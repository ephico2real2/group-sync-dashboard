"""Report 8 — access nobody uses: never logged in, not in the gate, or (with capture) no success in N days."""

from __future__ import annotations

from ..model import KeyValues, Note, Section, Table
from ..snapshot import Snapshot
from .common import Built, ParamSpec, ReportSpec, RunContext, cut, window_start

SPEC = ReportSpec(
    name="dormant-access", title="Dormant and unusable access",
    summary="Members with access who have never logged in, members outside the login gate, gate members with no access, and — with login capture — nobody-in-N-days.",
    values_key="dormantAccess",
    params=(ParamSpec("dormant_days", "int", 90, "With login capture on: a member whose last successful login is older than this is listed as dormant.", lo=1, hi=3650),),
)


def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    never = snap.never_logged_in_members(cid)
    awl = snap.access_without_login(cid)
    lwa = snap.login_without_access(cid)
    gate = snap.access_group(cid)
    never_rows, t1 = cut([[m["user_name"], m["group_count"], m["first_seen_at"], m["why"]] for m in never])
    sections = [Section("Summary", [KeyValues("Counts", [
        ("Members who have never logged in", len(never)),
        ("Members with access but outside the login gate", len(awl) if gate and gate["group_name"] else "no gate group known"),
        ("Gate members with no other access", len(lwa) if gate and gate["group_name"] else "no gate group known"),
        ("Login gate", f"{gate['group_name']} ({gate['source']})" if gate and gate["group_name"] else "none"),
    ])])]
    sections.append(Section("Never logged in", [
        Table("Synced members with no login", ["member", "groups", "first seen", "why"], never_rows, empty_text="everyone with access has logged in",
              note="Access held through a directory group by an account that has never authenticated here. Offboarding candidates, or people who never needed the access."),
    ], page_break=True))
    sections.append(Section("The login gate", [
        Table("Access without login (outside the gate)", ["member", "groups", "group names", "first seen", "has tried to log in"],
              [[a["user_name"], a["group_count"], a["groups"], a["first_seen_at"], "yes" if a["has_tried"] else "no"] for a in awl],
              empty_text="none" if gate and gate["group_name"] else "no gate group known — cannot be computed"),
        Table("Login without access (gate members holding nothing else)", ["member", "first seen", "has tried to log in"],
              [[a["user_name"], a["first_seen_at"], "yes" if a["has_tried"] else "no"] for a in lwa],
              empty_text="none" if gate and gate["group_name"] else "no gate group known — cannot be computed"),
    ], page_break=True))
    truncated = t1
    dormant_count = None
    if ctx.settings.login_capture_enabled:
        last = snap.last_successful_login(cid)
        cutoff = window_start(ctx.now, params["dormant_days"])
        capture = snap.login_capture_status(cid)
        rosters = snap.group_rosters(cid, [g["name"] for g in snap.groups(cid)])
        members = {m["user_name"] for ms in rosters.values() for m in ms if m.get("logged_in") == 1}
        dormant = sorted((u, last.get(u)) for u in members if last.get(u) is None or last[u] < cutoff)
        rows, t2 = cut([[u, l or "no success recorded since capture began"] for u, l in dormant])
        truncated = truncated or t2
        dormant_count = len(dormant)
        sections.append(Section(f"Dormant: no successful login in {params['dormant_days']} days", [
            Table("Members who have logged in before, not recently", ["member", "last successful login"], rows, empty_text="none"),
            Note("Only as good as capture's coverage: " + (f"attempts recorded since {capture['started_at']}" if capture else "capture has not read anything yet") + ". A member whose last login predates capture shows 'no success recorded'.", "caveat"),
        ], page_break=True))
    else:
        sections.append(Section("Dormancy by last login", [Note("Login capture is off; 'never logged in' above is the strongest dormancy statement this data supports (a User object with an identity exists or it does not).", "note")]))
    totals = {"never_logged_in": len(never), "access_without_login": len(awl), "login_without_access": len(lwa), "dormant": dormant_count}
    return Built(sections, totals, truncated, False)
