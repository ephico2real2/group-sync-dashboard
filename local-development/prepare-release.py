#!/usr/bin/env python3
"""Prepare a release pull request: the version fields, the history comment, the changelog heading,
the branch and the commit — one operation that commits every release edit or commits nothing.

    ./prepare-release.py --app 0.12.0 "Users tab pages by cursor"
    ./prepare-release.py --chart 0.11.0 "route.tls.termination is settable"
    ./prepare-release.py --app 0.12.0 --chart 0.11.0 "..."
    ./prepare-release.py --app 0.12.0 "..." --pr           # also open the pull request with gh
    ./prepare-release.py --app 0.12.0 "..." --no-commit    # edit the tree, commit nothing

WHY A SCRIPT. An application release is four edits that must land together — pyproject's version,
gsd/__init__.py's __version__, Chart.yaml's appVersion and Chart.yaml's version — plus a history
line in Chart.yaml and a heading in docs/CHANGELOG.md, in one pull request (docs/RELEASING.md).
tests/test_chart_versions.py holds the four together, but only after they were typed by hand, and
the history conventions are held by nothing. This does all six from two arguments, runs that test,
and commits to a NEW branch. It never touches main, never tags, never talks to a registry: publish
and release stay where they are, downstream of a merge (docs/RELEASING.md#The whole flow).

WHAT IT DERIVES. `--app` alone bumps the chart PATCH, because moving appVersion is a chart change
and the release guide requires the bump — that is the precedent of chart 0.7.1, 0.9.1, 0.9.2 and
0.9.4. An explicit --chart wins. KIND (MAJOR, MINOR, PATCH) is the semver component that moved.

WHAT IT REFUSES. A dirty tree (a release commit must contain exactly the release). A version that
does not advance, or that moves a component while leaving a lower one non-zero (0.10.0 -> 0.11.1
is not a bump anyone means). A reason that is empty or spans lines. A release branch that already
exists (checked before anything is edited). A version test that fails — the edits are left in the
tree for inspection, and nothing is committed. A reason with an unbalanced backtick or an asterisk:
the changelog bullet is already bold, and a code span must close.

NO Co-Authored-By TRAILER. The operator cutting the release is its sole author.
"""

from __future__ import annotations

import argparse
import datetime as dt
import pathlib
import re
import subprocess
import sys
import textwrap

HERE = pathlib.Path(__file__).resolve().parent          # local-development/
REPO = HERE.parent
PYPROJECT = HERE / "pyproject.toml"
INIT = HERE / "gsd" / "__init__.py"
CHART = REPO / "charts" / "group-sync-dashboard" / "Chart.yaml"
CHANGELOG = REPO / "docs" / "CHANGELOG.md"
VERSION_TEST = HERE / "tests" / "test_chart_versions.py"

SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
# Chart.yaml's comments are written to this width; a generated line should read like its neighbours.
COMMENT_WIDTH = 100


class ReleaseError(Exception):
    """A refusal with a reason. Printed, exit 1, nothing committed."""


def parse_semver(version: str) -> tuple[int, int, int]:
    match = SEMVER.match(version)
    if not match:
        raise ReleaseError(f"{version!r} is not bare semver X.Y.Z")
    return tuple(int(part) for part in match.groups())  # type: ignore[return-value]


def kind_of_bump(old: str, new: str) -> str:
    """MAJOR, MINOR or PATCH — the component that moved — or a refusal.

    A component may skip numbers (0.10.0 -> 0.12.0 is a MINOR bump); what is refused is a move
    that leaves a LOWER component non-zero, because nobody means 0.10.0 -> 0.11.1.
    """
    o, n = parse_semver(old), parse_semver(new)
    if n <= o:
        raise ReleaseError(f"{new} does not advance {old}")
    if n[0] != o[0]:
        if n[1:] != (0, 0):
            raise ReleaseError(f"{old} -> {new} moves MAJOR but leaves lower components non-zero")
        return "MAJOR"
    if n[1] != o[1]:
        if n[2] != 0:
            raise ReleaseError(f"{old} -> {new} moves MINOR but leaves PATCH non-zero")
        return "MINOR"
    return "PATCH"


def bump_patch(version: str) -> str:
    major, minor, patch = parse_semver(version)
    return f"{major}.{minor}.{patch + 1}"


def read_field(path: pathlib.Path, pattern: str, what: str) -> str:
    match = re.search(pattern, path.read_text(), re.M)
    if not match:
        raise ReleaseError(f"no {what} in {path.relative_to(REPO)}")
    return match.group(1)


