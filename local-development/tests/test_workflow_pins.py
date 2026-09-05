"""Every third-party action is pinned by the full commit of a release, with the version beside it.

The rule is stated at the top of ci.yml and it is the form Dependabot moves. It was stated and not
held: helm.yaml carried `helm/chart-releaser-action@v1.7.0` — a mutable major-minor tag — while
the note said every action was pinned. A tag's owner can move a tag; a green run under a moved
tag proves whatever the tag now points at.

Text, not YAML: the version comment lives beside the `uses:` value on the same line, and a parser
drops comments.
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOWS = sorted((REPO / ".github" / "workflows").glob("*.y*ml"))

USES = re.compile(r"^\s*(?:-\s+)?uses:\s*(\S+)\s*(#.*)?$")


def _uses() -> list[tuple[str, int, str, str]]:
    out = []
    for wf in WORKFLOWS:
        for n, line in enumerate(wf.read_text().splitlines(), start=1):
            if line.strip().startswith("#"):
                continue
            m = USES.match(line)
            if m:
                out.append((wf.name, n, m.group(1), m.group(2) or ""))
    return out


def test_there_are_actions_to_check() -> None:
    assert len(_uses()) >= 20, "the `uses:` pattern has probably stopped matching"


def test_every_third_party_action_is_pinned_to_a_full_commit_with_its_version() -> None:
    offenders = []
    for wf, n, ref, comment in _uses():
        if ref.startswith("./"):
            continue  # a reusable workflow in this repository moves with the commit under test
        name, _, sha = ref.partition("@")
        if not re.fullmatch(r"[0-9a-f]{40}", sha):
            offenders.append(f"{wf}:{n} {ref} — not a 40-hex commit")
        elif not re.search(r"#\s*v\d", comment):
            offenders.append(f"{wf}:{n} {ref} — no `# vX.Y.Z` comment beside it")
    assert not offenders, "unpinned or uncommented actions:\n  " + "\n  ".join(offenders)


# ── helm.yaml's version extractors ──────────────────────────────────────────────────────────────
#
# Routed here from the A3 review (PR #71, Codex C4): the two `sed` patterns that read Chart.yaml in
# helm.yaml's image-label step accept exactly the forms prepare-release.py writes and
# build-and-push-external.sh accepts — a bare three-part semver, and a double-quoted appVersion with
# nothing after the closing quote. Held by running the real patterns, lifted from the real file,
# through sed against the forms they must accept and refuse.

import shlex
import subprocess

HELM = REPO / ".github" / "workflows" / "helm.yaml"


def _sed_pattern(var: str) -> str:
    line = next(ln for ln in HELM.read_text().splitlines() if ln.strip().startswith(f"{var}=$(sed -n "))
    return shlex.split(line.split("$(", 1)[1])[2]  # sed -n '<pattern>' "$CHART" | head -1


def _sed(pattern: str, text: str) -> str:
    return subprocess.run(["sed", "-n", pattern], input=text, capture_output=True, text=True, check=True).stdout.strip()


def test_the_chart_version_extractor_accepts_only_a_bare_three_part_semver() -> None:
    pat = _sed_pattern("CHART_VERSION")
    assert _sed(pat, "version: 0.16.0\n") == "0.16.0"
    assert _sed(pat, "version: 0.16.0  \n") == "0.16.0", "trailing blanks are tolerated, as the script tolerates them"
    for bad in ("version: 0.16\n", "version: 0.16.0-rc1\n", "version: v0.16.0\n", "version: 0.16.0.1\n", 'version: "0.16.0"\n'):
        assert _sed(pat, bad) == "", bad


def test_the_app_version_extractor_accepts_only_a_quoted_value_with_nothing_after_it() -> None:
    pat = _sed_pattern("APP_VERSION")
    assert _sed(pat, 'appVersion: "0.15.0"\n') == "0.15.0"
    for bad in ("appVersion: 0.15.0\n", 'appVersion: ""\n', 'appVersion: "0.15.0" \n', "appVersion: '0.15.0'\n"):
        assert _sed(pat, bad) == "", bad
