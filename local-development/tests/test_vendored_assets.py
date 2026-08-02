"""The API-docs bundles are present, unmodified, and actually shipped.

`/api` and `/api/redoc` render from files committed to this repository rather than from
cdn.jsdelivr.net, because this chart targets clusters with no route to the internet — it
pulls oauth-proxy from the internal registry, injects a trusted CA bundle, and documents a
disconnected-mirror override. On such a cluster the stock FastAPI docs are blank pages.

Three separate things can break that, and each has a test here:

  * the files get modified or lost                 -> the lock check
  * the wheel stops carrying them                  -> the package-data check
  * the app quietly falls back to the CDN          -> the wiring check in test_api_contract

The middle one is the sneaky one. `package-data` was `static/*`, a single-level glob that
silently excludes `static/vendor/`, so the wheel would have shipped without the bundles
while every file sat correctly in git.
"""

from __future__ import annotations

import configparser
import hashlib
import pathlib
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
VENDOR = ROOT / "gsd" / "static" / "vendor"
LOCK = VENDOR / "ASSETS.lock"
SCRIPT = ROOT / "vendor-assets.sh"

EXPECTED = {"redoc.standalone.js", "swagger-ui-bundle.js", "swagger-ui.css"}


def _locked() -> dict[str, str]:
    entries = {}
    for line in LOCK.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        digest, name = line.split(None, 1)
        entries[name.strip()] = digest
    return entries


def test_the_bundles_are_committed():
    """Committed, not downloaded at build time.

    A build-time fetch makes every release depend on npm being up, on the version still
    being published, and on the build host having a route out — three ways for a release to
    become an incident at the worst moment.
    """
    assert VENDOR.is_dir(), f"{VENDOR} is missing — run ./vendor-assets.sh --upgrade"
    present = {p.name for p in VENDOR.iterdir() if p.suffix in {".js", ".css"}}
    assert EXPECTED <= present, f"missing bundles: {sorted(EXPECTED - present)}"


def test_the_lock_covers_every_bundle():
    locked = _locked()
    assert EXPECTED <= set(locked), (
        f"not recorded in ASSETS.lock: {sorted(EXPECTED - set(locked))}"
    )


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_each_bundle_matches_the_lock(name):
    """Detects a modified, truncated or partially-committed asset.

    Recomputed here rather than shelling out, so the test reports which file and both
    digests without depending on shasum vs sha256sum being the right one for this OS.
    """
    digest = hashlib.sha256((VENDOR / name).read_bytes()).hexdigest()
    assert digest == _locked()[name], (
        f"{name} does not match ASSETS.lock.\n"
        f"  locked: {_locked()[name]}\n  actual: {digest}\n"
        f"  If deliberate: ./vendor-assets.sh --upgrade. If not: git checkout -- {VENDOR}"
    )


def test_the_lock_records_which_versions_were_vendored():
    """Without the version, nobody can tell what is installed or whether it is old."""
    versions = [l for l in LOCK.read_text().splitlines() if l.startswith("# version ")]
    packages = {l.split()[2] for l in versions}
    assert {"redoc", "swagger-ui-dist"} <= packages, (
        f"ASSETS.lock does not record versions for every package: {packages}"
    )


def test_the_wheel_will_carry_them():
    """package-data must match the vendor subdirectory.

    `gsd = ["static/*"]` looks right and is not: the single-level glob excludes
    static/vendor/, so the wheel ships without the bundles and the built image silently
    falls back to the CDN — the exact failure vendoring them prevents, invisible in git.
    """
    text = (ROOT / "pyproject.toml").read_text()
    assert "static/vendor/*" in text, (
        "pyproject.toml package-data does not include static/vendor/*, so the wheel will "
        "not ship the API-docs bundles"
    )


def test_the_script_verifies_offline():
    """The same check a human or CI runs, exercised end to end.

    Offline by design: it has to work on a build host with no route out, which is the
    environment this whole arrangement exists for.
    """
    result = subprocess.run(
        [str(SCRIPT)], cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    assert result.returncode == 0, (
        f"./vendor-assets.sh failed:\n{result.stdout}\n{result.stderr}"
    )
    assert "Nothing was downloaded" in result.stdout


def test_no_asset_is_suspiciously_small():
    """A truncated download that still hashes consistently would pass the lock check.

    It cannot pass this: these bundles are hundreds of kilobytes, and an error page or a
    partial write is orders of magnitude smaller.
    """
    for name in sorted(EXPECTED):
        size = (VENDOR / name).stat().st_size
        assert size > 50_000, f"{name} is only {size} bytes — truncated or an error page?"