def replace_line(text: str, pattern: str, replacement: str, what: str) -> str:
    new, count = re.subn(pattern, replacement, text, count=1, flags=re.M)
    if count != 1:
        raise ReleaseError(f"expected exactly one {what} line, found {count}")
    return new


def insert_before_line(text: str, pattern: str, block: str, what: str) -> str:
    """Insert `block` (which must end with a newline) immediately before the line matching pattern."""
    match = re.search(pattern, text, re.M)
    if not match:
        raise ReleaseError(f"no {what} line to insert above")
    return text[: match.start()] + block + text[match.start():]


def comment(text: str) -> str:
    return "\n".join(textwrap.wrap(
        text, width=COMMENT_WIDTH, initial_indent="# ", subsequent_indent="# ",
        break_long_words=False, break_on_hyphens=False,
    )) + "\n"


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    done = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True, check=False)
    if check and done.returncode != 0:
        raise ReleaseError(f"git {' '.join(args)} failed:\n{done.stdout}{done.stderr}")
    return done


def sentence(reason: str) -> str:
    """The reason as a sentence: one line, capitalised as given, exactly one full stop."""
    text = reason.strip()
    if not text or "\n" in text:
        raise ReleaseError("the reason must be one non-empty line")
    # The reason lands inside a bold changelog bullet and a YAML comment, unescaped. A balanced
    # pair of backticks is a code span an operator meant; an odd count would swallow the rest of
    # the changelog into one, and an asterisk would end the bold early. Refused, never rewritten.
    if text.count("`") % 2:
        raise ReleaseError("the reason has an unbalanced backtick; close the code span")
    if "*" in text:
        raise ReleaseError("the reason may not contain '*'; the changelog bullet is already bold")
    text = text.rstrip(".")
    if not text:
        raise ReleaseError("the reason must be one non-empty line")
    return text


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("reason", help="one line: what this release is, for Chart.yaml and the changelog")
    parser.add_argument("--app", metavar="X.Y.Z", help="the new application version")
    parser.add_argument("--chart", metavar="A.B.C", help="the new chart version (derived as a PATCH bump when --app is given without it)")
    parser.add_argument("--pr", action="store_true", help="also open the pull request with `gh pr create`")
    parser.add_argument("--no-commit", action="store_true", help="edit the tree and stop; no branch, no commit")
    parser.add_argument("--date", default=dt.date.today().isoformat(), help="ISO date for the history line and heading (default: today)")
    args = parser.parse_args(argv)

    try:
        return run(args)
    except ReleaseError as err:
        print(f"ERROR: {err}", file=sys.stderr)
        return 1


