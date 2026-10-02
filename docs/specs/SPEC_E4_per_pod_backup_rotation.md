# SPEC E4 — per-pod backup rotation: above one replica, each pod keeps its own `keep` copies and deletes no other pod's (#391)

| | |
|---|---|
| Programme | Epic E (#385), restore tools and release safety; build-order step 3 of 9. Independent of #303 and #302; it runs early so that `restore-db.sh --list` (SPEC_E3) lists the copies an operator expects |
| Batch | E — restore tools and release safety |
| Release | — (post-programme; Epic E's release, milestone 3.0.0) |
| Version on release | app 2.4.0, chart 0.60.2 |
| Version note | The next free MINOR, filled at implementation. The change is in `local-development/gsd/` (image content), so the implementing pull request runs `local-development/prepare-release.py --app <the next free MINOR> --no-commit "…"`, which also moves `appVersion` and therefore bumps the chart PATCH that the values comment, the README and the alert text need. Against `dd51b91f` (application 2.0.0, chart 0.59.25) that is app 2.1.0 and chart 0.59.26; SPEC_E3 (#302) and SPEC_E2 (#303) claim the same next numbers, so whichever merges second takes the next ones. No block carries a version field: the script writes them, as in SPEC_E3 |
| Issue | [#391](https://github.com/ephico2real2/group-sync-dashboard/issues/391) |
| Status | merged |
| Source | OB1-lite's research and specification of 2026-10-01, written before any code from the issue (its "Decisions and corrections (2026-10-01)") and the epic's "Decisions settled (2026-10-01)". Measured on main `dd51b91f` (application 2.0.0, chart 0.59.25) with Python 3.14.7 and SQLite 3.53.4 on this machine, and read-only on the CRC lab (OpenShift, image 2.0.0, Python 3.14.7, SQLite 3.53.4 in the pod). §7's blocks were cut from a copy of `dd51b91f` with the design implemented, and proved against a clean worktree of `dd51b91f` (§4.3). Revised the same day after the review of `29c67b03` by OB3 (in Grok's seat) and OB2 (in Codex's seat), on the orchestrator's decisions (Orchestrator's notes, 12), on a branch that merged main `f144a82b` (SPEC_G1, SPEC_E2 and SPEC_G2); the revised blocks are proved against `73cc7d08` and check out on `f144a82b`, which changes no file they touch |

## How to read this spec

**The point in one sentence: above one replica every pod writes its scheduled backup into the one shared
`config.backup.dir` under a name that carries the pod (`gsd-<stamp>-<pod>.db`), and rotates and reports only the
copies whose name carries exactly its own pod; at one replica nothing changes.**

§1 is the mandate. §2 is the research: each finding names its primary source, quoted, or the command that measured
it with its output. §2a is the alternatives and the reconciliation of the research with this repository's code.
§3 is the design, one rule per subsection with its reason, and the safety property as a budget with its scope (§3.6).
§4 maps every test case of the issue (T391-k) to a test and records each failing before the change and passing
after it. §5 is the walk on the lab. §6 is what an operator sees and what it costs. §7 is the whole change as
implementation blocks (`docs/specs/README.md`, "Implementation blocks"), applied to a clean tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E4_per_pod_backup_rotation.md . --apply

Line numbers into the code at `dd51b91f` are written as plain text, `file:line` without backticks, to keep them
apart from the maintained `path#anchor` citations.

## Orchestrator's notes

1. **The defect is real, re-measured on `dd51b91f`** (§2.1): two stores sharing one directory with `keep` 4 keep 2
   copies each; three stores with `keep` 2 lose a pod's only copy. The counts are the ones the issue measured on
   `5c03a9b1`.
2. **Shape A, as the issue decided** (Decisions and corrections, 2026-10-01): the pod in the file name, the same
   directory, only when `Settings.replica_count` > 1. Research confirms it (§2a): it is how restic and borg keep
   several writers apart in one repository, and it is the only shape under which the offsite CronJob's
   non-recursive glob keeps working. Shape B (a per-pod directory) is rejected with its measured cost.
3. **The owner is compared whole, never globbed (beyond the issue).** borg's own prune documentation warns: "do not
   use "foo*" if you do not also want to match "foobar"" (§2.4). A glob `gsd-*-<pod>.db` would let pod `b` rotate the copies of a
   pod named `x-b`. The name is parsed with one expression, `BACKUP_NAME`, and the field after the stamp must equal
   the pod's name (§3.2; test `test_a_pod_is_its_whole_name_not_a_suffix_of_another`).
4. **The metric masking is fixed here; the KPI size line is not, on purpose.** The issue noted that
   `gsd_backup_last_success_timestamp_seconds` reads the newest copy in the shared directory, so a replica whose
   backups fail reports its neighbour's fresh time and `GroupSyncDashboardBackupStale` cannot see it. The fix costs
   one filter through the same helper the rotation uses (§3.4), and without it the budget of §3.6 cannot be
   observed in production: the critical alert is the only signal that a replica's own copies have stopped. Each pod
   serves its own `/metrics`, so the series is already per pod. A pod with no copy of its own yet reads the whole
   directory, as today (review of this spec): every rollout renames every pod, so with "no series" there a rollout
   whose backups all fail would leave the alert nothing to fire on, where today it fires (§3.4). The Grafana
   "Backup age" panel takes `min` over the pods' series for the same reason: its red step is the alert's
   threshold, and `max` stays green while the alert fires for one stale replica. The KPI size line counts the bytes backups hold on
   the claim; the claim is shared, so every pod's copies are the right number for sizing `persistence.size`, and it
   is left as it is (T391-8). #306's backup card reads "the pod's own values" (the epic, 2026-09-26); when it shows
   a last-success time it should read it through `local-development/gsd/storage.py#backup_copies` with
   `local-development/gsd/storage.py#backup_owner`, as the metric does.
5. **Retention is released only on a copy that still exists, by construction, not by a new check.** The poller
   records `ok` when `backup()` returns a path (poller.py:1002) and retention is released on `ok`
   (poller.py:1048). Today the copy can be gone by the next neighbour's rotation; with this change no pod deletes a
   file another wrote, so the copy `ok` was set on exists until its own pod rotates it, which happens only after
   that pod has written a newer one. An existence check in `_prune_history` was considered and not added: it would
   grow the code, and it would also hold the prune when an operator moves a copy away by hand. T391-3 holds the
   property over two pollers.
6. **The pod identity is `POD_NAME`, else the hostname**, the rule `_pre_upgrade_copy` (store.py:1205), the leader
   election and the fleet backstop already use. It lives once, in `backup_owner`, which the poller and the metric
   both call; the three existing copies of the expression are not refactored here (behaviour-preserving scope).
7. **The protocol changes, and two test fakes with it.** `StorageBackend.backup` gains the keyword `owner`
   (`local-development/tests/test_storage_seam.py#test_the_declared_signatures_match_the_implementation` holds the
   protocol and `Store` equal). The fakes `FailingStore.backup` (test_metrics.py) and `_Recording.backup`
   (test_history_retention.py) accept the poller's keywords (`**kwargs`, passed through): with their fixed
   signatures the poller's `owner=` raises `TypeError`, which `_maybe_backup` catches as a failed backup, so the
   first test would still pass for the wrong reason and the second would fail. `**kwargs`, not a keyword-only
   `owner`, keeps both fakes valid on the base too (§4.2).
8. **The CRC walk needs a throwaway release at two replicas** (§5). The lab release refuses `replicaCount` > 1
   three ways (the issue's "Facts for the walk"): reporting (`charts/group-sync-dashboard/templates/_helpers.tpl#reporting.enabled=true requires replicaCount 1`), cluster-Secret writes, which the lab turns on (`environments/crc.yaml`), and a Secret-declared
   `saTokenLookup`. The throwaway release has its own namespace and release name because the chart names its
   cluster-scoped RBAC by release. The lab also has an `nfs-csi` StorageClass (`nfsvers=4.1`, measured); an
   optional second leg runs the same walk on it, because NFS is where cross-client directory caching differs (§2.2).
9. **SPEC_E3 (#302, in review) needs no code change** (§2.6, measured with its helper): its `BACKUP_NAME` lists
   `gsd-<stamp>-<pod>.db`, and its ID `<user_version>-<stamp>` stays unique per copy except when two pods stamp a
   copy in the same microsecond, where its differing-twins rule refuses the ID by name. One sentence of SPEC_E3
   §3.3 becomes incomplete ("Two files with one ID are the same name in two sources"); its orchestrator should add
   "or, above one replica, two pods' copies stamped in the same microsecond, which differ and are refused". Note 12
   of SPEC_E3 ("the ID (the stamp) is unchanged by it") holds.
10. **Collisions with the specs in flight.** SPEC_E3 edits `docs/RUNBOOK_backup_restore.md` (§4) and
    `docs/CHANGELOG.md` (`## Unreleased`); this spec edits the runbook's first bullet and the same heading. Blocks
    are re-derived from main at implementation, per `docs/specs/README.md`, "Reconciliations", rule 5; a difference
    is recorded here as a deviation. The index row this spec adds is the thirty-ninth, after SPEC_G1's, SPEC_E2's
    and SPEC_G2's, which merged first (main `f144a82b`); `local-development/tests/test_specs_index.py` counts it and
    excludes the row E4 from its rising-issue order by its id, pinned to #391, as G1 is pinned to #239, E2 to #303
    and G2 to #255: an exclusion by the number alone let a mistyped issue on E4's row pass every index test (review of this
    spec, OB3 F3 and OB2). D5's exclusion becomes the same shape, by its id and pinned to #244 (OB3 N1). SPEC_E3
    makes the same kind of edit for #302, so whichever merges second recounts, in the test and in the index's own
    "Thirty-… specifications" words, which no test reads.
11. **Open for the operator (not decided here): what bounds the copies of pods that no longer exist?** Every
    rollout renames every pod (the lab's pod is `group-sync-dashboard-7b9485f499-jspfl`, measured), so under
    "rotate only your own" a departed pod's copies are rotated by nobody: each rollout at N replicas leaves up to
    N × `keep` copies, each about the size that pod's database reached (a new pod above one replica starts an empty
    `/data/<pod>/gsd.db`, SPEC_M1 §2.5, and that file is itself never deleted). The copies written at one replica
    before a scale-up (`gsd-<stamp>.db`, no pod) are in the same position. Today's shared rotation bounds the
    directory at `keep`. The two answers:
    - **(a) accept and document it.** The blocks below are complete for (a): the runbook, the chart README and the
      values comment state the fact.
    - **(b) a neighbour also deletes another writer's copies older than a bound**, for example
      `(keep + 1) × intervalHours`. The cost: a replica whose backups fail loses its last good copies to its
      neighbours once they pass the bound, the case where copies matter most. §3.7 gives the add-on exactly: one
      function beside `backup_copies`, one loop after the own rotation, one keyword threaded through, and one
      value (off by default). It reshapes nothing the blocks below write; it edits six of their lines, each only to
      thread the keyword or import the function (§3.7).

    A data-deletion policy, so the operator's. The blocks ship (a)'s behaviour, which is also what the per-pod
    databases already do; adding (b) later reshapes nothing.

12. **The review of `29c67b03`: OB3 (in Grok's seat) and OB2 (in Codex's seat, Codex out of usage until
    2026-10-03), decided by the orchestrator on 2026-10-01.** Both held the rotation: OB3 measured 648 scenarios on
    the real `Poller`, 3,240 deletions above one replica, every one by the pod that wrote the file; OB2 measured that
    pod names which prefix each other never cross, and that one replica is unchanged. Accepted, each traced and
    applied here:
    - **F1 (OB3, required): the metric must not lose its series after a rollout.** Block 15 read only the pod's own
      copies; every rollout renames every pod, so if the new pods' backups all fail no pod exports
      `gsd_backup_last_success_timestamp_seconds` and `GroupSyncDashboardBackupStale` can never fire, where on main
      it fires (OB3's scenario S1). A pod with no copy of its own now reads the whole directory, as main does (§3.4;
      blocks 14, 15, 22, 26, 28, 29, 30). Test
      `test_above_one_replica_a_pod_with_no_copy_of_its_own_reads_the_directory`: a regression guard against main,
      and it fails on the first version's metric, `{} == {'gsd_backup_last_success_timestamp_seconds': 2000000}`
      (measured again here, on a copy with the fallback removed). What it does not cover, as on main: a replica
      that has failed since its pod started, beside a healthy one, reads its neighbour's copy (OB3's S2; a new alert
      on `gsd_backup_failures_total` would be needed, beyond this issue).
    - **F2 (OB3): the Grafana "Backup age" panel takes `min`** (blocks 31 and 32): its red step is the per-pod alert's
      threshold, and `max` stays green while the alert fires for one replica.
    - **F3 (OB3) and OB2's C6: E4 is excluded from the rising-issue order by its id and pinned to #391** (note 10).
      A mutant proves it: E4's row and header mistyped as #491 pass every index test with an id exclusion and no pin
      (82 passed), and fail with the pin.
    - **N1 (OB3, volunteered): D5 is pinned to #244 the same way.** D5's row and header mistyped as #445 passed all
      82 index tests on main's rule; with the pin, `assert '445' == '244'`.
    - **F4 (OB3): answer (b) edits six of the blocks' lines**, each only to thread its keyword or import its function;
      §3.7 and note 11 said "no line". Corrected wording, OB3's.
    - **F5 (OB3) and OB2's blocks 24 and 26: copies named without a pod are never rotated above one replica.** Both
      named the same fact; OB3's wording is taken, because it covers both sources of such copies (written at one
      replica, and written by a release before #391) where OB2's named the first.
    - **OB2: §3.6 names the mechanism** (a copy's owner is its name; a reused pod name continues its own history),
      and **§3.7's add-on unlinks with `missing_ok=True`**, because two neighbours may delete the same departed copy.
    Where the two overlapped (F3 and C6; F5 and blocks 24 and 26) one version is applied, as named above. OB2's
    hunk to §6's line counts is superseded by counts measured again on the revised blocks. Nothing was rejected.

## 1. The mandate, and what is out of scope

The issue's "What must be accomplished": the measurement recorded and made the first test (T391-1, T391-2); above
one replica each pod keeps exactly its own `keep` newest copies (T391-1); no pod deletes a backup another pod
wrote (T391-2); a copy `backup()` reported still exists after the neighbours' next backups, because `ok` releases
retention (T391-3); one replica behaves exactly as today, the name `gsd-<stamp>.db`, rotation of every `gsd-*.db`
down to `keep`, the offsite job's newest-by-name, the last-success metric, the KPI size line and the report
snapshots (T391-4 to T391-8); the runbook and the chart README's Scaling section say where each replica's copies
are and how many are kept (T391-9); and two replicas on CRC keep their own copies (T391-10). Must not change: the
single-replica backup behaviour and its file names.

Out of scope, each owned elsewhere or by design: one shared history across replicas (each replica has its own
database, `charts/group-sync-dashboard/templates/deployment.yaml#value: /data/$(POD_NAME)/gsd.db`); shipping more
than the single newest copy off the volume (#304); restoring a replica's database with #302 (recovery mode runs at
one replica, #303); the bound on a departed pod's copies (Orchestrator's notes, 11); and cleaning up a departed
pod's `/data/<pod>/` directory, which nothing does today either.

## 2. Research, measured

The probes ran with the repository's venv (Python 3.14.7, SQLite 3.53.4) against copies of `dd51b91f`, each
printing the `gsd` it imported, with `PYTHONDONTWRITEBYTECODE=1`, writing only under this spec's scratch
directory. Lab reads used `oc get` and `oc exec … ls`/`python3.14 -c` reads, nothing else. Web sources were fetched
on 2026-10-01 with `curl` and quoted from the raw text.

### 2.1 The defect, re-run on `dd51b91f`

The issue's script (measure_391.py: two `Store`s marked with their pod sharing one backup directory, `keep` 4,
four interleaved cycles; then three stores, `keep` 2, one cycle), run against this spec's base:

```text
gsd from …/wt-e4-391/local-development/gsd/__init__.py 2.0.0
cycle 0 pod-a wrote gsd-20261001T140110.101656Z.db: dir holds 1 (pod-a 1, pod-b 0)
cycle 0 pod-b wrote gsd-20261001T140110.104590Z.db: dir holds 2 (pod-a 1, pod-b 1)
cycle 1 pod-a wrote gsd-20261001T140110.107285Z.db: dir holds 3 (pod-a 2, pod-b 1)
cycle 1 pod-b wrote gsd-20261001T140110.110235Z.db: dir holds 4 (pod-a 2, pod-b 2)
cycle 2 pod-a wrote gsd-20261001T140110.113277Z.db: dir holds 4 (pod-a 2, pod-b 2)
cycle 2 pod-b wrote gsd-20261001T140110.116515Z.db: dir holds 4 (pod-a 2, pod-b 2)
cycle 3 pod-a wrote gsd-20261001T140110.119784Z.db: dir holds 4 (pod-a 2, pod-b 2)
cycle 3 pod-b wrote gsd-20261001T140110.123060Z.db: dir holds 4 (pod-a 2, pod-b 2)
returned paths that no longer exist: {'pod-a': 2, 'pod-b': 2}
3 replicas keep=2, one cycle: newest copy of each pod still exists: {'pod-a': False, 'pod-b': True, 'pod-c': True}
```

The mechanism, read at `dd51b91f`: the name carries no pod (store.py:1737,
`target = target_dir / f"gsd-{stamp}.db"`), and the rotation sorts every `gsd-*.db` in the directory and deletes
all but the newest `keep` (store.py:1758, `existing = sorted(target_dir.glob("gsd-*.db"))`). The directory is one
value for every pod (`charts/group-sync-dashboard/templates/configmap.yaml#backupDir: {{ .Values.config.backup.dir | quote }}`,
`/data/backup` in `charts/group-sync-dashboard/values.yaml#dir: /data/backup`), and above one replica every pod
polls and backs up for itself, because the chart refuses leader election there
(`charts/group-sync-dashboard/templates/deployment.yaml#replicaCount > 1 requires leaderElection.enabled=false`).

### 2.2 Two processes, one directory: what POSIX and NFS promise

**POSIX `rename()`** (pubs.opengroup.org/onlinepubs/9799919799/functions/rename.html): "if the directory entry
named by new exists, it shall be removed and old renamed to new"; "a directory entry named new shall remain visible
to other threads throughout the renaming operation and refer either to the file referred to by new or old before
the operation began"; and the rationale, "That specification requires that the action of the function be atomic."
**POSIX `unlink()`** (…/functions/unlink.html): "When the file's link count becomes 0 and no process has a reference
to the file via an open file descriptor or a memory mapping … the space occupied by the file shall be freed".

**The Linux NFS client** (`nfs(5)`, man7.org/linux/man-pages/man5/nfs.5.html): "The Linux NFS client caches the
result of all NFS LOOKUP requests"; "To detect when directory entries have been added or removed on the server,
the Linux NFS client watches a directory's mtime"; "Caching directory entries improves the performance of
applications that do not share files with applications on other clients"; and close-to-open is the default ("If
neither option is specified (or if cto is specified), the client uses close-to-open cache coherence semantics").

**What it settles.** Today two pods act on the same names: pod B's rotation lists pod A's files and unlinks them,
and on NFS that listing may be a cached one. Under the design no pod renames, unlinks or rotates a name another
pod wrote: each pod renames its own `.tmp` onto its own new name (atomic on one filesystem) and unlinks only names
that carry its own pod, which it created itself. A stale listing of a neighbour's entries changes nothing, because
those entries are never acted on. The readers (the offsite CronJob, the metric, the KPI line) only read; a reader
that opens a copy its owner then rotates keeps reading it until it closes it (the `unlink()` sentence). Nothing
here depends on cross-client directory coherence.

**The lab's volume** (read-only, 2026-10-01): the data claim is `ReadWriteMany` on `crc-csi-hostpath-provisioner`
(`kubevirt.io.hostpath-provisioner`), and inside the pod `/data` is `/dev/vda4 /data xfs rw,…,prjquota`, a local
XFS filesystem with `f_namemax` 255, not NFS. The cluster also has a StorageClass `nfs-csi` (`nfs.csi.k8s.io`,
`server: nfs-server.nfs-server.svc.cluster.local`, `mountOptions: ["nfsvers=4.1"]`, `reclaimPolicy: Retain`,
`volumeBindingMode: Immediate`), with no claim bound to it now. The chart README already warns that SQLite's WAL is
refused on NFS (`charts/group-sync-dashboard/README.md#RWX in practice usually means NFS, and SQLite refuses WAL there.`);
the backup directory is plain files and needs no locking.

### 2.3 The pod's name, and how long it can be

**Downward API** (kubernetes/website, `content/en/docs/concepts/workloads/pods/downward-api.md`): the fields
"available via either mechanism" (an environment variable or a `downwardAPI` volume) include "`metadata.name`: the
pod's name". The chart already sets it
(`charts/group-sync-dashboard/templates/deployment.yaml#fieldPath: metadata.name`, as `POD_NAME`) on every pod, at
one replica too. **Hostname** (`…/services-networking/dns-pod-service.md`): "Currently when a Pod is created, its
hostname (as observed from within the Pod) is the Pod's `metadata.name` value", so the fallback names the same pod.

**Length and characters.** kubernetes `staging/src/k8s.io/apiserver/pkg/storage/names/generate.go` at
`44da5344`, lines 37-54: the generator "returns the name plus a random suffix of five alphanumerics … guaranteed to
not exceed the length of a standard Kubernetes name (63 characters)" (`maxNameLength = 63`, `randomLength = 5`).
A Deployment's pod is named that way. Object names are DNS subdomains ("contain no more than 253 characters",
`…/working-with-objects/names.md`): lowercase alphanumerics, `-` and `.`, never `/`. The longest name this design
writes is `gsd-` (4) + the stamp (23) + `-` (1) + 63 + `.db.tmp` (7) = 98 bytes, under the lab's `f_namemax` 255.
SPEC_M1 already writes the same pod name into the pre-upgrade copy's name.

**On the lab** (read-only): `POD_NAME=group-sync-dashboard-7b9485f499-jspfl`, and `socket.gethostname()` returns
the same string.

### 2.4 How other backup tools keep several writers apart

**restic** (`doc/060_forget.rst`, restic master): "When `forget` is run with a policy, restic first loads the list
of all snapshots and groups them by their host name and paths … The policy is then applied to each group of
snapshots individually. This is a safety feature to prevent accidental removal of unrelated backup sets. To disable
grouping and apply the policy to all snapshots regardless of their host, paths and tags, use `--group-by ''`."

**borg** (`docs/usage/prune.rst`, branch 1.4-maint): "By default, prune applies to **all archives in the
repository** unless you restrict its operation to a subset of the archives using `--glob-archives`. When using
`--glob-archives`, be careful to choose a good matching pattern — for example, do not use "foo*" if you do not also
want to match "foobar"." Its examples prune "only … archive names starting with the hostname of the machine
followed by a "-" character", `--glob-archives='{hostname}-*'`, and the `borg create` help's examples
(src/borg/archiver.py) name archives `{hostname}-{now:%Y-%m-%d_%H:%M:%S}`.

**Velero** (`site/content/docs/main/how-velero-works.md`): "When you create a backup, you can specify a TTL (time
to live) by adding the flag `--ttl <DURATION>`. If Velero sees that an existing backup resource is expired, it
removes:" the backup resource, its file in object storage, its volume snapshots and its restores; "If not specified, a default TTL value of 30 days will be applied", applied "when the gc-controller
runs its reconciliation loop every hour by default".

**What it settles.** Both file-level tools put the writer's identity on the copy and apply the count policy per
writer, which is shape A; restic calls the per-writer grouping "a safety feature to prevent accidental removal of
unrelated backup sets", the defect here. borg's own warning is why the owner is matched whole (Orchestrator's
notes, 3). Velero's age-based expiry is the model for answer (b) of note 11.

### 2.5 `VACUUM INTO`: what the output file must be

SQLite, "VACUUM" (sqlite.org/lang_vacuum.html, last updated 2025-07-12): "If the INTO clause is included, then the
original database file is unchanged and a new database is created in a file named by the argument to the INTO
clause"; "The file named by the INTO clause must not previously exist, or else it must be an empty file, or the
VACUUM INTO command will fail with an error"; "The VACUUM INTO command is transactional in the sense that the
generated output database is a consistent snapshot of the original database." **What it settles** (from the
code, not measured): two pods stamping `gsd-<stamp>.db` in the same microsecond would target one `<name>.tmp`
(`_vacuum_into` writes there, then renames), and the second `VACUUM INTO` would fail on the first's file. With
the pod in the name the targets differ, so that collision cannot happen above one replica; at one replica a single process writes, as today.

### 2.6 Every reader of `config.backup.dir`, and SPEC_E3, against the new names

| reader | what it reads at `dd51b91f` | after this change |
|---|---|---|
| the rotation, `Store._vacuum_into` | `sorted(target_dir.glob("gsd-*.db"))`, all but the newest `keep` deleted (store.py:1758) | at one replica and for report snapshots the same list (`backup_copies(dir, None)`); above one replica the copies whose name carries exactly this pod |
| the offsite script, `charts/group-sync-dashboard/scripts/offsite_backup.py#newest_backup` | `PATTERN = "gsd-*.db"`, non-recursive, newest by name, `--source` = `config.backup.dir` | unchanged: per-pod names match the pattern and sort by their leading stamp across pods, so it ships the newest copy, one replica's (T391-6) |
| `gsd_backup_last_success_timestamp_seconds` (metrics.py:815) | newest mtime of every `gsd-*.db` | at one replica the same; above one replica this pod's own copies (Orchestrator's notes, 4) |
| the KPI size line, `local-development/gsd/kpi/system.py#dashboard_data_bytes` | count and bytes of every `gsd-*.db` | unchanged: every pod's copies, the bytes on the shared claim (T391-8) |
| the report service, `local-development/gsd/reporting/snapshot.py#_STAMP` | `/data/report`, `^gsd-(\d{8}T\d{6}\.\d{6}Z)\.db$` | unchanged: snapshots never carry a pod (T391-5); reporting is refused above one replica anyway |
| SPEC_E3's restore-db.py, `BACKUP_NAME` | `gsd-(\d{8}T\d{6}\.\d{6}Z)(?:-[^/]+)?\.db`, ID `<user_version>-<stamp>` | lists per-pod names; IDs unique except the same-microsecond case, refused (below) |

**SPEC_E3, measured.** Its helper was cut from its create block (`git show 167ecb9b:docs/specs/SPEC_E3_restore_db.md`,
block local-development/restore-db.py) and its `catalogue` run over a directory written by this spec's `Store`:
two pods with two copies each, and a third copy of one pod given the stamp of the other pod's first copy, to stand
for two pods stamping a copy in the same microsecond:

```text
files 5 IDs 4
ID 20-20261001T141208.936382Z ['group-sync-dashboard-7b9485f499-jspfl.db', 'group-sync-dashboard-7b9485f499-x2k9q.db'] differ True
ID 20-20261001T141208.939133Z ['group-sync-dashboard-7b9485f499-jspfl.db'] differ False
ID 20-20261001T141208.946717Z ['group-sync-dashboard-7b9485f499-x2k9q.db'] differ False
ID 20-20261001T141208.948822Z ['group-sync-dashboard-7b9485f499-x2k9q.db'] differ False
refused: 20-20261001T141208.936382Z names copies that differ: …
```

Every copy lists; four distinct stamps give four IDs; the shared stamp gives one ID naming both files, which
`checked` refuses by name, so the tool never restores the wrong pod's copy. The same-microsecond case was
constructed, not observed: each pod takes its stamp from its own clock once per `intervalHours`.

### 2.7 The lab today (read-only, 2026-10-01)

`oc get deploy -n group-sync-dashboard group-sync-dashboard`: `replicas 1`, strategy `Recreate`. `ls -l /data/backup`
in the pod: four copies, `gsd-20260930T230906.692903Z.db` to `gsd-20261001T111104.000930Z.db`, 14,184,448 to
14,221,312 bytes. PVCs: `group-sync-dashboard-data` `f065b7a4-535c-4ef1-868c-58f5afee4953` (`ReadWriteMany`,
`crc-csi-hostpath-provisioner`, 119Gi) and `group-sync-dashboard-report-artifacts`
`08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`.

## 2a. Alternatives considered

| option | source | what it would cost here | decision |
|---|---|---|---|
| **A. The pod in the name, same directory, owner compared whole** | restic's per-host grouping, borg's `{hostname}-` archive prefix (§2.4); the issue's decision | four small code changes, two fakes, docs; one replica byte-identical | **chosen** |
| B. A per-pod directory, `/data/<pod>/backup` beside `pre-upgrade/` | the issue's table; SPEC_M1 §3.1 | breaks the offsite CronJob above one replica: its glob is non-recursive and its `--source` is `config.backup.dir`, so it finds nothing and fails "no gsd-*.db under …" (`charts/group-sync-dashboard/scripts/offsite_backup.py#newest_backup`); restore-db.sh (SPEC_E3) would need a new source; `config.backup.dir` would stop meaning where the copies are | rejected |
| C. Match the owner with a glob, `gsd-*-<pod>.db` | — | pod `b` rotates pod `x-b`'s copies, the trap borg's docs name (§2.4) | rejected; `BACKUP_NAME` and a whole-field comparison |
| D. Only one pod backs up (leader election, or a lease on the directory) | — | above one replica each pod has its own database, so the others' histories would have no copy; the chart refuses election above one replica | rejected |
| E. Age-based retention for everyone (a TTL, as Velero) | Velero (§2.4) | changes `keep`'s meaning at one replica, which must not change; a stalled writer loses its copies | rejected as the rule; kept as answer (b) for departed pods only (§3.7) |
| F. Remember the paths this process wrote, in memory | — | a container restart keeps the pod's name but loses the list, so earlier copies would never be rotated | rejected; the name is durable |
| G. Re-check that the copy exists before pruning | the issue's item 4 | grows `_prune_history`; holds the prune when a copy is moved by hand; unnecessary once no neighbour deletes the copy | rejected (Orchestrator's notes, 5) |

