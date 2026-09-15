# Findings — the auditor group vs the LDAP GroupSync: takeover, denial-of-sync, and adoption

Validated live on CRC, 2026-09-14, against the deployed chart 0.24.0 (application 0.19.0, image
`0.19.0-3e07b71ee0`) and the lab's group-sync-operator + OpenLDAP (`ldap-testing`). It answers a
question the reviewed auditor design (`docs/DESIGN_reporting_auditors_and_ns_selector.md` §2) raised but
did not test on a running cluster: **what happens when the chart's `rbacAuditors … createLocal: true`
local Group collides with a same-named group synced from LDAP** — the "hostile takeover" case — and
whether the chart could instead **stamp** a local group so the sync adopts it cleanly.

Every claim below is a measured `oc`/operator-log observation; the commands are in the appendix.

## The setup

- The chart's auditor feature (#100) binds a group to a least-privilege, read-only ClusterRole
  (`group-sync-dashboard-report-auditor`: `get,list` on `user.openshift.io/{users,groups}` and
  `rbac.authorization.k8s.io/{roles,rolebindings,clusterroles,clusterrolebindings}`). The
  ClusterRoleBinding names the group **by name**, so it works no matter who creates the Group object.
- `rbacAuditors.groups[].createLocal: true` makes the chart also render a **local** OpenShift Group;
  `false` renders **only** the binding and lets something else (an LDAP sync) own the Group.
- The lab's `GroupSync/app-ocp-rbac-group-groupsync` syncs every `cn=app-ocp-rbac-*` group from
  `ou=Groups,dc=ephico2real,dc=com` over `ldaps://openldap-service.ldap-testing.svc.cluster.local:636`,
  `prune: true`, every 30 min. Our auditor group name `app-ocp-rbac-groupsync-ns-auditor` **matches
  that filter** — so the two systems contend for the same Group object.

## Finding 1 — the LDAP sync does NOT take over a foreign local group (a real safety guard)

With `createLocal: true`, the chart made a Helm-owned local Group: `app.kubernetes.io/managed-by: Helm`,
annotation `group-sync-dashboard/managed: local`, `users: null`, and **no** `openshift.io/ldap.*`
markers. Creating the same-named group in LDAP (members `bob.wilson`, `jane.smith`) and forcing the sync
produced:

```
group "app-ocp-rbac-groupsync-ns-auditor": openshift.io/ldap.host label did not match sync host:
wanted openldap-service.ldap-testing.svc.cluster.local, got ""   → Failed to Complete Sync
```

The operator only reconciles a Group that already carries the ownership marker it stamps on groups it
created (`openshift.io/ldap.host`). A locally-created group lacks it, so the sync **refuses to overwrite
it** — the same protection `oc adm groups sync` uses. The Helm group stayed `users: null`, untouched.
**An actor who controls LDAP cannot silently inject members into a same-named cluster-local RBAC group.**

## Finding 2 — but the collision is a denial-of-sync for the WHOLE group family

The refusal is not a quiet skip: it is a hard error that fails the **entire** CR's sync cycle. With the
un-adoptable group present, `GroupSync/app-ocp-rbac-group-groupsync` reported `Failed to Complete Sync`
and `lastSyncSuccessTime` **froze** (stuck at `19:30:15Z` across repeated forced syncs). Every other
`app-ocp-rbac-*` group — additions, departures, new groups — **stopped syncing** while the one collision
persisted. A chart-created local group whose name matches an active sync filter is therefore a
cluster-wide outage of that group family's RBAC updates, not a local-only problem.

## Finding 3 — a fully-stamped local group IS adopted; the guard is a three-marker chain

Stamping the local group to look like one the operator owns lets the sync adopt it. Discovered marker by
marker (each forced sync advanced to the next guard), with a **bogus member `eve.attacker`** in the
local group to make adoption unambiguous:

| Order | Marker | Kind | Value it must equal | On mismatch |
|---|---|---|---|---|
| 1 | `openshift.io/ldap.host` **label** | hard | the sync host (`…svc.cluster.local`) | **errors the whole CR sync** |
| 2 | `openshift.io/ldap.url` **annotation** | hard | host **:port** (`…:636`) | **errors the whole CR sync** |
| 3 | `group-sync-operator.redhat-cop.io/sync-provider` **label** | soft | `<CR-name>_<provider>` (`app-ocp-rbac-group-groupsync_ldap`) | group **skipped**, rest of the sync succeeds |
| — | `openshift.io/ldap.uid` **annotation** | key | the group DN (`cn=…,ou=Groups,dc=…`) | operator can't map it to the LDAP entry |

