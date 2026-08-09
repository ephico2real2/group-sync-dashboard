# Requirements — per-user visibility

**Requirements only. No solution is specified here** — that is the job of the spec this document
feeds. Where a measurement constrains the solution space it is recorded, because a spec written
without these facts would propose something the cluster refuses.

Origin: a suggestion from Olawale (senior architect) that by default a reader should see only what
belongs to them, while an administrator sees everything, tied to OpenShift's own roles rather than to
a scheme invented here.

Measured on the reference cluster, 2026-08-09.

---

## 1. The problem, and it is not the one the suggestion describes

The suggestion reads as an enhancement. It is a **fix**, and the measurement is the reason.

This dashboard's standing justification for showing everything to everyone is that a reader "could
read this with `oc` anyway". That is **false for a plain authenticated user**. Asked as the lab's
ordinary LDAP user:

| `oc auth can-i list …` | plain user | cluster-admin |
|---|---|---|
| `groups.user.openshift.io` | **no** | yes |
| `users.user.openshift.io` | **no** | yes |
| `rolebindings.rbac.authorization.k8s.io` | **no** | yes |
| `clusterrolebindings.rbac.authorization.k8s.io` | **no** | yes |
| `groupsyncs.redhatcop.redhat.io` | **no** | yes |
| `namespaceconfigs.redhatcop.redhat.io` | **no** | yes |
| `pods` | **no** | yes |
| `oauths.config.openshift.io` | **no** | yes |

Eight for eight. The mechanism is not subtle: **the dashboard reads the cluster with its own
ServiceAccount token**, so every authenticated reader sees the ServiceAccount's view rather than their
own. Anyone who can log into the cluster currently sees the complete RBAC surface — every group's
membership, every person's grants, every namespace finding — plus the login record, which includes
who failed to authenticate and why.

So the requirement is not "add a nicety for tidiness". It is: **stop showing a reader data they have
no cluster permission to see.**

## 2. What a reader is entitled to see about themselves

"Their own info" has to be enumerated before it can be scoped. Endpoint by endpoint, what a
self-scoped reader legitimately wants:

| endpoint | today | self-scoped |
|---|---|---|
| `/api/clusters/{c}/users/{name}` | any named user's full profile | **their own** profile only |
| `/api/clusters/{c}/groups` | every group and its members | groups **they belong to** |
| `/api/clusters/{c}/groups/{name}` | any group's members | only groups they belong to |
| `/api/clusters/{c}/users` | every user | **their own** entry only |
| `/api/clusters/{c}/user-bindings` | every user's grants | **their own** grants |
| `/api/clusters/{c}/logins` | every login attempt, named, with failure causes | **their own** attempts |
| `/api/clusters/{c}/cluster-access` | who is and is not in the gate group | **their own** gate status |
| `/api/clusters/{c}/bindings/findings` | unmanaged-grant findings, cluster-wide | governance data; see §6 Q3 |
| `/api/clusters/{c}/membership-changes` | who joined and left which group, when | changes **affecting them** |
| `/api/clusters/{c}/groupsyncs` (+events) | operator CR health | not personal data; see §6 Q3 |
| `/api/clusters/{c}/operator-configs` | operator configuration | not personal data |
| `/api/dashboard/activity` | who used the dashboard, when | **already self-scoped by default** |
| `/api/alerts` | derived counts | depends on the above |
| `/api/whoami` | the caller's own identity | unchanged |

Two observations that shape the requirement:

- **`/api/dashboard/activity` already does this.** `userActivity.visibility` defaults to `"self"`
  precisely because "the response is identifiable personnel data — who was present, when, and how
  much — and the dashboard's usual *you could read this with oc anyway* argument does not cover it."
  The reasoning generalises; the setting does not. That is the inconsistency to resolve.
- **`/logins` is the most sensitive endpoint in the application.** It names a person and states that
  their password was wrong, expired, or that their account is locked. It has no self-scoping today.

## 3. The privilege tiers wanted

Three, not four. `edit` is explicitly out of scope: this dashboard writes nothing that a reader could
edit.

| tier | sees | expected population |
|---|---|---|
| **self** | only what belongs to them | every authenticated reader, by default |
| **all** | everything, as today | cluster administrators, platform/governance team |
| **none** | nothing; not admitted at all | already available via `oauthProxy.sar` |

The third tier already exists and is not part of this work: `oauthProxy.sar` puts a
SubjectAccessReview in front of the whole dashboard, so a deployment can already require *some*
permission merely to open it. What is missing is the distinction **between** admitted readers.

