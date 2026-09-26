"""Suite-wide guards for local-development/tests.

Standard library and pytest only: CI's chart jobs run tests/test_chart_*.py with nothing but pytest
and PyYAML installed, and this file is loaded for them too.
"""
import os
import threading
import time

import pytest

# The names gsd/poller.py gives its threads: `poll-<cluster>` (_start_cluster_thread) and the
# discovery thread `cluster-secrets` (Poller.start).
_POLLER_THREAD_PREFIXES = ("poll-", "cluster-secrets")
_JOIN_BUDGET_SECONDS = 2.0


def _poller_threads() -> set[threading.Thread]:
    return {t for t in threading.enumerate() if t.name.startswith(_POLLER_THREAD_PREFIXES)}


@pytest.fixture(autouse=True)
def no_leaked_poller_threads():
    """Fail the test that leaves a poller thread running, rather than the later test it corrupts.

    Why: a `poll-host` thread leaked by test_fleet_lookup called a later test's monkeypatched
    ClusterClient and ate one of its scripted cycles, failing that test at random (main CI run 36221028974).

    Absolute, not a delta against the set at test start: a leftover from a previous test (the 2 s
    join did not finish it) or from a higher-scope fixture is still a leak. Nothing in this suite
    keeps a poll-* thread across tests (every module-scoped build_app uses run_poller=False).
    """
    yield
    deadline = time.monotonic() + _JOIN_BUDGET_SECONDS
    found = _poller_threads()
    for thread in found:
        thread.join(max(0.0, deadline - time.monotonic()))
    leaked = sorted(t.name for t in found if t.is_alive())
    if leaked:
        pytest.fail(f"poller thread(s) still running after the test: {', '.join(leaked)} — stop what started them")


# Settings.db_path defaults to the RELATIVE path "gsd.db" (gsd/config.py#Settings), so a test that
# builds Settings without a db_path opens a database in whatever directory pytest runs from: the
# working tree (#371). SQLite adds the -wal and -shm files beside it while a connection is open.
_DEFAULT_DB_FILES = ("gsd.db", "gsd.db-wal", "gsd.db-shm")


def _default_db_state() -> dict[str, tuple[int, int] | None]:
    state: dict[str, tuple[int, int] | None] = {}
    for name in _DEFAULT_DB_FILES:
        try:
            st = os.stat(name)
        except FileNotFoundError:
            state[name] = None
        else:
            state[name] = (st.st_size, st.st_mtime_ns)
    return state


@pytest.fixture(autouse=True)
def no_default_database_in_the_working_directory():
    """Fail the test that writes the default relative database, rather than leave it in the tree.

    Why: one test built Settings without a db_path and left local-development/gsd.db behind on every
    run (#371, measured by a per-test file scan of the whole suite). A reviewer who runs the suite in
    the tree under review changed that tree.

    A delta, not absolute: a developer's checkout may hold a gsd.db from running the app locally, and
    only a file that appears or changes during this test is this test's doing.

    The first failure names the writer. A later test that never opens the file can fail too: with the
    writer unfixed, a full run also failed one that uses its own db_path, on gsd.db changing under it.
    """
    before = _default_db_state()
    yield
    after = _default_db_state()
    written = [name for name in _DEFAULT_DB_FILES if after[name] is not None and after[name] != before[name]]
    if written:
        pytest.fail(f"the test wrote {', '.join(written)} in {os.getcwd()} — give Settings a db_path under tmp_path")
