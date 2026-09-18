"""Home (#158): the viewer's own access on one cluster, for every tier.

One seed shaped like the mock (`docs/design/landing-access-mock.html`): a person with a cluster-wide
admin through one group, three groups granting a cluster-wide edit that admin already covers, a custom
cluster-wide role, four namespaces through one developer group (one of them a platform namespace reached
through two groups), one direct grant in the console's own namespace, eleven groups granting nothing here,
memberships on two other clusters, and a month of membership history with a batch and a flap in it.
"""
from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import IDENTITY_NONE, IDENTITY_SAME_AS_HOST, ClusterConfig, Settings
from gsd.home import HOME_CHANGES_DAYS, derive_answer, group_changes
from gsd.store import Store

ALICE = {"X-Forwarded-User": "alice"}
GIVES_ADMIN = "app-ocp-rbac-alpha-cluster-admin"
DEVS = "app-ocp-rbac-demo-ns-developer"
NS_ADMIN = "app-ocp-rbac-demo-ns-admin"
EDITORS = ["app-ocp-rbac-alpha-cluster-developer", "app-ocp-rbac-demo-cluster-developer",
           "app-ocp-rbac-platform-cluster-developer"]
AUDITOR = "app-ocp-rbac-groupsync-ns-auditor"
IDLE = [f"app-ocp-rbac-{x}-ns-viewer" for x in
        ("spar", "beta", "platform", "presto", "spark", "trino", "hive", "kafka", "flink", "nifi", "airflow")]
ALL_GROUPS = [GIVES_ADMIN, DEVS, NS_ADMIN, *EDITORS, AUDITOR, *IDLE]
MONITORING_NS = "openshift-user-workload-monitoring"


