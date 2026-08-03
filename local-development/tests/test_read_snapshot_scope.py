"""A read snapshot must stay short, and nothing may hold one across I/O.

Holding a read snapshot holds a WAL read-mark, and `wal_checkpoint(TRUNCATE)` cannot
reclaim past the oldest live reader. Measured: a reader held across a checkpoint blocked
it for the full writer busy_timeout and reclaimed zero pages, while the WAL grew from
4.1 MB to 43.0 MB across 2,000 small writes. On a 1 Gi PVC the WAL alert is then the only
thing between a long-held snapshot and a full volume — at which point the poller cannot
write the history at all.

Today every snapshot is 3-13 ms against a 60 s poll, so this is safe. The risk is entirely
what somebody adds later: an `await`, a `yield`, a `StreamingResponse`, an HTTP call to a
cluster. Each turns a millisecond snapshot into one that lasts as long as a response, a
network round trip, or a client's download speed.

This test is why `DashboardCollector.collect` materialises its families inside the snapshot
and yields them outside it — the generator would otherwise be driven lazily by
prometheus_client while writing the response.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

GSD = pathlib.Path(__file__).resolve().parents[1] / "gsd"

# Calls that make a block outlive its own queries. Deliberately specific: an earlier
# version banned bare "get"/"post", which matched every dict.get() in the file and made the
# test useless noise rather than a signal.
BANNED_CALLS = {"StreamingResponse", "FileResponse", "sleep", "iter_content", "aiter_bytes"}
BANNED_ATTR_ROOTS = {"httpx", "requests", "urllib", "socket"}


def _own_nodes(node: ast.AST):
    """Walk `node` but do NOT descend into nested function definitions.

    A nested function has its own lifetime — it is not executing while the snapshot is
    open — so its yields and awaits are irrelevant. Without this, `build_app` (which merely
    CONTAINS every handler) looked like one giant snapshotted function.
    """
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        yield child
        yield from _own_nodes(child)


def _guarded_regions():
    """Every region that executes while a snapshot is held, as (where, label, nodes).

    Two shapes: a function decorated `@consistent` — the whole body is guarded — and the
    BODY OF A `with ...read_snapshot()` block, which is guarded while the rest of its
    enclosing function is not. That distinction is the point: `collect()` deliberately
    gathers inside the block and yields outside it, and must not be failed for the yield.
    """
    out = []
    for path in sorted(GSD.rglob("*.py")):
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and any(
                isinstance(d, ast.Name) and d.id == "consistent" for d in node.decorator_list
            ):
                out.append((path.name, node.name, node.body, node))
            if isinstance(node, ast.With) and any(
                isinstance(i.context_expr, ast.Call)
                and isinstance(i.context_expr.func, ast.Attribute)
                and i.context_expr.func.attr == "read_snapshot"
                for i in node.items
            ):
                out.append((path.name, "with read_snapshot", node.body, None))
    return out


def _snapshotted():
    return [(where, label, body, fn) for where, label, body, fn in _guarded_regions()]


def test_there_are_snapshotted_regions_to_check():
    """A guard on the guard: if the mechanism is renamed this file must not silently pass."""
    regions = _snapshotted()
    assert regions, "found no read_snapshot users — has the mechanism been renamed?"
    labels = {label for _, label, _, _ in regions}
    assert "with read_snapshot" in labels, "metrics no longer gathers under a snapshot"


@pytest.mark.parametrize(
    "where,label,body,fn", _snapshotted(), ids=lambda v: v if isinstance(v, str) else ""
)
class TestSnapshotScope:
    def test_does_not_yield(self, where, label, body, fn):
        """A generator is driven by its consumer, so the snapshot would last as long as the
        response rather than as long as the queries."""
        for stmt in body:
            for n in [stmt, *_own_nodes(stmt)]:
                assert not isinstance(n, (ast.Yield, ast.YieldFrom)), (
                    f"{where}:{label} yields while holding a read snapshot"
                )

    def test_does_not_await(self, where, label, body, fn):
        """An await suspends with the snapshot still open, for as long as whatever it is
        waiting on takes."""
        if fn is not None:
            assert not isinstance(fn, ast.AsyncFunctionDef), f"{where}:{label} is async"
        for stmt in body:
            for n in [stmt, *_own_nodes(stmt)]:
                assert not isinstance(n, ast.Await), (
                    f"{where}:{label} awaits while holding a read snapshot"
                )

    def test_does_no_streaming_or_network_io(self, where, label, body, fn):
        """A streamed response holds the snapshot until the client finishes reading. A
        cluster call holds it for a network round trip."""
        for stmt in body:
            for n in [stmt, *_own_nodes(stmt)]:
                if not isinstance(n, ast.Call):
                    continue
                name = n.func.id if isinstance(n.func, ast.Name) else getattr(n.func, "attr", "")
                assert name not in BANNED_CALLS, (
                    f"{where}:{label} calls {name}() while holding a read snapshot; that "
                    f"pins a WAL read-mark and blocks checkpointing"
                )
                root = n.func
                while isinstance(root, ast.Attribute):
                    root = root.value
                if isinstance(root, ast.Name):
                    assert root.id not in BANNED_ATTR_ROOTS, (
                        f"{where}:{label} performs {root.id} I/O inside a read snapshot"
                    )
