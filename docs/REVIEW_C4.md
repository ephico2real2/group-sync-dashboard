# Review — PR #87, C4: idle timeout with a countdown

Adversarial second-opinion pass, 2026-09-06, on the ten-claim brief for #87
(`docs/specs/SPEC_C4_idle_timeout.md` applied; application 0.16.0, chart 0.18.0; the spec's
deviations are in its orchestrator's notes). Everything in this module runs locally — the config
and whoami tests, the chart guards through `helm template`, and ten Playwright tests that drive the
model with `page.clock` — so both reviewers could measure. Cursor (Grok 4.6 high fast, ask mode) and
Codex (gpt-5.6-sol, xhigh) are recorded below; every verdict was re-checked here before a decision.

## Live run on the reference cluster

`session.idleTimeout.enabled=true minutes=1 warningSeconds=30` on CRC, a real OpenShift login as
kubeadmin, then no activity: the dialog opened after 29.4 s with the countdown at 30, focus on "Stay
signed in" and `#wrap` inert; at 59.4 s the page landed on `/signed-out` — the proxy's `sign_out` is
the first hop and redirects to the dashboard's landing page — and a fresh `goto` of the route demanded
credentials. `/api/whoami` served `{"enabled": true, "seconds": 60, "warning_seconds": 30}`. The values
were then restored to the defaults.

## Verdicts — Cursor

Read-only (no shell in ask mode); every refutation re-checked against the code.

| Claim | Cursor | Decision |
|---|---|---|
| C1 states | REFUTED — a late tick goes active → expired without the dialog (correct: late, never early); `idleStay` after expiry was reachable via Escape after "Sign out now" | **Accepted** — `idleStay` refuses once expired, "Sign out now" is `idleExpire`; the late-tick skip stays as the spec's stated behaviour |
| C2 activity | CONFIRMED | — |
| C3 enforcement | REFUTED — "Sign out now" left the rows on screen; an in-flight `refresh()` could repaint rows or `showSessionEnded()` after the timer | **Accepted** — `idleExpire` bumps `navSeq`; `refresh()` returns when expired at start, before painting and in its catch |
| C4 the poll gate | REFUTED — `popstate` and header clicks call `refresh()` straight | **Accepted** — `popstate` gated while suspended; the `refresh()` guards cover the header after expiry |
| C5 accessibility | REFUTED — the skip link is outside `#wrap` and stayed reachable | **Accepted** — `setIdleChrome` makes it inert with `#wrap` |
| C6 the server side | REFUTED — `tests/test_activity.py`'s exact whoami body was red on the head (the full suite confirmed: 1 failed); a cap ≤ 0 treated as a cap; YAML `1.5` truncated | **Accepted**, all three, with Cursor's tests |
| C7 the chart | PLAUSIBLE (no render available to it) | — ; the six chart tests run here |
| C8 tests | REFUTED — four behaviours untested | **Accepted** — Cursor's four Playwright tests taken |
| C9 docs | REFUTED — values/README/CHANGELOG described `minutes` as the time before the countdown; `API.md` stale | **Accepted** — wording fixed everywhere; the spec's Goal sentence noted in deviation 8 |
| C10 the live run | PLAUSIBLE — predicted `sign_out` redirects to `/signed-out` | — ; measured above exactly so |

## Verdicts — Codex

Codex (gpt-5.6-sol, xhigh) reviewed the first head 721d412 with a pinned-code harness (its sandbox
refused pytest's temp directory); the branch moved to Cursor's fixes during its run.

| Claim | Codex | Decision |
|---|---|---|
| C1 states | REFUTED — "Sign out now" not terminal; Escape revived (as Cursor) | already applied |
| C2 activity | CONFIRMED (harness: broadcasts, backdrop, other tab, no channel) | — |
| C3 enforcement | REFUTED — in-flight refresh repaints; a late auth response shows the ended panel (as Cursor) | already applied; the catch also returns when superseded |
| C4 the poll gate | REFUTED — `popstate` AND `hashchange` call `refresh()` straight | **Accepted** — `hashchange` gated too; the Back test also edits the hash |
| C5 accessibility | REFUTED — the skip link outside `#wrap` (as Cursor); dialog contrast measured 7.7–19.2 | already applied |
| C6 the server side | REFUTED — YAML `true`/`1.5` become one minute through `_num_setting(int)`; disagrees with Cursor that 0/−1 is "no cap" | **Accepted** — `_idle_integer_setting` refuses booleans and floats as text for both numbers; the cap disagreement recorded, the guard kept as harmless and unreachable |
| C7 the chart | REFUTED — an unquoted `cookie.expire: 0` renders `4h` (Helm's `default` treats numeric zero as empty) | **Accepted** — `gsd.cookieExpire` returns `0` as typed and the deployment refuses it by name; Codex's test taken for both `--set` forms |
| C8 tests | REFUTED — the untested behaviours (as Cursor) | already applied |
| C9 docs | REFUTED — "never polled" in the design, the docstring and the page, and the "app's own /sign-out" comment, contradict `refresh()` fetching whoami every cycle | **Accepted** — all three corrected; Codex's prose test rejected |
| C10 the live run | PLAUSIBLE (no cluster) | — ; measured above |

Not asked, accepted: the chart README's `skipAuthRegex` row was the pre-C4 three-path regex.

## Outcome

Two first passes on two heads; between them the defects that mattered were about expiry being
final and complete — a refresh already in flight, "Sign out now", browser history, the skip link —
plus the whole-number rule for the idle settings, the exact whoami consumers, Helm's numeric zero,
and three stale sentences about whoami polling. Rejected: the prose-asserting tests. Live on CRC
before the reviews: the countdown at 29.4 s, expiry at 59.4 s, credentials demanded on re-entry. A
second pass by both reviewers runs on the fixed head before merge.
