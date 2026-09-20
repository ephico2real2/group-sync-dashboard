# SPEC E1 — The report library tab

| | |
|---|---|
| Programme | Feature programme 2026-09 — index and version ladder in `docs/specs/README.md` |
| Batch | E — after the programme: the operator's asks of 2026-09-20 |
| Release | — after the programme: with the next application release (Unreleased in `docs/CHANGELOG.md`) |
| Version on release | app 0.25.0 |
| Issue | [#229](https://github.com/ephico2real2/group-sync-dashboard/issues/229) |
| Status | in progress |
| Source | hand-written by the orchestrator from the agreed mock `docs/design/report-library-mock.html` (drafted by Cursor Grok on 2026-09-20, six render-check findings fixed before agreement) and from the code measured below; no design agent |

## How to read this spec

Unlike the programme's thirteen specs, this body is not a design agent's output: the design is the
agreed mock, and the page's render code is ported from it function by function. What this file adds
is the part the mock could only imitate — the service contract for a run's expiry, which must be the
`prune()` decision and never a second copy of its rules — and the integration points in the
application the mock stood outside of (the tab, the position, the fetch plan, the fingerprint, the
focus restore, the tier). Implementation applies the fenced blocks under "Design" one file at a
time with an exact-match check on every Old text; a deviation found necessary is written back here,
with the reason, under "Orchestrator's notes".

## Orchestrator's notes

- Review of #233 (2026-09-20, Grok, Codex — `docs/REVIEW_report_library.md`): the generate link's id is minted from
  the SECTION (`lib-gen-sec-<schedule>`) when the section belongs to a schedule, from the report when it does not —
  a report with two schedules repeated one id. The positioned run is fetched by id (`libraryPositionRun()` →
  `data.libraryRun`, in the fingerprint) and joined to the listing, so a run past the API's first page opens
  rather than "Run not found". `manual:cap`'s words are the page's, not the mock's: "held by the manual run cap
  alone" when no age bound applies (the mock's "goes on the next prune" is false with `manual_days` 0), "expires …"
  when one does — §3's rule, the same ranking. Rejected: re-basing `ago()`/`untilShort()` on the service's
  `as_of` — every page reads the browser clock for relative words, and one page drifting from the rest is the
  worse defect; and stripping `cluster` from the library's position — the position is the app's, and a reader on a
  two-cluster dashboard must land on the right one.

- The walk at `586e763`: "Copy link" writes the app's full position, `#page=library&cluster=crc-local&run=<id>`
  — `hashFor(currentPosition())`, the shape every position in the app carries (`#page=groups&cluster=…`).
  §2.6's `#page=library&run=<id>` is the minimal form the router accepts and opens the same drawer; the
  copied link carries the cluster because a reader on a two-cluster dashboard must land on the right one.

- Implementation (2026-09-20), the type-scale guards: the drawer took its report-kind rail from an inline
  `style="--rk: …"`, which `test_inline_styles_carry_no_literal_at_all` refuses; it carries `class="drawer
  r-<kind>"` and app.css sets `--rk` per kind, as `.report-panel.r-<kind>` and `.lib-sec.r-<kind>` do. The
  accent button's `#fff` is `var(--surface-1)` (the pager's and the segment's shape); the jump pills' `2px 9px`
  carries the optical note the badge rule carries. The spec index guard learns the E batch (ids `E\d`, release
  `—`) without loosening the programme's thirteen.

- Implementation (2026-09-20), decision 3 refined on the first render against the fixture's `weekly` schedule
  (`0 6 * * 1`, cadence `Weekly Mon 06:00`): "Weekly Mon groups" is not how anyone says it. The heading takes the
  cadence's NAMED word alone (Daily, Weekly, Weekdays, Monthly, Quarterly, Yearly), the whole cadence minus its
  clock when it has no such word ("1st & 16th"), and the report's title alone when `describe()` could only echo
  the cron expression; the weekday and the clock stay in the section's sub-line. The mock's rule (strip the
  clock only) gives the same words for the lab's three schedules.

## Design

### 1. The gap, measured (2026-09-20, CRC)

`GET /report/api/status`: three schedules (`nightly-namespace-access` ok, last success
`2026-09-20T06:16:31Z`; `quarterly-compliance` never; `biweekly-groups` paused). `GET /report/api/runs`:
8 runs — 4 `schedule:nightly-namespace-access`, 2 `kubeadmin`, 2 `jane.smith`; 6 done, 2 failed (`no
namespace matches company.net/mnemonic in (demo, beta)`). The history table with per-format download
buttons exists on the Reporting-status page (`index.html#reportingPage`), reached through one
`linkish` button at the foot of the Reports tab; it shows seven columns and none of the manifest's
`params`, `started_at`, `render_seconds`, `snapshot_stamp`, `bytes`, `error`; no run states when it
goes or why it stays; there is no position for a run.

### 2. Decisions

1. **A new tab, Library**, at `#page=library`, rendered beside Reports only when reporting is enabled
   (`reportingEnabled()`), with its own accent `--tab-library`: `#7a2468` in light (8.74:1 on `--page`
   `#f9f9f7`) and `#d489c0` in dark (7.53:1 on `#0d0d0d`), both measured by
   `tests/test_accessibility.py`, which reads every `--tab-*` token. **The Reports tab and the
   Reporting-status page are untouched** (the operator, 2026-09-20: adding to them clutters two pages
   that already do their jobs).
2. **Sections = the enabled catalogue crossed with the schedules.** For every enabled report
   (`GET /report/api/reports`), one section per schedule whose `report` is that report
   (`GET /report/api/status` `schedules[]`), else one unscheduled section. Nothing names the lab's
   schedules: a new stanza in `reporting.schedules[]` is a new section.
3. **The heading is how people ask for it**: the service's `cadence` with its clock time dropped, in
   front of the report's short title — "Daily namespace access", "Quarterly compliance"; a paused
   schedule reads "Groups — 1st & 16th, paused". Never a regex on the schedule's name. Manual runs of
   a scheduled report sit under their own sub-heading "Manual runs" inside that report's section.
4. **Each run shows** when it ran, the cluster, its formats with sizes (from `bytes`), its status,
   the first line of its error when failed, and its expiry in words and a date. Runs are cards, never a
   wide table (375 px). The newest run per cluster leads; two earlier ones follow; "all N →" reveals
   the rest in place.
5. **Links**: "Generate this report →" in an empty section, "Generate another →" under a section's
   runs; both open `#page=reports&report=<name>` (the arrow says it leaves the page).
6. **A run is a position**: `#page=library&run=<id>` opens the run's drawer — the full manifest, the
   expiry, the format buttons, "Open .html in a new tab", "Copy link". An unknown id renders "Run not
   found — No run with that id is in the library." Closing the drawer (Close, ← Library, Escape, the
   overlay) navigates to `#page=library`. `run` belongs to the Library page the way `report` belongs
   to Reports: any other page's position carries none.
