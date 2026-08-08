# Lens 1 — chart and oauth-proxy configuration

Implements the chart half of `docs/DESIGN_oauth_session_and_logout.md` with the operator's
decisions applied: 30m/5m defaults, GET logout, optional `-logout-url` override, a
render-time cookie-secret guard, and the `accessTokenMaxAgeSeconds` relationship made
visible. Every snippet below was applied to a scratch copy of the chart and rendered; every
guard was made to fire and to stand down; the new tests were run against both the patched
copy (22/22 pass) and the unpatched chart (14 fail, 8 boundary invariants pass); the
existing 44 chart tests all pass against the patched copy. Snippets are verbatim from that
verified copy.

## 0. Source verification done for this lens (extends the research, three additions)

Checked against `openshift/oauth-proxy` master (`main.go`, `options.go`), the same source
the research doc used. Three facts the research did not state, each load-bearing here:

1. **The proxy validates `cookie-refresh < cookie-expire` at startup** and refuses to run
   otherwise (`options.go`: `if o.CookieRefresh >= o.CookieExpire`). That is a
   crash-looping sidecar for a values typo, so the chart re-runs the same check at render
   time (guard §3 below).

2. **`-logout-url` has no validation and no absolute-URL requirement.** Its help text says
   "absolute URL", but `Validate()` never parses it, and `SignOut` (quoted in the research
   doc) hands it untouched to `http.Redirect`, which accepts a path. So the default can be
   the **relative** `/signed-out`, which removes the render-time hostname problem entirely
   (§5). Lab step: confirm the 302's `Location` header once, alongside the existing
   verification plan — the fallback if it somehow fails is one line (§5).

3. **The proxy's cookie-secret arithmetic is stranger than "16/24/32 bytes of input", and
   the research doc's proposed test vector is wrong because of it.** Verbatim from
   `options.go`:

   ```go
   func secretBytes(secret string) []byte {
       b, err := base64.URLEncoding.DecodeString(addPadding(secret))
       if err == nil {
           return []byte(addPadding(string(b)))
       }
       return []byte(secret)
   }
   ```

   A value that parses as URL-safe base64 (padding tolerated) is decoded, and the
   **decoded length is then padded up to a multiple of four**. Two measured consequences:

   * `"0123456789abcdef0123456789abcdef"` (32 raw chars) decodes to **24** bytes — valid,
     but not for the reason a naive `len` check would say.
   * `"twentybytesexactly1"` — the research doc's step-7 "must fail the render" vector —
     is **accepted by the proxy**: padded to 20 chars, decoded to 14 bytes, padded to
     16 — a valid AES key length. A guard using naive `len` would reject a working config
     (spurious install failure) and, in the other direction, pass a 44-char standard-base64
     value containing `+` that the proxy counts as 44 raw bytes and refuses.

   So the guard mirrors `secretBytes` exactly (helper in §2), and the honest invalid test
   vector is `"not-a-valid-secret??"` — 20 bytes that cannot parse as base64.

## 1. values.yaml — the stanza

**File:** `charts/group-sync-dashboard/values.yaml`
**Anchor:** inside the `oauthProxy:` block — the new `cookie:` block goes immediately after
the `cookieSecret: ""` line (lifetime sits next to the key that signs it); the
`skipAuthRegex` comment+value **replace** the existing four-line comment and value;
`logoutUrl` and `proxyPrefix` follow directly after `skipAuthRegex`, before `sar`.

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
  # start a fresh login the moment it loads, so the logout button would undo itself.
  skipAuthRegex: "^/(healthz|readyz|metrics|signed-out)$"

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

Notes on the shape:

* **30m/5m** per the operator's decision. Idle sign-out lands between 25m and 30m of true
  inactivity; revalidation (and therefore revocation latency) is 5m; cost is one
  `users/~` API call per active user per 5m.
