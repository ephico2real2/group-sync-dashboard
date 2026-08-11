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
from .kube import OK, ClusterClient, ClusterError, GroupSyncView, GroupView, dn_equal
from .leader import LeaderElector
from .logincapture import capture_once
from .audit import plan_audit_stamps
from .storage import StorageBackend
from .timeutil import now_iso

log = logging.getLogger(__name__)

# How often a non-leader re-checks whether it has become the leader. Deliberately decoupled
# from the poll interval: this costs a flag read, while tying it to the poll interval makes
# the delay before a new leader's first poll scale with a value chosen for a different
# reason entirely.
STANDBY_RECHECK_SECONDS = 5


def provider_keys_for(cr: GroupSyncView, groups: list[GroupView]) -> list[str]:
    """Every sync-provider label value belonging to this CR (PLAN §3).

    The operator writes ``<groupsync-name>_<provider>``, but the provider's name lives in
    the CR spec while the label is only observable on the Groups. Rather than reconstruct
    the string and hope, match against the label values actually present: the CR owns every
    value whose prefix is its own name.

    ALL of them, not the first. A CR may declare several providers, and each produces its
    own label value — ``corp_ldap-a`` and ``corp_ldap-b`` for a CR named ``corp``. Taking
    only the first left every group of every later provider with no owner: not flagged
    unattributed, because it does carry a label, and never staleness-checked, because no CR
    claimed it. Silently invisible is the one failure this dashboard exists to prevent.

    Returns [] when no group carries a matching label — a CR that has produced nothing yet.
    That is deliberately distinct from [""], which would match every unlabelled group.
    Sorted, so attribution is stable across polls regardless of Group list order.

    EXACT MATCH FIRST. When the CR declares its provider names, the label the operator
    writes is exactly ``<cr.name>_<provider>``, so it is reconstructed and intersected with
    what the Groups actually carry — reconstruction checked against observation, rather
    than either alone. Prefix matching alone is ambiguous and the ambiguity is reachable:
    a CR named ``corp`` and a CR named ``corp_extra`` BOTH match ``corp_extra_ldap``, so
    that group gets two owners, is counted in both CRs' group_count, and raises two stale
    alerts for one problem.

    The prefix path remains for a CR whose spec declares no provider names, and it now
    yields a label to the LONGEST matching CR name: between ``corp`` and ``corp_extra``,
    ``corp_extra_ldap`` belongs to ``corp_extra``. That is a tie-break, not a fix — see
    `ambiguous_attribution` for the case nothing can resolve.
    """
    observed = {g.sync_provider for g in groups if g.sync_provider}
    if cr.provider_names:
        return sorted(observed & {f"{cr.name}_{p}" for p in cr.provider_names})

    prefix = f"{cr.name}_"
    return sorted(label for label in observed if label.startswith(prefix))


def ambiguous_attribution(groupsyncs: list[GroupSyncView]) -> list[str]:
    """CR names that cannot be told apart from a Group label. Returns the colliding names.

    Two CRs with the SAME NAME in different namespaces produce byte-identical labels: the
    operator writes ``<name>_<provider>`` and namespace appears nowhere in it. No amount of
    care here resolves that — the information is not in the data. The honest response is to
    say so rather than silently attribute the groups to whichever CR was iterated first.
    """
    seen: dict[str, set[str]] = {}
    for cr in groupsyncs:
        seen.setdefault(cr.name, set()).add(cr.namespace)
    return sorted(name for name, namespaces in seen.items() if len(namespaces) > 1)


