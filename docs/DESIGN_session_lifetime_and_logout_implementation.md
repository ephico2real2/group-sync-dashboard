# Session lifetime and logout — the implementation design

> ## RECONCILIATION — revision two. Read this before applying anything below.
>
> The body of this document was drafted against a brief that has since been overtaken; where the two
> disagree, **this section wins.** Nothing below it has been edited — the reasoning is worth keeping
> intact, and rewriting somebody else's analysis to match a later decision destroys the record of why
> the earlier one looked right.
>
> **Revision one of this section was itself reviewed and was wrong in three places.** All seventeen
> findings were reproduced before being folded in; two of them carry corrections to the reviewer's own
> reasoning, and one forces a design neither of us proposed. The per-finding audit trail — what was
> verified, how, and which corrections were made to the review itself — is
> `docs/design-drafts/04-revision-two-ledger.md`.

## R1. The authoritative policy

| control | value | enforced by | guarantee |
|---|---|---|---|
| idle sign-out | **30m** of no user activity | the page: activity tracking → warning → navigate to `sign_out` | client-decided, server-effected |
| warning before either deadline | **2m** | modal; "Stay signed in" on the **idle** path only | advisory |
| absolute session cap | **4h** | `-cookie-expire=4h`; **detection** of the dead cookie drives the sign-out, not a client timer | server-enforced |
| credential prompt after the cap | best-effort | ending the OAuth server session | **conditional — see R4/D4** |
| `-cookie-refresh` | unset | — | n/a, see R2 |

The fourth row is the change revision one got wrong by omission: the prompt is guaranteed only for
identity providers the OAuth server checks itself.

## R2. Why the body says 30m/5m, and why that is wrong

**A briefing failure of mine.** The workflow that produced the body was launched with "Operator
decisions, fixed: cookie-expire 30m / cookie-refresh 5m". The policy changed while it ran and the brief
was never updated, so it was handed two contradictory sources, read the newer policy, and concluded —
reasonably — that the brief superseded it. Its section 6 therefore states it does *not* implement "the
research doc's earlier auto-POST-to-`/logout` sketch or a 4-hour absolute cap". That inversion is the
reason this section exists rather than edits scattered through the body.

**`cookie-refresh` is unusable, measured, not merely at risk.** `ValidateSessionState` →
`validateToken` sends the token as a query parameter and accepts only HTTP 200:

```
GET  <api>/apis/user.openshift.io/v1/users/~   with Authorization header  ->  200, user "kubeadmin"
GET  <api>/apis/user.openshift.io/v1/users/~?access_token=<token>         ->  403 "system:anonymous"
```

The API server ignored the parameter and treated the caller as anonymous. The provider does not
override `RefreshSessionIfNeeded`, so the default returns `(false, nil)`, `revalidated` stays false, and
`Redeem` populates `session.AccessToken` for every browser login — so the validation runs and fails at
every interval, clearing the cookie. **`-cookie-refresh` is a forced-logout timer on
`provider=openshift`, not a sliding window.**

## R3. Three independent policies, not two derived ones

With refresh off, `-cookie-expire` is an absolute cap measured from login and says nothing about
idleness. The idle timeout becomes a **policy the page owns**, with its own keys.

### The duration contract

| layer | keys | type | at defaults |
|---|---|---|---|
| `values.yaml` | `oauthProxy.cookie.expire` | Go duration | `4h` |
| | `oauthProxy.cookie.refresh` | Go duration, empty = flag omitted | `""` |
| | `session.idleTimeout` | Go duration, empty/`"0"` = idle sign-out disabled | `30m` |
| | `session.warnBefore` | Go duration | `2m` |
| Helm helpers | `gsd.cookieExpire`, `gsd.cookieRefresh`, `gsd.sessionIdleTimeout`, `gsd.sessionWarnBefore` | `dig`-based, so `cookie: null` / `session: null` fall back to the shipped defaults | `4h`, `""`, `30m`, `2m` |
| ConfigMap | `sessionCookieExpire`, **`sessionCookieRefresh`**, `sessionIdleTimeout`, `sessionWarnBefore` | quoted strings, same helpers | `"4h"`, `""`, `"30m"`, `"2m"` |
| `Settings` | `session_cookie_expire_seconds`, `session_cookie_refresh_seconds`, `session_idle_seconds`, `session_warn_seconds` | `int` seconds; malformed raises `ConfigError` naming the key | `14400`, `0`, `1800`, `120` |
| env overrides | `GSD_SESSION_COOKIE_EXPIRE`, `_REFRESH`, **`GSD_SESSION_IDLE_TIMEOUT`**, **`GSD_SESSION_WARN_BEFORE`** | Go duration strings, validated identically | — |
| `/api/whoami` | `session.{cookie_expire_seconds, cookie_refresh_seconds, idle_seconds, warn_seconds}` | JSON ints; `session` is `null` unauthenticated | `14400`, `0`, `1800`, `120` |
| page JS | `sessionModel = { idleMs, warnMs, expireMs, originMs, lastActivityAt }` | ms numbers | — |

`sessionCookieRefresh` stays in the ConfigMap row. Revision one dropped it there while the prose
retained it, which would have had the app report refresh off while the sidecar was told otherwise — the
exact drift the body's one-helper-feeds-both architecture exists to prevent. The env rows are likewise
restored: the body names `GSD_SESSION_COOKIE_EXPIRE` in seven places and revision one named none of them.

### Validation, at BOTH layers

Render time inside the `oauthProxy.enabled` block (the operator is watching, and `ingress.host` already
sets the fail-the-render precedent) **and** in `load_settings` as `ConfigError` (env overrides and
hand-written local configs never meet the chart):

- `warnBefore < idleTimeout`
- `idleTimeout + warnBefore <= expire` — otherwise a hair-under-expire idle opens an **extendable**
  warning inside the absolute cap's own death window, offering a stay button that cannot work
- `warnBefore <= idleTimeout / 2` — an open warning suspends the poll, so a long warn stales the page
  for its whole length
- `idleTimeout >= 5m`, `warnBefore >= 30s` — policy floors; the 5m figure is borrowed from OpenShift's
  own `accessTokenInactivityTimeout` minimum as a sanity line, not a platform constraint
- `refresh < expire` when refresh is set, which the proxy itself enforces at startup
- `idleTimeout` empty or `"0"` disables idle sign-out (the kiosk case) and stands the idle-side checks
  down; the absolute cap still applies

Every guard compares the **resolved** helper values, not the raw keys.

## R4. The deltas

### D1 — `values.yaml`
`refresh: 5m` → `refresh: ""`, carrying the R2 measurement as its comment so the next reader does not
re-enable it hopefully. `expire: 30m` → `4h`. Add the `session` stanza. Everything else in the body's
A2 stands.

### D2 — the app
`Settings` gains `session_idle_seconds` and `session_warn_seconds`, threaded exactly as the body threads
the cookie durations, with the same `ConfigError` behaviour and the env overrides named above. The
refresh default flips to `0`, which the body's parser already reads from `""`.

### D3 — the page

**The idle path is REWRITTEN, not renumbered.** The body derives both its *arming* and its deadline
from the `(expire, refresh)` stamp pair: `initSession` returns early on `!s.cookie_refresh_seconds`, so
at `refresh: 0` nothing arms and the release would ship with no idle warning and no idle sign-out at
all. Revision one's claim that the idle path was "essentially unchanged" was false.

Carried over unchanged: activity tracking (`recordActivity`, the `pointerdown`/`keydown`/`wheel`
choice), poll gating (`pollTick` and its reason-strings), `visibilitychange` handling, the dialog markup
and its a11y machinery. **Superseded outright:** `initSession`'s refresh gate — arm on
`authenticated && session.idle_seconds > 0`; the `{expireMs, refreshMs, lo, hi}` model;
`noteAuthedResponse` and `api()`'s `sentAt` plumbing; `mergeSharedStamp`'s stamp payload;
`SESSION_WARN_MS` as a constant; `staySignedIn`'s re-stamp rationale; and `sessionEnded`'s passive
over-state.

Replacement model: `{ idleMs, warnMs, expireMs, originMs, lastActivityAt }`. The idle deadline is
`lastActivityAt + idleMs`, with `lastActivityAt` shared across tabs through `localStorage` so a
foreground tab's activity moots a background tab's warning. On idle expiry the page **effects** the
sign-out — navigate to `<prefix>/sign_out` — which is what R1 means by client-decided, server-effected.
`staySignedIn` resets `lastActivityAt` only; its `refresh()` remains a data repaint, and with refresh
unset no request extends anything, so the body's keepalive rationale no longer applies.

**The absolute cap is enforced by DETECTION, and modelled only for the warning.** Revision one keyed a
destructive action to `localStorage` and claimed the model "can only ever be late, never early". That is
inverted: `localStorage` persists **across** sessions, so a recorded origin is routinely *older* than
the current session — sign out and back in, or a next-morning silent re-issue — and a timer counting
from it fires **early**, up to and including instantly at load, in a loop. The degeneration is
unavoidable rather than sloppy: telling "first load of this session" from "first load ever" requires
observing a session boundary, which is precisely what the premise says cannot be observed. A forward
clock jump fires it early too. So:

- `-cookie-expire=4h` ends the cookie and the body's dead-session failover detects it. **That detection
  submits the sign-out, not a timer.** With refresh unset the cookie dies only at the cap or a
  deliberate sign-out, and the idle path always leaves through `sign_out`, so anyone still there at 4h
  is active.
- Lateness, stated correctly: `pollTick` suppresses for four reasons in order — `"over"`, `"warned"`,
  `"hidden"`, `"idle"` — so detection waits for the reader's next activity or tab focus, both of which
  force a tick. The bound is **the idle timeout**, not the poll interval as the reviewer's fix claimed,
  because a tab quiet longer than that has its idle timer fire first and leave through `sign_out`
  anyway. Lateness costs nothing: the cookie is already dead throughout that window, so no access is
  granted — only the credential prompt is delayed.
- A `gsd:signed-out` marker, written by every page-initiated sign-out and cleared on the next
  authenticated load, suppresses the automatic SSO step so another tab's deliberate "don't sign out of
  OpenShift" choice is respected. Losing the marker costs one redundant prompt, never a missed cap.
- The origin model survives **only** as the 2-minute advisory warning: write `gsd:session-origin` at
  authenticated load *only if absent*; discard as stale when `now - origin >= expireMs` or
  `origin > now`; clear wherever the marker is written and on `/signed-out`. A wrong warning is a
  bounded annoyance; a wrong forced logout is not, which is why the two are decoupled.
- The absolute warning has **no** "Stay signed in" button. An absolute cap cannot be extended, and a
  button that cannot work is a lie told to somebody mid-review.

### D4 — the sign-out sequence

`-cookie-expire` alone forces nobody to re-authenticate: the proxy clears its own cookie, the browser
restarts the OAuth flow, and the OAuth server re-issues from its own session without prompting. Nothing
above the proxy helps on this cluster either — `accessTokenMaxAgeSeconds` is **31536000 (365 days)** and
`accessTokenInactivityTimeout` is unset.

The OAuth server's logout endpoint, measured and then read in `oauth-server`
`pkg/server/logout/logout.go`:

```
GET  https://oauth-openshift.<domain>/logout   ->  405 Method Not Allowed
POST https://oauth-openshift.<domain>/logout   ->  200, EMPTY BODY, no Location
```

Source facts that shape the design: it is POST-only with **no CSRF validation** (an explicit `TODO`
concedes "this endpoint is invokable via JS"); it calls `InvalidateAuthentication(w,
&user.DefaultInfo{})`, so it never reads the incoming session and overwrites unconditionally; and
without a valid `then` — validated against server-relative URLs or `osin.ValidateUri` — it emits no body
and no redirect.

**Both earlier designs are therefore wrong.** Revision one auto-submitted the form from `/signed-out`;
the reviewer's fix routed its chain through the same page. But B3's contract for that page is "no
`<style>` block, **no scripts**, no external assets", served as a static `FileResponse` — it cannot
submit anything. And navigating to the OAuth host lands the reader on that empty-body blank page,
unread wording and all.

**The POST moves to the main page, before the navigation:**

```
1. idle expiry | absolute detection | manual click   — on the main page, where the context is known
2. if oauthServerLogoutUrl is set and the marker is unset:
     POST it, same-site, credentials included, response unread, failures caught
3. navigate to <prefix>/sign_out                     — proxy clears its cookie, redirects onward
4. /signed-out renders, script-free, and says honestly what ended
```

Every problem dissolves together: the reader never visits the OAuth host, so the blank page cannot
happen; `/signed-out` keeps its no-scripts contract; the "which arrival is this" channel problem
disappears, because `-logout-url` is a single fixed value and the decision no longer needs to be
inferred from it; and the manual-versus-policy asymmetry becomes an ordinary UI choice on our own page.
Step 2 is **same-site** in the normal topology — both hosts are `*.apps.<cluster-domain>`; measured here
as a shared `apps-crc.testing` — so it is form-encoded, CORS-safelisted, needs no preflight, and the
`Set-Cookie` that clears `ssn` is a first-party write. (The reviewer reasoned this as cross-site and
Lax-withheld; that premise is wrong, in the direction that makes the mechanism more reliable, and it
does not matter anyway because the handler never reads the request session.)

**The idle path gets the same treatment as the cap**, and the reasoning points that way rather than the
other: the idle timeout's threat is an unattended unlocked workstation, which is exactly where leaving
the SSO session alive is worst. Revision one named only the manual and 4-hour arrivals.

**Conditionality, which must reach the wording.** Ending the OAuth server session forces a credential
prompt only for providers the OAuth server checks itself — htpasswd, LDAP, kubeadmin. Behind an external
OIDC or request-header IdP the next authorize re-authenticates silently from the upstream session: the
cap then guarantees a fresh token, not a fresh prompt. Chaining an IdP logout is out of scope. So the
modal and `/signed-out` say **"you may be asked to sign in again"**, never "you will be".

`oauthServerLogoutUrl` defaults to **the cluster's own OAuth route**, derived like `gsd.externalHost`
rather than hand-typed — revision one defaulted it empty, which meant R1's headline policy did not exist
at the chart's own defaults, and a hand-typed URL rots silently when a cluster customises the route.
Empty remains a valid explicit choice: step 2 is skipped and the page claims only that the dashboard
session ended.

### D5 — tests

Revision one said the body's five named assertions "flip as §5 describes". Wrong: §5 computed its list
for a world where expire **stayed** 30m, so moving to 4h touches assertions it never names.

**Delete** (behaviour inverted or machinery removed): `test_refresh_disabled_disarms_the_countdown_but_not_the_link`;
`TestSessionModelSoundness` entirely; `test_a_modeled_end_unlatches_when_another_tab_kept_the_session`;
and the `sessionModel.lo` reset assertions inside `test_stay_signed_in_closes_and_resets_the_model` and
`test_escape_counts_as_staying_not_as_dismiss_and_die`, replaced by `lastActivityAt` ones. All five
verified to exist in the body.

