"""The chart's version numbers must agree with the application they ship.

`appVersion` drifted to 0.5.2 and stayed there while the application moved to 0.6.0 and the
deployed image said so — so a consumer reading the chart learned a version that had not shipped
in weeks. Nothing caught it because appVersion sits outside the one chain that IS kept
consistent:

    local-development/pyproject.toml  version = "0.6.0"      <- the single source of truth
              |
              |  build-and-push-external.sh reads it
              v
    image tag  0.6.0-<git-sha>                               <- written into values.yaml
              |
              v
    values.yaml  image.tag: "0.6.0-01797a2cd8"

appVersion is declared by hand, so only a test can hold it to that chain. These are cheap file
reads with no cluster and no helm, so there is no reason for them not to run everywhere.
"""

from __future__ import annotations

import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
CHART = REPO / "charts" / "group-sync-dashboard" / "Chart.yaml"
VALUES = REPO / "charts" / "group-sync-dashboard" / "values.yaml"
PYPROJECT = REPO / "local-development" / "pyproject.toml"
INIT = REPO / "local-development" / "gsd" / "__init__.py"


def _app_version() -> str:
    """The application version, read the same way the build script reads it."""
    match = re.search(r'^version = "(.+?)"', PYPROJECT.read_text(), re.M)
    assert match, f"no `version = \"...\"` in {PYPROJECT}"
    return match.group(1)


def _chart() -> dict:
    return yaml.safe_load(CHART.read_text())


def test_appversion_equals_the_application_version() -> None:
    """The drift this file exists for.

    appVersion is what `helm search` and every chart consumer reads to answer "which version of
    the app does this deploy?". When it disagrees with pyproject.toml it is not vague, it is
    wrong — and wrong in the quiet direction, because the chart still installs and runs.
    """
    assert _chart()["appVersion"] == _app_version(), (
        "Chart.yaml appVersion disagrees with local-development/pyproject.toml. pyproject is the "
        "source of truth — build-and-push-external.sh derives the image tag from it — so update "
        "appVersion to match, rather than the other way round."
    )


def test_the_image_tag_is_empty_or_a_build_of_that_same_app_version() -> None:
    """SUCCESSOR to the pinned-tag check, which had nothing left to check once the pin went.

    THE ORIGINAL CAUGHT A REAL DEFECT and must not simply be deleted: it held the chart's pinned
    tag to appVersion, the other half of the drift that let appVersion read 0.5.2 for weeks while
    the application was 0.6.0. What changed is that `image.tag` now ships EMPTY — gsd.image resolves
    `default .Chart.AppVersion`, so a chart naming no tag deploys the version it declares, and there
    is no pin to compare (docs/DESIGN_decouple_chart_and_app_release.md).

    So the invariant becomes conditional, and covers BOTH states rather than only the committed one:

      empty      the chart resolves appVersion. Nothing to check, and this is what ships.
      non-empty  somebody pinned deliberately, and the prefix must still be appVersion — exactly
                 the original assertion, on exactly the original failure.

    Why not assert it is always empty: `build-and-push-external.sh --update-values` writes a real
    pin into a working copy, which is the supported path for building into your own registry. A test
    demanding empty would red the suite for a developer mid-build and teach them to skip it. This
    one passes for them AND still catches a pin that disagrees with appVersion — the case that
    installs something other than what the chart advertises.
    """
    tag = yaml.safe_load(VALUES.read_text())["image"]["tag"]
    app = _chart()["appVersion"]

    if not tag:
        return
    assert tag.startswith(f"{app}-"), (
        f"values.yaml pins image tag {tag!r}, which is not a build of appVersion {app!r}. "
        f"Expected either an empty tag — the chart then resolves appVersion — or "
        f"<appVersion>-<git-sha>."
    )


def test_an_empty_tag_still_resolves_to_something_the_chart_declares() -> None:
    """The empty case is only safe because the HELPER falls back; assert the helper, not the value.

    `image.tag: ""` is meaningless on its own — it is safe purely because
    `templates/_helpers.tpl#gsd.image` reads `default .Chart.AppVersion .Values.image.tag`. Remove
    that default and the chart renders `repository:` with a bare colon and no tag, which pulls
    `:latest` on some runtimes and fails outright on others. Neither is what the chart says it does.

    So this pins the coupling that makes an empty tag legitimate, in the file that ships it.
    """
    helper = (REPO / "charts" / "group-sync-dashboard" / "templates" / "_helpers.tpl").read_text()
    assert "default .Chart.AppVersion .Values.image.tag" in helper, (
        "gsd.image no longer falls back to .Chart.AppVersion, but values.yaml still ships an empty "
        "image.tag — so the chart would render an image reference with no tag at all. Either "
        "restore the fallback or stop shipping an empty tag."
    )


