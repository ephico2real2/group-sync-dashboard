"""docs/RUNBOOK_backup_restore.md, as #300 left it: §0 before every upgrade, §4 around recovery mode (#303) and
restore-db.sh (#302) with the manual paths as the fallback, and the section numbers the code cites.

The runbook is the procedure an operator follows at 03:00, so these read it as text: a heading renumbered or a
stale command left in place is a wrong instruction no other test sees. The store's refusals cite "§4" and "§6"
(gsd/store.py), a chart refusal cites "§5", and the chart README links "#6-pre-upgrade-copies".

#533 corrected four instructions the #300 walk ran as printed, and added §4's risks under Argo CD and the §4d break
glass (docs/specs/SPEC_E10_runbook_corrections.md); their tests are T533-1 to T533-7.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys

import pytest
import yaml

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
    # the break glass (§4d) scales the two Deployments by hand since #532; nothing else in §4 does
    outside = code_lines(body.split("### 4d.", 1)[0])
    assert not [line for line in outside if line.startswith("oc scale")], "no oc scale in §4's commands outside §4d"
    assert "`replicaCount: 0` in this release's values file" in body
    # the only Helm command line is the one labelled for development and troubleshooting; the break glass (§4d, the
    # last subsection) and the risks box it answers are the one place where Argo CD's controls and hand edits are the
    # path (#533, the operator's decision of 2026-10-02); elsewhere Argo CD is named for what it reverts, §4d or #532
    operator = re.sub(r"\*\*Development and troubleshooting only:\*\*.*?\n\n", "", body, flags=re.S)
    operator = "\n".join(line for line in operator.split("### 4d.", 1)[0].splitlines() if not line.startswith(">"))
    for word in ("helm upgrade", "--set", "argocd", "applications.argoproj.io", "oc patch", "oc set env deploy"):
        assert word not in operator.lower(), word
    for sentence in re.split(r"(?<=[.;:])\s+", operator):
        assert "Argo CD" not in sentence or any(word in sentence for word in ("revert", "§4d", "#532")), sentence


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


# ── #533: the corrections from the #300 walk, and the break glass under Argo CD (SPEC_E10) ─────────────────────────

def python_body(text: str, first_line: str) -> str:
    """The Python of the first `python3.14 -c '…'` command in `text` whose code starts with `first_line`: from the
    line after the opening quote to the line before the closing one, as the operator's shell passes it."""
    start = text.index(f"-c '\n{first_line}\n") + len("-c '\n")
    return text[start:text.index("\n'", start)] + "\n"


def flat(text: str) -> str:
    """Prose with its line breaks, indentation and blockquote markers folded, so a wrapped phrase still matches."""
    return " ".join(" ".join(re.sub(r"^\s*>\s?", "", line) for line in text.splitlines()).split())


def test_t533_1_oc_debug_runs_the_dashboard_container_alone() -> None:
    """§4a's helper pod is `oc debug` of the Deployment, which copies every container of its template. With the
    oauth-proxy sidecar copied the pod never completes and `oc debug` never returns (the #300 walk, F2); with
    `--one-container` it ran the body, exited 0 in 3 s and removed its pod (SPEC_E10 §2.2). Every `oc debug` command
    the runbook prints carries the flag."""
    uses = re.findall(r"oc debug [^`\n]*", TEXT)
    assert uses, "the runbook prints no oc debug command"
    assert all("--one-container" in use for use in uses), [use for use in uses if "--one-container" not in use]


