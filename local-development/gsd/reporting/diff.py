"""What changed between two runs of one report on one cluster (#108, docs/specs/SPEC_F3_report_diff.md).

A diff reads two stored `.json` artefacts, never the snapshot, and compares their SEALED data only
(SPEC_F1): page one states the run, so it is left out, and two runs over one snapshot diff to
"No change": a report's data ends at the snapshot's stamp (#592). Stable coverage conclusions,
every table, key-value list and the notes of each sealed section are compared as a multiset of whole
rows: a row present in the head and not the base is added, the reverse is removed, and a changed cell
is one row removed
and one added (v1). The result is an ordinary `Report` named `report-diff`, sealed, stored and
rendered like any other run, and kept out of the catalogue (`REGISTRY`).
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import datetime

from .. import __version__
from .artifacts import ArtifactStore, Run
from .catalogue.common import ValidationError
from .config import ReportSettings
from .model import KeyValues, Note, Report, Section, Table, iso, recompute_sha256

#: The run name a diff is requested and stored under. Not a catalogue entry, so the catalogue stays eleven.
DIFF_REPORT = "report-diff"
#: The wording of a diff with nothing to show; the page and the walk look for it.
NO_CHANGE = "No change"
#: Stable coverage conclusions. The omitted *_note and history-retained fields carry read-cycle
#: instants, so comparing those would make an otherwise identical pair change on every poll.
COVERAGE_FIELDS = (("Namespace read", "namespaces_read"), ("User read", "users_read"),
                   ("Login capture", "login_capture"), ("Attests absence", "attests_absence"))


def diff_params(store: ArtifactStore, params: dict, cluster: str | None) -> dict:
    """The diff's parameters, checked at request time: two known, finished runs of one report on the
    named cluster, neither a diff, both with their `.json` still on disk. The answer records both
    sha256s beside the ids, so the stored run says which evidence it compared. ValidationError → 422."""
    if set(params) != {"base", "head"}:
        raise ValidationError("a report-diff names exactly two runs: params {base, head}")
    base, head = store.get(str(params["base"])), store.get(str(params["head"]))
    for side, run in (("base", base), ("head", head)):
        if run is None:
            raise ValidationError(f"{side} run {params[side]!r} is unknown or was pruned")
        if run.status != "done":
            raise ValidationError(f"{side} run {run.id} is {run.status}, not finished")
        if run.report == DIFF_REPORT:
            raise ValidationError(f"{side} run {run.id} is itself a diff")
        if not store.exists(run.id, "json"):
            raise ValidationError(f"{side} run {run.id} no longer has its .json")
    if base.id == head.id:
        raise ValidationError("base and head are the same run")
    if not base.id < head.id:
        raise ValidationError(f"base {base.id} is newer than head {head.id}: "
                              "a diff compares an earlier run with a later one")
    if base.report != head.report or base.cluster != head.cluster:
        raise ValidationError(f"base is {base.report} on {base.cluster} and head is {head.report} on {head.cluster}: "
                              "a diff compares one report on one cluster")
    if cluster != head.cluster:
        raise ValidationError(f"the diff names cluster {cluster!r}; its runs are on {head.cluster!r}")
    return {"report": head.report, "base": base.id, "head": head.id,
            "base_sha256": base.sha256, "head_sha256": head.sha256}


def _blocks(doc: dict) -> dict[tuple, tuple[list, list]]:
    """Stable coverage conclusions and every comparable block of the sealed sections, keyed by
    where it sits and what it holds:
    (section title, kind, block title, columns, occurrence). The occurrence keeps two blocks with one
    key apart; a block's rows are its table rows, its key-value pairs, or the section's notes."""
    coverage = doc.get("coverage", {})
    coverage_rows = [[label, coverage[key]] for label, key in COVERAGE_FIELDS if key in coverage]
    out: dict[tuple, tuple[list, list]] = {}
    if coverage_rows:
        out[("Evidence coverage", "kv", "Coverage", ("key", "value"), 0)] = (["key", "value"], coverage_rows)
    for section in doc["sections"]:
        if not section["sealed"]:
            continue
        notes = [[b["level"], b["text"]] for b in section["blocks"] if b["kind"] == "note"]
        found = [("note", "Notes", ["level", "note"], notes)] if notes else []
        for b in section["blocks"]:
            if b["kind"] == "table":
                found.append(("table", b["title"], b["columns"], b["rows"]))
            elif b["kind"] == "kv":
                found.append(("kv", b["title"], ["key", "value"], [list(item) for item in b["items"]]))
        for kind, title, columns, rows in found:
            key = (section["title"], kind, title, tuple(columns))
            n = sum(1 for k in out if k[:4] == key)
            out[(*key, n)] = (columns, rows)
    return out


def _row_counts(rows: list) -> Counter:
    # A row's identity is the whole row, written canonically, so 1 and "1" stay different values.
    return Counter(json.dumps(row, sort_keys=True, default=str) for row in rows)


def _rows(counts: Counter) -> list:
    # A row removed (or added) twice is listed twice: the multiset keeps duplicate rows honest.
    return [json.loads(row) for row in sorted(counts.elements())]


def build_diff(base: dict, head: dict, *, run_id: str, now: datetime, generated_by: str, generated_by_note: str,
               settings: ReportSettings) -> Report:
    """The diff of two stored `.json` documents as a sealed Report. Deterministic in its inputs: two
    diffs of one pair hash the same, because the run facts are on page one, which is not sealed."""
    for side, doc in (("base", base), ("head", head)):
        if "sealed_provenance" not in doc:
            raise ValidationError(f"the {side} run {doc.get('run_id')} was written before 4.1.0 (SPEC_F1): its page one "
                                  "is inside its data, so it cannot be compared")
    b, h = _blocks(base), _blocks(head)
    summary, sections, added_total, removed_total = [], [], 0, 0
    for key in [*b, *(k for k in h if k not in b)]:          # the base's order, then blocks new in the head
        columns = (h.get(key) or b[key])[0]
        before, after = _row_counts(b.get(key, (None, []))[1]), _row_counts(h.get(key, (None, []))[1])
        removed, added = before - after, after - before
        if not removed and not added:
            continue
        where = key[0] if key[1] == "note" else f"{key[0]} — {key[2]}"
        summary.append([key[0], key[2], sum(removed.values()), sum(added.values())])
        removed_total, added_total = removed_total + sum(removed.values()), added_total + sum(added.values())
        sections.append(Section(where, [Table("Removed", columns, _rows(removed), empty_text="none removed"),
                                        Table("Added", columns, _rows(added), empty_text="none added")]))
    inputs = Table("The two runs", ["side", "run id", "sha256", "generated at", "snapshot", "parameters"], [
        [side, doc["run_id"], doc["sha256"], doc["generated_at"], doc["sealed_provenance"].get("snapshot_stamp"),
         ", ".join(f"{k}={v}" for k, v in sorted(doc["params"].items())) or "none"]
        for side, doc in (("base", base), ("head", head))])
    notes = [Note("Rows are compared whole: a changed cell shows as one row removed and one added. Only the sealed "
                  "data is compared, so who ran a report and when never shows as a change.", "note")]
    if base["params"] != head["params"]:
        notes.append(Note("The two runs were made with different parameters, so a difference may be the question "
                          "asked rather than the cluster.", "warning"))
    if base["truncated"] or head["truncated"]:
        notes.append(Note("At least one run cut a table at its row limit; rows past the cut are not compared.", "warning"))
    overview = [Table("Changes per block", ["section", "block", "removed", "added"], summary, empty_text=NO_CHANGE)]
    if not summary:
        overview.append(Note(f"{NO_CHANGE}: stable coverage conclusions and every table, list and note in the sealed "
                             "data are the same in both runs.", "note"))
    page_one = Section("Provenance and coverage", [KeyValues("Run", [
        ("Generated at (UTC)", iso(now)), ("Generated by", f"{generated_by} ({generated_by_note})"), ("Run id", run_id),
        ("Report service", f"{__version__} @ {settings.git_commit}")])], sealed=False)
    return Report(
        name=DIFF_REPORT, title=f"Changes in {head['title']}", cluster=head["cluster"], api_url=head["api_url"],
        generated_at=iso(now), generated_by=generated_by, generated_by_note=generated_by_note, run_id=run_id,
        params={"report": head["name"], "base": base["run_id"], "head": head["run_id"],
                "base_sha256": base["sha256"], "head_sha256": head["sha256"]},
        coverage={}, provenance={"marking": settings.marking, "report_service_version": __version__,
                                 "commit": settings.git_commit},
        totals={"blocks_changed": len(summary), "rows_removed": removed_total, "rows_added": added_total},
        truncated=bool(base["truncated"] or head["truncated"]), include_members=bool(head["include_members"]),
        sections=[page_one, Section("Inputs", [inputs, *notes]), Section("Summary", overview), *sections],
    ).seal()


def build_diff_run(store: ArtifactStore, run: Run, settings: ReportSettings, now: datetime) -> Report:
    """The worker's step: read both stored `.json` files and check each still carries the sha256 the
    request recorded, then build. A run pruned or rewritten since the request fails this run, never
    another one."""
    docs = []
    for side in ("base", "head"):
        data = store.read(run.params[side], "json")
        if data is None:
            raise ValidationError(f"the {side} run {run.params[side]} was pruned before this diff rendered")
        doc = json.loads(data)
        recorded = run.params[f"{side}_sha256"]
        if doc.get("sha256") != recorded or recompute_sha256(doc) != recorded:
            raise ValidationError(f"the {side} run's .json no longer matches the sha256 recorded at request time")
        docs.append(doc)
    return build_diff(*docs, run_id=run.id, now=now, generated_by=run.generated_by,
                      generated_by_note=run.generated_by_note, settings=settings)
