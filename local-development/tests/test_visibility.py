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
    store.replace_users("c1", [
        {"user_name": "alice", "full_name": "Alice A", "created_at": _iso(now - timedelta(days=9)),
         "providers": ["ldap-local"], "has_identity": True},
        {"user_name": "bob", "full_name": "Bob B", "created_at": _iso(now - timedelta(days=3)),
         "providers": ["ldap-local"], "has_identity": True},
    ], _iso(now))
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
        resp = client.get("/api/clusters/c1/users", headers=H("alice"))
        body = resp.json()
        assert body["scope"] == "self"
        assert [u["user_name"] for u in body["users"]] == ["alice"]
        # Your own display name comes with your row; nobody else's name is anywhere in the
        # response — the join must not widen what the privacy predicate narrowed.
        assert body["users"][0]["full_name"] == "Alice A"
        assert "Bob B" not in resp.text
        wide = client.get("/api/clusters/c1/users", headers=H("root")).json()
        assert {u["user_name"] for u in wide["users"]} == {"alice", "bob"}
        assert {u["full_name"] for u in wide["users"]} == {"Alice A", "Bob B"}

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

    def test_groupsyncs_omit_directory_detail_at_self(self, client):
        """CR health is governance data and stays visible; ldap_filter and error_message
        can embed directory DNs and the gate group, which /metrics deliberately never
        carries — the same line drawn here. The spec ruled this and named this test; the
        code never caught up until now, and the fixture measures why it mattered: the
        error text carries the service bind DN, and the narrowed personas cannot
        `oc get` the CR, so this endpoint was their only source.

        The keys are OMITTED, not nulled: /api/clusters withholds by nulling because its
        card must still render the key's slot, while here the whole point is that the
        self payload does not carry the field at all — and provider_keys stays, because
        index.html#function crSlot (the Groups tab, which the self tier DOES see) cannot
        colour without it, and /groups already serves the same <cr>_<provider> string to
        this reader on their own rows."""
        crs = client.get("/api/clusters/c1/groupsyncs", headers=H("alice")).json()
        assert crs, "the CR list itself must stay visible at self"
        for cr in crs:
            assert "ldap_filter" not in cr
            assert "error_message" not in cr
            assert cr["name"] == "ldap-sync" and "state" in cr, (
                "CR health must survive the projection — the spec keeps it, only the two "
                "directory diagnostics go")
            assert cr["provider_keys"] == ["ldap-sync_ldap"], (
                "crSlot reads provider_keys off this payload to colour the Groups tab")
        wide = client.get("/api/clusters/c1/groupsyncs", headers=H("root")).json()
        assert any(cr.get("ldap_filter") for cr in wide)
        assert any(cr.get("error_message") for cr in wide)

    def test_groupsync_tier_policy_is_exhaustive(self, db, client):
        """Every key this endpoint can emit is classified: allowlist ∪ withheld tiles the
        wide row exactly, so a NEW store column or enrich key is a red build here rather
        than a quiet self-tier leak (denylist failure) or a quiet hole (stale allowlist).

        The expected universe is derived from the CODE, not from a fixture payload: a row
        from gsd/store.py#Store.groupsyncs carries exactly its SELECT's columns — SQL
        emits every selected column even when NULL — plus the stitched provider_keys, and
        gsd/api.py#enrich adds its derived keys unconditionally. A fixture-derived
        expectation would only prove the fixture's shape, and a key that appears only
        with production data would slip past it."""
        from gsd.api import (
            SELF_TIER_GROUPSYNC_FIELDS,
            WITHHELD_AT_SELF_GROUPSYNC_FIELDS,
            enrich,
        )

        store = Store(db)
        try:
            store_row = store.groupsyncs("c1")[0]
        finally:
            store.close()
        universe = set(enrich(store_row, datetime.now(UTC), timedelta(seconds=120)))

        allow = set(SELF_TIER_GROUPSYNC_FIELDS)
        assert len(allow) == len(SELF_TIER_GROUPSYNC_FIELDS), "duplicate allowlist entry"
        assert allow.isdisjoint(WITHHELD_AT_SELF_GROUPSYNC_FIELDS), (
            "a field ruled both served and withheld is two policies for one key")
        assert universe == allow | WITHHELD_AT_SELF_GROUPSYNC_FIELDS, (
            "an unclassified GroupSync field exists — rule on it (allowlist or withheld) "
            "before it ships to either tier")

        wide = client.get("/api/clusters/c1/groupsyncs", headers=H("root")).json()[0]
        mine = client.get("/api/clusters/c1/groupsyncs", headers=H("alice")).json()[0]
        assert set(wide) == universe, "the wide tier serves the code-derived universe whole"
        assert tuple(mine) == SELF_TIER_GROUPSYNC_FIELDS, (
            "the self row is exactly the allowlist, in the wide row's own key order")

    def test_reconcile_alert_replaces_only_the_self_tier_detail(self, client):
        """The alert bus must not reopen the diagnostic /groupsyncs closes:
        gsd/state.py#compute_alerts copies error_message straight into `detail`, so
        before this fix a self reader whom the CR endpoint would deny the text was
        handed the full bind DN by /api/alerts on every page refresh.

        The detail is REPLACED, never omitted: index.html#function esc collapses a
        nullish detail to "", so an absent key renders as an empty reason column, which
        reads as "no reason exists" when the truth is "withheld" — the fabricated-absence
        this repo already bans for aggregates. The KIND stays, because the existence of a
        current reconcile failure is actionable and not secret."""
        mine = client.get("/api/alerts", headers=H("alice")).json()["alerts"]
        wide = client.get("/api/alerts", headers=H("root")).json()["alerts"]
        mine_error = next(a for a in mine if a["kind"] == "reconcile_error")
        wide_error = next(a for a in wide if a["kind"] == "reconcile_error")

        assert mine_error["detail"] == (
            "reconcile failed; diagnostic text is withheld in the self view"
        )
        assert "cn=svc,ou=people" not in mine_error["detail"]
        assert mine_error["subject"] == "ldap-sync", (
            "the kind and its subject stay actionable at self; only the text is withheld")
        assert wide_error["detail"] == (
            "LDAP bind failed for cn=svc,ou=people: invalid credentials"
        )

    def test_admin_keeps_the_diagnostic_bytes_on_both_endpoints(self, client):
        """The operator's constraint 1, made executable: error_message is operational
        data an administrator acts on quickly, so the wide tier keeps ldap_filter,
        error_message and the alert detail BYTE-FOR-BYTE — narrowing anything an admin
        sees is a defect, not a bonus, and this test is what stops somebody tidying the
        diagnostic away later."""
        wide_cr = client.get("/api/clusters/c1/groupsyncs", headers=H("root")).json()[0]
        wide_alerts = client.get("/api/alerts", headers=H("root")).json()["alerts"]
        wide_error = next(a for a in wide_alerts if a["kind"] == "reconcile_error")

        secret = "LDAP bind failed for cn=svc,ou=people: invalid credentials"
        assert wide_cr["error_message"] == wide_error["detail"] == secret, (
            "the admin diagnostic must be the operator's own text, identical on both "
            "endpoints — not a rewrite of either")
        assert wide_cr["ldap_filter"] == "(&(objectClass=groupOfNames)(cn=app-*))"

    def test_self_refresh_payload_does_not_carry_the_bind_dn(self, client):
        """What a self browser DOWNLOADS every refresh — not what any tab paints.
        index.html#async function refresh fetches /groupsyncs and /api/alerts on every
        page, so 'the Overview tab is admin-only' never protected these fields; the
        payload landed in the reader's network tab, page memory and any proxy log
        regardless of which tab they were on. Delivered counts as leaked."""
        alerts = client.get("/api/alerts", headers=H("alice")).json()["alerts"]
        syncs = client.get("/api/clusters/c1/groupsyncs", headers=H("alice")).json()
        events = client.get(
            "/api/clusters/c1/groupsyncs/ldap-sync/events", headers=H("alice")
        ).json()
        blob = repr(alerts) + repr(syncs) + repr(events)
        assert "cn=svc,ou=people" not in blob
        assert "(&(objectClass=groupOfNames)(cn=app-*))" not in blob

        wide_blob = repr(client.get("/api/alerts", headers=H("root")).json())
        assert "cn=svc,ou=people" in wide_blob, (
            "the probe string must be real at the wide tier, or the absence above proves "
            "nothing")


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