**Reconciliation, research against this repository's code:**
- POSIX `rename()` is atomic on one filesystem: the copy is written as `<name>.tmp` and renamed with `os.replace`
  inside `Store._vacuum_into` (`local-development/gsd/store.py#Store._vacuum_into`), unchanged; the only change is
  that `<name>` carries the pod above one replica, so two pods never rename onto one name.
- restic's "groups them by their host name … applied to each group … individually": `backup_copies(dir, owner)`
  (`local-development/gsd/storage.py#backup_copies`) is that group, and `Store._vacuum_into` applies `keep` to it.
- borg's "do not use "foo*" if you do not also want to match "foobar"": `BACKUP_NAME`
  (`local-development/gsd/storage.py#BACKUP_NAME`) captures the whole field after the stamp and `backup_copies`
  compares it with `==`.
- The downward API's `metadata.name` is `POD_NAME`
  (`charts/group-sync-dashboard/templates/deployment.yaml#fieldPath: metadata.name`), read by `backup_owner`
  (`local-development/gsd/storage.py#backup_owner`) with the hostname fallback the DNS page guarantees is the same
  name, the expression `_pre_upgrade_copy` uses (`local-development/gsd/store.py#_pre_upgrade_copy`).
- `VACUUM INTO` refuses an existing target: the per-pod name means two pods never target one file; the existing
  `.tmp`-then-rename and the microsecond stamp are unchanged.