def _iso(t: datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


class _Map:
    def __init__(self, tiers):
        self.tiers = tiers

    def resolve(self, viewer):
        return self.tiers.get(viewer, "self")


def _seed(db: str) -> datetime:
    now = datetime.now(UTC).replace(microsecond=0)
    s = Store(db)
    for cid, url in (("crc", "https://api.crc.testing:6443"), ("east", "https://api.east.example.com:6443"),
                     ("west", "https://api.west.example.com:6443")):
        s.upsert_cluster(cid, url, True)
    s.record_poll("crc", "ok", None)
    s.record_poll("east", "ok", None)
    s.record_poll("west", "auth_failed", "401 Unauthorized — token invalid or expired")
    s.replace_group_state("crc", [{"name": g, "member_count": 1, "sync_provider": "ldap-groupsync_ldap",
                                   "group_synced_at": _iso(now - timedelta(minutes=4)), "ldap_uid": None}
                                  for g in ALL_GROUPS], _iso(now))
    # A month ago: the baseline (first observed, never a change).
    baseline = {g: ["alice"] for g in (GIVES_ADMIN, DEVS, NS_ADMIN, *EDITORS)}
    baseline.update({g: [] for g in (AUDITOR, *IDLE)})
    s.sync_members("crc", baseline, {g: _iso(now - timedelta(days=40)) for g in ALL_GROUPS}, _iso(now - timedelta(days=40)))
    # Three days ago, one sync: the eleven idle groups and the auditor group all at once.
    t0 = now - timedelta(days=3, hours=2)
    at_once = dict(baseline, **{g: ["alice"] for g in (AUDITOR, *IDLE)})
    s.sync_members("crc", at_once, {g: _iso(t0) for g in ALL_GROUPS}, _iso(t0))
    # ...then the auditor group flaps: removed, added, removed, added — five changes in 33 minutes.
    for minutes, present in ((5, False), (15, True), (25, False), (33, True)):
        state = dict(at_once, **{AUDITOR: ["alice"] if present else []})
        s.sync_members("crc", state, {g: _iso(t0 + timedelta(minutes=minutes)) for g in ALL_GROUPS},
                       _iso(t0 + timedelta(minutes=minutes)))
    s.replace_bindings("crc", [
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "alpha-cluster-admin",
         "role_kind": "ClusterRole", "role_name": "admin", "group_name": GIVES_ADMIN, "managed_source": "baseline-cluster-rbac"},
        *[{"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": f"{g}-edit",
           "role_kind": "ClusterRole", "role_name": "edit", "group_name": g, "managed_source": "baseline-cluster-rbac"} for g in EDITORS],
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "report-auditor",
         "role_kind": "ClusterRole", "role_name": "group-sync-dashboard-report-auditor", "group_name": AUDITOR},
        *[{"binding_kind": "RoleBinding", "binding_namespace": ns, "binding_name": f"{ns}-devs",
           "role_kind": "ClusterRole", "role_name": "edit", "group_name": DEVS, "managed_source": "baseline-nonprod-rbac"}
          for ns in ("demo-qa", "demo-rnd", "demo-uat")],
        {"binding_kind": "RoleBinding", "binding_namespace": MONITORING_NS, "binding_name": "uwm-devs",
         "role_kind": "ClusterRole", "role_name": "monitoring-rules-edit", "group_name": DEVS},
        {"binding_kind": "RoleBinding", "binding_namespace": MONITORING_NS, "binding_name": "uwm-admins",
         "role_kind": "ClusterRole", "role_name": "monitoring-rules-edit", "group_name": NS_ADMIN},
    ], _iso(now))
    s.replace_user_bindings("crc", [
        {"binding_kind": "RoleBinding", "binding_namespace": "openshift-console-user-settings",
         "binding_name": "user-settings-alice", "role_kind": "Role", "role_name": "user-settings-alice-role",
         "user_name": "alice", "is_platform": 0},
        {"binding_kind": "RoleBinding", "binding_namespace": "demo-qa", "binding_name": "bob-view",
         "role_kind": "ClusterRole", "role_name": "view", "user_name": "bob", "is_platform": 0},
    ], _iso(now))
    s.replace_users("crc", [{"user_name": "alice", "full_name": "Alice Example", "created_at": _iso(now - timedelta(days=200)),
                             "providers": ["ldap-local"], "has_identity": True}], _iso(now))
    # Elsewhere: two groups on east (one added two days ago), one on west; bob's memberships are not alice's.
    s.replace_group_state("east", [{"name": g, "member_count": 1, "sync_provider": "ldap-groupsync_ldap",
                                    "group_synced_at": _iso(now), "ldap_uid": None}
                                   for g in ("east-dev", "platform-team-cluster-admin")], _iso(now))
    s.sync_members("east", {"east-dev": ["alice"], "platform-team-cluster-admin": ["bob"]},
                   {"east-dev": _iso(now - timedelta(days=40)), "platform-team-cluster-admin": _iso(now - timedelta(days=40))},
                   _iso(now - timedelta(days=40)))
    s.sync_members("east", {"east-dev": ["alice"], "platform-team-cluster-admin": ["alice", "bob"]},
                   {"east-dev": _iso(now - timedelta(days=2)), "platform-team-cluster-admin": _iso(now - timedelta(days=2))},
                   _iso(now - timedelta(days=2)))
    s.replace_group_state("west", [{"name": "west-viewer", "member_count": 1, "sync_provider": "ldap-groupsync_ldap",
                                    "group_synced_at": _iso(now), "ldap_uid": None}], _iso(now))
    s.sync_members("west", {"west-viewer": ["alice"]}, {"west-viewer": _iso(now - timedelta(days=40))}, _iso(now - timedelta(days=40)))
    s.close()
    return now


