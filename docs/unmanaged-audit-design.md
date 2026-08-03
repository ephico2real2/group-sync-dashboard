# Unmanaged-grant discovery — design and invariants

The dashboard finds grants that bypass the policy system and publishes them to the pod log,
the RBAC policy tab and the API. This feature writes nothing, and the dashboard's only write
anywhere is its own leader-election Lease — its coordination object, not anything it observes.
The rendered ClusterRole holds `get` and `list` on `rolebindings`/`clusterrolebindings` and no
verb that can change either (`charts/group-sync-dashboard/templates/rbac.yaml#clusterrolebindings`), and the cluster client has no
write method at all (`local-development/gsd/kube.py#UNREACHABLE`).

A binding is `unmanaged` when it names an operator-synced group and carries neither the policy
operator's `rbac.ocp.io/config-source` label nor an `rbac.ocp.io/unmanaged-exception`
annotation — somebody granted access by hand, outside the governance system, and nothing else
on the cluster reports it. On the reference cluster 77 of 85 convention bindings carry the
label, and the handful that do not are exactly the hand-made ones, including a
ClusterRoleBinding granting `cluster-admin` that nothing manages
(`local-development/tests/test_rbac.py#TestUnmanagedFinding`).

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
methods from the cluster client (`kube.py#UNREACHABLE` records what they were), the conditional
`patch` grant from the ClusterRole (`rbac.yaml#NO WRITE VERB`), and the `annotate` mode itself
(`config.py#_audit_mode_setting`). What remains is the half that was always the deliverable — the finding.

One artefact of the write is worth keeping in mind because it wasted an operator's time. The
refusal was being reported as "the token lacks `patch` on rolebindings/clusterrolebindings"
while `can-i` said yes, so the suggested remedy was a grant the ServiceAccount already had.
There is now one 403 path left in the client and it names listing
(`kube.py#ClusterClient._get`), so that particular misreport cannot recur.

## What is published

`log` mode emits one line per object plus a summary, on a refresh that runs every 300s
(`config.py#Settings`), on the lease holder, after the cycle's rows are stored
(`poller.py#refresh_bindings`). A cycle with nothing to report emits nothing at all: the summary is
guarded on the plan being non-empty (`poller.py#refresh_bindings`), so a clean cluster is silent rather than
producing a zero every five minutes.

The summary, at INFO (`poller.py#refresh_bindings`):

```
crc-local: unmanaged-grant discovery — 4 outside the policy system, 0 resolved since the
last cycle. Full detail: GET /api/clusters/crc-local/bindings/findings
```

Each finding, at **WARNING** (`poller.py#refresh_bindings`):

```
UNMANAGED GRANT DISCOVERED — crc-local: ClusterRoleBinding demo-cluster-admin-crb
(cluster-wide) grants cluster-admin to group app-ocp-rbac-demo-cluster-admin, outside the
policy system (no config-source label, no exception annotation)
```

WARNING rather than INFO for two reasons, both stated at `poller.py#refresh_bindings`: the poller emits
INFO for every routine HTTP call, so a finding at INFO is buried by the traffic around it, and a
log pipeline needs a level to filter on. The fixed prefix is there to be alerted on.

Each resolution, at INFO (`poller.py#refresh_bindings`):

```
unmanaged grant RESOLVED — crc-local: RoleBinding demo-prod/demo-prod-audit-rb is no longer
outside the policy system (adopted, annotated as an exception, or its group left management).
Its rbac.ocp.io/unmanaged label is now stale: oc label rolebinding -n demo-prod
demo-prod-audit-rb rbac.ocp.io/unmanaged-
```

The line names the object, what it grants, to whom, and why that is a finding, so it stands
alone as evidence without opening the dashboard. That is what the `evidence` dict on the plan
exists for (`audit.py#StampPlan`, `audit.py#plan_audit_stamps`); only the groups whose rows were classified
unmanaged are cited, because a binding can name two groups and be unmanaged for only one, and
citing the managed one would send a reader to inspect a grant that is fine
(`audit.py#plan_audit_stamps`, tested at `test_audit_stamp.py#TestEvidenceIsSelfContained.test_only_the_unmanaged_group_is_evidence`).

