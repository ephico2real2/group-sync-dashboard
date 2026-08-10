# Spec — per-user visibility

Written against `REQUIREMENTS_per_user_visibility.md`. **Spec only; no code.** Three lenses specified
independently, then an arbitration section recording what was verified, what was refuted, and the one
door that turned out to be closed.

---

## Arbitration — what changed after verification

### The refutation that matters most: a user-only SubjectAccessReview demotes every real administrator

The requirements proposed that the Kiali verb-pair maps onto our case "without invention", on the
strength of a measured table showing `list groups` answering `no` for plain/`view`/`admin` and `yes`
for `cluster-reader`. That table is correct **and its naive implementation would have shipped
administrators seeing nothing.**

Lens 1 found it and it reproduces independently. `john.doe` holds `cluster-admin` through
`Group/app-ocp-rbac-demo-cluster-admin`:

```
SAR spec.user=john.doe                                  -> allowed=false
SAR spec.user=john.doe  spec.groups=[<that group>, system:authenticated]
                                                        -> allowed=true
   reason: RBAC: allowed by ClusterRoleBinding "demo-cluster-admin-crb"
           of ClusterRole "cluster-admin" to Group "app-ocp-rbac-demo-cluster-admin"
```

Both measurements are right and together they define the constraint. The requirements' table used
`oc auth can-i --as=<user>`, which sets `spec.user` and no groups — and its probe users were bound
**directly** with `add-cluster-role-to-user`, so they resolved. Every *real* administrator on this
cluster is **group**-granted, which is the entire premise of this dashboard: LDAP group → OpenShift
Group → RBAC. So a SAR that names only the user demotes 100% of them.

**A SubjectAccessReview must therefore carry `spec.groups`.** That is not a refinement; it is the
difference between working and inverted.

### And the authoritative source for those groups does not exist

Lens 1 argues supplying groups from the dashboard's own polled `Group` objects is "principled, not a
hack". It is stronger than that: it is **forced**, because every alternative is closed.

- **The proxy cannot forward them.** `openshift/oauth-proxy`'s `oauthproxy.go` sets exactly
  `X-Forwarded-User`, `X-Forwarded-Email` and optionally `X-Forwarded-Access-Token`, and its
  `SessionState` has **no `Groups` field at all**. (Upstream oauth2-proxy has `X-Forwarded-Groups`;
  this v3-era fork does not.) Read in source, not inferred.
- **`SelfSubjectRulesReview` needs the caller's token**, which this application deliberately does not
  hold — `-pass-access-token` was added, measured, and removed.
- **The OAuth server does resolve groups** — its `users/~` response carries them, observed in the
  proxy's own log during a browser login — but nothing forwards that to the app.

So the app must assert the user's groups from its own copy. That has a consequence the spec must own.

### The consequence: this design fails OPEN in one direction

Asserting groups makes the application the supplier of its own authorization input. Fabrication is not
the risk — the Group objects are the same ones RBAC resolves against — but **staleness is, and it is
asymmetric**:

| change | until the next poll | direction |
|---|---|---|
| user **added** to an admin group | sees the self tier | fails **closed** — fine |
| user **removed** from an admin group | retains the **all** tier | fails **OPEN** |

At the shipped `pollIntervalSeconds: 60` that window is about a minute. Requirement §5.4 demands fail
closed and §8.8 demands the window be documented, so this must be stated in the values comment and the
NOTES output rather than discovered.

**A cheaper fix than accepting it**: resolve the caller's groups with a fresh read at decision time —
the ServiceAccount already holds `list groups` — rather than from the poll snapshot, and cache that for
a stated TTL. The window then equals the TTL, which the operator can reason about, instead of the poll
interval, which is tuned for something else entirely. The implementation phase should measure the cost
of that read before choosing.

### What the requirements got right and the spec should keep

`cluster-reader` as the administrator tier rather than `admin`, confirmed by both passes:
`admin`/`edit`/`view` are namespace roles and grant none of the cluster-scoped reads this dashboard
reports on. And `get users/~` is universal via `basic-user`, so it is the model's floor rather than its
discriminator — the discriminating verb is `list`.

### Where the lenses agree, and it is worth noting they agree

All three independently placed enforcement at the **API handler**, passing a scope predicate into the
existing store queries, on the precedent of `/api/dashboard/activity` — which already does exactly
this and is already tested. None proposed the store or the UI. That convergence is the strongest signal
in the spec, because a UI-only narrowing is a leak with a cosmetic fix and this repo has already been
bitten by the page claiming credit for hiding rows it was not hiding.

---
## Lens 1 — how the tier is decided
**Summary.** Read the requirements in full, all six named repo files (api.py, config.py, store.py, kube.py, rbac.yaml, values.yaml, deployment.yaml proxy args), and measured the live CRC cluster as both personas plus two synthetic ones. Key measurements: (1) reconfirmed the eight-for-eight baseline for lateef.o and `get users/~`=yes via basic-user; (2) runtime SARs created with the dashboard SA's own bound token proved SubjectAccessReview resolves NO groups — john.doe, cluster-admin via Group, is DENIED `list groups` user-only and ALLOWED once his polled group is supplied in spec.groups; even basic-user's `get users/~` needs system:authenticated supplied; (3) `oc auth can-i --as` shares the blindness (no for john.doe), so impersonation is not a faithful instrument for group-granted admins; (4) a cluster-reader persona passes list groups/users/CRBs and even oauth pod logs, a namespace-admin persona fails all cluster-scoped checks; (5) SAR latency 25.1ms median; (6) the SA's SAR grant exists on this cluster but is conditional in the chart on apiTokenAccess (default off) — the requirements' 'already paid for' claim holds for this deployment, not for a default install. Conclusion: the Kiali verb-pair maps onto this app only when the app supplies the viewer's polled groups in the SAR; with that correction it is the only candidate that is live, capability-based, fail-closed, and consistent with every §5 constraint.

### Option — (a) SubjectAccessReview naming the user only, on a real resource (the requirements' literal Kiali mapping)  [REJECTED]

**How.** On first authenticated /api request per viewer, the app POSTs authorization.k8s.io/v1 SubjectAccessReview as its own ServiceAccount with spec.user=<X-Forwarded-User> and resourceAttributes {verb: list, group: user.openshift.io, resource: groups} (and/or clusterrolebindings). allowed:true → all tier, else self.

**Evidence.** RBAC/SAR claims, measured at runtime with the SA's own bound token (oc create token group-sync-dashboard; POST subjectaccessreviews): user-only SAR for john.doe — who IS cluster-admin, via CRB demo-cluster-admin-crb binding Group app-ocp-rbac-demo-cluster-admin — answered {'allowed': False} for list groups. Even lateef.o's universal self-permission `get users/~` answered False user-only and True only once groups:['system:authenticated'] was supplied (reason: ClusterRoleBinding basic-users). oc get clusterrolebinding shows the only human all-tier identity a user-only SAR would pass on this cluster is kubeadmin (direct User binding); every other admin is group-granted. Corroborating instrument trap, measured: `oc auth can-i list groups --as=john.doe` → no — impersonation adds system:authenticated but does not resolve OpenShift Group objects, so can-i --as also under-reports group-granted admins.

**Failure modes.** Silently demotes every administrator whose grant arrives via a Group — on this cluster, all of them except kubeadmin. Fails closed, but permanently and invisibly: the admin sees the self view with no error anywhere, and the 'this is a fix' framing becomes 'the dashboard broke for the platform team'. No reader-visible failure signal exists because the SAR itself succeeds.

**Cost.** One SAR per viewer per cache TTL (~25ms median, measured: 10 warm SARs min 24.2 / median 25.1 / max 28.5 ms against api.crc.testing:6443). Zero new code beyond the SAR call. New RBAC on default installs only (see recommended option).

### Option — (a′) SAR naming the user PLUS their polled groups — RECOMMENDED  [RECOMMENDED]

**How.** Same SAR, but spec.groups = the viewer's group names from the dashboard's own polled Group data (store.user_groups, gsd/store.py:1274) + system:authenticated + system:authenticated:oauth. Two resourceAttributes are checked and BOTH must be allowed for the all tier: {verb: list, group: user.openshift.io, resource: groups} and {verb: list, group: rbac.authorization.k8s.io, resource: clusterrolebindings} — the AND because this repo already measured that `list groups` alone was a privilege escalation for /api (values.yaml apiTokenAccess block: an account with only list groups pulled 229 bindings it could not list with oc). Decision enforced in the API handlers (the /api/dashboard/activity pattern), cached per (viewer, sorted-groups) with a TTL equal to the poll interval, fail-closed to self on SAR error/timeout per §5.4. Runtime claim, validated: the SA's bound token (no OAuth scope gate — scopes apply to oauth-issued user tokens, which this design never touches) actually created every SAR in this measurement; this is not just a can-i inference.

**Evidence.** S4/S8 measured: SAR user=john.doe groups=[app-ocp-rbac-demo-cluster-admin, system:authenticated] → allowed:true for BOTH list groups and list clusterrolebindings, reason naming demo-cluster-admin-crb. S2: kubeadmin user-only → allowed:true (direct binding), so directly-bound admins need no group data. cluster-reader persona → allowed on both plus users and pods/log. namespace-admin persona (temp RoleBinding, deleted after) → denied both cluster-scoped checks, allowed only its namespaced list rolebindings. Group-input parity is principled: oauth logins resolve the user's groups from the same Group objects the poller reads, so the SAR input mirrors the user's real token identity. Latency measured 25.1ms median per SAR. `oc auth can-i create subjectaccessreviews --as=system:serviceaccount:group-sync-dashboard:group-sync-dashboard` → yes on this cluster.

**Failure modes.** Staleness of the groups INPUT (the SAR's RBAC evaluation is always live): a user removed from an admin group keeps the all tier for worst-case poll_interval (60s default) + cache TTL; a user added waits the same. Deleting the binding itself is caught within one TTL because the SAR consults live RBAC. An admin whose grant flows through a group that exists only outside the poller's view would be wrongly self — but on OpenShift, Group objects are also what the oauth server itself resolves, so such a grant would not authenticate as admin either. SAR error/timeout → self view + a UI banner; the reader sees their own data, never an error page. THE ONE CHART GAP, measured: the SA's SAR grant comes from the auth-delegator binding, which rbac.yaml:114 renders only when oauthProxy.enabled AND apiTokenAccess.enabled — apiTokenAccess defaults false (values.yaml:930), so a DEFAULT install has no SAR permission and every viewer would fail closed to self forever. The spec must add `create subjectaccessreviews` (or the auth-delegator binding) whenever visibility enforcement is enabled — compatible with §5.1 since a SAR creates no persistent object. Tests to name: test_tier_sar_carries_polled_groups_and_system_authenticated; test_tier_requires_both_capabilities (groups-only → self); test_tier_fails_closed_on_sar_error_and_timeout; test_tier_cache_ttl_bounds_revocation_window; test_admin_sees_identical_payload_per_endpoint; test_self_reader_sees_only_own_rows_per_endpoint; chart test: helm template renders the SAR grant with visibility on and apiTokenAccess off.

**Cost.** Two SARs (~50ms) per viewer per TTL, then a dict hit; at 30s page polling with a 60s TTL that is ≤2 SARs/min/viewer against an API server this app already polls with 150+ requests per binding cycle. Code surface: one tier module (SAR call + cache), a scope parameter threaded through existing handlers/store queries, no new dependency (httpx already in-tree, kube.py's client pattern reused). New RBAC: none on this deployment (binding exists); one conditional `create subjectaccessreviews` rule on default installs.

### Option — (b) App-defined ClusterRole checked by SAR — real resources vs fictional capability resource  [VIABLE]

**How.** Real-resource flavor: chart ships an UNBOUND ClusterRole (e.g. gsd-dashboard-all) whose rules are exactly the all-tier reads — list groups, list users, list rolebindings/clusterrolebindings; the operator binds it to a governance group with oc adm policy; the (a′) SAR then passes because the capability is genuinely held. Fictional flavor: SAR on a made-up resource (e.g. verb use on dashboardviews.gsd.example.com), with a ClusterRole granting that string — a pure capability flag, Kiali-style two-role packaging.

**Evidence.** Real flavor needs no new measurement: it produces the same SAR answers as (a′) — CR1-CR3 show a role carrying those verbs passes both checks. Stock cluster-reader already IS this role, measured allowed on all four probes including get pods/log in openshift-authentication, so the minimal version ships zero chart objects and one README paragraph, matching values.yaml:921-928's existing pattern of pointing operators at cluster-reader for apiTokenAccess. Fictional flavor: RBAC evaluates arbitrary resource strings, so it works mechanically (not measured — no candidate role exists to measure), but nothing about the cluster's real read permissions constrains it.

**Failure modes.** Real flavor: binding the role genuinely grants oc read of the same data — that is the point, but an operator must understand they are granting cluster RBAC read, not a dashboard checkbox; the removed apiTokenAccess.readers precedent (values.yaml:915-919) rules out driving the binding from a Helm value, because a values file must not be able to mint cluster-level read. Fictional flavor: the tier and the real permission drift independently — grant the flag without the read and 'you could see this with oc anyway' is false again (the §1 exposure, reintroduced by configuration); deny the flag to a cluster-admin and the SAR still passes only if (a′)'s real-resource checks are also asked, i.e. the flag adds a second vocabulary without retiring the first. Audit story: a reviewer of the fictional role learns nothing about what data it exposes.

**Cost.** Real flavor: one ClusterRole template behind a values toggle + docs, no runtime cost beyond (a′), no new verbs for the SA. Fictional flavor: same plus a permanently-maintained parallel authorization vocabulary.

### Option — (c) Derive the tier from the binding data the dashboard already polls — no API call  [REJECTED]

**How.** At request time, look the viewer up in the stored group_member and binding rows: if any of their groups (or their username) is bound to a role known to grant the all-tier reads, grant all. Since the poller never fetches Role/ClusterRole RULES (stated as a design invariant in kube.py, rbac.yaml and two endpoint docstrings: 'role rules are never evaluated'), 'known to grant' can only mean a hardcoded list of role NAMES — cluster-admin, cluster-reader, admin…

**Evidence.** The data exists: store.user_groups (store.py:1274) and the binding tables behind /bindings/findings answer the lookup with zero API calls, and the 'Access granted' tab is built on exactly this (requirements §4). But the decisive evidence is negative and measured: the tier question is 'can this user list groups/CRBs', and answering it from names would have called the cluster-reader persona self unless 'cluster-reader' was hardcoded (its capability was only visible via SAR, CR1-CR3), and calls ANY custom or aggregated role self forever. The repo's own history shows why rule evaluation stays out: re-implementing RBAC semantics in-app is the class of work the design refuses.

**Failure modes.** A permission granted by a route the model does not cover — a custom ClusterRole, RBAC aggregation, a rename — yields a PERMANENT wrong-self, not a staleness window, with no error anywhere. Staleness for modeled routes: bindings refresh every binding_interval_seconds=300 (config.py), so a revoked admin keeps the all tier up to 5 minutes — worse than (a′)'s 60s+TTL, and in the open direction. It is also a role-membership decision, the weaker Q4 branch: auditable by name, wrong by capability.

**Cost.** Zero API calls, one SQL lookup per request. But it converts the dashboard's polled view into a request-time authorization oracle — the caveat requirements §4 itself flags — and adds a hardcoded role-name list that must track every cluster's RBAC conventions forever.

### Option — (d) A second -openshift-delegate-urls path prefix, enforcing the admin tier in the proxy  [REJECTED]

**How.** Extend oauthProxy.apiTokenAccess.delegateUrls (deployment.yaml:249-251 renders it verbatim) with a stricter prefix, e.g. {"/api": {self-level SAR}, "/api/admin": {list clusterrolebindings}}, and move all-tier endpoints under /api/admin so the proxy 403s non-admins before the app sees the request.

**Evidence.** Read, not just recalled: values.yaml:884-888 records the upstream contract this project already verified in practice when building apiTokenAccess — '-openshift-delegate-urls ... applies ONLY to requests carrying Authorization: Bearer or a client certificate, so browser sessions keep the cookie flow untouched.' That is an upstream-documented runtime claim (openshift/oauth-proxy README), consistent with this deployment's observed behavior (browser cookie sessions reach /api today without ever passing the delegate SAR); it was not re-measured in this pass.

**Failure modes.** Fatal and structural: browser cookie sessions — the entire UI population, the population this feature is FOR — never pass through delegate-urls at all, so /api/admin would be wide open to any logged-in browser. Even for bearer callers it is admission-only (pass or 403 with the login page as body): the proxy forwards no header stating which SAR passed, so the app cannot learn the tier from it and every endpoint would need a duplicate admin-path mount purely to encode one bit. The cookie-covering sibling flag, -openshift-sar, takes no path map — it gates the whole dashboard identically, which is the already-shipped 'none' tier (oauthProxy.sar, values.yaml:868-871), not a distinction between admitted readers.

**Cost.** No app code, but a duplicated endpoint tree, a proxy-version-dependent contract, and a control that silently does not apply to browsers — negative value.

**Recommendation.** Option (a′) — a ServiceAccount-created SubjectAccessReview per viewer, naming the user AND their polled group memberships, requiring both `list groups.user.openshift.io` and `list clusterrolebindings.rbac.authorization.k8s.io` for the all tier — because runtime measurement proved a SAR without groups denies every group-granted administrator on this cluster (all of them but kubeadmin), and the dashboard is uniquely positioned to supply the groups it already polls, keeping the decision a live cluster-RBAC evaluation rather than an app-side guess.

### Answers to the open questions

**Q1 — How is the tier decided, and against which resource?**

By capability, via a SubjectAccessReview the ServiceAccount creates, naming the viewer AND the viewer's groups taken from the dashboard's own polled Group data plus system:authenticated. The requirements' claim that the Kiali verb-pair 'maps without invention' is REFUTED in its naive form, by runtime measurement: a SAR naming only the user resolves no group memberships at all — POST subjectaccessreviews as the SA with spec.user=john.doe (cluster-admin via Group app-ocp-rbac-demo-cluster-admin through CRB demo-cluster-admin-crb) answered allowed:false for list groups; adding spec.groups flipped it to allowed:true with reason naming that CRB. Even `get users/~` was denied user-only and allowed once system:authenticated was supplied (basic-users binding). On this cluster every human administrator is group-granted, so a user-only SAR would demote 100% of them. With groups supplied, the pair to require for the all tier is BOTH `list groups.user.openshift.io` AND `list clusterrolebindings.rbac.authorization.k8s.io` — the AND exists because this repo already measured (values.yaml §apiTokenAccess) that `list groups` alone was a privilege escalation for /api, which reports the whole RBAC binding surface. The self-tier baseline needs no check at all: it is what everyone gets. Supplying polled groups is principled, not a hack: at a real oauth login the user's groups are resolved from the same Group objects the dashboard polls, so the SAR input mirrors what the user's own token would carry, staleness aside.

**Q2 — Does the app define its own ClusterRoles, and what do they contain?**

Ship ONE app-defined ClusterRole over REAL resources, unbound (Kiali's pattern): rules exactly `list groups.user.openshift.io`, `list users.user.openshift.io`, `list rolebindings/clusterrolebindings.rbac.authorization.k8s.io` — the reads the all tier exposes. Binding it makes the SAR pass AND makes 'you could read this with oc anyway' literally true, which is the stated preference. The audit story is verbs an auditor can map to data. Also document stock `cluster-reader` as the broader alternative — measured by SAR with groups=[system:cluster-readers]: allowed on list groups, list users, list clusterrolebindings, and even get pods/log in openshift-authentication (the logins source), so cluster-reader passes the gate with no chart object at all; that matches the repo's existing preference for stock roles (the auth-delegator comment: 'an auditor recognises the grant instead of reading ours'). A ClusterRole over a FICTIONAL resource is rejected: it decouples dashboard visibility from real cluster read permission, so an operator could grant the all tier to someone who cannot read the data with oc — silently recreating the §1 exposure — and its audit trail is a capability flag naming a resource that does not exist. Per the removed apiTokenAccess.readers precedent, the chart must NOT bind the role from a values list; binding is an `oc adm policy add-cluster-role-to-group` task.

**Q3 — What about data that belongs to nobody?**

Directional (another lens owns this): groupsyncs and groupsync events are governance data about objects, not persons, and stay full-view for every admitted reader (SUPERSEDED at 03ad446: operator-configs and bindings/findings were originally grouped here too, but both are the ADMINISTRATOR TIER now — bindings/findings rows ARE the RBAC surface, and operator-configs has no /metrics analogue; see the endpoint-by-endpoint ruling below) — self-scoping them to nothing would make the dashboard useless to exactly the audience the sar-admission tier already vetted. The one caveat this lens's reading adds: bindings/findings rows carry group names and (user-bindings) person names, so 'findings stay visible' must mean the classification and counts, with the spec ruling explicitly on whether the named-subject detail rows are all-tier only. /logins is NOT governance data — it is the most sensitive endpoint (requirements §2) and is self-scoped.

**Q4 — Is cluster-admin special, or merely one binding among many?**

Capability, not role membership — settled by measurement. A cluster-reader persona (SAR with groups=[system:cluster-readers]) is allowed all four probes including the oauth pod logs, so it gets the all tier, which is correct: it can read everything the dashboard shows with oc today. A namespace-admin persona (temporary RoleBinding of ClusterRole admin in `default`, created and deleted during measurement) is allowed `list rolebindings` in its namespace but denied cluster-scoped `list groups` and `list clusterrolebindings`, so it gets self — a namespace grant is not a cluster-wide read. cluster-admin is not special anywhere in the design: kubeadmin passes because its direct User binding satisfies the SAR (measured, reason: ClusterRoleBinding kubeadmin), group-granted admins pass through their groups, and any custom role that grants the two lists passes by the same rule. Role-membership derivation would have missed cluster-reader entirely unless its name was hardcoded, and missed every custom route.

**Q5 — What does a self-scoped reader see where a value is aggregate?**

Directional (another lens owns this): follow Q3's split — aggregates over governance data (CR health counts, dangling-binding counts) stay cluster-wide because their inputs are shown in full anyway; aggregates over personal data (login summary, distinct_users, membership-change counts) must be recomputed over the visible subset, and the response must say so — the existing per-endpoint `scope` field pattern from /api/dashboard/activity ('scope': 'self'|'all', 'viewer': name) is the wire precedent, so the UI can label a recomputed number rather than letting it impersonate the cluster-wide one.

**Q6 — How does the UI show that a view is narrowed?**

Directional: every scoped response carries `scope` and `viewer` (the /api/dashboard/activity shape, already shipped), and the page renders a persistent 'showing your view' banner plus per-tab empty-states that distinguish 'nothing of yours' from 'nothing exists' — the exact distinction the Groups tab already draws for filters ('none match your filter' vs 'none exist'). Deciding this belongs to the UI lens; the API-side contract (scope on the wire, never inferred client-side) is fixed by this lens because the UI must never derive the tier itself.

**Q7 — Where is the decision enforced?**

At the API layer, in the FastAPI handlers, by passing a scope predicate into the existing store queries — exactly where /api/dashboard/activity already does it (scope_to = None if all else viewer, handed to store.user_activity). The store stays mechanism-free because it has no access to request identity and must not grow one; the UI is presentation of an already-scoped payload, because a UI-only narrowing is a data leak with a cosmetic fix (the requirements' own words) and this repo has prior scar tissue about the page claiming credit for hiding rows. One layer, one precedent, already tested in-tree.

**Q8 — What is the migration, and what is the default?**

Default `self` — the requirements establish this is a fix for an exposure, not a feature, and shipping the fix off-by-default leaves the exposure in place on exactly the installs that never read release notes. Mechanism: a `visibility: self|all` chart value flowing through configmap→Settings like userActivityVisibility does, parsed with the same fail-safe rule (_visibility_setting: only the exact string 'all' widens; any typo means self). Operator communication: a startup log line stating the effective mode, a values.yaml comment block in the house style, and a CHANGELOG/README upgrade note stating that admitted non-admin readers will see their view narrow on upgrade and which grant (`cluster-reader` or the shipped ClusterRole) restores the wide view. `all` remains available as a deliberate, documented choice — the same escape hatch userActivity.visibility ships.

### Risks named by this lens

What this spec cannot guarantee, and what to measure before code: (1) DEFAULT-INSTALL RBAC GAP — the SA's `create subjectaccessreviews` comes from the auth-delegator binding, rendered only when apiTokenAccess.enabled (default false, rbac.yaml:114 / values.yaml:930); on this cluster it happens to exist. The chart must grant it whenever visibility enforcement is on, and a helm-template test must prove the rendering; without it every reader is permanently self and the feature looks broken. (2) GROUP-INPUT STALENESS — the SAR's RBAC check is live but its group list is polled; worst-case retained all-tier after removal from an admin group = poll_interval + cache TTL (~2 min at defaults). This window must be stated in values.yaml and asserted by test; measure the actual propagation on the lab before fixing the TTL number. (3) IDENTITY-STRING PARITY — the design assumes X-Forwarded-User equals the username Group objects carry and the username RBAC bindings name; true on this LDAP IdP, but an IdP with a mappingMethod that decorates usernames would break the join silently — verify on any second cluster shape before GA. (4) MULTI-CLUSTER SEMANTICS — the SA token answers SARs only for the local cluster; the tier it yields would gate data ABOUT remote clusters using local RBAC, or per-cluster SARs need the remote tokens to hold the SAR grant (unmeasured — no remote cluster in the lab). The spec must pick one and say so. (5) The `oc auth can-i --as` instrument under-reports group-granted permissions (measured: --as=john.doe list groups → no, though he is cluster-admin via group); every future verification of this feature must use real SARs with groups or real logins, never bare impersonation. (6) SAR spec.groups is attacker-irrelevant only while identity comes solely from the proxy (§5.3) — if oauth_proxy_enabled is false the tier code must never run, same guard /api/dashboard/activity already has.


## Lens 2 — what each tier sees, and where it is enforced
**Summary.** I read the requirements, api.py, store.py (all 2,488 lines), config.py, kube.py, rbac.yaml, values.yaml and the index.html tab/banner code, then measured on the live CRC cluster: re-confirmed the eight RBAC denials for lateef.o and `get users/~`=yes; proved the dashboard SA can create SubjectAccessReviews with no new grant and that a SA-executed SAR separates the tiers (lateef.o false, kubeadmin true, cluster-readers true); discovered by experiment that SAR does NOT resolve OpenShift Group membership (jane.smith's group-granted admin is invisible unless the app supplies spec.groups from its own polled data); proved with a deliberate mixed-case failed login that the capture stores the name AS TYPED (LATEEF.O, bad_password) while whoami/User/group_member all carry the directory form (lateef.o) — so self-matching must be byte-exact, and case-variant rows fail closed to admin-only visibility; ran EXPLAIN QUERY PLAN on the live database showing the logins and groups scoping predicates are index-served while COLLATE NOCASE defeats the index; and fetched /metrics without credentials to establish that group counts, binding-finding counts and per-CR GroupSync health are already public — the fact that settles the aggregates and nobody's-data questions. The rulings: personal data self-scopes at the API handler via store-executed predicates, the RBAC binding surface is admin-only (the project's own measured-escalation precedent), metrics-public health and counts stay full at both tiers with DN-bearing fields omitted at self, aggregates are shown-or-suppressed but never recomputed (recomputation is semantically degenerate for membership-scoped data), and enforcement lives at exactly one layer — the API handler — with the UI reflecting a scope field it never decides.

### Option — A — Enforce at the API handler: a tier dependency + store-executed scope parameters  [RECOMMENDED]

**How.** A FastAPI dependency resolves the request to (viewer, tier): viewer = X-Forwarded-User, trusted only when settings.oauth_proxy_enabled (the whoami/activity rule, unchanged); tier = cached result of one SubjectAccessReview the app creates as its own SA — spec.user=viewer, spec.groups = viewer's groups from the polled group_member table + system:authenticated + system:authenticated:oauth, resourceAttributes = list clusterrolebindings (rbac.authorization.k8s.io). allowed=true → all; false, error, timeout, or no viewer → self (fail closed, constraint §5.4). Each handler then applies its ruling: pass scope_to=viewer into existing store parameters (login_events, membership_events, user_activity already take user_name; users() gains one; groups() gains the one new JOIN-shape), return 403 for admin-only endpoints (bindings/findings; non-member group/user detail — 403 emitted before any existence lookup so it is constant for nonexistent and forbidden alike), omit fields (ldap_filter, error_message, logins summary/ungoverned, cluster-access dn/lists), and filter alerts by kind under the existing 'an alert always has a page behind it' invariant. Every scoped payload carries scope+viewer (the activity response contract, generalised); the UI renders banners and hides suppressed tabs from those fields and decides nothing. SAR result cached per viewer, TTL 60s, per replica.

**Evidence.** All measured on the live CRC cluster. RBAC denials re-verified: `oc auth can-i list groups.user.openshift.io --as=lateef.o` → no (likewise users, rolebindings, clusterrolebindings, groupsyncs, oauths); `oc auth can-i get users/~ --as=lateef.o` → yes. SA needs no new grant: `oc auth can-i create subjectaccessreviews --as=system:serviceaccount:group-sync-dashboard:group-sync-dashboard` → yes. The SAR executed AS the SA (oc create --as=system:serviceaccount:...) distinguishes the tiers: lateef.o → {allowed:false}; kubeadmin → {allowed:true, reason: CRB kubeadmin/cluster-admin}; groups=[system:cluster-readers] → true for list clusterrolebindings, list groups, and get pods/log in openshift-authentication. THE GROUP-RESOLUTION TRAP, measured: jane.smith (in Group app-ocp-rbac-alpha-cluster-admin, CRB → ClusterRole admin) is allowed=false with user alone AND with groups=[system:authenticated], allowed=true only when her group is supplied in spec.groups — so the app MUST feed spec.groups from its store. Query plans against the live /data/gsd.db (oc exec, sqlite3 read-only): logins self-scope → 'SEARCH login_event USING INDEX login_event_by_user (cluster_id=? AND user_name=?)'; the new groups JOIN → group_state autoindex + group_member PK covering index; COLLATE NOCASE variant degrades to the cluster-wide login_event_lookup scan (rejected). Cost probe: 10 sequential oc-created SARs = 1.38s wall (~138ms each including oc client startup; the in-process httpx call will be under that, and it runs once per viewer per 60s, not per request). Public-aggregate precedent: credential-less `curl /metrics` returned gsd_groups_total=65, gsd_bindings_total{finding=unmanaged}=7, per-CR gsd_groupsync_state — so overview counts and CR health shown at self tier disclose nothing new.

**Failure modes.** SAR path down or slow → every reader degrades to self for the cache window; an admin sees the self banner and their own data, never an error page — visible, fail-closed, and the named test forces it. Attribute mismatch between the IdP's preferredUsername and the sync operator's userNameAttributes → viewer matches no rows; reader sees the 'you are not a member of any synced group' empty state with their whoami name displayed, which is the diagnostic. Revoked admin retains the all view ≤ 60s TTL + in-flight page; newly-granted-via-group admin waits ≤ TTL + one poll interval (spec.groups is polled data). Bearer-token API callers (apiTokenAccess): whether the proxy sets X-Forwarded-User on the delegate-urls path is unmeasured — if absent, those callers get 403 on personal endpoints and public data only, until measured and ruled. Multi-replica: per-replica cache means tiers can disagree across pods for ≤ TTL — bounded by the same window already documented for all per-pod state.

**Cost.** One extra API call per viewer per 60s per replica (measured ≤138ms via oc including client overhead; server-side SAR is cheaper), zero on cache hits — the 30s page poll rides the cache. No new RBAC: auth-delegator already grants create subjectaccessreviews (measured), no persistent object created, constraint §5.1 explicitly satisfied. Code surface: one dependency (~60 lines with cache), per-handler ruling edits, one new store query shape (groups JOIN) + user_name parameters on two existing methods, UI banner + tab gating in the one index.html, chart: one values key + template-time interlock + optional viewer-all ClusterRole. Tests named: test_plain_reader_sees_only_own_{profile,groups,logins,grants,gate_status}; test_admin_view_unchanged_per_endpoint; test_tier_indeterminate_fails_closed (SAR raises → self); test_sar_supplies_store_groups; test_group_detail_403_constant_for_nonmember_and_nonexistent; test_logins_self_scope_byte_exact (LATEEF.O row invisible to lateef.o, visible at all); test_alerts_filtered_by_kind; test_groupsyncs_omits_ldap_filter_at_self; test_proxy_off_rbac_mode_403s_personal_endpoints; test_scope_field_on_every_scoped_response; test_metrics_unchanged; chart test: template fails on visibility.mode=rbac with oauthProxy.enabled=false.

### Option — B — Enforce in the store: viewer threaded through every query method  [REJECTED]

**How.** Every Store read method gains a mandatory viewer/tier argument; the SQL itself refuses to return out-of-scope rows, so no handler can forget to scope. Policy lives in one module (store.py) instead of fourteen handlers.

**Evidence.** Read directly from store.py: the store serves three callers — API handlers, the Poller (sync_members, replace_* need unscoped reads of existing state), and the metrics collector (build_registry(store,...)) — and the latter two have no viewer; they would pass a sentinel 'system' tier, which is an always-open bypass living in the same signature as the control. The store also cannot express half the rulings: suppression is HTTP 403 (bindings/findings, non-member group detail with constant response), field omission (ldap_filter), and alert-kind filtering over st.compute_alerts output that is computed in the API layer, not in SQL. And the trust decision needs settings.oauth_proxy_enabled, which config.py shows never reaches the store. The codebase's own division already rejects this: user_activity's comment defines user_name as 'the privacy scope' PASSED IN by the API, and activity's proxy check lives in the handler.

**Failure modes.** The sentinel tier becomes the common path (poller + metrics + tests all use it), so the control's bypass is exercised constantly and a handler passing it by mistake is invisible in review. Rulings that are not row predicates end up half in the store and half in handlers anyway — two layers, which is the exact outcome Q7 forbids. Storage backends (storage.py seam) would each reimplement policy.

**Cost.** Signature change on ~25 store methods and every call site including the poller and metrics; higher than A for strictly less expressible policy.

### Option — C — Narrow in the UI: index.html hides what the tier should not see  [REJECTED]

**How.** The API keeps returning everything; index.html reads whoami's tier and renders only the viewer's rows and tabs.

**Evidence.** The API is directly reachable and self-describing: /api serves Swagger UI behind the same proxy door as the data (api.py's own comment: the schema 'is a map of this cluster's RBAC surface'), and apiTokenAccess exists precisely so curl works. Every byte still crosses the wire to the browser of the person who must not see it. The requirements pre-refute this in Q7 ('an endpoint that returns everything while the page hides most of it is a data leak with a cosmetic fix'), and this project has already paid for a UI element claiming credit for hiding rows it was not hiding (the Groups search-box fix, cited in Q6).

**Failure modes.** Trivially bypassed by DevTools, curl, or the built-in API docs; every future endpoint must remember client-side hiding; screenshots and browser caches retain the full payload.

**Cost.** Lowest to build, zero as a control. Not a control.

### Option — D — Two deployments: an admin install and a public install gated by oauthProxy.sar  [REJECTED]

**How.** Keep the app tier-blind. Deploy twice: one release with oauthProxy.sar requiring list clusterrolebindings (admins only, full view), one for everyone else with the sensitive tabs disabled by values. The proxy's SAR — already supported — does the authorization.

**Evidence.** oauthProxy.sar exists in values.yaml and requirements §3 confirms the none tier already works this way; the proxy performs the SAR per session with no app code. But the second install cannot produce a SELF view — the app reads with its own SA either way, so the 'everyone else' deployment either still shows everything (the bug, unfixed) or shows nothing personal (the product value gone). Requirements §3 names the missing piece as 'the distinction between admitted readers', which two doors cannot express; per-endpoint self-scoping needs the app to know the viewer.

**Failure modes.** Double the operational surface (two PVCs, two pollers, two login-capture readers against the same oauth logs), drifting versions, and the ordinary reader's deployment still has no self tier — the central requirement unmet.

**Cost.** No app change, but 2x infrastructure and it does not implement the requirement; usable only as an interim stopgap for the admin/none split that oauthProxy.sar already provides today.

**Recommendation.** Option A — enforce at the API handler with store-executed scope parameters — because it is the only layer that holds all three inputs a ruling needs (proxy-trusted identity, tier, and response shape including 403s and field omission), and the codebase's one already-shipped scoped endpoint (/api/dashboard/activity) proves the pattern end to end.

### Answers to the open questions

**Q1 — How is the tier decided, and against which resource?**

One SubjectAccessReview, created by the app as its own ServiceAccount, naming the viewer, against verb=list resource=clusterrolebindings group=rbac.authorization.k8s.io — the exact review this codebase already ruled to be the 'honest floor' for /api bearer tokens (values.yaml apiTokenAccess.delegateUrls is this SAR verbatim, adopted after the measured `list groups` privilege escalation). allowed=true → tier all; anything else (false, error, timeout) → tier self. Measured on this cluster, executed AS the SA via impersonation: lateef.o → {"allowed":false}; kubeadmin → allowed via CRB kubeadmin/cluster-admin; groups=[system:cluster-readers] → true. TWO CAVEATS THE SPEC MUST CARRY. (1) MEASURED: SubjectAccessReview does NOT resolve OpenShift Group membership — jane.smith, in Group app-ocp-rbac-alpha-cluster-admin bound to ClusterRole admin, got allowed=false with spec.user alone and with groups=[system:authenticated], and allowed=true only when her group was supplied in spec.groups. The app must populate spec.groups from its own polled group_member rows (SELECT group_name FROM group_member WHERE cluster_id=? AND user_name=? — index group_member_by_user) plus the static virtual groups system:authenticated and system:authenticated:oauth. This makes the decision partly polled data: correct within one poll interval. (2) RBAC vs runtime: a SAR answers about the USER'S RBAC, never about any token's scope. That is acceptable here BY CONSTRUCTION — no user token is involved anywhere in this design (constraint §5.2 is respected); the tier models the person's entitlement, which is what visibility should model. State in the spec which claims are RBAC claims (everything decided by SAR) and which are runtime claims (whether the proxy actually sets X-Forwarded-User on the apiTokenAccess bearer path is UNMEASURED and must be, because an empty viewer fails closed to a 403 on personal endpoints).

**Q2 — Does the app define its own ClusterRoles, and what do they contain?**

Yes, one, optional, default-off, and over REAL resources — never a fictional one. Because the tier probe is `list clusterrolebindings` (a real resource the dashboard reports on), an operator can already grant the all tier with stock roles: `oc adm policy add-cluster-role-to-group cluster-reader <group>` passes the probe (measured: SAR with groups=[system:cluster-readers] → true for list clusterrolebindings, list groups, AND get pods/log in openshift-authentication — so cluster-reader legitimately covers even the log-derived logins data). The chart additionally ships a convenience ClusterRole (suggest `<fullname>-viewer-all`, rendered only when asked) whose rules are the dashboard's actual read surface — list groups+users (user.openshift.io), list rolebindings+clusterrolebindings, list groupsyncs+namespaceconfigs+groupconfigs — for operators who want all-tier dashboard readers without full cluster-reader. Binding it makes 'you could read this with oc anyway' literally true for that reader, which is the audit story the fictional-resource capability flag cannot tell. It creates no new SA permission and no write verb; the SA itself needs NOTHING new — system:auth-delegator already grants create subjectaccessreviews (measured: `oc auth can-i create subjectaccessreviews --as=system:serviceaccount:group-sync-dashboard:group-sync-dashboard` → yes), and a SAR creates no persistent object, so constraint §5.1 holds.

**Q3 — What about data that belongs to nobody? (full endpoint-by-endpoint ruling)**

The decision rule, applied uniformly: personal data (names a person) → SELF-SCOPED; RBAC-surface data (what grants what to whom) → ADMIN-ONLY, because this project already measured and documented that exposing it to a reader who cannot `oc get` it is a privilege escalation (values.yaml apiTokenAccess history); operational health whose content is ALREADY PUBLISHED UNAUTHENTICATED on /metrics → FULL, because suppressing behind login what the pod serves without login is theatre. Measured live: `curl -sk https://group-sync-dashboard.apps-crc.testing/metrics` with no credential returns gsd_groups_total=65, gsd_groups_empty_total=1, gsd_bindings_total{finding=unmanaged}=7, and per-CR gsd_groupsync_state/last_sync with CR name and namespace. Rulings: /api/clusters → FULL except per-cluster counts are exactly the public metric set (poll status, group/empty/unattributed counts, binding-finding counts, operator-config summary — all in /metrics already). /api/.../groupsyncs and .../groupsyncs/{name}/events → FULL at both tiers (CR name, namespace, state, schedule, last sync, group_count are public in /metrics) EXCEPT ldap_filter and error_message are omitted at self tier — both can embed directory DNs and the gate group, which /metrics deliberately never carries. /api/.../operator-configs → ADMIN-ONLY (403 at self), reversed at 03ad446 from the original "FULL except error_message omitted at self": unlike CR health it has NO /metrics analogue, so serving it at self left a genuinely private view open; the present/failing counts stay on the public overview. /api/.../bindings/findings → ADMIN-ONLY (403 at self): the rows ARE the cluster's RBAC surface — binding names, roles, group subjects — the exact data whose exposure was the measured escalation; the COUNTS stay visible on the overview because /metrics already publishes them. /api/.../groups → self sees only groups they belong to (all columns); /groups/{name} → 403 at self for any group they are not a member of, and the 403 is returned for member-check failure BEFORE any existence lookup so a nonexistent group and a real group answer identically (no existence oracle). /api/.../users → self sees own row only; /users/{name} → own name or constant 403. /api/.../user-bindings → self sees rows WHERE user_name=viewer only; by_namespace rollup and excluded_platform count suppressed at self (they aggregate other people's grants). /api/.../logins → the most sensitive endpoint: self sees own attempts only (store already takes user_name; index login_event_by_user serves it — EXPLAIN QUERY PLAN measured), window metadata (capture_started_at, retained_since, last_read_at, enabled) kept because it describes the record not a person; summary, ungoverned, and gate cross-references suppressed at self. /api/.../cluster-access → self gets gated/synced booleans, their OWN in-gate status (store.is_in_access_group exists, batch form), and the note; dn, source, both people-lists and the summary suppressed. /api/.../membership-changes → self sees rows WHERE user_name=viewer (membership_events already takes user_name; index membership_event_by_user). /api/alerts → filtered BY KIND at self under the invariant api.py already states ('an alert here always has a page behind it'): poll failures and groupsync staleness/CRD-absent → visible; dangling_binding, config_reconcile_error (operator-config failing) and direct-user-binding alerts → admin-only, because their backing pages are — at 03ad446 operator-config failing moved here too when /operator-configs became the administrator tier, since the feed's "a page behind it" invariant follows the page (dangling_binding was always meant to be admin-only here; the code briefly left it in the self allow-list, closed with this reversal). /api/dashboard/activity → its OWN, STRICTER tier, INDEPENDENT of the wide tier above (added 2026-08, docs/SPEC_usage_admin_tier.md). Usage is the one dataset that lives only in the dashboard's SQLite and cannot be reproduced with oc, so passing the wide adminSar does NOT widen it — the auditor cluster-reader keeps every wide audit view but must not read colleagues' presence. It is widened only by (1) the userActivity.visibility:'all' blunt override, which keeps its documented meaning and wins, or (2) a separate usageAdminSar review (default `update clusterrolebindings`, a write verb cluster-reader fails and cluster-admin passes; the dashboard never writes, a SAR only asks). Separate resolver instance, separate cache, same 60s TTL and same fail-closed-to-self discipline. /api/whoami → unchanged plus a visibility field {tier, decided_at} so the UI renders truth, never decides it.

**Q4 — Is cluster-admin special, or merely one binding among many?**

Capability, not role membership: the tier is 'can this subject list clusterrolebindings', however granted. Measured consequences on this cluster: kubeadmin passes via a direct User CRB to cluster-admin; a member of system:cluster-readers passes via the group rule (SAR → true), so cluster-reader — read-everything, change-nothing — correctly lands in tier all, including for the log-derived logins data (SAR for get pods/log in openshift-authentication as cluster-readers → true, so the entitlement genuinely covers the dashboard's most sensitive source). jane.smith, whose LDAP group binds ClusterRole `admin` cluster-wide, does NOT pass — `admin` grants namespaced rolebinding reads but not clusterrolebindings list — and that is the correct answer, not a bug: she cannot read the surface the all tier shows, and an operator who wants her to have it binds the shipped viewer role or cluster-reader, leaving an audit trail in real RBAC. Capability survives a cluster that grants the read by any route; the auditor's question 'why does X see everything' is answered by `oc auth can-i list clusterrolebindings --as=X`, one command, authoritative.

**Q5 — What does a self-scoped reader see where a value is aggregate?**

Three-way ruling, not one rule. (1) SHOWN AS-IS: cluster-level counts and CR health KPIs (group totals, empty/unattributed, binding-finding counts, alert counts, groupsync states) — because they are ALREADY public unauthenticated on /metrics (measured with a credential-less curl), so hiding them from an authenticated reader protects nothing; the numbers keep their cluster-wide meaning and the UI keeps its labels truthful. (2) SUPPRESSED at self: aggregates that are personnel data even without names — the logins summary (failure counts, distinct users, by_outcome) and the ungoverned list; precedent is the project's own removal of gsd_dashboard_active_users from /metrics because 'even an unlabelled count of distinct users is personnel information'. What /metrics deliberately excludes, the self tier does not get. (3) RECOMPUTE REJECTED outright, with the measured degeneracy as the reason: recomputed membership-scoped aggregates are semantically empty — 'groups with zero members among the groups you belong to' is 0 by construction, 'distinct users among yourself' is 1 — and this codebase has already shipped the count-versus-page defect three times ('showing 50 of 30'); a number whose meaning changes with the viewer is that defect made permanent. Where a number describes the whole cluster it stays whole-cluster and visible-or-not; no number is quietly recomputed.

**Q6 — How does the UI show that a view is narrowed?**

Extend the two precedents the page already has, invent nothing. (1) The Usage tab's selfOnly banner (index.html ~line 874): every self-scoped tab renders one filterbar-note — 'Showing your view (<viewer>): your groups, your grants, your login attempts. An administrator sees the whole cluster.' — driven by a `scope: self|all` + `viewer` field the API puts on every scoped payload (the activity response already carries exactly these two fields; that contract generalises). (2) The Groups tab's none-match-vs-none-exist distinction: the self-tier empty state must say 'You are not a member of any synced group' (with the whoami name shown, which is also the diagnostic for the attribute-mismatch failure mode in the name-matching ruling), never an unqualified 'No groups'. Suppressed tabs (RBAC policy at self tier) are hidden from the nav, not rendered empty — an empty audit tab reads as a healthy cluster, which is a lie. The Logins tab at self tier additionally states 'attempts are recorded under the name as typed' beside the window note, because the byte-exact matching ruling means a case-variant attempt is invisible to its own author. All banners in both themes at WCAG 2.1 AA, per house rules; the scope-note span in the h1 already exists as a mount point.

**Q7 — Where is the decision enforced?**

Exactly one layer: THE API HANDLER, as a FastAPI dependency that resolves (viewer, tier) once per request from X-Forwarded-User + the cached SAR, with the store executing scope as bound SQL parameters and the UI only reflecting the response's scope field. Why the handler: it is the only layer that has all three inputs — the proxy-authenticated identity (constraint §5.3: header trusted only when oauth_proxy_enabled, which lives in Settings, which the store never sees), the tier, and the response shape (suppression is a 403 and field-omission, which a SQL predicate cannot express). It is also the codebase's existing precedent: /api/dashboard/activity enforces at the handler today — proxy check, 403, then scope_to passed into the store. Why NOT the store: it is the engine-neutral cache serving three callers (handlers, poller, metrics collector), two of which have no viewer; threading request identity through it couples storage to HTTP context, and its comment discipline (user_activity: 'user_name is the privacy scope... filtering in SQL rather than after the fetch matters — limit is applied by the database') already defines the correct division: the store executes the predicate, the handler owns the policy. Why NOT the UI: a control the response has already violated is a leak with a cosmetic fix — curl bypasses index.html entirely, and the API docs at /api advertise every endpoint. Concrete predicates, EXPLAIN QUERY PLAN measured against the live /data/gsd.db: LOGINS — the existing login_events(user_name=viewer) filter, plan 'SEARCH login_event USING INDEX login_event_by_user (cluster_id=? AND user_name=?)', index-served, no schema change. GROUPS — the one genuinely NEW query shape in this feature: SELECT g.* FROM group_state g JOIN group_member m ON m.cluster_id=g.cluster_id AND m.group_name=g.name WHERE g.cluster_id=? AND m.user_name=? ORDER BY g.name — plan shows group_state by its autoindex and group_member by its PK covering index; no new index needed at 65-group scale. users() and membership_events()/user_activity() gain/reuse a user_name parameter; user_binding WHERE user_name=? is a bounded scan (36 rows at reference scale, noted, no index yet). Endpoints needing NO store change because their self ruling is suppression or field-omission in the handler: bindings/findings, alerts, cluster-access (reuses is_in_access_group), groupsyncs, operator-configs. One deliberate non-predicate: COLLATE NOCASE on the logins match was measured to defeat the index (plan degrades to the cluster-wide login_event_lookup scan) and is also wrong on the merits — see the name-matching ruling.

**Q8 — What is the migration, and what is the default?**

Default SELF-tiered (visibility mode `rbac`), because the requirements' own §1 establishes this is a fix for showing readers data they hold no permission to see — a default of `all` ships the exposure for another release cycle and contradicts the document that motivated the work. Chart value `visibility.mode: rbac | all` (only the exact string 'all' widens, any other value means rbac — the _visibility_setting fail-safe pattern, reused). `all` restores today's behaviour verbatim as a deliberate documented choice, exactly as userActivity.visibility did for the same transition on the activity endpoint — that migration is the precedent and it shipped. Interlock: helm template FAILS when visibility.mode=rbac and oauthProxy.enabled=false — an rbac tier with no trusted identity is unsatisfiable (constraint §5.3); at runtime the same combination (belt to that brace) treats every request as self-with-no-identity: personal endpoints 403 like activity does today, public-by-metrics data still served. How the operator is told: the values.yaml comment block (# comments, WHY-form), a CHANGELOG/README upgrade note stating plainly 'plain authenticated readers now see only their own data; admins see no change; set visibility.mode: all to restore the old behaviour', and the UI banner itself — the first self-scoped reader after upgrade sees 'Showing your view', not an inexplicably empty cluster. Admins by definition pass the SAR and observe zero change on upgrade (DoD 2). Cache/staleness contract stated with the default: tier cached in-memory per replica, keyed by viewer, TTL 60s (one poll interval); a revoked administrator's worst-case retained visibility = TTL + in-flight page (≤ ~90s at the 30s refresh); a newly-granted administrator waits ≤ TTL, plus ≤ one poll interval more if the grant came via a synced Group (spec.groups is fed from the polled store — measured that SAR needs it). Both windows go in values.yaml and the response headers of whoami.

### Risks named by this lens

What this spec cannot guarantee, and what must be measured before code. (1) SAR latency in-cluster: my 138ms/call figure includes oc client startup from outside the cluster; the in-pod httpx number must be measured before fixing the 60s TTL, and the values.yaml comment the project already wrote ('a SubjectAccessReview from the app... makes a personal-data query depend on API-server availability') is a standing objection this design answers only via fail-closed-to-self plus caching — if API-server blips prove frequent on real clusters, admins will intermittently see the self banner, and that UX must be judged acceptable by the operator, not assumed. (2) The bearer-token path (apiTokenAccess/delegate-urls): whether the proxy sets X-Forwarded-User for token callers is a runtime claim I did not measure; until it is, the spec must state that token callers may land in the self tier regardless of entitlement. (3) The group-resolution dependency: tier correctness for group-granted admins rests on the polled group_member table — a cluster where the admin group is NOT synced into OpenShift Groups (granted by a group the dashboard never sees, e.g. an external OIDC group) will fail those admins closed to self; that population must be sized before the default flips. (4) Byte-exact name matching is fail-closed but not fail-obvious: an IdP-preferredUsername vs groupsync-userNameAttributes mismatch renders every reader's self view empty — the named empty-state diagnostic mitigates, but a pre-flight check (compare whoami names seen in activity against group_member names, warn in the log) should be considered and is not yet specified. (5) The mixed-case logins gap is measured (LATEEF.O row vs lateef.o viewer) and deliberately unfixed at self tier; if operators judge self-view completeness to outweigh it, the NOCASE index alternative exists but must confront both the measured index degradation and the case-sensitivity of OpenShift User names (two distinct Users differing only by case would cross-leak). (6) DoD 2 ('admin sees exactly what they see today') needs a golden-response test per endpoint at tier all, and any drift found there is a bug in the handler edits, not an accepted change.


## Lens 3 — operator surface, UI, migration and tests
**Summary.** Read in full: the requirements doc, api.py (1,127 lines — the scope/viewer contract and proxy-gated identity at /api/whoami and /api/dashboard/activity), config.py (the fail-to-self _visibility_setting parser at line 330), values.yaml (userActivity.visibility block, apiTokenAccess history), rbac.yaml (the auth-delegator binding is CONDITIONAL on apiTokenAccess.enabled — a chart gap the spec must close), NOTES.txt, the chart README's visibility row, and the index.html tab bar, Usage-tab scope banner and empty states. Measured on the live CRC cluster this session: lateef.o cannot list groups/users/clusterrolebindings and kubeadmin can (RBAC claims, can-i); the dashboard SA can create SubjectAccessReviews and, asked as the SA, the SAR answers false for lateef.o and true for kubeadmin (runtime claims, exercised); granting stock cluster-reader to lateef.o flips that SAR to true and revoking flips it back — the exact oc command the docs will print, proven end-to-end; ten sequential SARs as the SA took 1.55s wall including oc process launches, so a per-viewer cache at a 300s TTL makes the steady-state cost zero extra calls per poll. On that evidence, Lens 3 recommends: one new value `config.visibility: self|all` defaulting to self, sitting beside (not merging with) userActivity.visibility whose domain is disjoint; a scope pill plus per-tab banners and scoped empty states rendered from `scope`/`viewer` fields the response declares (the activity endpoint's shipped contract, and the search-box scar turned into a rule); NOTES.txt and README rows carrying the grant command and the rollback flag; and a hard-switch migration told four ways — NOTES, README upgrade note, startup log line, and the in-product banner that makes the narrowed view explain itself.

### Option — A — `config.visibility: self|all`, default `self`, beside (not replacing) userActivity.visibility; hard switch with four-channel telling  [RECOMMENDED]

**How.** One new chart value, `config.visibility` (default `self`), flowing configmap.yaml → `visibility` yaml key → Settings.visibility via a `_visibility_setting`-style parser that treats anything unrecognised as `self` (the exact fail-direction discipline of config.py:330-344). Meaning: what a reader who FAILS the admin SAR sees — `self` scopes the personal endpoints to the viewer and withholds governance views per Q3; `all` restores today's behaviour as an explicit, documented choice. Readers who pass the SAR (`list clusterrolebindings`, cached, fail-closed) always see everything. `config.userActivity.visibility` keeps its key, its semantics, and its domain (the Usage tab's personnel rows — data the dashboard generated, not cluster data); its values comment gains one cross-reference sentence, and the two knobs' domains are disjoint, so there is no combination where they contradict. Enforced in API handlers; every scoped response declares `scope`+`viewer` (the activity contract, reused); UI renders header pill + per-tab banners + scoped empty states from those fields. NOTES.txt gains a Visibility stanza with the grant command; README gains the values row and an Upgrading note. RBAC delta: the SA needs `create subjectaccessreviews` independent of apiTokenAccess — today the auth-delegator binding renders only when `oauthProxy.enabled AND apiTokenAccess.enabled` (rbac.yaml:114), and apiTokenAccess defaults false. Add one rule (`create` on subjectaccessreviews) to the reader ClusterRole instead of widening the auth-delegator condition: narrower (no tokenreviews the app never calls), and compatible with §5.1 since a SAR creates no persistent object — said explicitly in the rule's # comment.

**Evidence.** Live cluster, this session: `oc auth can-i create subjectaccessreviews --as=system:serviceaccount:group-sync-dashboard:group-sync-dashboard` → yes. SAR created AS the SA: lateef.o → allowed=false, kubeadmin → allowed=true. The documented grant command proven end-to-end: `oc adm policy add-cluster-role-to-user cluster-reader lateef.o` flipped the SAR to true; removal flipped it back to false. cluster-reader's live rules include get/list/watch on clusterrolebindings and user.openshift.io groups/users, so the all tier never shows that role more than oc would. Cost measured: 10 sequential SARs as the SA completed in 1.55s wall INCLUDING ten oc process launches — ≤155ms per review from outside the cluster, so an in-pod httpx call is cheap enough to hide behind a per-viewer cache. Precedent read in full: config.py:330-344 (fail-to-self parser), api.py:944-984 (scope/viewer response contract), index.html:877-884 (banner wording), values.yaml:891-928 (the honest-floor review and the removed readers list), README.md:147 (the row style to copy).

**Failure modes.** Upgrade surprise: a deployment whose whole org legitimately browsed everything sees narrowed views on upgrade day — mitigated by the four tellings and the one-flag rollback, not eliminated; the reader sees a banner naming the reason, never an unexplained empty page. SAR path broken (API server slow, RBAC rule dropped by a hand-edited role): fail-closed means every reader including admins degrades to the self view — the pod log carries one WARNING per failed review naming the viewer and the error, and the header pill reads 'Your view', so the symptom is legible ('admins suddenly see only themselves' → check the log). Revoked admin retains the wide view for at most the cache TTL — documented, bounded, default 300s. Operator sets `visibility: "ture"`: parser narrows to self and logs, never widens.

**Cost.** One SAR per distinct viewer per TTL (default 300s, matching bindingIntervalSeconds' rationale: tiers change on administrative action). Zero new API calls for cached viewers on the 30s poll. Code surface: one Settings field + parser, one tier-resolver in kube.py, per-endpoint predicates, UI banner/pill, one ClusterRole rule (`create subjectaccessreviews` — a new verb but not a write on anything reported on, per requirements §5.1), NOTES/README text, ~20 named tests.

### Option — B — Default `all`, `self` opt-in (compatible default)  [REJECTED]

**How.** Same machinery, but `config.visibility` defaults to `all`; nothing changes on upgrade until an operator opts in.

**Evidence.** The requirements' §1 measurement is the evidence AGAINST it: eight-for-eight resources a plain reader cannot list, yet every authenticated account sees them plus the login-failure record — so a compatible default ships the defect onward by default. The codebase's own precedents flipped defaults the safe way with loud comments: userActivity.visibility (values.yaml:337-360, 'It previously returned everyone to everyone') and unmanagedAudit.mode off→log (values.yaml:288-299). No measurement supports treating upgrade continuity as worth more than the exposure: the population that must not be surprised (admins) is unaffected by the flip, since they pass the SAR.

**Failure modes.** Every deployment that never reads the release notes keeps exposing every person's group memberships, grants, and failed-login causes to anyone who can log in. 'Secure only if you knew to ask' is the pattern this chart has spent several releases removing.

**Cost.** Same code surface as A; saves only the upgrade-communication work.

### Option — C — One merged `visibility` block that subsumes userActivity.visibility  [REJECTED]

**How.** Move the activity knob under a new `config.visibility` parent (e.g. visibility.default + visibility.userActivity), one place for all visibility decisions; old key dropped or aliased.

**Evidence.** Read against the live values surface: Helm does not fail on unknown keys, so an operator carrying `config.userActivity.visibility: all` upgrades and the value is silently ignored — measured behaviour of helm template with stray keys, and this chart has no values schema to catch it. The domains are also genuinely different: userActivity governs data the DASHBOARD generated about its own readers (and its comment at values.yaml:355-359 deliberately refused an admins-only tier for it — subsuming it under the SAR tier would let every cluster-reader see colleagues' presence records, a WIDENING of a personnel dataset as a side effect of a refactor). The overlapping-settings trap is real but is resolved by disjoint domains plus cross-referencing comments, not by a rename that breaks existing values files.

**Failure modes.** Silent loss of an explicitly-set value on upgrade (narrowing direction, so safe-ish, but a trap); or, if aliased, two spellings of one setting forever. If subsumption also gives admins the activity view, a documented privacy property of a shipped release changes without the operator asking.

**Cost.** A values migration note, alias-handling code, and a changed semantic for an existing setting — all spent to avoid one extra README row.

### Option — D — Two-release deprecation: ship 0.7 defaulting `all` with a warning, flip to `self` in 0.8  [VIABLE]

**How.** 0.7 adds the machinery defaulting `all`, logs a deprecation warning and renders a NOTES.txt notice ('the default becomes self in 0.8'); 0.8 flips the default.

**Evidence.** The standard practice for public charts with unknown consumers — but read against THIS distribution: chart 0.x, versioned by the operator's own build script (values.yaml:9-11), consumed by a known small set of deployments, and the thing deferred is live exposure of failed-login causes and the full RBAC surface (requirements §2 calls /logins the most sensitive endpoint in the application). The self-explaining UI (banner naming the narrowing) removes the main hazard a deprecation window exists to prevent: users mistaking the new behaviour for breakage.

**Failure modes.** One full release cycle during which the measured defect remains the default; two releases' worth of upgrade documentation instead of one; operators who set visibility=all in 0.7 'to be safe' and never revisit.

**Cost.** Same code as A plus a release of deprecation plumbing that exists only to be deleted.

**Recommendation.** Option A — `config.visibility: self` by default, beside an untouched userActivity.visibility, hard-switched with the NOTES.txt/README/log/banner four-channel telling — because the live cluster shows the tier machinery is already paid for (SA SAR yes; lateef.o false / kubeadmin true; the one documented grant command flips it), and this codebase has twice already established that a default which widens exposure is changed by flipping it loudly, not by waiting.

### Answers to the open questions

**Q1 — How is the tier decided, and against which resource?**

By SubjectAccessReview, created by the dashboard's own ServiceAccount, naming the viewer from X-Forwarded-User, asking `list clusterrolebindings.rbac.authorization.k8s.io`. That exact review is already this codebase's settled answer to "what is the honest floor for /api": oauthProxy.apiTokenAccess.delegateUrls carries `{"/api":{"resource":"clusterrolebindings","group":"rbac.authorization.k8s.io","verb":"list"}}`, chosen after `list groups` was measured to be a privilege escalation (values.yaml:891-907). Using the same predicate for the browser tier means the machine door and the human tier are ONE review the docs can state in one sentence, and `oc auth can-i list clusterrolebindings --as=<user>` answers 'which tier am I in' from the terminal. RBAC claims, measured on this cluster: `lateef.o` → no for list groups/users/clusterrolebindings; kubeadmin → yes. Runtime claims, exercised live: SAR created as `system:serviceaccount:group-sync-dashboard:group-sync-dashboard` (via impersonation) returned allowed=false for lateef.o and allowed=true for kubeadmin. Caveat stated honestly: impersonation exercises the SA's RBAC, not the literal in-pod token; but the SA's projected token is not an OAuth access token, so the user:info/user:check-access scope gate that killed -pass-access-token does not apply to it — and the same token already performs list calls every poll. A live smoke test (named below) closes the residual gap.

**Q2 — Does the app define its own ClusterRoles?**

No. The tier check names a real resource the dashboard reports on, so "you could read this with oc anyway" becomes literally true, and the administrator's grant surface is the STOCK role, not an app-shipped one. This repo already litigated the alternative: apiTokenAccess.readers — a chart value that created grants — was removed because "a Helm value is the wrong control for a cluster-level privilege" (values.yaml:913-928), and the documented grant is `oc adm policy add-cluster-role-to-group cluster-reader <group>`. Shipping Kiali-style app ClusterRoles would reopen exactly that door. Verified end-to-end on this cluster: `oc adm policy add-cluster-role-to-user cluster-reader lateef.o` flipped the SA's SAR for lateef.o from false to true, and removal flipped it back — so the one command the NOTES.txt will print demonstrably moves a reader between tiers, with no new role objects.

**Q3 — Data that belongs to nobody?**

Ruling per endpoint, from the reader-experience side (Lens 1/2 own the enforcement ruling; the wording below works for either outcome). SHOW IN FULL to the self tier: /groupsyncs (+events) — CR health names no person, is already on the credential-less /metrics, and hiding it makes the dashboard useless to the non-admin the product still serves (SUPERSEDED at 03ad446: /operator-configs was originally shown here too but is the ADMINISTRATOR TIER now — it has no /metrics analogue, so "names no person" did not make it public); /cluster-access's gated/dn/synced header (not the member lists). WITHHOLD from the self tier: /bindings/findings and /user-bindings' cluster view — findings name other subjects' grants, and the delegate-urls comment records the measurement that this data IS the RBAC surface (229 bindings including a cluster-admin CRB, readable through the dashboard by an identity that could not oc-read them). A withheld tab must be a NAMED refusal, never a blank: "This governance view needs the wider tier — ask an administrator for cluster-reader (see the chart README)", because a silent empty state teaches the reader the cluster has no findings.

**Q4 — Is cluster-admin special?**

Capability, not role membership: the SAR asks 'may this user list clusterrolebindings', not 'is this user bound to cluster-admin'. That survives a cluster granting the capability by another route, and the auditor story stays one command (`oc auth can-i list clusterrolebindings --as=<user>` — printed in NOTES.txt). cluster-reader lands in the ALL tier by construction, which is correct for a read-everything role: read from the live ClusterRole, cluster-reader's rules include get/list/watch on clusterrolebindings AND on user.openshift.io groups/users, so everything the wide view shows is data that role can already read with oc. Measured, not assumed: granting cluster-reader to lateef.o flipped the SA's SAR to allowed=true.

**Q5 — Aggregates for a self-scoped reader?**

Never silently recompute a number that keeps its old label — a KPI reading '3 empty groups' computed over the reader's one group means something different and the page would be lying. The self tier's Overview becomes a PERSONAL overview: your groups (N), your grants (N), your gate status, your last sign-in — numbers whose meaning matches their scope — plus the unscoped CR-health block from Q3. Cluster-wide KPIs and /api/alerts are withheld from the self tier with the named-refusal wording ('Alerts and cluster totals are governance data, visible to administrators'). /api/alerts returns an empty list plus scope:"self" rather than a recomputed subset, because an alert feed that quietly dropped rows would train readers that green means healthy when it means hidden.

**Q6 — How does the UI show a narrowed view?**

Three signals, all rendered FROM THE RESPONSE, never from the client's guess. (1) A header scope pill beside the existing #scope-note, on every tab, both tiers: self tier 'Your view — showing only what belongs to you'; all tier 'Full view — you are seeing everything (cluster RBAC read)'. The admin marker is the answer to 'what tells an administrator they see everything', and it must be text, not colour alone (WCAG, both themes). (2) A per-tab filterbar-note banner on scoped tabs, extending the Usage tab's shipped precedent (index.html:877-884): Groups — 'Showing only groups you belong to. The cluster-wide list needs list groups, which your account does not hold.'; Access granted — 'Showing only your own grants.'; Logins — 'Showing only your own sign-in attempts.' with the unconditional capture-window banner kept (index.html:1056 records why); RBAC policy / Namespace audit — the Q3 named refusal. (3) Empty states that distinguish 'narrowed and empty' from 'none exist', the Groups-tab discipline applied per tab: 'You are in no synced groups on this cluster' / 'Nothing grants you access through a synced group' / 'No sign-in attempts recorded for <viewer> since capture began <date>' — never the unscoped 'No groups match this filter'. The search-box scar (a UI that claimed credit for narrowing it was not doing) becomes a rule: every scoped endpoint declares `scope` and `viewer` in its response — the contract /api/dashboard/activity already ships — and the banner renders only what the response declares.

**Q7 — Where is enforced?**

At the API layer, in the handlers backed by store predicates — one layer. The UI is presentation of a scope the response declares (a UI-only narrowing is a leak with a cosmetic fix, and this page is one curl away from its API); the store cannot be the deciding layer because the tier is a request-time fact (viewer identity + SAR) the store does not hold, but it carries the scoping predicates (`user_name=` parameters), exactly the shape store.user_activity() already has for the activity precedent. From this lens the load-bearing addition: the response CONTRACT is part of enforcement — `scope` and `viewer` fields on every scoped endpoint are what let the UI be honest without being trusted.

**Q8 — Migration and default?**

Default `self`, hard switch, told four ways. The requirements' own framing decides it: this is a fix for showing readers data they hold no cluster permission to see (eight-for-eight measured no), and the codebase precedent is exactly this move — userActivity.visibility shipped as a default-flip from 'everyone to everyone' to self, and unmanagedAudit.mode moved off→log deliberately, both with the reasoning in the values comment. The operator is told: (1) NOTES.txt — renders on install AND upgrade — states the behaviour, the grant command, and the rollback; (2) a chart README 'Upgrading to 0.7' note plus the values-table row; (3) a startup log line naming the mode and the rollback flag, so 'the dashboard went empty' is diagnosable from the pod log; (4) the product itself explains the change — a reader who saw 200 groups yesterday sees 'Showing only groups you belong to' today, not silence, which is what makes a hard switch tolerable. Rollback is one flag: `--set config.visibility=all`. No transition release: every release defaulting to `all` keeps serving login-failure records and the full RBAC surface to any authenticated account, and this chart is 0.x with a small, known operator base.

### Risks named by this lens

What this spec cannot guarantee, and what must be measured before code. (1) The runtime-vs-RBAC gap: every SAR in this session ran via `oc --as=` impersonation, which exercises the SA's RBAC but not the literal projected token the pod presents; the token-scope trap that killed -pass-access-token applies to OAuth access tokens, not SA projected tokens, and the same token already lists resources every poll — but the first in-pod SAR must be smoke-tested (test_live_smoke.py::test_live_sa_can_create_a_subjectaccessreview) before the tier logic is trusted. (2) SAR latency was measured through oc from outside (≤155ms/call including process launch); the in-pod httpx figure and the cold-cache burst when N distinct readers open the page in one 30s window must be measured, and the TTL (proposed 300s — also the documented worst-case window a revoked admin retains the wide view, DoD #8) confirmed against it. (3) The Q3/Q5 per-endpoint rulings interlock with Lens 1/2's enforcement design; this lens specifies wording for both outcomes but the withhold-vs-show line for findings and alerts must be settled once, in one place. (4) The chart RBAC delta (create subjectaccessreviews on the reader role, currently reachable only via the apiTokenAccess-gated auth-delegator binding) changes what an auditor sees on the SA and needs its WHY comment and the §5.1 compatibility statement written into rbac.yaml itself. --- THE NAMED TESTS (fail before, pass after). tests/test_config.py: test_visibility_default_is_self; test_visibility_unrecognised_value_narrows_to_self; test_visibility_env_overrides_configmap. NEW tests/test_visibility.py (seeded app, proxy on, injectable tier resolver): test_self_reader_sees_only_their_own_groups; test_self_reader_sees_only_their_own_grants; test_self_reader_sees_only_their_own_login_attempts; test_self_reader_sees_only_their_own_gate_status; test_self_reader_cannot_read_another_users_profile; test_admin_sees_exactly_what_they_see_today (parametrised per endpoint, response-equal to pre-feature — DoD #2); test_indeterminate_tier_yields_the_self_view (resolver raises/times out → self view — the §5.4 fail-closed test, DoD #4); test_tier_check_failure_degrades_and_does_not_500; test_visibility_all_restores_the_old_behaviour; test_scope_and_viewer_are_declared_on_every_scoped_response; test_no_identity_behind_the_proxy_is_refused_not_widened; test_proxy_off_never_derives_a_tier_from_the_header (§5.3); test_tier_is_cached_per_viewer_within_the_ttl (two requests, one SAR); test_a_revoked_admin_loses_the_wide_view_after_the_ttl (DoD #8); test_a_failed_review_is_not_cached_as_a_tier. tests/test_ui.py: test_self_view_banner_names_the_viewer_and_the_reason; test_admin_header_says_it_is_everything; test_empty_self_view_is_not_mistaken_for_an_empty_cluster; test_scope_banner_renders_only_what_the_response_declares (the search-box scar as a regression test); test_withheld_governance_tab_is_a_named_refusal_not_a_blank. tests/test_accessibility.py: test_scope_pill_meets_contrast_in_both_themes. tests/test_metrics.py: test_tier_machinery_adds_no_username_label (§5.6). tests/test_chart_strategy.py (helm-template style): test_chart_renders_visibility_into_the_configmap; test_reader_role_grants_create_subjectaccessreviews; test_notes_txt_carries_the_grant_command_and_the_rollback_flag. tests/test_live_smoke.py: test_live_sa_can_create_a_subjectaccessreview.

---

# Arbitration of the code pass, 2026-08-09

Four lenses returned 79 snippets and 14 test functions. **Nothing is applied.** Each claim below was
re-measured by the arbiter before being accepted, and the two that changed the design are recorded
first.

## A1 — The RBAC gap. CONFIRMED, and it is a correction to the requirements

The code pass found that the ServiceAccount's `create subjectaccessreviews` grant renders only when
`apiTokenAccess.enabled` is true, which defaults false — so a default install has no SAR permission and
every reader would be self-tier forever. Reproduced: `helm template` at defaults yields **0**
auth-delegator objects, with the flag on, **3**. My requirements claim that "the expensive-looking part
is already paid for" was measured against the live release, which happens to have the flag on. The
requirements document now carries the correction.

**Accepted.** The chart must render the grant whenever visibility is enabled. Both of the code pass's
`rbac.yaml` snippets address exactly this and are the right shape.

## A2 — The groups question. CONFIRMED in both halves, each measured separately

The design supplies both the virtual groups and the user's real groups unconditionally. Each half now
has its own evidence, which it did not before:

```
list groups, john.doe (cluster-admin via a GROUP)
  spec.user only                                  -> allowed=false
  spec.user + spec.groups=[the admin group]       -> allowed=true     <- real groups required

get users/~, lateef.o (plain reader)
  spec.user only                                  -> allowed=false
  spec.user + spec.groups=[system:authenticated]  -> allowed=true     <- virtual groups required
```

The code pass's refinement is right and sharper than the requirements: the virtual groups are **not**
needed for the default threshold, because john.doe is admitted by his admin group's own binding. They
**are** needed for any operator-chosen threshold whose grant flows through `system:authenticated`, and
D2 makes the threshold choosable, so the code cannot know which kind it was given. Supplying both is
correct.

## A3 — The instrument was lying to me, mildly

`oc auth can-i --as=<user>` injects `system:authenticated` and does **not** resolve real group
memberships. Every measurement in this project taken with `--as` should be read with that in mind. It
does not move the role matrix — the `list` capabilities are unaffected and the probe users were bound
directly — but it does explain why `get users/~` looked universal when a raw user-only review denies
it.

## A4 — The test baseline. The code pass called mine stale; it was not

It reports the pristine baseline as 1078 and the brief's 1057 as stale. Both are correct and they are
different trees: `origin/main` measures **1057**, and this worktree measures **1078** because the
requirements and spec documents themselves add 21 parametrised doc-test cases. Verified by running
both. No disagreement survives, but the claim "+23 new tests, zero regressions" must be read against
1078, not 1057.

## A5 — What the arbiter has NOT yet verified

Recorded so nothing is mistaken for settled:

- **The 79 snippets have not been applied or compiled.** Anchors are quoted but unverified against the
  files; the code pass's own history in this project includes anchors that did not match and a test
  that failed against working code.
- **`_str_setting`** is referenced for the threshold's API-group handling and does not exist in
  `config.py` today — the same gap as the earlier work, where `whoami` depended on three `Settings`
  fields nobody had written. It must be written or the snippet reduced to existing helpers.
- **The identity-parity assumption**: that `X-Forwarded-User` is byte-equal to the `users` entries on
  Group objects. It holds on this LDAP provider; a `mappingMethod` that decorates the username would
  silently self-tier every administrator. Worth a guard rather than a comment.
- **Cost at scale**: one Group list per viewer per TTL, measured at 97 ms with 65 groups and one page.
  Unmeasured with a continue token.
- **The fail-open window** remains the design's sharpest edge: a user removed from an admin group keeps
  the wide view for up to the TTL. The code pass sets it to 60 s and states it in a docstring, which
  satisfies the requirement to document it, but the operator should decide whether 60 s is acceptable
  rather than inherit it.

---

# The code, as supplied by the code pass

Unapplied and unverified. Anchors are quoted as given.


## The authorization seam (kube.py, config.py)

**What it reports.** Read both docs in full, plus kube.py (all 1,038 lines), config.py, api.py's whoami/activity precedents, values.yaml's cluster block and rbac.yaml's auth-delegator condition. Measured on live CRC (2026-08-09), every SAR created with a token minted for the SA itself (`oc create token group-sync-dashboard -n group-sync-dashboard`), not impersonation: (a) grant sufficiency — `oc auth can-i create subjectaccessreviews --as=system:serviceaccount:group-sync-dashboard:group-sync-dashboard` → yes, and the exact POST the code makes answered 201 with a status under that token, so system:auth-delegator's `create subjectaccessreviews` half IS sufficient for this SAR on this deployment (the chart renders that binding only when apiTokenAccess is on — flagged in risks for the chart lens); (b) the groups question, answered by measurement: john.doe user-only → allowed=false; john.doe + [app-ocp-rbac-demo-cluster-admin] with NO system:authenticated → allowed=TRUE (reason: CRB demo-cluster-admin-crb) — so the virtual groups are NOT required when the admit comes from the admin group's own CRB; but lateef.o `get users/~` was false user-only and true only with system:authenticated (reason: CRB basic-users) — so any operator-chosen threshold flowing through system:authenticated REQUIRES them, and since D2 makes the shape choosable the code supplies both system:authenticated and system:authenticated:oauth unconditionally; (c) cost for the TTL: SAR 37–75ms, Group list 97ms at 65 groups (one page, no continue token). Wrote the seam: ClusterClient.fetch_groups_of_user (fresh paged Group read, byte-exact membership match), ClusterClient.create_subject_access_review (spec.user AND spec.groups, True only for a well-formed boolean allowed=true, ClusterError for everything else), TierResolver (per-viewer verdict cache, TTL 60s — worst-case stale window stated in the TIER_TTL_SECONDS docstring as the TTL itself, because BOTH inputs re-derive at refresh; failures collapse to self and are never cached; 5s request-path timeout), Settings/env wiring with GSD_ENABLE_VIEW_RESTRICTIONS (exact spelling, default true, malformed falls back restricted) and the D2 threshold as visibilityAdmin{Verb,Resource,ApiGroup,Namespace} with a _str_setting that preserves an explicit empty apiGroup (core group). Proved end to end: suite on the pristine worktree 1078 passed/1 skipped (the prompt's 1057 baseline is stale), with these changes 1101 passed/1 skipped = +23 new tests, zero regressions; and the actual TierResolver run live against CRC returned john.doe→all (173ms cold, 0.004ms cached), jane.smith (cluster-wide `admin` via Group)→self under the default threshold and →all under list-rolebindings — D2's matrix reproduced through the shipped code path — lateef.o→self, expired token→self uncached with one WARNING, unreachable cluster→self at exactly the 5.0s bound.

### `local-development/gsd/kube.py`

**Anchor.** `import re`

**Purpose.** Insert AFTER this line: threading guards the TierResolver's verdict cache, which FastAPI's threadpool reaches concurrently.

```
import threading
```

### `local-development/gsd/kube.py`

**Anchor.** `CLUSTERROLEBINDING_API = "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings"`

**Purpose.** Insert AFTER this line: the visibility constants — SAR path, tier vocabulary, the measured virtual-groups rule, and the TTL/timeout with the worst-case stale-visibility window stated where a reader will find it.

```

# ── Per-user visibility: the tier decision (docs/SPEC_per_user_visibility.md) ──────────────────

SAR_API = "/apis/authorization.k8s.io/v1/subjectaccessreviews"

# The two visibility tiers. Plain strings rather than an enum so they can sit directly in the
# `scope` field the API's responses already carry (/api/dashboard/activity's shipped contract).
TIER_SELF = "self"
TIER_ALL = "all"

# Virtual groups every real oauth token carries, ALWAYS added to the review's spec.groups.
#
# Measured with the ServiceAccount's own bearer token, 2026-08-09. The DEFAULT threshold does not
# strictly need them — `list groups` for john.doe was allowed on the strength of his admin group
# alone (spec.groups=["app-ocp-rbac-demo-cluster-admin"], reason naming CRB demo-cluster-admin-crb)
# — but the threshold is operator-CHOOSABLE, and any choice whose grant flows through
# system:authenticated fails without them: `get users/~` answered allowed=false user-only and
# allowed=true only once system:authenticated was supplied (reason: CRB basic-users of ClusterRole
# basic-user). This code cannot know which kind of threshold the operator picked, and every real
# login's token carries both, so supplying both keeps the review's input equal to the viewer's
# true token identity rather than a subset of it.
VIRTUAL_AUTH_GROUPS = ("system:authenticated", "system:authenticated:oauth")

TIER_TTL_SECONDS = 60.0
"""How long one viewer's decided tier is believed before it is re-derived from the cluster.

THE WORST-CASE STALE-VISIBILITY WINDOW — how long a user REMOVED from an admin group can retain
the wide view — is this TTL, measured from the moment the cluster itself reflects the removal
(plus the last wide response the browser already holds, ≤30s at the UI's poll cadence). The
window equals the TTL because BOTH inputs are re-derived at every refresh: the viewer's groups
come from a fresh Group list at decision time, not the poller's snapshot — the snapshot would
add pollIntervalSeconds on top — and the SubjectAccessReview evaluates live RBAC, so revocation
by deleting a ClusterRoleBinding is caught within the same bound. What the window deliberately
does NOT cover is upstream propagation: an LDAP removal reaches the OpenShift Group object only
when the group-sync operator next syncs, on that operator's schedule, not ours.

Sixty seconds because this failure direction is OPEN — a revoked administrator keeps seeing
everything until the refresh — so the window is bought as small as the refresh cost allows:
one Group list (97ms measured at the 65-group reference scale) plus one review (25-75ms
measured) per viewer per minute, against an API server the poller already asks far more of
every cycle. It also keeps "how stale can this dashboard be" a single number: the poll
interval and this TTL are the same figure.
"""

TIER_CHECK_TIMEOUT_SECONDS = 5.0
"""The tier decision's cluster timeout, deliberately tighter than the poller's default 15s.

The decision sits on the REQUEST path — a viewer's first page load blocks on it — so this is a
user-facing bound, not a bulk-list one. Five seconds is two orders of magnitude above the
measured answer time and small enough that an API-server outage degrades to a slow dashboard
failing closed to the self view rather than a hung one. Failures are never cached (see
TierResolver.tier_for), so recovery costs nothing beyond the next request.
"""
```

### `local-development/gsd/kube.py`

**Anchor.** `return out if any_crd_answered else None`

**Purpose.** Insert AFTER this line (the end of ClusterClient.fetch_operator_configs, before the module-level _condition helper): the two ClusterClient methods the tier decision needs, then the TierResolver itself. Verified live against CRC: john.doe (cluster-admin via Group) → all; jane.smith (cluster-wide admin via Group) → self under the default threshold, all under list-rolebindings; every failure → self.

```

    def fetch_groups_of_user(self, user_name: str) -> list[str]:
        """Names of the OpenShift Groups this user belongs to, read FRESH from the cluster.

        Fresh rather than from the poll snapshot, deliberately: this feeds spec.groups of the
        visibility SubjectAccessReview, and a snapshot input would stretch a revoked admin's
        retained wide view from the verdict TTL to pollIntervalSeconds + the TTL — in the
        direction that fails OPEN. Read at decision time, the window is the TTL alone (see
        TIER_TTL_SECONDS). Cost measured 2026-08-09: 97ms for the 65-group reference cluster,
        paid once per viewer per TTL. Paged like every other list here, so a cluster with more
        groups than one page holds resolves complete memberships rather than a silent subset.

        MEMBERSHIP IS MATCHED BYTE-EXACT. OpenShift User names are case-sensitive — two Users
        differing only in case are two identities — so a casefolded match would hand one of
        them the other's groups, and with them possibly the other's tier.
        """
        with self._client() as client:
            items = self._list_all(client, GROUP_API)
        return sorted(
            name
            for obj in items
            if (name := (obj.get("metadata") or {}).get("name"))
            and any(str(member) == user_name for member in obj.get("users") or [])
        )

    def create_subject_access_review(
        self, user: str, groups: list[str], resource_attributes: dict[str, str]
    ) -> bool:
        """One authorization.k8s.io/v1 SubjectAccessReview, created as our own ServiceAccount.

        spec.groups IS NOT OPTIONAL. A SubjectAccessReview resolves no group membership on its
        own: asked user-only about john.doe — cluster-admin via Group
        app-ocp-rbac-demo-cluster-admin — the API server answered allowed=false, and answered
        allowed=true only once that group was supplied in spec.groups (measured twice with the
        ServiceAccount's own bearer token; reason names CRB demo-cluster-admin-crb). Every real
        administrator on the reference cluster is group-granted, so omitting the groups would
        not weaken the check — it would invert the feature.

        An authorization QUERY, not a write: it creates no persistent object, so the
        ServiceAccount's no-write-verb rule holds. The permission is the `create
        subjectaccessreviews` half of system:auth-delegator, verified sufficient at runtime —
        this exact POST answered 201 under a token minted for the ServiceAccount.

        Returns True ONLY for a well-formed boolean status.allowed=true. Everything that is not
        a clean answer — connect error, timeout, 401, 403, any other >=400, a non-JSON body, a
        missing or non-boolean allowed — raises ClusterError, which the caller collapses to the
        self tier: the absence of an answer must never read as "allowed".
        """
        body = {
            "apiVersion": "authorization.k8s.io/v1",
            "kind": "SubjectAccessReview",
            "spec": {"user": user, "groups": groups, "resourceAttributes": resource_attributes},
        }
        with self._client() as client:
            try:
                response = client.post(SAR_API, json=body)
            except httpx.HTTPError as exc:
                raise ClusterError(UNREACHABLE, f"{type(exc).__name__}: {exc}") from exc
        if response.status_code == 401:
            raise ClusterError(AUTH_FAILED, "401 Unauthorized creating a SubjectAccessReview")
        if response.status_code == 403:
            raise ClusterError(
                FORBIDDEN,
                f"403 Forbidden on {SAR_API} — the ServiceAccount lacks `create "
                f"subjectaccessreviews` (the system:auth-delegator grant)",
            )
        if response.status_code >= 400:
            raise ClusterError(
                UNREACHABLE, f"HTTP {response.status_code} on {SAR_API}: {response.text[:200]}"
            )
        try:
            payload = response.json()
        except ValueError as exc:
            raise ClusterError(UNREACHABLE, f"non-JSON response from {SAR_API}: {exc}") from exc
        allowed = (payload.get("status") or {}).get("allowed")
        if not isinstance(allowed, bool):
            raise ClusterError(
                UNREACHABLE,
                f"{SAR_API} answered without a boolean status.allowed "
                f"(kind={payload.get('kind')!r}) — refusing to treat this as a decision",
            )
        return allowed


class TierResolver:
    """Decides, per viewer, self view or all view — by asking the cluster, failing closed.

    THE DECISION. One SubjectAccessReview, created as the dashboard's own ServiceAccount,
    naming the viewer AND the viewer's OpenShift Group memberships plus the virtual groups
    every token carries (VIRTUAL_AUTH_GROUPS). allowed=true is the all tier; a clean
    allowed=false, a missing identity, and EVERY failure are the self tier. The shape of the
    review — verb, resource, apiGroup, optional namespace — is the operator's choice
    (Settings.visibility_admin_*), defaulting to `list groups.user.openshift.io`, which admits
    cluster-admin and cluster-reader and nobody else among the stock roles (measured; `edit`
    and `view` pass no cluster-scoped list at all).

    WHY THE GROUPS COME FROM THE CLUSTER AND NOT FROM THE REQUEST. Nothing upstream has them:
    openshift/oauth-proxy forwards only X-Forwarded-User/-Email (its SessionState has no
    Groups field — read in source, not inferred), and SelfSubjectRulesReview answers as the
    caller, needing a token this app deliberately does not hold. The Group objects read here
    are the same objects RBAC itself evaluates, so the review's input mirrors what the
    viewer's real token would carry, staleness aside — and the staleness bound is
    TIER_TTL_SECONDS, where the worst-case window is stated.

    Thread-safe: handlers run in FastAPI's threadpool, so the cache is guarded. Concurrent
    cold-cache requests for one viewer may race into duplicate reviews; that costs one spare
    ~150ms round-trip, and both arrive at the same verdict, so it is left unserialised.
    """

    def __init__(
        self,
        cluster: ClusterConfig,
        *,
        verb: str,
        resource: str,
        api_group: str = "",
        namespace: str = "",
        ttl_seconds: float = TIER_TTL_SECONDS,
    ):
        self._kube = ClusterClient(cluster, timeout=TIER_CHECK_TIMEOUT_SECONDS)
        # resourceAttributes calls the API group `group`; an empty string is the CORE group
        # (pods, namespaces), so it is passed through rather than treated as unset.
        self._attributes = {"verb": verb, "resource": resource, "group": api_group}
        if namespace:
            self._attributes["namespace"] = namespace
        self._ttl = ttl_seconds
        self._cache: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()
        if not verb.strip() or not resource.strip():
            # Said once at startup rather than once per refused review. The API server will
            # reject the malformed SubjectAccessReview and every reader will fail closed to
            # the self view — safe, but it would otherwise present as "the feature broke",
            # diagnosed from one warning per request instead of one plain sentence.
            log.warning(
                "visibility admin threshold is malformed (verb=%r resource=%r) — every "
                "review it produces will be refused, so every reader gets the self view "
                "until the threshold is fixed",
                verb, resource,
            )

    def tier_for(self, viewer: str | None) -> str:
        """The tier for one viewer. Never raises; everything indeterminate is the self tier."""
        if not viewer:
            # No identity, no wide view. Whether ANY identity is trustworthy is the caller's
            # oauth-proxy guard; this is the belt to that brace.
            return TIER_SELF
        now = time.monotonic()
        with self._lock:
            cached = self._cache.get(viewer)
            if cached is not None and cached[0] > now:
                return cached[1]
        try:
            groups = self._kube.fetch_groups_of_user(viewer)
            allowed = self._kube.create_subject_access_review(
                viewer, [*groups, *VIRTUAL_AUTH_GROUPS], self._attributes
            )
        except ClusterError as exc:
            # EVERY failure — unreachable, timeout, 401, 403, malformed — is the self tier,
            # and it is NOT cached: a failure is not a decision, and caching one would pin an
            # administrator to the narrow view for a full TTL over a transient blip. The
            # reader still gets a page (their own data), never an error, so this warning is
            # the only place the cause is visible.
            log.warning(
                "%s: visibility tier for %r is indeterminate (%s: %s) — failing closed to "
                "the self view for this request",
                self._kube.cluster.name, viewer, exc.outcome, exc.message,
            )
            return TIER_SELF
        except Exception:
            # A bug in this path must degrade the same way a cluster failure does: the tier
            # is a security decision, and an exception escaping into the handler would turn
            # a fail-closed control into a 500 page.
            log.exception(
                "%s: visibility tier for %r is indeterminate — failing closed to the self "
                "view for this request",
                self._kube.cluster.name, viewer,
            )
            return TIER_SELF
        tier = TIER_ALL if allowed else TIER_SELF
        with self._lock:
            if len(self._cache) > 512:
                # Viewers are real authenticated people, so this stays small; the sweep only
                # exists so years of one-off names cannot grow the dict without bound.
                self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
            self._cache[viewer] = (now + self._ttl, tier)
        return tier
```

### `local-development/gsd/config.py`

**Anchor.** `user_activity_retention_days: int = 400`

**Purpose.** Insert AFTER this line (inside the Settings dataclass): D1's switch — default ON, exact env spelling GSD_ENABLE_VIEW_RESTRICTIONS — and D2's threshold expressed as the review itself.

```

    # ── Per-user visibility (docs/SPEC_per_user_visibility.md, decisions D1/D2) ──────────────────
    # ON by default because this is a fix, not a feature: the dashboard reads the cluster with its
    # own ServiceAccount, so without restrictions every authenticated reader sees data they hold
    # no cluster permission to see — measured eight-for-eight in the requirements. False restores
    # the wide view for every reader as a deliberate, documented operator choice. An INDETERMINATE
    # tier (review error, timeout, malformed answer) is NOT that choice: it yields the self view,
    # never the wide one (kube.TierResolver).
    #
    # The env var is GSD_ENABLE_VIEW_RESTRICTIONS — spelling load-bearing: a misspelled name here
    # is read by nothing and becomes a silently disabled security control.
    enable_view_restrictions: bool = True
    # The administrator threshold, expressed as the SubjectAccessReview itself rather than a list
    # of role names — a named-role list would miss cluster-reader and every custom grant route.
    # The default, `list groups.user.openshift.io`, admits cluster-admin and cluster-reader and no
    # other stock role (measured); `list rolebindings.rbac.authorization.k8s.io` additionally
    # admits cluster-wide `admin`; `edit` and `view` pass no cluster-scoped list at all and cannot
    # be a threshold with any resource this dashboard reports on.
    visibility_admin_verb: str = "list"
    visibility_admin_resource: str = "groups"
    # Empty is a REAL value for the API group — it names the core group (pods, namespaces) — which
    # is why these load via _str_setting rather than an `or` chain that would rewrite it.
    visibility_admin_api_group: str = "user.openshift.io"
    # Empty means a cluster-scoped review. Set it to ask about one namespace — e.g. a threshold of
    # `list rolebindings` in a team's namespace for a deployment scoped to that team.
    visibility_admin_namespace: str = ""
```

### `local-development/gsd/config.py`

**Anchor.** `def _bool_setting(raw: dict, env_name: str, yaml_key: str, default: bool) -> bool:`

**Purpose.** Insert BEFORE this line: a string-setting loader that distinguishes absent from empty, because an explicit empty apiGroup names the core API group and must survive.

```
def _str_setting(raw: dict, env_name: str, yaml_key: str, default: str) -> str:
    """Env wins over the ConfigMap; ABSENT means the default, but EMPTY is a real value.

    The `env or yaml or default` chain the other string settings use treats an explicit empty
    string as unset — and for the visibility threshold an empty apiGroup is meaningful: it names
    the CORE API group. A threshold of `list pods` (core) silently becoming
    `list pods.user.openshift.io` would refuse every administrator and read as "the feature
    broke", with the cause invisible in the config that looks correctly set.
    """
    source = os.environ.get(env_name)
    if source is None:
        source = raw.get(yaml_key)
    if source is None:
        return default
    return str(source).strip()
```

### `local-development/gsd/config.py`

**Anchor.** `user_activity_visibility=_visibility_setting(raw),`

**Purpose.** Insert AFTER this line (inside the Settings(...) construction in load_settings): wire the new keys, env winning over the ConfigMap per house pattern, with the fail-direction stated.

```
        # A malformed value falls back to the DEFAULT, and the default is the RESTRICTED
        # direction — a typo in this env var must never widen who sees the cluster.
        enable_view_restrictions=_bool_setting(
            raw, "GSD_ENABLE_VIEW_RESTRICTIONS", "enableViewRestrictions", True
        ),
        visibility_admin_verb=_str_setting(
            raw, "GSD_VISIBILITY_ADMIN_VERB", "visibilityAdminVerb", "list"
        ),
        visibility_admin_resource=_str_setting(
            raw, "GSD_VISIBILITY_ADMIN_RESOURCE", "visibilityAdminResource", "groups"
        ),
        visibility_admin_api_group=_str_setting(
            raw, "GSD_VISIBILITY_ADMIN_API_GROUP", "visibilityAdminApiGroup", "user.openshift.io"
        ),
        visibility_admin_namespace=_str_setting(
            raw, "GSD_VISIBILITY_ADMIN_NAMESPACE", "visibilityAdminNamespace", ""
        ),
```

### `local-development/gsd/api.py`

**Anchor.** `from .leader import LeaderElector`

**Purpose.** Insert BEFORE this line: the tier vocabulary and resolver the glue below uses.

```
from .kube import TIER_ALL, TIER_SELF, TierResolver
```

### `local-development/gsd/api.py`

**Anchor.** `@asynccontextmanager`

**Purpose.** Insert BEFORE this line (inside build_app, after the ActivityRecorder block): construct the resolver against the local cluster, log the effective mode, and define resolve_tier — the single function where D1 is applied and everything indeterminate fails closed. This is the seam the handler lens consumes.

```
    # ── Per-user visibility: the tier decision (docs/SPEC_per_user_visibility.md) ──────────
    # Decided against the FIRST enabled cluster, deliberately: the oauth-proxy authenticates
    # viewers against the cluster this pod runs on, and that is the entry the chart writes
    # (kubernetes.default.svc with the pod's own projected ServiceAccount token). The tier it
    # yields gates everything this instance SHOWS — rows about other observed clusters
    # included — because the viewer's identity only means something here; remote clusters
    # never see this review.
    tier_resolver: TierResolver | None = None
    local_cluster = next((c for c in settings.clusters if c.enabled), None)
    if settings.enable_view_restrictions and local_cluster is not None:
        tier_resolver = TierResolver(
            local_cluster,
            verb=settings.visibility_admin_verb,
            resource=settings.visibility_admin_resource,
            api_group=settings.visibility_admin_api_group,
            namespace=settings.visibility_admin_namespace,
        )
    if not settings.enable_view_restrictions:
        # WARNING rather than INFO: this is the one switch that restores the measured exposure
        # (every authenticated reader sees the full RBAC surface and the login record), and the
        # pod log is where "why can everyone see everything" gets answered.
        log.warning(
            "view restrictions are OFF (enableViewRestrictions=false / "
            "GSD_ENABLE_VIEW_RESTRICTIONS=false): every authenticated reader gets the full "
            "cluster view, as a deliberate operator choice"
        )
    elif tier_resolver is None:
        log.warning(
            "view restrictions are on but no enabled cluster is configured to answer the "
            "SubjectAccessReview — every reader will get the self view"
        )

    def resolve_tier(viewer: str | None) -> str:
        """The one place decision D1 is applied: restrictions off is the wide view by choice;
        everything else fails closed.

        The proxy guard comes FIRST. With the proxy off, X-Forwarded-User is whatever the
        caller typed, and a tier derived from it would be worse than no control — the same
        rule /api/dashboard/activity already enforces for its identity.
        """
        if not settings.enable_view_restrictions:
            return TIER_ALL
        if not settings.oauth_proxy_enabled or not viewer or tier_resolver is None:
            return TIER_SELF
        return tier_resolver.tier_for(viewer)
```

### `local-development/gsd/api.py`

**Anchor.** `app.state.settings = settings`

**Purpose.** Insert AFTER this line: expose the seam so the handler lens and tests reach one substitutable function.

```
    # The visibility seam, exposed for the handlers and for tests to substitute: a fake
    # resolve_tier is how a test forces the all tier, the self tier, or an indeterminate
    # answer without a cluster.
    app.state.resolve_tier = resolve_tier
```

### Test — `test_visibility_tier.py (new file, 23 tests — all fail before via ImportError, all pass after; full suite 1101 passed/1 skipped vs pristine 1078/1)` in `local-development/tests/test_visibility_tier.py`

```python
"""The visibility tier decision: groups resolved fresh, a SAR that carries them, fail-closed.

Every failure test here is requirement §5.4 (an indeterminate answer yields the self view,
never the wide one) made executable, and the group-carrying tests pin the measured finding
that shaped the code: a SubjectAccessReview without spec.groups answers allowed=false for a
cluster-admin whose grant arrives through a Group — which is every real administrator on the
reference cluster — so omitting them would invert the feature, not weaken it.

HTTP is mocked at the transport, the test_kube_reader idiom: no cluster is needed, and the
real request/response parsing runs.
"""
from __future__ import annotations

import json
import time

import httpx
import pytest

from gsd.config import ClusterConfig, load_settings
from gsd.kube import (
    SAR_API,
    TIER_ALL,
    TIER_SELF,
    VIRTUAL_AUTH_GROUPS,
    TierResolver,
)

GROUPS_PATH = "/apis/user.openshift.io/v1/groups"

BASE_CONFIG = """
clusters:
  - name: crc-local
    apiUrl: https://api.crc.testing:6443
    tokenEnv: GSD_TOKEN_CRC
"""


def _group(name: str, users: list[str]) -> dict:
    return {"metadata": {"name": name}, "users": users}


class FakeCluster:
    """Answers the resolver's two calls and records exactly what was asked."""

    def __init__(self, groups: list[dict], allowed: bool = True):
        self.groups = groups
        self.allowed = allowed
        self.sar_bodies: list[dict] = []
        self.group_lists = 0
        self.raise_exc: Exception | None = None       # raised for every call when set
        self.sar_status = 201
        self.sar_body_override: dict | str | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.raise_exc is not None:
            raise self.raise_exc
        if request.url.path == GROUPS_PATH:
            self.group_lists += 1
            return httpx.Response(
                200, json={"kind": "GroupList", "items": self.groups, "metadata": {}}
            )
        assert request.url.path == SAR_API, request.url.path
        self.sar_bodies.append(json.loads(request.content))
        if isinstance(self.sar_body_override, str):
            return httpx.Response(self.sar_status, text=self.sar_body_override)
        if self.sar_body_override is not None:
            return httpx.Response(self.sar_status, json=self.sar_body_override)
        return httpx.Response(self.sar_status, json={"status": {"allowed": self.allowed}})


def _resolver(monkeypatch, fake: FakeCluster, **kwargs) -> TierResolver:
    kwargs.setdefault("verb", "list")
    kwargs.setdefault("resource", "groups")
    kwargs.setdefault("api_group", "user.openshift.io")
    resolver = TierResolver(ClusterConfig("c", "https://api.example", token_env="X"), **kwargs)
    transport = httpx.MockTransport(fake.handler)
    monkeypatch.setattr(
        resolver._kube, "_client",
        lambda: httpx.Client(transport=transport, base_url="https://api.example"),
    )
    return resolver


class TestTheReviewCarriesTheGroups:
    def test_a_group_granted_admin_is_admitted_with_polled_plus_virtual_groups(self, monkeypatch):
        """The measured trap: user-only, this exact admin was allowed=false. The review must
        carry the memberships read from the cluster AND the virtual groups every token has."""
        fake = FakeCluster(
            groups=[
                _group("app-ocp-rbac-demo-cluster-admin", ["john.doe"]),
                _group("some-other-team", ["jane.smith"]),
            ],
            allowed=True,
        )
        resolver = _resolver(monkeypatch, fake)
        assert resolver.tier_for("john.doe") == TIER_ALL
        spec = fake.sar_bodies[0]["spec"]
        assert spec["user"] == "john.doe"
        assert spec["groups"] == ["app-ocp-rbac-demo-cluster-admin", *VIRTUAL_AUTH_GROUPS]
        assert spec["resourceAttributes"] == {
            "verb": "list", "resource": "groups", "group": "user.openshift.io",
        }

    def test_membership_is_matched_byte_exact_not_casefolded(self, monkeypatch):
        """OpenShift User names are case-sensitive: two Users differing only in case are two
        identities, and a casefolded match would hand one the other's groups — and tier."""
        fake = FakeCluster(groups=[_group("admins", ["lateef.o"])])
        resolver = _resolver(monkeypatch, fake)
        resolver.tier_for("LATEEF.O")
        assert fake.sar_bodies[0]["spec"]["groups"] == list(VIRTUAL_AUTH_GROUPS)

    def test_the_operators_threshold_shapes_the_review_namespace_included(self, monkeypatch):
        """D2: the threshold is the review itself — verb, resource, apiGroup, namespace."""
        fake = FakeCluster(groups=[])
        resolver = _resolver(
            monkeypatch, fake,
            verb="list", resource="rolebindings",
            api_group="rbac.authorization.k8s.io", namespace="team-a",
        )
        resolver.tier_for("someone")
        assert fake.sar_bodies[0]["spec"]["resourceAttributes"] == {
            "verb": "list", "resource": "rolebindings",
            "group": "rbac.authorization.k8s.io", "namespace": "team-a",
        }

    def test_an_empty_api_group_is_sent_as_the_core_group(self, monkeypatch):
        """'' names the core API group; rewriting it to a default would refuse every admin."""
        fake = FakeCluster(groups=[])
        resolver = _resolver(monkeypatch, fake, verb="list", resource="pods", api_group="")
        resolver.tier_for("someone")
        attrs = fake.sar_bodies[0]["spec"]["resourceAttributes"]
        assert attrs["group"] == "" and "namespace" not in attrs


class TestFailClosed:
    def test_a_clean_denial_is_the_self_tier(self, monkeypatch):
        fake = FakeCluster(groups=[], allowed=False)
        assert _resolver(monkeypatch, fake).tier_for("lateef.o") == TIER_SELF

    def test_no_viewer_is_self_without_touching_the_cluster(self, monkeypatch):
        fake = FakeCluster(groups=[])
        resolver = _resolver(monkeypatch, fake)
        assert resolver.tier_for("") == TIER_SELF
        assert resolver.tier_for(None) == TIER_SELF
        assert fake.group_lists == 0 and fake.sar_bodies == []

    @pytest.mark.parametrize(
        "break_it",
        [
            pytest.param(lambda f: setattr(f, "sar_status", 401), id="401"),
            pytest.param(lambda f: setattr(f, "sar_status", 403), id="403"),
            pytest.param(lambda f: setattr(f, "sar_status", 500), id="500"),
            pytest.param(
                lambda f: setattr(f, "raise_exc", httpx.ConnectTimeout("simulated timeout")),
                id="timeout",
            ),
            pytest.param(
                lambda f: setattr(f, "sar_body_override", {"kind": "SubjectAccessReview"}),
                id="missing-status",
            ),
            pytest.param(
                lambda f: setattr(f, "sar_body_override", {"status": {"allowed": "yes"}}),
                id="non-boolean-allowed",
            ),
            pytest.param(
                lambda f: (setattr(f, "sar_status", 200),
                           setattr(f, "sar_body_override", "<html>login</html>")),
                id="non-json",
            ),
        ],
    )
    def test_every_failure_collapses_to_the_self_tier(self, monkeypatch, break_it, caplog):
        """§5.4: an indeterminate answer is the self view, never the wide one — and it is
        said in the log, because the reader sees their own data rather than an error."""
        fake = FakeCluster(groups=[_group("admins", ["john.doe"])], allowed=True)
        break_it(fake)
        resolver = _resolver(monkeypatch, fake)
        assert resolver.tier_for("john.doe") == TIER_SELF
        assert "failing closed to the self view" in caplog.text

    def test_a_failure_is_not_cached_so_recovery_is_the_next_request(self, monkeypatch):
        """A failure is not a decision: caching one would pin an administrator to the narrow
        view for a full TTL over a transient API-server blip."""
        fake = FakeCluster(groups=[_group("admins", ["john.doe"])], allowed=True)
        fake.sar_status = 500
        resolver = _resolver(monkeypatch, fake)
        assert resolver.tier_for("john.doe") == TIER_SELF
        fake.sar_status = 201
        assert resolver.tier_for("john.doe") == TIER_ALL


class TestTheCacheBoundsTheWindow:
    def test_a_decided_tier_is_cached_within_the_ttl(self, monkeypatch):
        fake = FakeCluster(groups=[_group("admins", ["john.doe"])], allowed=True)
        resolver = _resolver(monkeypatch, fake)
        assert resolver.tier_for("john.doe") == TIER_ALL
        assert resolver.tier_for("john.doe") == TIER_ALL
        assert fake.group_lists == 1 and len(fake.sar_bodies) == 1

    def test_a_revoked_admin_loses_the_wide_view_after_the_ttl(self, monkeypatch):
        """DoD #8: the worst-case retained-visibility window is the TTL, and expiry re-reads
        BOTH inputs — the groups fresh from the cluster and the review against live RBAC."""
        fake = FakeCluster(groups=[_group("admins", ["john.doe"])], allowed=True)
        resolver = _resolver(monkeypatch, fake, ttl_seconds=0.05)
        assert resolver.tier_for("john.doe") == TIER_ALL
        fake.allowed = False                        # the revocation lands on the cluster
        assert resolver.tier_for("john.doe") == TIER_ALL   # inside the TTL: the stated window
        time.sleep(0.06)
        assert resolver.tier_for("john.doe") == TIER_SELF
        assert fake.group_lists == 2, "expiry must re-read the groups, not reuse the snapshot"

    def test_tiers_are_cached_per_viewer_not_globally(self, monkeypatch):
        fake = FakeCluster(groups=[_group("admins", ["john.doe"])], allowed=True)
        resolver = _resolver(monkeypatch, fake)
        assert resolver.tier_for("john.doe") == TIER_ALL
        fake.allowed = False
        assert resolver.tier_for("lateef.o") == TIER_SELF
        assert resolver.tier_for("john.doe") == TIER_ALL


class TestSettings:
    def _write(self, tmp_path, text: str) -> str:
        p = tmp_path / "clusters.yaml"
        p.write_text(text)
        return str(p)

    def test_view_restrictions_default_on(self, tmp_path):
        """D1: this is a fix for an exposure; shipping it off by default leaves the exposure
        in place on exactly the installs that never read release notes."""
        s = load_settings(self._write(tmp_path, BASE_CONFIG))
        assert s.enable_view_restrictions is True
        assert s.visibility_admin_verb == "list"
        assert s.visibility_admin_resource == "groups"
        assert s.visibility_admin_api_group == "user.openshift.io"
        assert s.visibility_admin_namespace == ""

    def test_the_exact_env_var_spelling_disables(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESTRICTIONS", "false")
        assert load_settings(self._write(tmp_path, BASE_CONFIG)).enable_view_restrictions is False

    def test_the_operators_typo_spelling_does_not_disable(self, tmp_path, monkeypatch):
        """The variable's spelling is load-bearing: the misspelled RESCRICTIONS variant is
        read by nothing, so setting it must leave the control ON, not silently off."""
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESCRICTIONS", "false")
        assert load_settings(self._write(tmp_path, BASE_CONFIG)).enable_view_restrictions is True

    def test_a_malformed_disable_falls_back_to_restricted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESTRICTIONS", "flase")
        assert load_settings(self._write(tmp_path, BASE_CONFIG)).enable_view_restrictions is True

    def test_the_threshold_flows_from_the_configmap_and_env_wins(self, tmp_path, monkeypatch):
        cfg = BASE_CONFIG + (
            "visibilityAdminVerb: list\n"
            "visibilityAdminResource: rolebindings\n"
            "visibilityAdminApiGroup: rbac.authorization.k8s.io\n"
            "visibilityAdminNamespace: team-a\n"
        )
        s = load_settings(self._write(tmp_path, cfg))
        assert s.visibility_admin_resource == "rolebindings"
        assert s.visibility_admin_api_group == "rbac.authorization.k8s.io"
        assert s.visibility_admin_namespace == "team-a"
        monkeypatch.setenv("GSD_VISIBILITY_ADMIN_RESOURCE", "clusterrolebindings")
        s = load_settings(self._write(tmp_path, cfg))
        assert s.visibility_admin_resource == "clusterrolebindings"

    def test_an_explicit_empty_api_group_means_core_not_the_default(self, tmp_path):
        """`or`-chaining would rewrite '' into user.openshift.io and silently change a
        core-group threshold into one that refuses every administrator."""
        cfg = BASE_CONFIG + 'visibilityAdminApiGroup: ""\n'
        assert load_settings(self._write(tmp_path, cfg)).visibility_admin_api_group == ""
```

**Risks it names.** 1) DEFAULT-INSTALL RBAC GAP (chart lens must close it): the SA's `create subjectaccessreviews` comes from the auth-delegator binding, which rbac.yaml renders only when `oauthProxy.enabled AND apiTokenAccess.enabled` (apiTokenAccess defaults false). Verified sufficient on THIS deployment, NOT on a default install — without the grant every reader is permanently self (fail-closed, but the feature looks broken). The chart must render the grant whenever visibility is on, with a helm-template test. 2) The `resolve_tier` seam is exposed but UNCONSUMED until Lens 2 wires the handlers — until then behaviour is unchanged; Lens 2 should call `app.state.resolve_tier` (or capture the closure) and its tests substitute the app.state attribute. 3) The stated 60s window is measured from the OpenShift Group object changing; LDAP→Group propagation rides the group-sync operator's own schedule and is explicitly excluded (said in the TIER_TTL_SECONDS comment). 4) An admin whose grant flows through a group that is NOT an OpenShift Group object (external OIDC) fails closed to self — size that population before GA. 5) Fresh-read cost: one Group list per viewer per TTL, 97ms measured at 65 groups but unmeasured at multi-page scale; the trade buys the minimal window, and TIER_TTL_SECONDS is the one knob if a large cluster hurts. Failures are deliberately uncached, so a sustained API-server outage costs each uncached request up to the 5s bound and shows admins the self view — fail-closed by requirement, but the UX during outages must be judged by the operator, not assumed. 6) Identity parity (X-Forwarded-User byte-equal to Group `users` entries) holds on this LDAP IdP; a decorating mappingMethod would silently self-tier admins — verify on any second cluster shape. 7) The tier is decided by the FIRST enabled cluster's RBAC and gates rows about all observed clusters (stated in the api.py comment); per-remote-cluster tiers are out of scope. 8) The concurrent cold-cache race can issue duplicate reviews for one viewer (~150ms wasted, same verdict) — left unserialised, said in the class docstring.


## API scoping and store predicates

**What it reports.** Read both docs in full plus api.py, config.py, store.py (schema, every read the scoping touches), kube.py, storage.py and the chart templates; then measured rather than asserted the two open questions. (1) Name-matching, measured on the live CRC database (oc exec, sqlite read-only): X-Forwarded-User is recorded verbatim in dashboard_user_activity as `lateef.o` — byte-identical to group_member, ocp_user and membership_event for the same person — so the viewer-to-rows join is byte-exact string equality with no normalisation; login_event additionally holds an as-typed `LATEEF.O` row beside `lateef.o`, and user_binding holds administrator-typed forms (`jdoe`, `asmith`) that match no member name, so both stay wide-tier-only by the same byte-exact rule (fail-closed, documented in comments where the predicates live). (2) Every new predicate was EXPLAIN QUERY PLAN'd on the live /data/gsd.db: groups-for-viewer = group_state PK autoindex + group_member PK covering index; users self = group_member_by_user; membership self = membership_event_by_user; logins self rows and count = login_event_by_user (covering); is_group_member = one PK covering probe; only the user_binding self filter is a bounded scan of the cluster slice (45 rows at reference scale) — no new index needed anywhere. Enforcement follows the /api/dashboard/activity precedent exactly: a viewer_scope helper in build_app resolves (viewer, scope) once per request — X-Forwarded-User believed only behind the proxy, tier from an injected resolver (Lens 1's SAR seam) where ONLY the exact string "all" widens and every failure (no resolver, error, junk answer, no header) lands on self per D1 — and the handler passes user_name into the store as a bound parameter. Per-endpoint rulings: groups/users/logins/user-bindings/membership-changes/cluster-access self-scoped with per-response scope+viewer; group and user detail 403 constant-before-existence for non-self names; groupsyncs, events, operator-configs and bindings/findings FULL view (governance about objects — findings' named subjects are Group names; the person-named rows live on /user-bindings and are scoped there); aggregates withheld as None at self (never zeros, never recomputed — the logins summary/ungoverned, the user-bindings rollup, the cluster-access lists/DN); /api/alerts filtered by a fail-closed kind allow-list under its own page-behind-it invariant and converted to an object; /groups likewise list→object (the two UI unwraps included). Verification on a scratch copy found and fixed one real bug in my own code — the pre-existing dangling-alert loop rebinding `scope` would have failed the filter OPEN — plus the storage-protocol parity the seam test enforces. Full suite: 1104 passed, 1 skipped (baseline 1078) including 26 new tests, one of which was proven to fail on the buggy variant. The API layer itself makes zero new cluster calls and needs no new ServiceAccount verb; the resolver seam's SAR is covered by the already-held create subjectaccessreviews from system:auth-delegator on this deployment (chart-gap caveat in risks).

### `local-development/gsd/config.py`

**Anchor.** `oauth_proxy_enabled: bool = False`

**Purpose.** Settings gains the D1 switch, ON by default, with the WHY and the load-bearing env-var spelling recorded where the field lives. Insert AFTER the anchor line (before user_activity_enabled).

```
    # Per-user view restrictions (docs/SPEC_per_user_visibility.md, decision D1). ON by
    # default because this is a fix for an exposure, not a feature: every authenticated
    # reader currently sees the ServiceAccount's view of the whole RBAC surface. `false`
    # restores the wide view as a deliberate, documented choice. The spelling of the env
    # var is load-bearing — GSD_ENABLE_VIEW_RESTRICTIONS — because a typo here is a
    # silently disabled security control.
    view_restrictions_enabled: bool = True
```

### `local-development/gsd/config.py`

**Anchor.** `raw, "GSD_OAUTH_PROXY_ENABLED", "oauthProxyEnabled", False`

**Purpose.** Wire GSD_ENABLE_VIEW_RESTRICTIONS / viewRestrictionsEnabled into load_settings, default True (a malformed value falls back to True — the narrowing direction). Insert AFTER the `),` line that closes the oauth_proxy_enabled=_bool_setting(...) call containing the anchor.

```
        view_restrictions_enabled=_bool_setting(
            raw, "GSD_ENABLE_VIEW_RESTRICTIONS", "viewRestrictionsEnabled", True
        ),
```

### `local-development/gsd/api.py`

**Anchor.** `from contextlib import asynccontextmanager`

**Purpose.** Import Callable for the tier_resolver seam. Insert BEFORE the anchor line.

```
from collections.abc import Callable
```

### `local-development/gsd/api.py`

**Anchor.** `#: What a `no match` refusal actually was, once gate membership is known.`

**Purpose.** The self tier's alert allow-list — fail-closed for future kinds, membership decided by the feed's own page-behind-it invariant. Insert BEFORE the anchor line, separated by two blank lines on each side.

```
# Alert kinds the SELF tier receives — an ALLOW-list, so a kind added later is hidden from
# the narrow view until someone rules on it, which is the fail-closed direction.
#
# Membership is decided by the feed's own invariant, "an alert here always has a page
# behind it": every kind here is backed by a page the self tier sees IN FULL (the cluster
# cards, GroupSync CRs and their events, operator configs, binding findings — all ruled
# governance data about objects). The excluded kinds are backed by pages the self tier does
# not see whole: `empty_group`, `unattributed` and `stale_group` name groups from the
# self-scoped Groups tab (and an empty group can never contain the viewer), and
# `direct_user_binding` aggregates other people's grants from the self-scoped
# user-bindings view.
SELF_ALERT_KINDS = frozenset({
    # Poll failures — kind carries poll_outcome.status verbatim.
    "auth_failed", "forbidden", "unreachable",
    # GroupSync CR health, full-view at both tiers.
    "groupsync_crd_absent", "invalid_schedule", "sync_stopped", "overdue", "reconcile_error",
    # Policy-operator health and binding findings, full-view at both tiers.
    "config_reconcile_error", "dangling_binding",
})
```

### `local-development/gsd/api.py`

**Anchor.** `def build_app(settings: Settings, run_poller: bool = True) -> FastAPI:`

**Purpose.** build_app gains the injectable tier resolver — Lens 1's SAR module plugs in here; None is a valid production state and fails closed. REPLACES the anchor line.

```
def build_app(
    settings: Settings,
    run_poller: bool = True,
    tier_resolver: Callable[[str], str] | None = None,
) -> FastAPI:
    """`tier_resolver` answers "which tier is this viewer?" — "all" or "self".

    Injected rather than constructed here so the SubjectAccessReview-backed resolver (the
    visibility module) stays independently testable and this app stays buildable without a
    cluster. None is a valid production state and it FAILS CLOSED: with restrictions on
    and no resolver, every reader gets the self view — never the wide one (decision D1).
    """
```

### `local-development/gsd/api.py`

**Anchor.** `@asynccontextmanager`

**Purpose.** The visibility core: trusted_viewer (identity without the resolver), viewer_scope (the fail-closed tier decision — only the exact string "all" widens), require_viewer (the activity-endpoint 403 rule), and the ActivityRecorder-style both-conditions composition with a loud warning for the proxy-off combination the chart refuses to render. Insert BEFORE the anchor line, followed by one blank line.

```
    # ── Per-user visibility ─────────────────────────────────────────────────────────────
    # The scope decision is made in the handler and passed into the store as a bound SQL
    # parameter — the /api/dashboard/activity pattern, generalised. The store never sees
    # request identity; the UI only reflects the `scope` and `viewer` fields each scoped
    # response declares, because a UI-only narrowing is a leak with a cosmetic fix.
    # Endpoint rulings: docs/SPEC_per_user_visibility.md.
    #
    # Both conditions, not either — the ActivityRecorder composition above, for the same
    # reason: the setting is the operator's choice, the proxy flag is whether any identity
    # we see is worth believing. Without the proxy there are no authenticated readers to
    # tier — the app is an open port serving today's wide view to whoever reaches it, and
    # scoping by a header the caller typed would be theatre. The chart refuses to render
    # restrictions-on/proxy-off at template time; this warning covers hand-built
    # deployments that bypass it.
    restrict = settings.view_restrictions_enabled and settings.oauth_proxy_enabled
    if settings.view_restrictions_enabled and not settings.oauth_proxy_enabled:
        log.warning(
            "view restrictions are configured on but the oauth proxy is not enabled, so "
            "there is no trusted identity to scope views to and every reader sees "
            "everything — exactly today's proxy-less behaviour. Enable the oauth proxy to "
            "make the restriction real, or set GSD_ENABLE_VIEW_RESTRICTIONS=false to "
            "record that the wide view is a deliberate choice."
        )

    def trusted_viewer(request: Request) -> str | None:
        """X-Forwarded-User, believed only behind the proxy — the whoami rule.

        Separate from viewer_scope so full-view endpoints can stamp `viewer` on their
        response without consulting the tier resolver they do not need.
        """
        if not settings.oauth_proxy_enabled:
            return None
        return request.headers.get(USER_HEADER) or None

    def viewer_scope(request: Request) -> tuple[str | None, str]:
        """Resolve this request to (viewer, scope). The failure direction IS the control.

        `scope` is "all" only when restrictions are off, or when the tier resolver
        POSITIVELY answers "all" for this viewer. Everything else — no viewer, no
        resolver wired, a resolver error or timeout, an unrecognised answer — lands on
        "self", never on the wide view (requirements §5.4, decision D1).
        """
        viewer = trusted_viewer(request)
        if not restrict:
            return viewer, "all"
        if not viewer or tier_resolver is None:
            return viewer, "self"
        try:
            tier = tier_resolver(viewer)
        except Exception:  # noqa: BLE001
            # Logged with the trace, served as self: an API-server blip degrades the VIEW,
            # never the availability — the reader sees their own data, not an error page.
            log.exception("tier resolution failed for %r; serving the self view", viewer)
            return viewer, "self"
        # Only the exact string "all" widens — the _visibility_setting discipline applied
        # to the resolver's answer, so a buggy resolver cannot widen by returning junk.
        return viewer, ("all" if tier == "all" else "self")

    def require_viewer(viewer: str | None) -> str:
        """Self-scoped data needs a name to scope to; without one it is refused.

        The /api/dashboard/activity rule: when no proxy fronts the app (or the proxy sent
        no identity header), X-Forwarded-User is whatever the caller typed, and honouring
        it would let anyone read anyone by asserting a name.
        """
        if not viewer:
            raise HTTPException(
                status_code=403,
                detail="this data is scoped to the authenticated viewer, and there is no "
                       "authenticated identity to scope it to",
            )
        return viewer
```

### `local-development/gsd/api.py`

**Anchor.** `the clock moved past it.`

**Purpose.** list_groupsyncs stays a bare list — the ruling and the reason it carries no scope field, said where a reader will look. Insert AFTER the anchor line (inside the docstring, before its closing quotes).

```

        FULL VIEW AT BOTH TIERS, by ruling (spec Q3): CR health is governance data about
        objects, and per-CR name, namespace, state and last-sync are already public on
        the unauthenticated /metrics. The payload never varies by tier, which is why this
        stays a bare list with no scope field — there is no narrowing to declare.
```

### `local-development/gsd/api.py`

**Anchor.** `@app.get("/api/clusters/{cluster_id}/groupsyncs/{name}/events")`

**Purpose.** list_events: full view at both tiers, now declaring scope/viewer. Two surgical edits inside the existing handler: (a) add `request: Request,` as the first parameter of def list_events, (b) insert the scope/viewer lines into the returned dict immediately after its `"cluster": cluster_id,` line. The code below is the complete replacement for the handler's signature-plus-return regions; everything between (docstring, rows fetch, truncation) is unchanged — shown here in full so the block can replace the whole handler from the anchor decorator through the end of its `return {...}`.

```
    @app.get("/api/clusters/{cluster_id}/groupsyncs/{name}/events")
    def list_events(
        request: Request,
        cluster_id: str,
        name: str,
        since: str | None = Query(
            default=None,
            description="ISO-8601 UTC instant; return only events observed after it"),
        limit: int = Query(
            default=200, ge=1, le=2000,
            description="Maximum events to return, newest first. `truncated` says whether "
                        "older ones were dropped."),
    ) -> dict:
        """Observed sync events for one GroupSync CR, newest first.

        Accumulated from polling rather than fetched, so the window starts when this
        dashboard did — see `note` in the response.
        """
        require_cluster(cluster_id)
        # limit + 1 to learn whether more exist, then hand back only `limit`. The cheap half
        # of R3 in docs/api-contract.md: it answers "is this all of them?" without a COUNT
        # over a table that grows with every poll, and it is the idiom list_users already
        # uses — one paging shape in the codebase rather than two.
        rows = store.sync_events(cluster_id, name, since, limit + 1)
        truncated = len(rows) > limit
        events = rows[:limit]
        return {
            "cluster": cluster_id,
            # FULL VIEW AT BOTH TIERS, by ruling (spec Q3): a sync timeline names CRs and
            # counts, never a person, and per-CR state is public on /metrics already.
            "scope": "all",
            "viewer": trusted_viewer(request),
            "groupsync": name,
            "count": len(events),
            "limit": limit,
            "truncated": truncated,
            # The timeline is accumulated, not fetched — it only covers the period this
            # dashboard has been running (PLAN §2). Saying so stops an empty list being
            # read as "the operator never synced".
            "note": "accumulated from polling; covers only the period since this dashboard started",
            "events": events,
        }
```

### `local-development/gsd/api.py`

**Anchor.** `@app.get("/api/clusters/{cluster_id}/groups")`

**Purpose.** SELF-SCOPED /groups: an object now (rows under .groups plus scope/viewer/count — the activity contract), the viewer's memberships served by one store call. REPLACES the entire existing handler from the anchor decorator through `return store.groups(cluster_id, state)`.

```
    @app.get("/api/clusters/{cluster_id}/groups")
    def list_groups(
        request: Request,
        cluster_id: str,
        state: str = Query(
            default="all", pattern="^(all|empty|unattributed)$",
            description="`all`; `empty` for groups with zero members, whatever created them; "
                        "`unattributed` for groups no GroupSync CR claims. The two overlap: a "
                        "hand-made group with no members is both."),
    ) -> dict:
        """Synced groups on one cluster, optionally narrowed to a problem state.

        SELF-SCOPED under view restrictions: a plain reader sees only the groups they are
        a member of, because `list groups.user.openshift.io` is a permission they do not
        hold (measured: eight-for-eight `no` for the lab's plain user). An object rather
        than the bare list this used to be, so `scope` and `viewer` ride the response and
        the UI never has to derive the tier — the activity-endpoint contract.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request)
        rows = store.groups(
            cluster_id, state,
            user_name=None if scope == "all" else require_viewer(viewer),
        )
        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "count": len(rows),
            "groups": rows,
        }
```

### `local-development/gsd/api.py`

**Anchor.** `@app.get("/api/clusters/{cluster_id}/groups/{name}")`

**Purpose.** SELF-SCOPED group detail: membership checked BEFORE any existence lookup so a non-member's 403 is constant for real and nonexistent names alike; a member gets the full detail. REPLACES the entire existing handler from the anchor decorator (including @consistent) through the end of its final `return {...}`.

```
    @app.get("/api/clusters/{cluster_id}/groups/{name}")
    @consistent
    def group_detail(request: Request, cluster_id: str, name: str) -> dict:
        """One group: its members, the CR that syncs it, and what it grants.

        A group with history but no current state is reported as DELETED rather than 404 —
        it is still named by every membership-change row that mentions it.

        SELF-SCOPED under view restrictions: only groups the viewer belongs to. The
        member check runs BEFORE any existence lookup, so a non-member's 403 is constant
        for a real group and a nonexistent one alike — answering differently would be a
        per-name existence oracle over the very list the self tier withholds. A member
        sees the full detail: membership is the entitlement, and their group's roster is
        exactly what they can see about themselves in the directory. Deleted groups are
        unreachable at self by the same rule — no membership row, no view — which fails
        closed rather than resurrecting history for an ex-member.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request)
        if scope == "self" and not store.is_group_member(
            cluster_id, name, require_viewer(viewer)
        ):
            raise HTTPException(
                status_code=403,
                detail="this group is outside your view; group detail beyond your own "
                       "memberships needs the wide tier",
            )
        detail = store.group_detail(cluster_id, name)
        if detail is None:
            # A group we have history for but no current state is DELETED, not unknown.
            # It is still reachable from every membership-change row that mentions it, and
            # "this group no longer exists, here is who was in it and when it went" is the
            # answer to that click — 404 strands the reader on a dead end instead.
            history = store.membership_events(cluster_id, group_name=name, limit=100)
            if not history:
                raise HTTPException(status_code=404, detail=f"unknown group {name!r}")
            return {
                "name": name,
                "scope": scope,
                "viewer": viewer,
                "deleted": True,
                "member_count": 0,
                "sync_provider": None,
                "group_synced_at": None,
                "ldap_uid": None,
                "observed_at": None,
                "owner": None,
                "members": [],
                "changes": history,
                "bindings": store.group_bindings(cluster_id, name),
            }
        detail["deleted"] = False
        owner = None
        if detail.get("sync_provider"):
            for cr in store.groupsyncs(cluster_id):
                if detail["sync_provider"] in (cr.get("provider_keys") or []):
                    owner = {"name": cr["name"], "namespace": cr["namespace"],
                             "schedule": cr["schedule"]}
                    break
        return {
            **detail,
            "scope": scope,
            "viewer": viewer,
            "owner": owner,
            "members": store.group_members(cluster_id, name),
            "changes": store.membership_events(cluster_id, group_name=name, limit=100),
            # DIRECT bindings only. Role rules are never fetched or expanded, so this is
            # not an effective-permission calculation and must not be presented as one.
            "bindings": store.group_bindings(cluster_id, name),
        }
```

### `local-development/gsd/api.py`

**Anchor.** `@app.get("/api/clusters/{cluster_id}/users")`

**Purpose.** SELF-SCOPED /users: the viewer's own row or nothing, via the store's user_name privacy-scope parameter. REPLACES the entire existing handler from the anchor decorator through the end of its `return {...}`.

```
    @app.get("/api/clusters/{cluster_id}/users")
    def list_users(
        request: Request,
        cluster_id: str,
        limit: int = Query(
            default=1000, ge=1, le=10000,
            description="Maximum users to return. `truncated` says whether more exist."),
    ) -> dict:
        """Users with a membership, bounded and honest about it.

        This used to return a bare unbounded list — 102,921 bytes at reference scale, and
        it grows with the size of the directory rather than with anything the dashboard
        controls. The response is now an object so `truncated` can be reported: a clipped
        list that looks like a complete one is the failure worth avoiding.

        SELF-SCOPED under view restrictions: a plain reader gets their own row or an
        empty list, because `list users.user.openshift.io` is a permission they do not
        hold — the only self-read OpenShift grants everyone is `get users/~`.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request)
        rows = store.users(
            cluster_id, limit=limit,
            user_name=None if scope == "all" else require_viewer(viewer),
        )
        truncated = len(rows) > limit
        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "count": min(len(rows), limit),
            "truncated": truncated,
            "limit": limit,
            "users": rows[:limit],
        }
```

### `local-development/gsd/api.py`

**Anchor.** `@app.get("/api/clusters/{cluster_id}/users/{name}")`

**Purpose.** SELF-SCOPED user profile: own name or a 403 issued BEFORE any store lookup, byte-identical for colleagues and nonexistent names. REPLACES the entire existing handler from the anchor decorator (including @consistent) through the end of its `return {...}`.

```
    @app.get("/api/clusters/{cluster_id}/users/{name}")
    @consistent
    def user_detail(request: Request, cluster_id: str, name: str) -> dict:
        """Reverse lookup: every group this user is in.

        The cluster cannot answer this directly — it means scanning every Group object — yet
        it is the question behind most "why does this person have access?" investigations.

        SELF-SCOPED under view restrictions: their own profile only, refused BEFORE any
        store lookup so the 403 for a colleague and for a name that does not exist are
        byte-identical — otherwise this endpoint is a username oracle.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request)
        if scope == "self" and name != require_viewer(viewer):
            raise HTTPException(
                status_code=403,
                detail="user profiles other than your own need the wide tier",
            )
        groups = store.user_groups(cluster_id, name)
        changes = store.membership_events(cluster_id, user_name=name, limit=100)
        # A user with no CURRENT groups is not unknown — they may have just been removed
        # from the last one, and "they are in nothing now" is the answer to the question,
        # not an error. 404 only when we have never seen them at all.
        if not groups and not changes:
            raise HTTPException(status_code=404, detail=f"unknown user {name!r}")
        return {
            "user": name,
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            # None whenever OpenShift has no name for them — no User object because they have
            # never logged in, or a User with fullName unset because their identity provider
            # supplies no name attribute. A separate store call rather than a join because this
            # handler is @consistent and already makes several inside one snapshot.
            "full_name": store.user_full_name(cluster_id, name),
            "groups": groups,
            "changes": changes,
            # Reachable through their group memberships. Each row carries via_group, so
            # "why do they have this?" is answerable without a second lookup.
            "bindings": store.user_bindings(cluster_id, name),
        }
```

### `local-development/gsd/api.py`

**Anchor.** `@app.get("/api/clusters/{cluster_id}/logins")`

**Purpose.** SELF-SCOPED /logins — the most sensitive endpoint: byte-exact own rows (the measured LATEEF.O case-variant stays wide-tier-only), personnel aggregates withheld as None (never zeros, never recomputed), total switched to the viewer's own indexed count, window metadata kept at both tiers. REPLACES the entire existing handler from the anchor decorator (including @consistent) through the end of its `return {...}`.

```
    @app.get("/api/clusters/{cluster_id}/logins")
    @consistent
    def list_logins(
        request: Request,
        cluster_id: str,
        outcome: str | None = Query(
            default=None,
            description="Return only attempts with this outcome. The vocabulary is the parser's: "
                        "success, bad_password, rejected (not found OR not permitted — the log "
                        "cannot tell those apart), password_expired, must_change_password, "
                        "account_locked, account_disabled, account_expired, logon_not_permitted, "
                        "and failed (the provider gave no reason — the normal shape on an "
                        "HTPasswd provider, which logs a verdict and nothing else)."),
        user: str | None = Query(
            default=None,
            description="Only attempts for this exact username — the login that was TYPED, which "
                        "may match no User object and no group member. That mismatch is a finding, "
                        "not an error."),
        limit: int = Query(
            default=200, ge=1, le=2000,
            description="Maximum attempts returned, newest first. `truncated` says whether older "
                        "ones were dropped; `total` and `summary` always describe the whole "
                        "retained record, never this page."),
    ) -> dict:
        """Login attempts against this cluster's oauth-server: who, when, and why it failed.

        THE RECORD IS A WINDOW, and both of its edges are carried as data rather than implied.
        `capture_started_at` is when watching began and is stable; `retained_since` is the oldest
        attempt still kept and moves under retention. Nothing before capture began exists to fetch —
        the log dies with its pod — so an empty list is a statement about the window and never proof
        that nobody logged in. The UI has to say that, which is why it is here and not a footnote.

        EVERY username is recorded, successful or not, member or not. `known_user: false` marks an
        account in NO synced group, which is the most valuable row this produces; `has_history: true`
        separates "access was removed and they are still trying" from "nobody ever governed this
        name". `ungoverned` lists those accounts separately so a paged chronology cannot bury them.
        """
        require_cluster(cluster_id)
        # THE MOST SENSITIVE ENDPOINT IN THE APPLICATION (requirements §2): it names people
        # and states that their password was wrong or their account locked. SELF-SCOPED
        # under view restrictions, and byte-exact on purpose: the capture stores the name
        # AS TYPED (measured live: rows for both `lateef.o` and `LATEEF.O`), while the
        # viewer arrives in the directory form, so a case-variant attempt stays visible to
        # the wide tier only. A COLLATE NOCASE match was measured to degrade the query to
        # the cluster-wide index scan AND would cross-leak between two OpenShift Users
        # differing only by case — User names are case-sensitive.
        viewer, scope = viewer_scope(request)
        if scope == "self":
            me = require_viewer(viewer)
            if user is not None and user != me:
                raise HTTPException(
                    status_code=403,
                    detail="login attempts other than your own need the wide tier",
                )
            user = me
        # Which provider NAMES are HTPasswd is deployment configuration — the log carries only the
        # name. Passed to the ungoverned queries so their rows and their count share ONE predicate in
        # the store, and applied per row below for the break_glass label.
        htpasswd = tuple(settings.login_capture_htpasswd_providers)
        status = store.login_capture_status(cluster_id)
        # Computed at BOTH tiers: the self view keeps the window edges (capture_started_at,
        # retained_since — facts about the record, not about a person) and withholds the
        # personnel aggregates below.
        summary = store.login_event_summary(cluster_id, exclude_providers=htpasswd)
        ungoverned = (
            store.ungoverned_login_users(cluster_id, exclude_providers=htpasswd, limit=50)
            if scope == "all" else None
        )
        # limit + 1 to learn whether more exist — the list_users idiom. `summary` carries the exact
        # whole-record numbers, so no headline figure is ever computed from this page.
        rows = store.login_events(cluster_id, user_name=user, outcome=outcome, limit=limit + 1)
        truncated = len(rows) > limit
        attempts = rows[:limit]

        by_outcome = summary["by_outcome"]
        successes = by_outcome.get(loginlog.OUTCOME_SUCCESS, 0)
        # Gate membership for the names on this page, in ONE batch lookup rather than a call per row.
        # An empty dict means no gate is known, and the rows then carry None — "unknown", which is a
        # different statement from False and the reason a `rejected` row can only sometimes be
        # explained. With a gate known, `in_access_group: false` on a person who IS in a synced group
        # turns "not found OR not permitted" into "a real person, not gated".
        gate = store.is_in_access_group(cluster_id, [r["user_name"] for r in attempts])
        for row in attempts:
            # Normalised here so the UI never re-derives a flag from raw fields, and so the wire
            # carries real booleans whatever 0/1 shape SQLite returned.
            row["break_glass"] = row.get("provider") in htpasswd
            row["known_user"] = bool(row.get("known_user"))
            row["has_history"] = bool(row.get("has_history"))
            # None, not False, when no gate is known. The UI must be able to say "we cannot tell"
            # rather than asserting a non-membership it has no basis for.
            row["in_access_group"] = gate.get(row["user_name"])
            row["refusal_reason"] = _refusal_reason(row)
        for row in ungoverned or []:
            row["has_history"] = bool(row.get("has_history"))

        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "enabled": settings.login_capture_enabled,
            "note": "read from the oauth-server log at Debug verbosity; covers only the period "
                    "since capture began — earlier logins were never recorded and cannot be "
                    "fetched, and rows older than the configured retention age out",
            # Set once by the capture loop's first successful read. Falls back to the oldest retained
            # attempt for the one-cycle window after a crash before that row exists — an honest floor
            # rather than null, which the UI would have to render as "unknown".
            "capture_started_at": (status or {}).get("started_at") or summary["first_at"],
            "last_read_at": (status or {}).get("last_read_at"),
            # How often `last_read_at` is EXPECTED to advance — capture runs on the poll thread, so
            # the poll interval is its cadence. Sent because the browser is the only place that can
            # decide whether a read is overdue and the only place that knows what a reader is
            # looking at, but it has no way to learn the cadence: a hardcoded threshold in the page
            # would call a 900s poll "stalled" every single cycle.
            "read_interval_seconds": settings.poll_interval_seconds,
            "retained_since": summary["first_at"],
            # At self, the whole-record count OF THE VIEWER (one indexed scalar), never the
            # cluster-wide total — a number computed over rows the response withholds would
            # be the count-versus-page defect reintroduced deliberately.
            "total": summary["total"] if scope == "all" else
                     store.count_login_events(cluster_id, user),
            "limit": limit,
            "truncated": truncated,
            # The personnel aggregates are WITHHELD at self, as None rather than zeros:
            # failure counts, distinct users and the ungoverned list are personnel data
            # even without names (the gsd_dashboard_active_users removal is the precedent),
            # and a fabricated 0 would read as "nothing happened". Never recomputed over
            # the visible subset either — "distinct users among yourself" is 1 by
            # construction, a number whose label would lie.
            "summary": {
                "distinct_users": summary["distinct_users"],
                "successes": successes,
                "failures": summary["total"] - successes,
                "by_outcome": by_outcome,
                "ungoverned_users": summary["ungoverned_users"],
                "first_at": summary["first_at"],
                "last_at": summary["last_at"],
            } if scope == "all" else None,
            # One row per account in no synced group, most recent first. Bounded at 50 and honest
            # about it: summary.ungoverned_users beside it is the whole-set count, from the SAME
            # store predicate, so the two cannot disagree.
            "ungoverned": ungoverned,
            "attempts": attempts,
        }
```

### `local-development/gsd/api.py`

**Anchor.** `@app.get("/api/clusters/{cluster_id}/cluster-access")`

**Purpose.** SELF-SCOPED /cluster-access: the viewer's own gate status only — DN, source, group name, both people-lists and the summary withheld as None; in_access_group is None when no synced gate exists (unknown is not non-member). REPLACES the entire existing handler from the anchor decorator (including @consistent) through the end of its final `return {...}`.

```
    @app.get("/api/clusters/{cluster_id}/cluster-access")
    @consistent
    def cluster_access(
        request: Request,
        cluster_id: str,
        limit: int = Query(
            default=200, ge=1, le=2000,
            description="Maximum rows per list. `summary` always describes the whole cluster."),
    ) -> dict:
        """Who can actually LOG IN, against who holds access — two different questions.

        Every other view in this dashboard starts from RBAC and stops there, so a role granted to
        somebody who cannot authenticate is invisible: access that can never be used. On the reference
        cluster 10 people held access through synced groups and 7 were in the gate group, so 3 held
        access they could not exercise.

        THE ANSWER DEPENDS ON A PREREQUISITE THIS DASHBOARD CANNOT MEET ITSELF. The gate group has to
        be synced into OpenShift by the group-sync-operator before there is any membership to compare
        against, and `synced: false` says the DN is known and the Group is not there. That is not zero
        findings — it is no data, and the two must never look alike.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request)
        access = store.cluster_access_group(cluster_id)
        if scope == "self":
            # THE VIEWER'S OWN GATE STATUS and nothing about anyone else. The DN, the
            # discovery source and both people-lists are withheld — the lists are other
            # people's findings, and the DN maps the directory. Withheld values are None,
            # never fabricated zeros: a summary of zeros would read as "no findings" to a
            # reader who cannot know it was narrowed. `in_access_group` is None when no
            # synced gate group exists to compare against — "we cannot tell" is a
            # different statement from "not a member", same contract as the logins rows.
            me = require_viewer(viewer)
            gated = bool(access)
            synced = bool(access and access["group_name"])
            membership = store.is_in_access_group(cluster_id, [me])
            return {
                "cluster": cluster_id,
                "scope": "self",
                "viewer": viewer,
                "gated": gated,
                "dn": None,
                "source": None,
                "group_name": None,
                "synced": synced,
                "in_access_group": membership.get(me) if synced else None,
                "note": ("membership of the login-gate group is required to authenticate; "
                         "in_access_group is your own status against it"
                         if synced else
                         "no synced login-gate group is known on this cluster, so your "
                         "gate status cannot be determined"),
                "summary": None,
                "access_without_login": None,
                "login_without_access": None,
                "limit": limit,
                "truncated": False,
            }
        if not access:
            # NO GATE, which is itself a finding rather than an absence: with no membership clause in
            # any identity provider's filter, every account in the search base can sign in.
            return {
                "cluster": cluster_id,
                "scope": scope,
                "viewer": viewer,
                "gated": False,
                "dn": None,
                "source": None,
                "group_name": None,
                "synced": False,
                "note": "no login gate is known. Either no identity provider's filter carries a "
                        "memberOf/isMemberOf clause — in which case any account in its search base "
                        "can sign in — or the OAuth CR could not be read. Set clusterAccess.group to "
                        "state the group explicitly.",
                "summary": {"gated_members": 0, "with_access": 0,
                            "access_without_login": 0, "login_without_access": 0},
                "access_without_login": [],
                "login_without_access": [],
                "limit": limit,
                "truncated": False,
            }

        synced = bool(access["group_name"])
        # limit + 1 to learn whether more exist — the list_users idiom used throughout.
        without_login = store.access_without_login(cluster_id, limit=limit + 1)
        truncated = len(without_login) > limit
        for row in without_login:
            row["has_tried"] = bool(row.get("has_tried"))
            # GROUP_CONCAT hands back one comma-joined string; the wire carries a list, so the UI
            # never splits a delimited field. A group name cannot contain a comma (RFC 1123 label
            # rules apply to a Group's metadata.name), so the split is safe here and would not be on
            # an LDAP DN — which is exactly why user_name is never packed this way.
            row["groups"] = [g for g in (row.get("groups") or "").split(",") if g]
        gated_only = store.login_without_access(cluster_id, limit=limit)
        for row in gated_only:
            row["has_tried"] = bool(row.get("has_tried"))

        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "gated": True,
            "dn": access["dn"],
            # Which of the two produced it. An operator asking "why is this the wrong group?" needs to
            # know whether to change values.yaml or the identity provider.
            "source": access["source"],
            "group_name": access["group_name"],
            "synced": synced,
            "note": ("membership of this group is required to authenticate, so somebody outside it "
                     "cannot use any access they hold")
                    if synced else
                    ("the gate group's DN is known but no synced Group matches it, so there is no "
                     "membership to compare against. The group-sync-operator has to pull it — see "
                     "docs/examples/clusteraccess-groupsync.yaml. Note a gate group is often "
                     "objectClass groupOfUniqueNames with `uniqueMember`, unlike RBAC groups: "
                     "copying an existing CR's rfc2307 block verbatim syncs it with zero members."),
            "summary": store.cluster_access_summary(cluster_id),
            "access_without_login": without_login[:limit],
            "login_without_access": gated_only,
            "limit": limit,
            "truncated": truncated,
        }
```

### `local-development/gsd/api.py`

**Anchor.** `"note": "direct bindings only; role rules are not evaluated",`

**Purpose.** binding_findings stays FULL VIEW at both tiers (the arbiter's ruling: governance data about objects; subjects are Group names, counts already public on /metrics) and declares scope/viewer. Insert the code BEFORE the anchor line, inside the returned dict, right after its `"cluster": cluster_id,` line. Additionally add `request: Request,` as the first parameter of `def binding_findings(` (directly below the `@app.get("/api/clusters/{cluster_id}/bindings/findings")` decorator and its @consistent line, before `cluster_id: str,`).

```
            # FULL VIEW AT BOTH TIERS, by ruling (spec Q3): these rows classify BINDINGS —
            # governance data about objects, whose subjects are Group names, not people —
            # and their counts are already public on the unauthenticated /metrics
            # (gsd_bindings_total{finding=...}, measured with a credential-less curl).
            # The person-named analogue, bindings that name a User directly, lives on
            # /user-bindings and is self-scoped there. `scope` declares what this payload
            # covers, which is always everything.
            "scope": "all",
            "viewer": trusted_viewer(request),
```

### `local-development/gsd/api.py`

**Anchor.** `require_cluster(cluster_id)
        total = store.count_direct_user_bindings(`

**Purpose.** SELF-SCOPED /user-bindings: rows naming the viewer only (byte-exact against the subject as typed), rollup and platform count withheld as None, total coherent with the visible set. REPLACES the block in the direct_user_bindings handler from `require_cluster(cluster_id)` through the end of its `return {...}` (the anchor is the first two lines of that block; it is unique because this is the only handler whose require_cluster is immediately followed by count_direct_user_bindings). Additionally add `request: Request,` as the first parameter of `def direct_user_bindings(`, before `cluster_id: str,`.

```
        require_cluster(cluster_id)
        # SELF-SCOPED under view restrictions: only bindings that name the viewer — their
        # own grants (requirements §2). Byte-exact against the subject name as the
        # administrator typed it, so a binding naming `jdoe` is invisible to `john.doe`:
        # fail-closed, because nothing proves those are one person. The rollup and the
        # platform count aggregate OTHER people's grants, so at self they are withheld as
        # None — never recomputed over one person (a one-row "worklist" would relabel the
        # migration effort as the viewer's) and never fabricated zeros.
        viewer, scope = viewer_scope(request)
        me = None if scope == "all" else require_viewer(viewer)
        total = store.count_direct_user_bindings(
            cluster_id, include_platform=include_platform, namespace=namespace,
            user_name=me)
        rows = store.direct_user_bindings(
            cluster_id, include_platform=include_platform, namespace=namespace,
            limit=limit, offset=offset, user_name=me)
        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "note": "direct user grants; migrate these to LDAP-managed groups",
            "by_namespace":
                store.user_bindings_by_namespace(cluster_id) if scope == "all" else None,
            "excluded_platform":
                store.platform_user_binding_count(cluster_id) if scope == "all" else None,
            "namespace": namespace,
            "total": total,
            "limit": limit,
            "offset": offset,
            "truncated": offset + len(rows) < total,
            "bindings": rows,
        }
```

### `local-development/gsd/api.py`

**Anchor.** `@app.get("/api/clusters/{cluster_id}/operator-configs")`

**Purpose.** operator-configs stays FULL VIEW, declaring scope/viewer. REPLACES the entire existing handler from the anchor decorator through its return statement.

```
    @app.get("/api/clusters/{cluster_id}/operator-configs")
    def operator_configs(request: Request, cluster_id: str) -> dict:
        """Health of the namespace-configuration-operator's CRs on this cluster.

        `present: false` means the CRDs do not exist there — auto-detected, and a
        different truth from "installed with zero CRs". Reconcile conditions only, by
        design: the templates are the operator's business.

        FULL VIEW AT BOTH TIERS, by ruling (spec Q3): operator configuration is
        governance data about objects, names no person, and its present/failing summary
        already rides the overview cards.
        """
        require_cluster(cluster_id)
        return {
            "cluster": cluster_id,
            "scope": "all",
            "viewer": trusted_viewer(request),
            **store.operator_configs(cluster_id),
        }
```

### `local-development/gsd/api.py`

**Anchor.** `@app.get("/api/clusters/{cluster_id}/membership-changes")`

**Purpose.** SELF-SCOPED /membership-changes: the viewer's own rows via the store's existing user_name privacy-scope parameter (membership_event_by_user, plan measured). REPLACES the entire existing handler from the anchor decorator through the end of its `return {...}`.

```
    @app.get("/api/clusters/{cluster_id}/membership-changes")
    def membership_changes(
        request: Request,
        cluster_id: str,
        limit: int = Query(
            default=100, ge=1, le=1000,
            description="Maximum changes to return, newest first. `truncated` says whether "
                        "older ones were dropped."),
    ) -> dict:
        """Who joined or left which group, newest first.

        The only record of a departure: the cluster shows current membership, so once
        somebody is removed nothing on it says they were ever there. Accumulated from
        polling, so the window starts when this dashboard did.

        SELF-SCOPED under view restrictions: only the changes affecting the viewer
        (requirements §2) — the rows are person-by-person history, and the store already
        takes user_name as the privacy scope (membership_event_by_user serves it).
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request)
        # limit + 1, as in list_events — see docs/api-contract.md R3. This log previously
        # cut off at 100 with nothing saying so, which on an audit trail reads as "no
        # further changes" rather than "not shown".
        rows = store.membership_events(
            cluster_id,
            user_name=None if scope == "all" else require_viewer(viewer),
            limit=limit + 1,
        )
        truncated = len(rows) > limit
        events = rows[:limit]
        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "count": len(events),
            "limit": limit,
            "truncated": truncated,
            "note": "accumulated from polling; covers only the period since this dashboard started",
            "changes": events,
        }
```

### `local-development/gsd/api.py`

**Anchor.** `@app.get("/api/alerts")`

**Purpose.** SELF-filtered /api/alerts, now an object carrying scope/viewer/count. Includes a load-bearing rename inside the pre-existing dangling loop: its local was named `scope` and would have rebound the tier variable, silently disabling the self filter on any cluster with a dangling finding (found in verification; test_dangling_binding_alert_does_not_break_the_self_filter pins it). REPLACES the entire existing handler from the anchor decorator (including @consistent) through `return alerts`.

```
    @app.get("/api/alerts")
    @consistent
    def list_alerts(request: Request) -> dict:
        """Everything currently worth a human's attention, across all clusters.

        Ordered by severity. Derived per request from the same stored observations the rest
        of the API serves, so an alert here always has a page behind it.

        THAT INVARIANT IS WHAT SCOPES THIS FEED. Under view restrictions the self tier
        receives only the kinds in SELF_ALERT_KINDS — the ones whose backing pages it
        sees in full — filtered by kind rather than recomputed, and the response says so:
        an alert feed that quietly dropped rows would train readers that green means
        healthy when it means hidden. An object rather than the bare list this used to
        be, so `scope` and `viewer` ride the wire (the activity contract).
        """
        viewer, scope = viewer_scope(request)
        now = datetime.now(UTC)
        alerts: list[dict] = []
        for row in store.clusters():
            cluster_id = row["id"]
            if row["status"] and row["status"] != "ok":
                alerts.append(
                    {
                        "cluster": cluster_id,
                        "kind": row["status"],
                        "subject": cluster_id,
                        "detail": row["message"] or "cluster poll failed",
                        "severity": "critical",
                    }
                )
                # A degraded cluster's cached rows are stale by definition; computing
                # group-level alerts from them would report yesterday's state as today's.
                continue
            computed = st.compute_alerts(
                cluster=cluster_id,
                groupsyncs=store.groupsyncs(cluster_id),
                operator_configs=store.operator_configs(cluster_id)["configs"],
                user_bindings=store.direct_user_bindings(cluster_id),
                groups=store.groups(cluster_id, "all"),
                groupsync_present=store.groupsync_present(cluster_id),
                now=now,
                grace=grace,
            )
            alerts.extend(a.as_dict() for a in computed)

            # Only the `dangling` tier alerts. `built_in` is normal, and `unresolved`
            # cannot be distinguished from a group that simply has not synced yet, so
            # alerting on either would produce noise that trains people to ignore this.
            for row in store.binding_findings(cluster_id):
                if row["finding"] != "dangling":
                    continue
                # `where`, not `scope`: this handler's `scope` is the visibility tier, and
                # a loop-local rebinding here once disabled the self filter below — the
                # feed failed OPEN on exactly the clusters that had a dangling finding.
                where = (
                    f"namespace {row['binding_namespace']}"
                    if row["binding_namespace"]
                    else "cluster-wide"
                )
                alerts.append(
                    {
                        "cluster": cluster_id,
                        "kind": "dangling_binding",
                        "subject": row["binding_name"],
                        "detail": (
                            f"{row['binding_kind']} grants {row['role_name']} {where} to "
                            f"group {row['group_name']!r}, which the operator used to "
                            f"manage and no longer exists — this binding now grants nobody"
                        ),
                        "severity": "critical",
                    }
                )
        if scope == "self":
            alerts = [a for a in alerts if a["kind"] in SELF_ALERT_KINDS]
        severity_rank = {"critical": 0, "warning": 1}
        alerts.sort(key=lambda a: (severity_rank.get(a["severity"], 9), a["cluster"], a["kind"]))
        return {
            "scope": scope,
            "viewer": viewer,
            "count": len(alerts),
            "alerts": alerts,
        }
```

### `local-development/gsd/store.py`

**Anchor.** `def groups(self, cluster_id: str, state: str = "all") -> list[dict]:`

**Purpose.** groups() gains the user_name privacy scope with a shared state predicate (one method, one handler call site — required by the R5 snapshot contract test), plus is_group_member for the constant-403 gate. REPLACES the entire existing groups() method from the anchor line through its `return self._rows(sql, params)` (the block ending just before `def group_counts`). Plans measured on the live database: scoped shape = group_state PK autoindex + group_member PK covering index; membership probe = one covering-index hit.

```
    @staticmethod
    def _group_state_predicate(state: str, alias: str = "") -> str:
        """The `state` filter, written once for both shapes of groups().

        Two copies of this predicate would drift the way the count-versus-list defects did,
        and the `empty` reading below has already been re-litigated once — it must not fork.
        """
        prefix = f"{alias}." if alias else ""
        if state == "empty":
            # EVERY group with no members, whatever created it. This was scoped to
            # `sync_provider IS NOT NULL` on PLAN §7's reading of EMPTY as "synced, then lost
            # its members" — an LDAP-side fault. That reading made the filter USELESS on the
            # cluster that most needs it: with no group-sync-operator installed, every group is
            # unattributed, so `empty` matched nothing however many groups had zero members.
            #
            # `empty` and `unattributed` therefore OVERLAP now, and that is intended: they are
            # two questions, not a partition. "Which groups grant nobody?" and "which groups is
            # no CR managing?" have different answers and a group can be both. Nothing sums
            # them — checked across store, api, metrics and the UI before the change.
            return f" AND {prefix}member_count = 0"
        if state == "unattributed":
            return f" AND {prefix}sync_provider IS NULL"
        if state != "all":
            raise ValueError(f"unknown group state filter {state!r}")
        return ""

    def groups(
        self, cluster_id: str, state: str = "all", user_name: str | None = None
    ) -> list[dict]:
        """Current groups, optionally narrowed to the ones this user is a member of.

        `user_name` is the privacy scope, not a convenience filter — the API passes the
        proxy-authenticated viewer's own name when view restrictions are on, the same
        contract user_activity() documents. One method rather than a scoped sibling so a
        handler has exactly one call site and the state predicate cannot fork.

        Matching is byte-exact on purpose. X-Forwarded-User and the Group objects' member
        names carry the same directory form (measured live: `lateef.o` in both), and a
        case-insensitive match would defeat the group_member index AND cross-leak between
        two OpenShift Users differing only by case — User names are case-sensitive.

        Plan for the scoped shape, measured on the live database: group_state by its PK
        autoindex, group_member by its PK covering index — no new index needed.
        """
        if user_name:
            sql = ("""SELECT g.name, g.member_count, g.sync_provider, g.group_synced_at,
                            g.ldap_uid, g.observed_at
                       FROM group_state g
                       JOIN group_member m
                         ON m.cluster_id = g.cluster_id AND m.group_name = g.name
                      WHERE g.cluster_id=? AND m.user_name=?"""
                   + self._group_state_predicate(state, alias="g") + " ORDER BY g.name")
            return self._rows(sql, [cluster_id, user_name])
        sql = ("""SELECT name, member_count, sync_provider, group_synced_at, ldap_uid,
                        observed_at
                   FROM group_state WHERE cluster_id=?"""
               + self._group_state_predicate(state) + " ORDER BY name")
        return self._rows(sql, [cluster_id])

    def is_group_member(self, cluster_id: str, group_name: str, user_name: str) -> bool:
        """Whether this user is currently a member of this group — the self-tier gate.

        One primary-key probe (covering index, measured). The API asks this BEFORE any
        existence lookup so a non-member's 403 is constant for a real group and a
        nonexistent one alike — a per-name existence oracle would leak the group list
        the self tier exists to withhold.
        """
        rows = self._rows(
            "SELECT 1 AS yes FROM group_member WHERE cluster_id=? AND group_name=? AND user_name=?",
            (cluster_id, group_name, user_name),
        )
        return bool(rows)
```

### `local-development/gsd/store.py`

**Anchor.** `def users(self, cluster_id: str, limit: int = 1000) -> list[dict]:`

**Purpose.** users() gains the user_name privacy scope (group_member_by_user, plan measured). REPLACES the entire existing users() method from the anchor line through its closing `)` before the `# -- RBAC bindings` section comment.

```
    def users(
        self, cluster_id: str, limit: int = 1000, user_name: str | None = None
    ) -> list[dict]:
        """Every user with a membership. BOUNDED.

        Unbounded, this returned one row per distinct user across every group: 1,240 rows
        and 102,921 bytes on a reference-shaped cluster with 62 groups, and it grows with
        the DIRECTORY rather than with anything the dashboard controls. A real corporate
        LDAP makes that a response big enough to hurt the browser and the pod.

        `limit + 1` is fetched deliberately: the caller compares the length against the
        limit to know it truncated, without a second COUNT query. A silently truncated
        list is worse than a large one — the reader cannot tell a short directory from a
        clipped answer.

        `user_name` is the privacy scope — the user_activity() contract. Byte-exact,
        served by group_member_by_user (plan measured on the live database).
        """
        sql = """SELECT user_name, COUNT(*) AS group_count, MIN(first_seen_at) AS first_seen_at
                     FROM group_member WHERE cluster_id=?"""
        params: list = [cluster_id]
        if user_name:
            sql += " AND user_name=?"
            params.append(user_name)
        sql += " GROUP BY user_name ORDER BY user_name LIMIT ?"
        params.append(limit + 1)
        return self._rows(sql, params)
```

### `local-development/gsd/store.py`

**Anchor.** `# ── The login gate ────────────────────────────────────────────────────────────────────────────`

**Purpose.** count_login_events: the viewer's whole-record attempt count for the self tier's `total` (login_event_by_user covering index, plan measured). Insert BEFORE the anchor section-header line, followed by one blank line.

```
    def count_login_events(self, cluster_id: str, user_name: str) -> int:
        """This user's whole-record attempt count, for the self tier's `total`.

        The self-scoped logins page must not inherit the cluster-wide total — a number
        computed over rows the viewer cannot see — and must not count its own page (the
        "showing 50 of 30" defect class). One scalar over login_event_by_user, a covering
        index (plan measured on the live database).
        """
        rows = self._rows(
            "SELECT COUNT(*) AS n FROM login_event WHERE cluster_id=? AND user_name=?",
            (cluster_id, user_name),
        )
        return rows[0]["n"] if rows else 0
```

### `local-development/gsd/store.py`

**Anchor.** `def _direct_user_binding_where(`

**Purpose.** The direct-user-binding predicate gains the user_name privacy scope, threaded through both the rows and the count so they cannot disagree. REPLACES the three methods _direct_user_binding_where, direct_user_bindings and count_direct_user_bindings — from the anchor line through count_direct_user_bindings' `return rows[0]["n"] if rows else 0` (the block ending just before `def platform_user_binding_count`).

```
    def _direct_user_binding_where(
        self, cluster_id: str, include_platform: bool, namespace: str | None,
        user_name: str | None = None,
    ) -> tuple[str, list]:
        """The WHERE shared by the row query and its COUNT, built once.

        Built once on purpose: a count computed from a different predicate than the rows
        it describes is how "showing 50 of 30" reaches a page, and the two drifting apart
        during a later edit is the likeliest way for that to happen.

        `user_name` is the privacy scope (the user_activity() contract): the self tier
        sees only bindings that name the viewer. Byte-exact — a direct binding names the
        subject in whatever form the administrator typed, so a binding naming `jdoe`
        stays invisible to `john.doe`, which is fail-closed and correct: the dashboard
        cannot prove those are the same person. Bounded scan of the cluster's slice via
        user_binding_by_namespace (45 rows at reference scale, plan measured); no
        dedicated index until a real cluster shows it needed.
        """
        sql, params = " WHERE cluster_id=?", [cluster_id]
        if not include_platform:
            sql += " AND is_platform=0"
        if namespace is not None:
            sql += " AND binding_namespace=?"
            params.append("" if namespace == self.CLUSTER_SCOPE else namespace)
        if user_name:
            sql += " AND user_name=?"
            params.append(user_name)
        return sql, params

    def direct_user_bindings(
        self,
        cluster_id: str,
        include_platform: bool = False,
        namespace: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        user_name: str | None = None,
    ) -> list[dict]:
        """Every binding naming a User subject, worst-first by privilege then namespace.

        NOT to be confused with `user_bindings(cluster_id, user_name)` above, which answers
        the opposite question: what a person reaches THROUGH their group memberships. This
        one is the governance violation — a grant that names the person directly. The
        original name for this collided with that method and silently overrode it, which
        broke two reverse-lookup tests; the names now say which question each answers.

        `namespace` and `limit` exist because this was previously unbounded at every layer:
        the store returned every row, the API returned every row, and the page rendered
        every row. On a cluster with thousands of direct grants that is a payload and a DOM
        nobody asked for, to show a list nobody can read. Pair with
        `count_direct_user_bindings` so the caller can say what it left out — a silently
        truncated audit list is worse than a slow one.
        """
        where, params = self._direct_user_binding_where(
            cluster_id, include_platform, namespace, user_name)
        sql = ("""SELECT binding_kind, binding_namespace, binding_name, role_kind,
                         role_name, user_name, is_platform
                    FROM user_binding""" + where +
               # cluster-admin first, then cluster-scoped, then namespaced: the order
               # somebody migrating would work in. Ordering is applied BEFORE the limit, so
               # a truncated page is the worst N rather than an arbitrary N.
               """ ORDER BY CASE WHEN role_name='cluster-admin' THEN 0 ELSE 1 END,
                            CASE WHEN binding_namespace='' THEN 0 ELSE 1 END,
                            binding_namespace, user_name""")
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params += [limit, offset]
        return self._rows(sql, tuple(params))

    def count_direct_user_bindings(
        self, cluster_id: str, include_platform: bool = False,
        namespace: str | None = None, user_name: str | None = None,
    ) -> int:
        """How many rows `direct_user_bindings` would return before its limit."""
        where, params = self._direct_user_binding_where(
            cluster_id, include_platform, namespace, user_name)
        rows = self._rows(
            "SELECT COUNT(*) AS n FROM user_binding" + where, tuple(params))
        return rows[0]["n"] if rows else 0
```

### `local-development/gsd/storage.py`

**Anchor.** `def groups(self, cluster_id: str, state: str = "all") -> list[dict]: ...`

**Purpose.** The storage contract declares the new/changed group reads (test_storage_seam enforces protocol/implementation parity — verified failing without this). REPLACES the anchor line.

```
    # The self-tier predicates (docs/SPEC_per_user_visibility.md). Every `user_name`
    # argument on a read below is the PRIVACY SCOPE, not a convenience filter — handlers
    # pass the proxy-authenticated viewer, and the backend must filter in its query so a
    # row limit can never silently starve the viewer's own rows.
    def groups(
        self, cluster_id: str, state: str = "all", user_name: str | None = None
    ) -> list[dict]: ...
    def is_group_member(
        self, cluster_id: str, group_name: str, user_name: str
    ) -> bool: ...
```

### `local-development/gsd/storage.py`

**Anchor.** `def users(self, cluster_id: str, limit: int = 1000) -> list[dict]: ...`

**Purpose.** Protocol: users() gains the privacy-scope parameter. REPLACES the anchor line.

```
    def users(
        self, cluster_id: str, limit: int = 1000, user_name: str | None = None
    ) -> list[dict]: ...
```

### `local-development/gsd/storage.py`

**Anchor.** `def direct_user_bindings(`

**Purpose.** Protocol: direct_user_bindings and count_direct_user_bindings gain the privacy-scope parameter. REPLACES both declarations — from the anchor line through the `) -> int: ...` that closes count_direct_user_bindings.

```
    def direct_user_bindings(
        self,
        cluster_id: str,
        include_platform: bool = False,
        namespace: str | None = None,
        limit: int | None = None,
        offset: int = 0,
        user_name: str | None = None,
    ) -> list[dict]: ...
    def count_direct_user_bindings(
        self,
        cluster_id: str,
        include_platform: bool = False,
        namespace: str | None = None,
        user_name: str | None = None,
    ) -> int: ...
```

### `local-development/gsd/storage.py`

**Anchor.** `def prune_login_events(self, cluster_id: str, before_at: str, max_rows: int = 5000) -> int: ...`

**Purpose.** Protocol: declare count_login_events. Insert BEFORE the anchor line.

```
    def count_login_events(self, cluster_id: str, user_name: str) -> int: ...
```

### `local-development/gsd/static/index.html`

**Anchor.** `data.alerts = await get("/api/alerts");`

**Purpose.** Minimal unwrap for the alerts endpoint's new object shape so the page keeps working; the scope banner rendering belongs to the UI lens, which reads data.alertsScope. REPLACES the anchor line.

```
    // The alerts endpoint is an object now — the rows plus the `scope`/`viewer` the API
    // decided, so the page can say a narrowed feed is narrowed instead of guessing.
    const alertsPayload = await get("/api/alerts");
    data.alerts = alertsPayload.alerts;
    data.alertsScope = alertsPayload.scope;
```

### `local-development/gsd/static/index.html`

**Anchor.** `data.groups = got;`

**Purpose.** Minimal unwrap for the groups endpoint's new object shape; the UI lens renders banners from data.groupsScope/data.groupsViewer. REPLACES the anchor line.

```
          // An object now — rows plus the `scope`/`viewer` the API decided, so the
          // narrowed state can be rendered from the response rather than derived.
          data.groups = got.groups;
          data.groupsScope = got.scope;
          data.groupsViewer = got.viewer;
```

### `local-development/tests/test_no_groupsync_operator.py`

**Anchor.** `return [g["name"] for g in r.json()]`

**Purpose.** The one existing test helper that consumed /groups as a bare list. REPLACES the anchor line.

```
        # The endpoint returns an object since per-user visibility landed — the rows plus
        # the scope/viewer contract — so the names live under `groups`.
        return [g["name"] for g in r.json()["groups"]]
```

### Test — `test_view_scoping.py — new module, 26 tests (verified: 26 passed; whole suite 1104 passed / 1 skipped; test_dangling_binding_alert_does_not_break_the_self_filter proven to fail on the pre-fix variant)` in `local-development/tests/test_view_scoping.py`

```python
"""Per-user visibility: every personal endpoint scopes at the API handler.

The exposure this guards (REQUIREMENTS_per_user_visibility.md §1, measured): the dashboard
reads the cluster with its own ServiceAccount, so every authenticated reader used to see
the whole RBAC surface — eight-for-eight resources a plain user cannot `oc` list, plus the
login-failure record. The fix scopes each endpoint in the handler and passes the viewer
into the store as a bound parameter, the /api/dashboard/activity pattern generalised.

What is pinned here, and why it must not drift:

  * the SELF tier is the DEFAULT OUTCOME, reached on every failure — no resolver, a
    resolver error, an unrecognised answer, a missing identity. Only the exact string
    "all" from the tier resolver widens (requirements §5.4, decision D1).
  * a non-member's 403 is CONSTANT across "forbidden" and "nonexistent", because an
    endpoint that answers those differently is an existence oracle over the very names
    the self tier withholds.
  * self-matching is BYTE-EXACT. Measured on the live cluster: X-Forwarded-User arrives
    as `lateef.o`, exactly the form group_member/ocp_user carry — while login_event also
    holds an as-typed `LATEEF.O` row that must stay invisible to `lateef.o` (fail-closed;
    a NOCASE match was measured to defeat the index and would cross-leak between Users
    differing only by case).
  * governance-about-objects endpoints (groupsyncs, events, operator-configs,
    bindings/findings) stay FULL VIEW at both tiers, by ruling (spec Q3) — self-scoping
    them would make the dashboard useless to the audience it still serves.
  * withheld aggregates are None, never fabricated zeros, and never recomputed over the
    visible subset — a number whose label lies is the count-versus-page defect class.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.store import Store
from gsd.timeutil import now_iso

VIEWER = "lateef.o"
OTHER = "jane.smith"
AS_VIEWER = {"X-Forwarded-User": VIEWER}


def _seed(db: str) -> None:
    """One cluster the viewer partially belongs to, with every personal dataset present."""
    store = Store(db)
    now = now_iso()
    store.upsert_cluster("c1", "https://x", True)
    store.replace_group_state("c1", [
        {"name": "team-a", "member_count": 2, "sync_provider": "corp_ldap",
         "group_synced_at": now, "ldap_uid": None},
        {"name": "team-b", "member_count": 1, "sync_provider": "corp_ldap",
         "group_synced_at": now, "ldap_uid": None},
        {"name": "secret-group", "member_count": 1, "sync_provider": "corp_ldap",
         "group_synced_at": now, "ldap_uid": None},
        # Zero members -> the `empty_group` alert, which the self tier must not receive.
        {"name": "lonely-group", "member_count": 0, "sync_provider": "corp_ldap",
         "group_synced_at": now, "ldap_uid": None},
        {"name": "gate-group", "member_count": 1, "sync_provider": "corp_ldap",
         "group_synced_at": now, "ldap_uid": "cn=gate,ou=groups,dc=example,dc=com"},
    ], now)
    store.sync_members("c1", {
        "team-a": [VIEWER, OTHER],
        "team-b": [VIEWER],
        "secret-group": [OTHER],
        "lonely-group": [],
        "gate-group": [VIEWER],
    }, {name: now for name in
        ("team-a", "team-b", "secret-group", "lonely-group", "gate-group")}, now)
    store.set_cluster_access_group(
        "c1", "cn=gate,ou=groups,dc=example,dc=com", "discovered", "gate-group", now)
    store.replace_user_bindings("c1", [
        {"binding_kind": "RoleBinding", "binding_namespace": "dev", "binding_name": "rb1",
         "role_kind": "ClusterRole", "role_name": "edit", "user_name": VIEWER,
         "is_platform": 0},
        {"binding_kind": "RoleBinding", "binding_namespace": "dev", "binding_name": "rb2",
         "role_kind": "ClusterRole", "role_name": "admin", "user_name": "jdoe",
         "is_platform": 0},
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "",
         "binding_name": "kubeadmin", "role_kind": "ClusterRole",
         "role_name": "cluster-admin", "user_name": "kubeadmin", "is_platform": 1},
    ], now)
    # A DANGLING binding: the group was seen operator-managed, its object is gone, and a
    # binding still names it. Beyond exercising the finding, this seeds the alert whose
    # construction loop once REBOUND the handler's `scope` variable — the regression
    # test_dangling_binding_alert_does_not_break_the_self_filter pins that.
    store.record_managed_groups(
        "c1", [{"name": "gone-group", "sync_provider": "corp_ldap"}], now)
    store.replace_bindings("c1", [
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "",
         "binding_name": "crb-gone", "role_kind": "ClusterRole", "role_name": "view",
         "group_name": "gone-group"},
    ], now)
    store.record_login_events("c1", [
        {"pod_name": "p1", "user_name": VIEWER, "outcome": "success",
         "at": "2026-08-09T10:00:00Z", "provider": "corp-ldap",
         "ldap_result_code": None, "detail": None, "observed_at": now},
        # The name AS TYPED — a case variant of the viewer, measured to exist on the live
        # cluster. Byte-exact self-matching must NOT return it.
        {"pod_name": "p1", "user_name": VIEWER.upper(), "outcome": "bad_password",
         "at": "2026-08-09T10:01:00Z", "provider": "corp-ldap",
         "ldap_result_code": "52e", "detail": None, "observed_at": now},
        {"pod_name": "p1", "user_name": OTHER, "outcome": "bad_password",
         "at": "2026-08-09T10:02:00Z", "provider": "corp-ldap",
         "ldap_result_code": "52e", "detail": None, "observed_at": now},
        {"pod_name": "p1", "user_name": "ghost.user", "outcome": "rejected",
         "at": "2026-08-09T10:03:00Z", "provider": "corp-ldap",
         "ldap_result_code": None, "detail": None, "observed_at": now},
    ])
    store.close()


def _client(tmp_path, tier_resolver=None, **overrides) -> TestClient:
    """A proxied app over the seeded store. Restrictions ride the DATACLASS DEFAULT (on),
    so this file breaks if anyone quietly flips it off."""
    db = str(tmp_path / "t.db")
    _seed(db)
    settings = Settings(
        clusters=[ClusterConfig("c1", "https://x", token_env="T")],
        db_path=db, oauth_proxy_enabled=True, **overrides,
    )
    return TestClient(build_app(settings, run_poller=False, tier_resolver=tier_resolver))


def _admin(viewer: str) -> str:
    return "all"


# ── The self tier, endpoint by endpoint ────────────────────────────────────────────────


def test_self_reader_sees_only_their_own_groups(tmp_path):
    c = _client(tmp_path)
    body = c.get("/api/clusters/c1/groups", headers=AS_VIEWER).json()
    assert body["scope"] == "self" and body["viewer"] == VIEWER
    assert [g["name"] for g in body["groups"]] == ["gate-group", "team-a", "team-b"]
    assert body["count"] == 3


def test_admin_sees_every_group(tmp_path):
    c = _client(tmp_path, tier_resolver=_admin)
    body = c.get("/api/clusters/c1/groups", headers=AS_VIEWER).json()
    assert body["scope"] == "all"
    assert len(body["groups"]) == 5, "the wide view must be exactly today's list"


def test_group_detail_403_is_constant_for_nonmember_and_nonexistent(tmp_path):
    """Answering those differently is an existence oracle over the withheld group list."""
    c = _client(tmp_path)
    real = c.get("/api/clusters/c1/groups/secret-group", headers=AS_VIEWER)
    fake = c.get("/api/clusters/c1/groups/no-such-group", headers=AS_VIEWER)
    assert real.status_code == fake.status_code == 403
    assert real.json() == fake.json()


def test_member_group_detail_is_served_in_full(tmp_path):
    c = _client(tmp_path)
    body = c.get("/api/clusters/c1/groups/team-a", headers=AS_VIEWER).json()
    assert body["scope"] == "self" and body["viewer"] == VIEWER
    assert {m["user_name"] for m in body["members"]} == {VIEWER, OTHER}, (
        "membership is the entitlement: a member sees their own group's whole roster"
    )


def test_self_reader_sees_only_their_own_user_row(tmp_path):
    c = _client(tmp_path)
    body = c.get("/api/clusters/c1/users", headers=AS_VIEWER).json()
    assert body["scope"] == "self"
    assert [u["user_name"] for u in body["users"]] == [VIEWER]
    assert body["users"][0]["group_count"] == 3


def test_other_profile_is_refused_before_existence(tmp_path):
    c = _client(tmp_path)
    real = c.get(f"/api/clusters/c1/users/{OTHER}", headers=AS_VIEWER)
    fake = c.get("/api/clusters/c1/users/no.such.person", headers=AS_VIEWER)
    assert real.status_code == fake.status_code == 403
    assert real.json() == fake.json()


def test_own_profile_is_served(tmp_path):
    c = _client(tmp_path)
    body = c.get(f"/api/clusters/c1/users/{VIEWER}", headers=AS_VIEWER).json()
    assert body["user"] == VIEWER and body["scope"] == "self"
    assert {g["group_name"] for g in body["groups"]} == {"team-a", "team-b", "gate-group"}


def test_self_logins_are_byte_exact_and_aggregate_free(tmp_path):
    """The most sensitive endpoint: own rows only, and the case-variant row stays hidden.

    `LATEEF.O` was typed by somebody at a keyboard and recorded as typed (measured live);
    only the wide tier may see it, because nothing proves it is the same person and a
    NOCASE join would cross-leak between distinct case-differing Users.
    """
    c = _client(tmp_path)
    body = c.get("/api/clusters/c1/logins", headers=AS_VIEWER).json()
    assert body["scope"] == "self" and body["viewer"] == VIEWER
    assert [a["user_name"] for a in body["attempts"]] == [VIEWER]
    assert body["total"] == 1, "the viewer's own whole-record count, not the cluster's 4"
    assert body["summary"] is None, "failure counts and distinct users are personnel data"
    assert body["ungoverned"] is None
    assert body["capture_started_at"], "window metadata describes the record, and stays"


def test_admin_logins_are_unchanged(tmp_path):
    c = _client(tmp_path, tier_resolver=_admin)
    body = c.get("/api/clusters/c1/logins", headers=AS_VIEWER).json()
    assert body["scope"] == "all"
    assert body["total"] == 4 and body["summary"]["distinct_users"] == 4
    assert len(body["attempts"]) == 4


def test_self_cannot_ask_for_another_users_logins(tmp_path):
    c = _client(tmp_path)
    r = c.get(f"/api/clusters/c1/logins?user={OTHER}", headers=AS_VIEWER)
    assert r.status_code == 403


def test_self_user_bindings_show_only_grants_naming_the_viewer(tmp_path):
    c = _client(tmp_path)
    body = c.get("/api/clusters/c1/user-bindings", headers=AS_VIEWER).json()
    assert body["scope"] == "self"
    assert [b["user_name"] for b in body["bindings"]] == [VIEWER]
    assert body["total"] == 1
    assert body["by_namespace"] is None, "the rollup aggregates other people's grants"
    assert body["excluded_platform"] is None


def test_self_membership_changes_are_the_viewers_only(tmp_path):
    c = _client(tmp_path)
    body = c.get("/api/clusters/c1/membership-changes", headers=AS_VIEWER).json()
    assert body["scope"] == "self"
    assert {ch["user_name"] for ch in body["changes"]} == {VIEWER}
    assert {ch["group_name"] for ch in body["changes"]} == {"team-a", "team-b", "gate-group"}


def test_self_cluster_access_is_own_gate_status_only(tmp_path):
    c = _client(tmp_path)
    body = c.get("/api/clusters/c1/cluster-access", headers=AS_VIEWER).json()
    assert body["scope"] == "self"
    assert body["gated"] is True and body["synced"] is True
    assert body["in_access_group"] is True, "the viewer is seeded into the gate group"
    assert body["dn"] is None and body["source"] is None and body["group_name"] is None
    assert body["summary"] is None
    assert body["access_without_login"] is None and body["login_without_access"] is None


def test_admin_cluster_access_is_unchanged(tmp_path):
    c = _client(tmp_path, tier_resolver=_admin)
    body = c.get("/api/clusters/c1/cluster-access", headers=AS_VIEWER).json()
    assert body["scope"] == "all"
    assert body["dn"] == "cn=gate,ou=groups,dc=example,dc=com"
    assert isinstance(body["access_without_login"], list)


def test_alerts_are_filtered_by_kind_at_self(tmp_path):
    """The feed keeps its invariant — every alert has a page behind it — per tier.

    The seed produces `empty_group` (its page is the self-scoped Groups tab, and an empty
    group can never contain the viewer) and `direct_user_binding` (an aggregate over other
    people's grants). Both must vanish at self, and the response must say it is narrowed
    rather than letting green mean hidden.
    """
    c = _client(tmp_path)
    wide = _client(tmp_path, tier_resolver=_admin)
    self_body = c.get("/api/alerts", headers=AS_VIEWER).json()
    wide_body = wide.get("/api/alerts", headers=AS_VIEWER).json()
    wide_kinds = {a["kind"] for a in wide_body["alerts"]}
    assert {"empty_group", "direct_user_binding"} <= wide_kinds
    self_kinds = {a["kind"] for a in self_body["alerts"]}
    assert not ({"empty_group", "direct_user_binding"} & self_kinds)
    assert self_body["scope"] == "self" and wide_body["scope"] == "all"
    assert self_body["count"] == len(self_body["alerts"])


def test_dangling_binding_alert_does_not_break_the_self_filter(tmp_path):
    """The regression this fixture's dangling binding exists for.

    The dangling-alert loop used a local variable named `scope` for its namespace label,
    which rebound the handler's tier variable — after one dangling finding the self filter
    compared against "cluster-wide" and passed EVERYTHING through: a fail-open. The fix
    renamed the local; this pins it by asserting both the filter and the declared scope
    survive a feed that contains a dangling alert.
    """
    c = _client(tmp_path)
    body = c.get("/api/alerts", headers=AS_VIEWER).json()
    kinds = {a["kind"] for a in body["alerts"]}
    assert "dangling_binding" in kinds, "the allowed kind must still arrive at self"
    assert "empty_group" not in kinds, (
        "a dangling finding in the feed must not disable the self filter for the rest"
    )
    assert body["scope"] == "self", "the declared scope must survive the alert loop"


def test_governance_endpoints_stay_full_view_at_self(tmp_path):
    """Ruled in the spec (Q3): data about OBJECTS — CRs, operator configs, group-subject
    binding findings — is served whole to every admitted reader; the person-named rows
    live on /user-bindings and are scoped there."""
    c = _client(tmp_path)
    syncs = c.get("/api/clusters/c1/groupsyncs", headers=AS_VIEWER)
    assert syncs.status_code == 200 and isinstance(syncs.json(), list)
    findings = c.get("/api/clusters/c1/bindings/findings", headers=AS_VIEWER).json()
    assert findings["scope"] == "all" and findings["viewer"] == VIEWER
    configs = c.get("/api/clusters/c1/operator-configs", headers=AS_VIEWER).json()
    assert configs["scope"] == "all"
    events = c.get("/api/clusters/c1/groupsyncs/x/events", headers=AS_VIEWER).json()
    assert events["scope"] == "all"


def test_scope_and_viewer_are_declared_on_every_scoped_response(tmp_path):
    """The UI never derives the tier — each scoped payload states what it covers."""
    c = _client(tmp_path)
    for path in (
        "/api/clusters/c1/groups",
        "/api/clusters/c1/users",
        f"/api/clusters/c1/users/{VIEWER}",
        "/api/clusters/c1/groups/team-a",
        "/api/clusters/c1/logins",
        "/api/clusters/c1/user-bindings",
        "/api/clusters/c1/membership-changes",
        "/api/clusters/c1/cluster-access",
        "/api/alerts",
    ):
        body = c.get(path, headers=AS_VIEWER).json()
        assert body.get("scope") == "self", f"{path} did not declare its scope"
        assert body.get("viewer") == VIEWER, f"{path} did not declare its viewer"


# ── The failure directions — every road that is not a positive "all" ends at self ──────


def test_indeterminate_tier_fails_closed_to_self(tmp_path):
    """Requirements §5.4 / DoD 4: a SAR error or timeout must yield self, never wide."""
    def boom(viewer: str) -> str:
        raise TimeoutError("the API server did not answer")
    c = _client(tmp_path, tier_resolver=boom)
    body = c.get("/api/clusters/c1/groups", headers=AS_VIEWER).json()
    assert body["scope"] == "self" and len(body["groups"]) == 3


def test_a_junk_tier_answer_narrows_rather_than_widens(tmp_path):
    """Only the exact string "all" widens — the _visibility_setting discipline, applied
    to the resolver so a bug there cannot become a wide view."""
    c = _client(tmp_path, tier_resolver=lambda v: "ALL")
    assert c.get("/api/clusters/c1/groups", headers=AS_VIEWER).json()["scope"] == "self"


def test_no_resolver_wired_means_self(tmp_path):
    """An app built without the tier machinery restricts everyone — never the reverse."""
    c = _client(tmp_path, tier_resolver=None)
    assert c.get("/api/clusters/c1/groups", headers=AS_VIEWER).json()["scope"] == "self"


def test_no_identity_behind_the_proxy_is_refused_not_widened(tmp_path):
    """Proxy on, no header: personal data 403s; governance data still answers."""
    c = _client(tmp_path)
    assert c.get("/api/clusters/c1/users").status_code == 403
    assert c.get("/api/clusters/c1/logins").status_code == 403
    assert c.get("/api/clusters/c1/groupsyncs").status_code == 200


def test_restrictions_off_restores_the_wide_view(tmp_path):
    """`GSD_ENABLE_VIEW_RESTRICTIONS=false` is the deliberate, documented escape hatch."""
    c = _client(tmp_path, view_restrictions_enabled=False)
    body = c.get("/api/clusters/c1/groups", headers=AS_VIEWER).json()
    assert body["scope"] == "all" and len(body["groups"]) == 5


def test_proxy_off_never_derives_a_tier_from_the_header(tmp_path, caplog):
    """Without the proxy the header is caller-typed, so no restriction can be real —
    the app keeps today's proxy-less behaviour and says so loudly at startup; the chart
    refuses to render restrictions-on/proxy-off at all (template interlock)."""
    db = str(tmp_path / "t.db")
    _seed(db)
    settings = Settings(clusters=[ClusterConfig("c1", "https://x", token_env="T")],
                        db_path=db, oauth_proxy_enabled=False)
    with caplog.at_level("WARNING", logger="gsd.api"):
        c = TestClient(build_app(settings, run_poller=False))
    assert any("view restrictions" in r.message for r in caplog.records), (
        "the inert combination must be loud in the pod log, not silent"
    )
    body = c.get("/api/clusters/c1/groups",
                 headers={"X-Forwarded-User": "anyone.at.all"}).json()
    assert body["scope"] == "all" and body["viewer"] is None, (
        "a caller-typed header must not become an identity, in either direction"
    )


def test_the_resolver_is_not_consulted_when_restrictions_are_off(tmp_path):
    """The wide-by-choice deployment must not depend on the SAR path at all."""
    def fail_if_called(viewer: str) -> str:
        raise AssertionError("the resolver must not run when restrictions are off")
    c = _client(tmp_path, tier_resolver=fail_if_called, view_restrictions_enabled=False)
    assert c.get("/api/clusters/c1/groups", headers=AS_VIEWER).status_code == 200


def test_metrics_are_untouched_by_scoping(tmp_path):
    """§5.6: /metrics stays unauthenticated, aggregate, and username-free."""
    c = _client(tmp_path)
    text = c.get("/metrics").text
    assert "gsd_groups_total" in text
    assert VIEWER not in text and OTHER not in text
```

**Risks it names.** (1) SEAM DEPENDENCY, fail-closed by design: build_app's new `tier_resolver` parameter is the hand-off to Lens 1's SAR module; until create_app wires it, every reader behind the proxy gets the SELF view — admins included. That is the D1-correct failure direction but it means this lens ALONE ships a dashboard where nobody has the wide view; the arbiter must land Lens 1's resolver (and its whoami/startup-log surface) in the same release. The resolver contract is: Callable[[str], str], returns exactly "all" to widen, anything else or any exception narrows. (2) PROXY-OFF SEMANTICS, a deliberate deviation to state plainly: with GSD_ENABLE_VIEW_RESTRICTIONS=true and oauthProxy off, this code serves today's wide view with a startup WARNING (the ActivityRecorder both-conditions composition, api.py's own precedent) rather than 403ing personal endpoints as spec Lens 2's Q8 sketched. Rationale: without the proxy there are no authenticated readers to tier and a header-derived 403 protects nothing an open port doesn't already give away; empirically, the 403 variant broke wide swaths of the in-tree suite (every fixture constructs Settings directly, proxy off) — measured before choosing. The compensating control is Lens 3's template interlock (restrictions-on + proxy-off must fail helm template); if the arbiter rejects the interlock, this decision must be re-opened. test_proxy_off_never_derives_a_tier_from_the_header pins the chosen semantics either way. (3) SA VERBS: this lens's code makes ZERO new cluster calls and needs no new ServiceAccount verb; the only new permission in the whole feature is the resolver's `create subjectaccessreviews`, already held via system:auth-delegator on this deployment — but the chart renders that binding only when apiTokenAccess.enabled (default false), so a default install fails everyone closed to self until Lens 1/3 add the unconditional grant. (4) BREAKING WIRE SHAPES: /groups and /api/alerts change from bare lists to objects (rows under .groups/.alerts plus scope/viewer). The two UI unwraps included keep the app working; docs/api-contract.md and any external consumer (curl scripts, the README examples) must be updated by the docs/UI lens. (5) BYTE-EXACT MATCHING is fail-closed but not fail-obvious: a direct binding naming `jdoe` is invisible to `john.doe`, and a case-variant login row is invisible to its own author — measured as the real data shape (login_event holds LATEEF.O beside lateef.o) and deliberately unfixed; an IdP whose preferredUsername differs from groupsync's userNameAttributes renders every self view empty, diagnosable only via the UI empty-state naming the whoami identity (Lens 3's wording). (6) NOT MEASURED HERE: whether the proxy sets X-Forwarded-User on the apiTokenAccess bearer path — if it does not, token callers land at self/403 on personal endpoints regardless of entitlement; and the user_binding self-filter is a bounded scan (45 rows on the lab) whose behaviour at 10-100x scale should be re-checked with EXPLAIN QUERY PLAN before anyone adds an index speculatively. (7) The empty-group/unattributed/stale_group alert kinds are hidden at self even when metrics publish their counts; an operator may ask for the counts-without-subjects variant later — the SELF_ALERT_KINDS allow-list is the single place to widen it.


## Chart and configuration

**What it reports.** Read both docs in full, then values.yaml (1008 lines), configmap.yaml, deployment.yaml, rbac.yaml, NOTES.txt, _helpers.tpl, the chart README, config.py (all 499 lines), the api.py whoami/activity precedent, and the in-tree chart/config test suites. Measured before writing: helm v3.14.0 sprig semantics for the nil cases the task warns about (`toString nil` -> "<nil>", `kindIs "invalid"` detects a present-but-nil key, `default dict` absorbs a nilled block), and the actual worktree baseline — 1078 passed, 1 skipped, not the stated 1057. Verified the house-rule claim about the SAR grant: it is NOT enough on a default install — rbac.yaml renders the system:auth-delegator binding only when oauthProxy.enabled AND apiTokenAccess.enabled, and apiTokenAccess defaults false, so a default install has no `create subjectaccessreviews` and the tier check would fail every reader closed to self forever; on the reference deployment (environments/crc.yaml, apiTokenAccess on) it already exists. The code therefore widens that binding's render condition to `or apiTokenAccess.enabled visibilityEnabled` rather than adding a rule to the reader ClusterRole, because the in-tree test pins the reader role's only write verb to leases. All snippets were applied to a full mirror of the worktree and verified end to end: `GSD_ENABLE_VIEW_RESTRICTIONS` renders "true" by default, "false" only on the exact word false, and "true" when the whole stanza or any sub-key is nilled out (the dig-panic case); the four adminSar keys reach the ConfigMap including the core-group ("") and resource/subresource spellings; miscased/versioned/nonsense shapes fail the render with named messages; visibility-on + proxy-off refuses to render (spec Q8 interlock) while off+off renders; NOTES prints the effective check, the exact `oc adm policy add-cluster-role-to-user cluster-reader <username>` command, and the rollback flag in both branches; config.py parses everything through the _bool_setting/_visibility_setting idioms with every failure direction landing restricted (including the operator's original RESCRICTIONS typo, which is simply never read), splits resource/subresource for the SAR builder, and states the worst-case revocation window (60s tier TTL + one in-flight page, groups from a fresh read on cache miss) on the visibility_tier_ttl_seconds field where the number lives. Reconciliation ruling: the new control sits BESIDE config.userActivity.visibility — domains are disjoint (cluster data vs the dashboard's own reader records), merging would widen a personnel dataset to every cluster-reader, and Helm ignores unknown keys so a rename would silently drop set values; the migration is cross-referencing comments in values.yaml, a rewritten now-stale "no admins-only tier" paragraph in both values.yaml and the README, and the README row update. Full suite after all changes: 1099 passed, 1 skipped — baseline plus exactly the 21 new tests (11 config, 10 chart), zero regressions.

### `charts/group-sync-dashboard/values.yaml`

**Anchor.** `# the behaviour, in a place an operator would reasonably believe.`

**Purpose.** New top-level visibility stanza (D1 switch + D2 choosable SAR), inserted AFTER the anchor — the last line of the oauthProxy section — with the measured role matrix in the comment so an operator can choose a threshold without opening the docs.

```

# ---------------------------------------------------------------------------
# Per-user visibility
# ---------------------------------------------------------------------------
# WHO SEES WHAT, once the proxy has admitted a reader. ON by default, because it fixes an
# exposure rather than adding a feature: the dashboard reads the cluster with its own
# ServiceAccount, so with restrictions off EVERY authenticated reader sees the full RBAC
# binding surface, every group's membership and every person's login failures — data a
# plain user cannot read with `oc` (measured: eight `oc auth can-i list` checks, all no).
#
# With restrictions on, a reader sees only what belongs to them — their profile, their
# groups, their grants, their own login attempts — unless a SubjectAccessReview, asked by
# the app as its own ServiceAccount and naming the reader AND their groups, allows the
# check in `adminSar` below. An INDETERMINATE answer (SAR error, timeout) always yields
# the narrow view, never the wide one. Requires oauthProxy.enabled — with the proxy off
# there is no trusted identity to scope to, and the chart refuses to render rather than
# ship a control that cannot work.
#
# A REVOKED administrator keeps the wide view for at most the tier cache TTL (60s) plus
# one in-flight page; a newly granted one waits the same. The SAR itself evaluates live
# RBAC — only the cached verdict and the group list age.
visibility:
  # true -> the env var GSD_ENABLE_VIEW_RESTRICTIONS on the Deployment. The spelling is
  # load-bearing: the app reads exactly that name, defaults to restricted, and never sees a
  # misspelling — so a typo cannot silently disable the control.
  #
  # false restores today's everyone-sees-everything view. Make that a deliberate, recorded
  # choice: it re-opens the exposure above for every authenticated account.
  enabled: true

  # THE ADMINISTRATOR THRESHOLD — the SubjectAccessReview a reader must pass to see
  # everything. Expressed as the check itself rather than a list of role names, because a
  # name list would miss cluster-reader and every custom role that grants the same read.
  #
  # Measured on the reference cluster, per role bound CLUSTER-WIDE:
  #
  #   check                                        admits
  #   list groups.user.openshift.io (default)      cluster-admin, cluster-reader
  #   list rolebindings.rbac.authorization.k8s.io  those two PLUS cluster-wide `admin`
  #   anything your own ClusterRole grants         whoever holds that role
  #
  # `edit` and `view` pass NO cluster-scoped list at all — bound cluster-wide they are
  # indistinguishable from a plain user here — and `cluster-edit`/`cluster-view` do not
  # exist as roles. If people holding edit/view must see everything, bind them a role that
  # grants the check above, or set enabled: false.
  adminSar:
    # "" means the core API group. No version suffix.
    apiGroup: user.openshift.io
    # Lowercase plural; resource/subresource (e.g. pods/log) is accepted.
    resource: groups
    verb: list
    # Empty means a cluster-scoped check — the normal case. Set a namespace only for a
    # threshold that is deliberately namespaced, e.g. get pods/log in
    # openshift-authentication, which cluster-wide admin/edit/view also pass.
    namespace: ""
```

### `charts/group-sync-dashboard/values.yaml`

**Anchor.** `# There is deliberately no "admins only" tier. Doing that properly means a`

**Purpose.** REPLACES the four comment lines starting at the anchor (through '... a group you choose.') inside config.userActivity — the old text claims an app-side SubjectAccessReview is off the table, which the new feature makes stale; the replacement states why the two visibility controls sit beside each other and never merge.

```
    # DELIBERATELY INDEPENDENT of the `visibility` block below, which governs CLUSTER data.
    # This knob governs data the dashboard GENERATED about its own readers, and the two must
    # not merge: handing this dataset to the visibility tier would let every cluster-reader
    # see colleagues' presence records — a personnel dataset widened as a side effect of a
    # refactor. Passing the visibility.adminSar check therefore does NOT widen this view;
    # only the exact string `all` here does. If you need an admins-only door for the whole
    # dashboard, that is oauthProxy.sar.
```

### `charts/group-sync-dashboard/templates/_helpers.tpl`

**Anchor.** `{{- define "gsd.accessMode" -}}`

**Purpose.** APPEND AT THE END OF THE FILE — the anchor locates the file's last define; the block goes after that define's two closing '{{- end -}}' lines. The helpers are self-contained defines, so any placement outside another define renders identically. Nil-safe resolution of the visibility values plus render-refusal of nonsensical SAR shapes, verified on helm v3.14.0 (toString nil -> "<nil>", kindIs "invalid" detects nil leaves).

```

# ── Per-user visibility ──────────────────────────────────────────────────────────────
# Every read below is nil-safe on purpose: commenting out the sub-keys in a values file
# leaves `visibility:` (or `adminSar:`) present-but-nil, which a bare field access — and
# sprig's dig — panics on. Intermediates are defaulted to a dict and a nil leaf is
# treated as "not set", which falls back to the shipped default, never to "off".

# Returns the word true or false. Only the exact word false — bool or string — disables:
# the switch guards personal data, so anything unrecognised must fail toward restricted.
{{- define "gsd.visibilityEnabled" -}}
{{- if eq (toString ((.Values.visibility | default dict).enabled)) "false" -}}
false
{{- else -}}
true
{{- end -}}
{{- end -}}

# The four adminSar fields, each validated where it is resolved so a nonsensical shape
# refuses to render anywhere it would be used. RBAC matching is exact and lowercase, so a
# miscased or misspelt field would not error — it would answer allowed=false for every
# viewer and silently demote every administrator, which is why these fail the render
# instead of passing the string through.

{{- define "gsd.visibilitySarApiGroup" -}}
{{- $sar := ((.Values.visibility | default dict).adminSar) | default dict -}}
{{- if or (not (hasKey $sar "apiGroup")) (kindIs "invalid" $sar.apiGroup) -}}
user.openshift.io
{{- else -}}
{{- $g := trim (toString $sar.apiGroup) -}}
{{- if not (regexMatch "^[a-z0-9.-]*$" $g) -}}
{{- fail (printf "visibility.adminSar.apiGroup %q is not an API group. Give the group alone (e.g. user.openshift.io, rbac.authorization.k8s.io), no version suffix, or \"\" for the core group." $g) -}}
{{- end -}}
{{- $g -}}
{{- end -}}
{{- end -}}

{{- define "gsd.visibilitySarResource" -}}
{{- $sar := ((.Values.visibility | default dict).adminSar) | default dict -}}
{{- if or (not (hasKey $sar "resource")) (kindIs "invalid" $sar.resource) -}}
groups
{{- else -}}
{{- $r := trim (toString $sar.resource) -}}
{{- if not (regexMatch "^[a-z0-9-]+(/[a-z0-9-]+)?$" $r) -}}
{{- fail (printf "visibility.adminSar.resource %q is not a resource. Use the lowercase plural (e.g. groups, rolebindings), optionally resource/subresource (e.g. pods/log). RBAC matching is exact, so anything else would silently answer no for every viewer and demote every administrator." $r) -}}
{{- end -}}
{{- $r -}}
{{- end -}}
{{- end -}}

{{- define "gsd.visibilitySarVerb" -}}
{{- $sar := ((.Values.visibility | default dict).adminSar) | default dict -}}
{{- if or (not (hasKey $sar "verb")) (kindIs "invalid" $sar.verb) -}}
list
{{- else -}}
{{- $v := trim (toString $sar.verb) -}}
{{- if not (regexMatch "^[a-z]+$" $v) -}}
{{- fail (printf "visibility.adminSar.verb %q is not a verb. Kubernetes verbs are lowercase words (list, get, watch, ...). RBAC matching is exact, so anything else would silently answer no for every viewer and demote every administrator." $v) -}}
{{- end -}}
{{- $v -}}
{{- end -}}
{{- end -}}

{{- define "gsd.visibilitySarNamespace" -}}
{{- $sar := ((.Values.visibility | default dict).adminSar) | default dict -}}
{{- if or (not (hasKey $sar "namespace")) (kindIs "invalid" $sar.namespace) -}}
{{- else -}}
{{- $n := trim (toString $sar.namespace) -}}
{{- if not (regexMatch "^[a-z0-9-]*$" $n) -}}
{{- fail (printf "visibility.adminSar.namespace %q is not a namespace name. Leave it empty for a cluster-scoped check." $n) -}}
{{- end -}}
{{- $n -}}
{{- end -}}
{{- end -}}
```

### `charts/group-sync-dashboard/templates/configmap.yaml`

**Anchor.** `userActivityRetentionDays: {{ .Values.config.userActivity.retentionDays }}`

**Purpose.** Inserted AFTER the anchor: the four adminSar keys the app reads. The enable switch deliberately does not appear here — it travels only as the env var on the Deployment, so the two can never disagree.

```
    # Per-user visibility: the SubjectAccessReview that separates the wide tier from the
    # self tier. The ON/OFF switch itself travels as GSD_ENABLE_VIEW_RESTRICTIONS on the
    # Deployment — one wire, visible where an auditor reads the pod spec — so it is
    # deliberately not repeated here, where a second copy could disagree with the first.
    # Quoted unconditionally: the apiGroup may legitimately be the empty string (the core
    # API group), which unquoted YAML would read as null.
    visibilityAdminSarApiGroup: {{ include "gsd.visibilitySarApiGroup" . | quote }}
    visibilityAdminSarResource: {{ include "gsd.visibilitySarResource" . | quote }}
    visibilityAdminSarVerb: {{ include "gsd.visibilitySarVerb" . | quote }}
    visibilityAdminSarNamespace: {{ include "gsd.visibilitySarNamespace" . | quote }}
```

### `charts/group-sync-dashboard/templates/deployment.yaml`

**Anchor.** `apiVersion: apps/v1`

**Purpose.** Inserted BEFORE the anchor, joining the existing render guards: a per-user control with no trusted identity is unsatisfiable (spec Q8 interlock), so proxy-off + visibility-on refuses to render and names the deliberate opt-out.

```
{{- if and (eq (include "gsd.visibilityEnabled" .) "true") (not .Values.oauthProxy.enabled) }}
{{- fail "visibility.enabled=true requires oauthProxy.enabled=true. The per-user tiers scope data to X-Forwarded-User, which is trustworthy only when the oauth-proxy sets it; with the proxy off the header is whatever the caller typed, so the control cannot work. Turn the proxy on, or set visibility.enabled=false to accept — deliberately and on the record — that every reader of an unauthenticated route sees everything." }}
{{- end }}
```

### `charts/group-sync-dashboard/templates/deployment.yaml`

**Anchor.** `value: {{ .Values.logLevel | quote }}`

**Purpose.** Inserted AFTER the anchor (the GSD_LOG_LEVEL value line): the D1 env var, rendered from the one values key via the nil-safe helper so the app always receives exactly "true" or "false".

```
            # The view-restrictions switch rides the Deployment rather than the ConfigMap:
            # one wire from one values key, visible in `oc describe deploy` where an
            # auditor looks for a security control. The NAME is load-bearing — the app
            # reads exactly GSD_ENABLE_VIEW_RESTRICTIONS and defaults to restricted, so a
            # misspelling anywhere is simply never read and cannot turn the control off.
            - name: GSD_ENABLE_VIEW_RESTRICTIONS
              value: {{ include "gsd.visibilityEnabled" . | quote }}
```

### `charts/group-sync-dashboard/templates/rbac.yaml`

**Anchor.** `{{- if and .Values.oauthProxy.enabled .Values.oauthProxy.apiTokenAccess.enabled }}`

**Purpose.** REPLACES the anchor line. Verified against the house rule: `create subjectaccessreviews` via system:auth-delegator is enough on the reference deployment (apiTokenAccess on) but NOT on a default install — the binding was gated on apiTokenAccess (default false), so every viewer would have failed closed to self forever. Widening the condition keeps the grant on the recognisable stock role and keeps the reader ClusterRole's only write verb pinned to leases, which the in-tree test asserts.

```
{{- if and .Values.oauthProxy.enabled (or .Values.oauthProxy.apiTokenAccess.enabled (eq (include "gsd.visibilityEnabled" .) "true")) }}
```

### `charts/group-sync-dashboard/templates/rbac.yaml`

**Anchor.** `# workloads. That trade is why this is default-off and why the dashboard works without it.`

**Purpose.** REPLACES the anchor line: 'default-off' is no longer true of this binding, and the comment must name the second consumer and the §5.1 compatibility argument.

```
# workloads.
#
# TWO CONSUMERS, one grant, and only the second is on by default. The proxy uses it for
# -openshift-delegate-urls (apiTokenAccess, default off). The DASHBOARD uses
# `create subjectaccessreviews` for the per-user visibility tier: it asks "may this reader
# pass visibility.adminSar?" as its own ServiceAccount, which is why this binding renders
# whenever visibility.enabled is true. A SubjectAccessReview creates no persistent object
# and reads nothing, so the reader role's rule — no write verb on anything the dashboard
# reports on — still holds. Without this grant every review errors and every reader,
# administrators included, fails closed to the self tier permanently.
```

### `charts/group-sync-dashboard/templates/NOTES.txt`

**Anchor.** `dashboard{{ if .Values.oauthProxy.sar }}, subject to the SubjectAccessReview in oauthProxy.sar{{ end }}.`

**Purpose.** Inserted AFTER the anchor, inside the proxy-enabled branch: states the effective mode, the effective check (rendered from the resolved values), the exact grant command, the fail-closed rule and the rollback flag. Both branches verified with helm install --dry-run=client.

```
{{- if eq (include "gsd.visibilityEnabled" .) "true" }}
{{- $sarGroup := include "gsd.visibilitySarApiGroup" . }}
{{- $sarResource := include "gsd.visibilitySarResource" . }}
{{- $sarVerb := include "gsd.visibilitySarVerb" . }}
{{- $sarNamespace := include "gsd.visibilitySarNamespace" . }}

Visibility: RESTRICTED (visibility.enabled=true, the default). Each reader sees only their
own profile, groups, grants and login attempts. A reader sees everything only if a
SubjectAccessReview allows:

  {{ $sarVerb }} {{ $sarResource }}{{ with $sarGroup }}.{{ . }}{{ end }}{{ with $sarNamespace }} in namespace {{ . }}{{ end }}
{{- if and (eq $sarGroup "user.openshift.io") (eq $sarResource "groups") (eq $sarVerb "list") (eq $sarNamespace "") }}

That default check admits cluster-admin and cluster-reader, and nobody else.
{{- else }}

This is a custom check (visibility.adminSar): whoever holds a role granting it gets the
wide view. Stock cluster-reader passes every threshold measured for this feature.
{{- end }}
Grant the wide view through normal RBAC, never a chart value:

  oc adm policy add-cluster-role-to-user cluster-reader <username>

  (prefer the group form — a grant naming a person survives their departure:
   oc adm policy add-cluster-role-to-group cluster-reader <ldap-group>)

An indeterminate review (API error, timeout) yields the narrow view, never the wide one.
Restore the old everyone-sees-everything behaviour only as a deliberate choice:
  --set visibility.enabled=false
{{- else }}

Visibility: WIDE (visibility.enabled=false). Every admitted reader sees the full RBAC
binding surface, every group's membership and every person's login attempts. You chose
this; the default is restricted.
{{- end }}
```

### `local-development/gsd/config.py`

**Anchor.** `import os`

**Purpose.** Inserted AFTER the anchor: re is needed by the SAR-shape validator, placed in alphabetical order.

```
import re
```

### `local-development/gsd/config.py`

**Anchor.** `user_activity_retention_days: int = 400`

**Purpose.** Inserted AFTER the anchor: the Settings fields. visibility_enabled defaults True so every failure direction (missing, misspelt, nonsense) lands restricted; the TTL field carries the worst-case staleness window statement where a reader of the number will find it.

```

    # ── PER-USER VISIBILITY ────────────────────────────────────────────────────────────────────────
    # ON by default: with restrictions off, every authenticated reader sees the ServiceAccount's
    # view of the cluster — the full RBAC binding surface and every person's login failures — which
    # a plain user cannot read with oc. `false` restores that wide view as a deliberate choice.
    #
    # The chart wires this as GSD_ENABLE_VIEW_RESTRICTIONS on the Deployment, and the spelling is
    # load-bearing: a misspelt variable is simply never read, and the default here is True, so a
    # typo leaves the control ON rather than silently disabling a security control.
    visibility_enabled: bool = True
    # The SubjectAccessReview separating the wide tier from the self tier, chosen by the operator
    # (chart: visibility.adminSar). The default — list groups.user.openshift.io — admits
    # cluster-admin and cluster-reader and nobody else; `list rolebindings` also admits
    # cluster-wide `admin`; `edit`/`view` pass no cluster-scoped list at all. Expressed as the
    # check itself, not role names: a name list would miss cluster-reader and every custom role.
    visibility_admin_sar_api_group: str = "user.openshift.io"
    visibility_admin_sar_resource: str = "groups"
    # Split out of a "resource/subresource" spelling (e.g. pods/log) at parse time, so the SAR
    # builder never re-parses the string.
    visibility_admin_sar_subresource: str = ""
    visibility_admin_sar_verb: str = "list"
    # Empty means a cluster-scoped check.
    visibility_admin_sar_namespace: str = ""
    # How long a viewer's tier verdict may be reused before it is re-decided.
    #
    # THE WORST-CASE STALENESS WINDOW, stated where the number lives: the SAR evaluates live RBAC,
    # but its verdict is cached for this long, and the viewer's groups are supplied to it from a
    # fresh read taken when the cache misses — never from the poll snapshot, whose interval is
    # tuned for history resolution, not authorization. A user REMOVED from an admin group
    # therefore keeps the wide view for at most this many seconds plus one in-flight page (the
    # fail-open direction); a user ADDED waits the same. An indeterminate answer (SAR error,
    # timeout) is never cached and always yields the self tier.
    visibility_tier_ttl_seconds: int = 60
```

### `local-development/gsd/config.py`

**Anchor.** `return "self"`

**Purpose.** Inserted AFTER the anchor (the last line of _visibility_setting): the SAR-shape parser. Any unusable field falls back to the WHOLE default check — never per-field, never off, never wider.

```


# What each field of visibility.adminSar may contain. RBAC matching is exact and lowercase, so a
# miscased or misspelt field would not error — it would answer allowed=false for every viewer and
# silently demote every administrator. The chart refuses these shapes at render time; this guards
# the same line for a hand-written config file.
_SAR_FIELD_PATTERNS = {
    "visibilityAdminSarApiGroup": re.compile(r"[a-z0-9.\-]*"),
    "visibilityAdminSarResource": re.compile(r"[a-z0-9\-]+(/[a-z0-9\-]+)?"),
    "visibilityAdminSarVerb": re.compile(r"[a-z]+"),
    "visibilityAdminSarNamespace": re.compile(r"[a-z0-9\-]*"),
}

_SAR_DEFAULTS = {
    "visibilityAdminSarApiGroup": "user.openshift.io",
    "visibilityAdminSarResource": "groups",
    "visibilityAdminSarVerb": "list",
    "visibilityAdminSarNamespace": "",
}


def _visibility_sar_setting(raw: dict) -> tuple[str, str, str, str, str]:
    """The admin-threshold SubjectAccessReview, taken whole or not at all.

    Fail SAFE, in the right direction: any unusable field falls back to the ENTIRE default check —
    list groups.user.openshift.io, the narrowest measured threshold — never to "everyone passes"
    and never to disabling the control. Whole, because half a custom check (the operator's
    resource under the default verb) is a question nobody chose to ask.

    Returns (api_group, resource, subresource, verb, namespace); a resource/subresource spelling
    is split here so the SAR builder never re-parses.
    """
    fields: dict[str, str] = {}
    for key, pattern in _SAR_FIELD_PATTERNS.items():
        value = raw.get(key)
        if value is None:
            # Absent or nil means "not set", which takes the default — matching the chart, where a
            # commented-out sub-key must not change the question.
            fields[key] = _SAR_DEFAULTS[key]
            continue
        word = str(value).strip()
        if not pattern.fullmatch(word):
            log.warning(
                "%s=%r is not usable in a SubjectAccessReview; using the default check "
                "(list groups.user.openshift.io)",
                key, value,
            )
            fields = dict(_SAR_DEFAULTS)
            break
        fields[key] = word
    resource, _, subresource = fields["visibilityAdminSarResource"].partition("/")
    return (
        fields["visibilityAdminSarApiGroup"],
        resource,
        subresource,
        fields["visibilityAdminSarVerb"],
        fields["visibilityAdminSarNamespace"],
    )
```

### `local-development/gsd/config.py`

**Anchor.** `return Settings(`

**Purpose.** Inserted BEFORE the anchor in load_settings: resolve the SAR shape once, so a fallback warns once rather than five times.

```
    admin_sar = _visibility_sar_setting(raw)
```

### `local-development/gsd/config.py`

**Anchor.** `user_activity_visibility=_visibility_setting(raw),`

**Purpose.** Inserted BEFORE the anchor (keyword-argument order is immaterial): the parse sites. _bool_setting with default True means env wins, the ConfigMap spelling works for local development, and every unrecognisable value lands restricted.

```
        visibility_enabled=_bool_setting(
            raw, "GSD_ENABLE_VIEW_RESTRICTIONS", "visibilityEnabled", True
        ),
        visibility_admin_sar_api_group=admin_sar[0],
        visibility_admin_sar_resource=admin_sar[1],
        visibility_admin_sar_subresource=admin_sar[2],
        visibility_admin_sar_verb=admin_sar[3],
        visibility_admin_sar_namespace=admin_sar[4],
        visibility_tier_ttl_seconds=_num_setting(
            raw, "GSD_VISIBILITY_TIER_TTL_SECONDS", "visibilityTierTtlSeconds", 60, int
        ),
```

### `charts/group-sync-dashboard/README.md`

**Anchor.** `| `config.userActivity.visibility` | `self` | `self` \| `all`. `self` means each authenticated user sees only their own rows. Anything unrecognised is treated a`

**Purpose.** REPLACES the anchor row: cross-references the new control so the two visibility knobs read as deliberately disjoint, not as a configuration trap.

```
| `config.userActivity.visibility` | `self` | `self` \| `all`. `self` means each authenticated user sees only their own rows. Anything unrecognised is treated as `self` — an unrecognised value must never be the one that widens access to a personnel dataset. Deliberately independent of `visibility.enabled` below: passing the admin check does **not** widen this view |
```

### `charts/group-sync-dashboard/README.md`

**Anchor.** `There is deliberately no "admins only" tier: doing that properly means a SubjectAccessReview`

**Purpose.** REPLACES the three-line paragraph starting at the anchor (through '... restricts the whole dashboard.') — the old objection to an app-side SAR is now stale, and the honest reason the knobs stay separate is the personnel-data widening.

```
There is deliberately no "admins only" tier here, even though the visibility control below
now performs exactly that SubjectAccessReview for cluster data: this dataset is about the
dashboard's own *readers*, not the cluster, and handing it to the tier would let every
`cluster-reader` browse colleagues' presence records — a personnel dataset widened as a side
effect of a refactor. Only the exact string `all` here widens it. If you need an admins-only
door for the whole dashboard, that is `oauthProxy.sar`.
```

### `charts/group-sync-dashboard/README.md`

**Anchor.** `day. Above one replica it is per-pod, like the rest of the history.`

**Purpose.** Inserted AFTER the anchor (before '### Workload'): the new values-table section, matching the README's existing row style, with the measured matrix and the grant path.

```

### Per-user visibility

Restricted by default: an admitted reader sees only what belongs to them — their own
profile, groups, grants and login attempts — unless a SubjectAccessReview, asked by the app
as its own ServiceAccount and naming the reader and their groups, passes the check below.
An indeterminate review (API error, timeout) always yields the narrow view, never the wide
one, and a revoked administrator keeps the wide view for at most the tier cache TTL (60s)
plus one in-flight page.

| Key | Default | Notes |
|---|---|---|
| `visibility.enabled` | `true` | reaches the app as `GSD_ENABLE_VIEW_RESTRICTIONS` on the Deployment — one wire, and the spelling is load-bearing. **`false` restores everyone-sees-everything**: a deliberate, recorded choice, since it re-exposes the full RBAC binding surface and every person's login failures to any account that can log in. Requires `oauthProxy.enabled` — the chart refuses to render a per-user control with no trusted identity |
| `visibility.adminSar.apiGroup` / `.resource` / `.verb` | `user.openshift.io` / `groups` / `list` | the check a reader must pass to see everything. The default admits `cluster-admin` and `cluster-reader`; `list` `rolebindings.rbac.authorization.k8s.io` also admits cluster-wide `admin`; `edit`/`view` pass no cluster-scoped list at all, and `cluster-edit`/`cluster-view` do not exist as roles. A miscased or versioned shape fails the render — RBAC matching is exact and lowercase, so it would not error at runtime, it would silently demote every administrator |
| `visibility.adminSar.namespace` | `""` | empty = a cluster-scoped check, the normal case. Set it only for a deliberately namespaced threshold such as `get` `pods/log` in `openshift-authentication` |

Grant the wide view through your normal RBAC process, never a chart value:

```
oc adm policy add-cluster-role-to-user  cluster-reader <username>
oc adm policy add-cluster-role-to-group cluster-reader <ldap-group>   # prefer the group form
```

The grant needed by the app itself — `create subjectaccessreviews` — arrives via the stock
`system:auth-delegator` binding, which renders whenever `visibility.enabled` or
`oauthProxy.apiTokenAccess.enabled` is true. A SubjectAccessReview creates no persistent
object, so the ServiceAccount still holds no write verb on anything the dashboard reports on.
```

### Test — `TestViewRestrictions` in `local-development/tests/test_config.py`

```python
class TestViewRestrictions:
    """The per-user visibility switch and the admin-threshold SubjectAccessReview.

    The switch guards personal data, so every failure here must land on the restricted
    side: unknown values, misspelt variables and unusable SAR shapes all leave the
    control ON with the default check, never off and never half-custom.
    """

    def test_restrictions_default_on(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_ENABLE_VIEW_RESTRICTIONS", raising=False)
        assert load_settings(write(tmp_path, BASE)).visibility_enabled is True

    def test_the_env_var_spelled_exactly_disables(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESTRICTIONS", "false")
        assert load_settings(write(tmp_path, BASE)).visibility_enabled is False

    def test_the_operators_original_typo_changes_nothing(self, tmp_path, monkeypatch):
        """GSD_ENABLE_VIEW_RESCRICTIONS — the misspelling that motivated the warning in
        the requirements. A misspelt variable is never read, and the default is ON, so
        the typo cannot silently disable a security control."""
        monkeypatch.delenv("GSD_ENABLE_VIEW_RESTRICTIONS", raising=False)
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESCRICTIONS", "false")
        assert load_settings(write(tmp_path, BASE)).visibility_enabled is True

    def test_a_nonsense_value_stays_restricted(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESTRICTIONS", "maybe")
        assert load_settings(write(tmp_path, BASE)).visibility_enabled is True

    def test_the_configmap_spelling_works_too(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_ENABLE_VIEW_RESTRICTIONS", raising=False)
        s = load_settings(write(tmp_path, BASE + "visibilityEnabled: false\n"))
        assert s.visibility_enabled is False

    def test_admin_sar_defaults_to_list_groups(self, tmp_path):
        s = load_settings(write(tmp_path, BASE))
        assert s.visibility_admin_sar_api_group == "user.openshift.io"
        assert s.visibility_admin_sar_resource == "groups"
        assert s.visibility_admin_sar_subresource == ""
        assert s.visibility_admin_sar_verb == "list"
        assert s.visibility_admin_sar_namespace == ""

    def test_admin_sar_is_read_from_the_configmap_keys(self, tmp_path):
        cfg = BASE + (
            'visibilityAdminSarApiGroup: "rbac.authorization.k8s.io"\n'
            'visibilityAdminSarResource: "rolebindings"\n'
            'visibilityAdminSarVerb: "list"\n'
        )
        s = load_settings(write(tmp_path, cfg))
        assert s.visibility_admin_sar_api_group == "rbac.authorization.k8s.io"
        assert s.visibility_admin_sar_resource == "rolebindings"

    def test_a_subresource_spelling_is_split_for_the_sar_builder(self, tmp_path):
        cfg = BASE + (
            'visibilityAdminSarApiGroup: ""\n'
            'visibilityAdminSarResource: "pods/log"\n'
            'visibilityAdminSarVerb: "get"\n'
            'visibilityAdminSarNamespace: "openshift-authentication"\n'
        )
        s = load_settings(write(tmp_path, cfg))
        assert s.visibility_admin_sar_api_group == ""       # the core group is expressible
        assert s.visibility_admin_sar_resource == "pods"
        assert s.visibility_admin_sar_subresource == "log"
        assert s.visibility_admin_sar_verb == "get"
        assert s.visibility_admin_sar_namespace == "openshift-authentication"

    def test_an_unusable_field_falls_back_to_the_whole_default_check(self, tmp_path):
        """Whole, not per-field: the operator's resource under the default verb would be
        a question nobody chose to ask. And never toward 'everyone passes'."""
        cfg = BASE + (
            'visibilityAdminSarResource: "rolebindings"\n'
            'visibilityAdminSarVerb: "List"\n'   # miscased: RBAC matching is exact
        )
        s = load_settings(write(tmp_path, cfg))
        assert s.visibility_admin_sar_verb == "list"
        assert s.visibility_admin_sar_resource == "groups"  # not rolebindings
        assert s.visibility_admin_sar_api_group == "user.openshift.io"

    def test_a_nil_key_means_not_set_not_empty(self, tmp_path):
        """A hand-written `visibilityAdminSarVerb:` with no value must take the default,
        matching the chart's treatment of a commented-out sub-key."""
        s = load_settings(write(tmp_path, BASE + "visibilityAdminSarVerb:\n"))
        assert s.visibility_admin_sar_verb == "list"

    def test_the_tier_ttl_defaults_to_the_documented_window(self, tmp_path):
        assert load_settings(write(tmp_path, BASE)).visibility_tier_ttl_seconds == 60
```

### Test — `TestVisibilityThreading` in `local-development/tests/test_chart_strategy.py`

```python
class TestVisibilityThreading:
    """visibility.enabled -> GSD_ENABLE_VIEW_RESTRICTIONS, and the adminSar shape.

    The switch is a security control, so the chart must refuse the states in which it
    silently cannot work: a proxy-less deployment (no trusted identity) and a SAR shape
    RBAC would answer `no` to for every viewer (exact, lowercase matching).

    NOTE ON PLACEMENT: `.github/workflows/ci.yml` points the `chart` job at THIS FILE.
    """

    def _docs(self, out):
        import yaml
        return [d for d in yaml.safe_load_all(out) if d]

    def _env(self, out, name):
        for d in self._docs(out):
            if d.get("kind") == "Deployment":
                for c in d["spec"]["template"]["spec"]["containers"]:
                    for e in c.get("env") or []:
                        if e["name"] == name:
                            return e["value"]
        return None

    def _configmap(self, out):
        import yaml
        for d in self._docs(out):
            if d.get("kind") == "ConfigMap" and d["metadata"]["name"].endswith("-config"):
                return yaml.safe_load(d["data"]["clusters.yaml"])
        raise AssertionError("no app ConfigMap in the rendered output")

    def test_restrictions_are_on_by_default_and_spelled_exactly(self):
        ok, out = render()
        assert ok, out
        assert self._env(out, "GSD_ENABLE_VIEW_RESTRICTIONS") == "true"
        # The requirements' typo must not propagate: a misspelt env var here is a
        # silently disabled security control.
        assert "RESCRICTIONS" not in out

    def test_disabling_is_expressible_and_explicit(self):
        ok, out = render(visibility__enabled="false")
        assert ok, out
        assert self._env(out, "GSD_ENABLE_VIEW_RESTRICTIONS") == "false"

    def test_a_nilled_block_keeps_restrictions_on(self):
        """Commenting out the stanza leaves `visibility:` present-but-nil; a bare field
        access panics and a naive `default` flips the control off. Neither may happen."""
        ok, out = render(visibility="null")
        assert ok, out
        assert self._env(out, "GSD_ENABLE_VIEW_RESTRICTIONS") == "true"
        cm = self._configmap(out)
        assert cm["visibilityAdminSarResource"] == "groups"
        assert cm["visibilityAdminSarVerb"] == "list"

    def test_the_sar_shape_reaches_the_configmap(self):
        ok, out = render(**{
            "visibility.adminSar.apiGroup": "rbac.authorization.k8s.io",
            "visibility.adminSar.resource": "rolebindings",
        })
        assert ok, out
        cm = self._configmap(out)
        assert cm["visibilityAdminSarApiGroup"] == "rbac.authorization.k8s.io"
        assert cm["visibilityAdminSarResource"] == "rolebindings"
        assert cm["visibilityAdminSarVerb"] == "list"

    def test_a_nonsensical_sar_shape_is_refused(self):
        """RBAC matching is exact and lowercase, so `List` would not error — it would
        answer no for every viewer and silently demote every administrator."""
        for key, bad in (("verb", "List"), ("resource", "Groups"),
                         ("apiGroup", "user.openshift.io/v1"), ("namespace", "Bad_NS")):
            ok, out = render(**{f"visibility.adminSar.{key}": bad})
            assert not ok, f"adminSar.{key}={bad!r} rendered happily"
            assert "visibility.adminSar" in out

    def test_visibility_without_the_proxy_is_refused(self):
        """No proxy means no trusted identity: X-Forwarded-User is whatever the caller
        typed, so the control cannot work and must not pretend to."""
        ok, out = render(oauthProxy__enabled="false")
        assert not ok, "a per-user control rendered with no authenticated identity"
        assert "requires oauthProxy.enabled=true" in out

    def test_declining_both_is_a_renderable_deliberate_choice(self):
        ok, out = render(oauthProxy__enabled="false", visibility__enabled="false")
        assert ok, out

    def test_the_sar_grant_is_present_on_a_default_install(self):
        """The tier check needs `create subjectaccessreviews`. It arrives via the stock
        system:auth-delegator binding, which used to render only for apiTokenAccess
        (default off) — so a default install would have failed every viewer closed to
        the self tier, permanently and invisibly."""
        ok, out = render()
        assert ok, out
        bindings = [d for d in self._docs(out)
                    if d.get("kind") == "ClusterRoleBinding"
                    and d["roleRef"]["name"] == "system:auth-delegator"]
        assert len(bindings) == 1, "the auth-delegator binding must render for the tier check"
        subject = bindings[0]["subjects"][0]
        assert subject["kind"] == "ServiceAccount"
        assert subject["name"] == "t-group-sync-dashboard"

    def test_the_sar_grant_disappears_when_nothing_needs_it(self):
        ok, out = render(visibility__enabled="false")
        assert ok, out
        assert not any(d.get("kind") == "ClusterRoleBinding"
                       and d["roleRef"]["name"] == "system:auth-delegator"
                       for d in self._docs(out)), (
            "with visibility off and apiTokenAccess off, nothing uses the SAR grant"
        )

    def test_notes_carry_the_grant_command_and_the_rollback_flag(self):
        notes = (CHART / "templates" / "NOTES.txt").read_text()
        assert "oc adm policy add-cluster-role-to-user cluster-reader" in notes
        assert "visibility.enabled=false" in notes
```

**Risks it names.** WHAT WAS VERIFIED, AND HOW FAR IT REACHES. Every snippet below was applied to a full mirror of the worktree and verified: `helm template`/`helm install --dry-run=client` across defaults, disabled, whole-block nil, per-key nil, core-group/subresource/namespaced custom shapes, four refused shapes, proxy-off refusal, and both NOTES branches; the full suite ran green at 1099 passed / 1 skipped (measured worktree baseline: 1078 passed, 1 skipped — the task's stated 1057 is stale; the +21 delta is exactly the 21 new tests). Sprig semantics (`toString nil` -> "<nil>", `kindIs "invalid"` for nil leaves, `--set visibility=null`) were measured on helm v3.14.0 specifically; other helm 3.x versions are expected to match but were not measured. WHAT THIS CANNOT GUARANTEE: (1) The auth-delegator binding now renders on a DEFAULT install — verified necessary, because rbac.yaml gated it on apiTokenAccess.enabled (default false), so a default install had NO `create subjectaccessreviews` and every reader would have failed closed to self forever; on the reference deployment (environments/crc.yaml sets apiTokenAccess.enabled=true) the grant already exists. The alternative — a bare `create subjectaccessreviews` rule in the reader ClusterRole — was rejected because the in-tree test `test_the_only_write_in_the_role_is_the_dashboards_own_lease` pins the reader role's sole write verb to leases; the stock-role binding passes that test (verified) and matches rbac.yaml's own auditor-recognises-the-grant reasoning, at the cost of also granting `create tokenreviews`, which the app never calls. Whether the SA's projected token can actually create a SAR in-pod must still be proven by the live smoke test the other lenses name. (2) The render guard breaks `helm upgrade` for any existing deployment running oauthProxy.enabled=false until the operator sets visibility.enabled=false explicitly — deliberate (the control is unsatisfiable without a trusted identity, per spec Q8's interlock), and both shipped environments files keep the proxy on (checked), but an unknown consumer with the proxy off will hit it. (3) The staleness window stated in values.yaml, config.py and the README — 60s tier-cache TTL plus one in-flight page, with groups from a fresh read on cache miss — is a CONTRACT for the lens-1/2 resolver, threaded here as Settings.visibility_tier_ttl_seconds; if the arbiter adopts the poll-snapshot design instead, the window statements must be rewritten to pollIntervalSeconds + TTL in all three places, or they become false documentation of a security property. (4) The NOTES claim "stock cluster-reader passes every threshold measured for this feature" is bounded by the D2 matrix (list groups / list users / list CRBs / list rolebindings / get pods/log in openshift-authentication); an operator's custom CRD-based check is outside it. (5) apiGroup is validated for shape (lowercase DNS-ish, no version suffix) but not for existence — a misspelt-yet-lowercase group fails closed at runtime with every reader self, visible only via the admins-see-self symptom the other lenses' logging must surface. (6) `visibilityEnabled` is deliberately NOT rendered into the ConfigMap (one wire, on the Deployment); config.py still reads the yaml key for local development, and the env var wins — a hand-edited ConfigMap key on a chart install is therefore inert by design, which the configmap.yaml comment states.


## UI labelling and tests

**What it reports.** Lens 4 of the per-user-visibility spec: how a narrowed view is labelled, and the complete test list. I read both docs in full (requirements + decisions D1/D2, spec with its arbitration), api.py (all 1,127 lines — the /api/dashboard/activity scope_to precedent and the whoami proxy gate), config.py (_bool_setting/_visibility_setting fail directions), index.html (all 2,493 lines), app.css (all 743), store.py's sync_members event semantics, and the test idioms in test_ui.py, test_activity.py, test_config.py, test_accessibility.py, test_chart_strategy.py. Everything shipped below was executed before being written into the spec: the test seed ran against the real Store (alice={g-adm,gate}, bob={g-dev}, dangling finding, gate membership {alice:True,bob:False}); the live app on that seed confirmed the premises (alert kinds auth_failed/dangling_binding/direct_user_binding/reconcile_error, logins distinct_users=3, cluster-access full shape); all 19 index.html anchors were grep-verified unique, the edits applied by script to a copy, and the assembled 150,673-byte page script parses under node --check with every original function intact; the CSS block merged into app.css passes the new token-only check and the type-scale rule; the whoami replacement compiles merged into api.py; all four Python test additions compile. UI design: a header #scope-pill driven by whoami's new visibility field ("Your view — <user>" / "Full view — you are seeing everything" / "Full view — restrictions are off for this deployment" — the admin marker is explicit text, not the absence of a banner); per-tab .scope-banner rendered ONLY when the response declares scope=self (Groups: membership + viewer name; Logins: own attempts + the as-typed caveat for the byte-exact match; Namespace audit: own grants, cluster KPIs dropped per Q5); designed 403s (findings, non-member group/user detail) become .scope-refusal named-refusal cards ("Withheld, not empty…"), never blanks and never the generic error card, with back buttons on drill-downs and no existence oracle in the wording; scoped empty states distinguish "nothing of yours (signed in as X)" from "none exist". The UI reads scope/viewer/403 off the wire exclusively — the search-box scar is encoded as the no-declaration-no-label regression test. Tests delivered per the task list: two-tier assertions per endpoint (groups/users/user detail/logins/user-bindings/membership-changes/cluster-access/findings/alerts/groupsyncs/overview), the fail-closed test (exploding resolver → 200 + self view, never 500 or wide), the group-granted-admin SAR test that reproduces the john.doe inversion (a fake RBAC that only allows when spec.groups carries the group), the stale-removal window test (revoked admin keeps "all" for at most ttl_seconds under an injected clock), the env-var tests including the pinned no-op of the operator's RESCRICTIONS typo, the render guards, and the Playwright labelling suite. File placement: tests/test_visibility.py (new), TestViewRestrictions appended to tests/test_config.py, the scoped_server fixture + TestVisibilityLabels appended to tests/test_ui.py, one token-only test appended to tests/test_accessibility.py. On the RBAC question the task asked about: lens 1's measurement stands — `create subjectaccessreviews` via system:auth-delegator is sufficient and adds no write verb (a SAR persists nothing), BUT the chart renders that binding only when apiTokenAccess.enabled (default false), so the operator-surface lens must grant it whenever visibility is on; no chart tests are duplicated here.

### `local-development/gsd/static/index.html`

**Anchor.** `<h1>OCP Access Control Dashboard<span id="scope-note"></span></h1>`

**Purpose.** INSERT AFTER the anchor line: the header mount for the tier pill — present on every tab, hidden until the wire declares a tier. This is the element the render-guard test asserts exists-but-hidden when nothing is declared.

```
    <!-- The visibility tier, as /api/whoami reports it. Populated by renderScopePill()
         and hidden until the wire declares a tier: the page labels what the server
         decided and never decides for itself. -->
    <span class="scope-pill" id="scope-pill" hidden></span>
```

### `local-development/gsd/static/index.html`

**Anchor.** `group: null, user: null, logins: null, access: null };`

**Purpose.** REPLACES the anchor line (the closing line of the `data` declaration): two new slots for what the wire declared.

```
             group: null, user: null, logins: null, access: null,
             /* Identity + tier as the server reports them (whoami), and the scope the
                groups response declared. Rendering reads these; nothing writes them but
                the wire. */
             whoami: null, groupsMeta: null };
```

### `local-development/gsd/static/index.html`

**Anchor.** `/* ---------- rendering ---------- */`

**Purpose.** INSERT AFTER the anchor line: the whole visibility-labelling toolkit — guard403 (absorbs a DESIGNED 403 into a marker, the Usage-tab pattern generalised), the header pill, the per-tab self banners, the named-refusal card, and the two scoped sub-views (cluster access, own grants). Everything renders from scope/viewer fields or a 403 the server sent; nothing decides a tier.

```

/* ── Visibility: the tier as the WIRE declares it ─────────────────────────────────────────
   The server decides who sees everything and who sees only their own slice, and every
   scoped response says which it did (`scope` + `viewer` — the /api/dashboard/activity
   contract, generalised). Everything below RENDERS those declarations and decides
   nothing: this page once shipped a search box that claimed credit for hiding rows it was
   not hiding, and a banner that guessed at the tier would be that defect with security
   consequences. No declaration on the wire, no label on the page. */

/* Absorb a DESIGNED 403 into a marker the renderer can phrase — the Usage tab's pattern
   for its proxy-off refusal, generalised. Only 403: a 500 is a fault and must still look
   like one. */
async function guard403(promise) {
  try { return await promise; }
  catch (e) {
    if (e.status !== 403) throw e;
    return { forbidden: true };
  }
}

/* Header pill: the one place the ADMINISTRATOR is told they are seeing everything. A
   narrowed reader gets per-tab banners as well; the wide reader gets only this, because
   "nothing looks different" and "you are seeing everything" are different statements and
   only the second is checkable from the screen. Driven by whoami's `visibility`, which
   the server computes — hidden entirely when the wire declares nothing (an older build,
   or no authenticated identity worth reporting). */
function renderScopePill() {
  const pill = $("scope-pill");
  if (!pill) return;
  const w = data.whoami;
  const vis = w && w.authenticated && w.visibility;
  if (!vis) { pill.hidden = true; pill.textContent = ""; return; }
  const self = vis.scope === "self";
  pill.hidden = false;
  pill.classList.toggle("self", self);
  pill.classList.toggle("full", !self);
  // textContent, not innerHTML: the username is caller-adjacent data and this element
  // needs no markup, so the cheapest sink is also the safe one.
  pill.textContent = self
    ? `Your view — ${w.user}`
    : (vis.enabled === false
        ? "Full view — restrictions are off for this deployment"
        : "Full view — you are seeing everything");
  pill.title = self
    ? "Every list here is scoped to you on the server: your groups, your grants, your "
      + "sign-in attempts. An administrator sees the whole cluster; the grant that widens "
      + "a view is documented in the chart README."
    : (vis.enabled === false
        ? "visibility.enabled is false, so every authenticated reader sees everything — "
          + "a deliberate deployment choice, not a grant your account holds."
        : "Your account holds the cluster permission this deployment treats as the "
          + "administrator tier, so nothing here is scoped down.");
}

/* Per-tab wording for a narrowed view: one sentence naming WHAT is scoped and to WHOM. A
   page that silently shows two rows where an administrator sees two hundred invites the
   reader to conclude the cluster is nearly empty (requirements Q6), so the banner sits at
   the top of the lead card, above the data it qualifies — the Usage tab's shipped
   position. Rendered ONLY when the response itself declares scope=self. */
const SCOPE_BANNER = {
  groups: (v) => `Showing only the groups <strong>${esc(v)}</strong> belongs to. The
    cluster-wide list is the administrator tier.`,
  logins: (v) => `Showing only sign-in attempts recorded for <strong>${esc(v)}</strong>.
    Attempts are recorded under the name <em>as typed</em>, so an attempt typed with
    different capitalisation is a different name and is not shown here.`,
  grants: (v) => `Showing only roles granted directly to <strong>${esc(v)}</strong>. The
    per-namespace audit of everyone's grants is the administrator tier.`,
};

function scopeBanner(kind, d) {
  if (!d || d.scope !== "self") return "";
  const words = SCOPE_BANNER[kind];
  if (!words) return "";
  return `<div class="filterbar-note scope-banner">${words(d.viewer || "you")}</div>`;
}

/* A withheld view is a NAMED refusal, never a blank: an empty audit tab reads as a
   healthy cluster, which is a lie of layout. Says what exists, why it is not shown, and
   what changes that. `withBack` for drill-downs, so a refusal is a detour rather than a
   dead end — the same rule the error card follows. */
function refusalCard(title, what, withBack) {
  return `<section class="card">
    ${withBack ? `<button class="back" id="back-groups">${backLabel()}</button>` : ""}
    <h2${withBack ? ' style="margin-top:10px"' : ""}>${esc(title)}</h2>
    <div class="scope-refusal"><strong>Withheld, not empty.</strong> ${what}
      Your account does not hold the cluster permission this deployment treats as the
      administrator tier, so this view is reserved — an administrator sees it in full,
      and nothing on this page is broken. The grant that widens it (stock
      <code>cluster-reader</code>, unless this deployment configured another check) is
      documented in the chart README.</div>
  </section>`;
}

/* Cluster access, scoped to the viewer: their OWN admission status and nothing else —
   the gate DN is directory structure and the member lists are other people's data.
   `in_gate` is three-valued for the same reason the wide panel's rows are: false is a
   statement, unknown is the absence of one, and rendering unknown as false would assert
   a non-membership the data cannot support. */
function accessSelfCard(d) {
  if (!d.gated) {
    return `<section class="card">
      <h2>Your cluster access</h2>
      <div class="empty-note">No login gate is configured on this cluster, so there is no
        gate membership to report — any account the identity provider matches can sign
        in.</div>
    </section>`;
  }
  const badge = d.in_gate === true
    ? `<span class="badge ok"><span class="glyph" aria-hidden="true"></span>in the login gate group</span>`
    : d.in_gate === false
      ? `<span class="badge warning"><span class="glyph" aria-hidden="true"></span>not in the login gate group</span>`
      : `<span class="badge unknown"><span class="glyph" aria-hidden="true"></span>cannot tell</span>`;
  return `<section class="card">
    <div class="section-head"><h2>Your cluster access</h2><span class="flush"></span>${badge}</div>
    <div class="filterbar-note" style="margin-top:8px">
      ${d.in_gate === false
        ? `Membership of the gate group <code>${esc(d.group_name || "")}</code> is required
           to sign in, and you are not in it — any access you hold cannot be used until
           you are.`
        : d.in_gate === true
          ? `Membership of <code>${esc(d.group_name || "")}</code> is what allows you to
             sign in to this cluster.`
          : `The gate group is known but not synced onto this cluster, so there is no
             membership to check yours against.`}
      Who else is or is not in the gate group is the administrator tier.
    </div>
  </section>`;
}

/* Namespace audit, scoped to the viewer: their own direct grants and no cluster KPIs.
   "People exposed" or "Namespaces at risk" recomputed over one person keeps its label and
   changes its meaning — the count-versus-page defect made permanent (requirements Q5) —
   so none of the wide view's aggregates render here at all. */
function selfGrantsView(ub) {
  const rows = ub.bindings || [];
  return `<section class="card">
    <h2>Namespace audit</h2>
    ${scopeBanner("grants", ub)}
    ${rows.length === 0
      ? `<div class="empty-note">No role is granted directly to
           <strong>${esc(ub.viewer || "you")}</strong> on this cluster. Your access, if
           any, arrives through synced groups — the goal state this audit exists to reach.
           This says nothing about whether OTHER accounts hold direct grants; that
           worklist is the administrator tier.</div>`
      : `<div class="scroll-x"><table>
          <thead><tr><th>Grants</th><th>Scope</th><th>Binding</th></tr></thead>
          <tbody>${rows.map((b) => `<tr>
            <td><code class="priv">${esc(b.role_name)}</code>
              <span class="muted">${esc(b.role_kind)}</span></td>
            <td>${b.binding_namespace ? esc(b.binding_namespace)
                  : `<strong class="err">cluster-wide</strong>`}</td>
            <td class="muted">${esc(b.binding_name)}</td>
          </tr>`).join("")}</tbody>
        </table></div>
        <div class="filterbar-note" style="margin-top:8px">
          A direct grant survives offboarding. Consider asking for the equivalent group
          membership and having the binding removed — the runbook on the administrator's
          view of this tab is the same one that applies to yours.</div>`}
  </section>`;
}
```

### `local-development/gsd/static/index.html`

**Anchor.** `function groupsPage() {`

**Purpose.** REPLACES the entire groupsPage function, from the anchor line through its closing brace. Adds the self banner (rendered only from the declared scope) and the scoped empty state that distinguishes 'nothing of yours' from 'none exist'; the search/filter logic and the table are unchanged. Verified: the whole modified page script parses under node --check.

```
function groupsPage() {
  // The whole list before the search narrows it, so the header can report what was hidden. A filtered
  // view that cannot state its own denominator has the same defect as a truncated page that cannot:
  // the reader cannot tell "there is one" from "there is one THAT MATCHES".
  const all = data.groups;
  // `scope`/`viewer` as the response declared them (kept beside the rows in refresh()).
  // The banner and the scoped empty state render from these fields and never from a
  // guess — the search-box scar, applied to a security label.
  const meta = data.groupsMeta || {};
  const self = meta.scope === "self";
  const rows = all.filter((g) => matchesGroupSearch(g.name, view.groupSearch));
  const searching = (view.groupSearch || "").trim().length > 0;
  const note = {
    empty: "Zero members, so the group grants nobody. On an operator-synced group that usually means an LDAP-side problem — a member DN that does not resolve. Includes hand-made groups, which also appear under unattributed.",
    unattributed: "No sync-provider label, so not managed by any GroupSync CR.",
    all: "",
  }[view.groupFilter];
  return `<section class="card">
    <h2>Groups <span class="muted" style="font-weight:400">· ${searching
      ? `${rows.length} of ${all.length} shown`
      : `${rows.length} shown`}</span></h2>
    ${scopeBanner("groups", meta)}
    ${note ? `<div class="filterbar-note" style="margin-top:4px">${esc(note)}</div>` : ""}
    ${searching ? `<div class="filterbar-note" style="margin-top:4px">Filtered by
      <strong>${esc(view.groupSearch.trim())}</strong> — every word must appear in the name.${all.length > 0
      // Same zero-denominator honesty as the empty state below: with nothing behind the search,
      // "clear the box to see all 0" invites the reader to clear it and get the same empty table.
      ? ` Clear the box, or press Escape in it, to see all ${all.length}.` : ""}</div>` : ""}
    ${rows.length === 0
      ? (searching && all.length > 0
          // Only blame the search when it IS the search: with a zero denominator the state filter
          // (or the cluster) has nothing to show, and "the search is hiding them" would be false —
          // the reader would clear their query expecting rows and get none.
          ? `<div class="empty-note">No group name contains
              <strong>${esc(view.groupSearch.trim())}</strong>. ${all.length === 1
              ? `1 group matches the state filter, so it is the search hiding it`
              : `${all.length} groups match the state filter, so it is the search hiding them`}
              rather than the data being empty.</div>`
          : (self && !searching && view.groupFilter === "all"
              // Scoped-and-empty is NOT an empty cluster, and the two must never share a
              // sentence (requirements Q6). Naming the viewer is deliberate twice over: it
              // is also the on-screen diagnostic when the IdP's username does not match
              // the names the sync operator writes into members.
              ? `<div class="empty-note">You are not a member of any synced group on this
                  cluster (signed in as <strong>${esc(meta.viewer || "")}</strong>). This
                  view is scoped to you — it is not a statement that the cluster has no
                  groups.</div>`
              : `<div class="empty-note">No groups match this filter.</div>`))
      : `<div class="scroll-x"><table>
          <thead><tr><th>Name</th><th class="num">Members</th><th>Owner</th>
            <th>Last refreshed</th><th>Source DN</th></tr></thead>
          <tbody>${rows.map((g) => `<tr class="rowlink" data-group="${esc(g.name)}">
            <td>${esc(g.name)}</td>
            <td class="num">${g.member_count}</td>
            <td>${ownerCell(g.sync_provider)}</td>
            <td class="mono">${esc(ago(g.group_synced_at))}</td>
            <td class="muted"><code>${esc(g.ldap_uid || "—")}</code></td>
          </tr>`).join("")}</tbody>
        </table></div>
        <div class="filterbar-note" style="margin-top:8px">Select a group to see its members.</div>`}
  </section>`;
}
```

### `local-development/gsd/static/index.html`

**Anchor.** `function captureSection(d, access) {`

**Purpose.** REPLACES the entire captureSection function, from the anchor line through its closing brace. At scope=self: the banner (with the as-typed caveat), a personal hero (the viewer's own attempt count — never zeros standing in for the suppressed whole-record summary), a scoped zero-state, the ungoverned-accounts card dropped, and the chronology retitled 'Your attempts'. The wide tier renders byte-identically to today. Capture-health notes (window, stalled) stay at both tiers — they describe the record, not a person.

```
function captureSection(d, access) {
  // Scope as the RESPONSE declares it. At "self" the record on screen is the viewer's own
  // slice: the whole-record summary and the ungoverned-accounts finding are not in the
  // payload at all, and nothing here may compute a stand-in — "accounts in no synced
  // group: 0" recomputed over one person would be the count-versus-page defect made
  // permanent (requirements Q5).
  const self = d.scope === "self";
  // Off is a DIFFERENT state from on-and-quiet, and conflating them sends the reader hunting
  // for logins that were never going to be recorded. Both halves are named because either one
  // alone records nothing: the module has to be running, and the operand has to be verbose.
  if (!d.enabled) {
    return `<section class="card">
      <h2>Login attempts</h2>
      <div class="empty-note">
        Not being captured. This needs <strong>both</strong>
        <code>config.loginCapture.enabled=true</code> — the module that reads the log — and the
        authentication <em>operator</em> at <code>spec.logLevel: Debug</code>, which is what
        makes the oauth-server write a username at all. At the default verbosity the lines this
        page parses do not exist, so capture would run and find nothing.
      </div>
      <div class="filterbar-note">Both are one <code>helm upgrade</code>:
        <code>loginCapture.enabled</code> and <code>authLogLevel.manage</code>. See
        <code>docs/LOGIN_CAPTURE_QUICKCHECK.md</code> for the five commands that prove the path
        end to end.</div>
    </section>` + access;
  }

  const s = d.summary || {};
  const rows = d.attempts || [];
  const ungoverned = d.ungoverned || [];

  // Overdue is measured against the cadence the SERVER reports, not a number invented here:
  // capture rides the poll thread, so `last_read_at` should advance every poll interval. Five
  // intervals is late beyond argument, with a 5-minute floor so a fast poll does not raise this
  // on one slow cycle. The threshold is stated on screen rather than implied by a red badge.
  const interval = d.read_interval_seconds || 60;
  const staleAfter = Math.max(300, interval * 5);
  const readAge = d.last_read_at
    ? Math.floor((Date.now() - new Date(d.last_read_at).getTime()) / 1000) : null;
  const stalled = readAge !== null && readAge > staleAfter;

  // Compared as INSTANTS, not as strings, and with a second of tolerance. The two fields do not
  // share a format: `capture_started_at` is stamped by now_iso() to whole seconds, while
  // `retained_since` is an attempt's `at` and carries microseconds. Lexicographically "…:00.5Z"
  // sorts BEFORE "…:00Z" ('.' < 'Z'), so a string compare would announce that the record
  // predates capture whenever the first attempt landed in the same second the watch began.
  const startedMs = d.capture_started_at ? new Date(d.capture_started_at).getTime() : NaN;
  const retainedMs = d.retained_since ? new Date(d.retained_since).getTime() : NaN;
  const predatesStart = retainedMs < startedMs - 1000;

  // Each edge is stated only when it HAS a value. Before the first successful read all three are
  // null, and "Watching since —. Oldest attempt still retained —. Last read —." is three em-dashes
  // of noise in front of the one sentence that state actually needs. The caveat below them is
  // unconditional, because it is true in every state and is the whole point of the banner.
  const edges = [
    d.capture_started_at
      && `Watching since <strong>${esc(fmtTime(d.capture_started_at))}</strong> (${
           esc(ago(d.capture_started_at))})`,
    d.retained_since
      && `oldest attempt still retained <strong>${esc(fmtTime(d.retained_since))}</strong>`,
    d.last_read_at
      && `last read <strong>${esc(fmtTime(d.last_read_at))}</strong> (${
           esc(ago(d.last_read_at))})`,
  ].filter(Boolean);
  const window_ = `<div class="filterbar-note" style="margin-top:8px">
    ${edges.length ? edges.join("; ") + "." : ""}
    Nothing before capture began was ever recorded — the oauth-server's log dies with its pod and
    cannot be read backwards — so an empty list here means nothing was <em>observed</em>, never
    that nobody signed in.
    ${predatesStart
      ? `The oldest attempt predates the first read because that read looked back an hour, which
         is expected rather than a fault.` : ""}
  </div>`;

  const stalledNote = stalled
    ? `<div class="truncation-note">
        <strong>Capture has stopped.</strong> The last successful read was
        ${esc(ago(d.last_read_at))}, and reads are expected every ${interval}s — anything past
        ${Math.round(staleAfter / 60)} minutes is overdue. Attempts made since then are being
        lost, and they cannot be recovered later. Check the dashboard pod's log for a refused
        <code>pods/log</code> read, and that an oauth-server pod is Running.
      </div>` : "";

  // Nothing recorded yet is the state most likely to be MISREAD, so it gets the whole card and
  // says which of the three reasons applies rather than leaving the reader to guess. At the
  // narrowed tier "no rows" means no rows FOR YOU — the two operational diagnoses below answer
  // a question the scoped reader did not ask, so the scoped state says whose record is empty
  // instead, and the capture-health note still carries the operational truth.
  if (!d.total) {
    return `<section class="card">
      <h2>Login attempts</h2>
      ${scopeBanner("logins", d)}
      ${self
        ? `<div class="empty-note">No sign-in attempts recorded for
            <strong>${esc(d.viewer || "you")}</strong> since capture began. This view is
            scoped to you; it says nothing about whether anyone else signed in.</div>`
        : d.last_read_at ? `<div class="empty-note">
          Reads are working — the log was last read ${esc(ago(d.last_read_at))} — and
          <strong>no login lines matched</strong>. Either nobody has signed in since watching
          began, or the authentication operator is not at Debug, in which case the oauth-server
          never writes a username. One command decides which:
          <code>oc get authentications.operator.openshift.io cluster -o jsonpath='{.spec.logLevel}'</code>
          must print <code>Debug</code>.
        </div>`
        : `<div class="empty-note">
          <strong>No successful read yet.</strong> Capture is enabled but has not managed to
          read a log, so this is a cluster-access problem rather than a quiet one. The
          dashboard's ServiceAccount needs <code>pods</code> list and the
          <code>pods/log</code> subresource in the oauth-server's namespace
          (<code>openshift-authentication</code> unless configured otherwise), and at least one
          oauth-server pod has to be Running. Note that
          <code>oc auth can-i get pods/log</code> answers <code>no</code> even on a correct
          grant — it reads <code>pods/log</code> as a resource <em>name</em>. Use
          <code>--subresource=log</code>.
        </div>`}
      ${stalledNote}
      ${window_}
    </section>` + access;
  }

  const failures = s.failures || 0;
  const ungovernedCount = s.ungoverned_users || 0;
  // The hero is the finding, not the volume — at the wide tier. At the narrowed tier the
  // finding is withheld along with the rest of the whole-record numbers, so the hero is
  // the one number that IS the viewer's: their own attempt count. No zeros stand in for
  // the suppressed summary — a zero with the old label would be a lie with an axis.
  const headline = self
    ? `<div class="hero">
      <span class="value mono">${(d.total || 0).toLocaleString()}</span>
      <span class="label">sign-in attempt${d.total === 1 ? "" : "s"} recorded for you</span>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="label">Most recent</div>
        <div class="value mono muted" style="font-size:var(--text-lg)">${
          esc(rows[0] ? ago(rows[0].at) : "—")}</div></div>
    </div>`
    : `<div class="hero">
      <span class="value mono">${ungovernedCount}</span>
      <span class="label">${ungovernedCount
        ? `${ungovernedCount === 1 ? "account" : "accounts"} in no synced group`
        : "every account seen is in a synced group"}</span>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="label">Attempts</div>
        <div class="value mono">${(d.total || 0).toLocaleString()}</div></div>
      <div class="kpi"><div class="label">Distinct users</div>
        <div class="value mono">${s.distinct_users || 0}</div></div>
      <div class="kpi"><div class="label">Signed in</div>
        <div class="value mono">${(s.successes || 0).toLocaleString()}</div></div>
      <div class="kpi ${failures ? "flag-warning" : ""}"><div class="label">Failed</div>
        <div class="value mono ${failures ? "" : "muted"}">${failures.toLocaleString()}</div></div>
      <div class="kpi"><div class="label">Most recent</div>
        <div class="value mono muted" style="font-size:var(--text-lg)">${esc(ago(s.last_at))}</div></div>
    </div>`;
  return `<section class="card">
    <h2>Login attempts</h2>
    ${scopeBanner("logins", d)}
    ${headline}
    ${stalledNote}
    ${window_}
  </section>
  ${access}
  ${self ? "" : ungovernedCard(d, ungoverned)}
  <section class="card">
    <div class="section-head"><h3>${self ? "Your attempts" : "Every attempt"}</h3><span class="flush"></span>
      ${view.loginOutcome !== "all"
        ? `<span class="chip">filtered to ${esc(OUTCOME_LABEL[view.loginOutcome]
            || view.loginOutcome)}</span>` : ""}
    </div>
    ${rows.length === 0
      ? `<div class="empty-note">No attempt matches this filter. The counts above cover the
           whole record, not this view.</div>`
      : `<div class="scroll-x"><table>
          <thead><tr><th>When</th><th>User</th><th>Outcome</th><th>Provider</th>
            <th>Detail</th><th>Replica</th></tr></thead>
          <tbody>${rows.map((r) => `<tr>
            <td class="mono" style="white-space:nowrap">${esc(fmtTime(r.at))}</td>
            <td>${loginUser(r)}${r.in_access_group === false && !r.break_glass
              ? ` <span class="chip" title="Not a member of the login-gate group, so this account cannot authenticate at all. With that known, a `+"`"+`no match`+"`"+` here is a real person outside the group rather than a username that does not exist.">not in access group</span>`
              : ""}${r.break_glass
              ? ` <span class="chip" title="${r.outcome === "success"
                  ? "A break-glass sign-in: a local HTPasswd account, not a directory identity, so there is no synced group to govern it and nobody to offboard."
                  : "An attempt against the local HTPasswd provider. The name may not exist — HTPasswd reports no reason — so this says which provider was tried and nothing about the account."}">${
                  r.outcome === "success" ? "break-glass" : "local provider"}</span>`
              : (r.known_user ? "" : ` <span class="chip">${r.has_history
                  ? "removed from every group" : "no synced group"}</span>`)}</td>
            <td>${outcomeBadge(r.outcome)}${refusalBadge(r.refusal_reason)}</td>
            <td class="mono muted">${esc(r.provider || "—")}</td>
            <td class="muted">${esc(r.detail || "")}${r.ldap_result_code != null
              ? ` <span class="mono">(LDAP ${r.ldap_result_code})</span>` : ""}</td>
            <td class="mono muted" style="white-space:nowrap">${
              esc((r.pod_name || "").replace(/^oauth-openshift-/, ""))}</td>
          </tr>`).join("")}</tbody>
        </table></div>`}
    ${d.truncated ? `<div class="truncation-note">
      Showing the <strong>${rows.length}</strong> most recent of <strong>${d.total}</strong>
      retained attempts. Every number above covers all of them.
    </div>` : ""}
    <div class="filterbar-note" style="margin-top:8px">
      <strong>No match</strong> covers two cases this log cannot separate: a real person who is
      not in the login-gate group, and a username that does not exist. The identity provider's
      search filter carries the gate group, so both produce the same
      <code>no entries matching</code> line — telling them apart from the log alone would need a
      directory read this dashboard does not make. Where a <strong>second badge</strong> appears
      beside it, that ambiguity HAS been resolved, from synced group membership rather than from any
      new read: hover it for the reasoning. Where no second badge appears, no login gate is known and
      the honest answer is still that we cannot tell.
      <strong>Detail</strong> is the directory's own diagnostic, passed through rather than
      interpreted. On Active Directory it carries a <code>data &lt;hex&gt;</code> sub-code, which
      is what distinguishes an expired password from a locked account — the LDAP result code
      alone does not: <code>49</code> is returned for all of them. OpenLDAP leaves the field
      empty and signals expiry with code <code>53</code> instead.
      <strong>Replica</strong> is which oauth-server pod saw it, with the common prefix trimmed;
      the two replicas serve different attempts, so a name here is the pod whose log to read.
    </div>
  </section>`;
}
```

### `local-development/gsd/static/index.html`

**Anchor.** `// No gate at all. A finding in itself rather than an absence, and stated as one: with no membership`

**Purpose.** INSERT BEFORE the anchor line (inside accessCard, after its Loading guard): dispatch the scoped cluster-access shape to its own renderer.

```
  // The narrowed shape, declared by the response itself: the viewer's own gate status,
  // rendered without the DN, the lists or the summary the payload no longer carries.
  if (d.scope === "self") return accessSelfCard(d);
```

### `local-development/gsd/static/index.html`

**Anchor.** `const d = data.findings;`

**Purpose.** INSERT AFTER the anchor line (top of bindingsPage): render the Access-granted tab's designed 403 as a named refusal.

```
  // A DESIGNED 403 (the binding surface is the administrator tier), phrased — never the
  // generic error card, and never a blank that reads as a healthy cluster.
  if (d && d.forbidden) {
    return refusalCard("Access granted",
      `Every group-subject binding on this cluster — who has been granted what — is the
       cluster's RBAC surface.`);
  }
```

### `local-development/gsd/static/index.html`

**Anchor.** `const oc = data.operatorConfigs;`

**Purpose.** INSERT AFTER the anchor line (top of policyPage): the findings refusal, with the governance-visible CR health still rendered beneath it.

```
  // The findings 403 is DESIGNED; the CR health beside it is governance data and still
  // renders. A named refusal, never a blank — an empty policy tab reads as "nothing
  // bypasses the policy system", which at the narrowed tier is not knowledge anyone has.
  if (data.findings && data.findings.forbidden) {
    return refusalCard("RBAC policy",
      `The grants that bypass the policy system name other people's access.`)
      + configHealth(oc);
  }
```

### `local-development/gsd/static/index.html`

**Anchor.** `function nsAuditPage() {`

**Purpose.** REPLACES the entire nsAuditPage function, from the anchor line through its closing brace (the block comment above the function stays — it still applies). Dispatches on what the wire declared: a scoped payload renders the viewer's own grants, a designed 403 a named refusal, everything else today's audit.

```
function nsAuditPage() {
  const ub = data.userBindings;
  if (!ub) return `<section class="card"><div class="empty-note">Loading…</div></section>`;
  // Both narrowed shapes are the SERVER's call, read off the wire: a scoped payload
  // renders the viewer's own grants, a designed 403 a named refusal. The page never
  // decides which applies.
  if (ub.forbidden) return refusalCard("Namespace audit",
    `The per-namespace worklist of direct user grants names people and their access.`);
  if (ub.scope === "self") return selfGrantsView(ub);
  return directUserGrants(ub);
}
```

### `local-development/gsd/static/index.html`

**Anchor.** `const d = data.group;`

**Purpose.** INSERT AFTER the anchor line (top of groupDetail): the constant-403 refusal, with a working back affordance and wording that refuses to guess existence.

```
  // A DESIGNED refusal: at the narrowed tier a group outside your membership answers a
  // 403 that is byte-identical for a real group and a nonexistent one — no existence
  // oracle — so this card must not claim to know which it was.
  if (d && d.forbidden) {
    return refusalCard(view.group || "This group",
      `Only groups you belong to are visible at your tier. This one is outside your view —
       or does not exist; the two are deliberately indistinguishable.`, true);
  }
```

### `local-development/gsd/static/index.html`

**Anchor.** `const d = data.user;`

**Purpose.** INSERT AFTER the anchor line (top of userDetail): the own-profile-only refusal.

```
  if (d && d.forbidden) {
    return refusalCard(view.user || "This user",
      `Only your own profile is visible at your tier.`, true);
  }
```

### `local-development/gsd/static/index.html`

**Anchor.** `main.classList.remove("stale");`

**Purpose.** INSERT BEFORE the anchor line (end of render()): repaint the header pill with every render.

```
  // After the page, so a refusal card and the pill can never disagree about the tier
  // within one paint.
  renderScopePill();
```

### `local-development/gsd/static/index.html`

**Anchor.** `data.clusters = await get("/api/clusters");`

**Purpose.** INSERT BEFORE the anchor line (inside refresh()): fetch whoami each cycle so the pill follows a tier change instead of the page's memory of it.

```
    // Refetched every cycle, unlike /api/version: the tier can change under a running
    // tab (a grant made or revoked), and the pill must follow the wire rather than the
    // page's memory of it. Cheap — no store read behind it.
    try {
      data.whoami = await get("/api/whoami");
    } catch (e) { data.whoami = null; }
```

### `local-development/gsd/static/index.html`

**Anchor.** `data.groups = got;`

**Purpose.** REPLACES the anchor line: the groups response is now an object carrying its rows and its declared scope; keep them together so the banner can only say what the server said.

```
          // Rows and their declared scope travel together; the banner renders from
          // `groupsMeta` and never from a client-side guess.
          data.groups = got.groups;
          data.groupsMeta = { scope: got.scope, viewer: got.viewer };
```

### `local-development/gsd/static/index.html`

**Anchor.** `const got = await get(`${base}/users/${encodeURIComponent(view.user)}`);`

**Purpose.** REPLACES the anchor line: absorb the designed 403 on a user drill-down.

```
          const got = await guard403(get(`${base}/users/${encodeURIComponent(view.user)}`));
```

### `local-development/gsd/static/index.html`

**Anchor.** `const got = await get(`${base}/groups/${encodeURIComponent(view.group)}`);`

**Purpose.** REPLACES the anchor line: absorb the designed 403 on a group drill-down.

```
          const got = await guard403(get(`${base}/groups/${encodeURIComponent(view.group)}`));
```

### `local-development/gsd/static/index.html`

**Anchor.** `data.findings = await get(`

**Purpose.** REPLACES the anchor line AND its continuation line directly below (the two-line statement fetching bindings/findings on the Access-granted tab; the 8-space indentation distinguishes this call site from the policy tab's).

```
        data.findings = await guard403(get(
          `/api/clusters/${encodeURIComponent(view.cluster)}/bindings/findings?limit=${FINDINGS_PAGE}`));
```

### `local-development/gsd/static/index.html`

**Anchor.** `data.findings = await get(`

**Purpose.** REPLACES the anchor line AND its continuation line directly below (the policy tab's findings fetch; 6-space indentation).

```
      data.findings = await guard403(get(
        `/api/clusters/${encodeURIComponent(view.cluster)}/bindings/findings?limit=${FINDINGS_PAGE}`));
```

### `local-development/gsd/static/index.html`

**Anchor.** `data.userBindings = await get(`

**Purpose.** REPLACES the anchor line AND its continuation line directly below: absorb a designed 403 on the namespace-audit fetch (belt for the withhold ruling, harmless under the scoped one).

```
      data.userBindings = await guard403(get(
        `/api/clusters/${encodeURIComponent(view.cluster)}/user-bindings?${q}`));
```

### `local-development/gsd/static/app.css`

**Anchor.** `.runbook { margin: 0; padding-left: 22px; font-size: var(--text-md); line-height: 1.7; color: var(--text-secondary); }`

**Purpose.** INSERT BEFORE the anchor line: the visibility-tier styles. Existing tokens only — no new colour, so the WCAG suite already covers both themes; font sizes only from the --text-* scale (test_type_scale.py); the [hidden] override is load-bearing because the class's display would otherwise beat the UA's [hidden] rule. Verified: merged sheet passes the new token-only test and the regex it uses.

```
/* ---- Visibility tier ------------------------------------------------------------------
   Labels for per-user visibility. Everything here renders what the RESPONSE declared
   (scope/viewer fields, or a designed 403) — the page never computes a tier. Colours are
   existing tokens only, so the WCAG tables in tests/test_accessibility.py already cover
   both themes: the text is --text-primary/--text-secondary on the surfaces it is checked
   on, and --status-warning appears only as a 3px edge — a graphical object under WCAG
   1.4.11, never text. */
.scope-pill {
  display: inline-flex; align-items: center;
  font-size: var(--text-sm); font-weight: 500; color: var(--text-primary);
  background: var(--zebra); border: 1px solid var(--border);
  border-left-width: 3px; border-radius: 999px; padding: 2px 10px;
  white-space: nowrap;
}
/* The narrowed state carries the attention edge; the full state a neutral one. The WORDS
   ("Your view" / "Full view") are the reliable channel — the edge is a scanning aid, so
   a colourblind reader loses nothing. */
.scope-pill.self { border-left-color: var(--status-warning); }
.scope-pill.full { border-left-color: var(--baseline); }
/* display on the class beats the UA's [hidden] rule — author styles always win over the
   UA sheet — so without this the pill would render while claiming to be hidden. */
.scope-pill[hidden] { display: none; }

/* Same shape as .truncation-note, for the same reason: a narrowed list that looks
   complete is the silent-truncation defect wearing a security hat, so the banner is an
   edge-marked notice above the data it qualifies, never a footnote below it. */
.scope-banner {
  margin: 4px 0 10px; padding: 6px 10px;
  border-left: 3px solid var(--status-warning);
  background: color-mix(in srgb, var(--status-warning) 8%, transparent);
  border-radius: 0 6px 6px 0;
}

/* A withheld view is a statement, not an absence — it must not wear .empty-note's quiet
   grey, which is this page's vocabulary for "nothing exists". */
.scope-refusal {
  margin-top: 6px; padding: 10px 12px;
  border-left: 3px solid var(--status-warning);
  background: color-mix(in srgb, var(--status-warning) 8%, transparent);
  border-radius: 0 6px 6px 0;
  font-size: var(--text-md); color: var(--text-secondary);
}
.scope-refusal strong, .scope-banner strong { color: var(--text-primary); }
```

### `local-development/gsd/api.py`

**Anchor.** `@app.get("/api/whoami")`

**Purpose.** REPLACES the whole whoami handler — the anchor decorator line through the handler's closing `return`. Adds the visibility field the UI pill renders from; the tier is computed server-side via the app.state.tier_resolver seam and fails CLOSED. May overlap with the enforcement lens's whoami edit — the arbiter keeps one, holding it to the wire contract test_whoami_reports_the_tier_so_the_ui_never_guesses. Verified to compile in context.

```
    @app.get("/api/whoami")
    def whoami(request: Request) -> dict:
        """Who the proxy says this request is. Reflected, never stored by this endpoint.

        `authenticated` is false when the proxy is disabled even if a username is present,
        because in that mode the caller supplied it themselves.

        `visibility` rides here so the page can LABEL its tier from the wire instead of
        deriving one — the UI never decides (tests/test_ui.py). Absent entirely when there
        is no authenticated identity: reporting a tier for a name nobody verified would
        lend that name credibility.
        """
        user = request.headers.get(USER_HEADER)
        authenticated = bool(user) and settings.oauth_proxy_enabled
        out = {
            "user": user if settings.oauth_proxy_enabled else None,
            "email": request.headers.get(EMAIL_HEADER) if settings.oauth_proxy_enabled else None,
            "authenticated": authenticated,
        }
        if authenticated:
            scope = "all"
            if settings.view_restrictions_enabled:
                try:
                    # Read from app.state per request — the seam the tests swap.
                    scope = app.state.tier_resolver.resolve(user)
                except Exception:  # noqa: BLE001 — an indeterminate tier is SELF, never wide
                    log.exception("tier check failed for %s; reporting the self view", user)
                    scope = "self"
            out["visibility"] = {"scope": scope, "enabled": settings.view_restrictions_enabled}
        return out
```

### `local-development/tests/test_activity.py`

**Anchor.** `assert body == {"user": "alice", "email": "a@x.com", "authenticated": True}`

**Purpose.** REPLACES the anchor line: whoami's proxy-on shape now carries the visibility field, and this exact-equality assertion would otherwise fail for the right reason without saying it.

```
            assert body["user"] == "alice" and body["email"] == "a@x.com"
            assert body["authenticated"] is True
            # The tier now rides on whoami so the UI can label itself from the wire. With
            # no cluster behind this test app the review fails, and the answer fails
            # CLOSED: self, never all.
            assert body["visibility"] == {"scope": "self", "enabled": True}
```

### `local-development/tests/test_ui.py`

**Anchor.** `login_capture_enabled=True,`

**Purpose.** REPLACES the anchor line (inside the module `server` fixture's Settings): the plain UI fixture runs with the proxy OFF and asserts the wide view, which the on-by-default restrictions would 403 — so it makes the same deliberate documented choice a proxyless deployment must make. The scoped fixture added at the end of this file is where restrictions stay on.

```
        login_capture_enabled=True,
        # This fixture predates per-user visibility and its tests assert the WIDE view
        # with the proxy off — which the on-by-default restrictions would 403. Turning
        # them off here is the same deliberate, documented choice a proxyless deployment
        # must make; the visibility labelling has its own scoped_server fixture below.
        view_restrictions_enabled=False,
```

### Test — `module scaffolding — the pinned seam, the seed (executed against the real Store before shipping), and the fixtures` in `local-development/tests/test_visibility.py`

```python
"""Per-user visibility: two tiers, decided by the cluster, enforced at the API handler.

THE SEAM THIS SUITE PINS (the cross-lens contract; a drift in any half is a test failure
here rather than a quiet disagreement):

  * ``Settings.view_restrictions_enabled`` — bool, default True (decision D1: restrictions
    are ON by default). Wire: values ``visibility.enabled`` → env
    ``GSD_ENABLE_VIEW_RESTRICTIONS`` → configmap key ``viewRestrictionsEnabled``. The
    spelling is load-bearing — see TestViewRestrictions in test_config.py.
  * ``gsd.visibility.TierResolver(fetch_groups, post_sar, *, verb="list",
    api_group="user.openshift.io", resource="groups", namespace=None, ttl_seconds=60.0,
    monotonic=time.monotonic)`` decides ``"all" | "self"`` per viewer.
    ``fetch_groups(viewer) -> list[str]`` is a FRESH read of the viewer's OpenShift Group
    names at decision time; ``post_sar(body) -> dict`` POSTs an authorization.k8s.io/v1
    SubjectAccessReview and returns the response object. ``resolve()`` never raises; every
    indeterminate answer is "self" (requirements §5.4); a failed review is never cached; a
    resolved tier is cached per viewer for ``ttl_seconds`` — which is therefore the exact
    worst-case window a revoked administrator retains the wide view.
  * ``build_app`` publishes its resolver at ``app.state.tier_resolver`` and every handler
    consults it PER REQUEST — the indirection that lets these tests install a stub.
  * Every scoped response carries ``scope`` ("self" | "all") and ``viewer`` — the
    /api/dashboard/activity contract, generalised. The UI renders those fields and never
    decides the tier itself (tests/test_ui.py).

Measured background these tests encode (docs/REQUIREMENTS_per_user_visibility.md §4/D2 and
the spec's arbitration): a SubjectAccessReview naming ONLY the user answers allowed=false
for john.doe, who holds cluster-admin through Group/app-ocp-rbac-demo-cluster-admin —
reproduced twice on the reference cluster; adding spec.groups flips it to allowed=true with
the CRB named in the reason. Every real administrator there is group-granted, so a
user-only SAR inverts the feature. That is why half this file is about spec.groups.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from gsd import loginlog
from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.logincapture import event_dict
from gsd.loginlog import LoginAttempt
from gsd.store import Store
from gsd.visibility import TierResolver

GATE_DN = "cn=gate,ou=Groups,dc=example,dc=com"


def _iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def H(user: str) -> dict:
    return {"X-Forwarded-User": user}


def _seed(db_path: str) -> None:
    """Two people, one gate, one dangling binding, one case-variant login.

    alice — in g-adm and the gate group; one success recorded as `alice` and one failure
            recorded as `ALICE`, the caps-lock variant (a DIFFERENT recorded name: self-
            matching is byte-exact, so the variant row is visible only to the wide tier).
    bob   — removed from g-adm and added to g-dev across two polls, so membership CHANGES
            exist for him; holds access through g-dev and is NOT in the gate group.
    root  — the administrator persona; a member of nothing, which is exactly the point:
            the tier comes from a SubjectAccessReview, not from membership rows.
    """
    now = datetime.now(UTC)
    store = Store(db_path)
    store.upsert_cluster("c1", "https://api.c1.example.com:6443", True)
    store.upsert_cluster("c2", "https://api.c2.example.com:6443", True)
    store.record_poll("c1", "ok", None)
    # A degraded cluster, so /api/alerts carries a row EVERY tier must keep seeing.
    store.record_poll("c2", "auth_failed", "401 Unauthorized - token invalid or expired")

    store.replace_groupsync_state(
        "c1",
        [{
            "name": "ldap-sync", "namespace": "group-sync-operator",
            "schedule": "*/30 * * * *",
            # Directory structure — omitted at the self tier along with error_message.
            "ldap_filter": "(&(objectClass=groupOfNames)(cn=app-*))",
            "last_sync_at": _iso(now - timedelta(minutes=4)),
            "generation": 2, "provider_keys": ["ldap-sync_ldap"],
        }],
        _iso(now),
    )
    store.upsert_reconcile_error(
        "c1", "ldap-sync", _iso(now - timedelta(minutes=2)), 2,
        "LDAP bind failed for cn=svc,ou=people: invalid credentials",
    )

    store.replace_group_state(
        "c1",
        [
            {"name": "g-adm", "member_count": 1, "sync_provider": "ldap-sync_ldap",
             "group_synced_at": _iso(now - timedelta(minutes=4)),
             "ldap_uid": "cn=g-adm,ou=Groups,dc=example,dc=com"},
            {"name": "g-dev", "member_count": 1, "sync_provider": "ldap-sync_ldap",
             "group_synced_at": _iso(now - timedelta(minutes=4)),
             "ldap_uid": "cn=g-dev,ou=Groups,dc=example,dc=com"},
            {"name": "gate", "member_count": 1, "sync_provider": "ldap-sync_ldap",
             "group_synced_at": _iso(now - timedelta(minutes=4)), "ldap_uid": GATE_DN},
        ],
        _iso(now),
    )
    # Two polls so membership CHANGES exist: bob leaves g-adm and joins g-dev.
    store.sync_members(
        "c1", {"g-adm": ["alice", "bob"], "g-dev": [], "gate": ["alice"]},
        {}, _iso(now - timedelta(hours=1)),
    )
    store.sync_members(
        "c1", {"g-adm": ["alice"], "g-dev": ["bob"], "gate": ["alice"]},
        {}, _iso(now - timedelta(minutes=4)),
    )
    store.replace_users("c1", {"alice": "Alice A", "bob": "Bob B"}, _iso(now))
    store.set_cluster_access_group("c1", GATE_DN, "config", "gate", _iso(now))

    # One managed group that vanished + a binding still naming it -> a `dangling` finding
    # and its alert, both of which are admin-only.
    store.record_managed_groups(
        "c1", [{"name": "gone-group", "sync_provider": "ldap-sync_ldap"}],
        _iso(now - timedelta(days=1)))
    store.replace_bindings(
        "c1",
        [
            {"binding_kind": "RoleBinding", "binding_namespace": "ns1",
             "binding_name": "gone-rb", "role_kind": "ClusterRole",
             "role_name": "admin", "group_name": "gone-group"},
            {"binding_kind": "RoleBinding", "binding_namespace": "ns1",
             "binding_name": "adm-rb", "role_kind": "ClusterRole",
             "role_name": "view", "group_name": "g-adm"},
        ],
        _iso(now),
    )
    store.replace_user_bindings(
        "c1",
        [
            {"binding_kind": "RoleBinding", "binding_namespace": "ns1",
             "binding_name": "alice-edit", "role_kind": "ClusterRole",
             "role_name": "edit", "user_name": "alice", "is_platform": 0},
            {"binding_kind": "RoleBinding", "binding_namespace": "ns2",
             "binding_name": "bob-admin", "role_kind": "ClusterRole",
             "role_name": "admin", "user_name": "bob", "is_platform": 0},
        ],
        _iso(now),
    )
    attempts = [
        (LoginAttempt("alice", loginlog.OUTCOME_SUCCESS, now - timedelta(minutes=10),
                      provider="ldap"), "oauth-openshift-aaa"),
        # The same person as TYPED with caps lock on: a different recorded name. Byte-exact
        # self-matching means this row is wide-tier only (COLLATE NOCASE was measured to
        # defeat the login_event_by_user index, and OpenShift User names are themselves
        # case-sensitive, so a case-blind match could cross-leak two distinct Users).
        (LoginAttempt("ALICE", loginlog.OUTCOME_BAD_PASSWORD, now - timedelta(minutes=9),
                      provider="ldap", ldap_result_code=49), "oauth-openshift-aaa"),
        (LoginAttempt("bob", loginlog.OUTCOME_BAD_PASSWORD, now - timedelta(minutes=8),
                      provider="ldap", ldap_result_code=49), "oauth-openshift-aaa"),
    ]
    store.record_login_events("c1", [event_dict(a, p, _iso(now)) for a, p in attempts])
    store.record_login_read("c1", _iso(now - timedelta(seconds=30)))
    store.close()


def _settings(db: str, **kw) -> Settings:
    kw.setdefault("oauth_proxy_enabled", True)
    kw.setdefault("login_capture_enabled", True)
    return Settings(
        clusters=[ClusterConfig("c1", "https://api.c1.example.com:6443", token_env="X"),
                  ClusterConfig("c2", "https://api.c2.example.com:6443", token_env="Y")],
        db_path=db, **kw)


class _MapResolver:
    """A stub for the app.state.tier_resolver seam: viewer name -> tier, default self.

    Counting `calls` is what proves the machinery is INERT when the feature is disabled —
    off must mean no SubjectAccessReview traffic at all, not a review whose answer is
    ignored.
    """

    def __init__(self, tiers: dict[str, str]):
        self.tiers = tiers
        self.calls = 0

    def resolve(self, viewer: str) -> str:
        self.calls += 1
        return self.tiers.get(viewer, "self")


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> str:
    path = str(tmp_path_factory.mktemp("vis") / "gsd.db")
    _seed(path)
    return path


@pytest.fixture(scope="module")
def client(db):
    """Proxy on, restrictions on (the D1 default), root is the administrator."""
    app = build_app(_settings(db), run_poller=False)
    app.state.tier_resolver = _MapResolver({"root": "all"})
    with TestClient(app) as c:
        yield c


# ── The decision, in isolation ───────────────────────────────────────────────────────────

class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def _allowed(flag: bool) -> dict:
    return {"apiVersion": "authorization.k8s.io/v1", "kind": "SubjectAccessReview",
            "status": {"allowed": bool(flag)}}
```

### Test — `TestTierResolver — the SAR body (the inversion catcher), the choosable threshold, fail-closed, the cache and the stale-removal window` in `local-development/tests/test_visibility.py`

```python
class TestTierResolver:
    """gsd.visibility.TierResolver with the SAR and the group read injected."""

    def test_the_sar_carries_the_viewers_groups_and_system_authenticated(self):
        """THE finding that shaped the feature (spec arbitration, measured twice):
        spec.user alone answered allowed=false for john.doe, cluster-admin via
        Group/app-ocp-rbac-demo-cluster-admin. A SubjectAccessReview resolves no group
        memberships itself, so the app must assert them — the Group objects it already
        reads, plus the virtual group every authenticated user holds."""
        bodies: list[dict] = []

        def post_sar(body):
            bodies.append(body)
            return _allowed(True)

        r = TierResolver(lambda v: ["app-ocp-rbac-demo-cluster-admin"], post_sar)
        assert r.resolve("john.doe") == "all"
        assert bodies[0]["apiVersion"] == "authorization.k8s.io/v1"
        assert bodies[0]["kind"] == "SubjectAccessReview"
        spec = bodies[0]["spec"]
        assert spec["user"] == "john.doe"
        assert "app-ocp-rbac-demo-cluster-admin" in spec["groups"]
        assert "system:authenticated" in spec["groups"]

    def test_a_group_granted_admin_is_recognised(self):
        """The end-to-end inversion catcher. This fake evaluates the review exactly the
        way RBAC on the reference cluster does — the grant is attached to the GROUP, so a
        body without spec.groups is denied. An implementation that names only the user
        demotes 100% of real administrators and fails here."""
        def cluster_rbac(body):
            groups = body["spec"].get("groups") or []
            return _allowed("app-ocp-rbac-demo-cluster-admin" in groups)

        r = TierResolver(lambda v: ["app-ocp-rbac-demo-cluster-admin"], cluster_rbac)
        assert r.resolve("john.doe") == "all"

    def test_the_default_threshold_is_list_groups(self):
        """D2's default: `list groups.user.openshift.io` — held by cluster-admin and
        cluster-reader, held by NONE of cluster-wide admin/edit/view (measured matrix in
        the requirements)."""
        bodies: list[dict] = []

        def post_sar(body):
            bodies.append(body)
            return _allowed(False)

        TierResolver(lambda v: [], post_sar).resolve("someone")
        ra = bodies[0]["spec"]["resourceAttributes"]
        assert ra["verb"] == "list"
        assert ra["group"] == "user.openshift.io"
        assert ra["resource"] == "groups"

    def test_the_threshold_is_choosable_by_the_operator(self):
        """D2: the values surface expresses the CHECK ITSELF (apiGroup, resource, verb,
        optional namespace) — `list rolebindings` is the documented alternative that also
        admits cluster-wide `admin`. A named-role list was rejected: it would miss
        cluster-reader and every custom route."""
        bodies: list[dict] = []

        def post_sar(body):
            bodies.append(body)
            return _allowed(False)

        TierResolver(
            lambda v: [], post_sar,
            verb="list", api_group="rbac.authorization.k8s.io",
            resource="rolebindings", namespace="team-ns",
        ).resolve("someone")
        ra = bodies[0]["spec"]["resourceAttributes"]
        assert ra["verb"] == "list"
        assert ra["group"] == "rbac.authorization.k8s.io"
        assert ra["resource"] == "rolebindings"
        assert ra.get("namespace") == "team-ns"

    def test_denied_means_self(self):
        r = TierResolver(lambda v: [], lambda body: _allowed(False))
        assert r.resolve("lateef.o") == "self"

    def test_a_sar_error_means_self_never_all(self):
        """Requirements §5.4 / D1: an INDETERMINATE answer yields the SELF tier. A control
        that fails open is not a control."""
        def post_sar(body):
            raise RuntimeError("API server unreachable")

        assert TierResolver(lambda v: [], post_sar).resolve("anyone") == "self"

    def test_a_missing_answer_means_self(self):
        r = TierResolver(lambda v: [], lambda body: {"status": {}})
        assert r.resolve("anyone") == "self"

    def test_a_group_read_failure_fails_closed(self):
        """The groups input is half the decision (the inversion finding), so a failed
        group read is as indeterminate as a failed review."""
        def fetch_groups(viewer):
            raise RuntimeError("Group list refused")

        assert TierResolver(fetch_groups, lambda body: _allowed(True)).resolve("x") == "self"

    def test_the_answer_is_cached_per_viewer(self):
        """One review per viewer per TTL — the page polls every 30s and a SAR per request
        would put a personal-data path on the API server's latency floor."""
        calls = {"n": 0}

        def post_sar(body):
            calls["n"] += 1
            return _allowed(True)

        r = TierResolver(lambda v: [], post_sar)
        assert r.resolve("jane") == "all"
        assert r.resolve("jane") == "all"
        assert calls["n"] == 1, "the second resolve should ride the cache"
        r.resolve("john")
        assert calls["n"] == 2, "the cache is per viewer, not global"

    def test_a_failed_review_is_not_cached_as_a_tier(self):
        """Fail-closed must be a POSTURE, not a sentence: one API-server blip must not
        demote an administrator for a whole TTL."""
        calls = {"n": 0}

        def flaky(body):
            calls["n"] += 1
            if calls["n"] == 1:
                raise RuntimeError("blip")
            return _allowed(True)

        r = TierResolver(lambda v: [], flaky)
        assert r.resolve("jane") == "self"
        assert r.resolve("jane") == "all", "the failure was cached; the blip became the tier"

    def test_a_revoked_admin_is_narrowed_when_the_ttl_lapses(self):
        """The stated staleness window (requirements §8.8, spec arbitration): a user
        removed from the admin group retains the wide view for AT MOST ttl_seconds,
        because the cache lapse forces a FRESH group read and a fresh review. The window
        is the TTL — not the poll interval, which is tuned for something else."""
        clock = _Clock()
        state = {"admin": True}

        def fetch_groups(viewer):
            return ["adm-group"] if state["admin"] else []

        def post_sar(body):
            return _allowed("adm-group" in (body["spec"].get("groups") or []))

        r = TierResolver(fetch_groups, post_sar, ttl_seconds=60.0, monotonic=clock)
        assert r.resolve("jane") == "all"
        state["admin"] = False              # removed from the admin group
        clock.t += 59.0
        assert r.resolve("jane") == "all"   # inside the documented worst-case window
        clock.t += 2.0
        assert r.resolve("jane") == "self"  # window closed: fresh groups, fresh review
```

### Test — `TestTwoTiersPerEndpoint — the two-tier assertions, endpoint by endpoint (seed premises verified against the live app: alert kinds, distinct users, cluster-access shape)` in `local-development/tests/test_visibility.py`

```python
# ── The two tiers, endpoint by endpoint ──────────────────────────────────────────────────

class TestTwoTiersPerEndpoint:
    def test_groups_are_scoped_to_membership_at_self(self, client):
        body = client.get("/api/clusters/c1/groups", headers=H("alice")).json()
        assert body["scope"] == "self" and body["viewer"] == "alice"
        assert {g["name"] for g in body["groups"]} == {"g-adm", "gate"}

    def test_groups_are_complete_at_all(self, client):
        body = client.get("/api/clusters/c1/groups", headers=H("root")).json()
        assert body["scope"] == "all"
        assert {g["name"] for g in body["groups"]} == {"g-adm", "g-dev", "gate"}

    def test_group_detail_403_is_constant_for_nonmember_and_nonexistent(self, client):
        """No existence oracle: a group outside the viewer's membership and a group that
        does not exist must be indistinguishable, or the 403 itself enumerates groups."""
        a = client.get("/api/clusters/c1/groups/g-dev", headers=H("alice"))
        b = client.get("/api/clusters/c1/groups/no-such-group", headers=H("alice"))
        assert a.status_code == 403 and b.status_code == 403
        assert a.json() == b.json()
        assert client.get("/api/clusters/c1/groups/g-adm",
                          headers=H("alice")).status_code == 200
        assert client.get("/api/clusters/c1/groups/g-dev",
                          headers=H("root")).status_code == 200

    def test_users_list_is_own_row_only_at_self(self, client):
        body = client.get("/api/clusters/c1/users", headers=H("alice")).json()
        assert body["scope"] == "self"
        assert [u["user_name"] for u in body["users"]] == ["alice"]
        wide = client.get("/api/clusters/c1/users", headers=H("root")).json()
        assert {u["user_name"] for u in wide["users"]} == {"alice", "bob"}

    def test_user_detail_is_own_profile_or_a_constant_403(self, client):
        assert client.get("/api/clusters/c1/users/alice",
                          headers=H("alice")).status_code == 200
        other = client.get("/api/clusters/c1/users/bob", headers=H("alice"))
        ghost = client.get("/api/clusters/c1/users/nobody", headers=H("alice"))
        assert other.status_code == 403 and ghost.status_code == 403
        assert other.json() == ghost.json()
        assert client.get("/api/clusters/c1/users/bob",
                          headers=H("root")).status_code == 200

    def test_logins_are_scoped_byte_exact_at_self(self, client):
        """`ALICE` is alice with caps lock on — and a DIFFERENT recorded name. The match
        is byte-exact on purpose (the NOCASE variant defeats the index and could cross-
        leak two Users differing only by case), so the variant row is wide-tier only and
        the UI carries the 'as typed' caveat instead."""
        body = client.get("/api/clusters/c1/logins", headers=H("alice")).json()
        assert body["scope"] == "self" and body["viewer"] == "alice"
        assert {a["user_name"] for a in body["attempts"]} == {"alice"}
        assert body["total"] == 1, "total must describe the viewer's record, not the cluster's"
        assert "summary" not in body, "the whole-record summary is personnel data"
        assert "ungoverned" not in body, "the ungoverned-accounts finding names other people"

    def test_logins_are_complete_at_all(self, client):
        body = client.get("/api/clusters/c1/logins", headers=H("root")).json()
        assert {a["user_name"] for a in body["attempts"]} == {"alice", "ALICE", "bob"}
        assert body["summary"]["distinct_users"] == 3
        assert "ungoverned" in body

    def test_user_bindings_are_own_grants_only_at_self(self, client):
        body = client.get("/api/clusters/c1/user-bindings", headers=H("alice")).json()
        assert body["scope"] == "self"
        assert {b["user_name"] for b in body["bindings"]} == {"alice"}
        assert "by_namespace" not in body, "the rollup aggregates other people's grants"
        assert "excluded_platform" not in body
        wide = client.get("/api/clusters/c1/user-bindings", headers=H("root")).json()
        assert {b["user_name"] for b in wide["bindings"]} == {"alice", "bob"}
        assert wide["by_namespace"], "the admin rollup went missing"

    def test_membership_changes_are_scoped_to_the_viewer(self, client):
        body = client.get("/api/clusters/c1/membership-changes", headers=H("bob")).json()
        assert body["scope"] == "self"
        assert {e["user_name"] for e in body["changes"]} == {"bob"}
        wide = client.get("/api/clusters/c1/membership-changes", headers=H("root")).json()
        assert {e["user_name"] for e in wide["changes"]} == {"alice", "bob"}

    def test_cluster_access_is_own_gate_status_at_self(self, client):
        """The viewer's own admission status is theirs; the gate DN, the member lists and
        the cluster summary are other people's data and directory structure."""
        body = client.get("/api/clusters/c1/cluster-access", headers=H("bob")).json()
        assert body["scope"] == "self" and body["viewer"] == "bob"
        assert body["gated"] is True
        assert body["in_gate"] is False, "bob is not in the gate group"
        assert body.get("dn") is None
        assert "access_without_login" not in body
        assert "login_without_access" not in body
        assert "summary" not in body
        mine = client.get("/api/clusters/c1/cluster-access", headers=H("alice")).json()
        assert mine["in_gate"] is True
        wide = client.get("/api/clusters/c1/cluster-access", headers=H("root")).json()
        assert wide["dn"] == GATE_DN and "access_without_login" in wide

    def test_binding_findings_are_admin_only(self, client):
        """The findings rows ARE the cluster's RBAC surface — the data whose exposure to a
        reader who cannot `oc get` it was the measured privilege escalation (values.yaml
        apiTokenAccess history)."""
        assert client.get("/api/clusters/c1/bindings/findings",
                          headers=H("alice")).status_code == 403
        wide = client.get("/api/clusters/c1/bindings/findings", headers=H("root"))
        assert wide.status_code == 200
        assert wide.json()["counts"]["dangling"] == 1

    def test_alerts_drop_the_rbac_kinds_at_self_and_keep_the_operational_ones(self, client):
        """An alert always has a page behind it (api.py's own invariant): the kinds whose
        pages are admin-only go with those pages; a broken cluster stays visible to
        everyone because its page does."""
        kinds = {a["kind"] for a in client.get("/api/alerts", headers=H("alice")).json()}
        assert "auth_failed" in kinds
        assert "dangling_binding" not in kinds
        assert "direct_user_binding" not in kinds
        wide = {a["kind"] for a in client.get("/api/alerts", headers=H("root")).json()}
        assert {"auth_failed", "dangling_binding", "direct_user_binding"} <= wide

    def test_groupsyncs_omit_directory_detail_at_self(self, client):
        """CR health is governance data and stays visible; ldap_filter and error_message
        can embed directory DNs and the gate group, which /metrics deliberately never
        carries — the same line drawn here."""
        crs = client.get("/api/clusters/c1/groupsyncs", headers=H("alice")).json()
        assert crs, "the CR list itself must stay visible at self"
        assert all(not cr.get("ldap_filter") for cr in crs)
        assert all(not cr.get("error_message") for cr in crs)
        wide = client.get("/api/clusters/c1/groupsyncs", headers=H("root")).json()
        assert any(cr.get("ldap_filter") for cr in wide)
        assert any(cr.get("error_message") for cr in wide)

    def test_the_overview_counts_stay_full_at_self(self, client):
        """/api/clusters is the credential-less /metrics content with names on the
        clusters: suppressing behind login what the pod serves without login is theatre."""
        mine = client.get("/api/clusters", headers=H("alice")).json()
        wide = client.get("/api/clusters", headers=H("root")).json()
        assert mine == wide
```

### Test — `TestFailClosed — the forced-failure test and the no-identity refusal` in `local-development/tests/test_visibility.py`

```python
# ── Fail closed ──────────────────────────────────────────────────────────────────────────

class TestFailClosed:
    def test_a_broken_tier_check_degrades_to_self_not_500(self, db):
        """Requirements §5.4, forced: the resolver contract says resolve() never raises,
        and the handlers must not trust that — an administrator on a flaky API server
        sees their OWN data and a banner, never an error page and never everyone's."""
        class Exploding:
            def resolve(self, viewer):
                raise RuntimeError("SAR path down")

        app = build_app(_settings(db), run_poller=False)
        app.state.tier_resolver = Exploding()
        with TestClient(app) as c:
            r = c.get("/api/clusters/c1/groups", headers=H("root"))
        assert r.status_code == 200
        body = r.json()
        assert body["scope"] == "self", "an indeterminate tier must be SELF, never wide"
        assert body["groups"] == [], "root is a member of nothing seeded"

    def test_no_identity_behind_the_proxy_is_refused_not_widened(self, client):
        """No X-Forwarded-User with the proxy on: there is nobody to scope to, and 'show
        everything' is the one wrong answer. The activity endpoint's rule, generalised."""
        assert client.get("/api/clusters/c1/groups").status_code == 403
        assert client.get("/api/clusters/c1/logins").status_code == 403
```

### Test — `TestTheSwitch — the env var actually disabling the feature (and staying inert), and the proxy-off guard` in `local-development/tests/test_visibility.py`

```python
# ── The one switch ───────────────────────────────────────────────────────────────────────

class TestTheSwitch:
    def test_disabling_restrictions_restores_the_wide_view(self, db):
        """D1: `visibility.enabled: false` -> GSD_ENABLE_VIEW_RESTRICTIONS=false restores
        today's behaviour as a deliberate documented choice. Off means INERT — zero
        SubjectAccessReviews — not a review whose answer is ignored."""
        app = build_app(_settings(db, view_restrictions_enabled=False), run_poller=False)
        stub = _MapResolver({})          # would answer "self" for everyone if consulted
        app.state.tier_resolver = stub
        with TestClient(app) as c:
            body = c.get("/api/clusters/c1/groups", headers=H("alice")).json()
        assert body["scope"] == "all", "disabled must be labelled as the wide view"
        assert {g["name"] for g in body["groups"]} == {"g-adm", "g-dev", "gate"}
        assert stub.calls == 0, "disabled must mean no tier machinery runs at all"

    def test_proxy_off_never_derives_a_tier_from_the_header(self, db):
        """Constraint §5.3: with the proxy off the app binds 0.0.0.0 unauthenticated and
        X-Forwarded-User is whatever the caller typed. Restrictions on + proxy off is
        self-with-no-identity: personal endpoints refuse, governance data still serves."""
        app = build_app(_settings(db, oauth_proxy_enabled=False), run_poller=False)
        with TestClient(app) as c:
            assert c.get("/api/clusters/c1/groups",
                         headers=H("alice")).status_code == 403
            assert c.get("/api/clusters/c1/logins",
                         headers=H("alice")).status_code == 403
            assert c.get("/api/clusters/c1/groupsyncs").status_code == 200
```

### Test — `TestWireContract — scope/viewer on every scoped response, and whoami's tier report` in `local-development/tests/test_visibility.py`

```python
# ── The wire contract the UI renders from ────────────────────────────────────────────────

class TestWireContract:
    SCOPED = [
        "/api/clusters/c1/groups",
        "/api/clusters/c1/users",
        "/api/clusters/c1/logins",
        "/api/clusters/c1/user-bindings",
        "/api/clusters/c1/membership-changes",
        "/api/clusters/c1/cluster-access",
    ]

    @pytest.mark.parametrize("path", SCOPED)
    def test_scope_and_viewer_are_declared_on_every_scoped_response(self, client, path):
        """The UI never decides the tier (the Groups search-box scar, as a rule): it can
        only render what the response declares, so every scoped payload must declare."""
        mine = client.get(path, headers=H("alice")).json()
        assert mine["scope"] == "self" and mine["viewer"] == "alice"
        wide = client.get(path, headers=H("root")).json()
        assert wide["scope"] == "all" and wide["viewer"] == "root"

    def test_whoami_reports_the_tier_so_the_ui_never_guesses(self, client):
        mine = client.get("/api/whoami", headers=H("alice")).json()
        assert mine["visibility"] == {"scope": "self", "enabled": True}
        wide = client.get("/api/whoami", headers=H("root")).json()
        assert wide["visibility"] == {"scope": "all", "enabled": True}

    def test_whoami_carries_no_visibility_claim_without_an_identity(self, client):
        body = client.get("/api/whoami").json()
        assert "visibility" not in body
```

### Test — `TestAdminSeesExactlyToday — DoD 2 as an equality between the wide tier and the disabled view` in `local-development/tests/test_visibility.py`

```python
# ── DoD 2: an administrator sees exactly what they see today ─────────────────────────────

def _strip(obj):
    """Drop the clock-derived GroupSync fields before comparing two requests made moments
    apart — `state` and `next_expected` are computed from now() and can legitimately
    differ across a minute boundary. Everything else must be byte-identical."""
    if isinstance(obj, dict):
        return {k: _strip(v) for k, v in obj.items() if k not in ("state", "next_expected")}
    if isinstance(obj, list):
        return [_strip(v) for v in obj]
    return obj


class TestAdminSeesExactlyToday:
    ENDPOINTS = [
        "/api/clusters",
        "/api/alerts",
        "/api/clusters/c1/groups",
        "/api/clusters/c1/users",
        "/api/clusters/c1/user-bindings",
        "/api/clusters/c1/logins",
        "/api/clusters/c1/cluster-access",
        "/api/clusters/c1/membership-changes",
        "/api/clusters/c1/bindings/findings",
        "/api/clusters/c1/groupsyncs",
        "/api/clusters/c1/operator-configs",
    ]

    def test_the_wide_tier_equals_the_disabled_view_per_endpoint(self, db):
        """Definition of done #2, as an equality: with restrictions ON an administrator's
        response is identical to the same request with restrictions OFF — the feature
        must be invisible to the people it does not restrict."""
        on = build_app(_settings(db), run_poller=False)
        on.state.tier_resolver = _MapResolver({"root": "all"})
        off = build_app(_settings(db, view_restrictions_enabled=False), run_poller=False)
        with TestClient(on) as a, TestClient(off) as b:
            for path in self.ENDPOINTS:
                x = a.get(path, headers=H("root"))
                y = b.get(path, headers=H("root"))
                assert x.status_code == y.status_code == 200, path
                assert _strip(x.json()) == _strip(y.json()), (
                    f"the admin view drifted from today's behaviour on {path}"
                )
```

### Test — `TestViewRestrictions — the correctly-spelled env var works, the operator's typo is pinned as a no-op (append after the existing classes; uses the module's BASE and write helpers)` in `local-development/tests/test_config.py`

```python
class TestViewRestrictions:
    """D1: view restrictions are ON by default, with one switch.

    The env var's SPELLING is load-bearing. The operator's message wrote RESCRICTIONS;
    an env var that only almost matches is read by nobody, the setting silently stays at
    its default, and here the default is the only thing standing between every
    authenticated reader and the full RBAC surface — so the misspelling is pinned as a
    no-op and the correct spelling is pinned as the one that works.
    """

    def test_on_by_default(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_ENABLE_VIEW_RESTRICTIONS", raising=False)
        assert load_settings(write(tmp_path, BASE)).view_restrictions_enabled is True

    def test_the_env_var_disables(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESTRICTIONS", "false")
        assert load_settings(write(tmp_path, BASE)).view_restrictions_enabled is False

    def test_the_configmap_key_disables(self, tmp_path, monkeypatch):
        monkeypatch.delenv("GSD_ENABLE_VIEW_RESTRICTIONS", raising=False)
        cfg = BASE + "viewRestrictionsEnabled: false\n"
        assert load_settings(write(tmp_path, cfg)).view_restrictions_enabled is False

    def test_env_wins_over_the_configmap(self, tmp_path, monkeypatch):
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESTRICTIONS", "true")
        cfg = BASE + "viewRestrictionsEnabled: false\n"
        assert load_settings(write(tmp_path, cfg)).view_restrictions_enabled is True

    def test_the_operators_typo_has_no_effect(self, tmp_path, monkeypatch):
        """GSD_ENABLE_VIEW_RESCRICTIONS — the typo from the original request — must not
        disable anything: a misspelled env var here is a silently disabled security
        control, which is the worst failure this feature can have."""
        monkeypatch.delenv("GSD_ENABLE_VIEW_RESTRICTIONS", raising=False)
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESCRICTIONS", "false")
        assert load_settings(write(tmp_path, BASE)).view_restrictions_enabled is True

    def test_a_nonsense_value_leaves_the_control_on(self, tmp_path, monkeypatch):
        """The fail direction matters more than the fallback: 'maybe' must not widen."""
        monkeypatch.setenv("GSD_ENABLE_VIEW_RESTRICTIONS", "maybe")
        assert load_settings(write(tmp_path, BASE)).view_restrictions_enabled is True
```

### Test — `visibility labelling — scoped fixture + TestVisibilityLabels (append at the end of the file, after TestTabFocusSurvivesTheRepaint; uses the module's existing imports and _seed)` in `local-development/tests/test_ui.py`

```python
# ── Per-user visibility: how a narrowed view is LABELLED ─────────────────────────────────
# The server decides the tier; the page renders `scope`/`viewer` off the wire and a
# designed 403 as a named refusal. These tests hold the page to exactly that — including
# the negative: no declaration on the wire, no label on the page.


class _TierByName:
    """The seam the visibility feature publishes for tests: build_app leaves its resolver
    at app.state.tier_resolver and every handler reads it per request, so swapping it here
    controls the tier without a cluster. `root` is the administrator persona; everyone
    else is self."""

    def resolve(self, viewer):
        return "all" if viewer == "root" else "self"


@pytest.fixture(scope="module")
def scoped_server(tmp_path_factory):
    """The seeded app behind a simulated oauth proxy, restrictions ON (the D1 default)."""
    db = str(tmp_path_factory.mktemp("gsd-vis") / "ui.db")
    _seed(db)
    settings = Settings(
        clusters=[
            ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X"),
            ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="Y"),
        ],
        db_path=db,
        login_capture_enabled=True,
        # Identity is believable here, unlike in the plain `server` fixture: the tier is
        # keyed off X-Forwarded-User, which is exactly what the proxy would set.
        oauth_proxy_enabled=True,
    )
    port = _free_port()
    app = build_app(settings, run_poller=False)
    app.state.tier_resolver = _TierByName()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    srv = uvicorn.Server(config)
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("scoped dashboard server did not start")
    yield base
    srv.should_exit = True
    thread.join(timeout=5)


def _open_as(page, base, user):
    """Load the dashboard as `user`, with an uncaught JS error an immediate failure —
    the same discipline as the `dash` fixture, for the same reason."""
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.set_extra_http_headers({"X-Forwarded-User": user})
    page.goto(base)
    try:
        page.wait_for_selector(".hero .value", timeout=10_000)
    except Exception:
        if errors:
            pytest.fail("the page raised and never rendered:\n  " + "\n  ".join(errors))
        raise
    assert not errors, "uncaught JS error on load:\n  " + "\n  ".join(errors)
    return page


class TestVisibilityLabels:
    def test_the_pill_names_the_narrowed_view(self, page, scoped_server):
        """Q6/DoD 5: the reader can tell 'this is your view' from 'this is everything',
        on every tab, starting with the landing page."""
        p = _open_as(page, scoped_server, "alice")
        p.wait_for_selector("#scope-pill:not([hidden])")
        text = p.locator("#scope-pill").inner_text()
        assert text.startswith("Your view"), text
        assert "alice" in text, "the pill must name the viewer it is scoped to"

    def test_the_administrator_is_told_they_see_everything(self, page, scoped_server):
        """The admin marker. 'Nothing looks different' and 'you are seeing everything'
        are different statements, and only the second is checkable from the screen."""
        p = _open_as(page, scoped_server, "root")
        p.wait_for_selector("#scope-pill:not([hidden])")
        assert p.locator("#scope-pill").inner_text().startswith("Full view")

    def test_groups_tab_banner_and_scoped_count(self, page, scoped_server):
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='groups']").click()
        p.wait_for_selector(".scope-banner")
        banner = p.locator(".scope-banner").inner_text()
        assert "alice" in banner and "belongs to" in banner
        # alice is in the RBAC group and the gate group — 2 of the 4 seeded groups.
        assert p.locator("tbody tr").count() == 2

    def test_admin_groups_tab_is_complete_and_carries_no_self_banner(self, page, scoped_server):
        p = _open_as(page, scoped_server, "root")
        p.locator("button[data-nav='groups']").click()
        p.wait_for_selector("#f-group-search")
        assert p.locator("tbody tr").count() == SYNCED_GROUPS
        assert p.locator(".scope-banner").count() == 0

    def test_scoped_empty_is_not_mistaken_for_an_empty_cluster(self, page, scoped_server):
        """Q6's founding example: one row where an administrator sees two hundred must
        not read as a nearly-empty cluster — and a scoped ZERO rows must not read as an
        empty one. The wording also surfaces the viewer's name, which is the on-screen
        diagnostic for an IdP-vs-synced-name mismatch."""
        p = _open_as(page, scoped_server, "nomember")
        p.locator("button[data-nav='groups']").click()
        p.wait_for_selector(".scope-banner")
        body = p.locator("#main").inner_text()
        assert "not a member of any synced group" in body
        assert "nomember" in body
        assert "No groups match this filter" not in body

    def test_withheld_governance_tabs_are_named_refusals_not_blanks(self, page, scoped_server):
        """An empty audit tab reads as a healthy cluster, which is a lie. The refusal
        names what exists, why it is withheld, and what widens it."""
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='bindings']").click()
        p.wait_for_selector(".scope-refusal")
        assert "Withheld" in p.locator(".scope-refusal").inner_text()
        p.locator("button[data-nav='policy']").click()
        p.wait_for_selector(".scope-refusal")
        text = p.locator(".scope-refusal").inner_text()
        assert "Withheld" in text and "administrator" in text

    def test_nsaudit_self_view_names_the_viewer_and_drops_cluster_kpis(self, page, scoped_server):
        """Q5: 'People exposed' recomputed over one person is a lying label, so the
        narrowed tab renders the viewer's own grants and none of the cluster KPIs."""
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='nsaudit']").click()
        p.wait_for_selector(".scope-banner")
        body = p.locator("#main").inner_text()
        assert "No role is granted directly to" in body and "alice" in body
        assert "People exposed" not in body
        assert "Namespaces at risk" not in body

    def test_logins_tab_banner_carries_the_as_typed_caveat(self, page, scoped_server):
        """Byte-exact matching means a caps-lock attempt is invisible to its own author;
        the banner says so instead of letting the absence read as 'never happened'."""
        p = _open_as(page, scoped_server, "alice")
        p.locator("button[data-nav='logins']").click()
        p.wait_for_selector(".scope-banner")
        banner = p.locator(".scope-banner").first.inner_text()
        assert "alice" in banner and "as typed" in banner
        main = p.locator("#main").inner_text()
        assert "Accounts in no synced group" not in main, (
            "the ungoverned-accounts finding is whole-cluster data and must not render "
            "at the narrowed tier"
        )
        assert "bob" not in main, "another person's attempts leaked into the scoped view"

    def test_admin_logins_page_is_unchanged(self, page, scoped_server):
        p = _open_as(page, scoped_server, "root")
        p.locator("button[data-nav='logins']").click()
        p.wait_for_selector("table")
        body = p.locator("#main").inner_text()
        assert "Accounts in no synced group" in body
        assert p.locator(".scope-banner").count() == 0

    def test_group_drilldown_refusal_is_a_detour_not_a_dead_end(self, page, scoped_server):
        """The constant 403 must render as a named refusal WITH a working back affordance
        — and must not claim to know whether the group exists, because the server
        deliberately answers nonexistent and forbidden identically."""
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.set_extra_http_headers({"X-Forwarded-User": "alice"})
        page.goto(scoped_server + "#page=groups&group=app-ocp-rbac-abcd-ns-superuser")
        page.wait_for_selector(".scope-refusal")
        assert not errors
        assert "indistinguishable" in page.locator(".scope-refusal").inner_text()
        assert page.locator(".back").count() == 1

    def test_no_declaration_on_the_wire_means_no_labels(self, page, server):
        """The search-box scar as a regression test: the page must not claim a narrowing
        the response never declared. The plain `server` fixture runs restrictions-off
        with the proxy off — its responses carry scope 'all' or nothing — so the pill
        must exist (it is part of the header) and stay hidden, and no self banner may
        render anywhere."""
        page.goto(server)
        page.wait_for_selector(".hero .value", timeout=10_000)
        assert page.locator("#scope-pill").count() == 1, "the pill mount is missing from the header"
        assert page.locator("#scope-pill").is_hidden()
        page.locator("button[data-nav='groups']").click()
        page.wait_for_selector("#f-group-search")
        assert page.locator(".scope-banner").count() == 0
        assert page.locator(".scope-refusal").count() == 0
```

### Test — `test_visibility_labels_use_only_vetted_tokens (append at the end of the file; verified to pass against the merged app.css and fail against the current one)` in `local-development/tests/test_accessibility.py`

```python
def test_visibility_labels_use_only_vetted_tokens():
    """The scope pill, banner and refusal ship NO colour of their own: every colour they
    use must be a var(--token) already covered by the contrast tables above, in both
    themes. A literal hex in that block would be the first colour on the page outside
    this file's checks — which is exactly how the nine original failures happened."""
    css = CSS.read_text()
    m = re.search(r"/\* ---- Visibility tier(.*?)\.runbook", css, re.S)
    assert m, "the visibility-tier style block is missing from app.css"
    block = re.sub(r"/\*.*?\*/", "", m.group(1), flags=re.S)
    assert "#" not in block, "a literal colour crept into the visibility styles; use a token"
    for cls in (".scope-pill", ".scope-banner", ".scope-refusal"):
        assert cls in block, f"{cls} is not styled in the visibility block"
```

**Risks it names.** WHAT WAS VERIFIED BEFORE WRITING: every anchor below was grep-counted unique against the worktree; all 19 index.html edits were applied to a copy by script and the assembled page <script> parses clean under node --check (150,673 bytes, no <style> tag, every original function still present exactly once); the CSS block was merged into app.css and passes both the new token-only test logic and the type-scale rule (font-size only via --text-*); the whoami replacement was merged into api.py and compiles; every Python test file compiles; the test seed was RUN against the real Store (user_groups alice=[g-adm,gate], bob=[g-dev], dangling finding present, is_in_access_group {alice:True,bob:False}) and the live app on that seed confirmed the premises the tests assert (alert kinds = auth_failed, dangling_binding, direct_user_binding, reconcile_error; logins distinct_users=3; cluster-access keys incl. dn and both lists).

WHAT THIS CANNOT GUARANTEE — the cross-lens seam. These tests and the UI PIN a contract other lenses must implement, and the arbiter must hold them to it or mechanically reconcile names: (1) gsd/visibility.py TierResolver(fetch_groups, post_sar, *, verb="list", api_group="user.openshift.io", resource="groups", namespace=None, ttl_seconds=60.0, monotonic=time.monotonic), resolve(viewer)->"all"|"self", never raises, failed reviews uncached, per-viewer TTL cache; it must also construct without crashing when zero clusters are configured (test_activity's whoami test exercises exactly that) and fail closed there. (2) Settings.view_restrictions_enabled: bool = True, env GSD_ENABLE_VIEW_RESTRICTIONS, yaml key viewRestrictionsEnabled. (3) build_app publishes the resolver at app.state.tier_resolver and every handler consults it PER REQUEST. (4) Wire shapes: /groups becomes {scope, viewer, groups:[...]} at BOTH tiers and when disabled; logins at self omits summary/ungoverned and total counts the viewer's rows; cluster-access at self is {scope, viewer, gated, synced, group_name, in_gate, note} with dn/lists/summary omitted; user-bindings at self omits by_namespace/excluded_platform; whoami gains visibility:{scope, enabled} only when authenticated; scoped 403s are constant for forbidden-vs-nonexistent.

FALLOUT THE ENFORCEMENT LENS MUST ABSORB, measured here: restrictions-on-by-default plus the /groups shape change will break existing tests that hit scoped endpoints with proxy off or assert the old list shape (test_api_contract.py, test_no_groupsync_operator.py, test_membership.py, test_binding_findings_paging.py, test_user_binding_paging.py, test_user_full_name.py and others). I fixed the one fixture my tests share (test_ui.py server gains view_restrictions_enabled=False as a deliberate documented choice — the same choice a proxyless deployment must make) but did NOT sweep the rest; the arbiter's proof is the suite command (baseline 1057 passed, 1 skipped) going green after ALL lenses land.

MUST BE MEASURED BEFORE SHIP (not provable in tests): in-pod SAR latency to confirm ttl_seconds=60 (lens 1 measured 25.1ms median from outside; the values.yaml comment must state the worst-case revoked-admin window = the TTL); the chart must render GSD_ENABLE_VIEW_RESTRICTIONS — correctly spelled — from visibility.enabled and grant `create subjectaccessreviews` INDEPENDENT of apiTokenAccess (lens 1 measured the auth-delegator binding renders only when apiTokenAccess.enabled, default false — on a default install every reader would be permanently self and the feature would look broken; that grant is compatible with 'no write verb': a SAR creates no persistent object, and on the reference deployment system:auth-delegator already supplies it); chart tests for both belong to the operator-surface lens — none are duplicated here by name. UI notes: the amber .scope-banner/.scope-refusal tint is 8% --status-warning over the card (decorative; text on it is the already-vetted --text-secondary/--text-primary), and the proxy-off+restrictions-on combination makes personal endpoints 403 — local development must set viewRestrictionsEnabled: false, which the README/values comment (other lens) must say.
