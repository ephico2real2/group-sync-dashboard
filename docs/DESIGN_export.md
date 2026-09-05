# Design — CSV and JSON export of the table on screen

**Status: shipped in application 0.14.0 / chart 0.15.0 (feature C1, `docs/specs/SPEC_C1_table_export.md`).**
The switch is `ui.export.enabled` (default `true`), served to the page as `features.export` on
`/api/version` (`gsd/api.py#feature_flags`, `gsd/config.py#Settings`, `charts/group-sync-dashboard/values.yaml#ui`).

## What it does

Export exactly the rows the browser holds for the current table, after the page's own filter and
sort, as RFC 4180 CSV or as a JSON envelope that names the cluster, tab, tier, filter, sort and
truncation. The file is generated in the browser from `data` and downloaded through a Blob and an
`<a download>` (`gsd/static/index.html#function exportDescriptor`, `index.html#function toCsv`). With
the switch off, the filter bar renders no export control and nothing else changes.

## Decision: client-side, not a `GET /api/…/export`, and not recorded in Usage

| | Client-side Blob (chosen) | Server-side `GET /api/clusters/{id}/<tab>/export` |
|---|---|---|
| Exports "what was served after filter and sort" | Yes by construction: the filter and sort are client-side and the export reads the same selection functions the tables paint from (`usersMatched`, `groupsMatched`, `bindingsVisible` and `sortedBindings`, `grantsSorted`). One deliberate difference: the Users table paints at most `USERS_RENDER` matches for responsiveness while the export carries every match, and the note beside the buttons states the export's count. | No: the server does not know the client filter or sort; it would export a different set from the one on screen, or re-implement six filter and sort rules. |
| Tier safety | Cannot widen: the browser only holds what `viewer_scope` and `require_admin_tier` served. | A seventh scoping path that must be kept identical to six handlers — the shape `gsd/api.py#SKIP_AUTH_PATHS` records as the one that drifted and was exploitable. |
| `@consistent` | Not applicable. | Streaming is forbidden inside a snapshot (`gsd/api.py#consistent`), so the CSV would be fully materialised anyway. |
| Session | No request. | Every request re-stamps the proxy cookie and, with `X-GSD-Interaction`, counts. |

`dashboard_user_activity` is one row per user per UTC day with a request count, deliberately not a
page-view log (`gsd/api.py#record_dashboard_use`). An export is a client action over rows whose
serving request was already counted, so exports are **not** recorded; the JSON envelope carries
`exported_at`, `viewer` and `scope` so the file states its own provenance. The operator accepted this
default (specification question 1).

## Encoding and safety

- **CSV carries the UTF-8 BOM, JSON does not.** A spreadsheet opened by double-click reads BOM-less
  UTF-8 as the local code page and mangles a non-ASCII display name; every programmatic reader accepts
  `utf-8-sig`. JSON must not carry one (RFC 8259 §8.1).
- **Formula guard.** A string cell beginning — after any leading whitespace — with `=`, `+`, `-`, `@`, tab, CR or LF,
  or with their full-width forms `＝ ＋ － ＠`, is prefixed with `'` (the OWASP CSV-injection mitigation, widened
  after review for importers that trim whitespace and for locales whose spreadsheets evaluate the full-width forms). Directory-supplied text is already treated as hostile for HTML on
  the page (`index.html#function esc`); it is the same input here. This is the only transformation;
  numbers and booleans are never touched.
- **Quoting.** A field holding a quote, a comma or a line break is quoted with doubled quotes; records
  end in CRLF; arrays (providers) join with `; `, which can never be this file's delimiter.

## Columns per tab

An explicit projection (`EXPORT_COLUMNS` in `index.html`), so a payload field the page does not render
is not smuggled out: users, groups, bindings (Access granted, wide view), myaccess (Access granted,
narrowed view), nsaudit and logins each name their columns; absent keys export as `null`.

## Filename and the truncation contract

`gsd_<cluster>_<tab>[_self][_partial]_<YYYYMMDDTHHMMSSZ>.<csv|json>`. `_self` when the payload declared
`scope: "self"`; `_partial` when the server said the page is a cut of a larger set (`truncated` and
`total`, the R3 fields already on `/users`, `/bindings/findings`, `/user-bindings` and `/logins`). The
note beside the buttons says the same before the download, wearing the warning edge, and the JSON
carries `served`, `total`, `truncated` and a sentence saying rows past the page were never loaded.

## Tests

`tests/test_export_module.py` (the flag in both states and its parsing), `tests/test_chart_strategy.py`
`TestUiExportModule` (values → ConfigMap key), and `tests/test_ui.py` `TestExport` /
`TestExportVisibility` (the download holds exactly the rows shown, follows filter and chip, says
partial in the note, filename and JSON, quotes per RFC 4180, makes no request, and a narrowed reader's
file holds only their own rows).
