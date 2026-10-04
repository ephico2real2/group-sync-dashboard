"""Keep the README navigation and install guide's signer requirement tied to the tree."""

import re
from pathlib import Path


REPO = Path(__file__).resolve().parents[2]


def test_readme_tabs_match_rendered_navigation():
    page = (REPO / "local-development/gsd/static/index.html").read_text()
    rendered = re.findall(r'\btab\("[^"]+", "([^"]+)"\)', page)
    readme = (REPO / "README.md").read_text()
    section = readme.split("## What it shows\n", 1)[1].split("\n## ", 1)[0]
    documented = re.findall(r"^\*\*([^*]+)\*\* —", section, re.MULTILINE)
    assert rendered, "No tab calls found in index.html"
    assert documented == rendered


def test_install_guide_minimum_cosign_version_matches_signer():
    workflow = (REPO / ".github/workflows/publish.yml").read_text()
    pin = re.search(r"^\s*cosign-release: (v(\d+)\.\d+\.\d+)\s*$", workflow, re.MULTILINE)
    assert pin, "No cosign-release pin found in publish.yml"
    guide = (REPO / "docs/HELM_DOWNLOAD_AND_INSTALL.md").read_text()
    section = guide.split("## 7. Verify what you downloaded\n", 1)[1].split("\n## ", 1)[0]
    assert f"Minimum cosign version: **v{pin[2]}**." in section
    assert f"`cosign-release: {pin[1]}`" in section
