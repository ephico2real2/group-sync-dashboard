# Unmanaged-grant discovery — design and invariants

The dashboard finds grants that bypass the policy system and publishes them to the pod log,
the RBAC policy tab and the API. It writes nothing to any cluster. The rendered ClusterRole
holds `get` and `list` on `rolebindings`/`clusterrolebindings` and no verb that can change
either (`charts/group-sync-dashboard/templates/rbac.yaml:55-57`), and the cluster client has no
write method at all (`local-development/gsd/kube.py:226-237`).

A binding is `unmanaged` when it names an operator-synced group and carries neither the policy
operator's `rbac.ocp.io/config-source` label nor an `rbac.ocp.io/unmanaged-exception`
annotation — somebody granted access by hand, outside the governance system, and nothing else
on the cluster reports it. On the reference cluster 77 of 85 convention bindings carry the
label, and the handful that do not are exactly the hand-made ones, including a
ClusterRoleBinding granting `cluster-admin` that nothing manages
(`local-development/tests/test_rbac.py:236-241`).

**Until 2026-08-03 this document described a write path.** The feature stamped the objects it
classified `unmanaged` with a label and two annotations, so an auditor could select them with
`oc get ... -l rbac.ocp.io/unmanaged=true`. It was enabled on a live cluster, it wrote nothing,
and it can never write. That measurement is the next section, because it is the reason this
design is shaped the way it is rather than a caveat attached to the end of it.

## What the cluster measured

**Live OpenShift cluster, `annotate` mode enabled.** The dashboard logged `plan — stamp 4,
heal 0` and then **0 of 4 landed**.

Kubernetes applies privilege-escalation prevention to RBAC objects: to write one, the writer
must already hold every permission that object grants. This holds for a metadata-only merge
patch that touches no rule and no subject — the check is on the object, not on the fields being
changed. The API server refused in these terms, from the pod log:

```
clusterrolebindings "demo-cluster-audit-crb" is forbidden: user
"system:serviceaccount:group-sync-dashboard:group-sync-dashboard" is attempting to grant
RBAC permissions not currently held: {APIGroups:[""], Resources:[...], Verbs:[...]}
```

`oc auth can-i patch clusterrolebindings --as=<the ServiceAccount>` answered **yes** throughout,
and `SelfSubjectAccessReview` returned `allowed: true`. The RBAC grant was correct and
irrelevant: the escalation check runs after authorization and refuses anyway. Anyone reasoning
from `can-i` alone will conclude the write works.

The 4 refusals included a ClusterRoleBinding granting nothing but `view` and a namespaced
RoleBinding granting `view`. On OpenShift `view` alone covers dozens of resources a read-only
ServiceAccount does not hold — the refusal named `appliedclusterresourcequotas`, `bindings`,
`buildconfigs` and more — so the low-privilege end was out of reach too. The earlier reading
that `annotate` would at least reach the narrow bindings was itself optimistic: it reached
nothing.

**How large a "special role" would have to be**, since that is the obvious next question. The
API server enumerates what it wants. To label the most harmless binding on the cluster — a
ClusterRoleBinding granting nothing but `view` — it demanded **175 additional rule sets**. For
the `cluster-admin` binding it demanded one: `{APIGroups:[*], Resources:[*], Verbs:[*]}`.

So the three available shapes were 175+ rules of Kubernetes internals per binding class,
`escalate` on `rbac.authorization.k8s.io` (the verb that switches the check off — cluster-admin
under a smaller name), or cluster-admin outright. Each gives a read-only auditing tool the most
privilege on precisely the most dangerous grants, so a compromise of this pod becomes a cluster
compromise, in exchange for a convenience label. All three were refused.

The write path was therefore removed rather than documented as a limitation: the two patch
methods from the cluster client (`kube.py:226-237` records what they were), the conditional
`patch` grant from the ClusterRole (`rbac.yaml:33-47`), and the `annotate` mode itself
(`config.py:277-293`). What remains is the half that was always the deliverable — the finding.

One artefact of the write is worth keeping in mind because it wasted an operator's time. The
refusal was being reported as "the token lacks `patch` on rolebindings/clusterrolebindings"
while `can-i` said yes, so the suggested remedy was a grant the ServiceAccount already had.
There is now one 403 path left in the client and it names listing
(`kube.py:257-261`), so that particular misreport cannot recur.

## What is published

`log` mode emits one line per object plus a summary, on a refresh that runs every 300s
(`config.py:181`), on the lease holder, after the cycle's rows are stored
(`poller.py:312-318`). A cycle with nothing to report emits nothing at all: the summary is
guarded on the plan being non-empty (`poller.py:331`), so a clean cluster is silent rather than
producing a zero every five minutes.

