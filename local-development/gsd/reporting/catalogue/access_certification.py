"""Report 11 — a user access certification pack: per subject, the access held, with the reviewer's
decision columns left blank. What an identity-governance product calls a campaign artefact,
built from this data: groups → bindings → namespaces, direct users → bindings."""

from __future__ import annotations

from ..model import KeyValues, Note, Section, Table
from ..snapshot import Snapshot
from .common import Built, ParamSpec, ReportSpec, RunContext, ValidationError, cut, ns_label, rank, roster_table, subject_filter, subject_scope

SPEC = ReportSpec(
    name="access-certification", title="Access certification pack",
    summary="Per group (with roster) and per directly-bound user: every binding held, with Approve / Revoke / Comment columns and a sign-off block for the named reviewer.",
    values_key="accessCertification",
    params=(
        ParamSpec("campaign", "str", "", "Campaign name printed on every page (e.g. 'Q3 2026 access review').", required=True),
        ParamSpec("due", "date", "", "Due date, YYYY-MM-DD.", required=True),
        ParamSpec("reviewer", "str", "", "The reviewer this pack is for (a name; printed, not verified).", required=True),
        *subject_scope(),
        ParamSpec("group_mnemonic", "csv", [], "Business mnemonics: each resolves to the exact group its namespaces pin "
                  "(the namespace group label), never by naming convention.", source="mnemonics"),
        ParamSpec("include_members", "bool", True, "Rosters of each group — a certification without names cannot be signed. Recorded in the provenance."),
    ),
)

DECISION_COLS = ["Approve", "Revoke", "Comment"]


def _scope_words(params: dict, resolved: set[str]) -> str:
    parts = []
    if params.get("users"):
        parts.append(f"users: {', '.join(params['users'])}")
    if params.get("groups"):
        parts.append(f"groups: {', '.join(params['groups'])}")
    if params.get("group_mnemonic"):
        # The exact groups the mnemonics resolved to are printed with them: a resolved group nothing
        # binds has no section below, and the header is where a reviewer reads why (review of #222, OB3).
        parts.append(f"mnemonics: {', '.join(params['group_mnemonic'])} ({', '.join(sorted(resolved))})")
    return "; ".join(parts) or "all"


def _resolve_mnemonics(snap: Snapshot, ctx: RunContext, cid: str, mnemonics: list[str]) -> set[str]:
    """The exact groups the mnemonics pin, or a ValidationError naming why none could be found — the
    same refusals the namespace report gives its mnemonic selection. A pack is a document a reviewer
    signs: one that certified nothing because the deployment captures no mnemonic dimension, the copy
    predates the capture, or the value matches nothing must be a failed run with a reason, never a
    clean empty pack (review of #222, OB3 — measured: every one of those built with totals 0/0)."""
    if not mnemonics:
        return set()
    labels = tuple(ctx.settings.namespace_selector_labels)
    mnemonic_key, group_key = (labels[0] if labels else ""), ctx.settings.namespace_group_label
    if not mnemonic_key or not group_key:
        raise ValidationError("mnemonic resolution is not configured on this deployment; set reporting.namespaceSelector.labels "
                              "(the first entry is the mnemonic) and reporting.namespaceGroupLabel, or pick groups directly")
    if not snap.selector_capture_present():
        raise ValidationError("this snapshot carries no namespace-label capture (it predates the capture); pick groups directly or wait for the next snapshot")
    if not snap.namespaces_for_metadata(cid, mnemonic_key, mnemonics):
        raise ValidationError(f"no namespace carries {mnemonic_key} with value(s) {', '.join(mnemonics)}")
    resolved = snap.groups_for_mnemonics(cid, mnemonic_key, group_key, mnemonics)
    if not resolved:
        raise ValidationError(f"the namespaces carrying {mnemonic_key} in ({', '.join(mnemonics)}) pin no group through {group_key}; "
                              "the certification would cover nothing — pick groups directly")
    return resolved


