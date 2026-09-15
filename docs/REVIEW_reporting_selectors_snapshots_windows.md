# Review — design PR #127 (multi-dimension selectors, snapshot modes, reporting windows)

Adversarial pass, 2026-09-15, on `docs/DESIGN_reporting_selectors_snapshots_and_windows.md` (design PR
#127, issue #126). Six claims (C1 as-is accuracy, C2 Feature 1, C3 Feature 2, C4 Feature 3, C5
decomposition/tests, C6 next-real-use). Codex ran `gpt-5.6-sol`/xhigh with a shell (read the whole
repo, `git status --short` clean after); Cursor ran `cursor-grok-4.6-high-fast` in ask mode, source
only. Both reviewed the doc against `main`. This is a DESIGN review: corrections are design-level
mechanisms with file:line artefacts; the full-code-snippet-plus-failing-test bar applies at the per-PR
code reviews of P1–P4.

## Verdicts

| Claim | Cursor | Codex | Decision |
|---|---|---|---|
| C1 as-is accuracy | REFUTED (C1e sloppy) | REFUTED (C1c "always" too strong; C1e) | **Accepted (converged)** — wording fixes to §1 |
| C2 Feature 1 (multi-dim selector) | REFUTED | REFUTED | **Accepted (converged)** — new param type, JSON transport, empty-dim semantics, DOM ids, tests |
| C3 Feature 2 (on-demand snapshot) | REFUTED ("not shippable as written") | REFUTED | **Accepted (converged on the problem); mechanism DECIDED — PVC sentinel** |
| C4 Feature 3 (reporting window) | REFUTED | REFUTED | **Accepted (converged)** — kind-gate, wrap predicate, tz, 409, spec.timeZone, fail-closed |
| C5 decomposition/tests | REFUTED | REFUTED | **Accepted (converged)** — full test list, P1→P2→P4→P3, chart-bump via CI diff |
| C6 next-real-use | REFUTED (cost) | PLAUSIBLE (cost) | **Accepted** — corrected cost claim, single-flight, min-age, secret note, evidence-gap alert |

Every load-bearing claim was re-verified by the orchestrator against the code before acceptance
(citations below), per the skill's "CONFIRMED is the weakest verdict" rule.

## C1 — as-is accuracy (converged, accepted)

Both confirmed (a) multi-label capture (`config.py` `namespace_metadata_labels` tuple; `kube.py`
captures every configured key), (b) single selector (`reporting/config.py` `namespace_selector_label`;
`server.py` list_reports; `namespace_access.py`; `common.py`), (d) scheduled CronJobs
(`report-cronjob.yaml` → `trigger.py`). **Fixes:** (C1c, Codex) "writes every interval" → "a
successful leader poll cycle attempts a snapshot after the monotonic deadline; a failed/stalled poll
delays it; no manual/off mode." (C1e, both) the mock has `team` **and** `acme-app` also carries
`kubernetes.io/metadata.name` — not "only team."

## C2 — Feature 1 (converged, accepted)

**Finding.** `validate_params` (`reporting/catalogue/common.py`) has a closed type set with no
object/map branch — the proposed `selectors: {label:[values]}` param is coerced as a string and 422s.
The XOR/50-cap/`MAX_NAMESPACES` are tied to `mnemonics`/`namespaces`. CronJob params are stringified
with Go `%v` (`report-cronjob.yaml`) — a nested map renders `map[k:v]`, not JSON — and `trigger.py`
keeps only a scalar. The current UI/tests assume `{cluster:{label,values}}` (`static/index.html`,
`test_reporting_server.py`, `test_ui.py`, `test_namespace_selector.py`).
**Re-check.** Verified: closed type set; `%v` stringify; the frontend `report-mnemonics` shape.
**Decision — accepted, folded into §3:**
- New `ParamSpec` type `selector-map`: non-empty `dict[str, list[str]]`; keys ⊆ configured selector
  labels; non-empty deduped string values; ≤ `MAX_NAMESPACES` selected values in aggregate; empty
  lists rejected; **an omitted dimension is unconstrained** (not `[]` → every-run-fails).
- XOR is exactly one of `selectors` / legacy `mnemonics` / `namespaces`. Keep `mnemonics` a hidden
  deprecated spec one release, mapping to the first configured label; reject it alongside a replacement.
- Scheduled params move to JSON: a `--params-json` trigger arg rendered `{{ toJson $s.params }}`;
  `--param` kept as a deprecated scalar path. Helm values must not key maps by dotted labels.
- Rolling compat: emit a new `namespaceSelectorDimensions: {cluster:[{label,values}]}` **and** keep
  `namespaceSelectors: {cluster:{label,values}}` (first dimension) one release; the new frontend prefers
  the new field, falls back to the old.
