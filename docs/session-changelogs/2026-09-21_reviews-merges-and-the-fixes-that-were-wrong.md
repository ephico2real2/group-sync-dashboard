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

## Numbers

| | |
|---|---|
| Pull requests merged | **10** (#251, #252, #254, #256, #258, #259, #260, #262, #265, #266) |
| Commits authored | 21 non-merge |
| Review passes run | 9 — OB2 ×4, OB3 ×2, Cursor ×3, Codex ×3 (one died: "model at capacity") |
| Reviewer findings accepted | the large majority; **2 refuted with evidence** (Codex C5 on #259, a Codex framing on 200% zoom) |
| **Fixes that were themselves wrong** | **6** — and every one was caught by a different reviewer than the one whose finding it answered |
| Tests that passed because they did not look | **3** — the tab-bar guard (passed with the old padding), the type guard (never asserted weight or tracking), the headroom canary (`spare` is 0 by construction) |
| Full suite, final | 4461 passed, 15 skipped (hermetic); test_ui 541 |
| Longest single loss | ~2 h across three venv rebuilds before the tracked symlink was diagnosed — the evidence was one `git ls-files -s` away each time |

## Where things are recorded

- `docs/specs/SPEC_S3_connection_modes.md` — eleven sections, three passes
- `docs/design/nsaudit-mock.html` + `nsaudit-feature-capture.md` + the `### Namespace audit` section
  of `docs/design/tab-feature-contract.md` — the page the contract had never captured
- `reports/2026-09-21_tabbar-headings-253/` and `reports/2026-09-21_deployed-walk/` — walks with
  assertions
- Issues opened: #255 (classification as configuration), #257, #261 (the mock's remaining tranche),
  #267 (the cluster in report forms)

## State left behind

- **Deployed:** `main @ 19ffb25b4a` through `release-crc.sh --argocd`, Argo Synced/Healthy, commit
  verified in-pod. The walk of that head is `reports/2026-09-21_deployed-walk/`.
- **#264 open** at `53e5f20`: Cursor's four findings fixed by OB2; **C2 is a live defect on it** —
  with only the section's box missing, the card says "0 of 39 match the search" above "No namespaces
  recorded for this cluster yet". OB2 is fixing it, and has been asked whether the ladder's *shape*
  is the defect, since that sentence has now been wrong three times.
- **#267 with Fable**: the operator's ruling settles it — *reports gather from a target cluster*, so
  several clusters means one run per cluster, not one run spanning them.
- The remaining #261 tranche is unbuilt, and the walk surfaced its first item on the live page:
  `openshift-console-user-settings` is ranked in the worklist and hidden from the index at once, with
  nothing reconciling the two.
