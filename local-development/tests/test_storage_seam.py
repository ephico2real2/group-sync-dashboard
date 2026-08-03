"""The storage seam, enforced rather than assumed.

docs/storage-coupling.md used to end with this caveat:

    There is no Protocol, ABC, or interface today. The decoupling is a property of how the
    code is *used*, protected by convention and enforced by nothing. A single
    `import sqlite3` in `api.py` would end it and no test would fail.

This file is that test. It fails the moment somebody reaches around the backend, which is
the only thing that keeps a second implementation possible.
"""

from __future__ import annotations

import ast
import contextlib
import inspect
import pathlib

import pytest

from gsd.storage import StorageBackend
from gsd.store import Store

GSD = pathlib.Path(__file__).resolve().parents[1] / "gsd"

# The ONLY module allowed to know what the engine is.
BACKEND = "store.py"

# Anything that names a specific engine or speaks its dialect.
ENGINE_IMPORTS = {
    "sqlite3", "aiosqlite", "apsw",
    "psycopg", "psycopg2", "asyncpg",
    "pymysql", "MySQLdb", "sqlalchemy",
}
# SQL SHAPES, not substrings. The first version matched bare "SELECT" anywhere, which
# flagged the word "selectable" in a docstring — prose about selecting is not a query.
# Whitespace is collapsed before matching, so "SELECT\n  * FROM x" is still caught.
import re as _re

SQL_SHAPES = tuple(_re.compile(pat) for pat in (
    r"\bSELECT\s+.+\bFROM\b",
    r"\bINSERT\s+INTO\b",
    r"\bUPDATE\s+\w+\s+SET\b",
    r"\bDELETE\s+FROM\b",
    r"\bCREATE\s+TABLE\b",
    r"\bPRAGMA\s+\w+",
))


