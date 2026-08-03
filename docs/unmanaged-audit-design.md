# Unmanaged-grant audit stamping — design and invariants

The dashboard's **first and only write** to any cluster: when enabled, it stamps bindings
it has classified `unmanaged` (a hand-made grant on an operator-synced group, outside the
policy system) so auditors can find them **from the objects themselves**:

```
oc get rolebindings,clusterrolebindings -A -l rbac.ocp.io/unmanaged=true
```

| Key | Kind | Meaning |
|---|---|---|
| `rbac.ocp.io/unmanaged: "true"` | label | *currently* classified unmanaged — selectable |
| `rbac.ocp.io/unmanaged-detected-at` | annotation | FIRST detection, never overwritten |
| `rbac.ocp.io/unmanaged-detected-by` | annotation | `group-sync-dashboard` |

Together with the existing human-side `rbac.ocp.io/unmanaged-exception` annotation, this
gives auditors a complete invariant: **every binding on a synced group carries either the
policy operator's `config-source` label, a human justification, or a machine detection
stamp** — and anything carrying none of the three is new since the last refresh.

## Invariants — each one is a test

**I1 — Write set.** Only `metadata.labels` / `metadata.annotations`, and only the three
keys above. Never subjects, never roleRef, never another key. The patch body is built in
exactly one function and contains nothing else.

**I2 — Target set.** Only bindings whose finding is `unmanaged` *this cycle*, which
already requires: the group resolves, the group is operator-synced, the binding carries no
`config-source` label and no exception annotation, and the cluster demonstrably uses the
policy operator (some managed binding exists — a cluster that has never heard of
config-source labels gets zero stamps, not sixty).

**I3 — Idempotent.** A binding already carrying the label is never patched again;
`detected-at` is immutable, so it stays meaningful as "how long has this existed
unacknowledged".

**I4 — Self-healing selection.** When a stamped binding STOPS being unmanaged — it gained
a `config-source` label, gained an exception, or its group left management — the label is
REMOVED so the CLI selection always means *currently outside governance*, while the
`detected-*` annotations are KEPT as history. An acknowledged binding therefore reads:
detected at X by the dashboard, justified by a human with reason Y.

**I5 — Mode-gated, default off.** `unmanagedAudit.mode: off | log | annotate`.
`off` executes no write-path code at all. `log` computes the full plan and logs it —
the rehearsal mode; nothing is patched. `annotate` writes. The chart renders the RBAC
`patch` grant **only** in annotate mode.

**I6 — Bounded blast radius.** At most `maxPerCycle` (default 20) stamps per refresh,
with a loud log when the cap is hit. A misclassification bug then mars one screenful of
objects per 300s cycle instead of the whole cluster at once, and the log gives a human a
cycle to pull the flag.

**I7 — Single writer.** Runs only on the binding-refresh path, which is leader-gated.

**I8 — Failure isolation.** A failed patch (403, conflict, timeout) is logged and skipped;
it never fails the refresh, never blocks other stamps, and never affects the read pipeline.

## Kubernetes will not let this work on the objects that matter most

**Discovered on the live cluster, after the feature was built and enabled.** Granting
`patch` is necessary but NOT sufficient. Kubernetes applies *privilege escalation
prevention* to RBAC objects: to write one — even a metadata-only merge patch that touches
no rule and no subject — the writer must already hold every permission that object grants.
The API server's own words, from the pod:

```
clusterrolebindings "demo-cluster-audit-crb" is forbidden: user
"system:serviceaccount:group-sync-dashboard:group-sync-dashboard" is attempting to grant
RBAC permissions not currently held: {APIGroups:[""], Resources:[...], Verbs:[...]}  (x~200)
```

`SelfSubjectAccessReview` says `allowed: true` — the RBAC grant is correct — and the patch
is still refused by the escalation check, which runs afterwards. Anyone reasoning from
`oc auth can-i` alone will conclude this works. It does not.

**The consequence is a hard ceiling, not a tuning problem.** For the dashboard to stamp a
binding that grants `cluster-admin`, the dashboard would itself need `cluster-admin`. The
audit feature would therefore require the *most* privilege on exactly the *most* dangerous
grants — precisely inverting what a read-only auditing tool should be. Two escape hatches
exist and both are refused here:

* grant the dashboard `cluster-admin` — absurd for a read-only dashboard, and it makes a
  compromise of this pod a full cluster compromise;
* grant `escalate` on `rbac.authorization.k8s.io` — the verb that switches the check off,
  which is the same thing wearing a smaller word.

**Therefore `annotate` mode can only ever stamp bindings whose grants the dashboard already
holds** — in practice the narrow, low-privilege ones.

> **Measured 2026-08-03, and the sentence above is optimistic.** Enabling `annotate` on the
> reference cluster produced `plan — stamp 4, heal 0` and then **0 of 4 succeeded**, including
> a ClusterRoleBinding granting nothing but `view` and a namespaced RoleBinding granting
> `view`. On OpenShift `view` alone covers dozens of resources the read-only SA does not hold
> — the refusal named `appliedclusterresourcequotas`, `bindings`, `buildconfigs` and more —
> so even the low-privilege end is out of reach. Treat `annotate` as reaching **nothing** on a
> cluster of this shape, rather than "the narrow ones", and use `log` mode plus the API for
> the audit trail.
>
> The refusal was also being reported as "the token lacks patch on
> rolebindings/clusterrolebindings" while `oc auth can-i patch clusterrolebindings --as=<the
> SA>` answered **yes** — an operator following that would add a grant they already had. The
> two 403s are now distinguished, with a test for each.
>
> **How big a "special role" would have to be, since it is the obvious next question.** The API
> server enumerates what it wants. To stamp the single most harmless binding on the cluster —
> a ClusterRoleBinding granting nothing but `view` — it demands **175 additional rule sets**,
> because the writer must hold everything `view` grants. For the `cluster-admin` binding it
> demands one rule: `{APIGroups:[*], Resources:[*], Verbs:[*]}`.
>
> So the three available shapes are 175+ rules of Kubernetes internals per binding class,
> `escalate` on `rbac.authorization.k8s.io` (the verb that disables the check — cluster-admin
> under a smaller name), or cluster-admin outright. Each gives a read-only auditing tool the
> most privilege on precisely the most dangerous grants, so a compromise of this pod becomes a
> cluster compromise, in exchange for a convenience label. Do not build it. It fails safe: each refusal is a
logged warning, the refresh continues, and the finding remains visible in the UI and the
API. The dashboard reports the grant either way; only the on-object convenience label is
lost. Enabling annotate mode remains reasonable for clusters where the unmanaged set is
low-privilege, and `log` mode is fully useful everywhere.

**What to use instead for a cluster-wide audit trail:** the API and UI already carry the
complete set with no write access at all
(`GET /api/clusters/{id}/bindings/findings` → `unmanaged`), and a privileged CI job or an
admin running `oc annotate` can stamp objects the dashboard cannot.

## The cost, stated plainly

Kubernetes RBAC has **no annotations-only patch scope**. Annotate mode requires `patch` on
`rolebindings`/`clusterrolebindings`, and a subject with that verb can technically modify
what a binding grants. The application never does (I1), but the *grant* exists — enabling
this hands the dashboard's ServiceAccount a write capability an attacker who compromised
the pod could abuse. That is why the default is `off`, the grant is rendered only in
annotate mode, and `log` mode exists so the plan can be inspected with zero write access.

## Rollout

1. Ship with `mode: off`. Nothing changes anywhere.
2. Flip to `log` on the target cluster. Inspect the planned stamps/unstamps for at least
   one full refresh cycle against expectations.
3. Flip to `annotate`. Verify: expected objects stamped; exception-annotated and
   operator-labelled bindings untouched; second cycle stamps zero (idempotency);
   adding an exception to a stamped binding removes its label next cycle and keeps the
   annotations (I4); the CLI selection returns exactly the current findings.

## Races considered

* **A binding mid-migration into the policy system** (created before its label lands) can
  be stamped in the window. I4 heals it: the label is removed the cycle after the
  `config-source` label appears; the annotations record that the window existed, which for
  audit purposes is the truth.
* **Stale classification after a failed group poll**: findings derive from the last
  successful poll's `group_state`/`managed_group_seen`; the binding refresh is separate.
  The failure direction is safe — a group that vanished from a failed poll does not make
  its bindings `unmanaged` (they become `dangling`, which never stamps).
