"""Per-user visibility: two tiers, decided by the cluster, enforced at the API handler.

THE SEAM THIS SUITE PINS (the cross-lens contract; a drift in any half is a test failure
here rather than a quiet disagreement):

  * ``Settings.view_restrictions_enabled`` — bool, default True (decision D1: restrictions
    are ON by default). Wire: values ``visibility.enabled`` → env
    ``GSD_ENABLE_VIEW_RESTRICTIONS`` → configmap key ``visibilityEnabled``. The
    spelling is load-bearing — see TestViewRestrictions in test_config.py.
  * ``gsd.kube.TierResolver`` decides ``"all" | "self"`` per viewer: one fresh Group read
    plus one SubjectAccessReview naming the viewer AND their groups, per-viewer verdict
    cache (``ttl_seconds`` — therefore the exact worst-case window a revoked administrator
    retains the wide view), failures never cached and never raised. Its unit tests live in
    tests/test_visibility_tier.py; here it is stubbed through the app.state seam.
  * ``build_app`` publishes its resolver at ``app.state.tier_resolver`` and every handler
    consults it PER REQUEST — the indirection that lets these tests install a stub.
  * Every scoped response carries ``scope`` ("self" | "all") and ``viewer`` — the
    /api/dashboard/activity contract, generalised. The UI renders those fields and never
    decides the tier itself (tests/test_ui.py).

Measured background these tests encode (docs/REQUIREMENTS_per_user_visibility.md §4/D2 and
the spec's arbitration): a SubjectAccessReview naming ONLY the user answers allowed=false
for john.doe, who holds cluster-admin through Group/app-ocp-rbac-demo-cluster-admin —
reproduced twice on the reference cluster; adding spec.groups flips it to allowed=true with
the CRB named in the reason. Every real administrator there is group-granted, so a
user-only SAR inverts the feature. That is why half this file is about spec.groups.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from gsd import loginlog
from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.logincapture import event_dict
from gsd.loginlog import LoginAttempt
from gsd.store import Store

GATE_DN = "cn=gate,ou=Groups,dc=example,dc=com"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def H(user: str) -> dict:
    return {"X-Forwarded-User": user}


def _seed(db_path: str) -> None:
    """Two people, one gate, one dangling binding, one case-variant login.

    alice — in g-adm and the gate group; one success recorded as `alice` and one failure
            recorded as `ALICE`, the caps-lock variant (a DIFFERENT recorded name: self-
            matching is byte-exact, so the variant row is visible only to the wide tier).
    bob   — removed from g-adm and added to g-dev across two polls, so membership CHANGES
            exist for him; holds access through g-dev and is NOT in the gate group.
    root  — the administrator persona; a member of nothing, which is exactly the point:
            the tier comes from a SubjectAccessReview, not from membership rows.
    """
    now = datetime.now(UTC)
    store = Store(db_path)
    store.upsert_cluster("c1", "https://api.c1.example.com:6443", True)
    store.upsert_cluster("c2", "https://api.c2.example.com:6443", True)
    store.record_poll("c1", "ok", None)
    # A degraded cluster, so /api/alerts carries a row EVERY tier must keep seeing.
    store.record_poll("c2", "auth_failed", "401 Unauthorized - token invalid or expired")

    store.replace_groupsync_state(
        "c1",
        [{
            "name": "ldap-sync", "namespace": "group-sync-operator",
            "schedule": "*/30 * * * *",
            # Directory structure — omitted at the self tier along with error_message.
            "ldap_filter": "(&(objectClass=groupOfNames)(cn=app-*))",
            "last_sync_at": _iso(now - timedelta(minutes=4)),
            "generation": 2, "provider_keys": ["ldap-sync_ldap"],
        }],
        _iso(now),
    )
    store.upsert_reconcile_error(
        "c1", "ldap-sync", _iso(now - timedelta(minutes=2)), 2,
        "LDAP bind failed for cn=svc,ou=people: invalid credentials",
    )

    store.replace_group_state(
        "c1",
        [
            {"name": "g-adm", "member_count": 1, "sync_provider": "ldap-sync_ldap",
             "group_synced_at": _iso(now - timedelta(minutes=4)),
             "ldap_uid": "cn=g-adm,ou=Groups,dc=example,dc=com"},
            {"name": "g-dev", "member_count": 1, "sync_provider": "ldap-sync_ldap",
             "group_synced_at": _iso(now - timedelta(minutes=4)),
             "ldap_uid": "cn=g-dev,ou=Groups,dc=example,dc=com"},
            {"name": "gate", "member_count": 1, "sync_provider": "ldap-sync_ldap",
             "group_synced_at": _iso(now - timedelta(minutes=4)), "ldap_uid": GATE_DN},
        ],
        _iso(now),
    )
    # Two polls so membership CHANGES exist: bob leaves g-adm and joins g-dev.
    store.sync_members(
        "c1", {"g-adm": ["alice", "bob"], "g-dev": [], "gate": ["alice"]},
        {}, _iso(now - timedelta(hours=1)),
    )
    store.sync_members(
        "c1", {"g-adm": ["alice"], "g-dev": ["bob"], "gate": ["alice"]},
        {}, _iso(now - timedelta(minutes=4)),
    )
    store.replace_users("c1", {"alice": "Alice A", "bob": "Bob B"}, _iso(now))
    store.set_cluster_access_group("c1", GATE_DN, "config", "gate", _iso(now))

    # One managed group that vanished + a binding still naming it -> a `dangling` finding
    # and its alert, both of which are admin-only.
    store.record_managed_groups(
        "c1", [{"name": "gone-group", "sync_provider": "ldap-sync_ldap"}],
        _iso(now - timedelta(days=1)))
    store.replace_bindings(
        "c1",
        [
            {"binding_kind": "RoleBinding", "binding_namespace": "ns1",
             "binding_name": "gone-rb", "role_kind": "ClusterRole",
             "role_name": "admin", "group_name": "gone-group"},
            {"binding_kind": "RoleBinding", "binding_namespace": "ns1",
             "binding_name": "adm-rb", "role_kind": "ClusterRole",
             "role_name": "view", "group_name": "g-adm"},
        ],
        _iso(now),
    )
    store.replace_user_bindings(
        "c1",
        [
            {"binding_kind": "RoleBinding", "binding_namespace": "ns1",
             "binding_name": "alice-edit", "role_kind": "ClusterRole",
             "role_name": "edit", "user_name": "alice", "is_platform": 0},
            {"binding_kind": "RoleBinding", "binding_namespace": "ns2",
             "binding_name": "bob-admin", "role_kind": "ClusterRole",
             "role_name": "admin", "user_name": "bob", "is_platform": 0},
        ],
        _iso(now),
    )
    attempts = [
        (LoginAttempt("alice", loginlog.OUTCOME_SUCCESS, now - timedelta(minutes=10),
                      provider="ldap"), "oauth-openshift-aaa"),
        # The same person as TYPED with caps lock on: a different recorded name. Byte-exact
        # self-matching means this row is wide-tier only (COLLATE NOCASE was measured to
        # defeat the login_event_by_user index, and OpenShift User names are themselves
        # case-sensitive, so a case-blind match could cross-leak two distinct Users).
        (LoginAttempt("ALICE", loginlog.OUTCOME_BAD_PASSWORD, now - timedelta(minutes=9),
                      provider="ldap", ldap_result_code=49), "oauth-openshift-aaa"),
        (LoginAttempt("bob", loginlog.OUTCOME_BAD_PASSWORD, now - timedelta(minutes=8),
                      provider="ldap", ldap_result_code=49), "oauth-openshift-aaa"),
    ]
    store.record_login_events("c1", [event_dict(a, p, _iso(now)) for a, p in attempts])
    store.record_login_read("c1", _iso(now - timedelta(seconds=30)))
    store.close()


def _settings(db: str, **kw) -> Settings:
    kw.setdefault("oauth_proxy_enabled", True)
    kw.setdefault("login_capture_enabled", True)
    return Settings(
        clusters=[ClusterConfig("c1", "https://api.c1.example.com:6443", token_env="X"),
                  ClusterConfig("c2", "https://api.c2.example.com:6443", token_env="Y")],
        db_path=db, **kw)


class _MapResolver:
    """A stub for the app.state.tier_resolver seam: viewer name -> tier, default self.

    Counting `calls` is what proves the machinery is INERT when the feature is disabled —
    off must mean no SubjectAccessReview traffic at all, not a review whose answer is
    ignored.
    """

    def __init__(self, tiers: dict[str, str]):
        self.tiers = tiers
        self.calls = 0

    def resolve(self, viewer: str) -> str:
        self.calls += 1
        return self.tiers.get(viewer, "self")


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> str:
    path = str(tmp_path_factory.mktemp("vis") / "gsd.db")
    _seed(path)
    return path


@pytest.fixture(scope="module")
def client(db):
    """Proxy on, restrictions on (the D1 default), root is the administrator."""
    app = build_app(_settings(db), run_poller=False)
    app.state.tier_resolver = _MapResolver({"root": "all"})
    with TestClient(app) as c:
        yield c


# ── The two tiers, endpoint by endpoint ──────────────────────────────────────────────────

class TestTwoTiersPerEndpoint:
    def test_groups_are_scoped_to_membership_at_self(self, client):
        body = client.get("/api/clusters/c1/groups", headers=H("alice")).json()
        assert body["scope"] == "self" and body["viewer"] == "alice"
        assert {g["name"] for g in body["groups"]} == {"g-adm", "gate"}

    def test_groups_are_complete_at_all(self, client):
        body = client.get("/api/clusters/c1/groups", headers=H("root")).json()
        assert body["scope"] == "all"
        assert {g["name"] for g in body["groups"]} == {"g-adm", "g-dev", "gate"}

    def test_group_detail_403_is_constant_for_nonmember_and_nonexistent(self, client):
        """No existence oracle: a group outside the viewer's membership and a group that
        does not exist must be indistinguishable, or the 403 itself enumerates groups."""
        a = client.get("/api/clusters/c1/groups/g-dev", headers=H("alice"))
        b = client.get("/api/clusters/c1/groups/no-such-group", headers=H("alice"))
        assert a.status_code == 403 and b.status_code == 403
        assert a.json() == b.json()
        assert client.get("/api/clusters/c1/groups/g-adm",
                          headers=H("alice")).status_code == 200
        assert client.get("/api/clusters/c1/groups/g-dev",
                          headers=H("root")).status_code == 200

    def test_users_list_is_own_row_only_at_self(self, client):
        body = client.get("/api/clusters/c1/users", headers=H("alice")).json()
        assert body["scope"] == "self"
        assert [u["user_name"] for u in body["users"]] == ["alice"]
        wide = client.get("/api/clusters/c1/users", headers=H("root")).json()
        assert {u["user_name"] for u in wide["users"]} == {"alice", "bob"}

    def test_user_detail_is_own_profile_or_a_constant_403(self, client):
        assert client.get("/api/clusters/c1/users/alice",
                          headers=H("alice")).status_code == 200
        other = client.get("/api/clusters/c1/users/bob", headers=H("alice"))
        ghost = client.get("/api/clusters/c1/users/nobody", headers=H("alice"))
        assert other.status_code == 403 and ghost.status_code == 403
        assert other.json() == ghost.json()
        assert client.get("/api/clusters/c1/users/bob",
                          headers=H("root")).status_code == 200

    def test_logins_are_scoped_byte_exact_at_self(self, client):
        """`ALICE` is alice with caps lock on — and a DIFFERENT recorded name. The match
        is byte-exact on purpose (the NOCASE variant defeats the index and could cross-
        leak two Users differing only by case), so the variant row is wide-tier only and
        the UI carries the 'as typed' caveat instead."""
        body = client.get("/api/clusters/c1/logins", headers=H("alice")).json()
        assert body["scope"] == "self" and body["viewer"] == "alice"
        assert {a["user_name"] for a in body["attempts"]} == {"alice"}
        assert body["total"] == 1, "total must describe the viewer's record, not the cluster's"
        assert body["summary"] is None, "the whole-record summary is personnel data"
        assert body["ungoverned"] is None, "the ungoverned-accounts finding names other people"

    def test_logins_are_complete_at_all(self, client):
        body = client.get("/api/clusters/c1/logins", headers=H("root")).json()
        assert {a["user_name"] for a in body["attempts"]} == {"alice", "ALICE", "bob"}
        assert body["summary"]["distinct_users"] == 3
        assert body["ungoverned"] is not None

    def test_user_bindings_are_own_grants_only_at_self(self, client):
        body = client.get("/api/clusters/c1/user-bindings", headers=H("alice")).json()
        assert body["scope"] == "self"
        assert {b["user_name"] for b in body["bindings"]} == {"alice"}
        assert body["by_namespace"] is None, "the rollup aggregates other people's grants"
        assert body["excluded_platform"] is None
        wide = client.get("/api/clusters/c1/user-bindings", headers=H("root")).json()
        assert {b["user_name"] for b in wide["bindings"]} == {"alice", "bob"}
        assert wide["by_namespace"], "the admin rollup went missing"

    def test_membership_changes_are_scoped_to_the_viewer(self, client):
        body = client.get("/api/clusters/c1/membership-changes", headers=H("bob")).json()
        assert body["scope"] == "self"
        assert {e["user_name"] for e in body["changes"]} == {"bob"}
        wide = client.get("/api/clusters/c1/membership-changes", headers=H("root")).json()
        assert {e["user_name"] for e in wide["changes"]} == {"alice", "bob"}

    def test_cluster_access_is_own_gate_status_at_self(self, client):
        """The viewer's own admission status is theirs; the gate DN, the member lists and
        the cluster summary are other people's data and directory structure."""
        body = client.get("/api/clusters/c1/cluster-access", headers=H("bob")).json()
        assert body["scope"] == "self" and body["viewer"] == "bob"
        assert body["gated"] is True
        assert body["in_access_group"] is False, "bob is not in the gate group"
        assert body.get("dn") is None
        assert body["access_without_login"] is None
        assert body["login_without_access"] is None
        assert body["summary"] is None
        mine = client.get("/api/clusters/c1/cluster-access", headers=H("alice")).json()
        assert mine["in_access_group"] is True
        wide = client.get("/api/clusters/c1/cluster-access", headers=H("root")).json()
        assert wide["dn"] == GATE_DN and "access_without_login" in wide

    def test_the_overview_counts_stay_full_at_self(self, client):
        """/api/clusters is the credential-less /metrics content with names on the
        clusters: suppressing behind login what the pod serves without login is theatre."""
        mine = client.get("/api/clusters", headers=H("alice")).json()
        wide = client.get("/api/clusters", headers=H("root")).json()
        assert mine == wide