# ── The Usage tab's second, stricter tier (docs/SPEC_usage_admin_tier.md) ─────────────────


def _seed_usage(db: str) -> None:
    """Three people's activity rows, so `scope: all` is visibly different from `scope: self`."""
    store = Store(db)
    store.record_user_activity([
        {"user_name": u, "day": "2026-08-08", "email": f"{u}@x.com",
         "first_seen_at": "2026-08-08T09:00:00Z", "last_seen_at": "2026-08-08T17:00:00Z",
         "request_count": n}
        for u, n in (("alice", 5), ("bob", 9), ("carol", 3))
    ])
    store.close()


def _usage_app(db: str, *, wide: dict, usage, **kw):
    """An app with the two tier seams stubbed INDEPENDENTLY — the whole point of the design.

    `wide` maps viewer -> wide tier; `usage` is a stub object (so a test can pass an exploding
    or junk resolver) or a dict, which is wrapped. The real resolvers build_app makes against
    the configured cluster are overwritten here and never called.
    """
    app = build_app(_settings(db, **kw), run_poller=False)
    app.state.tier_resolver = _MapResolver(wide)
    app.state.usage_tier_resolver = _MapResolver(usage) if isinstance(usage, dict) else usage
    return app


class TestUsageAdminTier:
    """Usage is the one dataset with no `oc` equivalent — it lives only in the dashboard's own
    database — so it gets a stricter threshold than the wide audit views the auditor persona
    (cluster-reader) keeps. The two tiers are decided by separate resolvers with separate
    caches and must never share a verdict."""

    def test_the_usage_admin_tier_sees_every_row_and_the_aggregates(self, tmp_path):
        """Spec test 1: a reader who passes the usage tier gets scope=all, all rows, summary."""
        db = str(tmp_path / "gsd.db")
        _seed_usage(db)
        with TestClient(_usage_app(db, wide={"admin": "all"}, usage={"admin": "all"})) as c:
            body = c.get("/api/dashboard/activity", headers=H("admin")).json()
        assert body["scope"] == "all"
        assert {r["user_name"] for r in body["activity"]} == {"alice", "bob", "carol"}
        assert body["summary"]["distinct_users"] == 3
        assert body["summary"]["interactions"] == 17

    def test_restrictions_off_does_not_widen_usage(self, tmp_path):
        """`visibility.enabled=false` widens CLUSTER data and must NOT widen Usage.

        This branch had no test, and an audit proved it: mutating `usage_scope`'s
        not-restricted return from "self" to "all" left the ENTIRE suite green. It is the one
        boundary in the feature where the safe answer is the narrow one even though every other
        view has just gone wide, so a future refactor tidying "two returns that look the same"
        into one would silently publish colleagues' presence records to every authenticated
        reader — the dataset with no `oc` equivalent, on a deployment whose operator asked only
        to stop scoping cluster data.

        `userActivity.visibility: all` remains the deliberate way to widen Usage, and the test
        below it pins that it still works. This asserts the other half: that turning cluster
        scoping off is NOT that switch.
        """
        db = str(tmp_path / "gsd.db")
        _seed_usage(db)
        # Restrictions off. The usage resolver would say "all" if it were consulted — it must
        # not be, so a stub that admits everyone still yields the self view.
        app = _usage_app(db, wide={"anyone": "all"}, usage={"anyone": "all"},
                         view_restrictions_enabled=False)
        with TestClient(app) as c:
            groups = c.get("/api/clusters/c1/groups", headers=H("anyone")).json()
            usage = c.get("/api/dashboard/activity", headers=H("anyone")).json()
        assert groups["scope"] == "all", "restrictions off means cluster data is wide"
        assert usage["scope"] == "self", (
            "restrictions off must NOT widen Usage — presence records are not cluster data"
        )
        assert {r["user_name"] for r in usage["activity"]} <= {"anyone"}

    def test_the_usage_tier_is_independent_of_the_wide_tier(self, tmp_path):
        """Spec test 2 — THE test: cluster-reader passes the WIDE check and FAILS the usage
        check, so it stays scope=all on /groups (the audit view it is meant to keep) and
        scope=self on Usage (colleagues' presence records it must not see) — same app, same
        request cycle. cluster-admin passes both and is scope=all on Usage. A decided wide tier
        must never widen Usage, and vice versa."""
        db = str(tmp_path / "gsd.db")
        _seed_usage(db)
        # wide admits both personas; usage admits only the full admin.
        app = _usage_app(db, wide={"reader": "all", "admin": "all"}, usage={"admin": "all"})
        with TestClient(app) as c:
            reader_groups = c.get("/api/clusters/c1/groups", headers=H("reader")).json()
            reader_usage = c.get("/api/dashboard/activity", headers=H("reader")).json()
            admin_usage = c.get("/api/dashboard/activity", headers=H("admin")).json()
        assert reader_groups["scope"] == "all", "the auditor keeps every wide audit view"
        assert reader_usage["scope"] == "self", "but NOT colleagues' presence records"
        assert {r["user_name"] for r in reader_usage["activity"]} <= {"reader"}
        assert admin_usage["scope"] == "all", "a full administrator is ungated on Usage"
        assert {r["user_name"] for r in admin_usage["activity"]} == {"alice", "bob", "carol"}

    def test_a_self_tier_reader_sees_only_their_own_usage(self, tmp_path):
        """Spec test 3: a reader the usage tier denies sees their own rows only — and the self
        verdict must come from CONSULTING the usage tier, not from ignoring it (the pre-tier
        default was also self, so the call-count is what proves the new path runs)."""
        db = str(tmp_path / "gsd.db")
        _seed_usage(db)
        usage_stub = _MapResolver({})            # denies everyone, counts calls
        app = _usage_app(db, wide={"alice": "all"}, usage=usage_stub)
        with TestClient(app) as c:
            body = c.get("/api/dashboard/activity", headers=H("alice")).json()
        assert body["scope"] == "self"
        assert {r["user_name"] for r in body["activity"]} == {"alice"}
        assert usage_stub.calls >= 1, (
            "the self verdict must be a DECISION by the usage tier, not the wide tier leaking "
            "in or the endpoint ignoring the tier entirely")

    def test_the_usage_tier_fails_closed(self, tmp_path):
        """Spec test 4: a raised exception, a junk tier string, and no resolver at all each
        serve the reader's own rows — never the wide set — exactly as viewer_scope does. The
        wide tier says `all` for this reader throughout, to prove it cannot leak into Usage."""
        db = str(tmp_path / "gsd.db")
        _seed_usage(db)

        class Exploding:
            def __init__(self):
                self.calls = 0

            def resolve(self, viewer):
                self.calls += 1
                raise RuntimeError("SAR path down")

        class Junk:
            def __init__(self):
                self.calls = 0

            def resolve(self, viewer):
                self.calls += 1
                return "administrator"           # not the exact string "all"

        for stub in (Exploding(), Junk()):
            app = _usage_app(db, wide={"alice": "all"}, usage=stub)
            with TestClient(app) as c:
                body = c.get("/api/dashboard/activity", headers=H("alice")).json()
            assert body["scope"] == "self", f"{type(stub).__name__} must fail closed to self"
            assert stub.calls >= 1, "fail-closed still means the tier was consulted"

        # No resolver at all — neither published nor injected — is the third indeterminate case.
        app = build_app(_settings(db), run_poller=False)
        app.state.tier_resolver = _MapResolver({"alice": "all"})
        app.state.usage_tier_resolver = None
        with TestClient(app) as c:
            body = c.get("/api/dashboard/activity", headers=H("alice")).json()
        assert body["scope"] == "self", "no usage resolver must serve self, not the wide set"

    def test_user_activity_visibility_all_wins_over_the_usage_tier(self, tmp_path):
        """Spec test 5: the blunt escape hatch is unchanged and takes precedence — everyone
        sees all rows, and the usage tier is never even consulted."""
        db = str(tmp_path / "gsd.db")
        _seed_usage(db)
        usage_stub = _MapResolver({})            # would deny everyone if asked
        app = build_app(_settings(db, user_activity_visibility="all"), run_poller=False)
        app.state.tier_resolver = _MapResolver({})
        app.state.usage_tier_resolver = usage_stub
        with TestClient(app) as c:
            body = c.get("/api/dashboard/activity", headers=H("alice")).json()
        assert body["scope"] == "all"
        assert {r["user_name"] for r in body["activity"]} == {"alice", "bob", "carol"}
        assert usage_stub.calls == 0, "the override wins before the usage tier is consulted"

    def test_no_identity_is_refused(self, tmp_path):
        """Spec test 6: no authenticated identity -> 403, precedence 3, unchanged."""
        db = str(tmp_path / "gsd.db")
        _seed_usage(db)
        with TestClient(_usage_app(db, wide={}, usage={})) as c:
            assert c.get("/api/dashboard/activity").status_code == 403

    def test_the_two_sar_caches_are_independent(self, db):
        """Spec test 8: build_app must construct TWO resolvers with TWO caches, asking two
        different questions, so a verdict decided by one is never served by the other. Reaches
        into the resolver internals deliberately: separate `_cache` objects is the property the
        independence rests on, and it cannot be observed from the wire."""
        app = build_app(_settings(db), run_poller=False)
        wide = app.state.tier_resolver
        usage = app.state.usage_tier_resolver
        assert wide is not None and usage is not None, "both tiers must be built"
        assert wide is not usage, "one resolver for both tiers would share a cache across two questions"
        assert wide._cache is not usage._cache, "the caches must be distinct objects"
        # The questions themselves differ — the reason a shared verdict would be wrong.
        assert wide._attributes["resource"] == "clusterrolebindings"
        assert usage._attributes["resource"] == "clusterrolebindings"
        assert usage._attributes["verb"] == "update"
        assert wide._attributes != usage._attributes


