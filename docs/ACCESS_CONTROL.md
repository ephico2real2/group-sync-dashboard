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
  ClusterRoleBinding                    demo-cluster-admin-crb -> ClusterRole/cluster-admin
```

So a person's cluster power comes from **group membership in the directory**, not from anything in
this chart. The dashboard reads that arrangement; it never grants anything.

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
off there is no trusted identity at all — see §7.

---

## 2. The two thresholds

A reader is placed in a **tier** by asking the cluster a question about them — a
SubjectAccessReview. There are two independent thresholds:

| threshold | values key | default check | governs |
|---|---|---|---|
| **wide tier** | `visibility.adminSar` | `list groups.user.openshift.io` | every cluster-data view |
| **usage tier** | `visibility.usageAdminSar` | `update clusterrolebindings.rbac.authorization.k8s.io` | the Usage tab alone |

A SubjectAccessReview **asks whether a subject could perform a verb**. It performs nothing. The
dashboard holds no write grant on any resource, and the usage threshold naming a write verb does
not change that.

**Why two, and why the second one asks about a write verb.** Measured on both ClusterRoles:

| check | `cluster-admin` | `cluster-reader` | separates them? |
|---|---|---|---|
| `list groups.user.openshift.io` | yes | yes | no |
| `list clusterrolebindings` | yes | yes | no |
| `update clusterrolebindings` | yes | **no** | **yes** |
| `get secrets` | yes | **no** | **yes** |

No *read* check can distinguish them, because `cluster-reader` is by construction "may read
everything". Only a write verb does.

That matters for exactly one dataset. Everything else the wide tier serves can be obtained outside
the dashboard by anyone who passes the wide check:

| view | reproducible with `oc`? |
|---|---|
| Groups, Access granted, RBAC policy, Namespace audit | yes — `oc get groups`, `oc get clusterrolebindings`, `oc get rolebindings -A` |
| Logins | yes — `cluster-reader` holds `get,list,watch` on `pods/log` cluster-wide, so `oc logs` on the oauth-server pod yields the same records |
| **Usage** | **no** — it exists only in the dashboard's own `dashboard_user_activity` table |

So `cluster-reader` seeing the audit views grants it nothing new, and that persona is deliberate: a
security auditor is given `cluster-reader`, not `cluster-admin`. Usage is where the two must
diverge, so Usage gets the higher bar.

---

## 3. What each reader sees

| tab | ordinary reader | `cluster-reader` (auditor) | `cluster-admin` |
|---|---|---|---|
| Groups | their own groups | all | all |
| Namespace audit | grants affecting them | all | all |
| Logins | their own attempts | all | all |
| Usage | their own activity | **their own activity** | all |
| Overview | *For administrators only* | all | all |
| Access granted | *For administrators only* | all | all |
| RBAC policy | *For administrators only* | all | all |

Three tabs are **refused** rather than narrowed, because their content is about the cluster rather
than about any reader — a binding names whoever it names, so there is no honest per-reader subset
of it.

---

## 4. Endpoint by endpoint

`scope` and `viewer` ride on every collection response so a client never has to guess.

| endpoint | at the self tier | at the wide tier |
|---|---|---|
| `/api/clusters/{c}/groups` | groups they belong to | all |
| `/api/clusters/{c}/groups/{name}` | 403 unless a member — **and a member's 200 names the group's bindings**, see below | all |
| `/api/clusters/{c}/users` | their own row | all |
| `/api/clusters/{c}/users/{name}` | 403 unless it is them — **their own 200 names the bindings reaching them**, see below | all |
| `/api/clusters/{c}/user-bindings` | their own grants | all |
| `/api/clusters/{c}/membership-changes` | changes affecting them | all |
| `/api/clusters/{c}/logins` | their own attempts | all |
| `/api/clusters/{c}/cluster-access` | their own gate status | all |
| `/api/alerts` | filtered to `SELF_ALERT_KINDS` | all kinds |
| `/api/dashboard/activity` | their own rows | all — **usage tier only** |
| `/api/clusters/{c}/bindings/findings` | **403** | all |
| `/api/clusters/{c}/operator-configs` | **403** | all |
| `/api/clusters` | reachable; cluster-wide `operator_configs` withheld | full card |
| `/api/clusters/{c}/groupsyncs` (+ events) | **unchanged at both tiers** | same |
| `/api/whoami` | own identity + declared tier | same |

**Two deliberate asymmetries, both measured:**

- `groupsyncs` is *not* gated. `/metrics` is in `skipAuthRegex` and already serves
  `gsd_groupsync_state{groupsync=...}`, `_last_sync_timestamp_seconds` and `_groups_total` to a
  request with no credential at all. Refusing the API while the metric is public would be theatre,
  and it would cost the Groups tab its per-provider colour slots. Gate `/metrics` first if this
  should change.
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
    ├─ trusted_viewer(request)                  api.py:244   the header, or None
    │
    ├─ viewer_scope(request)                    api.py:254   -> (viewer, "all" | "self")
    │     restrictions off?                     ──────────►  "all"
    │     no viewer / no resolver?              ──────────►  "self"
    │     resolver raises or answers junk?      ──────────►  "self"
    │     resolver answers exactly "all"?       ──────────►  "all"
    │
    ├─ require_admin_tier(request)              api.py:340   403 unless scope == "all"
    │     used by: bindings/findings, operator-configs
    │
    ├─ usage_scope(request)                     api.py:284   the SECOND, independent tier
    │     userActivity.visibility == all?       ──────────►  "all"   (blunt override, wins)
    │     usage resolver answers "all"?         ──────────►  "all"
    │     anything else                         ──────────►  "self"
    │
    └─ require_viewer(viewer)                   api.py:325   403 when there is no identity
```

