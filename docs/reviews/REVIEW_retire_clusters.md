# Review — PR #115 (#96): retire clusters removed from the configuration

Adversarial pass on the real code. 2026-09-14. Codex (gpt-5.6-sol, xhigh, shell — ran pytest and probed
the metrics registry and the alert feed) and Cursor (Grok 4.6 high fast, ask mode — traced from source,
marked what needs a process PLAUSIBLE). The orchestrator had already caught and fixed one gap (whoami)
by a forensic pass before the review; the reviewers found two more.

## Verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 retire_absent_clusters is correct | CONFIRMED | CONFIRMED | — |
| C2 the poller reconcile + re-add on the fly | CONFIRMED | CONFIRMED (re-add works) | — |
| C3 every served surface skips retired/disabled | REFUTED (metrics process-signals leak) | CONFIRMED for readers | **F1 accepted** |
| C4 the report service reads retained data, not offered active | CONFIRMED | PLAUSIBLE (reportable via direct CLI — intended) | — |
| C5 tests measure what they claim | REFUTED (coverage gaps) | REFUTED (coverage table) | **F3 accepted** |
| (attack) alert-scope fold | — | REFUTED / finding | **F2 accepted (= Codex fix 2)** |

## Findings

### F1 (Codex) — the process-signal metrics ignored the enabled set

**Finding.** The store-backed `/metrics` families skip a retired cluster (the orchestrator's fix), but the
process-local signal series — `gsd_cluster_poll_duration_seconds` and `gsd_login_capture_unmatched_total`,
emitted from `RuntimeSignals` in `_event_families` — had no enabled check. Codex probed the same registry
before and after a retirement and found `…{cluster="gone"}` still exported. In production a config change
rolls the pod so the signals start empty, but `/metrics` should not be an endpoint that can return a
retired id.

**Re-check.** Confirmed at `metrics.py`: `_event_families` is a separate method from the store loop, so it
never saw the `enabled` rows. Accepted Codex's fix: compute `enabled_ids` in `_gather` from the store rows
and thread it into `_event_families(enabled_ids)`, guarding both signal loops. The registry test
(`TestRetiredClusterLeavesTheMetricRegistry`) fails before and passes after; the two existing signal tests
now upsert an active cluster (process metrics require an active stored row — Codex's note).

### F2 (both reviewers) — an empty alert feed reported the wide `all` scope

**Finding.** Cursor's attack and Codex's fix 2 converged: `list_alerts` starts `scope = TIER_ALL` and only
narrows on a served-but-not-wide cluster. When the new skip (or an all-hidden estate) empties the served
set the loop body never runs, so `scope` stays `"all"` above `alerts: []` — "you are wide and the estate is
green" — while `whoami` for the same reader correctly fails closed to `self`. That is the exact quiet-drop
the feed's `scope` exists to name; the #96 skip made the all-disabled case reachable (before, disabled rows
were walked and resolved as remotes → self).

**Re-check.** Confirmed by construction and by Codex's probe (`ALL_DISABLED_ALERTS scope: all`). Accepted:
track a `served` flag and set `scope = TIER_SELF` when nothing was served, matching whoami's fail-closed.
Tested in `test_no_enabled_cluster_fails_closed_on_the_headline` (the feed now equals
`{"scope":"self","viewer":"root","count":0,"alerts":[]}`), which failed on the pre-fix head.

### F3 (both reviewers) — the retirement test coverage was incomplete

**Finding.** The matrix listed clusters/alerts/whoami/metrics/404 for both retired and disabled, but the
tests covered only some cells (disabled had no alerts/metrics test; retired had no whoami test; history
retention checked only `poll_outcome`, not the process signals).

**Re-check.** Accepted. Added: retired-whoami; disabled-alerts and disabled-metrics (with the disabled
cluster left `unreachable` so it WOULD alert if served); the registry-disappear test (F1); the doc skip
list now names `/api/whoami` and the empty-feed fail-close.

## Not asked / accepted debt

- **Reportable via the direct API/CLI (Cursor C4):** `POST /report/api/runs` / `trigger.py --cluster gone`
  still renders from a retired cluster's retained snapshot — intended ("history kept so a report can still
  read them"); the selector never offers it. No fix.
- **The `#cluster=gone` bookmark (Cursor):** a hash pointing at a now-retired cluster 404s and dead-ends
  the page (as an unknown id already did). Routed to the UI, out of #96's store/API scope — a follow-up
  (absorb the 404, reconcile onto `data.clusters[0]`), not elevated here.
- `readyz` counts configured entries including disabled ones — DEBT-ACCEPTED (a liveness count, not served
  data).

## Outcome

Two accepted code findings (F1 metrics uniformity, F2 the alert fail-close — both reviewers converged on
F2) and the coverage completion (F3). The orchestrator's own pre-review forensic pass had already closed
the whoami surface; the reviewers closed the two it had not. Full suite 2905 passed; the alert fail-close
and the metric-registry drop each verified by a test that fails on the pre-fix head.
