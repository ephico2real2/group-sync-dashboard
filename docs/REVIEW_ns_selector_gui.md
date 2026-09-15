# Review — PR #117 (#103, B3 GUI): the mnemonic multi-select on the namespace-access form

Adversarial second-opinion pass, 2026-09-14, on the five-claim brief for #117 — the Extension-B GUI from
`docs/DESIGN_reporting_auditors_and_ns_selector.md` §3.7. The change adds, to the report catalogue, a
per-cluster `namespaceSelectors` map, and renders it as a `<select multiple>` on the namespace-access
form ahead of the advanced explicit-names field; `readParamEl` serialises the multi-select as an array.

Codex ran at `gpt-5.6-sol` / `xhigh` with a shell (it traced the whole render→serialise→validate path,
executed the validator directly, and reproduced the corrupt-snapshot 500; Playwright could not launch in
its sandbox — `EPERM` on the artifacts dir — so its browser conclusions are trace-only). Cursor ran on
`cursor-grok-4.6-high-fast` in ask mode with the shell blocked and traced from source. Every verdict was
re-checked here, in a browser for the UI claims and by executing the endpoint for C1; each accepted fix
has a test that fails on the code before it and passes after (both demonstrated by reverting the fix).

## First pass — verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 `list_reports` returns `{label, values}` per cluster; a missing/unreadable snapshot yields an empty map, never a 500 | REFUTED: a **corrupt** copy raises `sqlite3.Error`, not caught → 500 | REFUTED: same — `sqlite3.Error` is neither `SnapshotError` nor `OSError` | **Accepted on the fact; both reviewers' snippet rejected.** Both proposed `import sqlite3` + `except sqlite3.Error` in `server.py` — which breaks the enforced storage seam (`test_storage_seam`: only the backend may name the engine). Fixed at the right layer instead: `Snapshot.__init__` translates the `sqlite3.Error` to `SnapshotError`, so `server.py`'s **unchanged** `except (SnapshotError, OSError)` catches it. A corrupt-snapshot test locks it, and three more lock the happy path the suite never had |
| C2 the special-case replaces the generic field — exactly one `data-param="mnemonics"` | CONFIRMED | CONFIRMED | — |
| C3 `readParamEl` serialises `<select multiple>` as the full array; the POST carries a real array | CONFIRMED (executed the validator) | CONFIRMED (traced) | — |
| C4 selection survives a same-cluster re-render; a cluster switch re-lists the new values | REFUTED: a switch does **not** clear `reportForm.mnemonics` → cluster A's value posts against B | CONFIRMED mechanics, **defect on the named risk** | **Accepted**: `applyPosition` drops the stale mnemonic on a cluster change. Cursor's extra `generateReport` filter **rejected** (below) |
| C5 the B3 test proves the array posts and follows the cluster | REFUTED: it never clicks Generate, never inspects the POST, counts the wrong element, and bypasses `navigate` | REFUTED: same, with a table of what each mutation would/would not catch | **Accepted**: the test is replaced — it captures the real POST, asserts one `data-param`, and switches via `navigate()` |

## What each accepted fix is

- **C1 — the corrupt-snapshot 500 (fixed at the backend boundary, not in `server.py`).** B3 is the first
  caller to open a snapshot from the catalogue. `Snapshot.__init__` reads `PRAGMA user_version`; on a file
  named like a copy but not a SQLite database, that raises `sqlite3.DatabaseError`, which subclasses
  `sqlite3.Error` — neither `SnapshotError` nor `OSError`. Reproduced here: before the fix,
  `GET /report/api/reports` returns **500** (the whole Reports tab faults, since `guard403` rethrows
  anything but 403). Both reviewers proposed the same fix — `import sqlite3` and `except sqlite3.Error` in
  `server.py`. **Re-checked and rejected as written:** `test_storage_seam::test_no_module_imports_a_database_driver`
  fails on it — `server.py` is not a backend, and the enforced seam (docs/storage-coupling.md,
  `BACKENDS = {store.py, reporting/snapshot.py}`) forbids any module outside the backend from naming the
  engine. A correct finding whose fix was at the wrong layer. Applied instead in the backend that already
  owns sqlite3: `Snapshot.__init__` wraps its connect / `PRAGMA` / `sqlite_master` reads and re-raises
  `sqlite3.Error` as `SnapshotError` (closing the half-open connection first) — so `server.py`'s two
  `except (SnapshotError, OSError)` guards are **unchanged** and now catch the corrupt case too, returning
  **200** with `namespaceSelectors: {}` and the eleven reports; the GUI hides the control. The
  `snapshot_age` probe (the other site) is fixed by the same wrap, since it also opens through
  `Snapshot.__init__`. Test: `TestNamespaceSelectorsOnTheCatalogue` — the corrupt case fails-before (500) /
  passes-after (200), plus the configured-label happy path, the empty-label case, and the missing-directory
  case, none of which the suite exercised before.
