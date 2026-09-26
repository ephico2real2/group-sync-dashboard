"""Suite-wide guards for local-development/tests.

Standard library and pytest only: CI's chart jobs run tests/test_chart_*.py with nothing but pytest
and PyYAML installed, and this file is loaded for them too.
"""
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
