# SPEC S3 — connection modes: the dashboard obtains a remote cluster's credential

| | |
|---|---|
| Programme | Cluster configuration as labelled Secrets (#230), continued — S1 and S2 shipped the contract, the reader and the tab; this is how a cluster is connected without a token being pasted |
| Batch | S — cluster configuration |
| Release | — (post-programme) |
| Version on release | chart 0.45.0 |
| Issue | [#230](https://github.com/ephico2real2/group-sync-dashboard/issues/230) |
| Status | specified |
| Source | the operator's design of 2026-09-20 (#248), with the OAuth-trust trap measured on the reference cluster |

Issue #248. Depends on S1 (the Secret contract, merged), S2 (the tab and the write path, merged),
#119 P2 (the password grant) and #245's phase-aware logging (merged). This spec is the one that lets
an operator name a cluster and have the dashboard connect to it, instead of pasting a token.

## 1. The shape the operator asked for (2026-09-20)

```yaml
clusters:
  - name: dashboard                       # this pod's own cluster
    apiUrl: https://kubernetes.default.svc
    tokenFile: /var/run/secrets/kubernetes.io/serviceaccount/token
    caBundleFile: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
    dashboard_controller: true

  - name: shared-rnd                      # a REMOTE cluster, named, with no credential
    apiUrl: https://api.crc.testing:6443
    saTokenLookup: true                   # obtain the credential; do not expect one here
    ldapConnectionBootstrap: svc-gsd-fleet  # OPTIONAL — defaults to the chart's fleet account
```

The second stanza is the whole point: **it carries no credential.** `load_settings` refuses that today
(`one of tokenEnv or tokenFile is required`, `gsd/config.py`), which is correct for every mode that
exists now and must be relaxed for exactly this one — a stanza declaring `saTokenLookup: true` is
*asking the dashboard to obtain the credential*, not forgetting to supply one.

**The stanza is a configuration item, not a GUI prompt** (the operator, 2026-09-20: *"this stanza
should be treated a configuration item … i don't wanna manually input things in gui everytime"*).
Connecting a cluster is something an operator declares once, in the file their GitOps process already
owns, and it survives a reinstall without anybody retyping it.

Key spelling: the operator wrote `ldap-connection-bootstrap`; the nine keys the loader already knows
are camelCase (`apiUrl`, `tokenFile`, `caBundleFile`, `insecureSkipVerify`), so these two join them as
`ldapConnectionBootstrap` and `saTokenLookup`. One spelling, no aliases — an alias is a second way to
be wrong.

## 2. Three ways to author a cluster, all equal

All three are supported (the operator, 2026-09-20: *"we can type in gui too … we are supporting all"*).
They are three authoring paths onto **one** object, not three features:

| path | who writes it | what exists afterwards |
|---|---|---|
| **`clusters[]` in values** | the operator's GitOps repository | a stanza the loader reads at startup — `source: values` |
| **a labelled Secret** | any GitOps process, or the tab's YAML output applied by hand | `groupsync-dashboard.io/secret-type: cluster` — `source: secret:<name>` (S1) |
| **the Cluster Configurations tab** | an administrator typing, for a one-off or an urgent add | the same labelled Secret the other two produce (S2) |

**How many at a time** is what actually separates them (the operator, 2026-09-20: *"can type
multiple clusters or in gui or via onboarding secrets spec"*). `clusters[]` is a list: a whole estate
is onboarded in one edit, reviewed as one diff and applied once. A Secret is one cluster per object,
so a GitOps repository holds as many as it likes. The tab adds one at a time, by hand — right for an
urgent add, wrong for twenty.

The equivalence is the rule, and it is testable: a cluster added in the tab and the same cluster
declared in values must produce the same rows, the same polling and the same page. The tab is the
convenience; the file is the record. Neither is the privileged one, and a mode declared in one is the
same mode in the others — `saTokenLookup` on a values stanza and `saTokenLookup` in a Secret's
`config` connect by the identical path.

What differs is only **where the credential comes from**, and that is §3's job.

## 3. The two connection modes

| key on the stanza | what the dashboard does | what it stores |
|---|---|---|
| **`saTokenLookup: true`** | authenticates to the TARGET cluster as the bootstrap account, reads the poller ServiceAccount's token **and its `ca.crt`** from the declared token Secret the operator chart ships (`group-sync-operator-helm-chart` `55c17bc`), and writes them into a labelled cluster Secret in its own namespace | a cluster Secret whose `config` holds `bearerToken` and `tlsClientConfig.caData`, annotated `token-source: lookup` with the source cluster, namespace, ServiceAccount, minted-at and minted-by |
| **`userSelfLogin: true`** | polls as the bootstrap account itself, re-authenticating daily | nothing at rest; the token lives in memory only |

The two are mutually exclusive, and **neither is implied by silence**: a stanza with no credential and
no mode keeps today's refusal, with today's message. Inferring "they must have meant a lookup" would
turn a typo into an outbound login attempt with a fleet credential — so the mode is always declared.

`userSelfLogin` ships with the operator's own objection recorded beside it: *a token that disappears
mid-flight takes a running report or a browsing user with it.* It is for a cluster where no
ServiceAccount can be provisioned.

**Where `saTokenLookup` finds no declared token Secret**, it mints one with the TokenRequest API
(#238) — `create serviceaccounts/<name>/token`, `resourceNames`-pinned — and annotates
`token-source: minted` with the real `expirationTimestamp`. Measured on the lab: both grants exist
and are each pinned to that one ServiceAccount (`create serviceaccounts/default/token → no`).

### 3.1 The bootstrap account — configured once, overridden per cluster

`ldapConnectionBootstrap` names **which** account performs the login above. It is optional, and the
chart carries the default so a stanza normally names nothing:

```yaml
clusterConfig:
  fleetAccount:
    # The LDAP account the dashboard logs in AS when connecting a cluster that declares a mode.
    # One account for the fleet; a stanza overrides it with ldapConnectionBootstrap.
    username: ""
    # Its password. Never a literal in values — a Secret reference, read at connect time only.
    passwordSecret:
      name: gsd-fleet-account
      key: password
```

Rules, in the order they are checked:

1. A stanza's `ldapConnectionBootstrap` wins over the chart's `fleetAccount.username`.
2. `ldapConnectionBootstrap` without a mode is refused — it configures a login that would never happen.
3. Where neither names a username, or the password Secret is unreadable, the cluster is a **finding**
   (`fleet-credential-missing`, naming the Secret and the key) and not a crashed pod.
4. The username appears in logs and on the tab; the password appears nowhere — not the database, not a
   log line, not a response, not `/metrics` (the redaction pin covers it).

## 4. What the loader and the parser must change

Three keys are new on a cluster: `saTokenLookup`, `userSelfLogin`, `ldapConnectionBootstrap`. Both
readers learn them, because §2's equivalence is only real if both accept the same declaration.

**The values loader** (`local-development/gsd/config.py`):

1. Add the three keys to the known set — today an unknown key is refused by name, so a stanza carrying
   them crashes the pod before anything else can be discussed.
2. A stanza declaring a mode **may omit** `tokenFile` and `tokenEnv`; one declaring neither mode keeps
   today's requirement, with today's message, unchanged.
3. Declaring **both** modes is refused; declaring a mode **and** a credential is refused — two sources
   of truth, and the operator meant one of them.
4. A mode is refused on the **controller** stanza: it is this pod's own cluster and authenticates with
   the mounted ServiceAccount, so there is nothing to connect. Refused by name, the way a second
   `dashboard_controller` is.
5. `ldapConnectionBootstrap` without a mode is refused (§3.1 rule 2), and its value is validated as a
   username, not accepted as free text.
6. Every refusal above names the offending cluster and the key. A pod that will not start must say
   which line of which file to fix.

**The Secret parser** (`local-development/gsd/clusterconfig/parser.py`) takes the same three keys in
`config`, with one rule of its own: a Secret carrying `bearerToken` *and* a mode is a **finding**, not
a crash — the same "two sources of truth" refusal, delivered the way a Secret's problems are always
delivered, on the tab, with the other clusters still polling.

**What does not change:** a stanza or Secret that names a credential behaves exactly as it does today.
Nothing here alters an existing configuration, and the acceptance run in §7 pins that.

### 4.1 The stanza will keep growing — the discipline that keeps it trackable

The operator's reason for preferring it (2026-09-20): *"i feel like it is easy to track this stanza and
as we build more cluster — we will keep adding more stuff."* That is right, and it is a commitment: the
stanza is the estate's record, it grows a key at a time, and every key must be as reviewable as the
first. Three rules hold it together.

**An unknown key stays a refusal.** It is tempting to ignore keys the loader does not know so old
dashboards tolerate new files. That would make `saTokenLookupp: true` a silent no-op — the cluster
would sit there unconnected with nothing to read. A refusal that names the key and the cluster is what
makes a typo a thirty-second fix, and it is the property the operator is calling "easy to track".

**A key is added in three places at once** — the loader's known set (`gsd/config.py`), the parser's
accepted set (`gsd/clusterconfig/parser.py`) and the documented block in
`charts/group-sync-dashboard/values.yaml`. S3a adds a guard that fails when the first two disagree, so
§2's equivalence cannot rot: a key that works in a values stanza but is refused in a Secret is a
divergence the suite catches on the commit that introduces it, not on the cluster six weeks later.

**A new key defaults to today's behaviour.** Every addition is inert until declared — an existing
values file keeps rendering, an existing release keeps polling, and upgrading is never a migration.
That is what lets the stanza absorb the next ten ideas without any of them being a breaking change.

## 5. The onboarding sequence, and where each step can fail

```
resolve the fleet credential  →  discover the target's OAuth endpoint  →  log in
      → read (or mint) the ServiceAccount token + ca.crt  →  write the cluster Secret
      → discovery picks it up  →  the cluster polls like any other
```

| step | failure | what the operator sees |
|---|---|---|
| resolve the credential | no credential Secret, or `passwordFrom` unreadable | `fleet-credential-missing`, naming the Secret and the key |
| discover the OAuth endpoint | `/.well-known/oauth-authorization-server` unreachable | `oauth-discovery-failed`, naming the API URL |
| **trust the OAuth endpoint** | **the route is served by the INGRESS certificate, not the API server's** | `oauth-trust-failed` — see §5 |
| log in | wrong uid, wrong password, or the IdP's filter does not admit the account | `login-refused`, quoting the OAuth server's own error and naming the uid in force |
| read the token Secret | the Secret is absent, or the fleet account lacks `get` on it | `sa-token-unreadable`, naming the Secret and the namespace |
| write the cluster Secret | the tab's writes are off, or the name is taken | `writes-disabled` / `secret-exists`, naming the switch or the Secret |

Every one is a finding on the Cluster Configurations tab and a `phase=`-tagged line in the log
(#245's vocabulary: `phase=credential|oauth|login|lookup|write`), never a crash.

## 6. The measured trap this spec exists to record

The OAuth endpoint is **not** covered by the cluster's API CA. Measured from inside the pod on the
reference cluster (2026-09-21):

```
https://oauth-openshift.apps-crc.testing/healthz   with the pod's trust store → 000, verify=19
                                                    insecure                   → 200
```

`verify=19` is *self-signed certificate in certificate chain*: the route is served by the **ingress**
certificate while `caData` from the ServiceAccount token Secret is the **API server's** CA. A design
that reuses the cluster's `caData` for the login step will fail on every cluster whose ingress
certificate is not publicly trusted — which is most of them.

So the login step has its **own** trust setting, with the same three modes as the cluster's:
`oauthTrust: bundle | caData | insecure`, defaulting to the dashboard's own trusted bundle (an
enterprise ingress CA usually is in it, while the API's CA usually is not). The two are independent
and both are shown on the tab.

## 7. Testing it — and why the reference cluster can test it honestly

The lab has one cluster, so a "remote" must be made rather than found. The controller's **public
endpoint** is a legitimate remote for this purpose: `dashboard` reaches the API in-cluster at
`https://kubernetes.default.svc` with the mounted ServiceAccount, while `shared-rnd` reaches the same
API at `https://api.crc.testing:6443` as an outside caller — a different URL, a different credential,
a different trust path, and a different row in every table.

It is a genuine test of the **connection path**: discovery, the fleet login, the token lookup, the CA,
and every read working against a non-in-cluster URL. It is **not** a test of cross-cluster *data*
semantics — D2's `visibility`/`identity` narrowing against a cluster whose identities differ — and the
spec says so rather than letting the green result imply more than it proves. That half is the mock
rig's job (`local-development/mock-app/deploy/tls-modes/`).

**The acceptance run**, on the reference cluster, with the values above:

1. `shared-rnd` appears with `source: values`, `saTokenLookup: true`, and **no credential in
   the stanza**.
2. The log shows the sequence at `phase=credential → oauth → login → lookup → write`, one line each,
   with the bootstrap username named and **no secret in any line** (the redaction pin covers it).
3. A labelled Secret `gsd-cluster-shared-rnd` exists, annotated `token-source: lookup` with the source
   ServiceAccount, and its `config` carries `bearerToken` and `tlsClientConfig.caData`.
4. The cluster polls `ok`, and reads what the reference cluster reads: 3 GroupSync CRs, 62 groups, 6
   NCO configs, 115 Kyverno reports, 201 login attempts.
5. Its rows are its own: `sync_event` for `shared-rnd` is independent of the controller's, because
   capture is keyed by the configured **name** — two entries are two clusters whatever endpoint they
   answer at, and nothing is merged or de-duplicated.
6. Deleting the stanza retires the cluster and it disappears from the UI (#96), keeping its history.
7. **The equivalence holds** (§2): the same cluster removed from values and re-added from the tab — and
   again as a hand-applied labelled Secret — polls identically and renders identically. Only `source`
   differs, and that is the one field allowed to differ.
8. **A second cluster costs one stanza.** Adding `shared-qa` beside `shared-rnd` is four lines and no
   new switch, no GUI step and no hand-made Secret — the test that the file scales to an estate.

## 8. Decomposition

- **S3a** — the loader AND the parser: the three keys in both, `clusterConfig.fleetAccount` in the
  chart, the relaxed credential requirement, the six refusals, the equivalence guard (§4.1) and the
  `fleet-credential-missing` finding. No network.
- **S3b** — the onboarding sequence and its findings, behind #119 P2's provider; `oauthTrust` and its
  three modes; the annotations on the written Secret.
- **S3c** — the tab: the mode per cluster, the credential's provenance, the token's source and
  expiry wording (`expires: current` for a declared Secret, a real date for a minted one — #248), and
  a **Connect** action for a stanza waiting on its credential.

Each its own PR, each its own three-seat review, each walked on the reference cluster.
