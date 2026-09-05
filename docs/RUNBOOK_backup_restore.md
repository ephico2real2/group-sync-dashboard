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

Also the way to bind the destination claim right after enabling the module: on a
`WaitForFirstConsumer` StorageClass it stays Pending until the first Job mounts it, so do not
enable with `helm upgrade --wait` (it times out, and a timed-out upgrade is a failed revision whose
objects Helm does not own until the next successful one — delete them by label,
`oc delete cronjob,sa,cm -l app.kubernetes.io/component=backup-offsite`, if you need a clean slate).

```sh
oc create job -n $NS --from=cronjob/$REL-backup-offsite manual-$(date +%s)
oc logs -n $NS -l job-name=manual-<stamp> -f
```

Expected log:

```
copied /data/backup/gsd-….db -> /offsite/gsd-….db (NNN bytes, sha256 …)
integrity_check ok; user_version 9; membership_event rows N; sync_event rows M
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
python3.14 -c "
import pathlib, time
live = pathlib.Path(\"/data/gsd.db\")
if live.is_file():
    keep = pathlib.Path(\"/data/pre-restore\"); keep.mkdir(parents=True, exist_ok=True)
    (keep / (\"gsd.db.\" + str(int(time.time())))).write_bytes(live.read_bytes())
    print(\"kept the live file under /data/pre-restore\")
"
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
      image: quay.io/ephico2real/group-sync-dashboard:0.15.0   # the running tag
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

For an S3 copy: download it (§3), then, in the helper pod, run the `rm -f /data/gsd.db-wal
/data/gsd.db-shm` line FIRST, stream the copy in —
`cat gsd-….db | oc exec -i -n $NS gsd-restore -- sh -c 'cat > /data/gsd.db'` — and finish with
the ownership lines. The order matters: a `-wal` that outlives the file it belonged to would be
replayed into the restored database.

**Both claims RWO on different nodes?** The helper pod needs both attached; if it stays Pending,
the offsite claim is attached elsewhere (a Job still running — wait for it) or the classes are
node-local. Move the file via §3 instead.

### 4c. Bring it back and verify

```sh
oc scale -n $NS deploy/$REL --replicas=1
oc rollout status -n $NS deploy/$REL
oc exec -n $NS deploy/$REL -c dashboard -- curl -s http://127.0.0.1:8080/api/version
```

Expected: `{"leader": true, "version": "0.15.0", …}` (with `oauthProxy.enabled` the app binds
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
