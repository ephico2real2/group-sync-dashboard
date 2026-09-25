"""Home (#158): the viewer's own access on one cluster, derived once, server-side.

The page every reader lands on answers "what can I reach, and how?" for the person asking and nobody
else. The arithmetic behind its sentences lives here rather than in the page so that a number and its
label change together (SPEC_per_user_visibility: never silently recompute a number that keeps its old
label) and so the rules are testable without a browser:

- ROLE_RANK orders the four built-in ClusterRoles whose meaning the platform fixes
  (cluster-admin ⊃ admin ⊃ edit ⊃ view). A grant is *covered* by a cluster-wide role when that role is
  at least as strong: removing the covered grant would not change what the person can do. Any other
  role name is a custom role whose meaning this dashboard does not know — never covered, never covers.
- A platform namespace (``openshift-*``, ``kube-*``, ``default``) is tagged, so a reader can tell the
  console's own per-user grant from a team's.
- The membership history is folded the way a person reads it: a sync that added a dozen groups at once
  is one line, a group that flapped five times in half an hour is one line, everything else is one line
  per change. Baseline rows (#177: "first observed") are not changes and are left out.
"""
from __future__ import annotations

from datetime import datetime

ROLE_RANK = {"cluster-admin": 0, "admin": 1, "edit": 2, "view": 3}
HOME_CHANGES_DAYS = 30        # the "What changed" window
HOME_CHANGES_ITEMS = 12       # lines shown; `more` counts the rest
HOME_EVENTS_LIMIT = 500       # rows read per cluster before folding — a person's own history, never a cluster's
FLAP_MIN_CHANGES = 3          # a group changing this often inside the window is one "flapping" line
BATCH_MIN_GROUPS = 3          # this many groups changing in one sync is one "at once" line
# THE SHIPPED DEFAULT, and only the default since #255. These two constants are OpenShift's and
# Kubernetes' own conventions; an estate's platform is wider — on the reference cluster this rule calls
# `cert-manager`, `cert-manager-operator`, `group-sync-operator`, `group-sync-dashboard`,
# `hostpath-provisioner`, `kyverno` and `namespace-configuration-operator` application namespaces, which
# is seven wrong out of 106. `Settings.platform_namespaces` carries the estate's own answer and every
# caller that has a Settings passes it; these remain the value it defaults to.
# The shipped namespace defaults — a namespace here, or starting with a prefix here, is the platform's;
# values.yaml `platformNamespaces.prefixes`/`names` replace them, `additionalPrefixes`/`additionalSuffixes`/
# `additionalNames` widen them (config.py PlatformNamespaces).
# PLATFORM-CLASSIFICATION (#255, #353): the namespace prefixes
PLATFORM_NAMESPACE_PREFIXES = ("openshift-", "kube-")
PLATFORM_NAMESPACES = frozenset({"default", "openshift", "kube-system", "kube-public", "kube-node-lease"})  # PLATFORM-CLASSIFICATION (#255, #353): the names
# OpenShift's per-project controller bindings, excluded by design in EVERY namespace, matched on all three
# parts — the binding's name, its ClusterRole, and the subject in the binding's own namespace — the shape
# the controller writes ("auto-managed by a controller"); nothing broader, and no values key widens it (the
# operator, 2026-09-24). The third such binding, `system:image-pullers` → ClusterRole `system:image-puller`
# → Group `system:serviceaccounts:<namespace>`, is decided by the store's Group `system:` rule (store.py
# _FINDING_CASE) and is listed here so all three stand in one place.
# PLATFORM-CLASSIFICATION (#255, #353): the controller defaults, exact shape
PLATFORM_CONTROLLER_BINDINGS = frozenset({
    ("system:image-builders", "system:image-builder", "builder"),
    ("system:deployers", "system:deployer", "deployer"),
})


# PLATFORM-CLASSIFICATION (#255, #353): the shipped rule alone, for a caller with no Settings
def is_platform_namespace(name: str) -> bool:
    """The shipped rule. Callers holding a `Settings` use `settings.platform_namespaces.matches`
    instead — this is what that defaults to, and what a caller without settings still gets."""
    return name in PLATFORM_NAMESPACES or name.startswith(PLATFORM_NAMESPACE_PREFIXES)


def is_builtin_clusterrole(role_kind: str, role_name: str) -> bool:
    """Only a ClusterRole named for one of the four the platform fixes is ranked. Kubernetes has ONE
    ClusterRole ``admin``; a namespaced Role of that name is a different object with whatever rules its
    author gave it, and ranking it would let the page say "removing this would not change what you can
    do" about access nothing else grants (review of #158, Grok)."""
    return role_kind == "ClusterRole" and role_name in ROLE_RANK


