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
        # SPEC_S4b: the lookup's standing finding per cluster, set by the retriever and cleared when
        # the lookup succeeds or the cluster stops being pending. Separate from `_findings`, which a
        # discovery replaces every cycle — a lookup finding must survive the cycles between attempts.
        self._lookups: dict[str, Finding] = {}

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
            out.extend(self._lookups[name] for name in sorted(self._lookups))
            if self.error:
                out.append(Finding("-", "discovery-failed", self.error))
            return out

    def set_lookup_finding(self, cluster: str, finding: Finding | None) -> None:
        """The lookup's standing finding for one cluster (SPEC_S4b); None clears it."""
        with self._lock:
            if finding is None:
                self._lookups.pop(cluster, None)
            else:
                self._lookups[cluster] = finding

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
