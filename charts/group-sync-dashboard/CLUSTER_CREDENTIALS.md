# Cluster credentials: how a connection is made, how it breaks, how to get it back

## Credential-free onboarding ConfigMaps (#293, SPEC_S5)

A release-namespace ConfigMap labelled `groupsync-dashboard.io/config-type: onboard` or `sideload`
contains `data.clusters.yaml`, whose `clusters:` list is values-shaped and uses `saTokenLookup: true`.
The manifest is in `docs/CLUSTER_STANZA.md`. The #284 lookup reads the remote token and the existing
writer creates `gsd-cluster-<name>` with `groupsync-dashboard.io/secret-type: cluster`. Nobody supplies
that token in the ConfigMap. Fleet account/password settings and the remote grants are unchanged.

`insecureSkipVerify: true` is accepted, exactly as in values; the generated Secret carries that
choice as `tlsClientConfig.insecure: true`. Whoever can write a labelled ConfigMap in the release
namespace can direct the fleet account's bind to a host of their choosing, with or without TLS
verification. ConfigMap write access there is therefore trusted like the fleet credential, and the
platform team must keep it restricted. This is the operator's final ruling of 2026-09-25:
"I need this feature badly. So insecure is required in configmap."


These generated Secrets carry `groupsync-dashboard.io/managed-by: configmap-onboarding`, plus the
existing `token-source: remote-lookup`, source namespace/ServiceAccount and lookup account. Three
additional annotations record `groupsync-dashboard.io/source-configmap`,
`groupsync-dashboard.io/source-configmap-uid`, and `groupsync-dashboard.io/connection-hash`.
The hash covers connection inputs and declared trust, never a password or token; it excludes policy.
They are bookkeeping markers inside the trusted namespace, not authentication or a tamper-proof claim.
UI and values-lookup Secrets are not adopted. Removing the stanza removes only this generator's local
copy; it does not revoke the remote ServiceAccount token or delete its source Secret.

Edit the source ConfigMap to change policy, disable or remove a generated cluster. The tab names it
and does not offer Rotate/Delete for a generated row; the API refuses those operations too. The
reconciler preserves a token through policy edits. Connection edits prune the old output, then await
a new lookup. Cleanup repeats until successful and reports every retained displaced credential.

The existing process-lifetime `CredentialGate` is shared by this trigger. ConfigMap logins also mark
success before the token read: a later failed read/write cannot trigger a second bind for the same
canonical target/account/password. Renaming or relabelling a ConfigMap, changing policy or removing
and re-adding an entry does not reset it. A missing token output after that budget was spent remains
pending, with a finding; correct the cause before rotating the password or deliberately restarting.
Since #315, every bound login failure gates that account and password on every target in this
process, for values, Secret and ConfigMap triggers alike. Successful ConfigMap sessions still spend only
their own target's budget; successful values/Secret logins are not globally one-shot. Account means the
exact configured username string: use one spelling for one directory identity. Since #285 every login claims
the fleet account's Lease (`gsd-fleet-<sha256(username)[:16]>` in the release namespace) and records its attempt
there before the password is sent; a session clears it and a refusal replaces it, so a restart, a crash or
another replica reads it and does not send the password again; a success is still not recorded there. Keep one
replica. Since #481 the same record is also kept beside the database, in `fleet-gate.json` on the data volume, because
`crc start` deletes every Lease on the cluster: a deleted Lease is put back from that copy, so it sends no refused
password again and pings no second time that day, and deleting the Lease no longer clears its entry (clear it as
[`RUNBOOK.md`](RUNBOOK.md) section 7 says). With `persistence.enabled: false` the copy lasts only as long as the pod.

Companion to [`docs/CLUSTER_STANZA.md`](../../docs/CLUSTER_STANZA.md), which covers *what a stanza may
say*. This covers *what happens to the credential afterwards* — who holds it, what fails, and how an
administrator recovers a cluster whose credential has gone bad.

