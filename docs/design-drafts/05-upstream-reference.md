# Upstream reference — what shipped OpenShift products actually do

Fetched verbatim, not paraphrased. This file exists so the design can be adapted from real code rather
than from reasoning about what the code probably says.

## 1. Kibana's oauth-proxy sidecar — `openshift/elasticsearch-operator`

`internal/kibana/reconciler.go`. A shipped Red Hat product running `provider=openshift`, which is the
same provider we run.

### The container args, verbatim

```go
"-provider=openshift",
fmt.Sprintf("-client-id=system:serviceaccount:%s:kibana", cluster.cluster.Namespace),
"-client-secret-file=/var/run/secrets/kubernetes.io/serviceaccount/token",
"-cookie-secret-file=/secret/session-secret",
fmt.Sprintf("-cookie-expire=%s", oauthTimeout),
"-skip-provider-button",
"-skip-auth-regex=^/api/status$",
"-upstream=http://localhost:5601",
"-scope=user:info user:check-access user:list-projects",
"--tls-cert=/secret/server-cert",
"-tls-key=/secret/server-key",
"-pass-access-token",
```

Three facts to carry over:

- **`-cookie-expire` is set. `-cookie-refresh` is NOT.** Not omitted by oversight — this is the shipped
  configuration of the product, and it matches our own measurement that refresh cannot work with
  `provider=openshift` (see §3).
- **`-pass-access-token` IS set.** A shipped Red Hat product forwards the user's access token to the
  application behind the proxy. That is the precedent for the console-style logout in §2.
- `-skip-provider-button` is set, as ours is.

### The cookie lifetime is DERIVED from cluster policy, verbatim

```go
const oauthTimeout = 24 * time.Hour

oauthConfig, err := getOAuthConfig(clusterRequest.client)
if err != nil {
    return kverrors.Wrap(err, "Failed to get oauth config")
}

cookieTimeout := oauthTimeout
if oauthConfig != nil && oauthConfig.Spec.TokenConfig.AccessTokenInactivityTimeout != nil {
    cookieTimeout = oauthConfig.Spec.TokenConfig.AccessTokenInactivityTimeout.Duration
}

kibanaPodSpec := newKibanaPodSpec(
    clusterRequest,
    fmt.Sprintf("%s.%s.svc", clusterName, clusterRequest.cluster.Namespace),
    proxyConfig,
    cookieTimeout,          // <- becomes the oauthTimeout parameter, hence -cookie-expire
    ...
)
```

and the read itself, which tolerates absence rather than failing:

```go
func getOAuthConfig(r client.Client) (*configv1.OAuth, error) {
    oauthNamespacedName := types.NamespacedName{Name: constants.OAuthName}
    oauthConfig := &configv1.OAuth{}
    if err := r.Get(context.TODO(), oauthNamespacedName, oauthConfig); err != nil {
        if !apierrors.IsNotFound(err) {
            return nil, kverrors.Wrap(err, "encountered unexpected error getting oauth", ...)
        }
    }
    return oauthConfig, nil
}
```

The pattern: **the proxy cookie must not outlive the cluster's declared inactivity policy.** When the
admin has expressed one, it wins; when they have not, fall back to a shipped default. Note it prefers
`AccessTokenInactivityTimeout`, NOT `AccessTokenMaxAgeSeconds`.

### The adaptation problem, which the operator does not have

Kibana is an **operator**: a live client, a reconcile loop, so it re-derives on every reconcile and
tracks a later change to the OAuth CR. We are a **Helm chart**, so:

- The read must be `lookup "config.openshift.io/v1" "OAuth" "" "cluster"`, which returns **empty** under
  `helm template` and client-side dry-runs — the same property `gsd.externalHost` already documents. So
  the derivation must degrade to the shipped default, and must **NOT** `fail` the render, unlike
  `ingress.host` where failing is correct.
- The value **freezes at install time**. An admin who sets `accessTokenInactivityTimeout` afterwards
  does not change our cookie until the next `helm upgrade`. Kibana has no such gap. This must be
  documented rather than glossed.
