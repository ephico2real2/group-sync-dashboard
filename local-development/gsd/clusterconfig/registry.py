"""The runtime cluster source beside the values list (SPEC_S1 C2, §S1.1). Mutable and locked: the
discovery thread replaces it each cycle; the API and the poll threads read it."""

from __future__ import annotations

import threading

from ..config import ClusterConfig
from .parser import Finding


class ClusterRegistry:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._discovered: dict[str, ClusterConfig] = {}
        self._findings: list[Finding] = []
        self.last_discovery: str | None = None
        self.error: str | None = None
        self.namespace: str | None = None

    def replace(self, clusters: list[ClusterConfig], findings: list[Finding], *, at: str, error: str | None = None) -> None:
        with self._lock:
            self._discovered = {c.name: c for c in clusters}
            self._findings = list(findings)
            self.last_discovery = at
            self.error = error

    def fail(self, at: str, error: str) -> None:
        """A LIST that failed: the previous set stands, the error is the cycle's one finding (C3)."""
        with self._lock:
            self.last_discovery = at
            self.error = error

    def discovered(self) -> list[ClusterConfig]:
        with self._lock:
            return list(self._discovered.values())

    def findings(self) -> list[Finding]:
        with self._lock:
            out = list(self._findings)
            if self.error:
                out.append(Finding("-", "discovery-failed", self.error))
            return out

    def merge(self, values: list[ClusterConfig]) -> list[ClusterConfig]:
        """The values list with the discovered clusters laid over it: a Secret shadows a values entry
        of the same name (C2 — the shadow is reported by the reader as a finding); the host, values[0]
        enabled, is never replaced (the parser refuses a Secret naming it, so nothing here can)."""
        with self._lock:
            discovered = dict(self._discovered)
        out: list[ClusterConfig] = []
        for c in values:
            out.append(discovered.pop(c.name, c))
        out.extend(discovered.values())
        return out
