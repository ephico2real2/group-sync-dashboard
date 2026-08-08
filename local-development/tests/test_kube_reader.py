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
