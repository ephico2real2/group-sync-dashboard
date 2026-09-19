"""Report 5 — group inventory and membership change in a window."""

from __future__ import annotations

from ..model import KeyValues, Note, Section, Table
from ..snapshot import Snapshot
from .common import Built, ParamSpec, ReportSpec, RunContext, cut, roster_table, window_start
from ...kpi.predicates import is_empty, is_unattributed

SPEC = ReportSpec(
    name="groups", title="Groups and membership changes",
    summary="Every synced group: provider, member count, last sync, bindings, cliff silence; the empty and unattributed lists; joins and leaves in the window.",
    values_key="groups",
    params=(
        ParamSpec("window_days", "int", 30, "Membership changes observed in the last N days.", lo=1, hi=3650),
        ParamSpec("include_members", "bool", False, "Rosters for every group. Recorded in the provenance when on."),
    ),
)


def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    since = window_start(ctx.now, params["window_days"])
    groups = snap.groups(cid)
    changes = snap.membership_changes(cid, since)
    change_counts = snap.membership_change_counts(cid, since)
    retained = snap.history_retained_since(cid)["membership_event"]
    inventory, t1 = cut([[g["name"], g["sync_provider"] or "unattributed", g["member_count"], g["group_synced_at"] or "", g["bindings"], g["cliff_silence"] or ""] for g in groups])
    shown_changes, t2 = cut([[c["observed_at"], c["change"], c["group_name"], c["user_name"], c["group_synced_at"] or ""] for c in changes])
    sections = [
        Section("Summary", [KeyValues("Groups", [
            ("Total", len(groups)), ("Empty (no members)", sum(1 for g in groups if is_empty(g))),
            ("Unattributed (no sync provider)", sum(1 for g in groups if is_unattributed(g))),
            (f"Members added in {params['window_days']} d", change_counts["added"]), (f"Members removed in {params['window_days']} d", change_counts["removed"]),
            ("Membership history retained since", retained or "no rows"),
        ])]),
        Section("Inventory", [Table("Groups", ["group", "provider", "members", "synced at", "bindings", "cliff silence"], inventory)], page_break=True),
        Section("Groups needing attention", [
            Table("Empty groups", ["group", "provider"], [[g["name"], g["sync_provider"] or "unattributed"] for g in groups if is_empty(g)], empty_text="none",
                  note="A group that grants nobody: either the directory group emptied, or the LDAP filter no longer matches it."),
            Table("Unattributed groups", ["group", "members"], [[g["name"], g["member_count"]] for g in groups if is_unattributed(g)], empty_text="none",
                  note="No GroupSync CR claims this group; it is not governed by the directory."),
        ], page_break=True),
        Section(f"Membership changes, last {params['window_days']} days", [
            Table("Changes", ["observed at", "change", "group", "member", "group synced at"], shown_changes, empty_text="no changes observed in the window"),
            Note("Observed by the dashboard's poll, so a change is dated at the poll that saw it, not at the directory's edit; the history covers only the period since the dashboard began observing" + (f" ({retained})" if retained else "") + ".", "caveat"),
        ], page_break=True),
    ]
    include_members = params["include_members"]
    if include_members:
        rosters = snap.group_rosters(cid, [g["name"] for g in groups])
        sections.append(Section("Rosters", [roster_table(f"Members of {g['name']}", rosters.get(g["name"], [])) for g in groups], page_break=True))
    totals = {"groups": len(groups), "changes": len(changes), **change_counts}
    return Built(sections, totals, t1 or t2, include_members)
