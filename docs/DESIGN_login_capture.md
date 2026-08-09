# Login capture — as built

Who logged in, when, from which provider, and why an attempt failed — accumulated from the
oauth-server's own pod logs.

**Status: shipped.** The parser, capture loop, storage, API and Logins tab are live. This document
describes what exists and the measurements behind it. Where a decision looks arbitrary, the reason is
here; where something is deliberately *not* done, that is here too, because most of it will be
proposed again.

Every measurement was taken on a live cluster and is dated. Nothing here is inferred.

## The shape of it

| piece | file | what it does |
|---|---|---|
| parser | `gsd/loginlog.py#parse` | log lines → `LoginAttempt` records. Knows nothing about clusters or storage, which is what makes it testable without either |
| capture loop | `gsd/logincapture.py#capture_once` | reads each oauth-server pod incrementally, decides what is settled enough to record, advances a per-pod cursor |
| log reader | `gsd/kube.py#ClusterClient.fetch_pod_log` | streamed, byte-bounded and wall-clock-bounded read of one pod's log |
| storage | `gsd/store.py` | `login_event`, `login_capture_watermark`, `login_capture_status` |
| API | `gsd/api.py` | `/api/clusters/{id}/logins`, `/api/clusters/{id}/cluster-access` |
| UI | `gsd/static/index.html` | the Logins tab and the cluster-access panel |

The constants that govern the loop, and why they are what they are:

| constant | value | reason |
|---|---|---|
| `gsd/loginlog.py#ATTEMPT_WINDOW` | 1s | how long one attempt may go **quiet** before it is concluded. Measured attempts span 30–125 ms, so this is roughly 8× the widest — thinner than it sounds, because a directory under load stretches an attempt without changing anything else about it |
| `gsd/logincapture.py#OVERLAP_SECONDS` | 60 | how far behind the cursor each read starts again. Must exceed 2×`ATTEMPT_WINDOW` for parse context (below) |
| `gsd/logincapture.py#SETTLE_SECONDS` | 30 | how far behind the log's tip an attempt must be before it is recorded |
| `gsd/logincapture.py#FIRST_SIGHT_SECONDS` | 3600 | how far back a first read goes for a pod with no cursor |
| `gsd/kube.py#LOG_READ_BUDGET_SECONDS` | 20 | wall-clock bound on one pod-log read |

The prerequisite is `authLogLevel`, which raises `spec.logLevel` on the authentication **operator** CR
so the oauth-server names the person logging in, plus `loginCapture`, which grants a namespaced read
of those pod logs. With capture on and Debug off this reads real logs and finds nothing — correct
rather than broken.

---

# The log, measured

## 1. The line, and where the timestamp comes from

```
2026-08-07T16:56:28.267663898Z I0807 16:56:28.267 1 basicauth.go:51] Login with provider "ldap-local" succeeded for login "john.doe"
└──────────── kubelet, RFC3339 UTC ───────────┘ └── klog: no year, no zone ──┘
```

Two stamps, one usable. The kubelet prefix appears because the reader passes `?timestamps=true`;
klog's own carries **no year and no timezone**, so it cannot be resolved to an instant without
guessing both. The kubelet stamp is stored as UTC and rendered with the container's `TZ` from
`values.timezone`, which `/api/version` also reports. Verified: `16:56:28Z` displays as
`12:56:28 EDT`.

## 2. One attempt is several lines, across two files

| case | lines, in order |
|---|---|
| LDAP success | `basicauth.go:48` failed `"developer"` → `ldap.go:131` searching → `ldap.go:148` found dn= → `basicauth.go:51` **succeeded** `"ldap-local"` |
| LDAP wrong password | … → `ldap.go:148` found dn= → `ldap.go:152` **error binding password … Result Code 49** → `basicauth.go:48` failed |
| LDAP rejected | … → `ldap.go:139` **no entries matching** → `basicauth.go:48` failed |
| unknown user | **identical to rejected** |
| HTPasswd success | `basicauth.go:51` **succeeded** `"developer"` — and nothing else |

Three rules follow, and none is visible from a successful login alone:

1. **A `failed` line is not a failed login.** Every provider tried before the matching one logs one,
   so a *successful* LDAP login contains `failed for login "john.doe"`. Outcome is a property of the
   group of lines for one username in one window, never of a line.
2. **An HTPasswd login logs no failure at all** — it matches the first provider. The shape per attempt
   is provider-**order** dependent, so no fixed shape can be assumed.
