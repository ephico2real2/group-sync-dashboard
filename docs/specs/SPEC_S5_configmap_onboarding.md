# SPEC S5 — ConfigMap cluster onboarding: credential-free declarations, owned Secrets (#293)

| | |
|---|---|
| Programme | Cluster configuration, continued: a runtime values-shaped feeder for S4b's remote lookup |
| Batch | S — cluster configuration |
| Release | — (post-programme; independently reviewed after #284) |
| Version on release | app 0.34.0, chart 0.55.0 |
| Issue | [#293](https://github.com/ephico2real2/group-sync-dashboard/issues/293) |
| Status | merged |
| Source | Codex phase-1 specification, 2026-09-25, against main 35fcddb; operator comments in issue-293.md and supplied lab-snapshot.md; phase-2 blocks re-anchored after #361/#360, applied and checked locally; see phase2-report.md for limits |

## How to read this spec

The research citations refer to the unmodified `35fcddb` files (paths relative to the repository;
`issue-293.md` and `lab-snapshot.md` are the supplied workspace evidence). New behavior below is a
**design decision**, not a claim that it already ships. Section 6 is the complete patch in the
format defined at `docs/specs/README.md:33`; the exact-match checker is
`local-development/apply-spec-blocks.py:67`. Phase 1 adds this document and its index row only.
Phase 2 applies reviewed blocks and runs tests. No phase-1 test result or live validation is implied.

## Orchestrator's notes

- S5 is the next independent S design, not a step of the S4 credential-lifecycle work. The S4c row
  remains specified; S5 uses the shipped S4b. The new index row sits after S4c and before D2b to
  preserve the index's enforced issue ordering (`local-development/tests/test_specs_index.py:94`).
  The count and S issue-set updates are **blocks**, so those tests intentionally await phase 2.
- Phase 2 (operator, 2026-09-25) reads `Chart.yaml` chart 0.54.0 / appVersion 0.33.0 and
  `local-development/pyproject.toml` app 0.33.0 after #361/#360. Blocks 57–60 assign the next
  minors: app 0.34.0 / chart 0.55.0. Blocks 78–80 move S4c's header/index to app 0.35.0 /
  chart 0.56.0 and set S5's index; blocks 55–56 keep the index count and S issue-set checks.
- Final review decisions (operator, phase-2 request, 2026-09-25; `grok1/report.md` C1–C8):
  - TLS ruling: "I need this feature badly. So insecure is required in configmap." The refusal
    and allow-list proposals are superseded. `insecureSkipVerify: true` stays accepted; existing
    declared-trust and writer code preserve it in the generated Secret. Block 31 tests this;
    blocks 61/63 document it. Whoever can write a labelled ConfigMap in the release namespace
    can direct the fleet account's bind to a host of their choosing, with or without TLS
    verification. ConfigMap write access there is therefore trusted like the fleet credential,
    and the platform team must keep it restricted.
  - Grok C1: block 2 refuses the three controller DNS aliases at any port and the values host's
    scheme/hostname/effective port; block 31 tests aliases and the host endpoint. The operator's
    2026-09-24 ruling reserves those DNS names for the controller. A physical-cluster match via
    a different external URL (shared-rnd by design) remains allowed and tested.
  - Grok C4: block 30 reserves valid names for cleanup but authors only successfully parsed and
    validated stanzas. Block 31 removes invalid-map from duplicates and proves invalid input
    cannot stop a values cluster; block 61 states the distinction.
  - Grok C8: block 61 states the bound-failure/success gate, pre-write retry, restart/replica
    limits and #285 deferral exactly; block 62 lists every cleanup ownership condition.
  - Grok C7: block 31's Host applies the supplied selector, both Settings paths use load_settings,
    and the bind test covers five discovery cycles and authorize-403 (credential phase).
  - Grok C2: section 3.3 states the per-process budget table with each row's named test.
  - Phase-2 verification: block 81 updates the existing exact API-row assertion for nullable
    provenance. Block 66 now names the actual release and applies C8's precise budget to the
    changelog too. Block 31 supplies enough mock responses for repeated values/restart attempts;
    its host tests check the parser directly as well as the no-bind discovery outcome.
- The operator requires baseline `file:line` citations. A narrow block exempts this pinned,
  point-in-time spec from the line-number prohibition only; all path/anchor checks and other docs
  stay covered (`local-development/tests/test_docs_citations.py:424`). Runtime documentation uses
  paths rather than pinned line citations.
- The older S1 design body says first-Secret-wins (`docs/specs/SPEC_S1_cluster_secrets.md:228`);
  the shipped code instead refuses both (`local-development/gsd/clusterconfig/reader.py:92`).
  This design follows the shipped rule. The shipped label-last fix already exists at
  `local-development/gsd/clusterconfig/writer.py:144`; no duplicate fix is proposed.
- The supplied issue file contains comments beginning with the synonym decision, including the
  later label-key correction (`issue-293.md:151`). Its full comments were read. A separate issue
  body could not be fetched: `gh issue view 293 --repo ephico2real2/group-sync-dashboard --json
  title,body,url` answered `error connecting to api.github.com`. It is **not measured** here.
- There is no `.codegraph/` in `wt/`; CodeGraph was therefore skipped under the supplied AGENTS rule.
  No git write command is part of phase 2. The reviewed blocks are applied and verified as recorded
  in the workspace `phase2-report.md`; baseline research citations remain pinned to phase 1.

## 1. Research ledger — evidence before design

| Evidence | What it establishes and why it matters |
|---|---|
| `issue-293.md:6`, `:65`, `:91`, `:151`, `:181` | Both synonyms are required; the correction is config-type on ConfigMaps; Secret label remains cluster; label-last is required; non-secret declaration / fetched Secret is the intended pattern. Earlier same-key proposals are superseded. |
| `local-development/gsd/clusterconfig/__init__.py:12` | Secret label and selector are constants; the closed finding vocabulary begins at line 18. Add ConfigMap constants beside them without changing LABEL_SELECTOR. |
| `local-development/gsd/clusterconfig/reader.py:69`, `:76`, `:92`, `:116` | Namespace-scoped paged LIST; deterministic parsing; duplicate Secrets load neither; Secret-versus-values currently shadows. ConfigMap conflicts need explicit suppression, not an accidental change to ordinary shadowing. |
| `local-development/gsd/clusterconfig/reader.py:5`, `:63`; `local-development/gsd/poller.py:1401` | Reader returns findings; poller logs transitions. Reuse that mechanism to avoid repeated standing warnings. |
| `local-development/gsd/clusterconfig/parser.py:45`, `:65`, `:111`, `:137`, `:158`, `:172`, `:237` | Closed config keys; no echo of arbitrary keys; host protection; controller refusal; JSON/TLS validation. Eventual generated Secrets must pass this same validator before binding. |
| `local-development/gsd/config.py:233`, `:1428`, `:1448`, `:1489`, `:1577` | Values have a closed key set, embedded stanza parsing, credential/mode exclusivity and second-pass host rules. Extract, do not duplicate, that parser. `labels` is not a values stanza key on this base. |
| `local-development/gsd/config.py:841`, `:852`, `:872`; `local-development/gsd/clusterconfig/registry.py:59` | Host comes from values; effective clusters merge through one locked registry; policy defaults already resolve centrally. A blocked-name set is necessary to stop values fallback after a runtime conflict. |
| `local-development/gsd/clusterconfig/writer.py:128`, `:144`, `:168`, `:239` | Existing Secret shape, unconditional cluster label, parse-before-write, existing-name and POST-409 refusals. Add provenance to this writer, not a second Secret serializer. |
| `local-development/gsd/clusterconfig/writer.py:217`, `:266`, `:279`, `:320`, `:366` | General ownership is only the label; rotate uses resourceVersion; lookup can update a declaring Secret; delete currently uses only name. Automatic ConfigMap ownership must be stricter and delete must gain preconditions on its own path. |
| `local-development/gsd/fleetlookup.py:97`, `:108`, `:121`, `:337`, `:359`, `:370` | The gate lives in memory, keyed by canonical target/account/password digest; bound login failures gate; pre-bind failures can retry. Successful sessions currently do not gate. State that limit, do not claim otherwise. |
| `local-development/gsd/fleetlookup.py:193`, `:216`, `:286`, `:304`, `:346` | Password read, remote token read by name, declaration's TLS, existing create/store_lookup paths, and the write switch before any password read. These stages are reused. |
| `local-development/gsd/fleetlogin.py:364`, `:500` | Session exit revokes its own token; a post-write read timeout is bound and terminal. ConfigMap onboarding must not turn that into another login. |
| `local-development/gsd/poller.py:910`, `:1353`, `:1457`, `:1464`, `:1489`, `:1496`, `:1510`, `:1580`, `:1596` | One process-lifetime gate, discovery startup/cadence, retirement, threads, existing retry key and lookup scheduler, leader/replica admission. Keep them rather than adding a second scheduler. |
| `local-development/gsd/kube.py:644`, `:1290` | Existing request/redaction and complete paginated-list helper; the new feeder calls these. |
| `charts/group-sync-dashboard/templates/cluster-secrets-rbac.yaml:1`, `:18`, `:21`; `charts/group-sync-dashboard/values.yaml:1429` | Release-namespace Role, read-only default and existing conditional Secret write verbs. Add only configmaps get/list/watch; preserve the write conditional. |
| `local-development/gsd/api.py:1125`, `:1141`, `:1176`, `:1279`; `local-development/gsd/static/index.html:6026`, `:6049`, `:6110`, `:6141` | Protected wire surface; generic finding renderer; current source and write controls. Add ConfigMap provenance and prevent misleading generated-output controls. |
| `docs/specs/SPEC_S1_cluster_secrets.md:233`, `:250`, `:270`; `docs/specs/SPEC_S2_cluster_configurations_tab.md:92`, `:228`, `:251`, `:285` | Cadence/no-watch decision, failure/retirement and no-credential exposure; UI writes/tier and write wake-up. Current code wins over superseded body statements. |
| `docs/specs/SPEC_S3_connection_modes.md:237`, `:269`, `:691`, `:706`, `:752`, `:918` | Shared stanza discipline; level-triggered reconciliation; ownership is bookkeeping, raw data identity and UID/RV delete preconditions; lockout risk. Borrow these requirements, not the stale vocabulary. |
| `docs/specs/SPEC_S4b_sa_token_lookup.md:25`, `:43`, `:76`, `:122`, `:323`, `:783`, `:937`, `:1281`, `:1696`, `:1994`, `:2859`, `:2942` | One grant/switch; declared trust; discovery-thread schedule; review's lockout corrections; reader/writer/lookup/test implementation model; deferred durable gate and #293 seam. |
| `docs/CLUSTER_STANZA.md:14`, `:35`, `:90`, `:136`; `docs/polling-and-discovery.md:30`, `:46`, `:70`, `:96`; `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md:10`, `:36`, `:72`, `:100` | Existing public key/mode/refusal matrices, timing measurements and credential/recovery limits. Extend these documents without calling historic measurements a ConfigMap test. |
| `local-development/API.md:141`, `:200`, `:211`; `docs/specs/README.md:33`, `:94`, `:115`; `local-development/apply-spec-blocks.py:24`, `:43`, `:67` | API compatibility, status/version lifecycle and exact block grammar/check-only semantics. The checker does not execute the proposed code. |
| `local-development/tests/test_specs_index.py:49`, `:94`, `:108`; `local-development/tests/test_clusterconfig.py:427`; `local-development/tests/test_clusterconfig_tab.py:671` | Index count/issue-set and exact chart grants need explicit test blocks; weakening assertions is not necessary. |

Primary upstream research (read 2026-09-25): [Kubernetes label selectors](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/#set-based-requirement)
allow a set of values in one selector. [DeleteOptions](https://kubernetes.io/docs/reference/kubernetes-api/definitions/delete-options-v1-meta/)
refuses unmet preconditions with 409; [Preconditions](https://kubernetes.io/docs/reference/kubernetes-api/definitions/preconditions-v1-meta/)
provides UID and resourceVersion. [ExternalSecret](https://external-secrets.io/latest/api/externalsecret/)
separates a declaration from a generated Secret. The inference for #293 is to reuse that separation
without importing ESO, a CRD, informer, controller framework or a new registry. The Argo comparison
is the already-recorded reasoning in `issue-293.md:197` and `docs/specs/SPEC_S4b_sa_token_lookup.md:2962`:
our declaration contains no kubeconfig or token, while the generated credential remains a Secret.

## 2. The four decisions

1. **Label discovery, any number of ConfigMaps.** One paginated LIST in the release namespace uses
   `groupsync-dashboard.io/config-type in (onboard,sideload)`. No fixed name, priority, secondary
   scan, or warning for a synonym. This matches Secret discovery and lets a platform repository
   split or replicate its stanzas without configuring names in Helm (`issue-293.md:151`;
   `local-development/gsd/clusterconfig/reader.py:76`; Kubernetes selectors above).
2. **Removal repeatedly prunes owned outputs.** A complete, valid inventory proving a declaration
   absent makes its generated Secret ineligible for polling immediately; every later cycle attempts
   cleanup until that Secret is absent. Entry removal, whole-map removal, label removal and UID
   replacement all count. Failed cleanup is a standing finding; a restart re-lists and retries.
   Malformed documents are not removal evidence. This avoids the one-shot set-change failure and
   silently orphaned credential described by the operator, while preserving history through existing
   retirement (`docs/specs/SPEC_S3_connection_modes.md:691`, `:752`;
   `local-development/gsd/poller.py:1457`; `local-development/gsd/clusterconfig/registry.py:33`).
3. **Duplicates load neither, with each author named.** Reserve a syntactically valid cluster name
   for cleanup even if its stanza is invalid; only successfully parsed and validated stanzas author
   names for conflicts. Invalid stanzas never block values. Values-versus-ConfigMap, map-versus-map, same-map
   duplicates and unrelated labelled Secrets are conflicts. Suppress the name in the existing
   registry merge and stop a running values thread; returning a finding alone would fall back to
   values. The values host is protected first: a refused host declaration cannot switch off the
   dashboard's authentication anchor. Ordinary Secret/values shadowing remains unchanged where
   there is no ConfigMap author (`local-development/gsd/clusterconfig/reader.py:92`, `:116`;
   `local-development/gsd/clusterconfig/registry.py:70`; `local-development/gsd/config.py:852`).
4. **Distinct ownership; no adoption.** A generated Secret has `managed-by: configmap-onboarding`,
   `token-source: remote-lookup`, source ConfigMap name/UID and a connection digest, all set in its
   initial POST. Eligibility also checks `secret-type=cluster`, data.name and the deterministic
   Secret name. Each mutation re-reads the Secret and verifies UID/resourceVersion plus ownership;
   DELETE carries both preconditions and PUT the observed version. UI, hand-made and values-lookup
   Secrets are never adopted or automatically overwritten. A colliding physical Secret name is
   refused before binding. An annotation is forgeable by a namespace writer; it is bookkeeping,
   not authentication (`local-development/gsd/clusterconfig/writer.py:144`, `:217`, `:239`, `:266`;
   `docs/specs/SPEC_S3_connection_modes.md:706`; Kubernetes preconditions above).

## 3. Proposed contract and implementation seams

### 3.1 Input and parser

`data.clusters.yaml` contains a YAML object whose sole key is `clusters`, a list of values-shaped
stanzas. `clusters: []` is an intentional empty desired set. Refuse duplicate YAML keys, extra data
keys, binaryData and malformed envelopes without echoing their contents. The exact sample is in the
CLUSTER_STANZA documentation block. This chooses one predictable file shape consistent with the
existing values envelope (`local-development/gsd/config.py:1444`; `docs/CLUSTER_STANZA.md:14`).

Extract the values loop and second pass into `config.parse_cluster_entries`, then have both
`load_settings` and the ConfigMap reader call it. The ConfigMap invocation supplies the known values
host: never infer a host from the first remote entry. In-cluster controller DNS aliases (any port)
and the values host's scheme/hostname/effective port are refused. A different external URL of the
same physical cluster remains allowed (operator, 2026-09-24; Grok C1). In that same parser refuse any `tokenEnv` or
`tokenFile` key, require `saTokenLookup: true`, and protect host name/controller/in-cluster URL.
Unknown keys (including tokens/passwords/labels) still fail the same known-key test. Cross-stanza
conflicts are handled by the reader, since startup rejection cannot be used on a live feed
(`local-development/gsd/config.py:1450`, `:1458`, `:1489`, `:1577`).

Before a login, validate the generated shape through `writer.validate`/`parse_secret` with a dummy
noncredential token; this enforces DNS-name, HTTPS endpoint and PEM rules that are stricter than old
values loading. Its parsed name must equal the values-parsed name; whitespace must not silently change
identity. Name reservation uses the same string coercion as values, including numeric YAML scalars.
No input-to-Secret translation is silently assumed. `caBundleFile` is a pre-existing
container path, not an instruction to fetch/mount a new file. ConfigMap-specific refusal text omits
all supplied values and arbitrary keys; unrelated good entries can proceed
(`local-development/gsd/clusterconfig/writer.py:168`; `local-development/gsd/clusterconfig/parser.py:130`,
`:135`, `:237`; `local-development/gsd/fleetlookup.py:286`).

### 3.2 Discovery, updates, failure and ownership

Use `onboarding.discover_onboarding` at the existing poller discovery call site. Finish both paged
LISTs before any mutation; failures leave the previous registry and block lookup from stale intent.
Feed the already-listed eligible raw Secrets to the **existing** `reader.discover(items=...)`.
Pending declarations join that reader's result as `ClusterConfig` objects, so `_retrieve_pending`
remains the only login scheduler. The registry gains only an atomic blocked-name set; no second
registry or configuration service (`local-development/gsd/poller.py:1377`, `:1496`;
`local-development/gsd/clusterconfig/registry.py:26`; `local-development/gsd/kube.py:1290`).

The connection digest covers canonical URL, declared trust bytes/mode, effective bootstrap account
and remote SA token address. It excludes policy and the password. Policy/enable edits update only
the owned output's policy keys and immediately serve the declaration's policy even if the PUT fails;
no bind. Changing connection inputs or drifting endpoint/trust retires and deletes the old output;
a fresh LIST must observe absence before create is attempted. Generated credential changes are not
health recovery; no new remote probe or automatic auth-failure repair is added (#285/#316 remain
separate). These choices extend `fleetlookup.declared_trust` and the existing policy overlay pattern
(`local-development/gsd/fleetlookup.py:286`; `local-development/gsd/clusterconfig/registry.py:74`;
`charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md:100`).

A malformed whole document holds outputs from that ConfigMap without polling them; an identifiable
invalid stanza holds that stanza's output. An unidentifiable malformed entry conservatively freezes
cleanup of its map's outputs. A conflicted name holds its credentials with findings, never polls
any contender, and does not bind. Once corrected/removed, current inventories decide again. No
ownerReference/finalizer is used: cleanup stays under the existing write switch rather than asking
Kubernetes GC to delete when that switch is off (`docs/specs/SPEC_S3_connection_modes.md:691`, `:706`;
`local-development/gsd/clusterconfig/writer.py:366`; `charts/group-sync-dashboard/templates/cluster-secrets-rbac.yaml:21`).

All automatic writes require the existing discovery and writes switches, leadership, and the existing
single-retriever replica guard. Both feeds use `clusterConfig.secrets.enabled`, following S4b's one
capability/explicit-intent rule rather than a new toggle that repeats it. Read-only deployments may
observe declarations/findings. Cleanup cannot finish while writes are off: displaced outputs remain
visible as cleanup-pending and do not poll. Discovery off means no reads or reconciliation at all;
operators must drain declarations before disabling it. Add only ConfigMap `get/list/watch` in the
same release-namespace Role; the application currently uses LIST, while get/watch retain the Secret
feed's read contract. No ConfigMap writes or cluster-scoped grant
(`docs/specs/SPEC_S4b_sa_token_lookup.md:25`; `local-development/gsd/fleetlookup.py:346`;
`local-development/gsd/poller.py:1510`; `charts/group-sync-dashboard/templates/cluster-secrets-rbac.yaml:18`).

### 3.3 Bind budget — measured baseline and explicit guarantee

The existing gate is constructed once per Poller, survives source/shape changes and uses canonical
(target, account, password digest). Bound login failures mark it; pre-bind TLS/connect failures may
retry. This is **not** a measured global account-wide or success-inclusive one-bind guarantee:
success followed by a failed token read/write does not mark the baseline gate
(`local-development/gsd/poller.py:910`; `local-development/gsd/fleetlookup.py:97`, `:359`, `:367`, `:380`).

For ConfigMap-triggered lookups, additionally mark the **same** gate immediately upon successful
session entry, before `read_sa_token`. After a bound failure or success this trigger never sends the
same canonical target/account/password again in a process, including 401/403/500/post-write timeout, successful read,
failed remote read, failed local create, renamed map/stanza, removal/re-add or policy edit. Existing
values/Secret failure rules, retry scheduler and FleetLogin session cleanup are unchanged. No new
retry loop, gate instance per map or on-demand login path is introduced
(`local-development/gsd/fleetlookup.py:367`; `local-development/gsd/fleetlogin.py:364`, `:503`;
`local-development/gsd/poller.py:1520`, `:1556`).

This deliberately prefers an explicit pending finding over a repeat bind if the output is missing
and the budget is spent. The operator fixes the cause, then rotates the password or deliberately
restarts after checking account state; routine policy edits need neither. A changed password is
noticed by the existing cheap re-read. Different targets still have different #284 gate keys;
account-wide durable/replica-shared fencing belongs to #285. This spec does **not** imply one total
successful bind across pre-existing values triggers, all targets, replicas or restarts
(`local-development/gsd/fleetlookup.py:108`, `:356`; `docs/specs/SPEC_S4b_sa_token_lookup.md:2942`).


Grok C2's stated budget (review `grok1/report.md`, C2; accepted by the operator 2026-09-25).
Counts concern one canonical target/account/password per process. “Attempt” before a password write
is not a measured directory bind. Wire mocks measure authorize requests, not real LDAP binds.
Tests below are in `tests/test_configmap_onboarding.py`; their execution is in `phase2-report.md`.

| Scenario | ConfigMap | Values (unchanged) | Named test(s) |
|---|---|---|---|
| First cycle, successful session | 1 | 1 | `test_one_bind_budget_survives_rename_and_policy_changes[success]`; `test_values_bind_budget_is_unchanged[success]` |
| First cycle, 401 / authorize-403 / 500 / post-send timeout | 1 | 1 | `test_one_bind_budget_survives_rename_and_policy_changes`; `test_values_bind_budget_is_unchanged` (401, 403, 500, timeout) |
| First cycle, TLS/connect before password write | Attempt may retry; no gate mark | Same | `test_pre_write_failure_can_retry` (both feeds and failure types) |
| Next five cycles, unchanged output present | 0 | 0 | `test_one_bind_budget_survives_rename_and_policy_changes[success]`; `test_values_bind_budget_is_unchanged[success]` |
| Next five, success then token read / Secret write failed, no output | 0 | Rebinds up to `LOOKUP_ATTEMPTS` | `test_one_bind_budget_survives_rename_and_policy_changes`; `test_values_bind_budget_is_unchanged` (bad-read, write-failure) |
| Policy / enabled / non-connection edit | 0 | n/a | `test_policy_and_enabled_changes_keep_the_token_and_do_not_bind`; `test_one_bind_budget_survives_rename_and_policy_changes` |
| 401 / authorize-403 / 500 / post-send timeout over later cycles | 1 then 0 | 1 then 0 | `test_one_bind_budget_survives_rename_and_policy_changes`; `test_values_bind_budget_is_unchanged` |
| ConfigMap LIST 403 | 0 | n/a | `test_failed_list_is_not_absence_and_cannot_authorize_lookup[/configmaps]` |
| Restart / another replica, missing output | 1 with new gate | 1 with new gate | `test_restart_has_a_new_bind_budget` (fresh gate simulation; no real process/replica measured) |

### 3.4 Surface and trust boundary

Keep `/api/clusterconfigs` behind `clusterconfig:view`, add selector metadata and nullable
`onboarding_configmap`; pending source is `configmap:<name>:<index>`, while a completed cluster keeps
`secret:gsd-cluster-<name>`. Reuse `Finding.secret` for source identity to preserve the wire contract;
label it “source” in the UI. The three new onboarding findings use existing generic rendering.
The tab directs edits/removals to the ConfigMap. Both API and raw writer refuse Rotate/Delete on a
generated output, including a stale-tab race. No credentials, input YAML or trust bytes are added
to public payloads (`local-development/gsd/api.py:1125`, `:1182`, `:1279`;
`local-development/gsd/static/index.html:6030`, `:6049`, `:6110`, `:6141`).

ConfigMap write access in this namespace now authorizes cluster enrollment using the configured
fleet credential. The chart grants the dashboard read access only; platform operators must own
ConfigMap write access. No Secret read permission is granted to those authors. Ownership cannot
resist a privileged namespace writer forging every marker, and this spec makes no such claim
(`docs/specs/SPEC_S3_connection_modes.md:706`; `charts/group-sync-dashboard/templates/cluster-secrets-rbac.yaml:5`).

## 4. Lab facts used — snapshot only

The only current lab measurement is `lab-snapshot.md:1`, timestamp 2026-09-25T05:26:20Z, CRC
OpenShift 4.22.7. It lists six discovery-labelled Secrets (`:4`–`:13`), including unannotated
shared-qa and shared-rnd marked sa-token-lookup. An existing token Secret's six data keys and five
lookup annotation keys are shown with values withheld (`:15`). None is established as S5-owned.
No config-type-labelled ConfigMap exists (`:31`). The SA cannot get/list/watch ConfigMaps but can
get/list/create/update/delete Secrets (`:34`). Therefore S5 needs the namespaced read Role change;
it must not claim or prune the existing Secrets merely because their names match the prefix.

The API sample has dashboard as values/in-cluster, active bearer rows for the three valid mocks,
shared-qa and shared-rnd, historical retired rows, and one insecure-with-ca finding for mock-refusal
(`lab-snapshot.md:44`, `:102`, `:199`). Annotation values truncated in the snapshot, real login/CA
behavior, cleanup retries, timing, live ConfigMap onboarding and anything else about the lab are
**not measured** in this run. Historical spec measurements are research context, not new lab facts.

## 5. Verification plan and phase boundary

The phase-1 report records the exact check-only output, the proven `gsd.__file__`, changed-file
inventory and every block's added/removed lines. The checker verifies matches, not runtime behavior
(`local-development/apply-spec-blocks.py:67`). Runtime and chart files in `wt/` remain unapplied.
The four version tokens must be assigned by the orchestrator before the phase-2 suite/render.

The new test file intentionally fails to import on the base (CONFIG_SELECTOR/new module/shared
parser do not exist). Each case encodes a before/after behavioral obligation; passes are **not
measured** in phase 1. Existing test fixture edits are compatibility adaptations, not claimed new
red/green behavior. Proposed cases:

| Obligation | Regression blocks / acceptance |
|---|---|
| Both synonyms, one selected namespace LIST, multiple maps and unclaimed labels | Full lookup -> Secret -> reader; idempotent second cycle; no writes for unmatched labels. |
| Same parser; closed keys, host, credential references, modes, types, TLS and policy | Shared-parser spy plus values/ConfigMap refusal pairs; no login or value echo. |
| Duplicate names, including invalid named stanzas | Values/map, two maps, same map, unrelated Secret; every source finding; no effective cluster, login or overwrite. |
| Removal survives restart and transient failures | Entry/map/label/UID disappearance; three-cycle failed/successful DELETE; UID+RV preconditions and replacement race. |
| Unowned or incomplete provenance | Physical-name collision labelled or unlabelled; no adoption; changed owner/name/UID marker never deleted. |
| Malformed/incomplete inventory and writes off | Duplicate YAML, malformed envelopes; hold output; ConfigMap and Secret LIST failures keep registry and suppress retrieval; read-only and nonleader cleanup finding. |
| Policy/disabled edits | Keep token, update policy, no bind; effective policy stays authoritative. |
| One-bind safety | Real MockTransport authorize counts for success, 401, 500, post-write timeout, bad read, local write failure; rename/case/policy change cannot rebind. |
| Runtime retirement | Conflicting values thread stops; DB row disabled/history retained; conflict removal restores effective values. |
| API/UI/RBAC | Protected provenance, no token exposure, generated write 409, pending and generated cards at phone width, exact Role rules in both switch states and no Role when discovery off. |
| Version/spec discipline | Existing chart version consistency and exact index count / S issue set; S5 row/header app 0.34.0 / chart 0.55.0; S4c moved to the following minors. |

Additional cases cover write/discovery switches before login, disabled pending entries, password
rotation rearming the same gate, connection edits waiting for a fresh inventory, and displaced
outputs held during a new conflict.

Phase 2: from `wt/local-development`, use the provided interpreter, `PYTHONPATH=.`,
`PYTHONDONTWRITEBYTECODE=1`, `-p no:cacheprovider`, and an absolute `--basetemp` under this workspace.
Run targeted `test_configmap_onboarding.py`, `test_clusterconfig.py`, `test_clusterconfig_tab.py`,
`test_clusterconfig_logging.py`, `test_fleet_lookup.py`, `test_fleet_login.py`, `test_connection_modes.py`,
`test_cluster_stanza_matrix.py`, `test_chart_connection_modes.py`, `test_chart_versions.py`,
`test_specs_index.py`, `test_docs_citations.py`, then the full suite and browser cluster-page cases.
Helm lint/template: defaults, writes on, discovery off, and the existing forbidden writes-on/two-replica
combination. Confirm configmaps exactly get/list/watch in either write state and no cluster-wide grant.
The orchestrator owns lab/CI/deployment; none is run here.

Live acceptance, for the orchestrator after review: use an approved non-fleet test account and an
unused cluster name; apply one map per synonym, verify the generated Secret's keys/markers and API
bearer row, then change policy, introduce/remove a duplicate, remove one entry, remove the map,
recreate it with a new UID, and inject a denied delete for two cycles before restoring the grant.
Verify retained credentials always have findings, history remains, manual/UI Secrets stay untouched,
and count authorize calls using the approved fixture rather than risking the estate's account.
This adapts S4b's safe test-account rule (`docs/specs/SPEC_S4b_sa_token_lookup.md:93`, `:2899`).

## 6. Implementation blocks

### Block 1 — `local-development/gsd/config.py`

Extract the existing values parser unchanged except the explicit ConfigMap boundary; both feeds call it.

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
    known = set(VALUES_CLUSTER_KEYS)

    clusters: list[ClusterConfig] = []
    wheres: list[str] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        where = f"{path}: clusters[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}: must be a mapping")

        unknown = set(entry) - known
        if unknown:
            raise ConfigError(f"{where}: unknown key(s) {sorted(unknown)}")

        name = str(_require(entry, "name", where))
        if name in seen:
            raise ConfigError(f"{where}: duplicate cluster name {name!r}")
        seen.add(name)

        if "/" in name:
            raise ConfigError(f"{where}: name {name!r} must not contain '/' — it is used in API paths")

        api_url = str(_require(entry, "apiUrl", where)).rstrip("/")
        if not api_url.startswith(("http://", "https://")):
            raise ConfigError(f"{where}: apiUrl must start with http:// or https://")

        # SPEC_S3 §4 (S3a): the connection mode, read as a WORD like dashboardController — a quoted
        # "yes" must not become a login. A stanza declaring a mode may omit the credential; one
        # declaring neither keeps today's requirement with today's message; declaring both modes, or
        # a mode beside a credential, is two sources of truth and the operator meant one of them.
        modes = []
        for key in CONNECTION_MODE_KEYS:
            if key in entry:
                if not isinstance(entry[key], bool):
                    raise ConfigError(f"{where}: {name!r}: {key} must be true or false, not {entry[key]!r}")
                if entry[key]:
                    modes.append(key)
        if len(modes) > 1:
            raise ConfigError(f"{where}: {name!r} declares both {' and '.join(modes)} — the two connection "
                              "modes are mutually exclusive; declare one")
        mode = modes[0] if modes else None
        if mode and (entry.get("tokenEnv") or entry.get("tokenFile")):
            supplied = " and ".join(k for k in ("tokenEnv", "tokenFile") if entry.get(k))
            raise ConfigError(f"{where}: {name!r} declares {mode} and also {supplied} — two sources of truth "
                              "for one credential; remove one")
        if not mode and not entry.get("tokenEnv") and not entry.get("tokenFile"):
            raise ConfigError(f"{where}: one of tokenEnv or tokenFile is required")
        bootstrap = entry.get(BOOTSTRAP_KEY)
        if bootstrap is not None:
            if not valid_bootstrap_username(bootstrap):
                raise ConfigError(f"{where}: {name!r}: {BOOTSTRAP_KEY} must be a username (letters, digits, "
                                  "'.', '_', '@', '-'; no spaces, colons or slashes) — the value is not repeated "
                                  "here, in case something other than a username was written into it")
            if not mode:
                raise ConfigError(f"{where}: {name!r}: {BOOTSTRAP_KEY} without saTokenLookup or userSelfLogin "
                                  "configures a login that would never happen — declare the mode, or remove the key")

        insecure = bool(entry.get("insecureSkipVerify", False))
        if insecure and entry.get("caBundleFile"):
            raise ConfigError(
                f"{where}: insecureSkipVerify and caBundleFile are mutually exclusive"
            )

        # A word, not truthiness: `bool("false")` is True, so a quoted `enabled: "false"` — what
        # a templating system emits — enabled the cluster, and since D2 the first ENABLED entry
        # is the authorization host (review of D2, second pass, Codex; measured).
        raw_enabled = entry.get("enabled", True)
        if isinstance(raw_enabled, bool):
            enabled = raw_enabled
        elif isinstance(raw_enabled, str) and raw_enabled.strip() in ("true", "false"):
            enabled = raw_enabled.strip() == "true"
        else:
            raise ConfigError(f"{where}: enabled must be true or false")
        # Strict, like every other cluster key: a typo here ("self_only", "Hidden") must not
        # silently become the default, in either direction.
        # Blank and whitespace-only are "unset" — the chart's guard tolerates them and renders
        # them through, so refusing them here was a pod that crashed after a green upgrade
        # (review of D2, Codex). Every non-empty word stays strict and case-sensitive.
        visibility = entry.get("visibility")
        if visibility is not None:
            visibility = str(visibility).strip() or None
            if visibility is not None and visibility not in CLUSTER_VISIBILITIES:
                raise ConfigError(
                    f"{where}: visibility {visibility!r} is not one of "
                    f"{', '.join(CLUSTER_VISIBILITIES)}"
                )
        identity = entry.get("identity")
        if identity is not None:
            identity = str(identity).strip() or None
            if identity is not None and identity not in CLUSTER_IDENTITIES:
                raise ConfigError(
                    f"{where}: identity {identity!r} is not one of {', '.join(CLUSTER_IDENTITIES)}"
                )
        controller = entry.get("dashboardController", False)
        if not isinstance(controller, bool):
            raise ConfigError(f"{where}: dashboardController must be true or false, not {controller!r}")
        if controller and not enabled:
            raise ConfigError(f"{where}: {name!r} is the dashboardController but enabled is false — "
                              "the controller is this pod's own cluster and cannot be disabled")

        clusters.append(
            ClusterConfig(
                name=name,
                api_url=api_url,
                token_env=entry.get("tokenEnv"),
                token_file=entry.get("tokenFile"),
                ca_bundle_file=entry.get("caBundleFile"),
                insecure_skip_verify=insecure,
                enabled=enabled,
                visibility=visibility,
                identity=identity,
                dashboard_controller=controller,
                sa_token_lookup=mode == "saTokenLookup",
                user_self_login=mode == "userSelfLogin",
                ldap_connection_bootstrap=bootstrap,
            )
        )
        wheres.append(where)

    declared = [c.name for c in clusters if c.dashboard_controller]
    if len(declared) > 1:
        raise ConfigError(f"{path}: {len(declared)} clusters declare dashboardController ({', '.join(declared)}) — "
                          "exactly one entry is this pod's own cluster")

    # THE HOST-ONLY VISIBILITY RULES RUN IN A SECOND PASS (review of #251, C1b). They were applied
    # inline against "the first enabled entry", which stopped being the host the moment a LATER entry
    # could declare `dashboardController: true`: measured on that head, `hidden` was accepted on the
    # declared controller — the login cluster, the one thing the rule exists to protect — and refused
    # on a remote. The host is not known until every entry has been read, so the check cannot be.
    host = (next((c for c in clusters if c.enabled and c.dashboard_controller), None)
            or next((c for c in clusters if c.enabled), None))
    for cluster, where in zip(clusters, wheres):
        if cluster is host:
            how = ("declared by dashboardController" if cluster.dashboard_controller
                   else "the first enabled entry, since none declares dashboardController")
            if cluster.connection_mode is not None:
                # SPEC_S3 §4 rule 4: the controller is this pod's own cluster and authenticates with the
                # mounted ServiceAccount — there is nothing to connect. Checked here, against the cluster
                # that really is the host, so an inferred host is refused the same as a declared one.
                raise ConfigError(
                    f"{where}: {cluster.name!r} is the hosting cluster ({how}) and declares "
                    f"{cluster.connection_mode} — the controller authenticates with the mounted "
                    "ServiceAccount; there is nothing to connect"
                )
            if cluster.visibility in (VISIBILITY_HIDDEN, VISIBILITY_REMOTE_SAR):
                raise ConfigError(
                    f"{where}: visibility {cluster.visibility!r} is not allowed on the hosting cluster "
                    f"({how}) — it is the cluster the viewer logged in to"
                )
        elif cluster.visibility == VISIBILITY_REMOTE_SAR and cluster.identity == IDENTITY_NONE:
            # Only the EXPLICIT pair (SPEC_D2b §3.2): an omitted identity resolves to same-as-host beside
            # remote-sar, and `identity: none` stated alone resolves to self-only.
            raise ConfigError(
                f"{where}: visibility remote-sar needs identity: same-as-host — the review names the "
                f"reader's OpenShift username on this cluster; set same-as-host or leave identity out"
            )

```

New text:

```python
    clusters = parse_cluster_entries(entries, path)

```

### Block 2 — `local-development/gsd/config.py`

The shared parser retains the second-pass host and policy checks.

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
def load_settings(path: str | Path) -> Settings:
```

New text:

```python
def _is_host_api(url: str, host: ClusterConfig) -> bool:
    """The controller's DNS aliases or the values host's scheme/host/effective port."""
    from urllib.parse import urlsplit

    def endpoint(value):
        parts = urlsplit(value)
        return (parts.scheme, (parts.hostname or "").lower().rstrip("."),
                parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80))

    declared = endpoint(url)
    return declared[1] in {"kubernetes.default.svc", "kubernetes.default.svc.cluster.local",
                           "kubernetes.default"} or declared == endpoint(host.api_url)


def parse_cluster_entries(entries: list, path: str | Path, *, remote_host: ClusterConfig | None = None) -> list[ClusterConfig]:
    """One values-shaped stanza parser; a runtime ConfigMap supplies its already-known host."""
    known = set(VALUES_CLUSTER_KEYS)

    clusters: list[ClusterConfig] = []
    wheres: list[str] = []
    seen: set[str] = set()
    for i, entry in enumerate(entries):
        where = f"{path}: clusters[{i}]"
        if not isinstance(entry, dict):
            raise ConfigError(f"{where}: must be a mapping")

        unknown = set(entry) - known
        if unknown:
            raise ConfigError(f"{where}: unknown key(s) {sorted(unknown)}")

        if remote_host is not None:
            # The same parser, with the runtime feed's no-credential / remote-only boundary.
            if "tokenEnv" in entry or "tokenFile" in entry:
                raise ConfigError(f"{where}: a ConfigMap may not carry a credential reference")
            if entry.get("dashboardController") or entry.get("name") == remote_host.name:
                raise ConfigError(f"{where}: the host is declared only in values")
            if _is_host_api(str(entry.get("apiUrl", "")), remote_host):
                raise ConfigError(f"{where}: the host is declared only in values")
            if entry.get("saTokenLookup") is not True:
                raise ConfigError(f"{where}: a ConfigMap needs saTokenLookup: true")
        name = str(_require(entry, "name", where))
        if name in seen:
            raise ConfigError(f"{where}: duplicate cluster name {name!r}")
        seen.add(name)

        if "/" in name:
            raise ConfigError(f"{where}: name {name!r} must not contain '/' — it is used in API paths")

        api_url = str(_require(entry, "apiUrl", where)).rstrip("/")
        if not api_url.startswith(("http://", "https://")):
            raise ConfigError(f"{where}: apiUrl must start with http:// or https://")

        # SPEC_S3 §4 (S3a): the connection mode, read as a WORD like dashboardController — a quoted
        # "yes" must not become a login. A stanza declaring a mode may omit the credential; one
        # declaring neither keeps today's requirement with today's message; declaring both modes, or
        # a mode beside a credential, is two sources of truth and the operator meant one of them.
        modes = []
        for key in CONNECTION_MODE_KEYS:
            if key in entry:
                if not isinstance(entry[key], bool):
                    raise ConfigError(f"{where}: {name!r}: {key} must be true or false, not {entry[key]!r}")
                if entry[key]:
                    modes.append(key)
        if len(modes) > 1:
            raise ConfigError(f"{where}: {name!r} declares both {' and '.join(modes)} — the two connection "
                              "modes are mutually exclusive; declare one")
        mode = modes[0] if modes else None
        if mode and (entry.get("tokenEnv") or entry.get("tokenFile")):
            supplied = " and ".join(k for k in ("tokenEnv", "tokenFile") if entry.get(k))
            raise ConfigError(f"{where}: {name!r} declares {mode} and also {supplied} — two sources of truth "
                              "for one credential; remove one")
        if not mode and not entry.get("tokenEnv") and not entry.get("tokenFile"):
            raise ConfigError(f"{where}: one of tokenEnv or tokenFile is required")
        bootstrap = entry.get(BOOTSTRAP_KEY)
        if bootstrap is not None:
            if not valid_bootstrap_username(bootstrap):
                raise ConfigError(f"{where}: {name!r}: {BOOTSTRAP_KEY} must be a username (letters, digits, "
                                  "'.', '_', '@', '-'; no spaces, colons or slashes) — the value is not repeated "
                                  "here, in case something other than a username was written into it")
            if not mode:
                raise ConfigError(f"{where}: {name!r}: {BOOTSTRAP_KEY} without saTokenLookup or userSelfLogin "
                                  "configures a login that would never happen — declare the mode, or remove the key")

        insecure = bool(entry.get("insecureSkipVerify", False))
        if insecure and entry.get("caBundleFile"):
            raise ConfigError(
                f"{where}: insecureSkipVerify and caBundleFile are mutually exclusive"
            )

        # A word, not truthiness: `bool("false")` is True, so a quoted `enabled: "false"` — what
        # a templating system emits — enabled the cluster, and since D2 the first ENABLED entry
        # is the authorization host (review of D2, second pass, Codex; measured).
        raw_enabled = entry.get("enabled", True)
        if isinstance(raw_enabled, bool):
            enabled = raw_enabled
        elif isinstance(raw_enabled, str) and raw_enabled.strip() in ("true", "false"):
            enabled = raw_enabled.strip() == "true"
        else:
            raise ConfigError(f"{where}: enabled must be true or false")
        # Strict, like every other cluster key: a typo here ("self_only", "Hidden") must not
        # silently become the default, in either direction.
        # Blank and whitespace-only are "unset" — the chart's guard tolerates them and renders
        # them through, so refusing them here was a pod that crashed after a green upgrade
        # (review of D2, Codex). Every non-empty word stays strict and case-sensitive.
        visibility = entry.get("visibility")
        if visibility is not None:
            visibility = str(visibility).strip() or None
            if visibility is not None and visibility not in CLUSTER_VISIBILITIES:
                raise ConfigError(
                    f"{where}: visibility {visibility!r} is not one of "
                    f"{', '.join(CLUSTER_VISIBILITIES)}"
                )
        identity = entry.get("identity")
        if identity is not None:
            identity = str(identity).strip() or None
            if identity is not None and identity not in CLUSTER_IDENTITIES:
                raise ConfigError(
                    f"{where}: identity {identity!r} is not one of {', '.join(CLUSTER_IDENTITIES)}"
                )
        controller = entry.get("dashboardController", False)
        if not isinstance(controller, bool):
            raise ConfigError(f"{where}: dashboardController must be true or false, not {controller!r}")
        if controller and not enabled:
            raise ConfigError(f"{where}: {name!r} is the dashboardController but enabled is false — "
                              "the controller is this pod's own cluster and cannot be disabled")

        clusters.append(
            ClusterConfig(
                name=name,
                api_url=api_url,
                token_env=entry.get("tokenEnv"),
                token_file=entry.get("tokenFile"),
                ca_bundle_file=entry.get("caBundleFile"),
                insecure_skip_verify=insecure,
                enabled=enabled,
                visibility=visibility,
                identity=identity,
                dashboard_controller=controller,
                sa_token_lookup=mode == "saTokenLookup",
                user_self_login=mode == "userSelfLogin",
                ldap_connection_bootstrap=bootstrap,
            )
        )
        wheres.append(where)

    declared = [c.name for c in clusters if c.dashboard_controller]
    if len(declared) > 1:
        raise ConfigError(f"{path}: {len(declared)} clusters declare dashboardController ({', '.join(declared)}) — "
                          "exactly one entry is this pod's own cluster")

    # THE HOST-ONLY VISIBILITY RULES RUN IN A SECOND PASS (review of #251, C1b). They were applied
    # inline against "the first enabled entry", which stopped being the host the moment a LATER entry
    # could declare `dashboardController: true`: measured on that head, `hidden` was accepted on the
    # declared controller — the login cluster, the one thing the rule exists to protect — and refused
    # on a remote. The host is not known until every entry has been read, so the check cannot be.
    host = (next((c for c in clusters if c.enabled and c.dashboard_controller), None)
            or next((c for c in clusters if c.enabled), None))
    host = remote_host or host
    for cluster, where in zip(clusters, wheres):
        if cluster is host:
            how = ("declared by dashboardController" if cluster.dashboard_controller
                   else "the first enabled entry, since none declares dashboardController")
            if cluster.connection_mode is not None:
                # SPEC_S3 §4 rule 4: the controller is this pod's own cluster and authenticates with the
                # mounted ServiceAccount — there is nothing to connect. Checked here, against the cluster
                # that really is the host, so an inferred host is refused the same as a declared one.
                raise ConfigError(
                    f"{where}: {cluster.name!r} is the hosting cluster ({how}) and declares "
                    f"{cluster.connection_mode} — the controller authenticates with the mounted "
                    "ServiceAccount; there is nothing to connect"
                )
            if cluster.visibility in (VISIBILITY_HIDDEN, VISIBILITY_REMOTE_SAR):
                raise ConfigError(
                    f"{where}: visibility {cluster.visibility!r} is not allowed on the hosting cluster "
                    f"({how}) — it is the cluster the viewer logged in to"
                )
        elif cluster.visibility == VISIBILITY_REMOTE_SAR and cluster.identity == IDENTITY_NONE:
            # Only the EXPLICIT pair (SPEC_D2b §3.2): an omitted identity resolves to same-as-host beside
            # remote-sar, and `identity: none` stated alone resolves to self-only.
            raise ConfigError(
                f"{where}: visibility remote-sar needs identity: same-as-host — the review names the "
                f"reader's OpenShift username on this cluster; set same-as-host or leave identity out"
            )

    return clusters


def load_settings(path: str | Path) -> Settings:
```

### Block 3 — `local-development/gsd/config.py`

Carry only provenance through the existing ClusterConfig and lookup.

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
    source: str = "values"                       # values | secret:<metadata.name>
```

New text:

```python
    source: str = "values"                       # values | secret:<name> | configmap:<name>:<index>
    # SPEC_S5: ConfigMap name, UID and connection digest; no credential, no second registry.
    onboarding: tuple[str, str, str] = ()
```

### Block 4 — `local-development/gsd/clusterconfig/__init__.py`

The operator-fixed two selectors remain disjoint; Secret selector is byte-for-byte unchanged.

<!-- block: local-development/gsd/clusterconfig/__init__.py | edit -->

Old text:

```python
LABEL_SELECTOR = f"{SECRET_TYPE_LABEL}={SECRET_TYPE_CLUSTER}"
```

New text:

```python
LABEL_SELECTOR = f"{SECRET_TYPE_LABEL}={SECRET_TYPE_CLUSTER}"
CONFIG_TYPE_LABEL = "groupsync-dashboard.io/config-type"
CONFIG_TYPES = ("onboard", "sideload")
CONFIG_SELECTOR = f"{CONFIG_TYPE_LABEL} in ({','.join(CONFIG_TYPES)})"
```

### Block 5 — `local-development/gsd/clusterconfig/__init__.py`

Reuse Finding; add only distinctions that the existing codes cannot express.

<!-- block: local-development/gsd/clusterconfig/__init__.py | edit -->

Old text:

```python
    "oauth-exchange-not-built", "discovery-failed",
```

New text:

```python
    "oauth-exchange-not-built", "discovery-failed",
    "onboarding-invalid", "onboarding-cleanup-pending", "onboarding-ownership-conflict",
```

### Block 6 — `local-development/gsd/clusterconfig/reader.py`

Allow the reconciler to hand the reader the same complete labelled Secret inventory.

<!-- block: local-development/gsd/clusterconfig/reader.py | edit -->

Old text:

```python
             values_modes: dict[str, str] | None = None) -> tuple[list[ClusterConfig], list[Finding]]:
```

New text:

```python
             values_modes: dict[str, str] | None = None,
             items: list[dict] | None = None) -> tuple[list[ClusterConfig], list[Finding]]:
```

### Block 7 — `local-development/gsd/clusterconfig/reader.py`

Existing callers still perform the identical namespace-scoped LIST.

<!-- block: local-development/gsd/clusterconfig/reader.py | edit -->

Old text:

```python
    with cluster_client._client() as client:
        items = cluster_client._list_all_with(client, path, {"labelSelector": LABEL_SELECTOR})
```

New text:

```python
    if items is None:
        with cluster_client._client() as client:
            items = cluster_client._list_all_with(client, path, {"labelSelector": LABEL_SELECTOR})
```

### Block 8 — `local-development/gsd/clusterconfig/reader.py`

The finding now also covers ConfigMap/values conflicts.

<!-- block: local-development/gsd/clusterconfig/reader.py | edit -->

Old text:

```python
    "duplicate-cluster-name": "remove one of the two Secrets, or rename the cluster in one",
```

New text:

```python
    "duplicate-cluster-name": "remove or rename the duplicate declaration; every conflicting source is listed on the tab",
```

### Block 9 — `local-development/gsd/clusterconfig/writer.py`

A distinct generator marker cannot adopt UI, values-lookup or hand-made Secrets.

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->

Old text:

```python
MANAGED_BY_LOOKUP = "sa-token-lookup"
```

New text:

```python
MANAGED_BY_LOOKUP = "sa-token-lookup"
MANAGED_BY_ONBOARD = "configmap-onboarding"
CONFIGMAP_ANNOTATION = "groupsync-dashboard.io/source-configmap"
CONFIGMAP_UID_ANNOTATION = "groupsync-dashboard.io/source-configmap-uid"
CONNECTION_HASH_ANNOTATION = "groupsync-dashboard.io/connection-hash"
```

### Block 10 — `local-development/gsd/clusterconfig/writer.py`

Provenance travels through the shipped writer, atomically with the initial POST.

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->

Old text:

```python
    lookup_account: str | None = None
```

New text:

```python
    lookup_account: str | None = None
    onboarding: tuple[str, str, str] = ()
```

### Block 11 — `local-development/gsd/clusterconfig/writer.py`

No second metadata patch after a create; a crash cannot leave an unmarked credential.

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->

Old text:

```python
    return {
        "apiVersion": "v1", "kind": "Secret",
```

New text:

```python
    if req.onboarding:
        annotations.update(zip((CONFIGMAP_ANNOTATION, CONFIGMAP_UID_ANNOTATION,
                                CONNECTION_HASH_ANNOTATION), req.onboarding))
    return {
        "apiVersion": "v1", "kind": "Secret",
```

### Block 12 — `local-development/gsd/clusterconfig/writer.py`

S3 ownership guards plus compare-and-swap deletes; retry is driven by current inventory.

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->

Old text:

```python
def delete(host_client: ClusterClient, namespace: str, name: str, *, viewer: str, cluster: str) -> None:
```

New text:

```python
def onboarding_owner(obj: dict) -> tuple[str, str, str] | None:
    """Strict bookkeeping ownership on a raw Secret, never inferred from its name or label alone."""
    from .parser import _data, _NAME
    meta = obj.get("metadata") or {}
    ann = meta.get("annotations") or {}
    data, bad = _data(obj)
    name = data.get("name", "")
    owner = tuple(ann.get(k, "") for k in
                  (CONFIGMAP_ANNOTATION, CONFIGMAP_UID_ANNOTATION, CONNECTION_HASH_ANNOTATION))
    if (not _labelled(obj) or ann.get(MANAGED_BY_ANNOTATION) != MANAGED_BY_ONBOARD
            or ann.get(TOKEN_SOURCE_ANNOTATION) != TOKEN_SOURCE_LOOKUP
            or not all(isinstance(v, str) and v for v in owner)
            or not re.fullmatch(r"[0-9a-f]{64}", owner[2])
            or "name" in bad or not _NAME.fullmatch(name)
            or meta.get("name") != secret_name_for(name)):
        return None
    return owner


def reconcile_onboarding(host_client: ClusterClient, namespace: str, snapshot: dict,
                         *, desired: ClusterConfig | None = None) -> dict | None:
    """Delete a displaced output or sync its policy, with identity/version preconditions.

    Callers gate writes and leadership. Re-read ownership before every mutation; do not inherit the
    general writer's label-only rule. A 409 or failed DELETE remains in next cycle's inventory.
    """
    from .parser import _data
    from ..config import remote_policy
    meta = snapshot.get("metadata") or {}
    owner = onboarding_owner(snapshot)
    if owner is None or not meta.get("uid") or not meta.get("resourceVersion"):
        raise WriteRefused("onboarding-ownership-conflict", "generated Secret has incomplete ownership; left untouched")
    name = meta["name"]
    with host_client._client() as client:
        obj = _read_ours(host_client, client, namespace, name)
        current = obj.get("metadata") or {}
        if (onboarding_owner(obj) != owner
                or current.get("uid") != meta["uid"]
                or current.get("resourceVersion") != meta["resourceVersion"]):
            raise WriteRefused("secret-changed", "generated Secret changed during discovery; retry next cycle")
        data, _ = _data(obj)
        if desired is not None:
            if owner != desired.onboarding or data.get("name") != desired.name:
                raise WriteRefused("onboarding-ownership-conflict", "generated Secret belongs to another declaration")
            visibility, identity = remote_policy(desired.visibility, desired.identity)
            policy = {"visibility": visibility, "identity": identity,
                      "enabled": "true" if desired.enabled else "false"}
            if all(data.get(k) == v for k, v in policy.items()):
                return obj
            # Keep the credential, trust, annotations, labels and resourceVersion exactly as read.
            obj = {**obj, "data": {**(obj.get("data") or {})},
                   "stringData": {**(obj.get("stringData") or {}), **policy}}
        try:
            if desired is None:
                host_client._send(client, "DELETE", _path(namespace, name), json={
                    "apiVersion": "v1", "kind": "DeleteOptions",
                    "preconditions": {"uid": meta["uid"], "resourceVersion": meta["resourceVersion"]}})
            else:
                host_client._send(client, "PUT", _path(namespace, name), json=obj,
                                  secrets=(data.get("config"), (obj.get("data") or {}).get("config")))
        except ClusterError as exc:
            # No remote body is repeated: it may echo a credential or an encoded config.
            raise WriteFailed(exc.outcome, "generated Secret write failed; retry next cycle") from exc
    event(log, logging.INFO, "cluster-secret-deleted" if desired is None else "cluster-secret-updated",
          secret=name, namespace=namespace, cluster=data["name"], by=MANAGED_BY_ONBOARD)
    return obj if desired is not None else None


def delete(host_client: ClusterClient, namespace: str, name: str, *, viewer: str, cluster: str) -> None:
```

### Block 13 — `local-development/gsd/fleetlookup.py`

Reuse the same lookup and writer, with a distinct owner value.

<!-- block: local-development/gsd/fleetlookup.py | edit -->

Old text:

```python
    MANAGED_BY_LOOKUP, TOKEN_SOURCE_LOOKUP, CreateRequest, WriteFailed, WriteRefused, create, secret_name_for,
```

New text:

```python
    MANAGED_BY_LOOKUP, MANAGED_BY_ONBOARD, TOKEN_SOURCE_LOOKUP, CreateRequest, WriteFailed, WriteRefused, create, secret_name_for,
```

### Block 14 — `local-development/gsd/fleetlookup.py`

Generated Secret has the same data/TLS shape and the ConfigMap provenance.

<!-- block: local-development/gsd/fleetlookup.py | edit -->

Old text:

```python
                            managed_by=MANAGED_BY_LOOKUP, token_source=TOKEN_SOURCE_LOOKUP, **provenance)
```

New text:

```python
                            managed_by=MANAGED_BY_ONBOARD if cluster.onboarding else MANAGED_BY_LOOKUP,
                            onboarding=cluster.onboarding, token_source=TOKEN_SOURCE_LOOKUP, **provenance)
```

### Block 15 — `local-development/gsd/fleetlookup.py`

The ConfigMap trigger cannot spend a second bind after a successful login followed by a failed read/write.

<!-- block: local-development/gsd/fleetlookup.py | edit -->

Old text:

```python
                secrets.append(session.token)
                sa_token = read_sa_token(session.token, cluster, source, timeout=settings.request_timeout_seconds)
```

New text:

```python
                secrets.append(session.token)
                if cluster.onboarding:
                    # #293's strict budget includes successful binds, even if the later read/write fails.
                    # Keep the SAME process-lifetime gate used by every existing lookup caller.
                    gate.refuse(cluster.api_url, account, password)
                sa_token = read_sa_token(session.token, cluster, source, timeout=settings.request_timeout_seconds)
```

### Block 16 — `local-development/gsd/clusterconfig/registry.py`

Runtime duplicate suppression must include values; otherwise merge falls back to a conflicting stanza.

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->

Old text:

```python
        self._lookups: dict[str, Finding] = {}
```

New text:

```python
        self._lookups: dict[str, Finding] = {}
        self._blocked: set[str] = set()
```

### Block 17 — `local-development/gsd/clusterconfig/registry.py`

Install conflict state atomically with the existing discovery snapshot.

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->

Old text:

```python
    def replace(self, clusters: list[ClusterConfig], findings: list[Finding], *, at: str, error: str | None = None) -> None:
```

New text:

```python
    def replace(self, clusters: list[ClusterConfig], findings: list[Finding], *, at: str,
                error: str | None = None, blocked: set[str] | None = None) -> None:
```

### Block 18 — `local-development/gsd/clusterconfig/registry.py`

A failed LIST leaves both snapshot and suppression intact.

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->

Old text:

```python
            self._findings = list(findings)
```

New text:

```python
            self._findings = list(findings)
            self._blocked = set(blocked or ())
```

### Block 19 — `local-development/gsd/clusterconfig/registry.py`

Use the same registry lock; no parallel configuration layer.

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->

Old text:

```python
            discovered = dict(self._discovered)
```

New text:

```python
            discovered = dict(self._discovered)
            blocked = set(self._blocked)
```

### Block 20 — `local-development/gsd/clusterconfig/registry.py`

Conflicting values cannot silently resume behind a duplicate finding.

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->

Old text:

```python
        for c in values:
            found = discovered.pop(c.name, None)
```

New text:

```python
        for c in values:
            if c.name in blocked:
                continue
            found = discovered.pop(c.name, None)
```

### Block 21 — `local-development/gsd/clusterconfig/registry.py`

Suppression applies to the generated and hand-authored Secret too.

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->

Old text:

```python
        out.extend(discovered.values())
```

New text:

```python
        out.extend(c for c in discovered.values() if c.name not in blocked)
```

### Block 22 — `local-development/gsd/poller.py`

Extend the same cadence, startup path and finding transitions.

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
        from .clusterconfig import discover
```

New text:

```python
        from .clusterconfig.onboarding import discover_onboarding
```

### Block 23 — `local-development/gsd/poller.py`

Only the leader with the existing replica guard may reconcile writes; reads remain available.

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
            clusters, findings = discover(
                ClusterClient(host, timeout=self.settings.request_timeout_seconds), namespace,
                host_name=host.name, values_names=tuple(c.name for c in self.settings.clusters),
                # A values stanza that declares a mode expects the retriever's Secret over it
                # (SPEC_S4 §1); the reader keeps that one out of `shadows-values-entry`.
                values_modes={c.name: c.credential_kind for c in self.settings.clusters
                              if c.connection_mode is not None})
```

New text:

```python
            clusters, findings, blocked = discover_onboarding(
                ClusterClient(host, timeout=self.settings.request_timeout_seconds), namespace,
                settings=self.settings,
                mutate=(self.elector is None or self.elector.is_leader)
                       and not (self.elector is None and self.settings.replica_count > 1))
```

### Block 24 — `local-development/gsd/poller.py`

Name both LIST grants in an operational failure.

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
                action=("grant the ServiceAccount list on secrets in this namespace, or check "
```

New text:

```python
                action=("grant the ServiceAccount list on secrets and configmaps in this namespace, or check "
```

### Block 25 — `local-development/gsd/poller.py`

Both inventory reads succeed before publishing or mutating.

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
        registry.replace(clusters, findings, at=at)
```

New text:

```python
        registry.replace(clusters, findings, at=at, blocked=blocked)
```

### Block 26 — `local-development/gsd/poller.py`

Conflicting values rows retire at runtime too, preserving history.

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
        for name in before - after:
            if name not in {c.name for c in self.settings.clusters}:
```

New text:

```python
        for name in (before - after) | blocked:
            if name in blocked or name not in {c.name for c in self.settings.clusters}:
```

### Block 27 — `local-development/gsd/poller.py`

A blocked values cluster must stop its already-running thread.

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
            if values_entry is not None and values_entry.credential_pending is None:
```

New text:

```python
            if values_entry is not None and self.settings.cluster(name) is not None and values_entry.credential_pending is None:
```

### Block 28 — `local-development/gsd/poller.py`

A failed ConfigMap or Secret LIST cannot trigger stale onboarding.

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
        pending = {c.name: c for c in self.settings.effective_clusters()
```

New text:

```python
        if registry.error:
            return  # An incomplete inventory cannot authorize a login from stale intent.
        pending = {c.name: c for c in self.settings.effective_clusters()
```

### Block 29 — `local-development/gsd/poller.py`

Startup discovery failure preserves pending ConfigMap rows as it does Secret rows.

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
        keep = ("secret:",) if discovery_failed else ()
```

New text:

```python
        keep = ("secret:", "configmap:") if discovery_failed else ()
```

### Block 30 — `local-development/gsd/clusterconfig/onboarding.py`

SPEC_S5 implementation and its adversarial regression cases.

<!-- block: local-development/gsd/clusterconfig/onboarding.py | create -->

```python
"""SPEC_S5: ConfigMap intent -> existing lookup -> labelled Secret discovery.

Two complete, namespace-scoped inventories precede every mutation. No edge-triggered deletion
state: absent outputs are reconciled from the current inventory, including after a restart.
"""
from __future__ import annotations

import base64
import dataclasses
import hashlib
import json

import httpx
import yaml

from ..config import ConfigError, parse_cluster_entries, remote_policy
from ..kube import ClusterError
from ..fleetlookup import LookupRefused, LookupSource, declared_trust
from . import CONFIG_SELECTOR, LABEL_SELECTOR
from .parser import Finding, _data, _NAME, parse_secret
from .reader import discover
from .writer import (
    MANAGED_BY_ANNOTATION, MANAGED_BY_ONBOARD,
    CreateRequest, WriteFailed, WriteRefused, onboarding_owner, reconcile_onboarding, secret_name_for, validate,
)


class _UniqueLoader(yaml.SafeLoader):
    """A duplicate YAML key must not silently erase a declaration or a credential refusal."""


def _mapping(loader, node, deep=False):
    loader.flatten_mapping(node)
    out = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in out:
            raise ValueError("mapping keys must be unique strings")
        out[key] = loader.construct_object(value_node, deep=deep)
    return out


_UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _mapping)


def _connection(cluster, settings, namespace):
    """Validate the eventual Secret before any login; hash connection inputs, excluding policy."""
    tls, ca = declared_trust(cluster)
    request = CreateRequest(name=cluster.name, server=cluster.api_url, credential_kind="bearerToken",
                            token="validation-only", tls_mode=tls, ca_data=ca,
                            visibility=cluster.visibility or "remote-sar",
                            identity=cluster.identity or "same-as-host")
    # remote_policy handles identity:none alone, the same default used by the real lookup.
    request = dataclasses.replace(request, **dict(zip(("visibility", "identity"),
                                  remote_policy(cluster.visibility, cluster.identity))))
    parsed = validate(request, namespace, host_name=settings.host_cluster().name, taken={})
    if parsed.name != cluster.name:
        raise ValueError("cluster identity must survive Secret serialization unchanged")
    source = LookupSource.from_settings(settings)
    payload = [str(httpx.URL(cluster.api_url)), tls, ca, cluster.ldap_connection_bootstrap or settings.fleet_account_username,
               source.namespace, source.service_account, source.secret_name]
    return hashlib.sha256(json.dumps(payload, separators=(",", ":")).encode()).hexdigest()


def discover_onboarding(host_client, namespace: str, *, settings, mutate: bool):
    """Return clusters, findings, blocked names; an incomplete LIST raises without any mutation."""
    with host_client._client() as client:
        maps = host_client._list_all_with(client, f"/api/v1/namespaces/{namespace}/configmaps",
                                         {"labelSelector": CONFIG_SELECTOR})
        secrets = host_client._list_all_with(client, f"/api/v1/namespaces/{namespace}/secrets",
                                            {"labelSelector": LABEL_SELECTOR})
    host = settings.host_cluster()
    findings = []
    declarations = {}             # source -> ClusterConfig; invalid named entries still reserve a name
    authors = {}                  # cluster name -> source descriptions
    reserved = set()              # (ConfigMap name, UID, cluster name), also for invalid named entries
    uncertain = set()             # malformed whole documents: absence cannot prove removal
    for obj in sorted(maps, key=lambda o: o["metadata"]["name"]):
        meta = obj["metadata"]
        cm, uid = meta["name"], meta.get("uid", "")
        source = f"configmap:{cm}"
        try:
            data = obj.get("data") or {}
            if set(data) != {"clusters.yaml"} or obj.get("binaryData") or not uid:
                raise ValueError("requires data.clusters.yaml only and an API-assigned UID")
            raw = yaml.load(data["clusters.yaml"], Loader=_UniqueLoader)
            if not isinstance(raw, dict) or set(raw) != {"clusters"} or not isinstance(raw["clusters"], list):
                raise ValueError("requires a mapping containing only a clusters list")
            entries = raw["clusters"]
        except (yaml.YAMLError, ValueError, TypeError, RecursionError):
            uncertain.add(cm)
            findings.append(Finding(source, "onboarding-invalid",
                                    "ConfigMap (config-type onboard or sideload) needs data.clusters.yaml with a clusters list; "
                                    "unique keys, no extra data or binaryData; existing outputs are held, not polled"))
            continue
        for index, entry in enumerate(entries):
            source = f"configmap:{cm}:{index}"
            raw_name = entry.get("name") if isinstance(entry, dict) else None
            name = str(raw_name) if raw_name is not None else None  # same coercion as the values parser
            if isinstance(name, str) and _NAME.fullmatch(name):
                reserved.add((cm, uid, name))
            else:
                # Cannot identify which previous stanza this malformed entry replaced.
                uncertain.add(cm)
            try:
                cluster, = parse_cluster_entries([entry], source, remote_host=host)
                digest = _connection(cluster, settings, namespace)
            except (ConfigError, WriteRefused, LookupRefused, TypeError, ValueError, RecursionError):
                # Never echo values, YAML snippets, arbitrary keys or exception text from this feed.
                findings.append(Finding(source, "onboarding-invalid",
                                        "invalid values-shaped stanza: check name/apiUrl, known keys, booleans, TLS and policy; "
                                        "use saTokenLookup: true, no credential or token reference, and no host declaration"))
                continue
            authors.setdefault(cluster.name, []).append(source)
            declarations[source] = dataclasses.replace(cluster, source=source, onboarding=(cm, uid, digest))

    # Values/ConfigMap duplicates load neither. Protect the values host before considering duplicates.
    for cluster in settings.clusters:
        if cluster.name in authors:
            authors[cluster.name].append("values")
    outputs = {}
    ordinary = []
    for obj in secrets:
        meta = obj.get("metadata") or {}
        data, _ = _data(obj)
        name = data.get("name", "").strip()
        owner = onboarding_owner(obj)
        if owner is not None:
            outputs[meta["name"]] = (obj, owner, name)
        elif (meta.get("annotations") or {}).get(MANAGED_BY_ANNOTATION) == MANAGED_BY_ONBOARD:
            findings.append(Finding(meta["name"], "onboarding-ownership-conflict",
                                    "generated Secret ownership is incomplete or changed; left untouched and not polled"))
            if name in authors:
                authors[name].append(f"secret:{meta['name']}")
        else:
            ordinary.append(obj)
            if name in authors:
                authors[name].append(f"secret:{meta['name']}")
    blocked = {name for name, sources in authors.items() if len(sources) > 1}
    for name in sorted(blocked):
        for source in authors[name]:
            findings.append(Finding(source, "duplicate-cluster-name",
                                    f"{name} is declared by {', '.join(authors[name])}; none loads until the conflict is removed"))
    desired = {c.name: c for c in declarations.values() if c.name not in blocked}
    ready = []
    pending = dict(desired)
    writable = mutate and settings.cluster_secrets_enabled and settings.cluster_secrets_writes_enabled
    for secret_name, (obj, owner, name) in sorted(outputs.items()):
        cluster = desired.get(name)
        declared = (owner[0], owner[1], name) in reserved
        if name in blocked or owner[0] in uncertain or (declared and cluster is None):
            findings.append(Finding(secret_name, "onboarding-cleanup-pending",
                                    "source is malformed or conflicted; credential retained, not polled; fix its ConfigMap"))
            pending.pop(name, None)
            continue
        matching = cluster is not None and owner == cluster.onboarding
        parsed = parse_secret(obj, host_name=host.name)
        if matching and not isinstance(parsed, Finding):
            tls, ca = declared_trust(cluster)
            matching = (httpx.URL(parsed.api_url) == httpx.URL(cluster.api_url) and parsed.credential_kind == "bearer"
                        and parsed.insecure_skip_verify == (tls == "insecure")
                        and parsed.ca_data == (base64.b64decode(ca).decode() if ca else None))
        elif matching:
            matching = False
        if not matching:
            # Complete inventory proves displacement, or credential/connection data drifted.
            if not writable:
                findings.append(Finding(secret_name, "onboarding-cleanup-pending",
                                        "generated credential is displaced; cleanup requires a single leader and "
                                        "clusterConfig.secrets.writes.enabled; not polled"))
                pending.pop(name, None)
                continue
            try:
                reconcile_onboarding(host_client, namespace, obj)
            except (WriteFailed, WriteRefused):
                findings.append(Finding(secret_name, "onboarding-cleanup-pending",
                                        "generated Secret cleanup failed or ownership changed; retained, not polled; retried next cycle"))
                pending.pop(name, None)
            # Successful delete is still observed in this snapshot: creation waits for a fresh LIST.
            else:
                pending.pop(name, None)
            continue
        # Same connection: policy edits consume no credential and never log in.
        if writable:
            try:
                obj = reconcile_onboarding(host_client, namespace, obj, desired=cluster)
            except (WriteFailed, WriteRefused):
                findings.append(Finding(secret_name, "lookup-write-failed",
                                        "generated Secret policy update failed; declared policy is served; retried next cycle"))
        ready.append(obj)
        pending.pop(name, None)
    # A current declaration whose output is missing is handed to the EXISTING lookup scheduler.
    ordinary = [o for o in ordinary if _data(o)[0].get("name", "").strip() not in blocked]
    clusters, secret_findings = discover(host_client, namespace, host_name=host.name,
                                        values_names=tuple(c.name for c in settings.clusters),
                                        values_modes={c.name: c.credential_kind for c in settings.clusters if c.connection_mode},
                                        items=ordinary + ready)
    findings.extend(secret_findings)
    for i, cluster in enumerate(clusters):
        declaration = desired.get(cluster.name)
        if declaration is not None and cluster.source.split(":", 1)[-1] in outputs:
            clusters[i] = dataclasses.replace(cluster, enabled=declaration.enabled,
                                              visibility=declaration.visibility, identity=declaration.identity,
                                              onboarding=declaration.onboarding)
    # Detect a physical-name collision, including an unlabelled Secret, before spending a login.
    for name, cluster in list(pending.items()):
        with host_client._client() as client:
            try:
                host_client._get(client, f"/api/v1/namespaces/{namespace}/secrets/{secret_name_for(name)}", {})
            except ClusterError as exc:
                if exc.message.startswith("HTTP 404"):
                    continue
                detail = "cannot establish that the output Secret name is free; no lookup attempted"
            else:
                detail = "output Secret already exists and is not this declaration's accepted output; left untouched"
        pending.pop(name)
        findings.append(Finding(cluster.source, "onboarding-ownership-conflict", detail))
    clusters.extend(pending.values())
    return clusters, findings, blocked
```

### Block 31 — `local-development/tests/test_configmap_onboarding.py`

SPEC_S5 implementation and its adversarial regression cases.

<!-- block: local-development/tests/test_configmap_onboarding.py | create -->

```python
"""SPEC_S5: complete inventories, shared parsing, guarded ownership, and the #284 bind budget."""
from __future__ import annotations

import base64
import copy
import dataclasses
import json
import threading

import httpx
import pytest
import yaml

from gsd.clusterconfig import CONFIG_SELECTOR, CONFIG_TYPE_LABEL, LABEL_SELECTOR
from gsd.clusterconfig.onboarding import discover_onboarding
from gsd.clusterconfig.writer import (
    MANAGED_BY_ANNOTATION, MANAGED_BY_ONBOARD, CONFIGMAP_UID_ANNOTATION,
    CreateRequest, WriteRefused, onboarding_owner, rotate, secret_object,
)
from gsd.config import ClusterConfig, ConfigError, load_settings, parse_cluster_entries
from gsd.fleetlookup import CredentialGate, LookupRefused, lookup
from gsd.kube import ClusterError
from gsd.poller import Poller
from gsd.store import Store
from test_clusterconfig_tab import _Host, _as_stored
from test_fleet_lookup import API, PASSWORD, USER, SA_TOKEN, settings, wire  # noqa: F401
from test_fleet_login import login_302, refused_401

STANZA = {"name": "rnd", "apiUrl": API, "saTokenLookup": True, "ldapConnectionBootstrap": USER}


def cm(entries=None, *, name="fleet", uid="cm-1", label="onboard"):
    return {"metadata": {"name": name, "uid": uid, "labels": {CONFIG_TYPE_LABEL: label}},
            "data": {"clusters.yaml": yaml.safe_dump({"clusters": [STANZA] if entries is None else entries})}}


class Host(_Host):
    def __init__(self, maps=None):
        password = {"metadata": {"name": "gsd-fleet-account"},
                    "data": {"password": base64.b64encode(PASSWORD.encode()).decode()}}
        super().__init__({"gsd-fleet-account": password})
        self.maps = [cm()] if maps is None else maps
        self.lists = []
        self.fail_list = None
        self.fail_delete = False
        self.serial = 1
        self.mutations = []
        self.race = False

    def _list_all_with(self, client, path, params):
        self.lists.append((path, params))
        if path.endswith(self.fail_list or "never"):
            raise ClusterError("forbidden", "HTTP 403 on inventory")
        objects = self.maps if path.endswith("/configmaps") else self.secrets.values()
        selector = params.get("labelSelector", "")
        if not selector:
            return copy.deepcopy(list(objects))
        if " in " in selector:
            key, values = selector.split(" in ", 1)
            allowed = {value.strip() for value in values.strip("()").split(",")}
        else:
            key, value = selector.split("=", 1)
            allowed = {value}
        return copy.deepcopy([obj for obj in objects
                              if obj.get("metadata", {}).get("labels", {}).get(key.strip()) in allowed])

    def _send(self, client, method, path, *, json=None, secrets=()):
        self.mutations.append((method, path, copy.deepcopy(json)))
        name = json["metadata"]["name"] if method == "POST" else path.rsplit("/", 1)[-1]
        if method == "DELETE":
            if self.fail_delete:
                raise ClusterError("forbidden", "HTTP 403 on delete")
            if self.race:
                self.secrets[name]["metadata"]["uid"] = "replacement"
            meta = self.secrets[name]["metadata"]
            assert json["preconditions"] == {"uid": "secret-1", "resourceVersion": "1"}
            if any(meta[k] != v for k, v in json["preconditions"].items()):
                raise ClusterError("unreachable", "HTTP 409 on delete")
        if method == "POST" and name in self.secrets:
            raise ClusterError("unreachable", "HTTP 409 on create")
        if method == "PUT":
            if json["metadata"]["resourceVersion"] != self.secrets[name]["metadata"]["resourceVersion"]:
                raise ClusterError("unreachable", "HTTP 409 on update")
        result = super()._send(client, method, path, json=json, secrets=secrets)
        if method != "DELETE":
            self.secrets[name]["metadata"].update(uid="secret-1", resourceVersion=str(self.serial))
            self.serial += 1
        return result


def cycle(host, s=None, *, mutate=True):
    s = s or settings()
    clusters, findings, blocked = discover_onboarding(host, "ns", settings=s, mutate=mutate)
    s.cluster_registry.replace(clusters, findings, at="now", blocked=blocked)
    return s, clusters, findings, blocked


def generated(host, s=None, gate=None):
    s, clusters, _, _ = cycle(host, s)
    declaration, = clusters
    lookup(declaration, s, host, own_namespace="ns", gate=gate or CredentialGate(), sleep=lambda _: None)
    return s


@pytest.mark.parametrize("label", ["onboard", "sideload"])
def test_full_loop_uses_each_synonym_and_the_existing_secret_reader(label, wire):
    host = Host([cm(label=label)])
    s = generated(host)
    _, clusters, findings, _ = cycle(host, s)
    cluster, = clusters
    assert not findings and cluster.source == "secret:gsd-cluster-rnd" and cluster.credential_kind == "bearer"
    assert cluster.resolve_token() == SA_TOKEN and cluster.onboarding[:2] == ("fleet", "cm-1")
    obj = host.secrets["gsd-cluster-rnd"]
    assert obj["metadata"]["labels"] == {"groupsync-dashboard.io/secret-type": "cluster"}
    assert obj["metadata"]["annotations"][MANAGED_BY_ANNOTATION] == MANAGED_BY_ONBOARD
    assert onboarding_owner(obj) == cluster.onboarding
    assert host.lists[:2] == [("/api/v1/namespaces/ns/configmaps", {"labelSelector": CONFIG_SELECTOR}),
                             ("/api/v1/namespaces/ns/secrets", {"labelSelector": LABEL_SELECTOR})]
    assert len(wire.authorize) == 1 and len(wire.revokes) == 1
    writes = len(host.mutations)
    cycle(host, s)
    assert len(host.mutations) == writes, "unchanged reconciliation must not write"


def test_values_and_configmap_call_the_same_parser(tmp_path, monkeypatch):
    import gsd.config as config
    import gsd.clusterconfig.onboarding as onboarding
    calls = []
    real = parse_cluster_entries
    def record(*a, **kw):
        calls.append(kw.get("remote_host"))
        return real(*a, **kw)
    monkeypatch.setattr(config, "parse_cluster_entries", record)
    monkeypatch.setattr(onboarding, "parse_cluster_entries", record)
    home = {"name": "host", "apiUrl": "https://kubernetes.default.svc", "tokenEnv": "X"}
    path = tmp_path / "values.yaml"
    path.write_text(yaml.safe_dump({"clusters": [home, STANZA]}))
    values = load_settings(path)
    runtime_path = tmp_path / "runtime-values.yaml"
    runtime_path.write_text(yaml.safe_dump({"clusters": [home]}))
    runtime = load_settings(runtime_path)
    _, clusters, findings, _ = cycle(Host(), runtime)
    assert not findings and calls[0] is None and calls[1] is None and calls[2] is runtime.host_cluster()
    remote, = clusters
    assert dataclasses.replace(remote, source="values", onboarding=()) == values.clusters[1]


@pytest.mark.parametrize("changes", [
    {"unknown": "sentinel-private-value"}, {"tokenEnv": "X"}, {"tokenFile": ""},
    {"bearerToken": "sentinel-private-value"}, {"password": "sentinel-private-value"},
    {"dashboardController": True}, {"name": "host"}, {"apiUrl": "https://kubernetes.default.svc"},
    {"apiUrl": "https://u:sentinel-private-value@host"}, {"saTokenLookup": "true"},
    {"userSelfLogin": True}, {"saTokenLookup": False}, {"visibility": "typo"},
    {"visibility": "remote-sar", "identity": "none"}, {"enabled": "yes"},
    {"caBundleFile": "/not-a-file", "insecureSkipVerify": True},
    {"labels": {"environment": "prod"}}, {"name": " rnd "},
])
def test_refused_stanzas_never_reach_lookup_or_echo_input(changes, wire, caplog):
    host = Host([cm([{**STANZA, **changes}])])
    _, clusters, findings, _ = cycle(host)
    assert not clusters and findings and not host.mutations and not wire.requests
    assert "sentinel-private-value" not in repr(findings) + caplog.text


@pytest.mark.parametrize("extra", [{"tokenFile": "X"}, {"surprise": True}, {"userSelfLogin": True}, {"enabled": "yes"}])
def test_common_invalid_rules_refuse_both_feeds(extra):
    s = settings()
    home = {"name": "host", "apiUrl": "https://kubernetes.default.svc", "tokenEnv": "X"}
    with pytest.raises(ConfigError):
        parse_cluster_entries([home, {**STANZA, **extra}], "values")
    with pytest.raises(ConfigError):
        parse_cluster_entries([{**STANZA, **extra}], "configmap", remote_host=s.host_cluster())


def test_label_mismatch_is_unclaimed_and_multiple_maps_are_one_list():
    host = Host([cm(name="a"), cm([{**STANZA, "name": "west"}], name="b", label="sideload"),
                 cm(name="ignored", label="cluster")])
    _, clusters, findings, _ = cycle(host)
    assert {c.name for c in clusters} == {"rnd", "west"} and not findings
    assert len(host.lists) == 2


@pytest.mark.parametrize("duplicate", ["values", "map", "same-map", "secret"])
def test_every_conflicting_declaration_is_a_finding_and_none_loads(duplicate):
    host = Host()
    s = settings()
    if duplicate == "values":
        s.clusters.append(ClusterConfig("rnd", API, token_env="X"))
    elif duplicate == "same-map":
        host.maps = [cm([STANZA, STANZA])]
    elif duplicate == "map":
        host.maps.append(cm(name="second", uid="cm-2"))
    else:
        host.secrets["human"] = _as_stored(secret_object(CreateRequest("rnd", API, "bearerToken", token=SA_TOKEN), "ns"))
        host.secrets["human"]["metadata"]["name"] = "human"
    _, clusters, findings, blocked = cycle(host, s)
    assert not clusters and blocked == {"rnd"} and s.cluster("rnd") is None
    assert len([f for f in findings if f.code == "duplicate-cluster-name"]) == 2
    assert not host.mutations


@pytest.mark.parametrize("labelled", [False, True])
def test_existing_physical_secret_name_is_never_adopted_or_bound(labelled, wire):
    host = Host()
    obj = secret_object(CreateRequest("other", API, "bearerToken", token=SA_TOKEN), "ns")
    obj["metadata"]["name"] = "gsd-cluster-rnd"
    if not labelled:
        obj["metadata"]["labels"] = {}
    host.secrets["gsd-cluster-rnd"] = _as_stored(obj)
    before = copy.deepcopy(host.secrets)
    _, clusters, findings, _ = cycle(host)
    assert "rnd" not in {c.name for c in clusters}
    assert any(f.code == "onboarding-ownership-conflict" for f in findings)
    assert host.secrets == before and not host.mutations and not wire.requests


@pytest.mark.parametrize("removal", ["entry", "map", "label", "uid"])
def test_removed_outputs_are_pruned_from_inventory_even_after_restart(removal, wire):
    host = Host(); generated(host)
    if removal == "entry": host.maps = [cm([])]
    if removal == "map": host.maps = []
    if removal == "label": host.maps = [cm(label="elsewhere")]
    if removal == "uid": host.maps = [cm(uid="replacement-cm")]
    # A new Settings has an empty registry: deletion cannot depend on the previous process's set.
    _, clusters, _, _ = cycle(host, settings())
    assert "gsd-cluster-rnd" not in host.secrets and not clusters
    method, _, body = host.mutations[-1]
    assert method == "DELETE" and body["preconditions"] == {"uid": "secret-1", "resourceVersion": "1"}


def test_failed_delete_is_retried_each_cycle_without_displaced_set_memory(wire):
    host = Host(); generated(host); host.maps = []
    host.fail_delete = True
    for _ in range(2):
        _, clusters, findings, _ = cycle(host, settings())
        assert not clusters and any(f.code == "onboarding-cleanup-pending" for f in findings)
        assert "gsd-cluster-rnd" in host.secrets
    host.fail_delete = False
    cycle(host, settings())
    assert "gsd-cluster-rnd" not in host.secrets
    assert [m[0] for m in host.mutations].count("DELETE") == 3


def test_delete_preconditions_protect_a_replacement_object(wire):
    host = Host(); generated(host); host.maps = []; host.race = True
    _, clusters, findings, _ = cycle(host)
    assert not clusters and findings
    assert host.secrets["gsd-cluster-rnd"]["metadata"]["uid"] == "replacement"


@pytest.mark.parametrize("corrupt", ["owner", "name", "uid"])
def test_changed_ownership_is_never_deleted(wire, corrupt):
    host = Host(); generated(host); host.maps = []
    obj = host.secrets["gsd-cluster-rnd"]
    if corrupt == "owner": obj["metadata"]["annotations"][MANAGED_BY_ANNOTATION] = "ui"
    if corrupt == "name": obj["data"]["name"] = base64.b64encode(b"other").decode()
    if corrupt == "uid": obj["metadata"]["annotations"].pop(CONFIGMAP_UID_ANNOTATION)
    cycle(host)
    assert "gsd-cluster-rnd" in host.secrets and len(host.mutations) == 1


@pytest.mark.parametrize("malformed", ["clusters: [", "clusters: null", "clusters: []\nclusters: []", "other: []"])
def test_bad_documents_hold_outputs_without_polling_or_deleting(wire, malformed):
    host = Host(); generated(host)
    host.maps[0]["data"]["clusters.yaml"] = malformed
    _, clusters, findings, _ = cycle(host)
    assert not clusters and "gsd-cluster-rnd" in host.secrets
    assert len(host.mutations) == 1 and any(f.code == "onboarding-invalid" for f in findings)


@pytest.mark.parametrize("failed", ["/configmaps", "/secrets"])
def test_failed_list_is_not_absence_and_cannot_authorize_lookup(tmp_path, monkeypatch, wire, failed):
    host = Host(); s = generated(host); host.maps = []; host.fail_list = failed
    poller = Poller(Store(str(tmp_path / "p.db")), s)
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: host)
    before = s.cluster_registry.discovered()
    poller._discover_once(); poller._retrieve_pending()
    assert s.cluster_registry.discovered() == before and s.cluster_registry.error
    assert len(host.mutations) == 1 and len(wire.authorize) == 1


@pytest.mark.parametrize("mutate,writes", [(False, True), (True, False)])
def test_read_only_or_nonleader_reports_cleanup_and_never_deletes(wire, mutate, writes):
    host = Host(); generated(host); host.maps = []
    _, clusters, findings, _ = cycle(host, settings(writes=writes), mutate=mutate)
    assert not clusters and len(host.mutations) == 1
    assert any(f.code == "onboarding-cleanup-pending" for f in findings)


def test_policy_and_enabled_changes_keep_the_token_and_do_not_bind(wire):
    host = Host(); s = generated(host)
    host.maps = [cm([{**STANZA, "enabled": False, "visibility": "self-only", "identity": "none"}])]
    _, clusters, findings, _ = cycle(host, s)
    cluster, = clusters
    assert not findings and not cluster.enabled and cluster.resolve_token() == SA_TOKEN
    assert s.cluster_policy("rnd") == ("self-only", "none")
    stored = host.secrets["gsd-cluster-rnd"]
    assert base64.b64decode(stored["data"]["enabled"]) == b"false"
    assert [m[0] for m in host.mutations] == ["POST", "PUT"] and len(wire.authorize) == 1


@pytest.mark.parametrize("answer", ["success", "401", "403", "500", "timeout", "bad-read", "write-failure"])
def test_one_bind_budget_survives_rename_and_policy_changes(wire, answer):
    host = Host(); s, clusters, _, _ = cycle(host); cluster, = clusters
    gate = CredentialGate()
    if answer == "401": wire.answers = [refused_401()]
    if answer == "403": wire.answers = [httpx.Response(403)]
    if answer == "500": wire.answers = [httpx.Response(500)]
    if answer == "timeout": wire.answers = [lambda r: httpx.ReadTimeout("lost after send")]
    if answer == "bad-read": wire.secret = httpx.Response(403, text=SA_TOKEN)
    if answer == "write-failure": host.refuse = True
    try:
        lookup(cluster, s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
    except LookupRefused as error:
        assert answer != "success"
        if answer == "403":
            assert gate.refused(API, USER, PASSWORD) and "phase=credential" in error.detail
    for _ in range(5):
        _, current, _, _ = cycle(host, s)
        if answer == "success":
            assert current[0].credential_kind == "bearer"
        else:
            with pytest.raises(LookupRefused) as exc:
                lookup(current[0], s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
            assert exc.value.gated
        assert len(wire.authorize) == 1
    wire.answers = [login_302()]
    moved = dataclasses.replace(cluster, name="renamed", source="configmap:new-name:9", visibility="self-only",
                                api_url=API.replace("api.example", "API.Example"), onboarding=("new-name", "new-uid", "a" * 64))
    with pytest.raises(LookupRefused) as exc:
        lookup(moved, s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
    assert exc.value.gated and len(wire.authorize) == 1
    assert SA_TOKEN not in str(exc.value)


def test_conflicting_values_thread_stops_and_its_history_retires(tmp_path, monkeypatch):
    host = Host()
    s = settings(ClusterConfig("rnd", API, token_env="X"))
    store = Store(str(tmp_path / "p.db")); store.upsert_cluster("rnd", API, True)
    poller = Poller(store, s); poller._cluster_stops["rnd"] = threading.Event()
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: host)
    monkeypatch.setattr(poller, "_start_cluster_thread", lambda _: None)
    poller._discover_once(); poller._reconcile_threads()
    assert poller._cluster_stops["rnd"].is_set()
    assert next(r for r in store.clusters() if r["id"] == "rnd")["enabled"] == 0
    host.maps = []
    poller._discover_once()
    assert s.cluster("rnd") is not None


def test_generated_secret_cannot_be_rotated_through_stale_ui_state(wire):
    host = Host(); generated(host)
    with pytest.raises(WriteRefused, match="source ConfigMap"):
        rotate(host, "ns", "gsd-cluster-rnd", "replacement-token", viewer="root", cluster="rnd")
    assert len(host.mutations) == 1


@pytest.mark.parametrize("writes,enabled", [(False, True), (True, False)])
def test_off_switches_do_not_spend_a_configmap_bind(wire, writes, enabled):
    host = Host(); s, clusters, _, _ = cycle(host, settings(writes=writes))
    s = dataclasses.replace(s, cluster_secrets_enabled=enabled)
    with pytest.raises(LookupRefused) as exc:
        lookup(clusters[0], s, host, own_namespace="ns", gate=CredentialGate(), sleep=lambda _: None)
    assert exc.value.code == "fleet-write-disabled" and not wire.requests and not host.mutations


def test_disabled_pending_declaration_is_not_retrieved(tmp_path, monkeypatch, wire):
    host = Host([cm([{**STANZA, "enabled": False}])]); s, _, _, _ = cycle(host)
    poller = Poller(Store(str(tmp_path / "p.db")), s)
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: host)
    poller._retrieve_pending()
    assert not wire.requests and not host.mutations


def test_password_rotation_rearms_the_existing_gate(wire):
    host = Host(); s, clusters, _, _ = cycle(host); gate = CredentialGate()
    wire.answers = [refused_401()]
    with pytest.raises(LookupRefused):
        lookup(clusters[0], s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
    host.secrets["gsd-fleet-account"]["data"]["password"] = base64.b64encode(b"rotated-password").decode()
    wire.answers = [login_302()]
    lookup(clusters[0], s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
    assert len(wire.authorize) == 2 and "gsd-cluster-rnd" in host.secrets


def test_connection_change_prunes_before_any_recreation(wire):
    host = Host(); s = generated(host)
    host.maps = [cm([{**STANZA, "insecureSkipVerify": True}])]
    _, clusters, _, _ = cycle(host, s)
    assert not clusters and "gsd-cluster-rnd" not in host.secrets
    _, clusters, _, _ = cycle(host, s)
    assert len(clusters) == 1 and clusters[0].credential_pending is not None
    assert len(wire.authorize) == 1


def test_displaced_owned_output_is_held_when_new_authors_conflict(wire):
    host = Host(); generated(host)
    host.maps = [cm(name="new-a", uid="a"), cm(name="new-b", uid="b")]
    _, clusters, findings, blocked = cycle(host)
    assert not clusters and blocked == {"rnd"} and "gsd-cluster-rnd" in host.secrets
    assert any(f.code == "onboarding-cleanup-pending" for f in findings)
    assert len(host.mutations) == 1


def test_numeric_values_names_reserve_the_same_identity_as_quoted_names():
    host = Host([cm([{**STANZA, "name": 1}]), cm([{**STANZA, "name": "1"}], name="second", uid="cm-2")])
    _, clusters, findings, blocked = cycle(host)
    assert not clusters and blocked == {"1"}
    assert len([f for f in findings if f.code == "duplicate-cluster-name"]) == 2
    assert not host.mutations


@pytest.mark.parametrize("api", [
    f"{scheme}://{name}{port}"
    for name in ("kubernetes.default.svc", "kubernetes.default.svc.cluster.local", "kubernetes.default")
    for scheme in ("http", "https") for port in ("", ":443", ":6443")
] + ["https://KUBERNETES.DEFAULT.SVC.:8443"])
def test_in_cluster_url_aliases_are_host_and_do_not_bind(api, wire):
    with pytest.raises(ConfigError, match="host is declared only in values"):
        parse_cluster_entries([{**STANZA, "apiUrl": api}], "configmap", remote_host=settings().host_cluster())
    host = Host([cm([{**STANZA, "apiUrl": api}])])
    _, clusters, findings, _ = cycle(host)
    assert not clusters and not host.mutations and not wire.requests
    assert any(f.code == "onboarding-invalid" for f in findings)


@pytest.mark.parametrize("host_url,api", [
    ("https://api.host.example", "https://API.HOST.EXAMPLE:443/"),
    ("https://api.host.example:6443", "https://api.host.example:6443/"),
    ("http://api.host.example", "http://api.host.example:80"),
])
def test_values_host_endpoint_is_refused(host_url, api, wire):
    s = settings()
    s.clusters[0] = dataclasses.replace(s.clusters[0], api_url=host_url)
    with pytest.raises(ConfigError, match="host is declared only in values"):
        parse_cluster_entries([{**STANZA, "apiUrl": api}], "configmap", remote_host=s.host_cluster())
    _, clusters, findings, _ = cycle(Host([cm([{**STANZA, "apiUrl": api}])]), s)
    assert not clusters and not wire.requests
    assert any(f.code == "onboarding-invalid" for f in findings)


@pytest.mark.parametrize("host_url", ["https://kubernetes.default.svc", "https://api.example.com:443",
                                     "http://api.example.com:6443"])
def test_external_url_of_same_cluster_is_allowed(host_url, wire):
    # shared-rnd intentionally uses its external API even when it is the controller's physical cluster.
    s = settings()
    s.clusters[0] = dataclasses.replace(s.clusters[0], api_url=host_url)
    host = Host([cm([{**STANZA, "name": "shared-rnd"}])])
    generated(host, s)
    assert "gsd-cluster-shared-rnd" in host.secrets and len(wire.authorize) == 1


def test_insecure_configmap_is_accepted_and_secret_preserves_tls_choice(wire):
    """The operator's ruling, end to end: the stanza's insecure flag reaches the Secret, the Secret parses back
    as insecure, and the rediscovered cluster polls with verification off, all on one bind."""
    from gsd.clusterconfig.parser import parse_secret
    host = Host([cm([{**STANZA, "insecureSkipVerify": True}])])
    generated(host)
    obj = host.secrets["gsd-cluster-rnd"]
    config = json.loads(base64.b64decode(obj["data"]["config"]))
    assert config["tlsClientConfig"]["insecure"] is True
    parsed = parse_secret(obj, host_name="host")
    assert parsed.insecure_skip_verify is True and parsed.verify() is False
    _, clusters, _, _ = cycle(host)
    live, = clusters
    assert live.source == "secret:gsd-cluster-rnd"
    assert live.insecure_skip_verify is True and live.verify() is False
    assert len(wire.authorize) == 1


@pytest.mark.parametrize("answer", ["403", "bad-read", "write-failure"])
def test_configmap_bind_budget_through_the_poller(tmp_path, monkeypatch, wire, answer):
    """#284's lesson, composed: the budget holds through the Poller's own scheduler across six cycles, not only
    through a direct lookup call (Grok, review of #363, N2)."""
    host = Host()
    s = settings()
    poller = Poller(Store(str(tmp_path / "cm-budget.db")), s)
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: host)
    if answer == "403":
        wire.answers = [httpx.Response(403)]
    if answer == "bad-read":
        wire.secret = httpx.Response(403, text=SA_TOKEN)
    if answer == "write-failure":
        host.refuse = True
    for _ in range(6):
        for state in poller._lookups.values():
            state.not_before = 0
        poller._discover_once()
        poller._retrieve_pending()
    assert len(wire.authorize) == 1


def test_invalid_configmap_stanza_does_not_stop_values(tmp_path, monkeypatch):
    host = Host([cm([{**STANZA, "unknown": True}])])
    s = settings(ClusterConfig("rnd", API, token_env="X"))
    poller = Poller(Store(str(tmp_path / "invalid.db")), s)
    poller._cluster_stops["rnd"] = threading.Event()
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: host)
    monkeypatch.setattr(poller, "_start_cluster_thread", lambda _: None)
    _, _, findings, blocked = cycle(host, s)
    poller._discover_once(); poller._reconcile_threads()
    assert blocked == set() and not poller._cluster_stops["rnd"].is_set()
    assert s.cluster("rnd").source == "values"
    assert any(f.code == "onboarding-invalid" for f in findings)
    assert not any(f.code == "duplicate-cluster-name" for f in findings)


@pytest.mark.parametrize("feed", ["configmap", "values"])
@pytest.mark.parametrize("failure", ["connect", "tls"])
def test_pre_write_failure_can_retry(feed, failure, wire):
    host = Host(); s, clusters, _, _ = cycle(host)
    cluster = clusters[0] if feed == "configmap" else dataclasses.replace(clusters[0], onboarding=(), source="values")
    gate = CredentialGate()
    def before_write(request):
        import ssl
        if failure == "tls":
            raise httpx.ConnectError("certificate verify failed") from ssl.SSLCertVerificationError("untrusted")
        raise httpx.ConnectError("connection refused")
    wire.answers = [before_write] * 10
    with pytest.raises(LookupRefused):
        lookup(cluster, s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
    assert not gate.refused(API, USER, PASSWORD)
    attempted = len(wire.authorize)
    wire.answers = [login_302()]
    lookup(cluster, s, host, own_namespace="ns", gate=gate, sleep=lambda _: None)
    assert len(wire.authorize) == attempted + 1 and "gsd-cluster-rnd" in host.secrets


@pytest.mark.parametrize("feed", ["configmap", "values"])
def test_restart_has_a_new_bind_budget(feed, wire):
    host = Host(); s, clusters, _, _ = cycle(host)
    cluster = clusters[0] if feed == "configmap" else dataclasses.replace(clusters[0], onboarding=(), source="values")
    wire.answers = [login_302(), login_302()]
    for _ in range(2):
        # A process/replica gets a fresh gate; no durable claim exists in S5.
        wire.secret = httpx.Response(403)
        with pytest.raises(LookupRefused):
            lookup(cluster, s, host, own_namespace="ns", gate=CredentialGate(), sleep=lambda _: None)
    assert len(wire.authorize) == 2


@pytest.mark.parametrize("answer", ["success", "401", "403", "500", "timeout", "bad-read", "write-failure"])
def test_values_bind_budget_is_unchanged(tmp_path, monkeypatch, wire, answer):
    from gsd.fleetlookup import LOOKUP_ATTEMPTS
    host = Host([])
    s = settings(parse_cluster_entries([STANZA], "values", remote_host=settings().host_cluster())[0])
    poller = Poller(Store(str(tmp_path / "values.db")), s)
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **kw: host)
    if answer == "401": wire.answers = [refused_401()]
    if answer == "403": wire.answers = [httpx.Response(403)]
    if answer == "500": wire.answers = [httpx.Response(500)]
    if answer == "timeout": wire.answers = [lambda r: httpx.ReadTimeout("lost after send")]
    if answer == "bad-read": wire.secret = httpx.Response(403)
    if answer == "write-failure": host.refuse = True
    if answer in ("bad-read", "write-failure"):
        wire.answers = [login_302() for _ in range(LOOKUP_ATTEMPTS)]
    for _ in range(6):  # first cycle, then the next five, with the retry delay elapsed
        for state in poller._lookups.values():
            state.not_before = 0
        poller._discover_once(); poller._retrieve_pending()
    expected = min(6, LOOKUP_ATTEMPTS) if answer in ("bad-read", "write-failure") else 1
    assert len(wire.authorize) == expected
```

### Block 32 — `local-development/gsd/clusterconfig/writer.py`

A stale UI must not mutate an output now owned by a ConfigMap.

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->

Old text:

```python
def _read_ours(host_client: ClusterClient, client, namespace: str, name: str) -> dict:
```

New text:

```python
def _read_ours(host_client: ClusterClient, client, namespace: str, name: str, *, allow_onboarding: bool = False) -> dict:
```

### Block 33 — `local-development/gsd/clusterconfig/writer.py`

The UI/read-rotate-delete paths reject generator-managed output even when the API snapshot is stale.

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->

Old text:

```python
    if not _labelled(obj):
```

New text:

```python
    if not allow_onboarding and (obj.get("metadata", {}).get("annotations") or {}).get(MANAGED_BY_ANNOTATION) == MANAGED_BY_ONBOARD:
        raise WriteRefused("not-our-secret", "edit the source ConfigMap; its generated Secret is reconciled automatically", conflict=True)
    if not _labelled(obj):
```

### Block 34 — `local-development/gsd/clusterconfig/writer.py`

Only the stricter reconciliation helper opts in to generated Secret mutations.

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->

Old text:

```python
        obj = _read_ours(host_client, client, namespace, name)
        current = obj.get("metadata") or {}
```

New text:

```python
        obj = _read_ours(host_client, client, namespace, name, allow_onboarding=True)
        current = obj.get("metadata") or {}
```

### Block 35 — `local-development/gsd/poller.py`

No fallback to a stale credential after a conflict, removal or pending transition.

<!-- block: local-development/gsd/poller.py | edit -->

Old text:

```python
            cluster = self.settings.cluster(cluster.name) or cluster
```

New text:

```python
            current = self.settings.cluster(cluster.name)
            if current is None or not current.enabled or current.credential_pending is not None:
                break
            cluster = current
```

### Block 36 — `local-development/gsd/api.py`

Expose the ConfigMap selector on the existing protected endpoint.

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
        from .clusterconfig import LABEL_SELECTOR
```

New text:

```python
        from .clusterconfig import CONFIG_SELECTOR, LABEL_SELECTOR
```

### Block 37 — `local-development/gsd/api.py`

Source provenance is public only at the existing clusterconfig:view gate; no token.

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
                "retired": False,
```

New text:

```python
                "retired": False, "onboarding_configmap": c.onboarding[0] if c.onboarding else None,
```

### Block 38 — `local-development/gsd/api.py`

Keep the legacy finding.secret field; ConfigMap sources are qualified there.

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
            "clusters": clusters,
            "findings": [f.public() for f in registry.findings()],
```

New text:

```python
            "configmaps": {"enabled": settings.cluster_secrets_enabled, "label": CONFIG_SELECTOR},
            "clusters": clusters,
            "findings": [f.public() for f in registry.findings()],
```

### Block 39 — `local-development/gsd/api.py`

Return an actionable 409 for UI Rotate/Delete on generated output.

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
        if not cluster.source.startswith("secret:"):
```

New text:

```python
        if cluster.onboarding:
            raise _write_error(WriteRefused("not-our-secret", "edit the source ConfigMap; this Secret is generated", conflict=True))
        if not cluster.source.startswith("secret:"):
```

### Block 40 — `local-development/gsd/static/index.html`

Pending onboarding must not be mislabelled as values.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```text
  return String(c.source || "").indexOf("secret:") === 0 ? "secret" : "values";
```

New text:

```text
  if (String(c.source || "").startsWith("configmap:")) return "configmap";
  return String(c.source || "").indexOf("secret:") === 0 ? "secret" : "values";
```

### Block 41 — `local-development/gsd/static/index.html`

Give ConfigMap-sourced pending clusters their own source chip.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```text
  const word = kind === "secret" ? `Secret ${c.source.slice(7)}` : kind === "in-cluster" ? "in-cluster" : "values";
```

New text:

```text
  const word = kind === "secret" ? `Secret ${c.source.slice(7)}` : kind === "configmap" ? `ConfigMap ${c.source.split(":")[1]}` : kind === "in-cluster" ? "in-cluster" : "values";
```

### Block 42 — `local-development/gsd/static/index.html`

Generated rows give the authoring location instead of Rotate.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```text
  if (secretRow && !c.retired && ccWritesOn()) {
```

New text:

```text
  if (c.onboarding_configmap && !c.retired) {
    out += ` <span class="cc-hint">managed by ConfigMap ${esc(c.onboarding_configmap)} — edit the stanza there</span>`;
  } else if (secretRow && !c.retired && ccWritesOn()) {
```

### Block 43 — `local-development/gsd/static/index.html`

Generated rows give the authoring location instead of Delete.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```text
  } else if (secretRow && !ccWritesOn()) {
```

New text:

```text
  } else if (c.onboarding_configmap) {
    foot = `<div class="cc-foot">declared in ConfigMap ${esc(c.onboarding_configmap)} — remove the stanza there; its Secret is cleaned up automatically</div>`;
  } else if (secretRow && !ccWritesOn()) {
```

### Block 44 — `local-development/gsd/static/index.html`

The legacy finding.secret key now identifies any declaration.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```text
    <div class="cc-kv"><span class="k">secret</span><span class="v mono">${esc(f.secret)}</span></div>
```

New text:

```text
    <div class="cc-kv"><span class="k">source</span><span class="v mono">${esc(f.secret)}</span></div>
```

### Block 45 — `local-development/gsd/static/index.html`

Count pending ConfigMap declarations.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```text
  const n = { "in-cluster": 0, values: 0, secret: 0 };
```

New text:

```text
  const n = { "in-cluster": 0, values: 0, secret: 0, configmap: 0 };
```

### Block 46 — `local-development/gsd/static/index.html`

Show both selectors without changing the Secret selector.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```text
      <span class="rp-chip cc-src-secret">Secret ${n.secret}</span></span></div>
```

New text:

```text
      <span class="rp-chip cc-src-secret">Secret ${n.secret}</span>
      <span class="rp-chip">ConfigMap ${n.configmap}</span></span></div>
    <div class="cc-kv"><span class="k">ConfigMap selector</span><span class="v mono">${esc((d.configmaps || {}).label || "")}</span></div>
```

### Block 47 — `local-development/gsd/static/index.html`

No new finding dictionary is needed: the page renders code and detail generically.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```text
    || `<div class="empty-note">No malformed Secrets. A Secret that fails to parse is a finding with the code named, never a crashed pod.</div>`;
```

New text:

```text
    || `<div class="empty-note">No configuration findings. Refused Secrets and ConfigMap stanzas are listed here with their source and reason.</div>`;
```

### Block 48 — `charts/group-sync-dashboard/templates/cluster-secrets-rbac.yaml`

ConfigMaps get read verbs only; the existing Secret write conditional is untouched.

<!-- block: charts/group-sync-dashboard/templates/cluster-secrets-rbac.yaml | edit -->

Old text:

```yaml
rules:
  - apiGroups: [""]
```

New text:

```yaml
rules:
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
```

### Block 49 — `charts/group-sync-dashboard/values.yaml`

Reuse the existing discovery capability switch; the ConfigMap label declares opt-in intent.

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```yaml
clusterConfig:
  secrets:
    enabled: true
```

New text:

```yaml
clusterConfig:
  secrets:
    # Discovery includes ConfigMaps labelled config-type: onboard or sideload in this namespace.
    # They contain data.clusters.yaml with values-shaped clusters, never credentials (#293, SPEC_S5).
    # The existing switch controls the whole discovery stage; no ConfigMap is written by the app.
    enabled: true
```

### Block 50 — `charts/group-sync-dashboard/values.yaml`

Name the new consumer and the ConfigMap-author trust boundary beside the switch.

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```yaml
    # says so, per cluster; SPEC_S4b). It does not split, because a second switch would gate the
```

New text:

```yaml
    # says so, per cluster; SPEC_S4b), including ConfigMap onboarding (SPEC_S5): creates, policy
    # updates and repeated cleanup of displaced generated Secrets all require this switch.
    # ConfigMap writers in this namespace can initiate a fleet lookup; limit that RBAC to platform
    # operators. It does not split, because a second switch would gate the
```

### Block 51 — `local-development/tests/test_clusterconfig.py`

Adapt the poller fake to ConfigMap discovery; existing Secret tests remain meaningful.

<!-- block: local-development/tests/test_clusterconfig.py | edit -->

Old text:

```python
        if path == "/api/v1/namespaces/ns/secrets":
```

New text:

```python
        if path == "/api/v1/namespaces/ns/configmaps":
            return {"items": []}
        if path == "/api/v1/namespaces/ns/secrets":
```

### Block 52 — `local-development/tests/test_clusterconfig.py`

Pin the expanded read-only Role rather than weakening its exact grant check.

<!-- block: local-development/tests/test_clusterconfig.py | edit -->

Old text:

```python
        assert role["rules"] == [{"apiGroups": [""], "resources": ["secrets"], "verbs": ["get", "list", "watch"]}]
```

New text:

```python
        assert role["rules"] == [
            {"apiGroups": [""], "resources": ["configmaps"], "verbs": ["get", "list", "watch"]},
            {"apiGroups": [""], "resources": ["secrets"], "verbs": ["get", "list", "watch"]}]
```

### Block 53 — `local-development/tests/test_clusterconfig_logging.py`

The log-transition fake remains a Secret feed with no onboarding declarations.

<!-- block: local-development/tests/test_clusterconfig_logging.py | edit -->

Old text:

```python
    def _list_all_with(self, client, path, params):
        return self.items
```

New text:

```python
    def _list_all_with(self, client, path, params):
        return [] if path.endswith("/configmaps") else self.items
```

### Block 54 — `local-development/tests/test_clusterconfig_logging.py`

Mock the discovery entry point now called by the poller.

<!-- block: local-development/tests/test_clusterconfig_logging.py | edit -->

Old text:

```python
        monkeypatch.setattr("gsd.clusterconfig.discover",
```

New text:

```python
        monkeypatch.setattr("gsd.clusterconfig.onboarding.discover_onboarding",
```

### Block 55 — `local-development/tests/test_specs_index.py`

S5 is a new design in the S batch, not a lettered step of S4; the index gains one row.

<!-- block: local-development/tests/test_specs_index.py | edit -->

Old text:

```python
    assert len(rows) == 24, f"expected twenty-four index rows (the programme's thirteen, D2b, E1, S1, S2, S3, S4, S4a, S4b, S4c, T1 and U1), matched {sorted(rows)}"
```

New text:

```python
    assert len(rows) == 25, f"expected twenty-five index rows, including S5 (#293); matched {sorted(rows)}"
```

### Block 56 — `local-development/tests/test_specs_index.py`

The issue set is hard-coded; admitting S5 must not disable the check.

<!-- block: local-development/tests/test_specs_index.py | edit -->

Old text:

```python
    assert s_issues == {230, 283, 284, 285}, f"the S batch is #230 (S1-S3), #283 (S4, S4a), #284 (S4b) and #285 (S4c); got {sorted(s_issues)}"
```

New text:

```python
    assert s_issues == {230, 283, 284, 285, 293}, f"the S batch includes ConfigMap onboarding #293 (S5); got {sorted(s_issues)}"
```

### Block 57 — `charts/group-sync-dashboard/Chart.yaml`

Phase 2 reads app 0.33.0 / chart 0.54.0 after #360 and assigns the next minor (operator, 2026-09-25).

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

Old text:

```yaml
version: 0.54.0
```

New text:

```yaml
# SPEC_S5 (#293): ConfigMap onboarding and namespaced read RBAC; minor release.
version: 0.55.0
```

### Block 58 — `charts/group-sync-dashboard/Chart.yaml`

Phase 2 reads app 0.33.0 / chart 0.54.0 after #360 and assigns the next minor (operator, 2026-09-25).

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

Old text:

```yaml
appVersion: "0.33.0"
```

New text:

```yaml
appVersion: "0.34.0"
```

### Block 59 — `local-development/pyproject.toml`

Phase 2 reads app 0.33.0 / chart 0.54.0 after #360 and assigns the next minor (operator, 2026-09-25).

<!-- block: local-development/pyproject.toml | edit -->

Old text:

```text
version = "0.33.0"
```

New text:

```text
version = "0.34.0"
```

### Block 60 — `local-development/gsd/__init__.py`

Phase 2 reads app 0.33.0 / chart 0.54.0 after #360 and assigns the next minor (operator, 2026-09-25).

<!-- block: local-development/gsd/__init__.py | edit -->

Old text:

```python
__version__ = "0.33.0"
```

New text:

```python
__version__ = "0.34.0"
```

### Block 61 — `docs/CLUSTER_STANZA.md`

Document SPEC_S5 at the relevant contract; prior measured tables remain historical.

<!-- block: docs/CLUSTER_STANZA.md | after: # The cluster stanza — every accepted combination, measured -->

```text

## ConfigMap onboarding (#293, SPEC_S5)

The existing measured values tables below remain the values contract. The additional runtime authoring
path is a ConfigMap in the release namespace; its stanzas call the same parser as values. Example:

    apiVersion: v1
    kind: ConfigMap
    metadata:
      name: cluster-onboarding
      namespace: group-sync-dashboard
      labels:
        groupsync-dashboard.io/config-type: onboard  # sideload is an exact synonym
    data:
      clusters.yaml: |
        clusters:
          - name: ocp-east
            apiUrl: https://api.ocp-east.example.com:6443
            saTokenLookup: true
            enabled: true

Use either `groupsync-dashboard.io/config-type: onboard` or `sideload`; any number of maps may match.
`data.clusters.yaml` must contain only a `clusters` list; `clusters: []` intentionally removes all entries.
Extra data keys, `binaryData`, duplicate YAML keys and malformed YAML are refused. No token, password,
`tokenFile` or `tokenEnv` belongs in this feed. `saTokenLookup: true` is required; `userSelfLogin` is not
implemented here. The host remains values-only. Unknown stanza keys are refused, including `labels`
(the values stanza does not accept it). Custom ConfigMap metadata labels do not become Secret labels.
`insecureSkipVerify: true` is accepted and preserved in the generated Secret.
Use the existing TLS/policy keys; a `caBundleFile` must already exist in the dashboard container and
cover the API and OAuth hosts. The generated Secret is also validated before a login is attempted.

Both feeds share `clusterConfig.secrets.enabled`. Creating, updating or deleting generated Secrets
requires `clusterConfig.secrets.writes.enabled`; ConfigMaps themselves are never written by the app.
The namespace's ConfigMap writers can initiate fleet credential lookups: reserve that permission for
platform operators. The existing fleet account/password and remote token-reader grants still apply.

A name repeated in values and a valid ConfigMap stanza, within one map, across maps, or in an unrelated labelled
Secret loads neither declaration and produces a finding for each. A ConfigMap cannot disable or
replace the values host: host declarations are refused before conflict resolution.
An invalid stanza reserves its name only to hold cleanup; it never blocks a values cluster.
Secret-versus-values precedence outside this feed is unchanged.

Edit or remove the source stanza. Policy and `enabled` edits reuse the credential; connection changes
retire and prune the prior output before another lookup. Confirmed removals (including map deletion,
label removal and UID replacement) repeatedly delete only outputs owned by this generator. History
stays. Failed cleanup remains a finding and is retried, including after restart. Invalid documents
hold their outputs without polling or deleting them; a failed inventory read keeps the prior fleet.

The ConfigMap trigger marks the existing process-lifetime CredentialGate on a bound
login failure and on a successful session (before the token read). After that mark,
the same canonical target/account/password is not sent again in this process, including
after a rename, policy edit, or a later read/write failure. A TLS or connect failure
before the password is written may bind again. A restart or another replica binds
again. There is no durable or replica-shared claim until #285. A missing output after that budget was spent stays pending with a finding; fix the
cause and rotate the credential or deliberately restart after checking the account. Routine policy
edits need neither. Do not delete an output as
a way to remove the declaration; the source is the record. Turning discovery off suspends all cleanup;
remove declarations and wait for cleanup before disabling the feed.

```

### Block 62 — `docs/polling-and-discovery.md`

Document SPEC_S5 at the relevant contract; prior measured tables remain historical.

<!-- block: docs/polling-and-discovery.md | after: # Polling, cluster discovery, and forcing a refresh -->

```text

## ConfigMap discovery and cleanup (#293, SPEC_S5)

The runtime sources now include release-namespace ConfigMaps selected by
`groupsync-dashboard.io/config-type in (onboard,sideload)`. Each has `data.clusters.yaml` containing
the same `clusters:` stanzas as values, with `saTokenLookup: true` and no credential or token reference.
The manifest and refusal rules are in `docs/CLUSTER_STANZA.md`.

One complete paged ConfigMap LIST and one complete labelled Secret LIST precede reconciliation on the
existing binding cadence and at startup. Both use the host client, the release namespace and their
own selector. This is polling, not a watch; the read grant retains `get/list/watch` to match the Secret
feed. A successful lookup wakes ordinary Secret discovery. GitOps additions wait for the cadence plus
lookup/discovery/poll duration; the earlier measured Secret timings below are not a ConfigMap measurement.

Cleanup compares the current inventories every cycle. It never relies on a one-time removed-name
set: deleting a stanza, its map, its label or replacing the map UID retires its generated output, and
a failed deletion is retried after the next LIST, also after restart. Eligibility requires the
`secret-type: cluster` label, `managed-by: configmap-onboarding`, `token-source: remote-lookup`,
source ConfigMap name and UID, a 64-hex connection hash, and data.name matching the deterministic
`gsd-cluster-<name>` Secret name. A re-read checks ownership and UID/resourceVersion, and DELETE
carries both preconditions to protect replacements.
Writes off or a nonleader causes no mutation. Displaced outputs stop polling and have a standing
cleanup finding while retained. An invalid document is not evidence of removal. A failed LIST keeps
the previous registry and prevents retrieval from stale intent until both inventories succeed.

The existing discovery transition logger announces new/cleared findings. New codes are
`onboarding-invalid`, `onboarding-cleanup-pending`, and `onboarding-ownership-conflict`; duplicate
sources use `duplicate-cluster-name`. Successful policy writes use `cluster-secret-updated` and
cleanup uses `cluster-secret-deleted`. The existing lookup events and gate remain the credential path.
Neither policy edits nor cleanup authenticates to a remote cluster.

```

### Block 63 — `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md`

Document SPEC_S5 at the relevant contract; prior measured tables remain historical.

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | after: # Cluster credentials: how a connection is made, how it breaks, how to get it back -->

```text

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

```

### Block 64 — `local-development/API.md`

Document SPEC_S5 at the relevant contract; prior measured tables remain historical.

<!-- block: local-development/API.md | after: # API reference -->

```text

## ConfigMap onboarding additions to `/api/clusterconfigs` (#293, SPEC_S5)

The existing `clusterconfig:view` gate covers both feeds; there is no new write endpoint. The response
adds `configmaps: {enabled, label}`, with label
`groupsync-dashboard.io/config-type in (onboard,sideload)`. Its namespace, discovery time and LIST
error are the existing `secrets.namespace`, `secrets.last_discovery` and `secrets.error` shared by the
single discovery stage. `secrets.label` remains `groupsync-dashboard.io/secret-type=cluster`.

An awaiting stanza has `source: configmap:<metadata.name>:<zero-based-index>` and credential
`remote-lookup`; after lookup its source is `secret:gsd-cluster-<name>` and its credential is `bearer`.
Live cluster entries add nullable `onboarding_configmap` naming the source ConfigMap; retired rows
may omit it. No token, password, YAML body, CA bytes or connection hash is added to this API.

For wire compatibility findings retain the field `secret`: it identifies a Secret name, a qualified
`configmap:<name>:<index>` (or `configmap:<name>` for a document error), or `values` for a conflicting
values stanza. The UI labels this field “source”. New codes: `onboarding-invalid`,
`onboarding-cleanup-pending`, `onboarding-ownership-conflict`. `duplicate-cluster-name` names every
conflicting source, all suppressed; lookup refusals keep #284's codes. A failed inventory read is
`discovery-failed` and preserves the prior set. Findings never quote the supplied YAML or unknown values.

Rotate and Delete on a live generated row return `409 not-our-secret`, directing the operator to its
ConfigMap. The raw writer repeats this check so a stale tab cannot mutate a newly generated Secret.
Confirmed removal retires the row and retains history. Cleanup pending is visible even if the output
is no longer polled. `clusterConfig.secrets.writes.enabled` still gates every Secret mutation.

```

### Block 65 — `charts/group-sync-dashboard/README.md`

Document the expanded discovery/RBAC contract in the chart values table.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
| `clusterConfig.secrets.enabled` | `true` | clusters declared as labelled Secrets in the release namespace (#230, `docs/specs/SPEC_S1_cluster_secrets.md`): a Role with `get`, `list`, `watch` on `secrets` there, and the poller's discovery on the binding cadence — a Secret labelled `groupsync-dashboard.io/secret-type: cluster` carrying `name`, `server`, `config` (JSON: `bearerToken` or `oauth{username,password}`, `tlsClientConfig{caData,insecure}`) and the D2 options is polled like a `clusters[]` entry; the host is always `clusters[0]` and a Secret naming it is refused; a Secret that does not parse is a finding on `GET /api/clusterconfigs`, one that vanishes disables its cluster and keeps its history. The credential never leaves the Secret. `false` — no Role, no discovery, the `clusters[]` list alone |
```

New text:

```text
| `clusterConfig.secrets.enabled` | `true` | clusters declared as labelled Secrets in the release namespace (#230, `docs/specs/SPEC_S1_cluster_secrets.md`): a Role with `get`, `list`, `watch` on `secrets` and `configmaps` there, and the poller's discovery on the binding cadence — a Secret labelled `groupsync-dashboard.io/secret-type: cluster` carrying `name`, `server`, `config` (JSON: `bearerToken` or `oauth{username,password}`, `tlsClientConfig{caData,insecure}`) and the D2 options is polled like a `clusters[]` entry; the host is always `clusters[0]` and a Secret naming it is refused; a Secret that does not parse is a finding on `GET /api/clusterconfigs`, one that vanishes disables its cluster and keeps its history. ConfigMaps labelled `groupsync-dashboard.io/config-type: onboard` or `sideload` carry credential-free values-shaped stanzas in `data.clusters.yaml` (SPEC_S5, #293); the #284 lookup generates their Secrets. Conflicts load neither; generated credentials are pruned repeatedly after confirmed removal, behind the writes switch. See `docs/CLUSTER_STANZA.md` for the manifest and recovery rules. `false` — no Role, no discovery, the `clusters[]` list alone |
```

### Block 66 — `docs/CHANGELOG.md`

Unreleased entry records app 0.34.0 / chart 0.55.0 and the precise post-mark bind budget (Grok C8).

<!-- block: docs/CHANGELOG.md | after: ## Unreleased -->

```text

- **ConfigMap cluster onboarding (#293; SPEC_S5).** Commit credential-free `clusters:` stanzas in
  `data.clusters.yaml` on any release-namespace ConfigMap labelled
  `groupsync-dashboard.io/config-type: onboard` or `sideload`. The existing remote lookup creates
  `gsd-cluster-<name>`; ordinary Secret discovery polls it. Duplicate declarations load neither,
  generated Secrets have distinct ownership, and confirmed removals are pruned on every cycle
  until successful. Malformed/incomplete inventories never authorize deletion. ConfigMaps receive
  only namespaced `get/list/watch`; all Secret mutations keep the existing writes switch. The
  ConfigMap trigger shares #284's credential gate: after a bound failure or successful session,
  the same canonical target/account/password is not sent again in that process, including after a
  later read/write failure. TLS/connect failures before the password write may retry; a restart or
  another replica has a fresh gate until #285. `insecureSkipVerify: true` is accepted and preserved;
  ConfigMap write access in the release namespace is trusted like the fleet credential. This is
  app 0.34.0, chart 0.55.0.
```

### Block 67 — `local-development/tests/test_clusterconfig_logging.py`

Keep the failure-transition rig resource-specific.

<!-- block: local-development/tests/test_clusterconfig_logging.py | edit -->

Old text:

```python
        return list(_RaisingHost.items)
```

New text:

```python
        return [] if path.endswith("/configmaps") else list(_RaisingHost.items)
```

### Block 68 — `local-development/tests/test_clusterconfig_tab.py`

Both switch states retain an exact RBAC assertion; ConfigMaps never gain write verbs.

<!-- block: local-development/tests/test_clusterconfig_tab.py | edit -->

Old text:

```python
        assert role["rules"] == [{"apiGroups": [""], "resources": ["secrets"], "verbs": ["get", "list", "watch"]}]
```

New text:

```python
        assert role["rules"] == [{"apiGroups": [""], "resources": ["configmaps"], "verbs": ["get", "list", "watch"]},
                                 {"apiGroups": [""], "resources": ["secrets"], "verbs": ["get", "list", "watch"]}]
```

### Block 69 — `local-development/tests/test_clusterconfig_tab.py`

Both switch states retain an exact RBAC assertion; ConfigMaps never gain write verbs.

<!-- block: local-development/tests/test_clusterconfig_tab.py | edit -->

Old text:

```python
        assert role["rules"] == [{"apiGroups": [""], "resources": ["secrets"], "verbs": ["get", "list", "watch", "create", "update", "delete"]}]
```

New text:

```python
        assert role["rules"] == [{"apiGroups": [""], "resources": ["configmaps"], "verbs": ["get", "list", "watch"]},
                                 {"apiGroups": [""], "resources": ["secrets"], "verbs": ["get", "list", "watch", "create", "update", "delete"]}]
```

### Block 70 — `local-development/tests/test_ui.py`

The empty finding sentence now covers both feeds.

<!-- block: local-development/tests/test_ui.py | edit -->

Old text:

```python
        assert "never polled" in east
        assert "No malformed Secrets" in page.locator("#cc-findings").inner_text()
```

New text:

```python
        assert "never polled" in east
        assert "No configuration findings" in page.locator("#cc-findings").inner_text()
```

### Block 71 — `local-development/tests/test_ui.py`

The empty finding sentence now covers both feeds.

<!-- block: local-development/tests/test_ui.py | edit -->

Old text:

```python
        page.click("#tab-clusters"); page.wait_for_selector("#cc-findings")
        assert "No malformed Secrets" in page.locator("#cc-findings").inner_text()
```

New text:

```python
        page.click("#tab-clusters"); page.wait_for_selector("#cc-findings")
        assert "No configuration findings" in page.locator("#cc-findings").inner_text()
```

### Block 72 — `local-development/tests/test_ui.py`

Browser regression: pending source, generated provenance, controls, findings and phone width.

<!-- block: local-development/tests/test_ui.py | edit -->

Old text:

```python
    def test_the_form_offers_remote_sar_and_starts_on_the_default_pair(self, page, cc_rig):
```

New text:

```python
    def test_configmap_pending_and_generated_rows_name_the_source_and_offer_no_secret_controls(self, page, cc_rig):
        import dataclasses
        from gsd.clusterconfig.parser import Finding
        from gsd.config import ClusterConfig
        base, host, settings = cc_rig
        east, = settings.cluster_registry.discovered()
        owner = ("fleet", "cm-uid", "a" * 64)
        east = dataclasses.replace(east, onboarding=owner)
        pending = ClusterConfig("pending", "https://api.pending:6443", sa_token_lookup=True,
                                source="configmap:fleet:1", onboarding=owner)
        settings.cluster_registry.replace([east, pending], [Finding("configmap:fleet:2", "onboarding-invalid", "invalid stanza")], at="now")
        page.set_viewport_size({"width": 375, "height": 812})
        page.set_extra_http_headers({"X-Forwarded-User": "root"})
        page.goto(f"{base}/#page=clusters")
        page.wait_for_selector("#cc-cluster-pending")
        assert "ConfigMap fleet" in page.locator("#cc-cluster-pending").inner_text()
        assert "ConfigMap fleet" in page.locator("#cc-cluster-east").inner_text()
        assert page.locator("#cc-rotate-east, #cc-delete-east").count() == 0
        assert "configmap:fleet:2" in page.locator("#cc-findings").inner_text()
        assert "onboard,sideload" in page.locator("#cc-head").inner_text()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")

    def test_the_form_offers_remote_sar_and_starts_on_the_default_pair(self, page, cc_rig):
```

### Block 73 — `docs/CLUSTER_STANZA.md`

Remove the old three-path claim now that ConfigMaps are a fourth authoring path.

<!-- block: docs/CLUSTER_STANZA.md | edit -->

Old text:

```text
There are three ways to declare a cluster and they are equal paths — the values stanza below, a
labelled Secret (`docs/specs/SPEC_S1_cluster_secrets.md`), and the Cluster Configurations tab. The
same keys mean the same thing in each. This document is the values path; the differences for a
Secret are in [§6](#6-the-same-stanza-as-a-secret).
```

New text:

```text
There are four authoring paths: values, a labelled Secret, the Cluster Configurations tab, and
ConfigMap onboarding (above). The values contract follows; Secret differences are in
[§6](#6-the-same-stanza-as-a-secret). A ConfigMap calls the values parser with the additional
remote-only and no-credential boundary described above.
```

### Block 74 — `docs/polling-and-discovery.md`

The added ConfigMap section defines the third source.

<!-- block: docs/polling-and-discovery.md | edit -->

Old text:

```text
Two sources, and the difference decides how fast a change takes effect.
```

New text:

```text
One startup source and two runtime feeds; the difference decides how fast a change takes effect.
```

### Block 75 — `docs/DESIGN_cluster_connection_flows.md`

Name the new policy event in the connection-flow log vocabulary.

<!-- block: docs/DESIGN_cluster_connection_flows.md | after: # How a cluster connects — the six flows -->

```text

ConfigMap onboarding (SPEC_S5, #293) precedes the labelled-Secret flow below. A complete
release-namespace ConfigMap/Secret inventory selects credential-free declarations, then the existing
lookup generates a Secret. The generator emits `cluster-secret-updated` for policy changes and
`cluster-secret-deleted` for confirmed removal; failures are findings announced by the existing
discovery transition logger. See `docs/specs/SPEC_S5_configmap_onboarding.md` for the ownership,
conflict and retry contract.
```

### Block 76 — `local-development/tests/test_clusterconfig_tab.py`

Protected API regression for pending/generated provenance, refusals and absence of credentials.

<!-- block: local-development/tests/test_clusterconfig_tab.py | edit -->

Old text:

```python
    def test_every_write_is_the_manage_level_and_a_reader_without_it_is_refused(self, rig):
```

New text:

```python
    def test_configmap_provenance_and_findings_are_protected_and_generated_writes_refuse(self, rig):
        import dataclasses
        from gsd.clusterconfig import CONFIG_SELECTOR
        c, app, host, settings = rig
        east, = settings.cluster_registry.discovered()
        east = dataclasses.replace(east, onboarding=("fleet", "uid-1", "a" * 64))
        pending = ClusterConfig("pending", "https://api.pending", sa_token_lookup=True,
                                source="configmap:fleet:1", onboarding=("fleet", "uid-1", "b" * 64))
        settings.cluster_registry.replace([east, pending], [Finding("configmap:fleet:2", "onboarding-invalid", "invalid stanza")], at="now")
        assert c.get("/api/clusterconfigs", headers=H("alice")).status_code == 403
        payload = c.get("/api/clusterconfigs", headers=H("root")).json()
        assert payload["configmaps"]["label"] == CONFIG_SELECTOR
        rows = {r["id"]: r for r in payload["clusters"]}
        assert rows["east"]["onboarding_configmap"] == "fleet"
        assert rows["pending"]["source"] == "configmap:fleet:1"
        assert payload["findings"][0]["secret"] == "configmap:fleet:2"
        assert TOKEN not in json.dumps(payload)
        for response in (c.put("/api/clusterconfigs/east/credential", json={"token": "replacement"}, headers=H("root")),
                         c.delete("/api/clusterconfigs/east", headers=H("root"))):
            assert response.status_code == 409 and "ConfigMap" in response.json()["detail"]
        assert host.calls == []

    def test_every_write_is_the_manage_level_and_a_reader_without_it_is_refused(self, rig):
```

### Block 77 — `local-development/tests/test_docs_citations.py`

The operator requires point-in-time file:line evidence; keep a single explicit exception to the line-number rule, with no exemption from other citation checks.

<!-- block: local-development/tests/test_docs_citations.py | edit -->

Old text:

```python
        for md in _markdown()
        for n, line in enumerate(md.read_text().split("\n"), start=1)
```

New text:

```python
        for md in _markdown()
        # #293 phase 1 explicitly requires baseline file:line evidence, pinned to 35fcddb.
        # Exempt only that historical spec from this check; path/anchor checks still run on it.
        if md.relative_to(REPO).as_posix() != "docs/specs/SPEC_S5_configmap_onboarding.md"
        for n, line in enumerate(md.read_text().split("\n"), start=1)
```


### Block 78 — `docs/specs/SPEC_S4c_credential_lifecycle.md`

Move the deferred lifecycle release beyond S5 (operator, 2026-09-25).

<!-- block: docs/specs/SPEC_S4c_credential_lifecycle.md | edit -->

Old text:

```text
| Version on release | app 0.34.0, chart 0.55.0 |
```

New text:

```text
| Version on release | app 0.35.0, chart 0.56.0 |
```

### Block 79 — `docs/specs/README.md`

Keep the release cell equal to the spec header.

<!-- block: docs/specs/README.md | edit -->

Old text:

```text
| S4c | [`SPEC_S4c_credential_lifecycle.md`](SPEC_S4c_credential_lifecycle.md) — S4 step C: the credential lifecycle — the daily ping, `self-login` renewal at the fixed margin, and the per-credential gate on a fleet-account Lease, durable and replica-shared; the design of #285 | S — cluster configuration | — | app 0.34.0, chart 0.55.0 | [#285](https://github.com/ephico2real2/group-sync-dashboard/issues/285) | specified |
```

New text:

```text
| S4c | [`SPEC_S4c_credential_lifecycle.md`](SPEC_S4c_credential_lifecycle.md) — S4 step C: the credential lifecycle — the daily ping, `self-login` renewal at the fixed margin, and the per-credential gate on a fleet-account Lease, durable and replica-shared; the design of #285 | S — cluster configuration | — | app 0.35.0, chart 0.56.0 | [#285](https://github.com/ephico2real2/group-sync-dashboard/issues/285) | specified |
```

### Block 80 — `docs/specs/README.md`

Keep the release cell equal to the spec header.

<!-- block: docs/specs/README.md | edit -->

Old text:

```text
| S5 | [`SPEC_S5_configmap_onboarding.md`](SPEC_S5_configmap_onboarding.md) — ConfigMap onboarding: credential-free cluster declarations, remote lookup and owned Secret reconciliation | S — cluster configuration | — | app and chart minor bumps at the PR | [#293](https://github.com/ephico2real2/group-sync-dashboard/issues/293) | specified |
```

New text:

```text
| S5 | [`SPEC_S5_configmap_onboarding.md`](SPEC_S5_configmap_onboarding.md) — ConfigMap onboarding: credential-free cluster declarations, remote lookup and owned Secret reconciliation | S — cluster configuration | — | app 0.34.0, chart 0.55.0 | [#293](https://github.com/ephico2real2/group-sync-dashboard/issues/293) | specified |
```

### Block 81 — `local-development/tests/test_clusterconfig.py`

The existing exact API row assertion includes the additive nullable provenance field (block 37).
Phase-2 hermetic test failure identified this missing expectation; retain the full shape assertion.

<!-- block: local-development/tests/test_clusterconfig.py | edit -->

Old text:

```python
                              "status": None, "last_poll": None, "error": None, "retired": False}
```

New text:

```python
                              "status": None, "last_poll": None, "error": None, "retired": False,
                              "onboarding_configmap": None}
```
