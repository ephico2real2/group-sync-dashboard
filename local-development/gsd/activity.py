"""Who used the dashboard, buffered in memory and flushed to the store on an interval.

IDENTITY AND WHETHER IT CAN BE TRUSTED
--------------------------------------
The app never authenticates anyone. When ``oauthProxy.enabled=true`` the OpenShift
oauth-proxy sidecar terminates the session and forwards the identity as request headers;
``-pass-basic-auth`` and ``-pass-user-headers`` both default to true in the shipped image,
so ``X-Forwarded-User`` and ``X-Forwarded-Email`` arrive on every authenticated request
without the chart having to ask for them.

That header is only worth believing because of a second thing the chart does: with the
proxy enabled the Deployment overrides the container command to bind 127.0.0.1, and the
Service targets the proxy's port rather than the app's. The app is not reachable on the pod
network, so nothing inside the cluster can address it directly and assert whatever username
it likes. With the proxy DISABLED the image's own ``--host 0.0.0.0`` applies and there is no
authentication at all — the header would then be a free-text field, so recording it would
manufacture an audit trail rather than keep one. The chart therefore reports its own
``oauthProxy.enabled`` into the config as ``oauthProxyEnabled``, and recording is off
whenever that is false regardless of what ``userActivity.enabled`` says. The app cannot
detect the sidecar for itself, and guessing from the presence of the header is exactly the
inference an attacker controls.

WHY BUFFERED RATHER THAN WRITTEN PER REQUEST
--------------------------------------------
A write per request would put every API call behind the SQLite writer lock, contending with
the poller's bulk write — measured at 0.92s for a 50k-row refresh. That is precisely the
latency the WAL and busy_timeout work exists to prevent, and it would be self-inflicted. It
is also heavy: one page view is several API calls, so the write amplification is ~10x for
data whose whole purpose is to be read in aggregate.

The cost of buffering is that an ungraceful kill loses up to one flush interval of counts.
That is acceptable *for this data specifically*: it is derived usage statistics, not the
accumulated sync and membership history, which is the part that cannot be re-fetched.
Shutdown flushes, so only a crash loses anything.
"""

from __future__ import annotations

import logging
import threading
from datetime import date, timedelta

from .store import Store, now_iso

log = logging.getLogger(__name__)

USER_HEADER = "x-forwarded-user"
EMAIL_HEADER = "x-forwarded-email"


def _day(at: str) -> str:
    """The UTC date an ISO-8601 Z timestamp falls on."""
    return at[:10]


class ActivityRecorder:
    """Accumulates per-user-per-day activity and flushes it on a background thread."""

    def __init__(
        self,
        store: Store,
        enabled: bool = True,
        flush_interval_seconds: int = 60,
        retention_days: int = 400,
    ):
        self.store = store
        self.enabled = enabled
        self.flush_interval_seconds = flush_interval_seconds
        self.retention_days = retention_days
        self._buckets: dict[tuple[str, str], dict] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_prune_day: str | None = None

    def record(self, user: str | None, email: str | None, at: str | None = None) -> None:
        """Note one request. In-memory only — never touches the database.

        Called from the request path, so it must stay cheap and must never raise: a failure
        to record who read a page is not a reason to fail the page.
        """
        if not self.enabled or not user:
            return
        at = at or now_iso()
        key = (user, _day(at))
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                self._buckets[key] = {
                    "user_name": user,
                    "day": key[1],
                    "email": email,
                    "first_seen_at": at,
                    "last_seen_at": at,
                    "request_count": 1,
                }
                return
            bucket["request_count"] += 1
            # Not simply "the latest wins": requests are recorded from several worker
            # threads and are not guaranteed to arrive in timestamp order.
            if at < bucket["first_seen_at"]:
                bucket["first_seen_at"] = at
            if at > bucket["last_seen_at"]:
                bucket["last_seen_at"] = at
            if email:
                bucket["email"] = email

    def flush(self) -> int:
        """Write everything buffered. Returns the number of user-days written.

        The buffer is swapped out under the lock and written outside it, so a slow write
        never blocks the request threads that are still recording.
        """
        with self._lock:
            if not self._buckets:
                return 0
            pending, self._buckets = list(self._buckets.values()), {}
        try:
            return self.store.record_user_activity(pending)
        except Exception:  # noqa: BLE001 - usage stats must not take the process down
            log.exception("could not flush %d user-activity bucket(s); they are lost", len(pending))
            return 0

    def prune(self, today: str | None = None) -> int:
        """Drop activity older than the retention window. At most once per day.

        Aggregation already bounds this table, so retention is a backstop against a
        long-lived deployment rather than the growth control it has to be for a request
        log. retention_days <= 0 disables it.
        """
        if self.retention_days <= 0:
            return 0
        today = today or _day(now_iso())
        if self._last_prune_day == today:
            return 0
        self._last_prune_day = today
        before = (date.fromisoformat(today) - timedelta(days=self.retention_days)).isoformat()
        removed = self.store.prune_user_activity(before)
        if removed:
            log.info("pruned %d dashboard-activity row(s) older than %s", removed, before)
        return removed

    # -- lifecycle -------------------------------------------------------------------

    def start(self) -> None:
        if not self.enabled or self._thread is not None:
            return
        self._thread = threading.Thread(
            target=self._loop, name="activity-flush", daemon=True
        )
        self._thread.start()

    def stop(self) -> None:
        """Stop the loop and flush what is left, so a graceful shutdown loses nothing."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
            self._thread = None
        self.flush()

    def _loop(self) -> None:
        while not self._stop.wait(self.flush_interval_seconds):
            try:
                self.flush()
                self.prune()
            except Exception:  # noqa: BLE001 - the flush thread must never die silently
                log.exception("unhandled error in the activity flush loop")
