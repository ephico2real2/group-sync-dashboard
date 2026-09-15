"""Server lifecycle: run the FastAPI app under uvicorn, with an ephemeral TLS certificate.

Two run forms share this class (DESIGN §8):

* **Form A** (pytest fixture): ``port=0`` binds an ephemeral port — parallel-test-safe — and the
  fresh CA's PEM is handed to the dashboard as ``caBundleFile``. ``start()`` blocks until the
  socket is bound and the real port is known.
* **Form B** (container): ``python -m mock_app`` binds ``0.0.0.0:6443`` (see ``__main__``).

TLS is real: the leaf we serve chains to ``ca_pem``, so the dashboard's
``ssl.create_default_context(cafile=ca.crt)`` verifies it with ``CERT_REQUIRED`` + hostname
checking — the enterprise-CA path, not ``insecure_skip_verify`` (DESIGN §4).
"""

from __future__ import annotations

import tempfile
import threading
import time
from pathlib import Path

import uvicorn

from .app import build_app
from .fixture import Fixture
from .tls import CaLeaf, default_sans, generate_ca_and_leaf


class MockClusterServer:
    def __init__(
        self,
        fixture: Fixture,
        host: str = "127.0.0.1",
        port: int = 0,
        tls: bool = True,
        sans: list[str] | None = None,
        ca_leaf: CaLeaf | None = None,
        log_level: str = "warning",
    ):
        self.fixture = fixture
        self.host = host
        self.port = port
        self.tls = tls
        self.sans = sans or default_sans(host)
        self._log_level = log_level
        self._ca_leaf = ca_leaf if ca_leaf is not None else (
            generate_ca_and_leaf(self.sans) if tls else None
        )
        self._app = build_app(fixture)
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._actual_port: int | None = None
        self._certdir: tempfile.TemporaryDirectory | None = None

    # ── lifecycle ───────────────────────────────────────────────────────────────────────────

    def start(self, timeout: float = 10.0) -> None:
        """Bind the socket, wrap it in TLS, and serve on a daemon thread. Blocks until ready."""
        kwargs: dict = dict(
            host=self.host,
            port=self.port,
            log_level=self._log_level,
            access_log=False,
            # Never issue a 3xx for a trailing-slash mismatch — kube.py would fail on it.
            # (build_app already sets redirect_slashes=False on the app.)
        )
        if self.tls:
            if self._ca_leaf is None:  # pragma: no cover - guarded by __init__
                raise RuntimeError("TLS requested but no CA/leaf was generated")
            self._certdir = tempfile.TemporaryDirectory(prefix="mock-openshift-tls-")
            cert_path = Path(self._certdir.name) / "leaf.crt"
            key_path = Path(self._certdir.name) / "leaf.key"
            cert_path.write_bytes(self._ca_leaf.leaf_cert_pem)
            key_path.write_bytes(self._ca_leaf.leaf_key_pem)
            kwargs["ssl_certfile"] = str(cert_path)
            kwargs["ssl_keyfile"] = str(key_path)

        config = uvicorn.Config(self._app, **kwargs)
        self._server = uvicorn.Server(config)
        # uvicorn installs signal handlers only on the main thread; disable so it runs threaded.
        self._server.install_signal_handlers = lambda: None

        self._thread = threading.Thread(target=self._server.run, name="mock-openshift",
                                        daemon=True)
        self._thread.start()

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._server.started and self._server.servers:
                sockets = self._server.servers[0].sockets
                if sockets:
                    self._actual_port = sockets[0].getsockname()[1]
                    return
            time.sleep(0.02)
        self.stop()
        raise TimeoutError(f"mock server did not start within {timeout}s")

    def stop(self, timeout: float = 5.0) -> None:
        if self._server is not None:
            self._server.should_exit = True
        if self._thread is not None:
            self._thread.join(timeout=timeout)
        if self._certdir is not None:
            self._certdir.cleanup()
            self._certdir = None

    def __enter__(self) -> "MockClusterServer":
        self.start()
        return self

    def __exit__(self, *exc) -> None:
        self.stop()

    # ── introspection ───────────────────────────────────────────────────────────────────────

    @property
    def actual_port(self) -> int:
        if self._actual_port is None:
            raise RuntimeError("server not started")
        return self._actual_port

    @property
    def scheme(self) -> str:
        return "https" if self.tls else "http"

    @property
    def base_url(self) -> str:
        host = "127.0.0.1" if self.host in {"0.0.0.0", "::"} else self.host
        return f"{self.scheme}://{host}:{self.actual_port}"

    @property
    def ca_pem(self) -> bytes:
        if self._ca_leaf is None:
            raise RuntimeError("no CA (server is running without TLS)")
        return self._ca_leaf.ca_pem
