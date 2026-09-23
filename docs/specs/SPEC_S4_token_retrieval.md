# SPEC S4 — retrieving a cluster credential as the fleet account

| | |
|---|---|
| Programme | Cluster configuration as labelled Secrets (#230), continued — S3 specified the modes and S3a shipped their keys; this is the machinery that actually obtains a credential |
| Batch | S — cluster configuration |
| Release | — (post-programme) |
| Version on release | app and chart bumps per step, assigned at each step's PR |
| Issue | [#283](https://github.com/ephico2real2/group-sync-dashboard/issues/283) |
| Status | specified |
| Source | the operator's design of 2026-09-21, with the challenging-client flow and the session lifetime measured on the reference cluster |

**Steps:** #283 (the login), #284 (retrieve and write), #285 (the lifecycle), #286 (token litter).
**Parent:** `docs/specs/SPEC_S3_connection_modes.md` — §3 the modes, §3.1 the bootstrap account,
§3.2 the session lifetime, §5.1 the Secret this produces, §9.3 the lockout rules.

This is a **design** document, written to be attacked. Where I am confident, I say why and show the
measurement. Where I am not, §10 says so plainly rather than smoothing it over.

---

## 1. What this is, in one paragraph

A permanent ServiceAccount token already exists on each remote cluster, and a central LDAP account
has been granted access there by design. All the dashboard does is **fetch it and store it locally**:
log in to the remote as the fleet account, read the ServiceAccount's token, write it into this
release's namespace as a labelled cluster Secret. Discovery then picks that Secret up on its next
cycle and the cluster starts polling. The dashboard is a courier, not an authority.

**Where it writes depends on where the mode was declared, because a Secret is named for its cluster
and the reader fails closed on two Secrets for one cluster.** A **values** stanza gets a new Secret
`gsd-cluster-<name>`, which shadows the stanza by SPEC_S1's rule — and that shadow is the design's
own, so the reader must not report it as `shadows-values-entry` when the stanza declares a mode and
the Secret's `token-source` names it; otherwise every retrieved cluster carries a permanent finding.
A **Secret-declared** stanza (`config.saTokenLookup: true` inside `gsd-cluster-<name>`) is **updated
in place**: `config` becomes `{bearerToken, tlsClientConfig.caData}`, the mode key leaves, and the
provenance annotations stay as the memory of the mode — exactly the shape of the hand-made
`gsd-cluster-shared-rnd` (SPEC_S3 §5.1). A second Secret would be `duplicate-cluster-name` and load
**neither**; a `create` over the existing one is refused `secret-exists`. Without this, one of the two
equal declaration paths is simply not implementable.

**The target's CA must be declared with the mode.** Before the first retrieval there is no `caData` —
that is what the lookup fetches — so the login verifies against `trusted-bundle`, and on a private-CA
estate the lookup cannot start without the CA it was going to fetch. The OAuth host is also on the
**ingress** certificate rather than the API's, so it is verified by the same bundle only where that
bundle carries the ingress CA (it does on the reference cluster: `CN=ingress-operator@…` is in the
ServiceAccount's `ca.crt`, and the route verifies with it while the system store returns 19).

## 2. What already ships — do not rebuild it

Measured on `main` at chart 0.49.0:

| piece | state |
|---|---|
| the three stanza keys, in both readers, six refusals, equivalence-guarded | **ships** (S3a) |
| a mode cluster is listed and **not polled** (`credential_pending`) | **ships** |
| `secret_object()` produces the exact target shape, verified field-for-field against the lab's | **ships** (#230 S2) |
| the three provenance annotations, omitted when unset; `managed_by` parameterised; `enabled` as a word | **ships** (#282) |
| `get` on the fleet password Secret, in the release namespace **or** another | **ships** (#282) |
| **the login, the read, the write, the schedule** | **this spec** |

`saTokenLookup` appears in exactly two files today — `gsd/config.py` and
`gsd/clusterconfig/parser.py` — and both only *record* the declaration. Nothing in the tree performs
a login, an exchange or a TokenRequest.

## 3. The mechanism — measured, not assumed

`oc login -u … -p …` is the OAuth **challenging-client** flow. `gsd/auditlog.py` already documents
the shape (`cli` = `GET /oauth/authorize?client_id=openshift-challenging-client`). Run against the
reference cluster with the htpasswd `developer` account, 2026-09-21:

```
curl -u <user>:<pass> -H "X-CSRF-Token: 1" \
  "https://<oauth-host>/oauth/authorize?client_id=openshift-challenging-client&response_type=token"

HTTP/1.1 302 Found
Location: .../oauth/token/implicit#access_token=sha256~…&expires_in=31536000&scope=user%3Afull&token_type=Bearer
```

Three facts fall out, each load-bearing:

1. **The expiry arrives with the token.** `expires_in` is in the redirect fragment; no second call.
   Confirmed equal to the cluster's `.spec.tokenConfig.accessTokenMaxAgeSeconds`.
2. **It is in the fragment, not the body.** A fragment is never sent to a server and is not in the
   response body — it must be read off the `Location` header, and a client that follows redirects
   automatically will lose it.
3. **The OAuth host is not the API host.** On the lab, `oauth-openshift.apps-crc.testing` against an
   API of `api.crc.testing:6443`. Discover it; do not construct it by string surgery.

### 3.1 The lifetime is the target's, and the lab proves why that matters

CRC's sessions last **31536000 seconds — a year.** SPEC_S3 §3.2 already says to read
`accessTokenMaxAgeSeconds` rather than assume 24 hours; this is that rule with a number attached. A
renewal schedule hard-coded to "daily" is wrong by 365× on this cluster — in the safe direction — and
fatally wrong on a cluster configured to an hour, which needs renewing every 48 minutes.

**So renew a fixed margin before expiry — 1 to 2 hours — not a percentage of the lifetime** (the
operator's rule, 2026-09-21, and it is better than the percentage this section first specified).

```
renew_at = expires_at − margin        margin = min(2 h, ¼ × lifetime)
```

**The point is that this needs no knowledge of the environment.** The session is self-describing: the
login hands back `expires_in`, so the dashboard records the absolute instant the session dies and
schedules re-authentication before it. It never has to know, ask, or assume what the cluster
configured — an estate that tightens tokens to an hour and one that loosens them to a year are the
same code path, because both are answered by the value the target just returned.

That also removes a permission and a failure mode the earlier draft introduced. **Nothing needs to
read `oauth/cluster` to schedule a renewal**: §3.2's rule — *read the lifetime rather than assume it* —
is satisfied by the session itself, not by querying the OAuth CR. Do not add a `get oauths/cluster`
grant for this.

**And the margin is a retry budget, not a fraction.** What it has to buy is time to fail, back off,
retry, alert a human, and still renew before the session actually dies. That is an absolute quantity:
two hours is two hours whether the session lasts a day or a year. Scaling it as a percentage produces
nonsense at both ends — 80 % of a year renews **73 days early** for no benefit, and 80 % of a
one-hour session leaves **12 minutes** to notice and recover.

The `¼ × lifetime` term is only a floor for unusually short sessions, so a cluster that sets an hour
renews at 45 minutes rather than at a margin larger than the session itself.

| `accessTokenMaxAgeSeconds` | where | renews |
|---|---|---|
| 86400 (24 h) | **real OpenShift, the documented default** | 2 h before expiry — once a day |
| 31536000 (365 d) | the reference cluster (CRC) | 2 h before expiry — once a year |
| 3600 (1 h) | an estate that tightens it | 15 min before expiry |

**What this costs is one login per session lifetime, which is the floor.** A session cannot be
renewed less often than it expires, and renewing it earlier buys nothing but more binds — which is
the one thing §6 says to spend carefully.

**Two clusters the same rule must survive.** OpenShift's default is 24 hours (`accessTokenMaxAgeSeconds:
86400`; `0` means "use the default"), while CRC sets `31536000` in `crc-org/snc`'s `oauth_cr.yaml`,
commented *"token max age set to 365 days"*. **So the lab renews once a year and a real cluster once a
day** — which is a trap for #285's tests: a renewal test run only on CRC will not fire naturally
inside any test run. Proving it needs a cluster with a realistic value, the lab's value temporarily
lowered, or an injected clock, and the test must say which.

**The one thing the session does not tell you: inactivity.**
`oauth/cluster .spec.tokenConfig.accessTokenInactivityTimeout` (300 s minimum; unset on the reference
cluster) invalidates a session that has merely been *idle*, whatever `expires_in` says — and a standby
replica or an unreachable target can idle one.

**Handle it reactively rather than by reading the CR**, for the same reason as above: a `401` on a
poll with a credential whose `token-source` is `self-login` means *re-authenticate*, not *the password
is wrong*. That covers an inactivity timeout, an administrator revoking the session, and a cluster
whose policy changed underneath us — without the dashboard knowing any of those settings. It is the
one place where a `401` is **not** treated as a refusal, and the distinction is the credential kind,
which the Secret already records.

## 4. The two identities

Neither is given anything on the other side, which is why both grants are narrow:

| identity | where | does what | needs |
|---|---|---|---|
| the LDAP fleet account | on the **remote** cluster | authenticates, reads the permanent SA token | its password, locally — `get` on one Secret |
| the dashboard's ServiceAccount | on the **local** cluster | writes `gsd-cluster-<name>` | `create` on secrets in its own namespace |

## 5. The two modes are not variations of one thing

| | `remote-lookup` (`saTokenLookup`) | `self-login` (`userSelfLogin`) |
|---|---|---|
| what is stored | the target SA's **permanent** token | nothing durable; the session **is** the credential |
| binds after onboarding | **one a day**, for the whole fleet | **one per cluster per renewal cycle** |
| adding the 21st cluster | no change to the bind rate | +1 login every cycle, forever |
| a failed renewal | a finding; clusters keep polling | **that cluster stops polling** |
| tab wording | `expires: current` (#248) | a real date |
| at rest | a long-lived token | only the fleet password |

`self-login` buys "nothing long-lived at rest" and pays in bind rate and blast radius. That is the
concrete reason `saTokenLookup` is preferred, and it is a trade an estate should make knowingly.

## 6. The lockout constraint governs everything

The fleet account is **one account for the estate**. A directory locks an account after a few failed
binds, so every design decision here is downstream of "how many binds does this produce, and what
happens when one is refused".

- **A refused password is never retried** — but two things the first draft assumed are wrong,
  measured against the reference cluster's OAuth server.

  *There are no "server's own words" to quote.* A refusal is a bare `401` with
  `Www-Authenticate: Basic realm="openshift"` and **an empty body**, and the same 401 answers a
  wrong password, a username the directory cannot find, and (unmeasured, escalated) probably a
  directory outage. The finding can quote a status line and nothing more, so it must say what was
  tried rather than pretend to relay a reason. A 401 *without* that header is a client fault — a
  missing `X-CSRF-Token` returns 401 too — and must not be recorded as a refusal.

  *"Stop until the declaration changes" is the wrong re-arm trigger.* The password is not in the
  declaration: `values.yaml` says it is "never a literal in values — a Secret reference, read at
  connect time only", and the normal fix for a refusal is **rotating that Secret**, which changes no
  stanza. Suspension is keyed on `(username, hash of the password value)` and re-arms when either
  moves.

  *And "needs no coordination" was too strong.* It is an **in-memory gate keyed on credential
  identity, consulted by every login call site** — which is the coordinator's in-memory half, not an
  absence of one. Two human-driven paths already exist that would otherwise bypass it:
  `request_discovery()` wakes discovery on every tab write, and `POST /api/clusterconfigs/test` is a
  button. Without durable state a pod restart is one more bind, and above one replica there is no
  election at all (below).
- **`UNREACHABLE` is safe to retry** — bounded exponential, a stated ceiling, then give up out loud.
  Nothing locks on a connection failure. `ClusterError` already carries this distinction and nothing
  consumes it yet.
- **Suspension is per credential, not per cluster**, and needs durable state so a restart does not
  forget and begin the walk again (#285).
- **The daily ping stands down on a refusal.** One failed bind a day is under most thresholds, until
  a directory whose counter does not reset.
- **One retriever per estate.** Above one replica the chart forces leader election **off** and every
  pod polls for itself, so every replica would log in, ping, and keep its own suspension state — N
  binds where this design promises one. Until the gate is shared through the namespace rather than
  the per-pod database, a mode stanza with `replicaCount > 1` is refused at render, in the set with
  the other mode refusals.
- **A login that succeeds and a read that fails is not a refusal**, so nothing stops it repeating:
  a missing SA Secret or revoked RBAC would re-run every discovery cycle — 288 successful binds and
  288 tokens a day, per broken cluster. The bounded backoff must cover the **whole retrieval**, not
  only the connect.

## 7. Why none of this is about report latency

The instinct is to protect the report path with a timeout. It does not need one: **the report service
never talks to a cluster.** It reads `Snapshot(newest_snapshot(...))` — a file — and its only HTTP
client posts to itself.

A connection failure cannot make a report slow. It can only make that cluster's data **stale**, or
**absent** if it was never polled — and an absent cluster fails its own run with `unknown cluster in
the snapshot` and no other. **Retry protects snapshot freshness, not request latency**, and the
snapshot is the airlock between the two. That is what makes it safe to retry generously in the
background.

## 8. Failure vocabulary

Extends #245 rather than replacing it. `phase=` stays the closed set — `credential` and `connect`
already name where these fail, and a `retry` phase would describe the mechanism rather than the place.

New fields: `attempt=<n>/<ceiling>`, `retry_in=<seconds>`, `gave_up=true` with the ceiling and last
error, `suspended=<credential>` with the count of what it stopped. Each joins the closed set in the PR
that emits it, and the redaction pin is extended to drive a failure in every new path with the
password in force (§3.1 rule 4).

## 9. Decomposition

- **#283 — the SESSION, not just the login.** Log in, read the expiry, apply the retry policy — and
  **log out**. A session is a context manager: `DELETE useroauthaccesstokens/<sha256~name>` on exit,
  whatever happened in between. This corrects the first draft, which put "revoke what it supersedes"
  in #284 and had it revoking the **wrong object**: what #284 stores is the target SA's token from a
  `kubernetes.io/service-account-token` Secret, which the dashboard *cannot* revoke — it dies only
  when the target deletes the Secret, which is why the tab words it `expires: current`. What actually
  litters is the `OAuthAccessToken` that **#283's login** mints, which #284 never stores and so never
  supersedes. Owning logout here makes the lookup and the ping leave nothing *by construction*.
- **#284 — read and write.** The SA token read, written as a function **#285 reuses with
  `write=False`**; the Secret write; the `writes.enabled` dependency refused at render **and** at
  runtime, because a Secret-declared mode is invisible to `helm template`.
- **#285 — the lifecycle.** The daily ping (which is #284's read without the write — so it needs
  #284, not only #283), `self-login` renewal at the fixed margin §3.1 states, and the
  per-credential gate: in-memory in #283, durable and replica-shared here.
- **#286 — pre-existing litter only.** Everything from #283 onward leaves nothing behind. This is
  about the objects already there — and most are not from logins at all: of 140 on the lab, **95 are
  the oauth-proxy's own browser sessions**, so a sweep policy that only inspects the challenging
  client misses two thirds. It deletes nothing it did not create.

## 10. What I am not sure about

Stated as questions, because a design document that only contains its author's confidence is not
worth reviewing.

1. ~~**Can the fleet account log in at all?**~~ **ANSWERED — and the answer refutes what this
   section first claimed.** I argued that a `cn=`-rooted entry in `ou=TrustedApplications` would
   satisfy neither the IDP's `(uid=*)` nor its `memberOf` requirement, so the whole design might rest
   on an account that cannot authenticate. **It authenticates, and already has.** Measured on the
   reference cluster:

   ```
   $ oc get user ocp-oauth-bind-serviceid -o json
   name     : ocp-oauth-bind-serviceid
   created  : 2026-09-19T00:48:44Z
   identity : ldap-local -> cn=ocp-oauth-bind-serviceid,ou=TrustedApplications,dc=ephico2real,dc=com
   ```

   OpenShift creates a `User` on **first successful login through an identity provider**, so the
   object's existence is the proof — and two `openshift-challenging-client` tokens for it, from the
   same minute, are the receipts. The `ldap-acls` ConfigMap states why: the account is itself a member
   of the gate group, and therefore a login identity as well as a bind identity.

   **The check to prescribe is `oc get user <name>` / `oc get identities` on the TARGET** — no bind,
   no `ldapsearch`, and it also proves the User name the RBAC binds to. The caution that stands is
   narrower than the doubt: never test this by *attempting* a login, because a lockout takes down the
   account the cluster authenticates every user with. Reading the User object costs nothing and
   answers it.
2. **Should `writes.enabled` split?** It currently means *a person may add a cluster from the tab*.
   With #284 it also means *the dashboard may mint cluster access unattended*. Those differ in kind.
3. **What does a retriever call itself in `managed-by`?** `token-source` says how the credential was
   got; `managed-by` says who created the Secret. The second needs a word, and I have not invented one.
4. **Should the daily ping revoke its own token?** It mints, confirms, and discards. Deleting it is
   one call; the argument against is that a revoke is a write against a cluster we are otherwise only
   reading.
5. **Is `self-login` worth building at all?** Given §5's table, an estate may rationally never choose
   it. It may be right to specify it and not implement it until someone asks.
6. **The per-credential coordinator is the largest unknown.** §9.3 records that no seam exists:
   `Poller` discards `poll_once`'s return value and `ClusterRegistry`'s lock guards discovery only.
   A process-wide gate plus durable state is the biggest single piece of work here and the one most
   likely to be wrong first.
