# Docs content audit, batch 1 of 6: the chart's install and operate guides

Phase 2 of the documents pass (phase 1, PR #616, only moved files). Each of the six guides under
`charts/group-sync-dashboard/docs/` was read in full and every checkable claim was measured against
main at 0b86c40e (application 5.3.0, chart 0.70.4): the chart's values and templates (`helm template`,
Helm v4.3.0), the application under `local-development/gsd/`, the tree, the published Helm repository
and image attestations, and the lab (CRC, namespace `group-sync-dashboard`, read-only `oc get` and
`oc logs`). Line numbers are given outside backticks; they are those of 0b86c40e.

Verdicts:

- **CORRECT**: the claim matches the evidence.
- **FIXED**: the claim was wrong or stale, and the guide now says what the evidence shows.
- **NOT MEASURED**: no measurement was possible here (a historical value, a tool that is not installed, or a
  step that needs a cluster write). It was left unchanged.
- **CODE-SUSPECT**: the guide is right and the code is not. This batch found none.

The repository has no `values.schema.json`; value types and defaults were read from
`charts/group-sync-dashboard/values.yaml`.

## Totals

| document | claims checked | fixed | not measured | code-suspect |
|---|---|---|---|---|
| `HELM_DOWNLOAD_AND_INSTALL.md` | 51 | 7 | 11 | 0 |
| `RUNBOOK.md` | 29 | 1 | 3 | 0 |
| `CLUSTER_STANZA.md` | 16 | 1 | 1 | 0 |
| `CLUSTER_CREDENTIALS.md` | 24 | 1 | 4 | 0 |
| `UNMANAGED_GRANT_EXCLUSIONS.md` | 15 | 0 | 1 | 0 |
| `TROUBLESHOOTING_auditor_groups.md` | 11 | 2 | 1 | 0 |

## `HELM_DOWNLOAD_AND_INSTALL.md`

The page's opening note says that its version numbers, digests and revision are from chart 0.4.4 and
application 0.7.0. Those values were not re-measured and are not counted as stale. The commands and
the statements about how the chart behaves were measured.

