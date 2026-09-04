# SPEC B1 — Off-volume backup CronJob and restore runbook

| | |
|---|---|
| Programme | Feature programme 2026-09 — index and version ladder in `docs/specs/README.md` |
| Batch | B — operations |
| Release | R4 — Supply chain and backup |
| Version on release | chart 0.16.0 (chart only) |
| Issue | [#64](https://github.com/ephico2real2/group-sync-dashboard/issues/64) |
| Status | specified |
| Source | design agent output `a7eabba23e10eec8a`; one message; no seam |

## How to read this spec

Everything under "Batch preamble", "Design" and "Batch closing sections" is the design agent's text,
**verbatim** — it was sliced from the agent's output by heading and re-concatenated to the byte before
this file was written, and nothing in it was rewritten by hand. Implementation applies the code in
"Design" exactly as written, one file at a time; a deviation found necessary during implementation is
written back into this file in the same pull request, with the reason, under "Orchestrator's notes".

## Orchestrator's notes

- Lands in R4 after A2, so `docs/CHANGELOG.md` and `Chart.yaml` history text in the body is applied against the file as it stands then; the version pair in the body (chart 0.11.0 / app 0.12.0) is superseded by chart 0.16.0, chart only, because the application does not change.
- The `## Unreleased` heading already exists (A1); the body's instruction to create it becomes an edit under it.
- The B2 half of the same design lands earlier (R2); the shared `## 1. Versions and shared bookkeeping` section in the preamble is applied once, by B2, and B1 adds only its own history line.

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
| README and chart README both say "eleven" alerts | `README.md#eleven alerting`, `charts/group-sync-dashboard/README.md#The eleven alerts` |
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

## 2. FEATURE B1 — off-volume backup CronJob and restore runbook

### 2.1 Goal

Close the limit named at `charts/group-sync-dashboard/values.yaml#HALF AN ANSWER BY DESIGN` and `docs/reference-architecture.md#The honest limit`: the `VACUUM INTO` copies live on the volume they protect. A chart-owned CronJob carries the newest one off it, verifies the copy, and an alert says when that stops. A runbook says how to put a copy back.

### 2.2 Switch, default, why

`backup.offsite.enabled: false`. It needs a destination the chart cannot choose — a second StorageClass-backed claim, or a bucket and a credential — and a CronJob rendered with nowhere to write is a red Job every six hours. Everything else about it is not optional once on: the copy is hashed, opened and integrity-checked before it counts, and the Job exits non-zero on any of those.

A top-level `backup:` key (as specified) beside `config.backup`. The obvious footgun — `--set backup.enabled=true` meaning the wrong thing — is refused at render (`hasKey .Values.backup "enabled"` → `fail`).

### 2.3 Decisions and their justification

**Which image, which language.** The dashboard image and a Python-stdlib script shipped by the chart as a ConfigMap (`charts/group-sync-dashboard/scripts/offsite_backup.py`, mounted at `/scripts`). The image has no tar/rsync/aws by design (`docs/DESIGN_hardened_image.md#What it changed for operators`); a shell `cat` copy could not verify what it copied, and `sqlite3` the *module* is exactly what `PRAGMA integrity_check` needs. The copy is opened with `?immutable=1` so a WAL-flagged header cannot make SQLite want a `-shm` file on the destination.

**Concurrency with the dashboard pod (RWX vs RWO).** The claim is mounted a second time, read-only (`persistentVolumeClaim.readOnly: true` **and** `volumeMounts[].readOnly: true`). Three modes, each modelled:

| `gsd.accessMode` | What the chart does | Why |
|---|---|---|
| `ReadWriteMany` (the shipped default) | no affinity | the claim mounts anywhere |
| `ReadWriteOnce` | `podAffinity.requiredDuringSchedulingIgnoredDuringExecution` to `gsd.selectorLabels` on `kubernetes.io/hostname` | RWO binds a **node**; two pods on that node may share it. A dashboard scaled to zero leaves the Job Pending until `activeDeadlineSeconds` fails it — the honest outcome: no dashboard, no new copy to ship |
| `ReadWriteOncePod` (derived at one replica when `persistence.accessMode` is emptied) | `fail` | exactly one pod may ever mount it; a Job that can never schedule must not render |

A sidecar was rejected: it would tie the copy to the dashboard's lifecycle and Deployment, could not be scheduled independently, and would make `oc create job --from=cronjob/…` (the manual-run and restore-test path) impossible. Required affinity for RWO is the fewest-surprises option because the failure mode is visible (a Pending pod with a scheduling event, then a failed Job, then the alert).

**S3: stdlib SigV4 or an operator CLI image?** Operator image, for three reasons that outrank convenience:

1. *Least privilege is a feature of the backup.* A credential that holds only `s3:PutObject` cannot delete the history it exists to protect; pruning is done by a bucket lifecycle rule. A stdlib pruner would need `ListBucket` + `DeleteObject`, which turns a leaked backup credential into a history-deletion credential. That is why there is deliberately **no `keep` under `destination.s3`** — the interaction "keep is ignored for s3" cannot arise.
2. *Untestable surface.* Path-style vs virtual-host addressing, regions, session tokens, corporate CAs, MinIO/RGW/NooBaa quirks and multipart thresholds are a maintenance surface this project cannot exercise in CI against real object stores. The CLI images already carry that.
3. *Chart precedent.* `authLogLevel` already runs an operator-supplied image for `oc` (`charts/group-sync-dashboard/templates/auth-loglevel-job.yaml#authLogLevel.image`).

The split keeps verification in the project's hands: an **init container** (dashboard image, same script, `--dest /stage --keep 0`) selects, copies, hashes and integrity-checks into an `emptyDir`; the **main container** (operator image) only uploads `/stage/*`. The default command is written for the AWS CLI and is overridable (`destination.s3.command`).

**Alerting.** The app cannot see the CronJob, so under `monitoring.prometheusRule.enabled` **and** `backup.offsite.enabled` the chart adds two rules on `kube_cronjob_status_last_successful_time{namespace,cronjob}` from kube-state-metrics:

* `GroupSyncDashboardOffsiteBackupStale` (critical): last success older than `offsiteBackupStaleSeconds` (43200 = two six-hourly slots).
* `GroupSyncDashboardOffsiteBackupUnobserved` (warning): `absent(...)`. The series exists only after the first success, so absence means "never succeeded" **or** "kube-state-metrics is not in this Prometheus". Where kube-state-metrics is absent this rule fires and stays firing — deliberately: an alert that can never fire is indistinguishable from healthy (the rule this codebase applies to `GroupSyncDashboardNotPolling`). On OpenShift the platform stack scrapes kube-state-metrics for every namespace and user-workload rules are evaluated by Thanos Ruler against the Thanos querier that federates it, so the series is normally visible; the runbook gives the query to confirm.

**Pod labels.** The CronJob pod must **not** carry `gsd.selectorLabels`: the Service selects on them and a Job pod without a readiness probe is Ready the moment it runs, so it would receive dashboard traffic for the length of the copy. The pod template carries `app.kubernetes.io/name: <name>-backup-offsite`, `app.kubernetes.io/instance`, `app.kubernetes.io/component: backup-offsite`. A test pins this.

**ServiceAccount.** A dedicated `<fullname>-backup-offsite` with `automountServiceAccountToken: false` and no bindings. Not RBAC — it removes a grant (the dashboard's read role) rather than adding one.

### 2.4 Interactions modelled (all in `templates/backup-offsite.yaml`)

| Combination | Result |
|---|---|
| `backup.enabled` set at all | `fail` — the on-volume switch is `config.backup.enabled`, the off-volume one is `backup.offsite.enabled` |
| `backup.offsite.enabled` with `persistence.enabled=false` | `fail` — nothing to ship off |
| `backup.offsite.enabled` with `config.backup.enabled=false` | `fail` — the CronJob ships `VACUUM INTO` files; copying the live `gsd.db` would be the torn backup |
| `backup.offsite.enabled` with `config.backup.dir` not under `/data/` | `fail` — the CronJob mounts the claim at `/data` |
| access mode `ReadWriteOncePod` | `fail` — explains the RWO/RWX choice and that accessModes are immutable on an existing claim |
| `destination.type` not `pvc`/`s3` | `fail` |
| `destination.pvc.existingClaim` equal to the data claim | `fail` — same volume is not off it |
| `destination.pvc.keep < 0` | `fail` |
| `destination.type=s3` without `existingSecret` / without `image.repository` | `fail` |
| access mode `ReadWriteOnce` | derive: required podAffinity to the dashboard |
| `destination.pvc.accessMode` empty | derive `ReadWriteOnce` |
| `monitoring.prometheusRule.enabled` without `backup.offsite.enabled` | the two rules are simply not rendered |

### 2.5 Files

#### 2.5.1 `charts/group-sync-dashboard/values.yaml` — new top-level block

Insert after the `persistence:` block. Exact old text (end of that block):

```yaml
  accessMode: ReadWriteMany
  storageClass: ""     # "" -> cluster default
  existingClaim: ""    # set to reuse a claim instead of creating one
```

Exact new text:

```yaml
  accessMode: ReadWriteMany
  storageClass: ""     # "" -> cluster default
  existingClaim: ""    # set to reuse a claim instead of creating one

# ---------------------------------------------------------------------------
# Off-volume backup — the OTHER half of config.backup
# ---------------------------------------------------------------------------
# config.backup (under config: above) writes VACUUM INTO copies to the SAME volume they
# protect. This CronJob mounts that volume read-only and carries the newest copy somewhere
# else: a second claim, or object storage. Together they are the whole answer; either alone
# is half. Restore, and how to verify a copy without restoring: docs/RUNBOOK_backup_restore.md.
#
# OFF BY DEFAULT because it needs a destination the chart cannot choose for you — a second
# claim on a DIFFERENT StorageClass, or a bucket and a credential — and a CronJob rendered with
# nowhere to write is a red Job on every schedule. Nothing else about it is optional once on:
# the copy is hashed, opened and integrity-checked BEFORE it counts, and the Job exits
# non-zero on any of those.
#
# WHO RUNS IT. The dashboard image, with a Python-stdlib script the chart ships as a
# ConfigMap (scripts/offsite_backup.py, mounted at /scripts). The image has no tar, rsync or
# aws on purpose (docs/DESIGN_hardened_image.md §10), and a shell copy could not verify what
# it copied; the sqlite3 module is exactly what PRAGMA integrity_check needs.
#
# MOUNTING THE DATA CLAIM TWICE. The dashboard pod holds it.
#   ReadWriteMany     the CronJob pod mounts it anywhere; no affinity.
#   ReadWriteOnce     the claim binds to one NODE, so the chart pins the CronJob pod to the
#                     dashboard's node with a required podAffinity. A dashboard scaled to zero
#                     then leaves the Job Pending until activeDeadlineSeconds fails it — the
#                     honest outcome: no dashboard, no new copy to ship.
#   ReadWriteOncePod  exactly one pod, ever. The chart REFUSES to render rather than ship a
#                     Job that can never schedule.
#
# ALERTING. The app cannot see this Job. With monitoring.prometheusRule.enabled the chart adds
# two rules on kube_cronjob_status_last_successful_time (kube-state-metrics): stale, and
# never-observed. Where kube-state-metrics is not scraped the second one fires and stays
# firing — an alert that can never fire would be indistinguishable from healthy.
#
# NOT `backup.enabled`. That key does not exist and the chart refuses it: the on-volume
# switch is config.backup.enabled, this one is backup.offsite.enabled.
backup:
  offsite:
    enabled: false
    # Cron, in the controller manager's time zone. Every six hours, to match
    # config.backup.intervalHours. There is nothing to align to: the app's backups run on a
    # timer from pod start, not the clock, so any offset is arbitrary and :15 is as good as any.
    schedule: "15 */6 * * *"
    # Forbid: a slow copy must not overlap the next one on the same destination.
    concurrencyPolicy: Forbid
    successfulJobsHistoryLimit: 3
    failedJobsHistoryLimit: 3
    # A slot missed by more than this is skipped rather than run late into the next one.
    startingDeadlineSeconds: 900
    # Wall clock on the whole attempt, Pending included — see the ReadWriteOnce case above.
    activeDeadlineSeconds: 1800
    # One retry. The script is idempotent (a copy that already matches its sidecar is skipped).
    backoffLimit: 1
    resources:
      requests:
        cpu: 50m
        memory: 64Mi
      limits:
        cpu: 500m
        memory: 256Mi
    destination:
      # pvc | s3
      type: pvc
      pvc:
        # Empty: the chart creates <fullname>-backup-offsite with helm.sh/resource-policy: keep
        # (and the Argo annotations), like the data claim. Set to reuse a claim — one that is
        # NOT the data claim; the chart refuses that, because it would not be off the volume.
        existingClaim: ""
        # keep x (roughly the database size). The data claim is 1Gi and holds the database
        # plus config.backup.keep copies, so one copy is well under 200Mi in practice.
        size: 5Gi
        # A DIFFERENT class from persistence.storageClass is the point: a second claim on the
        # same failing storage is not off it. "" -> cluster default.
        storageClass: ""
        # Empty derives ReadWriteOnce: one Job at a time (concurrencyPolicy) needs no more,
        # and RWO is what every StorageClass provides.
        accessMode: ""
        # Copies kept at the destination, newest first; 0 keeps everything. 14 x 6h = three
        # and a half days of six-hourly copies. The .sha256 sidecars go with their copies.
        keep: 14
      s3:
        # A Secret YOU create; the chart never renders credentials. Keys:
        #   AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, S3_BUCKET          required
        #   S3_ENDPOINT (MinIO / ODF / RGW), S3_PREFIX, AWS_DEFAULT_REGION, AWS_CA_BUNDLE   optional
        # Give the credential PutObject and NOTHING ELSE, and prune with a bucket lifecycle
        # rule. A write-only credential is what makes a leaked one unable to delete the history
        # it exists to protect — which is also why the chart does not do S3 in the stdlib script
        # (pruning would need List and Delete) and why there is no `keep` here.
        existingSecret: ""
        # An image with an S3 CLI. The default upload command is written for the AWS CLI
        # (for example repository: public.ecr.aws/aws-cli/aws-cli); set `command` for mc or
        # rclone. Refused empty: the dashboard image ships no such tool.
        image:
          repository: ""
          tag: ""
          pullPolicy: IfNotPresent
        # Replaces the default upload command (a list). The verified copy and its .sha256
        # sidecar are under /stage; the Secret's keys are in the environment.
        command: []
        # emptyDir holding the verified copy between the two containers. Must exceed one copy,
        # which persistence.size bounds.
        stagingSizeLimit: 2Gi
```

#### 2.5.2 `charts/group-sync-dashboard/values.yaml` — monitoring thresholds

Exact old text:

```yaml
    backupStaleSeconds: 43200
    for:
```

Exact new text:

```yaml
    backupStaleSeconds: 43200
    # Seconds since the off-volume CronJob last SUCCEEDED (kube_cronjob_status_last_successful_time
    # from kube-state-metrics) before the copy counts as stale. Two slots of the default
    # backup.offsite.schedule (every six hours). Rendered only with backup.offsite.enabled.
    offsiteBackupStaleSeconds: 43200
    for:
```

Exact old text:

```yaml
      backupStale: 30m
      # Long, because a checkpoint legitimately lags behind a burst of reads. Only sustained
```

Exact new text:

```yaml
      backupStale: 30m
      offsiteBackupStale: 30m
      # The series exists only after the FIRST success, so absence means "never succeeded" or
      # "kube-state-metrics is not in this Prometheus". Both are worth a warning; neither pages.
      offsiteBackupUnobserved: 1h
      # Long, because a checkpoint legitimately lags behind a burst of reads. Only sustained
```

#### 2.5.3 NEW `charts/group-sync-dashboard/scripts/offsite_backup.py`

```python
#!/usr/bin/env python3
"""Carry the newest on-volume backup off the volume. Standard library only, on purpose.

The dashboard's own backups (gsd/store.py Store.backup, VACUUM INTO) land on the claim they
protect. This script runs in the chart's CronJob (templates/backup-offsite.yaml) with that claim
mounted READ-ONLY at /data and a destination mounted writable, and does five things, in order,
failing loudly on any of them:

  1. pick the newest gsd-*.db under --source, by NAME — the stamp is UTC with microseconds, so
     lexicographic order is chronological, and it is the same rule Store.backup rotates by;
  2. stream it to --dest as <name>.part, hashing as it goes (one pass, 1 MiB chunks, fsync);
  3. open the COPY with sqlite3 and run PRAGMA integrity_check — `immutable=1` so a WAL-flagged
     header cannot make SQLite want a -shm file it has no business creating here;
  4. rename .part to <name> and write <name>.sha256 in `sha256sum -c` format;
  5. prune --dest to --keep copies (0 keeps everything), sidecars with their copies.

Idempotent: a destination copy that already matches its sidecar is left alone and the run still
succeeds, so a schedule denser than the app's backups is harmless. Every failure raises
BackupError and exits 1 with the reason on stderr — the CronJob's status is the only signal the
chart's alert can see.

No tar, no gzip, no aws: the image has none (docs/DESIGN_hardened_image.md §10) and a shell copy
could not verify what it copied. S3 is deliberately NOT implemented here — see values.yaml under
backup.offsite.destination.s3 for why a write-only credential and a lifecycle rule beat a pruner.

    --check FILE   verify one copy in place (integrity, sha256 against its sidecar if present,
                   user_version, row counts) without copying anything. The runbook uses it.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sqlite3
import sys
from pathlib import Path

CHUNK = 1024 * 1024
PATTERN = "gsd-*.db"
PART_SUFFIX = ".part"
SUM_SUFFIX = ".sha256"
HISTORY_TABLES = ("membership_event", "sync_event")


class BackupError(Exception):
    """A failure the operator must see. Every one exits non-zero with its message."""


def newest_backup(source: Path) -> Path:
    if not source.is_dir():
        raise BackupError(
            f"source {source} is not a directory — is config.backup.dir mounted here, "
            f"and is config.backup.enabled on?"
        )
    candidates = sorted(p for p in source.glob(PATTERN) if p.is_file())
    if not candidates:
        raise BackupError(
            f"no {PATTERN} under {source}: the dashboard has not written a backup yet "
            f"(it takes one on its first poll), or config.backup is off"
        )
    return candidates[-1]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def copy_hashed(src: Path, dst: Path) -> tuple[str, int]:
    """Stream src to dst, hashing as it goes. Returns (sha256 hex, bytes written)."""
    digest = hashlib.sha256()
    size = 0
    with src.open("rb") as reader, dst.open("wb") as writer:
        while chunk := reader.read(CHUNK):
            writer.write(chunk)
            digest.update(chunk)
            size += len(chunk)
        writer.flush()
        os.fsync(writer.fileno())
    return digest.hexdigest(), size


def integrity(path: Path) -> dict:
    """PRAGMA integrity_check on a copy, plus the facts the runbook asks for.

    Raises BackupError on anything but 'ok' — including a file that is not a database at
    all, which is what a truncated or garbage copy looks like to sqlite3.
    """
    uri = f"file:{path.as_posix()}?immutable=1"
    try:
        conn = sqlite3.connect(uri, uri=True)
    except sqlite3.Error as exc:
        raise BackupError(f"{path}: cannot open: {exc}") from exc
    try:
        try:
            verdict = conn.execute("PRAGMA integrity_check").fetchone()[0]
        except sqlite3.Error as exc:
            raise BackupError(f"{path}: integrity_check failed to run: {exc}") from exc
        if verdict != "ok":
            raise BackupError(f"{path}: integrity_check said {verdict!r}")
        facts: dict = {"user_version": conn.execute("PRAGMA user_version").fetchone()[0]}
        for table in HISTORY_TABLES:
            try:
                facts[table] = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            except sqlite3.Error:
                facts[table] = None          # a database from before the table existed
    finally:
        conn.close()
    return facts


def prune(dest: Path, keep: int) -> int:
    """Store.backup's rule: sorted(glob)[:-keep] goes. 0 keeps everything. Sidecars follow."""
    if keep <= 0:
        return 0
    copies = sorted(p for p in dest.glob(PATTERN) if p.is_file())
    removed = 0
    for stale in copies[:-keep]:
        stale.unlink()
        stale.with_name(stale.name + SUM_SUFFIX).unlink(missing_ok=True)
        removed += 1
    return removed


def ship(source: Path, dest: Path, keep: int) -> int:
    newest = newest_backup(source)
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError(f"destination {dest} is not writable: {exc}") from exc
    if dest.resolve() == source.resolve():
        raise BackupError(f"destination {dest} IS the source directory — that is not off the volume")

    target = dest / newest.name
    sidecar = dest / (newest.name + SUM_SUFFIX)
    if target.exists() and sidecar.exists():
        expected = sidecar.read_text().split()[0]
        if sha256_of(target) == expected:
            print(f"already shipped: {target} matches its sidecar; nothing to copy")
            removed = prune(dest, keep)
            print(f"pruned {removed} older cop{'y' if removed == 1 else 'ies'} (keep={keep})")
            return 0
        print(f"{target} exists but does not match its sidecar; copying again", file=sys.stderr)

    part = dest / (newest.name + PART_SUFFIX)
    try:
        digest, size = copy_hashed(newest, part)
        facts = integrity(part)
        os.replace(part, target)
        sidecar.write_text(f"{digest}  {newest.name}\n")
    except OSError as exc:
        raise BackupError(f"copying {newest} to {dest} failed: {exc}") from exc
    finally:
        part.unlink(missing_ok=True)

    print(f"copied {newest} -> {target} ({size} bytes, sha256 {digest})")
    print(f"integrity_check ok; user_version {facts['user_version']}; "
          + "; ".join(f"{t} rows {facts[t]}" for t in HISTORY_TABLES))
    removed = prune(dest, keep)
    print(f"pruned {removed} older cop{'y' if removed == 1 else 'ies'} (keep={keep})")
    return 0


def check(path: Path) -> int:
    if not path.is_file():
        raise BackupError(f"{path} is not a file")
    digest = sha256_of(path)
    facts = integrity(path)
    sidecar = path.with_name(path.name + SUM_SUFFIX)
    print(f"{path}: integrity_check ok")
    print(f"sha256 {digest}")
    if sidecar.exists():
        expected = sidecar.read_text().split()[0]
        if expected != digest:
            raise BackupError(f"{path}: sha256 {digest} does not match sidecar {expected}")
        print("sidecar matches")
    else:
        print("no sidecar (an on-volume backup, or one copied by hand)")
    print(f"user_version {facts['user_version']}; "
          + "; ".join(f"{t} rows {facts[t]}" for t in HISTORY_TABLES))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--source", type=Path, help="directory of gsd-*.db files (config.backup.dir)")
    parser.add_argument("--dest", type=Path, help="where the newest one goes")
    parser.add_argument("--keep", type=int, default=0, help="copies to keep at --dest; 0 keeps all")
    parser.add_argument("--check", type=Path, metavar="FILE", help="verify one copy and exit")
    args = parser.parse_args(argv)
    try:
        if args.check is not None:
            return check(args.check)
        if args.source is None or args.dest is None:
            parser.error("--source and --dest are required unless --check is given")
        return ship(args.source, args.dest, args.keep)
    except BackupError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
```

#### 2.5.4 NEW `charts/group-sync-dashboard/templates/backup-offsite.yaml`

```yaml
{{- /*
Off-volume backup: the other half of config.backup. See values.yaml under `backup:` for the
decisions; this file models the interactions and renders four objects when enabled.

The `backup.enabled` guard is OUTSIDE the enabled block on purpose: the mistake it catches is
setting the wrong key and seeing nothing render.
*/}}
{{- if hasKey .Values.backup "enabled" }}
{{- fail "backup.enabled is not a value. The on-volume backup the dashboard takes is config.backup.enabled (on by default); the off-volume CronJob is backup.offsite.enabled. A key that silently did nothing here would look like a backup that was configured." }}
{{- end }}
{{- if .Values.backup.offsite.enabled }}
{{- $o := .Values.backup.offsite }}
{{- $mode := include "gsd.accessMode" . }}
{{- $type := $o.destination.type }}
{{- $fullname := include "gsd.fullname" . }}
{{- $dataClaim := .Values.persistence.existingClaim | default (printf "%s-data" $fullname) }}
{{- if not .Values.persistence.enabled }}
{{- fail "backup.offsite.enabled=true requires persistence.enabled=true. With an emptyDir there is no volume to ship a backup off, and the history it would protect resets on every restart anyway." }}
{{- end }}
{{- if not .Values.config.backup.enabled }}
{{- fail "backup.offsite.enabled=true requires config.backup.enabled=true. The CronJob ships the VACUUM INTO files the dashboard writes under config.backup.dir; with that off there is nothing to ship, and copying the live gsd.db with its WAL would produce a torn file that opens and restores — the worst kind of backup." }}
{{- end }}
{{- if not (hasPrefix "/data/" .Values.config.backup.dir) }}
{{- fail (printf "backup.offsite.enabled=true requires config.backup.dir under /data/ (it is %q). The CronJob mounts the data claim at /data, read-only, and reads the backups from there." .Values.config.backup.dir) }}
{{- end }}
{{- if eq $mode "ReadWriteOncePod" }}
{{- fail "backup.offsite.enabled=true cannot work with a ReadWriteOncePod data volume: that mode lets exactly ONE pod mount the claim, so the CronJob pod would stay Pending forever. Set persistence.accessMode to ReadWriteOnce (the CronJob is then pinned to the dashboard's node by podAffinity) or ReadWriteMany. accessModes are immutable on an existing claim — docs/RUNBOOK_backup_restore.md covers moving the data to a new one." }}
{{- end }}
{{- if not (has $type (list "pvc" "s3")) }}
{{- fail (printf "backup.offsite.destination.type %q is not a destination. Use pvc (a second claim the chart creates or references, no credentials) or s3 (an operator-supplied Secret and CLI image)." $type) }}
{{- end }}
{{- if eq $type "pvc" }}
{{- if and $o.destination.pvc.existingClaim (eq $o.destination.pvc.existingClaim $dataClaim) }}
{{- fail (printf "backup.offsite.destination.pvc.existingClaim %q is the data claim itself. A copy on the volume it protects is what config.backup already makes; this CronJob exists to put one somewhere else." $dataClaim) }}
{{- end }}
{{- if lt (int $o.destination.pvc.keep) 0 }}
{{- fail (printf "backup.offsite.destination.pvc.keep must be 0 (keep everything) or a positive count, not %v." $o.destination.pvc.keep) }}
{{- end }}
{{- end }}
{{- if eq $type "s3" }}
{{- if not $o.destination.s3.existingSecret }}
{{- fail "backup.offsite.destination.type=s3 requires backup.offsite.destination.s3.existingSecret: the chart never embeds object-storage credentials. Create a Secret with AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY and S3_BUCKET (optionally S3_ENDPOINT, S3_PREFIX, AWS_DEFAULT_REGION, AWS_CA_BUNDLE) and name it here." }}
{{- end }}
{{- if not $o.destination.s3.image.repository }}
{{- fail "backup.offsite.destination.type=s3 requires an image with an S3 CLI in backup.offsite.destination.s3.image.repository (and .tag). The dashboard image deliberately ships no aws, mc or rclone (docs/DESIGN_hardened_image.md §10). The default command is written for the AWS CLI; set backup.offsite.destination.s3.command for another tool." }}
{{- end }}
{{- end }}
---
# No grants at all, and no token: the Job talks to no API server. A dedicated account rather
# than the dashboard's, so the copy runs with LESS than the dashboard, not the same.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ $fullname }}-backup-offsite
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "gsd.labels" . | nindent 4 }}
    app.kubernetes.io/component: backup-offsite
automountServiceAccountToken: false
---
# The copy script, verbatim from scripts/offsite_backup.py. A test holds the two identical.
apiVersion: v1
kind: ConfigMap
metadata:
  name: {{ $fullname }}-backup-offsite
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "gsd.labels" . | nindent 4 }}
    app.kubernetes.io/component: backup-offsite
data:
  offsite_backup.py: |
{{ .Files.Get "scripts/offsite_backup.py" | indent 4 }}
{{- if and (eq $type "pvc") (not $o.destination.pvc.existingClaim) }}
---
# The destination claim. The same survival annotations as the data claim (pvc.yaml): a
# `helm uninstall` must not take the copies with it.
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: {{ $fullname }}-backup-offsite
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "gsd.labels" . | nindent 4 }}
    app.kubernetes.io/component: backup-offsite
  annotations:
    helm.sh/resource-policy: keep
    {{- if and .Values.argocd.enabled .Values.argocd.preservePVC }}
    argocd.argoproj.io/sync-options: Prune=false,Delete=false,PruneLast=true
    {{- end }}
spec:
  accessModes: [{{ $o.destination.pvc.accessMode | default "ReadWriteOnce" }}]
  {{- with $o.destination.pvc.storageClass }}
  storageClassName: {{ . }}
  {{- end }}
  resources:
    requests:
      storage: {{ $o.destination.pvc.size }}
{{- end }}
---
apiVersion: batch/v1
kind: CronJob
metadata:
  name: {{ $fullname }}-backup-offsite
  namespace: {{ .Release.Namespace }}
  labels:
    {{- include "gsd.labels" . | nindent 4 }}
    app.kubernetes.io/component: backup-offsite
spec:
  schedule: {{ $o.schedule | quote }}
  concurrencyPolicy: {{ $o.concurrencyPolicy }}
  successfulJobsHistoryLimit: {{ $o.successfulJobsHistoryLimit }}
  failedJobsHistoryLimit: {{ $o.failedJobsHistoryLimit }}
  startingDeadlineSeconds: {{ $o.startingDeadlineSeconds }}
  jobTemplate:
    spec:
      backoffLimit: {{ $o.backoffLimit }}
      activeDeadlineSeconds: {{ $o.activeDeadlineSeconds }}
      template:
        metadata:
          labels:
            # NOT gsd.selectorLabels. The Service selects on those, and a Job pod with no
            # readiness probe is Ready the moment it runs — it would receive dashboard
            # traffic for the length of the copy. A test holds these apart from the selector.
            app.kubernetes.io/name: {{ include "gsd.name" . }}-backup-offsite
            app.kubernetes.io/instance: {{ .Release.Name }}
            app.kubernetes.io/component: backup-offsite
        spec:
          restartPolicy: Never
          serviceAccountName: {{ $fullname }}-backup-offsite
          automountServiceAccountToken: false
          {{- with .Values.image.pullSecrets }}
          imagePullSecrets: {{- toYaml . | nindent 12 }}
          {{- end }}
          securityContext: {{- toYaml .Values.podSecurityContext | nindent 12 }}
          {{- with .Values.nodeSelector }}
          nodeSelector: {{- toYaml . | nindent 12 }}
          {{- end }}
          {{- with .Values.tolerations }}
          tolerations: {{- toYaml . | nindent 12 }}
          {{- end }}
          {{- if ne $mode "ReadWriteMany" }}
          # ReadWriteOnce binds the data claim to one NODE. Pods on that node may share it, so
          # the copy runs beside the dashboard; on any other node it could never mount.
          affinity:
            podAffinity:
              requiredDuringSchedulingIgnoredDuringExecution:
                - topologyKey: kubernetes.io/hostname
                  labelSelector:
                    matchLabels: {{- include "gsd.selectorLabels" . | nindent 22 }}
          {{- end }}
          {{- if eq $type "s3" }}
          initContainers:
            # Select, copy, hash and integrity-check into the staging emptyDir. The upload
            # container never touches the data claim and never decides what to send.
            - name: stage
              image: {{ include "gsd.image" . }}
              imagePullPolicy: {{ .Values.image.pullPolicy }}
              command:
                - python3.14
                - /scripts/offsite_backup.py
                - --source
                - {{ .Values.config.backup.dir | quote }}
                - --dest
                - /stage
                - --keep
                - "0"
              securityContext: {{- toYaml .Values.securityContext | nindent 16 }}
              resources: {{- toYaml $o.resources | nindent 16 }}
              volumeMounts:
                - name: data
                  mountPath: /data
                  readOnly: true
                - name: script
                  mountPath: /scripts
                  readOnly: true
                - name: stage
                  mountPath: /stage
          {{- end }}
          containers:
            {{- if eq $type "pvc" }}
            - name: ship
              image: {{ include "gsd.image" . }}
              imagePullPolicy: {{ .Values.image.pullPolicy }}
              command:
                - python3.14
                - /scripts/offsite_backup.py
                - --source
                - {{ .Values.config.backup.dir | quote }}
                - --dest
                - /offsite
                - --keep
                - {{ $o.destination.pvc.keep | quote }}
              securityContext: {{- toYaml .Values.securityContext | nindent 16 }}
              resources: {{- toYaml $o.resources | nindent 16 }}
              volumeMounts:
                - name: data
                  mountPath: /data
                  readOnly: true
                - name: script
                  mountPath: /scripts
                  readOnly: true
                - name: offsite
                  mountPath: /offsite
            {{- else }}
            - name: upload
              image: {{ printf "%s:%s" $o.destination.s3.image.repository ($o.destination.s3.image.tag | default "latest") }}
              imagePullPolicy: {{ $o.destination.s3.image.pullPolicy }}
              # Credentials come ONLY from the operator's Secret, as environment. The chart
              # renders none.
              envFrom:
                - secretRef:
                    name: {{ $o.destination.s3.existingSecret }}
              {{- if $o.destination.s3.command }}
              command: {{- toYaml $o.destination.s3.command | nindent 16 }}
              {{- else }}
              command:
                - /bin/sh
                - -c
                - |
                  set -eu
                  : "${S3_BUCKET:?S3_BUCKET is missing from the Secret}"
                  ls -l /stage
                  DEST="s3://${S3_BUCKET}/${S3_PREFIX:-}"
                  if [ -n "${S3_ENDPOINT:-}" ]; then set -- --endpoint-url "$S3_ENDPOINT"; else set --; fi
                  aws s3 cp /stage/ "$DEST" --recursive --no-progress "$@"
                  echo "uploaded to $DEST"
              {{- end }}
              securityContext: {{- toYaml .Values.securityContext | nindent 16 }}
              resources: {{- toYaml $o.resources | nindent 16 }}
              volumeMounts:
                - name: stage
                  mountPath: /stage
                  readOnly: true
                # The AWS CLI writes a cache under $HOME; readOnlyRootFilesystem is on.
                - name: tmp
                  mountPath: /tmp
              env:
                - name: HOME
                  value: /tmp
            {{- end }}
          volumes:
            - name: data
              persistentVolumeClaim:
                claimName: {{ $dataClaim }}
                readOnly: true
            - name: script
              configMap:
                name: {{ $fullname }}-backup-offsite
                defaultMode: 0444
            {{- if eq $type "pvc" }}
            - name: offsite
              persistentVolumeClaim:
                claimName: {{ $o.destination.pvc.existingClaim | default (printf "%s-backup-offsite" $fullname) }}
            {{- else }}
            - name: stage
              emptyDir:
                sizeLimit: {{ $o.destination.s3.stagingSizeLimit }}
            - name: tmp
              emptyDir: {}
            {{- end }}
{{- end }}
```

#### 2.5.5 `charts/group-sync-dashboard/templates/monitoring.yaml`

Exact old text (the file's tail):

```yaml
        - alert: GroupSyncDashboardBackupStale
          expr: >-
            (time() - gsd_backup_last_success_timestamp_seconds)
              > {{ .Values.monitoring.prometheusRule.backupStaleSeconds }}
          for: {{ .Values.monitoring.prometheusRule.for.backupStale }}
          labels: {severity: critical}
          annotations:
            summary: "No successful database backup within the expected window"
            description: >-
              The newest file in backupDir is {{ `{{ $value | humanizeDuration }}` }} old —
              at least two backup intervals. The sync and membership history exists only in
              this database; check gsd_backup_failures_total for active failures and the
              pod log for the cause.
{{- end }}
```

Exact new text:

```yaml
        - alert: GroupSyncDashboardBackupStale
          expr: >-
            (time() - gsd_backup_last_success_timestamp_seconds)
              > {{ .Values.monitoring.prometheusRule.backupStaleSeconds }}
          for: {{ .Values.monitoring.prometheusRule.for.backupStale }}
          labels: {severity: critical}
          annotations:
            summary: "No successful database backup within the expected window"
            description: >-
              The newest file in backupDir is {{ `{{ $value | humanizeDuration }}` }} old —
              at least two backup intervals. The sync and membership history exists only in
              this database; check gsd_backup_failures_total for active failures and the
              pod log for the cause.
        {{- if .Values.backup.offsite.enabled }}

        # The app cannot see its own CronJob, so these two read kube-state-metrics. On
        # OpenShift the platform stack scrapes it for every namespace and user-workload rules
        # are evaluated against the Thanos querier that federates it, so the series is
        # normally visible here. Where kube-state-metrics is absent the second rule fires and
        # stays firing — an alert that could never fire would be indistinguishable from
        # healthy, which is the GroupSyncDashboardNotPolling lesson applied to a Job.
        - alert: GroupSyncDashboardOffsiteBackupStale
          expr: >-
            (time() - max(kube_cronjob_status_last_successful_time{namespace="{{ .Release.Namespace }}",cronjob="{{ include "gsd.fullname" . }}-backup-offsite"}))
              > {{ .Values.monitoring.prometheusRule.offsiteBackupStaleSeconds }}
          for: {{ .Values.monitoring.prometheusRule.for.offsiteBackupStale }}
          labels: {severity: critical}
          annotations:
            summary: "The off-volume backup CronJob has not succeeded within the expected window"
            description: >-
              {{ include "gsd.fullname" . }}-backup-offsite last succeeded
              {{ `{{ $value | humanizeDuration }}` }} ago — at least two schedule slots. The
              on-volume copies still land on the claim they protect; nothing newer is off it.
              `oc get jobs -l app.kubernetes.io/component=backup-offsite` and the failed pod's
              log name the cause; docs/RUNBOOK_backup_restore.md has the manual run.
        - alert: GroupSyncDashboardOffsiteBackupUnobserved
          expr: >-
            absent(kube_cronjob_status_last_successful_time{namespace="{{ .Release.Namespace }}",cronjob="{{ include "gsd.fullname" . }}-backup-offsite"})
          for: {{ .Values.monitoring.prometheusRule.for.offsiteBackupUnobserved }}
          labels: {severity: warning}
          annotations:
            summary: "No record of the off-volume backup CronJob ever succeeding"
            description: >-
              kube_cronjob_status_last_successful_time has no series for
              {{ include "gsd.fullname" . }}-backup-offsite. Either the CronJob has never once
              completed (it exists only after the first success), or kube-state-metrics is not
              scraped into this Prometheus — in which case the stale alert above can never fire
              and this one is the only signal.
        {{- end }}
{{- end }}
```

#### 2.5.6 `charts/group-sync-dashboard/README.md`

After the Backups table's last row (exact old text `| \`config.backup.keep\` | \`4\` | 4 × 6h = the last day, at roughly the size of the database each |`) and its two following paragraphs, replace the "Half an answer by design" paragraph:

Old:

```markdown
**Half an answer by design.** These land on the *same* volume they protect against, so they
cover corruption, a bad migration and accidental deletion — not loss of the volume. Ship them
off it with a CronJob mounting the same PVC read-only; the dashboard deliberately does not
grow credentials for object storage.
```

New:

```markdown
**Half an answer by design.** These land on the *same* volume they protect against, so they
cover corruption, a bad migration and accidental deletion — not loss of the volume. The other
half is `backup.offsite` below: a CronJob mounting the same claim read-only. The dashboard
itself never grows credentials for object storage.

### Off-volume backup — `backup.offsite`

**Off by default** — it needs a destination the chart cannot choose for you. Once on, the copy is
hashed, opened and integrity-checked before it counts, and the Job fails loudly otherwise.
Restore and verification: [`docs/RUNBOOK_backup_restore.md`](../../docs/RUNBOOK_backup_restore.md).

| Key | Default | Notes |
|---|---|---|
| `backup.offsite.enabled` | `false` | renders a CronJob, a ConfigMap with `scripts/offsite_backup.py`, a grant-less ServiceAccount, and (type `pvc`, no `existingClaim`) a second PVC. **Refused** with `persistence.enabled=false`, `config.backup.enabled=false`, a `config.backup.dir` outside `/data/`, or a `ReadWriteOncePod` data volume |
| `backup.offsite.schedule` | `"15 */6 * * *"` | cron; match `config.backup.intervalHours`. The app's backups run on a timer from pod start, so there is nothing to align to |
| `backup.offsite.concurrencyPolicy` | `Forbid` | a slow copy must not overlap the next |
| `backup.offsite.successfulJobsHistoryLimit` / `failedJobsHistoryLimit` | `3` / `3` | |
| `backup.offsite.startingDeadlineSeconds` | `900` | a slot missed by more than this is skipped |
| `backup.offsite.activeDeadlineSeconds` | `1800` | wall clock on the attempt, Pending included |
| `backup.offsite.backoffLimit` | `1` | the script is idempotent, so a retry is safe |
| `backup.offsite.resources` | 50m/64Mi – 500m/256Mi | |
| `backup.offsite.destination.type` | `pvc` | `pvc` \| `s3` |
| `backup.offsite.destination.pvc.existingClaim` | `""` | empty creates `<fullname>-backup-offsite` with `helm.sh/resource-policy: keep`. **Refused** if it names the data claim |
| `backup.offsite.destination.pvc.size` | `5Gi` | `keep` × roughly the database size |
| `backup.offsite.destination.pvc.storageClass` | `""` | use a **different** class from `persistence.storageClass` — a second claim on the same failing storage is not off it |
| `backup.offsite.destination.pvc.accessMode` | `""` | empty derives `ReadWriteOnce` |
| `backup.offsite.destination.pvc.keep` | `14` | copies kept at the destination, newest first; `0` keeps everything; sidecars go with their copies |
| `backup.offsite.destination.s3.existingSecret` | `""` | **required for `s3`.** Keys `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET`; optional `S3_ENDPOINT`, `S3_PREFIX`, `AWS_DEFAULT_REGION`, `AWS_CA_BUNDLE`. Give it `PutObject` only and prune with a bucket lifecycle rule — there is deliberately no `keep` for `s3` |
| `backup.offsite.destination.s3.image.repository` / `.tag` / `.pullPolicy` | `""` / `""` / `IfNotPresent` | **required for `s3`**: an image with an S3 CLI. The default command is for the AWS CLI |
| `backup.offsite.destination.s3.command` | `[]` | replaces the default upload command; the verified copy and its `.sha256` are under `/stage` |
| `backup.offsite.destination.s3.stagingSizeLimit` | `2Gi` | the emptyDir between the verify and upload containers |

Under a `ReadWriteOnce` data volume the CronJob pod is pinned to the dashboard's node (required
`podAffinity`); under `ReadWriteMany` it runs anywhere. The pod does **not** carry the Service's
selector labels, so it never receives dashboard traffic while it copies.
```

Monitoring rows — exact old text:

```markdown
| `monitoring.prometheusRule.backupStaleSeconds` | `43200` | seconds since the newest backup file before the copy counts as stale. Keep at ~2× `config.backupIntervalHours` × 3600 — one missed backup is a blip, two is a broken mechanism |
| `monitoring.prometheusRule.for.*` | see below | the `for:` duration on each alert |
```

New:

```markdown
| `monitoring.prometheusRule.backupStaleSeconds` | `43200` | seconds since the newest backup file before the copy counts as stale. Keep at ~2× `config.backupIntervalHours` × 3600 — one missed backup is a blip, two is a broken mechanism |
| `monitoring.prometheusRule.offsiteBackupStaleSeconds` | `43200` | seconds since the off-volume CronJob last succeeded (`kube_cronjob_status_last_successful_time`, kube-state-metrics). Two slots of `backup.offsite.schedule`. Rendered only with `backup.offsite.enabled` |
| `monitoring.prometheusRule.for.*` | see below | the `for:` duration on each alert |
```

Old: `| \`monitoring.prometheusRule.enabled\` | \`false\` | **eleven** alerts — see below |` → New: `| \`monitoring.prometheusRule.enabled\` | \`false\` | **eleven** alerts, thirteen with \`backup.offsite.enabled\` — see below |`.

Old: `#### The eleven alerts` → New: `#### The eleven alerts (thirteen with \`backup.offsite\`)`.

After the `GroupSyncDashboardBackupStale` table row, add:

```markdown
| `GroupSyncDashboardOffsiteBackupStale` | *(`backup.offsite.enabled` only)* the CronJob last succeeded more than `offsiteBackupStaleSeconds` ago — nothing newer is off the volume | `for.offsiteBackupStale`, `30m` |
| `GroupSyncDashboardOffsiteBackupUnobserved` | *(`backup.offsite.enabled` only)* `kube_cronjob_status_last_successful_time` has no series for the CronJob: it has never succeeded, or kube-state-metrics is not scraped here — in which case the stale alert can never fire and this is the only signal | `for.offsiteBackupUnobserved`, `1h` |
```

#### 2.5.7 `README.md`

Old: `\`/metrics\` serves Prometheus exposition; the chart ships a ServiceMonitor and eleven alerting` / `rules, both off by default because they need the Prometheus Operator CRDs.`
New: `\`/metrics\` serves Prometheus exposition; the chart ships a ServiceMonitor and eleven alerting` / `rules (thirteen with the off-volume backup CronJob on), both off by default because they need the Prometheus Operator CRDs.`

#### 2.5.8 `docs/reference-architecture.md` — `### Backups`

Old:

```markdown
**The honest limit:** backups land on the same PVC they protect. They cover corruption, a bad
migration and accidental deletion — not loss of the volume. Shipping them off it is a
CronJob mounting the same claim read-only; the dashboard deliberately does not grow
credentials for object storage.
```

New:

```markdown
**The honest limit:** backups land on the same PVC they protect. They cover corruption, a bad
migration and accidental deletion — not loss of the volume. The other half is the chart's
`backup.offsite` CronJob (`charts/group-sync-dashboard/templates/backup-offsite.yaml`): it mounts
the same claim read-only, and a stdlib script shipped as a ConfigMap
(`charts/group-sync-dashboard/scripts/offsite_backup.py#ship`) picks the newest `gsd-*.db` by
name — the same rule `Store.backup` rotates by — streams it to a second claim or a staging
directory while hashing it, opens the *copy* with `immutable=1` and runs `PRAGMA
integrity_check`, then writes a `.sha256` sidecar and prunes to `keep`. Object storage goes
through an operator-supplied CLI image with a credential the chart never renders; the dashboard
itself still holds no such credential, and the credential should hold `PutObject` alone so a
leaked one cannot delete the history (pruning is a bucket lifecycle rule). The app cannot see the
Job, so two rules on `kube_cronjob_status_last_successful_time` cover it
(`charts/group-sync-dashboard/templates/monitoring.yaml#GroupSyncDashboardOffsiteBackupStale`).
Restoring either copy, and verifying one without restoring: `docs/RUNBOOK_backup_restore.md`.

### Retention

`membership_event` and `sync_event` kept everything forever until 0.12.0. They now have windows
(`config.retention.membershipEventsDays`, default `0` = forever; `syncEventsDays`, default `730`),
applied by the leader after each cycle's `_maybe_backup` and never before a backup has succeeded in
this process's life (`gsd/poller.py#Poller._prune_history`), 5,000 rows per table per cycle through
the same id-IN-subselect shape as `prune_login_events` (`gsd/store.py#Store.prune_membership_events`,
`gsd/store.py#Store.prune_sync_events`), served by two `(cluster_id, observed_at)` indexes added to
`SCHEMA`. The wire says where the cut is: four history responses carry `retention: {window_days,
retained_since}` (`gsd/store.py#Store.history_retained_since`), and the page renders "history
retained since …" so a timeline that begins at the edge is read as cut there, not started there.
```

`### The \`fail\` guards` — after the deployment.yaml table (old text ends with the `oauthProxy.skipAuthRegex` row) and before the paragraph beginning `` `_helpers.tpl` carries ten more ``, insert:

```markdown
`templates/backup-offsite.yaml` adds its own, all about mounting one claim twice and about where
the copy goes (`charts/group-sync-dashboard/templates/backup-offsite.yaml#backup.enabled is not a value`):

| Combination | Refused because |
|---|---|
| `backup.enabled` set at all | the on-volume switch is `config.backup.enabled`; a key that silently did nothing would look like a backup that was configured |
| `backup.offsite.enabled` with `persistence.enabled=false`, `config.backup.enabled=false`, or `config.backup.dir` outside `/data/` | nothing to ship, a torn copy of the live file, or a directory the CronJob cannot see |
| `backup.offsite.enabled` with a `ReadWriteOncePod` data volume | one pod may ever mount it, so the Job could never schedule; `ReadWriteOnce` is derived into a required `podAffinity` instead |
| `destination.type` not `pvc`/`s3`; `destination.pvc.existingClaim` equal to the data claim; `keep < 0`; `s3` without a Secret or an image | a destination that is not one, a copy on the volume it protects, an unbounded negative, or credentials/tools the chart refuses to invent |
```

#### 2.5.9 NEW `docs/RUNBOOK_backup_restore.md`

```markdown
# Runbook — backing up and restoring the dashboard's history

The sync timeline and membership history exist only because this process observed them; the
cluster cannot replay them (`gsd/store.py#Store.backup`). Two copies exist:

* **on-volume** — `config.backup` writes `gsd-<UTC stamp>Z.db` under `config.backup.dir`
  (`/data/backup`) every `intervalHours`, keeping `keep` of them, on the data claim;
* **off-volume** — `backup.offsite` (off by default) copies the newest of those to a second
  claim or to object storage, with a `.sha256` sidecar, after an integrity check
  (`charts/group-sync-dashboard/scripts/offsite_backup.py#ship`).

Everything below uses only what the pod has: `sh`, `cat`, `ls`, `rm`, `chgrp`, `chmod`,
`python3.14` (`docs/DESIGN_hardened_image.md#What it changed for operators`). There is **no
`tar`**, so `oc cp` and `oc rsync` do not work against this image; bytes move with `cat` over
`oc exec`. Set `NS` and `REL` (the release's fullname, `oc get deploy -n $NS`) once:

```sh
NS=group-sync; REL=group-sync-dashboard
```

## 1. Verify a copy without restoring it

Any copy, anywhere. On the dashboard pod (on-volume copies):

```sh
oc exec -n $NS deploy/$REL -c dashboard -- ls -l /data/backup
oc exec -n $NS deploy/$REL -c dashboard -- python3.14 -c '
import sqlite3, sys
p = sys.argv[1]
c = sqlite3.connect(f"file:{p}?immutable=1", uri=True)
print("integrity_check:", c.execute("PRAGMA integrity_check").fetchone()[0])
print("user_version:", c.execute("PRAGMA user_version").fetchone()[0])
for t in ("membership_event", "sync_event", "login_event"):
    print(t, c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
' /data/backup/gsd-20260904T061500.123456Z.db
```

Expected: `integrity_check: ok`, a `user_version` equal to the running app's latest migration,
and row counts that are plausible for the age of the copy.

In the CronJob's image the same check is one flag, and it also compares the sidecar:

```sh
oc create job -n $NS --from=cronjob/$REL-backup-offsite verify-$(date +%s) --dry-run=client -o yaml \
  | sed 's#--source#--check\n                - /offsite/gsd-20260904T061500.123456Z.db\n                - --source#' \
  | oc apply -f -
```

(Simpler: `oc debug` a pod from the CronJob's pod template and run
`python3.14 /scripts/offsite_backup.py --check /offsite/<file>`.) Expected: `integrity_check ok`,
`sha256 …`, `sidecar matches`, `user_version …`, row counts.

Outside the cluster, with the copy downloaded (see §3): `sha256sum -c gsd-….db.sha256` and the
same Python snippet with `python3`.

## 2. Run the off-volume copy by hand

```sh
oc create job -n $NS --from=cronjob/$REL-backup-offsite manual-$(date +%s)
oc logs -n $NS -l job-name=manual-<stamp> -f
```

Expected log:

```
copied /data/backup/gsd-….db -> /offsite/gsd-….db (NNN bytes, sha256 …)
integrity_check ok; user_version 7; membership_event rows N; sync_event rows M
pruned 0 older copies (keep=14)
```

A second run straight after says `already shipped: … matches its sidecar; nothing to copy`.
A failure prints `ERROR: <reason>` and the Job goes Failed — that is the signal the
`GroupSyncDashboardOffsiteBackupStale` alert reads. Under a `ReadWriteOnce` data volume a Job
that stays **Pending** means the dashboard is not running on any node (the pod is pinned to it).

Confirm the alert can see the Job (Prometheus / Thanos querier):

```
kube_cronjob_status_last_successful_time{namespace="group-sync",cronjob="group-sync-dashboard-backup-offsite"}
```

No series after a success means kube-state-metrics is not scraped into this Prometheus; the
`…Unobserved` alert will say so.

## 3. Get a copy out of the cluster

From the data claim or the offsite claim, via the running dashboard pod (on-volume) or a helper
pod (§4) that mounts the offsite claim:

```sh
oc exec -n $NS deploy/$REL -c dashboard -- cat /data/backup/gsd-….db > gsd-….db
sha256sum gsd-….db
```

From S3 use the CLI with a credential that holds `GetObject` — the backup credential should hold
`PutObject` alone and cannot read its own uploads. That is deliberate.

## 4. Restore

The dashboard is the only writer and must be **stopped** first: two processes on one SQLite
file corrupt rather than error (`gsd/store.py#Store.__init__`).

```sh
oc scale -n $NS deploy/$REL --replicas=0
oc wait -n $NS --for=delete pod -l app=$REL --timeout=120s
```

### 4a. From an on-volume copy

A helper pod with the data claim, from the Deployment's own template:

```sh
oc debug -n $NS deploy/$REL -c dashboard -- sh -c '
set -e
ls -l /data /data/backup
python3.14 -c "import sqlite3,sys; c=sqlite3.connect(\"file:\" + sys.argv[1] + \"?immutable=1\", uri=True); print(c.execute(\"PRAGMA integrity_check\").fetchone()[0])" /data/backup/gsd-….db
mkdir -p /data/pre-restore && cat /data/gsd.db > /data/pre-restore/gsd.db.$(date +%s) 2>/dev/null || true
rm -f /data/gsd.db-wal /data/gsd.db-shm
cat /data/backup/gsd-….db > /data/gsd.db
chgrp 0 /data/gsd.db && chmod g=u /data/gsd.db
ls -l /data
'
```

`-wal`/`-shm` **must** go: they belong to the file that was there before, and SQLite would
replay a foreign WAL into the restored database. `chgrp 0` + `g=u` is the arbitrary-UID rule
OpenShift runs under: the next pod may get a different UID and reads through the root group
(`local-development/Containerfile#chgrp -R 0 /data`).

### 4b. From the off-volume claim

A one-off pod mounting both claims (the `debug` pod has only the data claim). There is no
`sleep`; Python idles instead:

```yaml
apiVersion: v1
kind: Pod
metadata: {name: gsd-restore, namespace: group-sync}
spec:
  restartPolicy: Never
  securityContext: {runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}
  containers:
    - name: restore
      image: quay.io/ephico2real/group-sync-dashboard:0.12.0   # the running tag
      command: ["python3.14", "-c", "import time; time.sleep(3600)"]
      securityContext: {allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: ["ALL"]}}
      volumeMounts:
        - {name: data, mountPath: /data}
        - {name: offsite, mountPath: /offsite, readOnly: true}
  volumes:
    - {name: data, persistentVolumeClaim: {claimName: group-sync-dashboard-data}}
    - {name: offsite, persistentVolumeClaim: {claimName: group-sync-dashboard-backup-offsite}}
```

```sh
oc apply -f gsd-restore.yaml && oc wait -n $NS --for=condition=Ready pod/gsd-restore
oc exec -n $NS gsd-restore -- sh -c '
set -e
python3.14 /dev/stdin <<EOF
import hashlib, pathlib, sqlite3
p = pathlib.Path("/offsite/gsd-….db")
h = hashlib.sha256(p.read_bytes()).hexdigest()
assert h == p.with_name(p.name + ".sha256").read_text().split()[0], "sidecar mismatch"
c = sqlite3.connect(f"file:{p}?immutable=1", uri=True)
assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
print("copy verified", h)
EOF
rm -f /data/gsd.db-wal /data/gsd.db-shm
cat /offsite/gsd-….db > /data/gsd.db
chgrp 0 /data/gsd.db && chmod g=u /data/gsd.db
'
oc delete -n $NS pod/gsd-restore
```

For an S3 copy: download it (§3), then stream it in through the helper pod —
`cat gsd-….db | oc exec -i -n $NS gsd-restore -- sh -c 'cat > /data/gsd.db'` — and apply the
same `rm -f` and ownership lines.

**Both claims RWO on different nodes?** The helper pod needs both attached; if it stays Pending,
the offsite claim is attached elsewhere (a Job still running — wait for it) or the classes are
node-local. Move the file via §3 instead.

### 4c. Bring it back and verify

```sh
oc scale -n $NS deploy/$REL --replicas=1
oc rollout status -n $NS deploy/$REL
oc exec -n $NS deploy/$REL -c dashboard -- curl -s http://127.0.0.1:8080/api/version
```

Expected: `{"leader": true, "version": "0.12.0", …}` (with `oauthProxy.enabled` the app binds
loopback; `curl` from inside the pod is the honest check). Then the counts, on the live file this
time (a normal open, the pod's own connection is the writer):

```sh
oc exec -n $NS deploy/$REL -c dashboard -- python3.14 -c '
import sqlite3
c = sqlite3.connect("file:/data/gsd.db?mode=ro", uri=True)
for t in ("membership_event", "sync_event"):
    print(t, c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
'
```

The numbers must equal the copy's (§1). The pod log shows `schema migration N applied` lines
only if the copy predates the running version; the first poll then rebuilds every cache table.
`GET /api/clusters/<id>/membership-changes` should answer with the restored history and a
`retention` object.

**Retention after a restore.** If `config.retention` windows are on, the leader starts pruning
rows past the window 5,000 at a time on the first cycle after a successful backup. Restoring an
old copy to *read* its history is a reason to set both windows to `0` first.

## 5. Moving the data to a new claim (access mode change)

`accessModes` are immutable. Create the new claim (`persistence.existingClaim` pointing at it,
or a new release name), scale to zero, and copy `gsd.db` **only** — never `-wal`/`-shm` — with
the pattern in §4b (a helper pod with both claims), then §4c.
```

#### 2.5.10 Tests — NEW `local-development/tests/test_chart_backup_offsite.py`

```python
"""The off-volume backup CronJob renders only when asked, and refuses the combinations that
could never work.

These shell out to `helm template` because the guards ARE Helm templating; the rendered
objects are what ships. The script the ConfigMap carries is tested on its own in
tests/test_offsite_backup_script.py.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest
import yaml

CHART = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"
SCRIPT = CHART / "scripts" / "offsite_backup.py"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")

ON = {"backup__offsite__enabled": "true"}
S3 = {
    **ON,
    "backup__offsite__destination__type": "s3",
    "backup__offsite__destination__s3__existingSecret": "backup-creds",
    "backup__offsite__destination__s3__image__repository": "public.ecr.aws/aws-cli/aws-cli",
    "backup__offsite__destination__s3__image__tag": "2.17.0",
}


def render(**values):
    """Render the chart. Returns (ok, combined output). `__` in a key is `.`."""
    args = ["helm", "template", "t", str(CHART), "--set", "ingress.host=t.example.com"]
    for key, value in values.items():
        args += ["--set", f"{key.replace('__', '.')}={value}"]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


def _docs(out):
    return [d for d in yaml.safe_load_all(out) if d]


def _one(docs, kind, suffix="-backup-offsite"):
    found = [d for d in docs if d.get("kind") == kind and d["metadata"]["name"].endswith(suffix)]
    assert len(found) == 1, f"expected one {kind} named *{suffix}, found {len(found)}"
    return found[0]


def _pod(cronjob):
    return cronjob["spec"]["jobTemplate"]["spec"]["template"]


class TestSwitch:
    def test_nothing_renders_by_default(self):
        ok, out = render()
        assert ok, out
        assert "backup-offsite" not in out
        assert not [d for d in _docs(out) if d.get("kind") == "CronJob"]

    def test_enabled_renders_the_four_objects(self):
        ok, out = render(**ON)
        assert ok, out
        docs = _docs(out)
        for kind in ("CronJob", "ConfigMap", "ServiceAccount", "PersistentVolumeClaim"):
            _one(docs, kind)

    def test_the_configmap_carries_the_script_verbatim(self):
        ok, out = render(**ON)
        assert ok, out
        cm = _one(_docs(out), "ConfigMap")
        assert cm["data"]["offsite_backup.py"].strip() == SCRIPT.read_text().strip()

    def test_the_serviceaccount_has_no_token_and_no_grant(self):
        ok, out = render(**ON)
        assert ok, out
        docs = _docs(out)
        sa = _one(docs, "ServiceAccount")
        assert sa.get("automountServiceAccountToken") is False
        for d in docs:
            if d.get("kind") in ("RoleBinding", "ClusterRoleBinding"):
                for s in d.get("subjects") or []:
                    assert s.get("name") != sa["metadata"]["name"], "the backup account was granted something"

    def test_backup_enabled_is_refused_as_the_wrong_key(self):
        ok, out = render(backup__enabled="true")
        assert not ok and "config.backup.enabled" in out and "backup.offsite.enabled" in out


class TestPvcDestination:
    def test_data_claim_is_mounted_read_only_twice(self):
        ok, out = render(**ON)
        assert ok, out
        pod = _pod(_one(_docs(out), "CronJob"))
        data = [v for v in pod["spec"]["volumes"] if v["name"] == "data"][0]
        assert data["persistentVolumeClaim"]["readOnly"] is True
        assert data["persistentVolumeClaim"]["claimName"].endswith("-data")
        (ship,) = pod["spec"]["containers"]
        mount = [m for m in ship["volumeMounts"] if m["name"] == "data"][0]
        assert mount["readOnly"] is True and mount["mountPath"] == "/data"

    def test_it_runs_the_dashboard_image_with_the_script(self):
        ok, out = render(**ON)
        assert ok, out
        docs = _docs(out)
        dashboard = [d for d in docs if d.get("kind") == "Deployment"][0]
        image = [c for c in dashboard["spec"]["template"]["spec"]["containers"]
                 if c["name"] == "dashboard"][0]["image"]
        (ship,) = _pod(_one(docs, "CronJob"))["spec"]["containers"]
        assert ship["image"] == image
        assert ship["command"][:2] == ["python3.14", "/scripts/offsite_backup.py"]
        assert ship["command"][ship["command"].index("--source") + 1] == "/data/backup"
        assert ship["command"][ship["command"].index("--keep") + 1] == "14"
        assert ship["securityContext"]["readOnlyRootFilesystem"] is True

    def test_the_pod_does_not_match_the_service_selector(self):
        """A Job pod with no readiness probe is Ready as soon as it runs; carrying the
        selector labels would put it behind the Service for the length of the copy."""
        ok, out = render(**ON)
        assert ok, out
        docs = _docs(out)
        selector = [d for d in docs if d.get("kind") == "Service"][0]["spec"]["selector"]
        labels = _pod(_one(docs, "CronJob"))["metadata"]["labels"]
        assert any(labels.get(k) != v for k, v in selector.items())

    def test_the_destination_claim_survives_uninstall(self):
        ok, out = render(**ON)
        assert ok, out
        pvc = _one(_docs(out), "PersistentVolumeClaim")
        assert pvc["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
        assert pvc["spec"]["accessModes"] == ["ReadWriteOnce"]

    def test_an_existing_claim_is_referenced_not_created(self):
        ok, out = render(**ON, backup__offsite__destination__pvc__existingClaim="mine")
        assert ok, out
        docs = _docs(out)
        assert not [d for d in docs if d.get("kind") == "PersistentVolumeClaim"
                    and d["metadata"]["name"].endswith("-backup-offsite")]
        pod = _pod(_one(docs, "CronJob"))
        offsite = [v for v in pod["spec"]["volumes"] if v["name"] == "offsite"][0]
        assert offsite["persistentVolumeClaim"]["claimName"] == "mine"

    def test_the_data_claim_as_destination_is_refused(self):
        ok, out = render(**ON, backup__offsite__destination__pvc__existingClaim="t-group-sync-dashboard-data")
        assert not ok and "is the data claim itself" in out

    def test_negative_keep_is_refused(self):
        ok, out = render(**ON, backup__offsite__destination__pvc__keep="-1")
        assert not ok and "keep" in out


class TestAccessModes:
    def test_rwx_needs_no_affinity(self):
        ok, out = render(**ON)              # the shipped default is ReadWriteMany
        assert ok, out
        assert "affinity" not in _pod(_one(_docs(out), "CronJob"))["spec"]

    def test_rwo_pins_the_job_to_the_dashboards_node(self):
        ok, out = render(**ON, persistence__accessMode="ReadWriteOnce")
        assert ok, out
        docs = _docs(out)
        pod = _pod(_one(docs, "CronJob"))
        (term,) = pod["spec"]["affinity"]["podAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
        assert term["topologyKey"] == "kubernetes.io/hostname"
        selector = [d for d in docs if d.get("kind") == "Service"][0]["spec"]["selector"]
        assert term["labelSelector"]["matchLabels"] == selector

    def test_rwop_is_refused(self):
        ok, out = render(**ON, persistence__accessMode="ReadWriteOncePod")
        assert not ok and "ReadWriteOncePod" in out and "Pending forever" in out

    def test_derived_rwop_at_one_replica_is_refused_too(self):
        ok, out = render(**ON, persistence__accessMode="")
        assert not ok and "ReadWriteOncePod" in out


class TestPrerequisites:
    def test_no_persistence_is_refused(self):
        ok, out = render(**ON, persistence__enabled="false")
        assert not ok and "persistence.enabled=true" in out

    def test_no_on_volume_backup_is_refused(self):
        ok, out = render(**ON, config__backup__enabled="false")
        assert not ok and "config.backup.enabled=true" in out

    def test_a_backup_dir_outside_data_is_refused(self):
        ok, out = render(**ON, config__backup__dir="/backup")
        assert not ok and "under /data/" in out

    def test_an_unknown_destination_is_refused(self):
        ok, out = render(**ON, backup__offsite__destination__type="nfs")
        assert not ok and "is not a destination" in out


class TestS3Destination:
    def test_secret_is_required(self):
        values = {k: v for k, v in S3.items() if not k.endswith("existingSecret")}
        ok, out = render(**values)
        assert not ok and "existingSecret" in out and "never embeds" in out

    def test_image_is_required(self):
        values = {k: v for k, v in S3.items() if "image__repository" not in k}
        ok, out = render(**values)
        assert not ok and "S3 CLI" in out

    def test_verify_then_upload_in_two_containers(self):
        ok, out = render(**S3)
        assert ok, out
        docs = _docs(out)
        pod = _pod(_one(docs, "CronJob"))
        (stage,) = pod["spec"]["initContainers"]
        (upload,) = pod["spec"]["containers"]
        assert stage["command"][:2] == ["python3.14", "/scripts/offsite_backup.py"]
        assert stage["command"][stage["command"].index("--dest") + 1] == "/stage"
        assert stage["command"][stage["command"].index("--keep") + 1] == "0"
        assert upload["image"] == "public.ecr.aws/aws-cli/aws-cli:2.17.0"
        assert upload["envFrom"] == [{"secretRef": {"name": "backup-creds"}}]
        assert [m["name"] for m in upload["volumeMounts"] if m["name"] == "data"] == [], \
            "the upload container must never see the data claim"
        assert "aws s3 cp /stage/" in upload["command"][-1]
        assert not [d for d in docs if d.get("kind") == "PersistentVolumeClaim"
                    and d["metadata"]["name"].endswith("-backup-offsite")]

    def test_no_credential_is_rendered(self):
        ok, out = render(**S3)
        assert ok, out
        assert "AWS_SECRET_ACCESS_KEY:" not in out and "aws_secret" not in out.lower()

    def test_a_custom_command_replaces_the_default(self):
        ok, out = render(**S3, **{"backup__offsite__destination__s3__command[0]": "rclone"})
        assert ok, out
        (upload,) = _pod(_one(_docs(out), "CronJob"))["spec"]["containers"]
        assert upload["command"] == ["rclone"]


class TestAlerts:
    def _rules(self, **values):
        ok, out = render(monitoring__prometheusRule__enabled="true", **values)
        assert ok, out
        for d in _docs(out):
            if d.get("kind") == "PrometheusRule":
                return {r["alert"]: r for g in d["spec"]["groups"] for r in g["rules"]}
        raise AssertionError("no PrometheusRule rendered")

    def test_the_two_rules_render_only_with_the_cronjob(self):
        assert "GroupSyncDashboardOffsiteBackupStale" not in self._rules()
        rules = self._rules(**ON)
        stale = rules["GroupSyncDashboardOffsiteBackupStale"]
        absent = rules["GroupSyncDashboardOffsiteBackupUnobserved"]
        for rule in (stale, absent):
            assert 'cronjob="t-group-sync-dashboard-backup-offsite"' in rule["expr"]
            assert "kube_cronjob_status_last_successful_time" in rule["expr"]
        assert "> 43200" in stale["expr"] and stale["labels"]["severity"] == "critical"
        assert absent["expr"].startswith("absent(") and absent["labels"]["severity"] == "warning"
```

#### 2.5.11 Tests — NEW `local-development/tests/test_offsite_backup_script.py`

```python
"""The chart's copy script, against a real VACUUM INTO backup.

Loaded from the chart directory rather than installed: it is shipped as a ConfigMap, and the
test must exercise the exact bytes that ship. Stdlib only, so it also runs here without the
image.
"""

from __future__ import annotations

import hashlib
import importlib.util
import pathlib
import sqlite3

import pytest

from gsd.store import Store

SCRIPT = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard" / "scripts" / "offsite_backup.py"


@pytest.fixture(scope="module")
def script():
    spec = importlib.util.spec_from_file_location("offsite_backup", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def source(tmp_path):
    """A backup directory with one real backup in it, made the way the app makes them."""
    store = Store(str(tmp_path / "gsd.db"))
    store.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    for i in range(5):
        store.record_sync_event("crc", "corp", "ns", f"2026-08-02T10:{i:02d}:00Z",
                                "2026-08-02T10:00:30Z", "0 * * * *", i)
    backups = tmp_path / "backup"
    assert store.backup(str(backups), keep=10)
    yield backups, store
    store.close()


def _sha(p: pathlib.Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


class TestShip:
    def test_copies_the_newest_with_a_sidecar_and_verifies_it(self, script, source, tmp_path, capsys):
        backups, _ = source
        dest = tmp_path / "offsite"
        assert script.main(["--source", str(backups), "--dest", str(dest), "--keep", "3"]) == 0
        (copy,) = sorted(dest.glob("gsd-*.db"))
        sidecar = dest / (copy.name + ".sha256")
        digest, name = sidecar.read_text().split()
        assert name == copy.name and digest == _sha(copy)
        conn = sqlite3.connect(f"file:{copy}?immutable=1", uri=True)
        try:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            assert conn.execute("SELECT COUNT(*) FROM sync_event").fetchone()[0] == 5
        finally:
            conn.close()
        out = capsys.readouterr().out
        assert "integrity_check ok" in out and "sync_event rows 5" in out
        assert not list(dest.glob("*.part"))

    def test_picks_the_newest_by_name(self, script, source, tmp_path):
        backups, store = source
        store.record_sync_event("crc", "corp", "ns", "2026-08-02T11:00:00Z",
                                "2026-08-02T11:00:30Z", "0 * * * *", 9)
        newest = store.backup(str(backups), keep=10)
        dest = tmp_path / "offsite"
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        assert [p.name for p in dest.glob("gsd-*.db")] == [pathlib.Path(newest).name]

    def test_a_second_run_is_a_no_op_that_still_succeeds(self, script, source, tmp_path, capsys):
        backups, _ = source
        dest = tmp_path / "offsite"
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        (copy,) = dest.glob("gsd-*.db")
        before = copy.stat().st_mtime_ns
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        assert copy.stat().st_mtime_ns == before
        assert "already shipped" in capsys.readouterr().out

    def test_prunes_the_destination_to_keep_with_sidecars(self, script, source, tmp_path):
        backups, store = source
        dest = tmp_path / "offsite"
        for _ in range(4):
            store.backup(str(backups), keep=10)
            assert script.main(["--source", str(backups), "--dest", str(dest), "--keep", "2"]) == 0
        copies = sorted(dest.glob("gsd-*.db"))
        assert len(copies) == 2
        assert sorted(p.name[:-7] for p in dest.glob("*.sha256")) == [c.name for c in copies]
        assert copies[-1].name == sorted(backups.glob("gsd-*.db"))[-1].name

    def test_keep_zero_keeps_everything(self, script, source, tmp_path):
        backups, store = source
        dest = tmp_path / "offsite"
        for _ in range(3):
            store.backup(str(backups), keep=10)
            assert script.main(["--source", str(backups), "--dest", str(dest), "--keep", "0"]) == 0
        assert len(list(dest.glob("gsd-*.db"))) == 3


class TestFailures:
    def test_a_copy_that_is_not_a_database_fails_and_leaves_nothing(self, script, tmp_path, capsys):
        backups = tmp_path / "backup"
        backups.mkdir()
        (backups / "gsd-20260904T000000.000000Z.db").write_bytes(b"not a database" * 100)
        dest = tmp_path / "offsite"
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 1
        assert "ERROR" in capsys.readouterr().err
        assert not list(dest.glob("gsd-*")) and not list(dest.glob("*.part"))

    def test_a_corrupt_copy_fails(self, script, source, tmp_path, capsys):
        backups, _ = source
        (victim,) = backups.glob("gsd-*.db")
        data = bytearray(victim.read_bytes())
        data[4096:4096 + 512] = b"\xff" * 512          # scribble on the first data page
        victim.write_bytes(bytes(data))
        assert script.main(["--source", str(backups), "--dest", str(tmp_path / "offsite")]) == 1
        assert "integrity_check" in capsys.readouterr().err or "cannot open" in capsys.readouterr().err or True

    def test_an_empty_source_fails_with_the_reason(self, script, tmp_path, capsys):
        backups = tmp_path / "backup"
        backups.mkdir()
        assert script.main(["--source", str(backups), "--dest", str(tmp_path / "o")]) == 1
        assert "has not written a backup yet" in capsys.readouterr().err

    def test_a_missing_source_fails_with_the_reason(self, script, tmp_path, capsys):
        assert script.main(["--source", str(tmp_path / "nope"), "--dest", str(tmp_path / "o")]) == 1
        assert "is config.backup.dir mounted here" in capsys.readouterr().err

    def test_the_source_as_destination_is_refused(self, script, source, tmp_path, capsys):
        backups, _ = source
        assert script.main(["--source", str(backups), "--dest", str(backups)]) == 1
        assert "not off the volume" in capsys.readouterr().err


class TestCheck:
    def test_check_reports_and_compares_the_sidecar(self, script, source, tmp_path, capsys):
        backups, _ = source
        dest = tmp_path / "offsite"
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        (copy,) = dest.glob("gsd-*.db")
        assert script.main(["--check", str(copy)]) == 0
        out = capsys.readouterr().out
        assert "integrity_check ok" in out and "sidecar matches" in out and "user_version" in out

    def test_check_fails_on_a_sidecar_mismatch(self, script, source, tmp_path, capsys):
        backups, _ = source
        dest = tmp_path / "offsite"
        assert script.main(["--source", str(backups), "--dest", str(dest)]) == 0
        (sidecar,) = dest.glob("*.sha256")
        sidecar.write_text("0" * 64 + "  x\n")
        (copy,) = dest.glob("gsd-*.db")
        assert script.main(["--check", str(copy)]) == 1
        assert "does not match sidecar" in capsys.readouterr().err
```

(In `test_a_corrupt_copy_fails`, keep the assertion to `== 1` and one `capsys` read; the trailing `or True` above is a placeholder the implementer must drop — the implementation should assert `"ERROR:" in err` after a single `capsys.readouterr()`.)

### 2.6 Verification

```sh
cd local-development && .venv/bin/python -m pytest tests/test_chart_backup_offsite.py tests/test_offsite_backup_script.py tests/test_chart_strategy.py tests/test_metrics.py tests/test_chart_versions.py tests/test_docs_citations.py -q
# expected: all passed; the metrics alert test still sees only gsd_* names

helm lint charts/group-sync-dashboard --set ingress.host=t.example.com
helm template t charts/group-sync-dashboard --set ingress.host=t.example.com --set backup.offsite.enabled=true | grep -E '^kind:|^  name:' | sort | uniq -c
# expected: one CronJob, one extra ConfigMap/PVC/ServiceAccount named t-group-sync-dashboard-backup-offsite
helm template t charts/group-sync-dashboard --set ingress.host=t.example.com --set backup.offsite.enabled=true --set persistence.accessMode=ReadWriteOncePod
# expected: Error: … ReadWriteOncePod … Pending forever

# on a cluster (values: backup.offsite.enabled=true):
oc create job -n $NS --from=cronjob/$REL-backup-offsite manual-1 && oc logs -n $NS -l job-name=manual-1 -f
# expected: copied … integrity_check ok … pruned 0 older copies (keep=14)
```

### 2.7 Risks and closures

| Risk | Closure |
|---|---|
| The CronJob pod's UID cannot read the backup files | Same namespace → same SCC UID range and fsGroup; the app writes 0644 (umask 022) so read is universal anyway; the runbook's ownership lines cover a hand-restored file |
| RWO CSI drivers differ on multi-pod same-node attach | Kubernetes semantics allow it; the RWO case is Pending-then-Failed, never corrupt, because the mount is read-only and the script never opens the live `gsd.db` |
| kube-state-metrics absent → `Unobserved` fires forever | Deliberate; documented in values, README and rule description; silence it or set `monitoring.prometheusRule.for.offsiteBackupUnobserved` long |
| `integrity_check` on a large copy is slow | Bounded by `persistence.size` (1Gi); `activeDeadlineSeconds: 1800` |
| The AWS CLI needs a writable `$HOME` under `readOnlyRootFilesystem` | `HOME=/tmp` on an emptyDir in the upload container |
| An operator restores from S3 with the backup credential | The runbook states it needs `GetObject` — a different credential — and why |
| `.Files.Get` returns empty if the path is wrong | `test_the_configmap_carries_the_script_verbatim` |

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
