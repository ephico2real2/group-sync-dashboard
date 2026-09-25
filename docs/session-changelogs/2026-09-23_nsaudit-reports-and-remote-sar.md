# Session change log — group-sync-dashboard, 2026-09-23 → 2026-09-24

What this session did, when, and how each claim was measured. Times are git author times in America/Chicago; a PR's
merge time is its squash commit's on main. Every "measured" claim is one the session ran a command for; nothing below
is recalled from memory alone. Numbers are quoted as a PR body, a commit message, a review record or a report states
them, and each says where it comes from; where a PR's review decisions are written nowhere in the repository, the
entry says so. The session began at 04:11 on 2026-09-23; this log runs to the evening of 2026-09-24: #338's close
at 08:52, the cleanup, and Part 7. The product changelog (`docs/CHANGELOG.md`) says what each release changed for an operator; this
says what a working session did. The review decisions of #336–#345 are itemised in
`docs/REVIEW_remote_sar_for_every_join.md`; Part 6 cites it rather than repeating every line.

Outcome in one line: **twenty-eight pull requests merged. Login capture reads the audit log by default. #261's Namespace audit parts 2 and 3 shipped, and the issue closed. The 2026-09-23 release was deployed through Argo CD and walked (84/84 steps, 15/15 release checks), and its one defect was fixed (#332). The operator's mandate was built end to end: SPEC_D2b was reviewed on six heads and merged with 221 blocks (#339), implemented from those blocks alone as application 0.32.0 and chart 0.53.0 (#342), and walked on the lab (Steps 0–11, then the e2e walk at 84/84). #338 closed with its evidence. In the evening, #312, #346 and #347 were fixed (#350, #352, #354) and proved on the lab, and the specs and design indexes were brought to the evidence (#351).**

