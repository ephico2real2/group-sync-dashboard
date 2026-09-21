# Session change log — group-sync-dashboard, 2026-09-21

What this session did, when, and how each claim was measured. Times are git author times in
America/Chicago. Every "measured" claim below is one the session ran a command for; nothing here is
recalled from memory alone. The product changelog (`docs/CHANGELOG.md`) says what each release
changed for an operator; this says what a working session did.

Outcome in one line: **ten pull requests merged and deployed through Argo — the controller declared, platform namespaces hidden and made configurable, the tab bar fixed, SPEC S3 corrected by three adversarial passes, S3a built — and, running through all of it, six occasions on which a fix written for a reviewer's finding was itself wrong.**

| | Before the session | After |
|---|---|---|
| main | `bfdb718` (#223 merged) | `93662c2` — ten PRs merged today |
| chart | 0.44.1 | **0.47.0** (0.45.0 controller, 0.46.0 platformNamespaces, 0.47.0 S3a) |
| deployed | `0.30.0-a90f1b277b`, a lab branch 16 commits behind main | `0.30.0-19ffb25b4a`, main, verified in-pod |
| CI | the Kyverno switch test failing on main, gating every merge | green; the test fixed, not re-run |
| open PRs | #251, #252, #223 | #264 (index controls, in review), #263 (Dependabot) |

---

## Part 1 — the controller cluster, and three defects the review found (#249 → #251)

### `dashboardController` (00:0x → 03:1x) — commits `7044d1d`, PR #251

`clusters[].dashboardController: true` names this pod's own cluster instead of it being whichever
entry sorted first. OB2's pass **REFUTED** the PR's central claim: `host_cluster()` was correct, but
it was not the only place the host was decided.

- **`gsd/api.py`** — all four `TierResolver`s reviewed against `next(enabled)`, so with the
  controller declared second **the wide tier was decided by a SubjectAccessReview on a remote
  cluster**, whose answer means nothing locally.
- **`gsd/config.py`** — the host-only visibility refusals ran positionally: `hidden` was
  ACCEPTED on the declared controller (the login cluster the rule protects) and REFUSED on a remote.
- **`templates/_helpers.tpl`** — the render-time guard knew nothing of the flag. Two controllers, a
  disabled one and a quoted `"yes"` all **rendered**, then CrashLooped the pod after a green
  `helm upgrade`.

**Found by OB2.** All three **accepted** and fixed. New tests: **15 failed / 3 passed** on the old
head, **18 passed** after. Full suite **4370 passed, 15 skipped**.

**One finding was mine**: `Chart.yaml` claimed "the page says the fallback was used" while
`controller_is_declared` had **no consumer anywhere**. Shipped a startup line rather than reworded
the claim.

---

## Part 2 — the `.venv` symlink, twice (#254, #265)

`local-development/.venv` was tracked as a **symlink whose target is its own path**. In a worktree it
resolves outward and works; in the canonical checkout it eats itself. Measured: `ls .venv/` →
`Too many levels of symbolic links`.

It destroyed the virtualenv **three times** before it was diagnosed — on a `git merge origin/main`, on
a `git checkout` of another branch, and again on a branch switch. Each time the evidence was one
`git ls-files -s` away and I rebuilt instead of looking.

**How it got in:** `.gitignore` carried only `.venv/` — with a trailing slash, which matches a
*directory* and not a symlink of the same name — so `git add -A` staged it silently.

**And the fix made something worse.** #254 needed two lines; I ran `sort -u` over `.gitignore` and
rewrote 104. In gitignore the **last** matching pattern wins, so sorting put every `!` re-include
*above* the pattern it carves out of. Measured on main:

```
.claude/settings.json              → .gitignore:11:.claude/*   IGNORED
.claude/skills/changelog/SKILL.md  → .gitignore:11:.claude/*   IGNORED
local-development/.env.example     → .gitignore:15:.env.*      IGNORED
```

**Found by OB2's audit of the fixes** (A8c) — the answer to the question that audit exists for.
Restored from the parent with only the two lines needed (#265).

---

## Part 3 — the CI blocker was never a flake (#246 → #262)

`TestKyvernoPage::test_the_switch_keeps_focus_and_a_kyverno_only_change_repaints_on_the_poll` failed
on four runs and was re-run twice as "the known flake". It was failing **on main**, gating every
merge.

It was a real defect in the test. It pressed the switch, then waited for `Findings · 2` — **the count
before the toggle**. The pre-toggle text was still on screen, so the wait was satisfied instantly by
the **stale paint** and the test never observed the repaint it exists to prove; the `aria-checked`
assertion then passed because the control sets it optimistically.

**Diagnosed from CI's own failure screenshot**, not a fifth re-run: switch on, `Findings · 3`, the Pod
row present. Reproduced locally by inserting a 1.5 s pause, which makes the old assertion fail every
time. It asserts the 2 → 3 transition now, pinned from both ends, and the same pause leaves it
passing.

---

## Part 4 — the Namespace audit index (#257 → #258, #255 → #259, #261 → #264)

### Platform namespaces hidden (#258)

`gsd/home.py` has shipped `is_platform_namespace()` all along and it had **exactly one caller**, the
Home page. Measured on the reference cluster: **67 of 106 namespaces are platform — 63%** — under a
five-row worklist.

Hidden by default with the count stated and a control to restore them; the rows stay in the payload,
so export, search and the drill still reach a hidden namespace.

**Codex C8 REFUTED my empty state**: an all-platform cluster rendered "1 platform namespace hidden"
**and** "No namespaces recorded for this cluster yet" together. Fixed by branching on cause.

**Cursor then REFUTED that fix**: at the self tier the payload is self-scoped, so "every namespace on
this cluster" and "nothing is missing from the cluster" are claims it cannot support — prefixing them
with "That is your view:" does not cancel them. And with every row hidden, the *search* branch won the
ladder and said "All 0 are still there".

### Configurable classification (#259)

The shipped rule under-classifies a real estate: it calls `cert-manager`, `cert-manager-operator`,
`group-sync-operator`, `group-sync-dashboard`, `hostpath-provisioner`, `kyverno` and
`namespace-configuration-operator` **application namespaces** — seven, on a lab with few operators.

Three axes, each load-bearing and measured: `-operator` catches three, `-manager` one,
`-provisioner` one, and two match no pattern at all. A test pins that **no two axes suffice**.

**Codex found two defects.** The chart rendered `additionalSufixes: ["-op"]` and `prefixes: [1]`
straight into the ConfigMap for the loader to refuse at startup — a green upgrade and a CrashLooping
pod. And **my own validation was dead code**: the padded/empty check ran after `_string_list_setting`
had already stripped and dropped empties, so it could never fire.

**One Codex finding I refuted**: C5 reported `platform_patterns_unmatched` as existing only in tests.
It is in `gsd/api.py` and `gsd/static/index.html` — its export predated that commit.

---

## Part 5 — SPEC S3, three adversarial passes (#248 → #252)

The spec grew from one section to eleven under review, and **most of §8 and §9 was refuted**.

- **OB3** refuted the §6 TLS diagnosis: the number (`verify=19`) reproduced exactly, but the cause
  was inverted. The ServiceAccount's `ca.crt` is a **bundle** carrying the ingress CA, which is why
  it validates the login endpoint; what fails is the dashboard's own injected store, on the external
  API URL too. The spec had made the **failing** mode the default. Retracted publicly on #248 and
  #119, where the wrong causal claim had been posted.
- **Cursor and Codex** refuted the ownership model: `writer.py` already defines the annotation key
  with value `ui`, and `parse_secret` **never reads annotations**, so the marker could not survive
  parsing. The annotation is also forgeable by anyone who can create a Secret in the namespace.
- **OB2's third pass audited the fixes** and refuted mine: the delete row named
  `retire_absent_clusters`, which runs **once at pod start**; and "the existing vanish path retires
  the row" is false for the case that matters — `_discover_once` skips a vanished name a values entry
  still declares, so the cluster keeps polling. Measured on the Poller, not argued.
- It also refuted two claims in the sections the operator contributed: the CRC attribution rested on
  a creation timestamp that proves nothing (the value arrived by `oc apply` afterwards), and "the lab
  cannot test expiry" **contradicted itself two sentences later** — TokenRequest's floor is 600 s.

Nine doc fixes applied one at a time, guards at **1295 passed** after every one.

---

## Part 6 — S3a, built from the corrected spec (#260)

A stanza may declare `saTokenLookup: true` or `userSelfLogin: true` and carry no credential. Driven
against the spec's own cases before landing: the §1 stanza accepted with `credential_kind=lookup`;
both modes, a quoted `"yes"`, a mode beside a credential and a mode on the declared controller all
refused, each naming the cluster and the key.

The part worth reading: the poller **generalises the gate `oauth` already had** rather than adding a
second. A cluster awaiting its credential is listed and not polled, because recording `auth_failed`
for a credential never presented sends an operator to rotate a token that does not exist.

Suite **4419 passed, 15 skipped** (+31).

---

## Part 7 — the cluster in the report forms (#267 → #269)

### The form names its cluster, and runs on several (14:0x → 14:4x) — commits `97462a1`, `76e7332`, PR #269

The operator's ruling settled the design before it was built: *reports gather from a target cluster*,
so several clusters is **one run per cluster** — shape A of #267's two — and `cluster` stays a single
string on the sealed model. The branch was built by a Fable seat; this session merged `main` into it
(both sides had appended independent test classes to `tests/test_ui.py`; both were kept) and reviewed it.

- **OB1-lite** (Fable 5.1, default effort) took an eight-claim brief and confirmed all eight, working
  from read-only clones — `tree` = head, `base` = the merge-base, `revert` = head with one file group
  reverted. The claim worth the pass was C1, the seal: base-vs-head and head-vs-head canonical
  documents differ on **the same two lines**, so a single-cluster report's shape and data are
  untouched by the PR.
- **Three volunteered defects, all page-side, all fixed.** **V1**: the cluster-change note was garbled
  whenever the previous position was the fleet — the Overview leaves the cluster null (#172), so the
  change records `to: null` and `esc(note.to)` rendered *"changed from crc-local to — … the lookups
  now offered are 's."* **V2**: any error after the POST was worded "the request was refused",
  although the service answered 202 and the runs reach the Library. **V3**: dismiss nulled the note
  for every form although it renders per form, so a second form's cleared lookup was never said.
- **Two of the three fixes needed tracing before they could be trusted**, which is the session's
  standing lesson applied rather than recited. V3's fix keys its delete on `view.report`;
  `generateReport` has a `|| cat.reports.find(r => r.enabled)` fallback that would have broken that
  key, but the *render* path has none, so the form card only ever exists for `view.report` — sound
  once checked. V1's fix quotes `view.cluster` rather than `note.to`, which is only behaviour-preserving
  because the field drop runs **before** `view.cluster` moves, making the two identical on every path
  but the fleet.
- **Found by OB1, a fourth test that did not look.** Two asserts in the list-shape test were bare
  `== 422`. Measured against a reverted `server.py`: the base answers the *string* detail
  `"a viewer run names its cluster"`, so those asserts could not tell "refused because the list is
  empty" from "refused because `clusters` is unknown". Both now name the `loc` and the pydantic error
  type, and were verified not to hold on base.
- **Proof, not inspection:** with `index.html` reverted, exactly the three new browser tests fail and
  the three existing ones pass. Reporting **101**, hermetic **4466 passed / 15 skipped**, browser **552**.

### Walked on five clusters (14:4x) — commit `76e7332`

Deployed through `release-crc.sh --argocd` (Argo Synced/Healthy, image `0.30.0-97462a1824`, commit
verified in-pod). The lab had been on `0.30.0-977365e25f` — main at the merge-base — so nothing of
#267 had ever run there. The estate is five configured clusters, which is what the hermetic
two-cluster fixture cannot be: five runs, five **distinct** seals, five download pairs, under one
count, with the totals line stating in words that it is the primary's.

- **Stated rather than papered over:** the walk was written expecting `shared-rnd` — the
  credential-less cluster of SPEC_S3 — to fail its own run and exercise partial failure on real data.
  It has a snapshot on this lab and sealed like the rest, so that DoD item remains covered **only** by
  the API test and the browser test's injected `ghost`. The walk's own comment was corrected and the
  weak `>= 2` assertion tightened to the measured `== 5`, then re-run to re-prove it.
- **Found by the walk, and it is not this PR: #270.** Two walks of the same head with the same
  parameters produced a different sha256 for **every** cluster. `canonical()` includes `sections`, and
  the provenance page puts run facts there — `Generated at (UTC)`, `Run id`, and the snapshot-age
  phrasing whose `age_seconds(now)` is computed from the run's own clock. `model.py` says the hash is
  over "the DATA … never over the timestamp, so the same data on two days hashes the same"; it is not.
  OB1 found the first two independently under a frozen clock; the **third** only appears with a real
  one, which is why the walk saw it and the probe could not.

---

## Numbers

| | |
|---|---|
| Pull requests merged | **10** (#251, #252, #254, #256, #258, #259, #260, #262, #265, #266); #264 and #269 reviewed and validated |
| Commits authored | 23 non-merge |
| Review passes run | 10 — OB1-lite ×1, OB2 ×4, OB3 ×2, Cursor ×3, Codex ×3 (one died: "model at capacity") |
| Reviewer findings accepted | the large majority; **2 refuted with evidence** (Codex C5 on #259, a Codex framing on 200% zoom) |
| **Fixes that were themselves wrong** | **6** — and every one was caught by a different reviewer than the one whose finding it answered |
| Tests that passed because they did not look | **4** — the tab-bar guard (passed with the old padding), the type guard (never asserted weight or tracking), the headroom canary (`spare` is 0 by construction), and two bare `== 422` asserts that also hold on the base server |
| Full suite, final | 4466 passed, 15 skipped (hermetic); test_ui 552; reporting 101 |
| Longest single loss | ~2 h across three venv rebuilds before the tracked symlink was diagnosed — the evidence was one `git ls-files -s` away each time |

## Where things are recorded

- `docs/specs/SPEC_S3_connection_modes.md` — eleven sections, three passes
- `docs/design/nsaudit-mock.html` + `nsaudit-feature-capture.md` + the `### Namespace audit` section
  of `docs/design/tab-feature-contract.md` — the page the contract had never captured
- `reports/2026-09-21_tabbar-headings-253/` and `reports/2026-09-21_deployed-walk/` — walks with
  assertions
- Issues opened: #255 (classification as configuration), #257, #261 (the mock's remaining tranche),
  #267 (the cluster in report forms), **#270** (the sha256 does not certify the data)
- `docs/REVIEW_report_form_clusters.md` — the #269 review record, eight claims and three volunteered
  defects
- `reports/2026-09-21_report-form-clusters/` — the five-cluster walk, with what it does **not** prove

## State left behind

- **Deployed:** `feat/267-cluster-in-report-forms @ 97462a1824` through `release-crc.sh --argocd`,
  Argo Synced/Healthy, commit verified in-pod. Before it the lab held main at the merge-base. The
  walk of that head is `reports/2026-09-21_report-form-clusters/`.
- **#264 merged** — OB2 fixed Cursor's four findings and then C2, restructuring the empty-state
  ladder around *which pipeline stage emptied* (`all` → `inScope` → `shown`) rather than patching the
  instance, after being asked whether the sentence's shape was the defect. It was: proving the fix
  turned up a fourth unreported instance.
- **#269 reviewed, validated and walked**, awaiting CI on `76e7332`. The one DoD item its walk could
  not close is partial failure on a *configured* cluster — see Part 7.
- **#270 open**: the report sha256 covers run facts, so two runs over one snapshot never agree. Needs
  a decision (exclude the provenance section, or split it) because the fix changes every existing
  artefact's hash once.
- The remaining #261 tranche is unbuilt, and the walk surfaced its first item on the live page:
  `openshift-console-user-settings` is ranked in the worklist and hidden from the index at once, with
  nothing reconciling the two.
- **#255's expected-grants half** is unbuilt: suppressing known-good direct grants, and
  `existingConfigMap` for maintaining the list outside the chart.
- **S3b/S3c/S3d** remain; S3d is explicitly unsafe until its prerequisites land.
