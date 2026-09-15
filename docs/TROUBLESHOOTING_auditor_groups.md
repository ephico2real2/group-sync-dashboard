# Troubleshooting — auditor groups, `createLocal`, and the LDAP GroupSync

Operator-facing runbook for the `rbacAuditors` feature
(`docs/DESIGN_reporting_auditors_and_ns_selector.md` §2) when the auditor Group is **also** managed by
an LDAP GroupSync. The mechanism and the evidence are in
`docs/FINDINGS_auditor_group_ldap_sync_interaction.md`; this page is the "what do I do" version, in the
order you hit the symptoms.

## TL;DR

- An auditor group that a directory syncs must be bound, **not** re-created, by this chart:
  `rbacAuditors.groups[].createLocal: false`. The ClusterRoleBinding names the group **by name**, so the
  read-only audit role attaches the moment the operator creates the Group.
- `createLocal: true` is only for a group name that **no** GroupSync filter matches (a purely local
  group). For a synced name it collides — and the chart now stops that collision with a clear error.

## Symptom 1 — `helm install/upgrade` fails naming the group

```
Error: UPGRADE FAILED: execution error at (…/templates/rbac-auditors.yaml): rbacAuditors: Group
"app-ocp-rbac-groupsync-ns-auditor" already exists on the cluster (LDAP-synced from
openldap-service.ldap-testing.svc.cluster.local) and is not owned by this Helm release. … Set
rbacAuditors.groups[] createLocal=false for "app-ocp-rbac-groupsync-ns-auditor" …
```

**Cause.** `createLocal: true` for a group that already exists under another owner (an LDAP sync, or a
hand-made group). The chart's collision guard (`templates/rbac-auditors.yaml`) caught it before Helm's
own, less specific, ownership error.

**Fix.** Do exactly what the message says — set `createLocal: false` for that group and re-run:

```yaml
rbacAuditors:
  enabled: true
  groups:
    - name: app-ocp-rbac-groupsync-ns-auditor
      createLocal: false        # the directory owns the Group; the chart only binds it
```

**Note on the guard.** It uses Helm `lookup`, which returns nothing during `helm template` and
`helm install --dry-run` — so it fires only on a **real** install/upgrade, which is when the collision
would actually occur. The account running Helm therefore needs `get` on `groups.user.openshift.io`
(cluster-admin already has it). In a pure GitOps render that never talks to the cluster, the guard
cannot see the group; there `createLocal: false` is a discipline, not something the chart can enforce.

**Note on release state.** A guard failure aborts at **render time**, before anything is applied, so the
running release is unchanged — but Helm still records a **failed revision**. `helm status` will read
`failed`; the deployed objects are still the previous good revision. Recover with a clean
`helm upgrade … --set rbacAuditors.groups[0].createLocal=false` (it supersedes the failed revision) or
`helm rollback group-sync-dashboard`.

## Symptom 2 — the whole `app-ocp-rbac-*` group family stopped syncing

You created the auditor group with `createLocal: true` on an older chart (before the guard), or by
hand, and now **no** `app-ocp-rbac-*` group updates — new members, departures, new groups all stall.

**Cause.** The un-adoptable local group errors the **entire** GroupSync cycle. The operator sync is
all-or-nothing per CR: one group it cannot reconcile fails the run, and `lastSyncSuccessTime` freezes.

**Diagnose.**

```sh
# Frozen timestamp = the CR has not completed a cycle since the collision:
oc get groupsync app-ocp-rbac-group-groupsync -n group-sync-operator -o jsonpath='{.status.lastSyncSuccessTime}'

# The operator names the offending group and the guard it tripped:
oc logs -n group-sync-operator deploy/group-sync-operator-controller-manager -c manager \
  | grep -E "Failed to Complete Sync|did not match sync host"
```

**Fix.** Remove the colliding local Group so the operator can own it, then force a sync:

```sh
oc delete group app-ocp-rbac-groupsync-ns-auditor      # the local, non-synced object
# then trigger a cycle (patch .spec so the operator reconciles), or wait for the schedule:
setup-local-ldap-testing/60-force-groupsync.sh app-ocp-rbac-group-groupsync group-sync-operator
```

`lastSyncSuccessTime` advances and the family syncs again; the operator recreates the auditor group,
now with its own ownership markers and the LDAP members.

## The metadata that decides ownership

The operator will only touch a Group that carries **its** ownership markers. These are what to inspect
when a group is "stuck" or when you are reasoning about who owns it:

| Marker | On the object | Set by | Meaning |
|---|---|---|---|
| `openshift.io/ldap.host` (label) | the sync host | the operator | which directory host owns this group. **Mismatch is a hard sync error.** |
| `openshift.io/ldap.url` (annotation) | host:port | the operator | the same, with port. **Mismatch is a hard sync error.** |
| `group-sync-operator.redhat-cop.io/sync-provider` (label) | `<CR-name>_ldap` | the operator | which GroupSync CR owns it. Absent ⇒ the operator **skips** the group (soft). |
| `openshift.io/ldap.uid` (annotation) | the group DN | the operator | maps the OpenShift Group to its LDAP entry. |
| `meta.helm.sh/release-name` (annotation) | the release | Helm | which Helm release owns the object. The chart's guard compares this to decide "mine vs not". |
| `group-sync-dashboard/managed: local` (annotation) | — | this chart | marks a `createLocal` Group as chart-made and **not** to be given to a sync. |

Inspect them:

```sh
oc get group <name> -o jsonpath='{.metadata.labels}{"\n"}{.metadata.annotations}{"\n"}users={.users}{"\n"}'
```

A group with `group-sync-operator.redhat-cop.io/sync-provider` set and **no** `meta.helm.sh/release-name`
is operator-owned — bind it (`createLocal: false`), never re-create it.

## Advanced — making the chart SEED a group the sync then adopts (discouraged)

It is possible to have the chart create a local group that the operator later adopts, by stamping the
full marker set (`openshift.io/ldap.host` label + `openshift.io/ldap.url` annotation +
`group-sync-operator.redhat-cop.io/sync-provider` label + `openshift.io/ldap.uid` annotation). When all
are correct the next sync overwrites the group's members from LDAP and keeps the Helm labels
(`docs/FINDINGS_auditor_group_ldap_sync_interaction.md`, Finding 3).

Do not do this by default. Two of those values — the sync **host:port** and the GroupSync **CR name** —
belong to the group-sync-operator's deployment, not to this dashboard; a wrong host is not a warning but
a hard error that freezes the whole family's sync. Bind by name (`createLocal: false`) and let the
operator own the object; seed-and-adopt is an explicit, operator-driven exception, never a silent
default.
