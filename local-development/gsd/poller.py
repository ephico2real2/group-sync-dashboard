"""The poll loop (PLAN §12).

Poll, don't watch (PLAN §6): sync events are at most hourly, so N persistent watches with
reconnect handling and relist storms buys nothing over two list calls a minute.

Each cluster is polled on its own thread. One slow or unreachable cluster must not stall the
others — a shared sequential loop would let a cluster that black-holes TCP hold every other
cluster's data hostage for the duration of the timeout.
"""

from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime

from .config import ClusterConfig, Settings
from .kube import OK, ClusterClient, ClusterError, GroupSyncView, GroupView
from .leader import LeaderElector
from .store import Store, now_iso

log = logging.getLogger(__name__)


def provider_key_for(cr: GroupSyncView, groups: list[GroupView]) -> str | None:
    """Work out which sync-provider label value belongs to this CR (PLAN §3).

    The operator writes ``<groupsync-name>_<provider>``, but the provider's name lives in
    the CR spec while the label is only observable on the Groups. Rather than reconstruct
    the string and hope, match against the label values actually present: the CR owns the
    value whose prefix is its own name.

    Returns None when no group carries a matching label — a CR that has produced nothing
    yet. That is deliberately distinct from an empty string, which would match everything.
    """
    prefix = f"{cr.name}_"
    for group in groups:
        if group.sync_provider and group.sync_provider.startswith(prefix):
            return group.sync_provider
    return None


def poll_once(store: Store, cluster: ClusterConfig, timeout: float = 15.0) -> str:
    """One poll of one cluster. Returns the outcome string (PLAN §12 step 7).

    Never raises for cluster-side failures: an unreachable or forbidden cluster is recorded
    as a degraded outcome so it renders as a degraded card rather than blanking the
    dashboard (PLAN §5).
    """
    client = ClusterClient(cluster, timeout=timeout)
    try:
        groupsyncs, groups = client.fetch()
    except ClusterError as exc:
        log.warning("poll %s failed: %s (%s)", cluster.name, exc.message, exc.outcome)
        store.record_poll(cluster.name, exc.outcome, exc.message)
        return exc.outcome

    observed_at = now_iso()

    # Steps 3-4: attribute groups to CRs, then record any sync we had not seen before.
    cr_rows = []
    new_events = 0
    for cr in groupsyncs:
        key = provider_key_for(cr, groups)
        group_count = sum(1 for g in groups if g.sync_provider == key) if key else 0

        cr_rows.append(
            {
                "name": cr.name,
                "namespace": cr.namespace,
                "schedule": cr.schedule,
                "ldap_filter": cr.ldap_filter,
                "last_sync_at": cr.last_sync_at,
                "generation": cr.generation,
                "provider_key": key,
            }
        )

        if cr.last_sync_at:
            inserted = store.record_sync_event(
                cluster_id=cluster.name,
                name=cr.name,
                namespace=cr.namespace,
                synced_at=cr.last_sync_at,
                observed_at=observed_at,
                schedule=cr.schedule,
                group_count=group_count,
            )
            if inserted:
                new_events += 1
                log.info(
                    "%s/%s: new sync observed at %s (%d groups)",
                    cluster.name,
                    cr.name,
                    cr.last_sync_at,
                    group_count,
                )

        # Step 5: the failure condition, stored whether or not it is current (PLAN §2.1).
        store.upsert_reconcile_error(
            cluster.name, cr.name, cr.error_at, cr.error_generation, cr.error_message
        )

    store.replace_groupsync_state(cluster.name, cr_rows, observed_at)

    # Step 6
    store.replace_group_state(
        cluster.name,
        [
            {
                "name": g.name,
                "member_count": g.member_count,
                "sync_provider": g.sync_provider,
                "group_synced_at": g.group_synced_at,
                "ldap_uid": g.ldap_uid,
            }
            for g in groups
        ],
        observed_at,
    )

    # Provenance for RBAC finding classification: remember which groups the operator
    # manages, so that a binding naming one of them later becomes meaningful evidence
    # rather than an unresolvable name.
    store.record_managed_groups(
        cluster.name,
        [{"name": g.name, "sync_provider": g.sync_provider} for g in groups],
        observed_at,
    )

    # Step 7: reconcile membership and record who joined or left since the last poll.
    member_changes = store.sync_members(
        cluster_id=cluster.name,
        memberships={g.name: g.members for g in groups},
        sync_times={g.name: g.group_synced_at for g in groups},
        observed_at=observed_at,
    )

    store.record_poll(cluster.name, OK, None)
    log.info(
        "polled %s: %d CRs, %d groups, %d new sync event(s), %d membership change(s)",
        cluster.name,
        len(groupsyncs),
        len(groups),
        new_events,
        member_changes,
    )
    return OK


