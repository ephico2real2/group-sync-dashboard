# Access granted: reach, filter, sort and the reader's own grants (PR #48, app 0.10.0) — review record

**Target:** `feat/access-granted-default` at the implementation commit ("feat: Access granted says
who each grant reaches, filters and sorts, and shows a reader their own"). Both reviewers received the
same eleven-claim brief naming the exact file, symbol and expected behaviour per claim. Every verdict
was re-checked against the code, a render, or a live query before being accepted; the disposition
column is the arbiter's.

**Baseline measured before the pass:** full suite `1683 passed` (Playwright included); live on CRC at
that commit, all 38 granted and unmanaged findings rows matched member and logged-in counts computed
independently from `oc get groups` and `oc get users`, and every other tier's row carried null.

## Codex

Ran read-only with a shell, but its sandbox had no writable temp directory, so pytest could not run;
verdicts rest on reading code and probing with in-memory SQLite where it could.

| Claim | Verdict | Re-check | Disposition |
|---|---|---|---|
| C1 `_REACH_JOIN` cannot multiply; NULL exactly when no Group; `reach=False` unchanged | CONFIRMED | `tests/test_binding_reach.py` runs the probe it could not | accepted |
| C2 hot callers pay nothing; `_binding_counts` scalar with defaults | CONFIRMED | — | accepted |
| C3 counts describe the cluster; fields in every tier; `@consistent`; 403 byte-identical | CONFIRMED | — | accepted |
| C4 default sections and their order; header from `counts`; "all" includes Built-in | CONFIRMED | — | accepted |
| C5 search | CONFIRMED, two UX defects: the note's denominator counted hidden Built-in rows; the search survived a cluster switch | both true | **fixed**: denominator is the sections shown; cleared on a cluster switch, sort kept |
| C6 sort | CONFIRMED | — | accepted; the sort state is shared with RBAC policy by design (one table helper, one preference) |
| C7 self tier in `refresh()` | **REFUTED**: requests were chosen from the previous cycle's identity and painted under the new one — an admin demoted mid-session got the wide payload for a cycle, a reader promoted got the narrowed one | true by construction | **fixed**: after the burst the tab decides again from the whoami that just arrived and makes one guarded follow-up fetch either way, clearing the other tier's payload; two Playwright tests drive the transitions by changing the identity header between refreshes |
| C8 `myAccessPage`, banner, drill, hidden controls | CONFIRMED | — | accepted |
| C9 renderer robustness | CONFIRMED, one gap: a narrowed identity with no username spun on "Loading…" | true | **fixed**: a named card; test |
| C10 tests pin C1–C9 | REFUTED, list of gaps | accurate | **fixed** for the transitions, the no-username case, a non-404 failure on the own path, the denominator and the cluster switch; the rest recorded below |
| C11 docs vs code | REFUTED: README "defaulting to what needs review"; ACCESS_CONTROL's "no honest per-reader subset" now contradicted by the tab; the admin-tier review record's item 3 and refusal-cards paragraph unscoped; `require_admin_tier` listed the sync CRs, which are served at both tiers | all true | **fixed**, every sentence |

## Cursor

The `cursor agent` run lost its connection to the service repeatedly and had produced no verdicts
when this record was written; see the addendum below if it completed.

## Declined or deferred

- **Pinning the generated SQL text for `reach=False`** (Codex C10): the store test pins the returned
  keys, and the `_FINDING_FROM` concatenation is what the count query reads — a text assertion would
  break on any reformatting. Declined.
- **A whoami failure while findings is refused** (C10): `narrowedFor(null)` is false, so the refusal
  card renders — the pre-existing behaviour, unchanged; not separately tested.

## What changed because of the review

The tier-transition race is the finding that mattered: it was invisible to the steady-state tests
and to the live check, which only ever loaded the tab under one identity. Both directions now have a
Playwright test that changes the identity header between two refreshes and asserts the tab paints
the new tier's view on the very next cycle, with the other tier's payload cleared.
