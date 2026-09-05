# Calling the API from outside the cluster

`/api` can be read with `curl`, Postman, or any HTTP client, using an ordinary account's
credentials — no `oc`, no kubeconfig, no port-forward. That is what makes an external
aggregator possible: each cluster publishes its own dashboard at a predictable hostname, so a
reporting service reads them and composes, rather than hosting or storing anything.

```
https://group-sync-dashboard.apps.<cluster>.<company-domain>/api
```

Two things have to be true first.

## 1. It is on by default since chart 0.14.0

`oauthProxy.apiTokenAccess.enabled` defaults to `true`: a default install already adds
`-openshift-delegate-urls` for the `/api` prefix and binds `system:auth-delegator` to the
**proxy's** ServiceAccount — the proxy is the party that calls TokenReview and
SubjectAccessReview. Callers do not need that role. The switch grants nothing on its own: a
bearer token reaches `/api` only after the proxy's SubjectAccessReview against the cluster-wide
read named in `delegateUrls` succeeds. The application then repeats that same check as
`visibility.adminSar`, so a token the proxy admitted normally lands on the wide cluster-data view;
the two exceptions are the same as for a cookie session — an indeterminate app-side review
fail-closes to the self view, and the Usage tab asks its own stricter review
(`visibility.usageAdminSar`, `update clusterrolebindings` by default), so a `cluster-reader` token
is wide on the cluster data and self on `/api/dashboard/activity`. A token that fails the proxy's
review never reaches the application. For cookie sessions only:

```bash
helm upgrade group-sync-dashboard charts/group-sync-dashboard \
  -n group-sync-dashboard -f my-values.yaml \
  --set oauthProxy.apiTokenAccess.enabled=false
```

With it off, the proxy only understands browser cookies and a perfectly valid bearer token gets a
`403` whose body is the login page.

### What the caller must be allowed to do, and why it is not `list groups`

The review demands **cluster-wide RBAC read** (`list clusterrolebindings`). An earlier version
demanded `list groups`, justified as "you could read this with `oc get groups` anyway". That was
wrong, and measurably so. An account granted only `list groups`:

```
oc list clusterrolebindings        ->  no
oc list rolebindings -A           ->  no
GET /api/.../bindings/findings    ->  229 bindings, including
                                      app-ocp-rbac-alpha-cluster-admin-crb
```

`/api` is not a group-membership API. It reports the cluster's whole RBAC binding surface —
every ClusterRoleBinding and RoleBinding, the role each grants, and which subjects hold it.
Gating that on `list groups` let an identity learn through the dashboard what it could not
learn with `oc`. If you narrow the review, narrow what `/api` returns first.

### Granting a reporting account

Through your normal RBAC process, not through this chart. An earlier version had an
`apiTokenAccess.readers` value that created the grant from the chart; it was removed, because
with the correct review the required permission is cluster-wide RBAC read, and a Helm value
that hands that out lets anyone who can edit a values file grant themselves that read. A chart
value is the wrong control for a cluster-level privilege.

The stock role already exists:

```bash
# prefer the group form — revoked by the directory when someone leaves
oc adm policy add-cluster-role-to-group cluster-reader <ldap-group-for-reporting>

# or a service account the aggregator runs as
oc adm policy add-cluster-role-to-user cluster-reader \
  system:serviceaccount:<namespace>:<name>
```

For a ServiceAccount use exactly that user form. The dashboard's repeated review sends the identity
with the OAuth virtual groups only, not `system:serviceaccounts:<namespace>`, so a grant made to the
ServiceAccount's namespace group passes the proxy and still lands on the self view inside the
application (recorded in `docs/REVIEW_chart_defaults.md`; carrying ServiceAccount virtual groups is
routed to `docs/specs/SPEC_D2_per_cluster_authorization.md`, which owns the tier resolver).

```bash
```

Verified after tightening: an identity that cannot list ClusterRoleBindings gets `403`, one
that can gets `200`, and an unauthenticated request gets `403`.

## 2. Get a token

A short-lived token, from the destination cluster's own OAuth server. This is the same
sequence `oc login -u -p` performs — it was derived by capturing
`oc login --loglevel=8` — so it is PKCE authorization-code, not the older implicit flow.

### curl