7. **Expiry comes from the service** (§3). The page renders `expires_at` and `retained_by`; it never
   computes them.
8. **Tier**: the administrator tier the reporting surface already enforces — the ticket, the refusal
   card for a reader narrowed on the host cluster, no personnel data beyond `generated_by`.
9. **The poll**: `data.library` joins the auto-refresh fingerprint (the omission #157, #167 and #228
   each fixed). Focus survives every repaint by id: the cards carry `id="run-<id>"`, the drawer's
   controls carry ids, the tab carries `tab-library`.

### 3. The service contract — `expires_at` and `retained_by`

Every run in `GET /report/api/runs` and `GET /report/api/runs/{id}` carries two more fields. They are
computed by the code `prune()` runs, refactored so that the ranking is written once:

- `expires_at` — ISO `YYYY-MM-DDTHH:MM:SSZ`: the **earliest** instant the run can be deleted, which is
  `retention_stamp(run) + 1 s + <days>` (the same instant `older_than` tests); `null` when no age bound
  applies (`days` 0), when only a count cap applies, or when the run is queued/running.
- `retained_by` — why it is held now:
  - `newest:<n>/<keep> of <schedule> on <cluster>` — one of the newest `keep` finished runs of its
    schedule on its cluster: kept whatever its age, so it lives **at least** until `expires_at` and
    longer while it stays among the `keep`;
  - `age:<days>d` — a scheduled run beyond the newest `keep`, kept while younger than `days`
    (`age:0d` when `days` is 0: kept indefinitely);
  - `manual:<days>d` — a manual run within the count cap, kept `days`;
  - `manual:cap` — a manual run beyond `manual_max_runs` (it goes on the next prune), or one under
    a cap with no age bound;
  - `null` — queued or running: never doomed.