The summary, at INFO (`poller.py:331-339`):

```
crc-local: unmanaged-grant discovery — 4 outside the policy system, 0 resolved since the
last cycle. Full detail: GET /api/clusters/crc-local/bindings/findings
```

Each finding, at **WARNING** (`poller.py:341-356`):

```
UNMANAGED GRANT DISCOVERED — crc-local: ClusterRoleBinding demo-cluster-admin-crb
(cluster-wide) grants cluster-admin to group app-ocp-rbac-demo-cluster-admin, outside the
policy system (no config-source label, no exception annotation)
```

WARNING rather than INFO for two reasons, both stated at `poller.py:345-348`: the poller emits
INFO for every routine HTTP call, so a finding at INFO is buried by the traffic around it, and a
log pipeline needs a level to filter on. The fixed prefix is there to be alerted on.

Each resolution, at INFO (`poller.py:358-374`):

```
unmanaged grant RESOLVED — crc-local: RoleBinding demo-prod/demo-prod-audit-rb is no longer
outside the policy system (adopted, annotated as an exception, or its group left management).
Its rbac.ocp.io/unmanaged label is now stale: oc label rolebinding -n demo-prod
demo-prod-audit-rb rbac.ocp.io/unmanaged-
```

The line names the object, what it grants, to whom, and why that is a finding, so it stands
alone as evidence without opening the dashboard. That is what the `evidence` dict on the plan
exists for (`audit.py:23-32`, `audit.py:77-81`); only the groups whose rows were classified
unmanaged are cited, because a binding can name two groups and be unmanaged for only one, and
citing the managed one would send a reader to inspect a grant that is fine
(`audit.py:62-68`, tested at `test_audit_stamp.py:144-157`).

**The summary's first number is not the cluster's total.** It counts the objects listed this
cycle, which excludes any already carrying the `rbac.ocp.io/unmanaged` label (I3 below) and any
deferred by the per-cycle cap, which is reported separately in the same line. The cluster-wide
set is `GET /api/clusters/{id}/bindings/findings` (`api.py:416`), which the summary points at
for exactly this reason.

## How a finding is suppressed

A cluster admin annotates the object by hand:

```bash
oc annotate clusterrolebinding <name> \
  rbac.ocp.io/unmanaged-exception="approved in TICKET-123, break-glass access"
```

The dashboard reads that annotation (`kube.py:68`, `kube.py:514`) and stops classifying the
binding as unmanaged (`store.py:1189`), so it leaves the log, the RBAC policy tab and the API.
Tested at `test_rbac.py:274-281`.

This is separation of duties rather than a limitation. The justification lives next to the
object it describes, where the next person to read that binding will find it, and the
acknowledgement is performed by somebody who holds the privileges — which the dashboard
deliberately does not. There is no dashboard-side allowlist, so a finding cannot be silenced by
whoever happens to run the dashboard.

The `rbac.ocp.io/unmanaged` label is still **read** and never written (`kube.py:78`,
`kube.py:515`), and served per row as `audit_stamped` (`store.py:1236`). If an admin or a CI job
applies it, the dashboard notices, and when the binding stops being unmanaged it reports
`unmanaged grant RESOLVED` with the command that removes the now-stale label. The label is an
input to this system now, not an output of it.

## Invariants

Each clause below is either a constraint the code still enforces, with the test that holds it,
or a retired one. The retired ones are kept and marked, because a reader who knows the old shape
of this feature needs to be able to find out what happened to it.

**I1 — Write set. RETIRED: there is no write.** The clause used to bound the patch body to
three metadata keys. What replaces it is not a bound on writing but its absence: no write verb
in the ClusterRole (`rbac.yaml:55-57`), no write method on the client (`kube.py:226-237`), and
a GET-only HTTP API enforced by `test_api_contract.py:229-240`. Measured by rendering the chart
at `mode` = `off`, `log`, `annotate`, an unrecognised word and the empty string: **zero
occurrences of `"patch"`** in each of the five renders, and the only write verbs anywhere in the
chart are `get`/`create`/`update` on the leader-election Lease. No test asserts this today; the
check is `helm template ... | grep '"patch"'`, and it belongs in the chart tests.

**I2 — Finding set.** Unchanged in substance, renamed from "Target set" because nothing is
targeted now. An object is a finding only if its group resolves, its group is operator-synced,
the binding carries no `config-source` label, the binding carries no exception annotation, and
the cluster demonstrably uses the policy operator — some managed binding exists, so a cluster
that has never heard of `config-source` labels reports zero findings rather than sixty. All five
conditions are one SQL `CASE` (`store.py:1188-1194`), which is also what the API and the counts
read, so the log and the UI cannot disagree about what a finding is. Tests:
`test_audit_stamp.py:28-50` and `test_rbac.py:233-302`.

