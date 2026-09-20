"""Report 1 — the namespace access report (the C3 report, kept): per namespace, who is granted
what, findings first, deterministically sorted (docs/namespace-report-design.md §6)."""

from __future__ import annotations

from ..model import KeyValues, Note, Section, Table
from ..snapshot import CLUSTER_SCOPE, Snapshot
from .common import (MAX_NAMESPACES, Built, ParamSpec, ReportSpec, RunContext, ValidationError,
                     cut, finding_label, roster_table)


def _validate_selection(params: dict) -> None:
    """Cross-parameter check run at the endpoint (a 422): choose namespaces by `selectors`
    (multi-dimension, P2) OR the deprecated single-dimension `mnemonics` OR explicit `namespaces` —
    exactly one. The label-value expansion needs the snapshot, so it stays in build()."""
    chosen = [k for k in ("selectors", "mnemonics", "namespaces") if params.get(k)]
    if len(chosen) > 1:
        raise ValidationError(
            "choose namespaces by selectors OR mnemonic OR explicit name, not more than one")
    if not chosen:
        raise ValidationError("select at least one namespace, by selector, mnemonic or explicit name")
    if len(params.get("mnemonics") or []) > MAX_NAMESPACES:
        raise ValidationError(f"at most {MAX_NAMESPACES} mnemonic values per report")


SPEC = ReportSpec(
    name="namespace-access", title="Namespace access report",
    summary="Per namespace: every group binding classified with who it reaches, every direct user grant, findings first.",
    values_key="namespaceAccess",
    params=(
        ParamSpec("selectors", "selector-map", None,
                  "Select namespaces by the estate's grouping labels (the Reports form offers one "
                  "multi-select per configured dimension). Values within a dimension match ANY; the "
                  "dimensions are AND'd. Leave the explicit names empty when using this."),
        ParamSpec("mnemonics", "csv", None,
                  "Deprecated single-dimension form — maps to the first configured selector label. "
                  "Prefer `selectors`; leave the explicit names empty when using this."),
        ParamSpec("namespaces", "namespaces", None,
                  "Explicit namespace names, at most 50; `(cluster-scoped)` for cluster-wide bindings. Overrides the Scope.",
                  source="namespaces", advanced=True),
        ParamSpec("include_members", "bool", False, "Expand group rosters. Off by default — a file that gets emailed has no reader log — and recorded in the provenance when on."),
        ParamSpec("group_by", "enum", "mnemonic", "Sort and group the namespaces by a metadata label — the mnemonic or the "
                  "app-environment every namespace carries, or the exact-group label some pin (the rest fall under "
                  "'(no oud-group)'). Groups the output; it does not filter.",
                  choices=("mnemonic", "app-environment", "oud-group"), advanced=True),
    ),
    validator=_validate_selection,
)


def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    selectors: dict[str, list[str]] = params.get("selectors") or {}
    mnemonics: list[str] = params.get("mnemonics") or []
    names: list[str] = params.get("namespaces") or []
    labels = tuple(ctx.namespace_selector_labels)
    # The snapshot-dependent expansion: a selection matching nothing is a failed run (it needs the
    # snapshot), not a 422 — the cross-parameter check already ran at the endpoint.
    if selectors:
        if not labels:
            raise ValidationError(
                "selector namespace selection is not configured on this deployment; set "
                "reporting.namespaceSelector.labels or use explicit namespace names")
        unknown = sorted(k for k in selectors if k not in labels)
        if unknown:
            raise ValidationError(
                f"selector label(s) not configured on this deployment: {', '.join(unknown)}")
        if not snap.selector_capture_present():          # a pre-capture copy attests nothing, not zero
            raise ValidationError(
                "this snapshot carries no namespace-label capture (it predates the capture); "
                "use explicit namespace names or wait for the next snapshot")
        names = snap.namespaces_for_selectors(cid, selectors)
        if not names:
            raise ValidationError("no namespace matches " + " AND ".join(
                f"{k} in ({', '.join(v)})" for k, v in selectors.items()))
    elif mnemonics:
        if not labels:
            raise ValidationError(
                "mnemonic namespace selection is not configured on this deployment; set "
                "reporting.namespaceSelector.labels or use explicit namespace names")
        if not snap.selector_capture_present():          # the mnemonic path expands the same table
            raise ValidationError(
                "this snapshot carries no namespace-label capture (it predates the capture); "
                "use explicit namespace names or wait for the next snapshot")
        names = snap.namespaces_for_metadata(cid, labels[0], mnemonics)
        if not names:
            raise ValidationError(
                f"no namespace carries {labels[0]} with value(s) {', '.join(mnemonics)}")
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
    # #149 R7: the sections come out grouped by a namespace label, the group named in each heading.
    # The label keys: the mnemonic is the first captured selector dimension, the app-environment the
    # second (the estate convention company.net/mnemonic + company.net/app-environment), the exact
    # group the deployment's namespace group label. A namespace without the label sits last.
    labels = list(ctx.settings.namespace_selector_labels)
    by_key = {"mnemonic": labels[0] if labels else "", "app-environment": labels[1] if len(labels) > 1 else "",
              "oud-group": ctx.settings.namespace_group_label}
    group_label = by_key.get(params["group_by"], "")
    label_map = snap.namespace_label_map(cid, group_label) if group_label else {}
    if not label_map:
        group_label = ""     # nothing captured for this cluster: the headings stay as they were (review of #222, Grok)
    pairs = sorted(zip(names, keys), key=lambda nk: (nk[0] == CLUSTER_SCOPE, label_map.get(nk[0]) is None, label_map.get(nk[0], ""), nk[0]))
    for n, key in pairs:
        bucket = "cluster-scoped" if n == CLUSTER_SCOPE else (label_map.get(n) or f"(no {params['group_by']})") if group_label else ""
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
        heading = f"Namespace: {n}" if n != CLUSTER_SCOPE else "Cluster-scoped bindings"
        if bucket and n != CLUSTER_SCOPE:
            heading = f"{bucket} · {heading}"
        sections.append(Section(heading, blocks, page_break=True))
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
