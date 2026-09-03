# Review: the administrator tier, and the ruling it reverses

Branch `feat/per-user-visibility`, head `03ad446`. Suite **1197 passed / 0 failed**
(`cd local-development && .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py`).

This document is the brief for an adversarial review. §1–§6 are the context and the claims. §7 is
what the review must produce, and it writes into §8 of **this file** — no new document.

---

## 1. What the feature is for

Until release 102 every authenticated reader of this dashboard saw every user's group memberships,
every grant, and every login attempt. The per-user visibility feature restricts a reader to their
own, and widens to the whole cluster only for a reader an OpenShift SubjectAccessReview admits.
It is a **fix for an over-exposure**, not a new capability.

The tier is decided by a SAR carrying both `spec.user` and `spec.groups`. The groups are
load-bearing: a reader granted cluster-admin through a Group rather than a direct binding is
refused when `spec.groups` is absent. Verified live from inside the pod with its own projected
ServiceAccount token:

```
POST /apis/authorization.k8s.io/v1/subjectaccessreviews -> 201
"allowed": true,
"reason": "RBAC: allowed by ClusterRoleBinding \"demo-cluster-admin-crb\"
           of ClusterRole \"cluster-admin\" to Group \"app-ocp-rbac-demo-cluster-admin\""
```

Decision cached 60s per viewer. A **failure is never cached**, so an API-server outage does not pin
every reader to the narrow view until a TTL expires. Everything indeterminate serves `self`.

## 2. What the operator asked for, in their words

> "I like your current work with on how the user can see only their groups, namespace audit, logins
> and usage and as currently spec but we need to gate and restrictions the overview, access granted
> and rbac policy page/tab is only for the admins as stated --> this page should say 'FOR ADMINS
> only' when this users login."

So: **Groups, Namespace audit, Logins, Usage** keep their self-scoped behaviour. **Overview, Access
granted, RBAC policy** become administrator-only and must say so.

## 3. The measurement that reversed our own ruling

Spec Q3 ruled that GroupSync CR health, operator configuration and unmanaged-grant findings were
"governance data about objects, not people" and served them **whole at both tiers**. I wrote that
ruling. It does not survive measurement.

`lateef.o` is an ordinary reader on the reference cluster (CRC), member of
`app-ocp-rbac-lateef-ns-developer` and `app-ssb-autobahnusers`:

```
oc auth can-i list clusterrolebindings --as=lateef.o   -> no
oc auth can-i list rolebindings        --as=lateef.o   -> no
oc auth can-i list groups              --as=lateef.o   -> no

GET /api/clusters/crc-local/bindings/findings  (X-Forwarded-User: lateef.o)
  -> 236 rows, scope="all"
  -> 21 name an admin role, including:
       app-ocp-rbac-alpha-cluster-admin -> admin (app-ocp-rbac-alpha-cluster-admin-crb)
       app-ocp-rbac-demo-cluster-admin  -> admin (app-ocp-rbac-demo-cluster-admin-crb)
```

A binding row names which **group** holds which **role**. The payload is therefore a list of which
group to join to gain admin — obtainable through the dashboard and **not** with `oc`.

`charts/group-sync-dashboard/values.yaml` already records this exact escalation for the
**bearer-token** path, where gating `/api` on `list groups` is called *"WRONG — a privilege
escalation, proven on the reference cluster"* and the floor was raised to cluster-wide RBAC read.
That floor never reached the **browser** path, because `-openshift-delegate-urls` governs bearer
tokens and client certificates only; cookie sessions bypass it entirely. The fix applies the same
floor where it was missing.

## 4. Why `groupsyncs` is deliberately NOT gated

`/metrics` is in the chart's `skipAuthRegex` and is served unauthenticated. Fetched from a laptop
with no credential against the live route:

```
gsd_groupsync_state{cluster="crc-local",groupsync="ldap-groupsync",namespace="group-sync-operator",state="ok"} 1.0
gsd_groupsync_last_sync_timestamp_seconds{...,groupsync="ldap-groupsync",...} 1.786316412e+09
gsd_groupsync_groups_total{...,groupsync="ldap-groupsync",...} 41.0
gsd_groups_total{cluster="crc-local"} 65.0
gsd_bindings_total{cluster="crc-local",finding="unresolved"} 9.0
```

So per-CR identity and state, and every aggregate count, are **already world-readable on that
route**. `/metrics` exposes **no** group names, usernames or binding subjects — I grepped for
`app-ocp-rbac`, `lateef`, `john.doe`, `jane.smith` and matched only GroupSync CR names.

Consequences taken as decisions:

- Gating `/groupsyncs` would be **theatre** while that holds, and would cost the Groups tab its
  per-provider colour slots (`crSlot` reads `data.groupsyncs`; it degrades to text, but for nothing).
- Withholding the Overview cluster-card counts (`group_count: 65`, `builtin_bindings: 150`) would
  likewise be theatre — `gsd_groups_total` and `gsd_bindings_total` publish them unauthenticated.
  **I did not withhold them**, and the Overview tab is refused wholesale instead.
- **Open question for the operator, not fixed here:** whether `/metrics` should stay on the public
  route at all. It is a deliberate skipAuthRegex entry for Prometheus scraping.

## 5. What is implemented at `03ad446`

Server (`local-development/gsd/api.py`):

- New `require_admin_tier(request)` beside `require_viewer`, raising 403 with a detail naming
  itself: `"…reserved to the administrator tier"`. Carries the measurement in its docstring.
- `binding_findings` — `require_admin_tier` added; docstring records the Q3 reversal.
- `operator_configs` — `require_admin_tier` added; docstring notes there is no `/metrics` analogue,
  so unlike CR health this was a genuinely private view left open.
- `list_groupsyncs`, `list_events` — **unchanged**, per §4.
- `/api/clusters`, `/api/alerts` — unchanged. Alerts were already scoped (0 rows for `lateef.o`,
  3 for `john.doe`). `/api/clusters` must stay reachable: the cluster selector needs it on every tab.

UI (`local-development/gsd/static/index.html`):

- New `narrowedReader()` reading `whoami.visibility.scope` — the same server-computed source
  `renderScopePill` uses. The page still never *decides* a tier. Absent declaration is treated as
  **not** narrowed, because the endpoints are the control.
- Overview render branches to `refusalCard("Overview", …)` for a narrowed reader.
- `operator-configs` fetch wrapped in the existing `guard403`, so the designed 403 does not replace
  the tab with "Dashboard API error: 403 Forbidden".
- The **already-existing** refusal cards for "Access granted" and "RBAC policy" now fire, because
  something finally refuses. All three carry `<strong>For administrators only.</strong>`.

Tests:

- `test_view_scoping.py`: the old `test_governance_endpoints_stay_full_view_at_self` is replaced by
  three — the RBAC surface is refused at self; the admin still gets it whole; CR health stays full
  view *with the /metrics reason in the docstring*.
- `test_ui.py`: two waits moved from `.hero .value` to `#main .card`, because a narrowed reader's
  landing page paints a refusal card and no cluster hero.

## 6. Known gaps, stated so the review does not have to find them

1. **Docs still assert the reversed ruling.** `docs/REQUIREMENTS_per_user_visibility.md:57` says
   findings are "governance data; see §6 Q3", §6 Q3 itself still argues the old position, and
   `local-development/API.md` says "Three endpoints do not vary by tier at all" naming
   `bindings/findings` and `operator-configs`. `docs/SPEC_per_user_visibility.md` likewise.
2. **`list_groupsyncs`'s docstring** still says "FULL VIEW AT BOTH TIERS, by ruling (spec Q3)" —
   still true for that endpoint, but the Q3 cross-reference now points at a partially reversed
   ruling and should say why *this* endpoint is the surviving half.
3. **Access granted is only refused via `findings`.** The tab's sole fetch is
   `bindings/findings`, so gating that endpoint gates the tab. Confirm there is no second path in.
   *Held until 2026-09-03.* The tab now has a second fetch at the narrowed tier — the reader's own
   `/users/{name}`, which serves their own bindings with `via_group` and refuses anyone else's name
   before any lookup — and renders their own grants where the refusal card was. The endpoint gate
   is unchanged: `bindings/findings` still refuses a plain reader with the same sentence, the
   refusal is still counted on `/metrics`, and the card still renders when the tier cannot be
   established (whoami unavailable). RBAC policy keeps its refusal.
4. **Not rebuilt or redeployed.** Live verification of these three tabs as `lateef.o` has not
   happened yet. Release 102 on CRC runs `0.6.0-6ed5d8ade9`, which predates this commit.
5. **`data.alertsScope`** is set by the loader and consumed by no renderer. Pre-existing.

## 7. What this review must do

Prefer refutation. For each claim below, return exactly one verdict — **CONFIRMED**, **REFUTED**, or
**FIX-INADEQUATE** — and say what you actually ran. "Cannot refute" is acceptable only with the
command and its output.

- **C1** `require_admin_tier` cannot be bypassed. Try: no `X-Forwarded-User`; a forged header with
  the proxy off; restrictions disabled; a resolver that raises; a resolver returning junk; the
  `?limit=`/`?offset=` variants; trailing-slash and case variants of the path; HEAD and OPTIONS.
