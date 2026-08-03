# Namespace access report + PDF — design, for approval

> **PARKED — 2026-08-02.** Not rejected and not scheduled. The analysis is finished and the
> five open questions in §9 are still the gate; nothing here proceeds until they are
> answered. Kept because the expensive part is already done: the `--openshift-sar` answer in
> §1 is definitive, and the measurements behind §2 (no groups-forwarding in the proxy,
> `-pass-access-token` present, SA cannot create SARs) were taken off the shipped binary and
> the live cluster. Re-verify those three before building — a proxy upgrade could move them.
>
> **Re-verified 2026-08-02 on `ose-oauth-proxy-rhel9:v4.15`**, after the chart moved off the
> cluster's internal `oauth-proxy:v4.4` imagestream. All three still hold: `-pass-access-token`
> is present, there is still no groups-forwarding flag of any kind, and the SA still cannot
> create `subjectaccessreviews`. §2's conclusion is unchanged on the newer proxy.

**Status: proposed, not built.** Nothing in this document is implemented. It exists to be
approved, amended or rejected first.

The ask: *a tab where a user can run a namespace report that generates a PDF, protected with
`--openshift-sar` so a user can only report on their own namespaces, with a namespace selector
using toggle switches.*

Four of those five pieces are buildable close to as described. One is not, and it is the
security-critical one. That is the first section, because everything downstream depends on it.

