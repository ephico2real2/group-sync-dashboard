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
    dashboardController: true

  - name: shared-rnd                      # a REMOTE cluster, named, with no credential
    apiUrl: https://api.crc.testing:6443
    saTokenLookup: true                   # obtain the credential; do not expect one here
    caBundleFile: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt   # the BOOTSTRAP trust (§6): no caData exists before the first login
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
| **`userSelfLogin: true`** | polls as the bootstrap account itself, re-authenticating when its OAuth session expires (§3.2 — the TARGET cluster's lifetime, not a figure we choose) | nothing at rest; the token lives in memory only |

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
    username: ocp-oauth-bind-serviceid
    # Its password. Never a literal in values — a Secret reference, read at connect time only.
    passwordSecret:
      namespace: openshift-config        # optional; defaults to the release namespace
      name: ldap-oauth-bind-secret
      key: bindPassword
```

**Named explicitly, never discovered from the OAuth CR** (the operator's ruling, 2026-09-21). The
account and its Secret could in principle be read off `oauth/cluster` — the cluster's LDAP identity
provider already names a `bindDN` and a `bindPassword` Secret. This spec deliberately does not, for
three reasons:

1. It would need `get` on `oauth/cluster`, a **cluster-scoped** read of the cluster's identity
   configuration, to learn one username.
2. It would couple S3b to the OAuth CR's shape — a second identity provider, a non-LDAP provider, or
   a schema change breaks a connector that has nothing to do with authentication config.
3. It would only ever work where the fleet account **is** the IDP's bind account. Naming it in values
   lets an estate use a different account, which is the normal case.

That the two happen to coincide on the reference cluster is a convenience, not a mechanism.

#### `passwordSecret.namespace` — a cross-namespace read, and what it costs

`namespace` is optional and defaults to the release namespace. Setting it — as the reference
configuration does, to `openshift-config` — moves the read outside the namespace boundary the rest of
this design is built on, and that is not free:

- `templates/cluster-secrets-rbac.yaml` is deliberately **a Role, not a ClusterRole**, because
  "`secrets` cluster-wide would hand the dashboard every credential on the cluster". A Secret in
  another namespace needs its own Role **there**, scoped with `resourceNames` to that one Secret, and
  a RoleBinding for the dashboard's ServiceAccount.
- The dashboard's chart installs into its own namespace. Creating a RoleBinding in `openshift-config`
  means either the chart writes into a namespace it does not own — which many clusters refuse, and
  which is a privilege-escalation surface — or that grant is applied separately and the chart
  **refuses to start the mode** until it is present, reporting `fleet-credential-missing` naming the
  namespace, the Secret and the key.

Measured on the reference cluster, 2026-09-21: `ldap-oauth-bind-secret` exists in `openshift-config`
with key `bindPassword`, and the dashboard's ServiceAccount **cannot read it** (`oc auth can-i get
secrets/ldap-oauth-bind-secret -n openshift-config` → `no`). The group-sync-operator chart
establishes the pattern to copy — a dedicated `oauth-secret-extractor` ServiceAccount with a Role in
`openshift-config` scoped by `resourceNames` to a single Secret — but that grant is for the
operator's consumer, not this one.

#### Whichever account is named, it must be able to LOG IN

Independent of where the password lives: §3's modes obtain a **token from the target cluster's OAuth
server**, so the named account has to be one that provider will authenticate. On the reference
cluster the IDP's user search is

```
…/dc=ephico2real,dc=com?uid?sub?(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,ou=Groups,dc=ephico2real,dc=com))
```

so an account authenticates only if it carries a `uid` **and** is a member of that group. A directory
*bind* identity — `cn=…,ou=TrustedApplications`, an RDN of `cn=`, in a service OU — typically
satisfies neither: it can bind to the directory so the OAuth server may search it, which is a
different capability from being findable as a user.

**This is checkable by a directory read and must not be checked by attempting the login.** A lockout
policy would lock the account the cluster's OAuth uses to authenticate *every* user, so the
verification is `ldapsearch -s base uid memberOf` against the entry, not a login attempt. If the named
account turns out not to be loginable, the answer is to name one that is — not to widen the filter.

Rules, in the order they are checked:

1. A stanza's `ldapConnectionBootstrap` wins over the chart's `fleetAccount.username`.
2. `ldapConnectionBootstrap` without a mode is refused — it configures a login that would never happen.
3. Where neither names a username, or the password Secret is unreadable, the cluster is a **finding**
   (`fleet-credential-missing`, naming the Secret and the key) and not a crashed pod.
4. The username appears in logs and on the tab; the password appears nowhere — not the database, not a
   log line, not a response, not `/metrics` (the redaction pin covers it). It is not a field of
   `ClusterConfig`, so `poller._credentials()` — the list the emit helper redacts against — does not hold
   it: the connector passes it as a `secrets=` value at every call site of the new phases, and the
   redaction pin is extended to drive a failure in each of them with the password in force.

### 3.2 The login session's lifetime belongs to the target cluster

An OpenShift login session is **24 hours by default, and the target cluster may have changed it.** The
knob is `oauth/cluster` `.spec.tokenConfig.accessTokenMaxAgeSeconds`; the default when unset (or set to
`0`) is `86400`. So a `userSelfLogin` credential does not live for "a day" — it lives for however long
*that* cluster says, and the dashboard must **read the value rather than assume it**.

This is not hypothetical. Measured on the reference cluster (2026-09-21):

```
$ oc get oauth cluster -o jsonpath='{.spec.tokenConfig}'
{"accessTokenMaxAgeSeconds":31536000}
$ oc get oauthaccesstokens -o jsonpath='{.items[0].expiresIn}'
31536000
```

**One year**, on live tokens — 365 times the default. **That is CRC's own doing, not an estate
setting**, and the evidence is the object's content, not its timestamp. `oauth/cluster` is created by the
cluster-version operator (`release.openshift.io/create-only: "true"`, owner `ClusterVersion`) at
`11:45:58Z`; the creation time dates the object the CVO made, not the value, and the object stands at
`generation: 3` — the spec changed twice after that moment. The value arrived by `oc apply`: its `kubectl.kubernetes.io/last-applied-configuration`
annotation holds exactly `tokenConfig.accessTokenMaxAgeSeconds: 31536000` beside the `developer`
HTPasswd provider — which is, key for key, `oauth_cr.yaml` in CRC's bundle builder (`crc-org/snc`:
*"token max age set to 365 days"*), applied by `snc.sh` after `wait-for install-complete` when the
bundle is made. So it is bundled, and it was applied *after* the install completed at `12:12:11Z`, not
before. A developer VM avoiding a daily re-login is a sensible default for a developer VM; it just makes
this lab unrepresentative of every cluster the dashboard will actually connect to.

**A fixed daily refresh is not wrong; it is just not derived.** The session lifetime is an **upper
bound**, so re-authenticating more often than required is safe — on this cluster a daily refresh is
simply 364 days earlier than it needs to be, which costs a login and nothing else. It fails in exactly
one direction: a target that has shortened its session **below** 24 hours, where the daily refresh
arrives after the credential has already died and every poll in between has failed. Reading the target's
value buys two things a fixed figure cannot — correctness on a short-session cluster, and the ability to
refresh at a *fraction* of the real lifetime rather than at a guess.

Three consequences follow:

1. **Renewal tracks the shorter of the two clocks.** A looked-up ServiceAccount token has its own TTL
   (§8.3); a `userSelfLogin` session has this one. Whichever expires first decides when the dashboard
   must act, and the tab shows the real date for each rather than a nominal "daily".
2. **The reference cluster cannot test *session* expiry; it can test token expiry.** §7's acceptance
   run proves the *connection path*. It cannot prove a `userSelfLogin` renewal, because a session here
   lives a year and shortening it means editing `oauth/cluster` for the whole cluster. A **minted** token
   is the other clock (§8.3), and that one the lab *can* run down: the TokenRequest API takes an
   `expirationSeconds` as low as 600 — the API server's floor — so a token that dies in ten minutes is one
   request away and needs no cluster-wide change. Saying a green run here demonstrates *session* renewal
   would be claiming a result the lab is incapable of producing; token renewal is demonstrated here, with
   a short-lived mint, and the spec prefers that proof for exactly that reason.
3. **Report the real lifetime, without editorialising.** The tab shows each cluster's actual
   `accessTokenMaxAgeSeconds` rather than a nominal figure — for the same reason #248 writes
   `expires: current` rather than `never`: the number a reviewer needs is the real one. This is
   reporting, not a judgement. A long session on a developer VM is a reasonable default; the same
   number on a production cluster is a conversation for whoever owns that cluster, and the dashboard's
   job is to make it visible, not to grade it.

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
   `dashboardController` is.
5. `ldapConnectionBootstrap` without a mode is refused (§3.1 rule 2), and its value is validated as a
   username, not accepted as free text.
6. Every refusal above names the offending cluster and the key. A pod that will not start must say
   which line of which file to fix.

**The Secret parser** (`local-development/gsd/clusterconfig/parser.py`) takes the same three keys in
`config`, with one rule of its own: a Secret carrying `bearerToken` *and* a mode is a **finding**, not
a crash — the same "two sources of truth" refusal, delivered the way a Secret's problems are always
delivered, on the tab, with the other clusters still polling. A key it does not know is refused today
**without being named** — the detail says "config has a 13-character key this contract does not
define … in case something other than a key name was written into it" — so each new key must also
join `_ECHOABLE_KEYS` (parser.py), or the operator is told the length of their mistake and not its
name. That is the mechanism, and it is worth saying exactly: an earlier draft of this spec said the
key would be "refused by name, the way `dashboardController` is", which was only true *because* #249
added that key to the echoable set. The naming is not automatic.

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

### 4.2 The loader is not the last refusal — the poll path refuses too

A relaxation that stops at `load_settings` produces a cluster that starts, appears, and then fails
**every poll for ever**. Driven end to end against a patched copy of the package, the sequence is:

```
credential_kind of a credential-less stanza   → "file"          (the fall-through, config.py)
ClusterConfig.resolve_token()                 → ConfigError: neither tokenFile nor tokenEnv configured
ClusterClient._client()                       → ClusterError(outcome="auth_failed")
the poller's line                             → cluster-unreachable phase=credential outcome=auth_failed
                                                cluster=shared-rnd source=values credential=file
