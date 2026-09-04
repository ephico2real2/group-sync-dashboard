"""Every `file.py#anchor` citation in the docs must resolve to something that still exists.

These docs cite the code heavily and deliberately — the reasoning for a decision lives next to
the code that implements it, and a reader is expected to follow the reference. That makes the
citations load-bearing.

WHY ANCHORS AND NOT LINE NUMBERS. Every citation used to be `path:123`. Line numbers rot on any
edit ABOVE the line, which is most edits, and the previous version of this file could only check
that the line still existed — not that it still said the same thing. That gap was not
theoretical:

    gsd/api.py:487-489     -> the comment it cited had moved to 615-617
    gsd/store.py:1156-1159 -> the rationale it cited had moved to 1197-1200

Both pointed at real lines, so both passed, while pointing at unrelated code. A four-line comment
added to the top of `templates/rbac.yaml` invalidated eleven citations across four documents in
one edit, and they were repaired by hand twice in one day before this was automated.

An anchor is a NAME, so it moves with the thing it names:

    `gsd/store.py#Store.groups`                     a def or class, resolved through the AST
    `gsd/store.py#_FINDING_CASE`                    a module-level constant
    `charts/.../templates/rbac.yaml#leases`         any file: a substring that must be present
    `gsd/config.py`                                 no anchor: the whole file is the subject

WHAT THIS STILL CANNOT DO. It proves the anchor exists, not that the prose around the citation
describes it correctly. Renaming a function and updating the docs is now enforced; rewriting what
a function does and leaving the prose stale is not, and no static check will catch that. The
guarantee is narrower than "the docs are right" — it is "the docs do not point at nothing", which
is exactly the failure that kept recurring.

SPECIFICATIONS ARE THE ONE EXCEPTION, AND A NARROW ONE. A file under `docs/specs/` describes code
that does not exist yet — the complete code is in the spec, and the spec is what the implementation
is applied from — so it cites names its own code creates (`gsd/store.py#Store.prune_sync_events`
before that method is written). Such a citation passes only if the specs themselves introduce the
anchor: for a Python target, a name the Python code blocks of some spec DEFINE (parsed, not
searched — see `_spec_definitions`) or literal text inside one of those code blocks; for any other
target, the anchor text in some spec outside the citation spans. Once the feature ships the anchor
exists in the cited file too and the ordinary rule takes over. A spec citing a name that neither
the code nor any spec introduces is a design error, and fails like any other broken citation —
which is how four wrong citations in the designs were found.
"""

from __future__ import annotations

import ast
import functools
import pathlib
import re
import textwrap

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SKIP = (".venv", "node_modules", ".agents", ".claude", "vendor", ".git", "deploy")

# `path#anchor`, or a bare `path`. The extension list is closed on purpose: an open pattern
# matches version strings, times and `localhost:8080`. The anchor runs to the end of the
# backtick-quoted span, so it may contain spaces and punctuation — some of the most stable
# anchors in Helm templates are a phrase from the comment they label.
CITATION = re.compile(
    r"`([\w./-]+\.(?:py|yaml|yml|tpl|sh|html|js|css|toml|md))"   # path
    r"(?:#([^`]+))?`"                                            # optional #anchor
)

# The form this file exists to eliminate. Kept as an explicit check so it cannot creep back in
# one citation at a time.
LINE_NUMBER_CITATION = re.compile(
    r"`([\w./-]+\.(?:py|yaml|yml|tpl|sh|html|js|css|toml|md)):(\d+)(?:-\d+)?`"
)