- **C2** No **other** endpoint still hands the RBAC binding surface, or any subject-to-role mapping,
  to a self-tier reader. Enumerate every route and check. `user-bindings` is *supposed* to be
  reachable and self-scoped — confirm it is genuinely scoped and not merely aggregate-withheld.
- **C3** The administrator loses nothing. Every endpoint an admin could reach at `03ad446`'s parent
  still returns the same payload for an admin.
- **C4** The proxy-off deployment is unchanged. Restrictions on with no proxy serves wide + warns;
  the new gate must not turn a proxy-less install into a 403 wall. Compare against `origin/main`.
- **C5** The UI refusal is reachable and correct for all three tabs, and no tab renders a blank or a
  generic error card at the self tier. Include the drill-down entries into those tabs (there are
  cross-links from Groups into Access granted / RBAC policy — check `view.group` deep links).
- **C6** `narrowedReader()`'s fail-open default (absent declaration ⇒ not narrowed) cannot show a
  narrowed reader the Overview *data*. The endpoints must be the real control; prove it.
- **C7** The `/metrics` reasoning in §4. Verify the metric names and that no group name, username or
  binding subject appears. If any does, that is a finding and gating `/groupsyncs` changes.
- **C8** Any NEW finding nobody asked about. Attacker's eye: what does a self-tier reader still
  learn that they could not learn with `oc` as themselves?

Every finding must carry: `file:line-or-symbol`, a concrete trigger (state, sequence, input — not
"could race"), the consequence stated as **what a reader of the dashboard would believe that is
false**, the complete replacement code ready to apply (not a fragment, not "add a check"), and a
complete test function that fails before and passes after. Preserve this codebase's comment style:
comments say WHY, never WHAT, and stripping the reasoning out of a replacement is a regression even
when the logic is right.

**Do not apply anything in this pass.** Findings and proposed code into §8 below, under
`> **Fable:**` markers. The arbiter applies changes after reading them.

Scope discipline: `charts/` and `environments/` are **out of scope** for this pass — no chart change
is proposed and the render matrix is already verified. Touch files outside
`local-development/gsd/`, `local-development/tests/`, `docs/` and `local-development/API.md` only if
a finding genuinely requires it, and say so explicitly.

---

## 8. Findings