* `proxyPrefix` is the research doc's own proposal ("chart: `oauthProxy.proxyPrefix` →
  ConfigMap `oauthProxyPrefix`"), taken to its conclusion: the value feeds the
  `-proxy-prefix` flag, the ServiceAccount redirect URI and the ConfigMap **together**
  (§4, §6), because a key that only fed the ConfigMap would *create* the drift it exists
  to prevent. The flag's default in the fork is `/oauth` (`main.go:71`), so rendering it
  explicitly changes nothing on a default install.
* House rule kept: all comments are `#`, mechanism-first, and none contains a `{{ }}`
  expression (a `#` comment is YAML, not Helm — Helm would still evaluate it).

## 2. _helpers.tpl — shared resolvers, so flags / ConfigMap / guards cannot disagree

**File:** `charts/group-sync-dashboard/templates/_helpers.tpl`
**Anchor:** appended at end of file, after the `gsd.accessMode` define.

The single most important design decision in this lens: the expire/refresh values are
resolved **once**, in named helpers, and everything else — the container args, the guards,
the ConfigMap the app models the countdown from, NOTES.txt — includes those helpers. The
countdown's truthfulness (the second hard constraint in the task) starts here: the numbers
the page uses ARE the numbers the proxy enforces, by construction, not by convention.

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
# so the ConfigMap can hand the app plain seconds instead of a format to re-parse.
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

Mechanics worth knowing (all measured under `helm template`):

* `dig` returns its default only for a **missing** key, so `oauthProxy.cookie: null` in a
  hand-written values file still yields 30m/5m (measured), while an explicit
  `refresh: ""` disables refresh — the two intents stay distinguishable.
* Sprig's `b64dec` does not error on bad input; it returns the error text as the string.
  The `contains "illegal base64"` sentinel is how decode failure is detected. (A secret
  whose *decoded bytes* contain that text would be misjudged as undecodable and counted
  raw; constructing one requires deliberately base64-encoding that sentence, so the
  divergence is theoretical.)
* Sprig's `b64dec` is StdEncoding and demands padding (measured: unpadded input fails),
  while the proxy uses URLEncoding with padding repair — hence the `-`→`+`, `_`→`/`
  replacement and the computed `=` padding. The `+`/`/` pre-check preserves the proxy's
  fallback: values containing those characters fail *its* URL-safe decode and count raw.
* `gsd.durationSeconds` emits integers as integers (1800, not 1800.0 — measured in the
  rendered ConfigMap) and floats only for sub-second durations, which no sane config uses.

## 3. deployment.yaml — guards and args

**File:** `charts/group-sync-dashboard/templates/deployment.yaml`

### 3a. Render-time guards

**Anchor:** immediately after the third existing guard's `{{- end }}` (the
`strategy=RollingUpdate is unsafe…` fail), before `apiVersion: apps/v1`. This is the
chart's established home for cross-value guards, and the whole block is inside
`.Values.oauthProxy.enabled` so a proxy-less render can never trip over cookie values it
does not use (measured: `enabled=false` with `expire=8hr` renders fine and emits no flag).

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

The skipAuthRegex guard is a substring check, deliberately: it cannot evaluate the regex
the way the proxy will, so it only refuses the configuration that is *certainly* broken —
default logout target with no mention of the page in the skip list. Whether the regex
actually admits `/signed-out` is asserted properly in the tests (§7), which `re.search` the
rendered value. An operator who sets `logoutUrl` to an external endpoint is exempt: the
chart-served page is then unused (tested both ways).

### 3b. The proxy args

**Anchor:** in the `oauth-proxy` container's `args`, between
`- -cookie-secret-file=/etc/proxy/secrets/session_secret` and
`- -openshift-service-account=…`.

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

Measured renders: defaults → `-cookie-expire=30m` / `-cookie-refresh=5m` /
`-proxy-prefix=/oauth` / `-logout-url=/signed-out`; `refresh=""` and `refresh=0` → no
`-cookie-refresh` line at all; `cookie: null` → the 30m/5m defaults.

## 4. The cookie-secret guard — where and why

**File:** `charts/group-sync-dashboard/templates/oauth-secret.yaml` — complete post-change
file (the edits interleave with the existing lookup logic, so the whole file is the
snippet):

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