def run(args: argparse.Namespace) -> int:
    if not args.app and not args.chart:
        raise ReleaseError("nothing to release: give --app and/or --chart")
    try:
        parsed_date = dt.date.fromisoformat(args.date)
    except ValueError:
        parsed_date = None
    if parsed_date is None or parsed_date.isoformat() != args.date:
        raise ReleaseError(f"--date {args.date!r} is not a real YYYY-MM-DD date")
    reason = sentence(args.reason)

    # ── Preconditions ─────────────────────────────────────────────────────────────────────────
    if git("status", "--porcelain").stdout.strip():
        raise ReleaseError("the working tree has uncommitted changes; a release commit must contain "
                           "exactly the release. Commit or stash first.")
    branch_now = git("rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if branch_now != "main":
        print(f"note    : branching from {branch_now}, not main", file=sys.stderr)

    app_old = read_field(PYPROJECT, r'^version = "(.+?)"$', 'version = "..."')
    init_old = read_field(INIT, r'^__version__ = "(.+?)"$', '__version__ = "..."')
    appversion_old = read_field(CHART, r'^appVersion: "(.+?)"$', 'appVersion: "..."')
    chart_old = read_field(CHART, r"^version: (\d+\.\d+\.\d+)[ \t]*$", "version:")
    if not (app_old == init_old == appversion_old):
        raise ReleaseError(f"the tree already disagrees with itself: pyproject {app_old}, "
                           f"__init__ {init_old}, appVersion {appversion_old}. Fix that first.")

    # ── What moves ────────────────────────────────────────────────────────────────────────────
    app_new = args.app or app_old
    if args.app:
        app_kind = kind_of_bump(app_old, app_new)
    chart_new = args.chart or (bump_patch(chart_old) if args.app else None)
    assert chart_new is not None
    chart_kind = kind_of_bump(chart_old, chart_new)
    if args.app and not args.chart:
        print(f"derived : chart {chart_old} -> {chart_new} (PATCH, because appVersion moves)")
    branch = f"release/app-{app_new}" if args.app else f"release/chart-{chart_new}"
    if (not args.no_commit
            and git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0):
        raise ReleaseError(f"branch {branch} already exists; nothing was changed. Delete or rename it.")

    # ── The edits ─────────────────────────────────────────────────────────────────────────────
    changed: list[pathlib.Path] = [CHART, CHANGELOG]
    chart_text = CHART.read_text()
    if args.app:
        PYPROJECT.write_text(replace_line(
            PYPROJECT.read_text(), r'^version = ".+?"$', f'version = "{app_new}"', "pyproject version"))
        INIT.write_text(replace_line(
            INIT.read_text(), r'^__version__ = ".+?"$', f'__version__ = "{app_new}"', "__version__"))
        changed += [PYPROJECT, INIT]
        # The application paragraph, in the form its neighbours use: `# X.Y.Z (date). ... KIND.`
        chart_text = insert_before_line(
            chart_text, r'^appVersion: ".+?"$',
            comment(f"{app_new} ({args.date}). {reason}. {app_kind}."), "appVersion")
        chart_text = replace_line(chart_text, r'^appVersion: ".+?"$', f'appVersion: "{app_new}"', "appVersion")
        history = (f"CHART {chart_new} ({args.date}), {chart_kind}: appVersion moves to application "
                   f"{app_new} (below); {reason}.")
    else:
        history = f"CHART {chart_new} ({args.date}), {chart_kind}: {reason}."
    chart_text = insert_before_line(
        chart_text, r"^version: \d+\.\d+\.\d+[ \t]*$", comment(history), "version")
    chart_text = replace_line(
        chart_text, r"^version: \d+\.\d+\.\d+[ \t]*$", f"version: {chart_new}", "version")
    CHART.write_text(chart_text)

    if args.app:
        heading = f"## Application {app_new} — chart {chart_new} — {args.date}"
    else:
        heading = f"## Chart {chart_new} — application {app_old} — {args.date}"
    bullet = f"- **{reason}.**\n"
    log = CHANGELOG.read_text()
    if re.search(r"^## Unreleased[ \t]*$", log, re.M):
        # The heading that has been collecting bullets since the last release becomes this one;
        # the reason goes first and the collected bullets follow it.
        log = replace_line(log, r"^## Unreleased[ \t]*$", heading + "\n\n" + bullet.rstrip("\n"), "Unreleased")
    else:
        log = insert_before_line(log, r"^## ", heading + "\n\n" + bullet + "\n", "first release heading")
    CHANGELOG.write_text(log)

    for path in changed:
        print(f"edited  : {path.relative_to(REPO)}")

    # ── The test that holds the four together ──────────────────────────────────────────────────
    done = subprocess.run([sys.executable, "-m", "pytest", str(VERSION_TEST), "-q"],
                          cwd=HERE, capture_output=True, text=True, check=False)
    if done.returncode != 0:
        print(done.stdout + done.stderr, file=sys.stderr)
        raise ReleaseError("tests/test_chart_versions.py fails on the edited tree; nothing was "
                           "committed. Inspect with `git diff`, undo with `git checkout -- .`")
    print("checked : tests/test_chart_versions.py passes")

    if args.no_commit:
        print("done    : --no-commit, the edits are in the tree and nothing is committed")
        return 0

    # ── The branch and the commit ──────────────────────────────────────────────────────────────
    title = (f"release: application {app_new}, chart {chart_new}" if args.app
             else f"release: chart {chart_new}")
    body_lines = [reason + "."]
    if args.app:
        body_lines += [f"pyproject.toml version, gsd/__init__.py __version__ and Chart.yaml appVersion: "
                       f"{app_old} -> {app_new} ({app_kind})."]
    body_lines += [f"Chart.yaml version: {chart_old} -> {chart_new} ({chart_kind})."]
    body = "\n".join(body_lines)

    git("checkout", "-q", "-b", branch)
    git("add", "--", *[str(p) for p in changed])
    git("commit", "-q", "-m", title, "-m", body)
    print(f"branch  : {branch}")
    print(f"commit  : {title}")

    if args.pr:
        done = subprocess.run(["gh", "pr", "create", "--base", "main", "--head", branch,
                               "--title", title, "--body", body],
                              cwd=REPO, capture_output=True, text=True, check=False)
        if done.returncode != 0:
            raise ReleaseError(f"gh pr create failed (the branch and commit exist):\n{done.stderr}")
        print(f"pr      : {done.stdout.strip()}")
    else:
        print(f"next    : git push -u origin {branch} && gh pr create --base main --head {branch}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
