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

## Part 6 — #149 R7, the report forms (02:5x → 04:2x) — PR #222 (merged `5e6b699`)

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
- `d886e78` (04:0x) — **OB3 on `7fa4a6e`** (470k tokens, 49 min; a labelled snapshot, a Playwright harness
  with fetch counts, focus after every id-less control, scroll positions, reduced-motion emulation): the
  same as Grok and Codex, and five more, **accepted** — a certification naming a mnemonic the deployment
  cannot resolve built a clean empty pack (0/0, nothing said, four states measured) → a failed run with
  the reason, the Scope line printing the resolved groups; the mnemonic key is a POSITION
  (`namespaceSelector.labels[0]`) → documented in `values.yaml` and the chart README; an explicit list
  re-sorted when nothing grouped it → the reader's order; the lookup menu lost by a repaint under a
  non-matching query ("zzz", a repaint, "kube" → no match) → rebuilt from the discovered set; "none
  discovered" while a fetch was pending → "loading…"; Enter on ×/Clear/a segment dropped focus → refocus
  / ids; the Advanced state recorded on the click too (the `toggle` event is a queued task). OB3's
  premise check: Chromium animates `scrollTo({behavior:"smooth"})` under reduced motion regardless of the
  stylesheet — the instant landing was right for everyone. **Not taken**: `default_from` on the ParamSpec
  (the page prefills in #224), the `oud-groups` set on the wire (noted). Three catalogue tests and four
  UI tests fail on the head without the fixes (measured); the class-rule guard caught its own wrapper
  class (a data attribute now). Hermetic 3886 passed, 15 skipped; UI 457 passed; `helm lint` clean;
  chart 0.40.1. CI green on `d886e78`; **merged** at `5e6b699` (04:2x) — the evidence with pictures on
  #149 (pinned to `66e8715`), the decisions on the PR.

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
  merge of #222's pass (`44587ce`). Review: Grok, Codex xhigh and OB3 launched on `44587ce`; deployed to
  CRC through Argo (`running : 44587ce783 — verified in-pod`) and walked (`reports/2026-09-20_picker-preview-143/`,
  `6be9506`): 106 namespaces in the picker, `'group-sync' → ['group-sync-dashboard', 'group-sync-operator']`,
  the preview POST → `200 {"totals":{"namespaces":1,"group_bindings":0,"user_bindings":0},"truncated":false}`,
  `reviewer: prefilled 'kubeadmin'`, an unscoped form → `preview: select at least one namespace…`, 375 px
  no overflow, `errors : []`.
- `ef91c74` (04:3x) — **Grok and Codex xhigh** refuted the same three claims, **accepted**: the totals
  stayed beside Generate after either Clear and painted cluster A's beside cluster B for the debounce
  (both Clears schedule them; keyed by cluster); the tests pinned "sorted and non-empty" and Generate
  once, the 429 test never re-POSTed (the seed's list, the exact sentence, the release after the join, a
  422 inside `build()`, an unconfigured selector label); the README's answer shape and "when a cap bites".
  Volunteered and taken: `(cluster-scoped)` offered first (Grok); "1 namespaces" → singular (Codex, the
  twenty-entry noun table **rejected**). **Rejected**: pre-slot target validation (the run POST is
  asynchronous by design), dropping `aria-live`. #222 merged meanwhile; the forms pass merged in and #224
  retargeted to `main`. Hermetic 3892 passed, 15 skipped; UI 459 passed; `helm lint` clean.
  `docs/REVIEW_picker_preview.md`. Deployed and re-walked at `ef91c74` (`27af538`): `(cluster-scoped)` first
  among 107 options, `1 namespace · 0 group bindings · 0 user bindings`, `errors : []`; the evidence with
  pictures on #143, pinned to `27af538`.
- `6c8b960` (05:0x) — **OB3 on `44587ce`** (424k tokens, 52 min; a parity matrix of preview vs run — 422 texts
  identical on seven inputs — a side-effect diff across five previews, release under real threads, a
  Playwright drive of every change path): five narrow refutations, all **accepted** — `Snapshot()`'s own
  `SnapshotError` (a torn or newer-schema copy) sat outside the 503 guard → a 500 per debounce; the
  lookups' arrival repaint re-created the focused input with its caret at 0 ("abc" then "XYZ" → "XYZabc")
  → `render()` restores it; the help promised "Overrides the Scope"; a padded `namespace_prefix` on an
  existing schedule changes meaning under the trimmer → said in the CHANGELOG; the module docstring's "one
  non-GET". Volunteered and taken: the picker's head counted the offered `(cluster-scoped)` as discovered;
  one retry ~1.5 s after a 429 (a viewer's own superseded preview can hold the slot). The independent-slot
  deviation from the issue's text noted on #143. Five of six new tests fail on the head without the fixes
  (measured). Hermetic 3895 passed, 15 skipped; UI 462 passed. Deployed and re-walked at `6c8b960`
  (the same lines; `errors : []`); CI green on `6c8b960` and `1993111`; **merged** at `af5c269` (05:2x);
  #143 closed with the evidence and the independent-slot deviation posted. `main` deployed to the lab
  (`running : af5c269990 — verified in-pod`); the six merged branches and three worktrees deleted after.

---

## Part 8 — #153, the trailing tabs at the bar (05:4x → 07:1x) — PR #225 (merged `1ef1dc8`)

- Before designing, the six mock tabs and the six live tabs were captured side by side: the live pages
  were already on the token system (#152 had removed the inline styles — one `style=` left, a series
  colour), so the uplift is the delta to the Namespace-audit bar, not the mock's skin. `43f1ee2` (05:5x):
  Groups gains a KPI row from `/api/clusters`' whole-set counts (the Overview card's numbers, never the
  rows a state filter narrows), rails on Empty/Unattributed, a `.drill` button for the name (the keyboard
  reaches the drill-down; a row was click-only), the owner-dot rule under the table; Users: rails on the
  two problem tiles when they hold anyone, provider chips; Access granted: the review rail; Usage: the
  footnote as three paragraphs with lead words. Four tests. Walked at `06ef60e` (`reports/2026-09-20_tab-uplifts-153/`):
  the KPIs equal `/api/clusters` (62/0/0) and hold under `state=empty` (rows 0), Enter drills, the rails
  and chips, four tabs at 375 px with no overflow, `errors : []`.
- **Found by CI** on `06ef60e` (the reviewers' sandboxes could not launch Chromium; my local run had
  filtered by keyword and missed it): an existing test read the row's LAST chip for the identity
  caveat's title, and the provider chip was last — the assertion reads the status cell; the provider chip
  carries its own title.
- `286c222` (06:3x) — **Grok and Codex xhigh**, both refuting M2, M6 and the owner-dot sentence,
  **accepted**: a never-polled cluster (`status` null, integer zeros from an empty `group_state`) painted
  0 / 0 / 0 → the tiles hidden while `status` is null; the tests' overflow line never set 375 px and the
  hides, the rails at zero, the table inside `.scroll-x` and the footnote were unpinned → five tests;
  `crSlot()` indexes the provider label in the sorted, flattened provider list, not the CR's position →
  the sentence says so. Grok's leftover accepted: the Logins provider cell as a chip. Codex's M5
  **accepted on the fact, snippet rejected** (the lead replaces the connective; saying both says it
  twice). The three review tests fail on the page without the fixes; hermetic 3897 passed, 15 skipped; UI
  471 passed; guards 526. `docs/REVIEW_tab_uplifts.md`. Deployed and re-walked at `286c222`.
- `5b48c51` (06:5x) — **OB3** (pinned clones of the head and the base; four seeded servers incl. a
  never-polled cluster, call counts at every chokepoint for four drill paths, chip line boxes at six
  widths, contrast from pixels in two modes × five palettes): the same as the others and three more,
  **accepted** — the footnote's third split sat inside a sentence with five words gone → the base's
  words restored, led by their own first words (my first-pass "the lead carries the clause" reversed:
  the contract's "keep the words" is the later ruling); `ldap-local` a two-line pill at every width →
  `.chip { white-space: nowrap }`, measured safe on every chip site; the Overview tile's critical
  "Bindings to review" beside a warning "Need review" rail → the rail carries the worst finding
  present; mutants (unconditional rails, row-counted tiles) passed the first tests → three more pins.
  OB3's three tests fail on the head without the fixes (measured); hermetic 3897 passed, 15 skipped;
  UI 474 passed. Deployed and walked at `78816f6` (the footnote's leads as the base's words;
  `errors : []`); CI green on `6076044`; **merged** at `1ef1dc8` (07:1x); #153 closed with the
  evidence and pictures.

---

## Part 9 — #219, the hover rail (07:2x → 08:5x) — PR #226 (merged `2581539`)

- `b350c14` (07:2x): OB3's rule from the review of #204, applied as proposed — every `.rowlink` table's first
  column keeps 3 px clear of the inset rail; one test (fails on `main`: "starts 0.0px in"). Deployed and walked
  at `67cca41` (`reports/2026-09-20_hover-rail-219/`): `first cell ink in / header ink in / rail painted [3, 3, True]`
  on Groups and Users.
- `08a8ab0` — **Grok**: the specificity story was wrong (`:where()` zeroed the `:has()` only → `(0,1,1)`; the
  KPI page's 18 px won by source order; the claim's table list false) → the comment and CHANGELOG say what the
  cascade does; the issue's own table (the user-History "− left" row, bob by position) and two preserved tables
  tested. `6f269ed` — **Codex**: a synthetic `.audit-table` with a rowlink row measured 3 px (its own 0 lost by
  order) → the second `:where()` on `:first-child`, the rule at `(0,0,1)`, a synthetic probe `[0, 3]`.
  `3fddd47` — **OB3** (fifteen rowlink tables hovered and pixel-diffed on three sheets: rail x = 0..2, ink from
  x = 3, zero ink pixels under it): the stale "(0,1,1)" comment the Codex pass left, the own-padding test, the
  fifteen-table sweep. UI 479 passed; guards 526; CI green; **merged** (08:5x); #219 closed.

## Part 10 — #170 step 0 and the Kyverno module (07:5x → ) — PRs #227 (merged), #228 (open)

- `9042b22` (08:0x): a discovery record measured on the lab. **Found by OB3 (re-measuring on CRC with the
  v1.19.1 and OTel sources) and Grok (from the source)**: the record was right where it measured and wrong
  where it interpreted — finding 10's cause is the per-policy opt-in (`status.conditionStatus.message: "skip
  generating ValidatingAdmissionPolicy: not enabled."`), not the CEL, and a generated policy reports under the
  VAP alone; 9 CEL results (6 + 3) with no `rule` key; `source.go` has four `Kyverno<Kind>` sources and no
  `KyvernoDeletingPolicy`; three breaker circuits on three endpoints; `resource_namespace` is a label on three of
  Kyverno's own families; two Group-matching `ClusterPolicy` objects can never report (an RBAC gap); "removed
  in 1.20" unsourced; the time misstated — and the **merged 09-19 step-0 record (PR #205) had probed finding 10
  already and was not cited** (a forensic failure: the docs index was not grepped before writing). All corrected
  at `a5df364`; `docs/REVIEW_kyverno_discovery.md`; CI green; brought up to date with `main` (`10bb8df`).
- `0989e4b` (09:1x) — the module, built to the corrected facts: the reader (runtime discovery, paging, the
  family by `source`, generated policies mapped to their policy, the resource UID in the key, all three breakers
  summed), the store (migration 18, three-valued presence, the appeared/cleared history), the binding-cadence
  stage, `GET /api/clusters/{id}/kyverno`, four public metrics with no name and no namespace, the chart's grants
  (0.41.0), the Kyverno tab. **Found on the way**: `ago()` recursed on a future instant until the stack blew (a
  fixture stamp 40 min ahead of the browser killed the page) — fixed; the migration pins moved to 18; a UI wait
  matched "Loading…"'s empty-note (a race in the full run) — keyed on the payload. Hermetic 3927 passed, 15
  skipped; UI 476 passed; helm lint clean; guards 536. Deployed to CRC; the walk, the three seats and CI pending.
- `60eeb0f` (06:50) — the walk at `0989e4b` (`reports/2026-09-20_kyverno-170/`): 115 reports, 667 legacy results
  not shown, 9 CEL results, three breakers summed (12 505, no drop), `errors : []`, 375 px without overflow.
- `d9a6f38`, `599039b` (07:08) — **Found by OB3** (N1–N3) and CI: three pins the module moved — the schema at 18
  in the binding-events upgrade test, `kyverno_result_event: None` in `history_retained_since`, the environments
  README row quoting `crc.yaml`'s `kyverno.metricsUrl` verbatim (the guard compares the two columns).
- `da46d4e` (07:22) — **Grok's and Codex's pass** (`docs/REVIEW_kyverno_module.md`): **Accepted** the `Namespaced<Kind>`
  twins listed under the family kind (Grok N1 / Codex M2 — a cluster using namespaced policies alone read
  `policies: 0` beside its rows), `?kind=` beside `?policy=` (Codex M5 — two kinds sharing a name answered
  `total=2`), `kyverno_result_counts()` for the metrics (Codex M6 — every scrape materialised every row: 82 ms
  and 16.7 MiB at 10 000 rows), the CHANGELOG entry (both — lost in a `git stash` cycle around the merge of
  `main`), `list`-only grants (Codex M7), the switch keeping focus and `data.kyverno` in the auto-refresh
  fingerprint (both, M8). **Rejected** Grok's Unreleased-section guard (it would refuse every release:
  `prepare-release.py` empties the section — eight `test_prepare_release` failures, measured) and Codex's opt-in
  default (the operator's rule: switches default on). Re-walked at this head (`84b4a03`).
- `9e8ef02` (07:46) — **OB3's pass** (its column in the record): **Accepted** F1 every served report group read
  and the one carrying Kyverno's reports named (a served-but-empty `openreports.io` group masked 115 reports —
  its test failed on the head); F4 `kyverno_metrics_url_for()` — the in-cluster breaker URL was handed to
  every cluster; N4/F6 readiness from `status.conditionStatus` — no CEL CRD defines `status.conditions`, and
  the page had printed the VAP-generation message as the readiness note (the lab's status, `oc get
  validatingpolicies … | jq .status`); F7 `breaker_configured`; F2 `max_length=317`; the policy buttons' ids;
  N5 step 3's watch and the LIST cost (330 KB / 0.28 s for 112 reports) now said as deferred. **Kept** OB3's
  Unreleased guard (it skips when the section is absent) over Grok's. OB3's harness and five mutant pins folded
  into `tests/test_kyverno.py` (37) and `TestKyvernoPage` (5); its 10 000-row timing test dropped (it measures,
  pins nothing). Hermetic 3964 passed, 15 skipped; UI 485; helm lint clean. Deployed; re-walked (`4392d5a`):
  the policy row reads `yes` alone, `breaker_configured: true` on the loopback, breaker_total 12 839.
- `4f93ad1` (08:21) — **#228 merged** on the head's green rollup (`mergeStateStatus CLEAN`; `gh run list
  --commit` does not index the docs commit's run). The evidence with pictures on #170; deferred to its next PR:
  the audit-log denials (step 5), the readiness signal (step 6), the metadata watch with 410 recovery (step 3).

### #229 — the report library, the issue and the mock (08:30 → 09:30)

- **The operator**: scheduled reports run, but where are they? Measured before answering: `/report/api/status`
  (three schedules; `nightly-namespace-access` ok, last success 06:16; `quarterly-compliance` never;
  `biweekly-groups` paused) and `/report/api/runs` (8 runs — 4 scheduled, 4 manual; 6 done, 2 failed). The
  history table with download buttons EXISTS, on the Reporting-status page behind one `linkish` button: no
  expiry, no run detail, no reason for a failed run, no schedule → report link. **The operator's ruling**: the
  Reports and Reporting-status pages stay as they are; the library is a new tab, a new canvas, one section per
  configured report, headed the way people say it ("the quarterly reports"). Issue #229 written on those facts.
- **Cursor Grok** drafted the mock in the background from the issue, the two pages' source, the three committed
  mocks and the lab's payloads embedded verbatim. **Found by the render-check, not by reading**: the output
  was cut off mid-string and resumed with a sentence spliced into a template literal — a syntax error, a blank
  page; run cards were `<button>`s containing `<button>` chips (invalid — the parser closed each card at the
  first chip); "goes when a newer one lands" was wrong against `prune()` (rank < K is kept whatever its age);
  "Nightly" was a regex on the schedule's *name* (now the service's `cadence`); the drawer opened on load; a
  long label overlapped its value at 375 px. All six fixed; 375/768/1280 in both themes, no errors, no
  horizontal scroll, the unknown-run sentence. Published as an artifact for the operator; not committed.
- **Operator**: "I love the design" — the mock committed as `docs/design/report-library-mock.html` (`240e25d`
  on `feat/229-report-library`); the link words settled as "Generate this report →" / "Generate another →".
  The implementation handed to a background fork (spec first: `docs/specs/SPEC_E1_report_library.md`).

### #230 — cluster configuration as labelled Secrets; #119 answered (10:0x → 11:3x)

- **Operator**: "did we extend authentication to other clusters with username/password?" Answered from the
  code, posted on #119: tokens only (`ClusterConfig` has `tokenFile`/`tokenEnv`, no password field); the
  chart mounts a fixed volume set so a remote entry's `tokenFile` names a path nothing mounts; #119's
  design (PR #120) has neither P1 nor P2 built. **Operator**: a new direction — clusters as labelled Secrets,
  Argo CD's model, a Cluster Configurations tab, GitOps parity. Researched and cited (Argo's
  `argocd.argoproj.io/secret-type: cluster` contract, `argocd cluster add`'s `argocd-manager` SA, the
  informer, the ApplicationSet cluster generator's label selection); issue **#230** written with the Secret
  contract, discovery, the tab, the security stance and the S1/S2/S3 decomposition; S1 handed to a fork.
- **Operator**: token renewal "the way Kubernetes does it". Researched: the OAuth server's
  `grant_types_supported` measured on CRC as `authorization_code, implicit` — no refresh tokens, renewal is
  re-authentication; `oc login`'s single request (`openshift-challenging-client`, `X-CSRF-Token`, the 302
  fragment with `access_token`/`expires_in`); `accessTokenMaxAgeSeconds` default 86400; the kubelet's 80 %
  rule and client-go's exec plugins (re-invoked on expiry or on a 401). **P2 redesigned** on #119: a
  `CredentialProvider` module with an `OAuthPassword` provider, the token in memory only, the GroupSync poll
  as the health call.

### #231 — the Flux example; #232 the handover; #212 closed (10:2x → 11:3x)

- `61999c2` (10:2x) — `examples/flux/helmrelease.yaml` (a `HelmRepository`, one `HelmRelease` per chart,
  `dependsOn`); validated against the upstream `helm.toolkit.fluxcd.io/v2` / `source.toolkit.fluxcd.io/v1`
  CRD schemas (jsonschema, the CRDs fetched from the controllers' repositories); each `values` rendered with
  its chart at the pinned version; the chart README's "Deploying with Flux or Kustomize" (chart 0.41.1 — a
  packaged README, the CI predicate excludes only Chart.yaml). Flux is not on CRC; the apply is not measured
  and every document says so.
- `7158542` (11:1x) — **the three seats** (`docs/REVIEW_flux_example.md`). **Accepted** OB3 C4: `crds:
  CreateReplace` removed — the openshift-grafana chart's `crds/` contract is "only when absent", OLM owns the
  CRDs once the operator is in, and helm-controller force-applies them on every upgrade (read at the v1.6.4
  source); the orchestrator's own draft had documented the hazard instead of removing it — **retracted**.
  **Accepted** OB3 C3: helm-controller never re-renders a deployed release on the interval, so the
  `dependsOn` order is load-bearing — said. **Accepted** Codex/Grok/OB3 C8: `timeout: 15m` on the grafana
  release (the gate's ceiling 720 s vs helm-controller's 5 m default); Grok C8: cluster-scoped Flux ≥ 2.3,
  OpenShift GitOps is Argo, the OperatorGroup clash; OB3 N1: `tests/test_flux_example.py` (fails on the
  reviewed head); N2 the Chart.yaml history line. **Rejected** Grok C2 (pin 0.41.1 — unpublished; the example
  must install when read). 929 passed, 14 skipped; helm lint clean.
- `79a9d68` (11:3x) — **#231 merged** on the head's green rollup after a merge of main (BEHIND); **#212
  closed** — Helm, Argo CD, Kustomize, Flux all covered.
- `88e401f` (11:0x) — **#232 merged**: `docs/HANDOVER_2026-09-20.md`, written when the operator's token was
  nearly out, then ruled the **living state document** (updated by a small docs PR on every move; PR #234 is
  update 1). **Found by the operator**: both forks had stopped while waiting on background work — the #229
  fork's suite had finished (4 guard failures: the specs-index row, three type-scale guards) with nobody to
  read it; restored from that point. Lesson written into both forks' briefs: never stop without a waiter
  that wakes you; the orchestrator now watches each fork's suite file and hands the result back.

---

## Part 11 — the design pass, the tier model and the Fable re-review programme (11:3x → 14:0x)

The account changed mid-session (the previous one hit its weekly limit) and every background fork died with
it; all three were restored from their worktrees, which is why this part reads as re-entrant. The usage panel
showed **Fable on a separate weekly pool** from the main limit — recorded as a standing scheduling rule
(memory *fable-has-a-separate-weekly-pool*): Fable seats never trade against the Opus budget, so re-reviews,
spec drafts and extra seats run in parallel rather than in turn.

### OB2's design review — four of seven claims refuted (Fable 5.1, live SARs on CRC)

- **The tier ladder was not a ladder.** A user bound to the stock `ClusterRole/admin` by a ClusterRoleBinding —
  the lab carries **seven** such bindings — answers `no` to `list clusterrolebindings` and `no` to
  `update clusterrolebindings` but `yes` to `get`/`create secrets`. Measured with `oc auth can-i --as --as-group`.
- **The S2 head let the auditor, and with restrictions off an anonymous caller, write cluster Secrets** — it was
  never rebased onto S1's resolver (`git merge-base --is-ancestor` proved it). Fixed in the branch.
- **#239 did not close #114** and its migration section described no observable change; the compatibility knob
  was dropped and the claim withdrawn.
- **#119 rested on a false premise:** the OAuth CR and the GroupSync CR name **different accounts** on the lab
  (`ocp-oauth-bind-serviceid` vs `ocp-ldap-bind-serviceid`), so `discover: oauth` would have paired one
  account's password with another's username. `discover: oauth` dropped.
- **#238 corrected twice:** the minted token must not be written into the GitOps-owned cluster Secret (a second
  labelled credential object, referenced), and `expirationSeconds` needs a ceiling and a floor — measured,
  `oc create token --duration 8760h` was honoured, so "bound and expiring" was only as true as the ask.
- **Found by the S1 fork, in OB2's own fix:** its ordering patch used `usage_scope` as the lower rung, which
  dissolves under `userActivity.visibility: all` and again when `visibility.enabled` is off. The rung is asked
  directly instead, past both escape hatches, with two mutant-checked pins. *A correct finding does not make
  its fix correct* — the fourth time that rule paid this session.
- **Operator ruling, 2026-09-20, which then reversed the ordering entirely:** *"A user with cluster admin and
  auditor is fine. That is how Kubernetes RBAC works."* Each tier asks its own SAR and composes nothing — RBAC
  is additive; the SAR is the action's own question, so whoever passes `create secrets` can write the Secret
  with `oc` and the dashboard's ServiceAccount grants nobody a permission they lack; and the "no auditor"
  ruling holds anyway because the pure auditor persona answers `no` to both questions (`lateef.o`, measured).

### The Fable re-review programme (#210) — four of seven done, all four confirming OB3

Run on **`ob1-lite`** (Fable 5.1, default effort — a new agent tier), each re-judging OB3's verdicts against
**main as it stands**, not the branch as reviewed.

- **#231 (Flux):** holds outright. Re-measured against helm-controller **v1.6.4**, source-controller **v1.9.5**,
  Helm **v4.2.4** and today's published index; `crds: CreateReplace`'s hazard re-derived at the source; four
  mutants each caught. The agent retracted a failure of its own harness rather than reporting it.
- **#228 (Kyverno):** holds — **18 mutants**, each caught by exactly the intended test. **Two gaps found:** a
  rewrite of the reader's `!= "True"` to `== "False"` **survived the whole suite** (37 passed), and four
  comments still described the pre-F1/pre-F6 code. → **PR #241**, merged `da4def4`; both fixes proven to fail
  before and pass after, with the mutant restored and the tree verified clean.
- **#226 (hover rail):** holds in full — specificity re-measured in Chromium against a `(0,1,1)` variant, both
  mutations failing exactly the right tests.
- **#227 (discovery):** every lab and source claim holds (112 reports, `{KyvernoValidatingPolicy: 6,
  kyverno: 667}`, 0 of 6 CEL rows carrying a `rule` key, the background controller serving **no**
  `kyverno_breaker_*` line at all), **but six statements in the discovery documents described a module we do
  not have** — the reader, the store key, the stored fields, the policy list. → **PR #243**, merged `9e2a077`,
  plus a **paint-level** test for #219: every existing test measured geometry, never ink, which is what the
  issue was about; it fails with the rule deleted.

### The tier model's spec — PR #242

Drafted on Fable in its own worktree (docs-only, so it could not collide with the three code branches). Its
persona scan across **497 ClusterRoles** found twelve that pass `update clusterrolebindings` — none bound to a
human but `cluster-admin`/`system:masters` — and one release trap: `rbac-auditors.yaml`'s guard reads
`adminSar`, so T2's rename would **fail every default chart render** unless re-pointed. It also measured
`bob.wilson` — an auditor-group member with cluster-wide `edit` — passing both cluster-admin questions, which
is the case the operator's no-composition ruling settles: he is admitted deliberately, because he can write
that Secret with `oc` whatever the dashboard shows him.

### Merged this part

`7f75131` **#240** (the design index says what is implemented — five rows had understated it), `da4def4`
**#241**, `9e2a077` **#243**. The mock programme finished: ten mocks, eight implemented, two in flight.

### Two process defects, both fixed in place

- A mutant script raised before restoring the file it had mutated, leaving `reader.py` broken in the worktree;
  caught on the next read, restored, and the proof re-run with the restore in a `finally`.
- The PR waiter fired on GitHub's optimistic `mergeStateStatus` while a new commit's checks were still
  registering, so a merge was attempted against a half-registered rollup. Replaced with one that requires
  **every** check concluded.

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