**The summary's first number is every finding awaiting acknowledgement — not the number of
lines beneath it, and not the cluster's total.** Until 2026-08-03 it was the count actually
listed, so the per-cycle cap silently shrank it: a cluster with 500 unmanaged grants announced
"20 outside the policy system", understating a governance finding 25x in the one line an operator
escalates on. The remainder was present only as a clause the reader had to add up. The cap now
appears as `(20 listed below, 480 held back by the per-cycle cap)` beside a headline of 500, and
`test_chart_strategy.py` is not where that is enforced —
`test_audit_stamp.py::TestTheSummaryLineReportsTheTrueTotal` is, including a case that fails if
the headline reverts to the capped count.

It is still narrower than the cluster's total, in one direction only: an object already carrying
the `rbac.ocp.io/unmanaged` label is a finding but is not re-announced (I3 below), so it is in
neither number. The label gates announcement, not classification — `audit_stamped` appears
nowhere in the classifying `CASE` (`store.py#Store.user_bindings`), only in the announcement filter
(`audit.py#plan_audit_stamps`). The cluster-wide set is `GET /api/clusters/{id}/bindings/findings`
(`api.py#user_detail`), which the summary line points at for exactly this reason.

## How a finding is suppressed

A cluster admin annotates the object by hand:

```bash
oc annotate clusterrolebinding <name> \
  rbac.ocp.io/unmanaged-exception="approved in TICKET-123, break-glass access"
```

The dashboard reads that annotation (`kube.py#UNMANAGED_EXCEPTION_ANNOTATION`, `kube.py#_user_binding_views`) and stops classifying the
binding as unmanaged (`store.py#Store.user_bindings`), so it leaves the log, the RBAC policy tab and the API.
Tested at `test_rbac.py#TestUnmanagedFinding.test_the_exception_annotation_acknowledges_it`.

This is separation of duties rather than a limitation. The justification lives next to the
object it describes, where the next person to read that binding will find it, and the
acknowledgement is performed by somebody who holds the privileges — which the dashboard
deliberately does not. There is no dashboard-side allowlist, so a finding cannot be silenced by
whoever happens to run the dashboard.

The `rbac.ocp.io/unmanaged` label is still **read** and never written (`kube.py#UNMANAGED_EXCEPTION_ANNOTATION`,
`kube.py#_binding_views`), and served per row as `audit_stamped` (`store.py#Store`). If an admin or a CI job
applies it, the dashboard notices, and when the binding stops being unmanaged it reports
`unmanaged grant RESOLVED` with the command that removes the now-stale label. The label is an
input to this system now, not an output of it.

## Invariants

Each clause below is either a constraint the code still enforces, with the test that holds it,
or a retired one. The retired ones are kept and marked, because a reader who knows the old shape
of this feature needs to be able to find out what happened to it.

**I1 — Write set. RETIRED: there is no write.** The clause used to bound the patch body to
three metadata keys. What replaces it is not a bound on writing but its absence: no write verb
in the ClusterRole (`rbac.yaml#clusterrolebindings`), no write method on the client (`kube.py#UNREACHABLE`), and
a GET-only HTTP API enforced by `test_api_contract.py#test_r6_the_api_is_read_only`. Measured by rendering the chart
at `mode` = `off`, `log`, `annotate`, an unrecognised word and the empty string: **zero
occurrences of `"patch"`** in each of the five renders, and the only write verbs anywhere in the
chart are `get`/`create`/`update` on the leader-election Lease. Enforced by
`test_chart_strategy.py::TestNoPatchVerbAtAnyAuditMode`, which renders the chart at each of
`off`, `log`, `annotate`, `bogus` and `""` and asserts two things: no write verb on any RBAC
object, and no write verb anywhere in the role except on `leases`. It parses the rendered YAML
rather than grepping it — `rbac.yaml` keeps the history of the removed grant in its comments and
Helm emits those verbatim, so three lines of rendered output contain the word `patch` today and a
text search would either trip on them or be written loosely enough to miss a real regression.

**I2 — Finding set.** Unchanged in substance, renamed from "Target set" because nothing is
targeted now. An object is a finding only if its group resolves, its group is operator-synced,
the binding carries no `config-source` label, the binding carries no exception annotation, and
the cluster demonstrably uses the policy operator — some managed binding exists, so a cluster
that has never heard of `config-source` labels reports zero findings rather than sixty. All five
conditions are one SQL `CASE` (`store.py#Store.user_bindings`), which is also what the API and the counts
read, so the log and the UI cannot disagree about what a finding is. Tests:
`test_audit_stamp.py#TestI2TargetSet.test_only_unmanaged_rows_are_stamped` and `test_rbac.py#TestUnmanagedFinding`.

