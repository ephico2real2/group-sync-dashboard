# Review record — the report forms (#149 R7, PR #222)

Branch `feat/149-forms`, base `feat/149-status-page` (PR #221) then `main` once #221 merged. Three seats:
Cursor Grok 4.6 (ask mode, from source), Codex GPT-5.6 xhigh (a `git archive` of `7fa4a6e`, with the
venv; 274k tokens; GitHub unreachable from its sandbox, so it read the R7 text from the brief) and OB3
(Opus 5, the live repository). Grok answered first and its ten findings were applied at `57b2c5c`
before Codex finished; Codex's report is read against that head below — where it names a defect Grok
had already found, the row says so, and the record keeps both verdicts because they were reached
independently. The brief: ten claims (M1–M10), reproduced by claim
in the table.

## Claims × decision

| # | Claim | Grok | Codex | Decision (head after the pass) |
|---|---|---|---|---|
| M1 | The Subject scope's semantics on the four subject reports | REFUTED — dormant-access never imported `subject_filter` (three sections cluster-wide, only the last table filtered); login-activity's Summary stays cluster-wide; a named group with no binding vanishes from the certification pack | REFUTED, the same three, with the probe's figures (`users=alice → attempts=3, users=1`; `groups=team-a` still listing carol, dave, erin; `groups=empty-group → {'groups': 0}`) | **Accepted** — dormant-access applies the scope to every section (`57b2c5c`); a named subject with no binding is said in a *Named but not bound* caveat (`57b2c5c`; Codex's alternative — an empty `Group:` section counted as certified — **rejected**: an empty table on a signed pack certifies nothing, the caveat says so). Login-activity's Summary: first kept cluster-wide with a Scope note saying so (`57b2c5c`); on Codex's row — `totals.attempts` counted the cluster beside a scoped `users` — **scoped** (`login_summary(user_names)`, this pass). |
| M2 | `group_mnemonic` resolves through the group label; nothing certified when nothing resolves | CONFIRMED | CONFIRMED (`resolve beta=['team-a']`, missing label `[]`, unknown mnemonic `0/0`, mnemonic + explicit group = union) | Holds. |
| M3 | `group_by`: ordering; the default changes nothing without captured labels | REFUTED — the default `mnemonic` set a bucket whenever the first dimension existed, so every heading on crc.yaml's nightly read `(no mnemonic) · Namespace: …` | CONFIRMED on `7fa4a6e` (after the fix: `alpha, beta, (no mnemonic), Cluster-scoped`; unchanged headings with no labels) | **Accepted** (`57b2c5c`): no bucket where nothing is captured; the test asserts both. |
| M4 | `discovered()`: guards, the cap, the route's degradations; the cost at 50 000 users | REFUTED — the users query had no LIMIT and parsed every `providers` blob; `groups()` unguarded | REFUTED — deleting `group_state` from a readable snapshot 500'd the route; a post-open `sqlite3.Error` is not translated (`queries=6 rows_materialized=50011`) | **Accepted** — LIMIT cap+1 on both name lists, a non-JSON blob counts as no provider, `group_state` guarded (`57b2c5c`); the post-open `sqlite3.Error` → `SnapshotError` wrap on `discovered()` like the other seam methods (this pass; the route already degrades `SnapshotError` to empty menus). Codex's rewrite of the whole method **rejected** — it dropped the bounded reads. |
| M5 | The controls post what the validators take; the repaint keeps the form's state | REFUTED — Advanced open state derived from "value ≠ default" only, so the lookups' arrival closed a disclosure the reader opened | REFUTED, the same, plus the 422 copy dropping the service's detail | **Accepted** (`57b2c5c`): Advanced is view state (`view.reportAdvancedOpen`); `reportFetch` carries a 422's `detail` and the run status shows it. |
| M6 | `ensureDiscovered()`: once per cluster, presence with `in`, no loop | CONFIRMED | CONFIRMED (driven in Node: rejecting, scalar and `{cluster}` replies → `calls=1 renders=1`; the cluster switch `calls=2`) | Holds. |
| M7 | The instant landing; the lookups' arrival re-landing | CONFIRMED / PLAUSIBLE on the ~100 ms fight | PLAUSIBLE — resetting `reportLanded` on arrival can yank back a reader who scrolled | **Accepted** (`57b2c5c`): the arrival repaints, it does not re-land. |
| M8 | Accessibility: roles, words, focus after a chip | REFUTED — a chip added from a keyboard-focused option (no id) dropped focus to `<body>` | REFUTED, the same | **Accepted** (`57b2c5c`): `after(name, focusId)` returns focus to the lookup input. |
| M9 | The chart: the env, the helper appending once, the guard, behaviour preservation | CONFIRMED | PLAUSIBLE — rendered and lint clean; base/head default object graphs equal but for the version labels and the new empty env; Kustomize renderer cases skipped (Helm 4 in its sandbox) | Holds; chart 0.40.0 (#221 took 0.39.0). |
| M10 | Old keys 422; crc.yaml posts none; the eleven reports render both ways | CONFIRMED / PLAUSIBLE on the operator docs | CONFIRMED; the CHANGELOG needs a migration note | **Accepted** — `docs/reports/README.md`'s table and schedule example (`57b2c5c`); the CHANGELOG's migration sentence, `reporting.namespaceGroupLabel` in the chart README, `docs/DESIGN_reporting_service.md` §7.3's parameter column, and an Orchestrator's note in `docs/specs/SPEC_C3_reporting_microservice.md` (this pass). Codex's test over three documents against the registry **rejected**: the spec's fenced blocks are the 2026-09-05 design as written and must not track the code. |
| F10 | (Grok, volunteered) the groups report's `groups` filter narrowed the inventory but not the membership changes | — | — | **Accepted** (`57b2c5c`). |
| N1 | (both, volunteered) `.rp-count-live` written into the markup with no rule | noted as harmless | required, with the mock's mono/accent treatment and a class-rule guard test | **Accepted** (this pass): the rule, and `test_every_report_shell_class_the_page_writes_has_a_rule` — fails on the head without it (`['rp-count-live']`). |
| N2 | (Grok) the mock's auto-filled reviewer is not in the shipping form | deviation, not a defect | — | Shipped in #143's PR (the reviewer prefilled from the signed-in name), not here. |
| N3 | (both) a walk report for R7 under `reports/` | required | required, with the list of states to show | **Accepted** (`66e8715`): `reports/2026-09-20_report-forms-149/` — the lookups from the real cluster, the chips, the POST, the pack certifying the group a mnemonic resolved to. |

## Re-validation

- `tests/test_reporting_catalogue.py -k "scoped_login_pack or damaged_table"`: both fail on the head
  without the fixes (`attempts=3`; `sqlite3.OperationalError` raised through) and pass with them.
- `tests/test_type_scale.py`: 19 passed; the new guard fails without the `.rp-count-live` rule.
- The hermetic suite and `helm lint` on the branch after the pass: see the PR's comment for the totals.