3. **The provider name separates people from break-glass accounts.** `ldap-local` is a directory
   identity; `developer`/`kubeadmin` on a success are HTPasswd.

There are also **two verdict grammars**. `basicauth.go` (the CLI path) writes `for login "<user>"`;
`login.go` (the browser form) writes `for "<user>"`. The parser accepts both, and the verdict pattern
is **anchored** at the start of the klog message — unanchored, a verdict phrase quoted inside another
klog message fabricates a login that never happened.

## 3. Code 49 is not a cause — the diagnostic message is

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
password with `53 unwillingToPerform`, not 49** — so 49 cannot be treated as "all password failures"
on either directory. `50` insufficient-access → `logon_not_permitted`; `19` constraintViolation →
`must_change_password`.

An **unmapped** sub-code becomes `failed` with the code in `detail`, so a grammar gap is visible
rather than silently mislabelled.

## 4. What the log cannot tell you

**Gate-denied and unknown-user are byte-identical.** Both emit only `no entries matching (<filter>)`,
because the identity provider's filter carries the login-gate group. Separating them needs a second
directory search *without* the gate clause — an LDAP read this application does not have and should
not acquire. One honest bucket: **`rejected` — not found or not permitted**. Both are still captured
against the attempted username.

## 5. Attribution: a cause line names nobody

This is the hardest part of the parser and the source of most of its defects.

A cause line (`error binding password for "<dn>"`, `no entries matching (<filter>)`) carries no
username. On a cluster whose **only** provider is LDAP — the ordinary production shape — the attempt
*starts* with `ldap.go:131 searching`, so no username exists yet when the cause arrives. This lab only
avoids that because htpasswd is tried first and logs a failure, creating the entry. Before it was
fixed, **every cause was dropped on a single-provider cluster, including every expired password.**

What the parser does now, in order of preference:

1. **Identity.** Attach a cause only when the evidence names exactly one pending login. The evidence
   is the cause's own text plus the `found dn=` line that resolved its bind DN.
2. **Adjacency, narrowly.** When nothing is named and exactly one unidentified cause is waiting and
   exactly one attempt is in flight, attach it. With **two** unidentified causes waiting, arrival
   order is the only tiebreak left and it is exactly wrong when the directory answers out of order —
   measured as two strangers' bind codes swapped, an expired password recorded as somebody else's
   wrong one. Both degrade to the provider's own verdict instead.
3. **Otherwise hold or drop.** A cause naming two in-flight logins has no honest owner; dropping it
   degrades both to the provider's verdict, which is true, where guessing makes one of them false.

Two details that look incidental and are not:

**`found dn=` is why AD works at all.** The line reads `found dn="<dn>" for (<filter>)`, and the
*filter* embeds the typed login on every directory (`(uid=jane.smith)` on OpenLDAP,
`(sAMAccountName=jsmith)` on AD) while the DN does so only where entries are named by login attribute.
On AD the DN is `CN=Jane Smith,OU=…` and the login is `jsmith` — they never match. A rule requiring
the cause itself to name the user would have silently discarded every AD cause.

**A success never borrows a cause.** A bind failure cannot explain a login that succeeded, so
`gsd/loginlog.py#adopt` refuses to hand an unidentified cause to a succeeding verdict, and `gsd/loginlog.py#conclude` suppresses any
cause a success acquired by another route. Measured before that guard: `jane.smith / success` carrying
`ldap_result_code=49` and `detail="LDAP result code 49"` — three false claims on the row a reader
trusts most, about somebody who typed the right password.

---

# The read seams

Everything above turns log text into attempts. This turns a *live, growing* log into a durable record,
and it is where the subtle defects live: every boundary that can slice a log produces the same shape
of bug — **one login stored as two rows, one of them false** — because an attempt's `at` depends on
which lines the read returned, and both `at` and `outcome` are in the store's unique key.

## The cursor is per pod, in the database, with overlap

**Per pod is required, not optional.** Two or three replicas serve different attempts and their logs
advance independently. One cluster-wide cursor has only two aggregations, both wrong: `max` jumps
ahead on the fastest pod and permanently skips lines on any pod that missed a cycle (Terminating
during one read, back the next); `min` never advances past the slowest pod, and a pod that dies pins it
forever, growing every other pod's re-read window without bound.