> **Fable:** Reviewed at `03ad446`, in-process TestClient over the worktree package
> (`gsd.__file__` confirmed to be the worktree copy, not the main checkout) plus the live
> revision 103 (`0.6.0-03ad446380`, same commit) via `oc exec` and the unauthenticated
> `/metrics` route. Every claim below is backed by a command I ran; the throwaway probes
> lived under `/tmp`, never in the worktree.
>
> **Verdicts:** C1 CONFIRMED · C2 **FIX-INADEQUATE** · C3 CONFIRMED · C4 CONFIRMED ·
> C5 CONFIRMED · C6 CONFIRMED · C7 CONFIRMED · C8 one MEDIUM finding (same root as C2) +
> one LOW note. **One finding total, severity MEDIUM.**
>
> ---
>
> ### C1 — the gate cannot be bypassed. CONFIRMED.
>
> Built a proxied, restrictions-on app (no resolver wired ⇒ self) and hit
> `/api/clusters/c1/bindings/findings` every way §7 lists:
>
> ```
> no X-Forwarded-User            -> 403
> self header (lateef.o)         -> 403
> self + ?limit=1&offset=0       -> 403
> trailing slash                 -> 403   (307 -> canonical path -> gate)
> case variant path (BINDINGS)   -> 404
> HEAD                           -> 405
> OPTIONS                        -> 405
> unknown cluster (self)         -> 404   (require_cluster runs first)
> resolver RAISES                -> 403
> resolver returns junk('administrator') -> 403
> admin resolver ('all')         -> 200
> ```
>
> Every indeterminate path lands on 403; only the exact string `"all"` from the resolver
> opens it, which is the `viewer_scope` discipline (`api.py:251-253`) applied through
> `require_admin_tier` (`api.py:293-301`). HEAD/OPTIONS 405 rather than falling through to an
> ungated handler. The `unknown cluster -> 404` before the tier check is a cluster-existence
> signal, but `/api/clusters` already lists every cluster to every reader, so it discloses
> nothing new. Live cross-check on revision 103 agreed: `lateef.o` and `jane.smith` 403,
> `john.doe` 200 with 236 rows.
>
> ### C2 — another endpoint still hands the RBAC binding surface to self. FIX-INADEQUATE.
>
> This is the finding. The gate closed `/bindings/findings` and `/operator-configs`, but
> **`/api/alerts` is the alternate path around it** and was not touched. See finding **F1**
> below for the full write-up, trigger, replacement and test.
>
> Everything else in the route enumeration is genuinely scoped, verified live and in-process:
>
> | route | self-tier behaviour | how verified |
> |---|---|---|
> | `/api/clusters` | aggregates only, no names/rows | read payload; counts, no subjects |
> | `/groupsyncs`, `/groupsyncs/{n}/events` | CR health, ungated by design (§4) | 200, no subject→role |
> | `/groups`, `/groups/{n}` | own groups; detail **member-gated** | non-member of `secret-group` → 403 *before* existence, so its live `secret-group`→cluster-admin binding is never disclosed |
> | `/users`, `/users/{n}` | own row / own profile only | 403 for others, byte-identical to nonexistent |
> | `/logins`, `/cluster-access`, `/membership-changes` | self-scoped, aggregates withheld as `None` | existing suite + probe |
> | `/user-bindings` | **row-scoped, not aggregate-withheld** | see premise check below |
> | `/bindings/findings`, `/operator-configs` | 403 | C1 |
> | `/api/alerts` | filtered by `SELF_ALERT_KINDS` — **leaks 2 kinds** | **F1** |
>
> **Premise re-checked (§7.3): `user-bindings` is per-reader scoped, not merely
> aggregate-withheld.** Seeded a binding for `lateef.o` (`edit`) and one for `jane.smith`
> (`admin`); as `lateef.o`:
>
> ```
> scope=self  rows=[('lateef.o','edit')]  total=1  by_namespace=None  excluded_platform=None
> ```
>
> The `jane.smith` **row is absent**, not present-with-hidden-aggregates, and `total` is the
> viewer's own 1, not the cluster's 2 (`api.py:1132-1139`, `me` bound into both the count and
> the row query). Premise holds.
>
> ### C3 — the administrator loses nothing. CONFIRMED.
>
> The diff adds exactly one line to each gated handler (`require_admin_tier(request)`), which
> for an admin resolves to `scope=="all"` and returns; the return blocks are unchanged but
> for comments. Measured with an `all`-resolver app: `/bindings/findings` → 200, `scope=all`,
> full `total`, `viewer` stamped; `/operator-configs` → 200, `scope=all`. Live: `john.doe`
> gets 236 binding rows and 11 operator configs.
>
> ### C4 — the proxy-less install is unchanged. CONFIRMED.
>
> `origin/main` has no `require_admin_tier` at all and its `operator_configs` is not even
> tiered (`def operator_configs(cluster_id: str)`), so it served both endpoints wide. On the
> branch with `oauth_proxy_enabled=False`, `restrict` is False (`api.py:205`) so `viewer_scope`
> returns `"all"` unconditionally and the gate is a no-op:
>
> ```
> proxy off + restrictions on, forged header -> bindings/findings 200 scope=all
> proxy off                                   -> operator-configs  200 scope=all
> ```
>
> The new gate does **not** turn a proxy-less install into a 403 wall — same wide behaviour as
> `origin/main`.
>
> ### C5 — the UI refusal is reachable and correct for all three tabs. CONFIRMED.
>
> All seven tabs render at every tier (`index.html:642-649`, no tier condition), so the three
> admin-only tabs are **visible and refuse by name**, never hidden:
> - Overview: `render()` `narrowedReader()` branch → `refusalCard("Overview", …)` (`index.html:2467-2475`).
> - Access granted: `bindingsPage()` sees `data.findings.forbidden` (from `guard403`) → `refusalCard("Access granted", … For administrators only.)` (`index.html:1885-1887`).
> - RBAC policy: `policyPage()` sees `data.findings.forbidden` → `refusalCard("RBAC policy", …)` + `configHealth(oc)` (`index.html:2014-2016`).
>
> Drill-down deep links are safe: `wireDrilldown()` sets `page:"groups"` on every group/user
> click (`index.html:2567-2580`), so a drill from Access granted / RBAC policy / Logins lands
> on the self-scoped `groupDetail`/`userDetail` (403 → its own refusal card for a
> non-member), not back on the admin surface. `configHealth()` returns `""` for a payload with
> no `present` key (`index.html:2403`), so a 403'd `operator-configs` simply omits the panel —
> no blank tab, no "Dashboard API error: 403" (that generic-error defect is exactly what the
> `guard403` wrap at `index.html:2732-2735` prevents).
>
> ### C6 — `narrowedReader()`'s fail-open default is harmless. CONFIRMED.
>
> `narrowedReader()` (`index.html:490-494`) returns false when `whoami.visibility` is absent.
> If it wrongly returns false for a genuinely-narrowed reader, `render()` falls to the Overview
> `else` branch (`index.html:2476-2483`), which paints `alertsCard()` + cluster cards +
> `groupsyncTable()` + `configHealth(data.operatorConfigs)`. The **data** in those is
> server-controlled regardless of the UI:
> - cluster cards come from `/api/clusters` — counts only, and `gsd_groups_total` /
>   `gsd_bindings_total` publish them unauthenticated on `/metrics` anyway;
> - `data.operatorConfigs` is `guard403`'d → 403 at self → `{forbidden:true}` → `configHealth`
>   renders `""`;
> - `data.alerts` is server-filtered by `SELF_ALERT_KINDS`.
>
> So a UI fail-open exposes only aggregates already world-readable on `/metrics` — never the
> operator-config detail or binding rows, which the server 403s. The endpoints are the real
> control, as claimed. (One count is *not* on `/metrics` — see the C8 LOW note.)
>
> ### C7 — `/metrics` leaks no group name, username or binding subject. CONFIRMED.
>
> Verified the code (`metrics.py`: labels are only `cluster`, `groupsync`, `namespace`,
> `finding`, `state`, `kind`, `severity`, plus build strings) **and** the live route with no
> credential:
>
> ```
> $ curl -sk https://group-sync-dashboard.apps-crc.testing/metrics   # HTTP 200, 6210 bytes
> label values present: cluster={crc-local,""} finding={ok,dangling,unresolved,built_in,unmanaged}
>   groupsync={bda-rbac-groupsync,ldap-clusteraccess-groupsync,ldap-groupsync}
>   namespace=group-sync-operator kind={direct_user_binding,unattributed} state=... severity=warning
> grep -c app-ocp-rbac|lateef|john.doe|jane.smith|cluster-admin|kubeadmin  -> 0 each
> ```
>
> The only `subject` hit is the word inside a HELP string. `groupsync` is a CR name and
> `namespace` is the operator's namespace — neither a group name, username nor binding
> subject. The premise of §4 holds against live data, so not gating `/groupsyncs` (whose
> per-CR identity is already here) is consistent. `gsd_bindings_total{finding="dangling"}` is
> `0.0` on CRC right now, which is why the F1 leak is currently dormant on the live cluster
> (see F1).
>
> ---
>
> ### F1 (MEDIUM) — `/api/alerts` carries `dangling_binding` and `config_reconcile_error` to the self tier, around the gate
>
> **Where:** `local-development/gsd/api.py:66-73` (`SELF_ALERT_KINDS`), consumed at
> `api.py:1295-1296`; the two leaking alerts are built at `api.py:1271-1294` (dangling, from
> `store.binding_findings`) and `state.py:330-342` (`config_reconcile_error`).
>
> **Trigger (concrete, not a race):** any cluster state where `store.binding_findings` returns
> a row with `finding == "dangling"` — a `RoleBinding`/`ClusterRoleBinding` naming a Group the
> operator once managed and that no longer exists — **or** an operator config with a current
> reconcile error. Then a self-tier reader issues `GET /api/alerts`.
>
> **Measured (in-process, worktree code).** Seeded one dangling CRB
> (`app-ocp-rbac-alpha-cluster-admin-crb` → group `app-ocp-rbac-alpha-cluster-admin`, role
> `cluster-admin`) and one failing `NamespaceConfig`, then, as `lateef.o` (self):
>
> ```
> whoami.visibility = {'scope': 'self', 'enabled': True}
> bindings/findings -> 403
> operator-configs  -> 403
> /api/alerts scope = self  count = 2
>   kind=config_reconcile_error  subject='NamespaceConfig/restricted-tenants'
>     detail='failed to reconcile RBAC template for tenant-x'
>   kind=dangling_binding  subject='app-ocp-rbac-alpha-cluster-admin-crb'
>     detail="ClusterRoleBinding grants cluster-admin cluster-wide to group
>             'app-ocp-rbac-alpha-cluster-admin', which the operator used to manage and no
>             longer exists — this binding now grants nobody"
> ```
>
> The existing suite already pins the leak: `test_dangling_binding_alert_does_not_break_the_
> self_filter` asserts `"dangling_binding" in kinds` for a self reader (`test_view_scoping.py:288`).
> On live revision 103 the leak is **dormant** only because `finding="dangling"` is `0.0` and
> no config is failing right now (`john.doe`'s feed is `unattributed`×2 + `direct_user_binding`;
> `lateef.o` gets 0) — it is a cluster-state accident, not a control.
>
> **Consequence — what a reader of the dashboard believes that is false.** The self reader is
> told, in the same session, two contradictory things: `/bindings/findings` and
> `/operator-configs` answer *"reserved to the administrator tier"* (403), yet the alert feed
> hands them a row from each — a group→role binding mapping and a named operator-config
> failure. They will believe the RBAC binding surface and the operator-config surface are
> withheld from them when in fact fragments of both are being served. The dangling row leaks
> the admin-group **naming convention** (`app-ocp-rbac-<x>-cluster-admin` ⇒ cluster-admin),
> which is reconnaissance toward the *live* `app-ocp-rbac-demo-cluster-admin` group the brief
> names — exactly the "which group grants admin, obtainable here and not with `oc`" escalation
> `require_admin_tier` exists to stop.
>
> **Severity MEDIUM, stated honestly.** Bounded: a dangling binding *grants nobody* (its group
> is gone, so it is not itself a join target), and `config_reconcile_error` names config
> objects and error text, not personnel. But it is a real breach of the gate's own invariant —
> `SELF_ALERT_KINDS`'s comment says every kind here "is backed by a page the self tier sees IN
> FULL", and after this commit the backing pages for these two (`/bindings/findings`,
> `/operator-configs`) 403 at self. The alert has no page behind it at self, so it must not be
> in the feed. Removal, not detail-stripping: a dangling-binding cleanup is administrator work,
> so the self reader loses no signal they could act on.
>
> **Complete replacement — `local-development/gsd/api.py`, the `SELF_ALERT_KINDS` block
> (currently lines 55-73):**
>
> ```python
> # Alert kinds the SELF tier receives — an ALLOW-list, so a kind added later is hidden from
> # the narrow view until someone rules on it, which is the fail-closed direction.
> #
> # Membership is the feed's own invariant, "an alert here always has a page behind it":
> # every kind here is backed by a page the self tier sees IN FULL — the cluster cards, and
> # the GroupSync CRs and their events (CR health, whose per-CR identity and state is already
> # public on the unauthenticated /metrics). The excluded kinds are backed by pages the self
> # tier does NOT see whole:
> #   * `empty_group`, `unattributed`, `stale_group` name groups from the self-scoped Groups
> #     tab (and an empty group can never contain the viewer);
> #   * `direct_user_binding` aggregates other people's grants from the self-scoped
> #     user-bindings view;
> #   * `dangling_binding` and `config_reconcile_error` are backed by /bindings/findings and
> #     /operator-configs, which require_admin_tier now REFUSES at self (the spec-Q3 reversal).
> #     A dangling_binding alert carries a group->role binding row and config_reconcile_error
> #     carries an operator-config object plus its error message — the very rows those two
> #     endpoints withhold — so leaving them here made the alert feed the alternate path around
> #     the gate. Measured: with one dangling finding and one failing config, a self reader
> #     whom BOTH endpoints 403'd still received BOTH alerts. Administrator-tier now; a dangling
> #     binding grants nobody, so a self reader loses no signal they could act on.
> SELF_ALERT_KINDS = frozenset({
>     # Poll failures — kind carries poll_outcome.status verbatim; backed by the cluster cards
>     # and gsd_cluster_up on /metrics.
>     "auth_failed", "forbidden", "unreachable",
>     # GroupSync CR health — per-CR state is public on /metrics, so full-view at both tiers.
>     "groupsync_crd_absent", "invalid_schedule", "sync_stopped", "overdue", "reconcile_error",
> })
> ```
>
> **Complete NEW test — append to `local-development/tests/test_view_scoping.py`.** Fails
> before the fix (self feed carries both kinds), passes after. Verified both directions: on
> unfixed code it raises `AssertionError: a group->role binding row must not reach a self
> reader…`; with `SELF_ALERT_KINDS` reduced as above it passes and the self feed is empty.
>
> ```python
> def test_alerts_do_not_carry_the_admin_only_surface_to_self(tmp_path):
>     """The alert feed must not become the alternate path around require_admin_tier.
>
>     A `dangling_binding` alert carries a group->role binding row and a
>     `config_reconcile_error` alert carries an operator-config object and its error message —
>     both from /bindings/findings and /operator-configs, which are the administrator tier now.
>     Measured at 03ad446: with one dangling finding (the fixture's crb-gone -> gone-group)
>     and one failing config, a self reader whom BOTH endpoints 403'd still received BOTH
>     alerts, so the feed leaked exactly what the gate withholds."""
>     c = _client(tmp_path)
>     # A currently-failing operator config, so config_reconcile_error is in the feed too.
>     store = Store(str(tmp_path / "t.db"))
>     store.replace_operator_configs("c1", [
>         {"kind": "NamespaceConfig", "name": "restricted-tenants", "error_at": now_iso(),
>          "error_message": "failed to reconcile RBAC template", "success_at": None},
>     ], now_iso())
>     store.close()
>
>     wide = _client(tmp_path, tier_resolver=_admin)
>     wide_kinds = {a["kind"] for a in wide.get("/api/alerts", headers=AS_VIEWER).json()["alerts"]}
>     assert {"dangling_binding", "config_reconcile_error"} <= wide_kinds, (
>         "the administrator must still see the whole feed")
>
>     body = c.get("/api/alerts", headers=AS_VIEWER).json()
>     self_kinds = {a["kind"] for a in body["alerts"]}
>     assert body["scope"] == "self"
>     assert "dangling_binding" not in self_kinds, (
>         "a group->role binding row must not reach self via alerts while /bindings/findings 403s")
>     assert "config_reconcile_error" not in self_kinds, (
>         "the operator-config surface must not reach self via alerts while /operator-configs 403s")
> ```
>
> *Note for the arbiter:* `_client` re-seeds the db from `_seed`, then this test opens the
> same `t.db` to add the failing config — `_seed` writes it and closes, so the extra
> `Store(...).replace_operator_configs(...)` lands on the same file the app reads. If you
> prefer, fold the failing-config seed into `_seed` instead; the assertions are what matter.
>
> **Complete replacement — the existing regression test in `test_view_scoping.py:276-292`,
> which my `SELF_ALERT_KINDS` change would otherwise break** (it currently asserts
> `"dangling_binding" in kinds`). Its purpose — the `scope`-shadowing guard — is preserved:
> if the dangling loop ever rebinds the handler's `scope` again, the filter at `api.py:1295`
> is skipped and `empty_group` reappears, so that assertion still catches it.
>
> ```python
> def test_dangling_binding_alert_does_not_break_the_self_filter(tmp_path):
>     """The regression this fixture's dangling binding exists for.
>
>     The dangling-alert loop once used a local `scope` for its namespace label, which rebound
>     the handler's tier variable — after one dangling finding the self filter compared against
>     "cluster-wide" and passed EVERYTHING through: a fail-open. The fix renamed the local to
>     `where`; this pins it. `dangling_binding` is itself WITHHELD at self now — it carries a
>     group->role binding row, see test_alerts_do_not_carry_the_admin_only_surface_to_self — so
>     the guard here is that a dangling finding in the feed does not disable the self filter for
>     the REST: empty_group must still be filtered and the declared scope must survive the loop.
>     """
>     c = _client(tmp_path)
>     body = c.get("/api/alerts", headers=AS_VIEWER).json()
>     kinds = {a["kind"] for a in body["alerts"]}
>     assert "dangling_binding" not in kinds, (
>         "the binding surface is administrator-only; a dangling finding must not reach self")
>     assert "empty_group" not in kinds, (
>         "a dangling finding in the feed must not disable the self filter for the rest")
>     assert body["scope"] == "self", "the declared scope must survive the alert loop"
> ```
>
> No other test depends on these two kinds being in the self feed. `test_rbac.py:316`
> exercises `st.compute_alerts` directly (the alert is still *produced* — admins must see it),
> not the `/api/alerts` self-filter, so it is unaffected. `test_alerts_are_filtered_by_kind_at_
> self` only asserts `empty_group`/`direct_user_binding` are excluded, which still holds.
>
> ### C8 — attacker's eye: what else does a self reader learn. One LOW note.
>
> Beyond F1 (the material one), one honest sub-finding, **LOW, no fix proposed:**
> `/api/clusters` (reachable at self, and it must be — the cluster selector needs it on every
> tab, §5) carries `operator_configs: {total, failing}` per cluster via `_config_summary`
> (`api.py:432-440, 487`). A self reader can read "N operator configs, M failing" even though
> `/operator-configs` 403s. Unlike the group/binding counts, this aggregate is **not** on
> `/metrics` (there is no `gsd_operator_configs_total`; only the *failing* count is inferable
> from `gsd_alerts_total{kind="config_reconcile_error"}`). So §4's "withholding overview counts
> is theatre because /metrics publishes them" does not actually cover this one. It is
> counts-only — no config names, no error text — so I rate it LOW and do not propose gating
> `/api/clusters`; flagging it so the operator knows the /metrics-parity argument has this one
> gap. Everything else a self reader can reach was checked under C2 and is properly scoped.
>
> ### Verdict
>
> The gating is **sound in its core mechanism** — `require_admin_tier` cannot be bypassed
> (C1), fails closed on every indeterminate path, leaves the administrator whole (C3), does
> not wall off the proxy-less install (C4), and the UI refuses all three tabs by name without
> blanks or generic errors, with the server as the true control (C5, C6). The `/metrics` and
> `user-bindings` premises both survived re-measurement (C7, C2). **The single highest-risk
> thing remaining is F1:** the commit gated the two endpoints but left `/api/alerts` — which
> re-serves rows from the very same two tables as `dangling_binding` and
> `config_reconcile_error` alerts — inside the self allow-list, with a now-false justifying
> comment. It is dormant on CRC today only because no binding is dangling, so it will surface
> silently the first time one is; close it with the three-part change in F1 before the gating
> is accepted.

