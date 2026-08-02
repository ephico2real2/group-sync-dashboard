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