# Point-in-time REVIEW ARTIFACTS, exempt from the citation rules on purpose.
#
# The rest of the docs describe the code as it IS, so a line-number citation there rots and the rule
# that forbids them is right. A review document describes the code as it WAS at review time, and its
# findings quote the exact lines they are about — rewriting those to symbol names as the code changes
# would falsify the record of what was reviewed. These files are historical once written.
REVIEW_ARTIFACTS = (
    # The chart/app release-decoupling design. A review record: its findings quote the exact
    # workflow steps, values lines and helper expressions they would replace, and the claims are
    # about spans of code at a moment — which is what the line-number exemption is for.
    "DESIGN_decouple_chart_and_app_release.md",
    # The tier-constants / `settling`-name debt review. Two claimed behaviour-PRESERVING
    # changes, which is why they earn a pass at all: the brief asks reviewers to prove identity,
    # not taste, and their verdicts quote the exact comparison sites and the DEBUG line's
    # arithmetic. Symbol names would not distinguish "this `"all"` is a tier" from "this `"all"`
    # is the operator's chart value", which is the whole question.
    "REVIEW_tier_constants_and_settling_name.md",
    "OAUTH_LOGLEVEL_REVIEW.md",
    # The PR #12 adversarial review. Its findings quote the exact lines they are about, which is
    # the point of a review record and precisely what the line-number rule forbids elsewhere.
    "REVIEW_login_capture_pr12.md",
    # The admin-tier gating review (feat/per-user-visibility). Same reason: its findings cite the
    # exact api.py / test lines they refuse or replace, so line numbers are the record, not rot.
    "REVIEW_admin_tier_gating.md",
    # The inert-code and vacuous-assertion audit. Its findings are line-anchored by necessity —
    # "this branch has no test" and "this constant is read by nothing" are claims ABOUT a
    # location, and the mutation that proves each one names the line it changed. Rewriting those
    # to symbol names would erase the evidence rather than keep it fresh.
    "AUDIT_visibility_premise_and_assumptions.md",
    # The post-merge pass over the visibility tier, admin gating, metrics and the publish pin
    # (two reviewers, one brief). The brief's claim table cites the ranges each claim was ABOUT,
    # which is what made the verdicts checkable — "V2: is gating these two endpoints the complete
    # surface?" is a question about a span of code at a moment. The pair is listed separately
    # because the verdicts live in the brief and the second reviewer's findings in its own file.
    "REVIEW_post_merge_visibility_metrics.md",
    "REVIEW_post_merge_cursor.md",
    "REVIEW_route_exposure.md",
    "REVIEW_users_tab_logins.md",
    "REVIEW_access_granted_reach.md",
    "REVIEW_second_pass_2026-09-04.md",
    "REVIEW_hardened_image.md",
    # The PR #69 specifications review. It quotes the wrong anchors the reviewers' probes used,
    # deliberately — an anchor that MUST fail is the record.
    "REVIEW_feature_specs.md",
    # The PR #70 (A1) review; its findings quote the workflow and test lines they are about.
    "REVIEW_A1.md",
    "REVIEW_A3.md",
    # The log-level contract review. Same reason, plus a worked example of why the exemption is
    # right: it cites `README.md#Configuration`, a heading that does not exist — and the finding
    # attached to that citation was correct and was applied. Rewriting the citation would not make
    # the record truer, and refusing the record over it would have cost a real finding.
    "REVIEW_log_level_contract.md",
)


def _markdown() -> list[pathlib.Path]:
    return [p for p in sorted(REPO.rglob("*.md"))
            if not any(s in p.parts for s in SKIP)
            and p.name not in REVIEW_ARTIFACTS]


def _index() -> dict[str, list[pathlib.Path]]:
    index: dict[str, list[pathlib.Path]] = {}
    for p in REPO.rglob("*"):
        if p.is_file() and not any(s in p.parts for s in SKIP):
            index.setdefault(p.name, []).append(p)
    return index


INDEX = _index()


def _resolve(cited: str) -> pathlib.Path | None:
    """Resolve a cited path, accepting the shorthand the docs actually use.

    Docs cite `poller.py` and `charts/group-sync-dashboard/values.yaml` interchangeably.
    Exact-from-root wins, then a unique suffix match, then a unique basename. An ambiguous
    basename (README.md exists five times) resolves to None and is reported rather than guessed
    at, because guessing invents a pass or a failure.
    """
    direct = REPO / cited
    if direct.is_file():
        return direct

    candidates = INDEX.get(pathlib.PurePath(cited).name, [])
    if len(cited.split("/")) > 1:
        suffixed = [c for c in candidates if str(c).endswith(cited)]
        if len(suffixed) == 1:
            return suffixed[0]
    return candidates[0] if len(candidates) == 1 else None