def _app(db: str, tiers: dict, *, west_identity: str = IDENTITY_SAME_AS_HOST):
    """The host and two remotes that treat the host's username as their own (`identity: same-as-host`);
    a remote left at the default (`none`) vouches for nobody and must not appear in `elsewhere`."""
    app = build_app(Settings(clusters=[ClusterConfig("crc", "https://api.crc.testing:6443", token_env="X"),
                                       ClusterConfig("east", "https://api.east.example.com:6443", token_env="Y",
                                                     identity=IDENTITY_SAME_AS_HOST),
                                       ClusterConfig("west", "https://api.west.example.com:6443", token_env="Z",
                                                     identity=west_identity)],
                             db_path=db, oauth_proxy_enabled=True), run_poller=False)
    app.state.tier_resolver = _Map(tiers)
    return app


@pytest.fixture(scope="module")
def home(tmp_path_factory):
    db = str(tmp_path_factory.mktemp("home") / "home.db")
    _seed(db)
    with TestClient(_app(db, {})) as client:
        yield client.get("/api/clusters/crc/home", headers=ALICE).json()


def test_the_answer_is_the_strongest_cluster_wide_role_and_what_it_covers(home):
    a = home["answer"]
    assert a["top_role"] == "admin"
    wide = {r["role_name"]: r for r in a["cluster_wide"]}
    assert list(wide) == ["admin", "edit", "group-sync-dashboard-report-auditor"], "ranked roles first, custom last"
    assert wide["admin"]["via_groups"] == [GIVES_ADMIN] and wide["admin"]["covered_by"] is None
    assert wide["edit"]["via_groups"] == EDITORS and wide["edit"]["covered_by"] == "admin" and wide["edit"]["bindings"] == 3
    assert wide["group-sync-dashboard-report-auditor"]["covered_by"] is None, "a custom role is never covered"
    assert a["cluster_wide_bindings"] == 5


def test_namespaces_carry_every_path_and_say_which_grants_admin_already_covers(home):
    ns = {n["name"]: n for n in home["answer"]["namespaces"]}
    assert list(ns) == ["demo-qa", "demo-rnd", "demo-uat", "openshift-console-user-settings", MONITORING_NS]
    assert ns["demo-qa"]["grants"] == [{"role_name": "edit", "role_kind": "ClusterRole", "via_group": DEVS,
                                        "binding_name": "demo-qa-devs", "covered": True}]
    assert ns["demo-qa"]["covered"] and not ns["demo-qa"]["platform"]
    two = ns[MONITORING_NS]
    assert two["platform"] and [g["via_group"] for g in two["grants"]] == [NS_ADMIN, DEVS], "two paths to the same grant"
    assert not two["covered"], "a custom role is not covered by admin"
    console = ns["openshift-console-user-settings"]
    assert console["platform"] and console["grants"][0]["via_group"] is None, "a direct grant carries no group"
    assert home["answer"]["namespaces_covered"] == 3


def test_groups_lead_with_the_one_that_gives_the_top_role_and_count_what_each_grants(home):
    a = home["answer"]
    assert (a["groups_total"], a["groups_granting"], a["direct_count"]) == (18, 7, 1)
    groups = a["groups"]
    assert groups[0]["group_name"] == GIVES_ADMIN and groups[0]["gives_top"] and groups[0]["cluster_wide_roles"] == ["admin"]
    assert groups[1]["group_name"] == DEVS and groups[1]["grants"] == 4 and groups[1]["namespaces"] == ["demo-qa", "demo-rnd", "demo-uat", MONITORING_NS]
    assert [g["group_name"] for g in groups if not g["grants"]] == sorted(IDLE)
    assert all(g["sync_provider"] == "ldap-groupsync_ldap" for g in groups)


def test_direct_grants_are_the_viewers_own_and_nobody_elses(home):
    assert [d["binding_name"] for d in home["direct"]] == ["user-settings-alice"]
    assert "bob" not in str(home), "another person's row never reaches this page"


