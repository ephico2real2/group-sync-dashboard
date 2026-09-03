# Review: user search (the Users tab and the group page's Find member box)

Adversarial review of PR #42 before merge, in the shape `docs/REVIEW_group_search.md` set: the
claims the change makes, handed to a second reviewer with the exact files and what to confirm or
refute, and what came back. Codex ran the pass read-only against `git diff main...feat/user-filter` before merge; Cursor ran
the same brief read-only against the merged range after merge (its CLI was not signed in at the
time), and its findings are at the end of this file.

Citations are by symbol (`file#symbol`), never by line, so this file stays true after the next edit.

## What was claimed

**A. Store.** `gsd/store.py#Store.users` gains `full_name` through the same `LEFT JOIN ocp_user`
that `Store.group_members` makes. The join is 1:1 (`ocp_user`'s key is `cluster_id, user_name`),
so `GROUP BY m.user_name, u.full_name` splits nothing and `group_count` cannot inflate; ordering
stays on the id; the `limit + 1` truncation contract survives; the narrowed-tier predicate stays on
the base table, so no other user's name can be reached.

**B. UI.** `gsd/static/index.html`:

1. The group box's markup, wiring, IME guard and Escape handling move into `SEARCH_BOXES`,
   `searchBoxHtml` and `wireSearchBox`; the composing flag becomes the id slot `searchComposingIn`.
   Behaviour of the group box is unchanged; only one box can render at a time; a stale slot cannot
   freeze the bar because the guard compares ids.
2. `matchesSearch(fields, query)` drops null fields and space-joins the rest, so a term cannot
   straddle the id and the name.
3. `usersPage` fetches the API maximum (`USERS_FETCH`), matches first and caps the paint second
   (`USERS_RENDER`, stated when it bites), and its empty state never blames the search at a zero
   denominator.
4. Navigation: `render` dispatches page `users`; `wireDrilldown` keeps a drill from Users under
   Users; `PAGE_LABEL.users`; `applyPosition` drops `data.users` on a cluster switch; the repaint
   fingerprint includes it; `/users` is fetched only on its own tab with no drill open.
5. `view.memberSearch` clears in `applyPosition` whenever the group changes; the box renders only on
   a group detail; `groupDetail` filters `members` into `shown` and keeps the empty-group text.
6. Every new interpolation goes through `esc`.

**C. Tier safety.** The UI never decides the tier; banner and empty state read the envelope's
`scope` and `viewer`; no new path shows another user's name to a narrowed reader.

**D. Tests** cover the above. **E. Versions and docs** agree.

## What came back

| Claim | Verdict | Note |
|---|---|---|
| A | confirmed | Join 1:1 on the `ocp_user` key; predicate, grouping, ordering and `limit + 1` intact; Protocol signature unchanged. |
| B.1 | confirmed | Mutually exclusive render predicates; id-compared guard. |
| B.2 | confirmed | |
| B.3 | **refuted** | The heading counted matches, not painted rows: with 1,500 users loaded and the 1,000-row cap in force it read "1500 shown". |
| B.4 | confirmed | |
| B.5 | confirmed | The group box no longer renders on detail pages; a test asserts it. |
| B.6 | confirmed | |
| C | confirmed | `tests/test_visibility.py` asserts the other user's name is nowhere in a self-tier response. |
| D | **refuted** | Not covered: the `forbidden` refusal branch of the Users tab, cluster-switch invalidation of `data.users`, and that other tabs never request `/users`. The IME tests wait fixed 100 ms between composition steps, which is timing-sensitive; that pattern predates this change. |
| E | confirmed | No dangling screenshot reference; the self-tier Users image is deliberately absent and unreferenced. |

## What changed because of it

- The Users heading now counts what is painted (`rows.length < all.length ? "N of M shown"`), so it
  is true whether the search or the paint cap narrowed the list; the notes beneath say which. The
  paint-cap test now asserts the heading as well as the row count.
- Three tests added to `tests/test_ui.py#TestUserSearch`: a refused list renders the named refusal
  and no rows; a cluster switch drops `data.users`; Groups, Overview and Access granted never
  request `/users`, and the Users tab does.

Not changed: the fixed 100 ms waits in the IME tests. They are the established pattern from the
group-search review and have not been seen to flake; replacing them with a condition to wait on is
a separate change to both suites.

## What the deployed build showed

Before the review, the branch was built and deployed to CRC with `release-crc.sh` and driven
through the real OAuth login with Playwright: 11 users listed, `cooper` narrowed to `alice.cooper`,
`bob wil` to `bob.wilson`, a drill from Users came back under Users with "← all users", and a
group's members narrowed by id with the header reading "1 of 2 shown". No JavaScript errors on any
page. The heading defect above was not visible there: 11 users are far below the paint cap.

## The Cursor pass, after merge

Same brief, run against `git diff 4892172^1 4892172` with the heading-count fix already in. Every
claim confirmed, including that fix; two findings:

| Finding | Severity | Outcome |
|---|---|---|
| A pasted hash carrying `page=users` and a group name fetched the group, which the Users tab never paints, so the tab showed "Loading…" for good. No tab builds that pair; `positionFromHash` accepts it. | low | Fixed: `index.html#async function refresh` now tests the position in the order `render` dispatches it — user, then the Users list, then a group, then the group list — with a test that pastes the pair. |
| The IME tests and one fetch-absence test wait on fixed timers (100 ms, 400 ms). | low, accepted | The IME pattern predates this feature and is shared with the group-search suite; replacing it with a condition to wait on is a change to both suites and was left as is. |

Coverage it named as still missing, both added in the same fix: a test that a changed user list
repaints on the auto-refresh (the fingerprint includes `data.users`), and the fetch-gate test now
walks every other tab, not just Groups, Overview and Access granted.
