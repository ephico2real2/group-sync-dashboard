"""Report 10 — one document for the ticket: the counts, the findings, the health, and what the
evidence can and cannot attest."""

from __future__ import annotations

from ... import state as st
from ..model import KeyValues, Note, Section, Table
from ..snapshot import Snapshot
from .common import Built, ReportSpec, RunContext, coverage, rank, window_start
from .groupsync_health import GRACE

SPEC = ReportSpec(
    name="compliance-snapshot", title="Compliance snapshot",
    summary="One page of KPIs — groups, users, bindings, findings, privileged grants, dormant access, sync health — and the coverage statement that says what this evidence can attest.",
    values_key="complianceSnapshot",
)


def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    c = snap.counts(cid)
    findings = snap.findings_counts(cid)
    g_rows = snap.group_bindings(cid)
    u_rows = snap.user_bindings(cid)
    priv_g = [g for g in g_rows if g["role_name"] == "cluster-admin" or (g["binding_namespace"] == "" and g["role_name"] in ("admin", "edit"))]
    priv_u = [u for u in u_rows if u["role_name"] == "cluster-admin" or (u["binding_namespace"] == "" and u["role_name"] in ("admin", "edit"))]
    never = snap.never_logged_in_members(cid)
    awl = snap.access_without_login(cid)
    gate = snap.access_group(cid)
    crs = snap.groupsyncs(cid)
    overdue = sum(1 for cr in crs if st.compute_state(st.parse_time(cr["last_sync_at"]), cr["schedule"], ctx.now, GRACE) == st.OVERDUE)
    changes = snap.membership_change_counts(cid, window_start(ctx.now, 30))
    cov = coverage(snap, ctx)
    sections = [
        Section("Key figures", [
            KeyValues("Directory and users", [("Synced groups", c["groups"]), ("Empty groups", c["empty_groups"]), ("Unattributed groups", c["unattributed_groups"]),
                                              ("Distinct members", c["members"]), ("Users who have logged in", c["users_logged_in"]), ("Manual accounts", c["users"] - c["users_logged_in"]),
                                              ("Members added / removed, 30 d", f"{changes['added']} / {changes['removed']}")]),
            # Two populations side by side (SPEC_U1): the group figure counts Group subjects, the
            # finding figures count every subject kind, so each label says which — a reader must not
            # take Unmanaged for a share of Group bindings.
            KeyValues("RBAC", [("Group bindings (Group subjects)", c["group_bindings"]), ("Namespaces with bindings", c["namespaces_with_bindings"]),
                               ("Dangling", findings.get("dangling", 0)), ("Unresolved", findings.get("unresolved", 0)),
                               ("Bindings (every subject kind)", sum(findings.values())),
                               ("Unmanaged (every subject kind)", findings.get("unmanaged", 0)),
                               ("Direct user grants", c["user_bindings"]), ("Platform identity grants (excluded from the direct-user figures)", c["platform_user_bindings"]),
                               ("Privileged group grants", len(priv_g)), ("Privileged direct grants", len(priv_u))]),
            KeyValues("Access hygiene", [("Members who never logged in", len(never)),
                                         ("Access outside the login gate", len(awl) if gate and gate["group_name"] else "no gate known"),
                                         ("Login gate", f"{gate['group_name']}" if gate and gate["group_name"] else "none")]),
            KeyValues("Sync pipeline", [("GroupSync CRs", c["groupsyncs"]), ("Overdue", overdue), ("Last poll", f"{ctx.cluster.get('last_poll')} — {ctx.cluster.get('status')}")]),
        ]),
        Section("Privileged grants", [Table("cluster-admin anywhere; admin/edit cluster-wide", ["kind", "subject", "role", "scope", "binding"],
                                            sorted([["group", g["group_name"], g["role_name"], g["binding_namespace"] or "(cluster-scoped)", g["binding_name"]] for g in priv_g]
                                                   + [["user", u["user_name"], u["role_name"], u["binding_namespace"] or "(cluster-scoped)", u["binding_name"]] for u in priv_u],
                                                   key=lambda r: (-rank(r[2]), r[0], r[1])), empty_text="none")], page_break=True),
        Section("What this evidence attests", [
            Table("Coverage", ["question", "answer"], [
                ["Can it attest that a namespace has NO grants?", "yes" if cov["attests_absence"] else "no — " + cov["namespaces_note"]],
                ["Can it say who has logged in?", "yes (User objects with identities)" if cov["users_read"] == "ok" else "no — " + cov["users_note"]],
                ["Can it say WHEN somebody last logged in?", "yes — " + cov["login_capture_note"] if cov["login_capture"] == "ok" else "no — " + cov["login_capture_note"]],
                ["Does it evaluate effective permissions?", "no — " + cov["direct_bindings_caveat"]],
                ["How far back does membership history go?", cov["history_retained_since"]["membership_event"] or "no rows"],
            ]),
            Note("Each detailed report in the catalogue expands one row of these figures; this page is the summary and inherits every caveat of the reports it summarises.", "note"),
        ], page_break=True),
    ]
    totals = {**c, **{f"finding_{k}": v for k, v in findings.items()}, "privileged_group_grants": len(priv_g), "privileged_direct_grants": len(priv_u), "never_logged_in": len(never), "overdue": overdue}
    return Built(sections, totals, False, False)
