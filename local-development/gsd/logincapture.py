"""Read the oauth-server's logs and record who logged in.

Its own module, not part of poller.py, because it is a separable concern with a separable failure mode:
capture can be off, forbidden, or broken while group polling is perfectly healthy, and nothing here may
take the poll down with it.

WHAT MAKES THIS WORK AT ALL. The lines naming a person exist only at `spec.logLevel: Debug` on
`authentications.operator.openshift.io/cluster` — the authentication OPERATOR CR, not the OAuth CR. At
the default verbosity they are not written, so with capture on and Debug off this reads real logs and
finds nothing, which is correct rather than broken. See docs/LOGIN_CAPTURE_QUICKCHECK.md.

AND WHAT IT CANNOT DO. Pod logs live as long as the pod. Every oauth roll — a cluster upgrade, a node
drain, a toggle of that very setting — starts the window again, and nothing before capture was enabled
was ever written down anywhere. So this accumulates a durable record GOING FORWARD and cannot
reconstruct the past. `login_capture_status.started_at` exists so the UI can say when watching began
rather than letting an empty table read as "nobody logged in".
"""

from __future__ import annotations

import logging

from .config import ClusterConfig, Settings
from .kube import ClusterClient, ClusterError
from .loginlog import LoginAttempt, parse
from .storage import StorageBackend
from .timeutil import now_iso

log = logging.getLogger(__name__)

# How far back to read when there is NO watermark for a pod — a first sight, or the first cycle after a
# restart. Deliberately modest: the alternative is reading a pod's entire history on every fresh start,
# which on a long-lived pod at Debug is a large read for lines that are almost all already recorded.
# One hour covers a restart and a rollout; anything older than that on a first sight is accepted as
# lost, which is the same bargain §1.8 of the design already makes.
FIRST_SIGHT_SECONDS = 3600

# Re-read this far behind the watermark on every cycle. An attempt is SEVERAL lines and they can
# straddle two reads: the success line may land in the next window from the failure lines that precede
# it. Re-reading the overlap means the whole attempt is present in one parse, and the dedup key makes
# the repeats free. Cheap insurance — it is one extra minute of lines per pod per cycle.
OVERLAP_SECONDS = 60

# Do not advance the watermark to the newest line seen; hold it back by this much. The newest lines of
# a live log are the ones most likely to be mid-attempt — the failure lines written, the success line
# not yet. Settling behind the tip means an attempt is only ever recorded once its lines have stopped
# arriving, and the overlap above then re-reads that settled region anyway.
SETTLE_SECONDS = 30


def event_dict(attempt: LoginAttempt, pod_name: str, observed_at: str) -> dict:
    """A LoginAttempt plus the two things the store needs and the parser cannot know.

    `pod_name` is required because it is IN the dedup key, and LoginAttempt deliberately does not carry
    it — the parser takes text and knows nothing about where it came from, which is what makes it
    testable without a cluster. Public rather than private so tests can build rows the same way the
    capture loop does, instead of hand-assembling dicts that drift from it.

    The timestamp format is fixed here, once. Microsecond precision with a literal Z, because it is
    part of the unique key: two attempts one microsecond apart must not collide, and a format that
    varied between writer and reader would make the key match rows it should not.
    """
    return {
        "pod_name": pod_name,
        "user_name": attempt.user_name,
        "outcome": attempt.outcome,
        "at": attempt.at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "provider": attempt.provider,
        "ldap_result_code": attempt.ldap_result_code,
        "detail": attempt.detail,
        "observed_at": observed_at,
    }