**I3 — Announced once while the label is absent.** Was "Idempotent", and the reason changed
completely. An object already carrying `rbac.ocp.io/unmanaged=true` is left out of the discovery
list (`audit.py:70`). There is no longer a patch to be idempotent about; what this now governs
is the log — a hand-applied or CI-applied label stops the per-cycle WARNING for that object
while leaving the finding in the API and the UI, and the RESOLVED line still fires when it stops
being unmanaged. The immutable `detected-at` annotation died with the write, so nothing records
how long a grant has existed unacknowledged; the first-seen time is now whatever the log pipeline
retains. Stated plainly as a cost: an unlabelled finding is re-announced every 300s, because the
plan is computed fresh each cycle and has no memory of the last one. That is what makes the line
alertable, and it also means the log repeats until the grant is adopted, annotated or labelled.
Test: `test_audit_stamp.py:53-56` (its assertion holds; its stated reason, protecting the
first-detected timestamp, no longer applies).

**I4 — Resolution is reported, not performed.** Was "Self-healing selection". An object that
carries the label and is no longer classified unmanaged by any of its rows produces the RESOLVED
line (`audit.py:71`, `poller.py:358-374`). The multi-subject rule is the one worth knowing: a
binding naming two groups resolves only when *no* row is unmanaged, so one acknowledged group
does not close a finding about the other. The dashboard cannot remove the label, so the line
repeats each cycle while the stale label remains and carries the `oc label ...
rbac.ocp.io/unmanaged-` command that ends it. Tests: `test_audit_stamp.py:59-76`.

**I5 — Mode-gated, and an unrecognised value fails to `off`.** `config.unmanagedAudit.mode` is
`off` or `log` (`config.py:265-295`). `off` runs no discovery code at all (`poller.py:317`).
`annotate` downgrades to `log` with a warning at settings load, deliberately not to `off`, which
would silently take the findings away from a cluster that had it set (`config.py:277-293`).
Anything else is `off`, because a typo must not enable a mode (`config.py:294-295`).

What changed, twice over. The mode no longer affects RBAC — and the chart's default moved from
`off` to `log`. `off` was the right default while this could write, because a default that
patches cluster objects has to be opted into; with nothing written, the only thing it buys is a
governance tool that has found a hand-made `cluster-admin` grant and declines to mention it. A
cluster with no unmanaged grants logs nothing (`poller.py:331`), so the new default costs nothing
where there is nothing to report.

Note that the two defaults differ, which matters when reading a running instance. The chart ships
`config.unmanagedAudit.mode: log`, so a Helm install discovers by default. The **application**
still defaults to `off` when the setting is absent altogether — a bare `Settings()`, or a
ConfigMap without the key (`config.py:223`, `config.py:273`, asserted by
`test_audit_stamp.py:121-122`) — which is what a hand-rolled deployment or a local run gets. To
know which one an instance is in, read the rendered `unmanagedAuditMode`
(`templates/configmap.yaml:27`), not either default.

Measured — the only difference between the `off`, `log`, `annotate` and unrecognised-word renders
is the one string in the ConfigMap and the checksum annotation that follows from it; every RBAC
object is identical. Tests: `test_audit_stamp.py:94-122`.

**I6 — Bounded log volume.** Was "Bounded blast radius", and the blast radius it was named for
is gone. `maxPerCycle` (default 20) caps how many findings are listed individually per refresh;
the remainder is counted and reported as "not yet listed" in the summary rather than dropped, so
the true total is recoverable from the line (`audit.py:72-74`, `poller.py:337`). The cap takes a
sorted prefix, so deferred findings converge instead of being re-deferred forever. Resolutions
are never capped: a closed finding must not queue behind new ones. A misclassification bug costs one
screenful of log per 300s cycle rather than a cluster's worth. Tests:
`test_audit_stamp.py:79-91`, `test_audit_stamp.py:72-76`.

**I7 — One announcer, in the default shape.** Was "Single writer", and it still constrains
something real. The discovery runs on the binding-refresh path, reached only by the lease
holder: a standby replica skips the cycle (`poller.py:442-455`) before it can get to
`refresh_bindings` (`poller.py:486-492`). At the chart's defaults — `replicaCount: 1` with
`leaderElection.enabled: true` — that stops an overlapping old and new pod, from a `Recreate`
rollout, a partitioned node or a `kubectl scale`, announcing the same grant twice.

