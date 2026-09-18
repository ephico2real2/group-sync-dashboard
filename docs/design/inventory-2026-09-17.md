# Design inventory — 2026-09-17

Every finished mock as of this date: the committed file, its owning issue, the rendered review
copy, and what was verified. **The file in this folder is the canonical artefact**; the review
URL is the rendering published from it on this date and may be republished or expire.

Verified headlessly before being called finished: both shell controls (Appearance, Colour) with
`?mode=` / `?theme=` persistence, the deuteranopia palette moving `--good` to `#0072B2`, no
horizontal overflow at 375 / 393 / 768 / 1280, no JavaScript errors, and each page's own approved
features driven (the checklist in the 2026-09-17 session notes).

## Finished mocks

| # | file | page | owning issue | review rendering (2026-09-17) |
|---|---|---|---|---|
| 1 | [`cluster-overview-mock.html`](cluster-overview-mock.html) | **Cluster Overview** — per-cluster tiles that shrink across four density tiers as the fleet grows, a scoped view per tile, paged alerts (worst first, silenced shown dimmed), GroupSync CRs and Policy operator with the real four-state vocabulary and each state's consequence | #157 (page kept; relayout) | https://claude.ai/code/artifact/815c4564-b6f0-44bd-acf2-a3a623dbef4f |
| 2 | [`drilldown-mock.html`](drilldown-mock.html) | **Access drill-down** — tiles, tabs and one pattern-matched search over 67 groups · 63 users · 110 namespaces from the live cluster; group → member → user → via-group; the namespace as the third drillable entity; hash positions with back/forward | #167, #153 | https://claude.ai/code/artifact/125de9ce-af6c-40bf-b577-392d354b91c6 |
| 3 | [`landing-access-mock.html`](landing-access-mock.html) | **Your Access** — the user landing page, self-scoped (jane.smith on real CRC data): the answer first, cluster-wide roles, namespaces reached, direct grant, what changed, groups | #158 | https://claude.ai/code/artifact/d4e907dc-1376-453e-a9ea-c56ce4360ecb |
| 4 | [`overview-kpi-mock.html`](overview-kpi-mock.html) | **KPI page** — measured system status for both components (memory, CPU, throttling, disk), access posture, trends, clusters, the Grafana / Observe door | #156 → #157 | https://claude.ai/code/artifact/5abd4cc1-cc43-4905-97d6-e78103f6ea1d |
| 5 | [`reports-page-mock.html`](reports-page-mock.html) | **Reports** — the catalogue (bolder names, a colour gradient per report kind) and the per-report form a click opens immediately, in view, as a shareable position | #149 | https://claude.ai/code/artifact/52699aa5-9612-4748-bbda-4c3c0c03ec54 |
| 6 | [`report-form-mock.html`](report-form-mock.html) | **Report forms** — all eleven forms on one ParamSpec-driven shell as a reference sheet: discovered lookups, type-ahead, all / clear, the oud-group filter, mnemonic sort | #149, #143 | https://claude.ai/code/artifact/239de856-34ba-4d60-b8ed-4aa27bc6278f |
| 7 | [`reporting-status-mock.html`](reporting-status-mock.html) | **Reporting status** — service, run window, two-tier retention, schedules with enabled / paused, run history with filters and paging | #149 | https://claude.ai/code/artifact/ad0d8b64-ede1-4ad4-aa2b-2db2375beffc |
| 8 | [`tab-redesign-mock.html`](tab-redesign-mock.html) | **Tab redesign** — the six tabs feature-complete against the contract: exports on four tabs, sortable headers (now with `aria-sort`), every caveat kept | #153 | https://claude.ai/code/artifact/3f04c0ed-2858-4052-8e68-46135cd3f222 |

## Records (not pages)

| file | what it holds |
|---|---|
| [`tab-feature-contract.md`](tab-feature-contract.md) | What a redesign may **not** remove, captured from the running DOM — including the Cluster Overview's three cards, ruled settled on this date |
| [`data-requirements.md`](data-requirements.md) | Every number each mock renders, its source in the app today, and the ten gaps between the mocks and real pages |
| this file | The inventory as of 2026-09-17 |

## Decisions recorded on this date that the mocks embody

- Appearance and colour are **global shell state**, consumed by every page — `data-theme` /
  `data-palette` on `<html>`, one control in the persistent shell, `?mode=` and `?theme=` in the
  URL (#152). All eight mocks now carry it.
- The **Cluster Overview keeps its three cards** unchanged; the KPI work is a separate page (#157).
  Visibility stays closed; the Policy operator card is administrator-tier by explicit reversal (#169).
- The **drill-down** keeps tiles and tabs as doors; the search is an extra door, never a replacement.
- Navigation follows the live app's model everywhere: one history stack, `from` stored with the
  entry, an unchanged position replaces rather than pushes, a pasted deep link rises to its parent.
- Status is never colour alone: the four CR states carry distinct glyph shapes, and every non-ok
  state states what it costs.

## Retired renderings (superseded — not part of the inventory)

*Tab Blueprint* (the regression the contract replaced), *Your Access — Pivot* (the alternative
not chosen), the earlier *Your Access* (lateef.o), *Is Everything OK* (withdrawn), *Reports
Directory* (its design now lives in the Reports page, item 5).

## Not yet mocked

Kyverno (#165) — the data shape has to be discovered first; Kyverno is installed on CRC, so it can be.
