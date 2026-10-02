# SPEC E6 — the KPI page's Backups card: last copy, copies kept, failures, the newest copy's schema and the pre-upgrade copy, from what the dashboard process already has (#306)

| | |
|---|---|
| Programme | Epic E (#385), restore tools and release safety; build-order step 5 of 9. Independent of the restore path (#303, #302); composes with SPEC_E4 (#391, step 3), see the Orchestrator's notes, 9 |
| Batch | E — restore tools and release safety |
| Release | — (post-programme; Epic E's release, milestone 3.0.0) |
| Version on release | app 2.4.0, chart 0.60.6 |
| Version note | The next free MINOR, filled at implementation. The change is in `local-development/gsd/` (image content), so the implementing pull request runs `local-development/prepare-release.py --app <the next free MINOR> --no-commit "…"`, which moves `pyproject.toml`, `gsd/__init__.py` and `Chart.yaml`'s `appVersion`, and with it the chart PATCH and its history line (the script's own rule). Against origin/main `6d532178` (application 2.0.0, chart 0.59.25) that is app 2.1.0 and chart 0.59.26. No block carries a version field: the script writes them, as in SPEC_E3 and SPEC_E4. **When specs claim the same numbers** (the rule SPEC_E5, #304, states): a spec still `specified` must name versions above `pyproject.toml` and `Chart.yaml` (`local-development/tests/test_specs_index.py#test_a_spec_the_changelog_has_not_begun_names_versions_the_tree_has_not_reached`), so whichever implementation merges first takes its numbers and, in the same pull request, moves every other `specified` spec whose application or chart version is not above the new tree to the next free version above it, in its header and its index row, keeping its MINOR or PATCH. Read from `docs/specs/README.md` on `6d532178`, those are SPEC_G2 (app 2.1.0, chart 0.60.0), whose app moves to 2.3.0 (2.2.0 being SPEC_G3's); SPEC_E4 (app 2.1.0, chart 0.59.26), which moves to app 2.4.0 and chart 0.59.27; and SPEC_E3 (app 2.1.0, chart 0.59.26), which moves to app 2.5.0 and chart 0.59.28. SPEC_E2 and SPEC_E5 (chart 0.60.0) and SPEC_G3 (app 2.2.0, chart 0.60.1) are already above and stay. Measured: `6d532178` with this spec's blocks and `prepare-release.py --app 2.1.0 --no-commit` fails that test with `AssertionError: ('G2', 'app 2.1.0, chart 0.60.0', 'pyproject.toml is already 2.1.0')`; with G2 and E4 moved and E3 not, with `AssertionError: ('E3', 'app 2.1.0, chart 0.59.26', 'Chart.yaml is already 0.59.26')`; with the three moves, `tests/test_specs_index.py` and `tests/test_chart_versions.py` give `100 passed`. If another of them is implemented first, its pull request moves this spec's cells instead, and this spec's implementing pull request re-derives the moves against main before applying, with the reason under these notes |
| Issue | [#306](https://github.com/ephico2real2/group-sync-dashboard/issues/306) |
| Status | specified |
| Source | OB1-lite's research and specification of 2026-10-01, written before any code from the issue (its "Decisions and corrections (2026-10-01)"), the epic, the committed mock (`docs/design/kpi-backups-mock.html`) and SPEC_E4 at `29c67b03` (in review). Measured on main `73cc7d08` (application 2.0.0, chart 0.59.25) with Python 3.14.7 and Chromium (Playwright) on this machine, and read-only on the CRC lab (image 2.0.0). §7's blocks were cut from a copy of `73cc7d08` with the design implemented, and proved against a clean worktree of this spec's commit (§4.3). Revised the same day on the reviews of `1e194df3` (OB3 in Grok's seat, OB2 in Codex's seat; Orchestrator's notes, 13), rebased onto origin/main `6d532178` (SPEC_E5 and SPEC_E3 merged), and proved again there (§4.3) |

## How to read this spec

**The point in one sentence: the dashboard process already knows everything an operator needs to judge its
on-volume backup — the backup directory it lists for the size line, the failure counter `/metrics` exports, and
`config.backup` — so `/api/kpi` carries those facts and the KPI page draws them as one Backups card, in one of
five states said in words: healthy, no copy yet, failing, stale, or disabled.**

§1 is the mandate. §2 is the research: each finding names its primary source and the exact sentence relied on,
or the command that measured it with its output. §2a weighs the alternatives and reconciles each external claim
with the code that behaves accordingly. §3 is the design, one rule per subsection with its reason, and the read
budget with its scope (§3.8). §4 maps every test case of the issue (T306-1 to T306-17) to a test and records each
failing before the change and passing after it. §5 is the walk on the lab. §6 is what an operator sees and what
it costs. §7 is the whole change as implementation blocks (`docs/specs/README.md`, "Implementation blocks"),
applied to a clean tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E6_kpi_backups_card.md . --apply

Line numbers into the code at `73cc7d08` are written as plain text, file:line without backticks, to keep them
apart from the maintained `path#anchor` citations. They hold on origin/main `6d532178` too: `git diff --stat 73cc7d08
origin/main` over the files this spec cites or edits is empty. This spec's own row in the index moves through the lifecycle
by the orchestrator's hand; no block touches it. A block found wrong during implementation is corrected here,
with the reason under the Orchestrator's notes, before it is applied again.

## Orchestrator's notes

Decisions taken while specifying, on "easy to manage, best practice", and the corrections the research made to the
issue and the mock. Each is applied in §3 and §7 and held by a test in §4.

1. **`pre_upgrade` sits beside `backups`, not inside it.** The issue settles that the disabled block is
   `{"enabled": false}` "and nothing else", and asks for the newest pre-upgrade copy (#301). The pre-upgrade copy is
   written whether or not backups are enabled (SPEC_M1 §3.10, "The copy is written; nothing else changes";
   `local-development/gsd/store.py#PRE_UPGRADE_DIR`'s comment). Inside `backups`, the disabled shape would either
   hide a real rollback point or stop being "nothing else". So the data block is
   `{"db_bytes", "wal_bytes", "backups", "pre_upgrade"}`, and a disabled card keeps exactly one tile, the
   pre-upgrade copy (T306-6, T306-8).
2. **Three fields beyond the issue's list, each for a figure the mock draws.** `dir` (the heading's
   "on-volume · /data/backup"); `failures_since` (the Failures tile's "since start <instant>": the instant the
   process built the measure, inside the same `build_app` call that creates `RuntimeSignals`, so the counter and
   its start are one process lifetime); and `kept` (the copies this process's rotation keeps, against `keep`).
   On `73cc7d08` `kept` equals `count`, because every `gsd-*.db` is rotated by every pod; it exists so that SPEC_E4
   composes without a second payload change (note 9).
3. **`newest_schema` is read from the header at offset 60, not through SQLite with `immutable=1`.** Both write
   nothing (§2.2). The header read is chosen because the storage seam forbids `import sqlite3` and SQL-shaped
   strings (`PRAGMA …` included) outside `store.py` and the report service's snapshot reader
   (`local-development/tests/test_storage_seam.py#test_no_module_imports_a_database_driver`,
   `#test_no_module_writes_sql`), and `gsd/kpi/system.py` is outside them; and because a header read opens one file
   for 64 bytes, with no lock and no SQLite connection. The reader, `copy_schema`, lives in `store.py`, the module
   that owns the file format, beside the pre-upgrade reader; it is SPEC_E3's `schema_of` rule (its §2.5), written
   for the application package, since SPEC_E3's lives in a standalone script.
4. **Stale is computed in the page, against the payload's `as_of`.** "Older than 2 × `interval_hours`", as the
   issue decided (the app never receives `monitoring.prometheusRule.backupStaleSeconds`; the values comment defines
   that line as two intervals, `charts/group-sync-dashboard/values.yaml#backupStaleSeconds: 43200`). The page
   compares `as_of` (the server's clock) with `newest_at`, as the sparklines already end on `as_of`'s day
   (`local-development/gsd/static/index.html#function kpiSpark`), so a browser with a wrong clock cannot turn a
   fresh copy stale, and the payload carries no now-dependent state of its own. The card says stale at two
   intervals; `GroupSyncDashboardBackupStale` pages 30 minutes later (`for.backupStale: 30m`). Where an estate tunes
   one and not the other, the card follows the interval (the issue's decision 1).
5. **Correction to the mock and the issue: instants are shown in the page's display zone, not as raw UTC.** The
   mock prints `14:34:37Z` and the issue says "ISO-8601 UTC". The page has one rule for every absolute time it
   shows, written beside the helper that applies it: "THE SERVER STATES AN INSTANT; THE PAGE PRESENTS IT (#271, and
   the operator's ruling of 2026-09-21 that an absolute stamp is the right thing for a server to emit)" and "an
   absolute stamp in raw UTC ignores the deployment's configured zone, which every other timestamp on this page
   honours, so the page localises it at RENDER time" (`local-development/gsd/static/index.html#function withLocalInstants`);
   `fmtTime` always prints the zone's label (`#function fmtTime`). The lab runs with `TZ=America/New_York`
   (measured, §2.4), so raw UTC on this card would sit beside EDT everywhere else on the page. The payload keeps
   ISO-8601 UTC (the server's rule), every instant on the card is a `<time datetime="<UTC>">`, and its text is
   `fmtTime`'s: `2026-10-01 07:11:04 EDT` on the lab, `2026-10-01 11:11:04Z` where no zone is configured, which is
   the mock's text exactly. T306-12 holds both. If the operator wants raw UTC here anyway, `kpiStampText` (block 8),
   the one function every instant on the card is printed through, the "next due by" date test included, reads
   `(iso) => (iso ? iso.replace("T", " ") : "—")` instead of `(iso) => fmtTime(iso)`: one line, and T306-12's
   display-zone assertion, which pins this decision, goes with it; the card then always reads `2026-10-01 11:11:04Z`.
   The guard is `fmtTime`'s own: a payload without an instant (a server older than this card answers
   `{"count", "bytes"}`, the shape three existing KPI tests send) prints `—`, where a bare `iso.replace` throws and
   stops the whole KPI page's render (review of this spec, measured: 4 failed, 19 passed in `TestKpiPage`).
6. **Correction folded into T306-3: the walk counts and sizes the same files.** On `73cc7d08` `count` increments
   before `stat()` (local-development/gsd/kpi/system.py:256-257): two copies and one name whose stat fails measured
   `{'count': 3, 'bytes': 12288}` (§2.1). The new walk stats each file once and counts it only when the stat
   succeeds. The metric is stricter in that race: one failed stat omits the whole series for that scrape
   (local-development/gsd/metrics.py:812-822, "OMITTED, never zeroed"), while the card reports the newest survivor.
   `/metrics` is out of scope (the issue's "Must not change"), so the two differ only for a scrape that lands
   inside a rotation.
7. **Found while implementing: the Data volume meter would read `NaN`.** `kpiComponent` adds
   `own.backups.bytes` whenever `own.backups` exists (local-development/gsd/static/index.html:1704). With the
   disabled block reduced to `{"enabled": false}` that is `undefined`, and the meter printed `NaNKi · node disk 47% full` (measured in the browser
   harness with block 7 reverted, §4.2's M8). Block 7 reads it as 0; T306-8 asserts no `NaN`.
8. **T306-8's "the page shows neither '0 backups' nor 'never'" is checked on the card and the dashboard component.**
   Those are the two places the backup state is written. The disabled sentence avoids the word ("a setting, not a
   failure"), where the mock had `not "never"`.
9. **SPEC_E4 (#391, merged as a spec at `66a6f325`): which numbers are per pod, which per volume, and what changes
   when it lands.** Above one replica E4 names copies `gsd-<stamp>-<pod>.db`, adds `BACKUP_NAME`, `backup_owner` and
   `backup_copies` to `local-development/gsd/storage.py`, makes `gsd_backup_last_success_timestamp_seconds` read the
   pod's own copies, or the whole directory while the pod has none of its own (every pod after a rollout: E4 §3.4,
   its review's F1), and keeps the KPI size line counting every pod's (its note 4, its T391-8). The card follows the
   same split:

   | figure | per | why |
   |---|---|---|
   | `count`, `bytes` (the sub-line, the Copies kept tile's size) | volume | the bytes on the shared claim, what `persistence.size` must hold (E4 note 4) |
   | `kept` (the Copies kept tile, against `keep`) | pod | `keep` is per pod above one replica under E4 |
   | `newest_at`, `newest_schema`, the stale and none-yet states | pod, else volume | the metric's rule under E4: a neighbour's fresh copy must not stand in for this pod's failing backups, and a pod with none of its own yet (after a rollout) reads the directory's newest, so the card turns stale when `GroupSyncDashboardBackupStale` fires |
   | `failures`, `failures_since` | pod (process) | the counter is per process already |
   | `pre_upgrade` | pod | `pre-upgrade/` is beside each pod's own database (SPEC_M1 §3.1) |

   - **Old texts.** None of this spec's 24 Old texts is changed by E4, and none of E4's 32 by this spec: this spec's
     blocks check out on origin/main `6d532178` with E4's 32 blocks applied, and on `6d532178` alone; E4's check out
     with this spec's applied; the two orders give the same tree but for the order of the two CHANGELOG entries
     (measured, review of this spec).
   - **Behaviour.** E4's T391-8 asserts the whole `backups` dict, `== {"count": 3, "bytes": 45}`
     (its block 23), so it fails once this spec lands (measured on `6d532178` + E4 + E6:
     `AssertionError: assert {'enabled': T...tes': 45, ...} == {'count': 3, 'bytes': 45}`). And without the owner
     rule, `kept` and `newest_at` would stay per volume above one replica.
   - **The composition, applied by whichever of #391 and #306 merges second**, re-derived against main as the
     README's rule 5 says. It takes two names from E4, `BACKUP_NAME` and `backup_owner`, and not `backup_copies`,
     which globs the directory again and would break the one-walk budget (§3.8). Five edits:
     1. `local-development/gsd/kpi/system.py`: below `from ..store import KNOWN_SCHEMA_VERSION, copy_schema, newest_pre_upgrade`,
        add `from ..storage import BACKUP_NAME, backup_owner`.
     2. The same file: `dashboard_data_bytes` as below (the signature gains `replica_count`, the docstring's
        `kept` and `newest_at` sentences change, and the walk counts `kept` over the own copies and takes `newest`
        over them, or over every copy while there is none of its own, as the metric does).
     3. `local-development/gsd/api.py#build_app`: the call gains `replica_count=settings.replica_count`.
     4. E4's T391-8 (`test_the_backup_size_line_counts_every_replicas_copies`): its last line becomes
        `got = dashboard_data_bytes(str(db), str(backups))()["backups"]` and `assert (got["count"], got["bytes"]) == (3, 45)`.
     5. `local-development/API.md`, the `kept` row: "the copies this process's rotation keeps to `keep`: every
        `gsd-*.db` at one replica; above one, the copies whose name carries this pod (#391)", and the `newest_at`
        row: "the newest `kept` copy's mtime, or the directory's newest while this pod has none of its own (above
        one replica, after a rollout: #391), ISO-8601 UTC to the second: the rule of
        `gsd_backup_last_success_timestamp_seconds`; `null` when there is none yet"; and in
        `local-development/tests/test_kpi.py`'s `TestBackupsCard`, the two tests below.

     The function, as the composition writes it:

     ```python
     def dashboard_data_bytes(db_path: str, backup_dir: str | None, *, keep: int | None = None,
                              interval_hours: float | None = None, failures: Callable[[], int] | None = None,
                              replica_count: int = 1):
         """The dashboard's own bytes: the database file, its WAL, and the backups — what
         `gsd_sqlite_wal_bytes` and the backup gauge already say, gathered for the page — and the KPI page's
         Backups card (#306), from what this process already has.

         `backups` is `{"enabled": False}` and nothing else when no backup directory is configured: disabled is
         not "0 backups". Enabled, it is ONE walk of the directory's gsd-*.db (the size line's own glob): each file
         stat'd once and counted only when its stat succeeds, so `count` and `bytes` describe the same files (a
         copy rotated away between the glob and the stat is in neither). `count` and `bytes` are every copy on the
         volume; `kept` is this process's own copies, the ones its rotation keeps to `keep`: every gsd-*.db at one
         replica, and above one the names that carry this pod (#391). `newest_at` is the newest own copy's mtime,
         or the directory's newest while this pod has none of its own (every pod, after a rollout): the rule
         `gsd_backup_last_success_timestamp_seconds` reads, compared in this walk rather than by a second listing,
         so the card turns stale when GroupSyncDashboardBackupStale fires. `newest_schema` is read from that one
         file's header without opening it in SQLite. `failures` is the counter /metrics exports, since
         `failures_since`: the instant this process built it. `keep` and `interval_hours` are the settings the
         poller backs up with.

         `pre_upgrade` sits beside `backups`, not inside it: the copy before a migration (#301) is taken whether
         or not backups are enabled. One listing of its directory, nothing opened.
         """
         started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
         owner = backup_owner(replica_count)

         def measure() -> dict | None:
             try:
                 db = os.stat(db_path).st_size
             except OSError:
                 return None
             try:
                 wal = os.stat(db_path + "-wal").st_size
             except OSError:
                 wal = 0
             backups: dict = {"enabled": False}
             if backup_dir:
                 count, size, kept, own, newest = 0, 0, 0, None, None
                 for f in Path(backup_dir).glob("gsd-*.db"):
                     try:
                         st = f.stat()
                     except OSError:
                         continue
                     count += 1
                     size += st.st_size
                     if newest is None or st.st_mtime > newest[0]:
                         newest = (st.st_mtime, f)
                     if owner is not None and ((m := BACKUP_NAME.fullmatch(f.name)) is None or m.group(2) != owner):
                         continue
                     kept += 1
                     if own is None or st.st_mtime > own[0]:
                         own = (st.st_mtime, f)
                 newest = own or newest      # none of its own yet: the directory's newest, as the metric reads
                 backups = {
                     "enabled": True, "dir": backup_dir, "count": count, "bytes": size, "kept": kept,
                     "newest_at": None if newest is None
                     else datetime.fromtimestamp(newest[0], UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                     "newest_schema": None if newest is None else copy_schema(newest[1]),
                     "known_schema": KNOWN_SCHEMA_VERSION,
                     "failures": None if failures is None else failures(),
                     "failures_since": started,
                     "keep": keep, "interval_hours": interval_hours,
                 }
             return {"db_bytes": db, "wal_bytes": wal, "backups": backups, "pre_upgrade": newest_pre_upgrade(db_path)}
         return measure
     ```

     The tests it adds, in `TestBackupsCard` before `test_t306_16_one_view_lists_two_directories_opens_one_copy_and_writes_nothing`:

     ```python
     def test_above_one_replica_the_card_reads_this_pods_copies_as_the_metric_does(self, tmp_path, monkeypatch):
         """SPEC_E6 with SPEC_E4 (#306, #391): above one replica `count` and `bytes` are every pod's copies (the
         bytes on the shared claim), while `kept`, `newest_at` and `newest_schema` are this pod's own, the copies
         gsd_backup_last_success_timestamp_seconds reads: a neighbour's fresh copy must not stand in for this
         pod's failing backups. The owner is the whole field after the stamp, never a suffix."""
         from types import SimpleNamespace

         from gsd.kpi.system import dashboard_data_bytes
         monkeypatch.setenv("POD_NAME", "pod-a")
         db = tmp_path / "gsd.db"; db.write_bytes(b"d" * 100)
         backups = tmp_path / "backup"; backups.mkdir()
         _copy(backups / "gsd-20261001T051103.798578Z-pod-a.db", 19, 4096, mtime=1790831464)
         _copy(backups / "gsd-20261001T111104.000930Z-pod-b.db", 20, 4096, mtime=1790853064)
         _copy(backups / "gsd-20261001T111105.000000Z-x-pod-a.db", 20, 4096, mtime=1790853065)
         got = dashboard_data_bytes(str(db), str(backups), replica_count=2)()["backups"]
         assert (got["count"], got["bytes"], got["kept"]) == (3, 3 * 4096, 1)
         assert (got["newest_at"], got["newest_schema"]) == ("2026-10-01T05:11:04Z", 19)
         store = Store(":memory:")
         try:
             text = generate_latest(build_registry(store, timedelta(seconds=120), settings=SimpleNamespace(
                 backup_dir=str(backups), login_capture_enabled=False, replica_count=2))).decode()
         finally:
             store.close()
         metric = next(float(line.split()[1]) for line in text.splitlines()
                       if line.startswith("gsd_backup_last_success_timestamp_seconds "))
         assert datetime.fromtimestamp(metric, UTC).strftime("%Y-%m-%dT%H:%M:%SZ") == got["newest_at"]
         one = dashboard_data_bytes(str(db), str(backups), replica_count=1)()["backups"]
         assert (one["count"], one["kept"], one["newest_at"]) == (3, 3, "2026-10-01T11:11:05Z")

     def test_above_one_replica_a_pod_with_no_copy_of_its_own_reads_the_directory_as_the_metric_does(self, tmp_path, monkeypatch):
         """SPEC_E6 with SPEC_E4 (#306, #391, E4's review F1): every rollout renames every pod, so after one no pod
         has a copy of its own until its first backup succeeds. The card then reads the directory's newest, the copy
         gsd_backup_last_success_timestamp_seconds reads, so a rollout whose backups all fail turns the card stale
         when GroupSyncDashboardBackupStale fires; `kept` stays this pod's own: none."""
         from types import SimpleNamespace

         from gsd.kpi.system import dashboard_data_bytes
         monkeypatch.setenv("POD_NAME", "new-pod")
         db = tmp_path / "gsd.db"; db.write_bytes(b"d" * 100)
         backups = tmp_path / "backup"; backups.mkdir()
         _copy(backups / "gsd-20261001T051103.798578Z-departed-a.db", 19, 4096, mtime=1790831464)
         _copy(backups / "gsd-20261001T111104.000930Z-departed-b.db", 20, 4096, mtime=1790853064)
         got = dashboard_data_bytes(str(db), str(backups), replica_count=2)()["backups"]
         assert (got["count"], got["kept"], got["newest_at"], got["newest_schema"]) == (2, 0, "2026-10-01T11:11:04Z", 20)
         store = Store(":memory:")
         try:
             text = generate_latest(build_registry(store, timedelta(seconds=120), settings=SimpleNamespace(
                 backup_dir=str(backups), login_capture_enabled=False, replica_count=2))).decode()
         finally:
             store.close()
         metric = next(float(line.split()[1]) for line in text.splitlines()
                       if line.startswith("gsd_backup_last_success_timestamp_seconds "))
         assert datetime.fromtimestamp(metric, UTC).strftime("%Y-%m-%dT%H:%M:%SZ") == got["newest_at"]
     ```

     Proved on origin/main `6d532178` + E4's 32 blocks + this spec's 24 blocks, the five edits applied by a script
     that took the two fenced listings from this note's text: over `test_kpi.py`, `test_metrics.py`, `test_backup.py`,
     `test_history_retention.py`, `test_offsite_backup_script.py`, `test_storage_seam.py`, `test_pre_upgrade_copy.py`
     and `test_docs_citations.py`, `1 failed, 1893 passed, 22 skipped` before the edits (the one is E4's T391-8) and
     `1896 passed, 22 skipped` after. With `owner = None` in place of `backup_owner(replica_count)`, both tests
     fail, the first with `assert (3, 12288, 3) == (3, 12288, 1)`; with `newest = own` in place of `newest = own or newest`, the
     second fails: `assert (2, 0, None, None) == (2, 0, '2026-...1:11:04Z', 20)`, the reading this note first had,
     under which a rollout whose backups all fail showed "failing: 3 failures since start; no good copy yet" with two
     copies on the volume and could never turn stale while the alert fired (review of this spec, measured in the
     browser harness). The page needs no change: the Copies kept tile already reads `kept` against `keep` and adds
     "N copies in all" when `count` differs (after a rollout, `0/4 · 2 copies in all`), and the states read
     `newest_at`, not `count`.
10. **T306-15 corrected: the only `charts/` change is the release script's.** The issue asks for
    `git diff --stat main -- charts/` to be empty, and its Definition of Done asks for the application bump with
    `prepare-release.py --app`, which moves `Chart.yaml`'s `appVersion` and bumps the chart PATCH with a history
    line ("`--app` alone bumps the chart PATCH, because moving appVersion is a chart change",
    `local-development/prepare-release.py`'s docstring). The two cannot both hold. The check becomes: the only file
    under `charts/` the pull request changes is `charts/group-sync-dashboard/Chart.yaml`, and only in the
    `version:`, `appVersion:` and history-comment lines the script writes; no template, value, RBAC rule or Grafana
    JSON. No block touches `charts/`.
11. **Collisions with the specs in flight.** The index count and its test (`docs/specs/README.md`'s two
    "forty-three" lines on `6d532178`, `local-development/tests/test_specs_index.py`'s row count and its rising-issue
    exclusion, which this spec extends to E6 by its id, pinned to #306 as E2 to E5 and E3 are) are edited by every spec in flight; whichever
    merges later recounts. `docs/CHANGELOG.md`'s block inserts after `## Unreleased` and its Old text stays unique
    after any other insertion there. The runbook paragraph goes in "What a successful backup looks like", which
    neither SPEC_E3 (§4) nor SPEC_E4 (the first bullet) edits.
12. **For the operator: none.** Note 5 is a correction made on the page's own written rule; it is called out so it
    can be overruled in one line.
13. **The reviews of `1e194df3` (OB3 in Grok's seat, OB2 in Codex's seat), decided by the orchestrator on
    2026-10-01.** Each is applied above and in §7 and measured again on `6d532178` (§4.3).
    - **F1, the composition with SPEC_E4 as merged (OB3's C5 and OB2's C5, the same defect).** E4 as merged
      (`66a6f325`, its block 15) makes the gauge read the whole directory while a pod has no copy of its own, every
      pod after a rollout; note 9's function read own copies only, so after a rollout whose backups fail the card said
      "failing: no good copy yet" with copies on the volume and could never turn stale while
      `GroupSyncDashboardBackupStale` fired. Taken: OB3's note 9 whole (the function with the fallback, the second
      test, the API.md `kept` and `newest_at` rows). Cross-checked against OB2's `fixed_function.py` and
      `test_ob2_fallback.py`: the two functions differ only in a variable's name and their comments, and gave the same
      `backups` on 400 random directories (pods, suffix names, replica counts 1 to 3, dangling and non-SQLite names:
      `cases 400 behavioural differences 0`); OB2's test passes against OB3's function and covers the case OB3's second
      test covers (no copy of the pod's own, two neighbours'), so it is not carried as a third test.
    - **F2, note 5's revert (OB3's C4, superseding OB2's F2).** The revert was not one line: a bare `iso.replace`
      throws on a payload without an instant and stops the whole KPI page (measured on the original blocks:
      `4 failed, 19 passed` in `TestKpiPage`, `TypeError: Cannot read properties of undefined (reading 'replace')`),
      `sameDay` stayed on `fmtTime` and printed a wrong "next due by" date (`2026-10-01 · next due by 02:00:00Z` for a
      copy at 20:00Z in New York, after: `2026-10-01 · next due by 2026-10-02 02:00:00Z`), and block 24's CHANGELOG
      said "an ISO-8601 UTC instant". Taken: OB3's block 8 (`kpiStampText`, the one function every instant is printed
      through, its block 8 comment corrected where it said the value "stays on one line", C6) and block 24, and §6's
      rows. With OB3's revert line, `TestKpiPage` gives `1 failed, 22 passed`, the one being T306-12's display-zone
      assertion, which pins this decision (OB2 measured the same of its own form of the revert).
    - **N1, the Last copy tile on a failing state with no copy (OB3, not asked).** The tile said "the first poll
      cycle takes one" beside "failing: no good copy yet"; block 8 now says "the attempts since start are failing".
      Beyond the review: T306-11 asserts it (block 19), failing on the original block 8 with
      `AssertionError: the first poll cycle takes one`.
    - **F3, the Version note (OB3's C8, OB2's F3).** Its rule ("whichever merges later takes the next ones") is the
      opposite of what the ladder test enforces; it now follows SPEC_E5's rule, with the claims read from main's index
      (the header). OB2's staleness items ("32 blocks", "merged as a spec", §4.3's E4 row) are corrected with it.
    - **The rebase.** Onto origin/main `6d532178`: E6's row goes after E3's, the index reads forty-three, and
      `test_specs_index.py` excludes E6 by its id and pins it to #306 (§4.3, the pin mutant).
    - **Not taken:** OB3's suggestion to write T306-15 as a shell command (C7, offered as "not a defect"); note 10
      keeps the check in words.

## 1. The mandate, and what is out of scope

The issue's "What must be accomplished": the payload tells disabled apart from nothing yet (`{"enabled": false}`
and nothing else when `backup_dir` is empty; enabled, the card's fields) (T306-1 to T306-5); the newest copy's schema
read without changing the copy (T306-4, T306-16); the newest pre-upgrade copy reported, or `null` (T306-6); a Backups
card below System status with the mock's five tiles (T306-8, T306-12); four states in words — disabled, no copy
yet, stale past two intervals, failing paired with the last good instant (T306-8 to T306-11); the sub-line says
"backups disabled" (T306-8); every screen, 375, 768 and 1280 px, light and dark, without horizontal overflow
(T306-13); nothing else moves — `/metrics`, the Grafana board, the KPI page's tier, RBAC, the chart (T306-7, T306-14,
T306-15); and on the lab the card's last copy and failures equal `/metrics` at the same moment (T306-17). Must not
change: no new metric, no new RBAC, no write action, no Prometheus query from the app; `/metrics`; the Grafana board;
the page's tier.

Out of scope, each owned elsewhere or by design: a backup button (dropped on #300: it needs `create` on
`batch/jobs`); the off-volume copy (its signal is the offsite CronJob's, through `GroupSyncDashboardOffsiteBackupStale`
and `…Unobserved`, #304); history beyond the process's lifetime (failures count since the process started, the
issue's decision 2); per-pod logic above one replica beyond what note 9 composes with SPEC_E4; and any change to
`/metrics` or the alerts. **Backup alerting already exists** — three Prometheus alerts
(`GroupSyncDashboardBackupStale`, and with `backup.offsite`, `GroupSyncDashboardOffsiteBackupStale` and
`GroupSyncDashboardOffsiteBackupUnobserved`, `charts/group-sync-dashboard/templates/monitoring.yaml#alert: GroupSyncDashboardBackupStale`)
and two Grafana panels ("Backup age", "Backup failures",
`charts/group-sync-dashboard/dashboards/group-sync-dashboard.json#"title": "Backup age"`). This card is the in-app
view of the same facts, for an estate without Prometheus and for the operator already on the page.

## 2. Research, measured

The probes ran with the repository's venv (Python 3.14.7) against copies of `73cc7d08`, each printing the `gsd` it
imported, writing only under this spec's scratch directory. Lab reads used `oc get`, `oc exec … ls` and a
`python3.14 -c` that reads 64 bytes, and the public `/metrics`; nothing else. Web sources were fetched on 2026-10-01
with `curl` and quoted from the raw text; upstream code lines come from `curl -s <raw-url> | nl -ba`.

### 2.1 What the page and the payload do today

`dashboard_data_bytes` (local-development/gsd/kpi/system.py:240-261) is the KPI page's only read of the backup
directory: `Path(backup_dir).glob("gsd-*.db")`, counting before the stat. `build_app` passes it the database path
and `settings.backup_dir` and nothing else (local-development/gsd/api.py:352-354). `SystemMonitor.view()` runs it
once per `/api/kpi` request (api.py:2880) and once per poll cycle (local-development/gsd/poller.py:1104), and
`page_payload` puts the result at `system.dashboard.data` (local-development/gsd/kpi/render_json.py:107-108). The
page prints it in the dashboard component's sub-line, `+ ${own.backups.count} backups …`, whenever `own.backups`
exists (local-development/gsd/static/index.html:1811). Measured on `73cc7d08` (probe `today`):

```text
disabled: {'db_bytes': 100, 'wal_bytes': 0, 'backups': {'count': 0, 'bytes': 0}}
enabled, empty: {'db_bytes': 100, 'wal_bytes': 0, 'backups': {'count': 0, 'bytes': 0}}
main, two copies and one name whose stat fails: {'count': 3, 'bytes': 12288}
```

Disabled and empty cannot be told apart, and a name whose stat fails counts without bytes. What the process
already holds, and where: the failure counter (`RuntimeSignals.note_backup_failure`, metrics.py:217-219, in
`snapshot()["backup_failures"]` at :256, exported as `gsd_backup_failures_total` at :713-759); the newest copy's mtime,
computed at scrape (metrics.py:803-825, omitted on any `OSError`); `backup_dir`, `backup_interval_hours` and
`backup_keep` (local-development/gsd/config.py:559-561); `KNOWN_SCHEMA_VERSION` (store.py:1159); the pre-upgrade
directory and its listing (`PRE_UPGRADE_DIR`, `_pre_upgrade_copies`, store.py:1177-1189). The poller makes the next
attempt due `backup_interval_hours` after the start of the last one (poller.py:990), on the first poll cycle after
that; the first attempt runs on the first cycle after start (`_next_backup = 0.0`).

### 2.2 The SQLite header, and `immutable=1`

**Source.** SQLite, "Database File Format" (sqlite.org/fileformat2.html, "This page was last updated on 2025-12-25
10:33:36Z"): the header's first field is "The header string: "SQLite format 3\000""; "All multibyte fields in the
database file header are stored with the most significant byte first (big-endian)"; and "The 4-byte big-endian
integer at offset 60 is the user version which is set and queried by the user_version pragma." Offsets 18 and 19 are
the write and read versions, "1 for legacy; 2 for WAL". SQLite, "Uniform Resource Identifiers" (sqlite.org/uri.html):
`immutable=1` "signals to SQLite that the underlying database file is held on read-only media and cannot be
modified … SQLite always opens immutable database files read-only and it skips all file locking and change
detection on immutable database files. If this query parameter … asserts that a database file is immutable and that
file changes anyhow, then SQLite might return incorrect query results and/or SQLITE_CORRUPT errors."

**On the lab** (`oc exec … python3.14 -c`, reading 64 bytes of the newest copy, 2026-10-01):

```text
gsd-20261001T111104.000930Z.db b'SQLite format 3\x00' 20 1 1
KNOWN 20 PRE_UPGRADE_DIR pre-upgrade
```

The newest copy's header reads `user_version` 20, and bytes 18 and 19 are 1 and 1: a rollback-journal file, as
`VACUUM INTO` writes it (SPEC_M1 §2.1 measured the same), so no `-wal` belongs to it and the header is the whole
truth about its schema. What this settles: both reads write nothing; the header read needs no SQLite connection at
all, which is what the storage seam allows in `gsd/kpi/` (Orchestrator's notes, 3).

### 2.3 Absolute instants on this page

The page's rule, in its own words (local-development/gsd/static/index.html:656-672): "THE SERVER STATES AN INSTANT;
THE PAGE PRESENTS IT (#271, and the operator's ruling of 2026-09-21 that an absolute stamp is the right thing for a
server to emit)"; "a relative age recomputed per request is a different string every time and defeats the
unchanged-poll repaint skip"; "an absolute stamp in raw UTC ignores the deployment's configured zone, which every
other timestamp on this page honours, so the page localises it at RENDER time". `fmtTime` renders in the server's
zone with its label, and "Falls back to UTC when the server reports no zone — an explicit UTC beats a guess"
(index.html:602-650). The KPI page today shows `updated <ago>` (a live age, client-side, from `as_of`), dates as
`slice(0, 10)` and the oldest sync as an age; it shows no absolute time-of-day yet. What this settles: the payload
carries ISO-8601 UTC; the card shows `fmtTime`'s zone-labelled instant, never an age (Orchestrator's notes, 5).

### 2.4 The lab (read-only, 2026-10-01)

```text
$ curl -sk https://group-sync-dashboard.apps-crc.testing/metrics | grep -E '^gsd_backup'     (at 2026-10-01T15:31:50Z)
gsd_backup_failures_total 0.0
gsd_backup_last_success_timestamp_seconds 1.7908530643803718e+09        = 2026-10-01T11:11:04.380372Z
$ oc exec … -c dashboard -- ls -la --time-style=full-iso /data/backup /data/pre-upgrade
ls: cannot access '/data/pre-upgrade': No such file or directory
-rw-rw-r--. 1 1000790000 1000790000 14184448 2026-09-30 19:09:06.771666652 -0400 gsd-20260930T230906.692903Z.db
-rw-r--r--. 1 1000790000 1000790000 14188544 2026-09-30 19:10:05.571879437 -0400 gsd-20260930T231004.994977Z.db
-rw-r--r--. 1 1000790000 1000790000 14204928 2026-10-01 01:11:04.282620960 -0400 gsd-20261001T051103.798578Z.db
-rw-r--r--. 1 1000790000 1000790000 14221312 2026-10-01 07:11:04.380371903 -0400 gsd-20261001T111104.000930Z.db
$ oc get configmap group-sync-dashboard-config -o jsonpath='{.data.clusters\.yaml}' | grep -n 'backup\|replicaCount'
9:backupDir: "/data/backup"
10:backupIntervalHours: 6
11:backupKeep: 4
92:replicaCount: 1
$ oc get deploy group-sync-dashboard -o jsonpath='…env[?(@.name=="TZ")]…'
dashboard America/New_York
```

The metric is the newest file's mtime (07:11:04.380371903 −04:00 is 11:11:04.380372Z). There is no `pre-upgrade/` on
the lab: the volume has not crossed a migration since #301 shipped, so its card will show "none" in that tile. At
this moment the card would read: healthy, last copy `2026-10-01 07:11:04 EDT`, next due by `13:11:04 EDT`, 4/4 kept,
54Mi (the four sizes sum to 56,799,232 bytes), 0 failures, schema 20/20.

### 2.5 Use of colour

**Source.** WCAG 2.2 (W3C Recommendation 12 December 2024, w3.org/TR/WCAG22/), Success Criterion 1.4.1 Use of Color
(Level A): "Color is not used as the only visual means of conveying information, indicating an action, prompting a
response, or distinguishing a visual element." Understanding SC 1.4.1 (w3.org/WAI/WCAG22/Understanding/use-of-color.html):
"Use information in addition to color, such as shape or text, to convey meaning." The page's `.badge` already pairs a
shape with a word (app.css: "State badge: shape + colour + text. Colour is never the only channel."), and
`test_status_is_never_colour_alone_and_the_mark_sits_at_the_threshold` holds every `.kpi-page .badge` to a word and a
glyph. What this settles: each state is a word on a badge (`healthy`, `no copy yet`, `failing`, `stale`,
`backups are disabled`); the tiles' coloured rails repeat what the state line already says in words.

### 2.6 How other backup tools show their status

- **Velero** (v1.18.4, released 2026-09-28; `pkg/metrics/metrics.go` lines 117-124 and 156-163): the gauge
  `backup_last_successful_timestamp`, "Last time a backup ran successfully, Unix timestamp in seconds", and the
  counter `backup_failure_total`, "Total number of failed backups", per schedule: the same pairing as
  `gsd_backup_last_success_timestamp_seconds` and `gsd_backup_failures_total`. Its `Schedule` status carries
  `LastBackup` ("the last time a Backup was run for this Schedule schedule", `pkg/apis/velero/v1/schedule_types.go`
  lines 79-83) and a `Paused` print column beside `Status`, `Schedule` and `LastBackup` (lines 102-106): a paused
  schedule is its own state, not a failure.
- **OpenShift API for Data Protection** (OADP, docs.redhat.com, OpenShift Container Platform 4.14, "OADP Application
  backup and restore"): the operator's status surface is Velero's resources, read with `oc`: "Verify that the status of
  the Backup CR is Completed", with `oc get backups.velero.io -n openshift-adp <backup> -o jsonpath='{.status.phase}'`.
  The same page says to verify a Schedule's phase is `Completed`, while Velero's `SchedulePhase` values are `New`,
  `Enabled` and `FailedValidation` (schedule_types.go lines 60-70): a reminder to read the state from its source.
- **Veeam Kasten** (docs.kasten.io/usage/overview.html, "Dashboard Overview"): three categories per object —
  "Unmanaged : There are no protection policies that cover this object"; "Non-compliant : A policy applies to this
  object but the actions associated with the policy are failing … or the actions haven't been invoked yet (e.g.,
  right after policy creation)"; "Compliant : Objects that both policies apply to and the policy SLAs are being
  respected".
- **Kubernetes CronJob** (`k8s.io/api` v0.35.0, `batch/v1/types.go` lines 746-749 and 791-797): `suspend` ("This
  flag tells the controller to suspend subsequent executions") beside `lastScheduleTime` and `lastSuccessfulTime`,
  which the offsite alerts already read through kube-state-metrics.

What this settles: every one of them shows the last success as an instant and separates "off" (Velero's `Paused`,
Kasten's `Unmanaged`, a suspended CronJob) from "failing". Kasten folds "not run yet" into non-compliant; this card
keeps it separate, as the issue requires, because a pod that has just started has no copy for a minute and that is
not a failure.

### 2.7 Measuring the read budget: the interpreter's audit events

**Source.** Python, "Audit events table" (docs.python.org/3.14/library/audit_events.html): "This table contains all
events raised by sys.audit() or PySys_Audit() calls throughout the CPython runtime and the standard library", among
them `open` (`path, mode, flags`), `os.scandir` (`path`), `os.listdir` (`path`) and `pathlib.Path.glob`
(`self, pattern`). PEP 578: "Hooks cannot be removed or replaced." CPython 3.11.13, the floor CI tests: `Path.glob`
lists through `_scandir`, which is `return os.scandir(self)` (`Lib/pathlib.py` lines 934-938), and `FileIO` raises
`PySys_Audit("open", "Osi", nameobj, mode, flags)` (`Modules/_io/fileio.c` line 361). Measured on 3.14.7 (probe
`audit`): one `glob` of a directory raised one `os.scandir` of it, a `pathlib.Path.glob`, and one `open` per file read,
with mode `r` and flags `16777216` (`O_CLOEXEC`).

What this settles: T306-16 counts the listings and opens of one `view()` without patching the code under test, and
runs in a child process, so no hook outlives the test.

## 2a. Alternatives considered

| option | source | what it would cost here | decision |
|---|---|---|---|
| **The process's own facts in `/api/kpi`, one card on the KPI page** | the issue; the epic (2026-09-26: "#306 reads the pod's own values") | one walk extended, two readers in `store.py`, one card, docs | **chosen** |
| Query Prometheus from the app (the original description, then the 2026-09-22 correction) | the issue's comments | a Prometheus client, a URL and credentials per estate, and "no data" on every estate without monitoring, which is the reference cluster (`docs/specs/README.md`, "Monitoring, parked") | rejected: superseded by the epic's decision; the metrics stay the alerting path |
| A new metric or a new `/api/backups` route | — | the issue's "no new metric"; a new route needs its tier declared in `ACCESS_CONTROL.md` §3 and a test per persona (SPEC_G1) | rejected; the KPI payload is already the cluster-admin tier |
| Read `newest_schema` with `sqlite3.connect("file:…?immutable=1&mode=ro")` | sqlite.org/uri.html; the report service (`local-development/gsd/reporting/snapshot.py#Snapshot`) | an engine import in `gsd/kpi/`, which the seam test refuses; a connection where 64 bytes answer | rejected; the header read, in `store.py` (notes, 3) |
| A second listing of `backup_dir` for the card (or E4's `backup_copies`, which lists again) | — | two reads of one directory per view, and two answers when a rotation runs between them | rejected: one walk, every figure from it (§3.8) |
| A state computed server-side (`"state": "stale"`) | — | the server would need the page's clock rule and a now-dependent field in the payload; a browser test could not drive a state without a fake server clock | rejected: the page derives it from `as_of`, the clock the sparklines use (notes, 4) |
| Raw UTC text, as the mock prints it | the mock | the one time on the page not in the configured zone (§2.3) | rejected; zone-labelled `fmtTime` text, UTC in `datetime` (notes, 5) |
| A state strip listing all four states, as the mock's lower half | the mock ("How the other states read (proposed)") | a legend of states that are not in force reads as four alarms | rejected: the mock's strip explains the design; the page shows the one state in force |
| Fold "no copy yet" into "failing", as Kasten does | §2.6 | a fresh pod would read as failing for its first poll cycle | rejected; four states plus healthy, as the issue requires |
| Persist failures across restarts | — | a write path for a read-only card; the issue's decision 2 | rejected: since the process started, with that instant shown |

**Reconciliation, research against this repository's code:**
- fileformat2's offset-60 user version and the "SQLite format 3\000" magic: `copy_schema`
  (`local-development/gsd/store.py#copy_schema`, block 2) reads 64 bytes, checks the magic and returns
  `int.from_bytes(header[60:64], "big")`; SPEC_M1's copy check reads the same number through
  `PRAGMA user_version` (`local-development/gsd/store.py#_pre_upgrade_copy`), and T306-4 holds the two equal on a
  real `VACUUM INTO` copy.
- The header is the whole truth only for a file with no `-wal`: `_vacuum_into` writes every backup with `VACUUM INTO`
  under a `.tmp` name and renames it (`local-development/gsd/store.py#Store._vacuum_into`), and the lab's newest copy
  reads 1, 1 at offsets 18 and 19 (§2.2). `copy_schema` is never called on the live database.
- uri.html's "SQLite always opens immutable database files read-only": not relied on here; the card opens no SQLite
  connection, and T306-16 asserts no `sqlite3.connect` event under the data directory.
- The page's "THE SERVER STATES AN INSTANT; THE PAGE PRESENTS IT": the payload's `newest_at`, `failures_since` and
  `pre_upgrade.at` are `strftime("%Y-%m-%dT%H:%M:%SZ")` (`local-development/gsd/kpi/system.py#dashboard_data_bytes`,
  `local-development/gsd/store.py#newest_pre_upgrade`), and `kpiInstant` shows each through `fmtTime` in a
  `<time datetime>` (block 8).
- WCAG 1.4.1: `kpiBackupState` returns a word for every state and `kpiBackups` puts it on a `.badge` with its glyph
  (block 8); the existing `test_status_is_never_colour_alone_and_the_mark_sits_at_the_threshold` now covers the card's
  badge too.
- Velero's last-success-plus-failures pairing: the card shows `failures` beside `newest_at`, and the failing state
  pairs them in one sentence ("3 failures since start; last good copy …"), the pairing
  `gsd_backup_failures_total`'s help text prescribes (local-development/gsd/metrics.py:714-717).
- The audit events: T306-16's child process records `os.scandir`, `os.listdir`, `pathlib.Path.glob` and `open`
  under the data directory and asserts exactly two listings and one read-only open (block 16).

## 3. The design

### 3.1 The payload

`/api/kpi`'s `system.dashboard.data` becomes `{"db_bytes", "wal_bytes", "backups", "pre_upgrade"}`:

- `backups` is `{"enabled": false}` and nothing else when `backup_dir` is empty (the chart omits `backupDir` when
  `config.backup.enabled` is false, `charts/group-sync-dashboard/templates/configmap.yaml#backupDir: {{ .Values.config.backup.dir | quote }}`).
- Enabled: `enabled`, `dir`, `count`, `bytes`, `kept`, `newest_at`, `newest_schema`, `known_schema`, `failures`,
  `failures_since`, `keep`, `interval_hours` (each defined in `local-development/API.md`, block 21).
- `pre_upgrade` is `{"at", "from", "to"}` of the newest pre-upgrade copy, or `null` (Orchestrator's notes, 1).

The KPI payload is already cluster-admin only (`local-development/gsd/api.py#require_cluster_admin`, #322); nothing
here changes who reads it. `dir` is the configured path, the same string `config.backup.dir` holds.

### 3.2 One walk

`dashboard_data_bytes` keeps its one glob of `backup_dir` and stats each `gsd-*.db` once; a file counts toward
`count`, `bytes` and `kept`, and competes for newest, only when its stat succeeds (notes, 6). `newest_at` is the
newest mtime (the metric's rule), formatted to the second; `newest_schema` is `copy_schema` of that one file.
`failures` calls the reader `build_app` passes (`signals.snapshot()["backup_failures"]`, the counter `/metrics`
exports); `failures_since` is the instant `dashboard_data_bytes` was called, in `build_app`; `keep` and
`interval_hours` are `settings.backup_keep` and `settings.backup_interval_hours`. The new arguments are keywords
with defaults, so the two existing callers in tests and SPEC_E4's keep their calls.

### 3.3 The schema reader

`copy_schema(path)` in `store.py`: open, read 64 bytes, close; `None` if the read fails, the file is shorter, or the
magic is not SQLite's. `known_schema` is `KNOWN_SCHEMA_VERSION`. A copy whose schema is above it is one this image
cannot restore (#305 would refuse it); the card flags that tile critical and says so.

### 3.4 The pre-upgrade reader

`newest_pre_upgrade(db_path)` in `store.py`: `_pre_upgrade_copies(<db dir>/pre-upgrade)` (its existing sorted glob,
`pre-upgrade-*.db`, which a `.sha256` sidecar or a `.db.tmp` does not match), newest by name first, the first whose
name `PRE_UPGRADE_NAME` matches: `pre-upgrade-<stamp>-schema-<from>-to-<to>-<pod>.db` (SPEC_M1 §3.2). The stamp is
read from the name, not the mtime, as SPEC_M1's pruning reads it. Nothing is opened.

### 3.5 The card

`kpiBackups(k)` renders a `section.card.kpi-page[data-card="backups"]` between System status and Access posture:

- the heading, `Backups`, and `on-volume · <dir> · every <interval> h · keep <keep>` (or `on-volume · disabled`);
- one state line, `.bk-state[data-state]`: the badge with the state's word and glyph, and one sentence;
- the tiles, on the band's hairline grid (`.kband.bk`), with `kpiTile`'s ids: `backup-last` (the time, then the
  date and "next due by"), `backup-kept` (`kept`/`keep`, the size on the volume, and "N copies in all" when `count`
  differs; with `keep` 0, which rotates nothing away, no ceiling and "keep all" in the heading), `backup-failures` ("since start <instant>"), `backup-schema` (`newest_schema`/`known_schema`) and
  `backup-preupgrade` (`<from> → <to>`, its instant, "kept outside the rotation", or "none");
- the rule line: where every figure comes from, that no Prometheus is read, the stale line, and that the off-volume
  copy is the CronJob's.

Disabled keeps one tile, the pre-upgrade copy. A missing data block (the database's stat failed) renders the card
with an `unavailable` badge and no tiles. `kpiTile` remembers each value, so a changed figure pulses on the
60-second repaint and an unchanged one does not.

### 3.6 The states

One state, the most severe that holds, from `kpiBackupState(b, as_of, due)`:

| state | when | badge | the sentence |
|---|---|---|---|
| disabled | `enabled` is false | `backups are disabled` (unknown) | no backup directory is configured, so this process takes no copies: a setting, not a failure; to take them, set `config.backup.enabled: true` in this release's values file and roll it out through the release's deployment pipeline |
| stale | `as_of − newest_at` > 2 × `interval_hours` | `stale` (critical) | last copy <instant>, past <2 × interval> h (two intervals of <interval> h); and the failures, if any |
| failing | `failures` > 0 | `failing` (warning) | N failures since start; last good copy <instant> (or "no good copy yet") |
| no copy yet | no `newest_at` | `no copy yet` (unknown) | the first copy is taken on the first poll cycle after this process started (<instant>) |
| healthy | otherwise | `healthy` (ok) | last copy <instant>; next due by <instant> |

"Next due by" is `newest_at + interval_hours`: the poller makes the next attempt due `interval_hours` after the last
attempt started (§2.1), which is no later than the copy's mtime, and runs it on the next poll cycle. Stale wins over
failing because a stale copy is the consequence the failures are a cause of; the stale sentence still counts them.

### 3.7 Styles and screens

Tokens and ladder steps only, beside the KPI page's rules in `app.css`: `.bk-state` (flex, wrapping, the badge
allowed to wrap), `.kband.bk` (five columns; three at 980 px and below with the fifth spanning two; two at 560 px and
below with the fifth spanning the row), `.kband.bk.one` (one column), and `.bk-rule`. The mock-only rules (the
PROPOSED banner, the outline, `.ptag`, `.abridged`, the state strip) are not carried. Render-checked at 375, 768 and
1280 px, light and dark, in every state (§4.3).

### 3.8 The budget, over the system, with its scope

Scope: one dashboard process, its `SystemMonitor`, its data directory (the directory of `GSD_DB_PATH`) and
`config.backup.dir`. This change writes nothing.

- **Each `SystemMonitor.view()`** — one per `/api/kpi` request (api.py:2880) and one per poll cycle (poller.py:1104) —
  **lists `config.backup.dir` once and `<data dir>/pre-upgrade` once, opens at most one file (the newest copy) once,
  read-only, for 64 bytes, and makes no other file access under either directory and no network call.** The stats of
  the database, its `-wal` and each listed copy are reads the code already made (the first two) or makes once per file.
- It never opens a SQLite connection, never creates a `-wal` or `-shm`, never changes a copy's bytes or mtime.
- At the defaults (a 60-second poll, four copies) that is two directory listings and one 64-byte read a minute, plus
  the same per page load.

The table, by event:

| event | listings | opens | writes | evidence |
|---|---|---|---|---|
| one `view()` with copies and a `pre-upgrade/` | `backup/` once, `pre-upgrade/` once | the newest copy, `r`, no write flag | none | T306-16 (audit events, child process) |
| a real `VACUUM INTO` copy read | — | — | sha256 and mtime unchanged, no `-wal`/`-shm` | T306-4 |
| backups disabled | `pre-upgrade/` once | none | none | from the code: the glob runs only `if backup_dir` |
| a copy rotated away during the walk | — | that file not opened | none | T306-3 (counted in neither `count` nor `bytes`) |
| `/metrics` scraped around the walk | — | — | the exposition unchanged | T306-14 |

**Outside the scope, named:** the poller's backup itself (`Store.backup`, unchanged), the metric's own scrape-time
glob (metrics.py:811-825, unchanged), and the report service, which builds its own `SystemMonitor` with
`artifact_bytes` and never calls this walk.

### 3.9 What does not change

`/metrics` (every family, label and value; T306-14); the Grafana board and the alerts; the KPI page's tier; every
RBAC rule; the chart, but for the release script's version lines (notes, 10); `config.backup.*` and their defaults;
the backup, its names, its rotation; the pre-upgrade copy's writer.

## 4. Tests

### 4.1 One test per issue test case

| ID | test (file) | fails without the change because |
|---|---|---|
| T306-1 | `test_t306_1_disabled_is_enabled_false_and_nothing_else` (`test_kpi.py`) | `assert {'count': 0, 'bytes': 0} == {'enabled': False}` |
| T306-2 | `test_t306_2_enabled_with_no_copy_yet_is_told_apart_from_disabled` | `KeyError: 'enabled'`: the empty directory reads as the disabled case |
| T306-3 | `test_t306_3_count_bytes_and_newest_at_describe_the_same_files_as_the_metric` (also: a name whose stat fails is in neither `count` nor `bytes`, and `newest_at` equals the metric's value in UTC) | `KeyError: 'kept'`: no `kept`, no `newest_at`; and the count-before-stat walk counts the dangling name (§2.1) |
| T306-4 | `test_t306_4_the_newest_schema_is_read_without_touching_the_copy` (a real `Store.backup` copy) | `KeyError: 'newest_schema'` |
| T306-5 | `test_t306_5_failures_keep_and_interval_come_from_the_process` (through `/api/kpi`, two `note_backup_failure()` calls) | `KeyError: 'failures'` |
| T306-6 | `test_t306_6_the_newest_pre_upgrade_copy_by_name_or_null` (two copies with sidecars, then none) | `KeyError: 'pre_upgrade'` |
| T306-7 | the existing `TestApi.test_administrator_tier_only` (`test_kpi.py`) and `local-development/tests/test_cluster_admin_tier.py` | a regression guard: passes before and after; no test is added for it |
| T306-8 | `TestKpiPage.test_t306_8_disabled_reads_disabled_never_zero` (`test_ui.py`; the harness's own payload) | no card: `Locator.get_attribute` times out on `.bk-state`; the sub-line read `+ 0 backups` |
| T306-9 | `test_t306_9_enabled_with_no_copy_reads_no_copy_yet` (also: `keep` 0 shows no "/0" and the heading says "keep all") | no card |
| T306-10 | `test_t306_10_older_than_two_intervals_reads_stale_with_the_instant` | no card |
| T306-11 | `test_t306_11_failures_are_paired_with_the_last_good_instant` (also: failing with no copy at all, the Last copy tile reads "the attempts since start are failing", N1) | no card; on the reviewed draft's block 8, `AssertionError: the first poll cycle takes one` |
| T306-12 | `test_t306_12_five_tiles_absolute_instants_and_the_repaint_keeps_the_card` (the route serves a healthy payload; `refresh()` runs the poll and the card is checked again; the display zone switched to America/New_York relabels the same instants) | no card |
| T306-13 | `test_t306_13_every_state_fits_375_768_and_1280_in_light_and_dark` (five states × three widths × two themes; the state drawn is the one set, so a 60-second auto-refresh landing mid-loop cannot pass a check on the wrong card; `scrollWidth == clientWidth` for the page, the card within itself, no page error) | no card |
| T306-14 | `TestCaptureAndBackupGauges.test_t306_14_the_backups_card_leaves_the_exposition_as_it_was` (`test_metrics.py`) | a regression guard: passes before and after |
| T306-15 | the pull request's own check, `git diff --name-only main -- charts/` = `charts/group-sync-dashboard/Chart.yaml`, and that file's diff only the release script's lines (notes, 10) | a regression guard; no block touches `charts/` |
| T306-16 | `test_t306_16_one_view_lists_two_directories_opens_one_copy_and_writes_nothing` (`test_kpi.py`) | `assert ['…/backup'] == ['…/backup', '…/pre-upgrade']`: no pre-upgrade listing today |
| T306-17 | the lab walk, §5 step 3 | — |

Changed, not new: `test_own_bytes_ride_the_view` asserts the four figures it is about instead of the whole data
dict (block 15), and `test_the_five_sections_render_from_the_payload` expects the Backups heading second and counts
the access-posture band apart from the card's (block 18).

### 4.2 Each test, before and after

**Before**, on a clean worktree of origin/main `6d532178` with the three changed test modules copied in, `PYTHONPATH`
at its `local-development`:

| run | result |
|---|---|
| `pytest tests/test_kpi.py tests/test_metrics.py -k 't306 or own_bytes'` | `7 failed, 2 passed`: T306-1 to T306-6 and T306-16 fail for the reasons in §4.1; T306-14 (a guard) and `test_own_bytes_ride_the_view` pass |
| `pytest tests/test_ui.py -k TestKpiPage --browser chromium --tb=line` | `7 failed, 16 passed`: T306-8 to T306-11 and T306-13 on `Locator.get_attribute: Timeout 30000ms exceeded` (no `.bk-state`), T306-12 on `Page.wait_for_selector: Timeout 10000ms exceeded`, and the changed `test_the_five_sections_render_from_the_payload` on its headings list; the other sixteen KPI-page tests pass |

**After** `--apply` (§4.3): the same unit selection `9 passed`, and `TestKpiPage` `23 passed`.

**Mutations** of the implemented code, each in a scratch copy of the implemented `local-development`: M1 to M6
run against `test_kpi.py` and `test_metrics.py` (`-k 't306 or own_bytes or TestCgroupSampler'`, 20 tests, the other
19 or 18 passing), M7 and M8 against the browser test named:

| run | the change | tests that go red |
|---|---|---|
| M1 | `count` before the stat, as today's walk | T306-3 |
| M2 | the disabled block keeps `count` and `bytes` | T306-1 |
| M3 | `pre_upgrade` only with backups on | T306-6 |
| M4 | `copy_schema` through `sqlite3.connect(…mode=ro)` and `PRAGMA user_version` | T306-16 (a `sqlite3.connect` event under the data directory) |
| M5 | the oldest pre-upgrade copy instead of the newest | T306-6 |
| M6 | a second glob of `backup.dir` for the newest copy | T306-3, T306-16 |
| M7 | stale measured against `Date.now()` instead of the payload's `as_of` (in `index.html`, against T306-10) | T306-10 (`assert 'stale' == 'ok'` for a payload three days behind the browser) |
| M8 | block 7 reverted: the Data volume meter sums `own.backups.bytes` whenever `own.backups` exists (against T306-8) | T306-8 (`assert 'NaN' not in 'NaNKi · node disk 47% full'`) |

### 4.3 The proof

§7 was not written by hand. The design was implemented in a detached copy of `73cc7d08`; a generator cut each block's
Old text from `73cc7d08` and its New text from the implemented copy, at whole lines, with the fewest context lines
(two of them carrying text) that make the Old text unique once the earlier blocks for the file are applied, and two
blocks (the CHANGELOG's and the design README's) were narrowed by hand to the one line they change, because their
neighbours are lines other specs in flight edit. It then checked that the blocks, applied in order, give the
implemented files byte for byte: `24 blocks across 12 files reproduce the dev copy byte for byte`. On the reviews
of `1e194df3` (Orchestrator's notes, 13), blocks 8 and 24 were taken whole from OB3's patch and block 19 gained N1's
assertion; the 24 Old texts are unchanged and check out on origin/main `6d532178`. Then:

On a fresh detached worktree of origin/main `6d532178` with this spec's commit content committed on it (the spec, the index row and the index
test), with `PYTHONPATH` at its `local-development` (the imported `gsd` printed as that tree's, `2.0.0`):

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E6_kpi_backups_card.md .
    24 blocks check out across 12 files
    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E6_kpi_backups_card.md . --apply

After `--apply` every changed file is identical (`cmp`) to the implemented copy.

| check | command | result |
|---|---|---|
| the new and changed tests | `pytest tests/test_kpi.py tests/test_metrics.py -k 't306 or own_bytes'`; `pytest tests/test_ui.py -k TestKpiPage --browser chromium` | `9 passed`; `23 passed` |
| the modules the change touches | `pytest tests/test_kpi.py tests/test_metrics.py tests/test_storage_seam.py tests/test_pre_upgrade_copy.py tests/test_type_scale.py tests/test_accessibility.py tests/test_docs_citations.py tests/test_specs_index.py tests/test_cluster_admin_tier.py` | `2509 passed, 22 skipped` |
| hermetic suite | `pytest tests/ -q -p no:cacheprovider --deselect tests/test_ui.py --deselect tests/test_live_smoke.py` | `6361 passed, 26 skipped, 661 deselected, 5 xfailed` in 301.97 s; `6d532178` without the spec or the blocks collects 6365, so 27 more: the eight new tests, and the citation, fence and index checks of this spec's own text and row |
| browser suite | `pytest tests/test_ui.py -q -p no:cacheprovider --browser chromium` | `657 passed` in 233.84 s; on `6d532178` the suite collects 651 |
| Python 3.11 | `ast.parse(source, feature_version=(3, 11))` on `store.py`, `kpi/system.py`, `api.py` and the three test modules | all parse; CI's 3.11 job was not run here. T306-16's audit events exist on 3.11 (§2.7) |
| render check | the card in every state at 375, 768 and 1280 px, light and dark, with no zone (UTC), `America/New_York` and `Asia/Kolkata`, screenshotted from the browser harness on the revised block 8, the state drawn checked against the state set | 90 renders, the page's `scrollWidth == clientWidth` and the card's `scrollWidth <= clientWidth` in all 90; looked at: the healthy card at 375 px light in Kolkata time (the zone label wraps under the time, never sideways) and the failing card at 1280 px dark in New York time |
| markdown | `markdownlint-cli2` on `docs/CHANGELOG.md`, `docs/RUNBOOK_backup_restore.md`, `docs/design/README.md`, `local-development/API.md`, and the specs index | the same findings before and after, per file and rule (CHANGELOG MD012 ×1; runbook MD004 ×3, MD040 ×3; API.md MD004 ×2, MD012 ×1, MD018 ×1), all on main already; the index README: 0 |
| the order against SPEC_E4 | E4's 32 blocks checked and applied on `6d532178` + this spec; this spec's 24 checked and applied on `6d532178` + E4 | both check out, and the two trees differ only in the order of the two CHANGELOG entries (`git ls-files -s` diffed); on `6d532178` + E4 + E6, `1 failed, 1893 passed, 22 skipped` (E4's T391-8), and with note 9's five edits, `1896 passed, 22 skipped` (Orchestrator's notes, 9) |
| chart and RBAC | no block touches `charts/` | nothing to render; the RBAC diff is the implementing pull request's (§5 step 5) |

The implemented copy, the generator, the probes and the screenshots ran from this spec's scratch directory and are
not committed.

## 5. On the lab (the implementing pull request)

Not run in this phase: the lab is read-only here. The implementing pull request deploys its head with
`local-development/release-crc.sh` (development), and the walk is committed under `reports/<date>_kpi-backups-306/`
with the screenshots:

1. **Before.** Record the UIDs of `group-sync-dashboard-data` (`f065b7a4-535c-4ef1-868c-58f5afee4953`) and
   `group-sync-dashboard-report-artifacts` (`08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`).
2. **The KPI page as a cluster-admin persona.** The Backups card below System status; the state `healthy` unless the
   newest copy is older than 12 h; the tiles at 375, 768 and 1280 px, light and dark (T306-13's lab half); no
   horizontal scroll.
3. **T306-17, within the same minute.** Read the card's `[data-kpi="backup-last"] time[datetime]` and the
   Failures tile with Playwright, and `curl -sk https://group-sync-dashboard.apps-crc.testing/metrics | grep -E '^gsd_backup'`.
   The `datetime` equals `gsd_backup_last_success_timestamp_seconds` truncated to the second in UTC, and the Failures
   value equals `gsd_backup_failures_total`. Compare at the walk, never with a recorded value (the issue's
   correction).
4. **The schema and the pre-upgrade tile.** `oc exec … python3.14 -c` reading 64 bytes of the newest copy, as §2.2:
   the tile's `newest_schema` equals offset 60; `ls /data/pre-upgrade` (absent today): the tile reads "none".
5. **Nothing else moved.** `/metrics` family names before and after the deploy, diffed (only values move);
   `git diff --name-only <merge base> -- charts/` per T306-15; the dashboard ServiceAccount's rendered RBAC rules
   before and after: REMOVED 0, ADDED 0 (`reports/2026-09-27_epic-c-walk/scripts/rbac_rules.py`).
6. **The disabled state** is shown from the browser harness (T306-8), because the lab keeps backups on.
7. **After.** The two PVC UIDs again: unchanged.

## 6. What an operator sees, and what it costs

- **On the KPI page** (cluster-admin only), below System status: a Backups card that says, in one word, whether the
  on-volume backup is working, when the last copy was taken and when the next is due (in the page's zone, labelled),
  how many copies are kept against `keep` and how much room they take, how many attempts failed since the pod
  started, whether the newest copy is one this image can restore, and the newest pre-upgrade copy.
- **With backups off**: "backups are disabled" on the card and "backups disabled" in the size line, never "0 backups".
- **Without Prometheus**: the same card. With Prometheus: the same facts as `GroupSyncDashboardBackupStale` and the
  board's two panels, which still do the paging.
- **Cost:** per `view()`, two directory listings and one 64-byte read (§3.8); the payload grows by about 300 bytes;
  no new permission, metric, value or object.
- **Code:** the table below, from `git diff --numstat` on the applied copy (§4.3).

| file | added | removed |
|---|---|---|
| `local-development/gsd/store.py` | 33 | 0 |
| `local-development/gsd/kpi/system.py` | 43 | 7 |
| `local-development/gsd/api.py` | 6 | 1 |
| `local-development/gsd/static/index.html` | 93 | 2 |
| `local-development/gsd/static/app.css` | 18 | 0 |
| `local-development/tests/test_kpi.py` | 156 | 1 |
| `local-development/tests/test_metrics.py` | 31 | 0 |
| `local-development/tests/test_ui.py` | 153 | 2 |
| `local-development/API.md` | 29 | 1 |
| `docs/RUNBOOK_backup_restore.md` | 6 | 0 |
| `docs/design/README.md` | 1 | 1 |
| `docs/CHANGELOG.md` | 11 | 0 |
| total | 580 | 15 |

## 7. Implementation blocks

Applied in this order: blocks 1 to 6 are the server (`store.py`, `kpi/system.py`, `api.py`), 7 to 13 the page
(`index.html`, `app.css`), 14 to 19 the tests, 20 to 24 the documents. None carries a version field
(Version note).

### Block 1 — local-development/gsd/store.py: `re`, for the pre-upgrade name

`PRE_UPGRADE_NAME` below is a regular expression (§3.4).

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
import os
import json
import shutil
import socket
```

New text:

```python
import os
import json
import re
import shutil
import socket
```

### Block 2 — local-development/gsd/store.py: `PRE_UPGRADE_NAME`, `newest_pre_upgrade` and `copy_schema`

The store owns the file format and the pre-upgrade layout, so the two readers live beside `_pre_upgrade_copies` (§3.3, §3.4; Orchestrator's notes, 3).

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
    """The copies in `directory`, oldest first."""
    return sorted(directory.glob("pre-upgrade-*.db"))

```

New text:

```python
    """The copies in `directory`, oldest first."""
    return sorted(directory.glob("pre-upgrade-*.db"))


#: The name _pre_upgrade_copy gives a copy, read back for the KPI page (#306): the stamp, the schema it was
#: taken at and the schema the migration went to. The pod after them is not read.
PRE_UPGRADE_NAME = re.compile(r"pre-upgrade-(\d{8}T\d{6}\.\d{6}Z)-schema-(\d+)-to-(\d+)-.+\.db")


def newest_pre_upgrade(db_path: str) -> dict | None:
    """The newest pre-upgrade copy beside the database, read from its name (#306): `{"at", "from", "to"}`,
    `at` in ISO-8601 UTC to the second. One listing of the directory; no copy is opened. None when there is
    no copy (the directory exists only once a migration has run on this volume)."""
    for copy in reversed(_pre_upgrade_copies(Path(db_path).parent / PRE_UPGRADE_DIR)):
        if (match := PRE_UPGRADE_NAME.fullmatch(copy.name)) is not None:
            at = datetime.strptime(match.group(1), "%Y%m%dT%H%M%S.%fZ")
            return {"at": at.strftime("%Y-%m-%dT%H:%M:%SZ"), "from": int(match.group(2)), "to": int(match.group(3))}
    return None


def copy_schema(path: str | Path) -> int | None:
    """A copy's schema, `PRAGMA user_version`, read from the file's header rather than through SQLite (#306):
    the 4-byte big-endian integer at offset 60 (sqlite.org/fileformat2.html). Exact for a backup or a
    pre-upgrade copy, which VACUUM INTO writes whole, in rollback-journal mode, with no -wal; not for the live
    database, whose -wal may hold a newer first page. One read-only open of 64 bytes: no lock, no -wal or
    -shm, nothing written. None when the file cannot be read or is not an SQLite database."""
    try:
        with open(path, "rb") as fh:
            header = fh.read(64)
    except OSError:
        return None
    if len(header) < 64 or not header.startswith(b"SQLite format 3\x00"):
        return None
    return int.from_bytes(header[60:64], "big")

```

### Block 3 — local-development/gsd/kpi/system.py: the imports the walk uses

`Callable` for the counter's reader, `datetime` for the instants, and the store's three names (§3.2).

<!-- block: local-development/gsd/kpi/system.py | edit -->

Old text:

```python
import threading
import time
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)
```

New text:

```python
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ..store import KNOWN_SCHEMA_VERSION, copy_schema, newest_pre_upgrade

log = logging.getLogger(__name__)
```

### Block 4 — local-development/gsd/kpi/system.py: `dashboard_data_bytes` takes the settings and the counter

Keyword arguments with defaults, so every existing caller (two tests and SPEC_E4's) keeps its call (§3.2).

<!-- block: local-development/gsd/kpi/system.py | edit -->

Old text:

```python
        return view or None


def dashboard_data_bytes(db_path: str, backup_dir: str | None):
    """The dashboard's own bytes: the database file, its WAL, and the backups — what
    `gsd_sqlite_wal_bytes` and the backup gauge already say, gathered for the page."""
    def measure() -> dict | None:
        try:
```

New text:

```python
        return view or None


def dashboard_data_bytes(db_path: str, backup_dir: str | None, *, keep: int | None = None,
                         interval_hours: float | None = None, failures: Callable[[], int] | None = None):
    """The dashboard's own bytes: the database file, its WAL, and the backups — what
    `gsd_sqlite_wal_bytes` and the backup gauge already say, gathered for the page — and the KPI page's
    Backups card (#306), from what this process already has.

    `backups` is `{"enabled": False}` and nothing else when no backup directory is configured: disabled is
    not "0 backups". Enabled, it is ONE walk of the directory's gsd-*.db (the size line's own glob): each file
    stat'd once and counted only when its stat succeeds, so `count` and `bytes` describe the same files (a
    copy rotated away between the glob and the stat is in neither). `count` and `bytes` are every copy on the
    volume; `kept`, `newest_at` and `newest_schema` are this process's own copies, the ones its rotation keeps
    to `keep`: today every gsd-*.db, so `kept` equals `count`. `newest_at` is the newest own file's mtime, the
    rule of `gsd_backup_last_success_timestamp_seconds`, and `newest_schema` is read from that one file's
    header without opening it in SQLite. `failures` is the counter /metrics exports, since `failures_since`:
    the instant this process built it. `keep` and `interval_hours` are the settings the poller backs up with.

    `pre_upgrade` sits beside `backups`, not inside it: the copy before a migration (#301) is taken whether
    or not backups are enabled. One listing of its directory, nothing opened.
    """
    started = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

    def measure() -> dict | None:
        try:
```

### Block 5 — local-development/gsd/kpi/system.py: the one walk carries the card's fields

Each file stat'd once and counted only when its stat succeeds; `pre_upgrade` beside `backups` (§3.1, §3.2; Orchestrator's notes, 1 and 6).

<!-- block: local-development/gsd/kpi/system.py | edit -->

Old text:

```python
        except OSError:
            wal = 0
        backups = {"count": 0, "bytes": 0}
        if backup_dir:
            for f in Path(backup_dir).glob("gsd-*.db"):
                try:
                    backups["count"] += 1
                    backups["bytes"] += f.stat().st_size
                except OSError:
                    pass
        return {"db_bytes": db, "wal_bytes": wal, "backups": backups}
    return measure
```

New text:

```python
        except OSError:
            wal = 0
        backups: dict = {"enabled": False}
        if backup_dir:
            count, size, newest = 0, 0, None
            for f in Path(backup_dir).glob("gsd-*.db"):
                try:
                    st = f.stat()
                except OSError:
                    continue
                count += 1
                size += st.st_size
                if newest is None or st.st_mtime > newest[0]:
                    newest = (st.st_mtime, f)
            backups = {
                "enabled": True, "dir": backup_dir, "count": count, "bytes": size, "kept": count,
                "newest_at": None if newest is None
                else datetime.fromtimestamp(newest[0], UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "newest_schema": None if newest is None else copy_schema(newest[1]),
                "known_schema": KNOWN_SCHEMA_VERSION,
                "failures": None if failures is None else failures(),
                "failures_since": started,
                "keep": keep, "interval_hours": interval_hours,
            }
        return {"db_bytes": db, "wal_bytes": wal, "backups": backups, "pre_upgrade": newest_pre_upgrade(db_path)}
    return measure
```

### Block 6 — local-development/gsd/api.py: `build_app` passes the settings and the counter

The same `signals` the collector exports `gsd_backup_failures_total` from (§3.2).

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
    # sampler reads nothing until scraped or asked, and reads None on cgroup v1 — omitted, not zero.
    from .kpi.system import CgroupSampler, SystemMonitor, dashboard_data_bytes
    system_monitor = SystemMonitor(CgroupSampler(), os.path.dirname(os.path.abspath(settings.db_path)),
                                   own=("data", dashboard_data_bytes(settings.db_path, settings.backup_dir)))
    poller = Poller(store, settings, elector, signals=signals, system_monitor=system_monitor)
```

New text:

```python
    # sampler reads nothing until scraped or asked, and reads None on cgroup v1 — omitted, not zero.
    # The data block also carries the KPI page's Backups card (#306): the settings the poller backs up
    # with and the failure counter /metrics exports, read from this process, never from Prometheus.
    from .kpi.system import CgroupSampler, SystemMonitor, dashboard_data_bytes
    system_monitor = SystemMonitor(CgroupSampler(), os.path.dirname(os.path.abspath(settings.db_path)),
                                   own=("data", dashboard_data_bytes(
                                       settings.db_path, settings.backup_dir, keep=settings.backup_keep,
                                       interval_hours=settings.backup_interval_hours,
                                       failures=lambda: signals.snapshot()["backup_failures"])))
    poller = Poller(store, settings, elector, signals=signals, system_monitor=system_monitor)
```

### Block 7 — local-development/gsd/static/index.html: the Data volume meter's bytes with backups disabled

With `backups` reduced to `{"enabled": false}` the old sum read `undefined` and printed `NaN` (Orchestrator's notes, 7).

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
  const own = name === "report" ? sys.artifacts : sys.data;
  const ownBytes = own ? (name === "report" ? own.bytes : own.db_bytes + own.wal_bytes + (own.backups ? own.backups.bytes : 0)) : null;
  const diskVal = `<b>${ownBytes == null ? "—" : kpiBytes(ownBytes)}</b>${name === "report" && own ? ` · ${kpiNum(own.files)} files` : ""}`
```

New text:

```html
  const own = name === "report" ? sys.artifacts : sys.data;
  const ownBytes = own ? (name === "report" ? own.bytes : own.db_bytes + own.wal_bytes + ((own.backups && own.backups.bytes) || 0)) : null;
  const diskVal = `<b>${ownBytes == null ? "—" : kpiBytes(ownBytes)}</b>${name === "report" && own ? ` · ${kpiNum(own.files)} files` : ""}`
```

### Block 8 — local-development/gsd/static/index.html: the Backups card

`kpiStampText`, `kpiInstant`, `kpiBackupState` and `kpiBackups`, before `KPI_REFUSAL` (§3.5 to §3.7).

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
}

const KPI_REFUSAL = `This page reports the dashboard's own pods, the fleet's access posture and its trends —
         governance data about the clusters, not about the reader.`;
```

New text:

```html
}

/* The Backups card (#306), built to docs/design/kpi-backups-mock.html. Every figure is the dashboard process's
   own, from /api/kpi's system.dashboard.data: the one walk of the backup directory the size line already lists,
   the failure counter /metrics exports and config.backup. No Prometheus query, so an estate without one sees it;
   where Prometheus runs, GroupSyncDashboardBackupStale and the board's two backup panels say the same. Every
   instant is absolute: the payload's ISO-8601 UTC in a <time datetime>, shown by fmtTime in the page's display
   zone with its label, as every other time on the page is (THE SERVER STATES AN INSTANT; THE PAGE PRESENTS IT).
   Stale is measured against the payload's as-of, the server's clock, as the sparklines are, so a browser with a
   wrong clock cannot make a fresh copy stale. */
const KPI_BACKUP_STALE_INTERVALS = 2;   // the values comment's alert line, backupStaleSeconds: two intervals

/* The text of every instant on the card: fmtTime's "YYYY-MM-DD HH:MM:SS<zone>", in the page's display zone with
   its label. One function, so the "next due by" date test below reads exactly what the tiles print. */
const kpiStampText = (iso) => fmtTime(iso);

/* `part` "date" or "time" splits that text at its first space, for the tiles; a zone label after the time
   ("11:03:38 EDT") is set small, as a tile's unit is: on a narrow tile it wraps under the time, never sideways. */
function kpiInstant(iso, part) {
  const text = kpiStampText(iso), cut = text.indexOf(" ");
  if (cut < 0 || !part) return `<time datetime="${esc(iso)}">${esc(text)}</time>`;
  if (part === "date") return `<time datetime="${esc(iso)}">${esc(text.slice(0, cut))}</time>`;
  const [clock, ...zone] = text.slice(cut + 1).split(" ");
  return `<time datetime="${esc(iso)}">${esc(clock)}${zone.length ? `<span class="of"> ${esc(zone.join(" "))}</span>` : ""}</time>`;
}

/* One state per card, the most severe that holds, always a word on a badge (WCAG 1.4.1, never colour alone):
   disabled, stale, failing, no copy yet, healthy. `due` is when the next copy is due at the latest. */
function kpiBackupState(b, asOf, due) {
  if (b.enabled === false) return { state: "disabled", cls: "unknown", word: "backups are disabled",
    detail: "no backup directory is configured, so this process takes no copies: a setting, not a failure. To take them, set "
      + "<span class=\"mono\">config.backup.enabled: true</span> in this release's values file and roll it out through the release's deployment pipeline." };
  const failures = b.failures || 0;
  const counted = `${kpiNum(failures)} failure${failures === 1 ? "" : "s"} since start`;
  const last = b.newest_at ? kpiInstant(b.newest_at) : null;
  const line = b.interval_hours ? KPI_BACKUP_STALE_INTERVALS * b.interval_hours : null;
  if (last && line != null && Date.parse(asOf) - Date.parse(b.newest_at) > line * 3600000) {
    return { state: "stale", cls: "critical", word: "stale",
      detail: `last copy ${last}, past ${line} h (two intervals of ${b.interval_hours} h)${failures ? `; ${counted}` : ""}` };
  }
  if (failures) return { state: "failing", cls: "warning", word: "failing", detail: `${counted}; ${last ? `last good copy ${last}` : "no good copy yet"}` };
  if (!last) return { state: "none", cls: "unknown", word: "no copy yet",
    detail: `the first copy is taken on the first poll cycle after this process started (${kpiInstant(b.failures_since)})` };
  return { state: "ok", cls: "ok", word: "healthy", detail: `last copy ${last}${due ? `; next due by ${kpiInstant(due)}` : ""}` };
}

function kpiBackups(k) {
  const sys = k.system.dashboard;
  const own = sys && sys.data;
  if (!own || !own.backups) {
    return `<section class="card kpi-page" data-card="backups"><h2>Backups</h2>
      <div class="bk-state" data-state="unknown"><span class="badge unknown"><span class="glyph" aria-hidden="true"></span>unavailable</span>
      <span class="d">the dashboard's database could not be read in this sample, so neither could its backups</span></div></section>`;
  }
  const b = own.backups, pre = own.pre_upgrade;
  const due = b.newest_at && b.interval_hours
    ? new Date(Date.parse(b.newest_at) + b.interval_hours * 3600000).toISOString().replace(/\.\d{3}Z$/, "Z") : null;
  const st = kpiBackupState(b, k.as_of, due);
  const preTile = kpiTile("backup-preupgrade", "Pre-upgrade copy", pre ? `${kpiNum(pre.from)} → ${kpiNum(pre.to)}` : "none",
    pre ? `${kpiInstant(pre.at)} · kept outside the rotation` : "one is taken before each schema migration; none on this volume yet");
  let tiles = preTile;
  if (b.enabled !== false) {
    const sameDay = due && kpiStampText(due).split(" ")[0] === kpiStampText(b.newest_at).split(" ")[0];
    const newer = b.newest_schema != null && b.newest_schema > b.known_schema;
    tiles = kpiTile("backup-last", "Last copy", b.newest_at ? kpiInstant(b.newest_at, "time") : "none yet",
        b.newest_at ? `${kpiInstant(b.newest_at, "date")}${due ? ` · next due by ${kpiInstant(due, sameDay ? "time" : null)}` : ""}`
          : b.failures ? "the attempts since start are failing" : "the first poll cycle takes one", st.state === "stale" ? "critical" : "")
      // keep 0 rotates nothing away (Store._vacuum_into), so there is no ceiling to show against.
      + kpiTile("backup-kept", "Copies kept", `${kpiNum(b.kept)}${b.keep ? `<span class="of">/${kpiNum(b.keep)}</span>` : ""}`,
        `${kpiBytes(b.bytes)} on the data volume${b.count !== b.kept ? ` · ${kpiNum(b.count)} copies in all` : ""}`)
      + kpiTile("backup-failures", "Failures", kpiNum(b.failures), `since start ${kpiInstant(b.failures_since)}`, b.failures ? "warning" : "")
      + kpiTile("backup-schema", "Newest copy's schema", `${kpiNum(b.newest_schema)}<span class="of">/${kpiNum(b.known_schema)}</span>`,
        b.newest_schema == null ? (b.newest_at ? "the newest copy's header could not be read" : "no copy yet")
          : newer ? `newer than this build understands (${kpiNum(b.known_schema)}): this image cannot restore it` : `this build understands ${kpiNum(b.known_schema)}`,
        newer ? "critical" : "")
      + preTile;
  }
  const where = b.enabled === false ? "on-volume · disabled"
    : `on-volume · ${esc(b.dir)} · every ${kpiNum(b.interval_hours)} h · ${b.keep ? `keep ${kpiNum(b.keep)}` : "keep all"}`;
  return `<section class="card kpi-page" data-card="backups">
    <h2>Backups <span class="asof">${where}</span></h2>
    <div class="bk-state" data-state="${st.state}"><span class="badge ${st.cls}"><span class="glyph" aria-hidden="true"></span>${esc(st.word)}</span>
      <span class="d">${st.detail}</span></div>
    <div class="kband bk${b.enabled === false ? " one" : ""}">${tiles}</div>
    <div class="bk-rule"><div class="rule">Read by the dashboard process from what it already has: the backup directory the size line
      above lists, the failure counter <span class="mono">/metrics</span> exports (<span class="mono">gsd_backup_failures_total</span>), counted
      since this process started, and <span class="mono">config.backup</span>. No Prometheus, so it reads the same without one; where one
      runs, <span class="mono">GroupSyncDashboardBackupStale</span> alerts on the same file. Stale is past two backup intervals, the alert's
      line at the chart's defaults. The off-volume copy is not on this card: its signal is the offsite CronJob's.</div></div>
  </section>`;
}

const KPI_REFUSAL = `This page reports the dashboard's own pods, the fleet's access posture and its trends —
         governance data about the clusters, not about the reader.`;
```

### Block 9 — local-development/gsd/static/index.html: the sub-line says "backups disabled"

T306-8; the issue's item 6.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
  const ownLineDashboard = (own, disk) => own
    ? `<div class="sub">gsd.db ${kpiBytes(own.db_bytes)} + WAL ${kpiBytes(own.wal_bytes)}${own.backups ? ` + ${own.backups.count} backups ${kpiBytes(own.backups.bytes)}` : ""}${disk.total_bytes ? `, on a ${kpiBytes(disk.total_bytes)} volume that shares the node's disk (${kpiBytes(disk.used_bytes)} of ${kpiBytes(disk.total_bytes)} used)` : ""}</div>` : "";
  const ownLineReport = (own, disk) => disk.total_bytes
```

New text:

```html
  const ownLineDashboard = (own, disk) => own
    ? `<div class="sub">gsd.db ${kpiBytes(own.db_bytes)} + WAL ${kpiBytes(own.wal_bytes)}${!own.backups ? "" : own.backups.enabled === false ? " · backups disabled" : ` + ${own.backups.count} backups ${kpiBytes(own.backups.bytes)}`}${disk.total_bytes ? `, on a ${kpiBytes(disk.total_bytes)} volume that shares the node's disk (${kpiBytes(disk.used_bytes)} of ${kpiBytes(disk.total_bytes)} used)` : ""}</div>` : "";
  const ownLineReport = (own, disk) => disk.total_bytes
```

### Block 10 — local-development/gsd/static/index.html: the card below System status

The issue's item 4: below System status, above Access posture.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
    </div>
  </section>
  <section class="card kpi-page">
    <h2>Access posture <span class="asof">as of last poll · ${clusters.length} cluster${clusters.length === 1 ? "" : "s"} · ${esc(clusters.join(" + "))}</span></h2>
```

New text:

```html
    </div>
  </section>
  ${kpiBackups(k)}
  <section class="card kpi-page">
    <h2>Access posture <span class="asof">as of last poll · ${clusters.length} cluster${clusters.length === 1 ? "" : "s"} · ${esc(clusters.join(" + "))}</span></h2>
```

### Block 11 — local-development/gsd/static/app.css: the card's styles

Tokens and ladder steps only (`local-development/tests/test_type_scale.py#test_spacing_and_radius_come_from_the_ladders`); the mock's mock-only rules are not carried (§3.6).

<!-- block: local-development/gsd/static/app.css | edit -->

Old text:

```css
.kpi-page .btn .ext { font-family: var(--font-mono); font-size: var(--text-xs); opacity: .8; }

@media (prefers-reduced-motion: reduce) {
```

New text:

```css
.kpi-page .btn .ext { font-family: var(--font-mono); font-size: var(--text-xs); opacity: .8; }

/* #306: the Backups card, to docs/design/kpi-backups-mock.html. One state line (a badge, its word, one mono
   line of detail), five tiles on the band's hairline grid, and the rule. A disabled card keeps one tile, the
   pre-upgrade copy, which is taken whether or not backups are on. */
.kpi-page .bk-state { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-4) var(--space-5);
  padding: var(--space-7) var(--space-9); border-bottom: 1px solid var(--border); }
.kpi-page .bk-state .badge { white-space: normal; max-width: 100%; }
.kpi-page .bk-state .d { font-size: var(--text-sm); color: var(--text-secondary); font-family: var(--font-mono);
  overflow-wrap: anywhere; min-width: 0; }
.kpi-page .kband.bk { grid-template-columns: repeat(5, 1fr); }
.kpi-page .kband.bk .kpi .note { overflow-wrap: anywhere; }
.kpi-page .kband.bk.one { grid-template-columns: minmax(0, 1fr); }
.kpi-page .kband.bk.one .kpi:last-child { grid-column: 1 / -1; }
.kpi-page .bk-rule { padding: 0 var(--space-9) var(--space-8); }

@media (prefers-reduced-motion: reduce) {
```

### Block 12 — local-development/gsd/static/app.css: three tiles a row at 980 px and below

The mock's breakpoints; the fifth tile spans two columns.

<!-- block: local-development/gsd/static/app.css | edit -->

Old text:

```css
  .kpi-page .kband { grid-template-columns: repeat(3, 1fr); }
  .kpi-page .trends { grid-template-columns: repeat(2, 1fr); }
```

New text:

```css
  .kpi-page .kband { grid-template-columns: repeat(3, 1fr); }
  .kpi-page .kband.bk { grid-template-columns: repeat(3, 1fr); }
  .kpi-page .kband.bk .kpi:last-child { grid-column: span 2; }
  .kpi-page .trends { grid-template-columns: repeat(2, 1fr); }
```

### Block 13 — local-development/gsd/static/app.css: two tiles a row at 560 px and below

The fifth tile takes the whole row.

<!-- block: local-development/gsd/static/app.css | edit -->

Old text:

```css
  .kpi-page .kband { grid-template-columns: repeat(2, 1fr); }
  .kpi-page .trends { grid-template-columns: 1fr; }
```

New text:

```css
  .kpi-page .kband { grid-template-columns: repeat(2, 1fr); }
  .kpi-page .kband.bk { grid-template-columns: repeat(2, 1fr); }
  .kpi-page .kband.bk .kpi:last-child { grid-column: 1 / -1; }
  .kpi-page .trends { grid-template-columns: 1fr; }
```

### Block 14 — local-development/tests/test_kpi.py: `os`, for the copies' mtimes

`_copy` below sets a file's mtime with `os.utime`.

<!-- block: local-development/tests/test_kpi.py | edit -->

Old text:

```python

import json
import sqlite3
from datetime import UTC, datetime, timedelta
```

New text:

```python

import json
import os
import sqlite3
from datetime import UTC, datetime, timedelta
```

### Block 15 — local-development/tests/test_kpi.py: the own-bytes test reads the fields it names

The data block grew fields (§3.1), so the exact-dict assertion becomes one on the four figures it is about.

<!-- block: local-development/tests/test_kpi.py | edit -->

Old text:

```python
        mon = SystemMonitor(_sampler(tmp_path), str(tmp_path), own=("data", dashboard_data_bytes(str(db), str(backups))))
        assert mon.view()["data"] == {"db_bytes": 100, "wal_bytes": 40, "backups": {"count": 2, "bytes": 25}}
        assert dashboard_data_bytes(str(tmp_path / "missing.db"), None)() is None
```

New text:

```python
        mon = SystemMonitor(_sampler(tmp_path), str(tmp_path), own=("data", dashboard_data_bytes(str(db), str(backups))))
        data = mon.view()["data"]
        assert (data["db_bytes"], data["wal_bytes"], data["backups"]["count"], data["backups"]["bytes"]) == (100, 40, 2, 25)
        assert dashboard_data_bytes(str(tmp_path / "missing.db"), None)() is None
```

### Block 16 — local-development/tests/test_kpi.py: T306-1 to T306-6 and T306-16

`_copy` writes a file shaped like a `VACUUM INTO` copy; `TestBackupsCard` holds the payload (§4.1).

<!-- block: local-development/tests/test_kpi.py | edit -->

Old text:

```python
        signals.note_report_system(None, "2026-09-19T00:01:00Z")
        assert kpi_client.get("/api/kpi", headers=H("root")).json()["system"]["report"] is None

```

New text:

```python
        signals.note_report_system(None, "2026-09-19T00:01:00Z")
        assert kpi_client.get("/api/kpi", headers=H("root")).json()["system"]["report"] is None


# ── the Backups card (#306) ──────────────────────────────────────────────────────────────

def _copy(path: Path, schema: int, size: int = 4096, mtime: float | None = None) -> Path:
    """A file shaped like a VACUUM INTO copy: SQLite's header string, user_version at offset 60."""
    header = b"SQLite format 3\x00" + bytes(44) + schema.to_bytes(4, "big") + bytes(4)
    path.write_bytes(header + bytes(size - len(header)))
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


class TestBackupsCard:
    """The data block's `backups` and `pre_upgrade` (#306), from what the dashboard process already has."""

    def test_t306_1_disabled_is_enabled_false_and_nothing_else(self, tmp_path):
        from gsd.kpi.system import dashboard_data_bytes
        db = tmp_path / "gsd.db"; db.write_bytes(b"d" * 100)
        data = dashboard_data_bytes(str(db), "")()
        assert data["backups"] == {"enabled": False}, "disabled must not read as 0 backups"

    def test_t306_2_enabled_with_no_copy_yet_is_told_apart_from_disabled(self, tmp_path):
        from gsd.kpi.system import dashboard_data_bytes
        db = tmp_path / "gsd.db"; db.write_bytes(b"d" * 100)
        backups = tmp_path / "backup"; backups.mkdir()
        got = dashboard_data_bytes(str(db), str(backups))()["backups"]
        assert (got["enabled"], got["count"], got["kept"], got["bytes"], got["newest_at"], got["newest_schema"]) == \
            (True, 0, 0, 0, None, None)

    def test_t306_3_count_bytes_and_newest_at_describe_the_same_files_as_the_metric(self, tmp_path):
        """newest_at is the newest gsd-*.db's mtime, the rule of gsd_backup_last_success_timestamp_seconds, in
        ISO-8601 UTC to the second. A name whose stat fails (a copy rotated away between the glob and the stat,
        here a dangling link) is neither counted nor sized: today's walk counted it and sized nothing."""
        from types import SimpleNamespace

        from gsd.kpi.system import dashboard_data_bytes
        db = tmp_path / "gsd.db"; db.write_bytes(b"d" * 100)
        backups = tmp_path / "backup"; backups.mkdir()
        _copy(backups / "gsd-20261001T051103.798578Z.db", 20, 4096, mtime=1790831464.28)
        _copy(backups / "gsd-20261001T111104.000930Z.db", 20, 8192, mtime=1790853064.38)
        measure = dashboard_data_bytes(str(db), str(backups))
        got = measure()["backups"]
        assert (got["count"], got["kept"], got["bytes"], got["newest_at"]) == (2, 2, 4096 + 8192, "2026-10-01T11:11:04Z")
        gone = backups / "gsd-20261001T000000.000000Z.db"
        gone.symlink_to(backups / "rotated-away")
        assert (measure()["backups"]["count"], measure()["backups"]["bytes"]) == (2, 4096 + 8192)
        gone.unlink()
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, timedelta(seconds=120), settings=SimpleNamespace(
                backup_dir=str(backups), login_capture_enabled=False))).decode()
        finally:
            store.close()
        metric = next(float(line.split()[1]) for line in text.splitlines()
                      if line.startswith("gsd_backup_last_success_timestamp_seconds "))
        assert datetime.fromtimestamp(metric, UTC).strftime("%Y-%m-%dT%H:%M:%SZ") == got["newest_at"]

    def test_t306_4_the_newest_schema_is_read_without_touching_the_copy(self, tmp_path):
        """A real VACUUM INTO copy: its schema is read from the header, and the copy keeps its bytes and its
        mtime, with no -wal or -shm beside it."""
        import hashlib

        from gsd.kpi.system import dashboard_data_bytes
        from gsd.store import KNOWN_SCHEMA_VERSION
        db = tmp_path / "gsd.db"
        backups = tmp_path / "backup"
        store = Store(str(db))
        try:
            copy = Path(store.backup(str(backups), keep=4))
        finally:
            store.close()
        before = (hashlib.sha256(copy.read_bytes()).hexdigest(), copy.stat().st_mtime_ns)
        got = dashboard_data_bytes(str(db), str(backups))()["backups"]
        assert (got["newest_schema"], got["known_schema"]) == (KNOWN_SCHEMA_VERSION, KNOWN_SCHEMA_VERSION)
        assert (hashlib.sha256(copy.read_bytes()).hexdigest(), copy.stat().st_mtime_ns) == before
        assert sorted(p.name for p in backups.iterdir()) == [copy.name], "a -wal or -shm appeared beside the copy"

    def test_t306_5_failures_keep_and_interval_come_from_the_process(self, tmp_path):
        """The counter /metrics exports (RuntimeSignals.note_backup_failure) and the settings the poller backs
        up with, through /api/kpi as the page reads them."""
        db = str(tmp_path / "gsd.db")
        _seed(db)
        app = build_app(_settings(db, backup_dir=str(tmp_path / "backup"), backup_keep=4, backup_interval_hours=6),
                        run_poller=False)
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
        app.state.signals.note_backup_failure()
        app.state.signals.note_backup_failure()
        with TestClient(app) as client:
            body = client.get("/api/kpi", headers=H("root")).json()
        got = body["system"]["dashboard"]["data"]["backups"]
        assert (got["failures"], got["keep"], got["interval_hours"], got["dir"]) == (2, 4, 6, str(tmp_path / "backup"))
        assert got["failures_since"] <= body["as_of"] and got["failures_since"].endswith("Z")

    def test_t306_6_the_newest_pre_upgrade_copy_by_name_or_null(self, tmp_path):
        """Beside the database, outside backup.dir; read from the name, whether or not backups are enabled."""
        from gsd.kpi.system import dashboard_data_bytes
        db = tmp_path / "gsd.db"; db.write_bytes(b"d" * 100)
        pre = tmp_path / "pre-upgrade"; pre.mkdir()
        measure = dashboard_data_bytes(str(db), "")
        assert measure()["pre_upgrade"] is None
        for name in ("pre-upgrade-20260920T010101.000000Z-schema-18-to-19-group-sync-dashboard-58bf7b9cb7-pgwcw.db",
                     "pre-upgrade-20260925T064601.000000Z-schema-19-to-20-group-sync-dashboard-d568cf97b-88dxh.db"):
            _copy(pre / name, int(name.split("-schema-")[1].split("-")[0]))
            (pre / (name + ".sha256")).write_text(f"{'0' * 64}  {name}\n")
        assert measure()["pre_upgrade"] == {"at": "2026-09-25T06:46:01Z", "from": 19, "to": 20}
        for f in pre.iterdir():
            f.unlink()
        assert measure()["pre_upgrade"] is None

    def test_t306_16_one_view_lists_two_directories_opens_one_copy_and_writes_nothing(self, tmp_path):
        """The read budget, measured with the interpreter's audit hooks in a child process (a hook cannot be
        removed, so none is left in this one): one listing of backup.dir, one of pre-upgrade/, one read-only open
        of the newest copy, and no other access under the data directory: no write, no rename, no SQLite open."""
        import subprocess
        import sys
        db = tmp_path / "gsd.db"; db.write_bytes(b"d" * 100)
        backups = tmp_path / "backup"; backups.mkdir()
        _copy(backups / "gsd-20261001T051103.798578Z.db", 20, mtime=1790831464)
        newest = _copy(backups / "gsd-20261001T111104.000930Z.db", 20, mtime=1790853064)
        pre = tmp_path / "pre-upgrade"; pre.mkdir()
        _copy(pre / "pre-upgrade-20260925T064601.000000Z-schema-19-to-20-pod.db", 19)
        probe = (
            "import json, os, sys\n"
            "from gsd.kpi.system import CgroupSampler, SystemMonitor, dashboard_data_bytes\n"
            "root, db, backups = (os.path.realpath(a) for a in sys.argv[1:4])\n"
            "seen = []\n"
            "def hook(event, args):\n"
            "    if args and isinstance(args[0], (str, os.PathLike)):\n"
            "        path = os.path.realpath(os.fspath(args[0]))\n"
            "        if path.startswith(root):\n"
            "            seen.append([event, path] + [a for a in args[1:3] if isinstance(a, (str, int))])\n"
            "monitor = SystemMonitor(CgroupSampler(os.path.join(root, 'no-cgroup')), None,\n"
            "                        own=('data', dashboard_data_bytes(db, backups)))\n"
            "sys.addaudithook(hook)\n"
            "view = monitor.view()\n"
            "print(json.dumps({'seen': seen, 'schema': view['data']['backups'].get('newest_schema')}))\n")
        done = subprocess.run([sys.executable, "-c", probe, str(tmp_path), str(db), str(backups)],
                              capture_output=True, text=True, timeout=60,
                              env={**os.environ, "PYTHONPATH": str(Path(__file__).resolve().parents[1])})
        assert done.returncode == 0, done.stderr
        out = json.loads(done.stdout)
        root = os.path.realpath(tmp_path)
        listings = sorted(path for event, path, *_ in out["seen"] if event in ("os.scandir", "os.listdir"))
        assert listings == sorted([os.path.join(root, "backup"), os.path.join(root, "pre-upgrade")]), out["seen"]
        opens = [entry for entry in out["seen"] if entry[0] == "open"]
        assert [path for _, path, *_ in opens] == [os.path.realpath(newest)], opens
        mode, flags = opens[0][2], opens[0][3]
        assert "r" in mode and not set("wax+") & set(mode)
        assert not flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND)
        # pathlib.Path.glob is the pattern's own event (Python 3.13 on); the listing itself is the os.scandir above.
        assert {event for event, *_ in out["seen"]} <= {"os.scandir", "os.listdir", "pathlib.Path.glob", "open"}, out["seen"]
        assert out["schema"] == 20

```

### Block 17 — local-development/tests/test_metrics.py: T306-14, `/metrics` unchanged

A regression guard: the exposition before and after the card's walk (§4.1).

<!-- block: local-development/tests/test_metrics.py | edit -->

Old text:

```python
            store.close()


class TestGroupCountCliffMetric:
```

New text:

```python
            store.close()

    def test_t306_14_the_backups_card_leaves_the_exposition_as_it_was(self, tmp_path):
        """T306-14, a regression guard (#306): the KPI page's Backups card reads what /metrics reads and adds
        nothing to it. The same store, signals and backup directory render the same families and label sets,
        and the same backup values, before and after the card's walk; and no family is the card's."""
        from types import SimpleNamespace

        from gsd.kpi.system import dashboard_data_bytes
        from gsd.metrics import RuntimeSignals
        db = tmp_path / "gsd.db"
        backups = tmp_path / "backup"
        store = Store(str(db))
        try:
            store.backup(str(backups), keep=4)
            signals = RuntimeSignals()
            signals.note_backup_failure()
            settings = SimpleNamespace(backup_dir=str(backups), login_capture_enabled=False)

            def exposition() -> list[str]:
                text = generate_latest(build_registry(store, GRACE, signals=signals, settings=settings)).decode()
                return sorted(line if line.startswith(("#", "gsd_backup_")) else line.rsplit(" ", 1)[0]
                              for line in text.splitlines())

            before = exposition()
            card = dashboard_data_bytes(str(db), str(backups))()
            assert exposition() == before
        finally:
            store.close()
        assert card["backups"]["count"] == 1
        assert "gsd_backup_failures_total 1.0" in before
        assert not [line for line in before if line.startswith("# HELP") and "card" in line.lower()]


class TestGroupCountCliffMetric:
```

### Block 18 — local-development/tests/test_ui.py: the five sections are six

The headings now include Backups, and the access-posture band is counted apart from the card's band.

<!-- block: local-development/tests/test_ui.py | edit -->

Old text:

```python
        headings = [h.split("\n")[0].strip() for h in dash.locator("section.kpi-page > h2").all_inner_texts()]
        assert headings[:4] == ["System status", "Access posture", "Trends", "Clusters"]
        assert dash.locator(".kpi-page .kband .kpi").count() == 6
        assert dash.locator(".kpi-page .trend").count() == 4
```

New text:

```python
        headings = [h.split("\n")[0].strip() for h in dash.locator("section.kpi-page > h2").all_inner_texts()]
        assert headings[:5] == ["System status", "Backups", "Access posture", "Trends", "Clusters"]
        assert dash.locator(".kpi-page .kband:not(.bk) .kpi").count() == 6
        assert dash.locator(".kpi-page .trend").count() == 4
```

### Block 19 — local-development/tests/test_ui.py: T306-8 to T306-13

The browser tests: each state, the five tiles, the instants, the repaint, the display zone, and the widths and themes (§4.1).

<!-- block: local-development/tests/test_ui.py | edit -->

Old text:

```python
        dash.emulate_media(reduced_motion="no-preference")
        assert dash.evaluate("() => getComputedStyle(document.querySelector('.kpi-page .beat')).animationName") == "kpi-beat"

```

New text:

```python
        dash.emulate_media(reduced_motion="no-preference")
        assert dash.evaluate("() => getComputedStyle(document.querySelector('.kpi-page .beat')).animationName") == "kpi-beat"

    # ── the Backups card (#306) ──
    # Each state as a server sends it, every instant placed against the payload's own as-of, the clock the card
    # measures stale against. The harness configures no backup directory, so the served payload is "disabled".
    BACKUP_STATES = ("disabled", "none", "stale", "failing", "healthy")
    SET_BACKUPS = """([state, withPre]) => {
        const at = Date.parse(data.kpi.as_of);
        const iso = (s) => new Date(at + s * 1000).toISOString().replace(/\\.\\d{3}Z$/, "Z");
        const on = {enabled: true, dir: "/data/backup", count: 4, kept: 4, bytes: 2621440, newest_at: iso(-3600), newest_schema: 20,
                    known_schema: 20, failures: 0, failures_since: iso(-86400), keep: 4, interval_hours: 6};
        data.kpi.system.dashboard.data.backups = {
          disabled: {enabled: false},
          none: {...on, count: 0, kept: 0, bytes: 0, newest_at: null, newest_schema: null},
          stale: {...on, newest_at: iso(-13 * 3600)},
          failing: {...on, failures: 3},
          healthy: on,
        }[state];
        data.kpi.system.dashboard.data.pre_upgrade = withPre ? {at: "2026-09-25T06:46:01Z", from: 19, to: 20} : null;
        render();
        return iso(-3600); }"""

    def _backups(self, dash, state, pre=False):
        return dash.evaluate(self.SET_BACKUPS, [state, pre])

    def _card(self, dash):
        return dash.locator('section.kpi-page[data-card="backups"]')

    def test_t306_8_disabled_reads_disabled_never_zero(self, dash):
        """The harness's own payload: no backup directory. The card and the sub-line say disabled; nothing in the
        card or the dashboard component reads "0 backups" or "never", and the data volume's bytes stay a number."""
        self._open(dash)
        card = self._card(dash)
        assert card.locator(".bk-state").get_attribute("data-state") == "disabled"
        assert card.locator(".bk-state .badge").inner_text().strip() == "backups are disabled"
        comp = dash.locator('.kpi-page .comp[data-comp="dashboard"]')
        assert "backups disabled" in comp.locator(".sub").nth(1).inner_text()
        for text in (card.inner_text(), comp.inner_text()):
            assert "0 backups" not in text and "never" not in text.lower(), text
        assert "NaN" not in comp.locator(".meter-val").last.inner_text()
        assert card.locator(".kpi").count() == 1, "disabled keeps only the pre-upgrade tile"

    def test_t306_9_enabled_with_no_copy_reads_no_copy_yet(self, dash):
        self._open(dash)
        self._backups(dash, "none")
        state = self._card(dash).locator(".bk-state")
        assert state.get_attribute("data-state") == "none"
        assert state.locator(".badge").inner_text().strip() == "no copy yet"
        # keep 0 keeps every copy (Store._vacuum_into rotates nothing): no "/0" ceiling, "keep all" in the heading
        dash.evaluate("() => { data.kpi.system.dashboard.data.backups.keep = 0; render(); }")
        assert self._card(dash).locator('[data-kpi="backup-kept"] .value').inner_text().strip() == "0"
        assert "keep all" in self._card(dash).locator("h2").inner_text()

    def test_t306_10_older_than_two_intervals_reads_stale_with_the_instant(self, dash):
        self._open(dash)
        self._backups(dash, "stale")
        state = self._card(dash).locator(".bk-state")
        assert state.get_attribute("data-state") == "stale"
        assert state.locator(".badge").inner_text().strip() == "stale"
        newest = dash.evaluate("() => data.kpi.system.dashboard.data.backups.newest_at")
        shown = dash.evaluate("(i) => fmtTime(i)", newest)
        assert f"last copy {shown}, past 12 h" in state.inner_text()
        assert state.locator("time").first.get_attribute("datetime") == newest
        # Measured against the payload's as-of, the server's clock, never the browser's: a payload three days
        # behind this browser, with a copy an hour older than its as-of, is healthy.
        skewed = dash.evaluate("""() => { const at = Date.now() - 3 * 86400000;
            const iso = (ms) => new Date(ms).toISOString().replace(/\\.\\d{3}Z$/, "Z");
            data.kpi.as_of = iso(at);
            Object.assign(data.kpi.system.dashboard.data.backups, {newest_at: iso(at - 3600000), failures: 0});
            render(); return document.querySelector('[data-card="backups"] .bk-state').dataset.state; }""")
        assert skewed == "ok", skewed

    def test_t306_11_failures_are_paired_with_the_last_good_instant(self, dash):
        self._open(dash)
        last = self._backups(dash, "failing")
        state = self._card(dash).locator(".bk-state")
        assert state.get_attribute("data-state") == "failing"
        shown = dash.evaluate("(i) => fmtTime(i)", last)
        assert f"3 failures since start; last good copy {shown}" in state.inner_text()
        assert state.locator("time").first.get_attribute("datetime") == last
        # Failing with no copy at all (a new install whose backupDir is unwritable): the Last copy tile agrees
        # with the state line rather than promising the first poll cycle (review of this spec, OB3, N1).
        dash.evaluate("""() => { Object.assign(data.kpi.system.dashboard.data.backups,
            {newest_at: null, newest_schema: null, count: 0, kept: 0, bytes: 0}); render(); }""")
        assert "3 failures since start; no good copy yet" in state.inner_text()
        tile = self._card(dash).locator('[data-kpi="backup-last"] .note').inner_text()
        assert tile == "the attempts since start are failing", tile

    def test_t306_12_five_tiles_absolute_instants_and_the_repaint_keeps_the_card(self, dash):
        """The healthy card with a pre-upgrade copy, served by the route so the 60-second refresh repaints from
        the same payload: five tiles, every instant an ISO-8601 UTC <time>, no age, and the card still there."""
        served: list[str] = []

        def healthy(route):
            body = route.fetch().json()
            at = datetime.fromisoformat(body["as_of"].replace("Z", "+00:00"))
            stamp = lambda s: (at + timedelta(seconds=s)).strftime("%Y-%m-%dT%H:%M:%SZ")  # noqa: E731
            body["system"]["dashboard"]["data"]["backups"] = {
                "enabled": True, "dir": "/data/backup", "count": 4, "kept": 4, "bytes": 2621440, "newest_at": stamp(-3600),
                "newest_schema": 20, "known_schema": 20, "failures": 0, "failures_since": stamp(-86400),
                "keep": 4, "interval_hours": 6}
            body["system"]["dashboard"]["data"]["pre_upgrade"] = {"at": "2026-09-25T06:46:01Z", "from": 19, "to": 20}
            route.fulfill(json=body)
            served.append(body["as_of"])
        dash.route("**/api/kpi", healthy)
        self._open(dash)
        dash.wait_for_selector('.bk-state[data-state="ok"]', timeout=10_000)
        card = self._card(dash)

        def check():
            tiles = card.locator(".kband.bk .kpi").evaluate_all("els => els.map(e => e.dataset.kpi)")
            assert tiles == ["backup-last", "backup-kept", "backup-failures", "backup-schema", "backup-preupgrade"]
            stamps = card.locator("time").evaluate_all("els => els.map(e => [e.getAttribute('datetime'), e.textContent])")
            assert stamps and all(re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", iso) for iso, _ in stamps), stamps
            for iso, text in stamps:   # each shown as fmtTime shows it: whole, its date, or what follows the date
                full = dash.evaluate("(i) => fmtTime(i)", iso)
                assert text in (full, full.split(" ", 1)[0], full.split(" ", 1)[-1]), (iso, text, full)
            assert " ago" not in card.inner_text()
            assert "19 → 20" in card.locator('[data-kpi="backup-preupgrade"]').inner_text()
            assert card.locator('[data-kpi="backup-kept"] .value').inner_text().replace("\n", "") == "4/4"

        check()
        polls = len(served)
        dash.evaluate("() => refresh()")          # the page's poll, as the 60-second timer runs it
        assert len(served) > polls, "the repaint did not fetch /api/kpi"
        check()
        # The page's display zone, as /api/version names it: the same instants, labelled in that zone.
        utc = card.locator('[data-kpi="backup-last"] time').first.get_attribute("datetime")
        dash.evaluate("() => { setDisplayZone({name: 'America/New_York', abbrev: 'EDT'}); render(); }")
        shown = card.locator('[data-kpi="backup-last"] .value').inner_text()
        assert shown.endswith(("EDT", "EST")) and card.locator('[data-kpi="backup-last"] time').first.get_attribute("datetime") == utc
        check()
        dash.evaluate("() => { setDisplayZone(null); render(); }")

    def test_t306_13_every_state_fits_375_768_and_1280_in_light_and_dark(self, dash):
        errors: list[str] = []
        dash.on("pageerror", lambda e: errors.append(str(e)))
        self._open(dash)
        for theme in ("light", "dark"):
            dash.evaluate("(t) => document.documentElement.setAttribute('data-theme', t)", theme)
            for width in (375, 768, 1280):
                dash.set_viewport_size({"width": width, "height": 900})
                for state in self.BACKUP_STATES:
                    self._backups(dash, state, pre=True)
                    drawn = self._card(dash).locator(".bk-state").get_attribute("data-state")
                    assert drawn == {"healthy": "ok"}.get(state, state), (state, drawn)   # the state measured is the one set
                    sizes = dash.evaluate("() => [document.documentElement.scrollWidth, document.documentElement.clientWidth]")
                    assert sizes[0] == sizes[1], f"{state} at {width} px, {theme}: scrolls sideways {sizes}"
                    card = dash.evaluate("""() => { const c = document.querySelector('[data-card="backups"]');
                        return [c.scrollWidth, c.clientWidth]; }""")
                    assert card[0] <= card[1], f"{state} at {width} px, {theme}: the card overflows {card}"
        assert not errors, errors

```

### Block 20 — local-development/API.md: the `/api/kpi` example carries the new fields

The issue's Definition of Done: every field, and the disabled shape (below).

<!-- block: local-development/API.md | edit -->

Old text:

```text
                  "disk": {"used_bytes": 27000000000, "total_bytes": 32000000000},
                  "data": {"db_bytes": 2400000, "wal_bytes": 4200000, "backups": {"count": 4, "bytes": 8500000}}},
    "report": null
```

New text:

```text
                  "disk": {"used_bytes": 27000000000, "total_bytes": 32000000000},
                  "data": {"db_bytes": 2400000, "wal_bytes": 4200000,
                           "backups": {"enabled": true, "dir": "/data/backup", "count": 4, "bytes": 8500000,
                                       "kept": 4, "newest_at": "2026-09-19T12:11:04Z", "newest_schema": 20, "known_schema": 20,
                                       "failures": 0, "failures_since": "2026-09-18T23:09:50Z",
                                       "keep": 4, "interval_hours": 6.0},
                           "pre_upgrade": {"at": "2026-09-18T23:09:45Z", "from": 19, "to": 20}}},
    "report": null
```

### Block 21 — local-development/API.md: `data.backups` and `data.pre_upgrade`, field by field

The disabled shape, each field, and where the state comes from.

<!-- block: local-development/API.md | edit -->

Old text:

```text
`openshift-config-managed/console-public`; `observe` is the console's namespace-workloads dashboard
scoped to the pod's own namespace (`…/dev-monitoring/ns/<ns>?dashboard=dashboard-k8s-resources-workloads-namespace` — the namespace in the path, because the console's project selector, which the graphs' tenancy requests carry, is set only from a `/ns/<name>` path segment).

```

New text:

```text
`openshift-config-managed/console-public`; `observe` is the console's namespace-workloads dashboard
scoped to the pod's own namespace (`…/dev-monitoring/ns/<ns>?dashboard=dashboard-k8s-resources-workloads-namespace` — the namespace in the path, because the console's project selector, which the graphs' tenancy requests carry, is set only from a `/ns/<name>` path segment).

`data.backups` and `data.pre_upgrade` are the KPI page's Backups card (#306), read by the dashboard process
from what it already has: no Prometheus query, so an estate without one gets the same answer. With no backup
directory configured (`config.backup.enabled: false`), `backups` is `{"enabled": false}` and nothing else:
disabled, which is not "0 backups". Enabled, it carries:

| field | what it is |
|---|---|
| `enabled` | `true` |
| `dir` | `config.backup.dir`, the directory the poller writes `gsd-*.db` into |
| `count`, `bytes` | the `gsd-*.db` files in it and their total size, from one walk; a file whose stat fails (rotated away during the walk) is in neither. Every copy on the volume: the dashboard's size line |
| `kept` | the copies this process's rotation keeps to `keep`; today every `gsd-*.db`, so equal to `count` |
| `newest_at` | the newest of the `kept` copies' mtime, ISO-8601 UTC to the second: the rule of `gsd_backup_last_success_timestamp_seconds`; `null` when there is none yet |
| `newest_schema` | that file's schema, read from its SQLite header (offset 60) without opening it in SQLite; `null` when there is no copy or its header is not SQLite's |
| `known_schema` | the schema this build understands (`KNOWN_SCHEMA_VERSION`): a copy above it cannot be restored under this image |
| `failures`, `failures_since` | `gsd_backup_failures_total`, the backups that failed since this process started, and the instant it started counting |
| `keep`, `interval_hours` | `config.backup.keep` and `config.backup.intervalHours`, as the poller uses them; `keep` 0 rotates nothing away |

`pre_upgrade` is the newest copy taken before a schema migration (#301), read from its name in
`pre-upgrade/` beside the database: `{"at", "from", "to"}`, or `null` when there is none. It is reported
whether or not backups are enabled, because that copy is taken either way. The page derives the card's state
from these fields, against the payload's `as_of`: stale is a newest copy older than two `interval_hours`, the
`GroupSyncDashboardBackupStale` line at the chart's defaults.

```

### Block 22 — docs/RUNBOOK_backup_restore.md: the runbook names the card

One paragraph in "What a successful backup looks like".

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
pod's own output. The commands are below each picture, and lines not relevant to the picture are left out. `grep` and
`tail` run on your workstation; the pod has neither.

```

New text:

```text
pod's own output. The commands are below each picture, and lines not relevant to the picture are left out. `grep` and
`tail` run on your workstation; the pod has neither.

Without a terminal, the KPI page's **Backups** card (the cluster-admin tier, #306) shows what the first picture
shows, read by the dashboard process itself and with no Prometheus: the newest copy's instant (the last-success
metric's file), the copies kept against `keep` and their size, the failures since the process started, the newest
copy's schema against the one the running image understands, and the newest pre-upgrade copy (§6). One state, in
words: healthy, no copy yet, failing, stale (older than two backup intervals), or disabled.

```

### Block 23 — docs/design/README.md: the mock's row says Implemented

`docs/design/README.md`'s status convention.

<!-- block: docs/design/README.md | edit -->

Old text:

```text
| [`kpi-backups-mock.html`](kpi-backups-mock.html) | **Proposed** (Epic E: #306; drawn 2026-09-26) — a Backups panel on the KPI page: last copy, copies kept, failures, the newest copy's schema and the pre-upgrade copy (#301), with how the disabled, none-yet, stale and failing states read. The rendered picture is `kpi-backups-mock.png` |
```

New text:

```text
| [`kpi-backups-mock.html`](kpi-backups-mock.html) | **Implemented** (#306, `docs/specs/SPEC_E6_kpi_backups_card.md`; the page shows the one state in force where the mock lists all four) (Epic E: #306; drawn 2026-09-26) — a Backups panel on the KPI page: last copy, copies kept, failures, the newest copy's schema and the pre-upgrade copy (#301), with how the disabled, none-yet, stale and failing states read. The rendered picture is `kpi-backups-mock.png` |
```

### Block 24 — docs/CHANGELOG.md: the CHANGELOG entry

First under `## Unreleased`.

<!-- block: docs/CHANGELOG.md | edit -->

Old text:

```text
## Unreleased

```

New text:

```text
## Unreleased

- **A Backups card on the KPI page (#306, Epic E #385, `docs/specs/SPEC_E6_kpi_backups_card.md`).** Below System
  status, from what the dashboard process already has: the last copy as an absolute instant in the page's display
  zone, with its label (ISO-8601 UTC in the payload), and when the next is due, the copies kept against
  `config.backup.keep` and their size, the failures since the process started, the
  newest copy's schema against what this build understands, and the newest pre-upgrade copy (#301). One state in
  words: healthy, no copy yet, failing, stale (older than two backup intervals), or disabled, which no longer reads
  "+ 0 backups" in the dashboard's size line ("backups disabled"). `/api/kpi`'s `system.dashboard.data.backups` is
  `{"enabled": false}` when backups are off and carries the card's fields when on, with `pre_upgrade` beside it
  (`local-development/API.md`); the same walk now counts and sizes the same files. No Prometheus query, no new
  metric, no new permission; `/metrics` and the Grafana board are unchanged.

```