## 4. Primitives available, measured

Any solution must be built from these. Each was verified rather than assumed.

**The dashboard's ServiceAccount can already perform a SubjectAccessReview.**

```
oc auth can-i create subjectaccessreviews --as=system:serviceaccount:group-sync-dashboard:group-sync-dashboard
  -> yes
```

It comes from `system:auth-delegator`, which the chart already binds for the oauth-proxy's
`-openshift-delegate-urls` feature and which grants exactly `create tokenreviews` and
`create subjectaccessreviews`. **So asking "may this user see everything?" needs no new grant.** This
is the single most important fact for the spec: the expensive-looking part is already paid for.

**A plain user can ask about themselves, but the app cannot ask on their behalf.**

| capability | plain user | dashboard SA |
|---|---|---|
| `create selfsubjectrulesreviews` | **yes** (via `self-access-reviewer`) | — |
| `create subjectaccessreviews` | **no** | **yes** |
| `get users` with `resourceNames: ["~"]` | **yes** (via `basic-user`) | — |

`SelfSubjectRulesReview` would be the natural "what may I do?" call, but it answers *as the caller*
and therefore needs the caller's token — which the application deliberately does not hold (§5). So
the app's route is `SubjectAccessReview` naming the user, as its own ServiceAccount.

**The `admin` / `edit` / `view` roles do NOT discriminate — measured.** The suggestion assumes the
dashboard can lean on OpenShift's `admin`, `edit` and `view` roles, with `view` as everyone's default
and `admin` seeing all. It cannot, and the reason is structural: those three are **namespace** roles,
and none of them grants the cluster-scoped reads this dashboard reports on. Bound cluster-wide with
`oc adm policy add-cluster-role-to-user`, they still answer `no`:

| role bound to a probe user | `list groups` | `list users` | `get users/~` | tier under a verb rule |
|---|---|---|---|---|
| *(plain authenticated user)* | no | no | **yes** | self |
| `view` | no | no | yes | self |
| `admin` | no | no | yes | self |
| `cluster-reader` | **yes** | **yes** | yes | **all** |

Two consequences the spec must carry. **`cluster-reader` is the natural administrator tier**, not
`admin` — it reads everything and changes nothing, which is exactly the governance reader this
dashboard serves; `cluster-admin` also qualifies, by holding everything. And **`get users/~` is
universal, so it is a floor rather than a discriminator** — every authenticated reader has it. The
discriminating verb is `list`.

(Fable was asked to verify this independently rather than inherit it, so the spec should either
corroborate the table or contradict it with evidence.)

**OpenShift already expresses "you may read yourself".** `basic-user`, bound to
`system:authenticated`, grants `get users` restricted to `resourceNames: ["~"]`. Every authenticated
reader therefore already holds a cluster permission that means precisely *"may read own identity, may
not read anyone else's"* — which is the self tier, expressed in the platform's own vocabulary rather
than a parallel one.

**The dashboard already knows who is privileged.** It reads `ClusterRoleBindings` and `RoleBindings`
and resolves group membership; the "Access granted" tab is built on exactly that. So a second route
to the same answer exists that requires no API call at all — with the caveat that it is the
dashboard's *polled* view, not a request-time authorization decision.

## 5. Constraints any solution must respect

These are standing rules of this codebase, each with a reason that has already cost something to
learn.

1. **The ServiceAccount holds no write verb on anything the dashboard reports on.** `create
   subjectaccessreviews` is compatible with this — it creates no persistent object and is an
   authorization query — but the spec must say so explicitly rather than leave a reader to wonder.
2. **The app does not hold the user's token.** `-pass-access-token` was added and then removed after
   measurement: the ServiceAccount-as-OAuth-client's tokens carry scope
   `["user:info","user:check-access"]`, and forwarding a user credential to a read-only dashboard
   widens it for no gain. Any solution requiring the user's bearer token is therefore refused unless
   it argues that trade afresh.
3. **Identity comes from the proxy, and only from the proxy.** `X-Forwarded-User` is trusted only when
   `oauthProxy.enabled`; with the proxy off the app binds `0.0.0.0` unauthenticated and that header is
   whatever the caller typed. `/api/whoami` already encodes this and must keep doing so. A visibility
   decision derived from an untrusted header would be worse than no visibility control.
4. **Fail closed.** If the tier cannot be determined — the SAR errors, times out, or the answer is
   ambiguous — the reader gets the **self** view, never the **all** view. A control that fails open is
   not a control.
