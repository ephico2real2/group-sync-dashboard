"""Per-user visibility: every personal endpoint scopes at the API handler.

The exposure this guards (REQUIREMENTS_per_user_visibility.md §1, measured): the dashboard
reads the cluster with its own ServiceAccount, so every authenticated reader used to see
the whole RBAC surface — eight-for-eight resources a plain user cannot `oc` list, plus the
login-failure record. The fix scopes each endpoint in the handler and passes the viewer
into the store as a bound parameter, the /api/dashboard/activity pattern generalised.

What is pinned here, and why it must not drift:

  * the SELF tier is the DEFAULT OUTCOME, reached on every failure — no resolver, a
    resolver error, an unrecognised answer, a missing identity. Only the exact string
    "all" from the tier resolver widens (requirements §5.4, decision D1).
  * a non-member's 403 is CONSTANT across "forbidden" and "nonexistent", because an
    endpoint that answers those differently is an existence oracle over the very names
    the self tier withholds.
  * self-matching is BYTE-EXACT. Measured on the live cluster: X-Forwarded-User arrives
    as `lateef.o`, exactly the form group_member/ocp_user carry — while login_event also
    holds an as-typed `LATEEF.O` row that must stay invisible to `lateef.o` (fail-closed;
    a NOCASE match was measured to defeat the index and would cross-leak between Users
    differing only by case).
  * governance-about-objects endpoints split by ruling: groupsyncs and events stay SERVED
    at both tiers (spec Q3), with exactly `ldap_filter` and `error_message` omitted at self
    — the spec's two named exceptions, both able to embed directory DNs and the gate group
    — while operator-configs and bindings/findings were reversed to the administrator tier
    at 03ad446. Refusing CR health outright would make the dashboard useless to the
    audience it still serves.
  * withheld aggregates are None, never fabricated zeros, and never recomputed over the
    visible subset — a number whose label lies is the count-versus-page defect class.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.store import Store
from gsd.timeutil import now_iso

VIEWER = "lateef.o"
OTHER = "jane.smith"
AS_VIEWER = {"X-Forwarded-User": VIEWER}


def _seed(db: str) -> None:
    """One cluster the viewer partially belongs to, with every personal dataset present."""
    store = Store(db)
    now = now_iso()
    store.upsert_cluster("c1", "https://x", True)
    store.replace_group_state("c1", [
        {"name": "team-a", "member_count": 2, "sync_provider": "corp_ldap",
         "group_synced_at": now, "ldap_uid": None},
        {"name": "team-b", "member_count": 1, "sync_provider": "corp_ldap",
         "group_synced_at": now, "ldap_uid": None},
        {"name": "secret-group", "member_count": 1, "sync_provider": "corp_ldap",
         "group_synced_at": now, "ldap_uid": None},
        # Zero members -> the `empty_group` alert, which the self tier must not receive.
        {"name": "lonely-group", "member_count": 0, "sync_provider": "corp_ldap",
         "group_synced_at": now, "ldap_uid": None},
        {"name": "gate-group", "member_count": 1, "sync_provider": "corp_ldap",
         "group_synced_at": now, "ldap_uid": "cn=gate,ou=groups,dc=example,dc=com"},
    ], now)
    store.sync_members("c1", {
        "team-a": [VIEWER, OTHER],
        "team-b": [VIEWER],
        "secret-group": [OTHER],
        "lonely-group": [],
        "gate-group": [VIEWER],
    }, {name: now for name in
        ("team-a", "team-b", "secret-group", "lonely-group", "gate-group")}, now)
    store.set_cluster_access_group(
        "c1", "cn=gate,ou=groups,dc=example,dc=com", "discovered", "gate-group", now)
    store.replace_user_bindings("c1", [
        {"binding_kind": "RoleBinding", "binding_namespace": "dev", "binding_name": "rb1",
         "role_kind": "ClusterRole", "role_name": "edit", "user_name": VIEWER,
         "is_platform": 0},
        {"binding_kind": "RoleBinding", "binding_namespace": "dev", "binding_name": "rb2",
         "role_kind": "ClusterRole", "role_name": "admin", "user_name": "jdoe",
         "is_platform": 0},
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "",
         "binding_name": "kubeadmin", "role_kind": "ClusterRole",
         "role_name": "cluster-admin", "user_name": "kubeadmin", "is_platform": 1},
    ], now)
    # A DANGLING binding: the group was seen operator-managed, its object is gone, and a
    # binding still names it. Beyond exercising the finding, this seeds the alert whose
    # construction loop once REBOUND the handler's `scope` variable — the regression
    # test_dangling_binding_alert_does_not_break_the_self_filter pins that.
    store.record_managed_groups(
        "c1", [{"name": "gone-group", "sync_provider": "corp_ldap"}], now)
    store.replace_bindings("c1", [
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "",
         "binding_name": "crb-gone", "role_kind": "ClusterRole", "role_name": "view",
         "group_name": "gone-group"},
    ], now)
    store.record_login_events("c1", [
        {"pod_name": "p1", "user_name": VIEWER, "outcome": "success",
         "at": "2026-08-09T10:00:00Z", "provider": "corp-ldap",
         "ldap_result_code": None, "detail": None, "observed_at": now},
        # The name AS TYPED — a case variant of the viewer, measured to exist on the live
        # cluster. Byte-exact self-matching must NOT return it.
        {"pod_name": "p1", "user_name": VIEWER.upper(), "outcome": "bad_password",
         "at": "2026-08-09T10:01:00Z", "provider": "corp-ldap",
         "ldap_result_code": "52e", "detail": None, "observed_at": now},
        {"pod_name": "p1", "user_name": OTHER, "outcome": "bad_password",
         "at": "2026-08-09T10:02:00Z", "provider": "corp-ldap",
         "ldap_result_code": "52e", "detail": None, "observed_at": now},
        {"pod_name": "p1", "user_name": "ghost.user", "outcome": "rejected",
         "at": "2026-08-09T10:03:00Z", "provider": "corp-ldap",
         "ldap_result_code": None, "detail": None, "observed_at": now},
    ])
    store.close()


def _client(tmp_path, tier_resolver=None, **overrides) -> TestClient:
    """A proxied app over the seeded store. Restrictions ride the DATACLASS DEFAULT (on),
    so this file breaks if anyone quietly flips it off."""
    db = str(tmp_path / "t.db")
    _seed(db)
    settings = Settings(
        clusters=[ClusterConfig("c1", "https://x", token_env="T")],
        db_path=db, oauth_proxy_enabled=True, **overrides,
    )
    return TestClient(build_app(settings, run_poller=False, tier_resolver=tier_resolver))


def _admin(viewer: str) -> str:
    return "all"


# ── The self tier, endpoint by endpoint ────────────────────────────────────────────────


def test_self_reader_sees_only_their_own_groups(tmp_path):
    c = _client(tmp_path)
    body = c.get("/api/clusters/c1/groups", headers=AS_VIEWER).json()
    assert body["scope"] == "self" and body["viewer"] == VIEWER
    assert [g["name"] for g in body["groups"]] == ["gate-group", "team-a", "team-b"]
    assert body["count"] == 3


def test_admin_sees_every_group(tmp_path):
    c = _client(tmp_path, tier_resolver=_admin)
    body = c.get("/api/clusters/c1/groups", headers=AS_VIEWER).json()
    assert body["scope"] == "all"
    assert len(body["groups"]) == 5, "the wide view must be exactly today's list"


def test_group_detail_403_is_constant_for_nonmember_and_nonexistent(tmp_path):
    """Answering those differently is an existence oracle over the withheld group list."""
    c = _client(tmp_path)
    real = c.get("/api/clusters/c1/groups/secret-group", headers=AS_VIEWER)
    fake = c.get("/api/clusters/c1/groups/no-such-group", headers=AS_VIEWER)
    assert real.status_code == fake.status_code == 403
    assert real.json() == fake.json()


def test_member_group_detail_is_served_in_full(tmp_path):
    c = _client(tmp_path)
    body = c.get("/api/clusters/c1/groups/team-a", headers=AS_VIEWER).json()
    assert body["scope"] == "self" and body["viewer"] == VIEWER
    assert {m["user_name"] for m in body["members"]} == {VIEWER, OTHER}, (
        "membership is the entitlement: a member sees their own group's whole roster"
    )


def test_self_reader_sees_only_their_own_user_row(tmp_path):
    c = _client(tmp_path)
    body = c.get("/api/clusters/c1/users", headers=AS_VIEWER).json()
    assert body["scope"] == "self"
    assert [u["user_name"] for u in body["users"]] == [VIEWER]
    assert body["users"][0]["group_count"] == 3


def test_other_profile_is_refused_before_existence(tmp_path):
    c = _client(tmp_path)
    real = c.get(f"/api/clusters/c1/users/{OTHER}", headers=AS_VIEWER)
    fake = c.get("/api/clusters/c1/users/no.such.person", headers=AS_VIEWER)
    assert real.status_code == fake.status_code == 403
    assert real.json() == fake.json()


def test_own_profile_is_served(tmp_path):
    c = _client(tmp_path)
    body = c.get(f"/api/clusters/c1/users/{VIEWER}", headers=AS_VIEWER).json()
    assert body["user"] == VIEWER and body["scope"] == "self"
    assert {g["group_name"] for g in body["groups"]} == {"team-a", "team-b", "gate-group"}


def test_self_logins_are_byte_exact_and_aggregate_free(tmp_path):
    """The most sensitive endpoint: own rows only, and the case-variant row stays hidden.

    `LATEEF.O` was typed by somebody at a keyboard and recorded as typed (measured live);
    only the wide tier may see it, because nothing proves it is the same person and a
    NOCASE join would cross-leak between distinct case-differing Users.
    """
    c = _client(tmp_path)
    body = c.get("/api/clusters/c1/logins", headers=AS_VIEWER).json()
    assert body["scope"] == "self" and body["viewer"] == VIEWER
    assert [a["user_name"] for a in body["attempts"]] == [VIEWER]
    assert body["total"] == 1, "the viewer's own whole-record count, not the cluster's 4"
    assert body["summary"] is None, "failure counts and distinct users are personnel data"
    assert body["ungoverned"] is None
    assert body["capture_started_at"], "window metadata describes the record, and stays"


def test_admin_logins_are_unchanged(tmp_path):
    c = _client(tmp_path, tier_resolver=_admin)
    body = c.get("/api/clusters/c1/logins", headers=AS_VIEWER).json()
    assert body["scope"] == "all"
    assert body["total"] == 4 and body["summary"]["distinct_users"] == 4
    assert len(body["attempts"]) == 4


def test_self_cannot_ask_for_another_users_logins(tmp_path):
    c = _client(tmp_path)
    r = c.get(f"/api/clusters/c1/logins?user={OTHER}", headers=AS_VIEWER)
    assert r.status_code == 403


def test_self_user_bindings_show_only_grants_naming_the_viewer(tmp_path):
    c = _client(tmp_path)
    body = c.get("/api/clusters/c1/user-bindings", headers=AS_VIEWER).json()
    assert body["scope"] == "self"
    assert [b["user_name"] for b in body["bindings"]] == [VIEWER]
    assert body["total"] == 1
    assert body["by_namespace"] is None, "the rollup aggregates other people's grants"
    assert body["excluded_platform"] is None


def test_self_membership_changes_are_the_viewers_only(tmp_path):
    c = _client(tmp_path)
    body = c.get("/api/clusters/c1/membership-changes", headers=AS_VIEWER).json()
    assert body["scope"] == "self"
    assert {ch["user_name"] for ch in body["changes"]} == {VIEWER}
    assert {ch["group_name"] for ch in body["changes"]} == {"team-a", "team-b", "gate-group"}


def test_self_cluster_access_is_own_gate_status_only(tmp_path):
    c = _client(tmp_path)
    body = c.get("/api/clusters/c1/cluster-access", headers=AS_VIEWER).json()
    assert body["scope"] == "self"
    assert body["gated"] is True and body["synced"] is True
    assert body["in_access_group"] is True, "the viewer is seeded into the gate group"
    assert body["dn"] is None and body["source"] is None and body["group_name"] is None
    assert body["summary"] is None
    assert body["access_without_login"] is None and body["login_without_access"] is None


def test_admin_cluster_access_is_unchanged(tmp_path):
    c = _client(tmp_path, tier_resolver=_admin)
    body = c.get("/api/clusters/c1/cluster-access", headers=AS_VIEWER).json()
    assert body["scope"] == "all"
    assert body["dn"] == "cn=gate,ou=groups,dc=example,dc=com"
    assert isinstance(body["access_without_login"], list)


def test_alerts_are_filtered_by_kind_at_self(tmp_path):
    """The feed keeps its invariant — every alert has a page behind it — per tier.

    The seed produces `empty_group` (its page is the self-scoped Groups tab, and an empty
    group can never contain the viewer) and `direct_user_binding` (an aggregate over other
    people's grants). Both must vanish at self, and the response must say it is narrowed
    rather than letting green mean hidden.
    """
    c = _client(tmp_path)
    wide = _client(tmp_path, tier_resolver=_admin)
    self_body = c.get("/api/alerts", headers=AS_VIEWER).json()
    wide_body = wide.get("/api/alerts", headers=AS_VIEWER).json()
    wide_kinds = {a["kind"] for a in wide_body["alerts"]}
    assert {"empty_group", "direct_user_binding"} <= wide_kinds
    self_kinds = {a["kind"] for a in self_body["alerts"]}
    assert not ({"empty_group", "direct_user_binding"} & self_kinds)
    assert self_body["scope"] == "self" and wide_body["scope"] == "all"
    assert self_body["count"] == len(self_body["alerts"])


def test_dangling_binding_alert_does_not_break_the_self_filter(tmp_path):
    """The regression this fixture's dangling binding exists for.

    The dangling-alert loop once used a local `scope` for its namespace label, which rebound
    the handler's tier variable — after one dangling finding the self filter compared against
    "cluster-wide" and passed EVERYTHING through: a fail-open. The fix renamed the local to
    `where`; this pins it, and the guard is load-bearing (it caught a real fail-open once).

    `dangling_binding` is itself WITHHELD at self now — it carries a group->role binding row,
    see test_alerts_do_not_carry_the_admin_only_surface_to_self — so the guard here is that a
    dangling finding in the feed does not disable the self filter for the REST: `empty_group`
    must still be filtered and the declared scope must survive the loop. If the shadowing bug
    returned, `scope` would rebind to "cluster-wide", the filter at api.py would be skipped,
    and `empty_group` would reappear — which is exactly what the second assertion catches.
    """
    c = _client(tmp_path)
    body = c.get("/api/alerts", headers=AS_VIEWER).json()
    kinds = {a["kind"] for a in body["alerts"]}
    assert "dangling_binding" not in kinds, (
        "the binding surface is administrator-only; a dangling finding must not reach self")
    assert "empty_group" not in kinds, (
        "a dangling finding in the feed must not disable the self filter for the rest"
    )
    assert body["scope"] == "self", "the declared scope must survive the alert loop"


def test_the_rbac_surface_is_refused_at_self_not_served(tmp_path):
    """REVERSES spec Q3, which called binding findings "data about objects" and served them
    whole. A binding row names which GROUP holds which ROLE, and measured on the reference
    cluster an ordinary reader — no `list clusterrolebindings`, no `list rolebindings`, no
    `list groups`, all three answered no by `oc auth can-i` — was handed 236 rows, 21 naming
    an admin role. That is which-group-to-join-for-admin, obtainable through the dashboard
    and not with `oc`.

    A 403, not a filtered list: a binding names whoever it names, so there is no honest
    per-reader subset. The UI turns this into a named refusal card, never a blank tab.
    """
    c = _client(tmp_path)
    for path in ("/api/clusters/c1/bindings/findings", "/api/clusters/c1/operator-configs"):
        r = c.get(path, headers=AS_VIEWER)
        assert r.status_code == 403, f"{path} served the cluster's RBAC surface to a self-tier reader"
        detail = r.json()["detail"]
        # THE SAME SENTENCE THE CARD DRAWS, and the operator asked for this exact phrase. The API
        # and the page are two renderings of one refusal; they used to word it differently ("For
        # administrators only." on the card, "reserved to the administrator tier" here), so a
        # caller comparing them could not tell they were the same control.
        # startswith, not `in`. `require_admin_tier` states that the phrase LEADS so a client
        # showing only the head of a `detail` still receives it — and an `in` assertion leaves
        # that unenforced, so moving the sentence to the end would keep the suite green while
        # breaking the property the comment promises.
        assert detail.startswith("For administrators only."), (
            f"{path}: the refusal must OPEN with the same sentence the UI card shows, so the "
            f"reader sees one phrasing whichever way they reach it and a truncating client still "
            f"gets the part that matters — got {detail!r}")
        # It must not hand the refused reader the way in. Same rule the card follows.
        for leak in ("cluster-admin", "cluster-reader", "clusterrolebinding", "can-i",
                     "visibility.", "SubjectAccessReview"):
            assert leak.lower() not in detail.lower(), (
                f"{path}: the refusal names {leak!r}, which tells a non-administrator what to ask "
                f"for — the escalation-path-as-shopping-list problem")


def test_the_admin_still_gets_the_whole_rbac_surface(tmp_path):
    """The other half: gating must not cost the administrator the view they are for."""
    c = _client(tmp_path, tier_resolver=_admin)
    findings = c.get("/api/clusters/c1/bindings/findings", headers=AS_VIEWER)
    assert findings.status_code == 200
    assert findings.json()["scope"] == "all" and findings.json()["viewer"] == VIEWER
    assert c.get("/api/clusters/c1/operator-configs", headers=AS_VIEWER).status_code == 200


def test_cr_health_stays_full_view_because_metrics_already_publishes_it(tmp_path):
    """groupsyncs and their events are NOT gated, and that is a ruling rather than an
    oversight: spec Q3 keeps CR health visible at both tiers — refusing it outright would
    be theatre while the unauthenticated /metrics names every CR and its state, and it
    would cost the Groups tab its per-provider colour slots, which read `data.groupsyncs`.
    Gate /metrics first if this should change.

    Visible is not identical, though. The SAME ruling names two exceptions, `ldap_filter`
    and `error_message`, omitted at the self tier because both can embed directory DNs and
    the gate group, which /metrics deliberately never carries — the omission and its
    exhaustive partition are pinned in tests/test_visibility.py. (The test name predates
    that projection shipping: "full view" here means the endpoint is neither refused nor
    row-scoped. It keeps its name because the round-2 review records cite it as a checked
    anchor.) What THIS test pins is the transport: still a 200 and still a BARE LIST at
    self — the field-withholding collection shape, like /api/clusters, never an envelope —
    and the events response untouched, because its rows carry timestamps, a schedule and a
    count, no error text.
    """
    c = _client(tmp_path)
    syncs = c.get("/api/clusters/c1/groupsyncs", headers=AS_VIEWER)
    assert syncs.status_code == 200 and isinstance(syncs.json(), list)
    events = c.get("/api/clusters/c1/groupsyncs/x/events", headers=AS_VIEWER).json()
    assert events["scope"] == "all"


def test_scope_and_viewer_are_declared_on_every_scoped_response(tmp_path):
    """The UI never derives the tier — each scoped payload states what it covers."""
    c = _client(tmp_path)
    for path in (
        "/api/clusters/c1/groups",
        "/api/clusters/c1/users",
        f"/api/clusters/c1/users/{VIEWER}",
        "/api/clusters/c1/groups/team-a",
        "/api/clusters/c1/logins",
        "/api/clusters/c1/user-bindings",
        "/api/clusters/c1/membership-changes",
        "/api/clusters/c1/cluster-access",
        "/api/alerts",
    ):
        body = c.get(path, headers=AS_VIEWER).json()
        assert body.get("scope") == "self", f"{path} did not declare its scope"
        assert body.get("viewer") == VIEWER, f"{path} did not declare its viewer"


# ── The failure directions — every road that is not a positive "all" ends at self ──────


def test_indeterminate_tier_fails_closed_to_self(tmp_path):
    """Requirements §5.4 / DoD 4: a SAR error or timeout must yield self, never wide."""
    def boom(viewer: str) -> str:
        raise TimeoutError("the API server did not answer")
    c = _client(tmp_path, tier_resolver=boom)
    body = c.get("/api/clusters/c1/groups", headers=AS_VIEWER).json()
    assert body["scope"] == "self" and len(body["groups"]) == 3


def test_a_junk_tier_answer_narrows_rather_than_widens(tmp_path):
    """Only the exact string "all" widens — the _visibility_setting discipline, applied
    to the resolver so a bug there cannot become a wide view."""
    c = _client(tmp_path, tier_resolver=lambda v: "ALL")
    assert c.get("/api/clusters/c1/groups", headers=AS_VIEWER).json()["scope"] == "self"


def test_no_resolver_wired_means_self(tmp_path):
    """An app built without the tier machinery restricts everyone — never the reverse."""
    c = _client(tmp_path, tier_resolver=None)
    assert c.get("/api/clusters/c1/groups", headers=AS_VIEWER).json()["scope"] == "self"


def test_no_identity_behind_the_proxy_is_refused_not_widened(tmp_path):
    """Proxy on, no header: personal data 403s; governance data still answers."""
    c = _client(tmp_path)
    assert c.get("/api/clusters/c1/users").status_code == 403
    assert c.get("/api/clusters/c1/logins").status_code == 403
    assert c.get("/api/clusters/c1/groupsyncs").status_code == 200


def test_restrictions_off_restores_the_wide_view(tmp_path):
    """`GSD_ENABLE_VIEW_RESTRICTIONS=false` is the deliberate, documented escape hatch."""
    c = _client(tmp_path, view_restrictions_enabled=False)
    body = c.get("/api/clusters/c1/groups", headers=AS_VIEWER).json()
    assert body["scope"] == "all" and len(body["groups"]) == 5


def test_proxy_off_never_derives_a_tier_from_the_header(tmp_path, caplog):
    """Without the proxy the header is caller-typed, so no restriction can be real —
    the app keeps today's proxy-less behaviour and says so loudly at startup; the chart
    refuses to render restrictions-on/proxy-off at all (template interlock)."""
    db = str(tmp_path / "t.db")
    _seed(db)
    settings = Settings(clusters=[ClusterConfig("c1", "https://x", token_env="T")],
                        db_path=db, oauth_proxy_enabled=False)
    with caplog.at_level("WARNING", logger="gsd.api"):
        c = TestClient(build_app(settings, run_poller=False))
    assert any("view restrictions" in r.message for r in caplog.records), (
        "the inert combination must be loud in the pod log, not silent"
    )
    body = c.get("/api/clusters/c1/groups",
                 headers={"X-Forwarded-User": "anyone.at.all"}).json()
    assert body["scope"] == "all" and body["viewer"] is None, (
        "a caller-typed header must not become an identity, in either direction"
    )


def test_the_resolver_is_not_consulted_when_restrictions_are_off(tmp_path):
    """The wide-by-choice deployment must not depend on the SAR path at all."""
    def fail_if_called(viewer: str) -> str:
        raise AssertionError("the resolver must not run when restrictions are off")
    c = _client(tmp_path, tier_resolver=fail_if_called, view_restrictions_enabled=False)
    assert c.get("/api/clusters/c1/groups", headers=AS_VIEWER).status_code == 200


def test_metrics_are_untouched_by_scoping(tmp_path):
    """§5.6: /metrics stays unauthenticated, aggregate, and username-free."""
    c = _client(tmp_path)
    text = c.get("/metrics").text
    assert "gsd_groups_total" in text
    assert VIEWER not in text and OTHER not in text


def test_alerts_do_not_carry_the_admin_only_surface_to_self(tmp_path):
    """The alert feed must not become the alternate path around require_admin_tier.

    A `dangling_binding` alert carries a group->role binding row and a
    `config_reconcile_error` alert carries an operator-config object and its error message —
    both from /bindings/findings and /operator-configs, which are the administrator tier now.
    Measured at 03ad446: with the fixture's dangling binding (crb-gone -> gone-group) plus one
    failing config, a self reader whom BOTH endpoints 403'd still received BOTH alerts, so the
    feed leaked exactly what the gate withholds.

    The failing config is written after `_client` seeds — `_seed` does not touch the operator-
    config tables, so the extra row survives the re-seed the admin app performs.
    """
    c = _client(tmp_path)
    store = Store(str(tmp_path / "t.db"))
    store.replace_operator_configs("c1", [
        {"kind": "NamespaceConfig", "name": "restricted-tenants", "error_at": now_iso(),
         "error_message": "failed to reconcile RBAC template", "success_at": None},
    ], now_iso())
    store.close()

    wide = _client(tmp_path, tier_resolver=_admin)
    wide_kinds = {a["kind"] for a in wide.get("/api/alerts", headers=AS_VIEWER).json()["alerts"]}
    assert {"dangling_binding", "config_reconcile_error"} <= wide_kinds, (
        "the administrator must still see the whole feed")

    body = c.get("/api/alerts", headers=AS_VIEWER).json()
    self_kinds = {a["kind"] for a in body["alerts"]}
    assert body["scope"] == "self"
    assert "dangling_binding" not in self_kinds, (
        "a group->role binding row must not reach self via alerts while /bindings/findings 403s")
    assert "config_reconcile_error" not in self_kinds, (
        "the operator-config surface must not reach self via alerts while /operator-configs 403s")


def test_operator_config_summary_is_withheld_at_self_on_the_cluster_list(tmp_path):
    """The one Overview aggregate with NO /metrics analogue, so the /api/clusters card leaks
    it to a self reader unless the handler withholds it.

    group_count and the binding-finding counts on each card are already world-readable on the
    unauthenticated /metrics (gsd_groups_total, gsd_bindings_total{finding=...}), so serving
    them at both tiers is not a leak. The operator-config {total, failing} pair is NOT on
    /metrics (there is no gsd_operator_configs_total), so it is a genuinely private aggregate
    reaching self through the one endpoint that must stay reachable for the cluster selector.
    Withheld as None at self — never a fabricated 0, which would read as "operator installed,
    nothing failing" to a reader who cannot know it was narrowed — present for an admin, with
    reachable/status/error untouched so an ordinary reader can still tell a broken dashboard
    from an empty one.
    """
    c = _client(tmp_path)
    store = Store(str(tmp_path / "t.db"))
    store.replace_operator_configs("c1", [
        {"kind": "NamespaceConfig", "name": "multitenant", "error_at": None,
         "error_message": None, "success_at": now_iso()},
    ], now_iso())
    store.close()
    admin = _client(tmp_path, tier_resolver=_admin)

    self_row = next(r for r in c.get("/api/clusters", headers=AS_VIEWER).json() if r["id"] == "c1")
    admin_row = next(r for r in admin.get("/api/clusters", headers=AS_VIEWER).json()
                     if r["id"] == "c1")

    assert self_row["operator_configs"] is None, (
        "the operator-config summary has no /metrics analogue and must be withheld at self")
    assert admin_row["operator_configs"] == {"total": 1, "failing": 0}, (
        "the administrator still gets the summary")
    # The rest of the card is untouched at both tiers — the selector and the broken-vs-empty
    # signal must keep working for every reader.
    assert self_row["reachable"] == admin_row["reachable"]
    assert self_row["status"] == admin_row["status"]
    assert self_row["group_count"] == admin_row["group_count"]
    assert self_row["dangling_bindings"] == admin_row["dangling_bindings"]


# ── The self tier withholds the CLUSTER's bindings, not the reader's own ───────────────
#
# `require_admin_tier` used to say the binding surface was withheld and "none of it is what a
# non-administrator gets". That reads as "a narrowed reader sees no binding at all", which is
# false and was never true: `/groups/{name}` and `/users/{name}` embed the bindings on the
# reader's OWN access path, because the narrowed tier exists to answer "what access do I have and
# how did I get it" — unanswerable without naming the binding that granted it.
#
# The distinction is scope, and these tests hold both halves of it, so neither a future change
# that quietly widens this nor one that quietly removes it can land unnoticed.


def _binding_on(store, group: str, role: str, name: str) -> None:
    """One ClusterRoleBinding granting `role` to `group`, replacing the seed's set."""
    store.replace_bindings("c1", [
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "",
         "binding_name": name, "role_kind": "ClusterRole", "role_name": role,
         "group_name": group},
    ], now_iso())


