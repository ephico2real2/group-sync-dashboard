# How a cluster connects — the four flows

The cluster-configuration module (#230) decides, for every cluster in the fleet, three things a
reader eventually has to ask about: where its configuration came from, what authenticates it, and
what its API server's certificate is checked against. This document is the picture of those
decisions.

**Each flow is drawn twice, and that is deliberate.** The mermaid renders on GitHub and in the docs
site; the ASCII twin beside it is what survives a terminal, a `kubectl logs` paste, a support ticket
and an email to somebody who cannot open the repository. They are the same decision points, not a
picture and a caption — if you change one, change the other.

The log lines quoted throughout are the real vocabulary (`gsd/clusterconfig/events.py`, #245): every
failure carries `phase=`, `outcome=`, `action=` and `detail=`, so a line in the log and a row on the
Cluster Configurations tab are two renderings of one fact.

---

## 1. The connection path

Discovery to poll, with every point that can refuse. A refusal is never an exception that stops the
other clusters: it is a **finding** on the tab and a `WARNING` in the log, and the rest of the fleet
keeps polling.

```mermaid
flowchart TD
    A["Discovery: LIST Secrets by label<br/>groupsync-dashboard.io/secret-type=cluster"] --> B{"LIST succeeded?"}
    B -- "no" --> BF["phase=discovery<br/>outcome=discovery-failed<br/>the previous set stands"]
    B -- "yes" --> C["Parse each Secret<br/>name, server, config, visibility, identity"]
    C --> D{"Valid, and the only<br/>claim on this name?"}
    D -- "no" --> DF["phase=parse<br/>config-missing, name-invalid,<br/>duplicate-cluster-name, insecure-with-ca"]
    D -- "yes" --> E["Resolve the credential"]
    E --> F{"Kind?"}
    F -- "oauth" --> FF["phase=credential<br/>outcome=oauth-exchange-not-built<br/>not polled until 119 P2"]
    F -- "bearer, in-cluster, file" --> G["Choose the TLS mode<br/>see flow 2"]
    G --> H["Connect to the API server"]
    H --> H2{"Socket opened?"}
    H2 -- "no" --> HF["phase=connect<br/>outcome=unreachable<br/>DNS, refused, timeout, a proxy"]
    H2 -- "yes" --> I{"Certificate verified?"}
    I -- "no" --> IF["phase=tls<br/>outcome=cert-verify-failed<br/>action names the store and the fix for the mode in force"]
    I -- "yes" --> J["Poll: GroupSyncs, Groups, bindings"]
    J --> K{"Answered yes?"}
    K -- "no" --> KF["phase=poll<br/>auth_failed, forbidden, unreachable<br/>the server replied: 401, 403, 5xx, non-JSON"]
    K -- "yes" --> L["Rows stored<br/>status ok, last_poll set"]
```

```text
  LIST Secrets by label ────────────► [FAIL] phase=discovery  outcome=discovery-failed
   groupsync-dashboard.io/                   the previous set stands; nothing is retired
   secret-type=cluster
          │ ok
          ▼
  Parse each Secret ───────────────► [FAIL] phase=parse       config-missing, name-invalid,
   name / server / config /                                    duplicate-cluster-name,
   visibility / identity                                       insecure-with-ca
          │ valid
          ▼
  Resolve the credential ──────────► [STOP] phase=credential  outcome=oauth-exchange-not-built
   bearer | in-cluster | file                                  (username+password: #119 P2)
          │
          ▼
  Choose the TLS mode  (flow 2)
          │
          ▼
  Connect ─────────────────────────► [FAIL] phase=connect     outcome=unreachable
          │ socket opened                                      DNS, refused, timeout, a proxy
          ▼
  Verify the certificate ──────────► [FAIL] phase=tls         outcome=cert-verify-failed
          │ verified                                           action names the store AND the fix
          ▼                                                    for the mode in force (flow 2)
  Poll ────────────────────────────► [FAIL] phase=poll        auth_failed | forbidden | unreachable
          │ answered yes                                       the server REPLIED: 401, 403, 5xx,
          ▼                                                    non-JSON — nothing about the socket
  Rows stored, status=ok

  Every [FAIL] is a finding on the tab and one WARNING line, never an exception that
  stops the other clusters. Read the phase first: it tells you how far it got.
  connect vs tls vs poll is decided by WHO WROTE THE MESSAGE: a transport error this
  process built (`ConnectError: …`) is connect or tls; anything the remote answered
  is poll, whatever its body says.
```

---

## 2. The three TLS modes

The operator's ruling of 2026-09-20: trust is one of three, and naming two at once is refused rather
than silently resolved. The decision is made **per cluster**, from that cluster's own `config`, in
the order the parser asks it — the **key** `caData` is looked for first, because an empty one is a
malformed declaration and not an absent key (review of #235).

```mermaid
flowchart TD
    A["tlsClientConfig in the Secret's config"] --> B{"caData key present?"}
    B -- "no" --> C{"insecure: true?"}
    C -- "yes" --> I["Mode: insecure<br/>verification off<br/>tls=insecure"]
    C -- "no" --> F["Mode: trusted-bundle<br/>GSD_TRUSTED_CA_FILE plus the system store<br/>tls=trusted-bundle"]
    B -- "yes" --> B2{"empty?"}
    B2 -- "yes" --> R0["REFUSED<br/>outcome=unsupported-config-key<br/>omit the key, or give a bundle"]
    B2 -- "no" --> B3{"insecure: true too?"}
    B3 -- "yes" --> R["REFUSED<br/>outcome=insecure-with-ca<br/>choose one"]
    B3 -- "no" --> B4{"decodes to a PEM<br/>bundle that loads?"}
    B4 -- "no" --> R2["REFUSED<br/>outcome=ca-data-invalid"]
    B4 -- "yes" --> E["Mode: caData<br/>this cluster's own bundle<br/>tls=caData"]
    E --> G["Verification fails here:<br/>replace caData in THIS Secret<br/>store=secret:name/tlsClientConfig.caData"]
    F --> H["Verification fails here:<br/>add the CA to trustedCA.existingConfigMap (fleet-wide)<br/>or set caData (this cluster only)<br/>store=$GSD_TRUSTED_CA_FILE"]
```

```text
                 tlsClientConfig
                        │
                 caData KEY present?
                        │
            no ─────────┴───────── yes
            │                       │
     insecure: true?             empty? ──yes──► REFUSED outcome=unsupported-config-key
      │           │                 │                    "omit the key, or give a bundle"
     yes          no                no
      │           │                 │
  MODE:      MODE:           insecure: true too? ──yes──► REFUSED outcome=insecure-with-ca
  insecure   trusted-bundle         │                              "choose one"
  verifi-    GSD_TRUSTED_CA_FILE    no
  cation     + system store         │
  off        tls=trusted-bundle   decodes to a PEM bundle
  tls=            │               that loads? ──no──► REFUSED outcome=ca-data-invalid
  insecure        │                 │
                  │                yes
                  │                 │
                  │           MODE: caData
                  │           this cluster's own bundle
                  │           tls=caData
                  │                 │
   if verification fails:      if verification fails:
   add the CA to               replace caData in THIS cluster's Secret
   trustedCA.existingConfigMap store=secret:<name>/tlsClientConfig.caData
   (whole fleet), OR set
   caData (this cluster)
   store=$GSD_TRUSTED_CA_FILE
```

A cluster that comes from the chart's **values** rather than a Secret has two more modes, and the log
prints them in the same `tls=` field: `tls=caBundleFile` (a `caBundleFile:` path in `clusters[]`) and
`tls=serviceAccount` (that path being the pod's own SA CA). Neither is reachable from a Secret, so
neither is on the flow above; for both, `store=` names the file itself and the fix is to point it at
the CA that signs that cluster's API server.

The last row is why the failure line separates the two: **the fix depends on the mode in force.** A
cluster on the shared bundle is repaired fleet-wide; a cluster pinning its own CA is repaired alone;
a cluster already running `insecure` cannot be failing verification at all.

### The three modes, proven: the TLS verification record

The picture above is a claim; this is its proof, and it lives beside the picture so the two are read
together (the operator on #244, 2026-09-20: *"the verification must be documented, not just measured"*).
The rig is `local-development/mock-app/deploy/tls-modes/` — three copies of the mock OpenShift API,
identical except for who signed their serving certificate, one labelled Secret per mode and a fourth
Secret that names two modes at once. **Re-running the rig (`deploy-tls-modes.sh --prove`) is how a
future change to the trust logic is re-proved — not re-argued.** The record below is #244's,
re-measured on the lab on 2026-09-20 from the worktree of PR #247 (pod
`group-sync-dashboard-76d5bb4ff8-w8pbx`), and the numbers are the same.

**1. The TLS handshake, from inside the dashboard pod, using only its own trust store**
(`curl -w '%{ssl_verify_result}'`, nothing but the pod's bundle):

| endpoint | `ssl_verify_result` | meaning |
|---|---|---|
| `mock-trusted` | **0** (HTTP 404 from the mock) | verified — the chain to the CA in the pod's bundle is real |
| `mock-privateca` | **20** | *unable to get local issuer certificate* — correctly rejected |
| `mock-selfsigned` | **18** | *self signed certificate* — correctly rejected |

The three certificates are genuinely distinct chains, which is what makes the test meaningful:
`mock-trusted-tls` ← issuer `ldap-enterprise-ca`; `mock-privateca-tls` ← its own bootstrapped CA;
`mock-selfsigned-tls` ← a `selfSigned` issuer. cert-manager issues all three, and the dashboard trusts
the first through the injected bundle.

The commands, exactly as run. The pod's curl reads its `.curlrc` through `CURL_HOME=/etc/curl`
(`cacert = /etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt`, `capath = /etc/pki/tls/certs`),
so a bare `curl` in the pod verifies against precisely the stores the dashboard's `trusted-bundle`
mode does; the rig's Services listen on `6443`, the port its Secrets' `server` names:

```sh
NS=group-sync-dashboard
for n in mock-trusted mock-privateca mock-selfsigned; do
  printf '%-16s ' "$n"
  oc -n "$NS" exec deploy/group-sync-dashboard -c dashboard -- \
    sh -c "curl -s -o /dev/null --max-time 5 -w 'http=%{http_code} ssl_verify_result=%{ssl_verify_result} exit=' https://$n:6443/; echo \$?"
done
```

```text
mock-trusted     http=404 ssl_verify_result=0 exit=0
mock-privateca   http=000 ssl_verify_result=20 exit=60
mock-selfsigned  http=000 ssl_verify_result=18 exit=60
```

The chains, read off the cluster (`oc -n "$NS" get certificate -o custom-columns='NAME:.metadata.name,ISSUER_KIND:.spec.issuerRef.kind,ISSUER:.spec.issuerRef.name,READY:.status.conditions[?(@.type=="Ready")].status'`):

```text
NAME                  ISSUER_KIND     ISSUER                     READY
mock-privateca-ca     Issuer          mock-privateca-bootstrap   True
mock-privateca-tls    Issuer          mock-privateca-issuer      True
mock-selfsigned-tls   Issuer          mock-selfsigned-leaf       True
mock-trusted-tls      ClusterIssuer   ldap-enterprise-ca         True
```

(`mock-privateca-bootstrap` and `mock-selfsigned-leaf` are `selfSigned: {}` Issuers; `mock-privateca-issuer`
signs from the `mock-privateca-ca` Secret — the manifests are `pki-trusted.yaml`, `pki-privateca.yaml`
and `pki-selfsigned.yaml` in the rig.)

**2. The application's own state** (`GET /api/clusterconfigs`, pod loopback):

```text
mock-trusted      {"insecure": false, "ca": "trusted-bundle"}   ok
mock-privateca    {"insecure": false, "ca": "caData"}           ok
mock-selfsigned   {"insecure": true,  "ca": null}               ok
gsd-cluster-mock-refusal → finding insecure-with-ca:
    "tlsClientConfig.caData and tlsClientConfig.insecure=true are both set: choose one"
```

All four claims hold and the pod served the request through the refusal. The command, and what it
returned when re-run:

```sh
oc -n "$NS" exec deploy/group-sync-dashboard -c dashboard -- \
  sh -c "curl -s --max-time 5 -H 'X-Forwarded-User: kubeadmin' 'http://127.0.0.1:8080/api/clusterconfigs'" \
  | jq -c '(.clusters[] | select(.id|startswith("mock-")) | {id, tls, status}), (.findings[] | select(.code=="insecure-with-ca"))'
```

```text
{"id":"mock-privateca","tls":{"insecure":false,"ca":"caData"},"status":"ok"}
{"id":"mock-selfsigned","tls":{"insecure":true,"ca":null},"status":"ok"}
{"id":"mock-trusted","tls":{"insecure":false,"ca":"trusted-bundle"},"status":"ok"}
{"secret":"gsd-cluster-mock-refusal","code":"insecure-with-ca","detail":"tlsClientConfig.caData and tlsClientConfig.insecure=true are both set: choose one"}
```

**3. The gap this verification found** (#244 item 5, fixed with the S2 PR): four Secrets carrying
**no `config` key** report `tls: null` — `crc-tls-default` among them, which is live and polling with
`unreachable` / `CERTIFICATE_VERIFY_FAILED`. A cluster being polled but showing "—" for its mode is the
ambiguity these three modes exist to remove; it is on the default store and should say so.

Read against the log: the `mock-privateca` row under mode 1, before its `caData` was set, is exactly
the `cluster-unreachable phase=tls outcome=cert-verify-failed … tls=trusted-bundle` line of
[the worked example below](#reading-the-log-against-these-pictures), and `ssl_verify_result=20` is the
OpenSSL code behind `unable to get local issuer certificate` in its `detail=`.

---

## 3. The credential modes

What authenticates the dashboard to a cluster, and **which object holds the secret** — the question
that decides who can rotate it and what a compromise costs.

```mermaid
flowchart TD
    subgraph now["Built today"]
        A["in-cluster<br/>the pod's ServiceAccount token<br/>host cluster only"]
        B["bearer<br/>config.bearerToken in this<br/>cluster's own Secret"]
        C["file<br/>tokenFile or tokenEnv<br/>from the chart's values"]
    end
    subgraph later["Designed, not built"]
        D["oauth: #119 P2<br/>today config.oauth in this cluster's Secret;<br/>designed as one fleet credential"]
        E["bootstrap: #238<br/>the dashboard mints a ServiceAccount<br/>token per cluster, stored beside it"]
    end
    A --> F["Poll as that identity"]
    B --> F
    C --> F
    D -. "refused today:<br/>outcome=oauth-exchange-not-built" .-> G["Not polled"]
    E -. "not built" .-> G
```

```text
  BUILT TODAY                          WHERE THE SECRET LIVES
  ───────────────────────────────────  ─────────────────────────────────────────
  in-cluster   the pod's SA token      mounted by Kubernetes; rotated by the kubelet
               (host cluster only)

  bearer       config.bearerToken      THIS cluster's own Secret, one per cluster
                                       rotate: edit that Secret

  file         tokenFile / tokenEnv    the chart's values and a mounted file

  DESIGNED, NOT BUILT
  ───────────────────────────────────  ─────────────────────────────────────────
  oauth        #119 P2                 TODAY: config.oauth {username, password} in this
               username + password     cluster's own Secret — parsed, then refused with
                                       outcome=oauth-exchange-not-built (no exchange yet).
                                       DESIGNED: one fleet credential Secret referenced by
                                       credentialRef, rotated once for the fleet.

  bootstrap    #238                    a token the dashboard MINTS per cluster and
               minted SA token         stores in its own labelled Secret, never in git
                                       re-minted at 80% of its life

  A bearer token is minted BY a cluster, so it lives IN that cluster's Secret.
  A username and password reach the whole fleet, so they live in ONE credential
  Secret that many clusters reference.
```

---

## 4. The tier gate on the surface

Who may see and change this, per the rulings of 2026-09-20 (#230, #239). **Each level asks its own
SubjectAccessReview and composes nothing**: RBAC is additive, and the SAR is the action's own
question, so whoever passes it can do the same thing with `oc` — the dashboard's ServiceAccount
performing the write grants nobody a permission they lack.

```mermaid
flowchart TD
    A["A reader opens the dashboard"] --> B{"SAR: get secrets<br/>in the dashboard's namespace"}
    B -- "no" --> C["No Cluster Configurations tab at all.<br/>By URL: the refusal card naming the tier"]
    B -- "yes" --> D["clusterconfig:view<br/>the tab, the clusters, their modes and findings"]
    D --> E{"SAR: create secrets<br/>in the dashboard's namespace"}
    E -- "no" --> F["Read-only: no Create, Rotate, Delete or Test.<br/>The GitOps YAML twin is still shown"]
    E -- "yes" --> G["clusterconfig:manage<br/>the write routes, when the tab lands (#237)"]
```

```text
   reader
     │
     ▼
   SAR: get secrets -n <dashboard ns>
     │                    │
     no                  yes
     │                    │
     ▼                    ▼
  no tab at all      clusterconfig:view
  (by URL: the       the tab, every cluster, its source,
   refusal card)     credential KIND, TLS mode, findings
                          │
                          ▼
                     SAR: create secrets -n <dashboard ns>
                          │                    │
                          no                  yes
                          │                    │
                          ▼                    ▼
                    read-only          clusterconfig:manage
                    no Create/Rotate/   the write routes, when the
                    Delete/Test         tab lands (#237). The gate
                    (YAML twin shown)   exists on main today; the
                                        routes it guards do not yet.

  MEASURED (CRC, 2026-09-20): the pure auditor persona — the chart's
  report-auditor role alone — answers NO to both questions, because
  cluster-reader carries no rule covering secrets at all. A reader who
  DOES pass holds namespace admin/edit and can write that Secret with
  `oc` regardless, so the gate is honest rather than decorative.
```

---

## Reading the log against these pictures

```text
gsd.clusterconfig INFO  discovery cycle=7 namespace=gsd seen=4 accepted=3 refused=1 added=ocp-east
gsd.clusterconfig INFO  cluster-resolved cycle=7 cluster=ocp-east source=secret:gsd-cluster-ocp-east
                        credential=bearer tls=trusted-bundle visibility=self-only identity=none enabled=true
gsd.poller        WARN  cluster-unreachable phase=tls outcome=cert-verify-failed
                        cluster=ocp-east source=secret:gsd-cluster-ocp-east tls=trusted-bundle
                        store=/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem
                        action="add the CA to the chart's trustedCA.existingConfigMap (fleet-wide), or set
                        tlsClientConfig.caData on this cluster's Secret (this cluster only)"
                        detail="ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed …"
```

The field order is the code's, not a choice made for the page: what and where (`phase`, `outcome`),
then which (`cluster`, `source`, `tls`, `store`), then the fix, then the evidence — `detail` is the
only field that can run to hundreds of characters, so it goes last.

`phase=` places the failure on flow 1; `tls=` places it on flow 2; `credential=` places it on flow 3.
A cycle that changes nothing logs nothing, so a line in the log always means something happened —
`grep 'cycle=7'` gives one cycle's whole story, `grep 'cluster=ocp-east'` gives one cluster's.
