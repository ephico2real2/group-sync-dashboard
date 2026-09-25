"""The runtime cluster source beside the values list (SPEC_S1 C2, §S1.1). Mutable and locked: the
discovery thread replaces it each cycle; the API and the poll threads read it."""

from __future__ import annotations

import dataclasses
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
        self._blocked: set[str] = set()

    def replace(self, clusters: list[ClusterConfig], findings: list[Finding], *, at: str,
                error: str | None = None, blocked: set[str] | None = None) -> None:
        with self._lock:
            self._discovered = {c.name: c for c in clusters}
            self._findings = list(findings)
            self._blocked = set(blocked or ())
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
        """The values list with the discovered clusters laid over it: a Secret shadows a values entry of the same
        name (C2 — the shadow is reported by the reader as a finding); the host, values[0] enabled, is never replaced
        (the parser refuses a Secret naming it, so nothing here can). A Secret the lookup wrote FOR a mode stanza
        (its token-source is that stanza's credential kind — the reader's "ours") keeps the credential and takes
        the stanza's policy and switch, so an edit of the stanza's visibility, a change of default, or the stanza
        set to `enabled: false` reaches what is served (SPEC_D2b §3.4); an unowned Secret still wins wholesale
        (SPEC_S3). A Secret with no values entry is appended."""
        with self._lock:
            discovered = dict(self._discovered)
            blocked = set(self._blocked)
        out: list[ClusterConfig] = []
        for c in values:
            if c.name in blocked:
                continue
            found = discovered.pop(c.name, None)
            if found is None:
                out.append(c)
            elif c.connection_mode is not None and found.token_source == c.credential_kind:
                # Either side may disable it: the lookup writes the stanza's `enabled` into the Secret.
                out.append(dataclasses.replace(found, visibility=c.visibility, identity=c.identity,
                                               enabled=c.enabled and found.enabled))
            else:
                out.append(found)
        out.extend(c for c in discovered.values() if c.name not in blocked)
        return out
