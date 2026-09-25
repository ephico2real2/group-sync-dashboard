"""Every line that decides or consumes "platform" carries the marker `PLATFORM-CLASSIFICATION (#255, #353)`
on itself or the line above, so `git grep PLATFORM-CLASSIFICATION` lists the whole logic end to end — the
operator's requirement (2026-09-24), so the classification can be reviewed as one path and cannot rot when a
new call appears somewhere unmarked. Spec: docs/specs/SPEC_U1_unmanaged_subjects.md, "The marked sites"."""
from __future__ import annotations

import pytest
import re
from pathlib import Path

MARKER = "PLATFORM-CLASSIFICATION (#255, #353)"
ROOT = Path(__file__).resolve().parents[2]
GSD = ROOT / "local-development" / "gsd"
# A decision or a consumption: the classifiers' definitions and defaults, and every call of them.
SITE = re.compile(
    # A call, or the bound method passed as an argument (Home passes `settings.platform_namespaces.matches`);
    # prose in a docstring ends the name with a backtick or a period, which neither form matches (Grok, #361).
    r"platform_namespaces\.(matches|unmatched)\s*[(,)]|\bplatform\.matches\s*\(|PlatformNamespaces\(\)\.matches\s*\("
    r"|\bis_platform_user\s*\(|\bis_platform_namespace\s*\("
    r"|PLATFORM_CONTROLLER_BINDINGS\b|^PLATFORM_(NAMESPACE_PREFIXES|NAMESPACES|USER_PREFIXES) ="
    r"|^def _platform_namespaces_setting\(|_platform_namespaces_setting\(raw\)|^\s+platform_namespaces: PlatformNamespaces = "
    # ... and the stored flag's SQL comparisons and Python assignments (OB1-lite, review of #361); a Python read
    # or a dict-literal write of the flag is marked by hand and not held here (OB2, second pass)
    r'|\bis_platform\s*=\s*[01]\b|\["is_platform"\]\s*=')
CHART_SITES = {
    ROOT / "charts/group-sync-dashboard/values.yaml": "platformNamespaces:",
    ROOT / "charts/group-sync-dashboard/templates/configmap.yaml": ".Values.platformNamespaces",
    ROOT / "charts/group-sync-dashboard/templates/_helpers.tpl": 'define "gsd.validatePlatformNamespaces"',
}


def _sites(path: Path) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("import ", "from ")) or not SITE.search(line):
            continue
        above = lines[i - 1] if i else ""
        if MARKER not in line and MARKER not in above:
            out.append((i + 1, line.strip()))
    return out


def test_every_python_site_that_decides_or_consumes_platform_is_marked() -> None:
    unmarked = {str(p.relative_to(ROOT)): _sites(p) for p in sorted(GSD.rglob("*.py")) if _sites(p)}
    assert unmarked == {}, f"unmarked platform-classification sites (add the marker on the line or the line above): {unmarked}"


def test_the_marked_python_path_is_complete() -> None:
    """The marker names every hop the spec lists: the classifiers, their settings, the direct-user path,
    and the finding path. A hop that loses its marker, or a file that drops out, fails here."""
    marked = {str(p.relative_to(ROOT)) for p in GSD.rglob("*.py") if MARKER in p.read_text(encoding="utf-8")}
    assert {"local-development/gsd/home.py", "local-development/gsd/config.py", "local-development/gsd/kube.py",
            "local-development/gsd/api.py", "local-development/gsd/poller.py", "local-development/gsd/store.py",
            "local-development/gsd/state.py", "local-development/gsd/reporting/snapshot.py"} <= marked, marked


def test_the_chart_path_is_marked() -> None:
    for path, needle in CHART_SITES.items():
        lines = path.read_text(encoding="utf-8").splitlines()
        hit = next(i for i, line in enumerate(lines) if needle in line)
        window = "\n".join(lines[max(0, hit - 3):hit + 1])
        assert MARKER in window, (str(path.relative_to(ROOT)), needle, window)

@pytest.mark.parametrize("line, is_site", [
    ('            row["platform"] = settings.platform_namespaces.matches(row["name"])', True),
    ("                                    platform=settings.platform_namespaces.matches),", True),
    ("        if platform.matches(b.subject_namespace):", True),
    ("    return PlatformNamespaces().matches(name)", True),
    ('    ok = is_platform_user ("kubeadmin")', True),
    ("                    WHERE cluster_id=? AND is_platform=0", True),
    ('                    r["is_platform"] = 1 if r["group_name"].startswith(SYSTEM_GROUP_PREFIX) else 0', True),
    ("    is_platform         INTEGER NOT NULL DEFAULT 0,", False),
    ('    """The shipped rule. Callers holding a `Settings` use `settings.platform_namespaces.matches`', False),
    ("from .config import PlatformNamespaces", False),
])
def test_the_site_pattern_sees_a_call_and_a_bound_method_pass_but_not_prose(line: str, is_site: bool) -> None:
    assert bool(SITE.search(line)) is is_site, line