- `lookup` runs with the **installing identity's** credentials, not the dashboard ServiceAccount's — so
  the chart's existing `get` on `oauths/cluster` for the SA does not authorise it. A namespace-scoped
  installer may legitimately be unable to read it, which is another reason absence must be tolerated.

## 2. The console's logout — `openshift/console`

The console is the only OpenShift component that logs out properly, and it does not clear a cookie or
redirect: **it revokes the token.** From PR #6445, "Delete the hashed session token on user logout",
`pkg/server/server.go`:

- `DELETE /apis/oauth.openshift.io/v1/oauthaccesstokens/<name>`
- the object name is derived from the raw bearer token: strip the `sha256~` prefix, SHA-256 the
  remainder, base64-encode, re-attach the prefix (`tokenToObjectName`)
- performed with the **user's own** credentials, proxied through the console's k8s proxy

**Verified reproducible on our lab.** Deriving the name from `oc whoami -t` with
`"sha256~" + base64.urlsafe_b64encode(sha256(token[7:])).rstrip("=")` resolved a real object:

```
sha256~jk8zMpWbaAXZpHuaB…  ->  user=kubeadmin  client=openshift-challenging-client
                               expires=31536000s  scopes=["user:full"]
```

Permissions, measured with SARs: `delete oauthaccesstokens` is **yes** even for a plain LDAP user
(`--as=lateef.o`), which is how the console's logout works for everybody. `useroauthaccesstokens`
answered **no** for delete, so the plain resource is the one to use — as the console does. Because the
app would act as the USER, the chart needs **no new ServiceAccount grant**, so the standing rule that
this chart holds no write verb on anything it reports on is untouched.

Whether the API enforces ownership on that delete is NOT verified. It matters for wording, not for us.

## 3. Our own measurements, for the same design

| claim | measured |
|---|---|
| `-cookie-refresh` clears the session with `provider=openshift` | `validateToken` sends the token as a **query parameter**; the API server answered **403** and named the caller `system:anonymous`. Header form on the same URL: 200 as `kubeadmin`. |
| a dead proxy cookie silently re-issues | **FALSE here.** Cleared only `_oauth_proxy`, `ssn` present and 9 seconds old: the OAuth server **demanded credentials**. It keeps no reusable session for this client. `ssn` is a session cookie (`expires=-1`), host-scoped, `SameSite=Lax`, HttpOnly. |
| `POST /logout` ends the browser SSO session | **Not demonstrated.** It answers 200 with an **empty body** and no `Location`, and the `ssn` cookie was **unchanged** before and after a same-site `fetch(..., {method:'POST', mode:'no-cors', credentials:'include'})`. |
| the dashboard and OAuth hosts are same-site | Yes — both `*.apps-crc.testing`, shared registrable domain. |
| the cluster's token policy | `accessTokenMaxAgeSeconds: 31536000` (365 days); `accessTokenInactivityTimeout` **unset**. |
| `-logout-url` usage across the `openshift` org | Zero real uses. Only Ansible inventories and STIG test assertions. |

## 4. Ecosystem summary

| app | expire | refresh | pass-access-token | logout-url |
|---|---|---|---|---|
| Kibana (cluster logging, shipped) | 24h, or the cluster's `accessTokenInactivityTimeout` | **none** | yes | none |
| hypershift Grafana (`hack/`, CI only) | 24h | 1h | no | none |
| ODH GatewayConfig | 24h | 1h | ? | via an `oauth-logout-url` annotation |
| Console (not oauth-proxy) | own session | — | — | revokes the token; `logoutRedirect` for IdP SLO |

Kibana's own UI sign-out button has **no** proxy-level wiring in that manifest, so it ends Kibana's
session while the proxy cookie survives — the standard weakness of app-level logout behind a proxy, and
the thing our signed-out page must not pretend to have solved. (Inference from the manifest; not driven.)
