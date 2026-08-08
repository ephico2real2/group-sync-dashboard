# Login capture — research, and the build

Status: **design. Nothing below the research section is implemented.**

The prerequisite shipped in PR #11: `authLogLevel` raises `spec.logLevel` on the authentication
**operator** CR so the oauth-server names the person logging in, and `loginCapture` grants the dashboard
a namespaced read of those pod logs. `gsd/loginlog.py` (committed) parses lines into attempts. What
remains is everything between the log and the screen.

---

# Part 1 — Research

Every claim here was measured on a live cluster on 2026-08-07, or cited. Nothing is inferred.

## 1.1 The line, and where the timestamp comes from

```
2026-08-07T16:56:28.267663898Z I0807 16:56:28.267 1 basicauth.go:51] Login with provider "ldap-local" succeeded for login "john.doe"
└──────────── kubelet, RFC3339 UTC ───────────┘ └── klog: no year, no zone ──┘
```

Two stamps, one usable. The kubelet prefix appears because the reader passes `?timestamps=true`; klog's
own carries **no year and no timezone**, so it cannot be resolved to an instant without guessing both.
**Store the kubelet stamp as UTC**, render with `.astimezone()` — the container's `TZ` comes from
`values.timezone`, already wired and already served by `/api/version`
(`{"name":"America/New_York","abbrev":"EDT","utc_offset":"-0400"}`). Verified: `16:56:28Z` displays as
`12:56:28 EDT`.

## 1.2 One attempt is several lines, across two files

| case | lines, in order |
|---|---|
| LDAP success | `basicauth.go:48` failed `"developer"` → `ldap.go:131` searching → `ldap.go:148` found dn= → `basicauth.go:51` **succeeded** `"ldap-local"` |
| LDAP wrong password | … → `ldap.go:148` found dn= → `ldap.go:152` **error binding password … Result Code 49** → `basicauth.go:48` failed |
| LDAP rejected | … → `ldap.go:139` **no entries matching** → `basicauth.go:48` failed |
| unknown user | **identical to rejected** |
| HTPasswd success | `basicauth.go:51` **succeeded** `"developer"` — and nothing else |

Three rules follow, and none is visible from a successful login alone:

1. **A `failed` line is not a failed login.** Every provider tried before the matching one logs one, so
   a *successful* LDAP login contains `failed for login "john.doe"`. Outcome is a property of the group
   of lines for one username in one window (~30–125 ms measured), never of a line.
2. **An HTPasswd login logs no failure at all** — it matches the first provider. The shape per attempt
   is provider-**order** dependent, so no fixed shape can be assumed.
3. **The provider name separates people from break-glass accounts.** `ldap-local` is a directory
   identity; `developer`/`kubeadmin` on a success are HTPasswd.

## 1.3 Code 49 is not a cause — the diagnostic message is

go-ldap formats bind errors as `LDAP Result Code %d %q: %s`, and the last field is the **server's
diagnostic**. Measured on this cluster's OpenLDAP it is **empty**:

```
code=49  text='Invalid Credentials'  diagnostic=' '
```

Active Directory fills it, and that is the only place the real cause appears:

```
LDAP Result Code 49 "Invalid Credentials": 80090308: LdapErr: DSID-0C0903A9,
  comment: AcceptSecurityContext error, data 532, v4563
                                             ^^^ the sub-code
```

**So on AD an expired password, a locked account and a disabled account all arrive as a bare 49.**
Reading the code alone labels an expired password as a wrong password, and sends somebody to reset a
credential that is already correct.

| `data` | meaning | outcome |
|---|---|---|
| `525` | user not found | `rejected` |
| `52e` | invalid credentials | `bad_password` |
| `530`/`531` | not permitted at this time / workstation | `logon_not_permitted` |
| `532` | **password expired** | `password_expired` |
| `533` | account disabled | `account_disabled` |
| `701` | account expired | `account_expired` |
| `773` | must change password at next logon | `must_change_password` |
| `775` | account locked out | `account_locked` |

Result codes other than 49 carry the cause themselves. **OpenLDAP's ppolicy overlay refuses an expired
password with `53 unwillingToPerform`, not 49** — so 49 cannot be treated as "all password failures" on
either directory. `50` insufficient-access → `logon_not_permitted`; `19` constraintViolation →
`must_change_password`.

An **unmapped** sub-code becomes `failed` with the code in `detail`, so a grammar gap is visible rather
than silently mislabelled.

## 1.4 What the log cannot tell you

**Gate-denied and unknown-user are byte-identical.** Both emit only `no entries matching (<filter>)`,
because the identity provider's filter carries the login-gate group. Separating them needs a second
directory search *without* the gate clause — an LDAP read this application does not have and should not
acquire. One honest bucket: **`rejected` — not found or not permitted**. Both are still captured against
the attempted username.

## 1.5 The defect that only shows on a single-provider cluster

A cause line names no user, so it attaches to the attempt in flight. But on a cluster whose **only**
provider is LDAP, the attempt *starts* with `ldap.go:131 searching` — no username exists yet. This lab
only avoids it because htpasswd is tried first and logs a failure, creating the entry.

**On a single-provider cluster — the ordinary production shape — every cause was dropped, including
every expired password.** Fixed in `loginlog.py` by buffering a pre-verdict cause and adopting it at the
verdict that names the user, windowed so an earlier unrelated cause cannot attach to a later person.

## 1.6 Reading the logs

- **`pods` list + `pods/log` get, both namespaced.** There is no Deployment log subresource — verified,
  `GET .../deployments/oauth-openshift/log` returns *"could not find the requested resource"*.
  `oc logs deploy/x` only looks combined; the client resolves to pods. Production runs 2–3 replicas and
  every roll replaces them, so discovery is not optional.
- **`pods/log` in a ClusterRole reads every pod on the cluster** — tokens, connection strings, customer
  data. It stays a `Role` in `openshift-authentication`.
- **`sinceSeconds` works** on the log endpoint, so reads are incremental.

## 1.7 What is not recorded, deliberately

- **The raw line.** `ldap.go` embeds the full bind filter and the user's DN, which disclose the gate
  group's DN and the directory's layout — more sensitive than the username the row is keyed on.
- **Any invented timestamp.** A line without the kubelet prefix is skipped rather than guessed.
- **Anything in `/metrics`.** It is unauthenticated by design, so no username may become a label.
  `openshift_auth_basic_password_count_result` already gives count-only success/error with no usernames,
  and is the right shape for a metric.

## 1.8 Accepted limitations

**Logs die with the pod, and nothing before Debug was enabled exists.** Every oauth roll — cluster
upgrade, node drain, or a toggle of this very setting — starts the window again. A continuous reader
accumulates a durable record *going forward*; the past cannot be reconstructed. This is inherent to the
source and is not a problem to be solved, only surfaced honestly.


## 1.9 The oauth-server AUDIT LOG — a documented alternative source, deliberately not used

Found after the design was written, measured on the live cluster, and **parked rather than adopted**. It is
recorded here because it is a better source in most respects and somebody will find it again; the reason it
was not chosen is a security trade-off, not an oversight.

`oc adm node-logs <node> --path=oauth-server/audit.log` returns structured JSON with authentication
annotations. Measured on this cluster: **36,568 events, 369 carrying
`authentication.openshift.io/decision`, 201 carrying `authentication.openshift.io/username`.** The five
deliberate test logins appear exactly as made:

```
2026-08-07T16:56:28.251  user=john.doe     decision=allow
2026-08-07T16:56:29.439  user=jane.smith   decision=deny
2026-08-07T16:56:29.701  user=bob.wilson   decision=deny
2026-08-07T16:56:30.009  user=nosuchuser   decision=deny
2026-08-07T16:56:30.321  user=developer    decision=allow
```

### Where it is better

| | pod logs (chosen) | audit log |
|---|---|---|
| needs `logLevel: Debug` | **yes** — a cluster-wide write, and a login outage on every toggle at one replica | **no** |
| format | klog text; provider-order noise; multi-line actions | structured JSON, **one event per attempt** |
| outcome | inferred by correlating several lines per username | explicit `allow` / `deny` annotation |
| history | dies with the pod; nothing before Debug was enabled | **~16 months here** — 187 of 201 username events predate Debug, earliest 2025-04-19 |

That fourth row is the striking one: it largely dissolves the "cannot travel back in time" limitation in
§1.8, which is the accepted weakness of the chosen design.

### Why it was not chosen

**The grant.** `oc adm node-logs` is `GET /api/v1/nodes/<node>/proxy/logs/<path>`, so it needs
**`nodes/proxy`** — and that path reads *any* file in the node's log directory. Verified reachable through
the same grant: `kube-apiserver/` audit logs (every API request on the cluster) and the kubelet journal.
That is categorically wider than `pods/log` in one namespace, and unlike the Debug toggle it is a
**standing** capability rather than a one-off write. For an application whose defining invariant is that it
reads narrowly and writes nothing, that is the wrong trade.

**It carries no cause.** `allow`/`deny` only. The `password_expired`, `account_locked`,
`must_change_password` and wrong-password distinctions exist only in the pod log's LDAP result codes and
AD sub-codes — which is what `loginlog.py` already implements and validates. So the two sources are
**complementary, not substitutes**.

### If it is ever revisited

The dedup key changes. `pod_name` is pod-log-specific; an audit event carries `auditID`, unique per
request, which makes deduplication trivial and removes the cross-replica same-instant reasoning entirely.
The parser is unaffected — it would gain a second front end, not a rewrite. The most likely shape is
**both**: the audit log as the authoritative who/when/allow-deny with real history, and the pod log
consulted for the LDAP cause when Debug happens to be on, enriching rows rather than being required.

---

# Part 2 — Still to build

All in this branch. Nothing here exists yet.

| # | piece | where |
|---|---|---|
| 1 | `login_event` table + migration 5 | `gsd/store.py` |
| 2 | reader: `fetch_oauth_pods()` / `fetch_pod_log()` with `sinceSeconds` for incremental reads | `gsd/kube.py` |
| 3 | the continuous capture thread | `gsd/poller.py` or its own module |
| 4 | API endpoint | `gsd/api.py` |
| 5 | UI | `gsd/static/index.html` |
| 6 | test suite, using the **12-line real-log fixture** already extracted | `tests/test_login_capture.py` |

## 2.1 Constraints the build must respect

Each of these is an existing invariant with a test behind it. Breaking one is not a trade-off, it is a
regression.

- **`gsd/storage.py` is a Protocol** and `tests/test_storage_seam.py` forbids SQL or a driver import in
  any other module. New store methods are declared there too.
- **Migrations are `(version, title, [statements])` in `_MIGRATIONS`**, and `_migrate` tolerates exactly
  one error — `"duplicate column name"`. A new table must be `CREATE TABLE IF NOT EXISTS`, or the replay
  against a database that got it from `SCHEMA` raises `"table already exists"` on every start.
- **No foreign keys.** `PRAGMA foreign_keys=ON` is live and no table declares one; a `REFERENCES` would
  be the schema's first and would fail fixtures that write cluster ids never passed to `upsert_cluster`.
- **`_tx()` refuses nesting**; use `self._write()` for anything that may run inside `poll_snapshot()`.
- **`tests/test_api_contract.py`** counts `store.\w+(` per handler: an undecorated handler makes exactly
  one store call. Use `@consistent` or a single query.
- **`tests/test_read_snapshot_scope.py`** forbids any cluster call, await, or yield inside a
  `read_snapshot()` body.
- **UI**: no literal `font-size` in the `<style>` block (`test_type_scale.py`), every colour token
  WCAG-checked in **both** themes (`test_accessibility.py`), and `test_display_timezone.py` slices
  `index.html` by source landmarks — inserting functions in those gaps breaks it.
- **`/metrics` is unauthenticated.** No username may reach it.
- **Leader election**: only the leader may write. A standby must not capture.

## 2.2 Open design questions for the reviewers

1. **Where does the capture loop live?** Its own thread on its own interval, or inside `poll_once`? The
   logs change continuously while groups change on a schedule, so they are different cadences — but a
   second thread per cluster is a second thing to get leader-election right.
2. **Deduplication.** `sinceSeconds` windows overlap, so the same line will be read twice. A natural key
   of `(cluster, user, at, outcome)` with `INSERT OR IGNORE` is the cheap answer — but two genuine
   attempts by one person in the same millisecond would collapse. Is that acceptable, and is the pod
   name part of the key?
3. **Where does the read watermark live?** Per pod, in the database, so a restart does not re-read from
   the beginning — or `sinceSeconds` from the last successful read, accepting overlap?
4. **Retention.** These rows accumulate forever. `dashboard_user_activity` has a prune; should this?
5. **What does the UI show, and where?** A new tab, or a section on Usage? And how is the
   "observed since" boundary from §1.8 made visible without it reading as an excuse?


---

# Part 3 — the implementation, as designed

Two Fable designers at `xhigh`, working independently from Parts 1 and 2. Merged verbatim; **nothing
below is applied yet.** Next step is the Codex `gpt-5.6-sol` pass, then arbitration.

Where the two disagree, the arbiter decides — B named its assumptions about A's store methods at the
top of its section precisely so those can be reconciled. Known seam to check: B assumes six store
methods and a dedup key of `(cluster, user, at, outcome)`, while A specifies
`(cluster_id, pod_name, user_name, at, outcome)` — **pod name included**. That is a real difference and
A's reasoning for it must be read before either is applied.

---

# Designer A — storage, reader, capture loop

Everything below was **built and run**, not sketched: the full test suite passes with these changes
applied (706 passed — 671 existing + 35 new), and the whole stack was run **against the live CRC
cluster read-only**, where it discovered the real oauth pod, backfilled 11 real login attempts on the
first read (`tailLines=10000`, no watermark), set the watermark to the settled horizon
(`2026-08-07T17:30:36.458380Z`), and on the second cycle read incrementally (`sinceSeconds=40`) and
inserted **zero** duplicates. Every empirical claim in the comments is cited to a measurement made
today; where I measured something new, the measurement is stated at the point of use.

---

## Decisions

### Q1 — Where does the capture loop live?

> **Codex:** **FIX-INADEQUATE** — Keeping capture in the existing per-cluster poller thread is the
> smallest correct ownership boundary, but the stated leader guarantee is stronger than the code.
> `poller.py#Poller` explicitly calls the lease check “BEST-EFFORT admission control, NOT a write
> fence”; `poller.py#Poller._run_cluster` checks once. A process that loses leadership while
> `fetch_pod_log()` is in flight can still return and execute A's writes. The standby-from-the-start
> test proves only admission, not loss of leadership during a read. Recheck immediately before the
> write transaction and add the flip-during-read test; document that this narrows, but cannot turn
> the current lease into, a fencing token.

**On the per-cluster poll thread, called by `Poller._run_cluster` immediately after `poll_once`,
every cycle. Its own module (`gsd/logincapture.py`), not inside `poll_once`. No second thread.**

Why: the poll thread already carries the two properties this loop must have and that are easy to get
wrong a second time — the **leader gate** (`poller.py:_run_cluster` checks `elector.is_leader` and
`continue`s *before* `poll_once`; anything after that check in the same iteration is gated for free,
so a standby writes nothing) and the **never-die error discipline**. A second thread per cluster
would need its own leadership re-check on its own tick, its own stop handling, and its own
crash-guard — three new places to introduce the exact class of bug leader election exists to prevent.
The design doc's own worry ("a second thread per cluster is a second thing to get leader-election
right") is the decisive argument.

Not *inside* `poll_once`, though, because `poll_once`'s contract is "the group poll": its failure is
recorded as the cluster's poll outcome, and a capture failure — most likely a 403, since capture
needs RBAC the group poll does not — must **not** mark the cluster unreachable or blank good group
data. That is exactly `refresh_bindings`' contract (`poller.py:refresh_bindings` docstring), so the
capture call gets the same shape: its own function, its own `try`, no `record_poll`.

**Interval: `poll_interval_seconds` (default 60s), not a new knob.** The logs change continuously but
*correctness never depends on cadence* — the per-pod watermark plus the read overlap makes any
cadence lossless up to the `tailLines` cap — so cadence buys only freshness, and this dashboard is
minute-granular everywhere else. The cost of riding the poll thread is serialisation: a slow log read
delays the next group poll by at most `pods × request_timeout` (worst case ~45s at 3 replicas ×
15s). That is the same trade `refresh_bindings` already made for a much larger read (~154 paged
requests at 100× reference scale), and log reads are bounded (see Q-bounds below).

### Q2 — Deduplication key

> **Codex:** CONFIRMED — A's pod-inclusive key is the correct one. A scratch-SQLite run inserting
> `(oauth-a, alice, T, success)`, rereading that same row, then inserting the independent
> `(oauth-b, alice, T, success)` produced insert counts `[1, 0, 1]` and two rows with A's key. With
> B's pod-less key it produced `[1, 0, 0]` and one row. Name the failing sequence the
> **cross-replica same-instant pair**: two requests for the same username with the same outcome and
> parsed microsecond `T`, one served by each replica. B's key drops the second genuine attempt.
> The overlapping-window duplicate is the first two operations and is suppressed by A's key,
> because a particular log line remains a line of the same pod; it is not copied into its peer's
> log. Including `pod_name` therefore does not duplicate the ordinary reread.

**`UNIQUE(cluster_id, pod_name, user_name, at, outcome)` with `INSERT OR IGNORE`. The pod name IS in
the key. `at` carries microseconds.**