```

Three things are wrong there and all three are S3a's work:

1. **`credential_kind` must gain a word for this state.** It falls through to `file`, so a cluster
   that has no file is reported as having one. The precedent is already in the code: `oauth` exists
   as a kind that *cannot be resolved yet* (#119 P2), paired with the finding
   `oauth-exchange-not-built`. A looked-up credential follows that pattern, not a new invention.
2. **`resolve_token()` must not be reached before the credential exists.** A cluster awaiting its
   first lookup is not a broken cluster; it is an unfinished connection, and the reconciler (§8) is
   what finishes it.
3. **The outcome must not be `auth_failed`.** Nothing authenticated and nothing was refused —
   reporting a failed authentication for a credential that was never presented sends the operator
   to rotate a token that does not exist. It is a distinct state with its own action line.

**What does not change:** a stanza or Secret that names a credential behaves exactly as it does today.
Nothing here alters an existing configuration, and the acceptance run in §7 pins that.

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
(#245's vocabulary), never a crash — **and none of those ids exists yet.** The review of this spec
constructed all seven and every one raised `ValueError: unknown finding code`: `Finding.__post_init__`
(`gsd/clusterconfig/parser.py`) enforces a **closed set** of nineteen codes, and SPEC_S1 §S1.2 makes
that set a page contract — *"the tab renders each with its own sentence, so a new code is a page
change too"*. The same is true of the phases: `phase=` today takes `discovery|parse|credential|tls|
connect|poll`, so `oauth`, `login`, `lookup` and `write` are new phases, not existing ones.

That is a real cost this spec must schedule rather than assume, and it splits three ways:

1. **Reuse where a code already means the right thing.** `credential-missing` and
   `oauth-exchange-not-built` already exist and already say what two of these rows say. A new id for
   an existing meaning is the divergence §4.1 exists to prevent — the same mistake §8.2 made with
   `shadows-values-entry` and had to retract.
2. **Add the genuinely new codes to the closed set AND to the page**, in the same PR, because the
   contract says they travel together. S3b owns that, and its Definition of Done names the page
   change explicitly.
3. **Add the new phases to the logging vocabulary** (#245) where the sequence genuinely has steps the
   existing six do not cover.

Until that lands, an implementer copying this table verbatim gets a `ValueError` at the first
failure — which is the loudest possible reminder, and better than a silent one, but it is the
spec's job to say so first.

### 5.1 The Secret the lookup writes — the artefact, and what reads each field

**Build state, measured on `main` at chart 0.48.0 (2026-09-21).** Say this first, because the stanza
below reads like working configuration and is not yet:

| piece | state |
|---|---|
| the three stanza keys, in both readers | **ships** (S3a) — recorded, refused six ways, equivalence-guarded |
| a mode cluster is listed and **not polled** | **ships** — `credential_pending`, `poller.py`'s gate |
| `gsd-cluster-<name>` Secret writer | **ships** (#230 S2) — `SECRET_NAME_PREFIX` in `gsd/clusterconfig/writer.py` |
| `clusterConfig.fleetAccount.username` in the chart | **ships** (S3a) |
| **logging in as the bootstrap account and reading the token** | **NOT BUILT** — S3b |
| **the provenance annotations below** | **NOT BUILT** — S3b; nothing writes or reads them today |

`saTokenLookup` appears in exactly two files (`gsd/config.py`, `gsd/clusterconfig/parser.py`), and
both only *record* the declaration. No code in the tree performs a login, an exchange or a
TokenRequest. A hand-made Secret of the shape below is therefore consumed normally — the parser
accepts its `config`, and the annotations are inert metadata — but nothing produced it and nothing
will refresh it.

#### The stanza

```yaml
  - name: shared-rnd
    apiUrl: https://api.shared-rnd.example.com:6443
    saTokenLookup: true
    ldapConnectionBootstrap: svc.gsd.fleet      # optional; overrides clusterConfig.fleetAccount.username
    enabled: true
