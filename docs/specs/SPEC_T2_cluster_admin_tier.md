# SPEC T2 — the cluster-admin tier: `visibility.clusterAdminSar` gates the Cluster Configurations tab and the KPI page, and grants every host tier (#322)

| | |
|---|---|
| Programme | Named dashboard tiers (#239), continued — the top tier the operator decided on 2026-09-23; it replaces the two-level `clusterConfig{View,Manage}Sar` pair of #230 and supersedes T1's step T3 for that tier |
| Batch | T — tiers |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 0.35.0, chart 0.57.0 |
| Issue | [#322](https://github.com/ephico2real2/group-sync-dashboard/issues/322) |
| Status | in progress |
| Source | OB2's design of 2026-09-25 from the issue's Decision (verbatim, not re-litigated), measured on main `7aa00f1` with the commands and `file#anchor` citations below; there is no separate design-agent output |

## How to read this spec

"The decision" is the issue's ruling, restated only as far as the code needs it. "The code as it
stands" is what main `7aa00f1` does today, cited by symbol (line numbers are given in prose for the
reviewer and rot with the file; the anchors do not). "The model" is the one tier and the four rules it
obeys. "Migration" says who loses access and how a values file moves. "Tests" is a case per
Definition-of-Done item. "Implementation blocks" (§6) is the whole change, applied by
`local-development/apply-spec-blocks.py` and nothing else. A deviation found necessary during
implementation is written back here, under "Orchestrator's notes", with the reason.

## Orchestrator's notes

- The issue's Decision, "Why this check", "The top tier", Design, Out of scope and Definition of Done
  are the operator's (2026-09-23) and this spec implements them as written. Where T1
  (`docs/specs/SPEC_T1_tier_model.md`) says otherwise it is superseded for this tier: T1's D1 (KPIs
  stay auditor-tier) and its two-level `cluster_admin:view` / `cluster_admin:manage` pair are replaced
  by one `clusterAdminSar` question that gates KPI and the whole tab; T1's rule 3 ("no tier implies
  another") gains the one exception the operator ruled: the top tier grants every host-decided tier,
  one way only.
- Decisions this spec makes where the issue is silent, each by the smallest-change rule:
  - **D1 — the wire field is `visibility.cluster_admin` on `/api/whoami`**, a boolean beside `scope`,
    `enabled` and `clusters`, replacing the top-level `clusterconfig: {view, manage}` object. One
    question, one boolean; the page reads it for both tabs. `test_activity.py`'s exact-equality body
    is the ruling's record.
  - **D2 — the refusal sentence is "For cluster administrators only."** (T1's D8, already recorded),
    leading the API `detail`, followed by what the view contains; the card keeps the operator's
    "For administrators only." phrase, as it did for the #230 tier.
  - **D3 — `GET /api/clusterconfigs` keeps `can: {view, manage}`**, both `true` for whoever reaches it:
    one question means one verdict, and the page's contract (`ccWritesOn`) reads the deployment's
    `secrets.writes` switch beside it.
  - **D4 — the hierarchy is decided in `viewer_scope` and `usage_scope`**, after the `self-only` and
    `remote-sar` branches and before the host resolver, so per-cluster policies stay exactly as
    `docs/ACCESS_CONTROL.md` §11 states them. The consulted verdict is uncounted; the decision served
    is counted under the threshold that served it (`admin` / `usage`), so
    `gsd_visibility_decisions_total` keeps meaning "decisions served".
  - **D5 — the built resolver's empty namespace is cluster-scoped**, like `adminSar`'s: the #230 tier's
    "empty means the pod's own namespace" rule and its refuse-when-unknown guard (review of #235,
    Codex C4) go with the namespaced question they protected.
  - **D6 — with the proxy off there is no one to ask about, so KPI is withheld**, exactly as the
    Cluster Configurations tab already was. The CHANGELOG says so.
  - **D7 — the removed values blocks are refused only when set.** A block that sets nothing — nulled
    (`clusterConfigViewSar: null`, or the key with its sub-keys commented out) or `{}` — asks no
    question of its own and passes; a block with any field set fails the render naming
    `visibility.clusterAdminSar`. The refusal tests the value's truth (`if index $vis $old`), not
    the key's presence: see "Grok's review of the spec" below for the measurement.
  - **D8 — the `auth-delegator` grant renders whenever the oauth-proxy is on.** The tier is asked
    whatever `visibility.enabled` says, and KPI is on every install, so the grant can no longer be
    tied to `clusterConfig.secrets.enabled`. With the proxy off `trusted_viewer` is `None` and no
    review is asked, so the grant still disappears there. This ADDS the binding in one state only
    (proxy on, `visibility.enabled`, `apiTokenAccess.enabled` and `clusterConfig.secrets.enabled` all
    off) and removes none.
- The index row for T2, the S4c reservation's move (app 0.36.0, chart 0.58.0, in `docs/specs/README.md` and
  `docs/specs/SPEC_S4c_credential_lifecycle.md`) and the row count in
  `local-development/tests/test_specs_index.py` are made in the commit that adds this document, not by a
  block: the index must name the file the moment it exists (`test_every_spec_file_has_an_index_row`).
- 2026-09-25, implementation: the UI suite's unrestricted `server` fixture (proxy off) can no longer
  reach the KPI page (D6). The fixture gains `oauth_proxy_enabled=True` (with no `X-Forwarded-User`
  header its whoami is unchanged: `authenticated: false`) and the cluster-admin seam; the four KPI
  sites send the `root` header and reload. Recorded here because it is a test-rig change forced by the
  operator's decision, not a symptom fix.
- 2026-09-25, **Grok's review of the spec** (`cursor-grok-4.6-high-fast`), the two REFUTED claims,
  traced and decided by OB1-lite (implementer):
  - **C7 — accepted, fix narrowed.** The spec's premise ("Helm's merge deletes a key given as
    `null`") is false for a key the chart's `values.yaml` no longer carries: Helm's coalesce deletes a
    nulled user key only when the chart defaults hold it. Measured with Helm v4.3.0 on the blocks as
    first written (`hasKey`): `-f` with `clusterConfigViewSar: null`, with `clusterConfigViewSar:`
    (sub-keys commented out), with `clusterConfigViewSar: {}`, and `--set
    visibility.clusterConfigViewSar=null` all FAILED the render with the removal message, so the
    spec's own `render(**{"visibility.<block>": "null"})` assertion could not pass. A block that sets
    nothing asks no question, so refusing it only breaks a values file copied from the old chart with
    the sub-keys commented out. Grok's `and (hasKey …) (not (kindIs "invalid" …))` still refuses `{}`;
    the refusal now tests the value's truth, `{{- if index $vis $old -}}`, which is one condition
    instead of two and passes nil, `{}` and a missing key alike.
  - **C9 — accepted as proposed.** Measured on the blocks as first written: `helm template` with
    `visibility.enabled=false`, `oauthProxy.apiTokenAccess.enabled=false` and
    `clusterConfig.secrets.enabled=false` rendered 0 `system:auth-delegator` bindings, while
    `require_cluster_admin` (KPI) and `_cluster_admin_granted` ask a SubjectAccessReview whatever
    `restrict` says — so in that state KPI would refuse everyone, administrators included, where main
    serves it to every reader. The binding's condition becomes `oauthProxy.enabled` (D8);
    `test_the_sar_grant_disappears_when_nothing_needs_it` pinned the hole and is replaced by a
    triple-off case that fails before and passes after, and a proxy-off case. The chart README row,
    the `userActivity.visibility` comment in `values.yaml` and the grant's comment in `rbac.yaml`
    said the grant followed `visibility.enabled` / `clusterConfig.secrets.enabled`, or that Usage is
    per-person for a cluster-admin with visibility off; each is corrected by a block below.
- 2026-09-25, implementation (OB1-lite): `TestTheHierarchy.rig` in the new test file gains
  `reporting_url` and a `reporting_token_file` (reporting on refuses to start without a usable token). Measured on the blocks as first written: the full hermetic suite failed
  `test_a_cluster_admin_is_wide_on_usage_whatever_the_usage_question_answers` at
  `/api/dashboard/reports` (`'self' == 'all'`) because that route returns a hard-coded `scope: self`
  when no report service is configured (`gsd/api.py#dashboard_reports`, `if not settings.reporting_url`),
  before `usage_scope` is asked. The test was wrong, not the code: with a report service configured the
  route reaches `usage_scope` and the cluster-admin grant.

- **Codex's code review of `18e7c66`** (gpt-6-astra, high; run by the orchestrator; OB1-lite implemented):
  - C1–C8 CONFIRMED with measurements: the routes, the negative control, one SubjectAccessReview for the
    hierarchy, fail-closed on every outcome, the 60-second cache and the Helm refusals.
  - **F1 (P3) accepted.** The Cluster Configurations page note still named the removed
    `clusterconfig:view` / `clusterconfig:manage` tiers. It now reads "Only cluster administrators see this
    page. Changing a cluster also needs `clusterConfig.secrets.writes.enabled`", pinned by
    `test_cluster_configuration_help_describes_the_single_tier`.
  - Applied after the blocks, so the tree differs from §6 by that sentence and that test.

## The decision (issue #322, operator, 2026-09-23)

One new tier, `visibility.clusterAdminSar`, asking `update clusterrolebindings.rbac.authorization.k8s.io`
(cluster-scoped) on the host cluster, gating:

| surface | gated on today | gated on after |
|---|---|---|
| Cluster Configurations tab: view (`GET /api/clusterconfigs`, the tab's existence) | `clusterConfigViewSar`: `get secrets` in the release namespace | `clusterAdminSar` |
| Cluster Configurations tab: manage (Create / Rotate / Delete / Test) | `clusterConfigManageSar`: `create secrets` there | `clusterAdminSar` (`clusterConfig.secrets.writes.enabled` still applies) |
| KPI page (`GET /api/kpi`) | `require_admin_tier`: the wide tier, `list clusterrolebindings` | `clusterAdminSar` |
| Rejoin (#316), when built | not built | `clusterAdminSar` |

A reader who passes it is granted every tier the host decides — the wide view on the host and on
`inherit` clusters, and Usage, including when `visibility.enabled` is off. One way only. Per-cluster
policies still apply (`remote-sar` asks its own API, `self-only` stays self, `hidden` stays hidden).
`clusterConfigViewSar` and `clusterConfigManageSar` are removed and refused by name. The tier fails
closed whatever `visibility.enabled` says. Out of scope: `/operator-configs` and the other wide-tier
views stay on `adminSar`; Rejoin itself.

## The code as it stands (main `7aa00f1`, measured 2026-09-25)

- **The wide gate.** `gsd/api.py#require_admin_tier` (line 824) reads `viewer_scope` and refuses
  below `all` with *"For administrators only. …"*. Its callers: `bindings/findings` (line 2148),
  `operator-configs` (2473), `kyverno` (2510), **`kpi` (2805)** and `report_ticket` (3045). Only KPI
  moves.
- **`viewer_scope`** (`gsd/api.py#viewer_scope`, line 603): `not restrict` → `all` (622); no host →
  `self` (634); `self-only` → `self` (646); `remote-sar` → that cluster's resolver (650–660); else the
  host resolver through `_decide` (661–662). `restrict = view_restrictions_enabled and oauth_proxy_enabled`
  (562).
- **`usage_scope`** (line 664): `userActivity.visibility == "all"` → `all` (686); `not restrict` →
  `self` (696); else the Usage resolver (698–713).
- **The #230 tier.** Two resolvers built at lines 453–477, each `TierResolver` on the host with
  `namespace=settings.visibility_clusterconfig_*_sar_namespace or cc_namespace or ""` and threshold
  labels `clusterconfig_view` / `clusterconfig_manage`, built whatever `visibility.enabled` says.
  `_clusterconfig_tier` (743) refuses when the namespace is unknown (769–776), fails closed, counts;
  `require_clusterconfig_view` (790) and `require_clusterconfig_manage` (809) raise 403 with
  *"For cluster-configuration administrators only. …"* and *"Changing cluster configuration is
  reserved to cluster-configuration administrators. …"*. Callers: `GET /api/clusterconfigs` (1138,
  and `may_manage` at 1143), `_writes_gate` (1210). Seams: `app.state.clusterconfig_view_resolver` /
  `clusterconfig_manage_resolver` (3305–3306); injection kwargs on `build_app` (320–321).
- **`/api/whoami`** (line 2826) builds `visibility = {scope, enabled, clusters}` (2925–2929) and
  `clusterconfig = {view, manage}` (2940–2942), both only when authenticated.
- **Settings.** `gsd/config.py#Settings` carries `visibility_clusterconfig_view_sar_*` and
  `visibility_clusterconfig_manage_sar_*` (lines 798–807), parsed by
  `gsd/config.py#_clusterconfig_view_sar_setting` and `#_clusterconfig_manage_sar_setting`
  (1258–1270) through `gsd/config.py#_sar_setting` (whole-or-default, 1200); wired in
  `load_settings` (1650–1651, 1749–1758). `visibility_usage_admin_sar_*` defaults to
  `update clusterrolebindings` (769–773) — the question this tier takes as its own.
- **Metrics.** `gsd/metrics.py#TIER_THRESHOLDS` = `("admin", "usage", "clusterconfig_view",
  "clusterconfig_manage")` (line 69), pre-seeded per outcome and per tier (724–731).
  `charts/group-sync-dashboard/dashboards/group-sync-dashboard.json` and
  `templates/monitoring.yaml` select on `outcome` / `sum by (threshold, …)`, never on a threshold
  value (grep: no `clusterconfig_` in either).
- **The chart.** `values.yaml#clusterConfigViewSar` / `#clusterConfigManageSar` (lines 2324–2333);
  `templates/_helpers.tpl#gsd.clusterConfigSarField` (413) renders eight ConfigMap keys
  `visibilityClusterConfig{View,Manage}Sar{ApiGroup,Resource,Verb,Namespace}` (`configmap.yaml`
  128–135); the `auth-delegator` binding renders with `visibility.enabled` off when
  `clusterConfig.secrets.enabled` is on (`rbac.yaml`, line 153). No template reads an unknown
  `visibility.*` key, so a stale block renders clean — the "silently vanishes" class
  `_helpers.tpl`'s `reporting.namespaceSelector.label` guard (797–802) already refuses.
- **The page.** `gsd/static/index.html#ccMayView` / `#ccMayManage` (6127–6134) read
  `whoami.clusterconfig`; the tab strip renders `kpi` unconditionally and `clusters` behind
  `ccMayView()` (1171, 1182); the KPI branch of `render()` (7155–7168), its fetch guard (7709) and its
  re-decision (7793–7795) key on `narrowedOnHost()`, the wide tier.
- **Who passes what** (CRC, `oc auth can-i` with the complete Group list, SPEC_T1 "The problem,
  measured", 2026-09-20): `kubeadmin` passes every question; `dana.lee` (cluster-reader) passes
  `list clusterrolebindings` and fails `update`; `john.doe` (`admin` cluster-wide) and `bob.wilson`
  (`edit` cluster-wide) fail both cluster-scoped questions and pass `get`/`create secrets`; the mock
  cluster's oracle (`local-development/mock-app/tests/test_sar_personas.py#ORACLE`) answers the same
  for `kubeadmin`, `dana.lee` and `developer` over `WIDE` (`list`) and `USAGE` (`update`).
- **A built resolver with no token fails in 0.0 ms** (measured: `TierResolver(ClusterConfig("c1",
  "https://x", token_env="T"), …).resolve("alice")` → `'self'` in 0.0 ms, three URLs), so consulting
  it first on every restricted request costs the test suites nothing.

## The model

One tier, one `gsd/kube.py#TierResolver` on the host, its own cache, threshold label `cluster_admin`,
seam `app.state.cluster_admin_resolver`, injection kwarg `cluster_admin_resolver`. Four rules:

1. **Its own question, its own setting.** `visibility_cluster_admin_sar_{api_group,resource,
   subresource,verb,namespace}`, default `rbac.authorization.k8s.io` / `clusterrolebindings` / `""` /
   `update` / `""` (cluster-scoped), parsed by `gsd/config.py#_cluster_admin_sar_setting` through the
   existing whole-or-default `_sar_setting`, from ConfigMap keys `visibilityClusterAdminSar{ApiGroup,
   Resource,Verb,Namespace}`; chart value `visibility.clusterAdminSar.{apiGroup,resource,verb,namespace}`
   with the same exact-lowercase guards as `adminSar`.
2. **Fail closed, whatever `visibility.enabled` says.** Built when a host exists and nothing was
   injected — not behind `view_restrictions_enabled`. No identity, no resolver, an error, a junk
   answer → refused, never cached (`TierResolver`'s own contract).
3. **It gates two surfaces whole.** `gsd/api.py#require_cluster_admin` (`request, what`) raises 403
   `"For cluster administrators only. {what}"` for `GET /api/kpi`, `GET /api/clusterconfigs` and the
   four write routes (through `_writes_gate`, which keeps its identity-and-`restrict` refusal first).
   `/api/whoami` carries `visibility.cluster_admin` so both tabs are absent for a reader who fails it.
4. **The top tier grants every host-decided tier, one way.** `gsd/api.py#_cluster_admin_granted`
   (`viewer`) is the uncounted cached verdict; `viewer_scope` returns `all` (counted as `admin`) when it holds,
   after the `self-only` and `remote-sar` branches; `usage_scope` returns `all` (counted as `usage`)
   when it holds, after the `userActivity.visibility: all` override and before the `not restrict`
   short-circuit — so a cluster-admin keeps Usage with restrictions off. Nothing reads the wide or
   Usage verdict to decide this tier.

## Migration

**Who loses access, by persona** (the measured table above):

| persona | KPI page | Cluster Configurations tab | wide views | Usage |
|---|---|---|---|---|
| `kubeadmin` (cluster-admin) | keeps | keeps (view and manage) | keeps | keeps |
| `dana.lee` (cluster-reader, the auditor) | **loses** | none before, none after | keeps | none before, none after |
| `john.doe`, `bob.wilson` (`admin`/`edit` in the release namespace, cluster-wide or by RoleBinding) | none before, none after | **lose** (view and manage) | as before (`bob.wilson` keeps; `john.doe` had none) | as before |
| the plain reader, the ServiceAccount | none before, none after | none before, none after | none | none |

**Proxy off** (`oauthProxy.enabled: false`): there is no identity to ask about, so KPI is withheld
where it was served wide before (D6); the Cluster Configurations tab already was.

**Values files.** A file that sets `visibility.clusterConfigViewSar` or `visibility.clusterConfigManageSar`
fails `helm template` with: *`visibility.<key> was removed in chart 0.57.0 (#322). One question,
visibility.clusterAdminSar (default: update clusterrolebindings.rbac.authorization.k8s.io, cluster-scoped),
now gates the whole Cluster Configurations tab and the KPI page. Delete this block; to ask a different
question, set visibility.clusterAdminSar.{apiGroup,resource,verb,namespace}.`* A file that set neither
changes nothing in its render but the four ConfigMap keys.

**Metrics.** `threshold="cluster_admin"` replaces `clusterconfig_view` and `clusterconfig_manage` on
`gsd_visibility_tier_checks_total` and `gsd_visibility_decisions_total`, pre-seeded; the shipped alert
and panels are unaffected (they never select a threshold value).

## Tests (a case per Definition-of-Done item)

`local-development/tests/test_cluster_admin_tier.py` (new), through the published seams with the
persona stubs `root` (passes everything), `auditor` (passes the wide stub, fails cluster-admin — the
negative control), `nsadmin` (passes nothing cluster-scoped), `alice`:

- **The four surfaces, each with the negative control:** `auditor` gets 403 on `GET /api/kpi`, on
  `GET /api/clusterconfigs` and on the four write routes, `visibility.cluster_admin: false` on whoami,
  while `/api/clusters/c1/groups` is still `scope: all` for them; `root` gets 200 everywhere and
  `cluster_admin: true`; the refusal leads with *"For cluster administrators only."* and names no
  cluster, Secret, namespace, role or value. The mutant: reverting either route to `require_admin_tier`
  admits `auditor`.
- **The hierarchy:** with the wide and Usage stubs denying everyone, `root` (passing cluster-admin) is
  `scope: all` on `/groups` for the host and for an `inherit` cluster, `all` on
  `/api/dashboard/activity`, and `all` on whoami's headline; a `remote-sar` cluster whose own stub
  denies `root` is `self` for them and its stub was asked; a `self-only` cluster is `self`; the wide
  and Usage stubs were not consulted for `root`. One way: `auditor`, wide by the wide stub, is refused
  KPI.
- **Fail closed with `visibility.enabled: false`:** the tier is still asked — `root` is admitted to
  KPI and the tab and is `all` on Usage; `auditor` and `alice` are refused both surfaces and stay
  `self` on Usage; with the proxy off everyone is refused.
- **Fail closed:** no resolver, a raising resolver, a junk answer, no identity → 403 on both surfaces.
- **The resolver:** `build_app` constructs it with the default question, apart from the wide switch,
  with a cache distinct from the Usage resolver's; `Settings` defaults equal the oracle's `USAGE`
  question; the ConfigMap keys parse whole-or-default.
- **Metrics:** `threshold="cluster_admin"` is pre-seeded and the two old labels are gone
  (`test_metrics.py`).
- **The chart** (`test_chart_strategy.py`): the default render carries the four keys; a nonsensical
  shape is refused naming the field; each removed block, set, is refused naming `clusterAdminSar`;
  a nulled block keeps the default; the `auth-delegator` binding renders whenever the proxy is on,
  with `visibility.enabled`, `apiTokenAccess` and cluster Secrets all off (D8), and disappears only with
  the proxy off.
- **The page** (`test_ui.py`): the seams, and the KPI cases as `root`; the Cluster Configurations
  cases read `visibility.cluster_admin`.

## Decomposition

One PR: the spec first (draft, reviewed), then the blocks below applied in one commit, versions
app 0.35.0 / chart 0.57.0. Verification the implementer runs: the hermetic suite, the browser suite,
`helm lint`, and the RBAC rule diff against `origin/main` (the dashboard ServiceAccount's REMOVED
rules must be 0 — this change removes none, and adds the `auth-delegator` binding in the one state
it was missing from, D8). The CRC walk with screenshots
(Definition of Done, last item) is the orchestrator's, who holds the lab.

## 6. Implementation blocks

### `local-development/gsd/config.py` — the settings

<!-- block: local-development/gsd/config.py | edit -->

```python
    # THE CLUSTER-CONFIGURATION TIER — two levels of its own (#230; the operator's ruling of
    # 2026-09-20, "a new tier boss — look at how argocd does it"). Argo CD's RBAC carries a
    # first-class `clusters` resource with `get` and `create/update/delete` actions, granted to
    # roles bound to SSO groups, default-deny. We carry no policy file — every tier here is a
    # SubjectAccessReview against the host cluster, so OpenShift groups and RoleBindings already
    # ARE that mapping — so the tier is a named pair of SAR questions about the very objects this
    # surface exposes, the cluster Secrets themselves:
    #
    #   clusterconfig:view    (Argo `clusters, get`)     — `get secrets` in the dashboard's namespace
    #   clusterconfig:manage  (Argo `clusters, create…`) — `create secrets` in that namespace
    #
    # It reads as what it is: you may SEE cluster credentials if you may read the Secrets that hold
    # them, and CHANGE them if you may create those Secrets. Measured on CRC 2026-09-20: the
    # `cluster-reader` ClusterRole — the deliberate auditor persona, which passes the WIDE tier by
    # design — has ZERO of its 172 rules covering core/`secrets`, and `oc auth can-i {get,list,
    # create,update,delete} secrets` answers `no` for a non-admin; so the auditor fails both levels
    # by construction and a cluster-admin passes both. No borrowed Usage-tab question and no new
    # vocabulary for an operator to learn.
    #
    # Each level is asked SEPARATELY and has its own resolver and cache: `manage` does not imply
    # `view` in code, so a site may grant them apart. An empty namespace here means THE POD'S OWN
    # (the namespace the Secrets live in), not a cluster-scoped check — the opposite of the wide
    # tier's empty, because these questions are namespaced by nature.
    visibility_clusterconfig_view_sar_api_group: str = ""
    visibility_clusterconfig_view_sar_resource: str = "secrets"
    visibility_clusterconfig_view_sar_subresource: str = ""
    visibility_clusterconfig_view_sar_verb: str = "get"
    visibility_clusterconfig_view_sar_namespace: str = ""
    visibility_clusterconfig_manage_sar_api_group: str = ""
    visibility_clusterconfig_manage_sar_resource: str = "secrets"
    visibility_clusterconfig_manage_sar_subresource: str = ""
    visibility_clusterconfig_manage_sar_verb: str = "create"
    visibility_clusterconfig_manage_sar_namespace: str = ""
```

```python
    # THE CLUSTER-ADMIN TIER (#322; the operator's decision of 2026-09-23) — ONE question, asked on
    # the host cluster: `update clusterrolebindings.rbac.authorization.k8s.io`, cluster-scoped. It
    # gates the surfaces that are for cluster administrators only — the Cluster Configurations tab
    # (view and manage alike) and the KPI page — and a reader who passes it is granted every tier the
    # host decides: the wide view on the host and on `inherit` clusters, and Usage, whatever adminSar
    # and usageAdminSar answer for them (gsd/api.py, viewer_scope and usage_scope). One way only:
    # passing adminSar or usageAdminSar never implies this tier.
    #
    # WHY THIS CHECK, measured on CRC (docs/SPEC_usage_admin_tier.md and the adminSar comment above):
    # no read check separates cluster-admin from cluster-reader, so `list clusterrolebindings` (the
    # wide tier) admitted the auditor persona to the KPI page; `create secrets` in the release
    # namespace (the two-level tier this replaces, #230) kept the auditor out but admitted anyone
    # holding `admin` or `edit` on that one namespace, who is not a cluster administrator.
    # `update clusterrolebindings` — the question the Usage tier already asks — a cluster-reader
    # fails and a cluster-admin passes. Its own setting, not usageAdminSar's, so an operator can move
    # one without moving the other.
    #
    # Asked WHATEVER visibility.enabled says (the fail-closed rule the #230 tier already followed):
    # turning the cluster-data restrictions off must not hand KPI or the fleet's wiring to every
    # proxy-admitted reader. An empty namespace means a cluster-scoped check, like adminSar's.
    visibility_cluster_admin_sar_api_group: str = "rbac.authorization.k8s.io"
    visibility_cluster_admin_sar_resource: str = "clusterrolebindings"
    visibility_cluster_admin_sar_subresource: str = ""
    visibility_cluster_admin_sar_verb: str = "update"
    visibility_cluster_admin_sar_namespace: str = ""
```

<!-- block: local-development/gsd/config.py | edit -->

```python
_CLUSTERCONFIG_VIEW_SAR_DEFAULTS = {
    "ApiGroup": "",
    "Resource": "secrets",
    "Verb": "get",
    "Namespace": "",
}

_CLUSTERCONFIG_MANAGE_SAR_DEFAULTS = dict(_CLUSTERCONFIG_VIEW_SAR_DEFAULTS, Verb="create")


def _clusterconfig_view_sar_setting(raw: dict) -> tuple[str, str, str, str, str]:
    """`clusterconfig:view` (chart: visibility.clusterConfigViewSar) — Argo's `clusters, get`.
    See Settings for the measurement behind the default."""
    return _sar_setting(raw, "visibilityClusterConfigViewSar", _CLUSTERCONFIG_VIEW_SAR_DEFAULTS,
                        "get secrets")


def _clusterconfig_manage_sar_setting(raw: dict) -> tuple[str, str, str, str, str]:
    """`clusterconfig:manage` (chart: visibility.clusterConfigManageSar) — Argo's `clusters,
    create/update/delete`. Its own setting, never derived from the view one: a site may grant the
    two apart, and one parser serving both would let a custom view question silently move manage."""
    return _sar_setting(raw, "visibilityClusterConfigManageSar", _CLUSTERCONFIG_MANAGE_SAR_DEFAULTS,
                        "create secrets")
```

```python
_CLUSTER_ADMIN_SAR_DEFAULTS = {
    "ApiGroup": "rbac.authorization.k8s.io",
    "Resource": "clusterrolebindings",
    "Verb": "update",
    "Namespace": "",
}


def _cluster_admin_sar_setting(raw: dict) -> tuple[str, str, str, str, str]:
    """The cluster-admin tier (chart: visibility.clusterAdminSar, #322). The same default question as
    the Usage tier's, deliberately its own setting and its own parse: an operator moves one without
    moving the other. Settings carries the measurement behind the default."""
    return _sar_setting(raw, "visibilityClusterAdminSar", _CLUSTER_ADMIN_SAR_DEFAULTS,
                        "update clusterrolebindings.rbac.authorization.k8s.io")
```

<!-- block: local-development/gsd/config.py | edit -->

```python
    clusterconfig_view_sar = _clusterconfig_view_sar_setting(raw)
    clusterconfig_manage_sar = _clusterconfig_manage_sar_setting(raw)
```

```python
    cluster_admin_sar = _cluster_admin_sar_setting(raw)
```

<!-- block: local-development/gsd/config.py | edit -->

```python
        visibility_clusterconfig_view_sar_api_group=clusterconfig_view_sar[0],
        visibility_clusterconfig_view_sar_resource=clusterconfig_view_sar[1],
        visibility_clusterconfig_view_sar_subresource=clusterconfig_view_sar[2],
        visibility_clusterconfig_view_sar_verb=clusterconfig_view_sar[3],
        visibility_clusterconfig_view_sar_namespace=clusterconfig_view_sar[4],
        visibility_clusterconfig_manage_sar_api_group=clusterconfig_manage_sar[0],
        visibility_clusterconfig_manage_sar_resource=clusterconfig_manage_sar[1],
        visibility_clusterconfig_manage_sar_subresource=clusterconfig_manage_sar[2],
        visibility_clusterconfig_manage_sar_verb=clusterconfig_manage_sar[3],
        visibility_clusterconfig_manage_sar_namespace=clusterconfig_manage_sar[4],
```

```python
        visibility_cluster_admin_sar_api_group=cluster_admin_sar[0],
        visibility_cluster_admin_sar_resource=cluster_admin_sar[1],
        visibility_cluster_admin_sar_subresource=cluster_admin_sar[2],
        visibility_cluster_admin_sar_verb=cluster_admin_sar[3],
        visibility_cluster_admin_sar_namespace=cluster_admin_sar[4],
```

### `local-development/gsd/metrics.py` — the threshold label

<!-- block: local-development/gsd/metrics.py | edit -->

```python
# "clusterconfig_view" / "clusterconfig_manage": the two levels of the cluster-configuration
# tier (#230), each counted apart so a refusal at one is never read as the other breaking.
TIER_THRESHOLDS = ("admin", "usage", "clusterconfig_view", "clusterconfig_manage")
```

```python
# "cluster_admin": the cluster-admin tier (#322) — one question, `update clusterrolebindings` on the
# host — counted apart so a refusal there is never read as the wide or Usage tier breaking.
TIER_THRESHOLDS = ("admin", "usage", "cluster_admin")
```

### `local-development/gsd/api.py` — the resolver, the gate, the hierarchy

<!-- block: local-development/gsd/api.py | edit -->

```python
    tier_resolver: Callable[[str], str] | None = None,
    usage_tier_resolver: Callable[[str], str] | None = None,
    clusterconfig_view_resolver: Callable[[str], str] | None = None,
    clusterconfig_manage_resolver: Callable[[str], str] | None = None,
) -> FastAPI:
```

```python
    tier_resolver: Callable[[str], str] | None = None,
    usage_tier_resolver: Callable[[str], str] | None = None,
    cluster_admin_resolver: Callable[[str], str] | None = None,
) -> FastAPI:
```

<!-- block: local-development/gsd/api.py | edit -->

```python
    because it asks a different question about the same person and a decided usage tier must
    never answer for the wide tier. Same fail-closed contract.
    """
```

```python
    because it asks a different question about the same person and a decided usage tier must
    never answer for the wide tier. Same fail-closed contract.

    `cluster_admin_resolver` is the THIRD decider, the top tier (#322): one question on the host,
    `update clusterrolebindings` by default, gating the Cluster Configurations tab and the KPI page
    and granting the wide view and Usage to whoever passes it. Asked whatever `visibility.enabled`
    says. Same fail-closed contract.
    """
```

<!-- block: local-development/gsd/api.py | edit -->

```python
    # THE CLUSTER-CONFIGURATION TIER, two levels, each its own instance (#230; the operator's
    # ruling of 2026-09-20 — Argo CD's `clusters` resource with its get / create-update-delete
    # actions, asked natively as SubjectAccessReviews about the Secrets this surface exposes).
    # Two resolvers and not one, with separate caches and separate threshold labels, for the
    # reason SPEC_usage_admin_tier states about the wide tier: one verdict must never answer
    # another question, and `manage` must not imply `view` by construction.
    #
    # An empty namespace setting means THE POD'S OWN — where the cluster Secrets live — because
    # these questions are namespaced by nature; the wide tier's empty means cluster-scoped.
    #
    # INDEPENDENT OF THE WIDE-VIEW SWITCH, deliberately (review of #235, Grok C2). Building these
    # only when `visibility.enabled` is on — and widening when it is off, as the wide views do —
    # would mean that turning cluster-DATA restrictions off hands every proxy-admitted reader, the
    # auditor included, the fleet's wiring. The operator's ruling is not conditional. Usage already
    # made this call (usage_scope stays self when restrictions are off); this surface goes one step
    # further and still ASKS, so a cluster-admin keeps the tab either way.
    #
    # THE CONSEQUENCE, stated where it bites: with restrictions off a site may not have granted the
    # auth-delegator role, so the SubjectAccessReview fails and the surface refuses everyone until
    # that grant exists. That is the fail-closed direction for a view naming cluster credentials,
    # and the chart's README says so beside the two values.
    # The namespace the two questions are asked IN. Unknown (no ServiceAccount mount, no
    # GSD_NAMESPACE) must not silently become a CLUSTER-SCOPED `get secrets` — a different and far
    # broader question than the one the operator configured (review of #235, Codex C4). None here
    # means "cannot ask", and the gate refuses rather than asking the wrong thing.
    cc_namespace = own_namespace() or None
    clusterconfig_view_tier: TierResolver | None = None
    clusterconfig_manage_tier: TierResolver | None = None
    if clusterconfig_view_resolver is None and local_cluster is not None:
        clusterconfig_view_tier = TierResolver(
            local_cluster,
            verb=settings.visibility_clusterconfig_view_sar_verb,
            resource=settings.visibility_clusterconfig_view_sar_resource,
            api_group=settings.visibility_clusterconfig_view_sar_api_group,
            namespace=settings.visibility_clusterconfig_view_sar_namespace or cc_namespace or "",
            subresource=settings.visibility_clusterconfig_view_sar_subresource,
            ttl_seconds=float(settings.visibility_tier_ttl_seconds),
            observe=functools.partial(signals.note_tier_check, "clusterconfig_view"),
        )
    if clusterconfig_manage_resolver is None and local_cluster is not None:
        clusterconfig_manage_tier = TierResolver(
            local_cluster,
            verb=settings.visibility_clusterconfig_manage_sar_verb,
            resource=settings.visibility_clusterconfig_manage_sar_resource,
            api_group=settings.visibility_clusterconfig_manage_sar_api_group,
            namespace=settings.visibility_clusterconfig_manage_sar_namespace or cc_namespace or "",
            subresource=settings.visibility_clusterconfig_manage_sar_subresource,
            ttl_seconds=float(settings.visibility_tier_ttl_seconds),
            observe=functools.partial(signals.note_tier_check, "clusterconfig_manage"),
        )
```

```python
    # THE CLUSTER-ADMIN TIER (#322; the operator's decision of 2026-09-23): one instance, one
    # question on the host — `update clusterrolebindings` by default, the check the Usage tier
    # already asks, which a cluster-reader fails and a cluster-admin passes — its own cache and its
    # own threshold label. It gates the Cluster Configurations tab (view and manage alike) and the
    # KPI page, and a pass is every host-decided tier: viewer_scope and usage_scope consult it
    # first. Its own setting, never usageAdminSar's, so an operator can move one without the other.
    #
    # INDEPENDENT OF THE WIDE-VIEW SWITCH, deliberately (review of #235, Grok C2, kept from the
    # two-level tier this replaces). Building it only when `visibility.enabled` is on — and widening
    # when it is off, as the wide views do — would mean that turning cluster-DATA restrictions off
    # hands every proxy-admitted reader, the auditor included, the fleet's wiring and the KPI page.
    # The operator's ruling is not conditional. For KPI this is a change: with restrictions off,
    # require_admin_tier admitted everyone; this still asks.
    #
    # THE CONSEQUENCE, stated where it bites: the review needs the auth-delegator role, which the
    # chart binds whenever the proxy is on (#322, Grok's review of SPEC_T2, C9); a deployment built
    # without it fails the review and both surfaces refuse everyone until that grant exists. That is
    # the fail-closed direction for a view naming cluster credentials, and the chart's README says
    # so beside the value. An empty namespace is a cluster-scoped
    # question, like adminSar's.
    cluster_admin_tier: TierResolver | None = None
    if cluster_admin_resolver is None and local_cluster is not None:
        cluster_admin_tier = TierResolver(
            local_cluster,
            verb=settings.visibility_cluster_admin_sar_verb,
            resource=settings.visibility_cluster_admin_sar_resource,
            api_group=settings.visibility_cluster_admin_sar_api_group,
            namespace=settings.visibility_cluster_admin_sar_namespace,
            subresource=settings.visibility_cluster_admin_sar_subresource,
            ttl_seconds=float(settings.visibility_tier_ttl_seconds),
            observe=functools.partial(signals.note_tier_check, "cluster_admin"),
        )
```

<!-- block: local-development/gsd/api.py | edit -->

```python
        state_resolver = getattr(app.state, "tier_resolver", None)
        return _decide(viewer, state_resolver, tier_resolver)

    def usage_scope(request: Request) -> tuple[str | None, str]:
```

```python
        # THE TOP TIER GRANTS THE WIDE VIEW (#322): a reader who passes clusterAdminSar is wide on
        # the host and on every cluster the host decides, whatever adminSar answers for them. Only
        # here — a `self-only` cluster stayed self above and a `remote-sar` cluster asked its own
        # API — and one way only: the wide question never implies this one. Counted as the wide
        # decision it is; the cluster-admin resolver's own cache answers, so no second review.
        if _cluster_admin_granted(viewer):
            signals.note_decision("admin", TIER_ALL)
            return viewer, TIER_ALL
        state_resolver = getattr(app.state, "tier_resolver", None)
        return _decide(viewer, state_resolver, tier_resolver)

    def usage_scope(request: Request) -> tuple[str | None, str]:
```

<!-- block: local-development/gsd/api.py | edit -->

```python
          1. userActivity.visibility == "all" -> every admitted reader sees all rows. The
             existing blunt escape hatch, kept unchanged.
          2. otherwise the USAGE resolver decides: its exact "all" widens; everything else — no
             resolver, an error, a junk string, no identity — is the reader's own rows.
```

```python
          1. userActivity.visibility == "all" -> every admitted reader sees all rows. The
             existing blunt escape hatch, kept unchanged.
          2. the cluster-admin tier (#322): a reader who passes it sees all rows, whatever the
             Usage question answers and whatever visibility.enabled says.
          3. otherwise the USAGE resolver decides: its exact "all" widens; everything else — no
             resolver, an error, a junk string, no identity — is the reader's own rows.
```

<!-- block: local-development/gsd/api.py | edit -->

```python
            signals.note_decision("usage", TIER_ALL)
            return viewer, TIER_ALL
        # Restrictions off (or proxy off) runs no tier machinery — but Usage is NOT the wide
```

```python
            signals.note_decision("usage", TIER_ALL)
            return viewer, TIER_ALL
        # Precedence 2 (#322): the top tier. A reader who passes clusterAdminSar sees every row,
        # whatever usageAdminSar answers and whatever visibility.enabled says — that tier is asked
        # in both states, so a cluster-admin keeps Usage when cluster-data restrictions are off.
        # One way only: the Usage question never implies this one.
        if _cluster_admin_granted(viewer):
            signals.note_decision("usage", TIER_ALL)
            return viewer, TIER_ALL
        # Restrictions off (or proxy off) runs no tier machinery — but Usage is NOT the wide
```

<!-- block: local-development/gsd/api.py | edit -->

```python
    def _clusterconfig_tier(request: Request, level: str) -> str:
        """One level of the cluster-configuration tier, resolved and counted. Returns TIER_ALL or
        TIER_SELF; never raises. FAIL CLOSED, which here means TIER_SELF — Argo's
        `policy.default: deny` in our vocabulary: no identity, no resolver, or an API-server blip
        all refuse. A blip must not widen a surface that names cluster credentials.

        NO `restrict` SHORT-CIRCUIT (review of #235, Grok C2): the wide views widen when
        `visibility.enabled` is off, and copying that here would re-admit the very persona this
        tier exists to exclude. Without the proxy there is no trustworthy identity either, and
        `trusted_viewer` returns None — which refuses, for the same reason.

        AND NO COMPOSITION WITH ANOTHER TIER (the operator's ruling of 2026-09-20, which reversed an
        earlier ordering): each level asks ITS OWN question and nothing else. RBAC is additive, so
        holding the auditor role AND a namespace-admin grant is not a contradiction to resolve; the
        SAR asks the action's own question, so whoever passes it can already read or create that
        Secret with `oc` — refusing them here protects nothing, and because the question IS the
        action, the ServiceAccount that performs the write is not a confused deputy. The auditor is
        excluded by the plain question, measured: the pure auditor persona answers `no` to both."""
        injected = (clusterconfig_view_resolver if level == "view" else clusterconfig_manage_resolver)
        built = (clusterconfig_view_tier if level == "view" else clusterconfig_manage_tier)
        state = getattr(app.state, f"clusterconfig_{level}_resolver", None)
        label = f"clusterconfig_{level}"
        viewer = trusted_viewer(request)
        resolver = state if state is not None else (built if built is not None else injected)
        # A question with no namespace is not this tier's question (Codex C4): refuse rather than
        # widen it to the cluster. A substituted resolver (the test seam) carries its own scope.
        if state is None and not (settings.visibility_clusterconfig_view_sar_namespace
                                  or settings.visibility_clusterconfig_manage_sar_namespace
                                  or cc_namespace):
            log.warning("cluster-configuration tier: this pod's namespace is unknown and no "
                        "visibility.clusterConfig*Sar.namespace is set, so the check cannot be "
                        "asked in a namespace; refusing %s", level)
            signals.note_decision(label, TIER_SELF)
            return TIER_SELF
        if not viewer or resolver is None:
            signals.note_decision(label, TIER_SELF)
            return TIER_SELF
        try:
            tier = resolver.resolve(viewer) if hasattr(resolver, "resolve") else resolver(viewer)
        except Exception:  # noqa: BLE001
            log.exception("cluster-configuration %s tier resolution failed for %r; refusing", level, viewer)
            signals.note_decision(label, TIER_SELF)
            return TIER_SELF
        scope = TIER_ALL if tier == TIER_ALL else TIER_SELF
        signals.note_decision(label, scope)
        return scope

    def require_clusterconfig_view(request: Request) -> str:
        """`clusterconfig:view` — Argo's `clusters, get`, asked as `get secrets` in this pod's
        namespace (Settings carries the measurement). Gates the read route, and in #230 S2 the
        tab's very existence: a reader who fails it is not shown that the surface is there.

        NOT the wide tier, deliberately. `require_admin_tier` admits cluster-reader — the auditor
        persona — by design (see usage_scope), and this surface says which clusters this instance
        reads, from which Secret, under which credential kind and trust mode. The operator's
        ruling of 2026-09-20: the auditor may neither view nor change it."""
        if _clusterconfig_tier(request, "view") != TIER_ALL:
            signals.note_admin_refusal()
            raise HTTPException(
                status_code=403,
                detail="For cluster-configuration administrators only. This view reports how this "
                       "instance is wired to its clusters — which Secret configures each one, the "
                       "kind of credential it holds and how its certificate is trusted.",
            )
        return TIER_ALL

    def require_clusterconfig_manage(request: Request) -> str:
        """`clusterconfig:manage` — Argo's `clusters, create/update/delete`, asked as `create
        secrets` in this pod's namespace. Gates the write routes (#230 S2).

        ASKED SEPARATELY, never inferred from view: a site may grant the two apart, so a reader
        who may see the wiring is not thereby allowed to change it."""
        if _clusterconfig_tier(request, "manage") != TIER_ALL:
            signals.note_admin_refusal()
            raise HTTPException(
                status_code=403,
                detail="Changing cluster configuration is reserved to cluster-configuration "
                       "administrators. This view remains readable.",
            )
        return TIER_ALL
```

```python
    def _cluster_admin_granted(viewer: str | None) -> bool:
        """Whether this viewer passes the cluster-admin tier — the cached verdict, uncounted.

        The core of _cluster_admin_tier, shared with viewer_scope and usage_scope, which consult
        this tier FIRST (#322) and count the decision they serve under their own threshold. FAIL
        CLOSED — Argo's `policy.default: deny` in our vocabulary: no identity, no resolver, or an
        API-server blip all answer False. Never raises. A blip must not widen a surface that names
        cluster credentials.

        NO `restrict` SHORT-CIRCUIT (review of #235, Grok C2): the wide views widen when
        `visibility.enabled` is off, and copying that here would re-admit the very persona this
        tier exists to exclude. Without the proxy there is no trustworthy identity either, and
        `trusted_viewer` returns None — which refuses, for the same reason.
        """
        state = getattr(app.state, "cluster_admin_resolver", None)
        resolver = state if state is not None else (
            cluster_admin_tier if cluster_admin_tier is not None else cluster_admin_resolver)
        if not viewer or resolver is None:
            return False
        try:
            tier = resolver.resolve(viewer) if hasattr(resolver, "resolve") else resolver(viewer)
        except Exception:  # noqa: BLE001
            log.exception("cluster-admin tier resolution failed for %r; refusing", viewer)
            return False
        return tier == TIER_ALL

    def _cluster_admin_tier(request: Request) -> str:
        """The cluster-admin tier for this request, resolved and counted. Returns TIER_ALL or
        TIER_SELF; never raises."""
        scope = TIER_ALL if _cluster_admin_granted(trusted_viewer(request)) else TIER_SELF
        signals.note_decision("cluster_admin", scope)
        return scope

    def require_cluster_admin(request: Request, what: str) -> str:
        """The cluster-admin tier (#322), or a refusal that names itself as one.

        `update clusterrolebindings` on the host by default — the question a cluster-reader fails
        and a cluster-admin passes (Settings carries the measurement). Gates the Cluster
        Configurations tab — the read route and, through /api/whoami, the tab's very existence, and
        the write routes behind the writes switch — and the KPI page. ONE question for the whole
        tab: once it gates the surface there is nothing left for a second level to ask, so view and
        manage are the same verdict. A reader who fails it is not shown that either surface exists.

        NOT the wide tier, deliberately. `require_admin_tier` admits cluster-reader — the auditor
        persona — by design (see usage_scope), and these surfaces are for cluster administrators
        only: how this instance is wired to its clusters, and the fleet's posture and the
        dashboard's own pods. `what` says what the refused view contains; the sentence leads with
        the tier's own words and names no role, grant, chart value or route — it reaches the person
        being refused."""
        if _cluster_admin_tier(request) != TIER_ALL:
            signals.note_admin_refusal()
            raise HTTPException(status_code=403, detail=f"For cluster administrators only. {what}")
        return TIER_ALL
```

<!-- block: local-development/gsd/api.py | edit -->

```python
        current discovery cycle's findings. `clusterconfig:view`, not the wide tier: the sources and the
        findings describe how the fleet is wired, which is not a self reader's — nor the auditor's —
        business. The Cluster Configurations tab (#230 S2) is built on this payload; the writes are S2's too.

        `clusterconfig:view`, NOT the wide tier: the wide one admits the auditor persona by design
        and the operator's ruling of 2026-09-20 forbids it here. See require_clusterconfig_view."""
        require_clusterconfig_view(request)
        viewer = trusted_viewer(request)
        # What THIS reader may do, decided here rather than guessed by the page: `secrets.writes` is
        # the deployment's switch, `can.manage` is the person's level, and the page needs both to tell
        # "this deployment does not write Secrets" from "you may not change them" (#230 S2).
        may_manage = _clusterconfig_tier(request, "manage") == TIER_ALL
```

```python
        current discovery cycle's findings. The cluster-admin tier (#322), not the wide tier: the
        sources and the findings describe how the fleet is wired, which is not a self reader's — nor
        the auditor's — business. The Cluster Configurations tab (#230 S2) is built on this payload;
        the writes are S2's too.

        NOT the wide tier: the wide one admits the auditor persona by design and the operator's
        ruling of 2026-09-20 forbids it here. See require_cluster_admin."""
        require_cluster_admin(request, "This view reports how this instance is wired to its clusters — "
                                       "which Secret configures each one, the kind of credential it holds "
                                       "and how its certificate is trusted.")
        viewer = trusted_viewer(request)
```

<!-- block: local-development/gsd/api.py | edit -->

```python
            "viewer": viewer, "scope": "all",
            # What THIS reader may do, decided here rather than guessed by the page: `writes` stays the
            # deployment's switch, `can.manage` is the person's level, and the page needs both to tell
            # "this deployment does not write Secrets" from "you may not change them" (#230).
            "can": {"view": True, "manage": may_manage},
```

```python
            "viewer": viewer, "scope": "all",
            # One tier for the whole tab (#322): whoever reads it may change it, `secrets.writes` — the
            # deployment's switch — permitting. Kept as a pair so the page's contract holds.
            "can": {"view": True, "manage": True},
```

<!-- block: local-development/gsd/api.py | edit -->

```python
    # Four routes, each: a proxy-verified identity and `clusterconfig:manage` first, the writes switch second, then the writer module,
```

```python
    # Four routes, each: a proxy-verified identity and the cluster-admin tier (#322) first, the writes switch second, then the writer module,
```

<!-- block: local-development/gsd/api.py | edit -->

```python
        `clusterconfig:manage`, never the wide tier (the auditor persona passes that by design)."""
        viewer = trusted_viewer(request)
        if not viewer or not restrict:
            signals.note_admin_refusal()
            raise HTTPException(
                status_code=403,
                detail="Changing cluster configuration is reserved to cluster-configuration "
                       "administrators, and needs an authenticated identity to audit the change to.",
            )
        require_clusterconfig_manage(request)
```

```python
        the cluster-admin tier (#322), never the wide tier (the auditor persona passes that by design)."""
        viewer = trusted_viewer(request)
        if not viewer or not restrict:
            signals.note_admin_refusal()
            raise HTTPException(
                status_code=403,
                detail="Changing cluster configuration is reserved to cluster administrators, and "
                       "needs an authenticated identity to audit the change to.",
            )
        require_cluster_admin(request, "Changing cluster configuration is reserved to cluster administrators.")
```

<!-- block: local-development/gsd/api.py | edit -->

```python
        ADMINISTRATOR TIER ONLY: the internal class counts people, and the trends aggregate the
        fleet's churn and logins, which is governance data about the clusters, not about the reader
        (the same reasoning as /operator-configs). Each block states its as-of, so a figure that
        differs from a signed report's — a snapshot taken earlier — is explained, not mysterious.
        """
        require_admin_tier(request)
        from .kpi import COMPONENT_DASHBOARD, Context
```

```python
        CLUSTER-ADMIN TIER ONLY (#322, the operator's decision of 2026-09-23): the internal class
        counts people, and the trends aggregate the fleet's churn and logins — governance data about
        the clusters, not about the reader — and the wide tier admits the auditor persona, which
        this page is not for. Asked whatever visibility.enabled says, like the Cluster Configurations
        tab. Each block states its as-of, so a figure that differs from a signed report's — a
        snapshot taken earlier — is explained, not mysterious.
        """
        require_cluster_admin(request, "This view reports the dashboard's own pods, the fleet's access "
                                       "posture and its trends — governance data about the clusters, "
                                       "not about the reader.")
        from .kpi import COMPONENT_DASHBOARD, Context
```

<!-- block: local-development/gsd/api.py | edit -->

```python
            out["visibility"] = {
                "scope": scope,
                "enabled": settings.view_restrictions_enabled,
                "clusters": clusters,
            }
            # The Cluster Configurations tier, decided here so the TAB ITSELF can be withheld
            # (#230): a reader who fails `view` gets no tab button, no dispatch and no fetch —
            # an auditor must not learn the surface exists by being refused by it. Both levels
            # ride the same cached resolvers the routes ask, so the strip and the routes cannot
            # disagree. Absent for an unauthenticated reader, who has no tab either.
            # EACH LEVEL FROM ITS OWN QUESTION, never derived from the other (the ruling: a level is
            # its own SAR and composes nothing). `manage` used to read `false` whenever `view` did, so
            # the strip and the write routes disagreed for a reader granted `create secrets` without
            # `get` (round 2, OB2 C4). The page still renders no write control without the page.
            out["clusterconfig"] = {
                "view": _clusterconfig_tier(request, "view") == TIER_ALL,
                "manage": _clusterconfig_tier(request, "manage") == TIER_ALL,
            }
        return out
```

```python
            out["visibility"] = {
                "scope": scope,
                "enabled": settings.view_restrictions_enabled,
                "clusters": clusters,
                # The cluster-admin tier (#322), decided here so the KPI and Cluster Configurations
                # TABS THEMSELVES can be withheld: a reader who fails it gets no tab button, no
                # dispatch and no fetch — an auditor must not learn a surface exists by being refused
                # by it. The same cached resolver the routes ask, so the strip and the routes cannot
                # disagree. Absent, with the whole object, for an unauthenticated reader.
                "cluster_admin": _cluster_admin_tier(request) == TIER_ALL,
            }
        return out
```

<!-- block: local-development/gsd/api.py | edit -->

```python
    # The two cluster-configuration levels, on their own seams so a test can substitute either
    # without touching the other or the wide tier (#230).
    app.state.clusterconfig_view_resolver = clusterconfig_view_tier or clusterconfig_view_resolver
    app.state.clusterconfig_manage_resolver = clusterconfig_manage_tier or clusterconfig_manage_resolver
```

```python
    # The cluster-admin tier's own seam (#322), so a test can substitute it without touching the wide
    # or Usage tier — and the seam every host tier consults first, since a pass here is every one.
    app.state.cluster_admin_resolver = cluster_admin_tier or cluster_admin_resolver
```

### `local-development/gsd/static/index.html` — the tabs, the page, the fetches

<!-- block: local-development/gsd/static/index.html | edit -->

```js
      ${tab("kpi", "KPIs")}
```

```js
      ${clusterAdmin() ? tab("kpi", "KPIs") : ""}
```

<!-- block: local-development/gsd/static/index.html | edit -->

```js
      ${ccMayView() ? tab("clusters", "Cluster Configurations") : ""}
```

```js
      ${clusterAdmin() ? tab("clusters", "Cluster Configurations") : ""}
```

<!-- block: local-development/gsd/static/index.html | edit -->

```js
/* Two different reasons the form cannot write, and the page must not confuse them (#230): the
   DEPLOYMENT's switch (clusterConfig.secrets.writes.enabled) and THIS READER's level
   (clusterconfig:manage). Both must hold for a write control to exist; each has its own sentence. */
function ccWritesOn() {
  return ccDeploymentWrites() && ccMayManage();
}
```

```js
/* Two different reasons the form cannot write, and the page must not confuse them (#230): the
   DEPLOYMENT's switch (clusterConfig.secrets.writes.enabled) and THIS READER's tier (the
   cluster-admin tier, #322). Both must hold for a write control to exist; each has its own sentence. */
function ccWritesOn() {
  return ccDeploymentWrites() && clusterAdmin();
}
```

<!-- block: local-development/gsd/static/index.html | edit -->

```js
/* The reader's levels, from whoami — the same cached decision the routes ask, so the tab strip, the
   controls and the API cannot disagree. Absent whoami is indeterminate: no tab and no controls. */
function ccMayView() {
  const w = data.whoami;
  return !!(w && w.clusterconfig && w.clusterconfig.view);
}
function ccMayManage() {
  const w = data.whoami;
  return !!(w && w.clusterconfig && w.clusterconfig.manage);
}
```

```js
/* The reader's cluster-admin tier (#322), from whoami — the same cached decision the routes ask, so
   the tab strip, the controls and the API cannot disagree. It gates the Cluster Configurations tab
   whole (view and manage are one question) and the KPI page. Absent whoami is indeterminate: no tab
   and no controls; so is an unauthenticated reader, who has no tier. */
function clusterAdmin() {
  const w = data.whoami;
  return !!(w && w.authenticated && w.visibility && w.visibility.cluster_admin === true);
}
```

<!-- block: local-development/gsd/static/index.html | edit -->

```js
      main.innerHTML = ccMayView() ? clusterConfigPage() : refusalCard("Cluster Configurations", CLUSTERS_REFUSAL);
      if (ccMayView()) wireClusterConfig();
```

```js
      main.innerHTML = clusterAdmin() ? clusterConfigPage() : refusalCard("Cluster Configurations", CLUSTERS_REFUSAL);
      if (clusterAdmin()) wireClusterConfig();
```

<!-- block: local-development/gsd/static/index.html | edit -->

```js
  } else if (view.page === "kpi") {
    // The same tier rule as the Overview, in the same words: the page is about the clusters and
    // the dashboard's own pods, and answers nothing a reader can ask about themselves. Keyed on the
    // HOST's headline, as Reports is and as the fetch is: the page is fleet-wide, so a narrowed
    // remote left selected must not refuse a host administrator (review of #157, Grok).
    if (!readerTierKnown()) {
      main.innerHTML = `<section class="card"><div class="empty-note">Loading…</div></section>`;
    } else if (narrowedOnHost()) {
      main.innerHTML = refusalCard("KPIs", KPI_REFUSAL);
    } else {
```

```js
  } else if (view.page === "kpi") {
    // The cluster-admin tier (#322), read off whoami as the tab is: the page is about the clusters
    // and the dashboard's own pods, and the wide tier admits the auditor persona it is not for. A
    // host tier, whatever cluster is selected — the page is fleet-wide, so a narrowed remote left
    // selected must not refuse a host administrator (review of #157, Grok). Never a refusal on
    // silence: a null whoami is indeterminate (the Cluster Configurations rule above).
    if (!readerTierKnown()) {
      main.innerHTML = `<section class="card"><div class="empty-note">Loading…</div></section>`;
    } else if (!clusterAdmin()) {
      main.innerHTML = refusalCard("KPIs", KPI_REFUSAL);
    } else {
```

<!-- block: local-development/gsd/static/index.html | edit -->

```js
    // The KPI page (#157): one payload, the KPI module's (#156) — every number on the page comes
    // from it. Administrator tier: a narrowed reader gets the designed 403, rendered as the refusal
    // card, so the fetch is skipped for a reader already known to be narrowed.
    if (view.page === "kpi" && !narrowedOnHost()) {
      want.kpi = guard403(get("/api/kpi"));
    }
    // The Cluster Configurations page (#230 S2): one payload, and only for a reader the
    // `clusterconfig:view` level admits — a reader without it makes NO request, so the surface
    // leaves no trace for them at all (#230; the tab is absent for them too).
    // NOT gated on the wide tier (narrowedOnHost) any more: this surface has a tier OF ITS OWN
    // (#230), and the route asks `clusterconfig:view` alone. A site may grant `get secrets` to
    // someone the wide tier narrows; deferring to it here would have shown them an empty page the
    // API would have answered.
    if (view.page === "clusters" && ccMayView()) {
      want.clusterconfigs = guard403(get("/api/clusterconfigs"));
    }
```

```js
    // The KPI page (#157): one payload, the KPI module's (#156) — every number on the page comes
    // from it. Cluster-admin tier (#322): a reader without it gets the designed 403, rendered as
    // the refusal card, so the fetch is skipped for a reader already known to fail it.
    if (view.page === "kpi" && clusterAdmin()) {
      want.kpi = guard403(get("/api/kpi"));
    }
    // The Cluster Configurations page (#230 S2): one payload, and only for a reader the
    // cluster-admin tier admits (#322) — a reader without it makes NO request, so the surface
    // leaves no trace for them at all (#230; the tab is absent for them too).
    // NOT gated on the wide tier (narrowedOnHost): this surface has a tier OF ITS OWN, and the
    // route asks that tier alone. A site may point clusterAdminSar at a question someone the wide
    // tier narrows passes; deferring to the wide tier here would have shown them an empty page the
    // API would have answered.
    if (view.page === "clusters" && clusterAdmin()) {
      want.clusterconfigs = guard403(get("/api/clusterconfigs"));
    }
```

<!-- block: local-development/gsd/static/index.html | edit -->

```js
      // From THIS surface's own tier, not the wide one (#230): the whoami that just landed carries
      // the levels, and a reader without `view` is refused here whatever the wide tier says.
      if (!ccMayView()) {
```

```js
      // From THIS surface's own tier, not the wide one (#230, #322): the whoami that just landed
      // carries it, and a reader without it is refused here whatever the wide tier says.
      if (!clusterAdmin()) {
```

<!-- block: local-development/gsd/static/index.html | edit -->

```js
    if (view.page === "kpi" && got.whoami) {
      if (narrowedOnHost()) {
        data.kpi = null;
```

```js
    if (view.page === "kpi" && got.whoami) {
      if (!clusterAdmin()) {
        data.kpi = null;
```

### `charts/group-sync-dashboard/values.yaml` — the value

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

```yaml
  # THE CLUSTER-CONFIGURATION TIER — two levels of its own (#230), modelled on Argo CD's RBAC,
  # where a first-class `clusters` resource carries `get` and `create/update/delete` actions.
  # We hold no policy file: every tier here is a SubjectAccessReview against this cluster, so
  # OpenShift groups and RoleBindings already are that mapping. The two questions are therefore
  # asked about the very objects the surface exposes — the cluster Secrets themselves:
  #
  #   clusterConfigViewSar   (Argo `clusters, get`)      -> the Cluster Configurations tab and
  #                                                         GET /api/clusterconfigs
  #   clusterConfigManageSar (Argo `clusters, create…`)  -> the write routes and the form's
  #                                                         Create / Rotate / Delete / Test (#230 S2)
  #
  # It reads as what it is: you may SEE cluster credentials if you may read the Secrets that hold
  # them, and CHANGE them if you may create those Secrets.
  #
  # WHY NOT THE WIDE `adminSar`, measured on CRC 2026-09-20: `cluster-reader` — the deliberate
  # auditor persona, which passes the wide tier by design — has ZERO of its 172 rules covering
  # core/`secrets`, and `oc auth can-i {get,list,create,update,delete} secrets` answers `no`. So
  # the auditor fails both levels by construction and a cluster-admin passes both.
  #
  # An empty `namespace` means THIS RELEASE'S namespace, where the cluster Secrets live — the
  # opposite of `adminSar`'s empty, which means a cluster-scoped check, because these questions
  # are namespaced by nature. Point them at your own question (a dedicated `fleet-admin`
  # ClusterRole, say) and both levels move independently: `manage` is never derived from `view`.
  clusterConfigViewSar:
    apiGroup: ""
    resource: secrets
    verb: get
    namespace: ""
  clusterConfigManageSar:
    apiGroup: ""
    resource: secrets
    verb: create
    namespace: ""
```

```yaml
  # THE CLUSTER-ADMIN TIER (#322; the operator's decision of 2026-09-23) — ONE SubjectAccessReview,
  # asked on this cluster, for the surfaces that are for cluster administrators only:
  #
  #   the Cluster Configurations tab — its existence, GET /api/clusterconfigs, and the write routes
  #     (Create / Rotate / Delete / Test), which clusterConfig.secrets.writes.enabled still switches
  #   the KPI page — GET /api/kpi
  #   Rejoin (#316), when it is built
  #
  # THE TOP TIER: a reader who passes it is granted every tier this cluster decides — the wide view
  # here and on `inherit` clusters, and Usage — whatever adminSar and usageAdminSar answer for them,
  # and with visibility.enabled off too. One way only: passing adminSar or usageAdminSar never
  # implies this one, so those stay separate and can be loosened without handing anyone this tab.
  # Per-cluster policies still apply: a `remote-sar` cluster asks its own API about the person, a
  # `self-only` cluster stays self, a `hidden` cluster stays hidden.
  #
  # WHY THIS CHECK, measured on CRC: `list clusterrolebindings` (adminSar) admits cluster-reader, so
  # the auditor saw the KPI page; `create secrets` in this namespace (the two-level tier this
  # replaces, chart 0.42.1 to 0.56.0) kept the auditor out but admitted anyone holding `admin` or
  # `edit` on that one namespace, who is not a cluster administrator. `update clusterrolebindings`
  # — the question usageAdminSar already asks — a cluster-reader fails and a cluster-admin passes.
  # Its own setting, not usageAdminSar's, so one moves without the other. Same exact-lowercase
  # render guards as adminSar. THE DASHBOARD STILL NEVER WRITES: a SubjectAccessReview only asks.
  #
  # ASKED WHATEVER visibility.enabled SAYS, like the tier it replaces: turning the cluster-data
  # restrictions off must not hand KPI or the fleet's wiring to every proxy-admitted reader. So with
  # visibility.enabled: false the auth-delegator grant still renders and the review is still made;
  # without that grant the two surfaces refuse everyone. An empty namespace is a cluster-scoped
  # check, like adminSar's.
  #
  # `visibility.clusterConfigViewSar` and `visibility.clusterConfigManageSar` are REMOVED (chart
  # 0.57.0): a values file that still sets either fails the render with a message naming this key.
  clusterAdminSar:
    apiGroup: rbac.authorization.k8s.io
    resource: clusterrolebindings
    verb: update
    namespace: ""
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

```yaml
    # reader holding clusterconfig:manage — visibility.clusterConfigManageSar — with a proxy-verified
```

```yaml
    # reader the cluster-admin tier admits — visibility.clusterAdminSar, #322 — with a proxy-verified
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

```yaml
    # ONE EDGE WORTH KNOWING, measured: with `visibility.enabled=false` the usage tier is not
    # consulted at all, so this view stays per-person for EVERY reader including a
    # cluster-admin, and `all` here becomes the only thing that widens it. That is deliberate
    # and it is the safe direction — switching off scoping for CLUSTER data must not, as a side
    # effect, publish presence records. It also means no SubjectAccessReview is attempted in
    # that state, which is why the auth-delegator grant may be absent there without breaking
    # anything.
```

```yaml
    # ONE EDGE WORTH KNOWING: with `visibility.enabled=false` the usage tier is not consulted
    # at all, so this view stays per-person for every reader but one who passes
    # `visibility.clusterAdminSar` — the top tier, asked in that state too (#322) — and `all`
    # here is the only thing that widens it for anyone else. That is deliberate and it is the
    # safe direction — switching off scoping for CLUSTER data must not, as a side effect,
    # publish presence records to the auditor.
```

### `charts/group-sync-dashboard/templates/_helpers.tpl` — the field helper and the refusal

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->

```text
{{/*
The cluster-configuration tier's two SAR blocks (#230): visibility.clusterConfigViewSar and
visibility.clusterConfigManageSar. ONE parameterised helper rather than eight near-identical ones —
the two blocks and their four fields validate identically, and a copy per field is four more places
for a guard to drift. Call it with a dict: {ctx, block, field, default}.

Same discipline as the adminSar helpers: nil-safe (commenting out the sub-keys leaves
`visibility:` present-but-nil, which a bare field access panics on), and a malformed value FAILS
THE RENDER rather than silently answering no for every viewer — which here would not demote an
administrator but lock everyone out of the surface, including the person trying to fix it.
*/}}
{{- define "gsd.clusterConfigSarField" -}}
{{- $sar := (index (.ctx.Values.visibility | default dict) .block) | default dict -}}
{{- if or (not (hasKey $sar .field)) (kindIs "invalid" (index $sar .field)) -}}
{{- .default -}}
{{- else -}}
{{- $v := trim (toString (index $sar .field)) -}}
{{- $ok := dict "apiGroup" "^[a-z0-9.-]*$" "resource" "^[a-z0-9-]+(/[a-z0-9-]+)?$" "verb" "^[a-z]+$" "namespace" "^[a-z0-9-]*$" -}}
{{- if not (regexMatch (index $ok .field) $v) -}}
{{- fail (printf "visibility.%s.%s %q is not a %s. RBAC matching is exact, so anything else would answer no for every viewer and close the Cluster Configurations surface to everyone." .block .field $v .field) -}}
{{- end -}}
{{- $v -}}
{{- end -}}
{{- end -}}
```

```text
{{/*
The cluster-admin tier's SAR block (#322): visibility.clusterAdminSar — one question, `update
clusterrolebindings` on this cluster by default, gating the Cluster Configurations tab and the KPI
page and granting every host tier to whoever passes it. ONE parameterised helper for its four fields
rather than four near-identical ones. Call it with a dict: {ctx, field, default}.

Same discipline as the adminSar helpers: nil-safe (commenting out the sub-keys leaves
`visibility:` present-but-nil, which a bare field access panics on), and a malformed value FAILS
THE RENDER rather than silently answering no for every viewer — which here would not demote an
administrator but close the Cluster Configurations tab and the KPI page to everyone, including the
person trying to fix it.
*/}}
{{- define "gsd.clusterAdminSarField" -}}
{{- $sar := ((.ctx.Values.visibility | default dict).clusterAdminSar) | default dict -}}
{{- if or (not (hasKey $sar .field)) (kindIs "invalid" (index $sar .field)) -}}
{{- .default -}}
{{- else -}}
{{- $v := trim (toString (index $sar .field)) -}}
{{- $ok := dict "apiGroup" "^[a-z0-9.-]*$" "resource" "^[a-z0-9-]+(/[a-z0-9-]+)?$" "verb" "^[a-z]+$" "namespace" "^[a-z0-9-]*$" -}}
{{- if not (regexMatch (index $ok .field) $v) -}}
{{- fail (printf "visibility.clusterAdminSar.%s %q is not a %s. RBAC matching is exact, so anything else would answer no for every viewer and close the Cluster Configurations tab and the KPI page to everyone." .field $v .field) -}}
{{- end -}}
{{- $v -}}
{{- end -}}
{{- end -}}

{{/*
The two blocks the cluster-admin tier replaced (#322): visibility.clusterConfigViewSar and
visibility.clusterConfigManageSar, chart 0.42.1 to 0.56.0. Helm ignores a key no template reads, so a
values file that still sets one would render clean while its question silently stopped being asked —
refuse it, naming the key that took its place. Only a block that sets something is refused: a nulled
block (`clusterConfigViewSar: null`, or its sub-keys commented out) or `{}` asked no question of its
own, and Helm keeps a nulled key the chart's defaults do not carry, so presence alone is not the test.
*/}}
{{- define "gsd.refuseRemovedVisibilitySar" -}}
{{- $vis := .Values.visibility | default dict -}}
{{- range $old := list "clusterConfigViewSar" "clusterConfigManageSar" -}}
{{- if index $vis $old -}}
{{- fail (printf "visibility.%s was removed in chart 0.57.0 (#322). One question, visibility.clusterAdminSar (default: update clusterrolebindings.rbac.authorization.k8s.io, cluster-scoped), now gates the whole Cluster Configurations tab and the KPI page. Delete this block; to ask a different question, set visibility.clusterAdminSar.{apiGroup,resource,verb,namespace}." $old) -}}
{{- end -}}
{{- end -}}
{{- end -}}
```

### `charts/group-sync-dashboard/templates/configmap.yaml` — the keys

<!-- block: charts/group-sync-dashboard/templates/configmap.yaml | edit -->

```yaml
    {{- /* The cluster-configuration tier's two levels (#230): view = Argo's `clusters, get`, manage
           = its `create/update/delete`, asked as SARs about the Secrets this surface exposes. */}}
    visibilityClusterConfigViewSarApiGroup: {{ include "gsd.clusterConfigSarField" (dict "ctx" . "block" "clusterConfigViewSar" "field" "apiGroup" "default" "") | quote }}
    visibilityClusterConfigViewSarResource: {{ include "gsd.clusterConfigSarField" (dict "ctx" . "block" "clusterConfigViewSar" "field" "resource" "default" "secrets") | quote }}
    visibilityClusterConfigViewSarVerb: {{ include "gsd.clusterConfigSarField" (dict "ctx" . "block" "clusterConfigViewSar" "field" "verb" "default" "get") | quote }}
    visibilityClusterConfigViewSarNamespace: {{ include "gsd.clusterConfigSarField" (dict "ctx" . "block" "clusterConfigViewSar" "field" "namespace" "default" "") | quote }}
    visibilityClusterConfigManageSarApiGroup: {{ include "gsd.clusterConfigSarField" (dict "ctx" . "block" "clusterConfigManageSar" "field" "apiGroup" "default" "") | quote }}
    visibilityClusterConfigManageSarResource: {{ include "gsd.clusterConfigSarField" (dict "ctx" . "block" "clusterConfigManageSar" "field" "resource" "default" "secrets") | quote }}
    visibilityClusterConfigManageSarVerb: {{ include "gsd.clusterConfigSarField" (dict "ctx" . "block" "clusterConfigManageSar" "field" "verb" "default" "create") | quote }}
    visibilityClusterConfigManageSarNamespace: {{ include "gsd.clusterConfigSarField" (dict "ctx" . "block" "clusterConfigManageSar" "field" "namespace" "default" "") | quote }}
```

```yaml
    {{- /* The cluster-admin tier (#322): one question, `update clusterrolebindings` on this cluster by
           default, gating the Cluster Configurations tab and the KPI page and granting every host tier
           to whoever passes it. The two blocks it replaced are refused by name at render. */}}
    {{- include "gsd.refuseRemovedVisibilitySar" . }}
    visibilityClusterAdminSarApiGroup: {{ include "gsd.clusterAdminSarField" (dict "ctx" . "field" "apiGroup" "default" "rbac.authorization.k8s.io") | quote }}
    visibilityClusterAdminSarResource: {{ include "gsd.clusterAdminSarField" (dict "ctx" . "field" "resource" "default" "clusterrolebindings") | quote }}
    visibilityClusterAdminSarVerb: {{ include "gsd.clusterAdminSarField" (dict "ctx" . "field" "verb" "default" "update") | quote }}
    visibilityClusterAdminSarNamespace: {{ include "gsd.clusterAdminSarField" (dict "ctx" . "field" "namespace" "default" "") | quote }}
```

### `charts/group-sync-dashboard/templates/rbac.yaml` — the grant's condition and its comment

<!-- block: charts/group-sync-dashboard/templates/rbac.yaml | edit -->

```yaml
{{- if and .Values.oauthProxy.enabled (or .Values.oauthProxy.apiTokenAccess.enabled (eq (include "gsd.visibilityEnabled" .) "true") (and .Values.clusterConfig.secrets.enabled (eq (include "gsd.visibilityEnabled" .) "false"))) }}
```

```yaml
{{- if .Values.oauthProxy.enabled }}
```

<!-- block: charts/group-sync-dashboard/templates/rbac.yaml | edit -->

```yaml
# AND IT RENDERS FOR THE CLUSTER-CONFIGURATION TIER TOO (#230, review of #235 by the Fable seat).
# That tier is deliberately independent of visibility.enabled — turning cluster-DATA restrictions off
# must not hand the fleet's wiring to every proxy-admitted reader — so it asks a SubjectAccessReview
# even when visibility is off. Without this binding in that state every such review errors and the
# surface refuses EVERYONE, administrators included, with nothing but a log line to say why. Measured
```

```yaml
# AND IT RENDERS FOR THE CLUSTER-ADMIN TIER TOO (#322; first for the #230 tier it replaced, review of
# #235 by the Fable seat). That tier — visibility.clusterAdminSar, the Cluster Configurations tab and
# the KPI page — is deliberately independent of visibility.enabled: turning cluster-DATA restrictions
# off must not hand the fleet's wiring or the KPI page to every proxy-admitted reader, so it asks a
# SubjectAccessReview even when visibility is off. Without this binding in that state every such
# review errors and both surfaces refuse EVERYONE, administrators included, with nothing but a log
# line to say why. The KPI page is on every install, so the binding renders WHENEVER THE PROXY IS ON
# (#322, Grok's review of SPEC_T2, C9): the tier asks only about a proxy-verified identity, so with the
# proxy off nothing asks and the binding is absent. Measured
```

### `charts/group-sync-dashboard/Chart.yaml`, `local-development/pyproject.toml`, `local-development/gsd/__init__.py` — the versions

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```yaml
# SPEC_S5 (#293): ConfigMap onboarding and namespaced read RBAC; minor release.
version: 0.56.0
```

```yaml
# SPEC_S5 (#293): ConfigMap onboarding and namespaced read RBAC; minor release.
# CHART 0.57.0 (2026-09-25), MINOR: the cluster-admin tier, `visibility.clusterAdminSar` (#322,
# SPEC_T2) — one SubjectAccessReview, `update clusterrolebindings` on the host by default, gates the
# whole Cluster Configurations tab and the KPI page and grants every host tier to whoever passes it.
# `visibility.clusterConfigViewSar` and `.clusterConfigManageSar` are removed and refused by name.
# appVersion moves to application 0.35.0 (below). WHO LOSES ACCESS: cluster-readers lose the KPI
# page; namespace-scoped `admin`/`edit` holders lose the Cluster Configurations tab.
version: 0.57.0
```

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```yaml
# the platform's own is a finding from the first refresh after upgrade, which is the capability.
appVersion: "0.34.1"
```

```yaml
# the platform's own is a finding from the first refresh after upgrade, which is the capability.
# 0.35.0 (2026-09-25). The cluster-admin tier (#322, SPEC_T2): `GET /api/kpi` and the whole Cluster
# Configurations tab ask `visibility.clusterAdminSar`; `/api/whoami` carries `visibility.cluster_admin`
# and drops `clusterconfig`; the `cluster_admin` threshold label replaces `clusterconfig_view` and
# `clusterconfig_manage`. MINOR: who may open two surfaces changes on upgrade (docs/CHANGELOG.md).
appVersion: "0.35.0"
```

<!-- block: local-development/pyproject.toml | edit -->

```toml
version = "0.34.1"
```

```toml
version = "0.35.0"
```

<!-- block: local-development/gsd/__init__.py | edit -->

```python
__version__ = "0.34.1"
```

```python
__version__ = "0.35.0"
```

### `charts/group-sync-dashboard/README.md` — the rows

<!-- block: charts/group-sync-dashboard/README.md | edit -->

```markdown
| `visibility.clusterConfigViewSar.apiGroup` / `.resource` / `.verb` | `""` (core) / `secrets` / `get` | **`clusterconfig:view`** — the THIRD tier, for the **Cluster Configurations** surface (#230), modelled on Argo CD's first-class `clusters` resource and its `get` action. Gates `GET /api/clusterconfigs` and the tab's existence: a reader who fails it is not shown that the surface is there. Asked about the objects the surface exposes — the cluster Secrets — so it reads as what it is: you may see cluster credentials if you may read the Secrets that hold them. **Not** the wide `adminSar`: `cluster-reader`, the auditor persona, passes that one by design, and on CRC (2026-09-20) has zero of its 172 rules covering `secrets` |
| `visibility.clusterConfigManageSar.apiGroup` / `.resource` / `.verb` | `""` (core) / `secrets` / `create` | **`clusterconfig:manage`** — Argo's `clusters, create/update/delete`. Gates the write routes and the form's Create / Rotate / Delete / Test (#230 S2). Asked **separately**: `manage` is never inferred from `view`, so a site may grant the two apart |
| `visibility.clusterConfigViewSar.namespace` / `visibility.clusterConfigManageSar.namespace` | `""` | empty = **this release's namespace**, where the cluster Secrets live — the opposite of `adminSar`'s empty, because these two questions are namespaced by nature |
```

```markdown
| `visibility.clusterAdminSar.apiGroup` / `.resource` / `.verb` | `rbac.authorization.k8s.io` / `clusterrolebindings` / `update` | **the cluster-admin tier** (#322), the top tier: ONE check for the surfaces that are for cluster administrators only — the **Cluster Configurations** tab whole (its existence, `GET /api/clusterconfigs`, and the Create / Rotate / Delete / Test routes, which `clusterConfig.secrets.writes.enabled` still switches) and the **KPI page**; Rejoin (#316) when it lands. A reader who passes it is granted every tier this cluster decides — the wide view here and on `inherit` clusters, and Usage — whatever `adminSar` and `usageAdminSar` answer, and with `visibility.enabled: false` too; one way only, so loosening those never hands anyone this tab. A `remote-sar` cluster still asks its own API, a `self-only` cluster stays self. The default is the question `usageAdminSar` asks, as its own setting: `cluster-reader` (the auditor, who passes `adminSar`) fails it, `cluster-admin` passes it — measured on CRC. **The dashboard never writes; a SubjectAccessReview only asks.** Asked whatever `visibility.enabled` says, so the `auth-delegator` grant renders in both states and without it both surfaces refuse everyone. Same exact-lowercase render guard. Replaces `clusterConfigViewSar` / `clusterConfigManageSar` (chart 0.42.1 to 0.56.0), which are refused by name |
| `visibility.clusterAdminSar.namespace` | `""` | empty = a cluster-scoped check, the normal case, which `update clusterrolebindings` is |
```

<!-- block: charts/group-sync-dashboard/README.md | edit -->

```markdown
| — | — | **Both levels are asked even when `visibility.enabled` is `false`.** That independence is deliberate: turning cluster-DATA restrictions off must not hand the fleet's wiring to every reader the proxy admits. It means the chart renders the `system:auth-delegator` binding whenever `clusterConfig.secrets.enabled` is on, because a tier that asks a SubjectAccessReview without the grant to ask it refuses everyone — administrators included — with only a log line to say why |
```

```markdown
| — | — | **The cluster-admin tier is asked even when `visibility.enabled` is `false`.** That independence is deliberate: turning cluster-DATA restrictions off must not hand the fleet's wiring or the KPI page to every reader the proxy admits. It means the chart renders the `system:auth-delegator` binding whenever `oauthProxy.enabled` is on, because a tier that asks a SubjectAccessReview without the grant to ask it refuses everyone — administrators included — with only a log line to say why |
```

<!-- block: charts/group-sync-dashboard/README.md | edit -->

```markdown
| `clusterConfig.secrets.writes.enabled` | `false` | the Cluster Configurations tab's writes (#230 S2, `docs/specs/SPEC_S2_cluster_configurations_tab.md`): `create`, `update`, `delete` join the `-cluster-secrets` Role so an administrator can add a cluster from the tab (the same labelled Secret a GitOps process would write, `gsd-cluster-<name>`, annotated `groupsync-dashboard.io/managed-by: ui`), rotate its bearer token in place, or delete it (the cluster retires, its history kept). The app writes only in its own namespace, only Secrets carrying the label (checked by the app — RBAC cannot scope a verb by label), only for a reader holding `clusterconfig:manage` (`visibility.clusterConfigManageSar`, never the wide tier the auditor passes) with a proxy-verified identity, one audit log line per write naming the person, the verb and the Secret; the credential never reaches a response, a log line, the database or `/metrics`. **Off by default**, a stated exception to the on-by-default rule: a write path on Secrets widens the dashboard's read-only posture (its only write anywhere is its own leader Lease), so it stays off until the operator turns it on — the default is pending the operator's A/B call of 2026-09-20; B flips it and removes the exception. Off, no write route is registered (a POST is a `405`) and the tab is read-only, its form still producing the Secret's YAML for a GitOps process to apply |
```

```markdown
| `clusterConfig.secrets.writes.enabled` | `false` | the Cluster Configurations tab's writes (#230 S2, `docs/specs/SPEC_S2_cluster_configurations_tab.md`): `create`, `update`, `delete` join the `-cluster-secrets` Role so an administrator can add a cluster from the tab (the same labelled Secret a GitOps process would write, `gsd-cluster-<name>`, annotated `groupsync-dashboard.io/managed-by: ui`), rotate its bearer token in place, or delete it (the cluster retires, its history kept). The app writes only in its own namespace, only Secrets carrying the label (checked by the app — RBAC cannot scope a verb by label), only for a reader the cluster-admin tier admits (`visibility.clusterAdminSar`, #322 — never the wide tier the auditor passes) with a proxy-verified identity, one audit log line per write naming the person, the verb and the Secret; the credential never reaches a response, a log line, the database or `/metrics`. **Off by default**, a stated exception to the on-by-default rule: a write path on Secrets widens the dashboard's read-only posture (its only write anywhere is its own leader Lease), so it stays off until the operator turns it on — the default is pending the operator's A/B call of 2026-09-20; B flips it and removes the exception. Off, no write route is registered (a POST is a `405`) and the tab is read-only, its form still producing the Secret's YAML for a GitOps process to apply |
```

### `docs/CHANGELOG.md` — the release note

<!-- block: docs/CHANGELOG.md | after: ## Unreleased -->

```markdown

- **The cluster-admin tier: `visibility.clusterAdminSar` gates the Cluster Configurations tab and the KPI page, and grants every host tier (application 0.35.0, chart 0.57.0; #322, `docs/specs/SPEC_T2_cluster_admin_tier.md`).** One SubjectAccessReview — `update clusterrolebindings.rbac.authorization.k8s.io`, cluster-scoped, on the host — decides who may open `GET /api/kpi` and the whole Cluster Configurations tab (`GET /api/clusterconfigs`, its existence in the tab strip, and the Create / Rotate / Delete / Test routes, which `clusterConfig.secrets.writes.enabled` still switches). It is asked whatever `visibility.enabled` says, and a reader who passes it is granted every tier this cluster decides — the wide view on the host and on `inherit` clusters, and Usage — whatever `visibility.adminSar` and `visibility.usageAdminSar` answer for them; one way only, so those two settings can still be loosened without handing anyone this tab. A `remote-sar` cluster still asks its own API, a `self-only` cluster stays self. `/api/whoami` carries `visibility.cluster_admin` and drops `clusterconfig`; both tabs are absent, not disabled, for a reader who fails it; the refusal leads with *For cluster administrators only.* The `cluster_admin` threshold label replaces `clusterconfig_view` and `clusterconfig_manage` on `gsd_visibility_tier_checks_total` and `gsd_visibility_decisions_total`. **Who loses access on upgrade:** cluster-readers (the auditor persona, who passes `list clusterrolebindings`) lose the KPI page; holders of `admin` or `edit` in the release namespace — by RoleBinding or cluster-wide — who are not cluster administrators lose the Cluster Configurations tab, which `get`/`create secrets` used to open for them; and with the oauth-proxy off there is no identity to ask about, so the KPI page is withheld where the proxy-less install served it wide. **Upgrade:** `visibility.clusterConfigViewSar` and `visibility.clusterConfigManageSar` are removed; a values file that still sets either fails the render with a message naming `visibility.clusterAdminSar` — delete the block, and set `visibility.clusterAdminSar.{apiGroup,resource,verb,namespace}` only to ask a different question. The `auth-delegator` grant now renders whenever `oauthProxy.enabled` is on — new only where `visibility.enabled`, `oauthProxy.apiTokenAccess.enabled` and `clusterConfig.secrets.enabled` were all off, which rendered none — because without it both surfaces would refuse everyone; no grant is removed. SPEC_S4c's reserved versions move to app 0.36.0, chart 0.58.0.
```

### `docs/ACCESS_CONTROL.md` — the tiers

<!-- block: docs/ACCESS_CONTROL.md | edit -->

```markdown
## 2. The two thresholds

A reader is placed in a **tier** by asking the cluster a question about them — a
SubjectAccessReview. There are two independent thresholds:

| threshold | values key | default check | governs |
|---|---|---|---|
| **wide tier** | `visibility.adminSar` | `list clusterrolebindings.rbac.authorization.k8s.io` | every cluster-data view |
| **usage tier** | `visibility.usageAdminSar` | `update clusterrolebindings.rbac.authorization.k8s.io` | the Usage tab alone |
```

```markdown
## 2. The three thresholds

A reader is placed in a **tier** by asking the cluster a question about them — a
SubjectAccessReview. There are three thresholds, each its own setting, resolver and cache:

| threshold | values key | default check | governs |
|---|---|---|---|
| **wide tier** | `visibility.adminSar` | `list clusterrolebindings.rbac.authorization.k8s.io` | every cluster-data view |
| **usage tier** | `visibility.usageAdminSar` | `update clusterrolebindings.rbac.authorization.k8s.io` | the Usage tab alone |
| **cluster-admin tier** | `visibility.clusterAdminSar` | `update clusterrolebindings.rbac.authorization.k8s.io` | the KPI page and the whole Cluster Configurations tab (#322) — and, for whoever passes it, every tier above |

**The cluster-admin tier is the top tier** (the operator's decision of 2026-09-23, #322). A reader who
passes it is granted every tier the host decides — the wide view on the host and on `inherit`
clusters, and Usage, with `visibility.enabled: false` too — whatever the other two questions answer
for them (`gsd/api.py#viewer_scope`, `gsd/api.py#usage_scope` consult it first). One way only:
passing the wide or the usage question never implies it, so those two can be loosened without
handing anyone the Cluster Configurations tab. Per-cluster policies still apply (§11): a `remote-sar`
cluster asks its own API about the person, a `self-only` cluster stays self, a `hidden` cluster stays
hidden. It is asked whatever `visibility.enabled` says (§8), and the default is the usage tier's
question as its own setting — a cluster-reader fails it, a cluster-admin passes it — where the
`get`/`create secrets` pair it replaced admitted anyone holding `admin` or `edit` in the release
namespace.
```

<!-- block: docs/ACCESS_CONTROL.md | edit -->

```markdown
| Access granted | their own grants, via their groups | all | all |
| RBAC policy | *For administrators only* | all | all |
```

```markdown
| Access granted | their own grants, via their groups | all | all |
| RBAC policy | *For administrators only* | all | all |
| KPIs | *For cluster administrators only* | **absent** | all |
| Cluster Configurations | *For cluster administrators only* | **absent** | all |
```

<!-- block: docs/ACCESS_CONTROL.md | edit -->

```markdown
| `/api/clusters/{c}/operator-configs` | **403** | all |
```

```markdown
| `/api/clusters/{c}/operator-configs` | **403** | all |
| `/api/kpi` | **403** | **403** unless the reader passes the cluster-admin tier (#322) |
| `/api/clusterconfigs` and its four write routes | **403** | **403** unless the reader passes the cluster-admin tier (#322); the writes also need `clusterConfig.secrets.writes.enabled` |
```

<!-- block: docs/ACCESS_CONTROL.md | edit -->

```markdown
With `visibility.enabled=false` the usage tier is **not consulted at all** — measured — so no
SubjectAccessReview is attempted in that state, which is why the `auth-delegator` grant may be
absent there without breaking anything. Switching off scoping for *cluster* data must not, as a side
effect, publish presence records.
```

```markdown
With `visibility.enabled=false` the usage tier is **not consulted at all** — measured — so switching
off scoping for *cluster* data does not, as a side effect, publish presence records. The
**cluster-admin tier is still asked** in that state (#322, as the Cluster Configurations tier it
replaced was): the KPI page and the Cluster Configurations tab stay reserved to whoever passes it,
and a cluster-admin keeps Usage through it. The chart therefore renders the `auth-delegator` grant
with `visibility.enabled: false` too; without it every such review errors and both surfaces refuse
everyone. With the proxy off there is no identity to ask about, so both are withheld.
```

<!-- block: docs/ACCESS_CONTROL.md | edit -->

```markdown
| use a different bar for Usage | `visibility.usageAdminSar.{...}` |
```

```markdown
| use a different bar for Usage | `visibility.usageAdminSar.{...}` |
| use a different bar for the cluster-admin tier (KPIs, Cluster Configurations, and the top tier) | `visibility.clusterAdminSar.{...}` |
```

### `local-development/API.md` — the contract

<!-- block: local-development/API.md | edit -->

```markdown
`GET /api/whoami` reports the same decision as a nested object rather than top-level fields:
`"visibility": {"scope": "self", "enabled": true}`. `enabled` is the operator's switch
(`GSD_ENABLE_VIEW_RESTRICTIONS`), not the outcome for this reader.
```

```markdown
`GET /api/whoami` reports the same decision as a nested object rather than top-level fields:
`"visibility": {"scope": "self", "enabled": true, "clusters": {...}, "cluster_admin": false}`.
`enabled` is the operator's switch (`GSD_ENABLE_VIEW_RESTRICTIONS`), not the outcome for this
reader; `cluster_admin` is the cluster-admin tier's verdict (#322, below), which the page reads to
render or withhold the KPI and Cluster Configurations tabs.

**The cluster-admin tier is the top tier (#322).** A reader who passes `visibility.clusterAdminSar`
(default `update clusterrolebindings`, asked on the host whatever `visibility.enabled` says) is
`scope: all` on the host and on every `inherit` cluster, and `all` on `/api/dashboard/activity` and
`/api/dashboard/reports`, whatever `adminSar` and `usageAdminSar` answer for them — one way only. A
`remote-sar` cluster still asks its own API about them; a `self-only` cluster stays `self`.
```

<!-- block: local-development/API.md | edit -->

```markdown
**`bindings/findings`, `operator-configs`, `kyverno` and `kpi` are the administrator tier** (`403` at self); **`clusterconfigs` is stricter still — `clusterconfig:view`, below.** The
```

```markdown
**`bindings/findings`, `operator-configs` and `kyverno` are the administrator tier** (`403` at self); **`kpi` and `clusterconfigs` are the cluster-admin tier (#322), below.** The
```

<!-- block: local-development/API.md | edit -->

```markdown
**`clusterconfig:view`, not the administrator tier.** The cluster-configuration tier is two levels of
its own (#230), modelled on Argo CD's first-class `clusters` resource and asked natively as
SubjectAccessReviews about the Secrets this surface exposes: **`clusterconfig:view`** (`get secrets` in
the dashboard's namespace, chart `visibility.clusterConfigViewSar`) gates this route and, at #230 S2,
the tab's existence; **`clusterconfig:manage`** (`create secrets`, `visibility.clusterConfigManageSar`)
gates S2's write routes. The two are asked separately — `manage` never implies `view` — and both fail
closed. This is deliberately **stricter than the administrator tier**, which the auditor persona
(`cluster-reader`) passes by design: measured on CRC 2026-09-20, that ClusterRole has zero of its 172
rules covering `secrets`, so the auditor fails both levels and a cluster-admin passes both. A refusal
names the control and no cluster, Secret or namespace.
```

```markdown
**The cluster-admin tier (#322), not the administrator tier.** One SubjectAccessReview —
`visibility.clusterAdminSar`, default `update clusterrolebindings.rbac.authorization.k8s.io` on the
host, asked whatever `visibility.enabled` says — gates this route, the tab's existence (through
`/api/whoami`'s `visibility.cluster_admin`) and the four write routes below; `can.manage` is `true`
for whoever reaches it, the deployment's `secrets.writes` switch permitting. Deliberately **stricter
than the administrator tier**, which the auditor persona (`cluster-reader`) passes by design: that
persona fails `update clusterrolebindings` and a cluster-admin passes it (measured on CRC), while the
`get`/`create secrets` pair this replaced (#230, `clusterconfig:view`/`manage`) admitted anyone holding
`admin` or `edit` in the release namespace. A refusal leads with *For cluster administrators only.*
and names no cluster, Secret or namespace.
```

<!-- block: local-development/API.md | edit -->

```markdown
Four routes, all `clusterconfig:manage` (above — never the wide tier) and each needing a proxy-verified
```

```markdown
Four routes, all the cluster-admin tier (above — never the wide tier) and each needing a proxy-verified
```

<!-- block: local-development/API.md | edit -->

```markdown
The KPI module's in-app surface (#156): every KPI definition rendered as JSON, the 30-day trends,
the daily rollup's series, and both processes' self-reported system usage. **Administrator tier**
(`403` at self): the `internal` class counts people, and the trends aggregate the fleet's churn
and logins — governance data about the clusters, not about the reader.
```

```markdown
The KPI module's in-app surface (#156): every KPI definition rendered as JSON, the 30-day trends,
the daily rollup's series, and both processes' self-reported system usage. **Cluster-admin tier**
(#322; `403` below it, the auditor persona included, whatever `visibility.enabled` says): the
`internal` class counts people, and the trends aggregate the fleet's churn and logins — governance
data about the clusters, not about the reader. The refusal leads with *For cluster administrators
only.*
```

### `docs/SPEC_usage_admin_tier.md` — the record

<!-- block: docs/SPEC_usage_admin_tier.md | after: # Spec: a second, stricter tier for the Usage tab -->

```markdown

> 2026-09-25 (#322, `docs/specs/SPEC_T2_cluster_admin_tier.md`): the question this spec measured is also
> the default of the cluster-admin tier, `visibility.clusterAdminSar`, as its own setting. That tier is
> the top tier: a reader who passes it is wide on Usage whatever `usageAdminSar` answers, and with
> `visibility.enabled: false` too. The Usage tier itself is unchanged.
```

### Tests — the existing files

<!-- block: local-development/tests/test_metrics.py | edit -->

```python
        # The cluster-configuration tier's two levels (#230) are thresholds like the others, so a
        # check neither of them has ever run still reports 0 rather than being absent.
        assert found[
            'gsd_visibility_tier_checks_total{outcome="denied",threshold="clusterconfig_view"}'] == 0
        assert found[
            'gsd_visibility_tier_checks_total{outcome="allowed",threshold="clusterconfig_manage"}'] == 0
        # Named, not counted: a bare number says nothing about WHICH threshold went missing, and
        # this assertion is the one that catches a new resolver whose label was never pre-seeded.
        assert {label.split('threshold="')[1].rstrip('"}') for label in found} == {
            "admin", "usage", "clusterconfig_view", "clusterconfig_manage"}
        assert len(found) == 4 * 6, "4 thresholds x 6 outcomes, nothing else"
```

```python
        # The cluster-admin tier (#322) is a threshold like the others, so a check it has never run
        # still reports 0 rather than being absent; the two labels of the tier it replaced are gone.
        assert found[
            'gsd_visibility_tier_checks_total{outcome="denied",threshold="cluster_admin"}'] == 0
        assert not any("clusterconfig_" in label for label in found), "the #230 labels were replaced"
        # Named, not counted: a bare number says nothing about WHICH threshold went missing, and
        # this assertion is the one that catches a new resolver whose label was never pre-seeded.
        assert {label.split('threshold="')[1].rstrip('"}') for label in found} == {
            "admin", "usage", "cluster_admin"}
        assert len(found) == 3 * 6, "3 thresholds x 6 outcomes, nothing else"
```

<!-- block: local-development/tests/test_activity.py | edit -->

```python
                "visibility": {"scope": "self", "enabled": True, "clusters": {}},
                # The Cluster Configurations tier (#230), also on whoami so the tab's very
                # existence can be decided before any request for it. Fails closed here for the
                # same reason the tier above does: no cluster, so no review to pass.
                "clusterconfig": {"view": False, "manage": False},
            }
```

```python
                # `cluster_admin` is the cluster-admin tier (#322), on whoami so the KPI and Cluster
                # Configurations tabs' very existence can be decided before any request for them.
                # Fails closed here for the same reason the scope does: no cluster, so no review to pass.
                "visibility": {"scope": "self", "enabled": True, "clusters": {}, "cluster_admin": False},
            }
```

<!-- block: local-development/tests/test_dashboard_controller.py | edit -->

```python
                   for name in ("tier_resolver", "usage_tier_resolver",
                                "clusterconfig_view_resolver", "clusterconfig_manage_resolver")}
```

```python
                   for name in ("tier_resolver", "usage_tier_resolver", "cluster_admin_resolver")}
```

<!-- block: local-development/tests/test_dashboard_controller.py | edit -->

```python
        app.state.clusterconfig_view_resolver = _MapResolver({"root": "all"})
        app.state.clusterconfig_manage_resolver = _MapResolver({"root": "all"})
```

```python
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
```

<!-- block: local-development/tests/test_remote_sar_default.py | edit -->

```python
                        run_poller=False, tier_resolver=lambda v: "all",
                        clusterconfig_view_resolver=lambda v: "all", clusterconfig_manage_resolver=lambda v: "all")
```

```python
                        run_poller=False, tier_resolver=lambda v: "all", cluster_admin_resolver=lambda v: "all")
```

<!-- block: local-development/tests/test_kpi.py | edit -->

```python
    app = build_app(_settings(db), run_poller=False)
    app.state.tier_resolver = _MapResolver({"root": "all"})
    with TestClient(app) as c:
        yield c
```

```python
    app = build_app(_settings(db), run_poller=False)
    app.state.tier_resolver = _MapResolver({"root": "all"})
    app.state.cluster_admin_resolver = _MapResolver({"root": "all"})   # /api/kpi is the cluster-admin tier (#322)
    with TestClient(app) as c:
        yield c
```

<!-- block: local-development/tests/test_kpi.py | edit -->

```python
        app = build_app(_settings(db, grafana_url="https://g.example", kpi_disk_warn_percent=70.0), run_poller=False)
        app.state.tier_resolver = _MapResolver({"root": "all"})
```

```python
        app = build_app(_settings(db, grafana_url="https://g.example", kpi_disk_warn_percent=70.0), run_poller=False)
        app.state.tier_resolver = _MapResolver({"root": "all"})
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
```

<!-- block: local-development/tests/test_kpi.py | edit -->

```python
        app = build_app(_settings(db), run_poller=False)
        app.state.tier_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as client:
            seeded = client.get("/api/kpi", headers=H("root")).json()["kpis"]["membership_added_30d"]["samples"][0]["value"]
```

```python
        app = build_app(_settings(db), run_poller=False)
        app.state.tier_resolver = _MapResolver({"root": "all"})
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as client:
            seeded = client.get("/api/kpi", headers=H("root")).json()["kpis"]["membership_added_30d"]["samples"][0]["value"]
```

<!-- block: local-development/tests/test_kpi.py | edit -->

```python
        app = build_app(_settings(db, console_url="https://console.example"), run_poller=False)
        app.state.tier_resolver = _MapResolver({"root": "all"})
```

```python
        app = build_app(_settings(db, console_url="https://console.example"), run_poller=False)
        app.state.tier_resolver = _MapResolver({"root": "all"})
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
```

<!-- block: local-development/tests/test_kpi.py | edit -->

```python
        app = build_app(_settings(db), run_poller=False)
        app.state.tier_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as client:
            assert "observe" not in client.get("/api/kpi", headers=H("root")).json()["links"], "nothing discovered yet: no dead link"
```

```python
        app = build_app(_settings(db), run_poller=False)
        app.state.tier_resolver = _MapResolver({"root": "all"})
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as client:
            assert "observe" not in client.get("/api/kpi", headers=H("root")).json()["links"], "nothing discovered yet: no dead link"
```

<!-- block: local-development/tests/test_kpi.py | edit -->

```python
        app2.state.tier_resolver = _MapResolver({"root": "all"})
```

```python
        app2.state.tier_resolver = _MapResolver({"root": "all"})
        app2.state.cluster_admin_resolver = _MapResolver({"root": "all"})
```

<!-- block: local-development/tests/test_kpi.py | edit -->

```python
            app = build_app(_settings(str(tmp_path / "w.db"), grafana_route_selector="k=v"), run_poller=False)
            app.state.tier_resolver = _MapResolver({"root": "all"})
```

```python
            app = build_app(_settings(str(tmp_path / "w.db"), grafana_route_selector="k=v"), run_poller=False)
            app.state.tier_resolver = _MapResolver({"root": "all"})
            app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
```

<!-- block: local-development/tests/test_visibility_tier.py | edit -->

```python
        assert app.state.tier_resolver is not app.state.usage_tier_resolver
        assert app.state.tier_resolver._cache is not app.state.usage_tier_resolver._cache

        reviews = {"n": 0}
```

```python
        assert app.state.tier_resolver is not app.state.usage_tier_resolver
        assert app.state.tier_resolver._cache is not app.state.usage_tier_resolver._cache
        # The cluster-admin tier is consulted first on both routes (#322); held at self here so the
        # reviews counted below are the two resolvers under test and nothing else.
        app.state.cluster_admin_resolver = type("Self", (), {"resolve": staticmethod(lambda viewer: "self")})()

        reviews = {"n": 0}
```

<!-- block: local-development/tests/test_clusterconfig.py | edit -->

```python
        # The read route is gated on clusterconfig:view, NOT the wide tier (#230, the operator's
        # ruling of 2026-09-20): the wide tier admits the auditor persona by design.
        app.state.clusterconfig_view_resolver = _MapResolver({"root": "all"})
        app.state.clusterconfig_manage_resolver = _MapResolver({"root": "all"})
```

```python
        # The read route is gated on the cluster-admin tier, NOT the wide tier (#230, #322): the
        # wide tier admits the auditor persona by design.
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
```

<!-- block: local-development/tests/test_clusterconfig.py | edit -->

```python
class TestClusterConfigTier:
    """The cluster-configuration tier (#230; the operator's ruling of 2026-09-20, "a new tier boss
    — look at how argocd does it").

    Argo CD's RBAC carries a first-class `clusters` resource with `get` and `create/update/delete`
    actions; ours is the same two levels asked natively as SubjectAccessReviews about the objects
    this surface exposes — `get secrets` for view, `create secrets` for manage, in the dashboard's
    own namespace.

    WHY NOT THE WIDE TIER, measured on CRC 2026-09-20: `oc get clusterrole cluster-reader -o json`
    has ZERO of its 172 rules covering core/`secrets` and `oc auth can-i {get,list,create,update,
    delete} secrets` answers `no` — while that same cluster-reader, the deliberate auditor persona,
    PASSES the wide tier by design (see api.usage_scope). Gating this surface on the wide tier would
    hand the auditor the fleet's wiring, and at S2 the writes that change it.
    """

    @pytest.fixture
    def make_app(self, tmp_path):
        """A FACTORY, not one app: each case gets its own store, because a TestClient's exit
        closes it and these cases need several clients."""
        seq = iter(range(100))

        def _make(view=None, manage=None):
            db = str(tmp_path / f"gsd{next(seq)}.db"); _seed(db)
            settings = _settings(db)
            settings.cluster_registry.namespace = "ns"
            settings.cluster_registry.replace(
                [parse_secret(_secret(), host_name="c1")], [], at="2026-09-20T16:05:12Z")
            app = build_app(settings, run_poller=False)
            # Everyone passes the WIDE tier here, auditor included — exactly the live situation
            # this gate exists for, so a passing test cannot be passing for the wrong reason.
            app.state.tier_resolver = _MapResolver({"root": "all", "auditor": "all", "viewer": "all"})
            app.state.remote_tier_resolvers = {}   # the discovered east is remote-sar (SPEC_D2b); no remote is asked
            app.state.clusterconfig_view_resolver = view
            app.state.clusterconfig_manage_resolver = manage
            return app

        return _make

    def test_the_auditor_passes_the_wide_tier_and_is_still_refused_with_no_cluster_named(self, make_app):
        app = make_app(view=_MapResolver({"root": "all"}), manage=_MapResolver({"root": "all"}))
        with TestClient(app) as c:
            # the same persona the wide tier admits
            assert c.get("/api/clusters", headers=H("auditor")).status_code == 200
            refused = c.get("/api/clusterconfigs", headers=H("auditor"))
            assert refused.status_code == 403
            body = refused.json()["detail"]
            assert "cluster-configuration administrators" in body
            # the refusal names no cluster, no Secret and no namespace: it reaches the refused
            # person, and a sentence that named the Secret would be a map for the next attempt.
            # Whole words: "ns" lives inside "instance", which is not a leak.
            words = set(re.findall(r"[A-Za-z0-9_.-]+", body))
            assert not words & {"c1", "east", "ns", "gsd-cluster-east", "secrets"}
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 200

    def test_view_and_manage_are_asked_separately_and_manage_does_not_imply_view(self, make_app):
        # A site may grant the two apart: passing manage alone must NOT open the read route.
        app = make_app(view=_MapResolver({"root": "all"}),
                       manage=_MapResolver({"root": "all", "manager": "all"}))
        with TestClient(app) as c:
            assert c.get("/api/clusterconfigs", headers=H("manager")).status_code == 403
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 200

    def test_it_fails_closed_on_no_resolver_no_identity_and_an_exploding_check(self, make_app):
        """Argo's `policy.default: deny` in our vocabulary — a surface naming cluster credentials
        must not widen because a SubjectAccessReview blipped.

        The no-resolver case leaves the seam None, so the resolver build_app made against the
        configured cluster answers: it cannot reach one, reports `auth_failed`, and the gate
        refuses — the live shape of "the check did not come back"."""
        class _Explodes:
            def resolve(self, viewer):
                raise RuntimeError("the API server said no such luck")

        with TestClient(make_app(view=None)) as c:
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 403
        with TestClient(make_app(view=_MapResolver({"root": "all"}))) as c:
            assert c.get("/api/clusterconfigs").status_code == 403          # no identity
        with TestClient(make_app(view=_Explodes())) as c:
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 403

    def test_the_wide_tier_alone_never_opens_it_the_mutant_this_kills(self, make_app):
        """The mutant: gating the route on `require_admin_tier` again. Everyone here passes the
        wide tier, so that revert makes this assertion fail."""
        app = make_app(view=_MapResolver({}))    # nobody passes the new tier
        with TestClient(app) as c:
            for who in ("root", "auditor", "viewer"):
                assert c.get("/api/clusterconfigs", headers=H(who)).status_code == 403

    def test_restrictions_off_does_not_open_the_surface(self, tmp_path):
        """`visibility.enabled=false` must not, as a side effect, hand the auditor the wiring.

        The wide views widen in that state by design — the deployment has said it trusts everyone
        its proxy admits for cluster DATA. This surface is not cluster data: it says how the fleet
        is wired. Usage made the same call (usage_scope stays self); we go further and still ask,
        so a cluster-admin keeps the tab (review of #235, Grok C2)."""
        db = str(tmp_path / "off.db"); _seed(db)
        # BOTH widening switches at once: `visibility.enabled=false` widens the wide views, and
        # `userActivity.visibility: all` widens Usage for every viewer. Neither is a statement about
        # who may read this namespace's Secrets, so neither may widen this tier.
        settings = _settings(db, view_restrictions_enabled=False, user_activity_visibility="all")
        settings.cluster_registry.namespace = "ns"
        settings.cluster_registry.replace(
            [parse_secret(_secret(), host_name="c1")], [], at="2026-09-20T16:05:12Z")
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _MapResolver({"auditor": "all", "root": "all"})
        app.state.clusterconfig_view_resolver = _MapResolver({"root": "all"})   # auditor absent
        with TestClient(app) as c:
            assert c.get("/api/clusters", headers=H("auditor")).status_code == 200
            assert c.get("/api/clusterconfigs", headers=H("auditor")).status_code == 403
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 200

    def test_build_app_constructs_two_resolvers_with_two_questions_and_two_caches(self, tmp_path):
        """The share-one-resolver mutant: one instance, its cache keyed by viewer alone, so a
        `view` verdict would answer `manage`. Also pins that construction no longer depends on
        the wide-view switch."""
        db = str(tmp_path / "two.db"); _seed(db)
        app = build_app(_settings(db), run_poller=False)          # no injection: the real path
        v = app.state.clusterconfig_view_resolver
        m = app.state.clusterconfig_manage_resolver
        assert v is not None and m is not None and v is not m
        assert v._attributes["verb"] == "get" and m._attributes["verb"] == "create"
        assert v._attributes["resource"] == "secrets" == m._attributes["resource"]
        assert v._cache is not m._cache

    def test_a_namespace_admin_who_can_create_the_secret_is_admitted(self, make_app):
        """Each level asks ITS OWN question and nothing else (the operator's ruling of 2026-09-20,
        reversing an earlier ordering).

        A reader who passes `create secrets` in this namespace — a namespace admin, say — can write
        the cluster Secret with `oc` whether or not the dashboard lets them; refusing them in the UI
        protects nothing, and because the gate IS the action's own question the ServiceAccount that
        performs the write is not acting beyond what the asker could do. RBAC is additive: holding
        the auditor role and a namespace-admin grant is not a contradiction to resolve.

        What still excludes the auditor is the plain question, measured on CRC 2026-09-20 with the
        persona's groups carried (`--as=lateef.o` plus his three groups): `get secrets` no,
        `create secrets` no.
        """
        app = make_app(view=_MapResolver({"root": "all", "nsadmin": "all"}),
                       manage=_MapResolver({"root": "all", "nsadmin": "all"}))
        app.state.tier_resolver = _MapResolver({"root": "all"})       # nsadmin is self on the wide tier
        with TestClient(app) as c:
            assert c.get("/api/clusterconfigs", headers=H("nsadmin")).status_code == 200
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 200

    def test_the_auditor_is_excluded_by_the_plain_question_without_composing_tiers(self, make_app):
        """The operator's ruling — the reporting auditor may neither view nor change this — holds
        with NO composition: the auditor simply fails `get secrets`."""
        app = make_app(view=_MapResolver({"root": "all"}), manage=_MapResolver({"root": "all"}))
        app.state.tier_resolver = _MapResolver({"root": "all", "auditor": "all"})   # wide admits them
        with TestClient(app) as c:
            assert c.get("/api/clusters", headers=H("auditor")).status_code == 200
            assert c.get("/api/clusterconfigs", headers=H("auditor")).status_code == 403

    def test_with_no_proxy_there_is_no_identity_to_ask_about_so_it_refuses(self, tmp_path):
        """The OTHER way the refusal is reached (OB3 F2-residue): with no proxy, `trusted_viewer`
        returns None because an unproxied `X-Forwarded-User` is whatever the caller typed. A surface
        naming cluster credentials must not take an identity on the caller's word."""
        db = str(tmp_path / "noproxy.db"); _seed(db)
        settings = _settings(db, oauth_proxy_enabled=False)
        settings.cluster_registry.namespace = "ns"
        settings.cluster_registry.replace(
            [parse_secret(_secret(), host_name="c1")], [], at="2026-09-20T16:05:12Z")
        app = build_app(settings, run_poller=False)
        app.state.clusterconfig_view_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as c:
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 403

    def test_the_two_levels_have_their_own_defaults_and_caches(self):
        """`manage` is not derived from `view`: separate settings, separate questions."""
        from gsd.config import Settings
        s = Settings(clusters=())
        assert (s.visibility_clusterconfig_view_sar_verb,
                s.visibility_clusterconfig_view_sar_resource) == ("get", "secrets")
        assert (s.visibility_clusterconfig_manage_sar_verb,
                s.visibility_clusterconfig_manage_sar_resource) == ("create", "secrets")
        assert s.visibility_clusterconfig_view_sar_api_group == ""      # the core group
```

```python
class TestClusterAdminTierOnClusterConfigs:
    """The cluster-admin tier on the Cluster Configurations surface (#322, replacing the #230 pair).

    ONE SubjectAccessReview — `update clusterrolebindings` on the host by default — decides the read
    route and the writes alike. WHY NOT THE WIDE TIER: the deliberate auditor persona, cluster-reader,
    PASSES the wide tier by design (see api.usage_scope) and fails this question (measured on CRC:
    `oc auth can-i update clusterrolebindings` → no). Gating this surface on the wide tier would hand
    the auditor the fleet's wiring, and at S2 the writes that change it. The per-surface cases live
    in tests/test_cluster_admin_tier.py; these pin this route's own shapes.
    """

    @pytest.fixture
    def make_app(self, tmp_path):
        """A FACTORY, not one app: each case gets its own store, because a TestClient's exit
        closes it and these cases need several clients."""
        seq = iter(range(100))

        def _make(cluster_admin=None):
            db = str(tmp_path / f"gsd{next(seq)}.db"); _seed(db)
            settings = _settings(db)
            settings.cluster_registry.namespace = "ns"
            settings.cluster_registry.replace(
                [parse_secret(_secret(), host_name="c1")], [], at="2026-09-20T16:05:12Z")
            app = build_app(settings, run_poller=False)
            # Everyone passes the WIDE tier here, auditor included — exactly the live situation
            # this gate exists for, so a passing test cannot be passing for the wrong reason.
            app.state.tier_resolver = _MapResolver({"root": "all", "auditor": "all", "viewer": "all"})
            app.state.remote_tier_resolvers = {}   # the discovered east is remote-sar (SPEC_D2b); no remote is asked
            app.state.cluster_admin_resolver = cluster_admin
            return app

        return _make

    def test_the_auditor_passes_the_wide_tier_and_is_still_refused_with_no_cluster_named(self, make_app):
        app = make_app(cluster_admin=_MapResolver({"root": "all"}))
        with TestClient(app) as c:
            # the same persona the wide tier admits
            assert c.get("/api/clusters", headers=H("auditor")).status_code == 200
            refused = c.get("/api/clusterconfigs", headers=H("auditor"))
            assert refused.status_code == 403
            body = refused.json()["detail"]
            assert body.startswith("For cluster administrators only.")
            # the refusal names no cluster, no Secret and no namespace: it reaches the refused
            # person, and a sentence that named the Secret would be a map for the next attempt.
            # Whole words: "ns" lives inside "instance", which is not a leak.
            words = set(re.findall(r"[A-Za-z0-9_.-]+", body))
            assert not words & {"c1", "east", "ns", "gsd-cluster-east", "secrets", "clusterrolebindings"}
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 200

    def test_one_question_decides_the_whole_tab_so_can_manage_follows_can_view(self, make_app):
        """The #230 pair asked `view` and `manage` apart; one tier means whoever reads may change
        (the deployment's writes switch permitting), and the payload says so."""
        app = make_app(cluster_admin=_MapResolver({"root": "all"}))
        with TestClient(app) as c:
            assert c.get("/api/clusterconfigs", headers=H("root")).json()["can"] == {"view": True, "manage": True}

    def test_it_fails_closed_on_no_resolver_no_identity_and_an_exploding_check(self, make_app):
        """Argo's `policy.default: deny` in our vocabulary — a surface naming cluster credentials
        must not widen because a SubjectAccessReview blipped.

        The no-resolver case leaves the seam None, so the resolver build_app made against the
        configured cluster answers: it cannot reach one, reports `auth_failed`, and the gate
        refuses — the live shape of "the check did not come back"."""
        class _Explodes:
            def resolve(self, viewer):
                raise RuntimeError("the API server said no such luck")

        with TestClient(make_app(cluster_admin=None)) as c:
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 403
        with TestClient(make_app(cluster_admin=_MapResolver({"root": "all"}))) as c:
            assert c.get("/api/clusterconfigs").status_code == 403          # no identity
        with TestClient(make_app(cluster_admin=_Explodes())) as c:
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 403

    def test_the_wide_tier_alone_never_opens_it_the_mutant_this_kills(self, make_app):
        """The mutant: gating the route on `require_admin_tier` again. Everyone here passes the
        wide tier, so that revert makes this assertion fail."""
        app = make_app(cluster_admin=_MapResolver({}))    # nobody passes the tier
        with TestClient(app) as c:
            for who in ("root", "auditor", "viewer"):
                assert c.get("/api/clusterconfigs", headers=H(who)).status_code == 403

    def test_restrictions_off_does_not_open_the_surface(self, tmp_path):
        """`visibility.enabled=false` must not, as a side effect, hand the auditor the wiring.

        The wide views widen in that state by design — the deployment has said it trusts everyone
        its proxy admits for cluster DATA. This surface is not cluster data: it says how the fleet
        is wired. Usage made the same call (usage_scope stays self); we go further and still ask,
        so a cluster-admin keeps the tab (review of #235, Grok C2; kept by #322)."""
        db = str(tmp_path / "off.db"); _seed(db)
        # BOTH widening switches at once: `visibility.enabled=false` widens the wide views, and
        # `userActivity.visibility: all` widens Usage for every viewer. Neither is a statement about
        # who administers this cluster, so neither may widen this tier.
        settings = _settings(db, view_restrictions_enabled=False, user_activity_visibility="all")
        settings.cluster_registry.namespace = "ns"
        settings.cluster_registry.replace(
            [parse_secret(_secret(), host_name="c1")], [], at="2026-09-20T16:05:12Z")
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _MapResolver({"auditor": "all", "root": "all"})
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})   # auditor absent
        with TestClient(app) as c:
            assert c.get("/api/clusters", headers=H("auditor")).status_code == 200
            assert c.get("/api/clusterconfigs", headers=H("auditor")).status_code == 403
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 200

    def test_build_app_constructs_the_resolver_with_its_own_question_and_cache(self, tmp_path):
        """The share-one-resolver mutant: reusing the Usage resolver, whose cache is keyed by viewer
        alone, would let an operator's custom Usage question answer this tier. Also pins that
        construction does not depend on the wide-view switch and asks a cluster-scoped question."""
        db = str(tmp_path / "one.db"); _seed(db)
        app = build_app(_settings(db, view_restrictions_enabled=False), run_poller=False)   # no injection: the real path
        r = app.state.cluster_admin_resolver
        assert r is not None
        assert r._attributes == {"verb": "update", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"}
        assert "namespace" not in r._attributes, "cluster-scoped, like adminSar's empty namespace"
        on = build_app(_settings(str(tmp_path / "on.db")), run_poller=False)
        assert on.state.cluster_admin_resolver is not on.state.usage_tier_resolver
        assert on.state.cluster_admin_resolver._cache is not on.state.usage_tier_resolver._cache

    def test_a_namespace_admin_who_could_create_the_secret_is_now_refused(self, make_app):
        """WHO LOSES ACCESS (#322): the #230 pair admitted whoever passed `create secrets` in the
        release namespace — a namespace admin, `john.doe` with cluster-wide `admin` (measured on
        CRC) — who is not a cluster administrator. The cluster-scoped question refuses them."""
        app = make_app(cluster_admin=_MapResolver({"root": "all"}))   # nsadmin fails `update clusterrolebindings`
        app.state.tier_resolver = _MapResolver({"root": "all"})       # and is self on the wide tier, as measured
        with TestClient(app) as c:
            assert c.get("/api/clusterconfigs", headers=H("nsadmin")).status_code == 403
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 200

    def test_with_no_proxy_there_is_no_identity_to_ask_about_so_it_refuses(self, tmp_path):
        """The OTHER way the refusal is reached (OB3 F2-residue): with no proxy, `trusted_viewer`
        returns None because an unproxied `X-Forwarded-User` is whatever the caller typed. A surface
        naming cluster credentials must not take an identity on the caller's word."""
        db = str(tmp_path / "noproxy.db"); _seed(db)
        settings = _settings(db, oauth_proxy_enabled=False)
        settings.cluster_registry.namespace = "ns"
        settings.cluster_registry.replace(
            [parse_secret(_secret(), host_name="c1")], [], at="2026-09-20T16:05:12Z")
        app = build_app(settings, run_poller=False)
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as c:
            assert c.get("/api/clusterconfigs", headers=H("root")).status_code == 403

    def test_the_tier_has_its_own_default_the_usage_question(self):
        """Its own setting, the same default question as Usage's — and the #230 fields are gone."""
        from gsd.config import Settings
        s = Settings(clusters=())
        assert (s.visibility_cluster_admin_sar_api_group, s.visibility_cluster_admin_sar_resource,
                s.visibility_cluster_admin_sar_verb, s.visibility_cluster_admin_sar_namespace) == (
            "rbac.authorization.k8s.io", "clusterrolebindings", "update", "")
        assert not [f for f in dir(s) if f.startswith("visibility_clusterconfig_")]
```

<!-- block: local-development/tests/test_clusterconfig_tab.py | edit -->

```python
        # The Cluster Configurations tier's own two seams (#230): root holds both levels here, and
        # the tier's tests below drive every other combination.
        app.state.clusterconfig_view_resolver = _MapResolver({"root": "all"})
        app.state.clusterconfig_manage_resolver = _MapResolver({"root": "all"})
```

```python
        # The cluster-admin tier's own seam (#322): root holds it here, and the tier's tests below
        # drive every other persona.
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
```

<!-- block: local-development/tests/test_clusterconfig_tab.py | edit -->

```python
        app.state.tier_resolver = _MapResolver({"root": "all"})
        app.state.clusterconfig_view_resolver = _MapResolver({"root": "all"})
        app.state.clusterconfig_manage_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as c:
            # a POST on the read path is a 405 (the path exists for GET); the write-only paths are 404s — routes that
```

```python
        app.state.tier_resolver = _MapResolver({"root": "all"})
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as c:
            # a POST on the read path is a 405 (the path exists for GET); the write-only paths are 404s — routes that
```

<!-- block: local-development/tests/test_clusterconfig_tab.py | edit -->

```python
        app.state.remote_tier_resolvers = {}   # the discovered east is remote-sar (SPEC_D2b); no remote is asked
        app.state.clusterconfig_view_resolver = _MapResolver({"root": "all", "viewer": "all"})
        app.state.clusterconfig_manage_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as c:
            yield c
```

```python
        app.state.remote_tier_resolvers = {}   # the discovered east is remote-sar (SPEC_D2b); no remote is asked
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})   # one tier for the whole tab (#322)
        with TestClient(app) as c:
            yield c
```

<!-- block: local-development/tests/test_clusterconfig_tab.py | edit -->

```python
        who = rig.get("/api/whoami", headers=H("auditor")).json()
        assert who["clusterconfig"] == {"view": False, "manage": False}      # no tab for this reader

    def test_view_without_manage_reads_the_surface_and_changes_nothing(self, rig):
        body = rig.get("/api/clusterconfigs", headers=H("viewer")).json()
        assert body["can"] == {"view": True, "manage": False}
        assert [c["id"] for c in body["clusters"]]                            # the cards are there to read
        assert [r.status_code for r in self._writes(rig, "viewer")] == [403, 403, 403, 403]
        assert rig.get("/api/whoami", headers=H("viewer")).json()["clusterconfig"] == {"view": True, "manage": False}

    def test_whoami_answers_manage_from_its_own_question_for_a_manage_only_reader(self, rig):
        """Round 2 (OB2 C4): `manage` was derived `false` whenever `view` was — a composition the ruling
        forbids — so the strip and the write routes disagreed for a reader granted `create secrets`
        without `get secrets`. Each level is its own answer; the page still shows no control without
        the page."""
        rig.app.state.clusterconfig_view_resolver = _MapResolver({"root": "all", "viewer": "all"})
        rig.app.state.clusterconfig_manage_resolver = _MapResolver({"root": "all", "writer": "all"})
        assert rig.get("/api/whoami", headers=H("writer")).json()["clusterconfig"] == {"view": False, "manage": True}
        assert rig.get("/api/clusterconfigs", headers=H("writer")).status_code == 403
        assert rig.post("/api/clusterconfigs/test", json=self.BODY, headers=H("writer")).status_code == 200

    def test_the_administrator_holds_both_levels(self, rig):
        assert rig.get("/api/clusterconfigs", headers=H("root")).json()["can"] == {"view": True, "manage": True}
        assert rig.get("/api/whoami", headers=H("root")).json()["clusterconfig"] == {"view": True, "manage": True}
        assert rig.post("/api/clusterconfigs/test", json=self.BODY, headers=H("root")).status_code == 200
```

```python
        who = rig.get("/api/whoami", headers=H("auditor")).json()
        assert who["visibility"]["cluster_admin"] is False                   # no tab for this reader

    def test_a_reader_the_wide_tier_admits_but_the_tier_refuses_gets_nothing_here(self, rig):
        """`viewer` passes the wide tier and fails the cluster-admin one — the #230 view-only level
        no longer exists (#322): one question decides the read route and the writes alike."""
        assert rig.get("/api/clusterconfigs", headers=H("viewer")).status_code == 403
        assert [r.status_code for r in self._writes(rig, "viewer")] == [403, 403, 403, 403]
        assert rig.get("/api/whoami", headers=H("viewer")).json()["visibility"]["cluster_admin"] is False

    def test_the_administrator_holds_the_tier_and_may_read_and_write(self, rig):
        assert rig.get("/api/clusterconfigs", headers=H("root")).json()["can"] == {"view": True, "manage": True}
        assert rig.get("/api/whoami", headers=H("root")).json()["visibility"]["cluster_admin"] is True
        assert rig.post("/api/clusterconfigs/test", json=self.BODY, headers=H("root")).status_code == 200
```

<!-- block: local-development/tests/test_clusterconfig_tab.py | edit -->

```python
    def test_the_pure_auditor_persona_is_refused_by_the_questions_themselves(self, rig):
        """The operator's rule (2026-09-20): each level gates on its OWN SAR alone — no composition with
        the administrator question, because RBAC is additive and whoever passes `get`/`create secrets`
        can do the same with `oc`. The "no auditor" ruling survives by MEASUREMENT: the chart's auditor
        role carries no rule over `secrets`, so the pure auditor answers no to both questions. Here the
        auditor holds the wide tier and neither cluster-config level — exactly that shape."""
        assert rig.get("/api/clusterconfigs", headers=H("auditor")).status_code == 403
        assert [r.status_code for r in self._writes(rig, "auditor")] == [403, 403, 403, 403]
        assert rig.get("/api/whoami", headers=H("auditor")).json()["clusterconfig"] == {"view": False, "manage": False}
```

```python
    def test_the_pure_auditor_persona_is_refused_by_the_question_itself(self, rig):
        """The "no auditor" ruling survives by MEASUREMENT (#322): cluster-reader passes the wide tier
        and fails `update clusterrolebindings`, so the auditor answers no to the one question. Here
        the auditor holds the wide tier and not the cluster-admin tier — exactly that shape."""
        assert rig.get("/api/clusterconfigs", headers=H("auditor")).status_code == 403
        assert [r.status_code for r in self._writes(rig, "auditor")] == [403, 403, 403, 403]
        assert rig.get("/api/whoami", headers=H("auditor")).json()["visibility"]["cluster_admin"] is False
```

<!-- block: local-development/tests/test_clusterconfig_tab.py | edit -->

```python
            assert c.get("/api/whoami", headers=H("anyone")).json().get("clusterconfig", {"view": False})["view"] is False

    def test_no_resolver_fails_closed(self, rig):
        """Argo's `policy.default: deny`: an instance that built no resolver — restrictions off, or no
        host cluster to review against — refuses rather than falling back to the wide tier."""
        rig.app.state.clusterconfig_view_resolver = None
        rig.app.state.clusterconfig_manage_resolver = None
        assert rig.get("/api/clusterconfigs", headers=H("root")).status_code == 403
        assert [r.status_code for r in self._writes(rig, "root")] == [403, 403, 403, 403]
```

```python
            assert c.get("/api/whoami", headers=H("anyone")).json()["visibility"]["cluster_admin"] is False

    def test_no_resolver_fails_closed(self, rig):
        """Argo's `policy.default: deny`: an instance that built no resolver — no host cluster to
        review against — refuses rather than falling back to the wide tier."""
        rig.app.state.cluster_admin_resolver = None
        assert rig.get("/api/clusterconfigs", headers=H("root")).status_code == 403
        assert [r.status_code for r in self._writes(rig, "root")] == [403, 403, 403, 403]
```

<!-- block: local-development/tests/test_chart_strategy.py | edit -->

```python
    # ── The cluster-configuration tier's two levels (#230) ────────────────────────────

    def test_the_clusterconfig_sar_defaults_reach_the_configmap(self):
        """view = `get secrets`, manage = `create secrets`, both in this release's namespace (an
        empty namespace means the pod's own for these two, unlike adminSar's cluster-scoped empty)."""
        ok, out = render()
        assert ok, out
        cm = self._configmap(out)
        assert cm["visibilityClusterConfigViewSarApiGroup"] == ""        # the core group
        assert cm["visibilityClusterConfigViewSarResource"] == "secrets"
        assert cm["visibilityClusterConfigViewSarVerb"] == "get"
        assert cm["visibilityClusterConfigManageSarResource"] == "secrets"
        assert cm["visibilityClusterConfigManageSarVerb"] == "create"
        assert cm["visibilityClusterConfigViewSarNamespace"] == ""
        assert cm["visibilityClusterConfigManageSarNamespace"] == ""

    def test_a_nilled_clusterconfig_block_keeps_its_own_default_and_does_not_move_the_other(self):
        """Commenting the sub-keys out leaves the block present-but-nil. Each level falls back to
        ITS OWN default — the two are separate questions, so a nilled view must not drag manage's
        verb with it, and never to an empty (allowed=false) check."""
        for nilled, other in (("clusterConfigViewSar", "clusterConfigManageSar"),
                              ("clusterConfigManageSar", "clusterConfigViewSar")):
            ok, out = render(**{f"visibility.{nilled}": "null"})
            assert ok, out
            cm = self._configmap(out)
            assert cm["visibilityClusterConfigViewSarVerb"] == "get"
            assert cm["visibilityClusterConfigManageSarVerb"] == "create"
            assert cm[f"visibility{other[0].upper()}{other[1:]}Resource".replace("Sar", "Sar")] == "secrets"

    def test_a_nonsensical_clusterconfig_sar_shape_is_refused(self):
        """A miscased or versioned field would answer no for every viewer — which here does not
        demote an administrator but closes the surface to everyone, including whoever would fix it.
        So it fails the render, with the field named and the reason said."""
        for block in ("clusterConfigViewSar", "clusterConfigManageSar"):
            for key, bad in (("verb", "Get"), ("resource", "Secrets"),
                             ("apiGroup", "rbac.authorization.k8s.io/v1"), ("namespace", "Bad_NS")):
                ok, out = render(**{f"visibility.{block}.{key}": bad})
                assert not ok, f"{block}.{key}={bad!r} rendered happily"
                assert f"visibility.{block}.{key}" in out
                assert "RBAC matching is exact" in out

    def test_the_sar_grant_renders_for_the_clusterconfig_tier_even_with_visibility_off(self):
        """The cluster-configuration tier asks a SubjectAccessReview regardless of
        `visibility.enabled` — that independence is the point of it. Without the auth-delegator
        binding in that state every review errors and the surface refuses EVERYONE, administrators
        included, with only a log line to say why (review of #235, the Fable seat)."""
```

```python
    # ── The cluster-admin tier (#322) ─────────────────────────────────────────────────

    def test_the_cluster_admin_sar_defaults_reach_the_configmap(self):
        """`update clusterrolebindings`, cluster-scoped — the Usage question as its own setting —
        and the #230 pair's eight keys are gone."""
        ok, out = render()
        assert ok, out
        cm = self._configmap(out)
        assert cm["visibilityClusterAdminSarApiGroup"] == "rbac.authorization.k8s.io"
        assert cm["visibilityClusterAdminSarResource"] == "clusterrolebindings"
        assert cm["visibilityClusterAdminSarVerb"] == "update"
        assert cm["visibilityClusterAdminSarNamespace"] == ""
        assert not [k for k in cm if k.startswith("visibilityClusterConfig")], "the #230 keys were replaced"

    def test_a_nilled_cluster_admin_block_keeps_the_default(self):
        """Commenting the sub-keys out leaves the block present-but-nil: the default question, never
        an empty (allowed=false) check."""
        ok, out = render(**{"visibility.clusterAdminSar": "null"})
        assert ok, out
        cm = self._configmap(out)
        assert (cm["visibilityClusterAdminSarVerb"], cm["visibilityClusterAdminSarResource"]) == ("update", "clusterrolebindings")

    def test_a_nonsensical_cluster_admin_sar_shape_is_refused(self):
        """A miscased or versioned field would answer no for every viewer — which here does not
        demote an administrator but closes two surfaces to everyone, including whoever would fix it.
        So it fails the render, with the field named and the reason said."""
        for key, bad in (("verb", "Update"), ("resource", "ClusterRoleBindings"),
                         ("apiGroup", "rbac.authorization.k8s.io/v1"), ("namespace", "Bad_NS")):
            ok, out = render(**{f"visibility.clusterAdminSar.{key}": bad})
            assert not ok, f"clusterAdminSar.{key}={bad!r} rendered happily"
            assert f"visibility.clusterAdminSar.{key}" in out
            assert "RBAC matching is exact" in out

    def test_the_removed_clusterconfig_blocks_are_refused_by_name(self):
        """`visibility.clusterConfigViewSar` / `.clusterConfigManageSar` were removed in chart 0.57.0
        (#322). Helm ignores a key no template reads, so a values file that still sets one would
        render clean while its question silently stopped being asked. Set — any field — it fails
        the render with a message naming `clusterAdminSar`; a block that sets nothing (nulled, the
        sub-keys commented out) asks no question and passes — Helm KEEPS such a key when the chart's
        defaults no longer carry it, so this case fails a presence test (Grok's review of SPEC_T2, C7)."""
        for block in ("clusterConfigViewSar", "clusterConfigManageSar"):
            for key, value in (("verb", "get"), ("namespace", "ns")):
                ok, out = render(**{f"visibility.{block}.{key}": value})
                assert not ok, f"{block}.{key}={value!r} rendered happily"
                assert f"visibility.{block} was removed" in out and "visibility.clusterAdminSar" in out
            ok, out = render(**{f"visibility.{block}": "null"})
            assert ok, out

    def test_the_sar_grant_renders_for_the_cluster_admin_tier_even_with_visibility_off(self):
        """The cluster-admin tier asks a SubjectAccessReview regardless of `visibility.enabled` —
        that independence is the point of it (#322, as for the #230 tier before it). Without the
        auth-delegator binding in that state every review errors and both surfaces refuse EVERYONE,
        administrators included, with only a log line to say why (review of #235, the Fable seat)."""
```

<!-- block: local-development/tests/test_chart_strategy.py | edit -->

```python
    def test_the_sar_grant_disappears_when_nothing_needs_it(self):
        """The invariant: the grant renders only when something asks a SubjectAccessReview. Every
        user of it must therefore be named here — apiTokenAccess (on by default since chart 0.14.0)
        and, since #230, the cluster-configuration tier, which asks regardless of visibility."""
        ok, out = render(visibility__enabled="false", oauthProxy__apiTokenAccess__enabled="false",
                         clusterConfig__secrets__enabled="false")
        assert ok, out
        assert not any(d.get("kind") == "ClusterRoleBinding"
                       and d["roleRef"]["name"] == "system:auth-delegator"
                       for d in self._docs(out)), (
            "with visibility off, apiTokenAccess off and cluster Secrets off, nothing uses the SAR grant"
        )
```

```python
    def test_the_sar_grant_renders_whenever_the_proxy_is_on(self):
        """The cluster-admin tier (#322) asks a SubjectAccessReview for the KPI page, which every
        install has, whatever `visibility.enabled`, apiTokenAccess or cluster Secrets say. With all
        three off the grant used to be absent, and KPI would have refused everyone (Grok's review of
        SPEC_T2, C9)."""
        ok, out = render(visibility__enabled="false", oauthProxy__apiTokenAccess__enabled="false",
                         clusterConfig__secrets__enabled="false")
        assert ok, out
        assert any(d.get("kind") == "ClusterRoleBinding"
                   and d["roleRef"]["name"] == "system:auth-delegator"
                   for d in self._docs(out)), "the cluster-admin tier would ask a review it has no grant for"

    def test_the_sar_grant_disappears_only_with_the_proxy_off(self):
        """With the proxy off there is no verified identity, so nothing asks a review
        (`trusted_viewer` is None) and the grant is not rendered."""
        ok, out = render(oauthProxy__enabled="false", visibility__enabled="false",
                         reporting__enabled="false")
        assert ok, out
        assert not any(d.get("kind") == "ClusterRoleBinding"
                       and d["roleRef"]["name"] == "system:auth-delegator"
                       for d in self._docs(out))
```

<!-- block: local-development/tests/test_chart_strategy.py | edit -->

```python
        the both-off state that removes it is `test_the_sar_grant_disappears_when_nothing_needs_it`."""
```

```python
        the only state that removes it is the proxy off, `test_the_sar_grant_disappears_only_with_the_proxy_off`."""
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
        # scoped_server fixture below, where restrictions stay on.
        view_restrictions_enabled=False,
    )
    port = _free_port()
    app = build_app(settings, run_poller=False)
```

```python
        # scoped_server fixture below, where restrictions stay on.
        view_restrictions_enabled=False,
        # The proxy is ON, with no header sent by default, so whoami is what it always was here
        # (`authenticated: false`) — and a test that needs the KPI page, the cluster-admin tier
        # (#322), sends `root` through _as_cluster_admin. Without the proxy there is no identity to
        # ask about and no rig can reach that page.
        oauth_proxy_enabled=True,
    )
    port = _free_port()
    app = build_app(settings, run_poller=False)
    app.state.cluster_admin_resolver = _TierByName()   # root
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
@pytest.fixture()
def dash(page, server):
```

```python
def _as_cluster_admin(page):
    """Reload the page as `root`, the cluster-admin persona of the `server` rig (#322). The KPI tab
    is drawn from whoami, so the header must be on the request that loads the page, not the next
    poll; the tab is what says the reload landed."""
    page.set_extra_http_headers({"X-Forwarded-User": "root"})
    page.reload()
    page.wait_for_selector("#tab-kpi", timeout=10_000)
    return page


@pytest.fixture()
def dash(page, server):
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
        dash.locator("button[data-nav='kpi']").click()
```

```python
        _as_cluster_admin(dash).locator("button[data-nav='kpi']").click()
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
    @pytest.mark.parametrize("tab", TABS)
    def test_no_horizontal_overflow_and_every_tab_inside_the_viewport(self, dash, tab):
        dash.set_viewport_size({"width": 375, "height": 740})
        dash.click(f"#tab-{tab}")
```

```python
    @pytest.mark.parametrize("tab", TABS)
    def test_no_horizontal_overflow_and_every_tab_inside_the_viewport(self, dash, tab):
        if tab == "kpi":
            _as_cluster_admin(dash)     # the cluster-admin tier's tab (#322)
        dash.set_viewport_size({"width": 375, "height": 740})
        dash.click(f"#tab-{tab}")
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
    def _open(self, dash):
        dash.click("#tab-kpi")
        dash.wait_for_selector(".kpi-page .kband .kpi", timeout=10_000)
        return dash
```

```python
    def _open(self, dash):
        _as_cluster_admin(dash)         # the KPI page is the cluster-admin tier (#322)
        dash.click("#tab-kpi")
        dash.wait_for_selector(".kpi-page .kband .kpi", timeout=10_000)
        return dash
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
        p.evaluate("""() => {
          data.whoami.visibility.scope = "self";
          data.whoami.visibility.clusters = Object.assign({}, data.whoami.visibility.clusters,
            { west: { policy: "remote-sar", identity: "same-as-host", scope: "all" } });
          data.clusters = (data.clusters || []).concat([{ id: "west", visibility: { policy: "remote-sar", scope: "all" } }]);
          view.cluster = "west"; data.kpi = null; render();
        }""")
        assert p.locator("#main .scope-refusal").count() == 1, "narrowed on the host is refused, not left on Loading…"
        # a designed 403 that reaches the renderer is the same card, never an exception
        p.evaluate("() => { data.whoami.visibility.scope = 'all'; view.cluster = null; data.kpi = {forbidden: true}; render(); }")
        assert p.locator("#main .scope-refusal").count() == 1
```

```python
        p.evaluate("""() => {
          data.whoami.visibility.scope = "self";
          data.whoami.visibility.cluster_admin = false;   // the host tier the page keys on since #322
          data.whoami.visibility.clusters = Object.assign({}, data.whoami.visibility.clusters,
            { west: { policy: "remote-sar", identity: "same-as-host", scope: "all" } });
          data.clusters = (data.clusters || []).concat([{ id: "west", visibility: { policy: "remote-sar", scope: "all" } }]);
          view.cluster = "west"; data.kpi = null; render();
        }""")
        assert p.locator("#main .scope-refusal").count() == 1, "refused on the host is refused, not left on Loading…"
        # a designed 403 that reaches the renderer is the same card, never an exception
        p.evaluate("() => { data.whoami.visibility.scope = 'all'; data.whoami.visibility.cluster_admin = true; view.cluster = null; data.kpi = {forbidden: true}; render(); }")
        assert p.locator("#main .scope-refusal").count() == 1
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
    app.state.tier_resolver = _TierByName()
    # The Cluster Configurations tier (#230): `root` holds both levels, `viewer` reads without
    # changing, and everyone else — the auditor persona included — holds neither and gets no tab.
    app.state.clusterconfig_view_resolver = _TierByName("root", "viewer")
    app.state.clusterconfig_manage_resolver = _TierByName("root")
```

```python
    app.state.tier_resolver = _TierByName()
    # The cluster-admin tier (#322): `root` holds it — the Cluster Configurations tab and the KPI
    # page — and everyone else, the auditor persona included, gets neither tab.
    app.state.cluster_admin_resolver = _TierByName("root")
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
    def test_a_view_only_reader_reads_the_cards_and_has_no_write_control(self, page, cc_rig):
        """`clusterconfig:view` without `manage` — the shape a site gets by granting `get secrets`
        and not `create secrets`: the tab, the cards and the YAML twin, and nothing that writes."""
        base, host, settings = cc_rig
        _open_as(page, base, "viewer")
        assert page.locator("#tab-clusters").count() == 1
        page.click("#tab-clusters"); page.wait_for_selector("#cc-cluster-east")
        for control in ("#cc-create", "#cc-test", "#cc-rotate-east", "#cc-delete-east"):
            assert page.locator(control).count() == 0, control
        assert page.locator("#cc-yaml").count() == 1                 # the GitOps twin stays: it writes nothing
        note = page.locator("#cc-writes-off").inner_text()
        assert "read-only for you" in note and "clusterConfig.secrets.writes.enabled" not in note

```

```python
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
            # 13, not 14: the strip is PERSONA-dependent now. Cluster Configurations appears only for
            # a reader the `clusterconfig:view` level admits (#230), and this walk runs as alice, who
            # is not one — an auditor must not learn the surface exists; root counts 14 in
            # TestClusterConfigPage. Home (#158), KPIs (#157), Kyverno (#170), Library (#229) are in.
            assert page.evaluate("() => document.querySelectorAll('button.tab').length") == 13
```

```python
            # 12, not 14: the strip is PERSONA-dependent now. Cluster Configurations and KPIs appear
            # only for a reader the cluster-admin tier admits (#230, #322), and this walk runs as
            # alice, who is not one — an auditor must not learn the surface exists; root counts 14 in
            # TestClusterConfigPage. Home (#158), Kyverno (#170), Library (#229) are in.
            assert page.evaluate("() => document.querySelectorAll('button.tab').length") == 12
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
            assert page.evaluate("() => document.querySelectorAll('button.tab').length") == 13   # Reports and Library, with reporting on
```

```python
            assert page.evaluate("() => document.querySelectorAll('button.tab').length") == 12   # Reports and Library, with reporting on; no KPIs — this rig has no cluster-admin seam (#322)
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
    def test_every_rowlink_table_keeps_its_first_column_clear_of_the_rail(self, dash, server):
        def go(hash_, wait):
```

```python
    def test_every_rowlink_table_keeps_its_first_column_clear_of_the_rail(self, dash, server):
        dash.set_extra_http_headers({"X-Forwarded-User": "root"})   # the KPI page is the cluster-admin tier (#322)

        def go(hash_, wait):
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
    app.state.usage_tier_resolver = _TierByName()
    app.state.clusterconfig_view_resolver = _TierByName()
    app.state.clusterconfig_manage_resolver = _TierByName()
```

```python
    app.state.usage_tier_resolver = _TierByName()
    app.state.cluster_admin_resolver = _TierByName()
```

### Tests — the new file

<!-- block: local-development/tests/test_cluster_admin_tier.py | create -->

```python
"""The cluster-admin tier (#322, SPEC_T2): one SubjectAccessReview — `update clusterrolebindings` on the
host — gates the KPI page and the whole Cluster Configurations tab, and a reader who passes it is granted
every tier the host decides. A case per Definition-of-Done item, through the seams build_app publishes
(app.state.tier_resolver, .usage_tier_resolver, .cluster_admin_resolver, .remote_tier_resolvers), stubbed
per persona so no cluster is needed.

The personas mirror the reference cluster (SPEC_T1, "The problem, measured", and the mock cluster's SAR
oracle): `root` is cluster-admin and passes every question; `auditor` is cluster-reader — passes
`list clusterrolebindings`, the wide question, and fails `update`, this one — the NEGATIVE CONTROL of every
case; `alice` is a plain reader.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings, _cluster_admin_sar_setting
from test_visibility import H, _MapResolver, _seed, _settings

KPI = "/api/kpi"
CONFIGS = "/api/clusterconfigs"
SENTENCE = "For cluster administrators only."


class _Explodes:
    def resolve(self, viewer):
        raise RuntimeError("the API server said no such luck")


def _app(db, *, wide=None, usage=None, cluster_admin=None, **kw):
    """The three host seams stubbed apart. `None` leaves the resolver build_app made, which cannot reach
    the configured cluster and fails closed — the live shape of "the check did not come back"."""
    _seed(db)
    app = build_app(_settings(db, **kw), run_poller=False)
    app.state.tier_resolver = _MapResolver(wide or {})
    app.state.usage_tier_resolver = _MapResolver(usage or {})
    if cluster_admin is not None:
        app.state.cluster_admin_resolver = cluster_admin
    return app


def _writes(c, who):
    body = {"name": "west", "server": "https://api.west.example:6443",
            "credential": {"kind": "bearerToken", "token": "sha256~a-long-enough-token"}}
    return [c.post(CONFIGS, json=body, headers=H(who)),
            c.put(f"{CONFIGS}/east/credential", json={"token": "t"}, headers=H(who)),
            c.delete(f"{CONFIGS}/east", headers=H(who)),
            c.post(f"{CONFIGS}/test", json=body, headers=H(who))]


class TestTheFourSurfaces:
    """Each surface the issue names, and the negative control on each: a cluster-reader passes the wide
    question and is refused."""

    @pytest.fixture
    def client(self, tmp_path):
        app = _app(str(tmp_path / "gsd.db"), wide={"root": "all", "auditor": "all"},
                   cluster_admin=_MapResolver({"root": "all"}), cluster_secrets_writes_enabled=True)
        with TestClient(app) as c:
            yield c

    def test_the_kpi_page_is_the_tier_and_a_cluster_reader_is_refused(self, client):
        assert client.get("/api/clusters/c1/groups", headers=H("auditor")).json()["scope"] == "all"   # wide, as measured
        refused = client.get(KPI, headers=H("auditor"))
        assert refused.status_code == 403
        assert refused.json()["detail"].startswith(SENTENCE)
        assert client.get(KPI, headers=H("root")).status_code == 200
        assert client.get(KPI, headers=H("alice")).status_code == 403

    def test_the_cluster_configurations_view_is_the_tier_and_a_cluster_reader_is_refused(self, client):
        refused = client.get(CONFIGS, headers=H("auditor"))
        assert refused.status_code == 403 and refused.json()["detail"].startswith(SENTENCE)
        body = client.get(CONFIGS, headers=H("root")).json()
        assert body["scope"] == "all" and body["can"] == {"view": True, "manage": True}

    def test_the_cluster_configurations_writes_are_the_tier_and_a_cluster_reader_is_refused(self, client):
        assert [r.status_code for r in _writes(client, "auditor")] == [403, 403, 403, 403]
        assert all(r.json()["detail"].startswith(SENTENCE) for r in _writes(client, "auditor"))
        # root reaches the writer (the test probe fails on the made-up server, which is past the gate)
        assert all(r.status_code != 403 for r in _writes(client, "root"))

    def test_whoami_withholds_both_tabs_from_a_cluster_reader(self, client):
        auditor = client.get("/api/whoami", headers=H("auditor")).json()["visibility"]
        assert auditor["scope"] == "all" and auditor["cluster_admin"] is False
        root = client.get("/api/whoami", headers=H("root")).json()["visibility"]
        assert root["scope"] == "all" and root["cluster_admin"] is True
        assert "clusterconfig" not in client.get("/api/whoami", headers=H("root")).json()

    def test_the_refusal_names_no_role_grant_value_or_route(self, client):
        for path in (KPI, CONFIGS):
            detail = client.get(path, headers=H("auditor")).json()["detail"]
            for word in ("cluster-admin", "clusterrolebindings", "clusterAdminSar", "update", "/api", "c1", "secrets"):
                assert word not in detail, (path, word)

    def test_the_mutant_reverting_a_route_to_the_wide_tier_admits_the_auditor(self, client):
        """The kill: everyone here passes the wide tier, so `require_admin_tier` on either route answers 200."""
        for path in (KPI, CONFIGS):
            assert client.get(path, headers=H("auditor")).status_code == 403, path


class TestTheHierarchy:
    """The top tier grants every host-decided tier, one way only; per-cluster policies still apply."""

    @pytest.fixture
    def rig(self, tmp_path):
        """The wide and Usage stubs deny EVERYONE — the case the issue names: adminSar and usageAdminSar
        pointed at checks the cluster-admin fails. Only clusterAdminSar admits root."""
        db = str(tmp_path / "gsd.db"); _seed(db)
        token = tmp_path / "token"; token.write_bytes(b"t" * 48 + b"\n")
        settings = Settings(
            clusters=[ClusterConfig("c1", "https://api.c1.example.com:6443", token_env="X"),
                      ClusterConfig("c2", "https://api.c2.example.com:6443", token_env="Y", visibility="inherit"),
                      ClusterConfig("far", "https://api.far.example.com:6443", token_env="Z"),          # remote-sar, by default
                      ClusterConfig("solo", "https://api.solo.example.com:6443", token_env="W",
                                    visibility="self-only", identity="same-as-host")],
            # A report service configured, so /api/dashboard/reports reaches usage_scope rather than
            # answering its reporting-off `self` before any tier is asked.
            db_path=db, oauth_proxy_enabled=True, reporting_url="https://gsd-report.ns.svc:8443",
            reporting_token_file=str(token))
        app = build_app(settings, run_poller=False)
        wide, usage, far = _MapResolver({}), _MapResolver({}), _MapResolver({})
        app.state.tier_resolver = wide
        app.state.usage_tier_resolver = usage
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
        app.state.remote_tier_resolvers = {"far": far}
        with TestClient(app) as c:
            yield c, wide, usage, far

    def test_a_cluster_admin_is_wide_on_the_host_and_on_inherit_clusters(self, rig):
        c, wide, usage, far = rig
        assert c.get("/api/clusters/c1/groups", headers=H("root")).json()["scope"] == "all"
        assert c.get("/api/clusters/c2/groups", headers=H("root")).json()["scope"] == "all"
        who = c.get("/api/whoami", headers=H("root")).json()["visibility"]
        assert who["scope"] == "all" and who["clusters"]["c1"]["scope"] == "all" and who["clusters"]["c2"]["scope"] == "all"
        assert wide.calls == 0, "the wide question is never asked of a cluster-admin"

    def test_a_cluster_admin_is_wide_on_usage_whatever_the_usage_question_answers(self, rig):
        c, wide, usage, far = rig
        assert c.get("/api/dashboard/activity", headers=H("root")).json()["scope"] == "all"
        assert c.get("/api/dashboard/reports", headers=H("root")).json()["scope"] == "all"
        assert usage.calls == 0, "the Usage question is never asked of a cluster-admin"

    def test_a_remote_sar_cluster_still_asks_its_own_api(self, rig):
        c, wide, usage, far = rig
        assert c.get("/api/clusters/far/groups", headers=H("root")).json()["scope"] == "self"
        assert far.calls >= 1, "the remote decided, not the host's top tier"
        assert c.get("/api/whoami", headers=H("root")).json()["visibility"]["clusters"]["far"]["scope"] == "self"

    def test_a_self_only_cluster_stays_self(self, rig):
        c, wide, usage, far = rig
        assert c.get("/api/clusters/solo/groups", headers=H("root")).json()["scope"] == "self"
        assert c.get("/api/whoami", headers=H("root")).json()["visibility"]["clusters"]["solo"]["scope"] == "self"

    def test_it_works_one_way_only(self, tmp_path):
        """Wide by adminSar, self on Usage by usageAdminSar, and refused the tier: passing the two lower
        questions implies nothing about this one."""
        app = _app(str(tmp_path / "one-way.db"), wide={"auditor": "all"}, usage={"auditor": "all"},
                   cluster_admin=_MapResolver({}))
        with TestClient(app) as c:
            assert c.get("/api/clusters/c1/groups", headers=H("auditor")).json()["scope"] == "all"
            assert c.get("/api/dashboard/activity", headers=H("auditor")).json()["scope"] == "all"
            assert c.get(KPI, headers=H("auditor")).status_code == 403
            assert c.get(CONFIGS, headers=H("auditor")).status_code == 403
            assert c.get("/api/whoami", headers=H("auditor")).json()["visibility"]["cluster_admin"] is False

    def test_a_plain_reader_stays_self_everywhere(self, rig):
        c, wide, usage, far = rig
        assert c.get("/api/clusters/c1/groups", headers=H("alice")).json()["scope"] == "self"
        assert c.get("/api/dashboard/activity", headers=H("alice")).json()["scope"] == "self"
        assert c.get(KPI, headers=H("alice")).status_code == 403


class TestFailClosed:
    def test_visibility_off_still_asks_the_tier(self, tmp_path):
        """`visibility.enabled: false` widens the wide views by design; it must not hand KPI or the
        fleet's wiring to every proxy-admitted reader (the issue: "for KPI this is a change"), and a
        cluster-admin keeps Usage through the tier."""
        app = _app(str(tmp_path / "off.db"), cluster_admin=_MapResolver({"root": "all"}),
                   view_restrictions_enabled=False)
        with TestClient(app) as c:
            for who in ("auditor", "alice"):
                assert c.get("/api/clusters/c1/groups", headers=H(who)).json()["scope"] == "all"   # restrictions off
                assert c.get(KPI, headers=H(who)).status_code == 403
                assert c.get(CONFIGS, headers=H(who)).status_code == 403
                assert c.get("/api/dashboard/activity", headers=H(who)).json()["scope"] == "self"
                assert c.get("/api/whoami", headers=H(who)).json()["visibility"]["cluster_admin"] is False
            assert c.get(KPI, headers=H("root")).status_code == 200
            assert c.get(CONFIGS, headers=H("root")).status_code == 200
            assert c.get("/api/dashboard/activity", headers=H("root")).json()["scope"] == "all"
            assert c.get("/api/whoami", headers=H("root")).json()["visibility"]["cluster_admin"] is True

    def test_with_the_proxy_off_there_is_no_one_to_ask_about(self, tmp_path):
        app = _app(str(tmp_path / "noproxy.db"), cluster_admin=_MapResolver({"root": "all"}),
                   oauth_proxy_enabled=False, view_restrictions_enabled=False)
        with TestClient(app) as c:
            assert c.get(KPI, headers=H("root")).status_code == 403
            assert c.get(CONFIGS, headers=H("root")).status_code == 403

    @pytest.mark.parametrize("stub", [None, _Explodes(), _MapResolver({"root": "ALL"}), _MapResolver({"root": "yes"})],
                             ids=["no-resolver", "raises", "miscased", "junk"])
    def test_an_indeterminate_answer_refuses(self, tmp_path, stub):
        app = _app(str(tmp_path / "ind.db"), wide={"root": "all"}, cluster_admin=stub)
        with TestClient(app) as c:
            assert c.get(KPI, headers=H("root")).status_code == 403
            assert c.get(CONFIGS, headers=H("root")).status_code == 403
            assert c.get("/api/whoami", headers=H("root")).json()["visibility"]["cluster_admin"] is False

    def test_no_identity_refuses(self, tmp_path):
        app = _app(str(tmp_path / "anon.db"), cluster_admin=_MapResolver({"root": "all"}))
        with TestClient(app) as c:
            assert c.get(KPI).status_code == 403
            assert c.get(CONFIGS).status_code == 403


class TestTheResolverAndItsSetting:
    def test_build_app_makes_one_resolver_apart_from_the_wide_switch_and_the_usage_cache(self, tmp_path):
        db = str(tmp_path / "gsd.db"); _seed(db)
        for restrictions in (True, False):
            app = build_app(_settings(db, view_restrictions_enabled=restrictions), run_poller=False)
            r = app.state.cluster_admin_resolver
            assert r is not None, f"restrictions={restrictions}: the tier is asked in both states"
            assert r._attributes == {"verb": "update", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"}
        on = build_app(_settings(db), run_poller=False)
        assert on.state.cluster_admin_resolver is not on.state.usage_tier_resolver
        assert on.state.cluster_admin_resolver._cache is not on.state.usage_tier_resolver._cache
        assert on.state.cluster_admin_resolver._kube.cluster.name == "c1", "asked on the host"

    def test_the_default_is_the_usage_question_as_its_own_setting(self):
        """The mock cluster's oracle (mock-app/tests/test_sar_personas.py, `USAGE`) answers this exact
        question `no` for `dana.lee` (cluster-reader) and `yes` for `kubeadmin` — the negative control
        at the SAR itself."""
        s = Settings(clusters=())
        assert {"verb": s.visibility_cluster_admin_sar_verb, "resource": s.visibility_cluster_admin_sar_resource,
                "group": s.visibility_cluster_admin_sar_api_group} == {
            "verb": "update", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"}
        assert (s.visibility_usage_admin_sar_verb, s.visibility_usage_admin_sar_resource) == ("update", "clusterrolebindings")
        assert s.visibility_cluster_admin_sar_namespace == "" == s.visibility_cluster_admin_sar_subresource

    def test_the_configmap_keys_parse_whole_or_default(self):
        custom = {"visibilityClusterAdminSarApiGroup": "example.io", "visibilityClusterAdminSarResource": "fleets/admin",
                  "visibilityClusterAdminSarVerb": "approve", "visibilityClusterAdminSarNamespace": "ops"}
        assert _cluster_admin_sar_setting(custom) == ("example.io", "fleets", "admin", "approve", "ops")
        assert _cluster_admin_sar_setting({}) == ("rbac.authorization.k8s.io", "clusterrolebindings", "", "update", "")
        # one unusable field takes the WHOLE default, never half a custom question
        assert _cluster_admin_sar_setting({**custom, "visibilityClusterAdminSarVerb": "Approve"}) == (
            "rbac.authorization.k8s.io", "clusterrolebindings", "", "update", "")

    def test_the_threshold_label_is_pre_seeded_and_counts_the_tier(self, tmp_path):
        app = _app(str(tmp_path / "m.db"), cluster_admin=_MapResolver({"root": "all"}))
        with TestClient(app) as c:
            before = c.get("/metrics").text
            assert 'gsd_visibility_decisions_total{threshold="cluster_admin",tier="all"} 0.0' in before
            assert "clusterconfig_view" not in before and "clusterconfig_manage" not in before
            c.get(KPI, headers=H("root"))
            after = c.get("/metrics").text
            assert 'gsd_visibility_decisions_total{threshold="cluster_admin",tier="all"} 1.0' in after
```