---

## 9. Applied (post-acceptance, by Fable — NOT committed; the coordinator commits after validating)

The coordinator accepted the review and reproduced F1 independently, then directed application.
What was changed, and where each thing came from:

**Code (F1):**
- `gsd/api.py` `SELF_ALERT_KINDS` — removed `dangling_binding` and `config_reconcile_error`;
  full comment rewritten to record why they left and the measurement (item 1).
- `tests/test_view_scoping.py` — new `test_alerts_do_not_carry_the_admin_only_surface_to_self`
  (item 2); rewrote `test_dangling_binding_alert_does_not_break_the_self_filter` to assert the
  kind is now withheld while preserving its scope-shadowing guard (item 3). Both verified
  fail-before / pass-after by stashing only `api.py`.

**Code (the C8 LOW note, upgraded to in-scope by the coordinator):**
- `gsd/api.py` `list_clusters` — now takes `request`, resolves scope once, and withholds the
  `operator_configs` summary at self (`None`, never `0`); it is the one card figure with no
  `/metrics` analogue. `reachable`/`status`/`error` and the /metrics-backed counts untouched.
- `tests/test_view_scoping.py` — new
  `test_operator_config_summary_is_withheld_at_self_on_the_cluster_list` (withheld at self,
  present for an admin, rest of the card untouched). `test_the_overview_counts_stay_full_at_self`
  in `test_visibility.py` stays green: its fixture seeds no operator config, so both tiers see
  `None` there — untouched.

