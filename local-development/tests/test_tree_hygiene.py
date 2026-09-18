"""The tree carries no unfinished merge.

A `<<<<<<<` / `>>>>>>>` pair survived a conflict resolution once (cf4f310, `docs/CHANGELOG.md`, found
by the review of #167 — Grok F1): the merge left both sides in the file under their markers, nothing
read the file afterwards, and the branch was pushed. Every tracked text file is scanned, so a marker
in a chart template or a test is caught the same way. Tracked means `git ls-files`, the one definition
that matches what a PR carries.
"""
from __future__ import annotations

import pathlib
import subprocess

REPO = pathlib.Path(__file__).resolve().parents[2]
MARKERS = ("<<<<<<< ", ">>>>>>> ")


def marker_lines(text: str) -> list[int]:
    """1-based lines that begin a conflict marker. `=======` alone is a Markdown setext underline
    and a table rule, so only the two seven-character markers with their trailing space count."""
    return [n for n, line in enumerate(text.splitlines(), 1) if line.startswith(MARKERS)]


def _tracked_files() -> list[pathlib.Path]:
    out = subprocess.run(["git", "-C", str(REPO), "ls-files", "-z"], check=True, capture_output=True).stdout
    return [REPO / p for p in out.decode().split("\0") if p]


def test_the_scan_sees_a_marker_at_the_start_of_a_line_and_not_inside_one():
    assert marker_lines("a\n<<<<<<< HEAD\nb\n=======\nc\n>>>>>>> theirs\n") == [2, 6]
    assert marker_lines("the pair <<<<<<< HEAD ... >>>>>>> theirs, quoted mid-line\n") == []


def test_no_tracked_file_carries_a_conflict_marker():
    hits = []
    for path in _tracked_files():
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue   # an image, a font, a wheel: nothing a merge writes markers into
        hits += [f"{path.relative_to(REPO)}:{n}" for n in marker_lines(text)]
    assert not hits, "unresolved merge markers: " + ", ".join(hits)
