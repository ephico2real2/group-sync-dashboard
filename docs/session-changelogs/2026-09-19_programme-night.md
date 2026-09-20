# Session change log — group-sync-dashboard, 2026-09-19 → 2026-09-20

The night the operator asked for the whole design programme: "complete all our issues tonight and release
all the mockup as a fully functional app", after the release script's Argo mode and its `--values` switch
were finished. Times are git author times in America/Chicago; every "measured" claim is one the session
ran a command for; nothing below is recalled from memory alone. The lab (CRC) is Argo-owned throughout —
every reviewed head was deployed through the Application by `release-crc.sh --argocd` and walked
through the OAuth proxy before its PR was called ready.

Outcome in one line: **#212 finished and #216 merged (the script's two managers, `--values`, the guarded waiter); #204 fixed and merged (#217); the Reports page shipped (#173, #218); #149 R1/R3/R4 merged (#220), R5/R6 (#221) and R7 (#222) built, reviewed and deployed — every mock that had an owner is a page.**

| | Before the session | After |
|---|---|---|
| main | `a551718` (#215 merged) | `0da4fa7` (#220 merged) with #216, #217, #218 in between; #221 and #222 open, stacked |
| chart / app | 0.37.0 / 0.24.0 | 0.38.0 (#220) on main; 0.39.0 on #222 |
| CRC | Argo-owned dashboard at `62a9c17` | Argo-owned at `7fa4a6e` (#222's head): the Reports page, the status page, the forms live |
| The programme | #212 item 1 done; #204, #173, #149, #143, #153, #170/#165 open | #212 done bar the Flux example; #204, #173 closed; #149 R1–R7 implemented (R2 was already in); #143, #153, #170/#165 remain |
| Reviews | — | seven three-seat passes (#216, #217, #218, #220 ×2 seats + OB3, #221 OB3, #222 in flight), every finding decided in a `docs/REVIEW_*.md` |

---

## Part 1 — release-crc.sh: `--values`, the mode matrix, the waiter (2026-09-19, 21:45 → 23:42) — PR #216

### The feature (21:45 → 21:56) — `75dbeb3` … `3a9c2be`
- `--argocd [branch]` and the Helm↔Argo handover were already on the branch; `--values <repo-path>` added for
  both modes (`365697d`): Helm's `-f`, the Application's `valueFiles: [../../<path>]`; in Argo mode the file
  must be committed/pushed (or present at `origin/<branch>`), in Helm mode a local variant is exempt from
  the dirty check because the build context is `local-development/` with named `COPY` lines.
- Measured on CRC with a temporary fixture (`3a9c2be`): Helm with the explicit default file (`helm rev 1`,
  DEBUG), an untracked variant without `-dirty` (`rev 2`, INFO), `--argocd --values crc-info.yaml`
  (`valueFiles=["../../environments/crc-info.yaml"]`, INFO), `--argocd` back (DEBUG).
- **Found by the live run:** the waiter accepted the previous sync's `Synced/Healthy` for the second Argo
  run — the new sync started one second after it exited. **Fixed in `7deba92`**: `comparedTo.source ==
  spec.source` before Synced/Healthy/Succeeded; also `--allow-dirty --argocd` refused; the header matrix and
  `local-development/README.md` carry every combination; the review skill's Step 4 names the modes.

### Review pass and the fixes (22:02 → 23:31) — `e65f245`, `ed6341e`, `f651c17`, `7415fc3`
- Codex (xhigh), Grok, OB3 on one brief of ten claims. **Accepted** (each with a failing-before test in the
  new `tests/test_release_crc.py`, the scripts driven end to end against stub `oc`/`podman`/`helm` in a
  temporary repository with an `origin`): `--values --argocd` ate the option; the dirty exemption was a
  regex (`crc_yaml` exempted); `fetch || true` fell through to a stale ref; a symbolic `main` unchanged while
  main moved satisfied the guard (the caller passes the expected commit; a refresh annotation follows the
  write); reuse decided after both builds and on one tag; apply-then-patch = two writes the controller could
  see between (OB3 measured it in the Application's history: a 15 s sync of `main` with the published image);
  a failed `oc` ended the waiter silently under pipefail; `--build-only` said "built + pushed".
- **OB3 added** (`ed6341e`): `--argocd main --build-only` ran a cutover with nothing built; fetch by
  `refs/heads/<branch>` from `FETCH_HEAD` (single-branch clones); the values file checked before any build;
  the Helm-mode probe took any `oc` failure as "no Application"; a running sync finishes before the delete.
- **Rejected**: Grok's M5 (apply keeps a patched `valueFiles`) — measured the opposite on run D; Codex's
  `"` in a filename; Grok's `--request-timeout`.
- **Found by CI** (`7415fc3`): `mktemp -t argocd-wait` is BSD's prefix form; GNU says "too few X's" and
  set -e ended the waiter before its first line. Measured on ubi9-minimal; `python:3.14-slim` runs the 20
  tests green.
- Live at `e65f245`/`ed6341e`/`f651c17`: both guards on the first read, a Helm handover, one history entry
  per run, the refresh annotation absent when the waiter exits, Secrets rv `643531 643532` unchanged
  through eleven handovers. Record: `docs/REVIEW_release_crc_argocd.md`. CI green on `7415fc3`;
  **merged 23:42 (`88e6ea5`)**.

## Part 2 — #204, the status text tokens (23:10 → 00:24) — PR #217

- `ca65496`: the three text tokens re-solved per palette block by the smallest hue-preserving step that
  clears 4.5 on the hovered row, using the fixture's own compositing; `TEXT_ON_ROWS` gains them (31 failures
  on main's sheet, 487 pass).
- **Review** (`1a138c6`, `1a18f64`): **Grok** — the dark sheet's wash is 14 %, the fixture composed 10 %
  for both themes (accepted: read per theme; the dark tokens moved 2–4 % more). **Codex and Grok** — in the
  light CVD palettes `--warn` sat 0.5° from the vermilion critical (accepted: each palette's own warning
  hue, held at the Okabe-Ito reference's own 14°); `.kpi-page .chip.crit` on the chip's translucent wash
  4.06–4.31 (accepted: an opaque surface). **OB3** — read the painted pixels: Chromium truncates the blend
  after quantising alpha, so nearest-rounded solutions land 0.01 short (accepted: the fixture composes
  rounded away from the text; 11 cells re-solved); the count was nine variants / 3.96, not eight / 4.01; its
  rail finding routed to **#219**. Record: `docs/REVIEW_status_token_contrast.md`. The first merge attempt
  was refused (the head behind main); merged with `main` in; **merged 00:24 (`3607ef1`)**.

## Part 3 — #173, the Reports page (23:43 → 00:47) — PR #218

- `21f8ff1`: `report` joins `POSITION_KEYS` (the state renamed `view.report` — `currentPosition()` reads
  `view[key]`, caught by an existing test); a fresh tab is the catalogue alone; the form card carries its
  colour and a back control through `backLabel()`; the click lands the panel by arithmetic; the key under
  each title, the count; the runs table wrapped (found by the ordered 375 px sweep: with rows it widened the
  page).
- **Found on the deployed page** (`36883bb`): a pasted link left the form at 849 px on an 800 px viewport
  — only the click path landed. The landing moved into `render()`, once per arrival.
- **Review** (`f4fc71b`): all three seats — `report` rode onto every later position (a tab click kept
  it, the Reports tab reopened the form, a group's back control read the report's title); accepted at the
  chokepoint (`applyPosition`). OB3 — history Back stranded the names dialog; `aria-selected="null"`; the
  arrival rule made a re-click a no-op. Codex/OB3 — focus to `<body>` after Back; Grok — `.linkish` not
  `.back`. Six tests lifted from OB3's patch. Record: `docs/REVIEW_reports_page.md`. Walked at `7748b69`
  and `1be4298` (`reports/2026-09-20_reports-page-173/`), evidence on the issue with pictures; **merged
  00:47 (`0ff858d`)**.

## Part 4 — #149 R1/R3/R4, schedules and formats (00:21 → 02:48) — PR #220

- `59e8cd1`: a schedule names no cluster (the service fans out over the snapshot's enabled clusters);
  formats by origin (`reporting.formats`); `enabled: false` → `spec.suspend`; chart 0.38.0.
- **Review** (`0f26a31`, `5e3a51b`): both seats — a fan-out submitted one by one left partial 429s the Job's
  retry duplicated (accepted: **one queue slot**, all or nothing); a quoted `"false"` did not suspend;
  `formats: [json]` reached `--format`; the docs taught a plural `clusters:` never read. Codex — ids unique
  against the store; the trigger's single-run line; `{"runs": []}` exited 0. **OB3** — the PR's CI was
  **red on its own fan-out tests** (`from tests.reporting_seed` under CI's bare entry point; the module's own
  convention fixed it); `backoffLimit: 0` with an in-process retry only for a POST that never reached the
  service; an unlistable snapshot dir was a 500; the upgrade note. Record:
  `docs/REVIEW_schedules_and_formats.md`.
- **Found by tooling**: three pushes registered **no check runs** — `mergeable_state=dirty`; GitHub runs
  no `pull_request` workflow on an unmergeable PR (memory note *conflicting-pr-runs-no-ci*). Merged with
  `main` in; **merged 02:48 (`0da4fa7`)**.
- Live on CRC (from the stacked head `cb74ce1`): the three CronJobs as rendered (no `--cluster`, the
  paused one `suspend: true`), a fired schedule answering the fan-out shape resolved to `crc-local`, the run
  `done` with `bytes: {json, html}`.

## Part 5 — #149 R5/R6, the Reporting status page (01:0x → 02:5x) — PR #221 (open, retargeted to main)

- `a832540`: `#page=reporting` — the strip, the schedules (cadence in words from a new
  `gsd/reporting/cron.py`, effective retention, On/Paused, last success, next, `ok`/`late`/`never`/
  `disabled`), the history with server-side filters and paging; `GET /report/api/status`; the schedules to
  the report pod as `GSD_REPORT_SCHEDULES`; the R6 deviation (cron in-app instead of kube-state-metrics)
  posted on the issue with the reasoning. **Found on the way**: the auto-refresh fingerprint omitted the new
  payloads (the comment above it names that trap).
- **OB3's pass** (`425388a`): a 6,256-triple differential against croniter and a minute scan of both DST
  transitions — `fold` was ignored (a nonexistent 02:30 read as a fire; a next fire 45 min in the past);
  the late predicate's grace sat before the fire (every healthy schedule read `late` until its run
  finished); the per-schedule retention override **was never passed to the prune** (since the two-tier
  retention landed); a quoted `"false"` reached the page as On; `retention: {days: "twelve"}` 500'd the
  route; `as_of` repainted the page every poll; the filter race. All accepted from its patch. Record:
  `docs/REVIEW_reporting_status_page.md`. Walked at `cb74ce1` (`reports/2026-09-20_reporting-status-149/`).

## Part 6 — #149 R7, the report forms (02:5x → 03:33) — PR #222 (open, retargeted to main)

- `35f1460` (backend): `ParamSpec` `source`/`unit`/`advanced`/`group`; the Subject scope replacing the kind
  toggle; `group_mnemonic` resolved to the exact group through `reporting.namespaceGroupLabel` (the poller
  captures it as a third label); `login-activity` by group; `namespace-access` `group_by`;
  `GET /report/api/discovered?cluster=` — **the V4-F1 one-query guard caught the first cut's N+1** on the
  catalogue load.
- `7ea5864` (the shell): per-type controls, the lookups with type-ahead, Advanced, no cluster field.
  **Found on the way**: a test stubbing `reportGet` by call order caught a needless lookup fetch; a stubbed
  reply of another shape re-fetched on every paint (a render loop — 242 runaway processes before it was
  found); the smooth landing measured stopping 110 px in (instant now); `.num`/`.scope` collided with the
  app's classes (namespace-audit rows unclickable) — every class `rp-` prefixed.
- Live at `7fa4a6e` (`reports/2026-09-20_report-forms-149/`): 61 users / 62 groups / 13 mnemonics
  discovered on CRC, type-ahead, chips, the POST's params, the run done; the snapshot taken 27 s after the
  pod started predated the poller's first capture of the exact-group label — the next one carries it.
- `57b2c5c` (03:0x) — **Grok's ten findings, accepted**: dormant-access applied the Subject scope to one
  table of four; the default `group_by` rewrote every heading `(no mnemonic) · …` on a deployment with no
  captured labels; the users lookup read every row and parsed every providers blob (LIMIT cap+1); Advanced
  closed on the lookups' arrival (view state now); a keyboard-added chip dropped focus to `<body>`; the
  arrival re-landed a reader who had scrolled; the 422 detail was dropped; the operator README listed the
  keys the service refuses; the groups report's filter left the membership changes cluster-wide; a named
  subject with no binding vanished from the pack (a *Named but not bound* caveat). Chart 0.40.0.
- `f2ef728` (03:32) — **Codex (xhigh, 274k tokens) on `7fa4a6e`** reached the same ten independently;
  against `57b2c5c` three remained and were **accepted**: the login summary and its `attempts` total counted
  the cluster beside scoped users (`users=alice → attempts=3`) — scoped now, the first pass's "said in a
  note" retracted; a post-open `sqlite3.Error` in `discovered()` 500'd the route (wrapped as
  `SnapshotError`, the seam's pattern); `.rp-count-live` styled nowhere (the rule, and a guard over every
  `rp-` class the page writes). Docs: the CHANGELOG's migration sentence, the chart README's
  `namespaceGroupLabel` row, `docs/DESIGN_reporting_service.md` §7.3's column, a note in SPEC_C3.
  **Rejected**: an empty `Group:` section for an unbound group; the whole-method rewrite (it dropped the
  bounded reads); a three-document registry test. Both new tests fail on the old code (measured);
  hermetic 3884 passed, 15 skipped; `helm lint` clean. `docs/REVIEW_report_forms.md`. OB3 still running.
- `b528151`/`df9ebfb` — `main` (#221 at `650ec09`, 03:13) merged in; the first resolution dropped #220's
  CHANGELOG line, **found by a diff of the tail against main** and restored. #222 retargeted to `main`.

---

## Part 7 — #143 phases 2–3, the picker, the prefill, the totals preview (03:1x → ) — PR #224 (open, stacked on #222)

- `6f2c7c4` (03:20): `namespaces` in `discovered()` (`cluster_namespace`, LIMIT cap+1) and the Advanced picker
  with the text-field fallback; the reviewer prefilled from the catalogue's `viewer`, kept once edited; the
  str trimmer (a required blank is refused); `POST /report/api/preview` — `build()` only, `Semaphore(1)`
  → 429, 422/404/503 as a run — and the totals beside Generate, debounced, versioned, keyed once per
  form+cluster, a 422 shown as the refusal. **Found on the way**: the fixture discovers namespaces, so the
  PDF test's `page.fill` on the old text field timed out (the picker's id; Advanced opened first); the
  call-order `reportGet` stub of the view-affordance test counted the picker's lookup fetch as the preview
  GET (the lookup settled first); an unscoped namespace-access form previews "select at least one
  namespace…" — the test asserts the refusal, then `1 namespaces · …` after a pick. Hermetic 3882 passed
  (the discovered key-set assertion widened after), UI 452 passed; the Reports class 31 passed after the
  merge of #222's pass (`44587ce`). Review: Grok, Codex xhigh and OB3 launched on `44587ce`.

---

## Numbers

| | |
|---|---|
| Commits authored | 45 on main by 02:48, plus #221 (5) and #222 (5) |
| PRs merged | 5 (#216, #217, #218, #220 — and #215's follow-ups counted in the previous log) |
| Review passes run | #216 (3 seats), #217 (3), #218 (3), #220 (3), #221 (OB3), #222 (3, in flight) |
| Reviewer findings accepted / rejected | 60 accepted (all with failing-before tests) / 5 rejected on measurement |
| Defects found by tooling rather than reviewers | 7 — the waiter's stale Synced (the live run), the pasted link not landing (the deployed page), `mktemp -t` on GNU (CI), the runs-table overflow (the ordered sweep), the N+1 (the one-query guard), the render loop and the class collision (the UI suite), zero CI runs on a dirty PR (`gh`) |
| Full suite, final (forms branch) | UI 451 passed; hermetic 3878 passed, 15 skipped |
| Longest single loss | ~40 min on the smooth-scroll landing at 375 px — three probes, the second of which broke `scrollTo` itself by forwarding `(a, b)`; written down in the commit and above |

## Where things are recorded

- `docs/REVIEW_release_crc_argocd.md`, `docs/REVIEW_status_token_contrast.md`, `docs/REVIEW_reports_page.md`,
  `docs/REVIEW_schedules_and_formats.md`, `docs/REVIEW_reporting_status_page.md`; the PR comments on #216,
  #217, #218, #220, #221.
- `reports/2026-09-20_reports-page-173/`, `reports/2026-09-20_reporting-status-149/`,
  `reports/2026-09-20_report-forms-149/`.
- Memory notes: *release-crc-modes-and-values*, *conflicting-pr-runs-no-ci*; *argo-owns-grafana-on-crc*
  and *helm-values-files-are-the-source-of-truth* corrected (the dashboard is Argo-owned by default).
- Issues: #219 filed (the hover rail); #149's evidence and the R6 deviation posted.

## State left behind

- CRC: the dashboard Argo-owned at `7fa4a6e` (#222's head, chart 0.39.0); `grafana` and `group-sync`
  Argo-owned; the three schedule shapes in `environments/crc.yaml`; a poll captures `company.net/oud-group`.
- Open: #221 (CI waiter armed on `108a073`, merges on green), #222 (reviewers running; retargets to `main`
  after #221). Remaining programme: #143 phases 2–3, #153, #170/#165, #212's Flux example, #210, #219.
- Worktrees: `gsd-grafana` (detached at main), `gsd-204` (feat/173 — reusable), `gsd-173`, `gsd-149`
  (feat/149-forms), `gsd-changelog`.
