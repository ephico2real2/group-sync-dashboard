# Spec: a second, stricter tier for the Usage tab

Branch `feat/per-user-visibility`, from `ac872d2`. Suite baseline **1201 passed / 0 failed**.

## The problem, measured

`cluster-admin` is currently restricted on exactly one tab. Live on revision 104:

```
GET /api/dashboard/activity   X-Forwarded-User: john.doe   (cluster-admin)
  -> scope='self'  rows=0
```

Everywhere else `john.doe` is wide. Usage alone stays per-person, because it is gated by
`config.userActivity.visibility` (default self-only) rather than by the visibility tier — a
deliberate choice recorded in the chart README:

> handing it to the tier would let every `cluster-reader` browse colleagues' presence records —
> a personnel dataset widened as a side effect

That concern is real, and it is the ONLY dataset for which it is real. Everything else the wide
tier serves is obtainable with `oc` by anyone holding the roles that pass the tier check:

| tab | reproducible outside the dashboard? |
|---|---|
| Groups, Access granted, RBAC policy, Namespace audit | yes — `oc get groups`, `oc get clusterrolebindings`, `oc get rolebindings -A` (and `oc get users` for Access granted's member and login counts) |
| Logins | yes — `cluster-reader` holds `get,list,watch` on `pods/log` in the core group, cluster-wide, so `oc logs` against the oauth-server pod yields the same records |
| **Usage** | **no** — it lives only in the dashboard's own `dashboard_user_activity` table |

## The operator's ruling

> "I think it is good in case someone from security wants to audit us. we can grant them cluster
> reader and not cluster admin. But it means cluster-admin need to see all and not gated all"

So: `cluster-reader` is the **auditor** persona and keeps every wide audit view it has today.
`cluster-admin` must be ungated **everywhere, including Usage**.

## Why this needs a write verb, and why one tier cannot do it

The tier check is a SubjectAccessReview. Measured against both ClusterRoles on the reference
cluster:

| candidate check | `cluster-admin` | `cluster-reader` | separates? |
|---|---|---|---|
| `list groups.user.openshift.io` — today's default | yes | yes | **no** |
| `list clusterrolebindings.rbac.authorization.k8s.io` | yes | yes | **no** |
| `update clusterrolebindings.rbac.authorization.k8s.io` | yes | **no** | **yes** |
| `create clusterrolebindings.rbac.authorization.k8s.io` | yes | **no** | **yes** |
| `get secrets` | yes | **no** | **yes** |

No **read** check can separate them, because `cluster-reader` is by construction "may read
everything". Only a write verb (or `get secrets`) does. Hence a second threshold, and hence it
asks about a write permission.

**The dashboard still never writes anything.** A SubjectAccessReview *asks* whether a subject
could perform a verb; it performs nothing. The app holds no write verb on any resource and this
does not change that. `update clusterrolebindings` is chosen over `get secrets` because it means
"this person administers who has access", which is the question actually being asked, and because
secret-read is granted to non-administrators in plenty of organisations.

## Shape

**Values** — mirror the existing `visibility.adminSar`, so an operator meets one pattern twice:

```yaml
visibility:
  enabled: true
  adminSar:                                  # the wide-view tier (unchanged)
    apiGroup: user.openshift.io
    resource: groups
    verb: list
    namespace: ""
  # The Usage tab is dashboard-usage data: who opened this dashboard, on which days, in which
  # window. It exists nowhere else on the cluster, so unlike every other wide view it cannot be
  # reproduced with `oc` — which is why it gets a HIGHER bar than the audit views.
  #
  # Measured: no read-based check separates cluster-admin from cluster-reader, because
  # cluster-reader may read everything. `update clusterrolebindings` does. The dashboard never
  # writes; a SubjectAccessReview only asks.
  usageAdminSar:
    apiGroup: rbac.authorization.k8s.io
    resource: clusterrolebindings
    verb: update
    namespace: ""
```

`config.userActivity.visibility: all` is **kept, unchanged**, as the blunt override.

**Precedence**, in order:

1. `config.userActivity.visibility: all` → every admitted reader sees all rows. Today's escape
   hatch; do not remove it.
2. otherwise the usage tier decides: passes → all rows; anything else → the reader's own.
3. no identity → 403, exactly as now (`require_viewer`).

**Fail closed.** Any indeterminate answer — no resolver, a raised exception, a junk tier string,
an API-server error — serves the reader's own rows. Never the wide set. Same discipline as
`viewer_scope`: only the exact string `all` widens.

**Cache.** Reuse the existing 60s per-viewer TTL, in a resolver instance SEPARATE from the wide
tier's. It is a different question about the same person and must not share a cache entry.

## What must not regress

- `cluster-reader` keeps `scope: all` on Groups, Access granted, RBAC policy, Namespace audit and
  Logins. The auditor persona is the point of this design, not a side effect.
- `cluster-admin` gets `scope: all` on Usage.
- A self-tier reader still gets their own rows on Usage and 403 on the two gated endpoints.
- `/api/clusters` stays reachable for every reader; `operator_configs` stays withheld at self.
- The proxy-off install is untouched: wide view plus the startup warning.
- The two admin-tier tabs (Overview, RBAC policy) still say "For administrators only" exactly once
  and still name no role, check, chart key or README. Access granted is narrowed rather than
  refused since 0.10.0: a plain reader sees the bindings that reach them through their groups.

## Tests required

1. Usage at the usage-admin tier → `scope: all`, every row, aggregates present.
2. Usage for a reader who passes the WIDE check but fails the USAGE check — the `cluster-reader`
   persona — → `scope: self` on Usage while `/groups` is still `scope: all`. This is the test that
   proves the two tiers are independent, and it is the one that matters most.
3. Usage for a self-tier reader → their own rows only.
4. Fail closed: resolver raises, resolver returns junk, no resolver at all → `self` each time.
5. `config.userActivity.visibility: all` still widens for everyone, usage tier irrelevant.
6. No identity → 403.
7. Chart: `usageAdminSar` threads into the ConfigMap; a miscased or versioned shape fails the
   render, matching `adminSar`'s existing guards; the default render still carries the
   `system:auth-delegator` grant and still disappears when `visibility.enabled=false`.
8. The two SAR caches are independent — a decided usage tier must not answer for the wide tier.

## Docs to update in the same pass

`docs/REQUIREMENTS_per_user_visibility.md` (the endpoint table row for `/api/dashboard/activity`,
which currently reads "already self-scoped by default"), `docs/SPEC_per_user_visibility.md`,
`local-development/API.md` (the `scope`/`viewer` section — Usage now has its own threshold, which
a client reading `scope` needs to know), and `charts/group-sync-dashboard/README.md` (the passage
arguing there is deliberately no admins-only tier for Usage is now superseded — keep its reasoning
as the record of WHY the bar is higher rather than deleting it).