Only with **all** of them did the operator adopt the group: `users` went `["eve.attacker"]` →
`["bob.wilson","jane.smith"]`, `openshift.io/ldap.sync-time` was stamped, and the "Groups Created or
Updated" count rose 42 → 43. The Helm labels/annotations were **preserved** — the operator manages
*membership*, Helm still owns the object lifecycle. This is a layered design: markers 1–2 (host/url) are
hard so a *wrong* host can never let a foreign sync take a group; marker 3 (provider) is soft so a group
that is simply "not mine" is left alone rather than failing the run.

## What this means for the chart

1. **Default to `createLocal: false` for any group a directory syncs.** The binding names the group by
   name and works the moment the operator creates it; the chart never contends for the object. This is
   the reviewed design's default and the live evidence confirms it: with `createLocal: false` the group
   synced cleanly (`users: ["bob.wilson","jane.smith"]`, `managed-by` empty, `sync-provider` set) and
   `lastSyncSuccessTime` advanced.
2. **`createLocal: true` is safe only for a name NO sync filter matches** — a genuinely local group. For
   a name inside a sync filter it is at best a no-op the operator skips, and at worst (a bare or
   partially-stamped group) a **denial-of-sync** for the whole family (Finding 2).
3. **Chart-stamped hand-off is possible but fragile — do not make it the default.** To have the chart
   seed a group the sync then adopts, it must stamp all four markers, and two of the four values are
   **not the dashboard's to know**: the sync **host:port** and the **GroupSync CR name**
   (`sync-provider = <CR-name>_ldap`) belong to the group-sync-operator's deployment, not to the
   dashboard. A wrong host/url is not a warning — it is a hard error that stops the whole family's sync.
   So stamping couples the dashboard chart to another operator's topology and turns a typo into an
   outage. If it is ever offered, it must be an explicit opt-in with the operator supplying the CR name
   and LDAP URL, never derived silently.

### On "add the auditor group to values.yaml as a default"

Ship the **group name** as the documented default entry so an operator who enables the feature gets it
without retyping, but keep `rbacAuditors.enabled: false` (the feature stays opt-in — flipping the
default on would also break `KEPT_OFF` in `test_values_defaults.py`) and keep `createLocal: false` (per
#1). The operator enables the stanza; LDAP owns the group; the chart binds it. This is a chart change
and goes through its own PR + two-reviewer pass.

## Live end state (verified)

- LDAP: `cn=app-ocp-rbac-groupsync-ns-auditor,ou=Groups,dc=ephico2real,dc=com` (`groupOfNames`), members
  `uid=bob.wilson`, `uid=jane.smith`; `bob.wilson` added to the login gate `app-ssb-autobahnusers`
  (`groupOfUniqueNames`), password set for the walk.
- OpenShift: the group is operator-owned (`sync-provider=app-ocp-rbac-group-groupsync_ldap`, no Helm
  label), bound by `group-sync-dashboard-ra-b78c05817c9d` to `group-sync-dashboard-report-auditor`.
- Deployment: chart 0.24.0 with `rbacAuditors.enabled: true`, `createLocal: false`.

## Appendix — the commands

```sh
# The ownership marker a synced group carries (the guard the operator checks):
oc get group app-ocp-rbac-alpha-ns-audit -o jsonpath='{.metadata.labels}'
#   openshift.io/ldap.host=openldap-service.ldap-testing.svc.cluster.local
#   group-sync-operator.redhat-cop.io/sync-provider=app-ocp-rbac-group-groupsync_ldap

# Create the auditor group + members in LDAP (admin bind, from inside the openldap pod):
POD=$(oc get pods -n ldap-testing -l app=openldap-server -o jsonpath='{.items[0].metadata.name}')
oc exec -i -n ldap-testing "$POD" -- ldapadd -x -H ldap://localhost:389 \
  -D cn=admin,dc=ephico2real,dc=com -w admin123 <<'LDIF'
dn: cn=app-ocp-rbac-groupsync-ns-auditor,ou=Groups,dc=ephico2real,dc=com
objectClass: groupOfNames
cn: app-ocp-rbac-groupsync-ns-auditor
member: uid=bob.wilson,ou=People,dc=ephico2real,dc=com
member: uid=jane.smith,ou=People,dc=ephico2real,dc=com
LDIF

# Force a sync now (patches .spec so generation advances; polls lastSyncSuccessTime):
setup-local-ldap-testing/60-force-groupsync.sh app-ocp-rbac-group-groupsync group-sync-operator

# The denial-of-sync signature (Finding 2) and the adoption signature (Finding 3) are in the operator log:
oc logs -n group-sync-operator deploy/group-sync-operator-controller-manager -c manager | \
  grep -E "Failed to Complete Sync|Provider Label Did Not Match|Sync Completed Successfully"
```
