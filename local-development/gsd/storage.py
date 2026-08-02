"""The storage contract, so the backend can be replaced without touching anything above it.

WHY THIS FILE EXISTS
--------------------
Nothing above the store has ever spoken SQL — callers use domain verbs like
``record_sync_event`` and ``sync_members``, and every one of the 50 SQL statements lives in
``store.py``. That made the codebase *accidentally* decoupled: the shape was right, but it
was protected by convention and enforced by nothing. A single ``import sqlite3`` in
``api.py`` would have ended it and no test would have failed.

This module turns that convention into a contract:

* ``StorageBackend`` declares what the rest of the application is allowed to depend on.
  A second implementation — Postgres, a network service, an in-memory fake — has exactly
  this to satisfy and nothing more.
* ``tests/test_storage_seam.py`` enforces it: no SQL and no engine import outside the
  backend, and ``Store`` must still satisfy this Protocol.

WHAT IS DELIBERATELY *NOT* HERE
-------------------------------
Engine-specific operational concerns. The old public surface exposed ``wal_bytes()``,
``maybe_checkpoint()`` and ``journal_mode`` — three SQLite nouns that the poller and the
metrics collector reached into directly, so both of them knew what the database was. Those
are replaced by two engine-neutral operations:

* ``maintain()`` — "do whatever periodic upkeep your engine needs". SQLite truncates the
  WAL; Postgres would do nothing and return an empty dict.
* ``health()`` — a free-form dict of engine-reported facts, which the collector turns into
  metrics without knowing what produced them.

The metric NAMES stay ``gsd_sqlite_*`` for now, because they are accurate today and because
they appear in shipped alert rules — renaming them is an operator-visible breaking change
that should happen when the engine actually changes, not before. The point of this refactor
is that the change would then be confined to one file (``metrics.py``) instead of requiring
the poller and collector to be rewritten too.

WHAT THIS DOES NOT SOLVE
------------------------
SQLite being single-writer is the premise of the *deployment*: one replica, leader
election, three Helm guards, ``Recreate``, the RWX/RWOP argument, the WAL-on-NFS alert.
None of that is in this contract and none of it is fixed by implementing it. Swapping the
engine is a contained job; deleting the deployment scaffolding it forced is the larger one.
See ``docs/storage-coupling.md``.
"""

from __future__ import annotations

from typing import Any, NotRequired, Protocol, TypedDict, runtime_checkable


class SqliteHealth(TypedDict):
    """What a SQLite backend can report. Nothing else may assume these exist."""

    wal_enabled: bool
    wal_bytes: int
    checkpoint_busy_total: int


class StorageHealth(TypedDict):
    """Engine-reported facts. `engine` is the ONLY key every backend must supply.

    Everything else is namespaced under the engine that produced it, so a collector reads
    `health.get("sqlite")` and finds nothing on a backend that has no WAL — rather than
    reading a top-level `wal_enabled` that is absent and defaulting it to False, which
    means "the filesystem refused WAL and readers now block on every write" and fires an
    alert against a perfectly healthy database.
    """

    engine: str
    sqlite: NotRequired[SqliteHealth]