# ── Fail closed ──────────────────────────────────────────────────────────────────────────

class TestFailClosed:
    def test_a_broken_tier_check_degrades_to_self_not_500(self, db):
        """Requirements §5.4, forced: the resolver contract says resolve() never raises,
        and the handlers must not trust that — an administrator on a flaky API server
        sees their OWN data and a banner, never an error page and never everyone's."""
        class Exploding:
            def resolve(self, viewer):
                raise RuntimeError("SAR path down")

        app = build_app(_settings(db), run_poller=False)
        app.state.tier_resolver = Exploding()
        with TestClient(app) as c:
            r = c.get("/api/clusters/c1/groups", headers=H("root"))
        assert r.status_code == 200
        body = r.json()
        assert body["scope"] == "self", "an indeterminate tier must be SELF, never wide"
        assert body["groups"] == [], "root is a member of nothing seeded"

    def test_no_identity_behind_the_proxy_is_refused_not_widened(self, client):
        """No X-Forwarded-User with the proxy on: there is nobody to scope to, and 'show
        everything' is the one wrong answer. The activity endpoint's rule, generalised."""
        assert client.get("/api/clusters/c1/groups").status_code == 403
        assert client.get("/api/clusters/c1/logins").status_code == 403


# ── The one switch ───────────────────────────────────────────────────────────────────────

