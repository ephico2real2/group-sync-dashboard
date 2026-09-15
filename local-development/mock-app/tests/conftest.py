"""Shared pytest fixtures: start the mock on an ephemeral TLS port and hand back a
ClusterConfig the real ``gsd.ClusterClient`` can drive (DESIGN §8.1).

The suite exercises the REAL client over REAL verified TLS — the coverage ``httpx.MockTransport``
cannot give. ``gsd`` must be importable; when this package is checked out at
``local-development/mock-app`` the sibling ``local-development`` (holding ``gsd/``) is added to
``sys.path`` as a fallback, or point ``GSD_LOCAL_DEV`` at it.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

# ── make `gsd` importable ─────────────────────────────────────────────────────────────────
try:  # already installed (CI does `pip install -e .` of the dashboard)
    import gsd  # noqa: F401
except ModuleNotFoundError:  # fall back to a sibling source tree
    candidates = []
    if os.environ.get("GSD_LOCAL_DEV"):
        candidates.append(Path(os.environ["GSD_LOCAL_DEV"]))
    # committed layout: local-development/mock-app/tests/ → local-development/
    candidates.append(Path(__file__).resolve().parents[2])
    # scratchpad layout: point at the repo's local-development explicitly if present
    candidates.append(
        Path("/Users/olasumbo/gitRepos/group-sync-dashboard/local-development")
    )
    for c in candidates:
        if (c / "gsd" / "__init__.py").exists():
            sys.path.insert(0, str(c))
            break

from gsd.config import ClusterConfig  # noqa: E402

from mock_app.fixture import Fixture  # noqa: E402
from mock_app.server import MockClusterServer  # noqa: E402

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures"


@dataclass
class MockHandle:
    base_url: str
    token: str
    ca_file: str
    server: MockClusterServer
    fixture: Fixture

    def cluster_config(self, name: str = "mock", *, token_env: str = "GSD_MOCK_TOKEN",
                       insecure: bool = False, use_trusted_ca_env: bool = False,
                       ca_bundle: str | None = "__default__") -> ClusterConfig:
        """Build a ClusterConfig pointed at this mock.

        Default: mode-2 trust (``ca_bundle_file`` = the ephemeral CA). Pass ``insecure=True`` for
        the verify-off escape hatch, or ``use_trusted_ca_env=True`` + set ``GSD_TRUSTED_CA_FILE``
        for the mode-3 enterprise fallback (then pass ``ca_bundle=None``).
        """
        os.environ[token_env] = self.token
        bundle = self.ca_file if ca_bundle == "__default__" else ca_bundle
        return ClusterConfig(
            name=name,
            api_url=self.base_url,
            token_env=token_env,
            ca_bundle_file=None if (insecure or use_trusted_ca_env) else bundle,
            insecure_skip_verify=insecure,
        )


def _start(fixture_name: str, tmp_path: Path) -> MockHandle:
    fixture = Fixture.from_yaml(FIXTURE_DIR / fixture_name)
    server = MockClusterServer(fixture, host="127.0.0.1", port=0, tls=True)
    server.start()
    ca_path = tmp_path / "ca.crt"
    ca_path.write_bytes(server.ca_pem)
    return MockHandle(
        base_url=server.base_url,
        token=fixture.token,
        ca_file=str(ca_path),
        server=server,
        fixture=fixture,
    )


@pytest.fixture
def mock_cluster(tmp_path):
    """The reference cluster on an ephemeral TLS port; CA written for the dashboard."""
    handle = _start("reference.yaml", tmp_path)
    try:
        yield handle
    finally:
        handle.server.stop()
        _clear_ca_cache()


@pytest.fixture
def mock_factory(tmp_path):
    """Start any fixture by name; caller stops nothing (torn down here)."""
    started: list[MockHandle] = []

    def make(fixture_name: str) -> MockHandle:
        sub = tmp_path / fixture_name.replace(".", "_")
        sub.mkdir(exist_ok=True)
        handle = _start(fixture_name, sub)
        started.append(handle)
        return handle

    try:
        yield make
    finally:
        for h in started:
            h.server.stop()
        _clear_ca_cache()


def _clear_ca_cache() -> None:
    """§4.3 stale-context guard: the module-global CA cache is keyed on the raw env string and
    never caches a null result, so a matrix reusing GSD_TRUSTED_CA_FILE must clear it."""
    try:
        import gsd.config as gsd_config
        with gsd_config._ca_cache_lock:  # noqa: SLF001
            gsd_config._ca_cache.clear()  # noqa: SLF001
    except Exception:
        pass
    os.environ.pop("GSD_TRUSTED_CA_FILE", None)
