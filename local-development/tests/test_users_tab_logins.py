"""/users lists the people who have logged in, and says so honestly at every edge.

docs/DESIGN_users_tab_logins.md: the row is the OpenShift User object, which the cluster creates at a
person's first login and never before. Group membership is an attribute of a row; a synced member who
has never logged in is not a row but a count. These tests pin the wire shape the tab reads, the
paging rule (docs/api-contract.md R3) the endpoint never met before, the tier scoping on BOTH
sources, and the one behaviour that matters most on a fresh or under-granted install: an empty table
is never presented as "nobody has logged in".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from gsd import loginlog
from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.store import Store

NOW = datetime(2026, 9, 3, 12, 0, tzinfo=UTC)


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


def _rec(name, full=None, created=None, providers=("ldap-local",), has_identity=True):
    return {"user_name": name, "full_name": full, "created_at": created or _iso(NOW - timedelta(days=10)),
            "providers": list(providers), "has_identity": has_identity}


def _seed(db: str, *, users=True, capture_events=True) -> None:
    store = Store(db)
    store.upsert_cluster("c1", "https://x", True)
    store.sync_members("c1", {"team-a": ["alice", "dave"], "gate": ["alice", "gatekeeper"]}, {}, _iso(NOW - timedelta(hours=2)))
    if users:
        store.replace_users("c1", [
            _rec("alice", "Alice Cooper", created=_iso(NOW - timedelta(days=30))),
            _rec("gatekeeper"),
            _rec("kubeadmin", providers=("developer",), created=_iso(NOW - timedelta(days=400))),
            _rec("manual", providers=(), has_identity=False),
        ], _iso(NOW - timedelta(minutes=1)))
    if capture_events:
        store.record_login_events("c1", [
            {"pod_name": "oauth-1", "user_name": "alice", "outcome": loginlog.OUTCOME_SUCCESS,
             "at": _iso(NOW - timedelta(hours=3)), "provider": "ldap-local", "ldap_result_code": None,
             "detail": None, "observed_at": _iso(NOW)},
            {"pod_name": "oauth-1", "user_name": "alice", "outcome": loginlog.OUTCOME_SUCCESS,
             "at": _iso(NOW - timedelta(hours=1)), "provider": "ldap-local", "ldap_result_code": None,
             "detail": None, "observed_at": _iso(NOW)},
            {"pod_name": "oauth-1", "user_name": "gatekeeper", "outcome": loginlog.OUTCOME_BAD_PASSWORD,
             "at": _iso(NOW - timedelta(hours=1)), "provider": "ldap-local", "ldap_result_code": 49,
             "detail": None, "observed_at": _iso(NOW)},
        ])
    store.close()


def _client(tmp_path, *, login_capture=True, tier="all", **seed) -> TestClient:
    db = str(tmp_path / "t.db")
    _seed(db, **seed)
    settings = Settings(clusters=[ClusterConfig("c1", "https://x", token_env="T")], db_path=db,
                        oauth_proxy_enabled=True, login_capture_enabled=login_capture)
    return TestClient(build_app(settings, run_poller=False, tier_resolver=lambda viewer: tier))


ADMIN = {"X-Forwarded-User": "root"}


class TestTheListIsThePeopleWhoHaveLoggedIn:
    def test_rows_are_user_objects_with_membership_as_an_attribute(self, tmp_path):
        body = _client(tmp_path).get("/api/clusters/c1/users", headers=ADMIN).json()
        rows = {u["user_name"]: u for u in body["users"]}
        assert list(rows) == ["alice", "gatekeeper", "kubeadmin", "manual"], "ordered by id; dave is not a row"
        assert rows["alice"]["group_count"] == 2 and rows["kubeadmin"]["group_count"] == 0
        assert rows["alice"]["first_seen_at"] is not None and rows["kubeadmin"]["first_seen_at"] is None

    def test_each_row_says_whether_and_since_when_the_person_logged_in(self, tmp_path):
        rows = {u["user_name"]: u for u in _client(tmp_path).get("/api/clusters/c1/users", headers=ADMIN).json()["users"]}
        assert rows["alice"]["logged_in"] is True
        assert rows["alice"]["first_login_at"] == _iso(NOW - timedelta(days=30)), "the User's creation time"
        assert rows["alice"]["providers"] == ["ldap-local"]
        assert rows["kubeadmin"]["providers"] == ["developer"]
        # An account created by hand: a User object, no identity, nobody has ever logged in as it.
        assert rows["manual"]["logged_in"] is False and rows["manual"]["first_login_at"] is None
        assert rows["manual"]["providers"] == []

    def test_last_login_is_the_newest_successful_captured_attempt_only(self, tmp_path):
        body = _client(tmp_path).get("/api/clusters/c1/users", headers=ADMIN).json()
        rows = {u["user_name"]: u for u in body["users"]}
        assert body["login_capture"] == "on"
        assert rows["alice"]["last_login_at"] == _iso(NOW - timedelta(hours=1))
        assert rows["gatekeeper"]["last_login_at"] is None, "a failed attempt is not a login"
        assert rows["kubeadmin"]["last_login_at"] is None

    def test_with_capture_off_the_response_says_so_rather_than_implying_nobody_logged_in(self, tmp_path):
        body = _client(tmp_path, login_capture=False, capture_events=False).get("/api/clusters/c1/users", headers=ADMIN).json()
        assert body["login_capture"] == "off"
        assert all(u["last_login_at"] is None for u in body["users"])

    def test_the_headline_counts_logins_not_user_objects(self, tmp_path):
        """Four User objects, one of them a manual account nobody has logged in as: total says 4,
        the headline says 3. Codex (#47) caught the headline counting the manual account as a login
        while its own row said "never logged in"."""
        body = _client(tmp_path).get("/api/clusters/c1/users", headers=ADMIN).json()
        assert body["total"] == 4 and body["logged_in_total"] == 3

    def test_synced_members_who_never_logged_in_are_a_count_and_names_not_rows(self, tmp_path):
        body = _client(tmp_path).get("/api/clusters/c1/users", headers=ADMIN).json()
        assert body["never_logged_in_members"] == {"count": 1, "names": ["dave"]}
        assert "dave" not in {u["user_name"] for u in body["users"]}

    def test_a_named_user_still_joins_every_member_surface(self, tmp_path):
        """The display name was the original job of this data and it must survive the re-sourcing:
        the member list of a group still carries it, and a member with no User still reads as None."""
        db = str(tmp_path / "t.db")
        _seed(db)
        store = Store(db)
        members = {m["user_name"]: m["full_name"] for m in store.group_members("c1", "team-a")}
        store.close()
        assert members == {"alice": "Alice Cooper", "dave": None}


class TestPagingPerR3:
    def test_total_offset_and_limit_describe_the_whole_set_and_this_page(self, tmp_path):
        c = _client(tmp_path)
        page1 = c.get("/api/clusters/c1/users?limit=3", headers=ADMIN).json()
        assert (page1["total"], page1["offset"], page1["limit"], page1["count"], page1["truncated"]) == (4, 0, 3, 3, True)
        page2 = c.get("/api/clusters/c1/users?limit=3&offset=3", headers=ADMIN).json()
        assert [u["user_name"] for u in page2["users"]] == ["manual"]
        assert (page2["total"], page2["offset"], page2["truncated"]) == (4, 3, False)

    def test_an_offset_past_the_total_is_an_empty_page_that_still_states_the_total(self, tmp_path):
        body = _client(tmp_path).get("/api/clusters/c1/users?limit=3&offset=40", headers=ADMIN).json()
        assert body["users"] == [] and body["count"] == 0 and body["truncated"] is False
        assert (body["total"], body["offset"]) == (4, 40), "the whole set is still described"

    def test_providers_are_sorted_on_the_wire_whatever_order_the_poll_saw(self, tmp_path):
        """Pinned on the JSON, not only in the kube fetch: replace_users sorts too."""
        db = str(tmp_path / "t.db")
        _seed(db)
        store = Store(db)
        store.replace_users("c1", [_rec("two", providers=("zeta", "alpha"))], _iso(NOW))
        store.close()
        settings = Settings(clusters=[ClusterConfig("c1", "https://x", token_env="T")], db_path=db, oauth_proxy_enabled=True)
        body = TestClient(build_app(settings, run_poller=False, tier_resolver=lambda v: "all")).get(
            "/api/clusters/c1/users", headers=ADMIN).json()
        assert body["users"][0]["providers"] == ["alpha", "zeta"]

    def test_a_negative_offset_is_refused(self, tmp_path):
        assert _client(tmp_path).get("/api/clusters/c1/users?offset=-1", headers=ADMIN).status_code == 422


class TestTheSourceIsReported:
    def test_ok_after_a_poll_that_could_read_users(self, tmp_path):
        body = _client(tmp_path).get("/api/clusters/c1/users", headers=ADMIN).json()
        assert body["source"] == "ok" and body["source_observed_at"] == _iso(NOW - timedelta(minutes=1))

    def test_pending_before_any_poll_has_reported_so_an_empty_table_is_not_an_empty_cluster(self, tmp_path):
        body = _client(tmp_path, users=False).get("/api/clusters/c1/users", headers=ADMIN).json()
        assert body["source"] == "pending" and body["users"] == [] and body["total"] == 0
        # The members are all "never logged in" as far as the store knows — and the tab must qualify
        # that with the pending source, which is why both travel in one response.
        assert body["never_logged_in_members"]["names"] == ["alice", "dave", "gatekeeper"]

    def test_forbidden_after_a_refused_poll_keeps_last_cycles_rows_and_says_why(self, tmp_path):
        db = str(tmp_path / "t.db")
        _seed(db)
        store = Store(db)
        store.mark_users_unavailable("c1", _iso(NOW))
        store.close()
        settings = Settings(clusters=[ClusterConfig("c1", "https://x", token_env="T")], db_path=db,
                            oauth_proxy_enabled=True)
        body = TestClient(build_app(settings, run_poller=False, tier_resolver=lambda v: "all")).get(
            "/api/clusters/c1/users", headers=ADMIN).json()
        assert body["source"] == "forbidden" and body["source_observed_at"] == _iso(NOW)
        assert len(body["users"]) == 4, "the refusal does not erase what the last successful poll wrote"


class TestTheSelfTierScopesBothSources:
    def test_a_narrowed_reader_gets_their_own_row_and_nobody_elses_name_anywhere(self, tmp_path):
        resp = _client(tmp_path, tier="self").get("/api/clusters/c1/users", headers={"X-Forwarded-User": "alice"})
        body = resp.json()
        assert body["scope"] == "self"
        assert [u["user_name"] for u in body["users"]] == ["alice"] and body["total"] == 1
        assert body["never_logged_in_members"] == {"count": 0, "names": []}, "dave's status is not theirs to see"
        for other in ("gatekeeper", "kubeadmin", "manual", "dave"):
            assert other not in resp.text

    def test_a_case_variant_of_another_user_is_not_that_user(self, tmp_path):
        """Byte-exact scoping: ALICE is not alice. The variant gets an empty view, never alice's row."""
        resp = _client(tmp_path, tier="self").get("/api/clusters/c1/users", headers={"X-Forwarded-User": "ALICE"})
        body = resp.json()
        assert body["users"] == [] and body["total"] == 0 and body["logged_in_total"] == 0
        assert "Alice Cooper" not in resp.text and "alice" not in {u["user_name"] for u in body["users"]}

    def test_a_narrowed_reader_who_never_logged_in_sees_only_that_fact_about_themselves(self, tmp_path):
        body = _client(tmp_path, tier="self").get("/api/clusters/c1/users", headers={"X-Forwarded-User": "dave"}).json()
        assert body["users"] == [] and body["total"] == 0
        assert body["never_logged_in_members"] == {"count": 1, "names": ["dave"]}


class TestTheDetailPage:
    def test_a_user_in_no_group_is_a_person_not_a_404(self, tmp_path):
        body = _client(tmp_path).get("/api/clusters/c1/users/kubeadmin", headers=ADMIN)
        assert body.status_code == 200
        d = body.json()
        assert d["groups"] == [] and d["logged_in"] is True and d["providers"] == ["developer"]
        assert d["first_login_at"] == _iso(NOW - timedelta(days=400)) and d["login_capture"] == "on"

    def test_a_member_who_never_logged_in_says_so(self, tmp_path):
        d = _client(tmp_path).get("/api/clusters/c1/users/dave", headers=ADMIN).json()
        assert [g["group_name"] for g in d["groups"]] == ["team-a"]
        assert d["logged_in"] is False and d["first_login_at"] is None and d["providers"] == []

    def test_a_name_seen_nowhere_is_still_a_404(self, tmp_path):
        assert _client(tmp_path).get("/api/clusters/c1/users/nobody", headers=ADMIN).status_code == 404