**I3 — Announced once while the label is absent.** Was "Idempotent", and the reason changed
completely. An object already carrying `rbac.ocp.io/unmanaged=true` is left out of the discovery
list (`audit.py#plan_audit_stamps`). There is no longer a patch to be idempotent about; what this now governs
is the log — a hand-applied or CI-applied label stops the per-cycle WARNING for that object
while leaving the finding in the API and the UI, and the RESOLVED line still fires when it stops
being unmanaged. The immutable `detected-at` annotation died with the write, so nothing records
how long a grant has existed unacknowledged; the first-seen time is now whatever the log pipeline
retains. Stated plainly as a cost: an unlabelled finding is re-announced every 300s, because the
plan is computed fresh each cycle and has no memory of the last one. That is what makes the line
alertable, and it also means the log repeats until the grant is adopted, annotated or labelled.
Test: `test_audit_stamp.py#TestI3Idempotency.test_an_already_stamped_binding_is_never_patched_again` (its assertion holds; its stated reason, protecting the
first-detected timestamp, no longer applies).

**I4 — Resolution is reported, not performed.** Was "Self-healing selection". An object that
carries the label and is no longer classified unmanaged by any of its rows produces the RESOLVED
line (`audit.py#plan_audit_stamps`, `poller.py#refresh_bindings`). The multi-subject rule is the one worth knowing: a
binding naming two groups resolves only when *no* row is unmanaged, so one acknowledged group
does not close a finding about the other. The dashboard cannot remove the label, so the line
repeats each cycle while the stale label remains and carries the `oc label ...
rbac.ocp.io/unmanaged-` command that ends it. Tests: `test_audit_stamp.py#TestI4SelfHealing.test_a_stamped_binding_no_longer_unmanaged_is_healed`.

**I5 — Mode-gated, and an unrecognised value fails to `off`.** `config.unmanagedAudit.mode` is
`off` or `log` (`config.py#_ca_cache_lock`). `off` runs no discovery code at all (`poller.py#refresh_bindings`).
`annotate` downgrades to `log` with a warning at settings load, deliberately not to `off`, which
would silently take the findings away from a cluster that had it set (`config.py#_audit_mode_setting`).
Anything else is `off`, because a typo must not enable a mode (`config.py#_audit_mode_setting`).

What changed, twice over. The mode no longer affects RBAC — and the chart's default moved from
`off` to `log`. `off` was the right default while this could write, because a default that
patches cluster objects has to be opted into; with nothing written, the only thing it buys is a
governance tool that has found a hand-made `cluster-admin` grant and declines to mention it. A
cluster with no unmanaged grants logs nothing (`poller.py#refresh_bindings`), so the new default costs nothing
where there is nothing to report.

Note that the two defaults differ, which matters when reading a running instance. The chart ships
`config.unmanagedAudit.mode: log`, so a Helm install discovers by default. The **application**
still defaults to `off` when the setting is absent altogether — a bare `Settings()`, or a
ConfigMap without the key (`config.py#Settings`, `config.py#_audit_mode_setting`, asserted by
`test_audit_stamp.py#TestI5ModeGating.test_the_default_is_off`) — which is what a hand-rolled deployment or a local run gets. To
know which one an instance is in, read the rendered `unmanagedAuditMode`
(`templates/configmap.yaml#unmanagedAuditMode`), not either default.

Measured — the only difference between the `off`, `log`, `annotate` and unrecognised-word renders
is the one string in the ConfigMap and the checksum annotation that follows from it; every RBAC
object is identical. Tests: `test_audit_stamp.py#TestI5ModeGating.test_an_unrecognised_mode_fails_safe_to_off`.