**Only the exact string `"all"` widens anything.** Every other outcome is `self`. That is the whole
fail-closed rule, in one sentence.

### The tier resolver

`kube.py:1018 class TierResolver` — one instance per threshold, so the two questions never share a
cache entry.

```
  resolve(viewer)
    │
    ├─ cache hit within TIER_TTL_SECONDS (60.0, kube.py:99)?  ──► return it
    │
    ├─ fetch_groups_of_user(viewer)      the reader's synced Group memberships
    │     + VIRTUAL_AUTH_GROUPS          system:authenticated, system:authenticated:oauth
    │
    ├─ POST SAR_API  (kube.py:79)        /apis/authorization.k8s.io/v1/subjectaccessreviews
    │     spec.user   = viewer
    │     spec.groups = polled groups + the two virtual ones     ◄── LOAD-BEARING, see below
    │     spec.resourceAttributes = the configured threshold
    │
    ├─ allowed == true   ──► TIER_ALL  ("all"),  cached for 60s
    ├─ allowed == false  ──► TIER_SELF ("self"), cached for 60s
    └─ any error         ──► TIER_SELF ("self"), NOT cached
```

**`spec.groups` is load-bearing.** A reader granted cluster-admin through a Group rather than a
direct binding is refused when `spec.groups` is absent — the review only sees the subject you
describe. Omitting it would silently demote every group-granted administrator. Verified live:

```
POST /apis/authorization.k8s.io/v1/subjectaccessreviews  -> 201
"allowed": true,
"reason": "RBAC: allowed by ClusterRoleBinding \"demo-cluster-admin-crb\"
           of ClusterRole \"cluster-admin\" to Group \"app-ocp-rbac-demo-cluster-admin\""
```

**A failure is never cached.** A decided answer is held 60s; an error is retried on the next
request, so an API-server outage does not pin every reader to the narrow view until a TTL expires.
The cost of the 60s cache is stated plainly: a revoked administrator keeps the wide view for at
most one minute.

### Why the alert feed is an allow-list

