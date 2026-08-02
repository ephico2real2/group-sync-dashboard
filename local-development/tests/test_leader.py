"""Leader election, and specifically the timestamp format the apiserver will accept.

This exists because of a live failure: every Lease create was rejected 400, the pod never
took leadership, and because the poller is gated on leadership the dashboard silently
stopped polling. Nothing surfaced it — the create path returned a bare False — so the only
symptom was data that quietly stopped updating.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime

import httpx
import pytest

from gsd.leader import LeaderElector


@pytest.fixture()
def elector():
    return LeaderElector(name="gsd", namespace="ns", identity="pod-a", lease_seconds=30)


# Go layout "2006-01-02T15:04:05.000000Z07:00" — `.000000` means EXACTLY six digits, not
# "up to six". This is the whole bug in one regex.
MICROTIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{6}Z$")


class TestMicroTimeFormat:
    def test_now_has_exactly_six_fractional_digits(self, elector):
        """Milliseconds are rejected. The apiserver said, verbatim:

            parsing time "...T05:04:05.491Z" as "2006-01-02T15:04:05.000000Z07:00":
            cannot parse "Z" as ".000000"
        """
        assert MICROTIME.match(elector._now()), elector._now()

    def test_lease_timestamps_are_microtime(self, elector):
        spec = elector._body(0)["spec"]
        assert MICROTIME.match(spec["acquireTime"])
        assert MICROTIME.match(spec["renewTime"])

    def test_the_timestamp_still_round_trips(self, elector):
        """Renewal parses renewTime back with fromisoformat to decide expiry, so the format
        has to satisfy the apiserver AND stay readable to us."""
        parsed = datetime.fromisoformat(elector._now().replace("Z", "+00:00"))
        assert abs((datetime.now(UTC) - parsed).total_seconds()) < 5


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://k8s")


class TestAcquire:
    def test_creates_the_lease_when_absent(self, elector):
        seen = {}

        def handler(request):
            if request.method == "GET":
                return httpx.Response(404)
            seen["body"] = request.read()
            return httpx.Response(201, json={})

        with _client(handler) as c:
            assert elector._try_acquire(c) is True
        assert b"holderIdentity" in seen["body"]

    def test_a_rejected_create_is_logged_not_swallowed(self, elector, caplog):
        """The regression that hid the outage: a 400 returned False with no log line, so a
        permanently broken election looked exactly like a healthy standby."""
        def handler(request):
            if request.method == "GET":
                return httpx.Response(404)
            return httpx.Response(400, text='{"message":"cannot be handled as a Lease"}')

        with caplog.at_level("ERROR"), _client(handler) as c:
            assert elector._try_acquire(c) is False
        assert "could not create lease" in caplog.text
        assert "cannot be handled as a Lease" in caplog.text, "the apiserver's reason is lost"

    def test_losing_the_create_race_is_not_an_error(self, elector, caplog):
        """409 means another replica won the same instant. That is the mechanism working."""
        def handler(request):
            if request.method == "GET":
                return httpx.Response(404)
            return httpx.Response(409, text="conflict")

        with caplog.at_level("ERROR"), _client(handler) as c:
            assert elector._try_acquire(c) is False
        assert "could not create lease" not in caplog.text

    def test_renews_its_own_lease(self, elector):
        lease = {
            "metadata": {"resourceVersion": "7"},
            "spec": {"holderIdentity": "pod-a", "leaseTransitions": 2,
                     "acquireTime": "2026-08-02T05:00:00.000000Z",
                     "renewTime": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"},
        }

        def handler(request):
            if request.method == "GET":
                return httpx.Response(200, json=lease)
            return httpx.Response(200, json={})

        with _client(handler) as c:
            assert elector._try_acquire(c) is True

    def test_does_not_steal_a_live_lease_from_another_holder(self, elector):
        lease = {
            "metadata": {"resourceVersion": "7"},
            "spec": {"holderIdentity": "pod-b", "leaseTransitions": 1,
                     "renewTime": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"},
        }
        with _client(lambda r: httpx.Response(200, json=lease)) as c:
            assert elector._try_acquire(c) is False

    def test_takes_over_an_expired_lease(self, elector):
        stale = datetime.fromtimestamp(datetime.now(UTC).timestamp() - 600, UTC)
        lease = {
            "metadata": {"resourceVersion": "7"},
            "spec": {"holderIdentity": "pod-b", "leaseTransitions": 1,
                     "renewTime": stale.strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"},
        }

        def handler(request):
            if request.method == "GET":
                return httpx.Response(200, json=lease)
            return httpx.Response(200, json={})

        with _client(handler) as c:
            assert elector._try_acquire(c) is True
