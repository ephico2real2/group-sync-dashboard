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

**`bindings/findings` and `operator-configs` are the administrator tier** (`403` at self). The
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

Adds `members`, `changes` and `bindings`.

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

Users with at least one group membership. **Bounded.**

Query: `limit` (default 1000, max 10000).

Returns an object, not a bare list — it previously returned every row, which is one per
distinct user across every group and grows with the size of the directory rather than with
anything the dashboard controls (102,921 bytes at reference scale). `truncated` tells the
caller the list was clipped, because a clipped list that looks complete is the failure
worth avoiding.

```json
{"cluster": "crc", "count": 1000, "truncated": true, "limit": 1000,
 "users": [{"user_name": "alice", "full_name": "Alice Cooper", "group_count": 2,
            "first_seen_at": "2026-08-01T09:00:00+00:00"}, ...]}
```

Each row carries `full_name`, `null` when OpenShift has no User object for the id or the IdP
supplied no name — the same field and the same absence rule as a group's members. The Users
tab filters in the browser on both `user_name` and `full_name`, so it requests the maximum
`limit`; when `truncated` is true the tab says so, because a filter over a clipped list would
report a real person as "no match".


### `GET /api/clusters/{cluster_id}/users/{name}`

The reverse lookup: every group the user is in, every binding that reaches them, and their
membership history. Each binding row carries `via_group`, because "why do they have this?"
is the next question after "do they have it".

**A user with no current groups returns 200, not 404**, if any history exists. "They are in
nothing now" is the answer, not an error. 404 only when the user has never been seen.

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

Every row, in every tier, has the same shape. `member_count` is the named Group's own member count
and `logged_in_count` is how many of those members have logged in — a User object with an identity,
the Users tab's definition. Both are `null` when no Group object exists (`dangling`, `unresolved`,
`built_in`), so `0` keeps its meaning: the group exists and grants nobody today.

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

### `GET /api/whoami`

```json
{"user": "developer", "email": "developer@cluster.local", "authenticated": true,
 "logout_url": "/oauth/sign_out",
 "session": {"cookie_expire_seconds": 14400, "cookie_refresh_seconds": 0}}
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
makes unobservable. Fetched once at page load; never poll it, because the request itself
would re-stamp the session cookie.

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

## Alerts

### `GET /api/alerts`

Computed on read across all clusters, sorted critical first.

Kinds: `overdue`, `invalid_schedule`, `sync_stopped`, `empty_group`, `unattributed`,
`stale_group`, `reconcile_error`, `dangling_binding`, `groupsync_crd_absent`, plus the poll
outcome for a degraded cluster.

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
| `GET /api/version` | `{version, commit, branch, dirty, timezone}` from the build stamp. `dirty: true` means no commit reproduces the running image. `timezone` is `{name, abbrev, utc_offset}` for the **container**, which the browser needs because it can only discover its own |
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