def _python_symbols(path: pathlib.Path) -> set[str]:
    """Every def/class (bare and `Class.method`) plus module-level assignments."""
    try:
        tree = ast.parse(path.read_text())
    except SyntaxError:
        return set()

    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names.update(t.id for t in node.targets if isinstance(t, ast.Name))
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)

    # Qualified method names, so `Store.groups` is citable and unambiguous in a file where
    # several classes define `groups`.
    for cls in (n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)):
        for child in cls.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                names.add(f"{cls.name}.{child.name}")
            elif isinstance(child, ast.Assign):
                names.update(f"{cls.name}.{t.id}" for t in child.targets
                             if isinstance(t, ast.Name))
    return names


# Fences at LINE START only: the specs quote triple backticks inside sentences, and an unanchored
# pattern paired one of those with a real fence and swallowed a page of prose as "code".
PYTHON_FENCE = re.compile(r"^```(?:python|py)\n(.*?)^```", re.S | re.M)
DEFINITION_LINE = re.compile(r"^\s*(?:def\s+(\w+)\s*\(|class\s+(\w+)\b|(\w+)\s*(?::[^=\n]+)?=(?!=))", re.M)


@functools.lru_cache(maxsize=None)
def _spec_definitions(spec: pathlib.Path) -> frozenset[str]:
    """Every name the Python code blocks of one spec DEFINE: defs, classes, class members and
    module-level assignments, as `name` and, inside a class, `Class.name` too.

    Parsed, not searched: a substring rule ("`name = ` appears somewhere") let a made-up
    `Store.name` pass on the strength of an unrelated assignment in another spec's prose. A spec
    quotes methods as an indented fragment without the `class` line, so each block is dedented
    before parsing and a member is also recorded bare; a block that is not parseable Python (a
    snippet with a prose line in it) defines nothing, which can only fail a citation, never pass
    one. Local variables inside function bodies are not definitions and are not collected.
    """
    names: set[str] = set()

    def collect(node: ast.AST, prefix: str) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.update({node.name, prefix + node.name})
        elif isinstance(node, ast.ClassDef):
            names.update({node.name, prefix + node.name})
            for child in node.body:
                collect(child, node.name + ".")
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    names.update({t.id, prefix + t.id})
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.update({node.target.id, prefix + node.target.id})

    for block in PYTHON_FENCE.findall(spec.read_text()):
        try:
            tree = ast.parse(textwrap.dedent(block))
        except SyntaxError:
            # A fragment that starts inside one method and goes on to whole methods has two
            # indentation levels and no single dedent makes it parse. Take the definition
            # forms at line start — `def name(`, `class name`, `name = ` — and nothing else.
            names.update(n for groups in DEFINITION_LINE.findall(block) for n in groups if n)
            continue
        for node in tree.body:
            collect(node, "")
    return frozenset(names)


ANY_FENCE = re.compile(r"^```[^\n]*\n(.*?)^```", re.S | re.M)


def _spec_introduces(md: pathlib.Path, cited: pathlib.Path, anchor: str) -> bool:
    """True when `md` is a spec under docs/specs and the specs' own CODE introduces `anchor`.

    Every spec in the programme is searched, not only the citing one: the specs ship in a fixed
    order and a later one may cite what an earlier one creates (the backup runbook in the B1 spec
    cites the retention methods the B2 spec introduces). Code, never prose: a spec's prose is full
    of plausible names and phrases, and the first version of this rule certified a made-up anchor
    on the strength of a heading in an unrelated spec. So —

    * a Python target: the anchor must be a name some spec's Python code DEFINES
      (`_spec_definitions`), or literal text inside one of those Python blocks (an index name in
      the schema, a log message). A qualified name matched by its bare member (a fragment quoted
      without the class line) must also have its class defined by the cited file or by a spec,
      so `Bogus.group_count_changes` cannot ride on B4's `def group_count_changes(`;
    * any other target: the anchor is literal text, and it must appear inside a fenced code
      block of some spec — the new file or the edit that will carry it — never in a sentence.

    A trailing backslash is stripped: a spec that quotes a doc edit inside a backtick span escapes
    the inner backticks as \\` and the anchor regex, which runs to the next backtick, captures
    the escape.
    """
    if "specs" not in md.relative_to(REPO).parts:
        return False
    needle = anchor.rstrip("\\")
    specs = sorted(md.parent.glob("SPEC_*.md"))
    if cited.suffix == ".py":
        defined = frozenset().union(*(_spec_definitions(spec) for spec in specs))
        if needle in defined:
            return True
        if "." in needle:
            cls, _, member = needle.rpartition(".")
            if member in defined and (cls in defined or cls in _python_symbols(cited)):
                return True
        return any(needle in block
                   for spec in specs for block in PYTHON_FENCE.findall(spec.read_text()))
    return any(needle in block for spec in specs for block in ANY_FENCE.findall(spec.read_text()))


