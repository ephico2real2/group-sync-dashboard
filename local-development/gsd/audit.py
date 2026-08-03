"""The unmanaged-audit stamping plan. Pure decisions; the poller executes them.

Design and invariants: docs/unmanaged-audit-design.md. Everything here is deliberately
free of I/O so every invariant is a plain unit test — for the dashboard's only write
path, the decision logic being trivially testable is the point.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class StampPlan:
    """What one refresh cycle DISCOVERED, and what it would write about it.

    The discovery is the deliverable. `annotate` mode reaches nothing on a normal cluster —
    Kubernetes privilege-escalation prevention refuses a metadata patch unless the writer
    already holds everything the binding grants — so the plan's real product is the finding
    itself, published to the log and to the API, not a label on an object.
    """

    stamp: list[tuple[str, str, str]]     # (binding_kind, namespace, name)
    unstamp: list[tuple[str, str, str]]
    capped: int                           # how many stamps were deferred by the cap
    # What makes each object a finding, keyed the same way as `stamp`/`unstamp`.
    #
    # Exists so a log line can stand alone as evidence. "ClusterRoleBinding
    # -/demo-cluster-admin-crb" tells a reader which object and nothing about why it matters;
    # naming the role and the group makes the line actionable without opening the dashboard,
    # which is the whole point of publishing the discovery rather than stamping it.
    evidence: dict[tuple[str, str, str], dict] = field(default_factory=dict)


def plan_audit_stamps(rows: list[dict], max_per_cycle: int = 20) -> StampPlan:
    """Decide which bindings to stamp and which to heal, from this cycle's findings.

    `rows` is store.all_bindings() output: one row per (binding, Group subject), so a
    binding naming two groups appears twice — and its two rows can be classified
    DIFFERENTLY (one subject's group managed, the other built-in). Decisions are therefore
    made per OBJECT, not per row:

      * stamp   if ANY of its rows is `unmanaged` and it is not already stamped (I2, I3)
      * unstamp if it IS stamped and NONE of its rows is `unmanaged` (I4) — the label
        comes off so the CLI selection means *currently* outside governance; the
        detected-at annotations stay behind as history, which is the audit trail.

    The cap (I6) bounds a misclassification bug to one screenful of objects per cycle;
    deferred stamps are counted so the caller can log that convergence is pending.
    Unstamps are deliberately NOT capped: healing a wrong or stale stamp must never queue
    behind new detections.
    """
    per_object: dict[tuple[str, str, str], dict] = {}
    for row in rows:
        key = (row["binding_kind"], row["binding_namespace"], row["binding_name"])
        entry = per_object.setdefault(
            key, {"unmanaged": False, "stamped": False, "role": None, "groups": set()})
        entry["stamped"] = entry["stamped"] or bool(row.get("audit_stamped"))
        # A binding has ONE roleRef, so every row for an object agrees about the role; the
        # first non-empty value is the answer rather than a set to reconcile.
        entry["role"] = entry["role"] or row.get("role_name")
        if row["finding"] == "unmanaged":
            entry["unmanaged"] = True
            # Only the groups whose rows were classified unmanaged. A binding naming two
            # groups can have one managed and one not, and reporting the managed one as
            # evidence would send a reader to look at a grant that is fine.
            if row.get("group_name"):
                entry["groups"].add(row["group_name"])

    stamp = sorted(k for k, v in per_object.items() if v["unmanaged"] and not v["stamped"])
    unstamp = sorted(k for k, v in per_object.items() if v["stamped"] and not v["unmanaged"])
    capped = max(0, len(stamp) - max_per_cycle) if max_per_cycle > 0 else 0
    if max_per_cycle > 0:
        stamp = stamp[:max_per_cycle]
    # Evidence for everything named in either list, so the caller never has to guess whether
    # a key is present.
    evidence = {
        key: {"role": per_object[key]["role"],
              "groups": sorted(per_object[key]["groups"])}
        for key in list(stamp) + list(unstamp)
    }
    return StampPlan(stamp=stamp, unstamp=unstamp, capped=capped, evidence=evidence)
