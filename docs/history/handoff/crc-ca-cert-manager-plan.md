# Plan — rename the LDAP cert-manager PKI to a general-purpose CRC enterprise CA

**Scope**: rework the cert-manager PKI in `group-sync-operator-helm-chart` so the CA is a
*general* CRC enterprise CA (`crc-*`) rather than LDAP-specific (`ldap-*`), because it will sign
the LDAP serving cert **and** subsequent certs the CRC lab needs. The LDAP *leaf* stays
LDAP-named; only the shared CA infrastructure and the cluster trust anchor generalise.

**Repo**: `/Users/olasumbo/gitRepos/group-sync-operator-helm-chart` (NOT the dashboard repo — the
plan file just lives in the dashboard scratchpad). No dashboard-repo changes.

**Authorization for THIS artifact**: plan only. The user said "wait" then "create the plan first
in the background". No cluster mutations, no repo edits, no commits/PRs until the plan is approved.

---

## 0. Open decisions (decide before executing)

| # | Decision | Recommendation | Why it matters |
|---|---|---|---|
| D1 | Does `ldap-trusted-ca` (the chart's **injected** empty ConfigMap, `trustedCA.injected.name`) rename to `crc-trusted-ca`? | **Yes** — it carries the CRC root, nothing LDAP-specific. | 3-way coupling: `values.yaml` default ↔ `crc-injected-values.yaml` ↔ `argocd-application.yaml` `ignoreDifferences[].name`. All three must change together or Argo empties it every sync. Not currently deployed on CRC (copy mode), so no live object to migrate — a pure code/doc change. |
| D2 | Does the root **certificate subject** generalise (`commonName: LDAP Enterprise Root CA` → `CRC Enterprise Root CA`, `organizations: ["Enterprise IT"]`)? | **Yes**, and change `want="..."` in `cmd_trust_cluster` in lockstep. | Changing the CN re-issues the root → new bundle bytes → **MachineConfig node roll**. Keeping the CN cosmetically as-is lets a rename reuse the *same root bytes* and avoid the roll (see §4). Choosing "yes" here is the choice to take one deliberate node roll for a coherent PKI. |
| D3 | Keep the `OWNED_VAL` label (`app.kubernetes.io/managed-by=15-bootstrap-cert-manager-ca`) and the script filename `15-bootstrap-cert-manager-ca.sh`? | **Keep both.** | Filename is a numbered pipeline step; renaming it churns 6 sibling scripts + README that reference it by name for no functional gain. Keeping `OWNED_VAL` stable means the label sweep in `delete` still finds *old* `ldap-*` objects for teardown. Optionally update the script's header title/comment to say "CRC enterprise CA (also signs the LDAP leaf)". |
| D4 | Reuse the **existing root key** (rename in place, byte-identical bundle, no reboot) or mint a **fresh root** (new key/CN, one node roll)? | **Fresh root** is cleaner and is the coherent reading of "create CA with it"; **reuse** is the zero-reboot path if the lab must stay verifiable through the change. Pick per how disruptive a ~105 s CRC node roll is right now. | This is the single biggest execution fork. §3 gives both sequences (3A fresh, 3B reuse). D2 and D4 are linked: a new CN forces a fresh root. |
| D5 | Do it as **one PR to the operator chart repo** (per the operator's "each change through a PR, main is protected" rule) or a live-cluster-only migration? | **PR for the code/doc rename**, then apply on CRC after merge. | `main is protected` (GH006) applies in the dashboard repo; confirm the operator chart repo's protection before pushing. The rename is code+docs+live-state, so the PR carries the code and the live steps are run post-merge. |

---

## 1. Rename mapping (complete)

Confirmed live on CRC 2026-09-16 (see §7). "STAYS" = LDAP-specific or OpenShift-shape convention,
deliberately not generalised.

| Old (`ldap-*`) | New (`crc-*`) | Kind / role | Rename? |
|---|---|---|---|
| `ldap-selfsigned-bootstrap` | `crc-selfsigned-bootstrap` | ClusterIssuer (`BOOTSTRAP_ISSUER`) — selfSigned, signs only the root | **YES** (explicit) |
| `ldap-enterprise-root-ca` | `crc-enterprise-root-ca` | Certificate **and** Secret in `cert-manager` ns (`ROOT_CERT`/`ROOT_SECRET`) — isCA | **YES** |
| `ldap-enterprise-ca` | `crc-enterprise-ca` | ClusterIssuer (`CA_ISSUER`) — the CA that signs leaves | **YES** (explicit) |
| `ldap-enterprise-ca-bundle` | `crc-enterprise-ca-bundle` | ConfigMap in `openshift-config` (`TRUST_BUNDLE_CM`, key `ca-bundle.crt`) — what `proxy/cluster.spec.trustedCA` points at | **YES** |
| `ldap-trusted-ca` | `crc-trusted-ca` | ConfigMap in operator ns — the chart's **empty injected** dest (`trustedCA.injected.name`) | **D1 — recommend YES** |
| `LDAP Enterprise Root CA` (CN) | `CRC Enterprise Root CA` | root cert `commonName` + `want=` verify grep | **D2 — recommend YES** |
| `openldap-serving-cert-cm` | — | Certificate (`LEAF_CERT`) — the LDAP serving cert | **STAYS** (LDAP leaf) |
| `openldap-certmanager-tls` | — | Secret (`LEAF_SECRET`) — leaf tls.crt/key + ca.crt, mounted by the LDAP pod | **STAYS** (LDAP leaf) |
| `ca-config-map` / `ca-config-map-copy` | — | copy-mode source (openshift-config) / copy (operator ns) | **STAYS** (OpenShift IdP shape; `ca.crt` key) |
| `15-bootstrap-cert-manager-ca` (`OWNED_VAL`) | — | ownership label value | **STAYS** (D3) |
| `15-bootstrap-cert-manager-ca.sh` (filename) | — | numbered setup step | **STAYS** (D3) |
| `ldap-testing`, `openldap-service` | — | LDAP namespace/Service; SANs derive from these | **STAYS** |

**Invariant to preserve**: `crc-enterprise-ca` (CA ClusterIssuer) `.spec.ca.secretName` must equal
the renamed `ROOT_SECRET` (`crc-enterprise-root-ca`), and the leaf Certificate's `issuerRef.name`
must equal `crc-enterprise-ca`. The root secret **must** stay in the `cert-manager` ns
(cluster-resource-namespace) or the CA ClusterIssuer goes permanently NotReady.

---

## 2. File-by-file changes (all in `group-sync-operator-helm-chart`)

### 2.1 `setup-local-ldap-testing/15-bootstrap-cert-manager-ca.sh` (the engine)
- L52 `BOOTSTRAP_ISSUER="ldap-selfsigned-bootstrap"` → `crc-selfsigned-bootstrap`
- L53 `ROOT_CERT="ldap-enterprise-root-ca"` → `crc-enterprise-root-ca`
- L54 `ROOT_SECRET="ldap-enterprise-root-ca"` → `crc-enterprise-root-ca`
- L55 `CA_ISSUER="ldap-enterprise-ca"` → `crc-enterprise-ca`
- L76 `TRUST_BUNDLE_CM="${TRUST_BUNDLE_CM:-ldap-enterprise-ca-bundle}"` → `crc-enterprise-ca-bundle`
- **L240 `commonName: LDAP Enterprise Root CA` → `CRC Enterprise Root CA`** *(D2)*
- **L419 `want="LDAP Enterprise Root CA"` → `CRC Enterprise Root CA`** *(D2 — MUST match L240; the verify loop greps the merged bundle for this exact subject string; a mismatch makes `trust-cluster` falsely report the root never merged)*
- L10–L12 header chain diagram: `ldap-selfsigned-bootstrap` / `ldap-enterprise-root-ca` / `ldap-enterprise-ca` → `crc-*`
- Header prose (L1–L44): reword "PKI for the test LDAP directory" → "general CRC enterprise PKI; also signs the LDAP serving cert". `LEAF_CERT`/`LEAF_SECRET` (L56/57) unchanged.
- **Do NOT touch**: `OWNED_VAL` (L88), `CA_CONFIGMAP_NAME=ca-config-map` (L61), `COPY_NAME` (L71), `LDAP_NS`/`LDAP_SVC`, SAN derivation.

### 2.2 `charts/group-sync-operator-helm/values.yaml`  *(D1)*
- L238 `name: ldap-trusted-ca` → `crc-trusted-ca` (the live default)
- L229 comment example `name: ldap-trusted-ca` → `crc-trusted-ca`

### 2.3 `charts/group-sync-operator-helm/crc-injected-values.yaml`  *(D1)*
- L48 `name: ldap-trusted-ca` → `crc-trusted-ca`

### 2.4 `argocd-application.yaml`  *(D1 — the load-bearing coupling)*
- L68 `ignoreDifferences[].name: ldap-trusted-ca` → `crc-trusted-ca`. **Must** equal the chart's
  `trustedCA.injected.name` or Argo selfHeal empties the injected ConfigMap every sync and LDAPS
  verification breaks until the network operator refills it.

### 2.5 `CA_CERTIFICATE_FLOW.md`
- L61/L64 manual publish example: `ldap-enterprise-ca-bundle` → `crc-enterprise-ca-bundle`
- L113/L120 injected example blocks: `ldap-trusted-ca` → `crc-trusted-ca` *(D1)*

### 2.6 `setup-local-ldap-testing/README.md`
- L287/L288 trust-cluster narrative: `openshift-config/ldap-enterprise-ca-bundle` → `crc-enterprise-ca-bundle`
- L51 tool-table row wording (LDAPS-only → general CA) — cosmetic

### 2.7 `charts/group-sync-operator-helm/templates/_helpers.tpl`
- L76/L77 are **historical comments** quoting old `ci/render-checks.py` output naming `ldap-trusted-ca`.
  Update for accuracy or leave (no runtime effect). No `.Values...` literal to change — the template
  reads `.Values.trustedCA.injected.name`, so 2.2 alone changes rendered output.

### No change required
- `crc-values.yaml`, `environments/ldap-plain-values.yaml`: reference only the script *filename*
  and `ca-config-map-copy` (both STAY). `01-ldap-server.yaml`, `01.4-trusted-ca-configmap.yaml`,
  `01.6-ldap-ca-job.yaml`: reference the leaf secret / the value, not the renamed literals.
- **No values-schema/golden test** exists in the operator chart (`find` returned none), so no test
  fixture pins these names. `ci.yaml` renders `--set trustedCA.injected.enabled=true` without the
  literal name (L146), so it stays green.

---

## 3. Live migration sequence

Two variants. **3A** = fresh root (D4=fresh, D2=new CN) — coherent PKI, costs one node roll.
**3B** = reuse existing root bytes — zero node roll, keeps the lab verifiable throughout.
Run from `group-sync-operator-helm-chart/setup-local-ldap-testing/`. Reference the OpenShift
"label an empty ConfigMap" injection strategy the chart already implements (`01.4`).

### 3A — fresh CRC root (recommended for a clean generalisation)
1. **Land the code PR** (§2) and check out the renamed script.
2. `oc create` the new self-signed bootstrap ClusterIssuer → new root Certificate/Secret
   (`crc-enterprise-root-ca` in `cert-manager` ns) → new CA ClusterIssuer (`crc-enterprise-ca`) →
   re-issue the leaf (`openldap-serving-cert-cm`, `issuerRef: crc-enterprise-ca`). This is exactly
   `./15-bootstrap-cert-manager-ca.sh apply` with the renamed vars; `apply` is idempotent and the
   `guard_existing_configmap` protects the still-valid `ca-config-map` until its cert expires — so
   pass `FORCE_REPLACE_UNOWNED=true` **only** if intentionally replacing the unexpired source, else
   the new root must be written to `ca-config-map` explicitly (the guard refuses a silent swap).
3. **Reload the LDAP leaf consumer**: `oc rollout restart deploy/openldap-server -n ldap-testing`
   (the leaf secret `openldap-certmanager-tls` now holds a cert from the new root). Wait for the
   2–4 min dhparam/startupProbe cycle.
4. **Publish the new root to cluster trust** — the empty-ConfigMap injection strategy:
   `./15-bootstrap-cert-manager-ca.sh trust-cluster` creates `crc-enterprise-ca-bundle`
   (key `ca-bundle.crt`) and patches `proxy/cluster.spec.trustedCA`. **Guard**: the script
   refuses if the proxy currently names a *different* CM. It currently names
   `ldap-enterprise-ca-bundle` (ours, old name) → the guard `die`s ("already trusts ... refusing").
   **So step 4 must first repoint or clear**: `oc patch proxy cluster --type=merge -p
   '{"spec":{"trustedCA":{"name":"crc-enterprise-ca-bundle"}}}'` after creating the new bundle CM,
   OR temporarily `untrust-cluster` (clears it, one roll) then `trust-cluster` (sets new, one roll)
   — see §4 for why the direct repoint is one roll, not two.
5. Wait for the proxy validator to merge (script polls `openshift-config-managed/trusted-ca-bundle`
   for the `CRC Enterprise Root CA` subject) → **MachineConfig pool roll (~105 s, single-node CRC)**.
6. `./15-bootstrap-cert-manager-ca.sh verify` (chain + SAN from inside the cluster).
7. **Restart CA consumers** so they reload trust: `oc rollout restart deploy -n group-sync-operator`
   (and any injected-mode consumer). In copy mode, bump the source hash so the CA Job re-copies:
   `helm upgrade group-sync ../charts/group-sync-operator-helm -n group-sync-operator -f
   ../charts/group-sync-operator-helm/crc-values.yaml` (the changed root changes `caSourceHash`).
8. **Clean up old objects by explicit name** (not the label sweep — old + new share `OWNED_VAL`):
   `oc delete clusterissuer ldap-enterprise-ca ldap-selfsigned-bootstrap`;
   `oc delete certificate ldap-enterprise-root-ca -n cert-manager`;
   `oc delete secret ldap-enterprise-root-ca -n cert-manager`;
   `oc delete configmap ldap-enterprise-ca-bundle -n openshift-config` (only after the proxy no
   longer names it — it doesn't, post-step 4).

### 3B — reuse the existing root (zero node roll)
Identical objects, but seed the new secret from the old so the **root bytes never change**, so the
merged node bundle is byte-identical and MCO renders no new MachineConfig:
1. `oc get secret ldap-enterprise-root-ca -n cert-manager -o json | jq '.metadata.name="crc-enterprise-root-ca"
   | del(.metadata.uid,.metadata.resourceVersion,.metadata.creationTimestamp,.metadata.ownerReferences)'
   | oc apply -f -` (copy tls.crt/tls.key/ca.crt under the new name).
2. Create `crc-selfsigned-bootstrap` + a `crc-enterprise-root-ca` Certificate with
   `privateKey.rotationPolicy: Never` pointing at the pre-seeded secret (cert-manager adopts it if
   the spec matches; if it re-issues, you are on path 3A) — **keep CN = `LDAP Enterprise Root CA`**
   (D2=no) so the cert content matches and no re-issue is triggered.
3. Create `crc-enterprise-ca` ClusterIssuer (`secretName: crc-enterprise-root-ca`).
4. Re-point the leaf `issuerRef` to `crc-enterprise-ca` → cert-manager re-issues the *leaf* only
   (same root signs it) → `oc rollout restart deploy/openldap-server -n ldap-testing`.
5. Create `crc-enterprise-ca-bundle` from the **same** `ca.crt` bytes;
   `oc patch proxy cluster ... name: crc-enterprise-ca-bundle`. Because the bytes equal what
   `ldap-enterprise-ca-bundle` held, the validator's merged bundle is identical → **MCO renders no
   new MachineConfig → no node roll** (verify with §4's identical-bytes check).
6. verify; delete old objects by name (as 3A step 8).

---

## 4. MachineConfig-reboot risk

**The cost model** (from `CA_CERTIFICATE_FLOW.md`, measured on single-node CRC): pointing
`proxy/cluster.spec.trustedCA` at a bundle whose *content differs* triggers, on two timescales — an
immediate API-level merge into `openshift-config-managed/trusted-ca-bundle` (seconds), then MCO
rendering new `rendered-master/worker-*` MachineConfigs and rolling the pool: `Updating ~105 s`,
node `Ready` `lastTransitionTime` moves (a restart/roll), never `Degraded`. Multi-node: one node at
a time, cordon+drain.

**MCO rolls on CONTENT, not on the ConfigMap NAME.** So:

- **Swapping only the carrying ConfigMap name, same root bytes** (3B) → merged bundle byte-identical
  → MCO renders an identical MachineConfig → **no roll**. This is the answer to "does appending the
  crc root to the existing bundle avoid swapping the name": you don't need to append — you keep the
  same bytes under a new name and the roll is avoided by *content identity*, not by name stability.
- **A genuinely new root** (3A, D2=new CN or D4=fresh key) → bundle bytes change → **one roll**.
- **Append-then-swap** (put both old+new roots in the new bundle, cut consumers over, then drop the
  old) → adding a cert changes bytes = **one roll**, removing it later = **a second roll**. So
  appending is a *continuity* tactic for a real key change, **not** a reboot-avoidance tactic — it
  is strictly worse for rolls than 3B. Only use it if the root genuinely rotates and consumers must
  never see a trust gap.

**One roll, not two, on the repoint**: patch the proxy directly from `ldap-enterprise-ca-bundle` to
`crc-enterprise-ca-bundle` in a single `oc patch` (do **not** `untrust` then `trust` — clearing to
`""` is a content change = roll #1, setting the new name = roll #2 if bytes differ). The script's
`trust-cluster` guard refuses a repoint when the proxy already names another CM, so on CRC do the
`oc patch` by hand (§3A.4) rather than via `untrust-cluster; trust-cluster`.

**Byte-identity check before the repoint (proves 3B avoids the roll):**
```
diff <(oc extract cm/ldap-enterprise-ca-bundle -n openshift-config --keys=ca-bundle.crt --to=-) \
     <(oc extract cm/crc-enterprise-ca-bundle  -n openshift-config --keys=ca-bundle.crt --to=-) \
  && echo "identical -> no MCO roll expected"
```
After any repoint, watch: `oc get mcp master -w` — if it stays `Updated=True`, no roll occurred.

**CRC caveat**: a single-node CRC roll briefly transitions the node — nothing else is scheduled
during it. Do this when the lab is idle. Not to be done casually on any shared cluster (the script's
own LOCAL-SIMULATION-ONLY banner).

---

## 5. Coexistence & cutover

The two PKIs can co-exist (different object names, same `OWNED_VAL` label). Recommended order that
keeps the lab usable throughout (maps to 3B for zero-roll, 3A for fresh):

1. **Add `crc-*` alongside `ldap-*`** — new issuers/root/bundle created; old still live and still
   named by the proxy. Nothing breaks (both roots valid).
2. **Cut the leaf over** — re-point the LDAP leaf `issuerRef` to `crc-enterprise-ca`, restart
   openldap. The leaf's `ca.crt` now carries the crc root.
3. **Cut cluster trust over** — single `oc patch` of `proxy/cluster.spec.trustedCA` to
   `crc-enterprise-ca-bundle`. (3B: byte-identical, no roll; 3A: one roll.)
4. **Cut chart consumers over** — copy mode: `helm upgrade` re-copies (hash change); injected mode:
   the renamed `crc-trusted-ca` empty CM is filled by the network operator; restart the operator.
5. **Verify** end to end (`verify` subcommand + `helm test`).
6. **Remove `ldap-*` last**, by explicit name (§3A.8), only once nothing references them — proxy no
   longer names the old bundle, no leaf points at the old issuer, no consumer loads the old root.

Both roots trusted simultaneously in steps 1–5 means no verification gap. The old cleanup is the
final, separately-reversible act.

---

## 6. Per-step rollback

| Step | Undo |
|---|---|
| Code PR (§2) | revert the PR; nothing on-cluster changed yet |
| Create `crc-*` issuers/root (3A.2 / 3B.1–3) | `oc delete clusterissuer crc-enterprise-ca crc-selfsigned-bootstrap; oc delete certificate crc-enterprise-root-ca -n cert-manager; oc delete secret crc-enterprise-root-ca -n cert-manager` — old `ldap-*` untouched, lab still on old PKI |
| Re-point leaf issuerRef (3A.3 / 3B.4) | set `issuerRef.name` back to `ldap-enterprise-ca`, `oc rollout restart deploy/openldap-server -n ldap-testing` |
| Create `crc-enterprise-ca-bundle` CM | `oc delete cm crc-enterprise-ca-bundle -n openshift-config` (only if the proxy no longer names it) |
| Repoint proxy trust | `oc patch proxy cluster --type=merge -p '{"spec":{"trustedCA":{"name":"ldap-enterprise-ca-bundle"}}}'` — `proxy-cluster.yaml` backup written by `trust-cluster` under `setup-local-ldap-testing/.ca-configmap-backup/`; expect a roll back to old bytes if they differed |
| Chart consumer cutover | `helm rollback group-sync` / re-`upgrade` with the prior values file; `--reset-values` if the values file changed |
| Old-object cleanup (§3A.8) | **not reversible** without re-`apply` — do it last, after a full verify. A deleted root secret means a re-issue on the next `apply`. |

Backup before touching the proxy: `trust-cluster` already writes
`.ca-configmap-backup/proxy-cluster.yaml`; also `oc get proxy cluster -o yaml > backup` by hand
before any manual `oc patch`.

---

## 7. Empirical live state (CRC, read-only, 2026-09-16)

- `proxy/cluster.spec.trustedCA.name = ldap-enterprise-ca-bundle` (SET — a prior path-C exercise)
- ClusterIssuers: `ldap-enterprise-ca` (Ready, 42d), `ldap-selfsigned-bootstrap` (Ready, 42d);
  unrelated `robocorp-tpp-venafi-issuer-rnd` (NotReady) — evidence the lab already issues non-LDAP
  certs, which is exactly the "sign subsequent stuff" rationale for generalising.
- Certificates: `cert-manager/ldap-enterprise-root-ca` (Ready, secret `ldap-enterprise-root-ca`);
  `ldap-testing/openldap-serving-cert-cm` (Ready, secret `openldap-certmanager-tls`)
- `openshift-config`: `ca-config-map` (copy-mode source, key `ca.crt`) and
  `ldap-enterprise-ca-bundle` (trust bundle, key `ca-bundle.crt`) both present, 42d
- `group-sync-operator/ldap-trusted-ca` = **NotFound** → the cluster runs **copy mode** (mode 1),
  not injected mode. So renaming `ldap-trusted-ca` (D1) is a pure code/doc change with **no live
  object to migrate** on this CRC.
- Namespaces `ldap-testing`, `group-sync-operator`, `cert-manager` all Active.

**Net**: on CRC today, the objects that actually need a live rename are the two ClusterIssuers, the
root Certificate+Secret, the `openshift-config` trust bundle, and the leaf's issuerRef — plus the
one `oc patch` to repoint the proxy. `crc-trusted-ca` is code-only (injected mode isn't deployed).

---

## 8. Out of scope (noted so it isn't conflated)
- The **mock-cluster** cert-manager PKI in the *dashboard* repo (`mock-selfsigned` / `mock-ca` /
  `mock-ca-issuer` / `mock-tls`) is a separate, independently-named PKI for the mock OpenShift API
  and is **not** part of this rename.
- The dashboard's uncommitted `environments/crc.yaml` reporting changes and `mock-certmanager.yaml`
  are a separate PR track.
