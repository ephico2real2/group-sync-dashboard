# SPEC B2 — Retention for membership_event and sync_event

| | |
|---|---|
| Programme | Feature programme 2026-09 — index and version ladder in `docs/specs/README.md` |
| Batch | B — data |
| Release | R2 — Alerts, retention, Grafana |
| Version on release | app 0.13.0, chart 0.12.0 |
| Issue | [#59](https://github.com/ephico2real2/group-sync-dashboard/issues/59) |
| Status | in progress |
| Source | design agent output `a7eabba23e10eec8a`; one message; no seam |

## How to read this spec

Everything under "Batch preamble", "Design" and "Batch closing sections" is the design agent's text,
sliced from the agent's output by heading and re-concatenated to the byte before this file was
written. It is verbatim with exactly two kinds of exception, both stated in this file: the seam
repair named in the Source row where the agent's output was cut across messages, and the citation or
name corrections listed under "Orchestrator's notes", each of which changes a reference and never a
claim. Nothing else was rewritten by hand. Implementation applies the code in "Design" exactly as
written, one file at a time, with the orchestrator's notes governing where they and the body differ;
a deviation found necessary during implementation is written back into this file in the same pull
request, with the reason, under "Orchestrator's notes".

## Orchestrator's notes

- Lands after B4, which already defines the index `membership_event_by_time` on `membership_event(cluster_id, observed_at)`; this spec adds only `sync_event_by_time`.
- Version pair superseded: app 0.13.0, chart 0.12.0 (B4 took 0.12.0 / 0.11.0). The operator confirmed `syncEventsDays: 730` on by default and `membershipEventsDays: 0`.
- The `README.md` "Not built yet" sentence is edited as it stands after B4 merged (B4 already removed the cliff-alert clause).
- The preamble's B1 bookkeeping (backup.offsite history text) is NOT applied here; B1 lands in R4.
- Interaction found in review (PR #69, C7) and modelled as DERIVE: the body lets retention run when `backup_dir` is empty ("purely the operator's policy"). With `syncEventsDays: 730` on by default that is an irreversible delete with no copy anywhere, so the prune is HELD whenever backups are disabled, exactly as it is held until the first successful backup — the `_prune_history` gate becomes `if not self.settings.backup_dir or self._backup_state != "ok"` with the same once-only warning, the test `test_with_backups_disabled_retention_is_the_operators_policy` becomes `test_with_backups_disabled_retention_is_held`, and the values comment and chart README say "retention runs only after a successful backup; with backups off nothing is ever deleted". The operator's 730 default stands.
- Ladder inversion found in review (PR #69, C8): the body's "Not built yet" NEW text keeps the cliff-alert clause, which B4 already removed. After B2 the sentence reads "Effective-permission expansion, log-scrape enrichment, per-namespace PDF reports"; the old text is the sentence as it stands after B4.
- The body inserts `membership_event_by_time` into SCHEMA; that insertion is SKIPPED here because B4 already made it. Only `sync_event_by_time` is added.

- Citation corrected when B4 landed (1 occurrence): the design's ground-truth table cited the chart README heading "The eleven alerts"; B4 made it twelve, and the heading is cited by its current text. The count this spec's own edits produce is re-derived from main at implementation, as the notes above already say.

- Deviations recorded at implementation (PR for #59): (1) every "Since 0.12.0" in the body's API.md text and the metrics design's "application 0.12.0" read 0.13.0, the release this spec ships in; (2) `docs/DESIGN_backup_offsite_and_retention.md`, a record never written, is cited as this spec instead; (3) the chart README's insertion anchor is the half-an-answer paragraph's actual last line ("grow credentials for object storage.") — the off-volume section it names does not exist until B1; (4) the body's test harness recomputed "now" after the app started and asserted the newest of three seeded rows where `MIN` returns the oldest: one frozen clock per module, and the oldest row (two seconds older) as the expectation.

## Batch preamble (verbatim from the design)

# DESIGN — B1 off-volume backup CronJob + restore runbook, B2 retention for `membership_event` / `sync_event`

Everything below is grounded in files read during this pass; each claim is cited as `path#anchor`. No file was modified. The document is written to be dropped into `docs/` as the specification the implementation follows; every backticked path it names exists today or is created by this change, so `tests/test_docs_citations.py` will hold.

---

## 0. Ground truth this design stands on

| Fact | Where |
|---|---|
| The on-volume backup is `VACUUM INTO` from the poll thread, files named `gsd-<UTC stamp with microseconds>Z.db`, rotated by `keep` with `sorted(glob("gsd-*.db"))[:-keep]`, returns `None` on failure | `gsd/store.py#Store.backup` |
| `_maybe_backup` runs on a monotonic timer (`_next_backup`, first cycle immediately), counts failures via `signals.note_backup_failure()`, never raises | `gsd/poller.py#Poller._maybe_backup` |
| The per-cluster loop is: leader gate → `poll_once` → `capture_once` → `store.maintain()` → `_maybe_backup()` | `gsd/poller.py#Poller._run_cluster` |
| Settings carry `backup_dir`, `backup_interval_hours`, `backup_keep`, `login_retention_days: int = 400`, `user_activity_retention_days: int = 400`; numeric keys go through `_num_setting` (env wins, malformed falls back) | `gsd/config.py#Settings`, `gsd/config.py#_num_setting` |
| The metric families `gsd_retention_rows_deleted_total{table}` (pre-seeded from `RETENTION_TABLES`), `gsd_backup_failures_total`, `gsd_backup_last_success_timestamp_seconds` (mtime of newest file) | `gsd/metrics.py#RETENTION_TABLES`, `gsd/metrics.py#DashboardCollector` |
| The HELP text currently says "membership_event and sync_event deliberately have none" | `gsd/metrics.py#DashboardCollector` (the `retention` family) |
| The bounded-prune precedent: id-IN-subselect, `DELETE … LIMIT` is not compiled into this build, non-positive limit deletes nothing | `gsd/store.py#Store.prune_login_events` |
| The leader-rechecked prune precedent with a signals seam | `gsd/logincapture.py#_prune` |
| `membership_event` and `sync_event` both carry `observed_at` stamped by `now_iso()` (second resolution, `Z`) | `gsd/store.py#SCHEMA`, `gsd/poller.py#poll_once` (`observed_at = now_iso()`), `gsd/timeutil.py#now_iso` |
| Indexes today: `sync_event_lookup(cluster_id, groupsync_name, synced_at DESC)`, `membership_event_lookup(cluster_id, group_name, id DESC)`, `membership_event_by_user(cluster_id, user_name, id DESC)` — nothing on `observed_at` | `gsd/store.py#SCHEMA` |
| `CREATE INDEX IF NOT EXISTS` in `SCHEMA` is applied at every startup via `executescript`, so an index (unlike a column) needs no `_MIGRATIONS` entry | `gsd/store.py#Store.__init__`, `gsd/store.py#_MIGRATIONS` |
| Every method the app calls on `store` must be in the Protocol with identical parameters | `tests/test_storage_seam.py` (`test_the_protocol_declares_every_method_the_application_calls`, `test_the_declared_signatures_match_the_implementation`) |
| A handler with more than one `store.` call must be `@consistent`; the API is GET-only | `tests/test_api_contract.py` (`test_r5_multi_store_handlers_take_a_snapshot`, `test_r6_the_api_is_read_only`) |
| History reaches the wire in four places: `/groupsyncs/{name}/events` (`note`, `events`), `/membership-changes` (`note`, `changes`), `/groups/{name}` (`changes`, both the deleted and live branches), `/users/{name}` (`changes`) | `gsd/api.py#build_app` (`list_events`, `membership_changes`, `group_detail`, `user_detail`) |
| The UI renders those in `timelineChart(events)` + the "Observed syncs" table (`${esc(ev.note || "")}`), the group page `<h2>Membership changes</h2>`, and the user page `<h2>History</h2>`; the Overview never calls `/membership-changes` | `gsd/static/index.html#timelineChart`, `gsd/static/index.html#Membership changes`, `gsd/static/index.html#<h2>History</h2>` |
| Chart: the data claim is `persistence.existingClaim | default "<fullname>-data"`, mounted at `/data`; access mode comes from `gsd.accessMode` (explicit value, else RWX above one replica, else RWOP); `config.backup.dir` defaults to `/data/backup`; `securityContext` has `readOnlyRootFilesystem: true`; `podSecurityContext` has no fsGroup | `charts/group-sync-dashboard/templates/deployment.yaml#claimName`, `charts/group-sync-dashboard/templates/_helpers.tpl#gsd.accessMode`, `charts/group-sync-dashboard/values.yaml#HALF AN ANSWER BY DESIGN` |
| The Service selects pods by `gsd.selectorLabels` (`app.kubernetes.io/name`, `instance`, **and** `app: <fullname>`) | `charts/group-sync-dashboard/templates/_helpers.tpl#gsd.selectorLabels` |
| The chart's Job precedent uses an operator-supplied image for a CLI the dashboard image lacks | `charts/group-sync-dashboard/templates/auth-loglevel-job.yaml#authLogLevel.image` |
| The pod has sh, curl, jq, ls, cat, base64, mkdir, chgrp, chmod, rm, rmdir, python3.14 — no tar/gzip/rsync/aws/head/wc/grep; the interpreter is `python3.14`; `PYTHONDONTWRITEBYTECODE=1` | `docs/DESIGN_hardened_image.md#What it changed for operators`, `local-development/Containerfile#PYTHONDONTWRITEBYTECODE` |
| Alert-rule tests extract only `gsd_*` names from `expr`, so a `kube_*` metric in a rule does not need a collector HELP line | `tests/test_metrics.py` (`test_every_metric_an_alert_references_is_declared_by_the_collector`) |
| README and chart README both say "eleven" alerts | `README.md#eleven alerting`, `charts/group-sync-dashboard/README.md#The twelve alerts` |
| The `helm template` test helper is `render(**values)` with `__` → `.` | `tests/test_chart_strategy.py#render` |

---

## 1. Versions and shared bookkeeping (both features, one change)

* `local-development/pyproject.toml`: `version = "0.11.0"` → `version = "0.12.0"`.
* `local-development/gsd/__init__.py`: `__version__ = "0.11.0"` → `__version__ = "0.12.0"`.
* `charts/group-sync-dashboard/Chart.yaml`: `version: 0.10.0` → `version: 0.11.0`; `appVersion: "0.11.0"` → `appVersion: "0.12.0"`.

Chart history line, inserted directly above `version:` (after the `# CHART 0.10.0 …` block):

```yaml
# CHART 0.11.0 (2026-09-04), MINOR: two new modules. `backup.offsite` (OFF) renders a CronJob that
# mounts the data claim read-only and ships the newest VACUUM INTO copy to a second claim or to
# object storage through an operator-supplied CLI image, with a stdlib copy script shipped as a
# ConfigMap (scripts/offsite_backup.py), a dedicated ServiceAccount with no grants, and — under
# monitoring.prometheusRule — two rules on kube_cronjob_status_last_successful_time. Six new `fail`
# guards model its interactions with persistence, config.backup and the access mode.
# `config.retention` (membershipEventsDays 0 = forever, syncEventsDays 730) reaches the app as two
# new ConfigMap keys; appVersion moves to application 0.12.0 (below). Rendered objects for a
# release that sets neither are unchanged apart from the two ConfigMap keys and version labels.
```

App history line, inserted directly above `appVersion:`:

```yaml
# 0.12.0 (2026-09-04). Retention for the accumulated history, leader-only, after the backup, in
# bounded batches (docs/DESIGN_backup_offsite_and_retention.md). membership_event keeps forever by
# default; sync_event keeps 730 days. Four responses gain an additive `retention` object
# (/groupsyncs/{name}/events, /membership-changes, /groups/{name}, /users/{name}) so a timeline that
# begins at the retention edge says so. Two indexes on (cluster_id, observed_at) are added to SCHEMA
# and built at first start. gsd_retention_rows_deleted_total gains table="membership_event" and
# table="sync_event". MINOR: additive on the wire, new settings, no shape change.
```

`docs/CHANGELOG.md`: insert this between the intro paragraph and `## Application 0.11.0 — chart 0.10.0 — 2026-09-04` (batch A introduces the heading; if it is already present, add only the bullets under it):

```markdown
## Unreleased

- **Off-volume backup CronJob, `backup.offsite` (chart, off by default).** The other half of
  `config.backup`: a CronJob mounts the data claim read-only, picks the newest `gsd-*.db`,
  streams it to a second claim (`destination.type: pvc`, no credentials) or stages it for an
  operator-supplied S3 CLI image (`destination.type: s3`, credentials only from a Secret you
  create), writes a `.sha256` sidecar, runs `PRAGMA integrity_check` on the copy, prunes the
  destination to `keep`, and fails loudly otherwise. Under `ReadWriteOnce` the Job is pinned to
  the dashboard's node; `ReadWriteOncePod` is refused at render. Two alerts on
  `kube_cronjob_status_last_successful_time` when `monitoring.prometheusRule` is on. Restore and
  verify: `docs/RUNBOOK_backup_restore.md`. (design `DESIGN_backup_offsite_and_retention.md`)
- **Retention for the accumulated history, `config.retention`.** `membershipEventsDays: 0`
  (forever) and `syncEventsDays: 730` by default; the leader prunes after the cycle's backup, never
  before one has succeeded in this process's life, 5,000 rows per table per cycle, counted into
  `gsd_retention_rows_deleted_total{table}`. Four history responses gain `retention:
  {window_days, retained_since}` and the page says "history retained since …" where a timeline
  begins at the cut. First start after upgrade builds two `(cluster_id, observed_at)` indexes.
  Application 0.12.0, chart 0.11.0.
```

---


## Design (verbatim)

## 3. FEATURE B2 — retention for `membership_event` and `sync_event`

### 3.1 Goal

Bound the two tables that grow forever (`docs/DESIGN_metrics_refresh.md#0.2`), without ever deleting a row that has not been backed up, without ever holding the single writer for long, and without letting the page or the API imply that nothing happened before the cut.

### 3.2 Switch, defaults, why

`config.retention.membershipEventsDays: 0` and `config.retention.syncEventsDays: 730`. `0` keeps a table forever.

The trade-off, stated: **the backup exists for these rows**, so deleting them is the one side effect in this codebase that cannot be undone by the next poll. Judgment per table:

* `membership_event` — one row per join/leave. At the reference scale (62 groups, ~1,240 users) that is tens of rows a day, roughly a megabyte a year. It is the answer to "when did this person lose access?", which is the product. Deleting it is a policy decision only an operator can make, so the default is **forever** and the switch is theirs.
* `sync_event` — one row per observed sync per CR. A CR on a ten-minute schedule writes ~52k rows a year; five CRs are ~25 MB a year, and the data claim holds the database **plus** `config.backup.keep` copies of it, so that is ~125 MB a year on a 1Gi claim. It names CRs and counts, never a person, and the `/events` timeline shows the newest 200 by default. Two years bounds the claim without touching anything the audit question needs, so the default is **730 days on**.

Both are one number away from the other choice, and the page tells the reader which is in force.

### 3.3 Mechanics

* **Where:** `gsd/poller.py#Poller._after_poll`, the tail of the per-cluster loop, in the order `maintain()` → `_maybe_backup()` → `_prune_history(cluster)`. The prune is **held** while `backup_dir` is set and no backup has succeeded yet in this process (`_backup_state != "ok"`): a failing or not-yet-run backup means "do not delete what has not been copied". With backups disabled (empty `backup_dir`) retention is purely the operator's policy and runs. Standbys never back up, so they never prune — and leadership is re-checked immediately before the write, as `logincapture._prune` does.
* **How much:** `HISTORY_PRUNE_BATCH = 5000` rows per table per cycle, the same bound as `prune_login_events`; a full batch logs "more remain" and the next cycle continues. Years of backlog drain at ~300k rows/hour with the writer held for milliseconds at a time.
* **Which rows:** `observed_at < now - days`, second-resolution `Z` cutoff in the same format `now_iso()` stamps (`gsd/timeutil.py#now_iso`), so the lexicographic compare is chronological. Two indexes `(cluster_id, observed_at)` make the subselect a range seek and `MIN(observed_at)` an index seek; without them an empty prune would be a full scan every minute.
* **Counted:** `signals.note_retention("membership_event" | "sync_event", removed)`; `RETENTION_TABLES` gains both so the series are pre-seeded at 0.
* **Wire:** `retention: {"window_days": int, "retained_since": "…Z" | null}` on `/groupsyncs/{name}/events` (sync_event), `/membership-changes`, `/groups/{name}`, `/users/{name}` (membership_event). `window_days: 0` means unbounded. `retained_since` is the oldest row still held for that cluster and table — cluster-wide, because the cut is a property of the policy, not of one CR or group. The two single-call handlers become `@consistent` because they now make two store calls (R5).
* **UI:** `retentionNote(r)` renders, only when `window_days > 0`, "History retained since **T**; rows older than N days are removed by retention, so a timeline that begins there was cut there — it does not mean nothing happened before." under the CR events note, the group page's "Membership changes", and the user page's "History".

### 3.4 Files

#### 3.4.1 `local-development/gsd/config.py`

Old:

```python
    user_activity_flush_seconds: int = 60
    user_activity_retention_days: int = 400
```

New:

```python
    user_activity_flush_seconds: int = 60
    user_activity_retention_days: int = 400

    # ── RETENTION ON THE ACCUMULATED HISTORY ──────────────────────────────────────────────────────
    # The two tables the backup exists for. 0 keeps a table forever. Pruned by the leader after
    # the cycle's backup and never before one has succeeded in this process's life, 5000 rows per
    # table per cycle (poller.HISTORY_PRUNE_BATCH), so a first prune over years of rows cannot
    # hold the single writer.
    #
    # membership_event keeps FOREVER by default: one row per join or leave, a megabyte a year at
    # reference scale, and it is the answer to "when did this person lose access?" — deleting it
    # is a policy only an operator can set. sync_event keeps two years: one row per observed sync
    # per CR, tens of megabytes a year on a claim that also holds every backup copy, naming CRs
    # and counts and never a person.
    membership_events_retention_days: int = 0
    sync_events_retention_days: int = 730
```

Old:

```python
        user_activity_retention_days=_num_setting(
            raw, "GSD_USER_ACTIVITY_RETENTION_DAYS", "userActivityRetentionDays", 400, int
        ),
    )
```

New:

```python
        user_activity_retention_days=_num_setting(
            raw, "GSD_USER_ACTIVITY_RETENTION_DAYS", "userActivityRetentionDays", 400, int
        ),
        membership_events_retention_days=_num_setting(
            raw, "GSD_MEMBERSHIP_EVENTS_RETENTION_DAYS", "membershipEventsRetentionDays", 0, int
        ),
        sync_events_retention_days=_num_setting(
            raw, "GSD_SYNC_EVENTS_RETENTION_DAYS", "syncEventsRetentionDays", 730, int
        ),
    )
```

#### 3.4.2 `local-development/gsd/store.py`

Old (in `SCHEMA`):

```sql
CREATE INDEX IF NOT EXISTS sync_event_lookup
    ON sync_event(cluster_id, groupsync_name, synced_at DESC);
```

New:

```sql
CREATE INDEX IF NOT EXISTS sync_event_lookup
    ON sync_event(cluster_id, groupsync_name, synced_at DESC);
-- Retention's index (prune_sync_events, history_retained_since): the prune subselect is a
-- range seek and MIN(observed_at) an index seek. Without it an EMPTY prune is a full scan
-- every poll. An index, not a migration: CREATE INDEX IF NOT EXISTS applies at startup on an
-- existing database, which ALTER TABLE ADD COLUMN does not (see _MIGRATIONS).
CREATE INDEX IF NOT EXISTS sync_event_by_time
    ON sync_event(cluster_id, observed_at);
```

Old:

```sql
CREATE INDEX IF NOT EXISTS membership_event_by_user
    ON membership_event(cluster_id, user_name, id DESC);
```

New:

```sql
CREATE INDEX IF NOT EXISTS membership_event_by_user
    ON membership_event(cluster_id, user_name, id DESC);
-- Retention's index; same reasoning as sync_event_by_time.
CREATE INDEX IF NOT EXISTS membership_event_by_time
    ON membership_event(cluster_id, observed_at);
```

Insert before `    def record_login_read(self, cluster_id: str, read_at: str) -> None:` (exact old text is that line; new text is the block below followed by that line unchanged):

```python
    # The two history tables retention may touch. A closed tuple, interpolated into SQL by
    # _prune_history — never a caller's string.
    _HISTORY_TABLES = ("membership_event", "sync_event")

    def prune_membership_events(self, cluster_id: str, before_at: str, max_rows: int = 5000) -> int:
        """Delete membership events observed before `before_at`, at most `max_rows`. Returns rows deleted.

        THE IRREPLACEABLE TABLE. The poller calls this only after the cycle's backup and only on
        the leader (Poller._prune_history); this method enforces the batch bound, not the policy.
        Same shape and same reasons as prune_login_events: id-IN-subselect because DELETE ... LIMIT
        is not compiled into this build, and a non-positive limit deletes NOTHING because SQLite
        reads LIMIT -1 as unlimited. The subselect is served by membership_event_by_time.
        """
        return self._prune_history("membership_event", cluster_id, before_at, max_rows)

    def prune_sync_events(self, cluster_id: str, before_at: str, max_rows: int = 5000) -> int:
        """Delete sync events OBSERVED before `before_at`, at most `max_rows`. Returns rows deleted.

        observed_at, not synced_at: the window is about how long this dashboard keeps what it
        saw, and observed_at is the stamp it controls. Served by sync_event_by_time.
        """
        return self._prune_history("sync_event", cluster_id, before_at, max_rows)

    def _prune_history(self, table: str, cluster_id: str, before_at: str, max_rows: int) -> int:
        if table not in self._HISTORY_TABLES:
            raise ValueError(f"not a history table: {table!r}")
        if max_rows <= 0:
            return 0
        with self._write() as conn:
            before = conn.total_changes
            conn.execute(
                f"""DELETE FROM {table} WHERE id IN (
                       SELECT id FROM {table}
                        WHERE cluster_id=? AND observed_at < ?
                        ORDER BY observed_at LIMIT ?)""",
                (cluster_id, before_at, max_rows),
            )
            return conn.total_changes - before

    def history_retained_since(self, cluster_id: str) -> dict[str, str | None]:
        """The oldest observed_at still held, per history table — the edge retention has cut to.

        None for a table with no rows for this cluster. Two MIN()s over the (cluster_id,
        observed_at) indexes: an index seek each, not a scan, so a handler can afford it on
        every request. The API pairs it with the configured window so a timeline that begins
        here is read as CUT here rather than started here.
        """
        out: dict[str, str | None] = {}
        for table in self._HISTORY_TABLES:
            row = self._row(
                f"SELECT MIN(observed_at) AS since FROM {table} WHERE cluster_id=?", (cluster_id,)
            )
            out[table] = row["since"] if row else None
        return out

```

#### 3.4.3 `local-development/gsd/storage.py`

Old:

```python
    def prune_login_events(self, cluster_id: str, before_at: str, max_rows: int = 5000) -> int: ...
```

New:

```python
    def prune_login_events(self, cluster_id: str, before_at: str, max_rows: int = 5000) -> int: ...

    # -- retention on the accumulated history --------------------------------------------

    def prune_membership_events(self, cluster_id: str, before_at: str, max_rows: int = 5000) -> int: ...
    def prune_sync_events(self, cluster_id: str, before_at: str, max_rows: int = 5000) -> int: ...
    def history_retained_since(self, cluster_id: str) -> dict[str, str | None]: ...
```

#### 3.4.4 `local-development/gsd/poller.py`

Old: `from datetime import UTC, datetime` → New: `from datetime import UTC, datetime, timedelta`.

Insert before `class Poller:`:

```python
# Rows removed per history table per cycle by Poller._prune_history. The same bound as
# Store.prune_login_events: small enough that the single writer is never held for long, large
# enough that a backlog of years drains in hours — 5000 rows a minute is 300k an hour.
HISTORY_PRUNE_BATCH = 5000
```

Old:

```python
        # 0 so the first cycle after start takes one immediately: a pod that
        # has just come up is exactly when you want a copy on disk.
        self._next_backup = 0.0
```

New:

```python
        # 0 so the first cycle after start takes one immediately: a pod that
        # has just come up is exactly when you want a copy on disk.
        self._next_backup = 0.0
        # pending | ok | failed — what the LAST backup attempt in this process did. Retention
        # reads it: nothing is deleted until a backup has succeeded here, so a broken backup
        # holds the prune instead of the prune quietly outrunning it.
        self._backup_state = "pending"
        self._prune_held_logged = False
```

Old:

```python
        try:
            if (self.store.backup(self.settings.backup_dir, keep=self.settings.backup_keep)
                    is None):
                # None is the method's own failure contract (VACUUM error, unwritable
                # directory) — already logged with the trace in the store; counted here,
                # where the schedule lives, so the exposition can say backups are breaking
                # hours before the last-success timestamp goes stale.
                if self.signals is not None:
                    self.signals.note_backup_failure()
        except Exception:  # noqa: BLE001 - a failed backup must never stop the poll
            if self.signals is not None:
                self.signals.note_backup_failure()
            log.exception("backup failed; the poll continues and the history is unprotected")
```

New:

```python
        try:
            if (self.store.backup(self.settings.backup_dir, keep=self.settings.backup_keep)
                    is None):
                # None is the method's own failure contract (VACUUM error, unwritable
                # directory) — already logged with the trace in the store; counted here,
                # where the schedule lives, so the exposition can say backups are breaking
                # hours before the last-success timestamp goes stale.
                self._backup_state = "failed"
                if self.signals is not None:
                    self.signals.note_backup_failure()
            else:
                self._backup_state = "ok"
        except Exception:  # noqa: BLE001 - a failed backup must never stop the poll
            self._backup_state = "failed"
            if self.signals is not None:
                self.signals.note_backup_failure()
            log.exception("backup failed; the poll continues and the history is unprotected")

    def _prune_history(self, cluster: ClusterConfig) -> None:
        """Retention on membership_event and sync_event, AFTER the backup and never ahead of one.

        Three gates, in order. The windows: 0 disables a table, both 0 is a no-op. The backup:
        while backup_dir is set, nothing is deleted until a backup has SUCCEEDED in this process
        — a failing backup holds the prune rather than the prune outrunning it, and a standby
        never backs up so never prunes. Leadership: re-checked right before the write, as
        logincapture._prune does, because the per-cycle check above is a cycle old.

        Bounded at HISTORY_PRUNE_BATCH per table per cycle so a first prune over years of rows
        cannot hold the single writer; a full batch means more remains and the next cycle
        continues. Counted into gsd_retention_rows_deleted_total{table} from the same number the
        log line reports. Never raises: a prune failure is not a poll failure.
        """
        windows = (
            ("membership_event", self.settings.membership_events_retention_days,
             self.store.prune_membership_events),
            ("sync_event", self.settings.sync_events_retention_days,
             self.store.prune_sync_events),
        )
        if all(days <= 0 for _, days, _ in windows):
            return
        if self.settings.backup_dir and self._backup_state != "ok":
            if not self._prune_held_logged:
                log.warning("%s: retention is held until a backup succeeds in this process "
                            "(last attempt: %s)", cluster.name, self._backup_state)
                self._prune_held_logged = True
            return
        self._prune_held_logged = False
        if self.elector is not None and not self.elector.is_leader:
            return
        try:
            for table, days, prune in windows:
                if days <= 0:
                    continue
                before = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
                removed = prune(cluster.name, before, max_rows=HISTORY_PRUNE_BATCH)
                if removed:
                    if self.signals is not None:
                        self.signals.note_retention(table, removed)
                    log.info("%s: pruned %d %s row(s) older than %s%s", cluster.name, removed,
                             table, before,
                             " (more remain; continuing next cycle)"
                             if removed >= HISTORY_PRUNE_BATCH else "")
        except Exception:  # noqa: BLE001 - retention must never stop the poll
            log.exception("%s: retention prune failed; the poll continues", cluster.name)

    def _after_poll(self, cluster: ClusterConfig) -> None:
        """The upkeep tail of a cycle, in an order that is the point: checkpoint, then the
        backup, then retention — so nothing is deleted before the copy that would hold it."""
        # After the write, never during it, and never from a request handler:
        # whatever upkeep the engine needs may wait on open readers, and that wait
        # is free here and would be user-visible latency anywhere else. The poller
        # does not know or care what the engine actually does — for SQLite it is a
        # WAL checkpoint; for another engine it may be nothing at all.
        self.store.maintain()
        self._maybe_backup()
        self._prune_history(cluster)
```

Old (in `_run_cluster`):

```python
                # After the write, never during it, and never from a request handler:
                # whatever upkeep the engine needs may wait on open readers, and that wait
                # is free here and would be user-visible latency anywhere else. The poller
                # does not know or care what the engine actually does — for SQLite it is a
                # WAL checkpoint; for another engine it may be nothing at all.
                self.store.maintain()
                self._maybe_backup()
```

New:

```python
                self._after_poll(cluster)
```

#### 3.4.5 `local-development/gsd/metrics.py`

Old: `RETENTION_TABLES = ("login_event", "dashboard_user_activity")`
New: `RETENTION_TABLES = ("login_event", "dashboard_user_activity", "membership_event", "sync_event")`

Old:

```python
        retention = CounterMetricFamily(
            "gsd_retention_rows_deleted_total",
            "Rows removed by retention, by table. login_event deletes are bounded at "
            "5000/cycle, so a rate pinned at that ceiling means the backlog is not "
            "draining. Only tables with a retention mechanism appear; membership_event "
            "and sync_event deliberately have none. Per replica (leader): sum().",
            labels=["table"],
        )
```

New:

```python
        retention = CounterMetricFamily(
            "gsd_retention_rows_deleted_total",
            "Rows removed by retention, by table. login_event, membership_event and "
            "sync_event deletes are bounded at 5000/cycle, so a rate pinned at that ceiling "
            "means the backlog is not draining; membership_event and sync_event prune only "
            "after a successful backup in the leader's life. Per replica (leader): sum().",
            labels=["table"],
        )
```

#### 3.4.6 `local-development/gsd/api.py`

Insert before `    def _config_summary(cluster_id: str) -> dict | None:`:

```python
    def history_retention(cluster_id: str, table: str) -> dict:
        """The retention edge of one history table, for the wire.

        `window_days` is the configured window (0 = kept forever); `retained_since` is the
        oldest row still held for this cluster, or null. Together they let a page say
        "history retained since T" where a timeline begins at the cut — without them an
        empty or short list reads as "nothing happened", which is the false absence this
        dashboard exists to avoid. Callers are @consistent: this is a second store call.
        """
        days = {
            "membership_event": settings.membership_events_retention_days,
            "sync_event": settings.sync_events_retention_days,
        }[table]
        return {
            "window_days": max(0, int(days)),
            "retained_since": store.history_retained_since(cluster_id).get(table),
        }

```

Old:

```python
    @app.get("/api/clusters/{cluster_id}/groupsyncs/{name}/events")
    def list_events(
```

New:

```python
    @app.get("/api/clusters/{cluster_id}/groupsyncs/{name}/events")
    @consistent
    def list_events(
```

Old:

```python
            "note": "accumulated from polling; covers only the period since this dashboard started",
            "events": events,
        }
```

New:

```python
            "note": "accumulated from polling; covers only the period since this dashboard started",
            # Where retention has cut the timeline, if anywhere. Cluster-wide: the edge is a
            # property of the policy, not of this CR.
            "retention": history_retention(cluster_id, "sync_event"),
            "events": events,
        }
```

Old:

```python
    @app.get("/api/clusters/{cluster_id}/membership-changes")
    def membership_changes(
```

New:

```python
    @app.get("/api/clusters/{cluster_id}/membership-changes")
    @consistent
    def membership_changes(
```

Old:

```python
            "note": "accumulated from polling; covers only the period since this dashboard started",
            "changes": events,
        }
```

New:

```python
            "note": "accumulated from polling; covers only the period since this dashboard started",
            "retention": history_retention(cluster_id, "membership_event"),
            "changes": events,
        }
```

Old (group_detail, deleted branch): `                "changes": history,` → New:

```python
                "changes": history,
                "retention": history_retention(cluster_id, "membership_event"),
```

Old (group_detail, live branch):

```python
            "changes": store.membership_events(cluster_id, group_name=name, limit=100),
```

New:

```python
            "changes": store.membership_events(cluster_id, group_name=name, limit=100),
            "retention": history_retention(cluster_id, "membership_event"),
```

Old (user_detail): `            "changes": changes,` → New:

```python
            "changes": changes,
            "retention": history_retention(cluster_id, "membership_event"),
```

#### 3.4.7 `local-development/gsd/static/index.html`

Insert immediately before the line `function timelineChart(events) {`:

```js
/* Retention makes a timeline's first row a CUT, not a beginning. Said only when a window is in
   force: window_days 0 keeps everything, and the `note` beside it already covers "since this
   dashboard started". `retained_since` is the oldest row still held on this cluster. */
function retentionNote(r) {
  if (!r || !(r.window_days > 0)) return "";
  const since = r.retained_since
    ? `History retained since <strong>${esc(fmtTime(r.retained_since))}</strong>; `
    : "";
  return `<div class="muted" style="font-size:11px;margin-bottom:6px">${since}rows older than
    ${Number(r.window_days)} days are removed by retention, so a timeline that begins there was
    cut there — it does not mean nothing happened before.</div>`;
}

```

Old:

```js
    <h3 style="margin-top:14px">Observed syncs</h3>
    <div class="muted" style="font-size:11px;margin-bottom:6px">${esc(ev.note || "")}</div>
```

New:

```js
    <h3 style="margin-top:14px">Observed syncs</h3>
    <div class="muted" style="font-size:11px;margin-bottom:6px">${esc(ev.note || "")}</div>
    ${retentionNote(ev.retention)}
```

Old:

```js
  <section class="card">
    <h2>Membership changes</h2>
    ${changeBody}
  </section>`;
```

New:

```js
  <section class="card">
    <h2>Membership changes</h2>
    ${retentionNote(d.retention)}
    ${changeBody}
  </section>`;
```

Old:

```js
  <section class="card">
    <h2>History</h2>
    ${(d.changes || []).length === 0
```

New:

```js
  <section class="card">
    <h2>History</h2>
    ${retentionNote(d.retention)}
    ${(d.changes || []).length === 0
```

#### 3.4.8 `charts/group-sync-dashboard/values.yaml` — `config.retention`

Old:

```yaml
  backup:
    enabled: true
    dir: /data/backup
    intervalHours: 6
    keep: 4     # 4 x 6h = the last day, at roughly the size of the database each
```

New:

```yaml
  backup:
    enabled: true
    dir: /data/backup
    intervalHours: 6
    keep: 4     # 4 x 6h = the last day, at roughly the size of the database each

  # Retention on the accumulated history — the two tables the backup above exists for.
  # 0 keeps a table forever. The leader prunes after each cycle's backup and NEVER before one
  # has succeeded in its own life (a failing backup holds the prune), 5000 rows per table per
  # cycle so years of backlog cannot hold the single writer, counted into
  # gsd_retention_rows_deleted_total{table}. The page and the API say where the cut is
  # ("history retained since ...") so a timeline that begins there is not read as empty before.
  #
  # membershipEventsDays 0 — FOREVER — by judgment: one row per join or leave, about a megabyte
  # a year at reference scale, and it is the answer to "when did this person lose access?".
  # Deleting that is a policy an operator sets, not a default a chart picks.
  # syncEventsDays 730 by judgment: one row per observed sync per CR — a ten-minute schedule
  # is ~52k rows a year per CR, tens of megabytes a year on a claim that also holds every
  # backup copy — naming CRs and counts and never a person. Two years bounds the claim.
  retention:
    membershipEventsDays: 0
    syncEventsDays: 730
```

#### 3.4.9 `charts/group-sync-dashboard/templates/configmap.yaml`

Old: `    userActivityRetentionDays: {{ .Values.config.userActivity.retentionDays }}`

New:

```yaml
    userActivityRetentionDays: {{ .Values.config.userActivity.retentionDays }}
    # Retention on the irreplaceable history; 0 keeps forever. See values.yaml config.retention.
    membershipEventsRetentionDays: {{ .Values.config.retention.membershipEventsDays }}
    syncEventsRetentionDays: {{ .Values.config.retention.syncEventsDays }}
```

#### 3.4.10 `charts/group-sync-dashboard/README.md` — retention rows

After the "Half an answer by design" paragraph (now ending "…never grows credentials for object storage.") and before `### Off-volume backup — \`backup.offsite\``, insert:

```markdown
### Retention on the history

| Key | Default | Notes |
|---|---|---|
| `config.retention.membershipEventsDays` | `0` | `0` keeps forever — one row per join/leave, ~1 MB/year, and the answer to "when did this person lose access?". Set a window only as a deliberate policy |
| `config.retention.syncEventsDays` | `730` | one row per observed sync per CR (~52k/year per ten-minute CR); names CRs and counts, never a person. `0` keeps forever |

The leader prunes **after** the cycle's backup and never before one has succeeded in its own
life, 5,000 rows per table per cycle, counted into `gsd_retention_rows_deleted_total{table}`. The
API and the page state the cut (`retention.retained_since`), so a timeline that begins at the edge
is read as cut there, not started there.
```

#### 3.4.11 `local-development/API.md`

After the `/events` paragraph ending `The response says so in a \`note\` field.`, add:

```markdown
Since 0.12.0 the response also carries `retention: {"window_days": N, "retained_since": "…Z"|null}`
for `sync_event`. `window_days` is the configured window (`0` = kept forever) and `retained_since`
is the oldest observation still held on this cluster — a timeline that begins there was cut
there by retention, which is a different fact from "the dashboard started there".
```

After the `/membership-changes` paragraph ending `…did not come from a sync.`, add:

```markdown
Since 0.12.0: `retention` for `membership_event`, the same shape as on `/events`. With the default
`membershipEventsDays: 0` it reads `{"window_days": 0, "retained_since": <oldest row>}`.
```

Old (groups/{name}): `Adds \`members\`, \`changes\` and \`bindings\`.` → New: `Adds \`members\`, \`changes\`, \`bindings\` and, since 0.12.0, \`retention\` (the \`membership_event\` window and edge — same shape as on \`/membership-changes\`).`

In `/users/{name}`, after `…so the detail page and the list cannot disagree.`, add: `Since 0.12.0 it carries \`retention\` for \`membership_event\`, the same shape as on \`/membership-changes\`.`

#### 3.4.12 `README.md` — Not built yet

Old:

```markdown
Effective-permission expansion, log-scrape enrichment, the group-count cliff alert (needs a
floor as well as a ratio), retention on the accumulated history, per-namespace PDF reports
```

New:

```markdown
Effective-permission expansion, log-scrape enrichment, the group-count cliff alert (needs a
floor as well as a ratio), per-namespace PDF reports
```

#### 3.4.13 `docs/DESIGN_metrics_refresh.md` — §0.2

After the paragraph ending `…vocabulary is written to be extended if those tables ever gain one.`, add:

```markdown
*(Extended 2026-09-04: `membership_event` and `sync_event` gained retention in application 0.12.0
— `gsd/poller.py#Poller._prune_history`, `docs/DESIGN_backup_offsite_and_retention.md` — and
`RETENTION_TABLES` now names all four tables. §10's exclusion is therefore closed by a later
change, not by this one.)*
```

#### 3.4.14 Tests — NEW `local-development/tests/test_history_retention.py`

```python
"""Retention on the two tables the backup exists for.

The claims, each with its test: pruned by age; bounded per call; nothing on a non-positive
limit; leader-only; after the backup and never before one has succeeded; counted into the
metric from the same number; both defaults, in the app and in the chart; and the wire says
where the cut is.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess
from datetime import UTC, datetime, timedelta

import pytest
import yaml
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings, load_settings
from gsd.metrics import RETENTION_TABLES, RuntimeSignals
from gsd.poller import HISTORY_PRUNE_BATCH, Poller
from gsd.store import Store

REPO = pathlib.Path(__file__).resolve().parents[2]
CHART = REPO / "charts" / "group-sync-dashboard"
INDEX = REPO / "local-development" / "gsd" / "static" / "index.html"
CLUSTER = ClusterConfig(name="crc", api_url="https://api.crc.testing:6443", token_env="X")


def _iso(days_ago: float) -> str:
    return (datetime.now(UTC) - timedelta(days=days_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _seed(store: Store, table: str, n: int, days_ago: float, cluster: str = "crc") -> None:
    """Rows straight into the table: the poller's own writes stamp now_iso() and cannot be
    back-dated through the public methods."""
    with store._write() as conn:
        if table == "membership_event":
            conn.executemany(
                """INSERT INTO membership_event(cluster_id, group_name, user_name, change,
                       observed_at, group_synced_at) VALUES(?,?,?,'added',?,NULL)""",
                [(cluster, "g", f"u{i}", _iso(days_ago + i / 86400)) for i in range(n)],
            )
        else:
            conn.executemany(
                """INSERT INTO sync_event(cluster_id, groupsync_name, groupsync_namespace,
                       synced_at, observed_at, schedule, group_count) VALUES(?,?,?,?,?,?,?)""",
                [(cluster, "corp", "ns", f"{_iso(days_ago + i / 86400)}", _iso(days_ago + i / 86400),
                  "0 * * * *", 1) for i in range(n)],
            )


def _count(store: Store, table: str, cluster: str = "crc") -> int:
    return store._rows(f"SELECT COUNT(*) AS n FROM {table} WHERE cluster_id=?", (cluster,))[0]["n"]


@pytest.fixture()
def store(tmp_path):
    s = Store(str(tmp_path / "gsd.db"))
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    s.upsert_cluster("other", "https://api.other:6443", True)
    yield s
    s.close()


class _Elector:
    def __init__(self, leader: bool):
        self.is_leader = leader


class TestStorePrune:
    @pytest.mark.parametrize("table,prune", [
        ("membership_event", "prune_membership_events"), ("sync_event", "prune_sync_events")])
    def test_prunes_by_age_and_leaves_the_rest(self, store, table, prune):
        _seed(store, table, 10, days_ago=800)
        _seed(store, table, 10, days_ago=10)
        _seed(store, table, 5, days_ago=800, cluster="other")
        removed = getattr(store, prune)("crc", _iso(730))
        assert removed == 10
        assert _count(store, table) == 10
        assert _count(store, table, "other") == 5, "another cluster's rows were touched"

    @pytest.mark.parametrize("table,prune", [
        ("membership_event", "prune_membership_events"), ("sync_event", "prune_sync_events")])
    def test_each_call_is_bounded_and_the_backlog_drains_across_calls(self, store, table, prune):
        _seed(store, table, 12_000, days_ago=800)
        cutoff = _iso(730)
        assert getattr(store, prune)("crc", cutoff) == 5000
        assert getattr(store, prune)("crc", cutoff) == 5000
        assert getattr(store, prune)("crc", cutoff) == 2000
        assert getattr(store, prune)("crc", cutoff) == 0

    def test_a_non_positive_limit_deletes_nothing(self, store):
        """SQLite reads LIMIT -1 as unlimited — the opposite of the contract."""
        _seed(store, "membership_event", 10, days_ago=800)
        assert store.prune_membership_events("crc", _iso(730), max_rows=0) == 0
        assert store.prune_membership_events("crc", _iso(730), max_rows=-1) == 0
        assert _count(store, "membership_event") == 10

    def test_retained_since_is_the_oldest_row_left(self, store):
        _seed(store, "membership_event", 3, days_ago=800)
        _seed(store, "membership_event", 1, days_ago=100)
        assert store.history_retained_since("crc")["membership_event"] == _iso(800)
        store.prune_membership_events("crc", _iso(730))
        assert store.history_retained_since("crc")["membership_event"] == _iso(100)
        assert store.history_retained_since("other") == {"membership_event": None, "sync_event": None}

    def test_the_retention_indexes_exist(self, store):
        names = {r["name"] for r in store._rows("SELECT name FROM sqlite_master WHERE type='index'")}
        assert {"membership_event_by_time", "sync_event_by_time"} <= names


class _Recording(Store):
    """A Store that records the order of its upkeep calls."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.calls: list[str] = []

    def maintain(self):
        self.calls.append("maintain")
        return super().maintain()

    def backup(self, directory, keep=3):
        self.calls.append("backup")
        return super().backup(directory, keep)

    def prune_membership_events(self, cluster_id, before_at, max_rows=5000):
        self.calls.append("prune_membership_events")
        return super().prune_membership_events(cluster_id, before_at, max_rows)

    def prune_sync_events(self, cluster_id, before_at, max_rows=5000):
        self.calls.append("prune_sync_events")
        return super().prune_sync_events(cluster_id, before_at, max_rows)


@pytest.fixture()
def recording(tmp_path):
    s = _Recording(str(tmp_path / "gsd.db"))
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    yield s
    s.close()


def _settings(tmp_path, **overrides) -> Settings:
    base = dict(clusters=[CLUSTER], db_path=str(tmp_path / "gsd.db"),
                backup_dir=str(tmp_path / "backup"),
                membership_events_retention_days=365, sync_events_retention_days=365)
    base.update(overrides)
    return Settings(**base)


class TestPollerPrune:
    def test_order_is_maintain_backup_then_prune(self, recording, tmp_path):
        poller = Poller(recording, _settings(tmp_path))
        poller._after_poll(CLUSTER)
        assert recording.calls == ["maintain", "backup", "prune_membership_events", "prune_sync_events"]

    def test_nothing_is_deleted_until_a_backup_has_succeeded(self, recording, tmp_path):
        """A failing backup HOLDS the prune; the first good one releases it."""
        _seed(recording, "membership_event", 5, days_ago=800)
        poller = Poller(recording, _settings(tmp_path, backup_dir="/proc/nonexistent-and-unwritable"))
        poller._after_poll(CLUSTER)
        assert "prune_membership_events" not in recording.calls
        assert _count(recording, "membership_event") == 5
        poller.settings = _settings(tmp_path)          # backups now work
        poller._next_backup = 0.0
        poller._after_poll(CLUSTER)
        assert _count(recording, "membership_event") == 0

    def test_with_backups_disabled_retention_is_the_operators_policy(self, recording, tmp_path):
        _seed(recording, "sync_event", 5, days_ago=800)
        Poller(recording, _settings(tmp_path, backup_dir=""))._after_poll(CLUSTER)
        assert "backup" not in recording.calls and _count(recording, "sync_event") == 0

    def test_a_standby_does_not_prune(self, recording, tmp_path):
        _seed(recording, "membership_event", 5, days_ago=800)
        poller = Poller(recording, _settings(tmp_path), elector=_Elector(leader=False))
        poller._backup_state = "ok"                     # the gate under test is leadership
        poller._prune_history(CLUSTER)
        assert _count(recording, "membership_event") == 5

    def test_zero_keeps_everything_and_calls_nothing(self, recording, tmp_path):
        _seed(recording, "membership_event", 5, days_ago=5000)
        _seed(recording, "sync_event", 5, days_ago=5000)
        poller = Poller(recording, _settings(tmp_path, membership_events_retention_days=0,
                                              sync_events_retention_days=0))
        poller._after_poll(CLUSTER)
        assert not [c for c in recording.calls if c.startswith("prune")]
        assert _count(recording, "membership_event") == 5 and _count(recording, "sync_event") == 5

    def test_a_table_at_zero_is_untouched_while_the_other_prunes(self, recording, tmp_path):
        _seed(recording, "membership_event", 5, days_ago=5000)
        _seed(recording, "sync_event", 5, days_ago=5000)
        Poller(recording, _settings(tmp_path, membership_events_retention_days=0))._after_poll(CLUSTER)
        assert _count(recording, "membership_event") == 5 and _count(recording, "sync_event") == 0

    def test_deletions_reach_the_metric_by_table_and_stay_bounded(self, recording, tmp_path):
        _seed(recording, "membership_event", HISTORY_PRUNE_BATCH + 7, days_ago=800)
        _seed(recording, "sync_event", 3, days_ago=800)
        signals = RuntimeSignals()
        poller = Poller(recording, _settings(tmp_path), signals=signals)
        poller._after_poll(CLUSTER)
        snap = signals.snapshot()["retention"]
        assert snap == {"membership_event": HISTORY_PRUNE_BATCH, "sync_event": 3}
        poller._after_poll(CLUSTER)
        assert signals.snapshot()["retention"]["membership_event"] == HISTORY_PRUNE_BATCH + 7

    def test_the_metric_family_declares_both_tables(self):
        assert {"membership_event", "sync_event"} <= set(RETENTION_TABLES)


class TestDefaults:
    def test_the_app_defaults(self):
        s = Settings()
        assert s.membership_events_retention_days == 0
        assert s.sync_events_retention_days == 730

    def test_the_configmap_keys_and_env_are_read(self, tmp_path, monkeypatch):
        p = tmp_path / "clusters.yaml"
        p.write_text("clusters:\n  - name: crc\n    apiUrl: https://api.crc.testing:6443\n"
                     "    tokenEnv: X\nmembershipEventsRetentionDays: 30\nsyncEventsRetentionDays: 0\n")
        s = load_settings(str(p))
        assert (s.membership_events_retention_days, s.sync_events_retention_days) == (30, 0)
        monkeypatch.setenv("GSD_SYNC_EVENTS_RETENTION_DAYS", "90")
        assert load_settings(str(p)).sync_events_retention_days == 90

    @pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")
    def test_the_chart_defaults_equal_the_app_defaults(self):
        """Two sources of one number; the environments README test applies the same rule."""
        done = subprocess.run(["helm", "template", "t", str(CHART), "--set", "ingress.host=t.example.com"],
                              capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
        cm = [d for d in yaml.safe_load_all(done.stdout)
              if d and d.get("kind") == "ConfigMap" and d["metadata"]["name"].endswith("-config")][0]
        raw = yaml.safe_load(cm["data"]["clusters.yaml"])
        assert raw["membershipEventsRetentionDays"] == Settings().membership_events_retention_days
        assert raw["syncEventsRetentionDays"] == Settings().sync_events_retention_days


@pytest.fixture()
def client(tmp_path):
    db = str(tmp_path / "gsd.db")
    s = Store(db)
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    s.record_sync_event("crc", "corp", "ns", "2026-08-02T09:00:00Z", "2026-08-02T09:00:30Z", "0 * * * *", 4)
    _seed(s, "membership_event", 2, days_ago=100)
    s.close()
    settings = Settings(clusters=[ClusterConfig(name="crc", api_url="https://api.crc.testing:6443")],
                        db_path=db, membership_events_retention_days=0, sync_events_retention_days=730,
                        view_restrictions_enabled=False)
    with TestClient(build_app(settings, run_poller=False)) as c:
        yield c


class TestWire:
    def test_events_say_the_sync_window_and_edge(self, client):
        body = client.get("/api/clusters/crc/groupsyncs/corp/events").json()
        assert body["retention"] == {"window_days": 730, "retained_since": "2026-08-02T09:00:30Z"}

    def test_membership_changes_say_forever_and_the_oldest_row(self, client):
        body = client.get("/api/clusters/crc/membership-changes").json()
        assert body["retention"]["window_days"] == 0
        assert body["retention"]["retained_since"] == _iso(100 + 1 / 86400)

    def test_group_and_user_pages_carry_it_too(self, client):
        assert "retention" in client.get("/api/clusters/crc/groups/g").json()
        assert "retention" in client.get("/api/clusters/crc/users/u0").json()

    def test_an_unknown_cluster_is_still_a_404(self, client):
        assert client.get("/api/clusters/nope/membership-changes").status_code == 404

    def test_the_page_renders_the_cut(self):
        html = INDEX.read_text()
        assert "function retentionNote(r)" in html
        assert "History retained since" in html
        assert html.count("retentionNote(") >= 4, "the CR, group and user pages must all say it"
```

(`view_restrictions_enabled` is the `Settings` field name wired to `GSD_ENABLE_VIEW_RESTRICTIONS` at `gsd/config.py#load_settings`; the implementer should confirm it against `gsd/config.py#Settings` — the field is referenced there under `# ── PER-USER VISIBILITY`. If the tests' existing fixtures pass without it, drop the kwarg; `/groups/{name}` at the self tier would otherwise 403.)

### 3.5 Verification

```sh
cd local-development && .venv/bin/python -m pytest tests/test_history_retention.py tests/test_storage_seam.py tests/test_api_contract.py tests/test_metrics.py tests/test_config.py tests/test_migrations.py tests/test_read_snapshot_scope.py tests/test_backup.py tests/test_chart_versions.py tests/test_docs_citations.py -q
# expected: all passed. test_storage_seam holds the three new Store methods to the Protocol;
# test_api_contract R5 holds list_events and membership_changes as @consistent.

.venv/bin/python -c "from gsd.config import Settings; s=Settings(); print(s.membership_events_retention_days, s.sync_events_retention_days)"
# expected: 0 730

# on a cluster after upgrade, in the leader's log:
#   schema migration lines only if pending; then per cycle, when rows exist past the window:
#   crc: pruned 5000 sync_event row(s) older than 2024-09-04T… (more remain; continuing next cycle)
# and a WARNING once if backups are failing: "retention is held until a backup succeeds in this process"
curl -s https://<host>/metrics | grep retention_rows_deleted
# expected: four series, table="membership_event" and table="sync_event" among them
curl -s https://<host>/api/clusters/<id>/membership-changes | jq .retention
# expected: {"window_days": 0, "retained_since": "<oldest row>"}
```

### 3.6 Risks and closures

| Risk | Closure |
|---|---|
| Index build at first start after upgrade on a large `sync_event` | one-off, at startup before serving, seconds at reference scale; noted in the CHANGELOG |
| A restore of an old copy is immediately pruned | the runbook says to set both windows to 0 first; the prune is also held until the post-restore backup succeeds, which is one cycle's warning |
| Prune held forever on a pod whose backups always fail | the WARNING logs once, `GroupSyncDashboardBackupStale` fires anyway; retention never outruns a broken backup by design |
| `MIN(observed_at)` per request on two tables | index seeks; `@consistent` keeps them in the handler's snapshot |
| `retained_since` for `sync_event` is cluster-wide while `/events` is per CR | documented in API.md; per-CR would need a third index for a fact the policy does not vary by CR |
| Two-format compare (`now_iso()` seconds vs. a microsecond stamp) | both tables are stamped only by `now_iso()`; the cutoff is built in the same format; login events keep their own microsecond format and their own prune |

---


## Batch closing sections (verbatim)

## 4. Questions only the operator can answer

1. **`syncEventsDays: 730` on by default** — or `0`, treating both tables as sacrosanct and leaving growth to the volume alert? The design argues 730 on size and on the fact that the rows name no person; it is a one-line change either way.
2. **AWS CLI as the S3 default command** (with `command` overridable) — or ship no default and require `command` for `s3`? The default makes the common case a two-value change; it also means the chart names a third-party tool it does not test.
3. **Keep `GroupSyncDashboardOffsiteBackupUnobserved`?** It fires permanently on a cluster without kube-state-metrics in the rule-evaluating Prometheus. The design keeps it because the alternative is a stale alert that can never fire.

---

### Critical Files for Implementation

- /Users/olasumbo/gitRepos/group-sync-dashboard/charts/group-sync-dashboard/templates/backup-offsite.yaml (new; the CronJob, its guards, SA, ConfigMap, PVC)
- /Users/olasumbo/gitRepos/group-sync-dashboard/charts/group-sync-dashboard/scripts/offsite_backup.py (new; the stdlib copy/verify/prune script, unit-tested from the chart path)
- /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/poller.py (`_after_poll`, `_prune_history`, `_backup_state`, `HISTORY_PRUNE_BATCH`)
- /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/store.py (two indexes in `SCHEMA`; `prune_membership_events`, `prune_sync_events`, `history_retained_since`)
- /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/api.py (`history_retention` helper, `@consistent` on `list_events`/`membership_changes`, the `retention` field in four responses)
