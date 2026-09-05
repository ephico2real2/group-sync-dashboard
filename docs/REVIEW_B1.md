# Review — PR #84, B1: off-volume backup CronJob and restore runbook

Adversarial second-opinion pass, 2026-09-05, on the ten-claim brief for #84
(`docs/specs/SPEC_B1_offsite_backup.md` applied; chart 0.17.0, chart only; the spec's eight
deviations are in its orchestrator's notes). Both the chart's guards (`helm template`) and the copy
script (against real `VACUUM INTO` backups) run locally, so this review could measure rather than
argue. Cursor (Grok 4.6 high fast, ask mode) and Codex (gpt-5.6-sol, xhigh) are recorded below;
every verdict was re-checked here before a decision.

## Live test on the reference cluster (before the reviews were read)

Chart 0.17.0 deployed with the module off; then `helm upgrade --reuse-values --set
backup.offsite.enabled=true --wait` — which **timed out**: the CRC StorageClass is
`WaitForFirstConsumer`, so the new claim stayed Pending until a Job mounted it. The objects rendered
regardless; `oc create job --from=cronjob/…` copied `gsd-20260905T200913.615850Z.db` (1,224,704
bytes, `integrity_check ok`, `user_version 9`, 169 membership events, 2,579 sync events), a second
run was the idempotent no-op, and a Job running `--check` on the copy reported `sidecar matches`.
The failed `--wait` revision left orphans Helm did not own (deviation 9); deleted by label, the
claim kept. Recorded in the values comment, the chart README and the runbook.

Repeated on the fixed head the way the docs now say: `helm upgrade` without `--wait` → `deployed`;
a manual Job shipped the newer `gsd-20260905T202405.365178Z.db` (1,224,704 bytes, `integrity_check
ok`) and the claim went `Bound`; `--set backup.offsite.enabled=false` then removed the CronJob,
ServiceAccount and ConfigMap — Helm owned them this time — and the claim stayed, holding two
verified copies.

**The bind Job (operator instruction).** After the finding above the operator asked for a throwaway
pod that binds the claim, with Argo ordering. Implemented as an ordinary Job in the claim's sync wave
(deviation 11 explains why not a Helm hook: post hooks run after `--wait`). Proven on CRC with the
claim deleted first so the bind was a real first bind: `helm upgrade --wait` → `deployed` in 19 s,
claim `Bound`, `…-backup-offsite-bind-5050820a` Complete (`bound: /offsite mounted, 11415085056 bytes
free`), a copy run green, and `--set backup.offsite.enabled=false --wait` removed the Job and CronJob
and kept the claim.

## Verdicts — Cursor

Read-only (no shell, no network in ask mode); every refutation re-measured here.

| Claim | Cursor | Decision |
|---|---|---|
| C1 a faithful, verified copy | REFUTED — the sidecar is written after the rename with no fsync (a crash leaves a 0-byte sidecar beside a good copy); a SIGKILL leaves a `.part`; the source can rotate the picked file mid-copy | **Accepted on durability and the stale `.part`**; the mid-copy rotation is real but the copy is still a verified backup one interval old — noted in the log and shipped next run; Cursor's recursive re-pick rejected (a loop on a busy source, and the six-hourly grain makes the race a curiosity) |
| C2 idempotence and pruning | REFUTED — an empty sidecar raised `IndexError`, uncaught: every later Job red beside a verified copy | **Accepted** — `sidecar_expected` returns None for an empty or malformed sidecar and the script copies again; Cursor's test taken. The single most important finding: a confident wrong signal (Stale) about the only un-refetchable history |
| C3 the read-only double mount | CONFIRMED | — |
| C4 access modes | REFUTED — with `persistence.existingClaim` the chart's derived mode may not be the claim's | **Accepted** — refused unless `persistence.accessMode` is explicit; test taken and extended with the passing case |
| C5 the guards | REFUTED — `hasPrefix "/data/"` accepts `/data/backup/../..`; Sprig's `int "abc"` is 0 so `keep=abc` rendered (both measured here with `helm template`) | **Accepted** — `contains ".."` refusal; `keep` held to `^(0\|[1-9][0-9]*)$`; both tests taken |
| C6 rendered objects and labels | CONFIRMED | — |
| C7 the S3 path | CONFIRMED | — |
| C8 alerts | CONFIRMED | — |
| C9 the runbook | REFUTED — `date` is not in the image (measured: `command -v date` → none), so the pre-restore copy silently did not happen; the `sed` `--check` trick fails on BSD sed and names `/offsite` the S3 path lacks | **Accepted** — Python for the pre-restore copy; a Python JSON edit for the `--check` Job (the same shape the live test used); the S3 caveat stated |
| C10 fidelity | PLAUSIBLE — named the Grafana panel still listing twelve | **Accepted** — the two rows and the title; the full suite had failed on exactly that invariant |

Not asked, accepted: the S3 restore order (`-wal`/`-shm` removal first, then the stream-in); the
selector-label test strengthened. Not asked, noted: `tests/test_metrics.py` renders without the
module on, so it never parses the two new expressions — they are held by `test_chart_backup_offsite.py`
instead.
