# API reference

Every endpoint is **read-only**. None returns a token, none accepts one from the browser, and
none mutates cluster state the dashboard reports on (§9, §11) — the ServiceAccount holds no
write verb on anything.

FastAPI serves interactive docs from the running instance, generated from the code rather
than from this file, so they cannot drift:

| | |
|---|---|
| `/docs` | Swagger UI — try requests against the live instance |
| `/redoc` | ReDoc |
| `/openapi.json` | the raw schema, for client generation |

This document adds the part a schema cannot express: what each field *means*, and which ones
are routinely misread.

## Who sees what

Responses are **scoped to the reader**. Every collection endpoint carries two fields saying whose
view you are looking at:

| field | values | meaning |
|---|---|---|
| `scope` | `"all"` \| `"self"` | whether these rows are the whole cluster or only the reader's own |
| `viewer` | the username, or `null` | who the server decided you are |

`self` means the rows are filtered to the reader's own groups, memberships and access. `all` means
nothing was filtered. There is no third value.

**Read `scope` before you read a count.** An empty list under `scope: "self"` means *nothing here
belongs to you*; the same empty list under `scope: "all"` means *nothing here exists*. Those are
different facts and the dashboard states them differently. A client that ignores `scope` will
report a clean cluster to a reader who simply is not an administrator.

**Aggregates that cannot honestly be computed are `null`, never `0`.** At `self` scope the
cluster-wide rollups — `summary`, `ungoverned`, `access_without_login`, `login_without_access`,
`in_access_group` — are withheld as `null`. A fabricated zero would read as "no problems found"
when the truth is "not counted for you".

How the scope is chosen:

- With the oauth-proxy **off** there is no trusted identity to scope to, so `scope` is `"all"`,
  `viewer` is `null`, and the app says so loudly at startup. This is the pre-existing behaviour of
  a proxy-less install and is preserved deliberately.
- With the proxy **on**, a SubjectAccessReview decides. It is posted with both `spec.user` and
  `spec.groups`, because a reader granted cluster-admin through a Group rather than a direct
  binding is refused when `spec.groups` is absent.
- The decision is cached per viewer for 60 seconds. A **failure is never cached**, so an API-server
  outage does not pin every reader to the narrow view until a TTL expires.
- Anything indeterminate serves `self`. The log line names the reader, the cause and the decision:
  `visibility tier for 'alice' is indeterminate (auth_failed: …) — failing closed to the self view
  for this request`.

**One endpoint has a SECOND, STRICTER threshold: `/api/dashboard/activity` (the Usage tab).** Every
other view above can be reproduced with `oc` by anyone holding the roles that pass the wide check —
groups, bindings, even the oauth-server logs behind Logins. Usage cannot: it is who-opened-this-
dashboard data, living only in the dashboard's own database. So it does NOT follow the wide tier that
`cluster-reader` (the auditor persona) also passes. Its `scope` is `all` only when
`config.userActivity.visibility: all` is set (the blunt override, which always wins) OR a SEPARATE
SubjectAccessReview — `visibility.usageAdminSar`, default `update clusterrolebindings`, a write verb
`cluster-reader` fails and `cluster-admin` passes — allows this reader. The two tiers are independent
and cached separately: a client will see `cluster-reader` come back `scope: all` on `/groups` and
`scope: self` on `/api/dashboard/activity` in the same session. The dashboard still writes nothing; a
SubjectAccessReview only asks whether a subject could. See docs/SPEC_usage_admin_tier.md.

`GET /api/whoami` reports the same decision as a nested object rather than top-level fields:
`"visibility": {"scope": "self", "enabled": true}`. `enabled` is the operator's switch
(`GSD_ENABLE_VIEW_RESTRICTIONS`), not the outcome for this reader.

**`groupsyncs` is served at both tiers minus two fields at `self`; only its events do not vary
at all.** The criterion is measurable, not "is it about objects": `/metrics` is unauthenticated
(chart `skipAuthRegex`) and already publishes `gsd_groupsync_state`,
`gsd_groupsync_last_sync_timestamp_seconds` and `gsd_groupsync_groups_total` per CR to a
credential-less `curl`, so refusing the same per-CR identity behind login would be theatre. What
`/metrics` deliberately never carries is directory detail — so at the self tier the row omits
`ldap_filter` and `error_message`, both of which can embed directory DNs and the gate group.
Administrators receive the full row, unchanged.

**`bindings/findings`, `operator-configs`, `kyverno` and `kpi` are the administrator tier** (`403` at self). The
Access granted tab at the narrowed tier reads the reader's own path instead — `/users/{name}`
for their own name, whose `bindings` carry `via_group` — which the gate never withheld.
They describe objects too, but that is not the test. A binding row names which *group* holds
which *role* — the cluster's RBAC binding surface — which on the reference cluster an ordinary
reader who could not `oc list` clusterrolebindings/rolebindings/groups was handed anyway (236
rows, 21 naming an admin role): obtainable through the dashboard and not with `oc`, a privilege
escalation. Neither has a `/metrics` analogue that would make gating theatre (`operator-configs`
in particular is genuinely private), so the criterion above puts them *behind* the tier. This
reverses an earlier ruling that served all four at both tiers; see
`docs/SPEC_per_user_visibility.md` (Q3) and `docs/REQUIREMENTS_per_user_visibility.md` (§6 Q3).

`/api/clusters` stays reachable at every tier — the cluster selector reads it on every tab —
and every count on it is a public `/metrics` figure except the `operator_configs` summary,
which has no `/metrics` analogue and is therefore the one field withheld (as `null`) at self.