**In the database** so a restart resumes with a bounded `sinceSeconds` instead of choosing between
re-reading from the beginning (unbounded) and a tail-only read that loses the restart window. The
store is the only place with the same lifetime as the events the cursor guards. It is also correct
under the multi-replica shape, because above one replica each pod has its own database *and* leader
election is off (a chart guard enforces this), so cursors never cross a writer boundary.

**Overlap on top.** Each read starts `OVERLAP_SECONDS` (60) *before* the cursor, for two reasons.
The obvious one: `sinceSeconds` is judged by the kubelet against the node's clock while our
`now - watermark` arithmetic uses ours, and the overlap absorbs the skew. The subtle one is **parse
context** — a cause can be adopted by a verdict up to `ATTEMPT_WINDOW` later, so an attempt near the
cursor re-parses identically only if the window also contains the *full attempt before it*. Overlap ≥
2×`ATTEMPT_WINDOW` guarantees every attempt in the persisted band arrives whole, with its whole
predecessor. 60s ≫ 2s, and the price — re-parsing a minute of lines — dies on the dedup key.

## The watermark and the status are two different things

`login_capture_watermark` is a **replay cursor**, per pod, and it is pruned when a pod disappears —
every oauth roll replaces them, so without pruning the table grows by one row per pod name the cluster
has ever had.

`login_capture_status` is a **liveness record**, per cluster, and it holds two values the cursor
cannot: a stable `started_at` (what "watching since" on the Logins tab means) and `last_read_at`. It
must survive pod pruning, which is exactly why it is not derived from the watermarks. The upsert
deliberately does **not** touch `started_at`, and `gsd/store.py#Store.set_login_watermark` takes `max()` so a late write
from a demoted leader cannot rewind it.

## Four guards, one per boundary

| boundary | what goes wrong unguarded | guard |
|---|---|---|
| trailing edge (lines not written yet) | an attempt read mid-flight concludes on partial evidence — the provider-chain `failed` is present, the success that follows is not — and the honest-but-wrong `failed` row sits beside the real one forever | `gsd/logincapture.py#_recordable`: withhold attempts younger than `SETTLE_SECONDS` + `ATTEMPT_WINDOW` |
| leading edge (lines behind the window) | a window opening between a bind error and its verdict parses the verdict alone, so a login already stored as `bad_password` at the cause is stored *again* as `failed` at the verdict | `gsd/logincapture.py#_not_clipped`: drop attempts within `ATTEMPT_WINDOW` of the window's start |
| the byte cap | an attempt straddling the cap byte is parsed half and recorded, then recorded again whole next cycle | keep the **oldest** lines, drop the half line, defer the rest |
| `parse`'s own expiry | an attempt whose lines span more than a second concluded mid-flight, fabricating a `failed` beside a real `success` | measure **silence since the last line**, not age since the first |

Two of those deserve their reasoning spelled out, because both are counter-intuitive.

**A cap hit keeps the OLDEST lines, deliberately.** The kubelet streams oldest first, and oldest-first
is the direction the cursor machinery *requires*: the cursor only advances through lines actually
returned, so the deferred newest lines fall inside the next cycle's window and nothing is lost — only
late. Keeping the newest instead would let the cursor advance past everything the cap displaced and
drop it forever. Recency is what the next cycle gets back anyway; completeness is not.

**The read is bounded in wall-clock time as well as bytes.** The httpx timeout caps the gap *between
chunks*, not the transfer — measured: a 4.17 s dribble completed through a `timeout=1.0` client
without raising. The leading-edge guard derives its window from a clock stamped *after* the read
returns, so every second spent reading widens the band of attempts that guard discards. Past ~58.5 s
of read latency it discards rows no cycle ever recorded, which is why `LOG_READ_BUDGET_SECONDS`
exists; a read it interrupts lands on the truncation path, which defers rather than loses.

## Still open

The expiry fix closes chains whose intervening lines are verdicts or causes — three providers 600 ms
apart went from two rows to one. It does **not** close the measured production shape, because
`last_at` advances only on verdict and cause lines; the progress lines never touch a pending attempt:

```
htpasswd failed 12:00:00.0 → searching .4 → found dn= .8 → identitymapper 1.2 → succeeded 1.6
  ⇒ still 2 rows: (jane.smith, failed, 12:00:00) and (jane.smith, success, 12:00:01.6)
```

