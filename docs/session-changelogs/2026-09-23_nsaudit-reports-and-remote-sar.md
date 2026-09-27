# Session change log — group-sync-dashboard, 2026-09-23 → 2026-09-24

What this session did, when, and how each claim was measured. Times are git author times in America/Chicago; a PR's
merge time is its squash commit's on main. Every "measured" claim is one the session ran a command for; nothing below
is recalled from memory alone. Numbers are quoted as a PR body, a commit message, a review record or a report states
them, and each says where it comes from; where a PR's review decisions are written nowhere in the repository, the
entry says so. The session began at 04:11 on 2026-09-23; this log runs to 2026-09-25 02:30: #338's close
at 08:52, the cleanup, Part 7, and Part 8 (2026-09-25). The product changelog (`docs/CHANGELOG.md`) says what each release changed for an operator; this
says what a working session did. The review decisions of #336–#345 are itemised in
`docs/REVIEW_remote_sar_for_every_join.md`; Part 6 cites it rather than repeating every line.

Outcome in one line: **twenty-eight pull requests merged. Login capture reads the audit log by default. #261's Namespace audit parts 2 and 3 shipped, and the issue closed. The 2026-09-23 release was deployed through Argo CD and walked (84/84 steps, 15/15 release checks), and its one defect was fixed (#332). The operator's mandate was built end to end: SPEC_D2b was reviewed on six heads and merged with 221 blocks (#339), implemented from those blocks alone as application 0.32.0 and chart 0.53.0 (#342), and walked on the lab (Steps 0–11, then the e2e walk at 84/84). #338 closed with its evidence. In the evening, #312, #346 and #347 were fixed (#350, #352, #354) and proved on the lab, and the specs and design indexes were brought to the evidence (#351). On 2026-09-25 #353 (the unmanaged finding on every subject, with the operator's platform rule), #293 (ConfigMap onboarding) and #340 (the CA cache) closed, each proved on the lab: thirty-nine PRs in all. In Part 10, #322 (the cluster-admin tier) and #321 (the OAuth Debug path removed) shipped, each walked on the lab and closed with its evidence. In Part 15, Epic C was released as application 1.0.0, the first MAJOR under the operator's new versioning rule, which a required CI check now enforces (#428). Epic C's composition fixes (1.1.0), Epic D's Refresh (1.2.0) and shared-URL warning (1.3.0), and #432's fix (1.4.0) followed, and 1.4.0 runs on the lab: eighty-four PRs in all.**