def test_t533_2_section_4c_counts_up_to_the_copys_highest_id(tmp_path: pathlib.Path) -> None:
    """§4c compared whole-table counts with the copy's, which fails as soon as the leader polls (the #300 walk read
    2776, then 2779 `sync_event` rows against the copy's 2770). §1 now prints each table's highest id and §4c counts
    the live file up to it. Both snippets run here as printed: on a copy, and on a live file holding the copy's rows
    and rows written after the restore, which take higher ids (AUTOINCREMENT)."""
    tables = {"membership_event": 5, "sync_event": 7, "login_event": 3}
    copy, live = tmp_path / "copy.db", tmp_path / "gsd.db"
    c = sqlite3.connect(copy)
    for table, rows in tables.items():
        c.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY AUTOINCREMENT, note TEXT)")
        c.executemany(f"INSERT INTO {table} (note) VALUES (?)", [("copy",)] * rows)
    c.commit()
    c.close()
    shutil.copyfile(copy, live)
    c = sqlite3.connect(live)                       # the leader's first polls after the restore
    c.executemany("INSERT INTO sync_event (note) VALUES (?)", [("after",)] * 6)
    c.executemany("INSERT INTO login_event (note) VALUES (?)", [("after",)] * 2)
    c.commit()
    c.close()
    printed = subprocess.run([sys.executable, "-c", python_body(section("1"), "import sqlite3, sys"), str(copy)],
                             capture_output=True, text=True, check=True).stdout
    tops = []
    for table, rows in tables.items():
        found = re.search(rf"^{table} (\d+) rows, highest id (\d+)$", printed, re.M)
        assert found, f"§1 prints no row count and highest id for {table}: {printed!r}"
        assert int(found[1]) == rows, (table, printed)
        tops.append(found[2])
    count = python_body(section("4").split("### 4c.", 1)[1], "import sqlite3, sys").replace("/data/gsd.db", str(live))
    counted = subprocess.run([sys.executable, "-c", count, *tops], capture_output=True, text=True, check=True).stdout
    for table, rows in tables.items():
        found = re.search(rf"^{table} (\d+) rows up to id (\d+)$", counted, re.M)
        assert found and int(found[1]) == rows, (table, counted)
    # right after a rollout the replaced pod still holds the lease (the §5 walk read "leader":false for about 10 s)
    assert "Wait and read again" in flat(section("4").split("### 4c.", 1)[1])


def test_t533_3_section_0_prints_the_metrics_read() -> None:
    """§0 named `gsd_build_info` and the two `gsd_volume_disk_*` gauges and printed no command to read them (the #300
    walk, F6). It prints one read through the pod's loopback, and its filter keeps exactly the three series the lab
    served (SPEC_E10 §2.4) and nothing else of a scrape."""
    reads = [line for line in code_lines(section("0")) if "curl -s http://127.0.0.1:8080/metrics" in line]
    assert len(reads) == 1, reads
    assert reads[0].startswith("oc exec -n $NS deploy/$REL -c dashboard -- curl -s http://127.0.0.1:8080/metrics | grep -E '")
    pattern = re.compile(reads[0].split("grep -E '", 1)[1].rsplit("'", 1)[0])
    scrape = [
        'gsd_build_info{branch="main",commit="521c2bb0b4",version="2.4.0"} 1.0',
        'gsd_volume_disk_used_bytes{component="dashboard"} 1.34537723904e+11',
        'gsd_volume_disk_total_bytes{component="dashboard"} 1.60456224768e+11',
        "# HELP gsd_build_info Always 1; the running build is carried in the labels.",
        "gsd_backup_last_success_timestamp_seconds 1.7904500667085032e+09",
    ]
    assert [line for line in scrape if pattern.search(line)] == scrape[:3]


def test_t533_4_spec_e7_says_the_fallback_restore_sets_the_database_back() -> None:
    """SPEC_E7 §5 step 6 said §4a's restore of the copy step 5 restored leaves "the database … unchanged". The app had
    written rows in between, and the restore discarded them (the #300 walk, F4)."""
    spec = (REPO / "docs" / "specs" / "SPEC_E7_schema_line_and_runbook.md").read_text()
    step = spec.split("6. **§4, the fallback.**", 1)[1].split("\n7. ", 1)[0]
    assert "the database is unchanged by it" not in step
    assert "sets the database back to that copy" in flat(step)


def test_t533_5_section_4_states_the_risks_under_argo_cd_before_step_1() -> None:
    """The operator's decision of 2026-10-02: the two risks Argo CD brings to a restore are stated at the top of §4,
    with the lab's numbers, and step 5 no longer says the recovery pod stops "at once" (#532)."""
    body = section("4")
    assert "> **Risks under Argo CD**" in body and body.index("> **Risks under Argo CD**") < body.index("1. **Turn it on")
    risks = flat("\n".join(line for line in body.splitlines() if line.startswith(">")))
    for words in ("selfHeal: true", "0.7 s", "4 min 38 s", "Pause automated sync first", "12 min 49 s", "limit: 3",
                  "less than 0", "retries 5 times", "#532", "§4d step 7"):
        assert words in risks, words
    step5 = flat(body.split("5. **Turn it off**", 1)[1].split("\n\n", 1)[0])
    assert "stops at once" not in step5, "under a retrying sync the recovery pod does not stop at once (#532)"
    # #532 (SPEC_E11): from chart 0.65.0 the switch takes one rollout; the measured wait is for older charts
    for words in ("#532", "within the one rollout", "On a chart before 0.65.0", "12 min 49 s"):
        assert words in step5, words
    assert "nothing to retry" in risks and "endless retry, on a chart before 0.65.0" in risks