def test_what_changed_folds_the_batch_and_the_flap_and_names_the_other_cluster(home):
    c = home["changes"]
    kinds = [(i["kind"], i["cluster"]) for i in c["items"]]
    assert kinds == [("single", "east"), ("flap", "crc"), ("batch", "crc")], kinds
    single, flap, batch = c["items"]
    assert single["group_name"] == "platform-team-cluster-admin" and single["change"] == "added"
    assert flap["group_name"] == AUDITOR and flap["changes"] == 5 and flap["span_minutes"] == 33 and flap["latest"] == "added"
    assert batch["change"] == "added" and batch["count"] == 11 and batch["groups"] == sorted(IDLE)
    assert c["more"] == 0 and c["changes"] == 17 and c["window_days"] == HOME_CHANGES_DAYS
    assert "since" not in c, "a clock-derived field on the wire defeats the page's unchanged-payload skip"
    assert home["retention"]["window_days"] >= 0 and "retained_since" in home["retention"]


def test_elsewhere_names_the_other_clusters_with_their_poll_state(home):
    assert home["elsewhere"] == [
        {"cluster": "east", "memberships": 2, "status": "ok", "last_poll": home["elsewhere"][0]["last_poll"]},
        {"cluster": "west", "memberships": 1, "status": "auth_failed", "last_poll": home["elsewhere"][1]["last_poll"]},
    ]
    assert home["memberships_total"] == 21
    assert (home["viewer"], home["full_name"], home["providers"], home["scope"]) == ("alice", "Alice Example", ["ldap-local"], "self")


def test_an_administrator_sees_their_own_access_here_not_everyones(tmp_path):
    """The page is self-scoped by definition: the payload for a name is the same whichever tier
    resolves it — only `scope` says which tier that was (the DoD's "no admin aggregate may leak")."""
    db = str(tmp_path / "tiers.db")
    _seed(db)
    with TestClient(_app(db, {})) as client:
        self_view = client.get("/api/clusters/crc/home", headers=ALICE).json()
    with TestClient(_app(db, {"alice": "all"})) as client:
        wide_view = client.get("/api/clusters/crc/home", headers=ALICE).json()
    assert (self_view["scope"], wide_view["scope"]) == ("self", "all")
    for body in (self_view, wide_view):
        body.pop("scope")
    assert self_view == wide_view, "only `scope` may differ between the tiers"


def test_no_identity_is_refused_never_a_typed_name(tmp_path):
    db = str(tmp_path / "noid.db")
    _seed(db)
    with TestClient(_app(db, {})) as client:
        r = client.get("/api/clusters/crc/home")
        assert r.status_code == 403 and "no authenticated identity" in r.json()["detail"]
        assert client.get("/api/clusters/nope/home", headers=ALICE).status_code == 404
    # Proxy off: the header is whatever the caller typed, so there is nobody to scope to.
    app = build_app(Settings(clusters=[ClusterConfig("crc", "https://api.crc.testing:6443", token_env="X")],
                             db_path=db, view_restrictions_enabled=False), run_poller=False)
    with TestClient(app) as client:
        assert client.get("/api/clusters/crc/home", headers=ALICE).status_code == 403


def test_a_person_with_nothing_gets_an_empty_answer_not_an_error(tmp_path):
    db = str(tmp_path / "nobody.db")
    _seed(db)
    with TestClient(_app(db, {})) as client:
        body = client.get("/api/clusters/crc/home", headers={"X-Forwarded-User": "nobody"}).json()
    a = body["answer"]
    assert a["top_role"] is None and a["cluster_wide"] == [] and a["namespaces"] == [] and a["groups"] == []
    assert (a["groups_total"], a["groups_granting"], a["direct_count"]) == (0, 0, 0)
    assert body["changes"]["items"] == [] and body["elsewhere"] == [] and body["memberships_total"] == 0


