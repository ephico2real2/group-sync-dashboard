"""Report 9 — the sync pipeline: CR state, errors, sync history, the policy operator's CRs."""

from __future__ import annotations

from datetime import timedelta

from ... import state as st
from ..model import KeyValues, Note, Section, Table, WITHHELD
from ..snapshot import Snapshot
from .common import Built, ParamSpec, ReportSpec, RunContext, window_start

SPEC = ReportSpec(
    name="groupsync-health", title="GroupSync and policy-operator health",
    summary="Every GroupSync CR with its computed state, schedule and last sync; reconcile errors (current vs stale); syncs in the window; NamespaceConfig/GroupConfig health.",
    values_key="groupsyncHealth",
    params=(ParamSpec("window_days", "int", 30, "Sync events in the last N days.", lo=1, hi=3650),),
)

GRACE = timedelta(seconds=120)   # values.yaml config.scheduleGraceSeconds' default; a report tolerance, not the alert's


def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    since = window_start(ctx.now, params["window_days"])
    crs = snap.groupsyncs(cid)
    presence = snap.groupsync_presence(cid)
    syncs = {s["groupsync_name"]: s for s in snap.sync_counts(cid, since)}
    oc = snap.operator_configs(cid)
    rows = []
    for cr in crs:
        last = st.parse_time(cr["last_sync_at"])
        state = st.compute_state(last, cr["schedule"], ctx.now, GRACE)
        current = st.reconcile_error_is_current(st.parse_time(cr["error_at"]), last)
        s = syncs.get(cr["name"], {})
        rows.append([f"{cr['namespace']}/{cr['name']}", cr["schedule"] or "", state, cr["last_sync_at"] or "never",
                     cr["group_count"], s.get("syncs", 0), s.get("last_in_window") or "",
                     ("CURRENT: " + WITHHELD) if current and cr["has_error_message"] else ("stale error" if cr["error_at"] else "")])
    cfg_rows = [[c["kind"], c["name"], c["success_at"] or "", c["error_at"] or "",
                 "failing" if c["error_at"] and (not c["success_at"] or c["error_at"] > c["success_at"]) else "ok",
                 WITHHELD if c["has_error_message"] else ""] for c in oc["configs"]]
    sections = [
        Section("Summary", [KeyValues("Pipeline", [
            ("GroupSync CRD present", {None: "not observed", True: "yes", False: "NO — the operator is not installed"}[presence]),
            ("GroupSync CRs", len(crs)), ("Overdue", sum(1 for r in rows if r[2] == st.OVERDUE)), ("Late", sum(1 for r in rows if r[2] == st.LATE)),
            ("Current reconcile errors", sum(1 for r in rows if r[7].startswith("CURRENT"))),
            ("Policy operator CRDs present", {None: "not observed", True: "yes", False: "no"}[oc["present"]]),
            ("Policy CRs failing", sum(1 for r in cfg_rows if r[4] == "failing")),
        ])]),
        Section("GroupSync CRs", [
            Table("CRs", ["cr", "schedule", "state", "last sync", "groups", f"syncs in {params['window_days']} d", "last sync in window", "reconcile error"], rows, empty_text="no GroupSync CR"),
            Note("State is computed from the schedule and the last sync at generation time, with a 120 s grace — the Overview's rule (gsd/state.py compute_state). Error text is withheld: it can carry the directory bind DN.", "caveat"),
        ], page_break=True),
        Section("Policy operator", [Table("NamespaceConfig and GroupConfig", ["kind", "name", "last success", "last error", "status", "message"], cfg_rows,
                                          empty_text="no CRs" if oc["present"] else "the namespace-configuration-operator is not installed")], page_break=True),
    ]
    totals = {"groupsyncs": len(crs), "overdue": sum(1 for r in rows if r[2] == st.OVERDUE), "policy_crs": len(cfg_rows)}
    return Built(sections, totals, False, False)