- **Why the pod name is in the key:** one attempt's lines live in exactly one replica's log — an
  HTTP login request is served by one pod — so the pod name can never *split* a genuine duplicate
  (overlap re-reads always come from the same pod's log). What it does buy: two genuine
  same-microsecond attempts by one user on two replicas stay two rows. Including it is free-safe;
  excluding it is a collapse with no compensating benefit.
- **Why the "two attempts in the same millisecond collapse" worry is structurally impossible within
  one pod:** the parser itself merges all lines for one username within `ATTEMPT_WINDOW` (1s) into
  ONE attempt (`loginlog.parse`, the `pending` dict is keyed by username). The database key cannot
  split what the parser already merged — the collapse the design doc worried about happens (by
  design, and correctly) at parse time or not at all. Across pods, the pod name in the key keeps
  them distinct. So: yes, acceptable, and moot.
- **Why microseconds in `at`:** attempts are 30–125ms long (design §1.2); a second-resolution key
  would collapse a burst of different users' attempts? No — user is in the key — but it *would*
  collapse two attempts by the *same* user 500ms apart on *different* pods, and it would make
  `ORDER BY at` shuffle a burst. `datetime.fromisoformat` **truncates** the kubelet's nanoseconds to
  microseconds deterministically (verified: `.267663898Z → 267663`), so a re-parse of the same line
  always yields the same string — which is what the dedup key requires.
- **Why `outcome` is in the key:** deliberate visibility. If a bug ever makes a re-parse disagree
  with the first parse, both rows land and the disagreement can be *seen*, rather than the first
  parse silently winning `OR IGNORE`. Same ethos as the parser's `OUTCOME_FAILED` ("a grammar gap is
  visible rather than silently mislabelled"). The watermark discipline (below) makes re-parses
  deterministic, so in correct operation the extra key column never fires.

### Q3 — Where does the read watermark live?

> **Codex:** CONFIRMED — for event capture, but it is not B's proposed product-history boundary.
> On a process restart the persisted per-pod watermark causes both `sinceSeconds` and `tailLines`
> to be sent. On a new database or first sight of a pod there is no watermark, so only
> `tailLines=10_000` bounds the read. The `newest - ATTEMPT_WINDOW` horizon intentionally withholds
> a straddling attempt; the next 30-second overlap completes it, while the unique key absorbs a
> replay after a crash between event insert and watermark update. A separate stable capture-start
> value is still required for B's “Watching since” claim: pruning pod watermarks destroys the
> evidence from which B proposes to derive it.

**Per pod, in the database (`login_capture_watermark`, PK `(cluster_id, pod_name)`) — AND
`sinceSeconds` overlap. They are not alternatives; each covers what the other cannot.**

- **Per pod is required, not optional:** 2–3 replicas serve different attempts and their logs
  advance independently. One cluster-wide watermark has only two aggregations, both wrong: `max`
  jumps ahead on the fastest pod and permanently skips lines on any pod that missed a cycle
  (Terminating during one read, back the next); `min` never advances past the slowest pod, and a pod
  that dies pins it forever, growing every other pod's re-read window without bound.
- **In the database** so a restart resumes with a bounded `sinceSeconds` instead of choosing between
  re-reading from the beginning (unbounded) and a tail-only read that loses the restart window. The
  store is the only place with the same lifetime as the events the watermark guards; it is also
  correct under the multi-replica deployment shape, because above one replica each pod has its own
  database *and* leader election is off (chart guard, `deployment.yaml` line 1-2), so watermarks
  never cross a writer boundary.
- **Overlap on top:** the next read starts `OVERLAP_SECONDS` (30s) *before* the watermark. Two
  reasons, one obvious and one subtle. Obvious: `sinceSeconds` is judged by the kubelet against the
  node's clock; our `now - watermark` arithmetic uses our clock, and the overlap absorbs the skew.
  Subtle: **parse context** — a cause line names no user and can be adopted by a verdict up to
  `ATTEMPT_WINDOW` later (`loginlog.py`, the `orphan` mechanism), so an attempt near the watermark
  re-parses identically only if the window also contains the *full attempt before it*. Overlap ≥
  2×`ATTEMPT_WINDOW` guarantees every attempt in the persisted band arrives whole, with its whole
  predecessor. 30s ≫ 2s, and the price — re-parsing ~30s of lines — dies on the dedup key.
- Watermark rows for pods that no longer exist are **pruned at discovery time**: every oauth roll
  replaces the pod names, and dead names would otherwise accumulate a few rows per roll forever.

### Q4 — Retention

> **Codex:** **FIX-INADEQUATE** — The indexed age predicate and 400-day default are reasonable, but
> an unbounded delete inside every capture cycle is not. Against the proposed schema, a scratch
> SQLite/WAL database with 300,000 rows took 1.551 s to delete a 200,000-row backlog; a subsequent
> zero-row prune took 0.000 s. `store.py#Store._write`, `store.py#Store._tx`, and
> `store.py#Store._reader` show that readers continue under
> WAL but all writers serialize. Normal steady-state pruning will be cheap; first enablement after
> a retention decrease or a long backlog can delay sync-event, membership, and capture writes.
> Delete in bounded chunks (and no more than once per day/cycle interval), with a test for backlog
> progress. Retention also means the UI must distinguish stable capture start from the oldest event
> still retained.

**Yes: pruned, per cluster, on the capture cadence. Default 400 days, `0` disables.
(`loginCaptureRetentionDays` / `GSD_LOGIN_CAPTURE_RETENTION_DAYS`.)**

This table is identifiable personnel data — who tried to log in, when, and how it went — the same
category as `dashboard_user_activity`, which already has a prune and a 400-day default. Matching
that default means the two personnel datasets age out together and one privacy conversation covers
both. Unlike `ActivityRecorder.prune` (which needs a day-guard because its DELETE scans), this
prune is *per cluster* so it is served by the `login_event_lookup (cluster_id, at DESC)` index — a
b-tree seek that costs nothing when there is nothing to delete — and can therefore simply run every
cycle with no state to carry.

Deliberately NOT bounded by row count (a burst of failed logins is exactly when the record matters
most) and NOT disabled by default (an append-only table of usernames with no lifecycle is a
data-protection finding waiting to be written up).

### The bounds question (from the task): what bounds the log read?

> **Codex:** **FIX-INADEQUATE** — The parameter matrix is accurate: first sight is `tailLines` only;
> ordinary reads use both `sinceSeconds` and `tailLines`; neither parameter is ever intentionally
> absent. But `tailLines` is a line-count bound, not a byte or memory bound. The supplied
> `real.log` is 73,371 bytes for 300 lines (244.57 bytes/line, about 2.45 MB at that measured shape
> for 10,000 lines), while Kubernetes log lines have no equivalent fixed byte ceiling. Because the
> proposed code buffers `response.text`, the design needs a streamed byte ceiling or must retract
> its memory-bound claim.

**Both knobs, each against a different failure — and on the first read after a restart, `tailLines`
alone, because nothing else has a sensible value.**

- **Routine read:** `sinceSeconds = int(now − watermark) + 30`, plus `tailLines=10000` as a fuse.
  Measured on the live endpoint: the two compose — `sinceSeconds` filters by time, `tailLines` then
  keeps the newest N of what passed.
- **First read of a pod (fresh install, restart with a new pod, or migration-5 upgrade):** there is
  no watermark, so `sinceSeconds` has no derivable value — too small silently loses history, too
  large is unbounded (the reference pod logs a healthz line every ~1.7s at Debug; days of that is
  tens of MB). So the first read is `tailLines=10000` only: as much history as the cap holds
  (~2.5MB at the measured line shape), then the watermark exists and every subsequent read is
  incremental.
- **When the fuse blows** (`len(lines) >= TAIL_LINES` on an incremental read), the kubelet cut the
  *oldest* lines — the ones between the watermark and the cut — and those attempts are gone. The
  loop logs a WARNING naming the possible loss instead of pretending completeness. On a capped
  *first* read the cut edge is additionally quarantined (first `ATTEMPT_WINDOW` after the oldest
  line is discarded) so a head-truncated attempt cannot be mis-parsed into a wrong row.

Q5 (UI) is Designer B's; the one hook my area supplies for it is `login_event_summary()['first_at']`
— the §1.8 "observed since" boundary, computed from data rather than guessed.

---

## Implementation

All paths are repo-relative to `/Users/olasumbo/gitRepos/group-sync-dashboard`.

### 1. `login_event` + `login_capture_watermark` tables (SCHEMA)

> **Codex:** **FIX-INADEQUATE** — The event columns persist every field of the committed
> `LoginAttempt`, and the pod-inclusive unique constraint is correct. The schema cannot, however,
> implement B's status contract: a per-pod settled-through row has neither stable cluster
> `started_at` nor a last-successful-read value, and dead-pod pruning removes old evidence. Add the
> minimal cluster capture-status state (stable first successful read plus last successful read),
> separate from the replay watermark and retained-event boundary.

- **File**: `local-development/gsd/store.py`
- **Anchor**: inside the `SCHEMA` string, immediately after
  ```
  CREATE INDEX IF NOT EXISTS dashboard_user_activity_by_day
      ON dashboard_user_activity(day DESC);
  ```
  and before the closing `"""` of `SCHEMA`.
- **Code**:

```sql
-- Login attempts parsed from the oauth-server's logs, append-only. Like membership_event,
-- this is accumulated history the cluster cannot re-answer: the source log dies with its
-- pod (design §1.8), so once a line has been read, this row is the only durable record
-- that the attempt happened.
--
-- `at` is the kubelet timestamp of the attempt's FIRST line, stored as fixed-width UTC
-- with microseconds ('%Y-%m-%dT%H:%M:%S.%fZ'), so lexicographic order is chronological —
-- the same contract now_iso() gives the second-resolution columns. Microseconds because
-- attempts arrive well under a second apart (measured 30-125 ms per attempt) and a
-- second-resolution key would collapse a burst into one row.
--
-- The UNIQUE key is the dedup for overlapping reads (design §2.2 Q2): the capture loop
-- re-reads a window around its watermark on purpose, so the same attempt is parsed more
-- than once and INSERT OR IGNORE absorbs it. pod_name is part of the key because one
-- attempt's lines live in exactly ONE pod's log — a request is served by one replica — so
-- the pod can never split a genuine duplicate, while two same-microsecond attempts by one
-- user on two replicas stay distinct. outcome is in the key so that if a bug ever makes a
-- re-parse disagree with the first parse, BOTH rows land and the disagreement is visible,
-- rather than the first parse silently winning.
--
-- What is deliberately NOT here: the raw line (it embeds the bind filter and the user's
-- DN — design §1.7), and any invented timestamp (a line without the kubelet prefix is
-- skipped by the parser, never guessed).
CREATE TABLE IF NOT EXISTS login_event (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    cluster_id          TEXT NOT NULL,
    pod_name            TEXT NOT NULL,  -- the oauth replica whose log carried it
    user_name           TEXT NOT NULL,  -- as attempted; may match no synced member, on purpose
    outcome             TEXT NOT NULL,  -- loginlog.OUTCOME_*
    at                  TEXT NOT NULL,  -- kubelet stamp, UTC, fixed-width microseconds
    provider            TEXT,           -- the provider that decided it; separates people from break-glass
    ldap_result_code    INTEGER,
    detail              TEXT,           -- short and non-sensitive; see loginlog._detail
    observed_at         TEXT NOT NULL,  -- when WE read it; observed_at - at is capture lag
    UNIQUE(cluster_id, pod_name, user_name, at, outcome)
);
CREATE INDEX IF NOT EXISTS login_event_lookup
    ON login_event(cluster_id, at DESC);
CREATE INDEX IF NOT EXISTS login_event_by_user
    ON login_event(cluster_id, user_name, at DESC);

-- How far each oauth pod's log has been SETTLED — parsed, persisted, and safe never to
-- re-read (design §2.2 Q3: per pod, in the database). Per pod because replicas serve
-- different attempts and their logs advance independently: one cluster-wide mark would
-- jump ahead on the fastest pod and permanently skip lines on any pod that missed a
-- cycle. In the database so a restart resumes with a bounded sinceSeconds instead of
-- either re-reading from the beginning or losing the leader-downtime window.
--
-- settled_through is deliberately BEHIND the newest line read, by loginlog.ATTEMPT_WINDOW:
-- an attempt whose lines straddle the end of a read must not be concluded from its first
-- half, so the capture loop withholds the trailing window and re-reads it next cycle.
-- Rows for pods that no longer exist are pruned on discovery — every oauth roll replaces
-- the pod names, and dead names would otherwise accumulate forever.
CREATE TABLE IF NOT EXISTS login_capture_watermark (
    cluster_id          TEXT NOT NULL,
    pod_name            TEXT NOT NULL,
    settled_through     TEXT NOT NULL,  -- same fixed-width format as login_event.at
    updated_at          TEXT NOT NULL,
    PRIMARY KEY(cluster_id, pod_name)
);
```

- **Why it is shaped this way**: `id AUTOINCREMENT` + `UNIQUE(...)` is the `sync_event` shape, not a
  composite PK — the API reads want a stable tiebreaker for same-microsecond ordering
  (`ORDER BY at DESC, id DESC`), and the existing idiom for "idempotent append" in this store is
  `INSERT OR IGNORE` against a UNIQUE constraint. **No foreign keys** (constraint §2.1: the schema
  has none and `PRAGMA foreign_keys=ON` is live, so the first `REFERENCES` would fail fixtures that
  never call `upsert_cluster`). Two indexes because the API needs both access paths (timeline per
  cluster; history per user) and the user index also serves Designer B's per-user drill-down without
  a scan.
- **Gotchas**:
  - *Trigger*: adding the tables only to `SCHEMA`. On an upgraded deployment `CREATE TABLE IF NOT
    EXISTS` no-ops against the existing schema **file** and the new tables never appear (the exact
    failure the migration mechanism's header describes). → *Code*: migration 5 below creates them;
    SCHEMA carries them for fresh databases.
  - *Trigger*: keying `at` at second resolution. Two same-user attempts <1s apart on different pods,
    or a burst, collapse. → *Code*: microsecond fixed-width format, truncation verified
    deterministic.
- **Test**: `TestLoginEventStore.test_overlapping_reads_insert_once`,
  `test_same_instant_on_two_pods_stays_distinct`,
  `test_a_disagreeing_reparse_is_visible_not_swallowed` — complete functions in piece 11.

### 2. Migration 5

> **Codex:** CONFIRMED — A numbered migration is supplied, introduces no foreign keys, and uses
> the same SQL shape as `SCHEMA`, satisfying Part 2.1's migration-shape rule. The proposed migration
> test does not isolate that fact, though: `Store.__init__` executes `SCHEMA` before `_migrate`
> (`store.py#Store.__init__`), so the test can pass even if migration 5 no longer creates these new tables.
> The test must exercise the migration SQL against a v4 fixture before the full current schema is
> applied, or otherwise prove migration 5 itself creates the objects.

- **File**: `local-development/gsd/store.py`
- **Anchor**: appended to `_MIGRATIONS`, immediately after the closing `),` of migration 4 (the
  tuple ending with the comment `# ... the same thing the UI already renders for a user who has
  never logged in.`), before the closing `]`.
- **Code**:

```python
    (
        5,
        "login_event + login_capture_watermark: who logged in, read from the oauth logs",
        [
            # IF NOT EXISTS for the same reason migration 4 states: _migrate tolerates
            # exactly one error, "duplicate column name", so a bare CREATE TABLE would raise
            # "table already exists" when this replays against a fresh database that got the
            # tables from SCHEMA.
            """CREATE TABLE IF NOT EXISTS login_event (
                   id                  INTEGER PRIMARY KEY AUTOINCREMENT,
                   cluster_id          TEXT NOT NULL,
                   pod_name            TEXT NOT NULL,
                   user_name           TEXT NOT NULL,
                   outcome             TEXT NOT NULL,
                   at                  TEXT NOT NULL,
                   provider            TEXT,
                   ldap_result_code    INTEGER,
                   detail              TEXT,
                   observed_at         TEXT NOT NULL,
                   UNIQUE(cluster_id, pod_name, user_name, at, outcome)
               )""",
            """CREATE INDEX IF NOT EXISTS login_event_lookup
                   ON login_event(cluster_id, at DESC)""",
            """CREATE INDEX IF NOT EXISTS login_event_by_user
                   ON login_event(cluster_id, user_name, at DESC)""",
            """CREATE TABLE IF NOT EXISTS login_capture_watermark (
                   cluster_id          TEXT NOT NULL,
                   pod_name            TEXT NOT NULL,
                   settled_through     TEXT NOT NULL,
                   updated_at          TEXT NOT NULL,
                   PRIMARY KEY(cluster_id, pod_name)
               )""",
            # No backfill row in either table, and none is possible: the history starts when
            # the capture starts (design §1.8 — logs die with the pod, and nothing before
            # Debug was enabled exists). An absent watermark row is the signal for the
            # capture loop's bounded first read, so seeding one would be wrong as well as
            # pointless.
        ],
    ),
```

- **Why it is shaped this way**: `(version, title, [statements])` per the mechanism; **every**
  statement is `IF NOT EXISTS` because `_migrate` tolerates exactly one error string
  (`"duplicate column name"`) and a bare `CREATE TABLE`/`CREATE INDEX` replayed against a fresh
  database (which got them from SCHEMA) raises `"table already exists"` on every start —
  constraint §2.1, stated verbatim in migration 4's own comment.
- **Gotchas**:
  - *Trigger*: the indexes in SCHEMA but not in the migration → upgraded databases silently run
    every login read as a table scan, forever, with no error to see. → *Code*: the indexes are in
    both, `IF NOT EXISTS` in both.
  - *Trigger*: seeding a watermark row "to be helpful" → the first read after upgrade would use
    `sinceSeconds` from an invented instant and either miss history or read unboundedly. → *Code*:
    no backfill; absence *is* the first-read signal.
- **Test**: `TestMigration5.test_a_version_4_database_gains_the_tables` (builds a `user_version=4`
  database without the tables, opens `Store`, asserts tables + version + a working write) and
  `test_replaying_against_a_fresh_database_is_a_noop` (open×3). Complete functions in piece 11.
  Verified live: the migration log line `schema migration 5 applied` appeared during the
  live-cluster run.

### 3. Store methods (write + the reads the API needs)

> **Codex:** **FIX-INADEQUATE** — The writes correctly use `_write()` and the event timestamp is fixed
> UTC microseconds. These methods do not match Designer B's named surface: names, inputs, result
> rows, summaries, ungoverned query, and status are all different. `prune_login_events()` is also
> an unbounded single-writer transaction. Reconcile one store contract before either API or tests
> land; the exact break list is in “Codex — additional findings.”

- **File**: `local-development/gsd/store.py`
- **Anchor**: new section inserted after the final line of `user_activity_summary`
  (`return dict(rows[0])`) and before the `# -- queries ------` section header.
- **Code** (complete, as validated):

```python
    # -- login capture ---------------------------------------------------------------------

    def record_login_events(self, cluster_id: str, events: list[dict]) -> int:
        """Append parsed login attempts. Returns how many were NEW.

        INSERT OR IGNORE against the natural key, exactly the record_sync_event idiom: the
        capture loop deliberately re-reads an overlap window around its watermark, so the
        same attempt arrives here more than once and the duplicate must cost nothing. The
        return value is the count of rows actually inserted (sqlite3 accumulates rowcount
        across executemany, and OR IGNOREd rows do not count — verified, not assumed), so
        the caller can log "3 new" rather than "17 parsed, mostly re-reads".

        `_write()`, not `_tx()`: this runs from the poll thread after poll_once, but nothing
        in its contract forbids a future caller sitting inside poll_snapshot(), and _write
        joins an ambient transaction instead of crashing into the nesting guard.
        """
        if not events:
            return 0
        with self._write() as conn:
            cursor = conn.executemany(
                """INSERT OR IGNORE INTO login_event(
                       cluster_id, pod_name, user_name, outcome, at,
                       provider, ldap_result_code, detail, observed_at)
                   VALUES(:cluster_id,:pod_name,:user_name,:outcome,:at,
                          :provider,:ldap_result_code,:detail,:observed_at)""",
                [{**e, "cluster_id": cluster_id} for e in events],
            )
            return cursor.rowcount

    def login_watermarks(self, cluster_id: str) -> dict[str, str]:
        """settled_through per oauth pod, for computing the next read's sinceSeconds."""
        return {
            r["pod_name"]: r["settled_through"]
            for r in self._rows(
                """SELECT pod_name, settled_through FROM login_capture_watermark
                    WHERE cluster_id=?""",
                (cluster_id,),
            )
        }

    def set_login_watermark(self, cluster_id: str, pod_name: str, settled_through: str) -> None:
        """Advance one pod's settled horizon. NEVER moves it backwards.

        The two-argument max() is the same defence record_user_activity uses: both operands
        are fixed-width UTC strings, so lexicographic comparison IS chronological, and a
        read that computed an older horizon — an empty overlap window after an idle pod, or
        a retried cycle landing out of order — widens nothing and rewinds nothing. A rewound
        watermark would make the next read re-settle attempts already recorded, which the
        dedup key absorbs, but it would also re-shrink sinceSeconds' upper bound for no
        reason; monotonic is simply the truthful shape.
        """
        with self._write() as conn:
            conn.execute(
                """INSERT INTO login_capture_watermark(
                       cluster_id, pod_name, settled_through, updated_at)
                   VALUES(?,?,?,?)
                   ON CONFLICT(cluster_id, pod_name) DO UPDATE SET
                       settled_through = max(settled_through, excluded.settled_through),
                       updated_at      = excluded.updated_at""",
                (cluster_id, pod_name, settled_through, now_iso()),
            )

    def prune_login_watermarks(self, cluster_id: str, live_pods: list[str]) -> int:
        """Forget watermarks for pods that no longer exist. Returns how many were dropped.

        Every oauth roll — upgrade, node drain, a logLevel change — replaces the pod names,
        so without this the table grows by a few rows per roll forever. A dead pod's log is
        unreadable, so its watermark answers no future question; the EVENTS it produced are
        untouched, because login_event is the durable record and this table is only read
        position.

        The diff is computed here rather than with NOT IN so the statement count is bounded
        by pods that actually disappeared (normally zero), not by the size of the live list.
        """
        with self._write() as conn:
            known = [
                row["pod_name"]
                for row in conn.execute(
                    "SELECT pod_name FROM login_capture_watermark WHERE cluster_id=?",
                    (cluster_id,),
                )
            ]
            stale = sorted(set(known) - set(live_pods))
            for pod in stale:
                conn.execute(
                    "DELETE FROM login_capture_watermark WHERE cluster_id=? AND pod_name=?",
                    (cluster_id, pod),
                )
        return len(stale)

    def prune_login_events(self, cluster_id: str, before_at: str) -> int:
        """Drop login events strictly before ``before_at`` for one cluster (§2.2 Q4).

        Per cluster rather than global so the DELETE is served by login_event_lookup
        (cluster_id, at DESC) — a b-tree seek that costs nothing when there is nothing to
        prune, which lets the capture loop call this every cycle instead of carrying
        day-guard state the way ActivityRecorder must. ``before_at`` is any fixed-width UTC
        string; both now_iso() second-resolution and the microsecond `at` format compare
        correctly against the stored values because all three are fixed-width with a
        trailing Z.
        """
        with self._write() as conn:
            cursor = conn.execute(
                "DELETE FROM login_event WHERE cluster_id=? AND at < ?",
                (cluster_id, before_at),
            )
            return cursor.rowcount

    def _login_event_where(
        self, cluster_id: str, user_name: str | None, outcome: str | None, since: str | None
    ) -> tuple[str, list]:
        """The WHERE shared by the row query and its summary, built once.

        Same reason as _direct_user_binding_where and _user_activity_where: a summary
        computed from a different predicate than the rows it sits beside is how
        "showing 50 of 30" reaches a page."""
        where, params = ["cluster_id=?"], [cluster_id]
        if user_name:
            where.append("user_name=?")
            params.append(user_name)
        if outcome:
            where.append("outcome=?")
            params.append(outcome)
        if since:
            where.append("at >= ?")
            params.append(since)
        return " WHERE " + " AND ".join(where), params

    def login_events(
        self,
        cluster_id: str,
        user_name: str | None = None,
        outcome: str | None = None,
        since: str | None = None,
        limit: int = 200,
    ) -> list[dict]:
        """Captured login attempts, newest first. BOUNDED.

        The caller passes limit+1 to learn whether it truncated — the sync_events /
        list_users idiom, one paging shape in the codebase rather than two. Ordered by
        (at DESC, id DESC): `at` is the attempt's instant, and id breaks the tie for two
        attempts in the same microsecond so paging cannot shuffle them between requests.
        """
        where, params = self._login_event_where(cluster_id, user_name, outcome, since)
        sql = (
            """SELECT user_name, outcome, at, provider, ldap_result_code, detail,
                      pod_name, observed_at
                 FROM login_event""" + where + " ORDER BY at DESC, id DESC LIMIT ?"
        )
        params.append(limit)
        return self._rows(sql, params)

    def login_event_summary(
        self, cluster_id: str, user_name: str | None = None, since: str | None = None
    ) -> dict:
        """Totals over the WHOLE captured set the caller may see, ignoring any row limit.

        `first_at` is the §1.8 "observed since" boundary: the oldest attempt this dashboard
        has ever captured on this cluster. The UI must surface it, because the record starts
        when capture started — an empty window before first_at is absence of observation,
        not absence of logins, and only this value lets the page say so without guessing.
        """
        where, params = self._login_event_where(cluster_id, user_name, None, since)
        rows = self._rows(
            """SELECT COUNT(*) AS attempts,
                      COUNT(DISTINCT user_name) AS distinct_users,
                      SUM(CASE WHEN outcome = 'success' THEN 1 ELSE 0 END) AS successes,
                      MIN(at) AS first_at,
                      MAX(at) AS last_at
                 FROM login_event""" + where,
            params,
        )
        row = dict(rows[0])
        row["successes"] = row["successes"] or 0
        row["failures"] = row["attempts"] - row["successes"]
        return row
```

- **Why it is shaped this way**: writes use `_write()` (constraint §2.1: `_tx()` refuses nesting;
  `_write` joins an ambient `poll_snapshot` if one ever encloses a caller). Reads use `_rows()` only
  — a bare `self._conn.execute` in a query method is a bug per `_rows`' own docstring. The shared
  WHERE builder is the codebase's third instance of the "count and rows must share a predicate"
  idiom, named in both prior instances as the fix for "showing 50 of 30". The reads give Designer
  B's handler the `@consistent` + `limit+1` shape the API contract test expects (rows + scalar
  summary = two store calls under one snapshot).
- **Gotchas**:
  - *Trigger*: `SUM(...)` over zero rows is `NULL` in SQLite → a fresh cluster's summary would say
    `successes: None` and arithmetic downstream would TypeError. → *Code*: `or 0` and derived
    `failures`. Pinned by `test_an_empty_summary_has_zero_failures_not_none`.
  - *Trigger*: `executemany().rowcount` semantics — if it counted attempted rows, the "N new" log
    and the loop's insert accounting would lie. → *Verified before shipping*: on this Python/SQLite,
    rowcount accumulates inserted rows only (`[dup among 3] → 2`, `[all dups] → 0`).
  - *Trigger*: a watermark UPDATE racing with itself is impossible today (one leader, one thread per
    cluster), but an out-of-order write from a *future* refactor would rewind the horizon. →
    *Code*: `max(settled_through, excluded.settled_through)` makes rewind structurally impossible;
    fixed-width strings make the comparison chronological.
  - *Trigger*: pruning watermarks with `NOT IN (...)` hits `SQLITE_LIMIT_VARIABLE_NUMBER` cliffs the
    codebase has already met once (`sync_members`' 500-chunk comment). → *Code*: diff in Python;
    statement count bounded by *disappeared* pods (normally zero).
- **Test**: `TestLoginEventStore` (7 functions), `TestWatermarks` (3 functions) — complete in
  piece 11.

### 4. `StorageBackend` Protocol additions

> **Codex:** CONFIRMED — for A's proposed Store surface. Declaring every A method preserves the
> SQL seam enforced by `tests/test_storage_seam.py`. It does not make B's six differently named
> calls legal; the final, reconciled reader methods and capture-status method must also be declared
> here in the same change that implements them.

- **File**: `local-development/gsd/storage.py`
- **Anchor**: inside `class StorageBackend`, immediately after the `user_activity` declaration (the
  last method of the `# -- dashboard usage` section), before the class ends.
- **Code**:

```python
    # -- login capture -------------------------------------------------------------------
    #
    # The capture loop's writes and the API's reads over login_event. The watermark pair
    # is part of the contract, not an implementation detail: "how far has this pod's log
    # been settled" must survive a restart in the same store as the events it guards, or a
    # second backend would silently turn every restart into a bounded-tail first read and
    # lose the leader-downtime window.

    def record_login_events(self, cluster_id: str, events: list[dict]) -> int: ...
    def login_watermarks(self, cluster_id: str) -> dict[str, str]: ...
    def set_login_watermark(
        self, cluster_id: str, pod_name: str, settled_through: str
    ) -> None: ...
    def prune_login_watermarks(self, cluster_id: str, live_pods: list[str]) -> int: ...
    def prune_login_events(self, cluster_id: str, before_at: str) -> int: ...
    def login_events(
        self,
        cluster_id: str,
        user_name: str | None = None,
        outcome: str | None = None,
        since: str | None = None,
        limit: int = 200,
    ) -> list[dict]: ...
    def login_event_summary(
        self, cluster_id: str, user_name: str | None = None, since: str | None = None
    ) -> dict: ...
```

- **Why it is shaped this way**: the signatures are **byte-identical** to the `Store`
  implementations because `tests/test_storage_seam.py::test_the_declared_signatures_match_the_implementation`
  compares `inspect.signature(...).parameters` between Protocol and Store — parameter names,
  defaults and annotations all participate. (Ran it: passes.) `_login_event_where` is deliberately
  *not* declared: it is an implementation detail with SQL-shaped output, not a caller surface.
- **Gotchas**:
  - *Trigger*: declaring the methods with drifted defaults (say `limit: int = 100`) — passes
    `isinstance`, fails the seam suite, and would TypeError a second backend. → *Code*: copied
    verbatim; the seam test is the regression net.
- **Test**: the existing seam suite is the test — `test_store_satisfies_the_backend_protocol`,
  `test_the_protocol_declares_every_method_the_application_calls` (which now also scans
  `logincapture.py`, see piece 10) and `test_the_declared_signatures_match_the_implementation`. All
  green with these additions.

### 5. The reader: `fetch_oauth_pods()` / `fetch_pod_log()` (+ the label constants)

> **Codex:** **FIX-INADEQUATE** — Bypassing `_get()` is mandatory and using `_client()` is safe:
> `kube.py#ClusterClient._client` only supplies TLS/token client setup, whereas
> `kube.py#ClusterClient._get` always calls `response.json()` and therefore cannot carry the text
> log response.
> The proposed direct `client.get()` plus `response.text` buffers the complete response, so the
> line cap is not a byte-memory cap. Error handling is also too broad: every 400 and 403 becomes an
> indistinguishable debug-only `None`. A normal terminating/not-ready 400 should leave the
> watermark unchanged and retry next cycle, but an unexpected 400 (including a future ambiguous
> container request) and a pods/log 403 must be visible at warning/info level with the Kubernetes
> Status reason. Keep 404/expected-not-ready roll noise benign; do not hide permanent failures.

- **File**: `local-development/gsd/kube.py`
- **Anchor (constants)**: immediately after the line
  `CLUSTERROLEBINDING_API = "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings"`.
- **Code (constants)**:

```python
# The label the cluster-authentication-operator stamps on the oauth-server's pods.
# Measured on the reference cluster: `app=oauth-openshift` (plus anti-affinity and
# pod-template-hash, which are not identity). Discovery filters on it CLIENT-SIDE rather
# than with a labelSelector param so that `_list_all`'s paging keys stay the two it has —
# a selector would be a third thing to carry through the continue-token loop for a
# namespace that holds a handful of pods.
OAUTH_POD_LABEL_KEY = "app"
OAUTH_POD_LABEL_VALUE = "oauth-openshift"
```

- **Anchor (methods)**: inside `class ClusterClient`, immediately **before**
  `def fetch_bindings(self) -> list[BindingView]:` (i.e. after `fetch_users` ends).
- **Code (methods)**:

```python
    def fetch_oauth_pods(self, namespace: str) -> list[str] | None:
        """Names of the oauth-server pods in `namespace`, or None when we may not list them.

        Discovery is not optional: there is no Deployment log subresource — verified,
        `GET .../deployments/oauth-openshift/log` returns "could not find the requested
        resource" — and production runs 2-3 replicas that every roll replaces, so the pod
        names cannot be configured, only discovered per cycle.

        403-TOLERANT, the fetch_users shape, and for the same reason: the chart's
        loginCapture grant is optional and lives in a namespace the chart does not own, so
        an install that enabled capture in the app config without the Role — or whose
        cluster policy rejected objects in openshift-* — gets a 403 here, and that must
        degrade to "no capture" rather than fail a poll that has nothing to do with it.
        None (forbidden) is deliberately distinct from [] (allowed, nothing matched): the
        first means the grant is missing, the second that the namespace holds no oauth
        pods, and the caller logs different advice for each.

        Terminating pods are deliberately INCLUDED: a pod with deletionTimestamp set still
        serves its log until the container is gone, and its final lines are the last chance
        to read the attempts it handled — the log dies with it (design §1.8). A pod that
        vanishes between this list and the log read 404s there, which fetch_pod_log treats
        as benign.
        """
        path = f"/api/v1/namespaces/{namespace}/pods"
        with self._client() as client:
            try:
                items = self._list_all(client, path)
            except ClusterError as exc:
                # Anchored on the outcome AND the path, exactly as fetch_users argues: the
                # pairing survives someone adding a second call here later.
                if exc.outcome == FORBIDDEN and path in exc.message:
                    log.debug(
                        "%s: not permitted to list pods in %s — login capture unavailable",
                        self.cluster.name, namespace,
                    )
                    return None
                raise
        names = sorted(
            name
            for obj in items
            if (((obj.get("metadata") or {}).get("labels") or {}).get(OAUTH_POD_LABEL_KEY)
                == OAUTH_POD_LABEL_VALUE)
            and (name := (obj.get("metadata") or {}).get("name"))
        )
        log.debug("found %d oauth pod(s) in %s on %s", len(names), namespace, self.cluster.name)
        return names

    def fetch_pod_log(
        self,
        namespace: str,
        pod_name: str,
        since_seconds: int | None = None,
        tail_lines: int | None = None,
    ) -> str | None:
        """One pod's log as TEXT with kubelet timestamps, or None when it is benignly gone.

        DOES NOT go through _get(), and must not: _get parses every 200 body as JSON, and
        this endpoint returns text/plain — measured on the live cluster, `content-type:
        text/plain` even when the request says `Accept: application/json` — so routing it
        through _get would turn every successful read into ClusterError("non-JSON
        response"). The plain `_client()` is still used unchanged: the apiserver ignores
        the Accept header here rather than rejecting it, so the shared client needs no
        special headers. Error statuses DO come back as JSON Status objects (measured for
        both 404 and 400), but they are classified below by status code alone and the body
        is only quoted into messages.

        `timestamps=true` is unconditional: the kubelet's RFC3339 prefix is the only
        usable instant on the line — klog's own stamp has no year and no timezone (design
        §1.1) — and loginlog.parse skips any line without it rather than guessing.

        THE BENIGN FAILURES RETURN None instead of raising, because they are the ordinary
        weather of reading logs in a namespace whose pods roll:
          * 404 — the pod vanished between discovery and this read (Terminating when
            listed, gone now). Its lines are unrecoverable whatever we do.
          * 400 — the container has not started ("is waiting to start: ContainerCreating"),
            or the pod has a container shape this reader did not name. No lines exist YET;
            the next cycle reads from the same watermark and misses nothing.
        Both leave the caller's watermark untouched. 403 also degrades — the grant is
        optional, the fetch_users argument — while 401 and everything else still raise:
        a bad token or a 5xx is a cluster problem, not a pod lifecycle.

        The `container` param is deliberately omitted. The oauth pod has exactly one
        container (measured: `oauth-openshift`), so the apiserver resolves it; naming it
        would break on a rename while omitting it breaks on a sidecar, and of the two only
        the rename has ever been plausible for a core payload pod. If a sidecar ever
        appears, the read 400s into the benign path above and the watermark stalls —
        visible in login_capture_watermark.updated_at rather than silently wrong.
        """
        path = f"/api/v1/namespaces/{namespace}/pods/{pod_name}/log"
        params: dict[str, Any] = {"timestamps": "true"}
        if since_seconds is not None:
            params["sinceSeconds"] = int(since_seconds)
        if tail_lines is not None:
            params["tailLines"] = int(tail_lines)
        with self._client() as client:
            try:
                response = client.get(path, params=params)
            except httpx.HTTPError as exc:
                raise ClusterError(UNREACHABLE, f"{type(exc).__name__}: {exc}") from exc
        if response.status_code == 401:
            raise ClusterError(AUTH_FAILED, "401 Unauthorized — token invalid or expired")
        if response.status_code == 403:
            log.debug(
                "%s: not permitted to read %s — login capture unavailable",
                self.cluster.name, path,
            )
            return None
        if response.status_code in (400, 404):
            log.debug(
                "%s: no log from %s (HTTP %d: %s)",
                self.cluster.name, path, response.status_code, response.text[:200],
            )
            return None
        if response.status_code >= 400:
            raise ClusterError(
                UNREACHABLE, f"HTTP {response.status_code} on {path}: {response.text[:200]}"
            )
        return response.text
```

- **Why it is shaped this way**:
  - **The TEXT question, answered exactly**: the read goes through `_client()` (unchanged — the
    measured endpoint ignores `Accept: application/json` and returns `content-type: text/plain`
    rather than 406ing) but **must not** go through `_get()`, because `_get` ends in
    `response.json()` and would classify every successful log read as
    `ClusterError(UNREACHABLE, "non-JSON response …")`. The error mapping (401/403/4xx/HTTPError)
    mirrors `_get`'s so the outcome taxonomy stays uniform.
  - `_list_all` handles pagination for the pods list, per the brief; the label filter is
    client-side so `_list_all`'s continue-token loop keeps exactly its two params.
  - Sorted names → stable iteration order → deterministic logs and tests.
- **Gotchas**:
  - *Trigger*: a Terminating pod. Excluded at discovery, its last seconds of logins are lost even
    though the log is still readable. → *Code*: discovery keeps every labelled pod regardless of
    phase or deletionTimestamp; the 404/400 tolerance handles the ones that are truly gone.
  - *Trigger*: a pod that 400s because the container is not ready (rolls, `ContainerCreating`) —
    treating it as a poll failure would degrade the whole cluster card for routine weather. →
    *Code*: 400 and 404 return `None`; caller skips the pod and leaves its watermark untouched.
  - *Trigger*: swallowing 403 by bare status alone hides a real RBAC break on some *other* future
    call in the same method. → *Code*: discovery anchors FORBIDDEN on outcome+path (the
    `fetch_users` pairing); the log read is a single fixed path.
  - *Trigger*: a 500 whose JSON body happens to contain "not found" — must not be misread as a
    vanished pod. → *Code*: classification is by status code only, never by body text.
- **Test**: `TestFetchOauthPods` (4 functions) and `TestFetchPodLog` (4 functions), via
  `httpx.MockTransport` — the `test_no_groupsync_operator` idiom — complete in piece 11. Also
  proven live: 200-text, 404→None (`oauth-openshift-000-gone`), params
  `timestamps=true&sinceSeconds=…&tailLines=…` visible in the httpx request log.

### 6. Namespace/flag wiring: `gsd/config.py`

> **Codex:** **FIX-INADEQUATE** — A's three fields are coherent, but the combined design also reads
> B's `login_capture_htpasswd_providers`, which this Settings change neither declares nor wires.
> The chart proposal below also exposes only enabled/namespace, so retention is not actually
> configurable from the chart despite being described as a setting. Choose the minimal final
> settings surface and carry every field end-to-end in one change.

- **File**: `local-development/gsd/config.py`
- **Anchor (fields)**: in `class Settings`, immediately after
  `user_activity_retention_days: int = 400`.
- **Code (fields)**:

```python
    # Login capture: read the oauth-server's pod logs and record who logged in.
    # Off by default for the same reason the chart's loginCapture.enabled is: the read
    # grant is optional and the Debug prerequisite is a separate, deliberate decision.
    # The chart writes both values from .Values.loginCapture, so one values block drives
    # the RBAC and the app together; enabling only one of the two degrades loudly (the
    # pods list 403s and the poller says which grant is missing) rather than failing.
    login_capture_enabled: bool = False
    login_capture_namespace: str = "openshift-authentication"
    """Where the oauth-server runs — the fixed namespace OpenShift installs it into.
    Configurable only because the chart's loginCapture.namespace is, for unusual clusters;
    the two must name the SAME namespace or the Role guards a namespace nobody reads."""
    login_capture_retention_days: int = 400
    """How long captured login attempts are kept; 0 disables pruning. Defaults to the
    dashboard_user_activity retention so the two personnel datasets age out together."""
```

- **Anchor (loading)**: in `load_settings`'s `return Settings(...)` call, immediately after the
  `user_activity_retention_days=_num_setting(...)` entry, before the closing `)`.
- **Code (loading)**:

```python
        login_capture_enabled=_bool_setting(
            raw, "GSD_LOGIN_CAPTURE_ENABLED", "loginCaptureEnabled", False
        ),
        login_capture_namespace=os.environ.get("GSD_LOGIN_CAPTURE_NAMESPACE")
        or str(raw.get("loginCaptureNamespace", "openshift-authentication")),
        login_capture_retention_days=_num_setting(
            raw, "GSD_LOGIN_CAPTURE_RETENTION_DAYS", "loginCaptureRetentionDays", 400, int
        ),
```

- **How the namespace reaches the app, traced end to end** (each hop verified by running it):
  1. `charts/.../values.yaml` → `loginCapture.namespace: openshift-authentication` (exists, shipped).
  2. `templates/login-capture-rbac.yaml` → Role/RoleBinding rendered into that namespace (shipped).
  3. `templates/configmap.yaml` → `loginCaptureNamespace: "…"` into `clusters.yaml` (piece 7 —
     **this hop did not exist and is the integration this area adds**).
  4. The ConfigMap is mounted at `/etc/gsd/clusters.yaml` and `GSD_CONFIG` points there
     (`deployment.yaml`, already shipped); the `checksum/config` pod annotation restarts the pod on
     change, so a namespace edit takes effect without manual restarts.
  5. `config.load_settings` → `Settings.login_capture_namespace` (this piece), with
     `GSD_LOGIN_CAPTURE_NAMESPACE` as the env override, following the `GSD_DB_PATH` precedent.
  6. `Poller._run_cluster` → `capture_logins(..., settings.login_capture_namespace, ...)` →
     `client.fetch_oauth_pods(namespace)` (pieces 8–9).
- **Why it is shaped this way**: `_bool_setting` for the flag because `bool("false")` is `True` —
  the module's own comment; a plain cast on the env var would turn an explicit disable into an
  enable, in the direction that grants. `_num_setting` for retention (malformed → default + a log
  line, matching every other numeric).
- **Gotchas**:
  - *Trigger*: enabling in the chart without re-rendering the ConfigMap (or vice versa) → one half
    on. → *Code*: both keys derive from the *same* values block (piece 7) so a values file cannot
    split them; if the RBAC objects are rejected by namespace policy, the reader logs which grant is
    missing every cycle instead of silently idling.
- **Test**: `TestSettingsWiring` (3 functions: defaults; ConfigMap keys land; env wins and
  `"false"` cannot enable) — complete in piece 11.

### 7. Chart ConfigMap wiring — INTEGRATION OUTSIDE MY AREA (2 keys + comment)

> **Codex:** CONFIRMED — for these two keys. `helm template review charts/group-sync-dashboard
> --set ingress.host=review.example.test` rendered no login-capture ConfigMap keys before this
> edit, while the existing enabled/custom-namespace Role and RoleBinding rendered as expected.
> These additions close the enabled/namespace application-config gap. They do not wire A's
> retention setting or B's HTPasswd-provider setting, which still must be reconciled.

- **File**: `charts/group-sync-dashboard/templates/configmap.yaml`
- **Anchor**: immediately after
  `userActivityRetentionDays: {{ .Values.config.userActivity.retentionDays }}` and before
  `leaderElection: …`.
- **Code**:

```yaml
    # ONE values block drives both halves of login capture: loginCapture.enabled renders
    # the Role/RoleBinding in the oauth namespace AND turns the reader on here, so the two
    # cannot drift apart in a values file. If the RBAC objects are rejected by a policy on
    # openshift-* namespaces, the reader degrades: the pods list 403s and the poller logs
    # which grant is missing, every cycle.
    loginCaptureEnabled: {{ .Values.loginCapture.enabled }}
    loginCaptureNamespace: {{ .Values.loginCapture.namespace | quote }}
```

- **Why it is shaped this way**: not a chart redesign — the `loginCapture` values block and the
  RBAC template are shipped and untouched; this is the one missing hop between them and the app
  (trace in piece 6). No new values keys are introduced.
- **Gotchas**:
  - *Trigger*: `tests/test_chart_strategy.py::TestLoginCaptureReadsOneNamespaceOnly::test_nothing_renders_by_default`
    asserts the literal string `login-capture` appears **nowhere** in a default render. A first
    draft of the comment cited `login-capture-rbac.yaml` by filename and failed it. → *Code*: the
    comment avoids the hyphenated literal; the *keys* render in every ConfigMap (with
    `false`/default values), which is correct — the flag must exist for the app to read — and does
    not trip the test. This is measured, not assumed: the failure was observed and the fix
    re-verified.
  - *Trigger*: an unquoted namespace value would let YAML re-type an unusual namespace. → *Code*:
    `| quote`, matching `leaderLeaseName`.
- **Test**: `TestLoginCaptureConfigWiring` — one new method appended to the *existing*
  `TestLoginCaptureReadsOneNamespaceOnly` class in `tests/test_chart_strategy.py` (anchor: insert
  immediately before `def test_the_read_binds_to_the_dashboard_not_the_job_identity`):

```python
    def test_one_values_block_drives_the_rbac_and_the_reader_together(self):
        """loginCapture.enabled must reach the APP through the ConfigMap, not only render
        the Role: an RBAC grant with the reader off captures nothing, a reader with no
        grant 403s forever, and both halves reading the SAME values key is what stops a
        values file enabling one without the other. The namespace rides along for the same
        reason — the Role and the pods-list call must name the same namespace."""
        ok, out = render()
        assert ok, out
        assert "loginCaptureEnabled: false" in out, "the reader flag is missing or defaulted on"
        ok, out = render(**self.ON, loginCapture__namespace="custom-auth")
        assert ok, out
        assert "loginCaptureEnabled: true" in out
        assert 'loginCaptureNamespace: "custom-auth"' in out
        role = [d for d in self._docs(out)
                if d.get("kind") == "Role" and "login-capture" in d["metadata"]["name"]][0]
        assert role["metadata"]["namespace"] == "custom-auth", (
            "the Role and the reader disagree about the namespace"
        )
```

  Verified with real `helm template` runs (default render carries
  `loginCaptureEnabled: false`; enabled render carries `true` + the namespace + the RBAC objects).

### 8. The capture loop: `gsd/logincapture.py` (NEW module, complete)

> **Codex:** **FIX-INADEQUATE** — The settle horizon, strict `at > old_watermark` replay filter, and
> pod-keyed insert correctly handle lines split across two reads and overlap rereads. The complete
> production path is still unsafe as written: it has no leadership recheck after network I/O,
> inherits the unbounded text buffering and overbroad error suppression, and performs an
> unbounded retention delete in the poller's single-writer process. The capped-first-read
> quarantine is defensible, but its “at most one attempt” claim is false: the strict
> `at > oldest + ATTEMPT_WINDOW` filter discards every attempt beginning in that second. A scratch
> run with starts at +100, +400, +900, and +1100 ms discarded the first three. Warn/count this as
> bounded first-read loss and test multiple concurrent attempts. Fix these issues before calling
> the module complete.

- **File**: `local-development/gsd/logincapture.py` (new)
- **Anchor**: n/a — whole file.
- **Code**:

```python
"""The login-capture loop: oauth pod logs -> loginlog.parse -> login_event rows.

WHERE THIS RUNS (design §2.2 Q1). On the per-cluster POLL THREAD, called by
Poller._run_cluster immediately after the group poll, every cycle. Deliberately NOT a
second thread: the poll thread already carries the two properties this loop must have and
that are easy to get wrong twice — the leader gate (a standby `continue`s before poll_once
and so never reaches this either; a standby writes nothing) and the never-die error
discipline. The price is serialisation: a slow log read delays the next group poll by at
most pods x request_timeout. That is the same trade refresh_bindings already made for a
far larger read (154 paged requests at 100x scale), and the log reads are bounded below.

THE INTERVAL is therefore poll_interval_seconds (default 60s). Logs change continuously
but correctness never depends on cadence — the watermark plus the overlap makes any
cadence lossless up to the tailLines cap — so cadence buys only freshness, and this
dashboard is minute-granular everywhere else. What a longer gap costs is bounded too: the
window since the watermark just grows, and one read catches up.

HOW A READ IS BOUNDED. Both knobs, each for a different failure:
  * sinceSeconds — computed from the pod's stored watermark plus OVERLAP_SECONDS, so a
    routine read covers only the unread window (measured: sinceSeconds works on the
    endpoint, and composes with tailLines — sinceSeconds filters, tailLines then keeps the
    newest N of what passed).
  * tailLines=TAIL_LINES — the memory ceiling. On the FIRST read of a pod there is no
    watermark and no sensible sinceSeconds (the pod may hold days of Debug logs — the
    reference pod logs a healthz line every ~1.7s, ~50k lines/day of noise alone), so the
    first read is tailLines-only: as much history as the cap holds, then the watermark
    exists and every later read is incremental. On incremental reads the cap is a fuse: if
    a window ever exceeds it the OLDEST lines are silently cut by the kubelet, so hitting
    the cap logs a WARNING naming the possible loss instead of pretending completeness.

THE WATERMARK DISCIPLINE (design §2.2 Q3, and the straddle question). One attempt is
several lines over ~30-125ms, so a read can end mid-attempt, and concluding from half the
lines records the wrong outcome (a success whose trailing verdict was cut parses as
`failed`). Three rules make re-reads deterministic and loss-free:

  1. SETTLE ONLY BEHIND THE HORIZON: attempts with at <= newest_line - ATTEMPT_WINDOW.
     The parser expires an attempt ATTEMPT_WINDOW after its first line, so every line an
     attempt inside the horizon can have is already in this read — its parse is final.
     Anything younger is withheld and re-read next cycle.
  2. ADVANCE THE WATERMARK TO THE HORIZON, not to the newest line, so the withheld band
     is inside the next read's window by construction, not by luck.
  3. RE-READ WITH CONTEXT: the next read starts OVERLAP_SECONDS before the watermark.
     The overlap exists for two reasons — clock skew between this process and the node
     stamping the lines (sinceSeconds is judged by the kubelet's clock), and parse
     context: a cause line carries no username and can be adopted by a verdict up to
     ATTEMPT_WINDOW later, so an attempt near the watermark parses identically only if
     the window also contains the full attempt BEFORE it. OVERLAP_SECONDS >> 2x
     ATTEMPT_WINDOW guarantees both attempts arrive whole.
     Rows already settled re-parse identically and die on the dedup key; rows at <=
     watermark are filtered before the insert anyway.

WHAT SURVIVES WHAT. A dashboard restart: watermarks are in the database, so reads resume
incrementally. A pod restart-in-place: the new container's lines carry later wall-clock
stamps, so the same watermark still bounds them. An oauth roll: new pod names get a
first read, dead names are pruned. A pod vanishing mid-read: fetch_pod_log returns None,
this cycle skips it, the prune forgets it once discovery stops listing it. The one
honest loss is the source's own (design §1.8): lines a dead pod never got read for are
gone, and nothing here can invent them.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from .config import ClusterConfig
from .kube import ClusterClient, ClusterError
from .loginlog import ATTEMPT_WINDOW, parse, parse_timestamp
from .storage import StorageBackend
from .timeutil import now_iso

log = logging.getLogger(__name__)

# See the module docstring. The floor for OVERLAP is 2x ATTEMPT_WINDOW (parse context);
# the rest is clock-skew margin between this process and the kubelet judging sinceSeconds.
# Generous is cheap: the overlap re-reads ~30s of lines that the dedup key absorbs.
OVERLAP_SECONDS = 30

# Per pod, per cycle. 10k lines is ~2.5 MB of the measured line shape — a bounded parse,
# not a bounded poll stall. As a first-read backfill it holds hours-to-days of quiet log;
# as an incremental fuse it means sustained >160 lines/s between 60s cycles before the
# warning below ever fires.
TAIL_LINES = 10_000

_MICRO = "%Y-%m-%dT%H:%M:%S.%fZ"


def _iso_micro(dt: datetime) -> str:
    """Fixed-width UTC with microseconds, the login_event.at / watermark format.

    Fixed width is load-bearing: the store compares these lexicographically (the
    watermark's max(), the retention prune, every ORDER BY at). now_iso() is deliberately
    second-resolution and cannot key attempts that land 30ms apart, so this module owns
    the finer format. datetime.fromisoformat TRUNCATES the kubelet's nanoseconds to
    microseconds (verified: .267663898Z -> 267663), deterministically, so a re-parse of
    the same line always yields the same string — which is what the dedup key requires.
    """
    return dt.astimezone(UTC).strftime(_MICRO)


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def capture_logins(
    store: StorageBackend,
    cluster: ClusterConfig,
    timeout: float,
    namespace: str,
    retention_days: int = 400,
) -> None:
    """One capture cycle for one cluster. Never raises for cluster-side failures.

    Mirrors refresh_bindings' contract: a capture failure — most likely a 403, since this
    needs RBAC the group poll does not — must not mark the cluster unreachable or blank
    perfectly good group data. It is logged and retried next cycle.
    """
    client = ClusterClient(cluster, timeout=timeout)
    try:
        pods = client.fetch_oauth_pods(namespace)
    except ClusterError as exc:
        log.warning(
            "login capture for %s failed listing pods in %s: %s (%s) — group data is "
            "unaffected", cluster.name, namespace, exc.message, exc.outcome,
        )
        return
    if pods is None:
        # Same cadence and level as poll_once's fetch_users message: INFO every cycle is
        # the price of a misconfiguration staying discoverable in the log.
        log.info(
            "%s: not permitted to list pods in %s — login capture is enabled in the app "
            "but the read grant is missing. loginCapture.enabled=true renders the "
            "Role/RoleBinding there (chart: login-capture-rbac.yaml).",
            cluster.name, namespace,
        )
        return
    if not pods:
        log.warning(
            "%s: no pods labelled app=oauth-openshift in %s — is loginCapture.namespace "
            "pointing at the right namespace?", cluster.name, namespace,
        )
        return

    # Dead pods first, so the watermark table tracks reality before this cycle adds to it.
    dropped = store.prune_login_watermarks(cluster.name, pods)
    if dropped:
        log.info("%s: forgot %d watermark(s) for replaced oauth pod(s)", cluster.name, dropped)

    watermarks = store.login_watermarks(cluster.name)
    observed_at = now_iso()
    for pod in pods:
        try:
            _capture_pod(store, client, cluster.name, namespace, pod,
                         watermarks.get(pod), observed_at)
        except ClusterError as exc:
            # Per pod, so one unreadable replica cannot cost the others their cycle.
            log.warning(
                "login capture for %s pod %s failed: %s (%s) — other pods are unaffected",
                cluster.name, pod, exc.message, exc.outcome,
            )

    if retention_days > 0:
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).strftime(_MICRO)
        removed = store.prune_login_events(cluster.name, cutoff)
        if removed:
            log.info("%s: pruned %d login event(s) older than %d days",
                     cluster.name, removed, retention_days)


def _capture_pod(
    store: StorageBackend,
    client: ClusterClient,
    cluster_id: str,
    namespace: str,
    pod: str,
    watermark: str | None,
    observed_at: str,
) -> None:
    """Read one pod's unread window, persist the settled attempts, advance the watermark."""
    if watermark is None:
        # First sight of this pod: no watermark, so neither knob has a derivable value and
        # the read is tailLines-bounded backfill. See the module docstring.
        text = client.fetch_pod_log(namespace, pod, tail_lines=TAIL_LINES)
    else:
        elapsed = (datetime.now(UTC) - _parse_iso(watermark)).total_seconds()
        # max(1, ...): sinceSeconds=0 is rejected by the apiserver, and a watermark stamped
        # microseconds ago still needs a non-empty window.
        since = max(1, int(elapsed) + OVERLAP_SECONDS)
        text = client.fetch_pod_log(namespace, pod, since_seconds=since,
                                    tail_lines=TAIL_LINES)
    if text is None:
        # Vanished or not-ready (fetch_pod_log's benign statuses). The watermark is left
        # alone: if the pod comes back it resumes, if it is gone the prune forgets it.
        return

    lines = text.splitlines()
    capped = len(lines) >= TAIL_LINES
    if capped and watermark is not None:
        # On an INCREMENTAL read the cap cuts the OLDEST lines — the ones between the
        # watermark and the cut — and those attempts are lost for good. Say so at WARNING:
        # a capture that silently skips is the failure mode this feature exists to end.
        log.warning(
            "%s pod %s produced %d+ log lines in one window; the oldest were cut by the "
            "tailLines cap and login attempts in the gap may be missing. A shorter poll "
            "interval reduces the window.", cluster_id, pod, TAIL_LINES,
        )

    newest = _newest_timestamp(lines)
    if newest is None:
        return  # nothing timestamped at all — an empty window
    horizon = newest - ATTEMPT_WINDOW

    # The lower bound of what this read may persist. Everything at <= watermark was
    # settled by an earlier read; re-parses of it die on the dedup key anyway, but
    # filtering here keeps the insert small and the "N recorded" log honest.
    low = _parse_iso(watermark) if watermark is not None else None
    if capped and watermark is None:
        # A capped FIRST read starts mid-log, so its oldest attempt may be missing its
        # head lines and would mis-parse (a cut leading verdict turns a success into a
        # `failed`, or orphans a cause onto the wrong user). Discard the first
        # ATTEMPT_WINDOW after the cut — at most one attempt, once per pod, and only when
        # the backfill was already truncated.
        oldest = _oldest_timestamp(lines)
        if oldest is not None:
            low = oldest + ATTEMPT_WINDOW

    settled = [
        a for a in parse(lines)
        if a.at <= horizon and (low is None or a.at > low)
    ]
    if settled:
        inserted = store.record_login_events(cluster_id, [
            {
                "pod_name": pod,
                "user_name": a.user_name,
                "outcome": a.outcome,
                "at": _iso_micro(a.at),
                "provider": a.provider,
                "ldap_result_code": a.ldap_result_code,
                "detail": a.detail,
                "observed_at": observed_at,
            }
            for a in settled
        ])
        if inserted:
            log.info("%s pod %s: %d new login attempt(s) recorded", cluster_id, pod, inserted)

    # AFTER the insert, so a crash between the two re-reads rather than skips. The store
    # refuses to move it backwards, so an idle pod's unchanged horizon is a no-op.
    store.set_login_watermark(cluster_id, pod, _iso_micro(horizon))


def _newest_timestamp(lines: list[str]) -> datetime | None:
    """The last kubelet timestamp in the window, scanning from the end.

    From the end because that is where it is: the log is chronological, and only a line
    the kubelet did not stamp (a rare multi-line spill) makes the scan step back further.
    """
    for line in reversed(lines):
        ts = parse_timestamp(line)
        if ts is not None:
            return ts
    return None


def _oldest_timestamp(lines: list[str]) -> datetime | None:
    for line in lines:
        ts = parse_timestamp(line)
        if ts is not None:
            return ts
    return None
```

- **Why it is shaped this way** — the straddle argument, in full, because it is the heart of the
  task's hardest question ("the watermark must not skip an attempt whose lines straddle two
  reads. How?"):
  1. `loginlog.ATTEMPT_WINDOW` (1s) bounds an attempt's span *by construction* — the parser expires
     any pending attempt whose first line is more than 1s old. Therefore an attempt whose first
     line (`at`) is at or before `newest − ATTEMPT_WINDOW` cannot have any line after `newest`:
     everything it can ever contain is already in this read, so its parse is **final**.
  2. Conversely an attempt with `at > horizon` may still be mid-flight — concluding it now (the
     parser concludes at end-of-input with whatever it has) can record the *wrong outcome*: cut the
     `succeeded` verdict off a real LDAP login and the leftover `failed "developer"` noise line
     parses as `failed`. So those attempts are **withheld**, not persisted, and the watermark
     advances only to the horizon — the withheld band is inside the next read's window by
     construction. Both directions are pinned by
     `test_a_straddled_attempt_is_never_concluded_from_half_its_lines` and
     `test_fixture_end_to_end_across_two_reads` (the real fixture's first read settles exactly 2 of
     5 attempts; the second read settles the other 3, total 5, zero duplicates).
  3. The mirror problem — a window whose *start* cuts an attempt in half — is covered by the
     overlap: `OVERLAP_SECONDS ≥ 2×ATTEMPT_WINDOW` guarantees any attempt overlapping the persist
     band's lower edge is in the window whole, *and* so is the whole attempt before it, which is
     what the orphan-cause adoption needs to re-parse identically. Attempts at or below the
     watermark are filtered (`a.at > low`), so a re-parse can only confirm, never double-insert.
- **Gotchas** (each from the task's own list):
  - *The first read after a restart*: process restart keeps watermarks (they are in the DB), so
    only a genuinely new pod takes the `tailLines`-only path; a *capped* first read additionally
    quarantines `oldest + ATTEMPT_WINDOW` so a head-truncated attempt cannot be misrecorded.
  - *Pod Terminating / 400 not-ready*: `fetch_pod_log` returns `None`; the loop `return`s for that
    pod only; the watermark is untouched, so nothing is skipped if the pod comes back, and the
    prune forgets it once discovery stops listing it.
  - *Two replicas serving different attempts*: per-pod watermark (Q3), per-pod `_capture_pod` calls
    each in its own `try`, so one unreadable replica cannot cost the others their cycle.
  - *Idle pod*: the overlap window returns only old lines; `horizon` computes ≤ stored watermark;
    `set_login_watermark`'s `max()` makes it a no-op; the filter yields nothing. Verified live —
    second cycle inserted 0.
  - *Empty window / no timestamps*: `newest is None` → return before touching the watermark.
  - *Retention*: per-cluster, index-served, every cycle, `0` disables; runs after the pods loop so
    one slow prune cannot delay reads.
- **Test**: `TestCaptureLoop` (5 functions) — complete in piece 11 — plus the live-cluster proof
  described at the top.

### 9. Poller integration — the call site

> **Codex:** **FIX-INADEQUATE** — A standby that observes `is_leader() == False` at
> `poller.py#Poller._run_cluster` genuinely reaches none of this call site and writes nothing. A
> leadership change after that check is different: `poller.py#Poller` expressly says the lease is not a
> write fence, and this placement lets the old leader write after `fetch_pod_log()` returns. The
> proposed test misses the failing sequence: leader check true → log GET blocks → lease lost/new
> leader starts → old GET returns → old leader records events/watermark. Recheck immediately before
> the transaction and test that sequence; retain the documented best-effort limitation.

- **File**: `local-development/gsd/poller.py`
- **Anchor (import)**: in the import block, after `from .audit import plan_audit_stamps` (keeping
  the existing grouping), i.e.:

```python
from .config import ClusterConfig, Settings
from .kube import OK, ClusterClient, ClusterError, GroupSyncView, GroupView
from .leader import LeaderElector
from .audit import plan_audit_stamps
from .logincapture import capture_logins
from .storage import StorageBackend
from .timeutil import now_iso
```

- **Anchor (call site)**: in `Poller._run_cluster`, immediately **before** the comment
  `# Bindings ride the same thread but on their own due-time, ...` (i.e. after the
  `try/except` block that wraps `poll_once` / `maintain` / `_maybe_backup`).
- **Code**:

```python
            # Login capture rides the poll cadence, not the binding cadence: logins happen
            # continuously while bindings change on administrative action. Its own try, its
            # own log line, and it never records a poll outcome — a capture failure (most
            # likely a 403, since it needs RBAC the group poll does not) must not mark the
            # cluster unreachable or blank good group data. Behind the SAME leader gate as
            # everything in this loop: a standby `continue`d above and never reaches here,
            # so a standby writes no login rows. See gsd/logincapture.py for the interval
            # and watermark reasoning.
            if self.settings.login_capture_enabled:
                try:
                    capture_logins(
                        self.store, cluster, self.settings.request_timeout_seconds,
                        self.settings.login_capture_namespace,
                        retention_days=self.settings.login_capture_retention_days,
                    )
                except Exception:  # noqa: BLE001 - same rule as the poll: never die silently
                    log.exception("unhandled error capturing logins for %s", cluster.name)
```

- **Why it is shaped this way**: placement *after* the poll's `try` and *before* the binding
  due-time check puts it (a) behind the leader `continue`, (b) outside `poll_once`'s outcome
  accounting, (c) on the poll cadence rather than the 300s binding cadence, and (d) inside the
  cycle's `elapsed` measurement, so the loop's existing
  `wait(max(1.0, poll_interval - elapsed))` automatically absorbs capture time instead of drifting
  the schedule.
- **Gotchas**:
  - *Trigger*: a capture exception killing the per-cluster thread while `/healthz` stays green —
    the exact failure mode the poll's own handler documents. → *Code*: blanket `except Exception`
    with `log.exception`, the established rule.
  - *Trigger*: capture running when the cluster is unreachable — it will fail too and log a
    warning each cycle. Accepted: identical behaviour to `refresh_bindings` on an unreachable
    cluster, and silencing it would hide the one signal that capture is configured but failing.
- **Test**: `TestLeaderGating.test_a_standby_captures_nothing` (runs the real `_run_cluster` on a
  thread with a non-leader elector and asserts neither `poll_once` nor `capture_logins` fired) and
  `test_the_leader_captures_when_enabled_and_not_when_disabled`. Complete in piece 11.

### 10. Seam-test coverage of the new module — INTEGRATION OUTSIDE MY AREA (2 one-line edits)

> **Codex:** CONFIRMED — Adding `logincapture.py` to both fixed scanner lists is required by the
> existing seam test and keeps SQL confined to Store/storage. This piece agrees with A's module
> name and contains no SQL escape hatch.

- **File**: `local-development/tests/test_storage_seam.py`
- **Why touched**: the seam suite scans a *fixed list* of consumer files for `store.X` calls and
  concrete-`Store` annotations; a new module is invisible to it unless listed. Without these edits
  the suite would pass even if `logincapture.py` called an undeclared method or annotated the
  concrete `Store` — the exact drift the suite exists to catch.
- **Edit 1 — Anchor**: in `test_the_protocol_declares_every_method_the_application_calls`, the line
  `for name in ("api.py", "metrics.py", "poller.py", "activity.py"):` becomes:

```python
        for name in ("api.py", "metrics.py", "poller.py", "activity.py", "logincapture.py"):
```

- **Edit 2 — Anchor**: in `TestConsumersDependOnTheContract`, the line
  `CONSUMERS = ("poller.py", "metrics.py", "activity.py", "api.py")` becomes:

```python
    CONSUMERS = ("poller.py", "metrics.py", "activity.py", "api.py", "logincapture.py")
```

- **Test**: the edits *are* tests; both pass with `logincapture.py` as written (it annotates
  `StorageBackend`, constructs no `Store`, and calls only declared methods).

### 11. The test suite for this area (NEW file, complete)

> **Codex:** **FIX-INADEQUATE** — The parser fixtures and steady-state dedup cases are useful, but the
> suite omits the production failures above: first read versus persisted restart request params,
> a split attempt completed in the next read, leadership lost during GET, expected versus
> unexpected 400 and visible 403, response byte ceiling, and bounded retention backlog. Its
> migration test is masked by `SCHEMA` running first. The supplied fixtures were independently run
> through the committed parser: both `fixture.log` (12 lines) and `real.log` (300 lines) yield the
> same five attempts, so that research result is confirmed.

- **File**: `local-development/tests/test_login_capture_backend.py` (new)
- **Anchor**: n/a — whole file. Named `_backend` so Designer B's API/UI suite can own
  `test_login_capture.py` without a collision.
- **Note on fixtures**: the 12 lines are the real extract, inlined verbatim so the test file is
  self-contained (the suite runs in CI where the scratchpad does not exist). Parser ground truth
  was verified against both `fixture.log` and the 300-line `real.log` before writing the
  assertions: both yield the same 5 attempts
  (`john.doe success`, `jane.smith bad_password 49`, `bob.wilson rejected`,
  `nosuchuser rejected`, `developer success` on provider `developer`).
- **Code**:

```python
"""Login capture, back half: the login_event store, the log reader, the capture loop.

The fixture lines are REAL — twelve lines captured from a live oauth-server at Debug on
2026-08-07, covering all five measured grammar cases (design §1.2). Where a test needs a
trailing "time has passed" line, it appends the healthz noise shape the real log is full
of, because that is what actually follows a login burst in production.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import UTC, datetime

import httpx
import pytest

import gsd.logincapture as logincapture
import gsd.poller as poller_mod
from gsd.config import ClusterConfig, Settings
from gsd.kube import ClusterClient, ClusterError
from gsd.logincapture import OVERLAP_SECONDS, TAIL_LINES, capture_logins
from gsd.poller import Poller
from gsd.store import Store

# The 12-line real-log extract, verbatim (see docs/DESIGN_login_capture.md §1.2).
FIXTURE = """\
2026-08-07T16:56:28.267663206Z I0807 16:56:28.267409       1 basicauth.go:48] Login with provider "developer" failed for login "john.doe"
2026-08-07T16:56:28.376654326Z I0807 16:56:28.376574       1 basicauth.go:51] Login with provider "ldap-local" succeeded for login "john.doe":
2026-08-07T16:56:29.450656295Z I0807 16:56:29.450280       1 basicauth.go:48] Login with provider "developer" failed for login "jane.smith"
2026-08-07T16:56:29.480403312Z I0807 16:56:29.480197       1 ldap.go:152] error binding password for "uid=jane.smith,ou=People,dc=ephico2real,dc=com": LDAP Result Code 49 "Invalid Credentials":
2026-08-07T16:56:29.481576592Z I0807 16:56:29.480665       1 basicauth.go:48] Login with provider "ldap-local" failed for login "jane.smith"
2026-08-07T16:56:29.721361638Z I0807 16:56:29.721010       1 basicauth.go:48] Login with provider "developer" failed for login "bob.wilson"
2026-08-07T16:56:29.750664877Z I0807 16:56:29.750247       1 ldap.go:139] no entries matching (&(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,ou=Groups,dc=ephico2real,dc=com))(uid=bob.wilson))
2026-08-07T16:56:29.750973091Z I0807 16:56:29.750767       1 basicauth.go:48] Login with provider "ldap-local" failed for login "bob.wilson"
2026-08-07T16:56:30.030313874Z I0807 16:56:30.030053       1 basicauth.go:48] Login with provider "developer" failed for login "nosuchuser"
2026-08-07T16:56:30.059385516Z I0807 16:56:30.059264       1 ldap.go:139] no entries matching (&(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,ou=Groups,dc=ephico2real,dc=com))(uid=nosuchuser))
2026-08-07T16:56:30.060193032Z I0807 16:56:30.060146       1 basicauth.go:48] Login with provider "ldap-local" failed for login "nosuchuser"
2026-08-07T16:56:30.532313817Z I0807 16:56:30.531828       1 basicauth.go:51] Login with provider "developer" succeeded for login "developer":
"""


def _noise(ts: str) -> str:
    """A healthz line, the shape the real log emits every ~1.7s. Advances the horizon."""
    return (f'{ts} I0807 00:00:00.000000       1 httplog.go:132] "HTTP" verb="GET" '
            f'URI="/healthz" resp=200')


def _event(user="john.doe", outcome="success", at="2026-08-07T16:56:28.267663Z",
           pod="oauth-openshift-a", **extra) -> dict:
    return {
        "pod_name": pod, "user_name": user, "outcome": outcome, "at": at,
        "provider": "ldap-local", "ldap_result_code": None, "detail": None,
        "observed_at": "2026-08-07T17:00:00Z", **extra,
    }


@pytest.fixture()
def store():
    s = Store(":memory:")
    s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
    yield s
    s.close()


class TestLoginEventStore:
    def test_overlapping_reads_insert_once(self, store):
        """The overlap window re-parses the same attempt every cycle; the dedup key must
        make the repeat free, exactly as record_sync_event does for re-observed syncs."""
        assert store.record_login_events("crc", [_event()]) == 1
        assert store.record_login_events("crc", [_event()]) == 0
        assert len(store.login_events("crc")) == 1

    def test_same_instant_on_two_pods_stays_distinct(self, store):
        """§2.2 Q2: the pod name IS in the key. One attempt's lines live in exactly one
        replica's log, so the pod can never split a real duplicate — but two genuine
        same-microsecond attempts on two replicas must not collapse into one row."""
        assert store.record_login_events("crc", [_event(pod="oauth-a")]) == 1
        assert store.record_login_events("crc", [_event(pod="oauth-b")]) == 1
        assert len(store.login_events("crc")) == 2

    def test_a_disagreeing_reparse_is_visible_not_swallowed(self, store):
        """outcome is in the key ON PURPOSE: if a bug ever makes a re-parse disagree with
        the first parse, both rows must land so the disagreement can be seen, rather than
        the first parse silently winning."""
        store.record_login_events("crc", [_event(outcome="success")])
        assert store.record_login_events("crc", [_event(outcome="failed")]) == 1
        assert {r["outcome"] for r in store.login_events("crc")} == {"success", "failed"}

    def test_events_are_newest_first_and_bounded(self, store):
        store.record_login_events("crc", [
            _event(at="2026-08-07T16:56:28.000001Z"),
            _event(at="2026-08-07T16:56:29.000001Z"),
            _event(at="2026-08-07T16:56:30.000001Z"),
        ])
        rows = store.login_events("crc", limit=2)
        assert [r["at"] for r in rows] == [
            "2026-08-07T16:56:30.000001Z", "2026-08-07T16:56:29.000001Z"
        ]

    def test_filters_narrow_without_reshaping(self, store):
        store.record_login_events("crc", [
            _event(user="alice", outcome="success", at="2026-08-07T16:00:00.000000Z"),
            _event(user="alice", outcome="bad_password", at="2026-08-07T17:00:00.000000Z"),
            _event(user="bob", outcome="success", at="2026-08-07T18:00:00.000000Z"),
        ])
        assert len(store.login_events("crc", user_name="alice")) == 2
        assert len(store.login_events("crc", outcome="success")) == 2
        assert len(store.login_events("crc", since="2026-08-07T17:30:00.000000Z")) == 1

    def test_summary_reports_the_observed_since_boundary(self, store):
        """§1.8 made visible: first_at is when observation STARTED, and the UI needs it to
        say 'observed since', not to imply nobody logged in before the dashboard did."""
        store.record_login_events("crc", [
            _event(user="alice", outcome="success", at="2026-08-07T16:00:00.000000Z"),
            _event(user="bob", outcome="rejected", at="2026-08-07T17:00:00.000000Z"),
            _event(user="bob", outcome="rejected", at="2026-08-07T18:00:00.000000Z"),
        ])
        s = store.login_event_summary("crc")
        assert s["attempts"] == 3
        assert s["distinct_users"] == 2
        assert s["successes"] == 1
        assert s["failures"] == 2
        assert s["first_at"] == "2026-08-07T16:00:00.000000Z"
        assert s["last_at"] == "2026-08-07T18:00:00.000000Z"

    def test_an_empty_summary_has_zero_failures_not_none(self, store):
        """SUM over zero rows is NULL in SQLite; the summary must not leak that."""
        s = store.login_event_summary("crc")
        assert (s["attempts"], s["successes"], s["failures"]) == (0, 0, 0)
        assert s["first_at"] is None

    def test_retention_prunes_only_old_rows_for_the_named_cluster(self, store):
        store.upsert_cluster("other", "https://other:6443", True)
        store.record_login_events("crc", [_event(at="2025-01-01T00:00:00.000000Z"),
                                          _event(at="2026-08-07T16:00:00.000000Z")])
        store.record_login_events("other", [_event(at="2025-01-01T00:00:00.000000Z")])
        assert store.prune_login_events("crc", "2026-01-01T00:00:00.000000Z") == 1
        assert len(store.login_events("crc")) == 1
        assert len(store.login_events("other")) == 1, "another cluster's history was pruned"


class TestWatermarks:
    def test_watermark_round_trips_per_pod(self, store):
        store.set_login_watermark("crc", "oauth-a", "2026-08-07T16:56:29.532313Z")
        store.set_login_watermark("crc", "oauth-b", "2026-08-07T16:56:10.000000Z")
        assert store.login_watermarks("crc") == {
            "oauth-a": "2026-08-07T16:56:29.532313Z",
            "oauth-b": "2026-08-07T16:56:10.000000Z",
        }

    def test_watermark_never_rewinds(self, store):
        """An idle pod's overlap window can compute an OLDER horizon than the one stored;
        writing it back would shrink nothing correct and re-widen the next read for no
        reason. max() keeps it monotonic — fixed-width UTC makes that a string compare."""
        store.set_login_watermark("crc", "oauth-a", "2026-08-07T16:56:29.532313Z")
        store.set_login_watermark("crc", "oauth-a", "2026-08-07T16:56:20.000000Z")
        assert store.login_watermarks("crc")["oauth-a"] == "2026-08-07T16:56:29.532313Z"

    def test_prune_forgets_only_pods_that_are_gone(self, store):
        store.set_login_watermark("crc", "oauth-old", "2026-08-07T16:00:00.000000Z")
        store.set_login_watermark("crc", "oauth-new", "2026-08-07T16:00:00.000000Z")
        assert store.prune_login_watermarks("crc", ["oauth-new"]) == 1
        assert set(store.login_watermarks("crc")) == {"oauth-new"}


class TestMigration5:
    def test_a_version_4_database_gains_the_tables(self, tmp_path):
        """The upgrade path: a database from the previous release has user_version 4 and
        no login tables (CREATE TABLE IF NOT EXISTS in SCHEMA no-ops on existing tables,
        which is exactly why the migration must exist)."""
        db = str(tmp_path / "v4.db")
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE cluster (id TEXT PRIMARY KEY, api_url TEXT NOT NULL,
                                  enabled INTEGER NOT NULL DEFAULT 1);
            PRAGMA user_version = 4;
        """)
        conn.commit()
        conn.close()
        store = Store(db)
        try:
            tables = {r[0] for r in store._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            assert {"login_event", "login_capture_watermark"} <= tables
            assert store._conn.execute("PRAGMA user_version").fetchone()[0] >= 5
            # And the new surface actually works against the upgraded file.
            assert store.record_login_events("crc", [_event()]) == 1
        finally:
            store.close()

    def test_replaying_against_a_fresh_database_is_a_noop(self, tmp_path):
        """Fresh databases get the tables from SCHEMA and then replay migration 5, which
        must tolerate them existing — the IF NOT EXISTS rule migration 4 documents."""
        db = str(tmp_path / "fresh.db")
        for _ in range(3):
            Store(db).close()
        store = Store(db)
        try:
            assert store._conn.execute("PRAGMA user_version").fetchone()[0] >= 5
        finally:
            store.close()


class TestSettingsWiring:
    """loginCapture.namespace's path to the app: values -> ConfigMap -> load_settings.

    The chart half is asserted in test_chart_strategy.py (TestLoginCaptureConfigWiring);
    this half proves the YAML keys and the env overrides land on Settings, so the Role's
    namespace and the reader's namespace cannot silently diverge through a typo'd key that
    load_settings would otherwise ignore.
    """

    BASE = "clusters:\n  - name: c\n    apiUrl: https://x\n    tokenEnv: T\n"

    def _load(self, tmp_path, body):
        from gsd.config import load_settings
        path = tmp_path / "clusters.yaml"
        path.write_text(self.BASE + body)
        return load_settings(path)

    def test_defaults_are_off_and_openshift_authentication(self, tmp_path):
        s = self._load(tmp_path, "")
        assert s.login_capture_enabled is False
        assert s.login_capture_namespace == "openshift-authentication"
        assert s.login_capture_retention_days == 400

    def test_the_configmap_keys_reach_settings(self, tmp_path):
        s = self._load(tmp_path, "loginCaptureEnabled: true\n"
                                 "loginCaptureNamespace: custom-auth\n"
                                 "loginCaptureRetentionDays: 30\n")
        assert s.login_capture_enabled is True
        assert s.login_capture_namespace == "custom-auth"
        assert s.login_capture_retention_days == 30

    def test_env_wins_and_a_yaml_false_string_cannot_enable(self, tmp_path, monkeypatch):
        """_bool_setting's whole point: bool("false") is True, so env spellings must be
        parsed, not cast — an explicit disable must never silently enable."""
        monkeypatch.setenv("GSD_LOGIN_CAPTURE_ENABLED", "false")
        monkeypatch.setenv("GSD_LOGIN_CAPTURE_NAMESPACE", "elsewhere")
        s = self._load(tmp_path, "loginCaptureEnabled: true\n")
        assert s.login_capture_enabled is False
        assert s.login_capture_namespace == "elsewhere"


def _mock_client(handler):
    """A ClusterClient whose HTTP goes to `handler` — the test_no_groupsync_operator idiom."""
    cluster = ClusterConfig("crc", "https://x", token_env="T")
    client = ClusterClient(cluster, timeout=5)
    transport = httpx.MockTransport(handler)
    client._client = lambda: httpx.Client(transport=transport, base_url="https://x")
    return client


PODS_PATH = "/api/v1/namespaces/openshift-authentication/pods"


def _pod(name, labels=None):
    return {"metadata": {"name": name,
                         "labels": labels if labels is not None
                         else {"app": "oauth-openshift"}}}


class TestFetchOauthPods:
    def test_forbidden_degrades_to_none(self):
        """The grant is optional (it lives in a namespace the chart does not own), so a
        403 means 'capture unavailable', never a failed poll — the fetch_users contract."""
        client = _mock_client(lambda req: httpx.Response(403, json={"kind": "Status"}))
        assert client.fetch_oauth_pods("openshift-authentication") is None

    def test_filters_to_oauth_pods_and_sorts(self):
        def handle(request):
            assert request.url.path == PODS_PATH
            return httpx.Response(200, json={"kind": "PodList", "items": [
                _pod("oauth-openshift-b"),
                _pod("some-debug-pod", labels={}),
                _pod("oauth-openshift-a"),
            ]})
        client = _mock_client(handle)
        assert client.fetch_oauth_pods("openshift-authentication") == [
            "oauth-openshift-a", "oauth-openshift-b"]

    def test_no_matching_pods_is_empty_not_none(self):
        """[] and None answer different questions: 'nothing there' vs 'may not look'."""
        client = _mock_client(lambda req: httpx.Response(
            200, json={"kind": "PodList", "items": []}))
        assert client.fetch_oauth_pods("openshift-authentication") == []

    def test_a_server_error_still_raises(self):
        client = _mock_client(lambda req: httpx.Response(500, text="boom"))
        with pytest.raises(ClusterError):
            client.fetch_oauth_pods("openshift-authentication")


class TestFetchPodLog:
    def test_returns_text_and_sends_the_bounding_params(self):
        """The endpoint returns text/plain (measured — even with Accept: application/json),
        so the read must NOT go through the JSON path. timestamps=true is unconditional:
        the kubelet prefix is the only usable instant on the line."""
        seen = {}

        def handle(request):
            seen.update(dict(request.url.params))
            return httpx.Response(200, text=FIXTURE,
                                  headers={"content-type": "text/plain"})
        client = _mock_client(handle)
        text = client.fetch_pod_log("openshift-authentication", "oauth-a",
                                    since_seconds=90, tail_lines=10000)
        assert text == FIXTURE
        assert seen == {"timestamps": "true", "sinceSeconds": "90", "tailLines": "10000"}

    def test_a_vanished_pod_is_none_not_an_error(self):
        """Terminating when listed, gone when read — the ordinary weather of a roll."""
        client = _mock_client(lambda req: httpx.Response(404, json={
            "kind": "Status", "message": 'pods "oauth-a" not found'}))
        assert client.fetch_pod_log("openshift-authentication", "oauth-a") is None

    def test_a_not_ready_container_is_none_not_an_error(self):
        client = _mock_client(lambda req: httpx.Response(400, json={
            "kind": "Status",
            "message": 'container "oauth-openshift" in pod "oauth-a" is waiting to start'}))
        assert client.fetch_pod_log("openshift-authentication", "oauth-a") is None

    def test_forbidden_is_none_but_a_server_error_raises(self):
        client = _mock_client(lambda req: httpx.Response(403, json={"kind": "Status"}))
        assert client.fetch_pod_log("openshift-authentication", "oauth-a") is None
        client = _mock_client(lambda req: httpx.Response(500, text="boom"))
        with pytest.raises(ClusterError):
            client.fetch_pod_log("openshift-authentication", "oauth-a")


class _FakeClient:
    """A scripted ClusterClient for the loop: each capture cycle pops the next script."""

    def __init__(self, pods, logs):
        self.pods = pods          # list per call, or None for forbidden
        self.logs = logs          # {pod: [text per call]}
        self.log_calls: list[dict] = []

    def fetch_oauth_pods(self, namespace):
        return self.pods

    def fetch_pod_log(self, namespace, pod, since_seconds=None, tail_lines=None):
        self.log_calls.append({"pod": pod, "since_seconds": since_seconds,
                               "tail_lines": tail_lines})
        series = self.logs.get(pod)
        if not series:
            return None
        return series.pop(0)


@pytest.fixture()
def fake_capture(monkeypatch, store):
    """capture_logins wired to a fake client; returns (run, fake) where run() is a cycle."""
    cluster = ClusterConfig("crc", "https://x", token_env="T")

    def wire(pods, logs):
        fake = _FakeClient(pods, logs)
        monkeypatch.setattr(logincapture, "ClusterClient", lambda *a, **kw: fake)

        def run():
            capture_logins(store, cluster, 5.0, "openshift-authentication")
        return run, fake
    return wire


class TestCaptureLoop:
    def test_fixture_end_to_end_across_two_reads(self, store, fake_capture):
        """The whole discipline on the real lines. The first read's newest line is the
        developer success at :30.532, so the horizon is :29.532 and only the two attempts
        behind it settle; the rest are WITHHELD, not guessed. A later read whose window
        has moved on settles the remainder exactly once."""
        later = FIXTURE + _noise("2026-08-07T16:56:35.000000000Z")
        run, fake = fake_capture(["oauth-a"], {"oauth-a": [FIXTURE, later]})

        run()
        first = {(r["user_name"], r["outcome"]) for r in store.login_events("crc")}
        assert first == {("john.doe", "success"), ("jane.smith", "bad_password")}
        # First read: no watermark yet, so tailLines-bounded backfill with no sinceSeconds.
        assert fake.log_calls[0] == {"pod": "oauth-a", "since_seconds": None,
                                     "tail_lines": TAIL_LINES}
        wm = store.login_watermarks("crc")["oauth-a"]
        assert wm == "2026-08-07T16:56:29.532313Z", "watermark is horizon, not newest line"

        run()
        rows = store.login_events("crc")
        assert {(r["user_name"], r["outcome"]) for r in rows} == {
            ("john.doe", "success"), ("jane.smith", "bad_password"),
            ("bob.wilson", "rejected"), ("nosuchuser", "rejected"),
            ("developer", "success"),
        }
        assert len(rows) == 5, "the overlap re-read duplicated an attempt"
        # Second read: incremental, sinceSeconds covers the watermark plus the overlap.
        assert fake.log_calls[1]["since_seconds"] >= OVERLAP_SECONDS
        assert fake.log_calls[1]["tail_lines"] == TAIL_LINES

    def test_a_straddled_attempt_is_never_concluded_from_half_its_lines(
            self, store, fake_capture):
        """The john.doe attempt cut before its success verdict: parsed alone it would
        conclude `failed` (the htpasswd noise line is all there is). The horizon must
        withhold it, and the completed re-read must record success — one row, the truth."""
        half = FIXTURE.splitlines()[0] + "\n"           # failed "developer" only
        full = "\n".join(FIXTURE.splitlines()[:2]) + "\n" + _noise(
            "2026-08-07T16:56:32.000000000Z")
        run, _ = fake_capture(["oauth-a"], {"oauth-a": [half, full]})

        run()
        assert store.login_events("crc") == [], "concluded an attempt from half its lines"
        run()
        rows = store.login_events("crc")
        assert [(r["user_name"], r["outcome"]) for r in rows] == [("john.doe", "success")]

    def test_a_pod_vanishing_mid_read_skips_without_state_damage(
            self, store, fake_capture):
        """fetch_pod_log returns None (404/400): no rows, no watermark, no exception —
        and the NEXT discovery prunes the name once the pod stops being listed."""
        run, _ = fake_capture(["oauth-gone"], {"oauth-gone": []})
        run()
        assert store.login_events("crc") == []
        assert store.login_watermarks("crc") == {}

    def test_forbidden_discovery_writes_nothing(self, store, fake_capture):
        run, fake = fake_capture(None, {})
        run()
        assert store.login_events("crc") == []
        assert fake.log_calls == [], "read logs despite a forbidden pod list"

    def test_replaced_pods_watermarks_are_pruned(self, store, fake_capture):
        store.set_login_watermark("crc", "oauth-dead", "2026-08-07T16:00:00.000000Z")
        run, _ = fake_capture(["oauth-live"],
                              {"oauth-live": [FIXTURE]})
        run()
        assert "oauth-dead" not in store.login_watermarks("crc")


class TestLeaderGating:
    def _poller(self, store, leader: bool, enabled: bool = True):
        class _Elector:
            is_leader = leader
        settings = Settings(
            clusters=[ClusterConfig("crc", "https://x", token_env="T")],
            poll_interval_seconds=1,
            login_capture_enabled=enabled,
        )
        return Poller(store, settings, _Elector())

    def _spin(self, poller, cluster, seconds=0.3):
        thread = threading.Thread(target=poller._run_cluster, args=(cluster,), daemon=True)
        thread.start()
        time.sleep(seconds)
        poller._stop.set()
        thread.join(timeout=5)

    def test_a_standby_captures_nothing(self, store, monkeypatch):
        """§2.1: only the leader may write. The capture call sits behind the SAME gate as
        poll_once — a standby `continue`s before either — so losing the lease stops login
        writes with the rest, and this pins that placement."""
        calls = []
        monkeypatch.setattr(poller_mod, "capture_logins",
                            lambda *a, **kw: calls.append(a))
        monkeypatch.setattr(poller_mod, "poll_once",
                            lambda *a, **kw: calls.append("poll"))
        p = self._poller(store, leader=False)
        self._spin(p, p.settings.clusters[0])
        assert calls == [], "a standby polled or captured"

    def test_the_leader_captures_when_enabled_and_not_when_disabled(
            self, store, monkeypatch):
        for enabled in (True, False):
            captured = []
            monkeypatch.setattr(poller_mod, "capture_logins",
                                lambda *a, **kw: captured.append(a))
            monkeypatch.setattr(poller_mod, "poll_once", lambda *a, **kw: "ok")
            monkeypatch.setattr(poller_mod, "refresh_bindings", lambda *a, **kw: "ok")
            p = self._poller(store, leader=True, enabled=enabled)
            self._spin(p, p.settings.clusters[0])
            assert bool(captured) is enabled
```

  Every function above executed and passed as part of the 706-test run.


---

## Integration points I touched outside my area

1. **`charts/group-sync-dashboard/templates/configmap.yaml`** — two data keys + a comment
   (piece 7). Required: without them `loginCapture.namespace` never reaches the app and the
   feature cannot be switched on in a deployment at all. No values-schema change; both keys derive
   from the shipped `loginCapture` block.
2. **`tests/test_storage_seam.py`** — `logincapture.py` added to the two scanned-file lists
   (piece 10). Required so the seam suite actually guards the new consumer.
3. **`tests/test_chart_strategy.py`** — one test method appended to the existing login-capture
   class (piece 7's test). It pins the ConfigMap wiring; the shipped RBAC tests are untouched.
4. **`gsd/poller.py`** — one import + one gated call block (piece 9). This is the seam the brief
   assigns me ("the capture loop … must respect leader election"), but the file itself is shared
   with the group poll, so flagging it: nothing else in the file changed, and
   `test_a_standby_captures_nothing` pins the placement.

Not touched, deliberately: `loginlog.py` (consumed as-is: `parse`, `parse_timestamp`,
`ATTEMPT_WINDOW`), `api.py`/`index.html`/`metrics.py` (Designer B's; my store reads are shaped for
their `@consistent` + `limit+1` idioms), the RBAC template, `authLogLevel`, oauth-proxy config.

## Tech debt: avoided, and accepted-with-reason

**Avoided:**
- *A second thread per cluster* — a second leader-election surface and a second crash-discipline
  for zero correctness gain (Q1).
- *Cluster-wide watermark* — silently loses lines on any pod that misses a cycle (Q3).
- *Trusting a single parse of a window edge* — the horizon/withhold rule exists precisely so no row
  is ever written from a half-read attempt.
- *Unbounded first read / unbounded incremental read* — both `tailLines`-capped, with the
  incremental cap *announcing* loss at WARNING rather than hiding it.
- *`labelSelector` threading through `_list_all`* — client-side filter keeps the shared pager
  untouched (and its paging semantics unchanged for every existing caller).
- *A per-request or per-line write path* — one `executemany` per pod per cycle, joined transactions
  via `_write()`.

**Accepted, with reasons:**
- *`retention_days` is app-config only (YAML/env), not a chart value.* Exposing
  `loginCapture.retentionDays` in `values.yaml` is a one-line chart change I left out to keep the
  chart surface to the minimum integration; the app default (400d) matches the existing activity
  retention. Debt: an operator who wants a different retention must set
  `loginCaptureRetentionDays` via `config`-block passthrough or env until the chart exposes it.
- *No `/metrics` series for capture health.* `metrics.py` is outside my scope and §1.7 forbids
  usernames there anyway; a count-only `gsd_login_capture_*` family would be legitimate future
  work. Until then, capture health is observable via `login_capture_watermark.updated_at` and the
  WARNING/INFO log lines.
- *The `container` param is omitted on the log read* — breaks (benignly, visibly) if the oauth pod
  ever grows a sidecar; documented in the method with the recovery signal (stalled
  `updated_at`).
- *A capped incremental read loses the gap and only warns.* The alternative — refusing to advance
  the watermark — re-reads a window that can never shrink and wedges capture permanently; a
  warned, bounded loss is the honest trade. The threshold (>160 sustained lines/s of *oauth* log
  between 60s cycles) is far beyond the measured line rate.
- *`INSERT OR IGNORE` hides which UNIQUE member collided* — inherent to the idiom the codebase
  already uses for `sync_event`; the `outcome`-in-key choice ensures the one collision class that
  would matter (a parse disagreement) surfaces as two rows instead of being ignored.

## What I could not settle, and what would settle it

1. **The oauth pod label on *other* OpenShift versions.** `app=oauth-openshift` is measured on this
   cluster (4.x/CRC) and consistent with the operator's manifests, but I could not verify it across
   versions from here. Settled by: one `oc get pods -n openshift-authentication --show-labels` on
   each supported version; if it ever varies, the constant pair in `kube.py` is the single place to
   widen.
2. **Whether `sinceSeconds` interacts with kubelet log rotation** (does a rotated file's older
   half stay readable within the window?). The capture is correct either way — rotation behaves
   like the cap: lines gone before a read are unrecoverable and the WARNING/first-read paths
   already model that — but the *probability* of loss under heavy rotation is unmeasured. Settled
   by: a soak on a busier cluster comparing `login_event` counts against
   `openshift_auth_basic_password_count_result` deltas (count-only, no usernames — §1.7-safe).
3. **Multi-cluster capture reach.** Each configured cluster is captured with *its own* token, so
   remote clusters need the equivalent Role bound to the remote token's identity — the chart only
   renders it for the local one. The code degrades exactly as designed (403 → INFO per cycle), but
   whether remote capture is *wanted* is a product decision. Settled by: the operator saying so;
   the wiring already works if the remote grant exists.
4. **`TAIL_LINES=10_000` and `OVERLAP_SECONDS=30` are engineering constants, not configuration.**
   Chosen from measured line rates with wide margins and deliberately not exposed as knobs (two
   more knobs nobody can set correctly without reading this document). Settled by: production
   observation; if the cap warning ever fires in practice, promote them to `Settings` then, with
   the observed rate as the sizing datum.


---

# Designer B — API, UI, tests

Everything below was written against the actual files on `feat/login-capture` and verified where
verification was possible: every claim about existing code cites `file:symbol`; every synthetic log
line in the tests was **run through the committed parser** (`gsd/loginlog.py#parse`) before being
asserted on; both accent colours were computed against the exact WCAG formula in
`tests/test_accessibility.py` (light `#0e7490` on `--page #f9f9f7` = **5.08:1**, dark `#21a1bd` on
`--page #0d0d0d` = **6.38:1**; both also clear 4.5:1 on `--surface-1`). The measured parse of the
real fixtures (command shown in §Tests): `fixture.log` → 5 attempts (`john.doe` success,
`jane.smith` bad_password 49, `bob.wilson` rejected, `nosuchuser` rejected, `developer` success on
provider `developer`); `real.log` (300 lines, httplog noise) → the **same 5 attempts**.

---

## Assumed store surface (Designer A) — NAMED, for the arbiter to reconcile

> **Codex:** REFUTED — This is not A's surface. B calls `record_login_attempts`,
> `record_login_read`, `login_attempts`, `login_summary`, `ungoverned_login_users`, and
> `login_capture_status`; A implements none of those names. A instead supplies
> `record_login_events`, `login_watermarks`, `set_login_watermark`,
> `prune_login_watermarks`, `prune_login_events`, `login_events`, and
> `login_event_summary`. The discrepancies are deeper than renaming: B seeds parser objects with no
> pod identity, expects joined `full_name`/`known_user`, different aggregate fields, provider
> exclusion, stable start/last-read status, and an ungoverned-account query. A accepts event dicts
> containing `pod_name`/`observed_at` and returns none of B's joined/status shapes. The Settings
> assumption is also false: A has no `login_capture_htpasswd_providers`. The combined code is a
> build-time break until one contract is selected; the complete matrix appears at the end.

My API and tests call exactly these. If A's names or shapes differ, the reconciliation happens in
`gsd/api.py#list_logins` and `tests/test_login_capture.py` only — the UI never sees store names.

```python
# --- writers (called by A's capture thread; called by my tests to seed) -------------------
def record_login_attempts(self, cluster_id: str, attempts: list[LoginAttempt]) -> int: ...
    # `attempts` is the parser's own type (gsd/loginlog.py#LoginAttempt). Returns rows
    # actually inserted. INSERT OR IGNORE on the natural key
    # (cluster_id, user_name, at, outcome) — `at` stored as FIXED-WIDTH microsecond UTC:
    # attempt.at.strftime("%Y-%m-%dT%H:%M:%S.%fZ")  ->  "2026-08-07T16:56:28.267663Z"
    # Fixed width matters: the store's lexicographic-equals-chronological convention
    # (gsd/timeutil.py docstring) is load-bearing for MIN/MAX and ORDER BY.
def record_login_read(self, cluster_id: str, pod_name: str,
                      started_at: str, read_at: str) -> None: ...
    # Per-pod read watermark, upserted. started_at = when capture FIRST began reading this
    # cluster (stable across cycles); read_at = last successful read.

# --- readers (called by my API handler) ---------------------------------------------------
def login_attempts(self, cluster_id: str, *, user_name: str | None = None,
                   outcome: str | None = None, limit: int = 200) -> list[dict]: ...
    # Newest first (ORDER BY at DESC). Row shape:
    #   user_name, outcome, at, provider, ldap_result_code, detail,
    #   full_name   -> LEFT JOIN ocp_user (NULL is the ordinary case, as in group_members)
    #   known_user  -> 0/1: EXISTS(group_member for this cluster+user_name).
    # known_user computed in SQL, NOT by fetching the member list into Python: it is the
    # "most valuable row" flag and must be correct on every page of a big table.
def login_summary(self, cluster_id: str,
                  exclude_providers: tuple[str, ...] = ()) -> dict: ...
    # Whole-cluster scalars, never the page:
    #   {total, by_outcome: {outcome: n}, distinct_users, ungoverned_users,
    #    first_at, last_at}
    # ungoverned_users = COUNT(DISTINCT user_name) of users with NO group_member row and
    # at least one attempt whose provider is NOT IN exclude_providers.
def ungoverned_login_users(self, cluster_id: str,
                           exclude_providers: tuple[str, ...] = (),
                           limit: int = 50) -> list[dict]: ...
    # One row per DISTINCT ungoverned account, most recent first — SAME predicate as
    # login_summary's ungoverned_users (the _direct_user_binding_where lesson: a count and
    # its rows built from two predicates is how "showing 50 of 30" ships). Row shape:
    #   user_name, attempts, first_at, last_at, last_outcome
def login_capture_status(self, cluster_id: str) -> dict | None: ...
    # {observed_since: MIN(started_at), last_read_at: MAX(read_at)} over the watermark
    # rows, or None when capture has never run against this cluster.
```

All six also get declared in `gsd/storage.py#StorageBackend` (A's file — `tests/test_storage_seam.py`
asserts `Store` satisfies the Protocol, so an undeclared method is invisible to the seam).

**Assumed `Settings` fields** (`gsd/config.py#Settings`, wired from the chart's existing
`loginCapture.*` values by A's config plumbing):

```python
login_capture_enabled: bool = False          # mirrors chart values.yaml loginCapture.enabled
login_capture_htpasswd_providers: list[str] = field(default_factory=lambda: ["developer", "htpasswd"])
    # Which identity-provider NAMES are HTPasswd. This is what loginlog.is_break_glass was
    # built to receive; the log alone cannot say what type a provider is, only its name.
    # "developer" is CRC's; "htpasswd" is the common production name. Chart value:
    # loginCapture.htpasswdProviders.
```

---

## Decisions

### Q5 (Part 2.2): a new tab — **`Logins`**, not a section on Usage. Reasons, in order of force:

> **Codex:** CONFIRMED — A cluster-scoped Logins tab fits the existing navigation model better
> than the deliberately dashboard-wide Usage page. The dedicated ungoverned-accounts card above
> the chronological table answers the production-critical discoverability question: after the
> store/API seam is fixed, a username belonging to no synced group is explicitly findable rather
> than buried in time order. This review used the repository's frontend-design guidance: the
> information hierarchy and separate review workflow justify the new view.

1. **Usage is deliberately not cluster-scoped and login capture deliberately is.** The Usage page
   *hides the cluster selector* (`index.html#renderFilters`: `view.page === "usage" ? "" : ...`,
   with the comment "Usage is a property of the DASHBOARD, not of a cluster") and suppresses the
   header scope-note for the same reason. Login attempts are per-cluster rows keyed on
   `cluster_id` and fetched under `/api/clusters/{cluster_id}/...`. Putting a cluster-scoped
   section on the one page that structurally removes cluster scope would either resurrect the
   selector for half the page (a filter that "would appear to filter them while silently doing
   nothing" for the other half — the exact defect that comment exists to prevent) or leave the
   login table unswitchable on a multi-cluster deployment.
2. **The reader's question is different.** Usage answers "does anyone use this dashboard" —
   justification telemetry. Logins answers "who came to the *cluster's* door, who was refused, and
   why" — a governance/security surface, read in the same access reviews as Groups and Namespace
   audit. A reviewer looking for "did anyone try the removed account" must be able to find it by
   name in the nav, not two scrolls down a page named after something else.
3. **The accent system is built for exactly this.** A new view costs one token plus one
   `body[data-page]` line (`index.html`: "a new view needs one line here and nothing else"), and
   `tests/test_accessibility.py` *derives* the tab-token list from the stylesheet
   (`_tab_tokens`) precisely so a seventh tab is automatically contrast-checked — the test's own
   comment records that a hardcoded list is how `policy` and `nsaudit` once went unchecked. The
   hue: with blue/teal/purple/violet/magenta/orange taken, cyan is the widest remaining gap;
   light `#0e7490` and dark `#21a1bd` measured at 5.08:1 and 6.38:1 against `--page` (both
   >4.5:1, the active-tab-label bar). Cyan sits between overview-blue and groups-teal on the
   wheel, so it leans on the lightness separation the palette comment already relies on — and the
   tab's position, label and weight are co-channels (WCAG 1.4.1 handling is unchanged).

### The other decisions in my area (each visible in the code below)

> **Codex:** **FIX-INADEQUATE** — The hierarchy, outcome words, and break-glass treatment are sound,
> but three dependencies are wrong. First, B's pod-less dedup key drops the cross-replica
> same-instant pair demonstrated under Q2. Second, a pruned per-pod watermark cannot truthfully
> mean stable “record begins”; expose capture-start and retained-since separately. Third, an
> ungoverned username is not guaranteed to 404: `api.py#user_detail` serves a user with membership
> history even when it has no current group. That “access removed, still trying” case is especially
> valuable and should retain drill-down; use a separate `has_history`/detail-available flag rather
> than equating current membership with route existence.

- **The "observed since" boundary is rendered as data, not as an apology.** A "Watching since"
  KPI in the lead card plus one reusable sentence (`loginWindowNote`) stating *when the record
  begins and why nothing earlier can exist* — and that same sentence is the empty state, so a
  sparse or empty table names the window instead of implying "nobody logged in". Source of truth:
  the reader watermark (`login_capture_status`), falling back to the oldest recorded attempt for
  a database that predates the watermark.
- **A username in no synced group is promoted, not buried.** The API returns a dedicated
  `ungoverned` list (distinct accounts, whole-set count beside it) and the UI renders it as its
  own card *above* the chronological table, with the hero number of the page being the count of
  such accounts. It is not reconstructed client-side from the paged attempts — a truncated page
  can be missing exactly those rows.
- **Break-glass accounts: shown and labelled, never hidden.** `loginlog.py#is_break_glass`'s
  docstring is the policy ("who used kubeadmin, and when, is a governance question"): rows stay
  in the record with a `break-glass` chip, but they are *excluded from the ungoverned card* —
  they belong to no directory group by construction, so listing them there permanently would be
  the `built_in`-tier mistake again: a section that always contains the same noise trains people
  to ignore it.
- **Drill-down goes through `navigate()` to the existing user page.** A known user's name is a
  `.drill` button that calls `navigate({ page: "groups", user, ... })` — position lands in the
  URL (`POSITION_KEYS` already carries `page`/`cluster`/`user`), browser Back returns to Logins,
  and the answer to "what does this person still have?" is the page that already answers it. An
  *ungoverned* account gets no drill button: `user_detail` 404s for a user with no memberships
  and no history (`gsd/api.py#user_detail`), and a button whose destination is a guaranteed
  error page is worse than the labelled fact. The absence **is** the finding, and the card says so.
- **Outcome severity mapping:** the WORD is the signal (badges carry glyph + text, colour never
  alone). `success`→ok; every classified failure→warning with its specific word (each is a
  different operational action — the reason loginlog keeps them distinct); `failed`
  (unclassified)→critical, because it means the grammar has a gap and should be loud, per
  `loginlog.py#OUTCOME_FAILED`'s own rationale.
- **No chart.** A sparse, restart-truncated event stream drawn as a timeline invites exactly the
  "nobody logged in before Tuesday" misreading §1.8 warns about. KPIs + two tables answer the
  questions; a rate chart can be added when a real deployment accumulates enough window to make
  one honest.
- **Positions on Q2/Q4 that my code depends on** (A owns the implementation): my tests assume the
  dedup key `(cluster, user, at, outcome)` at microsecond resolution — at that resolution two
  *human* attempts colliding is not a real case, and the pod name deliberately stays out of the
  key so the same line read from two replicas' overlapping windows cannot double-count. On
  retention (Q4) I take no dependency: the UI says "record begins", sourced from the watermark;
  if A adds a prune, `observed_since` semantics must be revisited (flagged in the last section).

---

## Implementation

### 1. API — module imports and the outcome vocabulary (`gsd/api.py`)

> **Codex:** CONFIRMED — Importing the committed parser module and deriving the filter vocabulary
> from its constants avoids a second outcome definition. This piece does not perform SQL or I/O and
> introduces no invariant conflict.

- **File**: `local-development/gsd/api.py`
- **Anchor 1 (import)**: the module imports at the top — insert between these two existing lines:

```python
from . import __version__
from . import state as st
```

- **Code 1**:

```python
from . import __version__
from . import loginlog
from . import state as st
```

- **Anchor 2 (constant)**: immediately after the existing module-level block:

```python
# Mirrors oauthProxy.skipAuthRegex. Requests here reach the app WITHOUT authentication, so
# nothing they claim about identity can be believed or recorded.
SKIP_AUTH_PATHS = frozenset({"/healthz", "/readyz", "/metrics"})
```

- **Code 2**:

```python
# The login-outcome vocabulary, taken from the one module that owns it rather than restated,
# so a new outcome the parser learns is filterable here the moment it exists. Order is the
# order a reader scans a filter in: the good case, then the causes, then the honest bucket.
LOGIN_OUTCOMES = (
    loginlog.OUTCOME_SUCCESS,
    loginlog.OUTCOME_BAD_PASSWORD,
    loginlog.OUTCOME_REJECTED,
    loginlog.OUTCOME_PASSWORD_EXPIRED,
    loginlog.OUTCOME_MUST_CHANGE_PASSWORD,
    loginlog.OUTCOME_ACCOUNT_LOCKED,
    loginlog.OUTCOME_ACCOUNT_DISABLED,
    loginlog.OUTCOME_ACCOUNT_EXPIRED,
    loginlog.OUTCOME_LOGON_NOT_PERMITTED,
    loginlog.OUTCOME_FAILED,
)
```

- **Why it is shaped this way**: importing `loginlog` into `api.py` is legal under the seam —
  `tests/test_storage_seam.py` bans engine imports and SQL shapes, and `loginlog` is pure
  functions with neither. Restating ten strings here instead would be the drift that
  `test_the_ui_outcome_vocabulary_matches_the_parser` (§9) exists to catch on the JS side, where
  restating is unavoidable.
- **Gotchas**: none beyond drift, which the import removes on this side.
- **Test**: `test_unknown_outcome_is_rejected_not_empty` (§9) — mutating the tuple (dropping an
  outcome) makes filtering that outcome a 422; mutating it to accept anything makes
  `?outcome=bogus` return an empty 200 that reads as "no such failures", which the test forbids.

### 2. API — the endpoint (`gsd/api.py`)

> **Codex:** **FIX-INADEQUATE** — `@consistent` correctly holds one read snapshot across the multiple
> store calls and the synchronous handler introduces no `await`. As written it cannot run against
> A's Store because all four called read methods and their result fields differ. It also exposes a
> sensitive username/authentication-result dataset through the application's existing broad auth
> surface without an explicit authorization decision. `values.yaml#ACCESS MODEL for the UI` says
> the default UI gate is authentication-only, and
> `values.yaml#THE REVIEW MUST MATCH WHAT /api EXPOSES.` delegates
> direct API access using permission to list clusterrolebindings. Neither permission implies the
> right to read OAuth pod logs. Before enabling this endpoint, bind it to an existing appropriately
> scoped authorization mechanism or explicitly require the chart's existing SAR configuration;
> do not silently widen what those principals can learn.

- **File**: `local-development/gsd/api.py`
- **Anchor**: inside `build_app`, insert the whole block **immediately before** this existing
  line (i.e. between the end of `membership_changes` and the alerts handler):

```python
    @app.get("/api/alerts")
```

- **Code**:

```python
    @app.get("/api/clusters/{cluster_id}/logins")
    @consistent
    def list_logins(
        cluster_id: str,
        outcome: str | None = Query(
            default=None, pattern=f"^({'|'.join(LOGIN_OUTCOMES)})$",
            description="Return only attempts with this outcome. The vocabulary is the "
                        "parser's: success, bad_password, rejected (not found OR not "
                        "permitted — the log cannot tell those apart), password_expired, "
                        "must_change_password, account_locked, account_disabled, "
                        "account_expired, logon_not_permitted, and failed (a cause the "
                        "parser does not recognise). Absent means every outcome."),
        user: str | None = Query(
            default=None,
            description="Return only attempts for this exact username — the login that was "
                        "TYPED, which may match no User object and no group member. That "
                        "mismatch is a finding, not an error."),
        limit: int = Query(
            default=200, ge=1, le=2000,
            description="Maximum attempts to return, newest first. `truncated` says whether "
                        "older ones were dropped; `total` and `summary` always describe the "
                        "whole record, never this page."),
    ) -> dict:
        """Login attempts against this cluster's oauth-server: who, when, and why it failed.

        Read from the oauth-server pod log, which only names the person at
        `spec.logLevel: Debug` on the authentication operator CR — so the record BEGINS
        when capture began (`observed_since`) and nothing before that exists to fetch:
        the log dies with the pod and the past cannot be reconstructed. An empty list is
        a statement about the window, never proof that nobody logged in.

        EVERY username is recorded, successful or not, member or not. `known_user: false`
        marks an account that belongs to NO synced group — the most valuable row here:
        either somebody whose access was removed and is still trying, or an account
        nobody governs. `ungoverned` lists those accounts distinctly so a paged
        chronology cannot bury them. Break-glass identities (an HTPasswd provider) are
        excluded from that list and labelled `break_glass` on their rows instead: they
        are not people to offboard, but "who used kubeadmin, and when" still deserves
        its rows.
        """
        require_cluster(cluster_id)
        # Which provider NAMES are HTPasswd is deployment configuration; the log only
        # carries the name. Applied to the ungoverned computation so break-glass accounts
        # cannot permanently occupy that list, and to the per-row flag below.
        htpasswd = tuple(settings.login_capture_htpasswd_providers)
        summary = store.login_summary(cluster_id, exclude_providers=htpasswd)
        status = store.login_capture_status(cluster_id)
        ungoverned = store.ungoverned_login_users(
            cluster_id, exclude_providers=htpasswd, limit=50)
        # limit + 1 to learn whether more exist — the cheap half of R3 (docs/api-contract.md),
        # the same idiom as list_users and list_events. `summary` above carries the exact
        # whole-record numbers, so no KPI is ever computed from this page.
        rows = store.login_attempts(
            cluster_id, user_name=user, outcome=outcome, limit=limit + 1)
        truncated = len(rows) > limit
        attempts = rows[:limit]
        for row in attempts:
            # The provider that DECIDED the outcome separates a directory identity from a
            # break-glass account (loginlog.LoginAttempt.provider). Normalised here so the
            # UI never re-derives either flag from raw fields.
            row["break_glass"] = row.get("provider") in htpasswd
            row["known_user"] = bool(row.get("known_user"))
        return {
            "cluster": cluster_id,
            "enabled": settings.login_capture_enabled,
            "note": "read from the oauth-server log at Debug verbosity; covers only the "
                    "period since capture began — earlier logins were never recorded and "
                    "cannot be fetched",
            # The §1.8 boundary, as data. The reader thread's watermark when there is one;
            # otherwise the oldest recorded attempt, which is the honest floor for a
            # database that predates the watermark table.
            "observed_since": (status or {}).get("observed_since") or summary["first_at"],
            "last_read_at": (status or {}).get("last_read_at"),
            "total": summary["total"],
            "limit": limit,
            "truncated": truncated,
            "summary": {
                "by_outcome": summary["by_outcome"],
                "distinct_users": summary["distinct_users"],
                "ungoverned_users": summary["ungoverned_users"],
                "first_at": summary["first_at"],
                "last_at": summary["last_at"],
            },
            # One row per account in NO synced group, most recent first. Bounded, and
            # honest about it: summary.ungoverned_users beside it is the whole-cluster
            # count, computed from the SAME predicate in the store.
            "ungoverned": ungoverned,
            "attempts": attempts,
        }
```

- **Why it is shaped this way**:
  - **Four store calls ⇒ `@consistent`** — `tests/test_api_contract.py::test_r5` counts
    `store.\w+(` per handler and requires the decorator above one call; without it the summary,
    the ungoverned list and the page could each land on a different snapshot and the page's
    `total` could contradict its own rows. The wrapped body is synchronous with no yield/await/
    network, satisfying `tests/test_read_snapshot_scope.py`.
  - **`limit` + `"total"` + `"truncated"`** satisfies `test_r3` both ways (exact and cheap), and
    the docstring/param descriptions satisfy R1/R2 (first line > 15 chars, not starting with
    "handler"/"endpoint"/"get"; every query param described — the outcome vocabulary is the
    `(cluster-scoped)`-style sentinel knowledge R2 exists for).
  - **GET only** — R6 stays intact; nothing here writes.
  - **Nothing reaches `/metrics`** — the constraint in Part 2.1: no username may appear on the
    unauthenticated endpoint, so this feature deliberately adds no metric at all (count-only
    login metrics already exist upstream as `openshift_auth_basic_password_count_result`,
    per Part 1.7).
- **Gotchas**:
  - *A filtered page vs whole-record summary*: `total`/`summary` are unfiltered on purpose — the
    KPIs must not shrink when the reader narrows the filter ("the problem getting smaller because
    they looked at it closely", the nsaudit lesson). The UI labels the table "N shown of M
    recorded" so the two numbers cannot be read as one.
  - *`observed_since` fallback*: with no watermark row and no attempts it is `null`; the UI
    renders "—" and the never-recorded empty state, not a fabricated instant (Part 1.7: never
    invent a timestamp).
  - *`pattern=` built from the tuple*: outcome names are `[a-z_]+` so the alternation is
    regex-safe; a 422 on an unknown outcome is deliberate — an empty 200 for `?outcome=typo`
    would read as "no such failures on this cluster".
  - *Comment hygiene*: no comment inside the handler contains the literal shape `store.x(`,
    because `test_r5` counts textual occurrences in the handler's source segment, comments
    included.
- **Test**: §9 `test_attempts_come_back_newest_first_with_the_fixture_truth` (field mapping and
  order), `test_limit_truncates_honestly` (mutation: computing `total` from the page),
  `test_ungoverned_user_is_flagged_and_listed` (mutation: losing the EXISTS join or the
  break-glass exclusion), `test_timestamps_stay_utc_z` (mutation: local-time drift).

### 3. API.md — the documented contract

> **Codex:** **FIX-INADEQUATE** — The response example is a useful contract, but A's proposed Store
> cannot produce its `known_user`, names, ungoverned rows, aggregate shape, or capture status. The
> “observed since” prose also conflates stable capture start with oldest retained data. Document
> both timestamps and the authorization requirement after the reconciled endpoint exists.

- **File**: `local-development/API.md` (integration: `tests/test_api_contract.py::`
  `test_every_endpoint_appears_in_api_md` fails the suite the moment the route exists and this
  file does not name the literal path).
- **Anchor**: insert after the `### GET /api/clusters/{cluster_id}/membership-changes` section
  (before `### GET /api/clusters/{cluster_id}/bindings/findings`), matching the file's
  per-endpoint heading style.
- **Code** (markdown):

```markdown
### `GET /api/clusters/{cluster_id}/logins`

Login attempts against this cluster's oauth-server, newest first — who logged in, who tried
and failed, and the classified cause where the directory reported one. Read from the
oauth-server pod log, which only names the person at `spec.logLevel: Debug` on the
authentication operator CR, so the record **begins when capture began** (`observed_since`)
and nothing before that exists to fetch. An empty list is a statement about the window,
never proof that nobody logged in.

Query parameters: `outcome` (one of `success`, `bad_password`, `rejected`,
`password_expired`, `must_change_password`, `account_locked`, `account_disabled`,
`account_expired`, `logon_not_permitted`, `failed`; unknown values are a 422, not an empty
list), `user` (exact username as typed at the prompt), `limit` (default 200, max 2000).

Response shape:

| field | meaning |
|---|---|
| `enabled` | whether capture is configured on (`loginCapture.enabled`); the record can be non-empty with this false — it just stops growing |
| `observed_since` | when the record begins: the reader's watermark, or the oldest recorded attempt; `null` when nothing has ever been captured |
| `last_read_at` | the last successful log read |
| `total`, `limit`, `truncated` | `total` counts the **whole record**; `truncated` says the page dropped older rows |
| `summary` | whole-record scalars: `by_outcome`, `distinct_users`, `ungoverned_users`, `first_at`, `last_at` — never computed from the page |
| `ungoverned` | one row per distinct account that belongs to **no synced group** (`user_name`, `attempts`, `first_at`, `last_at`, `last_outcome`), most recent first, capped at 50; `summary.ungoverned_users` is the uncapped count. Break-glass identities are excluded here and flagged on their rows instead |
| `attempts` | the page: `user_name`, `full_name` (or null), `outcome`, `at` (UTC, `Z`), `provider` (the provider that decided the outcome), `ldap_result_code`, `detail` (codes only — never the raw line), `known_user` (belongs to at least one synced group), `break_glass` (provider is HTPasswd) |

`rejected` deliberately bundles "user not found" and "not permitted by the login gate": the
identity provider's search filter carries the gate group, so the two produce byte-identical
log lines and separating them would require a directory read this application does not have.
```

- **Why**: the test matches the literal path string; the prose repeats the two things a consumer
  must not misread (the window, the `rejected` bucket) because this file is what `curl` users see.
- **Gotchas**: no `file.py#anchor` citations added — `tests/test_docs_citations.py` resolves every
  such anchor, and this section needs none.
- **Test**: `test_every_endpoint_appears_in_api_md` (existing) fails on omission; no new test.

### 4. UI — CSS: the seventh accent, in all three theme blocks + the page mapping

> **Codex:** CONFIRMED — An independent WCAG-formula run reproduced the stated ratios:
> `#0e7490` is 5.083:1 on the light page and 5.219:1 on its surface; `#21a1bd` is 6.384:1 on the
> dark page and 5.721:1 on its card. The tokenized theme additions comply with the existing
> literal-colour/type-scale checks.

- **File**: `local-development/gsd/static/index.html` (`<style>` block)
- **Anchor 1** — in the **first `:root {` block** (light theme), these exact lines (2-space indent):

```css
  --tab-nsaudit: #b3306e;
  --tab-usage: #c2410c;
  --accent: var(--tab-overview);
```

- **Code 1** (insert one line between usage and accent):

```css
  --tab-nsaudit: #b3306e;
  --tab-usage: #c2410c;
  /* 5.08:1 on --page, 5.22:1 on --surface-1 — measured with the WCAG 2.1 formula, not
     eyeballed. Cyan: the widest hue gap left after six accents; lightness-separated from
     both its neighbours (overview blue, groups teal), which is the separation the palette
     comment already relies on for deutan readers. */
  --tab-logins: #0e7490;
  --accent: var(--tab-overview);
```

- **Anchor 2** — in the `@media (prefers-color-scheme: dark)` block (4-space indent — this is
  what distinguishes it from the pinned-dark block below):

```css
    --tab-nsaudit: #e0559a;
    --tab-usage: #d9490d;
  }
}
```

- **Code 2**:

```css
    --tab-nsaudit: #e0559a;
    --tab-usage: #d9490d;
    /* 6.38:1 on the dark --page, 5.72:1 on the dark card. */
    --tab-logins: #21a1bd;
  }
}
```

- **Anchor 3** — in the `:root[data-theme="dark"]` block (2-space indent):

```css
  --tab-nsaudit: #e0559a;
  --tab-usage: #d9490d;
}
```

- **Code 3**:

```css
  --tab-nsaudit: #e0559a;
  --tab-usage: #d9490d;
  --tab-logins: #21a1bd;
}
```

- **Anchor 4** — the section-identity mapping:

```css
body[data-page="nsaudit"]  { --accent: var(--tab-nsaudit); }
body[data-page="usage"]    { --accent: var(--tab-usage); }
```

- **Code 4**:

```css
body[data-page="nsaudit"]  { --accent: var(--tab-nsaudit); }
body[data-page="logins"]   { --accent: var(--tab-logins); }
body[data-page="usage"]    { --accent: var(--tab-usage); }
```

- **Why it is shaped this way**: all three theme blocks, not two — the a11y test only reads
  `:root` and `:root[data-theme="dark"]`, but the **media-query block is what auto-dark users
  actually get**; omitting it there would pass the suite and render a light-cyan-on-dark tab at
  runtime (a token missing from the media block falls through to the light value). No literal
  `font-size` anywhere (`tests/test_type_scale.py`), no other new CSS at all: badges, chips,
  `.drill`, `.truncation-note`, `.kpis` and `.scroll-x` already exist and carry their own
  accessibility guarantees.
- **Gotchas**: the token name must match `--tab-[a-z]+` — `test_accessibility.py#_tab_tokens`
  derives the checked set with exactly that regex, which is what makes this token auto-checked in
  BOTH themes the moment it exists. A name like `--tab-loginCapture` would silently escape the
  suite.
- **Test**: existing `tests/test_accessibility.py::test_contrast` — parameterised over the derived
  token list; any mutation of either hex below 4.5:1 fails in the named theme. Verified before
  writing: both values pass with margin.

### 5. UI — state, filter row, tab (`index.html` script, small edits)

> **Codex:** CONFIRMED — Cluster, username, and outcome are URL-backed positional state, the
> controls use the existing filter idiom, and the new tab stays out of the display-timezone slice
> protected by `tests/test_display_timezone.py`. No build step or new framework is introduced.

- **File**: `local-development/gsd/static/index.html`

**5a. `view` gains the outcome filter** (a filter, deliberately NOT a `POSITION_KEYS` entry — the
comment above `POSITION_KEYS` draws exactly this line: positions get history entries, filters do
not).

- **Anchor** (start of the `view` literal):

```js
const view = { page: "overview", cluster: null, groupsync: null, groupFilter: "all", bindingFilter: "review",
```

- **Code** (replace that one line):

```js
const view = { page: "overview", cluster: null, groupsync: null, groupFilter: "all", bindingFilter: "review",
                loginOutcome: "all",
```

**5b. `data` gains its slot.**

- **Anchor**:

```js
let data = { clusters: [], alerts: [], groupsyncs: [], groups: [], events: null,
             group: null, user: null };
```

- **Code** (replace second line):

```js
let data = { clusters: [], alerts: [], groupsyncs: [], groups: [], events: null,
             group: null, user: null, logins: null };
```

**5c. The filter row.** Insert **after** the closing `}` of this existing block in
`renderFilters`:

```js
  if (view.page === "groups") {
    html += `<label for="f-state">Group state</label>
      <select id="f-state">
        <option value="all"${view.groupFilter === "all" ? " selected" : ""}>all</option>
        <option value="empty"${view.groupFilter === "empty" ? " selected" : ""}>empty</option>
        <option value="unattributed"${view.groupFilter === "unattributed" ? " selected" : ""}>unattributed</option>
      </select>`;
  }
```

- **Code** (the new block):

```js
  if (view.page === "logins") {
    // Options come from the same map the badges render from, so the filter can never
    // offer an outcome the table cannot display. Values are the parser's identifiers;
    // labels are the human words.
    html += `<label for="f-login-outcome">Outcome</label>
      <select id="f-login-outcome">
        <option value="all"${view.loginOutcome === "all" ? " selected" : ""}>all outcomes</option>
        ${Object.entries(LOGIN_OUTCOMES).map(([key, o]) =>
          `<option value="${key}"${view.loginOutcome === key ? " selected" : ""}>${o.label}</option>`).join("")}
      </select>`;
  }
```

**5d. The tab.** Anchor — this line inside the `<nav class="tabs">` template:

```js
      ${tab("nsaudit", "Namespace audit")}
```

- **Code** (insert after it, before the Usage tab — cluster-scoped pages stay together, the
  dashboard-scoped Usage stays last):

```js
      ${tab("nsaudit", "Namespace audit")}
      ${tab("logins", "Logins")}
```

**5e. Wire the select.** Anchor — these existing lines at the bottom of `renderFilters`:

```js
  const bf = $("f-binding");
  if (bf) bf.onchange = (e) => { view.bindingFilter = e.target.value; refresh(); };
```

- **Code** (insert after):

```js
  const lo = $("f-login-outcome");
  // Server-side filter (the store applies it), so this needs the round trip — same
  // shape as the bindings filter above.
  if (lo) lo.onchange = (e) => { view.loginOutcome = e.target.value; refresh(); };
```

- **Why / gotchas (all of 5)**: `LOGIN_OUTCOMES` (defined in §7) is a top-level `const` declared
  *later* in source than `renderFilters` — safe, because `renderFilters` first runs from
  `refresh()` after the first `await`, by which point the whole script body has executed (the
  same ordering `whoCell`/`WHO_PREVIEW` already rely on). The cluster selector stays visible on
  this page (unlike Usage) because the data is cluster-scoped — that is Decision Q5's point.
  Option labels/keys are static strings from the map, so no `esc()` is required there; everything
  dynamic elsewhere is escaped.
- **Test**: §10 `test_outcome_filter_narrows_the_table` — mutation: dropping the `refresh()` in
  the onchange (stale table), or filtering client-side (the ungoverned card would change too, which
  the test's scoped selector would surface).

### 6. UI — `backLabel` learns the new page (edit to an existing function)

> **Codex:** CONFIRMED — This is the necessary minimal navigation-label update and agrees with
> the `logins` position key used by the rest of B's UI.

- **File**: `local-development/gsd/static/index.html`
- **Anchor** (the last line of `backLabel`):

```js
  if (prev.groupsync) return `← ${esc(prev.groupsync)}`;
  return prev.page === "groups" ? "← all groups" : "← overview";
```

- **Code** (replace the final `return`):

```js
  if (prev.groupsync) return `← ${esc(prev.groupsync)}`;
  // The label must name where history.back() actually lands. A drill-down opened FROM the
  // Logins tab has `from.page === "logins"`, and labelling that "← overview" would be the
  // label-describes-a-place-the-click-does-not-go defect the navigate() rewrite fixed.
  if (prev.page === "logins") return "← logins";
  return prev.page === "groups" ? "← all groups" : "← overview";
```

- **Why**: without this, drilling from Logins to a user page renders a Back button labelled
  "← overview" that returns to Logins — the in-page button lying about its destination, the exact
  class of defect the history rewrite documents.
- **Gotchas**: the *pasted-link* branch above (`if (!prev)`) needs no change: a pasted link to a
  user page has `view.page === "groups"` and rises to the group list, which stays correct.
- **Test**: §10 `test_drilling_into_a_governed_user_goes_through_the_url` asserts the round trip;
  the label is asserted in the same test (mutation: reverting this edit mislabels the button).

### 7. UI — the page: `LOGIN_OUTCOMES`, `outcomeBadge`, `loginWindowNote`, `loginsPage`, `wireLogins`

> **Codex:** **FIX-INADEQUATE** — The dedicated ungoverned card makes the no-group username prominent
> and the glyph-plus-word badges do not rely on colour alone. The page nevertheless consumes fields
> A never returns and tells users that `observed_since` is the beginning of the record even though
> A prunes the per-pod rows proposed as its source. It also disables every ungoverned drill-down,
> incorrectly hiding valid historical user detail. Render stable capture-start and retained-since
> honestly, and make drillability depend on history/detail availability rather than current group
> membership.

- **File**: `local-development/gsd/static/index.html`
- **Anchor**: insert the whole block **immediately before** this existing comment (i.e. after the
  closing `}` of `usagePage`) — deliberately *outside* every source-landmark slice that
  `tests/test_display_timezone.py` takes (`fmtTime`, `setDisplayZone`, `fmtClock`, and the Usage
  table region all sit earlier in the file; nothing here contains the string `<th>Day (UTC)</th>`):

```js
/* Group drill-down: who is in it, since when, and what has changed. */
function groupDetail() {
```

- **Code**:

```js
/* ---- Logins ---------------------------------------------------------------------------
   Who came to the CLUSTER's door — every attempt the oauth-server named, successful or
   not. Cluster-scoped, unlike Usage (who used this dashboard), which is why it is its own
   tab and keeps the cluster selector. Timestamps arrive UTC and render through fmtTime,
   like everything else on this page. */

/* How many attempts the page asks for. Server-applied, so the rest never cross the wire;
   the response's `total` and `summary` are whole-record numbers computed server-side, so
   nothing on this page ever counts the page and calls it the cluster. */
const LOGIN_PAGE = 200;

/* Outcome vocabulary, hand-mirrored from gsd/loginlog.py (no build step means no import).
   tests/test_login_capture.py pins this map to the parser's constants, so the mirror
   cannot drift silently. The WORD is the signal a reader relies on; the severity colour is
   a scanning aid and the badge glyph gives it a shape — colour is never the only channel.
   `failed` is the parser saying "a cause I do not recognise": a grammar gap worth being
   loud about, hence critical while every CLASSIFIED failure is warning. */
const LOGIN_OUTCOMES = {
  success:              { label: "success",               sev: "ok" },
  bad_password:         { label: "bad password",          sev: "warning" },
  rejected:             { label: "rejected",              sev: "warning" },
  password_expired:     { label: "password expired",      sev: "warning" },
  must_change_password: { label: "must change password",  sev: "warning" },
  account_locked:       { label: "account locked",        sev: "warning" },
  account_disabled:     { label: "account disabled",      sev: "warning" },
  account_expired:      { label: "account expired",       sev: "warning" },
  logon_not_permitted:  { label: "not permitted",         sev: "warning" },
  failed:               { label: "failed (unclassified)", sev: "critical" },
};

function outcomeBadge(outcome) {
  // An outcome this map has never heard of still renders — as itself, in the unknown
  // shape — so a parser that grows a case cannot blank a row here while the mirror test
  // catches the gap in CI.
  const o = LOGIN_OUTCOMES[outcome] || { label: outcome, sev: "unknown" };
  return `<span class="badge ${o.sev}"><span class="glyph" aria-hidden="true"></span>${esc(o.label)}</span>`;
}

/* The coverage boundary (design §1.8), rendered as DATA rather than as an apology: the
   record is a window, the window has a start, and the start gets the same treatment as
   any other timestamp. Reused by the populated view AND the empty states, which is what
   keeps a sparse table from reading as "nobody logged in". */
function loginWindowNote(d) {
  if (!d.observed_since) return "";
  return `Record begins <strong>${esc(fmtTime(d.observed_since))}</strong>
    <span class="muted">(${esc(ago(d.observed_since))})</span> — when capture began.
    Logins before that were never recorded: the oauth-server only names the person at
    Debug verbosity, and its log dies with the pod.`;
}

function loginsPage() {
  const d = data.logins;
  if (!d) return `<section class="card"><div class="empty-note">Loading…</div></section>`;

  // Never captured AND not capturing: name the switches, the way the Usage tab does for
  // its own prerequisites. Distinct from "capturing, nothing seen yet", which is the
  // window note below — conflating them sends the reader hunting for logins that were
  // never going to be recorded.
  if (!d.enabled && !d.total) {
    return `<section class="card">
      <h2>Logins</h2>
      <div class="empty-note">
        Not being captured. This needs <strong>both</strong>
        <code>loginCapture.enabled=true</code> — the namespaced read of the oauth-server's
        log — and <code>authLogLevel: Debug</code> on the authentication operator, without
        which the log never names the person. Nothing is retroactive: the record starts
        when capture does.
      </div>
    </section>`;
  }

  const s = d.summary || {};
  const by = s.by_outcome || {};
  const successes = by.success || 0;
  const failures = (d.total || 0) - successes;
  const ungoverned = d.ungoverned || [];
  const rows = d.attempts || [];
  const filterLabel = view.loginOutcome !== "all"
    ? (LOGIN_OUTCOMES[view.loginOutcome] || { label: view.loginOutcome }).label : null;

  const lead = `<section class="card">
    <h2>Logins</h2>
    ${!d.enabled ? `<div class="filterbar-note truncation-note" style="margin-top:8px">
      Capture is currently <strong>disabled</strong>, so this record has stopped growing${
        d.last_read_at ? ` — it ends at ${esc(fmtTime(d.last_read_at))}` : ""}.
    </div>` : ""}
    <div class="hero">
      <div class="value">${s.ungoverned_users || 0}</div>
      <div class="label">account${(s.ungoverned_users || 0) === 1 ? "" : "s"} seen at the
        door that no synced group governs</div>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="label">Attempts recorded</div>
        <div class="value mono">${d.total || 0}</div></div>
      <div class="kpi"><div class="label">People</div>
        <div class="value mono">${s.distinct_users || 0}</div></div>
      <div class="kpi"><div class="label">Succeeded</div>
        <div class="value mono muted">${successes}</div></div>
      <div class="kpi ${failures ? "flag-warning" : ""}"><div class="label">Failed</div>
        <div class="value mono ${failures ? "" : "muted"}">${failures}</div></div>
      <div class="kpi"><div class="label">Watching since</div>
        <div class="value muted" style="font-size:15px">${
          d.observed_since ? esc(ago(d.observed_since)) : "—"}</div></div>
    </div>
    ${d.observed_since ? `<div class="filterbar-note" style="margin-top:10px">${loginWindowNote(d)}</div>` : ""}
  </section>`;

  // The most valuable rows, promoted above the chronology so a paged table cannot bury
  // them. Server-derived (its own bounded read over the same predicate as the count),
  // never reconstructed from the attempts page — a truncated page can be missing exactly
  // these accounts.
  const ungovernedCard = `<section class="card">
    <h2>${sevBadge("warning", "ungoverned")} Accounts in no synced group
      <span class="muted" style="font-weight:400">· ${s.ungoverned_users || 0}</span></h2>
    <div class="filterbar-note" style="margin:4px 0 8px">
      Each of these logged in — or tried to — and belongs to <strong>no group this
      dashboard syncs</strong>: either access was removed and somebody is still trying, or
      an account nobody governs. There is no drill-through because there is nothing to
      drill into; that absence is the finding. Break-glass accounts are not listed here —
      they are labelled in the record below instead.
    </div>
    ${ungoverned.length === 0
      ? `<div class="empty-note">Every account seen at the door belongs to at least one
           synced group${d.observed_since
             ? ` (record since ${esc(fmtTime(d.observed_since))})` : ""}.</div>`
      : `<div class="scroll-x"><table>
          <thead><tr><th>Account</th><th class="num">Attempts</th><th>Last attempt</th>
            <th>Last outcome</th><th>First seen</th></tr></thead>
          <tbody>${ungoverned.map((u) => `<tr>
            <td><code>${esc(u.user_name)}</code></td>
            <td class="num">${u.attempts}</td>
            <td class="mono">${esc(fmtTime(u.last_at))} <span class="muted">(${esc(ago(u.last_at))})</span></td>
            <td>${outcomeBadge(u.last_outcome)}</td>
            <td class="mono muted">${esc(fmtTime(u.first_at))}</td>
          </tr>`).join("")}</tbody>
        </table></div>`}
  </section>`;

  const attemptsCard = `<section class="card">
    <h2>Login attempts <span class="muted" style="font-weight:400">· ${rows.length}${
      filterLabel ? ` ${esc(filterLabel)}` : ""} shown of ${d.total || 0} recorded</span></h2>
    ${rows.length === 0
      ? `<div class="empty-note">${filterLabel
          ? `No <strong>${esc(filterLabel)}</strong> attempts in the record.`
          : `No login attempts recorded yet. ${loginWindowNote(d) ||
             "Capture writes rows as people log in; the record starts when capture does."}`}</div>`
      : `<div class="scroll-x"><table>
          <thead><tr><th>When</th><th>User</th><th>Outcome</th><th>Provider</th><th>Detail</th></tr></thead>
          <tbody>${rows.map((a) => `<tr>
            <td class="mono">${esc(fmtTime(a.at))}</td>
            <td>${a.known_user
                ? `<button type="button" class="drill" data-login-user="${esc(a.user_name)}">${esc(a.user_name)}</button>`
                : `<code>${esc(a.user_name)}</code>${a.break_glass ? "" :
                    ` <span class="badge warning"><span class="glyph" aria-hidden="true"></span>no synced group</span>`}`}${
                a.full_name ? ` <span class="muted">· ${esc(a.full_name)}</span>` : ""}</td>
            <td>${outcomeBadge(a.outcome)}</td>
            <td><code>${esc(a.provider || "—")}</code>${a.break_glass
                ? ` <span class="chip">break-glass</span>` : ""}</td>
            <td class="muted">${esc(a.detail || "—")}</td>
          </tr>`).join("")}</tbody>
        </table></div>`}
    ${d.truncated ? `<div class="filterbar-note truncation-note" style="margin-top:8px">
      Showing the <strong>${rows.length}</strong> most recent. The counts above cover the
      whole record.
    </div>` : ""}
  </section>`;

  return lead + ungovernedCard + attemptsCard;
}

function wireLogins() {
  // Through navigate(), so the drill-down lands in the URL and the browser's Back returns
  // HERE (POSITION_KEYS already carries page/cluster/user). The target is the existing
  // user page — where "what does this person still have?" is already answered. Only
  // governed users drill: an ungoverned account has no user page (user_detail 404s with
  // no memberships and no history), and a button to a guaranteed error page is worse than
  // the labelled fact. The handler sits on the <button class="drill"> itself, so Enter
  // and Space come free — no keydown shim needed, unlike the row-level handlers in
  // wireDrilldown.
  document.querySelectorAll("[data-login-user]").forEach((el) => {
    el.onclick = () => {
      navigate({ page: "groups", user: el.dataset.loginUser, group: null, groupsync: null });
      refresh();
    };
  });
}
```

- **Why it is shaped this way**:
  - `fmtTime`/`ago` everywhere — never a hand-sliced ISO string (the `.slice(11, 19)` regression
    `test_display_timezone.py` documents). `at` arrives with microseconds and a `Z`;
    `new Date(iso)` handles it, and the zone label rides on the value as on every other page.
  - `esc()` on every interpolated value, including `detail`, `provider`, `full_name` and the
    window note's formatted times — the `backLabel` comment in this file records a real XSS via
    the URL-sourced hash, and login usernames are *attacker-typed by definition* (anything
    entered at the login prompt lands in `user_name`).
  - Wide tables sit in `.scroll-x`; the page body never scrolls sideways (asserted in §10).
  - No new CSS classes; the three cards reuse the existing hierarchy (lead card gets the accent
    rail automatically via `main > .card:first-child`).
- **Gotchas**:
  - *Sparse ≠ idle*: both empty states route through `loginWindowNote`, so "no rows" is always
    phrased as a fact about the window when a window exists. The mutation — replacing the empty
    state with a bare "No logins" — is caught by §10
    `test_an_empty_record_names_the_window_not_the_absence`.
  - *Break-glass rows must not also wear the "no synced group" badge*: `kubeadmin`/`developer`
    are ungoverned by construction, and double-flagging them would make the warning badge
    ambient noise. The ternary renders the chip *instead of* the badge for `break_glass` rows.
  - *`data.logins` is written without a per-fetch `superseded()` guard*, exactly like
    `data.userBindings` in the nsaudit fetch — the final `superseded()` check before `render()`
    covers navigation races for page-scoped data; only the drill-down fetches need the stronger
    discard (their data outlives the render via `data.group`/`data.user`).
  - *Unknown outcome from a newer server*: `outcomeBadge` falls back to the raw identifier in the
    `unknown` badge shape rather than rendering nothing — an old page against a new API degrades
    to ugly-but-true.
- **Test**: §10 `TestLogins` (all of it); §9 `test_the_ui_outcome_vocabulary_matches_the_parser`
  pins the JS map to the Python constants (mutation: adding an outcome to the parser without
  teaching the map, or a typo in a key).

### 8. UI — dispatch and fetch (`render()` / `refresh()`)

> **Codex:** CONFIRMED — The page dispatch, stale-request guard, encoded query parameters, and
> existing `api()`/`render()` flow are consistent with the single-file application. This block is
> mechanically usable once the endpoint contract is reconciled.

- **File**: `local-development/gsd/static/index.html`

**8a. `render()` branch.** Anchor:

```js
  } else if (view.page === "usage") {
    main.innerHTML = usagePage();
  } else if (view.page === "bindings") {
```

- **Code** (insert the logins branch between them):

```js
  } else if (view.page === "usage") {
    main.innerHTML = usagePage();
  } else if (view.page === "logins") {
    main.innerHTML = loginsPage();
    wireLogins();
  } else if (view.page === "bindings") {
```

**8b. `refresh()` fetch.** Anchor — the end of the existing nsaudit block:

```js
      data.userBindings = await get(
        `/api/clusters/${encodeURIComponent(view.cluster)}/user-bindings?${q}`);
    }
```

- **Code** (insert after that closing `}`):

```js
    if (view.page === "logins" && view.cluster) {
      // The outcome filter is applied SERVER-side, like the nsaudit namespace filter:
      // the point of the limit is to stop shipping every row, and a client-side filter
      // still pays for all of them over the wire.
      const q = new URLSearchParams({ limit: String(LOGIN_PAGE) });
      if (view.loginOutcome !== "all") q.set("outcome", view.loginOutcome);
      data.logins = await get(
        `/api/clusters/${encodeURIComponent(view.cluster)}/logins?${q}`);
    }
```

- **Why**: fetched only on its own tab (the other pages must not pay for it — the Usage fetch
  comment states the rule); `encodeURIComponent` on the cluster like every sibling call; the
  30-second auto-refresh keeps the record live without registering as usage (the `mark`
  machinery is untouched).
- **Gotchas**: the fetch must come *before* the final `superseded()`/`render()` pair (it does, by
  construction of the anchor) or a stale page could paint with `data.logins` from the previous
  cluster. A failed fetch (e.g. 404 from an older server image) falls into `refresh()`'s existing
  catch and renders the error card with a working Back — no new error path to maintain.
- **Test**: §10 `test_the_tab_renders_with_the_fixture_attempts` (mutation: dropping the fetch
  leaves the page on "Loading…" and the test times out); the auto-refresh behaviour is covered by
  the existing interaction-counting tests, untouched.

### 9. The test suite — `tests/test_login_capture.py` (complete file)

> **Codex:** REFUTED — as a test file for the combined design. Its seeds and assertions call B's
> nonexistent Store methods and construct attempts without A's required `pod_name`; its Settings
> use a field A never defines. It therefore fails before it can validate the endpoint. Rewrite it
> against the selected contract, preserve the pod-inclusive collision test, add stable-start versus
> retained-since coverage, and test endpoint authorization. Also note that the current repository's
> docs-citation test already rejects this design's forward reference to the proposed login handler
> until that symbol lands; that is an expected application-order dependency, not a green baseline.

- **File**: `local-development/tests/test_login_capture.py` (new)
- **Fixtures**: the two real logs get committed as test fixtures (integration step — I cannot
  write into the repo from this task):

```bash
mkdir -p local-development/tests/fixtures
cp "$SCRATCH/fixture.log"  local-development/tests/fixtures/oauth-login-fixture.log   # 12 lines
cp "$SCRATCH/real.log"     local-development/tests/fixtures/oauth-login-real.log      # 300 lines
# where $SCRATCH = /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/325dfd2f-469e-4bd4-b279-331704911184/scratchpad
```

- **Code** (the complete file — every synthetic line below was run through the committed parser
  before being asserted on; the AD sub-code lines produce exactly the outcomes asserted, and the
  fixture parses to the five attempts named in the header of this document):

```python
"""Login capture, from the real oauth-server log through the store to the API.

These are INTEGRATION tests: gsd/loginlog.py's grammar is exercised through the store's
dedup and the API's contract, not re-tested line by line. The fixture is 12 REAL lines
captured from a live cluster (five attempts: an LDAP success, a bad password, two
rejections, and an HTPasswd break-glass success); the 300-line real log is the same window
with the ordinary httplog/reflector noise left in.

Each test names the mutation it catches. A test that keeps passing when the behaviour it
names regresses is decoration, and this suite is written to fail loudly instead.
"""

from __future__ import annotations

import pathlib
import re

import pytest
from fastapi.testclient import TestClient

from gsd import loginlog
from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.loginlog import parse
from gsd.store import Store
from gsd.timeutil import now_iso

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"
FIXTURE_LOG = FIXTURES / "oauth-login-fixture.log"   # 12 real lines, 5 attempts
REAL_LOG = FIXTURES / "oauth-login-real.log"         # 300 real lines, same 5 attempts
INDEX = pathlib.Path(__file__).resolve().parents[1] / "gsd" / "static" / "index.html"

CLUSTER = "crc-local"

# Measured by running the committed parser over the fixture (not assumed): user -> (outcome,
# provider). `developer` is the HTPasswd break-glass success; the other four are LDAP.
FIXTURE_TRUTH = {
    "john.doe":   ("success", "ldap-local"),
    "jane.smith": ("bad_password", "ldap-local"),
    "bob.wilson": ("rejected", "ldap-local"),
    "nosuchuser": ("rejected", "ldap-local"),
    "developer":  ("success", "developer"),
}

# The AD sub-codes of design §1.3, each of which arrives as a bare code 49 and is only
# tellable from the diagnostic's `data <hex>`. The pairs are the parser's own map
# (loginlog._AD_SUBCODE), asserted here THROUGH the store and the API.
AD_CASES = [
    ("532", "password_expired"),
    ("773", "must_change_password"),
    ("775", "account_locked"),
    ("533", "account_disabled"),
    ("52e", "bad_password"),
    ("525", "rejected"),
    ("530", "logon_not_permitted"),
]


def _ad_attempt(user: str, sub: str, minute: int) -> str:
    """One SINGLE-PROVIDER-SHAPED attempt: the cause line arrives BEFORE any verdict.

    This is the ordinary production shape from design §1.5 — on a cluster whose only
    provider is LDAP, `ldap.go` speaks first and no username exists yet — so every one of
    these also exercises the orphan-adoption path, not just the sub-code map. Verified
    against the committed parser before these assertions were written.
    """
    stamp = f"2026-08-07T17:{minute:02d}:00"
    return (
        f"{stamp}.100000000Z I0807 17:{minute:02d}:00.100100       1 ldap.go:152] "
        f'error binding password for "cn={user},ou=people,dc=corp,dc=example": '
        f'LDAP Result Code 49 "Invalid Credentials": 80090308: LdapErr: DSID-0C0903A9, '
        f"comment: AcceptSecurityContext error, data {sub}, v4563\n"
        f"{stamp}.200000000Z I0807 17:{minute:02d}:00.200100       1 basicauth.go:48] "
        f'Login with provider "ldap-ad" failed for login "{user}"\n'
    )


def _settings(db_path: str) -> Settings:
    return Settings(
        db_path=db_path,
        clusters=[ClusterConfig(CLUSTER, "https://api.crc.testing:6443", token_env="X")],
        login_capture_enabled=True,
        login_capture_htpasswd_providers=["developer"],
    )


@pytest.fixture()
def store(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.upsert_cluster(CLUSTER, "https://api.crc.testing:6443", True)
    yield s
    s.close()


@pytest.fixture()
def client(tmp_path):
    """A TestClient over the SAME database file the `store` fixture writes.

    File-backed on purpose: two connections to one file see each other's commits, which is
    exactly the production shape (poller writes, API reads).
    """
    return TestClient(build_app(_settings(str(tmp_path / "t.db")), run_poller=False))


def _logins(client, **params) -> dict:
    q = "&".join(f"{k}={v}" for k, v in params.items())
    r = client.get(f"/api/clusters/{CLUSTER}/logins" + (f"?{q}" if q else ""))
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------------------------------
# store: the fixture lands, once
# ---------------------------------------------------------------------------------------

def test_the_fixture_lands_once_and_only_once(store, client):
    """Overlapping sinceSeconds windows re-read the same lines; the record must not grow.

    MUTATION CAUGHT: losing INSERT OR IGNORE or narrowing the natural key — the second
    record call would then insert five duplicates and total reads 10.
    """
    attempts = parse(FIXTURE_LOG.read_text())
    assert len(attempts) == 5, "the 12-line fixture parses to five attempts"
    assert store.record_login_attempts(CLUSTER, attempts) == 5
    assert store.record_login_attempts(CLUSTER, attempts) == 0, "re-read must be a no-op"
    assert _logins(client)["total"] == 5


def test_the_real_log_parses_through_the_stack(store, client):
    """300 real lines, 295 of them noise (httplog, reflector, probes).

    MUTATION CAUGHT: any regression that trips on non-login lines — a reader that feeds
    the whole log is the production shape, and the noise must cost nothing.
    """
    store.record_login_attempts(CLUSTER, parse(REAL_LOG.read_text()))
    body = _logins(client)
    assert body["total"] == 5
    assert {a["user_name"] for a in body["attempts"]} == set(FIXTURE_TRUTH)


# ---------------------------------------------------------------------------------------
# API: contract against the fixture truth
# ---------------------------------------------------------------------------------------

def test_attempts_come_back_newest_first_with_the_fixture_truth(store, client):
    """Field mapping and ordering, checked against the measured parse of the real lines.

    MUTATION CAUGHT: ORDER BY at ASC (the page would then show the OLDEST slice and a
    truncated record silently hides this morning's logins); any column-mapping slip
    between LoginAttempt and the row dict.
    """
    store.record_login_attempts(CLUSTER, parse(FIXTURE_LOG.read_text()))
    rows = _logins(client)["attempts"]
    assert [r["user_name"] for r in rows] == [
        "developer", "nosuchuser", "bob.wilson", "jane.smith", "john.doe"
    ], "newest first — the fixture's five attempts in reverse wall-clock order"
    for r in rows:
        outcome, provider = FIXTURE_TRUTH[r["user_name"]]
        assert r["outcome"] == outcome
        assert r["provider"] == provider
    jane = next(r for r in rows if r["user_name"] == "jane.smith")
    assert jane["ldap_result_code"] == 49
    assert jane["detail"] == "LDAP result code 49"


def test_ad_subcodes_survive_the_round_trip(store, client):
    """Design §1.3: on AD, expired/locked/disabled all arrive as a bare 49; the sub-code
    is the only place the real cause lives, and it must survive store and API intact.

    MUTATION CAUGHT: any store/API layer that keeps only the result code (every one of
    these would flatten to bad_password — sending someone to reset a password that is
    already correct, the exact mislabel §1.3 documents).
    """
    text = "".join(
        _ad_attempt(f"user{sub}", sub, minute) for minute, (sub, _) in enumerate(AD_CASES)
    )
    store.record_login_attempts(CLUSTER, parse(text))
    got = {r["user_name"]: r for r in _logins(client)["attempts"]}
    for sub, want in AD_CASES:
        row = got[f"user{sub}"]
        assert row["outcome"] == want, f"data {sub} must classify as {want}"
        assert row["ldap_result_code"] == 49
        assert f"sub-code {sub}" in row["detail"]
    # And the outcome filter selects on the CLASSIFIED outcome, not the raw code.
    only = _logins(client, outcome="password_expired")["attempts"]
    assert [r["user_name"] for r in only] == ["user532"]


def test_single_provider_cause_precedes_the_verdict(store, client):
    """Design §1.5, named on its own: the cause line arrives before ANY verdict names the
    user (the only-provider-is-LDAP shape), and the adopted cause must reach the API.

    MUTATION CAUGHT: regressions in the orphan-adoption window that silently drop every
    cause on single-provider clusters — recorded here as the difference between
    password_expired and a bare failed/bad_password.
    """
    store.record_login_attempts(CLUSTER, parse(_ad_attempt("expired.solo", "532", 45)))
    rows = _logins(client, user="expired.solo")["attempts"]
    assert len(rows) == 1
    assert rows[0]["outcome"] == "password_expired"


def test_limit_truncates_honestly(store, client):
    """R3: a clipped page must say so, and the headline numbers must not shrink with it.

    MUTATION CAUGHT: computing total/summary from the returned page (the "showing 50 of
    30" defect class this codebase has now hit three times).
    """
    store.record_login_attempts(CLUSTER, parse(FIXTURE_LOG.read_text()))
    body = _logins(client, limit=2)
    assert len(body["attempts"]) == 2
    assert body["truncated"] is True
    assert body["total"] == 5
    assert body["summary"]["distinct_users"] == 5


def test_ungoverned_user_is_flagged_and_listed(store, client):
    """The most valuable row: a login by an account in NO synced group.

    MUTATION CAUGHT: losing the known_user EXISTS join (every row reads governed and the
    finding disappears); losing the break-glass exclusion (developer permanently occupies
    the ungoverned list and trains readers to ignore it); count/list predicate drift
    (summary says 3 while the list shows something else).
    """
    store.sync_members(
        CLUSTER,
        {"app-ocp-rbac-alpha-ns-admin": ["john.doe"]},
        {"app-ocp-rbac-alpha-ns-admin": None},
        now_iso(),
    )
    store.record_login_attempts(CLUSTER, parse(FIXTURE_LOG.read_text()))
    body = _logins(client)
    flags = {r["user_name"]: r["known_user"] for r in body["attempts"]}
    assert flags["john.doe"] is True
    assert flags["jane.smith"] is False
    listed = {u["user_name"] for u in body["ungoverned"]}
    assert listed == {"jane.smith", "bob.wilson", "nosuchuser"}, (
        "governed (john.doe) and break-glass (developer) must both be excluded"
    )
    assert body["summary"]["ungoverned_users"] == 3, (
        "the whole-set count must agree with the list it sits beside"
    )


def test_break_glass_is_labelled_not_hidden(store, client):
    """Design decision: shown and labelled, never dropped — who used the break-glass
    account, and when, is a governance question in its own right.

    MUTATION CAUGHT: filtering break-glass rows out of the record, or losing the flag.
    """
    store.record_login_attempts(CLUSTER, parse(FIXTURE_LOG.read_text()))
    rows = _logins(client)["attempts"]
    by_user = {r["user_name"]: r for r in rows}
    assert by_user["developer"]["break_glass"] is True
    assert by_user["john.doe"]["break_glass"] is False
    assert "developer" in by_user, "break-glass rows must stay in the record"


def test_observed_since_prefers_the_watermark(store, client):
    """The §1.8 boundary: the watermark is the truth about when capture began; the oldest
    row is only the fallback for a record that predates the watermark table.

    MUTATION CAUGHT: deriving observed_since from MIN(at) when a watermark exists — after
    a retention prune that would silently move the claimed window start.
    """
    store.record_login_attempts(CLUSTER, parse(FIXTURE_LOG.read_text()))
    body = _logins(client)
    assert body["observed_since"] == "2026-08-07T16:56:28.267663Z", (
        "no watermark yet: the oldest recorded attempt is the honest floor"
    )
    store.record_login_read(
        CLUSTER, "oauth-openshift-abc12", "2026-08-01T00:00:00Z", "2026-08-07T17:00:00Z"
    )
    body = _logins(client)
    assert body["observed_since"] == "2026-08-01T00:00:00Z"
    assert body["last_read_at"] == "2026-08-07T17:00:00Z"


def test_timestamps_stay_utc_z(store, client):
    """Storage and the wire stay UTC ending in Z; conversion happens in the browser only
    (the same invariant test_display_timezone pins for the rest of the API).

    MUTATION CAUGHT: a store layer that stamps local time or emits +00:00 offsets — rows
    written before and after a TZ change would then mean different things.
    """
    store.record_login_attempts(CLUSTER, parse(FIXTURE_LOG.read_text()))
    body = _logins(client)

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                yield from walk(v)
        elif isinstance(node, list):
            for v in node:
                yield from walk(v)
        elif isinstance(node, str):
            yield node

    for value in walk(body):
        if re.match(r"^\d{4}-\d{2}-\d{2}T", value):
            assert value.endswith("Z"), f"non-UTC timestamp on the wire: {value}"


def test_unknown_cluster_is_404(client):
    """MUTATION CAUGHT: dropping require_cluster — an unknown cluster would then answer
    with an empty-but-healthy record instead of an error."""
    assert client.get("/api/clusters/nope/logins").status_code == 404


def test_unknown_outcome_is_rejected_not_empty(store, client):
    """A typo'd outcome must be a 422, never an empty 200 that reads as "no such
    failures on this cluster".

    MUTATION CAUGHT: dropping the pattern= on the outcome query parameter.
    """
    store.record_login_attempts(CLUSTER, parse(FIXTURE_LOG.read_text()))
    assert client.get(f"/api/clusters/{CLUSTER}/logins?outcome=bogus").status_code == 422


# ---------------------------------------------------------------------------------------
# the hand-mirrored UI vocabulary cannot drift
# ---------------------------------------------------------------------------------------

def test_the_ui_outcome_vocabulary_matches_the_parser():
    """LOGIN_OUTCOMES in index.html is a hand mirror of the parser's constants — the cost
    of one file and no build step. This pin is what makes that debt safe to carry.

    MUTATION CAUGHT: the parser growing an outcome the UI cannot label (it would render
    as a raw identifier in the unknown badge — visible but wrong), or a typo'd key in the
    JS map (that outcome's badge silently degrades on every row).
    """
    html = INDEX.read_text()
    block = html[html.index("const LOGIN_OUTCOMES"):]
    block = block[: block.index("};")]
    ui = set(re.findall(r"^\s{2}(\w+):", block, re.M))
    parser = {
        getattr(loginlog, name)
        for name in dir(loginlog)
        if name.startswith("OUTCOME_")
    }
    assert ui == parser, (
        f"UI badge map and parser vocabulary disagree: "
        f"UI-only {sorted(ui - parser)}, parser-only {sorted(parser - ui)}"
    )
```

- **Why it is shaped this way**: file-backed DB shared between the seeding `Store` and the app's
  own backend (the `test_display_timezone.py` idiom); everything asserted from the wire, so a
  regression in *any* of parse→store→API fails, not only the layer it lives in; the AD cases use
  the single-provider line order so §1.3 and §1.5 are load-bearing in the same rows.
- **Gotchas**: `Settings(login_capture_enabled=..., login_capture_htpasswd_providers=...)` are
  the named assumptions — a dataclass rejects unknown kwargs, so the suite fails at collection
  until A's fields land, which is the correct failure mode (loud, at the seam, naming the field).

### 10. The UI tests — additions to `tests/test_ui.py`

> **Codex:** **FIX-INADEQUATE** — These tests inherit B's nonexistent seed/settings API and cannot run
> until the storage seam is reconciled. The proposed “server-side aggregation” assertion proves the
> ungoverned card survives an attempt filter, but does not by itself prove the aggregate was computed
> over the full set; assert the HTTP response/card count with an ungoverned event outside the first
> page. Local execution could not start Chromium or bind the test server under this sandbox, so no
> browser result is claimed; the non-browser suite ran independently (569 passed, 4 skipped).

- **File**: `local-development/tests/test_ui.py`

**10a. Imports.** Anchor — the existing import block ends:

```python
import pytest
import uvicorn

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.store import Store
```

- **Code** (add two lines):

```python
import pathlib

import pytest
import uvicorn

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.loginlog import parse as parse_logins
from gsd.store import Store

LOGIN_FIXTURE = pathlib.Path(__file__).resolve().parent / "fixtures" / "oauth-login-fixture.log"
```

**10b. Seed.** Anchor — this existing statement inside `_seed` (the display-names seed):

```python
    store.replace_users("crc-local", {"alice": "Alice Cooper"}, _iso(now))
```

- **Code** (insert after it):

```python
    # Login capture: the REAL 12-line fixture (five attempts), plus one synthetic success
    # by alice — the one login name a synced group governs — in the exact line shape the
    # oauth-server emits (verified through the parser). jane.smith is the load-bearing
    # row: a login by an account in NO synced group. developer is break-glass (HTPasswd).
    login_lines = LOGIN_FIXTURE.read_text() + (
        '2026-08-07T18:00:00.000000000Z I0807 18:00:00.000000       1 basicauth.go:51] '
        'Login with provider "ldap-local" succeeded for login "alice": \n'
    )
    store.record_login_attempts("crc-local", parse_logins(login_lines))
    store.record_login_read("crc-local", "oauth-openshift-abc12",
                            _iso(now - timedelta(days=2)), _iso(now))
    # prod-east: a watermark and ZERO attempts — the sparse-window state the empty copy
    # must name as a window, never as "nobody logged in".
    store.record_login_read("prod-east", "oauth-openshift-xyz34",
                            _iso(now - timedelta(hours=3)), _iso(now))
```

**10c. Settings.** Anchor — inside the `server` fixture:

```python
    settings = Settings(
        clusters=[
            ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X"),
            ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="Y"),
        ],
        db_path=db,
    )
```

- **Code** (replace the `db_path=db,` line):

```python
        db_path=db,
        login_capture_enabled=True,
        login_capture_htpasswd_providers=["developer"],
    )
```

**10d. The test class.** Anchor: append after the existing `class TestBrowserHistory:` block (end
of file region; exact placement among trailing classes is not load-bearing).

- **Code**:

```python
class TestLogins:
    """The Logins tab: who came to the cluster's door, from the real 12-line fixture.

    Five real attempts plus one synthetic alice success (the only governed login name), a
    two-day-old watermark on crc-local, and a watermark-with-no-rows on prod-east.
    """

    def _open(self, dash):
        dash.locator("button[data-nav='logins']").click()
        dash.wait_for_function("() => document.body.dataset.page === 'logins'")
        dash.wait_for_selector("text=Attempts recorded")

    def test_the_tab_renders_with_the_fixture_attempts(self, dash):
        """MUTATION: dropping the refresh() fetch leaves 'Loading…' forever; a render
        error is surfaced by the dash fixture's pageerror trap."""
        self._open(dash)
        body = dash.locator("body").inner_text()
        assert "john.doe" in body and "jane.smith" in body

    def test_an_ungoverned_account_is_findable_not_buried(self, dash):
        """jane.smith belongs to NO synced group — the most valuable row. She must appear
        in the dedicated section above the chronology, not only at whatever scroll depth
        her timestamp lands. MUTATION: deriving the section from the paged attempts, or
        dropping it — the section either misses her or vanishes."""
        self._open(dash)
        section = dash.locator("section.card", has_text="Accounts in no synced group")
        text = section.inner_text()
        assert "jane.smith" in text and "bob.wilson" in text and "nosuchuser" in text
        assert "alice" not in text, "a governed account must not be listed as ungoverned"

    def test_break_glass_is_labelled_and_not_in_the_ungoverned_list(self, dash):
        """Shown + labelled, never hidden — and never parked permanently in the
        ungoverned section, which would train readers to ignore it (the built_in-tier
        lesson). MUTATION: losing the chip, or the exclusion."""
        self._open(dash)
        ungoverned = dash.locator("section.card", has_text="Accounts in no synced group")
        assert "developer" not in ungoverned.inner_text()
        attempts = dash.locator("section.card", has_text="Login attempts")
        assert "break-glass" in attempts.inner_text()
        assert "developer" in attempts.inner_text(), "the row itself must stay visible"

    def test_the_observed_since_boundary_is_visible(self, dash):
        """Design §1.8 on screen, as data. MUTATION: dropping the KPI or the window
        sentence turns the boundary back into tribal knowledge."""
        self._open(dash)
        body = dash.locator("body").inner_text()
        assert "Watching since" in body
        assert "Record begins" in body

    def test_an_empty_record_names_the_window_not_the_absence(self, dash):
        """prod-east has a watermark and zero rows: the empty state must present the
        window ("Record begins …"), because a sparse table that just says "no logins"
        reads as 'nobody logged in', which the source cannot support. MUTATION: a bare
        empty-state string."""
        self._open(dash)
        dash.select_option("#f-cluster", "prod-east")
        dash.wait_for_function(
            "() => view.cluster === 'prod-east' && document.body.dataset.page === 'logins'")
        dash.wait_for_selector("text=No login attempts recorded yet")
        body = dash.locator("body").inner_text()
        assert "Record begins" in body, "the empty state must name the window"

    def test_drilling_into_a_governed_user_goes_through_the_url(self, dash):
        """The drill must ride navigate(): position in the URL, browser Back returns to
        Logins, and the in-page label names it. MUTATION: a handler that mutates `view`
        directly — the URL stays stale and go_back leaves the dashboard."""
        self._open(dash)
        dash.locator(".drill[data-login-user='alice']").first.click()
        dash.wait_for_selector("text=Group memberships")
        assert "page=groups" in dash.url and "user=alice" in dash.url
        assert "logins" in dash.locator("#back-groups").inner_text()
        dash.go_back()
        dash.wait_for_function("() => document.body.dataset.page === 'logins'")

    def test_an_ungoverned_account_offers_no_drill_to_a_404(self, dash):
        """user_detail 404s for a name with no memberships and no history, so an
        ungoverned login name must not render as a drill button. MUTATION: making every
        username drillable — jane.smith's button would lead to the error card."""
        self._open(dash)
        assert dash.locator(".drill[data-login-user='jane.smith']").count() == 0
        assert dash.locator(".drill[data-login-user='alice']").count() >= 1

    def test_outcome_words_are_present_not_colour_alone(self, dash):
        """Every outcome badge carries its word (WCAG 1.4.1); the fixture exercises three
        different ones. MUTATION: a badge rendered as a bare coloured glyph."""
        self._open(dash)
        body = dash.locator("body").inner_text()
        assert "bad password" in body and "rejected" in body and "success" in body

    def test_outcome_filter_narrows_the_table_only(self, dash):
        """The filter narrows the CHRONOLOGY server-side; the ungoverned section and the
        KPIs keep describing the whole record. MUTATION: filtering client-side (the
        ungoverned card would shrink too), or dropping the refetch."""
        self._open(dash)
        dash.select_option("#f-login-outcome", "bad_password")
        dash.wait_for_function(
            "() => { const s = [...document.querySelectorAll('section.card')]"
            ".find(c => c.innerText.includes('Login attempts'));"
            " return s && s.innerText.includes('jane.smith')"
            " && !s.innerText.includes('nosuchuser'); }")
        ungoverned = dash.locator("section.card", has_text="Accounts in no synced group")
        assert "nosuchuser" in ungoverned.inner_text(), (
            "the ungoverned section must not follow the chronology filter"
        )

    def test_no_horizontal_scroll_on_the_logins_tab(self, dash):
        """Wide tables scroll in their own .scroll-x container, never the page body."""
        self._open(dash)
        overflow = dash.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 0, f"logins page scrolls horizontally by {overflow}px"
```

- **Why / gotchas**: `_seed`'s existing group data is untouched (the 3-group and member-list
  assertions elsewhere in the file keep passing); alice's membership makes her the *only*
  governed login name, so the drill/no-drill pair is deterministic. The synthetic alice line was
  verified through the parser (success, `ldap-local`, `2026-08-07T18:00Z`). The
  outcome-filter test scopes its selector to the attempts card because jane.smith and nosuchuser
  legitimately appear in the ungoverned card regardless of filter — an unscoped body-text
  assertion would be a false failure.

---

## Integration points I touched outside my area

1. **`gsd/storage.py`** — the six method declarations in the `StorageBackend` Protocol (listed in
   the Assumptions section verbatim). A's file; the seam test requires them to be declared there,
   not just implemented.
2. **`gsd/config.py#Settings`** — two fields (`login_capture_enabled`,
   `login_capture_htpasswd_providers`) plus whatever env/values plumbing A's capture thread
   already needs; the chart's `loginCapture.enabled` value already exists, `htpasswdProviders`
   would be a new value (flagged below).
3. **`local-development/API.md`** — §3 above; required by
   `test_api_contract.py::test_every_endpoint_appears_in_api_md` the moment the route exists.
4. **`tests/fixtures/`** — two copied files (§9); the copy commands are given verbatim.
5. **`tests/test_ui.py`** — seed + settings edits (§10a–c) so the new class has data; no existing
   assertion is disturbed (checked against every count-based test in the file: group counts,
   member lists, binding tiers, and nav tests key on selectors my markup does not emit —
   `data-cr`, `data-group`, `data-user`, `#f-state` — and my page introduces `data-login-user`
   precisely so the two drill vocabularies cannot collide).

Explicitly **not** touched: `gsd/loginlog.py` (read-only dependency), the chart and RBAC
(shipped), `/metrics` (nothing added — no username may reach the unauthenticated endpoint),
`poller.py`/leader election (A's area; the API is read-only and standby-safe by construction),
the browser-history machinery (used through `navigate()`, edited only in `backLabel` as §6).

## Tech debt: avoided, and accepted-with-reason

**Avoided**
- *KPIs computed from the page.* Every headline number comes from `summary`/watermark scalars;
  the page is only ever a page. This codebase has shipped that defect three times; not a fourth.
- *A client-side outcome filter.* Server-side, so a 2,000-row record does not cross the wire to
  show five expired passwords.
- *Reconstructing the ungoverned list from the attempts page.* Its own bounded store read over
  the same predicate as its count — a truncated chronology can be missing exactly those rows.
- *New CSS surface.* One token and one mapping line; every visual element reuses classes whose
  accessibility is already test-pinned. No chart (reasoned in Decisions).
- *A login metric.* `/metrics` is unauthenticated; the upstream count-only metric already exists.
  Nothing here goes near it.

**Accepted, with reason**
- *`LOGIN_OUTCOMES` hand-mirrored into index.html.* Cost of one self-contained file with no build
  step. Made safe by `test_the_ui_outcome_vocabulary_matches_the_parser` (a hard pin, not a
  convention) plus `outcomeBadge`'s degrade-to-identifier fallback at runtime.
- *`ungoverned` capped at 50 with no paging.* Bounded by distinct ungoverned accounts, which on a
  governed cluster should hover near zero; the uncapped count sits beside the list so the cap is
  visible. Paging machinery for a list designed to be empty is complexity ahead of evidence.
- *Break-glass detection by provider NAME from configuration.* The log carries only the name;
  knowing a provider's *type* means reading the OAuth CR, which is a new RBAC grant for a
  cosmetic label — rejected on the same proportionality grounds as the parser's refusal to do a
  second directory search. The default (`developer`, `htpasswd`) covers CRC and the common
  production naming; a wrong config degrades to an unlabelled row, never a hidden one.
- *`loginOutcome` not in the URL.* Consistent with every other filter (`POSITION_KEYS` carries
  positions, not controls); a shared link loses the filter but keeps the position, which is the
  documented trade for the whole page.
- *`user=` filter exposed on the API but not in the UI.* The UI's route to a person is the drill;
  the parameter exists for `curl`/scripting and for the tests. A second search box on the page was
  scope I chose not to spend.

## What I could not settle, and what would settle it

1. **The watermark shape** (`record_login_read` / `login_capture_status`). I defined the minimum
   the boundary display needs (`observed_since` = earliest window start, `last_read_at` = latest
   read). If A's reader tracks per-pod byte/time offsets differently, only the two reader methods
   and two tests need renaming — settled by A's Part-2 pieces 2–3 landing.
2. **Retention (Part 2.2 Q4) vs `observed_since`.** If A adds a prune like
   `dashboard_user_activity`'s, "Record begins {watermark}" becomes untrue for pruned spans — the
   honest value becomes `max(watermark, oldest surviving row)` *with different copy* ("retained
   since"). Settled by A's retention decision; the API centralises the computation in one place
   (`list_logins`) so the UI needs no change either way.
3. **Whether `authLogLevel` state should be surfaced on the page** ("capture on, but the operator
   is at Normal so nothing is being emitted"). The dashboard cannot read the authentication
   operator CR with its current RBAC; the honest proxy is `last_read_at` going stale while
   `enabled` is true. I chose not to invent a claim the app cannot verify — settled only by a
   deliberate future RBAC decision, which is out of my scope to propose.
4. **The chart value name for the provider list** (`loginCapture.htpasswdProviders`). The chart is
   shipped-and-reviewed territory; the value addition belongs with A's config plumbing and needs
   the operator's naming sign-off.

## Codex — additional findings

### Evidence ledger and limits

- I read this document and the complete committed implementations of `loginlog.py`, `store.py`,
  `storage.py`, `kube.py`, `poller.py`, `api.py`, and `static/index.html` before marking the design.
- Running the committed parser over the supplied files reproduced Part 1: `fixture.log` is 12
  lines/1,846 bytes and produced five attempts; `real.log` is 300 lines/73,371 bytes and produced
  the same five attempts. The records were `john.doe/success`, `jane.smith/bad_password/49`,
  `bob.wilson/rejected`, `nosuchuser/rejected`, and `developer/success`. Nothing I ran refuted
  Part 1.
- The scratch-SQLite dedup sequence and retention timings are recorded under Q2 and Q4. They used
  the proposed table and index definitions with WAL enabled, not an in-memory approximation.
- `helm template review charts/group-sync-dashboard --set ingress.host=review.example.test`
  succeeded, as did the render with capture enabled and a custom auth namespace. The latter
  rendered the Role/RoleBinding in that namespace. Before the proposed ConfigMap edit, neither
  render contained `loginCaptureEnabled` or `loginCaptureNamespace`. A render without the required
  ingress host failed at the chart's existing guard, as expected; no Helm mutation was run.
- The non-browser suite ran with the repository's Python 3.13 environment: **569 passed, 4
  skipped**. A full collection reached **790 passed, 5 skipped, 1 failed, 81 errors**: the one
  ordinary failure is `tests/test_docs_citations.py` rejecting this document's forward reference
  to the not-yet-implemented login handler; all 81 errors were sandbox failures to
  launch Chromium or bind the UI server. No product-code failure is inferred from those sandbox
  errors, and no browser pass is claimed.
- I attempted only the permitted read-only cluster commands: `oc whoami`, `oc auth can-i list
  pods`, `oc auth can-i get pods/log`, and `oc get pods`. This environment denied the connection
  to `127.0.0.1:6443` with “operation not permitted,” so I produced no new live-cluster evidence
  and made no cluster change. Part 1's measured cluster facts therefore remain given.

### A/B build-time seam reconciliation

The designers do not currently agree where they must. These are compile/runtime contract breaks,
not naming preferences:

| Concern | Designer A | Designer B | Required resolution |
|---|---|---|---|
| Insert method | `record_login_events(cluster_id, events: list[dict])` | `record_login_attempts(cluster_id, attempts: list[LoginAttempt])` | Keep pod identity and choose one name/input type. A's dict also carries `pod_name` and `observed_at`, which B's parser object cannot supply alone. |
| Replay state write | `set_login_watermark(cluster_id, pod_name, settled_through)` | `record_login_read(cluster_id, pod_name, started_at, read_at)` | These timestamps have different meanings. Preserve per-pod `settled_through`; add stable cluster start/last-success state rather than overloading it. |
| Replay state read | `login_watermarks(cluster_id) -> dict[pod_name, settled_through]` | `login_capture_status(cluster_id) -> {observed_since,last_read_at}` | Both are needed for different jobs; B's status cannot be derived reliably from pruned A rows. |
| Event read | `login_events(cluster_id, user_name=None, outcome=None, since=None, limit=200)` | `login_attempts(cluster_id, *, user_name=None, outcome=None, limit=200)` | Select one name/signature. B additionally requires `full_name` and booleans describing current membership/detail availability; A returns `pod_name` and `observed_at` instead. |
| Summary read | `login_event_summary(cluster_id, user_name=None, since=None)` returning `attempts`, `distinct_users`, `successes`, `failures`, `first_at`, `last_at` | `login_summary(cluster_id, exclude_providers=())` returning `total`, `by_outcome`, `distinct_users`, `ungoverned_users`, `first_at`, `last_at` | Implement the endpoint's whole-set aggregates in Store with one agreed result shape and the same ungoverned predicate as its rows. |
| Ungoverned rows | No A method | `ungoverned_login_users(cluster_id, exclude_providers=(), limit=50)` | Add a Store/Protocol query; do not reconstruct it from the 200-row event page. Return detail availability separately from current membership. |
| Pruning | `prune_login_watermarks`, `prune_login_events` | No corresponding assumption; UI assumes stable history boundary | Keep dead-pod cleanup, bound event pruning, and expose `capture_started_at` separately from `retained_since`. |
| Event unique key | `(cluster_id,pod_name,user_name,at,outcome)` | `(cluster_id,user_name,at,outcome)` | Use A's pod-inclusive key; B's key drops the named cross-replica same-instant pair. |
| Event timestamp | Fixed UTC microseconds | Fixed UTC microseconds | Agreement: keep `%Y-%m-%dT%H:%M:%S.%fZ`. |
| Other timestamps | A's `settled_through` is microseconds; `observed_at`/watermark `updated_at` use `now_iso()` second precision | `started_at`/`read_at` are second-precision UTC | Precision itself is harmless, but names and semantics must not be interchanged. Document each field. |
| Settings | `login_capture_enabled`, `login_capture_namespace`, `login_capture_retention_days` | `login_capture_enabled`, `login_capture_htpasswd_providers` | Enabled is the only agreement. Decide whether provider names and retention are operator inputs, then wire every retained field through Settings and the existing ConfigMap path. |
| Protocol | Declares A's seven methods | Says B's six methods are declared | Declare exactly the final Store surface. Otherwise `StorageBackend` conformance and the seam test fail. |

The minimal coherent surface is A's pod-keyed event/replay writer plus Store queries that directly
produce B's endpoint contract. Do not discard pod identity at the API-test seed boundary. Capture
status is distinct state: `capture_started_at` is set on the first successful log read and never
rewritten; `last_read_at` advances on successful reads; `retained_since` is the oldest surviving
event (or null). That makes restart, dead-pod pruning, and 400-day retention truthful without a new
database or framework.

### Part 2.1 invariant audit

Counting the compound UI bullet as its three independently tested rules gives the eleven invariants
named by the task:

1. **StorageBackend/SQL seam — violated by the combined A/B text.** A's implementation and
   Protocol agree with each other and the new module is added to the scanner, but B calls six
   undeclared, unimplemented methods. The design cannot merge verbatim.
2. **Numbered/idempotent migration shape — implementation complies; test is inadequate.** Migration
   5 and `SCHEMA` match, but the proposed test lets current `SCHEMA` create the tables before it
   assesses the migration itself.
3. **No foreign keys — complies.** Neither proposed table declares one.
4. **Ambient write discipline — complies**, subject to bounding the prune. Store writes use
   `_write()` and no proposed SQL appears in kube, poller, API, or UI.
5. **One store call or `@consistent` per multi-call handler — complies.** B uses `@consistent`.
6. **No cluster call, await, or yield in a read snapshot — complies.** The synchronous handler does
   Store reads and Python shaping only.
7. **No literal CSS `font-size` — complies.** New UI sizing uses existing classes/tokens.
8. **Both-theme colour contrast — complies.** The independently measured ratios pass.
9. **Display-timezone source slices — complies.** The proposed insertions are outside the protected
   source gaps.
10. **No username in unauthenticated metrics — complies.** No metric or skipped-auth mutation is
    added. This does not resolve the separate authenticated/delegated API authorization issue.
11. **Leader-only writes — violated.** Admission works for a process already in standby, but the
    mid-read loss sequence can write after lease loss. The proposed standby test does not enforce
    the stated invariant. A pre-transaction recheck is the minimal mitigation available in the
    current best-effort lease design; it must be tested explicitly.

Thus the actual Part 2.1 merge blockers are leader-only writes and the unresolved storage seam.
The migration test should also be repaired before relying on it, even though the proposed migration
SQL itself follows the invariant.

### Production findings not fully owned by either design

1. **Authorization is a release decision, not inherited safely.** The default UI policy is merely
   “authenticated,” and the direct API delegation example is keyed to listing clusterrolebindings
   (`values.yaml#ACCESS MODEL for the UI` and
   `values.yaml#THE REVIEW MUST MATCH WHAT /api EXPOSES.`). The new endpoint reveals attempted
   usernames, provider names, and failure reasons originally obtained through `pods/log`; those
   existing permissions are not equivalent. Use the chart's existing SAR/auth mechanisms to gate
   deployments that enable login capture, and ensure the direct-token path cannot bypass that
   decision. This needs no new framework, chart subsystem, or RBAC redesign, but it must be stated
   and tested before exposing the route.
2. **A successful HTTP log read is not necessarily a useful capture read.** A normal rolling pod
   can return 400/404 and should be retried without advancing state. A 403, unexpected 400, or
   repeated container-selection error must remain observable; returning the same `None` for all of
   them makes “no logins” indistinguishable from “capture has been broken for weeks.” Record
   `last_read_at` only after a successful response and emit rate-limited warning/info evidence for
   persistent failures.
3. **The most valuable historical account can be both ungoverned and drillable.** Existing
   `api.py#user_detail` returns history even without a current group. The endpoint row
   needs separate facts for “currently in a synced group” and “has dashboard membership history.”
   The first drives the ungoverned card; the second drives the drill button.
4. **The response needs a real byte bound.** `_get()` must not be used for logs because it forces
   JSON, but `_client()` can and should be reused for credentials/TLS. Stream the direct text
   response and abort at a documented byte ceiling while preserving the tail-line warning. A line
   cap alone cannot justify the design's bounded-memory claim.
5. **The first-read quarantine can drop more than one attempt.** On a capped first read the proposed
   strict lower bound removes every parsed start in the first `ATTEMPT_WINDOW`, not “at most one.”
   The scratch sequence at +100, +400, +900, and +1100 ms retained only +1100 ms. The quarantine is
   still safer than parsing a cut head as a false outcome, but the loss must be logged honestly and
   the test must include concurrent starts; do not size or describe it as a single-row loss.

### Application order

1. **Settle and pin the contract first:** accept A's pod-inclusive key; define the final Store and
   `StorageBackend` signatures/row shapes; define stable capture status versus retained history;
   decide the existing authorization gate and final Settings fields. Update the design tests to
   name that one contract.
2. **Land storage before consumers:** schema plus migration 5, isolated migration test, Store
   event/replay/status/query methods, bounded pruning, and matching Protocol declarations. The
   store/query layer must land before B's endpoint or either designer's seed tests.
3. **Land the reader and capture mechanics:** text-stream byte bound, expected roll-error
   classification, visible 403/unexpected 400 behavior, per-pod horizon/overlap logic, and tests for
   first sight, persisted restart, split attempts, overlap, and the cross-replica same-instant pair.
4. **Integrate with poller/config/chart:** add the module to both seam scanners; wire only the final
   Settings through the ConfigMap; call capture behind leader admission and recheck leadership
   immediately before its write transaction. The flip-during-read test must land with this step.
5. **Land the API and documentation:** implement the reconciled Store calls under `@consistent`,
   enforce the chosen existing authorization policy, then add the route and API.md together. This
   ordering also makes the existing docs-citation forward reference valid.
6. **Land the UI and browser tests last:** add the tab, truthful capture/retention copy,
   ungoverned card, history-aware drill behavior, filters, and browser coverage against the final
   response. UI hierarchy must not be used to paper over missing server-side whole-set aggregates.
7. **Run the complete merge gates and renders:** all pytest suites including Playwright in an
   environment allowed to launch Chromium/bind localhost, the docs-citation and seam tests, default
   and enabled/custom-namespace Helm renders, plus a permitted read-only cluster smoke check. No
   implementation piece should claim completion until this final environment-backed pass is green.

---

# Addendum — the read seams, 2026-08-08

Four defects were found in the seams between `parse`, the capture window and the store's UNIQUE key,
after this design shipped. All four produced the same shape: **one login becoming two stored rows, one
of them stating something false about a named person.** Full detail, with the reviewer's own text and
the arbitration, is in `REVIEW_login_capture_seams.md`.

| seam | was | now |
|---|---|---|
| trailing edge of the read | guarded by `_recordable` | unchanged |
| leading edge of the read | **unguarded** — a window opening mid-attempt re-recorded it worse-informed | `_not_clipped`, plus a 20s wall-clock budget on the fetch, because the guard's overshoot equals the read's latency |
| the byte cap | keeps the oldest lines and defers the rest | unchanged, and now also the landing path for a read that outruns its budget |
| `parse`'s own expiry | measured age since the attempt's FIRST line, so anything spanning >1s concluded mid-flight | measures **silence since the last line** |
| `adopt` | took the first orphan in list order | evidence outranks adjacency; adjacency applies only to a lone unidentified cause; never into a success |
| `found` | one entry per DN, so two logins behind one AD entry traded sub-codes | a list per DN, and an ambiguous DN is dropped rather than guessed |

**Still open, and the reason this addendum exists rather than a claim of completeness.** The expiry fix
closes the case where the intervening lines are verdicts or causes — three providers 600ms apart went
from two rows to one. It does not close the measured production shape, because `last_at` advances only
on verdict and cause lines:

```
htpasswd failed 12:00:00.0 -> searching .4 -> found dn= .8 -> identitymapper 1.2 -> succeeded 1.6
  => still 2 rows: (jane.smith, failed, 12:00:00) and (jane.smith, success, 12:00:01.6)
```

Closing it means advancing `last_at` from progress lines that name a pending login — the `searching`
filter and the `found dn=` line both embed it. That is new design in the most delicate function in the
module, and it is deliberately not taken alongside a set of fixes.
