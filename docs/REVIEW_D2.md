# Review — PR #93, D2: per-cluster authorization for the multi-cluster case

Adversarial second-opinion pass, 2026-09-13, on the twelve-claim brief for #93
(`docs/specs/SPEC_D2_per_cluster_authorization.md` applied as amended by its orchestrator's notes,
deviations 1–8; application 0.19.0, chart 0.21.0). Codex (gpt-5.6-sol, xhigh) and Cursor (Grok 4.6 high
fast, ask mode) review the head after the first CRC deploy; every verdict is re-checked here before a
decision, and every accepted finding comes with a test that failed before its change.

## Live run on the reference cluster

Head 05cbf3f (the spec applied, the release bump), deployed by `release-crc.sh` with `environments/crc.yaml`
unchanged — one cluster — then upgraded three times with a second entry, `prod-east`, pointing at the same API
with the pod's own token (Helm never merges lists, so the whole list travels, the chart's default entry first):

| Measured | Value |
|---|---|
| startup | `INFO gsd.api prod-east: per-cluster visibility policy self-only, identity none` — once |
| `/api/whoami`, kubeadmin | `scope: all`; `clusters: {crc-local: {inherit, same-as-host, all}, prod-east: {self-only, none, self}}` — §D2.8's expected shape byte for byte |
| `/api/clusters` rows | `crc-local {inherit, all}`, `prod-east {self-only, self}` |
| person-scoped views on prod-east | `groups` → 403 with the §11 sentence; `bindings/findings` → 403; `groupsyncs` → 200; the host's `groups` → 200 |
| `/api/alerts` | `scope: self` — the narrowest served; administrator-tier kinds from `crc-local` only |
| prod-east `hidden` | `{"detail":"unknown cluster 'prod-east'"}` and `{"detail":"unknown cluster 'no-such'"}` — the same 404; absent from `/api/clusters`, `/api/whoami` and `/api/alerts`; still 37 series on `/metrics` |
| `remote-sar` without `same-as-host` | refused at render: `needs identity: same-as-host` |
| **found by the check** | with `--set clusters[1].…` on a values file that does not define the list, Helm pads index 0 with `null` and `gsd.validateClusters` died on a Go nil pointer (`nil pointer evaluating interface {}.name`); fixed in daa39a9 — the guard refuses a non-map entry by index and names the remedy; a chart test pins the padded case (deviation 8) |
| restoring one cluster | the first attempt failed on the chart's post-upgrade `auth-loglevel` hook exceeding `activeDeadlineSeconds`; re-measured with the hook pod watched: `Pending / Unschedulable` for 70 s on the node at 95 % CPU requests, then scheduled, ran 10 s ("already Normal — nothing to do"), upgrade complete. A lab-capacity condition, the same class as the C3 run's `Insufficient cpu`, not a code path |
| after | release `deployed`, both pods `Running`, `/api/whoami` names `crc-local` only; the store keeps `prod-east`'s row, as `Settings.cluster_policy`'s docstring states (a data decision, not a tier one) |

## Verdicts, first pass — head daa39a9

Cursor (ask mode: no shell, no helm, no venv — it read the tree and named what it could not run) and
Codex (a shell on a pristine export of the commit: it ran `load_settings`, TestClient probes, five
mutations, helm renders and a main-vs-head wire diff). Every verdict re-checked here, the refutations
measured before a decision.

