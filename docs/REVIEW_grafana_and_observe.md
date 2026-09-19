# Review record — the openshift-grafana chart, the GrafanaDashboard CR and the Observe door (#162, #161, #157 — PR #209)

Branch `feat/openshift-grafana-chart`, base `main`. Head reviewed: `dcc3574` (the pass ran while the
branch moved on to `576fc03` and `1825626`; each verdict was re-checked on the head as it stood). Three
reviewers on one brief of ten claims (`review_brief_162.md` in the session scratchpad; restated in the
table): Grok 4.6 (Cursor, ask mode — no shell; from the source), Codex (GPT-5.6, xhigh — rendered every
switch state in a copy, read grafana-operator v5.24.0's controllers, ran the version-bump function
against `main`), OB3 (Opus 5 — drove the rendered wait script through ten scenarios with a fake `oc`
under bash 3.2 and 5.3, measured the tenancy port on CRC with the chart's own ServiceAccount token, diffed
`crds/` against the live CSV, read the ingress operator's canary policy for the router topology, ran the
discovery path through twelve response shapes). OB3 held the third seat because the Fable quota was out;
its pass is owed an OB2 re-review (#210). Every verdict was re-checked on the branch before a decision.
Line numbers are those of `dcc3574` and are not maintained.

**One verdict all three reviewers gave was overturned by the operator's own use of the page** — see G9.

## Claims × reviewers × decision

| # | Claim | Grok | Codex | OB3 | Re-check / decision |
|---|---|---|---|---|---|
| G1 | One-shot install: crds/, ordinary Subscription, the gate | PLAUSIBLE | CONFIRMED (four CRDs `v1beta1`; the conditions the gate waits on are set by v5.24.0) | PLAUSIBLE — mechanics hold (crds/ `spec` == the live CRDs, OLM adopted them); the bare-cluster one-shot was never observed (the CRDs pre-date release 1 by five minutes); **Helm's own `--timeout` (5 m) undercuts the gate (600 s + 120 s)**; the README's "ordinary project rights" is false for the default shape (`admin` holds no `create` on operatorgroups) | **F4, accepted.** `--timeout 15m` in the README's command, a NOTES line computed from `wait.waitSeconds`, the values comment; the "Rights needed" row names the OperatorGroup and the CRDs. `TestReadme` (2) fail on `1825626`, pass now. |
| G2 | The wait script under `set -euo pipefail`; the Role | CONFIRMED (script); **N8** the Role grants unused `subscriptions` | REFUTED — the Role is not least-privilege (Subscriptions never read; `list` on kinds got by name) | REFUTED on "nothing more"; the script CONFIRMED (10 scenarios × 2 bashes: no unbound variable, every FAIL names an `Inspect:`); **F3b** two CSVs matching the displayName (Replacing beside Succeeded, an OLM upgrade's window) print `SucceededReplacing` — no case matches, the gate runs to its deadline | **Accepted, both.** The Role was cut to exactly the script's reads in `1825626`; now one phase per line (`{"\n"}` in the range) and `grep -qx Succeeded/Failed`. `test_the_wait_role_grants_exactly_the_reads_the_script_makes` reads the `oc get`s off the rendered Job; `test_the_wait_script_sees_a_succeeded_csv_beside_a_replaced_one` runs the rendered script with an `oc` shim that prints both phases — fails on `1825626`, passes now. |
| G3 | Thanos at namespace scope: nothing outside the namespace; the tenancy port refuses a foreign namespace | CONFIRMED | REFUTED on the letter — `--include-crds` emits four cluster-scoped CRDs; the 9092/GET/`view` mechanics CONFIRMED | CONFIRMED (measured): `?namespace=default` → `403 … verb=get, resource=pods`; a foreign label matcher → prom-label-proxy `conflicting label matcher`; POST → `403 … verb=create` | Holds; the README already states the CRDs are the first install's cluster-scoped step. **OB3 N5**: `wait.verifyUserWorkloadMonitoring` adds a one-ConfigMap Role in `openshift-monitoring` — the "Objects outside the namespace" row now says so. |
| G4 | No token or certificate in a manifest; `${key}` substitution | CONFIRMED | CONFIRMED (`strings.ReplaceAll` on `${<key>}` verbatim) | CONFIRMED (`controller_shared.go:429/444`, `datasource_controller.go:476`; live `secureJsonFields` both true, `/health` OK) | Holds |
| G5 | NetworkPolicy: the operator's pod label; the router namespace | PLAUSIBLE (live label not re-read) | CONFIRMED (`app: cr.Name` in the operator's deployment reconciler) | **REFUTED — the router rule covers only pod-network routers.** CRC's ingress controller is `HostNetwork`; the Route works there only because a policy never blocks the resident node. The ingress operator's own canary policy admits `policy-group.network.openshift.io/ingress` AND `policy-group.network.openshift.io/host-network` ("depending on topology"). | **F2, accepted.** The second peer in both branches of the template. The test holds the exact peer lists of both branches (proxy port for the routers under the OpenShift login; 3000 for the namespace). Egress stays unrestricted (all three: Grafana needs DNS, Thanos and whatever a consumer adds). |
| G6 | The GrafanaDashboard CR: inside the ConfigMap's switch; bound by uid | CONFIRMED; **N9** no render test | CONFIRMED (three switch states rendered; literal `${DS_PROMETHEUS}` replacement, not a lookup) | CONFIRMED (`resolver.go:73-74`); **F5** the operator refuses an empty `datasourceName` (`resolver.go:69`) and the chart rendered `""` silently; an empty `instanceSelector` with `allowCrossNamespaceImport` matches every Grafana the operator sees; **N1** the template header still said "No CR is shipped here on purpose" | **Accepted, all.** Render test in `1825626`; now both empties `fail` the render (2 tests), the header and the values comment say what renders. |
| G7 | The six KPI panels: exported families, `max by (component)`, `$cluster` where the label exists, thresholds; additions only | CONFIRMED (byte-identity not re-diffed) | CONFIRMED (first 25 panels equal as parsed JSON) | CONFIRMED (measured on the tenancy port: `max by (component)` collapsed a rollout's two pods per component to one series each; 29 → 4 series, 30 → 22) | Holds |
| G8 | Console discovery: `console-public`, the host only, the chart's value wins, quoted, escaped | CONFIRMED | CONFIRMED (no non-admin can write `console-public`) | CONFIRMED; **F6** `https://` → a door to `https:` (rstrip ate the slashes), `https://c/?x=1` a door with two query strings; `_client()` outside the `try` raised on an unresolvable token every cycle | **F6, accepted.** The discovered URL is held to `_door_url`'s rule (https, a host, no `?`/`#` — the characters, since a bare `?` parses as no query); `_client()` inside the `try`. `test_discovery_holds_the_url_to_the_door_rule_and_never_raises` fails on `1825626` (`https://` → `"https:"`), passes now. |
| G9 | The Observe URL's parameters | PLAUSIBLE | CONFIRMED (the plugin reads `project-dropdown-value` and `params.get(v.name)`) | CONFIRMED — "shallow: a second model is most likely to overturn this" | **Overturned by the operator (2026-09-19): jane.smith saw "Project: All Projects" and every graph on Bad Request; only kubeadmin saw the board.** All three reviewers read the parameter names off the source and were right about what they *are*; none asked what a non-admin's graphs SEND. Measured (Playwright, the `developer` user with `view` on the namespace, last project primed to All): the admin-form URL → `query_range … namespace=` absent → prom-label-proxy 400; the plugin's graph panels put `useActiveNamespace()` — the console's project selector — on the tenancy request (`query-browser.tsx`), and the selector is set only from a `/ns/<name>` path segment or the user's last-used project (`detect-context/namespace.ts`). kubeadmin never uses the tenancy proxy AND his stored `console.lastNamespace` was `group-sync-dashboard`. **Fixed in `972b143`:** the door is `/dev-monitoring/ns/<ns>?dashboard=<board>` — the console sets the selector from the path and the plugin redirects to the admin form with it right; measured `namespace=<ns>` on the same user's `query_range`. `docs/DESIGN_grafana_and_observe.md` §2.1 carries the measurement. |
| G10 | CI: the single bump job; both charts linted; chart-releaser attests | PLAUSIBLE | REFUTED — `ci.yml` lints only the app chart; `helm.yaml` attests only the app chart's package | REFUTED — **the required check is red on this head** (`Chart.yaml` 0.35.0 while the chart's files changed; job 105972235918); lint covers one chart; the provenance step attests one chart. Behaviour preservation CONFIRMED (96 added JSON lines, one whitespace line) | **F1, accepted.** `Chart.yaml` 0.36.0 with its history comment; the lint step loops `charts/*/`; the plan step lists exactly the packages this run uploads (`subjects`) and the attestation and the read-back take that list — OB3's precision over `1825626`'s `*.tgz`, which would also have attested a changed-but-unbumped chart's package chart-releaser never uploads. `tests/test_ci_charts.py` (4) runs the lint step with a helm shim and the plan step in a scratch repository with one tagged chart. |

## Volunteered, besides the above

- **Grok N1 / Codex G10** — CI never linted `charts/openshift-grafana`. Accepted (F1 above).
- **Grok N2** — `environments/README.md` said the lab keeps monitoring off. Fixed in `1825626`.
- **Grok N3 / Codex G3 / OB3 G1** — "ordinary project rights". Fixed in `1825626` (the CRDs) and now
  (the OperatorGroup).
- **Grok N4** — `console.url` "refuses the render" had no Helm guard. `gsd.doorUrl` in `1825626`.
- **Grok N5 / OB3 N2** — comments still said "bind by name". Fixed in `1825626`.
- **Grok N6** — a transient discovery `None` removed the Observe door for a poll. Fixed in `1825626`.
- **Grok N7 / Codex G10 / OB3 G10** — provenance attested only the app chart. `1825626`, refined now.
- **OB3 N3** — the second chart made `values.yaml`, `Chart.yaml` and `_helpers.tpl` ambiguous by
  basename in `tests/test_docs_citations.py`, and 25 anchored citations of the application chart's
  files went from verified to silently skipped (892/12 on `main` → 867/37). Accepted: `_resolve(cited,
  near=)` — a document inside a chart cites that chart, any other document's bare chart-file citation
  is the application chart's. 893 passed / 12 skipped again.
- **OB3 N6–N8** (observations, no fix): `editable: false` is not mapped by the operator (harmless);
  `wait.image.tag: latest` floats on `registry.redhat.io`; `config._door_url` accepts a bare trailing
  `?` (the discovered URL's check now refuses it; the chart-side rule can follow in a later PR).

## Rejected

- Nothing. OB3's `subjects` design was preferred over the head's `*.tgz` on the fact it named.

## Validation

`tests/test_chart_openshift_grafana.py` 25, `tests/test_chart_grafana_dashboard.py` +3, `tests/test_ci_charts.py`
4, `tests/test_kpi.py#TestObserveDoor` 6, `tests/test_docs_citations.py` 893 passed / 12 skipped; `helm lint`
both charts clean; full hermetic suite 3679 passed, 13 skipped (the citation resolver restored 25 checks). Deployed to CRC and walked
as `developer` (a tenancy-path reader) and kubeadmin with the last project set to All Projects —
`reports/2026-09-19_grafana-observe-162-161/`.

## Owed

An OB2 (Fable 5.1) re-review of this record's claims when the quota resets — tracked in #210. G9 is
the argument for it: three CONFIRMED verdicts from three models, and the page failed for the first
non-admin who opened it.
