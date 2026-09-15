"""The oauth-server audit-log served over the kubelet node-log proxy (DESIGN §7).

Two node-proxy shapes:

* directory listing (endpoint n) — HTML with ``<a href="…">`` entries, one per file. The
  dashboard parses it with ``href="([^"?#]+)"`` (kube.py:1201), so a bare ``<pre>`` of anchors
  is enough — no size or mtime (which is why the dashboard's cursor is name + byte-offset).
* file read (endpoint o) — raw bytes, Range-aware: ``200`` full, ``206`` partial with
  ``Content-Range``, ``416`` with ``Content-Range: bytes */<size>`` at/after EOF (parsed by
  ``_content_range_total``, kube.py:455). A ``416`` WITHOUT a parseable Content-Range makes the
  client retry once unranged — the fixture's ``malformed416`` flag exercises that path.

Each fixture ``AuditLine`` is expanded into a full Kubernetes-audit JSON event that
``gsd/auditlog.py::parse_audit_line`` (lines 152-222) accepts — the fixture author writes
shorthand, never the envelope.
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass

from .fixture import AuditFixture, AuditLine

# Rotated backup files sort before the live audit.log (lumberjack form); the dashboard reads
# rotated-ascending then audit.log. This mirrors gsd/auditlog.py's ROTATED regex.
_ROTATED = re.compile(r"^audit-(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})\.(\d+)\.log$")

_RANGE = re.compile(r"^\s*bytes=(\d+)-(\d*)\s*$")


@dataclass
class AuditResponse:
    status: int
    headers: dict[str, str]
    body: bytes


@dataclass
class Range:
    start: int
    end: int | None       # inclusive; None = open-ended ("bytes=<start>-")


def parse_range(header: str | None) -> Range | None:
    """Parse a single-range ``bytes=<start>-[<end>]`` header, or None if absent/unparseable."""
    if not header:
        return None
    m = _RANGE.match(header)
    if not m:
        return None
    start = int(m.group(1))
    end = int(m.group(2)) if m.group(2) else None
    return Range(start=start, end=end)


class AuditServer:
    def __init__(self, audit: AuditFixture):
        self._audit = audit
        self._by_name: dict[str, bytes] = {
            f.name: self._render_file(f.lines) for f in audit.files
        }

    # ── endpoint (n): directory listing ─────────────────────────────────────────────────────

    def files_in_order(self) -> list[str]:
        """Rotated files first (ascending), then the live ``audit.log`` — the read order the
        dashboard walks. Any non-rotated, non-live name keeps fixture order at the end."""
        rotated = sorted(
            (n for n in self._by_name if _ROTATED.match(n)),
            key=lambda n: _ROTATED.match(n).groups(),
        )
        live = [n for n in self._by_name if n == "audit.log"]
        other = [n for n in self._by_name if n not in rotated and n not in live]
        return rotated + other + live

    def listing_html(self) -> bytes:
        """A kubelet ``http.FileServer`` directory listing — one anchor per file."""
        anchors = "\n".join(
            f'<a href="{name}">{name}</a>' for name in self.files_in_order()
        )
        html = f"<pre>\n{anchors}\n</pre>\n"
        return html.encode("utf-8")

    # ── endpoint (o): file read ─────────────────────────────────────────────────────────────

    def has_file(self, filename: str) -> bool:
        return filename in self._by_name

    def size(self, filename: str) -> int:
        return len(self._by_name.get(filename, b""))

    def read(self, filename: str, rng: Range | None) -> AuditResponse:
        """Serve one audit file, honouring a byte Range exactly as the kubelet proxy does."""
        if filename not in self._by_name:
            return AuditResponse(404, {"Content-Type": "text/plain"}, b"file not found\n")

        data = self._by_name[filename]
        total = len(data)

        if rng is None:
            return AuditResponse(
                200,
                {"Content-Type": "text/plain; charset=utf-8", "Content-Length": str(total),
                 "Accept-Ranges": "bytes"},
                data,
            )

        # A Range whose first byte is at or past EOF is unsatisfiable → 416 + Content-Range.
        if rng.start >= total:
            if self._audit.malformed_416:
                # Deliberately omit Content-Range to exercise the client's unranged retry.
                return AuditResponse(416, {"Content-Type": "text/plain"}, b"")
            return AuditResponse(
                416,
                {"Content-Range": f"bytes */{total}", "Content-Type": "text/plain"},
                b"",
            )

        end = total - 1 if rng.end is None else min(rng.end, total - 1)
        chunk = data[rng.start:end + 1]
        return AuditResponse(
            206,
            {
                "Content-Type": "text/plain; charset=utf-8",
                "Content-Range": f"bytes {rng.start}-{end}/{total}",
                "Content-Length": str(len(chunk)),
                "Accept-Ranges": "bytes",
            },
            chunk,
        )

    # ── shorthand → Kubernetes-audit JSON ────────────────────────────────────────────────────

    def _render_file(self, lines: tuple[AuditLine, ...]) -> bytes:
        return ("".join(self.expand_line(ln) + "\n" for ln in lines)).encode("utf-8")

    def expand_line(self, line: AuditLine) -> str:
        """Expand one shorthand into a single Kubernetes-audit event JSON line (DESIGN §7.2).

        Matches gsd/auditlog.py::parse_audit_line: top-level ``kind==Event``,
        ``stage==ResponseComplete``, the two ``authentication.openshift.io/*`` annotations, and a
        request shape keyed on ``verb`` + ``requestURI``.
        """
        request_uri, verb = self._request_shape(line)
        annotations = {
            "authentication.openshift.io/username": line.user,
            "authentication.openshift.io/decision": line.decision,
        }
        response_status: dict = {"code": line.code}
        if line.error_message is not None:
            response_status["message"] = line.error_message
        event = {
            "kind": "Event",
            "apiVersion": "audit.k8s.io/v1",
            "level": "Metadata",
            "auditID": line.audit_id or str(uuid.uuid4()),
            "stage": "ResponseComplete",
            "requestURI": request_uri,
            "verb": verb,
            # The parser deliberately ignores user.username (it is system:anonymous on a login)
            # and reads the annotation instead.
            "user": {"username": "system:anonymous"},
            "userAgent": line.user_agent,
            "responseStatus": response_status,
            "requestReceivedTimestamp": line.at,
            "stageTimestamp": line.at,
            "annotations": annotations,
        }
        return json.dumps(event, separators=(",", ":"))

    @staticmethod
    def _request_shape(line: AuditLine) -> tuple[str, str]:
        kind = line.kind
        if kind == "credential":
            uri = f"/login/{line.provider}" if line.provider else "/login"
            return uri, "post"
        if kind == "cli":
            return "/oauth/authorize?client_id=openshift-challenging-client", "get"
        if kind == "session":
            return "/oauth/authorize?client_id=console", "get"
        raise ValueError(f"unknown audit line kind {kind!r} (use credential|cli|session)")
