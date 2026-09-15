"""The node-log-proxy machinery: HTML listing, Range 206, 416 + Content-Range, rotation, and
the malformed-416 unranged retry (DESIGN §7)."""

from __future__ import annotations

import pytest

from gsd.kube import ClusterClient

from mock_app.auditlog import AuditServer, Range, parse_range
from mock_app.fixture import Fixture
from mock_app.server import MockClusterServer


# ── AuditServer unit behaviour ─────────────────────────────────────────────────────────────
def _audit_fixture(**audit_overrides):
    data = {
        "meta": {"token": "t"},
        "auditLog": {
            "node": "master-0", "dir": "oauth-server",
            "files": [
                {"name": "audit.log", "lines": [
                    {"kind": "credential", "decision": "allow", "user": "jane.smith",
                     "at": "2026-09-03T10:15:27.234567Z", "code": 302},
                ]},
            ],
            **audit_overrides,
        },
    }
    return Fixture.from_dict(data)


def test_listing_orders_rotated_before_live():
    fx = Fixture.from_dict({
        "meta": {"token": "t"},
        "auditLog": {"node": "master-0", "dir": "oauth-server", "files": [
            {"name": "audit.log", "lines": []},
            {"name": "audit-2026-09-02T00-00-00.000.log", "lines": []},
            {"name": "audit-2026-09-01T00-00-00.000.log", "lines": []},
        ]},
    })
    server = AuditServer(fx.audit)
    assert server.files_in_order() == [
        "audit-2026-09-01T00-00-00.000.log",
        "audit-2026-09-02T00-00-00.000.log",
        "audit.log",
    ]
    html = server.listing_html().decode()
    assert '<a href="audit.log">audit.log</a>' in html


def test_expand_line_is_parseable_kubernetes_audit():
    from gsd.auditlog import parse_audit_line

    fx = _audit_fixture()
    server = AuditServer(fx.audit)
    line = server.expand_line(fx.audit.files[0].lines[0])
    parsed = parse_audit_line(line)
    assert parsed is not None
    assert parsed.user_name == "jane.smith"
    assert parsed.decision == "allow"
    assert parsed.kind == "credential"


def test_range_206_and_416():
    fx = _audit_fixture()
    server = AuditServer(fx.audit)
    total = server.size("audit.log")

    partial = server.read("audit.log", Range(start=5, end=None))
    assert partial.status == 206
    assert partial.headers["Content-Range"] == f"bytes 5-{total - 1}/{total}"
    assert partial.body == server.read("audit.log", None).body[5:]

    at_eof = server.read("audit.log", Range(start=total, end=None))
    assert at_eof.status == 416
    assert at_eof.headers["Content-Range"] == f"bytes */{total}"


def test_malformed_416_has_no_content_range():
    fx = _audit_fixture(malformed416=True)
    server = AuditServer(fx.audit)
    total = server.size("audit.log")
    resp = server.read("audit.log", Range(start=total, end=None))
    assert resp.status == 416
    assert "Content-Range" not in resp.headers


def test_parse_range():
    assert parse_range("bytes=10-") == Range(10, None)
    assert parse_range("bytes=10-99") == Range(10, 99)
    assert parse_range(None) is None
    assert parse_range("garbage") is None


# ── client-level rotation + malformed-416 retry over real TLS ─────────────────────────────
def test_rotation_detected_when_size_below_offset(mock_cluster):
    client = ClusterClient(mock_cluster.cluster_config(), timeout=5.0)
    full = client.fetch_node_log_file("master-0", "oauth-server/audit.log")
    beyond = client.fetch_node_log_file(
        "master-0", "oauth-server/audit.log", offset=len(full.data) + 100
    )
    assert beyond is not None
    assert beyond.rotated is True


def test_malformed_416_triggers_unranged_retry(tmp_path):
    fx = Fixture.from_dict({
        "meta": {"token": "tok-416"},
        "auditLog": {"node": "master-0", "dir": "oauth-server", "malformed416": True, "files": [
            {"name": "audit.log", "lines": [
                {"kind": "credential", "decision": "allow", "user": "jane.smith",
                 "at": "2026-09-03T10:15:27.234567Z", "code": 302},
            ]},
        ]},
    })
    server = MockClusterServer(fx, host="127.0.0.1", port=0, tls=True)
    server.start()
    ca = tmp_path / "ca.crt"
    ca.write_bytes(server.ca_pem)
    try:
        import os

        os.environ["GSD_MOCK_416_TOKEN"] = "tok-416"
        from gsd.config import ClusterConfig
        cfg = ClusterConfig(name="m416", api_url=server.base_url,
                            token_env="GSD_MOCK_416_TOKEN", ca_bundle_file=str(ca))
        client = ClusterClient(cfg, timeout=5.0)
        full = client.fetch_node_log_file("master-0", "oauth-server/audit.log")
        total = len(full.data)
        # A ranged read at EOF gets a 416 with NO Content-Range → client retries UNRANGED and
        # gets 200; skip=offset drains the whole body → rotated (nothing new), data empty.
        result = client.fetch_node_log_file("master-0", "oauth-server/audit.log", offset=total)
        assert result is not None
        assert result.data == b""
    finally:
        server.stop()


# ── the tolerated-403 and CRD-absent branches via the variant fixtures ────────────────────
def test_forbidden_fixture_tolerated(mock_factory):
    handle = mock_factory("forbidden.yaml")
    client = ClusterClient(handle.cluster_config(), timeout=5.0)
    # The core poll still succeeds (Groups readable)…
    _, groups = client.fetch()
    assert [g.name for g in groups] == ["admins"]
    # …and every optional read degrades to None rather than failing.
    assert client.fetch_users() is None
    assert client.fetch_identities() is None
    assert client.fetch_namespaces(["team"]) is None
    assert client.fetch_nodes("node-role.kubernetes.io/master=") is None
    assert client.fetch_oauth_providers() is None
    assert client.fetch_oauth_pods("openshift-authentication") is None


def test_crd_absent_fixture(mock_factory):
    handle = mock_factory("crd-absent.yaml")
    client = ClusterClient(handle.cluster_config(), timeout=5.0)
    groupsyncs, groups = client.fetch()
    assert groupsyncs is None                    # CRD absent → None, not a failure
    assert {g.name for g in groups} == {"hand-made-admins", "hand-made-viewers"}
    assert client.fetch_operator_configs() is None
    assert client.fetch_access_group_dn() is None


# ── paging via meta.pageSize drives kube.py's real continue loop ──────────────────────────
def test_paging_follows_continue_token(mock_factory):
    handle = mock_factory("paging.yaml")
    client = ClusterClient(handle.cluster_config(), timeout=5.0)
    _, groups = client.fetch()
    assert {g.name for g in groups} == {"team-a", "team-b", "team-c", "team-d", "team-e"}
    nodes = client.fetch_nodes("node-role.kubernetes.io/master=")
    assert nodes == ["master-0", "master-1", "master-2"]     # labelSelector carried on every page
