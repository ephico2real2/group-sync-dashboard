"""The audit-log source: the parser, the kinds, the identity match, the cursor, the backfill, and the
link to pod-log rows.

FIXTURES ARE MEASURED, NOT DOCUMENTED-SHAPE. Every record in FIXTURES is a real line from the
reference cluster's oauth-server audit log (`oc adm node-logs --role=master --path=oauth-server/audit.log`,
49,360 records read on 2026-09-05), one per request shape the grounding note of
docs/specs/SPEC_D1_audit_log_login_capture.md counted, with the usernames replaced by `userN.example`
and nothing else changed — field set, values, query strings, status messages and stamps are the
cluster's own. The `crc ` node-name prefix `oc adm node-logs --role` writes is kept on one of them.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import pytest

from gsd import auditlog, logincapture, loginlog
from gsd.auditlog import (AUDIT_FILE, KIND_CLI, KIND_CREDENTIAL, KIND_SESSION, SKIPPED, IdentityIndex,
                          audit_event_dict, capture_once, complete_lines, decode_identity_suffix,
                          fingerprint, identity_match_for, ignored_identity, parse_audit_line,
                          rotated_at)
from gsd.config import ClusterConfig, Settings
from gsd.kube import NodeLogRead
from gsd.logincapture import event_dict
from gsd.loginlog import LoginAttempt
from gsd.store import Store

CLUSTER = ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")
NODE = "crc"

FIXTURES = {
    'head_probe': '{"kind":"Event","apiVersion":"audit.k8s.io/v1","level":"Metadata","auditID":"6e1470e8-07c7-4314-a4b3-44096001b90d","stage":"ResponseComplete","requestURI":"/","verb":"head","user":{"username":"system:anonymous","groups":["system:unauthenticated"]},"sourceIPs":["10.217.0.2"],"userAgent":"Go-http-client/1.1","responseStatus":{"metadata":{},"status":"Failure","message":"forbidden: User \\"system:anonymous\\" cannot head path \\"/\\"","reason":"Forbidden","details":{},"code":403},"requestReceivedTimestamp":"2025-04-19T02:00:05.946135Z","stageTimestamp":"2025-04-19T02:00:05.951167Z","annotations":{"authorization.k8s.io/decision":"forbid","authorization.k8s.io/reason":""}}',
    'cli_allow': '{"kind":"Event","apiVersion":"audit.k8s.io/v1","level":"Metadata","auditID":"ea645771-3edd-4405-88f3-dd727c6d01f4","stage":"ResponseComplete","requestURI":"/oauth/authorize?client_id=openshift-challenging-client&code_challenge=MJQHVSvKQHefDpDvscw7vh8hfYldKObMYSzhUwY_wqc&code_challenge_method=S256&redirect_uri=https%3A%2F%2Foauth-openshift.apps-crc.testing%2Foauth%2Ftoken%2Fimplicit&response_type=code","verb":"get","user":{"username":"system:anonymous","groups":["system:unauthenticated"]},"sourceIPs":["10.217.0.2"],"userAgent":"Go-http-client/1.1","responseStatus":{"metadata":{},"code":302},"requestReceivedTimestamp":"2025-04-19T02:02:33.741413Z","stageTimestamp":"2025-04-19T02:02:34.069027Z","annotations":{"authentication.openshift.io/decision":"allow","authentication.openshift.io/username":"user1.example","authorization.k8s.io/decision":"allow","authorization.k8s.io/reason":""}}',
    'token': '{"kind":"Event","apiVersion":"audit.k8s.io/v1","level":"Metadata","auditID":"c5e2f9b5-2581-433e-b4a8-6325a888ab35","stage":"ResponseComplete","requestURI":"/oauth/token","verb":"post","user":{"username":"system:anonymous","groups":["system:unauthenticated"]},"sourceIPs":["10.217.0.2"],"userAgent":"Go-http-client/1.1","responseStatus":{"metadata":{},"code":200},"requestReceivedTimestamp":"2025-04-19T02:02:34.070992Z","stageTimestamp":"2025-04-19T02:02:34.368481Z","annotations":{"authorization.k8s.io/decision":"allow","authorization.k8s.io/reason":""}}',
    'cli_deny': '{"kind":"Event","apiVersion":"audit.k8s.io/v1","level":"Metadata","auditID":"8ebaa27c-67b3-4ba9-9e08-22cad2acc9d2","stage":"ResponseComplete","requestURI":"/oauth/authorize?client_id=openshift-challenging-client&code_challenge=ks7kUOHYF2gDBbfUpTsastWwXGcS0xHlzBT86SGrLFA&code_challenge_method=S256&redirect_uri=https%3A%2F%2Foauth-openshift.apps-crc.testing%2Foauth%2Ftoken%2Fimplicit&response_type=code","verb":"get","user":{"username":"system:anonymous","groups":["system:unauthenticated"]},"sourceIPs":["10.217.0.2"],"userAgent":"Go-http-client/1.1","responseStatus":{"metadata":{},"message":"Authentication failed, attempted: basic","code":401},"requestReceivedTimestamp":"2025-05-17T15:31:18.953611Z","stageTimestamp":"2025-05-17T15:31:19.013859Z","annotations":{"authentication.openshift.io/decision":"deny","authentication.openshift.io/username":"user1.example","authorization.k8s.io/decision":"allow","authorization.k8s.io/reason":""}}',
    'authorize_deny_no_user': '{"kind":"Event","apiVersion":"audit.k8s.io/v1","level":"Metadata","auditID":"0e968de4-6388-44a8-97bf-c34fb350f644","stage":"ResponseComplete","requestURI":"/oauth/authorize?client_id=console&redirect_uri=https%3A%2F%2Fconsole-openshift-console.apps-crc.testing%2Fauth%2Fcallback&response_type=code&scope=user%3Afull&state=75e1dfd427ee0e22189c763242e73fcb","verb":"get","user":{"username":"system:anonymous","groups":["system:unauthenticated"]},"sourceIPs":["10.217.0.2"],"userAgent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36","responseStatus":{"metadata":{},"code":302},"requestReceivedTimestamp":"2025-05-23T17:37:58.459042Z","stageTimestamp":"2025-05-23T17:37:58.468691Z","annotations":{"authentication.openshift.io/decision":"deny","authorization.k8s.io/decision":"allow","authorization.k8s.io/reason":""}}',
    'credential_allow_plain': '{"kind":"Event","apiVersion":"audit.k8s.io/v1","level":"Metadata","auditID":"05dedf8f-e34e-4385-a7b3-fd5ca3a87d42","stage":"ResponseComplete","requestURI":"/login","verb":"post","user":{"username":"system:anonymous","groups":["system:unauthenticated"]},"sourceIPs":["10.217.0.2"],"userAgent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36","responseStatus":{"metadata":{},"code":302},"requestReceivedTimestamp":"2025-05-23T17:38:04.358501Z","stageTimestamp":"2025-05-23T17:38:04.432936Z","annotations":{"authentication.openshift.io/decision":"allow","authentication.openshift.io/username":"user1.example","authorization.k8s.io/decision":"allow","authorization.k8s.io/reason":""}}',
    'session_allow_browser': '{"kind":"Event","apiVersion":"audit.k8s.io/v1","level":"Metadata","auditID":"85d90703-501c-48b1-ae40-6319ce1d1358","stage":"ResponseComplete","requestURI":"/oauth/authorize?client_id=console&redirect_uri=https%3A%2F%2Fconsole-openshift-console.apps-crc.testing%2Fauth%2Fcallback&response_type=code&scope=user%3Afull&state=75e1dfd427ee0e22189c763242e73fcb","verb":"get","user":{"username":"system:anonymous","groups":["system:unauthenticated"]},"sourceIPs":["10.217.0.2"],"userAgent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36","responseStatus":{"metadata":{},"code":302},"requestReceivedTimestamp":"2025-05-23T17:38:04.436623Z","stageTimestamp":"2025-05-23T17:38:04.495959Z","annotations":{"authentication.openshift.io/decision":"allow","authentication.openshift.io/username":"user1.example","authorization.k8s.io/decision":"allow","authorization.k8s.io/reason":""}}',
    'consent_approve': '{"kind":"Event","apiVersion":"audit.k8s.io/v1","level":"Metadata","auditID":"3250a6b5-3cfb-448a-ac16-3fd0bedf8de2","stage":"ResponseComplete","requestURI":"/oauth/authorize/approve?client_id=system%3Aserviceaccount%3Aopenshift-gitops%3Aopenshift-gitops-argocd-dex-server&redirect_uri=https%3A%2F%2Fopenshift-gitops-server-openshift-gitops.apps-crc.testing%2Fapi%2Fdex%2Fcallback&scope=user%3Ainfo&then=..%2Fauthorize%3Fclient_id%3Dsystem%253Aserviceaccount%253Aopenshift-gitops%253Aopenshift-gitops-argocd-dex-server%26redirect_uri%3Dhttps%253A%252F%252Fopenshift-gitops-server-openshift-gitops.apps-crc.testing%252Fapi%252Fdex%252Fcallback%26response_type%3Dcode%26scope%3Duser%253Ainfo%26state%3Dr4y4sfgttm33j33aj5b72u2eq","verb":"get","user":{"username":"system:anonymous","groups":["system:unauthenticated"]},"sourceIPs":["10.217.0.2"],"userAgent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36","responseStatus":{"metadata":{},"code":200},"requestReceivedTimestamp":"2025-05-23T17:41:50.613473Z","stageTimestamp":"2025-05-23T17:41:50.634129Z","annotations":{"authentication.openshift.io/decision":"allow","authentication.openshift.io/username":"user1.example","authorization.k8s.io/decision":"allow","authorization.k8s.io/reason":""}}',
    'request_received_login': '{"kind":"Event","apiVersion":"audit.k8s.io/v1","level":"Metadata","auditID":"e6f6dcdb-2bff-4c7b-8361-bf4c0d149875","stage":"RequestReceived","requestURI":"/login/developer","verb":"post","user":{"username":"system:anonymous","groups":["system:unauthenticated"]},"sourceIPs":["10.217.0.2"],"userAgent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36","requestReceivedTimestamp":"2026-08-05T15:41:37.399358Z","stageTimestamp":"2026-08-05T15:41:37.399358Z"}',
    'credential_allow_idp': '{"kind":"Event","apiVersion":"audit.k8s.io/v1","level":"Metadata","auditID":"e6f6dcdb-2bff-4c7b-8361-bf4c0d149875","stage":"ResponseComplete","requestURI":"/login/developer","verb":"post","user":{"username":"system:anonymous","groups":["system:unauthenticated"]},"sourceIPs":["10.217.0.2"],"userAgent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36","responseStatus":{"metadata":{},"code":302},"requestReceivedTimestamp":"2026-08-05T15:41:37.399358Z","stageTimestamp":"2026-08-05T15:41:38.089075Z","annotations":{"authentication.openshift.io/decision":"allow","authentication.openshift.io/username":"user2.example","authorization.k8s.io/decision":"allow","authorization.k8s.io/reason":""}}',
    'credential_deny_idp': '{"kind":"Event","apiVersion":"audit.k8s.io/v1","level":"Metadata","auditID":"d4d729cc-7414-421a-a0bb-ab87897914fb","stage":"ResponseComplete","requestURI":"/login/ldap-local","verb":"post","user":{"username":"system:anonymous","groups":["system:unauthenticated"]},"sourceIPs":["10.217.0.2"],"userAgent":"Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36","responseStatus":{"metadata":{},"code":302},"requestReceivedTimestamp":"2026-08-05T15:49:06.284711Z","stageTimestamp":"2026-08-05T15:49:06.370798Z","annotations":{"authentication.openshift.io/decision":"deny","authentication.openshift.io/username":"user1.example","authorization.k8s.io/decision":"allow","authorization.k8s.io/reason":""}}',
}
# The one with the node-name prefix, as `oc adm node-logs --role=master` writes every line.
FIXTURES["cli_allow"] = "crc " + FIXTURES["cli_allow"]


def _event(user, decision, at, uri="/login/developer", audit_id=None, stage="ResponseComplete", code=302,
           verb=None, message=None):
    """A synthetic record in the measured shape, for the cursor and correspondence tests that need
    controlled stamps. Field set copied from FIXTURES["credential_allow_idp"]."""
    path = uri.split("?", 1)[0]
    return json.dumps({
        "kind": "Event", "apiVersion": "audit.k8s.io/v1", "level": "Metadata",
        "auditID": audit_id or f"{user}-{at.timestamp()}-{uri}", "stage": stage,
        "requestURI": uri, "verb": verb or ("post" if path.startswith("/login") else "get"),
        "user": {"username": "system:anonymous", "groups": ["system:unauthenticated"]},
        "sourceIPs": ["10.217.0.2"], "userAgent": "Mozilla/5.0",
        "responseStatus": {"metadata": {}, "code": code, **({"message": message} if message else {})},
        "requestReceivedTimestamp": (at - timedelta(milliseconds=40)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "stageTimestamp": at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "annotations": {
            "authentication.openshift.io/decision": decision,
            "authentication.openshift.io/username": user,
            "authorization.k8s.io/decision": "allow", "authorization.k8s.io/reason": "",
        },
    })


class TestTheParserOnMeasuredRecords:
    def test_the_three_admitted_shapes_and_their_kinds(self):
        cred = parse_audit_line(FIXTURES["credential_allow_idp"])
        assert cred.kind == KIND_CREDENTIAL and cred.provider == "developer" and cred.decision == "allow"
        assert cred.request_path == "/login/developer" and cred.client_id is None
        plain = parse_audit_line(FIXTURES["credential_allow_plain"])
        assert plain.kind == KIND_CREDENTIAL and plain.provider is None, "the older /login path names no provider"
        cli = parse_audit_line(FIXTURES["cli_allow"])
        assert cli.kind == KIND_CLI and cli.client_id == "openshift-challenging-client" and cli.provider is None
        session = parse_audit_line(FIXTURES["session_allow_browser"])
        assert session.kind == KIND_SESSION and session.client_id == "console"

    def test_a_denied_credential_and_a_denied_cli_login_carry_what_the_record_has(self):
        deny = parse_audit_line(FIXTURES["credential_deny_idp"])
        assert deny.decision == "deny" and deny.response_code == 302 and deny.error_message is None
        cli = parse_audit_line(FIXTURES["cli_deny"])
        assert cli.decision == "deny" and cli.response_code == 401
        assert cli.error_message == "Authentication failed, attempted: basic"

    def test_everything_else_is_not_an_attempt(self):
        for label in ("authorize_deny_no_user", "consent_approve", "request_received_login", "head_probe", "token"):
            assert parse_audit_line(FIXTURES[label]) is None, label
        assert parse_audit_line("not json") is None
        assert parse_audit_line(json.dumps({"kind": "Status"})) is None

    def test_the_username_comes_from_the_annotation_never_from_user(self):
        login = parse_audit_line(FIXTURES["credential_allow_idp"])
        assert login.user_name == "user2.example", "user.username is system:anonymous on a login request"

    def test_system_accounts_are_never_rows(self):
        at = datetime.now(UTC)
        assert parse_audit_line(_event("kube:admin", "allow", at)) is None
        assert parse_audit_line(_event("system:serviceaccount:x:y", "allow", at)) is None

    def test_only_client_id_survives_the_query_string(self):
        row = audit_event_dict(parse_audit_line(FIXTURES["cli_allow"]), NODE, "x")
        text = json.dumps(row)
        assert row["client_id"] == "openshift-challenging-client"
        assert "code_challenge" not in text and "redirect_uri" not in text and "state=" not in text

    def test_the_stamp_is_microseconds_utc_in_the_shared_format(self):
        at = datetime(2024, 6, 25, 10, 46, 59, 895431, tzinfo=UTC)
        assert audit_event_dict(parse_audit_line(_event("a", "allow", at)), NODE, "x")["at"] == "2024-06-25T10:46:59.895431Z"

    def test_outcomes_map_to_the_vocabulary(self):
        at = datetime.now(UTC)
        assert audit_event_dict(parse_audit_line(_event("a", "allow", at)), NODE, "x")["outcome"] == loginlog.OUTCOME_SUCCESS
        assert audit_event_dict(parse_audit_line(_event("a", "deny", at)), NODE, "x")["outcome"] == loginlog.OUTCOME_FAILED
        assert audit_event_dict(parse_audit_line(_event("a", "error", at)), NODE, "x")["outcome"] == loginlog.OUTCOME_PROVIDER_ERROR


class TestIdentityClassification:
    def test_identity_match_is_case_insensitive_and_configured_only(self):
        index = IdentityIndex({"alice.example": ["ldap-local:dWlkPWFsaWNlLmV4YW1wbGUsb3U9UGVvcGxl"]},
                              {"developer", "ldap-local"}, ("ou=TrustedApplications",))
        assert index.match("ALICE.EXAMPLE") == "ldap-local", "the audit log records what was TYPED"
        assert index.match("nosuchperson") is None
        stale = IdentityIndex({"old.example": ["ceo_rnd_oim:x"]}, {"developer", "ldap-local"}, ())
        assert stale.match("old.example") is None, "a provider no longer on the OAuth CR is not a match"
        assert identity_match_for("x", ["developer:kubeadmin"], set()) == "developer", "empty configured = any"

    def test_a_cli_login_resolves_its_provider_from_the_identity(self):
        """Grounding note: the challenging client names no provider; the User's Identity does, so a
        CLI kubeadmin login carries provider=developer and CAN be labelled break-glass."""
        index = IdentityIndex({"kubeadmin": ["developer:kubeadmin"]}, {"developer"}, ())
        cli = parse_audit_line(_event("kubeadmin", "allow", datetime.now(UTC),
                                      uri="/oauth/authorize?client_id=openshift-challenging-client&code_challenge=abc"))
        row = audit_event_dict(cli, NODE, "x", index)
        assert row["provider"] == "developer" and row["identity_match"] == "developer" and row["kind"] == KIND_CLI

    def test_a_service_identity_is_dropped_on_every_decision(self):
        import base64
        dn = "cn=ocp-oauth-bind-serviceid,ou=TrustedApplications,dc=example,dc=com"
        suffix = base64.urlsafe_b64encode(dn.encode()).decode().rstrip("=")
        assert decode_identity_suffix(f"ldap-local:{suffix}") == dn
        assert decode_identity_suffix("developer:kubeadmin") == "kubeadmin", "an HTPasswd suffix is the bare username"
        assert ignored_identity([f"ldap-local:{suffix}"], ("ou=TrustedApplications",)) is True
        assert ignored_identity(["developer:kubeadmin"], ("ou=TrustedApplications",)) is False
        assert ignored_identity([f"ldap-local:{suffix}"], ()) is False

    def test_an_unmatched_failure_is_still_a_row(self):
        index = IdentityIndex({}, {"developer"}, ())
        row = audit_event_dict(parse_audit_line(FIXTURES["cli_deny"]), NODE, "x", index)
        assert row["identity_match"] is None and row["outcome"] == loginlog.OUTCOME_FAILED
        assert row["status_code"] == 401 and "Authentication failed" in row["detail"]


class TestLinesAndNames:
    def test_only_whole_lines_are_consumed(self):
        lines, used = complete_lines(b'{"a":1}\n{"b":2}\n{"half')
        assert lines == ['{"a":1}', '{"b":2}'] and used == 16

    def test_a_rotated_name_yields_its_close_time(self):
        assert rotated_at("audit-2021-03-09T00-12-19.834.log") == datetime(2021, 3, 9, 0, 12, 19, 834000, tzinfo=UTC)
        assert rotated_at("audit.log") is None and rotated_at("kube-apiserver.log") is None


class FakeNodeClient:
    """The calls capture_once makes, with a byte-addressable fake filesystem per node."""

    def __init__(self, nodes=None, files=None, forbidden_nodes=False, providers=("developer", "ldap-local")):
        self._nodes = nodes if nodes is not None else [NODE]
        self.files = files or {}
        self.forbidden_nodes = forbidden_nodes
        self.providers = list(providers)
        self.reads: list[tuple[str, str, int]] = []

    def fetch_nodes(self, selector):
        return None if self.forbidden_nodes else list(self._nodes)

    def fetch_oauth_providers(self):
        return list(self.providers)

    def list_node_log_files(self, node, directory):
        return sorted(self.files.get(node, {})) if node in self.files else None

    def fetch_node_log_file(self, node, path, offset=0, max_bytes=8 << 20):
        name = path.split("/", 1)[1]
        self.reads.append((node, name, offset))
        data = self.files[node].get(name)
        if data is None:
            return None
        if offset > len(data):
            # The kubelet answers 416 with `Content-Range: bytes */<size>`; the reader turns a
            # size below the cursor into rotated=True and a size equal to it into "nothing new".
            return NodeLogRead(data=b"", offset=offset, truncated=False, rotated=True)
        chunk = data[offset:offset + max_bytes]
        return NodeLogRead(data=chunk, offset=offset, truncated=offset + max_bytes < len(data), rotated=False)


@pytest.fixture()
def store(tmp_path):
    s = Store(str(tmp_path / "audit.db"))
    s.upsert_cluster(CLUSTER.name, CLUSTER.api_url, True)
    yield s
    s.close()


@pytest.fixture()
def settings(tmp_path):
    return Settings(clusters=[CLUSTER], db_path=str(tmp_path / "audit.db"),
                    login_capture_enabled=True, login_capture_source="audit-log")


@pytest.fixture()
def install(monkeypatch):
    def _install(client):
        monkeypatch.setattr(auditlog, "ClusterClient", lambda *a, **kw: client)
        return client
    return _install


def _file(*events):
    return ("\n".join(events) + "\n").encode()


class TestDispatchAndRefusals:
    def test_logincapture_dispatches_on_the_source(self, store, settings, install):
        client = install(FakeNodeClient(files={NODE: {AUDIT_FILE: _file(_event("a", "allow", datetime.now(UTC)))}}))
        assert logincapture.capture_once(store, CLUSTER, settings) == 1
        assert client.reads

    def test_forbidden_node_list_records_nothing_and_warns(self, store, settings, install, caplog):
        install(FakeNodeClient(forbidden_nodes=True))
        with caplog.at_level(logging.WARNING):
            assert capture_once(store, CLUSTER, settings) == 0
        assert "not permitted to list nodes" in caplog.text
        assert store.login_capture_status(CLUSTER.name) is None

    def test_pinned_node_names_skip_the_list(self, store, install, tmp_path):
        s = Settings(clusters=[CLUSTER], db_path=str(tmp_path / "audit.db"), login_capture_enabled=True,
                     login_capture_source="audit-log", login_capture_audit_node_names=("pinned",))
        install(FakeNodeClient(forbidden_nodes=True, files={"pinned": {AUDIT_FILE: _file(_event("a", "allow", datetime.now(UTC)))}}))
        assert capture_once(store, CLUSTER, s) == 1

    def test_no_audit_files_is_not_nobody_logged_in(self, store, settings, install, caplog):
        install(FakeNodeClient(files={NODE: {"other.log": b""}}))
        with caplog.at_level(logging.INFO):
            assert capture_once(store, CLUSTER, settings) == 0
        assert "audit profile None" in caplog.text
        assert store.login_capture_status(CLUSTER.name) is None

    def test_lost_leadership_writes_nothing(self, store, settings, install):
        class Lost:
            is_leader = False
        install(FakeNodeClient(files={NODE: {AUDIT_FILE: _file(_event("a", "allow", datetime.now(UTC)))}}))
        assert capture_once(store, CLUSTER, settings, elector=Lost()) == 0
        assert store.login_events(CLUSTER.name) == [] and store.audit_cursors(CLUSTER.name, NODE) == {}

    def test_a_measured_batch_records_every_admitted_shape_as_its_kind(self, store, settings, install):
        """The eleven measured records in one file: six admitted (two of them the same person's
        credential and session pair), five not."""
        store.replace_users(CLUSTER.name, [
            {"user_name": "user1.example", "identities": ["ldap-local:x1"], "providers": ["ldap-local"], "has_identity": True},
            {"user_name": "user2.example", "identities": ["developer:user2.example"], "providers": ["developer"], "has_identity": True},
        ], "2026-09-05T00:00:00Z")
        install(FakeNodeClient(files={NODE: {AUDIT_FILE: _file(*FIXTURES.values())}}))
        forever = Settings(clusters=[CLUSTER], db_path=settings.db_path, login_capture_enabled=True,
                           login_capture_source="audit-log", login_retention_days=0)
        assert capture_once(store, CLUSTER, forever) == 6
        rows = store.login_events(CLUSTER.name)
        kinds = sorted(r["kind"] for r in rows)
        assert kinds == ["cli", "cli", "credential", "credential", "credential", "session"]
        by_id = {r["audit_id"]: r for r in rows}
        session = next(r for r in rows if r["kind"] == "session")
        assert session["client_id"] == "console" and session["identity_match"] == "ldap-local"
        cli_deny = next(r for r in rows if r["kind"] == "cli" and r["outcome"] == "failed")
        assert cli_deny["status_code"] == 401 and cli_deny["error_message"] == "Authentication failed, attempted: basic"
        cred = next(r for r in rows if r["provider"] == "developer")
        assert cred["identity_match"] == "developer" and cred["user_name"] == "user2.example"
        assert all(r["source"] == "audit-log" and r["pod_name"] == NODE for r in rows)


class TestTheCursor:
    def test_the_cursor_stops_at_the_last_newline_and_resumes_there(self, store, settings, install):
        now = datetime.now(UTC)
        whole = _file(_event("a", "allow", now))
        client = install(FakeNodeClient(files={NODE: {AUDIT_FILE: whole + b'{"half'}}))
        assert capture_once(store, CLUSTER, settings) == 1
        assert store.audit_cursors(CLUSTER.name, NODE)[AUDIT_FILE]["byte_offset"] == len(whole)
        client.files[NODE][AUDIT_FILE] = whole + _file(_event("b", "deny", now + timedelta(seconds=5)))
        assert capture_once(store, CLUSTER, settings) == 1
        assert client.reads[-1] == (NODE, AUDIT_FILE, len(whole))

    def test_a_re_read_is_free_by_audit_id(self, store, settings, install):
        now = datetime.now(UTC)
        install(FakeNodeClient(files={NODE: {AUDIT_FILE: _file(_event("a", "allow", now, audit_id="id-1"))}}))
        assert capture_once(store, CLUSTER, settings) == 1
        store.set_audit_cursor(CLUSTER.name, NODE, AUDIT_FILE, 0, None, "x")   # a rewound cursor
        assert capture_once(store, CLUSTER, settings) == 0
        assert len(store.login_events(CLUSTER.name)) == 1

    def test_first_sight_backfills_rotated_files_oldest_first_within_retention(self, store, settings, install):
        now = datetime.now(UTC)
        old = "audit-2020-01-01T00-00-00.000.log"          # closed before the 400-day cutoff
        mid = (now - timedelta(days=30)).strftime("audit-%Y-%m-%dT%H-%M-%S.000.log")
        client = install(FakeNodeClient(files={NODE: {
            old: _file(_event("ancient", "allow", now - timedelta(days=2000))),
            mid: _file(_event("recent", "allow", now - timedelta(days=31))),
            AUDIT_FILE: _file(_event("live", "allow", now)),
        }}))
        assert capture_once(store, CLUSTER, settings) == 2
        assert [r[1] for r in client.reads] == [mid, AUDIT_FILE], "oldest readable first, audit.log last"
        cursors = store.audit_cursors(CLUSTER.name, NODE)
        assert cursors[old]["byte_offset"] == SKIPPED and cursors[mid]["complete"] is True
        assert {r["user_name"] for r in store.login_events(CLUSTER.name)} == {"recent", "live"}

    def test_rotation_hands_the_cursor_to_the_new_name(self, store, settings, install):
        """audit.log rotated and the NEW audit.log has already grown past the old cursor, so the
        size cannot tell; the head fingerprint does. The rotated file takes the cursor and is read
        from there, the new audit.log from 0, all in the cycle that first sees the rotated name."""
        now = datetime.now(UTC)
        first = _file(_event("a", "allow", now - timedelta(minutes=2)))
        client = install(FakeNodeClient(files={NODE: {AUDIT_FILE: first}}))
        assert capture_once(store, CLUSTER, settings) == 1
        cur = store.audit_cursors(CLUSTER.name, NODE)[AUDIT_FILE]
        assert cur["byte_offset"] == len(first) and cur["head"] == fingerprint(first)
        rotated = now.strftime("audit-%Y-%m-%dT%H-%M-%S.000.log")
        client.files[NODE] = {rotated: first + _file(_event("b", "allow", now - timedelta(minutes=1))),
                              AUDIT_FILE: _file(_event("c", "allow", now), _event("d", "allow", now))}
        assert len(client.files[NODE][AUDIT_FILE]) > len(first), "the size alone would not notice"
        client.reads.clear()
        assert capture_once(store, CLUSTER, settings) == 3
        assert (NODE, rotated, len(first)) in client.reads, "the rotated file resumed at the handed-over cursor"
        cursors = store.audit_cursors(CLUSTER.name, NODE)
        assert cursors[rotated]["complete"] is True and cursors[rotated]["byte_offset"] == len(client.files[NODE][rotated])
        assert cursors[AUDIT_FILE]["byte_offset"] == len(client.files[NODE][AUDIT_FILE])
        assert cursors[AUDIT_FILE]["head"] == fingerprint(client.files[NODE][AUDIT_FILE])
        assert {r["user_name"] for r in store.login_events(CLUSTER.name)} == {"a", "b", "c", "d"}

    def test_an_idle_cycle_is_not_a_rotation(self, store, settings, install):
        """Measured on the reference cluster: a Range exactly at the size returns 416 with
        `Content-Range: bytes */<size>`. Nothing new is not a rotation; the cursor stays put."""
        now = datetime.now(UTC)
        data = _file(_event("a", "allow", now))
        client = install(FakeNodeClient(files={NODE: {AUDIT_FILE: data}}))
        assert capture_once(store, CLUSTER, settings) == 1
        for _ in range(3):
            assert capture_once(store, CLUSTER, settings) == 0
        cur = store.audit_cursors(CLUSTER.name, NODE)[AUDIT_FILE]
        assert cur["byte_offset"] == len(data) and cur["head"] == fingerprint(data)
        assert all(r[2] in (0, len(data)) for r in client.reads)
        assert sum(1 for r in client.reads if r[2] == 0) == 1 + 3, "one first read, then one 1 KiB probe per cycle"

    def test_a_rotated_file_whose_head_changed_is_re_read_from_zero(self, store, settings, install, caplog):
        now = datetime.now(UTC)
        rotated = (now - timedelta(days=1)).strftime("audit-%Y-%m-%dT%H-%M-%S.000.log")
        big = _file(*[_event(f"u{i}", "allow", now - timedelta(days=2, seconds=i)) for i in range(4)])
        client = install(FakeNodeClient(files={NODE: {rotated: big + b'{"tail', AUDIT_FILE: b""}}))
        assert capture_once(store, CLUSTER, settings) == 4
        assert store.audit_cursors(CLUSTER.name, NODE)[rotated]["complete"] is False, "a partial last line keeps it open"
        client.files[NODE][rotated] = _file(_event("other", "allow", now - timedelta(days=2))) + big
        with caplog.at_level(logging.WARNING):
            assert capture_once(store, CLUSTER, settings) == 1
        assert "not the file its cursor was read from" in caplog.text
        assert {r["user_name"] for r in store.login_events(CLUSTER.name)} == {"u0", "u1", "u2", "u3", "other"}

    def test_the_byte_budget_defers_rather_than_drops(self, store, settings, install, monkeypatch):
        now = datetime.now(UTC)
        events = [_event(f"u{i}", "allow", now - timedelta(seconds=100 - i)) for i in range(20)]
        monkeypatch.setattr(auditlog, "AUDIT_READ_MAX_BYTES", len(_file(*events[:5])) + 1)
        install(FakeNodeClient(files={NODE: {AUDIT_FILE: _file(*events)}}))
        first = capture_once(store, CLUSTER, settings)
        assert 0 < first < 20
        total = first
        for _ in range(10):
            total += capture_once(store, CLUSTER, settings)
        assert total == 20

    def test_stale_cursors_are_pruned_and_last_read_advances(self, store, settings, install):
        client = install(FakeNodeClient(files={NODE: {"audit-2025-01-01T00-00-00.000.log": b"", AUDIT_FILE: b""}}))
        capture_once(store, CLUSTER, settings)
        client.files[NODE] = {AUDIT_FILE: b""}
        capture_once(store, CLUSTER, settings)
        assert "audit-2025-01-01T00-00-00.000.log" not in store.audit_cursors(CLUSTER.name, NODE)
        assert store.login_capture_status(CLUSTER.name)["last_read_at"]


class TestCorrespondenceWithThePodLog:
    def test_an_audit_credential_event_links_to_its_pod_log_twin_instead_of_doubling(self, store):
        at = datetime.now(UTC) - timedelta(minutes=5)
        store.record_login_events(CLUSTER.name, [event_dict(
            LoginAttempt("jane", loginlog.OUTCOME_BAD_PASSWORD, at, provider="ldap-local", ldap_result_code=49),
            "oauth-openshift-aaa", "x")])
        row = audit_event_dict(parse_audit_line(_event("jane", "deny", at + timedelta(milliseconds=16), audit_id="aud-1")), NODE, "x")
        assert store.record_audit_login_events(CLUSTER.name, [row], 2) == (0, 1)
        rows = store.login_events(CLUSTER.name)
        assert len(rows) == 1 and rows[0]["audit_id"] == "aud-1"
        assert rows[0]["outcome"] == loginlog.OUTCOME_BAD_PASSWORD, "the pod-log row keeps its cause"

    def test_a_success_does_not_link_to_a_failure(self, store):
        at = datetime.now(UTC) - timedelta(minutes=5)
        store.record_login_events(CLUSTER.name, [event_dict(LoginAttempt("jane", loginlog.OUTCOME_FAILED, at), "p", "x")])
        row = audit_event_dict(parse_audit_line(_event("jane", "allow", at, audit_id="aud-2")), NODE, "x")
        assert store.record_audit_login_events(CLUSTER.name, [row], 2) == (1, 0)

    def test_a_credential_login_and_its_session_reauthorisation_are_two_rows_of_two_kinds(self, store):
        """Grounding note: no coalescing. 133 session re-authorisations measured, up to 21 s after
        their credential allow; a 1 s window would have hidden 77 and left 56 as spurious logins."""
        at = datetime.now(UTC) - timedelta(minutes=5)
        a = parse_audit_line(_event("bob", "allow", at, uri="/login/ldap-local", audit_id="x1"))
        b = parse_audit_line(_event("bob", "allow", at + timedelta(milliseconds=300),
                                    uri="/oauth/authorize?client_id=system%3Aserviceaccount%3Agsd%3Adash&redirect_uri=x&state=y&code_challenge=z", audit_id="x2"))
        rows = [audit_event_dict(l, NODE, "x") for l in (a, b)]
        assert [r["kind"] for r in rows] == [KIND_CREDENTIAL, KIND_SESSION]
        assert rows[1]["client_id"] == "system:serviceaccount:gsd:dash"
        assert "redirect_uri" not in json.dumps(rows[1]) and "code_challenge" not in json.dumps(rows[1])
        assert store.record_audit_login_events(CLUSTER.name, rows, 2) == (2, 0)

    def test_two_real_attempts_on_one_path_stay_two(self, store):
        at = datetime.now(UTC) - timedelta(minutes=5)
        rows = [audit_event_dict(parse_audit_line(_event("bob", "deny", at + timedelta(seconds=i * 3), uri="/login", audit_id=f"r{i}")), NODE, "x") for i in range(2)]
        assert store.record_audit_login_events(CLUSTER.name, rows, 2) == (2, 0)


class TestMigrationTen:
    def test_an_existing_row_is_a_pod_log_credential_row(self, tmp_path):
        s = Store(str(tmp_path / "m.db"))
        s.upsert_cluster("c", "https://x", True)
        s.record_login_events("c", [event_dict(LoginAttempt("a", loginlog.OUTCOME_SUCCESS, datetime.now(UTC)), "p", "x")])
        row = s.login_events("c")[0]
        assert row["source"] == "pod-log" and row["audit_id"] is None and row["kind"] == "credential"
        assert row["identity_match"] is None and row["status_code"] is None
        s.close()

    def test_kinds_filter_and_the_default_view(self, tmp_path):
        s = Store(str(tmp_path / "k.db"))
        s.upsert_cluster("c", "https://x", True)
        at = datetime.now(UTC)
        rows = [audit_event_dict(parse_audit_line(_event("bob", "allow", at + timedelta(seconds=i), uri=u, audit_id=f"k{i}")), NODE, "x")
                for i, u in enumerate(("/login/ldap-local", "/oauth/authorize?client_id=openshift-challenging-client",
                                       "/oauth/authorize?client_id=console"))]
        s.record_audit_login_events("c", rows, 2)
        assert sorted(r["kind"] for r in s.login_events("c")) == ["cli", "credential", "session"]
        assert sorted(r["kind"] for r in s.login_events("c", kinds=("credential", "cli"))) == ["cli", "credential"]
        assert [r["kind"] for r in s.login_events("c", kinds=("session",))] == ["session"]
        s.close()