`docs/CHANGELOG.md` and `local-development/API.md` say this in one paragraph each.

#### `local-development/gsd/reporting/artifacts.py`

Old (the imports):

```python
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime, timedelta
```

New:

```python
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime, timedelta
from typing import NamedTuple
```

Old (after `new_run_id`):

```python
class ArtifactStore:
    def __init__(self, root: str):
```

New:

```python
class Retention(NamedTuple):
    """One run's standing under the two-tier rules, decided by the same ranking `prune()` deletes by.

    `expires_at` is the EARLIEST instant the run can go: `retention_stamp + 1 s + days`, the instant
    `older_than` starts answering true; None when no age bound applies. `retained_by` says why it is
    held now (`newest:<n>/<keep> of <schedule> on <cluster>` — kept whatever its age, so at least until
    `expires_at`; `age:<days>d`; `manual:<days>d`; `manual:cap`); None for a queued or running run.
    `doomed_at` is prune's own answer: the instant it deletes the run, `datetime.min` for one already
    beyond a count cap, None while the rank protects it or no bound applies. The page reads the first
    two (#229); prune reads the third. One ranking, two readers — the words on the page can never
    disagree with the deletion."""
    expires_at: str | None
    retained_by: str | None
    doomed_at: datetime | None


_ALWAYS = datetime.min.replace(tzinfo=UTC)


def _stamp(d: datetime) -> str:
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


class ArtifactStore:
    def __init__(self, root: str):
```

Old (the whole `prune` body from its lock to its return):

```python
        with self._lock:
            finished = [r for r in self._runs.values() if r.status in ("done", "failed")]
            doomed: list[Run] = []

            # Manual tier: keep the newest `manual_max_runs`, then drop anything older than `manual_days`.
            manual = sorted((r for r in finished if not r.schedule), key=newest_first, reverse=True)
            if manual_max_runs > 0:
                doomed += manual[manual_max_runs:]
                manual = manual[:manual_max_runs]
            doomed += [r for r in manual if older_than(r, manual_days)]

            # Scheduled tier: per (schedule, cluster) keep the newest K; beyond K keep only while young.
            by_key: dict[tuple[str, str], list[Run]] = {}
            for r in sorted((r for r in finished if r.schedule), key=newest_first, reverse=True):
                by_key.setdefault((r.schedule, r.cluster), []).append(r)
            for (name, _cluster), group in by_key.items():
                keep, days = overrides.get(name, (scheduled_keep, scheduled_days))
                doomed += [r for i, r in enumerate(group)
                           if not (keep > 0 and i < keep) and older_than(r, days)]

            for r in doomed:
                shutil.rmtree(self._dir(r.id), ignore_errors=True)
                self._runs.pop(r.id, None)
        if doomed:
            log.info("pruned %d report run(s)", len(doomed))
        return len(doomed)
```

New:

```python
        with self._lock:
            plan = self._retention(scheduled_keep=scheduled_keep, scheduled_days=scheduled_days,
                                   manual_days=manual_days, manual_max_runs=manual_max_runs, overrides=overrides)
            doomed = [self._runs[run_id] for run_id, standing in plan.items()
                      if standing.doomed_at is not None and standing.doomed_at <= now and run_id in self._runs]
            for r in doomed:
                shutil.rmtree(self._dir(r.id), ignore_errors=True)
                self._runs.pop(r.id, None)
        if doomed:
            log.info("pruned %d report run(s)", len(doomed))
        return len(doomed)

    def _retention(self, *, scheduled_keep: int, scheduled_days: int, manual_days: int, manual_max_runs: int,
                   overrides: dict[str, tuple[int, int]] | None) -> dict[str, Retention]:
        """Every finished run's standing (`Retention`), under the caller's lock. THE ranking: prune()
        deletes by `doomed_at`, the API prints `expires_at`/`retained_by` (#229). `doomed_at` is
        `retention_stamp + 1 s + days` — end-of-second, exactly as `older_than` tested it before this
        refactor (a run stamped on the cutoff second survives until the next). Manual tier: the newest
        `manual_max_runs` are kept, then aged by `manual_days`; beyond the cap a run is doomed now.
        Scheduled tier: per (schedule, cluster) the newest `keep` whatever their age, the rest while
        younger than `days`; a bound of 0 is disabled. Queued/running runs are absent (never doomed)."""
        overrides = overrides or {}

        def bound(run: Run, days: int) -> datetime | None:
            return retention_stamp(run) + timedelta(seconds=1) + timedelta(days=days) if days > 0 else None

        def newest_first(run: Run) -> tuple[datetime, str]:
            return (retention_stamp(run), run.id)

        finished = [r for r in self._runs.values() if r.status in ("done", "failed")]
        plan: dict[str, Retention] = {}
        manual = sorted((r for r in finished if not r.schedule), key=newest_first, reverse=True)
        for i, r in enumerate(manual):
            if manual_max_runs > 0 and i >= manual_max_runs:
                plan[r.id] = Retention(None, "manual:cap", _ALWAYS)
            elif manual_days > 0:
                at = bound(r, manual_days)
                plan[r.id] = Retention(_stamp(at), f"manual:{manual_days}d", at)
            else:
                plan[r.id] = Retention(None, "manual:cap", None)
        by_key: dict[tuple[str, str], list[Run]] = {}
        for r in sorted((r for r in finished if r.schedule), key=newest_first, reverse=True):
            by_key.setdefault((r.schedule, r.cluster), []).append(r)
        for (name, cluster), group in by_key.items():
            keep, days = overrides.get(name, (scheduled_keep, scheduled_days))
            for i, r in enumerate(group):
                at = bound(r, days)
                if keep > 0 and i < keep:
                    plan[r.id] = Retention(_stamp(at) if at else None, f"newest:{i + 1}/{keep} of {name} on {cluster}", None)
                else:
                    plan[r.id] = Retention(_stamp(at) if at else None, f"age:{days}d", at)
        return plan

    def retention(self, *, scheduled_keep: int, scheduled_days: int, manual_days: int, manual_max_runs: int,
                  overrides: dict[str, tuple[int, int]] | None = None) -> dict[str, Retention]:
        """The standing of every finished run, for the API (#229) — the same plan `prune()` deletes by."""
        with self._lock:
            return self._retention(scheduled_keep=scheduled_keep, scheduled_days=scheduled_days,
                                   manual_days=manual_days, manual_max_runs=manual_max_runs, overrides=overrides)
```

The `older_than` and `newest_first` closures inside `prune()` are removed with the body they served; the
`now` normalisation above the lock stays.

#### `local-development/gsd/reporting/server.py`

A helper beside `list_runs`, used by `list_runs` and `get_run`:

```python
    def _with_retention(rows: list[Run]) -> list[dict]:
        """The public dicts with `expires_at`/`retained_by` from the store's own ranking (#229) — the
        settings the prune applies, read the same way (`retention_overrides`)."""
        plan = store.retention(scheduled_keep=settings.scheduled_keep_per_schedule,
                               scheduled_days=settings.scheduled_retention_days,
                               manual_days=settings.manual_retention_days,
                               manual_max_runs=settings.manual_retention_max_runs,
                               overrides=retention_overrides(settings))
        out = []
        for r in rows:
            d = r.public()
            standing = plan.get(r.id)
            d["expires_at"] = standing.expires_at if standing else None
            d["retained_by"] = standing.retained_by if standing else None
            out.append(d)
        return out
```

`list_runs` returns `"runs": _with_retention(rows)`; `get_run` returns `_with_retention([run])[0]`.

### 4. The page

The render code is the mock's, ported function by function into `index.html` under a
`/* ─── #229 E1: the Library page ─── */` banner placed after `wireReporting()`, with these substitutions
and no others:

| mock | application |
|---|---|
| `REPORTS`, `STATUS`, `RUNS` (embedded JSON) | `data.reportCatalog`, `data.reportStatus`, `data.library` (the runs payload, `GET /report/api/runs?limit=1000`) |
| `computeExpiry()` and `retentionStamp()`/`newestFirst()` for expiry | removed — `run.expires_at` / `run.retained_by` from the service; `newestFirst` orders by `finished_at` then id, as the service does |
| `esc`, `stateBadge`, `fmtStamp`, `untilShort`, `ago`, `REPORT_KIND`, `refusalCard`, `downloadArtifact` | the application's own |
| `openRun()` writing the hash, `applyHash`, `hashchange` | `navigate({ run })` / `navigate({ run: null })`; the drawer renders from `view.run` |
| `location.hash = "#page=reports&report=…"` | `navigate({ page: "reports", report })` then `render(); refresh()` |
| the two-cluster `<template>` shape example | removed — the application groups by cluster for real (`cluster-head` when more than one) |
| "Open .html in a new tab" | `reportFetch(…/artifact?format=html&download=false)` → blob → `window.open(URL.createObjectURL(blob))`, revoked after a minute |
| "Copy link" | `navigator.clipboard.writeText(location.origin + location.pathname + location.search + hashFor(currentPosition()))`; the button reads "Copied" |

Integration blocks (each applied with an exact-match check):

- `POSITION_KEYS` gains `"run"`; `applyPosition` sets `view.run = view.page === "library" ? (pos.run || null) : null` beside the `report` rule with the same reasoning; `view` gains `run: null`.
- The tab strip: `${reportingEnabled() ? tab("library", "Library") : ""}` after the Reports tab.
- The dispatch in `render()`: `else if (view.page === "library") { main.innerHTML = libraryPage(); wireLibrary(); }`.
- The fetch plan: on the library page, when reporting is enabled and the reader is not narrowed on the host, `want.reportCatalog`, `want.reportStatus` and `want.library = guard403(reportGet("/api/runs?limit=1000"))`; the same tier catch-up as the status page (a reader promoted mid-session).
- The fingerprint: `data.library` beside `data.reportHistory`.
- `app.css`: `--tab-library` in the light `:root`, in the dark media block and in the `[data-theme="dark"]` block; `body[data-page="library"] { --accent: var(--tab-library); }`; the mock's `.lib-sec`, `.jumps`, `.run`, `.cluster-head`, `.subh`, `.expiry`, `.reason`, `.overlay`, `.drawer`, `.kv`, `.btn-acc`, `.note-found`, `.sec-foot` rules under a `#229` banner.

### 5. Tests

- `tests/test_reporting_server.py`: `TestRetentionStanding` — for the manual tier (within the cap, beyond it, days 0), the scheduled tier (rank < keep, beyond keep young, beyond keep old, days 0) and a per-schedule override, `store.retention()`'s `expires_at`/`retained_by` beside a real `store.prune(now=…)` at `expires_at − 1 s` (kept) and at `expires_at` (deleted, unless the rank protects it); the API test that `GET /api/runs` and `/runs/{id}` carry the two fields and a queued run carries nulls.
- `tests/test_ui.py`: `TestLibraryPage` on `reporting_server` — the sections from a cold `#page=library` (one per enabled report; the fixture's `weekly` and `paused-ns` schedules head their sections by cadence; the paused one dashed), a generated run appearing under its report with its formats and its expiry words, the run position from a cold URL opening the drawer with the manifest and closing back to `#page=library`, an unknown id's sentence, a failed run's reason, 375 px without horizontal scroll on the page and on the drawer, focus on a card surviving `refresh()`, the tab count 13 with reporting on.
- `tests/test_accessibility.py` measures `--tab-library` with the others (no change needed unless it fails).

### 6. Docs and evidence

`local-development/API.md` (the runs rows and a paragraph on the fields), `docs/CHANGELOG.md` (Unreleased),
`docs/design/README.md` (the mock is **Implemented**), the walk `reports/2026-09-20_report-library/`
with its pictures on #229, `docs/REVIEW_report_library.md` for the three seats.
