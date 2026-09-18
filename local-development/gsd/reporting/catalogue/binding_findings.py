"""Report 4 — RBAC hygiene: the dashboard's own classification, one table per tier."""

from __future__ import annotations

from ..model import KeyValues, Note, Section, Table
from ..snapshot import Snapshot
from .common import Built, ReportSpec, RunContext, cut, ns_label

SPEC = ReportSpec(
    name="binding-findings", title="RBAC binding findings",
    summary="Dangling, unresolved and unmanaged group bindings and direct user grants; system:* virtual groups are omitted (a platform built-in, not a person's grant).",
    values_key="bindingFindings",
)

_DEFINITIONS = [
    ("dangling", "the group was observed operator-managed and is now absent — something broke; the binding grants nobody"),
    ("unresolved", "the group has never been seen managed and does not exist — the binding names something that never existed"),
    ("unmanaged", "a synced group granted by a binding no policy operator manages, with no exception annotation — governance bypassed by hand"),
    ("ok", "resolves normally"),
]


def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    counts = snap.findings_counts(cid)
    rows = snap.group_bindings(cid)
    truncated = False
    sections = [Section("Summary", [
        KeyValues("Bindings by tier", [(k, counts.get(k, 0)) for k, _ in _DEFINITIONS]),
        Table("Definitions (the dashboard's, gsd/store.py Store._FINDING_CASE)", ["tier", "meaning"], [[k, v] for k, v in _DEFINITIONS]),
    ])]
    for tier in ("dangling", "unresolved", "unmanaged"):
        tier_rows, t = cut([r for r in rows if r["finding"] == tier])
        truncated = truncated or t
        sections.append(Section(f"{tier.capitalize()} bindings", [Table(
            tier, ["group", "scope", "role", "binding", "kind", "source", "exception"],
            [[r["group_name"], ns_label(r["binding_namespace"]), f"{r['role_kind']}/{r['role_name']}", r["binding_name"], r["binding_kind"],
              r["managed_source"] or "hand-made", r["exception"] or ""] for r in tier_rows],
            empty_text=f"no {tier} bindings")], page_break=True))
    exceptions = [r for r in rows if r["exception"]]
    sections.append(Section("Acknowledged exceptions", [Table(
        "Bindings carrying rbac.ocp.io/unmanaged-exception", ["group", "scope", "role", "binding", "exception"],
        [[r["group_name"], ns_label(r["binding_namespace"]), r["role_name"], r["binding_name"], r["exception"]] for r in exceptions],
        note="An exception suppresses the unmanaged finding; it is listed so a reviewer can re-judge it.", empty_text="none")]))
    users = snap.user_bindings(cid)
    users, t = cut(users)
    truncated = truncated or t
    sections.append(Section("Direct user grants", [
        Table("Bindings naming a person", ["user", "scope", "role", "binding", "kind"],
              [[u["user_name"], ns_label(u["binding_namespace"]), f"{u['role_kind']}/{u['role_name']}", u["binding_name"], u["binding_kind"]] for u in users],
              empty_text="none"),
        Note(f"{snap.platform_user_binding_count(cid)} platform identity binding(s) (system:*, kube-apiserver, node identities) are excluded from this table and counted here, so the exclusion is visible.", "note"),
    ], page_break=True))
    totals = {**{k: counts.get(k, 0) for k, _ in _DEFINITIONS}, "direct_user": len(users), "platform_user": snap.platform_user_binding_count(cid)}
    return Built(sections, totals, truncated, False)
