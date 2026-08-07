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
"""

from __future__ import annotations

import ast
import pathlib
import re

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
    "OAUTH_LOGLEVEL_REVIEW.md",
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
        if anchor in symbols:
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

    assert anchor in target.read_text(), (
        f"{where} — that text is not in {target.relative_to(REPO)}. If the code was renamed, "
        f"update the citation; if it was deleted, the claim around it probably needs rewriting "
        f"too."
    )
