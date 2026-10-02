# restore-db.sh on the CRC lab — the SPEC_E3 §5 walk (#302)

Walked 2026-10-02 01:28–01:34 UTC on CRC (OpenShift 4.22.7), PR #520. Lab deploys used `local-development/release-crc.sh`
in Helm mode from a worktree (development, as §5 says):
- **Step 2:** a local, never-pushed commit `47dd3a18` (walk-only branch) adding `(21, "no-op for the #302 lab walk",
  ["SELECT 1"])`. Its image `2.1.0-47dd3a18ac` exists only in the lab's internal registry.
- **Steps 3 and 8:** the PR head's real image `2.1.0-756d24cece`, which understands schema 20, with `values-recovery.yaml`
  and then `values-off.yaml`. Each is `environments/crc.yaml` plus the lines at its end.

The `--argocd <branch>` path could not be used: it checks the chart's appVersion (2.1.0) on quay, which is
published only at the merge.

The full record is `walk.log`. It is text, not the PNG terminal captures §5 names.

| Step | Spec §5 | Result |
|---|---|---|
| 1 | Before | PVC UIDs `f065b7a4-…` / `08c7d45c-…`; membership 1843, sync 2737, binding 4328, kyverno 0, login 7950; schema 20 |
| 2 | Upgrade to the walk-only schema 21 | Log: `pre-upgrade copy written before migrating schema 20 -> 21: /data/pre-upgrade/pre-upgrade-20261002T012959.076526Z-schema-20-to-21-….db`, with its `.sha256`; `user_version` 21 |
| 3 | Recovery mode under an image that understands 20 | Pod `1/2 Running`; the log begins `RECOVERY MODE`; TTL 2h |
| 4 | `--list` | The pre-upgrade copy as `20-20261002T012959.076526Z`, `pre-upgrade`, sidecar `ok`, `yes`; the schema-21 backup `no (21 > 20)`; the move-aside note for the `-to-21-` copy |
| 5 | The refusals | `--from-version 21-…` exits 3 naming 21, 20 and the pre-upgrade copy's ID, and `/data` is unchanged; with recovery off, exits 2 naming `recovery.enabled` |
| 6 | The restore | Checked again; loss window 2m42s (3 `sync_event` rows); live set kept under `/data/pre-restore/20261002T013241.786235Z/`; `user_version 21 -> 20`; `gsd.db` gid 0, `-rw-rw-r--`, no `-wal` or `-shm`. `--yes` stood in for answering `y`, because the walk shell has no terminal |
| 7 | Move the `-to-21-` copy aside | Moved with its `.sha256` into `/data/pre-restore/`; `/data/pre-upgrade` is empty |
| 8 | Recovery off | 2.1.0 starts and leads on schema 20; in every history table the live rows at or below the copy's highest id equal the copy's count; PVC UIDs unchanged |
| 9 | No chart change | Under `charts/` only `Chart.yaml`'s version fields differ (0.60.0 → 0.60.1, appVersion 2.0.0 → 2.1.0), which the spec's Version note has `prepare-release.py` write; no template or value changed |

After the walk, the lab runs the PR head under Helm. Once PR #520 merges and publish.yml has pushed 2.1.0, the lab is
handed back to Argo CD on `main` (`release-crc.sh --argocd main`).
