"""prepare-release.py moves the four version fields together, writes the two history records, and
commits to a branch that is not main — or refuses. A refusal before the edits changes nothing; a
version test that fails after them leaves the edits for inspection and commits nothing.

Run in a COPY of the repository under a temporary git checkout: the script derives every path from
its own location, so copying it beside copies of the files it edits is the whole harness. The
subprocess is the real script, so the tests exercise what an operator runs, including the version
test it invokes.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

# Everything the script reads or edits, plus what tests/test_chart_versions.py reads.
FILES = (
    "charts/group-sync-dashboard/Chart.yaml",
    "charts/group-sync-dashboard/values.yaml",
    "charts/group-sync-dashboard/templates/_helpers.tpl",
    "local-development/pyproject.toml",
    "local-development/gsd/__init__.py",
    "local-development/tests/test_chart_versions.py",
    "local-development/prepare-release.py",
    "docs/CHANGELOG.md",
    # The script runs pytest inside the sandbox, which writes tests/__pycache__/; without the
    # repository's own .gitignore the "everything edited was committed" check would see it.
    ".gitignore",
)

GIT_ENV = {
    **os.environ,
    # Isolated from the developer's own git config: a global hooksPath or commit.gpgsign would
    # otherwise fail the run for reasons unrelated to the script under test.
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    # ...and no configuration injected through the environment either.
    "GIT_CONFIG_COUNT": "0",
    "GIT_TERMINAL_PROMPT": "0",
    "GIT_AUTHOR_NAME": "Release Operator",
    "GIT_AUTHOR_EMAIL": "operator@example.com",
    "GIT_COMMITTER_NAME": "Release Operator",
    "GIT_COMMITTER_EMAIL": "operator@example.com",
}
DATE = "2026-09-05"


def git(cwd: pathlib.Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, env=GIT_ENV, capture_output=True, text=True)
    assert done.returncode == 0, f"git {' '.join(args)}:\n{done.stdout}\n{done.stderr}"
    return done.stdout


@pytest.fixture()
def sandbox(tmp_path: pathlib.Path) -> pathlib.Path:
    for rel in FILES:
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(REPO / rel, target)
    git(tmp_path, "init", "-q", "-b", "main")
    git(tmp_path, "add", "-A")
    git(tmp_path, "commit", "-qm", "baseline")
    return tmp_path


def run(sandbox: pathlib.Path, *args: str, date: str = DATE) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(sandbox / "local-development" / "prepare-release.py"), *args, "--date", date],
        cwd=sandbox, env=GIT_ENV, capture_output=True, text=True, check=False,
    )


def field(sandbox: pathlib.Path, rel: str, prefix: str) -> str:
    for line in (sandbox / rel).read_text().splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip().strip('"')
    raise AssertionError(f"no line starting {prefix!r} in {rel}")


def current(sandbox: pathlib.Path) -> dict[str, str]:
    return {
        "app": field(sandbox, "local-development/pyproject.toml", "version = "),
        "init": field(sandbox, "local-development/gsd/__init__.py", "__version__ = "),
        "appVersion": field(sandbox, "charts/group-sync-dashboard/Chart.yaml", "appVersion: "),
        "chart": field(sandbox, "charts/group-sync-dashboard/Chart.yaml", "version: "),
    }


def line_index(text: str, startswith: str) -> int:
    lines = text.splitlines()
    hits = [i for i, ln in enumerate(lines) if ln.startswith(startswith)]
    assert len(hits) == 1, f"expected one line starting {startswith!r}, found {len(hits)}"
    return hits[0]


def test_an_application_release_moves_all_four_fields_together(sandbox: pathlib.Path) -> None:
    before = current(sandbox)
    done = run(sandbox, "--app", "9.0.0", "A reason nobody will mistake")
    assert done.returncode == 0, done.stdout + done.stderr

    after = current(sandbox)
    assert after["app"] == after["init"] == after["appVersion"] == "9.0.0"
    major, minor, patch = before["chart"].split(".")
    assert after["chart"] == f"{major}.{minor}.{int(patch) + 1}", "the chart PATCH is derived"
    assert "derived : chart" in done.stdout

    chart = (sandbox / "charts/group-sync-dashboard/Chart.yaml").read_text()
    history = line_index(chart, f"# CHART {after['chart']} ({DATE}), PATCH: appVersion moves to application 9.0.0")
    assert history < line_index(chart, f"version: {after['chart']}")
    assert "A reason nobody will mistake." in chart
    paragraph = line_index(chart, f"# 9.0.0 ({DATE}). A reason nobody will mistake. MAJOR.")
    assert paragraph < line_index(chart, 'appVersion: "9.0.0"')

    log = (sandbox / "docs/CHANGELOG.md").read_text()
    headings = [ln for ln in log.splitlines() if ln.startswith("## ")]
    assert headings[0] == f"## Application 9.0.0 — chart {after['chart']} — {DATE}"
    assert "- **A reason nobody will mistake.**" in log
    assert not re.search(r"^## Unreleased[ \t]*$", log, re.M), "the heading line must be gone"

    assert git(sandbox, "rev-parse", "--abbrev-ref", "HEAD").strip() == "release/app-9.0.0"
    assert git(sandbox, "rev-list", "--count", "main..HEAD").strip() == "1"
    assert git(sandbox, "status", "--porcelain").strip() == "", "everything edited was committed"
    message = git(sandbox, "log", "-1", "--format=%B")
    assert message.startswith(f"release: application 9.0.0, chart {after['chart']}")
    assert "Co-Authored-By" not in message, "the operator is the sole author"
    assert git(sandbox, "log", "-1", "--format=%an").strip() == "Release Operator"


def test_a_chart_only_release_moves_one_field_and_names_the_application_it_carries(sandbox: pathlib.Path) -> None:
    before = current(sandbox)
    major, minor, _ = before["chart"].split(".")
    target = f"{major}.{int(minor) + 1}.0"
    done = run(sandbox, "--chart", target, "A template change")
    assert done.returncode == 0, done.stdout + done.stderr

    after = current(sandbox)
    assert (after["app"], after["init"], after["appVersion"]) == (before["app"], before["init"], before["appVersion"])
    assert after["chart"] == target
    chart = (sandbox / "charts/group-sync-dashboard/Chart.yaml").read_text()
    assert f"# CHART {target} ({DATE}), MINOR: A template change." in chart
    assert f"# {before['app']} ({DATE})" not in chart, "no application paragraph on a chart-only release"
    log = (sandbox / "docs/CHANGELOG.md").read_text()
    assert f"## Chart {target} — application {before['app']} — {DATE}" in log
    assert git(sandbox, "rev-parse", "--abbrev-ref", "HEAD").strip() == f"release/chart-{target}"
    assert git(sandbox, "log", "-1", "--format=%s").strip() == f"release: chart {target}"


def test_an_explicit_chart_version_wins_over_the_derived_patch(sandbox: pathlib.Path) -> None:
    before = current(sandbox)
    major, minor, _ = before["chart"].split(".")
    target = f"{major}.{int(minor) + 1}.0"
    done = run(sandbox, "--app", "9.0.0", "--chart", target, "Both, explicitly")
    assert done.returncode == 0, done.stdout + done.stderr
    assert current(sandbox)["chart"] == target
    assert "derived :" not in done.stdout
    assert f"# CHART {target} ({DATE}), MINOR: appVersion moves to application 9.0.0" in (
        sandbox / "charts/group-sync-dashboard/Chart.yaml").read_text()


def test_an_unreleased_heading_becomes_the_release_heading_and_keeps_its_bullets(sandbox: pathlib.Path) -> None:
    log = sandbox / "docs/CHANGELOG.md"
    log.write_text("# Changelog\n\nIntro.\n\n## Unreleased\n\n- **Something merged earlier.**\n\n## Application 0.1.0 — chart 0.1.0 — 2026-01-01\n\n- old\n")
    git(sandbox, "commit", "-qam", "seed an Unreleased section")
    done = run(sandbox, "--app", "9.0.0", "The release")
    assert done.returncode == 0, done.stdout + done.stderr
    text = log.read_text()
    assert not re.search(r"^## Unreleased[ \t]*$", text, re.M)
    chart = current(sandbox)["chart"]
    assert text.index(f"## Application 9.0.0 — chart {chart} — {DATE}") < text.index("- **The release.**")
    assert text.index("- **The release.**") < text.index("- **Something merged earlier.**")
    assert text.index("- **Something merged earlier.**") < text.index("## Application 0.1.0")


def test_a_dirty_tree_is_refused_and_nothing_is_edited(sandbox: pathlib.Path) -> None:
    before = current(sandbox)
    (sandbox / "docs/CHANGELOG.md").write_text("scratch\n")
    done = run(sandbox, "--app", "9.0.0", "Never mind")
    assert done.returncode == 1
    assert "uncommitted changes" in done.stderr
    assert current(sandbox) == before
    assert git(sandbox, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"


@pytest.mark.parametrize("flag,value,why", [
    ("--app", "0.0.1", "does not advance the application"),
    ("--chart", "0.0.1", "does not advance the chart"),
    ("--chart", "99.1.0", "moves MAJOR while leaving MINOR non-zero"),
    ("--app", "9.0.1", "moves MAJOR while leaving PATCH non-zero"),
])
def test_a_version_that_is_not_a_bump_is_refused(sandbox: pathlib.Path, flag: str, value: str, why: str) -> None:
    before = current(sandbox)
    done = run(sandbox, flag, value, "Nope")
    assert done.returncode == 1, why
    assert current(sandbox) == before, f"{why}: the tree must be untouched"
    assert git(sandbox, "status", "--porcelain").strip() == ""


def test_a_failing_version_test_leaves_the_edits_and_commits_nothing(sandbox: pathlib.Path) -> None:
    """The gate is real: sabotage what test_chart_versions.py asserts and the script must stop."""
    helpers = sandbox / "charts/group-sync-dashboard/templates/_helpers.tpl"
    helpers.write_text(helpers.read_text().replace("default .Chart.AppVersion .Values.image.tag", "REMOVED"))
    git(sandbox, "commit", "-qam", "break the helper the version test guards")
    done = run(sandbox, "--app", "9.0.0", "Would have been a release")
    assert done.returncode == 1
    assert "test_chart_versions.py fails" in done.stderr
    assert current(sandbox)["app"] == "9.0.0", "the edits are left for inspection"
    assert git(sandbox, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"
    assert git(sandbox, "rev-list", "--count", "HEAD").strip() == "2", "no release commit"


def test_no_commit_edits_the_tree_and_stops(sandbox: pathlib.Path) -> None:
    done = run(sandbox, "--app", "9.0.0", "Just the edits", "--no-commit")
    assert done.returncode == 0, done.stdout + done.stderr
    assert current(sandbox)["app"] == "9.0.0"
    assert git(sandbox, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"
    assert git(sandbox, "status", "--porcelain").strip() != ""


def test_an_existing_release_branch_is_refused_before_anything_is_edited(sandbox: pathlib.Path) -> None:
    before = current(sandbox)
    git(sandbox, "branch", "release/app-9.0.0")
    done = run(sandbox, "--app", "9.0.0", "Twice")
    assert done.returncode == 1
    assert "already exists" in done.stderr
    assert git(sandbox, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"
    assert current(sandbox) == before and git(sandbox, "status", "--porcelain").strip() == ""


@pytest.mark.parametrize("bad_date", ["2026-99-99", "2026-02-30", "26-09-05"])
def test_the_date_must_be_a_real_calendar_date(sandbox: pathlib.Path, bad_date: str) -> None:
    """A regex accepted 2026-99-99 and wrote it into both history records."""
    done = run(sandbox, "--chart", "0.10.1", "Bad date", "--no-commit", date=bad_date)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "not a real YYYY-MM-DD date" in done.stderr
    assert git(sandbox, "status", "--porcelain").strip() == ""


def test_a_reason_that_would_break_the_changelog_bullet_is_refused(sandbox: pathlib.Path) -> None:
    """The bullet is `- **reason.**`: an odd backtick swallows the rest of the file into a code span
    and an asterisk ends the bold early. A balanced pair is a code span the operator meant."""
    for reason in ("an `unclosed span", "a *star*"):
        done = run(sandbox, "--chart", "0.10.1", reason, "--no-commit")
        assert done.returncode == 1, reason
    assert git(sandbox, "status", "--porcelain").strip() == ""
    done = run(sandbox, "--chart", "0.10.1", "the `--pr` flag opens the pull request", "--no-commit")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "- **the `--pr` flag opens the pull request.**" in (sandbox / "docs/CHANGELOG.md").read_text()


def test_the_reason_must_be_one_line(sandbox: pathlib.Path) -> None:
    """Including a reason that is nothing but full stops: it strips to nothing and would have landed
    as `- **.**` in the changelog."""
    for reason in ("", "   ", "two\nlines", ".", "...", "   ."):
        done = run(sandbox, "--app", "9.0.0", reason)
        assert done.returncode == 1, repr(reason)
    assert git(sandbox, "status", "--porcelain").strip() == ""