This design was produced by two independent reviewers (codex gpt-5.6 and fey-fable-ultra)
working from a shared brief, plus measurements taken directly off the running cluster and the
shipped proxy binary. Where the reviewers disagreed, the disagreement and the measurement that
settled it are recorded in [§8](#8-where-the-reviewers-disagreed).

---

## 1. `--openshift-sar` cannot do this. The honest no.

**It cannot scope a user to their own namespaces.** Both reviewers reached this independently,
and the shipped binary's own help text is unambiguous:

```
-openshift-sar string
    require this encoded subject access review to authorize (may be a JSON list)
```

Three properties, each fatal on its own:

| Property | Consequence |
|---|---|
| The review is **fixed at deploy time** — the namespace is baked into the flag value | It cannot mean "whichever namespaces *this* user has". There is no request-time substitution |
| It is evaluated **once, at login**, for the **whole proxied app** | It admits or denies you from the entire dashboard. It cannot protect the report endpoint while leaving the rest authentication-only |
| It is not re-checked mid-session | Access revoked after login stays usable until the cookie expires |

**`-openshift-delegate-urls` is also a dead end**, which is worth recording because it looks
like the answer. It maps path prefixes to authorization checks, so a per-namespace prefix map
is superficially tempting. It fails twice: the `ResourceAttributes` namespace is still static
per entry, and — decisively — per the upstream README it applies **only to requests carrying
`Authorization: Bearer` or a client certificate**. Our report request is a browser `fetch`
with a session cookie (`index.html:498-504`), so it would never be evaluated against the map
at all. A 100-entry generated prefix map would gate nothing. Do not build it.

**What `--openshift-sar` remains good for:** a coarse front door — e.g. "you must be able to
`list groups` cluster-wide to enter this dashboard at all". That is already plumbed
(`values.yaml:530-533`, `deployment.yaml:202-204`) and stays as an optional operator knob. It
is a gate, not a scoping mechanism.

## 2. What actually works: the viewer's own token

The per-namespace decision has to happen **in the app**. The question is whose identity
answers it. Four options were weighed; three fail on measurement.

| Option | Verdict |
|---|---|
| Proxy-level SAR | Wholesale only — §1 |
| App creates a `SubjectAccessReview` **as the ServiceAccount**, identity from `X-Forwarded-User` | **Broken twice.** See below |
| Grant the SA **impersonation** | Largest possible privilege expansion for the smallest feature. Reject |
| **`-pass-access-token`, app calls `SelfSubjectAccessReview` with the *user's* token** | **Correct.** No new RBAC at all |

**Why the SA-side SAR fails — this is the subtle one, and it is the trap.** Two measurements:

```console
$ oc auth can-i create subjectaccessreviews --as=system:serviceaccount:group-sync-dashboard:group-sync-dashboard
no
```

That is a fixable grant. The second problem is not fixable:

```console
$ oc exec … -c oauth-proxy -- /usr/bin/oauth-proxy --help | grep -i group
  -openshift-group string
        restrict logins to members of this group (or groups, if encoded as a JSON array).
  -requestheader-group-headers value
        List of request headers to inspect for groups. X-Remote-Group is suggested.
```

**There is no flag that forwards the authenticated user's groups to the backend.**
`-openshift-group` *restricts logins* — it is an input gate, not a forward.
`-requestheader-group-headers` makes the proxy *read* groups from an authenticating proxy in
front of it (the kube front-proxy pattern) — also an input, and trusting it from a browser
would be a straightforward authorization bypass. The proxy forwards user and email, full stop.

So an SA-created SAR could only ever set `spec.user`, with `spec.groups` empty. **A SAR with no
groups under-authorizes**: it misses every permission the user holds *through a group* — and
group-derived permission is the entire access model this dashboard exists to audit. Nearly
every legitimate user would be denied. Filling `spec.groups` from the dashboard's own
`group_member` cache is worse than denying them: it turns an audit tool into an authorization
oracle running on 60-second-stale, incomplete data that knows nothing of virtual groups like
`system:authenticated`.

**The viewer-token path avoids all of it**, because the API server evaluates the real identity
with its real groups:

```console
$ oc auth can-i create selfsubjectaccessreviews --as=system:serviceaccount:…
yes          # SSAR is available to every authenticated identity (system:basic-user)
```

### The shape

1. **Proxy** adds `-pass-access-token` (verified present in the shipped v4.4 build). The app
   receives `X-Forwarded-Access-Token` on the upstream leg only. The browser never sees it, so
   the PLAN §9 principle at `api.py:1-5` — *the frontend never holds a cluster credential* —
   survives intact.
   **New invariant, to be written down and tested:** the token is used per-request for
   authorization calls only. Never stored, never logged, never included in any error path that
   dumps headers.
2. **Selector universe** — one `GET /apis/project.openshift.io/v1/projects` with the user's
   token. This is the canonical "namespaces this user can see" API (verified present on the
   cluster; it is what `oc projects` does). **One request at any cluster size** — no
   per-namespace fan-out to build the list.
3. **Entitlement at generation** — per *selected* namespace, one `SelfSubjectAccessReview` with
   the user's token for `list rolebindings` in that namespace. That is the honest gate, because
   rolebindings are exactly what the report contains. Note the default `view` and `edit`
   cluster roles do **not** include reading rolebindings; `admin` does. Project visibility alone
   would show "who has access to ns X" to every project member — so the rolebindings gate is
   the default, and loosening it is a conscious operator decision.
4. **Cluster-admin sees everything** — one cluster-scoped SSAR (`list rolebindings`, no
   namespace) unlocks the full universe and the cluster-scoped section of the report.
5. **Fail closed** (codex's enumeration, adopted verbatim — it is better than the alternative):
   `allowed: false` → 403. API error, timeout, malformed status, or a non-empty
   `status.evaluationError` → **503 with no report data**. No positive caching. Re-authorize
   every namespace at generation time. **Any single failed check rejects the whole
   multi-namespace report** rather than silently omitting a section — a report missing a
   namespace it should have covered is worse than no report.
6. **Proxy disabled → 403**, mirroring the existing pattern at `api.py:537-542`.
7. **Hosting cluster only in v1.** OAuth authenticates against the hosting cluster
   (`values.yaml:304-308`), so the viewer's token cannot answer entitlement questions about a
   remote cluster. Refuse reports for non-local clusters rather than mis-scope silently.

### The costs, stated plainly

* The session cookie grows — it now carries the access token. oauth-proxy chunks oversized
  cookies, but this should be watched on first deploy.
* **The app becomes a transit point for user credentials.** That is a genuine threat-model
  change, not a footnote, and it belongs in the PR description.
* Report generation now depends on API-server availability. Acceptable: the existing argument
  against per-read SARs (`values.yaml:283-285`) is about coupling *routine reads* to the API
  server. Report generation is an explicit, rare, user-initiated action.

Gating it: a new chart value **`oauthProxy.passAccessToken`, default `false`**, and the feature
reports itself disabled without it — so credential transit is an explicit operator opt-in, like
every other sensitive knob in this chart.

## 3. The app needs an authorization *layer*, not an endpoint check

**Operator's framing, and it is the right one: if we want proper RBAC, the app itself must have
authorization logic driven by OAuth — the way Spring Security does it.** §2 settles the
*mechanism*; this section settles the *structure*, because bolting a lone `if` onto the report
endpoint would not be RBAC. It would be one guarded door in a building with no walls.

### What exists today, measured

**One endpoint out of nineteen performs any authorization**, and it does it inline:
`dashboard_activity` (`api.py:515-555`) reads the identity header itself, checks
`oauth_proxy_enabled` itself, and applies the `self|all` policy itself. Every other endpoint is
*authenticated-therefore-authorized* — if you got past the proxy, you see everything.

In Spring terms: there is no `SecurityFilterChain`, no `Authentication` object, no
`AuthorizationManager`, and no deny-by-default. There is one hand-rolled check that happens to
be correct.

### The mapping

The Spring Security model translates almost exactly, and the translation is instructive because
one piece comes out *stronger* than the Spring default:

| Spring Security | Here | Note |
|---|---|---|
| `SecurityFilterChain` | One FastAPI dependency that resolves identity on every request | Replaces per-endpoint header reading |
| `Authentication` / principal | A `Principal` object: `user`, `email`, and the access token as the credential | Immutable, request-scoped |
| `GrantedAuthority` from a DB or JWT claims | **Nothing local.** Authority is resolved live from the Kubernetes API via SSAR | See below — this is the strong part |
| `@PreAuthorize("hasRole(...)")` | An `authorize(policy)` dependency declared per endpoint | Declarative, greppable, testable |
| `AuthorizationManager` | A `KubernetesAuthorizer` backed by `SelfSubjectAccessReview` | Pluggable; a `NullAuthorizer` covers proxy-disabled dev |
| `AccessDeniedException` → 403 | Fail-closed per §2.5 | 403 on deny, 503 on undecidable |
| Deny by default | Endpoints must name a policy; unnamed is a **test failure**, not an open door | See invariant A3 |

**The one place this beats a conventional Spring app:** in Spring you typically copy roles into
a local table or a JWT claim, and that copy drifts from the real authority. Here the authority
*is* the Kubernetes API server, asked live with the user's own token. There is no second copy of
the rules to go stale, and no group cache to be wrong — which matters especially for an
application whose entire purpose is auditing the accuracy of access data.

### Policies, and the deliberate restraint

The layer gets built; the *policies* stay conservative. Three exist in v1:

| Policy | Meaning | Applied to |
|---|---|---|
| `authenticated` | A verified identity exists | The 17 read endpoints — **the same effective access they have today** |
| `self_or_all` | The existing `userActivity.visibility` rule, moved into the layer | `dashboard_activity` |
| `can_read_bindings(ns)` | SSAR: `list rolebindings` in that namespace, with the viewer's token | The report endpoint only |

**Why most endpoints stay `authenticated` rather than SSAR-gated:** the chart already argues
against coupling routine reads to API-server availability (`values.yaml:283-285`), and that
argument is sound — an SSAR on every dashboard refresh would make the whole UI fail when the API
server is briefly slow, and would add latency to the hot path. Report generation is an explicit,
rare, user-initiated action, so it can afford the round trip.

The point of the layer is not to gate everything on day one. It is that **tightening any
endpoint later becomes a one-line policy change with a test**, instead of another hand-rolled
`if` — and that today's ad-hoc check stops being an exception and becomes an instance of a rule.

### Invariants — each one a test

**A1 — Identity has exactly one source.** The principal is resolved in one function, from proxy
headers only. `X-Forwarded-User` is never read anywhere else. With the proxy disabled the
principal is `None` and any policy above `authenticated` returns 403 — the app binds `0.0.0.0`
with no authentication in that mode, so an identity header is caller-supplied and worthless
(`api.py:535-542` already reasons this way; the layer generalizes it).

**A2 — The credential never escapes.** The access token lives on the request-scoped principal,
is passed only to authorization calls, and is never stored, logged, serialized into a response,
or included in an error path that dumps headers. A test asserts the token string appears in no
log record and no response body.

**A3 — Deny by default, enforced structurally.** A test enumerates every route on the app and
fails if any lacks an explicit policy. A new endpoint cannot ship unguarded by omission — which
is the failure mode a filter-chain design exists to prevent.

**A4 — Undecidable is not permitted.** Any authorizer error, timeout, malformed status or
`status.evaluationError` yields 503, never a permit and never a silent partial result (§2.5).

**A5 — The layer is testable without a cluster.** The authorizer is an interface; tests inject a
fake. This mirrors the existing `gsd/storage.py::StorageBackend` seam, which
`tests/test_storage_seam.py` already enforces.

### Cost

This is a larger change than the report feature it enables — it touches every endpoint's
signature, adds a module, and adds the deny-by-default route test. That is the honest price of
"proper RBAC" rather than one guarded endpoint, and it is worth paying **only if** the report
feature is approved, since nothing else currently needs it. If you would rather have the report
with a single inline check and no layer, say so and I will build that instead — it is smaller,
and it is the thing this section argues against.

## 4. PDF: render print-styled HTML, let the browser make the PDF

Both reviewers reached the same recommendation independently. The Python tree has **zero CVEs
today**, and that is a property worth defending.

| Candidate | Why not |
|---|---|
| **reportlab** | CVE-2023-33733 — CVSS 7.8 RCE via an `rl_safe_eval` sandbox bypass, public exploit released; CVE-2019-17626 before it. Not a currently-vulnerable tree, but a historically-exploited surface class. Also a low-level canvas API: every table, page break and footer becomes hand-maintained layout code |
| **WeasyPrint** | Pulls pango, cairo, gdk-pixbuf, fontconfig — C libraries absent from ubi9-minimal. The image grows an **OS-level** CVE surface no Python audit will ever see, making "zero CVEs in the Python tree" technically true and practically misleading. Worse: layout on a large report can spike past the **512Mi limit** (`values.yaml:96`), and an OOM kill takes down the poller — whose accumulated history is the only irreplaceable state in this system. The report feature must never be able to kill that process |
| **Headless Chromium** | Hundreds of MB, sandbox friction under an arbitrary high UID, memory far beyond budget. Not serious |

There is also a structural argument: whatever gathers the data must do it inside one
`@consistent` snapshot with no yield/await/streaming (`api.py:111-131`, enforced by
`tests/test_read_snapshot_scope.py`). A streaming PDF writer fights that rule head-on; a
fully-materialized JSON/HTML response fits it naturally.

**Recommendation: server-rendered report HTML with a print stylesheet; "Save as PDF" is
`window.print()`.** Zero new dependencies, zero image growth, zero CVE delta. Print CSS is no
longer the poor relation — Chromium 131 (Nov 2024) shipped `@page` margin boxes with `page`/
`pages` counters, so real headers, footers and "Page X of Y" are native in the browsers this
fleet uses. Firefox falls back to browser-generated headers; acceptable.

**What is genuinely lost** — the honest ledger, because two of these are operator decisions:

1. **Unattended generation.** No browser in the loop means no cron-mailed monthly PDF. Nothing
   in the ask requires it — but this is the one requirement that would justify a server-side
   generator, so it is **[open question A](#9-open-questions-for-you)**. If it ever
   materialises: WeasyPrint in a **separate CronJob container**, never in this pod.
2. **A byte-identical canonical artifact.** Each browser emits a slightly different PDF. Cheap
   mitigation: the server computes a **sha256 over the canonical report JSON** and prints it in
   the provenance block, and offers "Download .html" of the self-contained report. The `.html`
   is the canonical artifact; the PDF is a rendering of it that carries the hash.
3. **PDF/A.** Browsers do not emit archival PDF/A. If the records system demands it, that alone
   forces server-side generation — **[open question B](#9-open-questions-for-you)**.

## 5. Selector: keep the toggles as styling, not as layout

**Measured on this cluster: 100 namespaces, all 100 with binding data.** A wall of 100 toggle
rows is a full-page scroll where "select all" is 100 clicks and finding one namespace is a
visual grep. At several hundred it stops being a control.

The want — *one, several, or all of the namespaces I care about* — survives intact in:

* a **filterable checklist panel**: a search input, a scrollable list of **switch-styled rows**
  (the toggle *look* is styling and it stays), removable chips for the current selection, and
  two verbs — "Select all (N shown)" honouring the active filter, and "Clear";
* **the entitlement intersection doing most of the UX work**: the list is
  (user's projects ∩ namespaces the store has observed). The user entitled to 2 of 400 sees two
  rows. The scale problem exists only for the admin — who is exactly who the filter box serves;
* `(cluster-scoped)` as one visually distinct pseudo-entry (the `''` rows, `store.py:1241`),
  shown only to a viewer who passed the cluster-scope check;
* Generate disabled at zero selected. Nothing preselected.

**Universe = the store, not a new RBAC grant.** `DISTINCT binding_namespace` over
`rbac_group_binding` + `user_binding` (index already exists, `store.py:192-193`). The report can
only speak about what the poller observed; adding a `namespaces: [get, list]` grant would add
names the report has nothing to say about.

One consequence to **document rather than fix**: the report cannot distinguish *"no access
granted in ns X"* from *"ns X was never observed"*. Attesting the **absence** of grants is a
stronger claim than this data supports, and it needs the Namespace-list grant. That is
**[open question C](#9-open-questions-for-you)** — if you want absence attestation, the grant
is justified; until then it is not.

## 6. What the report says — structure by default, people by explicit switch

The framing that decides everything: today, PII exposure is bounded by authentication and a
browser tab.

> **Correction, 2026-08-02.** This section originally leaned on `values.yaml`'s claim that the
> dashboard *"shows nothing a user could not already read with `oc get groups`"*. That claim
> was wrong and has been removed from the chart: the dashboard reports the whole RBAC binding
> surface, not just group membership. The §5 conclusions do not change — if anything the case
> for minimising the export is stronger — but the premise no longer reads as it did. **A file that gets emailed has neither bound** — no authentication on a
forwarded attachment, no record of who read it. So the export defaults to access *structure*,
and membership rosters require an explicit, recorded switch.

### Provenance block, page one — without this it is a screenshot, not evidence

* Classification/handling marking; cluster id + API URL (`store.py:33`).
* **Generated at** (UTC) and **generated by** (`X-Forwarded-User`, noted as proxy-verified) —
  the requester is part of the evidence chain.
* Dashboard version + git commit, **including the `dirty` flag** (`api.py:558-573`) — a
  compliance artifact from an unreproducible build should say so.
* **Data freshness, split by kind** — the part a screenshot can never carry:
  * *snapshot* data (bindings, groups, member counts): "as observed at last poll `<ts>`;
    bindings refresh every 300s" (`values.yaml:179`) — current as of the poll, not live;
  * *accumulated* data (membership/sync timeline): "covers only the period since this dashboard
    began observing — earliest event `<ts>`" (already stamped at `api.py:240`, `api.py:420`).
    Without this an empty timeline reads as "nothing ever changed".
  * A **poll-failure banner** if the last poll failed.
* **The direct-bindings-only caveat, verbatim from the code's own discipline** (`api.py:291-293`,
  `store.py:1126`): role rules are never expanded — **this is not an effective-permissions
  calculation**. On an artifact titled "who has access", omitting that line converts an honest
  report into misleading evidence.
* Scope, methodology and exclusions; sha256 of the canonical payload; "Page X of Y".

### Body — findings before inventory, deterministically sorted

Sort by namespace, then severity, then subject, then binding — so two runs diff cleanly.

1. **Findings first**: `dangling` (grants nobody, `store.py:1184`); `unmanaged` (governance
   bypassed by hand, `store.py:1195-1201`, showing `exception` acknowledgements); and **direct
   user bindings** (`store.py:1256`+) — the usernames here *are* the finding and the migration
   worklist, and they belong in the export.
2. **Operator reconcile health** per namespace (`operator_config_state`).
3. **Group-based grants**: binding, role, group, `managed_source` provenance, and the member
   **count** (`store.py:88`) — count, not roster.
4. **Cluster-scoped grants that also apply**: the full list only for a viewer who passed the
   cluster-scope check; for everyone else a **count plus a note**. Silently omitting them makes
   the access review false — cluster-admins genuinely do have access to the namespace — while
   listing them to a namespace-scoped viewer leaks identities the API would not show them.
   Count-with-note threads that needle.

### Opt-in, default OFF

Membership roster expansion. A real access-review campaign does eventually need resolved
people, so the capability must exist — but it multiplies names per page, so it is a deliberate
choice **recorded in the provenance block** ("includes membership rosters: yes"). Same for the
membership-change timeline, with its coverage disclaimer.

### Never in the export

Dashboard usage/activity data (personnel data the code already treats differently —
`api.py:524-533`, `store.py:234-241`); user emails (the report needs identities, not contact
details); raw error text that could carry secrets; any data for a cluster other than the one
that authorized the request.

## 7. Scope

**Build (v1)**

- One **Report** tab.
- Universe = store namespaces ∩ user's projects; filterable checklist with switch-styled rows.
- `GET /api/clusters/{id}/report?namespaces=…` — fully materialized JSON under `@consistent`.
- A print-stylesheet report view; "Save as PDF" is `window.print()`; "Download .html" for the
  canonical artifact.
- The §6 provenance block.
- **The §3 authorization layer**: one identity resolver, declarative per-endpoint policies, a
  `KubernetesAuthorizer` backed by SSAR, deny-by-default enforced by a route-enumeration test.
  Existing endpoints move to the `authenticated` policy — same effective access as today.
- Authz via `-pass-access-token` + per-namespace SSAR with the viewer's token; fail closed per
  §2.5; 403 without the proxy; hosting cluster only.
- New chart value `oauthProxy.passAccessToken`, default `false`.
- Read-only throughout. The SA is deliberately read-oriented (`rbac.yaml:1-3`), and the audit
  write experiment (`docs/unmanaged-audit-design.md:59-107`) already demonstrated the cost of
  exceeding that boundary.

**Defer** — rosters default-on; server-side PDF; the Namespace-list grant; external-cluster
reports; scheduled/emailed reports; positive SAR caching; template customization.

**Say no to, by name** — `--openshift-sar` as the per-namespace mechanism (§1);
`-openshift-delegate-urls` for this purpose (§1); a flat toggle wall at 100+ namespaces (§5);
reportlab / WeasyPrint / headless Chromium inside this pod (§4); impersonation or
`create subjectaccessreviews` grants to the read-only SA (§2).

## 8. Where the reviewers disagreed

Recorded because the resolutions are load-bearing, and because in each case a **measurement**
settled it rather than an argument.

**7.1 — codex left a go/no-go fork that the measurements had already closed.** Codex correctly
identified that an SA-side SAR needs complete, trustworthy groups, then conceded no trustworthy
source exists, and concluded: *verify the proxy forwards groups, or verify `-pass-access-token`;
if neither, defer the feature.* Both branches were resolvable, and I re-verified both against
the shipped binary rather than trusting either reviewer:

* groups forwarding is **structurally absent** from ose-oauth-proxy — not merely unverified
  (§2). codex's own example SAR carried `groups: [team-a]  # complete trusted authn groups`;
  that comment is load-bearing and **nothing in this deployment can satisfy it**;
* `-pass-access-token` **is present** in this build.

So the answer is not "defer" — it is the viewer-token path, now. **Resolution: fable.**

**7.2 — should the SA get `list namespaces` by default?** codex called the binding-derived
universe incomplete and prescribed the grant. fable argued the store universe is the honest
default and the grant only buys *absence attestation* — a stronger evidentiary claim the
operator should choose deliberately. fable is right that they are different claims; codex is
right that the limitation must be visible. **Resolution: fable's default, codex's disclosure** —
store-derived universe, with the limitation printed in the report's coverage note, and the
grant offered as [open question C](#9-open-questions-for-you).

codex's related worry about ~400 SAR round-trips also dissolves: it is an artifact of the
SA-side framing. With the viewer's token the universe is **one** `projects` call — an API its
analysis missed — and SSARs run only for the handful of namespaces actually selected.

**7.3 — group rosters in the export.** codex excluded them outright; fable argued for opt-in
with the choice recorded. **Resolution: fable.** Banning rosters guarantees the operator falls
back to screenshots — the exact artifact this feature exists to retire. Default off, recorded
in provenance when on.

**Adopted from codex verbatim**, as better than the alternative: the fail-closed error
enumeration (§2.5), deterministic sort order, the raw-errors-may-contain-secrets exclusion, the
poll-failure banner, and handling-guidance marking on the artifact.

## 9. Open questions for you

**A. Does a report ever need to generate unattended** — a monthly PDF mailed by a CronJob? If
yes, that is the one requirement that justifies a server-side renderer, and it should shape v1
(as a separate CronJob container, never this pod). If no, `window.print()` is strictly better.

**B. Does anything consume these as archival PDF/A?** Browsers cannot emit it. Same consequence
as A.

**C. Do you need to attest the *absence* of grants** in a namespace — "ns X has no access
configured" as a positive claim? That requires the `namespaces: [get, list]` grant. Without it
the report can only say "no grants observed", which is a weaker statement.

**D. Confirm the §3 authorization layer is in scope.** You raised it, and I have designed for
it, so I am treating it as approved-in-principle — but it is the largest single piece of this
proposal and it touches all 19 endpoints. The alternative is one inline check on the report
endpoint. I recommend the layer; I want it stated rather than assumed.

**E. Is the rolebindings-read gate the right bar?** It means a plain `view`/`edit` user cannot
report on their own namespace — only `admin` and above can, because `view` does not include
reading rolebindings. The alternative is gating on project visibility, which lets any project
member see who else has access. My recommendation is the stricter default, but this is a policy
call that is yours.