5. **No new dependency, no build step**, one self-contained `index.html`, strict CSP, WCAG 2.1 AA in
   both themes, chart comments use `#`, comments say WHY not WHAT.
6. **`/metrics` stays unauthenticated and therefore stays aggregate.** No username may become a label,
   and per-user scoping must not tempt anyone to add one.
7. **Performance.** A SAR per request per reader is an extra API call on a page that polls every 30
   seconds. The spec must state what is cached, for how long, and what a revoked administrator's
   worst-case window of retained visibility is.

## 6. Open questions the spec must answer

**Q1 — How is the tier decided, and against which resource?**
The candidates are not equivalent and the spec should compare them on evidence, not taste: a
`SubjectAccessReview` naming the user against a resource the dashboard actually reports on (`list
groups`? `list clusterrolebindings`?); a check against an **app-defined ClusterRole** bound by the
operator; or derivation from the binding data already polled. Kiali is the closest prior art and uses
the first: it distinguishes **`list` (see everything) from `get` (see only the named thing)** on a real
resource, and ships two ClusterRoles — `kiali-namespace-authorization` and
`kiali-all-namespaces-authorization` — so an administrator has a clean surface to bind. It also offers
`require_namespace_get: true` for deployments that decline to trust `list` alone. Note that the
verb-pair idea maps onto our case without invention: `get users/~` is already every reader's
self-permission and `list users` / `list groups` is already an administrator's.

**Q2 — Does the app define its own ClusterRoles, and what do they contain?**
Piggy-backing on OpenShift roles is the stated preference, and the spec should say what that means
concretely. A role whose rules are the *real* resources the dashboard reports on makes the app's
authorization mirror the cluster's, so "you could read this with `oc` anyway" becomes true rather than
aspirational. A role over a *fictional* resource is a capability flag and nothing more. Both are used
in the wild; they have different failure modes and different audit stories.

**Q3 — What about data that belongs to nobody?**
GroupSync CR health, operator configuration, and unmanaged-grant findings are governance data, not
personal data. Self-scoping them to nothing would make the dashboard useless to a non-admin; showing
them in full may be exactly right. The spec must rule per endpoint and justify each, because this is
where an over-broad rule would destroy the product's value and an over-narrow one would leak.

**Q4 — Is `cluster-admin` special, or merely one binding among many?**
"Admin" in the suggestion means cluster-admin or an OpenShift admin role. The spec should say whether
the tier is decided by a *capability* (can you list groups?) or by *role membership* (are you bound to
`cluster-admin`?). The first survives a cluster that grants the capability by another route; the
second is easier to explain to an auditor. It should also state what happens for `cluster-reader`,
which can read everything but change nothing.

**Q5 — What does a self-scoped reader see where a value is aggregate?**
Counts, KPIs and the alerts feed are computed cluster-wide. "3 groups have zero members" is not
personal data but it is derived from data the reader may not see. The spec must decide whether
aggregates are shown, suppressed, or recomputed over the visible subset — and note that recomputing
changes what the number *means*, which the UI would then have to say.

**Q6 — How does the UI show that a view is narrowed?**
A dashboard that silently shows one row where an administrator sees two hundred invites the reader to
conclude the cluster is nearly empty. Precedent exists in this codebase: the Groups tab distinguishes
"none match your filter" from "none exist", and the search box was specifically fixed for claiming
credit for hiding rows it was not hiding. The spec must say what the narrowed state *says*.

**Q7 — Where is the decision enforced?**
At the API, in the store queries, or in the UI. The spec must place enforcement at exactly one layer
and say why the others are not it — a UI-only narrowing is not a control, and an endpoint that returns
everything while the page hides most of it is a data leak with a cosmetic fix.

**Q8 — What is the migration, and what is the default?**
Today's behaviour is "everyone sees everything". Turning that off by default changes what existing
deployments show on upgrade. The spec must state whether the default is `self` (safe, surprising) or
`all` (compatible, leaves the exposure in place), and how an operator is told.

## 7. Non-goals

- **No `edit` tier.** The dashboard writes nothing a reader could edit.
- **No per-namespace scoping model.** The dashboard's unit is a person and a group, not a namespace.
- **No change to how the dashboard reads the cluster.** It continues to read as its ServiceAccount;
  this is about what it *shows*, not about impersonation.
- **No user-token forwarding**, per §5.2, unless the spec argues that trade explicitly.
- **Not a login gate.** Admitting or refusing a reader entirely is `oauthProxy.sar`, and it already
  works.

## 8. Definition of done

