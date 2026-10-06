"""Every image a document shows resolves to a file in the repository.

The citation test reads backticked paths only, so an image path that broke when its document moved went unnoticed:
#616 moved `DESIGN_remote_cluster_access.md` into `docs/design/` and updated its `<img src>` paths, but not the
`<source srcset>` beside them, and a browser that finds `srcset` uses it, so readers saw broken figures. This holds
every relative `src`, `srcset` and Markdown image in the documents readers open.

Not scanned: `docs/specs/` (a spec's text is placed into other files by its implementation blocks, so its relative
paths are relative to where it lands), `docs/reviews/` and `docs/history/` (records, which quote examples), and
`reports/` (evidence folders, which carry their own images).
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
SKIP = ("docs/specs/", "docs/reviews/", "docs/history/", "reports/")
IMAGE = re.compile(r'(?:srcset|src)="([^"]+?\.(?:png|svg|jpe?g|gif))"|!\[[^\]]*\]\(([^)\s]+?\.(?:png|svg|jpe?g|gif))\)')


def _documents() -> list[pathlib.Path]:
    out = []
    for md in sorted(REPO.rglob("*.md")):
        rel = md.relative_to(REPO).as_posix()
        if rel.startswith(SKIP) or any(part in {"node_modules", ".venv", ".git", ".agents"} for part in md.parts):
            continue
        out.append(md)
    return out


def test_every_image_a_document_shows_resolves():
    unresolved = []
    for md in _documents():
        for match in IMAGE.finditer(md.read_text(errors="ignore")):
            ref = match.group(1) or match.group(2)
            if ref.startswith(("http://", "https://", "data:")):
                continue
            if not (md.parent / ref).resolve().is_file():
                unresolved.append(f"{md.relative_to(REPO)}: {ref}")
    assert not unresolved, "images that resolve to no file:\n" + "\n".join(unresolved)


def test_the_scan_sees_the_figures_it_exists_for():
    """Not vacuous: the design document's figures are found and counted."""
    text = (REPO / "docs/design/DESIGN_remote_cluster_access.md").read_text()
    assert len([m for m in IMAGE.finditer(text)]) >= 12
