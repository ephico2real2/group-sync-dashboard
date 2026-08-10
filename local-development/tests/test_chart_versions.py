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


def test_the_pinned_image_tag_is_a_build_of_that_same_app_version() -> None:
    """The pinned tag is `<version>-<git-sha>`, so its prefix must be appVersion.

    Catches the other half of the same drift: a chart claiming appVersion 0.6.0 while pinning an
    0.5.x image would install something other than what it advertises. The tag is written by the
    build script (or by CI's publish job), so a mismatch here means the chart was edited by hand
    and the two halves were not reconciled.
    """
    tag = yaml.safe_load(VALUES.read_text())["image"]["tag"]
    app = _chart()["appVersion"]
    assert tag.startswith(f"{app}-"), (
        f"values.yaml pins image tag {tag!r}, which is not a build of appVersion {app!r}. "
        "Expected <appVersion>-<git-sha>."
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
