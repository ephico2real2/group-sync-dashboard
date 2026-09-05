# Review — PR #75, chart 0.14.0: every switch on by default unless it costs something

Adversarial second-opinion pass, 2026-09-05, on the ten-claim brief for #75 (the chart-defaults
release; no feature spec — the operator's rule of 2026-09-05 is the specification). Codex
(gpt-5.6-sol, xhigh) reviewed the immutable commit `9a9cbbd` and, its sandbox refusing to create the
mandated copy, traced from `git show` and upstream oauth-proxy source; Cursor (Grok 4.6 high fast,
ask mode, shell blocked) traced the checked-out tree. Every verdict was re-checked here before a
decision. The orchestrator's own live validation on the reference cluster found the most important
defect (C3/C9) before either reviewer reported, and both reviewers named it independently.

Two operator decisions landed during the pass and are folded in below: `oauthProxy.skipProviderButton`
stays `false` (people log in from the OpenShift login screen), and `monitoring.serviceMonitor.enabled`
/ `monitoring.prometheusRule.enabled` stay `false` (the reference cluster runs no Prometheus), with
the on-state rendering verified first. The second pass added one more exception:
`oauthProxy.requestLogging` stays `false` because oauth-proxy logs the complete request URI, the OAuth
callback's authorization code included. Final state: three switches flipped
(`podDisruptionBudget.enabled`, `loginCapture.enabled`, `oauthProxy.apiTokenAccess.enabled`); eight
switches, nine keys, kept off. The operator also removed the Grafana lab override from
`environments/crc.yaml` (nothing on the reference cluster reads the board).

## Verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 only the stated booleans stay false, each with a reason | REFUTED | REFUTED | **Accepted** — `allowPrivilegeEscalation` and `trustedCA.existingConfigMap.enabled` had no reason next to them; comments added; the exception list is now held by `test_values_defaults.py` |
| C2 the default render on OpenShift | PLAUSIBLE | PLAUSIBLE | — (neither could render; measured here: lint clean, template exit 0, server-side dry run accepted) |
| C3 no new switch interaction | REFUTED | CONFIRMED | **Accepted** — the PDB selector matched the hook Job pods (fixed in `d690201` before the reports arrived; Codex reviewed the earlier commit) |
| C4 token access semantics and docs | REFUTED | REFUTED + PLAUSIBLE | **Accepted** — `rbac.yaml` and `docs/api-access.md` said off was the default; both rewritten; the wide-view consequence of a passing token is now stated in `docs/api-access.md` |
| C5 login capture on while the lines do not exist | REFUTED | REFUTED | **Accepted on the fact; both snippets rejected** — see below |
| C6 every statement of the old defaults is gone | REFUTED | REFUTED | **Accepted** — root README row, chart README prerequisites, quick-check commands; monitoring rows then reverted with the operator's decision |
| C7 the edited tests exercise distinct states | REFUTED | PLAUSIBLE | **Accepted** — the usage-tier SAR test repeated two states already covered; it now holds "visibility off, token access alone keeps the grant" |
| C8 versioning and the ladder | REFUTED | REFUTED | **Accepted** — the B1 note kept 0.16.0; fixed; the check is generalised in `test_specs_index.py` |
| C9 upgrade impact | REFUTED | CONFIRMED | **Accepted** — the same PDB defect, seen as an upgrade-time failure on any install with the hook Jobs |
| C10 the reference deployment's table | CONFIRMED | CONFIRMED | — ; the redundant-row test is generalised to every row that says "redundant" |

## C3 / C9 — the PodDisruptionBudget failed on the hook Job pods

**Finding (orchestrator, live; then Codex F1 and Cursor debt note).** With the budget on by default,
the reference cluster reported `SyncFailed: jobs.batch does not implement the scale subresource`,
`DisruptionAllowed=False`, `disruptionsAllowed 0`, `expectedPods 0`. The `authLogLevel` hook Job pods
carried `gsd.selectorLabels`, so the disruption controller resolved a matched pod to a Job, which has
no scale subresource, and failed the whole budget. With `maxUnavailable: 1` that is a blocked drain,
the exact failure the values comment promises the default avoids. The same labels made the Service
match a running hook pod (a pod with no readiness probe is Ready as soon as its container starts).

