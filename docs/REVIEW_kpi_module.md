# Review record — the KPI module (#156, PR #206)

Branch `feat/kpi-module`, base `main`. Head reviewed: `8c946d2`. Three reviewers on one brief of ten
claims (`review_brief_156.md` in the session scratchpad; restated in the table): Grok 4.6 (Cursor, ask
mode — no shell; verdicts from the source), Codex (GPT-5.6, xhigh — scraped the real app in a copy,
drove the counters, the rollup, the cgroup files and a main-vs-head byte diff of both expositions),
OB3 (Opus 5 — the same, plus a 60-step randomised insert/prune/scrape drive of the watermark
counters, a 300k-row cost measurement of the watermark queries, a spoof attempt on both login-capture
sources and a threshold-boundary drive of the rollup). Every verdict was re-checked on the branch before
a decision. Line numbers are those of `8c946d2` and are not maintained.

## Claims × reviewers × decision

| # | Claim | Grok | Codex | OB3 | Re-check / decision |
|---|---|---|---|---|---|
| K1 | The privacy class is enforced and every public label is bounded | REFUTED — `provider` is a log field | REFUTED — a person's name in `provider` reached `/metrics` | PLAUSIBLE — bounded on the measured apps; the audit-log path's provider is the CLIENT's request-path text | **F1, accepted twice.** The renderer refuses an internal definition (confirmed by all three); the `provider` label did not have the dashboard's own bound. Bounded at the definition to the identity providers the cluster's Identity objects name plus `unknown` (`Store.identity_providers`, measured live on CRC: `ldap-local`, `developer`, `ceo_rnd_oim`, `my-provider`), everything else folding into `other`; AND bounded at the source (OB3): `audit_event_dict` drops a `/login/<x>` provider the OAuth CR does not configure and falls back to the identity match. Codex's two-value anonymised class rejected — an IdP's name is operator configuration, the same class as the `schedule` label, and the mock counts providers |
| K2 | The watermark counters: one statement, retention-proof, baseline excluded, under the snapshot | REFUTED (b) — retention deletes by time, not by watermark | REFUTED (b) — a row above the watermark deleted before a scrape | CONFIRMED with the premise corrected — never decreases; may skip | **Accepted on the fact, both fixes rejected.** (a), (c), (d) hold. A row already past retention when it ARRIVES (a backlog) can be pruned before a scrape counts it: not counted, never un-counted; the counter cannot go backwards (OB3's 60-step drive). Moving the count into the capture path (Grok) or gating retention on the watermark (Codex) couples two subsystems for rows that are outside retention by definition. The docstring says so now |
| K3 | Unavailable is not zero | REFUTED — a partial `cpu.stat` read as zeros | REFUTED — `cpu.max` `50000 0` divided; `/api/kpi` 500 | PLAUSIBLE — the same zero period | **F2/F3, accepted.** The bandwidth lines travel together or the throttling families are omitted; a partial set is garbled; a zero period is garbled (it 500'd `/api/kpi` and the usage feed — every pull then `error`) |
| K4 | The CPU rate: monotonic, clamped, None without two samples | REFUTED — `throttled_fraction` −0.1 on a reset | REFUTED — −0.9 | CONFIRMED; PLAUSIBLE on the invitation | **Accepted.** Clamped to [0, 1]; None when either sample lacks the bandwidth lines |
| K5 | The rollup: leader only, once a day, from the live scalars, after a successful poll | REFUTED — not gated on a successful poll | REFUTED — a stale row after `unreachable` | REFUTED — the same | **F4, accepted.** `_after_poll` runs on every outcome; the day's first cycle can be an `unreachable` at 00:01 whose row `INSERT OR IGNORE` would then keep. `_rollup_kpi` reads the poll outcome first. Midnight: a late first success writes that hour's state under that date; a day with no successful poll has no row (not backfilled) |
| K6 | The predicates are spelled once | CONFIRMED | REFUTED — the Groups report's Python (`not sync_provider`) | CONFIRMED as scoped; a fourth and fifth spelling outside the diff | **N3, accepted.** `gsd/kpi/predicates.py` carries the Python twins (`is_empty`, `is_unattributed` — `is None`, not falsy, so an empty-string label counts as the SQL counts it); the catalogue reads them. The Overview door line (`index.html`) is a pre-existing count over the same rows, out of this PR's scope |
| K7 | The API: host tier, `@consistent`, served clusters only, the report block | CONFIRMED | CONFIRMED (self 403; hidden cluster absent) | CONFIRMED | Holds |
| K8 | Behaviour preservation | PLAUSIBLE | REFUTED — `gsd_retention_rows_deleted_total` gains `table="kpi_daily"` | CONFIRMED with that exception, by design | **Accepted on the fact; the claim was over-stated.** Every pre-existing series is byte-identical (OB3: head minus the additions == main, both expositions; store reads and `Snapshot.counts` identical; migration 15 == fresh). A new value on the bounded `table` label is the family's convention (it grew for `binding_event` too); Codex's separate family rejected |
| K9 | The usage feed's `system` key breaks no puller | CONFIRMED | CONFIRMED | CONFIRMED | Holds |
| K10 | The tests and the full suite | PLAUSIBLE | CONFIRMED (28 passed; 3512 passed) | CONFIRMED | Holds; on `main` the file fails at collection (`gsd.kpi` absent), the K6 equality test passes on `main` when run alone |

## Volunteered

- **N2 / F7 — the watermark queries scanned the cluster's rows on every scrape** (Grok N2, Codex, OB3 N1 — OB3
  measured the cost at 300k rows). Accepted: migration 16 adds `(cluster_id, id)` on both event tables, and
  `test_the_watermark_queries_seek_their_index` pins the plan.
- **A CPU rate over a sliver** (OB3 N2; found independently on CRC by the live check before the reports
  landed — the two cluster threads pulled the feed milliseconds apart and the second view read
  `cores_used 0.0813` over `0.0 s`). Accepted at a 5 s floor, with the poll thread taking a baseline every
  cycle so a page's rate spans at most one poll interval.
- **N4 (OB3, doc-only)** — the watermark docstring's "always below the watermark" premise. Reworded with K2.

## Validation

`tests/test_kpi.py` 28 → 37; `tests/test_auditlog.py` + 1. Full hermetic suite from `local-development/`
(`--deselect tests/test_ui.py --deselect tests/test_live_smoke.py`): 3522 passed, 13 skipped. Live on CRC at `a7d2f58`: both
pods' `/metrics` carry the `gsd_process_*` and `gsd_volume_disk_*` families under their `component`
(dashboard: 81 MB of 512Mi, 0.5 CPU, 5 of 120 periods throttled; report: 62 MB of 768Mi, 4 of 144),
`gsd_login_attempts_total` by `developer` / `ldap-local` / `unknown`, `/api/kpi` 200 for `kubeadmin` and
`lateef.o` (the wide tier on this cluster, as `/operator-configs` agrees) and 403 for `jdoe`.