**New**, roughly 25 functions across `test_chart_strategy.py` (the session stanza, each relational guard
refused at render, the nulled stanza falling back, the disable semantics, a proxyless render unaffected),
`test_config.py` (`TestSessionPolicySettings`: defaults, duration parsing, malformed naming its key, env
overrides winning and validated, the relational failures, disabled skipping them), `test_session_api.py`
(idle and warn restated unclamped, `/signed-out` with and without the form), and `test_ui.py` (activity
pushing the deadline back, the extendable idle warning, idle expiry effecting a navigation to
`sign_out`, cross-tab activity mooting a warning, the configured warn window, the origin recorded once
and reused across a reload, the absolute warning having no stay button, stay never extending the
absolute deadline, the absolute path forcing the full sign-out, and the manual "Also sign out of
OpenShift" affordance).

**Adjust**: the two whoami exact-shape tests, the three `TestWhoamiSession` duration tests,
`test_defaults_mirror_the_chart`, and the renamed chart defaults test.

## R5. Premises, and their status

| premise | status |
|---|---|
| `cookie-refresh` clears the session on `provider=openshift` | **measured** — 403 `system:anonymous` |
| the httpx timeout bounds only the inter-chunk gap | **measured** — 4.17s dribble under `timeout=1.0` |
| no CSP blocks the POST | **measured** — zero CSP headers from app or proxy |
| `POST /logout` answers 200 with no CSRF token; GET is 405 | **measured** by curl, and confirmed in source |
| the logout never reads the request session, so SameSite cannot defeat it | **read in source** — `InvalidateAuthentication(w, &user.DefaultInfo{})` |
| the dashboard and OAuth hosts are same-site | **measured** — shared registrable domain |
| a cleared OAuth-server session forces a credential prompt | **FALSE behind external SSO — by construction, not pending measurement.** True only for oauth-server-owned IdPs |
| the POST's `Set-Cookie` lands, and the next authorize then prompts | **NOT VERIFIED** — needs one browser login. D4's credential-prompt claim rests on it |
| a dead proxy cookie produces a silent re-issue in a real browser | **INFERRED**, not measured — well-supported but not established here |

Nothing in this section builds machinery on either unverified row: if both fail, the cap still ends the
session on time and the wording is already conditional.

## 1. Contradictions between the drafts, resolved

Each resolution names what was kept, what was dropped, and why. Every snippet in this document
already has these applied — do not consult the drafts for these points.

### 1.1 The whoami session field names — **lens 2's names win**

Lens 2 (API) defined `session: {cookie_expire_seconds, cookie_refresh_seconds}`. Lens 3 (UI)
sketched `{expire_seconds, refresh_seconds}` but stated explicitly: "if the API lens chose
different ones, reconcile to ITS names." Reconciled to the API's names. Changed relative to the
lens 3 draft: `initSession()` (§C5) and the two UI tests that stub whoami
(`test_present_named_and_wired_when_whoami_offers_it`,
`test_refresh_disabled_disarms_the_countdown_but_not_the_link`, §C8).

### 1.2 The duration format in the ConfigMap — **lens 2's strings win, rendered through lens 1's helpers**

Direct conflict: lens 1 rendered pre-computed integers (`sessionCookieExpireSeconds: 1800`, via
its `gsd.durationSeconds` template helper); lens 2 threads the Go-duration **string** the sidecar
flag receives (`sessionCookieExpire: "30m"`) and parses it in `config.py` at startup.

Kept: **lens 2's format.** Reasons:

- The app explicitly supports hand-written config files for local development; a hand-written
  `clusters.yaml` should carry the same spelling as the values file it mimics, not a second
  format (lens 2's own argument, grounded in the repo).
- The env-override path (`GSD_SESSION_COOKIE_EXPIRE`) then also takes Go durations —
  one grammar everywhere, and the app's parser validates the one path the proxy's own flag
  parsing can never catch.
- Lens 2's parser, validation and tests are complete and were executed against 21 vectors.

But the ConfigMap lines are rendered through **lens 1's shared helpers**
(`gsd.cookieExpire`/`gsd.cookieRefresh`), not raw `.Values.oauthProxy.cookie.*` as lens 2 drafted
— lens 2's raw form breaks on a values file that nulls the whole `cookie:` block and misses the
`"0"`→`""` refresh normalisation; the helpers handle both, and using the same helper for the flag
and the ConfigMap is the entire no-drift argument. Consequences applied below: the merged
ConfigMap snippet (§A5), two chart tests re-asserted against strings (§D1), lens 1's
"interface contract" table superseded by §2. Lens 1's `gsd.durationSeconds` helper **stays** —
the render-time `refresh < expire` guard and the NOTES.txt `accessTokenMaxAgeSeconds` comparison
still need it — it simply no longer feeds the ConfigMap.

### 1.3 The skipAuthRegex default — **lens 2's wider regex wins**

Lens 1 shipped `^/(healthz|readyz|metrics|signed-out)$`. Lens 2's cross-lens contract requires
`/static/app.css` and `/static/favicon.svg` admitted too, because `/signed-out` links both (the
CSP house rule forbids inline `<style>`, so the stylesheet cannot be inlined) and at the moment
that page renders the session cookie is *gone* — behind the proxy its subresource requests bounce
to the sign-in response and the logout landing page renders unstyled. Kept: lens 2's regex,

    ^/(healthz|readyz|metrics|signed-out|static/(app\.css|favicon\.svg))$

Exactly those two assets — both pure presentation, no data; the vendored API-docs JS stays
authenticated. **One consequence neither draft surfaced, decided here:** `app.css` declares
`@font-face` sources under `/static/vendor/*.woff2`, which stay behind the proxy — on the
signed-out page those font fetches fail and the browser falls back to the stack's system fonts.
Accepted deliberately: the page is transient and textual, the degradation is purely cosmetic, and
widening the unauthenticated surface by six more files to avoid it is the wrong trade. The
values.yaml comment states it (§A2). Consequences applied: values.yaml default (§A2), the chart
regex test extended to the two assets and to non-matching `/static` paths (§D1), the chart README
row (§A8). Note the value is **single-quoted** in values.yaml: it now contains `\.`, which a
double-quoted YAML scalar would try to read as an escape sequence.

### 1.4 The keepalive — **no dedicated endpoint (both agree); the vehicle is lens 3's `refresh()`**

Both drafts reject a `/api/keepalive` endpoint for the same verified reason: the *proxy* extends
the cookie, on any proxied request — the app has no session to extend, and "authenticated but not
session-extending" does not exist in this proxy. They differ on the vehicle: lens 2 described
"Stay signed in" as one interaction-marked `GET /api/whoami`; lens 3 implemented it as an
un-`auto`'d `refresh()` (interaction-marked data fetches). Kept: **lens 3's `refresh()`** — it
satisfies every constraint lens 2 set (human-driven, never on a timer, honestly
interaction-marked), and it additionally repaints the stale data the reader is about to keep
using and doubles as the truth-probe through `api()`'s typed dead-session error. One edit
follows: the whoami docstring's final paragraph no longer claims the stay button calls it
(§B2, wording adjusted from the lens 2 draft). `/api/whoami` is fetched exactly once, at page
load, and never on a timer — that instruction stays, verbatim, in its docstring.

### 1.5 Boot-lines anchor — corrected against the file

Lens 3's S5 said "replace the final three lines"; the actual tail of the script is four lines
(a comment sits between `refresh();` and the `setInterval`). §C6 states the replacement span
precisely.

Everything else in the drafts was found consistent: `/oauth/sign_out` composed from
`oauthProxyPrefix` in all three; `/signed-out` unauthenticated on the same origin; relative
`-logout-url` default; whoami fetched once; refresh-disabled (`0`) meaning "countdown disarmed,
absolute expiry" end to end.

---

## 2. The duration contract, end to end

One value, typed at every boundary. The operator states each duration **once**; every consumer
below the first row receives it mechanically.

| layer | key / field | type | value at defaults | disabled refresh |
|---|---|---|---|---|
| `values.yaml` (operator types) | `oauthProxy.cookie.expire` / `.refresh` | YAML string, Go duration (`"30m"`, `"1h30m"`) | `30m` / `5m` | `refresh: ""` or `"0"` |
| Helm helpers (normalise once) | `gsd.cookieExpire` / `gsd.cookieRefresh` | string; refresh normalised: `"0"` → `""`, missing → shipped default | `30m` / `5m` | `""` |
| sidecar args (`deployment.yaml`) | `-cookie-expire=` / `-cookie-refresh=` | Go duration string, parsed by the proxy's flag parser | `-cookie-expire=30m` `-cookie-refresh=5m` | `-cookie-refresh` **omitted** |
| ConfigMap (`clusters.yaml`) | `sessionCookieExpire` / `sessionCookieRefresh` | quoted YAML string, **same helper, same spelling** | `"30m"` / `"5m"` | `""` |
| `Settings` (parsed at app startup) | `session_cookie_expire_seconds` / `session_cookie_refresh_seconds` | Python `int` seconds; malformed input **raises `ConfigError`** | `1800` / `300` | `0` |
| env overrides | `GSD_SESSION_COOKIE_EXPIRE` / `_REFRESH` | Go duration string, validated identically | — | `""` or `"0"` |
| `/api/whoami` JSON | `session.cookie_expire_seconds` / `session.cookie_refresh_seconds` | JSON integer; the whole `session` object is `null` when not authenticated | `1800` / `300` | `0` |
| page JS (`sessionModel`) | `expireMs` / `refreshMs` | JS number, milliseconds (`* 1000` in `initSession`) | `1_800_000` / `300_000` | model stays `null` (disarmed) |

Also threaded, same route: `oauthProxy.proxyPrefix` (string, default `/oauth`) → ConfigMap
`oauthProxyPrefix` → `Settings.oauth_proxy_prefix` (validated absolute path, trailing `/`
stripped) → whoami `logout_url` = `<prefix>/sign_out` (string, `null` when not authenticated) →
the header link's `href`.

---

## 3. Implementation sequence

Apply top to bottom. Phase A = chart, B = app, C = UI, D = tests. Chart template comments use
`#` only (never `{{/* */}}` — and a `#` comment is YAML, not Helm, so no `{{ }}` expression may
appear inside one; the one pre-existing `{{- /* */ -}}` block in `oauth-secret.yaml` is left
as-is per the standing instruction not to retro-convert).

### Phase A — chart

#### A1. `charts/group-sync-dashboard/templates/_helpers.tpl` — shared resolvers

**Anchor:** appended at end of file, after the `gsd.accessMode` define.

The expire/refresh values are resolved **once**, in named helpers; the container args, the
render-time guards, and the ConfigMap the app models the countdown from all include these
helpers. The countdown's truthfulness starts here: the numbers the page uses ARE the numbers the
proxy enforces, by construction.

```
# The proxy's cookie-lifetime flag values, resolved once so the container args, the
# ConfigMap the app reads, and the render-time guards cannot disagree. `dig` tolerates a
# values file that nulls the whole cookie block (missing keys fall back to the shipped
# defaults); `default` catches a present-but-empty expire, because an empty -cookie-expire
# would fail the proxy's flag parsing at startup.
{{- define "gsd.cookieExpire" -}}
{{- dig "cookie" "expire" "30m" .Values.oauthProxy | default "30m" -}}
{{- end -}}

# Empty means refresh is disabled and the flag is omitted. "0" normalises to empty: the
# proxy reads 0 and no flag identically, and the pod spec should say what is off by not
# saying it. A MISSING key gets the shipped default; an EXPLICITLY empty one stays off.
{{- define "gsd.cookieRefresh" -}}
{{- $r := dig "cookie" "refresh" "5m" .Values.oauthProxy | toString -}}
{{- if ne $r "0" -}}{{ $r }}{{- end -}}
{{- end -}}

# Go duration string -> seconds (a float for sub-second units), or -1 when it is not a
# duration the proxy could parse. Exists so guards can compare refresh against expire and
# so NOTES.txt can compare expire against the cluster's token lifetime.
{{- define "gsd.durationSeconds" -}}
{{- $s := toString . -}}
{{- if eq $s "0" -}}
0
{{- else if not (regexMatch "^([0-9]+(\\.[0-9]+)?(ns|us|µs|ms|s|m|h))+$" $s) -}}
-1
{{- else -}}
{{- $total := 0.0 -}}
{{- $mult := dict "ns" 0.000000001 "us" 0.000001 "µs" 0.000001 "ms" 0.001 "s" 1.0 "m" 60.0 "h" 3600.0 -}}
{{- range $tok := regexFindAll "[0-9]+(\\.[0-9]+)?(ns|us|µs|ms|s|m|h)" $s -1 -}}
{{- $unit := regexFind "[a-zµ]+$" $tok -}}
{{- $total = addf $total (mulf (float64 (trimSuffix $unit $tok)) (get $mult $unit)) -}}
{{- end -}}
{{- if eq (floor $total) $total -}}{{ int64 $total }}{{- else -}}{{ $total }}{{- end -}}
{{- end -}}
{{- end -}}

# How many key bytes the proxy would actually derive from a cookie secret. Mirrors its
# secretBytes(): a value that reads as URL-safe base64 (padding tolerated) is decoded and
# the DECODED length is padded up to a multiple of four; anything else counts raw. The
# mirror matters in both directions — a naive `len` would reject secrets the proxy
# accepts (32 hex chars decode to 24 bytes) and accept ones it refuses.
{{- define "gsd.cookieSecretBytes" -}}
{{- $s := . -}}
{{- $n := len $s -}}
{{- if not (or (contains "+" $s) (contains "/" $s)) -}}
{{- $t := $s | replace "-" "+" | replace "_" "/" -}}
{{- $t = print $t (repeat (int (mod (sub 4 (mod (len $t) 4)) 4)) "=") -}}
{{- $d := b64dec $t -}}
{{- if not (contains "illegal base64" $d) -}}
{{- $n = add (len $d) (mod (sub 4 (mod (len $d) 4)) 4) -}}
{{- end -}}
{{- end -}}
{{- $n -}}
{{- end -}}
```

Mechanics (measured under `helm template` by lens 1): `dig` returns its default only for a
*missing* key, so `oauthProxy.cookie: null` still yields 30m/5m while an explicit `refresh: ""`
disables refresh — the two intents stay distinguishable. Sprig's `b64dec` returns error text
rather than failing (hence the `contains "illegal base64"` sentinel) and is StdEncoding with
mandatory padding, hence the `-`→`+`, `_`→`/` replacement and computed `=` padding; the `+`/`/`
pre-check preserves the proxy's raw-count fallback for values its URL-safe decode refuses.

#### A2. `charts/group-sync-dashboard/values.yaml` — the stanza

**Anchor:** inside the `oauthProxy:` block. The new `cookie:` block goes immediately after the
`cookieSecret: ""` line (lifetime sits next to the key that signs it). The `skipAuthRegex`
comment and value **replace** the existing four-line comment and
`skipAuthRegex: "^/(healthz|readyz|metrics)$"`. `logoutUrl` and `proxyPrefix` follow directly
after `skipAuthRegex`, before `sar`.

```yaml
  # Session lifetime. Sliding window: any request more than `refresh` after the last
  # re-stamp extends the cookie for a further `expire`, so an active reader is never
  # interrupted and an idle one is signed out between (expire - refresh) and expire of
  # inactivity. Each re-stamp also revalidates the token against the cluster, so a
  # revoked user loses access within one refresh interval — that revalidation, not the
  # sliding, is the main reason to keep refresh on.
  #
  # The page's own background polling pauses when the tab is hidden or the reader idle,
  # so an unattended browser genuinely goes idle here instead of re-stamping forever.
  # A kiosk / wall-screen deployment gets no input events, so its session ends at
  # `expire` by design — give such a cluster a longer expire here, not a UI exemption.
  #
  # Go durations ("30m", "8h", "1h30m"). refresh must be shorter than expire; empty or
  # "0" disables refresh, and the sliding and revalidation with it. Keep expire at or
  # below the cluster's token lifetime (default 24h), or the cookie outlives the token
  # it represents:
  #   oc get oauth cluster -o jsonpath='{.spec.tokenConfig.accessTokenMaxAgeSeconds}'
  cookie:
    expire: 30m
    refresh: 5m

  # Paths served without authentication. The health endpoints MUST be here or kubelet
  # probes receive a 302 to the login page and the pod is killed as unhealthy. /metrics is
  # included so a ServiceMonitor can scrape it; the exporter emits counts and states only,
  # never a group or user name, precisely because it is reachable unauthenticated.
  # /signed-out is the logout landing page and must also stay: behind the proxy it would
  # start a fresh login the moment it loads, so the logout button would undo itself. The
  # two named static assets are the stylesheet and favicon that page links — when it
  # renders the session cookie is already gone, so behind the proxy they would bounce to
  # the sign-in response and the page would arrive unstyled. Exactly those two files and
  # nothing else under /static/: they are pure presentation. (The vendored fonts stay
  # authenticated, so the signed-out page deliberately falls back to system fonts.)
  # Single-quoted because the value contains backslashes, which a double-quoted YAML
  # scalar would try to interpret as escape sequences.
  skipAuthRegex: '^/(healthz|readyz|metrics|signed-out|static/(app\.css|favicon\.svg))$'

  # Where the browser lands after the proxy clears its session cookie. Empty uses the
  # dashboard's own unauthenticated /signed-out page — a relative path on purpose, so no
  # hostname is needed at render time. Signing out of the proxy does NOT end the
  # cluster's own OAuth session (the page says so); on a cluster with a real SSO logout
  # endpoint, set that endpoint's absolute URL here to end the wider session too.
  logoutUrl: ""

  # The URL root the proxy nests its own endpoints under: <prefix>/start, <prefix>/callback,
  # <prefix>/sign_out. Threaded to the flag, the ServiceAccount's redirect URI and the app's
  # logout link from this one key so they cannot drift. Change it only if a path under /oauth
  # must be served by the dashboard itself.
  proxyPrefix: "/oauth"
```

30m/5m per the operator's decision: idle sign-out between 25m and 30m of true inactivity,
revocation latency 5m, cost one `users/~` API call per active user per 5m. `proxyPrefix` feeds
the `-proxy-prefix` flag, the ServiceAccount redirect URI and the ConfigMap **together** (§A3,
§A5, §A6) — a key that fed only the ConfigMap would *create* the drift it exists to prevent. The
flag's default in the fork is `/oauth`, so rendering it explicitly changes nothing on a default
install.

#### A3. `charts/group-sync-dashboard/templates/deployment.yaml` — guards and args

**A3a — render-time guards.** Anchor: immediately after the third existing guard's `{{- end }}`
(the `strategy=RollingUpdate is unsafe…` fail), before `apiVersion: apps/v1` (line 18). The whole
block is inside `.Values.oauthProxy.enabled` so a proxy-less render can never trip over cookie
values it does not use.

```
{{- if .Values.oauthProxy.enabled }}
# Refuse at render time what the proxy would refuse at startup, because its refusal is a
# crash-looping sidecar with the reason buried in `oc logs` while `helm upgrade` reports
# success. The proxy checks that cookie-refresh is strictly less than cookie-expire and
# that both parse as Go durations; these checks are the same ones, moved to install time.
{{- $expire := include "gsd.cookieExpire" . }}
{{- $refresh := include "gsd.cookieRefresh" . }}
{{- $expireSeconds := include "gsd.durationSeconds" $expire }}
{{- if eq $expireSeconds "-1" }}
{{- fail (printf "oauthProxy.cookie.expire %q is not a Go duration the proxy can parse. Use forms like 30m, 8h or 1h30m — a bare number has no unit and is refused, and so is a spelled-out one. The proxy itself would reject this at startup and crash-loop." $expire) }}
{{- end }}
{{- if $refresh }}
{{- $refreshSeconds := include "gsd.durationSeconds" $refresh }}
{{- if eq $refreshSeconds "-1" }}
{{- fail (printf "oauthProxy.cookie.refresh %q is not a Go duration the proxy can parse. Use forms like 5m or 90s, or set it empty (or \"0\") to disable refresh. The proxy itself would reject this at startup and crash-loop." $refresh) }}
{{- end }}
{{- if ge (float64 $refreshSeconds) (float64 $expireSeconds) }}
{{- fail (printf "oauthProxy.cookie.refresh (%s) must be less than oauthProxy.cookie.expire (%s). The proxy enforces exactly this at startup and would crash-loop; a refresh at or above expire also has no meaning — the cookie would die before it could ever be re-stamped." $refresh $expire) }}
{{- end }}
{{- end }}
{{- if and (not .Values.oauthProxy.logoutUrl) (not (contains "signed-out" .Values.oauthProxy.skipAuthRegex)) }}
{{- fail (printf "oauthProxy.skipAuthRegex (%s) no longer covers /signed-out while oauthProxy.logoutUrl is empty, so the logout landing page sits behind the proxy it is supposed to land OUTSIDE of: the redirect from sign_out starts a fresh OAuth flow, the OAuth server re-uses its own session, and the user who clicked \"Sign out\" arrives back signed in. Either keep signed-out in the regex, or point oauthProxy.logoutUrl at an external logout endpoint." .Values.oauthProxy.skipAuthRegex) }}
{{- end }}
{{- end }}
```

The skipAuthRegex guard is a substring check on purpose: the template cannot evaluate the regex
the way the proxy will, so it refuses only the configuration that is *certainly* broken; whether
the regex actually admits `/signed-out` (and the two assets) is asserted properly by the chart
test, which `re.search`es the rendered value (§D1). An operator who sets `logoutUrl` to an
external endpoint is exempt — the chart-served page is then unused.

**A3b — the proxy args.** Anchor: in the `oauth-proxy` container's `args`, between
`- -cookie-secret-file=/etc/proxy/secrets/session_secret` (line 218) and
`- -openshift-service-account=…` (line 219).

```
            - -cookie-secret-file=/etc/proxy/secrets/session_secret
            # Session lifetime — the sliding window values.yaml describes. Both values come
            # through helpers shared with the ConfigMap, so the numbers the app uses to model
            # the session are the numbers the proxy enforces. An empty or "0" refresh omits
            # the flag entirely: the proxy reads 0 and absence identically, and the pod spec
            # should say what is off by not saying it.
            - -cookie-expire={{ include "gsd.cookieExpire" . }}
            {{- with (include "gsd.cookieRefresh" .) }}
            - -cookie-refresh={{ . }}
            {{- end }}
            - -proxy-prefix={{ .Values.oauthProxy.proxyPrefix }}
            # Where the sign-out redirect lands. The default is the dashboard's own
            # unauthenticated /signed-out page, relative on purpose: the browser resolves it
            # against whatever host served it, so rendering needs no cluster lookup and a
            # changed route cannot strand it. The flag's help text says "absolute URL", but
            # the proxy hands the value untouched to an HTTP redirect, which takes a path.
            - -logout-url={{ .Values.oauthProxy.logoutUrl | default "/signed-out" }}
            - -openshift-service-account={{ include "gsd.serviceAccountName" . }}
```

Measured renders (lens 1): defaults → `-cookie-expire=30m` / `-cookie-refresh=5m` /
`-proxy-prefix=/oauth` / `-logout-url=/signed-out`; `refresh=""` and `refresh=0` → no
`-cookie-refresh` line; `cookie: null` → the 30m/5m defaults. The relative `-logout-url` is
verified against the fork's source — `Validate()` never parses it and `SignOut` hands it
untouched to `http.Redirect`, which accepts a path — with one lab confirmation of the 302's
`Location` header in the verification plan; the fallback if that somehow fails is one line:
`- -logout-url={{ .Values.oauthProxy.logoutUrl | default (printf "https://%s/signed-out" (include "gsd.externalHost" .)) }}`
(no new GitOps constraint — `serviceaccount.yaml` already requires `ingress.host` on every
proxy-enabled render).

#### A4. `charts/group-sync-dashboard/templates/oauth-secret.yaml` — the cookie-secret length guard

Complete post-change file (the edits interleave with the existing lookup logic).

```
{{- if .Values.oauthProxy.enabled }}
{{- $name := printf "%s-oauth-cookie" (include "gsd.fullname" .) }}
{{- /*
Generate once, then REUSE. `lookup` reads the Secret that already exists in the cluster, so
an upgrade keeps the same key. Generating inline in the container args — as several
published examples do — produces a fresh value on every `helm upgrade` and silently signs
every existing session out.

`lookup` returns empty on `helm template` and dry-run, which is correct: those must not
depend on cluster state, and the rendered value is not applied.
*/ -}}
{{- $existing := (lookup "v1" "Secret" .Release.Namespace $name) }}
# With cookie-refresh on, the proxy derives an AES key from this secret and refuses to
# start unless it yields 16, 24 or 32 key bytes — a crash-looping sidecar, with the reason
# in its logs while the upgrade reports success. So the same check runs here at render
# time, through gsd.cookieSecretBytes, which mirrors the proxy's own arithmetic (base64
# decoded when the value decodes, counted raw otherwise). The generated randAlpha path
# always passes. The looked-up branch below runs only against a real cluster — the lookup
# is empty under `helm template` and client dry-runs, so it cannot fire on a disconnected
# render.
{{- $refreshOn := ne (include "gsd.cookieRefresh" .) "" }}
{{- if and $refreshOn .Values.oauthProxy.cookieSecret }}
{{- $bytes := include "gsd.cookieSecretBytes" .Values.oauthProxy.cookieSecret }}
{{- if not (has (int $bytes) (list 16 24 32)) }}
{{- fail (printf "oauthProxy.cookieSecret yields %s key bytes, and with oauthProxy.cookie.refresh set it must be 16, 24, or 32 bytes so the proxy can build an AES cipher — it refuses to start otherwise, as a crash-looping sidecar. Supply a raw secret of one of those lengths (e.g. `openssl rand -hex 16` for 32 bytes), or its base64 encoding; a value that parses as base64 is measured after decoding, exactly as the proxy measures it. Alternatively leave cookieSecret empty and the chart generates a valid one." $bytes) }}
{{- end }}
{{- end }}
{{- if and $refreshOn (not .Values.oauthProxy.cookieSecret) $existing }}
{{- $bytes := include "gsd.cookieSecretBytes" (index $existing.data "session_secret" | b64dec) }}
{{- if not (has (int $bytes) (list 16 24 32)) }}
{{- fail (printf "the existing Secret %s holds a session_secret of %s key bytes, and with oauthProxy.cookie.refresh set the proxy needs 16, 24, or 32 to build an AES cipher — it would crash-loop on this upgrade. The chart reuses that Secret on purpose so upgrades do not sign everyone out. It was not generated by this chart (the generated form is always valid); either set a valid oauthProxy.cookieSecret, or delete the Secret and upgrade again to regenerate it — both sign every current session out once." $name $bytes) }}
{{- end }}
{{- end }}
{{- $secret := "" }}
{{- if .Values.oauthProxy.cookieSecret }}
{{- $secret = .Values.oauthProxy.cookieSecret | b64enc }}
{{- else if $existing }}
{{- $secret = index $existing.data "session_secret" }}
{{- else }}
{{- $secret = randAlpha 32 | b64enc }}
{{- end }}
apiVersion: v1
kind: Secret
metadata:
  name: {{ $name }}
  namespace: {{ .Release.Namespace }}
  labels: {{- include "gsd.labels" . | nindent 4 }}
type: Opaque
data:
  session_secret: {{ $secret | quote }}
{{- end }}
```

Why here and not `values.schema.json`: the constraints are relational
(`refresh < expire`; length only when refresh ≠ 0, measured after the proxy's own base64
arithmetic, which JSON Schema cannot express), the error message quality is the deliverable (the
suite asserts on guard text), and a partial schema implies validation the rest of values.yaml
does not have. The proxy needs the AES-sized secret when `cookie-refresh != 0` **or**
`pass-access-token` is set; this chart never sets the latter, so the guard keys on refresh alone
— if that flag is ever added, `$refreshOn` must widen with it.

The proxy's own arithmetic, mirrored (from `options.go` `secretBytes`): a value that parses as
URL-safe base64 is decoded and the decoded length padded up to a multiple of four. This is why
the honest invalid test vector is `"not-a-valid-secret??"` (20 raw bytes, cannot parse as
base64) and why the research doc's proposed vector `"twentybytesexactly1"` must **pass** (padded
to 20 chars, decoded to 14 bytes, padded to 16 — a valid AES key length). §D1 pins both
directions.

#### A5. `charts/group-sync-dashboard/templates/configmap.yaml` — the app's model inputs

**Anchor:** immediately after the `oauthProxyEnabled: {{ .Values.oauthProxy.enabled }}` line
(line 26) and its existing comment, inside the `clusters.yaml: |` block.

```yaml
    # The proxy's route prefix and session shape, restated for /api/whoami. Rendered
    # through the SAME helpers that build the sidecar's flags in deployment.yaml — that
    # identity is the whole trust argument: the session cookie is HttpOnly, so the
    # durations the UI counts down against can never be observed, only restated from the
    # one place that also set them. The durations stay in the proxy's own Go spelling
    # ("30m") and the app parses them at startup, so an operator states each value exactly
    # once and a hand-written local-development config carries the same format as the
    # values file it mimics. Quoted unconditionally: a disabled refresh is the empty
    # string, which unquoted would render a bare nothing that YAML reads as null.
    oauthProxyPrefix: {{ .Values.oauthProxy.proxyPrefix | quote }}
    sessionCookieExpire: {{ include "gsd.cookieExpire" . | quote }}
    sessionCookieRefresh: {{ include "gsd.cookieRefresh" . | quote }}
```

Rendered with defaults: `oauthProxyPrefix: "/oauth"`, `sessionCookieExpire: "30m"`,
`sessionCookieRefresh: "5m"`. With `refresh: ""` or `"0"`: `sessionCookieRefresh: ""`. The
`checksum/config` pod annotation already in `deployment.yaml` rolls the pod when these change,
so a stale model cannot outlive an upgrade.

#### A6. `charts/group-sync-dashboard/templates/serviceaccount.yaml` — the redirect URI tracks the prefix

**Anchor:** the `serviceaccounts.openshift.io/oauth-redirecturi.primary` line (replaced):

```
    # The path segment tracks oauthProxy.proxyPrefix: the proxy registers its callback
    # under that prefix, so a re-nested proxy moves this URI with it.
    serviceaccounts.openshift.io/oauth-redirecturi.primary: 'https://{{ include "gsd.externalHost" . }}{{ .Values.oauthProxy.proxyPrefix }}/callback'
```

Default render is byte-identical to today's (`…/oauth/callback`), so no OAuth client
re-registration happens on upgrade.

#### A7. `charts/group-sync-dashboard/templates/NOTES.txt` — session shape and the token-lifetime warning

**Anchor:** immediately after the `Authentication: OpenShift OAuth…` two-line sentence inside
the `{{- if .Values.oauthProxy.enabled }}` branch.

```
{{- $expire := include "gsd.cookieExpire" . }}
{{- $refresh := include "gsd.cookieRefresh" . }}
{{- if $refresh }}
Sessions: idle sign-out after {{ $expire }} (sliding — activity re-stamps the cookie every
{{ $refresh }}, and each re-stamp revalidates the token, so revoking a user takes effect
within {{ $refresh }}).
{{- else }}
Sessions: sign-out {{ $expire }} after login, absolute. cookie-refresh is disabled, so the
token is never revalidated mid-session — a revoked user keeps access until the cookie dies.
{{- end }}
{{- $oauthCR := lookup "config.openshift.io/v1" "OAuth" "" "cluster" }}
{{- if $oauthCR }}
{{- $maxAge := dig "spec" "tokenConfig" "accessTokenMaxAgeSeconds" 86400 $oauthCR | default 86400 }}
{{- if gt (float64 (include "gsd.durationSeconds" $expire)) (float64 $maxAge) }}

WARNING: oauthProxy.cookie.expire ({{ $expire }}) exceeds this cluster's
accessTokenMaxAgeSeconds ({{ $maxAge }}s), so the proxy cookie outlives the token it
represents.
{{- if $refresh }}
The dead token is caught at the next {{ $refresh }} refresh and the user is signed out
early — harmless, but the extra expire buys nothing.
{{- else }}
With refresh disabled nothing ever rechecks the token, so the session simply outlives
the cluster's own token lifetime. Lower expire, or enable oauthProxy.cookie.refresh.
{{- end }}
{{- end }}
{{- end }}
```

This is a NOTES warning and not a `fail`, deliberately: the OAuth CR is cluster-scoped and often
unreadable by a namespace-scoped installer, and `lookup` is empty on every disconnected render —
a guard would go silent exactly where it is needed most. It degrades honestly: readable CR →
warning when applicable; anything else → the values.yaml comment (§A2, with the `oc get oauth`
one-liner) still stands. The explicit `| default 86400` also covers a CR that sets the field to
`0`, which OpenShift documents as "use the default 24h". (At the shipped 30m default the warning
is unreachable; it exists for operators raising expire toward workday lengths.)

#### A8. Chart README and Chart.yaml

**File:** `charts/group-sync-dashboard/README.md`. **Anchor:** the Authentication values table;
new rows after the `oauthProxy.cookieSecret` row; the existing `oauthProxy.skipAuthRegex` row's
default cell updated in place (pipes inside cells escaped `\|`, matching the existing row):

```markdown
| `oauthProxy.cookie.expire` | `30m` | session cookie lifetime, a Go duration. Sliding when refresh is on: idle sign-out lands between `expire - refresh` and `expire` of inactivity. Keep at or below the cluster's `accessTokenMaxAgeSeconds` (default 24h) or the cookie outlives the token it represents |
| `oauthProxy.cookie.refresh` | `5m` | re-stamp the cookie on the first request older than this, **and revalidate the token against the cluster** — it bounds how long a revoked user keeps access. Empty or `0` disables both; must be less than `expire`, enforced at render time |
| `oauthProxy.skipAuthRegex` | `^/(healthz\|readyz\|metrics\|signed-out\|static/(app\.css\|favicon\.svg))$` | the health paths **must** stay, or kubelet gets a 302 and kills a healthy pod; `/signed-out` and its two assets must stay while `logoutUrl` is empty, or the logout button signs the user straight back in (enforced at render time) or lands on an unstyled page |
| `oauthProxy.logoutUrl` | `""` | where the browser lands after sign-out. Empty = the dashboard's own unauthenticated `/signed-out` page, which says plainly that the cluster's OAuth session is still alive. Set an absolute URL to an SSO logout endpoint for true single sign-out |
| `oauthProxy.proxyPrefix` | `/oauth` | URL root for the proxy's own endpoints (`/oauth/callback`, `/oauth/sign_out`). One key feeds the flag, the ServiceAccount redirect URI and the app's logout link, so they cannot drift |
```

The README's prose Authentication note gains one sentence: *"Sessions idle out after 30 minutes
by default (`oauthProxy.cookie.*`), and the page shows a countdown warning before that
happens."* (Pre-existing staleness noted by lens 1 and left alone: the README still carries an
`oauthProxy.redirectMode` row marked "currently inert" — not new drift from this change.)

