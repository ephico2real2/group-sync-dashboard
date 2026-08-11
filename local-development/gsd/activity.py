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

The cost of buffering is that a kill loses up to one flush interval of counts. That is
acceptable *for this data specifically*: it is derived usage statistics, not the accumulated
sync and membership history, which is the part that cannot be re-fetched.

Shutdown flushes, but it is NOT lossless and this file no longer claims it is. stop() joins
the worker with a timeout and, if that expires while a store call is still in flight,
reports the fact rather than starting a second concurrent write that could not make the
first one finish. A failed flush is requeued and retried up to MAX_FLUSH_ATTEMPTS, then
dropped loudly — retrying forever would turn a storage outage into unbounded memory growth.
"""

from __future__ import annotations

import logging
import threading
from datetime import date, timedelta

from .storage import StorageBackend
from .timeutil import now_iso

log = logging.getLogger(__name__)

USER_HEADER = "x-forwarded-user"
EMAIL_HEADER = "x-forwarded-email"

# Set by the dashboard's own JS on exactly one request per user-initiated refresh.
#
# Counting every request instead measured the 30s auto-refresh: four API calls twice a
# minute is 480 an hour from a tab left open on an empty desk, and a real session showed
# 722 "requests" for roughly a dozen actual clicks. The number was arithmetically correct
# and told you nothing about whether anyone had used the dashboard.
#
# An authenticated user could of course set this header by hand and inflate their own
# figure. That is not worth defending against: these are usage statistics, not an audit
# trail, and the only thing they could forge is their own row.
INTERACTION_HEADER = "x-gsd-interaction"

# How many times a failed flush is retried before its buckets are dropped. Small on
# purpose: this covers a transient lock or a brief storage hiccup, not an outage. Retrying
# indefinitely would grow the buffer without bound while new user-days keep arriving.
MAX_FLUSH_ATTEMPTS = 3


def _day(at: str) -> str:
    """The UTC date an ISO-8601 Z timestamp falls on."""
    return at[:10]


class ActivityRecorder:
    """Accumulates per-user-per-day activity and flushes it on a background thread."""

    def __init__(
        self,
        store: StorageBackend,
        enabled: bool = True,
        flush_interval_seconds: int = 60,
        retention_days: int = 400,
        signals=None,
    ):
        self.store = store
        self.enabled = enabled
        self.flush_interval_seconds = flush_interval_seconds
        self.retention_days = retention_days
        # The process-event metrics seam (gsd/metrics.py RuntimeSignals), duck-typed and
        # optional: prune() reports what it deleted, so retention is observable without
        # this module importing the metrics module.
        self.signals = signals
        self._buckets: dict[tuple[str, str], dict] = {}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_prune_day: str | None = None
        # Latch for the missing-username DEBUG in record(): the condition is per-deployment, so it
        # is worth saying once and worth not saying on every request.
        self._warned_missing_user = False

    def record(self, user: str | None, email: str | None, at: str | None = None) -> None:
        """Note one request. In-memory only — never touches the database.

        Called from the request path, so it must stay cheap and must never raise: a failure
        to record who read a page is not a reason to fail the page.
        """
        if not self.enabled:
            return
        if not user:
            # SAID ONCE PER PROCESS, not once per request. Capture being on while the username is
            # absent is the one configuration that makes a working dashboard report zero usage
            # forever: every request takes this branch, nothing is ever recorded, and the Usage tab
            # is empty with no error anywhere. The cause is upstream — the proxy is not passing the
            # header this reads — so it is the same on every request, and logging it per request
            # would flood the very level an operator turned on to find it.
            #
            # THE CHECK-AND-SET IS UNDER THE LOCK, because request handlers are concurrent and an
            # unsynchronised flag does not make a latch. Review forced two threads to observe False
            # together and the once-per-process line appeared twice — a line that says "said once"
            # appearing twice reads as two processes or two transitions, when it was one process and
            # one unchanged condition.
            #
            # The log call is OUTSIDE the lock: it must not hold the buffer's lock for the length of
            # a handler's logging, and by then the latch is already claimed by exactly one thread.
            with self._lock:
                first = not self._warned_missing_user
                self._warned_missing_user = True
            if first:
                log.debug("dashboard-usage recording is on but a request carried no username "
                          "header, so nothing was recorded for it and nothing will be until the "
                          "proxy supplies one — check the oauth-proxy sidecar is passing user "
                          "headers. Said once per process; the condition is per-deployment, not "
                          "per-request")
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

        A failed write is RETRIED, up to MAX_FLUSH_ATTEMPTS. The swap means the failed
        buckets are no longer in `_buckets`, so before this they were simply gone — one
        moment of lock contention past busy_timeout silently destroyed data that had
        already been captured. They are now merged back in.

        Bounded, because the obvious version is worse than the bug: retrying forever
        against a permanently broken store grows the buffer without limit as new user-days
        keep arriving, and turns a storage outage into an OOM. After the bound the buckets
        are dropped, loudly.
        """
        with self._lock:
            if not self._buckets:
                return 0
            pending, self._buckets = list(self._buckets.values()), {}
        try:
            return self.store.record_user_activity(pending)
        except Exception as exc:  # noqa: BLE001 - usage stats must not take the process down
            # THE CAUSE, which used to be swallowed entirely. `_requeue` reports how many buckets
            # were requeued and never why the write failed, so a Usage tab frozen at yesterday's
            # counts had no explanation anywhere in the process — the one question an operator has.
            #
            # Type and message, not log.exception: this is an expected-and-handled path, and a
            # stack trace on every transient SQLite lock would bury the line that matters. The
            # traceback is not the interesting part; "database is locked" versus "no such column"
            # is, and those two want opposite responses.
            log.warning("dashboard-usage flush failed against the store — %s: %s",
                        type(exc).__name__, exc)
            self._requeue(pending)
            return 0

    def _requeue(self, pending: list[dict]) -> None:
        """Merge failed buckets back, dropping any that have exhausted their retries.

        Merged rather than reinserted: the same user-day may have accumulated more
        interactions while the failed write was in flight, and overwriting would discard
        them. Same rule as the SQL upsert — counts add, the window widens.
        """
        kept, dropped = 0, 0
        with self._lock:
            for bucket in pending:
                bucket["attempts"] = bucket.get("attempts", 0) + 1
                if bucket["attempts"] >= MAX_FLUSH_ATTEMPTS:
                    dropped += 1
                    continue
                key = (bucket["user_name"], bucket["day"])
                current = self._buckets.get(key)
                if current is None:
                    self._buckets[key] = bucket
                else:
                    current["request_count"] += bucket["request_count"]
                    current["first_seen_at"] = min(
                        current["first_seen_at"], bucket["first_seen_at"]
                    )
                    current["last_seen_at"] = max(
                        current["last_seen_at"], bucket["last_seen_at"]
                    )
                    current["email"] = current.get("email") or bucket.get("email")
                    current["attempts"] = bucket["attempts"]
                kept += 1
        if dropped:
            log.error(
                "dropping %d user-activity bucket(s) after %d failed flushes; that usage "
                "is lost. %d bucket(s) still queued for retry",
                dropped, MAX_FLUSH_ATTEMPTS, kept,
            )
        else:
            # DEBUG, because flush() now logs the CAUSE at WARNING and this only carries the count.
            # Two WARNINGs for one failure read as two failures — measured across an exhausted
            # retry: three cause lines, two of these, and one ERROR, for a single unwritable store.
            # The cause is the line worth waking up for; the bookkeeping belongs a level down.
            log.debug("flush failed; %d user-activity bucket(s) requeued for retry", kept)

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
            if self.signals is not None:
                # Same count as the log line, from the same call — the two cannot disagree.
                self.signals.note_retention("dashboard_user_activity", removed)
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
        """Stop the loop and flush what is left.

        Deliberately NOT promising that a graceful shutdown loses nothing — it did claim
        that, and it was not true. If the worker is still inside a store call when the join
        times out, a final flush here would run a SECOND concurrent write and still not
        make the first one finish. So the timeout is reported instead of papered over.

        The join is bounded rather than indefinite because these are derived usage
        statistics: a stuck filesystem call must not hold pod termination open past the
        Kubernetes grace period for data of this value.
        """
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            thread.join(timeout=5)
            if thread.is_alive():
                log.warning(
                    "activity flush thread still running at shutdown; not starting another "
                    "write. Up to one flush interval of usage counts may be unpersisted"
                )
                return
        self.flush()

    def _loop(self) -> None:
        while not self._stop.wait(self.flush_interval_seconds):
            try:
                self.flush()
                self.prune()
            except Exception:  # noqa: BLE001 - the flush thread must never die silently
                log.exception("unhandled error in the activity flush loop")