**I6 — Bounded log volume.** Was "Bounded blast radius", and the blast radius it was named for
is gone. `maxPerCycle` (default 20) caps how many findings are listed individually per refresh;
the remainder is counted and reported as "not yet listed" in the summary rather than dropped, so
the true total is recoverable from the line (`audit.py#plan_audit_stamps`, `poller.py#refresh_bindings`). The cap takes a
sorted prefix, so deferred findings converge instead of being re-deferred forever. Resolutions
are never capped: a closed finding must not queue behind new ones. A misclassification bug costs one
screenful of log per 300s cycle rather than a cluster's worth. Tests:
`test_audit_stamp.py#TestI6BlastRadius.test_stamps_are_capped_and_the_deferral_is_counted`, `test_audit_stamp.py#TestI4SelfHealing.test_healing_is_never_capped`.

**I7 — One announcer, in the default shape.** Was "Single writer", and it still constrains
something real. The discovery runs on the binding-refresh path, reached only by the lease
holder: a standby replica skips the cycle (`poller.py#Poller._maybe_backup`) before it can get to
`refresh_bindings` (`poller.py#Poller._run_cluster`). At the chart's defaults — `replicaCount: 1` with
`leaderElection.enabled: true` — that stops an overlapping old and new pod, from a `Recreate`
rollout, a partitioned node or a `kubectl scale`, announcing the same grant twice.

Above one replica it does not hold, and the cost is worth stating rather than omitting.
`replicaCount > 1` requires `leaderElection.enabled=false` or the chart refuses to render
(`templates/deployment.yaml#requires leaderElection.enabled=false`), because each pod then keeps its own database and must poll
for itself. Every pod runs the discovery, so a log pipeline alerting on the
`UNMANAGED GRANT DISCOVERED` prefix sees one copy per replica. That is a property of the
multi-pod shape, not something the discovery can fix from its side. `test_leader.py` covers the
elector; nothing tests this gate specifically.

**I8 — Failure isolation. RETIRED as written**, because no patch can fail. Two weaker
properties remain and they are not the same claim. The discovery runs last in the refresh, after
the cycle's rows are committed (`poller.py#refresh_bindings`), so nothing it does can cost the refresh its
data. And the call is wrapped, so an exception in the plan or the logging cannot kill the poll
thread (`poller.py#Poller._run_cluster`).

## Races considered

**A binding mid-migration into the policy system** — created before its `config-source` label
lands — is reported for the window. The old answer was I4: the label came off the next cycle and
the annotations recorded that the window existed. That answer is gone, because a log line cannot
be withdrawn. So the honest position is that a migration produces a false-positive WARNING for
each 300s cycle the window spans, and nothing retracts them. The finding stops being reported the
cycle after the label lands, with no RESOLVED line unless somebody had labelled the object, since
resolution requires the label to be present (`audit.py#plan_audit_stamps`). The mitigation is in the line
itself: it names the role and the group, so a human reading it during a known migration can see
what it is.

**Stale classification after a failed group poll** — unchanged, and the reasoning survives
because it was never about writing. A failed poll returns before it touches `group_state`
(`poller.py#poll_once`), so findings are computed against the last successful poll's
`group_state`/`managed_group_seen` (`store.py#Store.binding_findings`) and a transient failure changes no
classification at all. When a group genuinely disappears, the binding becomes `dangling`, which
outranks `unmanaged` in the same `CASE` (`store.py#_FINDING_CASE`), so a vanished group can never
manufacture an unmanaged finding. Tested at `test_rbac.py#TestUnmanagedFinding.test_broken_resolution_outranks_provenance`.

**A grant created and removed between refreshes is never reported.** This is a sampler, not a
watch: the ClusterRole holds no `watch` verb and the interval is 300s. A hand-made binding that
exists for less than one interval can go unseen. That is accepted: the feature exists to find
grants that persist, and closing the gap would cost a `watch` verb and a standing connection per
cluster to catch grants that have already stopped existing before anyone could act on them.

## Rollout

There is no staged rollout left. It used to exist because the last step took a write grant, and
`log` was the rehearsal for it; now `log` is the feature and it needs no RBAC change — the
ClusterRole is the same object in both modes, so the switch is a ConfigMap change and nothing
else. The deployment's `checksum/config` annotation (`templates/deployment.yaml#checksum/config`) rolls the pod
so the new value is read, since settings load once at process start (`api.py#_factory`).

What to check on first enabling it, in order. Read the rendered `unmanagedAuditMode`
(`templates/configmap.yaml#unmanagedAuditMode`) so you know which mode the pod is actually in. Wait one binding
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
