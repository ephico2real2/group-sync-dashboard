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
    connectionMode: SATokenLookup
```

The second stanza is the whole point: **it carries no credential.** `load_settings` refuses that today
(`one of tokenEnv or tokenFile is required`, `gsd/config.py`), which is correct for the modes that
exist now and must be relaxed for exactly this one — a stanza that declares `connectionMode:
SATokenLookup` is *asking the dashboard to obtain the credential*, not forgetting to supply one.

## 2. The two modes

| mode | what the dashboard does | what it stores |
|---|---|---|
| **`SATokenLookup`** (default when a stanza names no credential) | authenticates to the TARGET cluster as the fleet account (#119 P2), reads the poller ServiceAccount's token **and its `ca.crt`** from the declared token Secret the operator chart ships (`group-sync-operator-helm-chart` `55c17bc`), and writes them into a labelled cluster Secret in its own namespace | a cluster Secret whose `config` holds `bearerToken` and `tlsClientConfig.caData`, annotated `token-source: lookup` with the source cluster, namespace, ServiceAccount, minted-at and minted-by |
| **`userSelfLogin`** | polls as the fleet account itself, re-authenticating daily | nothing at rest; the token lives in memory only |

`userSelfLogin` ships with the operator's own objection recorded beside it: *a token that disappears
mid-flight takes a running report or a browsing user with it.* It is for a cluster where no
ServiceAccount can be provisioned.

**Where `SATokenLookup` finds no declared token Secret**, it mints one with the TokenRequest API
(#238) — `create serviceaccounts/<name>/token`, `resourceNames`-pinned — and annotates
`token-source: minted` with the real `expirationTimestamp`. Measured on the lab: both grants exist
and are each pinned to that one ServiceAccount (`create serviceaccounts/default/token → no`).

## 3. What the loader must change

1. A stanza carrying `connectionMode: SATokenLookup | userSelfLogin` **may omit** `tokenFile` and
   `tokenEnv`; one carrying neither mode keeps today's requirement, with today's message.
2. `connectionMode` is refused on the **controller** stanza (it is this pod's own cluster and uses
   the mounted ServiceAccount) and refused in a **cluster Secret** (a Secret already carries the
   credential the mode exists to obtain) — both by name, the way `dashboard_controller` is.
3. A stanza that names a mode **and** a credential is refused: two sources of truth, and the operator
   meant one of them.
4. The fleet credential must resolve for a mode to be usable; where it does not, the cluster is a
   **finding** (`fleet-credential-missing`) and not a crashed pod — the other clusters keep polling.

## 4. The onboarding sequence, and where each step can fail

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

## 5. The measured trap this spec exists to record

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

## 6. Testing it — and why the reference cluster can test it honestly

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

1. `shared-rnd` appears with `source: values`, `connectionMode: SATokenLookup`, and **no credential in
   the stanza**.
2. The log shows the sequence at `phase=credential → oauth → login → lookup → write`, one line each,
   with the fleet uid named and **no secret in any line** (the redaction pin covers it).
3. A labelled Secret `gsd-cluster-shared-rnd` exists, annotated `token-source: lookup` with the source
   ServiceAccount, and its `config` carries `bearerToken` and `tlsClientConfig.caData`.
4. The cluster polls `ok`, and reads what the reference cluster reads: 3 GroupSync CRs, 62 groups, 6
   NCO configs, 115 Kyverno reports, 201 login attempts.
5. Its rows are its own: `sync_event` for `shared-rnd` is independent of the controller's, because
   capture is keyed by the configured **name** — two entries are two clusters whatever endpoint they
   answer at, and nothing is merged or de-duplicated.
6. Deleting the stanza retires the cluster and it disappears from the UI (#96), keeping its history.

## 7. Decomposition

- **S3a** — the loader: `connectionMode`, the relaxed credential requirement, the four refusals, and
  the `fleet-credential-missing` finding. No network.
- **S3b** — the onboarding sequence and its findings, behind #119 P2's provider; `oauthTrust` and its
  three modes; the annotations on the written Secret.
- **S3c** — the tab: the mode per cluster, the credential's provenance, the token's source and
  expiry wording (`expires: current` for a declared Secret, a real date for a minted one — #248), and
  a **Connect** action for a stanza waiting on its credential.

Each its own PR, each its own three-seat review, each walked on the reference cluster.