def _sample(text: str, needle: str) -> float:
    """The value of one exposition sample, matched on its exact name{labels} prefix."""
    for line in text.splitlines():
        if not line.startswith("#") and line.startswith(needle):
            return float(line.rsplit(" ", 1)[1])
    raise AssertionError(f"{needle} not found in the exposition")


class TestVisibilityMetricsSite:
    """§3.2/§3.3 of docs/DESIGN_metrics_refresh.md, measured off the app's own /metrics:
    the decision and refusal counters increment where the decisions actually happen."""

    def test_decisions_and_refusals_reach_the_exposition(self, client):
        before = client.get("/metrics").text
        refused = client.get("/api/clusters/c1/bindings/findings", headers=H("alice"))
        assert refused.status_code == 403
        wide = client.get("/api/clusters/c1/groups", headers=H("root")).json()
        assert wide["scope"] == "all"
        after = client.get("/metrics").text

        refusals = "gsd_visibility_admin_refusals_total"
        d_self = 'gsd_visibility_decisions_total{threshold="admin",tier="self"}'
        d_all = 'gsd_visibility_decisions_total{threshold="admin",tier="all"}'
        assert _sample(after, refusals) == _sample(before, refusals) + 1
        # >=, not ==: one request can be counted more than once by design (whoami and the
        # admin gate both consult viewer_scope), and the module-scoped client is shared.
        assert _sample(after, d_self) >= _sample(before, d_self) + 1
        assert _sample(after, d_all) >= _sample(before, d_all) + 1