Sections marked **PLANNED** describe work that does not exist yet and name the issue. Everything else
is the behaviour of the chart as shipped.

## 1. The separation this design rests on

**An LDAP account bootstraps the connection. A long-lived ServiceAccount token does the polling.**

That is deliberate, and it is why the two credentials have opposite lifetimes:

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
account still works, and stores nothing — confirming is not renewing. It logs in only as an account the
configuration names now — `clusterConfig.fleetAccount.username`, or a declaration's `ldapConnectionBootstrap`
(`gsd/poller.py#Poller._declared_accounts`, #432). A retrieved Secret's `lookup-account` says who fetched its
token; once the configuration stops naming that account, the one password Secret may hold another account's
password, so the ping does not log in as it. Its row and its share of the metrics stay, read from its Lease.

**Why the polling token carries no expiry.** A token that expires needs something to renew it, and
renewal means re-authenticating — which would turn a once-per-onboarding bind into a recurring one
against an account the whole estate shares. A long-lived token moves that risk to a credential scoped
to one cluster, which can be revoked there without touching anyone else.

An expiry *can* be set on a ServiceAccount token if an estate wants one — `oc create token
--duration` issues one (minimum 10 minutes, enforced by the API server). Nothing renews it today, so
a cluster using one stops polling when it lapses. See §5.

## 2. Which mode stores what

| mode | what the Secret holds | what authenticates |
|---|---|---|
| static bearer token | the token, written by whoever created the Secret | the token |
| `saTokenLookup` | the token the retrieval fetched, plus provenance annotations | the token; the fleet account bound once to fetch it |
| `userSelfLogin` | — (nothing at rest) | the fleet account's own session, held in memory and renewed a fixed margin before it expires, `expires_at − min(2 h, ¼ × expires_in)` (#285, `gsd/selflogin.py#SelfLoginSessions`); a refused password suspends every self-login cluster on the account |
| `oauth` (username/password) | — | **not built** — refused as `oauth-exchange-not-built` |

A retrieval-written Secret is recognisable by its annotations, which a hand-written one lacks:

```
managed-by: sa-token-lookup    token-source: remote-lookup
source-namespace: <ns>         source-service-account: <sa>
lookup-account: <the fleet account that fetched it>
```

## 3. What failure looks like

Every failure is classified, and the words are stable (`gsd/kube.py`):

| outcome | meaning |
|---|---|
| `auth_failed` | the credential was rejected — expired, revoked, or wrong |
| `forbidden` | the credential is valid but lacks the RBAC |
| `unreachable` | network, DNS, or the API did not answer |
| cert outcomes | the TLS chain did not verify |

They appear in the poller log and on `GET /api/clusters`, which carries each cluster's error — an
unreachable cluster still appears, carrying it. A failing poll is scoped: the audit-log capture can
fail on its own ("group data is unaffected") without failing the whole cycle.

**One limitation worth knowing.** `auth_failed` is a bare 401 from the target, so an **expired**
token, a **revoked** token and a **withdrawn** grant are indistinguishable. The message says "invalid
or expired" because that is the honest limit of what a 401 supports.

## 4. Recovering a cluster by hand

With writes on, Rejoin (§5) re-establishes a credential from the tab. Without writes, or without the UI, it is done
by hand, and it requires being cluster-admin on **both** clusters with two sessions. The steps, with what each
answer means, are in [`RUNBOOK.md`](RUNBOOK.md), beside this file:

```sh
# on the REMOTE cluster — mint a token for the poller ServiceAccount
oc create token <poller-sa> -n <ns> --duration=20m

# on the DASHBOARD CONTROLLER cluster — write it into the cluster's Secret
oc patch secret gsd-cluster-<name> -n <release-ns> --type=merge \
  -p '{"stringData":{"config":"{\"bearerToken\":\"<token>\",\"tlsClientConfig\":{\"insecure\":false}}"}}'
```

Two things about that `patch`: `stringData` is write-only sugar — the API server base64s it into
`data` and the plaintext field disappears — and `--type=merge` replaces the whole `config` value,
so the *entire* JSON must be supplied, not just the token.

**How soon it takes effect depends on how the Secret was written**, not on what it says:

| written by | noticed within |
|---|---|
| the API (the Cluster Configurations tab) | **seconds** — the write wakes discovery |
| `oc`, `kubectl`, or GitOps | **up to one discovery interval** (`discoveryIntervalSeconds`, 300s default) |

Measured on the reference cluster: 8m30s for a newly created Secret, and 3m42s / 4m08s for a rotation
— all via `oc`. Detail in [`docs/polling-and-discovery.md`](../../docs/polling-and-discovery.md).

## 5. The recovery flow — Refresh, then Rejoin

Two steps, deliberately separate.

**Refresh (#311, application 1.2.0).** Press **Refresh** on the cluster's card in the Cluster Configurations tab.
The dashboard probes that cluster **with the credential it already holds** — `GET /version`, then `GET
/apis/user.openshift.io/v1/users/~` — and shows the answer under the card's `connection` row, in the words of §3:
`connected` (the API's `ok`), `auth_failed`, `forbidden`, `unreachable` or `cert-verify-failed`, with the instant
in UTC and the message. It answers "is this actually broken, and how?" without changing anything: nothing is
stored, rotated or re-polled. It presents the credential the dashboard holds now, so after a rotation made
with `oc` or GitOps it tests the new token only once discovery has read it (the table in §4); a rotation made
in the tab is read within seconds. A cluster whose credential has not been retrieved yet answers `pending` with the
reason, and a `userSelfLogin` cluster `not-probed`, without contacting the cluster. The button exists only for
cluster administrators and only when `clusterConfig.secrets.writes.enabled` is on; **a default install, with
writes off, has no Refresh**. The route is `POST /api/clusterconfigs/{name}/refresh`
(`local-development/API.md`).

> **Refresh probes; it never re-binds.** A probe is an ordinary authenticated API call with a stored
> bearer token — no LDAP bind, no fleet account, no lockout exposure. A refresh that triggered a
> *retrieval* would be an on-demand bind, which is the thing to avoid.

**Rejoin (#316, `docs/specs/SPEC_D4_cluster_rejoin.md`).** When Refresh reports `auth_failed`, or `pending` for a
cluster whose token was never fetched, the card offers **Rejoin…** on a Secret-sourced cluster or a `saTokenLookup`
stanza. An administrator types **their own** username and password for that cluster, *at that moment*. The dashboard
logs in to the remote once as that person (`gsd/rejoin.py#RejoinLogin`), asks the remote whether that person may
`update clusterrolebindings` there (D8, one `SelfSubjectAccessReview` with the login's own token), reads the poller's
token Secret, signs the login out, and writes `gsd-cluster-<name>` with `token-source: rejoin` and the person's name
(`rejoined-by`, `rejoin-account`, `rejoined-at`). **The password is discarded**: nothing about it is stored. The route is
`POST /api/clusterconfigs/{name}/rejoin` (`local-development/API.md`), and the steps are in
[`RUNBOOK.md`](RUNBOOK.md).

Why the admin's own credential rather than the fleet account:

- **nothing is stored** — it exists for one exchange;
- **it is attributable** — the remote cluster's audit log names the person who rejoined it, where a
  shared service account names nobody;
- **it is singular** — one bind, because a human pressed a button, not a schedule;
- **the blast radius is that admin's account**, not the account the whole estate authenticates with.

Every cluster admin already has access to the remote cluster, so the person who needs to fix the
connection can always authenticate.

### Rules these must obey

- Refresh **never** triggers a retrieval and **never** binds.
- Rejoin's password is never stored, never logged, never echoed — in the Secret, a finding, or an
  error. The Secret records the username as provenance (`rejoin-account`).
- The credential gate still applies to Rejoin: once a password is on the wire the outcome is
  terminal. No retry on a 401, and **none on the HTTP 500 a locked directory returns** — a locked
  389-ds account answers LDAP code 19, which OpenShift surfaces as a 500, so "it failed, try again"
  is wrong precisely when the account is already locked. A Rejoin sends the password at most once per
  press, and the poller's gate holds a refused password back in that pod until it restarts. The gate
  lives in memory, so a press that reaches a restarted pod or another replica can send the same
  password once more. A durable hold keyed by the username alone was declined for its operating cost:
  any failure would block that account's Rejoin on every pod until someone deleted the hold by hand,
  even after the right password (SPEC_D4, D4-7).
- Rejoin never uses the fleet account: it refuses any name a fleet path logs in as, and it writes
  `rejoin-account`, never `lookup-account`, which the daily ping logs in as with the fleet password.
- Both are for the cluster-admin tier only (#322), and exist only with writes on.

## 6. The `OAuthAccessToken` objects a login leaves (#286)

Every OAuth flow that issues an access token creates a cluster-scoped `OAuthAccessToken` object on that
cluster. It stays until it expires or is deleted. `oauths.config.openshift.io/cluster` sets the default
lifetime and an `OAuthClient` can override it; on the reference lab the default is a year
(`{"accessTokenMaxAgeSeconds":31536000}`, read 2026-09-27T08:52:23Z). The dashboard's policy, point by point:

1. **Fleet logins attempt to revoke their session token and extracted response candidates.** The login is a
   context manager: `gsd/fleetlogin.py#FleetLogin.__exit__` attempts cleanup when the caller is done, whether
   the work returned or raised. If session construction fails, the login attempts cleanup of the candidates
   extracted from the received 302. Extraction takes the first `access_token` value from the fragment of
   each separate `Location` header; it does not enumerate repeated values or scan multiple URLs joined into
   one header value. The lookup and the daily ping run inside that session (`gsd/fleetlookup.py#lookup`; the ping calls
   it with `write=False`). A `userSelfLogin` session goes through the same exit
   (`gsd/selflogin.py#SelfLoginSessions._exit`) when a renewal replaces it, when the account is suspended, when
   a login succeeds while the account is suspended, when the cluster's URL moves (the revoke goes to the URL
   that minted the token, which is never sent to the new one), and when the cluster is disabled or removed and
   its polling thread stops. Each is an attempt: point 2 says what happens when the target refuses it, and
   nothing runs once the process is killed. `gsd/fleetlogin.py` names its own boundary in its module
   docstring ("What this cannot cover"): after a read timeout, or a 302 whose `Location` httpx cannot parse,
   the target may have minted a token this process never saw, and that token cannot be named or revoked.

   The request is `DELETE /apis/oauth.openshift.io/v1/useroauthaccesstokens/<name>`, sent with the token itself
   as the bearer, and `<name>` is derived from that token (`gsd/fleetlogin.py#token_object_name`). The token's
   own scope authorises the call, so the chart grants nothing for it. The intent is `oc logout`'s, removing
   your own token, but `oc logout` deletes through `oauthaccesstokens` instead
   ([`RunLogout`](https://github.com/openshift/oc/blob/release-4.20/pkg/cli/logout/logout.go)). This revoke
   is the dashboard's cleanup on the target, using a token candidate supplied by the login response.
   For a valid issued session, leaving its object for the lab's reported one-year lifetime on a cluster the
   dashboard does not own is the larger intrusion; malformed-response candidates are not proof of minting. The account's Lease
   is a separate write, on the dashboard's own cluster.

   `tests/test_fleet_login.py#TestScopeIsLoginOnly.test_a_delete_only_ever_names_the_object_of_the_token_that_authorises_it`
   drives five mocked logins: the work returns, raises an `Exception` or a `BaseException`, the login fails
   after a token arrived, and a malformed 302 carries two tokens. For each it checks exactly one DELETE per
   received token, authorised by that token and naming the object an independent derivation expects, and no
   token listing. Its source check fails if another `gsd` module uses the token API's path or
   `USER_TOKEN_API`, or if `fleetlogin.py` makes a second DELETE call. It checks the syntax written today,
   not every way the code could be written. On the lab, #283's live test
   (`tests/test_live_fleet_login.py#test_the_session_is_obtained_and_revoked`) took the account's count
   0 → 1 → 0, as issue #286 records.
2. **A failed revoke is reported, and not retried.** Only a 200 or a 404 counts as gone
   (`gsd/fleetlogin.py#FleetLogin._revoke`). Anything else (a 401, a 5xx, no answer) is one
   `fleet-logout-failed` line that names the object by its `sha256~` name, never the token, and tells a
   cluster-admin to delete it. The name is left out for legacy unprefixed tokens, whose object name is the token itself,
   and when an unexpected exception escapes `_delete_token`: that handler discards the name even if
   derivation already succeeded. If that
   line cannot be written, a plain warning (`fleet-logout line could not be written`) takes its place; if
   that fails too, the failure is dropped, so that cleanup never replaces the caller's exception.
3. **No sweep of objects already there.** The dashboard revokes only tokens its own login's response
   carried, read off that response (`gsd/fleetlogin.py#FleetLogin._login`). A malformed 302 with multiple `Location` headers has each extracted
   token candidate revoked best-effort, because whether the target minted it is not known; extraction
   has the limits described in point 1. The dashboard
   never lists tokens and deletes by filter: a filter on user and client cannot tell a dashboard login from a
   person's `oc login`, and issue #286 records four `developer` sessions deleted by such a filter when only
   one was the dashboard's. There is no cleanup Job and no RBAC for one. The fleet account had two objects on
   the lab at 2026-09-27T08:52:23Z, both created 2026-09-19, before #283 was merged; the dashboard leaves them
   to the cluster owner.
4. **Browser sessions through the dashboard's oauth-proxy are the largest group, and the dashboard cannot
   revoke them.** Each sign-in creates an object whose client is the release's ServiceAccount: 131 of 189,
   the largest group, on the lab at 2026-09-27T08:52:23Z. Their tokens carry the scopes `user:info` and
   `user:check-access`, which permit no delete. A sign-out that revoked them was built, deployed and measured
   returning 403 (`docs/DESIGN_session_and_signout.md#Token revocation is refused by the token's own scope`).
   Widening the scope to `user:full` would fix that by handing the dashboard a token that can act as the user
   anywhere on the cluster, so the chart does not. Sign-out clears the proxy's cookie and does not delete the
   object.
5. **Cluster hygiene belongs to the cluster owner.** `accessTokenMaxAgeSeconds` and
   `accessTokenInactivityTimeout` on `oauths.config.openshift.io/cluster` are defaults for every OAuth client,
   and an `OAuthClient` can override either
   ([`TokenConfig`](https://github.com/openshift/api/blob/master/config/v1/types_oauth.go),
   [`OAuthClient`](https://github.com/openshift/api/blob/master/oauth/v1/types.go)). They are cluster-wide
   policy, so a namespaced chart does not set them
   (`docs/DESIGN_session_and_signout.md#Cluster token policy is not ours to set`), and the dashboard never
   does. An inactivity timeout limits whether a token can still be used; it is not a quota on how many objects
   exist, and changing it does not lower the timeout of tokens already issued. The dashboard runs no sweep of
   its own. Removing old objects, or shortening their lifetime, is the cluster owner's decision.

To see what a cluster holds, by client (read-only):

```sh
oc get oauthaccesstokens.oauth.openshift.io \
  -o jsonpath='{range .items[*]}{.clientName}{"\n"}{end}' | sort | uniq -c | sort -rn
```
