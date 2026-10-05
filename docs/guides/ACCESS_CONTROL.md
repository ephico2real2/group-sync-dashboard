# How access control works in this dashboard

Who sees what, why, and where each decision is made in the code.

Two questions are answered separately and must not be confused:

1. **Can you get in at all?** The oauth-proxy answers this. The app never sees an unauthenticated
   request.
2. **How much do you see once you are in?** The app answers this, per request, per endpoint. That
   is what most of this document is about.

---

## 1. Where identity comes from

```
  OpenLDAP (the lab directory)          uid=john.doe,ou=People,dc=ephico2real,dc=com
        │
        │  the ldap-local identity provider, on first login
        ▼
  OpenShift User object                 User/john.doe   identities: [ldap-local:...]
        │
        │  group-sync-operator, on a schedule, from the same directory
        ▼
  OpenShift Group objects               Group/app-ocp-rbac-demo-cluster-admin
        │                               annotated openshift.io/ldap.uid = cn=...,ou=Groups,...
        │  normal RBAC binds roles to those groups
        ▼
  ClusterRoleBinding                    app-ocp-rbac-demo-cluster-admin-crb -> ClusterRole/admin
```

So a person's cluster power comes from **group membership in the directory**, not from anything in
this chart — with one exception: `rbacAuditors` (on by default) binds a read-only audit ClusterRole to
the named auditor Groups, and that role passes the wide tier's question (§2, §9). The dashboard reads
that arrangement; at runtime it grants nothing.

**The login flow, and the one header that matters:**

```
  browser ──► Route ──► oauth-proxy (sidecar, :8443) ──► app (127.0.0.1:8080)
                          │                                 ▲
                          │ sets X-Forwarded-User            │ the app trusts this header
                          └─────────────────────────────────┘   ONLY because nothing else can
                                                                reach the app's port
```

The app believes `X-Forwarded-User` because the container listens on the pod's loopback and the
Service targets the proxy, so the only writer of that header is the proxy. With the proxy switched
off there is no trusted identity at all — see §8.

---

## 2. The three thresholds

A reader is placed in a **tier** by asking the cluster a question about them — a
SubjectAccessReview. There are three thresholds, each its own setting, resolver and cache:

| threshold | values key | default check | governs |
|---|---|---|---|
| **wide tier** | `visibility.adminSar` | `list clusterrolebindings.rbac.authorization.k8s.io` | every cluster-data view |
| **usage tier** | `visibility.usageAdminSar` | `update clusterrolebindings.rbac.authorization.k8s.io` | the Usage tab alone |
| **cluster-admin tier** | `visibility.clusterAdminSar` | `update clusterrolebindings.rbac.authorization.k8s.io` | the KPI page and the whole Cluster Configurations tab (#322) — and, for whoever passes it, every tier above |

**The cluster-admin tier is the top tier** (the operator's decision of 2026-09-23, #322). A reader who
passes it is granted every tier the host decides — the wide view on the host and on `inherit`
clusters, and Usage, with `visibility.enabled: false` too — whatever the other two questions answer
for them (`gsd/api.py#viewer_scope`, `gsd/api.py#usage_scope` consult it first). One way only:
passing the wide or the usage question never implies it, so those two can be loosened without
handing anyone the Cluster Configurations tab. Per-cluster policies still apply (§11): a `remote-sar`
cluster asks its own API about the person, a `self-only` cluster stays self, a `hidden` cluster stays
hidden. It is asked whatever `visibility.enabled` says (§8), and the default is the usage tier's
question as its own setting — a cluster-reader fails it, a cluster-admin passes it — where the
`get`/`create secrets` pair it replaced admitted anyone holding `admin` or `edit` in the release
namespace.

A SubjectAccessReview **asks whether a subject could perform a verb**. It performs nothing. The
dashboard never performs the `update` the usage and cluster-admin thresholds name. Its
ServiceAccount's own writes are its Leases (the leader election's and a fleet account's), the
TokenReviews and SubjectAccessReviews `system:auth-delegator` allows (the oauth-proxy uses both; the
application asks these questions as SubjectAccessReviews; neither stores an object), and, only with
`clusterConfig.secrets.writes.enabled`, cluster Secrets in its own namespace.

**Why three, and why two of them ask about a write verb.** Measured on the lab's two ClusterRoles
(2026-10-05); a modified or aggregated ClusterRole elsewhere can answer differently:

| check | `cluster-admin` | `cluster-reader` | separates them? |
|---|---|---|---|
| `list groups.user.openshift.io` | yes | yes | no |
| `list clusterrolebindings` | yes | yes | no |
| `update clusterrolebindings` | yes | **no** | **yes** |
| `get secrets` | yes | **no** | **yes** |

On the lab, no *read* check on the objects these views show distinguished them, because `cluster-reader`
could read all of them. Only a write verb does, or a read `cluster-reader` excludes, such as `get secrets`.

That matters for Usage. Everything else the wide tier serves, Logins aside (below), can be obtained
outside the dashboard by anyone who passes the wide check:

| view | reproducible with `oc`? |
|---|---|
| Groups, Access granted, RBAC policy, Namespace audit | yes — `oc get groups`, `oc get clusterrolebindings`, `oc get rolebindings -A`; Access granted's "Reaches" column (members, and members who have logged in) also needs `oc get users` |
| Logins | **no**, since the pod-log reader was removed (chart 0.58.0, #321) — the records come from the oauth-server audit log, which `oc adm node-logs --path=oauth-server/audit.log` reads with `get nodes/proxy`, and the lab's `cluster-reader` does not hold it; the oauth-server pod log, which it can read, names no login at the default log level |
| **Usage** | **no** — it exists only in the dashboard's own `dashboard_user_activity` table |

So `cluster-reader` seeing the audit views grants it nothing new, Logins aside, and that persona is
deliberate: a security auditor is given `cluster-reader` or the chart's `rbacAuditors` report-auditor
role (§1), not `cluster-admin`. Usage is where the two
must diverge, so Usage gets the higher bar.

---

## 3. What each reader sees

One row for every page the dashboard draws: its fourteen tabs, in the order of the tab strip, then the two pages
that have no tab of their own (the Reporting status page, opened from Reports, and the search page, opened from the
search box). The reader columns are §4's personas. A reader with no identity never sees the page: the proxy admits
nobody to `/` without a session, and `charts/group-sync-dashboard/values.yaml#skipAuthRegex` lists the only paths it
lets through. Reports, Library and Reporting status exist only with reporting on (`reporting.enabled`, on by
default); with it off, no reader is drawn those two tabs. Each reader cell is one word:

| word | what the reader gets |
|---|---|
| all | the page, with the whole cluster's rows |
| self | the page, narrowed to the reader's own rows and saying so |
| refused | the tab is drawn, and the page is a named refusal card |
| absent | no tab is drawn; reached by URL, the page is the refusal card |

The page decides none of this (§7): it draws what `/api/whoami` and each response's `scope` declare, and every
refusal is the server's 403 first. `local-development/tests/test_access_declaration.py` holds this table to the tabs and
pages `local-development/gsd/static/index.html` can draw, and `local-development/tests/test_ui.py#TestTheDeclaredTabs`
loads every page as every persona and holds the tab strip and each refusal card to it.

| page | tab | self | auditor | usage | cluster-admin | what a narrowed or refused reader sees |
|---|---|---|---|---|---|---|
| home | Home | self | self | self | self | their own access, at every tier by design (#158): an administrator's Home is theirs, never everyone's |
| overview | Overview | refused | all | refused | all | the refusal card: the Overview is the cluster's own health |
| kpi | KPIs | absent | absent | absent | all | no tab; by URL, the refusal card |
| groups | Groups | self | all | self | all | the groups they belong to |
| users | Users | self | all | self | all | their own row |
| bindings | Access granted | self | all | self | all | their own grants, through their groups, with the group named |
| policy | RBAC policy | refused | all | refused | all | the refusal card: the whole binding surface has no per-reader subset |
| kyverno | Kyverno | refused | all | refused | all | the refusal card: a policy finding is about the cluster, not the reader |
| nsaudit | Namespace audit | self | all | self | all | the namespaces and grants that reach them |
| logins | Logins | self | all | self | all | their own attempts |
| usage | Usage | self | self | all | all | their own activity; the auditor too, because Usage is the usage tier's (§2) |
| reports | Reports | refused | all | refused | all | the refusal card: reports are documents about the cluster |
| library | Library | refused | all | refused | all | the refusal card, as Reports |
| clusters | Cluster Configurations | absent | absent | absent | all | no tab; by URL, the refusal card |
| reporting | — | refused | all | refused | all | the refusal card, as Reports |
| lookup | — | self | all | self | all | the search over their own groups, users and namespaces |

Access granted is narrowed, not refused: a reader's own path — the bindings that reach them through
their groups, with the group named — is what `require_admin_tier` deliberately never withheld, and
since 0.10.0 the tab shows it (from their own `/users/{name}`), while the cluster-wide list behind
`bindings/findings` stays the administrator tier and still answers a plain reader with the refusal.

The refused pages are refused rather than narrowed because their content is about the cluster rather
than about any reader: the Overview is the cluster's own health, RBAC policy is the whole binding
surface against the policy operator, Kyverno's findings are cluster-wide, and a report is a document
over the whole cluster. None has an honest per-reader subset. (Access granted has one: a reader's own
path, above.) KPIs and Cluster Configurations are left out of the strip rather than refused (#322):
the tab is not drawn for a reader the cluster-admin tier refuses.

---

## 4. Endpoint by endpoint

This section is the declaration: one row for every route the application registers, keyed by method and
path, because `GET /api/clusterconfigs` and `POST /api/clusterconfigs` share a path and not a gate.
`local-development/tests/test_access_declaration.py` builds the app with every switch that registers a route turned
on, walks `app.routes`, and fails when a route has no row, when a row names a route the app does not serve, or when
any persona is answered differently from its row. A route that ships without a gate, or with a lower one, fails
CI. The table records the gates; it does not configure them (§10 does).

**The posture the rows describe:** the oauth-proxy on, `visibility.enabled: true`, the host cluster deciding
(`inherit`, §11) for every cluster the dashboard reads, reporting on, for the six rows registered `writes on`,
`clusterConfig.secrets.writes.enabled: true`, and, for the five rows registered `housekeeping on`, `housekeeping.enabled: true`
(the chart's default) with each write carrying the page's `X-GSD-Interaction` header. §8 says what changes with the proxy or the restrictions off, and §11
what a remote cluster's own policy changes; of these rows only `/api/alerts` reads every cluster, and its `scope` is
the narrowest across them, so a `remote-sar` or `self-only` cluster that does not widen the reader makes it `self`.

**The personas.** Each is one reader, so a path naming the reader's own group, user or namespace resolves:

| persona | what it passes |
|---|---|
| no identity | nothing: the proxy is on and sent no `X-Forwarded-User`. In a deployment the proxy lets a request through without a session only on the paths `skipAuthRegex` lists; this column is the app's own answer behind it |
| self | none of the three questions (§2) |
| auditor | `visibility.adminSar` only: a `cluster-reader` |
| usage | `visibility.usageAdminSar` only |
| cluster-admin | `visibility.clusterAdminSar` only. It grants the wide view and Usage (#322), so a `cluster-admin`, who passes all three, is answered the same |

**The words in the persona columns:**

| word | the answer |
|---|---|
| all | 200, and the body's `scope` is `all` (`visibility.scope` on `/api/whoami`) |
| self | 200, and the body's `scope` is `self` |
| 200 | 200, with no `scope` in the body |
| 403 | refused |
| 308 | a redirect to `/api` |
| admitted | past the gate: the write reaches its own checks, which its own tests hold |

**gate** names the function in `local-development/gsd/api.py` the handler calls, or `none`, and the test checks that
the handler calls it. **registered** is `always`, `writes on` for the six routes that exist only with
`clusterConfig.secrets.writes.enabled`, or `housekeeping on` for the five that exist only with `housekeeping.enabled`.
`scope` and `viewer` ride on every collection response, so a client never has
to guess.

| method | path | registered | gate | no identity | self | auditor | usage | cluster-admin | notes |
|---|---|---|---|---|---|---|---|---|---|
| GET | `/api/clusters` | always | viewer_scope | 200 | 200 | 200 | 200 | 200 | reachable for everyone, because the cluster selector needs it on every tab; each row carries `visibility.scope` for this reader, and `operator_configs` is `null` below the wide tier |
| GET | `/api/clusters/{cluster_id}/groupsyncs` | always | viewer_scope | 200 | 200 | 200 | 200 | 200 | full CR health at every tier, minus `ldap_filter` and `error_message` below the wide tier (below) |
| GET | `/api/clusters/{cluster_id}/groupsyncs/{name}/events` | always | none | all | all | all | all | all | the same at every tier, by ruling |
| GET | `/api/clusters/{cluster_id}/groups` | always | viewer_scope | 403 | self | all | self | all | at self, the groups they belong to |
| GET | `/api/clusters/{cluster_id}/groups/{name}` | always | viewer_scope | 403 | self | all | self | all | at self, 403 unless a member; a member's 200 names the group's bindings (below) |
| GET | `/api/clusters/{cluster_id}/users` | always | viewer_scope | 403 | self | all | self | all | at self, their own row (with `first_login_source`) |
| GET | `/api/clusters/{cluster_id}/users/{name}` | always | viewer_scope | 403 | self | all | self | all | at self, 403 unless it is them; their own 200 names the bindings reaching them (below) |
| GET | `/api/clusters/{cluster_id}/user-bindings` | always | viewer_scope | 403 | self | all | self | all | at self, their own grants, acknowledged or not, with the acknowledged count and list `null`; at the wide tier, the grants the operator acknowledged are counted and listed apart (#503) |
| GET | `/api/clusters/{cluster_id}/membership-changes` | always | viewer_scope | 403 | self | all | self | all | at self, changes affecting them |
| GET | `/api/clusters/{cluster_id}/binding-changes` | always | viewer_scope | 403 | self | all | self | all | at self, rows naming them or a group they belong to |
| GET | `/api/clusters/{cluster_id}/logins` | always | viewer_scope | 403 | self | all | self | all | at self, their own attempts |
| GET | `/api/clusters/{cluster_id}/cluster-access` | always | viewer_scope | 403 | self | all | self | all | at self, their own gate status |
| GET | `/api/clusters/{cluster_id}/namespaces` | always | viewer_scope | 403 | self | all | self | all | at self, the namespaces their memberships or grants reach |
| GET | `/api/clusters/{cluster_id}/namespaces/{name}` | always | viewer_scope | 403 | self | all | self | all | at self, 403 before any lookup unless it reaches them; then their own paths only |
| GET | `/api/clusters/{cluster_id}/home` | always | viewer_scope | 403 | self | all | self | all | the reader's own access at every tier; `scope` names the tier that decided |
| GET | `/api/alerts` | always | viewer_scope | self | self | all | self | all | at self, the kinds in `SELF_ALERT_KINDS`, with the `reconcile_error` detail replaced by a generic sentence |
| GET | `/api/whoami` | always | viewer_scope | 200 | self | all | self | all | their identity and declared tier; with no identity, no `visibility` claim |
| GET | `/api/clusters/{cluster_id}/bindings/findings` | always | require_admin_tier | 403 | 403 | all | 403 | all | the cluster's whole binding surface |
| GET | `/api/clusters/{cluster_id}/operator-configs` | always | require_admin_tier | 403 | 403 | all | 403 | all | the operator's configuration |
| GET | `/api/clusters/{cluster_id}/kyverno` | always | require_admin_tier | 403 | 403 | all | 403 | all | Kyverno's policy findings, cluster-wide |
| GET | `/api/report/ticket` | always | require_admin_tier | 403 | 403 | 200 | 403 | 200 | a signed ticket for the report service, bound to the viewer; 404 with reporting off |
| GET | `/api/dashboard/activity` | always | usage_scope | 403 | self | self | all | all | at self, their own rows; `userActivity.visibility: all` widens it for everyone (§10) |
| GET | `/api/dashboard/reports` | always | usage_scope | 403 | self | self | all | all | at self, their own report runs |
| GET | `/api/kpi` | always | require_cluster_admin | 403 | 403 | 403 | 403 | all | the cluster-admin tier, whatever `visibility.enabled` says (§8) |
| GET | `/api/clusterconfigs` | always | require_cluster_admin | 403 | 403 | 403 | 403 | all | the cluster-admin tier, whatever `visibility.enabled` says (§8) |
| POST | `/api/clusterconfigs` | writes on | _writes_gate | 403 | 403 | 403 | 403 | admitted | an identity and the cluster-admin tier first, then the switch |
| PUT | `/api/clusterconfigs/{name}/credential` | writes on | _writes_gate | 403 | 403 | 403 | 403 | admitted | as above |
| DELETE | `/api/clusterconfigs/{name}` | writes on | _writes_gate | 403 | 403 | 403 | 403 | admitted | as above |
| POST | `/api/clusterconfigs/test` | writes on | _writes_gate | 403 | 403 | 403 | 403 | admitted | as above |
| POST | `/api/clusterconfigs/{name}/refresh` | writes on | _writes_gate | 403 | 403 | 403 | 403 | admitted | as above |
| POST | `/api/clusterconfigs/{name}/rejoin` | writes on | _writes_gate | 403 | 403 | 403 | 403 | admitted | as above |
| GET | `/api/housekeeping/copies` | housekeeping on | _housekeeping_gate | 403 | 403 | 403 | 403 | 200 | the database copies on this pod's volume (#542); an identity and the cluster-admin tier |
| DELETE | `/api/housekeeping/copies/{kind}/{name}` | housekeeping on | _housekeeping_write | 403 | 403 | 403 | 403 | admitted | an identity, the cluster-admin tier, then the page's header; the newest copy of each directory is refused (409) |
| POST | `/api/housekeeping/copies/cleanup` | housekeeping on | _housekeeping_write | 403 | 403 | 403 | 403 | admitted | as above; a preview without `confirm`, a delete of exactly that set with it (409 when it changed) |
| DELETE | `/api/housekeeping/reports/{run_id}` | housekeeping on | _housekeeping_write | 403 | 403 | 403 | 403 | admitted | as above; the report service deletes it at the dashboard's request with the service token |
| POST | `/api/housekeeping/reports/cleanup` | housekeeping on | _housekeeping_write | 403 | 403 | 403 | 403 | admitted | as above |
| GET | `/metrics` | always | none | 200 | 200 | 200 | 200 | 200 | public by ruling, so it carries no name |
| GET | `/healthz` | always | none | 200 | 200 | 200 | 200 | 200 | the liveness probe |
| GET | `/readyz` | always | none | 200 | 200 | 200 | 200 | 200 | the readiness probe |
| GET | `/api/version` | always | none | 200 | 200 | 200 | 200 | 200 | the running build |
| GET | `/api/openapi.json` | always | none | 200 | 200 | 200 | 200 | 200 | FastAPI's own schema route, behind the proxy like the data it describes |
| GET | `/api` | always | none | 200 | 200 | 200 | 200 | 200 | the schema browser |
| GET | `/api/redoc` | always | none | 200 | 200 | 200 | 200 | 200 | the reference rendering |
| GET | `/api/docs` | always | none | 308 | 308 | 308 | 308 | 308 | the conventional path, redirected to `/api` |
| GET | `/` | always | none | 200 | 200 | 200 | 200 | 200 | the page; it draws what `/api/whoami` declares (§3) |
| GET | `/signed-out` | always | none | 200 | 200 | 200 | 200 | 200 | the proxy's sign-out target; it reads no identity header |
| GET | `/static/index.html` | always | none | 200 | 200 | 200 | 200 | 200 | the page again, rendered, shadowing the raw file |
| GET | `/static/signed-out.html` | always | none | 200 | 200 | 200 | 200 | 200 | the sign-out page again, rendered, shadowing the raw file |
| GET | `/static/{path}` | always | none | 200 | 200 | 200 | 200 | 200 | the stylesheet, icon and vendored scripts (a mount; it refuses the page sources) |

**Served by another service**, behind the same proxy, and not a route of this application:

| path | served by | who is admitted |
|---|---|---|
| `/report/**` | the report service | a ticket from `/api/report/ticket` (a viewer), signed with the ticket key and never the service token (#392), or the service token; a viewer without a ticket gets 401, a ticket for another identity 403, a ticket of the earlier format 401 (the page mints again) |

**Two deliberate asymmetries, both measured:**

- `groupsyncs` is *not* gated, but it is *projected*. `/metrics` is in `skipAuthRegex` and already
  serves `gsd_groupsync_state{groupsync=...}`, `_last_sync_timestamp_seconds` and `_groups_total` to
  a request with no credential at all, so refusing CR health while the metric is public would be
  theatre — and it would cost the Groups tab its per-provider colour slots. Gate `/metrics` first if
  this should change. Two fields are the exception, by the spec's own ruling: **`ldap_filter` and
  `error_message` are omitted at the self tier**, because both can embed directory DNs and the gate
  group — which `/metrics` deliberately never carries, and which a narrowed reader cannot `oc get`
  the CR to read (measured: the narrowed personas fail `oc auth can-i get
  groupsyncs.redhatcop.redhat.io`). The omission is an allowlist
  (`gsd/api.py#SELF_TIER_GROUPSYNC_FIELDS`), so a field added later is withheld at self until
  somebody rules on it. The same diagnostic reaches `/api/alerts` as the `reconcile_error` detail,
  where the self tier keeps the alert and receives a generic sentence instead of the text —
  replaced rather than omitted, so an empty reason column cannot read as "no reason exists".
  Administrators keep both fields and the full alert detail, byte-for-byte.
- `/api/clusters` stays reachable for everyone because the cluster selector needs it on every tab.
  Its group and binding counts are also on `/metrics`, so they are not withheld; the
  `operator_configs` summary is **not** on `/metrics`, so that pair is withheld as `null`.

**Withheld aggregates are `null`, never `0`.** A fabricated zero reads as "no problems found" when
the truth is "not counted for you".

### The self tier withholds the cluster's bindings, not the reader's own

Worth stating plainly, because "`/bindings/findings` → 403" invites the conclusion that a narrowed
reader sees no binding at all, and that is not true.

`/groups/{name}` and `/users/{name}` embed a `bindings` list. So a reader who belongs to a group
that holds `cluster-admin` can see that their group holds it, and the name of the binding that
grants it — `{"role_name": "cluster-admin", "binding_name": "admin-crb"}` — while
`/bindings/findings` refuses them.

**That is the design, not a leak.** The narrowed tier exists to answer *"what access do I have, and
how did I get it"*, and that question is unanswerable without naming the binding that granted it.
What separates it from the gated views is **scope**:

| | `/groups/{name}`, `/users/{name}` | `/bindings/findings` |
|---|---|---|
| whose access | the reader's own path | everyone's, cluster-wide |
| bounded by | membership, checked before any existence lookup | nothing — it is the whole surface |
| a non-member gets | 403, identical whether or not the group exists | 403 |

The membership check runs **before** the existence lookup precisely so the two 403s are
indistinguishable: otherwise "403 for a real group, 404 for an absent one" would make the endpoint a
group-name oracle for a reader who is in none of them.

What a narrowed reader therefore cannot obtain: which *other* groups hold privileged roles, who is
in them, or any binding that does not reach them. What they can: their own, in full. If even that is
too much for a deployment, the control is `visibility.enabled=false` plus an external gate — not a
narrower tier, because a tier that hides the reader's own access path has nothing left to show them.

---

## 5. How a request becomes a decision

```
  request
    │
    ├─ gsd/api.py#trusted_viewer                       the header, or None
    │
    ├─ gsd/config.py#Settings.cluster_policy           inherit | self-only | hidden | remote-sar
    │
    ├─ gsd/api.py#viewer_scope  (request, cluster_id)  -> (viewer, "all" | "self")
    │     restrictions off?                     ──────────►  "all"
    │     no viewer / no resolver?              ──────────►  "self"
    │     resolver raises or answers junk?      ──────────►  "self"
    │     resolver answers exactly "all"?       ──────────►  "all"
    │
    ├─ gsd/api.py#require_admin_tier  (request, cluster_id)   403 unless scope == "all"
    │     used by: bindings/findings, operator-configs, kyverno, mint ticket (/api/report/ticket)
    │
    ├─ gsd/api.py#usage_scope                          the SECOND, independent tier
    │     userActivity.visibility == all?       ──────────►  "all"   (blunt override, wins)
    │     cluster-admin tier answers "all"?     ──────────►  "all"   (the top tier)
    │     restrictions or proxy off?            ──────────►  "self"
    │     usage resolver answers "all"?         ──────────►  "all"
    │     anything else                         ──────────►  "self"
    │
    └─ gsd/api.py#require_viewer  (viewer, cluster_id)  403 when there is no identity
```

**Only the exact string `"all"` widens anything.** Every other outcome is `self`. That is the whole
fail-closed rule, in one sentence.

### The tier resolver

`gsd/kube.py#TierResolver` — one instance per threshold, so the three questions never share a
cache entry.

```
  resolve(viewer)
    │
    ├─ cache hit within visibility.tierTtlSeconds (60 by default)?  ──► return it
    │
    ├─ fetch_groups_of_user(viewer)      the reader's synced Group memberships, listed now
    │     + _virtual_groups_for(viewer)  system:authenticated, system:authenticated:oauth
    │                                    (a ServiceAccount's own three for a ServiceAccount)
    │
    ├─ POST SAR_API                      /apis/authorization.k8s.io/v1/subjectaccessreviews
    │     spec.user   = viewer
    │     spec.groups = those groups + the virtual ones          ◄── LOAD-BEARING, see below
    │     spec.resourceAttributes = the configured threshold
    │
    ├─ allowed == true   ──► TIER_ALL  ("all"),  cached for tierTtlSeconds
    ├─ allowed == false  ──► TIER_SELF ("self"), cached for tierTtlSeconds
    └─ any error         ──► TIER_SELF ("self"), NOT cached
```

**`spec.groups` is load-bearing.** A reader granted cluster-admin through a Group rather than a
direct binding is refused when `spec.groups` is absent — the review only sees the subject you
describe. Omitting it would silently demote every group-granted administrator. Verified live, on
the lab as it was then (the binding it names is gone; §9 has today's personas):

```
POST /apis/authorization.k8s.io/v1/subjectaccessreviews  -> 201
"allowed": true,
"reason": "RBAC: allowed by ClusterRoleBinding \"demo-cluster-admin-crb\"
           of ClusterRole \"cluster-admin\" to Group \"app-ocp-rbac-demo-cluster-admin\""
```

**A failure is never cached.** A decided answer is held for `visibility.tierTtlSeconds` (60 by
default); an error is retried on the next request, so an API-server outage does not pin every reader
to the narrow view until a TTL expires. The cost of the cache is stated plainly: a revoked
administrator keeps the wide view for at most that TTL (one minute at the default).

### Why the alert feed is an allow-list

`gsd/api.py#SELF_ALERT_DETAILS` is an **allow**-list, not a deny-list, so an alert kind added later
is hidden from the narrow view until somebody rules on it — and it is ONE structure carrying both
the admitted kinds and each kind's detail policy, with `SELF_ALERT_KINDS` derived from its keys, so
the two can never disagree. The list's invariant is *"every kind here is backed by a page the self
tier sees"* — and where that page withholds a field, the alert must not re-serve it:
`reconcile_error` keeps its kind at self (a current failure is actionable), but its `detail`, which
copies the CR's `error_message`, is replaced with a generic sentence. Replaced, never omitted — an
absent reason renders as an empty column, which reads as "no reason exists" when the truth is
"withheld".

That invariant was broken once, and it is why the shape matters: `dangling_binding` and
`config_reconcile_error` were still in the list after their backing endpoints started refusing at
the self tier, so a reader who got 403 from `/bindings/findings` was handed a group→role binding row
by `/api/alerts` in the same session. Both kinds are administrator-tier now.

---

## 6. How the setting reaches the code

```
  values.yaml                       visibility.enabled: true
      │                             visibility.adminSar.{apiGroup,resource,verb,namespace}
      │                             visibility.usageAdminSar.{...}
      │                             visibility.clusterAdminSar.{...}
      │
      ├─ deployment.yaml    ──►  env GSD_ENABLE_VIEW_RESTRICTIONS = "true" | "false"
      │                          (rendered by the gsd.visibilityEnabled helper)
      │
      ├─ configmap.yaml     ──►  visibilityAdminSar*        (4 keys)
      │                          visibilityUsageAdminSar*   (4 keys)
      │                          visibilityClusterAdminSar* (4 keys)
      │
      └─ rbac.yaml          ──►  system:auth-delegator binding, which is what allows the pod
                                 to POST a SubjectAccessReview at all. ONE grant serves all
                                 three tiers. It renders whenever the proxy is on, because the
                                 cluster-admin tier is asked even with visibility.enabled false.
      ▼
  config.py                       Settings.view_restrictions_enabled
                                  Settings.visibility_admin_sar_*
                                  Settings.visibility_usage_admin_sar_*
                                  Settings.visibility_cluster_admin_sar_*
                                  Settings.visibility_tier_ttl_seconds
      ▼
  api.py / kube.py                three TierResolver instances, published on app.state
                                  (the wide and usage ones only with restrictions on)
      ▼
  index.html                      reads `scope` and `viewer` off the wire
```

**Render-time guards, not runtime surprises.** RBAC matching is exact and lowercase, so a miscased
threshold (`List` for `list`) would not error — it would answer `allowed=false` for every reader and
silently demote every administrator. All three thresholds therefore **fail the `helm` render** on a
miscased, versioned or malformed shape, with a message naming the key.

The chart also refuses `visibility.enabled=true` together with `oauthProxy.enabled=false`, because
`X-Forwarded-User` is whatever the caller typed when nothing sets it. A security control that
silently cannot work is worse than one that refuses to install.

---

## 7. The UI never decides the tier

The page reads `scope` and `viewer` from the response and renders a label. It never computes a tier
of its own, so it cannot disagree with the server.

- A narrowed list carries a banner naming the viewer, so **"no rows for you"** is never mistaken for
  **"no rows on the cluster"**. An empty audit tab that looks healthy is a lie of layout.
- A refused view renders a **named refusal card**, never a blank: *"For administrators only."* It
  deliberately does **not** name the role, the check, the chart key or the README — that text is read
  by the person being refused, who cannot act on any of it, and naming the permission that would
  lift a restriction turns a refusal into a shopping list.
- The header pill states *"Your view — &lt;name&gt;"* or *"Full view"*, because "nothing looks
  different" and "you are seeing everything" are different statements and only the second is
  checkable from the screen.

**Hiding a tab is never the control.** Every refusal above is a server 403; the tab following suit is
a consequence.

---

## 8. Proxy off, and restrictions off

| configuration | what happens |
|---|---|
| proxy **on**, `visibility.enabled: true` | the design above |
| proxy **on**, `visibility.enabled: false` | every admitted reader sees all cluster data; the pill says scoping is off. Usage is **still** per-person unless `userActivity.visibility: all` |
| proxy **off**, `visibility.enabled: false` | wide view, plus a loud startup warning. This is the pre-existing behaviour of a proxy-less install and is preserved |
| proxy **off**, `visibility.enabled: true` | **the chart refuses to render**, naming both remedies |

With `visibility.enabled=false` the usage tier is **not consulted at all** — measured — so switching
off scoping for *cluster* data does not, as a side effect, publish presence records. The
**cluster-admin tier is still asked** in that state (#322, as the Cluster Configurations tier it
replaced was): the KPI page and the Cluster Configurations tab stay reserved to whoever passes it,
and a cluster-admin keeps Usage through it. The chart therefore renders the `auth-delegator` grant
with `visibility.enabled: false` too; without it every such review errors and both surfaces refuse
everyone. With the proxy off there is no identity to ask about, so both are withheld.

---

## 9. Verifying it yourself

The app trusts `X-Forwarded-User` only from inside the pod, which is also the cleanest way to test a
persona without logging in as them:

```bash
NS=group-sync-dashboard
POD=$(oc get pods -n $NS -l app.kubernetes.io/name=group-sync-dashboard -o name | head -1)

# what a given reader gets
oc exec -n $NS "$POD" -c dashboard -- curl -s \
  -H 'X-Forwarded-User: lateef.o' \
  localhost:8080/api/clusters/dashboard/groups
```

Ask the cluster the same question the app asks — note `spec.groups`, without which a group-granted
reader is refused:

```bash
oc create -f - -o jsonpath='{.status.allowed}{" "}{.status.reason}{"\n"}' <<EOF
apiVersion: authorization.k8s.io/v1
kind: SubjectAccessReview
spec:
  user: lateef.o
  groups: [system:authenticated, system:authenticated:oauth, app-ocp-rbac-groupsync-ns-auditor]
  resourceAttributes: {group: rbac.authorization.k8s.io, resource: clusterrolebindings, verb: list}
EOF
```

**Test personas** on the reference cluster. Credentials live in the LDAP lab repository, not here —
this document deliberately carries no passwords.

| persona | tier | what makes them interesting |
|---|---|---|
| `john.doe` | self | in `app-ocp-rbac-demo-cluster-admin`, a group *named* cluster-admin whose binding grants ClusterRole `admin`, not `cluster-admin` — looks like an admin, passes none of the three questions |
| `dana.lee` | wide only | standing `cluster-reader`: the auditor. Wide audit views, Usage refused |
| `jane.smith` | wide only | in `app-ocp-rbac-alpha-cluster-admin`, also bound to `admin`; wide **through a Group**, the auditor Group `app-ocp-rbac-groupsync-ns-auditor` that `rbacAuditors` binds, so the `spec.groups` path |
| `lateef.o` | wide only | ordinary reader with real login history, wide through the same auditor Group |

Measured on 2026-10-05 from the lab's ClusterRoleBindings and ClusterRoles (`oc get`), not with a
SubjectAccessReview. None of the four passes the usage or cluster-admin question there.

---

## 10. Changing it

| you want to | change |
|---|---|
| turn per-reader scoping off entirely | `visibility.enabled: false` |
| use a different bar for the wide tier | `visibility.adminSar.{apiGroup,resource,verb,namespace}` |
| use a different bar for Usage | `visibility.usageAdminSar.{...}` |
| use a different bar for the cluster-admin tier (KPIs, Cluster Configurations, and the top tier) | `visibility.clusterAdminSar.{...}` |
| let everyone see all dashboard usage | `config.userActivity.visibility: all` (wins over the usage tier) |
| shorten the fail-open window after a revocation | `visibility.tierTtlSeconds` (default 60; `0` disables caching). Env `GSD_VISIBILITY_TIER_TTL_SECONDS` still overrides it. A fractional or negative value fails the render rather than being silently discarded |
| put an admins-only door on the whole dashboard | `oauthProxy.sar` — a different mechanism, at the proxy |

Narrow the threshold and you narrow who is an administrator; you do not narrow what the wide view
contains. If you want less in the wide view, change the view.

## 11. Several clusters in one instance

The oauth-proxy authenticates a reader against the **hosting** cluster only — the enabled entry that
declares `dashboardController: true`, or the first enabled entry when none declares it
(`gsd/config.py#Settings.host_cluster`). Before application 0.19.0 the tier that cluster
decided gated every cluster's rows, so a host `cluster-admin` was served a remote cluster's
membership, bindings and login failures with no standing there, and a reader who was nobody on the
host but an administrator of the remote got the self view there, keyed by a username the remote had
never vouched for. Two keys per entry now say, per cluster, what a reader may see about it
(`gsd/config.py#Settings.cluster_policy`, `gsd/api.py#viewer_scope`).

| key | values | default | meaning |
|---|---|---|---|
| `clusters[].visibility` | `inherit` | the hosting entry | the host's DECIDED tier — the old behaviour, and the host's own default; on a remote an explicit choice that the host's RBAC governs that cluster's data too (a `self-only` host is self on every cluster it governs), with identity not consulted: a self reader is keyed by the host's username there, as before 0.19.0 |
| | `self-only` | a remote that states only `identity: none` | nobody is ever wide on this cluster; it costs no RBAC, no credential and no cluster call, and can only narrow |
| | `hidden` | | polled and alerted on (`/metrics`, the pod log) but never served through `/api`; refused on the host entry |
| | `remote-sar` | a remote that states neither key | that cluster's own RBAC decides: the same SubjectAccessReview as `visibility.adminSar`, created on the remote API with that entry's token, naming the reader and the Group memberships read from the remote; refused on the host entry, and refused beside an explicit `identity: none` |
| `clusters[].identity` | `none` | beside an explicit `inherit`, `self-only` or `hidden` | the host's username is not treated as anyone on this cluster: person-scoped views answer 403 there, cluster-level health still shows |
| | `same-as-host` | the hosting entry, forced; beside `remote-sar`; a remote that states neither key | the reader is matched on this cluster by OpenShift username, the `User` object's name, so the reader's self views apply to this cluster too |

**What each endpoint does.** Every `/api/clusters/{id}/…` handler calls `require_cluster` first: a
`hidden` cluster answers the same 404, with the same sentence naming the id the caller sent, as an id
that does not exist, so the response is not an oracle over which clusters this instance watches;
`hidden` clusters are absent from `/api/clusters`, `/api/whoami` and `/api/alerts` too. On a
`self-only` cluster the tier is `self` for every reader, and with `identity: none` the viewer is
withheld on purpose, so a person-scoped endpoint (groups, users, logins, grants, membership changes,
cluster access) answers 403 with exactly this sentence — *this data is scoped to a viewer, and this
cluster does not treat your identity as one of its own; only cluster-level health is shown for it* —
and never names the value that would change it; `/api/clusters/{id}/groupsyncs`,
`/api/clusters/{id}/groupsyncs/{name}/events` and the self kinds of alerts still serve.
`/api/alerts` is filtered per cluster in that cluster's tier, and its `scope` is the narrowest served:
`all` only when every served cluster is wide for this reader.

A cluster **removed from `clusters:`** (or one with `enabled: false`) is **retired**, not deleted (#96):
the poller marks its stored row `enabled = 0` at the start of every cycle — a config change rolls the
pod, so add/remove takes effect on the next start — and every surfacing path (`/api/clusters`,
`/api/whoami`, `/api/alerts`, `/metrics`, and a direct `/api/clusters/{id}/…`, which answers the same 404
as an unknown id) skips it. With no served cluster at all, `/api/alerts` fails closed to `scope: self`
(an empty feed is never the wide `all` view), matching `/api/whoami`. Its history and snapshot rows stay in the store, so an already-generated report is still
readable, but it no longer appears as `ok` with frozen data or raises stale "overdue" alerts. This
supersedes the earlier behaviour where a removed cluster resolved to `inherit` and lingered in the list.

**How `remote-sar` decides.** `gsd/kube.py#RemoteTierResolvers` finds or builds one `gsd/kube.py#TierResolver`
per remote-sar cluster on each request, from that cluster's current configuration — a values entry or a
Secret, written by hand, by the tab or by the lookup — and rebuilds it when the connection changes (its URL,
token or CA), so the review is created on the remote API with the remote token and
`gsd/kube.py#ClusterClient.fetch_groups_of_user` reads the **remote's** Group objects — the
group-resolution trap handled by construction. Cached per (reader, cluster) for
`visibility.tierTtlSeconds`; every failure (a 403 because the remote ServiceAccount lacks the
review, unreachable, junk) is the self tier and is not cached — and it holds that cluster's resolver for
`gsd/kube.py#REMOTE_FAILURE_HOLD_SECONDS` (30 s): no attempt on that remote starts while the hold runs, and the
first request that would call after it expires is the one probe; distinct viewers already in flight when the first
failure lands may each finish their attempt. Failures count under the same signal
as the host's (`gsd_visibility_tier_checks_total`), so
`templates/monitoring.yaml#GroupSyncDashboardVisibilityChecksFailing` fires exactly as for the host.
This chart manages no remote RBAC. On each remote, `group-sync-operator-helm` installs the joining
ServiceAccount's ClusterRole `group-sync-dashboard-cluster-poller`, which carries `create subjectaccessreviews`
and `list groups` (a ServiceAccount joined by hand needs the same two; a `ClusterRoleBinding` of
`system:auth-delegator` grants the first), and — so that an auditor is wide there too — the auditor ClusterRole,
one ClusterRoleBinding per auditor Group, and each auditor Group the host creates locally
(`rbacAuditors.groups[].createLocal`) with its members (`docs/specs/SPEC_D2b_remote_sar_for_every_join.md` §3.7).

**The two models side by side** — `inherit` against `remote-sar`, with pictures, the lab's measurements (the joining
ServiceAccount already holds the rights `remote-sar` needs) and the decisions that extend `remote-sar` to clusters
declared through a Secret: `docs/design/DESIGN_remote_cluster_access.md`.

**Identity is the OpenShift username.** `same-as-host` matches a reader on another cluster by their OpenShift
username, the `User` object's name, with no identity-provider distinction (D3 of
`docs/design/DESIGN_remote_cluster_access.md`, the operator's decision of 2026-09-23). A remote entry that states nothing
is `same-as-host` with `remote-sar` (SPEC_D2b); `none` fails closed and, stated alone, keeps `self-only`; and
`remote-sar` refuses to render or start beside `identity: none`, because its review names that username on the remote.

**On the wire.** `/api/whoami` carries `visibility.clusters[id] = {policy, identity, scope}` for every
served cluster beside the headline `scope`, which is the host's decision (a `self-only` host makes it
`self` for everyone, and with it the report ticket); each `/api/clusters` row carries
`visibility = {policy, scope}` for this reader; `/api/alerts` reports the narrowest `scope` served.
The UI renders these — the selector marks a narrowed cluster, one line beside it says which rule decided the
selected cluster's view (the host, the cluster's own RBAC, or self-only), the header pill and the cluster-scoped
tabs follow the selected one, the Reports tab follows the host's headline — and never derives them (§7).

**The other posture.** One dashboard per cluster and a fleet report reading each one's API with a
token from that cluster (`docs/guides/reference-architecture.md` §8a, `local-development/cluster-report.py`)
needs none of this and remains the recommendation where trust boundaries differ: each cluster
authorises its own readers, and the identity question is removed rather than answered.