(The pre-existing `{{- /* */ -}}` block at the top is untouched per the standing
instruction not to retro-convert old comments; the new comment is `#`.)

**Where the guard belongs, judged against the alternatives:**

* **`oauth-secret.yaml` (chosen).** The value being validated is consumed here (`b64enc`,
  three lines lower), and the *second* thing worth validating — the looked-up existing
  secret — only exists here. Guard-next-to-consumption is also this chart's precedent
  (deployment.yaml validates what deployment.yaml renders). The length check itself lives
  in `_helpers.tpl` (`gsd.cookieSecretBytes`) because it is arithmetic, not policy.
* **`values.schema.json` — no** (full reasoning in §4a). The check is conditional on
  another value (`refresh`), depends on base64 arithmetic JSON Schema cannot express, and
  its failure message needs a paragraph, not a schema path.
* **`NOTES.txt` — no.** NOTES render *after* a successful install; a warning there arrives
  when the sidecar is already crash-looping.
* **Dry-run safety, stated explicitly:** the values-supplied branch reads only `.Values`,
  so it behaves identically connected or not — deterministic, and *should* fail a GitOps
  render, because the config is wrong. The looked-up branch depends on `lookup`, which is
  empty under `helm template`/client dry-run, so it can never fire spuriously on a
  disconnected render; it exists for the one hole the values check cannot see — a bad
  secret supplied in the past and since removed from values, which would otherwise
  crash-loop the moment refresh is enabled. Both cases fire at install/upgrade time with a
  message, never as a broken pod.

Condition scope: the proxy needs the AES-sized secret when `cookie-refresh != 0` **or**
`pass-access-token` is set. This chart never sets `pass-access-token`, so the guard keys on
refresh alone; if that flag is ever added, the `$refreshOn` condition must widen with it
(the values comment in §1 does not mention pass-access-token for the same reason).

## 4a. values.schema.json — considered and rejected for this change

Helm's position is that a schema is an *optional* layer for type/shape validation, and the
docs' own guidance for constraint failures with prose reasons is `fail`/`required` in
templates. Three specifics decide it here:

1. **The constraints are relational, not shapes.** `refresh < expire`;
   `secret length ∈ {16,24,32} only when refresh ≠ 0, measured after the proxy's own
   base64 arithmetic`. JSON Schema can express conditionality (`if`/`then`) but not the
   base64 arithmetic, so the schema could only carry a *weaker* duplicate of the template
   guard — two sources of truth, one of them wrong in the corners that matter (§0.3).
2. **Error quality is the deliverable.** This chart's guards are paragraphs that name the
   failure, the mechanism and the fix, and the test suite asserts on their text (five
   existing `assert "…" in out` tests). Schema violations surface as terse JSON-pointer
   errors and cannot be tested the same way.
3. **A partial schema is worse than none.** Shipping one that validates only
   `oauthProxy.cookie` implies the rest of a 1000-line values.yaml is validated when it is
   not, and every future key addition acquires a second file to keep in sync. If the chart
   ever adopts a schema it should cover the whole values surface as its own piece of work
   — at which point the duration *format* checks (but not the relational ones) could move
   into it.

The duration-format validation the schema would have provided lives in the §3a guards
instead (`not a Go duration…`), which fire under plain `helm template` with no cluster —
verified: `expire=8hr`, `expire=30` (bare number) and `refresh="5 minutes"` all refuse the
render; every currently-valid values file is untouched (the full existing chart test suite
passes against the patched copy).

## 5. `/signed-out`, skipAuthRegex, and how the logout-url default is composed

The default in values.yaml changes to `^/(healthz|readyz|metrics|signed-out)$` (§1), and
`-logout-url` defaults to the **relative** path `/signed-out` (§3b).

