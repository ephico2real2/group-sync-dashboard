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
