# Users tab from User objects (PR #47, app 0.9.0 / chart 0.9.0) — adversarial review record

**Target:** `feat/users-tab-logins` at `4e1518c` (the implementation commit). Both reviewers received
the same eleven-claim brief naming the exact file, symbol and expected behaviour per claim, and wrote
to separate files. Codex ran read-only with a shell (in-memory SQLite and `TestClient` probes); Cursor
ran in ask mode with the shell blocked, so its verdicts rest on reading code and tests. Every verdict
below was re-checked before being accepted; the disposition column is the arbiter's.

**Baseline measured before the pass:** `cd local-development && .venv/bin/python -m pytest tests/ -q
--deselect tests/test_live_smoke.py` → `1646 passed`. Live on CRC at the same commit: 62 users, 61
logged in, one manual account, 3 synced members never logged in, `source: ok`, migration 7 applied.

## Verdicts

| Claim | Codex | Cursor | Re-check | Disposition |
|---|---|---|---|---|
| C1 `Store.users` joins cannot multiply; success-only last login; limit+1; offset | CONFIRMED (probe: 3 groups, 4 mixed events → 1 row, count 3, newest success) | CONFIRMED | matches the query | accepted |
| C2 self tier scopes both sources | CONFIRMED (probes incl. case variant) | CONFIRMED | byte-exact `=` on both base tables | accepted; case-variant test added |
| C3 migration 7 on v6 and fresh; WAL | PLAUSIBLE — sound, no multi-connection probe possible | CONFIRMED; WAL note | migration runs in `Store.__init__` before the API thread; a shared-DB overlap of old and new pods would be the only hazard, and the chart's single-replica default avoids it | accepted, no change |
| C4 `_user_row` decoding | CONFIRMED (`''` → `[]`; NULL providers refused by NOT NULL) | CONFIRMED | — | accepted |
| C5 poller outcomes; **a poll failing before the users read leaves `ok`**; tab hid `source_observed_at` | REFUTED | CONFIRMED with the same wedge | true: `poll_once` returns at `client.fetch()` failure before the block | **fixed**: the tab shows when its source was last read; the early-failure behaviour is pinned as accepted (`test_a_poll_that_fails_before_the_user_read_…`) and the design doc says the Overview is the poll-freshness channel |
| C6 paging fields consistent, offset past total | CONFIRMED (probe at offset 99) | CONFIRMED, untested | — | accepted; offset-past-total test added |
| C7 detail 404 rule; refusal before lookup | CONFIRMED | CONFIRMED; **adjacent defect**: empty-groups copy claims prior membership | true for a User never in a group (`kubeadmin`) | **fixed**: copy branches on history; UI test added |
| C8 renderer vs old payloads | CONFIRMED; three malformed-payload throws listed | same three | `never.names.map`, non-array `providers` | **fixed**: `Array.isArray` guards; old-server payload UI test added |
| C9 chips wired; no reset on cluster switch | PLAUSIBLE: reset warranted | CONFIRMED: reset would be right | a `provider:x` chip carried to another cluster hides every row for a reason the reader never chose | **fixed**: `applyPosition` resets `userFilter`/`showNeverNames` on a cluster change, keeps the search; UI test added |
| C10 tests pin the behaviour | REFUTED, list of gaps | REFUTED, overlapping list | both lists accurate | **fixed**: poller matrix (6 tests), stale-rows banner, source age, cluster-switch reset, detail KPIs, self-scope never line, case-variant scope, providers sorted on the wire, old-server payload, offset past total, headline vs manual account |
| C11 docs vs code | REFUTED: **headline counts manual accounts as logins**; `unavailable`/`forbidden`; "cluster health"; `login_capture` per row vs top level; never-logged-in "chip"; paging "no longer optional" vs a 10,000 fetch; architecture table row | `unavailable`/`forbidden`; "cluster health"; architecture table row; chart-test docstring | all true | **fixed**: `logged_in_total` on the wire and the headline uses it, with a manual-accounts note; every listed sentence corrected |

## What Codex found that Cursor did not

The headline. `total` was `COUNT(*)` over every User object, and the KPI labelled it "Have logged in",
while a row for a User with no identity said "manual account · never logged in" on the same screen.
On CRC that is one account (`test-python-user`), so the headline read 62 where 61 was true. Cursor
confirmed the values comment and README row that made the same claim. Codex's C11 traced the number
from `store.count_users` to the KPI label and called it. That is the one finding in this pass that
changed what the page says, and it needed a reviewer that followed a value across three files.

## Where they disagreed

- **C3.** Codex would not say CONFIRMED without a multi-connection WAL probe it could not run;
  Cursor confirmed from the code. Neither found a defect; the arbiter accepts with the deployment
  note above.
- **C5, C9.** Codex REFUTED / PLAUSIBLE where Cursor CONFIRMED-with-caveat. Same facts, different
  thresholds for the word; both led to the same fixes.

Cursor's distinctive contributions: the detail-page copy defect (C7), which Codex did not raise, and
the observation that `source_observed_at` was on the wire and nowhere on the page. Codex's: the
headline, the doc-vocabulary drift in five places, and every probe result being a number rather than
a reading.

## Declined

- **Clear `ocp_user_status` when a poll fails before the users read.** A Groups-list failure says
  nothing about the User read; the last verdict stands, the tab shows its age, and the Overview
  shows the poll failure. Pinned as a decision by test.
- **A paged loop in the UI** (Codex C11). The chips and the Find box work over what is loaded; a
  loop would make their denominators lie. The single fetch at the server's maximum stays, with the
  truncation note, and the API pages for consumers. Recorded in the design doc.

## Invocations

Cursor: `cursor agent -p --mode ask --output-format text --trust "<brief>"`; the shell was blocked in
this session, so no pytest or sqlite ran. Codex: via the rescue agent; its sandbox could not write the
requested output file, so the transcript was captured by the agent.
