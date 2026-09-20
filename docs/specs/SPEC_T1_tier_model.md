# SPEC T1 — The named dashboard tier model: self / auditor / admin / cluster-admin

| | |
|---|---|
| Programme | Named dashboard tiers (#239), steps T1 / T2 / T3 — after the 2026-09 programme's ladder; T2 closes #114, T3 folds in #230's pair |
| Batch | T — tiers |
| Release | — (post-programme; each step its own PR and its own three-seat review) |
| Version on release | app and chart minor bumps per step, assigned at each step's PR |
| Issue | [#239](https://github.com/ephico2real2/group-sync-dashboard/issues/239) |
| Status | specified |
| Source | this document is the orchestrator's own design, measured on CRC on 2026-09-20 with the commands quoted below; there is no separate design-agent output |

## How to read this spec

"The problem, measured" is what the cluster answered, persona by persona, with the command that
asked. "The model" fixes the four tiers — their names in code and on the wire, their questions,
their settings and chart values — and the rules every tier obeys. "Surface → tier" is the one table
(`TIER_BY_SURFACE`) every route and every tab reads, derived from the gate each route calls on
main today, with what changes marked. "Migration" says exactly who loses what, what else reads a
tier's verdict, and the one-release knob. "Tests" is a case per persona per surface against the mock
cluster's SAR oracle, a mutant per surface, and the metrics pre-seeding. "Decomposition" is the
three pull requests. A deviation found necessary during implementation is written back here, in the
same pull request, under "Orchestrator's notes", with the reason.

## Orchestrator's notes

The operator's rulings this spec rests on, one line each, verbatim where quoted:

- 2026-09-20 (#230, and it SUPERSEDES the two rulings below wherever they are read as ordering the rungs): *"A user with cluster admin and auditor is fine. That is how Kubernetes RBAC works. As long as the user has the role needed or can get the right SAR needed, we are good."* Each tier asks its own SAR and **composes nothing**: RBAC is additive, so holding the auditor role beside a namespace or cluster admin grant is the model working, not a contradiction; the SAR is the ACTION'S OWN question, so whoever passes `create secrets` can write the Secret with `oc` and the dashboard's ServiceAccount performing the write grants nobody a permission they lack; and the "no auditor" ruling holds anyway, because the pure auditor persona (`lateef.o`, the chart's role alone) answers `no` to both cluster-admin questions. What protects the surface is therefore fail-closed resolution, the absence of a `restrict` short-circuit, a resolver and cache per level, and the question asked in the resolved namespace — not a ladder.
- 2026-09-20 (#239): *"we can learn a lot from argocd — we can create multiple tiers for this kind of stuff: dashboard_auditor_tier, dashboard_cluster_admin_tier"*.
- 2026-09-20 (#230): *"we can create a new tier boss — look at how argocd does it"* — the cluster-configuration tier is Argo CD's `clusters` resource expressed in OpenShift RBAC: a named pair of SAR questions (`get secrets` / `create secrets` in the dashboard's namespace), default deny.
- 2026-09-20 (#230, tier ruling): the Cluster Configurations surface is **cluster-admin only — the auditor must neither view nor change it**; every route behind it, a reader who fails it gets the refusal card, never a partial view.
- 2026-09-20 (#230): **the tab itself is not rendered** for a reader who fails its tier (no tab button, no dispatch, no fetch); reaching it by URL shows the refusal card naming itself.
- 2026-09-20 (#230): each level has its **own resolver instance and cache, never shared** with the wide tier's or with each other; `manage` does not imply `view` in code — both are asked.
- 2026-09-20 (#230): settings `visibility_clusterconfig_{view,manage}_sar_{verb,resource,subresource,namespace}`, chart values and README rows beside the Usage ones, so a site can point a level at its own ClusterRole.
- 2026-09-20 (#230): tests per measured persona through the mock cluster's SAR oracle; **a mutant that reverts any route to `require_admin_tier` must fail a test**.
- 2026-09-20 (#239): four named tiers, each ONE declared SAR question, its own resolver and cache, fail closed; *"a higher tier does not imply a lower one in code — each is asked"*.
- 2026-09-20 (#239): *"This consolidates, it does not add"* — `usage_scope` becomes the admin tier, `require_admin_tier` becomes the auditor tier for the read surfaces it guards.
- 2026-09-20 (#239): one table in code, `TIER_BY_SURFACE`, that every route and every tab reads; tabs a tier does not grant are not rendered, and a URL to one shows the refusal card naming itself.
- 2026-09-20 (#239): the migration ships with the tier on `/api/whoami`, a CHANGELOG line naming the change, and a values knob to keep the old behaviour for one release.
- 2026-09-20 (#239): T1 the registry, T2 the migration of the existing gates (closes #114), T3 the cluster-configuration tier as the fourth rung; #238's bootstrap controls sit at `cluster_admin:manage`.
- Standing rulings the model inherits: the Usage ruling — *"we can grant them cluster reader and not cluster admin. But it means cluster-admin need to see all and not gated all"* (`docs/SPEC_usage_admin_tier.md#The operator's ruling`); the refusal sentence *"For administrators only."* is the operator's exact phrase and leads both the card and the API `detail` (`gsd/api.py#require_admin_tier`); a refusal names no role, grant, chart value or route (`gsd/static/index.html#refusalCard`); *"Hiding a tab is never the control"* — the server 403 is (`docs/ACCESS_CONTROL.md#Hiding a tab is never the control`); chart booleans default on (2026-09-05).

Decisions this spec makes where the issue is silent, by the best-practice rule (posted on #239 with this spec; each is the orchestrator's, dated 2026-09-20, and stands until the operator rules otherwise):

- **D1 — KPIs and Kyverno are auditor-tier.** #239's table lists neither. Both are gated by `require_admin_tier` today, both are governance data about the clusters with no person named, and the auditor persona `cluster-reader` can read the source objects with `oc` (measured below: `list policyreports.wgpolicyk8s.io` → `yes`). By the same criterion that puts RBAC policy and Overview on the auditor tier, they stay where they are.
- **D2 — the Usage tab's existence is self-tier; its wide form is admin-tier.** Today every reader sees their own rows and the usage threshold widens (`gsd/api.py#dashboard_activity`). Naming the widening tier `admin` changes no behaviour; hiding the tab below admin would.
- **D3 — the compatibility knob is not "`adminSar` pointed back at `list clusterrolebindings`".** After T2 `visibility.adminSar` governs Usage; pointing it at a read verb admits the auditor to Usage, which the Usage ruling forbids. The knob that restores exactly the pre-T2 mapping is `visibility.compat.adminSarIsAuditorSar` (§ Migration).
- **D4 — the report ticket's `tier` claim stays the literal `all` through T2.** The report pod verifies that literal (`gsd/reporting/ticket.py#verify`); renaming it needs a two-release verifier and buys nothing, because the ticket is minted at exactly one tier.
- **D5 — the metrics `threshold` label takes the tier names** (`auditor`, `admin`, `cluster_admin_view`, `cluster_admin_manage`), pre-seeded, with `admin` → `auditor` and `usage` → `admin` said in the CHANGELOG. The shipped alert and Grafana panels select on `outcome`, `tier` and `sum by (threshold, …)`, never on a threshold value, so nothing shipped breaks.
- **D6 — `/api/whoami` gains `tiers` and keeps `visibility.scope`** with its meaning unchanged (`all` ⇔ the auditor tier on the host). Additive: no client that reads `scope` today changes.
- **D7 — the admin and cluster-admin tiers are decided on the host only.** Usage has no cluster dimension and the cluster Secrets live in the host namespace. The auditor tier is the one D2 decides per cluster: a `remote-sar` resolver asks the auditor question on the remote.
- **D8 — the refusal card names the tier it needed, in the dashboard's own words, never the SAR.** *"For administrators only."* stays for the admin tier; the auditor tier says *"For auditors and administrators only."*; the cluster-admin tier says *"For cluster administrators only."* The API `detail` leads with the same sentence, as today.

## The problem, measured (CRC, 2026-09-20)

The wide tier asks `list clusterrolebindings`; the chart's own auditor role grants exactly that.
Read off the cluster:

```
$ export KUBECONFIG=~/.kube/crc.kubeconfig
$ oc get clusterrole group-sync-dashboard-report-auditor -o json | python3 -c 'import json,sys; print(json.dumps(json.load(sys.stdin)["rules"]))'
[{"apiGroups": ["user.openshift.io"], "resources": ["users", "groups"], "verbs": ["get", "list"]},
 {"apiGroups": ["rbac.authorization.k8s.io"], "resources": ["roles", "rolebindings", "clusterroles", "clusterrolebindings"], "verbs": ["get", "list"]}]
$ oc get clusterrolebinding -o json | python3 -c '...'   # who holds the persona roles
cluster-admin   <- kubeadmin            [('User', 'kubeadmin')]
cluster-reader  <- cluster-reader       [('User', 'dana.lee')]
group-sync-dashboard-report-auditor <- group-sync-dashboard-ra-b78c05817c9d [('Group', 'app-ocp-rbac-groupsync-ns-auditor')]
self-provisioner <- self-provisioners   [('Group', 'system:authenticated:oauth')]
```

So an auditor passes the admin gate by construction — #114, from the live run.

**The measurement is in the dashboard's own form.** `gsd/kube.py#TierResolver` posts a
SubjectAccessReview naming the viewer **and** the Group memberships read from the cluster plus the
virtual groups (`gsd/kube.py#_virtual_groups_for`). Impersonation alone does not do that — the
apiserver adds no OpenShift Group membership under `--as` — measured: `oc auth can-i list
clusterrolebindings.rbac.authorization.k8s.io --as=lateef.o` → `no` while the same question with his
groups → `yes`; `dana.lee`, bound as a User, is `yes` either way. Every row below therefore passes
`--as=<user>` **and** `--as-group=<each Group the user is in>` plus `system:authenticated` (and
`system:authenticated:oauth` for people; `system:serviceaccounts` and `system:serviceaccounts:<ns>` for
the ServiceAccount) — the **complete** list read from the Group objects, because a partial list
measures a different person (a first pass with three of `bob.wilson`'s twenty-seven Groups answered
`no` to both secrets questions; his complete list answers `yes`). A SelfSubjectAccessReview under
impersonation persists nothing, like the dashboard's own review.

```
$ NS=group-sync-dashboard
$ oc auth can-i list   clusterrolebindings.rbac.authorization.k8s.io --as=$U $GROUPS
$ oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=$U $GROUPS
$ oc auth can-i get    secrets -n $NS --as=$U $GROUPS
$ oc auth can-i create secrets -n $NS --as=$U $GROUPS
$ oc auth can-i list   policyreports.wgpolicyk8s.io --as=$U $GROUPS          # D1's evidence
$ oc auth can-i list   namespaceconfigs.redhatcop.redhat.io --as=$U $GROUPS
$ oc auth can-i get    pods/log -n openshift-authentication --as=$U $GROUPS
```

| persona (real subject on CRC) | holds | `list` crb → **auditor** | `update` crb → **admin** | `get secrets` ns → **cluster_admin:view** | `create secrets` ns → **cluster_admin:manage** | policyreports / nsconfigs / pod logs |
|---|---|---|---|---|---|---|
| `kubeadmin` | `cluster-admin` (User CRB) | yes | yes | yes | yes | yes / yes / yes |
| `dana.lee` | `cluster-reader` (User CRB); a group bound to a **missing** ClusterRole `database-admin` | yes | no | no | no | yes / yes / yes |
| `lateef.o` | the chart's `…-report-auditor` via Group `app-ocp-rbac-groupsync-ns-auditor`; a `…-lateef-ns-developer` Group with **no binding behind it** on this cluster | **yes** | no | no | no | no / no / no |
| `bob.wilson` | the auditor Group, cluster-wide `view` (`…-demo-cluster-audit-crb`, `…-alpha-cluster-audit-crb`) **and cluster-wide `edit`** (`app-ocp-rbac-alpha-cluster-developer-crb`, `…-finance-cluster-developer-crb`) | yes | no | **yes** | **yes** | yes / yes / yes |
| `john.doe` | cluster-wide **`admin`** via four Groups (`…-demo-`, `…-newteam-`, `…-platform-`, `…-test-cluster-admin`, each a CRB to ClusterRole `admin`) | **no** | no | **yes** | **yes** | yes / yes / yes |
| `jeff` | `edit`/`view` by RoleBinding in `jeff-qa`, `jeff-rnd` only (a plain developer) | no | no | no | no | no / no / no |
| `test-user-002` | nothing but `self-provisioner` / `basic-user` (every OAuth login) | no | no | no | no | no / no / no |
| `system:serviceaccount:group-sync-dashboard:group-sync-dashboard` | the chart's reader role and `system:auth-delegator` | no | no | no | no | no / no / no |

`dana.lee`'s three `no` answers carry the reason *RBAC: clusterrole "database-admin" not found* — a
dangling binding in one of her groups, which the SAR reports and which changes nothing: `allowed`
is false. **`bob.wilson` is the case the operator's ruling of 2026-09-20 settles:** a member of the chart's
auditor Group who, through `app-ocp-rbac-alpha-cluster-developer-crb` → ClusterRole `edit`, passes
both cluster-admin levels. He is **admitted, deliberately** — he holds `create secrets` in that
namespace and can write the cluster Secret with `oc` whatever the dashboard shows him, so refusing him
here would protect nothing and only puzzle him. What the "no auditor" ruling actually excludes is the
auditor *persona* — the role alone — which answers `no` to both questions (`lateef.o`, measured). Confirmed by
subtraction: the same question with only his auditor and audit Groups answers `no`; with the
`…-alpha-cluster-developer` Group alone, `yes`. Every persona resolves the same on the mock cluster (`local-development/mock-app/fixtures/reference.yaml#persona`,
`local-development/mock-app/tests/test_sar_personas.py#ORACLE`), whose fixture reproduces
`kubeadmin`, `dana.lee`, `lateef.o` (there: no admin binding at all), the decoy `jane.smith` and the
auditor-group `developer`.

**Which ClusterRoles pass `update clusterrolebindings` without being `cluster-admin` — the model's
main risk, scanned across all 497 ClusterRoles on CRC** (`oc get clusterrole -o json`, every rule
matched on apiGroup/resource/verb with `*` honoured; then every ClusterRoleBinding's subjects):

| ClusterRole | how the rule grants it | bound to |
|---|---|---|
| `cluster-admin` | wildcard | `system:masters`, `system:cluster-admins`, `system:admin`, `kubeadmin`, 26 platform ServiceAccounts |
| `system:master` | wildcard | Group `system:masters` (the installer's client certificate) |
| `system:controller:generic-garbage-collector`, `system:controller:operator-lifecycle-manager` | wildcard | their controller ServiceAccounts |
| `openshift-gitops-openshift-gitops-argocd-application-controller`, the OpenShift GitOps operator's CSV role, the namespace-configuration operator's CSV role | wildcard | operator ServiceAccounts |
| `cluster-image-registry-operator`, `cluster-monitoring-operator`, `openshift-ingress-operator`, `openshift-ingress-operator-sail-library`, the cert-manager operator's CSV role | explicit `create,delete,get,list,patch,update,watch` (or a subset with `update`) | operator ServiceAccounts |

Twelve roles; on this cluster **no User or Group but `system:masters` holds one that is not
`cluster-admin`**. On another cluster the risk is a *custom* role granting RBAC write to people — a
"platform-rbac" role, say — which passes the admin tier and therefore Usage; the chart README row for
`visibility.adminSar` names this, and an operator who has such a role points the tier at a narrower
question (the settings exist for that).

**The other measured risk is the cluster-admin tier's.** The stock namespaced roles `admin` and
`edit` both grant `create,delete,get,list,patch,update,watch` on `secrets` (`oc get clusterrole admin
-o json`, `edit` likewise; `view` grants nothing on secrets). Measured on `john.doe`, who holds
`admin` cluster-wide: he **fails** the auditor and admin tiers and **passes both cluster-admin
levels** — and the same is true of anyone given `admin` or `edit` by a RoleBinding in the dashboard's
namespace (measured on `jeff` in `jeff-qa`: `get secrets` → `yes`, `create secrets` → `yes`).
That is the *"no tier implies another"* rule showing its consequence, and the operator accepted it on
2026-09-20: a reader may be able to rotate the fleet's credentials while unable to open the RBAC policy
tab, because those are two different grants and each gate asks for the one it needs. Such a reader can
already do both things with `oc`; the dashboard is not the boundary, RBAC is. The model keeps the
operator's questions
(they read as what they are) and states the consequence on the README row for
`visibility.clusterAdminSar`: **a RoleBinding to `admin`/`edit` in the dashboard's namespace is a
grant of the Cluster Configurations surface**; today that namespace holds none for a human
(`oc get rolebinding -n group-sync-dashboard` — every subject is a ServiceAccount or the namespace's
`system:serviceaccounts:<ns>` group); the cluster-wide `admin`/`edit` grants above reach it from
outside the namespace. The
scan of every role passing `get secrets` (44) and `create secrets` (26) is in the record of this
measurement; the human-facing ones are `admin`, `edit`, `registry-admin`, `registry-editor` and
`system:aggregate-to-edit`, all namespaced in intent.

## The model

Four named tiers. Each is ONE declared SubjectAccessReview about the viewer, decided by its own
`gsd/kube.py#TierResolver` instance with its own cache, and every tier fails closed: no identity,
no resolver, an error, a junk answer — refused. Nothing implies anything: the admin tier is asked
its own question, never inferred from the auditor's; `manage` never from `view`.

| tier (issue's name) | code `Tier` member → wire value | SAR question (default) | settings (`gsd/config.py#Settings`) | chart values | README rows | who passes, measured above |
|---|---|---|---|---|---|---|
| `dashboard_self_tier` | `Tier.SELF` → `"self"` | none — every authenticated identity behind the proxy | — | — | — | everyone the proxy names |
| `dashboard_auditor_tier` | `Tier.AUDITOR` → `"auditor"` | `list clusterrolebindings.rbac.authorization.k8s.io` (today's wide question) | `visibility_auditor_sar_{api_group,resource,subresource,verb,namespace}` | `visibility.auditorSar.{apiGroup,resource,verb,namespace}` | `visibility.auditorSar.*` (the present `adminSar` rows, renamed) | `kubeadmin`, `dana.lee`, `lateef.o`, `bob.wilson` — **not** `john.doe`, `jeff`, the plain login, the SA |
| `dashboard_admin_tier` | `Tier.ADMIN` → `"admin"` | `update clusterrolebindings.rbac.authorization.k8s.io` (today's Usage question) | `visibility_admin_sar_*` (the present names; **default changes** from `list` to `update`) | `visibility.adminSar.*` (default changes) | `visibility.adminSar.*` (rewritten) | `kubeadmin` only |
| `dashboard_cluster_admin_tier` | `Tier.CLUSTER_ADMIN_VIEW` → `"cluster_admin:view"`, `Tier.CLUSTER_ADMIN_MANAGE` → `"cluster_admin:manage"` | **view** `get secrets` in the dashboard's namespace; **manage** `create secrets` there | `visibility_cluster_admin_{view,manage}_sar_*` (S1/S2 ship them as `visibility_clusterconfig_{view,manage}_sar_*`; T3 renames, § Decomposition) | `visibility.clusterAdminSar.{view,manage}.{apiGroup,resource,verb,namespace}` | beside the two above | `kubeadmin`; **and `john.doe`** (cluster-wide `admin`) **and `bob.wilson`** (cluster-wide `edit`, an auditor-Group member) — the named risk |

Every `*_sar_*` setting is parsed by the existing `gsd/config.py#_sar_setting` with the existing
render-time guards in `charts/group-sync-dashboard/templates/_helpers.tpl#gsd.visibilitySarVerb`
generalised per tier (one helper family per tier, same exact-lowercase rule, same nil-safety).
`namespace` defaults to `""` for the two cluster-scoped questions and to the release namespace for
the cluster-admin pair (rendered by the chart; the app reads the namespace it runs in when the
setting is empty).

**Rules, each one already stated somewhere in this repository and now general:**

1. **Own resolver, own cache, never shared.** `docs/SPEC_usage_admin_tier.md#Cache`: *"Reuse the
   existing 60s per-viewer TTL, in a resolver instance SEPARATE from the wide tier's. It is a
   different question about the same person and must not share a cache entry."* One
   `TierResolver` per tier (per cluster for the auditor tier under `remote-sar`), each constructed
   with its own `observe=functools.partial(signals.note_tier_check, <tier>)`, published on
   `app.state.tier_resolvers[<tier>]` — the seam tests substitute, replacing today's
   `app.state.tier_resolver` and `app.state.usage_tier_resolver`.
2. **Fail closed** exactly as `gsd/api.py#_decide` does today: only the exact positive verdict
   grants; no viewer, no resolver, an exception, a junk string — refused, counted, never cached.
3. **No tier implies another in code.** There is no `>=` on tiers. A surface at the admin tier asks
   the admin resolver; a reader who is admin but (through a custom question) not auditor is
   refused the auditor surfaces. The one exception is by construction, not inference: the self
   tier is the authenticated identity itself.
4. **The blunt overrides survive unchanged, in their precedence.** `visibility.enabled=false` runs no
   resolver: the auditor tier reads as granted for every reader (today's everyone-sees-everything
   view, `gsd/api.py#viewer_scope`), the admin tier reads as **refused** so Usage stays each
   reader's own rows (`gsd/api.py#usage_scope`: "turning cluster-data restrictions off must not, as a
   side effect, expose colleagues' presence records"), and the cluster-admin pair is still asked —
   the Secrets are credentials, and restrictions off is a statement about cluster data.
   `config.userActivity.visibility: all` still widens Usage before the admin tier is consulted.
5. **The ServiceAccount never holds a tier.** The SAR is created as the dashboard's own
   ServiceAccount about *someone else*; the account itself fails every question (measured), and the
   proxy-off install has no identity to tier (`gsd/api.py#trusted_viewer`).

```python
# gsd/tiers/__init__.py (new package) — the registry. Pure data and one enum: no I/O, no FastAPI.
from __future__ import annotations

import enum
from dataclasses import dataclass


class Tier(str, enum.Enum):
    """The dashboard's own vocabulary, on the wire and in the logs. Never a role name."""
    SELF = "self"
    AUDITOR = "auditor"
    ADMIN = "admin"
    CLUSTER_ADMIN_VIEW = "cluster_admin:view"
    CLUSTER_ADMIN_MANAGE = "cluster_admin:manage"


#: The tiers a SubjectAccessReview decides, in the order /api/whoami reports them. SELF is not
#: here: it is the authenticated identity, decided by the proxy, not by a review.
DECIDED_TIERS = (Tier.AUDITOR, Tier.ADMIN, Tier.CLUSTER_ADMIN_VIEW, Tier.CLUSTER_ADMIN_MANAGE)

#: The metrics `threshold` label per decided tier (gsd_visibility_tier_checks_total,
#: gsd_visibility_decisions_total). Every combination is pre-seeded to 0 at startup.
THRESHOLD_LABEL = {
    Tier.AUDITOR: "auditor",
    Tier.ADMIN: "admin",
    Tier.CLUSTER_ADMIN_VIEW: "cluster_admin_view",
    Tier.CLUSTER_ADMIN_MANAGE: "cluster_admin_manage",
}

#: The refusal sentence per tier — the operator's exact phrase for the admin tier, the same shape
#: for the others. LEADS the API detail and the card; names the tier, never a role, grant, value
#: or route (gsd/api.py#require_admin_tier states why).
REFUSAL_SENTENCE = {
    Tier.AUDITOR: "For auditors and administrators only.",
    Tier.ADMIN: "For administrators only.",
    Tier.CLUSTER_ADMIN_VIEW: "For cluster administrators only.",
    Tier.CLUSTER_ADMIN_MANAGE: "For cluster administrators only.",
}


@dataclass(frozen=True)
class Surface:
    """One route or tab: where it is reachable, and where it is served whole.

    `reachable` is the tier below which the request is REFUSED (403; the tab is not rendered).
    `wide` is the tier at which a scoped surface serves the complete set rather than the reader's
    own rows; None for a surface with no scoped form (refused or whole, nothing between).
    """
    reachable: Tier
    wide: Tier | None = None


#: THE declaration. Keys are the FastAPI route path as registered (method GET unless stated) and
#: the page ids index.html dispatches on (prefixed `tab:`). A route or tab absent from this table
#: fails tests/test_tiers.py — that is the table's whole purpose: a new page cannot forget its gate.
TIER_BY_SURFACE: dict[str, Surface] = {
    # ── public: before the proxy or in skipAuthRegex; no identity, no tier ───────────────────
    "/metrics": Surface(Tier.SELF), "/healthz": Surface(Tier.SELF), "/readyz": Surface(Tier.SELF),
    "/api/version": Surface(Tier.SELF), "/": Surface(Tier.SELF), "/signed-out": Surface(Tier.SELF),
    "/api": Surface(Tier.SELF), "/api/redoc": Surface(Tier.SELF), "/api/docs": Surface(Tier.SELF),
    "/static/index.html": Surface(Tier.SELF), "/static/signed-out.html": Surface(Tier.SELF),
    # ── self: about the reader, or projected for every reader ───────────────────────────────
    "/api/whoami": Surface(Tier.SELF),
    "/api/clusters": Surface(Tier.SELF, wide=Tier.AUDITOR),                 # operator_configs null below wide
    "/api/clusters/{cluster_id}/groupsyncs": Surface(Tier.SELF, wide=Tier.AUDITOR),   # two fields projected
    "/api/clusters/{cluster_id}/groupsyncs/{name}/events": Surface(Tier.SELF),
    "/api/clusters/{cluster_id}/groups": Surface(Tier.SELF, wide=Tier.AUDITOR),
    "/api/clusters/{cluster_id}/groups/{name}": Surface(Tier.SELF, wide=Tier.AUDITOR),
    "/api/clusters/{cluster_id}/users": Surface(Tier.SELF, wide=Tier.AUDITOR),
    "/api/clusters/{cluster_id}/users/{name}": Surface(Tier.SELF, wide=Tier.AUDITOR),
    "/api/clusters/{cluster_id}/logins": Surface(Tier.SELF, wide=Tier.AUDITOR),
    "/api/clusters/{cluster_id}/cluster-access": Surface(Tier.SELF, wide=Tier.AUDITOR),
    "/api/clusters/{cluster_id}/namespaces": Surface(Tier.SELF, wide=Tier.AUDITOR),
    "/api/clusters/{cluster_id}/namespaces/{name}": Surface(Tier.SELF, wide=Tier.AUDITOR),
    "/api/clusters/{cluster_id}/home": Surface(Tier.SELF),                  # self-scoped by definition
    "/api/clusters/{cluster_id}/user-bindings": Surface(Tier.SELF, wide=Tier.AUDITOR),
    "/api/clusters/{cluster_id}/membership-changes": Surface(Tier.SELF, wide=Tier.AUDITOR),
    "/api/clusters/{cluster_id}/binding-changes": Surface(Tier.SELF, wide=Tier.AUDITOR),
    "/api/alerts": Surface(Tier.SELF, wide=Tier.AUDITOR),
    # ── auditor: the fleet-wide READ surface (today's require_admin_tier) ────────────────────
    "/api/clusters/{cluster_id}/bindings/findings": Surface(Tier.AUDITOR),
    "/api/clusters/{cluster_id}/operator-configs": Surface(Tier.AUDITOR),
    "/api/clusters/{cluster_id}/kyverno": Surface(Tier.AUDITOR),            # D1
    "/api/kpi": Surface(Tier.AUDITOR),                                      # D1
    "/api/report/ticket": Surface(Tier.AUDITOR),                            # the ticket's claim stays "all" (D4)
    # ── admin: personnel data that lives only here (today's usage_scope) ────────────────────
    "/api/dashboard/activity": Surface(Tier.SELF, wide=Tier.ADMIN),
    "/api/dashboard/reports": Surface(Tier.SELF, wide=Tier.ADMIN),
    # ── cluster-admin: the cluster Secrets (T3; S1/S2 ship the routes) ──────────────────────
    "/api/clusterconfigs": Surface(Tier.CLUSTER_ADMIN_VIEW),
    "POST /api/clusterconfigs": Surface(Tier.CLUSTER_ADMIN_MANAGE),
    "PUT /api/clusterconfigs/{name}/credential": Surface(Tier.CLUSTER_ADMIN_MANAGE),
    "DELETE /api/clusterconfigs/{name}": Surface(Tier.CLUSTER_ADMIN_MANAGE),
    "POST /api/clusterconfigs/test": Surface(Tier.CLUSTER_ADMIN_MANAGE),
    # ── tabs, as index.html names them ──────────────────────────────────────────────────────
    "tab:home": Surface(Tier.SELF), "tab:lookup": Surface(Tier.SELF, wide=Tier.AUDITOR),
    "tab:overview": Surface(Tier.AUDITOR), "tab:kpi": Surface(Tier.AUDITOR),
    "tab:groups": Surface(Tier.SELF, wide=Tier.AUDITOR), "tab:users": Surface(Tier.SELF, wide=Tier.AUDITOR),
    "tab:bindings": Surface(Tier.SELF, wide=Tier.AUDITOR), "tab:policy": Surface(Tier.AUDITOR),
    "tab:kyverno": Surface(Tier.AUDITOR), "tab:nsaudit": Surface(Tier.SELF, wide=Tier.AUDITOR),
    "tab:logins": Surface(Tier.SELF, wide=Tier.AUDITOR), "tab:usage": Surface(Tier.SELF, wide=Tier.ADMIN),
    "tab:reports": Surface(Tier.AUDITOR), "tab:reporting": Surface(Tier.AUDITOR),
    "tab:clusters": Surface(Tier.CLUSTER_ADMIN_VIEW),
}

#: What each refused surface CONTAINS, one sentence per key, drawn after the tier's sentence in the
#: 403 detail and on the card (today's per-route prose, e.g. KPI_REFUSAL, moved here). Never a role,
#: grant, chart value or route.
SURFACE_WORDS: dict[str, str] = {}

#: The tab half of the table, in the page's order, served to the browser on /api/whoami as
#: `tabs` so the page never derives a tier (docs/ACCESS_CONTROL.md §7). The page reads it; a
#: static test holds index.html's `tab(...)` calls to exactly this set.
TAB_TIERS = {k.removeprefix("tab:"): v for k, v in TIER_BY_SURFACE.items() if k.startswith("tab:")}
```

```python
# gsd/api.py — inside build_app, replacing require_admin_tier and usage_scope (T2). One gate for
# every decided tier; viewer_scope keeps its per-cluster D2 logic and asks the AUDITOR resolver.

def tier_verdicts(request: Request) -> dict[Tier, bool]:
    """Every decided tier for this viewer on the host, each asked of ITS OWN resolver, fail closed.

    The whoami payload and the tab list are built from this; a handler never calls it — a handler
    asks require_tier for the one tier its surface declares, so a verdict is never computed for a
    surface nobody is reading (and the metrics count decisions actually served, as today).
    """
    return {tier: _grants(request, tier) for tier in DECIDED_TIERS}


def _grants(request: Request, tier: Tier, cluster_id: str | None = None) -> bool:
    """_decide's core, per tier: the exact positive answer and nothing else. Never raises."""
    if tier is Tier.AUDITOR:                       # the DECIDED tier per cluster, D2's rules unchanged
        return viewer_scope(request, cluster_id)[1] == TIER_ALL
    if not restrict and tier is Tier.ADMIN:        # restrictions off: Usage stays self (rule 4)
        return False
    viewer = trusted_viewer(request)
    resolver = (getattr(app.state, "tier_resolvers", None) or {}).get(tier)
    if not viewer or resolver is None:
        signals.note_decision(THRESHOLD_LABEL[tier], TIER_SELF)
        return False
    try:
        verdict = resolver.resolve(viewer)
    except Exception:  # noqa: BLE001
        log.exception("%s tier resolution failed for %r; refusing", tier.value, viewer)
        signals.note_decision(THRESHOLD_LABEL[tier], TIER_SELF)
        return False
    granted = verdict == TIER_ALL
    signals.note_decision(THRESHOLD_LABEL[tier], TIER_ALL if granted else TIER_SELF)
    return granted


def require_tier(request: Request, tier: Tier, cluster_id: str | None = None) -> None:
    """The gate every refused surface calls, with the tier TIER_BY_SURFACE declares for it.

    Refuses with the tier's own sentence FIRST (the card draws the same words), then what the view
    contains; never the role, grant, chart value or route that would widen it — this string
    reaches the person being refused. Counted before the raise, per tier.
    """
    if tier is Tier.SELF:
        return
    if not _grants(request, tier, cluster_id):
        signals.note_tier_refusal(THRESHOLD_LABEL[tier])
        raise HTTPException(status_code=403, detail=f"{REFUSAL_SENTENCE[tier]} {SURFACE_WORDS[request.url.path]}")
```

`viewer_scope` keeps its signature and every D2 rule (`gsd/api.py#viewer_scope`: `inherit`,
`self-only`, `remote-sar`, `hidden`, identity `none`), reading the **auditor** resolver — the one
question D2 decides per cluster (D7). The Usage routes call `require_tier(request, Tier.SELF)` for
existence and read their `scope` from `_grants(viewer, Tier.ADMIN)` behind the
`userActivity.visibility: all` override, in `usage_scope`'s present precedence.

**`/api/whoami`** (`gsd/api.py#whoami`) adds, additively (D6):

```json
"visibility": {"scope": "all", "enabled": true, "clusters": {"crc-local": {"policy": "inherit", "identity": "same-as-host", "scope": "all"}},
               "tiers": {"auditor": true, "admin": false, "cluster_admin": {"view": false, "manage": false}},
               "tabs": ["home", "overview", "kpi", "groups", "users", "bindings", "policy", "kyverno", "nsaudit", "logins", "usage", "reports"]}
```

`tabs` is `TAB_TIERS` filtered by the reader's verdicts (`reachable` granted; a scoped tab is always
present), in the page's order, with `reports`/`reporting` present only when reporting is on and
`clusters` only when S1's `clusterConfig.secrets.enabled` is on. `visibility.scope` keeps meaning
"the auditor tier on the host" so every client and test that reads it today is unchanged; the pill
reads `tiers` and says *Auditor view* / *Administrator view* / *Your view — name* instead of
*Full view — you are seeing everything* (the pill's current wording claims a tier that no longer
exists as one thing).

**The page** (`gsd/static/index.html`): the nav renders `data.whoami.visibility.tabs` and nothing
else (`gsd/static/index.html#TAB_TIERS` is not duplicated in the page — the page has no table of its
own, per ACCESS_CONTROL §7 "the UI never decides"); `navigate()` to a page id not in `tabs` renders
`refusalCard(title, what, tier)`, which now takes the tier and draws `REFUSAL_SENTENCE[tier]`'s
exact text (the API's `detail` leads with the same sentence — the parity `gsd/api.py#require_admin_tier`
records); `narrowedReader()` / `narrowedOnHost()` / `scopeFor()` keep reading `visibility.scope` and
`visibility.clusters[id].scope` (the auditor tier per cluster); the per-page fetch guards
(`gsd/static/index.html#narrowedOnHost`, the KPI, Reports, Kyverno and Overview branches of
`refresh()`) become one rule: fetch a tab's payload only when the tab is in `tabs`. Until whoami
answers, a tab keeps today's "Loading…" — never a refusal painted on an unknown tier
(`gsd/static/index.html#readerTierKnown`).

## Surface → tier: what changes under the model

Derived from every call site on main (`gsd/api.py`: `viewer_scope` on 18 lines — 17 handlers and
`require_admin_tier` itself — `require_admin_tier`
at 5 — `bindings/findings`, `operator-configs`, `kyverno`, `kpi`, `report_ticket` — and
`usage_scope` at 2 — `dashboard_activity`, `dashboard_reports`; `gsd/static/index.html`: the
`tab(...)` list in `renderFilters` and the tier branches of `render()` and `refresh()`):

| surface | gate on main | tier under the model | what changes |
|---|---|---|---|
| the public routes (`/metrics`, `/healthz`, `/readyz`, `/api/version`, the docs UIs, the page shell) | none | `self` (no identity) | nothing |
| `/api/whoami`, `/api/clusters`, `/groupsyncs`, `/groupsyncs/{name}/events`, `/groups`, `/groups/{name}`, `/users`, `/users/{name}`, `/logins`, `/cluster-access`, `/namespaces`, `/namespaces/{name}`, `/home`, `/user-bindings`, `/membership-changes`, `/binding-changes`, `/api/alerts` | `viewer_scope` (scoped or projected) | reachable `self`, whole at `auditor` | **name only**: `scope: all` is now "the auditor tier"; the question and every row served are identical |
| `/bindings/findings`, `/operator-configs`, `/kyverno`, `/api/kpi`, `/api/report/ticket` (+ `/report/**` by ticket) | `require_admin_tier` (`list clusterrolebindings`) | `auditor` | **name and refusal sentence**: the same question; the 403 leads *"For auditors and administrators only."*; the ticket's claim stays `all` (D4) |
| `/api/dashboard/activity`, `/api/dashboard/reports` | `usage_scope` (`update clusterrolebindings`) | reachable `self`, whole at `admin` | **name and knob**: the same question; the setting is `visibility.adminSar` (the present `usageAdminSar`, aliased one release) |
| tabs Overview, KPIs, RBAC policy, Kyverno, Reports (+ Reporting status) | rendered for everyone; a refusal card below the wide tier | `auditor`; **not rendered** below it | **rendering**: the tab button disappears below the tier (the #230 ruling), the URL still shows the card naming the tier; this supersedes the page's own comment that a hidden tab "reads as a broken build" (`gsd/static/index.html#A named refusal rather than a hidden tab`) |
| tabs Home, Groups, Users, Access granted, Namespace audit, Logins, Usage, Search | rendered for everyone, scoped | `self`, whole at `auditor` (Usage at `admin`) | nothing |
| the Cluster Configurations tab and its five routes (S1/S2, not on main) | `require_admin_tier` at first, then S1/S2's own pair per the #230 ruling | `cluster_admin:view` / `cluster_admin:manage` | T3 renames the settings and folds the pair into the registry; behaviour as S1/S2 ship it |

**No surface changes its question on main.** What #114 reported — the auditor role sees every
read tab — is the auditor tier *by ruling* (the Usage ruling: the auditor "keeps every wide audit
view it has today"), now named as such on the wire and on the pill, with the admin tier the named
place for what must exclude auditors: Usage today, the cluster credentials (S2), the bootstrap
controls (#238), and every administrator action to come. What the auditor role can and cannot
reproduce with `oc` is in the persona table: `lateef.o` reads users, groups and bindings with `oc`
and nothing else, yet the auditor tier serves him Kyverno findings, the operator's configs and the
login record. That is the operator's table, kept; D1 records the two unlisted surfaces.

## Migration (T2)

**Who loses access when `visibility.adminSar`'s default becomes `update clusterrolebindings`.**
Per persona, per surface at the admin tier after T2 (`/api/dashboard/activity`,
`/api/dashboard/reports`): those surfaces already ask `update clusterrolebindings` today
(`visibility.usageAdminSar`), so **nobody** — `kubeadmin` keeps the wide Usage view, `dana.lee`,
`lateef.o` and `bob.wilson` keep their own rows, as measured. Per surface at the auditor tier: the
question is unchanged, so nobody. The two deployments that DO see a change:

1. A values file that **set `visibility.adminSar` explicitly** (to `list groups`, say, the pre-0.4.0
   threshold, or to a site role). After T2 that value would govern Usage — a silent widening of a
   personnel dataset to whoever passed the old wide check. The chart therefore **refuses to render**
   an explicit `visibility.adminSar` whose `verb` is `get`, `list` or `watch` unless
   `visibility.compat.adminSarIsAuditorSar` is on, with a message that names the rename
   (`auditorSar`). Silent demotion or silent widening are the two failure modes every SAR guard in
   `_helpers.tpl` already exists to prevent; this is the same guard, one rung up.
2. A values file that **set `visibility.usageAdminSar`**. It is accepted for one release as an alias of
   `visibility.adminSar` with a NOTES line; set beside a differing `adminSar` it fails the render.

**The one-release compatibility knob — `visibility.compat.adminSarIsAuditorSar: true`** (app
`visibility_compat_admin_sar_is_auditor_sar`, env `GSD_VISIBILITY_COMPAT_ADMIN_SAR_IS_AUDITOR_SAR`).
With it on, the `adminSar` values govern the **auditor** tier and `usageAdminSar` (or its default)
governs the **admin** tier — byte-for-byte the pre-T2 mapping, for a GitOps-managed values file that
cannot be edited on the day. It is refused from the release after T2 (an unknown key fails the
render, as every unknown key does). The issue's phrasing, `adminSar` pointed back at `list`, is
**not** offered — it would admit the auditor to Usage (D3).

**What else reads the wide tier's verdict, and what each becomes:**

| reader of the verdict | today | after T2 |
|---|---|---|
| `gsd/metrics.py#note_tier_check` / `note_decision` labels (`gsd/metrics.py#TIER_THRESHOLDS` = `("admin", "usage")`) | `threshold="admin"` is the wide tier, `"usage"` the Usage tier | `THRESHOLD_LABEL`: `auditor`, `admin`, `cluster_admin_view`, `cluster_admin_manage`, every (threshold, outcome) and (threshold, tier) pre-seeded to 0; the shipped alert `templates/monitoring.yaml#GroupSyncDashboardVisibilityChecksFailing` and the Grafana panels select on `outcome` / `sum by (threshold, …)` and keep working; an operator's own query on `threshold="admin"` now reads the admin tier — said in the CHANGELOG |
| `gsd_visibility_admin_refusals_total` (`gsd/metrics.py#note_admin_refusal`) | one unlabelled counter for the wide gate | gains a `tier` label (`note_tier_refusal`), pre-seeded per decided tier; `sum(increase(…))` — the shipped panel — is unchanged |
| the report ticket (`gsd/api.py#report_ticket` → `gsd/reporting/ticket.py#mint`) | minted at `require_admin_tier` with the literal claim `all` | minted at `require_tier(Tier.AUDITOR)`; the claim stays `all` (D4); `docs/ACCESS_CONTROL.md` and `local-development/API.md#GET /api/report/ticket` say "the auditor tier" |
| the D2 remote resolvers (`gsd/api.py#build_app`, `remote_resolvers`) | constructed with `visibility_admin_sar_*` | constructed with `visibility_auditor_sar_*`; `docs/ACCESS_CONTROL.md#Several clusters in one instance` row for `remote-sar` says `visibility.auditorSar` |
| `/api/whoami` `visibility.scope`, `visibility.clusters[id].scope`; `/api/clusters` rows' `visibility.scope`; `/api/alerts` `scope` | the wide decision | the auditor decision, same values; `tiers` and `tabs` added |
| the page: `narrowedReader()`, `narrowedOnHost()`, `renderScopePill()`, the `tab(...)` list, the fetch guards | read `visibility.scope`; the nav is static; refusal cards below the wide tier | `scope` unchanged; the nav is `visibility.tabs`; the pill names the tier; a refused tab is absent and its URL shows the card naming the tier |
| `templates/rbac-auditors.yaml#gsd.visibilitySarVerb` — the guard that the chart's auditor role covers the wide check | reads `adminSar`; **would fail every default render after the flip** (`update` is a non-read verb) | reads `auditorSar` through the new helper family; the guard's sentence names `visibility.auditorSar` |
| `templates/NOTES.txt#This is a custom check (visibility.adminSar)` | prints the wide check | prints the auditor check, then the admin check, each with the personas it admits |
| `templates/configmap.yaml#visibilityAdminSarVerb` (and the four `visibilityUsageAdminSar*` keys) | two key sets | `visibilityAuditorSar*` added; `visibilityAdminSar*` re-pointed; `visibilityUsageAdminSar*` rendered from the alias for one release; `gsd/config.py#_visibility_sar_setting` / `#_usage_visibility_sar_setting` become one `_tier_sar_setting(raw, tier)` |
| `charts/group-sync-dashboard/README.md#visibility.usageAdminSar` rows, the `rbacAuditors.*` rows ("reaches the wide report tier", "Must cover the `visibility.adminSar` gate") | name the two thresholds | name the four tiers; `rbacAuditors` reaches **the auditor tier**; `existingClusterRole` must cover `visibility.auditorSar` |
| `docs/ACCESS_CONTROL.md#The two thresholds` (§2), §3, §4, §7, §11; `local-development/API.md#GET /api/whoami`; `docs/SPEC_per_user_visibility.md`'s dated line; `docs/SPEC_usage_admin_tier.md` | two thresholds | four tiers, each doc's table re-keyed by tier name; the old docs keep their reasoning as the record of why the bars differ, with a dated line pointing here |
| tests: `local-development/tests/test_visibility.py#_usage_app` (the two seams), `#TestUsageAdminTier`, `tests/test_metrics.py`'s label assertions, `tests/test_activity.py`'s exact-equality whoami body | `app.state.tier_resolver`, `app.state.usage_tier_resolver`; `threshold="admin"`/`"usage"` | `app.state.tier_resolvers[Tier.X]`; the new labels; whoami gains `tiers`/`tabs` (the body "written so that a new key comes to it for a ruling" — this is the ruling) |

**Does `/api/whoami`'s payload change shape?** Additively only: `visibility.tiers` and
`visibility.tabs` appear beside the present keys; nothing is renamed or removed (D6). The
`gsd/api.py#report_ticket` and `/api/dashboard/*` payloads are unchanged.

**The CHANGELOG sentence** (`docs/CHANGELOG.md#Unreleased`, T2's entry):

> **Named dashboard tiers (#239, closes #114; app 0.x.0, chart 0.y.0).** The two thresholds are four
> named tiers, each its own SubjectAccessReview, own resolver and cache, fail closed: `self`,
> `auditor` (`visibility.auditorSar`, default `list clusterrolebindings` — today's wide check, so
> `cluster-reader` and the chart's `rbacAuditors` role keep every read tab), `admin`
> (`visibility.adminSar`, **default now `update clusterrolebindings`** — today's Usage check, so
> `cluster-admin` alone widens Usage), and `cluster_admin` (view/manage on the dashboard's Secrets,
> #230). No reader gains or loses a row by default. `/api/whoami` reports `visibility.tiers` and the
> tabs the reader may open; tabs a tier does not grant are not rendered and a link to one shows the
> refusal naming the tier. **Upgrade:** a values file that set `visibility.adminSar` explicitly must
> rename it `visibility.auditorSar` (the chart refuses a read-verb `adminSar`); `visibility.usageAdminSar`
> is accepted as an alias of `adminSar` for this release; `visibility.compat.adminSarIsAuditorSar: true`
> keeps the old mapping for this release only. Metrics: the `threshold` label reads `auditor`
> (was `admin`) and `admin` (was `usage`); `gsd_visibility_admin_refusals_total` gains a `tier` label.

## Tests

**The oracle.** `local-development/mock-app/mock_app/sar.py#SarAuthorizer` evaluates the fixture's
real RBAC graph (ClusterRoles, ClusterRoleBindings, namespaced Roles and RoleBindings — a namespaced
Role resolves to the binding's namespace) against the exact `spec.groups` `gsd/kube.py` sends, over
TLS, so every case below is the whole path and not a stub. `reference.yaml` gains three subjects
for T3, mirroring what CRC measured:

| persona | fixture RBAC | auditor | admin | cluster_admin:view | cluster_admin:manage |
|---|---|---|---|---|---|
| `kubeadmin` | `cluster-admin` CRB | yes | yes | yes | yes |
| `dana.lee` | `cluster-reader` CRB (read verbs, no `update`, nothing on secrets) | yes | no | no | no |
| `developer` | the `…-report-auditors` group → the chart's auditor role | yes | no | no | no |
| `lateef.o` | no admin binding | no | no | no | no |
| `jane.smith` | the decoy: in a group NAMED `…-cluster-admin`, no binding behind it | no | no | no | no |
| `platform.admin` (new) | CRB to ClusterRole `admin` cluster-wide — `john.doe`'s measured shape | no | no | **yes** | **yes** |
| `secret.viewer` (new) | RoleBinding in the dashboard's namespace to a Role with `get,list` on secrets | no | no | yes | no |
| `system:serviceaccount:<ns>:group-sync-dashboard` | the reader role + `system:auth-delegator` | no | no | no | no |

`local-development/mock-app/tests/test_sar_personas.py#ORACLE` becomes persona × four questions
and asserts this table through `ClusterClient.create_subject_access_review`.

**A case per persona per surface** — `tests/test_tiers.py` (new), parametrised over
`TIER_BY_SURFACE` × the personas, with the resolvers stubbed per tier through
`app.state.tier_resolvers` from the oracle table (the `_usage_app` pattern generalised): for a
refused surface the persona at the surface's tier gets 200 and the persona one rung below gets 403
whose `detail` **starts with** `REFUSAL_SENTENCE[tier]` (the leading-sentence rule
`tests/test_view_scoping.py` already holds); for a scoped surface the persona at `wide` gets
`scope: all` and every lower persona `scope: self` with their own rows only. The expected tier per
surface lives in the **test file's own copy** (`EXPECTED`), asserted equal to `TIER_BY_SURFACE` — so
a mutant that edits either the table or a route fails.

**A mutant per surface.** Reverting any route from `require_tier(Tier.X)` to a lower tier makes the
one-rung-below persona 200 where `EXPECTED` says 403 → fails. Two static tests pin the plumbing:
`require_admin_tier` and `usage_scope` no longer exist in `gsd/api.py` (T2), and every path in
`app.routes` and every `tab("…")` in `index.html` is a key of `TIER_BY_SURFACE` (the pattern of
`tests/test_multicluster_visibility.py#test_access_control_section_11_names_only_routes_the_app_serves`
and `tests/test_api_contract.py`'s "API.md must name every route"). `tests/test_api_contract.py#test_r6_the_api_is_read_only`
must be amended by S2 for its five write routes; T3 adds nothing to that list.

**The page** (`tests/test_ui.py`, Playwright, per persona through the `X-Forwarded-User` header and
stubbed resolvers): the rendered `nav.tabs` equals `visibility.tabs`; `#page=<refused tab>` by URL
paints exactly one `.scope-refusal` whose text begins with the tier's sentence and makes **no**
request for the tab's payload (the `test_a_narrowed_reader_does_not_fetch_the_fleet_tables`
pattern); the pill reads *Auditor view* for `dana.lee`, *Administrator view* for `kubeadmin`,
*Your view — lateef.o* for the plain reader; the two independence tests of
`tests/test_visibility.py#TestUsageAdminTier` are kept verbatim under the new seams — *the* test
(`cluster-reader` wide on `/groups`, self on Usage in one session) is what proves the tiers are
independent, and it must not move.

**Metrics pre-seeding** (`tests/test_metrics.py`): at startup every
`(threshold ∈ THRESHOLD_LABEL.values(), outcome)` of `gsd_visibility_tier_checks_total`, every
`(threshold, tier ∈ {all, self})` of `gsd_visibility_decisions_total` and every `tier` of
`gsd_visibility_admin_refusals_total` is present at 0 before any request — the FINDINGS discipline
`gsd/metrics.py` states — and the old label values `admin`-as-wide and `usage` do not appear.

**The chart** (`tests/test_chart_*.py`): the default render carries `auditorSar` at `list` and
`adminSar` at `update`, the auditor-role guard reads `auditorSar` and the default render passes it;
an explicit read-verb `adminSar` without the compat knob fails with the rename message; `usageAdminSar`
alone renders as `adminSar` with the NOTES line; `usageAdminSar` beside a differing `adminSar` fails;
the compat knob swaps the mapping and is refused the release after; `visibility.enabled=false` still
drops the `system:auth-delegator` binding and every SAR key.

## Decomposition — three pull requests, each its own three-seat review

**T1 — the registry** (additive; app minor, chart minor). `gsd/tiers/` (`Tier`, `DECIDED_TIERS`,
`THRESHOLD_LABEL`, `REFUSAL_SENTENCE`, `Surface`, `TIER_BY_SURFACE`, `TAB_TIERS`); `gsd/config.py`
`visibility_auditor_sar_*` (default `list clusterrolebindings`) beside the two present families,
`_tier_sar_setting`; `gsd/api.py#build_app` constructs one resolver per decided tier into
`app.state.tier_resolvers` (the auditor resolver from the auditor settings, the admin resolver from
the **present** `usageAdminSar` values — T1 changes no default), `tier_verdicts`, `require_tier`,
`/api/whoami` `tiers` + `tabs`; `gsd/metrics.py` the new labels pre-seeded, `note_tier_refusal`;
`index.html` renders `visibility.tabs`, `refusalCard` takes the tier; chart `visibility.auditorSar`
values, helpers, ConfigMap keys, README rows; `tests/test_tiers.py`, the UI tests, the oracle
extension. **Behaviour on T1's head is identical to main for every persona** — the registry
exists, `require_admin_tier` and `usage_scope` still gate, and a test asserts the two agree on
every surface. Verification: `release-crc.sh`, the persona walk (`kubeadmin`, `dana.lee`,
`lateef.o`) with screenshots of the nav and one refusal card each, under
`reports/<date>_tier-model-T1/`.

**T2 — migrate the existing gates; closes #114** (app minor, chart minor). Every
`require_admin_tier` call → `require_tier(request, Tier.AUDITOR, cluster_id)`, both `usage_scope`
callers → the admin verdict (`_grants(request, Tier.ADMIN)` behind the `userActivity.visibility: all`
override), the two old functions deleted; `visibility.adminSar` default →
`update clusterrolebindings`, `usageAdminSar` → the one-release alias, the read-verb guard, the
compat knob; `rbac-auditors.yaml`, NOTES, the D2 remote resolvers, the ticket's gate, the docs
table above, the CHANGELOG entry; the metrics labels renamed. Verification on CRC: the persona
table re-measured through `/api/whoami` for the four real subjects, the `rbacAuditors` default
render on the lab, an upgrade from the previous chart with an explicit `adminSar` (refused) and with
the compat knob (old mapping), `reports/<date>_tier-model-T2/`; #114 closed with the comment naming
the release.

**T3 — the cluster-configuration tier folds in** (after S1 and S2 merge; app minor, chart minor).
`visibility_clusterconfig_{view,manage}_sar_*` → `visibility_cluster_admin_{view,manage}_sar_*` and
`visibility.clusterConfig{View,Manage}Sar` → `visibility.clusterAdminSar.{view,manage}`, each with a
one-release alias by the T2 mechanism; S1/S2's two resolvers move into `app.state.tier_resolvers`
under the two `Tier` members; the five routes and `tab:clusters` are already in `TIER_BY_SURFACE`
(T1 ships the rows; until T3 they are asserted absent from `app.routes` when `clusterConfig` is off,
present and gated by S1/S2's own pair when on); the two new personas and the `admin`/`edit`
README sentence; #238's controls declare `Tier.CLUSTER_ADMIN_MANAGE` when they land. If S1/S2 are
still open when T1 merges, they take the final names directly and T3 is the fold alone.
