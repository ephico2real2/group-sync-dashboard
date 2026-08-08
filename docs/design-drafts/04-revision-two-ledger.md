# Revision-two ledger — 17 findings, verified one at a time

Status: PENDING / CONFIRMED / CONFIRMED-WITH-CORRECTION / REJECTED
"Correction" = the finding is right but its stated reasoning or bound is not, and revision two must
carry the corrected version rather than the reviewer's wording.

## Lens 1 — the four-hour model

| id | status | what I verified myself |
|---|---|---|
| L1-F1 origin persists across sessions | CONFIRMED | The degeneration is unavoidable, not sloppiness: distinguishing "first load of THIS session" from "first load ever" requires observing a session boundary, which the premise (HttpOnly cookie, no session-age header) says is impossible. So the write rule is either always-overwrite (then it is `now`, not an origin) or write-if-absent (then it is stale across sessions). There is no third option. My "late, never early" claim is inverted. |
| L1-F2 clock jump fires early | CONFIRMED | Wall-clock arithmetic with no monotonic source; a forward NTP correction moves the deadline earlier by the correction. Sleep is genuinely sound (elapsed matches), jumps are not — the finding draws that distinction correctly. |
| L1-F3 never-fires voids FORCED silently | CONFIRMED | Including its correction of MY example: `localStorage` is per-origin and shared, so a second tab reads the first tab's origin and fires ON TIME. My "tab opened an hour in fires an hour late" was wrong. |
| L1-F4 model not worth it as a trigger | **CONFIRMED-WITH-CORRECTION** | The design is right and better than mine — enforcement keys off a server event, not a client clock, and is premise-independent. But its bound is wrong. See below. |
| L1-F5 cross-browser blast / double-fire | CONFIRMED | An account-wide SSO logout does affect other browsers' next re-auth; worth the sentence it asks for. |

### The correction to L1-F4

It claims: "anyone still present at 4h is active, so the presence-gated 30s poll surfaces the death
within one interval — never early, **late by at most the poll interval**."

`pollTick()` suspends on a hidden tab, not only on inactivity — it returns the reason-string `"hidden"`
before it returns `"idle"`. So a tab that is hidden but recently-active (the reader interacted, then
switched tabs for five minutes, and the 4h cap falls in those five minutes) makes no request at all, and
the death is detected only when `visibilitychange` fires on their return.

`pollTick` in fact suppresses for FOUR reasons in order — `"over"`, `"warned"`, `"hidden"`, `"idle"` —
so hidden tabs are only one of them. `"warned"` matters too: while the advisory warning dialog is open
the poll is deliberately suppressed (a poll there would re-stamp the cookie and answer the presence
question for the reader), so the two minutes around the modelled deadline are also blind. And `"idle"`
begins after `IDLE_SUSPEND_MS` (2 minutes), long before the 30-minute idle timeout fires.

The true bound is therefore: detection occurs at the earlier of the reader's next activity-or-focus
(both of which force a `pollTick`) and the idle timer firing at 30m — so **late by at most the idle
timeout**, not the poll interval, and never early. Both routes end in the sign-out chain: the first via
the failover, the second via the idle path's own `sign_out`.

The design consequence is benign, and this is why the finding survives correction rather than being
rejected: throughout that window the cookie is already dead, so the reader has no access to lose. Only
the SSO-logout POST is late, which delays when the credential prompt is enforced — it never grants
anything. Revision two must state the bound as the idle timeout and say why lateness costs nothing,
rather than repeat "one poll interval", which a maintainer would find false the first time they
measured it.

### Still unverifiable without a lab login

L1-F1's headline sequence needs one premise I have not established: that a dead proxy cookie produces a
SILENT re-issue in a real browser. It is well-supported (the known OpenShift behaviour, this cluster's
365-day token, no inactivity timeout) but it is inference, not measurement. Revision two marks it as
such. It does not change F1's verdict — the stale-origin early fire happens on any second session,
silent or prompted.

## Lens 2 — the sign-out path

Grounded in `openshift/oauth-server` `pkg/server/logout/logout.go`, which I fetched and read rather
than taking the lens's reading on trust.

| id | status | what I verified myself |
|---|---|---|
| forced-relogin-is-idp-dependent | CONFIRMED | The handler calls `InvalidateAuthentication(w, &user.DefaultInfo{})` — it clears the oauth-server's OWN session and nothing else. An upstream IdP's session is structurally out of its reach, so behind external SSO the next authorize can re-authenticate silently. This is true by construction, not pending measurement — the distinction the lens drew is right. |
| post-landing-is-a-dead-end | CONFIRMED TWICE | Source: without a valid `then` the handler sends no body and no redirect — an implicit 200 with an empty body. And my own earlier curl measured exactly that: `POST /logout` → 200, no `Location`, empty body. A blank page on the OAuth host. |
| autosubmit-channel-unspecified | CONFIRMED | From the proxy source read earlier: `LogoutRedirectURL` is one fixed string handed straight to `http.Redirect`. Manual, idle and absolute sign-outs therefore arrive at `/signed-out` indistinguishably, so my consent asymmetry was unimplementable as specified. |
| samesite-and-csrf | CONFIRMED SOUND, **with a correction** | Source confirms POST-only, NO CSRF validation, and an explicit `TODO` conceding "this endpoint is invokable via JS". But see the correction below — the lens's SameSite reasoning is wrong in our topology, in the direction that makes the mechanism MORE reliable. |
| d4-replacement | CONFIRMED | Reading my own D4: `oauthServerLogoutUrl` empty by default means step 3 is omitted, so at the chart's own defaults R1's headline forced re-login does not exist. My text, my error. |
| idle-path-asymmetry | CONFIRMED | Also my own text: D4 names the manual button and the 4h auto-submit and never says what the idle path — R1's FIRST-listed control — gets when it lands on the same page. |

