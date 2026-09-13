"""Report 6 — user inventory: who has logged in, through which provider, with how much access."""

from __future__ import annotations

from collections import Counter

from ..model import KeyValues, Note, Section, Table
from ..snapshot import Snapshot
from .common import Built, ParamSpec, ReportSpec, RunContext, cut

SPEC = ReportSpec(
    name="users", title="Users",
    summary="Every User object (a login), its identity providers, group count and direct grants; manual accounts; synced members who have never logged in.",
    values_key="users",
    params=(ParamSpec("providers", "csv", [], "Only users with an identity from these providers (comma-separated; empty = all)."),),
)


def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    users = snap.users(cid)
    wanted = set(params["providers"])
    if wanted:
        users = [u for u in users if set(u["providers"]) & wanted]
    logged_in = [u for u in users if u["logged_in"]]
    manual = [u for u in users if not u["logged_in"]]
    without_user = snap.synced_members_without_user(cid)
    by_provider = Counter(p for u in logged_in for p in u["providers"])
    users_src = (snap.users_source(cid) or {}).get("state")
    rows, t1 = cut([[u["user_name"], u.get("full_name") or "", ", ".join(u["providers"]), u["created_at"] or "", u["group_count"], u["direct_bindings"], u["first_seen_at"] or ""] for u in logged_in])
    blocks_summary = [KeyValues("Users", [
        ("User objects", len(users)), ("With an identity (have logged in)", len(logged_in)), ("Manual accounts (no identity)", len(manual)),
        ("Synced members with no User object (never logged in)", len(without_user)),
        ("Providers", ", ".join(f"{p}: {n}" for p, n in sorted(by_provider.items())) or "none"),
        ("Filter", ", ".join(sorted(wanted)) or "none"),
    ])]
    if users_src != "ok":
        blocks_summary.append(Note("User objects were not read on the last poll (" + (users_src or "pending") + "); the tables below are the last successful read, or empty.", "warning"))
    sections = [
        Section("Summary", blocks_summary),
        Section("Users who have logged in", [Table("Users", ["user", "name", "providers", "first login", "groups", "direct grants", "first seen in a group"], rows, empty_text="none")], page_break=True),
        Section("Accounts to review", [
            Table("Manual accounts (created by hand, never logged in)", ["user", "name", "created", "groups", "direct grants"],
                  [[u["user_name"], u.get("full_name") or "", u["created_at"] or "", u["group_count"], u["direct_bindings"]] for u in manual], empty_text="none"),
            Table("Synced members with no User object", ["member", "groups", "first seen"],
                  [[m["user_name"], m["group_count"], m["first_seen_at"]] for m in without_user], empty_text="none",
                  note="Granted access through a directory group but never authenticated to this cluster."),
        ], page_break=True),
    ]
    return Built(sections, {"users": len(users), "logged_in": len(logged_in), "manual": len(manual), "without_user": len(without_user)}, t1, False)