```

#### What S3b does with it

1. Log in to `apiUrl` as **`svc.gsd.fleet`** — the bootstrap account of §3.1, a *person-shaped*
   account the target cluster's own identity provider authenticates. It is named here, per cluster,
   only to override the fleet default.
2. Read the **poller ServiceAccount's** token on that cluster. The bootstrap account's own session is
   never the polling credential: an OpenShift login session is short-lived by design (§3.2 — the
   cluster's `accessTokenMaxAgeSeconds`, 24 h by default), while the SA token is the long-lived
   credential the poll needs.
3. Write it to **`gsd-cluster-<name>`** in the release namespace — `gsd-cluster-shared-rnd` for the
   stanza above — in the labelled-Secret shape SPEC_S1 already defines, so the ordinary discovery path
   picks it up on the next cycle with no restart.

#### The Secret, with a placeholder credential

```yaml
kind: Secret
apiVersion: v1
metadata:
  name: gsd-cluster-shared-rnd                        # gsd-cluster-<name>, from the stanza
  namespace: group-sync-dashboard                     # the release namespace; a Secret elsewhere is refused
  labels:
    groupsync-dashboard.io/secret-type: cluster       # REQUIRED — what discovery selects on
    environment: rnd                                  # the fleet's own labels ride along, shown on the tab
  annotations:
    groupsync-dashboard.io/token-source: lookup            # how the credential was obtained
    groupsync-dashboard.io/source-namespace: group-sync-operator
    groupsync-dashboard.io/source-service-account: group-sync-dashboard-cluster-poller
stringData:
  name: shared-rnd                                    # must equal the stanza's `name`
  server: https://api.shared-rnd.example.com:6443
  enabled: "true"
  visibility: inherit
  identity: same-as-host
  config: |
    {"bearerToken":"<the poller SA's token — never in git, never in a manifest>",
     "tlsClientConfig":{"insecure":false,"caData":"<the target's CA chain, base64 PEM>"}}
type: Opaque
```

#### What reads each field

`name`, `server`, `enabled`, `visibility`, `identity` and `config` are SPEC_S1's contract and are
parsed today. `config.bearerToken` gives `credential_kind: bearer`, which clears
`credential_pending`, so **writing this Secret is what makes the cluster start polling** — the stanza
alone never does.

The three annotations are **new with S3b and are provenance, not configuration**. They answer, on the
Cluster Configurations tab and in a support ticket, the question a bearer token cannot: *where did
this come from, and what do I rotate?*

- `token-source: lookup` — distinguishes a token the dashboard fetched from one a human pasted. A
  hand-made Secret omits it, and S3d must not treat an unannotated Secret as its own to refresh or
  delete (§8.1: only what we made).
- `source-namespace` / `source-service-account` — **the rotation address.** A bearer token is opaque;
  without these, "rotate this credential" has no answer but "find whoever created it". With them the
  next lookup knows exactly which SA on which cluster to read again.

Today's writer sets a different annotation — `groupsync-dashboard.io/managed-by: ui` (#230 S2) — for a
Secret a person created through the form. The two are orthogonal: `managed-by` says *who* created it,
`token-source` says *how the credential was obtained*. S3b writes both.

#### Measured on the reference cluster (2026-09-21)

`gsd-cluster-shared-rnd` exists on the lab today, hand-made as a faithful mock of what S3b will
write. Read back from the API server (the credential not shown):

```
labels      {"environment": "rnd", "groupsync-dashboard.io/secret-type": "cluster"}
annotations groupsync-dashboard.io/token-source: lookup
            groupsync-dashboard.io/source-namespace: group-sync-operator
            groupsync-dashboard.io/source-service-account: group-sync-dashboard-cluster-poller
data        name=shared-rnd  server=https://api.crc.testing:6443  enabled=true
            visibility=inherit  identity=same-as-host
            config: bearerToken=<1377 chars>  tlsClientConfig{insecure:false, caData=<9612 chars>}
```

`server` is **CRC's own API** — the controller's public endpoint, which is §7's point: the reference
cluster can test this honestly without a second cluster, because what is exercised is the
*destination shape*, not the network hop.

**Why it polls, precisely.** Measured on the deployed ConfigMap, the lab's `clusters.yaml` contains
**one entry — `dashboard`**, the host with its mounted ServiceAccount token. There is no `shared-rnd`
stanza at all, so nothing is being shadowed: the Secret is that cluster's whole definition.
`/api/clusterconfigs` reports it as

```
shared-rnd   source=secret:gsd-cluster-shared-rnd   credential=bearer   enabled=True
```

— the SPEC_S1 path (#230), which ships. `config.bearerToken` resolves, so `credential_pending` is
`None` and the poller treats it like any other cluster. **`saTokenLookup` is not involved**, because
no stanza on this lab declares it.

That is the distinction the whole of S3 rests on, and it is easy to lose:

| | state |
|---|---|
| **consuming** a Secret that already holds a token, over the remote API | **ships** — this is what the lab demonstrates |
| **acquiring** that token — log in as the bootstrap account, read the poller SA's token, write the Secret | **not built** (S3b) |

The token reached that Secret by hand: its `kubectl.kubernetes.io/last-applied-configuration`
annotation is a manifest carrying `stringData.config`. S3b is the step that would fetch it, write it
and (with S3d) refresh it.

**The remote path is genuinely exercised.** `server` is `https://api.crc.testing:6443` — the
front-end OpenShift API, not `kubernetes.default.svc` — so the request leaves by the same route an
external cluster's would: a different endpoint, a real 9 612-character CA chain, and a bearer token
belonging to a ServiceAccount in another namespace, authenticated by the API server exactly as a
remote cluster's would be. The three `mock-*` clusters on the lab are configured the same way. This
is §7's point: the reference cluster tests the destination shape honestly without a second cluster.

