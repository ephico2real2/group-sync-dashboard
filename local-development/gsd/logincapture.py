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
from .loginlog import ATTEMPT_WINDOW, LoginAttempt, parse, parse_timestamp
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


def _settle_horizon(lines: list[str]) -> str | None:
    """The newest log instant old enough to be called settled, or None if none is yet.

    A READ CURSOR OVER LOG TIME, NOT OVER ATTEMPTS. The first shipped version took only parsed
    attempts, which stalls on a pod that logs plenty and authenticates nobody: the watermark never
    moves, sinceSeconds grows by the full poll interval every cycle for the life of the pod, and
    once the window outgrows the byte cap the newest lines are deferred every cycle while capture
    still stamps itself live. Any timestamped line proves the log was read through that instant,
    so any timestamped line may advance the cursor — without inventing a login record.

    RELATIVE TO NOW, not to the newest line in the batch — and that distinction is a bug I shipped
    into the first draft. Measuring from the newest meant a BURST of logins inside SETTLE_SECONDS
    made every one of them "unsettled" relative to its own peers, so the watermark never advanced
    at all: the same window was re-read forever. Caught by the healthy-path test writing zero
    watermarks. Measuring from now is what the horizon is actually for: a line stops being at risk
    of belonging to a still-arriving attempt once wall-clock has moved past it.
    """
    from datetime import UTC, datetime
    cutoff = datetime.now(UTC).timestamp() - SETTLE_SECONDS
    stamps = [ts for raw in lines if (ts := parse_timestamp(raw)) is not None
              and ts.timestamp() <= cutoff]
    if not stamps:
        return None
    return max(stamps).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _recordable(attempts: list[LoginAttempt]) -> list[LoginAttempt]:
    """Only the attempts old enough that every one of their lines must already have arrived.

    An attempt read MID-FLIGHT concludes on partial evidence: the provider-chain `failed` line is
    in the read, the success that follows it is not yet written, and the parse honestly returns a
    failure that never happened. The dedup key cannot collapse that with the finished attempt —
    the outcome differs — so the sliced row would sit beside the real one forever, and the page
    would show a failed login that is provider-order noise. Withholding an attempt until
    wall-clock has passed its whole window costs at most one cycle of latency, and nothing is
    lost: the watermark (same cutoff, minus the window) never advances past a withheld attempt,
    and OVERLAP_SECONDS exceeds SETTLE_SECONDS plus the attempt window, so the next read has the
    whole attempt again.
    """
    from datetime import UTC, datetime, timedelta
    cutoff = datetime.now(UTC) - timedelta(seconds=SETTLE_SECONDS) - ATTEMPT_WINDOW
    return [a for a in attempts if a.at <= cutoff]


def _not_clipped(attempts: list[LoginAttempt], window_start: datetime) -> list[LoginAttempt]:
    """Only the attempts that cannot have had earlier lines cut off by the window's leading edge.

    THE MIRROR OF `_recordable`, FOR THE OTHER END OF THE READ. That one distrusts the newest lines
    because the rest of an attempt may not have been written yet; this distrusts the oldest, because
    the rest of it may lie behind the window. Both failures look the same from here — a parse that
    concludes on part of an attempt — and only one of them had a guard.

    What it prevents, measured: a window opening in the 1.167 ms between a bind error and its verdict
    parses the verdict alone, so the login the previous cycle recorded as `bad_password` stamped at the
    cause is recorded AGAIN as `failed` stamped at the verdict. `at` and `outcome` are both in
    UNIQUE(cluster_id, pod_name, user_name, at, outcome), so nothing collapses them and the page
    reports one person's single login twice — once with a reason and once without. The boundary is
    reachable by this module's own arithmetic: it sits at `watermark - OVERLAP_SECONDS` and sweeps
    forward a cycle at a time, so it crosses every instant in the log eventually.

    An attempt's lines span at most ATTEMPT_WINDOW, so once `at` is further than that from the edge no
    unseen line can belong to it — anything earlier would have been inside the window and parsed.

    WHAT THIS DELIBERATELY GIVES UP. A withheld attempt is normally safe because the overlap re-reads
    it, but the watermark advances to `now - SETTLE_SECONDS` regardless, which is ahead of this edge —
    so an attempt dropped here is dropped for good, not deferred. In the ordinary case that costs
    nothing: the edge sits OVERLAP_SECONDS behind the watermark, so anything near it was fully inside
    an earlier cycle's window and is already recorded. It costs a row in two cases — a first sight,
    where the edge is FIRST_SIGHT_SECONDS back and the hour boundary is already declared lost, and a
    restart that lands the new edge within one second of an attempt the previous process had withheld.
    Losing a row there is the trade this module makes everywhere else: an absent record beats a false
    one, and the false one here is a second row contradicting the first about a named person.
    """
    edge = window_start + ATTEMPT_WINDOW
    return [a for a in attempts if a.at > edge]


