"""prepare-release.py moves the four version fields together, writes the two history records, and
commits to a branch that is not main — or refuses. A refusal before the edits changes nothing; a
version test that fails after them leaves the edits for inspection and commits nothing.

Run in a COPY of the repository under a temporary git checkout: the script derives every path from
its own location, so copying it beside copies of the files it edits is the whole harness. The
subprocess is the real script, so the tests exercise what an operator runs, including the version
test it invokes.
"""

from __future__ import annotations

import importlib.util
import os
import pathlib
import re
import shutil
import subprocess
import sys

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

# The script's own constants and parser, so a test of the schema line reads the words the script writes.
_spec = importlib.util.spec_from_file_location("prepare_release", REPO / "local-development" / "prepare-release.py")
prep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prep)

# Everything the script reads or edits, plus what tests/test_chart_versions.py reads.
FILES = (
    "charts/group-sync-dashboard/Chart.yaml",
    "charts/group-sync-dashboard/values.yaml",
    "charts/group-sync-dashboard/templates/_helpers.tpl",
    "local-development/pyproject.toml",
    "local-development/gsd/__init__.py",
    "local-development/tests/test_chart_versions.py",
    "local-development/prepare-release.py",
    # An application release reads the schema at HEAD and at the commit that released the current version
    # with `git show <rev>:local-development/gsd/store.py` (#300); without it every --app case fails.
    "local-development/gsd/store.py",
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
# Far in the future on purpose: the real Chart.yaml and CHANGELOG are copied into the sandbox, and a
# date that could already appear in them would make "no application paragraph" assertions lie.
DATE = "2031-01-15"


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


def _next_chart_patch(sandbox: pathlib.Path) -> str:
    """A chart version that advances whatever the copied Chart.yaml says — never a literal, which
    stopped advancing the day the real chart moved past it."""
    major, minor, patch = current(sandbox)["chart"].split(".")
    return f"{major}.{minor}.{int(patch) + 1}"


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
    # Review of A2 (Codex): Python's \d accepts these and int() parses them, but helm.yaml's [0-9]
    # extractors and the build script would refuse the release they name.
    ("--app", "\u0669.\u0660.\u0660", "Arabic-Indic digits are not the workflows' [0-9]"),
    ("--chart", "\uff11\uff10.\uff10.\uff10", "full-width digits are not the workflows' [0-9]"),
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
    done = run(sandbox, "--chart", _next_chart_patch(sandbox), "Bad date", "--no-commit", date=bad_date)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "not a real YYYY-MM-DD date" in done.stderr
    assert git(sandbox, "status", "--porcelain").strip() == ""


def test_a_reason_that_would_break_the_changelog_bullet_is_refused(sandbox: pathlib.Path) -> None:
    """The bullet is `- **reason.**`: an odd backtick swallows the rest of the file into a code span
    and an asterisk ends the bold early. A balanced pair is a code span the operator meant."""
    target = _next_chart_patch(sandbox)
    for reason in ("an `unclosed span", "a *star*"):
        done = run(sandbox, "--chart", target, reason, "--no-commit")
        assert done.returncode == 1, reason
    assert git(sandbox, "status", "--porcelain").strip() == ""
    done = run(sandbox, "--chart", target, "the `--pr` flag opens the pull request", "--no-commit")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "- **the `--pr` flag opens the pull request.**" in (sandbox / "docs/CHANGELOG.md").read_text()


def test_the_reason_must_be_one_line(sandbox: pathlib.Path) -> None:
    """Including a reason that is nothing but full stops, or dots and spaces, or a zero-width space:
    each would have landed as an empty bold bullet. Every line boundary Python knows is a boundary
    here too — U+2028 in a YAML comment corrupted Chart.yaml in review — but a trailing newline, the
    shape "$(cat file)" gives, is stripped and accepted."""
    for reason in ("", "   ", "two\nlines", "two\rparts", "two\u2028parts", ".", "...", "   .",
                   " . . ", "\u200b"):
        done = run(sandbox, "--app", "9.0.0", reason)
        assert done.returncode == 1, repr(reason)
    assert git(sandbox, "status", "--porcelain").strip() == ""
    done = run(sandbox, "--chart", _next_chart_patch(sandbox), "trailing newline\n", "--no-commit")
    assert done.returncode == 0, done.stdout + done.stderr


def test_a_release_is_cut_from_main_only(sandbox: pathlib.Path) -> None:
    """From a topic branch the release branch would carry the topic's commits into a pull request
    based on main, under the release's title."""
    git(sandbox, "switch", "-q", "-c", "topic")
    (sandbox / "topic-only.txt").write_text("unrelated\n")
    git(sandbox, "add", "topic-only.txt")
    git(sandbox, "commit", "-qm", "topic commit")
    before = current(sandbox)
    done = run(sandbox, "--chart", _next_chart_patch(sandbox), "Chart release")
    assert done.returncode == 1
    assert "cut from main" in done.stderr
    assert current(sandbox) == before
    assert git(sandbox, "rev-parse", "--abbrev-ref", "HEAD").strip() == "topic"
    assert git(sandbox, "status", "--porcelain").strip() == ""


def test_missing_gh_leaves_the_branch_and_says_so(sandbox: pathlib.Path) -> None:
    """--pr with no gh on PATH must not traceback: the branch and commit exist and the error says so,
    or the operator reads the crash as nothing having happened."""
    bin_dir = sandbox.parent / "path-with-git-only"
    bin_dir.mkdir()
    git_path = shutil.which("git")
    assert git_path
    os.symlink(git_path, bin_dir / "git")
    env = {**GIT_ENV, "PATH": str(bin_dir)}
    done = subprocess.run(
        [sys.executable, str(sandbox / "local-development" / "prepare-release.py"),
         "--app", "9.0.0", "Need a PR", "--pr", "--date", DATE],
        cwd=sandbox, env=env, capture_output=True, text=True, check=False,
    )
    assert done.returncode == 1, done.stdout + done.stderr
    assert "Traceback" not in done.stderr
    assert "the branch and commit exist" in done.stderr
    assert git(sandbox, "rev-parse", "--abbrev-ref", "HEAD").strip() == "release/app-9.0.0"
    assert git(sandbox, "rev-list", "--count", "main..HEAD").strip() == "1"
    assert git(sandbox, "status", "--porcelain").strip() == ""


def test_a_release_promotes_merged_status_cells(sandbox: pathlib.Path) -> None:
    """Unreleased becoming a release heading is the moment `merged` becomes `released` (docs/specs/README.md).
    Status cells only: a spec body may say `merged` as history and must keep that word; a row at another
    status is left alone; and the edits are in the release commit."""
    specs = sandbox / "docs" / "specs"
    specs.mkdir(parents=True)
    (specs / "README.md").write_text(
        "| Id | Specification | Batch | Milestone | Version on release | Issue | Status |\n"
        "|---|---|---|---|---|---|---|\n"
        "| Z1 | [`SPEC_Z1_example.md`](SPEC_Z1_example.md) — example | Z | — | chart 9.0.0 |"
        " [#1](https://github.com/ephico2real2/group-sync-dashboard/issues/1) | merged |\n"
        "| Z2 | [`SPEC_Z2_example.md`](SPEC_Z2_example.md) — example | Z | — | chart 9.0.0 |"
        " [#2](https://github.com/ephico2real2/group-sync-dashboard/issues/2) | in progress |\n"
        # a two-digit id (E10, #533): a row the pattern cannot read leaves its merged header behind, and the release
        # is refused
        "| Z10 | [`SPEC_Z10_example.md`](SPEC_Z10_example.md) — example | Z | — | chart 9.0.0 |"
        " [#3](https://github.com/ephico2real2/group-sync-dashboard/issues/3) | merged |\n"
    )
    for name, status in (("SPEC_Z1_example.md", "merged"), ("SPEC_Z2_example.md", "in progress"),
                         ("SPEC_Z10_example.md", "merged")):
        (specs / name).write_text(
            "# SPEC\n\n| | |\n|---|---|\n| Release | — after |\n"
            "| Version on release | chart 9.0.0 |\n"
            "| Issue | [#1](https://github.com/ephico2real2/group-sync-dashboard/issues/1) |\n"
            f"| Status | {status} |\n\n"
            "## How to read this spec\n\nS1 (the Secret contract, merged) stays merged.\n"
        )
    git(sandbox, "add", "-A")
    git(sandbox, "commit", "-qm", "seed a merged spec")
    done = run(sandbox, "--app", "9.0.0", "Promote")
    assert done.returncode == 0, done.stdout + done.stderr
    index = (specs / "README.md").read_text()
    assert re.search(r"\| Z1 \|.*\| released \|$", index, re.M)
    assert re.search(r"\| Z2 \|.*\| in progress \|$", index, re.M)
    assert re.search(r"\| Z10 \|.*\| released \|$", index, re.M)
    assert "| Status | released |" in (specs / "SPEC_Z10_example.md").read_text()
    z1 = (specs / "SPEC_Z1_example.md").read_text()
    assert "| Status | released |" in z1
    assert "S1 (the Secret contract, merged) stays merged." in z1
    assert "| Status | in progress |" in (specs / "SPEC_Z2_example.md").read_text()
    assert git(sandbox, "status", "--porcelain").strip() == "", "the spec edits must be in the release commit"


# ── The schema line (#300) ──────────────────────────────────────────────────────────────────────────

# The sentence the issue fixed, written here as text so a change to the script's constant fails a test.
SCHEMA_SENTENCE = ("The first start on this image migrates the database one way; the pre-upgrade copy (#301) and "
                   "`restore-db.sh` (#302) are the way back.")
STORE = "local-development/gsd/store.py"
MIGRATIONS_OPEN = "_MIGRATIONS: list[tuple[int, str, list[str]]] = ["


def _next_app_minor(sandbox: pathlib.Path) -> str:
    """The next application MINOR — the version an issue that adds a migration takes."""
    major, minor, _ = current(sandbox)["app"].split(".")
    return f"{major}.{int(minor) + 1}.0"


def add_migrations(sandbox: pathlib.Path, count: int) -> tuple[int, int]:
    """Commit `count` no-op migrations above the sandbox's highest, as an issue branch would before its release
    edits, and return the highest target before and after."""
    store = sandbox / STORE
    text = store.read_text()
    before = prep.highest_migration(text)
    entries = "".join(f'\n    ({before + n}, "a test-only migration", []),' for n in range(1, count + 1))
    assert text.count(MIGRATIONS_OPEN) == 1, "the store's _MIGRATIONS opening line moved; update MIGRATIONS_OPEN"
    store.write_text(text.replace(MIGRATIONS_OPEN, MIGRATIONS_OPEN + entries))
    git(sandbox, "commit", "-qam", f"{count} migration(s)")
    assert prep.highest_migration(store.read_text()) == before + count
    return before, before + count


def entry(sandbox: pathlib.Path, heading: str) -> list[str]:
    """The lines of one changelog entry, from below its heading to the next heading."""
    lines = (sandbox / "docs/CHANGELOG.md").read_text().splitlines()
    start = lines.index(heading)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return lines[start + 1:end]


@pytest.mark.parametrize("count", [1, 2])
def test_t300_1_2_a_release_after_a_migration_carries_the_schema_line_under_its_reason(
        sandbox: pathlib.Path, count: int) -> None:
    """T300-1 and T300-2: the numbers are the release's and HEAD's highest targets, a jump of two included, and
    the line sits directly under the reason, before the bullets Unreleased collected. The changelog is seeded:
    the repository's own has no `## Unreleased` heading on a release PR's head (the release consumed it), and
    the collected bullets must be known to be asserted."""
    log = sandbox / "docs/CHANGELOG.md"
    log.write_text("# Changelog\n\nIntro.\n\n## Unreleased\n\n- **Something merged earlier.**\n\n"
                   "## Application 0.1.0 — chart 0.1.0 — 2026-01-01\n\n- old\n")
    git(sandbox, "commit", "-qam", "seed an Unreleased section")
    then, now = add_migrations(sandbox, count)
    target = _next_app_minor(sandbox)
    done = run(sandbox, "--app", target, "The migration's release", "--no-commit")
    assert done.returncode == 0, done.stdout + done.stderr
    lines = entry(sandbox, f"## Application {target} — chart {current(sandbox)['chart']} — {DATE}")
    assert lines == ["", "- **The migration's release.**", "", f"- **Schema {then} → {now}.** {SCHEMA_SENTENCE}",
                     "", "- **Something merged earlier.**", ""], "reason, the line, then the collected bullets"
    assert f"schema  : {then} at " in done.stdout and f"{now} at HEAD; the changelog entry says so" in done.stdout


def test_t300_1_the_line_is_written_without_an_unreleased_heading_too(sandbox: pathlib.Path) -> None:
    """The other branch of the changelog edit: no Unreleased heading, so the entry goes above the first release."""
    log = sandbox / "docs/CHANGELOG.md"
    log.write_text("# Changelog\n\nIntro.\n\n## Application 0.1.0 — chart 0.1.0 — 2026-01-01\n\n- old\n")
    git(sandbox, "commit", "-qam", "a changelog with no Unreleased heading")
    then, now = add_migrations(sandbox, 1)
    target = _next_app_minor(sandbox)
    done = run(sandbox, "--app", target, "Released", "--no-commit")
    assert done.returncode == 0, done.stdout + done.stderr
    assert entry(sandbox, f"## Application {target} — chart {current(sandbox)['chart']} — {DATE}") == [
        "", "- **Released.**", "", f"- **Schema {then} → {now}.** {SCHEMA_SENTENCE}", ""]


def test_t300_3_no_line_when_the_schema_did_not_move(sandbox: pathlib.Path) -> None:
    target = _next_app_minor(sandbox)
    done = run(sandbox, "--app", target, "No migration here", "--no-commit")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "; no schema line" in done.stdout
    lines = entry(sandbox, f"## Application {target} — chart {current(sandbox)['chart']} — {DATE}")
    assert lines[1] == "- **No migration here.**"
    assert not [line for line in lines if line.startswith("- **Schema ")]


def test_t300_4_no_line_on_a_chart_only_release(sandbox: pathlib.Path) -> None:
    """A chart-only release builds no image (docs/RELEASING.md, the chart-only flow), so it migrates nothing."""
    add_migrations(sandbox, 1)
    target = _next_chart_patch(sandbox)
    done = run(sandbox, "--chart", target, "A template change", "--no-commit")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "schema  :" not in done.stdout
    lines = entry(sandbox, f"## Chart {target} — application {current(sandbox)['app']} — {DATE}")
    assert not [line for line in lines if line.startswith("- **Schema ")]


def _shallow_clone(sandbox: pathlib.Path, tmp_path_factory) -> pathlib.Path:
    """A depth-1 clone of the sandbox. git marks it shallow (it does even for a single commit), so the walk to the
    release commit ends at a boundary that is not where the version began."""
    clone = tmp_path_factory.mktemp("shallow") / "repo"
    git(sandbox, "clone", "-q", "--depth", "1", f"file://{sandbox}", str(clone))
    assert git(clone, "rev-parse", "--is-shallow-repository").strip() == "true"
    return clone


def test_t300_6_a_shallow_history_is_refused_before_anything_is_edited(sandbox: pathlib.Path,
                                                                        tmp_path_factory) -> None:
    """Decision 2 of the issue: a release that cannot read the schema at the last release is refused, not cut
    blind, and the refusal comes before the first edit."""
    clone = _shallow_clone(sandbox, tmp_path_factory)
    before = current(clone)
    done = run(clone, "--app", _next_app_minor(clone), "Blind", "--no-commit")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "so nothing was changed" in done.stderr and "fetch-depth: 0" in done.stderr
    assert "Traceback" not in done.stderr
    assert current(clone) == before
    assert git(clone, "status", "--porcelain").strip() == ""


@pytest.mark.parametrize("broken", ["\n    *EXTRA,", "\n    (),"], ids=["starred", "empty-tuple"])
def test_t300_6_an_unreadable_migrations_list_is_refused_before_anything_is_edited(sandbox: pathlib.Path,
                                                                                     broken: str) -> None:
    """A store.py the helper cannot read (an entry that is not a literal tuple, and an empty tuple whose first
    element the helper indexes) is a refusal with the script's message, not a traceback, and nothing is edited."""
    store = sandbox / STORE
    store.write_text(store.read_text().replace(MIGRATIONS_OPEN, MIGRATIONS_OPEN + broken))
    git(sandbox, "commit", "-qam", "a _MIGRATIONS entry the parser cannot read")
    before = current(sandbox)
    done = run(sandbox, "--app", _next_app_minor(sandbox), "Unreadable", "--no-commit")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "so nothing was changed" in done.stderr and "Traceback" not in done.stderr
    assert current(sandbox) == before and git(sandbox, "status", "--porcelain").strip() == ""


def test_t300_6_a_schema_that_fell_is_refused_before_anything_is_edited(sandbox: pathlib.Path) -> None:
    """HEAD's highest target below the released one: that image would refuse (StoreSchemaTooNew) every database
    the released image migrated, so the release is refused before any edit, not cut with no line."""
    then, now = add_migrations(sandbox, 1)
    released = _next_app_minor(sandbox)
    done = run(sandbox, "--app", released, "Released with the migration")
    assert done.returncode == 0, done.stdout + done.stderr
    (sandbox / STORE).write_text((REPO / STORE).read_text())
    git(sandbox, "commit", "-qam", "the migration reverted, the version kept")
    before = current(sandbox)
    done = run(sandbox, "--app", _next_app_minor(sandbox), "Fell", "--no-commit")
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"reaches {then} at HEAD but {now} at" in done.stderr and "nothing was changed" in done.stderr
    assert "Traceback" not in done.stderr
    assert current(sandbox) == before and git(sandbox, "status", "--porcelain").strip() == ""


def test_t300_6_a_chart_only_release_reads_no_history(sandbox: pathlib.Path, tmp_path_factory) -> None:
    """The new refusal is the application release's alone: a chart-only release on the same clone is cut."""
    clone = _shallow_clone(sandbox, tmp_path_factory)
    done = run(clone, "--chart", _next_chart_patch(clone), "A template change", "--no-commit")
    assert done.returncode == 0, done.stdout + done.stderr


def test_t300_8_releasing_md_states_the_line_and_when_it_appears() -> None:
    text = (REPO / "docs" / "RELEASING.md").read_text()
    section = text.split("### An application release", 1)[1].split("### A chart-only release", 1)[0]
    assert prep.SCHEMA_LINE.format(then="N", now="M") in section, "the exact line, as the script writes it"
    assert f"- **Schema N → M.** {SCHEMA_SENTENCE}" in section
    for words in ("`_MIGRATIONS`", "schema_since_app_release", "chart-only", "fetch-depth: 0", "MINOR"):
        assert words in section, words
