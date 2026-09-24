# Review — remote-sar for every way a cluster is joined: #336, #337, #339, #342, #343, #344, #345

The review record for the remote cluster access work of 2026-09-23 and 2026-09-24: the design (#336), D3 and the
operator's mandate (#337), the specification SPEC_D2b (#339), its implementation (#342), the two fixes the lab walk
forced (#343, #344) and the walk's evidence (#345). They close #338, the mandate as an issue: *"this is what I want:
remote-sar for whatever method the cluster was joined"* (the operator, 2026-09-23).

Written on 2026-09-24, after the last merge, from what was recorded at the time. Nothing here is recalled:

- **#336 and #337:** their commit messages, which are the only record of their review decisions.
- **#339:** the Orchestrator's notes in `docs/specs/SPEC_D2b_remote_sar_for_every_join.md`, which hold every decision
  round by round; the messages of its eight commits; and the reviewers' own reports, which are kept outside the
  repository and quoted here claim by claim. Two of OB1-lite's reports were delivered as messages, not files: its
  first pass on `ac194fe`, which the notes summarise, and its confirmation of `8460257`, stated here as the
  orchestrator's summary.
- **#342:** OB1-lite's report, delivered as a message; the orchestrator's summary.
- **#343, #344 and #345:** the decision comment on each PR, and Grok's and OB1-lite's own reports.
- **The lab walk:** `reports/2026-09-24_d2b-lab-walk/README.md` and the raw output in the walk folder beside it.

The reviewers. The model names come from the invocations, the commit messages and the PR comments; the reviewers'
own texts do not name them:

- **Codex:** at xhigh on `ac194fe` and `6b65a4e` (the commit messages). #342's body names two Codex models,
  `gpt-5.6-sol` and `gpt-6-astra`. On `12d9d8d` Codex ran as `gpt-6-astra` at high effort, invoked as the operator
  gave it: `codex --model gpt-6-astra --config model_reasoning_effort="high"`.
- **Grok:** Cursor's Grok; the #343 and #344 comments name it Grok 4.6. On `6b65a4e` it ran in ask mode, so it could
  not apply the blocks or run a suite, and its report says so.
- **OB1-lite:** Opus 5.5 at high effort.
- **OB3:** Opus 5.5 at max effort. It made a deep pass on `da5037e`, wrote §7's blocks at `6b65a4e` (it did not
  review its own blocks), and made a confirmation pass on `890f04c`.

For the first three rounds of #339, the notes record each accepted finding as re-checked in the source before it
was written in. One accepted finding was not measured first: Codex's B11. The orchestrator accepted it, and a later
measurement refuted it (below, and on #210).

## #339 at a glance: the heads reviewed

| Head | Blocks | Reviewer | Verdict, in the reviewer's words | Applied in |
|---|---|---|---|---|
| `ac194fe` | — | Codex | implementable after the named changes | `da5037e` |
| | | Grok | implementable after the named changes | |
| | | OB1-lite | the notes: "implementable after the named changes" (all three) | |
| `da5037e` | — | Grok, confirmation | implementable as specified (R1–R9 FIXED) | — |
| | | OB1-lite, confirmation | implementable after the named changes (N1, N2; the doc corrections N3, N4) | `6b65a4e` |
| | | OB3, deep | implementable after the named changes (F1, F2, D3, M1; F3, F6 and F7 recommended) | `6b65a4e` |
| `6b65a4e` | 154 | Codex | implementable after the named changes | `890f04c` |
| | | Grok (ask mode) | implementable as written | |
| | | OB1-lite | implementable after the named changes | |
| `890f04c` | 200 | Grok, confirmation | mergeable after F1 and F2 | `12d9d8d` |
| | | OB3, confirmation | mergeable after the named changes (stopped after its draft report) | `12d9d8d` |
| `12d9d8d` | 209 | Codex (`gpt-6-astra`) | request changes | `8460257` |
| | | OB1-lite | mergeable after fixes.patch | `8460257` |
| `8460257` | 221 | OB1-lite, confirmation | the orchestrator's summary: the renderer, its test and the counts hold; two wording corrections | `e4140d3` |

That is 14 passes on six heads. #342's body calls them five review rounds. #339 merged at 01:14 on 2026-09-24 as
`8f7d24e`, with 221 blocks in 47 files: 41 edited and 6 created.

## #336 — the design record

Its decisions are in `408d33e`, `cf51bef` and `17787e6`.

**Round 1** (Codex, Grok, OB1-lite):

- **All three, accepted:** §4, Figure 2 and its table presented D4's finding and D5's sentences as current behaviour.
  The table now has a "today" column and a "proposed" column.
- **Codex, accepted:** Figure 2 left out listing the reader's groups on the remote, which fails separately.
- **All three, accepted:** a parser comment said a runtime `remote-sar` cluster "would fail open", but
  `viewer_scope` fails closed. OB1-lite's F2 wording was applied.
- **OB1-lite F3, accepted:** the consequences now require the parser to refuse `remote-sar` without
  `identity: same-as-host`, as values loading already does.
- **Grok C9, accepted:** the `#gh-*-mode-only` fragments are deprecated, confirmed against GitHub's docs.

The operator's direction came in the same round: D2 (`remote-sar` + `same-as-host` is the standard) and D7 (joining
or rejoining with a username and password is a cluster-admin action, checked on the host).

**Round 2** (all three, "mergeable after the named changes"):

- **Accepted:** C1, C3, N1/F2, F3, C5, C6(d), C7, C8 and C10, and Codex N2, OB1-lite F6/Codex N1, OB1-lite F9, Grok
  N2 and Grok N3.
- **Accepted on the fact, snippets rejected:** Codex's seven-row table and its rewrite of the whole of §7. The table
  gained two rows and the text twin two lines instead.

**Grok's confirmation pass on `cf51bef`** confirmed nine of the ten fixes and found one new defect: Figure 2 lacked
the unexpected-exception path that its twin carries. **Accepted on the fact; snippet rejected:** Grok merged the
proposal line into a 150-character line wider than the figure, so a separate footer line was added instead.

## #337 — D3, the mandate and the outcomes figure

Its decisions are in `0b81d98` and `b56e60e`.

- **All three, accepted (C4):** the page's decision cards did not match the table.
- **Codex, accepted:** F3 and F5 (D4's finding is recommended, not built), and C2/F1 (the host is the entry that
  declares `dashboardController: true`, else the first enabled one).
- **Grok, accepted:** F3, the page's heading.
- **Rejected:** OB1-lite's permanent test that parses the page's decision cards. It is a prose test.
- **Routed to D1's code PR** (all three found it): the "clusters share an identity provider" wording, and N2's "the
  first enabled entry". SPEC_D2b took both ("the routed wording", in `ac194fe`'s message), and #342 applied them.
  Measured on main `43befa4`: none of `local-development/gsd/config.py`,
  `charts/group-sync-dashboard/templates/_helpers.tpl`, `charts/group-sync-dashboard/values.yaml`,
  `charts/group-sync-dashboard/example-production.yaml`, `charts/group-sync-dashboard/README.md` or
  `local-development/gsd/static/index.html` contains "share an identity provider". The chart README and
  `charts/group-sync-dashboard/values.yaml` name the host as "`dashboardController: true`, else the first enabled
  one".
- **Confirmation:** OB1-lite found R1–R4 fixed, and its N1 was fixed in `b56e60e`. Grok found #337 mergeable as is.

## #339, round 1 — the spec at `ac194fe`

Each reviewer's verdict per claim:

- **Codex:** C1–C4 REFUTED, C5 CONFIRMED, C6 REFUTED, C7 CONFIRMED (conditional on C3), C8 REFUTED, C9 CONFIRMED, and
  C10 and C11 REFUTED.
- **Grok:** C1 CONFIRMED; C2 CONFIRMED on (b)–(e) and REFUTED on (a); C3 REFUTED; C4 CONFIRMED in part and REFUTED
  on the table; C5 CONFIRMED with leftovers; C6 PLAUSIBLE risk; C7 CONFIRMED except "byte-for-byte"; C8 REFUTED; C9
  CONFIRMED; C10 REFUTED; and C11 "not enough".
- **OB1-lite:** its report was a message. The notes name its findings.

**CI** failed on `ac194fe` (`gh run list`). OB1-lite's N1 named the cause: the specs index counted `D2b` as a
programme row, and the header lacked `Release`.

The decisions, all written in `da5037e`:

- **The hold let every distinct viewer through during a failure** (Codex C3, Grok C3, OB1-lite C3). OB1-lite
  measured 5 attempts for 5 viewers in one hold window. **Accepted:** OB1-lite's probe design. The request after a
  hold expires re-arms it before calling, the hold is set before the failure is reported, and a success clears it.
  The budget sentence now states the first-failure burst. **Rejected:** Codex's cluster-wide attempt lock, which
  would also have serialised every healthy viewer's first review.
- **Grok C6, accepted:** the merge snippet dropped `out.extend(discovered.values())`, and with it every cluster that
  exists only as a Secret.
- **All three, accepted:** the review's error text was redacted after it was truncated, so a JWT's prefix leaked.
  OB1-lite measured the leak.
- **All three, accepted:** `"home" not in app.state.remote_tier_resolvers` breaks on the new object. The test
  changes to `.get`. **Rejected:** a `__contains__` (Codex's and Grok's snippet), because the lazily built map is not
  the set of `remote-sar` clusters (OB1-lite).
- **Accepted:** the policy is read from the same snapshot as the connection (Codex C2c).
- **Accepted:** the `cluster-resolved` line printed an owned Secret's frozen policy, not the served one
  (OB1-lite C6).
- **Accepted:** the parser's import lacked `IDENTITY_NONE` (OB1-lite C5), and the default table now separates
  resolution from acceptance (Codex C4a).
- **All three, accepted:** the missed default and wording sites, the auditor's locally created Group, the full
  behaviour change for a remote that states nothing, and a lab walk that separates the remote's server from the host.
- **Decided between reviewers:** which Secret takes its stanza's policy. Grok and OB1-lite held that any Secret over
  a mode stanza should. Codex held that only the lookup's own Secret should. SPEC_S3 says an unowned Secret over a
  declared cluster wins, and the broader overlay could widen a policy a person wrote. **Codex's rule was taken.**
- **Rejected:** Codex's capture of the Authorization header, to redact a token rotated between a request and its
  error. The same edge exists in `_get` and in every poll, and redaction here matches `_get`.
- **No setting for the hold:** all three advised a constant, like the timeout.
- **The operator decided, 2026-09-23:** `group-sync-operator-helm` installs the auditor objects on every remote
  (§3.7).

### #340 — found in this round

**Found by Codex** (round 1, C2(e)): `_trusted_ca_context()` caches the context by the `GSD_TRUSTED_CA_FILE` string,
not by the file's contents, so a bundle replaced at the same path keeps the old `SSLContext` until the process
restarts. Codex's words: "the process-wide CA cache must notice content rotation".

Grok's C2(e) recorded the same cache as a note, not a miss: "not a field the fingerprint should carry". #340's body
says OB1-lite confirmed it. That report was a message and cannot be checked here.

**Out of scope:** the cache is its own issue, #340, opened at 19:25 and still open. The function is
`local-development/gsd/config.py#_trusted_ca_context`.

## #339 — the confirmation passes and OB3's deep pass on `da5037e`

**Grok's confirmation:** R1–R9 FIXED, and no new defect that meets the bar. It could not run pytest ("the runner
rejected the command").

**OB1-lite's confirmation:** R1 FIXED WITH A NEW DEFECT; R2–R9 FIXED. Its four findings:

- **N1:** four code blocks raised NameError where the prose put them, because they used names their modules did not
  import.
- **N2:** the hold, checked ahead of single-flight, answered the probe's own sibling requests `self`, and a follower
  that steals a stuck leader's slot skipped it. Measured: `calls=['v', 'v']`, a call inside a 30 s hold.
- **N3:** the mock has no `explain` endpoint. The route is `POST /_mock/sar-probe`.
- **N4:** §3.7 said `docs/ACCESS_CONTROL.md` §11 named the auditor objects, and it did not.

**OB3's deep pass**, measured with harnesses on copies. Its verdicts:

- **D1, REFUTED (its F1):** the steal path never read the hold. Its runs b3 and b4 each made one call during a hold.
- **D2, REFUTED at one step (F2):** an ownership flip alone changed the served policy and logged no
  `cluster-resolved` line.
- **D3, REFUTED:** §6 omitted behaviour changes, and its latency sentence understated a cost that is serial across
  remotes (15.06 s for three unreachable ones) and recurs after every hold.
- **M1, REFUTED:** §5 could not be executed as written.
- **M2, CONFIRMED:** the names exist, but the spec omits the import lines.
- **M3, CONFIRMED:** the doc and specs-index tests passed, 1059 passed and 12 skipped.
- **Not asked:** F3 (a lookup stanza set to `enabled: false` stayed served), F6 (the default flip put every remote's
  review inside the read snapshot of `/api/clusters` and `/api/alerts`), and F7 (the tab's create request defaulted
  field by field).

**All were accepted** (F1 through OB1-lite's N2 fix), and OB3 wrote them in as the writer of the blocks (`6b65a4e`).
Two notes on that:

- **Decided: N2's gate over F1's guard.** Both close the steal-path hole. F1's guard kept the hold ahead of
  single-flight, so one page burst read mixed tiers (measured: a probe `all`, its four siblings `self`). N2 gates
  only a request about to call, through one `_may_call` under the lock, used by the leader and by the stealer.
- **The operator's go-ahead put D5 in scope,** relayed by the coordinator. D4 stayed out.

## #339 — the 154 blocks at `6b65a4e`

| Claim | Codex | Grok (ask mode) | OB1-lite |
|---|---|---|---|
| B1 applies and passes | PLAUSIBLE (4900 passed, 16 skipped, 2 sandbox socket errors; Chromium blocked) | PLAUSIBLE (not run) | CONFIRMED (4902 passed, 16 skipped; browser 593 passed) |
| B2 the hold | CONFIRMED | CONFIRMED | CONFIRMED (hold 30 s: 12 calls in 60 s; hold 0: 610) |
| B3 the resolver map | CONFIRMED | CONFIRMED | CONFIRMED, with N3 |
| B4 `served_scopes` (F6) | REFUTED | CONFIRMED (one extra call named) | REFUTED (F1, F2) |
| B5–B7 merge, default, D5 | CONFIRMED | CONFIRMED | CONFIRMED |
| B8 the chart | REFUTED (the hold wording) | CONFIRMED | CONFIRMED |
| B9 docs and upgrade note | REFUTED (the hold wording; the design doc stale) | CONFIRMED | CONFIRMED |
| B10 the tests are real | PLAUSIBLE (red only at collection) | PLAUSIBLE | CONFIRMED (19 mutations, each caught) |
| B11 §5 lab procedure | REFUTED (Step 7's restore) | CONFIRMED | CONFIRMED except Step 4 (F4) |

**Accepted,** and written as 46 correction blocks in `890f04c`:

- **OB1-lite F1:** thirteen per-cluster routes decided a `remote-sar` tier inside their read snapshot (read depth 1
  at every decision). The fix is `@tier_first`.
- **OB1-lite F2 and Codex B4:** `/api/alerts` asked a remote that its walk skips. `alert_scopes` now uses the
  handler's own predicate, in OB1-lite's version.
- **OB1-lite N3:** a retired or disabled cluster's resolver, and the credential in it, was kept. Every lookup now
  drops the resolvers of clusters that cannot be asked.
- **Codex B8/B9:** "asked at most once per 30 s, whatever the traffic" left out the first in-flight burst. This was
  corrected in the chart README, `charts/group-sync-dashboard/values.yaml` and the CHANGELOG, and by the
  orchestrator's sweep in the `local-development/gsd/kube.py` docstring.
- **Codex's three blocks and the orchestrator's sweep:** the design document and its figures still called D1 and D5
  unbuilt. `docs/diagrams/render.py` was added, so the figures are re-rendered from written instructions.
- **OB1-lite F4:** §5 Step 4 read `shared-rnd`'s Secret before the lookup had written it again.
- **Codex B11:** Step 7's restore was changed to keep the live `resourceVersion`. It was reverted two heads later
  (below).

**Rejected:**

- **Codex's retry-the-snapshot loop.** The window is rare, it costs one decision of two bounded calls, and the loop
  would put exception-driven control flow in two handlers.
- **Codex's regression file.** Five of its seven tests match prose or execute the spec's own text. Of its two
  behavioural tests, one is OB1-lite's alerts test again and the other tests the rejected loop.
- **Codex's B10 request for per-test red/green proof.** OB1-lite's 19 mutations answer it per mechanism.

## #339 — confirmation of the corrections at `890f04c`

**Grok:** R1–R4, R6 and R7 FIXED; R5 FIXED WITH A NEW DEFECT. Its two new findings:

- **F1:** Figure 3's page caption still called D5 a proposal.
- **F2:** the design's §8 D1 and D6 still read as unshipped.

Both were **accepted**. `12d9d8d`'s message says its nine blocks close them: "this also closes Grok's two
confirmation findings".

**OB3:** R1 and R2 FIXED; R3, R4 and R6 FIXED WITH A NEW DEFECT; R5 and R7 NOT FIXED. It found F1–F8, among them:

- **F4:** Step 7's restore was never broken. OB3 ran the real `oc` 4.22.13 against a recording API stand-in. The
  original command, with `resourceVersion` stripped, sent a PUT carrying the live `4242`: "replaced", exit 0.
- **F8:** `docs/diagrams/render.py` exited 0 when its web fonts could not load.
- **F6, not asked:** `docs/ACCESS_CONTROL.md` §11 and §3.5 said no request calls a held remote, while one already in
  flight may finish its attempt.

OB3 retracted one of its own measurements, a PNG comparison that read only the alpha band. The orchestrator stopped
the pass after its draft report, because of its token cost (the orchestrator's summary). Its findings were
**applied as written** in `12d9d8d`, which reverts Step 7's restore and records **Codex B11 as refuted**. The notes
and #210 record that B11 had been accepted without a measurement.

`12d9d8d`'s applied copy: 209 blocks, non-browser suite 4922 passed, 20 skipped, 0 failed (the commit message).

## #339 — `12d9d8d`: Codex on `gpt-6-astra`, and OB1-lite

Both briefs carried the operator's rule: *"remember codex review must give us full code solution to any findings in
file"*. Each reviewer wrote its fixes as spec blocks to a file, with a test for any code change.

**Codex's verdicts:**

- C1 PLAUSIBLE: 4923 passed, 20 skipped and 2 sandbox socket errors (the browser suite excluded, as briefed).
- C2 CONFIRMED.
- **C3 REFUTED:** a request that begins during a hold can steal after its wait crosses expiry. Measured: hold until
  t=1030, follower begun at t=1029, wait advanced to t=1031.
- C4 CONFIRMED: 19 routes at read depth 0; the documented window costs two calls at depth 1.
- C5 CONFIRMED: from Kubernetes cli-runtime's `Helper.Replace`, an overwrite with no `resourceVersion` reads the
  live one.
- **C6 REFUTED:** the 375 px page had no failure listeners.
- **C7 REFUTED:** six stale passages in the design document and its page.
- C8 CONFIRMED: 21 of 21 quotes match.

Its verdict: "request changes".

**OB1-lite's verdicts:**

- C1 CONFIRMED.
- C2 CONFIRMED, except the retention sentence (its **F2**).
- **C3 REFUTED (its F1):** a follower begun at t=1010 called at t=1032.
- C4 and C5 CONFIRMED. On C5 it read the same `Helper.Replace` source.
- C6 CONFIRMED for the nine blocks, REFUTED for the present-tense sweep (its **F3**).
- C7 and C8 CONFIRMED.

Its verdict: "mergeable after fixes.patch". The orchestrator saved its report, because the harness refused the
agent's own write of the report file.

**Accepted,** in `8460257`:

- **OB1-lite F1, the fact measured by both reviewers:** the hold sentence in §3.5 and `docs/ACCESS_CONTROL.md` §11
  now says that a request that arrived during the hold and outwaited a stuck resolution may be the one probe after
  the hold expires, and that no attempt starts while the hold runs.
- **OB1-lite F2:** a cluster still askable whose credential changed keeps its old resolver until that cluster is next
  looked up. Measured: `east` kept `token-one` across a lookup of `west`.
- **OB1-lite F3:** `shared-qa` "has always been `self-only`" was false after D2b.
- **Codex C6:** `docs/diagrams/render.py` now watches every page. Its test is its own file,
  `local-development/tests/test_diagram_render.py`, where 3 of 9 cases fail on the old renderer.
- **Codex C7, accepted on the facts; its option-column rewrites rejected:** the design document's status line, D2's
  "(today)", D6's "until D1 ships" and "right now", and the page's D5 card. Each was corrected in the fewest words,
  and the options column stays the record of what was proposed.

**Rejected:**

- **Codex's C3 code change, a `began_held` flag** so that a request that arrived held never probes. The budget the
  hold exists for is at most one call per hold per resolver, whatever the traffic, and it holds without the flag.
  Codex's own measurement: 11 calls in 60 s, one probe at 35.5 s. The flag would add state to make an over-stated
  sentence true, so the sentence was corrected instead.
- **Codex's five documentation contract tests.** They assert phrases in the documents, which makes them prose tests.
- **Codex's placement of the renderer test** in `local-development/tests/test_remote_sar_default.py`. It tests the
  renderer, so it has its own file.

`8460257`'s applied copy: 221 blocks in 47 files; non-browser suite 4934 passed, 20 skipped, 0 failed;
`docs/diagrams/render.py` on the real page gave exit 0, 8 PNGs and scrollWidth 375 (the commit message).

### OB1-lite's confirmation of `8460257`

This report was a message; the orchestrator's summary follows. The renderer, its test and the counts hold. OB1-lite
ran a held arrival under 50 viewers' traffic, and it kept one call per 30 s hold, the held arrival being that hold's
probe. That confirms the `began_held` rejection. It also measured that the renderer's one shared failure list fails a
theme-page request that dies after the load check, which the per-page list had dropped: a lazily loaded image gave
exit 0 before and exit 1 after (the notes). It made two wording corrections: the D5 line quoted on the page and in
the design document is a `remote-sar` cluster's, and each reviewer's hold timings are its own.

Both corrections were **accepted** in `e4140d3`. The doc, spec and renderer tests on the applied copy gave 1430
passed and 12 skipped. #339 merged as `8f7d24e`, with CI 8/8 on its last head (`gh pr checks 339`).

## #342 — the implementation

`fd9bfb9` is `local-development/apply-spec-blocks.py` run on main `8f7d24e`: "221 blocks check out across 47 files".
No line was written outside the blocks except the re-rendered figure PNGs.

**OB1-lite on `fd9bfb9`** (a message; the orchestrator's summary): **mergeable as is, no findings.**

- K1: the PR tree equals main `8f7d24e` plus the spec's 221 applied blocks, apart from the six re-rendered PNGs
  (a whole-tree diff).
- K2: the renderer and the figures.
- K3: `helm lint` and `helm template` of the chart, with the walk's values files.
- K4: the app reports 0.32.0, and its full suite gave 5527 passed in a git copy.
- K5: nothing that `local-development/release-crc.sh` would trip on.

CI on each of #342's three heads: 9 passed and `container-smoke` skipped (`gh api …/check-runs`). #338's evidence
comment calls this "CI 10/10". #342 merged as `46b71be`.

## #343 — the Helm handover (found by the lab walk, Step 3)

**Found by the walk:** `local-development/release-crc.sh`'s Helm mode was refused once the chart version moved. The
kept PVCs' `helm.sh/chart` and `app.kubernetes.io/version` labels were owned by `argocd-controller`, and Helm 4
applies server-side. **The fix:** `--force-conflicts` on the Helm-mode install. Its test fails on main's script (1
failed, 20 passed) and passes on the fix (21 passed).

The operator: *"pvc should not be removed"*. The PR's comment at 01:44 answered with a baseline of both PVCs' UIDs,
and showed that `--force-conflicts` transfers field ownership and deletes nothing.

**Grok 4.6's verdicts:**

- C1, C3 and C4: CONFIRMED.
- **C2: PLAUSIBLE (risk).** Forcing on every Helm-mode run would strip `mock-creds`, because Pod `volumes` are
  atomic lists under server-side apply. It proposed forcing only when the run deleted the Application.
- **C5: PLAUSIBLE (risk).** The Helm-to-Argo hand-back would meet the inverse conflict. It proposed `Force=true` in
  the kept PVCs' sync-options.

The decision comment heads C2 and C5 "REFUTED"; those are the orchestrator's decisions, not Grok's words.

- **C2, rejected, measured.** This cluster's OpenAPI lists `PodSpec.volumes` and `Container.volumeMounts` as keyed
  map lists, not atomic lists. The proposed gate would also break the recovery path the PR exists for: a rerun after
  a failed hand-over finds no Application, while `argocd-controller` still owns the labels. The walk then measured
  it. After Step 9's forced Helm apply, the Deployment's volumes still list `mock-creds`
  (`reports/2026-09-24_d2b-lab-walk/walk/step9.out`).
- **C5, rejected, from source.** Argo CD forces conflicts whenever it applies server-side (`gitops-engine`'s
  resource_ops.go). The proposed test grepped templates, which makes it a prose test. The walk's Step 10 then handed
  back with no conflict.

After the merge, Step 3's rerun left both PVCs identical to the baseline. #343 merged as `5b7d346` with CI 8/8.

## #344 — the spec's lab steps (found by the lab walk)

Three corrections to §5, each **found by the walk**:

- Step 6's page check could pass on the previous cluster's text.
- `shared-qa`'s token is expired on purpose, so Steps 6 and 10 expect `self` there.
- Step 7's in-cluster URL row asked for a URL the parser refuses by design.

A new Step 11 rejoins `shared-qa` with a long-lived token. The corrected Step 6 and the new Step 11 were run on the
lab and posted on the PR: 16/16 page checks, then 4/4 after the rejoin.

**Grok 4.6's verdicts:**

- C1 CONFIRMED.
- C2 PLAUSIBLE: the hold was not yet on main. The lab run measured it.
- **C3 REFUTED, accepted on the fact:** Step 7's sentence could read as the parser enforcing the operator's rule.
  Grok's replacement paragraph was not used. The orchestrator's wording keeps the rule as the operator's and states
  the guard's scope: it refuses only a `server` of exactly `https://kubernetes.default.svc`, or the host's `name`.
- C4 PLAUSIBLE: the token's missing `exp` needed the cluster. It was measured on the lab: `exp NONE (no expiry)`.
- **C5 REFUTED, accepted:** §5's opening Definition of Done said kubeadmin is wide on both remotes. It now says so
  only once Step 11 rejoins `shared-qa`.

Applied in `6769fa3`. Docs, specs index and apply-tool tests: 1077 passed, 12 skipped. #344 merged as `5c22370`.

## #345 — the walk's evidence and the README recaptured

**OB1-lite on `d82b898`** opened every README image and read the raw output in the walk folder. Its findings:

- **K1, REFUTED, accepted with its replacement text:** three README captions were wrong.
  - The RBAC tab's unmanaged grant is the chart's own auditor binding, not a hand-made one.
  - Access granted's split summed to 201 of 202.
  - The Overview caption named 9 of the 12 alerts.
- **K2, REFUTED, accepted:** four walk rows quoted pod-log lines that were not saved in the walk folder. Steps 3, 7
  and 8 now say what was and was not saved. Step 11 cites the pod's log for the window and the corrected scope read.
- **K3 and K4 CONFIRMED:** no secret in any committed file, and every referenced path exists.
- **Not asked, accepted:** the Files line now says where the scripts read passwords.
- **Not asked, filed:** two app defects, #346 (the Logins caveat under the audit-log source) and #347 (the Access
  granted tiles leave out unmanaged grants), and one question for the operator, #348 (the chart's own auditor
  binding is flagged as an unmanaged grant).

The accepted findings were applied in `70e4273`. #345 merged as `43befa4`. #338 closed at 08:52 with the evidence
comment.

## What the lab walk found on its own

These are findings of the walk, not of any reviewer:

- **The Helm handover** (Step 3) → #343.
- **Step 6's stale page check,** and **Step 7's in-cluster row** → #344.
- **The host guard refuses only the exact string** `https://kubernetes.default.svc` (Step 7, continued). Other
  spellings of the in-cluster endpoint pass it. This is open for the operator (the spec's notes and the walk record);
  a search of the issues finds none filed for it. The guard is
  `local-development/gsd/clusterconfig/parser.py#IN_CLUSTER_SERVER`.
- **Not measured:** the alert in Step 8, and Step 9's check that the mock is not asked. The operator stopped Step 9
  before it ran. It could not have been trusted anyway, because a local `podman` container held the port its
  port-forward uses.

## Retracted by their authors

- **OB3, writing the blocks:** `oc auth can-i` first said jane.smith "no" on CRC. zsh had passed her 18 groups as one
  argument; with the groups split, the answer is "yes".
- **OB3, on `890f04c`:** its first PNG comparison, which read only the alpha band.
- **OB1-lite, on `6b65a4e`:** a run that showed "2 failed" while its mutation runs competed for CPU. Re-run on a
  quiet machine: 4921 passed, 0 failed.

## Carried, not acted on

- **The specs index still lists D2b as `specified`,** with "app and chart minor bumps at the PR" (OB1-lite's note on
  `6b65a4e`; measured on main). The status is the operator's to state.
- **`docs/CLUSTER_STANZA.md` still says "Fourteen refusals fail `helm template`".** Grok (on `6b65a4e`) called the
  count stale before D2b. It is pre-existing, and no test pins it.
- **The tier-check metric has no cluster label** (Grok, round 1). SPEC_D2b §1 puts it out of scope.
- **#348 names the same binding as #312.** Found while writing this record: #312, opened on 2026-09-23 at 01:46 UTC,
  before this session, and still open, reports `group-sync-dashboard-ra-b78c05817c9d`. It argues for the
  `rbac.ocp.io/config-source` label over the `rbac.ocp.io/unmanaged-exception` annotation, which is #348's option 1.
- **A Fable re-review of OB3's two passes on #339 is owed** (#210). #210's row names this file as the record.

## The orchestrator's own errors

- **Codex's B11 was accepted without a measurement** and written into `890f04c`. OB3's measurement refuted it, and
  `12d9d8d` reverted it (#210's row: "which I had accepted unmeasured").
- **The spec's first head failed CI:** the specs index counted `D2b` as a programme row, and the header lacked
  `Release`.
- **A substitute in-cluster URL was tried in Step 7:** `https://kubernetes.default.svc.cluster.local`, which read
  `all` at cycle 20. The operator corrected it: *"`https://kubernetes.default.svc.cluster.local` - this is only
  connecting internally using the mounted ca into the pod for dashboard controller only."* The row is struck through
  and marked **RETRACTED** in the walk record.
- **A durable-token deviation for `shared-qa` was withdrawn** (the orchestrator's summary). The operator: *"This was
  an intentional set to expires because we didnt use the long term token just to dematrate"*. Step 7's restore put
  the expired token back, as the spec writes it. Then, at the operator's direction, *"fix shared-qa with a long term
  token that does not expires and then rejoin it. Show this as well"*, and Step 11 rejoined it.
- **Token cost.** The operator on OB3: *"the ob3 is wasting my token - we have a skill here that monitor a back
  ground and wake up. no polling is needed"*. And on the walk's Step 9: *"I just killed a process now. You wasted my
  token on that for over 230mins"*.
- **Walk scripts:**
  - Step 11's scope read failed on a quoting error (`SyntaxError`). The corrected read is
    `reports/2026-09-24_d2b-lab-walk/walk/scopes-now.sh`.
  - Step 8's `sed` extract printed `the` for `d2b-no-sar`. The metric (`forbidden` 0 → 8) shows all eight failures
    were `forbidden`.
- **The walk README** carried three wrong captions and four rows quoting unsaved log lines. The #345 review caught
  them.
- **Two statements that say more than their source, found while writing this record:**
  - #343's decision comment heads Grok's C2 and C5 "REFUTED", where Grok wrote PLAUSIBLE (risk).
  - #338's evidence comment calls #342's CI "10/10", where each head shows 9 passed and one skipped.

## Outcome

- **Seven PRs merged:** #336 `b21f80b`, #337 `7c0a42c`, #339 `8f7d24e`, #343 `5b7d346`, #344 `5c22370`, #342
  `46b71be` and #345 `43befa4`.
- **Review passes:** 7 on #336 and 5 on #337 (their commit messages), 14 on #339, and one each on #342, #343, #344
  and #345.
- **Rejected with a reason, or with the measurement that refuted it:** 20 proposals.
  - #336: 3 (Codex's seven-row table, Codex's §7 rewrite, Grok's 150-character line).
  - #337: 1 (OB1-lite's decision-card test).
  - #339: 13 (Codex's attempt lock, the Authorization capture, `__contains__`, the broader overlay, OB3's F1 guard,
    the retry loop, Codex's regression file, the B10 request, B11, `began_held`, the five contract tests, the
    renderer test's placement, and Codex's option-column rewrites).
  - #343: 2 (the conflict gate, `Force=true`).
  - #344: 1 (Grok's Step 7 paragraph).
- **App defects found by review and filed:** #346 and #347. For the operator: #312 (#348 closed as its duplicate) and the host-guard finding.
- **Deployed and walked:** `release-crc.sh --argocd`, Synced/Healthy at `8e50ff8eec`, verified in-pod. §5 Steps 0–11
  pass, with the notes above. The e2e walk after the rejoin: 84/84 steps, 24/24 extra, 11/11 PDFs rendered, and
  11/11 reports passing integrity. The kept PVCs' UIDs were unchanged through every Helm round and the hand-back.
