"""Report 3 — the privileged-access review: cluster-admin anywhere; admin and edit cluster-wide."""

from __future__ import annotations

from ..model import Note, Section, Table
from ..snapshot import Snapshot
from .common import Built, ParamSpec, ReportSpec, RunContext, finding_label, ns_label, rank, roster_table

DEFAULT_ROLES = ("cluster-admin", "admin", "edit")

SPEC = ReportSpec(
    name="privileged-access", title="Privileged access review",
    summary="Every subject holding cluster-admin at any scope, or admin/edit cluster-wide, with the people behind each group.",
    values_key="privilegedAccess",
    params=(
        ParamSpec("include_members", "bool", True, "Rosters of the privileged groups. ON by default here: a privileged-access review without names is not a review. Recorded in the provenance."),
        ParamSpec("roles", "csv", list(DEFAULT_ROLES), "Role names that count as privileged (comma-separated)."),
    ),
)


def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    roles = tuple(params["roles"]) or DEFAULT_ROLES
    g_rows = snap.privileged_group_bindings(cid, roles)
    u_rows = snap.privileged_user_bindings(cid, roles)
    g_rows.sort(key=lambda g: (-rank(g["role_name"]), g["binding_namespace"] != "", g["group_name"], g["binding_name"]))
    u_rows.sort(key=lambda u: (-rank(u["role_name"]), u["binding_namespace"] != "", u["user_name"], u["binding_name"]))
    blocks = [
        Note(f"Privileged here means: a binding to {', '.join(roles)} — cluster-admin at any scope, the others at cluster scope. Namespaced admin/edit grants are in the access matrix and the namespace report.", "note"),
        Table("Group grants", ["role", "scope", "group", "binding", "members", "logged in", "classification", "source"],
              [[g["role_name"], ns_label(g["binding_namespace"]), g["group_name"], g["binding_name"],
                "" if g["member_count"] is None else g["member_count"], "" if g["logged_in_count"] is None else g["logged_in_count"],
                finding_label(g["finding"]), g["managed_source"] or "hand-made"] for g in g_rows], empty_text="no privileged group grants"),
        Table("Direct user grants", ["role", "scope", "user", "binding"],
              [[u["role_name"], ns_label(u["binding_namespace"]), u["user_name"], u["binding_name"]] for u in u_rows],
              note="A direct privileged grant is the highest-severity finding this dashboard knows: tied to a person, not to a reviewed group.",
              empty_text="no direct privileged grants"),
    ]
    sections = [Section("Privileged grants", blocks)]
    include_members = params["include_members"]
    if include_members:
        names = sorted({g["group_name"] for g in g_rows if g["finding"] in ("ok", "unmanaged")})
        rosters = snap.group_rosters(cid, names)
        roster_blocks = [roster_table(f"Members of {n}", rosters.get(n, [])) for n in names]
        sections.append(Section("Who holds it — rosters of the privileged groups", roster_blocks or [Note("No resolvable privileged group.", "note")], page_break=True))
    people = set()
    if include_members:
        for n, ms in snap.group_rosters(cid, [g["group_name"] for g in g_rows]).items():
            people |= {m["user_name"] for m in ms}
    people |= {u["user_name"] for u in u_rows}
    totals = {"group_grants": len(g_rows), "direct_grants": len(u_rows), "distinct_people": len(people) if include_members else None}
    return Built(sections, totals, False, include_members)
