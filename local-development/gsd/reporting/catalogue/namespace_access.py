"""Report 1 — the namespace access report (the C3 report, kept): per namespace, who is granted
what, findings first, deterministically sorted (docs/namespace-report-design.md §6)."""

from __future__ import annotations

from ..model import KeyValues, Note, Section, Table
from ..snapshot import CLUSTER_SCOPE, Snapshot
from .common import (MAX_NAMESPACES, Built, ParamSpec, ReportSpec, RunContext, ValidationError,
                     cut, finding_label, roster_table)


def _validate_selection(params: dict) -> None:
    """Cross-parameter check run at the endpoint (a 422): choose namespaces by mnemonic OR by name,
    exactly one. The mnemonic-to-namespace expansion needs the snapshot, so it stays in build()."""
    mnemonics = params.get("mnemonics") or []
    names = params.get("namespaces") or []
    if mnemonics and names:
        raise ValidationError("choose namespaces by mnemonic OR by explicit name, not both")
    if not mnemonics and not names:
        raise ValidationError("select at least one namespace, by mnemonic or by explicit name")
    if len(mnemonics) > MAX_NAMESPACES:
        raise ValidationError(f"at most {MAX_NAMESPACES} mnemonic values per report")


SPEC = ReportSpec(
    name="namespace-access", title="Namespace access report",
    summary="Per namespace: every group binding classified with who it reaches, every direct user grant, findings first.",
    values_key="namespaceAccess",
    params=(
        ParamSpec("mnemonics", "csv", None,
                  "Select namespaces by the estate's grouping label (the Reports form offers the values). "
                  "Strict and current; leave the explicit names empty when using this."),
        ParamSpec("namespaces", "namespaces", None,
                  "Advanced: explicit namespace names, at most 50; `(cluster-scoped)` for cluster-wide bindings."),
        ParamSpec("include_members", "bool", False, "Expand group rosters. Off by default — a file that gets emailed has no reader log — and recorded in the provenance when on."),
    ),
    validator=_validate_selection,
)


def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    mnemonics: list[str] = params.get("mnemonics") or []
    names: list[str] = params.get("namespaces") or []
    if mnemonics:
        # The snapshot-dependent expansion: a mnemonic matching nothing is a failed run (it needs the
        # snapshot), not a 422 — the cross-parameter check already ran at the endpoint.
        if not ctx.namespace_selector_label:
            raise ValidationError(
                "mnemonic namespace selection is not configured on this deployment; set "
                "reporting.namespaceSelector.label or use explicit namespace names")
        names = snap.namespaces_for_metadata(cid, ctx.namespace_selector_label, mnemonics)
        if not names:
            raise ValidationError(
                f"no namespace carries the selector label with value(s) {', '.join(mnemonics)}")
    selector_capped = len(names) > MAX_NAMESPACES
    names = names[:MAX_NAMESPACES]                # cap AFTER expansion; recorded in the coverage note
    keys = ["" if n == CLUSTER_SCOPE else n for n in names]
    include_members = params["include_members"]
    ns_state = (snap.namespaces_source(cid) or {}).get("state")
    existing = {r["name"] for r in snap.cluster_namespaces(cid)} if ns_state == "ok" else None
    observed = {r["namespace"] for r in snap.binding_namespaces(cid)}
    groups = snap.group_bindings(cid, keys)
    users = snap.user_bindings(cid, keys)
    rosters = snap.group_rosters(cid, sorted({g["group_name"] for g in groups if g["finding"] in ("ok", "unmanaged")})) if include_members else {}
    sections: list[Section] = []
    truncated = False
    for n, key in zip(names, keys):
        g_rows = [g for g in groups if g["binding_namespace"] == key]
        u_rows = [u for u in users if u["binding_namespace"] == key]
        g_rows, t1 = cut(g_rows)
        u_rows, t2 = cut(u_rows)
        truncated = truncated or t1 or t2
        findings = {k: sum(1 for g in g_rows if g["finding"] == k) for k in ("dangling", "unresolved", "unmanaged")}
        findings["direct_user"] = len(u_rows)
        exists = None if existing is None or n == CLUSTER_SCOPE else n in existing
        status = ("cluster-wide bindings" if n == CLUSTER_SCOPE else
                  "exists on the cluster" if exists else "does NOT exist on the cluster" if exists is False else
                  "existence not attested (namespaces not read)")
        blocks = [
            KeyValues("Namespace", [("Name", n), ("Status", status), ("Observed on a binding", "yes" if n in observed else "no"),
                                    ("Findings", ", ".join(f"{k}: {v}" for k, v in findings.items()))]),
            Table("Group bindings", ["finding", "group", "role", "binding", "kind", "members", "logged in", "source", "exception"],
                  [[finding_label(g["finding"]), g["group_name"], f"{g['role_kind']}/{g['role_name']}", g["binding_name"], g["binding_kind"],
                    "" if g["member_count"] is None else g["member_count"], "" if g["logged_in_count"] is None else g["logged_in_count"],
                    g["managed_source"] or "hand-made", g["exception"] or ""] for g in g_rows],
                  empty_text="no group bindings" + ("" if exists is not False else " — the namespace does not exist")),
            Table("Direct user grants", ["user", "role", "binding", "kind"],
                  [[u["user_name"], f"{u['role_kind']}/{u['role_name']}", u["binding_name"], u["binding_kind"]] for u in u_rows],
                  note="A binding naming a person rather than a group survives offboarding and is invisible to group-based review.",
                  empty_text="no direct user grants"),
        ]
        if include_members:
            for g in g_rows:
                if g["group_name"] in rosters:
                    blocks.append(roster_table(f"Members of {g['group_name']}", rosters[g["group_name"]]))
        if exists is None and n != CLUSTER_SCOPE and n not in observed:
            blocks.append(Note("Neither a Namespace object nor a binding in it was observed; this report cannot say whether the namespace exists.", "warning"))
        sections.append(Section(f"Namespace: {n}" if n != CLUSTER_SCOPE else "Cluster-scoped bindings", blocks, page_break=True))
    if selector_capped:
        sections.insert(0, Section("Coverage", [Note(
            f"The selector matched more than {MAX_NAMESPACES} namespaces; this report covers the first "
            f"{MAX_NAMESPACES} in name order. Narrow the mnemonic selection for a complete listing.",
            "warning")]))
    totals = {"namespaces": len(names), "group_bindings": len(groups), "user_bindings": len(users)}
    # `truncated` is a ROW_LIMIT cut only — assemble()'s Truncation note says exactly that, and a
    # selector cap is neither a row cut nor a wrong `totals`. The Coverage section above is the cap
    # record (design §3.6), so the selector cap does not set `truncated` (review #112, F1).
    return Built(sections, totals, truncated, include_members)
