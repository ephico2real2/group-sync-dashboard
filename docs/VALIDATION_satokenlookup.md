# Validation — `saTokenLookup` on the reference cluster

Every command below was run on the reference lab (CRC, OpenShift 4.22.7) on 2026-09-22, and every
**Result** block is its real output. Nothing here is reconstructed.

Five cases were run, in this order: a rehearsal with a throwaway account, a failure case, the real
fleet account, a trust-store measurement, and the gaps that remain untested.

- [1. What is being validated](#1-what-is-being-validated)
- [2. Case A — rehearsal with the `developer` account](#2-case-a--rehearsal-with-the-developer-account)
- [3. Case B — the real fleet account, with no CA declared (the failure)](#3-case-b--the-real-fleet-account-with-no-ca-declared-the-failure)
- [4. Case C — the real fleet account, with trust declared (the success)](#4-case-c--the-real-fleet-account-with-trust-declared-the-success)
- [5. Case D — which trust store verifies which host](#5-case-d--which-trust-store-verifies-which-host)
- [5d. Making the trust bundle repeatable](#5d-making-the-trust-bundle-repeatable--refresh-cluster-wide-cash)
- [6. What is NOT proven by any of this](#6-what-is-not-proven-by-any-of-this)
- [7. Findings](#7-findings)

## 1. What is being validated

The loop `saTokenLookup` exists to close. Three of its four stages shipped before #284; the third is
the one that was missing.

```
values.yaml cluster stanza  (saTokenLookup: true, the fleet account)      the feeder, declared in code
        |
        v   #284 — the stage that was missing
  authenticate to the TARGET as the fleet account (#283's FleetLogin)
  read the target's poller ServiceAccount token, by name
        |
        v
  secret_object() writes gsd-cluster-<name>, stamping the discovery label
        |
        v
  the shipped labelled-Secret discovery picks it up  ->  the cluster polls
```

The question each case answers: **does the dashboard produce the credential itself, and does it fail
safely when it cannot?**

## 2. Case A — rehearsal with the `developer` account

Run first, deliberately, so the mechanism was proven before a real directory account was involved.
`developer` is a local htpasswd account on CRC; a wrong password there cannot lock out anything.

### Step A1 — the objects

```sh
oc create secret generic gsd-fleet-account -n group-sync-dashboard --from-literal=password=developer
oc create rolebinding gsd-verify-token-reader -n group-sync-operator \
  --role=group-sync-dashboard-cluster-poller-token-reader --user=developer
oc apply -f verify-cluster.yaml
```

The grant reuses the estate's **existing** `…-token-reader` Role — `get` on one named Secret, no
`list` — rather than creating a broader one for the test.

The cluster Secret declared the mode rather than carrying a credential:

```yaml
stringData:
  name: verify-lookup
  server: https://api.crc.testing:6443
  enabled: "true"
  config: '{"saTokenLookup": true, "ldapConnectionBootstrap": "developer",
            "tlsClientConfig": {"insecure": false, "caData": "<the cluster CA>"}}'
```

### Step A2 — what the dashboard did

Result:

```
fleet-login   cluster=verify-lookup account=<redacted> tls=caData
              oauth=https://oauth-openshift.apps-crc.testing expires_at=2027-09-22T11:49:28Z
fleet-logout  cluster=verify-lookup account=<redacted> tls=caData outcome=revoked
fleet-lookup  cluster=verify-lookup account=<redacted> secret=gsd-cluster-verify-lookup
              written=created source=group-sync-operator/group-sync-dashboard-cluster-poller
              last_used=2026-09-22 attempt=1/5
```

### Step A3 — and then it polled

Result:

```
verify-lookup: unmanaged-grant discovery — 1 outside the policy system, 0 resolved since the last cycle
UNMANAGED GRANT DISCOVERED — verify-lookup: ClusterRoleBinding group-sync-dashboard-ra-b78c05817c9d
  (cluster-wide) grants group-sync-dashboard-report-auditor to group app-ocp-rbac-groupsync-ns-auditor
verify-lookup poll cycle took 0.22s; next binding refresh in 300s
```

It did not merely connect — it immediately found a real unmanaged grant.

### Step A4 — litter

```sh
oc get oauthaccesstokens -o jsonpath='{range .items[*]}{.clientName}{" "}{.userName}{"\n"}{end}' \
  | grep -c 'openshift-challenging-client developer'
```

Result:

```
0
```

**`account=<redacted>` is the redactor working, not a bug.** CRC's `developer` password *is*
`developer`, so the redactor correctly replaces that substring wherever it appears — including where
it happens to be the username. Exempting `account=` to make the log prettier would be a real leak on
any estate where the two differ.

All three objects were deleted afterwards and proven absent.

## 3. Case B — the real fleet account, with no CA declared (the failure)

`shared-rnd` was declared in `environments/crc.yaml` with `saTokenLookup: true` and **no trust
declared**, then the hand-made Secret was deleted. This case was not planned; it is what happened.

Result:

```
fleet-login-failed phase=tls outcome=unreachable cluster=shared-rnd
  account=ocp-oauth-bind-serviceid tls=trusted-bundle host=api.crc.testing:6443
  attempt=1/5 retry_in=1  detail="ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] ..."
  attempt=2/5 retry_in=2
  attempt=3/5 retry_in=4
  attempt=4/5 retry_in=8
  attempt=5/5 gave_up=true
  action="gave up after 5 attempts: nothing more is tried until the next lookup or ping — check the
          API URL, the OAuth route and TLS trust for the OAuth host (the INGRESS CA, which the API's
          bundle may not carry) from this pod"
```

**This is the most valuable output in this document.** Three properties, against a real directory
account:

1. **Zero binds.** `phase=tls` means TLS failed *before* the password was written. The directory never
   saw an authentication attempt, so nothing moved toward a lockout.
2. **The backoff is exactly as specified** — 1, 2, 4, 8 seconds, five attempts, then it stops. It does
   not hammer.
3. **The error names the fix**, including the ingress-CA subtlety that #283's split-CA research put
   there.

The cause was the stanza, not the code: with no `caBundleFile` or `caData`, the login fell back to
the injected system bundle, which cannot verify CRC (see Case D).

## 4. Case C — the real fleet account, with trust declared (the success)

The stanza gained the pod's own ServiceAccount bundle:

```yaml
  - name: shared-rnd
    apiUrl: https://api.crc.testing:6443
    saTokenLookup: true
    caBundleFile: /var/run/secrets/kubernetes.io/serviceaccount/ca.crt
    enabled: true
```

Result:

```
09:34:28,843  fleet-login   cluster=shared-rnd account=ocp-oauth-bind-serviceid tls=serviceAccount
                            oauth=https://oauth-openshift.apps-crc.testing expires_at=2027-09-22T13:34:28Z
09:34:28,857  fleet-logout  account=ocp-oauth-bind-serviceid outcome=revoked
09:34:28,866  fleet-lookup  secret=gsd-cluster-shared-rnd written=created
                            source=group-sync-operator/group-sync-dashboard-cluster-poller
                            last_used=2026-09-22 attempt=1/5
09:34:28,873  cluster-resolved cycle=4 cluster=shared-rnd source=secret:gsd-cluster-shared-rnd
                            credential=bearer tls=caData visibility=self-only identity=none
09:34:28,906  polled shared-rnd: 3 CRs, 62 groups, 1 new sync event(s), 0 membership change(s)
```

**Sixty-three milliseconds** from login to polling. `written=created` — the dashboard made the Secret
itself; no human authored one.

### The Secret it wrote

```sh
oc get secret gsd-cluster-shared-rnd -n group-sync-dashboard -o jsonpath='{.metadata.annotations}'
```

Result:

```
groupsync-dashboard.io/managed-by            : sa-token-lookup
groupsync-dashboard.io/token-source          : remote-lookup
groupsync-dashboard.io/lookup-account        : ocp-oauth-bind-serviceid
groupsync-dashboard.io/source-namespace      : group-sync-operator
groupsync-dashboard.io/source-service-account: group-sync-dashboard-cluster-poller
label groupsync-dashboard.io/secret-type     : cluster
```

The `secret-type: cluster` label is stamped by `secret_object()` on everything it writes, so the
output of the lookup **is** the input of the discovery by construction — the two cannot drift apart.

### Litter

Challenging-client tokens for `ocp-oauth-bind-serviceid`: **2 before, 2 after**. The login revoked its
own (`outcome=revoked`), so the retrieval left nothing behind.

### One behaviour worth recording

While the hand-made Secret still existed alongside the declared stanza, discovery refused it by name:

```
refused_now=gsd-cluster-shared-rnd:shadows-values-entry
```

So the lookup did **not** run while a Secret of the same name was present — the Secret satisfied the
cluster and nothing needed retrieving. The lookup fired on the next cycle after the Secret was
deleted. A declared stanza does not race a hand-made Secret; it waits for it to go.

## 5. Case D — which trust store verifies which host

Measured from **inside the dashboard pod**, because that is the only place the answer is
authoritative — and against the file the application actually uses.

### Step D1 — find the bundle the app reads

A first attempt at this measurement tested `/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem`, a
guess, and concluded the injected bundle verified nothing. **That was wrong.** The app names its
bundle explicitly:

```sh
oc get deploy group-sync-dashboard -o jsonpath='{...volumeMounts[*]}{...env[*]}'
```

Result:

```
trusted-ca-injected -> /etc/pki/ca-trust/extracted/pem/injected
GSD_TRUSTED_CA_FILE=/etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt
```

### Step D2 — the measurement

Three targets: the lab's own API and OAuth route, and `mock-trusted` — an onboarded endpoint in this
namespace whose certificate is signed by the **enterprise CA**.

Result:

| bundle | size | `api.crc.testing` | `oauth-openshift…` | `mock-trusted` |
|---|---|---|---|---|
| **`GSD_TRUSTED_CA_FILE` (injected)** | 225,717 B | VERIFY-FAIL | VERIFY-FAIL | **OK** |
| system `tls-ca-bundle.pem` | 223,752 B | VERIFY-FAIL | VERIFY-FAIL | VERIFY-FAIL |
| ServiceAccount `ca.crt` | 7,209 B | OK | OK | VERIFY-FAIL |

**The ~2 KB between the injected bundle and the system one is `ldap-enterprise-ca-bundle`, and it is
exactly what makes the enterprise-signed endpoint verifiable.** The injection works, end to end:

```
ConfigMap group-sync-dashboard-trusted-ca
  label config.openshift.io/inject-trusted-cabundle: "true"
  data  ca-bundle.crt (225717 bytes)
  mount trusted-ca-injected  ->  /etc/pki/ca-trust/extracted/pem/injected
proxy/cluster trustedCA = ldap-enterprise-ca-bundle
```

### Step D3 — what this means for choosing trust

Each store is right for a different target, and none is right for all three:

- **The injected bundle** carries the system trust plus the proxy's `trustedCA`. It verifies anything
  signed by the enterprise CA — which is what a **real remote cluster** in this estate would be. It
  does **not** carry the lab's own API CA, which is self-signed by `kube-apiserver-lb-signer`.
- **The ServiceAccount bundle** is `kube-root-ca`. It verifies the lab's API and OAuth route (CRC
  merges the ingress CA into it) and nothing outside the cluster.

So the stanza must declare its trust **per target**, and the chart is right not to assume one. For
`shared-rnd` — which on this lab points at CRC itself — the ServiceAccount bundle is correct. For a
genuine remote cluster, the injected bundle is.

### Step D4 — why the enterprise path stops here

`mock-trusted` proves the **trust layer** but cannot complete a lookup:

```sh
GET https://mock-trusted:6443/.well-known/oauth-authorization-server
GET https://mock-trusted:6443/api/v1/namespaces/group-sync-operator/secrets/...-token
```

Result:

```
/.well-known/oauth-authorization-server                HTTP 404
/api/v1/namespaces/group-sync-operator/secrets/group   HTTP 404
```

It is a mock serving group-sync CRs and RBAC reads, not an OAuth server. TLS succeeds against it on
the injected bundle — which is the part that was previously unproven — but there is no authorization
endpoint to log in to and no ServiceAccount token Secret to read.

## 5b. How the trusted bundle reaches a remote cluster's handshake

Traced through the code and then proven live in the pod, because "the CA is mounted" and "the code
uses it to authenticate" are different claims.

### The chain

```
proxy/cluster  trustedCA: ldap-enterprise-ca-bundle
  |
  v   OpenShift merges it with the system bundle into any ConfigMap labelled
  |   config.openshift.io/inject-trusted-cabundle: "true"
  v
ConfigMap group-sync-dashboard-trusted-ca        (the chart creates it EMPTY; OpenShift fills it)
  |
  v   mounted by the Deployment
  v
/etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt
  |
  v   named by the env the chart sets
  v
GSD_TRUSTED_CA_FILE                              (colon-separated, like SSL_CERT_FILE)
  |
  v   gsd/config.py::_trusted_ca_context()
  v
one ssl.SSLContext                               (bundles LOADED IN TURN, never concatenated to /tmp)
  |
  v   gsd/config.py::ClusterConfig.verify()      — the fallback when no per-cluster CA is declared
  v
gsd/fleetlogin.py::FleetLogin._build_client()    — "the one TLS decision (SPEC_S3 §6)"
  |
  v
the TLS handshake against the REMOTE cluster
```

### Proven in the pod

```sh
oc exec deploy/group-sync-dashboard -c dashboard -- python3 -c \
  "<read the env, build the context, call verify() on a stanza with no CA>"
```

Result:

```
GSD_TRUSTED_CA_FILE           = /etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt
_trusted_ca_context()         -> SSLContext | certs loaded: 147
ClusterConfig(no CA).verify() -> SSLContext | certs: 147
```

A stanza that declares **no** CA resolves to the injected bundle — 147 certificates including the
enterprise CA — and that is the context the login hands to `httpx`.

### The precedence, and why it is a fallback rather than a merge

`ClusterConfig.verify()` resolves in this order:

| | |
|---|---|
| `insecureSkipVerify: true` | `False` — no verification at all |
| `caData` | a context from that data |
| `caBundleFile` | a context from that file |
| **nothing declared** | **the injected bundle** (`_trusted_ca_context()`) |
| no bundle mounted either | the system default |

The code states why the last two are not merged:

> "Deliberately a fallback rather than a merge: a cluster that names its own bundle is making a
> specific statement about what it trusts, and silently widening that would be the wrong kind of
> helpful."

And why the injected bundle is the intended default for external clusters:

> "This is what makes EXTERNAL clusters work without per-cluster configuration. Their API servers are
> usually signed by a corporate CA, which is not in Python's default trust store, so verification
> fails and the cluster shows as unreachable — a TLS problem that presents as an outage."

Two robustness details worth knowing: the context is **cached on the env value** rather than globally,
so changing the configured paths takes effect instead of being masked; and **a null result is not
cached**, because the injected ConfigMap is populated asynchronously and caching its absence would
mean never picking it up without a restart.

### The consequence for this lab's stanza

`shared-rnd` declares `caBundleFile`, so it **overrides** the injected bundle. That is necessary while
the target is CRC itself — the injected bundle cannot verify a self-signed `kube-apiserver-lb-signer`
certificate (Case D) — but it means this stanza does **not** exercise the path a real remote cluster
takes, which is to declare no CA at all and inherit the injected one.

## 5c. Case E — the production trust path, with nothing declared per cluster

Cases B–D left one gap: the injected bundle had never been the trust that actually worked. Closing it
required changing the cluster, not the code.

### Step E1 — give the proxy a bundle that covers this cluster too

The injected bundle carries the system trust merged with `proxy/cluster.spec.trustedCA`. It could not
verify CRC because CRC's API is self-signed by `kube-apiserver-lb-signer`, which is in no public
trust store. So the proxy's bundle was extended with the cluster's own CA:

```sh
oc get cm ldap-enterprise-ca-bundle -n openshift-config -o jsonpath='{.data.ca-bundle\.crt}' > enterprise.crt
oc get cm kube-root-ca.crt -n default -o jsonpath='{.data.ca\.crt}' > cluster.crt
cat enterprise.crt cluster.crt > combined.crt
oc create configmap enterprise-and-cluster-ca-bundle -n openshift-config --from-file=ca-bundle.crt=combined.crt
oc patch proxy cluster --type=merge -p '{"spec":{"trustedCA":{"name":"enterprise-and-cluster-ca-bundle"}}}'
```

Result:

```
enterprise.crt  1 cert  (O=Enterprise IT, OU=Directory Services, CN=LDAP Enterprise Root CA)
cluster.crt     6 certs (kube-root-ca)
combined        7 certs, 9173 bytes
proxy patched: ldap-enterprise-ca-bundle -> enterprise-and-cluster-ca-bundle
```

OpenShift re-injected within twelve seconds:

```
ConfigMap group-sync-dashboard-trusted-ca   225717 -> 232926 bytes   (+7209, the cluster CA)
context the app builds from it              147 -> 152 CA certs
```

(+5 rather than +6: `get_ca_certs()` counts CAs, and `kube-root-ca` includes the
`*.apps-crc.testing` leaf, which is not one.)

### Step E2 — remove the per-cluster CA from the stanza

```yaml
  - name: shared-rnd
    apiUrl: https://api.crc.testing:6443
    saTokenLookup: true
    enabled: true
    # no caBundleFile, no caData — the path a real remote cluster takes
```

### Step E3 — delete the Secret and watch

Result:

```
fleet-login   cluster=shared-rnd account=ocp-oauth-bind-serviceid tls=trusted-bundle
              oauth=https://oauth-openshift.apps-crc.testing expires_at=2027-09-22T15:25:25Z
fleet-logout  outcome=revoked
fleet-lookup  secret=gsd-cluster-shared-rnd written=created attempt=1/5
cluster-resolved cycle=3 cluster=shared-rnd credential=bearer tls=trusted-bundle
polled shared-rnd: 3 CRs, 62 groups
```

**`tls=trusted-bundle`** — compare Case C's `tls=serviceAccount`. Nothing is declared on the stanza;
the trust came entirely through the proxy and the injection. And it is the same `tls=trusted-bundle`
that **failed** in Case B with `CERTIFICATE_VERIFY_FAILED`; the only thing that changed is what the
proxy's `trustedCA` contains.

### Step E4 — the written Secret inherits it too

```
written Secret: insecure=False, caData ABSENT
cluster-resolved: tls=trusted-bundle
```

#284 decided the written Secret carries **the declaration's trust, verbatim**. The declaration had no
CA, so the Secret has none, so the steady-state **poll** also falls through to the injected bundle.
The login and the poll use the same trust, which is the property that decision exists to guarantee.

Challenging-client tokens for the fleet account: **2 before, 2 after**.

### What this now proves

The whole chain a real remote cluster depends on, with no per-cluster configuration:

```
proxy/cluster trustedCA -> inject-trusted-cabundle -> the mount -> GSD_TRUSTED_CA_FILE
  -> _trusted_ca_context() -> ClusterConfig.verify() -> the handshake -> login -> token -> poll
```

### Reverting

The original `proxy/cluster` spec and the original `ldap-enterprise-ca-bundle` ConfigMap are both
backed up; reverting is one `oc patch` back to the old name.

## 5d. Making the trust bundle repeatable — `refresh-cluster-wide-ca.sh`

Case E changed the cluster by hand. That is not a procedure anyone should repeat from memory, and the
certificate expiry dates say it will have to be repeated.

### Step F1 — check what expires, before designing anything

```sh
# every certificate in kube-root-ca, with days remaining
oc get cm kube-root-ca.crt -n default -o jsonpath='{.data.ca\.crt}' | <split and openssl x509 -enddate>
```

Result:

```
  [0]   3594d  2036-07-26  OU=openshift, CN=kube-apiserver-lb-signer
  [1]   3594d  2036-07-26  OU=openshift, CN=kube-apiserver-localhost-signer
  [2]   3594d  2036-07-26  OU=openshift, CN=kube-apiserver-service-network-signer
  [3]   3594d  2036-07-26  CN=openshift-kube-apiserver-operator_localhost-recovery-...
  [4]    674d  2028-07-28  CN=*.apps-crc.testing
  [5]    674d  2028-07-28  CN=ingress-operator@1785325954
```

Two things follow, and neither was obvious before measuring:

1. **The API signers last a decade; the INGRESS CA does not.** When it rotates in ~2 years, a bundle
   built from the old one stops verifying the **OAuth route** — and every lookup fails at `phase=tls`.
   So this is a *refresh* script, not a setup step.
2. **`[4]` is a LEAF certificate**, not an authority. It cannot sign anything, so it contributes
   nothing to a trust bundle — and Case E bundled it, because the manual procedure copied
   `kube-root-ca` wholesale.

### Step F2 — the script

`local-development/refresh-cluster-wide-ca.sh`. Dry run by default; `--apply` backs up the proxy spec
and the named ConfigMap before changing anything.

```sh
ENTERPRISE_CM=ldap-enterprise-ca-bundle ./refresh-cluster-wide-ca.sh            # report only
ENTERPRISE_CM=ldap-enterprise-ca-bundle ./refresh-cluster-wide-ca.sh --apply    # and do it
```

Result:

```
proxy/cluster trustedCA : enterprise-and-cluster-ca-bundle
enterprise source       : openshift-config/ldap-enterprise-ca-bundle

enterprise CA:
  KEEP    3646d  O=Enterprise IT, OU=Directory Services, CN=LDAP Enterprise Root CA
  enterprise: 1 of 1 kept

this cluster's CAs (kube-root-ca.crt):
  KEEP    3594d  OU=openshift, CN=kube-apiserver-lb-signer
  KEEP    3594d  OU=openshift, CN=kube-apiserver-localhost-signer
  KEEP    3594d  OU=openshift, CN=kube-apiserver-service-network-signer
  KEEP    3594d  CN=openshift-kube-apiserver-operator_localhost-recover
  drop     674d  CN=*.apps-crc.testing  (not a CA — a leaf cannot anchor a chain)
  KEEP     674d  CN=ingress-operator@1785325954
  cluster: 5 of 6 kept

combined: 6 CA certificate(s), 7949 bytes
```

Six real authorities where the hand-made bundle had seven entries in 9,173 bytes.

### Step F3 — the bug the first dry run caught

Reading the enterprise CA from *whatever the proxy currently names* is correct on the first run and
**wrong on the second**: by then the proxy names the script's own output, so the cluster CAs are read
back in and added again.

First dry run, before the fix:

```
  enterprise: 6 of 7 kept        <- "enterprise" was really enterprise+cluster
  cluster:    5 of 6 kept
  combined:   11 CA certificate(s)   <- 5 duplicates
```

Fixed two ways, because one alone would not be enough:

- **`ENTERPRISE_CM`** names the original source explicitly, rather than trusting the current state;
- **deduplication by SHA-256 fingerprint**, so any input is safe regardless. The same authority
  arriving from two sources is one anchor; a bundle listing it twice is merely larger.

After the fix, both routes converge on the same six certificates — the explicit source and the
read-back both produce `combined: 6 CA certificate(s), 7949 bytes`.

### Step F4 — applied, and idempotent

Result of `--apply`, then running it again unchanged:

```
ConfigMap openshift-config/enterprise-and-cluster-ca-bundle written (6 CA certificate(s))
proxy/cluster.spec.trustedCA -> enterprise-and-cluster-ca-bundle

Already current: proxy names 'enterprise-and-cluster-ca-bundle' and its contents match. Nothing to do.
```

### Step F5 — the effect, measured

```
injected ConfigMap   232926 -> 231702 bytes     (-1224, the leaf)
CA certs in context  152    -> 152              (unchanged — a leaf was never an anchor)
api.crc.testing                    OK
oauth-openshift.apps-crc.testing   OK
polled shared-rnd: 3 CRs, 62 groups
```

**The count staying at 152 while the file shrank is the proof the filtering was right.**

### A caution the run demonstrated

Patching `proxy/cluster` rolls cluster operators. Mid-verification the kubelet went away:

```
error: Internal error occurred: ... dial tcp 192.168.126.11:10250: connect: connection refused
```

It returned within thirty seconds and the dashboard pod never restarted, but the script says so
before it acts, and anyone running it on something that matters should expect it.

## 6. What is NOT proven by any of this

Stated plainly, because a validation document that only lists successes is not evidence.

- **`shared-rnd` is CRC targeting itself.** No cluster boundary was crossed. The mechanism is proven;
  the cross-cluster trust path, a remote OAuth route and network egress to another cluster are not.
- **`insecure: true` was not exercised live.** `fleetlookup.py` handles it (`if
  cluster.insecure_skip_verify: return "insecure", None`, writing `tlsClientConfig.insecure` and no
  CA) and `test_fleet_login.py` covers it hermetically (`verify is False`, `tls=insecure` on the log
  line), but no live retrieval has run with it.
- ~~The injected trusted bundle is proven at the TLS layer only.~~ **CLOSED by Case E**: after the
  proxy's `trustedCA` was extended with the cluster's own CA, a stanza declaring **no** CA completed a
  full login, token read, write and poll on `tls=trusted-bundle`. What remains unproven is only the
  *network* hop — the target is still this same cluster.
- **A wrong fleet password was never tested**, deliberately. The gate that makes it safe
  (`bound` + `phase=credential` -> one bind, never repeated for that password) is proven by harness in
  #284's review, not against this directory.

## 7. Findings

| | |
|---|---|
| The loop works end to end, with a real LDAP fleet account, on the first attempt | Case C |
| A missing CA fails safely: `phase=tls`, five bounded retries, **zero binds** | Case B |
| The written Secret is discoverable **by construction** — the label is stamped by the writer | Case C |
| The session revokes its own token; the retrieval leaves no litter | Cases A and C |
| A hand-made Secret **shadows** a declared stanza; the lookup waits rather than racing | Case C |
| The injected bundle verifies the **enterprise-signed** endpoint; the ServiceAccount bundle verifies the lab's own hosts; neither verifies both — so trust is declared per target | Case D |
| The enterprise CA reaches the pod: `inject-trusted-cabundle` + `proxy/cluster trustedCA` = the 2 KB that makes `mock-trusted` verifiable | Case D |
| A measurement against a guessed path produced a wrong conclusion, corrected by reading `GSD_TRUSTED_CA_FILE` | Case D, Step D1 |
| The trust bundle is rebuilt by a re-runnable script; the ingress CA expires in 674 days and will need it | Case F |
| A leaf certificate in a trust bundle costs 1,224 bytes and anchors nothing | Case F, Step F1 |
| Cross-cluster, `insecure: true`, and a wrong password remain untested live | Section 6 |
