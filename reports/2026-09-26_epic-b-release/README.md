# Epic B (#382) released and deployed — application 0.37.0, chart 0.58.5, 2026-09-27

## The release and the deploy gate

- **Release PR #409:** merge `b087c78f80b44be68bb40a0c0b44c71b53b069e7`, cut with `prepare-release.py --app 0.37.0`.
- **The gate before the deploy** (`walk/gate.txt`):
  - `publish.yml` succeeded (run 36281230543).
  - quay's `:0.37.0` resolves to the same digest as the immutable `:0.37.0-b087c78f80` for both images: dashboard
    `sha256:62e231178a3a…`, report `sha256:4715d4be2331…`.
  - `helm.yaml` succeeded, and chart 0.58.5 was published at 00:10:01Z.
  - Why the gate exists: before this release, `:0.37.0` was a stale chart-version label on an application 0.24.0
    image (#410).
- **The deploy:** `release-crc.sh --argocd main`. Argo CD was Synced/Healthy; the deployment ran chart
  `group-sync-dashboard-0.58.5` with image `…:0.37.0`, and `/api/version` in the pod read `"version":"0.37.0",
  "commit":"b087c78f80"`.
  - The script exited 1 because #411 merged during the sync. Argo followed `main` to `cbe828b`, which contains
    `b087c78`, and the script's wait for the exact `b087c78` revision timed out (`walk/release-tail.log`).
  - #411 changes `fleetlogin.py`, a spec and the changelog. None of those is in the published 0.37.0 image.
- **The PVC UIDs** are the same before the deploy and after the walk (`walk/pvc-before.txt`, `walk/pvc-after-walk.txt`).

## The checks: 13 of 13 passed (`walk/walk.out`)

The released image, pinned by digest, ran in a throwaway pod (`gsd-walk-epic-b`, deleted afterwards) with no volume.
It ran against a copy of the newest six-hourly backup, `gsd-20260927T000637.303159Z.db`; the copy's sha256 matched
the source's (`b8c87250…`). The script is `walk/walk_epic_b.py`.

| Check | Result |
|---|---|
| #305: a copy set to schema 21 | refused: "database schema 21 is newer than this dashboard understands (20) …"; the file is byte-identical |
| #301: a copy opened with a walk-only no-op migration 21 | the copy line comes before the migration line; one copy (8,876,032 bytes, 0.40 s), its sidecar matches, `user_version` 20; five more starts keep exactly that copy |
| R1–R4 on the backup | `integrity_check` ok at schema 20; opened with no migration and no copy; the five tables' counts equal before and after; `/healthz` 200, `/api/clusters` serves the 6 enabled clusters, and a group serves its 8 stored changes |
| R5 on #301's copy | the same four checks pass |
| R6 the live side | the walk pod had no volume; the live `gsd.db-wal` mtime moved from 1790469037 to 1790469096 across a poll (`walk/live-wal-*.txt`), so the dashboard kept writing; `/data` holds no `pre-upgrade/`, which is right for a database already at the release's schema |

The operator chose to prove #301 on a copy rather than by a live upgrade and restore (#301's amended Definition of
Done). The live rollback stays with #302.

## The three screenshots

They are in `docs/RUNBOOK_backup_restore.md` ("What a successful backup looks like") and under `docs/screenshots/`.
Each is rendered from real output:

- **The six-hourly backup:** captured at 23:02:25Z (`capture/`, `capture/render.py`).
- **The pre-upgrade copy and the restore check:** from this walk (`walk/render2.py`).