- **C4 — the stale mnemonic on a cluster switch.** A mnemonic is a value of *this* cluster's selector
  label. `applyPosition` is the single chokepoint every cluster change passes through (the `#f-cluster`
  selector, `popstate`, `hashchange`); it already drops cluster-scoped `data` and resets `userFilter` /
  `bindingSearch` when the cluster changes, but it left `view.reportForm["namespace-access"].mnemonics`
  in place. Carried across, the value does not appear selected (cluster B lists different options) yet
  `generateReport` still posts it — a failed run ("no namespace carries…") or, if the reader then types
  explicit names, a hidden XOR 422. The fix deletes `mnemonics` inside the existing
  `pos.cluster !== view.cluster` block; `include_members` is not a cluster fact and stays.
- **C5 — the test.** Rewritten to click Generate and capture the real POST via `page.expect_request`,
  asserting the body carries `cluster: "crc-local"` and `params.mnemonics: ["beta","demo"]` (an array,
  not `"beta"`); to assert exactly one `[data-param="mnemonics"]` element (a duplicate generic input would
  have passed the old advanced-field count); and to switch clusters through the real
  `navigate({cluster:"prod-east", …})` → `applyPosition` path, then assert the stale mnemonic is gone and
  the options are the new cluster's. Reverting the C4 delete makes it fail (`['beta','demo'] is None`).

## Rejected

- **Cursor's second C4 site — a filter inside `generateReport`.** Cursor proposed, beyond the
  `applyPosition` clear, dropping non-current mnemonics again at Generate
  (`params.mnemonics = params.mnemonics.filter(v => sel.values.includes(v))`), as a "belt for any path
  that assigns `view.cluster` without `applyPosition`". Re-checked: there is no such path in production —
  the cluster selector dispatches `navigate` → `applyPosition`, and Cursor itself calls `applyPosition`
  "the chokepoint for `#f-cluster`, popstate and hashchange". The only caller that set `view.cluster`
  directly was the *old* B3 test, which C5 replaces with one that uses `navigate()`. Adding runtime
  filtering to defend a code path that does not exist grows the code to guard a test artefact; the
  single-site `applyPosition` clear closes the real hole. (Review fixes stay the smallest that close the
  hole — the standing project rule.)
- **Cursor's C4/C5 replacement test body** was not taken verbatim: it switched via
  `page.select_option("#f-cluster", …)` and captured the POST with a synchronous `page.on("request", …)`
  guarded by a dummy `wait_for_function`. The `navigate()` evaluate is the same real path with fewer moving
  parts, and `page.expect_request` is Playwright's own capture helper (Cursor flagged this substitution as
  acceptable in its own note). Codex's `page.route`-fulfil stub was also set aside: it fabricates a minimal
  failed-run body the status card must then render, and Codex could not run it under Playwright; capturing
  the real outgoing POST needs no stub and was verified in a browser here.

## Not asked (volunteered, re-checked, no change)

- **Cluster absent from `namespaceSelectors`** (old report pod, swallowed snapshot `{}`, or a cluster the
  snapshot has not seen) → the `|| {label:"", values:[]}` guard hides the control. Safe. (Both reviewers.)
- **XSS in the label / option values** → `esc()` covers `& < > " '` on both the option value/text and the
  label; values are operator-controlled namespace labels and are still escaped. Safe. (Both reviewers.)