### The correction to the SameSite reasoning

The lens states the `ssn` cookie "sets no SameSite (so Lax-default Chrome/Firefox/Edge withhold it from
the POST)". That treats the POST as cross-site. In the normal OpenShift topology it is not: the
dashboard and the OAuth server are both `*.apps.<cluster-domain>`, so they share a registrable domain
and the request is **same-site**. Measured on this cluster — dashboard `…apps-crc.testing`, oauth
`…apps-crc.testing`, same registrable domain.

The consequence points the same way as the lens's conclusion but for a better reason: the cookie IS
sent, and the `Set-Cookie` overwrite is a first-party write rather than a third-party one subject to
blocking. So the mechanism is more robust than the lens assumed — and its conclusion (the POST works)
survives its own faulty premise. Revision two must not repeat the cross-site claim, because an operator
on a cluster where the two hosts genuinely differ would draw the opposite conclusion from it.

## Lens 3 — the three-policy restructure

| id | status | what I verified myself |
|---|---|---|
| L3-1 countdown never arms | CONFIRMED, decisively | The body's `initSession` guard is `if (!who || !who.authenticated || !s || !s.cookie_expire_seconds || !s.cookie_refresh_seconds) return;`. With `refresh: 0`, `!0` is true and it returns early — `sessionModel` stays null and nothing arms. My sentence "the body's design essentially unchanged … only the source of the numbers changes" was flatly wrong: applying my reconciliation as written ships NO idle warning and NO idle sign-out, which is R1's first control. |
| L3-2 ConfigMap contradiction | CONFIRMED | My own R3: the prose retains `session_cookie_refresh_seconds` "for an operator who enables refresh deliberately", while the ConfigMap row lists only three keys and drops `sessionCookieRefresh`. The app would then report refresh off while the sidecar was told otherwise. |
| L3-3 validation incomplete | CONFIRMED, and it adds two I had missed | `idleTimeout + warnBefore <= expire`, or a hair-under-expire idle opens an EXTENDABLE warning inside the absolute cap's death window — a stay button that cannot work. And `warnBefore <= idleTimeout/2`, because an open warning suspends the poll (`pollTick` returns `"warned"`), so a long warn stales the page for its whole length. It also supplies disable semantics for the kiosk case and dig-based helpers so `session: null` falls back. |
| L3-4 §5's flip list is stale | CONFIRMED | §5.1 states "The 30m expire stays and becomes an absolute (login+30m) timeout" — its five-assertion list was computed for a world where expire stayed 30m. R1 moves it to 4h, so assertions §5 never names also flip. |
| L3-5 tests: 5 to delete, ~25 missing | CONFIRMED | All five deletion targets exist in the body. And it caught something exact: my R3 table names **zero** env overrides for the new keys, where the body names `GSD_SESSION_COOKIE_EXPIRE` seven times — I dropped a row the body had. |
| L3-6 `/signed-out` cannot carry a script | CONFIRMED | B3's contract, verbatim: "no `<style>` block, **no scripts**, no external assets beyond `/static/app.css` and `/static/favicon.svg`". It is served as a static `FileResponse`. So an auto-submitted POST from that page is impossible without breaking the contract. |

## Arbiter-originated design change — forced by L3-6 + lens2-post-landing

L3-6 and the blank-page finding together invalidate **both** proposed sign-out designs: mine
auto-submitted from `/signed-out` (which cannot hold a script), and the lens's detection path submits
"the D4 sign-out chain" whose POST step lives on that same script-free page. Neither works.

**Move the SSO POST to the main page, BEFORE navigating to sign_out.** The main page already has
JavaScript and already knows which sign-out this is:

```
1. (idle expiry | absolute detection | manual click)  — on the main page, context known
2. if oauthServerLogoutUrl is set: POST to it, same-site, credentials included, response unread
3. navigate to <prefix>/sign_out  — proxy clears its cookie, redirects to /signed-out
4. /signed-out renders, script-free, and states honestly what ended
```

Every problem dissolves at once: the reader never navigates to the OAuth host, so the empty-body blank
page cannot happen; `/signed-out` keeps B3's no-scripts contract; the "which arrival is this" channel
problem disappears because the decision is made where the context lives, not inferred from a fixed
`-logout-url`; and the manual-versus-policy asymmetry becomes an ordinary UI choice on our own page.
Step 2 is same-site (measured: both hosts share `apps-crc.testing`), form-encoded, so it is a
CORS-safelisted request needing no preflight, and the `Set-Cookie` that clears `ssn` is a first-party
write. A failed or unreachable POST is caught and step 3 proceeds regardless — the dashboard session
ends either way, and the page's wording is already conditional.

**Unverified**: that the POST lands its `Set-Cookie` and that the next authorize then prompts. Testable
on the lab; needs one login.

## Tally

17 findings: **17 confirmed**, 0 rejected. Two carry corrections to the reviewer's own reasoning
(L1-F4's bound, lens2's SameSite premise), and one forces a design change neither of us proposed.