def test_the_shipped_chart_pins_neither_a_tag_nor_a_digest() -> None:
    """Both pins ship EMPTY, so the published chart deploys the appVersion it advertises.

    `image.digest` exists for consumers who need an immutable reference — a tag is a name the
    registry owner can repoint, a digest is the content itself. It must not be set HERE, because a
    digest committed into the chart would pin every installation to one build of one appVersion and
    quietly outlive the version it was taken from: `appVersion` would say 0.8.0 while the digest
    still served 0.7.0 bits, with nothing in the chart to reveal the disagreement.
    tests/test_chart_image_reference.py covers what each value does when a consumer sets it.
    """
    image = yaml.safe_load(VALUES.read_text())["image"]
    assert image.get("digest", "") == "", (
        f"values.yaml ships image.digest={image.get('digest')!r}. A committed digest overrides "
        "appVersion for every consumer and cannot be seen in `helm search`; pass it with --set at "
        "install time instead."
    )
    assert "digest" in image, (
        "image.digest is gone from values.yaml, so the only documented immutable pin is undiscoverable "
        "— `helm show values` is where a consumer looks for it."
    )


def test_the_package_version_equals_the_application_version() -> None:
    """THE SAME DRIFT, ONE FILE FURTHER IN, and nothing held it until 0.7.0.

    `gsd/__init__.py` declares `__version__` by hand — a second copy of the number, outside the
    chain this file's docstring draws. It is not decoration: gsd/api.py#version serves it at
    /api/version and gsd/metrics.py exports it as the `version` label on gsd_build_info, so those
    are what an operator reads to answer "what is this pod running?".

    Left uncoupled it fails in the quiet direction, worse than appVersion's did. A stale
    appVersion misinforms `helm search`; a stale `__version__` makes the RUNNING POD report a
    version it is not, confidently, on the endpoint built for exactly that question — while the
    image tag beside it (from GSD_GIT_COMMIT) is correct, so the two disagree and the
    human-readable one is the wrong half.
    """
    found = re.search(r'^__version__ = "(.+?)"', INIT.read_text(), re.M)
    assert found, f"no `__version__ = \"...\"` in {INIT}"
    assert found.group(1) == _app_version(), (
        f"gsd/__init__.py reports __version__ {found.group(1)!r} while pyproject.toml says "
        f"{_app_version()!r}. /api/version and gsd_build_info serve the former, so the pod would "
        "tell an operator it is running a version that was never built. pyproject is the source "
        "of truth — bump this to match."
    )


def test_the_chart_version_is_semver_and_not_the_app_version() -> None:
    """Two different numbers on purpose, and the comment in Chart.yaml says so.

    The chart version tracks TEMPLATE changes and is what gates publishing — chart-releaser
    skips a version it has already released. Tying it to appVersion would mean either
    republishing an unchanged chart on every app release, or being unable to ship a template fix
    without pretending the app changed.
    """
    version = str(_chart()["version"])
    assert re.fullmatch(r"\d+\.\d+\.\d+", version), (
        f"chart version {version!r} is not bare semver; chart-releaser tags releases as "
        f"<name>-<version> and a prerelease suffix changes how consumers resolve it"
    )


def test_the_changelog_heading_names_the_current_release_pair() -> None:
    """prepare-release.py writes `## Application X — chart Y — date` (or the chart-led form) at the
    top of the changelog; nothing held that heading to the files it describes, so a hand edit to
    one of them could leave the changelog naming a pair that never shipped (review, PR #73)."""
    log = (REPO / "docs" / "CHANGELOG.md").read_text()
    heading = next(line for line in log.splitlines() if line.startswith("## "))
    app = re.search(r'^version = "(.+?)"', PYPROJECT.read_text(), re.M).group(1)
    chart = re.search(r"^version: (\d+\.\d+\.\d+)", CHART.read_text(), re.M).group(1)
    # `## Unreleased` carries no date, so the date is taken only from a heading that has one (the
    # first A2 change landed under `## Unreleased` and found this branch unreachable — the rsplit
    # raised before the tuple was compared).
    date = heading.rsplit(" — ", 1)[1] if " — " in heading else ""
    assert heading in (
        f"## Application {app} — chart {chart} — {date}",
        f"## Chart {chart} — application {app} — {date}",
        "## Unreleased",
    ), f"the changelog's first heading {heading!r} does not name app {app} / chart {chart}"