`api.py:75 SELF_ALERT_KINDS` is an **allow**-list, not a deny-list, so an alert kind added later is
hidden from the narrow view until somebody rules on it. The list's invariant is *"every kind here is
backed by a page the self tier sees in full"*.

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
      │
      ├─ deployment.yaml    ──►  env GSD_ENABLE_VIEW_RESTRICTIONS = "true" | "false"
      │                          (rendered by the gsd.visibilityEnabled helper)
      │
      ├─ configmap.yaml     ──►  visibilityAdminSar*      (4 keys)
      │                          visibilityUsageAdminSar* (4 keys)
      │
      └─ rbac.yaml          ──►  system:auth-delegator binding, which is what allows the pod
                                 to POST a SubjectAccessReview at all. ONE grant serves BOTH
                                 tiers. It renders whenever something needs it and disappears
                                 when nothing does.
      ▼
  config.py                       view_restrictions_enabled            (config.py:301)
                                  visibility_admin_sar_*               (config.py:307-314)
                                  visibility_usage_admin_sar_*         (config.py:324-328)
                                  visibility_tier_ttl_seconds          (config.py:338)
      ▼
  api.py / kube.py                two TierResolver instances, published on app.state
      ▼
  index.html                      reads `scope` and `viewer` off the wire
```

**Render-time guards, not runtime surprises.** RBAC matching is exact and lowercase, so a miscased
threshold (`List` for `list`) would not error — it would answer `allowed=false` for every reader and
silently demote every administrator. Both thresholds therefore **fail the `helm` render** on a
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

With `visibility.enabled=false` the usage tier is **not consulted at all** — measured — so no
SubjectAccessReview is attempted in that state, which is why the `auth-delegator` grant may be
absent there without breaking anything. Switching off scoping for *cluster* data must not, as a side
effect, publish presence records.

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
  localhost:8080/api/clusters/crc-local/groups
```

Ask the cluster the same question the app asks — note `spec.groups`, without which a group-granted
admin is refused:

```bash
oc create -f - -o jsonpath='{.status.allowed}{" "}{.status.reason}{"\n"}' <<EOF
apiVersion: authorization.k8s.io/v1
kind: SubjectAccessReview
spec:
  user: john.doe
  groups: [system:authenticated, system:authenticated:oauth, app-ocp-rbac-demo-cluster-admin]
  resourceAttributes: {group: user.openshift.io, resource: groups, verb: list}
EOF
```

**Test personas** on the reference cluster. Credentials live in the LDAP lab repository, not here —
this document deliberately carries no passwords.

| persona | tier | what makes them interesting |
|---|---|---|
| `john.doe` | wide + usage | cluster-admin **through a Group**, so the `spec.groups` path |
| `dana.lee` | wide only | standing `cluster-reader`: the auditor. Wide audit views, Usage refused |
| `jane.smith` | self | in a group *named* `...-cluster-admin` with no binding behind it — looks like an admin, is not |
| `lateef.o` | self | ordinary reader with real login history, so a narrowed Logins tab is non-empty |

---

## 10. Changing it

| you want to | change |
|---|---|
| turn per-reader scoping off entirely | `visibility.enabled: false` |
| use a different bar for the wide tier | `visibility.adminSar.{apiGroup,resource,verb,namespace}` |
| use a different bar for Usage | `visibility.usageAdminSar.{...}` |
| let everyone see all dashboard usage | `config.userActivity.visibility: all` (wins over the usage tier) |
| shorten the fail-open window after a revocation | `visibility.tierTtlSeconds` (default 60; `0` disables caching). Env `GSD_VISIBILITY_TIER_TTL_SECONDS` still overrides it. A fractional or negative value fails the render rather than being silently discarded |
| put an admins-only door on the whole dashboard | `oauthProxy.sar` — a different mechanism, at the proxy |

Narrow the threshold and you narrow who is an administrator; you do not narrow what the wide view
contains. If you want less in the wide view, change the view.
