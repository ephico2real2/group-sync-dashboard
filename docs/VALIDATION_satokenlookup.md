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

Measured from **inside the dashboard pod**, because that is the only place the answer is authoritative.

```sh
oc exec deploy/group-sync-dashboard -c dashboard -- python3 -c "<ssl handshake against each host>"
```

Result:

| bundle | `api.crc.testing:6443` | `oauth-openshift.apps-crc.testing:443` |
|---|---|---|
| injected trusted-bundle | **SSLCertVerificationError** | **SSLCertVerificationError** |
| ServiceAccount `ca.crt` | OK | OK |

The chart **does** ship the injected bundle and it **is** mounted:

```
ConfigMap group-sync-dashboard-trusted-ca
  label config.openshift.io/inject-trusted-cabundle: "true"
  data  ca-bundle.crt (225717 bytes)
  mount trusted-ca-injected  ->  the dashboard pod
proxy/cluster trustedCA = ldap-enterprise-ca-bundle
```

**Why it still fails here:** `inject-trusted-cabundle` supplies the *system* trust plus the *proxy's*
`trustedCA`. It does not include the cluster's **own** API server CA, which on CRC is self-signed by
`kube-apiserver-lb-signer`. So the injected bundle cannot verify CRC, while the ServiceAccount bundle
— which is `kube-root-ca` — verifies both hosts, because CRC merges the ingress CA into it.

**For a real remote cluster the opposite is true**: an enterprise-signed API would be verified by the
injected bundle (it carries `ldap-enterprise-ca-bundle`), and the local ServiceAccount CA would be
irrelevant. The right trust source depends on the target, which is why the stanza declares it per
cluster rather than the chart assuming one.

## 6. What is NOT proven by any of this

Stated plainly, because a validation document that only lists successes is not evidence.

- **`shared-rnd` is CRC targeting itself.** No cluster boundary was crossed. The mechanism is proven;
  the cross-cluster trust path, a remote OAuth route and network egress to another cluster are not.
- **`insecure: true` was not exercised live.** `fleetlookup.py` handles it (`if
  cluster.insecure_skip_verify: return "insecure", None`, writing `tlsClientConfig.insecure` and no
  CA) and `test_fleet_login.py` covers it hermetically (`verify is False`, `tls=insecure` on the log
  line), but no live retrieval has run with it.
- **The injected trusted bundle was never the trust that worked.** Case D shows why on this lab, but
  the path an estate would actually use in production has not been exercised end to end.
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
| The injected bundle cannot verify a self-signed cluster; trust must be declared per target | Case D |
| Cross-cluster, `insecure: true`, and a wrong password remain untested live | Section 6 |