| claim | verdict | evidence |
|---|---|---|
| the current releases are in the CHANGELOG (link `../../../docs/CHANGELOG.md`) | CORRECT | `docs/CHANGELOG.md` exists |
| run on 2026-08-12 with helm v3.14.0, oc 4.13.6, skopeo 1.20.0 | NOT MEASURED | historical; the commands were re-run here with Helm v4.3.0 |
| `skopeo inspect` digest `sha256:2afeae…` | NOT MEASURED | skopeo is not installed here |
| the direct-install path is in `docs/guides/reference-architecture.md` | CORRECT | the file exists |
| repository URL; `helm pull` of a version | CORRECT | `helm pull group-sync-dashboard --repo https://ephico2real2.github.io/group-sync-dashboard --version 0.70.4 --untar` succeeded |
| `helm repo update` is needed, or `helm pull` fetches a stale version | NOT MEASURED | Helm cache behaviour; no repository was added to this machine's Helm config |
| CHART VERSION tracks templates and defaults; APP VERSION is the release the chart deploys | CORRECT | `charts/group-sync-dashboard/Chart.yaml` lines 7-23 |
| "the chart version moves on every image build … the patch component is automated" | FIXED | `charts/group-sync-dashboard/Chart.yaml` line 12: "BUMPED BY HAND, IN THE PR THAT CHANGES THE CHART. It was briefly automated … that automation is gone". Now: it moves on every chart change and is bumped by hand |
| `--untar` gives Chart.yaml, README.md, values.yaml, and templates including deployment, ingress, oauth-secret, pdb, pvc, rbac, route, serviceaccount, trusted-ca | CORRECT | `ls` of the pulled 0.70.4 chart; there are 30 template files today, and "19 at 0.4.4" is historical |
| the Route is the default exposure; the Ingress is off | CORRECT | `values.yaml` lines 1922-1923 (`route.enabled: true`) and 1965-1966 (`ingress.enabled: false`) |
| `helm show chart`, `values` and `readme` work offline | CORRECT | all three ran on the pulled chart: `version: 0.70.4`, `appVersion: 5.3.0`, a 2602-line values file, `# group-sync-dashboard` |
| `grep -E '^  tag:' values.yaml` prints `tag: ""` | CORRECT | measured: `  tag: ""` |
| an empty tag means `appVersion`, through `default .Chart.AppVersion .Values.image.tag` | CORRECT | `charts/group-sync-dashboard/templates/_helpers.tpl` line 92 |
| `helm template … \| grep -m1 'image: quay'` names the dashboard image at appVersion | CORRECT | measured: `image: quay.io/ephico2real/group-sync-dashboard:5.3.0` |
| `imagePullPolicy: Always` | CORRECT | `values.yaml` line 60; the render has `imagePullPolicy: Always` |
| `/api/version` and `gsd_build_info` report the commit | CORRECT | `local-development/gsd/api.py` line 3337; `local-development/gsd/metrics.py` line 321 |
| charts 0.4.4 and earlier shipped a pinned tag | NOT MEASURED | historical; the `values.yaml` comment at line 16 says so |
| a plain `helm template gsd ./charts/group-sync-dashboard` fails with the ingress.host error | FIXED | measured: the default render exits 0. The error needs `--set route.enabled=false --set ingress.enabled=true`, which is now the command shown. Measured with those flags: `Error: execution error at (group-sync-dashboard/templates/serviceaccount.yaml:83:72): ingress.host is not set …` |
| the error text names three cases and explains the refusal | CORRECT | `charts/group-sync-dashboard/templates/_helpers.tpl` line 191 |
| an offline render with `ingress.host` set succeeds | CORRECT | measured: rc=0 |
| `--dry-run=server` runs the same `lookup` as a real install | CORRECT | Helm v3.14.0 `pkg/action/upgrade.go` lines 255-262: `interactWithRemote` is true for `DryRunOption == "server"` |
| `environments/crc.yaml` and `environments/example-production.yaml` are on main | CORRECT | both files exist |
| any `-f` or `--set` resets to chart defaults; with neither, Helm reuses the last values | NOT MEASURED | needs an upgrade of a release (a cluster write). The example's `apiTokenAccess` turned off because its default was off then; it defaults on today (`values.yaml` line 2181) |
| the container is `dashboard`, the sidecar `oauth-proxy`, the app binds 127.0.0.1:8080 | CORRECT | render: `--host 127.0.0.1 --port "8080"`. Lab: Deployment `group-sync-dashboard` has containers `dashboard` and `oauth-proxy` |
| `deploy/group-sync-dashboard` for the release `group-sync-dashboard` | CORRECT | `helm template group-sync-dashboard …` gives Deployment `group-sync-dashboard`; the lab has the same name |
| "the image it pins … `values.yaml` references `…:<appVersion>-<sha>`" | FIXED | `values.yaml` line 32: `tag: ""`. Now: an empty `image.tag` deploys `…:<appVersion>` |
| air-gapped: mirror the dashboard image | FIXED (added) | a default render names four images (`grep -oE 'image: [^ ]+' \| sort -u`): `group-sync-dashboard:5.3.0`, `group-sync-dashboard-report:5.3.0`, `ose-oauth-proxy-rhel9:v4.15` and `ose-cli-rhel9:v4.22`. Their keys are `reporting.image.repository` (`values.yaml` line 1254), `oauthProxy.image` (line 2049) and `secretsMint.image.repository` (line 881). The guide now names them, and its install command also sets `reporting.image.repository`; the render then shows both quay images at the mirror |
| `image.digest` wins over the tag; a malformed digest fails the render | CORRECT | `charts/group-sync-dashboard/templates/_helpers.tpl` lines 84-93 |
| `skopeo copy` keeps the digest | NOT MEASURED | skopeo is not installed |
| "A plain pipe, not `grep <(tar ...)`" | FIXED (removed) | the paragraph is about a `tar` pipe that the page no longer shows; the render-and-grep command replaced it |
| "Override `image.repository` only, never `image.tag`" | FIXED | this contradicts the page's own sha-form step and `values.yaml` line 22 ("SET IT to deploy a specific build"). Now: leave `image.tag` empty unless you mirrored the sha form |
| the switches `SUPPLY_CHAIN_SIGNING` and `SUPPLY_CHAIN_SBOM` are on by default | CORRECT | `.github/workflows/publish.yml` lines 342 and 419 (`!= 'false'`) |
| only `main` is signed (D9) | CORRECT | `.github/workflows/publish.yml` attest condition `github.ref == 'refs/heads/main'` |
| `cosign-release: v3.1.3`, `sigstore/cosign-installer` v4.1.2 | CORRECT | `.github/workflows/publish.yml` lines 458 and 462 |
| cosign v2 cannot read the v3 signature format (D7) | CORRECT | `docs/design/DESIGN_supply_chain.md` D7, lines 78-80; not measured with cosign, which is not installed |
| two images per push since application 0.18.0 | CORRECT | `docs/CHANGELOG.md` lines 1055-1057 |
| the SBOM artifacts are `sbom-<commit>` and `sbom-report-<commit>`, made by Syft 1.51.1 | CORRECT | `.github/workflows/publish.yml` lines 363, 367 and 377 |
| the `cosign verify` identity is `publish.yml@refs/heads/main` | CORRECT | `gh attestation verify oci://quay.io/ephico2real/group-sync-dashboard:5.3.0 … --format json`: `buildSignerURI` is `…/.github/workflows/publish.yml@refs/heads/main`. `cosign verify` itself was not run |
| `gh attestation verify` of the image succeeds, for both images | CORRECT | measured rc=0 for `group-sync-dashboard:5.3.0` and `group-sync-dashboard-report:5.3.0` |
| piped, `gh` prints nothing and exits 0 on success | CORRECT | the chart 0.17.0 verify printed nothing, rc=0 |
| 0.17.0 is the first attested chart; 0.16.0 has none | CORRECT | measured: 0.17.0 rc=0; 0.16.0 rc=1 |
| for an unattested chart, `gh` reports `no attestations found` | FIXED | gh 2.102.0 prints `Error: HTTP 404: Not Found (https://api.github.com/repos/…/attestations/sha256:c46ad258…)`. The guide now gives both forms |
| the `publish` job is skipped outside `ephico2real2/group-sync-dashboard` | CORRECT | `.github/workflows/publish.yml` line 114 |
| `:latest` follows the newest signed main build (D11) | CORRECT | `docs/design/DESIGN_supply_chain.md` line 126; the registry was not read |
| `gh` 2.49 or newer is needed | NOT MEASURED | only gh 2.102.0 is installed here |
| no GPG signature; `helm verify` is not supported | NOT MEASURED | stated in the design record; not exercised |
| the quick reference: render offline with no host | CORRECT | the default render exits 0 |
| the release-alias wording ("republished when the application version changes") | CORRECT | `values.yaml` lines 28-31 |
| the `-f my-values.yaml` install flow from the copy | NOT MEASURED | needs a cluster write |
| `--create-namespace` not exercised | NOT MEASURED | the page says so itself |
| install verified at revision 129 | NOT MEASURED | historical |

