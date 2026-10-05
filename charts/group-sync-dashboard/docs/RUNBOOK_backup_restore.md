# Runbook — backing up and restoring the dashboard's history

The sync timeline and membership history exist only because this process observed them; the
cluster cannot replay them (`gsd/store.py#Store.backup`). Three copies exist:

* **on-volume** — `config.backup` writes `gsd-<UTC stamp>Z.db` under `config.backup.dir`
  (`/data/backup`) every `intervalHours`, keeping `keep` of them, on the data claim. Above one replica
  every pod writes `gsd-<UTC stamp>Z-<pod name>.db` into that same directory and keeps `keep` of its own:
  `keep` applies per replica, and no pod deletes another pod's copies. The copies of a pod that no longer
  exists (a rollout renames every pod), and the copies named without a pod (written at one replica, or by a
  release before #391), stay until they are removed by hand, or until the release runs one replica again,
  whose next backup keeps `keep` copies in all (#391);
* **off-volume** — `backup.offsite` (on by default wherever it can work) copies the newest of those to a
  second claim or to object storage, with a `.sha256` sidecar, after an integrity check
  (`charts/group-sync-dashboard/scripts/offsite_backup.py#ship`), and, at one replica with the second
  claim, the newest pre-upgrade copy as well (§6);
* **pre-upgrade** — from the application release after 0.36.0, before a new image upgrades the database it
  writes the database as it was to `pre-upgrade/` beside it, with a `.sha256` sidecar, even when scheduled
  backups are disabled (§6).

Everything below uses only what the pod has: `sh`, `cat`, `ls`, `rm`, `chgrp`, `chmod`, `curl`,
`python3.14` (`docs/design/DESIGN_hardened_image.md#What it changed for operators`). There is **no
`tar`**, so `oc cp` and `oc rsync` do not work against this image; bytes move with `cat` over
`oc exec`. Set `NS` and `REL` (the release's fullname, `oc get deploy -n $NS`) once:

```sh
NS=group-sync; REL=group-sync-dashboard
```

## 0. Before every upgrade

The first start of an image that moves the schema upgrades the database one way (§6), and the copy it takes first
stays on the volume it protects. Before you change the image a release runs (a new chart version, or `image.tag` in
its values file), do these three things. None of them stops the dashboard.

1. **Read whether the upgrade migrates the database, and note the schema you leave.** In `docs/CHANGELOG.md`,
   every entry after the version you run (`gsd_build_info`'s `version` label on `/metrics`), up to and including
   the one you deploy, that carries a `**Schema N → M.**` line migrates the database on its first start
   (`local-development/prepare-release.py#SCHEMA_LINE`); an epic's GitHub release lists its children's lines. The
   version you run, and the two volume gauges step 3 compares, are read from `/metrics` through the pod's loopback,
   where the app listens; nothing is opened or written, and `grep` runs on your workstation:

   ````sh
   oc exec -n $NS deploy/$REL -c dashboard -- curl -s http://127.0.0.1:8080/metrics | grep -E '^gsd_(build_info|volume_disk_(total|used)_bytes)\{'
   ````

   It prints three lines: `gsd_build_info{branch="main",commit="…",version="<the version you run>"} 1.0` and the two
   gauges in bytes. The schema you leave is the one the running image understands, read without opening the live
   file:

   ````sh
   oc exec -n $NS deploy/$REL -c dashboard -- python3.14 -c 'from gsd.store import KNOWN_SCHEMA_VERSION; print(KNOWN_SCHEMA_VERSION)'
   ````

   While the dashboard runs, its database is at exactly this number: a newer one is refused at startup
   (`gsd/store.py#StoreSchemaTooNew`) and an older one is migrated up to it (`gsd/store.py#_migrate`). Note it: it is
   the `<from>` in the pre-upgrade copy's name (§6), and a copy at this schema restores under the image you run now
   (§4).
2. **Take a copy off the volume, and confirm it landed.** Whether the release has the offsite CronJob decides how:

   ````sh
   oc get cronjob -n $NS $REL-backup-offsite
   ````

   * **It exists** (`backup.offsite` on): run it now (§2). The copy landed when the Job is `Complete` and its log
     says `copied … -> …` followed by `integrity_check ok; user_version` with step 1's number, or `already shipped:
     … matches its sidecar` (a scheduled run shipped the same backup and verified it then):

     ````sh
     J=manual-$(date +%s)
     oc create job -n $NS --from=cronjob/$REL-backup-offsite $J
     oc wait -n $NS --for=condition=complete job/$J --timeout=1800s
     oc logs -n $NS job/$J --all-containers | grep -E '^(copied|already shipped|integrity_check)'
     ````

     Without `oc`, where Prometheus reads kube-state-metrics, §2's query gives the last scheduled success, and
     `GroupSyncDashboardOffsiteBackupStale` not firing says it is recent: that copy is at most one
     `backup.offsite.schedule` old.
   * **It does not** (`NotFound`): copy the newest on-volume backup to your workstation (§3), and check it there
     with §1's snippet run with `python3`: `integrity_check: ok`, and a `user_version` equal to step 1's number.

     ````sh
     B=$(oc exec -n $NS deploy/$REL -c dashboard -- python3.14 -c 'import glob; print(sorted(glob.glob("/data/backup/gsd-*.db"))[-1])')
     oc exec -n $NS deploy/$REL -c dashboard -- cat "$B" > "$(basename "$B")"
     sha256sum "$(basename "$B")"
     ````

   Either way the copy is the newest six-hourly backup (`config.backup.intervalHours`); what changed after it is in
   the live database and, when the schema moves, in the pre-upgrade copy the new image takes on the volume.
3. **Know where the pre-upgrade copy goes, and that it fits.** When step 1 found a schema line, the new image's
   first start writes the database as it is to `/data/pre-upgrade/` (`/data/<pod-name>/pre-upgrade/` above one
   replica) before it migrates, and refuses to start, changing nothing, while the free space there is below the
   database's size (§6). Compare the two:

   ````sh
   oc exec -n $NS deploy/$REL -c dashboard -- python3.14 -c 'import glob, os, shutil; print("free", shutil.disk_usage("/data").free); print("databases", sum(os.stat(p).st_size for p in glob.glob("/data/gsd.db") + glob.glob("/data/gsd.db-wal") + glob.glob("/data/*/gsd.db") + glob.glob("/data/*/gsd.db-wal")))'
   ````

   `free` must be above `databases`. A copy needs at most its database's file and `-wal` together, and above one
   replica every pod copies its own at the same start, so the sum counts them all; `os.stat` opens no database.
   Step 1's `/metrics` read printed the volume's numbers too, and Prometheus has them where it scrapes the dashboard:
   `gsd_volume_disk_total_bytes{component="dashboard"}` minus `gsd_volume_disk_used_bytes{component="dashboard"}` is
   the free space, or more than the copy may use where the filesystem keeps blocks for root (`mke2fs` reserves 5% by
   default).

## What a successful backup looks like

Three pictures from the CRC lab (`reports/2026-09-26_epic-b-release/`). The first is the live dashboard pod. The second
and third come from a throwaway pod that worked on *copies* of a backup, not from the dashboard pod. Each shows the
pod's own output. The commands are below each picture, and lines not relevant to the picture are left out. `grep` and
`tail` run on your workstation; the pod has neither.

Without a terminal, the KPI page's **Backups** card (the cluster-admin tier, #306) shows what the first picture
shows, read by the dashboard process itself and with no Prometheus: the newest copy's instant (the last-success
metric's file), the copies kept against `keep` and their size, the failures since the process started, the newest
copy's schema against the one the running image understands, and the newest pre-upgrade copy (§6). One state, in
words: healthy, no copy yet, failing, stale (older than two backup intervals), or disabled.

**The six-hourly backup (the live pod).** The log line names the file and how many are kept, and the listing shows
that many copies. The §1 check on the newest copy says `integrity_check: ok`, with a `user_version` equal to the
running app's. Failures are zero, and the last-success metric is the newest file's time. In this capture the metric
`1.7904500667085032e+09` is 2026-09-26T19:14:26.7Z, the same second as the file `gsd-20260926T191426.213034Z.db`. It
was taken at 23:02:25Z on application 0.36.0.

![A successful six-hourly backup: the log line, four copies, the §1 check ok at schema 20, zero failures](../../../docs/screenshots/backup-six-hourly-success.png)

```sh
oc logs -n $NS deploy/$REL -c dashboard | grep 'backup written' | tail -1
oc exec -n $NS deploy/$REL -c dashboard -- ls -l /data/backup
oc exec -n $NS deploy/$REL -c dashboard -- python3.14 -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/metrics").read().decode())' | grep '^gsd_backup'
```

The picture's `<the §1 check>` block is §1's Python snippet, run on the newest file.

**The pre-upgrade copy (§6).** When a new image finds an older database, its startup log has
`pre-upgrade copy written before migrating schema <from> -> <to>: <file> (<bytes> bytes, <seconds> s)` before the
first `schema migration <to> applied` line. `pre-upgrade/` holds the copy and its `.sha256`. The copy matches its
sidecar, passes `integrity_check`, and keeps the old `user_version`:

![A successful pre-upgrade copy: taken before the migration, one copy with its sidecar, sidecar OK, integrity ok, schema 20](../../../docs/screenshots/backup-pre-upgrade-copy-success.png)

```sh
oc exec -n $NS deploy/$REL -c dashboard -- ls -l /data/pre-upgrade
oc exec -n $NS deploy/$REL -c dashboard -- sh -c 'cat /data/pre-upgrade/*.sha256'
oc exec -n $NS deploy/$REL -c dashboard -- python3.14 -c "$(cat reports/2026-09-26_epic-b-release/walk/pre-verify.py)" /data/pre-upgrade
```

The picture was taken on a copy in a throwaway pod, with a test-only migration 21, so its paths are under
`/tmp/work/301/`. On the dashboard they are under `/data/pre-upgrade/`, or `/data/<pod-name>/pre-upgrade/` with more
than one replica. A database already at the image's schema has no `pre-upgrade/` directory, and that is correct.

**A backup proven restorable.** On copies in a throwaway pod, never on the live file:
- the released app opens the copy with no migration and no new copy;
- the row counts are the same before and after the open;
- with polling off, the app serves the copy's groups and their stored changes.

The picture shows these checks, R1 to R4, for the six-hourly backup and for the pre-upgrade copy. Its total, 13, also
counts the #305 and #301 checks, which are out of frame:

![A backup proven restorable: R1 to R4 on the six-hourly backup and on the pre-upgrade copy; 13 of 13 checks, five of them out of frame](../../../docs/screenshots/backup-restore-check-success.png)

The recipe, as run on the lab. The pod mounts no volume, and the image has no `sleep`, so the pod waits in Python:

```sh
IMG=$(oc get deploy -n $NS $REL -o jsonpath='{.spec.template.spec.containers[0].image}')
oc run gsd-restore-check -n $NS --image=$IMG --restart=Never --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"gsd-restore-check","image":"'$IMG'","command":["python3.14","-c","import time; time.sleep(1800)"],"securityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]}}}]}}'
oc wait -n $NS pod/gsd-restore-check --for=condition=Ready --timeout=120s
B=$(oc exec -n $NS deploy/$REL -c dashboard -- python3.14 -c 'import glob; print(sorted(glob.glob("/data/backup/gsd-*.db"))[-1])')
oc exec -n $NS deploy/$REL -c dashboard -- cat "$B" | oc exec -i -n $NS gsd-restore-check -- sh -c 'cat > /tmp/backup.db'
oc exec -i -n $NS gsd-restore-check -- sh -c 'cat > /tmp/walk_epic_b.py' < reports/2026-09-26_epic-b-release/walk/walk_epic_b.py
oc exec -n $NS gsd-restore-check -- python3.14 -W ignore /tmp/walk_epic_b.py /tmp/backup.db /tmp/work
oc delete pod gsd-restore-check -n $NS
```

The script prints PASS or FAIL for each check, and exits 1 on any failure. Restoring onto the live database is §4, and
the scripted rollback is #302.

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
    n, top = c.execute(f"SELECT COUNT(*), COALESCE(MAX(id), 0) FROM {t}").fetchone()
    print(t, n, "rows, highest id", top)
' /data/backup/gsd-20260904T061500.123456Z.db
```

Expected: `integrity_check: ok`, a `user_version` equal to the running app's latest migration,
and row counts that are plausible for the age of the copy. Keep the three highest ids of the copy you restore: §4c
counts the restored file up to them.

In the CronJob's image the same check is one flag, and it also compares the sidecar:

```sh
oc create job -n $NS --from=cronjob/$REL-backup-offsite verify-$(date +%s) --dry-run=client -o json \
  | python3 -c '
import json, sys
job = json.load(sys.stdin)
job["metadata"].pop("ownerReferences", None)
c = job["spec"]["template"]["spec"]["containers"][0]
c["command"] = ["python3.14", "/scripts/offsite_backup.py", "--check", "/offsite/gsd-20260904T061500.123456Z.db"]
json.dump(job, sys.stdout)
' | oc apply -f -
oc wait -n $NS --for=condition=complete job/verify-<stamp> --timeout=180s && oc logs -n $NS job/verify-<stamp>
```

(`date` and `python3` here run on your workstation, not in the pod. With the `s3` destination
the CronJob's only container that runs the script is the init container, whose copy is under
`/stage` and is gone when the Job ends — verify an S3 copy after downloading it, §3.) Expected:
`integrity_check ok`, `sha256 …`, `sidecar matches`, `user_version …`, row counts.

Outside the cluster, with the copy downloaded (see §3): `sha256sum -c gsd-….db.sha256` and the
same Python snippet with `python3`.

## 2. Run the off-volume copy by hand

The destination claim is bound by the chart's one-shot bind Job when the module is enabled
(`oc get job -n $NS -l app.kubernetes.io/component=backup-offsite` shows it `Complete` under Helm;
under Argo CD it is a Sync hook and is gone once it succeeded), so `helm upgrade --wait` works and
an Argo sync turns healthy without waiting for the first scheduled run. If an upgrade ever fails part-way, the objects that revision created
are not owned by Helm until the next successful one renders them — delete them by label,
`oc delete cronjob,job,sa,cm -l app.kubernetes.io/component=backup-offsite`, for a clean slate; the
claim carries `helm.sh/resource-policy: keep` and is never removed that way.

```sh
oc create job -n $NS --from=cronjob/$REL-backup-offsite manual-$(date +%s)
oc logs -n $NS -l job-name=manual-<stamp> -f
```

Expected log:

```
copied /data/backup/gsd-….db -> /offsite/gsd-….db (NNN bytes, sha256 …)
integrity_check ok; user_version 20; membership_event rows N; sync_event rows M
pruned 0 older copies (keep=14)
no pre-upgrade-*.db under /data/pre-upgrade: nothing to ship (one is written only when an image upgrades the schema)
```

The last line is the second pass, which runs at one replica with the `pvc` destination. Once an upgrade
has written a pre-upgrade copy (§6), that line is replaced by the pass's own three lines, which name
`/data/pre-upgrade/pre-upgrade-….db -> /offsite/pre-upgrade/pre-upgrade-….db`, its `integrity_check ok`
and `pruned 0 older copies (keep=3)`. The pass checks the copy against the `.sha256` beside it first and
keeps the newest three. The two passes are independent: a failure in one does not stop the other, and
either fails the Job. A pass that prints `ERROR: … it is not the copy the store verified` has found a copy whose
bytes no longer match the checksum the dashboard wrote when it took it: do not restore from it. Every run fails on
it, and `GroupSyncDashboardOffsiteBackupStale` fires while the six-hourly copies still ship, until a newer upgrade
writes a newer copy or that copy and its `.sha256` are moved out of `pre-upgrade/` (to `/data/pre-restore/`, as §6
does); the next run then ships the newest copy that verifies.

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

**In order.** Turn recovery mode on through the release's values file, with the image you will restore under (steps
1 and 2 below); list the copies and restore one with `restore-db.sh` (**The script, in recovery mode**, next); turn
recovery mode off and verify (step 5 and §4c). §4a and §4b are the same restore by hand, the fallback when the script
cannot be used, and **Without recovery mode** below is the fallback for a chart that has none. Every change to the
release goes through its values file and its deployment pipeline, never `oc scale` or `oc set env`: a GitOps
controller that self-heals, Argo CD's for one, reverts a hand edit to an object it renders. The one exception is §4d,
the break glass for an incident on a release Argo CD syncs, which pauses Argo CD's automated sync first, puts the pod
into recovery mode by hand, restores with the same script and gives the release back to Git.

> **Risks under Argo CD** (measured on the CRC lab with Argo CD v3.4.7, 2026-10-02; #533, #532)
>
> * **Argo CD left on during a hand edit.** With `syncPolicy.automated.selfHeal: true`, Argo CD puts back within a
>   second a field it renders that was changed by hand (an `imagePullPolicy` changed by hand was back 0.7 s later),
>   and leaves a field that only the hand edit added (an added variable was still there 4 min 38 s later, the
>   Application reading Synced). A hand recovery edit is both: self-heal would restore the app's command and liveness
>   probe and start the app, perhaps on a half-restored database, while the pod still carries the recovery variables.
>   Pause automated sync first and confirm the pause held (§4d steps 1 and 2).
> * **The endless retry, on a chart before 0.65.0.** There, recovery mode never reports healthy, so a sync that turns
>   it on through the values file fails at the Deployment's progress deadline and is retried under the Application's
>   `syncPolicy.retry`, and every later change, `recovery.enabled: false` included, waits until the last retry has
>   failed: 12 min 49 s on the lab with `limit: 3` and a 30 s backoff doubling up to 5 min (#532). A `limit` less
>   than 0 retries without end, and an automated sync with no `retry` block retries 5 times. Meanwhile the
>   Application reads OutOfSync with its operation Running (`Retrying attempt #N`), the new revision is not applied,
>   and the recovery pod stays `1/2`. The way out is §4d step 7: pause, then end the running operation. From chart
>   0.65.0 recovery mode is its own Deployment and both Deployments report Healthy, so there is nothing to retry.

**The script, in recovery mode (#302).** With the release's pod in recovery mode (#303: `recovery.enabled: true`
in the release's values file), run `local-development/restore-db.sh --list` from your laptop, then
`local-development/restore-db.sh --from-version <ID>` with an ID it printed. It does what §4a and §4b do by hand,
for a scheduled backup, a pre-upgrade copy (§6) or a copy on the offsite claim when recovery mode mounts it: it
refuses a copy newer than the image, a sidecar that does not match and a failed `integrity_check`; it shows what the
restore discards and asks; it keeps the live set (`gsd.db` with its `-wal` and `-shm`) under
`/data/pre-restore/<stamp>/`; and it writes the copy under a temporary name, with `chgrp 0` and `chmod g=u`,
before it renames it onto `gsd.db`. It refuses unless the release's one pod is in recovery mode with at least ten
minutes of `recovery.ttl` left. The commands below stay as the fallback, and as the specification the script
implements (`docs/specs/SPEC_E3_restore_db.md`).

**Undo a restore.** The live set the script replaced is kept under `/data/pre-restore/<stamp>/`, and it is the way
back; a directory whose name ends in `.tmp` is a keep that never finished, not a set. Stay in recovery mode. The
kept set's committed rows may sit only in its `gsd.db-wal`, so fold it before anything copies it: in the recovery pod,
`oc exec -n $NS <pod> -c dashboard -- python3.14 -c 'import sqlite3, sys; c = sqlite3.connect(sys.argv[1]); c.execute("PRAGMA user_version"); c.close()' /data/pre-restore/<stamp>/gsd.db`
leaves that `gsd.db` whole and alone: SQLite folds the `-wal` into it and removes it with the `-shm`, and rolls a hot
`-journal` back. If a `-wal` or `-journal` with bytes is still beside it afterwards, something else has it open or
it is damaged; do not go on. Then restore it with §4a's commands, the kept `gsd.db` in place of the `gsd-….db` copy:
they run `integrity_check` on it, keep the current live set first, write it beside `gsd.db` under a temporary name,
and remove the current `-wal`, `-shm` and `-journal` before it takes the name. A kept `gsd.db` copied without the
fold can lack every row its `-wal` held.

**Deleting copies from the page (#542).** Nothing rotates `pre-restore/`: every restore adds a set. A cluster
administrator removes the ones no longer needed from the KPI page's **Database copies** card (one at a time, or a
cleanup previewed and confirmed), which also lists the scheduled backups and the pre-upgrade copies. The newest copy
of each directory is never deleted there: the newest backup (this section always has a copy to restore), the newest
pre-upgrade copy (§6) and the newest pre-restore set (the undo of the last restore). The page runs only while the
app serves, so it plays no part in recovery mode and changes nothing in the steps above.

The dashboard is the only writer and must be **stopped** first: two processes on one SQLite
file corrupt rather than error (`gsd/store.py#Store.__init__`).

**Recovery mode is the primary path (chart 0.60.0 and later, #303).** The recovery pod (`$REL-recovery` from chart
0.65.0, #532) has the app's pod spec and data volume but runs the chart's recovery script instead of the app
(`charts/group-sync-dashboard/scripts/recovery_mode.py`), so nothing opens `gsd.db`, and it stays up until
`recovery.ttl` (2h by default): a dropped `oc` session does not end it. It is a value like any other: set it
in this release's values file and roll it out through the release's deployment pipeline. Never with
`oc set env` or an edit of the Deployment: a GitOps tool such as Argo CD (selfHeal) reverts a hand edit.

1. **Turn it on, with the image you will restore under.** In the release's values file set
   `recovery.enabled: true` and `recovery.ttl` (for example `2h`, longer than the restore needs), and roll it
   out. For a rollback, set the older `image.tag` in the same change, so the restore runs under the image
   that will open the file.
2. **Wait for the recovery pod.** The app's Deployment goes to 0 and `$REL-recovery` to 1 (chart 0.65.0 and
   later, #532); the scheduler holds the recovery pod `Pending` until the app's pod is gone.
   `oc get pods -n $NS -l app=$REL-recovery` then shows `2/2` ready (`1/1` with the proxy off) and `Running`; no
   Service selects it. `oc logs -n $NS deploy/$REL-recovery -c dashboard` starts with `RECOVERY MODE`, `the app is
   NOT running and no data is collected` and the TTL's end. With `backup.offsite` on its `pvc` destination, the
   offsite claim is at `/offsite`, read-only. Both Deployments report available, so a pipeline step that waits for
   the rollout succeeds. A pipeline that rolls a failed rollout back on its own (Helm's `--rollback-on-failure`
   flag, `--atomic` in Helm 3, or an equivalent remediation) must still not carry this change: a rollout that
   fails for another reason is rolled back, which turns recovery mode off by itself and starts the app on a file
   that may be half restored.
3. **Restore** with `local-development/restore-db.sh --list`, then `--from-version <ID>` (**The script, in recovery
   mode**, above), each with `--namespace $NS --release $REL` unless both are the script's defaults
   (`group-sync-dashboard`); it refuses with less than ten minutes of `recovery.ttl` left. By hand, the fallback, use
   §4a or §4b, running their commands with `oc exec -n $NS deploy/$REL-recovery -c dashboard -- sh -c '…'` instead of `oc debug`
   or a helper pod. **Check the time left first** (the last `left` line of `oc logs`):
   at the TTL the script exits and every process in the container stops with it, a restore still running
   included, which leaves `gsd.db` half written. If the restore may not finish in time, extend first.
4. **More time?** At the TTL the script exits 1, the pod reads `CrashLoopBackOff`, and the log ends with how to
   extend or leave. Set a longer `recovery.ttl` (for example `4h`) in the values file and roll it out: the new
   pod counts it from its start. The change replaces the pod and ends any `oc exec` session in it; so does an
   eviction or a node drain, whose new pod also starts a new TTL. The time left is counted on the node's
   monotonic clock, so setting the wall clock back does not lengthen it; if the node restarts under the pod,
   the TTL counts as reached.
5. **Turn it off**, and verify with §4c: set `recovery.enabled: false` in the values file (keep a rollback's
   older `image.tag`) and roll it out. The rollout scales the recovery Deployment to 0 and the app's back to 1; the
   scheduler holds the app's pod until the recovery pod is gone, and the app starts on the restored file within
   the one rollout (#532). On a chart before 0.65.0, where the release's GitOps controller retries a failed sync (a
   `syncPolicy.retry` policy), the change waits until the retries of the sync that turned recovery on have run
   out, 12 min 49 s on the lab, and the recovery pod keeps running until then (the risks box above).

Nothing is recorded while recovery mode is on, and no rule says so: `GroupSyncDashboardNotPolling` reads a
gauge the stopped process no longer emits, so it returns nothing. With reporting on,
`GroupSyncDashboardReportSnapshotStale` (warning) fires after about 50 minutes, because the report service's
newest copy stops advancing. The TTL is the bound.

**Development and troubleshooting only:** with plain Helm and no pipeline, the same change is
`helm upgrade $REL <chart> -n $NS -f <values-file>`, with the chart reference and version the release already
runs (`helm list -n $NS`) and the release's complete values file, now carrying `recovery`.

**Without recovery mode** (the fallback, and any chart before 0.60.0), stop the writer the same way: set
`replicaCount: 0` in this release's values file and roll it out through its deployment pipeline (it changes the
Deployment's `replicas` and the configuration's copy of the number, not the claim or its access mode), then use the
`oc debug` pod of §4a or the helper pod of §4b. Wait until the pod is gone:

```sh
oc wait -n $NS --for=delete pod -l app=$REL --timeout=120s
```

### 4a. From an on-volume copy

In recovery mode the recovery pod already has the data claim: run the `sh -c '…'` body below with
`oc exec -n $NS deploy/$REL-recovery -c dashboard --` (`deploy/$REL` on a chart before 0.65.0) in place of
`oc debug -n $NS deploy/$REL --one-container -c dashboard --`.
Otherwise, a helper pod with the data claim, from the Deployment's own template, with the dashboard container alone:
without `--one-container` the pod also runs the oauth-proxy sidecar, which never exits, and `oc debug` waits for every
container of its pod, so it does not return (the #300 walk waited 5 min 13 s; with the flag the lab's run returned in
3 s, exit 0, its pod removed). A body that fails makes the command fail:

```sh
oc debug -n $NS deploy/$REL --one-container -c dashboard -- sh -c '
set -e
ls -l /data /data/backup
python3.14 -c "import sqlite3,sys; c=sqlite3.connect(\"file:\" + sys.argv[1] + \"?immutable=1\", uri=True); print(c.execute(\"PRAGMA integrity_check\").fetchone()[0])" /data/backup/gsd-….db
python3.14 -c "
import pathlib, time
keep = pathlib.Path(\"/data/pre-restore\") / time.strftime(\"%Y%m%dT%H%M%SZ\", time.gmtime())
for name in (\"gsd.db\", \"gsd.db-wal\", \"gsd.db-shm\", \"gsd.db-journal\"):
    live = pathlib.Path(\"/data\") / name
    if live.is_file():
        keep.mkdir(parents=True, exist_ok=True)
        (keep / name).write_bytes(live.read_bytes())
        print(\"kept\", live, \"under\", keep)
"
cat /data/backup/gsd-….db > /data/gsd.db.restore.tmp
chgrp 0 /data/gsd.db.restore.tmp && chmod g=u /data/gsd.db.restore.tmp
rm -f /data/gsd.db-wal /data/gsd.db-shm /data/gsd.db-journal
python3.14 -c "import os; os.replace(\"/data/gsd.db.restore.tmp\", \"/data/gsd.db\")"
ls -l /data
'
```

The live **set** is kept, not `gsd.db` alone: a writer killed before a checkpoint leaves committed rows only in
`gsd.db-wal`, and a kept `gsd.db` without it counted 0 of 500 such rows where the kept set counted 500 (#302).
The copy is written under a temporary name and renamed onto `gsd.db` once the old side files are gone, so a write
that fails (a full volume, a `gsd.db` the pod cannot write) stops before anything is removed.
`-wal`, `-shm` and `-journal` **must** go: they belong to the file that was there before, and SQLite would
replay a foreign WAL, or roll a foreign hot journal back, into the restored database. `chgrp 0` + `g=u` is the arbitrary-UID rule
OpenShift runs under: the next pod may get a different UID and reads through the root group
(`local-development/Containerfile#chgrp -R 0 /data`).

### 4b. From the off-volume claim

In recovery mode the recovery pod mounts the offsite claim read-only at `/offsite` (with
`backup.offsite` on its `pvc` destination): skip the helper pod and run the `oc exec` body below against
`deploy/$REL-recovery -c dashboard` (`deploy/$REL` on a chart before 0.65.0). Otherwise, a one-off pod mounting
both claims (the `debug` pod has only the data claim). There is no `sleep`; Python idles instead:

```yaml
apiVersion: v1
kind: Pod
metadata: {name: gsd-restore, namespace: group-sync}
spec:
  restartPolicy: Never
  securityContext: {runAsNonRoot: true, seccompProfile: {type: RuntimeDefault}}
  containers:
    - name: restore
      image: <the Deployment's image>   # oc get deploy -n $NS $REL -o jsonpath='{.spec.template.spec.containers[0].image}'
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
import hashlib, pathlib, sqlite3, time
p = pathlib.Path("/offsite/gsd-….db")
h = hashlib.sha256(p.read_bytes()).hexdigest()
assert h == p.with_name(p.name + ".sha256").read_text().split()[0], "sidecar mismatch"
c = sqlite3.connect(f"file:{p}?immutable=1", uri=True)
assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
print("copy verified", h)
keep = pathlib.Path("/data/pre-restore") / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
for name in ("gsd.db", "gsd.db-wal", "gsd.db-shm", "gsd.db-journal"):
    live = pathlib.Path("/data") / name
    if live.is_file():
        keep.mkdir(parents=True, exist_ok=True)
        (keep / name).write_bytes(live.read_bytes())
        print("kept", live, "under", keep)
EOF
cat /offsite/gsd-….db > /data/gsd.db.restore.tmp
chgrp 0 /data/gsd.db.restore.tmp && chmod g=u /data/gsd.db.restore.tmp
rm -f /data/gsd.db-wal /data/gsd.db-shm /data/gsd.db-journal
python3.14 -c "import os; os.replace(\"/data/gsd.db.restore.tmp\", \"/data/gsd.db\")"
'
oc delete -n $NS pod/gsd-restore
```

For an S3 copy: download it (§3), then, in the helper pod, run the keep lines above, stream the copy in under the
temporary name — `cat gsd-….db | oc exec -i -n $NS gsd-restore -- sh -c 'cat > /data/gsd.db.restore.tmp'` — and
finish with the last three lines above: the ownership line, the `rm -f /data/gsd.db-wal
/data/gsd.db-shm /data/gsd.db-journal` line, and the rename. The order matters: the copy is whole beside `gsd.db`
before anything of the old file is removed, and a `-wal` that outlives the file it belonged to would be replayed
into the restored database.

**Both claims RWO on different nodes?** The helper pod needs both attached; if it stays Pending,
the offsite claim is attached elsewhere (a Job still running — wait for it) or the classes are
node-local. Move the file via §3 instead.

### 4c. Bring it back and verify

Turn recovery mode off (§4, step 5); on the fallback, set `replicaCount` back to its value (1) in the values file
and roll it out. The app starts on the restored file:

```sh
oc rollout status -n $NS deploy/$REL
oc exec -n $NS deploy/$REL -c dashboard -- curl -s http://127.0.0.1:8080/api/version
```

Expected: `{"leader":true,"version":"<the application version the release now runs>",…}`, the older one after a
rollback, as `gsd_build_info` on `/metrics` says too (with `oauthProxy.enabled` the app binds loopback; `curl` from
inside the pod is the honest check). Straight after a rollout it can read `"leader":false`: the replaced pod's 30 s
lease has not expired yet, and the new pod takes it when it does (about 10 s on the lab, after §4d step 6). Wait and
read again.

**The report pod stays NotReady until a new copy is written** after a restore from a newer image. The newest copy under
`/data/report` is the one the previous image wrote, and the report service refuses a snapshot newer than it
understands (`snapshot schema N is newer…`, `/report/readyz` 503). The leader's first poll after this start writes a
new copy (`gsd/poller.py#_maybe_report_snapshot`: at once on the first cycle, then every
`reporting.snapshot.intervalSeconds`), and when that write succeeds the report pod becomes Ready (measured by OB2's
composition review of Epics A and B). If it is still NotReady after the leader's first poll, no copy was written:
the leader's log says `report snapshot was not written` or `report snapshot failed`, and the next attempt waits a
full interval. Fix what that names (the volume's space or permissions) rather than waiting.

**A copy newer than the image is refused (#305).** When the restored file's `user_version` (§1) is
above the highest migration the running image carries, the dashboard does not start: the container
exits 1 before it binds its port, `oc rollout status` does not complete, and the last log line names
both numbers:

```sh
oc logs -n $NS -l app=$REL -c dashboard --previous --tail=1
```

```
gsd.store.StoreSchemaTooNew: database schema 21 is newer than this dashboard understands (20); restore a backup at or below schema 20 (charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md §4; after an upgrade, the pre-upgrade copy in §6), or deploy the image that understands 21
```

The refusal comes before this image runs any of its own schema, migrations or seeds, so the
newer build's data is kept as it was. One physical change is possible: if the copy carries a committed
`gsd.db-wal`, SQLite folds it into `gsd.db` when the refusing connection closes (a checkpoint). That
changes the file's bytes, not its contents. Turn recovery mode on
(§4) and either restore a copy whose `user_version` is at or below the second number, or deploy the
image that understands the first, by its `image.tag` in the values file. A rollback to an older image without
restoring the database first stops the same way.

Then the counts, on the live file this time (opened read-only beside the app's own connection), each up to the copy's
highest id in that table, as §1 printed it:

```sh
oc exec -n $NS deploy/$REL -c dashboard -- python3.14 -c '
import sqlite3, sys
assert len(sys.argv) == 4, "give the three highest ids of the copy, as §1 printed them"
c = sqlite3.connect("file:/data/gsd.db?mode=ro", uri=True)
for t, top in zip(("membership_event", "sync_event", "login_event"), map(int, sys.argv[1:])):
    print(t, c.execute(f"SELECT COUNT(*) FROM {t} WHERE id <= ?", (top,)).fetchone()[0], "rows up to id", top)
' <membership-highest-id> <sync-highest-id> <login-highest-id>
```

Each number must equal the copy's row count in §1. A count of the whole table does not: the leader polls as soon as it
starts, and the rows it writes take ids above every id in the copy (SQLite's `AUTOINCREMENT`), so the #300 walk read
2776 and then 2779 `sync_event` rows against the copy's 2770 while the count up to the copy's highest id stayed 2770.
A count below the copy's means rows the copy had are gone; retention pruning them (**Retention after a restore**,
below) is the one expected reason. The pod log shows `schema migration N applied` lines
only if the copy predates the running version, each after a line about the pre-upgrade copy (§6): the
copy that start wrote, or the one an earlier start of the same upgrade wrote; the first poll then
rebuilds every cache table.
`GET /api/clusters/<id>/membership-changes` should answer with the restored history and a
`retention` object.

**Retention after a restore.** If `config.retention` windows are on, the leader starts pruning
rows past the window 5,000 at a time on the first cycle after a successful backup. Restoring an
old copy to *read* its history is a reason to set both windows to `0` first, with `kyverno.eventsRetentionDays`,
which the same backup releases, and `loginCapture.retentionDays`, which prunes `login_event` without waiting for one.

### 4d. Break glass under Argo CD: pause, recovery mode by hand, give back

For an incident on a release Argo CD syncs (#533; the operator's decision of 2026-10-02). It replaces steps 1, 2 and
5 of the values-file path; the restore is the same script. Every step was walked on the CRC lab (Argo CD v3.4.7, chart
0.61.2), the restore and step 7 included (SPEC_E10's §5 walk, 2026-10-02); steps 3, 5 and 6 as chart 0.65.0 changes
them (#532) are walked by SPEC_E11's §5; the ApplicationSet case follows Argo CD's
documentation. You need the right to patch the release's Application in Argo CD's namespace, to scale the release's Deployments, and a release at one replica (recovery
mode and `restore-db.sh` need exactly one pod).

1. **Find the Application, and whether an ApplicationSet owns it.** The Deployment's tracking annotation reads
   `<APP>:apps/Deployment:<namespace>/<name>`; Argo CD's namespace is `openshift-gitops` on OpenShift GitOps:

   ````sh
   oc get deploy -n $NS $REL -o jsonpath='{.metadata.annotations.argocd\.argoproj\.io/tracking-id}{"\n"}'
   APP=<the name before the first colon>; ARGO_NS=openshift-gitops
   oc get application.argoproj.io/$APP -n $ARGO_NS -o jsonpath='{.metadata.ownerReferences[*].kind}{"\n"}'
   ````

   `ApplicationSet` in the output means a change to this Application's `spec.syncPolicy` "will, however, have no
   effect" (Argo CD, "Temporarily toggling auto-sync for applications managed by ApplicationSets"): the ApplicationSet
   puts it back unless it lists `/spec/syncPolicy` under `ignoreApplicationDifferences`. That is a change to the
   ApplicationSet, made by its owners; ask them before you go on.
2. **Pause automated sync, and confirm the pause held and no operation is running before you touch anything else:**

   ````sh
   oc patch application.argoproj.io/$APP -n $ARGO_NS --type merge -p '{"spec":{"syncPolicy":{"automated":{"enabled":false}}}}'
   oc get application.argoproj.io/$APP -n $ARGO_NS -o jsonpath='{.spec.syncPolicy.automated.enabled} {.status.operationState.phase}{"\n"}'
   ````

   It must print `false` and a phase that is not `Running`, and the same a minute later. With `enabled: false` Argo CD
   runs neither automated sync nor self-heal for this Application ("controller will skip automated sync even if
   `prune`, `self-heal` and `allowEmpty` are set"), and `prune` and `selfHeal` stay as they were for step 5. A sync
   already running is not stopped by the pause: if it fails it is retried, and each retry applies what Git renders
   over the hand edit, so the app would start on a file a restore may still be writing. With `Running`, terminate the
   operation first (step 7's command) and confirm again.
3. **Put the release into recovery mode by hand.** The chart renders the recovery Deployment, `$REL-recovery`, on
   every release at 0 replicas (chart 0.65.0 and later, #532), so the hand edit is the two `replicas` that
   `recovery.enabled: true` renders, and nothing else: the pod is the chart's own recovery pod, with the release's
   `recovery.ttl` and, on the `pvc` destination, the offsite claim at `/offsite`. The scheduler starts the recovery
   pod only once the app's pod is gone (its required pod anti-affinity), whichever command runs first:

   ````sh
   oc scale -n $NS deploy/$REL --replicas=0
   oc scale -n $NS deploy/$REL-recovery --replicas=1
   ````

   Wait until `oc get pods -n $NS -l app=$REL-recovery` shows one pod `2/2` `Running` whose log starts with
   `RECOVERY MODE` (§4 step 2). For more time, `oc rollout restart -n $NS deploy/$REL-recovery`: the new pod counts
   the TTL from its start, and the restart ends any `oc exec` in the old one.

4. **Restore** with the script, as **The script, in recovery mode** says. It accepted this pod on the lab (`recovery
   mode, at least 1h59m56s of its TTL left`), listed its copies, and restored the newest (a loss window of 5m44s, no
   rows discarded):

   ````sh
   local-development/restore-db.sh --list --namespace $NS --release $REL
   local-development/restore-db.sh --from-version <ID> --namespace $NS --release $REL
   ````

5. **Give the release back to Git.** For a rollback, first commit the older `image.tag`, and anything else the
   restored database needs, to the release's values file. Then end the pause, wait until Argo CD has applied, and
   wait for the app:

   ````sh
   oc patch application.argoproj.io/$APP -n $ARGO_NS --type json -p '[{"op":"remove","path":"/spec/syncPolicy/automated/enabled"}]'
   oc wait application.argoproj.io/$APP -n $ARGO_NS --for=jsonpath='{.status.sync.status}'=Synced --timeout=5m
   oc rollout status -n $NS deploy/$REL
   ````

   With `selfHeal: true` Argo CD puts both `replicas` back, the recovery Deployment's to 0 and the app's to 1, and
   the app starts on the restored file once the recovery pod is gone. The wait comes first because `oc rollout
   status` run before Argo CD's apply reports the app's Deployment at 0 of 0, already complete. With `selfHeal` off and Git unchanged, automated sync
   does not sync a revision it has already synced ("a second sync will not be attempted, unless `selfHeal` flag is
   set to true"): sync the Application once from Argo CD, and the wait ends when it has (not measured). The
   operator's alternative for a rollback is Argo CD's history and rollback, while still paused (Argo CD refuses it
   while automated sync is on); commit the same values to Git before you end the pause, or automated sync takes the
   release back to what Git says.
6. **Nothing to remove.** The hand edit of step 3 changed only the two `replicas` fields, which Argo CD renders and
   step 5 puts back; the release reads Synced with nothing left over. Verify with §4c.

7. **A sync that is already retrying (the endless retry in **Risks under Argo CD**, a chart before 0.65.0).** When
   recovery mode was turned on through the values file and the Application's operation reads Running with `Retrying attempt #N`, the pause
   stops new automated syncs but not that operation: Argo CD retries a failed operation whatever the sync policy says,
   up to its `limit`. On the lab, after the pause, retry #2 failed and the operation scheduled retry #3 and stayed
   Running. **Incident step:** pause (step 2), then terminate the operation, from the Application's sync status in the
   Argo CD UI or with the Argo CD CLI; a terminating operation is not retried. With the CLI logged in to Argo CD:

   ````sh
   argocd app terminate-op $APP
   ````

   Without a login, use the CLI's `--core` mode, with a CLI of the server's version (v3.4.7 on the lab): it talks to
   the Kubernetes API with your kubeconfig and reads Argo CD's namespace from the kube context, so the context must
   name `$ARGO_NS`; with another namespace it fails with `configmap "argocd-cm" not found` (measured). The first
   command writes, into a file of its own, a context that names `$ARGO_NS` and your current context's cluster and user,
   and no credentials; your kubeconfig is not changed. The component names are OpenShift GitOps's:

   ````sh
   printf 'apiVersion: v1\nkind: Config\ncurrent-context: break-glass\ncontexts:\n- name: break-glass\n  context:\n    cluster: %s\n    user: %s\n    namespace: %s\n' "$(oc config view --minify -o jsonpath='{.contexts[0].context.cluster}')" "$(oc config view --minify -o jsonpath='{.contexts[0].context.user}')" $ARGO_NS > ./argocd-context.yaml
   KUBECONFIG=./argocd-context.yaml:${KUBECONFIG:-$HOME/.kube/config} argocd --core --redis-name openshift-gitops-redis --repo-server-name openshift-gitops-repo-server --server-name openshift-gitops-server --controller-name openshift-gitops-application-controller app terminate-op $APP
   ````

   It prints `Application '<APP>' operation terminating`. On the lab the phase read `Terminating` 0.9 s after the
   command and `Failed` (`Operation terminated (retried 3 times).`) 2.08 s after it, and step 2's check then read
   `false Failed`. Not measured: whether `terminate-op` needs the four component names (a read-only `argocd app get`
   worked without them), and the UI path. The pod stays in the recovery mode the chart rendered, and steps 3 and 6 do
   not apply. Restore (step 4), commit `recovery.enabled: false` to the values file, and end the pause (step 5): with
   no operation running, automated sync takes the new revision at once. On the lab an operation started in the same
   second, the app's command was back 21.0 s after the pause ended, and the Application read Synced/Healthy 40.5 s
   after it.

## 5. Moving the data to a new claim (access mode change)

`accessModes` are immutable. Create the new claim (`persistence.existingClaim` pointing at it,
or a new release name), scale to zero, and copy `gsd.db` **only** — never `-wal`/`-shm` — with
the pattern in §4b (a helper pod with both claims), then §4c. A `-wal` with bytes beside it holds committed rows:
fold it into `gsd.db` first, with the one-liner in **Undo a restore** (§4).

## 6. Pre-upgrade copies

A new image upgrades the database it finds at startup (its schema: the tables and columns) and cannot undo that
upgrade, so the database as it was before the upgrade is the only way back to the previous image. From the
application release after 0.36.0 the dashboard takes that copy itself (`gsd/store.py#_pre_upgrade_copy`, #301),
before the new image creates a table or runs a migration. A new database, or one already at the image's schema
version, needs no copy.

* **Where.** `pre-upgrade/` beside the database: `/data/pre-upgrade/` when there is one replica, or
  `/data/<pod-name>/pre-upgrade/` when `replicaCount` is greater than 1. It is written even when scheduled
  backups are disabled, and the six-hourly rotation, the backup metric and the KPI size line never include it.
* **Off the volume.** At one replica, the offsite CronJob's `pvc` destination also receives the newest copy,
  in `/offsite/pre-upgrade/` under the same name, checked against its `.sha256` first; the newest three are
  kept there (§2). The copies of the six-hourly backups in `/offsite` never include it.
* **Name.** `pre-upgrade-<UTC stamp>-schema-<from>-to-<to>-<pod>.db`. The two numbers are database schema
  versions, not application versions, and `<pod>` is the pod that took the copy. `<from>` is the copy's schema:
  restore it under an image that understands that schema or a newer one; an older image refuses to start (§4c).
  The `.sha256` file beside it holds the checksum `sha256sum -c` verifies it with.
* **Verified before the upgrade.** Startup writes a temporary file, checks its schema version and its
  integrity, writes its checksum, saves both to disk, renames the copy into place, and only then upgrades.
* **Once per upgrade.** A later start of the same image, a restarted container or a replacement pod, does not
  copy again: a failed attempt has already committed this image's new tables and every migration before the
  one that failed, so a second copy would not be the database the previous image wrote. Its log says
  `pre-upgrade copy for schema <from> -> <to> not taken again: <file> already exists from an earlier attempt`.
  The same holds when you restore that copy and start the same image again: the copy already there is the
  database you restored. If the previous image ran on the restored database before you retry the upgrade, move
  the earlier `-to-<to>-` copy and its `.sha256` out of `pre-upgrade/` first (to `/data/pre-restore/`, for
  example), or the retry takes no copy of what that image wrote since.
* **Kept.** The copies of the newest three upgrades; an older one is removed only when a newer upgrade's copy
  has been written. `config.backup.keep` and the six-hourly rotation do not apply to them. Each takes about as
  much space as the database and counts against `persistence.size`. A cluster administrator may delete an older
  one from the KPI page's **Database copies** card (#542); the newest is always kept there.

The startup log names the copy before the first migration line, for example
`pre-upgrade copy written before migrating schema 19 -> 20: /data/pre-upgrade/pre-upgrade-….db (9973760 bytes, 0.12 s)`
and then `schema migration 20 applied: …`.

**When the copy cannot be written, the dashboard does not start.** That start upgrades nothing: the container
exits 1 before it binds its port. The last line of `oc logs -n $NS -l app=$REL -c dashboard --previous --tail=1`
names the reason and the directory, for example
`gsd.store.StorePreUpgradeCopyFailed: schema 19 -> 20: the pre-upgrade copy of /data/gsd.db could not be written to /data/pre-upgrade, so the database was not migrated: free space 40.0 MiB, database 120.0 MiB. …`.
Grow the claim or free space on it, or make the directory writable (the `oc debug` pod of §4a, `chgrp 0` and
`chmod g=u`), and the next start takes the copy and upgrades. Or deploy the previous image: a start that could
not write the copy changed nothing. A process killed while copying leaves only a temporary file, which the next
start removes.

**Using a copy.** Verify it with §1, reading `/data/pre-upgrade/<file>` instead of a backup; outside the
cluster, run `sha256sum -c <file>.sha256` from the directory that holds both files (§3). To go back to the
previous image, restore the copy with §4a from `/data/pre-upgrade/<file>` and deploy that image.
If the previous image then runs on the restored database, move the earlier `-to-<to>-` copy and its `.sha256` out of
`pre-upgrade/` before you upgrade again ("Once per upgrade" above), or the retry takes no copy of what that image
wrote since.
