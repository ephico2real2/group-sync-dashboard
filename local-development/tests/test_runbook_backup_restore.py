"""docs/RUNBOOK_backup_restore.md, as #300 left it: §0 before every upgrade, §4 around recovery mode (#303) and
restore-db.sh (#302) with the manual paths as the fallback, and the section numbers the code cites.

The runbook is the procedure an operator follows at 03:00, so these read it as text: a heading renumbered or a
stale command left in place is a wrong instruction no other test sees. The store's refusals cite "§4" and "§6"
(gsd/store.py), a chart refusal cites "§5", and the chart README links "#6-pre-upgrade-copies".
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "docs" / "RUNBOOK_backup_restore.md"
TEXT = RUNBOOK.read_text()
HEADINGS = re.findall(r"^## (\d+)\. (.+)$", TEXT, re.M)


def section(number: str) -> str:
    """The body of `## <number>. …`, up to the next level-2 heading."""
    start = re.search(rf"^## {number}\. .+$", TEXT, re.M)
    assert start, f"no section {number}"
    end = re.search(r"^## ", TEXT[start.end():], re.M)
    return TEXT[start.end():start.end() + end.start()] if end else TEXT[start.end():]


def code_lines(text: str) -> list[str]:
    """Every line inside a fenced block, three backticks or four, stripped of its indentation."""
    lines, fence = [], None
    for line in text.splitlines():
        stripped = line.strip()
        marker = re.match(r"^(`{3,})", stripped)
        if fence is None and marker:
            fence = marker.group(1)
        elif fence is not None and stripped == fence:
            fence = None
        elif fence is not None:
            lines.append(stripped)
    return lines


def slug(title: str) -> str:
    """GitHub's heading anchor: lower case, punctuation other than '-' dropped, spaces to '-'."""
    return re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")


def test_t300_9_section_0_comes_first_and_covers_the_three_steps() -> None:
    assert [number for number, _ in HEADINGS] == ["0", "1", "2", "3", "4", "5", "6"], HEADINGS
    assert HEADINGS[0] == ("0", "Before every upgrade")
    body = section("0")
    code = code_lines(body)
    # the schema lines tell whether the upgrade migrates; the running image's number is the one you leave
    assert "**Schema N → M.**" in body and "prepare-release.py#SCHEMA_LINE" in body
    assert any("from gsd.store import KNOWN_SCHEMA_VERSION" in line for line in code)
    assert not [line for line in code if "sqlite3" in line or "gsd.db?" in line], "§0 opens no database"
    # the off-volume copy: §2 when the offsite CronJob exists, §3 when it does not, and how to see it landed
    assert "§2" in body and "§3" in body
    assert any(line.startswith("oc get cronjob -n $NS $REL-backup-offsite") for line in code)
    assert any("--from=cronjob/$REL-backup-offsite" in line for line in code)
    assert any("oc wait" in line and "condition=complete" in line for line in code)
    assert "integrity_check" in body and "already shipped" in body
    assert any('cat "$B" > "$(basename "$B")"' in line for line in code)
    # where the pre-upgrade copy goes, and the free space it needs, with and without oc
    assert "/data/pre-upgrade/" in body and "/data/<pod-name>/pre-upgrade/" in body
    assert any("shutil.disk_usage" in line and "os.stat" in line for line in code)
    assert "gsd_volume_disk_total_bytes" in body and "gsd_volume_disk_used_bytes" in body


def test_t300_10_section_4_is_recovery_mode_and_the_script_with_oc_debug_as_the_fallback() -> None:
    body = section("4")
    order = body.split("\n\n", 2)[1]
    assert order.startswith("**In order.**"), "§4 opens with the order"
    for words in ("recovery mode", "values file", "deployment pipeline", "restore-db.sh", "never `oc scale`"):
        assert words in order, words
    assert "recovery.enabled: true" in body and "local-development/restore-db.sh --list" in body
    assert "--from-version <ID>" in body
    assert "--namespace $NS --release $REL" in body, "the script defaults to group-sync-dashboard for both; the runbook's NS is not it"
    code = code_lines(body)
    assert any(line.startswith("oc debug -n $NS deploy/$REL") for line in code), "the fallback keeps oc debug"
    assert not [line for line in code if line.startswith("oc scale")], "no oc scale in §4's commands"
    assert "`replicaCount: 0` in this release's values file" in body
    # the only Helm command line is the one labelled for development and troubleshooting
    operator = re.sub(r"\*\*Development and troubleshooting only:\*\*.*?\n\n", "", body, flags=re.S)
    for word in ("helm upgrade", "--set", "argocd", "applications.argoproj.io", "oc patch", "oc set env deploy"):
        assert word not in operator.lower(), word
    for sentence in re.split(r"(?<=[.;:])\s+", operator):
        assert "Argo CD" not in sentence or "revert" in sentence, sentence


def test_t300_11_no_stale_version_and_the_fallback_keeps_the_wal() -> None:
    body = section("4")
    assert "group-sync-dashboard:0.15.0" not in TEXT
    assert '"version": "0.15.0"' not in TEXT and '"version":"0.15.0"' not in TEXT
    assert '"version":"<the application version the release now runs>"' in body, "the shape /api/version prints"
    keep = body.split("### 4a.", 1)[1].split("### 4b.", 1)[0]
    assert re.search(r'for name in \(\\"gsd\.db\\", \\"gsd\.db-wal\\"', keep), "§4a keeps gsd.db with its -wal"
    assert "Scale to 0" not in body


def test_t300_12_the_sections_the_code_cites_keep_their_numbers() -> None:
    titles = dict(HEADINGS)
    assert titles["4"] == "Restore"
    assert titles["5"] == "Moving the data to a new claim (access mode change)"
    assert titles["6"] == "Pre-upgrade copies"
    cited = set()
    for path in [*(REPO / "local-development" / "gsd").rglob("*.py"), *(REPO / "charts").rglob("*.*")]:
        if path.is_file() and path.suffix in (".py", ".tpl", ".yaml", ".md"):
            cited.update(re.findall(r"RUNBOOK_backup_restore\.md §(\d)", path.read_text(errors="replace")))
    assert {"4", "5", "6"} <= cited, cited
    assert cited <= set(titles), f"the code cites a section the runbook does not have: {cited - set(titles)}"
    # the links other documents make into the runbook, as GitHub resolves them: a heading's anchor
    anchors = {slug(title) for title in re.findall(r"^#{2,3} (.+)$", TEXT, re.M)}
    linked = set()
    for path in REPO.rglob("*.md"):
        if not {".git", ".venv", "node_modules"} & set(path.parts):
            linked.update(re.findall(r"\]\([^)\s]*RUNBOOK_backup_restore\.md#([\w-]+)\)", path.read_text(errors="replace")))
    assert "6-pre-upgrade-copies" in linked
    assert linked <= anchors, f"links to anchors the runbook does not have: {linked - anchors}"