**Re-check.** `oc get pdb` status and events on CRC before the fix (above); after the fix and after the
operator removed a leftover chart-0.1.0 hook Job that still carried the old labels: `expectedPods 1`,
`currentHealthy 1`, `disruptionsAllowed 1`, `DisruptionAllowed=True/SufficientPods`.

**Decision.** Fixed at the source: the two hook Job pod templates carry `app.kubernetes.io/name`,
`instance` and `component` and drop the `app` selector label; `tests/test_chart_pdb.py` holds the PDB
and Service selectors to the Deployment's pod template and refuses either Job's labels. Codex's F1
snippet is the same change (it read the fixed commit). The operator's rule for the future is recorded:
a budget covers only the dashboard Deployment and, in C3, the reporting service Deployment.

## C1 — kept-off booleans without a stated reason

**Finding (both).** `securityContext.allowPrivilegeEscalation: false` had no comment; Cursor's
enumeration of every `: false` matched the claimed list. Re-check found a second one with no reason in
its own block: `trustedCA.existingConfigMap.enabled`.

**Decision.** Accepted; comments added for both. Snippet for the comment accepted (both reviewers
proposed the same two lines). Both proposed *tests* rejected: each asserts a phrase ("hardening") in the
comment, which tests prose. Replaced by `test_values_defaults.py`, which holds the set of false defaults
to the enumerated exceptions and checks each has a comment block above it.

## C4 — token access "off, the default" and the wide-view consequence

**Finding (both).** `templates/rbac.yaml` said API-token access off "is the default" ten lines above the
sentence saying both consumers are on by default; `docs/api-access.md` opened with "Enable it on the
chart" and `--set …=true`. Cursor, PLAUSIBLE: a token that passes the proxy's SubjectAccessReview lands
on the wide view because the application repeats the identical default check; Codex confirmed the same
from oauth-proxy's source and added that the Usage tab still requires its stricter review.

**Re-check.** `visibility.adminSar` and `apiTokenAccess.delegateUrls` both name `list
clusterrolebindings` in `values.yaml`; the rbac condition is `apiTokenAccess OR visibility`.

**Decision.** Accepted. Both files rewritten in the orchestrator's words; the api-access doc now states
the wide-view consequence (the first version overclaimed it; the second pass corrected it). Cursor's rbac-comment
test and Codex's `test_chart_default_documentation.py` rejected as prose tests; the generalised
`test_no_current_doc_tells_the_operator_to_enable_a_default` covers the `--set` instruction.

## C5 — the UI's capture-off card

**Finding (both).** The card told the reader to set `config.loginCapture.enabled=true` (a key that
does not exist — Codex) and `authLogLevel.manage`, one now the default and the other the setting the
release deliberately leaves off. `test_ui.py` pinned the stale instruction.

**Decision.** Accepted on the fact; both snippets rejected. Cursor's card says "Do not turn on
`authLogLevel.manage`"; Codex's says to inspect the deployed values. Until D1 ships, the Debug level is
the only source that produces login lines and the chart still supports it, so the card now says the
module is off on this release (default on since 0.14.0), that lines exist only at Debug, that the chart
leaves Debug off because the audit log is replacing it, and how to turn either on. The Playwright test
holds the new wording and passed locally.

## C6 — documents that still described 0.13.0

**Finding (both).** Root README row `monitoring.serviceMonitor.enabled | false`; chart README
prerequisites "only if you enable"; the plain-Kubernetes recipe (Cursor, not asked) did not turn off
`loginCapture` whose Role lives in `openshift-authentication`; `docs/LOGIN_CAPTURE_QUICKCHECK.md` set
`loginCapture.enabled=true` twice (Cursor N4).

**Decision.** Accepted. The Kubernetes recipe now sets `loginCapture.enabled=false`; the quick-check
commands drop the default and say why. The monitoring rows were first flipped to `true`, then the
operator decided both monitoring switches stay off; the rows say `false` again with the rendering
verification noted. Codex's replacement of the whole README table rejected: only one row changed.

## C7 — a test that repeated covered states

**Finding (Codex).** `test_the_usage_tier_reuses_the_one_sar_grant` rendered the default and the
both-off state, both already held by neighbouring tests, and its docstring said the binding disappears
"when visibility is off" while the invocation also turned token access off. A nearby docstring said
"(default off)" of token access.

