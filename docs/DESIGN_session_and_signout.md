# Session lifetime and sign-out

What the dashboard does about sessions, and the measurements behind it. Everything described here
is implemented; the last section names what deliberately is not, so nobody rebuilds it hopefully.

## What ships

| control | mechanism | value |
|---|---|---|
| absolute session cap | `-cookie-expire` on the oauth-proxy sidecar | `4h`, from `oauthProxy.cookie.expire` |
| sign-out | header link to the proxy's own `sign_out` | hidden until `/api/whoami` reports a session |
| landing page | `/signed-out`, unauthenticated and script-free | states what ended and what did not |
| end-of-session panel | `api()` recognises an auth redirect | replaces a JSON parse error with an explanation |
| idle timeout (module, off by default) | the page's idle model → the proxy's `sign_out` | `session.idleTimeout.{minutes,warningSeconds}` |

The cap is **absolute, measured from login, and does not slide**. An active reader is signed out at
four hours too. That is a consequence of the next section rather than a choice, and the lever is the
number in values, not the design.

`/api/whoami` reports `logout_url` (the proxy's `sign_out`, composed from `oauthProxy.proxyPrefix`)
and `session.cookie_expire_seconds`. The page reads the cap from there rather than hardcoding it, so
an operator lowering `cookie.expire` cannot leave the UI quoting a number the proxy no longer
enforces. `initSession()` reads it once at load for the session controls and the idle model; the
ordinary data refresh also fetches it, because the viewer's tier can change while the page is open.
There is **no session-only timer** — every request through the proxy re-stamps the session cookie,
so a page that asked about its own session on a timer would hold that session open forever — and
the automatic data refresh is suspended while the idle model is warning or expired.

## Measurements

Each of these was reproduced on the reference cluster. They are the reason the design is small.

### `-cookie-refresh` is unusable with `provider=openshift`

The proxy's refresh-time revalidation (`validateToken`) sends the token as a **query parameter** and
accepts only HTTP 200:

```
GET <api>/apis/user.openshift.io/v1/users/~   with an Authorization header  ->  200, user "kubeadmin"
GET <api>/apis/user.openshift.io/v1/users/~?access_token=<token>            ->  403 "system:anonymous"
```

The API server ignores the parameter and treats the caller as anonymous. The OpenShift provider does
not override `RefreshSessionIfNeeded`, so the default returns `(false, nil)`, `revalidated` stays
false, and `Redeem` populates `session.AccessToken` for every browser login — so the validation runs
and fails at every interval, **clearing** the session rather than extending it.

Kibana's oauth-proxy sidecar (`openshift/elasticsearch-operator`, `internal/kibana/reconciler.go`) is
a shipped Red Hat product on this same provider and sets `-cookie-expire` with **no**
`-cookie-refresh`. The chart refuses a values file that sets `cookie.refresh`, with this measurement
in the error, so it cannot be re-enabled hopefully.

### A dead proxy cookie demands credentials here

Cleared only `_oauth_proxy`, leaving a nine-second-old `ssn` in place: the OAuth server **asked for
credentials**. It keeps no reusable session for this client. `ssn` is a session cookie
(`expires=-1`), host-scoped, `SameSite=Lax`, HttpOnly — transient login-flow state, not a durable SSO
session.

This is why the four-hour cap is a real forced re-login rather than a redirect flicker, and why no
further mechanism was needed to make sign-out mean something. **Behind an external OIDC or
request-header IdP the upstream session is untouched and re-entry may not prompt**, which is why the
signed-out page says "asks the cluster to authenticate you… though a cluster fronted by an external
single-sign-on provider may not" rather than promising a prompt.

### Token revocation is refused by the token's own scope

Sign-out briefly revoked the OAuth token the way the OpenShift console's logout does — `DELETE` on
the `oauthaccesstokens` object whose name derives from the token. It was built, deployed, and
measured returning **403** with everything else working: the proxy forwarded the token, the
derivation resolved a real object, the request was well-formed and self-scoped.

| client | scopes on its tokens |
|---|---|
| `console` | `["user:full"]` |
| `oc` (`openshift-challenging-client`) | `["user:full"]` |
| **this chart** (ServiceAccount as OAuth client) | **`["user:info", "user:check-access"]`** |

The console can revoke because its tokens carry full scope. `user:info` reads your own user and
`user:check-access` performs SubjectAccessReviews; neither permits deleting anything.

**The trap worth remembering**: `oc auth can-i delete oauthaccesstokens --as=<user>` answers **yes**,
because a SubjectAccessReview asks only whether the *user* may do a thing. It never sees the token's
**scope**, which is a separate and narrower gate applied at request time. Unit tests passed too,
because they mock the API. Only a live run could find this.

Widening `-scope` to `user:full` would make revocation work by handing a read-only dashboard a
credential able to act as the user anywhere on the cluster, in exchange for shortening the window in
which a *leaked* token stays valid. That is a worse trade than not revoking, and it would discard the
"constrained form of OAuth client" limit the ServiceAccount route provides for free. So
`-pass-access-token` is not set and the app never sees a user token.

### The OAuth server's `/logout` does not help

```
GET  https://oauth-openshift.<domain>/logout   ->  405 Method Not Allowed
POST https://oauth-openshift.<domain>/logout   ->  200, EMPTY BODY, no Location
```

POST-only with no CSRF validation (`oauth-server`'s own `pkg/server/logout/logout.go` carries a
`TODO` conceding "this endpoint is invokable via JS"), and it calls
`InvalidateAuthentication(w, &user.DefaultInfo{})` — it never reads the incoming session. Measured
from a same-site credentialed `fetch`: the `ssn` cookie was **unchanged** before and after. Without a
valid `then` parameter the response is an empty body, so navigating there lands the reader on a blank
page. `-logout-url` has zero real uses across the `openshift` GitHub organisation.

### Cluster token policy is not ours to set

`accessTokenInactivityTimeout` and `accessTokenMaxAgeSeconds` live on the cluster-scoped `OAuth` CR
and apply to **every** client, so a namespaced chart must not touch them. Per-client equivalents
exist only on an `OAuthClient` object, which the ServiceAccount-as-client shortcut does not have —
which is precisely why Kibana derives its cookie lifetime from the cluster's setting instead of
owning one.

A naming trap if anyone revisits this: `accessTokenInactivityTimeoutSeconds` exists on **both**
objects. On the cluster `OAuth` CR it is `DEPRECATED: setting this field has no effect`; on
`OAuthClient` it is active, with a minimum of 300 seconds. Same field name, one dead and one alive.

## Chart details worth knowing

**`skipAuthRegex` admits six paths and no more.** `/signed-out` must be reachable unauthenticated —
behind the proxy it would start a fresh OAuth flow and return the reader signed in, the opposite of
what they clicked — and it links `app.css` and `favicon.svg`, so those are admitted too. The vendored
fonts stay authenticated, so the page falls back to system fonts rather than widening the
unauthenticated surface further. `/static/index.html`, `/api/*` and `/` remain authenticated, asserted
path by path in `tests/test_chart_strategy.py`.

**`dig` is avoided in the helpers.** It panics on an intermediate that exists and is nil —
`interface conversion: interface {} is nil, not map[string]interface {}` — which is what a values
file produces the moment somebody comments out the keys under `cookie:`. A trailing `| default`
cannot rescue it, because the error happens inside `dig` before any value returns.

**`toString` before `%q` in guard messages.** An unquoted number in a values file is typed as an
integer, and `%q` on an int64 renders it as a Unicode rune — `expire: 14400` produced an error
message about the character `㡀`.

**Comments in a Helm template are YAML comments** and are emitted into the rendered manifest. A
`grep` over the render for `cookie-refresh` therefore matches the comment explaining its absence and
reports the opposite of the truth; chart tests parse arg lines instead.

## Deliberately not implemented

**A page-enforced idle timeout with a countdown** — designed in full, reviewed adversarially,
deferred at first because it was the largest and most fragile part of the original plan, and now
built as an off-by-default module (application 0.16.0, `session.idleTimeout`,
`docs/specs/SPEC_C4_idle_timeout.md`), applying the three lessons that were recorded here for
exactly this:

- **The idle timeout cannot be derived from the cookie pair.** The original design computed it as
  `expire - refresh .. expire`, which is sound only while the cookie slides — and it does not. *Met:*
  the module has its own three keys, rendered beside `sessionCookieExpire`, validated at render
  (`charts/group-sync-dashboard/templates/_helpers.tpl#gsd.idleTimeoutMinutes`) and at load
  (`gsd/config.py#_idle_timeout_setting`); the chart refuses a window at or beyond the cap, which
  could never fire.
- **The page cannot observe its own session deadline.** The cookie is HttpOnly and the proxy forwards
  no session-age header, so any countdown is a *model*. `localStorage` persists **across** sessions,
  so an origin recorded there is routinely older than the current session and a timer counting from
  it fires early — instantly, and repeatedly, after a re-login. *Met:* the page persists nothing; at
  zero it removes the data from the screen and sends the browser to the proxy's `sign_out`, and the
  proxy clears the cookie (`gsd/static/index.html#function idleExpire`). The "session has ended" panel
  still comes only from a request that came back as an auth redirect, never from the timer. Activity
  is shared across a browser's tabs over a `BroadcastChannel`, which is ephemeral, so an idle tab
  cannot sign out a colleague working in another. A tab that never reaches `sign_out` (a closed
  laptop) is still ended by the absolute cap.
- **The poll must suspend on real inactivity, or the timeout is unreachable.** *Met:* every automatic
  refresh passes one gate, `gsd/static/index.html#function autoRefresh`, which returns while the
  countdown is up or expired; "Stay signed in" resumes with one interaction-marked refresh.

**Token revocation, `-pass-access-token`, a `POST` to the OAuth server's `/logout`, and an
`OAuthClient` of our own.** Each was designed and each is refuted or made unnecessary by a
measurement above.
