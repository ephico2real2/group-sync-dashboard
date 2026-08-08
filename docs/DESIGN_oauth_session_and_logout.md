# Session lifetime and a logout button

Branch `feat/oauth-session-and-logout`. Two features against the oauth-proxy sidecar:

1. `-cookie-refresh` / `-cookie-expire`, parameterised through `values.yaml`.
2. A logout button — API first, then UI — wired to the proxy's sign-out endpoint.

Nothing is implemented yet. This is the research and the plan, and it opens with two findings that
change what gets built.

---

## Finding 1 — the endpoint is `/oauth/sign_out`, not `/oauth2/sign_out`

`/oauth2/...` is **upstream oauth2-proxy**. We run `openshift/oauth-proxy`, a fork of oauth2_proxy v3,
whose default proxy prefix is `/oauth`. From `oauthproxy.go`, the routes are registered relative to
`ProxyPrefix`:

| variable | suffix | our full path |
|---|---|---|
| `SignInPath` | `/sign_in` | `/oauth/sign_in` |
| `SignOutPath` | `/sign_out` | **`/oauth/sign_out`** |
| `OAuthStartPath` | `/start` | `/oauth/start` |
| `OAuthCallbackPath` | `/callback` | `/oauth/callback` |
| `AuthOnlyPath` | `/auth` | `/oauth/auth` |

This repo already depends on that prefix and proves it: `deployment.yaml` sets
`serviceaccounts.openshift.io/oauth-redirecturi.primary` to `https://<host>/oauth/callback`, and the
live cluster accepts it. A button pointing at `/oauth2/sign_out` would 404 into the dashboard itself.

The prefix is settable with `--proxy-prefix`, which we do not pass — so `/oauth` it is. The plan below
derives the path from config rather than hardcoding it in the page, so the two cannot drift.

## Finding 2 — sign-out on its own signs the user straight back in

`SignOut` does exactly three things:

```go
p.ClearSessionCookie(rw, req)
redirectURL := "/"
if len(p.LogoutRedirectURL) > 0 { redirectURL = p.LogoutRedirectURL }
http.Redirect(rw, req, redirectURL, 302)
```

It **ignores `rd`**, and it **does not revoke the OpenShift access token**. So the default redirect
lands on `/`, which is behind the proxy, which starts a fresh OAuth flow — and because the browser
still holds the OpenShift OAuth server's own session cookie, the server re-issues a token without
prompting. The user clicks "Sign out" and arrives back on the dashboard, logged in.

This is a known OpenShift-specific behaviour, not a quirk of our setup: the OAuth server "may re-use
that previous session and redirect back with a fresh access token without asking for credentials."

**Consequence for the design:** the logout button needs somewhere to land that is *not* behind the
proxy. The plan adds an unauthenticated `/signed-out` page in our own app, listed in
`skipAuthRegex`, and points `-logout-url` at it.

**And it must not overclaim.** Ending the proxy session does not end the cluster session. The page has
to say so plainly, because a governance dashboard that implies "you are fully signed out" when the next
click would re-authenticate silently is worse than no button.

---

## Feature 1 — cookie lifetime

### The flags, verified against `main.go`

```go
flagSet.Duration("cookie-expire",  time.Duration(168)*time.Hour, "expire timeframe for cookie")
flagSet.Duration("cookie-refresh", time.Duration(0),             "refresh the cookie after this duration; 0 to disable")
```

So today, passing neither, we run a **7-day cookie with no refresh and no revalidation**. That is the
weakest of the available configurations, which is what makes this worth doing.

### The sliding window — your model is right

Two pieces of `oauthproxy.go`. The age check marks the session for re-saving:

```go
if session != nil && sessionAge > p.CookieRefresh && p.CookieRefresh != time.Duration(0) {
    saveSession = true
}
```

and every save stamps a fresh absolute expiry — `MakeSessionCookie` → `makeCookie` computes
`Expires: now.Add(expiration)` with `expiration = p.CookieExpire`.

The cookie therefore dies at `last_save + cookie-expire`, and a save only happens on a request made
more than `cookie-refresh` after the previous one. An active user slides forward indefinitely. An idle
user is signed out **between `cookie-expire - cookie-refresh` and `cookie-expire`** of true inactivity:
worst case they went idle immediately after a save, best case just before the next one would have
fired. That is exactly the arithmetic you described.

### The part that is not obvious: refresh also REVALIDATES

The OpenShift provider does not override `RefreshSessionIfNeeded`, so the default runs and returns
`(false, nil)` — no OAuth refresh token is involved, and OpenShift issues none for this flow. But
`revalidated` therefore stays false, which opens the next block:

```go
if saveSession && !revalidated && session != nil && session.AccessToken != "" {
    if !p.provider.ValidateSessionState(session) {
        saveSession = false; session = nil; clearSession = true
    }
}
```

`ValidateSessionState` → `validateToken(p, s.AccessToken, nil)`, and the OpenShift provider sets

```go
defaults.ValidateURL = getKubeAPIURLWithPath("/apis/user.openshift.io/v1/users/~")
```

So every refresh interval costs one API call per active user and **re-checks that the token is still
good**. A revoked user loses access within `cookie-refresh` instead of keeping a valid cookie for the
rest of `cookie-expire`. That is a real security gain and the main argument for enabling refresh at
all.

### RISK — this could be broken, and it is the go/no-go for the feature

`validateToken` is called with a nil header, which takes this path:

```go
if len(header) == 0 {
    params := url.Values{"access_token": {access_token}}
    endpoint = endpoint + "?" + params.Encode()
}
...
if resp.StatusCode == 200 { return true }
return false
```

The bearer token goes in the **query string**, and only a 200 counts. The Kubernetes API server does
not generally accept credentials as a query parameter for REST calls. If it answers 401 here, then
every refresh clears the session, and `cookie-refresh` becomes a *forced logout* timer rather than a
sliding one.

I could not settle this from source — `api.RequestUnparsedResponse` may add a header, and the fork may
have patched it. **It is settled empirically on the lab before either default is chosen**, and it is
step 1 of the verification below. If it fails, the feature ships as `cookie-expire` only, with
`cookie-refresh` documented as unusable with `provider=openshift` and defaulted to `0`.

### Prerequisite the chart currently does not enforce

The proxy's own README: a properly sized cookie secret — **16, 24 or 32 bytes** — is required when
using `cookie-refresh` (or `pass-access-token`). Today nothing checks this.

- The generated path is safe: `oauth-secret.yaml` uses `randAlpha 32 | b64enc`, and the live secret
  measures 32 bytes.
- The **operator-supplied** path is not: `oauthProxy.cookieSecret` accepts any string. With refresh
  enabled, a 20-byte secret becomes a crash-looping proxy.

So this feature must add a `fail` in the template when refresh is on and a supplied secret is not one
of those three lengths — an install-time error with a readable message, rather than a pod that will not
start.

### One more interaction worth stating

`accessTokenMaxAgeSeconds` on the cluster's OAuth config defaults to **24 hours**. A `cookie-expire`
longer than that lets the proxy cookie outlive the token it represents. With refresh on, the stale
token is caught at the next interval; with refresh off, the cookie stays valid to its own expiry. The
default we ship should sit comfortably under 24h, and the values comment should name the cluster
setting so somebody tuning one knows about the other.

### Values shape

```yaml
oauthProxy:
  # Session lifetime. Sliding: any request more than `refresh` after the last one re-stamps the
  # cookie for a further `expire`, so an active reader is never interrupted and an idle one is
  # signed out after between (expire - refresh) and expire of inactivity.
  cookie:
    # -cookie-expire. Keep at or below the cluster's accessTokenMaxAgeSeconds (default 24h):
    #   oc get oauth cluster -o jsonpath='{.spec.tokenConfig.accessTokenMaxAgeSeconds}'
    expire: 8h
    # -cookie-refresh. Also the interval at which the proxy re-checks the token against
    # /apis/user.openshift.io/v1/users/~, so it bounds how long a revoked user keeps access.
    # Empty or 0 disables both the sliding behaviour and that re-check.
    refresh: 1h
```

`8h` / `1h` proposed: a workday-shaped session, idle logout between 7h and 8h, hourly revalidation,
and one API call per active user per hour. Both are overridable; neither is load-bearing for anything
else in the chart.

You asked for the default in `deployment.yaml` and the override in `values.yaml`. Helm's own model is
the reverse — `values.yaml` *is* the defaults file — so the plan honours the intent by putting the
documented values in `values.yaml` **and** a `| default` fallback in the template, so a hand-written
values file that omits the block still renders a sane flag instead of nothing:

```
- -cookie-expire={{ .Values.oauthProxy.cookie.expire | default "8h" }}
{{- with .Values.oauthProxy.cookie.refresh }}
- -cookie-refresh={{ . }}
{{- end }}
```

`refresh` is conditional so that setting it empty genuinely omits the flag rather than passing `0`,
which reads identically to the proxy but leaves a misleading line in `oc get pod -o yaml`.

---

## Feature 2 — the logout button

### API first

`/api/whoami` already exists and already reports identity from the proxy's headers, with the right
refusal built in — it returns `authenticated: false` when the proxy is disabled even if
`X-Forwarded-User` is present, because in that mode the caller supplied it. That is the natural home
for the logout URL, rather than a second endpoint.

