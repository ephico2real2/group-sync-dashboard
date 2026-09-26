"""Audit login capture entry point and bounded retention.

Legacy event_dict remains an offline row-construction helper for stored-history tests.
It does not read pod logs or select a retired source.
"""
from __future__ import annotations

import logging

from .config import ClusterConfig, Settings
from .loginlog import LoginAttempt
from .storage import StorageBackend

log = logging.getLogger(__name__)


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



def capture_once(store: StorageBackend, cluster: ClusterConfig, settings: Settings,
                 elector=None, timeout: float = 15.0, signals=None) -> int:
    """The poller's entry point: off means no read; on means audit-log only."""
    if not settings.login_capture_enabled:
        log.debug("%s: login capture is disabled; no audit log is read", cluster.name)
        return 0
    from .auditlog import capture_once as capture_audit_once
    return capture_audit_once(store, cluster, settings, elector, timeout, signals)


def _prune(store: StorageBackend, cluster: ClusterConfig, settings: Settings, elector=None,
           signals=None) -> None:
    """Drop events past the retention window.

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



def _iso_days_ago(days: int) -> str | None:
    from datetime import UTC, datetime, timedelta
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
