"""The default is `remote-sar` + `same-as-host` (docs/specs/SPEC_D2b_remote_sar_for_every_join.md §3.2, §3.3, §6),
and what that changes for a remote that states nothing — measured at the routes, through the app.state seams.

The rows of §3.2's table — its last row once for each of its three visibilities — are held twice: what
`remote_policy` RETURNS, and what each reader ACCEPTS — the loader, the Secret parser and the chart refuse only the
explicit pair `remote-sar` + `identity: none`.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest
import yaml
from fastapi.testclient import TestClient

import gsd.api as api_mod
from gsd.api import build_app
from gsd.clusterconfig import Finding, parse_secret, writer
from gsd.config import ClusterConfig, ConfigError, Settings, load_settings, remote_policy
from gsd.store import Store
from gsd.timeutil import now_iso

from test_clusterconfig import _secret

CHART = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"

#: (visibility stated, identity stated) -> what remote_policy returns, and whether the readers accept it
TABLE = [
    ((None, None), ("remote-sar", "same-as-host"), True),
    ((None, "none"), ("self-only", "none"), True),
    ((None, "same-as-host"), ("remote-sar", "same-as-host"), True),
    (("remote-sar", None), ("remote-sar", "same-as-host"), True),
    (("remote-sar", "none"), ("remote-sar", "none"), False),
    (("inherit", None), ("inherit", "none"), True),
    (("self-only", None), ("self-only", "none"), True),
    (("hidden", None), ("hidden", "none"), True),
]
IDS = [f"{v or '-'}+{i or '-'}" for (v, i), _, _ in TABLE]


def _stated(visibility, identity) -> dict:
    return {k: v for k, v in (("visibility", visibility), ("identity", identity)) if v is not None}


class TestThePairRule:
    @pytest.mark.parametrize("stated,resolved,accepted", TABLE, ids=IDS)
    def test_remote_policy_resolves_the_row(self, stated, resolved, accepted):
        assert remote_policy(*stated) == resolved

    @pytest.mark.parametrize("stated,resolved,accepted", TABLE, ids=IDS)
    def test_the_loader_accepts_or_refuses_the_row(self, tmp_path, stated, resolved, accepted):
        entry = {"name": "far", "apiUrl": "https://api.far.example:6443", "tokenEnv": "X", **_stated(*stated)}
        p = tmp_path / "clusters.yaml"
        p.write_text(yaml.safe_dump({"clusters": [
            {"name": "home", "apiUrl": "https://kubernetes.default.svc", "tokenEnv": "X", "dashboardController": True},
            entry]}))
        if accepted:
            assert load_settings(str(p)).cluster_policy("far") == resolved
        else:
            with pytest.raises(ConfigError, match="visibility remote-sar needs identity: same-as-host"):
                load_settings(str(p))

    @pytest.mark.parametrize("stated,resolved,accepted", TABLE, ids=IDS)
    def test_the_secret_parser_accepts_or_refuses_the_row(self, stated, resolved, accepted):
        parsed = parse_secret(_secret(**_stated(*stated)), host_name="home")
        if accepted:
            assert isinstance(parsed, ClusterConfig) and remote_policy(parsed.visibility, parsed.identity) == resolved
        else:
            assert isinstance(parsed, Finding) and parsed.code == "identity-invalid"
            assert "cannot pair with visibility remote-sar" in parsed.detail

    @pytest.mark.parametrize("stated,resolved,accepted", TABLE, ids=IDS)
    @pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
    def test_the_chart_accepts_or_refuses_the_row(self, tmp_path, stated, resolved, accepted):
        entry = {"name": "far", "apiUrl": "https://api.far.example:6443", "tokenEnv": "X", **_stated(*stated)}
        values = tmp_path / "v.yaml"
        values.write_text(yaml.safe_dump({"clusters": [
            {"name": "home", "apiUrl": "https://kubernetes.default.svc", "tokenEnv": "X", "dashboardController": True},
            entry]}))
        done = subprocess.run(["helm", "template", "t", str(CHART), "-f", str(values)],
                              capture_output=True, text=True, timeout=180)
        assert (done.returncode == 0) is accepted, done.stdout[-400:] + done.stderr[-400:]
        if not accepted:
            assert "visibility remote-sar needs identity: same-as-host" in done.stderr

    @pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
    def test_the_chart_accepts_remote_sar_beside_the_lookup(self, tmp_path):
        values = tmp_path / "v.yaml"
        values.write_text(yaml.safe_dump({
            "clusters": [{"name": "home", "apiUrl": "https://kubernetes.default.svc", "tokenEnv": "X",
                          "dashboardController": True},
                         {"name": "rnd", "apiUrl": "https://api.rnd.example:6443", "saTokenLookup": True,
                          "visibility": "remote-sar"}],
            "clusterConfig": {"secrets": {"writes": {"enabled": True}}}}))
        done = subprocess.run(["helm", "template", "t", str(CHART), "-f", str(values)],
                              capture_output=True, text=True, timeout=180)
        assert done.returncode == 0, done.stderr[-600:]


# ── what the flip changes for a remote that states nothing (§6) ──────────────────────────────────────────────
ALICE = {"X-Forwarded-User": "alice"}


def _seed(db: str) -> None:
    store = Store(db)
    now = now_iso()
    for cid in ("host", "far"):
        store.upsert_cluster(cid, f"https://api.{cid}.example:6443", True)
        store.record_poll(cid, "ok", None)
        store.replace_group_state(cid, [
            {"name": f"{cid}-admins", "member_count": 1, "sync_provider": "ldap_ldap", "group_synced_at": now, "ldap_uid": None},
        ], now)
        store.sync_members(cid, {f"{cid}-admins": ["alice"]}, {}, now)
        store.record_managed_groups(cid, [{"name": f"{cid}-gone", "sync_provider": "ldap_ldap"}], now)
        store.replace_bindings(cid, [
            {"binding_kind": "RoleBinding", "binding_namespace": "ns1", "binding_name": f"{cid}-gone-rb",
             "role_kind": "ClusterRole", "role_name": "admin", "group_name": f"{cid}-gone"},
        ], now)
        store.replace_operator_configs(cid, [
            {"kind": "GroupConfig", "name": f"{cid}-gc", "error_at": None, "error_message": None, "success_at": now},
        ], now)
    store.close()


class _Map:
    def __init__(self, tiers: dict[str, str]):
        self.tiers, self.calls = tiers, 0

    def resolve(self, viewer: str) -> str:
        self.calls += 1
        return self.tiers.get(viewer, "self")


def _unstated_app(tmp_path, remote: _Map | None):
    db = str(tmp_path / "gsd.db")
    _seed(db)
    app = build_app(Settings(clusters=[ClusterConfig("host", "https://api.host.example:6443", token_env="X"),
                                       ClusterConfig("far", "https://api.far.example:6443", token_env="X")],
                             db_path=db, oauth_proxy_enabled=True, view_restrictions_enabled=True), run_poller=False)
    app.state.tier_resolver = _Map({})
    app.state.remote_tier_resolvers = {"far": remote} if remote is not None else {}
    return app


PERSON_SCOPED = ("groups", "groups/far-admins", "users", "users/alice", "logins", "cluster-access", "namespaces",
                 "user-bindings", "membership-changes", "binding-changes", "home")
ADMINISTRATOR = ("bindings/findings", "operator-configs", "kyverno")


class TestAnUnstatedRemote:
    def test_a_reader_it_allows_sees_it_wide_on_every_tab_the_card_and_its_alerts(self, tmp_path):
        with TestClient(_unstated_app(tmp_path, _Map({"alice": "all"}))) as c:
            who = c.get("/api/whoami", headers=ALICE).json()["visibility"]["clusters"]["far"]
            assert who == {"policy": "remote-sar", "identity": "same-as-host", "scope": "all"}
            card = next(x for x in c.get("/api/clusters", headers=ALICE).json() if x["id"] == "far")
            assert card["visibility"] == {"policy": "remote-sar", "scope": "all"}
            assert card["operator_configs"] == {"total": 1, "failing": 0}
            for path in PERSON_SCOPED:
                r = c.get(f"/api/clusters/far/{path}", headers=ALICE)
                assert r.status_code == 200 and r.json()["scope"] == "all", path
            for path in ADMINISTRATOR:
                assert c.get(f"/api/clusters/far/{path}", headers=ALICE).status_code == 200, path
            kinds = {a["kind"] for a in c.get("/api/alerts", headers=ALICE).json()["alerts"] if a["cluster"] == "far"}
            assert "dangling_binding" in kinds

    @pytest.mark.parametrize("remote", ["denies", "cannot be asked"])
    def test_a_reader_it_denies_or_cannot_ask_about_gets_their_own_rows_not_a_403(self, tmp_path, remote):
        with TestClient(_unstated_app(tmp_path, _Map({}) if remote == "denies" else None)) as c:
            for path in PERSON_SCOPED:
                r = c.get(f"/api/clusters/far/{path}", headers=ALICE)
                assert r.status_code == 200 and r.json()["scope"] == "self" and r.json()["viewer"] == "alice", path
            for path in ADMINISTRATOR:
                assert c.get(f"/api/clusters/far/{path}", headers=ALICE).status_code == 403, path
            card = next(x for x in c.get("/api/clusters", headers=ALICE).json() if x["id"] == "far")
            assert card["operator_configs"] is None

    def test_home_counts_it_without_asking_its_resolver(self, tmp_path):
        remote = _Map({"alice": "all"})
        with TestClient(_unstated_app(tmp_path, remote)) as c:
            home = c.get("/api/clusters/host/home", headers=ALICE).json()
        assert [e["cluster"] for e in home["elsewhere"]] == ["far"] and home["memberships_total"] == 2
        assert remote.calls == 0, "vouches_for_host_identity is configuration only"

    def test_whoami_asks_it_once_and_reports_it(self, tmp_path):
        remote = _Map({})
        with TestClient(_unstated_app(tmp_path, remote)) as c:
            who = c.get("/api/whoami", headers=ALICE).json()["visibility"]["clusters"]
        assert who["far"] == {"policy": "remote-sar", "identity": "same-as-host", "scope": "self"}
        assert remote.calls == 1

    def test_identity_none_alone_keeps_the_old_self_only_and_its_403(self, tmp_path):
        db = str(tmp_path / "gsd.db")
        _seed(db)
        app = build_app(Settings(clusters=[ClusterConfig("host", "https://api.host.example:6443", token_env="X"),
                                           ClusterConfig("far", "https://api.far.example:6443", token_env="X",
                                                         identity="none")],
                                 db_path=db, oauth_proxy_enabled=True), run_poller=False)
        app.state.tier_resolver = _Map({})
        with TestClient(app) as c:
            assert c.get("/api/clusters/far/groups", headers=ALICE).status_code == 403
            assert c.get("/api/whoami", headers=ALICE).json()["visibility"]["clusters"]["far"] == \
                {"policy": "self-only", "identity": "none", "scope": "self"}


class TestNoTierIsDecidedInsideASnapshot:
    """§3.10: under remote-sar a decision is a group list and a review on the remote, and a read snapshot held
    across it pins the WAL read-mark (store.read_snapshot) — measured busy (1, 10, 10) for 15 s."""

    def test_clusters_and_alerts_decide_every_tier_before_their_read_snapshot(self, tmp_path):
        app = _unstated_app(tmp_path, None)
        store = app.state.store
        depths: list[int] = []

        class Probe:
            def resolve(self, viewer: str) -> str:
                depths.append(getattr(store._local, "read_depth", 0))
                return "self"
        app.state.tier_resolver = Probe()
        app.state.remote_tier_resolvers = {"far": Probe()}
        with TestClient(app) as c:
            for path in ("/api/clusters", "/api/alerts"):
                assert c.get(path, headers=ALICE).status_code == 200, path
        assert len(depths) == 4 and max(depths) == 0, f"a tier was decided inside a read snapshot: {depths}"

    @pytest.mark.parametrize("path", (*PERSON_SCOPED, *ADMINISTRATOR, "namespaces/ns1"))
    def test_a_named_remotes_tier_is_decided_once_and_before_the_routes_read_snapshot(self, tmp_path, path):
        """The per-cluster routes are @consistent too, and each decides the named cluster's tier: under the
        default that is the remote's own review, which must not run with the snapshot's read-mark held."""
        app = _unstated_app(tmp_path, None)
        store = app.state.store
        depths: list[int] = []

        class Probe:
            def resolve(self, viewer: str) -> str:
                depths.append(getattr(store._local, "read_depth", 0))
                return "all"
        app.state.remote_tier_resolvers = {"far": Probe()}
        with TestClient(app) as c:
            r = c.get(f"/api/clusters/far/{path}", headers=ALICE)
        assert r.status_code == 200, (path, r.text)                 # the decision made first is the one served
        assert depths == [0], f"{path}: the remote was asked {len(depths)} time(s), at snapshot depth {depths}"

    def test_a_route_that_decides_no_tier_asks_the_remote_nothing(self, tmp_path):
        remote = _Map({"alice": "all"})
        with TestClient(_unstated_app(tmp_path, remote)) as c:
            c.get("/api/clusters/far/groupsyncs/any/events", headers=ALICE)
        assert remote.calls == 0

    def test_alerts_ask_no_remote_that_their_walk_skips(self, tmp_path):
        """A row at enabled=0 while the configuration serves the cluster (a re-joined cluster before the leader's
        next cycle, or a replica that is not the leader): list_alerts skips it, so nothing may ask its remote."""
        remote = _Map({"alice": "all"})
        app = _unstated_app(tmp_path, remote)
        with TestClient(app) as c:
            app.state.store.upsert_cluster("far", "https://api.far.example:6443", False)
            assert c.get("/api/alerts", headers=ALICE).status_code == 200
        assert remote.calls == 0, f"the remote of a row the feed skips was asked {remote.calls} time(s)"


class TestTheTabsCreateRequestResolvesThePair:
    """§3.3: an omitted `visibility` or `identity` is resolved by §3.2's rule, the one discovery applies to the
    Secret the request writes — never field by field."""

    @pytest.fixture
    def post(self, tmp_path, monkeypatch):
        written: list[tuple[str, str]] = []

        def create(host_client, namespace, req, *, host_name, taken, viewer):
            writer.validate(req, namespace, host_name=host_name, taken=taken)
            written.append((req.visibility, req.identity))
            return writer.secret_name_for(req.name)
        monkeypatch.setattr(api_mod, "own_namespace", lambda: "gsd")
        monkeypatch.setattr(writer, "create", create)
        app = build_app(Settings(clusters=[ClusterConfig("home", "https://kubernetes.default.svc", token_env="X",
                                                         dashboard_controller=True)],
                                 db_path=str(tmp_path / "t.db"), oauth_proxy_enabled=True, view_restrictions_enabled=True,
                                 cluster_secrets_enabled=True, cluster_secrets_writes_enabled=True),
                        run_poller=False, tier_resolver=lambda v: "all", cluster_admin_resolver=lambda v: "all")

        def _post(**extra):
            body = {"name": "new", "server": "https://api.new.example:6443",
                    "credential": {"kind": "bearerToken", "token": "sha256~a-long-enough-token"}, **extra}
            with TestClient(app) as c:
                return c.post("/api/clusterconfigs", json=body, headers={"X-Forwarded-User": "kubeadmin"}), written
        return _post

    @pytest.mark.parametrize("extra,pair", [
        ({}, ("remote-sar", "same-as-host")),
        ({"identity": "none"}, ("self-only", "none")),
        ({"visibility": "self-only"}, ("self-only", "none")),
        ({"visibility": "inherit"}, ("inherit", "none")),
        ({"visibility": "remote-sar", "identity": "same-as-host"}, ("remote-sar", "same-as-host")),
    ], ids=["nothing", "identity-none", "self-only", "inherit", "both"])
    def test_an_omitted_field_is_resolved_by_the_pair_rule(self, post, extra, pair):
        r, written = post(**extra)
        assert r.status_code == 201, r.text
        assert written == [pair]

    def test_the_explicit_remote_sar_none_pair_is_refused_by_name(self, post):
        r, written = post(visibility="remote-sar", identity="none")
        assert r.status_code == 422 and r.json()["detail"].startswith("identity-invalid:") and written == []