- The non-recursive `glob(PATTERN)` of the offsite script
  (`charts/group-sync-dashboard/scripts/offsite_backup.py#newest_backup`) still sees every per-pod copy because
  they stay in `config.backup.dir` under `gsd-*.db`; name order is stamp order because the stamp leads the name
  and is fixed width (`%Y%m%dT%H%M%S.%fZ`).

## 3. The design

### 3.1 The name

At one replica: `gsd-<stamp>.db`, exactly as today. Above one replica: `gsd-<stamp>-<pod>.db`, for example
`gsd-20261001T111104.000930Z-group-sync-dashboard-7b9485f499-jspfl.db`. The stamp first, so name order stays time
order across every pod and every reader that sorts by name keeps working (§2.6); the pod after it, so the copies
stay inside the `gsd-*.db` pattern that the offsite job, the metric, the KPI line and SPEC_E3 read. Only
`backup()` passes an owner; `snapshot()` shares `_vacuum_into` and passes none, so report snapshots keep their
`_STAMP` name (T391-5).

### 3.2 Whose copies: `BACKUP_NAME`, `backup_owner`, `backup_copies`

Three names in `local-development/gsd/storage.py`, the module the store, the poller and the metrics collector
already import (the engine-neutral contract module; nothing in them names the engine,
`local-development/tests/test_storage_seam.py#test_no_module_imports_a_database_driver`):

- `BACKUP_NAME = re.compile(r"gsd-(\d{8}T\d{6}\.\d{6}Z)(?:-(.+))?\.db")`, matched with `fullmatch`. The stamp
  holds no `-`, so group 2 is the whole field after the stamp's `-`, or `None` for the one-replica name.
- `backup_owner(replica_count)`: `None` when `replica_count <= 1`; otherwise `POD_NAME`, else the hostname.
- `backup_copies(directory, owner)`: every `gsd-*.db`, sorted by name, when `owner` is `None` (today's list,
  whatever follows the stamp); otherwise only the names that `BACKUP_NAME` matches and whose group 2 equals
  `owner`.

`Settings.replica_count` is the chart's `replicaCount`, rendered on every install
(`charts/group-sync-dashboard/templates/configmap.yaml#replicaCount: {{ int .Values.replicaCount }}`, read at
config.py:1806, default 1), so no chart template changes.

### 3.3 The rotation

`Store.backup(directory, keep=3, *, owner=None)` passes `owner` to `_vacuum_into`, which names the copy (§3.1) and
rotates `backup_copies(directory, owner)` down to `keep` instead of every `gsd-*.db`. The poller passes
`owner=backup_owner(self.settings.replica_count)` (`local-development/gsd/poller.py#Poller._maybe_backup`).
Nothing else in `_vacuum_into` moves: the `.tmp` and the rename, the failure path returning `None`, the
`keep == 0` keeps-everything rule, and the log line, whose count is now the pod's own (`backup written to … (4
kept)`).

### 3.4 The metric

`gsd_backup_last_success_timestamp_seconds` reads `backup_copies(backupDir, backup_owner(replica_count))`: every
copy at one replica as today, this pod's own above one. `replica_count` is read with
`getattr(self.settings, "replica_count", 1)`, the module's own convention for optional settings
(`getattr(self.settings, "login_capture_enabled", False)` and `getattr(self.settings, "fleet_ping_enabled", None)`
in the same collector), so a collector given a settings object without
the field reads it as one replica, today's behaviour.

**A pod with no copy of its own reads the whole directory, as before this change**
(`backup_copies(backupDir, owner) or backup_copies(backupDir, None)`). Above one replica every rollout renames
every pod, so after a rollout no pod has a copy of its own until its first backup succeeds. Were that "no
series", a rollout whose backups all fail would leave `GroupSyncDashboardBackupStale` nothing to fire on, where
today the newest copy in the directory ages and the alert fires (review of this spec, measured: two replicas, the
departed pods' copies 13 hours old, every new pod's backup failing; on `21132a25` both pods' series are 13 hours
old and the rule's condition holds, with the own-copies-only reading neither pod has a series). With the
fallback the alert sees everything it sees today, plus a replica whose own copies have stopped beside a healthy
one; a replica that has never written a copy since its pod started still reads its neighbours' newest, as today.
No copy in the directory at all: no series, the same "absent, never zero" rule the metric already follows. The
alert's comment and description in `charts/group-sync-dashboard/templates/monitoring.yaml` say which copy it
measures.

**The Grafana "Backup age" panel takes `min`, not `max`.** Its red step is the alert's threshold
(`local-development/tests/test_chart_grafana_dashboard.py#TestTheFile.test_panel_thresholds_equal_the_shipped_alert_thresholds`
holds them equal), and the alert is per series, so per pod. With per-pod series,
`time() - max(gsd_backup_last_success_timestamp_seconds)` is the freshest replica and stays green while the alert
fires for a stale one; `min` is the stalest replica, so the panel turns red when the alert's condition holds for
any pod. At one replica `min` and `max` of the one series are the same number.

### 3.5 What does not change

The one-replica name and rotation; `snapshot()` and `_STAMP`; the offsite script; the KPI line; the pre-upgrade
copy; the chart's templates other than the alert's text; the Grafana dashboard other than the "Backup age" panel
(§3.4); every rendered RBAC rule (§4.3); `config.backup.*` and their defaults. No value is added.

### 3.6 The budget, over the system, with its scope

Scope: one release, one `config.backup.dir`, the pods of one ReplicaSet running this change with the same
`replicaCount`. `keep` > 0 (with `keep: 0` nothing is ever rotated, as today).

- **Above one replica, each live pod keeps exactly `min(copies it has written, keep)` of its own copies, and no pod
  deletes a file it did not write.** Mechanically: no pod deletes a copy whose name carries another pod, or no
  pod. A copy's owner is its name, never the process that wrote it, and the same name is what names the pod's
  database (`/data/<pod>/gsd.db`), so a pod name seen again (a container restart, or a replacement that drew the
  same name) continues the same history and rotates its earlier copies; a file an operator places in the
  directory under a live pod's name is that pod's to rotate (review of this spec, OB2).