def capture_once(
    store: StorageBackend,
    cluster: ClusterConfig,
    settings: Settings,
    elector=None,
    timeout: float = 15.0,
    signals=None,
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
        # DEBUG, not INFO: this is a configuration state rather than an event, so at INFO it would
        # repeat once per cluster per cycle forever and say nothing new. But it must be sayable
        # SOMEWHERE — "the Logins tab is empty" and "capture is switched off" are the same symptom,
        # and this is the only line that tells them apart.
        log.debug("%s: login capture is disabled, so no oauth-server logs are read and the Logins "
                  "tab will stay empty; set loginCapture.enabled=true to change that", cluster.name)
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
        # WARNING, not INFO, and the contract decides it: reaching here means capture is ENABLED
        # (the check above returned otherwise) and RBAC forbids the read, so the feature is
        # configured but inert and will not self-heal until somebody applies the grant. That is
        # the contract's WARNING case in its own words.
        #
        # It was INFO, which also made it invisible to anyone watching WARNING and above — while
        # kube.py#fetch_oauth_pods logs its own INFO for the same 403, so a forbidden cluster
        # emitted two INFO lines every cycle and nothing an operator would ever be paged on.
        log.warning("%s: login capture is enabled but not permitted to list pods in %s, so no "
                    "logins will be recorded until the grant is applied", cluster.name, ns)
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

        from datetime import UTC, datetime, timedelta
        try:
            lines = client.fetch_pod_log(ns, pod, since_seconds=since)
        except ClusterError as exc:
            # An AUTH_FAILED here is worth surfacing but must not stop the other pods.
            log.warning("%s: login capture failed reading %s: %s", cluster.name, pod, exc.message)
            continue
        if lines is None:
            continue                      # roll noise or a missing grant; both already logged
        read_ok = True

        # Stamped AFTER the response, and that direction is load-bearing. The kubelet resolves
        # sinceSeconds against its own RECEIVE time, so the true boundary is `receive - since`, which
        # this bounds from above: taking the stamp before the request would put the derived edge up to
        # one request-latency too EARLY, and the leading-edge guard would then miss exactly the attempts
        # a slow read clipped. An 8 MiB read can take longer than ATTEMPT_WINDOW, so that is not
        # hypothetical. Erring late costs at most a row near the edge, which in steady state was
        # already recorded a cycle ago.
        window_start = datetime.now(UTC) - timedelta(seconds=since)
        # SPLIT INTO NAMED STAGES so the DEBUG line below can report each one. This was a single
        # composed expression, which is tidier to read and impossible to explain: the two filters
        # remove attempts for OPPOSITE reasons, and from outside both look like "the parser found
        # things and the store got none".
        #   _recordable  withholds an attempt whose success line may not be written yet — it comes
        #                back next cycle (see its docstring).
        #   _not_clipped drops an attempt whose earlier lines may lie behind the window's leading
        #                edge — "dropped for good, not deferred", in its own words.
        parsed = parse(lines)
        settled = _recordable(parsed)
        attempts = _not_clipped(settled, window_start)
        horizon = _settle_horizon(lines)

        # THE LINE THAT MAKES SILENCE LEGIBLE, and the reason this module gained any DEBUG at all.
        # In steady state every path from here down is quiet — no NEW attempts means no INFO — so a
        # working capture and a broken one produce identical logs. Measured on the reference
        # cluster: 73 attempts stored, 13 distinct users, and not one line in the pod log to say
        # capture was running.
        #
        # "settled through", not "advances to": store.set_login_watermark applies max(), so a late
        # write from a demoted leader cannot rewind it and this horizon may not become the new one.
        log.debug("%s: %s read %d line(s) covering the last %ds from read position %s — parsed %d, "
                  "withheld %d still settling (returns next cycle), dropped %d clipped at the "
                  "window's leading edge (gone for good), %d to write; log settled through %s",
                  cluster.name, pod, len(lines), since,
                  settled_through or "none (first-sight window)",
                  len(parsed), len(parsed) - len(settled), len(settled) - len(attempts),
                  len(attempts), horizon or "nothing yet — read position holds")

        if lines and not parsed:
            # GATED ON `parsed`, NOT ON `attempts`, and that distinction is the whole point. If the
            # parser found attempts and the two filters withheld them, the cause is this module's
            # own arithmetic and the line above already says so — blaming the cluster there would
            # send an operator to the wrong place.
            #
            # Nothing parsed at all has one overwhelmingly likely cause, and it is not "nobody
            # logged in": the oauth-server writes the line naming a person ONLY while the
            # authentication OPERATOR is at spec.logLevel: Debug. That is a different log level from
            # this chart's `logLevel`, on a different object, in a different vocabulary
            # (Normal/Debug/Trace/TraceAll) — and confusing the two is the likeliest reason a
            # healthy-looking deployment records nothing. Both honest possibilities are stated,
            # because a genuinely quiet cluster reads identically.
            log.debug("%s: %s: %d line(s) read and no login attempt in any of them — either nobody "
                      "logged in, or authentications.operator.openshift.io/cluster is not at "
                      "spec.logLevel: Debug, without which the lines naming a person are never "
                      "written (chart value authLogLevel, NOT logLevel; see "
                      "docs/LOGIN_CAPTURE_QUICKCHECK.md)", cluster.name, pod, len(lines))

        if not attempts and horizon is None:
            continue

        observed_at = now_iso()
        events = [event_dict(a, pod, observed_at) for a in attempts]

        # THE RECHECK. Everything above is reads; everything below writes.
        if elector is not None and not elector.is_leader:
            log.info("%s: lost leadership while reading %s — discarding %d event(s) unwritten",
                     cluster.name, pod, len(events))
            return recorded

        n = store.record_login_events(cluster.name, events) if events else 0
        recorded += n
        if horizon is not None:
            store.set_login_watermark(cluster.name, pod, horizon, observed_at)
        if n:
            log.info("%s: recorded %d login attempt(s) from %s", cluster.name, n, pod)
        elif attempts:
            # The commonest steady-state path, and previously the most confusing: attempts WERE
            # found and none were new, because the overlap deliberately re-reads a window that was
            # already recorded. Without this, a working capture that has caught up is silent in
            # exactly the way a broken one is.
            log.debug("%s: %s: all %d attempt(s) in the window were already stored — the %ds "
                      "overlap re-reads them by design, so this is steady state, not a failure",
                      cluster.name, pod, len(attempts), OVERLAP_SECONDS)

    # Forget read positions for pods that are gone. Every oauth roll replaces them, so without this
    # the table grows by one row per pod name the cluster has ever had.
    #
    # Done on the strength of the POD LIST — which succeeded above, or we would have returned — and
    # NOT gated on whether any read worked: a cluster whose log reads are all refused would otherwise
    # keep every dead pod's position forever, which is the case most likely to accumulate them. It is
    # also independent of `login_retention_days`, because this is a leak rather than a policy about
    # how long to keep data; _prune's docstring claimed to do it and never did.
    if elector is None or elector.is_leader:
        dropped = store.prune_login_watermarks(cluster.name, pods)
        if dropped:
            log.info("%s: forgot %d stale read position(s) for pods that no longer exist",
                     cluster.name, dropped)

    if not read_ok:
        # Not a single pod answered. Do NOT stamp a successful read: `started_at` would then claim we
        # have been watching since a cycle that saw nothing, and `last_read_at` is the liveness signal
        # that tells somebody capture has stopped.
        #
        # SAY SO, because the decision above is invisible otherwise. Its whole effect is a metric
        # that stops moving (gsd_login_capture_last_read_timestamp_seconds), and a gauge going flat
        # is not self-explaining — nothing marked the cycle where it happened. WARNING rather than
        # ERROR: group polling is untouched and an oauth roll self-heals it within a cycle or two.
        log.warning("%s: login capture read none of the %d oauth-server pod(s) in %s this cycle; "
                    "the last-read stamp is deliberately not advanced, so the dashboard will report "
                    "capture as stale until one answers", cluster.name, len(pods), ns)
        return recorded

    if elector is not None and not elector.is_leader:
        return recorded
    store.record_login_read(cluster.name, now_iso())

    _prune(store, cluster, settings, elector, signals)
    return recorded


def _prune(store: StorageBackend, cluster: ClusterConfig, settings: Settings, elector=None,
           signals=None) -> None:
    """Drop events past the retention window.

    Watermarks are NOT pruned here — that happens in capture_once, where the live pod list is in
    scope and where it is correctly independent of this retention setting. This docstring used to
    claim both and deliver one.

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
        if signals is not None:
            # Duck-typed metrics seam (gsd/metrics.py RuntimeSignals), same count as the
            # log line below and from the same call, so the two cannot disagree. A rate
            # pinned at the 5000-row bound is the backlog-not-draining signal.
            signals.note_retention("login_event", removed)
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