class TestTheSwitch:
    def test_disabling_restrictions_restores_the_wide_view(self, db):
        """D1: `visibility.enabled: false` -> GSD_ENABLE_VIEW_RESTRICTIONS=false restores
        today's behaviour as a deliberate documented choice. Off means INERT — zero
        SubjectAccessReviews — not a review whose answer is ignored."""
        app = build_app(_settings(db, view_restrictions_enabled=False), run_poller=False)
        stub = _MapResolver({})          # would answer "self" for everyone if consulted
        app.state.tier_resolver = stub
        with TestClient(app) as c:
            body = c.get("/api/clusters/c1/groups", headers=H("alice")).json()
        assert body["scope"] == "all", "disabled must be labelled as the wide view"
        assert {g["name"] for g in body["groups"]} == {"g-adm", "g-dev", "gate"}
        assert stub.calls == 0, "disabled must mean no tier machinery runs at all"


# ── The wire contract the UI renders from ────────────────────────────────────────────────

class TestWireContract:
    SCOPED = [
        "/api/clusters/c1/groups",
        "/api/clusters/c1/users",
        "/api/clusters/c1/logins",
        "/api/clusters/c1/user-bindings",
        "/api/clusters/c1/membership-changes",
        "/api/clusters/c1/cluster-access",
    ]

    @pytest.mark.parametrize("path", SCOPED)
    def test_scope_and_viewer_are_declared_on_every_scoped_response(self, client, path):
        """The UI never decides the tier (the Groups search-box scar, as a rule): it can
        only render what the response declares, so every scoped payload must declare."""
        mine = client.get(path, headers=H("alice")).json()
        assert mine["scope"] == "self" and mine["viewer"] == "alice"
        wide = client.get(path, headers=H("root")).json()
        assert wide["scope"] == "all" and wide["viewer"] == "root"

    def test_whoami_reports_the_tier_so_the_ui_never_guesses(self, client):
        mine = client.get("/api/whoami", headers=H("alice")).json()
        assert mine["visibility"] == {"scope": "self", "enabled": True}
        wide = client.get("/api/whoami", headers=H("root")).json()
        assert wide["visibility"] == {"scope": "all", "enabled": True}

    def test_whoami_carries_no_visibility_claim_without_an_identity(self, client):
        body = client.get("/api/whoami").json()
        assert "visibility" not in body