Above one replica it does not hold, and the cost is worth stating rather than omitting.
`replicaCount > 1` requires `leaderElection.enabled=false` or the chart refuses to render
(`templates/deployment.yaml:1-2`), because each pod then keeps its own database and must poll
for itself. Every pod runs the discovery, so a log pipeline alerting on the
`UNMANAGED GRANT DISCOVERED` prefix sees one copy per replica. That is a property of the
multi-pod shape, not something the discovery can fix from its side. `test_leader.py` covers the
elector; nothing tests this gate specifically.

**I8 — Failure isolation. RETIRED as written**, because no patch can fail. Two weaker
properties remain and they are not the same claim. The discovery runs last in the refresh, after
the cycle's rows are committed (`poller.py:312-318`), so nothing it does can cost the refresh its
data. And the call is wrapped, so an exception in the plan or the logging cannot kill the poll
thread (`poller.py:487-494`).

## Races considered

**A binding mid-migration into the policy system** — created before its `config-source` label
lands — is reported for the window. The old answer was I4: the label came off the next cycle and
the annotations recorded that the window existed. That answer is gone, because a log line cannot
be withdrawn. So the honest position is that a migration produces a false-positive WARNING for
each 300s cycle the window spans, and nothing retracts them. The finding stops being reported the
cycle after the label lands, with no RESOLVED line unless somebody had labelled the object, since
resolution requires the label to be present (`audit.py:71`). The mitigation is in the line
itself: it names the role and the group, so a human reading it during a known migration can see
what it is.

**Stale classification after a failed group poll** — unchanged, and the reasoning survives
because it was never about writing. A failed poll returns before it touches `group_state`
(`poller.py:97-100`), so findings are computed against the last successful poll's
`group_state`/`managed_group_seen` (`store.py:1198-1204`) and a transient failure changes no
classification at all. When a group genuinely disappears, the binding becomes `dangling`, which
outranks `unmanaged` in the same `CASE` (`store.py:1176-1177`), so a vanished group can never
manufacture an unmanaged finding. Tested at `test_rbac.py:290-302`.

**A grant created and removed between refreshes is never reported.** This is a sampler, not a
watch: the ClusterRole holds no `watch` verb and the interval is 300s. A hand-made binding that
exists for less than one interval can go unseen. That is accepted: the feature exists to find
grants that persist, and closing the gap would cost a `watch` verb and a standing connection per
cluster to catch grants that have already stopped existing before anyone could act on them.

## Rollout

There is no staged rollout left. It used to exist because the last step took a write grant, and
`log` was the rehearsal for it; now `log` is the feature and it needs no RBAC change — the
ClusterRole is the same object in both modes, so the switch is a ConfigMap change and nothing
else. The deployment's `checksum/config` annotation (`templates/deployment.yaml:45`) rolls the pod
so the new value is read, since settings load once at process start (`api.py:872`).

What to check on first enabling it, in order. Read the rendered `unmanagedAuditMode`
(`templates/configmap.yaml:27`) so you know which mode the pod is actually in. Wait one binding
refresh (300s) and compare the summary line against
`GET /api/clusters/{id}/bindings/findings` — remembering that the summary's count excludes
already-labelled objects and the capped remainder. Confirm each WARNING names a binding you can
verify is hand-made, then annotate the deliberate ones with
`oc annotate ... rbac.ocp.io/unmanaged-exception=<why>` and treat what is left as work.

Set `off` if the findings are known and being worked through and the log noise is unwanted; the
findings stay in the UI and the API either way, and `off` silences only the log. If `annotate` is
still set anywhere — an old `environments/` file, a stale ArgoCD Application — the pod logs the
removal warning once at startup and runs as `log`.

## The cost, stated plainly

What was lost with the write, and none of it is recovered elsewhere:

`oc get rolebindings,clusterrolebindings -A -l rbac.ocp.io/unmanaged=true` no longer returns
anything the dashboard put there. Selecting the current findings from the cluster with a label
selector was the whole point of stamping, and it is gone; the equivalent is an API call. Nothing
records first detection on the object, so "how long has this existed unacknowledged" is now a
question for the log pipeline. And suppressing a finding costs a cluster-admin action on the
object instead of a setting in the dashboard.

What was gained is checkable in one command: the ServiceAccount holds no verb that can change
what any binding grants, in any configuration of the chart. That is a stronger statement than the
old I1 — which argued from the contents of a patch body that the grant permitted but the code
chose not to write — and it is verified by rendering the chart rather than by reading the
application.

One naming artefact remains. The decision module is still called `audit.py` and its function
`plan_audit_stamps`, returning a `StampPlan` whose lists are `stamp` and `unstamp`. Read them as
"newly discovered" and "resolved"; the names predate the removal and the tests are indexed to
them.