def _settle_horizon(attempts: list[LoginAttempt]) -> str | None:
    """The newest attempt old enough to be called settled, or None if none is yet.

    RELATIVE TO NOW, not to the newest attempt in the batch — and that distinction is a bug I shipped
    into the first draft. Measuring from the newest attempt means a BURST of logins inside
    SETTLE_SECONDS makes every one of them "unsettled" relative to its own peers, so the watermark
    never advances at all: the same window is re-read forever, sinceSeconds stays at first-sight, and
    the read grows without bound. Caught by the healthy-path test writing zero watermarks.

    Measuring from now is what the horizon is actually for: an attempt stops being at risk of having
    more lines arrive once wall-clock has moved past it, regardless of what else was in the batch.
    """
    if not attempts:
        return None
    from datetime import UTC, datetime
    cutoff = datetime.now(UTC).timestamp() - SETTLE_SECONDS
    settled = [a.at for a in attempts if a.at.timestamp() <= cutoff]
    if not settled:
        # Everything here is newer than the horizon, so nothing is confirmed finished. The events are
        # still RECORDED — only the watermark waits, and the next cycle re-reads them harmlessly
        # because of the dedup key. Recording early and advancing late is the safe order.
        return None
    return max(settled).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def capture_once(
    store: StorageBackend,
    cluster: ClusterConfig,
    settings: Settings,
    elector=None,
    timeout: float = 15.0,
) -> int:
    """One capture pass over one cluster. Returns events recorded. NEVER raises for cluster problems.

    ── THE LEADERSHIP RECHECK, AND WHY IT IS WHERE IT IS ─────────────────────────────────────────────
    `poller.py` says of its lease, in its own words, that it is "BEST-EFFORT admission control, NOT a
    write fence", and `_run_cluster` checks it once per cycle. That is fine for group polling and not
    fine here, because this reads logs over the network: the check can pass, the read can block, the
    lease can expire and pass to another replica, and the old leader's read can then return and write.
    Codex named the sequence exactly — leader check true → log GET blocks → lease lost → new leader
    starts → old GET returns → old leader records events and watermark.

    So leadership is rechecked IMMEDIATELY BEFORE the write transaction, which narrows the window from
    "the length of a log read" to "the few instructions between the check and the INSERT". It does not
    close it, and this comment exists so nobody later mistakes it for a fence: closing it needs a
    fencing token the lease does not provide. What makes the residual window tolerable is the dedup
    key — two leaders writing the same lines produce the same rows, and INSERT OR IGNORE collapses
    them. The watermark is the part that could regress, and `set_login_watermark` takes max() precisely
    so a late write from a demoted leader cannot rewind it.
    """
    if not settings.login_capture_enabled:
        return 0

    ns = settings.login_capture_namespace
    client = ClusterClient(cluster, timeout=timeout)

    try:
        pods = client.fetch_oauth_pods(ns)
    except ClusterError as exc:
        log.warning("%s: login capture could not list pods: %s — group data is unaffected",
                    cluster.name, exc.message)
        return 0
    if pods is None:
        log.info("%s: login capture is not permitted to list pods in %s; nothing recorded",
                 cluster.name, ns)
        return 0
    if not pods:
        log.info("%s: no Running oauth-server pods in %s", cluster.name, ns)
        return 0

    watermarks = store.login_watermarks(cluster.name)
    recorded = 0
    read_ok = False

    for pod in pods:
        settled_through = watermarks.get(pod)
        if settled_through is None:
            since = FIRST_SIGHT_SECONDS
        else:
            # Seconds back from now to the watermark, plus the overlap. sinceSeconds is relative and
            # coarse (whole seconds), which is exactly why the dedup key rather than arithmetic is what
            # guarantees correctness here.
            age = _seconds_since(settled_through)
            since = max(OVERLAP_SECONDS, int(age) + OVERLAP_SECONDS) if age is not None \
                else FIRST_SIGHT_SECONDS

        try:
            lines = client.fetch_pod_log(ns, pod, since_seconds=since)
        except ClusterError as exc:
            # An AUTH_FAILED here is worth surfacing but must not stop the other pods.
            log.warning("%s: login capture failed reading %s: %s", cluster.name, pod, exc.message)
            continue
        if lines is None:
            continue                      # roll noise or a missing grant; both already logged
        read_ok = True

        attempts = parse(lines)
        if not attempts:
            continue

        observed_at = now_iso()
        events = [event_dict(a, pod, observed_at) for a in attempts]
        horizon = _settle_horizon(attempts)

        # THE RECHECK. Everything above is reads; everything below writes.
        if elector is not None and not elector.is_leader:
            log.info("%s: lost leadership while reading %s — discarding %d event(s) unwritten",
                     cluster.name, pod, len(events))
            return recorded

        n = store.record_login_events(cluster.name, events)
        recorded += n
        if horizon is not None:
            store.set_login_watermark(cluster.name, pod, horizon, observed_at)
        if n:
            log.info("%s: recorded %d login attempt(s) from %s", cluster.name, n, pod)

    if not read_ok:
        # Not a single pod answered. Do NOT stamp a successful read: `started_at` would then claim we
        # have been watching since a cycle that saw nothing, and `last_read_at` is the liveness signal
        # that tells somebody capture has stopped.
        return recorded

    if elector is not None and not elector.is_leader:
        return recorded
    store.record_login_read(cluster.name, now_iso())

    _prune(store, cluster, settings, elector)
    return recorded


def _prune(store: StorageBackend, cluster: ClusterConfig, settings: Settings, elector=None) -> None:
    """Drop events past the retention window, and watermarks for pods that are gone.

    Bounded per call by store.prune_login_events' own max_rows, because this runs on the poll thread
    against a single writer — an unbounded DELETE over a long backlog holds the write lock while every
    reader and the next poll wait behind it. A full chunk means more remains, and the next cycle
    continues; there is no need to finish in one pass.
    """
    days = settings.login_retention_days
    if days <= 0:
        return                            # 0 disables retention, deliberately
    before = _iso_days_ago(days)
    if before is None:
        return
    if elector is not None and not elector.is_leader:
        return
    removed = store.prune_login_events(cluster.name, before)
    if removed:
        log.info("%s: pruned %d login event(s) older than %s", cluster.name, removed, before)


def _seconds_since(iso: str) -> float | None:
    """Seconds between an ISO timestamp and now, or None if it cannot be parsed."""
    from datetime import UTC, datetime
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (datetime.now(UTC) - then).total_seconds())


def _iso_days_ago(days: int) -> str | None:
    from datetime import UTC, datetime, timedelta
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
