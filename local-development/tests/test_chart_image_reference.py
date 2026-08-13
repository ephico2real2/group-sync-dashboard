"""Which image the chart deploys, asserted on the rendered manifest.

THREE WAYS TO NAME AN IMAGE, and they are not interchangeable:

    image.digest set   ->  repository@sha256:...   immutable. the registry cannot serve other bytes.
    image.tag set      ->  repository:tag          a NAME, repointable by whoever owns the registry
    both empty         ->  repository:appVersion   the chart's own declared version

`gsd.image` resolves them in that order. These tests render the chart and read the reference back,
because the resolution IS Helm templating — asserting on output is the only thing that tests what
ships. Same reason and same `render()` shape as tests/test_chart_strategy.py.

WHY A DIGEST NEEDS ITS OWN BRANCH rather than another link in the `default` chain: an OCI reference
by digest joins with `@`, not `:`. Joining a digest with a colon yields
`repository:sha256:abc...` — a syntactically valid TAG that no registry has — so the pod would fail
with ImagePullBackOff naming a tag nobody pushed. That is the failure this file's second test exists
to prevent, and it is invisible to `helm lint`.

AND WHY A BAD DIGEST MUST FAIL THE RENDER. A malformed digest still forms a reference Kubernetes
accepts, so passing it through moves the failure from a pipeline to a cluster. The chart already
takes this position elsewhere — `gsd.logLevel` refuses a level outside the five, and the ingress
host refuses to render when the apps domain cannot be read — and this follows it.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest
import yaml

CHART = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")

# A real digest of a real published image, and its shape is what matters here: sha256 plus 64
# lowercase hex. Hard-coded rather than fetched, so the suite needs no registry.
DIGEST = "sha256:aa6a7f5463c6b39f8d2647ba24ae756f4e7a0b101fe05c8e5bb58d05de016a68"


def render(**values) -> tuple[bool, str]:
    """Render the chart. Returns (ok, combined output)."""
    args = ["helm", "template", "t", str(CHART), "--set", "ingress.host=t.example.com"]
    for key, value in values.items():
        args += ["--set", f"{key.replace('__', '.')}={value}"]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


def dashboard_image(manifest: str) -> str:
    """The dashboard container's image, parsed out of the Deployment.

    PARSED, not grepped. The rendered manifest names several images — the oauth-proxy sidecar and
    the auth-loglevel Jobs' `oc` image among them — so a substring search could pass while the
    dashboard container itself was wrong.
    """
    for doc in yaml.safe_load_all(manifest):
        if not doc or doc.get("kind") != "Deployment":
            continue
        for container in doc["spec"]["template"]["spec"]["containers"]:
            if container["name"] == "dashboard":
                return container["image"]
    raise AssertionError("no dashboard container in the rendered Deployment")


def app_version() -> str:
    return str(yaml.safe_load((CHART / "Chart.yaml").read_text())["appVersion"])


def repository() -> str:
    return yaml.safe_load((CHART / "values.yaml").read_text())["image"]["repository"]


def test_no_digest_and_no_tag_resolves_the_charts_own_app_version() -> None:
    """THE REGRESSION GUARD THAT MATTERS MOST: the shipped default must be untouched.

    This is what every consumer who sets nothing gets. Adding digest support must not disturb it,
    and a branch in a template is exactly the kind of change that can.
    """
    ok, out = render()
    assert ok, out
    assert dashboard_image(out) == f"{repository()}:{app_version()}"


def test_a_digest_renders_with_an_at_sign_and_no_tag() -> None:
    """`repository@sha256:...`, and NOTHING resembling `:tag` in the reference.

    The negative half is the point. A digest accidentally joined with a colon still looks
    approximately right in a diff — `repository:sha256:abc...` — and fails only when a kubelet tries
    to pull it.
    """
    ok, out = render(image__digest=DIGEST)
    assert ok, out
    image = dashboard_image(out)
    assert image == f"{repository()}@{DIGEST}"
    assert f"{repository()}:" not in image, (
        f"the digest was joined as a tag rather than with '@': {image!r}"
    )


def test_a_digest_beats_a_tag_when_both_are_set() -> None:
    """Precedence, and it is the safe direction: the immutable form wins.

    A consumer who pins a digest and leaves an old tag lying in their values file must get the
    digest. The reverse — tag winning — would silently ignore the stronger pin.
    """
    ok, out = render(image__digest=DIGEST, image__tag="0.7.0-4830e5635a")
    assert ok, out
    image = dashboard_image(out)
    assert image == f"{repository()}@{DIGEST}"
    assert "4830e5635a" not in image, f"the tag survived alongside the digest: {image!r}"


def test_a_tag_still_wins_over_the_app_version_fallback() -> None:
    """The middle rung, unchanged from before digest support existed."""
    ok, out = render(image__tag="0.7.0-4830e5635a")
    assert ok, out
    assert dashboard_image(out) == f"{repository()}:0.7.0-4830e5635a"


@pytest.mark.parametrize(
    "bad,why",
    [
        ("abc123", "no algorithm prefix and far too short"),
        ("sha256:short", "right prefix, wrong length"),
        ("aa6a7f5463c6b39f8d2647ba24ae756f4e7a0b101fe05c8e5bb58d05de016a68",
         "64 hex but no sha256: prefix — the likeliest copy-paste mistake"),
        ("sha256:AA6A7F5463C6B39F8D2647BA24AE756F4E7A0B101FE05C8E5BB58D05DE016A68",
         "uppercase hex: registries compare the digest as a literal string, so this names "
         "something that does not exist"),
    ],
)
def test_a_malformed_digest_fails_the_render(bad: str, why: str) -> None:
    """Refused in the pipeline, not discovered on a cluster.

    Each of these forms a reference Kubernetes will accept, so without the guard the symptom is
    ImagePullBackOff against a digest no registry has — diagnosed at the wrong end of the day.
    """
    ok, out = render(image__digest=bad)
    assert not ok, f"{bad!r} was accepted ({why}); the render should have failed:\n{out}"
    assert "image.digest" in out, (
        f"the failure must name the value the operator has to fix; got:\n{out}"
    )
    assert "skopeo inspect" in out, (
        "the failure must say how to obtain a correct digest, or it only says 'no'"
    )