def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    resolved = _resolve_mnemonics(snap, ctx, cid, params["group_mnemonic"])
    header = Section("Campaign", [
        KeyValues("Certification", [("Campaign", params["campaign"]), ("Due", params["due"]), ("Reviewer", params["reviewer"]),
                                    ("Scope", _scope_words(params, resolved)), ("Cluster", cid), ("Data as of", ctx.snapshot_stamp)]),
        Note("For each line: tick Approve to keep the access as it stands, Revoke to remove it, and write the reason in Comment. Sign the last page. This pack records the state the dashboard observed; it does not change anything.", "note"),
    ])
    sections = [header]
    truncated = False
    include_members = params["include_members"]
    n_groups = n_users = 0
    only_users, only_groups = subject_filter(params)
    # A mnemonic names groups through the namespaces that pin them; it narrows like a picked group.
    if params["group_mnemonic"]:
        only_groups = (only_groups or set()) | resolved
        only_users = only_users if only_users is not None else set()
    if only_groups is None or only_groups:
        g_rows = snap.group_bindings(cid)
        if only_groups:
            g_rows = [g for g in g_rows if g["group_name"] in only_groups]
        by_group: dict[str, list[dict]] = {}
        for g in g_rows:
            by_group.setdefault(g["group_name"], []).append(g)
        rosters = snap.group_rosters(cid, sorted(by_group)) if include_members else {}
        for name in sorted(by_group):
            bindings = sorted(by_group[name], key=lambda g: (-rank(g["role_name"]), g["binding_namespace"] != "", g["binding_namespace"], g["binding_name"]))
            rows, t = cut([[ns_label(b["binding_namespace"]), b["role_name"], b["binding_name"], b["finding"], "☐", "☐", ""] for b in bindings])
            truncated = truncated or t
            blocks = [Table(f"Bindings of {name}", ["namespace", "role", "binding", "classification", *DECISION_COLS], rows)]
            if include_members:
                blocks.append(roster_table(f"Members of {name}", rosters.get(name, [])))
            sections.append(Section(f"Group: {name}", blocks, page_break=True))
            n_groups += 1
    if only_users is None or only_users:
        u_rows = snap.user_bindings(cid)
        if only_users:
            u_rows = [u for u in u_rows if u["user_name"] in only_users]
        by_user: dict[str, list[dict]] = {}
        for u in u_rows:
            by_user.setdefault(u["user_name"], []).append(u)
        for name in sorted(by_user):
            rows, t = cut([[ns_label(b["binding_namespace"]), b["role_name"], b["binding_name"], "☐", "☐", ""] for b in
                           sorted(by_user[name], key=lambda b: (-rank(b["role_name"]), b["binding_namespace"] != "", b["binding_namespace"]))])
            truncated = truncated or t
            sections.append(Section(f"User (direct grants): {name}", [
                Table(f"Direct bindings of {name}", ["namespace", "role", "binding", *DECISION_COLS], rows),
                Note("A direct grant is outside group governance; certifying it means accepting that it will not be revoked by removing the person from any group.", "caveat"),
            ], page_break=True))
            n_users += 1
    seen_groups = {s.title[len("Group: "):] for s in sections if s.title.startswith("Group: ")}
    seen_users = {s.title[len("User (direct grants): "):] for s in sections if s.title.startswith("User (direct grants): ")}
    missing = sorted((set(only_groups or ()) - seen_groups) | (set(only_users or ()) - seen_users))
    if missing:   # a named subject with no binding is said, not silently absent (review of #222, Grok)
        sections.append(Section("Named but not bound", [Note("No binding was observed for: " + ", ".join(missing) + " — nothing to certify.", "caveat")]))
    sections.append(Section("Sign-off", [KeyValues("Reviewer attestation", [
        ("Campaign", params["campaign"]), ("Reviewer", params["reviewer"]), ("Due", params["due"]),
        ("Reviewed on", "______________________"), ("Signature", "______________________"),
        ("Subjects certified", f"{n_groups} group(s), {n_users} directly bound user(s)"),
    ])], page_break=True))
    return Built(sections, {"groups": n_groups, "users": n_users}, truncated, include_members)