- Frontend: `id="report-selector-<i>"` + `data-selector-label` (a dotted label is not a valid CSS id);
  `form.selectors[label]` bracket notation; generalise the C4 cluster-switch reset to clear `.selectors`.
- `build()`: validate keys against `ctx.namespace_selector_labels`; AND across / OR within; deterministic
  sort; then `MAX_NAMESPACES` + the coverage warning; reject duplicate configured labels (a
  `COUNT(DISTINCT key)=N` impl can never satisfy N otherwise). Storage seam holds — SQL stays in
  `snapshot.py` (`test_storage_seam`); compose per-label `IN` + Python intersect is the clearer default.

## C3 — Feature 2 (converged on the problem; mechanism decided)

**Finding (both).** The proposed dashboard `POST /api/report/snapshot` that VACUUMs is unshippable:
(1) `store.snapshot` is documented POLL-THREAD-ONLY — "from a request handler would put a user's page
behind it" (`store.py`); (2) the dashboard API is GET-only by contract — `test_r6_the_api_is_read_only`
fails any non-GET, and ticket mint is a pure no-work GET (`api.py`); (3) the CronJob authenticates with
an HMAC file (`automountServiceAccountToken: false`) to the report Service only — the dashboard's
oauth-proxy would TokenReview that blob and refuse; the app binds 127.0.0.1 behind the proxy; (4) the
report pod mounts `/data` read-only (`immutable=1`) — it cannot VACUUM; (5) refresh-at-ticket-mint
would let a viewer induce a VACUUM (DoS) and contradicts §8; (6) a pre-lock freshness check → N callers
→ N VACUUMs; (7) manual mode with no interval write → report `readyz` never Ready (`newest_snapshot`
raises).
**Re-check.** All seven verified against the cited lines.
**Decision — accepted; mechanism = PVC sentinel (operator, 2026-09-15), Codex's dashboard-POST
alternative REJECTED.** Rationale: the dashboard's GET-only "PULLS, never writes" contract is a
load-bearing C3-spec principle both reviewers independently flagged; the sentinel preserves it with no
proxy skip-auth write-path and no contract amendment. Folded into §4 / P3:
- The schedule CronJob mounts the shared RWX `/data` and writes a sentinel (e.g.
  `/data/report/.snapshot-request`); the leader poller sees it in its tail and VACUUMs **on the poll
  thread** (the invariant), then deletes it. The trigger polls the existing `GET /report/api/snapshot`
  until the stamp advances, then POSTs the run. Manual UI runs use the newest snapshot (they "run
  anytime" on the latest copy — the operator's stated intent); no viewer-induced VACUUM.
- Codex's operational rigor folded in regardless of mechanism: **single-flight** with the freshness
  re-check **inside** the store lock (else N VACUUMs); a **server-owned `manualMinAgeSeconds` floor**
  (caller cannot force age 0); VACUUM in a bounded worker with a timeout, `finally` cleanup, and
  duration/failure/in-flight metrics (a hung VACUUM must not hold `_lock` forever); still write **one
  snapshot at leader start** in manual mode so `readyz` can go Ready (make `newest_snapshot`'s error and
  the staleness alert **mode-aware**); an explicitly invalid `snapshot.mode` **fails startup** (a typo
  must not silently re-enable the 300s VACUUM); compute the **effective** reporting URL/mode/interval
  first, then enforce the interval floor (the current floor check reads YAML-only `reportingUrl` and is
  bypassable via `GSD_REPORTING_URL`).

## C4 — Feature 3 (converged, accepted)

**Finding.** `principal.kind` is credential type, not schedule origin (`server.py`): gating on
`body.schedule` lets a service curl without `--schedule` bypass; the wrap-midnight/weekday predicate,
queue-time recheck, failure policy, and CronJob timezone are unspecified; the report pod gets `TZ` from
`.Values.timezone` (not `/api/version`, which is dashboard-only).
**Decision — accepted, folded into §5 / P4:**
- Persist an `origin` on `Run` (`viewer` = ticket; `schedule` = service + non-empty schedule; `service`
  = service without schedule). Gate `schedule` **and** `service`; only `viewer` bypasses.
- Half-open predicate: same-day `start ≤ t < end ∧ weekday ∈ days`; wrap (`start>end`)
  `(t≥start ∧ weekday(today)∈days) ∨ (t<end ∧ weekday(today−1)∈days)`. Reject `start==end` and
  empty/duplicate `days`.
- `GSD_REPORT_WINDOW_TIMEZONE = reporting.window.timezone | default .Values.timezone`; do not read
  `/api/version`. Also set CronJob `spec.timeZone` to the same zone (else K8s uses the controller's tz).
- An enabled malformed window **fails closed** (report-service startup failure), never log-and-disable.
- Refuse = **409 before constructing the Run** (`Retry-After`), no stored failed run per ordinary miss;
  `trigger.py` maps 409 → exit 0 ("skipped: outside window"), other 4xx/5xx → exit 1. A run admitted
  then carried past close by the one-worker queue is rechecked by the worker (may become a stored failed
  run). Add a `gsd_report_runs_outside_window_total` metric + WARNING log (no names) so a wrong-tz silent
  evidence-stop is visible; monitor "no successful schedule within its period" as an evidence gap.

## C5 — decomposition & tests (converged, accepted)

- Reorder **P1 → P2 → P4 → P3** (Codex): P4 establishes persisted `origin` and the pre-render window
  gate; P3 installs freshness strictly after it, so a refused run never VACUUMs. These PRs share
  `reporting` config/server/values/helpers/deployment files — sequential, not independent.
- **P1 must not bump the chart** (fixtures only); the per-PR chart bump is enforced by the CI base-diff
  guard (`.github/workflows/ci.yml`), not `test_chart_versions` (which only holds pyproject == appVersion
  == `__version__`).
- Test list, by PR: P2 — `test_namespace_selector`, `test_reporting_server`, `test_ui` (CI-deselected,
  run locally), new trigger JSON test, legacy compat; P4 — same-day + wrap boundaries, anchor weekday,
  DST, viewer/service/schedule origins, queue-crossing, fail-closed config, 409/no-artifact,
  CronJob `spec.timeZone`; P3 — `test_api_contract` R6 stays green (no dashboard write — the sentinel
  keeps it GET-only, so no `test_skip_auth_parity`/contract change), first-ever manual readiness,
  leader/non-leader, single-flight recheck, timeout/failure recovery, automatic-vs-manual alert.
- `test_values_defaults`: add `reporting.window.enabled: false` to `KEPT_OFF` with a reason; assert
  `snapshot.mode` default is exactly `automatic` (a string, not a KEPT_OFF boolean). Run
  `test_environments_readme` + update `environments/README.md` for any tracked CRC override; update the
  chart `README.md` rows (they are in the citation set).

## C6 — next-real-use (accepted)

- Cost claim corrected (§4/§8/§10): manual mode removes **idle** VACUUMs only; `store.snapshot` copies
  the **whole** DB (one file for all clusters), so cost scales with DB size; savings depend on run
  frequency and the freshness bucket — not "once per window." Add a target-scale load test (DB size,
  VACUUM duration, poll delay, N staggered schedules).
- Single-flight + server-owned min-age + bounded timeout (see C3). §8: the sentinel-driven VACUUM is an
  expensive-operation capability — rate-limit/audit; never age 0.
- **Secret note (Codex):** the same HMAC secret signs viewer tickets AND authenticates the service token
  (`ticket.py`, `server.py`), so a service-token holder could mint a viewer ticket to bypass a
  kind-based window. v1 declares the window an **operational rail, non-adversarial to a service-token
  holder** (the token is our own automation); splitting the signing secret from the service bearer is a
  named follow-up.

## Not asked (accepted)

- `reporting.snapshot.keep` is unbounded — `keep: 0` retains every copy (`store.py` prunes only
  `if keep > 0`), a negative value misbehaves. Add a guard/config floor **`keep ≥ 2`** (two copies close
  the newest-path/prune-handoff race) at render and runtime; do not lower `keep` in manual mode.
- The §6 mock example `gsd {mnemonic: gsd}` lacks `app-environment` and would vanish from a
  two-dimension AND — every fixture used for the two-dimension e2e must carry **both** labels (or be
  named an explicit missing-dimension negative case). Fold into P1's fixtures.

## Rejected

- **Codex's dashboard `POST /api/report/snapshot`** (amend R6, skip-auth write-path, report→dashboard
  client). Correctly identified and rigorous, but the operator chose to preserve the dashboard's
  GET-only "PULLS" contract; the PVC sentinel reaches the same freshness for automated runs without a
  contract or proxy change. Recorded so the decision and its reason are not lost.

## Outcome

The as-is grounding was mostly right (C1a–d); the three feature directions are sound, but the doc was
**not implementation-ready**, and both reviewers converged on the fatal Feature-2 seam. All accepted
corrections are folded into the design (Features 1/3/4 mechanisms, the PVC-sentinel Feature 2, the
`P1→P2→P4→P3` reorder, the full test/guard list, the cost and security notes). The storage seam
survives. The design is now ready to implement PR-by-PR, each with its own two-pass code review.
