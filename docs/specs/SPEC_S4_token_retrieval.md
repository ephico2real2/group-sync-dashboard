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

**So renew at 80 % of the stated lifetime**, never on a fixed clock. It is what the kubelet does for a
projected token, and the reason is that a renewal beginning at expiry has already failed and leaves
no room for the one retry a transient deserves.

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

- **A refused password is never retried.** One failure, a `login-refused` finding quoting the
  server's own words, stop until the declaration changes. This needs no coordination and therefore
  ships with #283, not with the coordinator.
- **`UNREACHABLE` is safe to retry** — bounded exponential, a stated ceiling, then give up out loud.
  Nothing locks on a connection failure. `ClusterError` already carries this distinction and nothing
  consumes it yet.
- **Suspension is per credential, not per cluster**, and needs durable state so a restart does not
  forget and begin the walk again (#285).
- **The daily ping stands down on a refusal.** One failed bind a day is under most thresholds, until
  a directory whose counter does not reset.

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

- **#283 — the login.** The flow, the expiry, the retry policy. No storage, no schedule.
- **#284 — retrieve and write.** The SA token read, the Secret, revoke-on-supersede, and the
  `writes.enabled` dependency refused at render.
- **#285 — the lifecycle.** The daily ping, `self-login` renewal, per-credential suspension.
- **#286 — token litter.** 144 `OAuthAccessToken` objects on the lab; policy for what we mint.

## 10. What I am not sure about

Stated as questions, because a design document that only contains its author's confidence is not
worth reviewing.

1. **Can the fleet account log in at all?** Everything downstream assumes it. On the lab the named
   account is `cn=ocp-oauth-bind-serviceid,ou=TrustedApplications,…` — a directory *bind* identity —
   while the IDP's user search requires `(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,…))`. A
   `cn=`-rooted entry in a service OU typically satisfies neither. **Binding to a directory so the
   OAuth server may search it is a different capability from being findable as a user.** Verify by a
   directory read, never by attempting the login — a lockout would take down the account the cluster
   authenticates *every* user with.
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