**Decision.** Accepted. The test now holds the one state nothing else covered — visibility off, token
access alone keeps the grant — and the docstring says so; the historical "(default off)" reads "off by
default at the time". Codex's `test_chart_test_intent.py`, a test that parses the test file's source,
rejected.

## C8 — the B1 note

**Finding (both).** `SPEC_B1_offsite_backup.md` header says chart 0.17.0; its note said "superseded by
chart 0.16.0". The index test compares headers only.

**Decision.** Accepted; note fixed. Both B1-specific tests rejected in favour of a generalised check in
`test_specs_index.py`: any "superseded by chart X" in a spec must equal the chart version in its index
row.

## Not asked, and what happened to it

- **Cursor N1 / Codex F8, `environments/crc.yaml` comment** ("the ServiceMonitor stays off"): with the
  operator's decision the ServiceMonitor does stay off; the comment now says why (no Prometheus on the
  reference cluster, off by decision). Both snippets, which describe a rendering ServiceMonitor,
  superseded. The environments README row for the Grafana dashboard stays "lab override" and the
  redundant-row test now measures every row that says "redundant".
- **Cursor N2, `environments/example-production.yaml`** pinned `apiTokenAccess.enabled: false` with the
  0.13.0 rationale. Accepted: flipped to `true` with the 0.14.0 reasoning; a copied template no longer
  undoes the default.
- **Codex F7, `docs/ACCESS_CONTROL.md` and the chart README** documented the wide-tier check as `list
  groups.user.openshift.io`; `values.yaml` has shipped `list clusterrolebindings` since the visibility
  review. Pre-existing drift in a security document, accepted and fixed in the threshold table, the
  verification command and the README row; `test_values_defaults.py` holds all three to the values file.
- **Cursor, the plain-Kubernetes recipe**: accepted (under C6).
- **Both, `rules()` in `test_metrics.py`**: the split on Helm's document separator is sound; the
  `--set monitoring.prometheusRule.enabled=true` it passes is now required again, not redundant.

## Outcome

Nine of ten claims refuted by at least one reviewer; every refutation re-checked and accepted on the
fact. Snippets accepted as written: the two comment lines (C1) and the hook-label change (already in the
tree). Snippets rejected: every prose-asserting test (replaced by four generalised tests in
`test_values_defaults.py`, `test_specs_index.py` and `test_environments_readme.py`), the two UI card
wordings (one forbids the only working source, one omits how to turn it on), the whole-table README
replacement, the source-parsing test, and the two CRC comment rewrites the operator's decision
superseded. Re-validated after the edits: full suite (2,077 passed before the review fixes; the
affected files and the Playwright card test after), `helm lint`, `helm template` in the default state
and with each flipped switch off, `oc apply --dry-run=server` of the monitoring objects against the
CRDs, and a live redeploy on the reference cluster with the PDB status read back. The second pass on
the fixed head is recorded below.

## Second pass — on the fixed head `1b19ad1`

Same models, a ten-claim brief: seven claims that each first-pass fix closed its hole, three that the
first pass never attacked (the upgrade delta, what request logging writes, a colliding `podLabels`
key). Codex measured with a shell this time (the sandbox again refused the external copy, so it
rendered from `git show`); Cursor traced.

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 hook pods match no selector in any state | CONFIRMED | CONFIRMED | — |
| C2 `test_values_defaults.py` enumerates every boolean | REFUTED | REFUTED | **Accepted** — `flatten` stored a list as one leaf, so `clusters[].enabled` was invisible; list-aware now, with the regression test both proposed |
| C3 values comments claim only what the code does | REFUTED | PLAUSIBLE | **Accepted** — the `requestLogging` comment said "log volume"; see C9 |
| C4 token-access docs and the wide-view sentence | REFUTED | REFUTED | **Accepted** — the first-pass sentence overclaimed; rewritten (fail-closed path, Usage tier); the ServiceAccount finding routed to D2 |
| C5 the UI card's statements are true | CONFIRMED | CONFIRMED | — ; Cursor's V1 test hole accepted |
| C6 the environments table after the monitoring decision | CONFIRMED | CONFIRMED | — ; the Grafana row then removed with the override |
| C7 the four release records agree | REFUTED | REFUTED | **Accepted** — the Chart.yaml history named the rule, not the release; the index said "seven" while listing eight keys; both rewritten |
| C8 the 0.13.0 → 0.14.0 upgrade delta | REFUTED | PLAUSIBLE | **Rejected** — the extra delta is the `helm.sh/chart` label and the config checksum, which every chart bump changes; the immutable-Job half confirmed |
| C9 request logging leaks nothing | REFUTED | PLAUSIBLE | **Accepted** — see below |
| C10 a colliding `podLabels` key | REFUTED | REFUTED | **Accepted on the fact; Cursor's snippet rejected** — see below |