| | Before the session | After |
|---|---|---|
| main | `cb64f81` (#307 merged, 2026-09-22 17:28) | `6a83e3e` (#438 merged, 2026-09-27 12:06). Through Part 10, `e5459e0` (#375 merged, 2026-09-26 00:10); through Part 7, `b647db4` (#354, 2026-09-24 20:00); the tag `checkpoint-2026-09-23` is on `7c0a42c`, and `checkpoint-2026-09-26` on `9da9234` |
| chart / app | 0.51.0 / 0.31.0 | **0.59.6 / 1.4.0**; 1.2.0 to 1.4.0 are under Unreleased in `docs/CHANGELOG.md`. Part 15: 1.0.0 (Epic C, chart 0.59.2), 1.1.0 (0.59.3), 1.2.0 (0.59.4), 1.3.0 (0.59.5), 1.4.0 (0.59.6). Through Part 14, 0.58.8 / 0.37.0; through Part 10, 0.58.0 / 0.36.0; through Part 7, 0.53.1 / 0.32.0; Parts 8–10 add U1 (0.54.0 / 0.33.0), S5 (0.55.0 / 0.34.0), #367 (0.55.1), #368 (0.56.0 / 0.34.1), #322 (0.57.0 / 0.35.0) and #321 (0.58.0 / 0.36.0) |
| deployed on the lab | not recorded in the repository | `6a83e3edda` (#438's merge), application 1.4.0, by Argo CD's auto-sync; `/api/version` read in-pod (#432). Through Part 10, `667b3c4a62` (#373's merge) through `release-crc.sh --argocd`, verified in-pod |
| open PRs | #309, #313, #317, #320 | #430, a draft held by the operator |
| issues | #261 open (part 1 shipped in #264; parts 2–4 not built), #318 open | closed: #261, #318, #332, #338, #346, #347 and #348. Opened: #321, #322, #332, #338, #340, #341, #346, #347, #348 and #353. #341 is deferred; #312 and #353 are handed to OB1. Part 15 closed #114 (decided), #415, #427 and #432 (#432 by a commit message, before its fix: Part 15), and opened #420, #425, #426, #427, #432, #435 and #436 |

---

## Part 1 — the reviewer seat and the audit-log default (2026-09-23)

### OB3 pinned to Opus 5.5 (05:09 → 05:31) — commit `d7b1d24`, PR #323

- At the operator's instruction, the adversarial-review skill's two mentions of OB3 name Opus 5.5 and
  `model: claude-opus-5-5`. Only `.claude/skills/adversarial-review/SKILL.md` changes; merged as `a9f0875`.
- **Measured** (the commit message): a one-turn probe, `claude -p … --agent ob3 --output-format json`, named only
  `claude-opus-5-5` in `modelUsage` before the pin and after it, so the loader accepts a full model ID in agent
  frontmatter. The agent file lives at user level; the PR body names its backup, claude-config `a9ab07a`.
- Review decisions not recorded in the repository.

### Login capture reads the audit log by default (04:25 → 05:40) — commits `f1b6010`, `21172d5`, PR #320

- The PR's first commit, `26d0bf6`, was authored at 02:38, before the session: `loginCapture.source` moves from
  `pod-log` to `audit-log`, chart 0.51.0 → 0.52.0. Its message records an end-to-end run on the reference cluster:
  an `oc login` at 07:34:49Z, read at 07:35:04Z, stored as `kind=cli provider=developer identity_match=developer`.
  Suite **4719 passed, 16 skipped**.
- #318 (opened 01:38) had asked for this flip, and a correction on it at 01:45 said **do not flip**: the audit-log
  grant is a ClusterRole with `get` on `nodes/proxy`. **The operator's decision at 04:25 superseded that
  correction:** *"we are moving away from oauth debug option to using audit-logs"*. The grant's cost is stated
  where the choice is made, and it narrows with `loginCapture.auditLog.nodeNames`.
- In the session: `f1b6010` (04:25) marks the chart's pod-log text and `authLogLevel` deprecated, reduces the
  README's verbosity section to pod-log only, and corrects the 0.14.0 rationale's "scoped to one namespace" claim.
  `21172d5` (04:43) opens the `authLogLevel` stanza with a DEPRECATED banner. Both touch comments and docs only.
  Suite at each: **5279 passed, 20 skipped** (the commit messages).
- #321 opened at 04:16 to remove the Debug path: the three `auth-loglevel-*` templates, the pod-log reader and its
  mock. #320 merged at 05:40 as `b57a584` and closed #318. New document: `docs/AUDIT_LOG_CAPTURE.md`. The release
  note is the chart 0.52.0 entry under `docs/CHANGELOG.md`'s Unreleased heading.
- Review decisions not recorded in the repository.

### #322 — the cluster-admin tier, decided and not built (04:59)

- Issue opened with the operator's decision. A new tier, `visibility.clusterAdminSar`, asks
  `update clusterrolebindings` on the host. It gates the Cluster Configurations tab (view and manage), the KPI page
  and Rejoin (#316). Nothing was built this session. Part 5's design composes with it (its §10).

---

## Part 2 — cluster credentials: three documents merged, SPEC_S4c reviewed (2026-09-23)

### Three documents written before the session (05:41 → 06:07) — PRs #317, #313, #309

- All three were authored before 04:11: #309's `c98589e` at 2026-09-22 17:26, #313's `5d7c1f2`, `5f13c9f` and
  `32120b2` from 20:53 to 21:00 that evening, and #317's `0ea9a60` at 01:33. The session merged main into each
  (`3f62ae6`, `26b4231`, `b2ddba9`) and then merged them: #317 at 05:50 (`7df3552`), #313 at 05:58 (`4dd1f3f`)
  and #309 at 06:07 (`8eb73d9`).
- **#317** adds `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md`. An LDAP account bootstraps the connection
  and a long-lived ServiceAccount token polls. The polling token has no `exp` by design: renewing it would turn a
  once-per-onboarding bind into a recurring one. Merging main after #320 put its chart bump on top of 0.52.0, making
  it **0.52.1** (`3f62ae6`). The PR body reports helm lint clean and **1525 passed, 15 skipped**.
- **#313** adds `docs/polling-and-discovery.md`. How soon a cluster enters the fleet depends on how its Secret was
  written. Measured on the reference cluster (its commit messages), both through the GitOps path: **8m30s** from
  `oc create secret` to the first poll, **3m42s** for an `oc patch` rotation to be noticed. A lapsed token stays
  accepted until somewhere between **+56 s and +62 s** past its `exp`.
- **Found by Cursor Grok**, recorded in `5f13c9f` before the session: the document had said a refresh on a
  `userSelfLogin` cluster is a bind. It is not today, because `userSelfLogin` is a pending kind that never reaches a
  client. **Accepted**: the constraint now attaches to `saTokenLookup`. Docs citations **961 passed, 12 skipped**.
- **#309** adds `docs/REVIEW_S4b.md`, the Step 5 record that #295 merged without. It indexes SPEC_S4b's
  orchestrator's notes and #295's comments across three rounds, **7 → 5 → 2** findings. It records the implementer's
  two departures from the brief, the rejection of both fixes offered for R3-2, what is not held (replica mutual
  exclusion) and the correction of four false claims. Docs citations **952 passed, 12 skipped** (the PR body).
- Review decisions not recorded in the repository for #317, #309, or #313 apart from the finding above.

### SPEC_S4c — the credential lifecycle (09:12 → 10:55) — commits `be0c7dc`, `078ebfd`, PR #325

- The spec itself, `5e53dff`, was written on 2026-09-22 at 17:56. It is #285's design: the daily ping, `self-login`
  renewal at `expires_at − min(2 h, ¼ lifetime)`, and a per-credential gate held on a fleet-account Lease. It is a
  spec only: `docs/specs/SPEC_S4c_credential_lifecycle.md`, 893 lines by the PR body.
- Its claims were reviewed as C21–C23 in the second pass of the day's brief: Codex, Grok and OB1-lite, recorded in
  `docs/REVIEW_2026-09-23_release.md` and the spec's Orchestrator's notes.
- **C21, found by all three**: the gate was one entry per target, so T clusters on one fleet account could present
  one wrong password T times, and a lockout is per directory account (#315). Grok and OB1-lite proposed a 401 per
  account and a 500 per target, which keeps R2-1. Codex proposed gating every bound failure per account, because a
  locked account's 500 (LDAP code 19) cannot be told from a sick target's 500. **The operator chose Codex's rule,
  reversing R2-1.** The price is stated in §5 question 7: one sick target stops binds on every target of that
  account until the password rotates or the entry is cleared.
- **C22, found by all three, accepted**: the versions become app 0.32.0 and chart 0.53.0, in four places.
  OB1-lite's test was taken. **Rejected**: Codex's test, which pinned "current chart + 1 minor" and would break as
  soon as another PR bumped the chart first.
- **Found by the Grok confirmation pass, accepted**: §3.1 and §3.6 still keyed the gate on "(target, password)";
  both now say "(account, password)", and the pin test lists the old phrase (`078ebfd`).
- Two tests fail on the previous head and pass on `be0c7dc`. Specs index, docs citations and diagrams:
  **1365 passed** (the commit messages). Merged at 10:55 as `048e928`.

---

## Part 3 — the Namespace audit: #261 parts 2 and 3 (2026-09-23)

### The agreed mock on main (06:34 → 10:46) — merges `710a376`, `c27892d`, PR #324

- The mock and its capture were authored on 2026-09-21, in six commits. The session merged main in twice and then
  merged the PR as `8791dec`: 23 files, all additions, no application code. `.gitignore` conflicted and was resolved
  to main's version (#254's bare `.venv` pattern).
- Adds `docs/design/nsaudit-mock.html` and `docs/design/nsaudit-feature-capture.md`, render-checked with
  **177 checks**, and **41/41** caveats reachable across ten driven states (the PR body).
- **Found by OB3**: the capture README's "41,078 px to 21,354 px" at 375 dates from the first mock commit,
  measured before the fold and the pager, and no state of the mock reaches it now (the highest is 16,689 px). The
  README keeps it as the record of that commit. Tests: **1703 passed, 12 skipped** (the PR body).

### OB3's first pass, and five PRs drafted from it (09:31) — commits `4a7b7ee`, `4b2297b`, `933e103`, `5b6b1ed`, `17c75d2`

- OB3 (Opus 5.5, max effort) reviewed #261 parts 2–4 against main `8eb73d9`, merged at 06:07, and drafted the code.
  It confirmed every part 2 and part 3 gap and found part 4's height comparison stale (#324's body).
- **#326**: the platform line counted a hidden namespace that still holds a finding but named nothing. It now names
  up to three and says "This hides rows, never findings".
- **#327**: CLUSTER-WIDE was ranked as a row of "Exposure by namespace". It moves to its own "Cluster-wide direct
  grants" card. The worklist's namespace cells, previously plain text with 0 `[data-ns]`, become drills.
- **#328**: the namespace page's "Also reached cluster-wide" was one 975-character paragraph with 16 links naming
  53 bindings on the lab. It becomes a KPI tile, a split and a disclosure.
- **#329**: the worklist now says when Find namespace is narrowing only the Namespaces card. The "Who is exposed"
  names are separated, where a copied cell used to read `asmithbwilliamsjdoe`.
- **#330, found by OB3 without being asked**: the zebra rule (specificity 0,2,3) outranked the risk tints (0,2,1),
  so a Critical or High row on an even row lost its tint (measured `rgba(0,0,0,0)`). The index row's drill had no
  id, so a keyboard reader's focus fell to `<body>` at every 60 s poll.
- Each PR's new tests fail on main and pass on the branch. UI + accessibility per PR (the commit messages): #326
  1099, #327 1100, #328 1098, #329 1099, #330 1099.

### The second pass: 23 claims on the integration head (fixes 10:29) — commits `96bdea7`, `05a30a9`, `ce87be1`

- Codex, Grok and OB1-lite (Fable 5.1) reviewed integration head `d86acd6`, which is main `8eb73d9` with all seven
  PRs merged. The record states the limits: Codex's sandbox refused Chromium, so its UI claims are structural; Grok
  traced from source; OB1-lite measured on a copy.
- **C2/C3, found by Codex (Grok on C3): accepted on the fact; Codex's three-way sentence rejected.** Two requests
  under two snapshots could name a namespace the worklist did not hold yet. At the self tier, "your grants above" is
  a page capped at 200 rows. The wide tier now names only what the rollup holds, and the self tier says "still
  among your direct grants" (`96bdea7`).
- **C9, found by OB1-lite: accepted** as written. `view.nsWideOpen` survived a cluster switch. The new test fails
  with `[True, None, '']` and passes (`05a30a9`).
- **C11, found by Grok, Codex and OB1-lite: accepted on the fact; Grok's snippet rejected.** The orchestrator's own
  sweep over 240 name lengths found the dot leading a line at 17 (375 px), 17 (393), 4 (768) and 2 (1280). Grok's
  `white-space: nowrap` overflowed the cell (scroll width 522 in 230). A no-break space still separated 14 of 240
  at 375; OB1-lite tried that and retracted it. The fix keeps the last code point and the separator together:
  **0 separations, 0 overflowing cells** at all four widths (`ce87be1`).
- **C8 overturned OB3's first-pass risk**: `member_count` cannot print "null", because the store coalesces it to 0.
- C16, the suites on the integration head: Codex 537 passed with 570 Chromium launch errors, OB1-lite 1107
  passed. The orchestrator's full run: **5339 passed**. A **Grok confirmation pass** then covered the fix commits.

### Merged in sequence (10:56 → 11:48) — #326 `2ad23da`, #327 `a2f5ae6`, #328 `145a50c`, #329 `31a07bc`, #330 `7f1856a`

- Each branch took main before merging. #329's one conflict was the worklist table's opening line: #329's note,
  then #327's table-or-empty branch. It was resolved as the integration branch had tested it (`72dc29b`,
  UI + accessibility 1109). #330's tests are a union at their shared anchor (`2393a93`, 1111).
- **Found by the orchestrator, before the suite** (the record's own errors): while composing #327, a JavaScript
  comment moved out of a `${…}` expression into the template literal, where it would have rendered as text in every
  worklist row.

### The CI race on #329 (09:46 → 10:09) — commit `42e3f7d`, PR #331

- **Found by CI** on #329 (run 35874897863):
  `TestLookup::test_a_committed_ime_composition_opens_the_lookup_once` read `#page=lookup` where
  `#page=lookup&cluster=crc-local` was expected. It had not failed in any other of the last 60 `ci` runs (the PR
  body).
- The mechanism: `navigate()` writes `#page=lookup` synchronously, and `refresh()` amends the same history entry
  with the default cluster once `/api/clusters` answers. The test waited on `view.page` alone. A one-off harness
  holding `/api/clusters` open reproduced CI's exact value on every run. The change is test-only: `TestLookup`
  **21 passed** on five consecutive runs. Merged at 10:09 as `b9cde37`.
- Reviewed by Grok (the record). Its one REFUTED point was that the new wait times out on an empty cluster list.
  **Not acted on**: that cannot happen with the fixture, and a bounded timeout is correct there.

---

## Part 4 — the release deployed and walked; the reports fixes (2026-09-23)

### The walk's own defect (13:11) — commit `04c30f5`, PR #334

- Main `7f1856a920` carries the eight merges #331, #324, #325 and #326–#330. It was deployed through
  `release-crc.sh --argocd`: Synced/Healthy, image `0.31.0-7f1856a920`, the commit verified in-pod
  (`reports/2026-09-23_release-walk/README.md`).
- **Found by the walk**: the first run failed one step (80/81). The namespace-access report was refused with
  "select at least one namespace, by selector, mnemonic or explicit name", and the fault was the walk's, not the
  product's. Since #143/#149 that parameter is a lookup picker inside the form's Advanced section, and the walk
  skipped any parameter whose text field it could not find.
  `local-development/e2e-walk/e2e_capture.py#fill_param` now drives the picker, and a required parameter with no
  control is recorded as a failure. The re-run on the same deployment: **84/84, 24/24, 11/11**.

### #332 — a focused picker option under the sticky Generate bar (13:09 → 13:43) — commits `956e611`, `0c8daf9`, `ddd7265`, PR #333

- **Found by the walk**: its capture of the namespace-access form showed the Generate row drawn over the open list.
  Measured on the lab (main `7f1856a`, 1440×900): **16 of 40** focused options hidden, a failure of WCAG 2.2
  SC 2.4.11. #332 opened at 13:09.
- The fix is technique C43, `scroll-padding-bottom` applied while the form is on the page (`956e611`, 7rem).
- **Found by Grok (C4): accepted on the fact; snippet rejected.** 7rem had been measured before the totals preview
  painted. The bar measures 44 px up to 160.5 px (320 px wide, two clusters), so Grok's 10rem (160 px) falls
  0.5 px short of the tallest bar. A ResizeObserver now writes the bar's real height into the padding (`0c8daf9`).
  The guard fails on the 7rem head at 320 (160.5 vs 112) and at 375 (142.5 vs 112).
- **Found by the Grok confirmation pass (C5): accepted.** The guard waited a flat 200 ms for the observer; it now
  waits until `--report-actions-h` equals the bar's height (`ddd7265`).
- UI + accessibility **1116 passed** (`0c8daf9`); the two #332 tests 5 passed on three consecutive runs
  (`ddd7265`). Merged at 13:43 as `e3b3731`, redeployed as `e3b3731b78`, re-measured: **0 of 40** hidden.

### The evidence committed (14:06 → 14:27) — commits `9ea1022`, `5276e77`, PR #334

- `reports/2026-09-23_release-walk/` holds the evidence: the walk **84/84**, the second pass **24/24**, integrity
  **11/11**, and `reports/2026-09-23_release-walk/validate_release.py` **15/15**, which checks #320's audit-log
  capture and #326–#330 on the lab's data. The PDF walk document, the report PDFs and the walk PNGs are not
  committed, for size (the operator).
- **Found by Grok, accepted**: three README numbers were not in the committed files. "16 tabs" is 14, a tile value
  the check never recorded is 53, and "76" captures is 75. All three were corrected. **Rejected**: "no
  `screenshots/` directory". Ten PNGs are committed there; the reviewer's ask mode does not list binaries.
- Docs citations **996 passed, 12 skipped** (`5276e77`). Merged at 14:27 as `7e68a93` and deployed as
  `7e68a93565`.

### #261 closed (15:54)

- The evidence comment on #261 covers parts 2 and 3, merged as #326–#330. They were deployed (`7f1856a920`, then
  `7e68a93565`, each verified in-pod) and validated by the release checks (15/15) beside the walk (84/84), with the
  screenshots pinned to `7e68a93565ceb02fb2e21619c558aeda535e0292`.
- **Part 4 decided, no code** (the operator, on OB3's recommendation). Main measures **3,344 px** at 375 on the
  lab's data with no sideways page scroll, and stacking every table would add 58–68 %. Sideways scrolling inside the
  tables stays.

### The release checks prove what they claim; the day's review record (15:57 → 16:34) — commits `d92f5b7`, `3d98e4b`, PR #335

- **Found by the orchestrator during the walk**: three checks proved less than their names.
  - The #320 check accepted the oauth-proxy's `session` row; it now requires `kind=credential`.
  - The #330 check counted even rows across every table; it now counts per `tbody`.
  - The #328 check recorded the tile's presence but not its value; it now records both.

  The corrected script, re-run against `7e68a93565`: **15/15**, committed as a second results file beside the
  first run.
- `docs/REVIEW_2026-09-23_release.md` is written. It records every claim by reviewer, each decision and its reason,
  the snippets rejected with the measurements that rejected them, the operator's C21 ruling, and the orchestrator's
  own errors.
- Codex, Grok and OB1-lite reviewed #335 against the raw outputs. **The record, all three, accepted**: three
  verdict cells had re-polarised the reviewers' words and now carry the reviewers' own (Grok CONFIRMED on C21 and
  C22, Codex CONFIRMED on C16). **Codex, accepted**: the PR count is ten, not eleven, and "8/8" needed its source.
  **Codex, accepted on the fact, snippet rejected**: the model names are attributed to the invocations rather than
  deleted, since they are true provenance. **OB1-lite, accepted**: the sweep numbers are marked as the
  orchestrator's, the 0.5 px as arithmetic, and its own C11 trial as retracted rather than rejected.
- **The script, found by OB1-lite, accepted.** The #320 check matched any ISO-8601 field on a row, so a backfilled
  older login would pass; it now compares only the row's own `at`. The #330 check could not tell an opened section
  from one that never opened; it now opens `button[data-ns-grants]` and fails if the section stays hidden.
  `reports/2026-09-23_release-walk/test_validate_release.py`: **3 failed before, 5 passed after**. The record
  calls Codex's and Grok's no-change verdict the weaker reading.
- **Found by the orchestrator** (the record): a per-PR file check in zsh passed an unquoted file list as one
  pathspec and reported "none" for every PR. It was caught, retracted and re-run with a proper split.
- Docs, citations, walk and diagram tests: **1336 passed, 12 skipped** (the PR body). Merged at 16:34 as `db1339b`.

---

## Part 5 — remote cluster access: the design, D3 and the mandate (2026-09-23)

### The design record (16:30 → 17:51) — commits `0088c5c`, `408d33e`, `cf51bef`, `17787e6`, PR #336

- Why, as the PR body gives it: the operator is cluster-admin on the lab but saw only their own rows on
  `shared-rnd` and `shared-qa`, because both resolve to `visibility=self-only`. Asked with the token the dashboard
  holds for `shared-rnd`, that cluster's own RBAC answers **allowed** for `kubeadmin` and `jane.smith` and
  **denied** for `asmith` and `tmp-contractor-9931`. Yet `remote-sar` is refused for every Secret-declared cluster,
  because the resolver that asks a remote is built once at start-up, from values only.
- `docs/DESIGN_remote_cluster_access.md` defines `inherit` + `same-as-host` against `remote-sar` + `same-as-host`,
  shows how `remote-sar` decides and fails, and records the lab's measurements with their commands, the support
  matrix and the decisions. Its figures have light and dark variants and text twins, with the source page at
  `docs/diagrams/remote-cluster-access/source.html`. `docs/ACCESS_CONTROL.md` §11 links to it.
- Round 1 (Codex, Grok, OB1-lite; decisions in `408d33e`):
  - **All three, accepted**: §4, Figure 2 and its table presented D4's finding and D5's sentences as current
    behaviour. The table now has "today" and "proposed" columns.
  - **Codex, accepted**: Figure 2 left out listing the reader's groups on the remote.
  - **All three, accepted**: a parser comment said a runtime `remote-sar` cluster "would fail open", but
    `viewer_scope` fails closed. The comment in `local-development/gsd/clusterconfig/parser.py` is the PR's only
    change outside docs, and it is a comment.
  - **OB1-lite F3, accepted**: the design's consequences now require the parser to refuse `remote-sar` without
    `identity: same-as-host`, as values loading already does. This is design text; no code changed.
  - **Grok C9, accepted**: the `#gh-*-mode-only` fragments are deprecated, confirmed against GitHub's docs.
- The operator's direction, recorded in the same commit: `remote-sar` + `same-as-host` is the standard (D2), and
  joining or rejoining with a username and password is a cluster-admin action checked on the host (D7).
- Round 2 (Codex, Grok, OB1-lite, each "mergeable after the named changes"; `cf51bef`): C1, C3, N1/F2, F3, C5,
  C6(d), C7, C8 and C10 **accepted**, each re-checked against the source. **Rejected snippets, facts accepted**:
  Codex's seven-row table and its rewrite of all of §7.
- Grok's confirmation pass on `cf51bef` (`17787e6`) confirmed nine of the ten fixes and found one new defect.
  Figure 2 lacked the unexpected-exception path that its twin carries
  (`local-development/gsd/kube.py#TierResolver._resolve_and_cache`). **Accepted on the fact; snippet rejected**: a
  separate footer line replaces Grok's 150-character line.
- Docs, citation and diagram tests **1337 passed** (the PR body). CI: 7 passed, `grype` skipped
  (`gh pr checks 336`). Merged at 17:51 as `b21f80b`.

### D3, the mandate, and the outcomes figure (17:58 → 18:57) — commits `9d4798b`, `e7936c7`, `cb23a21`, `0b81d98`, `b56e60e`, PR #337

- **D3**, the operator: *"this is all OpenShift and everyone appears as a user … just focus on the users that you
  see in OpenShift users."* A reader is matched on another cluster by the `User` object's name, with no
  identity-provider distinction. No code changes: `remote-sar` already names the host username in its review
  (`9d4798b`).
- **The mandate**, the operator: *"this is what I want: remote-sar for whatever method the cluster was joined."*
  **D6 was decided against** the `inherit` stopgap that the orchestrator's earlier recommendation had proposed.
  `shared-rnd` and `shared-qa` stay `self-only` until D1 ships (`e7936c7`).
- A figure of the operator's table shows what `inherit` and `remote-sar` show four people on a remote
  (`cb23a21`). The two middle rows are derived cases and marked as such; kubeadmin and asmith are the lab's
  measured answers.
- Review (Codex, Grok, OB1-lite, each "mergeable after the named changes"; `0b81d98`):
  - **All three, accepted (C4)**: the page's decision cards did not match the table.
  - **Codex F3/F5, accepted**: D4's finding is recommended, not built.
  - **Codex C2/F1, accepted**: the host is the entry that declares `dashboardController: true`, else the first
    enabled one (`local-development/gsd/config.py#Settings.host_cluster`).
  - **Rejected**: OB1-lite's permanent test that parses the page's decision cards, as a prose test.
  - **Routed to D1's code PR** (found by all three): the "clusters share an identity provider" wording in the code,
    the chart and the page.
- Confirmation (`b56e60e`): OB1-lite (Opus 5.5, high) found R1–R4 fixed and Figure 2's F1–F5 confirmed, and its
  N1 was fixed. Grok found it mergeable as is. N2 is routed to D1's code PR.
- `test_docs_citations` + `test_docs_diagrams` **1344 passed**; markdownlint reports 0 issues on the design
  document (the PR body). Merged at 18:57 as `7c0a42c`.

### #338 and the checkpoint tag (18:57, 20:37)

- #338 opened at 18:57, turning the mandate into an issue. Its Definition of Done:
  - `remote-sar` works for a values stanza, a hand-made or tab-made Secret, and `saTokenLookup`.
  - A remote with no policy resolves to `remote-sar` + `same-as-host`.
  - A failing remote is asked at most once per hold window.
  - The result is deployed with `release-crc.sh --argocd`, with evidence on the issue.

  It lists D4's finding, D5, #322 (D7), #316 (D8) and `inherit` on remotes as out of scope.
- Tag `checkpoint-2026-09-23`, made at 20:37, is an annotated tag on `7c0a42c`. **Measured**:
  `git ls-remote --tags origin checkpoint-2026-09-23` shows tag object `9348a3d`, and
  `git rev-list -n1 checkpoint-2026-09-23` returns `7c0a42c`. Its message: main before D2b, the deployed image
  `7e68a93565`, and "Not a chart release".

### #341 — the whole-UI redesign, deferred (19:49, 19:56)

- **#341** asks for a whole-UI redesign covering every tab, the header and navigation, and the shared components. The
  API would be extended additively only, tiered like its neighbours and specified first.
- **Deferred** by the operator: *"I want this app to be functioning first"*. The comment at 19:56 records it: the
  redesign waits until the app is functioning end to end, and it does not run in parallel with D2b. The few UI
  changes D2b needs shipped with #338.

---

## Part 6 — SPEC_D2b: specified, reviewed, built, walked and closed (2026-09-23 18:58 → 2026-09-24 08:52)

Every review decision below is itemised, with the reviewer's own verdict, in
`docs/REVIEW_remote_sar_for_every_join.md`. The spec's Orchestrator's notes hold them round by round.

### The spec and its first review (18:58 → 19:25) — commits `ac194fe`, `da5037e`, PR #339

- **`ac194fe`** (18:58) is the spec for #338. The orchestrator wrote it from a read-only map of main `b21f80b` and
  from lab measurements, and its header says so. It specifies:
  - per-request resolvers, keyed by a connection fingerprint;
  - `remote-sar` + `same-as-host` as a remote's default;
  - a 30 s hold for a failing remote;
  - redacted review errors;
  - the auditor binding on each remote, as a prerequisite outside this repository.
- **Found by CI:** `ac194fe` failed (`gh run list`). The specs index counted `D2b` as a programme row, and the
  header lacked `Release`; OB1-lite's N1 named the cause. Every later head of #339 passed.
- **Round 1:** Codex (xhigh), Grok and OB1-lite (Opus 5.5, high). All three said "implementable after the named
  changes". The decisions are in `da5037e`:
  - **Found by all three, accepted:** the hold let every distinct viewer through during a failure. OB1-lite measured
    5 attempts for 5 viewers in one hold. Its probe design was taken. **Rejected:** Codex's cluster-wide attempt
    lock, which would have serialised every healthy viewer's first review.
  - **Accepted:**
    - Grok's catch that the merge dropped every cluster that exists only as a Secret.
    - Redaction before truncation (all three; OB1-lite measured a leaked JWT prefix).
    - One configuration snapshot per lookup (Codex).
    - The served pair on the `cluster-resolved` line (OB1-lite).
  - **Decided between reviewers:** only the lookup's own Secret takes its stanza's policy (Codex's rule), because
    SPEC_S3 says an unowned Secret over a declared cluster wins.
  - **Rejected:** a `__contains__` on the resolver map, an Authorization-header capture for redaction, and a setting
    for the hold.
  - **The operator decided:** `group-sync-operator-helm` installs the auditor objects on every remote.
- **#340, found by Codex** (C2(e) of this round): the trusted CA bundle is cached by its path, not by its content
  (`local-development/gsd/config.py#_trusted_ca_context`), so a bundle replaced in place is not used until the pod
  restarts. Grok recorded the same cache as a note. #340's body says OB1-lite confirmed it; that report was a
  message, so this log cannot check it. **Out of scope:** it was opened as #340 at 19:25, and it is still open.

### The apply tool, OB3's deep pass and the 154 blocks (19:37 → 22:20) — commits `b8e75b0`, `6b65a4e`

- **`b8e75b0`** (19:37) adds `local-development/apply-spec-blocks.py`; #339's squash merge brought it to main. Its
  message records the operator's rule: implementation works from the finished, written document, not from memory.
  - The tool checks that every Old text occurs exactly once against a tree, and applies the blocks.
  - It refuses a git tree with uncommitted changes.
  - The format is in `docs/specs/README.md`, under "Implementation blocks".
- **Confirmation passes on `da5037e`:**
  - Grok found R1–R9 fixed: "implementable as specified".
  - **OB1-lite, found:** N1, code blocks that raise NameError where the prose puts them; N2, a follower stealing a
    stuck leader's slot called inside a 30 s hold (`calls=['v', 'v']`); N3; and N4.
- **OB3's deep pass on `da5037e`** (Opus 5.5, max):
  - **Found by OB3:** D1 (its F1), D2 (F2), D3 (§6 understated a cost that is serial across remotes, 15.06 s for
    three unreachable ones) and M1 (§5 could not be executed). Not asked: F3, F6 and F7.
  - **All accepted** (F1 through OB1-lite's N2 fix). OB3 wrote them in as the writer of the blocks.
  - **Decided:** OB1-lite's N2 gate over OB3's F1 guard. F1's guard left one page burst reading mixed tiers
    (measured: a probe `all`, its four siblings `self`).
- **D5 is in scope** by the operator's go-ahead, relayed by the coordinator. D4 stays out.
- **`6b65a4e`** (22:20): §7 becomes 154 implementation blocks in 44 files, written by OB3, which does not review its
  own blocks. The orchestrator checked every block against a clean export of `b8e75b0`. The applied copy's
  non-browser suite: **4892 passed, 20 skipped, 0 failed**, and OB3's browser run 593 passed (both from its commit
  message, on #339).

### The blocks reviewed (→ 23:13) — commit `890f04c`

- **The reviewers:**
  - Codex (xhigh) applied the blocks: 4900 passed, with 2 sandbox socket errors.
  - Grok ran in ask mode and could apply nothing.
  - OB1-lite applied them: 4902 non-browser and 593 browser tests passed, and each of 19 mutations was caught by a
    new test.
- **Accepted, as 46 correction blocks:**
  - `@tier_first` on thirteen per-cluster routes, which had decided a remote tier inside their read snapshot
    (OB1-lite F1: read depth 1 at every decision).
  - `alert_scopes` on `/api/alerts`' own predicate (OB1-lite F2, Codex B4).
  - Every lookup drops the resolvers of clusters that can no longer be asked (OB1-lite N3).
  - The hold's public wording names the first in-flight burst (Codex B8/B9).
  - The design document and its figures describe D1 and D5 as built, re-rendered by the new
    `docs/diagrams/render.py`.
  - §5's Step 4 waits for the lookup's rewrite (OB1-lite F4).
  - Step 7's restore keeps the live `resourceVersion` (Codex B11).
- **Rejected:**
  - Codex's retry-the-snapshot loop.
  - Its regression file: five of its seven tests match prose or execute the spec's own text.
  - Its request for per-test red/green proof.
- The applied copy: 200 blocks, and **4911 passed, 20 skipped, 0 failed** (the `890f04c` commit message).

### The confirmation pass (→ 00:24) — commit `12d9d8d`

- **Found by Grok, accepted:** Figure 3's page caption still called D5 a proposal, and the design's §8 D1 and D6
  still read as unshipped.
- **Found by OB3, applied as written:** F1–F8.
  - Its F4 measured Step 7's restore with the real `oc` 4.22.13 against a recording API stand-in. The command as
    first written sent the live `resourceVersion` itself: `replaced`, exit 0.
  - **Codex B11 is recorded as refuted**, and the restore was reverted. The orchestrator had accepted B11 without
    measuring it (#210's row says so).
  - The orchestrator stopped OB3 after its draft report, because of its token cost (the orchestrator's summary).
- 209 blocks. The applied copy: **4922 passed, 20 skipped, 0 failed** (the `12d9d8d` commit message).

### Codex on `gpt-6-astra`, and OB1-lite (00:24 → 00:56) — commit `8460257`

- **The operator's rule for this pass:** *"remember codex review must give us full code solution to any findings in
  file"*. The invocation, as the operator gave it:
  `codex --model gpt-6-astra --config model_reasoning_effort="high"`. Both reviewers wrote their fixes as spec blocks
  to a file.
- **Found by both, accepted on the fact:** a request that arrives during the hold and outwaits a stuck resolution can
  be the probe after the hold expires.
  - OB1-lite: begun at t=1010, it called at t=1032.
  - Codex: begun at t=1029, it called at t=1031.
  - The hold sentence in §3.5 and in `docs/ACCESS_CONTROL.md` §11 now says so.
- **Rejected: Codex's `began_held` flag.** The budget the hold exists for is at most one call per hold per resolver,
  whatever the traffic, and it holds without the flag: Codex's own run measured 11 calls in 60 s, one probe at
  35.5 s. The flag would add state to make an over-stated sentence true, so the sentence was corrected instead.
- **Accepted:**
  - OB1-lite's §3.1 retention sentence. Measured: `east` kept `token-one` across a lookup of `west`.
  - OB1-lite: `shared-qa` "has always been `self-only`" was false after D2b.
  - Codex's C6: `docs/diagrams/render.py` watched only the theme pages, so a failure on the 375 px page exited 0. It
    now watches every page, tested in `local-development/tests/test_diagram_render.py` (3 of 9 cases fail on the old
    renderer).
  - Codex's C7, on the facts, corrected in the fewest words.
- **Rejected:** Codex's five documentation contract tests (prose tests), and its placement of the renderer test.
- 221 blocks in 47 files: 41 edited and 6 created. The applied copy: **4934 passed, 20 skipped, 0 failed**.
  `docs/diagrams/render.py`: exit 0, 8 PNGs, scrollWidth 375.

### Merged (01:05 → 01:14) — commit `e4140d3`, merged as `8f7d24e`

- **OB1-lite confirmed `8460257`.** Its report was a message; this is the orchestrator's summary.
  - The renderer, its test and the counts hold.
  - A held arrival under 50 viewers' traffic kept one call per 30 s hold, which confirms the `began_held` rejection.
  - Its two wording corrections are `e4140d3`. The doc, spec and renderer tests on the applied copy: **1430 passed,
    12 skipped** (the `e4140d3` commit message).
- CI was 8/8 on `e4140d3` (`gh pr checks 339`). #339 merged at 01:14 as `8f7d24e`, after 14 review passes on six
  heads. #342's body calls them five review rounds.

### The implementation (01:21 → 08:36) — commit `fd9bfb9`, PR #342

- `local-development/apply-spec-blocks.py` on main `8f7d24e`: **221 blocks check out across 47 files**. No line was
  written outside the blocks except the re-rendered PNGs of Figures 2, 3 and 4. Figure 1's re-render differed by
  2 px of height, so its PNGs were kept (the PR body).
- Chart 0.53.0 and application 0.32.0. The upgrade note is under `docs/CHANGELOG.md`'s Unreleased heading.
- The non-browser suite on the branch: **4934 passed, 20 skipped, 0 failed** (the PR body).
- **OB1-lite on `fd9bfb9`** (a message; the orchestrator's summary): **mergeable as is, no findings.**
  - The PR tree equals main plus the 221 applied blocks, except the six PNGs.
  - The chart lints and renders with the walk's values files.
  - The full suite in a git copy: **5527 passed**.
- Main was merged in twice: `8e50ff8` at 01:47 brought #343, and `360b3c2` at 08:27 brought #344.
- CI on each head: 9 passed, and `container-smoke` skipped (the check runs). #342 merged at 08:36 as `46b71be`.

### #343 — the Helm handover (01:37 → 01:47) — commit `76eca74`, merged as `5b7d346`

- **Found by the lab walk, Step 3:** `local-development/release-crc.sh`'s Helm mode was refused once the chart
  version moved. The kept PVCs' labels were owned by `argocd-controller`, and Helm 4 applies server-side.
- **The fix:** `--force-conflicts` on the Helm-mode install. Its test fails on main's script (1 failed, 20 passed)
  and passes on the fix (21 passed) (the PR body and its commit message).
- **The operator:** *"pvc should not be removed"*. The PR's comment at 01:44 recorded both PVCs' UIDs as a baseline,
  and showed that the flag transfers field ownership and deletes nothing.
- **Grok 4.6:** C1, C3 and C4 CONFIRMED; C2 and C5 PLAUSIBLE (risk).
  - **Rejected, measured:** its gate, forcing only after an Application delete. The cluster's OpenAPI shows Pod
    `volumes` as keyed map lists, and the gate would refuse the rerun after a failed handover.
  - **Rejected, from source:** `Force=true` on the PVCs. Argo CD forces conflicts under server-side apply.
  - The walk measured both later, in Steps 9 and 10.
- CI 8/8. #343 merged at 01:47. Step 3's rerun after the merge left the PVCs identical (the PR comment at 01:49).

### The lab walk — SPEC_D2b §5 Steps 0–11 on #342's head `8e50ff8`

The record is `reports/2026-09-24_d2b-lab-walk/README.md`. The walk ran on CRC (OpenShift 4.22.7): two Helm rounds
with the Application's automated sync paused, then `release-crc.sh --argocd` and the recorded sync policy restored.

**Steps 3–5, the join paths:**

- **Step 3:** the handover defect, which became #343 (above).
- **Step 4:** the ownership flip logs `self-only`/`none` with `shadows-values-entry`, and restoring it clears the
  finding. The lookup rewrote the deleted Secret after 305 s, as `remote-sar`/`same-as-host`.
- **Step 5:** a Secret made on the tab at runtime resolved `remote-sar` within one discovery, with no restart, and
  developer is `all` there. A Secret stating only `identity: none` is `self-only`, and developer's groups there
  answer 403.

**Step 6, the personas.** **Found by the walk:** the spec's page check passed kubeadmin and jane.smith on `shared-qa`
on the previous cluster's text. `shared-qa`'s 10-minute token had expired at 01:57:12Z on 2026-09-23, on purpose.
The operator: *"This was an intentional set to expires because we didnt use the long term token just to dematrate"*.

**Step 7, rotation without a restart:** token 2/2, CA 2/2 and the dead URL 1/1 were each used at once.

- **Found by the walk:** the in-cluster row asked for `https://kubernetes.default.svc`, which the parser refuses by
  design.
- A substitute, `https://kubernetes.default.svc.cluster.local`, read `all` at cycle 20. It is **retracted**. The
  operator: *"`https://kubernetes.default.svc.cluster.local` - this is only connecting internally using the mounted
  ca into the pod for dashboard controller only."*
- **Open, for the operator:** the host guard refuses only the exact string, so other spellings of the in-cluster
  endpoint pass it. Closed in Part 7 as not a gap.

**Step 8, the hold:** two joins lacking `create subjectaccessreviews` and `list groups`, three readers for two
minutes. The result: **4 warnings per cluster, one per 30 s**, against a budget of 7 per cluster, and the metric's
`forbidden` count went 0 → 8. The alert was not measured.

**Step 9, retired and disabled clusters:** `mock-sar` and `mock-none` deleted, `shared-rnd` and `mock` disabled; none
of the four appears in `/api/whoami`.

- After the forced Helm apply, the Deployment still lists `mock-creds`
  (`reports/2026-09-24_d2b-lab-walk/walk/step9.out`). Grok's C2 on #343 had named the risk that forcing would strip
  it.
- The operator stopped the check that the mock is not asked before it ran: *"I just killed a process now. You wasted
  my token on that for over 230mins"*. The check could not have been trusted anyway, because a local `podman`
  container held its port.

**Step 10, the hand-back:** `release-crc.sh --argocd` gave Synced/Healthy, `running : 8e50ff8eec — verified in-pod`,
and met no conflict. `shared-rnd` and `shared-qa` both resolve `remote-sar`/`same-as-host`.

**The PVCs:** the same UIDs, volumes and creation times at the baseline and after Steps 3, 9 and 10 (the walk's PVC
files, compared with `diff` for this log).

**Step 11, the rejoin.** The operator: *"fix shared-qa with a long term token that does not expires and then rejoin
it. Show this as well"*.

- The new token has **no `exp`**.
- The tab's credential route rejoined `shared-qa` with no restart, and it has been polled every minute since.
- kubeadmin and jane.smith are `all`; developer and test-user-002 are `self`. The page check passed 4/4.

**The e2e walk after the rejoin:** **84/84** steps, **24/24** extra, **11/11** PDFs rendered, and **11/11** reports
passing integrity.

### #344 — the spec's lab steps (08:08 → 08:26) — commits `e61a38a`, `6769fa3`, merged as `5c22370`

- The changes to §5:
  - Step 6 opens a fresh page per reader and cluster.
  - Steps 6 and 10 expect `self` on the expired `shared-qa`.
  - Step 7's in-cluster row is removed.
  - Step 11 is added.
- The corrected Step 6 and Step 11, run on the lab (the PR comment at 08:13): **16/16** page checks with `shared-qa`
  expired, then **4/4** after the rejoin.
- **Grok 4.6:**
  - **C3, accepted on the fact:** Step 7's sentence could read as the parser enforcing the operator's rule. The
    orchestrator's wording states the guard's scope; Grok's paragraph was not used.
  - **C5, accepted:** §5's Definition of Done said kubeadmin is wide on both remotes before Step 11.
- Applied in `6769fa3`. Docs, specs index and apply-tool tests: **1077 passed, 12 skipped** (the `e61a38a` and `6769fa3`
  commit messages).

### The evidence and the README (08:30 → 08:50) — commits `d82b898`, `70e4273`, PR #345

- `reports/2026-09-24_d2b-lab-walk/` holds Steps 0–11 with each step's script and raw output, and the e2e walk with
  its HTML document and its eleven reports. The PDFs are not committed, for size.
- The README's screenshots were recaptured from `v0.32.0 · 8e50ff8eec`, as kubeadmin and as developer. The Home
  page and the self tier's users page were added.
- **Found by OB1-lite (Opus 5.5, high), all accepted** in `70e4273`:
  - Three README captions were wrong. The RBAC tab's unmanaged grant is the chart's own auditor binding, not a
    hand-made one. Access granted's split summed to 201 of 202. The Overview caption named 9 of the 12 alerts.
  - Four walk rows quoted log lines that were not saved in the walk folder.
- **Filed from the same review,** at 08:41–08:42:
  - #346: the Logins caveat shows under the audit-log source.
  - #347: the Access granted tiles leave out unmanaged grants.
  - #348, for the operator: the chart's own auditor binding is flagged as unmanaged.

  #312, open since 2026-09-23 01:46 UTC, already reports the same binding (found while writing this log).
- Docs citations: **1022 passed, 12 skipped** (the `d82b898` and `70e4273` commit messages). Diagrams, e2e selection and the environments README: **349 passed**
  (the PR body). #345 merged at 08:50 as `43befa4`.

### #338 closed (08:51, 08:52)

- The evidence comment is pinned to `43befa4e603b2ad57a9d9d9810aa2d422970d268`, and ticks every Definition of Done
  item with its step. #338 closed at 08:52.

### Published privately; nothing in the repository

- Two pages were published as private claude.ai artifacts (the orchestrator's summary; the titles are the pages'):
  - *D2b Lab Evidence*, a page of the walk's evidence.
  - *gRPC Through Envoy*, a diagram of how a gRPC call reaches a mongot pod through Envoy Gateway.
- No URL is committed.

### The cleanup (after 08:52)

The orchestrator's summary, with what was measured for this log:

- 42 scratch worktrees removed.
- 63 merged local branches deleted, and `integration/2026-09-23`. Measured now: 4 local branches.
- Remote branches deleted: 23 from this session's merged PRs, then 63 older merged ones, then 3 more once their
  worktrees under the home directory's gitRepos folder were removed. Measured now: 6 remote heads.
- 4 `gsd-*` worktrees removed. `gsd-grafana` is kept with 3 uncommitted changes; measured, they are three modified
  PNGs under `reports/2026-09-20_kyverno-170/`.
- A superseded leftover worktree discarded, after checking that every edit in it was on main.
- A 5-day-old local podman mock stopped.

### The operator's corrections to the orchestrator

- **OB3's token cost:** *"the ob3 is wasting my token - we have a skill here that monitor a back ground and wake up.
  no polling is needed"*.
- **The walk:** *"I just killed a process now. You wasted my token on that for over 230mins"*. What changed: one
  background waiter per step, and no polling.
- **The in-cluster URL:** the substitute row is retracted (Step 7, above).
- **`shared-qa`'s token:** a deviation toward a durable token was withdrawn (the orchestrator's summary). Step 7's
  restore put the expired token back, as the spec writes it. Step 11 then rejoined `shared-qa` with a long-lived
  token, on the operator's word.

---

## Part 7 — this log merged; #312, #346, #347 and the indexes (2026-09-24 11:55 → 20:00)

### This log, the review record and the handover (11:55) — commits `a4c2f75`, `83872bf`, merged as `2f1aa21`, PR #349

- Grok 4.6 reviewed `a4c2f75`: C1 and C3 **CONFIRMED**; C2 **accepted on the attribution, refuted on the numbers**.
  Every count now names its source, applied in `83872bf` (the PR's review comment).

### The host guard's other spellings — not a gap

- The walk had left one question open: the parser refuses only the exact string `https://kubernetes.default.svc`.
  The operator asked why that mattered. Re-read, the string has no power of its own. A cluster that a Secret
  declares always connects with its own token and CA, whatever URL it names. Another spelling of the in-cluster
  address only lists the host a second time, read with that Secret's token, as `shared-rnd` already does on purpose.
  **Closed with no change**. The walk record says so.

### #312 — the chart's own RBAC names the chart (18:16 → 18:26) — commit `47e9b73`, merged as `b04e85f`, PR #350

- The operator asked for the provenance metadata the design already defines. The chart set
  `rbac.ocp.io/config-source` on no template, so its own auditor binding was reported as a hand-made grant.
- The fix is a `gsd.rbacLabels` helper, used by all 19 RBAC documents in the chart's seven RBAC templates.
- **Research:** the dashboard counts any value as managed, and the namespace-configuration-operator never selects
  on the label, so nothing cleans the chart's value up.
- **Measured** (the PR body):
  - The new test failed 3 on main's chart and passed 4 on the PR.
  - Chart, version and citation tests: **1453 passed, 15 skipped**.
- Grok 4.6: C1–C5 **CONFIRMED**. Chart 0.53.1. CI 8/8 (`gh pr checks`).

### The specs and design indexes (18:31 → 18:51) — commits `cbd18b9`, `7739e07`, merged as `575befc`, PR #351

- The plan was reviewed by Grok 4.6 before any edit, and its named changes were all applied.
- The lifecycle is now defined per spec. Six specs moved to `merged` and two to `in progress`.
  `prepare-release.py` moves `merged` to `released` when a release is cut, and a test holds every status to the
  four words.
- The design index tags its two shipped mocks **Implemented**, and its duplicate rows are gone.
- Grok's confirmation pass: C1–C4 **CONFIRMED**, and C4's two points were **accepted** in `7739e07`.
- **Measured** (the PR body): the four new tests fail on main. **1115 passed, 12 skipped**. CI 8/8.

### #346 and #347 (18:41 → 19:13) — commits `ea2b7b2`, `ce3d8e2`, merged as `4f4c070`, PR #352

- **#346:** the Logins page takes its wording from one `LOGIN_SOURCE_TEXT` table, keyed on the API's `source`.
  Under the audit log it no longer says history "dies with its pod".
- **#347:** `/api/clusters` gains `unmanaged_bindings`. One `bindingsToReview` helper counts it on the Overview, the
  Access granted tiles and the KPI page.
- **Grok 4.6's review of `ea2b7b2`:**
  - C1 and C2 **REFUTED**, both **accepted**: three more pod-log assumptions, and a stalled note that overstated
    recovery past `retentionDays`.
  - C3 **accepted on the fact, one snippet rejected**: its KPI line would have added the fleet-wide unmanaged sum into
    the per-cluster bindings sum.
  - All applied in `ce3d8e2`.
- **Measured** (the PR's review comment):
  - Non-browser **4948 passed, 20 skipped**; browser **600 passed**.
  - Four new UI tests fail on `ea2b7b2`. CI 8/8.

### Deployed and proved on the lab (19:15 → 19:30)

- `4f4c070` was deployed with `release-crc.sh --argocd`. Synced/Healthy, `4f4c070b08` verified in-pod, and the PVCs
  identical to the baseline.
- **#312, measured:**
  - The auditor binding carries `config-source=group-sync-dashboard`.
  - `oc auth can-i` answers yes for an auditor-group member and no for its negative control.
  - The new pod logged 0 UNMANAGED warnings for it, and every cluster reports 0 unmanaged grants.
- **#312's last item, the ServiceAccount question:** the orchestrator first settled it as Group-only on best
  practice, reading the lab's unlabelled ServiceAccount-subject bindings as noise. **The operator
  refuted it:** the goal is to find hand-made grants on groups, ServiceAccounts or users, and *"The exclusion is not
  automatic … We are going to decide who to exclude"*, *"Using that label. We just need capabilities"*: the operator
  labels the RoleBinding or ClusterRoleBinding. **Retracted**; the capability for ServiceAccount and User subjects is
  #353, which carries the lab's ServiceAccount-subject measurement and its method.
- **#346, measured:** the audit-log wording is on the deployed page, and the pod-log sentence is gone.
- **#347, measured with a planted grant:** #312 had cleared the lab's only unmanaged grant, so a hand-made
  RoleBinding was planted in its own namespace, captured, and deleted.
  - With it: `dashboard` 207 = 38 ok + 7 to review (6 unresolved, 1 unmanaged) + 162 built-in; the Overview tile 7 on
    all three entries; the KPI page 21 = 18 unresolved · 0 dangling · 3 unmanaged.
  - After it: 205 and 0 unmanaged on every cluster (the 20:36:35 refresh).
- The evidence is in `reports/2026-09-24_rbac-provenance-and-review-counts/`.

### #312's follow-up — the chart's label turned the finding on (19:39 → 20:00) — commits `061c224`, `c7a9b26`, merged by the merge commit `b647db4`, PR #354

- **Found by the orchestrator**, re-reading the rule to answer the operator's question about it; #350's review had
  confirmed C1–C5 without it. The finding fires only where some binding carries a config-source, which is how the
  store tells whether a policy operator is in use. The chart's auditor binding is on every host by default, so #350
  switched the finding on for a host with no policy operator.
- **Measured:** the new test failed on main with the hand-made grant `unmanaged`. The lab cannot show it: 43 of its
  group bindings carry policy-operator values (read from the pod's database).
- The fix: the check ignores `CHART_CONFIG_SOURCE`, and the chart's own binding still counts as managed. The design
  was posted on #312 at 19:39, before any code.
- **Grok 4.6's review of `061c224`:** C1–C4 and C6 **CONFIRMED**. C5 **REFUTED, accepted and widened**: the
  classifier was cited as `Store.user_bindings` in six places across two documents, with three more wrong pointers.
  Its prose-pinning test was **rejected** as brittle.
- The operator's decisions, given while this was in review, are in the #312 line above and in #353 (opened 19:47).
- **Measured:** full suite on `061c224`, **5557 passed, 20 skipped**; docs citations on `c7a9b26`, **1037 passed,
  12 skipped**. CI: 9 passed, `container-smoke` skipped (`gh pr checks`).

---

## Part 8 — #340, the indexes, #353 and #293 (2026-09-24 21:47 → 2026-09-25 02:30)

### The CA cache (#340) and the indexes — PRs #358 (`4b07d45`, 21:47) and #359 (`ae431b0`, 21:57); merge shas and times from `git log`

- **#358:** the trusted CA bundle's cache now keys on each file's inode, mtime and size. A bundle kubelet swaps
  through `..data` is read on the next poll. The test reproduces the swap and failed on main.
  - Grok: C1–C5 **CONFIRMED**. Its note on two stale descriptions was **accepted**, its prose test **declined** (#358's
    body and commit `2694c75`).
  - Measured (the PR body): **5561 passed, 20 skipped**. #340 closed itself on the merge.
- **#359:** `reports/README.md` lists all 28 folders (it listed 7), held by `test_reports_index.py`.
  - S3's version corrected (0.45.0 was #249's). `data-requirements.md` dated.
  - Grok **REFUTED** three rows and two older cells as wider than their sources; all **accepted** (#359's review
    comment, commit `30b6a43`).

### #353 — OB1 on Fable (the record is OB1's log, `docs/session-changelogs/2026-09-24_ob1-312-close-out-and-353.md`)

- PRs #357 (`35fcddb`), #361 (`a79da71`), #360 (`c00aa2e`), #362 (`de303e9`), #364 (`7f46760`); merge shas from
  `git log`. #353 closed, with its Definition-of-Done comment pinned to `7f46760`.
- **The operator's rulings, in order:**
  - *"The exclusion is not automatic"*;
  - *"Remember we are supposed to silence all platform service account … those namespaces we excluded them in code
    and also add additional ones via values.yaml"*;
  - *"I wanna exclude by namespaces as designed"*;
  - the three OpenShift controller bindings as shipped defaults;
  - a User spelt `system:serviceaccount:…` kept silent.
- **The orchestrator's error, retracted:** its brief to OB1 said "no inference from `system:` names or namespaces".
  That over-corrected the operator's first ruling and dropped the long-standing platform rule. The operator caught it,
  and the consolidated mandate replaced it.
- **The orchestrator's owner reviews:** a `_FINDING_CASE` comment and a `system:kube-scheduler` sentence that stated
  the opposite of the rule, both fixed. It signed off on #361 and #360.
- **Measured** (the evidence folder `reports/2026-09-25_353-platform-rule/`): 125 findings on the defaults, 50 with the
  reference values. The PVC UIDs are identical.
- **Found by the orchestrator:** OB1's planted-grant check had an f-string `SyntaxError` and was waiting blind. OB1
  fixed it without re-planting.

### #293 — Codex implements, the orchestrator reviews (PRs #363 `09d5526`, 01:45; #365 `35d2c0c`, 02:28)

- **The workflow:** the operator asked Codex (gpt-6-astra, high) to implement #293 and the orchestrator to review it
  with Grok. Phase 1 wrote SPEC_S5 with 77 blocks (commit `3a0c2ff`'s message); Grok reviewed it before any code.
  Phase 2 applied them: 81 blocks, 31 files byte-identical to the spec (commit `63edb9a`'s message).
- **Found by the orchestrator in review:** a ConfigMap author can steer where the fleet account logs in. Put to the
  operator: an allow-list was declined, then "refuse insecure" was chosen, then **superseded**: *"I need this feature
  badly. So insecure is required in configmap."* The residual trust is recorded.
- **The operator:** *"Whatever you do … do not reduce the current level of permissions that service account has."*
  - **Measured** by rendering the chart's RBAC on main and on the branch: **REMOVED 0**, ADDED 3 (`configmaps
    get/list/watch`), recorded in #363's review comment and on #293.
  - #360 measured the same way: 0 and 0 (the memory note never-reduce-the-dashboard-sa-permissions).
- **Grok on the spec:** C1 and C4 **REFUTED, accepted** (the host's in-cluster aliases; an invalid stanza blocking a
  values cluster). C7 and C8 **accepted**.
- **Grok on the code:** C1–C8 **CONFIRMED**. N1–N3 **accepted**. N2's scheduler test failed 3 of 3 against a
  fresh-gate mutant, proven by the orchestrator (commit `69d1ae0`'s message; #363's review comment).
- **Measured** outside Codex's sandbox: **5175 passed, 16 skipped**; browser **606 passed**; helm lint clean (#363's
    review comment).
- **The lab walk** (`reports/2026-09-25_configmap-onboarding-293/`): one map with two stanzas → two generated Secrets,
  both polling, one fleet login each (B by IP with `insecureSkipVerify`). Then removal deleted B's Secret, a repeated
  name loaded nowhere, and a `bearerToken` stanza was refused. Deleting the map left no leftovers.
  - Grok **REFUTED** the README as wider than its files; **accepted**, and the IP measurement is committed.

### The incident

- OB1's end-of-task cleanup ran `git worktree remove --force` on every registered worktree.
- The operator's `~/gitRepos/gsd-grafana` (detached at `4f93ad1`) lost its three uncommitted PNGs under
  `reports/2026-09-20_kyverno-170/`.
- Nothing recovers them: no local snapshot (`tmutil listlocalsnapshots`), no Time Machine destination.
- The committed versions are intact. OB1 reported it at once, and the rule is in memory.

## Part 9 — the handover, the unmanaged-grant doc, the binding and discovery timers, the credential research (2026-09-25 02:36 → 10:00)

### The handover brought to #353, #293 and #340 — PR #366 (commit `481c312` 02:36; merge `4e24b7a` 02:45)

- `docs/HANDOVER_2026-09-20.md` and Part 8 of this log were written at the end of the night.
- **Found by Grok:** two stale handover lines, and Part 8 numbers without a source. **Accepted** in `481c312`, whose
  subject names them.

### How to silence a legitimate unmanaged grant — PR #367 (commits `b850c4c` 07:59, `306d4ad` 08:03; merge `dd4892b` 08:12)

- **Asked by the operator:** *"What labels do we add to grants to exclude them from being reported?"* The answer is
  written beside `Chart.yaml`: `charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md` covers the
  `rbac.ocp.io/config-source` label, the `rbac.ocp.io/unmanaged-exception` annotation, and what the platform rule
  already silences. Chart 0.55.1.
- **Found by Grok:** the doc implied the dashboard could set the label. **Accepted**, in `306d4ad`: the label is set by
  a person or CI, never by the dashboard.

### Bindings refresh hourly; discovery keeps its own timer — PR #368 (commits `437b3e6` 08:33, `ff2c441` 08:44; merge `7aa00f1` 08:53)

- **The operator:** a binding refresh every 300s on every cluster was *"too much checking and checking on every
  clusters"*, and chose 3600s.
- **Liveness stays separate.** The operator's ruling: *"liveness probes should Not be using the same parameter as
  bindingIntervalSeconds"*. The probe keeps `probes.liveness.periodSeconds: 300`.
- **The operator:** cluster discovery *"should run on a different timer and parameters so … we don't lose a
  cluster"*.
  - **Measured** (`gsd/poller.py`, `_run_discovery` and the lookup's failure path): two things slept on
    `binding_interval_seconds`. One was the thread that lists cluster Secrets. The other was the wait before the
    dashboard retries logging in as the fleet account to fetch a remote cluster's ServiceAccount token (#284).
  - Both now sleep on a new setting, `config.discoveryIntervalSeconds`, default 300 seconds. That is the cadence they
    already had, so slowing bindings to an hour does not delay a new cluster. Chart 0.56.0, app 0.34.1.
- **Measured before review** (both from #368's PR body):
  - `helm template` on the branch, diffed against main's render. Only `bindingIntervalSeconds`, the new
    `discoveryIntervalSeconds`, the Deployment's `checksum/config` annotation (which changes whenever the ConfigMap
    changes) and the two image tags differ. No Role, ClusterRole or binding changes.
  - **Full suite: 5791 passed, 20 skipped** (7m32s).
- **Grok on `437b3e6`:** C1–C5 **CONFIRMED**.
  - C6 **accepted**: `Event.wait(0)` returns at once, so `discoveryIntervalSeconds: 0` was a busy loop of LISTs against
    the host API, with a zero lookup backoff. The key is now refused below 1 at render and at startup.
  - C7 and V1 **accepted**: five texts still tied discovery to bindings, including the CHANGELOG heading.
  - Its phrase-blacklist doc test was **rejected**: it pins wording, not behaviour.
- **CI** on `ff2c441`: 9 passed, `container-smoke` skipped (`gh pr checks 368`). Merged with `merge-safe.sh`, which
  records a merge commit rather than a squash and deletes the branch only after checking main.

### The fleet-credential research — issues, no code (09:10 → 10:00)

- **Asked:** can Red Hat's Shared Resource CSI driver (the SharedSecret kind) replace the two Jobs in the
  group-sync-operator Helm chart? Those Jobs copy the LDAP bind credential and CA from `openshift-config` into the
  operator's own namespace, on each cluster where the chart is installed. Kyverno, which could do the copy, is not
  approved.
  - **Measured** (group-sync-operator's `pkg/syncer/ldap.go`, the `Get` of `CredentialsSecret`): the operator reads
    its credential and CA only as Kubernetes API objects.
  - SharedSecret only mounts files into a pod; it creates no Secret the operator could read. The OAuth bind Secret
    also holds only `bindPassword`, measured on the lab.
  - So SharedSecret cannot replace the Jobs. **Ruled out by the operator**, in operator-chart issue 69.
- **Parked, as the operator decided:**
  - #369: a cluster's credential is either an existing Secret, or one the External Secrets Operator creates from the
    organization's secret manager. That operator is GA on OpenShift 4.20+ ([Red Hat's OpenShift 4.20
    documentation](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html/security_and_compliance/external-secrets-operator-for-red-hat-openshift);
    the lab catalog offers `openshift-external-secrets-operator.v1.2.1`, read with `oc get packagemanifests`). One
    credential serves every cluster, unless a cluster's stanza names its own.
  - Operator-chart issue 70: retire the copy Jobs in four phases.
  - The routes tried and dropped (SharedSecret, native replication, the OAuth builder) stay on #369 as collapsed,
    outdated comments.

## Part 10 — the redeploy, #322 and #321, and the switch to new implementers (2026-09-25 21:37 → 2026-09-26 00:10)

### The session log and the redeploy — PR #370 (merge `9584239`, 21:37)

- #370 carried Part 9 and brought the handover to `7aa00f1`.
- **Found by Grok:**
  - two numbers without a source (the 5791 suite count and the PVC re-read);
  - #366 missing from Part 9;
  - the handover stale.
  All **accepted**, in `030739b`.
- **Deployed** `9584239` with `release-crc.sh --argocd`: verified in-pod, PVCs identical (#368's PR comment).
- **The timers, measured on the lab** (the evidence is #368's PR comment):
  - bindings refreshed once, at 22:39:53 CDT;
  - discovery cycles ran at 22:39:33, 22:44:33, 22:49:33 and 22:54:33. The cycles were timed by creating and deleting
    a probe Secret, a clone of the lab's refused test Secret, since removed.
- **Closed:** #308 (the `image` job passed on 8 of 8 main runs) and operator-chart issue 69 (the SharedSecret
  research). **Filed:** #371, the suite writes into the working tree.

### The implementers change (the operator, 2026-09-25 evening)

- *"New mandate. Switch to coding with ob1-lite and codex astra."*
- OB2 (Fable) was stopped mid-#322, after writing SPEC_T2 (`7f97731`) and before any code. Its worktree, branch and
  pending Grok spec review were handed over intact.
- The rule since then: a change is never reviewed by the seat that wrote it. OB1-lite's code gets Grok and Codex;
  Codex's code gets Grok and OB1-lite.

### #322, the cluster-admin tier — PR #372 (merge `49c4834`, 23:07), evidence PR #374 (merge `2f01a3c`, 23:30)

- **The build:** OB1-lite (Opus 5.5) continued from OB2's spec, rebased, and applied 91 blocks (`18e7c66`).
- **Grok's spec review:** C7 and C9 **accepted** (#372's first PR comment; SPEC_T2's Orchestrator's notes D7, D8).
  - C7: a values file that still sets a removed block to `null` keeps that null, because the chart no longer
    defaults the key. The first blocks refused any present key, so the render failed. Now a block is refused only
    when it sets a field.
  - C9: in one install (the proxy on; visibility, token access and cluster-Secret writes all off) no
    `system:auth-delegator` binding was rendered, so KPI would refuse everyone. The binding now renders whenever the
    proxy is on.
- **Measured by OB1-lite:**
  - hermetic 5232 passed (#372's Codex-review comment);
  - browser 605 passed, and no Role or ClusterRole rule removed across five `helm template` combinations. The only
    addition is that binding. These two are from OB1-lite's report to the orchestrator and are not in the
    repository.
- **Grok's code review:** no findings. Its shell was blocked, so the verdicts come from reading.
- **Codex's code review** (gpt-6-astra): approved, with one P3 copy fix **accepted** (`4cc54b7`). The Cluster
  Configurations note still named the removed tiers. The new test fails on the old text and passes on the new.
- **The lab walk on `18e7c6690a`** (`reports/2026-09-25_cluster-admin-tier-322/`):
  - kubeadmin: 200/200 and both tabs;
  - `developer` with a temporary `cluster-reader` binding, removed after: 403/403, neither tab, and the refusal cards.
- **Found by Grok on #374:** C1, C2 and C7 **accepted**. C6, "no screenshots", was **rejected**: `git ls-files` lists
  all six, and Grok's seat does not see binary files.

### #321, remove the OAuth Debug path — PR #373 (merge `667b3c4`, 23:46), evidence PR #375 (merge `e5459e0`, 00:10)

- **The four open decisions** were settled on "easy to manage, best practice" and recorded on #321. The lab measured
  `logLevel=Normal` and audit-log only.
- **Phase 1, the spec:** Codex (gpt-6-astra) wrote SPEC_L1, 135 blocks across 57 files (#373's PR body).
- **Spec review** (#373's spec-review comment; SPEC_L1, Review round 1):
  - OB1-lite measured 9 tests failing after apply and supplied fixes A–E, with 1103 passing after. **Accepted**.
  - Grok's C5 fallback was **rejected**. OB1-lite measured that no chart path gives a pod a pod-log ConfigMap.
- **Phase 2, the code:** Codex applied the amended spec; review round 1 added Blocks 136–142 (SPEC_L1). Its sandbox
  blocks sockets, so the orchestrator ran the suites outside it: browser 604, mock 59 in a CI-style venv, the Helm
  refusals, and RBAC REMOVED 0 (default 63/63, crc 70/70). These are in #373's round-2 comment.
- **The rebase onto #322:**
  - three conflicts (the specs index, its pinned count, the CHANGELOG);
  - the specs-index tests failed until L1's row sat above T2's (issue #321 before #322), T2's status was `merged`,
    and L1's was `in progress`. That was during the rebase; L1 became `merged` in this log's PR;
  - the version blocks applied: chart 0.58.0, app 0.36.0, SPEC_S4c to 0.59.0 / 0.37.0.
- **Code review:** OB1-lite approved, measuring hermetic 5177, #322's suites 299, browser 604, the code 64 lines added
  and 1223 deleted (#373's round-2 comment; SPEC_L1, Review round 2).
  - F1 **accepted**: the lost test of the log-read budget, restored; it fails on a mutant.
  - N1–N3 **accepted**.
  - Grok's F1 **rejected** by its own condition: `authLogLevel: null` exits 1, as the spec intends.
- **The lab** (`reports/2026-09-25_remove-oauth-debug-321/`):
  - no Debug-path object left, and OAuth at `Normal`;
  - a real `oc login -u developer` at 04:25:57Z was stored 23 s later as `success`, source `audit-log`, kind `cli`.
  - Stored pod-log history cannot be shown on this lab, whose database has only audit-log rows. A test pins it.
- **Found by Grok on #375:** C1 and C6 **accepted**, with the exact commands committed.
- **Found by `merge-safe.sh`:** it would not delete #373's branch after the merge. It treats a file the PR removed as
  "missing on main" and stops, so that a merge that dropped a file by accident is not cleaned up as a success. These
  files were meant to go; after checking that by hand, the branch was deleted.

## Part 11 — the failed Action, the review seats, the skill's lessons (2026-09-26 00:30 → 02:36)

### The failed Action — PR #378 (merge `7bd8e87`, 01:56)

- **Found by CI:** run 36221028974, on #376's merge `d1d046d`, failed the `tests (3.11)` job only; the
  `tests (3.14)` job on the same commit passed. The failing test was
  `test_unmanaged_subjects.py::TestAuditLogProgress::test_the_poll_loop_announces_a_new_grant_on_the_refresh_that_finds_it`.
- **Diagnosed from the failing run's own log:**
  - the test configures only cluster `c`, yet its captured log shows refreshes of a cluster `host`;
  - a leaked `poll-host` thread called this test's monkeypatched `ClusterClient` and used up one of its scripted
    cycles.
  - The test passed 40 of 40 times locally (the orchestrator's runs, not published), so re-running could not
    find the cause.
- **The leaking test was found by a per-test thread probe:** a local pytest plugin, never committed, run by the
  orchestrator over the full suite. It reported 5181 passing tests (its own count, not CI run 36221028974's 5182
  passed and 1 failed) and exactly one test that left a thread alive,
  `test_fleet_lookup.py::TestTheSchedule::test_a_retrieved_stanza_whose_secret_vanished_stops_polling_rather_than_polling_the_stanza`,
  which leaves `poll-host`. It called `_reconcile_threads()` without seeding `host`.
- **Built by OB1-lite, reviewed by Grok and Codex Astra** (#378's comments):
  - the source fix: seed `host`;
  - the mechanism: `local-development/tests/conftest.py`, a guard that fails any test leaving a poller thread alive.
- **Review decisions:**
  - Grok's C7 **accepted.** The guard used to ignore poller threads already running when a test started, so a leak
    from one test was excused in every later one. Measured on a two-test probe, the second test passed while
    `poll-host` was still running. The guard now fails any test that ends with a poller thread alive.
  - Codex's hardening **rejected.** It wanted extra machinery in the product: a special thread class, extra scans,
    and a suite-wide safety net. Neither reviewer found a test in this suite that needed it.
  - Grok's N1 **accepted as a note** in SPEC_S4b. The spec still quotes the old test, which did not seed `host`;
    that quoted example stays as the historical record, and only the real test in the tree was changed.
- **Measured** (#378's comments): hermetic 5180 passed, browser 604. With the leak, both the leaking test and the
  one after it now error, naming the thread.
- **Main's CI on `7bd8e87`:** every job passed, including `tests (3.11)`.

### Grok gets its shell back; the skill's lessons — PR #377 (merge `fb99e15`, 01:18)

- **The operator:** *"cursor grok was better before and it could access shell and write it own file."*
  - The CLI's own help calls `--mode ask` read-only, and every Grok pass from #368 to #376 used it.
  - Grok now launches with `-p --force --workspace "$G"`, in a scratch folder of its own. That folder holds a copy
    of the commit under review (under `head/`) and a `findings.md` that Grok writes itself. It was probed twice
    before it was recorded (#377's commit body).
- **The skill** (`.claude/skills/adversarial-review/SKILL.md`) gains:
  - the implementers, Codex Astra and OB1-lite, and the rule that no seat reviews its own change;
  - eight measured gotchas from #321 and #322 (listed in #377's commit body).
- **Found by Grok** (its first review with a shell; it ran the new launch line itself): C3. The launch recipe still
  made OB3 the default third seat. **Accepted.** A confirmation pass: C1–C3 CONFIRMED.

### The seats (the operator, 2026-09-26)

- *"Grant all the agent switch role capabilities."* `ob1-lite` and `ob3` gained OB2's REVIEWER/IMPLEMENTER switch,
  with REVIEWER as the read-only default. Backups: `~/.claude/{ob1-lite,ob3}.md.bak-2026-09-26`.
- **Found while validating** (PyYAML, run by the orchestrator, not published): both new descriptions broke strict
  YAML, because of a `: ` in plain text, and OB1-lite's original description already did. Fixed; all three now
  parse.
- **Found by probing:** an agent edit takes effect in the next session. Both probes answered from the old
  definitions.
- **The allocation approved by the operator:**
  - OB1-lite is the default builder;
  - Codex Astra takes large mechanical work;
  - OB3 takes only the riskiest design work;
  - OB2 settles disagreements and is the backup builder.
- **The operator's `claude-config` repository, PR #1** (merged by the operator at 02:36, its `mergedAt` time): the three agents at the top
  level, and `restore.sh` now restores them. It never did before.
- **Memory:** a single reference for every seat's exact launch line (the note *seat-invocations*), and the Grok
  invocation (the note *grok-runs-with-shell-in-its-own-dir*).

---

## Part 12 — the epics, and Epic A: quick cleanup (2026-09-26 09:54 → 13:00)

### The checkpoint and the mockups — PR #380 (merge `8990eab`, 10:43)

- **The operator:** *"create an epic for each group first and refine the issues now to align with our current
  state … Add screenshot or mockup html or render visually in each epic and then execute"*, and *"do a tag of this
  main branch before you start."*
- The tag `checkpoint-2026-09-26` points at `9da9234` (#379), made at 09:54 (`git for-each-ref`).
- #380 commits two mockups for the epics, each with its PNG, and a row in `docs/design/README.md`:
  - `docs/design/cluster-reconnect-mock.html`, for Epic D: Refresh, Rejoin and the duplicate-URL warning;
  - `docs/design/kpi-backups-mock.html`, for Epic E.
- **Found by Grok** (with a shell, in three passes): each mockup broke the rule that anything unmarked is exactly
  today's app and anything proposed carries its own PROPOSED tag.
  - Today's header, tab bar and cards were shown shortened, and the mockup did not say so.
  - A proposed box was marked only by its dashed outline.
  - **Accepted**, fixed in `d3471ce` and `be3b359`. The third pass confirmed both.

### Eight epics, six new issues, seven closed as already shipped (10:43 → 10:48)

- **Posted:** epics #381–#388 (labels `epic` and `epic/<letter>`) and new issues #389–#394, all created between
  15:43:31Z and 15:43:46Z (`createdAt`).
- **The children:** 51, linked as sub-issues (`subIssuesSummary` per epic: 7, 3, 6, 6, 6, 8, 3 and 12).
  - 44 existing issues, refined with their original text kept, collapsed;
  - the 6 new issues;
  - the operator chart's #70, under #388.
- **Closed as already shipped,** each with its evidence: #245, #131, #165, #170, #230, #171 and #119, between
  15:47:48Z and 15:48:01Z (`closedAt`).
- **The operator, about #291:** *"Do not deprecated my features here."* This is a rule in both new skills.

### `/epic` and `/issue` — PR #395 (merge `bebebc1`, 11:40)

- The format of the epics and their issues, the posting and linking steps, and the lessons from building them, as
  `.claude/skills/epic/SKILL.md` and `.claude/skills/issue/SKILL.md`.
- **Found by Grok**, five points, each re-measured and **accepted** (`573f0cd`):
  - the skill said 44 children; there are 51;
  - it said two issues were already shipped; there were seven;
  - it cited #291's rule as said on #291, which has no comments;
  - the `ls` lesson described a two-path `ls`, not the brace-expanded one that had failed;
  - the skills said two reviewers, where the adversarial-review skill launches three. They now say "at least two
    seats other than the implementer, Grok one" and point to that skill.
- **Found about Grok itself:** its answer said the review was in `findings.md`, but that file was never written. A
  waiter that waited for the file would never have ended. Recorded in the memory note
  *grok-runs-with-shell-in-its-own-dir*. Later waiters end when Grok's process exits.

### Epic A (#381) — #319, the docs index — PR #396 (merge `ad30bbe`, 11:26)

- **Written by Codex Astra:** `docs/README.md`, with operator guides first and development records by kind, and a
  test that fails if an operator page has no link. Chart 0.58.1 for the chart README's links.
- **Found by OB1-lite, accepted** (#396's comments):
  - the index promised that `docs/polling-and-discovery.md` covers forcing a refresh, which cannot be done today
    (#311);
  - `docs/LOGIN_CAPTURE_QUICKCHECK.md` is an operator guide since #321;
  - `docs/AUDIT_LOG_CAPTURE.md` still described the removed Debug source;
  - nothing checked that the index's links resolve.
- Grok confirmed all six claims of its brief (C1–C6). Measured after the fixes (#396's decisions comment): OB1-lite's
  `check_fixes.sh` gives 3 PASS; 96 of 96 links resolve; docs, citations and chart-version tests
  `1100 passed, 15 skipped`.
- **The CRC walk was waived**, with a measured reason: the render differs only in the version label and
  `checksum/config`.

### #371, no `gsd.db` in the working tree — PR #397 (merge `ed4a865`, 12:42)

- **Built by OB1-lite:** the one test that wrote `local-development/gsd.db` now uses `tmp_path`. A conftest guard
  fails a test during which the default database changes. It compares before and after, so an unchanged developer
  database passes.
- **Found by Codex** (its claim C3, point P3), **accepted:** the guard could compare the wrong directory, and it
  blamed the test for a change an earlier connection's WAL checkpoint can make. Both snapshots now read the directory
  the test started in, and the failure no longer claims that the test wrote the file.
- **Accepted in part:** Codex's regression file. Three of its five tests were kept; the stat-count test and the
  message-wording test were dropped.
- **Measured:** the three tests went from 2 failed and 1 passed to 3 passed. Full hermetic suite:
  `5183 passed, 19 skipped, 608 deselected`, with no `gsd.db*` left behind.
- Grok confirmed C1–C6.
- **Corrected after posting:** the closing comment on #371 first said every documented command sets
  `PYTHONDONTWRITEBYTECODE`. That was never measured, and it is not true. It now says what the issue decided: no
  change, since `.gitignore:1` already ignores `__pycache__/` (`git check-ignore -v`).

### #389, GitOps examples for adding clusters — PR #398 (merge `801b954`, 12:51)

- **Found while writing the brief, before any code:**
  - A Secret that declares `saTokenLookup` is rewritten in place with the token (`fleetlookup.store` →
    `writer.store_lookup`). Argo CD with self-heal would revert it, and the next lookup would log in again.
  - The issue as posted would have taught exactly that. It was refined before the build. The GitOps example is
    #293's onboarding ConfigMap, and the Secret example is for a one-off `oc apply`.
- **Built by Codex Astra:**
  - `examples/cluster-onboarding/`: the ConfigMap, a `kustomization.yaml` that lists only it, an Argo CD
    Application and a Flux Kustomization;
  - `examples/cluster-secret/secret.yaml`;
  - `local-development/tests/test_cluster_examples.py`: five tests, each failing before its file existed;
  - a §8 subsection and chart 0.58.2.
- **Added by the orchestrator, before the first commit:** a note in the ConfigMap's header that the dashboard writes
  the generated Secret only when `clusterConfig.secrets.writes.enabled` is on, and it is off by default.
- **The premise, measured by both reviewers:** OB1-lite called `lookup()` twice on a cluster read from a Secret, with
  one shared credential gate. Both calls returned `updated`, with 2 logins. The control, a cluster read from the
  onboarding ConfigMap, was held by the gate.
- **Found by OB1-lite (F1), accepted:** the drift test compared only the stanza's keys, and five edits to
  `docs/CLUSTER_STANZA.md` passed it. It now compares the whole manifest. Re-measured: doc-side drift fails.
- **Not applied:** Grok's optional note about the `argocd.argoproj.io/managed-by` label, which matters only for a
  namespaced Argo CD instance. On the lab, the default instance's operator-owned ClusterRole already grants
  `configmaps` `*` cluster-wide, so the example needs nothing more.
- **Found by CI** on `2a9903c` (run 36257489278): a new `reports/` folder needs its row in `reports/README.md`
  (`test_every_report_folder_has_one_index_row`). The orchestrator had run only the docs tests after adding the
  evidence (its own account). Fixed in `69619cf`; CI on that head: `5192 passed, 16 skipped, 608 deselected`
  (run 36258361975).
- **On CRC** (`reports/2026-09-26_gitops-examples-389/README.md`), with the committed example under a throwaway name:
  - the generated Secret appeared 286 s after the apply;
  - one fleet login, the session revoked;
  - the Secret was pruned 287 s after the delete;
  - the PVC UIDs were unchanged.

### Found by CI: the ASCII diagram preview — PR #399 (merge `4368409`, 13:00)

- **Found by CI:** #397's `diagrams` check failed in a step whose own comment says it never fails the job.
- **The mechanism, measured:** under the runner's `bash -e` and the step's `pipefail`, `url=$(curl … | grep …)`
  exits 1 when the API reply has no download URL. The step's script, taken from the workflow and run against a
  rate-limited `curl` stub: main exits 1 with no output; the fix exits 0 and says it skipped.
- **Corrected by OB1-lite:** a network failure (curl exit 6) produces the same silent exit, and the log keeps no
  reply. So "rate limit" is plausible, not measured. The failing log is attempt 1 of run 36257920883.
- Grok and OB1-lite each ran the step with failing stubs for the download, `tar`, a missing binary, a failing binary
  and an empty `mmd/`. Every case exits 0.

### Epic A's branches deleted

- **The operator:** *"Each deletion should happen after each epic is done."* 11 older branches, each re-measured
  first:
  - 8 were ancestors of main;
  - the local branch `feat/285-credential-lifecycle` (git: "Deleted branch feat/285-credential-lifecycle (was
    078ebfd)") is reachable from `refs/pull/325/head`, and #325 merged as `048e928`, which has an identical
    SPEC_S4c;
  - `skill/review-models-fable` and the remote `feat/mock-manifest-and-apple-silicon-notes` stay reachable as
    `refs/pull/137/head` and `refs/pull/196/head`.
- Kept, because each is its own call: `grafana-integration` (its document is cited from main),
  `integration/design-programme` (the only ref to `5ad0551`), `master-backup` (the operator's) and `gh-pages`.
- Separately from those 11, the four branches this epic created were deleted, each shown to be inside its merged
  PR's head: `docs/319-docs-index`, `fix/371-no-db-in-tree`, `skill/epic-and-issue` and
  `ci/ascii-preview-never-fails`. Worktrees were removed from the orchestrator's own list only, each clean first.

### Found on the lab, reported, not changed

- Read on the lab by the orchestrator (not published): the `group-sync-dashboard` Argo CD Application reads Healthy,
  but sync `Unknown` with a `ComparisonError`. Its server-side-apply diff cannot resolve `route.openshift.io/v1`
  Route.
- The `grafana` Application, which also manages a Route, is Synced.
- The last sync succeeded at `2026-09-26T04:48:04Z` (`status.operationState.finishedAt`). A hard refresh did not
  clear it.
- Restarting the Argo CD controller is the operator's call.

---

## Part 13 — Epic A released and deployed; Epic B built (2026-09-26 13:19 → 18:08)

### Every epic is released and deployed — PR #401 (merge `afcf457`, 13:54)

- **The operator:** *"In agile. You have deploy or redeploy every epic and cut a release note. So we are remaining
  true."* I had proposed skipping Epic A's deploy because nothing in it reached the image. The rule is now the last
  step of `.claude/skills/epic/SKILL.md` and a memory note (*every-epic-ends-with-release-and-deploy*).
- **Found by Grok, accepted:** the first head's close-out step deployed the release with bare `--argocd`, which
  builds HEAD and pins that image. The published release deploys with `--argocd main` (the mode table in
  `local-development/release-crc.sh`). Also, the GitHub release's tag is the chart version.
- **Found by OB1-lite, accepted:** a merge that only bumps the chart runs no image build; the chart-publish workflow
  (`helm.yaml`) retags the existing `:<appVersion>` image as `:<chart-version>`. **Corrected in Part 13's review:** the
  skill's claim that `publish.yml` "builds an image only on an `--app` release" was wrong. Any merge that changes the
  image's inputs pushes the immutable `<appVersion>-<sha>` tag; only the `:<appVersion>` alias waits for an `--app`
  release (`publish.yml`, and its run on `16c339e`). `.claude/skills/epic/SKILL.md` is corrected in this PR.

### Epic A's release — PR #402 (merge `2b2c744`, 14:04)

- Cut with `prepare-release.py --chart 0.58.3 "Epic A: quick cleanup (#381)"`. `docs/CHANGELOG.md` has its first
  release heading since application 0.24.0. The script also moved the ten specs marked `merged` to `released`.
- **Found by Grok and by OB1-lite, accepted:** my first bullet said every entry under the heading names the versions
  that shipped it. Measured: 62 bullets sit under the new heading, and 25 of them contain no `X.Y.Z` version at
  all. The bullet now says so.
- `helm.yaml` published the chart release at 19:12:57Z (`gh release view`). The release note on GitHub carries the
  epic's summary.

### The lab's Argo CD controller (the operator's go-ahead, 13:19)

- Found in Part 12: the `group-sync-dashboard` Application was Healthy but sync `Unknown`, with a `ComparisonError`
  on the Route type.
- Deleting `openshift-gitops-application-controller-0` (Ready again at 18:19:52Z) and a hard refresh made it
  **Synced/Healthy** at the same revision. The dashboard pod was not rolled, and the PVC UIDs were unchanged
  (recorded on #381).

### Epic A deployed and walked — PR #405 (merge `cbbc65a`, 15:07)

- `release-crc.sh --argocd main` reported Synced/Healthy at 19:14:46Z, with chart 0.58.3 and image 0.36.0; the PVC
  UIDs were unchanged (`reports/2026-09-26_epic-a-release/README.md`).
- **The operator asked:** *"Where is the screenshot of the newly added features."* The first evidence had been logs
  only. The walk captured the Cluster Configurations tab before, with, and after a cluster added through the
  committed GitOps example: the Secret was generated 257 s after the apply and pruned 272 s after the delete.
- **Found by the walk:** #404, filed under Epic D. While the GitOps cluster was live, the header read `ConfigMap 0`,
  because it counts a generated cluster under `Secret`.
- **Found by OB1-lite:** the index row named Argo's revision instead of the application build (fixed); and the
  discovery line counts retired rows (added to #404).
- **Found by Grok, accepted in part:** the publish time and the discovery interval had no source in the README; they
  now cite theirs. Rejected: removing the figures read off the screenshots, which both reviewers confirmed against
  the images.
- #381 is closed. Its screenshots are embedded on #381 and #389, pinned to `cbbc65a`.

### Epic B: #305, refuse a database newer than the build — PR #403 (merge `16c339e`, 14:57)

- **Built by OB1-lite:** `Store.__init__` reads `user_version` right after connecting, before the WAL pragma, `SCHEMA`
  and the seeds, and raises `StoreSchemaTooNew` with both numbers. A real `uvicorn --factory` start exits 1.
- **Measured by Codex and by Grok; Codex refuted my wording:** SQLite folds a committed but uncheckpointed WAL into
  `gsd.db` when the refusing connection closes, so the file's bytes change; the schema version and the rows do not.
  **Accepted Codex's advice:** I corrected my promise of
  "byte-identical", not the code. A new test keeps a killed writer's WAL data through the refusal; with the guard
  disabled, it fails with `DID NOT RAISE`.
- **Found by the full suite** after main was merged in: `test_kyverno.py::test_f3…` read the chart version with a
  lowercase `chart X.Y.Z`, which the first chart-led heading (`## Chart 0.58.3 …`) broke. It now reads both forms.
- **My slip:** one review brief was written with an unquoted heredoc, so the shell ran a backticked word as a
  command. Both reviewers were stopped and relaunched with the corrected brief.
- #305 was reopened after the merge: its Definition of Done still owes the lab check at Epic B's release.

### #298, a migration needs an application release — PR #406 (merge `411b6cc`, 15:36)

- **Built by OB1-lite:** `prepare-release.py` gains `schema_since_app_release`, and a test fails when the highest
  migration moved since the commit that released the current version. The tests job checks out with
  `fetch-depth: 0`.
- **Found by OB1-lite in my own brief:** `git log -S 'version = "'` looks for a change in how many times that string
  occurs, so it sees only the commit that first added the line, not a version bump. The helper walks
  `git rev-list --first-parent` and compares each commit's `version =` with its parent's. That walk agrees with
  `git log --first-parent -G '^version = "'` on all 31 application-version changes.
- **Rejected, with the fact:** Codex's F1, which asked to refuse any historical file with a second `_MIGRATIONS`
  assignment. Such a file cannot reach a release, because this PR's own parity test runs on every PR.
- Main's CI passed on `411b6cc`, the first run of the check on main.

### #301, a copy before an upgrade migrates — spec review, then PR #407 (merge `50ec1b5`, 18:08)

- **Researched and specified by OB3** (`docs/specs/SPEC_M1_pre_upgrade_copy.md`), reviewed before any code.
  - OB3 measured that a failed migration still commits `SCHEMA`'s new tables. So a crash loop that re-copies would
    copy a half-migrated database.
- **Found by Grok and by Codex on the spec, independently** (their claim C3, the P1): replacement pods each took a copy, and `keep=3` pruned the only
  clean one. **Accepted Grok's fix:** copy once per *upgrade*, not per pod. Rejected Codex's (drop the pruning),
  because each replacement pod would still add a copy, without bound.
- **Accepted:** Codex's C4 (a `stat()` outside the failure handler), and both reviewers' C6 (no application bump in a
  feature PR: chart 0.58.4 only).
- **Code review:** Grok found no defect. Codex F1a was **accepted**: the skip matched `-to-<N>-` anywhere in the name,
  so a pod name containing that string could skip the copy. It now reads only the target field of the copy's own
  file name; the test fails without the fix. F1b was **rejected**: it asked to re-verify an existing copy's contents, but this code
  never publishes an unverified copy.
- Hermetic suite on the final head: `5248 passed, 19 skipped`.

### Backups: what success looks like, and restore scoped

- **The operator:** *"Pls put this screenshot in one the doc showing what successful backup looks like."* Captured
  from the lab at 23:02:25Z (the capture time is on #382's R7; the image and its figures are committed with the
  runbook section at Epic B's release, not yet):
  - the log line `backup written … (4 kept)`;
  - four copies in `/data/backup`;
  - the runbook's §1 check, showing `integrity_check: ok` and `user_version: 20`;
  - `gsd_backup_failures_total 0.0`.
  It goes into `docs/RUNBOOK_backup_restore.md` at Epic B's release.
- **The operator:** *"We also have to try backup and restore … scope it by testing certain things."* Measured first:
  no committed walk has ever restored a database. Epic B's Definition of Done now carries checks R1–R7 (#382), run
  on copies in a throwaway pod. The live rollback stays with #302 (Epic E).
- **The operator chose** to prove #301 on a copy of the lab database, not by a live upgrade and restore. #301's
  Definition of Done is amended on the issue to say so; the live rollback stays with #302.

## Part 14 — Epic B released and walked; Fable's composition review; Epic C begun (2026-09-26 18:44 → 21:55)

### Epic B's release — PR #409 (merge `b087c78`, 19:01)

- Cut with `prepare-release.py --app 0.37.0` from `50ec1b5`: application 0.36.0 → 0.37.0, chart 0.58.4 → 0.58.5.
- **Found by `tests/test_specs_index.py`:** SPEC_S4c had reserved application 0.37.0. Its reservation moved to 0.38.0.
  #407 had merged SPEC_M1 at `specified`, so the script could not promote it; it was set to `released` by hand.
- **Reviewed by Grok and OB1-lite:** C1–C4 confirmed by both. OB1-lite re-cut the release in a scratch clone and
  every file matched except the three named edits. **Accepted (Grok):** #301's changelog entry names 0.37.0.
- **Found by OB1-lite (N1), confirmed on quay, filed as #410:** quay's `:0.37.0` and `:0.39.0` already existed as
  chart-version labels on an application 0.24.0 image.
- Hermetic suite: `5248 passed, 20 skipped, 608 deselected`.

### Epic B deployed and walked — PR #412 (merge `3d1c237`, 19:55)

- **My error, found by OB1-lite:** my draft credited the deploy gate for 0.37.0's deploy. Argo CD's auto-sync
  deployed `b087c78` at 00:05:54–00:06:11Z, 95 s after `publish.yml` finished and before the gate was checked. The
  report says so, from Argo's own history (`reports/2026-09-26_epic-b-release/walk/argo-history.txt`).
- **13 of 13 checks** on copies in a throwaway pod on the released image (`walk/walk.out`): #305's refusal, #301's
  copy, R1–R4 on the backup and R5 on #301's copy. R6, the live side, is not one of them: the review demoted it to
  "untouched by construction, not by measurement".
  The runbook's restore recipe was then run verbatim on the lab: 13 of 13.
- **The operator's request** (*"Pls put this screenshot in one the doc showing what successful backup looks
  like"*): `docs/RUNBOOK_backup_restore.md` gains "What a successful backup looks like", with three screenshots
  under `docs/screenshots/`, each rendered from real lab output.
- **Accepted from both reviewers:** every fact the README quoted is now a file under `walk/`; picture 2's caption
  gives the copy's own stamp; the runbook says which picture is the live pod. **Accepted (OB1-lite):** what the
  checks do not prove, and F1 (the walk script prints FAIL instead of crashing when no group qualifies).
- **My slips, fixed before the merge:** R6 was first read on `gsd.db`, whose size WAL mode leaves unchanged
  (9,842,688 bytes in both readings, `walk/live-wal-*.txt`); it was re-read on `gsd.db-wal`, and the review then
  demoted R6 to "untouched by construction, not by measurement". The first walk pod failed because the hardened
  image has no `sleep`; it has no `sha256sum` (#382's summary), `grep` or `tail` either, and the walk and the
  runbook use `python3.14`, the pod's own interpreter (the runbook's list of what the pod has).
- The PVC UIDs were unchanged.

### #291, the fleet login consolidated — PR #411 (merge `cbe828b`, 19:20)

- **Built by OB1-lite**, behaviour unchanged: `gsd/fleetlogin.py` 742 → 734 lines, 32 → 30 functions and methods.
- **Measured by both reviewers (Grok, Codex Astra):** the static and runtime fingerprints of the old and new module
  are identical; all 236 `gsd.*` log records the five fleet test files produce are byte-identical; the five files
  pass unedited.
- **Kept as proposals for the operator**, not in the PR: a shared `scrub()`, a test pinning the exception type in
  the revoke-failure text (the M2a/M2b mutation gap, which predates the change), and the runtime-capture plugin.
- #291 stays open for its live check at Epic C's release.

### The secrets-mint image and its deadline — PR #413 (merge `6451a32`, 20:19)

- **The operator:** *"Put ose-cli 4.18 and above"* and *"I like this image: registry.redhat.io/openshift4/ose-cli-rhel9
  v4.22"*. `secretsMint.image` now defaults to it. Chart 0.58.6.
- **Measured on the lab first:** v4.18 and v4.22 both pulled through the cluster's pull secret. OB1-lite then ran
  the rendered Job script, unchanged, on both tags under the Job's own securityContext and ServiceAccount. RBAC
  render: 13 objects and 19 rules each side, REMOVED 0, ADDED 0.
- **Accepted (both reviewers):** the docs say an unpullable image fails the install or upgrade, since the Job is a
  hook, and that a disconnected cluster needs an ImageTagMirrorSet (the reference is a tag). **Accepted (Grok N1):**
  a test pins the rendered image and the three documents.
- **The operator:** *"120-second deadline why? This might be too small for a larger cluster"*, then *"So set it 300
  then"*. The deadline also counts the image pull: 445–479 MB (OB1-lite), 21.6 s for v4.18's first pull on the lab.
  It is now `secretsMint.activeDeadlineSeconds`, default 300, matching Helm 4's 5-minute hook wait; 500 would
  outlast Helm's wait. The test fails on the old template (2 failed). Grok confirmed `d7d690b`.

### Fable's composition review of Epics A and B

- **The operator:** *"We can review both epic A and B with fable when done … But continue other epics before we
  review them."* OB2 (Fable 5.1, high) ran in the background on the two epics' merged diff while Epic C started.
- **Verdicts** (OB2's report as delivered, committed with #418 as
  `reports/2026-09-26_epic-b-release/fable-composition-review/report.txt`, with its drive scripts and logs): K1, K2
  and K4 CONFIRMED, measured with real `Store` runs under simulated image versions; K5 CONFIRMED by a hermetic suite
  run that left no `gsd.db` or `pre-upgrade/` in the tree; K3 CONFIRMED for the merge-commit flow `merge-safe.sh`
  uses, a rebase merge being the risk; **K6 REFUTED**, the one composition defect: nothing checked which application
  an image tag held before a deploy. K7 PLAUSIBLE.
- **The operator:** *"Apply those you accept only and tell fable why you refute some."* Every recommendation was
  accepted: K6's guard (#414), K4's and K2's runbook paragraphs (#414), and K7(b), #305's refusal naming the
  pre-upgrade copy (#414). K7(a) and a `.pyc` note needed no action. OB2 was told the dispositions.
- **K3 is the operator's decision:** disabling rebase merging is a repository setting, and has been asked.
- **Design input to #410:** a digest pin cannot close the auto-sync race, since the digest exists only after the
  merge; the check has to run on Argo's side, for example as a PreSync hook. Posted on #410.

### #410's guard: `release-crc.sh --argocd` reads the images back — PR #414 (merge `fc54f02`, 21:28)

- OB2's patch and 5 tests. They fail on the old script, which handed the stale image to Argo and reached
  Synced/Healthy.
- **Reviewed by Grok and Codex Astra; applied by OB1-lite in `bda1197`.** **Accepted (both), Grok's smaller fix:**
  each image is checked against its own pin (`image.tag`, `reporting.image.tag`). **Accepted (Codex F2):** every
  Linux child of a manifest list must carry the label. **Accepted (Codex F4):** the runbook no longer promises
  recovery when the first snapshot write fails. **Routed to #410 (Codex F3):** handing Argo a fixed commit changes
  the lab from tracking `main`; that is one of #410's design options.
- **Found by the implementer before pushing:** a SIGPIPE (exit 141) on the real 152 KB `values.yaml` would have
  made the guard refuse every release. A test now runs the guard on the shipped file.
- **Measured on quay:** `:0.37.0` passes, `:0.39.0` is refused as application 0.24.0, `:0.38.0` is refused as
  absent. `test_release_crc.py`: 31 passed. Grok confirmed `bda1197` and `14b6fd7` (K7(b)).
- **Not fixed here:** Argo can still deploy before the script runs. #410 stays open.

### Epic C: #315, the credential gate per account — PR #416 (merge `ed3edda`, 21:13)

- **Specified and built by OB1-lite** from `docs/specs/SPEC_S4d_credential_gate_per_account.md`; both spec rounds
  were reviewed by Grok and Codex Astra before any code. Chart 0.58.7 (docs only).
- **The budget, measured by the implementer and re-measured by both reviewers:** 4 targets answering 401 or 500
  give **1** authorize, where it was 4; two URLs for one cluster give 1; #293's two successful onboardings still
  give 2. The code equals the spec's blocks, byte for byte, apart from the spec's two status cells.
- **Accepted (Grok C5):** `docs/CLUSTER_STANZA.md` still stated the per-target key; fixed by S4d block 23, with a
  document-contract case that fails before. Hermetic suite: `5276 passed, 19 skipped`.
- **Found by Codex in the spec review and by OB1-lite while implementing, filed as #415:** a values `apiUrl` could
  carry userinfo. Codex's F1 on the spec found it; F1's accepted fix stripped userinfo from the gated detail, and the
  values parser's acceptance was left as the residual #415.
- #315 stays open for its lab walk at Epic C's release.

### Epic C: #415, userinfo refused in a values `apiUrl` — PR #417 (merge `f82a065`, 21:54)

- `clusters[].apiUrl` with userinfo, a query or a fragment now fails both `helm template` and the pod's loader, as
  the cluster Secret's `server` already did. The message never repeats the value. Chart 0.58.8.
- **Found by Grok and Codex Astra (F1), accepted, Grok's fix:** the render check matched `^https?://` case-sensitively
  and untrimmed, so `HTTPS://user:secret@host` or a padded value rendered the credential into the ConfigMap. The
  loader refuses both, but only at its scheme check, after Helm has rendered them. The check now trims and matches
  case-blind. Two new matrix cases: **4 failed** before the template edit, **88 passed** after.
- Neither reviewer found a loader bypass (Grok's C3 traced every other URL entry path).
- Full suite on the head, browser tests included: `5914 passed, 23 skipped`.
- **My slip, corrected:** I first posted that run on #417 as the hermetic suite; it had no deselection, so it
  includes `test_ui.py`. The comment was edited to say so.
- #417's `Closes #415` line closed #415 on the merge, but its Definition of Done still owes the release and deploy
  with its epic. It was reopened at 02:55Z with its first two boxes ticked. #315 and #291 were never closed (their
  PRs say "Part of"), and every box on both is still unticked.

### Epic B closed

- #298, #301 and #305 are closed, each with its evidence. #382's summary carries the release, the deploy, the walk,
  the three screenshots and the Fable verdict. This log is its last box.

---

## Part 15 — Epic C released as 1.0.0; the versioning rule; Epic D begun; #432 fixed (2026-09-26 23:03 → 2026-09-27 12:11)

Times are git author times in America/Chicago; a PR's merge time is its merge commit's on main
(`git log --first-parent e975410..6a83e3e`). Instants a comment gives in UTC are kept in UTC, with the local time beside
them where it matters.

### #285, the credential lifecycle — PR #419 (merge `602a1c4`, 03:39)

- **Specified by OB3:** SPEC_S4c was brought to main `f82a065` with 74 implementation blocks across 32 files
  (`1d38c67`, 2026-09-26 23:03). The orchestrator's check: `74 blocks check out across 32 files`, exit 0.
- **Spec review, round 1 (Grok and Codex Astra on `1d38c67`; decisions at 23:45):**
  - **Found by both, accepted in principle (F1):** a process that dies between the authorize and `refuse()` costs 2
    authorizes, measured by both.
  - **Accepted (Codex F2):** a successful onboarding's per-target mark suspended a self-login account, or silenced
    the ping, on that target.
  - **Accepted (F3, both; F8, Codex):** an `IndexError` for an account with no ping target; the regression tests.
  - **Rejected (Codex F7):** a namespaced Role for the election-off Lease grant. The same cluster-wide rule exists
    with election on. It was split out as #420 (filed 01:20).
- **OB2 (Fable, high) settled the four disputed findings (00:10); all four rulings accepted:**
  - D1: the attempt is reserved on the one `refused` entry by a strict compare-and-swap, before the password is sent.
  - D2: the scrypt fingerprint is salted with the account and the password Secret's `metadata.uid`.
  - D3: a refusal suspends the account's self-login sessions within one discovery cadence.
  - D4: a held session token is redacted from the standing finding.
  - **Rejected:** Codex's fail-closed on an absent Lease (it makes the install two steps), and its minted HMAC key
    (not required: OB2 measured that the uid closes the same oracle).
- **Round 2 (on `2d710fd`; decisions at 01:42).** Grok approved with one change; Codex refuted C1, C2, C3 and C5.
  - **Accepted (C5), only with Codex's per-attempt nonce.** The orchestrator ran Codex's probe:
    `literal_proposal_erased_other_reservation= True`. **Rejected:** the byte-identical cleanup rule.
  - **Accepted (Codex F1):** a stale refusal's retry bound a rotated password twice (`new password authorizes=2`).
  - **Accepted (Codex F2 and F3):** only an uncertain entry inside its own attempt window is deferred; a
    redaction-only refresh runs before every self-login revoke.
- **Round 3 (on `64e84d8`; closed at 02:48).** Grok confirmed C1–C6.
  - **Accepted (Codex R3-1):** a late self-login success could install its session over a sweep's suspension. The
    new test gives 2 failed on `64e84d8`'s blocks and passes with the fix. The fleet files: 264 passed and 2 failed
    before, 266 passed after.
  - Full suite on a git copy with the 93 blocks, browser tests included: `5979 passed, 19 skipped, 4 deselected`.
  - **A correction to the record:** OB3's round-2 figure "5996 passed" was its tree's collected count, not a pass
    count.
- **Applied** by the orchestrator as the 93 blocks (`c56f7af`, 02:57).
- **Code review (Grok and OB1-lite; decisions at 03:36).** Grok approved with no finding. OB1-lite's three findings
  were **accepted** with OB1-lite's code (`a61f371`):
  - N1 (security): after a Secret moved a cluster's URL, a live fleet token was presented to a host it was not minted
    for.
  - N3: #283's scrub had no rule for `Basic base64(user:password)`.
  - N2: the tab row called the last attempt's target "confirmed".
  - The four tests fail without the changes and pass with them. The fixes went into the spec as nine more blocks,
    102 in all.
  - Full suite, browser tests included: `6001 passed, 19 skipped, 0 failed`.
  - Grok confirmed `a61f371`: 20 concurrent poll-and-sweep runs gave at most one revoke of the minted token.
- Chart 0.59.0. The application code shipped with Epic C's release.

### #310 Part B, a retrieved token expiring — PR #421 (merge `44271d8`, 04:10)

- **Written by Codex Astra** from #310's comment. `docs/VALIDATION_satokenlookup.md` gains Case G, with the captures
  under `reports/2026-09-27_token-expiry-310/`:
  - G1: the validation leeway, +36 s and +42 s past `exp`, from go-jose's one-minute `DefaultLeeway`;
  - G2: a 401 cannot tell expiry from revocation or a withdrawn grant;
  - G3: discovery latency, 8m30s for a new Secret and 3m42s for a rotated one.
- **Found by Grok and OB1-lite (C2), accepted — the orchestrator's error, retracted.** The orchestrator had
  "corrected" Codex's upstream anchor `#L21-L25` to `#L15-L18`, reading the lines from WebFetch's summary. That
  anchor pointed at the licence header. Measured with `curl … | nl -ba`: `DefaultLeeway` is at L22–L25. The link now
  cites go-jose v2.6.3, the fork and version Kubernetes v1.35.0 pins.
- **Accepted (OB1-lite):** C1, the pod was replaced from 2026-09-27T08:44:51Z, not restarted; C5, what Case G did
  not measure; one volunteered sentence quoted verbatim. **Accepted (Grok):** straight quotes.
- **Not taken:** "causes" → "will cause". The quotation is the comment's.
- `test_docs_citations.py`: 1141 passed, 15 skipped.

### #286, the OAuthAccessToken policy — PR #422 (merge `b679701`, 04:51)

- **Built by OB1-lite**, no deletion code. `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md` gains the policy on
  the `OAuthAccessToken` objects a login leaves. Chart 0.59.1.
- A new test checks that a DELETE names only the object of the token that authorises it. Three mutations each fail
  only the new test.
- **Lab counts, read-only, 2026-09-27T08:52:23Z:** 189 objects in all; 131 oauth-proxy; 30 challenging-client; the
  fleet account still at 2.
- **Round 1 (Grok and Codex Astra), all accepted:**
  - Codex C1: §6 narrowed to what the code attempts. Two history facts Codex could not read (no GitHub in its
    sandbox) were kept, cited to #286.
  - Codex C2: the fleet account's count dated by the lab read, not removed.
  - Codex C3: a stronger test. Over 20 mutations the old test was wrong on 10, the new one on 0 (OB1-lite's run).
  - Grok C6: the source check matches use of the token API, not a help string.
- **Round 2 (Codex's confirmation):** the test confirmed, 15 of 15 cases. Text corrections A–D and a CHANGELOG
  replacement **accepted** verbatim, after both premises were traced.
- Docs, chart, kyverno and fleet-login tests: 1274 passed, 15 skipped. RBAC REMOVED 0, ADDED 0.

### 0.38.0, cut and withdrawn — PR #423 (opened 04:58, closed unmerged 05:03)

- Cut as `121327e` (04:57) with `prepare-release.py --app 0.38.0`, under the operator's rule of that morning:
  *"bump it after each epic closed as well. But bump it now."*
- **Why it closed:** its closing comment, *"Superseded by the 1.0.0 cut. The operator's ruling (2026-09-27) makes an
  epic's release a semver MAJOR, so Epic C is 1.0.0, not 0.38.0."* The branch `release/app-0.38.0` was deleted
  unmerged.
- OB1-lite's review of `121327e` was carried over to #424.

### Epic C released as application 1.0.0 — PR #424 (merge `05e32c8`, 05:18)

- **The operator:** *"Major bump after each epic closed - that's a major release. But minor for every issue merge;
  the commit sha being appended is normal."* Confirmed as semver MAJOR per epic: Epic C is 1.0.0, Epic D will be
  2.0.0, and each issue after it takes the next MINOR.
- Cut from `b679701` with `local-development/prepare-release.py --app 1.0.0`: application 0.37.0 → 1.0.0, chart
  0.59.1 → 0.59.2. quay had no `:1.0.0` or `:0.38.0` for either image. The entry is `docs/CHANGELOG.md`'s
  "Application 1.0.0 — chart 0.59.2".
- **Reviewed by Grok (on `ef4f945`, C1–C4 confirmed) and OB1-lite (on `121327e`, carried over).**
  - **Accepted (OB1-lite Fix 1):** the release note names the two entries outside Epic C, #414's read-back and
    #413's image.
  - **Accepted (OB1-lite Fix 2):** S4d's version cell names `app 1.0.0`. The test fails before (1 failed) and
    passes after. Docs, specs, kyverno and chart tests: 1262 passed, 16 skipped.
- **Both named the deploy race (#410), measured:** one of five recent auto-syncs came 36 s after a merge, against a
  69 s publish. **Agreed:** pause the auto-sync before merging, wait for the publish, check both `:1.0.0` labels,
  then deploy with `release-crc.sh --argocd main`.
- **Deployed** through `release-crc.sh --argocd main` at 10:22Z (05:22). The pod reported `version 1.0.0`, `commit
  05e32c8394` (#415's closing comment). #415 closed at 07:41 with every box ticked.

### The versioning rule, enforced by CI — PR #428 (merge `1cd67d5`, 06:06), closing #427

- **The operator** chose option (a): only a PR that changes what goes into the image bumps. Asked how the bump would
  be remembered, the answer was a CI check, not memory (#427).
- **Built by Codex Astra:** `local-development/check-app-version-bump.py` reads the image paths from `publish.yml`'s
  `on.push.paths` and requires exactly the next MINOR or MAJOR. The rule is in `docs/RELEASING.md`.
- 35 tests: **35 failed** against an empty script, **35 passed** with it. Hermetic suite: `5444 passed, 19 skipped`.
- **Found by OB1-lite (C8a), accepted:** a version-only PR, which is what an epic's release is, returned before
  either version was read. Moves to 1.0.1, 0.9.0, 3.0.0 and 1.2.0 all exited 0.
- **Accepted:** OB1-lite's C8b, `--no-color` on the hunk diff; C7 from both, one line of WHY per comment. The new
  tests: 6 failed before, 43 passed after.
- The check became a required status check on `main` at 06:09; the before and after lists are on #428. #427 closed
  with every box ticked.

### Target versions in the skills — PR #429 (merge `22a485c`, 06:23)

- **The operator:** *"set target image major and minor versions that we plan to build in our Issues and epic. That is
  what we do in a real devops shop"*, then *"So update our issues and epic skills"*.
- `.claude/skills/epic/SKILL.md` and `.claude/skills/issue/SKILL.md`: an epic's milestone is its MAJOR release; each
  image-changing issue names the MINOR its own PR takes. Milestones 1.0.0 (Epic C) through 5.0.0 (Epic G) were
  created, and every open child of Epics C–G assigned.
- **Reviewed by Grok.** **Accepted (C1):** "none" only outside `publish.yml`'s paths. It had already misled the
  orchestrator: #410 was first given "none". **Accepted (C4):** the column and header wording.
  `test_docs_citations.py`: 1152 passed on the first head, and passing after the fix.

### Version bumps stay manual, one PR at a time

- **The operator's decision**, as the brief for this log states it (the record shows it applied, not quoted): no
  automated bump. One version-bumping PR merges at a time, and the next one is renumbered by hand.
- `docs/RELEASING.md` carries the step: "After another PR claims a MINOR, merge main into the remaining PR and take
  the next MINOR."
- **Applied three times:**
  - #434's body: first in the merge queue; "#314 follows and is renumbered by hand after this merges".
  - #437's body: "renumbered by hand after #434 took 1.2.0 and 0.59.4 (merge commit `418b59f`; only the four version
    files conflicted)".
  - #438's body: "set by hand after #437 took 1.3.0".
- **Stale targets, found while writing this log:**
  - #425's header still names target 1.3.0, which #437 took.
  - #430's branch carries application 1.1.0 and chart 0.59.3, which #431 took. #431's body moved #430 to 1.2.0, which
    #434 then took.
  - Each takes the next free number at its turn.

### Epic C's composition fixes — PR #431 (merge `6740e1e`, 08:35), application 1.1.0

- **OB2 (Fable) reviewed Epic C's composition.** Every finding was accepted, and the code is OB2's patch, traced by
  the orchestrator. OB2's report is not in the repository; its findings are in #431's body.
  - **K2:** the ping built `FleetLogin` with no `secrets=`, so a remote echoing a held poller or self-login token put
    it in three log events and the standing finding the API serves.
  - **K7:** a refusal held only in this process's gate stamped `ping-last-attempt` for a login never made.
  - **K4:** the delete-name guard now also names another module calling `_revoke` or `_delete_token`.
  - **K1/K5:** 1.0.0's notes and SPEC_S4c now say a recreated Secret re-arms only after the pod restarts.
  - **Confirmed by OB2 (K6):** one wrong or locked password costs exactly 1 authorize over lookup, ping and
    self-login together, two replicas, a restart and three targets.
  - OB2's tests: 4 failed and 1 passed before; all pass after.
- **Reviewed by Grok and Codex Astra.**
  - **Accepted (Codex C4):** 1.0.0's #315 entry said a restart clears the refusal; with #285's Lease it does not.
    The docs pin fails on the old text (1 failed).
  - **Accepted (Grok C7):** a duplicate bullet removed.
  - Grok's C3 note, that the syntax guard would flag an unrelated attribute named `_revoke`, is the guard's stated
    limit; no change.
  - Full suite on the head, browser and TLS tests included: `6063 passed, 20 skipped, 0 failed`.
- Application 1.1.0, chart 0.59.3, cut with `prepare-release.py --app 1.1.0 --no-commit`: the first MINOR after Epic
  C. The auto-sync was paused around the merge, as for 1.0.0. The walk report records the pause lifted by 1.1.0's
  `release-crc.sh --argocd main`; no deploy time is recorded.
- **Noted, not fixed:** the stand-down line quotes a Lease entry's `target` raw. Only a hand-edited Lease could plant
  text there.

### The Epic C walk, which found #432 — PR #433 (merge `dc61012`, 09:06)

- **Walked by OB3** on application 1.0.0, chart 0.59.2, read-only: `reports/2026-09-27_epic-c-walk/`.
  - The start and end invariants are equal. The oauth-server audit log shows 0 authorizes for the fleet account and 0
    for `developer` across the walk. The PVC UIDs are unchanged.
  - One Definition of Done row met: #286's single daily cadence, the fleet account's token count 2 before and 2 after.
- **The live steps did not run.** `developer`'s walk password never arrived: the walk checked for it every 60 s from
  12:43Z to 13:19:37Z (`WALK_ENV_ABSENT after 36 minutes`).
- **Found by the walk (OB3), filed as #432 at 08:33:** SPEC_S4c §3.12 steps 2–3 would send `developer`'s password,
  then a wrong one, as the fleet account `ocp-oauth-bind-serviceid`. Measured on the deployed code with
  `reports/2026-09-27_epic-c-walk/hermetic/test_walk_password_scope.py`: 2 authorizes, or 3 with a restart.
- The walk found Argo's auto-sync paused and left it alone. The pause was the orchestrator's, for #431's release
  (corrected in `6545292`).
- **Reviewed by Grok and OB1-lite on `6545292`; C1–C6 confirmed by both.**
  - **Accepted (OB1-lite N1):** pinging only the accounts the Secret holds would not close #432. The lookup and
    self-login also present the one password as a stanza's `ldapConnectionBootstrap` account
    (`reports/2026-09-27_epic-c-walk/hermetic/test_432_scope_beyond_the_ping.py`, 2 passed, re-run by the
    orchestrator).
  - **Accepted:** the precondition in "How to resume" (OB1-lite), the due-test in full (Grok), and the per-subject
    RBAC result, REMOVED 0 with the walk grants (OB1-lite).
  - **Routed to #432 (Grok, note 2):** a committed ping-on case for the self-login arrangement.
  - `tests/test_docs_citations.py`: 1161 passed, 15 skipped.
- **Found while writing this log:** #432 was closed at 09:06 (14:06:32Z) by #433's merge, before its fix existed.
  `gh api repos/ephico2real2/group-sync-dashboard/issues/432/timeline` attributes the close to commit `2595bea`. The
  only "close … #432" in that message is "cannot close #432 alone", split across two lines. #432 is still closed;
  its last comment lists the walk as still owed.

### Epic D step 1: #311, Refresh — PR #434 (merge `7cb07f0`, 10:16), application 1.2.0

- **Decisions on #311 (posted 08:39)**, settled on the recommended options; `docs/specs/SPEC_D3_cluster_refresh.md`
  records them as the operator's:
  - the route `POST /api/clusterconfigs/{name}/refresh`, cluster-admin only;
  - registered with the writes switch, like `/test`;
  - every non-retired row;
  - a pending `saTokenLookup` row answers its reason, with no network call.
- **Specified and built by OB1-lite.** Refresh probes with the credential the dashboard holds and answers in the
  poller's words. It stores nothing, rotates nothing and never calls FleetLogin. Every live card gets a Refresh button
  with four states that survive the repaint.
- **The implementer's measurements:** 19 failed before; `tests/test_cluster_refresh.py` 18 passed after; six
  mutations caught; hermetic 5485 passed, 19 skipped; browser 607 passed; RBAC REMOVED 0, ADDED 0.
- **Reviewed by Grok and Codex Astra on `77360c7`.**
  - **Accepted (C4, both):** a successful probe did not scrub the remote's text. Grok measured `C4_TOKEN_IN_BODY
    True`. Every outcome is now scrubbed; the new test fails before (1 failed, 18 passed).
  - **Rejected (both):** adding `ca_data` to the scrub list. A CA is public trust material.
  - **Rejected on the facts (Codex C1/P1):** URL userinfo would send Basic auth, but it cannot reach Refresh: every
    production constructor of `ClusterConfig` sits behind a loader that refuses userinfo. The operator accepted the
    verdict, and the principle became #435.
  - **Accepted on the fact, fix rejected (Codex P2):** a click records the usage row and counters every request gets.
    The spec now says Refresh adds none of its own. The ContextVar suppression would grow the code.
  - **Rejected (Codex C8):** the spec's status `merged` is right by `docs/specs/README.md`.
  - Tests after the fix: 1338 passed, 15 skipped.
- **Lab check on #311 (posted 10:41), API level**, at `b18e62d` (application 1.3.0, which carries 1.2.0):
  - the pod runs `:1.3.0`, digest `sha256:fd211729…`, revision label `b18e62d660`;
  - as `kubeadmin`, `POST /api/clusterconfigs/shared-rnd/refresh` answers 200 `ok`;
  - an unknown name answers 404, and `developer` gets 403;
  - the pod log has one `cluster-refreshed` line and no `fleet-login` or ping line.

### Epic D step 2: #314, the shared-URL warning — PR #437 (merge `b18e62d`, 10:35), application 1.3.0

- **Decision on #314 (posted 08:39):** `warnings` is a list of `{code, clusters, detail}` on `GET
  /api/clusterconfigs`, separate from `findings`. #244's CA-expiry warning will reuse it.
- Discovery compares every effective entry by normalised API URL, using the credential gate's own rule. One
  `shared-api-url` event when a group appears, one when it clears. The tab shows a banner and a card chip. Nothing is
  refused.
- **Reviewed on `c5af507`.** Grok confirmed C1–C7.
  - **Accepted (OB1-lite F1), over Grok's C3:** a disabled entry joins no group, since it is not polled. The new test
    fails before (1 failed, 13 passed).
  - **Accepted (OB1-lite F2):** the design doc's sample log line printed `WARN` where the logger prints `WARNING`.
  - Both reviewers removed the wiring and saw the API and log tests fail on real assertions.
- Renumbered by hand to 1.3.0 and chart 0.59.5 after #434 (`418b59f`). Full suite on the merged tree, browser tests
  included: `6124 passed, 19 skipped`. RBAC REMOVED 0, ADDED 0 (the implementer's render).
- **Lab check on #314 (posted 10:41):**
  - the API returns one `shared-api-url` warning naming `shared-qa` and `shared-rnd`;
  - 10 of the lab's 16 disabled entries declare the same URL, and none is in the group: F1, measured. Without it the
    banner would list 12;
  - the log fired once, at cycle 1;
  - a correction in the same comment: two entries it first named declare a different URL.
- The browser walks of #311 and #314, with screenshots, wait for the walk password.

### #432 → SPEC_S4e → PR #438 (merge `6a83e3e`, 12:06), application 1.4.0

- **The defect:** the ping took its account from a retrieved Secret's `lookup-account` annotation, but its password
  from the one Secret configured today. After a username change, a removed stanza or a repointed Secret, it sent one
  account's password as another's.
- **Specified by OB3:** `docs/specs/SPEC_S4e_ping_account_scope.md` (`b341697`, 09:55). The rule: only a declaration
  authorizes an account — the chart's username, or an `ldapConnectionBootstrap` from a stanza, a retrieved Secret's
  explicit value or an accepted ConfigMap declaration. Never a generated output's annotation. An account nothing names
  stays listed from its Lease, and no password is read for it.
- **First review round (Grok and Codex Astra on `b341697`).** The spec's notes call it round 1; #438's body calls it
  round 0. Each reason is in the spec's Orchestrator's notes.
  - **Accepted (Codex C2):** a hole in the first filter. A ConfigMap output's annotation alone could authorize an
    account.
  - **Accepted (both, C4):** the first draft's two narrowings were not needed. A Secret's explicit account is still
    pinged, and an account no longer named stays visible.
  - **Accepted:** the Lease wording (one `refused` record, not a history), `.fullmatch()` for a trailing newline, the
    walk's live re-check before each password step, and the §3.2 table's cases.
  - **Rejected:** Codex's offline `check-ping-walk.py`, three of Codex's tests and two of Grok's, and Grok's
    `declared-account` annotation and `named` flag.
- **Second round (on `bb25e3f`):** both reviewers returned READY for phase 2. The orchestrator signed off OB3's two
  departures from the reviewers' code, both less code: a `targets` filter that could not change an outcome, and an
  `and oauth is None` clause. Putting either back fails none of the 386 fleet tests.
- **Phase 2, rebased onto `b18e62d`:** all 21 blocks applied. Two moved with the meaning unchanged: `writer.py`'s
  import line after #434, and the CHANGELOG insert under the existing Unreleased heading.
- **Measured:**
  - the code is +28/−10 lines across `config.py`, `poller.py`, `onboarding.py`, `parser.py` and `writer.py`;
  - 14 new tests fail before and pass after (OB3's run; Grok's re-run of the fleet set: 14 failed before, 520 passed
    after);
  - 12 of 12 mutants caught;
  - RBAC REMOVED 0 and ADDED 0 in 8 renders;
  - full suite on the head, browser tests included: `6156 passed, 19 skipped`;
  - the lab, read-only at 15:48:02Z: one retrieved Secret, `gsd-cluster-shared-rnd`, made for a values stanza. No case
    on the lab changes.
- #438 has no decisions comment; its decisions are in its body and the spec's notes.
- **Deployed (posted on #432 at 12:11):** Argo rolled the lab at 17:10:11Z (12:10).
  - `:1.4.0` and `:1.4.0-6a83e3edda` share digest `sha256:5105600f…`; the report image is `sha256:ed2b9259…`.
  - `/api/version` reports `1.4.0`, `dirty:false`.
  - The fleet account is the chart's declared username, so nothing changed for it. The new pod logged no
    `fleet-login`, `fleet-ping` or `fleet-logout` line. The kept PVCs are unchanged.
- **Still owed on #432:** the corrected SPEC_S4c §3.12 walk as `developer`. It waits for the walk password.
- `reports/2026-09-27_epic-c-walk/hermetic/test_walk_password_scope.py` pinned 1.0.0's defect. It fails against
  1.4.0 by design, and CI does not collect it.

### Filed and held

- **#435 (filed 10:05, Epic C, open):** `ClusterClient` refuses a userinfo URL before it sends anything. It comes from
  #434's Codex C1/P1: httpx turns userinfo into a Basic header that replaces the bearer. It is not reachable today,
  because all four entry doors refuse userinfo. The issue holds the rule at the one exit instead.
- **#436 (filed 10:06, no epic, open):** one diagram standard and one renderer across the repositories, published as
  `ephico2real2/diagram-kit`. The inventory found three copies of the renderer with two behaviours.
  - **The drift sync (posted 10:14, the operator's go-ahead):** the `/visual` skill's `render.py` is now this
    repository's `docs/diagrams/render.py`, apart from its usage line. With the font stylesheet answering 404, the
    synced copy exits 1; the old copy exits 0 with 8 PNGs in the fallback font.
  - **Found by the orchestrator's first test, a gap in both copies:** an undeclared font family is answered 200, so
    both exit 0 in a fallback font. It is left to #436's research.
  - `envoy-grpc-modernization`'s vendored copy is still the old one.
- **#425 (filed 05:08, Epic E, open):** move `:latest` to the newest `<appVersion>-<sha10>` on every publish. **The
  operator:** *"You need to move the latest tag too to current app version - sha10"*. Measured: `:latest` does not
  exist for either image.
- **#426 (filed 05:27, Epic E, open):** optional Argo Rollouts blue-green, and the operator's concern, the database
  migrations.
  - The research is on the issue (07:22). The orchestrator retracted its idea of the chart creating the
    RolloutManager (07:27): Red Hat allows one mode at a time, and the lab's operator is cluster-scoped.
  - Paused by the operator at 07:39 (*"We are not changing anything now."*), then clarified at 07:40 as background
    work.
  - OB1-lite's SPEC_W1 is pushed on `feat/426-rollout-blue-green` (`f7266dd`), not merged. It chooses option (d),
    each version on its own database copy. Its review runs in the background.
- **#430 (the draft PR for #410, opened 06:30, open and held):** Argo tracks a `release` branch that holds only the
  chart and the images pinned by digest. **The operator:** *"We shouldn't be rebuilding and syncing argo on main
  branches …"*.
  - Spec review by Grok and Codex Astra: round 1's F1–F5 accepted; round 2 closed.
  - The 51 blocks are applied in `0388448`. Full suite, browser tests included: `6091 passed, 19 skipped, 0 failed`.
  - **Held unmerged by the operator:** *"We are not changing anything now on the group sync dashboard"*.

### Operator decisions on older issues

- **#316, D8 (posted 23:01, 2026-09-26):** after the admin's own login, the dashboard asks the remote, with that
  login's token, whether this person can `update clusterrolebindings` there. A no refuses the Rejoin; the answer is
  logged either way.
- **#114, closed at 23:01 as decided, no code:** no narrower auditor tier. The operator: *"Cluster reader use list
  clusterrolebindings so indeed they can see all page except the kpi and cluster admin page."*

---

## Numbers

| | |
|---|---|
| Pull requests merged | **39**: #309, #313, #317, #320, #323, #324, #325, #326, #327, #328, #329, #330, #331, #333, #334, #335, #336, #337, #339, #342, #343, #344, #345, #349, #350, #351, #352, #354, #355, #356, #357, #358, #359, #360, #361, #362, #363, #364 and #365 (`gh pr list --state merged`, merged since 04:11). Part 9 adds #366, #367 and #368; Part 10 adds #370, #372, #373, #374 and #375; Part 11 adds #376, #377 and #378; #379 (Part 11's log, merged 02:57) and Part 12's #380, #395, #396, #397, #398 and #399 are added; Part 13 adds #400, #401, #402, #403, #405, #406 and #407. Part 14 adds #408 (Part 13's log), #409, #411, #412, #413, #414, #416 and #417. Total through Part 14: 72. Part 15 adds #418 (Part 14's log), #419, #421, #422, #424, #428, #429, #431, #433, #434, #437 and #438; #423 closed unmerged. Total through Part 15: 84 |
| Commits on main | 30: 27 squash commits, one per PR, from `a9f0875` to `4f4c070`; then #354's two commits and its merge commit `b647db4` (`merge-safe.sh` merges with `--merge`). Measured: `git rev-list cb64f81..b647db4` counts 30, 28 on the first-parent line, 1 merge. Part 15: `git rev-list e975410..6a83e3e` counts 53, 11 on the first-parent line (one merge commit per PR), 17 merges and 36 non-merge commits |
| Commits authored in the session | 45 non-merge and 18 merge commits on the merged PRs' branches (author time from 04:11). Another 13 commits of the merged PRs were authored before the session. Counted from each PR's commits through `gh api`, with the parents counted. Part 7 adds 9 non-merge commits (`a4c2f75`, `83872bf`, `47e9b73`, `cbd18b9`, `7739e07`, `ea2b7b2`, `ce3d8e2`, `061c224`, `c7a9b26`) and 2 merge commits on #352's branch (`82ad236`, `0989ca6`, main merged in; #352's commit list through `gh pr view`). Part 15 adds the 36 non-merge commits of `e975410..6a83e3e`, authored 2026-09-26 23:03 → 2026-09-27 11:48, and 6 merges of main into PR branches (on #419, #422, #433, #434, #437 and #438). #423's `121327e` was authored and never merged; #430's and #426's branches are not counted. |
| Review passes run | 48. That is 24 on #309–#337: 12 from `docs/REVIEW_2026-09-23_release.md`, 7 from #336's commit messages and 5 from #337's. Then 14 on #339, across six heads, and one each on #342, #343, #344 and #345. None are recorded for #309, #313, #317, #320 or #323. Part 7 adds 6: Grok 4.6 once each on #349, #350, #352 and #354, and twice on #351 (the plan, then the head). Part 15 adds 33 on the merged PRs, counted from their decisions comments, bodies and SPEC_S4e's notes: #419 10 (three spec rounds of Grok and Codex Astra, OB2's rulings, the code review by Grok and OB1-lite, Grok's confirmation), #421 2, #422 3, #424 2 (OB1-lite's on #423's cut carried over), #428 2, #429 1, #431 3 (OB2's composition review, Grok, Codex Astra), #433 2, #434 2, #437 2 and #438 4. #430, unmerged, has 4 more. |
| Reviewer findings accepted / rejected | For #324–#334, the record's Outcome: 6 code findings accepted, 3 snippets rejected with measurements, 1 trial retracted by its author, and 1 test rejected as brittle. Spec findings C21 and C22 were accepted, and the operator decided C21. #334: 3 accepted, 1 rejected. #335 is itemised in Part 4. For #336–#345, `docs/REVIEW_remote_sar_for_every_join.md` itemises every finding: 20 proposals were rejected, each with its reason or the measurement that refuted it. One of them, Codex's B11, had first been accepted without a measurement. Part 15, counted by this log's writer from the decision lists (a finding accepted on the fact with its fix rejected counts on both sides): 56 accepted and 21 rejected. By PR, accepted / rejected: #419 16 / 4, #421 5 / 1, #422 9 / 1, #424 2 / 0, #428 3 / 0, #429 2 / 0, #431 2 / 0, #433 4 / 0 (one routed to #432), #434 2 / 4, #437 2 / 1, #438 9 / 10. |
| Defects found by tooling rather than reviewers | 7. Three in the release: the IME test race (CI, #331), the walk's skipped picker parameter (the walk's own failure, 80/81), and the focused option under the Generate bar (the walk, #332). One by CI on #339's first head (the specs index row). Three by the D2b lab walk: the Helm handover (#343), Step 6's stale page check, and Step 7's in-cluster row (#344). The walk also raised the host-guard question, closed in Part 7 as not a gap. Part 12 adds 2, both found by CI: the missing reports-index row on #398, and the ASCII preview step on #397 (fixed in #399). Part 13 adds 2: `test_kyverno.py`'s release-heading regex (found by the full suite on #403), and #404 (found by the Epic A walk). Part 14 adds 1: `test_specs_index.py`'s version collision on #409. Total through Part 14: 12. Part 15 adds 2: #432 (found by the Epic C walk), and the renderer's blind spot for an undeclared font family (found by the orchestrator's first test on #436). Total through Part 15: 14 |
| Full suite, final | For the release: **5339 passed** on integration head `d86acd6` (the orchestrator's run, the record's C16; the skipped count is not stated). For D2b: **5527 passed** on #342's head `fd9bfb9` (OB1-lite's run in a git copy, per the orchestrator's summary of its report); #342's body gives the non-browser suite as **4934 passed, 20 skipped, 0 failed**. CI (`gh pr checks`): 8/8 on every merged head, except #336 (7 passed, `grype` skipped) and #342 (9 passed, `container-smoke` skipped). Part 7: **5557 passed, 20 skipped** on #354's `061c224`, browser tests included (the orchestrator's run); CI 8/8 on #350–#352. Part 15: **6156 passed, 19 skipped** on #438's head, browser tests included (#438's body). CI (`gh pr checks`): every check passed on every merged head, 8 to 10 each; `container-smoke` was skipped on #419, #431, #437 and #438. |
| Longest single loss | The D2b lab walk: over 230 minutes of the operator's tokens, in the operator's words. The operator killed the process during Step 9, before its mock-log check ran, and a local podman container on that check's port would have made it untrustworthy anyway. What changed: one background waiter per step, and no polling. In Part 15 the Epic C walk waited 36 minutes for `developer`'s walk password, checking every 60 s, and it never came; the live steps of #285, #291, #310 Part A and #432 are still owed. What was written down: every step is prepared, in order, under the walk's "How to resume". |

## Where things are recorded

- `docs/REVIEW_2026-09-23_release.md`: the day's review record for #324–#335, including #335's own review and the
  orchestrator's own errors.
- `docs/REVIEW_remote_sar_for_every_join.md`: the review record for #336, #337, #339, #342, #343, #344 and #345.
  It covers every finding by reviewer and head, the rejections with their reasons, what the walk found, and the
  orchestrator's own errors.
- `docs/specs/SPEC_D2b_remote_sar_for_every_join.md`, under Orchestrator's notes: every #339 decision round by round,
  and the lab walk's corrections to §5.
- `reports/2026-09-24_d2b-lab-walk/`: the D2b walk, each step's script and raw output, and the e2e walk after the
  rejoin.
- `local-development/apply-spec-blocks.py` and `docs/specs/README.md` ("Implementation blocks"): how a spec's blocks
  are checked and applied. `docs/diagrams/render.py`: how the design's figures are re-rendered.
- `docs/REVIEW_S4b.md`: #295's record, merged as #309.
- `docs/specs/SPEC_S4c_credential_lifecycle.md`, under Orchestrator's notes: C21's ruling and the versions.
- `docs/DESIGN_remote_cluster_access.md`, its page `docs/diagrams/remote-cluster-access/source.html`, and
  `docs/ACCESS_CONTROL.md` §11.
- `docs/AUDIT_LOG_CAPTURE.md`, `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md`, `docs/polling-and-discovery.md`.
- `docs/design/nsaudit-mock.html`, `docs/design/nsaudit-feature-capture.md` and `reports/2026-09-21_nsaudit-mock/`.
- `reports/2026-09-23_release-walk/`: the walk, the release checks and both result files.
- `docs/CHANGELOG.md`, Unreleased: the chart 0.52.0 and 0.52.1 entries, and application 0.32.0 with chart 0.53.0.
- PR comments: #343 (the PVC baseline, Grok's decisions and the rerun), #344 (the corrected steps as run, and Grok's
  decisions), and #345 (OB1-lite's decisions).
- Issue comments: #261 (the evidence and part 4's decision), #318 (the operator's audit-log decision), #341 (the
  deferral) and #338 (the evidence). #210 lists OB3's two passes on #339 as owed a Fable re-review.
- `docs/HANDOVER_2026-09-20.md`: the living state document, brought up to this state.
- The tag `checkpoint-2026-09-23`.
- Part 14: `reports/2026-09-26_epic-b-release/` (the image gate, Argo's auto-sync history, the 13 checks and the
  scripts); review decisions on #409, #411, #412, #413, #414, #416 and #417; #382's Epic B summary; #410 (the race
  and OB2's PreSync input); #415 (the reopen).
- `reports/2026-09-26_epic-b-release/fable-composition-review/`: OB2's composition review of Epics A and B, K1–K7,
  as delivered, with its drive scripts, logs and the patch that became #414.
- Part 15, the specifications, each with its review rounds in its Orchestrator's notes:
  `docs/specs/SPEC_S4c_credential_lifecycle.md` (rounds 1–3, OB2's rulings D1–D4, the 1.0.0 numbering),
  `docs/specs/SPEC_D3_cluster_refresh.md` (#311's decisions and D3-1 to D3-4) and
  `docs/specs/SPEC_S4e_ping_account_scope.md` (both rounds, the declined proposals, the phase-2 rebase).
- Part 15, the reports: `reports/2026-09-27_epic-c-walk/` (the Epic C walk, its evidence, the two hermetic tests and
  the prepared steps) and `reports/2026-09-27_token-expiry-310/` (Case G's captures).
- Part 15, the rules: `docs/RELEASING.md` (MAJOR per epic, MINOR per image-changing issue, and taking the next MINOR
  after another PR claims one), `local-development/check-app-version-bump.py`, and the target versions in
  `.claude/skills/epic/SKILL.md` and `.claude/skills/issue/SKILL.md`.
- Part 15, `docs/CHANGELOG.md`: "Application 1.0.0 — chart 0.59.2", "Application 1.1.0 — chart 0.59.3", and 1.2.0 to
  1.4.0 under Unreleased.
- Part 15, the review decisions on the PRs: #419, #421, #422, #424, #428, #429, #431, #433 and #434 in comments; #437
  and #438 in their bodies (no decisions comment). #423's closing comment says why it closed.
- Part 15, the issues: the operator's rulings and the lab checks on #311 and #314; the 1.4.0 deploy on #432; #415's
  1.0.0 deploy; the required-check change on #428; the drift sync on #436; the research and the pause on #426; the
  spec rounds and the hold on #430; D8 on #316; #114's decision.

## State left behind

Written at the end of Part 15, as of 2026-09-27 12:15 CDT. The lab reads below were re-taken read-only for this log at
18:11:52Z (13:11 CDT).

- **main** is `6a83e3e` (#438): application 1.4.0, chart 0.59.6.
- **Deployed** on the lab: the `group-sync-dashboard` Application is `Synced`/`Healthy` at `6a83e3edda`, with the
  auto-sync on (`spec.syncPolicy.automated`: prune and selfHeal). Its last sync finished at 17:09:40Z. Both
  Deployments carry the chart 0.59.6 label, with the images `quay.io/ephico2real/group-sync-dashboard:1.4.0` and
  `quay.io/ephico2real/group-sync-dashboard-report:1.4.0`.
- **The kept PVCs** are unchanged: data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts
  `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` (`oc get pvc -n group-sync-dashboard`).
- **Open PRs:** #430, the draft for #410, held unmerged by the operator. Its branch carries application 1.1.0 and
  chart 0.59.3, so it takes the next free MINOR at its turn. The merged PRs' branches are gone from the remote
  (`git ls-remote --heads origin`); `feat/426-rollout-blue-green` holds #426's unmerged spec.
- **Waiting on the walk password** (the file the walk reads, which the operator creates):
  - the browser walks of #311 and #314, with screenshots;
  - the corrected SPEC_S4c §3.12 walk for #432, as `developer`;
  - the live steps the Epic C walk could not run: #285's steps 4–5, #291's live count and #310 Part A.
- **Epics:**
  - Epic B (#382) was closed at 22:15 on 2026-09-26, after #418 merged.
  - Epic C (#383) is released as 1.0.0, with 1.1.0 and 1.4.0 as its follow-ups. Its milestone has 8 open and 2
    closed issues. Its closure waits on #432's walk. #432 itself is closed, by a commit message (Part 15), with that
    walk still owed. #435 is open.
  - Epic D (#384): #311 and #314 are merged, deployed and checked at the API level; each stays open for its browser
    walk. #316's spec is in progress, with D8 decided. #244 is last.
  - Epic E (#385): #410 (#430, held), #425 and #426 (background work) are open.
- **Open for the operator:** the walk password; #430's hold; #310's OAuth restart for Part A. Carried from Part 14
  and not re-checked here: #255's ruling on expected grants (the issue is open) and #411's three proposals.
- **OB2's K3 is settled on the repository:** `gh api repos/ephico2real2/group-sync-dashboard` reads
  `allow_rebase_merge: false`. When it was turned off is not recorded in this log's sources.
