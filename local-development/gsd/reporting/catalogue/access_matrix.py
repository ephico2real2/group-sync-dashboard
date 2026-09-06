"""Report 2 — the subject × namespace × role matrix, by role NAME (role rules are not read)."""

from __future__ import annotations

from ..model import Note, Section, Table
from ..snapshot import Snapshot
from .common import Built, ParamSpec, ReportSpec, RunContext, cut, ns_label, rank

SPEC = ReportSpec(
    name="access-matrix", title="Access matrix",
    summary="Every subject (group or direct user), the namespaces it is bound in and the role granted — the 'who has access where' sheet, by role name.",
    values_key="accessMatrix",
    params=(
        ParamSpec("subject_kind", "enum", "all", "Which subjects to list.", choices=("all", "groups", "users")),
        ParamSpec("namespace_prefix", "str", "", "Only namespaces starting with this prefix (empty = all, including cluster scope)."),
    ),
)


def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    prefix = params["namespace_prefix"]
    rows: list[list] = []
    if params["subject_kind"] in ("all", "groups"):
        for g in snap.group_bindings(cid):
            ns = ns_label(g["binding_namespace"])
            if prefix and not (g["binding_namespace"].startswith(prefix)):
                continue
            rows.append(["group", g["group_name"], ns, g["role_name"], rank(g["role_name"]), g["binding_name"],
                         g["managed_source"] or "hand-made", g["finding"]])
    if params["subject_kind"] in ("all", "users"):
        for u in snap.user_bindings(cid):
            ns = ns_label(u["binding_namespace"])
            if prefix and not (u["binding_namespace"].startswith(prefix)):
                continue
            rows.append(["user", u["user_name"], ns, u["role_name"], rank(u["role_name"]), u["binding_name"], "direct grant", "direct_user"])
    rows.sort(key=lambda r: (r[0], r[1], r[2] != "(cluster-scoped)", r[2], -r[4], r[5]))
    per_subject: dict[tuple[str, str], dict] = {}
    for r in rows:
        k = (r[0], r[1])
        s = per_subject.setdefault(k, {"namespaces": set(), "worst": 1, "bindings": 0})
        s["namespaces"].add(r[2]); s["worst"] = max(s["worst"], r[4]); s["bindings"] += 1
    shown, truncated = cut([r[:4] + r[5:] for r in rows])
    summary = Table("Subjects", ["kind", "subject", "namespaces", "bindings", "highest role rank"],
                    [[k[0], k[1], len(v["namespaces"]), v["bindings"], {4: "cluster-admin", 3: "admin", 2: "edit", 1: "other"}[v["worst"]]]
                     for k, v in sorted(per_subject.items(), key=lambda kv: (-kv[1]["worst"], kv[0]))])
    matrix = Table("Matrix", ["kind", "subject", "namespace", "role", "binding", "source", "classification"], shown,
                   note="Ordered subject, then cluster scope first, then role rank. Role rank: cluster-admin > admin > edit > other — a NAME ranking, not an evaluation of rules.")
    sections = [Section("Summary", [summary]), Section("Matrix", [matrix], page_break=True)]
    return Built(sections, {"rows": len(rows), "subjects": len(per_subject)}, truncated, False)
