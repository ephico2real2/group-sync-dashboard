"""Report 7 — login attempts in a window. Follows loginCapture.enabled; refuses to build without it."""

from __future__ import annotations

from ..model import KeyValues, Note, Section, Table
from ..snapshot import Snapshot
from .common import Built, ParamSpec, ReportSpec, RunContext, ValidationError, cut, window_start

SPEC = ReportSpec(
    name="login-activity", title="Login activity",
    summary="Attempts by outcome and provider, per-user successes and failures, and rejected attempts resolved against the login gate.",
    values_key="loginActivity", needs=("loginCapture",),
    params=(
        ParamSpec("window_days", "int", 30, "Attempts in the last N days.", lo=1, hi=3650, unit="days"),
        ParamSpec("users", "csv", [], "Only these users (empty = everyone).", source="users", group="subject"),
        ParamSpec("groups", "csv", [], "Only members of these groups (empty = everyone).", source="groups", group="subject"),
    ),
)


def _refusal(row: dict) -> str:
    # gsd/api.py#_refusal_reason, applied to the snapshot's columns; the vocabulary is the API's.
    gated = row["in_access_group"]
    if gated is None:
        return ""
    if gated:
        return "membership_disagrees"
    if row["known_user"] or row["has_history"]:
        return "not_gated"
    return "no_record"


def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    if not ctx.settings.login_capture_enabled:
        raise ValidationError("login-activity needs login capture (loginCapture.enabled); nothing writes login_event without it")
    cid = ctx.cluster["id"]
    since = window_start(ctx.now, params["window_days"])
    # The subject scope: named users, and the members of named groups (#149 R7). The summary by outcome
    # and provider is the scope's too — a scoped pack whose totals counted the whole cluster's attempts
    # beside its own users misread (review of #222, Codex M1).
    keep = set(params["users"]) | (snap.members_of_groups(cid, params["groups"]) if params["groups"] else set())
    scoped = bool(params["users"] or params["groups"])
    summary = snap.login_summary(cid, since, keep if scoped else None)
    per_user = [r for r in snap.login_by_user(cid, since, None) if not scoped or r["user_name"] in keep]
    rejected = snap.rejected_attempts(cid, since)
    if scoped:
        rejected = [r for r in rejected if r["user_name"] in keep]
    status = snap.login_capture_status(cid)
    gate = snap.access_group(cid)
    per_user_rows, t1 = cut([[u["user_name"], u["successes"], u["failures"], u["last_success"] or "", u["last_attempt"]] for u in per_user])
    rejected_rows, t2 = cut([[r["at"], r["user_name"], r["provider"] or "", _refusal(r)] for r in rejected])
    scope_note = ([Section("Scope", [Note("Every figure is narrowed to the named subjects: " + ", ".join(sorted(keep)) + ".", "note")])]
                  if scoped else [])
    sections = scope_note + [
        Section("Summary", [
            KeyValues("Window", [("From", since), ("To", ctx.now.strftime("%Y-%m-%dT%H:%M:%SZ")),
                                 ("Watching since", status["started_at"] if status else "not yet"), ("Last log read", status["last_read_at"] if status else "never"),
                                 ("Login gate", f"{gate['group_name']} ({gate['source']})" if gate and gate["group_name"] else "none known")]),
            Table("Attempts by outcome and provider", ["outcome", "provider", "attempts"], [[s["outcome"], s["provider"], s["n"]] for s in summary], empty_text="no attempts in the window"),
        ]),
        Section("Per user", [Table("Users", ["user", "successes", "failures", "last success", "last attempt"], per_user_rows, empty_text="none")], page_break=True),
        Section("Rejected attempts", [
            Table("Rejected", ["at", "user", "provider", "resolution"], rejected_rows, empty_text="none"),
            Note("Resolution: not_gated — a real member outside the gate group; no_record — no synced membership or history (a typo, a probe, or an unsynced branch); membership_disagrees — in the gate group per the synced Group while the directory refused (a sync lagging a removal). Empty when no gate group is known.", "caveat"),
        ], page_break=True),
    ]
    totals = {"attempts": sum(int(s["n"]) for s in summary), "users": len(per_user), "rejected": len(rejected)}
    return Built(sections, totals, t1 or t2, False)