def covers_grant(wide_role: str | None, role: str, *,
                 wide_kind: str = "ClusterRole", role_kind: str = "ClusterRole") -> bool:
    """A cluster-wide built-in ClusterRole makes a grant of another built-in ClusterRole redundant when
    the cluster-wide one is at least as strong (cluster-wide ``edit`` covers a namespaced ``edit``).

    Aggregation is the residual this does not model: a cluster can add rules to ``edit`` that ``admin``
    does not carry, so "already includes it" is the platform's default relation, not a proof. The four
    built-ins are what the mock ranks and what an access review reads; anything else is never covered."""
    return (is_builtin_clusterrole(wide_kind, wide_role or "")
            and is_builtin_clusterrole(role_kind, role)
            and ROLE_RANK[wide_role] <= ROLE_RANK[role])


def _rank(role: str) -> tuple[int, str]:
    return ROLE_RANK.get(role, len(ROLE_RANK)), role


# PLATFORM-CLASSIFICATION (#255, #353): Home's per-namespace flag — `platform` is settings.platform_namespaces.matches when the API calls
# this, and the shipped rule alone for a caller without Settings (OB2, review of #361)
def derive_answer(groups: list[dict], via: list[dict], direct: list[dict],
                  *, platform=is_platform_namespace) -> dict:
    """The headline and the cards, from the three reads the drill-downs already serve.

    ``groups``: ``Store.user_groups`` rows; ``via``: ``Store.user_bindings`` rows (each carrying
    ``via_group``); ``direct``: ``Store.direct_user_bindings`` rows naming the viewer.
    """
    # Keyed by (kind, name): a Role and a ClusterRole of the same name are two objects, and merging
    # them would put one's groups under the other's row (review of #158, Grok).
    wide: dict[tuple[str, str], dict] = {}

    def wide_row(role_kind: str, role_name: str) -> dict:
        return wide.setdefault((role_kind, role_name),
                               {"role_name": role_name, "role_kind": role_kind,
                                "via_groups": [], "direct": False, "bindings": 0})

    for b in via:
        if not b["binding_namespace"]:
            row = wide_row(b["role_kind"], b["role_name"])
            row["bindings"] += 1
            if b["via_group"] not in row["via_groups"]:
                row["via_groups"].append(b["via_group"])
    for d in direct:
        if not d["binding_namespace"]:
            row = wide_row(d["role_kind"], d["role_name"])
            row["bindings"] += 1
            row["direct"] = True
    ranked = [r["role_name"] for r in wide.values()
              if is_builtin_clusterrole(r["role_kind"], r["role_name"])]
    top = min(ranked, key=lambda n: ROLE_RANK[n]) if ranked else None
    for row in wide.values():
        stronger = [n for n in ranked
                    if is_builtin_clusterrole(row["role_kind"], row["role_name"])
                    and ROLE_RANK[n] < ROLE_RANK[row["role_name"]]]
        row["covered_by"] = min(stronger, key=lambda n: ROLE_RANK[n]) if stronger else None
    cluster_wide = sorted(wide.values(), key=lambda r: _rank(r["role_name"]))

    namespaces: dict[str, dict] = {}

    def ns_row(name: str) -> dict:
        # PLATFORM-CLASSIFICATION (#255, #353): Home's namespace rows, by the classifier the API passes in (settings.platform_namespaces.matches)
        return namespaces.setdefault(name, {"name": name, "platform": platform(name), "grants": []})

    for b in via:
        if b["binding_namespace"]:
            ns_row(b["binding_namespace"])["grants"].append({
                "role_name": b["role_name"], "role_kind": b["role_kind"], "via_group": b["via_group"],
                "binding_name": b["binding_name"],
                "covered": covers_grant(top, b["role_name"], role_kind=b["role_kind"])})
    for d in direct:
        if d["binding_namespace"]:
            ns_row(d["binding_namespace"])["grants"].append({
                "role_name": d["role_name"], "role_kind": d["role_kind"], "via_group": None,
                "binding_name": d["binding_name"],
                "covered": covers_grant(top, d["role_name"], role_kind=d["role_kind"])})
    ns_rows = sorted(namespaces.values(), key=lambda n: n["name"])
    for n in ns_rows:
        n["grants"].sort(key=lambda g: (_rank(g["role_name"]), g["via_group"] or ""))
        n["covered"] = all(g["covered"] for g in n["grants"])

    per_group: dict[str, list[dict]] = {}
    for b in via:
        per_group.setdefault(b["via_group"], []).append(b)
    out_groups = []
    for g in groups:
        rows = per_group.get(g["group_name"], [])
        out_groups.append({
            "group_name": g["group_name"], "sync_provider": g["sync_provider"],
            "first_seen_at": g["first_seen_at"], "last_seen_at": g["last_seen_at"],
            "grants": len(rows),
            "cluster_wide_roles": sorted({r["role_name"] for r in rows if not r["binding_namespace"]}, key=_rank),
            "namespaces": sorted({r["binding_namespace"] for r in rows if r["binding_namespace"]}),
            "gives_top": top is not None and any(not r["binding_namespace"] and r["role_name"] == top for r in rows),
        })
    out_groups.sort(key=lambda g: (not g["gives_top"], -g["grants"], g["group_name"]))
    return {
        "top_role": top,
        "cluster_wide": cluster_wide,
        "cluster_wide_bindings": sum(r["bindings"] for r in cluster_wide),
        "namespaces": ns_rows,
        "namespaces_covered": sum(1 for n in ns_rows if n["grants"] and n["covered"]),
        "groups": out_groups,
        "groups_total": len(groups),
        "groups_granting": sum(1 for g in out_groups if g["grants"]),
        "direct_count": len(direct),
    }