**File:** `charts/group-sync-dashboard/Chart.yaml` — `version: 0.1.0` → `version: 0.2.0`.
Minor, not patch, because behaviour changes for existing installs: a 7-day no-refresh cookie
becomes 30m/5m on upgrade — the point of the change, but it deserves the version signal.
`appVersion` untouched.

### Phase B — app

#### B1. `local-development/gsd/config.py`

**B1a — imports.** Anchor: the import block under the module docstring. Post-change block (one
line added, `import re`):

```python
from __future__ import annotations

import logging
import os
import re
import ssl
import threading
from dataclasses import dataclass, field
from pathlib import Path

import yaml
```

**B1b — the parser and the two setting helpers.** Anchor: insert immediately after the
`_bool_setting` function, before `_require`.

```python
# The unit table of Go's time.ParseDuration, which is the grammar of the proxy's
# -cookie-expire and -cookie-refresh flags. Matching it exactly — including sub-second
# units nobody should use here — keeps one invariant: any duration string the sidecar's
# flag parser accepts, this parser accepts, so the pod cannot half-start over format.
# "ms" is listed before "m" because the regex alternation is first-match.
_GO_DURATION_SECONDS = {
    "ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0,
}
_GO_DURATION_TOKEN = re.compile(r"(\d+(?:\.\d+)?)(ns|us|µs|ms|s|m|h)")


def _parse_proxy_duration(value: object, name: str) -> int:
    """Whole seconds from a Go time.ParseDuration string — the proxy flags' own format.

    The ConfigMap threads the SAME '30m' the sidecar flag receives, so one spelling
    serves both consumers and the two cannot drift. Empty and '0' mean disabled, which
    is what they mean to the proxy ('0 to disable' — its own flag help).

    Malformed values RAISE rather than fall back — deliberately unlike _num_setting.
    Those tune SQLite locking, where running on a default beats not running; these
    describe the session the proxy actually enforces, and a silently substituted
    default would make /api/whoami confidently wrong about a security control. Sign
    prefixes are rejected on purpose: Go accepts '-5m', but a negative session length
    here can only be a mistake worth stopping at install, not modelling.
    """
    word = str(value).strip()
    if word in ("", "0"):
        return 0
    pos, total = 0, 0.0
    for match in _GO_DURATION_TOKEN.finditer(word):
        if match.start() != pos:
            break
        total += float(match.group(1)) * _GO_DURATION_SECONDS[match.group(2)]
        pos = match.end()
    if pos != len(word):
        raise ConfigError(
            f"{name}: {value!r} is not a duration like '30m', '90s' or '1h30m' "
            "(Go time.ParseDuration syntax — the same grammar the oauth-proxy's "
            "-cookie-expire/-cookie-refresh flags parse)"
        )
    if 0 < total < 1:
        raise ConfigError(
            f"{name}: {value!r} is under one second, which a session cookie cannot "
            "express — it can only be a typo for a larger unit"
        )
    return int(round(total))


def _duration_setting(raw: dict, env_name: str, yaml_key: str, default_seconds: int) -> int:
    """Env wins over the ConfigMap, mirroring _bool_setting; parse failures raise.

    The error names whichever source actually carried the bad value, because the fix
    lives where the value was written — an env var points at the Deployment, a yaml
    key at the ConfigMap or values file.
    """
    source = os.environ.get(env_name)
    if source is not None:
        return _parse_proxy_duration(source, env_name)
    if yaml_key not in raw:
        return default_seconds
    return _parse_proxy_duration(raw[yaml_key], yaml_key)


def _proxy_prefix_setting(raw: dict) -> str:
    """The proxy's route prefix, normalised so building paths from it is concatenation.

    Strict, because /api/whoami composes the logout link from this: a malformed prefix
    produces a link that 404s INTO the dashboard — the SPA swallows the path and the
    user believes they signed out when nothing happened. Trailing slashes are stripped
    rather than rejected since '/oauth/' states the same intent as '/oauth'.
    """
    source = os.environ.get("GSD_OAUTH_PROXY_PREFIX")
    if source is None:
        source = raw.get("oauthProxyPrefix", "/oauth")
    word = str(source).strip().rstrip("/")
    if not word.startswith("/") or len(word) < 2:
        raise ConfigError(
            f"oauthProxyPrefix: {source!r} must be an absolute path like '/oauth' "
            "— it is the base of the proxy's own routes (sign_in, sign_out, callback)"
        )
    return word
```

**B1c — the `Settings` fields.** Anchor: the existing comment block beginning
`# Whether the oauth-proxy sidecar is in front of us` and the `oauth_proxy_enabled` field
(config.py line ~262). Post-change block, from that comment through `user_activity_enabled`
(which is unchanged and included only to fix the position):

```python
    # Whether the oauth-proxy sidecar is in front of us. The app cannot detect this for
    # itself, and it must not infer it from the presence of X-Forwarded-User — that header
    # is exactly what an unauthenticated caller would supply. Reported by the chart from
    # its own oauthProxy.enabled; false means no identity is trustworthy.
    oauth_proxy_enabled: bool = False
    # ── THE SESSION AS CONFIGURED, NOT AS OBSERVED ─────────────────────────────────────────────────
    # The proxy's route prefix and cookie lifetimes, restated from the chart so /api/whoami can hand
    # them to the UI. RESTATED is the load-bearing word: the session cookie is HttpOnly and the proxy
    # forwards no session-age header, so the real deadline cannot be observed by anyone — only the
    # configured shape can be reported, and it is trustworthy solely because the ConfigMap renders
    # these from the SAME chart values that render the sidecar's -cookie-expire/-cookie-refresh.
    oauth_proxy_prefix: str = "/oauth"
    # Seconds, parsed at startup from the Go-duration spelling the proxy flags use ("30m"), so the
    # chart states each duration exactly once. Defaults mirror the chart's. refresh == 0 means the
    # proxy never re-stamps the cookie: the session is then an absolute cap from login rather than a
    # sliding idle window, and the UI must model it that way (it cannot see the login time).
    session_cookie_expire_seconds: int = 1800
    session_cookie_refresh_seconds: int = 300
    user_activity_enabled: bool = True
```