def test_a_self_tier_member_sees_the_bindings_on_their_own_group(tmp_path):
    """Deliberate: they can read that their group holds cluster-admin, and which binding does it.

    This is the honest reading of the tier — it answers the reader's own access path in full.
    `/bindings/findings` still refuses them, because that is everyone's access, cluster-wide.
    """
    db = str(tmp_path / "t.db")
    c = _client(tmp_path)
    _binding_on(Store(db), "team-a", "cluster-admin", "admin-crb")

    body = c.get("/api/clusters/c1/groups/team-a", headers=AS_VIEWER).json()
    assert body["scope"] == "self"
    assert [(b["role_name"], b["binding_name"]) for b in body["bindings"]] == [
        ("cluster-admin", "admin-crb")
    ], "a member must still see how their own group's access was granted"

    # …while the cluster-wide surface stays refused for the same reader in the same breath.
    assert c.get("/api/clusters/c1/bindings/findings", headers=AS_VIEWER).status_code == 403


def test_that_visibility_is_bounded_by_membership_and_cannot_enumerate(tmp_path):
    """The other half: a non-member learns nothing, and cannot tell absent from forbidden.

    If a real group answered 403 and an absent one 404, the endpoint would be a group-name
    oracle for a reader who belongs to none of them — so the membership check runs before any
    existence lookup and both answers are byte-identical.
    """
    db = str(tmp_path / "t.db")
    c = _client(tmp_path)
    _binding_on(Store(db), "secret-group", "cluster-admin", "secret-crb")

    forbidden = c.get("/api/clusters/c1/groups/secret-group", headers=AS_VIEWER)
    absent = c.get("/api/clusters/c1/groups/no-such-group-anywhere", headers=AS_VIEWER)

    assert forbidden.status_code == 403 and absent.status_code == 403
    assert forbidden.json() == absent.json(), (
        "the two refusals differ, so a reader can tell which group names exist"
    )
    assert "cluster-admin" not in forbidden.text and "secret-crb" not in forbidden.text