- **At one replica, the directory holds at most `keep` copies**, as today.
- **The copy `backup()` returned exists until its own pod has written `keep` newer ones**, so the `ok` that
  releases retention is always backed by a copy on the volume (until an operator removes it by hand).

The table, by event (each row measured by the named test, or stated from the code where it says so):

| event | what is deleted | evidence |
|---|---|---|
| two pods, `keep` 4, six cycles each | each pod's own beyond 4; 4 + 4 remain | T391-1 (`{'pod-a': 4, 'pod-b': 4}`) |
| three pods, `keep` 2, one cycle | nothing; each returned copy exists | T391-2 |
| two pollers, `keep` 1, backup then prune each | each pod's own beyond 1; both pruned rows are in a copy | T391-3 (`[5, 7]`) |
| a container restart (same pod name) | the pod's own beyond `keep`, its earlier copies included | from the code: the owner is the name, not the process |
| a rollout at the same `replicaCount` > 1 | nothing of the old pods; the new pods start their own | from the code; old pods' copies stay (note 11) |
| a pod named `x-b` beside a pod `b` | neither touches the other's | `test_a_pod_is_its_whole_name_not_a_suffix_of_another` |
| one replica, six backups, `keep` 3 | all but 3, names without a pod | T391-4 |
| scale 2 → 1 (Recreate: every old pod stops first) | the one-replica pod's next backup keeps `keep` of every `gsd-*.db`, so the per-pod copies go | from the code (`backup_copies(dir, None)`); stated in the docs |

**Outside the scope, named:** (1) a rollout that changes `replicaCount` from 1 to more than 1 runs as `RollingUpdate`
(the chart derives it above one replica, `charts/group-sync-dashboard/templates/deployment.yaml#ternary "RollingUpdate" "Recreate"`),
so the outgoing one-replica pod, still carrying today's rule, keeps running until the new pods are ready; if its
`intervalHours` backup falls in that window, its rotation keeps `keep` of every `gsd-*.db` and can delete the new
pods' first copies. (2) The same holds for the first rollout of an image without this change to one with it above
one replica: the outgoing pods carry today's rule. Both windows last until the new pods are ready, and a pod backs
up once per `intervalHours` (6 by default). Not measured; the walk's step 2 starts the release at two replicas, so
it does not cross either.

### 3.7 Answer (b), if the operator chooses it: the add-on, and why nothing above is reshaped