| | Before the session | After |
|---|---|---|
| main | `cb64f81` (#307 merged, 2026-09-22 17:28) | `b647db4` (#354 merged, 2026-09-24 20:00): 28 PRs merged, 27 as one squash commit each and #354 as a merge commit; the tag `checkpoint-2026-09-23` is on `7c0a42c` |
| chart / app | 0.51.0 / 0.31.0 | **0.53.1 / 0.32.0**: 0.52.0 from #320, 0.52.1 from #317, 0.53.0 / 0.32.0 from #342, and 0.53.1 from #350 (Unreleased) |
| deployed on the lab | not recorded in the repository | `4f4c070b08` through `release-crc.sh --argocd`, Synced/Healthy and verified in-pod; #354 is not deployed |
| open PRs | #309, #313, #317, #320 | none once this log's PR merges |
| issues | #261 open (part 1 shipped in #264; parts 2–4 not built), #318 open | closed: #261, #318, #332, #338, #346, #347 and #348. Opened: #321, #322, #332, #338, #340, #341, #346, #347, #348 and #353. #341 is deferred; #312 and #353 are handed to OB1 |

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

## Numbers

| | |
|---|---|
| Pull requests merged | **28**: #309, #313, #317, #320, #323, #324, #325, #326, #327, #328, #329, #330, #331, #333, #334, #335, #336, #337, #339, #342, #343, #344, #345, #349, #350, #351, #352 and #354 (`gh pr list --state merged`, merged since 04:11) |
| Commits on main | 30: 27 squash commits, one per PR, from `a9f0875` to `4f4c070`; then #354's two commits and its merge commit `b647db4` (`merge-safe.sh` merges with `--merge`). Measured: `git rev-list cb64f81..b647db4` counts 30, 28 on the first-parent line, 1 merge |
| Commits authored in the session | 45 non-merge and 18 merge commits on the merged PRs' branches (author time from 04:11). Another 13 commits of the merged PRs were authored before the session. Counted from each PR's commits through `gh api`, with the parents counted. Part 7 adds 9 non-merge commits (`a4c2f75`, `83872bf`, `47e9b73`, `cbd18b9`, `7739e07`, `ea2b7b2`, `ce3d8e2`, `061c224`, `c7a9b26`) and 2 merge commits on #352's branch (`82ad236`, `0989ca6`, main merged in; #352's commit list through `gh pr view`). |
| Review passes run | 48. That is 24 on #309–#337: 12 from `docs/REVIEW_2026-09-23_release.md`, 7 from #336's commit messages and 5 from #337's. Then 14 on #339, across six heads, and one each on #342, #343, #344 and #345. None are recorded for #309, #313, #317, #320 or #323. Part 7 adds 6: Grok 4.6 once each on #349, #350, #352 and #354, and twice on #351 (the plan, then the head). |
| Reviewer findings accepted / rejected | For #324–#334, the record's Outcome: 6 code findings accepted, 3 snippets rejected with measurements, 1 trial retracted by its author, and 1 test rejected as brittle. Spec findings C21 and C22 were accepted, and the operator decided C21. #334: 3 accepted, 1 rejected. #335 is itemised in Part 4. For #336–#345, `docs/REVIEW_remote_sar_for_every_join.md` itemises every finding: 20 proposals were rejected, each with its reason or the measurement that refuted it. One of them, Codex's B11, had first been accepted without a measurement. |
| Defects found by tooling rather than reviewers | 7. Three in the release: the IME test race (CI, #331), the walk's skipped picker parameter (the walk's own failure, 80/81), and the focused option under the Generate bar (the walk, #332). One by CI on #339's first head (the specs index row). Three by the D2b lab walk: the Helm handover (#343), Step 6's stale page check, and Step 7's in-cluster row (#344). The walk also raised the host-guard question, closed in Part 7 as not a gap. |
| Full suite, final | For the release: **5339 passed** on integration head `d86acd6` (the orchestrator's run, the record's C16; the skipped count is not stated). For D2b: **5527 passed** on #342's head `fd9bfb9` (OB1-lite's run in a git copy, per the orchestrator's summary of its report); #342's body gives the non-browser suite as **4934 passed, 20 skipped, 0 failed**. CI (`gh pr checks`): 8/8 on every merged head, except #336 (7 passed, `grype` skipped) and #342 (9 passed, `container-smoke` skipped). Part 7: **5557 passed, 20 skipped** on #354's `061c224`, browser tests included (the orchestrator's run); CI 8/8 on #350–#352. |
| Longest single loss | The D2b lab walk: over 230 minutes of the operator's tokens, in the operator's words. The operator killed the process during Step 9, before its mock-log check ran, and a local podman container on that check's port would have made it untrustworthy anyway. What changed: one background waiter per step, and no polling. |

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

## State left behind

- **main** is `b647db4` (#354), at chart 0.53.1 and app 0.32.0, both under `docs/CHANGELOG.md`'s Unreleased
  heading. The tag `checkpoint-2026-09-23` stays on `7c0a42c`.
- **Deployed** on the lab: `4f4c070b08` through `release-crc.sh --argocd`, Synced/Healthy and verified in-pod. #354 is
  not deployed; its lab check is handed over (below).
- **`shared-qa`** is rejoined with a ServiceAccount token that has no expiry (Step 11). `shared-rnd` is served from
  the Secret the lookup rewrote in Step 4.
- **The kept PVCs** have the same UIDs, volumes and 2026-09-19 creation times as the walk's baseline, re-read after
  the `4f4c070` deploy: `group-sync-dashboard-data` has UID `f065b7a4-535c-4ef1-868c-58f5afee4953`, and
  `group-sync-dashboard-report-artifacts` has UID `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`.
- **Open PRs:** none once this log's PR merges.
- **Handed to OB1 (Fable 5.1)** at the operator's instruction:
  - #312: deploy main with #354, check that nothing regressed, post the evidence, close.
  - #353: the capability to honour the operator's label on ServiceAccount and User grants. Spec, review, then code.
- **Open issues from this session:**
  - #321: remove the Debug path.
  - #322: the cluster-admin tier, decided and not built.
  - #340: the CA cache.
  - #341: deferred.
  - #312 and #353, handed over above. #346 and #347 are closed with this folder's evidence.
- **Carried, not acted on:**
  - NA-2: markdownlint MD012 in `docs/specs/README.md`, pre-existing.
  - `docs/ACCESS_CONTROL.md` keeps six pre-existing MD040 findings (#336's and #337's bodies).
  - `docs/CLUSTER_STANZA.md` still says "Fourteen refusals fail `helm template`", a count Grok called stale.
  - `docs/design/data-requirements.md` still describes gaps the implemented mocks closed, and S3's version cell in
    the specs index names only its merged part (both noted by #351's review).
  - `reports/README.md` lists 7 of the 28 report folders.
- **Worktrees:** the main checkout, and `gsd-grafana`, detached at `4f93ad1` with its three uncommitted PNGs.
