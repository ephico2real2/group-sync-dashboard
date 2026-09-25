# SPEC S4c — the credential lifecycle: the daily ping, `self-login` renewal, and the per-credential gate that survives a restart and a second replica (#285)

| | |
|---|---|
| Programme | Cluster configuration as labelled Secrets (#230), continued — S4 designed the retrieval; S4a shipped the login; S4b shipped the lookup; this is step C, the only part that runs on a clock |
| Batch | S — cluster configuration |
| Release | — (post-programme; S4 step C, the issue's own label S3b-C) |
| Version on release | app 0.34.0, chart 0.55.0 |
| Issue | [#285](https://github.com/ephico2real2/group-sync-dashboard/issues/285) |
| Status | specified |
| Source | OB1's design specification of 2026-09-22, written before any code from the business owner's brief, the issue and its eight comments (the fixed-margin correction, the 401 ambiguity, the retraction on the one-year fuse, the inherited replica requirement), `docs/specs/SPEC_S4_token_retrieval.md` §3.1, §6 and §9, `docs/specs/SPEC_S4b_sa_token_lookup.md` (orchestrator's notes R2-5 and R3-2, §6), the review record `docs/REVIEW_S4b.md` ("What is NOT held"), the upstream sources cited in §2, and the reference cluster measured read-only on 2026-09-22 |

## How to read this spec

"Measured" is what the reference cluster or an upstream source answered, with the command. "Design"
is the mechanism, stated to the level a reviewer can attack it — the object shapes, the signatures,
the state machine, the exact log fields and values keys — and every non-obvious decision carries the
citation or the measurement it rests on. **Every safety claim is written as a budget with its scope**
("at most N per (key) per process / per replica / across restarts"), never "ever": the review of
#295 measured that a per-call guarantee is unfalsifiable at the scale that matters and an unscoped one
is false (`docs/REVIEW_S4b.md`, "What is NOT held"). Where a fact could not be measured it is labelled
as such in §5 with what would settle it, and nothing there is filled with an estimate.

**The constraint that overrides everything in this document:** the fleet account is the LDAP account
the reference cluster authenticates *every* user with. Nothing in this spec, its tests or its
verification logs in as it, with a correct password or a wrong one. Every live proof below uses the
htpasswd `developer` account, which no directory sits behind (SPEC_S4a, orchestrator's notes; SPEC_S4b,
"the live check logs in as the htpasswd `developer`"). Whether the fleet account works is answered by
reading — `oc get user`, the recorded measurements — never by trying.

## Orchestrator's notes

Decisions taken at review, recorded first and then applied:

- **The gate is per ACCOUNT for every bound failure** (review of #325, 2026-09-23: Codex, Grok and OB1-lite;
  the operator's ruling). All three reviewers refuted the draft's B2: its gate was one entry per target,
  so T clusters on one fleet account could present one wrong password T times, and a lockout is per
  directory account (#315). Grok and OB1-lite proposed splitting by outcome — a 401 per account, a 500
  per target, keeping R2-1 ("a 500 from target A must not stop a healthy target B"). Codex proposed every
  bound failure per account, because a locked account's 500 (LDAP code 19) cannot be told from a sick
  target's 500, so the per-target half still walks an already-locked account T times. **The operator chose
  Codex's rule, reversing R2-1**: a lockout of the account everyone logs in with is the worse outage; the
  price is that one sick target's 500 stops binds on every target of the account until the password
  rotates or the entry is cleared (§5, question 7). §3.4's ping already stood down on either kind for the
  same reason; every other path now does too.
- **The release versions** are app 0.32.0, chart 0.53.0 (all three reviewers): the draft's chart 0.51.0
  had already shipped (#307), and main is at 0.52.1 (#317). SPEC_D2b's implementation (#338) took those two
  rungs first, then SPEC_U1 (#353) took app 0.33.0 and chart 0.54.0, so this spec now carries app 0.34.0, chart 0.55.0.

## 0. The requirement, in business terms

The estate has **one LDAP account** that connects every cluster. Three things can go wrong with it
quietly, and each is found today at the worst moment — the next onboarding, or when a cluster stops
polling:

1. **The account stops working** (a rotated or expired password, a revoked grant on the target, a
   deleted ServiceAccount or token Secret) and nobody knows until a new cluster fails to connect.
   *Prevented by* the **daily ping**: one real login-and-read a day, per account, reported as an
   absolute instant — `fleet_account_last_ok` — so the tab can say how long it has been failing.
2. **A `self-login` cluster's session dies** on the target's own clock and that cluster stops polling.
   *Prevented by* **renewal a fixed margin before expiry**, on the lifetime the target itself stated.
3. **A wrong password starts the lockout walk** — one bind per cluster per cycle, per replica, again
   after every restart — and locks the account every cluster shares, converting one broken stanza into
   an estate where nobody can log in. *Prevented by* a **per-credential gate that is durable and
   replica-shared**: a failed bind is presented **once per account** — one bind for the whole estate,
   however many clusters share the account — and neither a restart nor a second pod sends it again.

The blast-radius asymmetry that decides every choice below (SPEC_S4a §3.1): *a wrong retry is an
estate-wide outage against the account the target authenticates every user with; a missed retry is
one delayed login the next ping or cycle picks up.* Wherever this spec could bind once more or once
less, it binds less.

## 1. What is NOT in scope

- **Sweeping pre-existing litter** — the two `openshift-challenging-client` tokens the fleet account
  already has on the lab from 2026-09-19 (§2) predate #283 and are #286's. Everything this spec
  mints is revoked by the session that minted it (`gsd/fleetlogin.py#FleetLogin.__exit__`).
- **The tab's provenance wording** — S3c. This spec adds the two rows the Definition of Done needs
  (the account's last confirmed instant; a `self-login` credential's expiry) and nothing else.
- **TokenRequest minting** (#238) and the rotation of a stored `remote-lookup` token: the credential
  #284 stores is the target's permanent token and has no clock (SPEC_S3 §8.3, measured: no `exp`).
- **Reading `oauth/cluster`.** The session is self-describing (`expires_in`); SPEC_S4 §3.1 forbids a
  grant for it, and the inactivity timeout is handled reactively (§3.6). Confirmed unnecessary by the
  measurement in §2: `accessTokenInactivityTimeout` is unset on the lab and the OAuth client's own
  fields are null.
- **Cross-pod session sharing for `self-login`.** A session is per process by design ("nothing
  durable at rest" is the mode's whole point, SPEC_S4 §5); above one replica the mode is refused at
  render (§3.8) rather than the sessions replicated.
- **A SQLite migration.** Read in full (`gsd/store.py#_MIGRATIONS`, `gsd/store.py#_migrate`, and
  what `ALTER TABLE ADD COLUMN` cannot do) and found unnecessary: the one place that is shared by
  replicas *and* survives restarts in every install is the namespace, not the pod's database file
  (§2, "the store is per pod"). Durable state lives on one Kubernetes object; the store gets no new
  table. The migration number stays at 19.

## 2. Measured, and what each measurement decides

Lab: OpenShift 4.22.7 (Kubernetes v1.35.6), `oc` 4.22.13, `KUBECONFIG` = the read-only client-cert
kubeconfig, 2026-09-22. **Every command below is a read.** No login, no apply, no patch.

### 2.1 The session lifetime, and the second clock

```
$ oc get oauth.config.openshift.io cluster -o jsonpath='{.spec.tokenConfig}'
{"accessTokenMaxAgeSeconds":31536000}

$ oc get oauthclient openshift-challenging-client -o json | jq -c '{accessTokenMaxAgeSeconds, accessTokenInactivityTimeoutSeconds, grantMethod, respondWithChallenges}'
{"accessTokenMaxAgeSeconds":null,"accessTokenInactivityTimeoutSeconds":null,"grantMethod":"auto","respondWithChallenges":true}

$ oc get oauthaccesstokens -o json | jq -r '.items[] | select(.userName=="ocp-oauth-bind-serviceid") | "\(.clientName) expiresIn=\(.expiresIn) inactivityTimeoutSeconds=\(.inactivityTimeoutSeconds // "absent") created=\(.metadata.creationTimestamp)"'
openshift-challenging-client expiresIn=31536000 inactivityTimeoutSeconds=absent created=2026-09-19T00:50:11Z
openshift-challenging-client expiresIn=31536000 inactivityTimeoutSeconds=absent created=2026-09-19T00:48:44Z
```

**Decides:** the lab states a one-year lifetime and **no inactivity timeout** at either level (the
CR's or the client's — the docs say the client's overrides the server's: *"If the token inactivity
timeout is also configured in your OAuth client, that value overrides the timeout that is set in the
internal OAuth server configuration"*, and *"The minimum allowed timeout value in seconds is 300"*,
OCP 4.16 *Configuring the internal OAuth server*). So the lab cannot show an inactivity expiry, and
this spec handles it reactively (§3.6) rather than by reading either object. The two token objects
are the ones SPEC_S4 §10.1 already counted on 2026-09-19 — nothing from #284's lookup on 2026-09-22
survived, which is the session's revoke working. This is the read-only answer to "does the fleet
account work": `oc get user ocp-oauth-bind-serviceid` → `created=2026-09-19T00:48:44Z`, an Identity
`ldap-local:…` — the object exists only after a successful login (SPEC_S4 §10.1).

### 2.2 What the margin computes to

SPEC_S4 §3.1 — the binding text, per the business owner's correction on the issue (2026-09-21) — is a
fixed margin, not a percentage: `renew_at = expires_at − min(2 h, ¼ × lifetime)`. The issue's own
"80 %" and its "48 minutes" are superseded, and the arithmetic below is the rule that stands:

| `expires_in` | where | margin | `renew_at` | the window to fail, back off and still renew |
|---|---|---|---|---|
| 3 600 s (1 h) | an estate that tightens it | 900 s | **45 min** after login | 15 min |
| 86 400 s (24 h) | OpenShift's documented default | 7 200 s | 22 h after login | 2 h |
| 31 536 000 s (365 d) | **the reference cluster** | 7 200 s | 364 d 22 h after login | 2 h |

**What the window buys, in this code's own numbers.** One login attempt (`gsd/fleetlogin.py#RETRY_POLICY`:
five attempts, waits 1 + 2 + 4 + 8 = 15 s, each attempt at most discovery + authorize = 2 ×
`requestTimeoutSeconds` = 30 s at the default) costs at most **165 s** and *binds nothing* unless the
target answers. The renewal is re-attempted once per poll cycle (`pollIntervalSeconds`, 60 s) until
`expires_at`, so a one-hour session has at most ⌊900 / 60⌋ = 15 acquisition attempts in its window —
and the first one the target *answers* is terminal for that (account, password) (§3.2, budget B2). The
window is a budget for *unreachable* targets; a *refusing* target consumes exactly one bind of it.

**The floor the schedule needs.** The renewal check runs on the poll cadence, so a renewal starts at
most one `pollIntervalSeconds` after `renew_at` and must still be before `expires_at`:
`pollIntervalSeconds < lifetime / 4`, i.e. **`expires_in > 4 × pollIntervalSeconds`** (240 s at the
default). A target stating less is refused as a standing finding, not chased (§3.6). Stated
precisely: the floor guarantees the renewal **starts** before expiry; a renewal that then needs the
whole 165 s retry budget can still overrun on a session near the floor — that is the *unreachable*
case, reported as such, and no floor on the lifetime removes it.

### 2.3 The trap: the lab cannot fire the normal renewal path

CRC's year-long session means `renew_at` is 364 days away. A renewal test run only on CRC proves
nothing about the path that runs daily on a real cluster (the issue's second comment, sourced to
OCP 4.16 docs and `crc-org/snc`'s `oauth_cr.yaml`). §3.11 says which mechanism each test uses — an
injected clock for the hermetic proof, and on the lab a **session revoked from outside** to drive the
reactive path, which the lab *can* do — and never claims the other.

### 2.4 Where the process runs, and what it may write

```
$ oc get deployment group-sync-dashboard -n group-sync-dashboard -o json | jq -r '"\(.spec.replicas) \(.spec.strategy.type) \(.spec.template.spec.containers[0].image)"'
1 Recreate image-registry.openshift-image-registry.svc:5000/group-sync-dashboard/group-sync-dashboard:0.31.0-11e66987e6

$ oc get pvc group-sync-dashboard-data -n group-sync-dashboard -o jsonpath='{.spec.accessModes}'
["ReadWriteMany"]

$ oc get configmap group-sync-dashboard-config -n group-sync-dashboard -o json | jq -r '.data["clusters.yaml"]' | grep -n 'replicaCount\|leaderElection\|fleet\|clusterSecretsWrites\|saTokenLookup: true'
71:clusterSecretsWritesEnabled: true
76:fleetAccountUsername: "ocp-oauth-bind-serviceid"
77:fleetPasswordSecretNamespace: "openshift-config"
78:fleetPasswordSecretName: "ldap-oauth-bind-secret"
79:fleetPasswordSecretKey: "bindPassword"
85:replicaCount: 1
157:leaderElection: true
158:leaderLeaseName: "group-sync-dashboard"
169:    saTokenLookup: true                 <- the shared-rnd stanza

$ oc get lease group-sync-dashboard -n group-sync-dashboard -o yaml | grep -v managedFields
spec:
  acquireTime: "2026-09-22T15:20:55.817127Z"
  holderIdentity: group-sync-dashboard-65d5bd899d-w4rlk
  leaseDurationSeconds: 30
  leaseTransitions: 88
  renewTime: "2026-09-22T22:39:35.422711Z"
resourceVersion: "2115891"

$ oc get clusterrole group-sync-dashboard-reader -o json | jq -c '.rules[] | select(.apiGroups | index("coordination.k8s.io"))'
{"apiGroups":["coordination.k8s.io"],"resources":["leases"],"verbs":["get","create","update"]}

$ oc get role -n group-sync-dashboard -o json | jq -c '.items[] | select(.metadata.name=="group-sync-dashboard-cluster-secrets") | .rules'
[{"apiGroups":[""],"resources":["secrets"],"verbs":["get","list","watch","create","update","delete"]}]

$ grep -rln 'HorizontalPodAutoscaler\|autoscaling' charts/group-sync-dashboard/templates/ charts/group-sync-dashboard/values.yaml
(nothing)
```

**Decides four things.**

- **The store is per pod above one replica, so it cannot be the replica-shared state.**
  `charts/group-sync-dashboard/templates/deployment.yaml` refuses `replicaCount > 1` with election on
  because *"Above one replica each pod keeps its OWN database (/data/$POD_NAME/gsd.db)"*, and
  `charts/group-sync-dashboard/values.yaml` says why: *"A shared VOLUME with unshared FILES is safe; a
  shared FILE is not."* A compare-and-swap in SQLite (`BEGIN IMMEDIATE`, which per sqlite.org
  *"might fail with SQLITE_BUSY if another write transaction is already active on another database
  connection"*) arbitrates writers **to one file** — and above one replica there is no shared file to
  arbitrate. With persistence off the file is an emptyDir and does not survive the pod either (the
  issue's first comment). So SQLite can give *durability across a restart at one replica*, and nothing
  across replicas. It is not used for this state at all (§1).
- **The Lease grant already exists, cluster-wide, and is conditional on the wrong thing.** The
  ClusterRole carries `leases: get, create, update` with no `resourceNames` (a `create` cannot be
  name-scoped), which `charts/group-sync-dashboard/templates/rbac.yaml` renders only under
  `{{- if .Values.leaderElection.enabled }}` — and election **must be off** above one replica. So
  exactly the deployment shape where a cluster-arbitrated claim matters most is the one with no
  grant for it. §3.8 widens the condition to "election on, **or** a fleet account in use", and the
  chart tests that pin *"the leader-election Lease is the only object this application may write"*
  (`local-development/tests/test_chart_strategy.py`) keep holding, because the new object is a Lease.
- **The lab is the one-replica, election-on, Recreate shape**, with the fleet account configured and
  one `saTokenLookup` stanza already retrieved by #284 (`gsd-cluster-shared-rnd` carries
  `lookup-account: ocp-oauth-bind-serviceid`, `managed-by: sa-token-lookup`, `token-source:
  remote-lookup`, `resourceVersion 2029578` — a number the daily ping must leave alone).
- **No HPA renders from this chart.** The "HPA past a ConfigMap that says 1" case R2-5 listed can
  only be an HPA someone else created; it is covered by the claim like every other second pod, not by
  a render rule.

### 2.5 What a Lease guarantees, from the source that implements it

`client-go/tools/leaderelection/leaderelection.go`, package doc, read 2026-09-22 (`master`):

> *"This implementation does not guarantee that only one client is acting as a leader (a.k.a.
> fencing)."*
>
> *"A client only acts on timestamps captured locally to infer the state of the leader election. The
> client does not consider timestamps in the leader election record to be accurate because these
> timestamps may not have been produced by a local clock. … Thus the implementation is tolerant to
> arbitrary clock skew, but is not tolerant to arbitrary clock skew rate."*
>
> *"While not required, some method of clock synchronization between nodes in the cluster is highly
> recommended."*

and on `LeaseDuration`: *"A client needs to wait a full LeaseDuration without observing a change to
the record before it can attempt to take over."* Its validity check is `isLeaseValid`:
`observedTime + LeaseDurationSeconds > now`, where `observedTime` is the **local** clock at the moment
the record was last seen to *change* — never the record's own `renewTime`.

**Measured against this codebase:** `gsd/leader.py#LeaderElector._try_acquire` judges expiry as
`now(UTC) − spec.renewTime > lease_seconds` — the holder's clock against this pod's. That is the
skew-sensitive reading client-go deliberately avoids, and the chart's own words for the whole
mechanism are *"BEST-EFFORT, not a write fence. Leadership is checked once before each poll cycle and
never again during it, so a pod that stalls after the check can lose the lease and still finish its
writes. Two pods can also both consider themselves leader briefly, since expiry is judged against
each pod's own clock."* (`charts/group-sync-dashboard/values.yaml#BEST-EFFORT, not a write fence`).
`gsd/poller.py` repeats it at the seam: *"BEST-EFFORT admission control, NOT a write fence."*

**What a Kubernetes write *does* guarantee** — the Kubernetes API conventions, *Concurrency Control
and Consistency*: *"When a record is about to be updated, its version is checked against a pre-saved
value, and if it doesn't match, the update fails with a StatusConflict (HTTP status code 409). … The
resourceVersion is changed by the server every time an object is modified. If resourceVersion is
included with the PUT operation the system will verify that there have not been other successful
mutations to the resource during a read/modify/write cycle."* And the client's duty on a conflict:
*"the correct client action at this point is to GET the resource again, apply the changes afresh,
and try submitting again."*

**So, stated plainly, what this codebase can honour and what it cannot (§3.2 turns this into
budgets):**

| property | mechanism | held? |
|---|---|---|
| two processes cannot both **win the same claim** | a PUT carrying the `resourceVersion` just read; the API server arbitrates, one wins, the other gets 409 | **yes** — linearisable, arbitrated by etcd, independent of either pod's clock |
| a refused password is **remembered across a restart and across replicas** | the same object's annotations, written by the same CAS | **yes** — the object outlives the pods and every replica reads it before binding |
| the process that won the claim is the **only one that binds while it holds it** | a claim with a duration, released on exit, judged expired by a clock | **best-effort** — a winner paused (GC, throttling, a partition) past the claim's duration can bind after a second pod's claim; that is the fence a Lease cannot be, in client-go's words |
| a claim is judged expired **at the same instant** by every pod | `renewTime + duration` against each pod's clock | **no** — skew between pods moves the judgement; a generous duration and a re-read immediately before the authorize GET narrow the window to one round-trip and never close it |

### 2.6 The seams that exist, and the one that does not

```
$ grep -n 'credential_kind: str' local-development/gsd/clusterconfig/writer.py
102:    credential_kind: str          # bearerToken | oauth
```

`POST /api/clusterconfigs/test` builds a `CreateRequest`, whose `credential_kind` is `bearerToken |
oauth` — it can present a bearer token, never the fleet account. **It is not a bind path** and needs
no gate; this corrects the issue's first comment, which listed `writer.test_connection` as an
ungated call site. `request_discovery()` (the tab's write) wakes the discovery thread, whose lookup
consults the gate already (R3-2's tests).

`gsd/fleetlookup.py#lookup` with `write=False` is the ping, and it is already proven: the shipped
test `test_write_false_is_the_ping_the_same_read_and_nothing_stored` asserts one read of the target's
Secret, one revoke, **no write** on the host, and `result.written is None`. Nothing touches the
stored Secret, so its `resourceVersion` cannot move.

`poll_once` returns the outcome word and `gsd/poller.py#Poller._run_cluster` discards it (SPEC_S3
§9.3 rule 1: *"there is no seam for this today"*). `_reconcile_threads` and `start()` skip a cluster
whose `credential_pending` is set, which today includes `self-login`
(`gsd/config.py#CREDENTIAL_PENDING_REASONS`). §3.6 is the seam.

### 2.7 The metric shape

Prometheus, *Metric and label naming*: the timestamp gauge is spelled
`…_timestamp_seconds` (its own example: `data_pipeline_last_record_processed_timestamp_seconds`), base
units, and *"Do not use labels to store dimensions with high cardinality … such as user IDs, email
addresses, or other unbounded sets of values."* This repository's rule is stricter and is an operator
ruling: `/metrics` is deliberately public and unauthenticated, so **no metric carries a username, a
group name, a DN or a binding name** (`gsd/metrics.py`, module docstring; memory
`metrics-endpoint-is-deliberately-public`). The shipped precedent for "an instant, absent until it
happened" is `gsd_login_capture_last_read_timestamp_seconds` — *"Absent until the first successful
read: absence means never, not zero"* — and `gsd_backup_last_success_timestamp_seconds`'s rule
*"OMITTED, never zeroed … a failure to measure must not read as a measurement of failure."*

## 3. Design

### 3.1 The contract, in one table

| | |
|---|---|
| the durable, replica-shared object | **one Lease per fleet account** in the release namespace: `gsd-fleet-<sha256(username)[:16]>`, labelled `groupsync-dashboard.io/lease-type: fleet-account`, annotated with the account. Its `spec` is the **claim** (who may bind as this account right now); its annotations are the **gate** (which (account, password) must not be presented again, from whichever target answered; the target is evidence, not the key) and the **ping's bookkeeping** (last attempt, last ok, last outcome, last target, the password digest last confirmed) |
| who takes the claim | every code path that can put the password on the wire: #284's lookup, this spec's ping, a `self-login` acquisition or renewal. **No claim, no bind** — fail closed |
| the daily ping | `fleetlookup.lookup(cluster, settings, host_client, own_namespace=…, gate=…, write=False)` against **one** target per account per cadence, on the discovery thread, leader only; the result is read for `sa_token.last_used` and dropped; the login's token is revoked by the session |
| once per credential per day | the ping's due-ness is read from the account Lease (`ping-last-attempt`), not from memory: a restart, a second replica and twenty clusters on one account all see the same instant |
| stands down on a refusal | before binding, the ping reads the gate on the Lease; any entry for this (account, password digest) — a 401 refusal *or* a bound-and-failed answer such as a locked account's 500 — stands it down until the password changes or the entry is cleared, said once with `gave_up=true` |
| `self-login` renewal | `renew_at = expires_at − min(2 h, ¼ × expires_in)` from `FleetSession.expires_at`; checked every poll cycle on the cluster's own thread; the new session is entered before the old one exits, so the old token is revoked by `FleetLogin.__exit__` and the poll never runs without a credential |
| the 401 rule for `self-login` | on a poll, `auth_failed` **before** `expires_at` means *re-authenticate* (an inactivity timeout, an administrator's revoke, a changed policy) — one login on the next cycle, not a refusal; a login that is then refused gates. On the revoke path a 401 keeps #283's reading: "not proven gone" |
| suspension | a gated (account, password) stops **every** `self-login` cluster on that account at once; the line says `suspended=<account> scope=self-login stopped=<n>` and names the clusters; each stopped cluster carries a standing finding and a critical card |
| cadence is a value | `clusterConfig.fleetAccount.ping.{enabled, intervalSeconds}` → ConfigMap `fleetPingEnabled`, `fleetPingIntervalSeconds` → `Settings.fleet_ping_enabled`, `Settings.fleet_ping_interval_seconds`; default on, 86 400 |
| the instant | `fleet_account_last_ok` is an ISO-8601 UTC instant everywhere it is served (the API, the tab's row, the log line) and a Unix timestamp on `/metrics` as `gsd_fleet_account_last_ok_timestamp_seconds`, **unlabelled** — no username on a public endpoint |
| the lease grant | `leases: get, create, update` renders when election is on **or** a fleet account is in use; the chart's "only write is a Lease" invariant is unchanged |
| replicas | `userSelfLogin` with `replicaCount > 1` is refused at render, the lookup's rule applied to the other mode; the claim covers what a render cannot see (a hand `scale`, a rollover's overlap, a partition, someone else's HPA) |
| failure vocabulary | three finding codes join `FINDING_CODES`: `fleet-state-unavailable`, `self-login-suspended`, `self-login-lifetime-too-short`; five events: `fleet-ping`, `fleet-ping-failed`, `fleet-credential-suspended`, `self-login-renewed`, `self-login-failed`; three fields: `suspended=<account>`, `scope=`, `stopped=<n>`. No new `phase` |

### 3.2 The budgets — every safety claim, with its scope

- **B1 — one claim holder per account at a time, across every replica and restart.** *Held by* the
  CAS on `gsd-fleet-<account>`: a PUT with the `resourceVersion` just read; 409 means someone else
  won, and the loser does not bind. Scope: **the estate**, arbitrated by the API server. Residual,
  stated: a holder paused past `claim_seconds` (§3.3) can still bind after its claim was judged
  expired and re-taken — one extra bind per pause, never a walk, and narrowed to one round-trip by the
  re-read immediately before the authorize GET.
- **B2 — at most one *answered* failed authorize per (account, password) until the password
  changes, across every target, replica and restart.** *Held by* the account entry on the Lease
  (`refused`, §3.3): every `LoginError.bound` answer (`gsd/fleetlogin.py#LoginError`) — a 401, and a
  500 alike, since a locked account's code 19 arrives as a 500 that cannot be told from a sick
  target's (SPEC_S4a §3.1) — is recorded there **before** the finding is raised, and every bind path
  (the lookup, the ping, a `self-login` acquisition) reads it **inside** the claim before building a
  `FleetLogin`. The target that answered is recorded as evidence; it is not part of the key (#315: a
  lockout is per directory account). Scope: **the estate**, as long as the Lease is readable.
  Residuals: if the Lease cannot be written (RBAC absent), the write is refused and **no bind happens
  at all** (fail closed, §3.3) — the in-memory `CredentialGate` is then the only memory and the finding
  says so; and a 500 from one sick target stops every target of the account until the password rotates
  or the entry is cleared — the price the operator chose over walking a locked account (§5, question 7).
- **B3 — at most one ping bind per (account, password) per `fleetPingIntervalSeconds`, across
  replicas and restarts.** *Held by* `ping-last-attempt` and `ping-digest` on the Lease, read inside
  the claim. Twenty clusters on one account are one bind, because the ping is keyed on the account
  and picks one target (§3.4). A rotated password is pinged once within one discovery cadence — a
  new (account, password) has no entry — which is one bind, and the one you want.
- **B4 — at most one `self-login` login per cluster per poll cycle, and at most two per
  unexpected-401 episode.** *Held by* the session holder's state (§3.6): a cluster whose fresh session
  is refused by the API server again in the same episode is suspended with
  `self-login-suspended`, not re-logged-in every 60 s. Scope: **per process** for the count; the bind
  it produces is under B1 and B2 like any other.
- **B5 — nothing this spec mints outlives its use.** *Held by* `FleetLogin` being a context manager
  (`gsd/fleetlogin.py#FleetLogin.__exit__`): the ping's session exits inside `lookup()`; a
  `self-login` session exits when its replacement is in hand or the cluster stops. Scope: per token;
  a failed revoke is a `fleet-logout-failed` line naming the object, never silence (#283's rule).

**The budget over the system, for one wrong or locked password on one account.** T is the number of
targets that can present the account's password — `saTokenLookup` stanzas still pending plus
`userSelfLogin` stanzas — with the ping on and the Lease writable. Binds are what the directory counts
against its lockout threshold, whose value and reset window this lab cannot measure (§5, question 2):

| shape | binds the directory sees | why |
|---|---|---|
| one target | **1** | the first bound answer writes the account entry; nothing binds again until the password changes |
| T targets sharing one account | **1** | the entry is the account's: the other T − 1 read it inside their claim and stand down (B1 serialises them, B2 stops them) |
| after a restart | **+0** | the entry is on the Lease; the new pod reads it before its first claim; `ping-last-attempt` keeps the ping off |
| two replicas | **+0**, plus at most one per paused winner (B1's residual) | the CAS admits one claimant; the loser reads the entry the winner wrote |

Never "at most N per cluster": whatever the number of clusters on the account, a wrong or locked
password is presented to the directory once.

### 3.3 The account Lease — `gsd/fleetstate.py` (new module)

One object per fleet account, in the release namespace. Shape, as the API server holds it:

```yaml
apiVersion: coordination.k8s.io/v1
kind: Lease
metadata:
  name: gsd-fleet-3b1f9c0e7a2d4e61          # "gsd-fleet-" + sha256(username)[:16]
  namespace: group-sync-dashboard
  labels:
    groupsync-dashboard.io/lease-type: fleet-account
  annotations:
    groupsync-dashboard.io/account: ocp-oauth-bind-serviceid
    # THE GATE: ONE entry per account (§3.2 B2) — the last bound failure for this (account, password),
    # from whichever target answered; `target` (as httpx canonicalises it, R3-1) is evidence, not the key.
    # `digest` is the 64-bit sha256 prefix CredentialGate already uses (R3-2: a collision over-blocks,
    # never binds). A rotated password is a different digest and does not match.
    groupsync-dashboard.io/refused: '{"digest": "9f2a…", "at": "2026-09-22T14:03:11Z", "code": "login-refused", "target": "https://api.crc.testing:6443"}'
    # THE PING'S BOOKKEEPING — instants, never ages.
    groupsync-dashboard.io/ping-last-attempt: "2026-09-22T06:00:04Z"
    groupsync-dashboard.io/ping-last-ok: "2026-09-22T06:00:05Z"
    groupsync-dashboard.io/ping-last-outcome: ok          # ok | <a finding code>
    groupsync-dashboard.io/ping-last-target: shared-rnd
    groupsync-dashboard.io/ping-digest: "9f2a…"           # the password the last ok was for
spec:
  holderIdentity: group-sync-dashboard-65d5bd899d-w4rlk   # POD_NAME; "" when nobody holds the claim
  leaseDurationSeconds: 195
  acquireTime: "2026-09-22T06:00:04.000123Z"              # MicroTime: EXACTLY six fractional digits (gsd/leader.py#_now)
  renewTime: "2026-09-22T06:00:04.000123Z"
```

Why a Lease and not a ConfigMap or a Secret: the grant for it exists (§2.4); the ClusterRole tests
pin `leases` as the only writable resource, so a ConfigMap would need a new Role, a test change and
three documents re-worded; and the object *is* a lease — a claim with a holder and a duration is what
`coordination.k8s.io` is for. The gate state rides the same object because it is read at the same
moment, inside the same claim, by the same identity, and two objects would be two things to drift.

The interface, signature-level (the whole module is small; a class, a claim, and five reads):

```python
class FleetStateUnavailable(Exception):
    """The Lease could not be read or written — RBAC, a 5xx, a CAS that lost three times. The caller
    FAILS CLOSED: no bind without the claim (the elector's own posture: a pod that cannot confirm
    it leads must stop). `detail` is the API server's answer; `action` names the grant."""


@dataclass(frozen=True)
class FleetRecord:
    """One account's Lease as read: the claim, the gate, the ping's instants. Immutable; a write
    returns a new one carrying the new resourceVersion."""
    account: str
    resource_version: str | None
    holder: str
    holder_until: datetime | None          # renewTime + leaseDurationSeconds, or None when unheld
    refused: dict | None                   # {digest, at, code, target}: the account entry; target is evidence
    ping_last_attempt: datetime | None
    ping_last_ok: datetime | None
    ping_last_outcome: str | None
    ping_last_target: str | None
    ping_digest: str | None

    def gated(self, digest: str) -> dict | None:
        """The account entry when its digest matches, whatever the target — every bind path's rule (B2)."""


class FleetLease:
    """The account's Lease through the pod's own ServiceAccount (the elector's client, verbatim:
    `gsd/leader.py#LeaderElector._client`). Every write is a PUT with the resourceVersion just read;
    a 409 is re-read and re-applied at most three times, then FleetStateUnavailable."""

    def __init__(self, namespace: str, account: str, *, identity: str, claim_seconds: int,
                 client_factory=None, clock=None): ...
    def read(self) -> FleetRecord: ...
    def claim(self) -> FleetRecord:
        """GET; if held by another identity and not expired -> ClaimHeld (a free, silent outcome);
        else PUT holder=identity, renewTime=now with the resourceVersion read (or POST when absent;
        a 409 on the POST is someone else's create — refused, not retried into)."""
    def release(self, record: FleetRecord) -> None:
        """PUT holder="" with the CAS; a failure is logged once and the claim expires on its own."""
    def refuse(self, record: FleetRecord, target: str, digest: str, code: str, at: datetime) -> FleetRecord:
        """Write the account entry (one CAS PUT); `target` is recorded as evidence, not as the key."""
    def clear_other_digests(self, record: FleetRecord, digest: str) -> FleetRecord:
        """A password that changed retires the entry for the old one."""
    def note_ping(self, record: FleetRecord, *, at: datetime, ok: bool, outcome: str, target: str,
                  digest: str) -> FleetRecord: ...


class ClaimHeld(Exception):
    """Another holder's claim is live. Not a failure: the caller tries again next cycle."""


def claim_seconds(settings) -> int:
    """The acquisition budget, computed from the settings the login runs under and never a magic
    number: RETRY_POLICY.attempts × 2 × requestTimeoutSeconds (discovery + authorize) + the policy's
    total backoff + 2 × requestTimeoutSeconds (the read and the revoke), floored at 60."""
```

**The protocol every bind path follows, in this order and no other:**

1. `record = lease.claim()` — CAS; `ClaimHeld` → stop, silently (DEBUG), try next cycle.
2. `record.gated(digest)` — the account entry, the same rule on every path (B2)
   → a gated credential is a free refusal (`LookupRefused(..., gated=True)`, R3-2's shape), said once
   with `gave_up=true`, and the claim is released.
3. **Re-read the Lease once more** (`lease.read()`): the holder must still be this identity and the
   claim not expired. Anything else → release nothing, bind nothing (the claim was lost while the
   gate was being read). This is the one round-trip the residual in B1 is narrowed to.
4. Bind: build `FleetLogin` (`gsd/fleetlogin.py#FleetLogin`), run the caller's body.
5. On `LoginError.bound` → `lease.refuse(record, target, digest, code, at)` — the account entry,
   with the answering target as evidence — **before** the finding is raised — the durable write comes first, the in-memory `CredentialGate.refuse` second, so a crash
   between the two loses the cheap copy, never the durable one.
6. `lease.release(record)` in a `finally`.

`gsd/fleetlookup.py#CredentialGate` stays as the **cache**: seeded from `FleetRecord.refused` at every
read, consulted where it is today. Its docstring's sentence *"Best-effort and per process; the
durable, replica-shared gate is #285's"* is replaced by "the cache of the account Lease's gate
(SPEC_S4c §3.3); seeded on every read, and never the only copy while the Lease is writable."

**Fail closed, and what it looks like.** `FleetStateUnavailable` on `claim()` or `refuse()` is the
finding `fleet-state-unavailable` (free, announced on transition, rechecked every cycle), with
`action=` naming the grant — *grant get/create/update on coordination.k8s.io/leases in <namespace> to
<serviceaccount> (the chart renders it under leaderElection.enabled or a fleet account in use)* — and
**no bind is attempted** by the lookup, the ping or a `self-login` acquisition while it stands. The
asymmetry decides it: a missed login while RBAC is fixed is one stale cluster; a bind without the
gate is the walk this object exists to stop.

### 3.4 The daily ping — on the discovery thread, after the lookups

`gsd/poller.py#Poller._run_discovery` already runs `_discover_once → _reconcile_threads →
_retrieve_pending` on the binding cadence; `_ping_accounts()` runs after `_retrieve_pending`, leader
only, and is a loop over **accounts**, not clusters:

```python
def _ping_accounts(self) -> None:
    """One real read per fleet account per cadence (SPEC_S4c §3.4): the accounts are the distinct
    `ldapConnectionBootstrap or fleet_account_username` over the enabled clusters that declare a
    mode; each is pinged against ONE target — the enabled cluster on that account whose Secret
    was pinged least recently (never first, then by name) — through lookup(write=False)."""
```

- **Which target.** The enabled clusters on the account whose credential kind is `remote-lookup`
  (a `self-login` cluster confirms the account every renewal and needs no ping), ordered by
  `ping-last-target` rotation: the cluster that was not the last target and comes first by name.
  Over N cadences every target is read once, so a grant revoked on target 3 is a finding naming
  target 3 within N days and the account's `last_ok` still moves on the days the others answer.
  Decided, not measured; §5.1 says what would change it.
- **Due when** `now − ping_last_attempt ≥ fleet_ping_interval_seconds`, **or** the password digest
  differs from `ping-digest` (a rotation is confirmed once, within one cadence). Both read from the
  Lease inside the claim, so a restart at 23:59 does not ping again at 00:00 and a second replica
  reads the same instant.
- **Stands down when** `record.gated(digest)` — the account entry for this (account, password),
  whether a 401 or a bound-and-failed 500, from any target. Decided on the asymmetry: a 500 from one target
  *may* be code 19 (the account already locked, SPEC_S4a §3.1), and one more bind a day against a
  locked account is the walk in a health check's clothing. The stand-down is a free finding, said
  once: `fleet-ping-failed … outcome=<the gating code> gave_up=true suspended=<account> scope=ping
  action="not pinged again until the fleet password Secret changes or the entry on Lease
  gsd-fleet-… is removed; the gate is re-read every cycle at no cost"`. §5.2 records the cost of
  this choice.
- **What it writes.** Nothing on the host but the Lease's ping annotations (one CAS PUT) — the
  cluster Secret is not touched, and the walk in §3.12 asserts its `resourceVersion` before and after.
  The `LookupResult` is read for `sa_token.last_used` and `account`, then dropped; the token it carried
  rides the result's `secrets` into the event helper's redaction and is never held.
- **What it says.** `fleet-ping account=<u> target=<cluster> last_used=<label> last_ok=<ISO>` on
  success; `fleet-ping-failed phase=credential outcome=<code> account=<u> target=<cluster>
  attempt=1/1 …` on a spent failure — one attempt, no backoff: the next ping is the next cadence, and
  a bound answer is gated anyway. The finding is held on the registry against the target in a slot
  of its own — `ClusterRegistry.set_ping_finding`, merged into `findings()` beside `_lookups` — and
  **not** through `gsd/clusterconfig/registry.py#ClusterRegistry.set_lookup_finding`: `_retrieve_pending`
  clears the lookup slot for every cluster it stops tracking, each cycle, and a cluster that re-enters
  pending would overwrite it. Two slots, two owners, one card: the Findings card names the cluster
  the next lookup would fail on.
- **The instant.** `ping-last-ok` is copied into `RuntimeSignals` (§3.9) and served by the API
  (§3.10) as it is on the Lease — an ISO-8601 UTC instant. Never an age in a server string
  (`absolute-instants-in-server-text`, the operator's ruling).

**Restart, and standbys.** On `start()`, **every** replica reads every account's Lease once
(`FleetLease.read`, no claim) to seed `CredentialGate` and `RuntimeSignals`, and re-reads them on every
discovery cadence (one GET per account per `bindingIntervalSeconds`, no claim, no write) — so
`/metrics` and the tab serve the same instant on a standby as on the leader, a refused password is
refused from the first cycle after a restart, and only the leader ever writes.

### 3.5 What the ping proves, and what it does not

The issue's table stands, confirmed against `gsd/fleetlookup.py#read_sa_token`: the ping is a real
login (a bind), then `GET /api/v1/namespaces/<ns>/secrets/<sa>-token` *as the session* — so a rotated
password, a revoked `get` grant, a deleted ServiceAccount or Secret, a Secret of the wrong type or
owner, and the cleaner's `invalid-since` stamp each surface as their own code. A SubjectAccessReview
would answer about a *kind*; the read answers about the object.

It does **not** keep any stored token alive — retracted on the issue and measured on #284:
`legacy-token-last-used` is stamped by the **ServiceAccount token authenticating**, i.e. the poll,
and the fleet account's `get` uses its own session. A manually created token Secret is never stamped
`invalid-since` at all. The residual case — an estate still carrying an **auto-generated** token
Secret (OpenShift ≤ 4.15 with the registry on) whose cluster *stops polling* for a year — is carried
here as one line, not a mechanism: a `self-login-suspended` or long-`unreachable` cluster on such an
estate should be re-onboarded (delete and recreate the token Secret) rather than resumed, and the
lookup's `sa-token-invalidated` finding is what says so when it happens.

### 3.6 `self-login` — the session is the credential, and it renews or it stops

`gsd/selflogin.py` (new module) owns the sessions; `gsd/poller.py` consults it on the cluster's own
thread. No new thread: the renewal check is one comparison per poll cycle.

```python
@dataclass
class SessionState:
    login: FleetLogin                    # entered; its __exit__ is the revoke
    session: FleetSession                # token, expires_at, issuer
    renew_at: datetime                   # expires_at - min(2 h, expires_in / 4)   (SPEC_S4 §3.1)
    reauth: bool = False                 # a poll answered 401 before expires_at: re-authenticate next cycle
    reauth_logins: int = 0               # B4: at most two per episode

class SelfLoginSessions:
    """Process-wide, one lock (the ClusterRegistry shape the issue asked for). The poll thread asks
    `credential_for(cluster)` before each poll and tells `poll_answered(cluster, outcome)` after."""
    def credential_for(self, cluster, settings, host_client, lease, gate, *, now) -> str | None:
        """The session's token, acquiring or renewing first when due; None when the cluster is
        suspended or the acquisition failed this cycle (the poll is skipped, not failed)."""
    def poll_answered(self, cluster, outcome: str, *, now) -> None: ...
    def stop(self, cluster) -> None:
        """Exit the session (revoke) — the cluster was disabled, retired or suspended."""
    def suspend_account(self, account: str, reason) -> list[str]:
        """Every cluster on this account: stopped, its finding set; returns the names for the line."""
```

**Acquisition** (first cycle, and every renewal) runs §3.3's protocol against the account's Lease —
`gated(digest)`, the account entry every path reads (B2): a failure written by any target parks
this acquisition too, after a restart and on another replica alike (R2-1 is reversed by the operator's
ruling, Orchestrator's notes) — then `FleetLogin(cluster, account, password, timeout=…).__enter__()`. On success the
**new** state replaces the old and the old `FleetLogin.__exit__` runs, so the superseded token is
revoked *after* its replacement exists; the poll never runs without a credential, and the token cache
window #283 measured (a revoked token authenticates for ~121 s) is irrelevant because the old token
is no longer presented.

**The poll** runs `poll_once(store, dataclasses.replace(cluster, token_value=token,
user_self_login=False, ldap_connection_bootstrap=None), …)` — the substitution `read_sa_token` already
uses; `token_value` is what `_credentials()` redacts against, so the session token never reaches a
line. `store.upsert_cluster` keeps `credential=self-login`; `credential_pending` no longer names
`self-login` (`gsd/config.py#CREDENTIAL_PENDING_REASONS` loses that key, and `resolve_token()` for
the mode raises unless a token was injected — reachable only by a direct caller, as today).

**Renewal** when `now ≥ renew_at`, at the top of the cycle, before the poll. A retryable failure
(unreachable) leaves the current session in place and is tried again next cycle until
`expires_at`; a bound failure gates the (account, password) and **suspends** (below). At
`expires_at` with no replacement the session is exited and the cluster stops with
`self-login-failed … gave_up=true`.

**The 401 rule, reconciled with #283's revoke-side reading.** `poll_answered(cluster, "auth_failed")`
with `now < expires_at` sets `reauth=True`: the session was invalidated by something the fragment
does not carry — an inactivity timeout (unset on the lab, minimum 300 s where set), an
administrator's `oc delete oauthaccesstoken`, a policy change — and the next cycle acquires again.
That is *not* a refusal and not recorded as one: nothing evaluated the password. A 401 at or after
`expires_at` is the schedule having failed and is logged as such. If the **fresh** session's first
poll answers 401 again (`reauth_logins == 2` in one episode), the cluster is suspended with
`self-login-suspended` naming the API server's answer — the API server refusing sessions it just
issued is a fact about the target, and re-logging in every 60 s is a bind rate with no ceiling. The
revoke path keeps #283's rule untouched: a 401 on the DELETE is `fleet-logout-failed`, "not proven
gone".

**Suspension.** A bound failure on any `self-login` acquisition for account *A* calls
`suspend_account(A)`: every `self-login` cluster on *A* has its session exited (revoked), its thread
parked (it keeps checking the gate each cycle at no cost and resumes when the digest changes), a
standing finding `self-login-suspended` on the registry, and its `poll_outcome` recorded once as
`auth_failed` for a `login-refused` (the password *was* presented and refused — truthful, and it
turns the Overview card critical, which is what "an outage, not a warning" means on this page) or
`unreachable` with the code for any other bound answer. The line:

```
fleet-credential-suspended phase=credential outcome=<login-refused|login-failed> account=<A> suspended=<A> scope=self-login stopped=<n> clusters=<a,b,c> target=<the one that answered> action="every self-login cluster on this account stopped polling: rotate the fleet password Secret or correct ldapConnectionBootstrap, or check the account is not locked; the gate on Lease gsd-fleet-… re-arms when the password changes"
```

A `remote-lookup` cluster on the same account keeps polling (its token is the target's); the ping
stands down (§3.4).

**The floor.** A session whose `expires_in ≤ 4 × pollIntervalSeconds` cannot be renewed on this
schedule (§2.2). It is not chased: the acquisition succeeds, the session is exited at once, and the
cluster carries `self-login-lifetime-too-short` naming both numbers and the fix (a longer
`accessTokenMaxAgeSeconds` on the target, or `saTokenLookup` instead).

### 3.7 Where the code changes, file by file

| file | change |
|---|---|
| `gsd/fleetstate.py` | **new** — §3.3 |
| `gsd/selflogin.py` | **new** — §3.6 |
| `gsd/fleetlookup.py` | `lookup()` gains `lease: FleetLease` and runs §3.3's protocol around `FleetLogin` (claim → gate → re-read → bind → refuse-on-bound → release); `CredentialGate` becomes the seeded cache; `LookupRefused` gains nothing |
| `gsd/poller.py` | `_ping_accounts()`; `_retrieve_pending()` passes the account's `FleetLease`; `_run_cluster` consults `SelfLoginSessions` before `poll_once` and reports after it; `start()` seeds from the Leases and no longer skips `self-login`; `_reconcile_threads` likewise |
| `gsd/config.py` | `fleet_ping_enabled`, `fleet_ping_interval_seconds`; `CREDENTIAL_PENDING_REASONS` drops `self-login`; `resolve_token()`'s message for the mode |
| `gsd/clusterconfig/__init__.py` | the three codes join `FINDING_CODES` |
| `gsd/clusterconfig/registry.py` | `set_ping_finding` — the ping's own standing slot, merged into `findings()` (§3.4) |
| `gsd/metrics.py` | the three families of §3.9; `RuntimeSignals.note_fleet_ping`, `note_fleet_suspended` |
| `gsd/api.py` | the `fleet` block and the per-cluster `session` block on `/api/clusterconfigs` (§3.10) |
| `gsd/static/index.html` | the two rows (§3.10) |
| `charts/…/values.yaml`, `templates/configmap.yaml` | `clusterConfig.fleetAccount.ping.{enabled, intervalSeconds}` → `fleetPingEnabled`, `fleetPingIntervalSeconds` |
| `charts/…/templates/rbac.yaml`, `templates/_helpers.tpl` | the Lease grant's condition; `gsd.fleetAccountInUse` shared with `fleet-account-rbac.yaml`; `userSelfLogin` with `replicaCount > 1` refused |
| `charts/…/Chart.yaml`, `pyproject.toml`, `gsd/__init__.py` | chart 0.54.0, app 0.33.0 — the next minor rungs after SPEC_D2b's chart 0.53.0 and app 0.32.0; re-assigned at the implementing PR if the ladder has moved |
| docs | §3.13 |

### 3.8 The chart

```yaml
clusterConfig:
  fleetAccount:
    # …existing keys…
    # THE DAILY PING (SPEC_S4c §3.4, #285): once per account per interval the dashboard logs in as
    # the fleet account and reads the poller ServiceAccount's token on ONE cluster, stores nothing,
    # and records the instant it last succeeded. One bind per interval for the whole fleet — never
    # one per cluster. It stands down on a refusal (a wrong password is sent once, not daily).
    ping:
      enabled: true
      # Daily. Shorter buys little — a credential rarely breaks between two mornings — and every
      # increment multiplies the bind rate at a directory that is counting (SPEC_S3 §9.3.6).
      intervalSeconds: 86400
```

`templates/rbac.yaml`: the `coordination.k8s.io/leases` rule renders under
`{{- if or .Values.leaderElection.enabled (eq (include "gsd.fleetAccountInUse" .) "true") }}`, where
`gsd.fleetAccountInUse` is the `$inUse` computation `fleet-account-rbac.yaml` already performs (a
chart-level username, or any stanza declaring a mode), lifted into `_helpers.tpl` and used by both.
The comment above the rule gains one sentence: *the fleet-account claim (SPEC_S4c) is a second Lease
under the same rule; still the one resource this application writes.*

`templates/_helpers.tpl`, beside the lookup's replica rule: `userSelfLogin` on any stanza with
`replicaCount > 1` is refused — *"a self-login session is per process, so each replica would log in
as the fleet account for every cluster on every renewal; use replicaCount 1 for a release that
declares userSelfLogin"* — the same rule as the lookup's, for the same reason. A Secret-declared
`userSelfLogin` on a multi-replica release is refused by the pod at runtime the way the lookup is
(`replica_count > 1` without an elector → `fleet-write-disabled`'s twin, `self-login-suspended`
with the replica count in its detail).

Chart README: the two values rows; the *"Three rules in the ClusterRole are conditional"* paragraph
becomes *"…`coordination.k8s.io/leases` (`get`, `create`, `update`) renders when `leaderElection.enabled`
or a fleet account is in use (`clusterConfig.fleetAccount.username`, or a stanza declaring a mode) —
the election Lease and the fleet-account claim, and that pair of Leases — the dashboard's own, which
grant nobody access to anything — are the only objects it writes on any cluster."*

### 3.9 Metrics — three families, no names

```
gsd_fleet_account_last_ok_timestamp_seconds     gauge, no labels
    Unix time of the OLDEST last successful ping across the configured fleet accounts — the most
    stale account is the one to alert on. Absent until any ping has succeeded: absence means never,
    not zero. Alert: (time() - gsd_fleet_account_last_ok_timestamp_seconds) > 2 * <interval>.
gsd_fleet_account_ping_enabled                  gauge, no labels, 0|1
    While this is 1, absence of the timestamp above means no ping has ever succeeded.
gsd_fleet_account_suspended                     gauge, no labels, 0|1
    1 when any (account, password) is gated on its Lease — a login was refused or answered without
    a session and nothing binds as that account until the password changes.
```

No label carries the account (a username), the target (a cluster name is existing precedent but adds
nothing here) or the digest (a sha256 prefix of a guessable username is a name in a hat). Read at
scrape time from `RuntimeSignals`, which every replica seeds from the Leases at start and refreshes
once per discovery cadence (§3.4), and which the leader also fills on every ping — never from the
Lease per scrape (an API call per scrape per replica), never zeroed on a failure to read
(`gsd/metrics.py`'s own rule for the backup timestamp). A standby therefore carries the same series
as the leader, unlike the per-poll families it deliberately omits.

### 3.10 The API and the tab

`GET /api/clusterconfigs` (behind `clusterconfig:view`, where usernames already appear — SPEC_S3
§3.1 rule 4) gains:

```json
"fleet": {
  "ping": {"enabled": true, "interval_seconds": 86400},
  "accounts": [
    {"username": "ocp-oauth-bind-serviceid", "lease": "gsd-fleet-3b1f9c0e7a2d4e61",
     "last_attempt": "2026-09-22T06:00:04Z", "last_ok": "2026-09-22T06:00:05Z",
     "last_outcome": "ok", "last_target": "shared-rnd",
     "suspended": [{"target": "https://api.other.example:6443", "since": "2026-09-22T14:03:11Z", "code": "login-refused"}]}
  ]
}
```

and, on a `self-login` cluster's entry, `"session": {"state": "current|renewing|suspended|none",
"expires_at": "2026-09-23T06:00:05Z", "renew_at": "2026-09-23T04:00:05Z"}`. Instants only; the page
computes any age client-side where it re-renders for free.

The tab (`gsd/static/index.html`, the `#cc-head` card): one row per account — `fleet account
<username> · last confirmed <instant> on <target> · <outcome>`, `never` before the first success, and
`suspended` with the count when any entry is gated; and on a `self-login` cluster's credential row
`self-login · expires <instant>`. That is all; the provenance card and its words are S3c's.

### 3.11 Tests — what fails before and passes after

`local-development/tests/test_fleet_lifecycle.py` (new), on the harness `test_fleet_lookup.py` ships
(`LookupTarget`, `FakeHost`, the `wire` fixture, an injected clock) plus a **fake Lease API** on the
host: `FakeHost._get`/`_send` answer the `coordination.k8s.io` paths, enforce the CAS (a PUT whose
`resourceVersion` is not the current one answers 409), and count every write.

- **R1 — the claim is a CAS.** Two `FleetLease` instances for one account, interleaved: the second
  PUT answers 409, `claim()` raises `ClaimHeld`, and the authorize count on the wire is **1**.
- **R2 — the gate is on the object, and it is the account's.** A bound failure (a 401, and a 500)
  through target A writes the account entry before the finding; a *new* `Poller` (a restart), a second
  `FleetLease` (a replica) and a bind path aimed at target B all read it and none binds: the authorize
  count stays **1** across two processes and three targets. A rotated password (a new digest) binds once.
- **R3 — the ping is one bind per account per cadence.** Twenty `remote-lookup` clusters on one
  account: one authorize per cadence; the target rotates by name; `ping-last-attempt` on the object
  makes a restarted poller skip until the cadence; a rotated password pings within one cadence.
- **R4 — the ping stands down.** With a gated entry for the account (either code) the ping makes no
  request, says `gave_up=true suspended=<account> scope=ping` once, and is silent after — and the
  stored cluster Secret's `resourceVersion` on the fake host is unchanged across a successful ping.
- **R5 — the margin.** With an injected clock: `expires_in=3600` renews at 2700 s, `86400` at 79 200
  s, `31536000` at 31 528 800 s; `expires_in=200` at `pollIntervalSeconds=60` is
  `self-login-lifetime-too-short` and no second login.
- **R6 — renewal keeps the poll fed and revokes the old token second.** The new 302 is answered
  before the old token's DELETE is on the wire; the poll after renewal presents the new token; a
  renewal that is unreachable leaves the old session in place; a bound failure suspends every
  `self-login` cluster on the account with `stopped=<n>` and the names.
- **R7 — the 401 rule.** A poll answering 401 before `expires_at` re-authenticates once on the next
  cycle and records no refusal; a fresh session answered 401 again suspends
  (`self-login-suspended`); a 401 on the revoke stays `fleet-logout-failed`.
- **R8 — fail closed.** A 403 on the Lease is `fleet-state-unavailable`, announced once, and **no**
  authorize reaches the wire from the lookup, the ping or a `self-login` acquisition.
- **R9 — no credential reaches a line.** The redaction pin drives every new event with the password
  and the session token planted in remote-controlled text and greps the whole log (SPEC_S3 §3.1
  rule 4).
- **Metrics:** absent-until-first-success for the timestamp; `ping_enabled` follows the setting;
  `suspended` follows the gate; no label on any of the three.
- **Chart** (`test_chart_connection_modes.py`, `test_chart_strategy.py`): `userSelfLogin` with
  `replicaCount 2` fails the render by name; the Lease rule renders with election off and a mode in
  use, and not with election off and no account; `test_the_only_write_in_the_role_is_the_dashboards_own_lease`
  passes unchanged on every render; the ConfigMap carries `fleetPingEnabled` and
  `fleetPingIntervalSeconds`.
- **Index:** `test_specs_index.py` — the count moves to twenty-two and the S batch's issue set gains
  #285.

### 3.12 Verification on the reference cluster — read-only where it matters

The lab cannot fire the normal renewal (§2.3) and **must not** log in as the fleet account. The walk:

1. Deploy the PR head with `release-crc.sh` (the operator's rule: the deployed page, not the
   harness). Before anything: `oc get secret gsd-cluster-shared-rnd -o jsonpath='{.metadata.resourceVersion}'`
   and `oc get oauthaccesstokens -o json | jq '[.items[] | select(.userName=="developer" and .clientName=="openshift-challenging-client")] | length'`.
2. **The ping, as `developer`.** A `saTokenLookup` stanza with `ldapConnectionBootstrap: developer`
   and the password Secret holding `developer`'s password (S4b's live-check arrangement; the
   token-reader Role granted to `developer` on the lab). Set `intervalSeconds` low for the walk.
   Expect: `fleet-ping account=developer target=… last_ok=<ISO>`; the Lease `gsd-fleet-<sha(developer)>`
   with its annotations; `gsd_fleet_account_last_ok_timestamp_seconds` present; the tab's row; the
   Secret's `resourceVersion` **unchanged**; the `developer` token count back to its starting number.
3. **The stand-down.** Rotate the Secret to a wrong password. Expect exactly **one** authorize on the
   oauth-server (its pod log, or the audit log D1 already parses), `login-refused` on the object,
   `fleet-ping-failed … gave_up=true suspended=developer scope=ping`, and *no further authorize
   across three cadences*. Rotate back: one confirming ping within a cadence.
4. **`self-login`, as `developer`.** A `userSelfLogin` stanza with `ldapConnectionBootstrap: developer`
   against `https://api.crc.testing:6443`. Expect the cluster to poll (`gsd_cluster_up 1`), the tab's
   `expires <ISO>` a year out, `renew_at` two hours before it.
5. **The reactive path the lab *can* drive.** `oc delete oauthaccesstoken <the session's object>` as
   cluster-admin. Expect: the next poll's 401, `reauth`, one new login on the following cycle, the
   poll green again — and no refusal recorded. Then a wrong password + the same deletion: the
   re-authentication is refused once, `fleet-credential-suspended … scope=self-login stopped=1`, the
   card critical, and no second authorize.
6. **Two processes.** With the pod running, run a second copy of the app out of cluster against the
   same namespace (`GSD_NAMESPACE`, the pod's ServiceAccount token): the second `claim()` on a held
   Lease is `ClaimHeld`; the authorize count moves by the leader's binds only.
7. `oc get oauthaccesstokens` count for `developer` at the end equals the start; the fleet account's
   count is **untouched at 2** (the pre-existing pair, #286's).

Steps 3 and 5 are the "deliberately wrong password" the Definition of Done asks for. **Both use
`developer`.** A wrong password for `ocp-oauth-bind-serviceid` is never tried, on this lab or any.

### 3.13 Documents

- `docs/CHANGELOG.md` — one Unreleased bullet in the house style (what changed, why, the numbers).
- `charts/group-sync-dashboard/Chart.yaml` — `# CHART 0.54.0 (…), MINOR:` history line; `version`,
  `appVersion`.
- `charts/group-sync-dashboard/README.md` — the two values rows; the conditional-rules paragraph
  (§3.8); the log-level ladder's ERROR row gains "the fleet-account Lease unwritable".
- `docs/CLUSTER_STANZA.md` — the `userSelfLogin: true` row of the credential-kind table (from *no —
  pending*) and case 7 (`remote + userSelfLogin`, from *listed, pending, not polled*) to *polled on its
  own session; renewed a fixed margin before expiry*; `local-development/tests/test_cluster_stanza_matrix.py`
  is what fails when the document stops being true.
- `docs/specs/README.md` — the S4c row; `local-development/tests/test_specs_index.py` — twenty-two,
  and `{230, 283, 284, 285}`.
- `gsd/fleetlookup.py#CredentialGate` docstring — the sentence in §3.3.

## 4. Failure modes, enumerated

| situation | what happens | budget |
|---|---|---|
| **pod restart mid-window** (a claim was held) | the new pod GETs the Lease: the old claim is live until `renewTime + claim_seconds` (≤ 195 s at defaults) → `ClaimHeld`, silent, next cycle. The gate and the ping instants are on the object, so nothing is re-bound and nothing is re-pinged | B1, B2, B3 |
| **two replicas** (a hand `scale`, a rollover's overlap, a partition, someone's HPA) | both read the gate; both try the CAS; one 409s and stands down. The render refuses the shapes it can see (§3.8); the claim covers the rest | B1 |
| **a paused winner** (GC, throttling) past `claim_seconds` | the claim is judged expired and re-taken; the paused pod's bind may still go out when it resumes — one extra bind, narrowed by the re-read before the authorize GET; never a walk, because its answer is gated like any other | B1's stated residual |
| **rotated password** | a new digest: the gate entry does not match; the old entry for the account is retired; the ping confirms within one cadence (one bind); `self-login` clusters resume on their next cycle | B2, B3 |
| **a directory that has already locked the account** | the first bind answers 500 (code 19 → `HandleError`), `bound=True`, `login-failed` on the object; every path on that account stands down (ping, lookup, `self-login`); the finding says *check the account is not locked*. Nothing here can unlock it, and nothing here binds again while it is locked | B2 |
| **the Lease is unreadable / unwritable** (RBAC drift, `rbac.create: false`, a 5xx) | `fleet-state-unavailable`, announced once, rechecked every cycle; **no bind by any path**; the lookup and the ping wait; a `self-login` cluster keeps its current session until `expires_at` and then stops with `gave_up=true` | fail closed |
| **clock skew between pods** | the CAS is unaffected; the expiry judgement moves by the skew; a skew larger than `claim_seconds` lets a live claim be judged expired → the paused-winner case above. Stated, not solved: client-go's own doc recommends clock synchronisation and offers no fence either | B1's residual |
| **the target's inactivity timeout / an admin revoke** | a 401 on the poll before `expires_at` → re-authenticate next cycle, once; no refusal recorded | B4 |
| **the API server refuses a fresh session** | a second 401 in the episode → `self-login-suspended`; no login loop | B4 |
| **`expires_in ≤ 4 × pollIntervalSeconds`** | the session is exited at once; `self-login-lifetime-too-short` names both numbers; the cluster does not poll | — |
| **renewal unreachable** | the current session keeps polling; retried each cycle until `expires_at`; then stop, out loud | none bind |
| **the old token's revoke fails on renewal** | `fleet-logout-failed` names the object; the new session polls; #286's litter, said so | B5 |
| **a `self-login` cluster is disabled or retired** | `SelfLoginSessions.stop` exits (revokes) its session on the thread's way out | B5 |
| **twenty clusters, one account, all `self-login`, all due at once** | twenty acquisitions serialise on one claim: each cycle at most one wins; the rest are `ClaimHeld` and try next cycle — at 60 s cycles the last renews within 20 minutes of `renew_at`, inside every window in §2.2 but the one-hour session's 15 minutes. §5.4 | B1 |

## 5. Open questions — not settled, with what would settle each

1. **Which target the ping reads.** Decided here as rotation by name (§3.4) so every target is
   covered over N cadences. The alternative — a fixed target — gives a stabler `last_ok` and never
   catches a grant revoked on the others until their next lookup. *To settle:* the estate's answer to
   "is a per-target grant revocation something you want found within N days, or only at the next
   onboarding?". House rule applied meanwhile: easy to manage, best practice → rotation.
2. **Whether a bound-and-failed (non-401) answer on one target should stand the ping down for the
   whole account.** Decided conservatively (§3.4): yes, because the 500 may be a locked account — and
   extended to every bind path at review (question 7).
   The cost: a flaky proxy in front of one target silences the daily check for every target until
   the password rotates or an operator clears the entry. *To settle:* a measurement this lab cannot
   take — what the estate's directory answers for a locked account through *its* OAuth server, and
   whether its lockout counter resets. Until then the safe direction is the over-block.
3. **`claim_seconds` from settings versus a fixed value.** Computed (§3.3) so a longer
   `requestTimeoutSeconds` cannot make a live claim look expired mid-login. *To settle:* measure the
   longest acquisition on the lab under a dropped target (the login's `gave_up` line carries the
   elapsed time) and compare with the computed figure.
4. **Serialising twenty `self-login` renewals on one claim.** §4's last row shows the one-hour
   session is the case that can be squeezed. *To settle:* whether any estate runs `self-login` at
   that lifetime with that many clusters; if so, the fix is a claim per (account, target) for
   renewals only — more objects, the same gate — and it is not built ahead of the need.
5. **Should the fleet-account Lease be labelled for `oc get lease -l` and pruned when an account
   leaves the configuration?** Decided: labelled, not pruned — the gate on it is exactly what must
   survive a stanza edit (`verify-what-resets-the-state`). *To settle:* whether an estate objects to
   one namespaced Lease per retired account; deletion is one `oc delete`.
6. **The inactivity timeout at the OAuth *client* level.** Unmeasured beyond "null on
   `openshift-challenging-client` on the lab". A cluster that sets it there would idle the session out
   and every poll would be a 401 → one re-auth per episode (§3.6). *To settle:* set it on a
   disposable cluster and watch the cadence; the reactive rule needs no change, only confirmation.
7. **The price of the account-wide gate.** Decided by the operator at review (2026-09-23; Orchestrator's
   notes): every bound failure gates the account, reversing R2-1. A flaky proxy in front of ONE target
   stops the lookup, the ping and `self-login` acquisition on EVERY target of that account until the
   password rotates or an operator clears the entry — `oc annotate lease gsd-fleet-<…> -n <ns>
   groupsync-dashboard.io/refused-`, which the runbook (#316) must carry. *To settle whether a narrower
   rule is ever safe:* what the estate's directory answers for a locked account through its OAuth
   server (question 2's measurement); if a locked account were distinguishable from a sick target, the
   500 half could return to a per-target entry without walking a locked account.

## 6. Definition of Done — one-to-one with the issue's

| the issue's line | this spec |
|---|---|
| *The daily ping, once per credential, standing down on a refusal, reporting `fleet_account_last_ok` as an instant.* | §3.4: one bind per account per cadence, keyed and remembered on the account Lease (B3); stands down on any gated entry for the (account, password), said once with `gave_up=true`; `last_ok` is an ISO-8601 UTC instant on the Lease, the API, the tab and the log, and `gsd_fleet_account_last_ok_timestamp_seconds` on `/metrics`. Tests R3, R4; walk steps 2–3 |
| *`self-login` renewal at 80 % of the **read** lifetime, with the target's value discovered rather than assumed.* | Superseded on the issue by the business owner: **a fixed margin**, `expires_at − min(2 h, ¼ × expires_in)` (SPEC_S4 §3.1), from `FleetSession.expires_at` — the target's own `expires_in`, nothing read from `oauth/cluster`. §2.2's table, §3.6, test R5; the lab's year-long session is the reason the hermetic proof injects the clock (§2.3) |
| *A per-credential suspension gate with durable state, surviving a pod restart.* | §3.3: the gate lives on the account Lease, written by CAS before the finding, read inside the claim by every bind path; survives a restart **and** a second replica (B2). Tests R2, R8; walk step 3 |
| *`suspended=<credential>` in the log, carrying the scope and the count of what stopped.* | §3.6's `fleet-credential-suspended … suspended=<account> scope=self-login stopped=<n> clusters=…`; the ping's `suspended=<account> scope=ping`. Test R6; walk step 5 |
| *Cadence is a value; the default is daily.* | `clusterConfig.fleetAccount.ping.intervalSeconds: 86400` → `fleetPingIntervalSeconds` → `Settings.fleet_ping_interval_seconds` (§3.8); the chart test asserts the ConfigMap key |
| *Walked on the reference cluster, including a deliberately wrong password proving the ping stands down rather than retrying.* | §3.12, steps 1–7 — as `developer`, never as the fleet account; step 3 counts the authorize requests and expects one |

Inherited from #284 and closed here: **true mutual exclusion across replicas** (R2-5) — B1, with its
residual stated rather than claimed away.

## 7. What the next steps inherit

- **#286** — the two `openshift-challenging-client` tokens for `ocp-oauth-bind-serviceid` created
  2026-09-19 (§2.1) are the litter; nothing from #283 onward adds to them, and every
  `fleet-logout-failed` line from this step names an object by its `sha256~` name.
- **S3c** — the `fleet` block and the `session` block on `/api/clusterconfigs` (§3.10) are the
  tab's inputs; the words are its to choose, the instants are not.
- **Anyone adding a bind path** — there is one protocol (§3.3) and it starts with `lease.claim()`.
  A path that builds a `FleetLogin` without it is the review finding that reopens #295's P0-1 one
  layer up.
