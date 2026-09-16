# Review — P4, the global reporting window (feat/p4-reporting-window)

Adversarial pass, 2026-09-16, on the P4 implementation (design §5,
`docs/DESIGN_reporting_selectors_snapshots_and_windows.md`; issue #131). Two reviewers on the same
9-claim brief: **Codex (gpt-5.6-sol, xhigh)** with a shell — it measured every claim in a copy — and
**Cursor Claude Fable 5.1 (xhigh)**, ask mode, tracing from source. Every verdict was re-checked here
before a decision; the disagreements between the two are called out and settled with the mechanism.

## Verdicts

| Claim | Codex | Fable | Decision |
|---|---|---|---|
| C1 predicate correct (half-open, wrap, tz) | CONFIRMED | CONFIRMED (345600-check oracle sweep) | — |
| C2 DST edge | REFUTED | REFUTED (F1) | **Accepted — fixed** |
| C3 create_run gate / TOCTOU | REFUTED | CONFIRMED (residual accepted) | **Accepted the race; fixed (one instant)** |
| C4 downgrade-safe loader | REFUTED | CONFIRMED | **Kept as-is** (Fable's analysis wins) |
| C5 worker recheck / metrics | REFUTED | REFUTED (F2) | **Accepted — fixed** |
| C6 chart guard / tz chain / cron | REFUTED | CONFIRMED + F3 | **F3 fixed; two items DEBT-ACCEPTED** |
| C7 metrics carry no names | REFUTED | CONFIRMED | **Codex right (Fable missed the service path) — fixed** |
| C8 fail-closed at startup | CONFIRMED | CONFIRMED | — |
| C9 storage seam / GET-only | CONFIRMED | CONFIRMED | — |
| F4 gauge resets on restart (volunteered) | — | volunteered | **Accepted — fixed** |
| F5 evidence-gap monitor not shipped (volunteered) | — | volunteered | **Routed (future work)** |

## C2 / F1 — the DST spring-forward edge

**Finding (both).** `is_open` admitted an imaginary spring-forward local time, and
`seconds_until_open` stepped the WALL clock onto the nonexistent 02:xx (which `contains` matched),
returning a `Retry-After` that lands still-closed — so a `days={Sun}` schedule that a wrong retry
sent back would miss a whole week.

**Re-check.** Reproduced: the wall-clock step is the bug. Both reviewers gave the same fix.

**Decision.** Accepted; applied Codex's fix in `window.py`: `_local` canonicalises via a UTC round trip
(`astimezone(UTC).astimezone(zone)`) so an imaginary instant becomes real, and `seconds_until_open`
scans REAL instants by stepping UTC. Tests `TestDSTTransitions` (spring gap never admits + retry lands
open; autumn fold found in real time) fail before, pass after.

## C3 — one authoritative instant (the create_run TOCTOU)

**Finding.** Codex: `now()` was called separately for the gate, the id and `requested_at`; a clock
crossing the close between calls admits a run and stamps it out-of-window (`boundary_race=202 …
stored=1`). Fable confirmed the race but accepted it (sub-second, fail-safe — the worker fails it).

**Re-check.** The race is real and the fix is trivial and strictly correct.

**Decision.** Accepted; `create_run` now takes one `requested = now()` and feeds the gate, `new_run_id`
and `requested_at` from it. Test `test_the_gate_id_and_requested_at_come_from_one_instant` (advancing
clock) fails before, passes after.

## C4 — the downgrade-safe loader (KEPT as-is)

**Finding.** Codex REFUTED: the loader drops unknown keys on read AND the restart-recovery rewrite
persists the loss (`future_field_after_rewrite=None`), so a future field is lost across
rollback→rollforward; proposed a preserve-unknowns envelope.

**Re-check.** Fable's forensic analysis is more precise and correct: `_load` only *rewrites* a manifest
for `queued`/`running` runs — which it fails on restart anyway — so the only unknown-key loss is on an
in-flight run crossing a rollback, a run that is terminal-failed regardless. A `done` run's manifest is
never rewritten on load, so its future keys stay on disk. The tolerate-unknown-keys loader already
fixes the actual downgrade trap #131 named (the CRASH). Codex's preserve-on-write envelope adds
complexity for a case that loses nothing a reader needs.

**Decision.** Rejected Codex's preserve-on-write; kept the current loader. Reason recorded here.

## C5 / F2 — a recheck-failed run must be counted finished

**Finding (both).** The worker's window-recheck early return skips the completion `finally`, so
`note_finished` never fires for a run `submit()` already counted submitted —
`submitted_total − finished_total` reads as one run in flight for ever.

**Decision.** Accepted; the recheck-failure block now calls `note_finished(report, "failed", 0.0, 0)`.
Test `TestWorkerWindowRecheck.test_a_recheck_failed_run_is_counted_finished` fails before, passes after.

## C7 — a service schedule label must not carry a name (Codex right; Fable's gap)

**Finding.** Codex REFUTED: a **service token** POSTing `schedule: "Alice Smith"` returned 202,
completed, and exposed `gsd_report_schedule_last_success_timestamp{schedule="Alice Smith"}` on the
public, unauthenticated `/metrics`. Fable CONFIRMED — but only traced the VIEWER path (a viewer cannot
set schedule); it missed that a service token can set an arbitrary string.

**Re-check.** Codex is right; Fable's confirmation had a gap. Even though §8 treats the service token as
non-adversarial, the no-names `/metrics` rule is a hard PUBLIC-exposure invariant that must hold
structurally, not by trusting the caller.

**Decision.** Accepted; `create_run` now bounds `body.schedule` to the chart's own DNS-label
schedule-name shape (`^[a-z0-9]([-a-z0-9]{0,40}[a-z0-9])?$`) — a person's name (spaces, capitals) is a
422. Test `test_a_service_schedule_label_is_bounded_to_a_dns_label` fails before, passes after. (Codex's
stronger "validate against the configured schedule set" is a possible future hardening; the pattern
closes the public-metric hole with no new config wiring and matches what the chart already enforces.)

## C6 / F3 — `reporting.window.enabled` truthiness

**Finding.** Fable F3 (Codex's C6 overlaps): `{{- if $window.enabled }}` is Go-template truthiness, so a
quoted `"false"` (or `--set-string`) rendered `spec.timeZone` on the CronJob and ran the window guard
for a window the app's env told it was DISABLED; a misspelt `"flase"` rendered clean and became a pod
startup failure instead of a render refusal.

**Decision.** Accepted; a `gsd.reportWindowEnabled` helper (the report service's own boolean spellings,
anything else a render failure) is the single source the guard, the CronJob and the Deployment env all
call — they cannot disagree. Tests `test_a_quoted_false_window_neither_gates_nor_sets_the_cron_timezone`
and `test_a_misspelt_window_enabled_refuses_the_render` fail before, pass after. Also added `trim` to the
chart's effective-timezone check so a whitespace-only tz fails at render, not at pod startup.

**DEBT-ACCEPTED (Fable, two items).** (1) An **unknown IANA zone renders clean** — Helm has no tzdb;
fail-closed still holds twice downstream (the API server rejects `spec.timeZone` at apply, and
`config.py#_window_env` fails the pod at startup). (2) The chart is **stricter** than the report
service's `_parse_hhmm`/day parsing (it rejects `9:00` and `mon` that startup would accept) — the safe
direction: a chart-rendered config always passes startup; only a direct-env deployment sees the laxer
parser, which handles valid values fine.

## F4 — the evidence-gap gauge is process-local (fixed)

**Finding (Fable).** `gsd_report_schedule_last_success_timestamp` is in-memory only, so a restart
emptied it and the §5 monitor ("no success within its period") went blind until the next success.

**Decision.** Accepted; `build_report_app` re-arms the gauge from the durable run manifests (the newest
DONE run per schedule) at startup. Test `TestScheduleLastSuccessSurvivesRestart` fails before, passes after.

## Not asked / routed

- **F5 (Fable).** §5's evidence-gap MONITOR (the alert rule) is not shipped in P4 — only the signal.
  P4's decomposition (§9) scopes P4 to the window rail; the alert rule is future work and is routed
  there, to be built with the last-success gauge (now durable per F4) as its input.
- Fable also confirmed (C7 trace) that no `generated_by`/viewer name reaches any metric label, and that
  a junk `origin` in a tampered manifest increments a dict key that is never exported (the collector
  iterates the fixed `("schedule","service")` pair).

## Outcome

Two reviewers, nine claims. Six real defects found and fixed (C2/F1 DST, C3 TOCTOU, C5/F2 metric
balance, C6/F3 enabled-truthiness, C7 public-metric name leak, F4 gauge restart) — each with a
fail-before/pass-after test. One Codex finding rejected on Fable's more precise analysis (C4). Two chart
items accepted as debt with the downstream fail-closed that covers them. One volunteered item (F5)
routed to the alert-rule follow-up. The two reviewers disagreed on C4 (Fable right) and C7 (Codex right —
Fable missed the service path); both disagreements were settled by tracing the mechanism, not by vote.
Re-validated after the fixes: the reporting/window/chart suites and the full suite green; helm lint
clean; the DST, one-instant, label-bound, recheck-balance, truthiness and gauge-seed behaviours proven
by their tests.