# ── DoD 2: an administrator sees exactly what they see today ─────────────────────────────

def _strip(obj):
    """Drop the clock-derived GroupSync fields before comparing two requests made moments
    apart — `state` and `next_expected` are computed from now() and can legitimately
    differ across a minute boundary. Everything else must be byte-identical."""
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in ("state", "next_expected")}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


class TestAdminSeesExactlyToday:
    ENDPOINTS = [
        "/api/clusters",
        "/api/alerts",
        "/api/clusters/c1/groups",
        "/api/clusters/c1/users",
        "/api/clusters/c1/user-bindings",
        "/api/clusters/c1/logins",
        "/api/clusters/c1/cluster-access",
        "/api/clusters/c1/membership-changes",
        "/api/clusters/c1/bindings/findings",
        "/api/clusters/c1/groupsyncs",
        "/api/clusters/c1/operator-configs",
    ]

    def test_the_wide_tier_equals_the_disabled_view_per_endpoint(self, db):
        """Definition of done #2, as an equality: with restrictions ON an administrator's
        response is identical to the same request with restrictions OFF — the feature
        must be invisible to the people it does not restrict."""
        on = build_app(_settings(db), run_poller=False)
        on.state.tier_resolver = _MapResolver({"root": "all"})
        off = build_app(_settings(db, view_restrictions_enabled=False), run_poller=False)
        with TestClient(on) as a, TestClient(off) as b:
            for path in self.ENDPOINTS:
                x = a.get(path, headers=H("root"))
                y = b.get(path, headers=H("root"))
                assert x.status_code == y.status_code == 200, path
                assert _strip(x.json()) == _strip(y.json()), (
                    f"the admin view drifted from today's behaviour on {path}"
                )