> **A correction to an earlier record.** The #269 walk
> (`reports/2026-09-21_report-form-clusters/README.md`, and the evidence comment on #267) expected
> `shared-rnd` to fail its run as "the credential-less cluster of SPEC_S3" and, when it sealed like
> the rest, attributed that to "it has a snapshot on this lab". The observation was right and **the
> stated reason was wrong**: this Secret is why. `shared-rnd` is not credential-less on the reference
> cluster and has not been since the Secret was applied. The conclusion that partial failure remains
> covered only by the API test and the browser test's injected `ghost` still holds — it holds for a
> different reason.

#### Why the token is not in the stanza

The stanza declares the *mode*; the Secret carries the *credential*. That split is the point of S3:
values files live in git, and a bearer token must not. The loader refuses a mode beside
`tokenEnv`/`tokenFile` for the same reason — two sources of truth for one credential (§4).

#### What must be true before S3b can run — and the dependency nobody wrote down

S3b writes a Secret, so it needs the **write** grant, not just the read one. That grant is
`clusterConfig.secrets.writes.enabled`, which is **off by default** and which `values.yaml` describes
as *"the decision to let the dashboard mint cluster access"* — which is exactly what the retriever
does. The `clusterConfig.fleetAccount` block sits directly beside it and **nothing connects the
two**: an operator can set `fleetAccount.username`, apply a mode stanza, and find the lookup has
nowhere to put its result.

Measured from the chart: `templates/cluster-secrets-rbac.yaml` grants
`get, list, watch` normally and adds `create, update, delete` **only** under
`clusterConfig.secrets.writes.enabled`. So:

| precondition | why | on the reference lab, 2026-09-21 |
|---|---|---|
| `clusterConfig.secrets.enabled` | discovery reads the labelled Secrets | **on** (default) |
| `clusterConfig.secrets.writes.enabled` | **the retriever cannot persist its token without `create`** | **on** — the Role carries `create, update, delete` |
| `fleetAccount.username`, or `ldapConnectionBootstrap` per stanza | the account to log in AS | **absent** — username is empty, so the chart renders nothing |
| the `gsd-fleet-account` Secret (`passwordSecret`) | its password, read at connect time only; **the chart does not create it** | **NotFound** |
| a stanza or Secret `config` declaring a mode | what triggers the lookup at all | **none** |

Nothing on the lab exercises the lookup, and the state above is why — independently of S3b being
unbuilt. That is worth recording: a reader who sees `shared-rnd` polling could reasonably conclude
the mode works, and none of these five is satisfied.

**Two things this implies for S3b's PR.**

1. **The dependency must be stated where the operator reads it.** `fleetAccount`'s own comment says
   S3b "reads it at connect time and nowhere else" — true, and incomplete: without
   `secrets.writes.enabled` the connect succeeds and the *write* fails. Either the chart refuses the
   combination at render (a mode stanza with writes off), or the tab says it plainly. A render-time
   refusal is this chart's habit — it already refuses a mode beside a credential, and a mode on the
   host.
2. **`writes.enabled` now gates two different decisions.** Today it means "a person may add a cluster
   from the tab". With S3b it also means "the dashboard may mint cluster access unattended", which is
   a larger grant of trust and is the thing the values comment was already circling. Whether those
   stay one switch or become two is an operator decision, and it belongs in S3b's review rather than
   being settled by whichever lands first.

#### The consumption path is ready for this Secret — with one gap S3d inherits

Reviewed against the Argo CD design it borrows from (2026-09-21). **A retriever writing the shape
above is consumed as-is**: `parse_secret` reads `metadata.name` and the `data` keys, and **ignores
annotations entirely**, so the provenance keys pass through untouched.

The borrowed design is followed where it is right and departed from where it is not, each departure
already reasoned in the code:

| | |
|---|---|
| label selector `groupsync-dashboard.io/secret-type=cluster`, server-side, release namespace only | Argo's model |
| Argo's scope keys (`namespaces`, `clusterResources`, `project`, `shard`) **refused by name** | a Secret copied from Argo with `namespaces: team-a` would be read as a FULL cluster — the opposite of what its author declared |
| the host is **never** sourced from a Secret | the host authenticates the reader; a Secret must not replace it |
| a duplicate cluster name loads **neither** Secret | Argo's first-by-name would let `aaa-anything` replace a real cluster's server and token, invisibly, for anyone who may create a Secret here |
| a shadowed values entry is a finding, not silence | the Secret wins, and the tab says so |

**The gap: the ownership marker is written and never read.** `writer.py` sets
`groupsync-dashboard.io/managed-by: ui`, the tab's YAML pane renders it, and the tab's own text warns
that a namespace policy "will still delete a UI-written Secret unless it honours" it — but no code
reads it back, because the parser ignores annotations.

That costs nothing today: nothing acts on ownership. It stops being free at **S3d**, whose §8.1 rule
is *only what we made* and which is **the only step that deletes**. Two consequences to settle before
that loop is written, not while writing it:

1. **The markers need a reader and a contract.** `token-source`, `source-namespace` and
   `source-service-account` are the rotation address and the ownership proof. If S3b writes one wrong
   — or a human hand-edits it — nothing notices today, and S3d would take a deleting decision on
   unvalidated input. Parsing them into `ClusterConfig` (ignored by the poll, surfaced on the tab)
   turns them from prose into a contract with one place to validate.
2. **`managed-by` and `token-source` answer different questions** and both are needed: *who created
   this* (`ui`, or the retriever) and *how the credential was obtained* (`lookup`, or pasted). A
   Secret carrying neither is a human's, and S3d must stand down on it — which is only enforceable
   once something reads them.

#### What still has to be decided in S3b

- **The lookup's own RBAC.** Reading another SA's token is `get` on that Secret, or a TokenRequest
  `create` on the SA. §8.3 prefers TokenRequest (bounded lifetime, the 80 % renewal trigger); a legacy
  SA-token Secret never expires and is invalidated only by deleting it, which is why the tab words it
  `expires: current` (#248) rather than `never`.
- **Failure vocabulary.** Every finding this adds joins the closed set *and* the page in the same PR
  (SPEC_S1 §S1.2), and every new `phase=` joins #245's set.

## 6. The measured trap this spec exists to record

**This section was wrong in the first draft and is corrected here.** The number was right; the cause
assigned to it was the opposite of what the cluster does, and the default derived from that cause was
the one mode measured to fail. The review of this spec re-measured it from inside the deployed pod,
with `curl` *and* with Python's `ssl` — the machinery `ClusterConfig.verify()` actually builds — and
enumerated the bundles certificate by certificate.

What the pod measures (CRC 4.22.7, 2026-09-20), against the OAuth route **and** the external API URL:

| target | the dashboard's own trusted bundle | the ServiceAccount's `ca.crt` (`caData`) | insecure |
|---|---|---|---|
| `oauth-openshift.apps-crc.testing` | **FAIL** — `verify=19`, self-signed certificate in chain | **OK** | OK |
| `api.crc.testing:6443` (external) | **FAIL** — `verify=19` | **OK** | OK |

`verify=19` is real and reproduces exactly. What it is *not* is a statement about the OAuth route
being outside the API CA's reach. The ServiceAccount's `ca.crt` is a **bundle**, not "the API
server's CA", and on this cluster it carries six certificates — the four kube-apiserver signers
**and** `ingress-operator@…` with the `*.apps-crc.testing` leaf it issued. That is exactly why it
validates the login endpoint.

The thing that fails is the **dashboard's own injected trust store**
(`GSD_TRUSTED_CA_FILE`, 147 certificates, 225 713 bytes): the ingress CA is **not** in it
(`ingress-operator CA present in injected bundle: False`). It fails on the OAuth route and on the
external API URL alike, so this is not a login-step problem at all — it is what happens to *any*
outside-the-cluster connection made on the default trust.

So the corrected design:

- The login step still gets its **own** trust setting, `oauthTrust: bundle | caData | insecure` —
  a separate axis is right, because a cluster may serve its API and its routes from different CAs
  and nothing guarantees one bundle covers both.
- **It defaults to `caData`, not `bundle`.** `caData` is the mode measured to work on both endpoints,
  and it is the one the dashboard obtains for free: `saTokenLookup` already reads `ca.crt` beside
  the token (§3), so the material is in hand at exactly the moment the login needs it.
- `bundle` remains for the estate whose ingress CA really is in the corporate store, and the tab
  says which mode a cluster used — because "it worked here" is not evidence about the next cluster.

**Before the first lookup there is no `caData`, so `caData` cannot be the first connection's trust.** The
material `caData` names is the `ca.crt` beside the token, and it is read *after* the login (§5's fourth
step) — so on a cluster's first connection the OAuth discovery and the login run with no `caData` in
hand, and `oauthTrust: caData` has nothing to verify against. The stanza therefore carries the
**bootstrap trust** itself, the way every other stanza carries its trust: `caBundleFile` (or
`insecureSkipVerify`, said out loud), and where it names neither the dashboard's own bundle is used —
which on this cluster is the mode measured to fail (`ClusterConfig(name='shared-rnd', api_url=…).tls_mode`
→ `trusted-bundle`). §1's stanza names `caBundleFile` for that reason and §7's acceptance run needs it.
Once the derived Secret exists, its `tlsClientConfig.caData` takes over for the poll and for every
reconnection, and `caData` is then the default it says it is.

**The lesson worth keeping, since it is the one that generalises:** a reproduced number is not a
confirmed cause. `verify=19` was measured correctly and then explained by the first plausible story
— "routes are ingress-signed, `caData` is the API CA" — without opening the bundle to see what was
actually in it. One `openssl`-equivalent enumeration refuted it. Measure the mechanism, not only the
symptom.

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

## 8. Reconciliation — what makes this suit CI/CD

The operator, 2026-09-20: *"this is the way that argocd works now … we just have to make sure we find a
way to reconcile now. setting up cluster config this way suits cicd and also automation."*

A declared stanza that mints a Secret has created a **derived object**, and a derived object goes stale.
The declaration is the desired state; the Secret is the observed state; something has to keep them
equal. That something runs on the discovery cadence — the same 300 s loop that already lists cluster
Secrets — and it is **level-triggered**: it compares what is declared against what exists, every cycle,
with no memory of how it got there. Applying the same values file twice changes nothing; applying it to
a half-connected estate finishes the job. That is the property automation needs, and the reason a
crashed pod mid-connect is not a broken cluster.

Drawn as flow 5 of `docs/DESIGN_cluster_connection_flows.md`, in mermaid and in ASCII.

### 8.1 Ownership — only what we made, and it is bookkeeping, not authentication

Argo CD marks every resource it manages with an `argocd.argoproj.io/tracking-id` annotation — now its
default tracking method — and **only resources carrying the matching annotation are candidates for
pruning**, precisely so it never deletes something another tool made. The same rule here, with three
corrections the adversarial pass measured against the shipped code.

**The key already exists, and it already has a value.** S2's writer defines
`MANAGED_BY_ANNOTATION = "groupsync-dashboard.io/managed-by"` with `MANAGED_BY_UI = "ui"`
(`local-development/gsd/clusterconfig/writer.py`), and stamps it on every Secret the tab creates. So the
reconciler does **not** introduce a key; it adds a second **value** on the existing one, and the match
must be on the **exact value**, never on the key's presence:

```yaml
metadata:
  annotations:
    groupsync-dashboard.io/managed-by: reconciler        # DERIVED — written by the loop
    groupsync-dashboard.io/source-cluster: shared-rnd     # from this declaration
    groupsync-dashboard.io/token-source: lookup           # or: minted
```

A Secret stamped `ui` is a human's, made through the tab. A Secret with no annotation is a human's or a
GitOps process's. Only `reconciler` is ours.

**The marker does not survive parsing, so the loop must read the raw object.** `parse_secret` builds its
`ClusterConfig` from `metadata.labels` and the `data` keys; it never reads `metadata.annotations`
(`local-development/gsd/clusterconfig/parser.py`). A reconciler that asks a parsed cluster "are you
mine?" will always hear no. Ownership is decided on the **raw Secret** as listed, before parsing, and
S3d's first job is to carry that field through.

**The annotation is NOT authentication.** Anyone who can create a Secret in the release namespace can
write `managed-by: reconciler` on it — and that is S2's existing trust boundary, not a new one. Paired
with §8.2's deletion, a forged marker turns "remove a stanza" into "delete the object someone else
made". So deletion is guarded by more than the marker:

1. The Secret's `data.name` must equal the declared cluster the loop is retiring — the marker alone
   never authorises a delete.
2. The delete carries **UID and resourceVersion preconditions**. S2 deletes by name today
   (`writer.py`), so a replacement object created between the read and the delete would be destroyed by
   a check-then-delete race. The reconciler must not inherit that.
3. Anything that fails either check is a finding, never a delete.

Stated plainly because it is the part most easily lost: the annotation exists so the loop can recognise
its **own** work, and for nothing else. It is a bookkeeping mark on a namespace whose write access is
already the privilege boundary.

### 8.2 The transitions

| what changed | what the reconciler does |
|---|---|
| a stanza is **added** | connect (§5) and write the derived Secret |
| a stanza's **mode or bootstrap account** changes | reconnect and rewrite the Secret in place — the cluster keeps its name, its rows and its history |
| a stanza's **`apiUrl`** changes | reconnect, and expect it to be *reported* as a change: `_cluster_shape` (`gsd/poller.py`) includes `api_url` in what "this cluster changed" means, deliberately, so that repointing a cluster is visible. The cluster keeps its name, its rows and its history; the `changed=` line is correct and stays |
| a stanza is **removed** | the derived Secret is deleted (under §8.1's guards). Retirement itself needs no new code, but it is **two paths, and `retire_absent_clusters` is only the first**: at start, `Poller.start` calls `store.retire_absent_clusters` for every row the merged configuration no longer names (`gsd/poller.py`, `gsd/store.py`); at runtime, `_discover_once`'s vanish block disables the row of a Secret that left the LIST **only when no values entry carries that name**, and `_reconcile_threads` stops its thread. Both **keep the history**. A removed stanza rolls the pod, so the derived Secret is still present at the next start and nothing retires the row then; the loop deletes the object, and the runtime path retires the row on the cycle that sees it gone — it must not invent a second retirement |
| a derived Secret is **deleted by hand** | re-created next cycle from the declaration. The file is the record; deleting the output does not undeclare the cluster. **The existing vanish path does not retire this row**: `_discover_once` skips a vanished name that is still in `settings.clusters` (`if name not in {c.name for c in self.settings.clusters}`, `gsd/poller.py`) and `_reconcile_threads` never stops a values cluster's thread, so between the delete and the re-creation the merged view falls back to the credential-less stanza and the thread polls *that* — §4.2's pending state, measured. Nothing is deleted from the store, so the history survives; S3d renders the gap as pending, not as a failure and not as a retirement |
| a derived Secret is **edited by hand** | the declared fields are restored, and the edit is reported as drift on the tab — the same answer Argo gives, for the same reason |
| an **unowned** Secret names a declared cluster | today's rule stands, unchanged: **the Secret shadows the values entry and wins**, with the existing `shadows-values-entry` finding (`gsd/clusterconfig/reader.py`) and its existing action — *"edit the Secret, or delete it to fall back to the values entry"*. The reconciler **stands down**: it does not connect, does not overwrite and does not delete. A human's credential is in force and the tab says so |

The removal row is the one that earns the design. A cluster deleted from the file but left polling from
an orphaned Secret is the failure this project has already met once — a set-change that displaces objects
without pruning them leaves them running, and only a matching owner marker makes the cleanup safe.

**One consequence to design for:** `reader.py` emits `shadows-values-entry` for **every** Secret that shadows a values entry — including the derived Secret the loop itself wrote. Left alone, connecting a cluster would raise a finding against the connection working correctly. S3d must either exempt a Secret whose `managed-by` is `reconciler` and whose `data.name` matches the stanza that produced it, or render that case as the normal state rather than a finding. Deciding this is part of S3d, not an afterthought.

**A second consequence, and it is the write itself.** The derived Secret's `data.name` is the stanza's name by design, and `writer.validate` refuses exactly that: `taken` is every effective cluster *including the values entries*, so a reconciler that reuses `writer.create` is answered `duplicate-cluster-name` — measured on this head, `writer.validate(req, ns, host_name='dashboard', taken={'shared-rnd': 'values'})` raises *"shared-rnd is already declared by values"* with `conflict=True`. The refusal is right for a human POST (two authors of one name is a conflict) and wrong for the loop, whose whole purpose is to author the Secret *for* the values entry. S3d exempts only a values-sourced entry, and only the one the loop names, and leaves the human path refused; §7 item 7's equivalence run is what proves the exemption did not widen.

**Shadowing is not a conflict — it is the mechanism.** A Secret already wins over a values entry of the
same name (`gsd/config.py`, `gsd/clusterconfig/registry.py`: *a Secret shadows a values entry*), and that
is exactly how a lookup delivers its result: the stanza declares the intent, the derived Secret carries
the credential, and the merged view polls the Secret. The only case needing a new rule is the *unowned*
shadow in the last row, and the rule there is to leave it alone. This spec adds **no** new precedence and
**no** new finding code for it — `shadows-values-entry` already exists, and inventing a second id for one
situation is the divergence §4.1 exists to prevent.

### 8.3 Renewal — the way Kubernetes does it

The operator's requirement. A minted token carries a real `expirationTimestamp`, and the reconciler
remints it **before** it expires rather than after a poll fails. Kubernetes' own rule for a projected
service-account token is that the kubelet requests a new one once the token is older than **80 % of its TTL**
**or older than 24 hours** — whichever comes first. This reconciler takes **both** triggers, not just the first:
a long-lived token that is nowhere near 80 % of its life still gets a daily refresh, which is the half that keeps
a multi-day token honest. The tab shows the real date.

**But the 80 % rule only applies to a token that HAS a lifetime, and the path this spec prefers does
not.** The declared `kubernetes.io/service-account-token` Secret the operator chart ships carries a
**legacy, non-expiring** token. Measured on the reference cluster, decoding the JWT that
`group-sync-operator/group-sync-dashboard-cluster-poller-token` holds:

```
claims present: iss, sub,
                kubernetes.io/serviceaccount/{namespace, secret.name,
                                              service-account.name, service-account.uid}
iat = ABSENT      exp = ABSENT      nbf = ABSENT
iss = kubernetes/serviceaccount        (the legacy issuer, not the bound-token issuer)
```

No `exp`. It does not expire, and no clock will ever make it expire. Kubernetes documents this as the
defined behaviour, not an artefact of this cluster: tokens in manually created
`kubernetes.io/service-account-token` Secrets **"don't expire and don't rotate"**, and the control plane
invalidates one by deleting the Secret — including automatically, via the token controller, when the
**ServiceAccount** itself is deleted ([Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/),
[Managing Service Accounts](https://kubernetes.io/docs/reference/access-authn-authz/service-accounts-admin/)).
So it stops working when the Secret goes, and at no other moment. So the two credential shapes need two
different designs, and conflating them is how a reconciler ends up waiting for an expiry that never
arrives:

| credential | lifetime | what "renewal" means |
|---|---|---|
| **declared token Secret** (`kubernetes.io/service-account-token`) | **none** — no `exp` claim at all | there is no clock to track. Rotation is an **action**: delete the Secret and let whatever declares it — the operator chart, by Helm or by Argo — re-create the object, which the token controller then fills. The controller **does not recreate** a deleted Secret; it only adds a token to one that exists (Kubernetes, *Token controller*: "watches for ServiceAccount token Secret addition … and adds a token to the Secret if needed"), and since 1.24 nothing creates one unasked. Nothing to schedule, and nothing for the 80 % trigger to fire on |
| **TokenRequest-minted** (#238) | bounded, real `expirationTimestamp` | §8.3's 80 %-or-24-hours trigger applies exactly as written |

Three consequences:

1. **§9.2's `auth_failed` row means different things on the two paths.** On a minted token it can be
   expiry. On a declared one expiry is *impossible*, so the same failure means the Secret was deleted or
   the ServiceAccount was recreated with a new uid (a withdrawn *grant* is a 403 — §9.2's `forbidden`
   row, never this one) — and re-reading the Secret before reminting is not merely an optimisation, it
   is the whole fix.
2. **This is precisely why the tab writes `expires: current` and never `expires: never`** (the
   operator's ruling on #248). A credential with no expiry must not be rendered as though it had a
   reassuring one, and "never" is the word an auditor is entitled to object to.
3. **It puts the preference order in question.** §3 prefers the declared Secret and mints only when none
   exists, because the chart provisions the declared one. But a non-expiring credential is the thing the
   audit posture likes least, and TokenRequest exists to avoid it. **Recommendation: prefer the minted
   token wherever the `create serviceaccounts/<name>/token` grant is present, and fall back to the
   declared Secret** — the reverse of the current draft. Upstream says the same thing, and more
   bluntly: for an application outside the cluster, the Kubernetes project *"recommends you avoid this
   approach, as long-lived bearer tokens represent a security risk"* once disclosed
   ([Service Accounts](https://kubernetes.io/docs/concepts/security/service-accounts/)). The dashboard
   is exactly that application. It is a decision for the operator, recorded here with its measurement
   rather than settled silently, and either way the tab must say which shape a
   cluster is using, because that is what determines whether renewal is a clock or a deletion.

Worth stating precisely, because an earlier draft overstated it: **Argo CD does not rotate cluster
credentials *automatically*.** It is not that it cannot — `argocd cluster rotate-auth` exists and rotates
the `argocd-manager` token on demand, and the documented manual procedure is to delete the token Secret
so Kubernetes issues a new one and re-run `argocd cluster add`. What Argo has no equivalent of is a
loop that renews **before** expiry without anybody asking.
A token that never expires is the alternative, and the audit position here forbids it (#248: never
`expires: never`; a declared Secret reads `expires: current`). So renewal is ours to do, and §8.2's loop
is where it lives.

### 8.4 What CI/CD gets from this

- **Idempotent.** The same values file applied any number of times produces one outcome.
- **No human step.** Connecting an estate is a merge, not a sequence of GUI actions; the tab remains for
  the urgent single add (§2).
- **Gated by the file, not by the tab's switch.** `clusterConfig.secrets.writes.enabled` governs the
  tab's writes (`_writes_gate`, `gsd/api.py`: a proxy-verified viewer, `clusterconfig:manage`, the
  switch, one audit line naming the viewer). A declared mode has no viewer to gate: the values file the
  operator's CI/CD reviewed *is* the authorization, the reconciler writes as the pod's ServiceAccount, and
  its audit is the `phase=`-tagged line naming the cluster and the bootstrap username. §5's
  `writes-disabled` row is therefore the **tab's** Connect action (S3c) only; a deployment that wants no
  autonomous minting declares no mode. Said here because an implementer reading §5 alone would gate the
  loop on the switch, and one reading this section alone would not.
- **Reviewable.** The cluster list is a diff, and the reconciler's every action is one `phase=`-tagged
  log line (#245) naming the cluster and the outcome.
- **Recoverable.** Any derived object can be deleted and will come back. Nothing a human authored is
  *targeted* by the loop — but "cannot be destroyed" is a promise only §8.1's guards can keep, and only
  once they are built: the marker is forgeable, and a delete without UID and resourceVersion
  preconditions can still destroy a replacement object created in the race. S3d's acceptance is where
  that promise is earned, not here.

## 9. Credential reconciliation, built in

The operator, 2026-09-20: *"we just need to add a credential reconciliation built-in so that we are
making sure that all things work as intended and help resolve things."*

§8 keeps the **object** right. This keeps the **credential** right — a Secret can exist, parse and be
perfectly current while the token inside it no longer opens anything. The dashboard already classifies
exactly this (`gsd/poller.py`, #245): every failure carries a `phase=`, an `outcome=` and an `action=`
telling a human what to fix. Credential reconciliation is the step that stops waiting for the human on
the subset the dashboard can fix by itself.

Drawn as flow 6 of `docs/DESIGN_cluster_connection_flows.md`, in mermaid and in ASCII.

### 9.1 The poll is the probe

A cluster that polls needs no health check — the poll already proves the credential works, every cycle,
and its outcome is recorded (`store.record_poll`). A separate probe runs only where there is no poll to
learn from: a cluster just connected, and one whose stanza changed. Nothing here adds a second request
per cluster per cycle to prove what the first one already proved.

### 9.2 What it resolves, and what it refuses to

| outcome | what it actually means | what the loop does |
|---|---|---|
| `auth_failed` on a **derived** Secret | the token expired, was deleted, or the ServiceAccount was recreated | re-read the declared token Secret; if it is gone or stale, **remint** (§8.3) and rewrite. Recorded as a recovery, not an incident |
| `auth_failed` on an **unowned** Secret | someone else's credential has gone stale | **report only** — today's action line, unchanged: *"the token is invalid or expired: rotate it in this cluster's Secret"*. We did not make it and we do not rewrite it |
| `forbidden` | the token is **valid**; the RBAC behind it is not | **never remint.** A new token has exactly the same permissions, so reminting burns the bootstrap account to no effect. Report the missing grant by name |
| `unreachable` | transport — DNS, routing, the endpoint moved | no credential action at all. Reminting an unreachable cluster is a login attempt that cannot succeed |
| `cert-verify-failed` *(see below — not an outcome today)* | the CA no longer matches | for a derived Secret, re-read `ca.crt` alongside the token and rewrite it — a rotated cluster CA is the common cause and it is ours to fix |

**Two corrections from the adversarial pass, both measured against the code, and both changing what S3a
must build:**

1. **`cert-verify-failed` is not an outcome the code produces.** It is a string in the log line only:
   `poll_once` classifies a certificate failure and still records and returns `unreachable`
   (`gsd/poller.py`). A reconciler keyed on it would never fire, and one keyed on `unreachable` would
   remint into an unreachable cluster. So S3a's first job in this section is to make the CA failure a
   **structured outcome** the caller can branch on — otherwise this row is undeliverable.
2. **`auth_failed` covers two different situations**, and only one of them is reminting's business: a
   real 401 from the API server, and a **local credential-resolution failure before any request is made**
   (`gsd/kube.py`). Reminting the second is pointless — nothing was presented and nothing was refused —
   and for a credential-less stanza awaiting its first lookup (§4.2) that is exactly the state the pod is
   in. The two must be told apart before any remint.

The `forbidden` row is the one that makes this design rather than a retry loop. "Credential
reconciliation" naively implemented remints on any refusal; authentication and authorization are
different answers to different questions, and the dashboard already distinguishes them
(`gsd/kube.py`: `AUTH_FAILED`, `FORBIDDEN`, `UNREACHABLE`).

### 9.3 The lockout guard — why this loop is bounded

The bootstrap account is **one account for the fleet** (§3.1). A directory locks an account after a few
failed binds. So a reconciler that retries a stale password once per cluster per cycle would, within
minutes, lock the one account every cluster depends on and convert one broken cluster into a broken
estate. The rules that prevent it:

1. **Back off per credential, not per cluster.** A bind failure suspends *that credential* everywhere,
   immediately — the other clusters using it are not allowed to keep trying. **There is no seam for this
   today and S3d must build one**: `Poller` runs one thread per cluster and *discards* `poll_once`'s
   return value (`gsd/poller.py`), and `ClusterRegistry`'s lock guards discovery state only
   (`gsd/clusterconfig/registry.py`). A per-credential gate therefore needs a process-wide coordinator
   **and** durable state in the Store — durable because a pod restart must not forget that a password was
   refused and start the lockout walk again.
2. **A refused password is never retried.** Wrong credentials are a configuration fact, not a transient:
   one failure, a `login-refused` finding quoting the server's own words, and no second attempt until
   the declaration changes.
3. **Bounded, exponential, and it gives up out loud.** Transient failures retry with backoff to a stated
   ceiling, then stop with a finding that names the cluster, the account and the last error.
4. **Reminting is not logging in.** A remint uses the bootstrap session that already exists, or the
   TokenRequest grant — it is not an excuse to re-enter a password.

### 9.4 Help resolve things

Where the loop cannot fix it, it says precisely what would, on the tab and in one log line — that is
what "#245's `action=`" already does, extended with what was *tried*: `attempted=remint`,
`outcome=forbidden`, so the reader knows the cheap fix is already ruled out.

It also checks the dashboard's **own** grants rather than inferring them from a failure: the reader
ClusterRole, `get` on the declared token Secret, and `create serviceaccounts/<name>/token` where
minting is configured. Each is asked as a **SelfSubjectAccessReview** — the dashboard asking about its
own identity on the target, not the `SubjectAccessReview` the tier resolver already uses to ask about a
*reader* (`gsd/api.py`). **No SelfSubjectAccessReview path exists in the app today** — `gsd/kube.py`
carries only the SubjectAccessReview form with an explicit user and groups — so this is new code, not a
new caller of something shipped. Each grant is reported present or missing by name. A missing grant is the
commonest cause of a cluster that "will not connect", and naming it is the difference between a
five-minute fix and an afternoon.

**The self-check must be asked precisely, or it reports grants that exist as missing.** Measured on the
reference cluster while auditing these very permissions:

- a subresource must be named as a subresource. `can-i get nodes/proxy` answers **no** while the rule is
  present; the question only resolves with the subresource given as one (`--subresource=proxy`).
- a `resourceNames`-pinned grant only answers for the name it is pinned to: the check must name *that*
  ServiceAccount, not ask in general.
- **and the notation matters, which an earlier draft of this very section got wrong.** In a
  `ResourceAttributes` the object's **name** and its **subresource** are separate fields, so
  `serviceaccounts/token` written as a single string asks about a ServiceAccount *named* `token` — the
  trap this paragraph exists to warn about, committed in the warning itself. The question is
  `resource: serviceaccounts`, `subresource: token`, `name: <the ServiceAccount>`.

Both traps produce a **false gap** — a red row on the tab telling an operator to grant something they
have already granted. Two were nearly recorded that way during the audit that produced this spec, which
is why the rule is written down rather than left to the implementer.

**Acceptance** (with §7's run): delete the declared token Secret on the target and the cluster recovers
by itself within one cycle, recorded as a recovery; remove the reader ClusterRoleBinding and it does
**not** remint — it reports `forbidden` with the missing grant named; set a wrong bootstrap password and
exactly one bind is attempted, with every other cluster on that credential suspended rather than
locking the account.

## 10. Decomposition

- **S3a** — the loader AND the parser: the three keys in both, the credential kind and poll path of
  §4.2 (a cluster awaiting its first lookup is not an `auth_failed`), `clusterConfig.fleetAccount` in the
  chart, the relaxed credential requirement, the six refusals, the equivalence guard (§4.1) and the
  `fleet-credential-missing` finding. No network.
- **S3b** — the onboarding sequence and its findings, behind #119 P2's provider; `oauthTrust` and its
  three modes (defaulting to `caData`, §6); the annotations on the written Secret. It also owns the
  **vocabulary**: every new finding code added to the closed set AND to the page in the same PR (the
  SPEC_S1 §S1.2 contract), and every new `phase=` added to #245's set.
- **S3d** — the reconciler (§8 and §9): credential recovery, the lockout guard, the self-check, and the ownership annotations, the seven transitions, drift reporting,
  the 80 % renewal trigger, and standing down on an unowned shadow. It is its own step because it is
  the only one that DELETES, and a deleting loop earns its own review and its own acceptance run.
- **S3c** — the tab: the mode per cluster, the credential's provenance, the token's source and
  expiry wording (`expires: current` for a declared Secret, a real date for a minted one — #248), and
  a **Connect** action for a stanza waiting on its credential.

Each its own PR, each its own three-seat review, each walked on the reference cluster.
