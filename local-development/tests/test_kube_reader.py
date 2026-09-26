"""The cluster reader's pure seams: the log truncation contract and the OAuth-filter DN parse.

These are the first direct tests of kube.py's reader helpers. The capture-loop suite deliberately
fakes the client, which is right for loop semantics and useless for the contracts the fakes
assume — the byte cap's direction was documented backwards for a full release because nothing
executed the real path. HTTP is mocked at the transport, so no cluster is needed.
"""
from __future__ import annotations

import logging

import httpx
import pytest

from gsd.config import ClusterConfig
from gsd.kube import ClusterClient, _access_group_from_ldap_url


def test_group_view_reads_exactly_the_silence_annotation():
    from gsd.kube import CLIFF_SILENCE_ANNOTATION, _group_view
    obj = {"metadata": {"name": "g", "annotations": {
        CLIFF_SILENCE_ANNOTATION: "until=2026-10-01", "somebody.else/note": "ignored"}},
        "users": ["a"]}
    view = _group_view(obj)
    assert view.cliff_silence == "until=2026-10-01"
    assert _group_view({"metadata": {"name": "g"}, "users": None}).cliff_silence is None
    assert CLIFF_SILENCE_ANNOTATION == "groupsync-dashboard.io/silence-group-count-cliff"


class TestNodeLogRangeReads:
    """fetch_node_log_file against the kubelet's measured answers. On the reference cluster
    (2026-09-06, audit.log of 27,804,760 bytes) `Range: bytes=<size>-` and `Range: bytes=<size+100>-`
    BOTH returned `416` with `Content-Range: bytes */27804760`, and HEAD returned 405. So a 416
    is not rotation by itself: the size in Content-Range decides."""

    @staticmethod
    def _client(monkeypatch, handler):
        cluster = ClusterConfig("c", "https://api.example", token_env="X")
        client = ClusterClient(cluster)
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(
            client, "_client",
            lambda: httpx.Client(transport=transport, base_url="https://api.example"))
        return client

    def test_a_range_exactly_at_the_size_is_nothing_new_not_rotation(self, monkeypatch):
        seen = []
        def handler(request):
            seen.append(request.headers.get("range"))
            return httpx.Response(416, headers={"Content-Range": "bytes */27804760"},
                                  content=b"invalid range: failed to overlap\n", request=request)
        got = self._client(monkeypatch, handler).fetch_node_log_file("crc", "oauth-server/audit.log", offset=27804760)
        assert seen == ["bytes=27804760-"]
        assert got is not None and got.data == b"" and got.rotated is False and got.truncated is False

    def test_a_size_below_the_cursor_is_rotation(self, monkeypatch):
        handler = lambda request: httpx.Response(416, headers={"Content-Range": "bytes */1000"}, request=request)
        got = self._client(monkeypatch, handler).fetch_node_log_file("crc", "oauth-server/audit.log", offset=27804760)
        assert got is not None and got.rotated is True and got.data == b""

    def test_a_416_without_a_size_falls_back_to_one_unranged_read(self, monkeypatch):
        """A proxy that strips Content-Range: the reader asks once more without Range and settles
        it the 200 way — skipping `offset` bytes, or calling a shorter body rotated."""
        body = b"line-one\nline-two\n"
        calls = []
        def handler(request):
            calls.append(request.headers.get("range"))
            if request.headers.get("range"):
                return httpx.Response(416, request=request)
            return httpx.Response(200, content=body, request=request)
        client = self._client(monkeypatch, handler)
        got = client.fetch_node_log_file("crc", "oauth-server/audit.log", offset=9)
        assert calls == ["bytes=9-", None]
        assert got is not None and got.data == b"line-two\n" and got.rotated is False
        calls.clear()
        got = client.fetch_node_log_file("crc", "oauth-server/audit.log", offset=len(body) + 5)
        assert got is not None and got.rotated is True

    def test_a_206_returns_the_tail_and_a_zero_offset_sends_no_range(self, monkeypatch):
        seen = []
        def handler(request):
            seen.append(request.headers.get("range"))
            return httpx.Response(206, headers={"Content-Range": "bytes 9-17/18"}, content=b"line-two\n", request=request)
        got = self._client(monkeypatch, handler).fetch_node_log_file("crc", "oauth-server/audit.log", offset=9)
        assert got.data == b"line-two\n" and got.offset == 9 and got.rotated is False
        handler0 = lambda request: httpx.Response(200, content=b"x\n", request=request) if seen.append(request.headers.get("range")) is None else None
        self._client(monkeypatch, handler0).fetch_node_log_file("crc", "oauth-server/audit.log", offset=0)
        assert seen[-1] is None

    def test_both_node_log_calls_accept_anything(self, monkeypatch):
        """Measured on the reference cluster: the API server's node proxy answers 406 to an explicit
        Accept of application/json, text/html or text/plain, and 200 only to */* (or none). The
        client's default is application/json, so the first deploy of the audit source read nothing."""
        seen = []
        def handler(request):
            seen.append(request.headers.get("accept"))
            if request.url.path.endswith("/"):
                return httpx.Response(200, content=b'<a href="audit.log">audit.log</a>', request=request)
            return httpx.Response(200, content=b"x\n", request=request)
        client = self._client(monkeypatch, handler)
        # The real _client() carries `Accept: application/json` as a DEFAULT header; the request
        # header must REPLACE it (httpx merges by popping the key), not join it as a second value.
        cluster = ClusterConfig("c", "https://api.example", token_env="X")
        monkeypatch.setenv("X", "a-token")
        real_default = ClusterClient(cluster)._client().headers.get("accept")
        assert real_default == "application/json", real_default
        transport = httpx.MockTransport(handler)
        monkeypatch.setattr(client, "_client", lambda: httpx.Client(
            transport=transport, base_url="https://api.example", headers={"Accept": real_default}))
        assert client.list_node_log_files("crc", "oauth-server") == ["audit.log"]
        client.fetch_node_log_file("crc", "oauth-server/audit.log", offset=0)
        client.fetch_node_log_file("crc", "oauth-server/audit.log", offset=1)
        assert seen == ["*/*", "*/*", "*/*"], seen

    def test_oauth_cr_with_no_providers_is_an_empty_list_not_none(self, monkeypatch):
        """Cursor pass 2: the CR read successfully and listing no provider must reach
        _configured_providers as an EMPTY SET (nothing is current), not None (unknown: any)."""
        import json
        for spec in ({"identityProviders": []}, {}):
            body = json.dumps({"kind": "OAuth", "spec": spec}).encode()
            handler = lambda request, body=body: httpx.Response(200, content=body, request=request)
            assert self._client(monkeypatch, handler).fetch_oauth_providers() == []
        handler403 = lambda request: httpx.Response(403, content=b"{}", request=request)
        assert self._client(monkeypatch, handler403).fetch_oauth_providers() is None

    def test_content_range_total_parses_both_forms(self):
        from gsd.kube import _content_range_total
        assert _content_range_total("bytes */27804760") == 27804760
        assert _content_range_total("bytes 0-1023/27804760") == 27804760
        assert _content_range_total(None) is None and _content_range_total("bytes */*") is None