1. A plain authenticated reader sees only their own profile, their own groups, their own login
   attempts, their own grants and their own gate status — asserted by test, per endpoint.
2. A cluster administrator sees exactly what they see today — asserted by test, per endpoint.
3. The tier is decided from a cluster permission rather than from a header, a values list of
   usernames, or the app's own guess.
4. An indeterminate answer yields the **self** view, with a test that forces the failure.
5. The narrowed state is legible in the UI: the reader can tell "this is your view" from "this is
   everything".
6. No new ServiceAccount write verb on anything the dashboard reports on.
7. `/metrics` is unchanged and still carries no username.
8. The decision's caching window is documented, and so is the worst-case interval during which a
   revoked administrator retains the wider view.

---

# Decisions taken, 2026-08-09

These are settled. The spec implements them rather than re-opening them.

## D1 — On by default, with one switch

Restrictions are **ON** by default. This is a fix for an exposure (§1), and shipping a fix off by
default leaves the exposure in place on exactly the installs that never read release notes.

One values key, one environment variable, wired into the core logic rather than the UI:

```
visibility.enabled: true        # values.yaml
  → GSD_ENABLE_VIEW_RESTRICTIONS=true
```

(The operator wrote `GSD_ENABLE_VIEW_RESCRICTIONS`; the correct spelling is **RESTRICTIONS** and is
used throughout. An environment variable name is load-bearing — a typo here is a silently disabled
security control, which is the worst failure this feature can have.)

`false` restores today's behaviour for a deployment that needs it, and must be a deliberate,
documented choice — not a fallback the code reaches for when something else fails. Requirement §5.4
still governs: an *indeterminate* answer means the self tier, never the wide one.

## D2 — The administrator threshold is CHOOSABLE, and here is what each choice buys

The operator grants people different cluster-wide roles and must be able to pick which of them counts
as a dashboard administrator. Measured with probe users bound cluster-wide via `ClusterRoleBinding`,
against every capability that could serve as the threshold:

| role bound cluster-wide | `list groups` | `list users` | `list clusterrolebindings` | `list rolebindings` | `get pods/log` in `openshift-authentication` |
|---|---|---|---|---|---|
| `cluster-admin` | yes | yes | yes | yes | yes |
| `cluster-reader` | yes | yes | yes | yes | yes |
| `admin` | no | no | no | **yes** | yes |
| `edit` | no | no | no | no | yes |
| `view` | no | no | no | no | yes |
| *(plain user)* | no | no | no | no | no |

**First: `cluster-edit` and `cluster-view` do not exist.** Verified — the cluster ships `cluster-admin`
and `cluster-reader`, and `admin`/`edit`/`view`. What is colloquially called "cluster-view" is `view`
bound cluster-wide, and the table shows what that is worth here.

Three thresholds are therefore meaningful, and the operator chooses:

| threshold | admits | use when |
|---|---|---|
| `list groups.user.openshift.io` **(default)** | `cluster-admin`, `cluster-reader` | the wide view should mean "can already read this with `oc`" |
| `list rolebindings.rbac.authorization.k8s.io` | the above **plus** cluster-wide `admin` | project administrators should see everything |
| a custom SubjectAccessReview | whatever the operator's own role grants | an app-defined or site-specific role |

**`edit` and `view` cannot be a threshold** using anything this dashboard reports on: they grant
nothing cluster-scoped, and they are indistinguishable from a plain user across all four `list`
capabilities. If people holding those roles must see everything, the only honest routes are an
app-defined ClusterRole the operator binds, or `visibility.enabled: false`.

So the values surface must express the check itself — API group, resource, verb, and optional namespace
— with the default above, rather than hardcoding one question. A named-role list is rejected: it would
miss `cluster-reader` unless spelled out, and miss every custom route entirely (spec §Q4).

## D3 — One measured finding that bears on `/logins` specifically

`get pods/log` in `openshift-authentication` is **yes** for `admin`, `edit` and `view` bound
cluster-wide. Those readers can therefore read the oauth-server's logs directly with `oc` — which is
the *source* of every row on the Logins tab. So for that endpoint, and only that endpoint, the "you
could read this with `oc` anyway" argument is true for a wider population than the four `list`
capabilities suggest.

The spec must rule on whether that changes the scoping of `/logins`. It does not change the default:
the raw log is not the parsed, searchable, retained record, and the requirement in §2 stands that
`/logins` is the most sensitive endpoint in the application. But an operator arguing for a looser
threshold on that tab has a real measurement behind them, and the spec should say so rather than
leaving it to be rediscovered.
