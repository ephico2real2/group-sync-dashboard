"""The docs index names every page outside the development filename conventions.

Issue #319: operator guides were buried among review records with no audience index.
Development records with other names also need individual links so they stay discoverable.
"""
from __future__ import annotations

import re
from pathlib import Path

DOCS = Path(__file__).resolve().parents[2] / "docs"
DEVELOPMENT_PREFIXES = ("REVIEW_", "SPEC_", "DESIGN_", "BENCHMARK_", "VALIDATION_")


def test_every_page_outside_development_conventions_is_linked() -> None:
    index = DOCS / "README.md"
    assert index.is_file(), "docs/README.md must index operator guides and development records"
    targets = {
        (DOCS / target.split("#", 1)[0]).resolve()
        for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", index.read_text())
    }
    missing = sorted(
        page.name for page in DOCS.glob("*.md")
        if page.name != "README.md"
        and not page.name.startswith(DEVELOPMENT_PREFIXES)
        and page.resolve() not in targets
    )
    assert not missing, f"pages with no link in docs/README.md: {missing}"