def poll_once(
    store: StorageBackend,
    cluster: ClusterConfig,
    timeout: float = 15.0,
    access_group_dn: str = "",
) -> str:
    """One poll of one cluster. Returns the outcome string (PLAN §12 step 7).

    Never raises for cluster-side failures: an unreachable or forbidden cluster is recorded
    as a degraded outcome so it renders as a degraded card rather than blanking the
    dashboard (PLAN §5).

    `access_group_dn` is the configured login-gate group. Empty means discover it from the OAuth CR.
    A parameter rather than a Settings argument because this function takes one cluster and a timeout
    and nothing else — threading the whole Settings through it to read one string would make every
    test that calls it build one.
    """
    client = ClusterClient(cluster, timeout=timeout)
    try:
        groupsyncs, groups = client.fetch()
    except ClusterError as exc:
        log.warning("poll %s failed: %s (%s)", cluster.name, exc.message, exc.outcome)
        store.record_poll(cluster.name, exc.outcome, exc.message)
        return exc.outcome

    # Undecidable, so say so rather than attributing to whichever CR came first. Two CRs
    # with the same name in different namespaces produce byte-identical Group labels — the
    # operator writes <name>_<provider> and namespace appears nowhere in it.
    # `None` means the CRD is absent; every loop below wants a list, and only
    # replace_groupsync_state needs to know the difference. Normalised here so the tri-state
    # cannot leak into the attribution logic, where `for cr in None` would raise mid-poll.
    crs = groupsyncs if groupsyncs is not None else []

    for collision in ambiguous_attribution(crs):
        log.warning(
            "%s: GroupSync %r exists in more than one namespace and the sync-provider "
            "label carries no namespace, so its groups cannot be attributed to one CR. "
            "Ownership, group_count and stale-group alerts for those groups are ambiguous.",
            cluster.name, collision,
        )

    observed_at = now_iso()

    # Display names, in the SAME cycle as the members they annotate. Deliberately here and not on
    # the slower refresh_bindings cadence: these names are rendered beside group members, which
    # this function writes, and a name arriving a cadence later than the member it labels would
    # show a fresh member with a stale-or-absent name.
    #
    # The most forgiving call in the cycle, because the data is cosmetic. `None` means FORBIDDEN —
    # the chart's `users` grant is not applied here — and any other failure is logged and skipped.
    # In BOTH cases the previous cycle's names stay in the database: writing {} would blank every
    # name currently on screen, which is worse than a stale name and much worse than doing nothing.
    #
    # getattr, not a direct call: tests stub this client with only the methods they exercise, and a
    # cosmetic field must not turn an old stub into an AttributeError mid-poll.
    fetch_users = getattr(client, "fetch_users", None)
    if fetch_users is not None:
        try:
            names = fetch_users()
        except ClusterError as exc:
            log.warning("display-name refresh for %s failed: %s — names are unaffected",
                        cluster.name, exc.message)
        else:
            if names is None:
                log.info("%s: not permitted to list users — display names left as they were. "
                         "Grant user.openshift.io/users [get,list] (chart: rbac.users) to enable.",
                         cluster.name)
            else:
                store.replace_users(cluster.name, names, observed_at)
                log.info("%s: %d display name(s) recorded", cluster.name, len(names))

    # Steps 3-4: attribute groups to CRs, then record any sync we had not seen before.
    cr_rows = []
    new_events = 0
    for cr in crs:
        keys = provider_keys_for(cr, groups)
        owned = set(keys)
        group_count = sum(1 for g in groups if g.sync_provider in owned)

        cr_rows.append(
            {
                "name": cr.name,
                "namespace": cr.namespace,
                "schedule": cr.schedule,
                "ldap_filter": cr.ldap_filter,
                "last_sync_at": cr.last_sync_at,
                "generation": cr.generation,
                "provider_keys": keys,
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

    # ONE TRANSACTION FROM HERE TO record_poll. Everything below lands together or not at
    # all. It used to be seven separate commits, so any read arriving mid-cycle saw a
    # mixture — measured at 11,598 torn reads in 19,208, a 60.38% failure rate — and a
    # cycle that died halfway could still stamp record_poll(OK) over half-written state,
    # which looks healthy and is the worse failure.
    #
    # record_sync_event is deliberately ABOVE this line and already committed: its key is
    # the operator's own lastSyncSuccessTime, so a rollback loses an observation for good
    # rather than re-deriving it next cycle.
    with store.poll_snapshot():
        for cr in crs:
            # Step 5: the failure condition, stored whether or not it is current (PLAN §2.1).
            store.upsert_reconcile_error(
                cluster.name, cr.name, cr.error_at, cr.error_generation, cr.error_message
            )

        # None when the CRD is absent, so the store records "not installed" rather than
        # "installed with zero CRs". cr_rows is [] in both cases and cannot carry that.
        store.replace_groupsync_state(
            cluster.name, None if groupsyncs is None else cr_rows, observed_at)

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

        # ── WHICH GROUP GATES AUTHENTICATION ─────────────────────────────────────────────────────
        # Resolved HERE, inside the snapshot that just wrote the groups, so the DN and the Group it
        # names are one consistent observation. Doing it at read time would let a group deleted
        # between poll and read turn a known gate into an unknown one.
        #
        # Configuration wins over discovery, and `source` records which answered, because an operator
        # asking "why is this the wrong group?" needs to know which of the two to change.
        dn = (access_group_dn or "").strip()
        source = "config"
        if not dn:
            # One extra GET per cluster per poll, and only when the DN is not configured. A
            # ClusterError here must not fail the poll: the gate is an enrichment, and groups are
            # the reason this function exists.
            source = "oauth"
            try:
                dn = client.fetch_access_group_dn() or ""
            except ClusterError as exc:
                log.warning("%s: could not read the OAuth CR to discover the login-gate group: "
                            "%s — set clusterAccess.group to state it explicitly",
                            cluster.name, exc.message)
                dn = ""
        if dn:
            # Case-insensitively, because DNs are. The operator writes the group's DN into
            # openshift.io/ldap.uid exactly as the directory returns it, while a DN typed into
            # values.yaml or copied out of an AD console is conventionally `CN=...,OU=...,DC=...`.
            # An exact match would report "the gate group is not synced" on a cluster where it is.
            group_name = next(
                (g.name for g in groups if dn_equal(g.ldap_uid, dn)), None)
            store.set_cluster_access_group(cluster.name, dn, source, group_name, observed_at)
        else:
            # No gate at all: no clusterAccess.group, and no membership clause in any identity
            # provider's filter. DELETED rather than left stale — a gate REMOVED from the provider
            # means everyone in the search base can sign in now, and keeping the last known value
            # would go on reporting findings against a group that gates nothing.
            store.clear_cluster_access_group(cluster.name)

        # Provenance for RBAC finding classification: remember which groups the operator
        # manages, so that a binding naming one of them later becomes meaningful evidence
        # rather than an unresolvable name.
        store.record_managed_groups(
            cluster.name,
            [{"name": g.name, "sync_provider": g.sync_provider} for g in groups],
            observed_at,
        )

        # Step 7: reconcile membership and record who joined or left since the last poll.
        # Inside the transaction, and safe to be: a membership event self-heals. If this
        # cycle rolls back, the next one re-derives the identical change with a later
        # observed_at, degrading the timestamp by one poll interval — which values.yaml
        # already documents as the error bar on "when did this person lose access?".
        member_changes = store.sync_members(
            cluster_id=cluster.name,
            memberships={g.name: g.members for g in groups},
            sync_times={g.name: g.group_synced_at for g in groups},
            observed_at=observed_at,
        )

        # Last inside the transaction: OK is only true if everything above committed.
        store.record_poll(cluster.name, OK, None)
    log.info(
        "polled %s: %d CRs, %d groups, %d new sync event(s), %d membership change(s)",
        cluster.name,
        len(crs),
        len(groups),
        new_events,
        member_changes,
    )
    return OK


def refresh_bindings(
    store: StorageBackend,
    cluster: ClusterConfig,
    timeout: float,
    audit_mode: str = "off",
    audit_max_per_cycle: int = 20,
) -> str:
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
                "managed_source": b.managed_source,
                "exception": b.exception,
            }
            for b in bindings
        ],
        now_iso(),
    )

    # Direct-user bindings ride the same cadence and the same two list calls' worth of
    # cluster data. Fetched separately rather than in one pass because the two questions
    # are different — "does this group exist?" vs "why is a person named here?" — and
    # conflating them made both harder to read.
    try:
        user_rows = client.fetch_user_bindings()
    except ClusterError as exc:
        log.warning("user-binding refresh for %s failed: %s — group data is unaffected",
                    cluster.name, exc.message)
    else:
        store.replace_user_bindings(
            cluster.name,
            [{"binding_kind": u.binding_kind, "binding_namespace": u.binding_namespace,
              "binding_name": u.binding_name, "role_kind": u.role_kind,
              "role_name": u.role_name, "user_name": u.user_name,
              "is_platform": 1 if u.is_platform else 0} for u in user_rows],
            now_iso(),
        )
        people = sum(1 for u in user_rows if not u.is_platform)
        log.info("%s: %d direct-user binding(s), %d naming a person",
                 cluster.name, len(user_rows), people)

    # The policy operator's CR health rides the SAME cadence, for the same reason: these
    # CRs change on administrative action, not on a schedule, and they are the source of
    # the very bindings fetched above. Auto-detected — a cluster without the
    # namespace-configuration-operator records "absent" and the UI shows nothing, rather
    # than an empty-but-healthy-looking section.
    try:
        configs = client.fetch_operator_configs()
    except ClusterError as exc:
        log.warning(
            "operator-config refresh for %s failed: %s — binding data is unaffected",
            cluster.name, exc.message,
        )
    else:
        store.replace_operator_configs(
            cluster.name,
            None if configs is None else [
                {"kind": c.kind, "name": c.name, "error_at": c.error_at,
                 "error_message": c.error_message, "success_at": c.success_at}
                for c in configs
            ],
            now_iso(),
        )
        if configs is not None:
            log.info("refreshed %d operator config(s) for %s", len(configs), cluster.name)

    log.info("refreshed %d group bindings for %s", len(bindings), cluster.name)

    # Unmanaged-grant discovery. Runs LAST, after this cycle's rows are stored, so the
    # findings are computed from exactly what was just observed rather than from the previous
    # cycle. Nothing here writes to the cluster.
    # docs/unmanaged-audit-design.md carries the invariants; gsd/audit.py the decisions.
    if audit_mode == "log":
        plan = plan_audit_stamps(store.all_bindings(cluster.name), audit_max_per_cycle)

        # THE DISCOVERY IS THE DELIVERABLE.
        #
        # These lines used to read "WOULD stamp ClusterRoleBinding -/demo-cluster-admin-crb",
        # which framed the log as a rehearsal for a write and told a reader nothing about why
        # the object mattered. The write could never land on a normal cluster — Kubernetes
        # refuses a metadata patch unless the writer already holds everything the binding
        # grants — so the finding IS the product, and it is published here as evidence that
        # stands alone: which object, what it grants, to whom, and why that is a finding.
        if plan.stamp or plan.unstamp or plan.capped:
            log.info(
                # The first number is every finding AWAITING ACKNOWLEDGEMENT, not the number
                # of lines that follow. `plan.stamp` is truncated to maxPerCycle
                # (audit.py:75-77) before this reads its length, so `len(plan.stamp)` alone
                # understated a large finding set — a cluster with 500 unmanaged grants
                # reported "20 outside the policy system", which is the one number an operator
                # escalates on.
                #
                # Not the cluster's total: an object already carrying the unmanaged label is a
                # finding but is not re-announced (audit.py:73). The findings API is the
                # cluster-wide set, which is why this line links it.
                "%s: unmanaged-grant discovery — %d outside the policy system%s, %d resolved "
                "since the last cycle. Full detail: "
                "GET /api/clusters/%s/bindings/findings",
                cluster.name, len(plan.stamp) + plan.capped,
                f" ({len(plan.stamp)} listed below, {plan.capped} held back by the "
                f"per-cycle cap)" if plan.capped else "",
                len(plan.unstamp),
                cluster.name,
            )

        for key in plan.stamp:
            kind, ns, name = key
            evidence = plan.evidence.get(key, {})
            groups = evidence.get("groups") or []
            # WARNING, not INFO. This needs a human, and the poller emits INFO for every
            # routine HTTP call — a finding at INFO is buried by the traffic that surrounds
            # it, and a log pipeline has no level to filter on. The fixed prefix is there to
            # be alerted on.
            log.warning(
                "UNMANAGED GRANT DISCOVERED — %s: %s %s grants %s to group %s, "
                "outside the policy system (no config-source label, no exception annotation)",
                cluster.name, kind,
                f"{ns}/{name}" if ns else f"{name} (cluster-wide)",
                evidence.get("role") or "an unknown role",
                ", ".join(groups) if groups else "an operator-synced group",
            )

        for key in plan.unstamp:
            kind, ns, name = key
            # The good-news direction, and it still works with nothing writing labels.
            #
            # An object reaches this branch because it CARRIES rbac.ocp.io/unmanaged=true and
            # is no longer classified unmanaged. The dashboard never applies that label — an
            # admin or a CI job does, with `oc annotate` — so this is the dashboard telling
            # whoever labelled it that the finding is closed and the label is now stale.
            # Without the line, the only visible signal is a count going down.
            log.info(
                "unmanaged grant RESOLVED — %s: %s %s is no longer outside the policy system "
                "(adopted, annotated as an exception, or its group left management). Its "
                "rbac.ocp.io/unmanaged label is now stale: oc label %s %s "
                "rbac.ocp.io/unmanaged-",
                cluster.name, kind, f"{ns}/{name}" if ns else f"{name} (cluster-wide)",
                kind.lower(), f"-n {ns} {name}" if ns else name,
            )


    return OK


