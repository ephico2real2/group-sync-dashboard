"""The docs index names every page outside the development filename conventions.

Issue #319: operator guides were buried among review records with no audience index.
Development records with other names also need individual links so they stay discoverable.
"""
from __future__ import annotations

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
CHART_DOCS = DOCS.parent / "charts" / "group-sync-dashboard" / "docs"
DEVELOPMENT_PREFIXES = ("REVIEW_", "SPEC_", "DESIGN_", "BENCHMARK_", "VALIDATION_")


def _targets(index: Path = DOCS / "README.md") -> set[Path]:
    assert index.is_file(), f"{index} must index the pages beside it"
    return {
        (index.parent / target.split("#", 1)[0]).resolve()
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", index.read_text())
    }


def _named(pages) -> list[Path]:
    return [p for p in pages if p.name != "README.md" and not p.name.startswith(DEVELOPMENT_PREFIXES)]


def test_every_page_outside_development_conventions_is_linked() -> None:
    targets = _targets()
    # The pages that sat at the top of docs/ before the regrouping keep their link from this index.
    pages = _named([*DOCS.glob("*.md"), *DOCS.glob("research/*.md"), *DOCS.glob("history/*.md"),
                    *CHART_DOCS.glob("*.md")])
    pages.extend((DOCS / "guides").rglob("*.md"))
    # design/ has its own index, so a page there may be found from either.
    in_either = targets | _targets(DOCS / "design" / "README.md")
    missing = sorted(str(p.relative_to(DOCS.parent)) for p in pages if p.resolve() not in targets)
    missing += sorted(str(p.relative_to(DOCS.parent)) for p in _named(DOCS.glob("design/*.md"))
                      if p.resolve() not in in_either)
    assert not missing, f"pages with no link in docs/README.md: {missing}"


def test_every_link_in_the_index_resolves() -> None:
    # A deleted or moved page leaves a dead entry that the check above cannot see.
    dead = sorted(str(target) for target in _targets() if not target.exists())
    assert not dead, f"docs/README.md links pages that do not exist: {dead}"
