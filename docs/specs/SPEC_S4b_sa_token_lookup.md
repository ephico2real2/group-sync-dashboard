# SPEC S4b — the ServiceAccount token lookup: read as the fleet account, write as the dashboard (#284)

| | |
|---|---|
| Programme | Cluster configuration as labelled Secrets (#230), continued — S4 designed the retrieval; S4a shipped the login; this is step B, the lookup that turns a `saTokenLookup` stanza into a polling cluster |
| Batch | S — cluster configuration |
| Release | — (post-programme; S4 step B, the issue's own label S3b-B) |
| Version on release | app 0.31.0, chart 0.50.0 |
| Issue | [#284](https://github.com/ephico2real2/group-sync-dashboard/issues/284) |
| Status | specified |
| Source | OB1's implementation specification of 2026-09-22, written before the code from the business owner's brief and the six corrections on the issue, `docs/specs/SPEC_S4_token_retrieval.md` §1, §4, §6 and §9, `docs/specs/SPEC_S4a_fleet_login_session.md` §2.1 and §6, the upstream sources cited in §2, and the lab measured 2026-09-21/22 |

## How to read this spec

"Measured" is what the reference cluster or an upstream source answered, with the command. "Design"
is the code, file by file, in fenced blocks applied **verbatim**: a whole-file block replaces or
creates the file it names; an edit block's "Old text" is replaced by its "New text" and must match
exactly once. A block found wrong during implementation is corrected **here first**, with the reason
under "Orchestrator's notes", and only then applied. The board is issue #288.

## Orchestrator's notes

Decisions taken where the sources were silent or wrong, each with its reason. They bind the code
below.

- **`clusterConfig.secrets.writes.enabled` does not split (SPEC_S4 §10.2, decided here).** The
  switch renders one grant — `create`/`update`/`delete` on Secrets in the release namespace
  (`charts/group-sync-dashboard/templates/cluster-secrets-rbac.yaml`) — and that grant is the
  *capability*. The two *intents* it serves are each declared explicitly already: a person's write
  needs a proxy-verified identity and `clusterconfig:manage` (`gsd/api.py#_writes_gate`); the
  lookup's write needs a stanza that says `saTokenLookup: true` for that one cluster, reviewed in the
  values file. A second switch would say "yes, I meant the stanza I wrote" and gate the same verbs
  twice — two places to get out of step, no decision it lets an estate take that the stanza does not.
  "Easy to manage, best practice": one switch, whose comment now names both consumers.
- **The token's address is fleet-wide, not a stanza key.** The poller ServiceAccount is provisioned
  on every target by the operator chart under one name (measured: `group-sync-operator-helm-0.14.0`
  labels on the lab's SA and Secret), so the source is one convention for the estate:
  `clusterConfig.saTokenLookup.{sourceNamespace, sourceServiceAccount, tokenSecretName}`, defaulting
  to the operator chart's names, with `tokenSecretName` empty meaning `<sourceServiceAccount>-token`.
  A per-cluster override is not added: it would be a key in three places (the stanza memory rule) for
  a case the estate does not have. When one appears it is added under that rule, not here.
- **The Secret is found by name with `get`, never by listing and never through the ServiceAccount.**
  Measured (§2): the lab's SA `.secrets` lists only its dockercfg — a manually created token Secret
  is *not* referenced from the SA, so `.secrets[]` cannot find it — and the estate's grant to the
  fleet account is `get` on that one Secret by `resourceNames`; `list` is refused. The read is one
  `GET` on a known name, the narrowest thing that works, the same rule the chart applies locally.
- **The written Secret's trust is the declaration's trust, verbatim — the target's `ca.crt` is not
  written.** SPEC_S3 §5 says "read the ServiceAccount token + ca.crt" and SPEC_S4 §1 "that is what
  the lookup fetches"; both are superseded, for the two-host reason S4a §2.1 measured. The bundle
  that just logged in verified the API host (discovery) *and* the OAuth host (authorize); the
  target's `ca.crt` verifies the API host only. Writing `ca.crt` as `caData` would make #285's
  re-login through that Secret fail at the OAuth host on exactly the split-CA estate the lab cannot
  show. So: `caBundleFile` → its bytes as `caData`; a declaring Secret's `caData` → kept;
  `insecureSkipVerify` → `insecure`; the trusted bundle → no `caData`. The poll then verifies with
  what the login verified with, and a ping can log in again with the same trust. This is #283's
  split-CA research (SPEC_S4a §2.1, raised by both reviewers of PR #289) carried forward into the
  one place it decides something; the business owner confirmed it on approval (2026-09-22).
- **The cluster type label is stamped last, unconditionally — the operator's requirement, stated
  on approval.** Measured on the merged tree: `validate()` refuses a caller label under the app's
  prefix, but `secret_object()` merges caller labels *after* the app's, so called without
  `validate()` with `groupsync-dashboard.io/secret-type: onboard` it produced a Secret labelled
  `onboard` — one discovery cannot see. The invariant "a written Secret always carries
  `secret-type: cluster`" held by convention (every caller validated first); `store_lookup` and
  #293's ConfigMap feed are new callers, the latter with labels someone else wrote. One line in
  §3.10 makes it structural, byte-identical for every input that validates today; `validate()`'s
  refusal stays.
- **`managed-by` for a lookup-written Secret is `sa-token-lookup`** (SPEC_S4 §10.3): the stanza key
  in kebab case, so `saTokenLookup: true` → `managed-by: sa-token-lookup` reads as one thing.
  `token-source` stays `remote-lookup`, the credential kind — the two answer different questions.
- **A fourth provenance annotation, `groupsync-dashboard.io/lookup-account`.** A Secret that declared
  the mode is updated in place (SPEC_S4 §1), and `ldapConnectionBootstrap` must leave `config` with
  the mode key — the parser refuses it beside a credential. Without a record the per-cluster account
  is lost and #285's ping would silently fall back to the fleet default. Written on both paths.
  Additive: omitted when unset, like the other three; the shape is otherwise untouched.
- **Where the lookup runs:** on the discovery thread, after each discovery, one cluster at a time,
  leader only. SPEC_S4 §6 wants one retriever per estate; the discovery thread is already that, and a
  successful write wakes it so the cluster polls within seconds, not at the next cadence.
- **The schedule is bounded by cost, not by kind.** A failure that spent a login (a bind, a token
  minted and revoked) counts: attempt `n/5`, the next try `binding_interval × 2^(n−1)` later (5, 10,
  20, 40 min at the default), then `gave_up=true` — nothing more until the declaration changes, the
  pod restarts, or #285 re-arms it. A failure that spent nothing (no password Secret, writes off, a
  password the target already refused) is rechecked every cycle at no cost and announced on
  transition only. A refused password is never sent again while it is the same password: an
  in-memory gate keyed on `(username, sha256(password))`, SPEC_S4 §6's in-memory half; #285 makes
  it durable.
- **Every lookup failure is `phase=credential`.** #245's set is ordered as the path runs, and the
  lookup — password, login, read, write — is how the credential is obtained. The login's own
  transport failures keep S4a's `tls`/`connect`. No new phase.
- **The finding's `secret` is `gsd-cluster-<name>` on both paths** — the object the lookup writes
  or updates — so the tab's Findings card names what to look at.
- **Render refusals cover `saTokenLookup` only.** `userSelfLogin` (#285) stores nothing and needs no
  write grant.
- **The live check logs in as the htpasswd `developer`, not the fleet account** (S4a's rule: the
  account the target authenticates every user with is never used to test), through
  `ldapConnectionBootstrap: developer` and a grant of the token-reader Role to `developer` on the
  lab. The mechanism is identical; the blast radius is not.

Corrections to the issue's comments, fact-led:

- **The one-year fuse applies to auto-generated token Secrets only.** The cleaner
  (`pkg/controller/serviceaccount/legacy_serviceaccount_token_cleaner.go`, `evaluateSATokens`) skips
  a Secret unless `hasSecretReference(sa, secret.Name)` — the ServiceAccount's `.secrets` names it —
  and the docs say the same: "If the Secret is referenced in the `secrets` field, it is considered an
  auto-generated legacy token. Otherwise, it is considered a manually created legacy token." Measured
  on the lab: the poller SA's `.secrets` is `[group-sync-dashboard-cluster-poller-dockercfg-474g6]`,
  the token Secret is not in it, so the cleaner will never stamp it. An estate whose poller token was
  auto-generated (OpenShift ≤ 4.15 with the registry on) *is* subject. Reading the label stays: it
  costs nothing and the failure it prevents is a bare 401 a year later.
- **The daily ping does not keep the credential alive; the poll does.** `legacy-token-last-used` is
  stamped by the token *authenticator* when the SA token authenticates a request
  (`pkg/serviceaccount/legacy.go`, `Validate` → `patchSecretWithLastUsedDate`). The fleet account's
  `get` of the Secret uses the fleet account's session, not the SA token, and stamps nothing.
  Measured: the lab's poller Secret is stamped `2026-09-22` because the mock cluster polls with it.
  What #285 must design for is a cluster that *stops polling* (suspended, disabled, unreachable) on
  an estate whose token was auto-generated.
- **OpenShift's 4.16 note is about registry-driven generation.** The release note reads: "when the
  integrated OpenShift image registry is enabled, the legacy service account API token secret is no
  longer generated for each service account". Upstream stopped auto-generation in 1.24
  (`LegacyServiceAccountTokenNoAutoGeneration`, beta on by default 1.24, GA 1.26). The consequence
  the issue draws is right either way: on a modern target nothing creates the Secret unasked.

Review of PR #295 (Codex and Cursor, 2026-09-22; seven findings, each corrected here first and then
re-applied from these blocks):

- **P0-1 — the scheduler re-entered a login #283 had made terminal.** Only `AUTH_FAILED` gated the
  credential; every other answer became `login-failed` and the schedule called `lookup()` again — a
  fresh bind, up to five, which for a *locked* account (LDAP code 19 → the oauth-server's HTTP 500)
  is the lockout walk one layer up. **Fix shape, and where it departs from the reviewers':** the
  brief proposed gating on `phase == "credential"`. That misses one case #283 also made terminal — a
  read timeout or dropped connection *after* the authorize GET was written (`phase=connect`,
  `retryable=False`): the password was on the wire and the target may have bound. So `LoginError`
  now carries **`bound`** — #283's own line, "the password was on the wire", as a field: True for
  every `phase=credential` answer and for that one transport branch. *As first written* the lookup
  gated the credential on `bound and phase == "credential"` and made any other `bound` failure
  "final" in the schedule; **the second pass (R2-1 below) refuted the second half** — the schedule's
  state re-arms on any shape change — so now every `bound` answer gates, and the gate carries the
  target. TLS and connect failures before the write still retry, correctly: nothing was bound. A
  500 on authorize is one bind and a gated (target, credential).
- **P0-2 — the replica rule reached only a values stanza.** The `replicaCount > 1` refusal sat inside
  `range $modeOf`; a Secret-declared mode on a two-replica release with election off (which
  `deployment.yaml` requires above one replica) retrieved on **every** replica, because with election
  off `elector` is None. The rule now holds wherever a lookup is *possible*: at render,
  `clusterConfig.secrets.writes.enabled` with `replicaCount > 1` is refused; at runtime the pod
  learns `replicaCount` through the ConfigMap and a lookup on a multi-replica release without an
  elector is `fleet-write-disabled`, whose meaning widens to "this deployment is not configured to
  let the lookup write".
- **P1-1 — the retrieved token could reach the tab.** `read_sa_token` raised on the type, owner and
  `invalid-since` paths before decoding `data.token`, so the token was not among the secrets the
  refusal was scrubbed against, and the owner and type were quoted raw. Now the token is decoded
  first and rides every refusal's `secrets`; the owner and the type are described by length, never
  echoed (the parser's rule for remote-controlled names); `LookupRefused.scrub` rewrites `detail`,
  `action` **and `args`**, so `str(exc)` is clean too. The pin asserts the SA token's absence, which
  it had not — a test that looked like it checked.
- **P1-2 — the tab's GitOps YAML had the writer's merge-order bug.** `ccYaml` emitted the app's label
  first and the form's labels after; the app's label goes last, as `secret_object()` now does.
- **P1-3 — a quoted `"false"` enabled writes.** `_bool_setting`'s ConfigMap path was
  `bool(raw.get(...))`; it now reads the word exactly as its env path does. A real YAML boolean is
  unchanged; any other type keeps truthiness, with the warning.
- **P1-4 — `lookup(write=True)` trusted its caller to check the switch.** It checks
  `secrets.enabled and writes.enabled` itself, before any password is read; the poller's own
  pre-check is gone, so the rule lives in one place. `write=False` needs no grant.
- **P1-5 — `invalid-since` was tested by truthiness.** Kubernetes allows an empty label value; the
  label must be *absent*: `INVALID_SINCE_LABEL in labels`.
- **Second pass on `129307b` (Codex with a working interpreter; five refutations, each corrected
  here first):**
  - **R2-1 — the gate was too narrow and too broad at once.** Too narrow: a post-write transport
    failure was made "final" in `_LookupState`, which re-arms on *any* shape change — a `visibility`
    edit sent the same password to the same target again. Too broad: the key omitted the target,
    so a 500 from target A blocked every login to a healthy target B on the same account
    (measured). One fix closes both: the gate is keyed on **(target `api_url`, username,
    sha256(password))** and **every `bound` answer gates** — the target evaluated the password or
    may have. `final` is gone. The business owner retracted the earlier "keep two tiers" decision
    on the measurement; the stored code stays `login-refused` for a 401 and `login-failed` otherwise.
  - **R2-2 — the test that blessed the regression is inverted:** after a read timeout the same
    credential must not reach that target again; a different target on the same account still may.
  - **R2-3 — moving the decode first put a new failure in front of the error handling:** a
    non-scalar `data.token` raised `TypeError` before any refusal. The decode now also catches
    `TypeError`. And a `ClusterError` message carries a remote body (`HTTP 500 on …: <body>`) that
    can hold the very token being read, which was never decoded and so never scrubbed: messages
    quoted by the lookup are cut at the status (`_status_only`), for the target's Secret and the
    local password Secret alike; a transport message is this process's own words and is kept.
  - **R2-4 — `_bool_setting` still decided on odd values:** `2`, `-1` and `[false]` enabled writes
    silently, `null` and `[]` disabled silently, and the warning named the env variable for a
    ConfigMap value. It now accepts a real boolean or one of the words and nothing else; anything
    else is the default, with a warning naming the source it came from. A null is absent.
  - **R2-5 — the replica guard is best-effort, and that is recorded rather than patched.** Two
    pollers with `replica_count=1` and no elector, a stale and a new lease holder, a rollout's two
    pods, an HPA past a ConfigMap that says 1: none is caught by an in-memory state, and the chart
    itself calls election "best-effort, not a write fence". True mutual exclusion across replicas
    needs a claim the cluster arbitrates — a Lease acquired by compare-and-swap before `FleetLogin`
    is built — and SPEC_S4 §9 assigns the durable, replica-shared gate to **#285**. Not built here;
    the render and runtime refusals stay as tight as they are, the operational guidance until #285
    is one replica, and #285 inherits the requirement with the measurement (§6).
- **Not a finding, recorded so nobody "fixes" it:** the lab's log lines read `account=<redacted>`
  because CRC's `developer` password *is* the word `developer`, and the redactor strips the
  substring wherever it appears. Over-redaction on this lab is the correct behaviour; exempting
  `account=` from scrubbing would leak the password on any estate where the two differ.

## 1. The loop — four stages, one missing

```
values.yaml cluster stanza  (saTokenLookup: true; the fleet account)         <- the feeder, declared in code
        |
        v   *** THIS SPEC — the only missing stage ***
  log in to the target as the fleet account (FleetLogin, #283, merged)
  GET the poller ServiceAccount's token Secret there, by name
        |
        v
  secret_object() writes gsd-cluster-<name> into the release namespace         <- ships (#230 S2, #282)
  and stamps groupsync-dashboard.io/secret-type: cluster on every Secret it writes
        |
        v
  discovery LISTs by that label -> the cluster polls, credential=bearer       <- ships (#230 S1)
```

Three of the four stages ship. `gsd/config.py#credential_kind` already classifies the stanza as
`remote-lookup`; what does not exist is the retrieval, and the code says so itself, in
`gsd/config.py#CREDENTIAL_PENDING_REASONS`: *"declares saTokenLookup — the token lookup is S3b, not
built; nothing has been obtained yet"*. This spec replaces that sentence with the mechanism, and
supplies the **values** the shipped writer takes — `token_source=remote-lookup`, the source namespace
and ServiceAccount, a `managed_by` that is not `ui` — not the Secret's shape.

Two identities, neither granted anything on the other side (`templates/fleet-account-rbac.yaml`): the
**LDAP fleet account** authenticates to the *remote* cluster and reads one Secret there; the
**dashboard's ServiceAccount** writes `gsd-cluster-<name>` *locally*. The GUI stays an equal path for
a single urgent add; the goal is that adding a cluster is a stanza.

Not in scope: revoking anything (the stored token is the target's and dies only with its Secret —
SPEC_S4 §9; #283 revokes the login token on every exit path), `userSelfLogin` and the schedule of
re-checks (#285), the token litter already on the lab (#286), TokenRequest minting (#238), and the
tab's provenance wording (S3c).

## 2. Measured, and what each measurement decides

Lab: OpenShift 4.22.7 (Kubernetes v1.35.6), `KUBECONFIG=~/.crc/machines/crc/kubeconfig`, 2026-09-22.

**The token Secret on the target, and the grant that reads it.**

```
$ oc get secret group-sync-dashboard-cluster-poller-token -n group-sync-operator -o json | jq '{type, keys:(.data|keys), labels:.metadata.labels, sa:.metadata.annotations["kubernetes.io/service-account.name"]}'
type   kubernetes.io/service-account-token
keys   ["ca.crt", "namespace", "service-ca.crt", "token"]          token = 1377 chars, ca.crt == kube-root-ca.crt (7209 bytes)
labels {..., "kubernetes.io/legacy-token-last-used": "2026-09-22"}
sa     group-sync-dashboard-cluster-poller

$ oc get sa group-sync-dashboard-cluster-poller -n group-sync-operator -o jsonpath='{.secrets}'
[{"name":"group-sync-dashboard-cluster-poller-dockercfg-474g6"}]      <- the token Secret is NOT referenced

$ oc get role group-sync-dashboard-cluster-poller-token-reader -n group-sync-operator -o yaml   (bound to User ocp-oauth-bind-serviceid)
  secrets              get      resourceNames: [group-sync-dashboard-cluster-poller-token]
  serviceaccounts      get      resourceNames: [group-sync-dashboard-cluster-poller]
  serviceaccounts/token create  resourceNames: [group-sync-dashboard-cluster-poller]

$ oc auth can-i get  secrets/group-sync-dashboard-cluster-poller-token -n group-sync-operator --as=ocp-oauth-bind-serviceid   yes
$ oc auth can-i list secrets -n group-sync-operator --as=ocp-oauth-bind-serviceid                                             no
```

So the read is `GET /api/v1/namespaces/<ns>/secrets/<sa>-token` as the session, and nothing else
works with the grant the estate actually gives.

**The local side.**

```
$ oc auth can-i create secrets -n group-sync-dashboard --as=system:serviceaccount:group-sync-dashboard:group-sync-dashboard   yes   (crc.yaml: writes.enabled: true)
$ oc auth can-i get secrets/ldap-oauth-bind-secret -n openshift-config --as=system:serviceaccount:group-sync-dashboard:group-sync-dashboard   no
$ oc get secret ldap-oauth-bind-secret -n openshift-config -o json | jq '.data|keys'   ["bindPassword"]
```

The lab's release has the write grant and does *not* have the fleet password grant: `environments/crc.yaml`
carries no `fleetAccount` block, and the chart passes none of it to the pod today —
`templates/configmap.yaml` has no fleet key, and `gsd/config.py` has no fleet setting. §3 wires both.

**The hand-made Secret the written one is compared against** (`gsd-cluster-shared-rnd`): labels
`environment=rnd` + the type label; annotations `token-source: lookup`, `source-namespace`,
`source-service-account`; data keys `config, enabled, identity, name, server, visibility`; `config`
keys `bearerToken, tlsClientConfig`. Its `token-source` is the pre-#282 word `lookup`, not
`remote-lookup`, so the reader's shadow rule below will not treat it as the lookup's own.

**The legacy-token cleaner, from upstream** (`kubernetes/kubernetes` at `master`, read with `gh api`):
`legacy_serviceaccount_token_cleaner.go#evaluateSATokens` marks a Secret invalid only when it is
type `kubernetes.io/service-account-token`, older than the period, unlabelled or last used before
the period, **referenced from the ServiceAccount's `.secrets`**, and not mounted by any pod; the period
is `--legacy-service-account-token-clean-up-period`, default `8760h0m0s` (kube-controller-manager
reference). `legacy.go#Validate` refuses a token whose Secret carries
`kubernetes.io/legacy-token-invalid-since` ("has been marked invalid … or remove the label from the
secret to temporarily allow use") and stamps `legacy-token-last-used` with today's date on every
successful use. Gates: `LegacyServiceAccountTokenTracking` GA 1.28, `LegacyServiceAccountTokenCleanUp`
GA 1.30. The OpenShift 4.16 release note is quoted in the notes above.

**The two-host CA contract** is S4a §2.1's measurement, not repeated: on CRC `kube-root-ca.crt` carries
the ingress CA, so a stanza with only the API CA works here and the split cannot be reproduced. The
contract this spec states on the stanza (§3.1) is therefore verified by the hermetic split-CA test
S4a shipped, and by naming the failing host, not by a green CRC run.

**The deployment paths read the cluster list from different places.** `gitops/argocd-application-dashboard.yaml`
declares `clusters` in `helm.valuesObject`, deliberately, for this lab (its comment says why); plain
Helm reads `environments/crc.yaml`. A live check must say which mechanism it uses (§5).

## 3. Design

### 3.1 The contract, in one table

| | |
|---|---|
| declares the intent | a stanza `saTokenLookup: true` (values, the feeder) or a Secret's `config.saTokenLookup: true`; the account is `ldapConnectionBootstrap` else `clusterConfig.fleetAccount.username`; the password is `clusterConfig.fleetAccount.passwordSecret` |
| what is read | `GET /api/v1/namespaces/{sourceNamespace}/secrets/{tokenSecretName}` on the target, as the session; refused unless it is type `kubernetes.io/service-account-token`, annotated for `sourceServiceAccount`, and not labelled `legacy-token-invalid-since` |
| what is written | values path: `writer.create` with `CreateRequest(token_source=remote-lookup, source_namespace, source_service_account, lookup_account, managed_by=sa-token-lookup, tls = the declaration's, visibility/identity = `Settings.cluster_policy`)`. Secret path: `writer.store_lookup` — `config` becomes `{bearerToken, tlsClientConfig}` (mode and bootstrap keys leave), the four annotations are set, labels and `managed-by` are kept |
| the CA the stanza must carry | **both hosts** — the API host (`/.well-known/oauth-authorization-server`) and the OAuth route (`/oauth/authorize`), which an enterprise PKI signs separately. A trust failure names the host |
| the write grant | `clusterConfig.secrets.writes.enabled` — refused at render for a stanza (and `secrets.enabled: false`, `visibility: remote-sar`); `writes.enabled` with `replicaCount > 1` refused at render stanza or not; at runtime `lookup()` itself refuses `fleet-write-disabled` with the switch off, and the poller refuses it above one replica without an elector |
| the shadow | a lookup-written Secret over the stanza that asked for it is not `shadows-values-entry` (the reader compares the Secret's `token-source` with the stanza's credential kind) |
| the seam for #285 | `fleetlookup.lookup(..., write=False)` — login, read, revoke, return the token, write nothing |
| the lockout gate | in memory, keyed on (target, username, sha256(password)): every answer that reached the target after the password was written gates that target; a healthy target on the same account is unaffected; best-effort across replicas until #285 |
| failure vocabulary | eight codes in `FINDING_CODES`, all `phase=credential`: `fleet-credential-missing`, `fleet-write-disabled`, `login-refused`, `login-failed`, `sa-token-secret-missing`, `sa-token-unreadable`, `sa-token-invalidated`, `lookup-write-failed`; two events, `fleet-lookup` and `fleet-lookup-failed`, the latter with S4a's `attempt=`, `retry_in=`, `gave_up=` |

### 3.2 `charts/group-sync-dashboard/values.yaml` — the address, the two-host contract, the switch

**File:** `charts/group-sync-dashboard/values.yaml` — edit

Old text:

```yaml
      # Secret and the key if the grant is absent — it does not crash.
      rbac:
        create: true
```

New text:

```yaml
      # Secret and the key if the grant is absent — it does not crash.
      rbac:
        create: true
  # WHAT `saTokenLookup` READS on every target (SPEC_S4b, #284): the poller ServiceAccount's permanent
  # token, held in a `kubernetes.io/service-account-token` Secret the operator chart creates beside
  # the ServiceAccount. One convention for the fleet — the operator chart provisions the same names
  # on every cluster — so the defaults are its names and a default install needs nothing here.
  #
  # AN ONBOARDING PRECONDITION, NOT AN ASSUMPTION. Kubernetes stopped creating token Secrets in 1.24
  # and OpenShift 4.16 stopped generating them for the registry, so on a modern target the Secret
  # exists only because someone created it (type kubernetes.io/service-account-token, annotated
  # kubernetes.io/service-account.name=<the ServiceAccount>; the control plane fills it). When it is
  # absent the tab says so in those words: `sa-token-secret-missing` — create the token Secret on
  # the target. The fleet account needs `get` on that ONE Secret there (resourceNames), never list.
  #
  # THE STANZA'S CA MUST COVER TWO HOSTS. The login touches the API host (the OAuth discovery
  # document) AND the OAuth route (/oauth/authorize), and an estate whose ingress is re-signed by an
  # enterprise PKI signs them differently. `caBundleFile` on a saTokenLookup stanza (or the trusted
  # bundle, when the stanza names none) must verify BOTH, and the finding names which host failed.
  # A green run on CRC proves nothing about this: its API bundle already carries the ingress CA.
  # The Secret the lookup writes carries the DECLARED trust, so a later re-login has what worked.
  #
  # NEEDS clusterConfig.secrets.writes.enabled (above): the lookup writes gsd-cluster-<name>, and
  # create/update on Secrets is the grant that switch renders. A stanza with it off fails
  # `helm template`; a Secret-declared mode with it off is a `fleet-write-disabled` finding.
  saTokenLookup:
    sourceNamespace: group-sync-operator
    sourceServiceAccount: group-sync-dashboard-cluster-poller
    # The token Secret's name on the target. Empty = <sourceServiceAccount>-token.
    tokenSecretName: ""
```

**File:** `charts/group-sync-dashboard/values.yaml` — edit

Old text:

```yaml
    # and removes the exception. Turning it on is the decision to let the dashboard mint cluster
    # access. On, the Role above
```

New text:

```yaml
    # and removes the exception. Turning it on is the decision to let the dashboard WRITE cluster
    # Secrets — the one grant, with two consumers that each declare their own intent: a person on
    # the tab (an identity and clusterconfig:manage), and the saTokenLookup lookup (a stanza that
    # says so, per cluster; SPEC_S4b). It does not split, because a second switch would gate the
    # same verbs twice and decide nothing the stanza does not. On, the Role above
```

**File:** `charts/group-sync-dashboard/values.yaml` — edit

Old text:

```yaml
  # the hosting cluster is refused — this pod's own cluster authenticates with the mounted
  # ServiceAccount. Until S3b lands, a mode stanza is listed on the Cluster Configurations tab with its
  # credential pending and is not polled. The render refuses each of these exactly as the loader does,
  # so a bad stanza fails `helm template`, not the pod after a green upgrade.
```

New text:

```yaml
  # the hosting cluster is refused — this pod's own cluster authenticates with the mounted
  # ServiceAccount. A saTokenLookup stanza is retrieved on the next discovery cycle (SPEC_S4b): the
  # dashboard logs in as the fleet account, reads the poller ServiceAccount's token on the target
  # (clusterConfig.saTokenLookup below) and writes gsd-cluster-<name> here, which discovery then
  # polls like any other Secret. It needs clusterConfig.secrets.writes.enabled, and its CA must
  # cover both the API host and the OAuth route. A userSelfLogin stanza is still pending (#285).
  # The render refuses each of these exactly as the loader does, so a bad stanza fails
  # `helm template`, not the pod after a green upgrade.
```

### 3.3 `charts/group-sync-dashboard/templates/configmap.yaml` — the pod learns the account and the address

**File:** `charts/group-sync-dashboard/templates/configmap.yaml` — edit

Old text:

```yaml
    clusterSecretsWritesEnabled: {{ .Values.clusterConfig.secrets.writes.enabled }}
```

New text:

```yaml
    clusterSecretsWritesEnabled: {{ .Values.clusterConfig.secrets.writes.enabled }}
    # The fleet account (SPEC_S3 §3.1) and what saTokenLookup reads (SPEC_S4b): the username and the
    # password Secret's ADDRESS — the password itself is read at connect time through the grant
    # fleet-account-rbac.yaml renders, and never rendered anywhere.
    fleetAccountUsername: {{ .Values.clusterConfig.fleetAccount.username | quote }}
    fleetPasswordSecretNamespace: {{ .Values.clusterConfig.fleetAccount.passwordSecret.namespace | quote }}
    fleetPasswordSecretName: {{ .Values.clusterConfig.fleetAccount.passwordSecret.name | quote }}
    fleetPasswordSecretKey: {{ .Values.clusterConfig.fleetAccount.passwordSecret.key | quote }}
    saTokenLookupSourceNamespace: {{ .Values.clusterConfig.saTokenLookup.sourceNamespace | quote }}
    saTokenLookupSourceServiceAccount: {{ .Values.clusterConfig.saTokenLookup.sourceServiceAccount | quote }}
    saTokenLookupTokenSecretName: {{ .Values.clusterConfig.saTokenLookup.tokenSecretName | quote }}
    # How many replicas this release runs: the lookup is one retriever per estate (SPEC_S4 §6), and a
    # Secret-declared mode is invisible to the render, so the pod refuses it above one replica itself.
    replicaCount: {{ int .Values.replicaCount }}
```

### 3.4 `charts/group-sync-dashboard/templates/_helpers.tpl` — refused at render

Inside `gsd.validateClusters`, the remote-sar rule in the second pass, then a third block after it.

**File:** `charts/group-sync-dashboard/templates/_helpers.tpl` — edit

Old text:

```
{{- else if and (eq $vis "remote-sar") (ne $id "same-as-host") -}}
{{- fail (printf "clusters[%d] (%s): visibility remote-sar needs identity: same-as-host. The review names the host's username on that cluster, which only means something if both clusters share an identity provider — say so explicitly." $i $name) -}}
{{- end -}}
{{- end -}}
{{- end -}}
```

New text:

```
{{- else if and (eq $vis "remote-sar") (eq (index $modeOf $name | default "") "saTokenLookup") -}}
{{- fail (printf "clusters[%d] (%s): visibility remote-sar with saTokenLookup — the lookup writes this cluster as a Secret, and remote-sar is not yet accepted from a Secret (SPEC_S1). Use inherit, self-only or hidden until it is." $i $name) -}}
{{- else if and (eq $vis "remote-sar") (ne $id "same-as-host") -}}
{{- fail (printf "clusters[%d] (%s): visibility remote-sar needs identity: same-as-host. The review names the host's username on that cluster, which only means something if both clusters share an identity provider — say so explicitly." $i $name) -}}
{{- end -}}
{{- end -}}
{{- /* SPEC_S4b (#284): a saTokenLookup stanza WRITES gsd-cluster-<name> into the release namespace
       and discovery reads it back, so it depends on two switches this render can see — refused
       here, not by a finding after a green upgrade. */ -}}
{{- range $name, $mode := $modeOf -}}
{{- if eq $mode "saTokenLookup" -}}
{{- if not $.Values.clusterConfig.secrets.enabled -}}
{{- fail (printf "cluster %s declares saTokenLookup but clusterConfig.secrets.enabled is false: the lookup writes gsd-cluster-%s as a labelled Secret and discovery is what reads it back. Turn discovery on, or remove the mode." $name $name) -}}
{{- end -}}
{{- if not $.Values.clusterConfig.secrets.writes.enabled -}}
{{- fail (printf "cluster %s declares saTokenLookup but clusterConfig.secrets.writes.enabled is false: the lookup writes gsd-cluster-%s into the release namespace, and create/update on Secrets is the grant that switch renders (templates/cluster-secrets-rbac.yaml). Set clusterConfig.secrets.writes.enabled: true, or remove the mode." $name $name) -}}
{{- end -}}
{{- end -}}
{{- end -}}
{{- /* One retriever per estate (SPEC_S4 §6), held wherever a lookup is POSSIBLE and not only where a
       values stanza declares one (review of #295, P0-2): a Secret may declare the mode at any time,
       and above one replica election is off, so every replica would log in as the fleet account. */ -}}
{{- if and $.Values.clusterConfig.secrets.writes.enabled (gt (int $.Values.replicaCount) 1) -}}
{{- fail (printf "clusterConfig.secrets.writes.enabled with replicaCount %d: a cluster Secret may declare saTokenLookup at any time, and above one replica every pod polls for itself and each would log in as the fleet account (SPEC_S4 §6, one retriever per estate). Use replicaCount 1 for a release that writes cluster Secrets, or turn writes off." (int $.Values.replicaCount)) -}}
{{- end -}}
{{- end -}}
```

### 3.5 `charts/group-sync-dashboard/Chart.yaml`, the app version, the production example

**File:** `charts/group-sync-dashboard/Chart.yaml` — edit

Old text:

```yaml
version: 0.49.0
```

New text:

```yaml
# CHART 0.50.0 (2026-09-22), MINOR: `saTokenLookup` retrieves (#284, SPEC_S4b). The pod learns the
# fleet account's address and `clusterConfig.saTokenLookup` (what it reads on every target) through
# the ConfigMap; a saTokenLookup stanza is refused at render without `clusterConfig.secrets.writes.enabled`
# and `secrets.enabled`, with `replicaCount > 1`, or with `visibility: remote-sar`. appVersion moves to
# application 0.31.0 (below). A release declaring no mode renders exactly as before.
version: 0.50.0
```

**File:** `charts/group-sync-dashboard/Chart.yaml` — edit

Old text:

```yaml
appVersion: "0.30.0"
```

New text:

```yaml
# 0.31.0 (2026-09-22). A `saTokenLookup` cluster is retrieved: the dashboard logs in as the fleet
# account, reads the poller ServiceAccount's token on the target and writes the cluster Secret
# (#284, SPEC_S4b). Eight finding codes join the closed set; additive on the wire. MINOR.
appVersion: "0.31.0"
```

**File:** `local-development/pyproject.toml` — edit

Old text:

```toml
version = "0.30.0"
```

New text:

```toml
version = "0.31.0"
```

**File:** `local-development/gsd/__init__.py` — edit

Old text:

```python
__version__ = "0.30.0"
```

New text:

```python
__version__ = "0.31.0"
```

**File:** `charts/group-sync-dashboard/example-production.yaml` — edit

Old text:

```yaml
  # UNTIL S3b LANDS this cluster is listed on the Cluster Configurations tab with its credential
  # pending and is NOT POLLED — deliberately, so it is never reported as `auth_failed` for a
  # credential that was never presented.
```

New text:

```yaml
  # The lookup runs on the next discovery cycle (SPEC_S4b): a login as `svc.gsd.fleet`, one GET of
  # the poller ServiceAccount's token Secret on the target, and `gsd-cluster-shared-rnd` written
  # here — which needs `clusterConfig.secrets.writes.enabled` below, and a CA that verifies BOTH the
  # API host and the OAuth route (the trusted bundle here; a `caBundleFile` where it does not).
```

**File:** `charts/group-sync-dashboard/example-production.yaml` — edit

Old text:

```yaml
    writes:
      enabled: false     # the Cluster Configurations tab's Create/Rotate/Delete; off by default
```

New text:

```yaml
    writes:
      enabled: true      # off by default; ON here because the saTokenLookup stanza above WRITES its Secret
```

### 3.6 `local-development/gsd/config.py` — the settings, and the sentence this spec closes

**File:** `local-development/gsd/config.py` — edit

Old text:

```python
CREDENTIAL_PENDING_REASONS = {
    "oauth": "declares oauth (#119 P2, not built)",
    CREDENTIAL_LOOKUP: "declares saTokenLookup — the token lookup is S3b, not built; nothing has been obtained yet",
    CREDENTIAL_SELF_LOGIN: "declares userSelfLogin — the fleet login is S3b, not built; nothing has been obtained yet",
}
```

New text:

```python
CREDENTIAL_PENDING_REASONS = {
    "oauth": "declares oauth (#119 P2, not built)",
    CREDENTIAL_LOOKUP: "declares saTokenLookup — S3b's lookup has not retrieved a credential yet; the Cluster "
                       "Configurations tab's findings say why when it is late",
    CREDENTIAL_SELF_LOGIN: "declares userSelfLogin — the self-login mode is S3b's #285, not built; nothing has been obtained yet",
}
```

**File:** `local-development/gsd/config.py` — edit

Old text:

```python
    cluster_secrets_writes_enabled: bool = False
    cluster_registry: "ClusterRegistry" = field(default_factory=lambda: _registry(), compare=False, repr=False)
```

New text:

```python
    cluster_secrets_writes_enabled: bool = False
    # SPEC_S3 §3.1 / SPEC_S4b: the fleet account and the ADDRESS of its password (never the value —
    # read at connect time through the chart's one-Secret grant), and what saTokenLookup reads on
    # every target. `fleet_password_secret_namespace` empty means the pod's own namespace;
    # `sa_token_lookup_secret_name` empty means `<service account>-token`.
    fleet_account_username: str = ""
    fleet_password_secret_namespace: str = ""
    fleet_password_secret_name: str = "gsd-fleet-account"
    fleet_password_secret_key: str = "password"
    sa_token_lookup_namespace: str = "group-sync-operator"
    sa_token_lookup_service_account: str = "group-sync-dashboard-cluster-poller"
    sa_token_lookup_secret_name: str = ""
    # How many replicas the chart runs (ConfigMap `replicaCount`): the lookup refuses to run above one
    # without an elector, because every replica would log in (SPEC_S4 §6; review of #295, P0-2).
    replica_count: int = 1
    cluster_registry: "ClusterRegistry" = field(default_factory=lambda: _registry(), compare=False, repr=False)
```

**File:** `local-development/gsd/config.py` — edit

Old text:

```python
    """Env wins over the ConfigMap. Accepts the YAML spellings, not Python truthiness.

    ``bool("false")`` is True, so a plain cast would turn every explicit disable in an env
    var into an enable — silently, and in the direction that grants rather than withholds.
    """
    source = os.environ.get(env_name)
    if source is None:
        return bool(raw.get(yaml_key, default))
    word = source.strip().lower()
    if word in ("true", "yes", "on", "1"):
        return True
    if word in ("false", "no", "off", "0"):
        return False
    log.warning("%s=%r is not a boolean; using %r", env_name, source, default)
    return default
```

New text:

```python
    """Env wins over the ConfigMap. Accepts a real boolean or one of the YAML spellings, and NOTHING
    else, from either source.

    ``bool("false")`` is True, so a plain cast turned an explicit disable into an enable — silently,
    and in the direction that grants rather than withholds; the ConfigMap path did exactly that
    until review of #295 (P1-3), and then a number or a list still decided the switch by truthiness
    (`bool([False])` is True — second pass, R2-4). Anything that is not a boolean or a word is the
    default, and the warning names the source it came from. A null is an absent key.
    """
    source, where = os.environ.get(env_name), env_name
    if source is None:
        if raw.get(yaml_key) is None:
            return default
        source, where = raw[yaml_key], yaml_key
    if isinstance(source, bool):
        return source
    if isinstance(source, str):
        word = source.strip().lower()
        if word in ("true", "yes", "on", "1"):
            return True
        if word in ("false", "no", "off", "0"):
            return False
    log.warning("%s=%r is not a boolean; using %r", where, source, default)
    return default
```

**File:** `local-development/gsd/config.py` — edit

Old text:

```python
def _bool_setting(raw: dict, env_name: str, yaml_key: str, default: bool) -> bool:
```

New text:

```python
def _str_setting(raw: dict, env_name: str, yaml_key: str, default: str) -> str:
    """Env wins over the ConfigMap; an absent or null key is the default. Stripped, never None."""
    source = os.environ.get(env_name)
    if source is None:
        source = raw.get(yaml_key)
    return str(default if source is None else source).strip()


def _bool_setting(raw: dict, env_name: str, yaml_key: str, default: bool) -> bool:
```

**File:** `local-development/gsd/config.py` — edit

Old text:

```python
        cluster_secrets_writes_enabled=_bool_setting(raw, "GSD_CLUSTER_SECRETS_WRITES_ENABLED", "clusterSecretsWritesEnabled", False),
```

New text:

```python
        cluster_secrets_writes_enabled=_bool_setting(raw, "GSD_CLUSTER_SECRETS_WRITES_ENABLED", "clusterSecretsWritesEnabled", False),
        fleet_account_username=_str_setting(raw, "GSD_FLEET_ACCOUNT_USERNAME", "fleetAccountUsername", ""),
        fleet_password_secret_namespace=_str_setting(raw, "GSD_FLEET_PASSWORD_SECRET_NAMESPACE", "fleetPasswordSecretNamespace", ""),
        fleet_password_secret_name=_str_setting(raw, "GSD_FLEET_PASSWORD_SECRET_NAME", "fleetPasswordSecretName", "gsd-fleet-account"),
        fleet_password_secret_key=_str_setting(raw, "GSD_FLEET_PASSWORD_SECRET_KEY", "fleetPasswordSecretKey", "password"),
        sa_token_lookup_namespace=_str_setting(raw, "GSD_SA_TOKEN_LOOKUP_NAMESPACE", "saTokenLookupSourceNamespace", "group-sync-operator"),
        sa_token_lookup_service_account=_str_setting(raw, "GSD_SA_TOKEN_LOOKUP_SERVICE_ACCOUNT", "saTokenLookupSourceServiceAccount", "group-sync-dashboard-cluster-poller"),
        sa_token_lookup_secret_name=_str_setting(raw, "GSD_SA_TOKEN_LOOKUP_SECRET_NAME", "saTokenLookupTokenSecretName", ""),
        replica_count=_num_setting(raw, "GSD_REPLICA_COUNT", "replicaCount", 1, int),
```

The four existing tests that assert `"S3b" in credential_pending` (`tests/test_connection_modes.py`,
`tests/test_cluster_stanza_matrix.py`) pass unchanged: the issue's own label is S3b-B and the
sentence keeps it; only "not built" leaves.

### 3.7 `local-development/gsd/clusterconfig/__init__.py` — the closed set grows by eight

**File:** `local-development/gsd/clusterconfig/__init__.py` — edit

Old text:

```python
    "host-cluster-not-from-secret", "duplicate-cluster-name", "shadows-values-entry",
    "oauth-exchange-not-built", "discovery-failed",
)
```

New text:

```python
    "host-cluster-not-from-secret", "duplicate-cluster-name", "shadows-values-entry",
    "oauth-exchange-not-built", "discovery-failed",
    # SPEC_S4b (#284): the saTokenLookup lookup's findings, held per cluster by the registry until
    # the lookup succeeds. Each names its fix in `detail`; the tab renders code and detail as it does
    # every other finding.
    "fleet-credential-missing", "fleet-write-disabled", "login-refused", "login-failed",
    "sa-token-secret-missing", "sa-token-unreadable", "sa-token-invalidated", "lookup-write-failed",
)
```

### 3.8 `local-development/gsd/clusterconfig/reader.py` — the lookup's own Secret is not a shadow

OB1's proven fix (`review_s4/ob1/fix-reader.diff`, 204 passed), applied with this issue because it
has nothing to suppress until retrieval exists.

**File:** `local-development/gsd/clusterconfig/reader.py` — edit

Old text:

```python
from .parser import Finding, parse_secret
```

New text:

```python
from .parser import Finding, parse_secret
from .writer import TOKEN_SOURCE_ANNOTATION
```

**File:** `local-development/gsd/clusterconfig/reader.py` — edit

Old text:

```python
def discover(cluster_client, namespace: str, *, host_name: str | None,
             values_names: tuple[str, ...] = ()) -> tuple[list[ClusterConfig], list[Finding]]:
    path = f"/api/v1/namespaces/{namespace}/secrets"
```

New text:

```python
def discover(cluster_client, namespace: str, *, host_name: str | None,
             values_names: tuple[str, ...] = (),
             values_modes: dict[str, str] | None = None) -> tuple[list[ClusterConfig], list[Finding]]:
    """`values_modes` maps a values entry's name to the credential kind its declared connection mode
    resolves to (`remote-lookup` / `self-login`, SPEC_S3 §3). A Secret over such an entry whose
    `token-source` annotation names that same kind is the retriever's own write (SPEC_S4 §1) — the
    Secret is MEANT to win there, so it is not a shadow finding. Any other shadow still is."""
    path = f"/api/v1/namespaces/{namespace}/secrets"
```

**File:** `local-development/gsd/clusterconfig/reader.py` — edit

Old text:

```python
    parsed_ok: list[ClusterConfig] = []
    findings: list[Finding] = []
    for obj in items:
        parsed = parse_secret(obj, host_name=host_name)
        if isinstance(parsed, Finding):
            findings.append(parsed)
            continue
        parsed_ok.append(parsed)
```

New text:

```python
    parsed_ok: list[ClusterConfig] = []
    findings: list[Finding] = []
    token_source: dict[str, str | None] = {}   # Secret name -> its token-source annotation, if any
    for obj in items:
        parsed = parse_secret(obj, host_name=host_name)
        if isinstance(parsed, Finding):
            findings.append(parsed)
            continue
        meta = obj.get("metadata") or {}
        token_source[str(meta.get("name") or "")] = (meta.get("annotations") or {}).get(TOKEN_SOURCE_ANNOTATION)
        parsed_ok.append(parsed)
```

**File:** `local-development/gsd/clusterconfig/reader.py` — edit

Old text:

```python
        if parsed.name in values_names:
            findings.append(Finding(secret_name, "shadows-values-entry",
                                    f"{parsed.name} is also a values entry; the Secret wins"))
```

New text:

```python
        if parsed.name in values_names:
            # The retriever's own Secret over the stanza that asked for it is the design, not a
            # shadow (SPEC_S4 §1): the values entry declares the mode, the Secret says it came from it.
            ours = (values_modes or {}).get(parsed.name) is not None \
                and token_source.get(secret_name) == (values_modes or {}).get(parsed.name)
            if not ours:
                findings.append(Finding(secret_name, "shadows-values-entry",
                                        f"{parsed.name} is also a values entry; the Secret wins"))
```

### 3.9 `local-development/gsd/clusterconfig/registry.py` — a finding that outlives the cycle

**File:** `local-development/gsd/clusterconfig/registry.py` — edit

Old text:

```python
        self.last_discovery: str | None = None
        self.error: str | None = None
        self.namespace: str | None = None
```

New text:

```python
        self.last_discovery: str | None = None
        self.error: str | None = None
        self.namespace: str | None = None
        # SPEC_S4b: the lookup's standing finding per cluster, set by the retriever and cleared when
        # the lookup succeeds or the cluster stops being pending. Separate from `_findings`, which a
        # discovery replaces every cycle — a lookup finding must survive the cycles between attempts.
        self._lookups: dict[str, Finding] = {}
```

**File:** `local-development/gsd/clusterconfig/registry.py` — edit

Old text:

```python
    def findings(self) -> list[Finding]:
        with self._lock:
            out = list(self._findings)
            if self.error:
                out.append(Finding("-", "discovery-failed", self.error))
            return out
```

New text:

```python
    def findings(self) -> list[Finding]:
        with self._lock:
            out = list(self._findings)
            out.extend(self._lookups[name] for name in sorted(self._lookups))
            if self.error:
                out.append(Finding("-", "discovery-failed", self.error))
            return out

    def set_lookup_finding(self, cluster: str, finding: Finding | None) -> None:
        """The lookup's standing finding for one cluster (SPEC_S4b); None clears it."""
        with self._lock:
            if finding is None:
                self._lookups.pop(cluster, None)
            else:
                self._lookups[cluster] = finding
```

### 3.10 `local-development/gsd/clusterconfig/writer.py` — the values, and the in-place write

**File:** `local-development/gsd/clusterconfig/writer.py` — edit

Old text:

```python
from ..config import ClusterConfig
from ..config import CREDENTIAL_LOOKUP, CREDENTIAL_SELF_LOGIN
```

New text:

```python
from ..config import ClusterConfig
from ..config import CONNECTION_KEYS, CREDENTIAL_LOOKUP, CREDENTIAL_SELF_LOGIN
```

**File:** `local-development/gsd/clusterconfig/writer.py` — edit

Old text:

```python
MANAGED_BY_UI = "ui"
```

New text:

```python
MANAGED_BY_UI = "ui"
#: The saTokenLookup lookup (SPEC_S4b): the stanza key in kebab case, so `saTokenLookup: true` and
#: `managed-by: sa-token-lookup` read as one thing. Says WHO wrote the Secret; `token-source` says how.
MANAGED_BY_LOOKUP = "sa-token-lookup"
```

**File:** `local-development/gsd/clusterconfig/writer.py` — edit

Old text:

```python
SOURCE_SERVICE_ACCOUNT_ANNOTATION = "groupsync-dashboard.io/source-service-account"
```

New text:

```python
SOURCE_SERVICE_ACCOUNT_ANNOTATION = "groupsync-dashboard.io/source-service-account"
#: The account the lookup logged in AS (SPEC_S4b). A Secret that declared the mode is updated in
#: place and its `ldapConnectionBootstrap` must leave `config` with the mode key, so this is where
#: the per-cluster account survives for #285's re-login; written on the values path too.
LOOKUP_ACCOUNT_ANNOTATION = "groupsync-dashboard.io/lookup-account"
```

**File:** `local-development/gsd/clusterconfig/writer.py` — edit

Old text:

```python
    token_source: str | None = None
    source_namespace: str | None = None
    source_service_account: str | None = None
```

New text:

```python
    token_source: str | None = None
    source_namespace: str | None = None
    source_service_account: str | None = None
    lookup_account: str | None = None
```

**File:** `local-development/gsd/clusterconfig/writer.py` — edit

Old text:

```python
    labels = {SECRET_TYPE_LABEL: SECRET_TYPE_CLUSTER, **{str(k): str(v) for k, v in (req.labels or {}).items()}}
```

New text:

```python
    # THE TYPE LABEL IS STAMPED LAST, so no caller-supplied label can replace it (SPEC_S4b, the
    # operator's requirement): `validate()` refuses the app's prefix, but this function has callers
    # that do not validate — the lookup, and #293's ConfigMap feed whose labels someone else wrote —
    # and a Secret without `secret-type: cluster` is one discovery cannot see. Byte-identical for
    # every input `validate()` accepts.
    labels = {**{str(k): str(v) for k, v in (req.labels or {}).items()}, SECRET_TYPE_LABEL: SECRET_TYPE_CLUSTER}
```

**File:** `local-development/gsd/clusterconfig/writer.py` — edit

Old text:

```python
    for key, value in ((TOKEN_SOURCE_ANNOTATION, req.token_source),
                       (SOURCE_NAMESPACE_ANNOTATION, req.source_namespace),
                       (SOURCE_SERVICE_ACCOUNT_ANNOTATION, req.source_service_account)):
```

New text:

```python
    for key, value in ((TOKEN_SOURCE_ANNOTATION, req.token_source),
                       (SOURCE_NAMESPACE_ANNOTATION, req.source_namespace),
                       (SOURCE_SERVICE_ACCOUNT_ANNOTATION, req.source_service_account),
                       (LOOKUP_ACCOUNT_ANNOTATION, req.lookup_account)):
```

`rotate` is not touched: the in-place write is its own function, after `rotate`, and repeats the
fifteen lines of decode-and-PUT rather than refactoring shipped code inside a feature step.

**File:** `local-development/gsd/clusterconfig/writer.py` — edit

Old text:

```python
def delete(host_client: ClusterClient, namespace: str, name: str, *, viewer: str, cluster: str) -> None:
```

New text:

```python
def store_lookup(host_client: ClusterClient, namespace: str, name: str, *, token: str, cluster: str,
                 source_namespace: str, source_service_account: str, lookup_account: str) -> None:
    """SPEC_S4b: a Secret that DECLARED `saTokenLookup` becomes the credential it asked for, in place.

    Why in place and not a second Secret (SPEC_S4 §1): a Secret is named for its cluster and the
    reader fails closed on two Secrets for one cluster, so a `create` beside the declaring Secret is
    `secret-exists` and any other name is `duplicate-cluster-name` — neither loads. `config` becomes
    `{bearerToken, tlsClientConfig}`: the mode and bootstrap keys leave (the parser refuses them
    beside a credential) and the annotations keep the memory of the mode. `tlsClientConfig` is kept
    as declared — it is the trust that just verified both hosts. Labels and `managed-by` are kept:
    the lookup did not create this Secret. The decode refusal and the 409 are `rotate`'s, for the
    reasons stated there.
    """
    with host_client._client() as client:
        obj = _read_ours(host_client, client, namespace, name)
        data = obj.get("data") or {}
        try:
            config = json.loads(base64.b64decode(data.get("config") or "", validate=True).decode("utf-8"))
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            raise WriteRefused("config-not-json", f"Secret {name}: data.config does not decode to JSON ({type(exc).__name__}); "
                                                  "fix the Secret where it is written") from None
        if not isinstance(config, dict):
            raise WriteRefused("config-not-json", f"Secret {name}: data.config is not a JSON object; fix the Secret where it is written")
        for key in (*CONNECTION_KEYS, "oauth"):
            config.pop(key, None)
        config["bearerToken"] = token.strip()
        data["config"] = base64.b64encode(json.dumps(config, separators=(",", ":")).encode("utf-8")).decode("ascii")
        obj["data"] = data
        obj.pop("stringData", None)
        meta = obj.setdefault("metadata", {})
        meta["annotations"] = {**(meta.get("annotations") or {}),
                               TOKEN_SOURCE_ANNOTATION: TOKEN_SOURCE_LOOKUP,
                               SOURCE_NAMESPACE_ANNOTATION: source_namespace,
                               SOURCE_SERVICE_ACCOUNT_ANNOTATION: source_service_account,
                               LOOKUP_ACCOUNT_ANNOTATION: lookup_account}
        try:
            host_client._send(client, "PUT", _path(namespace, name), json=obj, secrets=(token, data["config"]))
        except ClusterError as exc:
            if exc.message.startswith("HTTP 409"):
                raise WriteRefused("secret-changed", f"Secret {name} changed since it was read — GitOps or another "
                                                     "writer got there first; the next attempt reads it again", conflict=True) from exc
            raise _failed(exc, token, data["config"]) from exc
    event(log, logging.INFO, "cluster-secret-rotated", secret=name, namespace=namespace, cluster=cluster,
          by=MANAGED_BY_LOOKUP, secrets=(token,))


def delete(host_client: ClusterClient, namespace: str, name: str, *, viewer: str, cluster: str) -> None:
```

**File:** `local-development/gsd/clusterconfig/writer.py` — edit

Old text:

```python
__all__ = ["CreateRequest", "WriteRefused", "WriteFailed", "SECRET_NAME_PREFIX", "MANAGED_BY_ANNOTATION",
           "TOKEN_SOURCE_ANNOTATION", "SOURCE_NAMESPACE_ANNOTATION", "SOURCE_SERVICE_ACCOUNT_ANNOTATION",
           "TOKEN_SOURCE_LOOKUP", "TOKEN_SOURCE_SELF_LOGIN",
           "TLS_MODES", "OAUTH_NOT_BUILT", "secret_object", "secret_name_for", "validate", "create", "rotate",
           "delete", "test_connection", "AUTH_FAILED", "UNREACHABLE"]
```

New text:

```python
__all__ = ["CreateRequest", "WriteRefused", "WriteFailed", "SECRET_NAME_PREFIX", "MANAGED_BY_ANNOTATION",
           "MANAGED_BY_UI", "MANAGED_BY_LOOKUP",
           "TOKEN_SOURCE_ANNOTATION", "SOURCE_NAMESPACE_ANNOTATION", "SOURCE_SERVICE_ACCOUNT_ANNOTATION",
           "LOOKUP_ACCOUNT_ANNOTATION", "TOKEN_SOURCE_LOOKUP", "TOKEN_SOURCE_SELF_LOGIN",
           "TLS_MODES", "OAUTH_NOT_BUILT", "secret_object", "secret_name_for", "validate", "create", "rotate",
           "store_lookup", "delete", "test_connection", "AUTH_FAILED", "UNREACHABLE"]
```

### 3.11 `local-development/gsd/fleetlogin.py` — a failure names its host

The only change to #283's module: `LoginError` learns which host a transport failure was against,
so a trust failure can say *the OAuth route* or *the API host*. Five edits, no new behaviour.

**File:** `local-development/gsd/fleetlogin.py` — edit

Old text:

```python
    def __init__(self, outcome: str, message: str, *, phase: str, retryable: bool):
        super().__init__(outcome, message)
        self.phase = phase
        self.retryable = retryable
        self.attempts = 0
```

New text:

```python
    def __init__(self, outcome: str, message: str, *, phase: str, retryable: bool, host: str | None = None,
                 bound: bool = False):
        super().__init__(outcome, message)
        self.phase = phase
        self.retryable = retryable
        self.attempts = 0
        #: The host a TRANSPORT failure was against — the API host (discovery) or the OAuth route
        #: (authorize) — so a trust failure names which of the two the bundle does not cover
        #: (SPEC_S4b; the split-CA estate of SPEC_S4a §2.1). None for an answer, which names its own.
        self.host = host
        #: THE LINE THE MODULE DOCSTRING DRAWS, AS A FIELD: the password was on the wire. True for every
        #: answer the target gave (`phase=credential`) and for a transport failure AFTER the authorize
        #: GET was written (a read timeout, a dropped connection), so a caller that schedules logins
        #: (SPEC_S4b) can refuse to bind again — a locked account answers 500, and re-entering the
        #: login from outside is the lockout walk one layer up (review of #295, P0-1).
        self.bound = bound or phase == "credential"
```

**File:** `local-development/gsd/fleetlogin.py` — edit

Old text:

```python
        try:
            response = self._client.get(DISCOVERY_PATH, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            raise self._transport_error(exc) from exc
```

New text:

```python
        try:
            response = self._client.get(DISCOVERY_PATH, headers={"Accept": "application/json"})
        except httpx.HTTPError as exc:
            # The API host, userinfo stripped structurally: a values apiUrl may carry one.
            raise self._transport_error(exc, host=urlsplit(_without_userinfo(self.cluster.api_url) or "").netloc or None) from exc
```

**File:** `local-development/gsd/fleetlogin.py` — edit

Old text:

```python
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # Provably before the password bytes were written: the target cannot have bound.
            raise self._transport_error(exc) from exc
        except httpx.HTTPError as exc:
            # The request may have been written and the target may have bound — a read timeout, a
            # dropped connection, a non-HTTP answer: terminal.
            raise self._transport_error(exc, retryable=False) from exc
```

New text:

```python
        except (httpx.ConnectError, httpx.ConnectTimeout) as exc:
            # Provably before the password bytes were written: the target cannot have bound.
            raise self._transport_error(exc, host=urlsplit(endpoint).netloc) from exc
        except httpx.HTTPError as exc:
            # The request may have been written and the target may have bound — a read timeout, a
            # dropped connection, a non-HTTP answer: terminal.
            raise self._transport_error(exc, retryable=False, host=urlsplit(endpoint).netloc, bound=True) from exc
```

**File:** `local-development/gsd/fleetlogin.py` — edit

Old text:

```python
    def _transport_error(self, exc: httpx.HTTPError, *more: str | None, retryable: bool = True) -> LoginError:
```

New text:

```python
    def _transport_error(self, exc: httpx.HTTPError, *more: str | None, retryable: bool = True,
                         host: str | None = None, bound: bool = False) -> LoginError:
```

**File:** `local-development/gsd/fleetlogin.py` — edit

Old text:

```python
        phase = "tls" if is_verify_failure(raw) else "connect"
        return LoginError(UNREACHABLE, self._scrub(raw, *more), phase=phase, retryable=retryable)
```

New text:

```python
        phase = "tls" if is_verify_failure(raw) else "connect"
        return LoginError(UNREACHABLE, self._scrub(raw, *more), phase=phase, retryable=retryable, host=host, bound=bound)
```

**File:** `local-development/gsd/fleetlogin.py` — edit

Old text:

```python
        failure(log, "fleet-login-failed", phase=exc.phase, outcome=exc.outcome, **self._fields(),
                attempt=f"{attempt}/{ceiling}", retry_in=None if retry_in is None else f"{retry_in:g}",
```

New text:

```python
        failure(log, "fleet-login-failed", phase=exc.phase, outcome=exc.outcome, **self._fields(), host=exc.host,
                attempt=f"{attempt}/{ceiling}", retry_in=None if retry_in is None else f"{retry_in:g}",
```

**File:** `local-development/gsd/fleetlogin.py` — edit

Old text:

```python
        failure(log, "fleet-login-failed", phase=exc.phase, outcome=exc.outcome, **self._fields(),
                action="not retried: fix what detail names before the next lookup or ping",
```

New text:

```python
        failure(log, "fleet-login-failed", phase=exc.phase, outcome=exc.outcome, **self._fields(), host=exc.host,
                action="not retried: fix what detail names before the next lookup or ping",
```

### 3.12 `local-development/gsd/fleetlookup.py` — new module: the lookup

```python
"""Retrieve a cluster's credential as the fleet account — the lookup of #284 (SPEC_S4b).

THE LOOP, and this module is its one missing stage: a values stanza (or a Secret) declares
`saTokenLookup: true`; this module logs in to that cluster as the fleet account (`gsd/fleetlogin.py`,
#283), reads the poller ServiceAccount's PERMANENT token from its `kubernetes.io/service-account-token`
Secret there — one GET, by name, the only read the estate's `resourceNames` grant allows — and hands
the token to the shipped writer, which produces `gsd-cluster-<name>` in this release's namespace with
the discovery label on it. Discovery then polls the cluster like any other. Two identities, neither
granted anything on the other side: the LDAP account reads REMOTELY, the pod's ServiceAccount writes
LOCALLY.

WHAT IS WRITTEN IS THE VALUES, NOT THE SHAPE (chart 0.49.0 ships the shape): `token-source`
remote-lookup, the source namespace and ServiceAccount, `managed-by` sa-token-lookup, and the account
the login used. The Secret's trust is the DECLARATION's — a `caBundleFile`, a declaring Secret's
`caData`, `insecure`, or the trusted bundle — because that bundle just verified BOTH hosts the login
touches (the API host and the OAuth route), and the target's own `ca.crt` verifies only the first.

NOTHING HERE REVOKES. The stored token is the target's and dies only with its Secret; the login's
own token is revoked by `FleetLogin.__exit__` on every path, including a failed read.

THE ONE-YEAR FUSE, read rather than assumed: Kubernetes' legacy-token cleaner stamps
`kubernetes.io/legacy-token-invalid-since` on an AUTO-GENERATED token Secret (one the ServiceAccount's
`.secrets` references) unused for `--legacy-service-account-token-clean-up-period` (8760h), and the
API server then refuses the token. A manually created Secret is not referenced and is never stamped;
one that carries the label is already dead, and storing it would be a 401 on the first poll.

`lookup(..., write=False)` is #285's daily ping: the same login, read and revoke, and nothing stored.
"""

from __future__ import annotations

import base64
import binascii
import dataclasses
import hashlib
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .clusterconfig.writer import (
    MANAGED_BY_LOOKUP, TOKEN_SOURCE_LOOKUP, CreateRequest, WriteFailed, WriteRefused, create, secret_name_for,
    store_lookup,
)
from .clusterconfig.events import is_transport_message, redact
from .config import ClusterConfig, Settings
from .fleetlogin import FleetLogin, LoginError
from .kube import AUTH_FAILED, ClusterClient, ClusterError, redact_text

log = logging.getLogger(__name__)

SA_TOKEN_SECRET_TYPE = "kubernetes.io/service-account-token"
SA_NAME_ANNOTATION = "kubernetes.io/service-account.name"
#: Stamped by the API server on every use of a legacy token (pkg/serviceaccount/legacy.go, Validate).
LAST_USED_LABEL = "kubernetes.io/legacy-token-last-used"
#: Stamped by the cleaner on an auto-generated token unused for the period; the token is refused after.
INVALID_SINCE_LABEL = "kubernetes.io/legacy-token-invalid-since"
#: The schedule the poller runs this under (SPEC_S4b, orchestrator's notes): a failure that SPENT a
#: login counts, `attempt=n/5`, the next try binding_interval × 2^(n−1) later, capped at a day, then
#: gave up out loud until the declaration changes, the pod restarts or #285 re-arms it.
LOOKUP_ATTEMPTS = 5
LOOKUP_WAIT_CAP = 86400.0
#: Every finding code this module raises; each is in `clusterconfig.FINDING_CODES`.
CODES = ("fleet-credential-missing", "fleet-write-disabled", "login-refused", "login-failed",
         "sa-token-secret-missing", "sa-token-unreadable", "sa-token-invalidated", "lookup-write-failed")


class LookupRefused(Exception):
    """One step of the lookup refused, typed as the finding it becomes.

    `code` is in CODES; `detail` says what happened and `action` what to change (#245: the fix, not
    the diagnosis), neither ever a credential; `spent` is whether a login was attempted — the
    poller's schedule counts spent failures and rechecks the free ones every cycle; `secrets` are
    the values in play, for the emit helper to strip from the line the poller writes.
    """

    def __init__(self, code: str, detail: str, *, action: str, spent: bool, secrets: tuple[str, ...] = ()):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.action, self.spent = code, detail, action, spent
        self.secrets: tuple[str, ...] = tuple(secrets)

    def scrub(self, secrets: list[str]) -> None:
        """Every secret in play out of `detail`, `action` AND `args` — `str(exc)` is what a caller
        that did not read the fields prints (review of #295, P1-1)."""
        self.secrets = tuple(v for v in (*self.secrets, *secrets) if v)
        self.detail, self.action = _scrub(self.detail, list(self.secrets)), _scrub(self.action, list(self.secrets))
        self.args = (f"{self.code}: {self.detail}",)


class CredentialGate:
    """SPEC_S4 §6's in-memory half: a password a target evaluated — or may have — is never sent to
    THAT target again while it is the same password. Keyed on (target, username, sha256(password)):
    the target, because a 500 from one cluster must not stop a healthy one on the same account
    (review of #295, second pass, R2-1); the digest, because the password is not in the declaration,
    so the normal fix — rotating the Secret — changes no stanza and must re-arm this by itself.
    Best-effort and per process; the durable, replica-shared gate is #285's."""

    def __init__(self) -> None:
        self._refused: set[tuple[str, str, str]] = set()

    @staticmethod
    def _key(target: str, username: str, password: str) -> tuple[str, str, str]:
        return target.rstrip("/"), username, hashlib.sha256(password.encode("utf-8")).hexdigest()[:16]

    def refused(self, target: str, username: str, password: str) -> bool:
        return self._key(target, username, password) in self._refused

    def refuse(self, target: str, username: str, password: str) -> None:
        self._refused.add(self._key(target, username, password))


@dataclass(frozen=True)
class LookupSource:
    """Where the token is read on every target — one convention for the fleet (the operator chart's)."""

    namespace: str
    service_account: str
    secret_name: str

    @classmethod
    def from_settings(cls, settings: Settings) -> LookupSource:
        sa = settings.sa_token_lookup_service_account
        return cls(settings.sa_token_lookup_namespace, sa, settings.sa_token_lookup_secret_name or f"{sa}-token")


@dataclass(frozen=True)
class SaToken:
    """What the target's Secret held: the token, whose it is, and the cleaner's last-used stamp."""

    token: str = field(repr=False, compare=False)
    namespace: str = ""
    service_account: str = ""
    secret_name: str = ""
    last_used: str | None = None


@dataclass(frozen=True)
class LookupResult:
    cluster: str
    account: str
    sa_token: SaToken
    secret: str
    written: str | None
    """`created` (a values stanza), `updated` (a declaring Secret), or None when `write=False`."""
    secrets: tuple[str, ...] = field(repr=False, compare=False, default=())


def _status_only(message: str) -> str:
    """A `ClusterError` message without any remote body: `HTTP 500 on /path: <body>` becomes
    `HTTP 500 on /path`. A body is remote-controlled and can carry the very token this lookup is
    reading, which was never decoded and so is not among the secrets a refusal is scrubbed against
    (review of #295, second pass, R2-3). A transport message is this process's own words and is kept."""
    return message if is_transport_message(message) else message.split(": ", 1)[0]


def _scrub(text: str, secrets: list[str]) -> str:
    """Every secret in play out of free text, in the spellings the two helpers know and then, whatever
    its length, the raw value — `fleetlogin.FleetLogin._scrub`'s rule, applied at this module's one
    boundary rather than at every quoting site."""
    values = tuple(v for v in secrets if v)
    out = redact(redact_text(text, *values), values)
    for value in sorted(values, key=len, reverse=True):
        out = out.replace(value, "<redacted>")
    return out


def fleet_account(settings: Settings, cluster: ClusterConfig) -> str:
    """The stanza's `ldapConnectionBootstrap`, else the chart's fleet username (SPEC_S3 §3.1 rule 1)."""
    username = cluster.ldap_connection_bootstrap or settings.fleet_account_username
    if not username:
        raise LookupRefused("fleet-credential-missing", f"no fleet account is named for {cluster.name}",
                            action=("set clusterConfig.fleetAccount.username, or ldapConnectionBootstrap on the "
                                    "cluster's stanza"), spent=False)
    return username


def fleet_password(host_client: ClusterClient, settings: Settings, own_namespace: str) -> str:
    """The password, read now through the chart's one-Secret grant (`templates/fleet-account-rbac.yaml`);
    never held on Settings or ClusterConfig, so `poller._credentials` never sees it."""
    ns = settings.fleet_password_secret_namespace or own_namespace
    name, key = settings.fleet_password_secret_name, settings.fleet_password_secret_key
    where = f"Secret {ns}/{name} key {key!r}"
    action = ("put the fleet account's password in that Secret and key (clusterConfig.fleetAccount.passwordSecret), "
              "and let the chart render its grant (passwordSecret.rbac.create) or grant get on it by hand")
    try:
        with host_client._client() as client:
            obj = host_client._get(client, f"/api/v1/namespaces/{ns}/secrets/{name}", {})
    except ClusterError as exc:
        raise LookupRefused("fleet-credential-missing", f"cannot read {where}: {exc.outcome}: {_status_only(exc.message)}",
                            action=action, spent=False) from exc
    try:
        password = base64.b64decode((obj.get("data") or {}).get(key) or "", validate=True).decode("utf-8").strip()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        password = ""
    if not password:
        raise LookupRefused("fleet-credential-missing", f"{where} is absent or empty", action=action, spent=False)
    return password


def read_sa_token(session_token: str, cluster: ClusterConfig, source: LookupSource, *, timeout: float) -> SaToken:
    """GET the token Secret on the TARGET as the session — the read #285's ping reuses.

    `ClusterClient` with the session as the credential: the same TLS decision as the login
    (`ClusterConfig.verify()`), the same outcome words, and its own token scrubbed from what it
    quotes. The Secret is read BY NAME with `get` — the estate grants `get` on that one Secret by
    `resourceNames` and refuses `list`, and a manually created token Secret is not in the
    ServiceAccount's `.secrets`, so neither a list nor the SA can find it (measured, SPEC_S4b §2).
    """
    as_session = dataclasses.replace(cluster, token_value=session_token, sa_token_lookup=False,
                                     user_self_login=False, ldap_connection_bootstrap=None)
    path = f"/api/v1/namespaces/{source.namespace}/secrets/{source.secret_name}"
    where = f"Secret {source.namespace}/{source.secret_name} on {cluster.name}"
    reader = ClusterClient(as_session, timeout=timeout)
    try:
        with reader._client() as client:
            obj = reader._get(client, path, {})
    except ClusterError as exc:
        if exc.message.startswith("HTTP 404"):
            raise LookupRefused(
                "sa-token-secret-missing", f"{where} does not exist",
                action=(f"create the token Secret on the target: OpenShift 4.16+ and Kubernetes 1.24+ no longer "
                        f"create one, so it is an onboarding step — a kubernetes.io/service-account-token Secret "
                        f"named {source.secret_name} annotated {SA_NAME_ANNOTATION}={source.service_account}, "
                        f"which the control plane then fills"), spent=True) from exc
        raise LookupRefused("sa-token-unreadable", f"{where}: {exc.outcome}: {_status_only(exc.message)}",
                            action=("grant the fleet account get on that one Secret on the target (resourceNames), "
                                    "and check the ServiceAccount and Secret names in clusterConfig.saTokenLookup"),
                            spent=True) from exc
    meta = obj.get("metadata") or {}
    labels, annotations = meta.get("labels") or {}, meta.get("annotations") or {}
    # THE TOKEN IS DECODED FIRST (review of #295, P1-1): whatever this function refuses below, the
    # token the Secret carried rides the refusal's `secrets`, so no quoted field can carry it out.
    # `TypeError` too (second pass, R2-3): a non-scalar `data.token` must be a refusal, not a crash
    # in front of the refusals this decode exists to feed.
    try:
        token = base64.b64decode((obj.get("data") or {}).get("token") or "", validate=True).decode("utf-8").strip()
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError):
        token = ""
    carried = (token,) if token else ()
    # A remote-controlled NAME is described by its length, never echoed — the parser's rule for a key
    # this contract does not know (`parser._unknown_key`), applied to the type and the owner.
    kind = obj.get("type")
    if kind != SA_TOKEN_SECRET_TYPE:
        raise LookupRefused("sa-token-unreadable", f"{where} is not type {SA_TOKEN_SECRET_TYPE} (its type is "
                                                   f"{len(str(kind or ''))} characters long); not stored",
                            action="point clusterConfig.saTokenLookup.tokenSecretName at the ServiceAccount's token Secret",
                            spent=True, secrets=carried)
    owner = annotations.get(SA_NAME_ANNOTATION)
    if owner != source.service_account:
        raise LookupRefused("sa-token-unreadable", f"{where} is not {source.service_account!r}'s: its "
                                                   f"{SA_NAME_ANNOTATION} annotation is {len(str(owner or ''))} characters "
                                                   f"long and does not match; not stored",
                            action="check clusterConfig.saTokenLookup.sourceServiceAccount against the Secret's annotation",
                            spent=True, secrets=carried)
    if INVALID_SINCE_LABEL in labels:
        # PRESENCE, not truthiness (review of #295, P1-5): Kubernetes allows an empty label value.
        raise LookupRefused("sa-token-invalidated", f"{where} carries the {INVALID_SINCE_LABEL} label: the target's "
                                                    f"legacy-token cleaner invalidated it after a year unused and the API "
                                                    f"server refuses it; not stored",
                            action=("delete and recreate the token Secret on the target (the control plane fills the new "
                                    "one), or remove that label to allow the token temporarily"), spent=True, secrets=carried)
    if not token:
        raise LookupRefused("sa-token-unreadable", f"{where} has no token yet",
                            action="the token controller fills a new Secret within seconds; nothing to do unless it stays empty",
                            spent=True)
    return SaToken(token=token, namespace=source.namespace, service_account=source.service_account,
                   secret_name=source.secret_name, last_used=labels.get(LAST_USED_LABEL))


def declared_trust(cluster: ClusterConfig) -> tuple[str, str | None]:
    """(tls_mode, ca_data) for the Secret the values path writes: THE DECLARATION'S trust, verbatim.

    It is the bundle that just verified the API host (discovery) and the OAuth route (authorize), so
    it is proven for the poll and for a re-login alike; the target's `ca.crt` verifies only the API
    host and is deliberately not written (SPEC_S4b, orchestrator's notes).
    """
    if cluster.insecure_skip_verify:
        return "insecure", None
    if cluster.ca_bundle_file:
        try:
            return "caData", base64.b64encode(Path(cluster.ca_bundle_file).read_bytes()).decode("ascii")
        except OSError as exc:
            raise LookupRefused("lookup-write-failed", f"cannot read caBundleFile {cluster.ca_bundle_file!r}: {exc}",
                                action="fix the caBundleFile the stanza names", spent=True) from exc
    return "trustedBundle", None


def store(host_client: ClusterClient, own_namespace: str, cluster: ClusterConfig, settings: Settings,
          sa_token: SaToken, *, account: str) -> str:
    """Write the credential where the declaration says (SPEC_S4 §1): a values stanza gets a new
    `gsd-cluster-<name>` through `writer.create`; a declaring Secret is updated in place through
    `writer.store_lookup`. Returns `created` or `updated`."""
    provenance = dict(source_namespace=sa_token.namespace, source_service_account=sa_token.service_account,
                      lookup_account=account)
    try:
        if cluster.source.startswith("secret:"):
            store_lookup(host_client, own_namespace, cluster.source.split(":", 1)[1], token=sa_token.token,
                         cluster=cluster.name, **provenance)
            return "updated"
        tls_mode, ca_data = declared_trust(cluster)
        visibility, identity = settings.cluster_policy(cluster.name)
        req = CreateRequest(name=cluster.name, server=cluster.api_url, credential_kind="bearerToken",
                            token=sa_token.token, tls_mode=tls_mode, ca_data=ca_data,
                            visibility=visibility, identity=identity, enabled=cluster.enabled,
                            managed_by=MANAGED_BY_LOOKUP, token_source=TOKEN_SOURCE_LOOKUP, **provenance)
        # `taken` without this cluster: the stanza IS the entry the Secret is written for.
        taken = {c.name: c.source for c in settings.effective_clusters() if c.name != cluster.name}
        host = settings.host_cluster()
        create(host_client, own_namespace, req, host_name=host.name if host else None, taken=taken,
               viewer=MANAGED_BY_LOOKUP)
        return "created"
    except WriteRefused as exc:
        raise LookupRefused("lookup-write-failed", f"{exc.code}: {exc.detail}",
                            action=("fix or delete the Secret named, then the next attempt writes it — the credential was "
                                    "read and not stored"), spent=True) from exc
    except WriteFailed as exc:
        raise LookupRefused("lookup-write-failed", f"{exc.outcome}: {exc.message}",
                            action="check the write grant (clusterConfig.secrets.writes.enabled) and the API server", spent=True) from exc


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
        # #285's ping with write=True, #293's feed — must not bypass it. Before any password is read.
        raise LookupRefused("fleet-write-disabled", f"{cluster.name} declares saTokenLookup but this deployment does not "
                                                    f"write cluster Secrets",
                            action=("set clusterConfig.secrets.writes.enabled: true (and secrets.enabled) — the lookup "
                                    f"writes {secret_name_for(cluster.name)}, and create/update on Secrets is the grant "
                                    "that switch renders"), spent=False)
    source = LookupSource.from_settings(settings)
    account = fleet_account(settings, cluster)
    password = fleet_password(host_client, settings, own_namespace)
    secrets: list[str] = [password]
    try:
        if gate.refused(cluster.api_url, account, password):
            raise LookupRefused("login-refused", f"{cluster.name} evaluated this password for {account} already and it "
                                                 f"has not changed",
                                action=("rotate the fleet password Secret, or correct ldapConnectionBootstrap — no login is "
                                        "attempted against this target until the password moves (SPEC_S4 §6)"), spent=False)
        knobs = {"clock": clock} if clock is not None else {}
        try:
            with FleetLogin(cluster, account, password, timeout=settings.request_timeout_seconds, sleep=sleep, **knobs) as session:
                secrets.append(session.token)
                sa_token = read_sa_token(session.token, cluster, source, timeout=settings.request_timeout_seconds)
        except LoginError as exc:
            which = f" against {exc.host}" if exc.host else ""
            if exc.bound:
                # THE PASSWORD WAS ON THE WIRE. The target evaluated it — refused it (401), answered
                # 500 (what the oauth-server says for every directory result but 48/49, a LOCKED
                # account's code 19 included), answered without a token — or may have: a read timeout
                # after the GET was written. Never sent to THIS target again while it is this password
                # (review of #295, P0-1 and second pass R2-1): re-entering #283's terminal answer from a
                # schedule is the lockout walk one layer up, and an in-memory "final" that any shape
                # change re-arms is not a stop. `AUTH_FAILED` is the refusal's word; the rest read as failed.
                gate.refuse(cluster.api_url, account, password)
                code = "login-refused" if exc.outcome == AUTH_FAILED else "login-failed"
                raise LookupRefused(code, f"phase={exc.phase}{which}: {exc.message}",
                                    action=(f"the password for {account} was sent to {cluster.name} and no session came "
                                            f"back: rotate the fleet password Secret or correct ldapConnectionBootstrap, "
                                            f"or check the account is not locked — it is not sent there again while it "
                                            f"is the same password"), spent=True) from exc
            hint = ""
            if exc.phase == "tls":
                hint = (" — the stanza's CA must verify BOTH the API host and the OAuth route (the ingress CA, "
                        "which the API's bundle may not carry)")
            # Before the write — the socket never opened or the handshake failed: nothing was bound,
            # and the schedule may try again.
            raise LookupRefused("login-failed", f"phase={exc.phase}{which}: {exc.message}",
                                action=f"fix what detail names on the target or the stanza{hint}", spent=True) from exc
        secrets.append(sa_token.token)
        written = store(host_client, own_namespace, cluster, settings, sa_token, account=account) if write else None
    except LookupRefused as exc:
        # The boundary every refusal crosses: whatever a step quoted — a remote annotation, an API
        # server's echo — leaves here without the password, the session or the token in it (the
        # token a refused read carried rides `exc.secrets` already), and the poller's line is handed
        # the same values to strip again.
        exc.scrub(secrets)
        raise
    return LookupResult(cluster=cluster.name, account=account, sa_token=sa_token, secret=secret_name_for(cluster.name),
                        written=written, secrets=tuple(secrets))


__all__ = ["CODES", "LOOKUP_ATTEMPTS", "LOOKUP_WAIT_CAP", "CredentialGate", "LookupRefused", "LookupResult",
           "LookupSource", "SaToken", "declared_trust", "fleet_account", "fleet_password", "lookup", "read_sa_token",
           "store"]
```

### 3.13 `local-development/gsd/poller.py` — the schedule

**File:** `local-development/gsd/poller.py` — edit

Old text:

```python
import logging
import os
import threading
import time
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from .config import IDENTITY_NONE, VISIBILITY_SELF_ONLY, ClusterConfig, ConfigError, Settings
```

New text:

```python
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from .config import CREDENTIAL_LOOKUP, IDENTITY_NONE, VISIBILITY_SELF_ONLY, ClusterConfig, ConfigError, Settings
```

**File:** `local-development/gsd/poller.py` — edit

Old text:

```python
#: The last token each cluster resolved, kept for redaction alone. SEE `_credentials` — this is a
```

New text:

```python
@dataclass
class _LookupState:
    """One cluster's place in the lookup schedule (SPEC_S4b). `key` is what re-arms it."""

    key: tuple = ()
    attempts: int = 0
    not_before: float = 0.0
    gave_up: bool = False
    last_code: str | None = None

    def reset(self, key: tuple) -> None:
        self.key, self.attempts, self.not_before, self.gave_up, self.last_code = key, 0, 0.0, False, None


#: The last token each cluster resolved, kept for redaction alone. SEE `_credentials` — this is a
```

**File:** `local-development/gsd/poller.py` — edit

Old text:

```python
        self._backup_state = "pending"
        self._prune_held_logged = False
```

New text:

```python
        self._backup_state = "pending"
        self._prune_held_logged = False
        # SPEC_S4b (#284): the saTokenLookup schedule — one state per pending cluster, and the gate
        # that keeps a refused password off the wire. Both belong to the discovery thread, which is
        # the one retriever per estate (SPEC_S4 §6); the API reads the resulting findings from the
        # registry, never from here.
        from .fleetlookup import CredentialGate
        self._lookups: dict[str, _LookupState] = {}
        self._credential_gate = CredentialGate()
```

**File:** `local-development/gsd/poller.py` — edit

Old text:

```python
        try:
            clusters, findings = discover(
                ClusterClient(host, timeout=self.settings.request_timeout_seconds), namespace,
                host_name=host.name, values_names=tuple(c.name for c in self.settings.clusters))
```

New text:

```python
        try:
            clusters, findings = discover(
                ClusterClient(host, timeout=self.settings.request_timeout_seconds), namespace,
                host_name=host.name, values_names=tuple(c.name for c in self.settings.clusters),
                # A values stanza that declares a mode expects the retriever's Secret over it
                # (SPEC_S4 §1); the reader keeps that one out of `shadows-values-entry`.
                values_modes={c.name: c.credential_kind for c in self.settings.clusters
                              if c.connection_mode is not None})
```

**File:** `local-development/gsd/poller.py` — edit

Old text:

```python
    def request_discovery(self) -> None:
        """Wake the discovery thread now (SPEC_S2 notes): a Secret the tab just wrote is discovered within
        seconds instead of on the next cadence tick. A GitOps-written Secret still rides the cadence."""
        self._discover_now.set()
```

New text:

```python
    def request_discovery(self) -> None:
        """Wake the discovery thread now (SPEC_S2 notes): a Secret the tab just wrote is discovered within
        seconds instead of on the next cadence tick. A GitOps-written Secret still rides the cadence."""
        self._discover_now.set()

    # ── SPEC_S4b (#284): the saTokenLookup lookup ────────────────────────────────────────────────

    def _lookup_key(self, cluster: ClusterConfig) -> tuple:
        """What re-arms a lookup that gave up: the declaration (its shape) or the fleet credential's
        ADDRESS. The password's VALUE re-arms through the gate instead (`CredentialGate`)."""
        s = self.settings
        return (_cluster_shape(cluster), cluster.ldap_connection_bootstrap or s.fleet_account_username,
                s.fleet_password_secret_namespace, s.fleet_password_secret_name, s.fleet_password_secret_key)

    def _retrieve_pending(self) -> None:
        """One pass over every enabled cluster still awaiting its lookup, on the discovery thread,
        after discovery: the cluster that is due is retrieved, the one that is not is skipped, and a
        write wakes discovery so the cluster polls within seconds rather than at the next cadence."""
        from .clusterconfig.events import event
        from .clusterconfig.writer import secret_name_for
        from .fleetlookup import LOOKUP_ATTEMPTS, LookupRefused, lookup
        registry = self.settings.cluster_registry
        pending = {c.name: c for c in self.settings.effective_clusters()
                   if c.enabled and c.credential_kind == CREDENTIAL_LOOKUP}
        for name in [n for n in self._lookups if n not in pending]:
            # retrieved, disabled or gone: its state and its finding go with it
            self._lookups.pop(name)
            registry.set_lookup_finding(name, None)
        if not pending or (self.elector is not None and not self.elector.is_leader):
            return
        host, namespace = self.settings.host_cluster(), own_namespace()
        if host is None or not namespace:
            return    # `_discover_once` announced it
        # ONE RETRIEVER PER ESTATE (SPEC_S4 §6), the runtime half: above one replica election is off, so
        # `elector` is None and every replica would reach here — and a Secret-declared mode is invisible
        # to the render's refusal (review of #295, P0-2). The switch itself is checked inside `lookup`.
        many = self.elector is None and self.settings.replica_count > 1
        for name, cluster in pending.items():
            state = self._lookups.setdefault(name, _LookupState())
            key = self._lookup_key(cluster)
            if state.key != key:
                state.reset(key)
            now = time.monotonic()
            if state.gave_up or now < state.not_before:
                continue
            secret = secret_name_for(name)
            if many:
                self._lookup_failed(state, name, secret, LookupRefused(
                    "fleet-write-disabled", f"{name} declares saTokenLookup on a release of {self.settings.replica_count} "
                                            f"replicas without leader election: every replica would log in as the fleet account",
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
                  written=result.written, source=f"{result.sa_token.namespace}/{result.sa_token.service_account}",
                  last_used=result.sa_token.last_used, attempt=f"{state.attempts + 1}/{LOOKUP_ATTEMPTS}",
                  secrets=result.secrets)
            self._discover_now.set()

    def _lookup_failed(self, state: _LookupState, name: str, secret: str, exc, now: float) -> None:
        """Record the finding, place the cluster on the schedule, and say so — once for a failure
        that spent nothing (rechecked every cycle), every attempt for one that spent a login."""
        from .clusterconfig.events import failure
        from .clusterconfig.parser import Finding
        from .fleetlookup import LOOKUP_ATTEMPTS, LOOKUP_WAIT_CAP
        self.settings.cluster_registry.set_lookup_finding(name, Finding(secret, exc.code, f"{exc.detail} — {exc.action}"))
        if not exc.spent:
            if state.last_code != exc.code:
                state.last_code = exc.code
                failure(discovery_log, "fleet-lookup-failed", phase="credential", outcome=exc.code, cluster=name,
                        secret=secret, action=exc.action, detail=exc.detail, secrets=exc.secrets)
            state.not_before = now
            return
        state.attempts += 1
        state.last_code = exc.code
        state.gave_up = state.attempts >= LOOKUP_ATTEMPTS
        wait = None if state.gave_up else min(self.settings.binding_interval_seconds * (2 ** (state.attempts - 1)), LOOKUP_WAIT_CAP)
        state.not_before = now if wait is None else now + wait
        action = exc.action if not state.gave_up else (
            f"gave up after {LOOKUP_ATTEMPTS} attempts: nothing more is tried until the stanza or the fleet credential "
            f"changes, or the pod restarts — {exc.action}")
        failure(discovery_log, "fleet-lookup-failed", phase="credential", outcome=exc.code, cluster=name, secret=secret,
                attempt=f"{state.attempts}/{LOOKUP_ATTEMPTS}", retry_in=None if wait is None else f"{wait:g}",
                gave_up="true" if state.gave_up else None, action=action, detail=exc.detail, secrets=exc.secrets)
```

A values stanza's retrieved Secret can vanish at runtime — deleted to force a fresh lookup, or by
a namespace policy — and the stanza then resolves to its pending self again. The reconcile rule
"a values cluster is never stopped at runtime" was written for a stanza that carries its own
credential; a pending one must stop, or its thread polls the stanza, `resolve_token` raises the
pending reason, and the tab shows an `auth_failed` for a credential that was never presented —
the thing SPEC_S3 §4.2 forbids.

**File:** `local-development/gsd/poller.py` — edit

Old text:

```python
        for name in running - set(wanted):
            if name in {c.name for c in self.settings.clusters}:
                continue    # a values cluster is never stopped at runtime: its config rolls the pod
            self._cluster_stops[name].set()
```

New text:

```python
        for name in running - set(wanted):
            values_entry = next((c for c in self.settings.clusters if c.name == name), None)
            if values_entry is not None and values_entry.credential_pending is None:
                continue    # a values cluster with its own credential is never stopped at runtime: its config rolls the pod
            # A values stanza that declares a mode polls through the Secret the lookup wrote; with that
            # Secret gone it is pending again and must not poll its stanza (SPEC_S4b, SPEC_S3 §4.2).
            self._cluster_stops[name].set()
```

**File:** `local-development/gsd/poller.py` — edit

Old text:

```python
            try:
                self._discover_once()
                self._reconcile_threads()
            except Exception:  # noqa: BLE001 - the discovery thread must never die silently
                log.exception("unhandled error discovering cluster Secrets")
```

New text:

```python
            try:
                self._discover_once()
                self._reconcile_threads()
                self._retrieve_pending()
            except Exception:  # noqa: BLE001 - the discovery thread must never die silently
                log.exception("unhandled error discovering cluster Secrets")
```

**File:** `local-development/gsd/poller.py` — edit

Old text:

```python
        if self.settings.cluster_secrets_enabled:
            thread = threading.Thread(target=self._run_discovery, name="cluster-secrets", daemon=True)
            thread.start()
            self._threads.append(thread)
        log.info("poller started for %d cluster(s)", len(self._cluster_stops))
```

New text:

```python
        if self.settings.cluster_secrets_enabled:
            if any(c.enabled and c.credential_kind == CREDENTIAL_LOOKUP for c in effective):
                # SPEC_S4b: a cluster awaiting its lookup does not wait a whole cadence for it. The
                # lookup runs on the thread, never here — a target that is down must not hold up start.
                self._discover_now.set()
            thread = threading.Thread(target=self._run_discovery, name="cluster-secrets", daemon=True)
            thread.start()
            self._threads.append(thread)
        log.info("poller started for %d cluster(s)", len(self._cluster_stops))
```

### 3.14 Tests

#### `local-development/tests/test_fleet_lookup.py` — new file, the hermetic proof

```python
"""#284 (SPEC_S4b): the saTokenLookup lookup against a fake target and a fake host — a login as the
fleet account, one GET of the poller ServiceAccount's token Secret by name, the values handed to the
shipped writer, and the session revoked on every path. R1 the loop end to end; R2 the write follows the
declaration (create for a stanza, in place for a Secret); R3 the target's Secret is checked before it is
stored; R4 a refused password is gated; R5 a trust failure names its host; R6 the schedule; R7 no
credential reaches a line."""

from __future__ import annotations

import base64
import json
import logging

import httpx
import pytest

import gsd.fleetlookup as fleetlookup
from gsd.clusterconfig import FINDING_CODES
from gsd.clusterconfig.parser import Finding
from gsd.clusterconfig.writer import (
    LOOKUP_ACCOUNT_ANNOTATION, MANAGED_BY_ANNOTATION, MANAGED_BY_LOOKUP, SOURCE_NAMESPACE_ANNOTATION,
    SOURCE_SERVICE_ACCOUNT_ANNOTATION, TOKEN_SOURCE_ANNOTATION,
)
from gsd.config import ClusterConfig, Settings
from gsd.fleetlogin import USER_TOKEN_API
from gsd.fleetlookup import CODES, INVALID_SINCE_LABEL, LAST_USED_LABEL, CredentialGate, LookupRefused, lookup
from gsd.kube import ClusterClient, ClusterError
from test_fleet_login import (
    API, DISCOVERY_PATH, PASSWORD, TOKEN, USER, Target, _pki, _require_openssl, down, login_302, refused_401,
)

SA_TOKEN = "eyJhbGciOiJSUzI1NiJ9.sa-token-that-must-never-reach-a-log.sig"
SOURCE = "/api/v1/namespaces/group-sync-operator/secrets/group-sync-dashboard-cluster-poller-token"


def sa_secret(token: str = SA_TOKEN, sa: str = "group-sync-dashboard-cluster-poller", labels: dict | None = None,
              type_: str = "kubernetes.io/service-account-token") -> dict:
    """The lab's poller token Secret, as the API server answers it (SPEC_S4b §2)."""
    return {"metadata": {"name": "group-sync-dashboard-cluster-poller-token", "namespace": "group-sync-operator",
                         "labels": {LAST_USED_LABEL: "2026-09-22", **(labels or {})},
                         "annotations": {"kubernetes.io/service-account.name": sa}},
            "type": type_, "data": {"token": base64.b64encode(token.encode()).decode(), "ca.crt": "Y2E="}}


class LookupTarget(Target):
    """S4a's fake target, plus the token Secret the session reads (a Response, or an exception)."""

    def __init__(self, *answers, secret=None, **kw):
        super().__init__(*answers, **kw)
        self.secret = httpx.Response(200, json=sa_secret()) if secret is None else secret

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "GET" and request.url.path == SOURCE:
            self.requests.append(request)
            return self._answer(self.secret, request)
        return super().__call__(request)

    @property
    def reads(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == SOURCE]


class FakeHost(ClusterClient):
    """The LOCAL cluster: the fleet password Secret and the cluster Secrets, with every write kept."""

    def __init__(self, secrets: dict[str, dict] | None = None):
        super().__init__(ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"))
        self.secrets = {"/api/v1/namespaces/ns/secrets/gsd-fleet-account":
                        {"data": {"password": base64.b64encode(PASSWORD.encode()).decode()}}, **(secrets or {})}
        self.writes: list[tuple[str, str, dict]] = []

    class _Ctx:
        def __enter__(self): return self
        def __exit__(self, *a): return False

    def _client(self): return self._Ctx()

    def _get(self, client, path, params):
        if path not in self.secrets:
            raise ClusterError("unreachable", f"HTTP 404 on {path}: not found")
        return self.secrets[path]

    def _send(self, client, method, path, *, json=None, secrets=()):
        self.writes.append((method, path, json))
        if method == "POST":
            self.secrets[f"{path}/{json['metadata']['name']}"] = json
        return None


def settings(*clusters: ClusterConfig, writes: bool = True) -> Settings:
    return Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"), *clusters],
                    db_path=":memory:", cluster_secrets_writes_enabled=writes)


@pytest.fixture
def wire(monkeypatch):
    """Every httpx.Client the module builds — the login's and the read's — goes to the fake target."""
    target = LookupTarget(login_302())
    real = httpx.Client

    def client(**kw):
        return real(transport=httpx.MockTransport(target), base_url=kw.get("base_url", API),
                    headers=kw.get("headers"), follow_redirects=False)
    monkeypatch.setattr(httpx, "Client", client)
    return target


RND = ClusterConfig("rnd", API, sa_token_lookup=True, ldap_connection_bootstrap=USER)


def run(cluster: ClusterConfig, host: FakeHost | None = None, *, write: bool = True, gate=None, s: Settings | None = None):
    host = host or FakeHost()
    result = lookup(cluster, s or settings(cluster), host, own_namespace="ns", gate=gate or CredentialGate(),
                    write=write, sleep=lambda _: None)
    return result, host


# ── R1 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheLoop:
    def test_a_stanza_becomes_a_labelled_secret_with_the_lookups_values(self, wire):
        result, host = run(RND)
        wire_order = [(r.method, r.url.path) for r in wire.requests]
        assert wire_order[:3] == [("GET", DISCOVERY_PATH), ("GET", "/oauth/authorize"), ("GET", SOURCE)]
        assert len(wire_order) == 4 and wire_order[3][0] == "DELETE" and wire_order[3][1].startswith(USER_TOKEN_API + "/")
        assert wire.reads[0].headers["authorization"] == f"Bearer {TOKEN}", "the read is the session's, not the SA token's"
        (method, path, obj), = host.writes
        assert (method, path, obj["metadata"]["name"]) == ("POST", "/api/v1/namespaces/ns/secrets", "gsd-cluster-rnd")
        assert obj["metadata"]["labels"] == {"groupsync-dashboard.io/secret-type": "cluster"}, "stamped by secret_object()"
        assert obj["metadata"]["annotations"] == {
            MANAGED_BY_ANNOTATION: MANAGED_BY_LOOKUP, TOKEN_SOURCE_ANNOTATION: "remote-lookup",
            SOURCE_NAMESPACE_ANNOTATION: "group-sync-operator",
            SOURCE_SERVICE_ACCOUNT_ANNOTATION: "group-sync-dashboard-cluster-poller", LOOKUP_ACCOUNT_ANNOTATION: USER}
        config = json.loads(obj["stringData"]["config"])
        assert config == {"tlsClientConfig": {"insecure": False}, "bearerToken": SA_TOKEN}, "the declaration's trust, no caData"
        assert obj["stringData"]["visibility"] == "self-only" and obj["stringData"]["identity"] == "none"
        assert result.written == "created" and result.sa_token.last_used == "2026-09-22"
        assert len(wire.revokes) == 1, "the login's token is revoked; the stored one is the target's"
        assert set(result.secrets) == {PASSWORD, TOKEN, SA_TOKEN}

    def test_write_false_is_the_ping_the_same_read_and_nothing_stored(self, wire):
        result, host = run(RND, write=False)
        assert result.written is None and result.sa_token.token == SA_TOKEN and host.writes == []
        assert len(wire.reads) == 1 and len(wire.revokes) == 1

    def test_a_ca_bundle_file_is_carried_into_the_secret_as_the_declared_trust(self, wire, tmp_path):
        _require_openssl()
        pem, _, _ = _pki(tmp_path, "both-hosts")      # a real CA: the writer's parser LOADS caData before it writes
        cluster = ClusterConfig("rnd", API, sa_token_lookup=True, ldap_connection_bootstrap=USER, ca_bundle_file=str(pem))
        _, host = run(cluster, FakeHost(), s=settings(cluster))
        config = json.loads(host.writes[0][2]["stringData"]["config"])
        assert config["tlsClientConfig"] == {"insecure": False, "caData": base64.b64encode(pem.read_bytes()).decode()}

    def test_the_type_label_is_stamped_whatever_labels_a_caller_supplies(self):
        """The operator's requirement (SPEC_S4b notes): an invariant, not a convention. `validate()`
        refuses the app's prefix, but `secret_object()` has callers that do not validate — measured
        on the merged tree, a caller label `secret-type: onboard` replaced the discovery label."""
        from gsd.clusterconfig import SECRET_TYPE_LABEL
        from gsd.clusterconfig.writer import CreateRequest, secret_object
        req = CreateRequest(name="x", server=API, credential_kind="bearerToken", token="tok-12345678",
                            labels={SECRET_TYPE_LABEL: "onboard", "environment": "rnd"})
        assert secret_object(req, "ns")["metadata"]["labels"] == {"environment": "rnd", SECRET_TYPE_LABEL: "cluster"}


# ── R2 ─────────────────────────────────────────────────────────────────────────────────────────

class TestADeclaringSecretIsUpdatedInPlace:
    def test_the_mode_leaves_config_the_credential_arrives_and_the_annotations_remember(self, wire):
        declared = {"metadata": {"name": "gsd-cluster-rnd", "namespace": "ns", "resourceVersion": "7",
                                 "labels": {"groupsync-dashboard.io/secret-type": "cluster", "environment": "rnd"},
                                 "annotations": {MANAGED_BY_ANNOTATION: "ui"}},
                    "data": {k: base64.b64encode(v.encode()).decode() for k, v in {
                        "name": "rnd", "server": API,
                        "config": json.dumps({"saTokenLookup": True, "ldapConnectionBootstrap": USER,
                                              "tlsClientConfig": {"insecure": False, "caData": "Y2E="}})}.items()}}
        host = FakeHost({"/api/v1/namespaces/ns/secrets/gsd-cluster-rnd": declared})
        cluster = ClusterConfig("rnd", API, sa_token_lookup=True, ldap_connection_bootstrap=USER, source="secret:gsd-cluster-rnd")
        result, _ = run(cluster, host)
        (method, path, obj), = host.writes
        assert (method, path, result.written) == ("PUT", "/api/v1/namespaces/ns/secrets/gsd-cluster-rnd", "updated")
        config = json.loads(base64.b64decode(obj["data"]["config"]))
        assert config == {"tlsClientConfig": {"insecure": False, "caData": "Y2E="}, "bearerToken": SA_TOKEN}
        assert obj["metadata"]["resourceVersion"] == "7", "PUT as read: a rewrite underneath is a 409, not a silent overwrite"
        assert obj["metadata"]["labels"]["environment"] == "rnd"
        assert obj["metadata"]["annotations"] == {MANAGED_BY_ANNOTATION: "ui", TOKEN_SOURCE_ANNOTATION: "remote-lookup",
                                                  SOURCE_NAMESPACE_ANNOTATION: "group-sync-operator",
                                                  SOURCE_SERVICE_ACCOUNT_ANNOTATION: "group-sync-dashboard-cluster-poller",
                                                  LOOKUP_ACCOUNT_ANNOTATION: USER}


# ── R3 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheTargetsSecretIsCheckedBeforeItIsStored:
    @pytest.mark.parametrize("answer,code,words", [
        (httpx.Response(404, text="not found"), "sa-token-secret-missing", "create the token Secret on the target"),
        (httpx.Response(403, text="forbidden"), "sa-token-unreadable", "get on that one Secret"),
        (httpx.Response(200, json=sa_secret(labels={INVALID_SINCE_LABEL: "2027-09-22"})), "sa-token-invalidated", "invalidated it after a year unused"),
        (httpx.Response(200, json=sa_secret(labels={INVALID_SINCE_LABEL: ""})), "sa-token-invalidated", "invalidated it after a year unused"),
        (httpx.Response(200, json=sa_secret(sa="somebody-else")), "sa-token-unreadable", "13 characters long and does not match"),
        (httpx.Response(200, json=sa_secret(type_="Opaque")), "sa-token-unreadable", "is not type kubernetes.io/service-account-token"),
        (httpx.Response(200, json=sa_secret(token="")), "sa-token-unreadable", "has no token yet"),
    ])
    def test_each_refusal_names_its_fix_stores_nothing_and_still_logs_out(self, wire, answer, code, words):
        """The empty `invalid-since` value is review of #295, P1-5: the label's PRESENCE is the fact."""
        wire.secret = answer
        with pytest.raises(LookupRefused) as exc:
            run(RND)
        assert exc.value.code == code and exc.value.spent is True
        assert words in exc.value.detail + " " + exc.value.action
        assert "somebody-else" not in exc.value.detail and "Opaque" not in exc.value.detail, "a remote name is never echoed"
        assert SA_TOKEN not in str(exc.value) + exc.value.detail + exc.value.action
        assert len(wire.revokes) == 1, "the session is revoked after a failed read too"

    def test_every_code_this_module_raises_is_in_the_closed_set(self):
        assert set(CODES) <= set(FINDING_CODES)


# ── R4 ─────────────────────────────────────────────────────────────────────────────────────────

class TestARefusedPasswordIsGated:
    def test_the_second_lookup_sends_no_login_until_the_password_moves(self, wire):
        wire.answers = [refused_401(), login_302()]
        gate = CredentialGate()
        with pytest.raises(LookupRefused) as first:
            run(RND, gate=gate)
        assert first.value.code == "login-refused" and first.value.spent is True and len(wire.authorize) == 1
        host = FakeHost()
        with pytest.raises(LookupRefused) as second:
            run(RND, host, gate=gate)
        assert second.value.code == "login-refused" and second.value.spent is False
        assert len(wire.authorize) == 1, "the refusal was retried — that is the lockout walk"
        host.secrets["/api/v1/namespaces/ns/secrets/gsd-fleet-account"] = {"data": {"password": base64.b64encode(b"rotated-pass-9").decode()}}
        wire.secret = httpx.Response(200, json=sa_secret())
        result, _ = run(RND, host, gate=gate)
        assert result.written == "created" and len(wire.authorize) == 2

    def test_no_password_secret_is_a_free_finding_that_names_the_grant(self, wire):
        host = FakeHost(); host.secrets.clear()
        with pytest.raises(LookupRefused) as exc:
            run(RND, host)
        assert exc.value.code == "fleet-credential-missing" and exc.value.spent is False
        assert "gsd-fleet-account" in exc.value.detail and wire.authorize == []

    def test_a_500_on_authorize_is_one_bind_and_a_gated_credential(self, wire):
        """Review of #295, P0-1: a LOCKED account answers 500 (code 19 is not 48/49), #283 made it
        terminal inside the login, and the schedule must not re-enter it — one bind, then the gate."""
        wire.answers = [httpx.Response(500, text="Internal Server Error"), login_302()]
        gate = CredentialGate()
        with pytest.raises(LookupRefused) as first:
            run(RND, gate=gate)
        assert first.value.code == "login-failed" and first.value.spent is True and len(wire.authorize) == 1
        with pytest.raises(LookupRefused) as second:
            run(RND, gate=gate)
        assert second.value.code == "login-refused" and second.value.spent is False
        assert len(wire.authorize) == 1, "a 500 was retried — that is the lockout walk one layer up"

    def test_a_read_timeout_after_the_password_was_sent_gates_that_target(self, wire):
        """The GET was written and nothing came back: the target may have bound, #283 makes it
        terminal, and the same password must not reach THAT target again — an in-memory "final" that
        any shape change re-armed was not a stop (review of #295, second pass, R2-1/R2-2)."""
        wire.answers = [lambda r: httpx.ReadTimeout("timed out"), login_302()]
        gate = CredentialGate()
        with pytest.raises(LookupRefused) as exc:
            run(RND, gate=gate)
        assert exc.value.code == "login-failed" and exc.value.spent is True and len(wire.authorize) == 1
        assert gate.refused(API, USER, PASSWORD)
        with pytest.raises(LookupRefused) as again:
            run(RND, gate=gate)
        assert again.value.code == "login-refused" and again.value.spent is False
        assert len(wire.authorize) == 1, "the password reached a target that may have bound it, twice"

    def test_the_gate_is_per_target_so_a_sick_cluster_does_not_stop_a_healthy_one(self, wire):
        """Review of #295, second pass, R2-1: keyed without the target, a 500 from A blocked B."""
        wire.answers = [httpx.Response(500, text="Internal Server Error"), login_302()]
        gate = CredentialGate()
        with pytest.raises(LookupRefused):
            run(RND, gate=gate)
        other = ClusterConfig("east", "https://api.east.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=USER)
        result, _ = run(other, gate=gate, s=settings(other))
        assert result.written == "created" and len(wire.authorize) == 2
        assert gate.refused(API, USER, PASSWORD) and not gate.refused(other.api_url, USER, PASSWORD)


# ── R5 ─────────────────────────────────────────────────────────────────────────────────────────

class TestATrustFailureNamesItsHost:
    def test_the_oauth_route_is_named_when_authorize_cannot_connect(self, wire):
        wire.answers = [lambda r: httpx.ConnectError("[SSL: CERTIFICATE_VERIFY_FAILED] unable to get local issuer certificate")] * 5
        with pytest.raises(LookupRefused) as exc:
            run(RND)
        assert exc.value.code == "login-failed" and "against oauth-openshift.apps.example.com" in exc.value.detail
        assert "phase=tls" in exc.value.detail and "BOTH the API host and the OAuth route" in exc.value.action

    def test_the_api_host_is_named_when_discovery_cannot_connect(self, wire):
        wire.discovery = down
        with pytest.raises(LookupRefused) as exc:
            run(RND)
        assert exc.value.code == "login-failed" and "against api.example.com:6443" in exc.value.detail


# ── R6 ─────────────────────────────────────────────────────────────────────────────────────────

class TestTheSchedule:
    """The poller's half: attempts, backoff, gave up, and the free findings rechecked every cycle."""

    def _poller(self, tmp_path, monkeypatch, *, writes=True):
        from gsd.poller import Poller
        from gsd.store import Store
        monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
        s = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"), RND],
                     db_path=str(tmp_path / "p.db"), cluster_secrets_writes_enabled=writes)
        return Poller(Store(str(tmp_path / "p.db")), s)

    def test_a_spent_failure_backs_off_and_gives_up_out_loud(self, tmp_path, monkeypatch, caplog):
        clock = [1000.0]
        monkeypatch.setattr("gsd.poller.time.monotonic", lambda: clock[0])

        def failing(*a, **kw):
            raise LookupRefused("sa-token-secret-missing", "gone", action="create the token Secret on the target", spent=True)
        monkeypatch.setattr(fleetlookup, "lookup", failing)
        poller = self._poller(tmp_path, monkeypatch)
        interval = poller.settings.binding_interval_seconds
        with caplog.at_level(logging.INFO, logger="gsd"):
            waits = []
            for n in range(1, 6):
                poller._retrieve_pending()
                state = poller._lookups["rnd"]
                waits.append(state.not_before - clock[0])
                clock[0] = state.not_before
            poller._retrieve_pending()          # gave up: nothing runs, nothing is logged
        lines = [m for m in caplog.messages if m.startswith("fleet-lookup-failed ")]
        assert len(lines) == 5 and waits[:4] == [interval, 2 * interval, 4 * interval, 8 * interval] and waits[4] == 0
        assert "attempt=1/5" in lines[0] and "retry_in=" in lines[0] and "gave_up=true" in lines[4] and "outcome=sa-token-secret-missing" in lines[4]
        finding = next(f for f in poller.settings.cluster_registry.findings() if f.code == "sa-token-secret-missing")
        assert finding.secret == "gsd-cluster-rnd" and "create the token Secret on the target" in finding.detail

    def test_writes_off_is_a_free_finding_said_once_and_no_login(self, tmp_path, monkeypatch, caplog, wire):
        """The switch is checked inside `lookup()` (review of #295, P1-4), before any password is read
        and before any login; the poller announces the free finding once and rechecks every cycle."""
        poller = self._poller(tmp_path, monkeypatch, writes=False)
        monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: FakeHost())
        with caplog.at_level(logging.INFO, logger="gsd"):
            poller._retrieve_pending(); poller._retrieve_pending()
        assert wire.requests == [] and sum(m.startswith("fleet-lookup-failed ") for m in caplog.messages) == 1
        assert [f.code for f in poller.settings.cluster_registry.findings()] == ["fleet-write-disabled"]

    def test_the_lookup_itself_refuses_to_write_with_the_switch_off_and_the_ping_needs_no_grant(self, wire):
        with pytest.raises(LookupRefused) as exc:
            run(RND, s=settings(RND, writes=False))
        assert exc.value.code == "fleet-write-disabled" and exc.value.spent is False and wire.requests == []
        result, host = run(RND, write=False, s=settings(RND, writes=False))
        assert result.written is None and host.writes == [] and len(wire.reads) == 1

    def test_above_one_replica_without_an_elector_no_replica_retrieves(self, tmp_path, monkeypatch, caplog, wire):
        """Review of #295, P0-2: with election off `elector` is None on every replica, and a
        Secret-declared mode is invisible to the render's refusal — so the pod refuses it itself."""
        import dataclasses
        poller = self._poller(tmp_path, monkeypatch)
        poller.settings = dataclasses.replace(poller.settings, replica_count=2)
        with caplog.at_level(logging.INFO, logger="gsd"):
            poller._retrieve_pending()
        assert wire.requests == []
        finding, = poller.settings.cluster_registry.findings()
        assert finding.code == "fleet-write-disabled" and "2 replicas" in finding.detail

    def test_a_non_scalar_token_and_an_error_body_are_refusals_that_carry_nothing(self, wire):
        """Review of #295, second pass, R2-3: a `data.token` that is not a string raised TypeError in
        front of every refusal; a 500 body on the Secret GET carried the token straight into the
        finding, because an undecoded token is not among the secrets a refusal is scrubbed against."""
        wire.answers = [login_302(), login_302()]      # two logins, one per probe
        odd = sa_secret(); odd["data"]["token"] = 123
        wire.secret = httpx.Response(200, json=odd)
        with pytest.raises(LookupRefused) as exc:
            run(RND)
        assert exc.value.code == "sa-token-unreadable" and "has no token yet" in exc.value.detail
        wire.secret = httpx.Response(500, text=f"boom {SA_TOKEN} boom")
        with pytest.raises(LookupRefused) as exc:
            run(RND)
        assert exc.value.code == "sa-token-unreadable" and "HTTP 500 on " in exc.value.detail
        assert SA_TOKEN not in str(exc.value) + exc.value.detail + exc.value.action, "a remote body is never quoted"

    def test_success_clears_the_finding_and_wakes_discovery(self, tmp_path, monkeypatch, caplog):
        from gsd.fleetlookup import LookupResult, SaToken
        poller = self._poller(tmp_path, monkeypatch)
        poller.settings.cluster_registry.set_lookup_finding("rnd", Finding("gsd-cluster-rnd", "login-failed", "x"))
        monkeypatch.setattr(fleetlookup, "lookup", lambda *a, **kw: LookupResult(
            "rnd", USER, SaToken(token=SA_TOKEN, namespace="group-sync-operator", service_account="poller", secret_name="poller-token", last_used="2026-09-22"),
            "gsd-cluster-rnd", "created", (SA_TOKEN,)))
        with caplog.at_level(logging.INFO, logger="gsd"):
            poller._retrieve_pending()
        assert poller.settings.cluster_registry.findings() == [] and poller._discover_now.is_set()
        line = next(m for m in caplog.messages if m.startswith("fleet-lookup "))
        assert "written=created" in line and "last_used=2026-09-22" in line and SA_TOKEN not in line

    def test_a_retrieved_stanza_whose_secret_vanished_stops_polling_rather_than_polling_the_stanza(self, tmp_path, monkeypatch):
        """SPEC_S3 §4.2: a pending credential is never presented. With the lookup's Secret gone the
        stanza is pending again, so its thread stops; a values cluster with its own credential is
        still never stopped at runtime."""
        import threading
        poller = self._poller(tmp_path, monkeypatch)
        poller.settings.clusters.append(ClusterConfig("east", "https://api.east:6443", token_env="X"))
        poller._cluster_stops["rnd"] = threading.Event()
        poller._cluster_stops["east"] = threading.Event()
        poller._reconcile_threads()
        assert poller._cluster_stops["rnd"].is_set(), "the pending stanza kept polling"
        assert not poller._cluster_stops["east"].is_set(), "a values cluster with a credential was stopped"


# ── R7 ─────────────────────────────────────────────────────────────────────────────────────────

class TestNoCredentialReachesALine:
    def test_the_password_the_session_and_the_sa_token_are_absent_from_every_refusal_and_line(self, wire, caplog):
        planted = httpx.Response(200, json=sa_secret(sa=f"somebody {PASSWORD} {TOKEN} {SA_TOKEN}"))
        wire.secret = planted
        with caplog.at_level(logging.DEBUG, logger="gsd"):
            with pytest.raises(LookupRefused) as exc:
                run(RND)
        text = str(exc.value) + exc.value.detail + exc.value.action + " ".join(caplog.messages)
        assert PASSWORD not in text and TOKEN not in text and SA_TOKEN not in text, "review of #295, P1-1: all three"
        assert set(exc.value.secrets) >= {PASSWORD, TOKEN, SA_TOKEN}, "the poller's line is handed everything in play"


class TestTheSwitchReadsAWord:
    def test_a_quoted_false_in_the_configmap_does_not_enable_writes(self, tmp_path):
        """Review of #295, P1-3: `bool("false")` is True, so the ConfigMap path enabled writes on an
        explicit disable. The env path already read the word; the ConfigMap path now does too."""
        from gsd.config import load_settings
        clusters = "clusters:\n  - name: host\n    apiUrl: https://kubernetes.default.svc\n    tokenEnv: X\n"
        for spelling, expected in (('"false"', False), ("false", False), ('"true"', True), ("true", True), ('"no"', False)):
            path = tmp_path / "c.yaml"
            path.write_text(clusters + f"clusterSecretsWritesEnabled: {spelling}\n")
            assert load_settings(str(path)).cluster_secrets_writes_enabled is expected, spelling

    def test_a_value_that_is_neither_a_boolean_nor_a_word_is_the_default_and_names_its_source(self, tmp_path, caplog):
        """Review of #295, second pass, R2-4: `2`, `-1` and `[false]` enabled the switch by truthiness,
        silently; `null` and `[]` disabled it silently; the warning named the env variable for a
        ConfigMap value. The default is off, so every odd spelling must read as off, and say so."""
        from gsd.config import load_settings
        clusters = "clusters:\n  - name: host\n    apiUrl: https://kubernetes.default.svc\n    tokenEnv: X\n"
        for spelling in ("2", "-1", "[false]", "[]", '""', "maybe", "{a: 1}"):
            path = tmp_path / "c.yaml"
            path.write_text(clusters + f"clusterSecretsWritesEnabled: {spelling}\n")
            caplog.clear()
            with caplog.at_level(logging.WARNING, logger="gsd"):
                assert load_settings(str(path)).cluster_secrets_writes_enabled is False, spelling
            assert any("clusterSecretsWritesEnabled=" in m and "not a boolean" in m for m in caplog.messages), spelling
        path = tmp_path / "c.yaml"
        path.write_text(clusters + "clusterSecretsWritesEnabled: null\n")
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="gsd"):
            assert load_settings(str(path)).cluster_secrets_writes_enabled is False
        assert caplog.messages == [], "a null is an absent key, not an odd value"
```

#### `local-development/gsd/static/index.html` and `tests/test_ui.py` — the twin's label goes last

**File:** `local-development/gsd/static/index.html` — edit

Old text:

```
  const labels = [`    ${y(CC_LABEL)}: ${y("cluster")}`].concat(Object.keys(f.labels).map((k) => `    ${y(k)}: ${y(f.labels[k])}`));
```

New text:

```
  // THE APP'S LABEL LAST, exactly as secret_object() stamps it (SPEC_S4b; review of #295, P1-2): YAML keeps the
  // later duplicate, so a form label spelled `groupsync-dashboard.io/secret-type` must not win here either.
  const labels = Object.keys(f.labels).map((k) => `    ${y(k)}: ${y(f.labels[k])}`).concat([`    ${y(CC_LABEL)}: ${y("cluster")}`]);
```

**File:** `local-development/tests/test_ui.py` — edit

Old text:

```python
    def test_the_twin_is_the_object_the_api_writes_when_a_value_carries_whitespace(self, page, cc_rig):
```

New text:

```python
    def test_the_twins_type_label_cannot_be_replaced_by_a_form_label(self, page, cc_rig):
        """Review of #295, P1-2: the pane emitted the app's label first and the form's after, so a
        label spelled `groupsync-dashboard.io/secret-type: onboard` parsed to a Secret discovery
        cannot see — the merge-order defect secret_object() had just been fixed for."""
        import yaml as _yaml
        base, host, settings = cc_rig
        _open_as(page, base, "root")
        page.click("#tab-clusters"); page.wait_for_selector("#cc-form")
        page.fill("#cc-name", "west"); page.fill("#cc-server", "https://api.west.example:6443")
        page.evaluate("() => { view.clusterForm.labels['groupsync-dashboard.io/secret-type'] = 'onboard'; render(); }")
        twin = _yaml.safe_load(page.locator("#cc-yaml").inner_text())
        assert twin["metadata"]["labels"]["groupsync-dashboard.io/secret-type"] == "cluster"

    def test_the_twin_is_the_object_the_api_writes_when_a_value_carries_whitespace(self, page, cc_rig):
```

#### `local-development/tests/test_clusterconfig.py` — the reader's shadow rule

Append to `TestRegistryAndReader` (the class holding
`test_the_reader_lists_by_label_pages_and_applies_the_duplicate_and_shadow_rules`):

```python
    def test_the_lookups_own_secret_over_the_stanza_that_asked_for_it_is_not_a_shadow(self):
        """SPEC_S4 §1: a values stanza declaring a mode EXPECTS the retriever's Secret over it. Only a
        Secret whose token-source names the kind the stanza resolves to is spared; a Secret over a
        mode-less entry, or one carrying no provenance, is still shadowing something a person wrote."""
        from gsd.clusterconfig.writer import TOKEN_SOURCE_ANNOTATION
        ours = _secret("gsd-cluster-rnd", cluster="rnd")
        ours["metadata"]["annotations"] = {TOKEN_SOURCE_ANNOTATION: "remote-lookup"}
        hand_made = _secret("gsd-cluster-old", cluster="old")
        hand_made["metadata"]["annotations"] = {TOKEN_SOURCE_ANNOTATION: "lookup"}     # the pre-#282 word
        plain = _secret("gsd-cluster-west", cluster="west")
        client = _FakeClient({"/api/v1/namespaces/ns/secrets": {"items": [ours, hand_made, plain]}})
        clusters, findings = discover(client, "ns", host_name="host", values_names=("rnd", "old", "west"),
                                      values_modes={"rnd": "remote-lookup", "old": "remote-lookup"})
        assert sorted(c.name for c in clusters) == ["old", "rnd", "west"]
        assert sorted(f.secret for f in findings if f.code == "shadows-values-entry") == ["gsd-cluster-old", "gsd-cluster-west"]
```

#### Chart tests — the mode stanzas now need the write grant

**File:** `local-development/tests/test_chart_dashboard_controller.py` — edit

Old text:

```python
def _render_values(tmp_path, clusters: list[dict], chart=CHART, select: str | None = None):
    values = tmp_path / "values.yaml"
    values.write_text(yaml.safe_dump({"clusters": clusters}, sort_keys=False))
```

New text:

```python
def _render_values(tmp_path, clusters: list[dict], chart=CHART, select: str | None = None, values: dict | None = None):
    values_file = tmp_path / "values.yaml"
    values_file.write_text(yaml.safe_dump({"clusters": clusters, **(values or {})}, sort_keys=False))
    values = values_file
```

**File:** `local-development/tests/test_chart_connection_modes.py` — edit

Old text:

```python
RND = {"name": "shared-rnd", "apiUrl": "https://api.crc.testing:6443", "saTokenLookup": True}


class TestTheGuardMirrorsTheLoader:
    def test_a_mode_stanza_renders_and_reaches_the_configmap(self, tmp_path):
        ok, out = _render_values(tmp_path, [HOME, {**RND, "ldapConnectionBootstrap": "svc-gsd.fleet@corp"}],
                                 select="templates/configmap.yaml")
```

New text:

```python
RND = {"name": "shared-rnd", "apiUrl": "https://api.crc.testing:6443", "saTokenLookup": True}
#: SPEC_S4b: a saTokenLookup stanza WRITES its Secret, so a green render needs the write grant on.
WRITES = {"clusterConfig": {"secrets": {"writes": {"enabled": True}}}}


class TestTheGuardMirrorsTheLoader:
    def test_a_mode_stanza_renders_and_reaches_the_configmap(self, tmp_path):
        ok, out = _render_values(tmp_path, [HOME, {**RND, "ldapConnectionBootstrap": "svc-gsd.fleet@corp"}],
                                 select="templates/configmap.yaml", values=WRITES)
```

**File:** `local-development/tests/test_chart_connection_modes.py` — edit

Old text:

```python
        values.write_text(yaml.safe_dump({"clusters": [HOME, RND],
                                          "clusterConfig": {"fleetAccount": {"username": "svc-gsd-fleet"}}}, sort_keys=False))
```

New text:

```python
        values.write_text(yaml.safe_dump({"clusters": [HOME, RND],
                                          "clusterConfig": {"fleetAccount": {"username": "svc-gsd-fleet"},
                                                            "secrets": {"writes": {"enabled": True}}}}, sort_keys=False))
```

Append to `local-development/tests/test_chart_connection_modes.py`:

```python
class TestTheLookupIsRefusedAtRenderWithoutWhatItNeeds:
    """SPEC_S4b: a saTokenLookup stanza writes a Secret and discovery reads it back, so the render
    refuses it without the two switches, above one replica, and with a visibility the Secret parser
    would refuse — failing `helm template`, not a pod after a green upgrade. userSelfLogin needs none."""

    @pytest.mark.parametrize("values,fragment", [
        ({}, "cluster shared-rnd declares saTokenLookup but clusterConfig.secrets.writes.enabled is false"),
        ({"clusterConfig": {"secrets": {"enabled": False, "writes": {"enabled": True}}}},
         "cluster shared-rnd declares saTokenLookup but clusterConfig.secrets.enabled is false"),
        # reporting refuses > 1 replica by design (C3) and election must be off there: both set, so the
        # lookup's rule is the one refusal left to fire (the values test_chart_strategy renders at 2 with)
        ({**WRITES, "replicaCount": 2, "leaderElection": {"enabled": False}, "reporting": {"enabled": False}},
         "clusterConfig.secrets.writes.enabled with replicaCount 2"),
    ])
    def test_the_switches_and_the_replica_rule(self, tmp_path, values, fragment):
        ok, out = _render_values(tmp_path, [HOME, RND], values=values)
        assert not ok and fragment in out, out[-600:]

    def test_the_replica_rule_holds_without_a_values_stanza(self, tmp_path):
        """Review of #295, P0-2: a Secret may declare the mode at any time, so the rule is on the
        switch that makes a lookup possible, not on a stanza the render happens to see."""
        ok, out = _render_values(tmp_path, [HOME], values={**WRITES, "replicaCount": 2, "leaderElection": {"enabled": False},
                                                            "reporting": {"enabled": False}})
        assert not ok and "clusterConfig.secrets.writes.enabled with replicaCount 2" in out, out[-600:]
        ok, out = _render_values(tmp_path, [HOME], values={"replicaCount": 2, "leaderElection": {"enabled": False},
                                                            "reporting": {"enabled": False}})
        assert ok, out[-600:]     # writes off: two replicas render as before

    def test_remote_sar_with_the_lookup_is_refused_by_name(self, tmp_path):
        ok, out = _render_values(tmp_path, [HOME, {**RND, "visibility": "remote-sar", "identity": "same-as-host"}], values=WRITES)
        assert not ok and "clusters[1] (shared-rnd): visibility remote-sar with saTokenLookup" in out

    def test_self_login_needs_no_write_grant(self, tmp_path):
        ok, out = _render_values(tmp_path, [HOME, {"name": "shared-rnd", "apiUrl": "https://api.crc.testing:6443", "userSelfLogin": True}])
        assert ok, out

    def test_the_pod_learns_the_account_and_the_address(self, tmp_path):
        ok, out = _render_values(tmp_path, [HOME, RND], select="templates/configmap.yaml",
                                 values={**WRITES, "clusterConfig": {**WRITES["clusterConfig"], "fleetAccount": {
                                     "username": "svc", "passwordSecret": {"namespace": "openshift-config", "name": "ldap-oauth-bind-secret", "key": "bindPassword"}}}})
        assert ok, out
        docs = [d for d in yaml.safe_load_all(out) if d and d.get("kind") == "ConfigMap"]
        # the settings and the clusters share one key, `clusters.yaml` (templates/configmap.yaml)
        settings = yaml.safe_load(next(d for d in docs if "clusters.yaml" in d["data"])["data"]["clusters.yaml"])
        assert (settings["fleetAccountUsername"], settings["fleetPasswordSecretNamespace"], settings["fleetPasswordSecretName"],
                settings["fleetPasswordSecretKey"]) == ("svc", "openshift-config", "ldap-oauth-bind-secret", "bindPassword")
        assert (settings["saTokenLookupSourceNamespace"], settings["saTokenLookupSourceServiceAccount"], settings["saTokenLookupTokenSecretName"]) \
            == ("group-sync-operator", "group-sync-dashboard-cluster-poller", "")
        assert settings["replicaCount"] == 1
```

**File:** `local-development/tests/test_chart_fleet_account_rbac.py` — edit

Old text:

```python
        ok, out = _render(tmp_path, {}, clusters=[HOME, {**MODE, "ldapConnectionBootstrap": "svc.gsd.fleet"}])
```

New text:

```python
        # SPEC_S4b: a saTokenLookup stanza also needs the write grant, or the render refuses it
        ok, out = _render(tmp_path, {"clusterConfig": {"secrets": {"writes": {"enabled": True}}}},
                          clusters=[HOME, {**MODE, "ldapConnectionBootstrap": "svc.gsd.fleet"}])
```

**File:** `local-development/tests/test_cluster_stanza_matrix.py` — edit

Old text:

```python
def _values(tmp_path, entries, name="v.yaml"):
    p = tmp_path / name
    p.write_text(yaml.safe_dump({"clusters": entries}), encoding="utf-8")
    return str(p)
```

New text:

```python
def _values(tmp_path, entries, name="v.yaml"):
    p = tmp_path / name
    # Rendered with the write grant on: a saTokenLookup row writes its Secret and is refused at
    # render without it (SPEC_S4b); the switch adds verbs to one Role and changes no other row.
    p.write_text(yaml.safe_dump({"clusters": entries, "clusterConfig": {"secrets": {"writes": {"enabled": True}}}}),
                 encoding="utf-8")
    return str(p)
```

#### `local-development/tests/test_specs_index.py` — the count

**File:** `local-development/tests/test_specs_index.py` — edit

Old text:

```python
    assert len(rows) == 20, f"expected twenty index rows (the programme's thirteen, E1, S1, S2, S3, S4, S4a and T1), matched {sorted(rows)}"
```

New text:

```python
    assert len(rows) == 21, f"expected twenty-one index rows (the programme's thirteen, E1, S1, S2, S3, S4, S4a, S4b and T1), matched {sorted(rows)}"
```

**File:** `local-development/tests/test_specs_index.py` — edit

Old text:

```python
    s_issues = {int(ROWS[fid]["issue"]) for fid in _ordered_ids() if fid.startswith("S")}
    assert s_issues == {230, 283}, f"the S batch is #230 (S1-S3) and #283 (S4); got {sorted(s_issues)}"
```

New text:

```python
    # S4's steps each carry their own issue (S4a #283, S4b #284): one design, one row per step.
    s_issues = {int(ROWS[fid]["issue"]) for fid in _ordered_ids() if fid.startswith("S")}
    assert s_issues == {230, 283, 284}, f"the S batch is #230 (S1-S3), #283 (S4, S4a) and #284 (S4b); got {sorted(s_issues)}"
```

### 3.15 Documents

**File:** `docs/specs/README.md` — edit

Old text:

```markdown
| S4a | [`SPEC_S4a_fleet_login_session.md`](SPEC_S4a_fleet_login_session.md) — S4 step A: the fleet login session — obtain, expire, retry, revoke; the code of #283 | S — cluster configuration | — | no version change (a module nothing calls yet; the release that first calls it bumps) | [#283](https://github.com/ephico2real2/group-sync-dashboard/issues/283) | in implementation |
```

New text:

```markdown
| S4a | [`SPEC_S4a_fleet_login_session.md`](SPEC_S4a_fleet_login_session.md) — S4 step A: the fleet login session — obtain, expire, retry, revoke; the code of #283 | S — cluster configuration | — | no version change (a module nothing calls yet; the release that first calls it bumps) | [#283](https://github.com/ephico2real2/group-sync-dashboard/issues/283) | in implementation |
| S4b | [`SPEC_S4b_sa_token_lookup.md`](SPEC_S4b_sa_token_lookup.md) — S4 step B: the ServiceAccount token lookup — read as the fleet account, write as the dashboard; the code of #284 | S — cluster configuration | — | app 0.31.0, chart 0.50.0 | [#284](https://github.com/ephico2real2/group-sync-dashboard/issues/284) | specified |
```

**File:** `docs/CLUSTER_STANZA.md` — edit

Old text:

```markdown
| `saTokenLookup: true` | `lookup` | **no — pending** |
```

New text:

```markdown
| `saTokenLookup: true` | `remote-lookup` | **after the lookup** — the dashboard logs in as the fleet account, reads the poller SA's token on the target and writes `gsd-cluster-<name>`, which then polls (SPEC_S4b); needs `clusterConfig.secrets.writes.enabled` |
```

**File:** `docs/CLUSTER_STANZA.md` — edit

Old text:

```markdown
| 6 | remote + `saTokenLookup` | listed, pending, not polled |
```

New text:

```markdown
| 6 | remote + `saTokenLookup` | retrieved on the next discovery cycle, then polled through its written Secret; renders only with `clusterConfig.secrets.writes.enabled` |
```

**File:** `docs/CLUSTER_STANZA.md` — edit

Old text:

```markdown
| **`insecureSkipVerify` + `caBundleFile`** | *renders* | **refused** |
```

New text:

```markdown
| **`insecureSkipVerify` + `caBundleFile`** | *renders* | **refused** |
| `saTokenLookup` without `clusterConfig.secrets.writes.enabled` | **refused** | starts; the tab reports `fleet-write-disabled` (a Secret-declared mode reaches this half) |
| `saTokenLookup` without `clusterConfig.secrets.enabled` | **refused** | starts; the cluster stays pending |
| `clusterConfig.secrets.writes.enabled` with `replicaCount > 1` — a lookup is possible, stanza or not | **refused** | starts; a lookup reports `fleet-write-disabled` (one retriever per estate, SPEC_S4 §6) |
| `saTokenLookup` with `visibility: remote-sar` | **refused** | starts; the write would be refused `visibility-invalid` |
```

**File:** `docs/DESIGN_cluster_connection_flows.md` — edit

Old text:

```markdown
  A bearer token is minted BY a cluster, so it lives IN that cluster's Secret.
  A username and password reach the whole fleet, so they live in ONE credential
  Secret that many clusters reference.
```

New text:

```markdown
  A bearer token is minted BY a cluster, so it lives IN that cluster's Secret.
  A username and password reach the whole fleet, so they live in ONE credential
  Secret that many clusters reference.

  RETRIEVED (SPEC_S4b, #284) — a stanza that says saTokenLookup: true
  ───────────────────────────────────  ─────────────────────────────────────────
  remote-lookup                        the dashboard logs in as the fleet account
               the target's poller SA (fleet-login … fleet-logout, #283), GETs that
               token, read once           SA's token Secret on the target by name, and
                                          writes gsd-cluster-<name> here: `fleet-lookup
                                          written=created|updated`. Then it is a
                                          `bearer` row above. Every failure is one
                                          `fleet-lookup-failed phase=credential
                                          outcome=<finding>` line — attempt=n/5,
                                          retry_in=, gave_up=true — and a standing
                                          finding on the tab until the next success.
```

**File:** `docs/CHANGELOG.md` — edit

Old text:

```markdown
## Unreleased
```

New text:

```markdown
## Unreleased

- **A `saTokenLookup` stanza is retrieved: the dashboard logs in as the fleet account, reads the poller ServiceAccount's token on the target, and writes the cluster Secret itself (#284; SPEC_S4 step B, `docs/specs/SPEC_S4b_sa_token_lookup.md`; app 0.31.0, chart 0.50.0).** The one stage of the loop that was missing: a stanza in `values.yaml` declares the intent, #283's session logs in as the fleet account, one `GET` reads the poller ServiceAccount's `kubernetes.io/service-account-token` Secret **by name** on the target (the estate grants `get` on that one Secret by `resourceNames` and refuses `list`; a manually created token Secret is not in the ServiceAccount's `.secrets`, measured), and the shipped writer produces `gsd-cluster-<name>` in the release namespace with the discovery label — so the cluster polls on the next discovery cycle with no restart. What this adds is the **values**: `token-source: remote-lookup`, the source namespace and ServiceAccount, `managed-by: sa-token-lookup`, and `lookup-account` (the account used, so a Secret that declared the mode and is **updated in place** keeps its per-cluster account for #285's re-login). The written Secret carries the **declaration's trust** — the bundle that verified both the API host and the OAuth route — never the target's `ca.crt`, which verifies only the first. Nothing is revoked here: the stored token is the target's, the login's token is revoked by the session. **The stanza's CA must cover two hosts**, and a trust failure names which one failed. **Reads before it stores:** the Secret must be the right type, belong to the named ServiceAccount, and not carry `kubernetes.io/legacy-token-invalid-since` — the cleaner's stamp on an auto-generated token unused for a year, after which the API server refuses it (upstream `legacy_serviceaccount_token_cleaner.go`; it applies only to Secrets the ServiceAccount's `.secrets` references, so a manually created one is never stamped). A missing Secret says *create the token Secret on the target* — OpenShift 4.16 and Kubernetes 1.24 stopped creating them. **The schedule is bounded by cost:** a failure that spent a login counts, `attempt=n/5`, backing off 5, 10, 20, 40 minutes, then gives up out loud until the stanza or the fleet credential changes; a refused password is never sent again while it is the same password (SPEC_S4 §6's in-memory gate); a failure that spent nothing is rechecked every cycle and said once. Eight finding codes join the closed set, all `phase=credential`, and the lookup's own Secret over the stanza that asked for it is no longer a `shadows-values-entry`. **The write grant is a hard dependency:** a stanza with `clusterConfig.secrets.writes.enabled: false` fails `helm template` (as does one with discovery off, `replicaCount > 1`, or `visibility: remote-sar`), and a Secret-declared mode with it off is a `fleet-write-disabled` finding. The switch does not split — it is one grant, and each consumer declares its own intent. The pod now learns the fleet account's address and `clusterConfig.saTokenLookup` (what it reads on every target, defaulting to the operator chart's names) through the ConfigMap; `example-production.yaml` turns writes on for its mode stanza. The review of its PR closed seven holes before it shipped: a login the target answered without a session (a refused password, or the 500 a **locked** account earns) is never re-entered by the schedule — one bind, then the credential is gated; a release that writes cluster Secrets refuses more than one replica at render and at runtime, stanza or not; the retrieved token rides every refusal's redaction; the tab's GitOps YAML stamps the type label last as the writer does; a quoted `"false"` in the ConfigMap no longer enables writes; and the cleaner's `invalid-since` label counts by presence, not value.
```

## 4. Tests — what fails before and passes after

`tests/test_fleet_lookup.py` cannot import before the module exists, so all of it fails on `main`
and passes on this head. `test_clusterconfig.py`'s new reader test fails with `TypeError:
values_modes` before §3.8 and passes after (OB1 measured exactly that on the proven diff).
`test_chart_connection_modes.py`'s `TestTheLookupIsRefusedAtRenderWithoutWhatItNeeds` fails on `main`
(the stanzas render green) and passes after §3.4; every existing chart test passes on both heads
once its values carry the write grant. `test_specs_index.py` moves to twenty-one rows with this
spec's PR. `test_fleet_login.py` passes unchanged: `host=` is one more field on lines whose fields
are asserted by presence, and no phase moved. The behaviour-preservation check for §3.10's extraction
is `test_clusterconfig_tab.py`'s rotate cases, which pass on both heads.

## 5. Verification

**Hermetic:** `cd local-development && .venv/bin/python -m pytest tests/test_fleet_lookup.py
tests/test_fleet_login.py tests/test_clusterconfig.py tests/test_clusterconfig_logging.py
tests/test_clusterconfig_tab.py tests/test_connection_modes.py tests/test_chart_connection_modes.py
tests/test_chart_fleet_account_rbac.py tests/test_cluster_stanza_matrix.py tests/test_chart_versions.py
tests/test_specs_index.py tests/test_docs_citations.py -q`.

**`helm template`, per switch state**, from the repository root with a values file holding the host
stanza and `{name: rnd, apiUrl: https://api.crc.testing:6443, saTokenLookup: true}`:

| values | expected |
|---|---|
| defaults | refused: `cluster rnd declares saTokenLookup but clusterConfig.secrets.writes.enabled is false` |
| `clusterConfig.secrets.writes.enabled: true` | renders; the cluster-secrets Role carries `create`, `update`, `delete`; the ConfigMap carries the eight keys of §3.3 |
| `… writes.enabled: true`, `secrets.enabled: false` | refused, naming `secrets.enabled` |
| `… writes.enabled: true`, `replicaCount: 2`, `leaderElection.enabled: false`, `reporting.enabled: false` — with or without the stanza | refused: `clusterConfig.secrets.writes.enabled with replicaCount 2` |
| the stanza with `userSelfLogin: true` instead, defaults | renders |
| a Secret-declared mode | invisible to the render by construction; the runtime finding is the proof |

**Live, on the reference cluster — which mechanism, and why.** The lab's dashboard is the Argo
Application, whose `helm.valuesObject` declares `clusters` for this lab (`dashboard` alone, by
design). A values stanza therefore cannot be exercised through `--argocd` against *this*
Application; the values path is exercised under **plain Helm**, which reads the values file
directly (`release-crc.sh --values <file>` — it hands the release over from Argo first, and
`--argocd main` hands it back after the merge). The Secret-declared path is exercised through the
API and is independent of either.

1. The lab account. The fleet account is never used to test (S4a's rule); the htpasswd `developer`
   stands in, granted the same read the estate grants the fleet account:
   ```
   oc adm policy add-role-to-user group-sync-dashboard-cluster-poller-token-reader developer \
      -n group-sync-operator --role-namespace=group-sync-operator
   oc -n group-sync-dashboard create secret generic gsd-fleet-account --from-literal=password=<developer's password>
   ```
2. The values file, `environments/crc-lookup.yaml` (untracked is fine under Helm mode): `environments/crc.yaml`
   plus, under `clusters`, `{name: rnd-lookup, apiUrl: https://api.crc.testing:6443, saTokenLookup: true,
   ldapConnectionBootstrap: developer, caBundleFile: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt}`
   and `clusterConfig.fleetAccount.passwordSecret: {name: gsd-fleet-account, key: password}`. The name is
   new on purpose: `gsd-cluster-shared-rnd` already exists, hand-made, and a stanza of that name would
   be shadowed by it rather than retrieved. The CA is the pod's own bundle because, on CRC, it carries
   both hosts (S4a §2.1) — that is the lab's convenience, not the contract.
3. `local-development/release-crc.sh --values environments/crc-lookup.yaml`, then the pod log:
   ```
   oc -n group-sync-dashboard logs deploy/group-sync-dashboard | grep -E 'fleet-(login|lookup|logout)|discovery |cluster-resolved cluster=rnd-lookup'
   ```
   Expected, in order: `fleet-login … account=developer`, `fleet-lookup cluster=rnd-lookup … written=created
   source=group-sync-operator/group-sync-dashboard-cluster-poller last_used=<date>`, `fleet-logout …
   outcome=revoked`, `discovery … added=rnd-lookup`, `cluster-resolved cluster=rnd-lookup source=secret:gsd-cluster-rnd-lookup
   credential=bearer`, and no `fleet-lookup-failed`.
4. The Secret, field for field against the hand-made one:
   ```
   for s in gsd-cluster-shared-rnd gsd-cluster-rnd-lookup; do oc -n group-sync-dashboard get secret $s -o json | jq -c '{keys:(.data|keys), config:(.data.config|@base64d|fromjson|keys), labels:.metadata.labels, ann:(.metadata.annotations|del(.["kubectl.kubernetes.io/last-applied-configuration"]))}'; done
   ```
   Expected: the same `data` keys and the same `config` keys; the written one carries
   `managed-by: sa-token-lookup`, `token-source: remote-lookup`, `lookup-account: developer` and the
   two source annotations; its `config.tlsClientConfig` is the declared `caData`.
5. `curl` (or the tab): `/api/clusterconfigs` lists `rnd-lookup` with `credential: bearer`, `status: ok`
   after the first poll, and no finding for it.
6. The target's token count before and after (S4a §5's command, `userName=="developer"`): equal.
7. The Secret-declared path, without touching values: `oc -n group-sync-dashboard apply -f -` a Secret
   `gsd-cluster-rnd-lookup2` (`name: rnd-lookup2`, `server: https://api.crc.testing:6443`,
   `config: {"saTokenLookup": true, "ldapConnectionBootstrap": "developer"}`, the type label). Expected
   on the next cycle: `fleet-lookup … written=updated`, and the Secret's `config` now
   `{bearerToken, tlsClientConfig}` with the four annotations and `managed-by` untouched.
8. Clean up: delete both Secrets (the clusters retire, rows kept), remove the RoleBinding and the
   password Secret, and `release-crc.sh --argocd main` once merged.

The evidence — the log lines, the two `jq` outputs, the counts — is committed under
`reports/<date>_s4b_lookup/` and embedded on the issue against its Definition of Done.

## 6. What the next steps inherit

- **#285** calls `fleetlookup.lookup(cluster, settings, host_client, own_namespace=…, gate=…, write=False)`
  for the daily ping and reads `LookupResult.sa_token.last_used`; it makes `CredentialGate` durable
  and shared, re-arms a `gave_up` lookup on its own schedule, and **owns true mutual exclusion
  across replicas** (review of #295, second pass, R2-5): the in-memory gate and leader election are
  best-effort — two pollers without an elector, a stale and a new lease holder, a rollout's two pods,
  an HPA past a ConfigMap that says one replica — so before a `FleetLogin` is built, a claim the
  cluster arbitrates is taken: a Lease named for the (target, account) pair, acquired by
  compare-and-swap on its `resourceVersion` with a holder identity and a short expiry, refused when
  another holder's claim is live, released on exit. Until it lands, the operational guidance is one
  replica. And — for an estate whose token Secret
  is auto-generated — treats a cluster that has stopped polling as the fuse running, since the ping
  does not stamp `last-used` and the poll does. The account to re-login as is the Secret's
  `lookup-account`; the trust is the Secret's `tlsClientConfig`, which is what verified both hosts.
- **#286** finds nothing of this step's on the target: every login here is a session and revokes
  itself; a `fleet-logout-failed` line names the one object that survived.
- **S3c** (the tab) reads the four annotations for its provenance card and words a lookup-written
  credential `expires: current` — permanent while used, dead with its Secret or with the cleaner's
  stamp.
- **#293** — a labelled ConfigMap of cluster stanzas (label key `config-type: onboard|sideload`;
  `secret-type` stays Secret-only) that generates the Secrets through this lookup, so nobody
  hand-makes one. It depends on this step, and on the type label being stamped last (§3.10): its
  labels are authored by someone else. Prior art, for the reader who asks why this is not Argo CD's
  model: Argo's cluster declaration *is* a Secret because it carries the kubeconfig, whereas this
  design separates the declaration (a stanza, a ConfigMap) from the credential the lookup obtains —
  the shape of External Secrets Operator's `ExternalSecret`, not of `argocd cluster add`.
