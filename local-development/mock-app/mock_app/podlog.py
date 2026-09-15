"""The pod-log text stream (DESIGN §7.3, endpoint m).

``GET /api/v1/namespaces/<ns>/pods/<pod>/log?timestamps=true`` returns TEXT — each line
prefixed with the kubelet's RFC3339-UTC stamp + a space (``^(\\d{4}-…Z)\\s``, loginlog.py:113).
The fixture supplies whole lines (the timestamp prefix + a klog body) so the author controls
exactly what the klog verdict parser sees.
"""

from __future__ import annotations

from .fixture import PodLogFixture


class PodLogServer:
    def __init__(self, pod_log: PodLogFixture):
        self._pod_log = pod_log

    @property
    def namespace(self) -> str:
        return self._pod_log.namespace

    def body(self) -> bytes:
        """The whole log as bytes — one line per fixture entry, newline-joined."""
        if not self._pod_log.lines:
            return b""
        return ("\n".join(self._pod_log.lines) + "\n").encode("utf-8")