Closing it means advancing `last_at` from progress lines that name a pending login — the `searching`
filter and the `found dn=` line both embed it. That is new design in the most delicate function in the
module, deliberately not bundled with a set of fixes. Full detail of the four defects and their
arbitration is in `REVIEW_login_capture_seams.md`.

---

# Deliberately not done

## Not recorded

- **The raw line.** `ldap.go` embeds the full bind filter and the user's DN, which disclose the gate
  group's DN and the directory's layout — more sensitive than the username the row is keyed on.
- **Any invented timestamp.** A line without the kubelet prefix is skipped rather than guessed at.
- **Anything in `/metrics`.** It is unauthenticated by design, so no username may become a label.
  `openshift_auth_basic_password_count_result` already gives count-only success/error with no
  usernames, and is the right shape for a metric.

## Accepted limitation: the past cannot be reconstructed

**Logs die with the pod, and nothing before Debug was enabled exists.** Every oauth roll — cluster
upgrade, node drain, or a toggle of this very setting — starts the window again. The reader accumulates
a durable record *going forward*; the past is not recoverable. This is inherent to the source, not a
problem to be solved, and `login_capture_status.started_at` exists so the UI can say when watching
began rather than letting an empty table read as "nobody logged in".

## The oauth-server AUDIT LOG — a better source, not used

Found after the design was written, measured on the live cluster, and **parked rather than adopted**.
It is recorded here because it is a better source in most respects and somebody will find it again; the
reason it was not chosen is a security trade-off, not an oversight.

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

Where it is better:

| | pod logs (chosen) | audit log |
|---|---|---|
| needs `logLevel: Debug` | **yes** — a cluster-wide write, and a login outage on every toggle at one replica | **no** |
| format | klog text; provider-order noise; multi-line attempts | structured JSON, **one event per attempt** |
| outcome | inferred by correlating several lines per username | explicit `allow` / `deny` annotation |
| history | dies with the pod; nothing before Debug was enabled | **~16 months here** — 187 of 201 username events predate Debug, earliest 2025-04-19 |

That fourth row largely dissolves the accepted limitation above, which is the chosen design's real
weakness.

**Why it was not chosen.** `oc adm node-logs` is `GET /api/v1/nodes/<node>/proxy/logs/<path>`, so it
needs **`nodes/proxy`** — and that path reads *any* file in the node's log directory. Verified
reachable through the same grant: `kube-apiserver/` audit logs (every API request on the cluster) and
the kubelet journal. That is categorically wider than `pods/log` in one namespace, and unlike the Debug
toggle it is a **standing** capability rather than a one-off write. For an application whose defining
invariant is that it reads narrowly and writes nothing, that is the wrong trade.

**It also carries no cause.** `allow`/`deny` only. The `password_expired`, `account_locked`,
`must_change_password` and wrong-password distinctions exist only in the pod log's LDAP result codes
and AD sub-codes. So the two sources are **complementary, not substitutes**.

**If it is ever revisited**, the dedup key changes: `pod_name` is pod-log-specific, while an audit
event carries `auditID`, unique per request, which makes deduplication trivial and removes the
cross-replica same-instant reasoning entirely. The parser gains a second front end rather than a
rewrite. The most likely shape is **both** — the audit log as the authoritative who/when/allow-deny
with real history, and the pod log consulted for the LDAP cause when Debug happens to be on.

## Reading the logs: the RBAC shape, and why it stays narrow

- **`pods` list + `pods/log` get, both namespaced.** There is no Deployment log subresource — verified,
  `GET .../deployments/oauth-openshift/log` returns *"could not find the requested resource"*.
  `oc logs deploy/x` only looks combined; the client resolves to pods. Production runs 2–3 replicas
  and every roll replaces them, so discovery is not optional.
- **`pods/log` in a ClusterRole reads every pod on the cluster** — tokens, connection strings,
  customer data. It stays a `Role` in `openshift-authentication`.
- **`sinceSeconds` works** on the log endpoint, which is what makes reads incremental.

Also rejected, and likely to be proposed again: **reading LDAP directly** to tell a gate-denial from an
unknown user. It would put a bind credential and a CA into a component that today holds only its own
ServiceAccount token.

---

The pre-implementation design record — two parallel designers, their full code proposals, and the
review passes over them — is in this file's git history. It is not reproduced here because the code it
proposed has since been superseded in three places by the seam fixes above, and a proposal that no
longer matches the shipped parser is worse than no proposal at all.
