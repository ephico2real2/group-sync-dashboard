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


class Chunks(httpx.SyncByteStream):
    def __init__(self, values):
        self.values = values
        self.yielded = 0

    def __iter__(self):
        for value in self.values:
            self.yielded += 1
            yield value


def _client_for(monkeypatch, stream):
    cluster = ClusterConfig("c", "https://api.example", token_env="X")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, stream=stream, request=request))
    client = ClusterClient(cluster)
    monkeypatch.setattr(
        client, "_client",
        lambda: httpx.Client(transport=transport, base_url="https://api.example"))
    return client


def test_the_byte_cap_is_measured_in_bytes_not_line_characters(monkeypatch):
    """A multi-byte log must not blow through the cap: max_bytes is a MEMORY bound, and a
    character count taken after the line was already assembled is neither."""
    stream = Chunks([("€" * 10 + "\n").encode(), b"x\n"])       # 31 bytes, 11 characters
    client = _client_for(monkeypatch, stream)
    got = client.fetch_pod_log("ns", "pod", max_bytes=20)
    assert got is not None
    assert sum(len(line.encode()) for line in got) <= 20, got


def test_a_cap_hit_keeps_the_oldest_lines_and_stops_the_transfer(monkeypatch, caplog):
    """The watermark machinery REQUIRES oldest-first retention: the cursor only advances through
    returned lines, so the deferred newest fall inside the next window and are late, not lost.
    Keeping the newest would advance the cursor past the displaced middle and silently drop it
    forever — and reading on after the cap pays for bytes that are then thrown away."""
    stream = Chunks([b"oldest-1\n", b"oldest-2\n", b"newest-3\n", b"newest-4\n"])
    client = _client_for(monkeypatch, stream)
    with caplog.at_level(logging.INFO):
        got = client.fetch_pod_log("ns", "pod", max_bytes=20)
    assert got == ["oldest-1", "oldest-2"], got
    assert stream.yielded < 4, "the read continued past the cap"
    assert "OLDEST lines of this window are kept" in caplog.text


def test_the_line_the_cap_cuts_in_half_is_dropped_not_parsed(monkeypatch):
    """A truncated line can mis-parse — a bind diagnostic losing its `data` sub-code reads as a
    plain wrong password — so the cut line waits for the next cycle's overlap instead."""
    stream = Chunks([b"whole-line\n" + b"cut-here-" * 10])
    client = _client_for(monkeypatch, stream)
    got = client.fetch_pod_log("ns", "pod", max_bytes=30)
    assert got == ["whole-line"], got


def test_a_read_that_outlives_its_budget_is_cut_like_a_cap_hit(monkeypatch, caplog):
    """The httpx timeout caps the gap BETWEEN chunks, not the transfer, so a stream dripping just
    under it can run for minutes — measured: a timeout=1.0 client consumed a 4.2s dribble without
    raising. The capture loop stamps the clock behind its leading-edge guard AFTER this returns, so
    past ~58.5s of read latency that guard permanently drops logins nothing ever recorded. A read the
    budget interrupts must land on the cap-hit path: oldest lines kept, the tail deferred, said out
    loud.

    THE PAYLOAD HAS TO EXCEED chunk_size, not merely arrive in several pieces. `iter_bytes` re-chunks
    whatever the transport yields — two small source chunks are coalesced into one, the loop body runs
    once, and a budget that is only checked per iteration is never reached. A first draft of this test
    asserted against 33 bytes in two pieces and failed against working code for that reason.
    """
    import types

    from gsd import kube

    # Fixed-width lines so the boundary arithmetic is inspectable: 64 KiB of them is 1560 whole
    # lines plus a fragment, and one iteration of the loop consumes exactly that.
    lines = [f"2026-08-08T00:00:00.{i:09d}Z line-{i:05d}" for i in range(1600)]
    payload = ("\n".join(lines) + "\n").encode()
    assert len(payload) > 64 * 1024, "the payload must span more than one chunk_size"

    # One tick for the start stamp, then one per iteration; the second iteration lands past the
    # budget. The last value repeats so an extra clock read cannot exhaust the fake.
    ticks = [0.0, 5.0, kube.LOG_READ_BUDGET_SECONDS + 30.0]
    monkeypatch.setattr(
        kube, "time",
        types.SimpleNamespace(monotonic=lambda: ticks.pop(0) if len(ticks) > 1 else ticks[0]))

    stream = Chunks([payload])
    client = _client_for(monkeypatch, stream)
    with caplog.at_level(logging.INFO):
        got = client.fetch_pod_log("ns", "pod")

    assert got is not None
    assert 0 < len(got) < len(lines), f"kept {len(got)} of {len(lines)}"
    assert got == lines[:len(got)], "the OLDEST lines must be the ones kept"
    assert lines[-1] not in got, "the tail should be deferred to the next cycle, not returned"
    assert "budget" in caplog.text, caplog.text
    assert "byte cap" not in caplog.text, "a budget stop must not report itself as a cap hit"


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