class Poller:
    """Runs one polling thread per enabled cluster."""

    def __init__(self, store: StorageBackend, settings: Settings,
                 elector: LeaderElector | None = None, signals=None):
        self.store = store
        self.settings = settings
        # The process-event metrics seam (gsd/metrics.py RuntimeSignals), duck-typed and
        # optional so this module never imports the metrics module and every existing
        # caller keeps working. Reports poll durations, backup failures and — passed
        # through capture_once — retention deletions.
        self.signals = signals
        # BEST-EFFORT admission control, NOT a write fence. Read this before relying on it.
        #
        # Leadership is checked once, in _run_cluster, before poll_once is entered. Nothing
        # re-checks it during the seven writes that follow, and nothing carries a fence
        # token the store could reject. So a pod that passes the check and then pauses —
        # CPU throttling, a stop-the-world GC, a network partition — can lose the lease,
        # have another pod take over, and still complete every one of its writes on resume.
        # Two pods can also both believe they hold it for up to renew_seconds, because the
        # loser does not clear its own flag until its next round, and expiry is judged
        # against each pod's own clock.
        #
        # What it therefore DOES buy: it stops the ordinary cases — a scale-up, a slow
        # Recreate rollover — from having two steady-state pollers. What it does NOT buy is
        # a guarantee that only one process ever writes. The real protection against that
        # is the deployment shape: one replica, Recreate, one database file.
        #
        # Making it a true fence would mean every store write comparing a monotonic token
        # inside the same transaction, with the new leader advancing it first. That is a
        # distributed-systems protocol layered over SQLite, and it is not proportionate for
        # a single-writer application whose primary defence is that there is only one pod.
        self.elector = elector
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []
        # 0 so the first cycle after start takes one immediately: a pod that
        # has just come up is exactly when you want a copy on disk.
        self._next_backup = 0.0

    def _maybe_backup(self) -> None:
        """Snapshot the irreplaceable history on its own slower schedule.

        Leader-and-poll-thread only, the same rule as maintain(): VACUUM INTO holds a read
        transaction for the length of the copy, and doing that from a request handler would
        put a user's page behind it.

        This is the ONLY protection for data that cannot be re-fetched from the Kubernetes
        API. Everything else here is a cache. Note the honest limit: these land on the same
        PVC they protect against, so they cover corruption and accidental deletion but not
        loss of the volume — shipping them off it is a CronJob's job, not this process's.
        """
        if not self.settings.backup_dir:
            return
        now = time.monotonic()
        if now < self._next_backup:
            return
        self._next_backup = now + self.settings.backup_interval_hours * 3600
        try:
            if (self.store.backup(self.settings.backup_dir, keep=self.settings.backup_keep)
                    is None):
                # None is the method's own failure contract (VACUUM error, unwritable
                # directory) — already logged with the trace in the store; counted here,
                # where the schedule lives, so the exposition can say backups are breaking
                # hours before the last-success timestamp goes stale.
                if self.signals is not None:
                    self.signals.note_backup_failure()
        except Exception:  # noqa: BLE001 - a failed backup must never stop the poll
            if self.signals is not None:
                self.signals.note_backup_failure()
            log.exception("backup failed; the poll continues and the history is unprotected")

    def _run_cluster(self, cluster: ClusterConfig) -> None:
        # Poll immediately on start rather than sleeping first: a restarted dashboard that
        # shows nothing for its first interval is indistinguishable from a broken one.
        next_binding_refresh = 0.0
        while not self._stop.is_set():
            started = datetime.now(UTC)
            if self.elector is not None and not self.elector.is_leader:
                # Standby: serve reads, write nothing. Checked every cycle rather than once,
                # so leadership lost mid-life stops the writes promptly.
                #
                # Re-checked on a SHORT tick, not the poll interval. Leadership is acquired
                # asynchronously by the elector thread, so at startup this thread reliably
                # loses the race and lands here once — and sleeping a full interval then
                # means the first poll is a whole interval late, which defeats the
                # poll-immediately-on-start above. At 60s that was a shrug; at 900s it is a
                # 15-minute blackout after every restart. The wait is free: standby does no
                # I/O, it reads a flag the elector already maintains.
                log.debug("%s: not leader, skipping poll", cluster.name)
                self._stop.wait(min(self.settings.poll_interval_seconds, STANDBY_RECHECK_SECONDS))
                continue
            try:
                poll_started = time.monotonic()
                poll_once(self.store, cluster, self.settings.request_timeout_seconds,
                          access_group_dn=self.settings.cluster_access_group)
                if self.signals is not None:
                    # The whole poll, success or degraded — a poll that needs the full
                    # timeout to fail is the one worth seeing. Set only by the replica
                    # that polls, so standbys emit no series.
                    self.signals.note_poll_duration(
                        cluster.name, time.monotonic() - poll_started)
                # Login capture rides this thread rather than owning one, which is the smallest correct
                # ownership boundary: it inherits the leader gate above and the never-die discipline
                # below without a second lease to reason about. It is AFTER poll_once on purpose —
                # group data is what this dashboard is for, and capture must never delay it.
                #
                # The elector is passed through so capture can RECHECK leadership immediately before
                # its write. The check above is once per cycle, and capture reads logs over the
                # network, so the lease can pass to another replica while a read is in flight.
                try:
                    capture_once(self.store, cluster, self.settings, self.elector,
                                 self.settings.request_timeout_seconds,
                                 signals=self.signals)
                except Exception:  # noqa: BLE001 - capture must never stop the poll loop
                    log.exception("%s: login capture raised; group polling continues", cluster.name)
                # After the write, never during it, and never from a request handler:
                # whatever upkeep the engine needs may wait on open readers, and that wait
                # is free here and would be user-visible latency anywhere else. The poller
                # does not know or care what the engine actually does — for SQLite it is a
                # WAL checkpoint; for another engine it may be nothing at all.
                self.store.maintain()
                self._maybe_backup()
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
                    # THE ONE CRITICAL IN THIS CODEBASE, and it earns the level rather than
                    # decorating it. Reaching here means the poll failed AND the store could not
                    # record that it failed, so the stored outcome keeps whatever it last said —
                    # possibly `ok` — while /healthz is unconditionally green and /readyz only
                    # reads. The dashboard then reports itself healthy and serves frozen data under
                    # a stale success status: not degraded, but actively untruthful, which is what
                    # separates CRITICAL from the ERROR above. It cannot self-heal, because the
                    # thing that failed is the write path the recovery needs.
                    #
                    # log.critical with exc_info rather than log.exception: the traceback is the
                    # only clue to WHY the store is unwritable (a full disk and a locked database
                    # want different responses), and log.exception would pin this at ERROR.
                    log.critical(
                        "could not even record the poll failure for %s, so the stored status is "
                        "now stale and may still read as healthy; the poll loop continues",
                        cluster.name, exc_info=True,
                    )

            # Bindings ride the same thread but on their own due-time, so an expensive
            # cluster-wide binding list does not run every group poll.
            now = time.monotonic()
            if now >= next_binding_refresh:
                try:
                    refresh_bindings(
                        self.store, cluster, self.settings.request_timeout_seconds,
                        audit_mode=self.settings.unmanaged_audit_mode,
                        audit_max_per_cycle=self.settings.unmanaged_audit_max_per_cycle,
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