- **Both mnemonic and explicit names filled** → server-side XOR 422 as designed; the page shows the generic
  "parameters were refused" line rather than the specific sentence. That copy is older than B3
  (`generateReport`'s catch) and is out of scope here — recorded as accepted debt, not introduced by B3.

## Outcome

Two implementation defects and one over-claiming test, all confirmed by re-checking: a corrupt snapshot
could 500 the entire Reports tab (C1), and a cluster switch could post an invisible previous-cluster
mnemonic (C4). Both holes are closed by the minimal correct fix — C1 by translating the engine error to
`SnapshotError` at the backend boundary (`Snapshot.__init__`) rather than by importing sqlite3 into
`server.py` as both reviewers proposed, which the full suite proved would break the enforced storage seam;
C4 by a one-line clear in the existing cluster-switch chokepoint. Each is locked by a test proven to fail
on the code before it. The `generateReport` belt was rejected as complexity guarding a path production does
not take. Full suite (2912 non-UI) and the UI suite (274) green; second pass below.

## Second pass — on the fixed head, same two models

Brief: verify each accepted fix closes its hole and opened no other, then attack the corners the first
pass did not name (D1 the `except` breadth and the query-time gap, D2 the delete's blast radius, D3 two
switches / the chokepoint claim, D4/D5 the new tests' non-vacuity, plus schema-too-new, pre-migration,
unseen cluster, and the rejected belt). Codex ran `gpt-5.6-sol`/xhigh with a shell (it executed the real
`applyPosition`/`reportFormCard` in Node and drove the real FastAPI route with an in-process reinstalled
pre-fix constructor); Cursor traced from source in ask mode. Playwright and a physical revert-and-run were
blocked in Codex's sandbox (`EPERM`/`mktemp`), so D4/D5 came back PLAUSIBLE from it — both were CONFIRMED
here by actually running the tests with the fix reverted (fail-before) and in place (pass-after).

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| D1 the C1 wrap catches the corrupt file without hiding a real bug, and is at the right/sufficient boundary | **REFUTED**: `__init__` is too narrow — a copy that opens cleanly then raises `sqlite3.Error` from a TABLE read still 500s `/api/reports` (proved: `query_time_api_status= 500`) | CONFIRMED, residual named as accepted debt ("do not widen the wrap") | **Codex accepted.** The endpoint's contract is best-effort degradation, and the query-time 500 is the same class of hole C1 exists to close. Applied Codex's fix: a backend `Snapshot.namespace_selectors(label)` that gathers `clusters()`+`namespace_metadata_values` and translates `sqlite3.Error` → `SnapshotError`; `server.py` calls that one method (still no `import sqlite3`). Locked by `test_a_table_read_after_a_clean_open_that_fails_is_200_not_500` (both queries, fails-before 500 / passes-after 200). The `__init__` wrap stays — the two are complementary (open-time vs query-time). Cursor's "hides a real bug" objection is answered: the wrap is scoped to the two catalogue reads, and the happy-path value assertions in this class fail CI on a genuine query bug |
| D2 the C4 delete changes only the stale mnemonic | CONFIRMED (executed `applyPosition`: `namespaces`/`include_members` survive, same-cluster repaint preserves, delete-on-absent safe, other forms untouched) | CONFIRMED (same, with the cluster-fact rationale) | No change — both confirm |
| D3 `applyPosition` is the single chokepoint; the `generateReport` belt is right to reject | **REFUTED as worded**: the boot default assigns `view.cluster` directly, so it is not literally the single *setter* — but "cannot resurrect stale mnemonics and does not justify a belt" | CONFIRMED: the only non-`applyPosition` assignment is the boot default; not a change; rejecting the belt is correct | **No code change.** Both agree it is not a live bug. The boot assignment is a *deliberate, already-documented* exception (`index.html`: "The ONLY position mutation outside navigate(), and it has to be… `applyPosition` is a no-op here"), it runs once with a fresh `reportForm`, and this record's claim is "the chokepoint every cluster **change** passes through" — the boot sets the initial value from `null`, which is not a change. Codex's boot-to-`navigate` rewrite + a source-grep invariant test were declined: changing well-reasoned boot code and adding a brittle lint for a non-bug grows complexity against the standing "review fixes stay simple" rule |
| D4 the corrupt-snapshot test is non-vacuous | PLAUSIBLE (sandbox blocked revert-and-run; in-process proof shown) | CONFIRMED (path/values), PLAUSIBLE on revert-and-run | **CONFIRMED here**: reverted the wrap and ran it — 500 before, 200 after; `_STAMP` matches the file; `["beta","demo"]`/`["gamma"]` match `DISTINCT … ORDER BY value` |
| D5 the C5 test proves what it claims, no flake | PLAUSIBLE (Chromium `EPERM`); races analysed, none real | PLAUSIBLE (same) | **CONFIRMED here**: ran it with C4 reverted — `['beta','demo'] is None` fails; with C4 it passes |

Volunteered and re-checked by both, no change: a schema-too-new snapshot degrades to `{}`/200 (and `readyz` 503, a tighter signal); a pre-migration snapshot with no `cluster_namespace_label` yields `values: []` via the `has_table` guard; a configured-but-unseen cluster is absent from the map and the GUI `|| {label:"",values:[]}` guard hides the control; the validator's array/empty/XOR behaviour holds. Codex's read-only runs: `test_storage_seam` 98 passed, the validator 5 passed; both reviewers left the tree clean.

**Second-pass outcome.** One real gap (D1, Codex): the first fix closed open-time corruption but not a table read that fails after a clean open — a 500 the best-effort contract forbids. Closed by moving the gather behind `Snapshot.namespace_selectors`, which keeps the seam and degrades both failure times to `{}`. D3's chokepoint wording was tightened in the reviewers' favour (the boot default is a documented one-time exception, not a cluster change) without a code change. Everything else confirmed. Full suite re-run green after D1.