def _citations() -> list[tuple[pathlib.Path, int, str, str | None]]:
    out = []
    for md in _markdown():
        for i, line in enumerate(md.read_text().split("\n"), start=1):
            for m in CITATION.finditer(line):
                out.append((md, i, m.group(1), m.group(2)))
    return out


CITATIONS = _citations()
ANCHORED = [c for c in CITATIONS if c[3]]


def test_there_are_citations_to_check():
    """A regex that stops matching would reduce this whole file to a silent pass.

    The same guard as test_docs_diagrams.py, for the same reason: this suite is built on scanning
    for a pattern, so the pattern failing to match is indistinguishable from everything being
    correct unless something asserts the count.
    """
    assert len(CITATIONS) >= 150, (
        f"only found {len(CITATIONS)} citations; the docs carry far more, so the pattern has "
        f"probably stopped matching"
    )
    assert len(ANCHORED) >= 100, (
        f"only {len(ANCHORED)} citations carry an anchor; the conversion away from line numbers "
        f"has probably been reverted"
    )


def test_no_citation_uses_a_line_number():
    """Line numbers are the format this file exists to replace.

    Not style policing. A line number is correct only until someone edits above it, and the check
    that it still points at the right thing cannot be automated — which is how two citations in
    one paragraph came to point at unrelated code while the suite stayed green.
    """
    offenders = [
        f"{md.relative_to(REPO)}:{n} -> {m.group(0)}"
        for md in _markdown()
        for n, line in enumerate(md.read_text().split("\n"), start=1)
        for m in [LINE_NUMBER_CITATION.search(line)] if m
    ]
    assert not offenders, (
        "these citations use a line number; cite a name instead so the reference moves with the "
        "code:\n  " + "\n  ".join(offenders)
    )


def test_most_citations_resolve_to_a_file():
    """Guards the resolver, not the docs.

    If `_resolve` broke, every citation would return None, every check below would skip, and this
    suite would pass while verifying nothing.
    """
    unresolved = [(md.name, n, path) for md, n, path, _ in CITATIONS if _resolve(path) is None]
    ratio = 1 - len(unresolved) / len(CITATIONS)
    assert ratio > 0.9, (
        f"only {ratio:.0%} of {len(CITATIONS)} citations resolve to a file — the resolver is "
        f"probably broken rather than the docs being that wrong. Sample: {unresolved[:10]}"
    )


@pytest.mark.parametrize(
    "md,doc_line,cited,anchor",
    ANCHORED,
    ids=[f"{md.name}:{n}->{path}#{a}" for md, n, path, a in ANCHORED],
)
def test_the_anchor_exists_in_the_cited_file(md, doc_line, cited, anchor):
    target = _resolve(cited)
    if target is None:
        pytest.skip(f"{cited} does not resolve to exactly one file")

    where = f"{md.relative_to(REPO)}:{doc_line} cites {cited}#{anchor}"

    if target.suffix == ".py":
        # Through the AST, so `Store.groups` resolves even though that exact string never appears
        # in the file. A substring search would demand the docs write `def groups` instead.
        symbols = _python_symbols(target)
        if anchor in symbols or _spec_introduces(md, target, anchor):
            return
        # Some Python anchors name a string inside the file rather than a symbol — a log message
        # or a SQL fragment. Allow that, but only after the symbol lookup fails, so a typo'd
        # symbol name is not silently accepted because it happens to appear in a comment.
        assert anchor in target.read_text(), (
            f"{where} — no such def, class or module-level name in "
            f"{target.relative_to(REPO)}, and the text does not appear either. Closest: "
            f"{sorted(s for s in symbols if anchor.split('.')[-1].lower() in s.lower())[:5]}"
        )
        return

    assert anchor in target.read_text() or _spec_introduces(md, target, anchor), (
        f"{where} — that text is not in {target.relative_to(REPO)}. If the code was renamed, "
        f"update the citation; if it was deleted, the claim around it probably needs rewriting "
        f"too."
    )