**Docs:**
- `gsd/api.py` `list_groupsyncs` docstring — names *why this is the surviving half* of Q3 (the
  three `/metrics` series), so nobody "consistently" gates it later (item 8).
- `local-development/API.md` — the "three endpoints do not vary by tier" claim corrected: only
  `groupsyncs`/events are invariant; `bindings/findings` and `operator-configs` are the admin
  tier, with the `/metrics` criterion stated (item 6).
- `docs/REQUIREMENTS_per_user_visibility.md` — table row for `bindings/findings` corrected; §6
  Q3 gets a RESOLVED note keeping the original reasoning as superseded, with the overturning
  measurement (item 5).
- `docs/SPEC_per_user_visibility.md` — the Q3 rulings corrected in place at three sites (the
  lens framing, the endpoint-by-endpoint ruling, and the reader-experience lens); structure
  untouched (item 7).

**Changes I made beyond the literal eight items, flagged for the coordinator (each trivially
revertable):**
1. `docs/REQUIREMENTS_per_user_visibility.md` — also corrected the `operator-configs` table row
   ("not personal data" → administrator tier). The reversal is a package (both endpoints moved);
   correcting one row and leaving the other stale is the exact re-introduction risk item 5 names.
2. `docs/SPEC_per_user_visibility.md` (Q3 endpoint ruling, line 242) — also corrected the
   `/api/alerts` kind ruling: `config_reconcile_error` moves to admin-only alongside
   `dangling_binding`, because its backing page (`/operator-configs`) moved behind the tier.
   Leaving "operator-config failing → visible" would contradict the shipped F1 fix and is how
   the next person re-adds it to `SELF_ALERT_KINDS`.
3. `tests/test_docs_citations.py` — added `REVIEW_admin_tier_gating.md` to the existing
   `REVIEW_ARTIFACTS` exemption. This review doc cites exact line numbers (the point of a review
   record), which `test_no_citation_uses_a_line_number` forbids for living docs; the codebase
   already exempts `OAUTH_LOGLEVEL_REVIEW.md` and `REVIEW_login_capture_pr12.md` for exactly this
   reason. Without it the suite has one failure that is purely this artifact. If the doc is not
   to be committed, drop both the doc and this line.

Not touched, deliberately: `local-development/gsd/static/index.html` and `app.css` (the
coordinator is editing the refusal card concurrently). No UI change was required by any item.