### C9 — request logging writes the OAuth code to the pod log

**Finding (Codex).** oauth-proxy's `logging_handler.go` formats `url.RequestURI()`, query string
included, and excludes no path; the callback is `GET /oauth/callback?code=…&state=…` (`oauthproxy.go`
redeems `req.Form.Get("code")`). `-request-logging=true` therefore writes every authorization code,
and any credential an API client puts in a query parameter, to the pod log.

**Re-check.** Both files read from upstream master: the format string at `logging_handler.go:117-124`
carries `url.RequestURI()`; the callback branch at `oauthproxy.go:609/681`. The reference deploy with
logging on had seen no browser login since the flip, so the log held no such line yet; the source is
the proof.

**Decision.** Accepted: `requestLogging` back to `false` as a confidentiality exception; comment,
chart README row, CHANGELOG, Chart.yaml history, index paragraph and the exception list updated; a
render test holds the default and the explicit `true`. Codex's four replacement texts with "3 flipped
switches / 9 boolean leaves" wording and the test asserting those phrases across four files rejected
as prose tests; the sets themselves are held by `test_values_defaults.py`.

### C10 — a `podLabels` key that is also a selector label

**Finding (both).** `podLabels` was rendered after `gsd.selectorLabels`, so `--set podLabels.app=x`
rewrote the pod's `app` label by YAML last-key-wins. Cursor predicted a silent selector miss and
proposed reordering the includes; Codex measured the render and proposed refusing the key.

**Re-check.** `oc apply --dry-run=server` on CRC rejected the Deployment: template labels outside
its selector. So the failure was loud, not silent, and a reorder would have discarded the operator's
label silently instead.

**Decision.** Accepted on the fact; Cursor's reorder rejected; refused by name with a `fail` that
says which selector label collided (Codex's shape, applied before its report arrived), with a test
that every selector key is refused and a harmless label still renders.

### C4 — a ServiceAccount token can be wide at the proxy and self in the app

**Finding (Codex).** The app's repeated review adds only `system:authenticated` and
`system:authenticated:oauth` to the identity; a ServiceAccount granted through
`system:serviceaccounts:<ns>` passes the proxy's review (which sees the token's real groups) and
resolves to self. Codex proposed `_virtual_groups_for(viewer)` in `gsd/kube.py` with a test.

**Re-check.** `kube.py` `TierResolver._resolve_and_cache` sends `[*groups, *VIRTUAL_AUTH_GROUPS]`;
`docs/api-access.md` documents the user-form grant, which works because the SAR names the user.

**Decision.** Accepted on the fact; routed. This PR is chart-only and the resolver is D2's file, so the
finding, Codex's helper and its test go into `SPEC_D2_per_cluster_authorization.md`'s orchestrator's
notes, and `docs/api-access.md` says to grant a ServiceAccount in the user form until then.

### Also in the second pass

- **C2, C7, V1 accepted** as in the table; Codex's `git show`-based historical test and the
  upgrade-delta test that renders `8cf80bf` rejected (they pin git history into the suite).
- **Incident.** The Codex task set its scratch variable to the session scratchpad and removed it in an
  exit trap, deleting every review artefact and the C3 design; the design was rebuilt from its agent's
  transcript. The brief pattern is corrected in memory: a fresh subdirectory per reviewer, never the
  parent, and irreplaceable outputs copied out first.

### Outcome of the second pass

Nine of ten claims refuted by at least one reviewer; six accepted (one routed), two rejected with the
reason above, one confirmed. Re-validated: `test_chart_pdb.py`, `test_values_defaults.py`,
`test_chart_strategy.py`, the Playwright card test, `helm lint`, the full suite, and a CRC redeploy with
the proxy's `-request-logging=false` and the PDB status read back.