## `RUNBOOK.md`

| claim | verdict | evidence |
|---|---|---|
| the token Secret is `gsd-cluster-<name>` | CORRECT | `local-development/gsd/clusterconfig/writer.py` `secret_name_for`; the lab log shows `source=secret:gsd-cluster-mock-privateca` |
| Refresh and Rejoin need the cluster-admin tier and `clusterConfig.secrets.writes.enabled` | CORRECT | `local-development/gsd/api.py` lines 1378 and 1403 call `_writes_gate`; the tab's gate is the cluster-admin tier (#322). `values.yaml`: `writes.enabled` defaults to false |
| `REL=group-sync-dashboard` is the fullname | CORRECT | lab: Deployment `group-sync-dashboard` |
| Refresh probes with the held token, never logs in | CORRECT | `local-development/gsd/clusterconfig/writer.py` `refresh` docstring, lines 547-552 |
| the grep pattern `cluster-(unreachable\|refreshed) .*cluster=$C ` | CORRECT | `local-development/gsd/poller.py` lines 90-111 and `local-development/gsd/clusterconfig/writer.py` line 574 put `cluster=` before other fields. Lab lines have the shape `INFO gsd.clusterconfig cluster-resolved cycle=1 cluster=mock-privateca source=…` |
| outcome words: `ok` (shown as `connected`), `auth_failed`, `pending`, `forbidden`, `unreachable`, `cert-verify-failed`, `not-probed` | CORRECT | `local-development/gsd/kube.py` lines 361-364; `local-development/gsd/clusterconfig/writer.py` lines 540-541 and 570; `local-development/gsd/static/index.html` line 6486 |
| the `tls` chip reads `verified` / `verify failed` | CORRECT | `local-development/gsd/static/index.html` line 6577 |
| the poller identity is `system:serviceaccount:group-sync-operator:group-sync-dashboard-cluster-poller` | CORRECT | `local-development/gsd/config.py` lines 791-792; lab: `serviceaccount/group-sync-dashboard-cluster-poller` |
| the token Secret is `group-sync-dashboard-cluster-poller-token`, and a live one prints `invalid-since=` with nothing after it | CORRECT | `local-development/gsd/fleetlookup.py` line 191 (`f"{sa}-token"`). The doc's command on the lab printed `kubernetes.io/service-account-token  invalid-since=` |
| Rejoin asks `update clusterrolebindings` | CORRECT | `local-development/gsd/rejoin.py` line 183 |
| Rejoin refuses the fleet account's name | CORRECT | `local-development/gsd/rejoin.py` lines 153-155 |
| the annotations `rejoin-account`, `rejoined-at`, `rejoined-by`, `source-namespace`, `source-service-account`, `token-source` | CORRECT | `local-development/gsd/clusterconfig/writer.py` lines 35-80 |
| `managed-by` is kept by Rejoin | CORRECT | `local-development/gsd/clusterconfig/writer.py` line 378 |
| log lines `cluster-rejoined`, `cluster-rejoin-review`, `cluster-rejoin-failed` | CORRECT | `local-development/gsd/rejoin.py` lines 247, 274 and 318 |
| a Rejoin login is listed as a `cli` login | CORRECT | `local-development/gsd/auditlog.py` line 206: a login through `openshift-challenging-client` is `cli` |
| "`kubeadmin`'s logins are never listed" | FIXED | only `kube:admin` and `system:*` are never rows: `local-development/gsd/auditlog.py` lines 26-27 and 118 (`SYSTEM_NAMES = frozenset({"kube:admin"})`). The same docstring, lines 35-36, describes "a CLI `kubeadmin` row" with the break-glass label. On the lab, `kubeadmin` is an HTPasswd user (`identities=["developer:kubeadmin"]`, IdP `developer=HTPasswd`), so its logins are rows, labelled by `local-development/gsd/api.py` line 2135. Now: `kube:admin` is never listed, and an HTPasswd `kubeadmin` is listed with the break-glass label. No live row was read: that needs the API or the pod's database |
| the §4 codes `sa-token-secret-missing`, `sa-token-invalidated`, `not-cluster-admin`, `login-failed` | CORRECT | all four are in `local-development/gsd/rejoin.py` |
| a trust fix is `tlsClientConfig.caData` or the chart's `trustedCA` | CORRECT | `local-development/gsd/config.py` line 427; `values.yaml` `trustedCA` |
| the manual fallback writes the whole `config` JSON | CORRECT | the Secret contract's keys are `bearerToken` and `tlsClientConfig` (`local-development/gsd/clusterconfig/parser.py` line 45); the commands were not run (they are writes) |
| `discoveryIntervalSeconds` defaults to 300 | CORRECT | `values.yaml` line 311; `local-development/gsd/config.py` line 593 |
| a locked LDAP account answers code 19 as HTTP 500 | NOT MEASURED | needs a directory lockout |
| `useroauthaccesstokens` with `clientName=openshift-challenging-client` | CORRECT | the client the logins use (`local-development/gsd/auditlog.py` line 83); the command was not run on a remote |
| the fleet Lease `gsd-fleet-…`, annotation `groupsync-dashboard.io/refused`, label `lease-type=fleet-account` | CORRECT | `local-development/gsd/fleetstate.py` lines 64-111. Lab: the label selector returns `lease.coordination.k8s.io/gsd-fleet-666f1ba7f2fdead0` |
| `/data/fleet-gate.json`, or `/data/<pod>/fleet-gate.json` above one replica | CORRECT | `local-development/gsd/fleetstate.py` line 75; `local-development/gsd/poller.py` line 974 puts it beside the database, and `charts/group-sync-dashboard/templates/deployment.yaml` lines 234-240 set `/data/gsd.db` or `/data/$(POD_NAME)/gsd.db` |
| `fleet-lease-absent` with `kept=true` / `kept=false` and `refused=` | CORRECT | `local-development/gsd/fleetstate.py` lines 349 and 364 |
| `fleet-state-unavailable`; `fleet-ping-failed … gave_up=true`; `login-refused`; `self-login-suspended` | CORRECT | `local-development/gsd/fleetstate.py` line 102; `local-development/gsd/poller.py` lines 1822-1823; all four codes are in the application |
| SPEC_S4f §3.9 | CORRECT | `docs/specs/SPEC_S4f_fleet_gate_backstop.md` line 375 |
| `crc start` deletes every Lease | NOT MEASURED | needs a CRC restart |
| `persistence.enabled: false` keeps the copy only for the pod's life | NOT MEASURED | behaviour, not exercised; the key exists (`persistence.enabled`, default true) |