@runtime_checkable
class StorageBackend(Protocol):
    """Everything the application may ask of its storage.

    Grouped by the concern each method serves rather than alphabetically, because the
    groups are what a second implementation would tackle one at a time.
    """

    # -- lifecycle and upkeep ------------------------------------------------------------

    def close(self) -> None: ...

    def maintain(self) -> None:
        """Periodic upkeep, called from the poll loop after a write cycle.

        Engine-defined and allowed to do nothing. It exists because SQLite's WAL needs a
        checkpoint that must NOT run from a request handler — it waits for open readers,
        and that wait is free on the poller thread and user-visible latency anywhere else.

        Returns nothing, deliberately. An earlier version returned a dict describing what
        it did, which the only caller discarded — an ornamental contract that implied a
        signal it did not carry. The signal that matters, the starved-checkpoint count, is
        cumulative and belongs in health() where a scrape can actually read it.
        """
        ...

    def health(self) -> StorageHealth:
        """Engine-reported operational facts, for metrics and diagnostics.

        Namespaced by engine rather than free-form. The first version returned a flat dict
        and was described as engine-neutral, which it was not: the collector still had to
        know the exact keys `wal_bytes`, `wal_enabled` and `checkpoint_busy_total`, so the
        coupling had merely moved from attribute names to string literals.
        """
        ...

    # -- clusters and poll outcomes ------------------------------------------------------

    def upsert_cluster(self, cluster_id: str, api_url: str, enabled: bool) -> None: ...
    def clusters(self) -> list[dict]: ...
    def record_poll(self, cluster_id: str, status: str, message: str | None) -> None: ...
    def oldest_last_sync(self, cluster_id: str) -> str | None: ...

    # -- GroupSync CRs and their sync history --------------------------------------------

    def record_sync_event(
        self,
        cluster_id: str,
        name: str,
        namespace: str,
        synced_at: str,
        observed_at: str,
        schedule: str | None,
        group_count: int,
    ) -> bool: ...
    def replace_groupsync_state(
        self, cluster_id: str, rows: list[dict], observed_at: str
    ) -> None: ...
    def groupsyncs(self, cluster_id: str) -> list[dict]: ...
    def sync_events(
        self, cluster_id: str, name: str, since: str | None, limit: int
    ) -> list[dict]: ...
    def upsert_reconcile_error(
        self,
        cluster_id: str,
        name: str,
        failed_at: str | None,
        generation: int | None,
        message: str | None,
    ) -> None: ...

    # -- groups and membership -----------------------------------------------------------

    def replace_group_state(
        self, cluster_id: str, rows: list[dict], observed_at: str
    ) -> None: ...
    def groups(self, cluster_id: str, state: str = "all") -> list[dict]: ...
    def group_counts(self, cluster_id: str) -> dict: ...
    def group_detail(self, cluster_id: str, group_name: str) -> dict | None: ...
    def group_members(self, cluster_id: str, group_name: str) -> list[dict]: ...
    def sync_members(
        self,
        cluster_id: str,
        memberships: dict[str, list[str]],
        sync_times: dict[str, str | None],
        observed_at: str,
    ) -> int: ...
    def membership_events(
        self,
        cluster_id: str,
        group_name: str | None = None,
        user_name: str | None = None,
        limit: int = 200,
    ) -> list[dict]: ...
    def users(self, cluster_id: str) -> list[dict]: ...
    def user_groups(self, cluster_id: str, user_name: str) -> list[dict]: ...

    # -- RBAC bindings -------------------------------------------------------------------

    def replace_bindings(
        self, cluster_id: str, rows: list[dict], observed_at: str
    ) -> None: ...
    def record_managed_groups(
        self, cluster_id: str, groups: list[dict], observed_at: str
    ) -> None: ...
    def group_bindings(self, cluster_id: str, group_name: str) -> list[dict]: ...
    def user_bindings(self, cluster_id: str, user_name: str) -> list[dict]: ...
    def binding_findings(self, cluster_id: str) -> list[dict]: ...
    def all_bindings(self, cluster_id: str) -> list[dict]: ...

    # -- dashboard usage -----------------------------------------------------------------

    def record_user_activity(self, buckets: list[dict]) -> int: ...
    def prune_user_activity(self, before_day: str) -> int: ...
    def user_activity(
        self,
        since_day: str | None = None,
        limit: int = 500,
        user_name: str | None = None,
    ) -> list[dict]: ...
    def active_user_count(self, day: str) -> int: ...


def open_backend(settings) -> StorageBackend:
    """Construct the configured backend. The ONE place the application names an engine.

    Before this, `api.py` built a `Store` and passed `busy_timeout_ms`, `synchronous` and
    `wal_checkpoint_mb` — three SQLite tuning knobs — so the only dependency-injection site
    in the app was itself engine-shaped. A backend that does not take those could not be
    constructed without editing the application module, which is exactly what the seam is
    supposed to prevent.

    The Protocol deliberately says nothing about `__init__`: construction differs per engine
    and is this function's problem, not the contract's.
    """
    from .store import Store

    return Store(
        settings.db_path,
        busy_timeout_ms=settings.sqlite_busy_timeout_ms,
        reader_busy_timeout_ms=settings.sqlite_reader_busy_timeout_ms,
        synchronous=settings.sqlite_synchronous,
        wal_checkpoint_mb=settings.sqlite_wal_checkpoint_mb,
    )