**Why relative is the right composition — the GitOps question dissolved.** The task asks
how to compose the logout URL without breaking `helm template` given that
`gsd.externalHost` fails a disconnected render when `ingress.host` is unset. Verified
answer (§0.2): the flag needs no host at all. The proxy passes the value to
`http.Redirect`; the browser resolves `Location: /signed-out` against the host it is
already on. So the default breaks nothing for GitOps *and* is more robust than a composed
absolute URL — it survives an `ingress.host` change without a re-render of the flag.
For completeness: even if an absolute URL had been required, composing it from
`gsd.externalHost` would have added **no new** GitOps constraint, because
`serviceaccount.yaml` already calls that helper for the redirect URI on every
proxy-enabled render — `ingress.host` is already mandatory for GitOps users of this
chart. That is the fallback if the lab's 302 check surprises us: change one line to
`- -logout-url={{ .Values.oauthProxy.logoutUrl | default (printf "https://%s/signed-out" (include "gsd.externalHost" .)) }}`
and nothing else.

**The override.** `oauthProxy.logoutUrl` set to a cluster's real SSO logout endpoint
replaces the default entirely; the chart-served page goes unused, and the skipAuthRegex
guard stands down for that configuration (§3a). The proxy's own session cookie is still
cleared first — `SignOut` clears before redirecting — so the override composes correctly
with a wider single sign-out.

**What must not regress:** the guard in §3a catches the regex/`logoutUrl` mismatch, and a
test (§7) `re.search`es the rendered regex against `/signed-out`, `/healthz`, `/readyz`,
`/metrics` (all must match) and `/api/version` (must not) — so neither the landing page
nor the probe paths can silently fall out, and the skip list cannot silently widen.

