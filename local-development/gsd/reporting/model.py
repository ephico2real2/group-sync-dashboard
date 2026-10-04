"""The one data model every report is built into and every renderer reads.

A report is SECTIONS of BLOCKS — tables, key/value lists, notes — plus the provenance and coverage
facts every report carries. HTML and PDF are two renderings of this structure, and the sha256 is
computed over the canonical JSON of the DATA: the sealed sections, the parameters, the coverage, the
totals, the cluster, and the snapshot the data was read from (its stamp, its schema, how the
cluster's last poll before it ended). Page one's facts of the run — when, by whom, under which run
id or release, how old the snapshot was, the chart's marking or binding interval — are outside it,
so two runs over one snapshot with the same parameters hash the same whoever runs them, except where
a report's own data is computed against the generation clock (a window, a cutoff, an overdue state:
SPEC_F1, Orchestrator's notes 1): those agree only while the clock-derived values coincide. The
coverage can also reflect two report-service settings (`login_capture_enabled`,
`namespaces_read_enabled`), so a run under other settings is other evidence. A PDF can be tied back
to its .json by the number printed on page one. Page one states the run and is not sealed; what it
shows that is data is sealed through its own field. A new snapshot is new evidence even when no row
changed: its stamp and its coverage are sealed, so the hash answers
"is this the same evidence?", not "did access change?" (docs/specs/SPEC_F1_data_only_seal.md).
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
    #: False for a section that states facts of the RUN (page one): rendered like any other and
    #: written into the .json, but left out of the sha256 (SPEC_F1, #270).
    sealed: bool = True


#: The provenance facts that describe the DATA rather than the run: which snapshot it was read from,
#: that snapshot's schema, and how the cluster's last poll before it ended. Every run over one
#: snapshot reads the same values, so they are sealed; the rest of `provenance` is the run's.
SEALED_PROVENANCE = ("snapshot_stamp", "snapshot_schema_version", "last_poll", "poll_status", "poll_message")
#: The top-level fields in the canonical data. Kept here with the hashing recipe so every consumer
#: verifies a stored .json exactly as Report.seal() wrote it.
CANONICAL_FIELDS = ("name", "cluster", "api_url", "params", "coverage", "totals", "truncated",
                    "include_members", "sealed_provenance")


def canonical_sha256(canonical: dict) -> str:
    """Hash canonical report data with the one serialization recipe used by the model."""
    return hashlib.sha256(
        json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    ).hexdigest()


def recompute_sha256(doc: dict) -> str | None:
    """Recompute a stored .json's seal, or return None when it is not a post-SPEC_F1 document.

    Page one must be the first and only unsealed section; otherwise unchecked data would sit beside
    the seal. This is shared by the service, report-diff and the e2e integrity walk.
    """
    try:
        flags = [section.get("sealed") for section in doc["sections"]]
        if "sealed_provenance" not in doc or flags[:1] != [False] or not all(flags[1:]):
            return None
        canonical = {key: doc[key] for key in CANONICAL_FIELDS}
        canonical["sections"] = doc["sections"][1:]
    except (AttributeError, KeyError, TypeError):
        return None
    return canonical_sha256(canonical)


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
        """The DATA, and only the data: what two runs over one snapshot with the same parameters agree
        on while the values a report computes against the generation clock coincide (the module
        docstring). A section marked `sealed=False` (page one, the run's facts) is left out; what page
        one shows that is data is here through its own key: the cluster and its API URL, the snapshot facts, the
        coverage, the parameters and the rosters switch. Every key is in the .json, so the hash can be
        recomputed from the .json alone by keeping the sections whose `sealed` is true."""
        return {
            "name": self.name, "cluster": self.cluster, "api_url": self.api_url, "params": self.params,
            "coverage": self.coverage, "totals": self.totals, "truncated": self.truncated,
            "include_members": self.include_members,
            "sealed_provenance": {key: self.provenance.get(key) for key in SEALED_PROVENANCE},
            "sections": [asdict(s) for s in self.sections if s.sealed],
        }

    def seal(self) -> "Report":
        self.sha256 = canonical_sha256(self.canonical())
        return self

    def to_json(self) -> str:
        """The .json artefact: the canonical data plus the run facts, and the hash of the former.
        `sections` is every section, page one included, each with its `sealed` flag: the renderers and
        the PDF/A attachment read the whole report, the hash covers the sealed ones."""
        doc = {**self.canonical(), "sections": [asdict(s) for s in self.sections],
               "title": self.title, "api_url": self.api_url,
               "generated_at": self.generated_at, "generated_by": self.generated_by,
               "generated_by_note": self.generated_by_note, "run_id": self.run_id,
               "provenance": self.provenance, "sha256": self.sha256}
        return json.dumps(doc, indent=2, sort_keys=True, default=str)


def iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
