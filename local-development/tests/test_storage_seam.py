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
import pathlib

import pytest

from gsd.storage import StorageBackend
from gsd.store import Store

GSD = pathlib.Path(__file__).resolve().parents[1] / "gsd"

# The ONLY module allowed to know what the engine is.
BACKEND = "store.py"

# Anything that names a specific engine or speaks its dialect.
ENGINE_IMPORTS = {"sqlite3", "psycopg", "psycopg2", "asyncpg", "pymysql", "sqlalchemy"}
SQL_VERBS = ("SELECT ", "INSERT ", "UPDATE ", "DELETE FROM", "CREATE TABLE", "PRAGMA ")


def modules():
    """Every application module except the backend itself."""
    return [p for p in sorted(GSD.glob("*.py")) if p.name != BACKEND]


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
        and any(verb in node.value.upper() for verb in SQL_VERBS)
    ]
    assert not offenders, f"{path.name} contains SQL: {offenders}"


class TestContract:
    def test_store_satisfies_the_backend_protocol(self):
        """If Store drifts from the declared contract, a second implementation written
        against that contract would not be a drop-in — which is the whole point."""
        assert isinstance(Store(":memory:"), StorageBackend)

    def test_the_engine_specific_helpers_are_private(self):
        """wal_bytes/maybe_checkpoint/journal_mode were PUBLIC, and the poller and the
        metrics collector both called them — so both knew the database was SQLite. They are
        replaced by maintain() and health(), which say nothing about the engine."""
        store = Store(":memory:")
        try:
            for gone in ("wal_bytes", "maybe_checkpoint"):
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
        assert health["engine"] == "sqlite"
        # A caller reads keys defensively; nothing here may be required to exist.
        assert set(health) >= {"wal_enabled", "wal_bytes", "checkpoint_busy_total"}

    def test_maintain_is_safe_on_an_engine_with_nothing_to_do(self):
        """:memory: has no WAL, so upkeep is a no-op — and must return a dict, not None,
        so callers never have to special-case an engine that had nothing to do."""
        store = Store(":memory:")
        try:
            assert store.maintain() == {}
        finally:
            store.close()
