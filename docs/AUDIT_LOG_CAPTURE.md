# Audit-log login capture — how it works, and how to see it working

How the dashboard learns who logged in to a cluster it does not run on. The design and the
measurements behind it are in `docs/specs/SPEC_D1_audit_log_login_capture.md`; this is the
operational picture, with the mock cluster as a worked example you can run yourself.

This is the only capture source. The oauth-server pod-log reader, which needed `spec.logLevel: Debug`,
was removed in chart 0.58.0 / application 0.36.0 (#321); `docs/DESIGN_login_capture.md` keeps its
as-built record. `docs/LOGIN_CAPTURE_QUICKCHECK.md` is the short check that this source is working.

## 1. Nothing is shipped to the dashboard

There is no agent on the observed cluster, no log forwarder, and no second network path. The
dashboard **pulls**, through the cluster's own API server:

```
dashboard  ──►  remote API server  ──►  node proxy  ──►  kubelet  ──►  /var/log/oauth-server/audit.log
                (that cluster's bearer token, from gsd-cluster-<name>)
```

The request is exactly what `oc adm node-logs --path=oauth-server/audit.log` issues:

```
GET /api/v1/nodes/<node>/proxy/logs/oauth-server/audit.log
```

So a cluster the dashboard can already poll needs **no new connectivity** to be captured from — the
same API endpoint and the same credential carry it.

**`oauth-server`, not `oauth-apiserver`.** Both directories exist on a control-plane node and they
are different components. `oauth-server` is the login flow (`POST /login`, `GET /oauth/authorize`) —
that is where authentication decisions are recorded. `oauth-apiserver` is the API server for OAuth
*resources* (`oauthaccesstokens`, `oauthclients`) and records operations on those objects, not login
attempts. The reader uses `oauth-server` (`gsd/auditlog.py#AUDIT_DIR`).

## 2. What it needs on the observed cluster

Two rules, on the ServiceAccount the dashboard authenticates as:

```
nodes        list      discover which nodes are control-plane
nodes/proxy  get       read the log through the API server
```

**These are already granted.** On the hosting cluster this repository's chart binds them to the
dashboard's ServiceAccount (`<release>-login-capture-audit`,
`charts/group-sync-dashboard/templates/login-capture-rbac.yaml`). On every other observed cluster they
ship in the **`group-sync-operator-helm`** chart, in the ClusterRole
`group-sync-dashboard-cluster-poller`, which is installed on each cluster to be observed. That is the boundary: the operator chart decides what
the dashboard may read on a cluster; the dashboard chart only consumes it. If that grant needs
changing, it changes there.

**Be clear about what `get nodes/proxy` is.** It is read access to everything the kubelet serves over
GET on those nodes — other containers' logs, the apiserver audit logs, the journal — not just this
one file. The dashboard reads only `oauth-server/`, but the *grant* is wider than the use. Narrow it
with `loginCapture.auditLog.nodeNames`, which pins `resourceNames` and drops the `list` entirely.

Node discovery uses `loginCapture.auditLog.nodeSelector`, default
`node-role.kubernetes.io/master=`. Note that OpenShift sets both that and
`node-role.kubernetes.io/control-plane`; `master` is the deprecated label upstream, so a cluster that
stops setting it would discover zero nodes.

## 3. What counts as a login

Only events whose annotations carry **both** `authentication.openshift.io/username` and
`authentication.openshift.io/decision` (`allow`, `deny` or `error`). Three shapes, each its own kind:

| kind | request |
|---|---|
| `credential` | `POST /login[/<idp>]` — the interactive form |
| `cli` | `GET /oauth/authorize?client_id=openshift-challenging-client` — `oc login`, curl basic auth |
| `session` | `GET /oauth/authorize` with any other `client_id` — an existing session re-authorising |

Consent (`/oauth/authorize/approve`) is a decision about a client, not a login, and is not a row.

**Never recorded:** system accounts (`system:*`, `kube:admin`) and identities matching
`loginCapture.auditLog.ignoreIdentityPatterns` (default `ou=TrustedApplications` — an LDAP bind
service account's allows and denies are not personnel events).

**Recorded even when the name does not exist:** a failed attempt against an unknown username is still
a row, carrying `identity_match: NULL`. The identity is classified, not filtered.

## 4. Worked example — read it yourself from the mock cluster

The lab runs mock clusters that serve a fixture audit log, so the whole path can be exercised without
a second real cluster. Each mock is its own service: `mock-trusted`, `mock-privateca`,
`mock-selfsigned` — at `https://<name>:6443`, not at `mock-openshift`.

From inside the dashboard pod, with the cluster's own token:

```sh
TOK=$(oc get secret gsd-cluster-mock-trusted -n group-sync-dashboard \
        -o jsonpath='{.data.config}' | base64 -d | jq -r .bearerToken)

oc exec -n group-sync-dashboard deploy/group-sync-dashboard -c dashboard -- sh -c \
  "curl -s -H 'Authorization: Bearer $TOK' \
   'https://mock-trusted:6443/api/v1/nodes/master-0/proxy/logs/oauth-server/audit.log'"
```

Result — `HTTP 200`, 1559 bytes, three records:

```
POST /login/acme-ldap                                          jane.smith  allow  302   -> credential
GET  /oauth/authorize?client_id=openshift-challenging-client   lateef.o    deny   401   -> cli
GET  /oauth/authorize?client_id=console                        dana.lee    allow  302   -> session
```

One record in full, abbreviated:

```json
{"kind":"Event","apiVersion":"audit.k8s.io/v1","level":"Metadata",
 "auditID":"60a6dc3b-...","stage":"ResponseComplete",
 "requestURI":"/login/acme-ldap","verb":"post",
 "user":{"username":"system:anonymous"},
 "responseStatus":{"code":302},
 "annotations":{"authentication.openshift.io/username":"jane.smith",
                "authentication.openshift.io/decision":"allow"}}
```

**Note `user.username` is `system:anonymous` on every one.** That is why the annotations have to
exist at all: the request is what authenticates, so the record's own user field cannot say who tried.
Reading `user.username` instead of the annotation would attribute every login to nobody.

The mock's fixture lives in the `mock-fixture` ConfigMap, under `reference.yaml`'s `auditLog` key,
alongside the nodes it reports — so the node-discovery step is exercised too.

## 5. How a read is bounded

Per node, per cycle: list the `oauth-server/` directory, read each unread or partially read file from
its **byte cursor** (rotated files ascending by stamp, then `audit.log`), parse whole lines only, and
advance the cursor to the last newline consumed.

So a steady cluster transfers almost nothing — the `audit.log read 0 byte(s) from offset 1559` line
means "nothing new since last time", not "nothing found". A first sight **backfills** through the
rotated files, bounded by `loginCapture.retentionDays` and drained at 8 MiB per node per cycle so the
first read cannot flood.

## 6. What it cannot tell you

A `deny` carries **no cause**. LDAP result codes exist only in the Debug pod log, so a refusal is
recorded as failed with what the record has — the HTTP status (302 back to the form for a browser,
401 for the CLI) and `responseStatus.message` where present.

That matters in one specific case: a **locked** directory account answers LDAP code 19, which
OpenShift surfaces as an HTTP 500 rather than a 401. The audit log will show the failure but not that
the account is locked. The pod-log reader has been removed; new capture cannot supply that LDAP cause. Existing stored causes remain readable.