The `/signed-out` route itself, its content (including the "your cluster session is still
active" honesty requirement), and the CSP/theme constraints are lens 2/3 deliverables; the
chart's contract is only: *unauthenticated at that exact path, on the same origin*.

## 6. configmap.yaml and serviceaccount.yaml — the app's model inputs

**File:** `charts/group-sync-dashboard/templates/configmap.yaml`
**Anchor:** immediately after the `oauthProxyEnabled: {{ .Values.oauthProxy.enabled }}`
line (and its existing comment) inside the `clusters.yaml: |` block.

```
    # The proxy's session shape, in plain seconds. The session cookie is HttpOnly, so
    # neither the page nor the app can read its expiry — the page MODELS the deadline from
    # these numbers instead, and warns before it. They come through the same helpers as the
    # proxy's own flags, so the model and the enforcement cannot disagree. Refresh 0 means
    # disabled, and the expiry is then absolute from sign-in rather than sliding.
    sessionCookieExpireSeconds: {{ include "gsd.durationSeconds" (include "gsd.cookieExpire" .) }}
    sessionCookieRefreshSeconds: {{ include "gsd.durationSeconds" (include "gsd.cookieRefresh" . | default "0") }}
    # The app composes its logout link as <prefix>/sign_out, so a re-nested proxy moves the
    # link with it instead of leaving a hardcoded /oauth behind.
    oauthProxyPrefix: {{ .Values.oauthProxy.proxyPrefix | quote }}
```

Rendered with defaults (measured): `sessionCookieExpireSeconds: 1800`,
`sessionCookieRefreshSeconds: 300`, `oauthProxyPrefix: "/oauth"`. With `refresh: ""`:
`sessionCookieRefreshSeconds: 0`.

**File:** `charts/group-sync-dashboard/templates/serviceaccount.yaml`
**Anchor:** the `serviceaccounts.openshift.io/oauth-redirecturi.primary` line (replaced):

```
    # The path segment tracks oauthProxy.proxyPrefix: the proxy registers its callback
    # under that prefix, so a re-nested proxy moves this URI with it.
    serviceaccounts.openshift.io/oauth-redirecturi.primary: 'https://{{ include "gsd.externalHost" . }}{{ .Values.oauthProxy.proxyPrefix }}/callback'
```

Default render is byte-identical to today's (`…/oauth/callback`, measured), so no OAuth
client re-registration happens on upgrade.

**Interface contract for lenses 2 and 3** (stated here because the chart is the source):

| key | meaning | values |
|---|---|---|
| `sessionCookieExpireSeconds` | proxy `-cookie-expire`, in seconds | int > 0 always |
| `sessionCookieRefreshSeconds` | proxy `-cookie-refresh`, in seconds | int ≥ 0; **0 = disabled**, expiry is then absolute from sign-in |
| `oauthProxyPrefix` | proxy URL root; logout link is `<prefix>/sign_out` | default `/oauth` |

Plus: `/signed-out` is unauthenticated on the same origin, and the existing
`oauthProxyEnabled` key still gates whether any of this is live. The countdown model, its
drift handling, and the idle gating of the 30-second poll (the finding that makes the
30-minute timeout real) are lens 2/3 work **but the chart's share is delivered here**: the
model's inputs are the enforcement's inputs, one helper, zero drift; and the
`checksum/config` pod annotation already in deployment.yaml means changing the values
rolls the pod, so a stale model cannot outlive an upgrade. Note for lens 3's model: the
proxy re-stamps on ANY authenticated request through it, so the page's "last re-stamp"
estimate should be pegged to its own last completed authenticated fetch — which the page
controls once idle gating exists.

## 7. Chart tests — appended to `local-development/tests/test_chart_strategy.py`

That file is the right home and the only right home: its own docstrings record that
`.github/workflows/ci.yml` points the `chart` job at this file **by name**, and it already
owns the `render()` helper these reuse. **Anchor:** the two module-level helpers go after
the existing `render()` function; the three classes append at end of file, after
`TestTheProxyTrustsTheSameCAsTheApp`.

Verified: against the patched chart copy all 22 pass alongside all 44 existing tests;
against the unpatched chart 14 fail (every added behaviour has a failing-before test) and
8 pass-before — those 8 are deliberate boundary invariants (guards standing down, the
generated-secret path staying untouched, proxy-off rendering, the proxy-parity acceptance
vectors) which by construction cannot fail before the guards exist.

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

    def test_the_configmap_carries_the_same_numbers_as_the_flags(self):
        """The session cookie is HttpOnly, so the page cannot read its expiry — it models
        the deadline from these keys. If they drift from the flags, the model lies."""
        ok, out = render(oauthProxy__cookie__expire="1h30m", oauthProxy__cookie__refresh="90s")
        assert ok, out
        args = _proxy_args(out)
        assert "-cookie-expire=1h30m" in args and "-cookie-refresh=90s" in args
        cfg = _config_data(out)
        assert cfg["sessionCookieExpireSeconds"] == 5400
        assert cfg["sessionCookieRefreshSeconds"] == 90

    def test_disabled_refresh_reaches_the_app_as_zero(self):
        ok, out = render(oauthProxy__cookie__refresh="")
        assert ok, out
        assert _config_data(out)["sessionCookieRefreshSeconds"] == 0

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

    def test_signed_out_is_inside_the_default_skip_auth_regex(self):
        """Asserted by MATCHING the rendered regex, not by eyeballing the default — an
        override that anchors differently would pass a substring check and still bounce
        the landing page into a login."""
        ok, out = render()
        assert ok, out
        args = _proxy_args(out)
        regex = next(a for a in args if a.startswith("-skip-auth-regex=")).split("=", 1)[1]
        assert re.search(regex, "/signed-out"), f"{regex!r} does not admit /signed-out"
        for path in ("/healthz", "/readyz", "/metrics"):
            assert re.search(regex, path), f"{regex!r} lost {path} — kubelet gets a 302"
        assert not re.search(regex, "/api/version"), f"{regex!r} is wider than intended"

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

One more import is needed at the top of the file: `import re` joins the existing
`import pathlib` / `import shutil` / `import subprocess` block (alphabetical:
between `pathlib` and `shutil`).

Adjacent one-word fix, same commit: the docstring of
`test_docs_are_published_under_api` in `local-development/tests/test_api_contract.py`
says "oauthProxy.skipAuthRegex admits only the three probe paths" — with `/signed-out`
added that sentence should read "admits only the probe paths and the signed-out landing
page". It asserts nothing about the regex, so only the sentence changes.

## 8. accessTokenMaxAgeSeconds, NOTES.txt, README, Chart.yaml

### The token-lifetime relationship — documented in three places, warned in one

The facts (from the research doc): the cluster's `accessTokenMaxAgeSeconds` defaults to
24h; a `cookie-expire` above it makes the proxy cookie outlive the token. With refresh on,
the dead token fails the next revalidation and the user is signed out early — harmless
but pointless. With refresh off it is a real governance gap: nothing ever rechecks the
token, and note the dashboard's own API calls use the pod's ServiceAccount, not the user's
token, so nothing *breaks* to reveal it. At the shipped 30m default the situation is
unreachable; it matters for operators who raise expire towards workday lengths.

Where it lives:

1. **values.yaml comment** (§1) — the contract, with the `oc get oauth` one-liner. This is
   the copy an operator tuning `expire` will actually be looking at.
2. **Chart README row** (below) — one clause.
3. **NOTES.txt** — a best-effort warning, because it is the only chart artifact rendered
   at real install time with cluster access, where `lookup` works. It cannot be a `fail`:
   the OAuth CR is cluster-scoped and often unreadable by a namespace-scoped installer,
   and `lookup` is empty for every disconnected render — a guard would go silent exactly
   where it is needed most and could never be relied on. A NOTES warning degrades
   honestly: readable CR → warning when applicable; anything else → the values comment
   still stands.

**File:** `charts/group-sync-dashboard/templates/NOTES.txt`
**Anchor:** immediately after the `Authentication: OpenShift OAuth…` two-line sentence
inside the `{{- if .Values.oauthProxy.enabled }}` branch:

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

All four branches were exercised by stubbing the lookup with a dict (expire 30m vs maxAge
600s, refresh on and off; maxAge 86400 → no warning; disconnected → no warning). The
explicit `| default 86400` also covers a CR that sets the field to `0`, which OpenShift
documents as "use the default 24h".

### Chart README — rows for the Authentication table

**File:** `charts/group-sync-dashboard/README.md`
**Anchor:** the Authentication values table; the new rows go after the
`oauthProxy.cookieSecret` row, and the existing `oauthProxy.skipAuthRegex` row's default
cell is updated in place. (Pipes inside cells are escaped `\|`, matching the existing
skipAuthRegex row.)

```markdown
| `oauthProxy.cookie.expire` | `30m` | session cookie lifetime, a Go duration. Sliding when refresh is on: idle sign-out lands between `expire - refresh` and `expire` of inactivity. Keep at or below the cluster's `accessTokenMaxAgeSeconds` (default 24h) or the cookie outlives the token it represents |
| `oauthProxy.cookie.refresh` | `5m` | re-stamp the cookie on the first request older than this, **and revalidate the token against the cluster** — it bounds how long a revoked user keeps access. Empty or `0` disables both; must be less than `expire`, enforced at render time |
| `oauthProxy.skipAuthRegex` | `^/(healthz\|readyz\|metrics\|signed-out)$` | the health paths **must** stay, or kubelet gets a 302 and kills a healthy pod; `/signed-out` must stay while `logoutUrl` is empty, or the logout button signs the user straight back in — also enforced at render time |
| `oauthProxy.logoutUrl` | `""` | where the browser lands after sign-out. Empty = the dashboard's own unauthenticated `/signed-out` page, which says plainly that the cluster's OAuth session is still alive. Set an absolute URL to an SSO logout endpoint for true single sign-out |
| `oauthProxy.proxyPrefix` | `/oauth` | URL root for the proxy's own endpoints (`/oauth/callback`, `/oauth/sign_out`). One key feeds the flag, the ServiceAccount redirect URI and the app's logout link, so they cannot drift |
```

The README's prose "Authentication" note (and the repo README, lens 2's territory) should
gain one sentence on session shape; suggested: *"Sessions idle out after 30 minutes by
default (`oauthProxy.cookie.*`), and the header shows a countdown warning before that
happens."* Also worth noting for the reviewer: the README still carries a
`oauthProxy.redirectMode` row marked "currently inert" while values.yaml says the key was
removed — pre-existing staleness, not touched by this change, flagged here so it is not
mistaken for new drift.

