"""What every report shares: the parameter grammar, the run context, the provenance and coverage
blocks, and the small helpers that keep eleven modules from restating one rule."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any

from ... import __version__
from ..config import ReportSettings
from ..model import DIRECT_BINDINGS_CAVEAT, KeyValues, Note, Report, Section, Table, iso
from ..snapshot import CLUSTER_SCOPE, Snapshot

MAX_NAMESPACES = 50
_LABEL = re.compile(r"^[a-z0-9]([-a-z0-9]{0,61}[a-z0-9])?$")
_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_INT = re.compile(r"-?[0-9]+")        # what an integer parameter may spell when it arrives as a string
#: Tables longer than this are cut and the report says so — R3's rule, applied to a document:
#: a PDF that silently drops rows cannot be told apart from a complete one.
ROW_LIMIT = 5000


class ValidationError(ValueError):
    """A parameter the caller got wrong; the message is served as the 422 detail."""


@dataclass(frozen=True)
class ParamSpec:
    name: str
    type: str                      # "namespaces" | "bool" | "int" | "str" | "date" | "enum" | "csv" | "selector-map"
    default: Any
    help: str
    choices: tuple[str, ...] = ()
    lo: int | None = None
    hi: int | None = None
    required: bool = False
    #: #149 R7 — what the ParamSpec-driven shell needs beyond the type. `source` names a DISCOVERED
    #: lookup the catalogue serves per cluster from the snapshot ("users", "groups", "providers",
    #: "roles", "mnemonics", "oud-groups"): a csv with a source renders as a tag input with type-ahead
    #: over those values (Enter adds a value not in the set). `unit` labels an int ("days"). `advanced`
    #: folds the field under the Advanced disclosure. `group` renders two fields as one framed block —
    #: "subject" is the users+groups Subject scope.
    source: str = ""
    unit: str = ""
    advanced: bool = False
    group: str = ""

    def as_json(self) -> dict:
        return {"name": self.name, "type": self.type, "default": self.default, "help": self.help,
                "choices": list(self.choices), "lo": self.lo, "hi": self.hi, "required": self.required,
                "source": self.source, "unit": self.unit, "advanced": self.advanced, "group": self.group}


def subject_scope() -> tuple[ParamSpec, ParamSpec]:
    """The Subject scope the subject-centric reports share (#149 R7): all subjects by default, or the
    named users and/or groups. Replaces the old all/groups/users kind toggle — a specific selection
    subsumes it: users only = pick users, groups only = pick groups."""
    return (
        ParamSpec("users", "csv", [], "Only these users (empty = every subject).", source="users", group="subject"),
        ParamSpec("groups", "csv", [], "Only these groups (empty = every subject).", source="groups", group="subject"),
    )


def subject_filter(params: dict) -> tuple[set[str] | None, set[str] | None]:
    """(users, groups) to keep, or None for "all of that kind". With neither named, every subject of
    both kinds; with only users named, groups are OUT (the reader asked for those users), and the
    same the other way — the old `users`/`groups` kinds by selection."""
    users, groups = set(params.get("users") or []), set(params.get("groups") or [])
    if not users and not groups:
        return None, None
    return (users or set()), (groups or set())


@dataclass(frozen=True)
class ReportSpec:
    name: str
    title: str
    summary: str
    values_key: str                 # reporting.reports.<key>.enabled
    params: tuple[ParamSpec, ...] = ()
    #: Which dashboard facilities the report needs beyond the snapshot, for the catalogue's
    #: "why is this report greyed out" line. "loginCapture" is the only one today.
    needs: tuple[str, ...] = ()
    #: An optional cross-parameter check run at the endpoint (a 422 on bad input), for rules a single
    #: ParamSpec cannot express — e.g. "exactly one of two parameters". Runs on the validated dict.
    validator: object = None

    def as_json(self, enabled: bool) -> dict:
        return {"name": self.name, "title": self.title, "summary": self.summary, "enabled": enabled,
                "values_key": f"reporting.reports.{self.values_key}.enabled",
                "needs": list(self.needs), "params": [p.as_json() for p in self.params]}


@dataclass
class RunContext:
    settings: ReportSettings
    cluster: dict                   # Snapshot.cluster row
    now: datetime
    run_id: str
    generated_by: str
    generated_by_note: str
    snapshot_stamp: str
    snapshot_age_seconds: float
    schema_version: int
    #: The ordered selector DIMENSIONS the namespace-access report offers (P2): company.net/mnemonic AND
    #: company.net/app-environment. Empty = no selector.
    namespace_selector_labels: tuple[str, ...] = ()


@dataclass
class Built:
    sections: list[Section]
    totals: dict = field(default_factory=dict)
    truncated: bool = False
    include_members: bool = False


def parse_namespaces(raw: str) -> list[str]:
    """Comma-separated namespace names, de-duplicated in order; `(cluster-scoped)` accepted."""
    names: list[str] = []
    for token in (t.strip() for t in (raw or "").split(",")):
        if not token:
            continue
        if token != CLUSTER_SCOPE and not _LABEL.match(token):
            raise ValidationError(f"{token!r} is not a namespace name")
        if token not in names:
            names.append(token)
    if not names:
        raise ValidationError("at least one namespace is required")
    if len(names) > MAX_NAMESPACES:
        raise ValidationError(f"at most {MAX_NAMESPACES} namespaces per report")
    return names


def _string_items(value: object, name: str) -> list[str]:
    """A comma string or a list of strings — nothing else. An integer or a list holding one raised
    a TypeError that surfaced as a 500 instead of the 422 every other bad parameter gets (review of
    C3, Codex)."""
    if isinstance(value, str):
        return [t for t in value.split(",")]
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value)
    raise ValidationError(f"{name} must be a comma-separated string or a list of strings")


def validate_selector_map(value: object, name: str) -> dict[str, list[str]]:
    """A `{label: [values]}` selection for the multi-dimension namespace selector (P2). STRUCTURE
    only — the check that each label is one of the deployment's configured selector labels needs the
    settings and stays in the report's build(). Values within a dimension are OR'd, dimensions are
    AND'd (docs/DESIGN_reporting_selectors_snapshots_and_windows.md §3). An OMITTED dimension is
    unconstrained; a PRESENT dimension with no values is a 422, so a blank multi-select cannot
    silently select nothing and fail every run. Values are stripped, blanks skipped, de-duplicated;
    the aggregate is bounded like the explicit-names path."""
    if not isinstance(value, dict) or not value:
        raise ValidationError(f"{name} must be a non-empty object of label -> [values]")
    out: dict[str, list[str]] = {}
    total = 0
    for label, values in value.items():
        if not isinstance(label, str) or not label.strip():
            raise ValidationError(f"{name} label must be a non-empty string")
        # A dimension's values must be a JSON list of strings — NOT a comma string. `_string_items`
        # would accept "beta,demo" and split it, which the grammar (dict[str, list[str]]) forbids and
        # which a Helm/JSON transport never produces (review PR #129 C1, Codex).
        if not isinstance(values, list) or not all(isinstance(v, str) for v in values):
            raise ValidationError(f"{name}[{label}] must be a list of strings")
        cleaned: list[str] = []
        for v in values:
            v = v.strip()
            if v and v not in cleaned:
                cleaned.append(v)
        if not cleaned:
            raise ValidationError(
                f"{name}[{label}] must have at least one value (omit the dimension to leave it unconstrained)")
        out[label] = cleaned
        total += len(cleaned)
    if total > MAX_NAMESPACES:
        raise ValidationError(f"at most {MAX_NAMESPACES} selector values in total")
    return out


def validate_params(spec: ReportSpec, raw: dict | None) -> dict:
    """The one place a request's parameters are checked and defaulted. Unknown keys are refused:
    a misspelt parameter that silently fell back to a default would produce a report that says
    something other than what was asked."""
    raw = dict(raw or {})
    unknown = sorted(set(raw) - {p.name for p in spec.params})
    if unknown:
        raise ValidationError(f"unknown parameter(s) for {spec.name}: {unknown}")
    out: dict = {}
    for p in spec.params:
        value = raw.get(p.name, p.default)
        if value is None or value == "":
            if p.required:
                raise ValidationError(f"{p.name} is required")
            out[p.name] = p.default
            continue
        if p.type == "namespaces":
            out[p.name] = parse_namespaces(",".join(_string_items(value, p.name)))
        elif p.type == "bool":
            if isinstance(value, bool):
                out[p.name] = value
            elif str(value).lower() in ("true", "false"):
                out[p.name] = str(value).lower() == "true"
            else:
                raise ValidationError(f"{p.name} must be true or false")
        elif p.type == "int":
            if isinstance(value, bool) or isinstance(value, float) or not isinstance(value, (int, str)):
                raise ValidationError(f"{p.name} must be an integer")
            # A string spells digits and nothing else: int() itself also takes " 1", "1_000" and
            # "\t1\n", so a padded or underscored value would have been accepted as an integer
            # while every other wrong shape is a 422 (review of C3, second pass, Cursor).
            if isinstance(value, str) and not _INT.fullmatch(value):
                raise ValidationError(f"{p.name} must be an integer")
            try:
                n = int(value)
            except (TypeError, ValueError) as exc:
                raise ValidationError(f"{p.name} must be an integer") from exc
            if (p.lo is not None and n < p.lo) or (p.hi is not None and n > p.hi):
                raise ValidationError(f"{p.name} must be between {p.lo} and {p.hi}")
            out[p.name] = n
        elif p.type == "enum":
            if str(value) not in p.choices:
                raise ValidationError(f"{p.name} must be one of {list(p.choices)}")
            out[p.name] = str(value)
        elif p.type == "date":
            if not isinstance(value, str) or not _DATE.match(value):
                raise ValidationError(f"{p.name} must be YYYY-MM-DD")
            try:
                date.fromisoformat(value)               # a real calendar date, not just the shape
            except ValueError as exc:
                raise ValidationError(f"{p.name} must be a real date (YYYY-MM-DD)") from exc
            out[p.name] = value
        elif p.type == "csv":
            out[p.name] = [t.strip() for t in _string_items(value, p.name) if t.strip()]
        elif p.type == "selector-map":
            out[p.name] = validate_selector_map(value, p.name)
        else:  # "str" — trimmed: a reviewer's name with a trailing space is the same reviewer (#143 phase 2)
            # A string is a string: a number was stringified here while the record said "strings
            # must be strings" (review of C3, second pass, Cursor).
            if not isinstance(value, str):
                raise ValidationError(f"{p.name} must be a string")
            s = value.strip()
            if not s and p.required:
                raise ValidationError(f"{p.name} is required")
            if len(s) > 200:
                raise ValidationError(f"{p.name} is longer than 200 characters")
            out[p.name] = s
    if spec.validator is not None:
        spec.validator(out)                       # a cross-parameter check → 422 at the endpoint
    return out


def window_start(now: datetime, days: int) -> str:
    return iso(now - timedelta(days=days))


def rank(role_name: str) -> int:
    return {"cluster-admin": 4, "admin": 3, "edit": 2}.get(role_name, 1)


def ns_label(binding_namespace: str) -> str:
    return CLUSTER_SCOPE if binding_namespace == "" else binding_namespace


def cut(rows: list, limit: int = ROW_LIMIT) -> tuple[list, bool]:
    return (rows[:limit], True) if len(rows) > limit else (rows, False)


def coverage(snap: Snapshot, ctx: RunContext) -> dict:
    """What this evidence can attest. Every value is a STATE, and every state has a sentence."""
    cid = ctx.cluster["id"]
    ns_src = snap.namespaces_source(cid)
    ns_state = (ns_src or {}).get("state") or ("pending" if ctx.settings.namespaces_read_enabled else "off")
    ns_notes = {
        "ok": "Every namespace on the cluster was read, so a requested namespace that does not exist is reported as such, and a namespace with no observed binding is reported as having no grants.",
        "off": "Namespaces are known only from observed bindings (rbac.namespaces is off). 'No grants observed' cannot be told from 'namespace never observed', so absence of access is NOT attested.",
        "forbidden": "The Namespace read is refused (the rbac.namespaces grant is missing), so this report falls back to observed bindings and does not attest absence.",
        "pending": "Namespaces have not been read yet; this report falls back to observed bindings.",
    }
    users_src = snap.users_source(cid)
    users_state = (users_src or {}).get("state") or "pending"
    capture = snap.login_capture_status(cid)
    if not ctx.settings.login_capture_enabled:
        capture_state, capture_note = "off", "Login capture is off; nothing in this report says when anyone last logged in beyond the existence of their User object."
    elif capture is None:
        capture_state, capture_note = "pending", "Login capture is on but has not read the oauth-server logs yet."
    else:
        capture_state = "ok"
        capture_note = f"Login attempts are recorded since {capture['started_at']} (last read {capture['last_read_at']}); nothing before that was ever observed."
    retained = snap.history_retained_since(cid)
    return {
        "namespaces_read": ns_state, "attests_absence": ns_state == "ok", "namespaces_note": ns_notes[ns_state],
        "users_read": users_state,
        "users_note": {"ok": "User objects were read; 'logged in' means a User with an identity exists.",
                       "forbidden": "The User read is refused (rbac.users is off); nothing here can say who has logged in.",
                       "pending": "User objects have not been read yet."}[users_state if users_state in ("ok", "forbidden") else "pending"],
        "login_capture": capture_state, "login_capture_note": capture_note,
        "history_retained_since": retained,
        "direct_bindings_caveat": DIRECT_BINDINGS_CAVEAT,
    }


def provenance(ctx: RunContext) -> dict:
    commit = ctx.settings.git_commit
    return {
        "marking": ctx.settings.marking,
        "report_service_version": __version__, "commit": commit, "dirty": commit.endswith("-dirty"),
        "snapshot_stamp": ctx.snapshot_stamp,
        "snapshot_age_seconds": round(ctx.snapshot_age_seconds),
        "snapshot_schema_version": ctx.schema_version,
        "binding_interval_seconds": ctx.settings.binding_interval_seconds,
        "poll_status": ctx.cluster.get("status"), "last_poll": ctx.cluster.get("last_poll"),
        "poll_message": ctx.cluster.get("message"),
        "pdf_variant": ctx.settings.pdf_variant if ctx.settings.pdf_enabled else None,
        "pdf_font": "DejaVu Sans 2.37" if ctx.settings.pdf_enabled and ctx.settings.font_regular else None,
    }


def provenance_section(ctx: RunContext, cov: dict, params: dict, include_members: bool) -> Section:
    """Page one of every report. Without it a report is a screenshot, not evidence."""
    prov = provenance(ctx)
    age_min = prov["snapshot_age_seconds"] / 60
    items: list[tuple[str, Any]] = [
        ("Handling", prov["marking"]),
        ("Cluster", f"{ctx.cluster['id']} — {ctx.cluster.get('api_url', '')}"),
        ("Generated at (UTC)", iso(ctx.now)),
        ("Generated by", f"{ctx.generated_by} ({ctx.generated_by_note})"),
        ("Run id", ctx.run_id),
        ("Report service", f"{prov['report_service_version']} @ {prov['commit']}" + (" (DIRTY BUILD — no commit reproduces it)" if prov["dirty"] else "")),
        ("Data as of", f"snapshot {prov['snapshot_stamp']} (taken {age_min:.0f} min before generation; bindings refresh every {prov['binding_interval_seconds']} s); schema {prov['snapshot_schema_version']}"),
        ("Last poll", f"{prov['last_poll']} — {prov['poll_status']}" + (f": {prov['poll_message']}" if prov["poll_status"] not in (None, "ok") and prov["poll_message"] else "")),
        ("Namespaces", f"{cov['namespaces_read']} — {'attests absence' if cov['attests_absence'] else 'does not attest absence'}"),
        ("User objects", cov["users_read"]),
        ("Login capture", cov["login_capture"]),
        ("History retained since", ", ".join(f"{k}: {v or 'no rows'}" for k, v in cov["history_retained_since"].items())),
        ("Includes membership rosters", "yes" if include_members else "no"),
        ("Parameters", ", ".join(f"{k}={v}" for k, v in sorted(params.items())) or "none"),
    ]
    if prov["pdf_variant"] is not None:
        items.append(("PDF", f"variant {prov['pdf_variant'] or 'plain'}; font {prov['pdf_font']}"))
    blocks: list = [KeyValues("Provenance", items)]
    if prov["poll_status"] not in (None, "ok"):
        blocks.append(Note(f"The last poll of this cluster did not succeed ({prov['poll_status']}). Snapshot data is as of the last successful poll and may be stale.", "warning"))
    blocks.append(Note(cov["namespaces_note"], "note"))
    blocks.append(Note(cov["users_note"], "note"))
    blocks.append(Note(cov["login_capture_note"], "note"))
    blocks.append(Note("Scope: " + DIRECT_BINDINGS_CAVEAT + ".", "caveat"))
    return Section("Provenance and coverage", blocks)


def assemble(spec: ReportSpec, snap: Snapshot, ctx: RunContext, params: dict, built: Built) -> Report:
    cov = coverage(snap, ctx)
    sections = [provenance_section(ctx, cov, params, built.include_members), *built.sections]
    if built.truncated:
        sections.insert(1, Section("Truncation", [Note(f"At least one table was cut at {ROW_LIMIT} rows; `totals` carries the whole counts. Narrow the parameters for a complete listing.", "warning")]))
    return Report(
        name=spec.name, title=spec.title, cluster=ctx.cluster["id"], api_url=ctx.cluster.get("api_url", ""),
        generated_at=iso(ctx.now), generated_by=ctx.generated_by, generated_by_note=ctx.generated_by_note,
        run_id=ctx.run_id, params=params, coverage=cov, provenance=provenance(ctx),
        totals=built.totals, truncated=built.truncated, include_members=built.include_members, sections=sections,
    ).seal()


def roster_table(title: str, members: list[dict]) -> Table:
    return Table(title, ["member", "name", "logged in", "first seen"],
                 [[m["user_name"], m.get("full_name") or "", {None: "unknown", 0: "no", 1: "yes"}.get(m.get("logged_in"), "unknown"), m.get("first_seen_at") or ""] for m in members],
                 empty_text="no members")


def finding_label(finding: str) -> str:
    return {"dangling": "DANGLING — grants nobody (group was managed, now absent)",
            "unresolved": "UNRESOLVED — names a group that has never existed",
            "built_in": "built-in virtual group",
            "unmanaged": "UNMANAGED — synced group granted by hand, no policy operator source",
            "ok": "ok"}.get(finding, finding)