def test_t533_6_section_4d_pauses_first_and_gives_the_release_back_to_git() -> None:
    """§4d, the break glass: the pause comes first and is confirmed, with the operation's phase beside it, before the
    hand edit; the restore is the script; the give-back waits for Argo CD's apply before `oc rollout status`, and
    ends with what the edit added removed. §4d is §4's last subsection, because T300-10 exempts it whole."""
    body = section("4")
    assert re.findall(r"^### (4\w)\. ", body, re.M) == ["4a", "4b", "4c", "4d"]
    glass = body.split("### 4d.", 1)[1]
    code = code_lines(glass)
    steps = [
        r"argocd\.argoproj\.io/tracking-id",
        "{.metadata.ownerReferences[*].kind}",
        """--type merge -p '{"spec":{"syncPolicy":{"automated":{"enabled":false}}}}'""",
        "{.spec.syncPolicy.automated.enabled} {.status.operationState.phase}",
        "oc scale -n $NS deploy/$REL --replicas=0",
        "oc scale -n $NS deploy/$REL-recovery --replicas=1",
        "restore-db.sh --list",
        '[{"op":"remove","path":"/spec/syncPolicy/automated/enabled"}]',
        "--for=jsonpath='{.status.sync.status}'=Synced",
        "oc rollout status -n $NS deploy/$REL",
        "argocd app terminate-op $APP",
    ]
    where = []
    for step in steps:
        hits = [i for i, line in enumerate(code) if step in line]
        assert hits, f"§4d prints no command with {step!r}"
        where.append(hits[0])
    assert where == sorted(where), "§4d's commands are out of order"
    # the give-back's rollout status comes after the wait for Synced: before Argo CD's apply it reports the app's
    # Deployment at 0 of 0, already complete (#532)
    assert where[steps.index("--for=jsonpath='{.status.sync.status}'=Synced")] < where[steps.index("oc rollout status -n $NS deploy/$REL")]
    prose = flat(glass)
    for words in ("ignoreApplicationDifferences", "Incident step", "selfHeal", "Nothing to remove",
                  "a phase that is not `Running`", "each retry applies what Git renders over the hand edit",
                  "0 of 0, already complete", "a chart before 0.65.0"):
        assert words in prose, words
    assert "oc patch -n $NS deploy" not in glass and "helm pull" not in glass, "the hand edit is two oc scale commands"
    # the §5 walk (2026-10-02) ran the restore and step 7; without an Argo CD login the CLI needs its --core form
    assert "Not measured on the lab" not in prose and "except the restore itself" not in prose
    for words in ("argocd --core", 'configmap "argocd-cm" not found', "Operation terminated (retried 3 times)", "5m44s"):
        assert words in prose, words


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")
def test_t533_7_the_hand_edit_is_what_recovery_mode_renders() -> None:
    """§4d's hand edit must be the chart's recovery mode, or the pod it makes is not the recovery pod `restore-db.sh`
    and SPEC_E2 promise. Since #532 (SPEC_E11) it is two `oc scale` commands: applied to the default render they
    give exactly the render with recovery.enabled: true, so Argo CD's give-back (step 5) leaves nothing behind."""
    glass = section("4").split("### 4d.", 1)[1]
    scale = re.compile(r"^oc scale -n \$NS deploy/\$REL(?P<suffix>-recovery)? --replicas=(?P<n>\d)$")
    scaled = {"group-sync-dashboard" + (m.group("suffix") or ""): int(m.group("n"))
              for m in map(scale.match, code_lines(glass)) if m}
    assert len(scaled) == 2 and len([line for line in code_lines(glass) if line.startswith("oc scale")]) == 2, scaled

    def deployments(*flags: str) -> dict:
        out = subprocess.run(["helm", "template", "group-sync-dashboard", str(REPO / "charts" / "group-sync-dashboard"),
                              "--set", "ingress.host=t.example.com", *flags],
                             capture_output=True, text=True, check=True).stdout
        return {d["metadata"]["name"]: d for d in yaml.safe_load_all(out) if d and d["kind"] == "Deployment"}

    by_hand, rendered = deployments(), deployments("--set", "recovery.enabled=true")
    for name, replicas in scaled.items():
        by_hand[name]["spec"]["replicas"] = replicas
    assert by_hand == rendered