## `CLUSTER_STANZA.md`

| claim | verdict | evidence |
|---|---|---|
| only cluster administrators can open the Cluster Configurations tab | CORRECT | `local-development/gsd/api.py` line 1213: the cluster-admin tier (#322) |
| the `shared API URL` chip, and warnings served apart from findings | CORRECT | `local-development/gsd/static/index.html` line 6619; `local-development/gsd/api.py` line 1191 (`"warnings"`) |
| the link `local-development/API.md` with anchor `get-apiclusterconfigs` | CORRECT | `local-development/API.md` line 174, heading `GET /api/clusterconfigs` |
| ConfigMap onboarding: the `onboard` or `sideload` label, only `data.clusters.yaml`, no `binaryData`, duplicate YAML keys refused | CORRECT | `local-development/gsd/clusterconfig/onboarding.py` lines 29 and 84-94 |
| no credential reference; `saTokenLookup: true` required; the host only in values | CORRECT | `local-development/gsd/config.py` lines 1697-1706 |
| ConfigMap cleanup, gating and conflict behaviour | NOT MEASURED | behaviour across discovery cycles; the finding codes it names exist in `local-development/gsd/clusterconfig/onboarding.py` |
| the matrix test exists and holds the tables | CORRECT, with a gap | `local-development/tests/test_cluster_stanza_matrix.py` holds §4 and §5's first 21 rows. The last four rows of §5 are not in it; those were rendered by hand (below). Reported to the orchestrator, not changed |
| §1's thirteen keys | CORRECT | `local-development/gsd/config.py` lines 346-349 (`VALUES_CLUSTER_KEYS`) |
| renaming retires the cluster: 33 tables key on it | CORRECT | a fresh `Store` has 35 tables, 33 of them with `cluster_id` (all but `cluster` and `dashboard_user_activity`) |
| §2's credential kinds | CORRECT | `local-development/gsd/config.py` lines 329-333 and 441-450 |
| §3's TLS order | CORRECT | `local-development/gsd/config.py` lines 425-432 |
| fourteen accepted combinations | CORRECT | the matrix test passes (run below) |
| "Seventeen refusals fail `helm template`" | FIXED | the table has 21 rows refused at render. The 17 stanza rows are held by the test. The four chart-setting rows were rendered here, and each fails: `… declares saTokenLookup but clusterConfig.secrets.writes.enabled is false`; `… but clusterConfig.secrets.enabled is false`; `clusterConfig.secrets.writes.enabled with replicaCount 2 …`; `cluster r declares userSelfLogin with replicaCount 2 …`. The last two were rendered with `reporting.enabled=false` and `leaderElection.enabled=false`, so that the replica guards of those features did not fire first. Now: twenty-one |
| four refusals only at pod startup | CORRECT | the matrix test passes |
| the Secret form refuses Argo's keys by name | CORRECT | `local-development/gsd/clusterconfig/parser.py` lines 32-41 |
| `charts/group-sync-dashboard/example-production.yaml` is the worked example | CORRECT | the matrix test loads and renders it |

## `CLUSTER_CREDENTIALS.md`

| claim | verdict | evidence |
|---|---|---|
| generated Secrets carry `secret-type: cluster` | CORRECT | `local-development/gsd/clusterconfig/__init__.py` line 12 |
| `managed-by: configmap-onboarding`, `source-configmap`, `source-configmap-uid`, `connection-hash` | CORRECT | `local-development/gsd/clusterconfig/writer.py` lines 39-43 |
| `insecureSkipVerify: true` is accepted from a ConfigMap | CORRECT | the ConfigMap boundary (`local-development/gsd/config.py` lines 1697-1706) does not refuse it |
| the Lease is `gsd-fleet-<sha256(username)[:16]>` | CORRECT | `local-development/gsd/fleetstate.py` lines 110-111; the lab Lease name has that form |
| the retrieval and ping symbols | CORRECT | `local-development/tests/test_docs_citations.py` resolves them (run below) |
| the retrieved token has no `exp` | NOT MEASURED | reading a token is out of bounds here |
| `oc create token --duration` has a 10-minute minimum | NOT MEASURED | an upstream API rule; creating a token is a write |
| the self-login margin `expires_at − min(2 h, ¼ × expires_in)` | CORRECT | `local-development/gsd/selflogin.py` lines 56 and 70-71 |
| `oauth` is refused as `oauth-exchange-not-built` | CORRECT | `local-development/gsd/clusterconfig/reader.py` line 44 |
| retrieval annotations `managed-by: sa-token-lookup` and `lookup-account` | CORRECT | `local-development/gsd/clusterconfig/writer.py` lines 39 and 54 |
| the outcome words live in `local-development/gsd/kube.py` | CORRECT | lines 361-364 |
| a 401 reads "invalid or expired" | CORRECT | `local-development/gsd/kube.py` line 615 |
| the measured discovery delays (8m30s, 3m42s, 4m08s) | NOT MEASURED | historical |
| the link to `docs/design/polling-and-discovery.md` | CORRECT | the file exists |
| Refresh probes `GET /version`, then `users/~` | CORRECT | `local-development/gsd/clusterconfig/writer.py` lines 497-506 |
| Refresh exists only for administrators with writes on | CORRECT | `local-development/gsd/api.py` lines 1378-1385 (`_writes_gate`) |
| the refresh and rejoin routes | CORRECT | `local-development/gsd/api.py` lines 1378 and 1403 |
| Rejoin is offered "on a Secret-sourced cluster or a `saTokenLookup` stanza" | FIXED | `local-development/gsd/rejoin.py` lines 126-131 refuse a ConfigMap-declared cluster ("a ConfigMap declares it, and its Secret is generated from the stanza there"), and that cluster is a `saTokenLookup` stanza too. Now: a values `saTokenLookup` stanza, never a ConfigMap-declared one |
| Rejoin writes `token-source: rejoin` and never `lookup-account` | CORRECT | `local-development/gsd/clusterconfig/writer.py` lines 75 and 398-401 |
| D4-7, the per-pod memory gate | CORRECT | `docs/specs/SPEC_D4_cluster_rejoin.md` lines 62 and 100 |
| the revoke path, `fleet-logout-failed`, and the "fleet-logout line could not be written" fallback | CORRECT | `local-development/gsd/fleetlogin.py` lines 143, 678 and 686 |
| the lab's `accessTokenMaxAgeSeconds` is 31536000 | CORRECT | measured today: `{"accessTokenMaxAgeSeconds":31536000}` |
| the token-object counts (131 of 189; two fleet objects) | NOT MEASURED | dated measurements of 2026-09-27, left as dated |
| the `DESIGN_session_and_signout.md` references | CORRECT | the file exists, and the citation test resolves its anchors |

## `UNMANAGED_GRANT_EXCLUSIONS.md`

| claim | verdict | evidence |
|---|---|---|
| the log line `UNMANAGED GRANT DISCOVERED` at WARNING | CORRECT | `local-development/gsd/poller.py` line 858; present in the lab log |
| `GET /api/clusters/<id>/bindings/findings?finding=unmanaged` | CORRECT | `local-development/gsd/api.py` lines 2326 and 2337 |
| the `/metrics` finding label `unmanaged` | CORRECT | `local-development/gsd/metrics.py` line 41 |
| the label `rbac.ocp.io/config-source`, the annotation `rbac.ocp.io/unmanaged-exception`, the label `rbac.ocp.io/unmanaged` | CORRECT | `local-development/gsd/kube.py` lines 309-310 and 345 |
| `group-sync-dashboard` and `group-sync-operator-helm` are provenance only | CORRECT | `local-development/gsd/kube.py` lines 314-323; `charts/group-sync-dashboard/templates/_helpers.tpl` lines 33-35. The operator chart's `group-sync-operator-helm.rbacLabels` was added in its 0.14.1 (commit 5a18b07, `version: 0.14.0` to `0.14.1`) |
| the lab's `baseline-nonprod-rbac` and `baseline-cluster-rbac` | CORRECT | lab: 28 RoleBindings `baseline-nonprod-rbac`, 12 ClusterRoleBindings `baseline-cluster-rbac` |
| the platform namespaces | CORRECT | `local-development/gsd/home.py` lines 38-39 |
| the three controller bindings | CORRECT | `local-development/gsd/home.py` lines 48-49 and the comment from line 40 |
| the platform users | CORRECT | `local-development/gsd/config.py` lines 237-251 |
| the `platformNamespaces` and `platformUsers` keys, with `existingConfigMap.revision` | CORRECT | `values.yaml` keys `additionalPrefixes`, `additionalSuffixes`, `additionalNames`, `existingConfigMap {enabled, name, key, revision}` |
| `bindingIntervalSeconds` defaults to 3600 | CORRECT | `values.yaml` `config.bindingIntervalSeconds: 3600` |
| a values change restarts the pod | CORRECT | `charts/group-sync-dashboard/templates/deployment.yaml` line 148 (`checksum/config`) |
| the design and spec paths | CORRECT | `docs/design/unmanaged-audit-design.md` and `docs/specs/SPEC_U1_unmanaged_subjects.md` exist |
| `git grep "PLATFORM-CLASSIFICATION"` lists the rule | CORRECT | 22 files carry the marker |
| the Access granted, Namespace audit and alert counting | NOT MEASURED | UI behaviour; needs a signed-in session |

## `TROUBLESHOOTING_auditor_groups.md`

| claim | verdict | evidence |
|---|---|---|
| the design and research paths | CORRECT | `docs/design/DESIGN_reporting_auditors_and_ns_selector.md` and `docs/research/FINDINGS_auditor_group_ldap_sync_interaction.md` exist |
| the guard's error text | CORRECT | `charts/group-sync-dashboard/templates/rbac-auditors.yaml` line 75 |
| the guard uses `lookup` of the Group | CORRECT | `charts/group-sync-dashboard/templates/rbac-auditors.yaml` line 65 |
| "Helm still records a **failed revision**; `helm status` will read `failed`" | FIXED | from the Helm source, not from a cluster (that needs a failing upgrade, which is a write). Helm v3.14.0 `pkg/action/upgrade.go` lines 156-159 and 262-264 return the render error from `prepareUpgrade`; `Releases.Create` is only at line 357, in `performUpgrade`. Helm v4.3.0 is the same: render error at lines 302-304, `Releases.Create` at line 409. Now: no revision is recorded, `helm status` still reads `deployed`, and the rollback alternative is gone |
| the GroupSync `app-ocp-rbac-group-groupsync` in `group-sync-operator` has `lastSyncSuccessTime` | CORRECT | lab: `2026-10-05T07:30:00Z` |
| `deploy/group-sync-operator-controller-manager -c manager` | CORRECT | lab: containers `kube-rbac-proxy` and `manager` |
| the log strings `Failed to Complete Sync` and `did not match sync host` | CORRECT | in the group-sync-operator source (`internal/controller/groupsync_controller.go` line 120; `pkg/provider/ldap/helpers/groupsyncer.go` lines 161-165) |
| the force-sync script runs as `setup-local-ldap-testing/60-force-groupsync.sh` | FIXED | the script is not in this repository's tree or history; it is in the group-sync-operator-helm-chart repository, with the usage `60-force-groupsync.sh <groupsync-name> [namespace]`. Now the guide names that repository |
| the ownership markers and their values | CORRECT | operator source `pkg/provider/ldap/helpers/consts.go` lines 8-13 and `pkg/constants/constants.go` line 9; the label value is `<CR>_<provider name>`. Lab group `app-ocp-rbac-groupsync-ns-auditor`: `sync-provider=app-ocp-rbac-group-groupsync_ldap`, `ldap.host` label, `ldap.url` `…:636`, `ldap.uid` the group DN |
| `group-sync-dashboard/managed: local` | CORRECT | `charts/group-sync-dashboard/templates/rbac-auditors.yaml` line 88 |
| one group it cannot reconcile fails the whole run | NOT MEASURED | not reproduced; the operator source returns a hard error on a host mismatch (above) |

## Findings for the orchestrator (no change made)

1. **A test gap, not a defect.** `local-development/tests/test_cluster_stanza_matrix.py` says that every
   row of the guide's tables is a case. It has no case for the last four rows of §5 (`saTokenLookup`
   without writes, `saTokenLookup` without discovery, writes with `replicaCount > 1`, `userSelfLogin`
   with `replicaCount > 1`). They were measured by hand here and are correct today.
2. **Two specs say the same wrong thing about `kubeadmin`.** `docs/specs/SPEC_D4_cluster_rejoin.md`
   lines 433 and 762 say "`kubeadmin` is never a Logins row (`gsd/auditlog.py#SYSTEM_NAMES`)". On
   the lab, `kubeadmin` is the HTPasswd user `developer:kubeadmin`, and `SYSTEM_NAMES` holds only
   `kube:admin`. Line 2787 quotes the runbook sentence corrected here. The specs are out of this
   batch's scope and were left unchanged.
