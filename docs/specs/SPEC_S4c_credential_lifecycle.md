# SPEC S4c — the credential lifecycle: the daily ping, `self-login` renewal, and the per-credential gate that survives a restart and a second replica (#285)

| | |
|---|---|
| Programme | Cluster configuration as labelled Secrets (#230), continued — S4 designed the retrieval; S4a shipped the login; S4b shipped the lookup; this is step C, the only part that runs on a clock |
| Batch | S — cluster configuration |
| Release | — (post-programme; S4 step C, the issue's own label S3b-C) |
| Version on release | app 0.38.0, chart 0.59.0 |
| Issue | [#285](https://github.com/ephico2real2/group-sync-dashboard/issues/285) |
| Status | specified |
| Source | OB1's design specification of 2026-09-22, written before any code from the business owner's brief, the issue and its eight comments (the fixed-margin correction, the 401 ambiguity, the retraction on the one-year fuse, the inherited replica requirement), `docs/specs/SPEC_S4_token_retrieval.md` §3.1, §6 and §9, `docs/specs/SPEC_S4b_sa_token_lookup.md` (orchestrator's notes R2-5 and R3-2, §6), the review record `docs/REVIEW_S4b.md` ("What is NOT held"), the upstream sources cited in §2, and the reference cluster measured read-only on 2026-09-22. Brought to main `f82a065` on 2026-09-26 by OB3 (#285, the implementer's brief): the reference cluster re-measured read-only, the body corrected where it had stopped being true (Orchestrator's notes), and §8's implementation blocks cut from a copy of `f82a065` with the design implemented and applied back to a clean clone for the proof in §8.1 |

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
- **#315 ships B2's in-memory half first** (`docs/specs/SPEC_S4d_credential_gate_per_account.md`):
  `CredentialGate` holds a refused kind, keyed on (account, digest) and written by every bound answer with
  the answering target as evidence, and a spent kind, #293's per-target success mark (SPEC_S5 §3.3). §3.3's
  cache paragraph now names the refused kind as what `FleetRecord.refused` seeds, leaves the spent kind
  off the Lease, and quotes the docstring sentence #315 wrote, which is the one this spec replaces.
  "Account" there is the exact configured username string (SPEC_S4d §3.3); the Lease inherits that key.
- **Brought to main `f82a065` and given its implementation blocks (#285, 2026-09-26, OB3 as implementer).** The
  body stays verbatim where it is still true; each sentence changed is named in the bullets below with its reason,
  and §8 is the whole change as implementation blocks, in apply order — cut from a copy of `f82a065` with the design
  implemented, and applied back to a clean clone of `f82a065` for the proof in §8.1. §2 was re-measured read-only on
  the reference cluster on 2026-09-26 (`oc get` only, full resource names). Unchanged: `oauths.config.openshift.io/cluster`
  states `{"accessTokenMaxAgeSeconds":31536000}`; `oauthclients.oauth.openshift.io/openshift-challenging-client` has
  both timeouts null; the fleet account holds the same two `openshift-challenging-client` tokens of 2026-09-19; the
  ClusterRole's `coordination.k8s.io` rule is still `leases: get, create, update` with no `resourceNames`; the
  release still runs one replica, `Recreate`, election on, and `leases.coordination.k8s.io` in the namespace lists
  the elector's and grafana-operator's only — no `gsd-fleet-*` Lease. Moved: the image is
  `quay.io/ephico2real/group-sync-dashboard:0.37.0`; `gsd-cluster-shared-rnd` is at `resourceVersion` 2835139
  (§2.4's 2029578 predates later rewrites of that Secret; the walk in §3.12 records its own starting number);
  `developer` holds three `openshift-challenging-client` tokens. New, and it decides the digest below: the stock
  ClusterRoles on the lab grant `view` nothing on `coordination.k8s.io`, `edit` and `admin` every verb on `leases`,
  and `cluster-reader` `get, list, watch` on them — so `cluster-reader` reads a fleet account's Lease and cannot read
  the password Secret in `openshift-config`.
- **The versions, corrected** (the bullet above, §3.7's table and §3.13). The ladder moved past every rung the body
  names: SPEC_S5 (#293), #368, SPEC_T2 (#322), SPEC_L1 (#321), Epic B (app 0.37.0, chart 0.58.5), #413 (0.58.6),
  SPEC_S4d (#315, 0.58.7) and #415 (0.58.8) took them. S4d's precedent applies, since releases are cut per epic by
  `local-development/prepare-release.py`: the implementing pull request bumps the chart to **0.59.0** (MINOR: two new
  values), and the application code has no version of its own — it rides Epic C's release, **app 0.38.0**, the pair
  the header and the index already carry. `pyproject.toml`, `gsd/__init__.py` and `appVersion` are not touched.
- **The cadence, corrected** (§3.4, twice). Since #368 the discovery thread waits `discovery_interval_seconds`
  (`discoveryIntervalSeconds`, 300 s by default; `gsd/poller.py#Poller._run_discovery`), not the binding interval
  (3600 s): "on the binding cadence" and "one GET per account per `bindingIntervalSeconds`" now name the discovery
  cadence.
- **How the Lease's entry relates to S4d's `CredentialGate`** (§3.3's cache paragraph, restated exactly). The gate
  holds two kinds (#315): REFUSED, keyed on (the exact configured username, sha256(password)[:16]) and gating every
  target; SPENT, keyed on (canonical target, username, digest) and written only by #293's success mark. The Lease
  holds ONE `refused` entry per account and nothing else of the gate. Every bind path claims the Lease first; the
  Lease's entry, when its digest is this password's, SEEDS the refused kind (`CredentialGate.refuse` with the answering
  target as evidence), and a bound answer is written to the Lease BEFORE the refused kind — so the Lease EXTENDS the
  refused half across restarts and replicas. The spent kind is never read from or written to the Lease: a success
  releases the claim with a stale entry for another password removed and records nothing. The daily ping logs in
  with `onboarding=()`, so it never writes the spent mark either. `test_293s_success_mark_stays_per_target_and_off_the_lease`
  holds both: two successful ConfigMap onboardings on one account are two authorizes with the Lease in the loop, the
  Lease carries no `refused` entry after them, a restart with the output missing binds once more (#293's row, unchanged),
  and a ping of an onboarded cluster leaves the spent kind empty.
- **#291, #293, #315 and #415, accounted for.** #291 consolidated `FleetLogin`'s failure writers; every name this spec
  cites in `gsd/fleetlogin.py` still exists, and no block touches the file (#283's rules hold by construction: every
  login is a `FleetLogin` context manager, and a 401 on the revoke is still "not proven gone" — R7 asserts the line).
  #293's budget table (SPEC_S5 §3.3) is stated per canonical target and per process, and every row is unchanged; the
  Lease adds no row to it (it removes the rebind of a *bound failure* after a restart, which the table never
  counted). #315 is the in-memory half this spec's Lease seeds (above). #415 refuses userinfo, a query and a fragment
  in a values `apiUrl` at render and at load, as the Secret contract already did for `server`, so the `target` a
  Lease entry keeps as evidence cannot carry a URL credential; the API and the lines show it through
  `gsd/fleetlogin.py#_without_userinfo` regardless.
- **Implementation deviations — each found while implementing, each decided on the reason given.**
  - *The Lease's digest is salted and slow* (§3.3's YAML and the gate paragraph): `lease_digest` is scrypt salted with
    the account at the OWASP Password Storage Cheat Sheet's 16 MiB setting (N=2^14, r=8, p=5; measured 112 ms here,
    once per password per process), 64 bits kept — not the gate's sha256 prefix, which the draft named. The
    measurement above is why: `cluster-reader` reads the Lease and not the password, and a fast unsalted prefix on an
    object it reads is an offline dictionary oracle for the directory's bind password. The in-memory gate keeps its
    sha256 prefix: it never leaves the process.
  - *The client is the host cluster's `ClusterClient`* (§3.3's class docstring), not `LeaderElector._client`: the same
    identity in production — the host stanza's token is the pod's mounted ServiceAccount token — and the one client the
    lookup already writes the cluster Secret with, so the hermetic tests drive the Lease through the fake host every
    lookup test uses. The test fakes gained the Lease resource (`FakeHost` keeps a PUT on a Lease path; `_Host.refuse`
    models the Secret grant and no longer refuses a Lease write), which no assertion depended on.
  - *The caller owns the claim* (§3.3's interface and §3.7). One `FleetLease` per attempt: `read`, `claim`, `refuse`,
    `release`. `claim(read, **changes)` writes against the record a decision rests on, so the ping records its attempt
    WITH its claim (`ping-last-attempt`, `ping-last-target`, `ping-digest`) — B3 across replicas and across a crash,
    atomically — and a success releases with `refused` removed; `note_ping` and `clear_other_digests` are those two
    writes. `lookup(..., lease=None)` takes a claimed Lease: it seeds the gate from it and records a bound answer
    there first; None is the process gate alone, which #284's and #293's own hermetic tests call it with, unchanged.
  - *The re-read before the bind is dropped* (§3.3's step 3, B1, §2.5's table, §4): the claim's compare-and-swap PUT is
    itself the last confirmation, and only the in-memory gate check and the unauthenticated OAuth discovery GET
    separate it from the authorize GET, which a re-read cannot come after (#283's `FleetLogin` owns both requests).
    A re-read would narrow nothing measurable, so B1's residual is restated as the window it is.
  - *`ping-digest` is the password the last ATTEMPT was for*, not the last success (§3.3's YAML, §3.1): read as the
    last success, a password whose ping keeps failing after the login — a revoked `get` grant on the target — would
    be "due" every discovery cadence, one bind per 300 s, and B3 would not hold.
  - *The ping's targets and accounts* (§3.4): a retrieved cluster no longer declares its mode — `store_lookup` strips
    it from a declaring Secret and a generated Secret never had it — so the ping reads the account from the
    `groupsync-dashboard.io/lookup-account` annotation every lookup-written Secret carries (the reader records it as
    `ClusterConfig.lookup_account`, a valid username or nothing) and targets the enabled clusters whose
    `token-source` is `remote-lookup`. Every account in use — those, pending lookups and `userSelfLogin` stanzas — has
    its Lease read each cadence on every replica, so `gsd_fleet_account_suspended` and the tab see a self-login
    account's gate too; only an account with retrieved clusters is pinged.
  - *`self-login` logs in with one attempt per cycle* (§3.6, and §2.2's "165 s", which becomes 30 s): `FleetLogin`'s
    `policy` is `RetryPolicy(attempts=1)` there, because the poll interval is the retry (SPEC_S3 §9.3.1) and #283's
    five attempts inside every cycle would write five `fleet-login-failed` lines a minute for a target that is down.
    §2.2's "⌊900 / 60⌋ = 15 acquisition attempts" for a one-hour session is unchanged.
  - *Clearing an entry by hand* (§5, question 7; §3.4's stand-down line): removing the annotation re-arms the Lease,
    and the running process keeps its own copy in the gate, so the procedure is "remove the annotation and restart
    the pod" — the safe direction, since a Lease read never drops a process's refusal.
  - *Findings and signals* (§3.4, §3.7, §3.9): one registry method holds both new owners' standing findings,
    `ClusterRegistry.set_standing_finding(slot, cluster, finding)` with the slots `ping` and `self-login`, and
    `prune_standing` drops a slot's findings for clusters that left; `RuntimeSignals.note_fleet_accounts` (every
    account's Lease view, replaced each cadence, a failed read keeping its last view) and `note_self_login` replace
    `note_fleet_ping` and `note_fleet_suspended`.
  - *The ERROR row of the chart README's log ladder is not changed* (§3.13): a `fleet-state-unavailable` line is a
    finding's line, WARNING like the lookup's own `fleet-credential-missing` (also a missing grant), written through
    the one `failure()` shape; the row's "Lease RBAC missing" stays the elector's.
  - *A composition the draft predates: `remote-sar` on a self-login cluster.* SPEC_D2b made `remote-sar` the default
    for a remote after this spec was written, and its resolver asks with the cluster's own credential — for a
    self-login cluster the poll thread's session, which the resolver never holds. `gsd/kube.py#RemoteTierResolvers`
    therefore leaves self-login clusters unaskable, exactly as while the mode was pending: their readers get the self
    tier there (fail closed). Letting a resolver ask with the session is not in #285's scope.
  - *The tab's words* (§3.10): the account row says "not yet confirmed by the daily ping" before the first success
    (a self-login-only account is never pinged) and a `suspended` badge while its Lease holds an entry; the words stay
    S3c's to refine.
  - *`self-login-renewed` is said when a session replaces another*; the first session's line is `fleet-login`, which
    already carries its `expires_at`.
  - *The index rule* (§3.11): `test_specs_index.py`'s count is twenty-nine and the S batch's issue set already holds
    #285; what moves is the `specified`-versions rule's `assert "S4c" in checked`, retired, because this change takes
    the chart rung S4c names and records `SPEC_S4c` by name.
  - *The chart's Lease rule* widens its condition in the ClusterRole, as §3.8 specifies. Left to review, stated: a
    namespaced Role would be narrower for the election-off shape; the default shape (election on) already carries the
    same cluster-wide rule, so the election-off shape gains nothing the default install lacks.
- **The release versions** were app 0.32.0, chart 0.53.0 at the review of #325 (all three reviewers): the draft's
  chart 0.51.0 had already shipped (#307), and main was at 0.52.1 (#317). SPEC_D2b's implementation (#338) took
  those two rungs first and SPEC_U1 (#353) the next (app 0.33.0, chart 0.54.0); the rungs after were taken too (the
  first bullet below lists them). This spec carries **app 0.38.0, chart 0.59.0**, the header's and the index's pair.

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

**What the window buys, in this code's own numbers.** One renewal attempt is ONE login attempt
(`gsd/selflogin.py#ONE_ATTEMPT`: the poll interval is the retry, SPEC_S3 §9.3.1) — at most discovery +
authorize = 2 × `requestTimeoutSeconds` = **30 s** at the default — and *binds nothing* unless the
target answers. The renewal is re-attempted once per poll cycle (`pollIntervalSeconds`, 60 s) until
`expires_at`, so a one-hour session has at most ⌊900 / 60⌋ = 15 acquisition attempts in its window —
and the first one the target *answers* is terminal for that (account, password) (§3.2, budget B2). The
window is a budget for *unreachable* targets; a *refusing* target consumes exactly one bind of it.

**The floor the schedule needs.** The renewal check runs on the poll cadence, so a renewal starts at
most one `pollIntervalSeconds` after `renew_at` and must still be before `expires_at`:
`pollIntervalSeconds < lifetime / 4`, i.e. **`expires_in > 4 × pollIntervalSeconds`** (240 s at the
default). A target stating less is refused as a standing finding, not chased (§3.6). Stated
precisely: the floor guarantees the renewal **starts** before expiry; a renewal that then needs the
whole 30 s attempt can still overrun on a session near the floor — that is the *unreachable*
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
| a claim is judged expired **at the same instant** by every pod | `renewTime + duration` against each pod's clock | **no** — skew between pods moves the judgement; a generous duration and a claim written immediately before the bind narrow the window to the OAuth discovery round-trip and never close it |

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
| the durable, replica-shared object | **one Lease per fleet account** in the release namespace: `gsd-fleet-<sha256(username)[:16]>`, labelled `groupsync-dashboard.io/lease-type: fleet-account`, annotated with the account. Its `spec` is the **claim** (who may bind as this account right now); its annotations are the **gate** (which (account, password) must not be presented again, from whichever target answered; the target is evidence, not the key) and the **ping's bookkeeping** (last attempt, last ok, last outcome, last target, and the password the last attempt was for) |
| who takes the claim | every code path that can put the password on the wire: #284's lookup, this spec's ping, a `self-login` acquisition or renewal. **No claim, no bind** — fail closed |
| the daily ping | `fleetlookup.lookup(cluster, settings, host_client, own_namespace=…, gate=…, write=False, lease=…)` against **one** target per account per cadence, on the discovery thread, leader only; the result is read for `sa_token.last_used` and dropped; the login's token is revoked by the session |
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
  expired and re-taken — one extra bind per pause, never a walk. The claim's own compare-and-swap is
  written immediately before the bind: only the in-memory gate and the OAuth discovery GET lie between it
  and the authorize GET. When the paused holder resumes, its bound answer is re-applied to the Lease as
  it now is and the claim that took over is left standing.
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
  replicas and restarts.** *Held by* `ping-last-attempt` and `ping-digest` on the Lease, written WITH
  the claim, on the read the decision rests on (a 409 means another replica decided first). Twenty clusters on one account are one bind, because the ping is keyed on the account
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
    # `digest` is 64 bits of scrypt salted with the account (`gsd/fleetstate.py#lease_digest`), NOT the
    # sha256 prefix CredentialGate keeps in memory: cluster-reader reads Leases (R3-2's rule holds: a
    # collision over-blocks, never binds). A rotated password is a different digest and does not match.
    groupsync-dashboard.io/refused: '{"digest": "9f2a…", "at": "2026-09-22T14:03:11Z", "code": "login-refused", "target": "https://api.crc.testing:6443"}'
    # THE PING'S BOOKKEEPING — instants, never ages.
    groupsync-dashboard.io/ping-last-attempt: "2026-09-22T06:00:04Z"
    groupsync-dashboard.io/ping-last-ok: "2026-09-22T06:00:05Z"
    groupsync-dashboard.io/ping-last-outcome: ok          # ok | <a finding code>
    groupsync-dashboard.io/ping-last-target: shared-rnd
    groupsync-dashboard.io/ping-digest: "9f2a…"           # the password the last ATTEMPT was for (B3)
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

The interface, signature-level (the whole module is small; §8 carries it whole):

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
    """One attempt's handle on an account's Lease, through the host cluster's ClusterClient — the pod's
    own ServiceAccount, the client the lookup writes the cluster Secret with. The caller owns the claim;
    never shared between threads. A write that meets a 409 is re-read and re-applied, at most three
    times, then FleetStateUnavailable."""

    def __init__(self, host: ClusterClient, namespace: str, account: str, *, claim_seconds: int,
                 identity: str | None = None, clock=None): ...
    def read(self) -> FleetRecord: ...
    def claim(self, read: FleetRecord | None = None, **changes) -> FleetRecord:
        """ONE write with the resourceVersion of `read` (the record a decision rests on) or of a fresh
        read: a live claim — anyone's, this process's included — or a 409 is ClaimHeld (a free,
        silent outcome). `changes` ride the same write: the ping's attempt is recorded with its claim."""
    def refuse(self, target: str, digest: str, code: str) -> None:
        """The account entry, one CAS write while holding; `target` is evidence, not the key. Never raises."""
    def release(self, **changes) -> FleetRecord | None:
        """holder="" with any last changes (`refused=None` after a success retires an older password's
        entry); never clears a claim that was taken meanwhile; never raises."""


class ClaimHeld(Exception):
    """Another holder's claim is live, or the Lease changed since the read. Not a failure: next cycle."""


def lease_digest(account: str, password: str) -> str:
    """scrypt(password, salt=account, N=2^14, r=8, p=5), 64 bits — the Lease's fingerprint."""


def claim_seconds(settings) -> int:
    """The acquisition budget, computed from the settings the login runs under and never a magic
    number: RETRY_POLICY.attempts × 2 × requestTimeoutSeconds (discovery + authorize) + the policy's
    total backoff + 2 × requestTimeoutSeconds (the read and the revoke), floored at 60."""
```

**The protocol every bind path follows, in this order and no other:**

1. `record = lease.claim()` — CAS; `ClaimHeld` → stop, silently, try next cycle.
2. `record.gated(lease_digest(account, password))` — the account entry, the same rule on every path
   (B2): when it matches, it SEEDS the process's gate (`CredentialGate.refuse`, the answering target as
   evidence), and the process's gate is asked as it is today → a gated credential is a free refusal
   (`LookupRefused(..., gated=True)`, R3-2's shape), said once with `gave_up=true`, and the claim is released.
3. *(The draft's re-read of the Lease here is dropped — Orchestrator's notes: the claim's own
   compare-and-swap is the last confirmation, written immediately before the bind.)*
4. Bind: build `FleetLogin` (`gsd/fleetlogin.py#FleetLogin`), run the caller's body.
5. On `LoginError.bound` → `lease.refuse(target, digest, code)` — the account entry,
   with the answering target as evidence — **before** the finding is raised — the durable write comes first, the in-memory `CredentialGate.refuse` second, so a crash
   between the two loses the cheap copy, never the durable one.
6. `lease.release()` in a `finally` — with `refused=None` after a success, which retires an entry an
   older password left.

`gsd/fleetlookup.py#CredentialGate` stays as the **cache**, and the relation is exact. Its REFUSED kind is
keyed on (the exact configured username, sha256(password)[:16]) and gates every target (#315,
`docs/specs/SPEC_S4d_credential_gate_per_account.md`); its SPENT kind is keyed on (canonical target,
username, digest) and is written only by #293's success mark (SPEC_S5 §3.3). The Lease holds one
`refused` entry per account and nothing else of the gate: it SEEDS the refused kind whenever a bind path
claims it (step 2) and EXTENDS it across restarts and replicas (step 5 writes the Lease first). The
spent kind is never read from or written to the Lease — a success records nothing there — so #293's
per-target success mark never becomes an account-wide refusal. Its docstring's sentence *"A restart or a
second replica starts empty — not covered until #285's account Lease, which this becomes the cache of
(SPEC_S4c §3.3)"* is replaced by "It is the cache of the account Lease's gate (SPEC_S4c §3.3): every bind
path claims the Lease first and seeds the REFUSED kind from the Lease's entry, and a bound answer is
written to the Lease before it is written here — so a restart and a second replica read it while the
Lease is writable, and this is the only copy when it is not. The SPENT kind is never on the Lease."

**Fail closed, and what it looks like.** `FleetStateUnavailable` on `claim()` or `refuse()` is the
finding `fleet-state-unavailable` (free, announced on transition, rechecked every cycle), with
`action=` naming the grant — *grant get/create/update on coordination.k8s.io/leases in <namespace> to
<serviceaccount> (the chart renders it under leaderElection.enabled or a fleet account in use)* — and
**no bind is attempted** by the lookup, the ping or a `self-login` acquisition while it stands. The
asymmetry decides it: a missed login while RBAC is fixed is one stale cluster; a bind without the
gate is the walk this object exists to stop.

### 3.4 The daily ping — on the discovery thread, after the lookups

`gsd/poller.py#Poller._run_discovery` already runs `_discover_once → _reconcile_threads →
_retrieve_pending` on the discovery cadence (`discoveryIntervalSeconds`, 300 s by default — its own timer
since #368, no longer the binding interval); `_ping_accounts()` runs after `_retrieve_pending`, binds on
the leader only, and is a loop over **accounts**, not clusters:

```python
def _ping_accounts(self) -> None:
    """One real read per fleet account per cadence (SPEC_S4c §3.4) — the daily ping. Every account in use
    has its Lease read each cadence, on every replica; an account whose clusters the lookup retrieved is
    pinged against ONE of them — the `lookup-account` their Secrets record, in rotation by name —
    through `lookup(write=False)` under the account Lease's claim, by the leader alone."""
```

- **Which target.** The enabled clusters the lookup retrieved — `token-source: remote-lookup` — whose
  Secrets record the account as `groupsync-dashboard.io/lookup-account` (retrieval strips the mode keys, so
  that annotation is where the account survives; a `self-login` cluster confirms the account every renewal
  and needs no ping), ordered by
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
  action="not pinged again until the fleet password Secret changes, or the entry on Lease
  gsd-fleet-… is removed and the pod restarted; the gate is re-read every cycle at no cost"`. §5.2 records the cost of
  this choice.
- **What it writes.** Nothing on the host but the Lease's ping annotations (one CAS PUT) — the
  cluster Secret is not touched, and the walk in §3.12 asserts its `resourceVersion` before and after.
  The `LookupResult` is read for `sa_token.last_used` and `account`, then dropped; the token it carried
  rides the result's `secrets` into the event helper's redaction and is never held.
- **What it says.** `fleet-ping account=<u> target=<cluster> last_used=<label> last_ok=<ISO>` on
  success; `fleet-ping-failed phase=credential outcome=<code> account=<u> target=<cluster>
  attempt=1/1 …` on a spent failure — one attempt, no backoff: the next ping is the next cadence, and
  a bound answer is gated anyway. The finding is held on the registry against the target in a slot
  of its own — `ClusterRegistry.set_standing_finding("ping", …)`, merged into `findings()` beside `_lookups` — and
  **not** through `gsd/clusterconfig/registry.py#ClusterRegistry.set_lookup_finding`: `_retrieve_pending`
  clears the lookup slot for every cluster it stops tracking, each cycle, and a cluster that re-enters
  pending would overwrite it. Two slots, two owners, one card: the Findings card names the cluster
  the next lookup would fail on.
- **The instant.** `ping-last-ok` is copied into `RuntimeSignals` (§3.9) and served by the API
  (§3.10) as it is on the Lease — an ISO-8601 UTC instant. Never an age in a server string
  (`absolute-instants-in-server-text`, the operator's ruling).

**Restart, and standbys.** On `start()`, the discovery thread is woken at once, and **every** replica
reads every account's Lease (`FleetLease.read`, no claim) into `RuntimeSignals`, and re-reads them on every
discovery cadence (one GET per account per `discoveryIntervalSeconds`, no claim, no write) — so
`/metrics` and the tab serve the same instant on a standby as on the leader. The process's gate is seeded
from the Lease whenever a bind path claims it, so a refused password is refused from the first attempt
after a restart, and only the leader ever writes.

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
class _Session:
    login: FleetLogin                    # entered; its __exit__ is the revoke
    session: FleetSession                # token, expires_at, issuer
    account: str
    key: tuple                           # (account, the password's sha256 prefix, the cluster's URL) at login
    renew_at: datetime                   # expires_at - min(2 h, expires_in / 4)   (SPEC_S4 §3.1)
    reauth: bool = False                 # a poll answered 401 before expires_at: re-authenticate next cycle
    reauth_logins: int = 0               # B4: at most two per episode

class SelfLoginSessions:
    """Process-wide, one lock (the ClusterRegistry shape the issue asked for); it reads the poller it
    belongs to — settings, store, gate, signals, host client — each time, never a copy. The poll thread
    asks `credential_for(cluster)` before each poll and tells `poll_answered(cluster, outcome)` after."""
    def credential_for(self, cluster) -> ClusterConfig | None:
        """The cluster as it polls — the session's token substituted, acquiring or renewing first when
        due — or None when the cluster is suspended or has no session this cycle (the poll is skipped,
        not failed)."""
    def poll_answered(self, cluster, outcome: str) -> None: ...
    def stop(self, name: str) -> None:
        """Exit the session (revoke) — the cluster was disabled, retired, or its thread is stopping."""
    def _suspend(self, cluster, account, key, *, code, target, detail, secrets) -> None:
        """Every self-login cluster on this account: stopped, parked, its finding set; one line."""
```

**Acquisition** (first cycle, and every renewal) runs §3.3's protocol against the account's Lease —
`gated(digest)`, the account entry every path reads (B2): a failure written by any target parks
this acquisition too, after a restart and on another replica alike (R2-1 is reversed by the operator's
ruling, Orchestrator's notes) — then `FleetLogin(cluster, account, password, timeout=…, policy=ONE_ATTEMPT).__enter__()`
— one attempt, because the poll interval is the retry (SPEC_S3 §9.3.1). On success the
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

**Suspension.** A bound failure on any `self-login` acquisition for account *A* — or a gate entry
for *A*'s password met by one — calls `_suspend` for *A*: every `self-login` cluster on *A* has its session exited (revoked), its thread
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
| `gsd/fleetlookup.py` | `lookup()` gains `lease`, a `FleetLease` its caller has claimed: the Lease's entry seeds the gate, and a bound answer is recorded there before the gate (§3.3, steps 2 and 5); `CredentialGate` becomes the seeded cache (its docstring); `LookupRefused` gains nothing — `FleetStateUnavailable` carries its fields (§3.3) |
| `gsd/poller.py` | `_ping_accounts()`; `_retrieve_pending()` claims the account's `FleetLease` around `lookup()`; `_run_cluster` consults `SelfLoginSessions` before `poll_once` and reports after it, and stops the session on the thread's way out; `start()` wakes discovery for the Lease reads and no longer skips `self-login`; `_reconcile_threads` likewise |
| `gsd/config.py` | `fleet_ping_enabled`, `fleet_ping_interval_seconds`; `CREDENTIAL_PENDING_REASONS` drops `self-login`; `resolve_token()`'s message for the mode; `ClusterConfig.lookup_account` |
| `gsd/clusterconfig/reader.py` | records a lookup-written Secret's `lookup-account` annotation on the cluster (§3.4) |
| `gsd/kube.py` | `RemoteTierResolvers` leaves a self-login cluster unaskable, as while it was pending (Orchestrator's notes) |
| `gsd/clusterconfig/__init__.py` | the three codes join `FINDING_CODES` |
| `gsd/clusterconfig/registry.py` | `set_standing_finding(slot, cluster, finding)` and `prune_standing` — the ping's and self-login's own standing slots, merged into `findings()` (§3.4) |
| `gsd/metrics.py` | the three families of §3.9; `RuntimeSignals.note_fleet_accounts`, `note_self_login` |
| `gsd/api.py` | the `fleet` block and the per-cluster `session` block on `/api/clusterconfigs` (§3.10) |
| `gsd/static/index.html` | the two rows (§3.10) |
| `charts/…/values.yaml`, `templates/configmap.yaml` | `clusterConfig.fleetAccount.ping.{enabled, intervalSeconds}` → `fleetPingEnabled`, `fleetPingIntervalSeconds` |
| `charts/…/templates/rbac.yaml`, `templates/_helpers.tpl` | the Lease grant's condition; `gsd.fleetAccountInUse` shared with `fleet-account-rbac.yaml`; `userSelfLogin` with `replicaCount > 1` refused |
| `charts/…/Chart.yaml` | chart 0.59.0 (MINOR: two new values); the application code has no version of its own and rides Epic C's release, app 0.38.0 — `pyproject.toml`, `gsd/__init__.py` and `appVersion` are not touched (S4d's precedent) |
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
<username> · last confirmed <instant> on <target> · <outcome>`, `not yet confirmed by the daily ping`
before the first success, and a `suspended` badge while the account's Lease holds an entry; and on a
`self-login` cluster's credential row
`self-login · expires <instant>`. That is all; the provenance card and its words are S3c's.

### 3.11 Tests — what fails before and passes after

`local-development/tests/test_fleet_lifecycle.py` (new), on the harness `test_fleet_lookup.py` ships
(`LookupTarget`, `FakeHost`, the `wire` fixture, an injected clock) plus a **fake Lease API** on the
host: `LeaseAPI`, behind `LeaseHost._get`/`_send`, answers the `coordination.k8s.io` paths, enforces the
CAS (a PUT whose `resourceVersion` is not the current one answers 409), and counts every write; one
`LeaseAPI` behind two pollers is one API server behind two processes. §8.1 maps each test below to its
result before and after.

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
- **#293:** `test_293s_success_mark_stays_per_target_and_off_the_lease` — two successful ConfigMap
  onboardings on one account are two authorizes with the Lease in the loop; the Lease records no refusal;
  a restart with the output missing binds once more; the ping writes no success mark.
- **Index:** `test_specs_index.py` — its count (twenty-nine) and its S-batch issue set already hold S4c;
  the `specified`-versions rule's `assert "S4c" in checked` is retired, since this change takes the chart
  rung S4c names.

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
- `charts/group-sync-dashboard/Chart.yaml` — `# CHART 0.59.0 (…), MINOR:` history line; `version`
  (`appVersion` is not touched: the application code rides Epic C's release).
- `charts/group-sync-dashboard/README.md` — the two values rows; the conditional-rules paragraph
  (§3.8). The log-level ladder is not changed (Orchestrator's notes).
- `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md` — the refusal on the Lease, the daily ping as the
  fleet account's one later use, and the `userSelfLogin` row; `docs/polling-and-discovery.md` — which modes
  bind; `docs/DESIGN_cluster_connection_flows.md` — the ping's and self-login's lines;
  `local-development/API.md` — the `fleet` and `session` blocks.
- `docs/CLUSTER_STANZA.md` — the `userSelfLogin: true` row of the credential-kind table (from *no —
  pending*) and case 7 (`remote + userSelfLogin`, from *listed, pending, not polled*) to *polled on its
  own session; renewed a fixed margin before expiry*; `local-development/tests/test_cluster_stanza_matrix.py`
  is what fails when the document stops being true.
- `docs/specs/README.md` — the S4c row, moved to `merged` by hand in the implementing commit with this
  header's Status (a block cannot: its Old text would also match inside its own fence);
  `local-development/tests/test_specs_index.py` — the rule named in §3.11.
- `gsd/fleetlookup.py#CredentialGate` docstring — the sentence in §3.3.

## 4. Failure modes, enumerated

| situation | what happens | budget |
|---|---|---|
| **pod restart mid-window** (a claim was held) | the new pod GETs the Lease: the old claim is live until `renewTime + claim_seconds` (≤ 195 s at defaults) → `ClaimHeld`, silent, next cycle. The gate and the ping instants are on the object, so nothing is re-bound and nothing is re-pinged | B1, B2, B3 |
| **two replicas** (a hand `scale`, a rollover's overlap, a partition, someone's HPA) | both read the gate; both try the CAS; one 409s and stands down. The render refuses the shapes it can see (§3.8); the claim covers the rest | B1 |
| **a paused winner** (GC, throttling) past `claim_seconds` | the claim is judged expired and re-taken; the paused pod's bind may still go out when it resumes — one extra bind, never a walk, because its answer is re-applied to the Lease and gated like any other, and the claim that took over is left standing | B1's stated residual |
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
   password rotates or an operator clears the entry — `oc annotate leases.coordination.k8s.io
   gsd-fleet-<…> -n <ns> groupsync-dashboard.io/refused-`, then a restart of the dashboard pod, which
   keeps its own copy in the gate — which the runbook (#316) must carry. *To settle whether a narrower
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

## 8. Implementation blocks

The whole of #285's step 3 as implementation blocks (`docs/specs/README.md`, "Implementation blocks"), in apply
order, cut from a copy of main `f82a065` with the design implemented and applied back to a clean clone of `f82a065`
for the proof below:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_S4c_credential_lifecycle.md . --apply

This spec's own Status, and its row in `docs/specs/README.md`, move to `merged` by hand in the implementing commit,
beside the applied blocks — a block cannot, because its Old text would also match inside its own fence — so that
`local-development/prepare-release.py` promotes them with Epic C's release.

### 8.1 Tests, before and after

"Before" is `f82a065` plus this section's test blocks only (the eleven blocks under `local-development/tests/`);
"after" is `f82a065` with every block applied. Run from `local-development/` with `PYTHONPATH=.` (the venv's editable
install points at another checkout), `-p no:cacheprovider`.

| Definition of Done | test | before | after |
|---|---|---|---|
| R1: two processes cannot both win one claim; no claim, no bind | `test_fleet_lifecycle.py::test_r1_two_processes_cannot_both_win_one_claim_and_no_claim_is_no_bind` | ERROR at collection: `ModuleNotFoundError: No module named 'gsd.fleetstate'` (every test in the file) | passed |
| B1's residual: a paused holder's refusal is recorded, the claim that took over stands | `…::test_r1_a_paused_holders_refusal_is_recorded_and_it_never_clears_the_claim_that_took_over` | ERROR (the same) | passed |
| authorize count 1 across two processes, three targets, a restart and an irrelevant edit (401 and 500) | `…::test_r2_the_budget_over_the_system_one_authorize_across_two_processes_three_targets_a_restart_and_an_edit[401]`, `[500]` | ERROR (the same); the same scenario measured on `f82a065` without the Lease: 4 authorizes (§8.2) | passed |
| the Lease's fingerprint is salted and slow | `…::test_r2_the_lease_digest_is_salted_and_slow_not_the_gates_prefix` | ERROR (the same) | passed |
| #293's success mark is not turned into an account-wide refusal | `…::test_293s_success_mark_stays_per_target_and_off_the_lease` | ERROR (the same) | passed |
| R3: twenty clusters, one ping a cadence, rotation by name, a restart, a rotated password once (a failing read too) | `…::test_r3_twenty_clusters_on_one_account_are_one_ping_a_cadence_rotating_by_name` | ERROR (the same) | passed |
| R4: the ping stands down on either code, said once | `…::test_r4_a_gated_account_is_not_pinged_and_is_said_once[login-refused]`, `[login-failed]` | ERROR (the same) | passed |
| R5: the margin, with an injected clock | `…::test_r5_renewal_is_a_fixed_margin_before_expiry[3600-2700]`, `[86400-79200]`, `[31536000-31528800]` | ERROR (the same) | passed |
| R5: a session too short to renew is not chased | `…::test_r5_a_session_too_short_to_renew_is_not_chased` | ERROR (the same) | passed |
| R6: the new login is answered before the old token's revoke; unreachable keeps the session | `…::test_r6_renewal_answers_the_new_login_before_the_old_token_is_revoked` | ERROR (the same) | passed |
| R6: a bound failure suspends every self-login cluster on the account, `stopped=2` | `…::test_r6_a_bound_failure_suspends_every_self_login_cluster_on_the_account[401]`, `[500]` | ERROR (the same) | passed |
| R7: the 401 rule, and #283's revoke-side reading kept | `…::test_r7_a_401_before_expiry_reauthenticates_once_and_a_second_suspends` | ERROR (the same) | passed |
| R8: fail closed on every path, said once | `…::test_r8_an_unreadable_lease_binds_nothing_on_any_path_and_is_said_once` | ERROR (the same) | passed |
| R9: no password or token in any new event | `…::test_r9_every_new_event_carries_no_password_and_no_token` | ERROR (the same) | passed |
| the metric families: unlabelled, absent until true | `…::test_the_fleet_families_are_unlabelled_and_absent_until_a_ping_succeeds` | ERROR (the same) | passed |
| the API's `fleet` and `session` blocks | `…::test_the_api_serves_the_fleet_block_and_a_self_login_session_as_instants` | ERROR (the same) | passed |
| the three codes in the closed set; `claim_seconds` computed | `…::test_the_new_codes_join_the_closed_set_and_claim_seconds_is_computed` | ERROR (the same) | passed |
| the `CredentialGate` docstring names the Lease | `…::test_the_gate_docstring_names_the_lease_as_its_durable_half` | ERROR (the same) | passed |
| the chart: the ping's values in the ConfigMap | `test_chart_connection_modes.py::TestTheCredentialLifecycleInTheChart::test_the_ping_values_reach_the_configmap` | FAILED `KeyError: 'fleetPingEnabled'` | passed |
| the chart: `userSelfLogin` above one replica refused by name | `…::test_self_login_above_one_replica_is_refused_by_name` | FAILED (rendered) | passed |
| the chart: the Lease rule where a claim is needed; the only write stays a Lease | `…::test_the_lease_rule_renders_where_a_claim_is_needed_and_stays_the_only_write[mode-in-use-election-off]`, `[username-election-off]` | FAILED (no `leases` rule) | passed |
| the same, the guards | `…[no-account-election-off]`, `[election-on]` | passed | passed |
| self-login is no longer pending | `test_connection_modes.py::TestTheLoader::test_a_stanza_declaring_a_mode_loads_without_a_credential[userSelfLogin-self-login-False]` | FAILED `assert True is False` — `credential_pending` still says "the self-login mode is S3b's #285, not built" | passed |
| a Secret-declared self-login cluster starts a thread and polls only on a session | `test_connection_modes.py::TestThePollPath::test_a_secret_declaring_self_login_is_discovered_listed_and_polled_only_on_a_session` | FAILED: no `fleet-credential-missing` finding within 5 s — the cluster is still pending, so no thread starts | passed |
| the tab's two rows, at 375 px | `test_ui.py::TestClusterConfigPage::test_the_fleet_account_rows_and_a_self_login_expiry_are_instants` | FAILED `AttributeError: 'RuntimeSignals' object has no attribute 'note_fleet_accounts'` | passed |
| the index rule's retired pin | `test_specs_index.py::test_a_spec_the_changelog_has_not_begun_names_versions_the_tree_has_not_reached` | passed (unchanged, it passes on `f82a065`); the original test FAILS on the applied tree | passed |
| harness only: the Lease needs the fake host | `test_fleet_lookup.py::TestTheSchedule::test_a_spent_failure_backs_off_and_gives_up_out_loud`, `…::test_success_clears_the_finding_and_wakes_discovery` | passed | passed; without the added line, FAILED `fleet-state-unavailable` (the Lease read went to a real client) |
| harness only: `_Host.refuse` models the Secret grant | `test_configmap_onboarding.py::test_values_bind_budget_is_unchanged[write-failure]`, `test_configmap_bind_budget_through_the_poller[write-failure]` (#293's table, unchanged) | passed | passed; with `refuse` on the Lease too, FAILED (no bind) |

The whole suite, `pytest tests/ -q --deselect tests/test_live_smoke.py`, browser tests included: on `f82a065`,
`5913 passed, 19 skipped, 4 deselected, 2 warnings in 467.71s`; with every block applied (this spec in the tree),
`5969 passed, 19 skipped, 4 deselected, 2 warnings in 471.25s`. `helm lint` passes for the default values and each of
the three values files below, and `helm template` renders all eight renders of §8.3.

Twelve design decisions were each reverted in the implemented copy and the tests above run against the mutant; all
twelve were caught: the paused holder clearing the claim that took over; the ping writing #293's success mark; the
ping recording no password per attempt; the lookup not seeding the gate from the Lease; the lookup not recording a
bound answer on the Lease; the Lease keeping the gate's sha256 prefix; the ping not standing down; the lookup binding
without a claim; renewal at 80 % of the lifetime; a second 401 logging in again; a bound failure suspending only its
own cluster; an unreadable Lease still letting the lookup bind.

### 8.2 The budget over the system

One wrong (401) or locked (500) password on one account, three `saTokenLookup` stanzas, measured in authorize
requests by the hermetic harness (a wire mock counts requests, not directory binds); each later shape is a new
`Poller` — its own in-memory gate — over the same fake API server. Before is `f82a065` (the same scenario, with the
Lease resource answered if asked, which that tree never does); after is every block applied
(`test_r2_the_budget_over_the_system…`).

| shape | before (`f82a065`), 401 and 500 alike | after |
|---|---|---|
| one process, three targets | 1 | **1** |
| + a second replica | +1 | **+0** |
| + a restart | +1 | **+0** |
| + an irrelevant config edit (`visibility`) | +1 | **+0** |
| total | 4 | **1** |
| + a rotated password | — | +1, and its success retires the old entry |

The ping, measured by `test_r3…`: twenty retrieved clusters on one account are ONE authorize per interval, a restart
inside the interval adds none, and a rotated password is confirmed once — once, too, while its read keeps failing.
#293's table (SPEC_S5 §3.3), stated per canonical target and per process, is unchanged row by row: the Lease adds no
row to it and removes only the rebind of a *bound failure* after a restart, which that table never counted.

### 8.3 RBAC, rendered before and after

Every Role, ClusterRole and binding the chart renders, as atoms (one verb on one resource, one subject on one role),
from `f82a065` and from the applied tree, with `-n group-sync-dashboard`, for the default values,
`environments/crc.yaml`, `environments/example-production.yaml` and `charts/group-sync-dashboard/example-production.yaml`,
each with election on and off. REMOVED is 0 in all eight renders. ADDED is the `leases` rule — `get`, `create`,
`update` on `coordination.k8s.io/leases` in the reader ClusterRole, 3 atoms — in exactly the two renders where
election is off and a fleet account is in use (`crc`, and the chart's production example); 0 elsewhere.
`test_the_only_write_in_the_role_is_the_dashboards_own_lease` passes unchanged.

### 8.4 The blocks

<!-- block: local-development/gsd/fleetstate.py | create -->
```python
"""The fleet account's Lease: the claim every bind path takes, the durable half of the credential gate, and
the daily ping's bookkeeping (#285, SPEC_S4c §3.3).

ONE Lease per fleet account in the release namespace, `gsd-fleet-<sha256(username)[:16]>`:

  spec         the CLAIM — who may put this account's password on the wire right now
  annotations  the GATE — `refused`, ONE entry per account: the last answered failure for one password, the
               target that answered kept as evidence, never as the key (#315: a lockout is per directory
               account) — and the PING's instants

WHAT A LEASE GUARANTEES, from the documents that define it. The Kubernetes API conventions ("Concurrency
Control and Consistency"): a PUT carrying the resourceVersion just read fails with 409 when the object
changed since, and the client's duty is to "GET the resource again, apply the changes afresh, and try
submitting again". So two processes cannot both win one claim, whatever their clocks — the API server
arbitrates. What it CANNOT be is a fence: client-go's leaderelection package says so of itself ("does not
guarantee that only one client is acting as a leader"), and a holder paused past the claim's duration can
still bind after another process took the claim over. SPEC_S4c §3.2 states that residual (B1); nothing here
claims it away.

FAIL CLOSED. A Lease that cannot be read or written is `FleetStateUnavailable`, and no path binds without
its claim: a missed login while the RBAC is fixed is one stale cluster; a bind without the gate is the
lockout walk this object exists to stop (SPEC_S4a §3.1's asymmetry).

THE CALLER OWNS THE CLAIM. One `FleetLease` per attempt: `claim()` holds it, `refuse()` records a bound
failure while holding it, `release()` lets it go — so the ping's due-ness is decided on the read its claim
writes against, and nothing here is shared between threads.
"""

from __future__ import annotations

import copy
import hashlib
import json
import logging
import math
import os
import socket
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from .clusterconfig.events import failure
from .fleetlogin import RETRY_POLICY
from .kube import ClusterClient, ClusterError
from .leader import LEASE_API

log = logging.getLogger(__name__)

PREFIX = "groupsync-dashboard.io/"
LEASE_TYPE_LABEL = PREFIX + "lease-type"
LEASE_TYPE = "fleet-account"
#: The instants this module writes: fixed-width UTC, `gsd/timeutil.py`'s stamp — never an age.
STAMP = "%Y-%m-%dT%H:%M:%SZ"
#: A write that met a 409 is re-read and re-applied at most this many times (the API conventions' duty).
CAS_TRIES = 3
#: The action every `fleet-state-unavailable` names: the grant the chart renders, and where.
GRANT = ("grant get/create/update on coordination.k8s.io/leases in this namespace to the dashboard's "
         "ServiceAccount — the chart renders it under leaderElection.enabled or a fleet account in use")

_DIGESTS: dict[tuple[str, str], str] = {}


class ClaimHeld(Exception):
    """Another claim on this account is live, or the Lease changed since the read a decision rests on. Not a
    failure: the caller binds nothing and tries on its next cycle."""


class FleetStateUnavailable(Exception):
    """The Lease could not be read or written: a 403 (the grant is absent), a 5xx, a write that met a 409
    `CAS_TRIES` times. FAIL CLOSED — nothing binds. Shaped as the finding it becomes, with the lookup's
    refusal fields (`gsd/fleetlookup.py#LookupRefused`): free, announced when it appears, rechecked every cycle."""

    code, spent, gated, secrets = "fleet-state-unavailable", False, False, ()

    def __init__(self, detail: str, action: str = GRANT):
        super().__init__(f"{self.code}: {detail}")
        self.detail, self.action = detail, action


def lease_name(account: str) -> str:
    """`gsd-fleet-` + sha256(username)[:16]: a DNS-1123 name whatever the username holds."""
    return "gsd-fleet-" + hashlib.sha256(account.encode("utf-8")).hexdigest()[:16]


def lease_digest(account: str, password: str) -> str:
    """The password's fingerprint AS THE LEASE RECORDS IT: scrypt, salted with the account, at the OWASP Password
    Storage Cheat Sheet's 16 MiB scrypt setting (N=2^14, r=8, p=5), 64 bits kept.

    NOT the in-memory gate's sha256 prefix (`gsd/fleetlookup.py#CredentialGate`), on purpose: a Lease is read by
    whoever holds `get leases` in this namespace — `cluster-reader` among them, measured on the reference cluster
    (SPEC_S4c orchestrator's notes), which cannot read the password Secret in `openshift-config` — and an
    unsalted fast hash there would be an offline dictionary oracle for the LDAP bind password. 64 bits of it
    still over-block on a collision and never bind (R3-2's rule). Computed once per (account, password) per
    process: the cache is keyed on the password's sha256, never on the password."""
    key = (account, hashlib.sha256(password.encode("utf-8")).hexdigest())
    if key not in _DIGESTS:
        _DIGESTS[key] = hashlib.scrypt(password.encode("utf-8"), salt=account.encode("utf-8"),
                                       n=2**14, r=8, p=5, dklen=8).hex()
    return _DIGESTS[key]


def claim_seconds(settings) -> int:
    """How long a claim stands before another process may judge it abandoned: the longest bind path under the
    settings it runs with — the login under `RETRY_POLICY` (each attempt at most discovery + authorize, two
    request timeouts, plus the policy's backoff) and then the read and the revoke (two more) — floored at 60.
    195 s at the defaults. Computed, never a constant: a longer requestTimeoutSeconds must not let a live
    claim look abandoned mid-login."""
    timeout = float(settings.request_timeout_seconds)
    backoff = sum(RETRY_POLICY.wait_after(n) for n in range(1, RETRY_POLICY.attempts))
    return max(60, math.ceil(RETRY_POLICY.attempts * 2 * timeout + backoff + 2 * timeout))


def stamp(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime(STAMP)


def _micro(moment: datetime) -> str:
    """A Kubernetes MicroTime: EXACTLY six fractional digits (`gsd/leader.py#LeaderElector._now` says why)."""
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


def _instant(value) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.utcoffset() is not None else None


@dataclass(frozen=True)
class FleetRecord:
    """One account's Lease as read: the claim, the gate, the ping's instants. Immutable; a write returns the
    next one."""

    account: str
    resource_version: str | None
    holder: str
    holder_until: datetime | None          # renewTime + leaseDurationSeconds, or None when unheld
    refused: dict | None                   # {digest, at, code, target}: the account entry; target is evidence
    ping_last_attempt: datetime | None
    ping_last_ok: datetime | None
    ping_last_outcome: str | None
    ping_last_target: str | None
    ping_digest: str | None                # the password the last ATTEMPT was for (B3)
    raw: dict | None = field(default=None, repr=False, compare=False)

    def gated(self, digest: str) -> dict | None:
        """The account entry when its digest matches, whatever the target — every bind path's rule (B2). An
        entry that is not this dashboard's JSON gates every password: the safe direction, until it is removed."""
        if self.refused is None:
            return None
        return self.refused if self.refused.get("digest") in (digest, None) else None

    def view(self) -> dict:
        """What the API and `/metrics` serve: instants and words as the Lease holds them, never the digest."""
        entry = self.refused
        return {"lease": lease_name(self.account),
                "last_attempt": stamp(self.ping_last_attempt) if self.ping_last_attempt else None,
                "last_ok": stamp(self.ping_last_ok) if self.ping_last_ok else None,
                "last_outcome": self.ping_last_outcome, "last_target": self.ping_last_target,
                "suspended": [{"target": entry.get("target"), "since": entry.get("at"), "code": entry.get("code")}]
                if entry else []}


def _record(account: str, obj: dict | None) -> FleetRecord:
    if not isinstance(obj, dict):
        return FleetRecord(account, None, "", None, None, None, None, None, None, None)
    meta, spec = obj.get("metadata") or {}, obj.get("spec") or {}
    ann = meta.get("annotations") or {}
    renewed, seconds = _instant(spec.get("renewTime")), spec.get("leaseDurationSeconds")
    refused = ann.get(PREFIX + "refused")
    if refused is not None:
        try:
            refused = json.loads(refused)
        except ValueError:
            refused = None
        # An entry that is not this dashboard's JSON gates every password (the safe direction) until removed.
        refused = refused if isinstance(refused, dict) else {"digest": None, "code": "login-refused", "target": "", "at": ""}
    return FleetRecord(
        account=account, resource_version=meta.get("resourceVersion"), holder=spec.get("holderIdentity") or "",
        holder_until=renewed + timedelta(seconds=seconds) if renewed and isinstance(seconds, int) else None,
        refused=refused, ping_last_attempt=_instant(ann.get(PREFIX + "ping-last-attempt")),
        ping_last_ok=_instant(ann.get(PREFIX + "ping-last-ok")), ping_last_outcome=ann.get(PREFIX + "ping-last-outcome"),
        ping_last_target=ann.get(PREFIX + "ping-last-target"), ping_digest=ann.get(PREFIX + "ping-digest"), raw=obj)


class FleetLease:
    """One attempt's handle on an account's Lease, through the host cluster's client: the pod's own
    ServiceAccount, the identity the lookup writes the cluster Secret with. Never shared between threads."""

    def __init__(self, host: ClusterClient, namespace: str, account: str, *, claim_seconds: int,
                 identity: str | None = None, clock: Callable[[], datetime] | None = None):
        self.host, self.namespace, self.account = host, namespace, account
        self.name = lease_name(account)
        # The pod's name, so `oc get leases.coordination.k8s.io` names the holder — the elector's rule.
        self.identity = identity or os.environ.get("POD_NAME") or socket.gethostname()
        self.claim_seconds = claim_seconds
        self._clock = clock or (lambda: datetime.now(UTC))
        #: The claim this instance holds, as its last write left it; None when it holds none.
        self.record: FleetRecord | None = None
        #: A write met a 409: the claim was judged expired and taken, so its holder is no longer ours to clear.
        self._lost = False

    def _call(self, method: str, obj: dict | None = None) -> dict | None:
        path = LEASE_API.format(ns=self.namespace)
        with self.host._client() as client:
            if method == "GET":
                return self.host._get(client, f"{path}/{self.name}", {})
            return self.host._send(client, method, path if method == "POST" else f"{path}/{self.name}", json=obj)

    def _unavailable(self, what: str, exc: ClusterError) -> FleetStateUnavailable:
        return FleetStateUnavailable(f"cannot {what} Lease {self.namespace}/{self.name}: {exc.outcome}: "
                                     f"{exc.message.split(': ', 1)[0]}")

    def read(self) -> FleetRecord:
        """The Lease without a claim; an absent one is an empty record, not an error."""
        try:
            obj = self._call("GET")
        except ClusterError as exc:
            if exc.message.startswith("HTTP 404"):
                return _record(self.account, None)
            raise self._unavailable("read", exc) from exc
        return _record(self.account, obj)

    def claim(self, read: FleetRecord | None = None, **changes: str | None) -> FleetRecord:
        """Hold the account: ONE write carrying the resourceVersion of `read` — the record a caller decided on —
        or of a fresh read. A live claim, anyone's, this process's included, is ClaimHeld; so is a 409, because the
        Lease changed since that read. `changes` ride the same write: the ping's attempt is recorded atomically
        with its claim, before its bind, so a second replica or a crash cannot ping twice (B3)."""
        now = self._clock()
        record = read if read is not None else self.read()
        if record.holder and record.holder_until is not None and record.holder_until > now:
            raise ClaimHeld(f"{record.holder} holds {self.name} until {stamp(record.holder_until)}")
        obj = _applied(record.raw or {"apiVersion": "coordination.k8s.io/v1", "kind": "Lease",
                                      "metadata": {"name": self.name, "namespace": self.namespace,
                                                   "labels": {LEASE_TYPE_LABEL: LEASE_TYPE}}},
                       {"account": self.account, **changes})
        obj["spec"] = {**(obj.get("spec") or {}), "holderIdentity": self.identity,
                       "leaseDurationSeconds": self.claim_seconds, "acquireTime": _micro(now), "renewTime": _micro(now)}
        try:
            written = self._call("POST" if record.raw is None else "PUT", obj)
        except ClusterError as exc:
            if exc.message.startswith("HTTP 409"):
                raise ClaimHeld(f"{self.name} changed since it was read") from exc
            raise self._unavailable("claim", exc) from exc
        self.record, self._lost = (_record(self.account, written) if isinstance(written, dict) else self.read()), False
        return self.record

    def refuse(self, target: str, digest: str, code: str) -> None:
        """A bound answer, recorded on the Lease BEFORE the process's gate and before the finding (SPEC_S4c §3.3,
        step 5), so that a restart and another replica read it. Never raises: when the Lease cannot take it, one
        line says the process's gate is the only memory until it restarts, and the caller's refusal goes on."""
        entry = json.dumps({"digest": digest, "at": stamp(self._clock()), "code": code, "target": target}, sort_keys=True)
        try:
            self._put({"refused": entry}, release=False)
        except FleetStateUnavailable as exc:
            failure(log, "fleet-state-unavailable", phase="credential", outcome=exc.code, account=self.account,
                    lease=self.name, action=f"the refusal is held in this process only, so a restart or another replica "
                                            f"may send this password once more: {exc.action}", detail=exc.detail)
        except Exception:  # noqa: BLE001 - it runs inside the caller's refusal, which it must never replace
            log.exception("recording a refusal on Lease %s/%s failed; this process's gate holds it", self.namespace, self.name)

    def release(self, **changes: str | None) -> FleetRecord | None:
        """Let the claim go, with any last changes, in one write; the record it left, or None. NEVER raises —
        cleanup never replaces the exception it is cleaning up after (#283's rule): a failure is one line, and the
        claim expires by itself."""
        try:
            if self.record is not None:
                return self._put(changes, release=True)
        except FleetStateUnavailable as exc:
            failure(log, "fleet-state-unavailable", phase="credential", outcome=exc.code, account=self.account,
                    lease=self.name, action=f"the claim expires by itself within {self.claim_seconds}s: {exc.action}",
                    detail=exc.detail)
        except Exception:  # noqa: BLE001 - a release must never raise past its caller
            log.exception("releasing Lease %s/%s failed; the claim expires by itself", self.namespace, self.name)
        finally:
            self.record = None
        return None

    def _put(self, changes: dict, *, release: bool) -> FleetRecord:
        record = self.record
        for _ in range(CAS_TRIES):
            obj = _applied(record.raw, changes)
            if release and not self._lost:
                obj["spec"]["holderIdentity"] = ""
            try:
                written = self._call("PUT", obj)
            except ClusterError as exc:
                if not exc.message.startswith("HTTP 409"):
                    raise self._unavailable("write", exc) from exc
                # The Lease changed under the claim — it was judged expired and taken. The changes are re-applied
                # to it as it now is; its holder is not ours to clear, and a removal of `refused` is dropped, so
                # another process's refusal is never erased by this one's success.
                record, self._lost = self.read(), True
                changes = {k: v for k, v in changes.items() if not (k == "refused" and v is None)}
                if record.raw is None:
                    raise FleetStateUnavailable(f"Lease {self.namespace}/{self.name} was deleted under a claim") from exc
                continue
            self.record = _record(self.account, written) if isinstance(written, dict) else self.read()
            return self.record
        raise FleetStateUnavailable(f"Lease {self.namespace}/{self.name} changed under each of {CAS_TRIES} writes")


def _applied(obj: dict, changes: dict) -> dict:
    """A copy of the Lease with annotation changes applied: `ping_last_ok` is `ping-last-ok`; None removes one."""
    out = copy.deepcopy(obj)
    ann = out.setdefault("metadata", {}).setdefault("annotations", {})
    for key, value in changes.items():
        if value is None:
            ann.pop(PREFIX + key.replace("_", "-"), None)
        else:
            ann[PREFIX + key.replace("_", "-")] = value
    return out


__all__ = ["CAS_TRIES", "ClaimHeld", "FleetLease", "FleetRecord", "FleetStateUnavailable", "LEASE_TYPE",
           "LEASE_TYPE_LABEL", "claim_seconds", "lease_digest", "lease_name", "stamp"]
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
one that carries the label is already dead, and storing it would be a 401 on the first poll.

`lookup(..., write=False)` is #285's daily ping: the same login, read and revoke, and nothing stored.
"""

from __future__ import annotations
```

```python
one that carries the label is already dead, and storing it would be a 401 on the first poll.

`lookup(..., write=False)` is #285's daily ping: the same login, read and revoke, and nothing stored.

THE ACCOUNT LEASE (#285, SPEC_S4c §3.3). A caller that passes `lease` has CLAIMED the fleet account's Lease
first: its entry for this password gates here like the process's own, and a bound answer is written to it
before the process's gate, so a restart and a second replica read what this process was told.
"""

from __future__ import annotations
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
from .clusterconfig.events import is_transport_message, redact
from .config import ClusterConfig, Settings
from .fleetlogin import FleetLogin, LoginError, _without_userinfo
from .kube import AUTH_FAILED, ClusterClient, ClusterError, redact_text

log = logging.getLogger(__name__)
```

```python
from .clusterconfig.events import is_transport_message, redact
from .config import ClusterConfig, Settings
from .fleetlogin import FleetLogin, LoginError, _without_userinfo
from .fleetstate import FleetLease, lease_digest
from .kube import AUTH_FAILED, ClusterClient, ClusterError, redact_text

log = logging.getLogger(__name__)
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
    THE BUDGET, with its scope: at most one answered failed authorize per (account, password) per
    process, across every target. "Account" is the exact configured username string, compared as
    written: directory aliases and case variants are not resolved, so every stanza for one identity
    must use one spelling. "Process" is the production Poller's one gate, used serially on its
    discovery thread; a new gate starts a new budget. A restart or a second replica starts empty —
    not covered until #285's account Lease, which this becomes the cache of (SPEC_S4c §3.3)."""

    def __init__(self) -> None:
        self._refused: dict[tuple[str, str], str] = {}
```

```python
    THE BUDGET, with its scope: at most one answered failed authorize per (account, password) per
    process, across every target. "Account" is the exact configured username string, compared as
    written: directory aliases and case variants are not resolved, so every stanza for one identity
    must use one spelling. "Process" is the production Poller's one gate, shared by its discovery
    thread and its self-login poll threads (single dict and set operations); a new gate starts a new
    budget. It is the cache of the account Lease's gate (SPEC_S4c §3.3): every bind path claims the
    Lease first and seeds the REFUSED kind from the Lease's entry, and a bound answer is written to
    the Lease before it is written here — so a restart and a second replica read it while the Lease
    is writable, and this is the only copy when it is not. The SPENT kind is never on the Lease."""

    def __init__(self) -> None:
        self._refused: dict[tuple[str, str], str] = {}
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python

def lookup(cluster: ClusterConfig, settings: Settings, host_client: ClusterClient, *, own_namespace: str,
           gate: CredentialGate, write: bool = True, sleep: Callable[[float], None] = time.sleep,
           clock: Callable[[], datetime] | None = None) -> LookupResult:
    """The whole retrieval for one cluster: password, login, read, revoke, and — with `write` — store.

    Every refusal is a `LookupRefused` carrying the finding it becomes and the secrets in play. The
    session is a context manager, so the login's token is revoked whatever the read does. With
    `write=False` (#285's ping) nothing is written and the token is returned in the result.
    """
    if write and not (settings.cluster_secrets_enabled and settings.cluster_secrets_writes_enabled):
        # THE SWITCH IS CHECKED HERE, not only by the caller (review of #295, P1-4): a second caller —
```

```python

def lookup(cluster: ClusterConfig, settings: Settings, host_client: ClusterClient, *, own_namespace: str,
           gate: CredentialGate, write: bool = True, sleep: Callable[[float], None] = time.sleep,
           clock: Callable[[], datetime] | None = None, lease: FleetLease | None = None) -> LookupResult:
    """The whole retrieval for one cluster: password, login, read, revoke, and — with `write` — store.

    Every refusal is a `LookupRefused` carrying the finding it becomes and the secrets in play. The
    session is a context manager, so the login's token is revoked whatever the read does. With
    `write=False` (#285's ping) nothing is written and the token is returned in the result. `lease` is
    the fleet account's Lease with the caller's claim on it (SPEC_S4c §3.3); every production caller
    passes one, and None is the process's gate alone — #284's and #293's own hermetic tests.
    """
    if write and not (settings.cluster_secrets_enabled and settings.cluster_secrets_writes_enabled):
        # THE SWITCH IS CHECKED HERE, not only by the caller (review of #295, P1-4): a second caller —
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
    password = fleet_password(host_client, settings, own_namespace)
    secrets: list[str] = [password]
    try:
        answered = gate.answered(cluster.api_url, account, password)
        if answered is not None:
            # THE TARGET THAT ANSWERED IS NAMED (#315): the entry is the account's, so it may be another
```

```python
    password = fleet_password(host_client, settings, own_namespace)
    secrets: list[str] = [password]
    try:
        if lease is not None:
            # THE LEASE SEEDS THE PROCESS'S GATE (SPEC_S4c §3.3): an entry another replica, or this pod before
            # a restart, wrote for this account and password gates here too, naming the target that answered.
            entry = lease.record.gated(lease_digest(account, password))
            if entry is not None:
                gate.refuse(entry.get("target") or "", account, password)
        answered = gate.answered(cluster.api_url, account, password)
        if answered is not None:
            # THE TARGET THAT ANSWERED IS NAMED (#315): the entry is the account's, so it may be another
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
                # account's 500 cannot be told from a sick target's): re-entering #283's terminal answer
                # from a schedule is the lockout walk one layer up, and an in-memory "final" that any
                # shape change re-arms is not a stop. `AUTH_FAILED` is the refusal's word; the rest read
                # as failed.
                gate.refuse(cluster.api_url, account, password)
                code = "login-refused" if exc.outcome == AUTH_FAILED else "login-failed"
                raise LookupRefused(code, f"phase={exc.phase}{which}: {exc.message}",
                                    action=(f"the password for {account} was sent to {cluster.name} and no session came "
                                            f"back: rotate the fleet password Secret or correct ldapConnectionBootstrap, "
```

```python
                # account's 500 cannot be told from a sick target's): re-entering #283's terminal answer
                # from a schedule is the lockout walk one layer up, and an in-memory "final" that any
                # shape change re-arms is not a stop. `AUTH_FAILED` is the refusal's word; the rest read
                # as failed. The Lease first, the process second (SPEC_S4c §3.3, step 5): a crash between the
                # two loses the cheap copy, never the durable one.
                code = "login-refused" if exc.outcome == AUTH_FAILED else "login-failed"
                if lease is not None:
                    lease.refuse(CredentialGate._target(cluster.api_url), lease_digest(account, password), code)
                gate.refuse(cluster.api_url, account, password)
                raise LookupRefused(code, f"phase={exc.phase}{which}: {exc.message}",
                                    action=(f"the password for {account} was sent to {cluster.name} and no session came "
                                            f"back: rotate the fleet password Secret or correct ldapConnectionBootstrap, "
```

<!-- block: local-development/gsd/config.py | edit -->
```python
#: found. It pairs with `self-login` — both say how the credential was got, in two words.
CREDENTIAL_SELF_LOGIN = "self-login"    # userSelfLogin: the bootstrap account polls as itself
#: Credential kinds the process cannot resolve yet, each with the reason the poller logs instead of
#: polling. A kind in this table is never handed to ClusterClient.
CREDENTIAL_PENDING_REASONS = {
    "oauth": "declares oauth (#119 P2, not built)",
    CREDENTIAL_LOOKUP: "declares saTokenLookup — S3b's lookup has not retrieved a credential yet; the Cluster "
                       "Configurations tab's findings say why when it is late",
    CREDENTIAL_SELF_LOGIN: "declares userSelfLogin — the self-login mode is S3b's #285, not built; nothing has been obtained yet",
}
#: Every key a values stanza may carry. The parser's accepted `config` keys include CONNECTION_KEYS
#: too, and tests/test_connection_modes.py fails the commit on which the two sets diverge (§4.1).
```

```python
#: found. It pairs with `self-login` — both say how the credential was got, in two words.
CREDENTIAL_SELF_LOGIN = "self-login"    # userSelfLogin: the bootstrap account polls as itself
#: Credential kinds the process cannot resolve yet, each with the reason the poller logs instead of
#: polling. A kind in this table is never handed to ClusterClient. `self-login` left it with #285: its
#: credential is the session the poll thread holds, substituted for each poll (SPEC_S4c §3.6).
CREDENTIAL_PENDING_REASONS = {
    "oauth": "declares oauth (#119 P2, not built)",
    CREDENTIAL_LOOKUP: "declares saTokenLookup — S3b's lookup has not retrieved a credential yet; the Cluster "
                       "Configurations tab's findings say why when it is late",
}
#: Every key a values stanza may carry. The parser's accepted `config` keys include CONNECTION_KEYS
#: too, and tests/test_connection_modes.py fails the commit on which the two sets diverge (§4.1).
```

<!-- block: local-development/gsd/config.py | edit -->
```python
    # is the lookup's own write for that stanza: ClusterRegistry.merge keeps its credential and serves the
    # stanza's policy and `enabled`. None for a values entry and for a Secret that carries no annotation.
    token_source: str | None = field(default=None, repr=False)

    @property
    def tls_mode(self) -> dict:
```

```python
    # is the lookup's own write for that stanza: ClusterRegistry.merge keeps its credential and serves the
    # stanza's policy and `enabled`. None for a values entry and for a Secret that carries no annotation.
    token_source: str | None = field(default=None, repr=False)
    # The account a lookup-written Secret records it logged in as (`groupsync-dashboard.io/lookup-account`):
    # the one place that account survives retrieval, which strips the mode keys from a declaring Secret and
    # never had them on a generated one — so it is what the daily ping is keyed on (SPEC_S4c §3.4).
    lookup_account: str | None = field(default=None, repr=False)

    @property
    def tls_mode(self) -> dict:
```

<!-- block: local-development/gsd/config.py | edit -->
```python
                f"cluster {self.name!r}: username/password exchange against the OAuth server is #119 P2, not built"
            )
        if self.connection_mode is not None:
            # Listed so the tab can say what the stanza declares; obtaining the credential is S3b. The
            # poller never asks (`credential_pending`), so this is reached only by a direct caller.
            raise ConfigError(f"cluster {self.name!r}: {CREDENTIAL_PENDING_REASONS[self.credential_kind]}")
        if self.token_file:
            try:
                token = Path(self.token_file).read_text(encoding="utf-8").strip()
```

```python
                f"cluster {self.name!r}: username/password exchange against the OAuth server is #119 P2, not built"
            )
        if self.connection_mode is not None:
            # Listed so the tab can say what the stanza declares; obtaining the credential is S3b. The poller
            # never asks: a lookup is pending (`credential_pending`) until its Secret exists, and a self-login
            # session is substituted as `token_value` for each poll (SPEC_S4c §3.6) — so this is reached only
            # by a direct caller.
            reason = CREDENTIAL_PENDING_REASONS.get(self.credential_kind) or (
                "declares userSelfLogin — S3b's session is its credential, held by the poll thread and never "
                "resolved from the declaration")
            raise ConfigError(f"cluster {self.name!r}: {reason}")
        if self.token_file:
            try:
                token = Path(self.token_file).read_text(encoding="utf-8").strip()
```

<!-- block: local-development/gsd/config.py | edit -->
```python
    # How many replicas the chart runs (ConfigMap `replicaCount`): the lookup refuses to run above one
    # without an elector, because every replica would log in (SPEC_S4 §6; review of #295, P0-2).
    replica_count: int = 1
    cluster_registry: "ClusterRegistry" = field(default_factory=lambda: _registry(), compare=False, repr=False)
    kyverno_metrics_url: str = ""
    kyverno_events_retention_days: int = 90
```

```python
    # How many replicas the chart runs (ConfigMap `replicaCount`): the lookup refuses to run above one
    # without an elector, because every replica would log in (SPEC_S4 §6; review of #295, P0-2).
    replica_count: int = 1
    # The daily ping (SPEC_S4c §3.4): one real login-and-read per fleet account per interval, on the
    # discovery cadence, leader only — `clusterConfig.fleetAccount.ping.{enabled, intervalSeconds}`.
    fleet_ping_enabled: bool = True
    fleet_ping_interval_seconds: int = 86400
    cluster_registry: "ClusterRegistry" = field(default_factory=lambda: _registry(), compare=False, repr=False)
    kyverno_metrics_url: str = ""
    kyverno_events_retention_days: int = 90
```

<!-- block: local-development/gsd/config.py | edit -->
```python
        sa_token_lookup_service_account=_str_setting(raw, "GSD_SA_TOKEN_LOOKUP_SERVICE_ACCOUNT", "saTokenLookupSourceServiceAccount", "group-sync-dashboard-cluster-poller"),
        sa_token_lookup_secret_name=_str_setting(raw, "GSD_SA_TOKEN_LOOKUP_SECRET_NAME", "saTokenLookupTokenSecretName", ""),
        replica_count=_num_setting(raw, "GSD_REPLICA_COUNT", "replicaCount", 1, int),
        kyverno_metrics_url=str(os.environ.get("GSD_KYVERNO_METRICS_URL") or raw.get("kyvernoMetricsUrl") or "").strip(),
        kyverno_events_retention_days=_num_setting(
            raw, "GSD_KYVERNO_EVENTS_RETENTION_DAYS", "kyvernoEventsRetentionDays", 90, int
```

```python
        sa_token_lookup_service_account=_str_setting(raw, "GSD_SA_TOKEN_LOOKUP_SERVICE_ACCOUNT", "saTokenLookupSourceServiceAccount", "group-sync-dashboard-cluster-poller"),
        sa_token_lookup_secret_name=_str_setting(raw, "GSD_SA_TOKEN_LOOKUP_SECRET_NAME", "saTokenLookupTokenSecretName", ""),
        replica_count=_num_setting(raw, "GSD_REPLICA_COUNT", "replicaCount", 1, int),
        fleet_ping_enabled=_bool_setting(raw, "GSD_FLEET_PING_ENABLED", "fleetPingEnabled", True),
        fleet_ping_interval_seconds=_num_setting(raw, "GSD_FLEET_PING_INTERVAL_SECONDS", "fleetPingIntervalSeconds", 86400, int),
        kyverno_metrics_url=str(os.environ.get("GSD_KYVERNO_METRICS_URL") or raw.get("kyvernoMetricsUrl") or "").strip(),
        kyverno_events_retention_days=_num_setting(
            raw, "GSD_KYVERNO_EVENTS_RETENTION_DAYS", "kyvernoEventsRetentionDays", 90, int
```

<!-- block: local-development/gsd/clusterconfig/__init__.py | edit -->
```python
    # every other finding.
    "fleet-credential-missing", "fleet-write-disabled", "login-refused", "login-failed",
    "sa-token-secret-missing", "sa-token-unreadable", "sa-token-invalidated", "lookup-write-failed",
)

from .parser import Finding, parse_secret  # noqa: E402
```

```python
    # every other finding.
    "fleet-credential-missing", "fleet-write-disabled", "login-refused", "login-failed",
    "sa-token-secret-missing", "sa-token-unreadable", "sa-token-invalidated", "lookup-write-failed",
    # SPEC_S4c (#285): the fleet account's Lease could not be read or written (nothing binds); a self-login
    # cluster suspended with its account's credential, or whose target states a session too short to renew.
    "fleet-state-unavailable", "self-login-suspended", "self-login-lifetime-too-short",
)

from .parser import Finding, parse_secret  # noqa: E402
```

<!-- block: local-development/gsd/clusterconfig/reader.py | edit -->
```python

import dataclasses

from ..config import ClusterConfig
from . import LABEL_SELECTOR
from .parser import Finding, parse_secret
from .writer import TOKEN_SOURCE_ANNOTATION

#: What to do about each refusal, in the operator's terms rather than the parser's. `action=` is the
#: fix, not the diagnosis (#245): a line that says only what broke leaves the reader to translate,
```

```python

import dataclasses

from ..config import ClusterConfig, valid_bootstrap_username
from . import LABEL_SELECTOR
from .parser import Finding, parse_secret
from .writer import LOOKUP_ACCOUNT_ANNOTATION, TOKEN_SOURCE_ANNOTATION

#: What to do about each refusal, in the operator's terms rather than the parser's. `action=` is the
#: fix, not the diagnosis (#245): a line that says only what broke leaves the reader to translate,
```

<!-- block: local-development/gsd/clusterconfig/reader.py | edit -->
```python
    parsed_ok: list[ClusterConfig] = []
    findings: list[Finding] = []
    token_source: dict[str, str | None] = {}   # Secret name -> its token-source annotation, if any
    for obj in items:
        parsed = parse_secret(obj, host_name=host_name)
        if isinstance(parsed, Finding):
```

```python
    parsed_ok: list[ClusterConfig] = []
    findings: list[Finding] = []
    token_source: dict[str, str | None] = {}   # Secret name -> its token-source annotation, if any
    lookup_account: dict[str, str | None] = {}  # Secret name -> the account a lookup wrote it as (SPEC_S4c §3.4)
    for obj in items:
        parsed = parse_secret(obj, host_name=host_name)
        if isinstance(parsed, Finding):
```

<!-- block: local-development/gsd/clusterconfig/reader.py | edit -->
```python
            continue
        meta = obj.get("metadata") or {}
        token_source[str(meta.get("name") or "")] = (meta.get("annotations") or {}).get(TOKEN_SOURCE_ANNOTATION)
        parsed_ok.append(parsed)
    # FAIL CLOSED ON A DUPLICATE NAME (design review of #230, OB2). "The first by metadata.name wins"
    # let a Secret named to sort first — `aaa-anything` — replace the server and the token of a
```

```python
            continue
        meta = obj.get("metadata") or {}
        token_source[str(meta.get("name") or "")] = (meta.get("annotations") or {}).get(TOKEN_SOURCE_ANNOTATION)
        account = (meta.get("annotations") or {}).get(LOOKUP_ACCOUNT_ANNOTATION)
        lookup_account[str(meta.get("name") or "")] = account if valid_bootstrap_username(account) else None
        parsed_ok.append(parsed)
    # FAIL CLOSED ON A DUPLICATE NAME (design review of #230, OB2). "The first by metadata.name wins"
    # let a Secret named to sort first — `aaa-anything` — replace the server and the token of a
```

<!-- block: local-development/gsd/clusterconfig/reader.py | edit -->
```python
        secret_name = parsed.source.split(":", 1)[1]
        # The ownership the check below makes, recorded on the config itself (SPEC_D2b §3.4): the merge
        # serves a stanza's policy over the Secret the lookup wrote for it, and only that Secret.
        parsed = dataclasses.replace(parsed, token_source=token_source.get(secret_name))
        if parsed.name in values_names:
            # The retriever's own Secret over the stanza that asked for it is the design, not a
            # shadow (SPEC_S4 §1): the values entry declares the mode, the Secret says it came from it.
```

```python
        secret_name = parsed.source.split(":", 1)[1]
        # The ownership the check below makes, recorded on the config itself (SPEC_D2b §3.4): the merge
        # serves a stanza's policy over the Secret the lookup wrote for it, and only that Secret.
        parsed = dataclasses.replace(parsed, token_source=token_source.get(secret_name),
                                     lookup_account=lookup_account.get(secret_name))
        if parsed.name in values_names:
            # The retriever's own Secret over the stanza that asked for it is the design, not a
            # shadow (SPEC_S4 §1): the values entry declares the mode, the Secret says it came from it.
```

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->
```python
        # the lookup succeeds or the cluster stops being pending. Separate from `_findings`, which a
        # discovery replaces every cycle — a lookup finding must survive the cycles between attempts.
        self._lookups: dict[str, Finding] = {}
        self._blocked: set[str] = set()

    def replace(self, clusters: list[ClusterConfig], findings: list[Finding], *, at: str,
```

```python
        # the lookup succeeds or the cluster stops being pending. Separate from `_findings`, which a
        # discovery replaces every cycle — a lookup finding must survive the cycles between attempts.
        self._lookups: dict[str, Finding] = {}
        # SPEC_S4c: the standing findings of the daily ping (per target) and of self-login (per cluster), each
        # in a slot of its own — `_retrieve_pending` clears the lookup slot every cycle for every cluster it
        # stops tracking, so a finding another owner holds there would be erased by it. Two owners, one card.
        self._standing: dict[tuple[str, str], Finding] = {}
        self._blocked: set[str] = set()

    def replace(self, clusters: list[ClusterConfig], findings: list[Finding], *, at: str,
```

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->
```python
        with self._lock:
            out = list(self._findings)
            out.extend(self._lookups[name] for name in sorted(self._lookups))
            if self.error:
                out.append(Finding("-", "discovery-failed", self.error))
            return out
```

```python
        with self._lock:
            out = list(self._findings)
            out.extend(self._lookups[name] for name in sorted(self._lookups))
            out.extend(self._standing[key] for key in sorted(self._standing))
            if self.error:
                out.append(Finding("-", "discovery-failed", self.error))
            return out
```

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->
```python
            else:
                self._lookups[cluster] = finding

    def merge(self, values: list[ClusterConfig]) -> list[ClusterConfig]:
        """The values list with the discovered clusters laid over it: a Secret shadows a values entry of the same
        name (C2 — the shadow is reported by the reader as a finding); the host, values[0] enabled, is never replaced
```

```python
            else:
                self._lookups[cluster] = finding

    def set_standing_finding(self, slot: str, cluster: str, finding: Finding | None) -> None:
        """A finding its owner holds across cycles in its own slot — `ping`, `self-login` (SPEC_S4c); None clears it."""
        with self._lock:
            if finding is None:
                self._standing.pop((slot, cluster), None)
            else:
                self._standing[(slot, cluster)] = finding

    def prune_standing(self, slot: str, keep: set[str]) -> None:
        """Drop the slot's findings for every cluster not in `keep` — one that left the fleet takes its finding along."""
        with self._lock:
            for key in [k for k in self._standing if k[0] == slot and k[1] not in keep]:
                del self._standing[key]

    def merge(self, values: list[ClusterConfig]) -> list[ClusterConfig]:
        """The values list with the discovered clusters laid over it: a Secret shadows a values entry of the same
        name (C2 — the shadow is reported by the reader as a finding); the host, values[0] enabled, is never replaced
```

<!-- block: local-development/gsd/kube.py | edit -->
```python
import httpx

from .config import (
    IDENTITY_SAME_AS_HOST, VISIBILITY_REMOTE_SAR, VISIBILITY_TIER_TTL_DEFAULT, ClusterConfig, ConfigError, Settings,
    remote_policy,
)

log = logging.getLogger(__name__)
```

```python
import httpx

from .config import (
    CREDENTIAL_SELF_LOGIN, IDENTITY_SAME_AS_HOST, VISIBILITY_REMOTE_SAR, VISIBILITY_TIER_TTL_DEFAULT, ClusterConfig,
    ConfigError, Settings, remote_policy,
)

log = logging.getLogger(__name__)
```

<!-- block: local-development/gsd/kube.py | edit -->
```python

    def get(self, cluster_id: str) -> TierResolver | None:
        host = self._settings.host_cluster()
        askable = {c.name: c for c in self._settings.effective_clusters()
                   if c.enabled and c.credential_pending is None
                   and (host is None or c.name != host.name)
                   and remote_policy(c.visibility, c.identity) == (VISIBILITY_REMOTE_SAR, IDENTITY_SAME_AS_HOST)}
        cluster = askable.get(cluster_id)
```

```python

    def get(self, cluster_id: str) -> TierResolver | None:
        host = self._settings.host_cluster()
        # A self-login cluster is not askable either (#285): its credential is the poll thread's session, which
        # this resolver never holds, so the review would present no token at all — it answers self, as it did
        # while the mode was pending.
        askable = {c.name: c for c in self._settings.effective_clusters()
                   if c.enabled and c.credential_pending is None and c.credential_kind != CREDENTIAL_SELF_LOGIN
                   and (host is None or c.name != host.name)
                   and remote_policy(c.visibility, c.identity) == (VISIBILITY_REMOTE_SAR, IDENTITY_SAME_AS_HOST)}
        cluster = askable.get(cluster_id)
```

<!-- block: local-development/gsd/selflogin.py | create -->
```python
"""`userSelfLogin`: the session is the credential, and it renews or it stops (#285, SPEC_S4c §3.6).

A `self-login` cluster stores no token. Before each poll its thread asks `credential_for(cluster)` and gets the
cluster as it polls — the session's token substituted as `token_value`, the substitution `read_sa_token` already
uses, so the token is redacted from every line like any other credential — or None: no session this cycle, and
the poll is skipped rather than failed. After the poll it reports what the poll answered to `poll_answered`.

THE SCHEDULE IS THE SESSION'S OWN (SPEC_S4 §3.1, the business owner's ruling): renew at
`expires_at − min(2 h, ¼ × expires_in)`, from the `expires_in` the target put in the fragment — RFC 6749 §4.2.2,
"the lifetime in seconds of the access token" — never a percentage and never a fixed clock. A one-hour session
renews after 45 minutes; CRC's year renews two hours before it ends. Checked once per poll cycle, on the
cluster's own thread. The new session is entered before the old one exits, so the poll never runs without a
credential and the superseded token is revoked after its replacement exists.

EVERY LOGIN FOLLOWS THE ACCOUNT LEASE'S PROTOCOL (SPEC_S4c §3.3): claim, the gate, the bind, a bound answer
recorded on the Lease before the process's gate, release. ONE attempt per cycle: the poll interval is the retry
(SPEC_S3 §9.3.1), and #283's five-attempt policy inside every cycle would write five `fleet-login-failed` lines
a minute for a target that is down.

THE 401 RULE, reconciled with #283's revoke-side reading. A poll answered 401 BEFORE `expires_at` means the session
was invalidated by something the fragment does not carry — an inactivity timeout, an administrator's `oc delete
oauthaccesstoken`, a changed policy — so the next cycle logs in once more, and nothing is recorded as a refusal
because nothing evaluated the password. If the fresh session's first poll answers 401 too, the API server is
refusing sessions it just issued: the cluster is suspended rather than logged in again every cycle (B4). On the
revoke path a 401 keeps #283's reading: "not proven gone".

SUSPENSION (SPEC_S3 §9.3 rule 1). A bound answer on any acquisition gates the (account, password) and stops EVERY
self-login cluster on the account at once — its session revoked, the cluster parked, a standing finding, its poll
outcome recorded once — in one `fleet-credential-suspended` line that names what stopped and how many. A parked
cluster re-reads the password each cycle at no cost to the directory and resumes when it, the account or the
cluster's URL changes.
"""

from __future__ import annotations

import dataclasses
import logging
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .clusterconfig.events import event, failure
from .clusterconfig.parser import Finding
from .config import CREDENTIAL_SELF_LOGIN, ClusterConfig
from .fleetlogin import FleetLogin, FleetSession, LoginError, RetryPolicy, _without_userinfo
from .fleetlookup import CredentialGate, LookupRefused, fleet_account, fleet_password
from .fleetstate import ClaimHeld, FleetLease, FleetStateUnavailable, claim_seconds, lease_digest, lease_name, stamp
from .kube import AUTH_FAILED, OK, UNREACHABLE

log = logging.getLogger(__name__)

#: One login attempt per poll cycle: the poll interval is the retry (SPEC_S3 §9.3.1).
ONE_ATTEMPT = RetryPolicy(attempts=1)
#: The margin's ceiling (SPEC_S4 §3.1): two hours before the session ends, or a quarter of a shorter lifetime.
MARGIN = timedelta(hours=2)
#: The registry slot this module's standing findings live in.
SLOT = "self-login"
EVENTS = ("self-login-renewed", "self-login-failed", "fleet-credential-suspended")


def renew_at(session: FleetSession) -> datetime:
    """`expires_at − min(2 h, ¼ × expires_in)` (SPEC_S4 §3.1): a fixed margin, a retry budget, not a fraction."""
    return session.expires_at - min(MARGIN, timedelta(seconds=session.expires_in / 4))


@dataclass
class _Session:
    login: FleetLogin                     # entered; its __exit__ is the revoke
    session: FleetSession
    account: str
    key: tuple                            # (account, the password's sha256 prefix, the cluster's URL) at login
    renew_at: datetime
    reauth: bool = False                  # a poll answered 401 before expires_at: log in again next cycle
    reauth_logins: int = 0                # B4: a re-authenticated session whose first poll 401s again is suspended


class SelfLoginSessions:
    """The poller's self-login sessions: one lock, a dict, replace and read — the ClusterRegistry shape. It reads
    the poller it belongs to (its settings, store, gate, signals and host client) each time, never a copy."""

    def __init__(self, poller, *, clock=None):
        self._poller = poller
        self._clock = clock or (lambda: datetime.now(UTC))
        self._lock = threading.Lock()
        self._sessions: dict[str, _Session] = {}
        self._parked: dict[str, tuple] = {}

    # ── the poll thread's two calls ───────────────────────────────────────────────────────────

    def credential_for(self, cluster: ClusterConfig) -> ClusterConfig | None:
        """The cluster as it polls — this cycle's session token substituted — or None when there is no session."""
        now = self._clock()
        with self._lock:
            held = self._sessions.get(cluster.name)
        if held is not None and now < held.renew_at and not held.reauth:
            return self._as(cluster, held)                      # the steady state: one comparison a cycle
        if held is not None and now >= held.session.expires_at:
            self._end(cluster.name, "the session reached expires_at with no replacement; the next cycle logs in again",
                      outcome="expired")
            held = None
        # What the poll keeps while a renewal waits: the current session, unless a 401 already invalidated it.
        live = self._as(cluster, held) if held is not None and not held.reauth else None
        poller = self._poller
        if poller.elector is None and poller.settings.replica_count > 1:
            # The render refuses userSelfLogin above one replica; a Secret-declared one is refused here (§3.8).
            self._finding(cluster.name, "self-login-suspended", f"{cluster.name} declares userSelfLogin on a release of "
                          f"{poller.settings.replica_count} replicas without leader election: every replica would log in "
                          f"as the fleet account — run one replica for a release that declares userSelfLogin")
            return None
        host = poller._host_client()
        if host is None:
            self._finding(cluster.name, "fleet-state-unavailable", "no host cluster or namespace: the fleet account's "
                          "Lease has nowhere to live, so no login is made — check the pod's ServiceAccount mount")
            return live
        client, namespace = host
        try:
            account = fleet_account(poller.settings, cluster)
            password = fleet_password(client, poller.settings, namespace)
        except LookupRefused as exc:
            self._finding(cluster.name, exc.code, f"{exc.detail} — {exc.action}")
            return live
        key = (account, CredentialGate._digest(password), cluster.api_url)
        with self._lock:
            parked = self._parked.get(cluster.name)
            if parked is not None and parked != key:
                del self._parked[cluster.name]          # the password, the account or the URL moved: try again
        if parked == key:
            return None
        fresh = self._acquire(cluster, client, namespace, account, password, key, held)
        if fresh is not None:
            return fresh
        with self._lock:                                  # a suspension may have ended the session meanwhile
            held = self._sessions.get(cluster.name)
        return self._as(cluster, held) if held is not None and not held.reauth else None

    def poll_answered(self, cluster: ClusterConfig, outcome: str) -> None:
        """What the poll with the session answered: a 401 before expires_at re-authenticates once (the 401 rule)."""
        now = self._clock()
        with self._lock:
            held = self._sessions.get(cluster.name)
            if held is not None and outcome == OK:
                held.reauth_logins = 0
        if held is None or outcome != AUTH_FAILED:
            return
        if now >= held.session.expires_at:
            self._end(cluster.name, "the session expired before it was renewed — the schedule failed; the next cycle "
                      "logs in again", outcome="expired")
            return
        if held.reauth_logins:
            with self._lock:
                self._parked[cluster.name] = held.key
            self._end(cluster.name, "the API server refused a session it had just issued, twice in one episode: not "
                      "logged in again until the password, the account or the cluster's URL changes, or the pod restarts",
                      outcome="self-login-suspended", finding=True)
            return
        with self._lock:
            held.reauth = True
        event(log, logging.INFO, "self-login-failed", phase="poll", outcome=AUTH_FAILED, cluster=cluster.name,
              account=held.account, expires_at=held.session.expires_at_iso, reauth="next-cycle",
              action="the session was invalidated before it expired (an inactivity timeout or a revoke): one login on "
                     "the next cycle; nothing is recorded as a refusal")

    def stop(self, name: str) -> None:
        """Exit (revoke) the cluster's session: it was disabled, retired, or its thread is stopping."""
        with self._lock:
            self._parked.pop(name, None)
        self._end(name, None)
        self._finding(name, None)
        if self._poller.signals is not None:
            self._poller.signals.note_self_login(name, None)

    def view(self, name: str) -> dict:
        """The API's `session` block: instants only, as the tab shows them."""
        with self._lock:
            held, parked = self._sessions.get(name), name in self._parked
        if held is None:
            return {"state": "suspended" if parked else "none", "expires_at": None, "renew_at": None}
        return {"state": "renewing" if held.reauth or self._clock() >= held.renew_at else "current",
                "expires_at": held.session.expires_at_iso, "renew_at": stamp(held.renew_at)}

    # ── the login ─────────────────────────────────────────────────────────────────────────────

    def _acquire(self, cluster, client, namespace, account, password, key, held) -> ClusterConfig | None:
        poller = self._poller
        lease = FleetLease(client, namespace, account, claim_seconds=claim_seconds(poller.settings), clock=self._clock)
        try:
            lease.claim()
        except ClaimHeld:
            return None                                  # another holder binds as this account now: the next cycle
        except FleetStateUnavailable as exc:
            self._finding(cluster.name, exc.code, f"{exc.detail} — {exc.action}")
            return None
        acquired: tuple[FleetLogin, FleetSession] | None = None
        try:
            entry = lease.record.gated(lease_digest(account, password))
            if entry is not None:
                poller._credential_gate.refuse(entry.get("target") or "", account, password)
            answered = poller._credential_gate.answered(cluster.api_url, account, password)
            secrets = (password, *((held.session.token,) if held is not None else ()))
            if answered is not None:
                self._suspend(cluster, account, key, code=(entry or {}).get("code") or "login-refused", target=answered,
                              detail=f"{_without_userinfo(answered) or 'another target'} evaluated this password for "
                                     f"{account} already and it has not changed", secrets=secrets)
                return None
            login = FleetLogin(cluster, account, password, timeout=poller.settings.request_timeout_seconds,
                               policy=ONE_ATTEMPT, clock=self._clock)
            try:
                acquired = login, login.__enter__()
            except LoginError as exc:
                if not exc.bound:
                    # Before the password was written: nothing bound, the current session (if any) keeps polling.
                    if held is None:
                        poller.store.record_poll(cluster.name, UNREACHABLE, f"self-login: {exc.message}")
                    return None
                code = "login-refused" if exc.outcome == AUTH_FAILED else "login-failed"
                # The Lease first, the process second (SPEC_S4c §3.3, step 5), then the finding.
                lease.refuse(CredentialGate._target(cluster.api_url), lease_digest(account, password), code)
                poller._credential_gate.refuse(cluster.api_url, account, password)
                self._suspend(cluster, account, key, code=code, target=cluster.api_url,
                              detail=f"phase={exc.phase}: {exc.message}", secrets=secrets)
                return None
        finally:
            # A password that works retires the entry an older one left on the Lease.
            lease.release(**({"refused": None} if acquired else {}))
        login, session = acquired
        floor = 4 * poller.settings.poll_interval_seconds
        if session.expires_in <= floor:
            login.__exit__(None, None, None)
            with self._lock:
                self._parked[cluster.name] = key
            detail = (f"{cluster.name} states a session of {session.expires_in}s, and one renewed a margin before expiry on a "
                      f"{poller.settings.poll_interval_seconds}s poll cycle needs more than {floor}s: raise "
                      f"accessTokenMaxAgeSeconds on the target, or declare saTokenLookup")
            self._finding(cluster.name, "self-login-lifetime-too-short", detail)
            failure(log, "self-login-failed", phase="credential", outcome="self-login-lifetime-too-short",
                    cluster=cluster.name, account=account, gave_up="true", action=detail, secrets=(password,))
            self._note(cluster.name)
            return None
        fresh = _Session(login, session, account, key, renew_at(session),
                         reauth_logins=held.reauth_logins + 1 if held is not None and held.reauth else 0)
        with self._lock:
            old = self._sessions.get(cluster.name)
            self._sessions[cluster.name] = fresh
        if old is not None:
            old.login.__exit__(None, None, None)         # the superseded token, revoked after its replacement exists
            event(log, logging.INFO, "self-login-renewed", cluster=cluster.name, account=account,
                  expires_at=session.expires_at_iso, renew_at=stamp(fresh.renew_at),
                  reauth="true" if fresh.reauth_logins else None, secrets=(password, session.token))
        self._finding(cluster.name, None)
        self._note(cluster.name)
        return self._as(cluster, fresh)

    def _suspend(self, cluster: ClusterConfig, account: str, key: tuple, *, code: str, target: str, detail: str,
                 secrets: tuple[str, ...]) -> None:
        """Every self-login cluster on the account, stopped at once, and one line that says what stopped."""
        poller = self._poller
        stanzas = {c.name: c for c in poller.settings.effective_clusters()
                   if c.enabled and c.credential_kind == CREDENTIAL_SELF_LOGIN
                   and (c.ldap_connection_bootstrap or poller.settings.fleet_account_username) == account}
        stanzas.setdefault(cluster.name, cluster)
        names = sorted(stanzas)
        with self._lock:
            stopped = [self._sessions.pop(name) for name in names if name in self._sessions]
            for name in names:
                self._parked[name] = (account, key[1], stanzas[name].api_url)
        # Every value in play leaves the line: the password, and each session being stopped (a remote may echo one).
        secrets = (*secrets, *(held.session.token for held in stopped))
        for held in stopped:
            held.login.__exit__(None, None, None)
        action = (f"every self-login cluster on {account} stopped polling: rotate the fleet password Secret or correct "
                  f"ldapConnectionBootstrap, or check the account is not locked; the gate on Lease {lease_name(account)} "
                  f"re-arms when the password changes")
        for name in names:
            # `auth_failed` for a refusal — the password WAS presented and refused, and the card goes critical —
            # `unreachable` with the code for any other bound answer. Once: a parked cluster does not poll.
            poller.store.record_poll(name, AUTH_FAILED if code == "login-refused" else UNREACHABLE,
                                     f"{code}: the self-login credential for {account} is suspended")
            self._finding(name, "self-login-suspended", f"{detail} — {action}")
            self._note(name)
        failure(log, "fleet-credential-suspended", phase="credential", outcome=code, account=account, suspended=account,
                scope="self-login", stopped=len(names), clusters=",".join(names),
                target=_without_userinfo(target) or "the answering target", action=action, detail=detail, secrets=secrets)

    # ── the bookkeeping ───────────────────────────────────────────────────────────────────────

    def _end(self, name: str, why: str | None, *, outcome: str | None = None, finding: bool = False) -> None:
        with self._lock:
            held = self._sessions.pop(name, None)
        if held is None:
            return
        held.login.__exit__(None, None, None)
        if why is not None:
            failure(log, "self-login-failed", phase="credential", outcome=outcome, cluster=name, account=held.account,
                    expires_at=held.session.expires_at_iso, gave_up="true" if finding else None, action=why)
        if finding:
            self._finding(name, outcome, why)
        self._note(name)

    def _finding(self, name: str, code: str | None, detail: str | None = None) -> None:
        self._poller.settings.cluster_registry.set_standing_finding(SLOT, name, Finding(name, code, detail) if code else None)

    def _note(self, name: str) -> None:
        if self._poller.signals is not None:
            self._poller.signals.note_self_login(name, self.view(name))

    @staticmethod
    def _as(cluster: ClusterConfig, held: _Session) -> ClusterConfig:
        return dataclasses.replace(cluster, token_value=held.session.token, user_self_login=False,
                                   ldap_connection_bootstrap=None)


__all__ = ["EVENTS", "MARGIN", "ONE_ATTEMPT", "SLOT", "SelfLoginSessions", "renew_at"]
```

<!-- block: local-development/gsd/poller.py | edit -->
```python

from __future__ import annotations

import logging
import os
import threading
```

```python

from __future__ import annotations

import dataclasses
import logging
import os
import threading
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from .config import CREDENTIAL_LOOKUP, ClusterConfig, ConfigError, PlatformNamespaces, Settings, remote_policy
from .home import PLATFORM_CONTROLLER_BINDINGS
from .kube import (AUTH_FAILED, OK, SERVICE_ACCOUNT_KIND, SUBJECT_KINDS, UNREACHABLE, USER_KIND, ClusterClient,
                   ClusterError, GroupSyncView, GroupView, dn_equal, is_platform_user)
```

```python
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from .config import (CREDENTIAL_LOOKUP, CREDENTIAL_SELF_LOGIN, ClusterConfig, ConfigError, PlatformNamespaces, Settings,
                     remote_policy)
from .home import PLATFORM_CONTROLLER_BINDINGS
from .kube import (AUTH_FAILED, OK, SERVICE_ACCOUNT_KIND, SUBJECT_KINDS, UNREACHABLE, USER_KIND, ClusterClient,
                   ClusterError, GroupSyncView, GroupView, dn_equal, is_platform_user)
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
        from .fleetlookup import CredentialGate
        self._lookups: dict[str, _LookupState] = {}
        self._credential_gate = CredentialGate()

    def _maybe_backup(self) -> None:
        """Snapshot the irreplaceable history on its own slower schedule.
```

```python
        from .fleetlookup import CredentialGate
        self._lookups: dict[str, _LookupState] = {}
        self._credential_gate = CredentialGate()
        # SPEC_S4c (#285): the self-login sessions, consulted by each self-login cluster's own poll thread; and
        # the daily ping's stand-downs already announced, so a gated account is said once (§3.4).
        from .selflogin import SelfLoginSessions
        self.self_login = SelfLoginSessions(self)
        self._ping_said: set[tuple[str, str]] = set()

    def _maybe_backup(self) -> None:
        """Snapshot the irreplaceable history on its own slower schedule.
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
                log.debug("%s: not leader, skipping poll", cluster.name)
                self._stop.wait(min(self.settings.poll_interval_seconds, STANDBY_RECHECK_SECONDS))
                continue
            try:
                poll_started = time.monotonic()
                poll_once(self.store, cluster, self.settings.request_timeout_seconds,
                          access_group_dn=self.settings.cluster_access_group,
                          identities_read=self.settings.identities_read_enabled)
                if self.signals is not None:
                    # The whole poll, success or degraded — a poll that needs the full
                    # timeout to fail is the one worth seeing. Set only by the replica
```

```python
                log.debug("%s: not leader, skipping poll", cluster.name)
                self._stop.wait(min(self.settings.poll_interval_seconds, STANDBY_RECHECK_SECONDS))
                continue
            if current.credential_kind == CREDENTIAL_SELF_LOGIN:
                # SPEC_S4c §3.6: the session IS the credential — acquired, renewed or refused here, before the poll,
                # and substituted as the token for this whole cycle; none this cycle skips the poll, never fails it.
                try:
                    polled = self.self_login.credential_for(current)
                except Exception:  # noqa: BLE001 - a poll thread must never die silently
                    log.exception("%s: self-login raised; the cluster is not polled this cycle", current.name)
                    polled = None
                if polled is None:
                    self._wait_cycle(started, own_stop)
                    continue
                cluster = polled
            try:
                poll_started = time.monotonic()
                outcome = poll_once(self.store, cluster, self.settings.request_timeout_seconds,
                                    access_group_dn=self.settings.cluster_access_group,
                                    identities_read=self.settings.identities_read_enabled)
                if current.credential_kind == CREDENTIAL_SELF_LOGIN:
                    self.self_login.poll_answered(current, outcome)
                if self.signals is not None:
                    # The whole poll, success or degraded — a poll that needs the full
                    # timeout to fail is the one worth seeing. Set only by the replica
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
                "%s poll cycle took %.2fs; next binding refresh in %.0fs",
                cluster.name, elapsed, max(0.0, next_binding_refresh - time.monotonic()),
            )
            wait = max(1.0, self.settings.poll_interval_seconds - elapsed)
            # Either event ends the wait: the poller's, or this cluster's own.
            deadline = time.monotonic() + wait
            while not self._stop.is_set() and not own_stop.is_set() and time.monotonic() < deadline:
                self._stop.wait(min(1.0, max(0.0, deadline - time.monotonic())))
        if own_stop.is_set():
            log.info("%s: its Secret is gone; the poll thread stops (history kept)", cluster.name)

    def _start_cluster_thread(self, cluster: ClusterConfig) -> None:
        with self._threads_lock:
            self._cluster_stops[cluster.name] = threading.Event()
```

```python
                "%s poll cycle took %.2fs; next binding refresh in %.0fs",
                cluster.name, elapsed, max(0.0, next_binding_refresh - time.monotonic()),
            )
            self._wait_cycle(started, own_stop)
        # A self-login session is revoked on the thread's way out: disabled, retired or stopping (SPEC_S4c B5).
        self.self_login.stop(cluster.name)
        if own_stop.is_set():
            log.info("%s: its Secret is gone; the poll thread stops (history kept)", cluster.name)

    def _wait_cycle(self, started: datetime, own_stop: threading.Event) -> None:
        """The rest of this cluster's poll interval. Either event ends the wait: the poller's, or this cluster's own."""
        wait = max(1.0, self.settings.poll_interval_seconds - (datetime.now(UTC) - started).total_seconds())
        deadline = time.monotonic() + wait
        while not self._stop.is_set() and not own_stop.is_set() and time.monotonic() < deadline:
            self._stop.wait(min(1.0, max(0.0, deadline - time.monotonic())))

    def _start_cluster_thread(self, cluster: ClusterConfig) -> None:
        with self._threads_lock:
            self._cluster_stops[cluster.name] = threading.Event()
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
        write wakes discovery so the cluster polls within seconds rather than at the next cadence."""
        from .clusterconfig.events import event
        from .clusterconfig.writer import secret_name_for
        from .fleetlookup import LOOKUP_ATTEMPTS, LookupRefused, lookup
        registry = self.settings.cluster_registry
        if registry.error:
            return  # An incomplete inventory cannot authorize a login from stale intent.
```

```python
        write wakes discovery so the cluster polls within seconds rather than at the next cadence."""
        from .clusterconfig.events import event
        from .clusterconfig.writer import secret_name_for
        from .fleetlookup import LOOKUP_ATTEMPTS, LookupRefused, fleet_account, lookup
        from .fleetstate import ClaimHeld, FleetStateUnavailable
        registry = self.settings.cluster_registry
        if registry.error:
            return  # An incomplete inventory cannot authorize a login from stale intent.
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
        host, namespace = self.settings.host_cluster(), own_namespace()
        if host is None or not namespace:
            return    # `_discover_once` announced it
        # ONE RETRIEVER PER ESTATE (SPEC_S4 §6), the runtime half: above one replica election is off, so
        # `elector` is None and every replica would reach here — and a Secret-declared mode is invisible
        # to the render's refusal (review of #295, P0-2). The switch itself is checked inside `lookup`.
```

```python
        host, namespace = self.settings.host_cluster(), own_namespace()
        if host is None or not namespace:
            return    # `_discover_once` announced it
        client = ClusterClient(host, timeout=self.settings.request_timeout_seconds)
        # ONE RETRIEVER PER ESTATE (SPEC_S4 §6), the runtime half: above one replica election is off, so
        # `elector` is None and every replica would reach here — and a Secret-declared mode is invisible
        # to the render's refusal (review of #295, P0-2). The switch itself is checked inside `lookup`.
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
                    action="run one replica for a release that retrieves credentials (SPEC_S4 §6, one retriever per estate)",
                    spent=False), now)
                continue
            try:
                result = lookup(cluster, self.settings, ClusterClient(host, timeout=self.settings.request_timeout_seconds),
                                own_namespace=namespace, gate=self._credential_gate)
            except LookupRefused as exc:
                self._lookup_failed(state, name, secret, exc, now)
                continue
            self._lookups.pop(name, None)
            registry.set_lookup_finding(name, None)
            event(discovery_log, logging.INFO, "fleet-lookup", cluster=name, account=result.account, secret=result.secret,
```

```python
                    action="run one replica for a release that retrieves credentials (SPEC_S4 §6, one retriever per estate)",
                    spent=False), now)
                continue
            # THE ACCOUNT LEASE FIRST (SPEC_S4c §3.3): no claim, no bind. A live claim is someone else binding as
            # this account now — silent, the next cycle tries; an unreadable Lease is a free finding (fail closed).
            try:
                lease = self._fleet_lease(client, namespace, fleet_account(self.settings, cluster))
                lease.claim()
            except ClaimHeld:
                continue
            except (LookupRefused, FleetStateUnavailable) as exc:
                self._lookup_failed(state, name, secret, exc, now)
                continue
            retrieved = False
            try:
                result = lookup(cluster, self.settings, client, own_namespace=namespace, gate=self._credential_gate,
                                lease=lease)
                retrieved = True
            except LookupRefused as exc:
                self._lookup_failed(state, name, secret, exc, now)
                continue
            finally:
                # A password that works retires the entry an older one left on the Lease.
                lease.release(**({"refused": None} if retrieved else {}))
            self._lookups.pop(name, None)
            registry.set_lookup_finding(name, None)
            event(discovery_log, logging.INFO, "fleet-lookup", cluster=name, account=result.account, secret=result.secret,
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
                attempt=f"{state.attempts}/{LOOKUP_ATTEMPTS}", retry_in=None if wait is None else f"{wait:g}",
                gave_up="true" if state.gave_up else None, action=action, detail=exc.detail, secrets=exc.secrets)

    def _run_discovery(self) -> None:
        """The discovery stage on its own cadence, `discoveryIntervalSeconds` (SPEC_S1 C3; off the binding
        cadence since chart 0.56.0), after the synchronous one in start(); a write from the tab shortens
```

```python
                attempt=f"{state.attempts}/{LOOKUP_ATTEMPTS}", retry_in=None if wait is None else f"{wait:g}",
                gave_up="true" if state.gave_up else None, action=action, detail=exc.detail, secrets=exc.secrets)

    # ── SPEC_S4c (#285): the account Lease and the daily ping ────────────────────────────────────────

    def _fleet_lease(self, client: ClusterClient, namespace: str, account: str):
        from .fleetstate import FleetLease, claim_seconds
        return FleetLease(client, namespace, account, claim_seconds=claim_seconds(self.settings))

    def _host_client(self) -> tuple[ClusterClient, str] | None:
        """The host cluster's client — the pod's own ServiceAccount — and the pod's namespace, or None."""
        host, namespace = self.settings.host_cluster(), own_namespace()
        if host is None or not namespace:
            return None
        return ClusterClient(host, timeout=self.settings.request_timeout_seconds), namespace

    def _ping_accounts(self) -> None:
        """One real read per fleet account per cadence (SPEC_S4c §3.4) — the daily ping, on the discovery thread,
        after the lookups. Every account in use has its Lease read each cadence, on every replica, so the tab and
        /metrics serve the same instants and the same gate on a standby; an account whose clusters the lookup
        retrieved is pinged against ONE of them — the `lookup-account` their Secrets record, in rotation by name —
        through `lookup(write=False)` under the account Lease's claim, by the leader alone."""
        from .clusterconfig.events import event, failure
        from .clusterconfig.parser import Finding
        from .clusterconfig.writer import secret_name_for
        from .fleetlookup import LookupRefused, fleet_password, lookup
        from .fleetstate import ClaimHeld, FleetStateUnavailable, lease_digest, lease_name, stamp
        registry = self.settings.cluster_registry
        if registry.error:
            return
        accounts: dict[str, list[ClusterConfig]] = {}      # every account in use -> the clusters its ping may read
        for c in self.settings.effective_clusters():
            named = c.ldap_connection_bootstrap or self.settings.fleet_account_username
            if c.enabled and c.token_source == CREDENTIAL_LOOKUP and c.lookup_account:
                accounts.setdefault(c.lookup_account, []).append(c)
            elif c.enabled and c.connection_mode is not None and named:
                accounts.setdefault(named, [])
        registry.prune_standing("ping", {c.name for group in accounts.values() for c in group})
        found = self._host_client()
        if found is None:
            return
        client, namespace = found
        views = dict(self.signals.fleet_accounts()) if self.signals is not None else {}
        leader = self.elector is None or self.elector.is_leader
        for account, clusters in sorted(accounts.items()):
            names = sorted(c.name for c in clusters)
            lease = self._fleet_lease(client, namespace, account)
            try:
                record = lease.read()
            except FleetStateUnavailable as exc:
                self._ping_finding(names[0], exc, account)
                continue                                   # the last view stands: never zeroed on a failed read
            views[account] = record.view()
            if not (leader and clusters and self.settings.fleet_ping_enabled):
                continue
            # ROTATION BY NAME (§3.4): the first after the last target, wrapping — over N cadences every target is
            # read once, so a grant revoked on one is found naming it.
            last = record.ping_last_target
            pick = next((n for n in names if last is None or n > last), names[0])
            target = next(c for c in clusters if c.name == pick)
            try:
                password = fleet_password(client, self.settings, namespace)
            except LookupRefused as exc:
                self._ping_finding(target.name, exc, account)
                continue
            digest, now = lease_digest(account, password), datetime.now(UTC)
            entry = record.gated(digest)
            if entry is not None:
                # STANDS DOWN on either kind of gated entry (§3.4): a 500 may be a locked account's code 19, and
                # one more bind a day against it is the walk in a health check's clothing. Said once.
                if (account, digest) not in self._ping_said:
                    self._ping_said.add((account, digest))
                    action = (f"not pinged again until the fleet password Secret changes, or the entry on Lease "
                              f"{lease_name(account)} is removed and the pod restarted; the gate is re-read every cycle "
                              f"at no cost")
                    said = (f"{entry.get('target') or 'an entry this dashboard cannot read'} answered {entry.get('code')} "
                            f"at {entry.get('at') or 'an unrecorded instant'}")
                    failure(discovery_log, "fleet-ping-failed", phase="credential", outcome=entry.get("code"),
                            account=account, target=target.name, gave_up="true", suspended=account, scope="ping",
                            action=action, detail=said)
                    registry.set_standing_finding("ping", target.name, Finding(
                        secret_name_for(target.name), entry.get("code"), f"the daily ping for {account} stands down: "
                                                                          f"{said} — {action}"))
                continue
            interval = timedelta(seconds=self.settings.fleet_ping_interval_seconds)
            if (record.ping_last_attempt is not None and now - record.ping_last_attempt < interval
                    and record.ping_digest == digest):
                continue                                   # not due: once per (account, password) per interval (B3)
            try:
                # The attempt is recorded WITH the claim, on the read this decision rests on: a second replica, or
                # a crash between the claim and the bind, cannot ping twice (B3).
                lease.claim(record, ping_last_attempt=stamp(now), ping_last_target=target.name, ping_digest=digest)
            except ClaimHeld:
                continue
            except FleetStateUnavailable as exc:
                self._ping_finding(target.name, exc, account)
                continue
            changes: dict[str, str | None] = {}
            try:
                # `onboarding=()`: the ping must never write #293's per-target success mark (SPEC_S5 §3.3).
                result = lookup(dataclasses.replace(target, ldap_connection_bootstrap=account, onboarding=()),
                                self.settings, client, own_namespace=namespace, gate=self._credential_gate,
                                write=False, lease=lease)
            except LookupRefused as exc:
                changes = {"ping_last_outcome": exc.code}
                failure(discovery_log, "fleet-ping-failed", phase="credential", outcome=exc.code, account=account,
                        target=target.name, attempt="1/1", gave_up="true" if exc.gated else None, action=exc.action,
                        detail=exc.detail, secrets=exc.secrets)
                registry.set_standing_finding("ping", target.name, Finding(secret_name_for(target.name), exc.code,
                                                                            f"{exc.detail} — {exc.action}"))
            else:
                changes = {"ping_last_ok": stamp(now), "ping_last_outcome": "ok", "refused": None}
                self._ping_said = {k for k in self._ping_said if k[0] != account}
                registry.set_standing_finding("ping", target.name, None)
                event(discovery_log, logging.INFO, "fleet-ping", account=account, target=target.name,
                      last_used=result.sa_token.last_used, last_ok=stamp(now), secrets=result.secrets)
            finally:
                views[account] = (lease.release(**changes) or record).view()
        if self.signals is not None:
            self.signals.note_fleet_accounts({a: v for a, v in views.items() if a in accounts})

    def _ping_finding(self, target: str, exc, account: str) -> None:
        """A free ping failure — no password Secret, an unreadable Lease — announced when it appears."""
        from .clusterconfig.events import failure
        from .clusterconfig.parser import Finding
        from .clusterconfig.writer import secret_name_for
        registry = self.settings.cluster_registry
        finding = Finding(secret_name_for(target), exc.code, f"{exc.detail} — {exc.action}")
        if finding not in registry.findings():
            failure(discovery_log, "fleet-ping-failed", phase="credential", outcome=exc.code, account=account,
                    target=target, action=exc.action, detail=exc.detail)
        registry.set_standing_finding("ping", target, finding)

    def _run_discovery(self) -> None:
        """The discovery stage on its own cadence, `discoveryIntervalSeconds` (SPEC_S1 C3; off the binding
        cadence since chart 0.56.0), after the synchronous one in start(); a write from the tab shortens
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
                self._discover_once()
                self._reconcile_threads()
                self._retrieve_pending()
            except Exception:  # noqa: BLE001 - the discovery thread must never die silently
                log.exception("unhandled error discovering cluster Secrets")

```

```python
                self._discover_once()
                self._reconcile_threads()
                self._retrieve_pending()
                self._ping_accounts()
            except Exception:  # noqa: BLE001 - the discovery thread must never die silently
                log.exception("unhandled error discovering cluster Secrets")

```

<!-- block: local-development/gsd/poller.py | edit -->
```python
                continue
            self._start_cluster_thread(cluster)
        if self.settings.cluster_secrets_enabled:
            if any(c.enabled and c.credential_kind == CREDENTIAL_LOOKUP for c in effective):
                # SPEC_S4b: a cluster awaiting its lookup does not wait a whole cadence for it. The
                # lookup runs on the thread, never here — a target that is down must not hold up start.
                self._discover_now.set()
            thread = threading.Thread(target=self._run_discovery, name="cluster-secrets", daemon=True)
            thread.start()
```

```python
                continue
            self._start_cluster_thread(cluster)
        if self.settings.cluster_secrets_enabled:
            if any(c.enabled and (c.connection_mode is not None or c.token_source == CREDENTIAL_LOOKUP) for c in effective):
                # SPEC_S4b: a cluster awaiting its lookup does not wait a whole cadence for it; SPEC_S4c §3.4: every
                # replica reads the fleet accounts' Leases within seconds of a restart, so /metrics and the tab do
                # not start blank. Both run on the thread, never here — a target that is down must not hold up start.
                self._discover_now.set()
            thread = threading.Thread(target=self._run_discovery, name="cluster-secrets", daemon=True)
            thread.start()
```

<!-- block: local-development/gsd/metrics.py | edit -->
```python
        self._report_system_at: str | None = None
        self._console_url: str | None = None
        self._grafana_url: str | None = None

    def membership_change_totals(self, store, cluster_ids) -> dict[tuple[str, str], int]:
        """Advance each cluster's watermark over the rows committed since the last call and return
```

```python
        self._report_system_at: str | None = None
        self._console_url: str | None = None
        self._grafana_url: str | None = None
        # SPEC_S4c (#285): every fleet account's Lease as the discovery thread last read it, and each self-login
        # cluster's session — what the tab and /metrics serve, the same on a standby as on the leader.
        self._fleet: dict[str, dict] = {}
        self._self_login: dict[str, dict] = {}

    def membership_change_totals(self, store, cluster_ids) -> dict[tuple[str, str], int]:
        """Advance each cluster's watermark over the rows committed since the last call and return
```

<!-- block: local-development/gsd/metrics.py | edit -->
```python
        with self._lock:
            return self._grafana_url

    def note_report_system(self, view: dict | None, at: str) -> None:
        """The report service's self-report as the usage feed carried it; None when the feed had
        none (an older build) — the page then says unavailable rather than showing a stale block."""
```

```python
        with self._lock:
            return self._grafana_url

    def note_fleet_accounts(self, views: dict[str, dict]) -> None:
        """Each fleet account's Lease view (`gsd/fleetstate.py#FleetRecord.view`), replaced once per discovery
        cadence; an account whose read failed keeps its last view — never zeroed on a failure to read."""
        with self._lock:
            self._fleet = dict(views)

    def fleet_accounts(self) -> dict[str, dict]:
        with self._lock:
            return dict(self._fleet)

    def note_self_login(self, cluster: str, view: dict | None) -> None:
        """A self-login cluster's session (`gsd/selflogin.py#SelfLoginSessions.view`); None forgets the cluster."""
        with self._lock:
            if view is None:
                self._self_login.pop(cluster, None)
            else:
                self._self_login[cluster] = view

    def self_login(self, cluster: str) -> dict | None:
        with self._lock:
            return self._self_login.get(cluster)

    def note_report_system(self, view: dict | None, at: str) -> None:
        """The report service's self-report as the usage feed carried it; None when the feed had
        none (an older build) — the page then says unavailable rather than showing a stale block."""
```

<!-- block: local-development/gsd/metrics.py | edit -->
```python
                backup_ts.add_metric([], newest)
        yield backup_ts


def build_registry(store: StorageBackend, grace: timedelta, elector=None,
                   signals: RuntimeSignals | None = None, settings=None,
```

```python
                backup_ts.add_metric([], newest)
        yield backup_ts

        # SPEC_S4c §3.9: the fleet account, UNLABELLED — /metrics is public and the account is a username, the
        # target adds nothing, and a digest of a guessable username is a name in a hat.
        fleet_ok = GaugeMetricFamily(
            "gsd_fleet_account_last_ok_timestamp_seconds",
            "Unix time of the OLDEST last successful daily ping across the fleet accounts — the most stale account "
            "is the one to alert on: (time() - this) > 2 * clusterConfig.fleetAccount.ping.intervalSeconds. Absent "
            "until a ping has succeeded: absence means never, not zero. Read from the account Leases, the same on "
            "every replica.",
            labels=[],
        )
        ping_enabled = GaugeMetricFamily(
            "gsd_fleet_account_ping_enabled",
            "1 when the daily ping is configured on. While this is 1, absence of "
            "gsd_fleet_account_last_ok_timestamp_seconds means no ping has ever succeeded.",
            labels=[],
        )
        suspended = GaugeMetricFamily(
            "gsd_fleet_account_suspended",
            "1 when a fleet account's Lease holds a refused entry: a login was refused or answered without a "
            "session, and nothing binds as that account with that password until it changes.",
            labels=[],
        )
        enabled = getattr(self.settings, "fleet_ping_enabled", None)
        if enabled is not None:
            ping_enabled.add_metric([], 1 if enabled else 0)
        if self.signals is not None:
            views = list(self.signals.fleet_accounts().values())
            oks = [ok for ok in (_epoch(v.get("last_ok")) for v in views) if ok is not None]
            if oks:
                fleet_ok.add_metric([], min(oks))
            suspended.add_metric([], 1 if any(v.get("suspended") for v in views) else 0)
        yield from (fleet_ok, ping_enabled, suspended)


def build_registry(store: StorageBackend, grace: timedelta, elector=None,
                   signals: RuntimeSignals | None = None, settings=None,
```

<!-- block: local-development/gsd/api.py | edit -->
```python
from .activity import EMAIL_HEADER, INTERACTION_HEADER, USER_HEADER, ActivityRecorder
from .home import HOME_CHANGES_DAYS, HOME_EVENTS_LIMIT, derive_answer, group_changes
from .config import (
    IDENTITY_NONE, IDENTITY_SAME_AS_HOST, VISIBILITY_HIDDEN, VISIBILITY_INHERIT,
    VISIBILITY_REMOTE_SAR, VISIBILITY_SELF_ONLY, Settings, load_settings, remote_policy,
)
from .kube import REMOTE_FAILURE_HOLD_SECONDS, TIER_ALL, TIER_SELF, ClusterClient, RemoteTierResolvers, TierResolver
```

```python
from .activity import EMAIL_HEADER, INTERACTION_HEADER, USER_HEADER, ActivityRecorder
from .home import HOME_CHANGES_DAYS, HOME_EVENTS_LIMIT, derive_answer, group_changes
from .config import (
    CREDENTIAL_SELF_LOGIN, IDENTITY_NONE, IDENTITY_SAME_AS_HOST, VISIBILITY_HIDDEN, VISIBILITY_INHERIT,
    VISIBILITY_REMOTE_SAR, VISIBILITY_SELF_ONLY, Settings, load_settings, remote_policy,
)
from .kube import REMOTE_FAILURE_HOLD_SECONDS, TIER_ALL, TIER_SELF, ClusterClient, RemoteTierResolvers, TierResolver
```

<!-- block: local-development/gsd/api.py | edit -->
```python
                "status": row.get("status"), "last_poll": row.get("last_poll"), "error": row.get("message"),
                "retired": False, "onboarding_configmap": c.onboarding[0] if c.onboarding else None,
            })
        # A cluster the store still holds but no source names any more — a Secret that vanished, a values
        # entry removed — is retired (enabled=0, history kept, #96). The tab shows it as such rather than
        # letting it disappear: its rows are still there, and the reader should know why.
```

```python
                "status": row.get("status"), "last_poll": row.get("last_poll"), "error": row.get("message"),
                "retired": False, "onboarding_configmap": c.onboarding[0] if c.onboarding else None,
            })
            if c.credential_kind == CREDENTIAL_SELF_LOGIN:
                # SPEC_S4c §3.10: the session's instants — never an age; the page computes one where it repaints.
                clusters[-1]["session"] = signals.self_login(c.name) or {"state": "none", "expires_at": None,
                                                                          "renew_at": None}
        # A cluster the store still holds but no source names any more — a Secret that vanished, a values
        # entry removed — is retired (enabled=0, history kept, #96). The tab shows it as such rather than
        # letting it disappear: its rows are still there, and the reader should know why.
```

<!-- block: local-development/gsd/api.py | edit -->
```python
            "configmaps": {"enabled": settings.cluster_secrets_enabled, "label": CONFIG_SELECTOR},
            "clusters": clusters,
            "findings": [f.public() for f in registry.findings()],
        }

    # ── SPEC_S2: the Cluster Configurations tab's writes ─────────────────────────────────────────────
```

```python
            "configmaps": {"enabled": settings.cluster_secrets_enabled, "label": CONFIG_SELECTOR},
            "clusters": clusters,
            "findings": [f.public() for f in registry.findings()],
            # SPEC_S4c §3.10: the daily ping and each fleet account's Lease, as instants.
            "fleet": {"ping": {"enabled": settings.fleet_ping_enabled,
                               "interval_seconds": settings.fleet_ping_interval_seconds},
                      "accounts": [{"username": account, **view}
                                   for account, view in sorted(signals.fleet_accounts().items())]},
        }

    # ── SPEC_S2: the Cluster Configurations tab's writes ─────────────────────────────────────────────
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
  const kind = c.credential === "bearer" ? "bearerToken" : c.credential === "in-cluster" ? "serviceAccount" : c.credential;
  // a retired row from before S1 recorded the kind carries "": say so rather than printing a bare badge
  let out = kind ? `${esc(kind)} ${ccBadge("ok", "set")}` : `<span class="muted">unknown</span>`;
  const secretRow = ccSourceKind(c) === "secret";
  if (c.onboarding_configmap && !c.retired) {
    out += ` <span class="cc-hint">managed by ConfigMap ${esc(c.onboarding_configmap)} — edit the stanza there</span>`;
```

```html
  const kind = c.credential === "bearer" ? "bearerToken" : c.credential === "in-cluster" ? "serviceAccount" : c.credential;
  // a retired row from before S1 recorded the kind carries "": say so rather than printing a bare badge
  let out = kind ? `${esc(kind)} ${ccBadge("ok", "set")}` : `<span class="muted">unknown</span>`;
  // SPEC_S4c §3.10: a self-login cluster's credential is its session — say when it expires, as an instant.
  const s = c.session;
  if (s) out += ` · ${s.expires_at ? `expires <span class="mono">${fmtStamp(s.expires_at)}</span>` : esc(s.state === "suspended" ? "suspended" : "no session yet")}`;
  const secretRow = ccSourceKind(c) === "secret";
  if (c.onboarding_configmap && !c.retired) {
    out += ` <span class="cc-hint">managed by ConfigMap ${esc(c.onboarding_configmap)} — edit the stanza there</span>`;
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
        the namespace will still delete a UI-written Secret unless it honours <span class="mono">groupsync-dashboard.io/managed-by: ui</span>.</p>
    </aside></div></section>`;
}
function clusterConfigPage() {
  const d = data.clusterconfigs;
  if (!d) return `<section class="card"><h2>Cluster Configurations</h2><div class="empty-note">Loading…</div></section>`;
```

```html
        the namespace will still delete a UI-written Secret unless it honours <span class="mono">groupsync-dashboard.io/managed-by: ui</span>.</p>
    </aside></div></section>`;
}
/* SPEC_S4c §3.10: one row per fleet account — when the daily ping last confirmed it, on which cluster, and what the
   last ping said; `never` before the first success, and `suspended` when its Lease holds a refused entry. */
function ccFleetRows(f) {
  return ((f && f.accounts) || []).map((a) => {
    const seen = a.last_ok
      ? `last confirmed <span class="mono">${fmtStamp(a.last_ok)}</span> on ${esc(a.last_target || "—")} · ${esc(a.last_outcome || "")}`
      : "not yet confirmed by the daily ping";
    const n = (a.suspended || []).length;
    return `<div class="cc-kv" data-cc-fleet="${esc(a.username)}"><span class="k">fleet account</span><span class="v"><span class="mono">${esc(a.username)}</span> · ${seen}${n ? ` ${ccBadge("critical", "suspended")}` : ""}</span></div>`;
  }).join("");
}
function clusterConfigPage() {
  const d = data.clusterconfigs;
  if (!d) return `<section class="card"><h2>Cluster Configurations</h2><div class="empty-note">Loading…</div></section>`;
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
    <div class="cc-kv"><span class="k">ConfigMap selector</span><span class="v mono">${esc((d.configmaps || {}).label || "")}</span></div>
    <div class="cc-kv"><span class="k">discovery</span><span class="v">${s.enabled === false ? "switched off (<code>clusterConfig.secrets.enabled: false</code>)"
      : `${n.secret} Secret${n.secret === 1 ? "" : "s"} carry the discovery label · last read <span class="mono">${s.last_discovery ? fmtStamp(s.last_discovery) : "never"}</span>${s.error ? `<div class="err">${esc(s.error)}</div>` : ""}`}</span></div>
    <div class="ns-controls"><a class="btn cc-btn-acc" id="cc-add-jump" href="#cc-add">Add cluster</a></div></section>`;
  const findings = (d.findings || []).map(ccFinding).join("")
    || `<div class="empty-note">No configuration findings. Refused Secrets and ConfigMap stanzas are listed here with their source and reason.</div>`;
```

```html
    <div class="cc-kv"><span class="k">ConfigMap selector</span><span class="v mono">${esc((d.configmaps || {}).label || "")}</span></div>
    <div class="cc-kv"><span class="k">discovery</span><span class="v">${s.enabled === false ? "switched off (<code>clusterConfig.secrets.enabled: false</code>)"
      : `${n.secret} Secret${n.secret === 1 ? "" : "s"} carry the discovery label · last read <span class="mono">${s.last_discovery ? fmtStamp(s.last_discovery) : "never"}</span>${s.error ? `<div class="err">${esc(s.error)}</div>` : ""}`}</span></div>
    ${ccFleetRows(d.fleet)}
    <div class="ns-controls"><a class="btn cc-btn-acc" id="cc-add-jump" href="#cc-add">Add cluster</a></div></section>`;
  const findings = (d.findings || []).map(ccFinding).join("")
    || `<div class="empty-note">No configuration findings. Refused Secrets and ConfigMap stanzas are listed here with their source and reason.</div>`;
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->
```yaml
      # Secret and the key if the grant is absent — it does not crash.
      rbac:
        create: true
  # WHAT `saTokenLookup` READS on every target (SPEC_S4b, #284): the poller ServiceAccount's permanent
  # token, held in a `kubernetes.io/service-account-token` Secret the operator chart creates beside
  # the ServiceAccount. One convention for the fleet — the operator chart provisions the same names
```

```yaml
      # Secret and the key if the grant is absent — it does not crash.
      rbac:
        create: true
    # THE DAILY PING (SPEC_S4c §3.4, #285): once per account per interval the dashboard logs in as
    # the fleet account and reads the poller ServiceAccount's token on ONE cluster the lookup retrieved,
    # stores nothing, and records on the account's Lease the instant it last succeeded. One bind per
    # interval for the whole fleet — never one per cluster. It stands down on a refusal (a wrong
    # password is sent once, not daily), and it rides config.discoveryIntervalSeconds, so it never
    # runs more often than discovery does.
    ping:
      enabled: true
      # Daily. Shorter buys little — a credential rarely breaks between two mornings — and every
      # increment multiplies the bind rate at a directory that is counting (SPEC_S3 §9.3.6).
      intervalSeconds: 86400
  # WHAT `saTokenLookup` READS on every target (SPEC_S4b, #284): the poller ServiceAccount's permanent
  # token, held in a `kubernetes.io/service-account-token` Secret the operator chart creates beside
  # the ServiceAccount. One convention for the fleet — the operator chart provisions the same names
```

<!-- block: charts/group-sync-dashboard/templates/configmap.yaml | edit -->
```yaml
    fleetPasswordSecretNamespace: {{ .Values.clusterConfig.fleetAccount.passwordSecret.namespace | quote }}
    fleetPasswordSecretName: {{ .Values.clusterConfig.fleetAccount.passwordSecret.name | quote }}
    fleetPasswordSecretKey: {{ .Values.clusterConfig.fleetAccount.passwordSecret.key | quote }}
    saTokenLookupSourceNamespace: {{ .Values.clusterConfig.saTokenLookup.sourceNamespace | quote }}
    saTokenLookupSourceServiceAccount: {{ .Values.clusterConfig.saTokenLookup.sourceServiceAccount | quote }}
    saTokenLookupTokenSecretName: {{ .Values.clusterConfig.saTokenLookup.tokenSecretName | quote }}
```

```yaml
    fleetPasswordSecretNamespace: {{ .Values.clusterConfig.fleetAccount.passwordSecret.namespace | quote }}
    fleetPasswordSecretName: {{ .Values.clusterConfig.fleetAccount.passwordSecret.name | quote }}
    fleetPasswordSecretKey: {{ .Values.clusterConfig.fleetAccount.passwordSecret.key | quote }}
    # The daily ping (SPEC_S4c §3.4): once per fleet account per interval, on the discovery cadence.
    fleetPingEnabled: {{ .Values.clusterConfig.fleetAccount.ping.enabled }}
    fleetPingIntervalSeconds: {{ .Values.clusterConfig.fleetAccount.ping.intervalSeconds }}
    saTokenLookupSourceNamespace: {{ .Values.clusterConfig.saTokenLookup.sourceNamespace | quote }}
    saTokenLookupSourceServiceAccount: {{ .Values.clusterConfig.saTokenLookup.sourceServiceAccount | quote }}
    saTokenLookupTokenSecretName: {{ .Values.clusterConfig.saTokenLookup.tokenSecretName | quote }}
```

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->
```yaml
{{- end -}}
{{- end -}}
{{- end -}}
{{- /* One retriever per estate (SPEC_S4 §6), held wherever a lookup is POSSIBLE and not only where a
       values stanza declares one (review of #295, P0-2): a Secret may declare the mode at any time,
       and above one replica election is off, so every replica would log in as the fleet account. */ -}}
```

```yaml
{{- end -}}
{{- end -}}
{{- end -}}
{{- /* SPEC_S4c §3.8: a self-login session is per process, so above one replica each would log in as the fleet
       account for every cluster on every renewal — the lookup's rule below, for the same reason. */ -}}
{{- range $name, $mode := $modeOf -}}
{{- if and (eq $mode "userSelfLogin") (gt (int $.Values.replicaCount) 1) -}}
{{- fail (printf "cluster %s declares userSelfLogin with replicaCount %d: a self-login session is per process, so each replica would log in as the fleet account for every cluster on every renewal. Use replicaCount 1 for a release that declares userSelfLogin." $name (int $.Values.replicaCount)) -}}
{{- end -}}
{{- end -}}
{{- /* One retriever per estate (SPEC_S4 §6), held wherever a lookup is POSSIBLE and not only where a
       values stanza declares one (review of #295, P0-2): a Secret may declare the mode at any time,
       and above one replica election is off, so every replica would log in as the fleet account. */ -}}
```

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->
```yaml
{{- end -}}
{{- end -}}

{{- /*
The KPI page's doors (grafana.url, console.url): empty is unset — the Grafana door absent, the console
discovered. A value must be an http(s) URL with a host and no query or fragment, the rule the app's
```

```yaml
{{- end -}}
{{- end -}}

{{- /*
Whether a fleet account is in use (SPEC_S3 §3.1; SPEC_S4c §3.8): the chart names one, or any cluster stanza declares a
connection mode — a stanza's ldapConnectionBootstrap names the username, but the password is still the chart's Secret.
"true" or "false". Shared by fleet-account-rbac.yaml (the password grant) and rbac.yaml (the fleet account's Lease).
*/ -}}
{{- define "gsd.fleetAccountInUse" -}}
{{- $fleet := (.Values.clusterConfig).fleetAccount | default dict -}}
{{- $inUse := not (empty ($fleet.username | default "")) -}}
{{- range .Values.clusters -}}
  {{- /* SKIP A NON-ENTRY RATHER THAN DEREFERENCE IT. Helm pads a list index set beyond the list's
         length with null, so `clusters[0]` can be nil; `gsd.validateClusters` refuses that BY NAME
         ("clusters[0] is not a cluster entry"), and reaching into it here would abort the render
         with a nil-pointer first — replacing a diagnosis with a stack trace. */ -}}
  {{- if kindIs "map" . -}}
    {{- if or .saTokenLookup .userSelfLogin -}}{{- $inUse = true -}}{{- end -}}
  {{- end -}}
{{- end -}}
{{- $inUse -}}
{{- end -}}

{{- /*
The KPI page's doors (grafana.url, console.url): empty is unset — the Grafana door absent, the console
discovered. A value must be an http(s) URL with a host and no query or fragment, the rule the app's
```

<!-- block: charts/group-sync-dashboard/templates/fleet-account-rbac.yaml | edit -->
```yaml
{{- $fleet := (.Values.clusterConfig).fleetAccount | default dict }}
{{- $ps := $fleet.passwordSecret | default dict }}
{{- $rbac := $ps.rbac | default dict }}
{{- /* In use when the chart names an account, or any cluster stanza declares a connection mode —
       a stanza's ldapConnectionBootstrap names the username but the password is still this one. */ -}}
{{- $inUse := not (empty ($fleet.username | default "")) }}
{{- range .Values.clusters }}
  {{- /* SKIP A NON-ENTRY RATHER THAN DEREFERENCE IT. Helm pads a list index set beyond the list's
         length with null, so `clusters[0]` can be nil; `gsd.validateClusters` refuses that BY NAME
         ("clusters[0] is not a cluster entry"), and reaching into it here would abort the render
         with a nil-pointer first — replacing a diagnosis with a stack trace. */ -}}
  {{- if kindIs "map" . }}
    {{- if or .saTokenLookup .userSelfLogin }}{{- $inUse = true }}{{- end }}
  {{- end }}
{{- end }}
{{- /* A WORD, NOT TRUTHINESS. `$rbac.create | default true` returns TRUE for an explicit `false`,
       because Helm's `default` treats false as empty — an opt-out that silently does not opt out.
       The same trap `enabled: "false"` fell into on a cluster stanza; read it the same way. */ -}}
```

```yaml
{{- $fleet := (.Values.clusterConfig).fleetAccount | default dict }}
{{- $ps := $fleet.passwordSecret | default dict }}
{{- $rbac := $ps.rbac | default dict }}
{{- /* In use: `gsd.fleetAccountInUse`, shared with rbac.yaml's Lease rule (SPEC_S4c §3.8). */ -}}
{{- $inUse := eq (include "gsd.fleetAccountInUse" .) "true" }}
{{- /* A WORD, NOT TRUTHINESS. `$rbac.create | default true` returns TRUE for an explicit `false`,
       because Helm's `default` treats false as empty — an opt-out that silently does not opt out.
       The same trap `enabled: "false"` fell into on a cluster stanza; read it the same way. */ -}}
```

<!-- block: charts/group-sync-dashboard/templates/rbac.yaml | edit -->
```yaml
    resourceNames: ["cluster"]
    verbs: ["get"]
  {{- end }}
  {{- if .Values.leaderElection.enabled }}
  # Leader election. Namespaced, so this belongs in a Role rather than the ClusterRole —
  # but keeping one object is simpler and the grant is confined to one named Lease anyway.
  - apiGroups: ["coordination.k8s.io"]
    resources: ["leases"]
    verbs: ["get", "create", "update"]
```

```yaml
    resourceNames: ["cluster"]
    verbs: ["get"]
  {{- end }}
  {{- if or .Values.leaderElection.enabled (eq (include "gsd.fleetAccountInUse" .) "true") }}
  # Leader election, and the fleet-account claim (SPEC_S4c §3.3): a second Lease under the same rule,
  # still the one resource this application writes. It renders when a fleet account is in use even with
  # election off, because above one replica election MUST be off and that is where a claim the API
  # server arbitrates matters most. Namespaced, so it belongs in a Role rather than the ClusterRole —
  # but keeping one object is simpler; `create` cannot be narrowed by resourceNames, so none is set.
  - apiGroups: ["coordination.k8s.io"]
    resources: ["leases"]
    verbs: ["get", "create", "update"]
```

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->
```yaml
# CHART 0.58.8 (2026-09-26), PATCH: gsd.validateClusters refuses a clusters[].apiUrl carrying userinfo,
# a query or a fragment, as the loader now does (#415), without repeating the value. Refuses only input the
# pod already could not use safely; no value default, RBAC or appVersion change.
version: 0.58.8
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
# id or display name — and a Find member box on the group page. /users rows gain `full_name`,
# nullable, the same field the members list already carried. Additive on the wire and in the UI,
```

```yaml
# CHART 0.58.8 (2026-09-26), PATCH: gsd.validateClusters refuses a clusters[].apiUrl carrying userinfo,
# a query or a fragment, as the loader now does (#415), without repeating the value. Refuses only input the
# pod already could not use safely; no value default, RBAC or appVersion change.
# CHART 0.59.0 (2026-09-26), MINOR: the credential lifecycle (#285, SPEC_S4c) — clusterConfig.fleetAccount.ping
# (enabled, intervalSeconds: on, daily) reaches the ConfigMap as fleetPingEnabled and fleetPingIntervalSeconds;
# the `leases` rule renders under leaderElection.enabled OR a fleet account in use (the account's claim Lease);
# a userSelfLogin stanza with replicaCount > 1 is refused. RBAC: the `leases` rule is added only where election
# is off and a fleet account is in use; nothing is removed. appVersion unchanged: the application code rides
# Epic C's release.
version: 0.59.0
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
# id or display name — and a Find member box on the group page. /users rows gain `full_name`,
# nullable, the same field the members list already carried. Additive on the wire and in the UI,
```

<!-- block: charts/group-sync-dashboard/README.md | edit -->
```markdown
| `rbac.namespaces` | `false` | adds `get`/`list` on `namespaces` (core group). Lets the report service's namespace report attest **absence** — "this namespace exists and has no grants" — instead of "none observed". Off by default: extra RBAC |
| `kyverno.enabled` | `true` | the Kyverno policy module (#165, #170): grants `list` on the policy reports (`wgpolicyk8s.io`, `openreports.io`) and the five CEL policy kinds (`policies.kyverno.io`, with their namespaced twins) and turns the poller's read on. Auto-detected per cluster — no policy-report API group is "not installed", said on the page, never zero results. Read-only: no `/status`, no write verb, never the deprecated `kyverno.io` family (the API says it will be removed in a future release; its results are counted so the page can say they exist) |
| `clusterConfig.secrets.enabled` | `true` | clusters declared as labelled Secrets in the release namespace (#230, `docs/specs/SPEC_S1_cluster_secrets.md`): a Role with `get`, `list`, `watch` on `secrets` and `configmaps` there, and the poller's discovery on `discoveryIntervalSeconds` — a Secret labelled `groupsync-dashboard.io/secret-type: cluster` carrying `name`, `server`, `config` (JSON: `bearerToken` or `oauth{username,password}`, `tlsClientConfig{caData,insecure}`) and the D2 options is polled like a `clusters[]` entry; the host is always `clusters[0]` and a Secret naming it is refused; a Secret that does not parse is a finding on `GET /api/clusterconfigs`, one that vanishes disables its cluster and keeps its history. ConfigMaps labelled `groupsync-dashboard.io/config-type: onboard` or `sideload` carry credential-free values-shaped stanzas in `data.clusters.yaml` (SPEC_S5, #293); the #284 lookup generates their Secrets. Conflicts load neither; generated credentials are pruned repeatedly after confirmed removal, behind the writes switch. See [the cluster stanza guide](../../docs/CLUSTER_STANZA.md) for prerequisites and recovery, and the [Argo CD / Flux onboarding examples](../../examples/cluster-onboarding/) for adding clusters through GitOps. The [manual Secret example](../../examples/cluster-secret/) explains why a `saTokenLookup` Secret must not be self-healed. `false` — no Role, no discovery, the `clusters[]` list alone. See [polling and discovery](../../docs/polling-and-discovery.md) for cadence, cleanup and refresh behaviour |
| `clusterConfig.secrets.writes.enabled` | `false` | the Cluster Configurations tab's writes (#230 S2, `docs/specs/SPEC_S2_cluster_configurations_tab.md`): `create`, `update`, `delete` join the `-cluster-secrets` Role so an administrator can add a cluster from the tab (the same labelled Secret a GitOps process would write, `gsd-cluster-<name>`, annotated `groupsync-dashboard.io/managed-by: ui`), rotate its bearer token in place, or delete it (the cluster retires, its history kept). The app writes only in its own namespace, only Secrets carrying the label (checked by the app — RBAC cannot scope a verb by label), only for a reader the cluster-admin tier admits (`visibility.clusterAdminSar`, #322 — never the wide tier the auditor passes) with a proxy-verified identity, one audit log line per write naming the person, the verb and the Secret; the credential never reaches a response, a log line, the database or `/metrics`. **Off by default**, a stated exception to the on-by-default rule: a write path on Secrets widens the dashboard's read-only posture (its only write anywhere is its own leader Lease), so it stays off until the operator turns it on — the default is pending the operator's A/B call of 2026-09-20; B flips it and removes the exception. Off, no write route is registered (a POST is a `405`) and the tab is read-only, its form still producing the Secret's YAML for a GitOps process to apply |
| `kyverno.metricsUrl` | `""` | the metrics endpoints the dashboard pod can reach, comma-separated, for the report breakers (`kyverno_breaker_total` / `kyverno_breaker_drops`, summed): reports a breaker dropped are results the page cannot show. Three circuits, one per controller, each on its own endpoint — in-cluster on the host cluster: `http://kyverno-svc-metrics.kyverno.svc:8000/metrics`, `http://kyverno-reports-controller-metrics.kyverno.svc:8000/metrics`, `http://kyverno-background-controller-metrics.kyverno.svc:8000/metrics`. Empty leaves the truncation state unknown, said on the page. One GET per endpoint per poll, for the host cluster only — a remote cluster's breaker is unmeasured |
| `kyverno.eventsRetentionDays` | `90` | the appeared/cleared history of problem results, pruned like the other event tables (`0` keeps forever). A policy report carries no history — it dies with its resource — so this table is the only memory of a finding |
```

```markdown
| `rbac.namespaces` | `false` | adds `get`/`list` on `namespaces` (core group). Lets the report service's namespace report attest **absence** — "this namespace exists and has no grants" — instead of "none observed". Off by default: extra RBAC |
| `kyverno.enabled` | `true` | the Kyverno policy module (#165, #170): grants `list` on the policy reports (`wgpolicyk8s.io`, `openreports.io`) and the five CEL policy kinds (`policies.kyverno.io`, with their namespaced twins) and turns the poller's read on. Auto-detected per cluster — no policy-report API group is "not installed", said on the page, never zero results. Read-only: no `/status`, no write verb, never the deprecated `kyverno.io` family (the API says it will be removed in a future release; its results are counted so the page can say they exist) |
| `clusterConfig.secrets.enabled` | `true` | clusters declared as labelled Secrets in the release namespace (#230, `docs/specs/SPEC_S1_cluster_secrets.md`): a Role with `get`, `list`, `watch` on `secrets` and `configmaps` there, and the poller's discovery on `discoveryIntervalSeconds` — a Secret labelled `groupsync-dashboard.io/secret-type: cluster` carrying `name`, `server`, `config` (JSON: `bearerToken` or `oauth{username,password}`, `tlsClientConfig{caData,insecure}`) and the D2 options is polled like a `clusters[]` entry; the host is always `clusters[0]` and a Secret naming it is refused; a Secret that does not parse is a finding on `GET /api/clusterconfigs`, one that vanishes disables its cluster and keeps its history. ConfigMaps labelled `groupsync-dashboard.io/config-type: onboard` or `sideload` carry credential-free values-shaped stanzas in `data.clusters.yaml` (SPEC_S5, #293); the #284 lookup generates their Secrets. Conflicts load neither; generated credentials are pruned repeatedly after confirmed removal, behind the writes switch. See [the cluster stanza guide](../../docs/CLUSTER_STANZA.md) for prerequisites and recovery, and the [Argo CD / Flux onboarding examples](../../examples/cluster-onboarding/) for adding clusters through GitOps. The [manual Secret example](../../examples/cluster-secret/) explains why a `saTokenLookup` Secret must not be self-healed. `false` — no Role, no discovery, the `clusters[]` list alone. See [polling and discovery](../../docs/polling-and-discovery.md) for cadence, cleanup and refresh behaviour |
| `clusterConfig.fleetAccount.ping.enabled` | `true` | the daily ping (#285, `docs/specs/SPEC_S4c_credential_lifecycle.md` §3.4): once per fleet account per interval, on the leader, the dashboard logs in as the account on ONE cluster the lookup retrieved (in rotation by name), reads the poller ServiceAccount's token Secret there and stores nothing. The instant it last succeeded is kept on the account's Lease (`gsd-fleet-<sha256(username)[:16]>`) and served on `GET /api/clusterconfigs`, the tab and `gsd_fleet_account_last_ok_timestamp_seconds`. One bind per interval for the whole fleet, never one per cluster; a refused or locked password stops it, said once, until the password changes |
| `clusterConfig.fleetAccount.ping.intervalSeconds` | `86400` | how often the ping confirms each account: daily. It rides `discoveryIntervalSeconds`, so it never runs more often than discovery; a shorter interval multiplies the bind rate at a directory that is counting |
| `clusterConfig.secrets.writes.enabled` | `false` | the Cluster Configurations tab's writes (#230 S2, `docs/specs/SPEC_S2_cluster_configurations_tab.md`): `create`, `update`, `delete` join the `-cluster-secrets` Role so an administrator can add a cluster from the tab (the same labelled Secret a GitOps process would write, `gsd-cluster-<name>`, annotated `groupsync-dashboard.io/managed-by: ui`), rotate its bearer token in place, or delete it (the cluster retires, its history kept). The app writes only in its own namespace, only Secrets carrying the label (checked by the app — RBAC cannot scope a verb by label), only for a reader the cluster-admin tier admits (`visibility.clusterAdminSar`, #322 — never the wide tier the auditor passes) with a proxy-verified identity, one audit log line per write naming the person, the verb and the Secret; the credential never reaches a response, a log line, the database or `/metrics`. **Off by default**, a stated exception to the on-by-default rule: a write path on Secrets widens the dashboard's read-only posture (its only write anywhere is its own leader Lease), so it stays off until the operator turns it on — the default is pending the operator's A/B call of 2026-09-20; B flips it and removes the exception. Off, no write route is registered (a POST is a `405`) and the tab is read-only, its form still producing the Secret's YAML for a GitOps process to apply |
| `kyverno.metricsUrl` | `""` | the metrics endpoints the dashboard pod can reach, comma-separated, for the report breakers (`kyverno_breaker_total` / `kyverno_breaker_drops`, summed): reports a breaker dropped are results the page cannot show. Three circuits, one per controller, each on its own endpoint — in-cluster on the host cluster: `http://kyverno-svc-metrics.kyverno.svc:8000/metrics`, `http://kyverno-reports-controller-metrics.kyverno.svc:8000/metrics`, `http://kyverno-background-controller-metrics.kyverno.svc:8000/metrics`. Empty leaves the truncation state unknown, said on the page. One GET per endpoint per poll, for the host cluster only — a remote cluster's breaker is unmeasured |
| `kyverno.eventsRetentionDays` | `90` | the appeared/cleared history of problem results, pruned like the other event tables (`0` keeps forever). A policy report carries no history — it dies with its resource — so this table is the only memory of a finding |
```

<!-- block: charts/group-sync-dashboard/README.md | edit -->
```markdown
retention still applies. See `docs/AUDIT_LOG_CAPTURE.md` and `docs/LOGIN_CAPTURE_QUICKCHECK.md`.

Three rules in the ClusterRole are conditional. `coordination.k8s.io/leases`
(`get`, `create`, `update`) renders only when `leaderElection.enabled`,
`rolebindings`/`clusterrolebindings` (`get`, `list`) only when `rbac.bindings`, and
`users` (`get`, `list`) only when `rbac.users`. Everything
else in it is `get`/`list`, and that Lease — the dashboard's own, which grants nobody
access to anything — is the only object it writes on any cluster.

A `patch` on rolebindings/clusterrolebindings used to render here when
`config.unmanagedAudit.mode` was `annotate`. The mode and the grant are both gone; see
```

```markdown
retention still applies. See `docs/AUDIT_LOG_CAPTURE.md` and `docs/LOGIN_CAPTURE_QUICKCHECK.md`.

Three rules in the ClusterRole are conditional. `coordination.k8s.io/leases`
(`get`, `create`, `update`) renders when `leaderElection.enabled` or a fleet account is in use
(`clusterConfig.fleetAccount.username`, or a stanza declaring a mode) — the election Lease and the
fleet account's claim (#285) —
`rolebindings`/`clusterrolebindings` (`get`, `list`) only when `rbac.bindings`, and
`users` (`get`, `list`) only when `rbac.users`. Everything
else in it is `get`/`list`, and that pair of Leases — the dashboard's own, which grant nobody
access to anything — are the only objects it writes on any cluster.

A `patch` on rolebindings/clusterrolebindings used to render here when
`config.unmanagedAudit.mode` was `annotate`. The mode and the grant are both gone; see
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
Since #315, every bound login failure gates that account and password on every target in this
process, for values, Secret and ConfigMap triggers alike. Successful ConfigMap sessions still spend only
their own target's budget; successful values/Secret logins are not globally one-shot. Account means the
exact configured username string: use one spelling for one directory identity. A restart or another
replica starts with an empty gate; durable, replica-shared protection remains #285's work. Keep one replica.

Companion to [`docs/CLUSTER_STANZA.md`](../../docs/CLUSTER_STANZA.md), which covers *what a stanza may
say*. This covers *what happens to the credential afterwards* — who holds it, what fails, and how an
```

```markdown
Since #315, every bound login failure gates that account and password on every target in this
process, for values, Secret and ConfigMap triggers alike. Successful ConfigMap sessions still spend only
their own target's budget; successful values/Secret logins are not globally one-shot. Account means the
exact configured username string: use one spelling for one directory identity. Since #285 the refusal is
also recorded on the fleet account's Lease (`gsd-fleet-<sha256(username)[:16]>` in the release namespace)
before the process's gate, and every login claims that Lease first, so a restart or another replica reads
it and does not send the password again; a success is still not recorded there. Keep one replica.

Companion to [`docs/CLUSTER_STANZA.md`](../../docs/CLUSTER_STANZA.md), which covers *what a stanza may
say*. This covers *what happens to the credential afterwards* — who holds it, what fails, and how an
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
| | the fleet LDAP account | the retrieved ServiceAccount token |
|---|---|---|
| used for | one retrieval, at onboarding | every poll, forever |
| how often it authenticates | once per cluster, while that cluster is awaiting a credential | never re-authenticates; the token is presented |
| lifetime | a directory password, rotated by policy | **no `exp` claim at all** |
| stored where | one Secret, named by `clusterConfig.fleetAccount.passwordSecret` | `gsd-cluster-<name>`, written by the retrieval |

The bind happens only while a cluster is *pending* a credential
(`gsd/poller.py#Poller._retrieve_pending` selects `credential_kind == CREDENTIAL_LOOKUP`). Once the
token is written, the cluster leaves that set and the LDAP account is not used for it again.

**Why the polling token carries no expiry.** A token that expires needs something to renew it, and
renewal means re-authenticating — which would turn a once-per-onboarding bind into a recurring one
```

```markdown
| | the fleet LDAP account | the retrieved ServiceAccount token |
|---|---|---|
| used for | one retrieval, at onboarding | every poll, forever |
| how often it authenticates | once per cluster, while that cluster is awaiting a credential; and once a day for the whole fleet, the daily ping (#285) | never re-authenticates; the token is presented |
| lifetime | a directory password, rotated by policy | **no `exp` claim at all** |
| stored where | one Secret, named by `clusterConfig.fleetAccount.passwordSecret` | `gsd-cluster-<name>`, written by the retrieval |

The retrieval binds only while a cluster is *pending* a credential
(`gsd/poller.py#Poller._retrieve_pending` selects `credential_kind == CREDENTIAL_LOOKUP`). Once the
token is written, the cluster leaves that set and is not retrieved again. The one later use of the LDAP
account is the daily ping (`gsd/poller.py#Poller._ping_accounts`, `clusterConfig.fleetAccount.ping`): once
per account per interval it logs in on ONE retrieved cluster, reads the token Secret there to confirm the
account still works, and stores nothing — confirming is not renewing.

**Why the polling token carries no expiry.** A token that expires needs something to renew it, and
renewal means re-authenticating — which would turn a once-per-onboarding bind into a recurring one
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
|---|---|---|
| static bearer token | the token, written by whoever created the Secret | the token |
| `saTokenLookup` | the token the retrieval fetched, plus provenance annotations | the token; the fleet account bound once to fetch it |
| `userSelfLogin` | — | **not built** — `gsd/config.py#CREDENTIAL_PENDING_REASONS` records it as #285's work |
| `oauth` (username/password) | — | **not built** — refused as `oauth-exchange-not-built` |

A retrieval-written Secret is recognisable by its annotations, which a hand-written one lacks:
```

```markdown
|---|---|---|
| static bearer token | the token, written by whoever created the Secret | the token |
| `saTokenLookup` | the token the retrieval fetched, plus provenance annotations | the token; the fleet account bound once to fetch it |
| `userSelfLogin` | — (nothing at rest) | the fleet account's own session, held in memory and renewed a fixed margin before it expires, `expires_at − min(2 h, ¼ × expires_in)` (#285, `gsd/selflogin.py#SelfLoginSessions`); a refused password suspends every self-login cluster on the account |
| `oauth` (username/password) | — | **not built** — refused as `oauth-exchange-not-built` |

A retrieval-written Secret is recognisable by its annotations, which a hand-written one lacks:
```

<!-- block: docs/CLUSTER_STANZA.md | edit -->
```markdown
use one spelling per identity. The ConfigMap trigger also marks a successful session (before the token
read), for that target only (#293). A gated password is not sent again in this process, including
after a rename, policy edit, or a later read/write failure. A TLS or connect failure
before the password is written may bind again. A restart or another replica binds
again. There is no durable or replica-shared claim until #285. A missing output after that budget was spent stays pending with a finding; fix the
cause and rotate the credential or deliberately restart after checking the account. Routine policy
edits need neither. Do not delete an output as
a way to remove the declaration; the source is the record. Turning discovery off suspends all cleanup;
```

```markdown
use one spelling per identity. The ConfigMap trigger also marks a successful session (before the token
read), for that target only (#293). A gated password is not sent again in this process, including
after a rename, policy edit, or a later read/write failure. A TLS or connect failure
before the password is written may bind again. Since #285 every login claims the fleet account's Lease
first, and a bound failure is recorded there before the process's gate, so a restart or another replica
does not send a refused password again; a successful session's mark is not on the Lease, so after a
restart that trigger may bind once more. A missing output after that budget was spent stays pending with a finding; fix the
cause and rotate the credential or deliberately restart after checking the account. Routine policy
edits need neither. Do not delete an output as
a way to remove the declaration; the source is the record. Turning discovery off suspends all cleanup;
```

<!-- block: docs/CLUSTER_STANZA.md | edit -->
```markdown
| `tokenFile` = the SA path | `in-cluster` | yes |
| `tokenEnv` or `tokenFile` | `file` | yes |
| `saTokenLookup: true` | `remote-lookup` | **after the lookup** — the dashboard logs in as the fleet account, reads the poller SA's token on the target and writes `gsd-cluster-<name>`, which then polls (SPEC_S4b); needs `clusterConfig.secrets.writes.enabled` |
| `userSelfLogin: true` | `self-login` | **no — pending** |
| a Secret's `bearerToken` | `bearer` | yes |
| a Secret's `oauth {username, password}` | `oauth` | **no — pending (#119 P2)** |

A *pending* cluster is listed on the Cluster Configurations tab with the reason, and is **not
polled** — deliberately, so it is never reported as `auth_failed` for a credential that was never
presented. The connection itself is S3b and is not built; S3a ships the keys.

## 3. TLS — how the API server is verified

```

```markdown
| `tokenFile` = the SA path | `in-cluster` | yes |
| `tokenEnv` or `tokenFile` | `file` | yes |
| `saTokenLookup: true` | `remote-lookup` | **after the lookup** — the dashboard logs in as the fleet account, reads the poller SA's token on the target and writes `gsd-cluster-<name>`, which then polls (SPEC_S4b); needs `clusterConfig.secrets.writes.enabled` |
| `userSelfLogin: true` | `self-login` | **on its own session** — the dashboard logs in as the fleet account on the target and polls with that session, renewed a fixed margin before it expires (SPEC_S4c §3.6); a refused password suspends every self-login cluster on the account. Refused above one replica |
| a Secret's `bearerToken` | `bearer` | yes |
| a Secret's `oauth {username, password}` | `oauth` | **no — pending (#119 P2)** |

A *pending* cluster is listed on the Cluster Configurations tab with the reason, and is **not
polled** — deliberately, so it is never reported as `auth_failed` for a credential that was never
presented. A `self-login` cluster is never pending: with no session it skips the poll, and the finding
says why.

## 3. TLS — how the API server is verified

```

<!-- block: docs/CLUSTER_STANZA.md | edit -->
```markdown
| 4 | remote + `tokenEnv` + `caBundleFile` | polled, pinned CA |
| 5 | remote + `tokenEnv` + `insecureSkipVerify` | polled, verification off |
| 6 | remote + `saTokenLookup` | retrieved on the next discovery cycle, then polled through its written Secret; renders only with `clusterConfig.secrets.writes.enabled` |
| 7 | remote + `userSelfLogin` | listed, pending, not polled |
| 8 | remote + `saTokenLookup` + `ldapConnectionBootstrap` | as 6, with a per-cluster bootstrap account |
| 9 | remote + `visibility: self-only` | every viewer is the self tier there |
| 10 | remote + `visibility: hidden` | polled, never served through `/api` |
```

```markdown
| 4 | remote + `tokenEnv` + `caBundleFile` | polled, pinned CA |
| 5 | remote + `tokenEnv` + `insecureSkipVerify` | polled, verification off |
| 6 | remote + `saTokenLookup` | retrieved on the next discovery cycle, then polled through its written Secret; renders only with `clusterConfig.secrets.writes.enabled` |
| 7 | remote + `userSelfLogin` | polled on its own session; renewed a fixed margin before expiry |
| 8 | remote + `saTokenLookup` + `ldapConnectionBootstrap` | as 6, with a per-cluster bootstrap account |
| 9 | remote + `visibility: self-only` | every viewer is the self tier there |
| 10 | remote + `visibility: hidden` | polled, never served through `/api` |
```

<!-- block: docs/CLUSTER_STANZA.md | edit -->
```markdown
| `saTokenLookup` without `clusterConfig.secrets.writes.enabled` | **refused** | starts; the tab reports `fleet-write-disabled` (a Secret-declared mode reaches this half) |
| `saTokenLookup` without `clusterConfig.secrets.enabled` | **refused** | starts; the cluster stays pending |
| `clusterConfig.secrets.writes.enabled` with `replicaCount > 1` — a lookup is possible, stanza or not | **refused** | starts; a lookup reports `fleet-write-disabled` (one retriever per estate, SPEC_S4 §6) |

The chart's guard covers the connection-mode and host rules; the remaining four are the loader's
alone, because `templates/configmap.yaml` passes `clusters` through with `toYaml` and the pod is
```

```markdown
| `saTokenLookup` without `clusterConfig.secrets.writes.enabled` | **refused** | starts; the tab reports `fleet-write-disabled` (a Secret-declared mode reaches this half) |
| `saTokenLookup` without `clusterConfig.secrets.enabled` | **refused** | starts; the cluster stays pending |
| `clusterConfig.secrets.writes.enabled` with `replicaCount > 1` — a lookup is possible, stanza or not | **refused** | starts; a lookup reports `fleet-write-disabled` (one retriever per estate, SPEC_S4 §6) |
| `userSelfLogin` with `replicaCount > 1` | **refused** | starts; the cluster reports `self-login-suspended` (a session is per process, SPEC_S4c §3.8) |

The chart's guard covers the connection-mode and host rules; the remaining four are the loader's
alone, because `templates/configmap.yaml` passes `clusters` through with `toYaml` and the pod is
```

<!-- block: docs/polling-and-discovery.md | edit -->
```markdown
`POST /api/clusters/{name}/refresh` — and a control in the UI that calls it. **Neither exists
today.** When it is built, the constraint that governs it is not performance but safety.

**Which modes bind, precisely.** `userSelfLogin` does **not** bind today — it sits in
`gsd/config.py#CREDENTIAL_PENDING_REASONS` ("the self-login mode is S3b's #285, not built"), and a
kind in that table is never handed to `ClusterClient`. The mode that binds today is
**`saTokenLookup`**, whose fleet login puts the password on the wire; `userSelfLogin` joins it when
#285 lands.

So a refresh on a `saTokenLookup` cluster *is a bind*, and it must honour
`gsd/fleetlookup.py#CredentialGate` — returning a gated credential's standing refusal **without
```

```markdown
`POST /api/clusters/{name}/refresh` — and a control in the UI that calls it. **Neither exists
today.** When it is built, the constraint that governs it is not performance but safety.

**Which modes bind, precisely.** **`saTokenLookup`** binds to retrieve a cluster's token, and the daily
ping binds once per fleet account per interval to confirm it (#285). **`userSelfLogin`** binds for its own
session — at the first cycle and at each renewal, a fixed margin before the session expires
(`gsd/selflogin.py#SelfLoginSessions`). Every one of those logins claims the fleet account's Lease first
and reads the refusal recorded there (`gsd/fleetstate.py#FleetLease`).

So a refresh on a `saTokenLookup` cluster *is a bind*, and it must honour
`gsd/fleetlookup.py#CredentialGate` — returning a gated credential's standing refusal **without
```

<!-- block: docs/DESIGN_cluster_connection_flows.md | edit -->
```markdown
                                          outcome=<finding>` line — attempt=n/5,
                                          retry_in=, gave_up=true — and a standing
                                          finding on the tab until the next success.
```

```markdown
                                          outcome=<finding>` line — attempt=n/5,
                                          retry_in=, gave_up=true — and a standing
                                          finding on the tab until the next success.

  CONFIRMED DAILY (SPEC_S4c, #285) — the fleet account itself, once per account per interval
  ───────────────────────────────────  ─────────────────────────────────────────
  the daily ping                       the leader claims the account's Lease, logs in on
               one retrieved cluster,  ONE retrieved cluster (in rotation by name) and
               read, nothing stored    reads the same token, writing nothing:
                                          `fleet-ping account= target= last_ok=<instant>`.
                                          A failure is `fleet-ping-failed phase=credential
                                          outcome=<finding> attempt=1/1`; a refused
                                          password stands it down, said once: gave_up=true
                                          suspended=<account> scope=ping.

  SELF-LOGIN (SPEC_S4c, #285) — a stanza that says userSelfLogin: true
  ───────────────────────────────────  ─────────────────────────────────────────
  self-login   the fleet account's     nothing at rest: the session is the credential,
               own session             renewed at expires_at − min(2 h, ¼ × expires_in):
                                          `self-login-renewed`. A 401 before expiry logs in
                                          once more (`self-login-failed reauth=next-cycle`);
                                          a refused password stops every self-login cluster
                                          on the account: `fleet-credential-suspended
                                          suspended=<account> scope=self-login stopped=<n>`.
```

<!-- block: local-development/API.md | edit -->
```markdown
previous set of discovered clusters stands. `secrets.enabled=false` (`clusterConfig.secrets.enabled`)
answers the values list alone with `last_discovery: null`.

### The Cluster Configurations tab's writes (#230 S2)

Four routes, all the cluster-admin tier (above — never the wide tier) and each needing a proxy-verified
```

```markdown
previous set of discovered clusters stands. `secrets.enabled=false` (`clusterConfig.secrets.enabled`)
answers the values list alone with `last_discovery: null`.

**`fleet`** (#285, `docs/specs/SPEC_S4c_credential_lifecycle.md` §3.10) is the daily ping's setting,
`{"ping": {"enabled": true, "interval_seconds": 86400}}`, and one entry per fleet account as its Lease
holds it: `username`, `lease` (`gsd-fleet-<sha256(username)[:16]>`), `last_attempt`, `last_ok` (null before
the first success), `last_outcome` (`ok` or the finding code the last ping met), `last_target` (the cluster
it last read), and `suspended` — `[{"target", "since", "code"}]` while a refused entry stands, `[]`
otherwise. A `self-login` cluster's entry carries `session`: `{"state": "current|renewing|suspended|none",
"expires_at", "renew_at"}`. Every instant is ISO-8601 UTC; the page computes any age itself.

### The Cluster Configurations tab's writes (#230 S2)

Four routes, all the cluster-admin tier (above — never the wide tier) and each needing a proxy-verified
```

<!-- block: docs/CHANGELOG.md | edit -->
```markdown

## Unreleased

- **A values `apiUrl` carrying userinfo, a query or a fragment is refused (#415; chart 0.58.8).**
  `https://user:password@host` (in any letter case, and with surrounding whitespace), `…?x` and `…#x` in
  `clusters[].apiUrl` now fail `helm template` and the pod's loader, as the cluster Secret's `server` already did;
```

```markdown

## Unreleased

- **The fleet account's credential lifecycle — a durable, replica-shared gate, the daily ping, and `userSelfLogin`
  (#285, `docs/specs/SPEC_S4c_credential_lifecycle.md`; chart 0.59.0; the application code rides Epic C's release).**
  Every login as the fleet account first claims the account's Lease in the release namespace
  (`gsd-fleet-<sha256(username)[:16]>`) and binds nothing without it. A password the directory refused, or
  answered without a session, is recorded there before the process's own gate, so a restart, a second replica
  and every other cluster on the account read it: one wrong or locked password costs one login across two
  processes, three clusters, a restart and an irrelevant edit, where each of those sent it once more. The Lease
  keeps a salted scrypt fingerprint of the password, never the fast hash the process holds, because
  `cluster-reader` can read Leases. A successful ConfigMap onboarding still spends only its own cluster (#293's
  budget, unchanged). **The daily ping** (`clusterConfig.fleetAccount.ping`, on, `intervalSeconds: 86400`): once
  per account per interval, on the leader, the dashboard logs in on ONE cluster the lookup retrieved (in rotation
  by name) and reads the poller token Secret there, storing nothing; the instant it last succeeded is served on
  `GET /api/clusterconfigs` (`fleet`), the Cluster Configurations tab and `gsd_fleet_account_last_ok_timestamp_seconds`
  (with `gsd_fleet_account_ping_enabled` and `gsd_fleet_account_suspended`, all unlabelled). A refused entry
  stands it down, said once. **`userSelfLogin` is built**: the cluster polls on its own session, renewed at
  `expires_at − min(2 h, ¼ × expires_in)` from the lifetime the session states (a year on CRC renews two hours
  before it ends); a 401 before expiry logs in once more and a second suspends the cluster; a refused password
  suspends every self-login cluster on the account at once (`fleet-credential-suspended … stopped=<n>`). The
  chart's `leases` rule also renders when a fleet account is in use with election off, and a `userSelfLogin`
  stanza with `replicaCount > 1` is refused. Clearing a refused entry by hand means removing its annotation and
  restarting the pod, which keeps its own copy.
- **A values `apiUrl` carrying userinfo, a query or a fragment is refused (#415; chart 0.58.8).**
  `https://user:password@host` (in any letter case, and with surrounding whitespace), `…?x` and `…#x` in
  `clusters[].apiUrl` now fail `helm template` and the pod's loader, as the cluster Secret's `server` already did;
```

<!-- block: local-development/tests/test_fleet_lifecycle.py | create -->
```python
"""#285 (SPEC_S4c): the credential lifecycle — the fleet account's Lease (the claim, the durable gate, fail
closed), the daily ping, `self-login` renewal and suspension, the metric families and the API blocks.

The fake target is S4a's and `wire` counts its authorize requests — the unit every budget here is stated in (a
wire mock counts authorize requests, not directory binds). The fake host is S4b's, with the Lease resource
answered by `LeaseAPI`: the API server's coordination.k8s.io/v1 Lease — GET, POST and PUT by name, and the
resourceVersion compare-and-swap (a PUT carrying a stale resourceVersion answers 409). One `LeaseAPI` behind two
pollers is one API server behind two processes; a new `Poller` over it is a restart. No test logs in as the fleet
account of any cluster: USER is the harness's own name."""

from __future__ import annotations

import base64
import copy
import dataclasses
import json
import logging
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from gsd.clusterconfig import FINDING_CODES
from gsd.config import ClusterConfig, Settings
from gsd.fleetlogin import FleetSession
from gsd.fleetlookup import CODES, CredentialGate, lookup
from gsd.fleetstate import ClaimHeld, FleetLease, claim_seconds, lease_digest, lease_name
from gsd.kube import FORBIDDEN, ClusterError
from gsd.metrics import RuntimeSignals, build_registry
from gsd.poller import Poller
from gsd.selflogin import SelfLoginSessions, renew_at
from gsd.store import Store
from test_fleet_login import API, PASSWORD, T0, TOKEN, USER, login_302, refused_401
from test_fleet_lookup import SA_TOKEN, FakeHost, sa_secret, wire  # noqa: F401

LEASES = "/apis/coordination.k8s.io/v1/namespaces/ns/leases"
ANSWERS = {"401": refused_401, "500": lambda: httpx.Response(500, text="Internal Server Error")}
TOKEN_2 = "sha256~U2Vjb25kU2Vzc2lvblRva2VuVGhhdE11c3ROZXZlckxlYWs"
TOKEN_3 = "sha256~VGhpcmRTZXNzaW9uVG9rZW5UaGF0TXVzdE5ldmVyTGVhaw"


class LeaseAPI:
    """The API server's Lease resource, shared by every host built over it. `refuse` answers 403 to everything."""

    def __init__(self):
        self.objects: dict[str, dict] = {}
        self.serial = 0
        self.writes: list[tuple[str, str]] = []
        self.refuse = False

    def get(self, name: str) -> dict:
        if self.refuse:
            raise ClusterError(FORBIDDEN, f"403 Forbidden on {LEASES}/{name}")
        if name not in self.objects:
            raise ClusterError("unreachable", f"HTTP 404 on {LEASES}/{name}: not found")
        return copy.deepcopy(self.objects[name])

    def write(self, method: str, name: str, obj: dict) -> dict:
        self.writes.append((method, name))
        if self.refuse:
            raise ClusterError(FORBIDDEN, f"403 Forbidden on {method} {LEASES}")
        if method == "POST" and name in self.objects:
            raise ClusterError("unreachable", f"HTTP 409 on POST {LEASES}: AlreadyExists")
        if method == "PUT" and obj["metadata"].get("resourceVersion") != self.objects[name]["metadata"]["resourceVersion"]:
            raise ClusterError("unreachable", f"HTTP 409 on PUT {LEASES}/{name}: Conflict")
        self.serial += 1
        stored = copy.deepcopy(obj)
        stored["metadata"]["resourceVersion"] = str(self.serial)
        self.objects[name] = stored
        return copy.deepcopy(stored)

    def annotations(self, account: str = USER) -> dict:
        return self.objects.get(lease_name(account), {}).get("metadata", {}).get("annotations", {})

    def backdate(self, account: str, key: str, seconds: int) -> None:
        """Move an instant annotation back in time: the harness's clock for the ping's cadence."""
        ann = self.objects[lease_name(account)]["metadata"]["annotations"]
        moment = datetime.fromisoformat(ann[key].replace("Z", "+00:00")) - timedelta(seconds=seconds)
        ann[key] = moment.strftime("%Y-%m-%dT%H:%M:%SZ")


class LeaseHost(FakeHost):
    """S4b's fake host — the fleet password Secret and the cluster Secrets — with the Lease resource on `leases`."""

    def __init__(self, leases: LeaseAPI | None = None, secrets: dict | None = None):
        super().__init__(secrets)
        self.leases = leases or LeaseAPI()

    def _get(self, client, path, params):
        if path.startswith(LEASES + "/"):
            return self.leases.get(path.rsplit("/", 1)[1])
        return super()._get(client, path, params)

    def _send(self, client, method, path, *, json=None, secrets=()):
        if path.startswith(LEASES):
            return self.leases.write(method, json["metadata"]["name"] if method == "POST" else path.rsplit("/", 1)[1], json)
        return super()._send(client, method, path, json=json, secrets=secrets)

    def rotate(self, password: str) -> None:
        self.secrets["/api/v1/namespaces/ns/secrets/gsd-fleet-account"] = {
            "data": {"password": base64.b64encode(password.encode()).decode()}}


def stanza(name: str, url: str | None = None, **kw) -> ClusterConfig:
    return ClusterConfig(name, url or f"https://api.{name}.example.com:6443", sa_token_lookup=True,
                         ldap_connection_bootstrap=USER, **kw)


def retrieved(name: str) -> ClusterConfig:
    """A cluster the lookup retrieved: its own Secret, the token it stored, and the account it logged in as."""
    return ClusterConfig(name, f"https://api.{name}.example.com:6443", token_value=SA_TOKEN, source=f"secret:gsd-cluster-{name}",
                         token_source="remote-lookup", lookup_account=USER)


def self_login(name: str) -> ClusterConfig:
    return ClusterConfig(name, f"https://api.{name}.example.com:6443", user_self_login=True, ldap_connection_bootstrap=USER)


def process(tmp_path, monkeypatch, host: LeaseHost, *clusters: ClusterConfig, discovered=(), name="p", **kw) -> Poller:
    """One dashboard process over `host`: its own store and its own in-memory gate."""
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **k: host)
    s = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"), *clusters],
                 db_path=str(tmp_path / f"{name}.db"), cluster_secrets_writes_enabled=True, **kw)
    s.cluster_registry.replace(list(discovered), [], at="2026-09-26T00:00:00Z")
    return Poller(Store(str(tmp_path / f"{name}.db")), s, signals=RuntimeSignals())


def lines(caplog, event: str) -> list[str]:
    return [m for m in caplog.messages if m.startswith(event + " ")]


# ── R1: the claim is a compare-and-swap ──────────────────────────────────────────────────────────

def test_r1_two_processes_cannot_both_win_one_claim_and_no_claim_is_no_bind(tmp_path, monkeypatch, wire):
    host = LeaseHost()
    a = FleetLease(host, "ns", USER, claim_seconds=195, identity="pod-a")
    b = FleetLease(host, "ns", USER, claim_seconds=195, identity="pod-b")
    seen_a, seen_b = a.read(), b.read()            # both read the absent Lease...
    a.claim(seen_a)                                 # ...A creates it
    with pytest.raises(ClaimHeld):
        b.claim(seen_b)                             # B's create answers 409: A won
    with pytest.raises(ClaimHeld):
        b.claim()                                   # a fresh read shows A's live claim
    a.release()
    stale = b.read()                                # released: no live claim in it...
    a.claim(); a.release()                          # ...but A claims and lets go again after B's read
    with pytest.raises(ClaimHeld):
        b.claim(stale)                              # B's PUT carries the older resourceVersion: 409, the CAS
    b.claim()
    b.release()
    # Through the poller: while another process holds the account, nothing binds; once it lets go, one bind.
    wire.answers = [login_302()]
    p = process(tmp_path, monkeypatch, host, stanza("rnd"))
    a.claim()
    p._retrieve_pending()
    assert wire.authorize == [], "a bind without the claim"
    a.release()
    p._retrieve_pending()
    assert len(wire.authorize) == 1 and "/api/v1/namespaces/ns/secrets/gsd-cluster-rnd" in host.secrets


def test_r1_a_paused_holders_refusal_is_recorded_and_it_never_clears_the_claim_that_took_over(wire):
    """B1's residual, stated rather than claimed away: a holder paused past its claim can still bind after another
    process took the claim over. When it resumes, its bound answer is re-applied to the Lease as it now is (the API
    conventions' duty on a 409) and the claim that took over is left standing."""
    from datetime import datetime
    host, now = LeaseHost(), [datetime(2026, 9, 26, 12, 0, tzinfo=UTC)]
    paused = FleetLease(host, "ns", USER, claim_seconds=60, identity="pod-a", clock=lambda: now[0])
    paused.claim()
    now[0] += timedelta(seconds=61)                  # judged expired...
    taker = FleetLease(host, "ns", USER, claim_seconds=60, identity="pod-b", clock=lambda: now[0])
    taker.claim()                                    # ...and taken
    paused.refuse("https://api.crc.testing:6443", lease_digest(USER, PASSWORD), "login-refused")
    paused.release()
    obj = host.leases.objects[lease_name(USER)]
    assert json.loads(obj["metadata"]["annotations"]["groupsync-dashboard.io/refused"])["code"] == "login-refused"
    assert obj["spec"]["holderIdentity"] == "pod-b", "the resumed holder cleared the claim that took over"


# ── R2: the gate is on the object, and it is the account's ───────────────────────────────────────

@pytest.mark.parametrize("answer", sorted(ANSWERS))
def test_r2_the_budget_over_the_system_one_authorize_across_two_processes_three_targets_a_restart_and_an_edit(
        tmp_path, monkeypatch, wire, answer):
    """The Definition of Done: one wrong or locked password on one account, measured in authorize requests as
    (first, what each later shape adds). Before #285 the in-memory gate covered only its own process: a second
    replica, a restart and an irrelevant edit's rollout each sent the password once more."""
    host = LeaseHost()
    targets = [stanza("rnd", "https://api.crc.testing:6443"), stanza("east"), stanza("west")]
    wire.answers = [ANSWERS[answer]() for _ in range(8)]
    measured = {}
    first = process(tmp_path, monkeypatch, host, *targets, name="first")
    first._retrieve_pending()
    measured["one process, three targets"] = len(wire.authorize)
    for shape, clusters in (("a second replica", targets), ("a restart", targets),
                            ("an irrelevant config edit (visibility)", [dataclasses.replace(t, visibility="self-only") for t in targets])):
        before = len(wire.authorize)
        process(tmp_path, monkeypatch, host, *clusters, name=shape.split()[1])._retrieve_pending()
        measured[shape] = len(wire.authorize) - before
    assert measured == {"one process, three targets": 1, "a second replica": 0, "a restart": 0,
                        "an irrelevant config edit (visibility)": 0}, measured
    entry = json.loads(host.leases.annotations()["groupsync-dashboard.io/refused"])
    assert entry["digest"] == lease_digest(USER, PASSWORD) != CredentialGate._digest(PASSWORD)
    assert entry["code"] == ("login-refused" if answer == "401" else "login-failed")
    assert entry["target"] == "https://api.crc.testing:6443", "the target that answered, kept as evidence"
    # A rotated password is a new (account, password): it binds once, and its success retires the old entry.
    host.rotate("rotated-pass-9")
    wire.answers = [login_302()]
    process(tmp_path, monkeypatch, host, targets[0], name="rotated")._retrieve_pending()
    assert len(wire.authorize) == 2 and "groupsync-dashboard.io/refused" not in host.leases.annotations()


def test_r2_the_lease_digest_is_salted_and_slow_not_the_gates_prefix():
    """The Lease is readable by `cluster-reader` (measured on the reference cluster): an unsalted fast hash there is
    an offline dictionary oracle for the bind password. scrypt salted with the account, 64 bits kept."""
    assert lease_digest(USER, PASSWORD) != CredentialGate._digest(PASSWORD)
    assert lease_digest(USER, PASSWORD) != lease_digest("another-account", PASSWORD), "salted with the account"
    assert len(lease_digest(USER, PASSWORD)) == 16 and lease_digest(USER, PASSWORD) == lease_digest(USER, PASSWORD)


# ── #293: the Lease never turns a per-target success mark into an account-wide refusal ──────────

def test_293s_success_mark_stays_per_target_and_off_the_lease(tmp_path, monkeypatch, wire):
    """#293's budget (SPEC_S5 §3.3), with the Lease in the loop: two SUCCESSFUL ConfigMap onboardings on one
    account are two authorizes; the Lease records no refusal; a restart with a missing output binds once more,
    as #293's table says; and the daily ping never writes the success mark."""
    host = LeaseHost()
    onboarded = [dataclasses.replace(stanza(n), onboarding=("fleet", "cm-1", n)) for n in ("rnd", "east")]
    wire.answers = [login_302() for _ in range(4)]
    p = process(tmp_path, monkeypatch, host, *onboarded, name="p")
    p._retrieve_pending()
    assert len(wire.authorize) == 2, "a success on one target gated the other"
    assert "groupsync-dashboard.io/refused" not in host.leases.annotations()
    assert all(p._credential_gate.refused(c.api_url, USER, PASSWORD) for c in onboarded), "#293's mark, per target"
    # A restart with the output missing: a new gate, the same Lease — one more bind (#293's row, unchanged).
    del host.secrets["/api/v1/namespaces/ns/secrets/gsd-cluster-rnd"]
    wire.secret = httpx.Response(403)
    process(tmp_path, monkeypatch, host, onboarded[0], name="restarted")._retrieve_pending()
    assert len(wire.authorize) == 3
    # The ping of an onboarded cluster marks nothing: onboarding=() is what it logs in with.
    wire.secret = httpx.Response(200, json=sa_secret())
    ping = process(tmp_path, monkeypatch, host, discovered=[dataclasses.replace(retrieved("rnd"), onboarding=("fleet", "cm-1", "rnd"))],
                   name="ping")
    ping._ping_accounts()
    assert len(wire.authorize) == 4 and not ping._credential_gate._spent


# ── R3: the ping is one bind per account per cadence ─────────────────────────────────────────────

def test_r3_twenty_clusters_on_one_account_are_one_ping_a_cadence_rotating_by_name(tmp_path, monkeypatch, wire, caplog):
    host = LeaseHost()
    fleet = [retrieved(f"c{n:02d}") for n in range(20)]
    wire.answers = [login_302() for _ in range(4)]
    p = process(tmp_path, monkeypatch, host, discovered=fleet)
    with caplog.at_level(logging.INFO, logger="gsd"):
        p._ping_accounts()
        p._ping_accounts()                                     # not due: nothing
    assert len(wire.authorize) == 1 and len(wire.reads) == 1 and len(wire.revokes) == 1
    ann = host.leases.annotations()
    assert (ann["groupsync-dashboard.io/ping-last-target"], ann["groupsync-dashboard.io/ping-last-outcome"]) == ("c00", "ok")
    line, = lines(caplog, "fleet-ping")
    assert f"account={USER}" in line and "target=c00" in line and "last_ok=" in line and "last_used=2026-09-22" in line
    assert not [w for w in host.writes if "/secrets" in w[1]], "the ping stores nothing: no cluster Secret is written"
    # A restart reads the instant off the Lease and does not ping again inside the cadence.
    process(tmp_path, monkeypatch, host, discovered=fleet, name="restarted")._ping_accounts()
    assert len(wire.authorize) == 1
    # A cadence later, the next target by name.
    host.leases.backdate(USER, "groupsync-dashboard.io/ping-last-attempt", 86400)
    p._ping_accounts()
    assert len(wire.authorize) == 2 and host.leases.annotations()["groupsync-dashboard.io/ping-last-target"] == "c01"
    # A rotated password is confirmed within the discovery cadence, once — and once only when its read keeps
    # failing (a revoked grant on the target): the Lease records the password each ATTEMPT was for (B3).
    host.rotate("rotated-pass-9")
    wire.secret = httpx.Response(403, text="forbidden")
    p._ping_accounts(); p._ping_accounts(); p._ping_accounts()
    assert len(wire.authorize) == 3 and host.leases.annotations()["groupsync-dashboard.io/ping-last-outcome"] == "sa-token-unreadable"


# ── R4: the ping stands down ─────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ["login-refused", "login-failed"])
def test_r4_a_gated_account_is_not_pinged_and_is_said_once(tmp_path, monkeypatch, wire, caplog, code):
    host = LeaseHost()
    holder = FleetLease(host, "ns", USER, claim_seconds=195, identity="pod-a")
    holder.claim()
    holder.refuse("https://api.other.example.com:6443", lease_digest(USER, PASSWORD), code)
    holder.release()
    p = process(tmp_path, monkeypatch, host, discovered=[retrieved("c00")])
    with caplog.at_level(logging.INFO, logger="gsd"):
        p._ping_accounts(); p._ping_accounts(); p._ping_accounts()
    assert wire.requests == [], "a gated account was pinged — one more bind a day against a locked account"
    line, = lines(caplog, "fleet-ping-failed")
    assert f"outcome={code}" in line and "gave_up=true" in line and f"suspended={USER}" in line and "scope=ping" in line
    finding, = [f for f in p.settings.cluster_registry.findings() if f.secret == "gsd-cluster-c00"]
    assert finding.code == code and "stands down" in finding.detail


# ── R5: the margin ───────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("expires_in,seconds", [(3600, 2700), (86400, 79200), (31536000, 31528800)])
def test_r5_renewal_is_a_fixed_margin_before_expiry(expires_in, seconds):
    """SPEC_S4 §3.1: expires_at − min(2 h, ¼ × expires_in) — CRC's year renews two hours before it ends. The
    reference cluster cannot fire this path (SPEC_S4c §2.3), so the clock here is injected."""
    session = FleetSession("c", USER, TOKEN, obtained_at=T0, expires_in=expires_in, issuer="i", attempts=1)
    assert renew_at(session) == T0 + timedelta(seconds=seconds)


def sessions(p: Poller, now: list) -> SelfLoginSessions:
    p.self_login = SelfLoginSessions(p, clock=lambda: now[0])
    return p.self_login


def test_r5_a_session_too_short_to_renew_is_not_chased(tmp_path, monkeypatch, wire, caplog):
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("sl"), poll_interval_seconds=60)
    s = sessions(p, now)
    wire.answers = [login_302(expires_in="200"), login_302(expires_in="200")]
    with caplog.at_level(logging.INFO, logger="gsd"):
        assert s.credential_for(p.settings.cluster("sl")) is None
        now[0] += timedelta(seconds=60)
        assert s.credential_for(p.settings.cluster("sl")) is None
    assert len(wire.authorize) == 1 and len(wire.revokes) == 1, "the short session was exited at once, and not chased"
    finding, = [f for f in p.settings.cluster_registry.findings() if f.secret == "sl"]
    assert finding.code == "self-login-lifetime-too-short" and "200s" in finding.detail and "240s" in finding.detail


# ── R6: renewal keeps the poll fed and revokes the old token second ─────────────────────────────

def test_r6_renewal_answers_the_new_login_before_the_old_token_is_revoked(tmp_path, monkeypatch, wire, caplog):
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("sl"))
    s = sessions(p, now)
    wire.answers = [login_302(expires_in="3600"), lambda r: httpx.ConnectError("refused"),
                    login_302(expires_in="3600", token=TOKEN_2)]
    first = s.credential_for(p.settings.cluster("sl"))
    assert first.token_value == TOKEN and first.credential_kind == "bearer"
    now[0] = T0 + timedelta(seconds=2700)                    # renew_at
    kept = s.credential_for(p.settings.cluster("sl"))
    assert kept.token_value == TOKEN and wire.revokes == [], "an unreachable renewal keeps the session it has"
    now[0] += timedelta(seconds=60)
    with caplog.at_level(logging.INFO, logger="gsd"):
        renewed = s.credential_for(p.settings.cluster("sl"))
    assert renewed.token_value == TOKEN_2
    order = [(r.method, r.url.path) for r in wire.requests]
    assert order.index(("GET", "/oauth/authorize"), 2) < next(i for i, (m, _) in enumerate(order) if m == "DELETE")
    assert wire.revokes[0].headers["authorization"] == f"Bearer {TOKEN}", "the superseded token, revoked second"
    assert lines(caplog, "self-login-renewed")
    assert s.view("sl")["state"] == "current" and s.view("sl")["expires_at"] == "2026-09-21T13:46:00Z"


@pytest.mark.parametrize("answer", sorted(ANSWERS))
def test_r6_a_bound_failure_suspends_every_self_login_cluster_on_the_account(tmp_path, monkeypatch, wire, caplog, answer):
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("a"), self_login("b"))
    for name in ("a", "b"):
        p.store.upsert_cluster(name, f"https://api.{name}.example.com:6443", True, source="values", credential="self-login")
    s = sessions(p, now)
    wire.answers = [login_302(expires_in="3600"), login_302(expires_in="3600", token=TOKEN_2), ANSWERS[answer]()]
    s.credential_for(p.settings.cluster("a")); s.credential_for(p.settings.cluster("b"))
    now[0] = T0 + timedelta(seconds=2700)
    with caplog.at_level(logging.INFO, logger="gsd"):
        assert s.credential_for(p.settings.cluster("a")) is None
        assert s.credential_for(p.settings.cluster("b")) is None
    assert len(wire.authorize) == 3 and len(wire.revokes) == 2, "both sessions revoked, and b did not log in again"
    line, = lines(caplog, "fleet-credential-suspended")
    assert f"suspended={USER}" in line and "scope=self-login" in line and "stopped=2" in line and "clusters=a,b" in line
    rows = {r["id"]: r["status"] for r in p.store.clusters()}
    assert rows == {"a": "auth_failed" if answer == "401" else "unreachable", "b": "auth_failed" if answer == "401" else "unreachable"}
    assert json.loads(host.leases.annotations()["groupsync-dashboard.io/refused"])["digest"] == lease_digest(USER, PASSWORD)
    # A restart reads the gate off the Lease: no login.
    other = process(tmp_path, monkeypatch, host, self_login("a"), name="restarted")
    assert sessions(other, now).credential_for(other.settings.cluster("a")) is None and len(wire.authorize) == 3


# ── R7: the 401 rule ─────────────────────────────────────────────────────────────────────────────

def test_r7_a_401_before_expiry_reauthenticates_once_and_a_second_suspends(tmp_path, monkeypatch, wire, caplog):
    host, now = LeaseHost(), [T0]
    p = process(tmp_path, monkeypatch, host, self_login("sl"))
    s = sessions(p, now)
    wire.answers = [login_302(), login_302(token=TOKEN_2)]
    wire.revoke = httpx.Response(401, text="Unauthorized")       # the revoke of an invalidated token: 401
    cluster = p.settings.cluster("sl")
    s.credential_for(cluster)
    now[0] += timedelta(seconds=60)
    with caplog.at_level(logging.INFO, logger="gsd"):
        s.poll_answered(cluster, "auth_failed")                     # an administrator revoked it, say
        assert s.credential_for(cluster).token_value == TOKEN_2     # one login on the next cycle
        assert "groupsync-dashboard.io/refused" not in host.leases.annotations(), "nothing evaluated the password"
        assert not p._credential_gate.refused(cluster.api_url, USER, PASSWORD)
        s.poll_answered(cluster, "auth_failed")                     # the fresh session refused too
        assert s.credential_for(cluster) is None and s.credential_for(cluster) is None
    assert len(wire.authorize) == 2, "a re-login loop"
    assert any("outcome=auth_failed" in m for m in lines(caplog, "fleet-logout-failed")), "#283's revoke-side reading"
    finding, = [f for f in p.settings.cluster_registry.findings() if f.secret == "sl"]
    assert finding.code == "self-login-suspended" and s.view("sl")["state"] == "suspended"


# ── R8: fail closed ──────────────────────────────────────────────────────────────────────────────

def test_r8_an_unreadable_lease_binds_nothing_on_any_path_and_is_said_once(tmp_path, monkeypatch, wire, caplog):
    host = LeaseHost()
    host.leases.refuse = True
    p = process(tmp_path, monkeypatch, host, stanza("rnd"), self_login("sl"), discovered=[retrieved("c00")])
    with caplog.at_level(logging.INFO, logger="gsd"):
        p._retrieve_pending(); p._retrieve_pending()
        p._ping_accounts()
        assert p.self_login.credential_for(p.settings.cluster("sl")) is None
    assert wire.authorize == [], "a bind without the gate"
    codes = {(f.secret, f.code) for f in p.settings.cluster_registry.findings()}
    assert {("gsd-cluster-rnd", "fleet-state-unavailable"), ("gsd-cluster-c00", "fleet-state-unavailable"),
            ("sl", "fleet-state-unavailable")} <= codes
    assert len([m for m in lines(caplog, "fleet-lookup-failed") if "fleet-state-unavailable" in m]) == 1
    assert all("coordination.k8s.io/leases" in f.detail for f in p.settings.cluster_registry.findings()
               if f.code == "fleet-state-unavailable")


# ── R9: no credential reaches a line ─────────────────────────────────────────────────────────────

def test_r9_every_new_event_carries_no_password_and_no_token(tmp_path, monkeypatch, wire, caplog):
    """The redaction pin (SPEC_S3 §3.1 rule 4): the password echoed by the OAuth server, and the session a renewal
    replaces echoed beside it, reach no line of the events this change adds — nor the password any line at all."""
    host, now = LeaseHost(), [T0]
    # The self-login cluster logs in as another account, so the ping's refusal does not gate it first.
    other = dataclasses.replace(self_login("a"), ldap_connection_bootstrap="svc-other")
    p = process(tmp_path, monkeypatch, host, other, discovered=[retrieved("c00"), retrieved("c01")])
    s = sessions(p, now)
    wire.answers = [login_302(), login_302(token=TOKEN_2), login_302(token=TOKEN_3),
                    httpx.Response(500, text=f"echo {PASSWORD}"), httpx.Response(500, text=f"echo {PASSWORD} {TOKEN_2}")]
    with caplog.at_level(logging.DEBUG, logger="gsd"):
        cluster = p.settings.cluster("a")
        s.credential_for(cluster)                                   # a session (TOKEN)
        now[0] += timedelta(seconds=60)
        s.poll_answered(cluster, "auth_failed")                     # self-login-failed
        s.credential_for(cluster)                                   # self-login-renewed (TOKEN_2)
        p._ping_accounts()                                          # fleet-ping (TOKEN_3)
        host.leases.backdate(USER, "groupsync-dashboard.io/ping-last-attempt", 86400)
        p._ping_accounts()                                          # fleet-ping-failed: the password echoed
        p._ping_accounts()                                          # the stand-down, said once
        p.self_login._sessions["a"].renew_at = now[0]               # due: the renewal meets the password and TOKEN_2
        s.credential_for(cluster)                                   # fleet-credential-suspended
    new = [m for event in ("self-login-failed", "self-login-renewed", "fleet-ping", "fleet-ping-failed",
                           "fleet-credential-suspended") for m in lines(caplog, event)]
    assert {m.split()[0] for m in new} == {"self-login-failed", "self-login-renewed", "fleet-ping", "fleet-ping-failed",
                                           "fleet-credential-suspended"}
    assert any("echo <redacted>" in m for m in lines(caplog, "fleet-credential-suspended")), "the echo was not met"
    for secret in (PASSWORD, TOKEN, TOKEN_2, TOKEN_3, SA_TOKEN):
        assert secret not in "\n".join(new), secret
    assert PASSWORD not in "\n".join(caplog.messages) and SA_TOKEN not in "\n".join(caplog.messages)


# ── the metric families: unlabelled, absent until true ───────────────────────────────────────────

def test_the_fleet_families_are_unlabelled_and_absent_until_a_ping_succeeds():
    store = Store(":memory:")
    try:
        signals, settings = RuntimeSignals(), Settings(clusters=[ClusterConfig("h", "https://h", token_env="X")], db_path=":memory:")
        text = generate_latest(build_registry(store, timedelta(0), signals=signals, settings=settings)).decode()
        assert "# HELP gsd_fleet_account_last_ok_timestamp_seconds " in text
        assert "\ngsd_fleet_account_last_ok_timestamp_seconds " not in text, "absence means never, not zero"
        assert "\ngsd_fleet_account_ping_enabled 1.0" in text and "\ngsd_fleet_account_suspended 0.0" in text
        signals.note_fleet_accounts({USER: {"last_ok": "2026-09-22T06:00:05Z", "suspended": []},
                                     "acct-two": {"last_ok": "2026-09-21T06:00:05Z",
                                                "suspended": [{"target": "https://x", "since": "t", "code": "login-refused"}]}})
        text = generate_latest(build_registry(store, timedelta(0), signals=signals,
                                              settings=dataclasses.replace(settings, fleet_ping_enabled=False))).decode()
        value = next(float(l.split()[1]) for l in text.splitlines() if l.startswith("gsd_fleet_account_last_ok_timestamp_seconds "))
        assert value == datetime(2026, 9, 21, 6, 0, 5, tzinfo=UTC).timestamp(), "the OLDEST account's instant"
        assert "\ngsd_fleet_account_ping_enabled 0.0" in text and "\ngsd_fleet_account_suspended 1.0" in text
        assert "gsd_fleet_account_" not in "".join(l for l in text.splitlines() if "{" in l), "a label on a fleet family"
        assert USER not in text and "acct-two" not in text, "a username on a public endpoint"
    finally:
        store.close()


# ── the API's two blocks ─────────────────────────────────────────────────────────────────────────

def test_the_api_serves_the_fleet_block_and_a_self_login_session_as_instants(tmp_path):
    from gsd.api import build_app
    from gsd.clusterconfig import parse_secret
    from test_clusterconfig import _secret
    from test_visibility import H, _MapResolver, _seed, _settings
    db = str(tmp_path / "gsd.db"); _seed(db)
    settings = _settings(db)
    sl = parse_secret(_secret("gsd-cluster-sl", cluster="sl", config={"userSelfLogin": True, "ldapConnectionBootstrap": USER}),
                      host_name="c1")
    settings.cluster_registry.replace([sl], [], at="2026-09-26T00:00:00Z")
    app = build_app(settings, run_poller=False)
    app.state.tier_resolver = app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
    app.state.remote_tier_resolvers = {}
    app.state.signals.note_fleet_accounts({USER: {"lease": lease_name(USER), "last_attempt": "2026-09-22T06:00:04Z",
                                                  "last_ok": "2026-09-22T06:00:05Z", "last_outcome": "ok",
                                                  "last_target": "shared-rnd", "suspended": []}})
    app.state.signals.note_self_login("sl", {"state": "current", "expires_at": "2026-09-23T06:00:05Z",
                                             "renew_at": "2026-09-23T04:00:05Z"})
    with TestClient(app) as c:
        body = c.get("/api/clusterconfigs", headers=H("root")).json()
    assert body["fleet"] == {"ping": {"enabled": True, "interval_seconds": 86400},
                             "accounts": [{"username": USER, "lease": lease_name(USER), "last_attempt": "2026-09-22T06:00:04Z",
                                           "last_ok": "2026-09-22T06:00:05Z", "last_outcome": "ok",
                                           "last_target": "shared-rnd", "suspended": []}]}
    by = {x["id"]: x for x in body["clusters"]}
    assert by["sl"]["credential"] == "self-login" and by["sl"]["session"]["expires_at"] == "2026-09-23T06:00:05Z"
    assert "session" not in by["c1"], "the session block is a self-login cluster's alone"


# ── the vocabulary ───────────────────────────────────────────────────────────────────────────────

def test_the_new_codes_join_the_closed_set_and_claim_seconds_is_computed():
    from gsd.fleetstate import FleetStateUnavailable
    assert set(CODES) <= set(FINDING_CODES) and FleetStateUnavailable.code in FINDING_CODES
    assert {"fleet-state-unavailable", "self-login-suspended", "self-login-lifetime-too-short"} <= set(FINDING_CODES)
    s = Settings(clusters=[], db_path=":memory:")
    assert claim_seconds(s) == 195
    assert claim_seconds(dataclasses.replace(s, request_timeout_seconds=30)) == 375


def test_the_gate_docstring_names_the_lease_as_its_durable_half():
    doc = " ".join((CredentialGate.__doc__ or "").split())
    assert "the cache of the account Lease's gate (SPEC_S4c §3.3)" in doc
    assert "not covered until #285" not in doc and "The SPENT kind is never on the Lease" in doc
    assert lookup.__kwdefaults__["lease"] is None
```

<!-- block: local-development/tests/test_fleet_lookup.py | edit -->
```python
        self.writes.append((method, path, json))
        if method == "POST":
            self.secrets[f"{path}/{json['metadata']['name']}"] = json
        return None


```

```python
        self.writes.append((method, path, json))
        if method == "POST":
            self.secrets[f"{path}/{json['metadata']['name']}"] = json
        elif method == "PUT" and "/leases/" in path:
            self.secrets[path] = json          # the fleet account's Lease (#285) is kept as written, as the API server does
        return None


```

<!-- block: local-development/tests/test_fleet_lookup.py | edit -->
```python
        def failing(*a, **kw):
            raise LookupRefused("sa-token-secret-missing", "gone", action="create the token Secret on the target", spent=True)
        monkeypatch.setattr(fleetlookup, "lookup", failing)
        poller = self._poller(tmp_path, monkeypatch)
        interval = poller.settings.discovery_interval_seconds
        with caplog.at_level(logging.INFO, logger="gsd"):
```

```python
        def failing(*a, **kw):
            raise LookupRefused("sa-token-secret-missing", "gone", action="create the token Secret on the target", spent=True)
        monkeypatch.setattr(fleetlookup, "lookup", failing)
        monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: FakeHost())   # the account Lease's API (#285)
        poller = self._poller(tmp_path, monkeypatch)
        interval = poller.settings.discovery_interval_seconds
        with caplog.at_level(logging.INFO, logger="gsd"):
```

<!-- block: local-development/tests/test_fleet_lookup.py | edit -->
```python
    def test_success_clears_the_finding_and_wakes_discovery(self, tmp_path, monkeypatch, caplog):
        from gsd.fleetlookup import LookupResult, SaToken
        poller = self._poller(tmp_path, monkeypatch)
        poller.settings.cluster_registry.set_lookup_finding("rnd", Finding("gsd-cluster-rnd", "login-failed", "x"))
        monkeypatch.setattr(fleetlookup, "lookup", lambda *a, **kw: LookupResult(
            "rnd", USER, SaToken(token=SA_TOKEN, namespace="group-sync-operator", service_account="poller", secret_name="poller-token", last_used="2026-09-22"),
```

```python
    def test_success_clears_the_finding_and_wakes_discovery(self, tmp_path, monkeypatch, caplog):
        from gsd.fleetlookup import LookupResult, SaToken
        poller = self._poller(tmp_path, monkeypatch)
        monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: FakeHost())   # the account Lease's API (#285)
        poller.settings.cluster_registry.set_lookup_finding("rnd", Finding("gsd-cluster-rnd", "login-failed", "x"))
        monkeypatch.setattr(fleetlookup, "lookup", lambda *a, **kw: LookupResult(
            "rnd", USER, SaToken(token=SA_TOKEN, namespace="group-sync-operator", service_account="poller", secret_name="poller-token", last_used="2026-09-22"),
```

<!-- block: local-development/tests/test_clusterconfig_tab.py | edit -->
```python

    def _send(self, client, method, path, *, json=None, secrets=()):
        self.calls.append((method, path))
        if self.refuse:
            raise ClusterError(FORBIDDEN, f"403 Forbidden on {method} {path}")
        if self.echo:
            import json as _json
```

```python

    def _send(self, client, method, path, *, json=None, secrets=()):
        self.calls.append((method, path))
        if self.refuse and "/leases" not in path:    # `refuse` models the Secret grant; a Lease has its own (#285)
            raise ClusterError(FORBIDDEN, f"403 Forbidden on {method} {path}")
        if self.echo:
            import json as _json
```

<!-- block: local-development/tests/test_connection_modes.py | edit -->
```python
# ── the loader (§4 items 1-6) ──────────────────────────────────────────────────────────────────

class TestTheLoader:
    @pytest.mark.parametrize("key,kind", [("saTokenLookup", "remote-lookup"), ("userSelfLogin", "self-login")])
    def test_a_stanza_declaring_a_mode_loads_without_a_credential(self, tmp_path, key, kind):
        s = _load(tmp_path, f"    {key}: true\n")
        c = s.cluster("shared-rnd")
        assert (c.connection_mode, c.credential_kind, c.ldap_connection_bootstrap) == (key, kind, None)
        assert c.credential_pending and "S3b" in c.credential_pending
        with pytest.raises(ConfigError, match="S3b"):
            c.resolve_token()      # §4.2: nothing has been obtained, and the message says so
        assert s.host_cluster().name == "dashboard"

    def test_a_stanza_declaring_neither_mode_nor_credential_keeps_todays_refusal(self, tmp_path):
```

```python
# ── the loader (§4 items 1-6) ──────────────────────────────────────────────────────────────────

class TestTheLoader:
    @pytest.mark.parametrize("key,kind,pending", [("saTokenLookup", "remote-lookup", True), ("userSelfLogin", "self-login", False)])
    def test_a_stanza_declaring_a_mode_loads_without_a_credential(self, tmp_path, key, kind, pending):
        s = _load(tmp_path, f"    {key}: true\n")
        c = s.cluster("shared-rnd")
        assert (c.connection_mode, c.credential_kind, c.ldap_connection_bootstrap) == (key, kind, None)
        # A lookup is pending until its Secret exists; a self-login cluster polls on its session (#285, SPEC_S4c §3.6).
        assert bool(c.credential_pending and "S3b" in c.credential_pending) is pending
        with pytest.raises(ConfigError, match="S3b"):
            c.resolve_token()      # §4.2: nothing is resolved from the declaration, and the message says so
        assert s.host_cluster().name == "dashboard"

    def test_a_stanza_declaring_neither_mode_nor_credential_keeps_todays_refusal(self, tmp_path):
```

<!-- block: local-development/tests/test_connection_modes.py | edit -->
```python
        finally:
            poller.stop()

    def test_a_secret_declaring_a_mode_is_discovered_listed_and_not_polled(self, tmp_path):
        _Host.secrets = {"items": [_secret(config={"userSelfLogin": True})]}
        store = Store(str(tmp_path / "p.db"))
        settings = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X")],
```

```python
        finally:
            poller.stop()

    def test_a_secret_declaring_self_login_is_discovered_listed_and_polled_only_on_a_session(self, tmp_path):
        """#285 (SPEC_S4c §3.6): self-login is no longer pending — its thread starts — and it polls only on a
        session. This Secret names no account and the chart none, so there is no session: the poll is skipped
        (never a false `auth_failed`) and the finding says why."""
        _Host.secrets = {"items": [_secret(config={"userSelfLogin": True})]}
        store = Store(str(tmp_path / "p.db"))
        settings = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X")],
```

<!-- block: local-development/tests/test_connection_modes.py | edit -->
```python
            assert self._wait(lambda: "host" in self.polled)
            east = settings.cluster("east")
            assert east is not None and east.credential_kind == "self-login" and east.source == "secret:gsd-cluster-east"
            assert "east" not in poller._cluster_stops and "east" not in self.polled
            assert next(r for r in store.clusters() if r["id"] == "east")["credential"] == "self-login"
        finally:
            poller.stop()
```

```python
            assert self._wait(lambda: "host" in self.polled)
            east = settings.cluster("east")
            assert east is not None and east.credential_kind == "self-login" and east.source == "secret:gsd-cluster-east"
            assert self._wait(lambda: any(f.code == "fleet-credential-missing" and f.secret == "east"
                                          for f in settings.cluster_registry.findings()))
            assert "east" in poller._cluster_stops and "east" not in self.polled
            assert next(r for r in store.clusters() if r["id"] == "east")["credential"] == "self-login"
        finally:
            poller.stop()
```

<!-- block: local-development/tests/test_chart_connection_modes.py | edit -->
```python
        assert (settings["saTokenLookupSourceNamespace"], settings["saTokenLookupSourceServiceAccount"], settings["saTokenLookupTokenSecretName"]) \
            == ("group-sync-operator", "group-sync-dashboard-cluster-poller", "")
        assert settings["replicaCount"] == 1
```

```python
        assert (settings["saTokenLookupSourceNamespace"], settings["saTokenLookupSourceServiceAccount"], settings["saTokenLookupTokenSecretName"]) \
            == ("group-sync-operator", "group-sync-dashboard-cluster-poller", "")
        assert settings["replicaCount"] == 1


class TestTheCredentialLifecycleInTheChart:
    """SPEC_S4c §3.8 (#285): the ping's two values reach the ConfigMap; a self-login stanza above one replica is
    refused by name; the Lease rule renders wherever a fleet account is in use, election on or off — and a Lease
    stays the one object the application writes."""

    SL = {"name": "shared-rnd", "apiUrl": "https://api.crc.testing:6443", "userSelfLogin": True}
    OFF = {"leaderElection": {"enabled": False}}

    @staticmethod
    def _rules(out: str) -> list[dict]:
        return [r for d in yaml.safe_load_all(out) if d and d.get("kind") in ("ClusterRole", "Role")
                and not d["metadata"]["name"].endswith("-secrets-mint") for r in d.get("rules") or []]

    def test_the_ping_values_reach_the_configmap(self, tmp_path):
        for values, expected in (({}, (True, 86400)),
                                 ({"clusterConfig": {"fleetAccount": {"ping": {"enabled": False, "intervalSeconds": 3600}}}},
                                  (False, 3600))):
            ok, out = _render_values(tmp_path, [HOME], select="templates/configmap.yaml", values=values)
            assert ok, out[-600:]
            docs = [d for d in yaml.safe_load_all(out) if d and d.get("kind") == "ConfigMap"]
            settings = yaml.safe_load(next(d for d in docs if "clusters.yaml" in d["data"])["data"]["clusters.yaml"])
            assert (settings["fleetPingEnabled"], settings["fleetPingIntervalSeconds"]) == expected

    def test_self_login_above_one_replica_is_refused_by_name(self, tmp_path):
        ok, out = _render_values(tmp_path, [HOME, self.SL], values={"replicaCount": 2, **self.OFF, "reporting": {"enabled": False}})
        assert not ok and "cluster shared-rnd declares userSelfLogin with replicaCount 2" in out, out[-600:]
        ok, out = _render_values(tmp_path, [HOME, self.SL], values=self.OFF)
        assert ok, out[-600:]

    @pytest.mark.parametrize("clusters,values,renders", [
        ([HOME, SL], OFF, True),                                                              # a mode in use, election off
        ([HOME], {**OFF, "clusterConfig": {"fleetAccount": {"username": "svc-gsd"}}}, True),  # the chart names an account
        ([HOME], OFF, False),                                                                 # no account, election off
        ([HOME], {}, True),                                                                   # election on: as before
    ], ids=["mode-in-use-election-off", "username-election-off", "no-account-election-off", "election-on"])
    def test_the_lease_rule_renders_where_a_claim_is_needed_and_stays_the_only_write(self, tmp_path, clusters, values, renders):
        ok, out = _render_values(tmp_path, clusters, values=values)
        assert ok, out[-600:]
        rules = self._rules(out)
        leases = [r for r in rules if "leases" in (r.get("resources") or [])]
        assert bool(leases) is renders and all(sorted(r["verbs"]) == ["create", "get", "update"] for r in leases)
        writes = {"patch", "update", "create", "delete", "deletecollection", "*"}
        assert all(set(r.get("resources") or []) == {"leases"} for r in rules if set(r.get("verbs") or []) & writes)
```

<!-- block: local-development/tests/test_ui.py | edit -->
```python
        assert "onboard,sideload" in page.locator("#cc-head").inner_text()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

    def test_the_form_offers_remote_sar_and_starts_on_the_default_pair(self, page, cc_rig):
        """SPEC_D2b §3.3: the form starts on the pair a remote that states nothing resolves to, and offers
        remote-sar with its meaning; same-as-host says how a reader is matched (design D3)."""
```

```python
        assert "onboard,sideload" in page.locator("#cc-head").inner_text()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

    def test_the_fleet_account_rows_and_a_self_login_expiry_are_instants(self, page, cc_rig):
        """SPEC_S4c §3.10 (#285): one head row per fleet account — when the daily ping last confirmed it, on which
        cluster, what the last ping said, and a suspended badge while its Lease holds an entry — and a self-login
        cluster's credential row says when its session expires. Instants as the service stamps them; 375 px."""
        from gsd.clusterconfig import parse_secret
        from test_clusterconfig import _secret
        base, host, settings = cc_rig
        east, = settings.cluster_registry.discovered()
        sl = parse_secret(_secret("gsd-cluster-sl", cluster="sl", config={"userSelfLogin": True, "ldapConnectionBootstrap": "svc-gsd"}),
                          host_name="crc-local")
        settings.cluster_registry.replace([east, sl], [], at="now")
        signals = _SCOPED_APP.state.signals
        signals.note_fleet_accounts({
            "svc-gsd": {"lease": "gsd-fleet-3b1f9c0e7a2d4e61", "last_attempt": "2026-09-22T06:00:04Z", "last_ok": "2026-09-22T06:00:05Z",
                        "last_outcome": "ok", "last_target": "shared-rnd",
                        "suspended": [{"target": "https://api.other.example.com:6443", "since": "2026-09-22T14:03:11Z", "code": "login-refused"}]},
            "svc-new": {"lease": "gsd-fleet-0000000000000000", "last_attempt": None, "last_ok": None, "last_outcome": None,
                        "last_target": None, "suspended": []}})
        signals.note_self_login("sl", {"state": "current", "expires_at": "2026-09-23T06:00:05Z", "renew_at": "2026-09-23T04:00:05Z"})
        try:
            page.set_viewport_size({"width": 375, "height": 812})
            page.set_extra_http_headers({"X-Forwarded-User": "root"})
            page.goto(f"{base}/#page=clusters")
            page.wait_for_selector("#cc-cluster-sl")
            row = page.locator("[data-cc-fleet='svc-gsd']").inner_text().replace("\n", " ")
            assert "last confirmed 2026-09-22 06:00 on shared-rnd · ok" in row and "suspended" in row, row
            assert "not yet confirmed by the daily ping" in page.locator("[data-cc-fleet='svc-new']").inner_text()
            credential = page.locator("#cc-cluster-sl .cc-kv", has_text="credential").inner_text().replace("\n", " ")
            assert "self-login" in credential and "expires 2026-09-23 06:00" in credential, credential
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        finally:
            signals.note_fleet_accounts({})
            signals.note_self_login("sl", None)

    def test_the_form_offers_remote_sar_and_starts_on_the_default_pair(self, page, cc_rig):
        """SPEC_D2b §3.3: the form starts on the pair a remote that states nothing resolves to, and offers
        remote-sar with its meaning; same-as-host says how a reader is matched (design D3)."""
```

<!-- block: local-development/tests/test_specs_index.py | edit -->
```python
    pyproject.toml's current rungs. S4c said `chart 0.51.0` on a main at 0.52.1, and 0.51.0 had already
    shipped (review of #325, all three seats; the test is OB1-lite's). S3 and S4b are recorded by name
    and, since the index took the four-word lifecycle, are `in progress` and `merged` — this rule reads
    `specified` rows only."""
    chart = re.search(r"^version: (\d+\.\d+\.\d+)$",
                      (REPO / "charts/group-sync-dashboard/Chart.yaml").read_text(), re.M).group(1)
    app = re.search(r'^version = "(\d+\.\d+\.\d+)"$', (REPO / "local-development/pyproject.toml").read_text(), re.M).group(1)
    changelog = (REPO / "docs/CHANGELOG.md").read_text()
    as_tuple = lambda v: tuple(int(x) for x in v.split("."))  # noqa: E731
    checked = []
    for fid, row in ROWS.items():
        if row["status"] != "specified" or re.search(rf"SPEC_{fid}[_ §.:,)]", changelog):
            continue
        m_chart = re.search(r"chart (\d+\.\d+\.\d+)", row["version"])
        m_app = re.search(r"app (\d+\.\d+\.\d+)", row["version"])
        if m_chart:
            checked.append(fid)
            assert as_tuple(m_chart.group(1)) > as_tuple(chart), (fid, row["version"], f"Chart.yaml is already {chart}")
        if m_app:
            assert as_tuple(m_app.group(1)) > as_tuple(app), (fid, row["version"], f"pyproject.toml is already {app}")
    assert "S4c" in checked, checked


def test_s4c_gates_every_bound_failure_per_account() -> None:
```

```python
    pyproject.toml's current rungs. S4c said `chart 0.51.0` on a main at 0.52.1, and 0.51.0 had already
    shipped (review of #325, all three seats; the test is OB1-lite's). S3 and S4b are recorded by name
    and, since the index took the four-word lifecycle, are `in progress` and `merged` — this rule reads
    `specified` rows only. S4c was the row it was written for; its implementation (#285) takes the chart
    rung it names and records it by name, so the rule may have no row to read until the next spec."""
    chart = re.search(r"^version: (\d+\.\d+\.\d+)$",
                      (REPO / "charts/group-sync-dashboard/Chart.yaml").read_text(), re.M).group(1)
    app = re.search(r'^version = "(\d+\.\d+\.\d+)"$', (REPO / "local-development/pyproject.toml").read_text(), re.M).group(1)
    changelog = (REPO / "docs/CHANGELOG.md").read_text()
    as_tuple = lambda v: tuple(int(x) for x in v.split("."))  # noqa: E731
    for fid, row in ROWS.items():
        if row["status"] != "specified" or re.search(rf"SPEC_{fid}[_ §.:,)]", changelog):
            continue
        m_chart = re.search(r"chart (\d+\.\d+\.\d+)", row["version"])
        m_app = re.search(r"app (\d+\.\d+\.\d+)", row["version"])
        if m_chart:
            assert as_tuple(m_chart.group(1)) > as_tuple(chart), (fid, row["version"], f"Chart.yaml is already {chart}")
        if m_app:
            assert as_tuple(m_app.group(1)) > as_tuple(app), (fid, row["version"], f"pyproject.toml is already {app}")


def test_s4c_gates_every_bound_failure_per_account() -> None:
```
