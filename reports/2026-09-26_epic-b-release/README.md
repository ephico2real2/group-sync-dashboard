# Epic B (#382) released and deployed — application 0.37.0, chart 0.58.5 (2026-09-27 UTC)

## The release, the image gate, and what actually deployed it

- **Release PR #409:** merge `b087c78f80b44be68bb40a0c0b44c71b53b069e7`, cut with `prepare-release.py --app 0.37.0`.
- **The image gate** (`walk/gate.txt`, `walk/workflow-times.txt`):
  - `publish.yml` (run 36281230543) ran 00:01:34 → 00:04:19Z.
  - quay's `:0.37.0` then equals the immutable `:0.37.0-b087c78f80` for both images: dashboard `sha256:62e231178a3a…`,
    report `sha256:4715d4be2331…`.
  - `helm.yaml` ran 00:01:34 → 00:10:12Z and published chart 0.58.5.
- **The deploy was Argo CD's own auto-sync, not the script** (`walk/argo-history.txt`, `walk/replicasets.txt`,
  `walk/deploy.txt`):
  - The Application has `syncPolicy.automated: {prune: true, selfHeal: true}` and `targetRevision: main`.
  - It deployed `b087c78` at 00:05:54–00:06:11Z, and the 0.37.0 ReplicaSets were created at 00:06:12Z. That was
    95 s after `publish.yml` finished, and **before the gate above was checked**.
  - `release-crc.sh --argocd main`, started at 00:11:30Z, found the release already deployed. Every line of
    `walk/release-tail.log` reads "status is for the previous spec". It exited 1 because its wait for the exact
    `b087c78` revision timed out: #411 merged at 00:20:14Z (`cbe828b`, which contains `b087c78`), and Argo followed
    `main`.
  - **The images were ready in time by luck of timing, not by design.** Before this release, quay's `:0.37.0` was a
    stale label on an application 0.24.0 image. The measured race and the fix are #410.
- **What runs** (`walk/api-version.txt`, `walk/deploy.txt`): chart `group-sync-dashboard-0.58.5`, image `…:0.37.0` at
  `sha256:62e231178a3a…`, and `/api/version` reads `"version":"0.37.0","commit":"b087c78f80"`.
- **The PVC UIDs** are the same before the deploy and after the walk (`walk/pvc-before.txt`, `walk/pvc-after-walk.txt`).

## The checks: 13 of 13 passed (`walk/walk.out`)

The released image, pinned by digest, ran in a throwaway pod with no volume.
- It ran against a copy of the newest six-hourly backup, `gsd-20260927T000637.303159Z.db`, whose sha256 matched the
  source's (`walk/backup-sha.txt`).
- The copy is stamped 00:29:48Z. The first attempt at the pod failed, because the image has no `sleep`; it was
  recreated with a Python wait.
- The script is `walk/walk_epic_b.py`. The recipe in `docs/RUNBOOK_backup_restore.md` was then run verbatim on the
  lab and also gave 13 of 13.

| Check | Result |
|---|---|
| #305: a copy set to schema 21 | Refused: "database schema 21 is newer than this dashboard understands (20) …". The file is byte-identical. |
| #301: a copy opened with a walk-only no-op migration 21 | The copy line comes before the migration line: one copy, 8,876,032 bytes, in 0.40 s. Its sidecar matches, and its `user_version` is 20. |
| R1–R4 on the backup | `integrity_check` is ok at schema 20. It opens with no migration and no copy. The five tables' counts are equal before and after. `/healthz` returns 200, and a group serves all 8 of its stored changes. |
| R5 on #301's copy | The same four checks pass. |

**What these checks do not prove** (OB1-lite's review):
- **`/api/clusters` equal to the enabled rows holds by construction.** The configured set is read from the copy, and
  `is_served` means configured and enabled. The group check is the real serving test: it reads the stored rows through
  the endpoint, `limit=100`.
- **"Five more starts keep that copy" does not exercise the not-taken-again guard.** After the first start the copy is
  at schema 21, so no copy is attempted. That guard is covered by `tests/test_pre_upgrade_copy.py`.
- **Not tested:**
  - the §4 restore onto `/data` (permissions, removing `-wal` and `-shm`);
  - the chart's real configuration (tokens, the oauth proxy, view restrictions);
  - the poller resuming after a restore.
  The live rollback is #302.
- **The live side is untouched by construction, not by measurement.** The walk pod mounted no volume, and the script
  writes only under its work directory.
  - The WAL readings in `walk/live-wal-*.txt` were taken after the walk pod was deleted. They show that the live
    dashboard kept writing, not that the walk left it alone.
  - `/data` has no `pre-upgrade/` (`walk/data-ls.txt`), which is right for a database already at the release's
    schema.

The operator chose to prove #301 on a copy, not by a live upgrade and restore (#301's amended Definition of Done).

## The three screenshots

They are in `docs/RUNBOOK_backup_restore.md`, in "What a successful backup looks like", with the commands for each,
and under `docs/screenshots/`. Each picture shows real output; lines not relevant to it are left out.
- **The six-hourly backup:** captured at 23:02:25Z (`capture/`, `capture/render.py`).
- **The pre-upgrade copy and the restore check:** from this walk (`walk/render2.py`, `walk/pre-verify.py`).