**B1d — `load_settings`, whole post-change function.** Two insertions relative to today's
function: the validated duration pair before `return Settings(`, and three kwargs after
`oauth_proxy_enabled=...`. Everything else is verbatim today's code.

```python
def load_settings(path: str | Path) -> Settings:
    """Load and validate settings from a YAML file.

    Validation is strict and up-front: a typo in a cluster entry should fail at startup
    with the offending key named, not surface later as a cluster that silently never polls.
    """
    try:
        raw = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    except OSError as exc:
        raise ConfigError(f"cannot read config {str(path)!r}: {exc}") from exc
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {str(path)!r}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"{path}: top level must be a mapping")

    entries = raw.get("clusters") or []
    if not isinstance(entries, list) or not entries:
        raise ConfigError(f"{path}: 'clusters' must be a non-empty list")

    known = {
        "name",
        "apiUrl",
        "tokenEnv",
        "tokenFile",
        "caBundleFile",
        "insecureSkipVerify",
        "enabled",
    }

    clusters: list[ClusterConfig] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        where = f"{path}: clusters[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}: must be a mapping")

        unknown = set(entry) - known
        if unknown:
            raise ConfigError(f"{where}: unknown key(s) {sorted(unknown)}")

        name = str(_require(entry, "name", where))
        if name in seen:
            raise ConfigError(f"{where}: duplicate cluster name {name!r}")
        seen.add(name)

        if "/" in name:
            raise ConfigError(f"{where}: name {name!r} must not contain '/' — it is used in API paths")

        api_url = str(_require(entry, "apiUrl", where)).rstrip("/")
        if not api_url.startswith(("http://", "https://")):
            raise ConfigError(f"{where}: apiUrl must start with http:// or https://")

        if not entry.get("tokenEnv") and not entry.get("tokenFile"):
            raise ConfigError(f"{where}: one of tokenEnv or tokenFile is required")

        insecure = bool(entry.get("insecureSkipVerify", False))
        if insecure and entry.get("caBundleFile"):
            raise ConfigError(
                f"{where}: insecureSkipVerify and caBundleFile are mutually exclusive"
            )

        clusters.append(
            ClusterConfig(
                name=name,
                api_url=api_url,
                token_env=entry.get("tokenEnv"),
                token_file=entry.get("tokenFile"),
                ca_bundle_file=entry.get("caBundleFile"),
                insecure_skip_verify=insecure,
                enabled=bool(entry.get("enabled", True)),
            )
        )

    # Parsed BEFORE the Settings call so the pair can be validated against each other.
    # expire must be positive — the proxy always has a cookie lifetime, so 0 here could
    # only misdescribe it. refresh >= expire is refused because a cookie is only ever
    # re-stamped by a request arriving more than `refresh` after the last stamp, so that
    # combination means no session can ever slide and the "sliding window" the values
    # comment promises is fiction; upstream oauth2_proxy refuses the same pair at its own
    # startup, and matching that keeps the app and the sidecar rejecting the same configs.
    session_expire = _duration_setting(
        raw, "GSD_SESSION_COOKIE_EXPIRE", "sessionCookieExpire", 1800
    )
    session_refresh = _duration_setting(
        raw, "GSD_SESSION_COOKIE_REFRESH", "sessionCookieRefresh", 300
    )
    if session_expire <= 0:
        raise ConfigError(
            "sessionCookieExpire: must be a positive duration like '30m' — the proxy "
            "always enforces a cookie lifetime, so zero could only misdescribe it"
        )
    if session_refresh >= session_expire:
        raise ConfigError(
            f"sessionCookieRefresh ({session_refresh}s) must be 0 (disabled) or shorter "
            f"than sessionCookieExpire ({session_expire}s); a session can only slide if "
            "the proxy re-stamps the cookie before it dies"
        )

    return Settings(
        clusters=clusters,
        poll_interval_seconds=int(raw.get("pollIntervalSeconds", 60)),
        schedule_grace_seconds=int(raw.get("scheduleGraceSeconds", 120)),
        binding_interval_seconds=int(raw.get("bindingIntervalSeconds", 300)),
        login_capture_enabled=str(raw.get("loginCaptureEnabled", "false")).lower() == "true",
        login_capture_namespace=raw.get("loginCaptureNamespace") or "openshift-authentication",
        login_capture_htpasswd_providers=tuple(
            p.strip() for p in str(raw.get("loginCaptureHtpasswdProviders", "developer")).split(",")
            if p.strip()
        ),
        login_retention_days=int(raw.get("loginRetentionDays", 400)),
        # Stripped, because a DN pasted out of `ldapsearch` output arrives with trailing whitespace
        # often enough to matter, and it is compared for exact equality against a Group's ldap.uid.
        cluster_access_group=str(raw.get("clusterAccessGroup", "") or "").strip(),
        request_timeout_seconds=float(raw.get("requestTimeoutSeconds", 15.0)),
        # GSD_DB_PATH wins over the file so the config can ship as a ConfigMap that does
        # not need to know where the writable volume is mounted.
        leader_election=bool(raw.get("leaderElection", True)),
        leader_lease_name=str(raw.get("leaderLeaseName", "group-sync-dashboard")),
        db_path=os.environ.get("GSD_DB_PATH") or str(raw.get("dbPath", "gsd.db")),
        sqlite_busy_timeout_ms=_num_setting(
            raw, "GSD_SQLITE_BUSY_TIMEOUT_MS", "sqliteBusyTimeoutMs", 5000, int
        ),
        sqlite_reader_busy_timeout_ms=_num_setting(
            raw, "GSD_SQLITE_READER_BUSY_TIMEOUT_MS", "sqliteReaderBusyTimeoutMs", 2000, int
        ),
        sqlite_synchronous=os.environ.get("GSD_SQLITE_SYNCHRONOUS")
        or str(raw.get("sqliteSynchronous", "NORMAL")),
        backup_dir=os.environ.get("GSD_BACKUP_DIR") or str(raw.get("backupDir", "")),
        backup_interval_hours=_num_setting(
            raw, "GSD_BACKUP_INTERVAL_HOURS", "backupIntervalHours", 6.0, float
        ),
        backup_keep=_num_setting(raw, "GSD_BACKUP_KEEP", "backupKeep", 4, int),
        unmanaged_audit_mode=_audit_mode_setting(raw),
        unmanaged_audit_max_per_cycle=_num_setting(
            raw, "GSD_UNMANAGED_AUDIT_MAX_PER_CYCLE", "unmanagedAuditMaxPerCycle", 20, int
        ),
        sqlite_wal_checkpoint_mb=_num_setting(
            raw, "GSD_SQLITE_WAL_CHECKPOINT_MB", "sqliteWalCheckpointMb", 8.0, float
        ),
        oauth_proxy_enabled=_bool_setting(
            raw, "GSD_OAUTH_PROXY_ENABLED", "oauthProxyEnabled", False
        ),
        oauth_proxy_prefix=_proxy_prefix_setting(raw),
        session_cookie_expire_seconds=session_expire,
        session_cookie_refresh_seconds=session_refresh,
        user_activity_enabled=_bool_setting(
            raw, "GSD_USER_ACTIVITY_ENABLED", "userActivityEnabled", True
        ),
        user_activity_visibility=_visibility_setting(raw),
        user_activity_flush_seconds=_num_setting(
            raw, "GSD_USER_ACTIVITY_FLUSH_SECONDS", "userActivityFlushSeconds", 60, int
        ),
        user_activity_retention_days=_num_setting(
            raw, "GSD_USER_ACTIVITY_RETENTION_DAYS", "userActivityRetentionDays", 400, int
        ),
    )
```

#### B2. `local-development/gsd/api.py`

**B2a — `SKIP_AUTH_PATHS`, whole post-change constant.** Anchor: the module-level constant under
`STATIC_DIR` (api.py line 38). (The two static assets in the proxy regex need no entry here:
this constant gates *activity recording*, and static files are served by the `StaticFiles`
mount, which never passes through the middleware's interaction check with a marked header.)

```python
# Mirrors oauthProxy.skipAuthRegex. Requests here reach the app WITHOUT authentication, so
# nothing they claim about identity can be believed or recorded. /signed-out is the proxy's
# -logout-url landing page: it exists precisely for the moment the session cookie has just
# been cleared, so it is unauthenticated by design rather than by oversight.
SKIP_AUTH_PATHS = frozenset({"/healthz", "/readyz", "/metrics", "/signed-out"})
```

**B2b — the middleware, whole post-change function.** Only the path enumeration in the docstring
changes (it would otherwise be factually stale). Anchor: `@app.middleware("http")` (api.py
line ~180).

```python
    @app.middleware("http")
    async def record_dashboard_use(request, call_next):
        """Note who made this request, before serving it.

        Only requests the client marked as a human action are counted. The page polls
        itself every 30s and each poll is several API calls, so counting requests measured
        how long a tab had been open rather than whether anyone used the dashboard — one
        real session read 722. See activity.INTERACTION_HEADER.

        The unauthenticated paths (/healthz, /readyz, /metrics, /signed-out —
        oauthProxy.skipAuthRegex) need no special case: they carry neither header.
        """
        # Excluded EXPLICITLY, not by assuming they arrive header-less. These paths
        # bypass the proxy entirely (oauthProxy.skipAuthRegex), so whether they carry an
        # identity header is decided by the caller — which is exactly the input we must not
        # let decide whether we record.
        if request.url.path not in SKIP_AUTH_PATHS and request.headers.get(INTERACTION_HEADER):
            try:
                activity.record(
                    request.headers.get(USER_HEADER), request.headers.get(EMAIL_HEADER)
                )
            except Exception:  # noqa: BLE001
                # Logged with a trace rather than swallowed, but never propagated: failing
                # to note who read a page is not a reason to fail the page.
                log.exception("could not record dashboard use; serving the request anyway")
        return await call_next(request)
```

**B2c — `whoami`, whole post-change function.** Anchor: the `@app.get("/api/whoami")` decorator
(api.py line 909).

```python
    @app.get("/api/whoami")
    def whoami(request: Request) -> dict:
        """Who the proxy says this request is. Reflected, never stored by this endpoint.

        `authenticated` is false when the proxy is disabled even if a username is present,
        because in that mode the caller supplied it themselves. `logout_url` and `session`
        are gated on the same judgement, for the same reason: without the proxy there is no
        session to end and no idle timeout anyone enforces, so offering either would be the
        page claiming a security control that does not exist.

        `session` carries the CONFIGURED durations, never a deadline. The session cookie is
        HttpOnly and the proxy forwards no session-age header, so the true expiry is not
        observable from here; these numbers are trustworthy only because the ConfigMap
        renders them from the same chart values as the proxy's own flags. The browser owns
        the countdown model built on them — see static/index.html.

        NEVER POLL THIS ON A TIMER. Requesting it through the proxy re-stamps the session
        cookie like any other request, so a page calling it periodically would hold every
        session open forever — the exact defect the durations exist to fix. It is called
        once, at page load; the page's "Stay signed in" control re-proves the session with
        an ordinary interaction-marked data refresh instead of calling this again.
        """
        user = request.headers.get(USER_HEADER)
        authenticated = bool(user) and settings.oauth_proxy_enabled
        return {
            "user": user if settings.oauth_proxy_enabled else None,
            "email": request.headers.get(EMAIL_HEADER) if settings.oauth_proxy_enabled else None,
            "authenticated": authenticated,
            # Composed, not hardcoded: tracks a --proxy-prefix override through
            # Settings.oauth_proxy_prefix so the link and the proxy cannot drift apart.
            "logout_url": f"{settings.oauth_proxy_prefix}/sign_out" if authenticated else None,
            "session": (
                {
                    "cookie_expire_seconds": settings.session_cookie_expire_seconds,
                    "cookie_refresh_seconds": settings.session_cookie_refresh_seconds,
                }
                if authenticated
                else None
            ),
        }
```

Response, proxy enabled: `{"user": "alice", "email": "a@x.com", "authenticated": true,
"logout_url": "/oauth/sign_out", "session": {"cookie_expire_seconds": 1800,
"cookie_refresh_seconds": 300}}`. Proxy disabled: `{"user": null, "email": null,
"authenticated": false, "logout_url": null, "session": null}`. Seconds as integers, not `"30m"`
strings: the one consumer is JavaScript arithmetic, and shipping a string would force a second
Go-duration parser to exist in the page — two parsers of one format is how they diverge.

**B2d — the `/signed-out` route.** Anchor: immediately after the `index()` function, before the
`if os.path.isdir(STATIC_DIR):` mount. Stays IN the OpenAPI schema, like `/`; it is classed as
infrastructure by the contract test's explicit list (§D5).

```python
    @app.get("/signed-out")
    def signed_out() -> FileResponse:
        # The proxy's -logout-url target, listed in oauthProxy.skipAuthRegex. It renders at
        # the exact moment the session cookie has just been cleared, so it reads no headers
        # and claims nothing about who signed out — anything it said would be
        # caller-supplied. Same Cache-Control reasoning as index(): a stale cached copy
        # after a redeploy would misdescribe what logout actually does, and what this page
        # says logout does NOT do (end the cluster session) is its entire purpose.
        return FileResponse(
            os.path.join(STATIC_DIR, "signed-out.html"),
            headers={"Cache-Control": "no-cache, must-revalidate"},
        )
```

Why a route and not a bare `StaticFiles` path: the route gives it the clean top-level path the
proxy's `-logout-url` and `skipAuthRegex` name, and carries the no-cache header. Why not a
template: there is nothing to interpolate, and the page must not personalise itself — it renders
for an unauthenticated caller, so any header it read would be caller-supplied.

#### B3. New file: `local-development/gsd/static/signed-out.html`

Contract: no `<style>` block, no scripts, no external assets beyond `/static/app.css` and
`/static/favicon.svg`; reads no identity; states plainly that the **cluster** session is
separate and still active (research Finding 2 — the proxy's `SignOut` clears its own cookie and
revokes nothing, and the OAuth server will re-issue a token from its own live session without
prompting).

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<link rel="icon" href="/static/favicon.svg" type="image/svg+xml">
  <title>Signed out — OCP Access Control Dashboard</title>
<link rel="stylesheet" href="/static/app.css">
</head>
<body data-page="signed-out">
<div class="wrap">
  <main id="main">
    <h1>Signed out of the dashboard</h1>
    <p>Your dashboard session has ended.</p>
    <!-- The claim below is the point of this page existing: the proxy clears its own
         cookie and does NOT revoke the OpenShift token or end the OAuth server's session,
         so signing in again may not ask for a password. Saying less would imply a full
         sign-out that did not happen. -->
    <p>Your cluster login is separate and is still active, so signing in again may not ask
       for your password. To end it too, sign out of the OpenShift web console or run
       <code>oc logout</code>.</p>
    <p><a href="/">Sign in again</a></p>
  </main>
</div>
</body>
</html>
```

### Phase C — UI

All markup/JS changes in `local-development/gsd/static/index.html`, all styling in
`local-development/gsd/static/app.css` (a repo test asserts index.html contains no `<style>`).
Insertion points were checked against `tests/test_display_timezone.py`'s landmark slicing (all
four landmark ranges live between lines ~256–330 inside `usagePage()`): every change below is
outside them, and none of the new markup or code contains any landmark literal earlier in the
file than the original.

#### C1. The header — identity and the logout link

**Anchor:** replace the whole `<header class="top">…</header>` element (lines 13–19).

```html
  <header class="top">
    <h1>OCP Access Control Dashboard<span id="scope-note"></span></h1>
    <span class="spacer"></span>
    <span class="sub" id="build-info"></span>
    <span class="sub" id="last-refresh"></span>
    <!-- Who the proxy says is here, and the way out. Both stay hidden until /api/whoami proves a
         session exists: local development and an oauthProxy.enabled=false install must never
         offer to end a session that does not exist. A plain GET link because the fork's SignOut
         has no method check; see the one-line drive-by note in the design doc. -->
    <span class="sub" id="whoami" hidden></span>
    <a id="logout" class="logout" hidden>Sign out</a>
    <button id="refresh">Refresh</button>
  </header>
```

Accessible name is the link text, "Sign out"; `#whoami` beside it carries the username (title
attribute the email), so "sign out of what account" is answered by adjacency. The header is the
one region the 30s repaint never rebuilds, so no focus-restore machinery is needed for it.
GET drive-by, acknowledged in one line: a cross-site `<img src=…/oauth/sign_out>` can end the
session unwantedly; the cost is an annoyance (a fresh login) with zero data exposure or mutation
— the trade the operator chose.

#### C2. The session dialog markup

**Anchor:** insert between `</div>` (closing `.wrap`) and the `<script>` tag.

```html
<!-- The session dialog. OUTSIDE .wrap and #main deliberately: render() replaces #main's
     innerHTML on every poll, and a warning that vanished mid-countdown because the page
     repainted would be worse than none. One element, two states (warning / signed-out),
     swapped by JS — never rebuilt, so its listeners are wired once at boot.
     role and aria-modal are implicit with <dialog> + showModal(); stated anyway for the
     assistive tech that predates the implicit mapping, and so the test can assert them. -->
<dialog id="session-dialog" class="session" role="dialog" aria-modal="true"
        aria-labelledby="session-title" aria-describedby="session-desc">
  <h2 id="session-title">Your session is about to end</h2>
  <p id="session-desc"></p>
  <!-- aria-hidden on the TICKING number, not because it is unimportant but because a live
       region here would make a screen reader read every second. The sr-only status region
       below carries the same fact at humane milestones instead. -->
  <p class="session-remaining" id="session-remaining" aria-hidden="true"><span
      id="session-count" class="mono">–:––</span></p>
  <p id="session-announce" class="sr-only" role="status"></p>
  <div class="session-actions">
    <button id="session-stay" class="session-primary" autofocus>Stay signed in</button>
    <a id="session-signout" hidden>Sign out now</a>
    <a id="session-signin" href="/" hidden>Sign in again</a>
  </div>
</dialog>
```