```bash
OAUTH=https://oauth-openshift.apps.<cluster>.<company-domain>
DASH=https://group-sync-dashboard.apps.<cluster>.<company-domain>

# PKCE: a random verifier, and its SHA-256 as the challenge (base64url, unpadded)
VERIFIER=$(python3 -c 'import secrets;print(secrets.token_urlsafe(64))')
CHALLENGE=$(python3 -c "
import base64,hashlib,sys
print(base64.urlsafe_b64encode(hashlib.sha256('$VERIFIER'.encode()).digest()).decode().rstrip('='))")

# 1. authorize -> a 302 whose Location carries ?code=
#    -i to see the header, and NO -L: following the redirect loses it
CODE=$(curl -sk -i -u "<user>:<password>" -H 'X-Csrf-Token: 1' \
  "$OAUTH/oauth/authorize?client_id=openshift-challenging-client\
&code_challenge=$CHALLENGE&code_challenge_method=S256\
&redirect_uri=$OAUTH/oauth/token/implicit&response_type=code" \
  | grep -i '^location:' | sed -n 's/.*[?&]code=\([^&]*\).*/\1/p' | tr -d '\r')

# 2. exchange the code for the token
TOKEN=$(curl -sk -X POST "$OAUTH/oauth/token" \
  -u 'openshift-challenging-client:' \
  -d grant_type=authorization_code -d "code=$CODE" \
  -d "code_verifier=$VERIFIER" -d client_id=openshift-challenging-client \
  -d "redirect_uri=$OAUTH/oauth/token/implicit" \
  | python3 -c 'import json,sys;print(json.load(sys.stdin)["access_token"])')

# 3. read the API
curl -sk -H "Authorization: Bearer $TOKEN" "$DASH/api/clusters"
```

### Postman

It works, but **two Postman defaults will break it** and neither failure is self-explanatory.

**Turn off "Automatically follow redirects."** Settings → General. The authorization code
arrives in the `Location` header of a 302. With redirects on, Postman follows it, lands on
`/oauth/token/implicit?code=…` with a 200, and the code is buried in the final URL rather than
in a header you were reading. Measured — it is recoverable from the address, but nothing about
the response looks like a failure, so this is the one that wastes an afternoon.

**Turn off "SSL certificate verification"** (or add the cluster's CA). The Route is served
with the cluster's own certificate, which a laptop does not trust.

Then:

| Request | Setup |
|---|---|
| `GET {{oauth}}/oauth/authorize` | Params as in the curl above. Auth tab → Basic, your username and password. Headers → `X-Csrf-Token: 1`. Read `code` from the response's `Location` header |
| `POST {{oauth}}/oauth/token` | Auth tab → Basic, username `openshift-challenging-client`, password empty. Body → x-www-form-urlencoded: `grant_type=authorization_code`, `code`, `code_verifier`, `client_id`, `redirect_uri` |
| `GET {{dashboard}}/api/clusters` | Auth tab → Bearer, the `access_token` from step 2 |

On `X-Csrf-Token`: it decides whether the server issues a basic-auth *challenge*. Measured —
with no credentials and no header the reply is a bare `401`; with the header it is `401` plus
`WWW-Authenticate: Basic realm="openshift"`. Postman's Basic Auth sends credentials
preemptively, so it would work without the header. Send it anyway: the OpenShift docs require
it, and a cluster that enforces it fails with a `401` that gives no hint why.

### The script does all of this

```bash
read -rs GSD_PASSWORD && export GSD_PASSWORD
./cluster-report.py --clusters prod,staging,dev --domain example.com --ldap-user svc-reporter
```

One token exchange per cluster, because an OpenShift token is issued by one cluster's OAuth
server and is meaningless to any other. The password is read from the environment and there is
no `--password` flag: an argument is visible in `ps` to every user on the host and lands in
shell history.

## What the UI keeps

The prefix map covers `/api` only, so `/` stays browser-only. A bearer token against the UI
root still returns `403`, by design — the token path exists for machines, and the HTML is not
an API.

## What the endpoints are

`/api` renders the schema (Swagger UI), `/api/redoc` the reference, `/api/openapi.json` the
spec itself for codegen. Those are behind the same authentication as the data, deliberately: a
document naming every endpoint and field is a map of the cluster's RBAC surface.

Rules for adding an endpoint: [`api-contract.md`](api-contract.md).
