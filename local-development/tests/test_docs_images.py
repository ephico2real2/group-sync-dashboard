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


def test_a_figure_s_alt_text_does_not_call_proposed_what_its_page_shows_built():
    """A re-rendered figure and its alt text agree on what is proposed.

    The remote-cluster-access figures were re-rendered from a page that shows Rejoin, clusterAdminSar and D8 as built
    (#316, #322), while Figure 4's alt text still called them proposed: a screen reader heard the old figure.
    """
    import html
    page = (REPO / "docs/diagrams/remote-cluster-access/source.html").read_text()
    labels = [html.unescape(m) for m in re.findall(r'class="fig-scroll">\s*<svg[^>]*aria-label="([^"]*)"', page)]
    names = ["policies-who-decides", "inherit-vs-remote-sar-outcomes", "remote-sar-decision-flow", "joining-a-cluster"]
    assert len(labels) == len(names)
    doc = (REPO / "docs/design/DESIGN_remote_cluster_access.md").read_text()
    alts = re.findall(r'<img alt="([^"]*)" src="\.\./diagrams/remote-cluster-access/([a-z-]+)\.light\.png"', doc)
    assert len(alts) == len(names)
    stale = [name for alt, name in alts if "proposed" in alt and "proposed" not in labels[names.index(name)]]
    assert not stale, f"alt text calls proposed what the figure shows built: {stale}"
