"""Per-cluster authorization: the host's tier never widens a remote unless the operator says so.

THE EXPOSURE (docs/reference-architecture.md §7.2, before 0.19.0): the tier was decided against the
first enabled cluster and gated every cluster's rows, so a host cluster-admin was served a remote's
membership, bindings and login failures with no standing there. These tests pin the four policies
and the identity switch (gsd/config.py CLUSTER_VISIBILITIES, CLUSTER_IDENTITIES) at the API handler,
through the app.state seams, without a cluster.

The matrix below is the contract: a policy may narrow what the host decided and may substitute the
remote's own decision; nothing here may widen.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, ConfigError, Settings, load_settings
from gsd.store import Store
from gsd.timeutil import now_iso

ROOT = {"X-Forwarded-User": "root"}      # wide on the host
ALICE = {"X-Forwarded-User": "alice"}    # self on the host, a member everywhere


def _seed(db: str) -> None:
    store = Store(db)
    now = now_iso()
    for cid in ("host", "east", "west", "far", "dark"):
        store.upsert_cluster(cid, f"https://api.{cid}.example:6443", True)
        store.record_poll(cid, "ok", None)
        store.replace_group_state(cid, [
            {"name": f"{cid}-admins", "member_count": 1, "sync_provider": "ldap_ldap",
             "group_synced_at": now, "ldap_uid": None},
            {"name": f"{cid}-devs", "member_count": 1, "sync_provider": "ldap_ldap",
             "group_synced_at": now, "ldap_uid": None},
        ], now)
        store.sync_members(cid, {f"{cid}-admins": ["alice"], f"{cid}-devs": ["bob"]}, {}, now)
        # A managed group that vanished + a binding naming it: one dangling_binding alert per
        # cluster, an administrator-tier kind, so the per-cluster alert filter is observable.
        store.record_managed_groups(cid, [{"name": f"{cid}-gone", "sync_provider": "ldap_ldap"}], now)
        store.replace_bindings(cid, [
            {"binding_kind": "RoleBinding", "binding_namespace": "ns1",
             "binding_name": f"{cid}-gone-rb", "role_kind": "ClusterRole",
             "role_name": "admin", "group_name": f"{cid}-gone"},
        ], now)
    store.close()


class _Map:
    def __init__(self, tiers):
        self.tiers, self.calls = tiers, 0

    def resolve(self, viewer):
        self.calls += 1
        return self.tiers.get(viewer, "self")


def _settings(db: str, **kw) -> Settings:
    kw.setdefault("oauth_proxy_enabled", True)
    return Settings(clusters=[
        ClusterConfig("host", "https://api.host.example:6443", token_env="X"),
        ClusterConfig("east", "https://api.east.example:6443", token_env="X",
                      visibility="self-only", identity="same-as-host"),
        ClusterConfig("west", "https://api.west.example:6443", token_env="X",
                      visibility="remote-sar", identity="same-as-host"),
        ClusterConfig("far", "https://api.far.example:6443", token_env="X"),   # the defaults
        ClusterConfig("dark", "https://api.dark.example:6443", token_env="X",
                      visibility="hidden"),
    ], db_path=db, **kw)


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> str:
    path = str(tmp_path_factory.mktemp("mc") / "gsd.db")
    _seed(path)
    return path


@pytest.fixture(scope="module")
def client(db):
    app = build_app(_settings(db), run_poller=False)
    app.state.tier_resolver = _Map({"root": "all"})
    # west's own RBAC disagrees with the host's on purpose: alice administers west, root does not.
    app.state.remote_tier_resolvers = {"west": _Map({"alice": "all"})}
    with TestClient(app) as c:
        yield c


class TestTheDefaultsResolve:
    def test_host_is_inherit_same_as_host_and_a_remote_is_self_only_none(self, db):
        s = _settings(db)
        assert s.cluster_policy("host") == ("inherit", "same-as-host")
        assert s.cluster_policy("far") == ("self-only", "none")
        assert s.cluster_policy("east") == ("self-only", "same-as-host")

    def test_a_cluster_no_longer_configured_is_not_widened_beyond_today(self, db):
        assert _settings(db).cluster_policy("ghost") == ("inherit", "same-as-host")


class TestInheritIsTodaysBehaviour:
    def test_root_is_wide_and_alice_is_self_on_the_host(self, client):
        assert client.get("/api/clusters/host/groups", headers=ROOT).json()["scope"] == "all"
        body = client.get("/api/clusters/host/groups", headers=ALICE).json()
        assert body["scope"] == "self"
        assert [g["name"] for g in body["groups"]] == ["host-admins"]


class TestSelfOnlyNeverWidens:
    def test_the_host_administrator_is_self_on_east(self, client):
        body = client.get("/api/clusters/east/groups", headers=ROOT).json()
        assert body["scope"] == "self" and body["viewer"] == "root"
        assert body["groups"] == []
        assert client.get("/api/clusters/east/bindings/findings", headers=ROOT).status_code == 403

    def test_a_same_as_host_identity_gets_their_own_rows_on_east(self, client):
        body = client.get("/api/clusters/east/groups", headers=ALICE).json()
        assert [g["name"] for g in body["groups"]] == ["east-admins"]

    def test_identity_none_refuses_person_scoped_views_and_serves_health(self, client):
        refused = client.get("/api/clusters/far/groups", headers=ROOT)
        assert refused.status_code == 403
        assert "does not treat your identity" in refused.json()["detail"]
        # Never the chart value that would change it: the sentence reaches the refused reader.
        assert "identity" not in refused.json()["detail"].split("your identity")[1]
        for path in ("/api/clusters/far/users/alice", "/api/clusters/far/logins",
                     "/api/clusters/far/user-bindings", "/api/clusters/far/membership-changes",
                     "/api/clusters/far/cluster-access"):
            assert client.get(path, headers=ROOT).status_code == 403, path
        # CR health is full at both tiers by ruling and stays served, projected.
        crs = client.get("/api/clusters/far/groupsyncs", headers=ROOT)
        assert crs.status_code == 200
        assert all("ldap_filter" not in cr for cr in crs.json())


CLUSTER_ENDPOINTS = ("groupsyncs", "groupsyncs/x/events", "groups", "groups/x", "users", "users/x", "logins",
                     "cluster-access", "bindings/findings", "user-bindings", "operator-configs", "membership-changes")


class TestHiddenIsNotAnOracle:
    def test_hidden_and_unknown_are_the_same_404(self, client):
        for headers in (ROOT, ALICE):
            a = client.get("/api/clusters/dark/groups", headers=headers)
            b = client.get("/api/clusters/no-such/groups", headers=headers)
            assert a.status_code == b.status_code == 404
            assert a.json()["detail"].replace("dark", "X") == b.json()["detail"].replace("no-such", "X")

    @pytest.mark.parametrize("suffix", CLUSTER_ENDPOINTS)
    def test_every_cluster_handler_answers_hidden_like_unknown(self, client, suffix):
        """Codex, review D2: the twelve `/api/clusters/{id}/…` handlers, each measured — the same
        status and the same sentence, differing only by the id the caller sent (which is the
        caller's own input, not information about the server)."""
        for headers in (ROOT, ALICE):
            a = client.get(f"/api/clusters/dark/{suffix}", headers=headers)
            b = client.get(f"/api/clusters/no-such/{suffix}", headers=headers)
            assert a.status_code == b.status_code == 404, suffix
            assert a.json()["detail"].replace("dark", "X") == b.json()["detail"].replace("no-such", "X"), suffix

    def test_hidden_is_absent_from_the_lists(self, client):
        ids = {c["id"] for c in client.get("/api/clusters", headers=ROOT).json()}
        assert "dark" not in ids and {"host", "east", "west", "far"} <= ids
        who = client.get("/api/whoami", headers=ROOT).json()
        assert "dark" not in who["visibility"]["clusters"]
        alerts = client.get("/api/alerts", headers=ROOT).json()
        assert not any(a["cluster"] == "dark" for a in alerts["alerts"])


class TestRemoteSarIsTheRemotesDecision:
    def test_alice_is_wide_on_west_and_self_on_the_host(self, client):
        assert client.get("/api/clusters/west/groups", headers=ALICE).json()["scope"] == "all"
        assert client.get("/api/clusters/host/groups", headers=ALICE).json()["scope"] == "self"

    def test_root_is_not_wide_on_west_because_the_host_said_so(self, client):
        assert client.get("/api/clusters/west/groups", headers=ROOT).json()["scope"] == "self"

    def test_a_missing_remote_resolver_is_self_never_the_hosts_answer(self, db):
        app = build_app(_settings(db), run_poller=False)
        app.state.tier_resolver = _Map({"root": "all"})
        app.state.remote_tier_resolvers = {}
        with TestClient(app) as c:
            assert c.get("/api/clusters/west/groups", headers=ROOT).json()["scope"] == "self"

    def test_a_raising_remote_resolver_is_self(self, db):
        class Boom:
            def resolve(self, viewer):
                raise RuntimeError("remote down")
        app = build_app(_settings(db), run_poller=False)
        app.state.tier_resolver = _Map({"root": "all"})
        app.state.remote_tier_resolvers = {"west": Boom()}
        with TestClient(app) as c:
            assert c.get("/api/clusters/west/groups", headers=ALICE).json()["scope"] == "self"


class TestTheWireSaysSo:
    def test_whoami_carries_every_served_clusters_decision(self, client):
        vis = client.get("/api/whoami", headers=ROOT).json()["visibility"]
        assert vis["scope"] == "all"
        assert vis["clusters"] == {
            "host": {"policy": "inherit", "identity": "same-as-host", "scope": "all"},
            "east": {"policy": "self-only", "identity": "same-as-host", "scope": "self"},
            "west": {"policy": "remote-sar", "identity": "same-as-host", "scope": "self"},
            "far": {"policy": "self-only", "identity": "none", "scope": "self"},
        }

    def test_cluster_rows_carry_policy_and_scope_and_withhold_accordingly(self, client):
        rows = {c["id"]: c for c in client.get("/api/clusters", headers=ROOT).json()}
        assert rows["host"]["visibility"] == {"policy": "inherit", "scope": "all"}
        assert rows["east"]["visibility"] == {"policy": "self-only", "scope": "self"}
        assert rows["east"]["operator_configs"] is None

    def test_alerts_are_filtered_per_cluster_in_that_clusters_tier(self, client):
        body = client.get("/api/alerts", headers=ROOT).json()
        dangling = {a["cluster"] for a in body["alerts"] if a["kind"] == "dangling_binding"}
        assert dangling == {"host"}, "an administrator-tier kind leaked from a narrowed cluster"
        assert body["scope"] == "self", "narrowed somewhere must not read as wide everywhere"
        alice = client.get("/api/alerts", headers=ALICE).json()
        assert {a["cluster"] for a in alice["alerts"] if a["kind"] == "dangling_binding"} == {"west"}


class TestInheritIsTheHostsDecidedTier:
    """Cursor, review D2 (its most important finding): `inherit` meant the host's RESOLVER, so a
    `self-only` host with an `inherit` remote — legal per the guard — served the remote wide to a
    reader the host itself refused to widen, and the whoami headline said `all` above a host row
    that said `self`. Measured before the fix: host self, east all, findings 200."""

    def test_a_self_only_host_does_not_leave_an_inherit_remote_wide(self, db):
        settings = Settings(clusters=[
            ClusterConfig("host", "https://api.host.example:6443", token_env="X", visibility="self-only"),
            ClusterConfig("east", "https://api.east.example:6443", token_env="X",
                          visibility="inherit", identity="same-as-host"),
        ], db_path=db, oauth_proxy_enabled=True)
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _Map({"root": "all"})
        with TestClient(app) as c:
            assert c.get("/api/clusters/host/groups", headers=ROOT).json()["scope"] == "self"
            assert c.get("/api/clusters/east/groups", headers=ROOT).json()["scope"] == "self", \
                "inherit must not outrun a self-only host"
            assert c.get("/api/clusters/east/bindings/findings", headers=ROOT).status_code == 403
            who = c.get("/api/whoami", headers=ROOT).json()["visibility"]
            assert who["scope"] == "self", "the headline is the host's decision, and the host is self-only"
            assert c.get("/api/clusters/host/bindings/findings", headers=ROOT).status_code == 403

    def test_inherit_under_a_self_only_host_keeps_the_username_at_identity_none(self, db):
        """Cursor, review D2 second pass (its most important finding): the first-pass remap
        applied the remote's default `identity: none` AFTER remapping inherit onto the host's
        self-only, and withheld the viewer — §11 says identity is not consulted under inherit.
        The first-pass test hid it by setting same-as-host."""
        settings = Settings(clusters=[
            ClusterConfig("host", "https://api.host.example:6443", token_env="X", visibility="self-only"),
            ClusterConfig("east", "https://api.east.example:6443", token_env="X", visibility="inherit"),
        ], db_path=db, oauth_proxy_enabled=True)
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _Map({"root": "all"})
        with TestClient(app) as c:
            body = c.get("/api/clusters/east/groups", headers=ROOT)
            assert body.status_code == 200, body.json()
            assert body.json()["scope"] == "self" and body.json()["viewer"] == "root"
            alice = c.get("/api/clusters/east/groups", headers=ALICE).json()
            assert alice["viewer"] == "alice" and [g["name"] for g in alice["groups"]] == ["east-admins"]
            who = c.get("/api/whoami", headers=ROOT).json()["visibility"]
            assert who["scope"] == "self"
            assert who["clusters"]["east"] == {"policy": "inherit", "identity": "none", "scope": "self"}

    def test_no_enabled_cluster_fails_closed_on_the_headline(self, tmp_path):
        """Cursor, second pass: with every entry disabled there is no host, and the nameless
        question fell through to the host resolver — `all` above rows that all said `self`.

        Its own db, not the module-scoped one: build_app's lifespan upserts these disabled clusters
        (run_poller=False still records them), and once list_clusters skips enabled=0 (the #96 retire
        rule) that would leak host/east=disabled into the shared-db tests that follow."""
        db = str(tmp_path / "no-enabled.db")
        settings = Settings(clusters=[
            ClusterConfig("host", "https://api.host.example:6443", token_env="X", enabled=False),
            ClusterConfig("east", "https://api.east.example:6443", token_env="X", enabled=False),
        ], db_path=db, oauth_proxy_enabled=True)
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _Map({"root": "all"})
        with TestClient(app) as c:
            who = c.get("/api/whoami", headers=ROOT).json()["visibility"]
            assert who["scope"] == "self"          # the nameless headline fails closed with no host
            # #96: a disabled cluster is not served, so every-entry-disabled serves NOTHING — the rows
            # are empty rather than a wall of `self` clusters the selector would never offer.
            assert who["clusters"] == {}
            # And the alert feed must agree: zero served clusters is not a wide `all` view above an
            # empty list ("you are wide and the estate is green") — it fails closed to self (review).
            assert c.get("/api/alerts", headers=ROOT).json() == {
                "scope": "self", "viewer": "root", "count": 0, "alerts": []}

    def test_an_inherit_host_still_decides_by_its_resolver(self, client):
        assert client.get("/api/whoami", headers=ROOT).json()["visibility"]["scope"] == "all"
        assert client.get("/api/whoami", headers=ALICE).json()["visibility"]["scope"] == "self"


def _admin_decisions(text: str) -> int:
    return int(sum(float(line.rsplit(" ", 1)[1]) for line in text.splitlines()
                   if line.startswith('gsd_visibility_decisions_total{threshold="admin"')))


def test_whoami_and_alerts_note_one_decision_per_served_cluster(client):
    """Cursor, second pass: whoami and alerts decided the host twice — once nameless for the
    headline, once as a row — so gsd_visibility_decisions_total counted five for four served
    clusters (measured: 2 after one whoami on a one-cluster app). The headline is the host row."""
    before = _admin_decisions(client.get("/metrics").text)
    client.get("/api/whoami", headers=ROOT)
    after_who = _admin_decisions(client.get("/metrics").text)
    assert after_who - before == 4, (before, after_who)
    client.get("/api/clusters", headers=ROOT)
    after_cl = _admin_decisions(client.get("/metrics").text)
    assert after_cl - after_who == 4
    client.get("/api/alerts", headers=ROOT)
    after_al = _admin_decisions(client.get("/metrics").text)
    assert after_al - after_cl == 4
    client.get("/api/clusters/host/groups", headers=ROOT)
    assert _admin_decisions(client.get("/metrics").text) - after_al == 1


def test_manual_alerts_keep_the_common_silence_fields(tmp_path):
    """Codex, review D2: the poll-failure and dangling-binding alerts are built by hand in
    list_alerts and, since D2's block predated B4, lost the `silenced`/`silenced_by` every alert
    carries (gsd/state.py#Alert) — measured against main's wire."""
    db = str(tmp_path / "alerts.db")
    _seed(db)
    store = Store(db)
    store.record_poll("host", "unreachable", "remote API timed out")
    store.close()
    settings = Settings(clusters=[
        ClusterConfig("host", "https://api.host.example:6443", token_env="X"),
        ClusterConfig("east", "https://api.east.example:6443", token_env="X", visibility="inherit"),
    ], db_path=db, oauth_proxy_enabled=True)
    app = build_app(settings, run_poller=False, tier_resolver=lambda viewer: "all")
    with TestClient(app) as c:
        alerts = c.get("/api/alerts", headers=ROOT).json()["alerts"]
    manual = [a for a in alerts if a["kind"] in {"unreachable", "dangling_binding"}]
    assert {a["kind"] for a in manual} == {"unreachable", "dangling_binding"}
    for a in manual:
        assert a["silenced"] is False and a["silenced_by"] is None, a


class TestRestrictionsOff:
    def test_off_is_off_for_every_policy_but_hidden(self, db):
        app = build_app(_settings(db, view_restrictions_enabled=False), run_poller=False)
        with TestClient(app) as c:
            for cid in ("host", "east", "west", "far"):
                assert c.get(f"/api/clusters/{cid}/groups", headers=ALICE).json()["scope"] == "all"
            assert c.get("/api/clusters/dark/groups", headers=ALICE).status_code == 404


def test_access_control_section_11_names_only_routes_the_app_serves():
    """Both reviewers of D2: §11 named `/api/events`, a route that does not exist (the events
    handler is under `/api/clusters/{id}/groupsyncs/{name}/events`). Every `/api/…` path the
    section names is held to the app's route table, with `{id}`/`{name}` as the placeholders."""
    import pathlib
    import re
    text = (pathlib.Path(__file__).resolve().parents[2] / "docs" / "ACCESS_CONTROL.md").read_text()
    section = text.split("## 11. Several clusters in one instance", 1)[1].split("\n## ", 1)[0]
    app = build_app(Settings(clusters=[ClusterConfig("h", "https://h", token_env="X")], oauth_proxy_enabled=True),
                    run_poller=False)
    routes = {getattr(r, "path", "").replace("{cluster_id}", "{id}") for r in app.routes}
    named = set(re.findall(r"`(/api/[A-Za-z0-9_{}/.-]*?)`", section))
    named = {n.rstrip("/") for n in named if "…" not in n and "{name}" not in n or n.endswith("/events")}
    assert named, "the section names no route at all"
    unknown = {n for n in named if n not in routes and not any(r.startswith(n + "/") for r in routes)}
    assert not unknown, f"§11 names routes the app does not serve: {sorted(unknown)}"


def test_access_control_decision_diagram_cites_definitions_not_line_numbers():
    """Codex, review D2 second pass: §5's diagram still wrote `api.py:244` beside functions that
    had moved hundreds of lines — the line-number rot the citation rule exists to end, surviving
    inside a code block the rule does not scan. Every anchor in the diagram is a definition."""
    import pathlib
    import re
    root = pathlib.Path(__file__).resolve().parents[2]
    text = (root / "docs" / "ACCESS_CONTROL.md").read_text()
    section = text.split("## 5. How a request becomes a decision", 1)[1].split("\n## ", 1)[0]
    diagram = section.split("```", 2)[1]          # the fenced decision diagram alone
    assert not re.findall(r"\b(?:api|config)\.py:\d+\b", diagram), "a line-number citation is back"
    cited = re.findall(r"gsd/(api|config)\.py#([A-Za-z_.]+)", diagram)
    assert len(cited) >= 6, cited
    for module, symbol in cited:
        source = (root / "local-development" / "gsd" / f"{module}.py").read_text()
        name = symbol.rsplit(".", 1)[-1]
        assert re.search(rf"^\s*def {re.escape(name)}\(", source, re.M), f"{module}.py has no def {name}"


class TestConfigValidation:
    BASE = """
clusters:
  - name: host
    apiUrl: https://api.host.example:6443
    tokenEnv: X
  - name: east
    apiUrl: https://api.east.example:6443
    tokenEnv: X
"""

    def _load(self, tmp_path, text):
        p = tmp_path / "clusters.yaml"
        p.write_text(text)
        return load_settings(str(p))

    def test_defaults_resolve_from_a_file_too(self, tmp_path):
        s = self._load(tmp_path, self.BASE)
        assert s.cluster_policy("east") == ("self-only", "none")

    def test_an_unknown_policy_is_refused(self, tmp_path):
        with pytest.raises(ConfigError, match="visibility 'Hidden'"):
            self._load(tmp_path, self.BASE + "    visibility: Hidden\n")

    def test_remote_sar_needs_same_as_host(self, tmp_path):
        with pytest.raises(ConfigError, match="needs identity: same-as-host"):
            self._load(tmp_path, self.BASE + "    visibility: remote-sar\n")
        s = self._load(tmp_path, self.BASE + "    visibility: remote-sar\n    identity: same-as-host\n")
        assert s.cluster_policy("east") == ("remote-sar", "same-as-host")

    def test_hidden_and_remote_sar_are_refused_on_the_host(self, tmp_path):
        for policy in ("hidden", "remote-sar"):
            text = self.BASE.replace("    tokenEnv: X\n  - name: east",
                                     f"    tokenEnv: X\n    visibility: {policy}\n  - name: east", 1)
            with pytest.raises(ConfigError, match="hosting cluster"):
                self._load(tmp_path, text)

    @pytest.mark.parametrize("key", ("visibility", "identity"))
    @pytest.mark.parametrize("yaml_value", ('""', "'   '"))
    def test_blank_policy_values_are_unset_like_the_chart_says(self, tmp_path, key, yaml_value):
        """Codex, review D2 (its most important finding): the chart's guard tolerates a blank or
        whitespace value as unset and renders it through, and load_settings refused it — a pod
        that crashed at startup after a green `helm upgrade`. Measured: `visibility: ""` → ConfigError."""
        settings = self._load(tmp_path, self.BASE + f"    {key}: {yaml_value}\n")
        assert settings.cluster_policy("east") == ("self-only", "none")
        assert getattr(settings.cluster("east"), key) is None

    @pytest.mark.parametrize("spelling", ("false", '"false"', "'false'", " false "))
    def test_enabled_is_a_word_so_a_quoted_false_disables(self, tmp_path, spelling):
        """Codex, review D2 second pass (its most important finding): `bool("false")` is True, so a
        quoted `enabled: "false"` — what a templating system emits — enabled the entry, and since
        D2 the first ENABLED entry is the authorization host. Measured: the quoted first entry
        became the host."""
        text = self.BASE.replace("    tokenEnv: X\n  - name: east", f"    tokenEnv: X\n    enabled: {spelling}\n  - name: east", 1)
        s = self._load(tmp_path, text)
        assert s.cluster("host").enabled is False
        assert s.host_cluster().name == "east"

    @pytest.mark.parametrize("bad", ("maybe", "1", "0", '"yes"', "[true]", "{a: 1}"))
    def test_enabled_refuses_every_other_spelling_by_name(self, tmp_path, bad):
        """(An unquoted `yes` is a YAML 1.1 boolean and arrives as True — the loader's doing, not
        a spelling this parser sees.)"""
        text = self.BASE.replace("    tokenEnv: X\n  - name: east", f"    tokenEnv: X\n    enabled: {bad}\n  - name: east", 1)
        with pytest.raises(ConfigError, match="enabled must be true or false"):
            self._load(tmp_path, text)

    def test_a_disabled_first_entry_is_not_the_host(self, tmp_path):
        text = self.BASE.replace("    tokenEnv: X\n  - name: east",
                                 "    tokenEnv: X\n    enabled: false\n  - name: east", 1)
        s = self._load(tmp_path, text)
        assert s.host_cluster().name == "east"
        assert s.cluster_policy("east") == ("inherit", "same-as-host")
