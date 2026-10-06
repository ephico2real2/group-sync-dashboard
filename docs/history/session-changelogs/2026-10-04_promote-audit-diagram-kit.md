# Session change log — group-sync-dashboard, 2026-10-04 → 2026-10-06

This log continues `docs/history/session-changelogs/2026-10-04_snapshot-clock.md`, from the moment its PR (#612)
merged.

- **Times.** PR merge times are in America/Chicago, from `gh pr list`. Lab readings are as the cluster printed them.
- **Measurement.** Every "measured" claim is one the session ran a command for; nothing below is recalled from memory
  alone.
- **Where the product change is described.** `docs/CHANGELOG.md`, application 5.2.0 to 5.8.0, chart 0.70.3 to
  0.70.12.

Outcome in one line: **release promotion shipped (#598); the docs were reorganised and audited in six batches; the
four defects the audit found were fixed, plus #626 and #600; and the diagrams of six repositories moved onto one
public renderer, diagram-kit. 20 PRs merged here, #613 to #635.**

| | Before | After |
|---|---|---|
| main | `7b1a2628` (#612), 5.1.0 / chart 0.70.2 | `d618b699` (#635), 5.8.0 / chart 0.70.12 |
| issues | #598, #600, #625, #626, #627 open | all five closed; #436 open (below) |
| diagram renderers | three copies that had drifted (this repository, the `/visual` skill, envoy-grpc-modernization) | one public kit, ephico2real2/diagram-kit v0.1.1, MPL-2.0 |
| lab dashboard CPU | the chart defaults: request 50m, limit 0.5 core | request 100m, limit 1 core |

---

## Part 1 — Build once and promote (#598)

### The spec, the code, the lab (2026-10-04 23:18 → 2026-10-05 02:00) — PRs #613, #614, #615

- #613 rewrote SPEC_P1 against main; #614 shipped `.github/workflows/promote.yml` and a `release` branch the lab can
  track (application 5.2.0, chart 0.70.3); #615 recorded the first promotion on the lab, and back.
- The repository now has three branches only: `main`, `gh-pages` and `release`.

---

## Part 2 — The docs: reorganised, then audited (2026-10-05)

### Reorganisation (03:08) — PR #616, and walk documents (03:23) — PR #617

- #616 sorted the docs into guides, design, reviews, research and history; the chart guides ship with the chart
  (application 5.3.0, chart 0.70.4).
- #617: walk HTML and PDF documents stay local and leave the tree (the operator's rule); `.gitignore` holds it.

### The audit, six batches (08:45 → 17:47) — PRs #618, #620, #621, #622, #623, #624

- Each batch checked its guides against the code and the lab, with a review record under `docs/reviews/`
  (`docs/reviews/DOCS_AUDIT_2026-10-05_b1_chart_operate.md` to
  `docs/reviews/DOCS_AUDIT_2026-10-05_b6_tutorials.md`).
- **Found by CI:** #621 was behind main (merged in, re-armed); the 5.5.0 publish hit a registry 502 on `:latest`
  (re-run); #624's runner could not reach the network over IPv6 (re-run).
- #619 (Dependabot) bumped anchore/sbom-action from 0.24.2 to 0.24.3.

---

## Part 3 — The defects the audit found, and two parked issues (2026-10-06)

### #625: four code defects (00:04) — PR #628, application 5.6.0, chart 0.70.9

- The CI chart-bump gap, prefix attribution in `provider_keys_for` (exact name first), `prepare-release --pr`, and the
  render-manifests cookie step.
- **Found by CI:** `mktemp -t` fails under GNU; a trailing-X template replaced it.
- **Codex** found that a prefix could orphan a label or give it two owners: **Accepted** on the two-owner case, fixed
  by exact-match-first. **Rejected** its longest-name rule.

### #627: KPI thresholds (00:40) — PR #629, chart 0.70.10

- A bad `gsd.kpiThresholds` value is refused at render, and the unit is stated (80 means 80 %).
- Helm's `--set` delivers decimals as strings, so the check is a regex; `--set key=null` deletes the key, so "is not
  set" has its own message.
- The issue claimed a value like "80%" fails the pod. That was wrong: the application falls back to its default.
  Corrected on the issue.

### #626: the query planner's statistics (04:58) — PR #630, application 5.7.0, chart 0.70.11

- Research, then `docs/specs/SPEC_Q1_planner_statistics.md`, then `local-development/gsd/store.py`: `PRAGMA
  optimize` runs at open and in maintenance when SQLite reports work, and each reader reconnects once the statistics
  move. Tests: `local-development/tests/test_store_statistics.py`.
- **Found by Codex Astra and OB3:** a statistics refresh that raised was fatal, and a failed reconnect left a closed
  connection cached. **Accepted**, both fixed: the refresh never raises.
- **Found by CI:** the runner's SQLite is 3.45.1, below the 3.46 the behaviour needs; 5 tests failed. The tests now
  skip there, and `local-development/image-proof.py` proves the behaviour on the image's SQLite 3.53.4.
- **Measured on the lab:** the Groups list on the `dashboard` cluster went from 103 ms to 0.8 ms.

### #600: unknown manifest keys (14:46) — PR #633, application 5.8.0, chart 0.70.12

- `local-development/gsd/reporting/artifacts.py` keeps the keys a newer build wrote, through a read and a rewrite.
  Test: `local-development/tests/test_reporting_manifest_unknown_keys.py`.
- **Measured on the lab:** the new report pod indexed 83 runs, and an unknown key survived a restart rewrite in the
  live 5.8.0 image. PVC UIDs unchanged: data `f065b7a4`, report artefacts `08c7d45c`.

---

## Part 4 — The lab's CPU (2026-10-06 05:46 and 13:26) — PRs #631, #632

- `environments/crc.yaml`: the dashboard's limit to 1 core (#631), then the request to 100m (#632). The operator's
  reason for the request: stability under contention, not throttling.
- **Measured:** at 0.5 core, 7.6 % of periods were throttled at 0.036 cores average; at 1 core, 2.3 % (2.3 s); at
  100m and 1 core, 3.3 % (2.31 s) at 0.047 cores. Node CPU requests after: 8812m of 11800m (74 %).

---

## Part 5 — One renderer for every repository (#436), 2026-10-06

### This repository — PRs #634, #635

- #634: #616's move left the design document's 8 `<source srcset>` paths pointing at a directory that does not
  exist, so readers saw broken figures. Fixed, and `local-development/tests/test_docs_images.py` now checks every
  relative image in every document. Doc tests: 1908 passed.
- #635: `docs/diagrams/remote-cluster-access/source.html` takes the 4.82:1 grey (`#5f6a77`; `#6b7684` was 4.04:1 on
  its wash, under WCAG's 4.5:1), and its four figures were re-rendered with the kit.
- **Found by OB1-lite:** "Joining a cluster" had been rendered on 2026-09-24, before its page changed, and still drew
  Rejoin (#316) and clusterAdminSar (#322) as proposed. The re-render shows them built. Figure 4's alt text in
  `docs/design/DESIGN_remote_cluster_access.md` still called them proposed: fixed, and a test fails when an alt text
  calls proposed what its figure does not.

### diagram-kit, published

- ephico2real2/diagram-kit is public under MPL-2.0; the template and examples are MIT-0, so a page started from the
  template carries no obligation. Tags v0.1.0 and v0.1.1.
- Its renderer refuses what a review of the SVG does not see: a fallback font, a label past its box, text under
  4.5:1 in either theme, a dashed arrow with no label, and sideways scroll at 375 px. 83 tests pass, on Linux in its
  CI too.
- **Found by Codex and OB3 (first review):** the font check proved only that some face loaded; a failed render
  overwrote the last good PNGs; the template was not in the package; and the standard overclaimed its pins.
  **Accepted.** Codex's font fix, as written, failed every real page: the browser refuses a font spec carrying
  `font-stretch: 100%`, and the fix swallowed the error. Corrected and measured before it was applied.
- **Found by OB1-lite (two later reviews):** a PNG name with a subdirectory broke the staged write; and a box
  painted over the start of an arrow let the box's own text pass as the arrow's label. **Accepted**, both fixed with
  tests.
- New, at the operator's request: curved connectors for many-to-many traffic and labelled dashed arrows for a
  relationship. The meaning of a dashed box (proposed) is unchanged.
- The `/visual` skill now lives in the kit, `~/.claude/skills/visual` links to it, and the global Claude settings
  name the kit as the default for every diagram.

### The rollout

- Measured first: 33 of 159 pages failed the kit, 18 of them the same 3 pages on six envoy-tutorial branches.
- The old grey moved to `#5f6a77` on all 36 pages that carried it, every page re-rendered, and the four hand fixes
  made: a label past its box, system fonts, unlabelled dashed arrows, and 14 texts drawn black in the dark theme.
- Merged: this repository #635, openshift-ipsec-nas #50, envoy-tutorial #30, envoy-grpc-modernization #1,
  mongodb-poc #30 and #6. openshift-upgrade became a private repository with the fixes in it.
- **Measured after the merges:** on each repository's main, the diagrams equal the reviewed branch, no old grey is
  left, and every page passes v0.1.1 (36 of 36). The six envoy-tutorial module branches, each fully merged, were
  fast-forwarded to main.

---

## Numbers

| | |
|---|---|
| PRs merged in this repository | 20 (#613 to #624, #628 to #635; #625, #626 and #627 are issues) |
| PRs merged in other repositories | 9 (diagram-kit #1; the rollout's 5; mongodb-poc #6; aurum-signal #1, a review document; cilium-policies-lab #1) |
| Issues closed | #598, #600, #625, #626, #627 |
| Review passes run | Codex and OB3 on the kit; OB1-lite three times (kit fixes, connectors, rollout); Codex Astra and OB3 on #626; Codex on #625 |
| Defects found by tooling rather than reviewers | 4 by CI (`mktemp`, SQLite 3.45.1, IPv6, the registry 502); 3 by the kit itself on the rollout (the font spec, the unfilled texts, the container box) |
| Longest single loss | Codex's untested font fix; the kit's reviews now run in real Chromium (OB1-lite), not in a sandbox without a browser |

## Where things are recorded

- The audit records under `docs/reviews/`, and `docs/specs/SPEC_Q1_planner_statistics.md`.
- The kit's `RESEARCH.md` (every page measured, the revisions after each review) in ephico2real2/diagram-kit.
- The memory notes *diagram-kit-is-the-default* and *scratchpad-files-can-vanish*.

## State left behind

- #436 is open. The kit is public, its CI is green, and every page re-renders through it. Each repository still
  carries its own renderer copy, which the issue's Definition of Done asks to replace with the kit; the operator kept
  them for this rollout.
- No open PRs across the owner's repositories.
- The lab runs 5.8.0 with the dashboard at request 100m, limit 1 core; the next `crc start` still owes the Argo CD
  end-to-end check.