The administrator equality still holds where it always did: an administrator's response with
restrictions on is byte-identical to the same request with them off, per endpoint (DoD #2).

## Clusters

### `GET /api/clusters`

One entry per configured cluster.

```json
[{
  "id": "crc-local",
  "api_url": "https://kubernetes.default.svc",
  "enabled": true,
  "reachable": true,
  "status": "ok",
  "last_poll": "2026-08-02T00:14:32Z",
  "error": null,
  "groupsync_count": 2,
  "groupsync_operator_present": true,
  "group_count": 62,
  "empty_groups": 0,
  "unattributed_groups": 0,
  "oldest_last_sync": "2026-08-02T00:00:11Z",
  "dangling_bindings": 0,
  "unresolved_bindings": 9,
  "builtin_bindings": 145
}]
```

`reachable` is **`null`, not `false`, when the cluster has never been polled.** A
never-polled cluster and an unreachable one are different states, and rendering the first as
`false` would report a failure that has not happened.

`status` distinguishes `ok` / `auth_failed` / `forbidden` / `unreachable`. `forbidden`
matters most: a ServiceAccount that can list GroupSyncs but not Groups produces a
half-populated view that otherwise looks exactly like a cluster with no groups.

## GroupSync CRs

### `GET /api/clusters/{cluster_id}/groupsyncs`

```json
[{
  "name": "ldap-groupsync",
  "namespace": "group-sync-operator",
  "schedule": "*/30 * * * *",
  "ldap_filter": "(&(objectClass=groupOfNames)(cn=app-ocp-rbac-*))",
  "last_sync_at": "2026-08-02T00:00:11Z",
  "generation": 2,
  "group_count": 41,
  "state": "ok",
  "next_expected": "2026-08-02T00:30:00Z",
  "interval_seconds": 1800,
  "schedule_valid": true,
  "error_at": "2026-07-30T15:16:17Z",
  "error_message": "failed calling webhook …",
  "error_is_current": false
}]
```

**At the self tier the row omits `ldap_filter` and `error_message`.** Both can embed directory
DNs and the gate group — an LDAP filter names the groups it selects, and a bind failure's text
names the service DN — and a reader below the wide tier cannot `oc get` the CR to read them
anyway. The keys are absent, not `null`; every other field above is present, and the response
stays the bare list. The projection is an allowlist (`gsd/api.py#SELF_TIER_GROUPSYNC_FIELDS`),
so a field added later is withheld at `self` until it is explicitly ruled on. Administrators
always receive the full row, byte-for-byte.

**`error_is_current` is the field to read, not `error_at`.** The operator never clears
`ReconcileError` on a later success, so a perfectly healthy CR carries a months-old error
indefinitely. `error_at` alone would paint it permanently red; `error_is_current` compares
the error's transition time against the success's (§2.1).

`state` is computed on read, never stored:

```text
ok        age <= 1 interval + grace
late      age >  1 interval + grace
overdue   age >  2 intervals + grace
unknown   unreachable, never synced, or an unparseable schedule
```

`grace` (default 120s) exists because the literal thresholds flap: a sync lands 3–14s after
its cron minute and is observed up to a poll interval later, so a healthy CR exceeds one
interval for ~70s of *every* cycle.

`unknown` is not a synonym for healthy. A CR with an unparseable schedule sits in `unknown`
forever, so `/api/alerts` reports `invalid_schedule` and `sync_stopped` separately — without
those, a CR that stopped syncing days ago would be entirely silent.

`next_expected` comes from a real cron parser. `0 * * * *` and `*/30 * * * *` both look
hourly if you only measure gaps between events; they differ only at `:30`.

### `GET /api/clusters/{cluster_id}/groupsyncs/{name}/events`

Query: `since` (RFC3339), `limit` (1–2000, default 200).

The accumulated sync timeline. `synced_at` is the operator's timestamp; `observed_at` is
ours, and the difference is **our** polling lag, not the operator's. Conflating them would
blame the operator for our latency.

**An empty list means this dashboard has not seen a sync yet** — not that the operator never
synced. The API keeps no history, so the timeline only covers the period since the dashboard
started (§2). The response says so in a `note` field.

Since 0.13.0 the response also carries `retention: {"window_days": N, "retained_since": "…Z"|null}`
for `sync_event`. `window_days` is the configured window (`0` = kept forever) and `retained_since`
is the oldest observation still held on this cluster — a timeline that begins there was cut
there by retention, which is a different fact from "the dashboard started there".

## Namespaces

### `GET /api/clusters/{cluster_id}/namespaces`

Every namespace the poller sees on the cluster, with its configured labels (`namespaceMetadataLabels`)
and two counts — distinct groups of people bound in it (a virtual `system:` group is on the page, badged, not in
the count), and non-platform grants naming a person there (#167).
Cluster-wide bindings reach every namespace and are counted once, on the envelope.

```json
{
  "cluster": "crc-local", "scope": "all", "viewer": "kubeadmin",
  "source": {"state": "ok", "observed_at": "2026-09-18T05:12:06Z"},
  "label_keys": ["company.net/mnemonic", "company.net/app-environment", "company.net/oud-group"],
  "count": 110, "cluster_wide_groups": 3, "cluster_wide_grants": 0, "cluster_wide_path": true,
  "namespaces": [
    {"name": "demo-prod", "created_at": "2026-08-02T04:00:11Z", "phase": "Active",
     "observed_at": "2026-09-18T05:12:06Z",
     "labels": {"company.net/mnemonic": "demo", "company.net/app-environment": "prod"},
     "via_groups": 2, "direct_grants": 0}
  ]
}
```

`source.state` is `forbidden` when the chart did not grant the namespace read — a refused read cannot
attest absence, and the page says so rather than showing an empty list as a clean one. A namespace with
zero in both counts is a result an access review wants to confirm, not an absence.

`cluster_wide_groups` counts distinct groups (a group with two ClusterRoleBindings is one group, as the
`via_groups` column counts) and `cluster_wide_grants` the non-platform bindings naming a person, as the
`direct_grants` column counts.

`cluster_wide_path` is the reach itself: true when any cluster-wide binding names the viewer — unlike the
two counts, a platform identity's binding included.

Self tier: only the namespaces the viewer's own memberships or own bindings reach, counted over those
paths; `cluster_wide_*` count the viewer's **own** cluster-wide paths, and when `cluster_wide_path` is true
every namespace is listed — a cluster-wide grant reaches every one, which is also what the detail answers.

### `GET /api/clusters/{cluster_id}/namespaces/{name}`

One namespace: who reaches it and through which group, the grants naming a person there, the
cluster-wide grants that reach it too, its siblings under the first configured label (the mnemonic),
how many distinct people the paths add up to, and its history of binding changes.

```json
{
  "cluster": "crc-local", "scope": "all", "viewer": "kubeadmin",
  "name": "demo-prod", "present": true, "created_at": "…", "phase": "Active", "observed_at": "…",
  "label_keys": ["company.net/mnemonic", "company.net/app-environment", "company.net/oud-group"],
  "labels": {"company.net/mnemonic": "demo", "company.net/app-environment": "prod"},
  "via_groups": [{"group_name": "app-ocp-rbac-demo-ns-developer", "binding_kind": "RoleBinding",
                  "binding_name": "demo-devs", "role_kind": "ClusterRole", "role_name": "edit",
                  "managed_source": "baseline-nonprod-rbac", "member_count": 4, "is_platform": 0}],
  "cluster_wide_groups": [{"group_name": "platform-team-cluster-admin", "role_name": "cluster-admin", "…": "…"}],
  "direct_grants": [{"user_name": "jane.smith", "binding_kind": "RoleBinding", "binding_name": "jane-edit",
                     "role_kind": "ClusterRole", "role_name": "edit", "is_platform": 0}],
  "cluster_wide_grants": [{"user_name": "ops.oncall", "binding_kind": "ClusterRoleBinding", "binding_name": "oncall-view",
                           "role_kind": "ClusterRole", "role_name": "view", "is_platform": 0}],
  "people": 7, "sibling_key": "company.net/mnemonic", "siblings": ["demo-qa", "demo-uat"],
  "changes": [{"…": "the binding_event rows for this namespace, newest first"}],
  "retention": {"window_days": 0, "retained_since": "2026-09-18T02:57:18Z"}
}
```

Every `via_groups` and `cluster_wide_groups` row carries `is_platform`: 1 for a virtual `system:` group
(`system:authenticated`, `system:nodes`, `system:serviceaccounts:<ns>` — access with no person behind it),
sorted after the real groups; the list's `via_groups` column and `cluster_wide_groups` count leave them out, as
the person counts leave platform identities out. A platform row's default binding wears no `hand-made` badge:
the findings tier it `built_in`, never `unmanaged`.

`cluster_wide_groups` and `cluster_wide_grants` are the ClusterRoleBindings — naming a group, naming a person —
that reach this namespace along with every other; `direct_grants` are the bindings *in* the namespace only, and
`people` counts the members of the via and cluster-wide groups plus every non-platform person named either way.

`present` is `false` for a namespace the store no longer holds but that bindings or history still name —
a removed namespace's link is a detour, not a dead end; 404 only when nothing at all names it.

Self tier: refused **before** any lookup unless one of the viewer's own paths reaches the namespace, so the
403 for a namespace outside their view and for one that does not exist are byte-identical; then the
viewer's own paths only, and `people` is `null` (a count over other people's memberships).

## Groups

### `GET /api/clusters/{cluster_id}/groups`

Returns an **object**, not a bare array — the rows plus the scope they were selected under:

```json
{"cluster": "crc-local", "count": 41, "scope": "all", "viewer": null, "groups": [...]}
```

This changed when per-user visibility landed; it used to return the array alone. Read
`response.json()["groups"]`. Two ways an old client breaks, and the quiet one is worse:

```python
body = r.json()
len(body)                    # 5 — the number of KEYS, not rows. Silently plausible.
for g in body: g["name"]     # TypeError: string indices must be integers, not 'str'
```

The `TypeError` announces itself. `len()` does not: it returns 5 on a cluster with 41 groups and 5
on a cluster with none, so a caller that only counts reports a number that is never right and never
obviously wrong. Use `count`, which is the row count under the current scope.

Query: `state` = `all` (default) | `empty` | `unattributed`.

Each row also carries `cliff_silence` — the raw value of the Group annotation
`groupsync-dashboard.io/silence-group-count-cliff`, or `null` (application 0.12.0) — and
`binding_count`, how many RoleBindings and ClusterRoleBindings name the group on this cluster: the
same number the group's own detail lists under `bindings`, on every tier and under every `state`
filter (#174, the Grants column of the list and the lookup).

The two filters **overlap, deliberately**. `empty` means *zero members* for any group,
whatever created it; `unattributed` means *no GroupSync CR claims it*. A hand-made group with no
members is both, and is returned by both.

`empty` was previously scoped to operator-synced groups only, on the reading that EMPTY means
"synced, then lost its members" — an LDAP-side fault. That made the filter useless on the cluster
that most needs it: with no group-sync-operator installed every group is unattributed, so `empty`
matched nothing however many groups granted nobody.

They are two questions rather than a partition — "which groups grant nobody?" and "which groups
is no CR managing?" — so do not add them together. `empty_groups` and `unattributed_groups` on
`/api/clusters` are counted with the same predicates and can likewise overlap.

The ALERT stream is unchanged and still reports each group once: a hand-made empty group raises
`unattributed`, not `empty_group`, because that alert's remedy names the LDAP side and there is no
LDAP side for a group somebody created by hand.

### `GET /api/clusters/{cluster_id}/groups/{name}`

Adds `members`, `changes`, `bindings` and, since 0.13.0, `retention` (the `membership_event` window and edge — same shape as on `/membership-changes`).

Each member carries two dates:

* `first_seen_at` — start of the current unbroken membership
* `original_first_seen_at` — the first time we ever saw them in this group

They differ when a user left and rejoined. Showing only the first would tell an auditor that
access is newer than it is.

**A deleted group returns 200, not 404**, when history exists for it. "This group is gone,
here is who was in it" is the answer to that click; 404 strands the reader. `deleted: true`
marks it.

## Users

### `GET /api/clusters/{cluster_id}/users`

Everyone who has logged in to the cluster: one row per OpenShift `User` object, which the cluster
creates at a person's first login through an identity provider and never before — so the row is
the fact of a login, and the headline count is how many people have used the cluster. Group
membership is an attribute of a row, not the reason it exists (`docs/DESIGN_users_tab_logins.md`).
**Bounded and paged.**

| parameter | default | meaning |
|---|---|---|
| `limit` | `1000` (max 10000) | rows on this page; `truncated` says whether more exist, `total` is the whole set |
| `offset` | `0` | rows to skip, for paging |

```json
{"cluster": "crc", "scope": "all", "viewer": "kubeadmin",
 "source": "ok", "source_observed_at": "2026-09-03T17:52:38Z", "login_capture": "on",
 "providers_filter": [], "identities_source": "off", "identities_source_observed_at": null,
 "total": 62, "logged_in_total": 61, "offset": 0, "limit": 1000, "count": 62, "truncated": false,
 "never_logged_in_members": {"count": 3, "names": ["bob.wilson", "charlie.brown", "hello1"]},
 "users": [{"user_name": "alice.cooper", "full_name": "Alice Cooper",
            "logged_in": true, "first_login_at": "2026-08-05T16:14:16Z", "first_login_source": "user",
            "providers": ["ldap-local"],
            "last_login_at": null, "created_at": "2026-08-05T16:14:16Z",
            "group_count": 7, "first_seen_at": "2026-08-05T16:20:01Z"}, ...]}
```

Per row: `logged_in` is false only for a `User` created by hand (`oc create user`) with no identity,
which is listed but is not a login; `first_login_at` is the Identity object's creation time when
`first_login_source` is `identity` (the chart's `rbac.identities` read), otherwise the User object's
creation time (`user`), and `null` for a manual account; the envelope's `identities_source` says why
(`ok` | `forbidden` | `off` | `pending`) and `providers_filter` names the identity providers
`config.users.providers` narrowed the list, `total` and `logged_in_total` to (`[]` = all; the
never-logged-in line is never narrowed); `providers` are the identity-provider names from the object's `identities`;
`last_login_at` is the newest **successful** captured login, `null` when none — read `login_capture`
before trusting the null, since nothing before capture began was ever recorded; `group_count` may be
0 (logged in, no synced access); `first_seen_at` is when the dashboard first saw them in any group,
`null` for a user in none; `full_name` is `null` when the provider supplied no name.

Envelope: `total` is every `User` under the scope and `logged_in_total` those with an identity — the
headline; they differ by the manual accounts. `never_logged_in_members` are members of synced groups
with no `User` object: not rows, reported once. `source` is `ok`, `forbidden` (the chart's
`rbac.users` grant is missing, so the rows are stale or absent and the tab says so by name) or
`pending` (no poll has read users yet); `source_observed_at` is when the source was last read.

**Self-scoped** under view restrictions: a plain reader gets their own row or an empty list, and
`never_logged_in_members` is scoped the same way, so nothing about anyone else is on the wire.


### `GET /api/clusters/{cluster_id}/users/{name}`

The reverse lookup: every group the user is in, every binding that reaches them, and their
membership history. Each binding row carries `via_group`, because "why do they have this?"
is the next question after "do they have it". Since 0.9.0 it also carries the login facts a row of
`/users` has — `logged_in`, `first_login_at`, `last_login_at`, `providers`, `login_capture` — so the
detail page and the list cannot disagree. Since 0.13.0 it carries `retention` for `membership_event`, the
same shape as on `/membership-changes`.

**A user with no current groups returns 200, not 404**, if any history exists or a `User` object
does: "they are in nothing now" is the answer, and a person who logged in and holds no synced access
is a finding, not an error. 404 only when the name has been seen nowhere. At the narrowed tier only
the reader's own name is served, and the refusal for any other name comes before any lookup.

### `GET /api/clusters/{cluster_id}/logins`

Login attempts against this cluster's oauth-server: who, when, and why a failure failed. Read from the
oauth-server pod log, which names the person only at `spec.logLevel: Debug` on the authentication
**operator** CR (`authentications.operator.openshift.io/cluster` — not the OAuth CR).

| parameter | default | meaning |
|---|---|---|
| `outcome` | all | one of the parser's outcomes: `success`, `bad_password`, `rejected`, `password_expired`, `must_change_password`, `account_locked`, `account_disabled`, `account_expired`, `logon_not_permitted`, `failed` |
| `user` | all | the username as **typed**, which may match no `User` object and no group member — that mismatch is a finding, not an error |
| `limit` | `200` | attempts returned, newest first. `truncated` reports whether older ones were dropped; `total` and `summary` always describe the whole retained record, never the page |

**`rejected` — shown as "no match" — covers two different things and cannot separate them.** The identity provider's search
filter carries the login-gate group, so a real person who is not in that group and a username that does
not exist produce the same `no entries matching` line. Telling them apart would need a directory read
this application does not have.

**The record is a WINDOW, and both edges are carried as data:**

| field | meaning |
|---|---|
| `capture_started_at` | when watching began. Stable — set once by the first successful read. May be *later* than `retained_since`, because the first read looks back an hour |
| `retained_since` | the oldest attempt still kept. Moves as retention ages rows out |
| `last_read_at` | liveness. If this stops advancing, capture has stopped |
| `read_interval_seconds` | how often `last_read_at` is *expected* to advance — capture rides the poll thread, so this is the poll interval. Sent because the browser is the only place that can judge whether a read is overdue and the only place that knows what a reader is looking at, but it has no way to learn the cadence: a threshold hardcoded in the page would call a 900s poll stalled every cycle |

Nothing before capture began exists to fetch — the log dies with its pod — so **an empty `attempts` is a
statement about the window, never proof that nobody logged in.**

Every username is recorded, successful or not, member or not. Per attempt: `known_user` false marks an
account in **no synced group**, which is the most valuable row here; `has_history` true separates
"access removed and still trying" from "nobody ever governed this name"; `break_glass` marks a success
on an HTPasswd provider (`kubeadmin`, `developer`), which is not a person to offboard. `ungoverned`
lists the no-synced-group accounts separately, bounded at 50, so a paged chronology cannot bury them —
with `summary.ungoverned_users` beside it as the whole-set count from the same store predicate.

Each attempt also carries **`in_access_group`**: `true`/`false` when a login gate is known, and
**`null` when it is not** — "we cannot tell", which is a different statement from "not a member". With
a gate known, `in_access_group: false` on somebody who *is* in a synced group turns `no match` from
"not found **or** not permitted" into **a real person, not gated**.

That conclusion is served as **`refusal_reason`**, so every consumer draws it the same way rather than
each reimplementing the rule. It is set only on `rejected` — an outcome that already carries its own
cause must not acquire a competing one — and is `null` whenever the question cannot be answered:

| `refusal_reason` | meaning |
|---|---|
| `not_gated` | **a real person, outside the gate group.** In at least one synced group, so the directory knows them and this cluster governs them, and not in the gate group. The refusal is the gate working; the finding is the access they cannot use |
| `no_record` | no synced group and no membership history for this name. Consistent with a typo, a probe, or a directory branch this cluster does not sync. Deliberately **not** called "unknown account": this dashboard reads OpenShift, not the directory, so it cannot claim the account does not exist |
| `membership_disagrees` | the synced group says they **are** in the gate group and the directory search still found nothing — our membership data and the live directory disagree, usually a sync that has not caught up with a removal. The only one of the three that is a fault in our own data |
| `null` | no login gate is known, or the outcome was never ambiguous |

### `GET /api/clusters/{cluster_id}/cluster-access`

Who can actually **log in**, set against who holds access. Two different questions, and every other
view here answers only the second.

A cluster whose identity provider gates authentication on group membership can grant somebody a role
they can never use. Measured on the reference cluster: 10 people held access through synced groups, 7
were in the login-gate group, so **3 held access they could not exercise**. Nothing else in this
dashboard sees that, because everything else starts from RBAC.

| field | meaning |
|---|---|
| `gated` | whether a login gate is known at all. `false` means no identity provider filter carries a `memberOf`/`isMemberOf` clause — so any account in its search base can sign in — or the OAuth CR could not be read |
| `dn` | the gate group's full DN |
| `source` | `config` if it came from `clusterAccess.group`, `oauth` if discovered from the identity provider's filter. Stored so "why is this the wrong group?" has an answer |
| `group_name` / `synced` | the synced OpenShift Group whose `openshift.io/ldap.uid` matches the DN. **`synced: false` is no data, not zero findings** — without the Group object there is no membership to compare against |
| `summary` | `gated_members`, `with_access`, `access_without_login`, `login_without_access`, over the whole cluster |
| `access_without_login` | the finding: holds access through a synced group, is not in the gate group. `groups` is a list, `has_tried` says whether they have ever appeared in a login attempt |
| `login_without_access` | the quieter half: in the gate group, holds no other synced-group access. Not automatically a problem — a new joiner looks like this, and so does a service identity that happens to sit in the group |

**The gate group must be synced by the group-sync-operator first**, with its own GroupSync CR — this
chart does not create one, because GroupSync CRs belong to the platform team. A worked example is in
`docs/examples/clusteraccess-groupsync.yaml`. Watch the membership attribute: a gate group is often
`objectClass: groupOfUniqueNames` with `uniqueMember`, while RBAC groups are `groupOfNames` with
`member` — copying an existing CR's `rfc2307` block verbatim syncs the group with **zero members** and
looks like a working sync.

Both attribute spellings are read when discovering the DN: `memberOf` (OpenLDAP, Active Directory) and
`isMemberOf` (389-ds, Oracle/Sun DSEE). Neither is standardised, and a parser that knew only one would
report "no gate configured" on half the directories in the world.

### `GET /api/clusters/{cluster_id}/membership-changes`

Query: `limit` (1–1000, default 100). Joins and departures cluster-wide.

Each change carries `group_synced_at` — the group's own sync-time when the change was seen.
That distinguishes *"the operator did this"* from *"someone edited the object"*: a change
stamped with a stale sync-time did not come from a sync.

Since 0.13.0: `retention` for `membership_event`, the same shape as on `/events`. With the default
`membershipEventsDays: 0` it reads `{"window_days": 0, "retained_since": <oldest row>}`.

### `GET /api/clusters/{cluster_id}/binding-changes`

Query: `namespace` (optional — the empty string selects ClusterRoleBindings; omit for every
scope), `limit` (1–1000, default 100). Which (binding, subject) rows appeared or disappeared,
newest first — the bindings' membership-changes (`docs/DESIGN_binding_events.md`).

The only record of a binding change: the current-state tables are replaced every refresh, so a
RoleBinding created and deleted between two refreshes never existed as far as
`/bindings/findings` is concerned. A role change on the same binding+subject is one `removed`
and one `added`.

```json
{
  "cluster": "crc", "scope": "all", "viewer": "kubeadmin",
  "count": 2, "limit": 100, "truncated": false, "baseline_rows": 0,
  "note": "accumulated from binding refreshes; a baseline row is the first observation, not a change",
  "retention": {"window_days": 0, "retained_since": "2026-09-17T22:00:11Z"},
  "changes": [
    {"binding_kind": "RoleBinding", "binding_namespace": "demo-qa", "binding_name": "demo-dev",
     "subject_kind": "Group", "subject_name": "app-ocp-rbac-demo-ns-developer",
     "role_kind": "ClusterRole", "role_name": "edit", "is_platform": 0,
     "change": "added", "baseline": 0, "observed_at": "2026-09-17T22:05:00Z"}
  ]
}
```

`baseline` is 1 on a cluster's **first observation** of that subject kind — the refresh that
consumes the cluster's `observation_state` marker, whether or not it returned rows — because
every row it had is recorded as `added` in that instant, which is not a change anyone made;
render it as "first observed", never as "added". A store upgraded with rows already present
starts marked, so an upgrade writes no baseline rows. `retention` shares `membership_event`'s
window (`membershipEventsDays`).

Self tier: only rows naming the viewer, or a group the viewer belongs to.

## RBAC

### `GET /api/clusters/{cluster_id}/bindings/findings`

Every group-subject binding, classified. Despite the path, this returns **all** bindings,
including healthy ones — the caller filters.

```json
{
  "total": 229, "limit": 500, "offset": 0, "truncated": false,
  "counts": {"ok": 70, "dangling": 0, "unresolved": 9, "built_in": 146, "unmanaged": 4},
  "ok": [
    {"binding_kind": "RoleBinding", "binding_namespace": "prod-ns", "binding_name": "managed-admin-rb",
     "role_kind": "ClusterRole", "role_name": "admin", "group_name": "app-ocp-rbac-alpha-ns-admin",
     "managed_source": "baseline-nonprod-rbac", "exception": null, "audit_stamped": 0, "finding": "ok",
     "member_count": 2, "logged_in_count": 1}
  ],
  "dangling": [], "unresolved": [], "built_in": [], "unmanaged": [],
  "operator_configs": {}
}
```

Every row, in every tier, has the same shape. `member_count` is the named group's synced members
and `logged_in_count` is how many of those members have logged in — a User object with an identity,
the Users tab's definition — both from the same membership rows, so their difference is exactly the
members with no login. Both are `null` when no Group object exists (`dangling`, `unresolved`,
`built_in`), so `0` keeps its meaning: the group exists and grants nobody today. `logged_in_count`
is also `null` until the User objects have been read at least once (`/users` says `source: pending`
then), rather than a confident zero.

| Parameter | Default | |
|---|---|---|
| `limit` | `500` (max 5000) | rows across **all** tiers combined, not per tier |
| `offset` | `0` | for paging through `total` |

**`counts` and `total` always describe the whole cluster, never the page.** They come from a
separate scalar query, because counting the rows you just limited is how "showing 50 of 30"
reaches a report. `truncated` says whether rows were dropped.

This was unbounded at the store, the API and the renderer simultaneously — measured at 2,280
rows and 545,800 bytes on a cluster ten times the reference size, fetched on a 30-second
auto-refresh.

| Tier | Meaning | Alerts? |
|---|---|---|
| `ok` | the group exists; access reaches its members | no |
| `dangling` | the group **was** operator-managed and has disappeared | **yes, critical** |
| `unresolved` | names a group that has never existed here | no |
| `built_in` | `system:*` virtual group; no object expected | no |
| `unmanaged` | the group IS operator-synced, but no policy CR templates this binding — somebody granted access by hand | no |

**Suppressing an `unmanaged` finding is a cluster-admin task, performed on the object:**

```bash
oc annotate clusterrolebinding <name> \
  rbac.ocp.io/unmanaged-exception="approved in TICKET-123, break-glass access"
```

The poller reads that annotation on its next binding refresh and stops classifying the binding
as `unmanaged`, so it leaves this response, the RBAC policy tab and the log together. The
dashboard cannot write it for you — it holds no write verb on any cluster — and that is the
point: the justification ends up next to the object it excuses, where `oc describe` finds it,
and the acknowledgement is made by somebody who holds the privileges.

`audit_stamped` on a row reports whether the object carries `rbac.ocp.io/unmanaged=true`. The
dashboard never applies that label either; an admin or a CI job may, to make findings
selectable with `oc get ... -l`. Nothing here depends on it.

`unresolved` deliberately does not alert: a group never observed cannot be distinguished
from one that simply has not synced yet. It is still worth reading — those bindings grant
nobody — which is why the UI shows them even though nothing pages, and why the count sits on
the cluster card: a reader who only looks at the UI must not see "No alerts" and conclude
nothing is wrong.

The three "group does not exist" tiers all share that symptom and are separated by what can be
*proved* about the cause, which is why there are three rather than one.
[`docs/reference-architecture.md`](../docs/reference-architecture.md) has the evaluation order,
the reasoning, and a worked example from the reference cluster.

Classification tests **provenance before the `system:` prefix**. The reverse order silently
downgraded a genuinely dangling binding to `built_in` whenever a managed group carried that
prefix — a grants-nobody binding with no alert.

Direct bindings only. Role rules are never fetched or expanded, so this is not an
effective-permission calculation and must not be presented as one.

### `GET /api/clusters/{cluster_id}/home`

Home — the page every reader lands on (#158): the viewer's own access on one cluster, answering "what can I
reach, and how?" for the person asking and nobody else. **Self-scoped by definition, on every tier**: an
administrator sees their own access here, never everyone's, so the payload for a name is identical whichever
tier resolves it (only `scope` says which). The identity is the proxy's; with none there is nothing to scope
to and the request is refused with 403 — never a name the caller typed.

```json
{
  "cluster": "crc-local", "viewer": "jane.smith", "scope": "self",
  "full_name": "Jane Smith", "providers": ["ldap-local"],
  "answer": {
    "top_role": "admin",
    "cluster_wide": [{"role_name": "admin", "role_kind": "ClusterRole", "via_groups": ["app-ocp-rbac-alpha-cluster-admin"],
                      "direct": false, "bindings": 1, "covered_by": null},
                     {"role_name": "edit", "role_kind": "ClusterRole", "via_groups": ["…", "…", "…"],
                      "direct": false, "bindings": 3, "covered_by": "admin"}],
    "cluster_wide_bindings": 5,
    "namespaces": [{"name": "demo-qa", "platform": false, "covered": true,
                    "grants": [{"role_name": "edit", "role_kind": "ClusterRole", "via_group": "app-ocp-rbac-demo-ns-developer",
                                "binding_name": "demo-qa-devs", "covered": true}]}],
    "namespaces_covered": 3,
    "groups": [{"group_name": "app-ocp-rbac-alpha-cluster-admin", "sync_provider": "ldap-groupsync_ldap",
                "first_seen_at": "…", "last_seen_at": "…", "grants": 1, "cluster_wide_roles": ["admin"],
                "namespaces": [], "gives_top": true}],
    "groups_total": 18, "groups_granting": 7, "direct_count": 1
  },
  "direct": [{"binding_kind": "RoleBinding", "binding_namespace": "openshift-console-user-settings", "binding_name": "user-settings-jane",
              "role_kind": "Role", "role_name": "user-settings-jane-role", "user_name": "jane.smith", "is_platform": 0}],
  "changes": {"items": [{"kind": "single", "cluster": "prod-east", "change": "added", "group_name": "platform-team-cluster-admin", "observed_at": "…"},
                        {"kind": "flap", "cluster": "crc-local", "group_name": "app-ocp-rbac-groupsync-ns-auditor", "changes": 5, "span_minutes": 33, "latest": "added", "observed_at": "…"},
                        {"kind": "batch", "cluster": "crc-local", "change": "added", "count": 17, "groups": ["…"], "observed_at": "…"}],
              "more": 0, "more_items": 0, "changes": 23, "window_days": 30},
  "retention": {"window_days": 90, "retained_since": "…"},
  "elsewhere": [{"cluster": "prod-east", "memberships": 17, "status": "ok", "last_poll": "…"}],
  "memberships_total": 36
}
```

`answer` is derived once, server-side (`gsd/home.py`), so the page's sentences and the numbers under them
change together. `top_role` is the strongest of the four built-in ClusterRoles held cluster-wide
(cluster-admin ⊃ admin ⊃ edit ⊃ view), through a group or directly; a grant is `covered` when that role is at
least as strong, and a cluster-wide role is `covered_by` a strictly stronger one — a custom role is never
covered and never covers, since its meaning is the cluster's. `namespaces` are every namespace a binding
reaches through the viewer's groups or names them in directly (`via_group` null), `platform` for the
platform's own (`openshift-*`, `kube-*`, `default`). `groups` are every synced group the viewer is in, the
one that gives `top_role` first, then by what each grants. `direct` are the bindings naming the viewer
(their own only). `changes` is their membership history over the last 30 days on this cluster and on every
cluster in `elsewhere`, folded: a group with three or more changes is one `flap` line, three or more groups
changing in one sync one `batch` line, the rest `single`; newest first, twelve lines and `more`.
`elsewhere` names the other enabled clusters that treat this identity as their own, with the viewer's
membership count and the cluster's last poll; a cluster whose identity policy withholds the host's username
is not listed.

### `GET /api/clusters/{cluster_id}/user-bindings`

Roles granted **directly to a person** rather than to a group. The governance finding in its
purest form: it survives offboarding, because removing someone from an LDAP group revokes
nothing here, and it is invisible to every group-based review including the rest of this API.

```json
{
  "cluster": "crc-local",
  "note": "direct user grants; migrate these to LDAP-managed groups",
  "by_namespace": [
    {"namespace": "legacy-payments", "bindings": 3, "distinct_users": 3,
     "worst_privilege": 3, "cluster_scoped": 0,
     "users": ["asmith", "bwilliams", "jdoe"]}
  ],
  "excluded_platform": 36,
  "namespace": null, "total": 6, "limit": 200, "offset": 0, "truncated": false,
  "bindings": []
}
```

| Parameter | Default | |
|---|---|---|
| `namespace` | none | restrict to one namespace. **See the sentinel below** |
| `limit` | `200` (max 5000) | applies to `bindings` only |
| `offset` | `0` | |
| `include_platform` | `false` | see below |

**`namespace=(cluster-scoped)` is the only way to ask for the cluster-wide rows, and nobody
would guess it.** Those bindings have `binding_namespace: ""`, and an empty query parameter is
indistinguishable from an absent one — which means "everything". So the literal string
`(cluster-scoped)` is the sentinel, translated at the store boundary:

```bash
curl -sk -H "Authorization: Bearer $TOKEN" \
  "https://$ROUTE/api/clusters/crc-local/user-bindings?namespace=(cluster-scoped)"
# -> total 1, binding_namespace ""
```

**`by_namespace` is NOT paged**, and the asymmetry is deliberate. It is one row per namespace,
bounded by a number the cluster already keeps small, and it is what the UI ranks risk from —
truncating it would make the ranking a ranking of an arbitrary subset. `bindings` is the flat
list that grows with people × grants, so that is what `limit` applies to.

`worst_privilege` is `4` cluster-admin, `3` admin, `2` edit, `1` anything else. Rows are
ordered worst-privilege first, then cluster-scoped, then count — **not** by count, because one
forgotten `cluster-admin` matters more than twenty `view` grants.

`users` is a **list**, not a comma-joined string. It was a string once and the UI rebuilt the
set by splitting on `,` — which breaks the moment an IdP maps LDAP DNs to usernames, since
`cn=jdoe,ou=People,dc=example,dc=com` becomes four people.

`excluded_platform` counts what was left out: `system:*` identities and `kubeadmin` are
break-glass with nowhere to migrate to, and on the reference cluster they were 34 of 36 rows.
`include_platform=true` shows them.

### `GET /api/clusters/{cluster_id}/operator-configs`

Reconcile health of the namespace-configuration-operator's CRs (`NamespaceConfig`,
`GroupConfig`) — the CRs that *template* the bindings above.

```json
{
  "cluster": "crc-local",
  "present": true,
  "configs": [
    {"kind": "GroupConfig", "name": "cluster-admin-groupconfig-rbac",
     "error_at": null, "error_message": null,
     "success_at": "2026-08-02T23:00:19Z", "observed_at": "2026-08-02T23:32:38Z"}
  ]
}
```

**`present` distinguishes "the CRDs are not installed" from "installed with zero CRs".** They
are different truths and conflating them would let the UI report all-healthy about a concept
the cluster does not have.

A CR is currently failing when `error_at` is set and is *later* than `success_at`. A
`NamespaceConfig` that stops reconciling raises nothing on the cluster — both its conditions
stay `True` — so new namespaces silently receive no RBAC and drift stops being corrected.

### `GET /api/clusters/{cluster_id}/kyverno`

The Kyverno policy module (#165, #170): the CEL policies (`ValidatingPolicy`, `MutatingPolicy`,
`GeneratingPolicy`, `DeletingPolicy`, `ImageValidatingPolicy`) the poller listed, what their policy
reports say about each resource, and the appeared/cleared history. **Administrator tier** (`403` at
self): a finding names a resource cluster-wide and answers nothing a reader can ask about themselves.

```json
{
  "cluster": "crc-local", "scope": "all", "viewer": "kubeadmin", "enabled": true,
  "present": true, "api_group": "wgpolicyk8s.io/v1alpha2", "policy_kinds": ["ValidatingPolicy"],
  "reports": 115, "legacy_results": 667, "other_results": 0,
  "breaker_total": 3949, "breaker_drops": null, "observed_at": "2026-09-20T12:00:00Z",
  "results": {"pass": 9, "fail": 0, "warn": 0, "error": 0, "skip": 0}, "policies": 1,
  "policies_list": [{"kind": "ValidatingPolicy", "namespace": "", "name": "restrict-nco-config-writers",
                     "admission": true, "background": false, "actions": ["Audit"], "failure_policy": "Fail",
                     "ready": true, "results": {"pass": 9, "fail": 0, "warn": 0, "error": 0, "skip": 0}}],
  "rows": [], "total": 0, "truncated": false, "events": [], "controlled_kinds": ["Pod", "ReplicaSet", "Job"]
}
```

Three states, rendered distinctly: **`present: null`** — never polled since the module arrived;
**`present: false`** — no policy-report API group is served, Kyverno is not installed (never
"zero results"); **`present: true`** with **`legacy_results`** counting what the deprecated
`ClusterPolicy`/`Policy` family wrote that this module does not read (a cluster carrying them is not a
clean cluster), and **`breaker_drops`** — `kyverno_breaker_drops` as last scraped from the reports
controller when `kyverno.metricsUrl` is set; `null` is "no drop observed, or not scraped", never 0.
`?problems=false` lists every result; `?controlled=true` includes Pods, ReplicaSets and Jobs (usually a
controller's copies of one finding — off by default and said on the page); `?policy=` (the wire string —
`namespace/name` for a namespaced policy) with `?kind=` narrows to one policy — a `ValidatingPolicy` and a
`MutatingPolicy` may share a name; `total` and `truncated` say what `limit` cut. A result is keyed by policy and resource, never by
rule: the CEL engine writes no rule name. `events` are the problems (fail/warn/error) that appeared or
cleared between two polls, newest first — the reports themselves are owned by their resource and carry
no history.

### `GET /api/kpi`

The KPI module's in-app surface (#156): every KPI definition rendered as JSON, the 30-day trends,
the daily rollup's series, and both processes' self-reported system usage. **Administrator tier**
(`403` at self): the `internal` class counts people, and the trends aggregate the fleet's churn
and logins — governance data about the clusters, not about the reader.

```json
{
  "scope": "all", "viewer": "root", "as_of": "2026-09-19T14:02:11Z",
  "kpis": {
    "gsd_membership_changes_total": {"help": "…", "kind": "counter", "privacy": "public",
                                     "labels": ["cluster", "change"],
                                     "samples": [{"cluster": "crc-local", "change": "added", "value": 14}]},
    "users_total": {"help": "…", "kind": "gauge", "privacy": "internal", "labels": ["cluster"],
                    "samples": [{"cluster": "crc-local", "value": 41}]},
    "gsd_process_memory_limit_bytes": {"…": "…", "samples": null}
  },
  "posture": {
    "crc-local": {"groups": {"total": 62, "empty": 1, "unattributed": 2},
                  "bindings": {"ok": 26, "dangling": 5, "unresolved": 6, "unmanaged": 5, "built_in": 157},
                  "groupsyncs": {"total": 3, "states": {"ok": 3}, "oldest_last_sync": "2026-09-19T13:30:00Z"}}
  },
  "thresholds": {"memory_percent": 80, "cpu_percent": 80, "throttled_percent": 1, "disk_percent": 80},
  "links": {"grafana": "https://grafana.example.com", "console": "https://console-openshift-console.apps.example.com"},
  "trends": {
    "crc-local": {
      "window_days": 30,
      "activity": {"membership": [{"day": "2026-09-19", "added": 3, "removed": 2}],
                   "logins": [{"day": "2026-09-19", "attempts": 6, "successes": 2}],
                   "syncs": [{"day": "2026-09-19", "syncs": 48}],
                   "reports": []},
      "history_retained_since": {"membership_event": "2026-08-20T00:00:00Z", "sync_event": null, "binding_event": null},
      "report_timeline_since": "2026-09-16T02:00:00Z",
      "daily": {"since": "2026-09-19", "window_days": 90,
                "series": {"groups": [{"day": "2026-09-19", "value": 62.0}], "bindings": []}},
      "as_of": "2026-09-19T14:01:40Z"
    }
  },
  "system": {
    "dashboard": {"as_of": "2026-09-19T14:02:11Z",
                  "memory": {"used_bytes": 105410560, "limit_bytes": 536870912},
                  "cpu": {"limit_cores": 0.5, "usage_seconds": 5.06, "periods": 175931,
                          "throttled_periods": 196, "throttled_seconds": 5.06,
                          "cores_used": 0.02, "throttled_fraction": 0.0, "rate_interval_seconds": 60.0},
                  "disk": {"used_bytes": 27000000000, "total_bytes": 32000000000},
                  "data": {"db_bytes": 2400000, "wal_bytes": 4200000, "backups": {"count": 4, "bytes": 8500000}}},
    "report": null
  }
}
```

Every KPI carries its **privacy class**: `public` ones are the same definitions `/metrics`
exports (`gsd_process_*{component}`, `gsd_volume_disk_*`, `gsd_membership_changes_total`,
`gsd_login_attempts_total`); `internal` ones — anything counting people — never reach `/metrics`,
which the renderer refuses rather than a convention remembers. A KPI whose source cannot be
measured has `samples: null` — *unavailable*, distinguishable from 0 (a cgroup v1 node, an
unlimited `memory.max`). `system.report` is the report service's last self-report, pulled with
its usage feed — the same blocks, with `artifacts: {bytes, files}` in place of `data`; `null` until
the first pull, or when the service predates it. `disk` is the filesystem under the volume (on a
hostPath volume, the node's disk), `data` / `artifacts` the component's own bytes on it — the mock
shows both because a hostPath volume's own size means nothing. `cpu.cores_used`
and `throttled_fraction` are rates over the interval since the previous sample, on a monotonic
clock, and `null` on the first, and are derived only over an interval of at least five seconds (the
poll thread takes a baseline every cycle). Every trend carries `history_retained_since`, because
retention prunes the event tables and a trend that ignores the cut lies about a quiet month;
`report_timeline_since` is the first report run the dashboard ever recorded for the cluster; and
`daily.since` is where the rollup — written once a day by the leader, for the counts that have no
history — actually starts. `activity` is the page's sparkline buckets: the `window_days` whole UTC
days ending on `as_of`'s day, from the first day's midnight — the scalars beside them are rolling
30 × 24 h, so the two can differ by that first, partial day.
`posture` is each served cluster's access-posture figures from the same scalar queries the cluster
rows and `/metrics` use, and `groupsyncs.states` the CRs' derived states, so the KPI page (#157) adds no
arithmetic of its own. `thresholds` are the configured amber marks (`kpi.thresholds.*` in the chart) the
page draws on every meter and names in its rule line; `links` carries the doors out (`grafana`,
`grafana_dashboard_uid`, `console`, `observe`) and omits any that is not configured. `console` is
the chart's `console.url` or, when that is empty, the URL the poll thread discovered from
`openshift-config-managed/console-public`; `observe` is the console's namespace-workloads dashboard
scoped to the pod's own namespace (`…/dev-monitoring/ns/<ns>?dashboard=dashboard-k8s-resources-workloads-namespace` — the namespace in the path, because the console's project selector, which the graphs' tenancy requests carry, is set only from a `/ns/<name>` path segment).

### `GET /api/whoami`

```json
{"user": "developer", "email": "developer@cluster.local", "authenticated": true,
 "logout_url": "/oauth/sign_out",
 "session": {"cookie_expire_seconds": 14400, "cookie_refresh_seconds": 0,
             "idle_timeout": {"enabled": false}}}
```

Reflects the identity the **proxy** asserted, from `X-Forwarded-User`. With the proxy disabled
the app binds `0.0.0.0` with no authentication, so those headers are whatever the caller typed
— `authenticated` is `false` in that mode, every other field is `null`, and nothing should
trust the values.

`logout_url` is the proxy's own `sign_out`, composed from the configured `--proxy-prefix` so a
changed prefix cannot leave the page's control pointing at a path the proxy no longer answers.
The dashboard does **not** revoke the OAuth token on the way out: that was built, measured
failing, and removed — the console can revoke because its tokens carry scope `user:full`, while
this chart authenticates through a ServiceAccount whose tokens carry `user:info` and
`user:check-access`, so the API refuses the delete whatever the RBAC says. `session` restates the
**configured** cookie lifetimes in seconds — never a live deadline, which an HttpOnly cookie
makes unobservable. The page reads it at load for the sign-out link, the cap note and
the idle model, and again on every ordinary data refresh so `visibility` can follow a grant that
changes while the tab is open. There is no session-only timer: the request itself re-stamps the
session cookie, and the automatic refresh is suspended while the idle model is warning or expired,
so an unattended tab does not keep its own session alive.

### `GET /api/dashboard/activity`

Who used the dashboard: one row per user per UTC day, with first seen, last seen and an
interaction count.

```json
{
  "enabled": true, "retention_days": 400,
  "scope": "self", "viewer": "developer",
  "total": 1, "limit": 500, "truncated": false,
  "summary": {"distinct_users": 1, "days": 1, "interactions": 250},
  "activity": [{"user_name": "developer", "day": "2026-08-02",
                "first_seen_at": "2026-08-02T12:46:04Z",
                "last_seen_at": "2026-08-02T23:18:41Z", "request_count": 250}]
}
```

**`scope` is `self` by default** — each person sees only their own row. This is identifiable
personnel data (who was present, on which days, between which times), and the argument that
carries the rest of this API, "you could read the groups with `oc` anyway", is true of group
membership and false of who looked at it — and Usage is the one dataset with no `oc` equivalent at
all, living only in this dashboard's database.

**It is widened by its OWN, stricter tier, not the wide one.** `scope` is `all` here only when
`config.userActivity.visibility: all` is set (the blunt override, which always wins) OR when this
reader passes `visibility.usageAdminSar` — a separate SubjectAccessReview, default
`update clusterrolebindings`, that `cluster-admin` passes and the auditor `cluster-reader` does not.
Passing the wide `visibility.adminSar` does NOT widen this view; the two tiers are independent and
cached separately. See docs/SPEC_usage_admin_tier.md.

**`summary` describes the whole set, not the page.** It used to be computed in the browser from
`activity`, which the API caps — measured against 1,092 stored rows, the UI reported 167 days
and 5,000 interactions where the truth was 364 and 10,920.

An **interaction** is one deliberate action, not one HTTP request: the page refreshes itself
every 30s, and counting those measured how long a tab was left open rather than whether anyone
used the dashboard. One real session read 722.

**These are not logins.** The proxy owns the session, so the app never sees a sign-in or
sign-out; `first_seen_at`/`last_seen_at` are the first and last request on that UTC day.

Requires `oauthProxy.enabled` **and** `config.userActivity.enabled`. Without the proxy there is
no authentication, so nothing is recorded whatever the setting says, and the endpoint returns
`403` rather than trusting a caller-supplied name.

### `GET /api/report/ticket`

A short-lived, signed ticket that lets THIS reader call the report service — minted only at the
administrator tier (`require_admin_tier`, the same SubjectAccessReview as `/bindings/findings`), and
bound to the proxy's `X-Forwarded-User`. 404 when reporting is off; 403 with the gate's own sentence
below the wide tier. A GET that does no work: nothing is stored, rendered or fetched.

```json
{"ticket": "eyJ2IjoxLCJ2aWV3ZXIiOiJyb290Ii4uLg.5kZ…", "expires_in": 300, "prefix": "/report", "viewer": "root"}
```

The browser sends the ticket on every request to `/report/**` as `X-GSD-Report-Ticket`; the report
service verifies the signature (HMAC-SHA256 with the token both pods mount), the expiry, the tier and
that `viewer` equals the `X-Forwarded-User` the proxy stamped on that request. Expiry is a 401 (the
page mints once more); every other refusal is a 403.

### `GET /api/dashboard/reports`

Who generated which report, when — pulled from the report service by the poller (`/report/api/usage`,
with the shared token) and recorded in `report_run`. **Usage tier**, like `/api/dashboard/activity`:
`scope` is `all` only for that tier; everyone else sees their own runs. `enabled` is false when
reporting is off; 403 without the proxy.

```json
{
  "enabled": true, "scope": "self", "viewer": "developer", "total": 1, "limit": 200, "truncated": false,
  "runs": [{"id": "20260906T120001.000000Z-1a2b", "report": "namespace-access", "cluster_id": "crc-local",
            "generated_by": "developer", "generated_by_note": "proxy-verified, ticket from the dashboard",
            "schedule": null, "status": "done", "requested_at": "2026-09-06T12:00:01Z",
            "finished_at": "2026-09-06T12:00:03Z", "sha256": "…", "snapshot_stamp": "2026-09-06T11:58:00.123456Z",
            "formats": ["html", "pdf"], "bytes_total": 48211, "pdf_variant": "pdf/a-2b"}]
}
```

Query: `limit` (1–5000, default 200), `offset`.

## The report service's API

Everything under `/report` is served by the **report service**, a second pod behind the same
oauth-proxy (path-routed upstream), not by the dashboard. It is documented by the service's own
`/report/api/openapi.json`; every route needs a dashboard-minted ticket or the service token, except
the three probe paths, which are reachable only on the report Service. One line each:

| Method and path | Who | What |
|---|---|---|
| `GET /report/healthz`, `GET /report/readyz`, `GET /report/metrics` | none (Service only) | liveness; readiness (artefact volume writable, a snapshot exists); Prometheus exposition (`gsd_report_*`, no names) |
| `GET /report/api/reports` | ticket | the catalogue: each report, whether enabled, its values key and parameter specs |
| `GET /report/api/snapshot` | ticket or token | the copy a run would read now: stamp, age, schema, bytes |
| `POST /report/api/runs` | ticket or token | queue one run (`report`, `cluster`, `params`, `formats`); 202 with the run id — **the one write in either service's API, deliberately not on the dashboard** |
| `GET /report/api/runs`, `GET /report/api/runs/{id}` | ticket or token | runs newest first; one run's status, timings, sha256 and artefact sizes |
| `GET /report/api/runs/{id}/artifact?format=json\|html\|pdf` | ticket or token | the artefact, `Cache-Control: no-store`, `X-GSD-Report-SHA256`, as an attachment |
| `GET /report/api/usage?since_id=&limit=` | **token only** | finished runs for the dashboard's pull; viewers read them from the dashboard at the usage tier |

## Alerts

### `GET /api/alerts`

Computed on read across all clusters, sorted critical first.

Kinds: `overdue`, `invalid_schedule`, `sync_stopped`, `empty_group`, `unattributed`,
`stale_group`, `reconcile_error`, `dangling_binding`, `groupsync_crd_absent`,
`config_reconcile_error`, `direct_user_binding`, `group_count_cliff`,
`group_count_cliff_silenced`, plus the poll outcome for a degraded cluster.

Every row carries `silenced` (boolean) and `silenced_by` (`"annotation"` | `"values"` | `null`).
Only the group-count cliff sets them: a group whose membership fell by
`config.alerts.groupCountCliff.dropRatio` from at least `minMembers` within `windowHours`,
reconstructed from `membership_event` (`gsd/state.py#compute_alerts`,
`gsd/store.py#Store.group_count_changes`). A cliff silenced by the Group annotation
`groupsync-dashboard.io/silence-group-count-cliff` (`"true"` or `until=YYYY-MM-DD`) or by the
chart's `silence` list is reported under `group_count_cliff_silenced` with the same detail —
reported, never dropped. Both kinds are withheld at the self tier, like `empty_group`.

At the self tier the feed is filtered to the kinds whose backing pages a narrowed reader sees
(`gsd/api.py#SELF_ALERT_DETAILS`), and one kind's text is rewritten: `reconcile_error` keeps its
kind and subject, but its `detail` — which copies the CR's `error_message`, the field
`/groupsyncs` withholds at self — is replaced with
`reconcile failed; diagnostic text is withheld in the self view`. Replaced rather than omitted,
so an empty reason column cannot read as "no reason exists". Administrators receive every kind
with the full detail.

`groupsync_crd_absent` fires when the group-sync-operator's CRD is not installed. It is raised
FIRST because it explains every other finding on the page: with no CR to attribute anything to,
every group is `unattributed` and every provider-based check has nothing to work with. Groups
themselves are still read and shown, which the detail text says explicitly so a reader does not
conclude the dashboard is broken.

It requires absence to have been OBSERVED. `groupsync_operator_present` on the cluster card is
three-valued — `true` / `false` / `null` (never polled) — and only `false` alerts. `null` must
not, or upgrading would fire this for every cluster before it had looked at any of them. The
field also disambiguates `groupsync_count: 0`, which otherwise reads identically for "operator
not installed" and "installed, no CRs defined".

A degraded cluster's group-level alerts are **skipped entirely**, because its cached rows are
stale by definition and would report yesterday's state as today's.

## Operational

| Endpoint | Notes |
|---|---|
| `GET /healthz` | liveness. Unconditional |
| `GET /readyz` | readiness. **Not** gated on a reachable cluster — an unreachable cluster is a thing this dashboard exists to display, so failing readiness for one would take it down exactly when it has something to report |
| `GET /api/version` | `{version, commit, branch, dirty, features, timezone}` from the build stamp. `features` names the optional modules switched on for this deployment (`export`); the page renders a control only where its flag is `true`. `dirty: true` means no commit reproduces the running image. `timezone` is `{name, abbrev, utc_offset}` for the **container**, which the browser needs because it can only discover its own |
| `GET /metrics` | Prometheus exposition. Unauthenticated so a ServiceMonitor can scrape it, which is why it emits counts and states only — never a group or user name |
| `GET /signed-out` | the proxy's `-logout-url` landing page. Static, script-free, unauthenticated (it renders at the exact moment the cookie died), and worded to be true whether or not the revocation above happened |
| `GET /static/index.html`, `GET /static/signed-out.html` | the same two pages, rendered. The `/static` mount would otherwise serve the source files with the dashboard's name unfilled, so these routes shadow them. Not in the OpenAPI schema |

## The schema, served

| Endpoint | |
|---|---|
| `GET /api` | Swagger UI |
| `GET /api/docs` | `308` redirect to `/api` — one canonical URL, so the two cannot render different schemas after a FastAPI upgrade |
| `GET /api/redoc` | ReDoc reference |
| `GET /api/openapi.json` | the OpenAPI document, for codegen |

Under `/api` rather than FastAPI's default `/docs` deliberately: `oauthProxy.skipAuthRegex`
admits only `/healthz`, `/readyz` and `/metrics`, so everything under `/api` is authenticated
exactly like the data it describes. A document naming every endpoint and field is a map of the
cluster's RBAC surface.

Both renderers are served from bundles committed to this repository, so they work on a cluster
with no route to the internet — see [`../docs/updating-vendored-assets.md`](../docs/updating-vendored-assets.md).

Rules a new endpoint must satisfy, each enforced by a test:
[`../docs/api-contract.md`](../docs/api-contract.md).

## Trying it

```bash
ROUTE=$(oc get route group-sync-dashboard -n group-sync-dashboard -o jsonpath='{.spec.host}')

curl -sk "https://$ROUTE/api/clusters" | python3 -m json.tool
curl -sk "https://$ROUTE/api/clusters/crc-local/bindings/findings" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['counts'])"
curl -sk "https://$ROUTE/api/version"
```

Locally, `http://127.0.0.1:8099` and `/docs` for the interactive version.
