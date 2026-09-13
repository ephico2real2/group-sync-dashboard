"""The one data model every report is built into and every renderer reads.

A report is SECTIONS of BLOCKS — tables, key/value lists, notes — plus the provenance and coverage
facts every report carries. HTML and PDF are two renderings of this structure, which is what makes
the sha256 honest: it is computed over the canonical JSON of the DATA (sections, params, coverage,
totals), never over a rendering and never over the timestamp, so the same data on two days hashes
the same and a PDF can be tied back to its .json by the number printed on page one.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any

#: The caveat the parked design made mandatory on any artefact titled "who has access"
#: (docs/namespace-report-design.md §6). Printed verbatim on every report, never paraphrased.
DIRECT_BINDINGS_CAVEAT = ("direct bindings only; role rules are not evaluated — "
                          "this is not an effective-permissions calculation")
#: What replaces any diagnostic text that could carry a secret (§7.5), so an empty column can
#: never read as "no reason exists" — replaced, not omitted (gsd/api.py#SELF_ALERT_DETAILS).
WITHHELD = "diagnostic text withheld — see the dashboard"


@dataclass
class Table:
    title: str
    columns: list[str]
    rows: list[list[Any]]
    note: str | None = None
    empty_text: str = "none"
    kind: str = "table"


@dataclass
class KeyValues:
    title: str
    items: list[tuple[str, Any]]
    kind: str = "kv"


@dataclass
class Note:
    text: str
    level: str = "note"      # note | warning | caveat
    kind: str = "note"


Block = Table | KeyValues | Note


@dataclass
class Section:
    title: str
    blocks: list[Block] = field(default_factory=list)
    page_break: bool = False


@dataclass
class Report:
    name: str
    title: str
    cluster: str
    api_url: str
    generated_at: str
    generated_by: str
    generated_by_note: str
    run_id: str
    params: dict
    coverage: dict
    provenance: dict           # version, commit, dirty, snapshot stamp/age, schema, marking, font/variant
    totals: dict
    truncated: bool
    include_members: bool
    sections: list[Section]
    sha256: str = ""

    def canonical(self) -> dict:
        """The DATA, and only the data: what two runs over the same snapshot must agree on."""
        return {
            "name": self.name, "cluster": self.cluster, "params": self.params, "coverage": self.coverage,
            "totals": self.totals, "truncated": self.truncated, "include_members": self.include_members,
            "sections": [asdict(s) for s in self.sections],
        }

    def seal(self) -> "Report":
        self.sha256 = hashlib.sha256(
            json.dumps(self.canonical(), sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        ).hexdigest()
        return self

    def to_json(self) -> str:
        """The .json artefact: the canonical data plus the run facts, and the hash of the former."""
        doc = {**self.canonical(), "title": self.title, "api_url": self.api_url,
               "generated_at": self.generated_at, "generated_by": self.generated_by,
               "generated_by_note": self.generated_by_note, "run_id": self.run_id,
               "provenance": self.provenance, "sha256": self.sha256}
        return json.dumps(doc, indent=2, sort_keys=True, default=str)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
