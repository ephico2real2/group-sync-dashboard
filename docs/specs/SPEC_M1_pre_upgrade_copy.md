# SPEC M1 — the pre-upgrade copy: the database as it was, copied and verified before a migration, or no start (#301)

| | |
|---|---|
| Programme | Epic B (#382), protect the data during upgrades. #305 (merged in `16c339e`) reads the schema version before anything writes; this attaches to that read. #298, the CI guard, is the epic's third child |
| Batch | M — schema migrations |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 0.37.0, chart 0.59.0 |
| Version note | §7's version blocks move the application from 0.36.0 to 0.37.0 and the chart from 0.58.3 to 0.59.0, the next minors on main `cbbc65a`, and move SPEC_S4c's reservation (specified, not begun) to 0.38.0 and 0.60.0, as #322 and #321 did. A release that lands first makes those blocks fail their check, because each Old text is the version it replaces; the implementing pull request then corrects them here before applying (`docs/specs/README.md`) |
| Issue | [#301](https://github.com/ephico2real2/group-sync-dashboard/issues/301) |
| Status | specified |
| Source | OB3's research and specification of 2026-09-26, written before any code from the issue, the epic (#382) and its decisions settled on 2026-09-26, and #305's merged code. Measured on main `cbbc65a` on this machine (Python 3.14.7 and SQLite 3.53.4, the versions the image carries) and read-only on the lab. §7's blocks were cut from a copy of `cbbc65a` with the design implemented, and proved against a clean copy (§4.3) |

## How to read this spec

§1 is the mandate. §2 is the research: each finding names its primary source and what was measured, with the
command's output. Line citations into the code at `cbbc65a` are written as plain text, file:line, to keep them
apart from the maintained `path#anchor` citations. §3 is the design, one decision per subsection, each with its
reason. §4 maps every Definition-of-Done item to a test and shows each test failing on a tree without the change.
§5 is the procedure on the lab for the implementing pull request. §6 is what an operator sees and what it costs.
§7 is the whole change as implementation blocks (`docs/specs/README.md`, "Implementation blocks"), applied to a
clean tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_M1_pre_upgrade_copy.md . --apply

This spec's own row in the index moves through the lifecycle by the orchestrator's hand, as T2's and L1's did; no
block touches it. A block found wrong during implementation is corrected here, with the reason under the
orchestrator's notes, before it is applied again.

## Orchestrator's notes

## 1. The mandate, and what is out of scope

The issue (#301, "The change"): take a copy of the database before `SCHEMA` and `_migrate` touch it, outside the
six-hourly `gsd-*.db` rotation, with a `.sha256` sidecar, a free-space check, and a refused start when the copy
cannot be written; decide where, the name, the order, retention, the failure, the offsite question, multi-replica
and backups disabled. Its Definition of Done asks for a test per behaviour: a database at N-1 opened by a build at
N writes the copy before migrating, and the copy reads N-1 with no table `SCHEMA` would have added; a copy that
cannot be written (unwritable directory, or free space below the database) refuses the start and leaves
`user_version` unchanged; a database at N writes nothing; a fresh file writes nothing; with the copy present,
`keep` six-hourly backups survive `backup()`; the offsite script's newest-by-name is unchanged. It must not change
the six-hourly backup's name, cadence, rotation or metric, the report snapshots and their `_STAMP`, the migrations,
the fresh-install path (no copy), or RBAC.

Out of scope, each owned elsewhere: the restore tool (#302), recovery mode (#303), the release note (#300), offsite
on by default and shipping this copy off the volume (#304, see §3.8), the KPI panel (#306), the CI guard (#298), and
a down-migration path, which `_migrate` does not have by design. Waiting for an off-volume copy before migrating is
decided no (§3.8), as the epic proposed.

## 2. Research, measured

The probes ran with the repository's venv (Python 3.14.7, SQLite 3.53.4, uvicorn 0.53.0) against copies of the
tree, each run printing the `gsd` it imported. The lab reads used `oc get`, `oc logs` and `oc exec` of `ls` and of
a `python3.14 -c` that reads `statvfs` and compile options, and nothing else. The lab pod reports the same two
versions: `sqlite 3.53.4 python 3.14.7`.

### 2.1 `VACUUM INTO` at the point #305 left

**Source.** SQLite, "VACUUM" (sqlite.org/lang_vacuum.html, last updated 2025-07-12): "The VACUUM INTO command is
transactional in the sense that the generated output database is a consistent snapshot of the original database";
"The file named by the INTO clause must not previously exist, or else it must be an empty file, or the VACUUM INTO
command will fail with an error"; "A VACUUM will fail if there is an open transaction on the database connection
that is attempting to run the VACUUM"; and "if the PRAGMA synchronous setting of the original database is NORMAL
or FULL, then SQLite invokes fsync() or FileFlushBuffers() to sync the output database to disk after it has been
written". That last behaviour arrived in 3.40.0 (release log item 8, 2022-11-16: "Enhance the VACUUM INTO statement
so that it honors the PRAGMA synchronous setting"; check-in 86cb21ca12 of 2022-10-24). Python 3.14, `sqlite3`: under
`LEGACY_TRANSACTION_CONTROL`, the default, a transaction is implicitly opened only when "sql is an `INSERT`,
`UPDATE`, `DELETE`, or `REPLACE` statement"; `executescript` commits a pending transaction first and "No other
implicit transaction control is performed"; and `connect`'s `timeout` ("Default five seconds") is how long a
connection waits on a lock, which the attach point reads back as `PRAGMA busy_timeout` 5000.

**The attach point.** `Store.__init__` (local-development/gsd/store.py:1283-1293 at `cbbc65a`) connects, runs
`_harden`, reads `_schema_state`, and refuses a newer database, all before `PRAGMA journal_mode=WAL` (:1304-1306),
`busy_timeout` (:1316), `synchronous` (:1321), `executescript(SCHEMA)` (:1323), `_migrate` (:1324) and the seeds
(:1325). Measured there (probe 1a), on a WAL database whose writer was killed with SIGKILL after committing one row
to a 24,752-byte `-wal`:

```text
state (19, False) in_transaction False busy_timeout 5000 synchronous 2 journal_mode (read, not set) wal
VACUUM INTO ok in 0.006 s; copy bytes 2740224; header(write,read)=(1, 1); copy user_version 19; integrity ok; row committed only in the WAL present: True; tables 36
files beside the copy after the check: ['copy.db.tmp', 'gsd.db', 'gsd.db-shm', 'gsd.db-wal']
source user_version still 19 after VACUUM INTO
```

The copy holds what only the `-wal` held, and its header bytes 18 and 19 are 1 and 1: a rollback-journal file, not
WAL, so opening it `immutable=1&mode=ro` created no `-wal` or `-shm` beside it (the repository's report reader
relies on the same fact, `local-development/gsd/reporting/snapshot.py#Snapshot`).

**Locks** (probe 1b). With another connection holding `BEGIN IMMEDIATE` and an uncommitted `INSERT`, `VACUUM INTO`
succeeded in WAL mode and in rollback mode, 0.004 s each, and did not copy the uncommitted row. Only an `EXCLUSIVE`
lock, a rollback-mode writer committing, stopped it: `OperationalError: database is locked (SQLITE_BUSY)` after the
busy timeout, with no target file left. The copy is a read; it takes no write lock.

**The image.** In the lab pod, `PRAGMA compile_options` on an in-memory database lists `DEFAULT_SYNCHRONOUS=2`,
`DEFAULT_WAL_SYNCHRONOUS=2`, `DEFAULT_WAL_AUTOCHECKPOINT=1000`, `DISABLE_DIRSYNC` and `TEMP_STORE=1`; this machine's
build lists the same without `DISABLE_DIRSYNC`. SQLite's compile options: the default `synchronous` "is 2 (FULL)"
unless overridden, and with `SQLITE_DISABLE_DIRSYNC` "directory syncs are disabled". At the attach point
`synchronous` is therefore FULL (2, measured here on the same SQLite version with the same two defaults), SQLite
syncs the copy itself, and the image's SQLite syncs no directory.

**Cost** (probe 1d). Databases built by the real `Store`, filled with `membership_event` rows, at the lab's size
(its `gsd.db` is 9,822,208 bytes with a 4,223,032-byte `-wal`, from `ls -la /data`) and at 10 and 100 times it:

| logical size | `VACUUM INTO` | `user_version` + `integrity_check` | sha256 + fsync | directory fsync | total |
|---|---|---|---|---|---|
| 10,641,408 (lab) | 0.023 s | 0.091 s | 0.004 s | < 0.0001 s | 0.117 s |
| 98,263,040 (10×) | 0.231 s | 1.427 s | 0.030 s | < 0.0001 s | 1.689 s |
| 982,839,296 (100×) | 4.963 s | 19.866 s | 0.282 s | 0.0001 s | 25.111 s |

`integrity_check` dominates and grows faster than the file: on the 10× file `PRAGMA quick_check` took 0.077 s
against `integrity_check`'s 1.591 s (probe `full`).

**Failures** (probe 1c and probe `full`). An unwritable or missing target directory: `OperationalError: unable to open
database: <path>`, `SQLITE_CANTOPEN` (14). A full volume, simulated with a 3 MB HFS+ image attached with `hdiutil`
(`df` 2,892 KB available): `OperationalError: database or disk is full`, `SQLITE_FULL` (13), after 0.008 s, leaving
a partial 2,957,312-byte target that had consumed all the free space (`free now 0`) until it was removed. An existing
database as the target: `output file already exists`. A 1-byte or empty file as the target is overwritten without
error. After every failure the source still read `user_version` 19 and the connection held no transaction.

What this settles: the copy can be taken on the connection #305 left, before the WAL switch; it needs no write lock;
a failed copy must delete its own partial file, or it keeps the space it failed for.

### 2.2 The space a copy needs

**Source.** Python, `shutil.disk_usage`: the installed 3.14.7 implements it as `os.statvfs(path)` with
`free = st.f_bavail * st.f_frsize` (read with `inspect.getsource`). `f_bavail` is the space an unprivileged process
may use; the dashboard runs as UID 1000790000 (measured in the pod). The fragment size, not the block size, is the
unit: on the 3 MB HFS+ volume `f_bsize` was 2,097,152 and `f_frsize` 4,096, so `f_bavail × f_bsize` would have
overstated the free space 512 times.

**The file size is not a bound** (probe 2). The `VACUUM INTO` output against four predictors, in bytes:

| shape | file | `-wal` | `page_count × page_size` | output |
|---|---|---|---|---|
| fresh, checkpointed | 4,562,944 | 0 | 4,562,944 | 4,292,608 |
| half the rows deleted | 4,567,040 | 0 | 4,567,040 | 2,347,008 |
| growth still in the `-wal` (writer killed) | 1,224,704 | 82,713,152 | 13,225,984 | 12,517,376 |
| random keys, fragmented indexes | 17,620,992 | 0 | 17,620,992 | 16,605,184 |

With the growth still in the `-wal` the main file is a tenth of the copy, and the file plus the `-wal` overstates it
6.7 times. `PRAGMA page_count × page_size`, read through the connection, counts what the `-wal` holds and bounded
the output in all four shapes; SQLite's page calls the output "minimal in size". A shape where the output exceeds it
was not found, and a copy that runs out of space still fails with `SQLITE_FULL` and is removed.

**The lab.** In the dashboard pod, `shutil.disk_usage('/data')` returned `total=160456224768, used=107837399040,
free=52618825728` (`f_frsize` 4096, `f_bavail` = `f_bfree` = 12,846,393), while the claim reports `119Gi` on
`crc-csi-hostpath-provisioner`: the statvfs total is the node's filesystem, not the claim's size. On that
provisioner the check measures the node's disk; on a block volume it measures the volume. A quota-enforcing
provisioner was not measured.

### 2.3 A refused start: what uvicorn, Kubernetes and Argo CD show, and how long the copy may take

**uvicorn.** The image runs `python3.14 -m uvicorn gsd.api:create_app --factory` (`local-development/Containerfile`,
and `charts/group-sync-dashboard/templates/deployment.yaml#- gsd.api:create_app` with the proxy on), and
`create_app` calls `build_app`, which constructs the store through `open_backend` before the port is bound
(`local-development/gsd/api.py#create_app`, `local-development/gsd/storage.py#open_backend`). A factory that raises a
named exception, run with the venv's uvicorn 0.53.0, exited 1 and printed a traceback whose last line is the
exception and its message:

```text
exit code: 1
refusing.StorePreUpgradeCopyFailed: schema 19 -> 20: the pre-upgrade copy was not written (probe)
```

That is how #305's refusal reaches `oc logs --previous --tail=1` (`docs/RUNBOOK_backup_restore.md#4c. Bring it back and verify`).

**Kubernetes** (kubernetes/website at `a746bbd`, 2026-09-26). Pod lifecycle: "After containers in a Pod exit, the
kubelet restarts them with an exponential backoff delay (10s, 20s, 40s, …), that is capped at 300 seconds (5
minutes). Once a container has executed for 10 minutes without any problems, the kubelet resets the restart backoff
timer for that container"; `CrashLoopBackOff` "indicates that the backoff delay mechanism is currently in effect".
Probes: `initialDelaySeconds` is the "Number of seconds after the container has started before startup, liveness or
readiness probes are initiated"; "After a probe fails `failureThreshold` times in a row … For the case of a startup
or liveness probe … Kubernetes treats the container as unhealthy and triggers a restart"; a readiness failure only
sets the Pod's `Ready` condition false. The chart has no startup probe; its liveness probe is
`initialDelaySeconds: 10`, `periodSeconds: 300`, `failureThreshold: 2` (`charts/group-sync-dashboard/values.yaml#failureThreshold: 2`),
and the lab's Deployment carries exactly that (read with `oc get deploy -o jsonpath`). A container that never binds
its port is killed at the second failed probe: no earlier than 10 + (2 − 1) × 300 = 310 s after it starts, and by
the documentation's own reckoning (initialDelaySeconds + failureThreshold × periodSeconds) about 610 s. Not measured
on the lab. Against §2.1's 0.117 s at the lab's size and 25 s at 100 times it, the budget holds by more than twelve
times; since `integrity_check` grows faster than the file, a database near a thousand times the lab's would approach
it (extrapolated, not measured).

**The Deployment.** `progressDeadlineSeconds` defaults to 600, after which the controller records
`reason: ProgressDeadlineExceeded` and "will keep retrying". The lab's is 600, with `Recreate`, one replica and
`terminationGracePeriodSeconds: 30`. `Recreate`: "All existing Pods are killed before new ones are created … If you
manually delete a Pod … the replacement will be created immediately (even if the old Pod is still in a Terminating
state)". So at one replica an upgrade never has two pods on the file.

**Argo CD.** "The health of a resource is not inherited from child resources", and "The App health will be the worst
health of its immediate child resources" (operator manual, health). A Deployment is Progressing ("Waiting for rollout
to finish: …") until its progress deadline, then Degraded ("Deployment %q exceeded its progress deadline")
(`gitops-engine`, `pkg/health/health_deployment.go`). A start refused during an upgrade, which is a rollout, therefore reads
Progressing for 600 s and Degraded after, with the pod in `CrashLoopBackOff` and the reason in its previous container's last log line. The
lab's three Applications read `Synced Healthy` now (`oc get applications.argoproj.io -A`).

### 2.4 Every reader of `gsd-*.db`

| reader | where it looks | how |
|---|---|---|
| the six-hourly rotation, `Store._vacuum_into` (store.py:1640-1641) | `config.backup.dir`; `/data/report` for snapshots | `sorted(target_dir.glob("gsd-*.db"))`, all but the last `keep` deleted |
| the offsite script (`charts/group-sync-dashboard/scripts/offsite_backup.py#newest_backup`, `#prune`) | `--source`, which the CronJob sets to `config.backup.dir`; its destination | `PATTERN = "gsd-*.db"`, newest by name; destination pruned by the same pattern |
| `gsd_backup_last_success_timestamp_seconds` (metrics.py:789) | `config.backup.dir` | `glob("gsd-*.db")`, newest mtime |
| the KPI size line (`local-development/gsd/kpi/system.py#dashboard_data_bytes`) | `config.backup.dir` | `glob("gsd-*.db")`, count and bytes |
| the report service (`local-development/gsd/reporting/snapshot.py#_STAMP`, `#newest_snapshot`) | `/data/report` | `iterdir()`, `^gsd-(\d{8}T\d{6}\.\d{6}Z)\.db$` |

Every one is non-recursive (`Path.glob` without `**`, `iterdir`). Measured on `cbbc65a` (probe `readers`), the
issue's regression reproduces: with two `gsd-preupgrade-19-to-20-…` files in the backup directory,
`store.backup(dir, keep=2)` returned `gsd-20260926T210420.861130Z.db`, which no longer existed after its own
rotation, and the offsite script's `newest_backup` picked `gsd-preupgrade-19-to-20-20260926T150001.000000Z.db`. The
name chosen in §3.2 is seen by none of the globs in three layouts (beside the backup directory, inside it, and as the
backup directory itself), and `_STAMP` does not match it:

```text
chosen name, sibling directory (chart layout): gsd-*.db glob of the backup dir sees it: False; _STAMP matches it: False
chosen name, inside backupDir: gsd-*.db glob of the backup dir sees it: False; _STAMP matches it: False
chosen name, backupDir itself: gsd-*.db glob of the backup dir sees it: False; _STAMP matches it: False
```

### 2.5 Replicas, backups off, and who owns the directory

**Replicas.** `GSD_DB_PATH` is `/data/gsd.db` at one replica and `/data/$(POD_NAME)/gsd.db` above one
(`charts/group-sync-dashboard/templates/deployment.yaml#value: /data/$(POD_NAME)/gsd.db`), with `POD_NAME` from
`metadata.name`. A Deployment's pods are named by `generateName`: the apiserver cuts the base to 58 characters and
appends five random ones (`staging/src/k8s.io/apiserver/pkg/storage/names/generate.go` at kubernetes `dfd7b93`), and
"when a Pod is created, its hostname (as observed from within the Pod) is the Pod's `metadata.name` value" (DNS for
Services and Pods). On the lab, `socket.gethostname()` and `POD_NAME` both read
`group-sync-dashboard-d568cf97b-88dxh`, and the pod's first leader-election line names the one before it,
`group-sync-dashboard-58bf7b9cb7-pgwcw`. So above one replica every new pod opens a new, empty file and an upgrade
takes no copy; a container restart keeps both the pod's file and its name.

**Backups off.** `backupDir` is one value for every replica and is left out of the ConfigMap when
`config.backup.enabled=false` (`charts/group-sync-dashboard/templates/configmap.yaml#backupDir: {{ .Values.config.backup.dir | quote }}`),
which the app reads as backups disabled (`local-development/gsd/poller.py#Poller._maybe_backup`); the offsite
CronJob refuses to render then (`charts/group-sync-dashboard/templates/backup-offsite.yaml#requires config.backup.enabled=true`).

**Ownership.** The pod runs as UID 1000790000, GID 0, groups `[0, 1000790000]`, umask 022 (measured in the pod);
its `fsGroup` is 1000790000 (SCC `restricted-v2`, no `fsGroupChangePolicy`), and the data volume's CSI driver,
`kubevirt.io.hostpath-provisioner`, has `fsGroupPolicy: File`. "By default, Kubernetes recursively changes
ownership and permissions for the contents of each volume to match the `fsGroup` specified in a Pod's
`securityContext` when that volume is mounted" (Configure a Security Context). On the lab every file older than
the running pod is group-writable (0664; `/data/backup` is 2775) and the three it wrote since are 0644, which fits
that; the modes alone do not prove it, since an older image may have had another umask. A `pre-upgrade/` directory
made by one pod is writable by the next the same way `/data/backup` is; nothing here sets a mode, as
`_vacuum_into` sets none. A driver without `fsGroup` support was not measured.

### 2.6 What a failed attempt leaves behind

`executescript(SCHEMA)` runs `CREATE … IF NOT EXISTS` statements outside any transaction, and a migration made only
of `ALTER TABLE` statements commits each one and its `PRAGMA user_version` as it goes (§2.1's Python source:
implicit transactions open only before `INSERT`, `UPDATE`, `DELETE` or `REPLACE`). Measured on `cbbc65a` (probe `crashloop`): a database shaped like schema 18
(migration 19's two columns and `SCHEMA`'s `kyverno_result_event` absent), opened by this build with migration 20
replaced by a failing statement:

```text
KNOWN 20 before any attempt: {'user_version': 18, 'SCHEMA table kyverno_result_event': False, 'migration 19 column cluster.source': False}
attempt 1: OperationalError: no such table: no_such_table; the database now: {'user_version': 19, 'SCHEMA table kyverno_result_event': True, 'migration 19 column cluster.source': True}
attempt 2: OperationalError: no such table: no_such_table; the database now: {'user_version': 19, 'SCHEMA table kyverno_result_event': True, 'migration 19 column cluster.source': True}
```

The second attempt finds schema 19 with this build's tables, not the database schema 18's image wrote, and #305
makes that image refuse schema 19. A rule that copied at every start below the build's version and kept the newest
N would, in a crash loop (10 s, 20 s, 40 s …), write N copies of that within about a minute and prune the clean one.

## 3. The design

### 3.1 Where: `pre-upgrade/` beside the database

`Path(db_path).parent / "pre-upgrade"`: `/data/pre-upgrade/` at one replica, `/data/<pod>/pre-upgrade/` above one.
One rule for every layout; each replica has its own (§2.5), so two cannot collide; it is written whether backups are
on or off (the epic's decision of 2026-09-26: "written even with backups off"); and it needs no setting and no new
argument, so `open_backend` is unchanged. No reader of `gsd-*.db` looks there (§2.4).

### 3.2 The name and the sidecar

`pre-upgrade-<UTC stamp>-schema-<from>-to-<to>-<pod>.db`, for example
`pre-upgrade-20260926T143437.649774Z-schema-19-to-20-group-sync-dashboard-d568cf97b-88dxh.db`, and beside it
`<name>.sha256` holding `<sha256 hex>  <name>` and a newline.

- **Not `gsd-*.db`.** The issue's `gsd-preupgrade-…` is the name its measured regression came from (§2.4). The
  directory alone keeps today's readers away; the name keeps the copy out of their pattern even if
  `config.backup.dir` were pointed at this directory, and out of the offsite destination's own rotation if #304 ships
  it there.
- **The stamp first.** Name order is then time order, the rule every reader here sorts by. With the issue's
  `<from>-to-<to>-<stamp>` a copy from schema 9 sorts after one from 19, and a copy taken after a restore to an older
  schema sorts before the copies it is newer than, so pruning by name would remove the newest.
- **The stamp of `Store._vacuum_into`** (`%Y%m%dT%H%M%S.%fZ`, UTC, microseconds), so two copies never share a name.
- **`schema-`**, so the numbers read as schemas, not application versions (the distinction #302 draws).
- **`<pod>`**: `POD_NAME`, else the hostname, the identity the leader election already takes
  (`local-development/gsd/leader.py#LeaderElector`), for §3.6.
- **The sidecar is the offsite script's format** (`charts/group-sync-dashboard/scripts/offsite_backup.py#write_sidecar_part`),
  so `sha256sum -c` and that script's `--check` verify a copy wherever it travels.

### 3.3 The order

1. `_schema_state` (#305, unchanged). Newer than the build: #305 refuses. Fresh, or equal to the build's version:
   no copy, and the open continues exactly as today.
2. Older and not fresh: `_pre_upgrade_copy`, then the open continues exactly as today: the WAL switch,
   `busy_timeout`, `synchronous`, `foreign_keys`, `SCHEMA`, `_migrate`, the seeds, the commit. The copy comes before
   the WAL switch too, because the switch rewrites the header (#305's reason for its own placement).
3. Inside `_pre_upgrade_copy`: the once-per-pod check (§3.6); make the directory; delete what a killed attempt left
   (`*.db.tmp`, and a sidecar whose copy is gone); the space check (§3.4); `VACUUM INTO <name>.tmp`; open it
   `immutable=1&mode=ro` and require `user_version` equal to `<from>` and `integrity_check` `ok`; hash it and
   `fsync` it; write the sidecar and `fsync` it; rename the copy into place; `fsync` the directory; log; prune (§3.5).

The copy's name appears only after its sidecar exists, as in the offsite script. The syncs are there because the
migration that follows is the event the copy exists for: SQLite syncs the `VACUUM INTO` output itself at `synchronous`
FULL (§2.1), but the image's build has `DISABLE_DIRSYNC` and nothing else syncs the rename, and the explicit `fsync`
of the copy keeps the guarantee on a build older than 3.40.0. Their cost at the lab's size is in §2.1's table.

### 3.4 The space check

`PRAGMA page_count × page_size`, read on the same connection, against `shutil.disk_usage(<directory>).free`; below
it, refuse with both in MiB (`free space 40.0 MiB, database 120.0 MiB`). §2.2 is the reason for both halves. It
covers the copy, not the migration's own growth: a migration that fills the volume fails as it does today, and the
retry does not copy again (§3.6).

### 3.5 Retention

The newest three (`PRE_UPGRADE_KEEP = 3`) by name, pruned only right after a new copy has been written and renamed,
each copy's sidecar with it. `config.backup.keep`, the six-hourly job and the offsite script never touch them (§2.4).
The bound: three copies at rest and four for the moment a fourth has been written, each about the size of the
database (about 9 MB on the lab today, where the newest backup, the same `VACUUM INTO`, is 8,843,264 bytes), on
the data claim, so they count against `persistence.size` (1Gi by default). Three is the last three schema-moving
upgrades, and a spare for the replacement pod a failed upgrade may get (§3.6). A constant, not a setting: nothing in the issue asks to tune it, and a new key is three edits and a
render guard.

### 3.6 Once per upgrade per pod

When the directory already holds a copy for this build's target written by this pod (a name ending
`-to-<target>-<pod>.db`), the start does not copy again and says so at INFO. §2.6 is the reason. The pod's name,
`POD_NAME` as the chart sets it from `metadata.name` or else the hostname, which in a pod is the same name (§2.5), is
the same across its container's restarts and new for every pod. A crash loop keeps the clean
copy and adds none; a new pod — a rollout, a deleted pod — takes a fresh copy of whatever the database is by then, so
a rollback that ran the older image for days before the upgrade was retried is copied again. The mutation M6 in §4.2
removes this rule and the test for it goes red.

### 3.7 The failure

`Store.__init__` closes its connection and raises `StorePreUpgradeCopyFailed`, a named exception beside #305's
`StoreSchemaTooNew`, from inside `create_app`: the container exits 1 before it binds its port (§2.3). The message
names the move, the database, the directory, the reason and the ways out:

    schema 19 -> 20: the pre-upgrade copy of /data/gsd.db could not be written to /data/pre-upgrade, so the database
    was not migrated: free space 40.0 MiB, database 120.0 MiB. Free space on the volume or make the directory
    writable, then restart; or deploy the image that understands schema 19 (docs/RUNBOOK_backup_restore.md §6)

A refused attempt deletes its `.tmp`, its sidecar and its copy (§2.1: a partial file keeps the space it failed for).
The database is not migrated. As with #305, closing the refusing connection may fold a committed `-wal` into the
main file; the bytes change, the content does not. On success, one INFO line before the first
`schema migration N applied`:

    pre-upgrade copy written before migrating schema 19 -> 20: /data/pre-upgrade/pre-upgrade-….db (9973760 bytes, 0.12 s)

### 3.8 The offsite question

**The migration does not wait for an off-volume copy.** That would tie the start to a CronJob that exists only with
`backup.offsite.enabled`, to a second claim, and to a schedule; the epic proposed no and this confirms it.

**Shipping the newest pre-upgrade copy off the volume belongs to #304, not here.** #301's Definition of Done holds
the offsite script's newest-by-name unchanged, and a test here pins it. It is also not a one-line change of source:
the script's pattern is `gsd-*.db`, the copies are `pre-upgrade-*.db` in another directory, and its destination is
pruned to `--keep` by that same pattern (`charts/group-sync-dashboard/scripts/offsite_backup.py#prune`), so shipping
them needs a source, a pattern and a destination rule of their own; and #304 is already changing that script's defaults
and its tests. The recommendation for #304: a second pass with `--source <directory of GSD_DB_PATH>/pre-upgrade` and the
`pre-upgrade-*.db` pattern, into its own destination directory, at one replica only.

### 3.9 Multi-replica

Nothing beyond §3.1: each pod copies its own file into its own directory. In practice a pod above one replica
starts on a new file and takes no copy (§2.5).

### 3.10 Backups disabled

The copy is written; nothing else changes (§3.1).

### 3.11 Versions

Application 0.37.0 and chart 0.59.0, both MINOR: a new directory on the data volume and a new way for a start to be
refused. The chart moves because `appVersion` moves, and the values comment and README it publishes describe what the
image it deploys does (`docs/RELEASING.md`: a chart change forced by an app change moves both in the same PR). #305,
under Unreleased with no version of its own, ships in the same application release. SPEC_S4c's reservation moves to
0.38.0 and 0.60.0.

### 3.12 What does not change

The six-hourly backup's name, cadence, rotation and metric; the offsite script; `/data/report` and `_STAMP`; the
migrations; the fresh path; #305's refusal and its text; the chart's templates and every rendered RBAC rule (§4.3).

## 4. Tests

### 4.1 One test per Definition-of-Done item

All in `local-development/tests/test_pre_upgrade_copy.py` (§7, block 5):

| Definition of Done | test |
|---|---|
| N-1 opened by N writes the copy before migrating; the copy reads N-1 with no table `SCHEMA` would add | `test_an_older_database_is_copied_before_schema_and_migrations_touch_it` (also the sidecar's content and the log order) |
| an unwritable directory, or free space below the database, refuses the start; `user_version` unchanged | `test_a_copy_that_cannot_be_written_refuses_the_start`, four cases: unwritable directory, free space below the database, free space for the file but not its `-wal`, and the rename failing after the copy and sidecar exist |
| a database already at N writes nothing | `test_a_database_at_the_build_version_writes_nothing` |
| a fresh file writes nothing | `test_a_fresh_file_writes_nothing` |
| with the copy present, `keep` six-hourly backups survive `backup()` | `test_the_six_hourly_backups_do_not_see_the_copy`, two layouts: the chart's, and `config.backup.dir` pointed at the copies (also the metric, the KPI size line and `_STAMP`) |
| the offsite script's newest-by-name is unchanged | the same test: `newest_backup` returns the newest ordinary backup in both layouts |
| (§3.6) a restarted container does not copy again; a new pod does | `test_a_restarted_container_does_not_copy_again` |
| (§3.5) the newest three are kept; a killed attempt's files go | `test_the_newest_copies_are_kept_and_a_killed_attempt_leaves_nothing` |
| (§3.10, §2.3) backups off still copies; the app does not start without the copy | `test_the_app_copies_with_backups_off_and_does_not_start_without_the_copy` |

### 4.2 Each test fails without the change

The mutation harness (§4.4) runs the module against main's `gsd` and against eleven mutations of the implemented
`store.py`, each package first on the path and the imported `gsd` printed:

| run | the change to `store.py` | result | tests that go red |
|---|---|---|---|
| M0 | none: main `cbbc65a` | 1 error, at collection | all twelve: the module imports names this change adds |
| — | the change as §7 writes it | 12 passed | none |
| M1 | the copy is never taken | 10 failed, 2 passed | all but the two that must see nothing written |
| M2 | a database at the build's version is copied (`<=`) | 1 failed | `test_a_database_at_the_build_version_writes_nothing` |
| M3 | a fresh file is copied (no `not fresh`) | 9 failed | `test_a_fresh_file_writes_nothing`, the equal-version test, and seven whose setup opens a fresh file |
| M4 | the copy is taken after `SCHEMA` | 6 failed | the copy test (`SCHEMA`'s table is in the copy), the four refusal cases (`SCHEMA` ran before the refusal), the restart test |
| M5 | free space is checked against the file's size | 1 failed | `test_a_copy_that_cannot_be_written_refuses_the_start[free space for the file but not its WAL]` |
| M6 | no once-per-pod rule | 1 failed | `test_a_restarted_container_does_not_copy_again` |
| M7 | the name starts `gsd-preupgrade-` | 4 failed | `test_the_six_hourly_backups_do_not_see_the_copy[backup.dir set to the copies]` and three that assert the name |
| M8 | no pruning | 1 failed | `test_the_newest_copies_are_kept_and_a_killed_attempt_leaves_nothing` |
| M9 | a killed attempt's `.tmp` stays | 1 failed | the same |
| M10 | a sidecar without its copy stays | 1 failed | the same |
| M11 | a refused attempt leaves its files | 1 failed | `test_a_copy_that_cannot_be_written_refuses_the_start[the rename fails]` |

On main every test errors at collection (the module imports names this change adds). The two tests that must see
nothing written pass under M1 by construction; M2 and M3 are what they are for.

### 4.3 The proof

§7 was not written by hand. The design was implemented in a copy of `cbbc65a`; the generator cut each block's Old
text from main and its New text from that copy, at whole lines, and checked that each file's blocks, applied in order
to main's file, give the implemented file byte for byte: `17 blocks across 11 files reproduce the prototype byte for
byte`. Then, on a clean clone of this spec's own commit:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_M1_pre_upgrade_copy.md .
    17 blocks check out across 11 files
    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_M1_pre_upgrade_copy.md . --apply

After `--apply` every changed file is identical (`cmp`) to the implemented copy, except `docs/specs/README.md`, which
also carries this spec's own index row. On that applied tree, with `PYTHONPATH` at its `local-development` and
`gsd.__version__` reading `0.37.0`:

| check | command | result |
|---|---|---|
| hermetic suite | `pytest tests/ -q -p no:cacheprovider --deselect tests/test_ui.py --deselect tests/test_live_smoke.py` | `5236 passed, 19 skipped, 608 deselected` |
| browser suite | `pytest tests/test_ui.py -q -p no:cacheprovider --browser chromium` | `604 passed` |
| this spec's commit alone | the same hermetic run on a clean clone of the commit, before `--apply` | `5223 passed, 19 skipped, 608 deselected` |
| markdown | `markdownlint-cli2` on the runbook, the CHANGELOG, the specs index and the chart README | 15 findings before and after, all of them already on main (MD040, MD004, MD012); none new |
| chart | `helm lint`; `helm template` of main and of the applied chart, diffed | lint clean; the only rendered differences are the chart and app version labels on 34 objects, the two image tags (0.36.0 to 0.37.0) and the config checksum |
| RBAC | every rendered Role, ClusterRole and binding, rule by rule | 70 before, 70 after; REMOVED 0, ADDED 0 |
| Python 3.11 | `ast.parse(source, feature_version=(3, 11))` on `store.py` and the test module | both parse; CI's 3.11 job was not run here |

### 4.4 The probes

The probes ran in a scratch copy and are not committed. The two that decided the design are here as they ran, with
`PYTHONPATH` at a copy of `cbbc65a`'s `local-development`; the others are described well enough to repeat: 1a and
1b open a database the way `Store.__init__` does up to `_schema_state` and run `VACUUM INTO` (1b with a second
connection holding `BEGIN IMMEDIATE` or `BEGIN EXCLUSIVE`); 1c and `full` point it at a `0555` directory, a missing
one, a 3 MB HFS+ image (`hdiutil create -size 3m -fs HFS+`, attached `-nobrowse`) and existing targets; 1d and 2
fill databases through `Store` with `membership_event` rows and time or size each step; the mutation harness
copies the implemented `gsd` package once per row of §4.2, applies that row's replacement to `store.py`, and runs
the test module with the copy as the working directory, because `python -m pytest` puts the working directory
ahead of `PYTHONPATH`.

probe_crashloop.py (§2.6):

```text
"""#301 research: what a FAILED upgrade attempt leaves in the database on the current code (main cbbc65a).

A database shaped like schema 18 (migration 19's columns absent, a SCHEMA table absent) is opened by this build
with migration 20 replaced by one that fails. Printed: the user_version the failed attempt left, and whether
SCHEMA's table and migration 19's columns were committed before the failure. argv: <work dir>."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import gsd.store as store
from gsd.store import KNOWN_SCHEMA_VERSION, Store

work = Path(sys.argv[1])
work.mkdir(parents=True, exist_ok=True)
db = work / "gsd.db"
Store(str(db)).close()
c = sqlite3.connect(db)
c.execute("ALTER TABLE cluster DROP COLUMN source")
c.execute("ALTER TABLE cluster DROP COLUMN credential")
c.execute("DROP TABLE kyverno_result_event")
c.execute("PRAGMA user_version = 18")
c.commit()
c.close()


def state() -> dict:
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try:
        return {"user_version": c.execute("PRAGMA user_version").fetchone()[0],
                "SCHEMA table kyverno_result_event": c.execute(
                    "SELECT COUNT(*) FROM sqlite_master WHERE name='kyverno_result_event'").fetchone()[0] == 1,
                "migration 19 column cluster.source": "source" in {r[1] for r in c.execute("PRAGMA table_info(cluster)")}}
    finally:
        c.close()


print("KNOWN", KNOWN_SCHEMA_VERSION, "before any attempt:", state())
real = store._MIGRATIONS
store._MIGRATIONS = [m for m in real if m[0] != 20] + [(20, "fails on purpose", ["INSERT INTO no_such_table VALUES (1)"])]
for attempt in (1, 2):
    try:
        Store(str(db))
        print(f"attempt {attempt}: opened?!")
    except sqlite3.Error as exc:
        print(f"attempt {attempt}: {type(exc).__name__}: {exc}; the database now:", state())
store._MIGRATIONS = real
```

probe_readers.py (§2.4; its second argument is the chart's `scripts/offsite_backup.py`):

```text
"""#301 research item 4: the issue's measured regression, re-run on main's Store.backup, and the name/directory
the spec chooses against every reader of gsd-*.db. argv: <work dir> <path to offsite_backup.py>."""
import importlib.util, sys
from pathlib import Path
from gsd.store import Store
from gsd.reporting.snapshot import _STAMP

work, script = Path(sys.argv[1]), Path(sys.argv[2])
spec = importlib.util.spec_from_file_location("offsite_backup", script); offsite = importlib.util.module_from_spec(spec); spec.loader.exec_module(offsite)
store = Store(str(work / "gsd.db"))
backups = work / "backup"; backups.mkdir(parents=True)
for name in ("gsd-preupgrade-19-to-20-20260926T150000.000000Z.db", "gsd-preupgrade-19-to-20-20260926T150001.000000Z.db"):
    (backups / name).write_bytes(b"pre-upgrade copy under the issue's proposed name")
written = store.backup(str(backups), keep=2)
print("issue's name in backupDir: backup(keep=2) returned", Path(written).name, "- exists after rotation:", Path(written).exists())
print("  offsite newest_backup ->", offsite.newest_backup(backups).name)
chosen = "pre-upgrade-20260926T150000.000000Z-schema-19-to-20-group-sync-dashboard-d568cf97b-88dxh.db"
for label, d in (("sibling directory (chart layout)", work / "pre-upgrade"), ("inside backupDir", backups / "pre-upgrade"), ("backupDir itself", work / "b2")):
    d.mkdir(parents=True, exist_ok=True); (d / chosen).write_bytes(b"copy")
    target = backups if d.parent == backups or d == work / "pre-upgrade" else d
    seen = sorted(p.name for p in target.glob("gsd-*.db"))
    print(f"chosen name, {label}: gsd-*.db glob of the backup dir sees it: {chosen in seen}; _STAMP matches it: {bool(_STAMP.match(chosen))}")
store.close()
```

## 5. On the lab (the implementing pull request)

Not run in this phase: the lab is read-only here. The issue's own check needs a real copy on `/data`, and this change
adds no migration, so a start of its image on the lab meets a database at the image's version and copies nothing.
The procedure, for the orchestrator to confirm, deployed with `release-crc.sh`:

1. Record the UIDs of `group-sync-dashboard-data` and `group-sync-dashboard-report-artifacts`.
2. **One migration more.** Deploy a lab-only image of the branch with one no-op migration added,
   `(21, "no-op for the #301 lab check", ["SELECT 1"])`. Its start must log
   `pre-upgrade copy written before migrating schema 20 -> 21: /data/pre-upgrade/…` before
   `schema migration 21 applied`; the copy must verify against its sidecar (§6 of the runbook, "Using a copy") and
   read `user_version` 20.
3. **Restarts.** Five restarts (`oc delete pod`), each at schema 21: no new copy, the copy still in
   `/data/pre-upgrade`, and `ls /data/backup` still four `gsd-*.db`.
4. **Back.** The branch's real image understands 20 and refuses the database at 21 (#305), which is the rollback this
   copy exists for: scale to zero (with Argo CD's auto-sync paused), restore the copy with runbook §4a from `/data/pre-upgrade/<file>`, deploy the
   real image, and it opens at 20 with no copy and no migration. What the lab image wrote in between is lost, as a
   rollback loses it.
5. The UIDs again: unchanged.

A throwaway pod opening a copy of `gsd.db` set to `user_version` 19, as #305's lab check did, shows step 2's log
order without touching `/data`, but not steps 3 and 4. Rewinding the live `user_version` is not safe: migration 20
would replay on a populated table, its `INSERT OR IGNORE … SELECT … 'Group', '', 0` would re-label every
ServiceAccount and User row as a Group subject and drop the rows that then collide, and the next binding refresh
would record the difference as binding events, which are history.

## 6. What an operator sees, and what it costs

- At an upgrade across a migration, one line before the migration lines, and a directory `pre-upgrade/` beside the
  database holding up to three copies, each about the size of the database, and their sidecars.
- When the copy cannot be written: no start, a pod in `CrashLoopBackOff`, an Argo CD Application Progressing then
  Degraded after 600 s, and the reason as the last line of `oc logs --previous`. The database is untouched, and the
  previous image still opens it.
- Time: 0.12 s at the lab's size, 25 s at a hundred times it (§2.1), inside the start.
- Code: the table below.

Lines added and removed by §7, from `git diff --numstat` on the applied copy (§4.3):

| file | added | removed |
|---|---|---|
| `local-development/gsd/store.py` | 118 (85 code, 23 comment or docstring, 10 blank) | 3 |
| `local-development/tests/test_pre_upgrade_copy.py` (new) | 272 | 0 |
| `docs/RUNBOOK_backup_restore.md` | 50 | 3 |
| `docs/CHANGELOG.md` | 15 | 0 |
| `charts/group-sync-dashboard/values.yaml` | 7 | 0 |
| `charts/group-sync-dashboard/README.md` | 6 | 0 |
| `charts/group-sync-dashboard/Chart.yaml` | 10 | 2 |
| `local-development/pyproject.toml`, `local-development/gsd/__init__.py` | 1 each | 1 each |
| `docs/specs/SPEC_S4c_credential_lifecycle.md`, `docs/specs/README.md` | 1 each | 1 each |

## 7. Implementation blocks

Applied in this order. Blocks 1 to 4 are `store.py`; block 5 creates the tests; 6 to 11 are the documents; 12 to 17
are the version fields, the history lines and SPEC_S4c's reservation.

### Block 1 — local-development/gsd/store.py: the imports the copy uses

`hashlib` for the sidecar, `shutil.disk_usage` for the space check, `socket.gethostname` for the pod's name, `time.monotonic` for the elapsed time, `suppress` for the cleanup (§3.3, §3.4, §3.6, §3.7).

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
from __future__ import annotations

import logging
import os
import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
```

New text:

```python
from __future__ import annotations

import hashlib
import logging
import os
import json
import shutil
import socket
import sqlite3
import threading
import time
from contextlib import contextmanager, suppress
from datetime import UTC, datetime, timedelta
```

### Block 2 — local-development/gsd/store.py: the copy, after the version read it attaches to

`PRE_UPGRADE_DIR`, `PRE_UPGRADE_KEEP`, `StorePreUpgradeCopyFailed`, `_pre_upgrade_copies` and `_pre_upgrade_copy` (§3.1 to §3.7), placed after #305's `_schema_state`.

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
def _schema_state(conn: sqlite3.Connection) -> tuple[int, bool]:
    """(PRAGMA user_version, fresh), read without writing. Fresh means no schema objects at all."""
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    fresh = conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone() is None
    return version, fresh
```

New text:

```python
def _schema_state(conn: sqlite3.Connection) -> tuple[int, bool]:
    """(PRAGMA user_version, fresh), read without writing. Fresh means no schema objects at all."""
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    fresh = conn.execute("SELECT 1 FROM sqlite_master LIMIT 1").fetchone() is None
    return version, fresh


#: Where the copy taken before a migration goes (#301): BESIDE the database, so it is written whatever
#: config.backup says and each replica's /data/$POD_NAME/gsd.db has its own. Nothing that reads
#: config.backup.dir looks here, and the name is outside their gsd-*.db pattern even if that setting pointed
#: here: the six-hourly rotation, the offsite script, the backup metric and the KPI size line never see it.
PRE_UPGRADE_DIR = "pre-upgrade"
#: Copies kept, newest by name: the UTC stamp leads it, so name order is time order. Each is about the
#: database's size and counts against persistence.size; nothing else prunes them, config.backup.keep included.
PRE_UPGRADE_KEEP = 3


class StorePreUpgradeCopyFailed(Exception):
    """The copy of the database taken before a migration was not written, so the migration did not run (#301)."""


def _pre_upgrade_copies(directory: Path) -> list[Path]:
    """The copies in `directory`, oldest first."""
    return sorted(directory.glob("pre-upgrade-*.db"))


def _pre_upgrade_copy(conn: sqlite3.Connection, db_path: str, version: int) -> None:
    """Copy the database as it is, before SCHEMA and _migrate change it, and verify the copy (#301).

    The migration is one-way, so this copy is the only way back to the build that wrote the database. It is
    taken on the connection that has run nothing yet, so it holds no table SCHEMA would add, and VACUUM INTO
    reads in one transaction: it needs no write lock and carries what a -wal left by the last pod holds.

    Once per upgrade per pod. A failed attempt commits SCHEMA's new tables and every migration before the
    one that failed, so the container's next attempt would copy a half-migrated database, and PRE_UPGRADE_KEEP
    of those would prune the clean one away. The pod's name, read as gsd/leader.py reads it, survives the
    container's restarts and changes with every new pod.
    """
    directory = Path(db_path).parent / PRE_UPGRADE_DIR
    host = os.environ.get("POD_NAME") or socket.gethostname()
    move = f"schema {version} -> {KNOWN_SCHEMA_VERSION}"
    earlier = [p for p in _pre_upgrade_copies(directory) if p.name.endswith(f"-to-{KNOWN_SCHEMA_VERSION}-{host}.db")]
    if earlier:
        log.info("pre-upgrade copy for %s not taken again: this pod wrote %s before an earlier attempt",
                 move, earlier[-1])
        return
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    target = directory / f"pre-upgrade-{stamp}-schema-{version}-to-{KNOWN_SCHEMA_VERSION}-{host}.db"
    tmp = target.with_name(target.name + ".tmp")
    sidecar = target.with_name(target.name + ".sha256")
    started = time.monotonic()

    def refused(reason: object) -> StorePreUpgradeCopyFailed:
        for leftover in (tmp, sidecar, target):          # a refused attempt leaves nothing behind
            with suppress(OSError):
                leftover.unlink(missing_ok=True)
        return StorePreUpgradeCopyFailed(
            f"{move}: the pre-upgrade copy of {db_path} could not be written to {directory}, so the database was "
            f"not migrated: {reason}. Free space on the volume or make the directory writable, then restart; or "
            f"deploy the image that understands schema {version} (docs/RUNBOOK_backup_restore.md §6)")

    try:
        directory.mkdir(parents=True, exist_ok=True)
        # What a killed attempt left: a .tmp is not a copy, and a sidecar without its copy verifies nothing.
        for stale in directory.glob("pre-upgrade-*.db.tmp"):
            stale.unlink()
        for orphan in directory.glob("pre-upgrade-*.db.sha256"):
            if not orphan.with_suffix("").exists():
                orphan.unlink()
        # The size SQLite reports, WAL included: the file alone can be a tenth of it.
        need = conn.execute("PRAGMA page_count").fetchone()[0] * conn.execute("PRAGMA page_size").fetchone()[0]
        free = shutil.disk_usage(directory).free
        if free < need:
            raise refused(f"free space {free / 1048576:.1f} MiB, database {need / 1048576:.1f} MiB")
        conn.execute(f"VACUUM INTO '{str(tmp).replace(chr(39), chr(39) * 2)}'")
        check = sqlite3.connect(f"file:{tmp}?immutable=1&mode=ro", uri=True)
        try:
            copied = check.execute("PRAGMA user_version").fetchone()[0]
            verdict = check.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            check.close()
        if copied != version or verdict != "ok":
            raise refused(f"the copy reads schema {copied} and integrity_check {verdict!r}")
        digest = hashlib.sha256()
        with tmp.open("rb") as fh:
            while chunk := fh.read(1 << 20):
                digest.update(chunk)
            os.fsync(fh.fileno())
        # `sha256sum -c` format, as the offsite script writes it; the copy takes its name only once it has one.
        with sidecar.open("w") as fh:
            fh.write(f"{digest.hexdigest()}  {target.name}\n")
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, target)
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)                                 # the names, before the migration commits anything
        finally:
            os.close(fd)
    except (sqlite3.Error, OSError) as exc:
        raise refused(exc) from exc
    log.info("pre-upgrade copy written before migrating %s: %s (%d bytes, %.2f s)", move, target,
             target.stat().st_size, time.monotonic() - started)
    for old in _pre_upgrade_copies(directory)[:-PRE_UPGRADE_KEEP]:
        for path in (old, old.with_name(old.name + ".sha256")):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                log.warning("could not remove the old pre-upgrade copy %s", path)
```

### Block 3 — local-development/gsd/store.py: the exported name

The refusal is part of the store's public surface, beside #305's.

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
__all__ = ["KNOWN_SCHEMA_VERSION", "Store", "StoreSchemaTooNew", "now_iso"]
```

New text:

```python
__all__ = ["KNOWN_SCHEMA_VERSION", "Store", "StorePreUpgradeCopyFailed", "StoreSchemaTooNew", "now_iso"]
```

### Block 4 — local-development/gsd/store.py: `Store.__init__` takes the copy before anything writes

Between #305's refusal and the WAL switch: the order of §3.3.

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
        version, _ = _schema_state(self._conn)
        if version > KNOWN_SCHEMA_VERSION:
            self._conn.close()
            raise StoreSchemaTooNew(
                f"database schema {version} is newer than this dashboard understands ({KNOWN_SCHEMA_VERSION}); "
                f"restore a backup at or below schema {KNOWN_SCHEMA_VERSION} (docs/RUNBOOK_backup_restore.md §4), "
                f"or deploy the image that understands {version}")
        self._conn.row_factory = sqlite3.Row
```

New text:

```python
        version, fresh = _schema_state(self._conn)
        if version > KNOWN_SCHEMA_VERSION:
            self._conn.close()
            raise StoreSchemaTooNew(
                f"database schema {version} is newer than this dashboard understands ({KNOWN_SCHEMA_VERSION}); "
                f"restore a backup at or below schema {KNOWN_SCHEMA_VERSION} (docs/RUNBOOK_backup_restore.md §4), "
                f"or deploy the image that understands {version}")
        # Older and not fresh: this open is about to migrate, so the copy comes first, or nothing does (#301).
        if version < KNOWN_SCHEMA_VERSION and not fresh:
            try:
                _pre_upgrade_copy(self._conn, path, version)
            except Exception:
                self._conn.close()
                raise
        self._conn.row_factory = sqlite3.Row
```

### Block 5 — local-development/tests/test_pre_upgrade_copy.py: the tests

One test per Definition-of-Done item, §4.1.

<!-- block: local-development/tests/test_pre_upgrade_copy.py | create -->

```python
"""The copy of the database taken before a migration (#301, docs/specs/SPEC_M1_pre_upgrade_copy.md).

The migration is one-way, so the database as it was before it is the only way back to the build that wrote
it. These tests hold four promises: the copy is taken before SCHEMA or any migration writes, it verifies, a
start that cannot take it does not migrate, and nothing that manages the six-hourly backups can reach it.
"""

from __future__ import annotations

import hashlib
import importlib.util
import os
import pathlib
import re
import shutil
import sqlite3
import subprocess
import sys
from datetime import timedelta

import pytest

import gsd.store as store_module
from gsd.store import (KNOWN_SCHEMA_VERSION, PRE_UPGRADE_DIR, PRE_UPGRADE_KEEP, Store,
                       StorePreUpgradeCopyFailed)

OFFSITE = (pathlib.Path(__file__).resolve().parents[2]
           / "charts" / "group-sync-dashboard" / "scripts" / "offsite_backup.py")
COPY_NAME = re.compile(rf"^pre-upgrade-\d{{8}}T\d{{6}}\.\d{{6}}Z-schema-(\d+)-to-{KNOWN_SCHEMA_VERSION}-(.+)\.db$")


def _older_database(path: pathlib.Path, version: int = KNOWN_SCHEMA_VERSION - 1) -> None:
    """A database this build must migrate: written by the real Store, rewound to `version`, holding one sync
    event, and missing one table SCHEMA creates — so a copy taken after SCHEMA ran would show it."""
    store = Store(str(path))
    store.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    store.record_sync_event("crc", "corp", "ns", "2026-09-26T10:00:00Z", "2026-09-26T10:00:30Z", "0 * * * *", 3)
    store.close()
    conn = sqlite3.connect(path)
    conn.execute("DROP TABLE kyverno_result_event")
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()


def _facts(path: pathlib.Path) -> dict:
    """Read-only, and not `immutable=1`: the live file's newest commits may still be in its -wal."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        return {"user_version": conn.execute("PRAGMA user_version").fetchone()[0],
                "tables": {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")},
                "sync_events": conn.execute("SELECT COUNT(*) FROM sync_event").fetchone()[0]}
    finally:
        conn.close()


def _copies(data: pathlib.Path) -> list[pathlib.Path]:
    """Every database file in the copy directory, whatever its name: the name is asserted, not assumed."""
    return sorted((data / PRE_UPGRADE_DIR).glob("*.db"))


def _grow_the_wal(db: pathlib.Path) -> None:
    """Commit rows to the -wal and die before any checkpoint, as a pod killed mid-run leaves its database: the
    main file is then far smaller than the database SQLite reads (SPEC_M1 §2.2)."""
    writer = subprocess.Popen([sys.executable, "-c", (
        "import sqlite3, sys, time\n"
        "c = sqlite3.connect(sys.argv[1]); c.execute('PRAGMA wal_autocheckpoint=0')\n"
        "c.executemany(\"INSERT INTO membership_event(cluster_id, group_name, user_name, change, observed_at)"
        " VALUES ('crc', 'g', ?, 'added', '2026-09-26T00:00:00Z')\", [(f'u{i}',) for i in range(20000)])\n"
        "c.commit(); print('ready', flush=True); time.sleep(30)\n"), str(db)], stdout=subprocess.PIPE, text=True)
    try:
        assert writer.stdout.readline().strip() == "ready"
    finally:
        writer.kill()
        writer.wait()
        writer.stdout.close()


def test_an_older_database_is_copied_before_schema_and_migrations_touch_it(tmp_path, caplog):
    db = tmp_path / "gsd.db"
    _older_database(db)
    with caplog.at_level("INFO", logger="gsd.store"):
        Store(str(db)).close()
    (copy,) = _copies(tmp_path)
    assert COPY_NAME.match(copy.name).group(1) == str(KNOWN_SCHEMA_VERSION - 1)
    facts = _facts(copy)
    assert facts["user_version"] == KNOWN_SCHEMA_VERSION - 1
    assert "kyverno_result_event" not in facts["tables"], "the copy was taken after SCHEMA ran"
    assert facts["sync_events"] == 1
    assert (copy.parent / (copy.name + ".sha256")).read_text() == (
        f"{hashlib.sha256(copy.read_bytes()).hexdigest()}  {copy.name}\n")
    assert not list(copy.parent.glob("*.tmp"))
    lines = caplog.text.splitlines()
    written = next(i for i, line in enumerate(lines) if "pre-upgrade copy written before migrating" in line)
    migrated = next(i for i, line in enumerate(lines) if f"schema migration {KNOWN_SCHEMA_VERSION} applied" in line)
    assert written < migrated
    assert f"schema {KNOWN_SCHEMA_VERSION - 1} -> {KNOWN_SCHEMA_VERSION}: {copy}" in lines[written]
    live = _facts(db)
    assert live["user_version"] == KNOWN_SCHEMA_VERSION and "kyverno_result_event" in live["tables"]


@pytest.mark.parametrize("cause", ["unwritable directory", "free space below the database",
                                   "free space for the file but not its WAL", "the rename fails"])
def test_a_copy_that_cannot_be_written_refuses_the_start(tmp_path, monkeypatch, caplog, cause):
    db = tmp_path / "gsd.db"
    _older_database(db)
    directory = tmp_path / PRE_UPGRADE_DIR
    real = shutil.disk_usage
    if cause == "unwritable directory":
        if os.geteuid() == 0:
            pytest.skip("root writes into a 0555 directory")
        directory.mkdir(mode=0o555)
    elif cause == "free space below the database":
        conn = sqlite3.connect(db)
        need = conn.execute("PRAGMA page_count").fetchone()[0] * conn.execute("PRAGMA page_size").fetchone()[0]
        conn.close()
        monkeypatch.setattr(store_module.shutil, "disk_usage", lambda path: real(path)._replace(free=need - 1))
    elif cause == "free space for the file but not its WAL":
        _grow_the_wal(db)
        size = db.stat().st_size
        assert (tmp_path / "gsd.db-wal").stat().st_size > size
        monkeypatch.setattr(store_module.shutil, "disk_usage", lambda path: real(path)._replace(free=size))
    else:
        # The last step: the copy and its sidecar are on disk, so this is the most a failure can leave behind.
        def rename_fails(src, dst):
            raise OSError("rename refused by the test")
        monkeypatch.setattr(store_module.os, "replace", rename_fails)
    try:
        with caplog.at_level("INFO", logger="gsd.store"), pytest.raises(StorePreUpgradeCopyFailed) as refused:
            Store(str(db))
        message = str(refused.value)
        assert message.startswith(
            f"schema {KNOWN_SCHEMA_VERSION - 1} -> {KNOWN_SCHEMA_VERSION}: the pre-upgrade copy of {db} could not "
            f"be written to {directory}, so the database was not migrated: ")
        if cause.startswith("free space"):
            assert re.search(r"free space [\d.]+ MiB, database [\d.]+ MiB", message)
        facts = _facts(db)
        assert facts["user_version"] == KNOWN_SCHEMA_VERSION - 1
        assert "kyverno_result_event" not in facts["tables"], "SCHEMA ran although the copy was refused"
        assert "schema migration" not in caplog.text
        assert not [p for p in directory.iterdir()], "a refused attempt left a file"
    finally:
        directory.chmod(0o755)


def test_a_database_at_the_build_version_writes_nothing(tmp_path):
    db = tmp_path / "gsd.db"
    Store(str(db)).close()
    Store(str(db)).close()
    assert not (tmp_path / PRE_UPGRADE_DIR).exists()


def test_a_fresh_file_writes_nothing(tmp_path):
    Store(str(tmp_path / "gsd.db")).close()
    assert not (tmp_path / PRE_UPGRADE_DIR).exists()


@pytest.fixture(scope="module")
def offsite():
    spec = importlib.util.spec_from_file_location("offsite_backup", OFFSITE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("backup_dir", ["backup", PRE_UPGRADE_DIR],
                         ids=["chart layout", "backup.dir set to the copies"])
def test_the_six_hourly_backups_do_not_see_the_copy(tmp_path, offsite, backup_dir):
    """The regression measured on #301: a `gsd-preupgrade-*` name in the backup directory sorts after every
    `gsd-2026…` backup, and `backup(keep=2)` deleted the backup it had just written. The copy's directory keeps
    it away from every reader of config.backup.dir, and its name keeps it out of their pattern even if
    config.backup.dir pointed at that directory."""
    from types import SimpleNamespace

    from prometheus_client import generate_latest

    from gsd.kpi.system import dashboard_data_bytes
    from gsd.metrics import build_registry
    from gsd.reporting.snapshot import _STAMP

    db = tmp_path / "gsd.db"
    _older_database(db)
    store = Store(str(db))
    try:
        (copy,) = _copies(tmp_path)
        assert not _STAMP.match(copy.name), "the report service would read the copy as a snapshot"
        backups = tmp_path / backup_dir
        settings = SimpleNamespace(backup_dir=str(backups), login_capture_enabled=False)
        metric = "gsd_backup_last_success_timestamp_seconds"

        def samples() -> list[str]:
            text = generate_latest(build_registry(store, timedelta(seconds=120), settings=settings)).decode()
            return [line for line in text.splitlines() if line.startswith(metric)]

        assert samples() == [], "the backup metric counts the pre-upgrade copy"
        assert dashboard_data_bytes(str(db), str(backups))()["backups"]["count"] == 0
        written = [store.backup(str(backups), keep=2) for _ in range(3)]
        assert all(written) and pathlib.Path(written[-1]).exists()
        assert sorted(p.name for p in backups.glob("gsd-*.db")) == sorted(pathlib.Path(w).name for w in written[1:])
        assert offsite.newest_backup(backups) == pathlib.Path(written[-1])
        assert len(samples()) == 1
        assert dashboard_data_bytes(str(db), str(backups))()["backups"]["count"] == 2
        assert copy.exists() and (copy.parent / (copy.name + ".sha256")).exists()
    finally:
        store.close()


def test_a_restarted_container_does_not_copy_again(tmp_path, monkeypatch, caplog):
    """A failed attempt commits what ran before the failure: here SCHEMA's table, and on main `cbbc65a` an 18 -> 20
    upgrade whose migration 20 failed also left user_version 19 (SPEC_M1 §2.6). A second copy would be of that,
    and PRE_UPGRADE_KEEP of them would prune the clean one. A container restarts in its pod; a new pod copies."""
    db = tmp_path / "gsd.db"
    _older_database(db)
    monkeypatch.setenv("POD_NAME", "crashing-pod")
    failing = [m for m in store_module._MIGRATIONS if m[0] != KNOWN_SCHEMA_VERSION]
    failing.append((KNOWN_SCHEMA_VERSION, "fails on purpose", ["INSERT INTO no_such_table VALUES (1)"]))
    monkeypatch.setattr(store_module, "_MIGRATIONS", failing)
    for _ in range(2):
        with caplog.at_level("INFO", logger="gsd.store"), \
                pytest.raises(sqlite3.OperationalError, match="no_such_table"):
            Store(str(db))
    (copy,) = _copies(tmp_path)
    assert "kyverno_result_event" not in _facts(copy)["tables"]
    assert "kyverno_result_event" in _facts(db)["tables"], "the failed attempt committed nothing to copy"
    assert f"not taken again: this pod wrote {copy} before an earlier attempt" in caplog.text
    monkeypatch.setenv("POD_NAME", "replacement-pod")
    with pytest.raises(sqlite3.OperationalError):
        Store(str(db))
    assert [COPY_NAME.match(p.name).group(2) for p in _copies(tmp_path)] == ["crashing-pod", "replacement-pod"]


def test_the_newest_copies_are_kept_and_a_killed_attempt_leaves_nothing(tmp_path):
    directory = tmp_path / PRE_UPGRADE_DIR
    directory.mkdir()
    seeds = [directory / f"pre-upgrade-2000090{i}T000000.000000Z-schema-{KNOWN_SCHEMA_VERSION - 2}-to-"
                         f"{KNOWN_SCHEMA_VERSION - 1}-pod-{i}.db" for i in range(1, 5)]
    for seed in seeds:
        seed.write_bytes(b"copy")
        (directory / (seed.name + ".sha256")).write_text("sidecar")
    stale = directory / "pre-upgrade-20000905T000000.000000Z-schema-1-to-2-killed.db.tmp"
    orphan = directory / "pre-upgrade-20000906T000000.000000Z-schema-1-to-2-killed.db.sha256"
    foreign = directory / "notes.txt"
    for path in (stale, orphan, foreign):
        path.write_text("x")
    db = tmp_path / "gsd.db"
    _older_database(db)
    Store(str(db)).close()
    kept = _copies(tmp_path)
    assert len(kept) == PRE_UPGRADE_KEEP == 3
    assert kept[:2] == seeds[2:] and COPY_NAME.match(kept[2].name)
    assert sorted(p.name for p in directory.iterdir()) == sorted(
        [p.name for p in kept] + [p.name + ".sha256" for p in kept] + [foreign.name])


def test_the_app_copies_with_backups_off_and_does_not_start_without_the_copy(tmp_path, monkeypatch):
    """The level it surfaces at: build_app is what `uvicorn gsd.api:create_app --factory` calls, and an exception
    there stops the container before it binds the port. With config.backup off the copy is still taken: its
    directory is the database's, not config.backup.dir."""
    from gsd.api import build_app
    from gsd.config import Settings

    db = tmp_path / "gsd.db"
    _older_database(db)
    real = shutil.disk_usage
    monkeypatch.setattr(store_module.shutil, "disk_usage", lambda path: real(path)._replace(free=0))
    with pytest.raises(StorePreUpgradeCopyFailed, match=r"free space 0\.0 MiB"):
        build_app(Settings(db_path=str(db), clusters=[], backup_dir=""), run_poller=False)
    monkeypatch.undo()
    app = build_app(Settings(db_path=str(db), clusters=[], backup_dir=""), run_poller=False)
    app.state.store.close()
    (copy,) = _copies(tmp_path)
    assert _facts(copy)["user_version"] == KNOWN_SCHEMA_VERSION - 1
```

### Block 6 — docs/RUNBOOK_backup_restore.md: the runbook names three copies

The intro lists what exists; the pre-upgrade copy is the third.

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
cluster cannot replay them (`gsd/store.py#Store.backup`). Two copies exist:

* **on-volume** — `config.backup` writes `gsd-<UTC stamp>Z.db` under `config.backup.dir`
  (`/data/backup`) every `intervalHours`, keeping `keep` of them, on the data claim;
* **off-volume** — `backup.offsite` (off by default) copies the newest of those to a second
  claim or to object storage, with a `.sha256` sidecar, after an integrity check
  (`charts/group-sync-dashboard/scripts/offsite_backup.py#ship`).
```

New text:

```text
cluster cannot replay them (`gsd/store.py#Store.backup`). Three copies exist:

* **on-volume** — `config.backup` writes `gsd-<UTC stamp>Z.db` under `config.backup.dir`
  (`/data/backup`) every `intervalHours`, keeping `keep` of them, on the data claim;
* **off-volume** — `backup.offsite` (off by default) copies the newest of those to a second
  claim or to object storage, with a `.sha256` sidecar, after an integrity check
  (`charts/group-sync-dashboard/scripts/offsite_backup.py#ship`);
* **pre-upgrade** — before a new image migrates the database, it writes the database as it was to
  `pre-upgrade/` beside it, with a `.sha256` sidecar, whatever `config.backup` says (§6).
```

### Block 7 — docs/RUNBOOK_backup_restore.md: §4c: a restored older copy is copied again before it migrates

A copy restored under a newer image migrates at its next start, so it is copied first.

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
The numbers must equal the copy's (§1). The pod log shows `schema migration N applied` lines
only if the copy predates the running version; the first poll then rebuilds every cache table.
```

New text:

```text
The numbers must equal the copy's (§1). The pod log shows `schema migration N applied` lines
only if the copy predates the running version, each after the line naming the pre-upgrade copy the
start took first (§6); the first poll then rebuilds every cache table.
```

### Block 8 — docs/RUNBOOK_backup_restore.md: §6, the new section

Where the copies are and how they are kept (the Definition of Done), what the refusal looks like, and how to use a copy. Inline code only: a fence inside a block would end the block (§4.3).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
the pattern in §4b (a helper pod with both claims), then §4c.
```

New text:

```text
the pattern in §4b (a helper pod with both claims), then §4c.

## 6. Pre-upgrade copies

A new image migrates the database it finds at startup, one way: `_MIGRATIONS` has no down-path, so the
database as it was before the migration is the only way back to the image that wrote it. The dashboard
takes that copy itself (`gsd/store.py#_pre_upgrade_copy`, #301) whenever the database's `user_version` is
below the image's highest migration, before the image creates a table or runs a migration. A new database,
and one already at the image's version, take none.

* **Where.** `pre-upgrade/` beside the database: `/data/pre-upgrade/`, or `/data/<pod>/pre-upgrade/` above
  one replica. It is written whether `config.backup` is on or off, and nothing that reads
  `config.backup.dir` looks there: not the six-hourly rotation, the offsite CronJob, the backup metric or
  the KPI size line.
* **Name.** `pre-upgrade-<UTC stamp>-schema-<from>-to-<to>-<pod>.db`, and a `.sha256` sidecar in
  `sha256sum -c` format. `<from>` is the copy's `user_version`: an image can open it only if its highest
  migration is at least that.
* **Verified before the migration runs.** The copy is written as `….db.tmp`, opened read-only and checked
  (`user_version` equal to `<from>`, `integrity_check` `ok`), hashed and synced, and only then renamed.
* **Kept.** The newest three, removed only when a newer copy has been written; `config.backup.keep` does
  not apply to them. Each is about the size of the database, on the data claim, so they count against
  `persistence.size`.
* **Once per pod.** A container that restarts because its migration failed does not copy again: the
  failed attempt committed this image's new tables and every migration before the one that failed, so a
  second copy would not be the database the previous image wrote. Its log says
  `pre-upgrade copy for schema <from> -> <to> not taken again: this pod wrote <file> before an earlier attempt`.
  A new pod copies again.

The startup log names the copy before the first migration line, for example
`pre-upgrade copy written before migrating schema 19 -> 20: /data/pre-upgrade/pre-upgrade-….db (9973760 bytes, 0.12 s)`
and then `schema migration 20 applied: …`.

**When the copy cannot be written, the dashboard does not start.** The container exits 1 before it binds
its port and the database is not migrated. The last line of
`oc logs -n $NS -l app=$REL -c dashboard --previous --tail=1` names the reason and the directory, for
example
`gsd.store.StorePreUpgradeCopyFailed: schema 19 -> 20: the pre-upgrade copy of /data/gsd.db could not be written to /data/pre-upgrade, so the database was not migrated: free space 40.0 MiB, database 120.0 MiB. …`.
Grow the claim or free space on it, or make the directory writable (the `oc debug` pod of §4a,
`chgrp 0` and `chmod g=u`), and the next restart takes the copy and migrates. Or deploy the previous
image, which opens the unmigrated database as before.

**Using a copy.** Verify it with §1, reading `/data/pre-upgrade/<file>` instead of a backup, or outside
the cluster with `sha256sum -c <file>.sha256` (§3). To go back to the image that wrote it, restore it with
§4a from `/data/pre-upgrade/<file>` and deploy that image; an image whose highest migration is below
`<from>` refuses it (§4c).
```

### Block 9 — charts/group-sync-dashboard/values.yaml: the values comment on `config.backup`

None of the `config.backup` keys governs the copy, and it counts against `persistence.size`.

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```yaml
  # deliberately does not grow credentials for object storage.
  backup:
    enabled: true
```

New text:

```yaml
  # deliberately does not grow credentials for object storage.
  #
  # NOT THE PRE-UPGRADE COPY, which none of these keys governs. Before a new image migrates the
  # database, it writes a verified copy of the database as it was to pre-upgrade/ beside it
  # (/data/pre-upgrade, or /data/$POD_NAME/pre-upgrade above one replica), with backups on or off,
  # and refuses to start rather than migrate without one. The newest three are kept, each about the
  # size of the database, so they count against persistence.size; `keep` and the six-hourly job
  # never touch them (docs/RUNBOOK_backup_restore.md §6).
  backup:
    enabled: true
```

### Block 10 — charts/group-sync-dashboard/README.md: the chart README's Backups section

A reader sizing the claim from the README alone would miss the copies (§3.5).

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
**Half an answer by design.** These land on the *same* volume they protect against, so they
cover corruption, a bad migration and accidental deletion — not loss of the volume. The other
half is `backup.offsite` below: a CronJob mounting the same claim read-only. The dashboard
itself never grows credentials for object storage.
```

New text:

```text
**Half an answer by design.** These land on the *same* volume they protect against, so they
cover corruption, a bad migration and accidental deletion — not loss of the volume. The other
half is `backup.offsite` below: a CronJob mounting the same claim read-only. The dashboard
itself never grows credentials for object storage.

**The pre-upgrade copy is separate.** Before a new image migrates the database, it writes the
database as it was to `pre-upgrade/` beside it, whether `config.backup` is on or off, and does not
start without it. The newest three are kept, each about the size of the database, so they count
against `persistence.size`; `config.backup.keep` does not apply to them
([runbook §6](../../docs/RUNBOOK_backup_restore.md#6-pre-upgrade-copies)).
```

### Block 11 — docs/CHANGELOG.md: the CHANGELOG entry

Under Unreleased, newest first, naming both versions (`tests/test_kyverno.py` holds the chart's).

<!-- block: docs/CHANGELOG.md | edit -->

Old text:

```text
## Unreleased

- **The dashboard refuses a database newer than it understands (#305; application only).** An image
```

New text:

```text
## Unreleased

- **The database is copied before a new image migrates it (#301, `docs/specs/SPEC_M1_pre_upgrade_copy.md`;
  application 0.37.0, chart 0.59.0).** When an image opens a database whose `user_version` is below its
  highest migration, it first writes the database as it was to `pre-upgrade/` beside it (`/data/pre-upgrade`,
  or `/data/$POD_NAME/pre-upgrade` above one replica), before its own schema, migrations or seeds run. The
  copy is opened and checked (`user_version`, `integrity_check`), gets a `.sha256` sidecar, and is logged at
  INFO before the first `schema migration N applied` line. When it cannot be written (the directory is not
  writable, or the free space is below the database's size, its WAL included) the dashboard does not start,
  the database is not migrated, and the last log line names the reason and the directory. The copy is
  written whether or not `config.backup` is on, and its name is outside the six-hourly `gsd-*.db` pattern,
  so the rotation, `config.backup.keep`, the offsite CronJob, `gsd_backup_last_success_timestamp_seconds`
  and the KPI size line never see it. The newest three are kept, each about the size of the database, so
  they count against `persistence.size`; a container that restarts after a failed migration does not copy
  again. A new database, or one already at the image's version, takes no copy. Where the copies are and
  how to use them: [RUNBOOK_backup_restore.md §6](RUNBOOK_backup_restore.md#6-pre-upgrade-copies). This
  release also carries #305 below. SPEC_S4c's reserved versions move to app 0.38.0, chart 0.60.0.
- **The dashboard refuses a database newer than it understands (#305; application only).** An image
```

### Block 12 — local-development/pyproject.toml: the application version

§3.11.

<!-- block: local-development/pyproject.toml | edit -->

Old text:

```toml
version = "0.36.0"
```

New text:

```toml
version = "0.37.0"
```

### Block 13 — local-development/gsd/__init__.py: the package version

Held equal to pyproject's by `tests/test_chart_versions.py`.

<!-- block: local-development/gsd/__init__.py | edit -->

Old text:

```python
__version__ = "0.36.0"
```

New text:

```python
__version__ = "0.37.0"
```

### Block 14 — charts/group-sync-dashboard/Chart.yaml: the chart version and its history line

§3.11; CI refuses a chart change without a new version.

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

Old text:

```yaml
# CHART 0.58.3 (2026-09-26), PATCH: Epic A: quick cleanup (#381).
version: 0.58.3
```

New text:

```yaml
# CHART 0.58.3 (2026-09-26), PATCH: Epic A: quick cleanup (#381).
# CHART 0.59.0, MINOR: appVersion moves to application 0.37.0 (below): the copy of the database taken
# before a migration (#301, SPEC_M1) and the refusal of a database newer than the image (#305). The
# values comment on config.backup and the README say where the copy goes and that it counts against
# persistence.size. No template, value or RBAC change.
version: 0.59.0
```

### Block 15 — charts/group-sync-dashboard/Chart.yaml: appVersion and its history line

appVersion equals pyproject's version (`tests/test_chart_versions.py`).

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

Old text:

```yaml
# `clusterconfig_manage`. MINOR: who may open two surfaces changes on upgrade (docs/CHANGELOG.md).
appVersion: "0.36.0"
```

New text:

```yaml
# `clusterconfig_manage`. MINOR: who may open two surfaces changes on upgrade (docs/CHANGELOG.md).
# 0.37.0. Before a migration, the database as it was is copied to pre-upgrade/ beside it, verified, with
# a .sha256 sidecar, the newest three kept, and the image does not start rather than migrate without the
# copy (#301, SPEC_M1). A database newer than the image is refused before anything writes to it (#305).
# MINOR: a new directory on the data volume, and two ways a start is refused.
appVersion: "0.37.0"
```

### Block 16 — docs/specs/SPEC_S4c_credential_lifecycle.md: SPEC_S4c's reservation moves

A specified spec's versions stay above the tree's (`tests/test_specs_index.py`).

<!-- block: docs/specs/SPEC_S4c_credential_lifecycle.md | edit -->

Old text:

```text
| Version on release | app 0.37.0, chart 0.59.0 |
```

New text:

```text
| Version on release | app 0.38.0, chart 0.60.0 |
```

### Block 17 — docs/specs/README.md: the index row of SPEC_S4c

The index and the spec's header say the same thing (`tests/test_specs_index.py`).

<!-- block: docs/specs/README.md | edit -->

Old text:

```text
| S4c | [`SPEC_S4c_credential_lifecycle.md`](SPEC_S4c_credential_lifecycle.md) — S4 step C: the credential lifecycle — the daily ping, `self-login` renewal at the fixed margin, and the per-credential gate on a fleet-account Lease, durable and replica-shared; the design of #285 | S — cluster configuration | — | app 0.37.0, chart 0.59.0 | [#285](https://github.com/ephico2real2/group-sync-dashboard/issues/285) | specified |
```

New text:

```text
| S4c | [`SPEC_S4c_credential_lifecycle.md`](SPEC_S4c_credential_lifecycle.md) — S4 step C: the credential lifecycle — the daily ping, `self-login` renewal at the fixed margin, and the per-credential gate on a fleet-account Lease, durable and replica-shared; the design of #285 | S — cluster configuration | — | app 0.38.0, chart 0.60.0 | [#285](https://github.com/ephico2real2/group-sync-dashboard/issues/285) | specified |
```