### Chart.yaml — version

**File:** `charts/group-sync-dashboard/Chart.yaml` — `version: 0.1.0` → `version: 0.2.0`.

How versioning is actually handled here, checked before asserting: the chart landed in a
single commit and `version` has never moved since; there is no chart-museum publishing in
the repo, so nothing *consumes* the number yet. But Chart.yaml's own header states the
policy — "version — the CHART version, bumped when templates or defaults change" — and
this change does both (new values keys, new flags, changed skipAuthRegex default, new
guards). Minor bump, not patch, because behaviour changes for existing installs: a 7-day
no-refresh cookie becomes 30m/5m on upgrade, which is the entire point but deserves the
version signal. `appVersion` stays untouched by this lens (it tracks the application; the
lens-2 app changes decide it).

## 9. The go/no-go: exactly what changes if the lab shows refresh broken

The research doc's step-1 gate: `cookie-refresh` may be unusable with
`provider=openshift` because `validateToken` sends the token as a query parameter and
accepts only HTTP 200. If the lab test fails, this design loses **one default and gains
one warning; nothing else moves**:

1. `values.yaml`: `refresh: 5m` → `refresh: ""`, and the comment block gains its closing
   fact — suggested wording: `# refresh is DISABLED by default: with provider=openshift
   the revalidation sends the token as a query parameter, which this cluster's API server
   rejects, turning every refresh into a forced logout. See
   docs/DESIGN_oauth_session_and_logout.md before enabling.` The 30m expire stays and
   becomes an absolute (login+30m) timeout instead of an idle one.
