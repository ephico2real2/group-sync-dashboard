# SPEC A3 — Release preparation script

| | |
|---|---|
| Programme | Feature programme 2026-09 — index and version ladder in `docs/specs/README.md` |
| Batch | A — release |
| Release | R1 — Quality and release tooling |
| Version on release | no version change (a repository tool) |
| Issue | [#57](https://github.com/ephico2real2/group-sync-dashboard/issues/57) |
| Status | released |
| Source | design agent output `a38be666b46d57784`; one message; no seam |

## How to read this spec

Everything under "Batch preamble", "Design" and "Batch closing sections" is the design agent's text,
sliced from the agent's output by heading and re-concatenated to the byte before this file was
written. It is verbatim with exactly two kinds of exception, both stated in this file: the seam
repair named in the Source row where the agent's output was cut across messages, and the citation or
name corrections listed under "Orchestrator's notes", each of which changes a reference and never a
claim. Nothing else was rewritten by hand. Implementation applies the code in "Design" exactly as
written, one file at a time, with the orchestrator's notes governing where they and the body differ;
a deviation found necessary during implementation is written back into this file in the same pull
request, with the reason, under "Orchestrator's notes".

## Orchestrator's notes

- Lands second in R1. The script's first real use is B4's release.
- Ladder inversion found in review (PR #69, C8): A3 lands BEFORE A2, so the body's "after the A2 bullet" places the CHANGELOG bullet directly under `## Unreleased`, and the RELEASING sentences that describe signed images with SBOM and provenance and an attested chart package are NOT written by A3 — A2 adds them when it lands. A3 documents the release as it is at that point.
- Citation corrected: the design cited the chart README with the anchor "(no `redirectMode` key)", which nests backticks that the citation grammar (path#anchor inside one backtick span) cannot express; the anchor now cites `redirectMode`, the row's own text.

- Deviation recorded at implementation (PR for #57): the body's test asserted `"## Unreleased" not in log` after a release, but the CHANGELOG's intro sentence (written by A1 and extended by this spec) contains that text inside backticks, so the substring assertion cannot pass on the real file while the script correctly replaces only the heading line. Both assertions now test for the heading LINE (`^## Unreleased` with `re.M`), which is what the script's own regex targets. No change to the script.

- Deviation recorded at implementation (PR for #57): the sandbox `FILES` list gains `.gitignore`. The script runs `tests/test_chart_versions.py` inside the sandbox, which writes `tests/__pycache__/`; the real repository ignores it, the sandbox did not, and the "everything edited was committed" assertion saw an untracked directory. Test harness only; no change to the script.

- Found in review (PR #71, Codex C2): the docstring promised "either completes or changes nothing" while the existing-branch check ran after the four edits. The check now runs before any edit (skipped under `--no-commit`, which never branches) and both docstrings say what is true: a refusal before the edits changes nothing; a failed version test leaves its edits for inspection, as the design intended.
- Found in review (PR #71, Codex C7): `--date` was shape-checked only, so `2026-99-99` was written into both history records. Now `date.fromisoformat` with a round-trip; three bad dates are tested.
- Found in review (PR #71, Codex C6): an unbalanced backtick in the reason produced an unclosed code span in the changelog bullet. The reviewer's fix escaped every backtick, which would break the code span an operator means ("the `--pr` flag"); rejected. The reason is refused, never rewritten, when its backticks are unbalanced or it contains `*` (the bullet is already bold); a balanced pair is tested to pass through intact.
- Found in review (PR #71, Codex C4), routed to A2: `.github/workflows/helm.yaml`'s `sed` extractors accept broader version forms than this script writes (`[0-9][0-9.]*`, `"(.*)"` with trailing blanks). Everything the script writes is accepted, so nothing changes here; A2, which rewrites `helm.yaml`, tightens both extractors to `X.Y.Z` and `"(.+)"` with a test.

- Found in review (PR #71, Cursor C6, on the fixed head): a reason of only full stops stripped to nothing and would have landed as `- **.**`; refused now, tested. Cursor also noted the test harness inherited `GIT_CONFIG_COUNT`/`GIT_CONFIG_KEY_*` from the environment; `GIT_CONFIG_COUNT=0` closes it. The verification section's "13 passed" is the design's count; the file holds 17 after the review.
- Found in review (PR #71, Cursor, not asked), routed to B4: the `Chart.yaml` preamble says nothing but a human writes the file, which this script now does. A comment-only edit under `charts/` costs a chart release, so the sentence is corrected in B4's PR, the first to bump the chart.

- Found in the second pass (PR #71; Codex gpt-5.6-sol at xhigh and Cursor Grok 4.6 high fast, both on the fixed head): (1) `--pr` with no `gh` on PATH raised an uncaught `FileNotFoundError` after the release commit existed — the body's risk section claimed the script "says so"; now a `ReleaseError` that names the branch and commit. (2) The body only NOTED a checkout other than main; a release branch cut from a topic branch carries that branch's commits into a PR based on main, so it is refused when the run would commit (`--no-commit` edits and branches nothing, so the spec's dry run on a feature branch still works). (3) The one-line check tested `\n` only; `\r` passed and U+2028 corrupted Chart.yaml; now `splitlines()` on the stripped text, so a trailing newline is still fine. (4) A reason of dots and spaces or only zero-width characters still produced an empty bold bullet; a reason must contain a letter or digit. Rejected: `break_long_words=True` to hold the 100-column comment width (it would split a URL or identifier in a comment) and display-width wrapping. The test file holds 19 tests after this.

## Batch preamble (verbatim from the design)

# Design: A1 (UI tests in CI), A2 (SBOM, signing, provenance), A3 (release preparation script)

Every claim below is grounded in a file read in this session, cited as `path#anchor`. Nothing was written.

## 0. The amended house rule, applied

Each feature is a module with one switch; the default is a judgment, and the rationale is in the comment beside the switch.

| Feature | Switch | Default | Why |
|---|---|---|---|
| A1 browser tests in CI | repository variable `CI_UI_TESTS` (`ci.yml` `ui` job, `if: vars.CI_UI_TESTS != 'false'`) | **ON** | needs no credential, no cluster, no second image; only a Chromium download. The tests already exist (`local-development/tests/test_ui.py#dash`), and a green CI that skips them is the failure `ci.yml#Unit and integration tests` names. A fork or self-hosted runner that cannot fetch browsers sets it to `false`; the `tests` matrix is byte-identical either way. |
| A2 SBOM | repository variable `SUPPLY_CHAIN_SBOM` (`publish.yml` `sbom` job) | **ON** | reads the pushed image with the same registry credential the publish job already holds; produces a workflow artifact; no identity, no publication change. |
| A2 signing + provenance (image and chart) | repository variable `SUPPLY_CHAIN_SIGNING` (`publish.yml` `attest` job, `helm.yaml` chart attestation steps) | **ON** | keyless: GitHub OIDC (`id-token: write`) needs no secret. What it needs instead is stated in the workflow comment: egress to `fulcio.sigstore.dev`, `rekor.sigstore.dev`, `tuf-repo-cdn.sigstore.dev`, and a repository that is not a fork (forks are already skipped by `publish.yml#github.repository ==`). A self-hosted runner without that egress sets it to `false`. Signing changes nothing that is published — it adds referrers beside the image and records in GitHub's store. |
| A2 interaction | modelled, not left to chance | — | `attest` `needs: [publish, sbom]` with `!cancelled()`; the SBOM is attached only when `needs.sbom.result == 'success'`, and a step says by name when it is not. SBOM off + signing on: image signed, provenance attested, no SBOM attestation. SBOM on + signing off: SBOM artifact only. Chart attestation runs only when chart-releaser will publish a NEW version (`helm.yaml` `steps.plan.outputs.new`), so a skipped version attests nothing and says so. |
| A3 release script | invocation is the switch; side effects have their own: `--no-commit` (edit only), `--pr` (open the PR, off by default) | **ON** (exists; off = nobody ran it) | a script that edits a working tree and commits to a new branch has no cluster-wide side effect and never touches `main` — the `docs/RELEASING.md#Nothing else couples them` model is preserved. |

No Helm value is added by any feature. A chart value read by nothing is exactly the debt `charts/group-sync-dashboard/README.md#redirectMode` records removing, and `local-development/tests/test_environments_readme.py#test_every_key_in_the_table_still_exists_in_the_chart` would fail a README row with no key behind it. Nothing in A1–A3 runs in a pod. So the chart README values table gains no row, and Chart.yaml is not bumped (no PR touches `charts/`), which keeps `ci.yml#Chart changes bump the chart version` green without a version move.

Repository-wide conventions relied on:

- `docs/CHANGELOG.md` heading convention `## Application X — chart Y — date` (and `## Chart X — application Y — date` for chart-led releases). None of these PRs is a release, so A1 introduces a `## Unreleased` heading that A3's script converts into the release heading. The intro paragraph says so.
- `local-development/tests/test_docs_citations.py#CITATION` — every `` `path#anchor` `` in new docs below names a substring that exists in the cited file (`.py` anchors resolve through the AST or as a substring).
- Action pins: full commit of a release tag with the version in a comment (`ci.yml#ACTION PINS`). All SHAs below were resolved with `gh api repos/<owner>/<repo>/git/ref/tags/<tag>`, annotated tags through `git/tags/<sha>`:

| Action | Tag | Commit | `runs.using` |
|---|---|---|---|
| `actions/upload-artifact` | v7.0.1 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` | node24 |
| `actions/download-artifact` | v8.0.1 | `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` | node24 |
| `anchore/sbom-action` | v0.24.2 (annotated → commit) | `3ad7283483fc7af8ff2b4ea19663c2d5ca935e26` | node24 |
| `sigstore/cosign-installer` | v4.1.2 | `6f9f17788090df1f26f669e9d70d6ae9567deba6` | composite |
| `actions/attest-build-provenance` | v4.2.2 | `4d101475d8b20a2381f78447822ac1eab6504dd8` | composite (wraps `actions/attest` v4.2.1, pinned inside) |
| `helm/chart-releaser-action` | v1.7.0 (annotated → commit) | `cae68fefc6b5f367a0275617c9f83181ba54714f` | composite |

`helm.yaml` today uses `helm/chart-releaser-action@v1.7.0` — a mutable tag, against the rule at `ci.yml#ACTION PINS`. A2 pins it and adds a test so it cannot regress.

Tool pins: Syft `v1.51.1` (the version `docs/image-vulnerability-scan.md#Tools:` measured identifying Hummingbird; latest release on 2026-09-04), cosign `v3.1.3` (latest release; the installer's own default is v3.0.6), playwright `1.62.0` + pytest-playwright `0.8.0` (the pair in the local venv that runs the suite today; pytest-playwright 0.9.0 exists and is not yet exercised locally).

Order of PRs: **A1 → A2 → A3.** A1 creates `## Unreleased`; A2 adds the pin test that A1's actions must already satisfy; A3 converts `## Unreleased` and is documented in RELEASING.md on top of A2's diagram.

---


## Design (verbatim)

## FEATURE A3 — release preparation script

### Goal and switch

`local-development/prepare-release.py` takes `--app X.Y.Z` and/or `--chart A.B.C` and a one-line reason; refuses a dirty tree; edits the four fields (`local-development/pyproject.toml#version`, `local-development/gsd/__init__.py#__version__`, `charts/group-sync-dashboard/Chart.yaml#appVersion`, `charts/group-sync-dashboard/Chart.yaml#version`); inserts the `# CHART A.B.C (date), KIND: …` history line directly above `version:` (and the application paragraph above `appVersion:`, in the file's own `# X.Y.Z (date). … KIND.` form); turns `## Unreleased` into the release heading in `docs/CHANGELOG.md` (or inserts one), with the reason as the first bullet; runs `tests/test_chart_versions.py`; creates `release/app-X.Y.Z` or `release/chart-A.B.C` and one commit with no trailer; `--pr` opens the PR with `gh`. Python, because it edits comments positionally and is testable in a temp copy — the repository already ships Python tooling (`local-development/cluster-report.py`, `local-development/uninstall-lists.py`).

Derivation instead of refusal: `--app` without `--chart` bumps the chart PATCH (the precedent of chart 0.7.1, 0.9.1, 0.9.2, 0.9.4 in `Chart.yaml#CHART 0.9.4`), and says so; an explicit `--chart` wins. KIND is the semver component that moved; a bump that leaves a lower component non-zero (0.10.0 → 0.11.1) or does not advance is refused.

### Files

#### `local-development/prepare-release.py` — new (commit with `chmod +x`)

```python
#!/usr/bin/env python3
"""Prepare a release pull request: the version fields, the history comment, the changelog heading,
the branch and the commit — one operation that either completes or changes nothing.

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
exists. A version test that fails — the edits are left in the tree for inspection, and nothing is
committed.

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
    return text.rstrip(".")


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
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", args.date):
        raise ReleaseError(f"--date {args.date!r} is not YYYY-MM-DD")
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
    branch = f"release/app-{app_new}" if args.app else f"release/chart-{chart_new}"
    if git("rev-parse", "--verify", "--quiet", f"refs/heads/{branch}", check=False).returncode == 0:
        raise ReleaseError(f"branch {branch} already exists; the edits are in the tree, nothing was "
                           "committed. Delete or rename it, or `git checkout -- .` to undo.")
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
```

#### `local-development/tests/test_prepare_release.py` — new

```python
"""prepare-release.py moves the four version fields together, writes the two history records, and
commits to a branch that is not main — or refuses and changes nothing.

Run in a COPY of the repository under a temporary git checkout: the script derives every path from
its own location, so copying it beside copies of the files it edits is the whole harness. The
subprocess is the real script, so the tests exercise what an operator runs, including the version
test it invokes.
"""

from __future__ import annotations

import os
import pathlib
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
)

GIT_ENV = {
    **os.environ,
    # Isolated from the developer's own git config: a global hooksPath or commit.gpgsign would
    # otherwise fail the run for reasons unrelated to the script under test.
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
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


def run(sandbox: pathlib.Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(sandbox / "local-development" / "prepare-release.py"), *args, "--date", DATE],
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
    assert "## Unreleased" not in log

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
    assert "## Unreleased" not in text
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


def test_an_existing_release_branch_is_refused(sandbox: pathlib.Path) -> None:
    git(sandbox, "branch", "release/app-9.0.0")
    done = run(sandbox, "--app", "9.0.0", "Twice")
    assert done.returncode == 1
    assert "already exists" in done.stderr
    assert git(sandbox, "rev-parse", "--abbrev-ref", "HEAD").strip() == "main"


def test_the_reason_must_be_one_line(sandbox: pathlib.Path) -> None:
    for reason in ("", "   ", "two\nlines"):
        done = run(sandbox, "--app", "9.0.0", reason)
        assert done.returncode == 1, repr(reason)
    assert git(sandbox, "status", "--porcelain").strip() == ""
```

#### `docs/RELEASING.md` — edit (A3 part)

Old:
```markdown
### An application release

1. Bump `version` in `local-development/pyproject.toml`.
2. Bump `__version__` in `local-development/gsd/__init__.py` to match — it is what `/api/version` and
   `gsd_build_info` report, and a test holds the two together.
3. Bump `appVersion` in `charts/group-sync-dashboard/Chart.yaml` to match.
4. Bump `Chart.yaml` `version` too, because you just changed the chart. `ci.yml` will fail the PR if
   you forget.
5. Open the PR, merge it. `publish.yml` sees the version change and publishes both the immutable tag
   and the `:<appVersion>` alias.

All three version edits land in one PR, or CI is red. That is the coupling working, not friction.

### A chart-only release

Change the templates or defaults, bump `Chart.yaml` `version`, open the PR, merge. No image is
built — `charts/**` is deliberately absent from `publish.yml`'s path filter — and `helm.yaml` retags
the existing image under the new chart version.
```
New:
```markdown
### An application release

```sh
cd local-development
./prepare-release.py --app 0.12.0 "Users tab pages by cursor"          # branch + commit
./prepare-release.py --app 0.12.0 "Users tab pages by cursor" --pr     # ...and the pull request
```

What that does, and what you would do by hand without it:

1. Bump `version` in `local-development/pyproject.toml`.
2. Bump `__version__` in `local-development/gsd/__init__.py` to match — it is what `/api/version` and
   `gsd_build_info` report, and a test holds the two together.
3. Bump `appVersion` in `charts/group-sync-dashboard/Chart.yaml` to match.
4. Bump `Chart.yaml` `version` too, because you just changed the chart. The script derives a PATCH
   bump; pass `--chart A.B.C` when the release is more than that. `ci.yml` fails the PR if the
   version did not move.
5. Write the `# CHART A.B.C (date), KIND: …` line above `version:` and the application paragraph
   above `appVersion:` — the file's history, newest nearest the field.
6. Turn `## Unreleased` in `docs/CHANGELOG.md` into `## Application X — chart Y — date`, with the
   reason as its first bullet and everything merged since the last release beneath it.
7. Run `tests/test_chart_versions.py`. The script refuses to commit if it fails, and leaves the
   edits in the tree for you to read.
8. Open the PR, merge it. `publish.yml` sees the version change and publishes both the immutable tag
   and the `:<appVersion>` alias — signed, with its SBOM and provenance.

The script refuses a dirty tree, a version that does not advance, a bump that leaves a lower
component non-zero, and a release branch that already exists; it commits to `release/app-X.Y.Z`
with you as the only author and never touches `main` (`local-development/prepare-release.py#WHAT IT REFUSES`).
All the edits land in one PR, or CI is red. That is the coupling working, not friction.

### A chart-only release

Change the templates or defaults, then:

```sh
cd local-development
./prepare-release.py --chart 0.11.0 "route.tls.termination is settable"
```

It bumps `Chart.yaml` `version`, writes the history line, and turns `## Unreleased` into
`## Chart A.B.C — application X.Y.Z — date`. Open the PR, merge. No image is built — `charts/**`
is deliberately absent from `publish.yml`'s path filter — and `helm.yaml` retags the existing image
under the new chart version and attests the package.
```

Note: the history bullets under `## Unreleased` describe the chart-only release's other changes; the script's bullet is the reason. The uncommitted template edits must be committed before the script runs (it refuses a dirty tree) — say so in the doc? It is implied by "refuses a dirty tree" above; the chart-only paragraph gets one more sentence: "Commit the template change first; the script refuses a dirty tree, so the release commit contains only the release." Add that sentence after the `--chart` code block in the orchestrator's application.

#### `local-development/README.md` — edit (table row)

Old:
```markdown
| `release-crc.sh` | build + push + deploy against **CRC's built-in registry**. Portable nowhere else |
```
New:
```markdown
| `release-crc.sh` | build + push + deploy against **CRC's built-in registry**. Portable nowhere else |
| `prepare-release.py` | the four version fields, the Chart.yaml history line, the changelog heading, the branch and the commit, from `--app`/`--chart` and a reason; runs the version test first (`../docs/RELEASING.md`) |
```

#### `docs/CHANGELOG.md` — edits (A3 part)

Old:
```markdown
lives next to the code and in the design and review records linked here. Changes merged since the
last release sit under `## Unreleased` until the release that carries them replaces that heading.
```
New:
```markdown
lives next to the code and in the design and review records linked here. Changes merged since the
last release sit under `## Unreleased` until the release that carries them replaces that heading —
which `local-development/prepare-release.py` does when the release is cut.
```
And a bullet appended under `## Unreleased` (after the A2 bullet, before `## Application 0.11.0 — chart 0.10.0 — 2026-09-04`):
```markdown
- **A release is one command.** `local-development/prepare-release.py --app X.Y.Z "reason"` (or
  `--chart A.B.C`) moves the four version fields together, writes the `Chart.yaml` history line and
  the application paragraph, turns this `## Unreleased` heading into the release heading, runs
  `tests/test_chart_versions.py`, and commits to `release/…` with the operator as sole author;
  `--pr` opens the pull request. It refuses a dirty tree, a version that does not advance, and a
  branch that exists. Nothing writes to `main`, as before.
```

### Verification (A3)

```sh
cd local-development
.venv/bin/python -m pytest tests/test_prepare_release.py -q          # expected: 13 passed (4 parametrised)
.venv/bin/python -m pytest tests/test_docs_citations.py -q           # the new `prepare-release.py#WHAT IT REFUSES` citation resolves
# a dry run on the real tree, undone afterwards:
./prepare-release.py --chart 0.10.1 "dry run" --no-commit && git diff --stat && git checkout -- . 
# expected diff: charts/group-sync-dashboard/Chart.yaml and docs/CHANGELOG.md only; "checked : tests/test_chart_versions.py passes"
./prepare-release.py --app 0.11.1 "dry run" --no-commit && git diff --stat && git checkout -- .
# expected diff: the four files; "derived : chart 0.10.0 -> 0.10.1 (PATCH, because appVersion moves)"
```

### Risks and how they close

- The Chart.yaml comment regexes assume `version: X.Y.Z` bare and `appVersion: "X.Y.Z"` quoted — exactly the forms `helm.yaml#CHART_VERSION=$(sed` and `build-and-push-external.sh#no bare-semver version line` already depend on; a change to either form fails with "expected exactly one … line", not a silent mis-edit.
- `git commit` uses the operator's identity from their git config; the tests set it through `GIT_AUTHOR_*` so the venv's environment is not a factor.
- `gh pr create` failure after the commit leaves the branch and commit, and says so.

---


## Batch closing sections (verbatim)

## Order of PRs and what each needs from the operator

1. **A1** — `ci.yml`, `test_ci_ui_job.py`, `local-development/README.md`, `RELEASING.md` (one line), `CHANGELOG.md` (intro + `## Unreleased`), `README.md` variables row for `CI_UI_TESTS` (included in A2's table rewrite; if A1 lands alone, add only that row). No `charts/` change, no version bump.
2. **A2** — build script, `publish.yml`, `helm.yaml`, `test_supply_chain.py`, `test_workflow_pins.py`, `HELM_DOWNLOAD_AND_INSTALL.md`, `DESIGN_supply_chain.md`, `RELEASING.md`, `README.md`, `image-vulnerability-scan.md`, `CHANGELOG.md`. Merging it fires `publish.yml` (paths include the script and the workflow), which is the first signed image. No `charts/` change.
3. **A3** — `prepare-release.py`, `test_prepare_release.py`, `RELEASING.md`, `local-development/README.md`, `CHANGELOG.md`. The next real release then converts `## Unreleased`.

## Questions only the operator can answer

- **Q1 (A1):** make `Browser tests (Playwright, Chromium)` a required check under branch protection after a week of green runs? (a Settings change, not a repository file).
- **Q2 (A2):** which cosign major do consumers run? The workflow signs with cosign 3.1.3 in its default bundle layout and proves the round trip against Quay in-run; if a consumer population on cosign 2.x must verify, `cosign sign --new-bundle-format=false` is the one-flag change and the install guide would say "cosign 2.x or newer".
- **Q3 (A2):** is a public Rekor entry per push acceptable? It names the repository, the workflow file and the digest — nothing else — and is the property that makes keyless verifiable offline.
- **Q4 (A2):** should the quay robot account's token be scoped to allow pushing referrer artifacts (`sha256-<digest>.sig` / `.att` tags)? A write-scoped robot already can; a tag-restricted one would fail the sign step visibly.

### Critical Files for Implementation

- `/Users/olasumbo/gitRepos/group-sync-dashboard/.github/workflows/ci.yml`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/.github/workflows/publish.yml`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/.github/workflows/helm.yaml`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/build-and-push-external.sh`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/prepare-release.py` (new; conventions it edits live in `/Users/olasumbo/gitRepos/group-sync-dashboard/charts/group-sync-dashboard/Chart.yaml` and `/Users/olasumbo/gitRepos/group-sync-dashboard/docs/CHANGELOG.md`)