| Claim | Cursor | Codex | Decision |
|---|---|---|---|
| C1 config: host, defaults, refusals | CONFIRMED (traced) | CONFIRMED (measured on the four files) | — |
| C2 viewer_scope per policy | CONFIRMED; named the three `all` paths (restrictions off, inherit, a ghost id) | CONFIRMED (measured, including a remote answering exactly `all`) | — |
| C3 hidden = unknown on every handler | CONFIRMED — same 404, same sentence template, the id substituted | REFUTED — the bodies differ by the id (`'dark'` vs `'ghost'`); proposed dropping the id from the detail | **Rejected** — the id in the body is the caller's own input, not information about the server; the same sentence for both is what stops the oracle, and the spec's own test asserts exactly that. Codex's per-handler probe is taken as a test with the id normalised |
| C4 rows, whoami, alerts | CONFIRMED | CONFIRMED (the four wire tests and the B4 cliff test ran) | — |
| C5 remote resolvers | CONFIRMED | CONFIRMED — runtime inspection: bound to the remote's URL and token, host SAR shape, the `admin` label | — |
| C6 ServiceAccount virtual groups | CONFIRMED | REFUTED — `Bad_NS` and `bad_name` pass the four-part check while Kubernetes' `SplitUsername` would reject them | **Rejected** — a name no apiserver issues yields a group no binding names; the review answers a denial either way, so there is no hole and the DNS-1123 code would be complexity without a consequence |
| C7 the page | CONFIRMED | REFUTED — the pill tested `=== "self"` while the helpers test `!== "all"`: a missing scope painted "Full view" over a narrowed layout | **Accepted** — the same fail-closed rule everywhere; Codex's Playwright test taken |
| C8 the chart guard, NOTES, render | REFUTED — NOTES take index 0 as the host and do not trim; the "byte-identical" test was `… or True` | REFUTED — the same, plus: blank values render through and the pod refuses them; two template comments landed INSIDE the ConfigMap's config | **Accepted, all four** — NOTES find the first enabled entry and print it first (Codex's shape); blank is unset in `load_settings` (Codex's most important finding, measured: `visibility: ""` → `ConfigError`); the comment lines removed; the tautology rewritten |
| C9 the tests kill the mutations | CONFIRMED (named the test per mutation) | CONFIRMED — all five mutations run and red, the unmutated focus 271 passed | — |
| C10 the docs | REFUTED — §11 names `/api/events`, which does not exist | REFUTED — the same, plus "first entry" for "first enabled entry" in four places | **Accepted** — the route corrected and a test holds every route §11 names to the app's route table; "first enabled" throughout; the prose-keyword tests rejected as on every PR |
| C11 upgrade behaviour | CONFIRMED | REFUTED — the hand-built poll and dangling alerts lost `silenced`/`silenced_by` (measured against main's wire) | **Accepted** — the two fields restored on both; the same class as deviation 2, the block predating B4 |
| C12 the release push | PLAUSIBLE — the publish/helm race is pre-existing and deliberate | REFUTED — the label step's error text says the chart "will still publish" while chart-releaser has no `if:` and never runs after `exit 1`; proposed a 30-minute wait loop | **Accepted on the message, rejected on the loop** — the text now says the job stops; the wait is the cross-workflow timing assumption the file's own comment forbids after #37, and `validate` gating `release` has put the chart run behind publish on every release since A2 (C3's: publish done 23:31, the chart run 23:33) |

**Cursor's most important finding — `inherit` was the host's resolver, not the host's decided tier.**
A `self-only` host (legal per the guard) with an `inherit` remote served the remote wide to a reader the
host itself refused to widen, and the whoami headline said `all` above a host row that said `self`.
Measured before the fix: host `self`, east `all`, `bindings/findings` 200. **Accepted** — `viewer_scope`
resolves a nameless question to the host cluster's own policy and an `inherit` remote to the host's
policy; the headline, the report ticket and every inherit remote now follow a self-only host. Cursor's
snippet taken in substance, compacted (host policy is one of two values, so no recursion); its test
taken with the headline assertion added.

**Not asked, applied.** Cursor: the Reports tab read the selected cluster's decision while the ticket
is minted on the host's tier, so a host administrator with a narrowed remote selected was refused a
report the API would mint — `narrowedOnHost` for the tab and its fetch guard, Playwright test taken;
the values comment said "chart 0.10.x" (the body's ladder) — 0.20.x. Codex: none beyond its claims.

**Clarified, not changed.** Under `inherit` identity is not consulted — the body withholds the viewer
under `self-only` only — so an `inherit` remote at the default `identity: none` keys a self reader by
the host's username, exactly as before 0.19.0. §11's table and the values comment now say so; the
alternative (identity biting under every policy) would make "set `inherit` to keep the old view" false
for self readers, and the upgrade note is the promise that matters.

## Second pass — head 91c5554, 2026-09-14

An eleven-claim brief on the fixed head: each accepted fix, then the matrix, the decision counts, the
no-host case, the chart's agreement with the app, the byte-identical render, the page's every scope
consumer, the alert wire shape, the docs, the mutations, and the release. Cursor (ask mode, source only —
it enumerated the matrix from the code and marked the runs it could not make PLAUSIBLE); Codex (a shell
on a pristine export; its first launch hung 4 h 16 min on stdin from a backgrounded shell — a launch
defect, written into the skill — and was relaunched with stdin closed).

| Claim | Cursor | Codex | Decision |
|---|---|---|---|
| C1 the matrix | REFUTED — the pass-1 remap copies the host's POLICY and then applies the remote's default `identity: none`, withholding the viewer on an `inherit` remote under a `self-only` host — the very clause §11 states the other way; the pass-1 test hid it with `same-as-host`. And with NO enabled cluster the nameless question fell through to the host resolver: `all` above rows all `self` | CONFIRMED — enumerated all 48 cells by TestClient; read the `self-only`×`inherit`×`none` cell's 403 as agreeing with §11 | **Accepted, both of Cursor's** — under inherit the viewer is kept whatever the remote's identity (the cluster's OWN policy decides whether identity is consulted); no host means fail closed. The pass-1 hole was mine: a fix that made a doc sentence true for the case its test covered and false for the default. The two reviewers read the same cell differently; the sentence in §11 is the contract, and Cursor read it. Codex's CONFIRMED is the weak kind again |
| C2 decision counts | REFUTED — whoami and alerts decided the host twice (nameless, then as a row): 5 notes for 4 served clusters | REFUTED — the same, measured twice: `{admin/all: 2, admin/self: 3}` for four served clusters | **Accepted** — measured: 2 notes after one whoami on a one-cluster app. The whoami headline IS the host row's decision; alerts take the envelope's viewer from `trusted_viewer`. Both reviewers' tests agree; Cursor's taken |
| C3 blank → unset | PLAUSIBLE (traced) | CONFIRMED — measured on every shape; lists, mappings, numbers and booleans are a ConfigError naming the key | — |
| C4 guard / NOTES / load_settings agree | PLAUSIBLE (traced; noted `--set-string enabled=false` would be truthy in all three) | **REFUTED — a quoted `enabled: "false"` in a values file is a non-empty string, truthy in Go and in `bool()`, so all three made the disabled entry the HOST** — Codex's most important finding | **Accepted** — measured: the quoted first entry became the host with `enabled = True`. `enabled` is a word everywhere: `load_settings` takes a boolean or the strings true/false and refuses the rest by name; the guard and NOTES read `trim (toString …)` and refuse any other word. The `enabled` key predates D2, but D2 made it decide the host, which is why it matters now. Codex's three-way test taken |
| C5 byte-identical default render | PLAUSIBLE | REFUTED on the WHOLE chart — two generated Secrets differ by design (`randAlpha`); the ConfigMap alone is byte-identical | the claim was mine and over-broad; **rejected** Codex's test that renders `git archive main` at test time (a checkout without `main`, CI's included, cannot run it) — the existing test holds the comment lines absent and the row free of the keys |
| C6 the page's scope consumers | REFUTED — the selector still tested `=== "self"`; the Overview card does not render `visibility` | REFUTED — the same selector, plus eight `=== "self"` on tab payloads; proposed a `narrowedScope()` helper on all nine and a visibility badge on the card | **Accepted** (the selector). **Rejected** (the eight): they compare the API envelope's `scope`, a closed server vocabulary that is always present on a 200 — the fail-closed rule exists for whoami's `visibility.scope`, which can be absent, and that is what the helpers read. **Rejected** (the card), as for Cursor |
| C7 alert key sets | PLAUSIBLE | CONFIRMED — every alert's keys equal `Alert.as_dict()`'s in both tiers | — |
| C8 the docs | REFUTED — the §11 clause was false of the head (C1) | REFUTED — §5's diagram still carried line-number citations, hundreds of lines stale, inside a code block the citation rule does not scan | **Accepted, both** — C1's fix makes §11 true; the diagram cites `gsd/api.py#viewer_scope`-style anchors and a test holds each to a `def` |
| C9 the pass-1 tests | PLAUSIBLE — named the test per mutation; noted the Reports test pinned `reportsPage()` only | CONFIRMED — all seven mutations run and red | **Accepted** (Cursor's) — a second Playwright test holds `refresh()`'s guard |
| C10 helm.yaml and the release | PLAUSIBLE — the recovery after a lost race is a re-run of the chart workflow | PLAUSIBLE — the same; the workflows are independent, `validate` orders nothing | recorded |
| C11 the next real use | PLAUSIBLE — adding an entry with `--set` must pass every entry | CONFIRMED — the seven renders and four refusals as intended; the full suite 2819 + 1 (the export lacked `.git`, a sandbox artefact); no hand-fix beyond the upgrade note | **Accepted** (Cursor's clause in the upgrade note) |

## Live run on the fixed head, 2026-09-14

Head 3629c8c (both passes applied), built by both wrappers and deployed by `release-crc.sh`
(`running : 3629c8ca27 — verified in-pod`), then the two-cluster check again with `prod-east` at the
defaults, hidden, refused at render, and the release put back:

| Measured | Value |
|---|---|
| startup | `prod-east: per-cluster visibility policy self-only, identity none` — once |
| `/api/whoami`, kubeadmin | `scope: all`; `clusters: {crc-local: {inherit, same-as-host, all}, prod-east: {self-only, none, self}}` — the headline is the host row's decision, decided once |
| `/api/clusters` rows | `crc-local {inherit, all}`, `prod-east {self-only, self}` — prod-east now polled `ok` |
| person-scoped views on prod-east | `groups` → 403 with the §11 sentence; `bindings/findings` → 403; `groupsyncs` → 200; the host's `groups` → 200 |
| `/api/alerts` | `scope: self`; administrator-tier kinds from `crc-local` only |
| prod-east `hidden` | the same `unknown cluster` sentence as an unknown id; absent from the three lists; 37 series on `/metrics` |
| `remote-sar` without `same-as-host` | refused at render |
| the release put back | one cluster, `scope: all`, both pods Running with 0 restarts — the `auth-loglevel` hook completed inside its deadline this time (the first run's timeout was the node's capacity, not a code path) |

## Outcome

Two passes, twenty-three claims. First pass: Cursor refuted three, Codex six (two of them rejected on
consequence); Cursor's most important finding — `inherit` was the host's resolver, not its decided
tier — was real and the spec's own block had it. Second pass on the fixed head: Cursor found that my
pass-1 fix had refused a self reader on an inherit remote under a self-only host (the case my own test
did not cover), and that whoami and alerts decided the host twice; Codex found that a quoted
`enabled: "false"` made a disabled entry the host in the guard, NOTES and the app alike, and that the
Reports tab lagged a cycle behind a mid-session promotion. Ten snippets rejected with reasons
(byte-identical 404s, DNS-1123 on ServiceAccount names, a chart-workflow wait loop, a test rendering
`git archive main`, a nine-site `=== "self"` refactor, a policy badge on the Overview card, and the
prose-keyword tests). Two operator-facing defects the reviewers did not find came from the tooling:
CI's chart job runs without the application (a test split across two modules) and the two-cluster live
check itself (Helm's padded-null list entry). Re-validated on 3629c8c: the full hermetic suite 2839
passed / 14 skipped, the browser subset 42 passed, helm lint and actionlint clean, both images built
locally with their proofs, deployed to the reference cluster and the live checks above.

**Not asked, Codex.** `refresh()` chose its report requests on the PREVIOUS cycle's host tier, so a
reader promoted mid-session saw "Loading…" on the Reports tab for a whole cycle (measured: zero
report calls on the promoting refresh) and a demoted one kept the catalogue. **Accepted** — the same
catch-up the Access granted tab has, after the whoami lands: a narrowed host drops the catalogue,
the runs and the ticket; a promoted reader fetches both and never lends a ticket minted under the
old identity. Playwright test taken (the page's `reportGet` is a global, so the seam is real).
