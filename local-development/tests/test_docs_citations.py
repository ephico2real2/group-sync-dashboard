"""Every `file.py:123` citation in the docs must point inside the file it names.

These docs cite line numbers heavily and deliberately — the reasoning for a decision lives
next to the code that implements it, and a reader is expected to follow the reference. That
makes the citations load-bearing, and it makes them rot on every edit above the line they
point at.

Measured while removing the `annotate` write path: a four-line comment added to the top of
`templates/rbac.yaml` invalidated eleven citations across four documents in one edit, and
they were caught by hand, twice, in the same session. A citation pointing past the end of a
file is the cheap half of that problem and this file ends it.

WHAT THIS CANNOT DO. It checks that the target line EXISTS, not that it says what the prose
claims. A citation that slides from line 55 to line 61 and lands on a different rule still
passes. Ranges that resolve are therefore necessary, not sufficient, and a semantic drift
check would need stable anchors rather than line numbers — see the module docstring of
test_docs_diagrams.py for the same trade-off applied to mermaid.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]
SKIP = (".venv", "node_modules", ".agents", ".claude", "vendor", ".git", "deploy")

# `gsd/poller.py:318`, `rbac.yaml:35-53`, `charts/x/templates/y.yaml:12`. The extension list
# is closed on purpose: an open pattern matches version strings, times and `localhost:8080`.
CITATION = re.compile(
    r"\b([\w./-]+\.(?:py|yaml|yml|tpl|sh|html|js|css|toml|md))"   # path
    r":(\d+)(?:-(\d+))?\b"                                        # line, optional end
)


def _markdown() -> list[pathlib.Path]:
    return [p for p in sorted(REPO.rglob("*.md"))
            if not any(s in p.parts for s in SKIP)]


def _index() -> dict[str, list[pathlib.Path]]:
    """Basename -> every file with that name, so abbreviated citations can resolve."""
    index: dict[str, list[pathlib.Path]] = {}
    for p in REPO.rglob("*"):
        if p.is_file() and not any(s in p.parts for s in SKIP):
            index.setdefault(p.name, []).append(p)
    return index


INDEX = _index()


def _resolve(cited: str) -> pathlib.Path | None:
    """Resolve a cited path, accepting the shorthand the docs actually use.

    Docs cite `poller.py:318` and `charts/group-sync-dashboard/values.yaml:300`
    interchangeably. Exact-from-root wins; then a unique suffix match; then a unique
    basename. Ambiguous basenames (README.md exists five times) resolve to None and are
    reported rather than guessed at, because guessing would invent a pass or a failure.
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


def _citations() -> list[tuple[pathlib.Path, int, str, int, int | None]]:
    """(doc, doc_line, cited_path, start, end) for every citation in every markdown file."""
    out = []
    for md in _markdown():
        for i, line in enumerate(md.read_text().split("\n"), start=1):
            for m in CITATION.finditer(line):
                path, start, end = m.group(1), int(m.group(2)), m.group(3)
                out.append((md, i, path, start, int(end) if end else None))
    return out


CITATIONS = _citations()


def test_there_are_citations_to_check():
    """A regex that stops matching would reduce this whole file to a silent pass.

    The same guard as test_docs_diagrams.py, for the same reason: these suites are built on
    scanning for a pattern, so the pattern failing to match is indistinguishable from
    everything being correct unless something asserts the count.
    """
    assert len(CITATIONS) >= 150, (
        f"only found {len(CITATIONS)} citations; the docs carry far more, so the pattern "
        f"has probably stopped matching"
    )


def test_most_citations_resolve_to_a_file():
    """Guards the resolver, not the docs.

    If `_resolve` broke, every citation would return None, every range check below would skip,
    and this suite would pass while checking nothing.
    """
    unresolved = [(md.name, n, path) for md, n, path, _, _ in CITATIONS
                  if _resolve(path) is None]
    ratio = 1 - len(unresolved) / len(CITATIONS)
    assert ratio > 0.9, (
        f"only {ratio:.0%} of {len(CITATIONS)} citations resolve to a file — the resolver is "
        f"probably broken rather than the docs being that wrong. Sample: {unresolved[:10]}"
    )


@pytest.mark.parametrize(
    "md,doc_line,cited,start,end",
    CITATIONS,
    ids=[f"{md.name}:{n}->{path}:{start}" for md, n, path, start, _ in CITATIONS],
)
def test_the_cited_line_exists(md, doc_line, cited, start, end):
    target = _resolve(cited)
    if target is None:
        pytest.skip(f"{cited} does not resolve to exactly one file")

    total = len(target.read_text().split("\n"))
    where = f"{md.relative_to(REPO)}:{doc_line} cites {cited}:{start}"
    if end is not None:
        where += f"-{end}"

    assert start >= 1, f"{where} — line numbers start at 1"
    assert start <= total, (
        f"{where} but {target.relative_to(REPO)} has {total} lines. Something was deleted "
        f"above it, or the citation was never right."
    )
    if end is not None:
        assert end >= start, f"{where} — the range runs backwards"
        assert end <= total, (
            f"{where} but {target.relative_to(REPO)} has {total} lines. The range starts "
            f"inside the file and ends past the end of it."
        )