def _minutes_between(first: str, last: str) -> int:
    a, b = datetime.fromisoformat(first), datetime.fromisoformat(last)
    return int(round((b - a).total_seconds() / 60))


def group_changes(events: list[dict], since: str) -> dict:
    """The viewer's own membership history, folded. ``events`` are ``membership_event`` rows, each
    with a ``cluster`` key added by the caller; ``since`` is the window's ISO start.

    Flapping first (a group with FLAP_MIN_CHANGES or more changes in the window is one line, its
    events taken out of everything else), then batches (the remaining events of one cluster, one
    direction and one observed_at — one sync — with BATCH_MIN_GROUPS or more groups), then the rest one
    line each. Newest first; HOME_CHANGES_ITEMS lines and how many more.
    """
    rows = [e for e in events if not e.get("baseline") and e["observed_at"] >= since]
    by_group: dict[tuple[str, str], list[dict]] = {}
    for e in rows:
        by_group.setdefault((e["cluster"], e["group_name"]), []).append(e)
    items: list[dict] = []
    consumed: set[int] = set()
    for (cluster, group), evs in by_group.items():
        if len(evs) >= FLAP_MIN_CHANGES:
            evs.sort(key=lambda e: e["observed_at"])
            items.append({"kind": "flap", "cluster": cluster, "group_name": group, "changes": len(evs),
                          "span_minutes": _minutes_between(evs[0]["observed_at"], evs[-1]["observed_at"]),
                          "latest": evs[-1]["change"], "observed_at": evs[-1]["observed_at"]})
            consumed.update(id(e) for e in evs)
    by_sync: dict[tuple[str, str, str], list[dict]] = {}
    for e in rows:
        if id(e) not in consumed:
            by_sync.setdefault((e["cluster"], e["change"], e["observed_at"]), []).append(e)
    for (cluster, change, observed_at), evs in by_sync.items():
        if len(evs) >= BATCH_MIN_GROUPS:
            items.append({"kind": "batch", "cluster": cluster, "change": change, "observed_at": observed_at,
                          "count": len(evs), "groups": sorted(e["group_name"] for e in evs)})
        else:
            items.extend({"kind": "single", "cluster": cluster, "change": change,
                          "group_name": e["group_name"], "observed_at": observed_at} for e in evs)
    items.sort(key=lambda i: i["observed_at"], reverse=True)
    shown, rest = items[:HOME_CHANGES_ITEMS], items[HOME_CHANGES_ITEMS:]
    # The page says "N more changes", so N counts CHANGES, not the cards they were folded into: one
    # leftover batch of eleven groups is eleven more changes, not one (review of #158, Grok).
    more = sum(i["changes"] if i["kind"] == "flap" else i["count"] if i["kind"] == "batch" else 1
               for i in rest)
    # `since` is NOT returned. It is derived from the request's clock, so it differs on every poll — and the
    # page's unchanged-payload skip compares the whole payload, so echoing it meant Home, alone among the
    # pages, repainted every 60 s and threw away scroll, selection and focus (OB3, integration review, C3;
    # measured: three polls, three renders, the only differing slot `changes.since`, two seconds apart). The
    # window is named by `window_days` and every item carries its own `observed_at`; nothing renders `since`.
    return {"items": shown, "more": more, "more_items": len(rest),
            "changes": len(rows), "window_days": HOME_CHANGES_DAYS}
