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
The baseline values/Secret trigger still gates bound login failures as #284 specifies; this does not
claim that its successful logins were globally one-shot. Cross-process and cross-target account-wide
lockout protection is #285's work, not measured or implemented by this feature. Keep one replica.

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
| how often it authenticates | once per cluster, while that cluster is awaiting a credential | never re-authenticates; the token is presented |
| lifetime | a directory password, rotated by policy | **no `exp` claim at all** |
| stored where | one Secret, named by `clusterConfig.fleetAccount.passwordSecret` | `gsd-cluster-<name>`, written by the retrieval |

The bind happens only while a cluster is *pending* a credential
(`gsd/poller.py#Poller._retrieve_pending` selects `credential_kind == CREDENTIAL_LOOKUP`). Once the
token is written, the cluster leaves that set and the LDAP account is not used for it again.

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
| `userSelfLogin` | — | **not built** — `gsd/config.py#CREDENTIAL_PENDING_REASONS` records it as #285's work |
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

## 4. Recovering a cluster today

There is **no in-product way** to re-establish a credential. Today it is done by hand, and it
requires being cluster-admin on **both** clusters with two sessions:

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
| `oc`, `kubectl`, or GitOps | **up to one binding interval** (`bindingIntervalSeconds`, 300s default) |

Measured on the reference cluster: 8m30s for a newly created Secret, and 3m42s / 4m08s for a rotation
— all via `oc`. Detail in [`docs/polling-and-discovery.md`](../../docs/polling-and-discovery.md).

## 5. The intended recovery flow — **PLANNED**

Two steps, deliberately separate.

**Refresh (#311).** Probe an existing cluster **with the credential it already holds** and return the
outcome. It answers "is this actually broken, and how?" without changing anything.

> **Refresh probes; it never re-binds.** A probe is an ordinary authenticated API call with a stored
> bearer token — no LDAP bind, no fleet account, no lockout exposure. A refresh that triggered a
> *retrieval* would be an on-demand bind, which is the thing to avoid.

**Rejoin (#316).** When Refresh reports `auth_failed`, an administrator clicks Rejoin and supplies
**their own** cluster-admin username and password *at that moment*. The dashboard authenticates to
the remote cluster as that person, retrieves the ServiceAccount token, writes
`gsd-cluster-<name>`, and **discards the credentials**. Nothing is stored.

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
- Rejoin's credentials are never stored, never logged, never echoed — in the Secret, a finding, or an
  error.
- The credential gate still applies to Rejoin: once a password is on the wire the outcome is
  terminal. No retry on a 401, and **none on the HTTP 500 a locked directory returns** — a locked
  389-ds account answers LDAP code 19, which OpenShift surfaces as a 500, so "it failed, try again"
  is wrong precisely when the account is already locked.
- Both are admin-tier only.
