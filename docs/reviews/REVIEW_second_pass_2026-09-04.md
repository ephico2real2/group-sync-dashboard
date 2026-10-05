# Second pass over merged main (94c792a): the Route, the Users tab and Access granted together

**Target:** `main` at `94c792a`, carrying PRs #45–#49. A second pass rather than a diff review: both
reviewers received one nine-claim brief on the interactions between the three merges, and were asked
to say what the first-pass records (`REVIEW_users_tab_logins.md`, `REVIEW_access_granted_reach.md`)
and their fixes could have missed. Every verdict was re-checked against the code, a query or the
poller's structure before being accepted; the disposition column is the arbiter's.

## Codex

Read-only with a shell but no writable temp directory, so pytest could not run; in-memory SQLite
probes and code reading, including `EXPLAIN QUERY PLAN` for S6.

| Claim | Verdict | Re-check | Disposition |
|---|---|---|---|
| S1 one definition of a login across Users and Reaches | CONFIRMED; both tables can be stale independently | true, and the Users tab shows its source age | accepted |
| S2 Reaches arithmetic equals never-logged-in + manual members | **REFUTED**: `group_state.member_count` and `group_member` "are separate write transactions" | partly wrong on the mechanism — `gsd/poller.py#poll_once` writes both inside one `store.poll_snapshot()` transaction — but right on the seam: nothing in the STORE ties the Group object's count to the membership rows, and Cursor made the same point independently | **fixed**: `member_count` now comes from the same membership rows as `logged_in_count`, so the invariant holds by construction; test |
| S3 drill rule | CONFIRMED; **new**: a row with no `finding` (older server) still drilled | true — the rule was negative | **fixed**: positive rule (ok, unmanaged, dangling drill); test |
| S4 nine tier transitions | **REFUTED**: the three cases where the new whoami is null — a cached wide payload painted under an unknown identity, or Loading with no correction | true by the code | **fixed**: `bindingsPage` fails closed to Loading when the tier is unknown, as the Overview does; test |
| S5 metrics and privacy | CONFIRMED | — | accepted |
| S6 query cost, `EXPLAIN QUERY PLAN` | CONFIRMED: the reach subquery materialises once per query and the outer join probes it; `group_member`'s primary key serves it | — | accepted |
| S7 migration 7 then first poll | **REFUTED**: before any User read the Reaches column said "0 logged in", a confident answer to a question never asked | true | **fixed**: null until `ocp_user_status` has a row; stands through a later refusal; test |
| S8 tests pin S1–S7 | REFUTED, gaps listed | accurate | fixed for S3, S4, S7; the rest recorded below |
| S9 docs after three merges | REFUTED: README Users paragraphs, `/users` and `/users/{name}` in API.md, current-tense parts of the Users design doc | true — found independently the same hour and fixed in #50 | fixed (#50) |

## Cursor

Ran after Codex, in ask mode with the shell blocked for pytest but able to probe a temp store; it
reviewed merged `94c792a` while the fix branch was already in the working tree and said so,
labelling each fix "found here / already sketched in dirty tree". Its verdicts match Codex's on
every claim; its S4 matrix is the same nine cases with the same three failures; its S6 confirmed
the reach subquery is materialised once (`MATERIALIZE li`, then `SEARCH li` per binding) on the
`group_member` primary key. Its distinctive contribution was the S2 wording — "Reaches can show a
'not logged in' gap that is really 'membership table behind the Group object'" — which is what
turned S2 from declined into fixed. Its S9 list added the design doc's present-tense "today" section
and the 0.10.1 Chart paragraph's overclaim; both corrected here.

## Declined or deferred

- **S8 remaining gaps** (a whoami failure while findings is refused; missing entire tiers and
  `counts` in a payload; the C1 four-member probe as a named test): low value against the fixture's
  coverage; recorded.

## What this pass added that the first passes did not

Three defects, all at the seams: an indeterminate identity between two tiers, a count reported before
its source had ever been read, and a row shape from a server that predates the tier field. None was
visible from either feature alone, which is the case for a second pass over the merged whole.