Not applied by this spec. If the operator answers (b), the add-on is: one function in
`local-development/gsd/storage.py` beside `backup_copies`, using the same `BACKUP_NAME`; one keyword on `backup()`
and `_vacuum_into` (`departed_before: datetime | None = None`); after the own rotation in `_vacuum_into`, when
`owner is not None and departed_before is not None`, `unlink(missing_ok=True)` each path `departed_copies`
returns (two neighbours may delete the same departed copy in the same interval; review of this spec, OB2); one value,
`config.backup.departedMaxAgeHours` (0, off, by default; refused below `(keep + 1) × intervalHours` so a healthy
pod's oldest copy is never inside the bound), rendered into the ConfigMap and read into `Settings`; and the poller
passing `datetime.now(UTC) - timedelta(hours=…)`. The function, run on sample names (pod-a at `now` = 2026-10-01
12:00Z, bound (4 + 1) × 6 h):

```text
def departed_copies(directory, owner: str, older_than: datetime) -> list[Path]:
    """Answer (b) only: copies another writer left (another pod, or the one-replica name), stamped before
    older_than. The stamp is read from the name, never the mtime, which a copy tool may reset."""
    found = []
    for path in sorted(Path(directory).glob("gsd-*.db")):
        match = BACKUP_NAME.fullmatch(path.name)
        if match is None or match.group(2) == owner:
            continue
        if datetime.strptime(match.group(1), "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=UTC) < older_than:
            found.append(path)
    return found

['gsd-20260929T200000.000000Z-old-pod.db', 'gsd-20260929T200000.000000Z.db', 'gsd-20260930T050000.000000Z-pod-b.db']
```

(pod-a's own 40-hour copy, pod-b's 10-hour copy and a `gsd-junk.db` were not returned.) It reshapes nothing the
blocks below write: `backup_copies`, `BACKUP_NAME`, the owner rule, the name and the metric stay, and the add-on
only adds a second pass. It does edit six of their lines, each only to thread the keyword or import the function
(measured in review: the add-on applied to the applied tree, and the storage-seam test passes with the protocol
line edited): the protocol's `backup` (block 2), the store's import (block 4), `Store.backup`'s signature and its
call of `_vacuum_into` (blocks 5 and 6), `_vacuum_into`'s signature (block 7) and the poller's call (block 11).
Under (b) the docs' sentence "stay until they are removed by hand" becomes "are deleted by a
neighbour once older than `departedMaxAgeHours`". Its cost, again: a live replica whose backups have failed for
longer than the bound loses its last good copies; `_backup_state` is then `failed`, so its retention is already
held and no history is deleted on top.

## 4. Tests

### 4.1 One test per issue test case

| ID | test (file) | fails without the change because |
|---|---|---|
| T391-1 | `test_two_replicas_sharing_one_directory_each_keep_their_own_keep` (`tests/test_backup.py`) | every rotation deletes by the bare pattern: `{'pod-a': 2, 'pod-b': 2} != {'pod-a': 4, 'pod-b': 4}` |
| T391-2 | `test_no_replica_deletes_a_copy_it_did_not_write` (`tests/test_backup.py`) | pod C's rotation deletes pod A's only copy: `'pod-a': False` |
| T391-3 | `TestPollerPrune.test_a_replica_prunes_only_while_its_own_copy_exists` (`tests/test_history_retention.py`) | pod A pruned on `ok`, then pod B's rotation deleted A's copy: the copies hold `[7]`, not `[5, 7]` |
| T391-4 | `test_one_replica_keeps_the_name_and_the_rotation` (`tests/test_backup.py`) | a regression guard: passes before and after |
| T391-5 | `test_report_snapshots_keep_their_name_with_a_pod_set` (`tests/test_backup.py`) | a regression guard: passes before and after |
| T391-6 | `TestShip.test_above_one_replica_the_newest_copy_is_still_found_and_shipped` (`tests/test_offsite_backup_script.py`) | a regression guard: passes before and after; it would fail under shape B |
| T391-7 | `TestCaptureAndBackupGauges.test_at_one_replica_the_backup_timestamp_reads_every_copy` (`tests/test_metrics.py`); `test_backup_timestamp_reads_the_newest_file` is kept | a regression guard: passes before and after |
| T391-8 | `TestCgroupSampler.test_the_backup_size_line_counts_every_replicas_copies` (`tests/test_kpi.py`) | a regression guard: passes before and after |
| T391-9 | `test_the_docs_say_where_each_replicas_copies_are` (`tests/test_backup.py`) | the runbook names one directory and one `keep`; Scaling and the values comment say nothing of replicas' copies |
| T391-10 | the lab walk (§5) | not a hermetic test |
| research | `TestCaptureAndBackupGauges.test_above_one_replica_the_backup_timestamp_is_this_pods_own` (`tests/test_metrics.py`) | the metric reads the newest copy of any pod, 3,000,000 (`x-pod-a`'s), not pod-a's own 1,000,000 (Orchestrator's notes, 4) |
| research | `test_a_pod_is_its_whole_name_not_a_suffix_of_another` (`tests/test_backup.py`) | `backup_copies` does not exist (`ImportError`); it pins the whole-field comparison (notes, 3) |
| review | `TestCaptureAndBackupGauges.test_above_one_replica_a_pod_with_no_copy_of_its_own_reads_the_directory` (`tests/test_metrics.py`) | a regression guard: passes before and after; it fails on a metric that reads only the pod's own copies with no fallback, which leaves no series after a rollout (§3.4) |
| review | `TestTheFile.test_backup_age_reads_the_stalest_replica` (`tests/test_chart_grafana_dashboard.py`) | the panel reads `max`, the freshest replica, so it stays green while the per-pod alert fires (§3.4) |

T391-1, T391-2 and T391-6 drive the poller (`Poller._maybe_backup`) with `Settings(replica_count=…)` and
`POD_NAME` set per pod, which is where the pod's identity meets `Store.backup`, and read each copy's owner from a
marker table inside the copy, never from the file name under test. The helpers live in `tests/test_backup.py` and
are imported inside the one test of `tests/test_offsite_backup_script.py` that uses them, so that module still
collects on a tree without them.

### 4.2 Each test, before and after

**Before:** a copy of `73cc7d08` with only the nine test blocks of §7 applied (blocks 16 to 23 and 32; no code, no
docs), the six touched test files run with that copy's `gsd` imported (the review measured the same on `dd51b91f`
and `21132a25`):

```text
FAILED tests/test_backup.py::test_two_replicas_sharing_one_directory_each_keep_their_own_keep
FAILED tests/test_backup.py::test_no_replica_deletes_a_copy_it_did_not_write
FAILED tests/test_backup.py::test_a_pod_is_its_whole_name_not_a_suffix_of_another
FAILED tests/test_backup.py::test_the_docs_say_where_each_replicas_copies_are
FAILED tests/test_history_retention.py::TestPollerPrune::test_a_replica_prunes_only_while_its_own_copy_exists
FAILED tests/test_metrics.py::TestCaptureAndBackupGauges::test_above_one_replica_the_backup_timestamp_is_this_pods_own
FAILED tests/test_chart_grafana_dashboard.py::TestTheFile::test_backup_age_reads_the_stalest_replica
7 failed, 177 passed, 1 skipped, 2 warnings in 7.72s
```

Each for the reason §4.1 states; the assertion lines, in the same order:

```text
AssertionError: assert {'pod-a': 2, 'pod-b': 2} == {'pod-a': 4, 'pod-b': 4}
{'pod-a': False} != {'pod-a': True}
ImportError: cannot import name 'backup_copies' from 'gsd.storage'
AssertionError: runbook / assert 'gsd-<UTC stamp>Z-<pod name>.db' in 'Runbook — backing up and restoring …'
assert [7] == [5, 7]
{'gsd_backup_last_success_timestamp_seconds': 3000000.0} != {'gsd_backup_last_success_timestamp_seconds': 1000000}
assert ['time() - max(gsd_backup_last_success_timestamp_seconds)'] == ['time() - min(gsd_backup_last_success_timestamp_seconds)']
```

The regression guards T391-4 to T391-8, the review's fallback test and every existing test in the six files are
among the 177 that pass before the change. The two fakes take `**kwargs` (blocks 18 and 21) so that they are valid
on both trees; with a keyword-only `owner` instead, the first run of this proof failed five existing retention
tests on the base, which is how that shape was rejected. The fallback test passes on the base because the base
reads the whole directory; it fails, `{} == {'gsd_backup_last_success_timestamp_seconds': 2000000}`, on a metric
that reads only the pod's own copies with no fallback, the shape this spec first had.

**After:** the whole spec applied (§4.3), the same six files and the seam test:

```text
tests/test_backup.py tests/test_history_retention.py tests/test_offsite_backup_script.py tests/test_metrics.py tests/test_kpi.py tests/test_chart_grafana_dashboard.py
184 passed, 1 skipped, 2 warnings in 7.06s
tests/test_storage_seam.py
152 passed in 0.68s
```

### 4.3 The proof

§7 was not written by hand. The design was implemented in a copy of `dd51b91f`; a generator cut each block's Old
text from the base and its New text from the implemented copy, at whole lines, widened upward until the Old text
occurs once and holds two non-blank lines, and checked that each file's blocks, applied in order, give the
implemented file. Then, on a clean `git worktree add --detach … dd51b91f`:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E4_per_pod_backup_rotation.md <worktree>
    32 blocks check out across 16 files
    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E4_per_pod_backup_rotation.md <worktree> --apply

After `--apply`, `cmp` finds every one of the 14 changed files of the first 30 blocks identical to the implemented
copy; blocks 14, 15, 22, 24, 26, 28 to 30 were corrected and 31 and 32 added in review, and the corrected spec checks
out the same way against `dd51b91f`, `21132a25`, `73cc7d08` and `f144a82b` (32 blocks, 16 files; on `73cc7d08` and
`f144a82b`, `cmp` finds all 16 applied files identical to the implemented copy). The checks below are on a copy
of `73cc7d08` (SPEC_G1 and SPEC_E2 merged) with the revised blocks applied, `PYTHONPATH` at its `local-development`
(`gsd` imported from the copy, version 2.0.0):

| check | command | result |
|---|---|---|
| hermetic suite | `pytest tests/ -q -p no:cacheprovider --deselect tests/test_ui.py --deselect tests/test_live_smoke.py` | `6232 passed, 26 skipped, 655 deselected, 5 xfailed`, no failure. Against the base, `pytest --co` adds the thirteen new tests (the eleven of the first version and the two the review added); the rest of the difference is the citation, index and fence cases that this spec's file and index row bring (`test_docs_citations.py`, `test_specs_index.py`, `test_docs_diagrams.py`), and twelve citation ids whose line numbers moved in the runbook and the CHANGELOG |
| the base, for comparison | the same run on a clean worktree of `73cc7d08` | `6190 passed, 26 skipped, 655 deselected, 5 xfailed` (the first version, on `dd51b91f`: `6126` before, `6137` after) |
| chart | `helm lint`; `helm template` of `73cc7d08` and of the applied chart, diffed, with default values, with the walk's values (§5), and with `monitoring.prometheusRule.enabled=true` | lint clean; in all three renders 12 lines differ and only these: the alert's comment (one line becomes three) and description (one line becomes three), and the dashboard ConfigMap's "Backup age" panel (its description and its expression, `max` to `min`); the config checksum and every label are unchanged |
| RBAC | `reports/2026-09-27_epic-c-walk/scripts/rbac_rules.py` on the same three pairs of renders | 59 → 59, 56 → 56 and 59 → 59 rules; REMOVED 0, ADDED 0 in each |
| the alert | the rendered `PrometheusRule` parsed with PyYAML | `description` reads `The newest backup in backupDir (above one replica, the newest this pod wrote, or the directory's newest until it has written one) is {{ $value \| humanizeDuration }} old — at least two backup intervals. …` |
| Python 3.11 | `ast.parse(source, feature_version=(3, 11))` on the ten changed Python files | all parse |
| markdown | `markdownlint-cli2` on the runbook, the CHANGELOG and the chart README, base and applied | 17 findings before and after, the same per file and rule (MD004 9, MD040 7, MD012 1), all on main already; none new |
| this spec | `pytest -q tests/test_specs_index.py tests/test_docs_citations.py` in the spec's own worktree | on this revision, merged with `f144a82b` (the index at thirty-nine rows; E4 and D5 excluded from the rising-issue order by their ids and pinned, Orchestrator's notes, 10): `1573 passed, 22 skipped`; the first version, at `29c67b03`, `1474 passed, 18 skipped` |
| the index pins | mutants of `docs/specs/README.md` and the spec headers, `test_specs_index.py` | E4's row and header mistyped as #491: 82 passed with an id exclusion and no pin, 1 failed with the pin; D5's as #445: 82 passed on main's rule, 1 failed with the pin (`assert '445' == '244'`) |

The browser suite was not run: no block touches `gsd/static/` or an API response.

### 4.4 The probes

Not committed; described to be repeated. The defect run is the issue's measure_391.py, unchanged, against
`dd51b91f` (§2.1). SPEC_E3's helper was cut from `git show 167ecb9b:docs/specs/SPEC_E3_restore_db.md` with
`apply-spec-blocks.py`'s own `blocks()` parser, loaded with `importlib`, and run with `GSD_DB_PATH` and
`GSD_BACKUP_DIR` pointing at a scratch directory written by the implemented `Store` (§2.6). The add-on of §3.7 was
run against the implemented `gsd.storage` on seven sample names.

## 5. On the lab (the implementing pull request)

**Measured now, read-only (2026-10-01):** §2.2 (the data claim is XFS on the node; `nfs-csi` exists) and §2.7
(the lab release runs one replica, `Recreate`, four copies of about 14.2 MB, the two PVC UIDs).

**The walk, T391-10, for the implementer: development, on the lab, so the CLI is used.** The lab release cannot
run two replicas (Orchestrator's notes, 8), so the walk installs a throwaway release with its own namespace and
release name and removes it at the end. It runs after the merge, on the published image: the chart at the merge
commit deploys `quay.io/ephico2real/group-sync-dashboard:<appVersion>` by default, so the evidence is pinned to the
merge sha as the issue's Definition of Done asks.

1. Record the lab release's PVC UIDs:
   `oc get pvc -n group-sync-dashboard -o custom-columns=NAME:.metadata.name,UID:.metadata.uid`; expect
   `f065b7a4-535c-4ef1-868c-58f5afee4953` and `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`.
2. The throwaway values file, `reports/<date>_backup-per-replica-391/walk-391-values.yaml` (rendered on the applied
   tree, §4.3: two replicas, `/data/$(POD_NAME)/gsd.db`, `backupIntervalHours: 0.02`, `replicaCount: 2`):

   ```yaml
   # T391-10 (#391): a throwaway release at two replicas. Development only: the lab release refuses
   # replicaCount > 1 (reporting, cluster-Secret writes, saTokenLookup), so the walk runs its own release.
   replicaCount: 2
   leaderElection:
     enabled: false
   reporting:
     enabled: false
   clusterConfig:
     secrets:
       writes:
         enabled: false
   config:
     backup:
       intervalHours: 0.02
       keep: 4
   ```

   Install it from the merge commit's chart:
   `helm install gsd391 charts/group-sync-dashboard -n gsd-391-walk --create-namespace -f reports/<date>_backup-per-replica-391/walk-391-values.yaml`.
   Its data claim is `ReadWriteMany` on the default class, `crc-csi-hostpath-provisioner`.
3. Wait for twelve backups, six per pod, with one waiter on the log lines of both pods. The render declares one
   cluster (`dashboard`) polled every 60 s, and the backup is checked at the end of each poll once 72 s have
   passed, so a pod should back up about every 120 s, about 12 minutes for six (expected, not measured). Then
   record:
   - `oc logs -n gsd-391-walk <pod> -c dashboard | grep 'backup written'` for each pod: every line names
     `/data/backup/gsd-<stamp>-<that pod>.db` and, from the fourth on, `(4 kept)`;
   - `oc exec -n gsd-391-walk <pod> -c dashboard -- ls -l /data/backup`: eight files, four per pod name;
   - per pod, its newest copy from the log exists in the listing, and `python3.14 -c` in the pod reading
     `http://127.0.0.1:8080/metrics` shows `gsd_backup_last_success_timestamp_seconds` equal to that copy's mtime.
4. `oc delete pod` one of the two. Its replacement takes a new name and starts its own four; the deleted pod's
   four copies stay (Orchestrator's notes, 11): `ls -l /data/backup` shows twelve files after the replacement's
   fourth backup.
5. **Optional, the NFS leg:** the same steps 2 to 4 in a second throwaway release whose values add
   `persistence.storageClass: nfs-csi`, where cross-client directory caching applies (§2.2). There the dashboard
   logs at ERROR that the journal mode is not WAL and `gsd_sqlite_wal_enabled` reads 0 (SQLite refuses WAL on NFS,
   the chart README's "Watch the filesystem underneath"); that is expected and not this issue's.
6. Remove what the walk created, by name, and nothing else: `helm uninstall gsd391 -n gsd-391-walk`; the claim
   the chart keeps (`helm.sh/resource-policy: keep`), `oc delete pvc -n gsd-391-walk gsd391-group-sync-dashboard-data`;
   `oc delete namespace gsd-391-walk`; and for the NFS leg its `Retain` PersistentVolume.
7. The lab release redeployed on the merged release (`release-crc.sh --argocd main`): `/data/backup` still names
   `gsd-<stamp>.db`, `keep` 4, and the PVC UIDs equal step 1's.

The evidence (the values file, the logs, the listings, the metric reads) goes under
`reports/<date>_backup-per-replica-391/` and on the issue, pinned to the full merge sha.

## 6. What an operator sees, and what it costs

- **At one replica: nothing.** The same names, the same `keep`, the same metric, the same log line.
- **Above one replica:** `/data/backup` holds `gsd-<stamp>-<pod>.db` files, `keep` per pod; each pod's log line
  `backup written to /data/backup/gsd-<stamp>-<pod>.db (4 kept)` counts its own; each pod's
  `gsd_backup_last_success_timestamp_seconds` is its own newest copy, so `GroupSyncDashboardBackupStale` fires for
  the one replica whose backups stopped (a pod with no copy of its own yet reads the directory's newest, so after a
  rollout whose backups all fail it still fires), and the Grafana "Backup age" panel shows the stalest replica.
  The offsite CronJob ships the newest copy of whichever pod wrote last, as
  it shipped one pod's copy before. The KPI size line counts every pod's copies.
- **Disk:** at N replicas, N × `keep` copies on the claim instead of `keep` in all, each about the size of that
  pod's database; plus, under the shipped behaviour, the copies of every departed pod until they are removed by
  hand (Orchestrator's notes, 11). On the lab a copy is about 14.2 MB (§2.7); the lab runs one replica, so nothing
  changes there.
- **Time:** none measurable; the rotation filters a directory listing it already made.
- **Code** (`git diff --numstat` on the applied tree):

| file | added | removed |
|---|---|---|
| `local-development/gsd/storage.py` | 45 | 1 |
| `local-development/gsd/store.py` | 12 | 7 |
| `local-development/gsd/poller.py` | 5 | 2 |
| `local-development/gsd/metrics.py` | 10 | 4 |
| `local-development/tests/test_backup.py` | 164 | 0 |
| `local-development/tests/test_history_retention.py` | 35 | 2 |
| `local-development/tests/test_offsite_backup_script.py` | 20 | 0 |
| `local-development/tests/test_metrics.py` | 71 | 1 |
| `local-development/tests/test_kpi.py` | 11 | 0 |
| `local-development/tests/test_chart_grafana_dashboard.py` | 8 | 0 |
| `docs/RUNBOOK_backup_restore.md` | 6 | 1 |
| `docs/CHANGELOG.md` | 16 | 0 |
| `charts/group-sync-dashboard/README.md` | 13 | 1 |
| `charts/group-sync-dashboard/values.yaml` | 5 | 0 |
| `charts/group-sync-dashboard/templates/monitoring.yaml` | 6 | 2 |
| `charts/group-sync-dashboard/dashboards/group-sync-dashboard.json` | 2 | 2 |

Plus the version fields, the Chart.yaml history line and the CHANGELOG heading that `prepare-release.py --app`
writes at implementation. No RBAC, no new value, no new template.

## 7. Implementation blocks

Applied in this order: blocks 1 to 15 are the code (`storage.py`, `store.py`, `poller.py`, `metrics.py`), 16 to 23
the tests, 24 to 30 the documents, the values comment, the alert's text and the CHANGELOG, and 31 and 32 the Grafana
"Backup age" panel and its test (review of this spec). Each was cut by the generator of §4.3, blocks 14, 15, 22, 24,
26, 28 to 30 corrected and 31 and 32 added in review; none carries a version field.

### Block 1 — local-development/gsd/storage.py: the imports the naming rule uses

`re` for `BACKUP_NAME`, `os` and `socket` for the pod's name, `Path` for the listing (§3.2).

<!-- block: local-development/gsd/storage.py | edit -->

Old text:

```python

from contextlib import AbstractContextManager
from typing import Any, NotRequired, Protocol, TypedDict, runtime_checkable
```

New text:

```python

import os
import re
import socket
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any, NotRequired, Protocol, TypedDict, runtime_checkable
```

### Block 2 — local-development/gsd/storage.py: the protocol's `backup` takes `owner`

`local-development/tests/test_storage_seam.py#test_the_declared_signatures_match_the_implementation` holds the protocol and `Store` to the same parameters (Orchestrator's notes, 7).

<!-- block: local-development/gsd/storage.py | edit -->

Old text:

```python

    def backup(self, directory: str, keep: int = 3) -> str | None: ...
    def snapshot(self, directory: str, keep: int = 2) -> str | None:
```

New text:

```python

    def backup(self, directory: str, keep: int = 3, *, owner: str | None = None) -> str | None: ...
    def snapshot(self, directory: str, keep: int = 2) -> str | None:
```

### Block 3 — local-development/gsd/storage.py: `BACKUP_NAME`, `backup_owner` and `backup_copies`

Whose copies a pod writes, rotates and reports (§3.2), after `open_backend`, in the module the store, the poller and the metrics collector already import.

<!-- block: local-development/gsd/storage.py | edit -->

Old text:

```python
        wal_checkpoint_mb=settings.sqlite_wal_checkpoint_mb,
    )
```

New text:

```python
        wal_checkpoint_mb=settings.sqlite_wal_checkpoint_mb,
    )


# -- the scheduled backups' names (#391) ---------------------------------------------------------
#
# Above one replica every pod has its own database (/data/$POD_NAME/gsd.db), but config.backup.dir is
# ONE directory on the shared volume. Rotating by the bare gsd-*.db pattern there let each pod delete
# its neighbours' copies: two pods with keep 4 kept 2 of their own, and with three pods and keep 2 a
# pod's only copy went, after backup() had returned it and the poller had released retention on it.
# So above one replica a copy carries the pod that wrote it, and a pod rotates and reports only its
# own. At one replica the name stays gsd-<stamp>.db and every gsd-*.db is the pod's, as before:
# existing restores, the runbook and the restore tool read that name.

#: gsd-<%Y%m%dT%H%M%S.%fZ>.db, or gsd-<stamp>-<pod>.db above one replica. The stamp holds no "-", so the
#: owner is everything after the stamp's "-", compared whole: a glob such as gsd-*-<pod>.db would also
#: take the copies of a pod whose name merely ends in "-<pod>".
BACKUP_NAME = re.compile(r"gsd-(\d{8}T\d{6}\.\d{6}Z)(?:-(.+))?\.db")


def backup_owner(replica_count: int) -> str | None:
    """Whose scheduled backups this process writes, rotates and reports (#391).

    None at one replica: every gsd-*.db in config.backup.dir is this pod's, as before. Above one, this
    pod's name: POD_NAME (the chart's downward-API metadata.name), else the hostname, which Kubernetes
    sets to the same name; the rule the leader election and the pre-upgrade copy already use.
    """
    if replica_count <= 1:
        return None
    return os.environ.get("POD_NAME") or socket.gethostname()


def backup_copies(directory: str | Path, owner: str | None) -> list[Path]:
    """The scheduled backups in `directory` that `owner` wrote, oldest first.

    Ordered by name, which the UTC stamp leads, so name order is time order across every pod. owner None
    is every gsd-*.db whatever follows the stamp: the rule at one replica, unchanged.
    """
    copies = sorted(Path(directory).glob("gsd-*.db"))
    if owner is None:
        return copies
    return [p for p in copies if (m := BACKUP_NAME.fullmatch(p.name)) is not None and m.group(2) == owner]
```

### Block 4 — local-development/gsd/store.py: the store imports `backup_copies`

The rotation's list (§3.3).

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python

from .storage import SqliteHealth, StorageHealth  # noqa: F401
from .kpi.predicates import GROUP_EMPTY, GROUP_UNATTRIBUTED, qualified
```

New text:

```python

from .storage import SqliteHealth, StorageHealth, backup_copies  # noqa: F401
from .kpi.predicates import GROUP_EMPTY, GROUP_UNATTRIBUTED, qualified
```

### Block 5 — local-development/gsd/store.py: `Store.backup` takes `owner`

Keyword-only, default `None`: every existing caller keeps today's behaviour.

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python

    def backup(self, directory: str, keep: int = 3) -> str | None:
        """Write a consistent copy of the database to `directory`. Returns its path.
```

New text:

```python

    def backup(self, directory: str, keep: int = 3, *, owner: str | None = None) -> str | None:
        """Write a consistent copy of the database to `directory`. Returns its path.
```

### Block 6 — local-development/gsd/store.py: `Store.backup` says what `owner` does, and passes it

§3.1 and §3.3.

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
        them off the volume is the other half.
        """
        return self._vacuum_into(directory, keep, what="backup")

```

New text:

```python
        them off the volume is the other half.

        `owner` is the pod above one replica (storage.backup_owner, #391): the copy is named
        gsd-<stamp>-<owner>.db and `keep` bounds that pod's own copies only, so a neighbour
        sharing the directory never deletes one. None, at one replica, is gsd-<stamp>.db and
        `keep` over every gsd-*.db, as before.
        """
        return self._vacuum_into(directory, keep, what="backup", owner=owner)

```

### Block 7 — local-development/gsd/store.py: `_vacuum_into` takes `owner`

`snapshot()` passes none, so report snapshots keep their name (T391-5).

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python

    def _vacuum_into(self, directory: str, keep: int, *, what: str) -> str | None:
        if self.path == ":memory:":
```

New text:

```python

    def _vacuum_into(self, directory: str, keep: int, *, what: str, owner: str | None = None) -> str | None:
        if self.path == ":memory:":
```

### Block 8 — local-development/gsd/store.py: the name carries the pod above one replica

§3.1; the `.tmp` is the same name plus `.tmp`, as before.

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        target = target_dir / f"gsd-{stamp}.db"
        tmp = target_dir / f"gsd-{stamp}.db.tmp"
        try:
```

New text:

```python
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
        target = target_dir / (f"gsd-{stamp}.db" if owner is None else f"gsd-{stamp}-{owner}.db")
        tmp = target.with_name(target.name + ".tmp")
        try:
```

### Block 9 — local-development/gsd/store.py: the rotation counts only the owner's copies

§3.3: at one replica and for snapshots `backup_copies(dir, None)` is the same sorted list as before.

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
            return None
        existing = sorted(target_dir.glob("gsd-*.db"))
        for stale in existing[:-keep] if keep > 0 else []:
```

New text:

```python
            return None
        existing = backup_copies(target_dir, owner)
        for stale in existing[:-keep] if keep > 0 else []:
```

### Block 10 — local-development/gsd/poller.py: the poller imports `backup_owner`

§3.3.

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
from .audit import AuditLogProgress, plan_audit_stamps
from .storage import StorageBackend
from .timeutil import now_iso
```

New text:

```python
from .audit import AuditLogProgress, plan_audit_stamps
from .storage import StorageBackend, backup_owner
from .timeutil import now_iso
```

### Block 11 — local-development/gsd/poller.py: the poller passes this pod above one replica

`Settings.replica_count` is the chart's `replicaCount` (§3.2).

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
        try:
            if (self.store.backup(self.settings.backup_dir, keep=self.settings.backup_keep)
                    is None):
```

New text:

```python
        try:
            # Above one replica this pod's own copies only (#391): no neighbour sharing the directory
            # deletes the copy that sets "ok" below, which is what releases retention.
            if (self.store.backup(self.settings.backup_dir, keep=self.settings.backup_keep,
                                  owner=backup_owner(self.settings.replica_count))
                    is None):
```

### Block 12 — local-development/gsd/metrics.py: `Path` is no longer used in the metrics module

Its only use was the backup gauge's glob, which block 15 replaces.

<!-- block: local-development/gsd/metrics.py | edit -->

Old text:

```python
from datetime import UTC, datetime, timedelta
from pathlib import Path

```

New text:

```python
from datetime import UTC, datetime, timedelta

```

### Block 13 — local-development/gsd/metrics.py: the metrics module imports the two helpers

§3.4.

<!-- block: local-development/gsd/metrics.py | edit -->

Old text:

```python
from . import __version__, state as st
from .storage import StorageBackend

```

New text:

```python
from . import __version__, state as st
from .storage import StorageBackend, backup_copies, backup_owner

```

### Block 14 — local-development/gsd/metrics.py: the gauge's help text says which copy it measures

§3.4.

<!-- block: local-development/gsd/metrics.py | edit -->

Old text:

```python
            "gsd_backup_last_success_timestamp_seconds",
            "Modification time of the newest backup file in backupDir. Read from the "
            "files rather than remembered from the last attempt, so it survives restarts "
```

New text:

```python
            "gsd_backup_last_success_timestamp_seconds",
            "Modification time of the newest backup file in backupDir; above one replica, "
            "the newest this pod wrote, or the directory's newest until it has written one. Read from the "
            "files rather than remembered from the last attempt, so it survives restarts "
```

### Block 15 — local-development/gsd/metrics.py: the gauge reads this pod's own copies above one replica, the directory until it has one

§3.4 and Orchestrator's notes, 4: with no copy of its own (every pod, after a rollout) it reads the whole directory, as before, so a rollout whose backups all fail still ages a series the alert can fire on.

<!-- block: local-development/gsd/metrics.py | edit -->

Old text:

```python
            try:
                newest = max(
                    (p.stat().st_mtime
                     for p in Path(self.settings.backup_dir).glob("gsd-*.db")),
                    default=None,
```

New text:

```python
            try:
                # Above one replica, this pod's own copies (#391): a neighbour's fresh copy in the
                # shared directory must not stand in for this replica's failing backups. A pod with
                # none yet (every pod, after a rollout) reads the whole directory, as before #391:
                # with no series, a rollout whose backups all fail could never fire the alert.
                owner = backup_owner(getattr(self.settings, "replica_count", 1))
                mine = backup_copies(self.settings.backup_dir, owner)
                newest = max(
                    (p.stat().st_mtime
                     for p in mine or backup_copies(self.settings.backup_dir, None)),
                    default=None,
```

### Block 16 — local-development/tests/test_backup.py: `re`, for T391-4's name check

T391-4 asserts the one-replica name with a regular expression.

<!-- block: local-development/tests/test_backup.py | edit -->

Old text:

```python
import pathlib
import sqlite3
```

New text:

```python
import pathlib
import re
import sqlite3
```

### Block 17 — local-development/tests/test_backup.py: the replicas harness, T391-1, T391-2, T391-4, T391-5, T391-9 and the whole-name test

The helpers drive the poller as the chart runs it (§4.1); `test_history_retention.py` and `test_offsite_backup_script.py` import them inside their tests.

<!-- block: local-development/tests/test_backup.py | edit -->

Old text:

```python
    assert seen["visible_before"] == [], "nothing matched gsd-*.db until the rename"
    assert not list((tmp_path / "report").glob("*.tmp"))
```

New text:

```python
    assert seen["visible_before"] == [], "nothing matched gsd-*.db until the rename"
    assert not list((tmp_path / "report").glob("*.tmp"))


# -- #391: above one replica, every pod writes into one config.backup.dir -----------------------------------
#
# Each replica has its own database (/data/$POD_NAME/gsd.db) and the chart gives every pod the same backupDir.
# These drive the poller, which is where the pod's identity (POD_NAME, Settings.replica_count) meets
# Store.backup, and they read a copy's owner from its CONTENTS, never from the file name under test.
# test_history_retention.py and test_offsite_backup_script.py import the three helpers.

REPO = pathlib.Path(__file__).resolve().parents[2]


class _Replica(Store):
    """One replica's database, marked with its pod, recording every path backup() returned."""

    def __init__(self, root: pathlib.Path, pod: str) -> None:
        super().__init__(str(root / pod / "gsd.db"))
        self.pod = pod
        self.returned: list[str | None] = []
        with self._write() as conn:
            conn.execute("CREATE TABLE replica_marker(pod TEXT)")
            conn.execute("INSERT INTO replica_marker VALUES(?)", (pod,))

    def backup(self, *args, **kwargs):
        path = super().backup(*args, **kwargs)
        self.returned.append(path)
        return path


def replicas_sharing_one_directory(root: pathlib.Path, pods: tuple[str, ...], keep: int):
    """(the shared backup directory, [(pod, its store, its poller)]), as the chart runs len(pods) replicas."""
    from gsd.config import Settings
    from gsd.poller import Poller

    shared = root / "backup"
    replicas = []
    for pod in pods:
        store = _Replica(root, pod)
        settings = Settings(clusters=[], db_path=store.path, backup_dir=str(shared), backup_keep=keep,
                            replica_count=len(pods))
        replicas.append((pod, store, Poller(store, settings, None)))
    return shared, replicas


def backup_cycle(replicas, monkeypatch) -> None:
    """One scheduled backup per replica, in order, each run as its own pod (POD_NAME, as the chart sets it)."""
    for pod, _store, poller in replicas:
        monkeypatch.setenv("POD_NAME", pod)
        poller._next_backup = 0.0
        poller._maybe_backup()


def copy_owners(directory: pathlib.Path) -> list[str]:
    """The pod each gsd-*.db in `directory` is a copy of, read from inside the copy."""
    owners = []
    for path in sorted(directory.glob("gsd-*.db")):
        conn = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
        try:
            owners.append(conn.execute("SELECT pod FROM replica_marker").fetchone()[0])
        finally:
            conn.close()
    return owners


def _close(replicas) -> None:
    for _pod, store, _poller in replicas:
        store.close()


def test_two_replicas_sharing_one_directory_each_keep_their_own_keep(tmp_path, monkeypatch):
    """T391-1. Measured on main dd51b91f: with keep 4 each replica kept 2 of its own, because every rotation
    deleted by the bare gsd-*.db pattern across the shared directory. Six cycles, so each pod's own rotation
    runs too."""
    shared, replicas = replicas_sharing_one_directory(tmp_path, ("pod-a", "pod-b"), keep=4)
    try:
        for _ in range(6):
            backup_cycle(replicas, monkeypatch)
        owners = copy_owners(shared)
        assert {pod: owners.count(pod) for pod, _, _ in replicas} == {"pod-a": 4, "pod-b": 4}
        assert all(pathlib.Path(store.returned[-1]).exists() for _, store, _ in replicas)
    finally:
        _close(replicas)


def test_no_replica_deletes_a_copy_it_did_not_write(tmp_path, monkeypatch):
    """T391-2. Three replicas, keep 2, one cycle: A, then B, then C. On main C's rotation deleted A's only copy
    after backup() had returned it: {'pod-a': False, 'pod-b': True, 'pod-c': True}."""
    shared, replicas = replicas_sharing_one_directory(tmp_path, ("pod-a", "pod-b", "pod-c"), keep=2)
    try:
        backup_cycle(replicas, monkeypatch)
        assert {pod: pathlib.Path(store.returned[-1]).exists() for pod, store, _ in replicas} == {
            "pod-a": True, "pod-b": True, "pod-c": True}
        assert sorted(copy_owners(shared)) == ["pod-a", "pod-b", "pod-c"]
    finally:
        _close(replicas)


def test_one_replica_keeps_the_name_and_the_rotation(tmp_path, monkeypatch):
    """T391-4, a regression guard: at one replica the name carries no pod even with POD_NAME set, and keep
    bounds the directory (test_generations_are_bounded, store.py's gsd-<stamp>.db)."""
    shared, replicas = replicas_sharing_one_directory(tmp_path, ("pod-a",), keep=3)
    try:
        for _ in range(6):
            backup_cycle(replicas, monkeypatch)
        names = sorted(p.name for p in shared.glob("gsd-*.db"))
        assert len(names) == 3
        assert all(re.fullmatch(r"gsd-\d{8}T\d{6}\.\d{6}Z\.db", name) for name in names), names
    finally:
        _close(replicas)


def test_report_snapshots_keep_their_name_with_a_pod_set(tmp_path, monkeypatch):
    """T391-5, a regression guard: Store.snapshot shares _vacuum_into, and the report service reads its files
    by _STAMP. The pod in the name is backup()'s alone."""
    from gsd.reporting.snapshot import _STAMP

    monkeypatch.setenv("POD_NAME", "pod-a")
    store = Store(str(tmp_path / "gsd.db"))
    try:
        written = [store.snapshot(str(tmp_path / "report"), keep=2) for _ in range(2)]
    finally:
        store.close()
    assert all(written)
    assert all(_STAMP.match(pathlib.Path(path).name) for path in written), written


def test_a_pod_is_its_whole_name_not_a_suffix_of_another(tmp_path):
    """#391, from the research (borg prune: a pattern "foo*" also matches "foobar"): the owner is the whole
    field after the stamp, so pod-b neither counts nor rotates x-pod-b's copies or a one-replica copy."""
    from gsd.storage import backup_copies

    shared = tmp_path / "backup"
    shared.mkdir()
    names = ("gsd-20261001T000000.000000Z.db", "gsd-20261001T010000.000000Z-x-pod-b.db",
             "gsd-20261001T020000.000000Z-pod-b.db")
    for name in names:
        (shared / name).write_bytes(b"not a database")
    assert [p.name for p in backup_copies(shared, "pod-b")] == ["gsd-20261001T020000.000000Z-pod-b.db"]
    assert [p.name for p in backup_copies(shared, None)] == list(names)
    store = Store(str(tmp_path / "gsd.db"))
    try:
        mine = store.backup(str(shared), keep=1, owner="pod-b")
    finally:
        store.close()
    assert sorted(p.name for p in shared.glob("gsd-*.db")) == sorted([*names[:2], pathlib.Path(mine).name])


def test_the_docs_say_where_each_replicas_copies_are(tmp_path):
    """T391-9: the runbook, the chart README's Scaling section and the values comment on config.backup each
    say where a replica's copies are and that keep applies per replica. On main the runbook names one
    directory and one keep, and Scaling says nothing about backups."""
    def words(text: str) -> str:
        return " ".join(text.replace("#", " ").split())

    runbook = words((REPO / "docs" / "RUNBOOK_backup_restore.md").read_text())
    readme = (REPO / "charts" / "group-sync-dashboard" / "README.md").read_text()
    scaling = words(readme[readme.index("\n## Scaling\n"):readme.index("\n## Storage\n")])
    values = (REPO / "charts" / "group-sync-dashboard" / "values.yaml").read_text()
    comment = words(values[:values.index("\n  backup:\n    enabled: true")].rsplit("\n\n", 1)[-1])
    for name, text in (("runbook", runbook), ("Scaling", scaling)):
        assert "gsd-<UTC stamp>Z-<pod name>.db" in text, name
        assert "`keep` applies per replica" in text, name
    assert "gsd-<stamp>-<pod>.db" in comment and "keep applies per replica" in comment
```

### Block 18 — local-development/tests/test_history_retention.py: `_Recording.backup` passes the poller's keywords through

Orchestrator's notes, 7: with its fixed signature the poller's `owner=` raises `TypeError`, which `_maybe_backup` counts as a failed backup. `**kwargs` keeps the fake valid on a tree with and without the change.

<!-- block: local-development/tests/test_history_retention.py | edit -->

Old text:

```python

    def backup(self, directory, keep=3):
        self.calls.append("backup")
        return super().backup(directory, keep)

```

New text:

```python

    def backup(self, directory, keep=3, **kwargs):
        self.calls.append("backup")
        return super().backup(directory, keep, **kwargs)

```

### Block 19 — local-development/tests/test_history_retention.py: T391-3: a replica prunes only while its own copy exists

Two pollers, `keep` 1, retention on: both pruned rows are in a copy afterwards.

<!-- block: local-development/tests/test_history_retention.py | edit -->

Old text:

```python
        poller._after_poll(CLUSTER)
        assert _count(recording, "membership_event") == 0

```

New text:

```python
        poller._after_poll(CLUSTER)
        assert _count(recording, "membership_event") == 0

    def test_a_replica_prunes_only_while_its_own_copy_exists(self, tmp_path, monkeypatch):
        """T391-3 (#391). Retention is released on "ok", which backup() returning a path sets. Two replicas
        share one backup directory with keep 1: on main the second replica's rotation deleted the first's
        copy after the first had pruned on it, so the rows it pruned were in no copy anywhere ([7] == [5, 7])."""
        import sqlite3

        shared = tmp_path / "backup"
        replicas = []
        for pod, rows in (("pod-a", 5), ("pod-b", 7)):
            db = tmp_path / pod / "gsd.db"
            store = Store(str(db))
            store.upsert_cluster("crc", "https://api.crc.testing:6443", True)
            _seed(store, "membership_event", rows, days_ago=800)
            settings = _settings(tmp_path, db_path=str(db), backup_dir=str(shared), backup_keep=1, replica_count=2)
            replicas.append((pod, store, Poller(store, settings)))

        def rows_in(path) -> int:
            conn = sqlite3.connect(f"file:{path}?immutable=1", uri=True)
            try:
                return conn.execute("SELECT COUNT(*) FROM membership_event").fetchone()[0]
            finally:
                conn.close()

        try:
            for pod, _store, poller in replicas:
                monkeypatch.setenv("POD_NAME", pod)
                poller._after_poll(CLUSTER)
            assert [_count(store, "membership_event") for _, store, _ in replicas] == [0, 0], "both pruned"
            assert sorted(rows_in(p) for p in shared.glob("gsd-*.db")) == [5, 7]
        finally:
            for _pod, store, _poller in replicas:
                store.close()

```

### Block 20 — local-development/tests/test_offsite_backup_script.py: T391-6: the offsite job still ships the newest copy above one replica

A regression guard; it fails under shape B (§2a).

<!-- block: local-development/tests/test_offsite_backup_script.py | edit -->

Old text:

```python
            assert script.main(["--source", str(backups), "--dest", str(dest), "--keep", "0"]) == 0
        assert len(list(dest.glob("gsd-*.db"))) == 3

```

New text:

```python
            assert script.main(["--source", str(backups), "--dest", str(dest), "--keep", "0"]) == 0
        assert len(list(dest.glob("gsd-*.db"))) == 3


    def test_above_one_replica_the_newest_copy_is_still_found_and_shipped(self, script, tmp_path, monkeypatch):
        """T391-6, a regression guard (#391): above one replica the copies stay in config.backup.dir, the
        CronJob's --source, under gsd-*.db, so the non-recursive glob still finds them, and the newest by name
        is the newest written whichever pod wrote it."""
        from test_backup import backup_cycle, replicas_sharing_one_directory

        shared, replicas = replicas_sharing_one_directory(tmp_path, ("pod-a", "pod-b"), keep=4)
        try:
            for _ in range(3):
                backup_cycle(replicas, monkeypatch)
            newest = pathlib.Path(replicas[-1][1].returned[-1])
            assert script.newest_backup(shared) == newest
            dest = tmp_path / "offsite"
            assert script.main(["--source", str(shared), "--dest", str(dest), "--keep", "2"]) == 0
            assert [p.name for p in dest.glob("gsd-*.db")] == [newest.name]
        finally:
            for _pod, store, _poller in replicas:
                store.close()

```

### Block 21 — local-development/tests/test_metrics.py: `FailingStore.backup` accepts the poller's keywords

Orchestrator's notes, 7: without it the test passes for the wrong reason (`TypeError`, not `None`).

<!-- block: local-development/tests/test_metrics.py | edit -->

Old text:

```python
        class FailingStore:
            def backup(self, directory, keep=3):
                return None
```

New text:

```python
        class FailingStore:
            def backup(self, directory, keep=3, **kwargs):
                return None
```

### Block 22 — local-development/tests/test_metrics.py: T391-7, and the gauge's per-pod reading

T391-7 is a regression guard at one replica; the second test is the masking the issue found (Orchestrator's notes, 4); the third is the fallback that keeps a series after a rollout (§3.4, review of this spec).

<!-- block: local-development/tests/test_metrics.py | edit -->

Old text:

```python
        assert value == pytest.approx(expected, abs=1)

    def test_backup_timestamp_is_absent_when_backups_are_off_or_none_exist(self, tmp_path):
```

New text:

```python
        assert value == pytest.approx(expected, abs=1)

    def test_at_one_replica_the_backup_timestamp_reads_every_copy(self, tmp_path, monkeypatch):
        """T391-7, a regression guard (#391): at one replica the metric is the newest gsd-*.db's mtime whatever
        follows the stamp, as before; POD_NAME is set and does not narrow it."""
        import os

        from gsd.config import Settings
        older = tmp_path / "gsd-20261001T000000.000000Z.db"
        newer = tmp_path / "gsd-20261001T060000.000000Z-pod-b.db"
        for path, mtime in ((older, 1_000_000), (newer, 2_000_000)):
            path.write_bytes(b"x")
            os.utime(path, (mtime, mtime))
        monkeypatch.setenv("POD_NAME", "pod-a")
        settings = Settings(clusters=[], db_path=":memory:", backup_dir=str(tmp_path), replica_count=1)
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, GRACE, settings=settings)).decode()
        finally:
            store.close()
        assert series(text, "gsd_backup_last_success_timestamp_seconds") == {
            "gsd_backup_last_success_timestamp_seconds": 2_000_000}

    def test_above_one_replica_the_backup_timestamp_is_this_pods_own(self, tmp_path, monkeypatch):
        """#391 (the masking the issue found): above one replica the metric is this pod's newest copy, so a
        neighbour's fresh copy in the shared directory cannot hide this replica's failing backups from
        GroupSyncDashboardBackupStale. On main it read the newest copy of any pod, 3,000,000."""
        import os

        from gsd.config import Settings
        own = tmp_path / "gsd-20261001T000000.000000Z-pod-a.db"
        files = ((own, 1_000_000), (tmp_path / "gsd-20261001T060000.000000Z-pod-b.db", 2_000_000),
                 (tmp_path / "gsd-20261001T070000.000000Z-x-pod-a.db", 3_000_000))
        for path, mtime in files:
            path.write_bytes(b"x")
            os.utime(path, (mtime, mtime))
        monkeypatch.setenv("POD_NAME", "pod-a")
        settings = Settings(clusters=[], db_path=":memory:", backup_dir=str(tmp_path), replica_count=2)
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, GRACE, settings=settings)).decode()
        finally:
            store.close()
        assert series(text, "gsd_backup_last_success_timestamp_seconds") == {
            "gsd_backup_last_success_timestamp_seconds": 1_000_000}

    def test_above_one_replica_a_pod_with_no_copy_of_its_own_reads_the_directory(self, tmp_path, monkeypatch):
        """#391, review of the spec: every rollout renames every pod, so after one no pod has a copy of its own.
        If the new pods' backups all fail, the departed pods' copies age, and the metric must keep reading them,
        as on main, or GroupSyncDashboardBackupStale has no series to fire on. Nothing in the directory at all:
        no series, never zero."""
        import os

        from gsd.config import Settings
        for name, mtime in (("gsd-20261001T000000.000000Z-departed-a.db", 1_000_000),
                            ("gsd-20261001T060000.000000Z-departed-b.db", 2_000_000)):
            (tmp_path / name).write_bytes(b"x")
            os.utime(tmp_path / name, (mtime, mtime))
        monkeypatch.setenv("POD_NAME", "new-pod")
        settings = Settings(clusters=[], db_path=":memory:", backup_dir=str(tmp_path), replica_count=2)
        store = Store(":memory:")
        try:
            text = generate_latest(build_registry(store, GRACE, settings=settings)).decode()
            assert series(text, "gsd_backup_last_success_timestamp_seconds") == {
                "gsd_backup_last_success_timestamp_seconds": 2_000_000}
            for path in tmp_path.glob("gsd-*.db"):
                path.unlink()
            text = generate_latest(build_registry(store, GRACE, settings=settings)).decode()
            assert series(text, "gsd_backup_last_success_timestamp_seconds") == {}
        finally:
            store.close()

    def test_backup_timestamp_is_absent_when_backups_are_off_or_none_exist(self, tmp_path):
```

### Block 23 — local-development/tests/test_kpi.py: T391-8: the size line counts every replica's copies

A regression guard (Orchestrator's notes, 4).

<!-- block: local-development/tests/test_kpi.py | edit -->

Old text:

```python
        (arts / "r2" / "run.json").write_bytes(b"{}")
        assert artifact_bytes(str(arts))() == {"bytes": 34, "files": 3}

```

New text:

```python
        (arts / "r2" / "run.json").write_bytes(b"{}")
        assert artifact_bytes(str(arts))() == {"bytes": 34, "files": 3}

    def test_the_backup_size_line_counts_every_replicas_copies(self, tmp_path):
        """T391-8, a regression guard (#391): the size line counts every gsd-*.db in backupDir, whichever pod
        wrote it: the bytes on the shared claim, which is what it is for."""
        from gsd.kpi.system import dashboard_data_bytes
        db = tmp_path / "gsd.db"; db.write_bytes(b"d" * 100)
        backups = tmp_path / "backup"; backups.mkdir()
        for name, size in (("gsd-20261001T000000.000000Z.db", 10), ("gsd-20261001T010000.000000Z-pod-a.db", 15),
                           ("gsd-20261001T020000.000000Z-pod-b.db", 20)):
            (backups / name).write_bytes(b"b" * size)
        assert dashboard_data_bytes(str(db), str(backups))()["backups"] == {"count": 3, "bytes": 45}

```

### Block 24 — docs/RUNBOOK_backup_restore.md: the runbook's on-volume bullet names a replica's copies

T391-9; the issue's item 6.

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
* **on-volume** — `config.backup` writes `gsd-<UTC stamp>Z.db` under `config.backup.dir`
  (`/data/backup`) every `intervalHours`, keeping `keep` of them, on the data claim;
* **off-volume** — `backup.offsite` (off by default) copies the newest of those to a second
```

New text:

```text
* **on-volume** — `config.backup` writes `gsd-<UTC stamp>Z.db` under `config.backup.dir`
  (`/data/backup`) every `intervalHours`, keeping `keep` of them, on the data claim. Above one replica
  every pod writes `gsd-<UTC stamp>Z-<pod name>.db` into that same directory and keeps `keep` of its own:
  `keep` applies per replica, and no pod deletes another pod's copies. The copies of a pod that no longer
  exists (a rollout renames every pod), and the copies named without a pod (written at one replica, or by a
  release before #391), stay until they are removed by hand, or until the release runs one replica again,
  whose next backup keeps `keep` copies in all (#391);
* **off-volume** — `backup.offsite` (off by default) copies the newest of those to a second
```

### Block 25 — charts/group-sync-dashboard/README.md: the chart README's Backups table: `keep` is per replica above one

T391-9.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
| `config.backup.intervalHours` | `6` | taken from the poll thread, and once immediately at startup |
| `config.backup.keep` | `4` | 4 × 6h = the last day, at roughly the size of the database each |

```

New text:

```text
| `config.backup.intervalHours` | `6` | taken from the poll thread, and once immediately at startup |
| `config.backup.keep` | `4` | 4 × 6h = the last day, at roughly the size of the database each; per replica above one ([Scaling](#scaling)) |

```

### Block 26 — charts/group-sync-dashboard/README.md: the chart README's Scaling section: backups above one replica

T391-9; the departed pods' copies stated as the fact the blocks ship (Orchestrator's notes, 11).

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
which pod responds.

Four combinations are refused at template time rather than deployed broken:
```

New text:

```text
which pod responds.

**Backups above one replica.** Every pod writes its scheduled backups into the one
`config.backup.dir`, named `gsd-<UTC stamp>Z-<pod name>.db`, and keeps `config.backup.keep` of its
own: `keep` applies per replica, no pod deletes another pod's copies, and each pod's
`gsd_backup_last_success_timestamp_seconds` is its own newest copy (until it has written one, the
directory's newest, so a rollout whose new pods all fail to back up still fires
`GroupSyncDashboardBackupStale`). The directory holds `replicaCount × keep` copies, each about the size
of one pod's database, and also the copies of pods that no longer exist and those named without a pod
(written at one replica, or by a release before #391): a rollout renames every pod, and nothing deletes
a departed pod's copies, as nothing deletes its `/data/<pod name>/gsd.db`. `backup.offsite` still ships
the single newest copy, which is one replica's. At one replica the name stays `gsd-<UTC stamp>Z.db` and
`keep` bounds the whole directory ([runbook](../../docs/RUNBOOK_backup_restore.md)).

Four combinations are refused at template time rather than deployed broken:
```

### Block 27 — charts/group-sync-dashboard/values.yaml: the values comment on `config.backup`

T391-9.

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```yaml
  # they count against persistence.size (docs/RUNBOOK_backup_restore.md §6).
  backup:
```

New text:

```yaml
  # they count against persistence.size (docs/RUNBOOK_backup_restore.md §6).
  #
  # ABOVE ONE REPLICA every pod writes into this one dir as gsd-<stamp>-<pod>.db and keeps `keep` of
  # its OWN: keep applies per replica, and no pod deletes another pod's copies. The copies of a pod
  # that no longer exists are rotated by nobody (a rollout renames every pod). At one replica the name
  # stays gsd-<stamp>.db and keep bounds the whole dir (the chart README's Scaling section).
  backup:
```

### Block 28 — charts/group-sync-dashboard/templates/monitoring.yaml: the backup alert's comment

§3.4.

<!-- block: charts/group-sync-dashboard/templates/monitoring.yaml | edit -->

Old text:

```yaml
        # The only copy of the data that cannot be re-fetched from the cluster. The metric
        # reads the newest file in backupDir, so this fires on every failure shape —
        # including a wrong directory and rotation deleting everything. No series while
```

New text:

```yaml
        # The only copy of the data that cannot be re-fetched from the cluster. The metric
        # reads the newest file in backupDir (above one replica, the newest that pod wrote,
        # so each replica's series is its own; a pod that has written none yet, as every pod
        # after a rollout, reads the whole directory), so this fires on every failure shape —
        # including a wrong directory and rotation deleting everything. No series while
```

### Block 29 — charts/group-sync-dashboard/templates/monitoring.yaml: the backup alert's description

§3.4: an operator reading the alert looks at the right copy.

<!-- block: charts/group-sync-dashboard/templates/monitoring.yaml | edit -->

Old text:

```yaml
            description: >-
              The newest file in backupDir is {{ `{{ $value | humanizeDuration }}` }} old —
              at least two backup intervals. The sync and membership history exists only in
```

New text:

```yaml
            description: >-
              The newest backup in backupDir (above one replica, the newest this pod wrote, or
              the directory's newest until it has written one) is
              {{ `{{ $value | humanizeDuration }}` }} old —
              at least two backup intervals. The sync and membership history exists only in
```

### Block 30 — docs/CHANGELOG.md: the CHANGELOG entry

First under `## Unreleased`; `prepare-release.py` moves it under the release heading it cuts.

<!-- block: docs/CHANGELOG.md | edit -->

Old text:

```text
which `local-development/prepare-release.py` does when the release is cut.

## Unreleased

```

New text:

```text
which `local-development/prepare-release.py` does when the release is cut.

## Unreleased

- **Above one replica, every pod keeps its own scheduled backups (#391, Epic E #385,
  `docs/specs/SPEC_E4_per_pod_backup_rotation.md`).** Replicas share `config.backup.dir`, and each rotation
  deleted by the bare `gsd-*.db` pattern there, so with two replicas and `keep: 4` each kept 2 of its own,
  and with three replicas and `keep: 2` a pod's only copy was deleted by a neighbour after the poller had
  released retention on it. Above one replica a copy is now named `gsd-<UTC stamp>Z-<pod name>.db` (the pod is
  `POD_NAME`), and a pod rotates only the copies whose name carries exactly its own pod, so each keeps `keep`
  of its own and none deletes another's; `gsd_backup_last_success_timestamp_seconds` reads the pod's own
  copies, so `GroupSyncDashboardBackupStale` sees a replica whose backups fail beside a healthy one (a pod
  with none yet reads the whole directory, as before, so a rollout whose backups all fail still alerts), and
  the Grafana "Backup age" panel shows the stalest replica. At one replica nothing changes: the name stays
  `gsd-<UTC stamp>Z.db`, `keep` bounds the whole directory, and the metric reads every copy. The offsite
  CronJob still ships the newest `gsd-*.db` by name, the KPI size line counts every pod's copies (the bytes
  on the claim), and report snapshots keep their name. The copies of a pod that no longer exists, and those
  named without a pod, are not rotated above one replica (a rollout renames every pod); the runbook and the
  chart README's Scaling section say so.

```

### Block 31 — charts/group-sync-dashboard/dashboards/group-sync-dashboard.json: "Backup age" shows the stalest replica

§3.4 (review of this spec): the panel's red step is `GroupSyncDashboardBackupStale`'s threshold and the alert is per pod, so the panel takes `min` over the pods' series; at one replica it is the same number.

<!-- block: charts/group-sync-dashboard/dashboards/group-sync-dashboard.json | edit -->

Old text:

```json
      "title": "Backup age",
      "description": "time() - gsd_backup_last_success_timestamp_seconds. Red at monitoring.prometheusRule.backupStaleSeconds (43200) — GroupSyncDashboardBackupStale. No data means backups are disabled or none exists yet.",
      "gridPos": { "h": 6, "w": 6, "x": 0, "y": 37 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "time() - max(gsd_backup_last_success_timestamp_seconds)", "legendFormat": "backup age", "instant": true }
```

New text:

```json
      "title": "Backup age",
      "description": "time() - gsd_backup_last_success_timestamp_seconds of the stalest replica (min over the pods; above one replica each pod's series is its own). Red at monitoring.prometheusRule.backupStaleSeconds (43200) — GroupSyncDashboardBackupStale. No data means backups are disabled or none exists yet.",
      "gridPos": { "h": 6, "w": 6, "x": 0, "y": 37 },
      "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" },
      "targets": [
        { "refId": "A", "datasource": { "type": "prometheus", "uid": "${DS_PROMETHEUS}" }, "expr": "time() - min(gsd_backup_last_success_timestamp_seconds)", "legendFormat": "backup age", "instant": true }
```

### Block 32 — local-development/tests/test_chart_grafana_dashboard.py: the "Backup age" panel reads the stalest replica

§3.4 (review of this spec); it fails on the base, whose panel reads `max`.

<!-- block: local-development/tests/test_chart_grafana_dashboard.py | edit -->

Old text:

```python
        assert red_step("Login capture: last successful read age") == rule["captureStalledSeconds"]
        assert red_step("Backup age") == rule["backupStaleSeconds"]

```

New text:

```python
        assert red_step("Login capture: last successful read age") == rule["captureStalledSeconds"]
        assert red_step("Backup age") == rule["backupStaleSeconds"]

    def test_backup_age_reads_the_stalest_replica(self):
        """#391: above one replica each pod's gsd_backup_last_success_timestamp_seconds is its own and
        GroupSyncDashboardBackupStale fires per pod. The panel's red step is that alert's threshold (the test
        above), so it shows the stalest replica: with max() it stayed green while the alert fired for one."""
        board = json.loads(DASHBOARD.read_text())
        panel = next(p for p in _walk_panels(board["panels"]) if p["title"] == "Backup age")
        assert [t["expr"] for t in panel["targets"]] == ["time() - min(gsd_backup_last_success_timestamp_seconds)"]

```
