# Review record — clusters as labelled Secrets (#230 S1, PR #235)

Branch `feat/230-cluster-secrets`. Four seats, because the operator lifted the budget for this one
(2026-09-20) and Fable draws on a separate pool: **Cursor Grok 4.6** (ask mode, from source),
**Codex GPT-5.6 xhigh** (a `git archive` export with the venv; TestClient probes, mutants run,
`helm template` both switch states), **OB3** (Opus 5, the live repository) and a **Fable seat (OB2)**
scoped to the three areas worth a fourth opinion — the tier gate, the TLS modes, the no-credential
pins. A separate OB2 **design** pass reviewed the tier as a design and is the source of the ordering
finding below.

Every fix was traced before it was applied; two were taken on the fact and re-implemented, because the
proposed mechanism did not hold.

## Claims × decision

| # | Claim | Grok | Codex | OB2/OB3 | Decision |
|---|---|---|---|---|---|
| C1 | No route but the gated one carries the wiring | CONFIRMED | CONFIRMED (probe: `/api/clusters`, `/api/kpi`, `/metrics`, `/readyz` carry zero occurrences) | — | Holds; re-measured live (`validate-tier.sh` §3). |
| C2 | Fail-closed is exhaustive | **REFUTED** — `if not restrict: return TIER_ALL` | **REFUTED**, same line | — | **Accepted.** The short-circuit is gone and the resolvers are built regardless of `visibility.enabled`; Usage's precedent (stays self when restrictions are off) is the one this surface follows, and it goes further by still asking so a cluster-admin keeps the tab. Pinned by `test_restrictions_off_does_not_open_the_surface` (fails on the old code — mutant-checked). |
| C3 | The two levels are independent | CONFIRMED | CONFIRMED (`same_instance False`, `same_cache False`) | — | Holds; the missing pin is now `test_build_app_constructs_two_resolvers_with_two_questions_and_two_caches`. |
| C4 | The default questions are right | PLAUSIBLE (no live `oc` in ask mode) | **REFUTED** — an unknown pod namespace silently became a **cluster-scoped** `get secrets` | — | **Accepted**: with no namespace and no explicit setting the gate refuses and says why, rather than asking a broader question than the operator configured. Pinned. |
| C5 | The Secret contract vs Argo's | CONFIRMED | REFUTED on unsupported top-level keys | OB2: Argo's scope keys read as a FULL cluster | **Accepted**: `namespaces`, `clusterResources`, `project`, `shard` refused with the key named — a Secret copied from Argo declaring a narrowed cluster must not be silently over-read. |
| C6 | Precedence, retirement, the in-cluster rule | **REFUTED** on two races | CONFIRMED | OB2: duplicate names are a hijack vector | **Accepted both**: a failed start-up LIST no longer retires Secret-sourced rows (on a fresh process the registry has no previous set, so one timeout would have retired the fleet); and a duplicate cluster name now loads **neither** Secret, each a finding naming the other — "first by `metadata.name` wins" let a Secret named to sort first replace another's server and token. |
| C7 | The three TLS modes and the refusal | CONFIRMED | **REFUTED** — explicit empty `caData` bypassed the refusal and silently became the trusted-bundle mode | — | **Accepted**: the refusal now tests the key's **presence**, not its truthiness; an empty `caData` is a malformed declaration with its own finding. |
| C8 | The credential never leaves the Secret | CONFIRMED (paths traced) | **REFUTED** — a remote that echoes the request puts our own token in `response.text`, which `_get` copies into the error, `record_poll` stores and `/api/clusters` serves | — | **Accepted**: `ClusterClient._redact()` strips the cluster's own credential from diagnostics before they are quoted — the remote controls its error bodies, and the token is the one string we can always recognise. Pinned with a mock remote that echoes the Authorization header. |
| C9 | The chart | CONFIRMED | CONFIRMED (`get/list/watch` only, both switch states render) | — | Holds. |
| C10 | The migration and its pins | REFUTED on the dashboard's clarity | REFUTED — no rollback refusal | — | **Deferred, said**: the report service already refuses a newer snapshot with a clear message (measured this session when two branches met on one lab); the dashboard's own refusal is filed rather than bolted on at the end of this PR. |
| C11 | Tests as mutant pins | REFUTED — 2 survive | REFUTED — the shared-resolver mutant survived | — | **Accepted**: both surviving mutants are now pinned, and every pin in this record was re-run against its mutant before being called a pin. |
| — | **The ladder is not ordered** | — | — | **OB2 design pass, REFUTED** | **Accepted, re-implemented.** See below. |

## The ordering finding — accepted, then reversed by the operator

**Superseded (2026-09-20, later the same day).** The operator: *"A user with cluster admin and auditor
is fine. That is how Kubernetes RBAC works. As long as the user has the role needed or can get the right
SAR needed, we are good."* The composition below was removed; each level asks its own question alone.
The reasons are in `docs/specs/SPEC_S1_cluster_secrets.md` — RBAC is additive; the SAR asks the action's
own question, so anyone who passes it can do the thing with `oc` and the ServiceAccount is not a confused
deputy; and the auditor ruling holds without composition, measured. **Everything else the review earned
is kept** (C2, C4, C7, C8, C6, the duplicate-name and Argo-key refusals) — those are the real protections.

The finding is recorded because what it measured is still true and still shapes the contract: these
questions are not a *higher* bar than the wide tier, they are the bar that matches the action.

## The ordering finding as it was argued, and the one deviation

OB2's design pass measured what the other seats did not ask: `get`/`create secrets` in a namespace is
held by the stock `admin` ClusterRole, so asked **alone** the two questions are not a higher bar than
the wide tier but a *different* one. Re-measured here before applying — a member of
`app-ocp-rbac-alpha-cluster-admin`, bound to `ClusterRole/admin` by one of the lab's **seven** such
ClusterRoleBindings:

```
oc auth can-i list clusterrolebindings   --as-group=app-ocp-rbac-alpha-cluster-admin  -> no
oc auth can-i update clusterrolebindings --as-group=app-ocp-rbac-alpha-cluster-admin  -> no
oc auth can-i get    secrets -n group-sync-dashboard                                   -> yes
oc auth can-i create secrets -n group-sync-dashboard                                   -> yes
```

That reader is narrowed to `self` on every other tab and would have held the fleet's credential store.
The gate is now **ordered**: the administrator rung first, then the level's own question.

**Deviation from OB2's patch, on the fact but not the mechanism.** Its snippet used
`usage_scope(request)[1] != TIER_ALL` as the rung. That rung dissolves in two supported configurations:
`usage_scope` returns `TIER_ALL` for *every* viewer when `userActivity.visibility: all` (its documented
blunt override), and `viewer_scope` widens for everyone when `visibility.enabled` is off. Neither is a
statement about who administers the cluster, which is all the rung asks — so the administrator question
is asked **directly** through `_decide`, past both escape hatches. Pinned by
`test_the_admin_rung_is_asked_directly_past_both_escape_hatches`, which fails against OB2's own shape.

## Re-validation

Hermetic and UI suites green with every fix in (totals in the PR comment); `helm lint` and both switch
states render. On CRC: the auditor persona passes the wide tier and is refused here, the refusal names
no cluster, Secret or namespace, no other route carries the wiring, the three TLS-mode clusters still
poll and the `caData`+`insecure` Secret is still a finding — `reports/2026-09-20_cluster-secrets-230/`.
