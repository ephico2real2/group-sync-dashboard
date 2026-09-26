# SPEC L1 — Remove the OAuth Debug path (#321)

| | |
|---|---|
| Programme | Login capture retirement |
| Batch | L — login capture |
| Release | — (after #322 merges) |
| Version on release | app 0.36.0, chart 0.58.0 |
| Issue | [#321](https://github.com/ephico2real2/group-sync-dashboard/issues/321) |
| Status | released |
| Source | Codex phase-1 research and specification, 2026-09-25, baseline 9584239; supplied ../tmp/issue-321.md |

## How to read this spec

Shipped in #373 (merged 2026-09-25); the text below is the specification as it was applied. Baseline citations are repository-relative
file:line evidence at 9584239, written as plain text to distinguish them from maintained symbol
citations. The request explicitly requires point-in-time lines; no citation-test exemption is added.
The block convention and checker are docs/specs/README.md:33 and
local-development/apply-spec-blocks.py:31. L1 is free in the baseline index
(docs/specs/README.md:68). Phase 1 changes this spec, its index registration/count, and the explicitly
requested pinned index-test count only. No application or chart implementation is applied.

## Orchestrator's notes

The issue is the authority (../tmp/issue-321.md:64–77), including the four decisions settled
2026-09-25:

1. Loss of LDAP cause (including locked-account versus bad-password detail) is accepted. The
   release note states it explicitly.
2. No converge-to-Normal Job survives. The operator manually runs
   `oc patch authentications.operator.openshift.io cluster --type=merge -p '{"spec":{"logLevel":"Normal"}}'`.
   The release note and chart README give that exact command and the rollout implication.
3. Stored pod-log rows stay in the database and remain readable. No migration deletes history.
   Existing retention continues; this is not a promise to bypass the configured retention period.
4. Any supplied `authLogLevel` map, including false/empty/unknown child values, and
   `loginCapture.source: pod-log` fails Helm rendering with the migration step. Source typos remain
   refusals, even when capture is disabled. The now-unused namespace key is also refused by name.

Release order is mandatory: merge/rebase onto #322 (app 0.35.0 / chart 0.57.0), then ship this change
as app 0.36.0 / chart 0.58.0. S4c moves to app 0.37.0 / chart 0.59.0. Version blocks below are
**applied after rebasing onto #322**; current source is app 0.34.1 / chart 0.56.0
(local-development/pyproject.toml:13; charts/group-sync-dashboard/Chart.yaml:236,327).
The exact post-#322 S4c reservation is not measured; the deferred block states the anticipated
intermediate reservation and must be re-anchored if #322 leaves different text. Historical spec
bodies stay unchanged; only S4c release header/index metadata moves as explicitly requested.

The checker supports edit/create/after, but no delete operation
(local-development/apply-spec-blocks.py:31,67–106). For each whole-file removal, the exact Old text
and empty New text certify its entire contents. In phase 2, remove those certified-empty files
from the worktree as the final deletion step. These are not replacement empty modules to ship.
This is an explicit tooling limitation: this phase's check proves the removal payloads, not file
absence. The deletion list is given below. No checker extension is applied in phase 1.

Deferred version blocks use `deferred-block` markers, with exact Old/New text, because their Old
text cannot exist on this baseline. The current-tree checker does not count them. After rebasing,
change those markers to `block`, reconcile Old text against the merged #322 metadata, and rerun
all checks. A passing current-tree check must not be represented as validating those future edits.

### Review round 1

PR #373 decisions supplied by the orchestrator; review sources are ../tmp/review-ob1lite.txt
and ../tmp/review-grok.txt. These decisions amend the executable blocks against daf22e2.

| Finding | Seat | Decision | Reason |
|---|---|---|---|
| A: six deleted-symbol citations in docs/DESIGN_login_capture.md | OB1-lite | ACCEPT; four edits, Blocks 136–139 | Point live anchors at the audit reader and mark retired loop/window/guard names as historical text. |
| B: README loginCapture table floor | OB1-lite | ACCEPT; Block 140 | Removing namespace leaves eight rows; lower the floor from 9 to 8. |
| C / C8: login envelope source assertion | OB1-lite / Grok | ACCEPT; Block 141 | Top-level source is audit-log; retain nonempty stored pod-log row assertions. The baseline ledger entries below are corrected. |
| D: disabled UI card | OB1-lite | ACCEPT; Block 142 | Assert no authLogLevel switch and retain the spec.logLevel/default-verbosity explanation. |
| E / N1: login_event retention coverage | OB1-lite | ACCEPT; folded into Block 125 | Pin normal pruning, zero retention and standby behavior through the audit-only poller; the old loop test file is deleted. |
| Empty else-if clause in login-capture-rbac.yaml | Grok | ACCEPT; folded into Block 4 | Delete the retired clause and explicitly preserve a valid closing `{{- end }}`. The supplied Block 4 already included the clause in Old text; the closing structure is now part of the payload too. |
| N2: stale pod-reader comment at local-development/gsd/kube.py:72–74 | OB1-lite | ACCEPT; folded into Block 17 | Remove the comment together with POD_API_TMPL, using baseline text rather than the review's post-apply anchor. |
| C5: warning plus audit-log fallback | Grok | REJECT; keep app refusal; DEBT-ACCEPTED explicit pod-log crash-loop | a chart-driven pod can never read a pod-log ConfigMap (ConfigMaps render before Deployments, checksum/config rolls pods, no extraEnv); a fallback would 403 on a grant the old chart never made; the crash-loop needs an operator to ask for pod-log explicitly, and that is accepted. |

### Review round 2 (code, head `1178e03`, after the rebase onto #322)

OB1-lite (Opus 5.5) measured and approved; Grok read the source and gave its verdicts from that reading.

| Finding | Seat | Decision | Reason |
|---|---|---|---|
| F1(a): the only test of LOG_READ_BUDGET_SECONDS went with fetch_pod_log; fetch_node_log_file still relies on the budget | OB1-lite | ACCEPT | Restored as `test_a_read_that_outlives_its_budget_keeps_the_oldest_bytes`. Measured: it fails when the budget check is removed and passes when it is present. |
| F1(b): fetch_node_log_file's docstring said "for the same reason it does there", and "there" was the deleted reader | OB1-lite | ACCEPT | Reworded. |
| N1: a broken comment fragment in each of the three Containerfiles | OB1-lite | ACCEPT | Deleted the stray line. |
| N2: tests/test_loginlog.py cites the deleted cross-seam test file (Grok found the same) | OB1-lite, Grok | ACCEPT | The docstring now says that test was removed in #321. |
| N3: a dead `source` variable and an always-true `if` in metrics.py | OB1-lite | ACCEPT | Removed; less code. |
| F1: drop `None` from the refusal matrix | Grok | REJECT | Grok made it conditional on `authLogLevel: null` rendering. OB1-lite measured rc=1 with the removal message. The spec's matrix lists `None` deliberately, because a supplied null is still a retired key. |

These edits were applied after the blocks, so the tree differs from §6 by exactly them.

### Phase 2 verification correction

| Finding | Seat | Decision | Reason |
|---|---|---|---|
| `git diff --check`: new blank lines at EOF in mock fixtures paging.yaml:29 and reference.yaml:205 | Codex implementation verification | Fold separator removal into Blocks 51 and 55; regenerate Block 56 payload | Deleting a final fixture section left its preceding blank line. Keep the deployed ConfigMap's reference.yaml byte-identical after trimming the separator. |

Browser execution is blocked by this session's environment (Chromium Mach-port registration and
local socket binding are denied). The supplied Python lacks cryptography; network installation
fails because pypi.org cannot resolve. Cached cryptography/cffi wheels were subsequently recovered
into scratch and exposed via PYTHONPATH for the same interpreter. Environment failures are not
reasons to weaken application tests or change the specification's behavior.
Measured commands, summaries and evidence are recorded in ../tmp/phase2-report.md.

## Measured scope and design

The required first search was `git grep -n -E 'authLogLevel|auth_log_level|pod-log|pod_log|podlog'`.
The exhaustive ledger below captures its baseline lines (before this spec was added). There is no
.codegraph directory at the worktree root; CodeGraph was skipped under the supplied instruction.
No live cluster, CRC install, #322 merge tree or OpenShift rollout was measured in this phase.

| Evidence at baseline | Measurement and resulting decision |
|---|---|
| charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:1,96; auth-loglevel-revert-job.yaml:1; auth-loglevel-rbac.yaml:1 (all under the same templates directory) | Management switch controls both Jobs and their separate write identity/RBAC. Remove all three whole files; no transitional writer remains. |
| charts/group-sync-dashboard/templates/login-capture-rbac.yaml:1,59 | Audit branch grants nodes/proxy plus optional node LIST; else branch grants namespaced pods and pods/log. Delete only that else branch. Preserve audit grants, node pinning and capture-off behavior. |
| charts/group-sync-dashboard/templates/_helpers.tpl:594; charts/group-sync-dashboard/templates/configmap.yaml:170 | Helper currently accepts two sources and conditionally rejects Debug. Make audit-log the only accepted source and refuse the retired root map before checking enabled. ConfigMap always resolves the helper; no disabled-state bypass. Remove namespace output. |
| charts/group-sync-dashboard/values.yaml:1548,1641,1719; charts/group-sync-dashboard/README.md:526 | Remove authLogLevel and the unused namespace setting; document audit breadth and cause loss. Replace the verbosity section with the migration note. |
| local-development/gsd/logincapture.py:159,181,190,365 | Poller entry has capture-off gating, audit dispatch and pod read implementation; shared bounded retention is used by audit. Keep a small audit-only dispatcher and retention; delete pod fetching/window/settling code. |
| local-development/gsd/kube.py:79,103,1095,1137,1247,1398 | Remove pod URL/list/read/error helpers. Keep LOG_READ_BUDGET_SECONDS because node audit reads also use it, plus all node list/proxy/range logic. |
| local-development/gsd/config.py:481,493,1030,1669 | Direct app defaults to pod-log and invalid source silently falls back there. Default to audit-log; reject old/unknown file/environment source with ConfigError. Direct app capture stays off by default; chart capture stays on. |
| local-development/gsd/auditlog.py:44,92,318,445,590,594,625 | Audit correspondence links an existing legacy row rather than inserting a twin. Keep it: backfill after upgrading must not double-count old history. Keep audit classification, identity filters, cursor/rotation/budget, leadership rechecks and retention. |
| local-development/gsd/store.py:428,489,794,900,2933,3013,3044,3274 | No schema changes. Retain legacy source defaults/migrations, cause columns, row query, correspondence and legacy fixture insert/watermark helpers. They neither fetch pod logs nor enable Debug. |
| local-development/gsd/api.py:1823,1836,1916,1940,1964; local-development/gsd/metrics.py:462,471,478,524 | Preserve consumer field names and metric label keys; top-level live source becomes audit-log. Keep row-specific pod-log source, cause/outcome vocabulary, summary and tier scoping. Details below. |
| local-development/gsd/static/index.html:3977,4003,4052 | Live-source prose still instructs users to raise Debug. Remove it; use audit health advice and label the origin column for both live node names and stored pod names. |
| local-development/mock-app/mock_app/app.py:23,143,303,317,428; fixture.py:189,204,228,249,524,564 (same mock_app directory) | Remove both mock pod routes, server, fixture fields/classes/parsers, summary count and reload wiring. Retired fixture keys become ordinary unknown-key errors. Keep node proxy and SAR. |
| local-development/mock-app/fixtures/reference.yaml:192,214; fixtures/forbidden.yaml:38; fixtures/crd-absent.yaml:37; fixtures/paging.yaml:30; deploy/mock-fixture-configmap.yaml:99,109 (all under local-development/mock-app) | Initial grep misses camelCase fixture keys. Remove them from every bundled fixture and regenerate only the embedded fixture data in the deployed ConfigMap. |
| local-development/gsd/loginlog.py:1; local-development/gsd/kpi/definitions.py:20; local-development/tests/test_login_capture.py:18; test_visibility.py:39; test_ui.py:32 (tests under local-development/tests) | Pure legacy parser/outcome vocabulary and event_dict remain offline compatibility/fixture support. They do not retain a live reader. Stored row/API/KPI coverage depends on them; removing them would expand scope unnecessarily. |
| local-development/tests/test_chart_strategy.py:241,316,1537; test_chart_pdb.py:82; test_chart_rbac_provenance.py:34; test_values_defaults.py:22 (tests under local-development/tests) | Remove old success expectations for Debug and pod-source rendering, preserve audit tests, PDB/service isolation for the surviving mint Job, provenance coverage and default-key inventory. |
| local-development/tests/test_logincapture_loop.py:24; test_login_capture_cross_seam.py:26; test_kube_reader.py:40; local-development/mock-app/tests/test_request_surface.py:136 | Remove live pod loop/seam/HTTP tests; retain node proxy tests. Add migration/history/audit-default/mock-refusal regressions. |
| docs/LOGIN_CAPTURE_QUICKCHECK.md:1,22,375; docs/AUDIT_LOG_CAPTURE.md:146; environments/crc.yaml:66 | Current quickcheck becomes audit-only; the measured old transcript is visibly archived, not rewritten as new evidence. Remove CRC's old false-valued stanza, fix the environment table, source advice and architecture grant description. |
| local-development/tests/test_specs_index.py:50,94; docs/specs/README.md:68 | Index contains 25 rows and pins 25 in its test. Register L1 before #338, make the header say 26, update the pinned test count to 26. The original thirteen-module programme remains historical context. |

### Compatibility and wire contract

No login API field is removed or renamed. `/api/clusters/{cluster_id}/logins` retains `cluster`,
`scope`, `viewer`, `enabled`, `source`, `kinds`, `note`, `capture_started_at`, `last_read_at`,
`read_interval_seconds`, `retained_since`, `total`, `limit`, `truncated`, `summary`, `ungoverned`
and `attempts` (local-development/gsd/api.py:1916–1978). Top-level `source` is now audit-log;
`note` describes audit capture only. Summary retains distinct_users, successes, failures,
by_outcome, ungoverned_users, first_at and last_at; self-tier nulls/authorization are unchanged.

Each attempt still carries user_name, outcome, at, provider, ldap_result_code, detail, pod_name,
observed_at, source, audit_id, kind, client_id, identity_match, status_code, error_message,
user_agent, full_name, known_user, has_history, break_glass, in_access_group and refusal_reason
(local-development/gsd/store.py:3317–3332; local-development/gsd/api.py:1902–1912).
The HTTP field is `status_code`, not `response_code`. Historical `source=pod-log`, credential kind,
LDAP result/detail and original pod_name remain. New audit events have node names in pod_name,
audit ID and HTTP fields; deny cannot newly populate a LDAP cause. Correspondence can enrich an
old row while preserving its source/cause (local-development/gsd/store.py:3013–3078).
`/users` and user-detail login state/last-login fields continue to include retained history
(local-development/gsd/api.py:1718,1779; local-development/tests/test_users_tab_logins.py:36–106).

No metric family or label key is removed. `gsd_login_capture_source_info{cluster,source}` remains
an enabled-only gauge of 1; its live source label is audit-log. The previous pod-log series ceases
on the next scrape. Keep `gsd_login_capture_last_read_timestamp_seconds{cluster}` and
`gsd_login_capture_audit_settled_timestamp_seconds{cluster,node}` with their existing absence and
liveness semantics (local-development/gsd/metrics.py:462–482,519–531), as well as
`gsd_login_capture_enabled`, `gsd_login_capture_unmatched_total`, retention counters and all
login outcome/KPI consumers (local-development/gsd/metrics.py:680,706,769;
local-development/gsd/store.py:4371,4394). Old cause/outcome series remain legitimate history;
new audit rows contribute success/failed/provider_error rather than inventing LDAP diagnoses
(local-development/gsd/auditlog.py:74–78). App build/version fields move only with the deferred
version blocks (local-development/gsd/__init__.py:8; local-development/gsd/metrics.py:286).

The mock intentionally loses pod LIST/log endpoints (404), oauthPods/podLog fixture keys
(refused), and fixture_summary.oauthPods (removed). That mock-only wire break is deliberate;
node proxy, audit fixtures and the dashboard API are retained (mock app/fixture citations above).

The public `gsd_login_attempts_total{cluster,outcome,provider}` counter and internal
`login_attempts_30d`, `login_successes_30d`, `login_providers_30d` KPIs remain unchanged, including
pre-seeded outcome values and retained-row accounting
(local-development/gsd/kpi/definitions.py:24,79,177–188). The unmatched counter's labels remain
cluster/outcome; the capture-enabled gauge remains unlabelled
(local-development/gsd/metrics.py:706–712,769–776).

The dependency trace also reaches local-development/API.md:573–600, whose prose describes the
retired live reader despite not matching the initial hyphenated search. Its blocks correct the
source, backfill window and historical-only LDAP interpretation; the response fields stay intact.
The initial search measured **416 matching lines across 88 files**; the complete ledger is below.

### Verification contract

Every newly introduced test has a baseline failure: removed-key matrix sees accepted values;
render matrix sees authLogLevel in defaults; reopened-history API sees the old top-level default;
default dispatcher calls the old pod path; mock endpoints return 200; fixture keys are accepted.
The amended config/logging/PDB/UI tests assert their changed contract. Tests for unchanged stored
rows, migrations, audit correspondence, audit file reading, identity classification, authorization,
retention and metrics remain in place. These are expected red/green outcomes, **not measured test
results** in phase 1. Only the docs/tool checks requested for this phase are run here.

Phase 2 must run those regressions, existing audit/kube/storage/API/metrics/UI/mock tests and the
full suite after rebase, using a tmp-directory basetemp. Run helm lint and render default, capture
on/off, pinned/unpinned nodes, RBAC create on/off and every retired-value case. “Under any values”
is structurally enforced by deleting the templates and the pod RBAC branch; a finite render matrix
is evidence for its gates, not an exhaustive enumeration of arbitrary YAML. Finally demonstrate
one controlled real `oc login` captured via the audit log on CRC with zero auth-loglevel objects;
record identity, timestamps, API row and rendered object inventory without passwords/tokens.
That live result is **not measured** here. Restoring Normal is an operator action, not a chart hook.

## Exhaustive baseline grep ledger

| Baseline hit | Exact matching line | Disposition | Reason |
|---|---|---|---|
| README.md:197 | \| &#96;logLevel&#96; \| &#96;INFO&#96; \| &#96;DEBUG&#96; \\| &#96;INFO&#96; \\| &#96;WARNING&#96; \\| &#96;ERROR&#96; \\| &#96;CRITICAL&#96;, and nothing else. &#96;DEBUG&#96; adds this app's own reasoning — login-capture accounting per pod, poll timing, row counts, which replica holds the Lease. Not the same setting as &#96;authLogLevel&#96;; the [chart README](charts/group-sync-dashboard/README.md#dashboard-log-verbosity--loglevel) lists what is refused and why \| | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/Chart.yaml:134 | # trustedCA.existingConfigMap.enabled, ingress.enabled, authLogLevel.manage/.enabled (the audit | kept | Keep version-history comments; release fields are deferred until after #322. |
| charts/group-sync-dashboard/Chart.yaml:158 | # module setting, &#96;loginCapture.source&#96; (pod-log, the default, renders as before): &#96;audit-log&#96; | kept | Keep version-history comments; release fields are deferred until after #322. |
| charts/group-sync-dashboard/Chart.yaml:161 | # namespaced pod-log Role — read-only, cluster-wide, its breadth stated in values — and carries | kept | Keep version-history comments; release fields are deferred until after #322. |
| charts/group-sync-dashboard/Chart.yaml:163 | # ConfigMap. Refused together with &#96;authLogLevel.enabled=true&#96;: the chart will not roll the OAuth | kept | Keep version-history comments; release fields are deferred until after #322. |
| charts/group-sync-dashboard/Chart.yaml:303 | # and file, exact de-duplication by auditID, an audit event linked to its pod-log twin instead of | kept | Keep version-history comments; release fields are deferred until after #322. |
| charts/group-sync-dashboard/README.md:454 | \| &#96;loginCapture.source&#96; \| &#96;audit-log&#96; \| **&#96;audit-log&#96; (the default since chart 0.52.0)** — &#96;/var/log/oauth-server/audit.log&#96; on the control-plane nodes, read through the API server's node proxy: names the person at the DEFAULT audit verbosity, so no Debug, no OAuth roll, no login outage, and history back through the rotated files. Its cost is a **ClusterRole on &#96;get nodes/proxy&#96;**, which is read access to everything the kubelet serves over GET on those nodes, plus &#96;list nodes&#96; unless &#96;auditLog.nodeNames&#96; pins them — read-only but cluster-wide. It is nevertheless the default because the alternative shipped a feature switched on and unable to name anyone: turn it off with &#96;loginCapture.enabled: false&#96; if the grant is unacceptable. &#96;pod-log&#96; — the opt-in: a Role on &#96;pods&#96;/&#96;pods/log&#96; in &#96;loginCapture.namespace&#96;, narrower, but it names a person only at Debug (&#96;authLogLevel&#96;), which rolls the OAuth server, and its history dies with every pod. It does keep the LDAP cause, which the audit log has not. Refused together with &#96;authLogLevel.enabled=true&#96; (while &#96;loginCapture.enabled&#96;); the audit log is authoritative from the switch on and corresponding pod-log rows are linked, not doubled. How the whole path works, with a worked example: [&#96;docs/AUDIT_LOG_CAPTURE.md&#96;](../../docs/AUDIT_LOG_CAPTURE.md) \| | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/README.md:455 | \| &#96;loginCapture.namespace&#96; \| &#96;openshift-authentication&#96; \| pod-log source only: where the oauth-server pods run \| | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/README.md:462 | \| &#96;authLogLevel.manage&#96; \| &#96;false&#96; \| lets this chart own &#96;spec.logLevel&#96; on the authentication **operator** CR (&#96;authentications.operator.openshift.io/cluster&#96;) — not the OAuth CR, and not &#96;operatorLogLevel&#96;. Off by default — turning it on is what transfers ownership \| | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/README.md:463 | \| &#96;authLogLevel.enabled&#96; \| &#96;false&#96; \| with &#96;manage&#96;, sets &#96;Debug&#96; (login lines appear) or &#96;Normal&#96;. The Job runs for **both** values: Helm does not run a Job you merely stopped rendering, so a one-way enable would strand the cluster in Debug \| | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/README.md:464 | \| &#96;authLogLevel.revertOnUninstall&#96; \| &#96;true&#96; \| **leave on.** A pre-delete Job puts the level back, or removing the dashboard leaves the OAuth server naming every person who authenticates with nothing left watching \| | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/README.md:465 | \| &#96;authLogLevel.waitSeconds&#96; / &#96;.activeDeadlineSeconds&#96; / &#96;.revertDeadlineSeconds&#96; \| &#96;180&#96; / &#96;300&#96; / &#96;120&#96; \| the Job polls the Deployment's &#96;observedGeneration&#96; rather than using &#96;oc rollout status&#96;, which returned success ~30s **before** the rollout began. A wait timeout is not a failure — the patch has landed \| | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/README.md:528 | **Deprecated — the pod-log source only.** Since chart 0.52.0 login capture reads the oauth-server | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/README.md:530 | it. This machinery remains for the opt-in &#96;pod-log&#96; source and to move a cluster left at &#96;Debug&#96; | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/README.md:546 | &#96;authLogLevel.*&#96; is the prerequisite for the pod-log source, and nothing more; the audit-log default | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/README.md:569 | &#96;--set authLogLevel.*&#96; discards every other user-supplied value and reverts it to the chart default — | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/README.md:580 | helm upgrade ... -f my-values.yaml --set authLogLevel.manage=true --set authLogLevel.enabled=false | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/README.md:582 | helm upgrade ... -f my-values.yaml --set authLogLevel.manage=false | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/README.md:589 | [&#96;docs/AUDIT_LOG_CAPTURE.md&#96;](../../docs/AUDIT_LOG_CAPTURE.md). **To verify the pod-log path end to | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/README.md:916 | &#96;authLogLevel&#96; hook Job pods carry &#96;app.kubernetes.io/name&#96;, &#96;instance&#96; and &#96;component&#96; but not | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/templates/NOTES.txt:164 | needed; if authLogLevel.manage is still true with enabled=false, the Job is converging the | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/templates/_helpers.tpl:490 | {{- fail (printf "logLevel %q is not a log level. Use one of DEBUG, INFO, WARNING, ERROR, CRITICAL (case does not matter).\n\nIf you are trying to raise the OAUTH-SERVER's verbosity so the Logins tab has something to read, that is the chart's &#96;authLogLevel&#96; value, not this one — a different setting on a different object.\n\nRefused here rather than passed through, because a release value can be corrected before anything is deployed. The app itself is more forgiving with a directly supplied GSD_LOG_LEVEL — it runs at INFO and logs a warning — so this is the stricter of two boundaries, not the only one." (toString $raw)) -}} | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/templates/_helpers.tpl:594 | # pod-log \| audit-log, validated where it is resolved, and the ONE place the two switches that | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/templates/_helpers.tpl:599 | {{- $s := "pod-log" -}} | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/templates/_helpers.tpl:601 | {{- if not (has $s (list "pod-log" "audit-log")) -}} | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/templates/_helpers.tpl:602 | {{- fail (printf "loginCapture.source %q is not one of pod-log, audit-log." $s) -}} | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/templates/_helpers.tpl:604 | {{- if and (eq $s "audit-log") ($lc.enabled) ((.Values.authLogLevel \| default dict).enabled) -}} | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/templates/_helpers.tpl:605 | {{- fail "loginCapture.source=audit-log and authLogLevel.enabled=true contradict each other: the audit log names every login at the DEFAULT verbosity, so Debug on the authentication operator CR buys nothing and costs an OAuth roll. The chart will not roll the OAuth server as a side effect of a read setting. Retire Debug in order:\n  1. --set loginCapture.source=audit-log --set authLogLevel.manage=true --set authLogLevel.enabled=false   (converges the cluster to Normal; one last roll — a login outage at one replica)\n  2. --set authLogLevel.manage=false once the rollout has finished.\nPass your whole values file each time (see the chart README)." -}} | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:1 | {{- if .Values.authLogLevel.manage }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:2 | {{- if ge (int .Values.authLogLevel.waitSeconds) (int .Values.authLogLevel.activeDeadlineSeconds) }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:3 | {{- fail (printf "authLogLevel.waitSeconds (%v) must be LESS than activeDeadlineSeconds (%v).\n  As set, the deadline kills the Job mid-wait and FAILS &#96;helm upgrade&#96; — which contradicts the\n  promise in values.yaml that a wait timeout is not a failure. The wait must be able to finish\n  and print its own guidance before the deadline fires." .Values.authLogLevel.waitSeconds .Values.authLogLevel.activeDeadlineSeconds) }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:68 |   backoffLimit: {{ .Values.authLogLevel.backoffLimit }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:71 |   activeDeadlineSeconds: {{ .Values.authLogLevel.activeDeadlineSeconds }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:88 |         image: {{ .Values.authLogLevel.image.repository }}:{{ .Values.authLogLevel.image.tag }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:89 |         imagePullPolicy: {{ .Values.authLogLevel.image.pullPolicy }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:96 |           WANT={{ if .Values.authLogLevel.enabled }}Debug{{ else }}Normal{{ end }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:158 |           DEADLINE=$(( $(date +%s) + {{ .Values.authLogLevel.waitSeconds }} )) | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:159 |           echo "waiting up to {{ .Values.authLogLevel.waitSeconds }}s for --v=${WANT_V} to be live" | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:200 |           {{- if .Values.authLogLevel.enabled }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:204 |           echo "      openshift-authentication. Turn it back off with authLogLevel.enabled=false when" | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:211 |           {{- toYaml .Values.authLogLevel.resources \| nindent 10 }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-rbac.yaml:1 | {{- if .Values.authLogLevel.manage }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-rbac.yaml:11 | # &#96;authLogLevel.manage=false&#96;. | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-revert-job.yaml:1 | {{- if and .Values.authLogLevel.manage .Values.authLogLevel.revertOnUninstall }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-revert-job.yaml:29 |   activeDeadlineSeconds: {{ .Values.authLogLevel.revertDeadlineSeconds }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-revert-job.yaml:46 |         image: {{ .Values.authLogLevel.image.repository }}:{{ .Values.authLogLevel.image.tag }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-revert-job.yaml:47 |         imagePullPolicy: {{ .Values.authLogLevel.image.pullPolicy }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/auth-loglevel-revert-job.yaml:84 |           {{- toYaml .Values.authLogLevel.resources \| nindent 10 }} | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| charts/group-sync-dashboard/templates/configmap.yaml:173 |     # authLogLevel.enabled=true are refused as a contradiction. | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/templates/login-capture-rbac.yaml:10 | # the journal. Read-only, and far wider than the namespaced pods/log Role the pod-log source | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/templates/pdb.yaml:22 | cluster when the authLogLevel hook pods still carried gsd.selectorLabels; the hook pod | kept | Historical/compatibility reference, not a live OAuth Debug reader or writer; no behavior change required. |
| charts/group-sync-dashboard/templates/secrets-mint.yaml:137 |         # the authLogLevel hook; test_chart_pdb holds the selector to the Deployment's pods alone). | kept | Historical/compatibility reference, not a live OAuth Debug reader or writer; no behavior change required. |
| charts/group-sync-dashboard/values.yaml:557 | # NOT TO BE CONFUSED WITH &#96;authLogLevel&#96; BELOW, which is a different setting on a different object: | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:802 |   # authLogLevel note explains why not registry.redhat.io). Override on a cluster that mirrors | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1557 | #   pod-log (deprecated, removal tracked in #321) — a Role on &#96;pods/log&#96; in ONE namespace, | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1559 | #     strings, customer data. It NEEDS authLogLevel.enabled=true TO SEE ANYTHING — measured: | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1572 |   #   pod-log     (deprecated, #321) the oauth-server pods' logs, through a Role in | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1574 |   #               authentication operator CR (authLogLevel below), which rolls the OAuth server — | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1596 |   # &#96;enabled: true&#96; with &#96;source: pod-log&#96; while &#96;authLogLevel&#96; stayed off, so a plain install | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1606 |   # HOW IT MEETS authLogLevel: with source audit-log, Debug is unnecessary. The chart REFUSES | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1607 |   # source=audit-log together with authLogLevel.enabled=true — it will not roll the OAuth server | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1609 |   #   1. loginCapture.source=audit-log  authLogLevel.manage=true   authLogLevel.enabled=false | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1611 |   #   2. authLogLevel.manage=false once the rollout has finished. | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1612 |   # The audit log is the authoritative record from then on; pod-log rows already stored are kept, | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1615 |   # DEPRECATION: &#96;pod-log&#96; and the whole &#96;authLogLevel&#96; Job machinery are on their way out — the | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1719 | # DEPRECATED — oauth-server log verbosity  (OAuth Debug, pod-log source only) | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1723 | # the OAuth server to Debug for the deprecated pod-log source, and remains only to move a cluster | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1736 | # this section is the prerequisite for the pod-log source, and nothing more. | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1754 | # lines are obtained. This block serves only the deprecated pod-log source and the move of a cluster | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| charts/group-sync-dashboard/values.yaml:1756 | authLogLevel: | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| docs/AUDIT_LOG_CAPTURE.md:146 | the account is locked. If that distinction is needed, the pod-log source is the only place it exists. | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| docs/CHANGELOG.md:43 | - **Login capture reads the audit log by default (chart 0.52.0).** &#96;loginCapture.source&#96; moves from &#96;pod-log&#96; to &#96;audit-log&#96;. The previous pairing shipped the feature **enabled** while its source needed a verbosity the same install left **off** — &#96;authLogLevel.enabled: false&#96; — so a plain install captured no named login at all; the chart's own README measured zero occurrences of the naming line at &#96;Normal&#96;. The audit log names the person at the **default** audit verbosity, so nothing has to raise &#96;spec.logLevel&#96; on the authentication operator CR and nothing rolls the OAuth server, which at one replica is a login outage rather than a rolling update. **The cost, stated:** the grant is a ClusterRole with &#96;get&#96; on &#96;nodes/proxy&#96; plus &#96;list nodes&#96; — read-only, but read access to everything the kubelet serves over GET on the control-plane nodes, including other containers' logs, the apiserver audit logs and the journal. Narrow it in production with &#96;loginCapture.auditLog.nodeNames&#96;, which pins &#96;resourceNames&#96; and drops the &#96;list&#96; entirely; turn the feature off with &#96;loginCapture.enabled: false&#96; if the grant is unacceptable. &#96;pod-log&#96; remains selectable and is deprecated along with the &#96;authLogLevel&#96; Job machinery; their removal is tracked in #321. | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| docs/CHANGELOG.md:263 |   default audit verbosity, so the &#96;authLogLevel&#96; Jobs and the OAuth roll they cause can be | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| docs/CHANGELOG.md:268 |   carries its &#96;auditID&#96;, so de-duplication is exact; an event that corresponds to a pod-log row | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| docs/CHANGELOG.md:288 |   &#96;list nodes&#96;, or &#96;resourceNames&#96;) renders instead of the namespaced pod-log Role — read-only, | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| docs/CHANGELOG.md:290 |   &#96;source=audit-log&#96; with &#96;authLogLevel.enabled=true&#96; is refused: the chart will not roll the | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| docs/CHANGELOG.md:371 |   &#96;trustedCA.existingConfigMap.enabled&#96;, &#96;ingress.enabled&#96;, &#96;authLogLevel.manage&#96;/&#96;.enabled&#96; — the | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| docs/CHANGELOG.md:382 |   on-by-default budget on the reference cluster: the &#96;authLogLevel&#96; Job pods matched the | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| docs/DESIGN_decouple_chart_and_app_release.md:578 | &gt;     # Match the dashboard container only: oauth-proxy and authLogLevel jobs carry other images, | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_login_capture.md:19 | \| log reader \| &#96;gsd/kube.py#ClusterClient.fetch_pod_log&#96; \| streamed, byte-bounded and wall-clock-bounded read of one pod's log \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_login_capture.md:32 | \| &#96;gsd/kube.py#LOG_READ_BUDGET_SECONDS&#96; \| 20 \| wall-clock bound on one pod-log read \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_login_capture.md:34 | The prerequisite is &#96;authLogLevel&#96;, which raises &#96;spec.logLevel&#96; on the authentication **operator** CR | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_login_capture.md:270 | pod-log source's. The audit source backfills to the oldest rotated file on first read, bounded by | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_login_capture.md:279 | &#96;gsd/auditlog.py#capture_once&#96;, and the link to pod-log rows is | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_login_capture.md:323 | audit credential event that corresponds to a pod-log row for the same user and success class within | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_metrics_refresh.md:62 | Today their only signals are pod-log lines — verified live: the last 48 h of the dashboard | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_mock_cluster.md:14 | &#96;kube.py&#96; issues** — the ~16 read endpoints, the two node-log-proxy shapes, the pod-log | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_mock_cluster.md:77 |     caBundleFile)   │   • router → list / get / sar / nodelog / podlog│ | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_mock_cluster.md:119 | \| m \| &#96;/api/v1/namespaces/&lt;ns&gt;/pods/&lt;pod&gt;/log&#96; \| &#96;fetch_pod_log()&#96; \| **stream, TEXT** \| &#96;client.stream&#96;; params &#96;timestamps=true&#96; (+&#96;sinceSeconds&#96;). Body = lines each prefixed with an **RFC3339 UTC** timestamp + space. &#96;&gt;=400&#96; → parsed as k8s &#96;Status&#96; JSON (&#96;.reason&#96;, &#96;.message&#96;). \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_mock_cluster.md:413 | Two node-proxy shapes (endpoints n, o), plus the pod-log stream (m). All verified against | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_mock_cluster.md:572 | │   ├── podlog.py                 # pod-log text stream builder (§7.3) | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_mock_cluster.md:627 |     audit: AuditFixture; pod_log: PodLogFixture | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_mock_cluster.md:670 |     # attaches: self.server.fixture, .sar, .audit, .podlog, .inspect, .reqlog | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/DESIGN_remote_cluster_access.md:100 |   &lt;img alt="remote-sar today: a cached verdict, or list the reader's groups on the remote and create a SubjectAccessReview there with the joining token; allowed gives the wide view and denied gives self, both cached; a 401, 403 or unreachable answer at either remote call gives self, not cached, with a pod-log warning and the tier-check metric; any other exception gives self, not cached, with an ERROR and the metric outcome error" src="diagrams/remote-cluster-access/remote-sar-decision-flow.light.png"&gt; | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/LOGIN_CAPTURE_QUICKCHECK.md:8 | Use this after enabling &#96;authLogLevel&#96; / &#96;loginCapture&#96;, or when the dashboard shows no login activity | kept | Edit current instructions to audit-only; keep old measured transcript under an explicit retired-history warning. |
| docs/LOGIN_CAPTURE_QUICKCHECK.md:31 |   --set authLogLevel.manage=true --set authLogLevel.enabled=true | kept | Edit current instructions to audit-only; keep old measured transcript under an explicit retired-history warning. |
| docs/LOGIN_CAPTURE_QUICKCHECK.md:37 | &gt; **Pass your whole value set.** &#96;helm upgrade&#96; with only &#96;--set authLogLevel.*&#96; discards every other | kept | Edit current instructions to audit-only; keep old measured transcript under an explicit retired-history warning. |
| docs/LOGIN_CAPTURE_QUICKCHECK.md:207 |   --set authLogLevel.manage=true --set authLogLevel.enabled=false | kept | Edit current instructions to audit-only; keep old measured transcript under an explicit retired-history warning. |
| docs/LOGIN_CAPTURE_QUICKCHECK.md:366 | \| the level flipped back on its own \| somebody ran &#96;helm upgrade&#96; without &#96;-f&#96;, reverting &#96;authLogLevel.enabled&#96; to the chart default \| | kept | Edit current instructions to audit-only; keep old measured transcript under an explicit retired-history warning. |
| docs/LOGIN_CAPTURE_QUICKCHECK.md:399 | oc auth can-i list pods -n openshift-authentication --as=$SA  # no: the pod-log Role is not rendered | kept | Edit current instructions to audit-only; keep old measured transcript under an explicit retired-history warning. |
| docs/OAUTH_LOGLEVEL_REVIEW.md:176 | - **Test that would catch a regression** (in &#96;TestTheOauthLogLevelJobKeepsTheWriteOffTheDashboard&#96;, | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/OAUTH_LOGLEVEL_REVIEW.md:851 | - **REMEDIATION**: add to &#96;TestTheOauthLogLevelJobKeepsTheWriteOffTheDashboard&#96; (after &#96;test_the_jobs_write_is_pinned_to_one_named_object&#96;): | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_D1.md:12 | audit-log&#96; and &#96;authLogLevel.enabled: false&#96; (manager left on). The first crashed on open — | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_D1.md:23 | \| pod-log rows linked to their audit twin \| 110 of 129, at a 0.25 s window \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_D1.md:25 | \| two fresh &#96;oc login&#96; attempts (wrong then right password, developer) \| both rows within two minutes: &#96;cli failed 401 "Authentication failed, attempted: basic"&#96; and &#96;cli success 302&#96;, provider &#96;developer&#96; resolved through the User's Identity — the break-glass label the pod-log source could never give a CLI login \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_D1.md:28 | \| RBAC \| &#96;oc auth can-i get nodes --subresource=proxy --as=&lt;SA&gt;&#96; yes; &#96;list pods -n openshift-authentication&#96; no; no pod-log Role rendered \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_D1.md:49 | unqualified "refused together with &#96;authLogLevel.enabled=true&#96;" are corrected. Its one accepted | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_D1.md:80 | \| C6 correspondence \| REFUTED — a credential retry 1 s after a pod-log row of the same class was linked to it instead of inserted \| **Accepted in part** — &#96;CORRESPONDENCE_SECONDS&#96; is 0.25 (fifteen times the measured 16 ms pairing) and Cursor's test is taken. The "swallowed retry" framing is rejected on the data: the swallow needs the first attempt's own audit twin to be absent (events are processed in file order, and the twin links first), and the closest same-user credential retry in the cluster's 49,360-record log is 3.6 s apart (133 pairs, none under 2 s). Its second point — two audit rows with an identical microsecond stamp collide on the table's UNIQUE key — is **rejected**: zero same-user same-stamp pairs in the log, and the stamps are microseconds \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_D1.md:92 | &#96;authLogLevel.enabled=true&#96; even with &#96;loginCapture.enabled=false&#96;, when no RBAC renders and no log | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_D1.md:114 | \| C6 \| REFUTED — two audit IDs for one person, node, microsecond and outcome collapse on the table's UNIQUE key; proposed rebuilding &#96;login_event&#96; in migration 10 with a partial pod-log-only index \| **Rejected as a rebuild, accepted as a visible event** — zero same-user same-stamp pairs in the cluster's 49,360 records, and rebuilding the table that holds every install's login history for a collision never observed is more upgrade risk than the defect. The ignored row is logged at WARNING with its auditID (no username), with a test \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_chart_defaults.md:40 | &#96;DisruptionAllowed=False&#96;, &#96;disruptionsAllowed 0&#96;, &#96;expectedPods 0&#96;. The &#96;authLogLevel&#96; hook Job pods | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_chart_defaults.md:86 | does not exist — Codex) and &#96;authLogLevel.manage&#96;, one now the default and the other the setting the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_chart_defaults.md:90 | &#96;authLogLevel.manage&#96;"; Codex's says to inspect the deployed values. Until D1 ships, the Debug level is | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_group_search.md:653 | A third review pass over &#96;parse()&#96; and &#96;fetch_pod_log&#96; in the login-capture module. Fable's replacements | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_log_level_contract.md:54 |     TraceAll and this chart carries &#96;authLogLevel&#96; for that distinct setting. Debug is the only word | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_log_level_contract.md:66 |         "objects and is set through the chart's authLogLevel, not logLevel; only Debug means the " | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_log_level_contract.md:160 | {{- fail "logLevel is not a log level for THIS chart. Use one of DEBUG, INFO, WARNING, ERROR, CRITICAL (case does not matter).\n\nIf you were reaching for OpenShift's vocabulary — Normal, Debug, Trace, TraceAll — that belongs to operator.openshift.io resources and means something different. This value configures the dashboard's own Python logging, while authLogLevel manages spec.logLevel on authentications.operator.openshift.io/cluster. Debug is the one word valid in both.\n\nA direct GSD_LOG_LEVEL deployment degrades an unrecognised value to INFO and warns. This chart is stricter because a release value is known before rollout: refusing the render prevents a typo from silently deploying at a level the operator did not request." -}} | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_log_level_contract.md:535 | \| &#96;logLevel&#96; \| &#96;INFO&#96; \| &#96;DEBUG&#96; adds this app's own reasoning: login-capture accounting per pod, poll timing, fetched-object summaries, and which replica holds the Lease. **Not** HTTP request lines — httpx logs those at &#96;INFO&#96; already. Not the same value as &#96;authLogLevel&#96; \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:211 | - **K1** &#96;fetch_pod_log&#96; streams and is byte-bounded, so a large log cannot be buffered whole. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:232 | - **Do not touch &#96;authLogLevel&#96;**, the oauth-proxy, or the SQLite engine choice. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:726 | &gt; &#96;fetch_pod_log&#96; (caught &#96;ClusterError&#96;), pure &#96;parse/_settle_horizon/event_dict&#96;, then store writes. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:821 | &gt;             lines = client.fetch_pod_log(ns, pod, since_seconds=since) | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:953 | &gt; **Codex:** CONFIRMED — **K1** — &#96;kube.py:623-684#fetch_pod_log&#96; uses &#96;client.stream&#96; and caps the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:957 | &gt; **Codex:** NEW — high — &#96;kube.py:636-640,660-677#fetch_pod_log&#96;. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:969 | &gt; def fetch_pod_log(self, namespace: str, pod_name: str, | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:1055 | &gt;     got = client.fetch_pod_log("ns", "pod", max_bytes=20) | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:1257 | \| &#96;kube.py#fetch_pod_log&#96; — the byte cap keeps the OLDEST lines \| NEW \| high \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:1283 | - **The &#96;fetch_pod_log&#96; fix must not buffer the whole log.** Keeping the NEWEST lines under a byte cap | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:1337 | &gt; fetch_pod_log byte cap (bytes kept):  repo 31 of a 20-byte cap (chars counted) \| codex 20 \| fable &lt;=20 | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:1338 | &gt; fetch_pod_log cap direction:          repo keeps OLDEST but logs "newest lines are kept" \| codex keeps newest | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:2134 | &gt;             lines = client.fetch_pod_log(ns, pod, since_seconds=since) | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:2274 | &gt; &#96;local-development/gsd/kube.py#ClusterClient.fetch_pod_log&#96; (the comment lies; the submitted | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:2311 | &gt;     def fetch_pod_log( | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:2433 | &gt;     got = client.fetch_pod_log("ns", "pod", max_bytes=20) | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:2446 | &gt;         got = client.fetch_pod_log("ns", "pod", max_bytes=20) | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:2457 | &gt;     got = client.fetch_pod_log("ns", "pod", max_bytes=30) | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:2515 | &gt; &#96;#ClusterClient.fetch_pod_log&#96; have no test home: NOTHING under &#96;tests/&#96; imports either (verified | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:2519 | &gt; &#96;tests/test_kube_reader.py&#96; holding the three &#96;fetch_pod_log&#96; tests and the two | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:2567 | &gt; contract), and the &#96;fetch_pod_log&#96; tail-retention erases displaced log history permanently (the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:2572 | &gt; &#96;capture_once&#96;/&#96;_settle_horizon&#96;/&#96;_recordable&#96;, &#96;fetch_pod_log&#96;, the five loop-test rewrites, the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_pr12.md:2618 | **Codex's &#96;fetch_pod_log&#96; rolling tail (finding 9).** The defect is real: the code keeps the OLDEST | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_seams.md:141 | **Claim.** gsd/logincapture.py:capture_once — stamping datetime.now(UTC) after fetch_pod_log returns (line 231) bounds the kubelet's true window boundary from above, which is the safe direction for the duplicate defect. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_seams.md:160 | # module constants, and replace fetch_pod_log with the version below. This closes the loss at | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_seams.md:165 | # One pod-log read's wall-clock budget. The httpx timeout on _client caps the SILENCE between | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_seams.md:176 | def fetch_pod_log( | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_seams.md:314 |         got = client.fetch_pod_log("ns", "pod") | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_seams.md:331 | **Reviewer's summary.** Measured in the worktree (gsd resolves to wt-crossseam, suite 1069 passed / 1 skipped): the two fixes hold for their stated targets, but the same two defect classes — one login stored as two rows, and a stored row asserting something false about a named person — survive through four other doors in the same seam, each reproduced with a script against the real parse()/capture_once()/fetch_pod_log()/Store objects. (1) parse() expires a pending attempt on age-since-FIRST-line, so any login whose lines span more than ATTEMPT_WINDOW=1s (slow directory bind, 3-provider chain) is concluded twice — measured as a fabricated ('jane.smith','failed') row beside the real ('jane.smith','success'), mid-log where neither _recordable nor _not_clipped can see it. (2) The 8 MiB byte cap in fetch_pod_log is a third read seam with no guard: an attempt straddling the cap parses half in cycle 1 and whole in cycle 2 — measured end-to-end through the real cap logic and real SQLite store as ('jane.smith','failed') + ('jane.smith','success') for one successful login. (3) adopt() hands unidentified orphan causes out in arrival order: with two waiting bind errors and verdicts returning in the other order, the codes CROSS — measured bob recorded bad_password with alice's code 49 and alice recorded password_expired with bob's 53. (4) found{} keeps ONE entry per DN, so two logins resolving the same directory entry inside a window trade evidence, and the blind bind_code overwrite then records one named person's expired password (AD data 532) as a wrong one (data 52e) — measured. All four replacement fixes were applied to a scratch copy and validated: the 5 new regression tests fail on the worktree code and pass on the fixed copy; all 124 seam tests and the full suite pass on the fixed copy (1247 passed; the only 2 failures are tests/test_docs_citations.py rglobbing parents[2] of the scratch location and tripping on unrelated scratchpad *.md artifacts — environmental). Probed and found clean: _cause_mentions_user's boundaries (bob/bobby, dotted suffix, group-name-as-username, '='/',' in usernames — no wrong-person match; an escaped-comma DN loses its cause, which is the documented absent-beats-false trade), and provider-outside-the-UNIQUE-key (measured INSERT 1 then 0, first writer wins; after the two fixes the only same-(user,at,outcome) pair one pod can produce is a re-read of the same fully-parsed attempt, where parse is deterministic, so the collapse is safe). Also verified the idle-expiry replacement does not weaken the shipped guards: a chained attempt clipped at the leading edge still dies in _not_clipped (measured, survives=[]), because any unseen line of one attempt is within ATTEMPT_WINDOW of a visible one. Artifacts: /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/325dfd2f-469e-4bd4-b279-331704911184/scratchpad/attack{1,2,3,5}*.py and scratchpad/fixcheck/ (validated fixed copy + tests). | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_seams.md:592 | **Claim.** local-development/gsd/kube.py:fetch_pod_log() — the byte cap (line 737, &#96;if len(chunk) &gt;= room&#96;) is a THIRD read seam with no guard: an attempt straddling the cap byte is returned half (its head), parsed to a false conclusion, recorded, and then recorded AGAIN whole when the next cycle's overlap re-reads it. _recordable cannot see it (a capped backlog's attempts are minutes old) and _not_clipped cannot (they are nowhere near the leading edge). Distinct from the known-agreed exact-cap final-line drop. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_seams.md:601 | # New module-level constant + helper (place above &#96;class ClusterClient&#96;), and fetch_pod_log's | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_seams.md:652 | # Complete replacement for ClusterClient.fetch_pod_log — the only change from the shipped version | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_seams.md:654 |     def fetch_pod_log( | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_seams.md:791 |     got = client.fetch_pod_log("ns", "pod", max_bytes=cap) | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_login_capture_seams.md:803 |     got = client.fetch_pod_log("ns", "pod", max_bytes=cap) | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_rbacauditors_default_and_authloglevel.md:1 | # Review — PR #121 (rbacAuditors ON by default) + PR #122 (crc authLogLevel off) | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_rbacauditors_default_and_authloglevel.md:18 | \| C4 crc authLogLevel management off is safe and complete \| CONFIRMED \| CONFIRMED \| — (the Job/hook is fully gated by &#96;manage&#96;; the operator CR is at Normal, so nothing is stranded) \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_rbacauditors_default_and_authloglevel.md:56 | The code was correct on both PRs; #122 (authLogLevel off) was CONFIRMED clean by both reviewers. The one | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_remote_sar_for_every_join.md:413 | - **K2, REFUTED, accepted:** four walk rows quoted pod-log lines that were not saved in the walk folder. Steps 3, 7 | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_tier_constants_and_settling_name.md:402 | &gt;             lines = client.fetch_pod_log(ns, pod, since_seconds=since) | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/REVIEW_tier_constants_and_settling_name.md:464 | &gt;                       "written (chart value authLogLevel, NOT logLevel; see " | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/SPEC_per_user_visibility.md:3861 |         &lt;code&gt;loginCapture.enabled&lt;/code&gt; and &lt;code&gt;authLogLevel.manage&lt;/code&gt;. See | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/diagrams/remote-cluster-access/source.html:236 |         &lt;svg viewBox="0 0 980 490" role="img" aria-label="remote-sar today: a cached verdict, or list the reader's groups on the remote and create a SubjectAccessReview there with the joining token. Allowed gives the wide view and denied gives self, both cached. A 401, 403 or unreachable answer at either remote call gives self, not cached, with a pod-log warning and the tier-check metric; any other exception gives self, not cached, with an ERROR and the metric outcome error. A failure holds the cluster's resolver for 30 s; the line beside the selector (D5) names the rule; the named finding is proposal D4."&gt; | kept | Refers to the dashboard application log, not the retired OAuth login source. |
| docs/diagrams/remote-cluster-access/source.html:263 |             &lt;text x="332" y="203"&gt;pod-log warning + tier-check metric · a 403 is fixed by: list groups&lt;/text&gt; | kept | Refers to the dashboard application log, not the retired OAuth login source. |
| docs/handoff/macbook-migration-plan.md:770 |   &#96;FailedScheduling: Insufficient cpu&#96;) — this is why &#96;authLogLevel.manage&#96; is &#96;false&#96; in &#96;crc.yaml&#96; (the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/reference-architecture.md:810 | &#96;authLogLevel.manage=true&#96;: | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| docs/session-changelogs/2026-09-15_release-020-mock-and-auditor-incident.md:74 | - **#122 (crc, authLogLevel off):** the CRC env forced &#96;authLogLevel.manage: true&#96;, whose Job (a | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/session-changelogs/2026-09-15_release-020-mock-and-auditor-incident.md:75 |   post-upgrade HOOK for the pod-log login source) ran on every upgrade and, on the CPU-saturated node, | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/session-changelogs/2026-09-23_nsaudit-reports-and-remote-sar.md:38 |   &#96;pod-log&#96; to &#96;audit-log&#96;, chart 0.51.0 → 0.52.0. Its message records an end-to-end run on the reference cluster: | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/session-changelogs/2026-09-23_nsaudit-reports-and-remote-sar.md:45 | - In the session: &#96;f1b6010&#96; (04:25) marks the chart's pod-log text and &#96;authLogLevel&#96; deprecated, reduces the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/session-changelogs/2026-09-23_nsaudit-reports-and-remote-sar.md:46 |   README's verbosity section to pod-log only, and corrects the 0.14.0 rationale's "scoped to one namespace" claim. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/session-changelogs/2026-09-23_nsaudit-reports-and-remote-sar.md:47 |   &#96;21172d5&#96; (04:43) opens the &#96;authLogLevel&#96; stanza with a DEPRECATED banner. Both touch comments and docs only. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/session-changelogs/2026-09-23_nsaudit-reports-and-remote-sar.md:49 | - #321 opened at 04:16 to remove the Debug path: the three &#96;auth-loglevel-*&#96; templates, the pod-log reader and its | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/session-changelogs/2026-09-23_nsaudit-reports-and-remote-sar.md:681 |   - C1 and C2 **REFUTED**, both **accepted**: three more pod-log assumptions, and a stalled note that overstated | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/session-changelogs/2026-09-23_nsaudit-reports-and-remote-sar.md:704 | - **#346, measured:** the audit-log wording is on the deployed page, and the pod-log sentence is gone. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/session-changelogs/2026-09-24_ob1-312-close-out-and-353.md:49 |   deletion (21:42:49). **Accepted:** &#96;walk/pod-log-excerpt.sh&#96; and its &#96;.out&#96; capture the pod's refresh and finding | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/session-changelogs/2026-09-24_ob1-312-close-out-and-353.md:53 |   **Accepted on the fact; Codex's softened wording rejected** — the pod-log excerpt turns the sentence into a quote, | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/README.md:131 | &#96;oauthProxy.apiTokenAccess.enabled&#96;. Eight switches (nine keys, &#96;authLogLevel&#96; being two) stay off, | kept | Keep historical defaults narrative; add L1 index/count now; defer S4c release reservation update. |
| docs/specs/README.md:134 | (exclusive with the Route the chart refuses to render alongside), &#96;authLogLevel.manage&#96;/&#96;.enabled&#96; | kept | Keep historical defaults narrative; add L1 index/count now; defer S4c release reservation update. |
| docs/specs/SPEC_B1_offsite_backup.md:64 | \| The chart's Job precedent uses an operator-supplied image for a CLI the dashboard image lacks \| &#96;charts/group-sync-dashboard/templates/auth-loglevel-job.yaml#authLogLevel.image&#96; \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_B1_offsite_backup.md:162 | 3. *Chart precedent.* &#96;authLogLevel&#96; already runs an operator-supplied image for &#96;oc&#96; (&#96;charts/group-sync-dashboard/templates/auth-loglevel-job.yaml#authLogLevel.image&#96;). | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_B2_history_retention.md:76 | \| The chart's Job precedent uses an operator-supplied image for a CLI the dashboard image lacks \| &#96;charts/group-sync-dashboard/templates/auth-loglevel-job.yaml#authLogLevel.image&#96; \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:32 | - Applied at implementation (PR for #66), 2026-09-06, from the body's blocks as amended by the grounding note above. Deviations, each with the reason: (1) **file identity is a head fingerprint, not the size.** Measured on the reference cluster (audit.log of 27,804,760 bytes): &#96;Range: bytes=&lt;size&gt;-&#96; — the idle case, nothing new since the last read — answers &#96;416&#96; with &#96;Content-Range: bytes */&lt;size&gt;&#96;, exactly as a Range past the end does, and &#96;HEAD&#96; answers &#96;405&#96;. The body's reader took every 416 as rotation, which would have reset audit.log's cursor on every idle cycle; and its loop visited a fresh rotated file (sorted before &#96;audit.log&#96;) before noticing the rotation, so the hand-over never fired and the rotated file was re-read from byte 0 — while the size alone cannot tell the file that was read from a new &#96;audit.log&#96; that has already grown past the cursor (a resume would start mid-line in the new file and lose its first bytes). As built: &#96;kube.py#fetch_node_log_file&#96; decides a 416 by the size in &#96;Content-Range&#96; (equal to the cursor is "nothing new", below it is &#96;rotated&#96;; absent, one unranged read settles it the 200 way); each cursor row carries &#96;head_sha256&#96;/&#96;head_len&#96;, the sha256 of the file's first &#96;min(1024, bytes consumed)&#96; bytes (&#96;auditlog.py#FINGERPRINT_BYTES&#96;, at least one whole line with its unique &#96;auditID&#96; — Filebeat's &#96;file_identity.fingerprint&#96;), re-read and compared before every resume; &#96;audit.log&#96; is visited first once it has a cursor, and &#96;auditlog.py#_hand_over&#96; moves the cursor and fingerprint to the newest cursor-less rotated file only after that file's head matches, updating the in-cycle view so the rotated file resumes from the handed-over offset in the same cycle. One extra ~1 KiB request per in-progress file per cycle; complete rotated files pay nothing. Tests: &#96;test_kube_reader.py::TestNodeLogRangeReads&#96; (the measured 416 forms), &#96;test_auditlog.py&#96; rotation past the cursor, the idle cycle, a rotated file whose head changed. (2) The fixtures in &#96;tests/test_auditlog.py&#96; are the eleven measured records the grounding note counted, anonymised (&#96;userN.example&#96;) and otherwise byte-identical, one keeping the &#96;crc &#96; node-name prefix &#96;oc adm node-logs --role&#96; writes; the batch test that reads them runs with &#96;loginRetentionDays: 0&#96; because the cluster's records are older than the 400-day default — two of the eleven were inside it and nine were, correctly, aged out. (3) The kinds, the identity classification (&#96;identity_match&#96;, &#96;loginCapture.auditLog.providers&#96;, &#96;ignoreIdentityPatterns&#96;), the absence of coalescing, the &#96;gsd_login_capture_unmatched_total{cluster,outcome}&#96; counter and the &#96;kind&#96; query parameter are the grounding note's, not the body's; the body's coalescing paragraph in the design doc is replaced by the note's rule. (4) Schema migration 10, and the design doc heading names application 0.17.0; the body's 0.13.0 / 0.12.0 pairs and its CHANGELOG heading are superseded by the ladder and by the heading &#96;prepare-release.py&#96; writes. (5) The chart README's &#96;htpasswdProviders&#96; row says a CLI &#96;kubeadmin&#96; login IS labelled break-glass (the provider resolves through the User's Identity) where the body said it is not; the values comment says the same. (6) &#96;docs/LOGIN_CAPTURE_QUICKCHECK.md&#96; §6 states the measured answer, &#96;206&#96;, for the ranged read, and the Node column replaces Replica on the Logins tab only when the envelope's &#96;source&#96; is &#96;audit-log&#96;. (7) &#96;ClusterError&#96; is not imported by the test module (unused in the body's tests). (8) The audit &#96;detail&#96; names the request path as the target for credential logins (&#96;via /login/&lt;idp&gt;&#96;), the client for CLI and session ones. (9) From the adversarial review (&#96;docs/REVIEW_D1.md&#96;, Cursor pass 1): the &#96;login_event_by_audit_id&#96; index is created by migration 10 only — in &#96;SCHEMA&#96; it ran before &#96;_migrate&#96; and aborted the open of every pre-0.17.0 database (the reference cluster's pod crashed on it); the three audit lists reach the ConfigMap as JSON and &#96;_string_list_setting&#96; never splits a list; &#96;CORRESPONDENCE_SECONDS&#96; is 0.25; an authorize request without a &#96;client_id&#96; is not a row; a fingerprint probe does not set &#96;read_ok&#96;; a rotated file's newline-less last line is taken as its final line; the unmatched counter's label is &#96;outcome&#96;; the Debug contradiction is only checked with capture on; an unreadable OAuth CR is logged at WARNING. (10) From Codex's pass of the same review and the second live run: both node-log reads send &#96;Accept: */*&#96; — the API server's proxy answered 406 to the client's default &#96;application/json&#96; (measured), so the second deploy read nothing; &#96;/login/&lt;idp&gt;&#96; is exactly one path segment; the re-read after a fingerprint mismatch counts as a read; &#96;_configured_providers&#96; distinguishes an unreadable OAuth CR (None: any provider, said at WARNING) from one that lists none (empty set: nothing matches); identities of &#96;loginCapture.htpasswdProviders&#96; are never base64-decoded; an audit row the pod-log UNIQUE key ignores is logged with its auditID rather than rebuilt around (zero same-stamp pairs measured); the NOTES no longer say &#96;0 days at most&#96; for an unlimited retention. (11) Cursor's second pass (&#96;docs/REVIEW_D1.md&#96;): all ten claims confirmed; its residual test gaps and stale wording are closed as listed there — among them the migration test now also opens v5 and v8 databases, and the README's &#96;loginCapture.*&#96; cells are held to values.yaml by &#96;tests/test_values_defaults.py&#96;. (12) Codex's second pass: &#96;read_ok&#96; is set only by a resume that carried a body — a "rotated" answer (no body) followed by a failed re-read from 0 had advanced last_read_at on a cycle that read nothing. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:44 | **The capture pipeline as built.** &#96;gsd/kube.py#ClusterClient.fetch_oauth_pods&#96; and &#96;gsd/kube.py#ClusterClient.fetch_pod_log&#96; read pod logs (streamed, byte- and wall-clock-bounded by &#96;gsd/kube.py#LOG_READ_BUDGET_SECONDS&#96;); &#96;gsd/loginlog.py#parse&#96; correlates klog lines into &#96;LoginAttempt&#96;; &#96;gsd/logincapture.py#capture_once&#96; owns the per-pod watermark, the settle horizon (&#96;gsd/logincapture.py#_settle_horizon&#96;), the leading-edge guard (&#96;gsd/logincapture.py#_not_clipped&#96;) and the leadership recheck; &#96;gsd/logincapture.py#event_dict&#96; fixes the row shape and stamp format; &#96;gsd/store.py#Store.record_login_events&#96; inserts against &#96;UNIQUE(cluster_id, pod_name, user_name, at, outcome)&#96;; &#96;gsd/store.py#Store.prune_login_events&#96; is bounded; &#96;gsd/store.py#Store.record_login_read&#96; is the liveness record that &#96;gsd/metrics.py#DashboardCollector._gather&#96; exports as &#96;gsd_login_capture_last_read_timestamp_seconds{cluster}&#96;, and &#96;templates/monitoring.yaml#GroupSyncDashboardLoginCaptureStalled&#96; alerts on it joined &#96;on()&#96; to the unlabelled &#96;gsd_login_capture_enabled&#96;. The poller calls &#96;capture_once&#96; once per cycle after &#96;poll_once&#96; (&#96;gsd/poller.py#_run_cluster&#96;), so a second source must be a dispatch inside &#96;capture_once&#96;, not a second thread. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:46 | **The switches as built.** &#96;loginCapture.enabled&#96; renders a namespaced Role (&#96;templates/login-capture-rbac.yaml&#96;) and the ConfigMap key &#96;loginCaptureEnabled&#96; (&#96;templates/configmap.yaml#loginCaptureEnabled&#96;, the key that was once unwired). &#96;authLogLevel.manage&#96;/&#96;.enabled&#96; render two hook Jobs on a separate ServiceAccount (&#96;templates/auth-loglevel-job.yaml&#96;, &#96;templates/auth-loglevel-rbac.yaml&#96;, &#96;templates/auth-loglevel-revert-job.yaml&#96;); the values comment is explicit that a toggle "ROLLS THE OAUTH SERVER, WHICH IS A LOGIN OUTAGE ON A SINGLE-REPLICA CLUSTER", and the chart README says turning it off is two steps in order (&#96;enabled=false&#96; then &#96;manage=false&#96;). &#96;tests/test_chart_strategy.py::TestLoginCaptureReadsOneNamespaceOnly&#96; asserts no ClusterRole ever grants &#96;pods&#96;/&#96;pods/log&#96; — the audit-log grant must be a *different* resource so that test keeps holding. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:73 | Consequences carried into the design: (1) the oauth-server audit log names no identity provider except in the browser path's &#96;/login/&lt;idp&gt;&#96; URI, so &#96;provider&#96; is nullable on audit rows and the break-glass classification (&#96;gsd/api.py#list_logins&#96;, &#96;break_glass = provider in htpasswd&#96;) cannot fire for a CLI &#96;kubeadmin&#96; login — stated as a limitation, not hidden; (2) &#96;deny&#96; carries no cause, so the LDAP result codes and AD sub-codes stay pod-log-only, exactly as &#96;docs/DESIGN_login_capture.md#It also carries no cause&#96; says; (3) the audit source is **off** when the cluster's audit profile is &#96;None&#96;, which the reader reports as "no audit files on any node" rather than as "nobody logged in". | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:95 | **Goal.** Record the same &#96;login_event&#96; rows — who, when, provider where known, outcome — from &#96;/var/log/oauth-server/audit.log&#96; on the control-plane nodes, so an operator can retire the &#96;authLogLevel&#96; Jobs (no Debug, no OAuth roll, no login outage) and gain the history the pod log never had, while the store, the Logins tab, retention and the metrics stay as they are. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:97 | **The switch.** &#96;loginCapture.source: pod-log \| audit-log&#96;, **default &#96;pod-log&#96;**. Rationale (in the values comment): &#96;audit-log&#96; needs a cluster-wide grant — &#96;get nodes/proxy&#96; reads anything the kubelet serves over GET (every container's log on that node via &#96;/containerLogs&#96;, the kube-apiserver audit log, the journal) — and a &#96;list nodes&#96; grant unless node names are pinned; that is categorically wider than the namespaced &#96;pods/log&#96; Role and it is a standing capability. A grant of that width is opted into, never defaulted. &#96;both&#96; is deliberately not offered in this PR: it would keep Debug on, which is the thing this source lets an operator retire; the &#96;audit_id&#96; link column below is what a later &#96;both&#96; mode would use, so nothing here forecloses it. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:101 | \| &#96;loginCapture.source&#96; \| &#96;authLogLevel.manage&#96; \| &#96;authLogLevel.enabled&#96; \| render \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:103 | \| &#96;pod-log&#96; \| any \| any \| as today \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:110 | **Which source is authoritative.** With &#96;source: audit-log&#96;, the audit log is the only source read and the authoritative who/when/allow-deny record; pod-log rows already stored are kept and, where an audit event corresponds to one (same user, same success class, within 2 s — measured 16 ms apart in &#96;docs/DESIGN_login_capture.md#deliberate test logins appear exactly as made&#96;), the audit event is **linked** to the existing row (&#96;audit_id&#96; set) rather than inserted beside it, so the row keeps its LDAP cause and the record does not double. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:127 | # One audit-file read's byte budget per cycle. The same figure as the pod-log cap and for the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:241 |         Bounded in bytes and in wall-clock (LOG_READ_BUDGET_SECONDS), like fetch_pod_log, and a | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:378 | migration from the pod-log source both records exist for the same login; an audit event matching | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:379 | a pod-log row for the same user and success class within CORRESPONDENCE_SECONDS is LINKED to it | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:418 | # A pod-log row and an audit event for ONE login sit this close: measured 16 ms apart on the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:691 |                          f", linked {linked} to pod-log rows" if linked else "") | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:735 |     # WHICH LOG. &#96;pod-log&#96; reads the oauth-server pods' logs, which name a person only at | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:739 |     # grant, which is why the chart defaults it off. Anything unrecognised is pod-log: the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:741 |     login_capture_source: str = "pod-log" | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:752 |     """pod-log \| audit-log. Fail SAFE to pod-log: it is the shipped default and needs nothing | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:756 |         source = raw.get("loginCaptureSource", "pod-log") | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:758 |     if word in ("pod-log", "audit-log"): | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:760 |     log.warning("loginCaptureSource=%r is not pod-log/audit-log; using 'pod-log'", source) | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:761 |     return "pod-log" | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:784 |     -- 'pod-log' or 'audit-log' (migration 8). For an audit row pod_name carries the NODE the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:786 |     source              TEXT NOT NULL DEFAULT 'pod-log', | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:788 |     -- free; SET on a pod-log row when an audit event corresponds to it, so one login read from | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:822 |             "ALTER TABLE login_event ADD COLUMN source TEXT NOT NULL DEFAULT 'pod-log'", | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:836 |             # Every existing row is a pod-log row, which the DEFAULT states. No backfill of | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:851 |                 [{"source": "pod-log", "audit_id": None, **e, "cluster_id": cluster_id} | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:863 |         """Insert audit-source attempts, LINKING one to an existing pod-log row where the two | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:868 |           2. a pod-log row for the same user, same success class, within the window and not yet | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:891 |                         WHERE cluster_id=? AND user_name=? AND source='pod-log' | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:942 |         because auditID makes a re-read free — the opposite trade from the pod-log watermark.""" | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1046 |             "Always 1; &#96;source&#96; is which log login capture reads for this cluster (pod-log or " | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1068 |                         [cluster, getattr(self.settings, "login_capture_source", "pod-log")], 1) | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1069 |                     if getattr(self.settings, "login_capture_source", "pod-log") == "audit-log": | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1086 |   #   pod-log     (default) the oauth-server pods' logs, through a Role in openshift-authentication | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1088 |   #               authentication operator CR (authLogLevel below), which rolls the OAuth server — | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1104 |   # pod-log despite the audit log being the better source in every other respect. Narrow it with | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1107 |   # HOW IT MEETS authLogLevel: with source audit-log, Debug is unnecessary. The chart REFUSES | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1108 |   # source=audit-log together with authLogLevel.enabled=true — it will not roll the OAuth server | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1110 |   #   1. loginCapture.source=audit-log  authLogLevel.manage=true   authLogLevel.enabled=false | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1112 |   #   2. authLogLevel.manage=false once the rollout has finished. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1113 |   # The audit log is the authoritative record from then on; pod-log rows already stored are kept, | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1115 |   source: pod-log | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1130 | # pod-log \| audit-log, validated where it is resolved, and the ONE place the two switches that | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1135 | {{- $s := "pod-log" -}} | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1137 | {{- if not (has $s (list "pod-log" "audit-log")) -}} | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1138 | {{- fail (printf "loginCapture.source %q is not one of pod-log, audit-log." $s) -}} | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1140 | {{- if and (eq $s "audit-log") ((.Values.authLogLevel \| default dict).enabled) -}} | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1141 | {{- fail "loginCapture.source=audit-log and authLogLevel.enabled=true contradict each other: the audit log names every login at the DEFAULT verbosity, so Debug on the authentication operator CR buys nothing and costs an OAuth roll. The chart will not roll the OAuth server as a side effect of a read setting. Retire Debug in order:\n  1. --set loginCapture.source=audit-log --set authLogLevel.manage=true --set authLogLevel.enabled=false   (converges the cluster to Normal; one last roll — a login outage at one replica)\n  2. --set authLogLevel.manage=false once the rollout has finished.\nPass your whole values file each time (see the chart README)." -}} | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1159 | # the journal. Read-only, and far wider than the namespaced pods/log Role the pod-log source | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1208 | …followed by the existing Role/RoleBinding text unchanged, ending in the existing &#96;{{- end }}&#96;. The pod-log render is byte-identical to today. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1214 |     # authLogLevel.enabled=true are refused as a contradiction. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1228 | needed; if authLogLevel.manage is still true with enabled=false, the Job is converging the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1234 | **Chart README rows** (RBAC and monitoring table, before the &#96;authLogLevel.manage&#96; row): | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1238 | \| &#96;loginCapture.source&#96; \| &#96;pod-log&#96; \| &#96;pod-log&#96; — a Role on &#96;pods&#96;/&#96;pods/log&#96; in &#96;loginCapture.namespace&#96;; names a person only at Debug (&#96;authLogLevel&#96;), keeps the LDAP cause, loses history with every pod. &#96;audit-log&#96; — &#96;/var/log/oauth-server/audit.log&#96; on the control-plane nodes through the node proxy: no Debug, no OAuth roll, history back to the rotated files; a **ClusterRole on &#96;get nodes/proxy&#96;**, which reads everything the kubelet serves on those nodes, plus &#96;list nodes&#96; unless &#96;auditLog.nodeNames&#96; is set — read-only, cluster-wide, hence not the default. Refused together with &#96;authLogLevel.enabled=true&#96;; the audit log is authoritative from the switch on and corresponding pod-log rows are linked, not doubled \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1239 | \| &#96;loginCapture.namespace&#96; \| &#96;openshift-authentication&#96; \| pod-log source only: where the oauth-server pods run \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1252 | # authLogLevel Jobs can be retired — and renders a ClusterRole on &#96;get nodes/proxy&#96; (+ &#96;list | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1254 | # Default pod-log: the render is byte-identical to 0.11.0. New refusal: source=audit-log with | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1255 | # authLogLevel.enabled=true (docs/DESIGN_login_capture.md). | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1271 | """The audit-log source: the parser, the cursor, the backfill, and the link to pod-log rows. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1528 |     def test_an_audit_event_links_to_its_pod_log_twin_instead_of_doubling(self, store): | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1537 |         assert rows[0]["outcome"] == loginlog.OUTCOME_BAD_PASSWORD, "the pod-log row keeps its cause" | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1563 |     def test_an_existing_row_is_a_pod_log_row(self, tmp_path): | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1568 |         assert row["source"] == "pod-log" and row["audit_id"] is None | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1572 | Plus: &#96;tests/test_config.py&#96; — three tests (&#96;loginCaptureSource&#96; parses, junk falls back to &#96;pod-log&#96; with a warning, node names split); &#96;tests/test_chart_strategy.py::TestAuditLogSource&#96; — default renders no &#96;login-capture-audit&#96;; &#96;audit-log&#96; renders the ClusterRole with exactly &#96;[("nodes/proxy",),("get",)]&#96; and &#96;[("nodes",),("list",)]&#96; and **no** Role in &#96;openshift-authentication&#96;; &#96;nodeNames&#96; set → &#96;resourceNames&#96; present and no &#96;nodes&#96; list rule; &#96;TestLoginCaptureReadsOneNamespaceOnly.test_the_log_read_is_never_cluster_scoped&#96; re-run with &#96;loginCapture__source=audit-log&#96; in its &#96;extra&#96; list; &#96;audit-log&#96; + &#96;authLogLevel__enabled=true&#96; refused with "contradict"; &#96;audit-log&#96; + &#96;manage=true&#96; + &#96;enabled=false&#96; renders and the Job's &#96;WANT=Normal&#96;; &#96;loginCapture__source=both&#96; refused; ConfigMap carries &#96;loginCaptureSource: "audit-log"&#96;. &#96;tests/test_metrics.py&#96; — &#96;gsd_login_capture_source_info{cluster="crc",source="audit-log"} 1&#96; when settings say so, absent when capture is off; &#96;gsd_login_capture_audit_settled_timestamp_seconds{cluster,node}&#96; after a &#96;set_audit_cursor&#96;; both names added to &#96;test_event_families_are_declared_even_unwired&#96;. &#96;tests/test_users_tab_logins.py&#96;-style API test: &#96;/logins&#96; carries &#96;source&#96; and the audit note; &#96;?outcome=provider_error&#96; is accepted (200). | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1576 | - **&#96;docs/DESIGN_login_capture.md&#96;** — replace the heading &#96;## The oauth-server AUDIT LOG — a better source, not used&#96; and its first paragraph (&#96;Found after the design was written ... not an oversight.&#96;) with &#96;## The oauth-server AUDIT LOG — the second source (0.13.0)&#96; and: &#96;Found after the design was written, measured on the live cluster, parked for a release because of the grant it needs, and adopted in 0.13.0 as \&#96;loginCapture.source: audit-log\&#96; — opt-in, for exactly that reason. The reader is \&#96;gsd/kube.py#ClusterClient.fetch_node_log_file\&#96; (byte cursor, Range, rotation detection), the front end is \&#96;gsd/auditlog.py#parse_audit_line\&#96;, the loop is \&#96;gsd/auditlog.py#capture_once\&#96;, and the link to pod-log rows is \&#96;gsd/store.py#Store.record_audit_login_events\&#96;. What follows is the measurement that justified it.&#96; Keep the table; replace &#96;**Why it was not chosen.**&#96; paragraph's last sentence &#96;For an application whose defining invariant ... wrong trade.&#96; with &#96;For an application whose defining invariant is that it reads narrowly and writes nothing, that is a trade the operator makes, not the chart: default off, the blast radius stated in values.yaml, narrowable to named nodes.&#96; Replace &#96;**If it is ever revisited**, the dedup key changes ...&#96; paragraph with the as-built rule: auditID unique per cluster (\&#96;gsd/store.py#login_event_by_audit_id\&#96;), \&#96;pod_name\&#96; carrying the node, correspondence linking within \&#96;gsd/auditlog.py#CORRESPONDENCE_SECONDS\&#96;, the browser pair coalesced by path within \&#96;ATTEMPT_WINDOW\&#96;; and the sentence: **the audit log is authoritative once selected; the pod log is not read at all in that mode, and \&#96;both\&#96; is deliberately not offered because it would keep the Debug roll the audit source exists to retire.** Also amend &#96;## Accepted limitation: the past cannot be reconstructed&#96; with a final sentence: &#96;That limitation is the pod-log source's. The audit source backfills to the oldest rotated file on first read, bounded by \&#96;loginRetentionDays\&#96; and drained at \&#96;gsd/kube.py#AUDIT_READ_MAX_BYTES\&#96; per node per cycle.&#96; And in "Not recorded": &#96;the audit event's query string (client_id, redirect_uri, PKCE challenge) — the path only.&#96; | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1589 |   so the &#96;authLogLevel&#96; Jobs and their OAuth roll can be retired, and a first read backfills as | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1592 |   corresponds to a pod-log row already stored is linked to it rather than recorded twice, and the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1601 |   values. &#96;source=audit-log&#96; with &#96;authLogLevel.enabled=true&#96; is refused: the chart will not roll | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1611 | helm template t charts/group-sync-dashboard --set ingress.host=t.example.com --set loginCapture.enabled=true --set loginCapture.source=audit-log --set authLogLevel.manage=true --set authLogLevel.enabled=true | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1612 | # expected: Error: ... loginCapture.source=audit-log and authLogLevel.enabled=true contradict each other ... | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1620 | #           "recorded N login attempt(s) from the audit log on crc-master-0 (audit.log), linked M to pod-log rows" | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1622 | # expected: source "audit-log", retained_since in 2025 (the backfill), total &gt; the pod-log count | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1632 | \| The grant is cluster-wide read \| default &#96;pod-log&#96;; breadth stated in values, README, NOTES and reference-architecture §7.1; &#96;nodeNames&#96; narrows; the existing no-&#96;pods/log&#96;-ClusterRole test still holds \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D1_audit_log_login_capture.md:1633 | \| Switching source rolls the OAuth server by accident \| render refusal on &#96;audit-log&#96; + &#96;authLogLevel.enabled=true&#96;; retirement order in the refusal text, values and NOTES \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D2_per_cluster_authorization.md:45 | **The capture pipeline as built.** &#96;gsd/kube.py#ClusterClient.fetch_oauth_pods&#96; and &#96;gsd/kube.py#ClusterClient.fetch_pod_log&#96; read pod logs (streamed, byte- and wall-clock-bounded by &#96;gsd/kube.py#LOG_READ_BUDGET_SECONDS&#96;); &#96;gsd/loginlog.py#parse&#96; correlates klog lines into &#96;LoginAttempt&#96;; &#96;gsd/logincapture.py#capture_once&#96; owns the per-pod watermark, the settle horizon (&#96;gsd/logincapture.py#_settle_horizon&#96;), the leading-edge guard (&#96;gsd/logincapture.py#_not_clipped&#96;) and the leadership recheck; &#96;gsd/logincapture.py#event_dict&#96; fixes the row shape and stamp format; &#96;gsd/store.py#Store.record_login_events&#96; inserts against &#96;UNIQUE(cluster_id, pod_name, user_name, at, outcome)&#96;; &#96;gsd/store.py#Store.prune_login_events&#96; is bounded; &#96;gsd/store.py#Store.record_login_read&#96; is the liveness record that &#96;gsd/metrics.py#DashboardCollector._gather&#96; exports as &#96;gsd_login_capture_last_read_timestamp_seconds{cluster}&#96;, and &#96;templates/monitoring.yaml#GroupSyncDashboardLoginCaptureStalled&#96; alerts on it joined &#96;on()&#96; to the unlabelled &#96;gsd_login_capture_enabled&#96;. The poller calls &#96;capture_once&#96; once per cycle after &#96;poll_once&#96; (&#96;gsd/poller.py#_run_cluster&#96;), so a second source must be a dispatch inside &#96;capture_once&#96;, not a second thread. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D2_per_cluster_authorization.md:47 | **The switches as built.** &#96;loginCapture.enabled&#96; renders a namespaced Role (&#96;templates/login-capture-rbac.yaml&#96;) and the ConfigMap key &#96;loginCaptureEnabled&#96; (&#96;templates/configmap.yaml#loginCaptureEnabled&#96;, the key that was once unwired). &#96;authLogLevel.manage&#96;/&#96;.enabled&#96; render two hook Jobs on a separate ServiceAccount (&#96;templates/auth-loglevel-job.yaml&#96;, &#96;templates/auth-loglevel-rbac.yaml&#96;, &#96;templates/auth-loglevel-revert-job.yaml&#96;); the values comment is explicit that a toggle "ROLLS THE OAUTH SERVER, WHICH IS A LOGIN OUTAGE ON A SINGLE-REPLICA CLUSTER", and the chart README says turning it off is two steps in order (&#96;enabled=false&#96; then &#96;manage=false&#96;). &#96;tests/test_chart_strategy.py::TestLoginCaptureReadsOneNamespaceOnly&#96; asserts no ClusterRole ever grants &#96;pods&#96;/&#96;pods/log&#96; — the audit-log grant must be a *different* resource so that test keeps holding. | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D2_per_cluster_authorization.md:74 | Consequences carried into the design: (1) the oauth-server audit log names no identity provider except in the browser path's &#96;/login/&lt;idp&gt;&#96; URI, so &#96;provider&#96; is nullable on audit rows and the break-glass classification (&#96;gsd/api.py#list_logins&#96;, &#96;break_glass = provider in htpasswd&#96;) cannot fire for a CLI &#96;kubeadmin&#96; login — stated as a limitation, not hidden; (2) &#96;deny&#96; carries no cause, so the LDAP result codes and AD sub-codes stay pod-log-only, exactly as &#96;docs/DESIGN_login_capture.md#It also carries no cause&#96; says; (3) the audit source is **off** when the cluster's audit profile is &#96;None&#96;, which the reader reports as "no audit files on any node" rather than as "nobody logged in". | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D2b_remote_sar_for_every_join.md:5070 |         &lt;svg viewBox="0 0 980 490" role="img" aria-label="remote-sar today: a cached verdict, or list the reader's groups on the remote and create a SubjectAccessReview there with the joining token. Allowed gives the wide view and denied gives self, both cached. A 401, 403 or unreachable answer at either remote call gives self, not cached, with a pod-log warning and the tier-check metric; any other exception gives self, not cached, with an ERROR and the metric outcome error. The named finding and the per-outcome sentence are proposals D4 and D5."&gt; | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| docs/specs/SPEC_D2b_remote_sar_for_every_join.md:5074 |         &lt;svg viewBox="0 0 980 490" role="img" aria-label="remote-sar today: a cached verdict, or list the reader's groups on the remote and create a SubjectAccessReview there with the joining token. Allowed gives the wide view and denied gives self, both cached. A 401, 403 or unreachable answer at either remote call gives self, not cached, with a pod-log warning and the tier-check metric; any other exception gives self, not cached, with an ERROR and the metric outcome error. A failure holds the cluster's resolver for 30 s; the line beside the selector (D5) names the rule; the named finding is proposal D4."&gt; | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| environments/README.md:54 | \| &#96;authLogLevel.manage&#96; / &#96;.enabled&#96; \| &#96;false&#96; / &#96;false&#96; \| &#96;false&#96; / &#96;false&#96; \| inherits the default: the lab reads the AUDIT LOG, which names the person at the default verbosity, so the auth-loglevel Job (a post-upgrade hook) is not needed; the one-time convergence to Normal is done, so management is off (set &#96;manage=true&#96; only for the pod-log source) \| | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| environments/README.md:68 | - &#96;authLogLevel&#96; writes a **cluster-scoped** CR and rolls the OAuth server, which on a | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| environments/crc.yaml:27 | # for THIS Python process — not the cluster's verbosity, and not &#96;authLogLevel&#96; below. The two are | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| environments/crc.yaml:45 | #   authLogLevel  raises &#96;spec.logLevel&#96; on the authentication OPERATOR CR — NOT the OAuth CR — so the | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| environments/crc.yaml:46 | #                 oauth-server's POD LOG names the person logging in. Only the pod-log source needs it. | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| environments/crc.yaml:48 | #   loginCapture  lets the DASHBOARD read a log. &#96;source: pod-log&#96; is a Role on pods/log in | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| environments/crc.yaml:65 | # pod-log login source, which is the one that needs the elevated verbosity. | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| environments/crc.yaml:66 | authLogLevel: | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/Containerfile:168 | # Not to be confused with the chart's authLogLevel, which raises the oauth-server's own verbosity | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/Containerfile.annotated:302 | # Not to be confused with the chart's authLogLevel, which raises the oauth-server's own verbosity | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/Containerfile.ubi:74 | # Not to be confused with the chart's authLogLevel, which raises the oauth-server's own verbosity | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/api.py:1823 |                         "form — every pod-log row is one), cli (&#96;oc login&#96; and other " | kept | Keep historical row fields, filters, tier scoping and outcome vocabulary; remove live pod-source note and obsolete logging advice. |
| local-development/gsd/api.py:1836 |         Rows carry &#96;source&#96; (pod-log or audit-log), &#96;kind&#96;, and — from the audit-log source — the | kept | Keep historical row fields, filters, tier scoping and outcome vocabulary; remove live pod-source note and obsolete logging advice. |
| local-development/gsd/api.py:1845 |         under &#96;pod-log&#96; nothing before capture began exists to fetch — the log dies with its pod; under | edited | Keep historical row fields, filters, tier scoping and outcome vocabulary; remove live pod-source note and obsolete logging advice. |
| local-development/gsd/api.py:3376 |     THE COMPLAINT POINTS AT &#96;authLogLevel&#96;, because the commonest reason to be fiddling with a log | edited | Keep historical row fields, filters, tier scoping and outcome vocabulary; remove live pod-source note and obsolete logging advice. |
| local-development/gsd/api.py:3408 |         f"authLogLevel value — a different setting, on a different object, not this one." | edited | Keep historical row fields, filters, tier scoping and outcome vocabulary; remove live pod-source note and obsolete logging advice. |
| local-development/gsd/auditlog.py:45 | matching a pod-log row for the same user and success class within CORRESPONDENCE_SECONDS is LINKED | kept | Keep 0.25-second legacy-row correspondence, audit parsing/cursors/backfill/leadership and retention; edit stamp comment only. |
| local-development/gsd/auditlog.py:92 | # A pod-log row and an audit event for ONE login sit this close: measured 16 ms apart on the | kept | Keep 0.25-second legacy-row correspondence, audit parsing/cursors/backfill/leadership and retention; edit stamp comment only. |
| local-development/gsd/auditlog.py:607 |                          f", linked {linked} to pod-log rows" if linked else "") | kept | Keep 0.25-second legacy-row correspondence, audit parsing/cursors/backfill/leadership and retention; edit stamp comment only. |
| local-development/gsd/config.py:493 |     # WHICH LOG. &#96;pod-log&#96; reads the oauth-server pods' logs, which name a person only at | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/config.py:497 |     # grant, which is why the chart defaults it off. Anything unrecognised is pod-log: the | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/config.py:499 |     login_capture_source: str = "pod-log" | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/config.py:1031 |     """pod-log \| audit-log. Fail SAFE to pod-log: it is the shipped default and needs nothing | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/config.py:1035 |         source = raw.get("loginCaptureSource", "pod-log") | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/config.py:1037 |     if word in ("pod-log", "audit-log"): | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/config.py:1039 |     log.warning("loginCaptureSource=%r is not pod-log/audit-log; using 'pod-log'", source) | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/config.py:1040 |     return "pod-log" | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/kube.py:91 | # One audit-file read's byte budget per cycle. The same figure as the pod-log cap and for the | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/kube.py:103 | # One pod-log read's wall-clock budget. The httpx timeout on _client caps the SILENCE between | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/kube.py:1137 |     def fetch_pod_log( | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/kube.py:1250 |         """Classify a &gt;=400 on a pod-log read: benign roll noise, or something worth saying out loud. | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/kube.py:1398 |         Bounded in bytes and in wall-clock (LOG_READ_BUDGET_SECONDS), like fetch_pod_log, and a | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/logincapture.py:237 |             lines = client.fetch_pod_log(ns, pod, since_seconds=since) | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/logincapture.py:299 |                       "written (chart value authLogLevel, NOT logLevel; see " | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/gsd/metrics.py:463 |             "Always 1; &#96;source&#96; is which log login capture reads for this cluster (pod-log or " | edited | Keep metric names/label keys; live source value becomes audit-log and help text follows it. |
| local-development/gsd/metrics.py:524 |                     source = getattr(self.settings, "login_capture_source", "pod-log") | edited | Keep metric names/label keys; live source value becomes audit-log and help text follows it. |
| local-development/gsd/static/index.html:3977 |   "pod-log": { | edited | Remove live pod-source advice; retain historical row display and explain Node / stored pod column. |
| local-development/gsd/static/index.html:4003 |         the Debug source is &lt;code&gt;authLogLevel.manage&lt;/code&gt; and &lt;code&gt;.enabled&lt;/code&gt;, a | edited | Remove live pod-source advice; retain historical row display and explain Node / stored pod column. |
| local-development/gsd/static/index.html:4052 |   const text = LOGIN_SOURCE_TEXT[d.source === "audit-log" ? "audit-log" : "pod-log"]; | edited | Remove live pod-source advice; retain historical row display and explain Node / stored pod column. |
| local-development/gsd/store.py:428 |     -- 'pod-log' or 'audit-log' (migration 10). For an audit row pod_name carries the NODE the | kept | Keep schema/defaults/migrations, historical row reads, legacy fixture writer/watermarks and audit correspondence; edit only its fixture comment. No data deletion. |
| local-development/gsd/store.py:430 |     source              TEXT NOT NULL DEFAULT 'pod-log', | kept | Keep schema/defaults/migrations, historical row reads, legacy fixture writer/watermarks and audit correspondence; edit only its fixture comment. No data deletion. |
| local-development/gsd/store.py:432 |     -- free; SET on a pod-log row when an audit event corresponds to it, so one login read from | kept | Keep schema/defaults/migrations, historical row reads, legacy fixture writer/watermarks and audit correspondence; edit only its fixture comment. No data deletion. |
| local-development/gsd/store.py:900 |             "ALTER TABLE login_event ADD COLUMN source TEXT NOT NULL DEFAULT 'pod-log'", | kept | Keep schema/defaults/migrations, historical row reads, legacy fixture writer/watermarks and audit correspondence; edit only its fixture comment. No data deletion. |
| local-development/gsd/store.py:923 |             # Every existing login row is a pod-log credential attempt, which the DEFAULTs state. | kept | Keep schema/defaults/migrations, historical row reads, legacy fixture writer/watermarks and audit correspondence; edit only its fixture comment. No data deletion. |
| local-development/gsd/store.py:2946 |                 [{"source": "pod-log", "audit_id": None, "kind": "credential", "client_id": None, | kept | Keep schema/defaults/migrations, historical row reads, legacy fixture writer/watermarks and audit correspondence; edit only its fixture comment. No data deletion. |
| local-development/gsd/store.py:3013 |         """Insert audit-source attempts, LINKING one to an existing pod-log row where the two | kept | Keep schema/defaults/migrations, historical row reads, legacy fixture writer/watermarks and audit correspondence; edit only its fixture comment. No data deletion. |
| local-development/gsd/store.py:3018 |           2. a pod-log row for the same user, same success class, within the window and not yet | kept | Keep schema/defaults/migrations, historical row reads, legacy fixture writer/watermarks and audit correspondence; edit only its fixture comment. No data deletion. |
| local-development/gsd/store.py:3044 |                             WHERE cluster_id=? AND user_name=? COLLATE NOCASE AND source='pod-log' | kept | Keep schema/defaults/migrations, historical row reads, legacy fixture writer/watermarks and audit correspondence; edit only its fixture comment. No data deletion. |
| local-development/gsd/store.py:3072 |                     # The pod-log UNIQUE key (cluster, pod/node, user, at, outcome) ignored a row | kept | Keep schema/defaults/migrations, historical row reads, legacy fixture writer/watermarks and audit correspondence; edit only its fixture comment. No data deletion. |
| local-development/gsd/store.py:3104 |         because auditID makes a re-read free — the opposite trade from the pod-log watermark. | kept | Keep schema/defaults/migrations, historical row reads, legacy fixture writer/watermarks and audit correspondence; edit only its fixture comment. No data deletion. |
| local-development/mock-app/README.md:4 | issues** — the ~16 read endpoints, the two node-log-proxy shapes, the pod-log stream, and the | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/README.md:31 | │   ├── podlog.py     pod-log text stream | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/mock_app/__init__.py:4 | node-log-proxy shapes, the pod-log stream, and the SubjectAccessReview POST) from a declarative | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/mock_app/app.py:23 | from .podlog import PodLogServer | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/mock_app/app.py:143 |     state.podlog = PodLogServer(fixture.pod_log) | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/mock_app/app.py:318 |     def pod_log(request: Request, namespace: str, pod: str): | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/mock_app/app.py:322 |         body = state.podlog.body() | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/mock_app/app.py:428 |         state.podlog = PodLogServer(fresh.pod_log) | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/mock_app/errors.py:9 | * &#96;&#96;status_json&#96;&#96; — a Kubernetes Status body, used for pod-log &gt;=400. | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/mock_app/fixture.py:230 |     pod_log: PodLogFixture | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/mock_app/fixture.py:291 |         pod_log = _pod_log(data.get("podLog")) | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/mock_app/fixture.py:312 |             pod_log=pod_log, | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/mock_app/fixture.py:564 | def _pod_log(value: Any) -&gt; PodLogFixture: | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/mock_app/podlog.py:1 | """The pod-log text stream (DESIGN §7.3, endpoint m). | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| local-development/mock-app/mock_app/podlog.py:15 |     def __init__(self, pod_log: PodLogFixture): | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| local-development/mock-app/mock_app/podlog.py:16 |         self._pod_log = pod_log | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| local-development/mock-app/mock_app/podlog.py:20 |         return self._pod_log.namespace | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| local-development/mock-app/mock_app/podlog.py:24 |         if not self._pod_log.lines: | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| local-development/mock-app/mock_app/podlog.py:26 |         return ("\n".join(self._pod_log.lines) + "\n").encode("utf-8") | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| local-development/mock-app/mock_app/responses.py:273 |     Read by kube.py's _log_read_refused (&#96;&#96;.reason&#96;&#96;, &#96;&#96;.message&#96;&#96;) on a pod-log &gt;=400. | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/tests/test_request_surface.py:147 | def test_fetch_pod_log(client): | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/mock-app/tests/test_request_surface.py:148 |     lines = client.fetch_pod_log("openshift-authentication", "oauth-openshift-6d8f9c7b4-abcde") | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_auditlog.py:2 | link to pod-log rows. | kept | Keep audit parser, real audit loop, cursor/leadership and legacy correspondence/migration tests. |
| local-development/tests/test_auditlog.py:515 |     def test_an_audit_credential_event_links_to_its_pod_log_twin_instead_of_doubling(self, store): | kept | Keep audit parser, real audit loop, cursor/leadership and legacy correspondence/migration tests. |
| local-development/tests/test_auditlog.py:524 |         assert rows[0]["outcome"] == loginlog.OUTCOME_BAD_PASSWORD, "the pod-log row keeps its cause" | kept | Keep audit parser, real audit loop, cursor/leadership and legacy correspondence/migration tests. |
| local-development/tests/test_auditlog.py:546 |         """Cursor, review D1. Measured on the reference cluster: a pod-log row and its audit twin | kept | Keep audit parser, real audit loop, cursor/leadership and legacy correspondence/migration tests. |
| local-development/tests/test_auditlog.py:558 |         assert {r["source"] for r in rows} == {"pod-log", "audit-log"} | kept | Keep audit parser, real audit loop, cursor/leadership and legacy correspondence/migration tests. |
| local-development/tests/test_auditlog.py:561 |         """Codex and Cursor, review D1: the table's pod-log UNIQUE key also binds audit rows, so two | kept | Keep audit parser, real audit loop, cursor/leadership and legacy correspondence/migration tests. |
| local-development/tests/test_auditlog.py:597 |     def test_an_existing_row_is_a_pod_log_credential_row(self, tmp_path): | kept | Keep audit parser, real audit loop, cursor/leadership and legacy correspondence/migration tests. |
| local-development/tests/test_auditlog.py:602 |         assert row["source"] == "pod-log" and row["audit_id"] is None and row["kind"] == "credential" | kept | Keep audit parser, real audit loop, cursor/leadership and legacy correspondence/migration tests. |
| local-development/tests/test_chart_pdb.py:4 | Measured on the reference cluster (2026-09-05): the &#96;authLogLevel&#96; hook Job pods carried the same | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| local-development/tests/test_chart_pdb.py:70 |         # source=pod-log because the chart refuses authLogLevel.enabled with the audit-log | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_pdb.py:72 |         docs = _render("authLogLevel.manage=true", "authLogLevel.enabled=true", "loginCapture.source=pod-log") | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_pdb.py:105 |         # source=pod-log: the chart refuses authLogLevel.enabled with the audit-log default (0.52.0). | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_pdb.py:106 |         docs = _render("authLogLevel.manage=true", "authLogLevel.enabled=true", "loginCapture.source=pod-log") | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_rbac_provenance.py:34 | # cluster-Secret writes, the auditor binding) and the pod-log source with the authLogLevel Job, whose | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_rbac_provenance.py:38 |     "pod-log": ["--set", "loginCapture.source=pod-log", "--set", "authLogLevel.manage=true"], | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:253 |     # pod-log is opt-in since chart 0.52.0 (audit-log is the default), so this path says so. | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:254 |     ON = {"loginCapture__enabled": "true", "loginCapture__source": "pod-log"} | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:272 |         for extra in ({}, self.ON, {**self.ON, "authLogLevel__manage": "true"}, | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:316 | class TestTheOauthLogLevelJobKeepsTheWriteOffTheDashboard: | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:327 |     # authLogLevel raises the OAuth server verbosity, which only the pod-log source needs — and | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:328 |     # the chart REFUSES it together with source=audit-log, now the default. Select pod-log. | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:329 |     ON = {"authLogLevel__manage": "true", "loginCapture__source": "pod-log"} | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:343 |         for extra in ({}, self.ON, {**self.ON, "authLogLevel__enabled": "true"}): | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:391 |             ok, out = render(**self.ON, authLogLevel__enabled=enabled) | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:543 |         ok, out = render(**self.ON, authLogLevel__waitSeconds="600") | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:1538 |     """D1: &#96;loginCapture.source: audit-log&#96; swaps the namespaced pod-log Role for a ClusterRole on | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:1564 |     def test_the_default_renders_the_audit_grant_and_no_pod_log_role(self): | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| local-development/tests/test_chart_strategy.py:1571 |         assert self._rules(out, "Role", "login-capture") is None, "the pod-log Role must not render by default" | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| local-development/tests/test_chart_strategy.py:1574 |     def test_pod_log_remains_selectable_and_then_renders_no_audit_grant(self): | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:1576 |         ok, out = render(loginCapture__source="pod-log") | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:1580 |         assert 'loginCaptureSource: "pod-log"' in out | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:1587 |         assert self._rules(out, "Role", "login-capture") is None, "the pod-log Role must not render too" | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| local-development/tests/test_chart_strategy.py:1648 |                          authLogLevel__manage="true", authLogLevel__enabled="true") | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:1652 |         ok, out = render(**self.AUDIT, authLogLevel__manage="true", authLogLevel__enabled="true") | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:1656 |         ok, out = render(**self.AUDIT, authLogLevel__manage="true", authLogLevel__enabled="false") | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_chart_strategy.py:1662 |         for value in ("both", "pod-logs", "AUDIT-LOG"): | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| local-development/tests/test_config.py:578 |     def test_the_default_is_pod_log_with_the_measured_defaults(self, tmp_path): | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_config.py:580 |         assert s.login_capture_source == "pod-log" | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_config.py:619 |     def test_junk_falls_back_to_pod_log_with_a_warning(self, tmp_path, caplog): | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_config.py:623 |         assert s.login_capture_source == "pod-log" | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_environments_readme.py:58 |     &#96;authLogLevel.manage&#96; / &#96;.enabled&#96; — because they are one decision to a reader; the shorthand | kept | Historical/compatibility reference, not a live OAuth Debug reader or writer; no behavior change required. |
| local-development/tests/test_kube_reader.py:46 |     got = client.fetch_pod_log("ns", "pod", max_bytes=20) | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_kube_reader.py:59 |         got = client.fetch_pod_log("ns", "pod", max_bytes=20) | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_kube_reader.py:70 |     got = client.fetch_pod_log("ns", "pod", max_bytes=30) | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_kube_reader.py:107 |         got = client.fetch_pod_log("ns", "pod") | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_log_levels.py:148 |     &#96;authLogLevel&#96;, which raises the OAUTH-SERVER's verbosity and is what makes the login lines the | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_log_levels.py:158 |     assert "authLogLevel" in got["complaint"], ( | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_log_levels.py:159 |         f"{written!r} must be refused with a pointer at authLogLevel" | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_log_levels.py:290 |     assert "authLogLevel" in complaint | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_log_levels.py:316 |         """The operator-facing prose about &#96;logLevel&#96;, excluding the &#96;authLogLevel&#96; sections. | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| local-development/tests/test_log_levels.py:318 |         &#96;authLogLevel&#96; legitimately documents &#96;Normal&#96; and &#96;Debug&#96; — those are ITS real values, on | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| local-development/tests/test_log_levels.py:323 |         for marker in ("authLogLevel", "oauth-server log verbosity", "### oauth-server"): | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| local-development/tests/test_login_capture_cross_seam.py:94 |     def fetch_pod_log(self, namespace, pod_name, since_seconds=None, **kw): | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| local-development/tests/test_logincapture_loop.py:73 |     def fetch_pod_log(self, namespace, pod_name, since_seconds=None, **kw): | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| local-development/tests/test_logincapture_loop.py:168 |         """fetch_pod_log returns None for roll noise or a missing grant; both are already logged.""" | removed | Whole retired live reader/mock/test/template payload removed; phase-2 deletion protocol removes empty file. |
| local-development/tests/test_metrics.py:556 |             for source in ("pod-log", "audit-log"): | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_migrations.py:238 |         assert tuple(row) == ("pod-log", "credential", None) | kept | Keep migration/default-source assertions: old rows remain pod-log. |
| local-development/tests/test_no_groupsync_operator.py:83 |             "defined, leaving a pod-log line as the only evidence the operator is missing." | kept | Refers to the dashboard application log, not the retired OAuth login source. |
| local-development/tests/test_ui.py:4054 |         assert "authLogLevel.manage" in body | kept | Edit live-source caveat expectations; keep historical rows, outcomes and display coverage. |
| local-development/tests/test_ui.py:10435 |     def test_the_pod_log_source_keeps_its_own_account(self, dash): | edited | Edit live-source caveat expectations; keep historical rows, outcomes and display coverage. |
| local-development/tests/test_ui.py:10436 |         text = self._render(dash, "pod-log") | edited | Edit live-source caveat expectations; keep historical rows, outcomes and display coverage. |
| local-development/tests/test_ui.py:10443 |         assert [p for p in self.POD_LOG if p in text] == [], "a pod-log sentence under the audit-log source" | kept | Edit live-source caveat expectations; keep historical rows, outcomes and display coverage. |
| local-development/tests/test_ui.py:10461 |         off_audit, off_pod = render("audit-log", False), render("pod-log", False) | edited | Edit live-source caveat expectations; keep historical rows, outcomes and display coverage. |
| local-development/tests/test_ui.py:10462 |         rows_audit, rows_pod = render("audit-log", True), render("pod-log", True) | edited | Edit live-source caveat expectations; keep historical rows, outcomes and display coverage. |
| local-development/tests/test_users_tab_logins.py:316 |     def test_pod_log_is_the_default_source_and_says_what_it_cannot_see(self, tmp_path): | edited | Update the live envelope to audit-log while keeping nonempty stored pod-log rows and their credential kind (Review round 1 C). |
| local-development/tests/test_users_tab_logins.py:318 |         assert body["source"] == "pod-log" | edited | Update the live envelope to audit-log while keeping nonempty stored pod-log rows and their credential kind (Review round 1 C). |
| local-development/tests/test_users_tab_logins.py:321 |         assert all(r["source"] == "pod-log" and r["kind"] == "credential" for r in body["attempts"]) | edited | Update the live envelope to audit-log while keeping nonempty stored pod-log rows and their credential kind (Review round 1 C). |
| local-development/tests/test_values_defaults.py:21 |     "authLogLevel.manage": "a cluster-wide write that rolls the OAuth server; the audit log replaces it", | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_values_defaults.py:22 |     "authLogLevel.enabled": "same decision as manage", | edited | Remove the retired surface or replace its values, fixture, test expectation or operator guidance; exact replacement is in implementation blocks. |
| local-development/tests/test_values_defaults.py:99 |     &#96;authLogLevel.enabled&#96; and &#96;trustedCA.existingConfigMap.enabled&#96; are told apart.""" | kept | Unchanged compatibility assertion, audit behavior or explicitly historical incident context in a file otherwise edited. |
| reports/2026-09-22_s4b_lookup/README.md:38 | - &#96;03-pod-log.txt&#96; — &#96;fleet-login … tls=serviceAccount&#96;, &#96;fleet-logout … outcome=revoked&#96;, then | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| reports/2026-09-22_s4b_lookup/capture.sh:19 |   &gt; "$OUT/03-pod-log.txt" 2&gt;&1 | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| reports/2026-09-24_312-close-out/README.md:16 | Two scripts are new: &#96;config-source.sh&#96;, the label census #354's premise rests on, and &#96;pod-log-excerpt.sh&#96;, the pod's | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| reports/2026-09-24_312-close-out/README.md:24 | **Times.** Every pod time below is the pod's own, UTC−4: its &#96;TZ&#96; is &#96;America/New_York&#96; (&#96;walk/pod-log-excerpt.out&#96;, | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| reports/2026-09-24_312-close-out/README.md:36 | \| &#96;walk/pod-log-excerpt.sh&#96;, &#96;.out&#96; \| the pod's log: every binding refresh of the three CRC entries and every line naming the planted grant \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| reports/2026-09-24_312-close-out/README.md:82 |   lines in all (&#96;walk/pod-log-excerpt.out&#96;); the line &#96;walk/evidence-347.out&#96; quotes, at 21:36:49, is the last of | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| reports/2026-09-24_312-close-out/README.md:87 |   &#96;walk/pod-log-excerpt.out&#96;). The copied script's wait for 206 therefore matched nothing and ran its budget of 48 × | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| reports/2026-09-24_312-close-out/README.md:91 |   showed 1; &#96;shared-rnd&#96;'s first refresh after the deletion, at 21:42:49, read 205 (&#96;walk/pod-log-excerpt.out&#96;), and | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| reports/2026-09-24_d2b-lab-walk/README.md:38 | \| 3 \| Helm round 1: every join path at the default \| &#96;mock&#96; start-up line &#96;remote-sar, identity same-as-host&#96;; &#96;shared-qa&#96; and &#96;shared-rnd&#96; resolved &#96;visibility=remote-sar identity=same-as-host enabled=true&#96; \| First run **FAILED** before install: &#96;release-crc.sh&#96;'s Helm handover was refused by a server-side-apply conflict on the kept PVCs' labels (owned by &#96;argocd-controller&#96;) — a pre-existing tooling defect, fixed in #343 (&#96;--force-conflicts&#96;; reviewed, CI 8/8, merged &#96;5b7d346&#96;). Rerun on &#96;8e50ff8&#96; (#342 with main): &#96;running : 8e50ff8eec — verified in-pod&#96;, and the release's per-cluster policy for &#96;shared-rnd&#96; and &#96;mock&#96;, &#96;visibility remote-sar (default), identity same-as-host (default)&#96; (&#96;step3b.out&#96;); the first resolution &#96;cycle=1 cluster=shared-rnd source=secret:gsd-cluster-shared-rnd … visibility=remote-sar identity=same-as-host enabled=true&#96; (&#96;step4.out&#96;; its Secret still states &#96;self-only&#96;/&#96;none&#96;: the stanza's pair is served). The pod-log lines for &#96;mock&#96;'s start-up and &#96;shared-qa&#96;'s resolution at this step were not saved to &#96;walk/&#96;; &#96;shared-qa&#96; resolving &#96;remote-sar&#96;/&#96;same-as-host&#96; is recorded at Step 10 (&#96;step10.out&#96;) and Step 11 — **PASS**. PVCs: identical UIDs, volumes and creation times before and after (&#96;pvc-baseline.txt&#96;, &#96;pvc-after-step3.txt&#96;). \| | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| reports/2026-09-24_d2b-lab-walk/walk/step3b.out:163 | needed; if authLogLevel.manage is still true with enabled=false, the Job is converging the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| reports/2026-09-24_d2b-lab-walk/walk/step9.out:85 | needed; if authLogLevel.manage is still true with enabled=false, the Job is converging the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |
| reports/2026-09-25_353-platform-rule/README.md:17 | and time below is quoted from a file in &#96;walk/&#96; (the &#96;.txt&#96;/&#96;.out&#96; files, the two release logs, the pod-log lines the | kept | Historical design/review/release/measurement record; not rewritten to describe a later release. |

## Implementation blocks

### Block 1 — charts/group-sync-dashboard/templates/auth-loglevel-job.yaml

Retire the whole file. Empty New is the checker-compatible deletion payload; see deletion protocol.
Baseline: charts/group-sync-dashboard/templates/auth-loglevel-job.yaml:1; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/templates/auth-loglevel-job.yaml | edit -->

Old text:

```text
{{- if .Values.authLogLevel.manage }}
{{- if ge (int .Values.authLogLevel.waitSeconds) (int .Values.authLogLevel.activeDeadlineSeconds) }}
{{- fail (printf "authLogLevel.waitSeconds (%v) must be LESS than activeDeadlineSeconds (%v).\n  As set, the deadline kills the Job mid-wait and FAILS `helm upgrade` — which contradicts the\n  promise in values.yaml that a wait timeout is not a failure. The wait must be able to finish\n  and print its own guidance before the deadline fires." .Values.authLogLevel.waitSeconds .Values.authLogLevel.activeDeadlineSeconds) }}
{{- end }}
# Turns the oauth-server operand's log verbosity up, and back down again, via the cluster's
# authentication OPERATOR CR.
#
# ── THREE SIMILARLY-NAMED RESOURCES. THIS ONE IS THE OPERATOR CR. ─────────────────────────────────
# Verified on a live cluster, because two of these are one word apart and hold entirely different
# things:
#
#   authentications.operator.openshift.io/cluster   kind Authentication (operator.openshift.io/v1)
#                                                   spec: logLevel, operatorLogLevel,
#                                                         managementState, ...        <- THIS FILE
#   authentications.config.openshift.io/cluster     kind Authentication (config.openshift.io/v1)
#                                                   spec: type, serviceAccountIssuer, oauthMetadata
#   oauth.config.openshift.io/cluster               kind OAuth
#                                                   spec: identityProviders, tokenConfig, templates
#
# The last of those is what people mean by "the OAuth CR" — it holds the LDAP identity provider, and
# the group-sync-operator chart reads it. This feature does NOT touch it. Saying "the OAuth CR" here
# would point a reader at the wrong object, and the RBAC below would look wrong to them.
#
# AND WITHIN the operator CR, `logLevel` is not `operatorLogLevel`: logLevel is the OPERAND's
# verbosity — the oauth-server process, which is what emits the login lines — while
# operatorLogLevel is the cluster-authentication-operator's own. Patching the wrong one changes
# nothing that this feature needs. Confirmed by reading the operand's args after a patch: the
# Deployment renders `exec oauth-server osinserver ... --v=2`, and Normal=2 / Debug=4.
#
# WHY THIS EXISTS: the oauth-openshift server only names the person logging in when
# `authentications.operator.openshift.io/cluster` has `spec.logLevel: Debug`. At `Normal` the line
# the dashboard's login capture reads does not exist at all — measured on the reference cluster:
# zero occurrences of "succeeded for login" until this Job runs. So this is the prerequisite for
# that feature, and nothing more.
#
# ── WHY A SEPARATE ServiceAccount, AND WHY IT MATTERS ────────────────────────────────────────────
# This Job WRITES to a core platform object. The dashboard must not be able to: `rbac.yaml` states
# "NO WRITE VERB ON ANYTHING THE DASHBOARD REPORTS ON" and five documents cite that line. So the
# grant lives on this Job's own ServiceAccount and the dashboard's stays read-only — the same split
# the group-sync-operator chart uses for its hook Jobs. The dashboard, separately, is granted only
# `get` on pods/log in openshift-authentication, which is a read.
#
# ── WHY IT RENDERS WHEN THE FEATURE IS OFF ───────────────────────────────────────────────────────
# `manage` and `enabled` are two switches on purpose, and the Job runs for BOTH values of `enabled`:
#
#   manage: false (default)   nothing renders, no RBAC, the chart never touches logLevel
#   manage: true, enabled: t  the Job sets Debug
#   manage: true, enabled: f  the Job sets Normal  <- this is what makes "turn it off" work
#
# Helm does not run a Job you merely stopped rendering, so a one-way "enable" Job would leave the
# cluster in Debug forever after somebody flipped the flag back and saw nothing happen. Applying the
# REQUESTED level rather than a fixed one converges either way, which is also what makes the Job
# safe to re-run.
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "gsd.fullname" . }}-auth-loglevel
  labels:
    {{- include "gsd.labels" . | nindent 4 }}
    app.kubernetes.io/component: auth-loglevel
  annotations:
    helm.sh/hook: post-install,post-upgrade
    # before-hook-creation, so an upgrade replaces the previous run rather than failing on a name
    # that already exists. NOT hook-succeeded: the log of what this changed on the cluster is worth
    # keeping until the next upgrade.
    helm.sh/hook-delete-policy: before-hook-creation
spec:
  backoffLimit: {{ .Values.authLogLevel.backoffLimit }}
  # A wall clock on the whole attempt. The wait loop below is bounded too, but a Job that cannot
  # reach the API server would otherwise sit in Pending indefinitely and hold up `helm upgrade`.
  activeDeadlineSeconds: {{ .Values.authLogLevel.activeDeadlineSeconds }}
  template:
    metadata:
      labels:
      # NOT gsd.selectorLabels. Those are the Service's and the PodDisruptionBudget's selector, and
      # a hook pod carrying them is matched by both: the Service routes to it while it runs (a pod
      # with no readiness probe is Ready as soon as its container starts), and the disruption
      # controller fails the PDB outright — measured on the reference cluster: "jobs.batch does not
      # implement the scale subresource", DisruptionAllowed=False, every drain blocked.
        app.kubernetes.io/name: {{ include "gsd.name" . }}
        app.kubernetes.io/instance: {{ .Release.Name }}
        app.kubernetes.io/component: auth-loglevel
    spec:
      restartPolicy: Never
      serviceAccountName: {{ include "gsd.fullname" . }}-auth-loglevel
      containers:
      - name: set-loglevel
        image: {{ .Values.authLogLevel.image.repository }}:{{ .Values.authLogLevel.image.tag }}
        imagePullPolicy: {{ .Values.authLogLevel.image.pullPolicy }}
        command:
        - /bin/bash
        - -c
        - |
          set -euo pipefail

          WANT={{ if .Values.authLogLevel.enabled }}Debug{{ else }}Normal{{ end }}

          # A3: an `oc get` FAILURE must not read as "already Normal". `|| true` on the old form
          # made a 403, a network blip and a genuinely-unset field indistinguishable — and the unset
          # case is the one that means "default, i.e. Normal", so an error silently claimed the work
          # was done. Status and value are captured separately.
          if ! CURRENT=$(oc get authentications.operator.openshift.io cluster \
                           -o jsonpath='{.spec.logLevel}' 2>&1); then
            echo "❌ cannot read authentications.operator.openshift.io/cluster:"
            echo "   ${CURRENT}"
            echo "   Nothing was changed. The ServiceAccount needs get+patch on that named object."
            exit 1
          fi
          echo "requested logLevel: ${WANT}"
          echo "current logLevel:   ${CURRENT:-<unset, i.e. Normal>}"

          # The operand's verbosity flag, which is what we actually wait for below. Verified on a live
          # cluster: the authentication operator renders `exec oauth-server osinserver ... --v=2` into
          # the Deployment's container args, and the OpenShift API types define Normal=2, Debug=4.
          case "$WANT" in
            Debug)  WANT_V=4 ;;
            Normal) WANT_V=2 ;;
          esac

          # An unset logLevel means the operator default, which IS Normal.
          if [ "${CURRENT:-Normal}" = "$WANT" ]; then
            echo "already ${WANT} — nothing to do"
            exit 0
          fi

          # C1: this is a LOGIN OUTAGE on a single-replica cluster, not a rolling update. Said here,
          # at the moment of acting, because a warning in values.yaml is read once and this is read
          # every time. Measured: `authentication` reported "no oauth-openshift pods available on any
          # node" and a second application watching the cluster logged
          # "HTTP 503 on /apis/user.openshift.io/v1/groups" while the roll happened.
          REPLICAS=$(oc get deploy oauth-openshift -n openshift-authentication \
                       -o jsonpath='{.spec.replicas}' 2>/dev/null || echo "?")
          if [ "$REPLICAS" = "1" ]; then
            echo
            echo "⚠️  oauth-openshift runs ONE replica: this roll is a LOGIN OUTAGE, not a rolling"
            echo "    update. In-flight logins fail and new ones are refused until the replacement"
            echo "    pod is Ready. Same on the way back off — both directions are a logLevel change."
            echo
          fi

          echo "patching authentications.operator.openshift.io/cluster -> ${WANT}"
          oc patch authentications.operator.openshift.io cluster --type=merge \
            -p "{\"spec\":{\"logLevel\":\"${WANT}\"}}"

          # A1: WAIT ON THE OPERAND'S OWN FLAG, not on the Deployment's generation.
          #
          # `oc rollout status` is useless here — measured: it returned "successfully rolled out"
          # about THIRTY SECONDS BEFORE the rollout began, because the old ReplicaSet was still
          # current and complete. The first fix for that polled generation/observedGeneration and
          # available/updated replicas, and it had the SAME defect for the same reason: every one of
          # those is a steady-state invariant that is equally true in the window before the operator
          # reconciles. It logged "rollout complete: generation 26" while the deployment went on to
          # generation 27 — the new pod started 29 seconds after the Job exited.
          #
          # `--v=<n>` in the Deployment's container args IS causal: it can only appear once the
          # operator has rendered the requested level into the workload. So the gate is "the template
          # carries the level we asked for" AND THEN Kubernetes' ordinary completion predicate.
          DEADLINE=$(( $(date +%s) + {{ .Values.authLogLevel.waitSeconds }} ))
          echo "waiting up to {{ .Values.authLogLevel.waitSeconds }}s for --v=${WANT_V} to be live"
          while :; do
            if [ "$(date +%s)" -ge "$DEADLINE" ]; then
              echo "⚠️  timed out waiting for the rollout. The level IS set — confirm with:"
              echo "    oc get pods -n openshift-authentication"
              echo "    oc get deploy oauth-openshift -n openshift-authentication -o yaml | grep -- --v="
              # NOT a failure. The patch landed, which is this Job's work; finishing the rollout is
              # the operator's. Failing here would fail `helm upgrade` over somebody else's slow
              # reconcile — see waitSeconds in values.yaml.
              exit 0
            fi
            tmpl=$(oc get deploy oauth-openshift -n openshift-authentication \
                     -o jsonpath='{.spec.template.spec.containers[*].args}' 2>/dev/null || true)
            gen=$(oc get deploy oauth-openshift -n openshift-authentication \
                    -o jsonpath='{.metadata.generation}' 2>/dev/null || true)
            obs=$(oc get deploy oauth-openshift -n openshift-authentication \
                    -o jsonpath='{.status.observedGeneration}' 2>/dev/null || true)
            want=$(oc get deploy oauth-openshift -n openshift-authentication \
                     -o jsonpath='{.spec.replicas}' 2>/dev/null || true)
            avail=$(oc get deploy oauth-openshift -n openshift-authentication \
                      -o jsonpath='{.status.availableReplicas}' 2>/dev/null || true)
            upd=$(oc get deploy oauth-openshift -n openshift-authentication \
                    -o jsonpath='{.status.updatedReplicas}' 2>/dev/null || true)
            # Every default is EMPTY, not 0/-1: an empty jsonpath means "could not read", and
            # substituting a number would make a comparison accidentally true. `-eq` on an empty
            # string is a syntax error under set -e, so each is tested for content first.
            case "$tmpl" in
              *"--v=${WANT_V}"*)
                if [ -n "$gen" ] && [ -n "$obs" ] && [ "$obs" = "$gen" ] \
                   && [ -n "$want" ] && [ -n "$avail" ] && [ -n "$upd" ] \
                   && [ "$avail" -ge "$want" ] && [ "$upd" -ge "$want" ]; then
                  echo "rollout complete: --v=${WANT_V} live, ${avail}/${want} available and updated"
                  break
                fi
                ;;
            esac
            sleep 5
          done

          echo
          echo "✅ OAuth server logLevel is now ${WANT}"
          {{- if .Values.authLogLevel.enabled }}
          echo
          echo "NOTE: Debug logging names every person who authenticates, and their LDAP DN and the"
          echo "      bind filter used. Those lines are readable by anyone who can read pod logs in"
          echo "      openshift-authentication. Turn it back off with authLogLevel.enabled=false when"
          echo "      you no longer need the capture."
          {{- end }}
        env:
        - name: HOME
          value: /tmp
        resources:
          {{- toYaml .Values.authLogLevel.resources | nindent 10 }}
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop: ["ALL"]
      securityContext:
        runAsNonRoot: true
        seccompProfile:
          type: RuntimeDefault
{{- end }}
```

New text:

```text
```

### Block 2 — charts/group-sync-dashboard/templates/auth-loglevel-revert-job.yaml

Retire the whole file. Empty New is the checker-compatible deletion payload; see deletion protocol.
Baseline: charts/group-sync-dashboard/templates/auth-loglevel-revert-job.yaml:1; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/templates/auth-loglevel-revert-job.yaml | edit -->

Old text:

```text
{{- if and .Values.authLogLevel.manage .Values.authLogLevel.revertOnUninstall }}
# Puts the oauth-server operand's log verbosity back on uninstall, via the authentication
# OPERATOR CR — `authentications.operator.openshift.io/cluster`, NOT the OAuth CR
# (`oauth.config.openshift.io/cluster`), which holds the identity providers and is untouched.
#
# WITHOUT THIS, `helm uninstall` leaves the cluster in Debug — the dashboard is gone, nothing is
# reading the logs any more, and the OAuth server carries on naming every person who authenticates
# along with their LDAP DN. Nobody would notice, because the thing that would have told you is the
# thing you just removed.
#
# pre-delete, so it runs while its ServiceAccount and ClusterRoleBinding still exist. Helm deletes
# release resources AFTER pre-delete hooks complete, which is why neither carries
# `helm.sh/resource-policy: keep` — see auth-loglevel-rbac.yaml.
apiVersion: batch/v1
kind: Job
metadata:
  name: {{ include "gsd.fullname" . }}-auth-loglevel-revert
  labels:
    {{- include "gsd.labels" . | nindent 4 }}
    app.kubernetes.io/component: auth-loglevel-revert
  annotations:
    helm.sh/hook: pre-delete
    helm.sh/hook-delete-policy: before-hook-creation,hook-succeeded
spec:
  backoffLimit: 0
  # Short and hard. An uninstall must not hang on this: the alternative to a timeout is a `helm
  # uninstall` that never returns, and a cluster left in Debug is recoverable by hand while a wedged
  # uninstall is not.
  activeDeadlineSeconds: {{ .Values.authLogLevel.revertDeadlineSeconds }}
  template:
    metadata:
      labels:
      # NOT gsd.selectorLabels. Those are the Service's and the PodDisruptionBudget's selector, and
      # a hook pod carrying them is matched by both: the Service routes to it while it runs (a pod
      # with no readiness probe is Ready as soon as its container starts), and the disruption
      # controller fails the PDB outright — measured on the reference cluster: "jobs.batch does not
      # implement the scale subresource", DisruptionAllowed=False, every drain blocked.
        app.kubernetes.io/name: {{ include "gsd.name" . }}
        app.kubernetes.io/instance: {{ .Release.Name }}
        app.kubernetes.io/component: auth-loglevel-revert
    spec:
      restartPolicy: Never
      serviceAccountName: {{ include "gsd.fullname" . }}-auth-loglevel
      containers:
      - name: revert-loglevel
        image: {{ .Values.authLogLevel.image.repository }}:{{ .Values.authLogLevel.image.tag }}
        imagePullPolicy: {{ .Values.authLogLevel.image.pullPolicy }}
        command:
        - /bin/bash
        - -c
        - |
          # NOT `set -e`. A pre-delete hook that fails BLOCKS the uninstall, and an operator trying
          # to remove this chart must never be held hostage by a best-effort tidy-up. Every failure
          # below is reported and then forgiven.
          set -uo pipefail

          CURRENT=$(oc get authentications.operator.openshift.io cluster \
                      -o jsonpath='{.spec.logLevel}' 2>/dev/null || true)
          echo "current logLevel: ${CURRENT:-<unset, i.e. Normal>}"

          if [ "${CURRENT:-Normal}" = "Normal" ]; then
            echo "already Normal — nothing to revert"
            exit 0
          fi

          # Reverts only what this chart is responsible for. If somebody set Debug for their own
          # reasons and separately installed this chart, we still put it back — because `manage:
          # true` is the operator declaring that this chart owns the setting. That is why `manage`
          # defaults to false: opting in is what transfers ownership.
          echo "reverting authentications.operator.openshift.io/cluster -> Normal"
          if oc patch authentications.operator.openshift.io cluster --type=merge \
               -p '{"spec":{"logLevel":"Normal"}}'; then
            echo "✅ reverted. The oauth-openshift pods will roll shortly."
          else
            echo "⚠️  could not revert the log level. The uninstall CONTINUES — put it back by hand:"
            echo "    oc patch authentications.operator.openshift.io cluster --type=merge \\"
            echo "      -p '{\"spec\":{\"logLevel\":\"Normal\"}}'"
          fi
          exit 0
        env:
        - name: HOME
          value: /tmp
        resources:
          {{- toYaml .Values.authLogLevel.resources | nindent 10 }}
        securityContext:
          allowPrivilegeEscalation: false
          readOnlyRootFilesystem: true
          capabilities:
            drop: ["ALL"]
      securityContext:
        runAsNonRoot: true
        seccompProfile:
          type: RuntimeDefault
{{- end }}
```

New text:

```text
```

### Block 3 — charts/group-sync-dashboard/templates/auth-loglevel-rbac.yaml

Retire the whole file. Empty New is the checker-compatible deletion payload; see deletion protocol.
Baseline: charts/group-sync-dashboard/templates/auth-loglevel-rbac.yaml:1; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/templates/auth-loglevel-rbac.yaml | edit -->

Old text:

```text
{{- if .Values.authLogLevel.manage }}
{{- if eq (include "gsd.serviceAccountName" .) (printf "%s-auth-loglevel" (include "gsd.fullname" .)) }}
{{- fail (printf "serviceAccount.name is %q, which collides with the log-level Job's own ServiceAccount.\n  That would render two same-named ServiceAccounts, run the DASHBOARD as that identity, and hand it\n  the `patch` grant on authentications.operator.openshift.io — defeating the separation this whole\n  feature is shaped around. Choose a different serviceAccount.name." (include "gsd.serviceAccountName" .)) }}
{{- end }}
# The ONLY write grant this chart creates, and it is deliberately not on the dashboard.
#
# `rbac.yaml` states "NO WRITE VERB ON ANYTHING THE DASHBOARD REPORTS ON" and five documents cite
# that line. Putting `patch` on the dashboard's ServiceAccount to enable a logging prerequisite
# would falsify all of them for a cosmetic feature. This ServiceAccount exists only for the
# hook Jobs beside it, is used by nothing at runtime, and disappears entirely with
# `authLogLevel.manage=false`.
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {{ include "gsd.fullname" . }}-auth-loglevel
  labels:
    {{- include "gsd.labels" . | nindent 4 }}
    app.kubernetes.io/component: auth-loglevel
  # NO resource-policy: keep, deliberately. Helm runs pre-delete hooks BEFORE it deletes the
  # release's resources, so this ServiceAccount is still present when the revert Job authenticates
  # with it. `keep` would orphan a cluster-scoped RBAC pair on every uninstall, forever — which is
  # a worse outcome than the problem it looks like it solves.
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: {{ include "gsd.fullname" . }}-auth-loglevel
  labels:
    {{- include "gsd.rbacLabels" . | nindent 4 }}
rules:
  # `get` and `patch` on ONE named object. resourceNames is honoured for both — unlike `create` and
  # `list`, where a request carries its name in the body or not at all, so a name-pinned rule never
  # authorises them. That distinction matters here: without the pin this would be patch on every
  # object in the group, which includes the cluster's whole authentication configuration.
  #
  # No `update`: --type=merge is a PATCH. No `list`, no `watch`, and no other resource.
  - apiGroups: ["operator.openshift.io"]
    resources: ["authentications"]
    resourceNames: ["cluster"]
    verbs: ["get", "patch"]
  # Read-only, and only to answer "has the rollout finished?" — see the wait loop in the Job, and
  # why `oc rollout status` cannot be trusted for it.
  # PINNED to the one Deployment the wait loop reads. Unpinned this was `get deployments` on every
  # namespace on the cluster — verified with `oc auth can-i --as=` the Job's own ServiceAccount: yes
  # in kube-system, openshift-console and everywhere else. resourceNames is honoured for `get`.
  #
  # A ClusterRole rather than a Role in openshift-authentication, deliberately: a Role would have the
  # chart creating an object in a namespace it does not own, which breaks ArgoCD pruning and leaves
  # something behind that no release manifest accounts for.
  - apiGroups: ["apps"]
    resources: ["deployments"]
    resourceNames: ["oauth-openshift"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: {{ include "gsd.fullname" . }}-auth-loglevel
  labels:
    {{- include "gsd.rbacLabels" . | nindent 4 }}
  # No `keep` here either — same reason as the ServiceAccount above.
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: {{ include "gsd.fullname" . }}-auth-loglevel
subjects:
  - kind: ServiceAccount
    name: {{ include "gsd.fullname" . }}-auth-loglevel
    namespace: {{ .Release.Namespace }}
{{- end }}
```

New text:

```text
```

### Block 4 — charts/group-sync-dashboard/templates/login-capture-rbac.yaml

Remove the retired path.
Baseline: charts/group-sync-dashboard/templates/login-capture-rbac.yaml:56; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/templates/login-capture-rbac.yaml | edit -->

Old text:

```text
{{- else if .Values.loginCapture.enabled }}
# Lets the DASHBOARD read the oauth-server's logs, so it can record who logged in and when.
#
# This is a READ, and it is the dashboard's own ServiceAccount — unlike the log-level Jobs beside it,
# which write and therefore run under their own identity. `rbac.yaml`'s "NO WRITE VERB" invariant is
# untouched: nothing here grants one.
#
# ── WHY A Role IN openshift-authentication, AND NOT A ClusterRole ─────────────────────────────────
# Because `pods/log` in a ClusterRole means EVERY POD ON THE CLUSTER. Pod logs routinely carry tokens,
# connection strings and customer data, so a cluster-wide log read is one of the widest grants a
# read-only application can hold — far wider than the group and binding reads this dashboard exists
# for. Scoping it to the one namespace whose logs it actually parses is the difference between "can
# read the OAuth server's logs" and "can read anything anyone logs".
#
# The cost is real and stated rather than hidden: this creates two objects in a namespace the chart
# does not own. They carry the release's labels so they can be found, and `helm uninstall` removes
# them like any other release resource — but an ArgoCD Application syncing this chart will show them
# as living outside its destination namespace, and a cluster policy that forbids writing to
# `openshift-*` namespaces will reject them. Both are better problems than a cluster-wide log grant.
#
# ── WHY BOTH pods AND pods/log ────────────────────────────────────────────────────────────────────
# There is no Deployment log subresource — verified:
#   GET /apis/apps/v1/namespaces/openshift-authentication/deployments/oauth-openshift/log
#     -> "the server could not find the requested resource"
# `oc logs deploy/x` only LOOKS like combined logs: the client resolves the Deployment to its
# ReplicaSet to its Pods and reads each one. So the dashboard must do the same — `list` pods to
# discover them (production runs 2-3 oauth replicas, and every roll replaces them), then `get`
# pods/log per pod. Neither verb alone is enough.
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: {{ include "gsd.fullname" . }}-login-capture
  namespace: {{ .Values.loginCapture.namespace }}
  labels:
    {{- include "gsd.rbacLabels" . | nindent 4 }}
    app.kubernetes.io/component: login-capture
rules:
  # Discovery. `list` only — no watch, and no get on a named pod, because pod names are generated and
  # change on every roll.
  - apiGroups: [""]
    resources: ["pods"]
    verbs: ["list"]
  # The logs themselves. A subresource, so it cannot be pinned by resourceName in any useful way:
  # the names are generated. The namespace scope IS the boundary here.
  - apiGroups: [""]
    resources: ["pods/log"]
    verbs: ["get"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: {{ include "gsd.fullname" . }}-login-capture
  namespace: {{ .Values.loginCapture.namespace }}
  labels:
    {{- include "gsd.rbacLabels" . | nindent 4 }}
    app.kubernetes.io/component: login-capture
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: Role
  name: {{ include "gsd.fullname" . }}-login-capture
subjects:
  # The dashboard's own ServiceAccount. This is the ONE grant it holds outside its own namespace, and
  # it is read-only.
  - kind: ServiceAccount
    name: {{ include "gsd.serviceAccountName" . }}
    namespace: {{ .Release.Namespace }}
{{- end }}
```

New text:

```text
{{- end }}
```

### Block 5 — charts/group-sync-dashboard/templates/login-capture-rbac.yaml

Remove the retired path.
Baseline: charts/group-sync-dashboard/templates/login-capture-rbac.yaml:10; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/templates/login-capture-rbac.yaml | edit -->

Old text:

```text
# the journal. Read-only, and far wider than the namespaced pods/log Role the pod-log source
# uses; values.yaml says why it is worth it and why it is opt-in. `resourceNames` narrows it to
```

New text:

```text
# the journal. Read-only and cluster-wide. `resourceNames` narrows it to
```

### Block 6 — charts/group-sync-dashboard/templates/login-capture-rbac.yaml

Remove the retired path.
Baseline: charts/group-sync-dashboard/templates/login-capture-rbac.yaml:15; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/templates/login-capture-rbac.yaml | edit -->

Old text:

```text
# Still no write verb: rbac.yaml's "NO WRITE VERB" invariant is untouched, and
# tests/test_chart_strategy.py::TestLoginCaptureReadsOneNamespaceOnly still holds — this role
# grants no pods and no pods/log anywhere.
```

New text:

```text
# No pods or pods/log grant, and no authentication-operator write.
```

### Block 7 — charts/group-sync-dashboard/templates/_helpers.tpl

Remove the retired path.
Baseline: charts/group-sync-dashboard/templates/_helpers.tpl:594; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->

Old text:

```text
# pod-log | audit-log, validated where it is resolved, and the ONE place the two switches that
# interact are reconciled: audit-log makes Debug unnecessary, so a render that asks for both is a
# contradiction and is refused — never resolved by quietly rolling the OAuth server.
{{- define "gsd.loginCaptureSource" -}}
{{- $lc := .Values.loginCapture | default dict -}}
{{- $s := "pod-log" -}}
{{- if and (hasKey $lc "source") (not (kindIs "invalid" $lc.source)) -}}{{- $s = trim (toString $lc.source) -}}{{- end -}}
{{- if not (has $s (list "pod-log" "audit-log")) -}}
{{- fail (printf "loginCapture.source %q is not one of pod-log, audit-log." $s) -}}
{{- end -}}
{{- if and (eq $s "audit-log") ($lc.enabled) ((.Values.authLogLevel | default dict).enabled) -}}
{{- fail "loginCapture.source=audit-log and authLogLevel.enabled=true contradict each other: the audit log names every login at the DEFAULT verbosity, so Debug on the authentication operator CR buys nothing and costs an OAuth roll. The chart will not roll the OAuth server as a side effect of a read setting. Retire Debug in order:\n  1. --set loginCapture.source=audit-log --set authLogLevel.manage=true --set authLogLevel.enabled=false   (converges the cluster to Normal; one last roll — a login outage at one replica)\n  2. --set authLogLevel.manage=false once the rollout has finished.\nPass your whole values file each time (see the chart README)." -}}
{{- end -}}
{{- $s -}}
{{- end -}}

```

New text:

```text
# Audit-only source; validate even when capture is disabled.
{{- define "gsd.loginCaptureSource" -}}
{{- if hasKey .Values "authLogLevel" -}}
{{- fail "authLogLevel has been removed: remove the entire authLogLevel stanza (including false values), set loginCapture.source=audit-log, and manually restore the authentication operator to Normal as described in the chart README migration note." -}}
{{- end -}}
{{- $lc := .Values.loginCapture | default dict -}}
{{- if hasKey $lc "namespace" -}}
{{- fail "loginCapture.namespace has been removed: remove this key and use loginCapture.source=audit-log with loginCapture.auditLog.nodeNames or nodeSelector." -}}
{{- end -}}
{{- $s := "audit-log" -}}
{{- if hasKey $lc "source" -}}{{- $s = trim (toString $lc.source) -}}{{- end -}}
{{- if ne $s "audit-log" -}}
{{- fail (printf "loginCapture.source %q is unsupported: pod-log has been removed; set loginCapture.source=audit-log, remove authLogLevel, and manually restore the authentication operator to Normal (chart README migration note)." $s) -}}
{{- end -}}
{{- $s -}}
{{- end -}}

```

### Block 8 — charts/group-sync-dashboard/templates/_helpers.tpl

Remove the retired live path; keep audit capture and stored history.
Baseline: charts/group-sync-dashboard/templates/_helpers.tpl:490; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->

Old text:

```text
{{- fail (printf "logLevel %q is not a log level. Use one of DEBUG, INFO, WARNING, ERROR, CRITICAL (case does not matter).\n\nIf you are trying to raise the OAUTH-SERVER's verbosity so the Logins tab has something to read, that is the chart's `authLogLevel` value, not this one — a different setting on a different object.\n\nRefused here rather than passed through, because a release value can be corrected before anything is deployed. The app itself is more forgiving with a directly supplied GSD_LOG_LEVEL — it runs at INFO and logs a warning — so this is the stricter of two boundaries, not the only one." (toString $raw)) -}}
```

New text:

```text
{{- fail (printf "logLevel %q is not a log level. Use one of DEBUG, INFO, WARNING, ERROR, CRITICAL (case does not matter). Login capture uses the audit log at default OAuth verbosity; see docs/LOGIN_CAPTURE_QUICKCHECK.md." (toString $raw)) -}}
```

### Block 9 — charts/group-sync-dashboard/values.yaml

Remove the retired path.
Baseline: charts/group-sync-dashboard/values.yaml:1551; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```text
# Grants the DASHBOARD a read of the oauth-server's login records, which is where "who logged in"
# comes from. Read-only, on the dashboard's own ServiceAccount. The grant follows `source` below:
#
#   audit-log (the default since 0.52.0) — a ClusterRole on `get nodes/proxy`, plus `list
#     nodes` unless auditLog.nodeNames pins the nodes. Names the person at the DEFAULT
#     verbosity: nothing to enable, no OAuth roll. Its cost is stated at `source` below.
#   pod-log (deprecated, removal tracked in #321) — a Role on `pods/log` in ONE namespace,
#     never a ClusterRole: cluster-wide it would read EVERY pod's logs — tokens, connection
#     strings, customer data. It NEEDS authLogLevel.enabled=true TO SEE ANYTHING — measured:
#     zero occurrences of "succeeded for login" until the level is Debug — and that write
#     lives on a separate identity. The Role and RoleBinding land in a namespace the chart
#     does not own: an ArgoCD Application shows them outside its destination, and a policy
#     forbidding writes to `openshift-*` rejects them.
#
# ON by default since chart 0.14.0, with audit-log as its source since 0.52.0: the Users tab's login
# columns need it. Set false where the nodes/proxy grant is unacceptable.
loginCapture:
  enabled: true

  # WHICH LOG TO READ. Two sources, and the whole point of the second is what it does not need:
  #
  #   pod-log     (deprecated, #321) the oauth-server pods' logs, through a Role in
  #               openshift-authentication on `pods` and `pods/log`. Names a person ONLY at spec.logLevel: Debug on the
  #               authentication operator CR (authLogLevel below), which rolls the OAuth server —
  #               a login outage at one replica — and history dies with every pod. What it has that
  #               the audit log does not: the LDAP result code and AD sub-code behind a refusal.
  #   audit-log   /var/log/oauth-server/audit.log on the control-plane nodes, read through the API
  #               server's node proxy (what `oc adm node-logs --path=oauth-server/audit.log` does).
  #               Written at every audit profile but None, at the DEFAULT verbosity: no Debug, no
  #               roll, no outage, and a first read backfills as far back as the rotated files
  #               reach (audit-log-maxsize 100 MB x maxbackup 10 — by volume, not by days; one lab
  #               cluster held sixteen months). It records allow/deny/error and the username,
  #               never a cause. The identity provider is on the path for browser logins and is
  #               resolved from the User's Identity otherwise, so a CLI kubeadmin login is still
  #               labelled break-glass through htpasswdProviders.
  #
  # THE COST OF audit-log, STATED: the grant is a ClusterRole with `get` on `nodes/proxy`, which
  # is READ ACCESS TO EVERYTHING THE KUBELET SERVES OVER GET on those nodes — every container's
  # logs on them (/containerLogs), the kube-apiserver and openshift-apiserver audit logs, the
  # journal — and `list nodes` to find the control-plane nodes. That is categorically wider than
  # a namespaced pods/log Role, and it is a standing capability.
  #
  # IT IS NEVERTHELESS THE DEFAULT, by decision (2026-09-23). Capturing who logged in is what this
  # feature is FOR, and the audit log is the only source that does it without raising the OAuth
  # server's verbosity — which rolls it, a login outage at one replica. The previous default paired
  # `enabled: true` with `source: pod-log` while `authLogLevel` stayed off, so a plain install
  # captured no named login at all: the chart shipped a feature switched on and unable to work.
  # Between a wide read-only grant an operator can see and narrow, and a feature that silently does
  # nothing, the grant is the honest choice. TURN IT OFF with `enabled: false` if the grant is
  # unacceptable — that is the override, not a source that cannot deliver.
  #
  # NARROW IT with auditLog.nodeNames below (resourceNames on nodes/proxy, and no list at all).
  # That is the recommended production shape: name the control-plane nodes and the cluster-wide
  # `list` disappears entirely.
  #
  # HOW IT MEETS authLogLevel: with source audit-log, Debug is unnecessary. The chart REFUSES
  # source=audit-log together with authLogLevel.enabled=true — it will not roll the OAuth server
  # as a side effect of a read setting — and the retirement order is the README's two-step:
  #   1. loginCapture.source=audit-log  authLogLevel.manage=true   authLogLevel.enabled=false
  #      (the Job converges the cluster to Normal; one last roll)
  #   2. authLogLevel.manage=false once the rollout has finished.
  # The audit log is the authoritative record from then on; pod-log rows already stored are kept,
  # and an audit event that corresponds to one is linked to it rather than recorded twice.
  #
  # DEPRECATION: `pod-log` and the whole `authLogLevel` Job machinery are on their way out — the
  # audit log is the supported path. Tracked in #321 so the removal is a decision, not a drift.
  #
  # HOW THE AUDIT PATH WORKS end to end — the node-proxy request, what it needs on a REMOTE cluster
  # and which chart grants it, what counts as a login, and a worked example you can run against the
  # lab's mock cluster: docs/AUDIT_LOG_CAPTURE.md
  source: audit-log

```

New text:

```text
# Grants the dashboard get nodes/proxy, plus list nodes unless auditLog.nodeNames is set.
# This is read access to everything the kubelet serves over GET on those nodes, including
# other containers' logs and the journal. Set enabled=false if that grant is unacceptable.
# Audit capture names the person at default OAuth verbosity, with no OAuth rollout.
# It records allow/deny/error, but no LDAP result code or AD sub-code (such as account locked).
# First read backfills available rotated files within retentionDays; pin nodeNames to narrow RBAC.
# Stored pod-log rows and their causes remain readable and are linked to matching audit events.
# See docs/AUDIT_LOG_CAPTURE.md for the local/remote grant and worked example.
loginCapture:
  enabled: true
  # The only supported source. Old pod-log values fail with migration guidance.
  source: audit-log

```

### Block 10 — charts/group-sync-dashboard/values.yaml

Remove the retired path.
Baseline: charts/group-sync-dashboard/values.yaml:1641; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```text
  # Where the oauth-server runs. Only change this if your cluster is unusual; it is the fixed
  # namespace OpenShift installs the OAuth server into.
  namespace: openshift-authentication

```

New text:

```text
```

### Block 11 — charts/group-sync-dashboard/values.yaml

Remove the retired path.
Baseline: charts/group-sync-dashboard/values.yaml:1718; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```text
# ---------------------------------------------------------------------------
# DEPRECATED — oauth-server log verbosity  (OAuth Debug, pod-log source only)
# ---------------------------------------------------------------------------
# Login capture reads the oauth-server AUDIT LOG by default (`loginCapture.source: audit-log`),
# which names the person at the default verbosity: nothing here is needed for it. This stanza raises
# the OAuth server to Debug for the deprecated pod-log source, and remains only to move a cluster
# left at Debug back to Normal (the two-step below). Do not enable it on a new install.
# Removal: #321.
#
# The oauth-openshift server's POD LOG only names the person logging in when the AUTHENTICATION
# OPERATOR CR — `authentications.operator.openshift.io/cluster` — has `spec.logLevel: Debug`.
#
# NOT the OAuth CR. `oauth.config.openshift.io/cluster` is the object that holds the identity
# providers, and this feature never touches it; there is also a THIRD, one word apart:
# `authentications.config.openshift.io/cluster`, which holds `type`/`serviceAccountIssuer`.
# And within the operator CR, `logLevel` (the operand's verbosity) is not `operatorLogLevel`
# (the operator's own) — patching the latter would change nothing this needs. At `Normal` the line
# is not emitted at all — measured: zero occurrences of "succeeded for login" until this is on. So
# this section is the prerequisite for the pod-log source, and nothing more.
#
# TWO SWITCHES, ON PURPOSE:
#
#   manage: false            nothing renders, no RBAC, this chart never touches the cluster's setting
#   manage: true  enabled: t a hook Job sets Debug
#   manage: true  enabled: f the same Job sets Normal  <- this is what makes "turn it off" work
#
# Helm does not run a Job you merely stopped rendering, so a one-way enable Job would strand the
# cluster in Debug the moment somebody flipped the flag back and saw nothing happen.
#
# `manage: true` is the operator DECLARING THAT THIS CHART OWNS the cluster's log level. That is why
# it defaults to false: opting in is what transfers ownership, and the uninstall revert below then
# has the standing to put it back.
#
# Both stay false under the chart's on-by-default rule (0.14.0), on purpose: the Debug level is a
# cluster-wide write that rolls the OAuth server, and the oauth-server audit log
# (`loginCapture.source: audit-log`, the default since 0.52.0) has replaced it as the way login
# lines are obtained. This block serves only the deprecated pod-log source and the move of a cluster
# left at Debug back to Normal; its removal is tracked in #321.
authLogLevel:
  manage: false
  enabled: false

  # ⚠️  CHANGING THIS ROLLS THE OAUTH SERVER, WHICH IS A LOGIN OUTAGE ON A SINGLE-REPLICA CLUSTER.
  # The authentication operator replaces deploy/oauth-openshift when logLevel changes; until the new
  # pod is Ready, `authentication` reports "OAuthServerDeploymentAvailable: no oauth-openshift pods
  # available on any node" and logins fail. Measured on a 1-replica CRC cluster: the replacement pod
  # sat Pending (node at 91% CPU requests) and a second application watching the same cluster logged
  # `HTTP 503 on /apis/user.openshift.io/v1/groups` while it happened.
  #
  # Check the blast radius first, and use a maintenance window if the answer is 1:
  #   oc get deploy oauth-openshift -n openshift-authentication -o jsonpath='{.spec.replicas}{"\n"}'
  #
  # This applies to turning it OFF as much as ON — both directions are a logLevel change.

  # Puts the level back to Normal on `helm uninstall`, via a pre-delete Job.
  #
  # LEAVE THIS ON. Without it, removing the dashboard leaves the OAuth server naming every person
  # who authenticates — along with their LDAP DN and the bind filter — with nothing left watching
  # the logs and nobody aware it is happening. The one thing that would have told you is the thing
  # you just uninstalled.
  revertOnUninstall: true

  # WHAT DEBUG ACTUALLY EXPOSES, so this is a decision and not a shrug: the lines carry the username
  # of everyone who authenticates, their resolved LDAP DN, and the bind filter used. Anyone who can
  # read pod logs in openshift-authentication can read them. Turn it off when the capture is not
  # needed; that is what the toggle is for.

  # `oc` is all the Jobs need, and this is the IN-CLUSTER imagestream every OpenShift cluster ships
  # — not registry.redhat.io.
  #
  # MEASURED: `registry.redhat.io/openshift4/ose-cli:latest` was the first choice and it failed here
  # with ErrImagePull ("copying config: context canceled") after 40s. It needs registry.redhat.io
  # credentials, it is a large image, and `:latest` is unpinned — three ways for a prerequisite Job
  # to fail on somebody else's cluster. The internal imagestream is already mirrored by the release
  # payload, so there is nothing to authenticate and usually nothing to pull.
  #
  # OpenShift-specific, deliberately: this whole section patches an OpenShift operator CR, so it has
  # no meaning on plain Kubernetes. Override it if your cluster mirrors elsewhere.
  image:
    repository: image-registry.openshift-image-registry.svc:5000/openshift/cli
    tag: latest
    pullPolicy: IfNotPresent

  # How long to wait for the operator to roll the oauth pods after the patch.
  #
  # The Job does NOT use `oc rollout status` for this, and that is measured rather than cautious: on
  # the reference cluster it returned "successfully rolled out" about THIRTY SECONDS BEFORE the
  # rollout began, because the old ReplicaSet was still current and complete at that moment. The Job
  # polls the Deployment's observedGeneration and available/updated replicas instead.
  #
  # A timeout here is NOT a failure — the patch has landed, which is the Job's actual work, and the
  # rollout is the operator's to finish. Failing would fail `helm upgrade` over somebody else's slow
  # reconcile.
  waitSeconds: 180

  # Wall clock on the whole attempt, so a Job that cannot reach the API server cannot hold up an
  # upgrade indefinitely. Must stay above waitSeconds.
  activeDeadlineSeconds: 300

  # Deliberately short. An uninstall must not hang: a cluster left in Debug is fixable by hand, a
  # wedged `helm uninstall` is not.
  revertDeadlineSeconds: 120

  backoffLimit: 2

  resources:
    requests:
      cpu: 10m
      memory: 64Mi
    limits:
      cpu: 200m
      memory: 256Mi

```

New text:

```text
```

### Block 12 — charts/group-sync-dashboard/values.yaml

Remove the retired path.
Baseline: charts/group-sync-dashboard/values.yaml:557; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```text
# NOT TO BE CONFUSED WITH `authLogLevel` BELOW, which is a different setting on a different object:
# it raises the oauth-server's own verbosity, which is what makes that server EMIT the login lines
# this dashboard reads. If the Logins tab is empty, that is the one to check — not this one.
```

New text:

```text
# Login capture reads the audit log at default OAuth verbosity; logLevel is app logging only.
```

### Block 13 — charts/group-sync-dashboard/values.yaml

Update the surviving contract.
Baseline: charts/group-sync-dashboard/values.yaml:802; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```text
  # authLogLevel note explains why not registry.redhat.io). Override on a cluster that mirrors
```

New text:

```text
  # release payload avoids a separate registry.redhat.io pull). Override on a cluster that mirrors
```

### Block 14 — charts/group-sync-dashboard/templates/configmap.yaml

Remove the retired path.
Baseline: charts/group-sync-dashboard/templates/configmap.yaml:165; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/templates/configmap.yaml | edit -->

Old text:

```text
    # THE GRANT AND THE MODULE ARE TWO DIFFERENT THINGS, and until now only the grant was wired.
    # `loginCapture.enabled` rendered the Role that lets the pod read oauth-server logs, and nothing
    # told the application to read them: the setting the code looks for is this ConfigMap key, so
    # capture stayed off with the flag on and the permission in place. Caught on the cluster, where
    # /api/.../logins answered `enabled: false` on a release built from `enabled: true`.
    loginCaptureEnabled: {{ .Values.loginCapture.enabled }}
    loginCaptureNamespace: {{ .Values.loginCapture.namespace | quote }}
    # Which log capture reads. Through the helper, which is also where source=audit-log and
    # authLogLevel.enabled=true are refused as a contradiction.
```

New text:

```text
    # The module and its read grant share the values switch. The helper refuses removed keys.
    loginCaptureEnabled: {{ .Values.loginCapture.enabled }}
```

### Block 15 — charts/group-sync-dashboard/templates/NOTES.txt

Update the surviving contract.
Baseline: charts/group-sync-dashboard/templates/NOTES.txt:164; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/templates/NOTES.txt | edit -->

Old text:

```text
needed; if authLogLevel.manage is still true with enabled=false, the Job is converging the
cluster back to Normal and you can set manage=false once the rollout has finished.
```

New text:

```text
needed. Clusters left at Debug must be restored manually; see the chart README migration note.
```

### Block 16 — local-development/gsd/logincapture.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/gsd/logincapture.py:1; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/logincapture.py | edit -->

Old text:

```python
"""Read the oauth-server's logs and record who logged in.

Its own module, not part of poller.py, because it is a separable concern with a separable failure mode:
capture can be off, forbidden, or broken while group polling is perfectly healthy, and nothing here may
take the poll down with it.

WHAT MAKES THIS WORK AT ALL. The lines naming a person exist only at `spec.logLevel: Debug` on
`authentications.operator.openshift.io/cluster` — the authentication OPERATOR CR, not the OAuth CR. At
the default verbosity they are not written, so with capture on and Debug off this reads real logs and
finds nothing, which is correct rather than broken. See docs/LOGIN_CAPTURE_QUICKCHECK.md.

AND WHAT IT CANNOT DO. Pod logs live as long as the pod. Every oauth roll — a cluster upgrade, a node
drain, a toggle of that very setting — starts the window again, and nothing before capture was enabled
was ever written down anywhere. So this accumulates a durable record GOING FORWARD and cannot
reconstruct the past. `login_capture_status.started_at` exists so the UI can say when watching began
rather than letting an empty table read as "nobody logged in".
"""

from __future__ import annotations

import logging

from .config import ClusterConfig, Settings
from .kube import ClusterClient, ClusterError
from .loginlog import ATTEMPT_WINDOW, LoginAttempt, parse, parse_timestamp
from .storage import StorageBackend
from .timeutil import now_iso

log = logging.getLogger(__name__)

# How far back to read when there is NO watermark for a pod — a first sight, or the first cycle after a
# restart. Deliberately modest: the alternative is reading a pod's entire history on every fresh start,
# which on a long-lived pod at Debug is a large read for lines that are almost all already recorded.
# One hour covers a restart and a rollout; anything older than that on a first sight is accepted as
# lost, which is the same bargain §1.8 of the design already makes.
FIRST_SIGHT_SECONDS = 3600

# Re-read this far behind the watermark on every cycle. An attempt is SEVERAL lines and they can
# straddle two reads: the success line may land in the next window from the failure lines that precede
# it. Re-reading the overlap means the whole attempt is present in one parse, and the dedup key makes
# the repeats free. Cheap insurance — it is one extra minute of lines per pod per cycle.
OVERLAP_SECONDS = 60

# Do not advance the watermark to the newest line seen; hold it back by this much. The newest lines of
# a live log are the ones most likely to be mid-attempt — the failure lines written, the success line
# not yet. Settling behind the tip means an attempt is only ever recorded once its lines have stopped
# arriving, and the overlap above then re-reads that settled region anyway.
SETTLE_SECONDS = 30


def event_dict(attempt: LoginAttempt, pod_name: str, observed_at: str) -> dict:
    """A LoginAttempt plus the two things the store needs and the parser cannot know.

    `pod_name` is required because it is IN the dedup key, and LoginAttempt deliberately does not carry
    it — the parser takes text and knows nothing about where it came from, which is what makes it
    testable without a cluster. Public rather than private so tests can build rows the same way the
    capture loop does, instead of hand-assembling dicts that drift from it.

    The timestamp format is fixed here, once. Microsecond precision with a literal Z, because it is
    part of the unique key: two attempts one microsecond apart must not collide, and a format that
    varied between writer and reader would make the key match rows it should not.
    """
    return {
        "pod_name": pod_name,
        "user_name": attempt.user_name,
        "outcome": attempt.outcome,
        "at": attempt.at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "provider": attempt.provider,
        "ldap_result_code": attempt.ldap_result_code,
        "detail": attempt.detail,
        "observed_at": observed_at,
    }


def _settle_horizon(lines: list[str]) -> str | None:
    """The newest log instant old enough to be called settled, or None if none is yet.

    A READ CURSOR OVER LOG TIME, NOT OVER ATTEMPTS. The first shipped version took only parsed
    attempts, which stalls on a pod that logs plenty and authenticates nobody: the watermark never
    moves, sinceSeconds grows by the full poll interval every cycle for the life of the pod, and
    once the window outgrows the byte cap the newest lines are deferred every cycle while capture
    still stamps itself live. Any timestamped line proves the log was read through that instant,
    so any timestamped line may advance the cursor — without inventing a login record.

    RELATIVE TO NOW, not to the newest line in the batch — and that distinction is a bug I shipped
    into the first draft. Measuring from the newest meant a BURST of logins inside SETTLE_SECONDS
    made every one of them "unsettled" relative to its own peers, so the watermark never advanced
    at all: the same window was re-read forever. Caught by the healthy-path test writing zero
    watermarks. Measuring from now is what the horizon is actually for: a line stops being at risk
    of belonging to a still-arriving attempt once wall-clock has moved past it.
    """
    from datetime import UTC, datetime
    cutoff = datetime.now(UTC).timestamp() - SETTLE_SECONDS
    stamps = [ts for raw in lines if (ts := parse_timestamp(raw)) is not None
              and ts.timestamp() <= cutoff]
    if not stamps:
        return None
    return max(stamps).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _recordable(attempts: list[LoginAttempt]) -> list[LoginAttempt]:
    """Only the attempts old enough that every one of their lines must already have arrived.

    An attempt read MID-FLIGHT concludes on partial evidence: the provider-chain `failed` line is
    in the read, the success that follows it is not yet written, and the parse honestly returns a
    failure that never happened. The dedup key cannot collapse that with the finished attempt —
    the outcome differs — so the sliced row would sit beside the real one forever, and the page
    would show a failed login that is provider-order noise. Withholding an attempt until
    wall-clock has passed its whole window costs at most one cycle of latency, and nothing is
    lost: the watermark (same cutoff, minus the window) never advances past a withheld attempt,
    and OVERLAP_SECONDS exceeds SETTLE_SECONDS plus the attempt window, so the next read has the
    whole attempt again.
    """
    from datetime import UTC, datetime, timedelta
    cutoff = datetime.now(UTC) - timedelta(seconds=SETTLE_SECONDS) - ATTEMPT_WINDOW
    return [a for a in attempts if a.at <= cutoff]


def _not_clipped(attempts: list[LoginAttempt], window_start: datetime) -> list[LoginAttempt]:
    """Only the attempts that cannot have had earlier lines cut off by the window's leading edge.

    THE MIRROR OF `_recordable`, FOR THE OTHER END OF THE READ. That one distrusts the newest lines
    because the rest of an attempt may not have been written yet; this distrusts the oldest, because
    the rest of it may lie behind the window. Both failures look the same from here — a parse that
    concludes on part of an attempt — and only one of them had a guard.

    What it prevents, measured: a window opening in the 1.167 ms between a bind error and its verdict
    parses the verdict alone, so the login the previous cycle recorded as `bad_password` stamped at the
    cause is recorded AGAIN as `failed` stamped at the verdict. `at` and `outcome` are both in
    UNIQUE(cluster_id, pod_name, user_name, at, outcome), so nothing collapses them and the page
    reports one person's single login twice — once with a reason and once without. The boundary is
    reachable by this module's own arithmetic: it sits at `watermark - OVERLAP_SECONDS` and sweeps
    forward a cycle at a time, so it crosses every instant in the log eventually.

    An attempt's lines span at most ATTEMPT_WINDOW, so once `at` is further than that from the edge no
    unseen line can belong to it — anything earlier would have been inside the window and parsed.

    WHAT THIS DELIBERATELY GIVES UP. A withheld attempt is normally safe because the overlap re-reads
    it, but the watermark advances to `now - SETTLE_SECONDS` regardless, which is ahead of this edge —
    so an attempt dropped here is dropped for good, not deferred. In the ordinary case that costs
    nothing: the edge sits OVERLAP_SECONDS behind the watermark, so anything near it was fully inside
    an earlier cycle's window and is already recorded. It costs a row in two cases — a first sight,
    where the edge is FIRST_SIGHT_SECONDS back and the hour boundary is already declared lost, and a
    restart that lands the new edge within one second of an attempt the previous process had withheld.
    Losing a row there is the trade this module makes everywhere else: an absent record beats a false
    one, and the false one here is a second row contradicting the first about a named person.
    """
    edge = window_start + ATTEMPT_WINDOW
    return [a for a in attempts if a.at > edge]


def capture_once(
    store: StorageBackend,
    cluster: ClusterConfig,
    settings: Settings,
    elector=None,
    timeout: float = 15.0,
    signals=None,
) -> int:
    """One capture pass over one cluster. Returns events recorded. NEVER raises for cluster problems.

    ── THE LEADERSHIP RECHECK, AND WHY IT IS WHERE IT IS ─────────────────────────────────────────────
    `poller.py` says of its lease, in its own words, that it is "BEST-EFFORT admission control, NOT a
    write fence", and `_run_cluster` checks it once per cycle. That is fine for group polling and not
    fine here, because this reads logs over the network: the check can pass, the read can block, the
    lease can expire and pass to another replica, and the old leader's read can then return and write.
    Codex named the sequence exactly — leader check true → log GET blocks → lease lost → new leader
    starts → old GET returns → old leader records events and watermark.

    So leadership is rechecked IMMEDIATELY BEFORE the write transaction, which narrows the window from
    "the length of a log read" to "the few instructions between the check and the INSERT". It does not
    close it, and this comment exists so nobody later mistakes it for a fence: closing it needs a
    fencing token the lease does not provide. What makes the residual window tolerable is the dedup
    key — two leaders writing the same lines produce the same rows, and INSERT OR IGNORE collapses
    them. The watermark is the part that could regress, and `set_login_watermark` takes max() precisely
    so a late write from a demoted leader cannot rewind it.
    """
    if not settings.login_capture_enabled:
        # DEBUG, not INFO: this is a configuration state rather than an event, so at INFO it would
        # repeat once per cluster per cycle forever and say nothing new. But it must be sayable
        # SOMEWHERE — "the Logins tab is empty" and "capture is switched off" are the same symptom,
        # and this is the only line that tells them apart.
        log.debug("%s: login capture is disabled, so no oauth-server logs are read and the Logins "
                  "tab will stay empty; set loginCapture.enabled=true to change that", cluster.name)
        return 0

    if settings.login_capture_source == "audit-log":
        # The second source (docs/DESIGN_login_capture.md): same store, same status row, same
        # retention, a different reader. Dispatched here so the poller keeps one call site and
        # the never-take-the-poll-down contract is one contract.
        from .auditlog import capture_once as capture_audit_once
        return capture_audit_once(store, cluster, settings, elector, timeout, signals)

    ns = settings.login_capture_namespace
    client = ClusterClient(cluster, timeout=timeout)

    try:
        pods = client.fetch_oauth_pods(ns)
    except ClusterError as exc:
        log.warning("%s: login capture could not list pods: %s — group data is unaffected",
                    cluster.name, exc.message)
        return 0
    if pods is None:
        # WARNING, not INFO, and the contract decides it: reaching here means capture is ENABLED
        # (the check above returned otherwise) and RBAC forbids the read, so the feature is
        # configured but inert and will not self-heal until somebody applies the grant. That is
        # the contract's WARNING case in its own words.
        #
        # It was INFO, which also made it invisible to anyone watching WARNING and above — while
        # kube.py#fetch_oauth_pods logs its own INFO for the same 403, so a forbidden cluster
        # emitted two INFO lines every cycle and nothing an operator would ever be paged on.
        log.warning("%s: login capture is enabled but not permitted to list pods in %s, so no "
                    "logins will be recorded until the grant is applied", cluster.name, ns)
        return 0
    if not pods:
        log.info("%s: no Running oauth-server pods in %s", cluster.name, ns)
        return 0

    watermarks = store.login_watermarks(cluster.name)
    recorded = 0
    read_ok = False

    for pod in pods:
        settled_through = watermarks.get(pod)
        if settled_through is None:
            since = FIRST_SIGHT_SECONDS
        else:
            # Seconds back from now to the watermark, plus the overlap. sinceSeconds is relative and
            # coarse (whole seconds), which is exactly why the dedup key rather than arithmetic is what
            # guarantees correctness here.
            age = _seconds_since(settled_through)
            since = max(OVERLAP_SECONDS, int(age) + OVERLAP_SECONDS) if age is not None \
                else FIRST_SIGHT_SECONDS

        from datetime import UTC, datetime, timedelta
        try:
            lines = client.fetch_pod_log(ns, pod, since_seconds=since)
        except ClusterError as exc:
            # An AUTH_FAILED here is worth surfacing but must not stop the other pods.
            log.warning("%s: login capture failed reading %s: %s", cluster.name, pod, exc.message)
            continue
        if lines is None:
            continue                      # roll noise or a missing grant; both already logged
        read_ok = True

        # Stamped AFTER the response, and that direction is load-bearing. The kubelet resolves
        # sinceSeconds against its own RECEIVE time, so the true boundary is `receive - since`, which
        # this bounds from above: taking the stamp before the request would put the derived edge up to
        # one request-latency too EARLY, and the leading-edge guard would then miss exactly the attempts
        # a slow read clipped. An 8 MiB read can take longer than ATTEMPT_WINDOW, so that is not
        # hypothetical. Erring late costs at most a row near the edge, which in steady state was
        # already recorded a cycle ago.
        window_start = datetime.now(UTC) - timedelta(seconds=since)
        # SPLIT INTO NAMED STAGES so the DEBUG line below can report each one. This was a single
        # composed expression, which is tidier to read and impossible to explain: the two filters
        # remove attempts for OPPOSITE reasons, and from outside both look like "the parser found
        # things and the store got none".
        #   _recordable  withholds an attempt whose success line may not be written yet — it comes
        #                back next cycle (see its docstring).
        #   _not_clipped drops an attempt whose earlier lines may lie behind the window's leading
        #                edge — "dropped for good, not deferred", in its own words.
        parsed = parse(lines)
        settled = _recordable(parsed)
        attempts = _not_clipped(settled, window_start)
        horizon = _settle_horizon(lines)

        # THE LINE THAT MAKES SILENCE LEGIBLE, and the reason this module gained any DEBUG at all.
        # In steady state every path from here down is quiet — no NEW attempts means no INFO — so a
        # working capture and a broken one produce identical logs. Measured on the reference
        # cluster: 73 attempts stored, 13 distinct users, and not one line in the pod log to say
        # capture was running.
        #
        # "settled through", not "advances to": store.set_login_watermark applies max(), so a late
        # write from a demoted leader cannot rewind it and this horizon may not become the new one.
        log.debug("%s: %s read %d line(s) covering the last %ds from read position %s — parsed %d, "
                  "withheld %d still settling (returns next cycle), dropped %d clipped at the "
                  "window's leading edge (gone for good), %d to write; log settled through %s",
                  cluster.name, pod, len(lines), since,
                  settled_through or "none (first-sight window)",
                  len(parsed), len(parsed) - len(settled), len(settled) - len(attempts),
                  len(attempts), horizon or "nothing yet — read position holds")

        if lines and not parsed:
            # GATED ON `parsed`, NOT ON `attempts`, and that distinction is the whole point. If the
            # parser found attempts and the two filters withheld them, the cause is this module's
            # own arithmetic and the line above already says so — blaming the cluster there would
            # send an operator to the wrong place.
            #
            # Nothing parsed at all has one overwhelmingly likely cause, and it is not "nobody
            # logged in": the oauth-server writes the line naming a person ONLY while the
            # authentication OPERATOR is at spec.logLevel: Debug. That is a different log level from
            # this chart's `logLevel`, on a different object, in a different vocabulary
            # (Normal/Debug/Trace/TraceAll) — and confusing the two is the likeliest reason a
            # healthy-looking deployment records nothing. Both honest possibilities are stated,
            # because a genuinely quiet cluster reads identically.
            log.debug("%s: %s: %d line(s) read and no login attempt in any of them — either nobody "
                      "logged in, or authentications.operator.openshift.io/cluster is not at "
                      "spec.logLevel: Debug, without which the lines naming a person are never "
                      "written (chart value authLogLevel, NOT logLevel; see "
                      "docs/LOGIN_CAPTURE_QUICKCHECK.md)", cluster.name, pod, len(lines))

        if not attempts and horizon is None:
            continue

        observed_at = now_iso()
        events = [event_dict(a, pod, observed_at) for a in attempts]

        # THE RECHECK. Everything above is reads; everything below writes.
        if elector is not None and not elector.is_leader:
            log.info("%s: lost leadership while reading %s — discarding %d event(s) unwritten",
                     cluster.name, pod, len(events))
            return recorded

        n = store.record_login_events(cluster.name, events) if events else 0
        recorded += n
        if horizon is not None:
            store.set_login_watermark(cluster.name, pod, horizon, observed_at)
        if n:
            log.info("%s: recorded %d login attempt(s) from %s", cluster.name, n, pod)
        elif attempts:
            # The commonest steady-state path, and previously the most confusing: attempts WERE
            # found and none were new, because the overlap deliberately re-reads a window that was
            # already recorded. Without this, a working capture that has caught up is silent in
            # exactly the way a broken one is.
            log.debug("%s: %s: all %d attempt(s) in the window were already stored — the %ds "
                      "overlap re-reads them by design, so this is steady state, not a failure",
                      cluster.name, pod, len(attempts), OVERLAP_SECONDS)

    # Forget read positions for pods that are gone. Every oauth roll replaces them, so without this
    # the table grows by one row per pod name the cluster has ever had.
    #
    # Done on the strength of the POD LIST — which succeeded above, or we would have returned — and
    # NOT gated on whether any read worked: a cluster whose log reads are all refused would otherwise
    # keep every dead pod's position forever, which is the case most likely to accumulate them. It is
    # also independent of `login_retention_days`, because this is a leak rather than a policy about
    # how long to keep data; _prune's docstring claimed to do it and never did.
    if elector is None or elector.is_leader:
        dropped = store.prune_login_watermarks(cluster.name, pods)
        if dropped:
            log.info("%s: forgot %d stale read position(s) for pods that no longer exist",
                     cluster.name, dropped)

    if not read_ok:
        # Not a single pod answered. Do NOT stamp a successful read: `started_at` would then claim we
        # have been watching since a cycle that saw nothing, and `last_read_at` is the liveness signal
        # that tells somebody capture has stopped.
        #
        # SAY SO, because the decision above is invisible otherwise. Its whole effect is a metric
        # that stops moving (gsd_login_capture_last_read_timestamp_seconds), and a gauge going flat
        # is not self-explaining — nothing marked the cycle where it happened. WARNING rather than
        # ERROR: group polling is untouched and an oauth roll self-heals it within a cycle or two.
        log.warning("%s: login capture read none of the %d oauth-server pod(s) in %s this cycle; "
                    "the last-read stamp is deliberately not advanced, so the dashboard will report "
                    "capture as stale until one answers", cluster.name, len(pods), ns)
        return recorded

    if elector is not None and not elector.is_leader:
        return recorded
    store.record_login_read(cluster.name, now_iso())

    _prune(store, cluster, settings, elector, signals)
    return recorded


def _prune(store: StorageBackend, cluster: ClusterConfig, settings: Settings, elector=None,
           signals=None) -> None:
    """Drop events past the retention window.

    Watermarks are NOT pruned here — that happens in capture_once, where the live pod list is in
    scope and where it is correctly independent of this retention setting. This docstring used to
    claim both and deliver one.

    Bounded per call by store.prune_login_events' own max_rows, because this runs on the poll thread
    against a single writer — an unbounded DELETE over a long backlog holds the write lock while every
    reader and the next poll wait behind it. A full chunk means more remains, and the next cycle
    continues; there is no need to finish in one pass.
    """
    days = settings.login_retention_days
    if days <= 0:
        return                            # 0 disables retention, deliberately
    before = _iso_days_ago(days)
    if before is None:
        return
    if elector is not None and not elector.is_leader:
        return
    removed = store.prune_login_events(cluster.name, before)
    if removed:
        if signals is not None:
            # Duck-typed metrics seam (gsd/metrics.py RuntimeSignals), same count as the
            # log line below and from the same call, so the two cannot disagree. A rate
            # pinned at the 5000-row bound is the backlog-not-draining signal.
            signals.note_retention("login_event", removed)
        log.info("%s: pruned %d login event(s) older than %s", cluster.name, removed, before)


def _seconds_since(iso: str) -> float | None:
    """Seconds between an ISO timestamp and now, or None if it cannot be parsed."""
    from datetime import UTC, datetime
    try:
        then = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (datetime.now(UTC) - then).total_seconds())


def _iso_days_ago(days: int) -> str | None:
    from datetime import UTC, datetime, timedelta
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
```

New text:

```python
"""Audit login capture entry point and bounded retention.

Legacy event_dict remains an offline row-construction helper for stored-history tests.
It does not read pod logs or select a retired source.
"""
from __future__ import annotations

import logging

from .config import ClusterConfig, Settings
from .loginlog import LoginAttempt
from .storage import StorageBackend

log = logging.getLogger(__name__)


def event_dict(attempt: LoginAttempt, pod_name: str, observed_at: str) -> dict:
    """A LoginAttempt plus the two things the store needs and the parser cannot know.

    `pod_name` is required because it is IN the dedup key, and LoginAttempt deliberately does not carry
    it — the parser takes text and knows nothing about where it came from, which is what makes it
    testable without a cluster. Public rather than private so tests can build rows the same way the
    capture loop does, instead of hand-assembling dicts that drift from it.

    The timestamp format is fixed here, once. Microsecond precision with a literal Z, because it is
    part of the unique key: two attempts one microsecond apart must not collide, and a format that
    varied between writer and reader would make the key match rows it should not.
    """
    return {
        "pod_name": pod_name,
        "user_name": attempt.user_name,
        "outcome": attempt.outcome,
        "at": attempt.at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "provider": attempt.provider,
        "ldap_result_code": attempt.ldap_result_code,
        "detail": attempt.detail,
        "observed_at": observed_at,
    }



def capture_once(store: StorageBackend, cluster: ClusterConfig, settings: Settings,
                 elector=None, timeout: float = 15.0, signals=None) -> int:
    """The poller's entry point: off means no read; on means audit-log only."""
    if not settings.login_capture_enabled:
        log.debug("%s: login capture is disabled; no audit log is read", cluster.name)
        return 0
    from .auditlog import capture_once as capture_audit_once
    return capture_audit_once(store, cluster, settings, elector, timeout, signals)


def _prune(store: StorageBackend, cluster: ClusterConfig, settings: Settings, elector=None,
           signals=None) -> None:
    """Drop events past the retention window.

    Bounded per call by store.prune_login_events' own max_rows, because this runs on the poll thread
    against a single writer — an unbounded DELETE over a long backlog holds the write lock while every
    reader and the next poll wait behind it. A full chunk means more remains, and the next cycle
    continues; there is no need to finish in one pass.
    """
    days = settings.login_retention_days
    if days <= 0:
        return                            # 0 disables retention, deliberately
    before = _iso_days_ago(days)
    if before is None:
        return
    if elector is not None and not elector.is_leader:
        return
    removed = store.prune_login_events(cluster.name, before)
    if removed:
        if signals is not None:
            # Duck-typed metrics seam (gsd/metrics.py RuntimeSignals), same count as the
            # log line below and from the same call, so the two cannot disagree. A rate
            # pinned at the 5000-row bound is the backlog-not-draining signal.
            signals.note_retention("login_event", removed)
        log.info("%s: pruned %d login event(s) older than %s", cluster.name, removed, before)



def _iso_days_ago(days: int) -> str | None:
    from datetime import UTC, datetime, timedelta
    return (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
```

### Block 17 — local-development/gsd/kube.py

Remove the retired path.
Baseline: local-development/gsd/kube.py:76; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/kube.py | edit -->

Old text:

```python
# The oauth-server's own pods, and their logs. Read for ONE purpose: the lines naming who logged in,
# which exist only at `spec.logLevel: Debug` on the authentication OPERATOR CR — not the OAuth CR. See
# docs/LOGIN_CAPTURE_QUICKCHECK.md.
#
# Templated on the namespace because it is a chart value (`loginCapture.namespace`), not because it
# varies in practice: OpenShift installs the OAuth server into openshift-authentication and the grant
# the chart creates is a Role in that one namespace.
POD_API_TMPL = "/api/v1/namespaces/%s/pods"

```

New text:

```python
```

### Block 18 — local-development/gsd/kube.py

Remove the retired path.
Baseline: local-development/gsd/kube.py:91; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/kube.py | edit -->

Old text:

```python
# One audit-file read's byte budget per cycle. The same figure as the pod-log cap and for the
# same reason — a bounded transfer on the poll thread — and it is what bounds a backfill:
# ten rotated files of 100 MB drain at this rate over cycles, not in one.
```

New text:

```python
# One audit-file read is bounded to 8 MiB per node per cycle; backfills drain over cycles.
```

### Block 19 — local-development/gsd/kube.py

Remove the retired path.
Baseline: local-development/gsd/kube.py:103; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/kube.py | edit -->

Old text:

```python
# One pod-log read's wall-clock budget. The httpx timeout on _client caps the SILENCE between
# chunks, not the transfer, so a stream dripping just under it can run for minutes (measured:
# a timeout=1.0 client consumed a 3.1s dribble without raising). logincapture stamps the clock
# behind its leading-edge guard AFTER this returns, and its no-loss accounting holds only while
# that stamp lags the kubelet's window resolution by less than OVERLAP_SECONDS minus the settle
# margin — loss measured from ~58.5s of latency with the shipped constants. Twenty seconds keeps
# the overshoot far inside that, and a read this interrupts is deferred, not lost: the truncation
# path keeps the oldest lines and the watermark machinery re-reads the rest next cycle.
```

New text:

```python
# Wall-clock budget for one node audit-file read, in addition to the HTTP silence timeout.
```

### Block 20 — local-development/gsd/kube.py

Remove the retired path.
Baseline: local-development/gsd/kube.py:1095; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/kube.py | edit -->

Old text:

```python
    def fetch_oauth_pods(self, namespace: str) -> list[str] | None:
        """Names of the Running oauth-server pods, or None when we may not list them.

        DISCOVERY IS NOT OPTIONAL. Pod names are generated, production runs two or three replicas, and
        every roll replaces them — so there is no fixed name to read and no Deployment log subresource
        to read instead (verified: `GET .../deployments/oauth-openshift/log` returns "the server could
        not find the requested resource"). `oc logs deploy/x` only looks combined; the client resolves
        the Deployment to its pods and reads each one, which is what this does.

        Only Running pods. A Pending pod has produced nothing yet, and a Terminating one is mid-roll —
        both are read next cycle if they are still there, and neither is worth a failed request.

        None means FORBIDDEN, deliberately distinct from [] (permitted, no pods found). The grant is
        optional: an install that never enabled loginCapture, or upgraded the image without
        re-applying RBAC, gets a 403 here and must degrade rather than fail the poll.
        """
        path = POD_API_TMPL % namespace
        with self._client() as client:
            try:
                items = self._list_all(client, path)
            except ClusterError as exc:
                if exc.outcome == FORBIDDEN and path in exc.message:
                    # DEBUG, and factual only. This said "login capture is off. Grant it with
                    # loginCapture.enabled=true." at INFO, which was wrong twice over: this method
                    # is called ONLY from logincapture#capture_once, which has already returned when
                    # capture is disabled — so whenever this fires capture is ON and the missing
                    # thing is the RBAC grant, not the feature flag. It sent an operator to set a
                    # value that was already set.
                    #
                    # The operator-facing sentence now lives in capture_once, which is the layer
                    # that knows what a 403 MEANS for the feature and says it once, at WARNING.
                    # This layer only reports what it saw.
                    log.debug("%s: forbidden listing pods in %s; returning no pods",
                              self.cluster.name, namespace)
                    return None
                raise
        return [
            name for obj in items
            if (obj.get("status") or {}).get("phase") == "Running"
            and (name := (obj.get("metadata") or {}).get("name"))
        ]

    def fetch_pod_log(
        self,
        namespace: str,
        pod_name: str,
        since_seconds: int | None = None,
        max_bytes: int = 8 * 1024 * 1024,
    ) -> list[str] | None:
        """Timestamped log lines for one pod, or None when this pod cannot be read right now.

        NOT THROUGH `_get()`, and that is mandatory rather than stylistic: `_get` always calls
        `response.json()`, and this endpoint returns TEXT. `_client()` IS used — it only supplies the
        bearer token and CA verification, which this needs exactly as much as any other call.

        STREAMED, AND BYTE-BOUNDED — in BYTES, counted before any line is assembled. The previous
        draft counted characters of lines `iter_lines()` had already buffered whole, so a single
        line larger than the cap was held in memory before it could be measured, and a multi-byte
        log undercounted. Stopping at the cap also ends the transfer instead of paying for lines
        that would be discarded.

        A CAP HIT KEEPS THE OLDEST LINES OF THE WINDOW, deliberately. The kubelet streams oldest
        first, and oldest-first is the direction the watermark machinery REQUIRES: the cursor only
        advances through lines actually returned, so the deferred newest lines fall inside the next
        cycle's window and nothing is lost — only late. Keeping the newest instead would let the
        cursor advance past everything the cap displaced and silently drop it forever; recency is
        what the next cycle gets back anyway, completeness is not. (An earlier comment here claimed
        the newest lines were kept; it described the opposite of what the code did.) The line the
        cap cuts in half is dropped for the same reason: a truncated diagnostic can mis-parse — a
        bind error losing its `data` sub-code reads as a plain wrong password — and the whole line
        is inside the next cycle's overlap.

        BOUNDED IN WALL-CLOCK TIME as well, and on the same path as the cap. The client's timeout
        only caps the gap between chunks, so it bounds nothing about the whole transfer — and the
        capture loop derives its leading-edge guard from a clock stamped AFTER this returns, so
        every second spent here widens the band of attempts that guard throws away for good. See
        LOG_READ_BUDGET_SECONDS for the measured threshold where that band reaches rows no cycle
        ever recorded.

        `timestamps=true` is what makes the result usable at all — it prefixes each line with the
        kubelet's RFC3339 UTC stamp. klog's own stamp carries no year and no timezone.

        RETURNS None FOR THE ORDINARY ROLL, RAISES FOR THE REST, and the distinction is the point:

          404              the pod went away between listing and reading. Every roll does this.
          400 not-ready    the container has not started, so there is no log yet. Measured message:
                           "container nope is not valid for pod ..." — reason BadRequest.
          403              the grant is missing. LOGGED AT WARNING, because it is permanent and will
                           not fix itself, and a silent None here looks identical to "nobody logged
                           in" forever.
          any other        raised, so a real outage is not mistaken for roll noise.
        """
        params: dict[str, Any] = {"timestamps": "true"}
        if since_seconds is not None:
            params["sinceSeconds"] = str(since_seconds)
        path = f"{POD_API_TMPL % namespace}/{pod_name}/log"

        chunks: list[bytes] = []
        size = 0
        truncated = False
        over_budget = False
        started = time.monotonic()
        try:
            with self._client() as client:
                with client.stream("GET", path, params=params) as response:
                    if response.status_code >= 400:
                        response.read()
                        return self._log_read_refused(response, namespace, pod_name)
                    for chunk in response.iter_bytes(chunk_size=min(64 * 1024, max(1, max_bytes))):
                        if time.monotonic() - started > LOG_READ_BUDGET_SECONDS:
                            # Checked before the chunk is kept: a chunk that arrived past the budget
                            # proves the transfer is the slow kind, and keeping it would end the
                            # batch mid-line anyway — the pop below drops the tail either way.
                            truncated = over_budget = True
                            break
                        room = max_bytes - size
                        if len(chunk) >= room:
                            chunks.append(chunk[:room])
                            size = max_bytes
                            truncated = True
                            break
                        chunks.append(chunk)
                        size += len(chunk)
        except httpx.HTTPError as exc:
            # A connect error or timeout reading ONE pod must not fail the cycle: the other pods still
            # have lines, and this one is retried next time from the same watermark.
            log.info("%s: could not read %s log (%s: %s)",
                     self.cluster.name, pod_name, type(exc).__name__, exc)
            return None

        # errors="replace" cannot corrupt a kept line: the only place a multi-byte character can be
        # split is the cap boundary, and the line holding it is popped below.
        lines = b"".join(chunks).decode("utf-8", errors="replace").splitlines()
        if truncated:
            if lines:
                lines.pop()
            if over_budget:
                log.info(
                    "%s: %s log read exceeded its %.0fs budget after %d lines; the OLDEST lines of "
                    "this window are kept, and the rest fall inside the next cycle's window once "
                    "the watermark has advanced",
                    self.cluster.name, pod_name, LOG_READ_BUDGET_SECONDS, len(lines),
                )
            else:
                log.info(
                    "%s: %s log hit the %d-byte cap after %d lines; the OLDEST lines of this window "
                    "are kept, and the rest fall inside the next cycle's window once the watermark "
                    "has advanced",
                    self.cluster.name, pod_name, max_bytes, len(lines),
                )
        return lines

    def _log_read_refused(
        self, response: httpx.Response, namespace: str, pod_name: str
    ) -> list[str] | None:
        """Classify a >=400 on a pod-log read: benign roll noise, or something worth saying out loud.

        The Kubernetes Status body carries `reason` and `message`, which is the only way to tell a
        container-not-ready 400 from a 400 that means something else. Guessing from the code alone is
        what turns a permanent misconfiguration into indistinguishable debug noise.
        """
        try:
            body = response.json()
        except ValueError:
            body = {}
        reason = body.get("reason") or ""
        message = body.get("message") or response.text[:200]
        code = response.status_code

        if code == 404:
            log.debug("%s: %s is gone (read raced a roll)", self.cluster.name, pod_name)
            return None
        if code == 403:
            log.warning(
                "%s: FORBIDDEN reading %s/%s log — capture will record nothing until this is fixed. "
                "The chart grants it with loginCapture.enabled=true (a Role in %s). Reason: %s",
                self.cluster.name, namespace, pod_name, namespace, reason or code,
            )
            return None
        if code == 400 and ("ContainerCreating" in message or "not started" in message
                            or "is waiting to start" in message):
            log.debug("%s: %s container not ready yet (%s)", self.cluster.name, pod_name, reason)
            return None
        if code == 401:
            raise ClusterError(AUTH_FAILED, f"401 Unauthorized reading {pod_name} log")
        # Everything else — an unexpected 400 included — is surfaced rather than swallowed.
        log.warning("%s: unexpected HTTP %d reading %s log (reason=%s): %s",
                    self.cluster.name, code, pod_name, reason or "-", message[:200])
        return None

```

New text:

```python
```

### Block 21 — local-development/gsd/kube.py

Update the surviving contract.
Baseline: local-development/gsd/kube.py:1398; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/kube.py | edit -->

Old text:

```python
        Bounded in bytes and in wall-clock (LOG_READ_BUDGET_SECONDS), like fetch_pod_log, and a
```

New text:

```python
        Bounded in bytes and in wall-clock (LOG_READ_BUDGET_SECONDS), and a
```

### Block 22 — local-development/gsd/config.py

Remove the retired path.
Baseline: local-development/gsd/config.py:478; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
    # Login capture. OFF by default: it needs a read grant the chart only creates when asked, and it
    # records nothing at all unless the authentication operator's logLevel is Debug — so enabling it
    # here alone is inert rather than broken.
    login_capture_enabled: bool = False
    # Where the oauth-server runs. A value rather than a constant only because the chart's Role is
    # created in this namespace and the two must agree; it is fixed on any normal OpenShift cluster.
    login_capture_namespace: str = "openshift-authentication"
```

New text:

```python
    # Direct app installs opt into the audit node-proxy read; Helm enables it by default.
    login_capture_enabled: bool = False
```

### Block 23 — local-development/gsd/config.py

Remove the retired path.
Baseline: local-development/gsd/config.py:493; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
    # WHICH LOG. `pod-log` reads the oauth-server pods' logs, which name a person only at
    # spec.logLevel: Debug on the authentication operator CR. `audit-log` reads
    # /var/log/oauth-server/audit.log on the control-plane nodes through the API server's node
    # proxy: no Debug, no OAuth roll, history back to the rotated files — and a cluster-wide read
    # grant, which is why the chart defaults it off. Anything unrecognised is pod-log: the
    # shipped default, and inert rather than wide.
    login_capture_source: str = "pod-log"
```

New text:

```python
    # The sole live source. Historical row source fields remain unchanged.
    login_capture_source: str = "audit-log"
```

### Block 24 — local-development/gsd/config.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/gsd/config.py:1030; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
def _login_capture_source_setting(raw: dict) -> str:
    """pod-log | audit-log. Fail SAFE to pod-log: it is the shipped default and needs nothing
    the audit source needs; a typo must not be what widens the read."""
    source = os.environ.get("GSD_LOGIN_CAPTURE_SOURCE")
    if source is None:
        source = raw.get("loginCaptureSource", "pod-log")
    word = str(source).strip().lower()
    if word in ("pod-log", "audit-log"):
        return word
    log.warning("loginCaptureSource=%r is not pod-log/audit-log; using 'pod-log'", source)
    return "pod-log"
```

New text:

```python
def _login_capture_source_setting(raw: dict) -> str:
    """Refuse retired/unknown sources rather than silently changing the requested read grant."""
    source = os.environ.get("GSD_LOGIN_CAPTURE_SOURCE", raw.get("loginCaptureSource", "audit-log"))
    if str(source).strip() != "audit-log":
        raise ConfigError("loginCaptureSource must be audit-log; pod-log was removed. "
                          "Set loginCaptureSource/GSD_LOGIN_CAPTURE_SOURCE to audit-log, remove "
                          "authLogLevel chart values, and restore OAuth verbosity to Normal manually.")
    return "audit-log"
```

### Block 25 — local-development/gsd/config.py

Update the surviving contract.
Baseline: local-development/gsd/config.py:1670; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
        login_capture_namespace=raw.get("loginCaptureNamespace") or "openshift-authentication",
```

New text:

```python
```

### Block 26 — local-development/gsd/api.py

Remove the retired path.
Baseline: local-development/gsd/api.py:3376; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
    THE COMPLAINT POINTS AT `authLogLevel`, because the commonest reason to be fiddling with a log
    level on this deployment is to make the Logins tab show something — and that is a different
    setting, on a different object, which raises the OAUTH-SERVER's verbosity rather than this
    app's. Naming it turns a puzzling fallback into a one-line fix. Only the five levels this app
    accepts are ever listed; the message does not catalogue values that do not work here.
```

New text:

```python
    Login capture uses audit logs and needs no OAuth verbosity change.
```

### Block 27 — local-development/gsd/api.py

Update the surviving contract.
Baseline: local-development/gsd/api.py:3406; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
        f"{', '.join(LOG_LEVELS)} (case does not matter). If you were trying to raise the "
        f"oauth-server's verbosity so the Logins tab has something to read, that is the chart's "
        f"authLogLevel value — a different setting, on a different object, not this one."
```

New text:

```python
        f"{', '.join(LOG_LEVELS)} (case does not matter). Login capture uses the audit log "
        f"at default OAuth verbosity; see docs/LOGIN_CAPTURE_QUICKCHECK.md."
```

### Block 28 — local-development/gsd/api.py

Remove the retired path.
Baseline: local-development/gsd/api.py:1934; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
                if settings.login_capture_source == "audit-log" else
                "read from the oauth-server log at Debug verbosity; covers only the period "
                "since capture began — earlier logins were never recorded and cannot be "
                "fetched, and rows older than the configured retention age out"
```

New text:

```python
```

### Block 29 — local-development/gsd/metrics.py

Update the surviving contract.
Baseline: local-development/gsd/metrics.py:463; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/metrics.py | edit -->

Old text:

```python
            "Always 1; `source` is which log login capture reads for this cluster (pod-log or "
            "audit-log). Join it onto gsd_login_capture_last_read_timestamp_seconds with "
```

New text:

```python
            "Always 1; `source` is audit-log for live capture. "
            "Join it onto gsd_login_capture_last_read_timestamp_seconds with "
```

### Block 30 — local-development/gsd/metrics.py

Update the surviving contract.
Baseline: local-development/gsd/metrics.py:524; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/metrics.py | edit -->

Old text:

```python
                    source = getattr(self.settings, "login_capture_source", "pod-log")
```

New text:

```python
                    source = "audit-log"
```

### Block 31 — local-development/gsd/auditlog.py

Update the surviving contract.
Baseline: local-development/gsd/auditlog.py:112; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/auditlog.py | edit -->

Old text:

```python
# The stamp format every login_event row uses (gsd/logincapture.py#event_dict). Fixed once.
```

New text:

```python
# The existing login_event storage format: microseconds and a literal UTC Z.
```

### Block 32 — local-development/mock-app/mock_app/podlog.py

Retire the whole file. Empty New is the checker-compatible deletion payload; see deletion protocol.
Baseline: local-development/mock-app/mock_app/podlog.py:1; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/podlog.py | edit -->

Old text:

```python
"""The pod-log text stream (DESIGN §7.3, endpoint m).

``GET /api/v1/namespaces/<ns>/pods/<pod>/log?timestamps=true`` returns TEXT — each line
prefixed with the kubelet's RFC3339-UTC stamp + a space (``^(\\d{4}-…Z)\\s``, loginlog.py:113).
The fixture supplies whole lines (the timestamp prefix + a klog body) so the author controls
exactly what the klog verdict parser sees.
"""

from __future__ import annotations

from .fixture import PodLogFixture


class PodLogServer:
    def __init__(self, pod_log: PodLogFixture):
        self._pod_log = pod_log

    @property
    def namespace(self) -> str:
        return self._pod_log.namespace

    def body(self) -> bytes:
        """The whole log as bytes — one line per fixture entry, newline-joined."""
        if not self._pod_log.lines:
            return b""
        return ("\n".join(self._pod_log.lines) + "\n").encode("utf-8")
```

New text:

```python
```

### Block 33 — local-development/mock-app/mock_app/app.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/app.py:23; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/app.py | edit -->

Old text:

```python
from .podlog import PodLogServer
```

New text:

```python
```

### Block 34 — local-development/mock-app/mock_app/app.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/app.py:143; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/app.py | edit -->

Old text:

```python
    state.podlog = PodLogServer(fixture.pod_log)
```

New text:

```python
```

### Block 35 — local-development/mock-app/mock_app/app.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/app.py:428; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/app.py | edit -->

Old text:

```python
        state.podlog = PodLogServer(fresh.pod_log)
```

New text:

```python
```

### Block 36 — local-development/mock-app/mock_app/app.py

Remove the retired path.
Baseline: local-development/mock-app/mock_app/app.py:303; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/app.py | edit -->

Old text:

```python
    # ── (l) OAuth-server pods ────────────────────────────────────────────────────────────────
    @app.get("/api/v1/namespaces/{namespace}/pods")
    def pods(request: Request, namespace: str):
        if (r := gate(request)) is not None:
            return r
        request.state.endpoint = "l"
        pods_fx = state.fixture.oauth_pods
        if pods_fx.forbidden:
            return errors.forbidden_403(f"/api/v1/namespaces/{namespace}/pods")
        entries = pods_fx.entries if namespace == pods_fx.namespace else ()
        items = [pod_item(p["name"], p["phase"]) for p in entries]
        return list_response(request, items, "PodList", "l")

    # ── (m) Pod log (TEXT stream) ────────────────────────────────────────────────────────────
    @app.get("/api/v1/namespaces/{namespace}/pods/{pod}/log")
    def pod_log(request: Request, namespace: str, pod: str):
        if (r := gate(request)) is not None:
            return r
        request.state.endpoint = "m"
        body = state.podlog.body()
        # timestamps=true is what makes each line usable; the fixture already supplies the
        # RFC3339 prefix, so we simply return the text.
        return PlainTextResponse(content=body, media_type="text/plain; charset=utf-8")

```

New text:

```python
```

### Block 37 — local-development/mock-app/mock_app/app.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/app.py:35; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/app.py | edit -->

Old text:

```python
    pod_item,
```

New text:

```python
```

### Block 38 — local-development/mock-app/mock_app/fixture.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/mock_app/fixture.py:189; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/fixture.py | edit -->

Old text:

```python
@dataclass(frozen=True)
class OAuthPods:
    namespace: str = "openshift-authentication"
    entries: tuple[dict[str, str], ...] = ()   # {name, phase}
    forbidden: bool = False
```

New text:

```python
```

### Block 39 — local-development/mock-app/mock_app/fixture.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/mock_app/fixture.py:204; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/fixture.py | edit -->

Old text:

```python
@dataclass(frozen=True)
class PodLogFixture:
    namespace: str = "openshift-authentication"
    lines: tuple[str, ...] = ()       # whole lines, RFC3339 prefix + klog body
```

New text:

```python
```

### Block 40 — local-development/mock-app/mock_app/fixture.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/mock_app/fixture.py:524; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/fixture.py | edit -->

Old text:

```python
def _oauth_pods(value: Any) -> OAuthPods:
    block = _as_dict(value, "oauthPods")
    entries = tuple(
        {"name": p["name"], "phase": p.get("phase", "Running")}
        for p in _as_list(block.get("entries") or [], "oauthPods.entries")
    )
    return OAuthPods(
        namespace=block.get("namespace", "openshift-authentication"),
        entries=entries,
        forbidden=bool(block.get("forbidden", False)),
    )
```

New text:

```python
```

### Block 41 — local-development/mock-app/mock_app/fixture.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/mock_app/fixture.py:564; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/fixture.py | edit -->

Old text:

```python
def _pod_log(value: Any) -> PodLogFixture:
    block = _as_dict(value, "podLog")
    return PodLogFixture(
        namespace=block.get("namespace", "openshift-authentication"),
        lines=tuple(block.get("lines") or ()),
    )
```

New text:

```python
```

### Block 42 — local-development/mock-app/mock_app/fixture.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/fixture.py:228; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/fixture.py | edit -->

Old text:

```python
    oauth_pods: OAuthPods
```

New text:

```python
```

### Block 43 — local-development/mock-app/mock_app/fixture.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/fixture.py:230; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/fixture.py | edit -->

Old text:

```python
    pod_log: PodLogFixture
```

New text:

```python
```

### Block 44 — local-development/mock-app/mock_app/fixture.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/fixture.py:289; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/fixture.py | edit -->

Old text:

```python
        oauth_pods = _oauth_pods(data.get("oauthPods"))
```

New text:

```python
```

### Block 45 — local-development/mock-app/mock_app/fixture.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/fixture.py:291; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/fixture.py | edit -->

Old text:

```python
        pod_log = _pod_log(data.get("podLog"))
```

New text:

```python
```

### Block 46 — local-development/mock-app/mock_app/fixture.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/fixture.py:310; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/fixture.py | edit -->

Old text:

```python
            oauth_pods=oauth_pods,
```

New text:

```python
```

### Block 47 — local-development/mock-app/mock_app/fixture.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/fixture.py:312; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/fixture.py | edit -->

Old text:

```python
            pod_log=pod_log,
```

New text:

```python
```

### Block 48 — local-development/mock-app/mock_app/fixture.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/fixture.py:332; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/fixture.py | edit -->

Old text:

```python
            "oauthPods": len(self.oauth_pods.entries),
```

New text:

```python
```

### Block 49 — local-development/mock-app/mock_app/fixture.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/fixture.py:249; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/fixture.py | edit -->

Old text:

```python
            "bindings", "operatorConfigs", "nodes", "oauth", "oauthPods", "auditLog", "podLog",
```

New text:

```python
            "bindings", "operatorConfigs", "nodes", "oauth", "auditLog",
```

### Block 50 — local-development/mock-app/mock_app/responses.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/mock_app/responses.py:265; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/responses.py | edit -->

Old text:

```python
def pod_item(name: str, phase: str) -> dict:
    return {"apiVersion": "v1", "kind": "Pod",
            "metadata": {"name": name}, "status": {"phase": phase}}
```

New text:

```python
```

### Block 51 — local-development/mock-app/fixtures/paging.yaml

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/fixtures/paging.yaml:30; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/fixtures/paging.yaml | edit -->

Old text:

```text

oauthPods:
  namespace: openshift-authentication
  entries:
    - {name: oauth-openshift-a, phase: Running}
    - {name: oauth-openshift-b, phase: Running}
    - {name: oauth-openshift-c, phase: Running}
```

New text:

```text
```

### Block 52 — local-development/mock-app/fixtures/forbidden.yaml

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/fixtures/forbidden.yaml:38; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/fixtures/forbidden.yaml | edit -->

Old text:

```text
oauthPods:
  namespace: openshift-authentication
  forbidden: true

```

New text:

```text
```

### Block 53 — local-development/mock-app/fixtures/crd-absent.yaml

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/fixtures/crd-absent.yaml:37; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/fixtures/crd-absent.yaml | edit -->

Old text:

```text
oauthPods:
  namespace: openshift-authentication
  entries: []

```

New text:

```text
```

### Block 54 — local-development/mock-app/fixtures/reference.yaml

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/fixtures/reference.yaml:192; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/fixtures/reference.yaml | edit -->

Old text:

```text
oauthPods:
  namespace: openshift-authentication
  entries:
    - {name: oauth-openshift-6d8f9c7b4-abcde, phase: Running}
    - {name: oauth-openshift-6d8f9c7b4-fghij, phase: Running}
    - {name: oauth-openshift-6d8f9c7b4-pending, phase: Pending}
  forbidden: false

```

New text:

```text
```

### Block 55 — local-development/mock-app/fixtures/reference.yaml

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/fixtures/reference.yaml:214; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/fixtures/reference.yaml | edit -->

Old text:

```text

podLog:
  namespace: openshift-authentication
  lines:
    - '2026-09-03T10:15:27.234567Z I0903 10:15:27.234567 1 login.go:191] Login with provider "acme-ldap" succeeded for "jane.smith"'
    - '2026-09-03T10:16:01.000000Z I0903 10:16:01.000000 1 basicauth.go:48] Login with provider "acme-ldap" failed for login "lateef.o"'
```

New text:

```text
```

### Block 56 — local-development/mock-app/deploy/mock-fixture-configmap.yaml

Regenerate the bundled mock ConfigMap with the audit-only reference fixture; metadata is retained.
Baseline: local-development/mock-app/deploy/mock-fixture-configmap.yaml:1; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/deploy/mock-fixture-configmap.yaml | edit -->

Old text:

```text
apiVersion: v1
data:
  reference.yaml: "# reference.yaml \u2014 a small reference cluster that reproduces the four measured\
    \ personas.\n#\n# The SAR oracle (DESIGN \xA75.4), which test_sar_personas.py asserts:\n#\n#   persona\
    \      fixture RBAC                                   list crb (wide)  update crb (usage)\n#   kubeadmin\
    \    cluster-admin CRB                              ALLOW            ALLOW\n#   dana.lee     cluster-reader\
    \ CRB (read verbs, no update)     ALLOW            DENY\n#   lateef.o     no admin CRB           \
    \                        DENY             DENY\n#   jane.smith   in a group NAMED \"...-cluster-admin\"\
    \ but with  DENY             DENY\n#                NO ClusterRoleBinding behind it (the decoy)\n\
    #\n# The decoy is the point: a suggestively-named group must NOT grant the tier \u2014 only a real\n\
    # (Cluster)RoleBinding reaching one of spec.groups/spec.user does.\n\nmeta:\n  clusterName: mock-openshift\n\
    \  token: \"mock-token-reference\"\n\ngroupsyncs:\n  - name: ldap-sync\n    namespace: group-sync-operator\n\
    \    generation: 3\n    schedule: \"*/30 * * * *\"\n    providers:\n      - {name: acme-ldap, kind:\
    \ rfc2307, filter: \"(objectClass=groupOfNames)\"}\n    lastSyncSuccessTime: \"2026-09-14T08:00:00Z\"\
    \n    conditions:\n      - {type: ReconcileSuccess, lastTransitionTime: \"2026-09-14T08:00:00Z\"}\n\
    \  - crdAbsent: false\n\ngroups:\n  # Bound to cluster-admin via cluster-admin-crb \u2192 grants kubeadmin\
    \ the wide + usage tiers.\n  - name: app-ocp-rbac-demo-cluster-admin\n    syncProvider: acme-ldap\n\
    \    syncTime: \"2026-09-14T08:00:00Z\"\n    ldapUid: \"cn=ocp-admins,ou=Groups,dc=acme,dc=com\"\n\
    \    users: [kubeadmin]\n  # Bound to cluster-reader via cluster-reader-crb \u2192 dana.lee gets wide\
    \ but not usage.\n  - name: cluster-readers\n    syncProvider: acme-ldap\n    syncTime: \"2026-09-14T08:00:00Z\"\
    \n    users: [dana.lee]\n  # THE DECOY: name ends \"-cluster-admin\" but nothing binds it. jane.smith\
    \ must stay self.\n  - name: platform-team-cluster-admin\n    syncProvider: acme-ldap\n    syncTime:\
    \ \"2026-09-14T08:00:00Z\"\n    users: [jane.smith]\n  # An ordinary application group with a namespaced\
    \ viewer grant to a direct user.\n  - name: acme-app-viewers\n    syncProvider: acme-ldap\n    syncTime:\
    \ \"2026-09-14T08:00:00Z\"\n    users: [lateef.o]\n  # An empty group (the API returns users: null)\
    \ \u2014 exercises the null-users branch.\n  - name: empty-team\n    syncProvider: acme-ldap\n   \
    \ users: null\n  # A legacy group carrying a non-person service account; the target of the hand-made\n\
    \  # (unmanaged) binding below. Deliberately holds NO persona, so it cannot perturb the oracle.\n\
    \  - name: legacy-ops\n    syncProvider: acme-ldap\n    users: [svc-legacy]\n  # The reporting-auditor\
    \ group (rbacAuditors, #100): bound to the report-auditor ClusterRole below,\n  # which grants `list\
    \ clusterrolebindings` \u2014 the wide-tier gate \u2014 so its members are AUDITORS (wide\n  # read-only,\
    \ NOT usage). developer is a member, to test the auditor tier on the mock.\n  - name: app-ocp-rbac-demo-report-auditors\n\
    \    syncProvider: acme-ldap\n    syncTime: \"2026-09-14T08:00:00Z\"\n    users: [developer]\n\nusers:\n\
    \  entries:\n    - {name: kubeadmin,  fullName: \"Cluster Admin\", creationTimestamp: \"2026-01-01T00:00:00Z\"\
    ,\n       identities: []}\n    - {name: dana.lee,   fullName: \"Dana Lee\",      creationTimestamp:\
    \ \"2026-01-02T00:00:00Z\",\n       identities: [\"acme-ldap:dana.lee\"]}\n    - {name: lateef.o,\
    \   fullName: \"Lateef O.\",     creationTimestamp: \"2026-01-03T00:00:00Z\",\n       identities:\
    \ [\"acme-ldap:lateef.o\"]}\n    - {name: jane.smith, fullName: \"Jane Smith\",    creationTimestamp:\
    \ \"2026-01-04T00:00:00Z\",\n       identities: [\"acme-ldap:jane.smith\"]}\n    # The developer persona:\
    \ member of the reporting-auditor group below, so it exercises the AUDITOR\n    # (wide read-only)\
    \ tier \u2014 a member of a feature-granting group, for testing \"who belongs to it\".\n    - {name:\
    \ developer,  fullName: \"Developer\",     creationTimestamp: \"2026-01-05T00:00:00Z\",\n       identities:\
    \ [\"developer:developer\"]}\n  forbidden: false\n\nidentities:\n  entries:\n    - {userName: dana.lee,\
    \   creationTimestamp: \"2026-01-02T00:00:00Z\", providerPrefix: acme-ldap}\n    - {userName: lateef.o,\
    \   creationTimestamp: \"2026-01-03T00:00:00Z\", providerPrefix: acme-ldap}\n    - {userName: jane.smith,\
    \ creationTimestamp: \"2026-01-04T00:00:00Z\", providerPrefix: acme-ldap}\n    - {userName: developer,\
    \  creationTimestamp: \"2026-01-05T00:00:00Z\", providerPrefix: developer}\n  forbidden: false\n\n\
    namespaces:\n  entries:\n    # Two selector dimensions \u2014 company.net/mnemonic AND company.net/app-environment\
    \ \u2014 mirroring the\n    # real crc-local convention (docs/DESIGN_reporting_selectors_snapshots_and_windows.md\
    \ \xA76), so the\n    # multi-dimension selector (AND across dimensions, OR within one) is exercisable\
    \ against the mock.\n    # `team` is kept on the first two so the single-label tests still hold.\n\
    \    - {name: acme-app, phase: Active, creationTimestamp: \"2026-01-02T00:00:00Z\",\n       labels:\
    \ {\"team\": \"acme\", \"kubernetes.io/metadata.name\": \"acme-app\",\n                \"company.net/mnemonic\"\
    : \"acme\", \"company.net/app-environment\": \"prod\"}}\n    - {name: group-sync-operator, phase:\
    \ Active, creationTimestamp: \"2026-01-01T00:00:00Z\",\n       labels: {\"team\": \"platform\",\n\
    \                \"company.net/mnemonic\": \"gso\", \"company.net/app-environment\": \"prod\"}}\n\
    \    - {name: demo-prod, phase: Active, creationTimestamp: \"2026-01-04T00:00:00Z\",\n       labels:\
    \ {\"company.net/mnemonic\": \"demo\", \"company.net/app-environment\": \"prod\"}}\n    - {name: demo-qa,\
    \ phase: Active, creationTimestamp: \"2026-01-05T00:00:00Z\",\n       labels: {\"company.net/mnemonic\"\
    : \"demo\", \"company.net/app-environment\": \"qa\"}}\n    - {name: beta-rnd, phase: Active, creationTimestamp:\
    \ \"2026-01-06T00:00:00Z\",\n       labels: {\"company.net/mnemonic\": \"beta\", \"company.net/app-environment\"\
    : \"rnd\"}}\n    - {name: platform-prod, phase: Active, creationTimestamp: \"2026-01-07T00:00:00Z\"\
    ,\n       labels: {\"company.net/mnemonic\": \"klta\", \"company.net/app-environment\": \"prod\"}}\n\
    \    # Missing-dimension NEGATIVE case: mnemonic only, no app-environment \u2014 it must drop out\
    \ of any\n    # two-dimension AND selection on app-environment (adversarial-review note, 2026-09-15).\n\
    \    - {name: gsd-shared, phase: Active, creationTimestamp: \"2026-01-08T00:00:00Z\",\n       labels:\
    \ {\"company.net/mnemonic\": \"gsd\"}}\n  forbidden: false\n\nroles:\n  clusterRoles:\n    - name:\
    \ cluster-admin\n      rules:\n        - {verbs: [\"*\"], apiGroups: [\"*\"], resources: [\"*\"]}\n\
    \    - name: cluster-reader\n      rules:\n        # Read verbs only \u2014 deliberately NO `update`,\
    \ which is what excludes the auditor\n        # (dana.lee) from the write-verb usage tier.\n     \
    \   - {verbs: [get, list, watch], apiGroups: [\"*\"], resources: [\"*\"]}\n    # The reporting-auditor\
    \ ClusterRole (chart renders <fullname>-report-auditor). Read-only get/list on\n    # identities and\
    \ RBAC \u2014 `list clusterrolebindings` is what lifts a member to the wide (auditor) tier.\n    -\
    \ name: group-sync-dashboard-report-auditor\n      rules:\n        - {verbs: [get, list], apiGroups:\
    \ [\"user.openshift.io\"], resources: [\"users\", \"groups\"]}\n        - {verbs: [get, list], apiGroups:\
    \ [\"rbac.authorization.k8s.io\"], resources: [\"roles\", \"rolebindings\", \"clusterroles\", \"clusterrolebindings\"\
    ]}\n  namespacedRoles:\n    - namespace: acme-app\n      name: viewer\n      rules:\n        - {verbs:\
    \ [get, list], apiGroups: [\"\"], resources: [pods]}\n\nbindings:\n  clusterRoleBindings:\n    - name:\
    \ cluster-admin-crb\n      roleRef: {kind: ClusterRole, name: cluster-admin}\n      subjects: [{kind:\
    \ Group, name: app-ocp-rbac-demo-cluster-admin}]\n      labels: {\"rbac.ocp.io/config-source\": \"\
    gitops\"}\n    - name: cluster-reader-crb\n      roleRef: {kind: ClusterRole, name: cluster-reader}\n\
    \      subjects: [{kind: Group, name: cluster-readers}]\n      labels: {\"rbac.ocp.io/config-source\"\
    : \"gitops\"}\n    # A hand-made grant with no config-source label \u2192 the `unmanaged` finding\
    \ the dashboard\n    # exists to surface; carries an operator-acknowledged exception annotation.\n\
    \    - name: handmade-reader-crb\n      roleRef: {kind: ClusterRole, name: cluster-reader}\n     \
    \ subjects: [{kind: Group, name: legacy-ops}]\n      annotations: {\"rbac.ocp.io/unmanaged-exception\"\
    : \"reviewed 2026-09-10, temporary\"}\n    # Binds the auditor group to the report-auditor role \u2192\
    \ its members (developer) are wide-tier auditors.\n    - name: report-auditors-crb\n      roleRef:\
    \ {kind: ClusterRole, name: group-sync-dashboard-report-auditor}\n      subjects: [{kind: Group, name:\
    \ app-ocp-rbac-demo-report-auditors}]\n      labels: {\"rbac.ocp.io/config-source\": \"gitops\"}\n\
    \  roleBindings:\n    - namespace: acme-app\n      name: viewer-rb\n      roleRef: {kind: Role, name:\
    \ viewer}\n      subjects: [{kind: User, name: lateef.o}]\n\noperatorConfigs:\n  namespaceConfigs:\n\
    \    - name: acme-nsconfig\n      conditions:\n        - {type: ReconcileSuccess, lastTransitionTime:\
    \ \"2026-09-14T08:00:00Z\"}\n  groupConfigs: []\n  namespaceConfigsCrdAbsent: false\n  groupConfigsCrdAbsent:\
    \ false\n\nnodes:\n  entries:\n    - {name: master-0, labels: {\"node-role.kubernetes.io/master\"\
    : \"\", \"node-role.kubernetes.io/control-plane\": \"\"}}\n    - {name: master-1, labels: {\"node-role.kubernetes.io/master\"\
    : \"\"}}\n    - {name: worker-0, labels: {\"node-role.kubernetes.io/worker\": \"\"}}\n  forbidden:\
    \ false\n\noauth:\n  identityProviders:\n    - name: acme-ldap\n      ldapUrl: \"ldaps://openldap.acme.svc:636/dc=acme,dc=com?uid?sub?(&(uid=*)(memberOf=cn=ocp-admins,ou=Groups,dc=acme,dc=com))\"\
    \n  forbidden: false\n  crdAbsent: false\n\noauthPods:\n  namespace: openshift-authentication\n  entries:\n\
    \    - {name: oauth-openshift-6d8f9c7b4-abcde, phase: Running}\n    - {name: oauth-openshift-6d8f9c7b4-fghij,\
    \ phase: Running}\n    - {name: oauth-openshift-6d8f9c7b4-pending, phase: Pending}\n  forbidden: false\n\
    \nauditLog:\n  node: master-0\n  dir: oauth-server\n  malformed416: false\n  files:\n    - name: \"\
    audit-2026-09-01T00-00-00.000.log\"     # a rotated backup (lumberjack form)\n      lines:\n     \
    \   - {kind: session, decision: allow, user: dana.lee, at: \"2026-09-01T09:00:00.000000Z\", code:\
    \ 302}\n    - name: audit.log                                # the live file\n      lines:\n     \
    \   - {kind: credential, decision: allow, user: jane.smith, at: \"2026-09-03T10:15:27.234567Z\", code:\
    \ 302, provider: acme-ldap}\n        - {kind: cli,        decision: deny,  user: lateef.o,   at: \"\
    2026-09-03T10:16:01.000000Z\", code: 401}\n        - {kind: session,    decision: allow, user: dana.lee,\
    \   at: \"2026-09-03T10:17:44.500000Z\", code: 302}\n\npodLog:\n  namespace: openshift-authentication\n\
    \  lines:\n    - '2026-09-03T10:15:27.234567Z I0903 10:15:27.234567 1 login.go:191] Login with provider\
    \ \"acme-ldap\" succeeded for \"jane.smith\"'\n    - '2026-09-03T10:16:01.000000Z I0903 10:16:01.000000\
    \ 1 basicauth.go:48] Login with provider \"acme-ldap\" failed for login \"lateef.o\"'\n"
kind: ConfigMap
metadata:
  name: mock-fixture
```

New text:

```text
apiVersion: v1
data:
  reference.yaml: "# reference.yaml \u2014 a small reference cluster that reproduces the four measured personas.\n#\n# The SAR oracle (DESIGN \xA75.4), which test_sar_personas.py asserts:\n#\n#   persona      fixture RBAC                                   list crb (wide)  update crb (usage)\n#   kubeadmin    cluster-admin CRB                              ALLOW            ALLOW\n#   dana.lee     cluster-reader CRB (read verbs, no update)     ALLOW            DENY\n#   lateef.o     no admin CRB                                   DENY             DENY\n#   jane.smith   in a group NAMED \"...-cluster-admin\" but with  DENY             DENY\n#                NO ClusterRoleBinding behind it (the decoy)\n#\n# The decoy is the point: a suggestively-named group must NOT grant the tier \u2014 only a real\n# (Cluster)RoleBinding reaching one of spec.groups/spec.user does.\n\nmeta:\n  clusterName: mock-openshift\n  token: \"mock-token-reference\"\n\ngroupsyncs:\n  - name: ldap-sync\n    namespace: group-sync-operator\n    generation: 3\n    schedule: \"*/30 * * * *\"\n    providers:\n      - {name: acme-ldap, kind: rfc2307, filter: \"(objectClass=groupOfNames)\"}\n    lastSyncSuccessTime: \"2026-09-14T08:00:00Z\"\n    conditions:\n      - {type: ReconcileSuccess, lastTransitionTime: \"2026-09-14T08:00:00Z\"}\n  - crdAbsent: false\n\ngroups:\n  # Bound to cluster-admin via cluster-admin-crb \u2192 grants kubeadmin the wide + usage tiers.\n  - name: app-ocp-rbac-demo-cluster-admin\n    syncProvider: acme-ldap\n    syncTime: \"2026-09-14T08:00:00Z\"\n    ldapUid: \"cn=ocp-admins,ou=Groups,dc=acme,dc=com\"\n    users: [kubeadmin]\n  # Bound to cluster-reader via cluster-reader-crb \u2192 dana.lee gets wide but not usage.\n  - name: cluster-readers\n    syncProvider: acme-ldap\n    syncTime: \"2026-09-14T08:00:00Z\"\n    users: [dana.lee]\n  # THE DECOY: name ends \"-cluster-admin\" but nothing binds it. jane.smith must stay self.\n  - name: platform-team-cluster-admin\n    syncProvider: acme-ldap\n    syncTime: \"2026-09-14T08:00:00Z\"\n    users: [jane.smith]\n  # An ordinary application group with a namespaced viewer grant to a direct user.\n  - name: acme-app-viewers\n    syncProvider: acme-ldap\n    syncTime: \"2026-09-14T08:00:00Z\"\n    users: [lateef.o]\n  # An empty group (the API returns users: null) \u2014 exercises the null-users branch.\n  - name: empty-team\n    syncProvider: acme-ldap\n    users: null\n  # A legacy group carrying a non-person service account; the target of the hand-made\n  # (unmanaged) binding below. Deliberately holds NO persona, so it cannot perturb the oracle.\n  - name: legacy-ops\n    syncProvider: acme-ldap\n    users: [svc-legacy]\n  # The reporting-auditor group (rbacAuditors, #100): bound to the report-auditor ClusterRole below,\n  # which grants `list clusterrolebindings` \u2014 the wide-tier gate \u2014 so its members are AUDITORS (wide\n  # read-only, NOT usage). developer is a member, to test the auditor tier on the mock.\n  - name: app-ocp-rbac-demo-report-auditors\n    syncProvider: acme-ldap\n    syncTime: \"2026-09-14T08:00:00Z\"\n    users: [developer]\n\nusers:\n  entries:\n    - {name: kubeadmin,  fullName: \"Cluster Admin\", creationTimestamp: \"2026-01-01T00:00:00Z\",\n       identities: []}\n    - {name: dana.lee,   fullName: \"Dana Lee\",      creationTimestamp: \"2026-01-02T00:00:00Z\",\n       identities: [\"acme-ldap:dana.lee\"]}\n    - {name: lateef.o,   fullName: \"Lateef O.\",     creationTimestamp: \"2026-01-03T00:00:00Z\",\n       identities: [\"acme-ldap:lateef.o\"]}\n    - {name: jane.smith, fullName: \"Jane Smith\",    creationTimestamp: \"2026-01-04T00:00:00Z\",\n       identities: [\"acme-ldap:jane.smith\"]}\n    # The developer persona: member of the reporting-auditor group below, so it exercises the AUDITOR\n    # (wide read-only) tier \u2014 a member of a feature-granting group, for testing \"who belongs to it\".\n    - {name: developer,  fullName: \"Developer\",     creationTimestamp: \"2026-01-05T00:00:00Z\",\n       identities: [\"developer:developer\"]}\n  forbidden: false\n\nidentities:\n  entries:\n    - {userName: dana.lee,   creationTimestamp: \"2026-01-02T00:00:00Z\", providerPrefix: acme-ldap}\n    - {userName: lateef.o,   creationTimestamp: \"2026-01-03T00:00:00Z\", providerPrefix: acme-ldap}\n    - {userName: jane.smith, creationTimestamp: \"2026-01-04T00:00:00Z\", providerPrefix: acme-ldap}\n    - {userName: developer,  creationTimestamp: \"2026-01-05T00:00:00Z\", providerPrefix: developer}\n  forbidden: false\n\nnamespaces:\n  entries:\n    # Two selector dimensions \u2014 company.net/mnemonic AND company.net/app-environment \u2014 mirroring the\n    # real crc-local convention (docs/DESIGN_reporting_selectors_snapshots_and_windows.md \xA76), so the\n    # multi-dimension selector (AND across dimensions, OR within one) is exercisable against the mock.\n    # `team` is kept on the first two so the single-label tests still hold.\n    - {name: acme-app, phase: Active, creationTimestamp: \"2026-01-02T00:00:00Z\",\n       labels: {\"team\": \"acme\", \"kubernetes.io/metadata.name\": \"acme-app\",\n                \"company.net/mnemonic\": \"acme\", \"company.net/app-environment\": \"prod\"}}\n    - {name: group-sync-operator, phase: Active, creationTimestamp: \"2026-01-01T00:00:00Z\",\n       labels: {\"team\": \"platform\",\n                \"company.net/mnemonic\": \"gso\", \"company.net/app-environment\": \"prod\"}}\n    - {name: demo-prod, phase: Active, creationTimestamp: \"2026-01-04T00:00:00Z\",\n       labels: {\"company.net/mnemonic\": \"demo\", \"company.net/app-environment\": \"prod\"}}\n    - {name: demo-qa, phase: Active, creationTimestamp: \"2026-01-05T00:00:00Z\",\n       labels: {\"company.net/mnemonic\": \"demo\", \"company.net/app-environment\": \"qa\"}}\n    - {name: beta-rnd, phase: Active, creationTimestamp: \"2026-01-06T00:00:00Z\",\n       labels: {\"company.net/mnemonic\": \"beta\", \"company.net/app-environment\": \"rnd\"}}\n    - {name: platform-prod, phase: Active, creationTimestamp: \"2026-01-07T00:00:00Z\",\n       labels: {\"company.net/mnemonic\": \"klta\", \"company.net/app-environment\": \"prod\"}}\n    # Missing-dimension NEGATIVE case: mnemonic only, no app-environment \u2014 it must drop out of any\n    # two-dimension AND selection on app-environment (adversarial-review note, 2026-09-15).\n    - {name: gsd-shared, phase: Active, creationTimestamp: \"2026-01-08T00:00:00Z\",\n       labels: {\"company.net/mnemonic\": \"gsd\"}}\n  forbidden: false\n\nroles:\n  clusterRoles:\n    - name: cluster-admin\n      rules:\n        - {verbs: [\"*\"], apiGroups: [\"*\"], resources: [\"*\"]}\n    - name: cluster-reader\n      rules:\n        # Read verbs only \u2014 deliberately NO `update`, which is what excludes the auditor\n        # (dana.lee) from the write-verb usage tier.\n        - {verbs: [get, list, watch], apiGroups: [\"*\"], resources: [\"*\"]}\n    # The reporting-auditor ClusterRole (chart renders <fullname>-report-auditor). Read-only get/list on\n    # identities and RBAC \u2014 `list clusterrolebindings` is what lifts a member to the wide (auditor) tier.\n    - name: group-sync-dashboard-report-auditor\n      rules:\n        - {verbs: [get, list], apiGroups: [\"user.openshift.io\"], resources: [\"users\", \"groups\"]}\n        - {verbs: [get, list], apiGroups: [\"rbac.authorization.k8s.io\"], resources: [\"roles\", \"rolebindings\", \"clusterroles\", \"clusterrolebindings\"]}\n  namespacedRoles:\n    - namespace: acme-app\n      name: viewer\n      rules:\n        - {verbs: [get, list], apiGroups: [\"\"], resources: [pods]}\n\nbindings:\n  clusterRoleBindings:\n    - name: cluster-admin-crb\n      roleRef: {kind: ClusterRole, name: cluster-admin}\n      subjects: [{kind: Group, name: app-ocp-rbac-demo-cluster-admin}]\n      labels: {\"rbac.ocp.io/config-source\": \"gitops\"}\n    - name: cluster-reader-crb\n      roleRef: {kind: ClusterRole, name: cluster-reader}\n      subjects: [{kind: Group, name: cluster-readers}]\n      labels: {\"rbac.ocp.io/config-source\": \"gitops\"}\n    # A hand-made grant with no config-source label \u2192 the `unmanaged` finding the dashboard\n    # exists to surface; carries an operator-acknowledged exception annotation.\n    - name: handmade-reader-crb\n      roleRef: {kind: ClusterRole, name: cluster-reader}\n      subjects: [{kind: Group, name: legacy-ops}]\n      annotations: {\"rbac.ocp.io/unmanaged-exception\": \"reviewed 2026-09-10, temporary\"}\n    # Binds the auditor group to the report-auditor role \u2192 its members (developer) are wide-tier auditors.\n    - name: report-auditors-crb\n      roleRef: {kind: ClusterRole, name: group-sync-dashboard-report-auditor}\n      subjects: [{kind: Group, name: app-ocp-rbac-demo-report-auditors}]\n      labels: {\"rbac.ocp.io/config-source\": \"gitops\"}\n  roleBindings:\n    - namespace: acme-app\n      name: viewer-rb\n      roleRef: {kind: Role, name: viewer}\n      subjects: [{kind: User, name: lateef.o}]\n\noperatorConfigs:\n  namespaceConfigs:\n    - name: acme-nsconfig\n      conditions:\n        - {type: ReconcileSuccess, lastTransitionTime: \"2026-09-14T08:00:00Z\"}\n  groupConfigs: []\n  namespaceConfigsCrdAbsent: false\n  groupConfigsCrdAbsent: false\n\nnodes:\n  entries:\n    - {name: master-0, labels: {\"node-role.kubernetes.io/master\": \"\", \"node-role.kubernetes.io/control-plane\": \"\"}}\n    - {name: master-1, labels: {\"node-role.kubernetes.io/master\": \"\"}}\n    - {name: worker-0, labels: {\"node-role.kubernetes.io/worker\": \"\"}}\n  forbidden: false\n\noauth:\n  identityProviders:\n    - name: acme-ldap\n      ldapUrl: \"ldaps://openldap.acme.svc:636/dc=acme,dc=com?uid?sub?(&(uid=*)(memberOf=cn=ocp-admins,ou=Groups,dc=acme,dc=com))\"\n  forbidden: false\n  crdAbsent: false\n\nauditLog:\n  node: master-0\n  dir: oauth-server\n  malformed416: false\n  files:\n    - name: \"audit-2026-09-01T00-00-00.000.log\"     # a rotated backup (lumberjack form)\n      lines:\n        - {kind: session, decision: allow, user: dana.lee, at: \"2026-09-01T09:00:00.000000Z\", code: 302}\n    - name: audit.log                                # the live file\n      lines:\n        - {kind: credential, decision: allow, user: jane.smith, at: \"2026-09-03T10:15:27.234567Z\", code: 302, provider: acme-ldap}\n        - {kind: cli,        decision: deny,  user: lateef.o,   at: \"2026-09-03T10:16:01.000000Z\", code: 401}\n        - {kind: session,    decision: allow, user: dana.lee,   at: \"2026-09-03T10:17:44.500000Z\", code: 302}\n"
kind: ConfigMap
metadata:
  name: mock-fixture
```

### Block 57 — local-development/tests/test_logincapture_loop.py

Retire the whole file. Empty New is the checker-compatible deletion payload; see deletion protocol.
Baseline: local-development/tests/test_logincapture_loop.py:1; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_logincapture_loop.py | edit -->

Old text:

```python
"""The capture loop: what it reads, what it writes, and what it refuses to do.

THE LOOP'S CONTRACT IS MOSTLY ABOUT NOT DOING THINGS, which is why it needs tests of its own rather
than being covered incidentally by the store's. It must never take the group poll down; it must not
write when it has lost the lease; it must not stamp a successful read when no pod answered; and it must
advance its watermark, because the first draft did not and the read grew without bound.

A FAKE CLUSTER, NOT A MOCKED ONE. The double below implements the two methods capture_once calls and
records the `since_seconds` it was asked for, so the read WINDOW — the part that decides whether an
attempt is seen twice or missed — is asserted rather than assumed. capture_once constructs its own
ClusterClient, so the class is swapped in the module under test.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

import pytest

from gsd import logincapture, loginlog
from gsd.config import ClusterConfig, Settings
from gsd.kube import ClusterError
from gsd.logincapture import (
    FIRST_SIGHT_SECONDS,
    OVERLAP_SECONDS,
    SETTLE_SECONDS,
    capture_once,
    event_dict,
)
from gsd.loginlog import LoginAttempt
from gsd.store import Store

CLUSTER = ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")
POD = "oauth-openshift-66444df7fc-nccmh"

# A real attempt, verbatim from the cluster: the HTPasswd failure that is not a failed login, the
# directory search, and the success. Reused so every test drives the loop with lines it will actually
# meet rather than with a synthetic single line.
def _lines(when: datetime, user: str = "jane.smith", ok: bool = True) -> list[str]:
    stamp = when.strftime("%Y-%m-%dT%H:%M:%S.%f000Z")
    verdict = "succeeded" if ok else "failed"
    return [
        f'{stamp} I0807 23:48:57.591365       1 basicauth.go:48] '
        f'Login with provider "developer" failed for login "{user}"',
        f'{stamp} I0807 23:48:57.687787       1 ldap.go:131] searching for (uid={user})',
        f'{stamp} I0807 23:48:58.035917       1 basicauth.go:51] '
        f'Login with provider "ldap-local" {verdict} for login "{user}"',
    ]


class FakeClient:
    """The two methods capture_once calls, plus a record of how it was called."""

    #: Distinguishes "no pods argument given" from "fetch_oauth_pods returns None", which is what
    #: the real client does for FORBIDDEN. `pods=None` alone could not say the second thing.
    DEFAULT = object()

    def __init__(self, pods=DEFAULT, logs=None, list_error=None, log_error=None):
        self._pods = [POD] if pods is FakeClient.DEFAULT else pods
        self._logs = logs or {}
        self._list_error = list_error
        self._log_error = log_error
        self.since_by_pod: dict[str, int] = {}
        self.log_calls: list[str] = []

    def fetch_oauth_pods(self, namespace):
        self.namespace = namespace
        if self._list_error:
            raise self._list_error
        return self._pods

    def fetch_pod_log(self, namespace, pod_name, since_seconds=None, **kw):
        self.log_calls.append(pod_name)
        self.since_by_pod[pod_name] = since_seconds
        if self._log_error and pod_name in self._log_error:
            raise self._log_error[pod_name]
        return self._logs.get(pod_name)


class FakeElector:
    """Leadership that can change between the read and the write, which is the whole point."""

    def __init__(self, leader=True, lose_after=None):
        self._leader = leader
        self._lose_after = lose_after
        self.checks = 0

    @property
    def is_leader(self):
        self.checks += 1
        if self._lose_after is not None and self.checks > self._lose_after:
            return False
        return self._leader


@pytest.fixture()
def store(tmp_path):
    s = Store(str(tmp_path / "capture.db"))
    s.upsert_cluster(CLUSTER.name, CLUSTER.api_url, True)
    yield s
    s.close()


@pytest.fixture()
def settings(tmp_path):
    return Settings(clusters=[CLUSTER], db_path=str(tmp_path / "capture.db"),
                    login_capture_enabled=True)


@pytest.fixture()
def install(monkeypatch):
    """Swap the client class capture_once constructs, and hand back the instance it used."""
    def _install(client):
        monkeypatch.setattr(logincapture, "ClusterClient", lambda *a, **kw: client)
        return client
    return _install


def _old_enough(seconds=SETTLE_SECONDS + 60) -> datetime:
    """An instant far enough in the past that the settle horizon considers it finished."""
    return datetime.now(UTC) - timedelta(seconds=seconds)


class TestItNeverTakesThePollDown:
    """capture_once must not raise for a cluster problem. Group polling is a separate concern with a
    separate failure mode, and a broken log read must not stop groups being observed."""

    def test_disabled_does_nothing_at_all(self, store, settings, monkeypatch):
        settings = Settings(clusters=[CLUSTER], db_path=settings.db_path,
                            login_capture_enabled=False)

        def explode(*a, **kw):  # pragma: no cover - must not be reached
            raise AssertionError("a cluster client was constructed with capture disabled")

        monkeypatch.setattr(logincapture, "ClusterClient", explode)
        assert capture_once(store, CLUSTER, settings) == 0

    def test_a_failed_pod_list_is_logged_and_swallowed(self, store, settings, install, caplog):
        install(FakeClient(list_error=ClusterError("auth_failed", "401 Unauthorized")))
        with caplog.at_level(logging.WARNING):
            assert capture_once(store, CLUSTER, settings) == 0
        assert "group data is unaffected" in caplog.text
        assert "401 Unauthorized" in caplog.text

    def test_a_forbidden_pod_list_records_nothing(self, store, settings, install):
        """fetch_oauth_pods returns None for FORBIDDEN — a missing grant, not a fault."""
        install(FakeClient(pods=None))
        assert capture_once(store, CLUSTER, settings) == 0
        assert store.login_capture_status(CLUSTER.name) in (None, {})

    def test_no_running_pods_records_nothing(self, store, settings, install):
        install(FakeClient(pods=[]))
        assert capture_once(store, CLUSTER, settings) == 0

    def test_one_pod_failing_does_not_stop_the_others(self, store, settings, install):
        when = _old_enough()
        client = install(FakeClient(
            pods=["pod-a", "pod-b"],
            logs={"pod-b": _lines(when, "jane.smith")},
            log_error={"pod-a": ClusterError("error", "read timed out")},
        ))
        assert capture_once(store, CLUSTER, settings) == 1
        assert client.log_calls == ["pod-a", "pod-b"], "the loop stopped at the first failure"
        assert [a["user_name"] for a in store.login_events(CLUSTER.name)] == ["jane.smith"]

    def test_a_refused_read_returning_none_is_skipped_quietly(self, store, settings, install):
        """fetch_pod_log returns None for roll noise or a missing grant; both are already logged."""
        install(FakeClient(logs={POD: None}))
        assert capture_once(store, CLUSTER, settings) == 0


class TestTheReadWindow:
    def test_a_first_sight_looks_back_one_hour(self, store, settings, install):
        client = install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        assert client.since_by_pod[POD] == FIRST_SIGHT_SECONDS, (
            "with no watermark the read must be bounded, not unbounded: a long-lived pod at Debug "
            "would otherwise have its entire history re-read on every restart"
        )

    def test_a_watermark_is_re_read_with_an_overlap(self, store, settings, install):
        """An attempt is SEVERAL lines and they can straddle two reads.

        The success line may land in the window after the failure lines that precede it, so the
        overlap is what makes the whole attempt present in one parse. The dedup key makes the repeats
        free.
        """
        mark = (datetime.now(UTC) - timedelta(seconds=300)).strftime("%Y-%m-%dT%H:%M:%S.%f000Z")
        store.set_login_watermark(CLUSTER.name, POD, mark, "x")
        client = install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        since = client.since_by_pod[POD]
        assert 300 + OVERLAP_SECONDS <= since <= 300 + OVERLAP_SECONDS + 5, since

    def test_an_unparsable_watermark_falls_back_to_a_first_sight(self, store, settings, install):
        """Rather than reading zero seconds and silently capturing nothing ever again."""
        store.set_login_watermark(CLUSTER.name, POD, "not-a-timestamp", "x")
        client = install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        assert client.since_by_pod[POD] == FIRST_SIGHT_SECONDS

    def test_each_pod_carries_its_own_window(self, store, settings, install):
        """Two replicas serve different attempts, so one shared position would skip lines."""
        mark = (datetime.now(UTC) - timedelta(seconds=200)).strftime("%Y-%m-%dT%H:%M:%S.%f000Z")
        store.set_login_watermark(CLUSTER.name, "pod-a", mark, "x")
        client = install(FakeClient(pods=["pod-a", "pod-b"], logs={"pod-a": [], "pod-b": []}))
        capture_once(store, CLUSTER, settings)
        assert client.since_by_pod["pod-b"] == FIRST_SIGHT_SECONDS
        assert client.since_by_pod["pod-a"] < FIRST_SIGHT_SECONDS


class TestTheSettleHorizon:
    """The bug that shipped into the first draft, and the reason it is measured from NOW.

    Measuring from the newest attempt in the BATCH means a burst of logins inside SETTLE_SECONDS makes
    every one of them unsettled relative to its own peers, so the watermark never advances at all: the
    same window is re-read forever, sinceSeconds stays at first-sight, and the read grows without
    bound. It was caught by the healthy path writing zero watermarks — which is why the first test here
    asserts a watermark exists rather than only that events were recorded.
    """

    def test_the_healthy_path_advances_the_watermark(self, store, settings, install):
        install(FakeClient(logs={POD: _lines(_old_enough())}))
        assert capture_once(store, CLUSTER, settings) == 1
        assert POD in store.login_watermarks(CLUSTER.name), (
            "events were recorded and the read position was not advanced — the next cycle re-reads "
            "the same window, forever"
        )

    def test_a_burst_inside_the_horizon_still_advances_it(self, store, settings, install):
        """Ten logins within a second of each other, all comfortably older than the horizon.

        Under the original bug every one of these was 'unsettled' because it was within
        SETTLE_SECONDS of its neighbours, and nothing advanced.
        """
        base = _old_enough()
        lines = []
        for i in range(10):
            lines += _lines(base + timedelta(milliseconds=100 * i), f"user{i}")
        install(FakeClient(logs={POD: lines}))
        assert capture_once(store, CLUSTER, settings) == 10
        assert POD in store.login_watermarks(CLUSTER.name)

    def test_attempts_newer_than_the_horizon_are_withheld_not_written(
            self, store, settings, install):
        """A read can slice a live attempt mid-flight: the chain `failed` line has arrived, the
        success that follows it has not. Concluded from partial lines it records a failure that
        never happened, and the dedup key cannot collapse that with the finished attempt because
        the outcome differs. So nothing inside the settle window is written yet — the watermark
        holds behind it, and OVERLAP_SECONDS > SETTLE_SECONDS + ATTEMPT_WINDOW guarantees the next
        cycle re-reads the whole attempt."""
        install(FakeClient(logs={POD: _lines(datetime.now(UTC))}))
        assert capture_once(store, CLUSTER, settings) == 0
        assert store.login_events(CLUSTER.name) == []
        assert store.login_watermarks(CLUSTER.name) == {}, (
            "the position advanced past an attempt whose lines may still be arriving"
        )
    def test_the_horizon_is_the_newest_settled_line(self):
        """Any timestamped line proves the log was read through that instant, so any timestamped
        line may advance the cursor — attempts are not required (the quiet-pod case), and a line
        newer than the horizon may not (its attempt can still be arriving)."""
        now = datetime.now(UTC)
        def line(when):
            return f"{when.strftime('%Y-%m-%dT%H:%M:%S.%fZ')} I0807 0:0:0.0 1 httplog.go:1] request"
        settled = now - timedelta(seconds=SETTLE_SECONDS + 30)
        horizon = logincapture._settle_horizon([
            line(now - timedelta(seconds=SETTLE_SECONDS + 90)),
            line(settled),
            line(now),                                   # newer than the horizon
        ])
        assert horizon == settled.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    def test_a_sliced_read_cannot_record_a_failure_that_never_happened(
            self, store, settings, install, monkeypatch):
        """The regression the withholding exists for, end to end: first read ends between the
        provider-chain `failed` line and the success; the next read has the whole attempt. One
        person, one login, one row — never a failed row beside the success it belonged to."""
        whole = _lines(datetime.now(UTC) - timedelta(seconds=2))
        client = install(FakeClient(logs={POD: whole[:1]}))
        capture_once(store, CLUSTER, settings)          # sliced: chain-failure line only
        client._logs = {POD: whole}
        monkeypatch.setattr(logincapture, "SETTLE_SECONDS", 0)   # the attempt ages past the window
        capture_once(store, CLUSTER, settings)
        rows = store.login_events(CLUSTER.name)
        assert [(r["user_name"], r["outcome"]) for r in rows] == [
            ("jane.smith", loginlog.OUTCOME_SUCCESS)
        ], rows
    def test_non_login_lines_advance_a_quiet_pods_watermark(self, store, settings, install):
        """The cursor follows successfully read log time, not only business events.

        A pod that logs plenty and authenticates nobody otherwise pins its watermark forever:
        sinceSeconds grows by a poll interval per cycle for the life of the pod, and once the
        window outgrows the byte cap the newest lines are deferred every cycle while capture
        still stamps itself live."""
        old = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        recent = datetime.now(UTC) - timedelta(seconds=SETTLE_SECONDS + 10)
        stamp = recent.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        progress = f"{stamp} I0807 00:00:00.0 1 httplog.go:1] ordinary request"
        store.set_login_watermark(CLUSTER.name, POD, old, "x")
        install(FakeClient(logs={POD: [progress]}))
        capture_once(store, CLUSTER, settings)
        assert store.login_watermarks(CLUSTER.name)[POD] == stamp
    def test_no_settled_lines_means_no_horizon(self):
        assert logincapture._settle_horizon([]) is None
        now_line = (f"{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%S.%fZ')} "
                    "I0807 0:0:0.0 1 httplog.go:1] request")
        assert logincapture._settle_horizon([now_line]) is None

class TestLeadership:
    """`poller.py` calls its own lease "BEST-EFFORT admission control, NOT a write fence".

    That is fine for group polling and not fine here, because this reads logs over the network: the
    check can pass, the read can block, the lease can pass to another replica, and the old leader's
    read can then return and write. So leadership is rechecked immediately before the write.
    """

    def test_a_standby_writes_nothing(self, store, settings, install):
        install(FakeClient(logs={POD: _lines(_old_enough())}))
        assert capture_once(store, CLUSTER, settings, elector=FakeElector(leader=False)) == 0
        assert store.login_events(CLUSTER.name) == []
        assert store.login_capture_status(CLUSTER.name) in (None, {})

    def test_losing_the_lease_during_the_read_discards_the_events(
            self, store, settings, install, caplog):
        """The sequence Codex named: leader check true, log GET blocks, lease lost, GET returns.

        The recheck cannot CLOSE that window — closing it needs a fencing token the lease does not
        provide — but it narrows it from the length of a log read to a few instructions, and nothing
        may be written on the far side of it.
        """
        install(FakeClient(logs={POD: _lines(_old_enough())}))
        elector = FakeElector(leader=True, lose_after=0)
        with caplog.at_level(logging.INFO):
            assert capture_once(store, CLUSTER, settings, elector=elector) == 0
        assert store.login_events(CLUSTER.name) == []
        assert store.login_watermarks(CLUSTER.name) == {}
        assert "lost leadership while reading" in caplog.text

    def test_what_was_already_written_is_still_returned(self, store, settings, install):
        """Losing the lease mid-loop reports the events already committed, not zero.

        Two pods, leadership lost between them: the first pod's events are written and counted, the
        second pod's are discarded. Reporting zero would say nothing happened when something did.
        """
        when = _old_enough()
        install(FakeClient(pods=["pod-a", "pod-b"],
                           logs={"pod-a": _lines(when, "first"),
                                 "pod-b": _lines(when, "second")}))
        # One check passes (pod-a's write), the next fails (pod-b's).
        assert capture_once(store, CLUSTER, settings, elector=FakeElector(lose_after=1)) == 1
        assert [a["user_name"] for a in store.login_events(CLUSTER.name)] == ["first"]

    def test_the_recheck_happens_after_the_read_not_only_before(self, store, settings, install):
        """If leadership were checked once at the top, a lease lost during the read would go
        unnoticed. The elector counts its calls, so this asserts the check is made per write."""
        install(FakeClient(logs={POD: _lines(_old_enough())}))
        elector = FakeElector(leader=True)
        capture_once(store, CLUSTER, settings, elector=elector)
        assert elector.checks >= 2, (
            f"leadership was consulted {elector.checks} time(s); the write needs its own check"
        )


class TestLivenessAndTheWindowTheUiShows:
    def test_a_successful_read_stamps_the_status(self, store, settings, install):
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        status = store.login_capture_status(CLUSTER.name)
        assert status["started_at"] and status["last_read_at"]

    def test_started_at_does_not_move_on_later_cycles(self, store, settings, install):
        """It is what lets the page say when watching began. If it drifted forward, an empty list
        would look like a fresh start rather than a quiet cluster."""
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        first = store.login_capture_status(CLUSTER.name)["started_at"]
        capture_once(store, CLUSTER, settings)
        assert store.login_capture_status(CLUSTER.name)["started_at"] == first

    def test_a_cycle_where_no_pod_answered_does_not_claim_a_read(self, store, settings, install):
        """`last_read_at` is the liveness signal the page uses to say capture has stopped.

        Stamping it when every read was refused would make a broken capture look healthy, and
        `started_at` would then claim we had been watching since a cycle that saw nothing.
        """
        install(FakeClient(logs={POD: None}))
        capture_once(store, CLUSTER, settings)
        assert store.login_capture_status(CLUSTER.name) in (None, {}), (
            "a cycle in which no pod answered stamped a successful read"
        )

    def test_an_empty_log_is_a_successful_read(self, store, settings, install):
        """Capture on with Debug off reads real logs and finds nothing. That is correct, not broken,
        and it must still register as liveness — otherwise the page reports capture as stopped on a
        cluster where it is working perfectly and simply has nothing to see."""
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        assert store.login_capture_status(CLUSTER.name)["last_read_at"]


class TestPruning:
    def test_read_positions_for_dead_pods_are_forgotten(self, store, settings, install):
        """Every oauth roll replaces the pods. _prune's docstring claimed to do this and did not, so
        the table grew by one row per pod name the cluster had ever had."""
        store.set_login_watermark(CLUSTER.name, "pod-gone", "2026-08-07T23:00:00.000000Z", "x")
        store.set_login_watermark(CLUSTER.name, POD, "2026-08-07T23:00:00.000000Z", "x")
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        assert list(store.login_watermarks(CLUSTER.name)) == [POD]

    def test_a_standby_does_not_prune(self, store, settings, install):
        store.set_login_watermark(CLUSTER.name, "pod-gone", "2026-08-07T23:00:00.000000Z", "x")
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings, elector=FakeElector(leader=False))
        assert "pod-gone" in store.login_watermarks(CLUSTER.name)

    def test_positions_are_pruned_even_when_every_read_failed(self, store, settings, install):
        """On the strength of the POD LIST, which succeeded. A cluster whose reads are all refused is
        the case most likely to accumulate dead positions, so gating this on a successful read would
        leak exactly where it matters."""
        store.set_login_watermark(CLUSTER.name, "pod-gone", "2026-08-07T23:00:00.000000Z", "x")
        install(FakeClient(logs={POD: None}))
        capture_once(store, CLUSTER, settings)
        assert "pod-gone" not in store.login_watermarks(CLUSTER.name)

    def test_events_past_retention_are_dropped(self, store, settings, install, tmp_path):
        old = datetime.now(UTC) - timedelta(days=500)
        store.record_login_events(CLUSTER.name, [event_dict(
            LoginAttempt("ancient", loginlog.OUTCOME_FAILED, old, provider="ldap-local"),
            POD, "2026-01-01T00:00:00Z")])
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        assert store.login_events(CLUSTER.name) == []

    def test_retention_zero_keeps_everything(self, store, install, tmp_path):
        """0 disables retention deliberately — for a cluster that must keep the whole record."""
        s = Settings(clusters=[CLUSTER], db_path=str(tmp_path / "x.db"),
                     login_capture_enabled=True, login_retention_days=0)
        old = datetime.now(UTC) - timedelta(days=5000)
        store.record_login_events(CLUSTER.name, [event_dict(
            LoginAttempt("ancient", loginlog.OUTCOME_FAILED, old, provider="ldap-local"),
            POD, "2026-01-01T00:00:00Z")])
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, s)
        assert [a["user_name"] for a in store.login_events(CLUSTER.name)] == ["ancient"]

    def test_disabling_retention_does_not_disable_position_cleanup(self, store, install, tmp_path):
        """They are unrelated: one is a policy about how long to keep data, the other is a leak."""
        s = Settings(clusters=[CLUSTER], db_path=str(tmp_path / "x.db"),
                     login_capture_enabled=True, login_retention_days=0)
        store.set_login_watermark(CLUSTER.name, "pod-gone", "2026-08-07T23:00:00.000000Z", "x")
        install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, s)
        assert "pod-gone" not in store.login_watermarks(CLUSTER.name)


class TestEventDict:
    """The row shape, which is also the dedup key, so its format is load-bearing."""

    def test_the_pod_is_carried_because_it_is_in_the_key(self):
        row = event_dict(LoginAttempt("jane.smith", loginlog.OUTCOME_SUCCESS, datetime.now(UTC)),
                         POD, "2026-08-07T23:48:57Z")
        assert row["pod_name"] == POD

    def test_the_timestamp_keeps_microseconds_and_a_literal_z(self):
        """Two attempts one microsecond apart must not collide, and a format that varied between
        writer and reader would make the key match rows it should not."""
        at = datetime(2026, 8, 7, 23, 48, 57, 591593, tzinfo=UTC)
        row = event_dict(LoginAttempt("x", loginlog.OUTCOME_SUCCESS, at), POD, "obs")
        assert row["at"] == "2026-08-07T23:48:57.591593Z"

    def test_it_carries_the_parser_fields_through_unchanged(self):
        made = LoginAttempt("jane.smith", loginlog.OUTCOME_BAD_PASSWORD, datetime.now(UTC),
                            provider="ldap-local", ldap_result_code=49,
                            detail="LDAP result code 49")
        row = event_dict(made, POD, "obs")
        assert (row["user_name"], row["outcome"], row["provider"], row["ldap_result_code"],
                row["detail"], row["observed_at"]) == (
            "jane.smith", loginlog.OUTCOME_BAD_PASSWORD, "ldap-local", 49,
            "LDAP result code 49", "obs")


class TestTheWholeLoopIsIdempotent:
    def test_running_it_twice_over_the_same_log_records_each_attempt_once(
            self, store, settings, install):
        """Which is what the overlap guarantees will happen on every real cycle."""
        lines = _lines(_old_enough())
        client = FakeClient(logs={POD: lines})
        install(client)
        assert capture_once(store, CLUSTER, settings) == 1
        assert capture_once(store, CLUSTER, settings) == 0
        assert len(store.login_events(CLUSTER.name)) == 1

    def test_the_namespace_comes_from_configuration(self, store, settings, install):
        client = install(FakeClient(logs={POD: []}))
        capture_once(store, CLUSTER, settings)
        assert client.namespace == settings.login_capture_namespace == "openshift-authentication"
```

New text:

```python
```

### Block 58 — local-development/tests/test_login_capture_cross_seam.py

Retire the whole file. Empty New is the checker-compatible deletion payload; see deletion protocol.
Baseline: local-development/tests/test_login_capture_cross_seam.py:1; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_login_capture_cross_seam.py | edit -->

Old text:

```python
"""The seam three files share: `loginlog.adopt` → the capture read window → the store's UNIQUE key.

AN ATTEMPT'S `at` IS NOT DECIDED BY THE LOGIN. It is decided by which lines the read returned.
`parse` stamps an attempt at its CAUSE when the cause is in the same read — `adopt` moves `first_at`
back to it, which `test_loginlog.py` asserts in as many words ("stamped at the cause, which is where
the attempt actually began") — and at its VERDICT when the cause fell outside the window. Both `at`
and `outcome` are components of `UNIQUE(cluster_id, pod_name, user_name, at, outcome)`, so one real
login read two different ways is two different rows and INSERT OR IGNORE cannot collapse them.

WHY THIS NEEDED A MODULE OF ITS OWN. `test_loginlog.py` proves the parse in both shapes and never
touches a store. `test_logincapture_loop.py` drives the loop, but its double returns the same lines
whatever window it is asked for — it asserts the `since_seconds` REQUESTED, which is the right
contract for what that suite covers and blind to this one, because nothing has ever clipped a log.
The failure this guards is the class deployment found and two review passes did not: a phantom row
beside a real one, stating something false about a named person.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from gsd import logincapture
from gsd.config import ClusterConfig, Settings
from gsd.logincapture import (FIRST_SIGHT_SECONDS, OVERLAP_SECONDS, SETTLE_SECONDS,
                             capture_once)
from gsd.loginlog import ATTEMPT_WINDOW, parse, parse_timestamp
from gsd.store import Store
from gsd.timeutil import now_iso

POD = "oauth-openshift-6b9f7c8d5-abcde"
CLUSTER = ClusterConfig("crc-local", "https://api.example", token_env="X")

# The measured browser+LDAP wrong-password sequence, from the session recorded in test_loginlog.py.
# The message bodies are verbatim; only the kubelet stamps move, for the reason _restamp exists there.
_SEARCH = ('I0808 00:01:50.757022       1 ldap.go:131] searching for (&(&(uid=*)'
           '(memberOf=cn=app-ssb-autobahnusers,ou=Groups,dc=ephico2real,dc=com))(uid=jane.smith))')
_FOUND = ('I0808 00:01:50.761246       1 ldap.go:148] found dn="uid=jane.smith,ou=People,'
          'dc=ephico2real,dc=com" for (&(&(uid=*)(memberOf=cn=app-ssb-autobahnusers,ou=Groups,'
          'dc=ephico2real,dc=com))(uid=jane.smith))')
_BIND = ('I0808 00:02:46.883110       1 ldap.go:152] error binding password for '
         '"uid=jane.smith,ou=People,dc=ephico2real,dc=com": LDAP Result Code 49 '
         '"Invalid Credentials": ')
_VERDICT = ('I0808 00:02:46.884152       1 login.go:183] Login with provider "ldap-local" '
            'failed for "jane.smith"')

# Offsets within the one attempt, in seconds. The bind→verdict figure is the MEASURED 1.167 ms —
# `00:02:46.883182023` to `00:02:46.884349367` — and is deliberately not widened: the width of that
# gap is the width of the slot a read boundary has to land in, so rounding it up would make the
# defect look likelier than the cluster's own logs say it is.
SEARCH_OFFSET = 0.000
FOUND_OFFSET = 0.004
BIND_OFFSET = 0.010
VERDICT_OFFSET = 0.011167


def _stamp(at: datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%S.%f000Z")


def _attempt_lines(begins: datetime) -> list[str]:
    """The four lines of one wrong-password attempt, anchored at `begins`."""
    return [
        f"{_stamp(begins + timedelta(seconds=SEARCH_OFFSET))} {_SEARCH}",
        f"{_stamp(begins + timedelta(seconds=FOUND_OFFSET))} {_FOUND}",
        f"{_stamp(begins + timedelta(seconds=BIND_OFFSET))} {_BIND}",
        f"{_stamp(begins + timedelta(seconds=VERDICT_OFFSET))} {_VERDICT}",
    ]


class WindowedClient:
    """A fake cluster that HONOURS `since_seconds`, slicing the log the way the kubelet does.

    The existing loop suite's double records the window it was asked for and returns the same lines
    regardless. That is the right contract for what it tests and blind to this one: a boundary can
    only clip an attempt if something actually slices.

    Deriving the cutoff from `since_seconds` rather than taking it as a parameter is deliberate, and
    a first draft of this file got it wrong. Imposing a cutoff directly decouples the lines returned
    from the window the loop believes it asked for — and the guard under test is defined in terms of
    that window, so it could never see the clip and the test passed while the defect stood.
    """

    def __init__(self, lines, pods=(POD,)):
        self._lines = list(lines)
        self._pods = list(pods)
        self.windows: list[int | None] = []
        self.returned: list[int] = []

    def fetch_oauth_pods(self, namespace):
        return list(self._pods)

    def fetch_pod_log(self, namespace, pod_name, since_seconds=None, **kw):
        self.windows.append(since_seconds)
        if since_seconds is None:
            out = list(self._lines)
        else:
            cutoff = datetime.now(UTC) - timedelta(seconds=since_seconds)
            out = [raw for raw in self._lines
                   if (ts := parse_timestamp(raw)) is not None and ts > cutoff]
        self.returned.append(len(out))
        return out


@pytest.fixture()
def store(tmp_path):
    s = Store(str(tmp_path / "crossseam.db"))
    s.upsert_cluster(CLUSTER.name, CLUSTER.api_url, True)
    yield s
    s.close()


@pytest.fixture()
def settings(tmp_path):
    return Settings(clusters=[CLUSTER], db_path=str(tmp_path / "crossseam.db"),
                    login_capture_enabled=True)


@pytest.fixture()
def install(monkeypatch):
    def _install(client):
        monkeypatch.setattr(logincapture, "ClusterClient", lambda *a, **kw: client)
        return client
    return _install


class TestTheParseShiftsTheStampWithTheWindow:
    """The premise, established on the parser alone before any store is involved.

    If these two reads agreed on `at` and `outcome`, the dedup key would collapse them and there
    would be nothing further to test.
    """

    def test_the_whole_attempt_is_stamped_at_its_cause(self):
        begins = datetime(2026, 8, 8, 0, 2, 46, tzinfo=UTC)
        got = parse(_attempt_lines(begins))
        assert len(got) == 1, got
        assert got[0].outcome == "bad_password"
        assert got[0].ldap_result_code == 49
        assert got[0].at == begins + timedelta(seconds=BIND_OFFSET), (
            "the attempt should carry the CAUSE's instant, not the verdict's"
        )

    def test_the_same_login_clipped_of_its_cause_is_stamped_at_its_verdict(self):
        begins = datetime(2026, 8, 8, 0, 2, 46, tzinfo=UTC)
        clipped = _attempt_lines(begins)[3:]            # the verdict alone, as a late window sees it
        got = parse(clipped)
        assert len(got) == 1, got
        assert got[0].outcome == "failed", "with no cause there is no code to classify"
        assert got[0].ldap_result_code is None
        assert got[0].at == begins + timedelta(seconds=VERDICT_OFFSET)

    def test_so_the_two_reads_disagree_on_both_key_columns(self):
        """`at` AND `outcome` both differ, and both are in UNIQUE(...) — hence two rows, not one."""
        begins = datetime(2026, 8, 8, 0, 2, 46, tzinfo=UTC)
        whole = parse(_attempt_lines(begins))[0]
        clipped = parse(_attempt_lines(begins)[3:])[0]
        assert whole.user_name == clipped.user_name
        assert whole.at != clipped.at
        assert whole.outcome != clipped.outcome


class TestOneLoginReadTwiceIsOneRow:
    """The invariant that matters: however the window falls, one login is one row.

    Cycle 1 reads the whole attempt. Cycle 2's window is made to open between the bind error and its
    verdict — the state the sweeping `watermark − OVERLAP_SECONDS` boundary reaches on its own — by
    setting the watermark that decides `since_seconds`, so the loop's real arithmetic does the slicing.

    THE GAP IS WIDENED HERE, to 0.5 s from the measured 1.167 ms, and only here. `since_seconds` is a
    whole number, so the boundary's position inside its second is fixed by the instant of the call:
    against a 1.167 ms gap the assertion would turn on milliseconds of scheduler noise. 0.5 s is still
    one attempt — ATTEMPT_WINDOW is a full second — and a directory that takes that long to answer a
    bind is ordinary. The measured width is asserted where it can be, in the parse-only tests above
    and in TestTheClipIsReachable.
    """

    # Chosen so `int(age) + OVERLAP_SECONDS` lands on a known integer, below.
    WINDOW = 94
    HALF_GAP = 0.25

    def _straddling_lines(self, t0: datetime) -> list[str]:
        """One attempt whose bind and verdict sit either side of `t0 - WINDOW`."""
        begins = t0 - timedelta(seconds=self.WINDOW + self.HALF_GAP + BIND_OFFSET)
        lines = _attempt_lines(begins)
        # Push the verdict to the far side of the boundary; the first three lines stay before it.
        verdict_at = t0 - timedelta(seconds=self.WINDOW - self.HALF_GAP)
        lines[3] = f"{_stamp(verdict_at)} {_VERDICT}"
        return lines

    def test_a_window_that_clips_the_cause_does_not_add_a_second_row(
            self, store, settings, install):
        t0 = datetime.now(UTC)
        lines = self._straddling_lines(t0)

        first = install(WindowedClient(lines))
        assert capture_once(store, CLUSTER, settings) == 1
        assert first.windows == [FIRST_SIGHT_SECONDS]
        assert first.returned == [4], "cycle 1 must see the whole attempt"
        rows = store.login_events(CLUSTER.name)
        assert [(r["user_name"], r["outcome"]) for r in rows] == [("jane.smith", "bad_password")], rows

        # Put the watermark where a steady-state cycle would have it, so the loop computes
        # since_seconds = int(age) + OVERLAP_SECONDS = 34 + 60 = WINDOW, opening the window inside
        # the gap. set_login_watermark takes max(), and this instant is newer than cycle 1's.
        store.set_login_watermark(
            CLUSTER.name, POD, _stamp(t0 - timedelta(seconds=34.5)), now_iso())

        second = install(WindowedClient(lines))
        capture_once(store, CLUSTER, settings)
        assert second.windows == [self.WINDOW], (
            f"the watermark did not produce the intended window: {second.windows}"
        )
        assert second.returned == [1], (
            "the window did not clip between the cause and the verdict, so this test proves nothing "
            f"— it returned {second.returned[0]} lines instead of the verdict alone"
        )

        rows = store.login_events(CLUSTER.name)
        assert len(rows) == 1, (
            "one login produced two rows: the same person is reported both as a wrong password and "
            f"as an unexplained failure — {[(r['user_name'], r['outcome'], r['at']) for r in rows]}"
        )
        assert rows[0]["outcome"] == "bad_password", (
            "the surviving row is the one with no reason; a later, worse-informed read displaced the "
            "diagnosis"
        )

    def test_a_log_that_never_contained_the_cause_still_records_the_failure(
            self, store, settings, install):
        """A pod whose log begins after the bind has no better information anywhere.

        Recording the verdict alone is right here, and asserting it is what stops the guard above from
        being implemented as "drop anything without a cause".
        """
        begins = datetime.now(UTC) - timedelta(seconds=95)
        install(WindowedClient(_attempt_lines(begins)[3:]))
        assert capture_once(store, CLUSTER, settings) == 1
        rows = store.login_events(CLUSTER.name)
        assert [(r["user_name"], r["outcome"]) for r in rows] == [("jane.smith", "failed")], rows


class TestTheClipIsReachable:
    """Whether the loop's own window arithmetic can put a boundary inside that 1.167 ms gap.

    If it could not, the row above would be unreachable in production and this would be a curiosity
    rather than a defect. `since_seconds` is whole seconds, which is the reason to check: a boundary
    quantised to a whole second could never land between two lines that share one.
    """

    def test_the_boundary_carries_the_request_instant_s_sub_second_phase(self):
        """`since_seconds` is coarse; `now − since_seconds` is not.

        The kubelet resolves sinceSeconds against the request's own instant, so the boundary inherits
        that instant's fractional part and can fall anywhere inside a second.
        """
        boundaries = set()
        for micros in (0, 250_000, 500_000, 883_500, 999_999):
            now = datetime(2026, 8, 8, 0, 4, 21, micros, tzinfo=UTC)
            boundaries.add((now - timedelta(seconds=95)).microsecond)
        assert len(boundaries) == 5, (
            "a whole-second sinceSeconds still yields sub-second boundaries; if these collapsed to "
            "one value the clip would be unreachable"
        )

    def test_the_sweeping_boundary_passes_through_the_gap(self):
        """The read window's start is `watermark − OVERLAP_SECONDS`, and the watermark advances every
        cycle, so the boundary sweeps forward through log time and crosses every instant — including
        the 1.167 ms between a cause and its verdict."""
        begins = datetime(2026, 8, 8, 0, 2, 46, tzinfo=UTC)
        bind = begins + timedelta(seconds=BIND_OFFSET)
        verdict = begins + timedelta(seconds=VERDICT_OFFSET)

        # A watermark that lands the boundary inside the gap: any settled line at bind + overlap.
        watermark = bind + timedelta(seconds=OVERLAP_SECONDS, microseconds=500)
        now = watermark + timedelta(seconds=SETTLE_SECONDS)
        since = max(OVERLAP_SECONDS, int((now - watermark).total_seconds()) + OVERLAP_SECONDS)
        boundary = now - timedelta(seconds=since)
        assert bind < boundary < verdict, (
            f"boundary {boundary.isoformat()} did not land in the gap "
            f"({bind.isoformat()}, {verdict.isoformat()})"
        )

    def test_the_settle_rules_do_not_withhold_the_clipped_attempt(self):
        """`_recordable` is what could have saved this, and does not: it withholds attempts younger
        than SETTLE_SECONDS + ATTEMPT_WINDOW, and by the time the boundary has swept far enough to
        clip a cause, the attempt is a minute older than that."""
        begins = datetime.now(UTC) - timedelta(seconds=95)
        verdict_only = parse(_attempt_lines(begins)[3:])
        assert logincapture._recordable(verdict_only) == verdict_only, (
            "an attempt this old is recordable, so nothing holds the clipped read back"
        )
        cutoff = datetime.now(UTC) - timedelta(seconds=SETTLE_SECONDS) - ATTEMPT_WINDOW
        assert verdict_only[0].at <= cutoff
```

New text:

```python
```

### Block 59 — local-development/tests/test_kube_reader.py

Remove the retired path.
Baseline: local-development/tests/test_kube_reader.py:19; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_kube_reader.py | edit -->

Old text:

```python
class Chunks(httpx.SyncByteStream):
    def __init__(self, values):
        self.values = values
        self.yielded = 0

    def __iter__(self):
        for value in self.values:
            self.yielded += 1
            yield value


def _client_for(monkeypatch, stream):
    cluster = ClusterConfig("c", "https://api.example", token_env="X")
    transport = httpx.MockTransport(
        lambda request: httpx.Response(200, stream=stream, request=request))
    client = ClusterClient(cluster)
    monkeypatch.setattr(
        client, "_client",
        lambda: httpx.Client(transport=transport, base_url="https://api.example"))
    return client


def test_the_byte_cap_is_measured_in_bytes_not_line_characters(monkeypatch):
    """A multi-byte log must not blow through the cap: max_bytes is a MEMORY bound, and a
    character count taken after the line was already assembled is neither."""
    stream = Chunks([("€" * 10 + "\n").encode(), b"x\n"])       # 31 bytes, 11 characters
    client = _client_for(monkeypatch, stream)
    got = client.fetch_pod_log("ns", "pod", max_bytes=20)
    assert got is not None
    assert sum(len(line.encode()) for line in got) <= 20, got


def test_a_cap_hit_keeps_the_oldest_lines_and_stops_the_transfer(monkeypatch, caplog):
    """The watermark machinery REQUIRES oldest-first retention: the cursor only advances through
    returned lines, so the deferred newest fall inside the next window and are late, not lost.
    Keeping the newest would advance the cursor past the displaced middle and silently drop it
    forever — and reading on after the cap pays for bytes that are then thrown away."""
    stream = Chunks([b"oldest-1\n", b"oldest-2\n", b"newest-3\n", b"newest-4\n"])
    client = _client_for(monkeypatch, stream)
    with caplog.at_level(logging.INFO):
        got = client.fetch_pod_log("ns", "pod", max_bytes=20)
    assert got == ["oldest-1", "oldest-2"], got
    assert stream.yielded < 4, "the read continued past the cap"
    assert "OLDEST lines of this window are kept" in caplog.text


def test_the_line_the_cap_cuts_in_half_is_dropped_not_parsed(monkeypatch):
    """A truncated line can mis-parse — a bind diagnostic losing its `data` sub-code reads as a
    plain wrong password — so the cut line waits for the next cycle's overlap instead."""
    stream = Chunks([b"whole-line\n" + b"cut-here-" * 10])
    client = _client_for(monkeypatch, stream)
    got = client.fetch_pod_log("ns", "pod", max_bytes=30)
    assert got == ["whole-line"], got


def test_a_read_that_outlives_its_budget_is_cut_like_a_cap_hit(monkeypatch, caplog):
    """The httpx timeout caps the gap BETWEEN chunks, not the transfer, so a stream dripping just
    under it can run for minutes — measured: a timeout=1.0 client consumed a 4.2s dribble without
    raising. The capture loop stamps the clock behind its leading-edge guard AFTER this returns, so
    past ~58.5s of read latency that guard permanently drops logins nothing ever recorded. A read the
    budget interrupts must land on the cap-hit path: oldest lines kept, the tail deferred, said out
    loud.

    THE PAYLOAD HAS TO EXCEED chunk_size, not merely arrive in several pieces. `iter_bytes` re-chunks
    whatever the transport yields — two small source chunks are coalesced into one, the loop body runs
    once, and a budget that is only checked per iteration is never reached. A first draft of this test
    asserted against 33 bytes in two pieces and failed against working code for that reason.
    """
    import types

    from gsd import kube

    # Fixed-width lines so the boundary arithmetic is inspectable: 64 KiB of them is 1560 whole
    # lines plus a fragment, and one iteration of the loop consumes exactly that.
    lines = [f"2026-08-08T00:00:00.{i:09d}Z line-{i:05d}" for i in range(1600)]
    payload = ("\n".join(lines) + "\n").encode()
    assert len(payload) > 64 * 1024, "the payload must span more than one chunk_size"

    # One tick for the start stamp, then one per iteration; the second iteration lands past the
    # budget. The last value repeats so an extra clock read cannot exhaust the fake.
    ticks = [0.0, 5.0, kube.LOG_READ_BUDGET_SECONDS + 30.0]
    monkeypatch.setattr(
        kube, "time",
        types.SimpleNamespace(monotonic=lambda: ticks.pop(0) if len(ticks) > 1 else ticks[0]))

    stream = Chunks([payload])
    client = _client_for(monkeypatch, stream)
    with caplog.at_level(logging.INFO):
        got = client.fetch_pod_log("ns", "pod")

    assert got is not None
    assert 0 < len(got) < len(lines), f"kept {len(got)} of {len(lines)}"
    assert got == lines[:len(got)], "the OLDEST lines must be the ones kept"
    assert lines[-1] not in got, "the tail should be deferred to the next cycle, not returned"
    assert "budget" in caplog.text, caplog.text
    assert "byte cap" not in caplog.text, "a budget stop must not report itself as a cap hit"


```

New text:

```python
```

### Block 60 — local-development/mock-app/tests/test_request_surface.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/tests/test_request_surface.py:136; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/tests/test_request_surface.py | edit -->

Old text:

```python
def test_fetch_oauth_pods(client):
    pods = client.fetch_oauth_pods("openshift-authentication")
    assert pods is not None
    # Only Running pods; the Pending one is dropped.
    assert sorted(pods) == [
        "oauth-openshift-6d8f9c7b4-abcde",
        "oauth-openshift-6d8f9c7b4-fghij",
    ]
```

New text:

```python
```

### Block 61 — local-development/mock-app/tests/test_request_surface.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/tests/test_request_surface.py:147; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/tests/test_request_surface.py | edit -->

Old text:

```python
def test_fetch_pod_log(client):
    lines = client.fetch_pod_log("openshift-authentication", "oauth-openshift-6d8f9c7b4-abcde")
    assert lines is not None
    assert any('succeeded for "jane.smith"' in ln for ln in lines)
    for ln in lines:
        assert ln[:4].isdigit()                        # RFC3339 prefix present
```

New text:

```python
```

### Block 62 — local-development/mock-app/tests/test_audit_stream.py

Update the surviving contract.
Baseline: local-development/mock-app/tests/test_audit_stream.py:153; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/tests/test_audit_stream.py | edit -->

Old text:

```python
    assert client.fetch_oauth_pods("openshift-authentication") is None
```

New text:

```python
```

### Block 63 — local-development/tests/test_chart_strategy.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/tests/test_chart_strategy.py:245; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_chart_strategy.py | edit -->

Old text:

```python
class TestLoginCaptureReadsOneNamespaceOnly:
    """The dashboard's log read, and the one thing that must never widen.

    `pods/log` in a ClusterRole is EVERY POD ON THE CLUSTER — tokens, connection strings, customer
    data. That is a far wider grant than the group and binding reads this dashboard exists for, so the
    read is a Role in the single namespace whose logs it parses.
    """

    # pod-log is opt-in since chart 0.52.0 (audit-log is the default), so this path says so.
    ON = {"loginCapture__enabled": "true", "loginCapture__source": "pod-log"}

    def _docs(self, out):
        import yaml
        return [d for d in yaml.safe_load_all(out) if d]

    def test_it_renders_by_default_and_nothing_renders_when_off(self):
        # On since chart 0.14.0: a namespaced read is inside the on-by-default rule.
        ok, out = render()
        assert ok, out
        assert "login-capture" in out, "the log read is the default since chart 0.14.0"
        ok, out = render(loginCapture__enabled="false")
        assert ok, out
        assert "login-capture" not in out, "the log read renders after being disabled"

    def test_the_log_read_is_never_cluster_scoped(self):
        """The whole point. A ClusterRole here reads every pod's logs on the cluster — with either
        source: the audit-log branch grants nodes/proxy, never pods/log."""
        for extra in ({}, self.ON, {**self.ON, "authLogLevel__manage": "true"},
                      {**self.ON, "loginCapture__source": "audit-log"}):
            ok, out = render(**extra)
            assert ok, out
            for d in self._docs(out):
                if d.get("kind") != "ClusterRole":
                    continue
                for rule in d.get("rules") or []:
                    res = rule.get("resources") or []
                    assert "pods/log" not in res and "pods" not in res, (
                        f"settings={extra}: {d['metadata']['name']} grants {res} CLUSTER-WIDE. "
                        f"pods/log in a ClusterRole reads every pod on the cluster — it must stay a "
                        f"Role in loginCapture.namespace."
                    )

    def test_it_grants_exactly_list_pods_and_get_logs(self):
        """Both verbs are needed and neither is enough: there is no Deployment log subresource
        (verified: GET .../deployments/oauth-openshift/log -> "could not find the requested
        resource"), so pods must be LISTED to be discovered and then read one at a time."""
        ok, out = render(**self.ON)
        assert ok, out
        role = [d for d in self._docs(out)
                if d.get("kind") == "Role" and "login-capture" in d["metadata"]["name"]][0]
        assert role["metadata"]["namespace"] == "openshift-authentication"
        got = sorted((tuple(r["resources"]), tuple(sorted(r["verbs"]))) for r in role["rules"])
        assert got == [(("pods",), ("list",)), (("pods/log",), ("get",))], (
            f"the log read changed: {got}. No write verb belongs here at any value."
        )

    def test_the_read_binds_to_the_dashboard_not_the_job_identity(self):
        """This one IS the dashboard's own ServiceAccount — it is a read. The inverse of the
        log-level Jobs, whose write must never reach it."""
        ok, out = render(**self.ON)
        assert ok, out
        rb = [d for d in self._docs(out)
              if d.get("kind") == "RoleBinding" and "login-capture" in d["metadata"]["name"]][0]
        subj = rb["subjects"][0]
        assert subj["kind"] == "ServiceAccount"
        assert "auth-loglevel" not in subj["name"], (
            "the read must not be granted to the log-level Job's write identity"
        )
        assert subj.get("namespace"), "an unnamespaced subject binds nothing"
```

New text:

```python
```

### Block 64 — local-development/tests/test_chart_strategy.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/tests/test_chart_strategy.py:316; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_chart_strategy.py | edit -->

Old text:

```python
class TestTheOauthLogLevelJobKeepsTheWriteOffTheDashboard:
    """The chart's only write grant, and the whole point is WHERE it lives.

    Enabling login capture needs `patch` on authentications.operator.openshift.io — a write to a core
    platform object. `rbac.yaml` states "NO WRITE VERB ON ANYTHING THE DASHBOARD REPORTS ON" and five
    documents cite that line, so the grant sits on a ServiceAccount used only by the hook Jobs and
    the dashboard's own role stays read-only. These tests are what stop that separation eroding.

    NOTE ON PLACEMENT: `.github/workflows/ci.yml` points the `chart` job at THIS FILE by name.
    """

    # authLogLevel raises the OAuth server verbosity, which only the pod-log source needs — and
    # the chart REFUSES it together with source=audit-log, now the default. Select pod-log.
    ON = {"authLogLevel__manage": "true", "loginCapture__source": "pod-log"}

    def _docs(self, out):
        import yaml
        return [d for d in yaml.safe_load_all(out) if d]

    def test_nothing_renders_by_default(self):
        """The chart must not touch a cluster's authentication config unless asked."""
        ok, out = render()
        assert ok, out
        assert "auth-loglevel" not in out, "the log-level Job renders without being enabled"

    def test_the_dashboards_own_role_never_gains_the_write(self):
        """The invariant. If this fails, five documents became false."""
        for extra in ({}, self.ON, {**self.ON, "authLogLevel__enabled": "true"}):
            ok, out = render(**extra)
            assert ok, out
            for d in self._docs(out):
                if d.get("kind") != "ClusterRole":
                    continue
                if "auth-loglevel" in d["metadata"]["name"]:
                    continue                      # the Job's own role, which is allowed to write
                for rule in d.get("rules") or []:
                    writes = set(rule.get("verbs") or []) & {
                        "patch", "update", "create", "delete", "deletecollection", "*"}
                    if writes:
                        assert set(rule.get("resources") or []) == {"leases"}, (
                            f"settings={extra}: the DASHBOARD's role gained {sorted(writes)} on "
                            f"{rule.get('resources')}. The log-level write belongs on the Job's own "
                            f"ServiceAccount — see rbac.yaml's header and "
                            f"docs/reference-architecture.md."
                        )

    def test_the_jobs_write_is_pinned_to_one_named_object(self):
        """Unpinned, this would be patch on every object in operator.openshift.io — which includes
        the cluster's entire authentication configuration. resourceNames IS honoured for `patch`,
        unlike `create`/`list` where the name is not in the request path."""
        ok, out = render(**self.ON)
        assert ok, out
        rules = [r for d in self._docs(out)
                 if d.get("kind") == "ClusterRole" and "auth-loglevel" in d["metadata"]["name"]
                 for r in d["rules"]
                 if "authentications" in (r.get("resources") or [])]
        assert len(rules) == 1, f"expected exactly one authentications rule, got {len(rules)}"
        rule = rules[0]
        assert rule.get("resourceNames") == ["cluster"], (
            f"the write must be pinned to the single named object: {rule}"
        )
        assert sorted(rule["verbs"]) == ["get", "patch"], (
            f"only get and patch — no update, no list, no watch: {rule['verbs']}"
        )

    def test_the_job_applies_the_REQUESTED_level_both_ways(self):
        """Two switches, and the Job runs for both values of `enabled`.

        Helm does not run a Job you merely stopped rendering, so a one-way enable Job would strand
        the cluster in Debug the moment somebody flipped the flag back and saw nothing happen.

        Asserts the PATCH PAYLOAD, not the WANT assignment. Pinning `WANT=` alone was a false
        guarantee: a Job that assigns WANT and then hardcodes `logLevel: Debug` in the patch passed.
        """
        for enabled, level, other in (("false", "Normal", "Debug"), ("true", "Debug", "Normal")):
            ok, out = render(**self.ON, authLogLevel__enabled=enabled)
            assert ok, out
            job = [d for d in self._docs(out)
                   if d.get("kind") == "Job" and not d["metadata"]["name"].endswith("-revert")][0]
            script = job["spec"]["template"]["spec"]["containers"][0]["command"][-1]
            assert f"WANT={level}" in script, f"enabled={enabled} must request {level}"
            # The patch must interpolate WANT rather than name a level literally.
            assert '\\"logLevel\\":\\"${WANT}\\"' in script, (
                f"enabled={enabled}: the patch must use ${{WANT}}, or the toggle is one-way"
            )
            assert f'logLevel\\":\\"{other}' not in script, (
                f"enabled={enabled}: a hardcoded {other} in the patch defeats the toggle"
            )

    def test_the_revert_job_patches_Normal_and_only_Normal(self):
        """B5: nothing pinned the revert Job's payload, so a revert that patched `Debug` passed —
        which would make `helm uninstall` ENABLE debug logging on the way out."""
        ok, out = render(**self.ON)
        assert ok, out
        job = [d for d in self._docs(out)
               if d.get("kind") == "Job" and d["metadata"]["name"].endswith("-revert")][0]
        script = job["spec"]["template"]["spec"]["containers"][0]["command"][-1]
        assert '"logLevel":"Normal"' in script, "the revert Job must patch Normal"
        assert '"logLevel":"Debug"' not in script, "the revert Job must never patch Debug"

    def test_the_write_binding_names_the_jobs_own_service_account(self):
        """B1, and the most important test here: the invariant was only HALF guarded.

        The ClusterRole was tested; its BINDING was not. Rebinding the write role to the dashboard's
        ServiceAccount passed all 30 tests while the chart README claimed the suite would fail. The
        full subject triple is asserted — dropping the namespace let `other-namespace` through.
        """
        ok, out = render(**self.ON)
        assert ok, out
        binding = [d for d in self._docs(out)
                   if d.get("kind") == "ClusterRoleBinding"
                   and "auth-loglevel" in d["metadata"]["name"]][0]
        subjects = binding["subjects"]
        assert len(subjects) == 1, f"exactly one subject, got {subjects}"
        s = subjects[0]
        assert (s["kind"], s["name"]) == ("ServiceAccount", "t-group-sync-dashboard-auth-loglevel"), (
            f"the write must bind to the JOB's ServiceAccount, not {s}. If this fails, the dashboard "
            f"may be able to patch the cluster's authentication config."
        )
        assert s.get("namespace"), "an unnamespaced ServiceAccount subject binds nothing"
        assert binding["roleRef"]["name"] == "t-group-sync-dashboard-auth-loglevel"

    def test_a_service_account_name_collision_is_refused(self):
        """The configuration-level bypass Codex found: setting serviceAccount.name to the Job's SA
        name renders two same-named ServiceAccounts, runs the DASHBOARD as that identity, and hands
        it the patch grant. Verified before the guard: it rendered cleanly."""
        ok, out = render(**self.ON,
                         serviceAccount__name="t-group-sync-dashboard-auth-loglevel")
        assert not ok, "the chart rendered a configuration that gives the dashboard the write grant"
        assert "collides with the log-level Job" in out

    def test_the_set_jobs_hook_annotations_are_pinned(self):
        """B6: stripping them made the Job an ordinary object, which then FAILS every later upgrade
        on an immutable-field conflict — and nothing caught it."""
        ok, out = render(**self.ON)
        assert ok, out
        job = [d for d in self._docs(out)
               if d.get("kind") == "Job" and not d["metadata"]["name"].endswith("-revert")][0]
        ann = job["metadata"].get("annotations") or {}
        assert ann.get("helm.sh/hook") == "post-install,post-upgrade", (
            f"the set Job must be a hook, or it becomes a permanent object: {ann}"
        )
        assert "before-hook-creation" in (ann.get("helm.sh/hook-delete-policy") or ""), (
            "without before-hook-creation, the second upgrade fails on the existing Job's name"
        )

    def test_the_job_role_grants_nothing_beyond_its_two_rules(self):
        """B7: the role's total surface was unbounded — an extra rule or a widened apiGroup rode
        through every test. Pinned exhaustively, so widening it is a deliberate act."""
        ok, out = render(**self.ON)
        assert ok, out
        role = [d for d in self._docs(out)
                if d.get("kind") == "ClusterRole" and "auth-loglevel" in d["metadata"]["name"]][0]
        got = sorted(
            (tuple(sorted(r["apiGroups"])), tuple(sorted(r["resources"])),
             tuple(sorted(r.get("resourceNames") or [])), tuple(sorted(r["verbs"])))
            for r in role["rules"]
        )
        assert got == sorted([
            (("operator.openshift.io",), ("authentications",), ("cluster",), ("get", "patch")),
            (("apps",), ("deployments",), ("oauth-openshift",), ("get",)),
        ]), f"the Job's role changed. Every rule here is a cluster-scoped grant: {got}"

    def test_the_patched_object_is_the_operator_cr_and_says_so(self):
        """Three cluster-scoped objects have confusingly similar names, and two are one word apart:

            authentications.operator.openshift.io/cluster   spec.logLevel        <- what we patch
            authentications.config.openshift.io/cluster     spec.type, ...
            oauth.config.openshift.io/cluster               spec.identityProviders  ("the OAuth CR")

        Calling ours "the OAuth CR" points a reader at the object that holds the identity providers —
        which this feature never touches — and makes the RBAC look wrong. Verified on a live cluster.
        """
        ok, out = render(**self.ON)
        assert ok, out
        for job in [d for d in self._docs(out)
                    if d.get("kind") == "Job" and "auth-loglevel" in d["metadata"]["name"]]:
            script = job["spec"]["template"]["spec"]["containers"][0]["command"][-1]
            assert "authentications.operator.openshift.io cluster" in script, (
                f"{job['metadata']['name']} no longer targets the operator CR"
            )
            assert "oauth.config.openshift.io" not in script, (
                "this feature must never touch the OAuth CR — it holds the identity providers"
            )
            assert "operatorLogLevel" not in script, (
                "operatorLogLevel is the OPERATOR's own verbosity; the login lines come from the "
                "operand, whose verbosity is spec.logLevel"
            )
        role = [d for d in self._docs(out)
                if d.get("kind") == "ClusterRole" and "auth-loglevel" in d["metadata"]["name"]][0]
        groups = {g for r in role["rules"] for g in r["apiGroups"]}
        assert "config.openshift.io" not in groups, (
            "the grant must not reach config.openshift.io — that is where the OAuth CR and the "
            "Authentication CONFIG CR live"
        )

    def test_the_outage_warning_survives(self):
        """C1: the behaviour is inherent to a logLevel change; the WARNING is the deliverable.

        Measured on a 1-replica cluster: `authentication` reported "no oauth-openshift pods available
        on any node" and a second application logged HTTP 503 on the groups API while it rolled.
        """
        ok, out = render(**self.ON)
        assert ok, out
        assert "LOGIN OUTAGE" in out, "the Job no longer warns that a 1-replica roll is an outage"
        values = (CHART / "values.yaml").read_text()
        assert "LOGIN OUTAGE" in values.upper(), "values.yaml no longer warns at the decision point"

    def test_the_image_is_not_a_credentialed_registry(self):
        """C2: registry.redhat.io needs a pull secret this chart does not create, and the failure
        mode is a FAILED RELEASE — measured ErrImagePull -> `helm upgrade` failed "context canceled".
        """
        ok, out = render(**self.ON)
        assert ok, out
        # Scoped to THIS feature's Jobs: the oauth-proxy legitimately uses registry.redhat.io and is
        # out of scope. A whole-render assertion matched that and failed for the wrong reason.
        for job in [d for d in self._docs(out)
                    if d.get("kind") == "Job" and "auth-loglevel" in d["metadata"]["name"]]:
            image = job["spec"]["template"]["spec"]["containers"][0]["image"]
            assert "registry.redhat.io" not in image, (
                f"{job['metadata']['name']} uses {image}, which needs a pull secret this chart does "
                f"not create. Measured: ErrImagePull -> `helm upgrade` failed with context canceled."
            )

    def test_a_wait_longer_than_the_deadline_is_refused(self):
        """A6/B2: the deadline would kill the Job mid-wait and fail `helm upgrade`, contradicting the
        documented promise that a wait timeout is not a failure."""
        ok, out = render(**self.ON, authLogLevel__waitSeconds="600")
        assert not ok, "a wait longer than the deadline rendered happily"
        assert "must be LESS than activeDeadlineSeconds" in out

    def test_the_wait_gates_on_the_operands_own_flag(self):
        """A1: generation/replica polling is a steady-state invariant, equally true BEFORE the
        operator reconciles — it logged "rollout complete: generation 26" while the deployment went
        on to 27, with the new pod starting 29s after the Job exited. `--v=<n>` in the Deployment's
        container args can only appear once the level is rendered into the workload."""
        ok, out = render(**self.ON)
        assert ok, out
        job = [d for d in self._docs(out)
               if d.get("kind") == "Job" and not d["metadata"]["name"].endswith("-revert")][0]
        script = job["spec"]["template"]["spec"]["containers"][0]["command"][-1]
        # Pins the GATE, not a mention. An earlier version of this test asserted only that
        # `--v=${WANT_V}` appeared somewhere in the script — and it survived a mutation that broke the
        # case pattern, because the string still appeared in an echo. Mutation-tested: this fails when
        # the match pattern changes.
        assert '*"--v=${WANT_V}"*)' in script, (
            "the wait no longer MATCHES on the operand's verbosity flag — a mention in an echo is "
            "not a gate"
        )
        assert "WANT_V=4" in script and "WANT_V=2" in script, "Debug=4 / Normal=2 mapping is gone"

    def test_uninstall_reverts_by_default(self):
        """Without this, removing the dashboard leaves the OAuth server naming every person who
        authenticates, with nothing left watching the logs and nobody aware of it."""
        ok, out = render(**self.ON)
        assert ok, out
        jobs = [d for d in self._docs(out)
                if d.get("kind") == "Job" and d["metadata"]["name"].endswith("-revert")]
        assert len(jobs) == 1, "the pre-delete revert Job is missing"
        ann = jobs[0]["metadata"]["annotations"]
        assert ann["helm.sh/hook"] == "pre-delete", (
            "must be pre-delete: post-delete would run after Helm removed the ServiceAccount it "
            "authenticates with"
        )

    def test_neither_job_carries_a_keep_policy(self):
        """`helm.sh/resource-policy: keep` on the SA or binding would orphan a CLUSTER-SCOPED RBAC
        pair on every uninstall, forever. It is not needed: Helm runs pre-delete hooks before it
        deletes release resources, so both still exist when the revert Job runs."""
        ok, out = render(**self.ON)
        assert ok, out
        for d in self._docs(out):
            if "auth-loglevel" not in (d.get("metadata", {}).get("name") or ""):
                continue
            ann = d["metadata"].get("annotations") or {}
            assert "helm.sh/resource-policy" not in ann, (
                f"{d['kind']} {d['metadata']['name']} would be orphaned on uninstall"
            )
```

New text:

```python
```

### Block 65 — local-development/tests/test_chart_strategy.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/tests/test_chart_strategy.py:1574; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_chart_strategy.py | edit -->

Old text:

```python
    def test_pod_log_remains_selectable_and_then_renders_no_audit_grant(self):
        """The old default is now the opt-in: it still works, it is just not chosen for you."""
        ok, out = render(loginCapture__source="pod-log")
        assert ok, out
        assert "login-capture-audit" not in out
        assert self._rules(out, "Role", "login-capture") is not None
        assert 'loginCaptureSource: "pod-log"' in out
```

New text:

```python
```

### Block 66 — local-development/tests/test_chart_strategy.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/tests/test_chart_strategy.py:1644; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_chart_strategy.py | edit -->

Old text:

```python
    def test_the_debug_contradiction_is_moot_when_capture_is_off(self):
        """Cursor, review D1: with loginCapture.enabled=false no RBAC renders and no log is read,
        so a leftover source=audit-log must not refuse a render that keeps Debug on."""
        ok, out = render(**self.AUDIT, loginCapture__enabled="false",
                         authLogLevel__manage="true", authLogLevel__enabled="true")
        assert ok, out
```

New text:

```python
```

### Block 67 — local-development/tests/test_chart_strategy.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/tests/test_chart_strategy.py:1651; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_chart_strategy.py | edit -->

Old text:

```python
    def test_audit_log_with_debug_on_is_refused(self):
        ok, out = render(**self.AUDIT, authLogLevel__manage="true", authLogLevel__enabled="true")
        assert not ok and "contradict" in out, out
```

New text:

```python
```

### Block 68 — local-development/tests/test_chart_strategy.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/tests/test_chart_strategy.py:1655; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_chart_strategy.py | edit -->

Old text:

```python
    def test_audit_log_with_the_manager_retiring_debug_renders_normal(self):
        ok, out = render(**self.AUDIT, authLogLevel__manage="true", authLogLevel__enabled="false")
        assert ok, out
        assert "WANT=Normal" in out or 'WANT="Normal"' in out or "Normal" in out
        assert "retire" in out.lower() or "Debug" in out
```

New text:

```python
```

### Block 69 — local-development/tests/test_chart_pdb.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/tests/test_chart_pdb.py:1; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_chart_pdb.py | edit -->

Old text:

```python
"""The PodDisruptionBudget, on by default since chart 0.14.0, must select the Deployment's pods and
nothing else.

Measured on the reference cluster (2026-09-05): the `authLogLevel` hook Job pods carried the same
selector labels as the dashboard pod, the disruption controller resolved a matched pod to a Job,
and the budget failed outright — `SyncFailed: jobs.batch does not implement the scale subresource`,
`DisruptionAllowed=False`, `disruptionsAllowed: 0`. With `maxUnavailable: 1` that is a blocked drain,
the exact failure the values comment says the default avoids. The same labels also made the Service
match a running hook pod (no readiness probe, so Ready as soon as its container starts).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

CHART = Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"
needs_helm = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not on PATH")


def _render(*sets: str) -> list[dict]:
    args = ["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h"]
    for s in sets:
        args += ["--set", s]
    done = subprocess.run(args, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return [d for d in yaml.safe_load_all(done.stdout) if d]


def _one(docs: list[dict], kind: str, name_part: str = "") -> dict:
    """The one document of `kind` whose name IS `name_part`, else the one whose name contains it.
    Exact first: since chart 0.20.0 the report service's budget is named `<fullname>-report`, so
    the dashboard's own name is a substring of two budgets (SPEC_C3, orchestrator's note)."""
    exact = [d for d in docs if d.get("kind") == kind and d["metadata"]["name"] == name_part]
    if len(exact) == 1:
        return exact[0]
    hits = [d for d in docs if d.get("kind") == kind and name_part in d["metadata"]["name"]]
    assert len(hits) == 1, f"{kind} {name_part!r}: {[d['metadata']['name'] for d in hits]}"
    return hits[0]


def _matches(selector: dict, labels: dict) -> bool:
    return all(labels.get(k) == v for k, v in selector.items())


@needs_helm
class TestThePdbSelectsTheDeploymentOnly:
    def test_on_by_default_and_permissive(self):
        pdb = _one(_render(), "PodDisruptionBudget", "t-group-sync-dashboard")
        assert pdb["spec"]["maxUnavailable"] == 1
        assert "minAvailable" not in pdb["spec"]

    def test_off_removes_it(self):
        # Two budgets since chart 0.20.0, each behind its own switch: the dashboard's here, the
        # report Deployment's under reporting.podDisruptionBudget (SPEC_C3, orchestrator's note).
        left = [d["metadata"]["name"] for d in _render("podDisruptionBudget.enabled=false")
                if d.get("kind") == "PodDisruptionBudget"]
        assert left == ["t-group-sync-dashboard-report"], left
        assert not [d for d in _render("podDisruptionBudget.enabled=false", "reporting.podDisruptionBudget.enabled=false")
                    if d.get("kind") == "PodDisruptionBudget"]

    def test_min_available_replaces_max_unavailable(self):
        pdb = _one(_render("podDisruptionBudget.minAvailable=1"), "PodDisruptionBudget", "t-group-sync-dashboard")
        assert pdb["spec"].get("minAvailable") == 1 and "maxUnavailable" not in pdb["spec"]

    def test_the_selector_matches_the_dashboard_pod_and_no_hook_pod(self):
        # source=pod-log because the chart refuses authLogLevel.enabled with the audit-log
        # default (0.52.0): it will not roll the OAuth server as a side effect of a read setting.
        docs = _render("authLogLevel.manage=true", "authLogLevel.enabled=true", "loginCapture.source=pod-log")
        selector = _one(docs, "PodDisruptionBudget", "t-group-sync-dashboard")["spec"]["selector"]["matchLabels"]
        deployment = _one(docs, "Deployment", "t-group-sync-dashboard")
        assert _matches(selector, deployment["spec"]["template"]["metadata"]["labels"])
        jobs = [d for d in docs if d.get("kind") == "Job"]
        assert len(jobs) == 3, [d["metadata"]["name"] for d in jobs]   # the two auth-loglevel hooks and the secrets mint (0.37.0)
        for job in jobs:
            labels = job["spec"]["template"]["metadata"]["labels"]
            assert not _matches(selector, labels), (
                f"{job['metadata']['name']}: a Job-owned pod in the budget fails it "
                f"(jobs.batch has no scale subresource) and blocks every drain"
            )
            # Still identifiable as this release's pod, just not as the workload.
            assert labels["app.kubernetes.io/instance"] == "t"
            assert labels["app.kubernetes.io/component"] in ("auth-loglevel", "auth-loglevel-revert", "secrets-mint"), labels

    def test_a_pod_label_that_collides_with_a_selector_label_is_refused(self):
        """Second-pass review (Cursor): `podLabels.app=x` used to win by last-key-wins, so the
        API server rejected the Deployment and the PDB and Service would have matched no pod.
        Refused by name; a harmless extra label still renders."""
        for key in ("app", "app.kubernetes.io/name", "app.kubernetes.io/instance"):
            escaped = key.replace(".", "\\.")  # Helm --set: a literal dot inside a key
            args = ["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h",
                    "--set", f"podLabels.{escaped}=x"]
            done = subprocess.run(args, capture_output=True, text=True, timeout=120)
            assert done.returncode != 0, key
            assert "podLabels must not set" in done.stderr and key in done.stderr, done.stderr
        docs = _render("podLabels.team=platform")
        labels = _one(docs, "Deployment", "t-group-sync-dashboard")["spec"]["template"]["metadata"]["labels"]
        assert labels["team"] == "platform"
        assert _matches(_one(docs, "PodDisruptionBudget", "t-group-sync-dashboard")["spec"]["selector"]["matchLabels"], labels)

    def test_the_service_does_not_route_to_a_hook_pod_either(self):
        # source=pod-log: the chart refuses authLogLevel.enabled with the audit-log default (0.52.0).
        docs = _render("authLogLevel.manage=true", "authLogLevel.enabled=true", "loginCapture.source=pod-log")
        selector = _one(docs, "Service", "t-group-sync-dashboard")["spec"]["selector"]
        assert _matches(selector, _one(docs, "Deployment", "t-group-sync-dashboard")["spec"]["template"]["metadata"]["labels"])
        for job in (d for d in docs if d.get("kind") == "Job"):
            assert not _matches(selector, job["spec"]["template"]["metadata"]["labels"])
```

New text:

```python
"""The PodDisruptionBudget, on by default since chart 0.14.0, must select the Deployment's pods and
nothing else.

Measured on the reference cluster (2026-09-05): the `authLogLevel` hook Job pods carried the same
selector labels as the dashboard pod, the disruption controller resolved a matched pod to a Job,
and the budget failed outright — `SyncFailed: jobs.batch does not implement the scale subresource`,
`DisruptionAllowed=False`, `disruptionsAllowed: 0`. With `maxUnavailable: 1` that is a blocked drain,
the exact failure the values comment says the default avoids. The same labels also made the Service
match a running hook pod (no readiness probe, so Ready as soon as its container starts).
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

CHART = Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"
needs_helm = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not on PATH")


def _render(*sets: str) -> list[dict]:
    args = ["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h"]
    for s in sets:
        args += ["--set", s]
    done = subprocess.run(args, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return [d for d in yaml.safe_load_all(done.stdout) if d]


def _one(docs: list[dict], kind: str, name_part: str = "") -> dict:
    """The one document of `kind` whose name IS `name_part`, else the one whose name contains it.
    Exact first: since chart 0.20.0 the report service's budget is named `<fullname>-report`, so
    the dashboard's own name is a substring of two budgets (SPEC_C3, orchestrator's note)."""
    exact = [d for d in docs if d.get("kind") == kind and d["metadata"]["name"] == name_part]
    if len(exact) == 1:
        return exact[0]
    hits = [d for d in docs if d.get("kind") == kind and name_part in d["metadata"]["name"]]
    assert len(hits) == 1, f"{kind} {name_part!r}: {[d['metadata']['name'] for d in hits]}"
    return hits[0]


def _matches(selector: dict, labels: dict) -> bool:
    return all(labels.get(k) == v for k, v in selector.items())


@needs_helm
class TestThePdbSelectsTheDeploymentOnly:
    def test_on_by_default_and_permissive(self):
        pdb = _one(_render(), "PodDisruptionBudget", "t-group-sync-dashboard")
        assert pdb["spec"]["maxUnavailable"] == 1
        assert "minAvailable" not in pdb["spec"]

    def test_off_removes_it(self):
        # Two budgets since chart 0.20.0, each behind its own switch: the dashboard's here, the
        # report Deployment's under reporting.podDisruptionBudget (SPEC_C3, orchestrator's note).
        left = [d["metadata"]["name"] for d in _render("podDisruptionBudget.enabled=false")
                if d.get("kind") == "PodDisruptionBudget"]
        assert left == ["t-group-sync-dashboard-report"], left
        assert not [d for d in _render("podDisruptionBudget.enabled=false", "reporting.podDisruptionBudget.enabled=false")
                    if d.get("kind") == "PodDisruptionBudget"]

    def test_min_available_replaces_max_unavailable(self):
        pdb = _one(_render("podDisruptionBudget.minAvailable=1"), "PodDisruptionBudget", "t-group-sync-dashboard")
        assert pdb["spec"].get("minAvailable") == 1 and "maxUnavailable" not in pdb["spec"]

    def test_the_selector_matches_the_dashboard_pod_and_no_hook_pod(self):
        docs = _render()
        selector = _one(docs, "PodDisruptionBudget", "t-group-sync-dashboard")["spec"]["selector"]["matchLabels"]
        deployment = _one(docs, "Deployment", "t-group-sync-dashboard")
        assert _matches(selector, deployment["spec"]["template"]["metadata"]["labels"])
        jobs = [d for d in docs if d.get("kind") == "Job"]
        assert len(jobs) == 1, [d["metadata"]["name"] for d in jobs]   # secrets mint only
        for job in jobs:
            labels = job["spec"]["template"]["metadata"]["labels"]
            assert not _matches(selector, labels), (
                f"{job['metadata']['name']}: a Job-owned pod in the budget fails it "
                f"(jobs.batch has no scale subresource) and blocks every drain"
            )
            # Still identifiable as this release's pod, just not as the workload.
            assert labels["app.kubernetes.io/instance"] == "t"
            assert labels["app.kubernetes.io/component"] == "secrets-mint", labels

    def test_a_pod_label_that_collides_with_a_selector_label_is_refused(self):
        """Second-pass review (Cursor): `podLabels.app=x` used to win by last-key-wins, so the
        API server rejected the Deployment and the PDB and Service would have matched no pod.
        Refused by name; a harmless extra label still renders."""
        for key in ("app", "app.kubernetes.io/name", "app.kubernetes.io/instance"):
            escaped = key.replace(".", "\\.")  # Helm --set: a literal dot inside a key
            args = ["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h",
                    "--set", f"podLabels.{escaped}=x"]
            done = subprocess.run(args, capture_output=True, text=True, timeout=120)
            assert done.returncode != 0, key
            assert "podLabels must not set" in done.stderr and key in done.stderr, done.stderr
        docs = _render("podLabels.team=platform")
        labels = _one(docs, "Deployment", "t-group-sync-dashboard")["spec"]["template"]["metadata"]["labels"]
        assert labels["team"] == "platform"
        assert _matches(_one(docs, "PodDisruptionBudget", "t-group-sync-dashboard")["spec"]["selector"]["matchLabels"], labels)

    def test_the_service_does_not_route_to_a_hook_pod_either(self):
        docs = _render()
        selector = _one(docs, "Service", "t-group-sync-dashboard")["spec"]["selector"]
        assert _matches(selector, _one(docs, "Deployment", "t-group-sync-dashboard")["spec"]["template"]["metadata"]["labels"])
        for job in (d for d in docs if d.get("kind") == "Job"):
            assert not _matches(selector, job["spec"]["template"]["metadata"]["labels"])
```

### Block 70 — local-development/tests/test_chart_rbac_provenance.py

Remove the retired path.
Baseline: local-development/tests/test_chart_rbac_provenance.py:33; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_chart_rbac_provenance.py | edit -->

Old text:

```python
# Two renders reach every RBAC template: the lab's values (audit-log login capture, the fleet account, the
# cluster-Secret writes, the auditor binding) and the pod-log source with the authLogLevel Job, whose
# Role and ClusterRole only exist on that path.
RENDERS = {
    "crc": [],
    "pod-log": ["--set", "loginCapture.source=pod-log", "--set", "authLogLevel.manage=true"],
}
```

New text:

```python
# The lab audit-log values reach every surviving RBAC template.
RENDERS = {"crc": []}
```

### Block 71 — local-development/tests/test_values_defaults.py

Update the surviving contract.
Baseline: local-development/tests/test_values_defaults.py:21; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_values_defaults.py | edit -->

Old text:

```python
    "authLogLevel.manage": "a cluster-wide write that rolls the OAuth server; the audit log replaces it",
    "authLogLevel.enabled": "same decision as manage",
```

New text:

```python
```

### Block 72 — local-development/tests/test_config.py

Update the surviving contract.
Baseline: local-development/tests/test_config.py:578; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_config.py | edit -->

Old text:

```python
    def test_the_default_is_pod_log_with_the_measured_defaults(self, tmp_path):
        s = load_settings(write(tmp_path, BASE))
        assert s.login_capture_source == "pod-log"
```

New text:

```python
    def test_the_default_is_audit_log_with_the_measured_defaults(self, tmp_path):
        s = load_settings(write(tmp_path, BASE))
        assert s.login_capture_source == "audit-log"
```

### Block 73 — local-development/tests/test_config.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/tests/test_config.py:619; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_config.py | edit -->

Old text:

```python
    def test_junk_falls_back_to_pod_log_with_a_warning(self, tmp_path, caplog):
        import logging
        with caplog.at_level(logging.WARNING):
            s = load_settings(write(tmp_path, BASE + "loginCaptureSource: both\n"))
        assert s.login_capture_source == "pod-log"
        assert "loginCaptureSource" in caplog.text and "both" in caplog.text
```

New text:

```python
    @pytest.mark.parametrize("source", ("pod-log", "both", "garbage"))
    def test_retired_or_unknown_source_is_refused(self, tmp_path, source):
        with pytest.raises(ConfigError, match="audit-log"):
            load_settings(write(tmp_path, BASE + f"loginCaptureSource: {source}\n"))
```

### Block 74 — local-development/tests/test_log_levels.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/tests/test_log_levels.py:143; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_log_levels.py | edit -->

Old text:

```python
@pytest.mark.parametrize("written", ["Normal", "Trace", "TraceAll"])
def test_a_platform_operators_likely_mistake_is_rejected_and_redirected(written: str) -> None:
    """The trap this chart sets for anyone who knows OpenShift.

    This chart carries two log levels: `logLevel` for the dashboard's own Python logging, and
    `authLogLevel`, which raises the OAUTH-SERVER's verbosity and is what makes the login lines the
    dashboard reads exist at all. Someone reaching for the second and typing it into the first is
    making an understandable mistake, so the complaint has to name the other setting or it is
    useless.

    The values themselves are parametrised here — a test may name what the docs do not advertise,
    because its job is to prove they are refused.
    """
    got = probe(written)
    assert got["effective"] == "INFO"
    assert "authLogLevel" in got["complaint"], (
        f"{written!r} must be refused with a pointer at authLogLevel"
    )
```

New text:

```python
@pytest.mark.parametrize("written", ["Normal", "Trace", "TraceAll"])
def test_a_platform_operators_likely_mistake_is_rejected_and_redirected(written: str) -> None:
    got = probe(written)
    assert got["effective"] == "INFO"
    assert "audit log" in got["complaint"]
    assert "authLogLevel" not in got["complaint"]
```

### Block 75 — local-development/tests/test_log_levels.py

Update the surviving contract.
Baseline: local-development/tests/test_log_levels.py:290; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_log_levels.py | edit -->

Old text:

```python
    assert "authLogLevel" in complaint
```

New text:

```python
    assert "audit log" in complaint and "authLogLevel" not in complaint
```

### Block 76 — charts/group-sync-dashboard/README.md

Remove the retired path.
Baseline: charts/group-sync-dashboard/README.md:595; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
**What Debug exposes**, so this is a decision and not a shrug: the lines carry the username of
everyone who authenticates, their resolved LDAP DN, and the bind filter used. Anyone who can read pod
logs in `openshift-authentication` can read them.
```

New text:

```text
New audit events cannot report LDAP result codes or AD sub-codes, including a locked-account
cause. Existing pod-log rows, their causes and their API/UI fields remain readable; configured
retention still applies. See `docs/AUDIT_LOG_CAPTURE.md` and `docs/LOGIN_CAPTURE_QUICKCHECK.md`.
```

### Block 77 — charts/group-sync-dashboard/README.md

Remove the retired path.
Baseline: charts/group-sync-dashboard/README.md:588; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
The default audit-log path has its own worked example in
[`docs/AUDIT_LOG_CAPTURE.md`](../../docs/AUDIT_LOG_CAPTURE.md). **To verify the pod-log path end to
end**, follow `docs/LOGIN_CAPTURE_QUICKCHECK.md` — five commands that turn the
verbosity up, cause a login, and read that login back using the dashboard's own ServiceAccount token,
with the real output of each recorded. It is also the place to start when the dashboard shows no login
activity and you need to find which link is missing.
```

New text:

```text
The audit grant is cluster-wide `get nodes/proxy` (all kubelet GET surfaces on those nodes), plus
`list nodes` unless `loginCapture.auditLog.nodeNames` pins the nodes. Set
`loginCapture.enabled: false` if this grant is unacceptable. A remote target needs its own grant;
the controller chart cannot grant access on another cluster.
```

### Block 78 — charts/group-sync-dashboard/README.md

Remove the retired path.
Baseline: charts/group-sync-dashboard/README.md:585; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
`helm uninstall` needs no such care — the pre-delete Job reverts first. But `helm rollback` does not
run hooks at all, so rolling back past an enable does **not** put the level back; do step 1 by hand.
```

New text:

```text
Changing the level rolls OAuth; schedule a maintenance window on a single-replica cluster and
verify the operator reaches Normal and the OAuth deployment is available. No convergence or
uninstall Job remains to do this for you. Audit capture needs no Debug verbosity.
```

### Block 79 — charts/group-sync-dashboard/README.md

Remove the retired path.
Baseline: charts/group-sync-dashboard/README.md:579; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
# 1. converge the cluster to Normal, with the machinery still present
helm upgrade ... -f my-values.yaml --set authLogLevel.manage=true --set authLogLevel.enabled=false
# 2. then, once the rollout has finished, stop managing it
helm upgrade ... -f my-values.yaml --set authLogLevel.manage=false
```

New text:

```text
oc patch authentications.operator.openshift.io cluster --type=merge -p '{"spec":{"logLevel":"Normal"}}'
```

### Block 80 — charts/group-sync-dashboard/README.md

Remove the retired path.
Baseline: charts/group-sync-dashboard/README.md:533; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
The oauth-openshift server only names the person logging in when the authentication **operator**
CR — `authentications.operator.openshift.io/cluster` — has `spec.logLevel: Debug`. Three
cluster-scoped objects have confusingly similar names, and this feature touches only the first:

| object | kind | holds |
|---|---|---|
| `authentications.operator.openshift.io/cluster` | `Authentication` (operator) | `logLevel`, `operatorLogLevel`, `managementState` |
| `authentications.config.openshift.io/cluster` | `Authentication` (config) | `type`, `serviceAccountIssuer`, `oauthMetadata` |
| `oauth.config.openshift.io/cluster` | `OAuth` | `identityProviders` — "the OAuth CR" |

`logLevel` is the **operand's** verbosity (the `oauth-server` process, which emits the login
lines); `operatorLogLevel` is the operator's own and would change nothing here. At `Normal` that line is
not emitted at all — measured: **zero** occurrences of `succeeded for login` until it is on. So
`authLogLevel.*` is the prerequisite for the pod-log source, and nothing more; the audit-log default
needs none of it.

**The write does not go on the dashboard.** Patching that object is a write to a core platform
object, and `rbac.yaml` states *"NO WRITE VERB ON ANYTHING THE DASHBOARD REPORTS ON"* — a line
`test_docs_citations.py` pins from five places across two documents. So the grant lives on a
ServiceAccount used only by the two hook Jobs. It is two rules and nothing else:

| API group | Resources | resourceNames | Verbs |
|---|---|---|---|
| `operator.openshift.io` | `authentications` | `cluster` | get, patch |
| `apps` | `deployments` | `oauth-openshift` | get |

Both are pinned by name. That is narrowing, not isolation: `resourceNames` stops this identity
touching *other* objects in those groups, and the object it can patch is the cluster's authentication
configuration — so the grant is small but not harmless, which is why it is opt-in.

The dashboard's own role stays read-only, and `test_chart_strategy.py` fails if that stops being
true — including if the *binding* is repointed at the dashboard's ServiceAccount, or if
`serviceAccount.name` is set to collide with the Job's. Both were possible until they were tested;
the second rendered cleanly and handed the dashboard the write.

**Pass your whole value set when you enable this on an existing release.** `helm upgrade` with only
`--set authLogLevel.*` discards every other user-supplied value and reverts it to the chart default —
measured here: a release carrying `oauthProxy.apiTokenAccess.enabled=true` lost it, and API token
access broke three commands later with no obvious connection to the cause. Re-pass your values file,
or use `--reuse-values` deliberately, then confirm with `helm get values`.

**Turning it off is two steps, in this order.** `manage: false` removes the Jobs *and* the revert Job
along with them, so going straight there while `Debug` is live strands the cluster in Debug with
nothing left to put it back:
```

New text:

```text
For a cluster still at Debug, run this as an authorized cluster administrator:
```

### Block 81 — charts/group-sync-dashboard/README.md

Remove the retired path.
Baseline: charts/group-sync-dashboard/README.md:528; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
**Deprecated — the pod-log source only.** Since chart 0.52.0 login capture reads the oauth-server
audit log, which names the person at the default verbosity; nothing in this section is needed for
it. This machinery remains for the opt-in `pod-log` source and to move a cluster left at `Debug`
back to `Normal` (the two steps below). Its removal is tracked in #321.
```

New text:

```text
Chart 0.58.0 / app 0.36.0 remove the OAuth Debug reader and both auth-loglevel Jobs.
If your values contain `authLogLevel` (even false settings), remove the entire stanza. Replace
`loginCapture.source: pod-log` with `loginCapture.source: audit-log` and remove
`loginCapture.namespace`. These retired values fail Helm rendering with migration guidance.
Re-pass your complete cleaned values file; do not reuse values containing removed keys.
```

### Block 82 — charts/group-sync-dashboard/README.md

Remove the retired path.
Baseline: charts/group-sync-dashboard/README.md:526; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
### oauth-server log verbosity
```

New text:

```text
### OAuth Debug migration
```

### Block 83 — charts/group-sync-dashboard/README.md

Remove the retired live path; keep audit capture and stored history.
Baseline: charts/group-sync-dashboard/README.md:454; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
| `loginCapture.source` | `audit-log` | **`audit-log` (the default since chart 0.52.0)** — `/var/log/oauth-server/audit.log` on the control-plane nodes, read through the API server's node proxy: names the person at the DEFAULT audit verbosity, so no Debug, no OAuth roll, no login outage, and history back through the rotated files. Its cost is a **ClusterRole on `get nodes/proxy`**, which is read access to everything the kubelet serves over GET on those nodes, plus `list nodes` unless `auditLog.nodeNames` pins them — read-only but cluster-wide. It is nevertheless the default because the alternative shipped a feature switched on and unable to name anyone: turn it off with `loginCapture.enabled: false` if the grant is unacceptable. `pod-log` — the opt-in: a Role on `pods`/`pods/log` in `loginCapture.namespace`, narrower, but it names a person only at Debug (`authLogLevel`), which rolls the OAuth server, and its history dies with every pod. It does keep the LDAP cause, which the audit log has not. Refused together with `authLogLevel.enabled=true` (while `loginCapture.enabled`); the audit log is authoritative from the switch on and corresponding pod-log rows are linked, not doubled. How the whole path works, with a worked example: [`docs/AUDIT_LOG_CAPTURE.md`](../../docs/AUDIT_LOG_CAPTURE.md) |
```

New text:

```text
| `loginCapture.source` | `audit-log` | Only supported source: oauth-server audit files through the node proxy, no Debug or OAuth rollout. Cluster-wide `get nodes/proxy`, plus `list nodes` unless `auditLog.nodeNames` pins them. No LDAP cause for new failures; stored pod-log rows remain readable. Removed values fail with migration guidance; see OAuth Debug migration below. |
```

### Block 84 — charts/group-sync-dashboard/README.md

Remove the retired live path; keep audit capture and stored history.
Baseline: charts/group-sync-dashboard/README.md:455; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
| `loginCapture.namespace` | `openshift-authentication` | pod-log source only: where the oauth-server pods run |
```

New text:

```text
```

### Block 85 — charts/group-sync-dashboard/README.md

Remove the retired live path; keep audit capture and stored history.
Baseline: charts/group-sync-dashboard/README.md:462; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
| `authLogLevel.manage` | `false` | lets this chart own `spec.logLevel` on the authentication **operator** CR (`authentications.operator.openshift.io/cluster`) — not the OAuth CR, and not `operatorLogLevel`. Off by default — turning it on is what transfers ownership |
```

New text:

```text
```

### Block 86 — charts/group-sync-dashboard/README.md

Remove the retired live path; keep audit capture and stored history.
Baseline: charts/group-sync-dashboard/README.md:463; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
| `authLogLevel.enabled` | `false` | with `manage`, sets `Debug` (login lines appear) or `Normal`. The Job runs for **both** values: Helm does not run a Job you merely stopped rendering, so a one-way enable would strand the cluster in Debug |
```

New text:

```text
```

### Block 87 — charts/group-sync-dashboard/README.md

Remove the retired live path; keep audit capture and stored history.
Baseline: charts/group-sync-dashboard/README.md:464; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
| `authLogLevel.revertOnUninstall` | `true` | **leave on.** A pre-delete Job puts the level back, or removing the dashboard leaves the OAuth server naming every person who authenticates with nothing left watching |
```

New text:

```text
```

### Block 88 — charts/group-sync-dashboard/README.md

Remove the retired live path; keep audit capture and stored history.
Baseline: charts/group-sync-dashboard/README.md:465; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
| `authLogLevel.waitSeconds` / `.activeDeadlineSeconds` / `.revertDeadlineSeconds` | `180` / `300` / `120` | the Job polls the Deployment's `observedGeneration` rather than using `oc rollout status`, which returned success ~30s **before** the rollout began. A wait timeout is not a failure — the patch has landed |
```

New text:

```text
```

### Block 89 — charts/group-sync-dashboard/README.md

Update the surviving contract.
Baseline: charts/group-sync-dashboard/README.md:916; later blocks for a file apply after its preceding blocks.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
`authLogLevel` hook Job pods carry `app.kubernetes.io/name`, `instance` and `component` but not
```

New text:

```text
`secrets-mint` hook Job pods carry `app.kubernetes.io/name`, `instance` and `component` but not
```

### Block 90 — README.md

Remove the retired live path; keep audit capture and stored history.
Baseline: README.md:197; later blocks for a file apply after its preceding blocks.

<!-- block: README.md | edit -->

Old text:

```text
| `logLevel` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` \| `CRITICAL`, and nothing else. `DEBUG` adds this app's own reasoning — login-capture accounting per pod, poll timing, row counts, which replica holds the Lease. Not the same setting as `authLogLevel`; the [chart README](charts/group-sync-dashboard/README.md#dashboard-log-verbosity--loglevel) lists what is refused and why |
```

New text:

```text
| `logLevel` | `INFO` | `DEBUG` \| `INFO` \| `WARNING` \| `ERROR` \| `CRITICAL`, and nothing else. Controls the app's own logging; login capture reads audit logs at default OAuth verbosity. See the [chart README](charts/group-sync-dashboard/README.md#dashboard-log-verbosity--loglevel). |
```

### Block 91 — environments/crc.yaml

Remove the retired path.
Baseline: environments/crc.yaml:42; later blocks for a file apply after its preceding blocks.

<!-- block: environments/crc.yaml | edit -->

Old text:

```text
# Login capture, on for this lab, from the oauth-server AUDIT LOG since chart 0.19.0 (D1). The two
# halves are still separate decisions:
#
#   authLogLevel  raises `spec.logLevel` on the authentication OPERATOR CR — NOT the OAuth CR — so the
#                 oauth-server's POD LOG names the person logging in. Only the pod-log source needs it.
#                 A cluster-scoped write, so it runs under its own ServiceAccount, never the dashboard's.
#   loginCapture  lets the DASHBOARD read a log. `source: pod-log` is a Role on pods/log in
#                 openshift-authentication; `source: audit-log` is a ClusterRole on `get nodes/proxy`
#                 (+ `list nodes`) — read-only, cluster-wide. The CHART DEFAULT since 0.52.0, because
#                 the audit log names the person at the DEFAULT verbosity and keeps history back to
#                 the rotated files. Restated below rather than inherited, per this directory's rule.
#
# ON A SHARED CLUSTER, READ THIS FIRST: toggling the level rolls oauth-openshift, which at one replica
# is a login outage rather than a rolling update. CRC has one replica. See
# docs/LOGIN_CAPTURE_QUICKCHECK.md (§6 for the audit-log source), which is also how to verify the whole
# path end to end.
#
# Management OFF: this cluster captures logins from the AUDIT LOG (loginCapture.source: audit-log,
# below), which names the person at the DEFAULT verbosity — the oauth operator's log level never needs
# raising, so the auth-loglevel Job is not needed here. That Job is a post-install/post-upgrade HOOK, so
# with manage:true it ran on EVERY upgrade and, on the CPU-saturated CRC node, could not schedule and
# hung the whole upgrade. The one-time convergence back to Normal is complete (the operator CR is at
# Normal), so manage:false no longer risks stranding the cluster in Debug. Set manage:true only for the
# pod-log login source, which is the one that needs the elevated verbosity.
authLogLevel:
  manage: false
  enabled: false

```

New text:

```text
# Login capture uses the audit log at default OAuth verbosity.
# Read-only nodes/proxy grant; see docs/LOGIN_CAPTURE_QUICKCHECK.md.
```

### Block 92 — environments/crc.yaml

Remove the retired path.
Baseline: environments/crc.yaml:27; later blocks for a file apply after its preceding blocks.

<!-- block: environments/crc.yaml | edit -->

Old text:

```text
# for THIS Python process — not the cluster's verbosity, and not `authLogLevel` below. The two are
# adjacent here on purpose: they are the pair that gets confused, and the whole reason the Logins tab
# once looked broken while capture was working.
#
# DEBUG is affordable now in a way it was not before. It used to mean 366 lines a cycle of which 356
# were httpcore socket framing, measured in this pod; the framing is pinned to WARNING, so DEBUG is
# ~11 lines and every one of them is the app's own reasoning — per-pod login-capture accounting, the
# poll cycle's timing, row counts per read, which replica holds the Lease and how stale its renewal
# is. Set GSD_DEBUG_HTTP=true on the container if a TLS handshake ever needs the framing back.
#
# It lives HERE rather than in a `--set` because the deploy script passes this file on every upgrade
# and Helm resets to chart defaults the moment either is given — a `--set logLevel=DEBUG` would be
# silently dropped by the next `helm upgrade -f` that did not repeat it.
```

New text:

```text
# for this Python process. Audit capture needs no OAuth verbosity change.
```

### Block 93 — environments/README.md

Remove the retired live path; keep audit capture and stored history.
Baseline: environments/README.md:54; later blocks for a file apply after its preceding blocks.

<!-- block: environments/README.md | edit -->

Old text:

```text
| `authLogLevel.manage` / `.enabled` | `false` / `false` | `false` / `false` | inherits the default: the lab reads the AUDIT LOG, which names the person at the default verbosity, so the auth-loglevel Job (a post-upgrade hook) is not needed; the one-time convergence to Normal is done, so management is off (set `manage=true` only for the pod-log source) |
```

New text:

```text
```

### Block 94 — environments/README.md

Remove the retired live path; keep audit capture and stored history.
Baseline: environments/README.md:68; later blocks for a file apply after its preceding blocks.

<!-- block: environments/README.md | edit -->

Old text:

```text
- `authLogLevel` writes a **cluster-scoped** CR and rolls the OAuth server, which on a
  single-replica cluster is a login outage rather than a rolling update. `values.yaml` carries the
  measured blast radius and the check to run first. It is the one switch chart 0.14.0's
  on-by-default rule left off: the oauth-server audit log is replacing it as the source of login
  lines.
```

New text:

```text
- OAuth Debug management was removed; clusters left at Debug must restore Normal manually (chart README migration note).
```

### Block 95 — docs/AUDIT_LOG_CAPTURE.md

Update the surviving contract.
Baseline: docs/AUDIT_LOG_CAPTURE.md:146; later blocks for a file apply after its preceding blocks.

<!-- block: docs/AUDIT_LOG_CAPTURE.md | edit -->

Old text:

```text
the account is locked. If that distinction is needed, the pod-log source is the only place it exists.
```

New text:

```text
the account is locked. The pod-log reader has been removed; new capture cannot supply that LDAP cause. Existing stored causes remain readable.
```

### Block 96 — docs/LOGIN_CAPTURE_QUICKCHECK.md

Replace the current quickcheck with audit-only instructions; retain the original measured transcript below a conspicuous historical warning.
Baseline: docs/LOGIN_CAPTURE_QUICKCHECK.md:1; later blocks for a file apply after its preceding blocks.

<!-- block: docs/LOGIN_CAPTURE_QUICKCHECK.md | edit -->

Old text:

```text
# Quick check: is login capture actually working?
```

New text:

```text
# Login capture quickcheck — audit log only

Login capture reads the oauth-server audit log at default OAuth verbosity. The OAuth Debug
reader and auth-loglevel Jobs were removed in chart 0.58.0 / app 0.36.0. Migrate old values and
restore Normal using the chart README's **OAuth Debug migration** section before upgrading.

1. Render your complete cleaned values file with `helm template` and confirm there are no
   auth-loglevel objects and no login-capture Role granting pods/log. Capture enabled renders
   the audit ClusterRole with `get nodes/proxy`, plus `list nodes` unless nodeNames is pinned.
2. Check the target cluster's poller ServiceAccount can `get nodes --subresource=proxy` and,
   unless nodes are pinned, `list nodes`. On remote clusters use that target's credential and
   context; installing the controller chart cannot authorize a remote read.
3. Check the configured nodes hold `/var/log/oauth-server/audit.log`. See
   [Audit log capture](AUDIT_LOG_CAPTURE.md) for the node-proxy URL, remote grants and worked
   example. A 403 is a grant failure, not evidence that nobody logged in.
4. Make one controlled successful `oc login` on the target, using a test account interactively
   (do not place its password in shell history). Wait for a successful capture cycle. The
   Logins tab and `GET /api/clusters/<cluster>/logins?kind=all` should contain its CLI row.
   Inspect `source`, `status_code`, `identity_match`, `last_read_at` and `capture_started_at`.
5. Check `gsd_login_capture_source_info{source="audit-log"}`, the last-read timestamp and
   per-node audit-settled timestamps on `/metrics`. First read may drain a backfill over cycles;
   one stalled node can lag while the aggregate last-read timestamp advances.

Audit deny records contain HTTP status and sometimes a message, but no LDAP result code or
AD sub-code: a wrong password cannot be distinguished from a locked account. Existing pod-log
rows and their causes remain visible and are subject to the configured retention. No migration
removes them. Capture disabled stops reads but does not hide retained history.

These are verification instructions, not a claim that this release has been tested on a live cluster.

## Historical transcript — retired OAuth Debug path

The transcript below records 2026-08-07 behavior. **Do not execute its commands on this release.**
The old keys, Jobs, pod reader and troubleshooting advice no longer apply. Use the audit-only
quickcheck above. It is retained as a historical measurement, not current operating guidance.

```

### Block 97 — docs/reference-architecture.md

Remove the retired path.
Baseline: docs/reference-architecture.md:803; later blocks for a file apply after its preceding blocks.

<!-- block: docs/reference-architecture.md | edit -->

Old text:

```text
A third role, on the dashboard's own ServiceAccount and only when `loginCapture.source: audit-log`
(`charts/group-sync-dashboard/templates/login-capture-rbac.yaml#nodes/proxy`): `get nodes/proxy`
(optionally `resourceNames`) and `list nodes`. Read-only and cluster-wide — read access to everything
the kubelet serves over GET on those nodes — which is why it is the one grant in this chart whose
default is off for breadth rather than for writing.

A **separate** ClusterRole, on a ServiceAccount the dashboard never uses, is created only when
`authLogLevel.manage=true`:

| API group | Resources | Verbs |
|---|---|---|
| `operator.openshift.io` | `authentications`, `resourceNames: [cluster]` | get, **patch** |
| `apps` | `deployments` | get |

That is the chart's only *write* outside its own namespace — the oauth-proxy's
`system:auth-delegator` binding is a read-path grant, not a write — and it is deliberately not
reachable by the dashboard process: the two hook Jobs that enable and revert the OAuth server's
`spec.logLevel` are its only consumers. Pinning `resourceNames` matters — unpinned it would be patch
on every object in the group, which includes the cluster's whole authentication configuration.
`resourceNames` IS honoured for `patch`, unlike `create` and `list` where the name is not in the
request path.

```

New text:

```text
The login-capture ClusterRole grants `get nodes/proxy`, optionally pinned by `resourceNames`,
and `list nodes` only when names are not pinned. It is enabled by `loginCapture.enabled` (true
by default) and reads audit logs at default OAuth verbosity. It grants no pods/log access.
The auth-loglevel Jobs, identity and authentication-operator patch grant have been removed.
See the chart README migration note for the manual Debug-to-Normal step.

```

### Block 98 — local-development/Containerfile

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/Containerfile:168; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/Containerfile | edit -->

Old text:

```text
# Not to be confused with the chart's authLogLevel, which raises the oauth-server's own verbosity
# on authentications.operator.openshift.io/cluster — a different setting, on a different object,
```

New text:

```text
# Login capture reads audit logs at default OAuth verbosity.
```

### Block 99 — local-development/Containerfile.ubi

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/Containerfile.ubi:74; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/Containerfile.ubi | edit -->

Old text:

```text
# Not to be confused with the chart's authLogLevel, which raises the oauth-server's own verbosity
# on authentications.operator.openshift.io/cluster — a different setting, on a different object,
```

New text:

```text
# Login capture reads audit logs at default OAuth verbosity.
```

### Block 100 — local-development/Containerfile.annotated

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/Containerfile.annotated:302; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/Containerfile.annotated | edit -->

Old text:

```text
# Not to be confused with the chart's authLogLevel, which raises the oauth-server's own verbosity
# on authentications.operator.openshift.io/cluster — a different setting, on a different object,
```

New text:

```text
# Login capture reads audit logs at default OAuth verbosity.
```

### Block 101 — local-development/mock-app/README.md

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/README.md:133; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/README.md | edit -->

Old text:

```text
- `forbidden.yaml` — users/identities/namespaces/nodes/oauth/pods answer 403 (tolerated → None).
```

New text:

```text
- `forbidden.yaml` — users/identities/namespaces/nodes/oauth answer 403 (tolerated → None).
```

### Block 102 — local-development/mock-app/README.md

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/README.md:129; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/README.md | edit -->

Old text:

```text
`operatorConfigs`, `nodes`, `oauth`, `oauthPods`, `auditLog`, `podLog`. See
```

New text:

```text
`operatorConfigs`, `nodes`, `oauth`, `auditLog`. See
```

### Block 103 — local-development/mock-app/deploy/DEPLOY.md

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/deploy/DEPLOY.md:101; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/deploy/DEPLOY.md | edit -->

Old text:

```text
`oauthPods`, `auditLog`, `podLog`. Any unknown top-level key is **rejected** rather than ignored, so a
```

New text:

```text
`auditLog`. Any unknown top-level key is **rejected** rather than ignored, so a
```

### Block 104 — docs/CHANGELOG.md

Update the surviving contract.
Baseline: docs/CHANGELOG.md:11; later blocks for a file apply after its preceding blocks.

<!-- block: docs/CHANGELOG.md | edit -->

Old text:

```text
## Unreleased
```

New text:

```text
## Unreleased

- **OAuth Debug path removed (#321, SPEC_L1; app 0.36.0 / chart 0.58.0, after #322).**
  Operators using `loginCapture.source: pod-log` or any `authLogLevel` values must migrate:
  remove the whole `authLogLevel` stanza (even false settings), remove `loginCapture.namespace`,
  and set `loginCapture.source: audit-log`. Old values fail `helm template` with these steps.
  The reader, its mock endpoints, both log-level Jobs and their write RBAC are gone; no
  converge-to-Normal or uninstall-revert Job remains. On clusters still at Debug, run:

      oc patch authentications.operator.openshift.io cluster --type=merge -p '{"spec":{"logLevel":"Normal"}}'

  This changes OAuth verbosity and can interrupt login while OAuth rolls, especially at one
  replica; plan the maintenance window and verify availability. Audit capture needs no Debug.
  **New logins lose LDAP causes**, including locked-account versus bad-password detail: the
  audit log supplies allow/deny/error, HTTP status and sometimes a message. Existing pod-log
  history stays readable with its causes; no migration deletes it. Normal retention continues.
  The audit source needs `get nodes/proxy` and `list nodes` unless nodes are pinned; disable
  capture if that cluster-wide read grant is unacceptable. API fields and metric names remain;
  the live source field/label becomes audit-log, while historical row sources remain pod-log.
```

### Block 105 — local-development/gsd/static/index.html

Remove the retired path.
Baseline: local-development/gsd/static/index.html:3971; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```text
// What the Logins page says about its record depends on which log the rows come from — the API's
// `source` (#346). The pod log is read at Debug from the moment watching began and dies with its pod;
// the audit log sits on the control-plane nodes, a first read backfills through its rotated files, and
// what a stalled reader missed is still there for the next read (docs/AUDIT_LOG_CAPTURE.md §2, §5).
// Every source-specific sentence lives here, so the two sources' wording cannot drift apart.
```

New text:

```text
// Live capture is audit-only. Stored pod-log rows keep their outcomes and pod_name.
```

### Block 106 — local-development/gsd/static/index.html

Remove the retired path.
Baseline: local-development/gsd/static/index.html:3977; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```text
  "pod-log": {
    window: `Nothing before capture began was ever recorded — the oauth-server's log dies with its pod and
      cannot be read backwards — so an empty list here means nothing was <em>observed</em>, never
      that nobody signed in.`,
    predates: `The oldest attempt predates the first read because that read looked back an hour, which
      is expected rather than a fault.`,
    stalled: `Attempts made since then are being lost, and they cannot be recovered later. Check the
      dashboard pod's log for a refused <code>pods/log</code> read, and that an oauth-server pod is Running.`,
    noMatch: `Either nobody has signed in since watching began, or the authentication operator is not at
      Debug, in which case the oauth-server never writes a username. One command decides which:
      <code>oc get authentications.operator.openshift.io cluster -o jsonpath='{.spec.logLevel}'</code>
      must print <code>Debug</code>.`,
    noRead: `The dashboard's ServiceAccount needs <code>pods</code> list and the
      <code>pods/log</code> subresource in the oauth-server's namespace
      (<code>openshift-authentication</code> unless configured otherwise), and at least one
      oauth-server pod has to be Running. Note that
      <code>oc auth can-i get pods/log</code> answers <code>no</code> even on a correct
      grant — it reads <code>pods/log</code> as a resource <em>name</em>. Use
      <code>--subresource=log</code>.`,
    disabled: `Not being captured. <code>loginCapture.enabled</code> — the module that reads the log —
        is off on this release; the chart default since 0.14.0 is on. Login lines also only exist
        while the authentication <em>operator</em> is at <code>spec.logLevel: Debug</code>, which
        makes the oauth-server write a username at all; the chart leaves that off by default
        because the oauth-server audit log is replacing it as the source. At the default verbosity
        capture runs and finds nothing.`,
    disabledHow: `Turning capture back on is <code>loginCapture.enabled=true</code>;
        the Debug source is <code>authLogLevel.manage</code> and <code>.enabled</code>, a
        cluster-wide write that rolls the OAuth server. See
        <code>docs/LOGIN_CAPTURE_QUICKCHECK.md</code> for the five commands that prove the path
        end to end.`,
    column: "Replica",
    columnHelp: `<strong>Replica</strong> is which oauth-server pod saw it, with the common prefix trimmed;
      the two replicas serve different attempts, so a name here is the pod whose log to read.`,
  },
```

New text:

```text
```

### Block 107 — local-development/gsd/static/index.html

Update the surviving contract.
Baseline: local-development/gsd/static/index.html:4052; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```text
  const text = LOGIN_SOURCE_TEXT[d.source === "audit-log" ? "audit-log" : "pod-log"];
```

New text:

```text
  const text = LOGIN_SOURCE_TEXT["audit-log"];
```

### Block 108 — local-development/gsd/static/index.html

Update the surviving contract.
Baseline: local-development/gsd/static/index.html:4039; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```text
    column: "Node",
```

New text:

```text
    column: "Node / stored pod",
```

### Block 109 — local-development/gsd/static/index.html

Update the surviving contract.
Baseline: local-development/gsd/static/index.html:4041; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```text
      with <code>oc adm node-logs &lt;node&gt; --path=oauth-server/audit.log</code>, not an oauth-server pod.`,
```

New text:

```text
      with <code>oc adm node-logs &lt;node&gt; --path=oauth-server/audit.log</code>. For a stored pod-log row,
      this is the original oauth-server pod name; its LDAP cause remains visible.`,
```

### Block 110 — local-development/tests/test_ui.py

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/tests/test_ui.py:10435; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_ui.py | edit -->

Old text:

```python
    def test_the_pod_log_source_keeps_its_own_account(self, dash):
        text = self._render(dash, "pod-log")
        assert [p for p in self.POD_LOG if p not in text] == []
        assert [a for a in self.AUDIT_LOG if a in text] == []
```

New text:

```python
```

### Block 111 — local-development/tests/test_ui.py

Update the surviving contract.
Baseline: local-development/tests/test_ui.py:10461; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_ui.py | edit -->

Old text:

```python
        off_audit, off_pod = render("audit-log", False), render("pod-log", False)
        rows_audit, rows_pod = render("audit-log", True), render("pod-log", True)
```

New text:

```python
        off_audit = render("audit-log", False)
        rows_audit = render("audit-log", True)
```

### Block 112 — local-development/tests/test_ui.py

Update the surviving contract.
Baseline: local-development/tests/test_ui.py:10465; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_ui.py | edit -->

Old text:

```python
        assert [c for c in pod_claims if c not in off_pod] == [], off_pod
```

New text:

```python
```

### Block 113 — local-development/tests/test_ui.py

Update the surviving contract.
Baseline: local-development/tests/test_ui.py:10467; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_ui.py | edit -->

Old text:

```python
        assert "which oauth-server pod saw it" in rows_pod
```

New text:

```python
        assert "stored pod-log row" in rows_audit
```

### Block 114 — local-development/tests/test_metrics.py

Update the surviving contract.
Baseline: local-development/tests/test_metrics.py:556; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_metrics.py | edit -->

Old text:

```python
            for source in ("pod-log", "audit-log"):
```

New text:

```python
            for source in ("audit-log",):
```

### Block 115 — local-development/gsd/api.py

Remove the retired path.
Baseline: local-development/gsd/api.py:1844; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
        attempt still kept and moves under retention. What lies before the window depends on `source`:
        under `pod-log` nothing before capture began exists to fetch — the log dies with its pod; under
        `audit-log` a first read backfills through the rotated audit files still on the control-plane
        nodes, bounded by the retention. Either way an empty list is a statement about the window and
        never proof that nobody logged in. The UI says that per source (#346), which is why it is here
        and not a footnote.
```

New text:

```python
        attempt still kept and moves under retention. The live source is audit-log: first read
        backfills available rotated files within retention. Historical pod-log rows retain their
        own source and causes. An empty list is never proof that nobody logged in.
```

### Block 116 — local-development/gsd/api.py

Update the surviving contract.
Baseline: local-development/gsd/api.py:1921; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
            # Which log the rows come from, and what that source can and cannot say — the two
            # differ in exactly the ways a reader of this page needs to know (no cause from the
            # audit log; no history from the pod log).
```

New text:

```python
            # Live reader source; individual stored rows can still have source=pod-log.
```

### Block 117 — local-development/mock-app/mock_app/__init__.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/__init__.py:4; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/__init__.py | edit -->

Old text:

```python
node-log-proxy shapes, the pod-log stream, and the SubjectAccessReview POST) from a declarative
```

New text:

```python
node-log-proxy shapes and the SubjectAccessReview POST) from a declarative
```

### Block 118 — local-development/mock-app/mock_app/errors.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/errors.py:9; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/errors.py | edit -->

Old text:

```python
* ``status_json`` — a Kubernetes Status body, used for pod-log >=400.
```

New text:

```python
* ``status_json`` — the Kubernetes Status body used by these error responses.
```

### Block 119 — local-development/mock-app/mock_app/responses.py

Update the surviving contract.
Baseline: local-development/mock-app/mock_app/responses.py:273; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/mock_app/responses.py | edit -->

Old text:

```python
    Read by kube.py's _log_read_refused (``.reason``, ``.message``) on a pod-log >=400.
```

New text:

```python
    Shared by the mock's forbidden and absent-resource responses.
```

### Block 120 — local-development/mock-app/README.md

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/README.md:4; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/README.md | edit -->

Old text:

```text
issues** — the ~16 read endpoints, the two node-log-proxy shapes, the pod-log stream, and the
```

New text:

```text
issues** — the ~16 read endpoints, the two node-log-proxy shapes, the audit stream, and the
```

### Block 121 — local-development/mock-app/README.md

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/README.md:31; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/README.md | edit -->

Old text:

```text
│   ├── podlog.py     pod-log text stream
```

New text:

```text
│   ├── podlog.py     pod-log text stream
```

### Block 122 — local-development/mock-app/fixtures/forbidden.yaml

Update the surviving contract.
Baseline: local-development/mock-app/fixtures/forbidden.yaml:3; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/fixtures/forbidden.yaml | edit -->

Old text:

```text
# users / identities / namespaces / nodes / oauth / oauthPods each answer 403 (the path is in
```

New text:

```text
# users / identities / namespaces / nodes / oauth each answer 403 (the path is in
```

### Block 123 — local-development/tests/test_chart_strategy.py

Update the surviving contract.
Baseline: local-development/tests/test_chart_strategy.py:1538; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_chart_strategy.py | edit -->

Old text:

```python
    """D1: `loginCapture.source: audit-log` swaps the namespaced pod-log Role for a ClusterRole on
```

New text:

```python
    """The audit-only source uses a ClusterRole on
```

### Block 124 — local-development/gsd/loginlog.py

Remove the retired path.
Baseline: local-development/gsd/loginlog.py:3; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/loginlog.py | edit -->

Old text:

```python
PURE FUNCTIONS, no I/O and no cluster. The reader that fetches logs lives elsewhere; everything here
takes text and returns records, so every rule below is testable against the real lines that produced it.

WHAT THIS READS. The oauth-server writes a line per login attempt naming the account that made it, but
only at `spec.logLevel: Debug` on `authentications.operator.openshift.io/cluster` — the authentication
OPERATOR CR, not the OAuth CR. At the default verbosity the lines do not exist, so capture is inert
until somebody enables it. See docs/LOGIN_CAPTURE_QUICKCHECK.md.

EVERY USERNAME IS CAPTURED, successful or not. There is no allowlist and there must not be one: a
username that appears here and belongs to NO synced group is the most interesting row this produces —
either somebody whose access was removed and is still trying, or an account nobody governs. Filtering
against known members would drop exactly those.

```

New text:

```python
PURE FUNCTIONS, no I/O and no cluster. This legacy parser and outcome vocabulary remain for
historical-row fixtures and API/KPI consumers. The live pod-log reader is removed; auditlog.py
is the only live input. Nothing in this module enables OAuth Debug or reads a cluster.

```

### Block 125 — local-development/tests/test_remove_oauth_debug.py

New regressions: baseline failures are the old default, accepted removed values and extant reader.
Baseline: local-development/tests/test_remove_oauth_debug.py:1; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/tests/test_remove_oauth_debug.py | create -->

New text:

```python
"""#321: audit-only migration, retained history and refusal of retired values."""
from __future__ import annotations

import itertools
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from gsd import auditlog, logincapture
from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.kube import ClusterClient
from gsd.metrics import build_registry
from gsd.store import Store
from datetime import timedelta

REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "charts/group-sync-dashboard"


def render_file(tmp_path, values):
    path = tmp_path / "values.yaml"
    path.write_text(yaml.safe_dump(values))
    return subprocess.run(["helm", "template", "t", str(CHART), "-f", str(path)],
                          capture_output=True, text=True, timeout=120)


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")
def test_removed_values_refuse_even_when_false_or_capture_disabled(tmp_path):
    # A single migration matrix also covers unknown nested keys: no retired map may be ignored.
    for enabled in (True, False):
        for retired in ({"manage": False}, {"enabled": False}, {"manage": True},
                        {"revertOnUninstall": False}, {"waitSeconds": 1}, {"unknown": False},
                        {}, False, None):
            result = render_file(tmp_path, {"authLogLevel": retired,
                                          "loginCapture": {"enabled": enabled}})
            assert result.returncode != 0, (enabled, retired, result.stdout)
            assert "authLogLevel" in result.stderr and "remove" in result.stderr
            assert "audit-log" in result.stderr and "Normal" in result.stderr
        for source in ("pod-log", "both", "typo", "AUDIT-LOG"):
            result = render_file(tmp_path, {"loginCapture": {"enabled": enabled, "source": source}})
            assert result.returncode != 0 and "loginCapture.source" in result.stderr
            assert "audit-log" in result.stderr
        result = render_file(tmp_path, {"loginCapture": {"enabled": enabled, "namespace": "ns"}})
        assert result.returncode != 0 and "remove" in result.stderr


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")
def test_no_oauth_debug_objects_or_grants_for_the_surviving_switch_matrix(tmp_path):
    # Removed values above fail. Every combination of the relevant surviving gates renders
    # either audit RBAC or no capture RBAC, never an OAuth writer or a pods/log reader.
    defaults = yaml.safe_load((CHART / "values.yaml").read_text())
    assert "authLogLevel" not in defaults  # baseline fails before any matrix render
    for capture, rbac, pinned in itertools.product((True, False), repeat=3):
        values = {"loginCapture": {"enabled": capture, "auditLog": {
                      "nodeNames": ["master-0"] if pinned else []}}, "rbac": {"create": rbac}}
        result = render_file(tmp_path, values)
        assert result.returncode == 0, result.stderr
        docs = [d for d in yaml.safe_load_all(result.stdout) if d]
        assert not any("auth-loglevel" in d.get("metadata", {}).get("name", "") for d in docs)
        for d in docs:
            for rule in d.get("rules", []):
                assert "pods/log" not in rule.get("resources", [])
                assert not ("operator.openshift.io" in rule.get("apiGroups", [])
                            and "authentications" in rule.get("resources", []))
        audit = [d for d in docs if d.get("kind") == "ClusterRole"
                 and d["metadata"]["name"].endswith("-login-capture-audit")]
        assert len(audit) == int(capture)
        if capture:
            proxy = next(r for r in audit[0]["rules"] if r["resources"] == ["nodes/proxy"])
            assert proxy["verbs"] == ["get"]
            assert proxy.get("resourceNames", []) == (["master-0"] if pinned else [])
            assert any(r["resources"] == ["nodes"] for r in audit[0]["rules"]) == (not pinned)


def test_audit_default_reads_stored_pod_history_over_api_and_metrics_after_reopen(tmp_path):
    db = str(tmp_path / "history.db")
    s = Store(db)
    s.upsert_cluster("c", "https://example", True)
    s.record_login_events("c", [{"pod_name": "oauth-old", "user_name": "alice",
        "outcome": "bad_password", "at": "2026-09-20T10:00:00.000000Z", "provider": "ldap",
        "ldap_result_code": 49, "detail": "data 775", "observed_at": "2026-09-20T10:01:00Z"}])
    s.close()
    settings = Settings(clusters=[ClusterConfig("c", "https://example")], db_path=db,
                        login_capture_enabled=True, oauth_proxy_enabled=True)
    with TestClient(build_app(settings, run_poller=False, tier_resolver=lambda viewer: "all")) as client:
        result = client.get("/api/clusters/c/logins?kind=all", headers={"X-Forwarded-User": "root"})
        assert result.status_code == 200
        body = result.json()
        assert body["source"] == "audit-log"  # baseline incorrectly describes the live reader as pod-log
        row, = body["attempts"]
        assert (row["source"], row["pod_name"], row["ldap_result_code"], row["detail"]) == (
            "pod-log", "oauth-old", 49, "data 775")
        assert row["outcome"] == "bad_password" and row["kind"] == "credential"
    reopened = Store(db)
    try:
        assert len(reopened.login_events("c")) == 1
        text = generate_latest(build_registry(reopened, timedelta(seconds=120), settings=settings)).decode()
        assert 'gsd_login_capture_source_info{cluster="c",source="audit-log"} 1.0' in text
    finally:
        reopened.close()


def test_the_default_dispatches_to_audit_and_disabled_capture_reads_nothing(monkeypatch):
    calls = []
    monkeypatch.setattr(auditlog, "capture_once", lambda *a: calls.append(a) or 7)
    cfg = ClusterConfig("c", "https://example")
    settings = Settings(clusters=[cfg], login_capture_enabled=True)
    assert logincapture.capture_once(None, cfg, settings) == 7
    assert len(calls) == 1
    from dataclasses import replace
    settings = replace(settings, login_capture_enabled=False)
    assert logincapture.capture_once(None, cfg, settings) == 0
    assert len(calls) == 1
    assert not hasattr(ClusterClient, "fetch_pod_log")
    assert not hasattr(ClusterClient, "fetch_oauth_pods")


class _EmptyAuditNode:
    """The four calls auditlog.capture_once makes, for one node whose audit file is empty."""

    def fetch_nodes(self, selector):
        return ["master-0"]

    def fetch_oauth_providers(self):
        return ["ldap"]

    def list_node_log_files(self, node, directory):
        return [auditlog.AUDIT_FILE]

    def fetch_node_log_file(self, node, path, offset=0, max_bytes=8 << 20):
        from gsd.kube import NodeLogRead
        return NodeLogRead(data=b"", offset=offset, truncated=False, rotated=False)


class _Elector:
    def __init__(self, leader):
        self.is_leader = leader


@pytest.mark.parametrize(("retention_days", "leader", "kept"), (
    (400, True, ["recent"]),               # Decision 3: normal retention still ages out history
    (0, True, ["ancient", "recent"]),      # 0 disables retention, as before
    (400, False, ["ancient", "recent"]),   # a standby never prunes
))
def test_stored_pod_log_history_keeps_its_retention_under_the_audit_only_poller(
        tmp_path, monkeypatch, retention_days, leader, kept):
    # The pod-log loop tests that pinned login_event retention are deleted with the loop; the
    # audit path now owns the prune, so the same three outcomes are pinned through it.
    from datetime import UTC, datetime
    db = str(tmp_path / "retention.db")
    store = Store(db)
    try:
        store.upsert_cluster("c", "https://example", True)
        now = datetime.now(UTC)
        store.record_login_events("c", [
            {"pod_name": "oauth-old", "user_name": name, "outcome": "bad_password",
             "at": (now - timedelta(days=age)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
             "provider": "ldap", "ldap_result_code": 49, "detail": None,
             "observed_at": now.strftime("%Y-%m-%dT%H:%M:%SZ")}
            for name, age in (("ancient", 500), ("recent", 1))])
        monkeypatch.setattr(auditlog, "ClusterClient", lambda *a, **kw: _EmptyAuditNode())
        cfg = ClusterConfig("c", "https://example")
        settings = Settings(clusters=[cfg], db_path=db, login_capture_enabled=True,
                            login_retention_days=retention_days,
                            login_capture_audit_node_names=("master-0",))
        logincapture.capture_once(store, cfg, settings, elector=_Elector(leader))
        assert sorted(r["user_name"] for r in store.login_events("c")) == kept
        assert all(r["source"] == "pod-log" for r in store.login_events("c"))
    finally:
        store.close()
```

### Block 126 — local-development/mock-app/tests/test_request_surface.py

Tests fail before removal: both endpoints answer 200 and both fixture keys are accepted.
Baseline: local-development/mock-app/tests/test_request_surface.py:1; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/tests/test_request_surface.py | edit -->

Old text:

```python
"""Every endpoint a–p parsed by a REAL gsd.ClusterClient over the mock's real TLS."""

from __future__ import annotations

import pytest

from gsd.kube import ClusterClient


@pytest.fixture
def client(mock_cluster):
    return ClusterClient(mock_cluster.cluster_config(), timeout=5.0)


# ── (a) GroupSync + (b) Groups via fetch() ────────────────────────────────────────────────
def test_fetch_groupsyncs_and_groups(client):
    groupsyncs, groups = client.fetch()
    assert groupsyncs is not None
    assert [gs.name for gs in groupsyncs] == ["ldap-sync"]
    gs = groupsyncs[0]
    assert gs.namespace == "group-sync-operator"
    assert gs.schedule == "*/30 * * * *"
    assert gs.generation == 3
    assert gs.provider_names == ("acme-ldap",)
    assert gs.ldap_filter == "(objectClass=groupOfNames)"
    assert gs.success_at == "2026-09-14T08:00:00Z"

    by_name = {g.name: g for g in groups}
    assert by_name["app-ocp-rbac-demo-cluster-admin"].member_count == 1
    assert by_name["app-ocp-rbac-demo-cluster-admin"].members == ["kubeadmin"]
    assert by_name["app-ocp-rbac-demo-cluster-admin"].sync_provider == "acme-ldap"
    assert by_name["app-ocp-rbac-demo-cluster-admin"].ldap_uid == "cn=ocp-admins,ou=Groups,dc=acme,dc=com"
    # The null-users group parses as empty, not an error.
    assert by_name["empty-team"].member_count == 0
    assert by_name["empty-team"].members == []


# ── (c) Users ──────────────────────────────────────────────────────────────────────────────
def test_fetch_users(client):
    users = client.fetch_users()
    assert users is not None
    by = {u["user_name"]: u for u in users}
    assert by["dana.lee"]["full_name"] == "Dana Lee"
    assert by["dana.lee"]["has_identity"] is True
    assert by["dana.lee"]["providers"] == ["acme-ldap"]
    assert by["kubeadmin"]["has_identity"] is False


# ── (d) Identities ───────────────────────────────────────────────────────────────────────
def test_fetch_identities(client):
    identities = client.fetch_identities()
    assert identities is not None
    assert identities["dana.lee"] == "2026-01-02T00:00:00Z"
    assert set(identities) == {"dana.lee", "lateef.o", "jane.smith", "developer"}


# ── (e) Namespaces ─────────────────────────────────────────────────────────────────────────
def test_fetch_namespaces(client):
    namespaces = client.fetch_namespaces(["team"])
    assert namespaces is not None
    by = {n["name"]: n for n in namespaces}
    assert by["acme-app"]["phase"] == "Active"
    # Only the configured key is copied, never the whole label map.
    assert by["acme-app"]["metadata"] == {"team": "acme"}


def test_fetch_namespaces_two_dimension_metadata(client):
    # The multi-dimension selector reads BOTH company.net/mnemonic and company.net/app-environment
    # (docs/DESIGN_reporting_selectors_snapshots_and_windows.md §6). The client down-selects to
    # exactly the requested keys that are PRESENT — both on a two-dimension namespace, only the
    # mnemonic on the missing-dimension negative case, never the whole label map.
    keys = ["company.net/mnemonic", "company.net/app-environment"]
    by = {n["name"]: n for n in client.fetch_namespaces(keys)}
    assert by["demo-prod"]["metadata"] == {"company.net/mnemonic": "demo",
                                           "company.net/app-environment": "prod"}
    assert by["demo-qa"]["metadata"] == {"company.net/mnemonic": "demo",
                                         "company.net/app-environment": "qa"}
    assert by["platform-prod"]["metadata"] == {"company.net/mnemonic": "klta",
                                               "company.net/app-environment": "prod"}
    # acme-app also carries team + kubernetes.io/metadata.name; neither is requested, so only the
    # two company.net keys come back.
    assert by["acme-app"]["metadata"] == {"company.net/mnemonic": "acme",
                                          "company.net/app-environment": "prod"}
    # Negative case: only the mnemonic is present, so only it is copied — this namespace drops out
    # of any AND-across-dimensions selection that also constrains app-environment.
    assert by["gsd-shared"]["metadata"] == {"company.net/mnemonic": "gsd"}


# ── (f)+(g) Group + User bindings ────────────────────────────────────────────────────────
def test_fetch_bindings(client):
    rows = client.fetch_bindings()
    by = {(r.binding_name, r.group_name): r for r in rows}
    admin = by[("cluster-admin-crb", "app-ocp-rbac-demo-cluster-admin")]
    assert admin.binding_kind == "ClusterRoleBinding"
    assert admin.role_name == "cluster-admin"
    assert admin.managed_source == "gitops"
    handmade = by[("handmade-reader-crb", "legacy-ops")]
    assert handmade.managed_source is None            # unmanaged finding
    assert handmade.exception == "reviewed 2026-09-10, temporary"


def test_fetch_user_bindings(client):
    rows = client.fetch_user_bindings()
    by = {(r.binding_name, r.user_name): r for r in rows}
    row = by[("viewer-rb", "lateef.o")]
    assert row.binding_kind == "RoleBinding"
    assert row.binding_namespace == "acme-app"
    assert row.role_name == "viewer"
    assert row.is_platform is False


# ── (h)+(i) Operator configs ────────────────────────────────────────────────────────────
def test_fetch_operator_configs(client):
    configs = client.fetch_operator_configs()
    assert configs is not None
    assert [c.name for c in configs] == ["acme-nsconfig"]
    assert configs[0].kind == "NamespaceConfig"
    assert configs[0].success_at == "2026-09-14T08:00:00Z"


# ── (j) Nodes (labelSelector honoured) ───────────────────────────────────────────────────
def test_fetch_nodes(client):
    nodes = client.fetch_nodes("node-role.kubernetes.io/master=")
    assert nodes == ["master-0", "master-1"]           # sorted; worker-0 filtered out


# ── (k) OAuth CR ─────────────────────────────────────────────────────────────────────────
def test_fetch_oauth(client):
    providers = client.fetch_oauth_providers()
    assert providers == ["acme-ldap"]
    dn = client.fetch_access_group_dn()
    assert dn == "cn=ocp-admins,ou=Groups,dc=acme,dc=com"


# ── (l) OAuth pods ───────────────────────────────────────────────────────────────────────


# ── (m) Pod log ──────────────────────────────────────────────────────────────────────────


# ── (n) Node-log listing + (o) file read ─────────────────────────────────────────────────
def test_node_log_listing_and_read(client):
    names = client.list_node_log_files("master-0", "oauth-server")
    assert names == ["audit-2026-09-01T00-00-00.000.log", "audit.log"]

    read = client.fetch_node_log_file("master-0", "oauth-server/audit.log")
    assert read is not None
    assert read.rotated is False
    text = read.data.decode("utf-8")
    assert '"authentication.openshift.io/username":"jane.smith"' in text
    assert text.count("\n") == 3                        # three events in the live file


def test_node_log_range_resume(client):
    full = client.fetch_node_log_file("master-0", "oauth-server/audit.log")
    total = len(full.data)
    # A ranged read from the middle returns the tail; a read at EOF returns nothing new.
    tail = client.fetch_node_log_file("master-0", "oauth-server/audit.log", offset=10)
    assert tail is not None and tail.rotated is False
    assert tail.data == full.data[10:]
    at_eof = client.fetch_node_log_file("master-0", "oauth-server/audit.log", offset=total)
    assert at_eof is not None and at_eof.data == b"" and at_eof.rotated is False


# ── (p) SubjectAccessReview ──────────────────────────────────────────────────────────────
def test_subject_access_review(client):
    allowed = client.create_subject_access_review(
        "kubeadmin",
        ["app-ocp-rbac-demo-cluster-admin", "system:authenticated", "system:authenticated:oauth"],
        {"verb": "list", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"},
    )
    assert allowed is True
    denied = client.create_subject_access_review(
        "lateef.o",
        ["system:authenticated", "system:authenticated:oauth"],
        {"verb": "list", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"},
    )
    assert denied is False


# ── auth gate ────────────────────────────────────────────────────────────────────────────
def test_wrong_token_is_auth_failed(mock_cluster):
    import os

    from gsd.kube import AUTH_FAILED, ClusterError

    cfg = mock_cluster.cluster_config(token_env="GSD_BAD_TOKEN")
    # resolve_token reads the env at call time, so overwrite AFTER the helper set the good one.
    os.environ["GSD_BAD_TOKEN"] = "not-the-token"
    client = ClusterClient(cfg, timeout=5.0)
    with pytest.raises(ClusterError) as exc:
        client.fetch()
    assert exc.value.outcome == AUTH_FAILED


@pytest.mark.parametrize(("kind", "api_version"), [
    ("GroupSyncList", "redhatcop.redhat.io/v1alpha1"), ("GroupList", "user.openshift.io/v1"),
    ("UserList", "user.openshift.io/v1"), ("IdentityList", "user.openshift.io/v1"),
    ("NamespaceList", "v1"), ("RoleBindingList", "rbac.authorization.k8s.io/v1"),
    ("ClusterRoleBindingList", "rbac.authorization.k8s.io/v1"),
    ("NamespaceConfigList", "redhatcop.redhat.io/v1alpha1"),
    ("GroupConfigList", "redhatcop.redhat.io/v1alpha1"), ("NodeList", "v1"), ("PodList", "v1"),
])
def test_list_envelope_carries_the_real_api_version(kind, api_version):
    # review #118 C4: no literal "unknown".
    from mock_app.responses import k8s_list
    assert k8s_list([], kind=kind)["apiVersion"] == api_version
```

New text:

```python
"""Every endpoint a–p parsed by a REAL gsd.ClusterClient over the mock's real TLS."""

from __future__ import annotations

import pytest

from gsd.kube import ClusterClient


@pytest.fixture
def client(mock_cluster):
    return ClusterClient(mock_cluster.cluster_config(), timeout=5.0)


# ── (a) GroupSync + (b) Groups via fetch() ────────────────────────────────────────────────
def test_fetch_groupsyncs_and_groups(client):
    groupsyncs, groups = client.fetch()
    assert groupsyncs is not None
    assert [gs.name for gs in groupsyncs] == ["ldap-sync"]
    gs = groupsyncs[0]
    assert gs.namespace == "group-sync-operator"
    assert gs.schedule == "*/30 * * * *"
    assert gs.generation == 3
    assert gs.provider_names == ("acme-ldap",)
    assert gs.ldap_filter == "(objectClass=groupOfNames)"
    assert gs.success_at == "2026-09-14T08:00:00Z"

    by_name = {g.name: g for g in groups}
    assert by_name["app-ocp-rbac-demo-cluster-admin"].member_count == 1
    assert by_name["app-ocp-rbac-demo-cluster-admin"].members == ["kubeadmin"]
    assert by_name["app-ocp-rbac-demo-cluster-admin"].sync_provider == "acme-ldap"
    assert by_name["app-ocp-rbac-demo-cluster-admin"].ldap_uid == "cn=ocp-admins,ou=Groups,dc=acme,dc=com"
    # The null-users group parses as empty, not an error.
    assert by_name["empty-team"].member_count == 0
    assert by_name["empty-team"].members == []


# ── (c) Users ──────────────────────────────────────────────────────────────────────────────
def test_fetch_users(client):
    users = client.fetch_users()
    assert users is not None
    by = {u["user_name"]: u for u in users}
    assert by["dana.lee"]["full_name"] == "Dana Lee"
    assert by["dana.lee"]["has_identity"] is True
    assert by["dana.lee"]["providers"] == ["acme-ldap"]
    assert by["kubeadmin"]["has_identity"] is False


# ── (d) Identities ───────────────────────────────────────────────────────────────────────
def test_fetch_identities(client):
    identities = client.fetch_identities()
    assert identities is not None
    assert identities["dana.lee"] == "2026-01-02T00:00:00Z"
    assert set(identities) == {"dana.lee", "lateef.o", "jane.smith", "developer"}


# ── (e) Namespaces ─────────────────────────────────────────────────────────────────────────
def test_fetch_namespaces(client):
    namespaces = client.fetch_namespaces(["team"])
    assert namespaces is not None
    by = {n["name"]: n for n in namespaces}
    assert by["acme-app"]["phase"] == "Active"
    # Only the configured key is copied, never the whole label map.
    assert by["acme-app"]["metadata"] == {"team": "acme"}


def test_fetch_namespaces_two_dimension_metadata(client):
    # The multi-dimension selector reads BOTH company.net/mnemonic and company.net/app-environment
    # (docs/DESIGN_reporting_selectors_snapshots_and_windows.md §6). The client down-selects to
    # exactly the requested keys that are PRESENT — both on a two-dimension namespace, only the
    # mnemonic on the missing-dimension negative case, never the whole label map.
    keys = ["company.net/mnemonic", "company.net/app-environment"]
    by = {n["name"]: n for n in client.fetch_namespaces(keys)}
    assert by["demo-prod"]["metadata"] == {"company.net/mnemonic": "demo",
                                           "company.net/app-environment": "prod"}
    assert by["demo-qa"]["metadata"] == {"company.net/mnemonic": "demo",
                                         "company.net/app-environment": "qa"}
    assert by["platform-prod"]["metadata"] == {"company.net/mnemonic": "klta",
                                               "company.net/app-environment": "prod"}
    # acme-app also carries team + kubernetes.io/metadata.name; neither is requested, so only the
    # two company.net keys come back.
    assert by["acme-app"]["metadata"] == {"company.net/mnemonic": "acme",
                                          "company.net/app-environment": "prod"}
    # Negative case: only the mnemonic is present, so only it is copied — this namespace drops out
    # of any AND-across-dimensions selection that also constrains app-environment.
    assert by["gsd-shared"]["metadata"] == {"company.net/mnemonic": "gsd"}


# ── (f)+(g) Group + User bindings ────────────────────────────────────────────────────────
def test_fetch_bindings(client):
    rows = client.fetch_bindings()
    by = {(r.binding_name, r.group_name): r for r in rows}
    admin = by[("cluster-admin-crb", "app-ocp-rbac-demo-cluster-admin")]
    assert admin.binding_kind == "ClusterRoleBinding"
    assert admin.role_name == "cluster-admin"
    assert admin.managed_source == "gitops"
    handmade = by[("handmade-reader-crb", "legacy-ops")]
    assert handmade.managed_source is None            # unmanaged finding
    assert handmade.exception == "reviewed 2026-09-10, temporary"


def test_fetch_user_bindings(client):
    rows = client.fetch_user_bindings()
    by = {(r.binding_name, r.user_name): r for r in rows}
    row = by[("viewer-rb", "lateef.o")]
    assert row.binding_kind == "RoleBinding"
    assert row.binding_namespace == "acme-app"
    assert row.role_name == "viewer"
    assert row.is_platform is False


# ── (h)+(i) Operator configs ────────────────────────────────────────────────────────────
def test_fetch_operator_configs(client):
    configs = client.fetch_operator_configs()
    assert configs is not None
    assert [c.name for c in configs] == ["acme-nsconfig"]
    assert configs[0].kind == "NamespaceConfig"
    assert configs[0].success_at == "2026-09-14T08:00:00Z"


# ── (j) Nodes (labelSelector honoured) ───────────────────────────────────────────────────
def test_fetch_nodes(client):
    nodes = client.fetch_nodes("node-role.kubernetes.io/master=")
    assert nodes == ["master-0", "master-1"]           # sorted; worker-0 filtered out


# ── (k) OAuth CR ─────────────────────────────────────────────────────────────────────────
def test_fetch_oauth(client):
    providers = client.fetch_oauth_providers()
    assert providers == ["acme-ldap"]
    dn = client.fetch_access_group_dn()
    assert dn == "cn=ocp-admins,ou=Groups,dc=acme,dc=com"


# ── (l) OAuth pods ───────────────────────────────────────────────────────────────────────


# ── (m) Pod log ──────────────────────────────────────────────────────────────────────────


# ── (n) Node-log listing + (o) file read ─────────────────────────────────────────────────
def test_node_log_listing_and_read(client):
    names = client.list_node_log_files("master-0", "oauth-server")
    assert names == ["audit-2026-09-01T00-00-00.000.log", "audit.log"]

    read = client.fetch_node_log_file("master-0", "oauth-server/audit.log")
    assert read is not None
    assert read.rotated is False
    text = read.data.decode("utf-8")
    assert '"authentication.openshift.io/username":"jane.smith"' in text
    assert text.count("\n") == 3                        # three events in the live file


def test_node_log_range_resume(client):
    full = client.fetch_node_log_file("master-0", "oauth-server/audit.log")
    total = len(full.data)
    # A ranged read from the middle returns the tail; a read at EOF returns nothing new.
    tail = client.fetch_node_log_file("master-0", "oauth-server/audit.log", offset=10)
    assert tail is not None and tail.rotated is False
    assert tail.data == full.data[10:]
    at_eof = client.fetch_node_log_file("master-0", "oauth-server/audit.log", offset=total)
    assert at_eof is not None and at_eof.data == b"" and at_eof.rotated is False


# ── (p) SubjectAccessReview ──────────────────────────────────────────────────────────────
def test_subject_access_review(client):
    allowed = client.create_subject_access_review(
        "kubeadmin",
        ["app-ocp-rbac-demo-cluster-admin", "system:authenticated", "system:authenticated:oauth"],
        {"verb": "list", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"},
    )
    assert allowed is True
    denied = client.create_subject_access_review(
        "lateef.o",
        ["system:authenticated", "system:authenticated:oauth"],
        {"verb": "list", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"},
    )
    assert denied is False


# ── auth gate ────────────────────────────────────────────────────────────────────────────
def test_wrong_token_is_auth_failed(mock_cluster):
    import os

    from gsd.kube import AUTH_FAILED, ClusterError

    cfg = mock_cluster.cluster_config(token_env="GSD_BAD_TOKEN")
    # resolve_token reads the env at call time, so overwrite AFTER the helper set the good one.
    os.environ["GSD_BAD_TOKEN"] = "not-the-token"
    client = ClusterClient(cfg, timeout=5.0)
    with pytest.raises(ClusterError) as exc:
        client.fetch()
    assert exc.value.outcome == AUTH_FAILED


@pytest.mark.parametrize(("kind", "api_version"), [
    ("GroupSyncList", "redhatcop.redhat.io/v1alpha1"), ("GroupList", "user.openshift.io/v1"),
    ("UserList", "user.openshift.io/v1"), ("IdentityList", "user.openshift.io/v1"),
    ("NamespaceList", "v1"), ("RoleBindingList", "rbac.authorization.k8s.io/v1"),
    ("ClusterRoleBindingList", "rbac.authorization.k8s.io/v1"),
    ("NamespaceConfigList", "redhatcop.redhat.io/v1alpha1"),
    ("GroupConfigList", "redhatcop.redhat.io/v1alpha1"), ("NodeList", "v1"), ("PodList", "v1"),
])
def test_list_envelope_carries_the_real_api_version(kind, api_version):
    # review #118 C4: no literal "unknown".
    from mock_app.responses import k8s_list
    assert k8s_list([], kind=kind)["apiVersion"] == api_version


def test_retired_pod_endpoints_are_not_routes(mock_cluster):
    import httpx
    with httpx.Client(base_url=mock_cluster.base_url, verify=mock_cluster.ca_file,
                      headers={"Authorization": f"Bearer {mock_cluster.token}"}) as wire:
        for path in ("/api/v1/namespaces/openshift-authentication/pods",
                     "/api/v1/namespaces/openshift-authentication/pods/old/log"):
            assert wire.get(path).status_code == 404


def test_retired_fixture_keys_remain_unknown_key_refusals():
    from mock_app.fixture import Fixture, FixtureError
    for key in ("oauthPods", "podLog"):
        with pytest.raises(FixtureError):
            Fixture.from_dict({key: {}})
```

### Block 127 — local-development/mock-app/README.md

Remove the retired live path; keep audit capture and stored history.
Baseline: local-development/mock-app/README.md:31; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/mock-app/README.md | edit -->

Old text:

```text
│   ├── podlog.py     pod-log text stream
```

New text:

```text
```

### Block 128 — local-development/gsd/store.py

Update the surviving contract.
Baseline: local-development/gsd/store.py:2933; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
        parser know where its input came from. gsd/logincapture.event_dict() builds these, so callers
```

New text:

```python
        parser know where its input came from. Legacy fixtures use gsd/logincapture.event_dict(), so callers
```

### Block 129 — local-development/API.md

Remove the retired path.
Baseline: local-development/API.md:575; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/API.md | edit -->

Old text:

```text
Login attempts against this cluster's oauth-server: who, when, and why a failure failed. Read from the
oauth-server pod log, which names the person only at `spec.logLevel: Debug` on the authentication
**operator** CR (`authentications.operator.openshift.io/cluster` — not the OAuth CR).

```

New text:

```text
Login attempts against this cluster's oauth-server. The live reader is audit-log only: no
OAuth Debug setting or pod-log read. Existing pod-log rows and their LDAP causes remain readable.
Top-level `source` is audit-log; each attempt's `source` still identifies its original record.
New failures report `status_code` and `error_message`, without LDAP result codes or AD sub-codes.

```

### Block 130 — local-development/API.md

Update the surviving contract.
Baseline: local-development/API.md:594; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/API.md | edit -->

Old text:

```text
| `capture_started_at` | when watching began. Stable — set once by the first successful read. May be *later* than `retained_since`, because the first read looks back an hour |
```

New text:

```text
| `capture_started_at` | when watching began. Stable — set once by the first successful read. May be later than `retained_since`, because audit backfill reads older rotated files |
```

### Block 131 — local-development/API.md

Update the surviving contract.
Baseline: local-development/API.md:599; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/API.md | edit -->

Old text:

```text
Nothing before capture began exists to fetch — the log dies with its pod — so **an empty `attempts` is a
statement about the window, never proof that nobody logged in.**
```

New text:

```text
A first audit read backfills available rotated files within retention. **An empty `attempts` is a
statement about that window, never proof that nobody logged in.** Historical pod-log rows keep their
original observation window and causes. No migration deletes them; normal retention still applies.
```

### Block 132 — local-development/API.md

Update the surviving contract.
Baseline: local-development/API.md:585; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/API.md | edit -->

Old text:

```text
**`rejected` — shown as "no match" — covers two different things and cannot separate them.** The identity provider's search
```

New text:

```text
**Historical `rejected` rows — shown as "no match" — cover two different things and cannot separate them.** The identity provider's search
```

### Block 133 — README.md

Update the surviving contract.
Baseline: README.md:83; later blocks for a file apply after its preceding blocks.

<!-- block: README.md | edit -->

Old text:

```text
failure failed. Read by default from the oauth-server audit log on the control-plane nodes
```

New text:

```text
failure failed, to the extent the record supplies a cause. Read from the oauth-server audit log on the control-plane nodes
```

### Block 134 — local-development/gsd/api.py

Update the surviving contract.
Baseline: local-development/gsd/api.py:1924; later blocks for a file apply after its preceding blocks.

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
            "source": settings.login_capture_source,
```

New text:

```python
            "source": "audit-log",
```

### Block 135 — chart history

Record the new release without rewriting older version-history comments.

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

Old text:

```text
apiVersion: v2
```

New text:

```text
apiVersion: v2
# 0.58.0 / app 0.36.0 (#321): audit-only capture; remove OAuth Debug Jobs and pod reader.
```

### Block 136 — docs/DESIGN_login_capture.md

Review round 1: accepted OB1-lite fix A.

<!-- block: docs/DESIGN_login_capture.md | edit -->

Old text:

```text
Who logged in, when, from which provider, and why an attempt failed — accumulated from the
oauth-server's own pod logs.

**Status: shipped.** The parser, capture loop, storage, API and Logins tab are live. This document
describes what exists and the measurements behind it. Where a decision looks arbitrary, the reason is
here; where something is deliberately *not* done, that is here too, because most of it will be
proposed again.
```

New text:

```text
Who logged in, when, from which provider, and why an attempt failed — accumulated from the
oauth-server's own pod logs until chart 0.58.0 / app 0.36.0, and from its audit log since (#321).

**Status: the pod-log reader is retired (#321).** Live capture reads only the audit log ("The
oauth-server AUDIT LOG" below). The parser, storage, API and Logins tab remain, because stored
pod-log rows stay readable. The pod-log sections are the as-built record of the retired reader and
the measurements behind it; the loop, window and guard names they give no longer exist in the code.
Where a decision looks arbitrary, the reason is here; where something is deliberately *not* done,
that is here too, because most of it will be proposed again.
```

### Block 137 — docs/DESIGN_login_capture.md

Review round 1: accepted OB1-lite fix A.

<!-- block: docs/DESIGN_login_capture.md | edit -->

Old text:

```text
| capture loop | `gsd/logincapture.py#capture_once` | reads each oauth-server pod incrementally, decides what is settled enough to record, advances a per-pod cursor |
| log reader | `gsd/kube.py#ClusterClient.fetch_pod_log` | streamed, byte-bounded and wall-clock-bounded read of one pod's log |
```

New text:

```text
| capture loop | `gsd/logincapture.py#capture_once` | off reads nothing; on dispatches to `gsd/auditlog.py#capture_once`, which reads each control-plane node's audit file from a per-file cursor. The per-pod loop it replaced was removed in #321 |
| log reader | `gsd/kube.py#ClusterClient.fetch_node_log_file` | byte-bounded and wall-clock-bounded read of one node's audit file through the node proxy. The pod-log reader (`fetch_pod_log`) was removed in #321 |
```

### Block 138 — docs/DESIGN_login_capture.md

Review round 1: accepted OB1-lite fix A.

<!-- block: docs/DESIGN_login_capture.md | edit -->

Old text:

```text
| `gsd/logincapture.py#OVERLAP_SECONDS` | 60 | how far behind the cursor each read starts again. Must exceed 2×`ATTEMPT_WINDOW` for parse context (below) |
| `gsd/logincapture.py#SETTLE_SECONDS` | 30 | how far behind the log's tip an attempt must be before it is recorded |
| `gsd/logincapture.py#FIRST_SIGHT_SECONDS` | 3600 | how far back a first read goes for a pod with no cursor |
| `gsd/kube.py#LOG_READ_BUDGET_SECONDS` | 20 | wall-clock bound on one pod-log read |

The prerequisite is `authLogLevel`, which raises `spec.logLevel` on the authentication **operator** CR
so the oauth-server names the person logging in, plus `loginCapture`, which grants a namespaced read
of those pod logs. With capture on and Debug off this reads real logs and finds nothing — correct
rather than broken.
```

New text:

```text
| `OVERLAP_SECONDS` (retired, #321) | 60 | how far behind the cursor each pod-log read started again. Had to exceed 2×`ATTEMPT_WINDOW` for parse context (below) |
| `SETTLE_SECONDS` (retired, #321) | 30 | how far behind the log's tip an attempt had to be before it was recorded |
| `FIRST_SIGHT_SECONDS` (retired, #321) | 3600 | how far back a first read went for a pod with no cursor |
| `gsd/kube.py#LOG_READ_BUDGET_SECONDS` | 20 | wall-clock bound on one node audit-file read (formerly one pod-log read) |

The pod-log reader's prerequisite was `authLogLevel`, which raised `spec.logLevel` on the
authentication **operator** CR so the oauth-server named the person logging in, plus a namespaced
read of those pod logs. Both were removed in #321: the audit log names the person at the default
verbosity, and a cluster still at Debug is restored by hand (the chart README's migration note).
```

### Block 139 — docs/DESIGN_login_capture.md

Review round 1: accepted OB1-lite fix A.

<!-- block: docs/DESIGN_login_capture.md | edit -->

Old text:

```text
| trailing edge (lines not written yet) | an attempt read mid-flight concludes on partial evidence — the provider-chain `failed` is present, the success that follows is not — and the honest-but-wrong `failed` row sits beside the real one forever | `gsd/logincapture.py#_recordable`: withhold attempts younger than `SETTLE_SECONDS` + `ATTEMPT_WINDOW` |
| leading edge (lines behind the window) | a window opening between a bind error and its verdict parses the verdict alone, so a login already stored as `bad_password` at the cause is stored *again* as `failed` at the verdict | `gsd/logincapture.py#_not_clipped`: drop attempts within `ATTEMPT_WINDOW` of the window's start |
```

New text:

```text
| trailing edge (lines not written yet) | an attempt read mid-flight concludes on partial evidence — the provider-chain `failed` is present, the success that follows is not — and the honest-but-wrong `failed` row sits beside the real one forever | `_recordable` (retired, #321): withheld attempts younger than `SETTLE_SECONDS` + `ATTEMPT_WINDOW` |
| leading edge (lines behind the window) | a window opening between a bind error and its verdict parses the verdict alone, so a login already stored as `bad_password` at the cause is stored *again* as `failed` at the verdict | `_not_clipped` (retired, #321): dropped attempts within `ATTEMPT_WINDOW` of the window's start |
```

### Block 140 — local-development/tests/test_values_defaults.py

Review round 1: accepted OB1-lite fix B.

<!-- block: local-development/tests/test_values_defaults.py | edit -->

Old text:

```text
    assert len(rows) >= 9, sorted(rows)
```

New text:

```text
    # Eight since #321 removed loginCapture.namespace; a floor, so a table that loses rows still fails.
    assert len(rows) >= 8, sorted(rows)
```

### Block 141 — local-development/tests/test_users_tab_logins.py

Review round 1: accepted OB1-lite fix C.

<!-- block: local-development/tests/test_users_tab_logins.py | edit -->

Old text:

```text
    def test_pod_log_is_the_default_source_and_says_what_it_cannot_see(self, tmp_path):
        body = _client(tmp_path).get("/api/clusters/c1/logins", headers=ADMIN).json()
        assert body["source"] == "pod-log"
        assert body["kinds"] == ["credential", "cli"]
        assert "since capture began" in body["note"] and "audit log" not in body["note"]
        assert all(r["source"] == "pod-log" and r["kind"] == "credential" for r in body["attempts"])
```

New text:

```text
    def test_the_live_source_is_audit_log_and_stored_pod_log_rows_keep_their_own(self, tmp_path):
        """#321: the envelope names the live reader (audit-log only); the seeded rows are stored
        pod-log history and keep their row-level source and kind (decision 3)."""
        body = _client(tmp_path).get("/api/clusters/c1/logins", headers=ADMIN).json()
        assert body["source"] == "audit-log"
        assert body["kinds"] == ["credential", "cli"]
        assert "audit log" in body["note"] and "since capture began" not in body["note"]
        assert body["attempts"]
        assert all(r["source"] == "pod-log" and r["kind"] == "credential" for r in body["attempts"])
```

### Block 142 — local-development/tests/test_ui.py

Review round 1: accepted OB1-lite fix D.

<!-- block: local-development/tests/test_ui.py | edit -->

Old text:

```text
        # BOTH halves, because either one alone records nothing: the module has to run, and the
        # operand has to be verbose enough to write a username at all. Since chart 0.14.0 the
        # module is on by default, so the card says that rather than prescribing the default.
        assert "chart default since 0.14.0 is on" in body
        assert "loginCapture.enabled=true" in body
        assert "config.loginCapture.enabled" not in body, "the old card named a key that does not exist"
        assert "authLogLevel.manage" in body
        assert "Debug" in body
        assert "audit log" in body
```

New text:

```text
        # Since #321 one switch: the audit log names the person at default verbosity, so the card
        # names the module and says nothing has to raise the operator's logLevel. Since chart
        # 0.14.0 the module is on by default, so the card says that rather than prescribing it.
        assert "chart default since 0.14.0 is on" in body
        assert "loginCapture.enabled=true" in body
        assert "config.loginCapture.enabled" not in body, "the old card named a key that does not exist"
        assert "authLogLevel" not in body, "the retired Debug switch must not be offered"
        assert "spec.logLevel" in body
        assert "audit log" in body
```

## Certified file deletions for phase 2

After the empty-New blocks check and are applied, remove these empty paths; none is a surviving
module or template. The current checker cannot perform this filesystem step.

- charts/group-sync-dashboard/templates/auth-loglevel-job.yaml
- charts/group-sync-dashboard/templates/auth-loglevel-rbac.yaml
- charts/group-sync-dashboard/templates/auth-loglevel-revert-job.yaml
- local-development/mock-app/mock_app/podlog.py
- local-development/tests/test_login_capture_cross_seam.py
- local-development/tests/test_logincapture_loop.py

## Deferred version blocks — applied after rebasing onto #322

These six exact Old/New payloads are excluded from current-tree checks. Activate and check them
after #322; do not apply intermediate release bumps on this branch. The S4c Old reservation is
anticipated, not measured; re-anchor its two metadata rows together if #322 differs.

### Deferred 1 — charts/group-sync-dashboard/Chart.yaml

**Applied after the rebase onto #322 (merge `49c4834`).**

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

Old text:

```text
version: 0.57.0
```

New text:

```text
version: 0.58.0
```

### Deferred 2 — charts/group-sync-dashboard/Chart.yaml

**Applied after the rebase onto #322 (merge `49c4834`).**

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

Old text:

```text
appVersion: "0.35.0"
```

New text:

```text
appVersion: "0.36.0"
```

### Deferred 3 — local-development/pyproject.toml

**Applied after the rebase onto #322 (merge `49c4834`).**

<!-- block: local-development/pyproject.toml | edit -->

Old text:

```text
version = "0.35.0"
```

New text:

```text
version = "0.36.0"
```

### Deferred 4 — local-development/gsd/__init__.py

**Applied after the rebase onto #322 (merge `49c4834`).**

<!-- block: local-development/gsd/__init__.py | edit -->

Old text:

```text
__version__ = "0.35.0"
```

New text:

```text
__version__ = "0.36.0"
```

### Deferred 5 — docs/specs/SPEC_S4c_credential_lifecycle.md

**Applied after the rebase onto #322 (merge `49c4834`).**

<!-- block: docs/specs/SPEC_S4c_credential_lifecycle.md | edit -->

Old text:

```text
| Version on release | app 0.36.0, chart 0.58.0 |
```

New text:

```text
| Version on release | app 0.37.0, chart 0.59.0 |
```

### Deferred 6 — docs/specs/README.md

**Applied after the rebase onto #322 (merge `49c4834`).**

<!-- block: docs/specs/README.md | edit -->

Old text:

```text
| S4c | [`SPEC_S4c_credential_lifecycle.md`](SPEC_S4c_credential_lifecycle.md) — S4 step C: the credential lifecycle — the daily ping, `self-login` renewal at the fixed margin, and the per-credential gate on a fleet-account Lease, durable and replica-shared; the design of #285 | S — cluster configuration | — | app 0.36.0, chart 0.58.0 | [#285](https://github.com/ephico2real2/group-sync-dashboard/issues/285) | specified |
```

New text:

```text
| S4c | [`SPEC_S4c_credential_lifecycle.md`](SPEC_S4c_credential_lifecycle.md) — S4 step C: the credential lifecycle — the daily ping, `self-login` renewal at the fixed margin, and the per-credential gate on a fleet-account Lease, durable and replica-shared; the design of #285 | S — cluster configuration | — | app 0.37.0, chart 0.59.0 | [#285](https://github.com/ephico2real2/group-sync-dashboard/issues/285) | specified |
```