class TestDerivation:
    """The rules, without a store."""

    def test_cluster_wide_view_is_covered_by_a_namespaced_nothing_but_by_cluster_wide_edit(self):
        via = [{"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "v", "role_kind": "ClusterRole", "role_name": "view", "via_group": "g1"},
               {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "e", "role_kind": "ClusterRole", "role_name": "edit", "via_group": "g2"},
               {"binding_kind": "RoleBinding", "binding_namespace": "ns", "binding_name": "a", "role_kind": "ClusterRole", "role_name": "admin", "via_group": "g3"}]
        a = derive_answer([{"group_name": g, "sync_provider": None, "first_seen_at": None, "last_seen_at": None} for g in ("g1", "g2", "g3")], via, [])
        wide = {r["role_name"]: r["covered_by"] for r in a["cluster_wide"]}
        assert a["top_role"] == "edit" and wide == {"edit": None, "view": "edit"}
        assert a["namespaces"][0]["grants"][0]["covered"] is False, "cluster-wide edit does not cover a namespaced admin"

    def test_a_namespaced_role_named_admin_is_not_the_builtin_clusterrole(self):
        """Kubernetes has one ClusterRole `admin`; a namespaced Role of that name is a different object.
        Ranking it by name let the page say "covered by admin — removing this would not change what you
        can do" about access nothing else grants (Grok, review of #158)."""
        via = [{"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "ca",
                "role_kind": "ClusterRole", "role_name": "admin", "via_group": "g1"},
               {"binding_kind": "RoleBinding", "binding_namespace": "ns", "binding_name": "r",
                "role_kind": "Role", "role_name": "admin", "via_group": "g2"}]
        a = derive_answer([{"group_name": g, "sync_provider": None, "first_seen_at": None, "last_seen_at": None}
                           for g in ("g1", "g2")], via, [])
        assert a["top_role"] == "admin"
        grant = a["namespaces"][0]["grants"][0]
        assert (grant["role_kind"], grant["role_name"]) == ("Role", "admin")
        assert grant["covered"] is False, "a Role named admin is not ClusterRole admin"
        assert a["namespaces"][0]["covered"] is False
        assert a["namespaces_covered"] == 0

    def test_a_cluster_wide_role_and_a_namespaced_role_of_one_name_stay_two_rows(self):
        """Keyed by name alone, a Role and a ClusterRole called `admin` merged into one row and one
        row's groups appeared under the other's name."""
        via = [{"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "ca",
                "role_kind": "ClusterRole", "role_name": "admin", "via_group": "g1"},
               {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "rb",
                "role_kind": "Role", "role_name": "admin", "via_group": "g2"}]
        a = derive_answer([], via, [])
        rows = [(r["role_kind"], r["role_name"], r["via_groups"]) for r in a["cluster_wide"]]
        assert rows == [("ClusterRole", "admin", ["g1"]), ("Role", "admin", ["g2"])], rows

    def test_a_covered_role_held_only_directly_names_no_groups(self):
        """A direct cluster-wide `edit` under a cluster-wide `admin` has no groups behind it, and the
        card's foot read "0 groups grant edit cluster-wide … removing them would not change what you can
        do" (Grok, review of #158). The payload is what the page composes from."""
        direct = [{"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "me-admin",
                   "role_kind": "ClusterRole", "role_name": "admin", "user_name": "me", "is_platform": 0},
                  {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "me-edit",
                   "role_kind": "ClusterRole", "role_name": "edit", "user_name": "me", "is_platform": 0}]
        a = derive_answer([], [], direct)
        edit = next(r for r in a["cluster_wide"] if r["role_name"] == "edit")
        assert edit["covered_by"] == "admin" and edit["via_groups"] == [] and edit["direct"] is True

    def test_more_counts_the_changes_the_leftover_cards_stand_for(self):
        """The page says "N more changes in the window", so N counts CHANGES: one leftover batch of
        three groups is three, not one card (Grok, review of #158)."""
        now = datetime.now(UTC)
        since = (now - timedelta(days=HOME_CHANGES_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        at = [_iso(now - timedelta(minutes=i)) for i in range(13)]
        singles = [{"cluster": "c", "group_name": f"g{i}", "change": "added", "observed_at": at[i], "baseline": 0}
                   for i in range(12)]
        batch = [{"cluster": "c", "group_name": g, "change": "added", "observed_at": at[12], "baseline": 0}
                 for g in ("x", "y", "z")]
        c = group_changes(singles + batch, since)
        assert c["changes"] == 15 and len(c["items"]) == 12 and c["more_items"] == 1
        assert c["more"] == 3, "the leftover card is one batch of three groups, not '1 change'"

    def test_a_direct_cluster_wide_grant_counts_as_the_top_role(self):
        direct = [{"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "me-ca", "role_kind": "ClusterRole",
                   "role_name": "cluster-admin", "user_name": "me", "is_platform": 0}]
        a = derive_answer([], [], direct)
        assert a["top_role"] == "cluster-admin" and a["cluster_wide"][0]["direct"] and a["cluster_wide"][0]["via_groups"] == []

    def test_changes_outside_the_window_and_baseline_rows_are_not_changes(self):
        now = datetime.now(UTC)
        since = (now - timedelta(days=HOME_CHANGES_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        events = [{"cluster": "c", "group_name": "old", "change": "added", "observed_at": _iso(now - timedelta(days=45)), "baseline": 0},
                  {"cluster": "c", "group_name": "first", "change": "added", "observed_at": _iso(now - timedelta(days=1)), "baseline": 1},
                  {"cluster": "c", "group_name": "new", "change": "removed", "observed_at": _iso(now - timedelta(days=1)), "baseline": 0}]
        c = group_changes(events, since)
        assert [i["group_name"] for i in c["items"]] == ["new"] and c["changes"] == 1

    def test_two_groups_in_one_sync_are_two_lines_three_are_one(self):
        now = datetime.now(UTC)
        since = (now - timedelta(days=HOME_CHANGES_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")
        at = _iso(now - timedelta(hours=1))
        two = [{"cluster": "c", "group_name": g, "change": "added", "observed_at": at, "baseline": 0} for g in ("a", "b")]
        assert [i["kind"] for i in group_changes(two, since)["items"]] == ["single", "single"]
        three = two + [{"cluster": "c", "group_name": "d", "change": "added", "observed_at": at, "baseline": 0}]
        assert [i["kind"] for i in group_changes(three, since)["items"]] == ["batch"]


def test_a_cluster_that_vouches_for_nobody_is_not_elsewhere(tmp_path):
    """A remote at the default identity policy (`none`) does not treat the host's username as its own, so
    nothing there is this person's: it is left out of `elsewhere`, its memberships out of the total."""
    db = str(tmp_path / "identity.db")
    _seed(db)
    with TestClient(_app(db, {}, west_identity=IDENTITY_NONE)) as client:
        body = client.get("/api/clusters/crc/home", headers=ALICE).json()
    assert [e["cluster"] for e in body["elsewhere"]] == ["east"] and body["memberships_total"] == 20


def test_a_hidden_cluster_is_not_elsewhere(tmp_path):
    """`hidden` is a serving rule: the cluster is polled, never named. Home's cross-cluster line was
    written against the STORE's clusters, so it named a cluster whose own endpoint 404s, counted its
    memberships and folded its history into "what changed" (Grok, review of #158). The rule is one
    predicate now — `is_served` — and `require_cluster` is its other caller."""
    db = str(tmp_path / "hidden.db")
    _seed(db)
    app = build_app(Settings(
        clusters=[ClusterConfig("crc", "https://api.crc.testing:6443", token_env="X"),
                  ClusterConfig("east", "https://api.east.example.com:6443", token_env="Y",
                                identity=IDENTITY_SAME_AS_HOST),
                  ClusterConfig("west", "https://api.west.example.com:6443", token_env="Z",
                                identity=IDENTITY_SAME_AS_HOST, visibility="hidden")],
        db_path=db, oauth_proxy_enabled=True), run_poller=False)
    app.state.tier_resolver = _Map({})
    with TestClient(app) as client:
        body = client.get("/api/clusters/crc/home", headers=ALICE).json()
        assert client.get("/api/clusters/west/home", headers=ALICE).status_code == 404, "hidden 404s"
    assert [e["cluster"] for e in body["elsewhere"]] == ["east"], body["elsewhere"]
    assert body["memberships_total"] == 20, "the hidden cluster's membership is not counted"
    assert all(i["cluster"] != "west" for i in body["changes"]["items"]), "nor its history folded in"


def test_the_cross_cluster_loop_consults_no_tier_resolver(tmp_path):
    """The loop runs inside `@consistent`, holding a read snapshot. `viewer_scope` decides a tier per
    cluster, and a `remote-sar` cluster's resolver is an HTTP SubjectAccessReview against that cluster's
    own API — one per remote in the fleet, inside the snapshot (Grok, review of #158). Home needs only the
    NAME question, which is config alone: `west` is remote-sar here, and its resolver must not be called.
    """
    db = str(tmp_path / "noresolve.db")
    _seed(db)
    calls = []

    class _Counting:
        def resolve(self, viewer):
            calls.append(viewer)
            return "self"

    app = build_app(Settings(
        clusters=[ClusterConfig("crc", "https://api.crc.testing:6443", token_env="X"),
                  ClusterConfig("east", "https://api.east.example.com:6443", token_env="Y",
                                identity=IDENTITY_SAME_AS_HOST),
                  ClusterConfig("west", "https://api.west.example.com:6443", token_env="Z",
                                identity=IDENTITY_SAME_AS_HOST, visibility="remote-sar")],
        db_path=db, oauth_proxy_enabled=True), run_poller=False)
    app.state.tier_resolver = _Map({})
    app.state.remote_tier_resolvers = {"west": _Counting()}
    with TestClient(app) as client:
        body = client.get("/api/clusters/crc/home", headers=ALICE).json()
    assert [e["cluster"] for e in body["elsewhere"]] == ["east", "west"], "remote-sar still vouches for the name"
    assert calls == [], f"the remote cluster's SubjectAccessReview ran inside the snapshot: {calls}"


def test_the_history_cap_is_named_on_the_wire(tmp_path, monkeypatch):
    """A cluster whose history hits the per-cluster cap makes every count a lower bound, so the payload
    says which clusters those were rather than letting the page present them as complete (Codex, review
    of #158). Both directions, so the field means something: capped at 2, not capped at the real limit."""
    import gsd.api as api
    db = str(tmp_path / "capped.db")
    _seed(db)
    with TestClient(_app(db, {})) as client:
        uncapped = client.get("/api/clusters/crc/home", headers=ALICE).json()["changes"]
    assert uncapped["capped_clusters"] == [], uncapped["capped_clusters"]
    assert uncapped["changes"] > 2, "the seed must exceed the cap this test lowers to, or it proves nothing"
    monkeypatch.setattr(api, "HOME_EVENTS_LIMIT", 2)
    with TestClient(_app(db, {})) as client:
        capped = client.get("/api/clusters/crc/home", headers=ALICE).json()["changes"]
    assert "crc" in capped["capped_clusters"], capped["capped_clusters"]


def test_two_reads_of_an_unchanged_store_are_byte_identical(tmp_path):
    """The page skips the repaint when the whole payload is unchanged, so ANY clock-derived field on the wire
    defeats it. `/home` echoed the window's start, computed from `datetime.now()` per request — so Home,
    alone among the pages, repainted every 60 s and threw away scroll, selection and focus (OB3, integration
    review, C3). Two reads of a store nobody has touched must be the same bytes."""
    db = str(tmp_path / "stable.db")
    _seed(db)
    with TestClient(_app(db, {})) as client:
        first = client.get("/api/clusters/crc/home", headers=ALICE).content
        time.sleep(1.1)                      # longer than the field's one-second resolution
        second = client.get("/api/clusters/crc/home", headers=ALICE).content
    assert first == second, "the payload moved while the store did not"