2. `NOTES.txt` already has the refresh-off wording (built §8, tested) — no change.
3. Tests: two default-expectation tests flip their assertions
   (`test_defaults_render_the_thirty_minute_sliding_window` asserts no `-cookie-refresh`
   flag; a defaults call of `test_disabled_refresh_reaches_the_app_as_zero` replaces the
   `--set`). Every guard, helper, the secret-length check (still correct for any operator
   who enables refresh anyway, or for `pass-access-token` futures), the logout wiring,
   the ConfigMap keys and the omission logic are used *unchanged* — the machinery is
   identical whether refresh defaults on or off, which is precisely why the "empty omits
   the flag" path got first-class treatment and tests.
4. Lens 2/3 already receive `sessionCookieRefreshSeconds: 0` through the contract in §6
   and must handle it regardless (any operator can set `refresh: ""` today), so the
   countdown model needs no redesign either — with refresh=0 its deadline is absolute
   from sign-in rather than sliding.

## 10. Verification record (commands run for this lens)

* Flags verified in `openshift/oauth-proxy` master `main.go`: `-cookie-expire`,
  `-cookie-refresh`, `-logout-url` (no validation; help text overstates), `-proxy-prefix`
  (default `/oauth`), `-cookie-httponly` default true (the countdown constraint).
  `options.go`: `secretBytes`/`addPadding` quoted verbatim in §0; `CookieRefresh >=
  CookieExpire` refusal.
* Sprig behaviour measured under `helm template`: `b64dec` returns error text on invalid
  input rather than failing; demands padding; `len` counts bytes; `dig` default only for
  missing keys (nulled parent included).
* Full matrix rendered against a patched scratch copy of this chart: defaults, `refresh=""`,
  `refresh=0`, `cookie=null`, `refresh>=expire` (fails), `8hr`/`30`/`5 minutes` (fail),
  five secret vectors incl. both proxy-parity directions, regex-drop with and without
  `logoutUrl`, `enabled=false` with bad values (renders), `proxyPrefix=/auth` end-to-end,
  NOTES branches via stubbed lookup.
* Test runs: existing `test_chart_strategy.py` = 44 passed against the patched copy; the
  §7 tests = 22 passed against it, 14 failed against the unpatched chart (8 boundary
  invariants pass by construction).
