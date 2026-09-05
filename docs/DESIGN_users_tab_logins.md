# Design — the Users tab counts people who have logged in

**Status:** implemented in application 0.9.0 / chart 0.9.0 (the PR that follows #46). The three open
questions were closed in application 0.15.0 / chart 0.16.0 (feature C2,
`docs/specs/SPEC_C2_users_tab_providers_identities.md`) — see "Decisions after 0.9.0" at the end.

The 0.9.0 decisions were: provider chips rather than an allow-list; the `User` creation time
accepted as first login and labelled "since"; the never-logged-in line stays on the Users tab, with
the names one click away. The default view is every `User`, with chips to narrow.

**The operator's framing, which this document takes as the premise (2026-09-03):** the users that
count are the ones who have actually logged in to OpenShift. Group sync is a separate fact and stays
as it is — it puts every LDAP member of a synced group into the OpenShift `Group`, logged in or not,
and that is correct. The Users tab, and only the Users tab, should answer "how many people have
logged in to this cluster, and who", from OpenShift's own `User` objects.

## Why the `User` object is the right source

OpenShift creates a `users.user.openshift.io` object at a person's first login through an identity
provider, and not before. Membership in a synced group creates nothing. The object carries:

- `metadata.creationTimestamp` — the first login, for a user the identity provider created;
- `identities[]` — `provider:id` strings, one per provider the person has logged in through; an
  **empty** list means the object was created by hand (`oc create user`) and nobody has logged in as it;
- `fullName` — set by the provider when its attribute mapping supplies one;
- `groups[]` — legacy, empty on every object measured; group membership lives on `Group` objects.

There is no last-login field. The login-capture feature (`docs/DESIGN_login_capture.md`, table
`gsd/store.py#login_event`) supplies that, for the window since capture was enabled.

## Measured on CRC, 2026-09-03

| Population | Count |
|---|---|
| distinct members of synced groups | 11 |
| of those, with a `User` object (have logged in) | 8 |
| of those, never logged in | 3 — `bob.wilson`, `charlie.brown`, `hello1` |
| `User` objects in total | 62 |
| with at least one identity | 61 |
| with no identity (manual account, never logged in) | 1 — `test-python-user` |
| `User` objects in no synced group | 54 — `kubeadmin`, `developer`, 49 `ceo_rnd_oim` test accounts, the manual one |

Identity providers seen on `User.identities`: `ldap-local` 8, `ceo_rnd_oim` 49, `developer` 2,
`my-provider` 2. `fullName` is set on the 8 LDAP users and on none of the others.

## What the tab did before 0.9.0, and why that was a different question

Rows came from `gsd/store.py#group_member`, filled by `gsd/poller.py#poll_once` from the `Group`
objects' member lists. The `User` read (`gsd/kube.py#ClusterClient.fetch_users`) was a decoration:
it stored only `fullName`, only for names that were set, into `gsd/store.py#ocp_user`, and
`gsd/store.py#Store.users` LEFT JOINed it. So the tab answered "who has access through synced
groups". `docs/REVIEW_user_search.md` locked that shape in when PR #42 shipped it; this document
changed the question the tab answers, deliberately, and says so. (Written in the present tense
before implementation; both second-pass reviewers read it as a description of the current tab.)

The RBAC is already in place: `charts/group-sync-dashboard/templates/rbac.yaml#rbac.users` grants
`get`/`list` on `users.user.openshift.io`, on by default. `identities` is not granted and this
design does not need it: the provider is the prefix of each `identities[]` entry on the `User`.

## The design

### Rows

A row per `User` object on the cluster. Group membership is an attribute of the row (a count, and
the names on the detail page), not the reason the row exists. Synced members with no `User` object
are **not rows**: they have not logged in. They are reported once, under the headline, as
"N synced members have never logged in", expanding to the names — a review fact worth one line,
and they remain fully visible on their group pages and in the access views, which do not change.

### Columns

| Column | Source | Notes |
|---|---|---|
| User | `User.metadata.name` · `fullName` | id first; the id is what an operator matches against `oc` |
| Status | `identities[]`, `creationTimestamp` | "logged in since {first login}" when identities is non-empty; "manual account, never logged in" when empty |
| Provider | `identities[]` prefixes | one or more; a filter chip per provider |
| Groups | `group_member` count for the id | 0 allowed and highlighted: logged in, no synced access |
| Last login | `login_event` max successful `at` for the id | "capture off" when login capture is disabled; "none captured" when on but nothing seen |
| First seen | `group_member` `MIN(first_seen_at)` | kept for continuity with today's tab; null for a user in no group |

Headline: four counts — **have logged in** (Users with an identity; a manual account is listed
below but is not a login and is said so in a note), in a synced group, logged in with no synced
group, and synced members who have never logged in — with the never-logged-in-members line under
them, expanding to the names. Filter chips: all · in a synced group · no synced group · one per
provider. The never-logged-in members are not a chip, because they are not rows; the line is theirs.
The free-text filter over id and full name stays as it is (`gsd/static/index.html#usersPage`,
`matchesSearch`).

### Storage

`ocp_user` becomes a record of every `User`, not of names that happen to be set:

```sql
ocp_user(cluster_id, user_name, full_name NULL, created_at, providers TEXT, has_identity INTEGER,
         observed_at, PRIMARY KEY(cluster_id, user_name))
```

One migration (the next number after the current last entry in `gsd/store.py#_MIGRATIONS`),
rebuilding the table; the current contents are a strict subset of the new ones and are refetched
on the next poll, so no data is worth migrating. `gsd/store.py#Store.replace_users` takes full
records. `gsd/store.py#Store.users` is rewritten: base table `ocp_user`, LEFT JOIN a grouped
`group_member` for the count and first-seen, LEFT JOIN a grouped `login_event` for the last success.
A second query, `synced_members_without_user`, produces the never-logged-in line. The storage
protocol in `gsd/storage.py` moves in step — `tests/test_storage_seam.py` enforces parity.

### The `User` read stops being optional by construction

`gsd/kube.py#ClusterClient.fetch_users` returns whole records. The 403 tolerance stays — an image
upgraded without the chart's RBAC must not fail the poll — but its meaning changes from "names go
stale" to "the tab has no rows", so it is surfaced: `gsd/poller.py#poll_once` records the refusal
in `ocp_user_status` (`Store.mark_users_unavailable`), `/users` returns `source: "forbidden"` with
`source_observed_at`, and the tab shows a banner naming the grant instead of an empty list, and the
age of the last successful read. A poll that fails before reaching the users read leaves the status
as it was — the Overview's poll status is the freshness channel for the cluster as a whole, and the
tab shows when its own source was last read. `charts/group-sync-dashboard/values.yaml`'s
`rbac.users` comment, the README row, and `docs/reference-architecture.md`'s "one field" paragraph
all currently say the read buys display names only, and all three change. The chart test
`tests/test_chart_strategy.py#TestTheUsersGrantIsReadOnlyAndOptional` keeps the grant read-only and
switchable; its docstring's "lose display names and keep the dashboard" becomes "lose the Users
tab's rows and keep the dashboard".

### API

`GET /api/clusters/{id}/users` (`gsd/api.py#list_users`) keeps `cluster`, `scope`, `viewer`,
`limit`, `truncated`. Each row gains `logged_in`, `first_login_at`, `providers`, `last_login_at`,
and `group_count` may now be 0. The envelope gains `login_capture` (`on`/`off`, top level),
`source` and `source_observed_at`, `total` (every User under the scope), `logged_in_total` (those
with an identity — the headline), `offset`, and `never_logged_in_members: {count, names}`. `total`
and `offset` are what `docs/api-contract.md` rule R3 has required all along and this endpoint never
had: a cluster's User count is every person who has ever logged in, so the API pages. The only
consumer today is the UI (`gsd/static/index.html#usersPage`); `cluster-report.py` does not read
`/users`.

`GET /api/clusters/{id}/users/{name}` (`gsd/api.py#user_detail`) gains the same per-user fields and
keeps its 404 rule, extended: a name with a `User` object is never 404 even with no groups.

### Tiering

Unchanged in principle: `gsd/api.py#viewer_scope` narrows a plain reader to their own row. The
self-tier predicate must apply to **both** base tables (the `User` row and the members line), so a
narrowed reader cannot learn another person's login status or that a named member has never logged
in. `docs/REQUIREMENTS_per_user_visibility.md` already records that a plain user cannot list
`users.user.openshift.io`, which is exactly why the wide view is gated.

### Privacy

The tab is behind the OAuth proxy and tiered. `/metrics` is unauthenticated by decision
(`gsd/metrics.py` removed `gsd_dashboard_active_users` for that reason), so **no gauge** of
logged-in users is added; the count lives only on the authenticated page.

### Scale

One `list users` call per poll cycle, already made today. Thousands of `User` objects on a real
cluster is the expected shape and the reason the API pages. Decided at implementation: the UI keeps
its single fetch at the server's maximum (`USERS_FETCH`, 10,000) with the existing truncation note,
because the chips and the Find box work over what is loaded and a paged loop would make them lie
about the denominator; a cluster past that cap gets the honest note, and an API consumer pages.

## Two incidental defects to fix in the same change

- `gsd/store.py#Store.login_without_access` was defined twice; Python kept the second, the first
  (with the documented rationale) was dead. Fixed first, on its own, in PR #46.
- `/users` violates R3 (`total`, `offset`), as above.

## What this does not change

Group sync, the `Group` read, group pages and member lists, the access views (`access_without_login`,
`login_without_access`), login capture, the OAuth proxy, tiering rules, `/metrics`.

## Open questions for the reviewer

1. Should the `ceo_rnd_oim`-style test accounts be filterable out by provider only, or is a
   configurable provider allow-list wanted so a production tab shows one directory's people?
2. `first_login_at` from `User.creationTimestamp` is exact for provider-created users. A user
   pre-created by an admin and later linked to an identity has a creation time before their first
   login; `Identity.metadata.creationTimestamp` would be exact but needs the `identities` grant.
   Proposed: accept the `User` timestamp, label it "since", and note the edge; revisit only if a
   real cluster has admin-created users in numbers.
3. Whether the never-logged-in members line belongs on the Users tab or on the cluster-access
   panel, which already reasons about access without login.

## Verification plan

- Store: a fixture with a `User` in no group, a group member with no `User`, a manual account with
  no identities, a user with two providers; assert rows, counts, the members line, and the
  self-tier predicate on both tables.
- Poller: the 403 path surfaces in health and in `/users` `source`, and leaves last cycle's rows.
- API: R3 fields; ordering on the id; `limit + 1` truncation; the detail 404 rule.
- UI: chips, headline, the three empty states, the banner when the grant is missing.
- Chart: the grant stays `get`/`list` and switchable; the README table row matches.
- Live: CRC after a poll shows 62 rows, 8 with a group count above zero, the members line naming
  the three, and `lateef.o` at the self tier seeing exactly one row.

## Decisions after 0.9.0 (C2, application 0.15.0 / chart 0.16.0)

The open questions above were closed as follows, each with the code that carries the decision.

1. **Chips or an allow-list?** Both. The provider chips stay, and `config.users.providers` (empty by
   default, meaning every provider) narrows the tab to the named identity providers at READ time
   (`gsd/config.py#_providers_setting` validates the names at startup; `gsd/store.py#Store.users` and
   `count_users` apply the list through SQLite's `json_each` on the stored provider list). The wire
   says so in `providers_filter`, and the page says "Showing providers: …". The never-logged-in line
   is not narrowed: a member who logged in through an excluded provider has logged in. Manual accounts
   with no identity drop out under any list.
2. **Which time is the first login?** The Identity object's creation time when the chart grants
   `rbac.identities` (`gsd/kube.py#ClusterClient.fetch_identities` reads them paged, keeps the earliest
   per User, skips an Identity naming no User, and returns None on a 403). Otherwise the User's
   creation time, labelled approximate: `gsd/store.py#Store._user_row` sets `first_login_source` to
   `identity` or `user`, the page shows an `identity` or `approx.` chip, and `identities_source` on the
   wire says why (`ok`, `forbidden`, `off`, `pending`). The Identity time is not called "exact"
   (review of C2, Codex): with `mappingMethod: claim` or `add` OpenShift creates the Identity at the
   first login, so it is; with `mappingMethod: lookup` an administrator creates the Identity before
   the first login, so there it is the mapping's creation, the same caveat as a pre-created User —
   and the page states it. Identity times are compared as instants: metav1.Time marshals fixed-width
   RFC3339 seconds today, so the string minimum was not wrong, but the instant is the operation meant
   and holds at any width (Cursor's mixed-width premise was refuted by Codex at the apimachinery
   source; the comparison stayed). A transient failure of the Identity read keeps the last-known
   Identity times rather than downgrading every row to the User time while the status still says
   `ok`; a User who appears during such a cycle carries the User time and its chip until the next
   successful read, and the tab's note describes the source per row rather than asserting one for
   all.
3. **Where does the never-logged-in line live?** On the Users tab, unchanged and unnarrowed.
