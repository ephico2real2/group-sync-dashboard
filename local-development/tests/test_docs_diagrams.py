"""Mermaid diagrams in the docs must actually render.

One did not, for an unknown length of time. `docs/reference-architecture.md` §3 "How a poll
flows" contained:

    Note over T: stand by; re-check in 5s,<br/>not one poll interval

and `;` is a STATEMENT SEPARATOR in mermaid, so it terminated the Note and everything after it
was a parse error. GitHub renders that as an error box where the diagram should be. Nothing in
this repository noticed — it was found by a human looking at the page, which is the worst way to
find it, because a diagram nobody looks at stays broken indefinitely.

WHAT THIS FILE IS, AND IS NOT. It is not a mermaid parser; writing one to catch a class of bug
would be worse than the bug. It checks the specific constructs that are known to break a
render, each one because it actually did or was one edit away from doing so. The ground truth is
a real render, which is a browser away and belongs in CI:

    npx @mermaid-js/mermaid-cli@11 -i diagram.mmd -o out.svg

All nine diagrams were verified that way when this file was written.
"""

from __future__ import annotations

import pathlib
import re

import pytest

REPO = pathlib.Path(__file__).resolve().parents[2]

# Skip vendored and tool directories — third-party markdown is not ours to fix.
SKIP = (".venv", "node_modules", ".agents", ".claude", "vendor", ".git")


def _markdown() -> list[pathlib.Path]:
    return [p for p in sorted(REPO.rglob("*.md"))
            if not any(s in p.parts for s in SKIP)]


def _blocks() -> list[tuple[pathlib.Path, int, str]]:
    """Every mermaid block, with the 1-indexed line its content starts on."""
    out = []
    for md in _markdown():
        lines = md.read_text().split("\n")
        start = None
        for i, line in enumerate(lines):
            if line.strip() == "```mermaid":
                start = i + 1
            elif start is not None and line.strip().startswith("```"):
                out.append((md, start + 1, "\n".join(lines[start:i])))
                start = None
    return out


BLOCKS = _blocks()


def _strip_quoted(line: str) -> str:
    """Blank out "..." spans, so a check applies to mermaid syntax and not to label text."""
    return re.sub(r'"[^"]*"', '""', line)


def test_there_are_diagrams_to_check():
    """A silent zero would make every test below pass vacuously.

    The blocks are found by scanning for fences, so a change to how they are written would
    quietly reduce this suite to nothing — which is the failure mode this whole file exists to
    prevent, applied to itself.
    """
    assert len(BLOCKS) >= 9, f"only found {len(BLOCKS)} mermaid blocks; expected at least 9"


@pytest.mark.parametrize("md,start,body", BLOCKS,
                         ids=[f"{p.name}:{n}" for p, n, _ in BLOCKS])
def test_no_semicolon_outside_a_quoted_label(md, start, body):
    """`;` separates statements. Inside "..." it is text; bare, it truncates the line.

    This is the one that shipped broken. Note the asymmetry — the same character is harmless in
    a flowchart label and fatal in a `Note over X:` — which is why the check strips quoted
    spans instead of banning the character.
    """
    offenders = [
        (start + i, line.strip())
        for i, line in enumerate(body.split("\n"))
        if ";" in _strip_quoted(line)
    ]
    assert not offenders, (
        f"{md.name}: `;` outside a quoted label truncates the statement:\n" +
        "\n".join(f"  line {n}: {text}" for n, text in offenders) +
        "\n  Use an em dash or a comma."
    )


@pytest.mark.parametrize("md,start,body", BLOCKS,
                         ids=[f"{p.name}:{n}" for p, n, _ in BLOCKS])
def test_no_angle_brackets_but_line_breaks(md, start, body):
    """Mermaid passes label text through as HTML, so `<why>` is an unknown tag.

    It disappears silently rather than erroring, which is worse than a parse failure: the
    diagram renders, and the word the reader needed is simply absent. `<br/>` and `<br>` are
    the intended exceptions.
    """
    pattern = re.compile(r"<(?!/?br\s*/?>)[^>]*>")
    offenders = [
        (start + i, m.group(0), line.strip())
        for i, line in enumerate(body.split("\n"))
        for m in pattern.finditer(line)
    ]
    assert not offenders, (
        f"{md.name}: HTML-looking text in a label is dropped by the renderer:\n" +
        "\n".join(f"  line {n}: {tag!r} in {text[:70]}" for n, tag, text in offenders)
    )


@pytest.mark.parametrize("md,start,body", BLOCKS,
                         ids=[f"{p.name}:{n}" for p, n, _ in BLOCKS])
def test_quotes_are_balanced(md, start, body):
    """An unclosed quote swallows the rest of the diagram into one label."""
    offenders = [
        (start + i, line.strip())
        for i, line in enumerate(body.split("\n"))
        if line.count('"') % 2
    ]
    assert not offenders, (
        f"{md.name}: odd number of double quotes:\n" +
        "\n".join(f"  line {n}: {text}" for n, text in offenders)
    )


@pytest.mark.parametrize("md,start,body", BLOCKS,
                         ids=[f"{p.name}:{n}" for p, n, _ in BLOCKS])
def test_no_style_directive_on_a_subgraph(md, start, body):
    """`style <subgraph> ...` is version-dependent, and GitHub pins its own mermaid.

    Removed from a diagram here for that reason. A node style is fine; a subgraph style renders
    on one version and fails the whole diagram on another, and the repository cannot control
    which one the reader has.
    """
    subgraphs = set(re.findall(r"^\s*subgraph\s+(\w+)", body, re.M))
    offenders = [
        (start + i, line.strip())
        for i, line in enumerate(body.split("\n"))
        if (m := re.match(r"\s*style\s+(\w+)", line)) and m.group(1) in subgraphs
    ]
    assert not offenders, (
        f"{md.name}: style applied to a subgraph:\n" +
        "\n".join(f"  line {n}: {text}" for n, text in offenders) +
        "\n  Style the nodes, or leave the subgraph unstyled."
    )


@pytest.mark.parametrize("md", _markdown(), ids=lambda p: p.name)
def test_every_fence_is_closed(md):
    """An unclosed ```mermaid fence renders the rest of the document as a code block."""
    text = md.read_text()
    assert text.count("\n```") % 2 == 0 or text.count("```") % 2 == 0, (
        f"{md.name} has an odd number of code fences"
    )