Accessibility decisions: native `showModal()` supplies the focus trap, top layer, backdrop and
the Escape channel (the `cancel` event) — no hand-rolled trap under the no-dependency rule.
Initial focus on "Stay signed in" (the safe default) in the warning state, on "Sign in again" in
the over-state. Focus is restored on any close path (§C5's `close` handler), falling back to the
always-present Refresh button if the repaint removed the remembered element. The ticking counter
is `aria-hidden`; a visually-hidden `role="status"` region announces at open, 60s and 30s only.
Escape in the warning state is intercepted and treated as "stay": a keypress aimed at this
dialog is proof of presence, and dismiss-but-die would manufacture the silent mid-read logout
the dialog exists to prevent; in the over-state Escape closes normally — the page behind is dead
but still readable and copyable.

#### C3. `api()` — record send time, refuse to follow the proxy's bounce, type the error

Today, on a dead session, the proxy answers an API fetch with a redirect to its sign-in page;
`fetch` follows it, `res.ok` passes on the HTML, and `res.json()` throws
`SyntaxError: Unexpected token '<'`, which the error card paints over a note blaming a deleted
object. `redirect: "manual"` is safe because the FastAPI app never redirects `/api/*` (exact
routes) — the only redirect an API request can meet is the proxy answering for a dead session.

**Anchor:** replace the whole `async function api(path, mark) {…}` function, directly beneath
the comment block ending `…480 requests an hour from a tab left open on an empty desk. */` (the
comment stays).

```js
async function api(path, mark) {
  const headers = { Accept: "application/json" };
  if (mark) headers["X-GSD-Interaction"] = "1";
  // Recorded BEFORE the fetch: if the proxy re-stamps the cookie it does so while this request
  // is in flight, so send time is the safe floor for the session model and receive time the
  // safe ceiling — see noteAuthedResponse().
  const sentAt = Date.now();
  // redirect: "manual", because the app never redirects /api/* — the only redirect one of these
  // requests can meet is the oauth-proxy bouncing a dead session toward its sign-in page.
  // Following it (the old default) returned that page's HTML with a 200, and res.json() then
  // reported the end of the session as "Unexpected token '<'". Refusing to follow makes a dead
  // session detectable without loading the sign-in page or touching the OAuth server at all.
  const res = await fetch(path, { headers, redirect: "manual" });
  const ct = (res.headers.get("content-type") || "").toLowerCase();
  // HTML on any status is the same verdict: a proxy configured to serve its sign-in page
  // directly (200 or 403) instead of redirecting must not fall through to the generic card.
  if (res.type === "opaqueredirect" || ct.includes("text/html")) {
    const err = new Error(`signed out — the login page answered for ${path}`);
    err.sessionExpired = true;
    throw err;
  }
  if (!res.ok) {
    // The status rides on the error so a caller can tell a DESIGNED refusal from a fault.
    const err = new Error(`${res.status} ${res.statusText} on ${path}`);
    err.status = res.status;
    throw err;
  }
  // Only an OK JSON response teaches the session model: it provably traversed the proxy with a
  // live cookie. Error statuses are left out — they prove it too, but nothing is lost by being
  // conservative and the model stays a floor either way.
  noteAuthedResponse(sentAt);
  return res.json();
}
```

#### C4. The catch block in `refresh()` — a dead session is not a data error

**Anchor:** replace the block from the unique line `  } catch (err) {` (inside `refresh()`,
line ~2453) through the function's closing brace. Everything except the first two added lines is
the existing code, unchanged.

```js
  } catch (err) {
    // A dead session is not a data error: the object is fine, the SESSION is gone. The generic
    // card below would blame a deleted object for what is actually an expired login — the exact
    // illegibility this branch removes.
    if (err.sessionExpired) { sessionEnded("confirmed"); return; }
    // An error must never strand the reader: keep a working Back so a dead link is a
    // detour, not a dead end. This was reported from the field — a 404 on a deleted group
    // replaced the whole page, back button included.
    $("main").classList.remove("stale");
    $("main").innerHTML = `<section class="card">
      <button class="back" id="back-groups">${backLabel()}</button>
      <div class="err" style="margin-top:10px">Dashboard API error: ${esc(err.message)}</div>
      <div class="filterbar-note" style="margin-top:6px">
        The object may have been deleted since this page was rendered.</div>
    </section>`;
    const eb = $("back-groups");
    if (eb) eb.onclick = () => { goBack(); };
  }
}
```

#### C5. The session section — idle-aware polling, the countdown model, the modal, identity

**Anchor:** insert immediately after the unique line `$("refresh").onclick = refresh;`
(line ~2469) and before the `/* Boot from the URL…` comment block.

The model, stated once: track a wall-clock interval `[lo, hi]` guaranteed to contain the instant
the proxy last stamped the cookie. The displayed deadline is `lo + expire` — a **floor**, so the
warning errs early (by at most `cookie-refresh`), never late, while the page's clock runs. The
two drift cases are handled by construction: laptop sleep (all arithmetic is wall-clock, never
accumulated ticks — the first tick after wake recomputes and lands in the right state,
including straight to the over-state) and backward clock jumps (any tick observing time running
backwards shifts the interval down by the gap — over-correcting toward early, the safe
direction). When the modeled deadline is reached the truth lies in `[0, +refresh]`; the page
must **not** probe to find out — a probe is a request, and a request re-stamps a still-live
cookie, quietly rebuilding the bug this feature removes — so the over-state says the truth
("has ended, or is about to") and one click recovers either way.

```js
/* ── Session lifetime: idle-aware polling and the countdown model ─────────────────────────
   The proxy re-stamps the session cookie on any request older than cookie-refresh, so the old
   unconditional 30s poll made the idle timeout unreachable: an open tab slid the cookie forever,
   including on an unattended, unlocked workstation — the exact case the timeout is for. The
   poll therefore runs only while a human is demonstrably present, and a model of the deadline
   (which an HttpOnly cookie makes unobservable) drives a warning before the end.

   The model is a provable FLOOR on the deadline: [sessLo, sessHi] always contains the instant
   the proxy last stamped the cookie, so lo + expire never overstates the time left. Early by at
   most cookie-refresh (an interruption); late never (a silent logout mid-read). */

const POLL_MS = 30_000;
/* Two minutes: long enough that reading a long table never pauses the data underneath it,
   short enough that the idle-logout promise stays honest — the last poll that can re-stamp the
   cookie is sent within this window of the last human input, so true idle logout lands between
   expire-refresh and expire+IDLE_SUSPEND after the person left (27–32 minutes at the shipped
   defaults, against the "about 30" the values file promises). */
const IDLE_SUSPEND_MS = 120_000;
const SESSION_WARN_MS = 120_000;
const SESSION_STAMP_KEY = "gsd:session-stamp";

let lastActivityAt = Date.now();
let lastAutoRefreshAt = 0;
/* null until /api/whoami proves there is a proxy session to model — local development and
   proxy-disabled installs keep every branch below inert. */
let sessionModel = null;   // { expireMs, refreshMs, lo, hi }
/* false | "modeled" | "confirmed". Modeled ends can be un-latched by another tab's shared
   stamp proving the session alive; a confirmed one (the proxy itself answered for a request)
   cannot. */
let sessionOver = false;
let sessionLogoutUrl = null;
let sessionReturnFocus = null;
let sessionLastAnnouncedMs = Infinity;
let lastTickAt = Date.now();

/* pointerdown, keydown, wheel — discrete, deliberate acts. NOT pointermove: it fires from
   sub-pixel jitter of a resting hand, and browsers synthesize one when layout changes under a
   stationary cursor — which this page does to itself on every poll, so pointermove would re-arm
   the idle timer from our own repaint forever. NOT scroll: the repaint clamps the scroll
   position when content shrinks and fires it with nobody there; wheel and keydown cover real
   reading. Capture phase, because several tables stopPropagation() in their own handlers and
   the window would otherwise never hear those clicks. */
function recordActivity() {
  const wasIdle = Date.now() - lastActivityAt > IDLE_SUSPEND_MS;
  lastActivityAt = Date.now();
  // One catch-up so the page is fresh the moment someone returns — pollTick's own guard
  // collapses this, the interval and visibilitychange into a single request cycle.
  if (wasIdle) pollTick();
}
for (const type of ["pointerdown", "keydown", "wheel"]) {
  window.addEventListener(type, recordActivity, { capture: true, passive: true });
}

document.addEventListener("visibilitychange", () => {
  if (document.hidden) return;
  // Choosing this tab is a human act. Session state first: a deadline that passed while the
  // tab was hidden must surface as the over-state, not as one more poll re-stamping a cookie
  // nobody is using.
  sessionTick();
  recordActivity();
  pollTick();
});

/* The 30s poll, gated. Returns WHY it did or did not fetch — that string is the test surface
   and the console diagnosis for "why is my dashboard stale". {auto: true} because background
   polling must not register as somebody using the page (the usage counter's rule). */
function pollTick() {
  if (sessionOver) return "over";
  // An open warning means the reader is being asked whether they are present; a poll here
  // would re-stamp the cookie and answer for them.
  if ($("session-dialog").open) return "warned";
  if (document.hidden) return "hidden";
  if (Date.now() - lastActivityAt > IDLE_SUSPEND_MS) return "idle";
  // The herd guard: interval, catch-up and visibilitychange can all land in the same instant
  // when a tab wakes; whichever arrives first fetches and the rest see "fresh". The 1s slop
  // keeps ordinary interval jitter from skipping a legitimate tick.
  if (Date.now() - lastAutoRefreshAt < POLL_MS - 1_000) return "fresh";
  lastAutoRefreshAt = Date.now();
  refresh({ auto: true });
  return "refreshed";
}

/* Arms the model from the whoami contract. cookie_refresh_seconds of 0 (refresh disabled —
   the provider=openshift contingency) leaves it DISARMED on purpose: with no re-stamping the
   expiry is absolute and anchored to a login instant this page cannot observe, so any
   countdown would be a guess; the signed-out failover in api() carries that mode alone. */
function initSession(who, sentAt) {
  const s = who && who.session;
  if (!who || !who.authenticated || !s || !s.cookie_expire_seconds || !s.cookie_refresh_seconds) return;
  // The whoami request itself just traversed the proxy: either it re-stamped the cookie, or
  // the previous stamp was younger than refresh — so the stamp lies in [sentAt-refresh, now].
  sessionModel = {
    expireMs: s.cookie_expire_seconds * 1000,
    refreshMs: s.cookie_refresh_seconds * 1000,
    lo: sentAt - s.cookie_refresh_seconds * 1000,
    hi: Date.now(),
  };
}

/* Every OK JSON response teaches the model, mirroring the proxy's own arithmetic
   (oauthproxy.go: re-stamp iff sessionAge > CookieRefresh). sentAt, not now, as the floor:
   the proxy stamped while the request was in flight.
     certain re-stamp (age exceeded refresh even by the OLDEST possible stamp) -> exact;
     maybe (only the newest bound rules it in) -> hull of both outcomes, floor rises;
     provably young -> nothing happened, learn nothing.
   The maybe-branch is load-bearing: assuming a re-stamp whenever the MODEL's age crosses
   refresh puts the floor past the truth after one unlucky page load, and the warning after
   the expiry — the unsound direction. A test replays that exact sequence. */
function noteAuthedResponse(sentAt) {
  if (!sessionModel || sessionOver) return;
  const m = sessionModel;
  if (!m.refreshMs) return;
  const now = Date.now();
  if (sentAt - m.hi > m.refreshMs) { m.lo = sentAt; m.hi = now; }
  else if (sentAt - m.lo > m.refreshMs) { m.lo = Math.max(m.lo, sentAt - m.refreshMs); m.hi = now; }
  else return;
  // Tabs share the cookie, so they share the model: a background tab warning while a
  // foreground tab keeps the session alive would be the page lying. Storage denied just means
  // tabs model alone — every stamp any tab writes is a valid bound for all of them.
  try { localStorage.setItem(SESSION_STAMP_KEY, JSON.stringify({ lo: m.lo, hi: m.hi })); }
  catch (e) { /* private mode / quota: single-tab modelling is still sound */ }
}

function mergeSharedStamp(now) {
  let shared = null;
  try { shared = JSON.parse(localStorage.getItem(SESSION_STAMP_KEY) || "null"); }
  catch (e) { return; }
  if (!shared || typeof shared.lo !== "number" || typeof shared.hi !== "number") return;
  // Clamped to now: same machine, same clock, but a corrupt future stamp must not push the
  // deadline past what any tab actually proved.
  const lo = Math.min(shared.lo, now);
  if (lo > sessionModel.lo) {
    sessionModel.lo = lo;
    sessionModel.hi = Math.max(Math.min(shared.hi, now), lo);
  }
}

function fmtCountdown(ms) {
  const s = Math.max(0, Math.ceil(ms / 1000));
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

/* The 1s heartbeat. Cheap when disarmed, and it is also the drift detector: everything is
   wall-clock (Date.now()), never accumulated ticks, so laptop sleep costs nothing — on wake the
   next tick recomputes and lands in the right state directly. Forward clock jumps only shrink
   the modeled remainder (early, safe); a BACKWARD jump would inflate it, so any tick that
   observes time running backwards shifts the model down by the gap — over-correcting toward
   early, which is the safe direction. Hidden tabs get throttled ticks; visibilitychange runs
   one immediately on return. */
function sessionTick() {
  const now = Date.now();
  const gap = now - lastTickAt;
  lastTickAt = now;
  if (!sessionModel) return "disarmed";
  if (gap < 0) { sessionModel.lo += gap; sessionModel.hi += gap; }
  mergeSharedStamp(now);
  const remaining = sessionModel.lo + sessionModel.expireMs - now;
  if (sessionOver === "confirmed") return "over";
  if (sessionOver === "modeled") {
    // Another tab's shared stamp can prove a modeled end wrong; a confirmed one it cannot.
    if (remaining > SESSION_WARN_MS) { sessionOver = false; closeSessionModal(); return "armed"; }
    return "over";
  }
  if (remaining <= 0) { sessionEnded("modeled"); return "ended"; }
  if (remaining <= SESSION_WARN_MS) { openSessionModal(remaining); return "warning"; }
  // A warning made moot (stay in another tab, merge above) must not stay on screen lying.
  if ($("session-dialog").open) closeSessionModal();
  return "armed";
}

function openSessionModal(remaining) {
  const dlg = $("session-dialog");
  $("session-count").textContent = fmtCountdown(remaining);
  if (!dlg.open) {
    sessionReturnFocus = document.activeElement;
    // Full state reset, because the same element served the over-state on a previous cycle.
    $("session-title").textContent = "Your session is about to end";
    $("session-desc").textContent =
      "You have been inactive for a while, so this dashboard is about to sign you out to " +
      "protect the access data it shows.";
    $("session-remaining").hidden = false;
    $("session-stay").hidden = false;
    $("session-signin").hidden = true;
    $("session-signout").hidden = !sessionLogoutUrl;
    dlg.showModal();
    $("session-stay").focus();
    // Announced ONCE at open, then at two milestones below — never per second. The visible
    // counter is aria-hidden for exactly that reason.
    $("session-announce").textContent =
      `Inactive session: you will be signed out in about ${Math.ceil(remaining / 60_000)} ` +
      `minutes unless you choose to stay signed in.`;
    sessionLastAnnouncedMs = remaining;
    return;
  }
  for (const mark of [60_000, 30_000]) {
    if (remaining <= mark && sessionLastAnnouncedMs > mark) {
      $("session-announce").textContent =
        `About ${Math.round(mark / 1000)} seconds until sign-out.`;
      break;
    }
  }
  sessionLastAnnouncedMs = remaining;
}

function closeSessionModal() {
  const dlg = $("session-dialog");
  if (dlg.open) dlg.close();
}

function staySignedIn() {
  recordActivity();
  closeSessionModal();
  // A human choice, so refresh() runs un-auto'd: it marks the interaction like any click,
  // repaints the stale page, and its first response hits noteAuthedResponse's certain branch
  // (the idle gap exceeds cookie-refresh by construction) — model exact, deadline reset to a
  // full expire. No dedicated keepalive endpoint exists or is needed: the PROXY extends the
  // cookie, on any proxied request.
  refresh();
}

/* The end state — reached from a modeled zero, or "confirmed" when the proxy itself answered
   an API call with its login page. NO automatic probe distinguishes the two: a probe is a
   request, and a request re-stamps a still-live cookie — extending the session with nobody
   present, which is the bug this feature exists to remove. The copy carries the resulting
   uncertainty honestly, and one click recovers either way. */
function sessionEnded(kind) {
  sessionOver = kind;
  $("main").classList.remove("stale");
  const dlg = $("session-dialog");
  $("session-title").textContent = "Signed out";
  // "or is about to": a modeled end is a floor, so the true expiry may be up to cookie-refresh
  // later. The SSO sentence is research Finding 2 — the proxy session ends, the cluster
  // session does not, and a governance page must not imply otherwise.
  $("session-desc").textContent =
    "Your session has ended, or is about to. Nothing more will load until you sign in again — " +
    "and signing in may not ask for a password, because your OpenShift single sign-on session " +
    "is separate and may still be active.";
  $("session-remaining").hidden = true;
  $("session-stay").hidden = true;
  $("session-signout").hidden = true;
  $("session-signin").hidden = false;
  if (!dlg.open) { sessionReturnFocus = document.activeElement; dlg.showModal(); }
  $("session-signin").focus();
}

/* Escape. On the WARNING it is consent to continue, not a dismissal: a keypress aimed at this
   dialog is proof of presence, and dismiss-but-die would manufacture the silent mid-read logout
   the dialog exists to prevent. On the over-state it closes normally — the page behind is dead,
   but still readable and copyable. */
$("session-dialog").addEventListener("cancel", (e) => {
  if (!sessionOver) { e.preventDefault(); staySignedIn(); }
});
/* Focus restore on ANY close path, in one place. The remembered element may have been repainted
   away by the poll; the Refresh button always exists, and landing there beats landing on
   <body>, which is the same silent drop the filter bar's restore machinery exists to prevent. */
$("session-dialog").addEventListener("close", () => {
  sessionLastAnnouncedMs = Infinity;
  const back = sessionReturnFocus;
  sessionReturnFocus = null;
  if (back && document.contains(back)) back.focus({ preventScroll: true });
  else $("refresh").focus({ preventScroll: true });
});
$("session-stay").onclick = staySignedIn;

/* Identity is fetched ONCE: user and logout_url cannot change without the proxy bouncing the
   session, at which point every API call fails over to the signed-out state anyway. A failure
   here (older API, transient fault) just leaves the header plain and the countdown disarmed —
   never a broken page. */
async function initIdentity() {
  const sentAt = Date.now();
  let who;
  try { who = await api("/api/whoami"); } catch (e) { return; }
  if (who.authenticated && who.user) {
    $("whoami").textContent = who.user;
    if (who.email) $("whoami").title = who.email;
    $("whoami").hidden = false;
  }
  if (who.logout_url) {
    sessionLogoutUrl = who.logout_url;
    $("logout").href = who.logout_url;
    $("logout").hidden = false;
    $("session-signout").href = who.logout_url;
  }
  initSession(who, sentAt);
}
```

The security arithmetic at defaults (expire 30m, refresh 5m, suspend 2m): last human input at
`T`; polls continue until `T+2m`; the cookie dies between `T+27m` and `T+32m` — the "≈30 minutes
of true inactivity" the tighter default is buying, within +2m. Warning-too-early is bounded by
`refresh` (5m) and resolved by one click; warning-too-late is impossible while the clock runs,
and the sleep/backward-jump paths above close the clock's own failure modes.

#### C6. The boot lines

**Anchor:** replace the final lines of the script, from the line `refresh();` through
`setInterval(() => refresh({ auto: true }), 30000);` inclusive (the `// {auto: true}: background
polling…` comment line between them goes too — its rule now lives in `pollTick()`):

```js
refresh();
lastAutoRefreshAt = Date.now();
initIdentity();
/* The interval is UNGATED here and gated inside pollTick(), so every suppression reason is a
   testable return value instead of a tangle of cleared-and-rearmed timers. A suspended poll
   costs one no-op comparison per 30s; the 1s session tick is a no-op until whoami arms it. */
setInterval(pollTick, POLL_MS);
setInterval(sessionTick, 1_000);
```

#### C7. `local-development/gsd/static/app.css` — the styles

**Anchor:** appended at the end of the file (after the final rule,
`header.top { border-bottom-color: … }`). No new colour tokens and no literal font sizes, so
`test_accessibility.py` and `test_type_scale.py` cover these rules with zero edits. The logout
control deliberately does **not** reuse the `.drill` link colour: `--series-1` measures 4.43:1
against `--page` in the light theme (its tested 4.55:1 is against `--surface-1`, and the header
sits on the page wash) — below the 4.5:1 text bar.

```css
/* ---- Session: sign-out and the countdown dialog ---------------------------------------
   The sign-out control does NOT reuse the .drill link colour: --series-1 measures 4.43:1
   against --page in the light theme — under the 4.5 text bar — because its tested 4.55:1 is
   against --surface-1 and the header sits on the page wash. It wears the Refresh button's
   surface instead, which both passes trivially (--text-primary on --surface-1) and pairs the
   header's two actions visually. Inside the dialog, links sit on --surface-1, where --series-1
   is the already-tested 4.55:1 (light) / 4.79:1 (dark). */
a.logout {
  display: inline-block; font-size: var(--text-md); color: var(--text-primary);
  background: var(--surface-1); border: 1px solid var(--border); border-radius: 6px;
  padding: 5px 9px; text-decoration: none;
}
a.logout:hover { border-color: var(--baseline); }

/* Native <dialog> + showModal(): the focus containment, the Escape channel (the `cancel`
   event), the top layer and the backdrop come from the platform instead of being re-implemented
   under a strict no-dependency rule. It lives OUTSIDE #main and #filters, so the 30s repaint
   that replaces both wholesale can never destroy an open warning. */
dialog.session {
  background: var(--surface-1); color: var(--text-primary);
  border: 1px solid var(--border); border-radius: 10px;
  padding: 20px 22px; max-width: 420px; box-shadow: var(--elev-1);
}
/* Decorative dimming, not a surface anything renders on — no contrast requirement applies,
   and the page beneath is inert while it shows. */
dialog.session::backdrop { background: rgba(0, 0, 0, 0.5); }
/* Tabular mono so the countdown does not wobble as digits change — the same reason the data
   tables pin their figures. aria-hidden rides on the element (see the markup): a per-second
   live region would make a screen reader narrate every tick. */
.session-remaining {
  font-family: var(--font-mono); font-size: var(--text-2xl);
  font-variant-numeric: tabular-nums; margin: 10px 0 4px;
}
.session-actions { display: flex; gap: 10px; align-items: center; margin-top: 14px; }
/* Primacy by colour AND weight, on tokens already held to the text bar on this surface. */
.session-primary { border-color: var(--series-1); color: var(--series-1); font-weight: 600; }
.session-actions a { color: var(--series-1); font-size: var(--text-md); }
```

### Phase D — tests

Run from `local-development/` in the worktree so `gsd` resolves there:

```
cd /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/325dfd2f-469e-4bd4-b279-331704911184/scratchpad/wt-oauth-session/local-development && /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py
```

Baseline 1058 passed, 1 skipped. Every new behaviour has a test that fails before its snippet
and passes after (the handful of pass-before entries are deliberate boundary invariants, marked
below).

#### D1. `local-development/tests/test_chart_strategy.py` — chart tests

This file is the only right home: CI's `chart` job points at it **by name**, and it owns the
`render()` helper. One import joins the existing block: `import re` (alphabetical, between
`pathlib` and `shutil`). **Anchor:** the two module-level helpers go after the existing
`render()` function; the three classes append at end of file, after
`TestTheProxyTrustsTheSameCAsTheApp`.

```python
def _proxy_args(out):
    """The oauth-proxy container's args, parsed — the template's # comments render into
    the output, so grepping the raw text would match prose as easily as flags."""
    import yaml
    for doc in yaml.safe_load_all(out):
        if doc and doc.get("kind") == "Deployment":
            spec = doc["spec"]["template"]["spec"]
            proxy = next((c for c in spec["containers"] if c["name"] == "oauth-proxy"), None)
            assert proxy, "the oauth-proxy container did not render"
            return proxy["args"]
    raise AssertionError("no Deployment in the rendered output")


def _config_data(out):
    """The clusters.yaml the app reads, parsed out of the ConfigMap."""
    import yaml
    for doc in yaml.safe_load_all(out):
        if doc and doc.get("kind") == "ConfigMap" and "clusters.yaml" in (doc.get("data") or {}):
            return yaml.safe_load(doc["data"]["clusters.yaml"])
    raise AssertionError("no config ConfigMap in the rendered output")


class TestSessionCookieLifetime:
    """cookie-expire/cookie-refresh, and the one invariant that matters: the numbers the
    proxy enforces and the numbers the app models the session from must be THE SAME
    numbers, or the countdown warning lies."""

    def test_defaults_render_the_thirty_minute_sliding_window(self):
        ok, out = render()
        assert ok, out
        args = _proxy_args(out)
        assert "-cookie-expire=30m" in args
        assert "-cookie-refresh=5m" in args

    def test_an_empty_refresh_omits_the_flag_rather_than_passing_zero(self):
        """The proxy reads 0 and absence identically; the pod spec should say what is off
        by not saying it."""
        ok, out = render(oauthProxy__cookie__refresh="")
        assert ok, out
        args = _proxy_args(out)
        assert not any(a.startswith("-cookie-refresh") for a in args), args
        assert "-cookie-expire=30m" in args, "disabling refresh must not disturb expire"

    def test_a_zero_refresh_is_normalised_to_omission(self):
        ok, out = render(oauthProxy__cookie__refresh="0")
        assert ok, out
        assert not any(a.startswith("-cookie-refresh") for a in _proxy_args(out))

    def test_a_nulled_cookie_block_still_renders_the_shipped_defaults(self):
        """A values file with `oauthProxy.cookie: null` must fall back to 30m/5m, not to
        the proxy's built-in 7-day cookie with no refresh."""
        ok, out = render(oauthProxy__cookie="null")
        assert ok, out
        args = _proxy_args(out)
        assert "-cookie-expire=30m" in args
        assert "-cookie-refresh=5m" in args

    def test_the_configmap_carries_the_same_strings_as_the_flags(self):
        """The session cookie is HttpOnly, so the page cannot read its expiry — the app
        parses these keys and /api/whoami restates them to the UI. They must be the SAME
        Go-duration strings the flags carry (one helper feeds both), or the countdown
        models a session nobody configured."""
        ok, out = render(oauthProxy__cookie__expire="1h30m", oauthProxy__cookie__refresh="90s")
        assert ok, out
        args = _proxy_args(out)
        assert "-cookie-expire=1h30m" in args and "-cookie-refresh=90s" in args
        cfg = _config_data(out)
        assert cfg["sessionCookieExpire"] == "1h30m"
        assert cfg["sessionCookieRefresh"] == "90s"

    def test_disabled_refresh_reaches_the_app_as_the_empty_string(self):
        """The app parses '' to 0 (disabled) — the same meaning the omitted flag has."""
        ok, out = render(oauthProxy__cookie__refresh="")
        assert ok, out
        assert _config_data(out)["sessionCookieRefresh"] == ""

    def test_refresh_at_or_above_expire_is_refused_at_render(self):
        """The proxy validates exactly this at startup and crash-loops; the render is
        where the operator is still watching."""
        ok, out = render(oauthProxy__cookie__refresh="30m")
        assert not ok, "refresh == expire rendered happily and would crash-loop the proxy"
        assert "must be less than oauthProxy.cookie.expire" in out

    def test_a_non_duration_is_refused_at_render(self):
        for key, bad in (("expire", "8hr"), ("expire", "30"), ("refresh", "5 minutes")):
            ok, out = render(**{f"oauthProxy__cookie__{key}": bad})
            assert not ok, f"cookie.{key}={bad!r} rendered happily and would crash-loop the proxy"
            assert "not a Go duration" in out

    def test_no_proxy_means_no_flags_and_no_guards(self):
        """With the sidecar off there is nothing to crash-loop, so a bad duration must
        not block a render that never uses it."""
        ok, out = render(oauthProxy__enabled="false", oauthProxy__cookie__expire="8hr")
        assert ok, out
        assert "-cookie-expire" not in out


class TestCookieSecretLengthGuard:
    """With refresh on, the proxy derives an AES key from the cookie secret and refuses
    to start unless it yields 16/24/32 bytes. The guard reproduces the proxy's OWN
    arithmetic — secretBytes() base64-decodes a value that decodes and pads the DECODED
    length up to a multiple of four — because a naive len() disagrees with it in both
    directions, and each disagreement is a defect: rejecting a working config, or
    passing one that crash-loops."""

    # 20 bytes, and the '?'s keep it from parsing as base64 — the proxy counts it raw
    # and refuses to start. This is the honest invalid vector; see the parity test below
    # for why a more obvious-looking one is not.
    INVALID = "not-a-valid-secret??"

    def test_an_invalid_supplied_secret_with_refresh_on_fails_the_render(self):
        ok, out = render(oauthProxy__cookieSecret=self.INVALID)
        assert not ok, "a secret the proxy would refuse rendered happily"
        assert "16, 24, or 32" in out, "the three valid lengths belong in the message"

    def test_with_refresh_disabled_the_guard_stands_down(self):
        """No refresh means no AES cipher, and the proxy accepts any secret for plain
        signing — the guard must not invent a requirement the proxy does not have."""
        ok, out = render(oauthProxy__cookieSecret=self.INVALID,
                         oauthProxy__cookie__refresh="")
        assert ok, out

    def test_a_32_byte_secret_passes(self):
        ok, out = render(oauthProxy__cookieSecret="0123456789abcdef0123456789abcdef")
        assert ok, out

    def test_a_base64_encoded_secret_is_measured_after_decoding(self):
        """44 chars of base64 decoding to 32 bytes: the proxy decodes it, so raw length
        must not be what the guard measures."""
        ok, out = render(
            oauthProxy__cookieSecret="MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
        assert ok, out

    def test_the_guard_matches_the_proxys_arithmetic_not_a_naive_len(self):
        """'twentybytesexactly1' is 19 bytes and LOOKS invalid — but the proxy pads it to
        20 chars, base64-decodes those to 14 bytes, and pads THOSE to 16: a valid AES key
        length, so it starts fine. A guard that rejects what the proxy accepts is a
        spurious install failure, which is its own defect."""
        ok, out = render(oauthProxy__cookieSecret="twentybytesexactly1")
        assert ok, out

    def test_a_standard_base64_value_the_proxy_cannot_decode_counts_raw(self):
        """The proxy tries URL-SAFE base64 only, so a '+' makes the decode fail and the
        44 raw bytes are the length that counts — invalid, and the guard must agree."""
        ok, out = render(
            oauthProxy__cookieSecret="+DEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY=")
        assert not ok, "the proxy would count 44 raw bytes and refuse; the guard passed it"
        assert "16, 24, or 32" in out

    def test_the_generated_secret_path_is_untouched(self):
        """Empty cookieSecret generates randAlpha 32, which is always valid — the guard
        must never fire on the path the chart itself controls."""
        ok, out = render()
        assert ok, out


class TestLogoutWiring:
    """-logout-url and the unauthenticated landing page. Sign-out that lands on an
    authenticated path starts a fresh OAuth flow, which the OAuth server satisfies from
    its own still-live session — a logout button that undoes itself."""

    def test_the_default_logout_url_is_the_relative_signed_out_page(self):
        """Relative on purpose: the browser resolves it against whatever host served it,
        so a GitOps render needs no cluster lookup and a changed route cannot strand it."""
        ok, out = render()
        assert ok, out
        assert "-logout-url=/signed-out" in _proxy_args(out)

    def test_signed_out_and_its_assets_are_inside_the_default_skip_auth_regex(self):
        """Asserted by MATCHING the rendered regex, not by eyeballing the default — an
        override that anchors differently would pass a substring check and still bounce
        the landing page into a login. The two static assets are admitted because
        /signed-out links them: at the moment it renders the session cookie is gone, so
        behind the proxy the stylesheet request would bounce to the sign-in page and the
        logout landing page would arrive unstyled."""
        ok, out = render()
        assert ok, out
        args = _proxy_args(out)
        regex = next(a for a in args if a.startswith("-skip-auth-regex=")).split("=", 1)[1]
        for path in ("/signed-out", "/healthz", "/readyz", "/metrics",
                     "/static/app.css", "/static/favicon.svg"):
            assert re.search(regex, path), f"{regex!r} does not admit {path}"
        for path in ("/api/version", "/static/vendor/redoc.standalone.js", "/static/x.css"):
            assert not re.search(regex, path), f"{regex!r} is wider than intended: {path}"

    def test_an_sso_override_replaces_the_default(self):
        ok, out = render(oauthProxy__logoutUrl="https://sso.example.com/logout")
        assert ok, out
        args = _proxy_args(out)
        assert "-logout-url=https://sso.example.com/logout" in args
        assert "-logout-url=/signed-out" not in args

    def test_dropping_signed_out_from_the_regex_without_an_override_is_refused(self):
        ok, out = render(oauthProxy__skipAuthRegex="^/(healthz|readyz|metrics)$")
        assert not ok, "rendered a logout that lands back inside the proxy and re-authenticates"
        assert "no longer covers /signed-out" in out

    def test_a_custom_regex_with_an_sso_override_is_allowed(self):
        """With logoutUrl pointing elsewhere the chart-served page is unused, so its
        absence from the regex is not a defect."""
        ok, out = render(oauthProxy__skipAuthRegex="^/(healthz|readyz|metrics)$",
                         oauthProxy__logoutUrl="https://sso.example.com/logout")
        assert ok, out

    def test_the_proxy_prefix_reaches_flag_configmap_and_redirect_uri_together(self):
        """One key feeds all three, so they cannot drift — a prefix change that moved the
        proxy but not the ServiceAccount's callback URI would break every login."""
        ok, out = render(oauthProxy__proxyPrefix="/auth")
        assert ok, out
        assert "-proxy-prefix=/auth" in _proxy_args(out)
        assert _config_data(out)["oauthProxyPrefix"] == "/auth"
        import yaml
        sa = next(d for d in yaml.safe_load_all(out)
                  if d and d.get("kind") == "ServiceAccount")
        uri = sa["metadata"]["annotations"][
            "serviceaccounts.openshift.io/oauth-redirecturi.primary"]
        assert uri == "https://t.example.com/auth/callback", uri
```

#### D2. `local-development/tests/test_config.py` — two new classes

**Anchor:** append after `TestBothCASources`.

```python
class TestProxyPrefix:
    """The proxy's route prefix, from which /api/whoami composes the logout link. Composed
    rather than hardcoded so a --proxy-prefix override cannot strand the link (a wrong one
    404s INTO the dashboard, which reads as a logout that silently did nothing)."""

    def test_default_is_oauth(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_OAUTH_PROXY_PREFIX", raising=False)
        assert load_settings(write(tmp_path, BASE)).oauth_proxy_prefix == "/oauth"

    def test_configmap_value_is_used(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_OAUTH_PROXY_PREFIX", raising=False)
        cfg = BASE + "oauthProxyPrefix: /gate\n"
        assert load_settings(write(tmp_path, cfg)).oauth_proxy_prefix == "/gate"

    def test_env_wins_over_the_configmap(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_OAUTH_PROXY_PREFIX", "/env-gate")
        cfg = BASE + "oauthProxyPrefix: /file-gate\n"
        assert load_settings(write(tmp_path, cfg)).oauth_proxy_prefix == "/env-gate"

    def test_a_trailing_slash_is_normalised_away(self, tmp_path, monkeypatch):
        """'/oauth/' states the same intent as '/oauth'; the composed sign_out path must
        not end up with a double slash either way."""
        monkeypatch.delenv("GSD_OAUTH_PROXY_PREFIX", raising=False)
        cfg = BASE + "oauthProxyPrefix: /oauth/\n"
        assert load_settings(write(tmp_path, cfg)).oauth_proxy_prefix == "/oauth"

    def test_a_relative_prefix_fails_at_startup(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_OAUTH_PROXY_PREFIX", raising=False)
        with pytest.raises(ConfigError, match="oauthProxyPrefix"):
            load_settings(write(tmp_path, BASE + "oauthProxyPrefix: oauth\n"))


class TestSessionDurationSettings:
    """The chart carries Go-duration strings ('30m') — one spelling serving both the proxy
    flag and this setting, so the two cannot drift. Malformed values fail startup rather
    than falling back: a silently substituted default would make /api/whoami confidently
    wrong about the security control the proxy is actually enforcing, and the same string
    would crash the sidecar's own flag parsing anyway — failing here keeps the pod's two
    containers telling one story."""

    def _clean(self, monkeypatch):
        monkeypatch.delenv("GSD_SESSION_COOKIE_EXPIRE", raising=False)
        monkeypatch.delenv("GSD_SESSION_COOKIE_REFRESH", raising=False)

    def test_defaults_mirror_the_chart(self, tmp_path, monkeypatch):
        self._clean(monkeypatch)
        s = load_settings(write(tmp_path, BASE))
        assert s.session_cookie_expire_seconds == 1800
        assert s.session_cookie_refresh_seconds == 300

    def test_go_duration_spellings_parse_to_seconds(self, tmp_path, monkeypatch):
        self._clean(monkeypatch)
        cfg = BASE + 'sessionCookieExpire: "1h30m"\nsessionCookieRefresh: "90s"\n'
        s = load_settings(write(tmp_path, cfg))
        assert s.session_cookie_expire_seconds == 5400
        assert s.session_cookie_refresh_seconds == 90

    def test_fractional_units_parse_like_go(self, tmp_path, monkeypatch):
        self._clean(monkeypatch)
        cfg = BASE + 'sessionCookieExpire: "1.5h"\n'
        assert load_settings(write(tmp_path, cfg)).session_cookie_expire_seconds == 5400

    def test_empty_or_zero_refresh_means_disabled(self, tmp_path, monkeypatch):
        """The chart renders '' when refresh is off; '0' is the proxy's own disable
        spelling. Both must arrive as 0, which tells the UI the window is absolute."""
        self._clean(monkeypatch)
        for spelling in ('""', '"0"', '"0s"'):
            cfg = BASE + f"sessionCookieRefresh: {spelling}\n"
            assert load_settings(write(tmp_path, cfg)).session_cookie_refresh_seconds == 0

    def test_a_malformed_duration_fails_at_startup_naming_the_key(self, tmp_path, monkeypatch):
        """Loud, not lenient — the one place a fallback would silently disable the idle
        warning while the proxy enforces something else entirely."""
        self._clean(monkeypatch)
        for bad in ("half an hour", "30", "30 m", "-5m", "300ms", "0"):
            cfg = BASE + f'sessionCookieExpire: "{bad}"\n'
            with pytest.raises(ConfigError, match="sessionCookieExpire"):
                load_settings(write(tmp_path, cfg))

    def test_refresh_must_be_shorter_than_expire(self, tmp_path, monkeypatch):
        """refresh >= expire means the proxy can never re-stamp a cookie before it dies, so
        no session slides and the values comment's promise is fiction. Upstream oauth2_proxy
        refuses the identical combination at its own startup."""
        self._clean(monkeypatch)
        cfg = BASE + 'sessionCookieExpire: "30m"\nsessionCookieRefresh: "30m"\n'
        with pytest.raises(ConfigError, match="sessionCookieRefresh"):
            load_settings(write(tmp_path, cfg))

    def test_env_override_wins_and_is_validated_too(self, tmp_path, monkeypatch):
        """The env path is the one the proxy's own flag parsing can never catch."""
        self._clean(monkeypatch)
        monkeypatch.setenv("GSD_SESSION_COOKIE_EXPIRE", "10m")
        cfg = BASE + 'sessionCookieExpire: "45m"\n'
        assert load_settings(write(tmp_path, cfg)).session_cookie_expire_seconds == 600
        monkeypatch.setenv("GSD_SESSION_COOKIE_EXPIRE", "nonsense")
        with pytest.raises(ConfigError, match="GSD_SESSION_COOKIE_EXPIRE"):
            load_settings(write(tmp_path, cfg))
```

#### D3. New file: `local-development/tests/test_session_api.py`

```python
"""The session surface: what /api/whoami tells the UI about ending or keeping a session,
and the unauthenticated /signed-out landing page.

The constraint behind all of it: the session cookie is HttpOnly and the proxy forwards no
session-age header, so no one — not the app, not the browser — can observe the real
deadline. whoami therefore reports the CONFIGURED durations and nothing it cannot know; the
browser builds its countdown model on those, and these tests pin that contract."""

from __future__ import annotations

from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import Settings
from gsd.store import Store


def _client(tmp_path, **settings_kw):
    return TestClient(
        build_app(Settings(db_path=str(tmp_path / "gsd.db"), **settings_kw), run_poller=False)
    )


class TestWhoamiSession:
    def test_logout_and_session_are_offered_behind_the_proxy(self, tmp_path):
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "alice"}).json()
            assert body["authenticated"] is True
            assert body["logout_url"] == "/oauth/sign_out"
            assert body["session"] == {
                "cookie_expire_seconds": 1800,
                "cookie_refresh_seconds": 300,
            }

    def test_logout_url_follows_the_configured_prefix(self, tmp_path):
        """The proxy's routes hang off --proxy-prefix, so the link is composed from config
        rather than hardcoded — a hardcoded /oauth would 404 into the dashboard the moment
        the prefix changed, which reads as a logout that silently did nothing."""
        with _client(tmp_path, oauth_proxy_enabled=True, oauth_proxy_prefix="/gate") as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "alice"}).json()
            assert body["logout_url"] == "/gate/sign_out"

    def test_the_configured_durations_are_the_ones_reported(self, tmp_path):
        """whoami restates config; it must not normalise, clamp or invent."""
        with _client(tmp_path, oauth_proxy_enabled=True,
                     session_cookie_expire_seconds=600,
                     session_cookie_refresh_seconds=60) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "alice"}).json()
            assert body["session"] == {
                "cookie_expire_seconds": 600,
                "cookie_refresh_seconds": 60,
            }

    def test_nothing_is_offered_when_the_proxy_is_off(self, tmp_path):
        """No proxy means no session exists to end and no idle timeout anyone enforces.
        A logout link or a countdown here would claim a control that is not there — and the
        identity beside them would be caller-supplied anyway."""
        with _client(tmp_path, oauth_proxy_enabled=False) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "impostor"}).json()
            assert body["authenticated"] is False
            assert body["logout_url"] is None
            assert body["session"] is None

    def test_nothing_is_offered_to_an_anonymous_request(self, tmp_path):
        """Proxy on but no identity header — there is no session to describe, so none is."""
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            body = c.get("/api/whoami").json()
            assert body["authenticated"] is False
            assert body["logout_url"] is None
            assert body["session"] is None


class TestSignedOutPage:
    def test_served_with_no_headers_at_all(self, tmp_path):
        """The proxy's -logout-url target: reached at the exact moment the session cookie
        was cleared, so it must depend on nothing the proxy would have added."""
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            r = c.get("/signed-out")
            assert r.status_code == 200
            assert r.headers["content-type"].startswith("text/html")

    def test_served_even_with_the_proxy_off(self, tmp_path):
        """Unreachable in that mode in practice, but it must not 500 on a mode check."""
        with _client(tmp_path, oauth_proxy_enabled=False) as c:
            assert c.get("/signed-out").status_code == 200

    def test_never_cached(self, tmp_path):
        """Same reasoning as index(): a stale copy after a redeploy would misdescribe what
        logout does — and what it does NOT do is this page's entire message."""
        with _client(tmp_path) as c:
            assert "no-cache" in c.get("/signed-out").headers["cache-control"]

    def test_does_not_overclaim_a_cluster_signout(self, tmp_path):
        """Ending the proxy session does not end the cluster session (the proxy's SignOut
        clears its own cookie and revokes nothing). A governance dashboard implying
        otherwise is worse than no logout button."""
        with _client(tmp_path) as c:
            assert "cluster" in c.get("/signed-out").text.lower()

    def test_records_no_activity_even_with_forged_headers(self, tmp_path):
        """It is reachable unauthenticated, so its headers are caller-supplied by
        definition — the same trust boundary as /healthz, enforced by SKIP_AUTH_PATHS."""
        db = str(tmp_path / "gsd.db")
        settings = Settings(db_path=db, oauth_proxy_enabled=True)
        with TestClient(build_app(settings, run_poller=False)) as c:
            c.get("/signed-out", headers={"X-Forwarded-User": "impostor",
                                          "X-GSD-Interaction": "1"})
        store = Store(db)
        rows = store.user_activity()
        store.close()
        assert rows == []
```

#### D4. `local-development/tests/test_activity.py` — two existing tests updated

Both assert whoami's exact shape, so they fail the moment the new fields land; that exactness is
worth keeping (it catches an accidental extra field), so they are updated rather than loosened.
Whole post-change functions; anchors are their current definitions in `TestTrustBoundary`.

```python
    def test_identity_is_ignored_when_the_proxy_is_off(self, tmp_path):
        """Without the proxy the app binds 0.0.0.0 with no authentication, so anything in
        X-Forwarded-User is caller-supplied. Recording it would fabricate an audit trail."""
        with _client(tmp_path, oauth_proxy_enabled=False) as c:
            body = c.get("/api/whoami", headers={"X-Forwarded-User": "impostor"}).json()
            assert body == {"user": None, "email": None, "authenticated": False,
                            "logout_url": None, "session": None}
            # Refused, not merely empty. This used to return an empty list, which is the
            # same answer a legitimately-unused dashboard gives — so it could not be told
            # apart from "there is nothing to see". 403 says why.
            assert c.get("/api/dashboard/activity").status_code == 403
```

```python
    def test_identity_is_honoured_when_the_proxy_is_on(self, tmp_path):
        with _client(tmp_path, oauth_proxy_enabled=True) as c:
            body = c.get(
                "/api/whoami",
                headers={"X-Forwarded-User": "alice", "X-Forwarded-Email": "a@x.com"},
            ).json()
            assert body == {
                "user": "alice", "email": "a@x.com", "authenticated": True,
                "logout_url": "/oauth/sign_out",
                "session": {"cookie_expire_seconds": 1800, "cookie_refresh_seconds": 300},
            }
```

#### D5. `local-development/tests/test_api_contract.py` — one constant, one docstring sentence

Whole post-change constant; anchor: the `INFRASTRUCTURE` constant (line 31).

```python
# Not every path is an endpoint a reader consumes: the SPA shell, the three unauthenticated
# probe paths, and the logout landing page are infrastructure. They are listed rather than
# pattern-matched so that adding one is a visible decision.
INFRASTRUCTURE = {"/", "/healthz", "/readyz", "/metrics", "/signed-out"}
```

And in `test_docs_are_published_under_api`'s docstring (line 54), the sentence
`oauthProxy.skipAuthRegex admits only the three probe paths, so anything under /api is` becomes
`oauthProxy.skipAuthRegex admits only the probe paths, the signed-out landing page and its two
static assets, so anything under /api is` — it asserts nothing about the regex, so only the
sentence changes.

#### D6. `local-development/tests/test_ui.py` — the UI suites

All Playwright, **appended at the end of the file** (appending cannot disturb the
landmark-slicing tests; the module's `server`/`dash`/`page` fixtures — verified present — and
seeded store are reused unchanged; the module server runs with the proxy off, which is itself
the fixture for "disarmed" behaviour). The dead-session tests record their `page.route` hits and
assert the route fired — the suite's own scar ("a Playwright route glob that never matched") —
so a silently unmatched glob fails loudly.

```python
class TestSessionAwarePolling:
    """The 30s poll used to be unconditional, and every request re-stamps the proxy cookie —
    so an open tab made the idle timeout unreachable. pollTick() returns WHY it did or did not
    fetch, which is what makes suspension testable without watching the network for a minute."""

    def test_the_poll_suspends_after_real_inactivity(self, dash):
        dash.evaluate("""() => {
            window.__fetches = 0;
            const orig = window.fetch;
            window.fetch = (...a) => { window.__fetches++; return orig(...a); };
        }""")
        dash.evaluate("() => { lastActivityAt = Date.now() - IDLE_SUSPEND_MS - 1_000; }")
        assert dash.evaluate("() => pollTick()") == "idle"
        assert dash.evaluate("() => window.__fetches") == 0, (
            "a suspended poll still made a request — every request re-stamps the cookie, so "
            "this is the idle timeout being defeated, not a wasted fetch"
        )

    def test_an_active_reader_still_gets_the_poll(self, dash):
        dash.evaluate("() => { lastActivityAt = Date.now(); lastAutoRefreshAt = 0; }")
        assert dash.evaluate("() => pollTick()") == "refreshed"

    def test_a_hidden_tab_does_not_poll(self, dash):
        dash.evaluate("""() => Object.defineProperty(
            document, 'hidden', { get: () => true, configurable: true })""")
        dash.evaluate("() => { lastActivityAt = Date.now(); lastAutoRefreshAt = 0; }")
        assert dash.evaluate("() => pollTick()") == "hidden"

    def test_pointermove_alone_is_not_activity(self, dash):
        """The trap: browsers synthesize pointermove when layout changes under a stationary
        cursor — which this page does to itself on every poll — and a resting hand jitters.
        Counting it would re-arm the idle timer forever on an unattended machine."""
        dash.evaluate("() => { lastActivityAt = Date.now() - IDLE_SUSPEND_MS - 1_000; }")
        dash.mouse.move(200, 200)
        dash.mouse.move(320, 260)
        assert dash.evaluate("() => pollTick()") == "idle"

    def test_returning_from_idle_refreshes_once_not_a_burst(self, dash):
        """Interval, catch-up and visibilitychange can land in the same instant when a tab
        wakes; the guard must collapse them to one request cycle."""
        dash.evaluate(
            "() => { lastActivityAt = Date.now() - IDLE_SUSPEND_MS - 60_000; lastAutoRefreshAt = 0; }")
        # The first deliberate act after idleness triggers the single catch-up...
        dash.evaluate("() => window.dispatchEvent(new Event('pointerdown'))")
        # ...and every immediately-following trigger sees it already happened.
        assert dash.evaluate("() => pollTick()") == "fresh"
        dash.evaluate("() => window.dispatchEvent(new Event('keydown'))")
        assert dash.evaluate("() => pollTick()") == "fresh"


class TestSessionCountdownModal:
    def _arm(self, dash, remaining_ms):
        """A model armed as if whoami reported 30m/5m and the deadline sat remaining_ms away.
        Driving internals directly matches the suite's idiom (tests already call render() and
        navigate()); the 25-minute wait a real deadline needs is not a test."""
        dash.evaluate("""(ms) => {
            sessionOver = false;
            const stamp = Date.now() - 1_800_000 + ms;
            sessionModel = { expireMs: 1_800_000, refreshMs: 300_000, lo: stamp, hi: stamp };
        }""", remaining_ms)

    def test_no_modal_while_the_session_is_healthy(self, dash):
        self._arm(dash, 20 * 60_000)
        assert dash.evaluate("() => sessionTick()") == "armed"
        assert not dash.evaluate("() => document.getElementById('session-dialog').open")

    def test_the_modal_appears_inside_the_warning_window(self, dash):
        self._arm(dash, 90_000)
        assert dash.evaluate("() => sessionTick()") == "warning"
        dlg = dash.locator("#session-dialog")
        assert dlg.evaluate("d => d.open")
        text = dlg.inner_text()
        assert "about to end" in text and "Stay signed in" in text
        # An open warning must also silence the poll — a poll would answer for the reader.
        assert dash.evaluate("() => pollTick()") == "warned"

    def test_stay_signed_in_closes_and_resets_the_model(self, dash):
        self._arm(dash, 90_000)
        dash.evaluate("() => sessionTick()")
        dash.locator("#session-stay").click()
        assert not dash.evaluate("() => document.getElementById('session-dialog').open")
        # The click's refresh() re-proves the session: the idle gap exceeds cookie-refresh by
        # construction, so noteAuthedResponse takes the certain branch and the floor is now.
        dash.wait_for_function("() => Date.now() - sessionModel.lo < 10_000")

    def test_escape_counts_as_staying_not_as_dismiss_and_die(self, dash):
        dash.focus("#refresh")
        self._arm(dash, 90_000)
        dash.evaluate("() => sessionTick()")
        dash.keyboard.press("Escape")
        assert not dash.evaluate("() => document.getElementById('session-dialog').open")
        # Raises on timeout if Escape dismissed without extending — the session would then die
        # silently, which is the exact failure the dialog exists to prevent.
        dash.wait_for_function("() => Date.now() - sessionModel.lo < 10_000")

    def test_focus_lands_in_the_dialog_is_trapped_and_returns(self, dash):
        dash.focus("#refresh")
        self._arm(dash, 90_000)
        dash.evaluate("() => sessionTick()")
        assert dash.evaluate("() => document.activeElement.id") == "session-stay"
        # The trap property that matters: Tab must never reach a control BEHIND the modal.
        # Everything on the page lives under .wrap and the dialog is outside it, so the
        # assertion is "focus never lands inside .wrap" rather than "focus stays inside the
        # dialog" — engines legitimately park focus on the dialog or body while wrapping a
        # single-focusable dialog, and asserting containment would fail on that, not on a bug.
        for _ in range(5):
            dash.keyboard.press("Tab")
            escaped = dash.evaluate(
                "() => !!(document.activeElement.closest && document.activeElement.closest('.wrap'))")
            assert not escaped, "Tab reached a control behind a modal dialog"
        dash.keyboard.press("Escape")
        assert dash.evaluate("() => document.activeElement.id") == "refresh", (
            "focus was not restored to where the reader left it"
        )

    def test_the_ticking_counter_is_not_a_live_region(self, dash):
        """aria-live on a per-second counter makes a screen reader narrate every tick — the
        classic mistake. The counter is aria-hidden; a status region announces milestones."""
        self._arm(dash, 90_000)
        dash.evaluate("() => sessionTick()")
        assert dash.locator("#session-remaining").get_attribute("aria-hidden") == "true"
        assert dash.locator("#session-count").get_attribute("aria-live") is None
        announce = dash.locator("#session-announce")
        assert announce.get_attribute("role") == "status"
        # text_content, not inner_text: the region is .sr-only (1px, clipped), and innerText
        # of a clipped box is engine-dependent while textContent is not.
        assert "minute" in announce.text_content(), "no announcement at open"

    def test_dialog_declares_itself_to_assistive_tech(self, dash):
        self._arm(dash, 90_000)
        dash.evaluate("() => sessionTick()")
        dlg = dash.locator("#session-dialog")
        assert dlg.get_attribute("aria-modal") == "true"
        assert dlg.get_attribute("aria-labelledby") == "session-title"
        assert dlg.get_attribute("aria-describedby") == "session-desc"

    def test_a_passed_deadline_is_the_over_state_not_silence(self, dash):
        """Also the wake-from-sleep case: timers froze, Date.now() jumped, the next tick must
        land HERE rather than resume polling a dead session."""
        self._arm(dash, -60_000)
        assert dash.evaluate("() => sessionTick()") == "ended"
        dlg = dash.locator("#session-dialog")
        assert dlg.evaluate("d => d.open")
        assert "has ended, or is about to" in dlg.inner_text(), (
            "a modeled end is a floor — claiming certain death would be its own small lie"
        )
        assert dash.locator("#session-signin").is_visible()
        assert dash.locator("#session-signin").get_attribute("href") == "/"
        assert dash.locator("#session-stay").is_hidden()
        assert dash.evaluate("() => pollTick()") == "over"

    def test_a_modeled_end_unlatches_when_another_tab_kept_the_session(self, dash):
        """Tabs share the cookie; the shared stamp is how a background tab learns a foreground
        tab's activity made its warning moot."""
        self._arm(dash, -60_000)
        dash.evaluate("() => sessionTick()")
        dash.evaluate("""() => localStorage.setItem('gsd:session-stamp',
            JSON.stringify({ lo: Date.now(), hi: Date.now() }))""")
        assert dash.evaluate("() => sessionTick()") == "armed"
        assert not dash.evaluate("() => document.getElementById('session-dialog').open")
        assert dash.evaluate("() => sessionOver") is False

    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_modal_text_meets_aa_in_both_themes(self, dash, theme):
        """test_accessibility.py already guards every token PAIR the dialog uses; this checks
        the RENDER — that the dialog actually resolves to those tokens in both themes."""
        if theme == "dark":
            dash.evaluate("() => document.documentElement.setAttribute('data-theme', 'dark')")
        self._arm(dash, 90_000)
        dash.evaluate("() => sessionTick()")
        contrast_js = """(sel) => {
            const el = document.querySelector(sel);
            const parse = (c) => c.match(/[\\d.]+/g).slice(0, 3).map(Number);
            const lum = ([r, g, b]) => {
                const f = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92
                    : ((v + 0.055) / 1.055) ** 2.4; };
                return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b);
            };
            let bgEl = el, bg;
            while (bgEl) {
                bg = getComputedStyle(bgEl).backgroundColor;
                if (bg && !bg.includes("0, 0, 0, 0")) break;
                bgEl = bgEl.parentElement;
            }
            const a = lum(parse(getComputedStyle(el).color)), b = lum(parse(bg));
            return (Math.max(a, b) + 0.05) / (Math.min(a, b) + 0.05);
        }"""
        for sel in ["#session-title", "#session-desc", "#session-count", "#session-stay"]:
            got = dash.evaluate(contrast_js, sel)
            assert got >= 4.5, f"{theme}: {sel} renders at {got:.2f}:1, below WCAG AA"


class TestSessionModelSoundness:
    """The model is a provable floor on the deadline; these replay the arithmetic that keeps it
    one, including the exact sequence that breaks the naive version."""

    def test_a_maybe_restamp_raises_the_floor_but_never_to_now(self, dash):
        """The unsound shortcut — 'assume a re-stamp whenever the MODEL's age crosses refresh' —
        concludes a re-stamp the proxy may not have made and warns AFTER the expiry. The hull
        update must raise the floor only to sentAt - refresh."""
        got = dash.evaluate("""() => {
            sessionOver = false;
            const now = Date.now();
            sessionModel = { expireMs: 1_800_000, refreshMs: 300_000,
                             lo: now - 360_000, hi: now - 60_000 };
            noteAuthedResponse(now);
            return { loAge: now - sessionModel.lo, hiAge: now - sessionModel.hi };
        }""")
        assert 299_000 <= got["loAge"] <= 301_000, (
            f"floor moved to {got['loAge']}ms ago — a maybe-re-stamp must raise it exactly to "
            f"sentAt - refresh, never to sentAt"
        )
        assert got["hiAge"] <= 1_000

    def test_a_certain_restamp_makes_the_model_exact(self, dash):
        got = dash.evaluate("""() => {
            sessionOver = false;
            const now = Date.now();
            sessionModel = { expireMs: 1_800_000, refreshMs: 300_000,
                             lo: now - 400_000, hi: now - 400_000 };
            noteAuthedResponse(now);
            return { loAge: Date.now() - sessionModel.lo, hiAge: Date.now() - sessionModel.hi };
        }""")
        assert got["loAge"] <= 1_000 and got["hiAge"] <= 1_000

    def test_a_provably_young_session_teaches_nothing(self, dash):
        got = dash.evaluate("""() => {
            sessionOver = false;
            const now = Date.now();
            sessionModel = { expireMs: 1_800_000, refreshMs: 300_000,
                             lo: now - 100_000, hi: now - 100_000 };
            noteAuthedResponse(now);
            return Date.now() - sessionModel.lo;
        }""")
        assert 99_000 <= got <= 101_000, "the proxy provably did not re-stamp; the model moved"


class TestDeadSessionLegibility:
    """Today an auth redirect surfaces as 'Dashboard API error: Unexpected token <' over a note
    blaming a deleted object. The route-hit asserts are the lesson from this suite's own scar:
    a glob that never matches must fail loudly, not prove nothing."""

    def test_an_auth_redirect_is_named_not_a_json_parse_error(self, dash):
        hits = []

        def as_proxy_bounce(route):
            hits.append(route.request.url)
            route.fulfill(status=302, headers={"Location": "/oauth/sign_in"})

        dash.route("**/api/clusters", as_proxy_bounce)
        dash.evaluate("() => refresh()")
        dash.wait_for_selector("#session-dialog[open]")
        assert hits, "the route glob never matched — this test proved nothing"
        text = dash.locator("#session-dialog").inner_text()
        assert "Sign in again" in text
        assert "single sign-on" in text, (
            "the over-state must not overclaim: the cluster SSO session survives a proxy logout"
        )
        body = dash.locator("body").inner_text()
        assert "Unexpected token" not in body
        assert "Dashboard API error" not in body
        assert dash.evaluate("() => sessionOver") == "confirmed"
        assert dash.evaluate("() => pollTick()") == "over", (
            "a dead session kept polling — each poll would bounce through the login flow"
        )

    def test_html_where_json_was_expected_is_the_same_verdict(self, dash):
        """A proxy that serves its sign-in page with 200 instead of redirecting."""
        hits = []

        def as_login_page(route):
            hits.append(route.request.url)
            route.fulfill(status=200, content_type="text/html",
                          body="<html><body>Log in to continue</body></html>")

        dash.route("**/api/clusters", as_login_page)
        dash.evaluate("() => refresh()")
        dash.wait_for_selector("#session-dialog[open]")
        assert hits, "the route glob never matched — this test proved nothing"
        assert dash.evaluate("() => sessionOver") == "confirmed"


class TestLogoutLink:
    def test_absent_when_there_is_no_session_to_end(self, dash):
        """The module server runs with the proxy off; offering to end a session that does not
        exist is the refusal /api/whoami already encodes and the header must honour."""
        assert dash.locator("#logout").is_hidden()
        assert dash.locator("#whoami").is_hidden()
        assert dash.evaluate("() => sessionModel") is None

    def test_present_named_and_wired_when_whoami_offers_it(self, page, server):
        hits = []

        def as_authenticated(route):
            hits.append(route.request.url)
            route.fulfill(json={
                "user": "jane.smith", "email": "jane.smith@example.com",
                "authenticated": True, "logout_url": "/oauth/sign_out",
                "session": {"cookie_expire_seconds": 1800, "cookie_refresh_seconds": 300},
            })

        page.route("**/api/whoami", as_authenticated)
        page.goto(server)
        page.wait_for_selector(".hero .value")
        page.wait_for_selector("#logout:not([hidden])")
        assert hits, "the route glob never matched — this test proved nothing"
        link = page.locator("#logout")
        assert link.inner_text() == "Sign out", "the accessible name is the link text"
        assert link.get_attribute("href") == "/oauth/sign_out"
        assert page.locator("#whoami").inner_text() == "jane.smith"
        # The same whoami arms the countdown model with the chart-configured lifetimes.
        assert page.evaluate("() => sessionModel && sessionModel.expireMs") == 1_800_000
        assert page.evaluate("() => sessionModel && sessionModel.refreshMs") == 300_000
        # And the dialog's own sign-out action points at the same place.
        assert page.locator("#session-signout").get_attribute("href") == "/oauth/sign_out"

    def test_refresh_disabled_disarms_the_countdown_but_not_the_link(self, page, server):
        """The provider=openshift contingency: if the lab proves cookie-refresh unusable, the
        chart ships refresh 0 — the deadline is then absolute and unobservable, so the modal
        must disarm while logout and the dead-session failover keep working."""
        page.route("**/api/whoami", lambda route: route.fulfill(json={
            "user": "jane.smith", "email": None, "authenticated": True,
            "logout_url": "/oauth/sign_out",
            "session": {"cookie_expire_seconds": 1800, "cookie_refresh_seconds": 0},
        }))
        page.goto(server)
        page.wait_for_selector("#logout:not([hidden])")
        assert page.evaluate("() => sessionModel") is None
        assert page.evaluate("() => sessionTick()") == "disarmed"
```

Why each UI test honestly fails first: every one references `pollTick`, `sessionTick`,
`sessionModel`, `noteAuthedResponse`, `#session-dialog`, `#logout` or `err.sessionExpired` —
none of which exists on the current tree — so each fails with a JS reference error, a missing
selector, or (for the dead-session pair) the old "Unexpected token" card where the dialog is
awaited.

---

## 4. Consolidated test list

Deduplicated; boundary invariants that pass-before are marked *(inv)* — they pin guard
stand-down and untouched paths, which by construction cannot fail before the guards exist.

**`tests/test_chart_strategy.py`** (add `import re`; 22 tests)
- TestSessionCookieLifetime: defaults render 30m/5m; empty refresh omits the flag; `"0"`
  normalises to omission; nulled cookie block falls back to defaults; ConfigMap carries the same
  duration strings as the flags; disabled refresh reaches the app as `""`; refresh ≥ expire
  refused at render; non-durations refused at render (`8hr`, bare `30`, `5 minutes`);
  proxy-off renders with bad values *(inv)*.
- TestCookieSecretLengthGuard: invalid supplied secret with refresh on fails; guard stands down
  with refresh off *(inv)*; 32-byte raw passes *(inv)*; base64 measured after decoding *(inv)*;
  `twentybytesexactly1` passes (proxy-parity) *(inv)*; `+`-bearing standard-base64 refused;
  generated-secret path untouched *(inv)*.
- TestLogoutWiring: default `-logout-url=/signed-out`; `/signed-out` **and the two static
  assets** match the rendered skipAuthRegex, probe paths still match, `/api/version` and other
  `/static` paths do not; SSO override replaces the default; dropping signed-out from the regex
  without an override is refused; custom regex + SSO override allowed *(inv)*; proxyPrefix
  reaches flag, ConfigMap and redirect URI together.

**`tests/test_config.py`** (13 tests)
- TestProxyPrefix: default `/oauth`; ConfigMap value used; env wins; trailing slash normalised;
  relative prefix fails at startup.
- TestSessionDurationSettings: defaults 1800/300; Go spellings parse; fractional units;
  `""`/`"0"`/`"0s"` → 0; malformed durations fail naming the key; refresh < expire enforced;
  env override wins and is validated.

**`tests/test_session_api.py`** (new file, 10 tests)
- TestWhoamiSession: logout_url + session offered behind the proxy; logout_url follows the
  prefix; configured durations restated unclamped; nothing offered proxy-off; nothing offered
  anonymous.
- TestSignedOutPage: served with no headers; served proxy-off; never cached; does not overclaim
  a cluster sign-out; records no activity even with forged headers.

**`tests/test_activity.py`** (2 updated — whoami exact-shape assertions extended)

**`tests/test_api_contract.py`** (INFRASTRUCTURE gains `/signed-out`; one docstring sentence)

**`tests/test_ui.py`** (23 tests, appended)
- TestSessionAwarePolling: suspends after inactivity (with zero fetches); active reader still
  polls; hidden tab does not poll; pointermove is not activity; return from idle is one refresh,
  not a burst.
- TestSessionCountdownModal: no modal while healthy; appears in the warning window and silences
  the poll; stay-signed-in closes and resets the model; Escape = stay, not dismiss-and-die;
  focus trapped and restored; ticking counter is not a live region; dialog declares itself to
  AT; passed deadline → over-state (also the sleep/wake case); modeled end un-latches via the
  shared stamp; AA contrast in both themes (rendered, not just token pairs).
- TestSessionModelSoundness: maybe-re-stamp raises the floor only to `sentAt − refresh`;
  certain re-stamp makes the model exact; provably-young response teaches nothing.
- TestDeadSessionLegibility: an auth redirect is named, not a JSON parse error, and latches
  `"confirmed"` + stops polling; HTML-with-200 is the same verdict. (Route-hit asserts on both.)
- TestLogoutLink: absent with no session; present/named/wired from whoami (and arms the model);
  refresh 0 disarms the countdown but not the link or the failover.

---

## 5. If the lab shows `cookie-refresh` unusable with provider=openshift

The research doc's go/no-go: `ValidateSessionState` → `validateToken` sends the token as a
**query parameter** to `/apis/user.openshift.io/v1/users/~` and accepts only HTTP 200; if the
API server 401s that, every refresh clears the session and `cookie-refresh` becomes a forced
logout rather than a slide. Being tested on the lab (verification step 1 of the research doc).
If it fails, this design loses **one default and flips a handful of assertions; no layer is
redesigned**:

1. **Chart**: `values.yaml` flips `refresh: 5m` → `refresh: ""`, and the comment block gains its
   closing fact — suggested wording: `# refresh is DISABLED by default: with provider=openshift
   the revalidation sends the token as a query parameter, which the API server rejects, turning
   every refresh into a forced logout. See docs/DESIGN_oauth_session_and_logout.md before
   enabling.` The 30m expire stays and becomes an absolute (login+30m) timeout. Everything else
   — helpers, guards, the secret-length check (still correct for any operator who enables
   refresh anyway, or for a `pass-access-token` future), the omission logic, the logout wiring,
   NOTES (the refresh-off branch already exists and is exercised) — is used unchanged.
2. **App**: the `Settings` default `session_cookie_refresh_seconds: int = 300` flips to `0`. The
   ConfigMap then carries `sessionCookieRefresh: ""`, which the parser already reads as 0 — no
   code change. The API contract ("configured durations, truthfully restated") holds in both
   worlds, which is precisely why the API exposes durations and not a deadline.
3. **UI — nothing is re-coded.** `initSession` disarms on `cookie_refresh_seconds: 0` (tested:
   `test_refresh_disabled_disarms_the_countdown_but_not_the_link`), so the countdown goes
   dormant *as data*. Poll suspension stays and stays correct: with an absolute cookie, polls
   never extended the session anyway, but a suspended tab also stops hammering the login flow
   after expiry. The dead-session failover (§C3/§C4) becomes the entire end-of-session UX: the
   first request after the absolute expiry surfaces the "Signed out" dialog instead of a parse
   error. The logout link is untouched. The warning path stays in the codebase because
   re-enabling it is a values change, not a release.
4. **Test assertions that flip** (mechanical, listed exhaustively):
   `test_defaults_render_the_thirty_minute_sliding_window` (asserts no `-cookie-refresh` flag),
   the defaults leg of `test_disabled_refresh_reaches_the_app_as_the_empty_string`,
   `test_defaults_mirror_the_chart` (`== 0`), and the two whoami exact-shape assertions carrying
   `"cookie_refresh_seconds": 300` (`test_logout_and_session_are_offered_behind_the_proxy`,
   `test_identity_is_honoured_when_the_proxy_is_on`).

---

## 6. What this design deliberately does not do, and the honest limits of the logout

- **The logout ends the dashboard session, not the cluster SSO session.** The proxy's `SignOut`
  clears its own cookie and revokes nothing; the OpenShift OAuth server keeps its session cookie
  and will re-issue a token without prompting (research Finding 2), and on the reference cluster
  `accessTokenMaxAgeSeconds` is 365 days with no inactivity timeout — nothing above the proxy
  cuts a session short. The `/signed-out` page and the over-state dialog both say so in plain
  words; a governance dashboard that implied "fully signed out" would be worse than no button.
  True single sign-out is available where the cluster has a real SSO logout endpoint, via
  `oauthProxy.logoutUrl` — and that override is deliberately invisible to the app (whoami's
  `logout_url` always points at the proxy's own `sign_out`; where the browser lands afterwards
  is the proxy's business). This design does **not** implement the research doc's earlier
  auto-POST-to-`/logout` sketch or a 4-hour absolute cap — the operator's decisions superseded
  that plan.
- **No server-side session or last-seen tracking.** The proxy's stamp times are unobservable
  from the app, and `activity.py`'s per-user-per-day, interaction-only, buffered, per-replica
  design is wrong for a per-browser session model on every axis — reusing it would un-fix a
  measured defect (722 recorded "uses" from tab-open time). The model lives in the browser,
  where the information lives. `activity.py` is untouched.
- **No dedicated keepalive endpoint.** The proxy extends the cookie on any proxied request;
  "authenticated but not session-extending" does not exist in this proxy, so a `/api/keepalive`
  would document a capability the app does not have. Equally, nothing is moved into
  `skipAuthRegex` to stop it sliding the session — a skipped path is unauthenticated, and
  serving RBAC data unauthenticated is not a trade this design will make.
- **No automatic probe when the modeled deadline passes.** A probe is a request; a request
  re-stamps a still-live cookie — extending the session with nobody present, quietly rebuilding
  the exact bug this feature removes. The over-state says "has ended, or is about to" and one
  click recovers either way.
- **GET logout, drive-by accepted.** A cross-site `<img src=…/oauth/sign_out>` can end a session
  unwantedly; the cost is a fresh login with zero data exposure or mutation. The operator chose
  the GET link; a POST form is the alternative if that trade is ever revisited.
- **No `values.schema.json`.** The constraints are relational and need paragraph-quality errors;
  a partial schema implies validation the rest of values.yaml does not have (§A4 rationale).
- **Known bounded gaps, named:** a reader with hands off mouse and keyboard for longer than
  `IDLE_SUSPEND_MS + (expire − warn)` gets the modal while present — one click, bounded
  annoyance; the alternative (counting `pointermove`) re-opens the hole entirely. The signed-out
  page renders in system fonts (§1.3). The shared-stamp merge trusts same-origin
  `localStorage` — anything able to write it can only make warnings earlier or moot-close them,
  never move the true cookie expiry, and a same-origin attacker is already past every control
  this page has. `redirect: "manual"` assumes the app never redirects `/api/*` — true today
  (exact FastAPI routes); the `api()` comment states the assumption where a future author will
  trip over it. Kiosk/TV deployments get no input events and idle out at ~`expire` by design;
  the values comment points such clusters at a longer `cookie.expire`, not a UI exemption.

---

## 7. Post-apply verification (beyond the suite)

The research doc's lab sequence still applies verbatim (its step 1 is the §5 gate; steps 2–8
cover idle expiry, sliding, revocation, logout behaviour, non-revocation, the render-time secret
guard, and Playwright in both themes). One addition from lens 1: confirm once on the lab that
the `-logout-url=/signed-out` relative redirect arrives as `Location: /signed-out` on the
sign-out 302 (fallback is the one-line absolute-URL default in §A3b). And two paper checks after
apply: `helm template` with defaults renders flags, ConfigMap strings and redirect URI
byte-identical to §A3b/§A5/§A6's stated outputs; the full suite runs green from the worktree
(`1058 + additions passed, 1 skipped`).