def refresh_bindings(store: Store, cluster: ClusterConfig, timeout: float) -> str:
    """Re-read RoleBindings/ClusterRoleBindings for one cluster.

    Deliberately does NOT record a poll outcome. A binding-list failure — most likely a
    403, since this needs RBAC the group poll does not — must not mark the cluster
    unreachable and blank out perfectly good group data. It is logged and retried on the
    next binding interval.
    """
    client = ClusterClient(cluster, timeout=timeout)
    try:
        bindings = client.fetch_bindings()
    except ClusterError as exc:
        log.warning(
            "binding refresh for %s failed: %s (%s) — group data is unaffected",
            cluster.name, exc.message, exc.outcome,
        )
        return exc.outcome

    store.replace_bindings(
        cluster.name,
        [
            {
                "binding_kind": b.binding_kind,
                "binding_namespace": b.binding_namespace,
                "binding_name": b.binding_name,
                "role_kind": b.role_kind,
                "role_name": b.role_name,
                "group_name": b.group_name,
            }
            for b in bindings
        ],
        now_iso(),
    )
    log.info("refreshed %d group bindings for %s", len(bindings), cluster.name)
    return OK


class Poller:
    """Runs one polling thread per enabled cluster."""

    def __init__(self, store: Store, settings: Settings, elector: LeaderElector | None = None):
        self.store = store
        self.settings = settings
        # Only the leader writes. Without this, a scale-up, a slow Recreate, or a partitioned
        # node puts two pollers on one database — and the poll loop is not idempotent across
        # writers, so racing sync_members calls emit membership events for changes that never
        # happened.
        self.elector = elector
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def _run_cluster(self, cluster: ClusterConfig) -> None:
        # Poll immediately on start rather than sleeping first: a restarted dashboard that
        # shows nothing for its first interval is indistinguishable from a broken one.
        next_binding_refresh = 0.0
        while not self._stop.is_set():
            started = datetime.now(UTC)
            if self.elector is not None and not self.elector.is_leader:
                # Standby: serve reads, write nothing. Checked every cycle rather than once,
                # so leadership lost mid-life stops the writes promptly.
                log.debug("%s: not leader, skipping poll", cluster.name)
                self._stop.wait(self.settings.poll_interval_seconds)
                continue
            try:
                poll_once(self.store, cluster, self.settings.request_timeout_seconds)
            except Exception:  # noqa: BLE001 - a poll thread must never die silently
                log.exception("unhandled error polling %s", cluster.name)
                # The recovery write can fail for the SAME reason the poll did — a full or
                # locked database. Unguarded, that second failure escapes this handler and
                # kills the thread permanently, while /healthz stays unconditionally green
                # and /readyz only does a read: the dashboard then serves frozen data
                # forever and reports itself healthy. Never let cleanup end the loop.
                try:
                    self.store.record_poll(
                        cluster.name, "unreachable", "internal poller error"
                    )
                except Exception:  # noqa: BLE001
                    log.exception(
                        "could not even record the poll failure for %s; "
                        "the poll loop continues",
                        cluster.name,
                    )

            # Bindings ride the same thread but on their own due-time, so an expensive
            # cluster-wide binding list does not run every group poll.
            now = time.monotonic()
            if now >= next_binding_refresh:
                try:
                    refresh_bindings(
                        self.store, cluster, self.settings.request_timeout_seconds
                    )
                except Exception:  # noqa: BLE001
                    log.exception("unhandled error refreshing bindings for %s", cluster.name)
                next_binding_refresh = now + self.settings.binding_interval_seconds

            elapsed = (datetime.now(UTC) - started).total_seconds()
            log.debug(
                "%s poll cycle took %.2fs; next binding refresh in %.0fs",
                cluster.name, elapsed, max(0.0, next_binding_refresh - time.monotonic()),
            )
            self._stop.wait(max(1.0, self.settings.poll_interval_seconds - elapsed))

    def start(self) -> None:
        for cluster in self.settings.clusters:
            self.store.upsert_cluster(cluster.name, cluster.api_url, cluster.enabled)
            if not cluster.enabled:
                log.info("cluster %s is disabled, not polling", cluster.name)
                continue
            thread = threading.Thread(
                target=self._run_cluster, args=(cluster,), name=f"poll-{cluster.name}", daemon=True
            )
            thread.start()
            self._threads.append(thread)
        log.info("poller started for %d cluster(s)", len(self._threads))

    def stop(self) -> None:
        self._stop.set()
        for thread in self._threads:
            thread.join(timeout=5)
