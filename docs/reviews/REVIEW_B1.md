# Review — PR #84, B1: off-volume backup CronJob and restore runbook

Adversarial second-opinion pass, 2026-09-05, on the ten-claim brief for #84
(`docs/specs/SPEC_B1_offsite_backup.md` applied; chart 0.17.0, chart only; the spec's
deviations — fourteen by the end of the review — are in its orchestrator's notes). Both the chart's guards (`helm template`) and the copy
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

## Verdicts — Codex

Codex (gpt-5.6-sol, xhigh) reviewed the original head 30143b6 while the branch moved; its sandbox
refused pytest's temp directory, so its measurements were `helm template` renders, shell expansions
with a stub `aws`, and source reading.

| Claim | Codex | Decision |
|---|---|---|
| C1 a faithful, verified copy | REFUTED — the sidecar digest is of the bytes READ, not what the destination persisted; the sidecar was unfsynced and written after the rename; the source can rotate mid-copy | **Accepted** — destination re-hash before publication (Codex's test taken: a same-length value altered on the destination is now refused with nothing published), ordered publication with rollback (test taken), bounded re-pick (see below) |
| C2 idempotence | REFUTED — the empty-sidecar `IndexError` (as Cursor) | already fixed from Cursor's pass; `sidecar_expected` now also validates the name and the hex |
| C3 read-only double mount | CONFIRMED | — |
| C4 access modes | REFUTED — an existing claim's real mode is unknown to the chart; proposed a new `sourceAccessMode` value | **Fact accepted, value rejected** — `persistence.accessMode` is required explicit with `existingClaim` (Cursor's pass); a second key meaning the same thing was not added |
| C5 the guards | REFUTED — `/data/backup/../..` and `keep=abc` render (measured) | already fixed from Cursor's pass; Codex's `clean` and `^[0-9]+$` variants rejected for the stricter forms |
| C6 objects and labels | CONFIRMED (the ConfigMap byte-equal to the script, 8,519 bytes) | — |
| C7 the S3 path | CONFIRMED — the default command expanded with a stub `aws`, prefix and endpoint cases | — |
| C8 alerts | CONFIRMED — 12 rules, 14 with the module; kube-state-metrics labels checked | — |
| C9 the runbook | REFUTED — `date` (as Cursor); the `sed` rewrite measured to produce one argument | already fixed from Cursor's pass |
| C10 fidelity | CONFIRMED narrowly — the spec's notes and the index are the only extra files | — |

**The re-pick, decided across both reviewers.** Cursor proposed an unbounded recursive re-pick,
Codex an unbounded loop; the first pass here kept the verified copy and logged a note. Both
reviewers' point stands — the destination should end the run holding the newest when the app
rotates backups mid-copy — so the run now re-picks up to three times (`REPICK_ATTEMPTS`) and then
keeps the verified copy and says so, which is the bounded form of what both asked for.

Not asked (Codex): the Grafana panel — already fixed from Cursor's pass; the time-ns runbook test
rejected as prose-asserting.

## Second pass — Cursor (on 6332449)

| Claim | Cursor | Decision |
|---|---|---|
| C1 publication | PLAUSIBLE — every interleaving it attacked leaves a state the next run repairs; deviation 12's "never" was stronger than the code (a SIGKILL between the two renames) | **Wording accepted** — deviation 12 now says so |
| C2 the bounded re-pick | CONFIRMED | — |
| C3 sidecar validation | CONFIRMED (backup names cannot contain a space; `sha256sum -b`'s `*name` is refused as malformed, by design) | — |
| C4 pruning | REFUTED on the claim's wording — a sidecar-less copy beyond `keep` IS removed, and must be, or it would be immortal | **Accepted as a characterisation test**; the code is right, the claim overstated |
| C5 the bind Job | REFUTED — the hash omitted `pullPolicy`, `pullSecrets`, `podSecurityContext`, `nodeSelector`, `tolerations`, all rendered into the immutable pod template | **Accepted** — all hashed; Cursor's test taken (pullPolicy and nodeSelector change the name, an unchanged spec does not). The single most important finding of the pass |
| C6 the guards | PLAUSIBLE — `--set keep=007` reaches the guard as Helm's integer 7 | — ; noted in deviation 13 |
| C7 documentation | CONFIRMED | — |
| C8 fidelity | PLAUSIBLE (no diff available to it) | — |

Not asked, noted in deviation 13: a failure on a second re-pick attempt skips that run's prune; a
hash change while a previous bind Job still runs leaves two bind pods until the older one completes.

## Second pass — Codex (on 6332449; the branch moved to 9c25b7e during its run)

| Claim | Codex | Decision |
|---|---|---|
| C1 publication | PLAUSIBLE — no interleaving found that misleads the next run; fault-injection tests could not run in its sandbox | — |
| C2 the bounded re-pick | REFUTED — it re-picked on any name change, so a vanished pick with an older backup left behind was recopied | **Accepted** — only a name that moved forward is chased; Codex's test taken |
| C3 sidecar validation | REFUTED — `.split()` accepted a newline-separated digest and name (`sha256sum -c` rejects it) and broke a hand-copied name with a space | **Accepted** — one-line regex parser; Codex's test taken, plus the `-b` binary-marker case |
| C4 pruning | REFUTED on wording (as Cursor) | already characterised |
| C5 the bind Job | REFUTED — the hash omitted value-derived fields (as Cursor, already fixed in 9c25b7e) and fixed template content | **Accepted** — `.Chart.Version` joins the hash |
| C6 the guards | CONFIRMED, measured on Helm 3.14 — `-1`, `abc`, `007`, `1.5` refused in both `--set` and `--set-string`; `0`, `14` accepted | — ; settles Cursor's open `007` point |
| C7 documentation | REFUTED on three stale sentences — the script's docstring, the template's "four objects", this record's "eight deviations" | **Accepted**, all three corrected; the prose-asserting test rejected |
| C8 fidelity | CONFIRMED — eleven files, every hunk attributed | — |

## Outcome — final

Four passes over three heads, plus four live runs on the reference cluster and two operator
instructions (the bind Job; it must work with Argo CD). The findings that changed behaviour: the
sidecar's durability and the empty-sidecar crash, the destination re-hash, the ordered publication,
the bounded and forward-only re-pick, strict sidecar parsing, orphan pruning, guards for `..`,
non-numeric `keep` and an existing claim's mode, the bind Job and its complete hash, and runbook
commands the image can run. Rejected with a measured reason: the unbounded re-pick (twice), a second
access-mode value, `clean` and `^[0-9]+$` guard variants, and every prose- or diff-asserting test.
Proof: 33 chart tests and 22 script tests against real `VACUUM INTO` backups; on CRC, `helm upgrade
--wait` binding a fresh claim in 18 s, copies verified with `--check`, the idempotent no-op, and a
clean disable.