```json
{ "user": "jane.smith", "email": "…", "authenticated": true, "logout_url": "/oauth/sign_out" }
```

`logout_url` is `null` whenever `authenticated` is false, so local development and a
`oauthProxy.enabled=false` install simply render no button — the page never offers to end a session
that does not exist.

The path is composed from a new config key rather than a literal, so it tracks `--proxy-prefix` if
that is ever set:

- chart: `oauthProxy.proxyPrefix: "/oauth"` → ConfigMap `oauthProxyPrefix`
- app: `Settings.oauth_proxy_prefix`, and `logout_url = f"{prefix}/sign_out"`

### The landing page

`-logout-url=https://<host>/signed-out`, with `/signed-out` added to `skipAuthRegex` so the proxy does
not immediately re-authenticate it. The page states what actually happened:

> Signed out of the dashboard. Your cluster session is separate and is still active, so signing in
> again may not ask for your password. To end that too, log out of the OpenShift console.

Serving it from our own app keeps the feature working on any cluster, without depending on the OAuth
server exposing a logout endpoint.

### UI

A button in the header beside the existing version/refresh controls, rendered only when
`logout_url` is present. It is a plain link — the fork's `SignOut` has no method check, so GET works.
A GET logout is drive-by triggerable (someone can end your session with an `<img>` tag); the
consequence is an unwanted logout rather than any data exposure, so a link is proportionate. If we
would rather not have that, a POST form is the alternative and costs little.

Must satisfy the tests already in the repo: WCAG 2.1 AA contrast in **both** themes, a real accessible
name, keyboard reachable, and the type scale honoured. The stylesheet is now `static/app.css`.

---

## Verification, in order

Step 1 is a gate. If it fails, the shape of feature 1 changes, so nothing else is built first.

1. **Does `cookie-refresh` work with `provider=openshift`?** Deploy with `refresh=1m`, `expire=3m`.
   Browse continuously for 3 minutes. Watch the sidecar: `oc logs deploy/group-sync-dashboard -c
   oauth-proxy -f`. Expect `refreshing … old session cookie` followed by a `200 GET
   …/apis/user.openshift.io/v1/users/~`. A 401 there, or a bounce to the login page, means the
   query-parameter path is rejected and refresh is unusable.
2. **Idle expiry.** Same settings, then leave it alone for 3 minutes: the next click must re-authenticate.
3. **Sliding.** Click every 30s for 5 minutes with `expire=3m`: must never re-authenticate. This is the
   test that distinguishes a sliding window from an absolute cap.
4. **Revocation is noticed.** With refresh on, `oc delete oauthaccesstokens <token>` for the test user
   mid-session; access must stop within one refresh interval.
5. **Logout.** Click it: cookie gone (`document.cookie`, and the `Set-Cookie` on the 302), land on
   `/signed-out` unauthenticated, and record whether returning to `/` re-authenticates silently — the
   answer goes in the docs either way.
6. **Logout does not revoke.** `oc get oauthaccesstokens | wc -l` before and after: expected unchanged,
   which is exactly why the page must not claim otherwise.
7. **Bad cookie secret is rejected at install**, not at runtime: `--set
   oauthProxy.cookieSecret=twentybytesexactly1 --set oauthProxy.cookie.refresh=1h` must fail the render.
8. Playwright for the button in both themes, plus the existing accessibility and type-scale suites.

## Tests to add

| area | test |
|---|---|
| chart | both flags render from values; `refresh: ""` omits the flag entirely; the `default` fallback renders when the block is absent |
| chart | a supplied `cookieSecret` of invalid length with refresh on fails the render, with the three valid lengths in the message |
| chart | `/signed-out` is inside the rendered `skipAuthRegex`, and `-logout-url` matches the ingress host |
| api | `whoami` carries `logout_url` when the proxy is enabled and `null` when it is not |
| api | `logout_url` follows `oauthProxyPrefix`, so a non-default prefix is not hardcoded away |
| ui | the button appears only when `logout_url` is present, and its `href` is that value |
| ui | contrast in both themes; accessible name; keyboard reachable |

## Open questions for you

1. **Defaults**: `8h` expire / `1h` refresh as proposed, or tighter (`30m` / `5m` gives idle logout in
   25–30 minutes, which some governance reviews want)? This changes behaviour for existing installs,
   which today get 7 days.
2. **Logout link as GET or POST form?** GET is simpler and matches the fork; POST removes drive-by logout.
3. Worth adding an optional `-logout-url` override so a cluster with an SSO logout endpoint can point at
   it and get true single sign-out? Cheap to add, and useless on a cluster without one.