def modules():
    """Every application module except the backend itself.

    rglob, not glob: a subpackage such as gsd/db/queries.py would otherwise never be
    looked at, and "put the SQL in a subdirectory" is the first thing anyone tries.
    """
    return [p for p in sorted(GSD.rglob("*.py")) if p.name != BACKEND]


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_module_imports_a_database_driver(path):
    """A driver import outside the backend is the seam breaking.

    Checked with the AST rather than a grep, so it sees `import sqlite3`,
    `from sqlite3 import connect` and `import sqlite3 as db` alike, and is not fooled by
    the word appearing in a comment or docstring — which it legitimately does, a lot.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module.split(".")[0])
        # Dynamic imports, which the plain Import/ImportFrom walk cannot see:
        #     sqlite3 = __import__("sqlite3")
        #     sqlite3 = importlib.import_module("sqlite3")
        # Both were a clean bypass of the original check.
        elif isinstance(node, ast.Call):
            name = None
            if isinstance(node.func, ast.Name):
                name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                name = node.func.attr
            if name in ("__import__", "import_module") and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.add(first.value.split(".")[0])
    leaked = found & ENGINE_IMPORTS
    assert not leaked, (
        f"{path.name} imports {leaked}. Storage engines belong behind gsd/storage.py — "
        f"only {BACKEND} may know what the database is."
    )


@pytest.mark.parametrize("path", modules(), ids=lambda p: p.name)
def test_no_module_writes_sql(path):
    """SQL outside the backend is the same leak wearing different clothes.

    Only string literals are examined; the prose in these files discusses SELECT and
    PRAGMA constantly and must stay free to.
    """
    tree = ast.parse(path.read_text(), filename=str(path))
    offenders = [
        node.value[:60]
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and any(shape.search(" ".join(node.value.upper().split())) for shape in SQL_SHAPES)
    ]
    assert not offenders, f"{path.name} contains SQL: {offenders}"


def test_the_enforcement_documents_what_it_cannot_catch():
    """Honest framing beats false confidence.

    This is a lint, not a sandbox. A determined author can still route around it — the
    known holes are listed here so nobody mistakes a green suite for a guarantee:

    * SQL assembled by concatenation, so no single literal contains a verb
      (``"SEL" + "ECT * FROM cluster"``).
    * SQL read from a file, a template or a constant defined outside ``gsd/``.
    * A driver reached through an already-imported module
      (``import gsd.store; gsd.store.sqlite3``).

    What it does catch is the realistic accident: somebody adds ``import sqlite3`` to a
    module because it was quicker than adding a store method. That is the failure mode
    that actually erodes a seam, and it is now impossible to merge quietly.
    """
    assert True


def _protocol_members(proto) -> set[str]:
    """The method names a Protocol declares, on every supported Python.

    NOT `proto.__protocol_attrs__`. That is a CPython private attribute added in 3.12, so the
    two tests below passed on a 3.13 developer machine and failed CI on 3.11 with
    AttributeError — a portability bug in the test, not in the code it guards. Reading the
    class dict works everywhere and does not depend on an implementation detail that may move
    again. Verified equivalent: both yield the same 43 names on 3.13.
    """
    return {name for name, value in vars(proto).items()
            if callable(value) and not name.startswith("_")}


class TestContract:
    def test_store_satisfies_the_backend_protocol(self):
        """Presence only. isinstance() on a runtime_checkable Protocol checks that the
        attribute NAMES exist and nothing else — a class whose every method takes zero
        arguments passes this. The two tests below are what actually hold the seam."""
        assert isinstance(Store(":memory:"), StorageBackend)

    def test_the_protocol_declares_every_method_the_application_calls(self):
        """The drift this catches was real: six methods across eleven call sites —
        read_snapshot, poll_snapshot, backup, operator_configs, replace_operator_configs,
        count_direct_user_bindings — were used on StorageBackend-typed objects while absent
        from the contract. read_snapshot is the @consistent decorator's whole mechanism and
        poll_snapshot is the poll's atomicity, so a backend written to the contract as
        declared would have had neither."""
        declared = _protocol_members(StorageBackend)
        missing: dict[str, list[str]] = {}
        for name in ("api.py", "metrics.py", "poller.py", "activity.py"):
            tree = ast.parse((GSD / name).read_text(), filename=name)
            for node in ast.walk(tree):
                target = None
                # store.foo(...)
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                        and node.value.id == "store":
                    target = node
                # self.store.foo(...)
                elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Attribute) \
                        and isinstance(node.value.value, ast.Name) \
                        and node.value.value.id == "self" and node.value.attr == "store":
                    target = node
                if target is not None and target.attr not in declared:
                    missing.setdefault(target.attr, []).append(f"{name}:{target.lineno}")
        assert not missing, (
            f"called on the backend but not declared in StorageBackend: {missing}. "
            f"A second implementation would AttributeError on the first request."
        )

    def test_the_declared_signatures_match_the_implementation(self):
        """isinstance() cannot see this. `users` gained a `limit` and
        `direct_user_bindings` gained namespace/limit/offset in the store while the
        Protocol kept the old shape, so api.py's calls would TypeError against any
        backend that implemented the contract as written.

        PARAMETERS ONLY, and deliberately. A caller breaks on the arguments it passes, which
        is the drift worth failing over. Return annotations legitimately differ for the
        @contextmanager methods: read_snapshot and poll_snapshot are generators annotated
        `Iterator[None]`, and the decorator hands the caller an AbstractContextManager — the
        Protocol declares what a caller RECEIVES, the implementation annotates the
        undecorated generator. Both are right, and comparing the two strings would fail
        forever on a difference that cannot break anybody.
        """
        def params(fn) -> str:
            return str(inspect.signature(fn).parameters)

        drifted = {
            name: (params(getattr(StorageBackend, name)), params(getattr(Store, name)))
            for name in sorted(_protocol_members(StorageBackend))
            if params(getattr(StorageBackend, name)) != params(getattr(Store, name))
        }
        assert not drifted, f"Protocol and Store parameters disagree: {drifted}"

    def test_the_engine_specific_helpers_are_private(self):
        """wal_bytes/maybe_checkpoint/journal_mode were PUBLIC, and the poller and the
        metrics collector both called them — so both knew the database was SQLite. They are
        replaced by maintain() and health(), which say nothing about the engine."""
        store = Store(":memory:")
        try:
            # journal_mode and checkpoint_busy_total were missed the first time: the
            # methods were privatised but these two ATTRIBUTES stayed public, so the claim
            # "the three SQLite nouns are private" was wrong for two of them.
            for gone in ("wal_bytes", "maybe_checkpoint",
                         "journal_mode", "checkpoint_busy_total"):
                assert not hasattr(store, gone), (
                    f"Store.{gone}() is public again; the poller/collector can reach "
                    f"SQLite internals through it"
                )
            assert callable(store.maintain) and callable(store.health)
        finally:
            store.close()

    def test_health_reports_without_leaking_the_engine_into_the_call(self):
        """The collector must be able to export this without knowing what produced it."""
        store = Store(":memory:")
        try:
            health = store.health()
        finally:
            store.close()
        assert isinstance(health, dict)
        # `engine` is the only key any backend must supply; its facts are namespaced under
        # it. See TestHealthIsNamespaced for why the flat version was unsafe.
        assert health["engine"] == "sqlite"
        assert set(health["sqlite"]) >= {"wal_enabled", "wal_bytes", "checkpoint_busy_total"}

    def test_a_backend_without_a_wal_emits_no_wal_metrics(self):
        """The false-alarm case. A server-based engine reports no wal_* keys, and the
        collector must omit those series rather than invent a 0 that means
        'the filesystem refused WAL and readers now block on every write'."""
        from datetime import timedelta
        from prometheus_client import generate_latest
        from gsd.metrics import build_registry

        class _NoWal:
            # A minimal backend, which is the point: it implements only what the collector
            # is allowed to need. read_snapshot is part of that surface now.
            @contextlib.contextmanager
            def read_snapshot(self):
                yield
            def health(self):
                return {"engine": "postgres"}
            def clusters(self):
                return []

        text = generate_latest(build_registry(_NoWal(), timedelta(minutes=2))).decode()
        for series in ("gsd_sqlite_wal_bytes", "gsd_sqlite_wal_enabled",
                       "gsd_sqlite_checkpoint_busy_total"):
            assert series not in text, f"{series} invented for an engine that has no WAL"

    def test_a_failing_health_omits_the_series_rather_than_zeroing_them(self):
        """Reporting a failure to measure as a measurement of failure is the worst
        available answer: wal_enabled=0 fires GroupSyncDashboardWalDisabled. Omitting
        leaves Prometheus holding the last good value."""
        from datetime import timedelta
        from prometheus_client import generate_latest
        from gsd.metrics import build_registry

        class _Broken:
            @contextlib.contextmanager
            def read_snapshot(self):
                yield
            def health(self):
                raise RuntimeError("storage unavailable")
            def clusters(self):
                return []

        text = generate_latest(build_registry(_Broken(), timedelta(minutes=2))).decode()
        assert "gsd_sqlite_wal_enabled" not in text, "a broken store reported WAL as disabled"
        assert "gsd_build_info" in text, "the rest of the scrape should still succeed"

    def test_maintain_is_safe_on_an_engine_with_nothing_to_do(self):
        """:memory: has no WAL, so upkeep is a no-op — and must not raise."""
        store = Store(":memory:")
        try:
            assert store.maintain() is None
        finally:
            store.close()


class TestConsumersDependOnTheContract:
    """Both reviewers landed on the same point: a Protocol nobody is typed against is
    decoration. `StorageBackend` was declared, then every consumer went on annotating the
    concrete `Store`, so a second backend would have violated those annotations even while
    satisfying the contract.
    """

    CONSUMERS = ("poller.py", "metrics.py", "activity.py", "api.py")

    @pytest.mark.parametrize("name", CONSUMERS)
    def test_no_consumer_annotates_the_concrete_store(self, name):
        source = (GSD / name).read_text()
        tree = ast.parse(source, filename=name)
        offenders = []
        for node in ast.walk(tree):
            if isinstance(node, ast.arg) and isinstance(node.annotation, ast.Name):
                if node.annotation.id == "Store":
                    offenders.append(f"{node.arg}: Store")
        assert not offenders, (
            f"{name} depends on the concrete backend: {offenders}. "
            f"Annotate StorageBackend so a second implementation is substitutable."
        )

    @pytest.mark.parametrize("name", CONSUMERS)
    def test_no_consumer_constructs_a_backend(self, name):
        """Construction is storage.open_backend()'s job. api.py used to build a Store and
        pass four SQLite tuning knobs, so the only DI site in the app was engine-shaped."""
        tree = ast.parse((GSD / name).read_text(), filename=name)
        built = [
            n.func.id for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name) and n.func.id == "Store"
        ]
        assert not built, f"{name} constructs Store directly; use storage.open_backend()"


class TestHealthIsNamespaced:
    def test_engine_facts_are_not_top_level(self):
        """A flat dict was described as engine-neutral and was not — the collector still
        had to know `wal_bytes` and `wal_enabled` by name. Worse, a backend without a WAL
        omits `wal_enabled`, and a defaulting reader turns that absence into False, which
        means 'the filesystem refused WAL' and fires an alert on a healthy database."""
        store = Store(":memory:")
        try:
            health = store.health()
        finally:
            store.close()
        assert set(health) == {"engine", "sqlite"}, (
            "engine facts leaked to the top level, where a caller cannot tell an absent "
            "key from a false one"
        )
        assert set(health["sqlite"]) == {"wal_enabled", "wal_bytes", "checkpoint_busy_total"}

    def test_maintain_returns_nothing(self):
        """It briefly returned a dict the only caller discarded — a contract implying a
        signal it did not deliver. The durable signal is in health()."""
        store = Store(":memory:")
        try:
            assert store.maintain() is None
        finally:
            store.close()
