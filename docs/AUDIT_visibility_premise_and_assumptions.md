# Audit brief: the premise, what we built, and what to distrust

Branch `feat/per-user-visibility`, head `509dfc2`, 16 commits, +10,873/−118 across 30 files.
Suite **1230 passed / 0 failed**
(`cd local-development && /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py`).
Live on CRC at revision 105 (`0.6.0-39f61286b9`) — that image predates the last three commits.

§1–§4 are the premise: what this is, what we added, and why. §5 is what to attack. §6 is the
scope fence. Findings go in §7 of **this file**.

---

## 1. What the dashboard is

An OpenShift RBAC governance dashboard. It polls one or more clusters with its own
ServiceAccount and reports: which Groups exist and who is in them, which RoleBindings and
ClusterRoleBindings grant what to whom, which GroupSync CRs are syncing and which have stopped,
who has logged in and why a login failed, and which grants bypass the policy operator.

**The founding asymmetry, and the reason any of this is hard:** the dashboard reads the cluster
with a privileged ServiceAccount, but its *readers* are ordinary people who arrive through an
oauth-proxy. Until this branch, every authenticated reader saw everything the ServiceAccount
could see. A reader with no `oc` permissions at all could read the whole RBAC surface, every
group's membership, and every login failure by name.

So this work is **a fix for an over-exposure**, not a feature. That framing matters for the
audit: a regression here is not "a feature stopped working", it is "the exposure came back".

## 2. What we added, and the measurement behind each

Every item here exists because something was measured, not because it seemed sensible.

| # | what | why — the measurement |
|---|---|---|
| 1 | **Per-reader scoping**, on by default | Eight resources a plain user cannot `oc list` were being served to them, plus named login failures |
| 2 | The tier decided by a **SubjectAccessReview**, not a role-name list | A name list misses `cluster-reader` and every custom role granting the same read |
| 3 | The review carries **`spec.groups`**, not just `spec.user` | Measured: a cluster-admin whose grant arrives through a Group is answered `allowed=false` when groups are omitted — that is *every* real administrator on the reference cluster, so omitting them would invert the feature |
| 4 | **Fail closed** everywhere; only the exact string `"all"` widens | An indeterminate answer that widened would be an exposure triggered by an outage |
| 5 | A **60s cache**, failures never cached | 97ms per resolution for the 65-group reference cluster; caching an error would let an outage pin every reader to the narrow view |
| 6 | **Overview, Access granted, RBAC policy are administrator-only** (reversing our own spec Q3) | Q3 called binding findings "data about objects, not people". Measured: `lateef.o`, who cannot `oc list` clusterrolebindings/rolebindings/groups, was handed 236 rows, 21 naming an admin role — a list of which group to join to gain admin, obtainable here and not with `oc` |
| 7 | `groupsyncs` deliberately **not** gated | `/metrics` is unauthenticated by design and already publishes per-CR identity and state to a credential-less curl. Gating the API while the metric is public is theatre |
| 8 | The **alert feed is an allow-list**, and two kinds were removed from it | The list's own invariant is "every kind here has a page behind it". After #6, two kinds had no page — a reader 403'd from `/bindings/findings` was handed a group→role row by `/api/alerts` in the same session |
| 9 | A **second, stricter tier for the Usage tab** | Usage is the only dataset that cannot be reproduced with `oc` — it lives in the dashboard's own sqlite. Every other wide view is obtainable by anyone passing the wide check. And no *read* check separates `cluster-admin` from `cluster-reader`, so the second threshold asks a write verb |
| 10 | Refusals name **no route in** | The card is read by the person being refused, who cannot act on a chart key and should not be handed the name of the permission that would lift the restriction |
| 11 | Chart **refuses** `visibility.enabled=true` with `oauthProxy.enabled=false` | `X-Forwarded-User` is whatever the caller typed when nothing sets it; a control that silently cannot work is worse than one that refuses to install |
| 12 | **Two configured values that never reached the review**, fixed in `509dfc2` | See §4 — these are the reason this audit exists |

## 3. The design in one paragraph

The oauth-proxy answers "may you in at all" and sets `X-Forwarded-User`, which the app trusts
only because the app binds the pod's loopback and the Service targets the proxy. Per request,
`viewer_scope()` turns that header into `(viewer, "all" | "self")` by asking a `TierResolver`,
which posts a SubjectAccessReview carrying the reader's freshly-read Group memberships plus the
two virtual auth groups. `require_admin_tier()` turns `self` into a 403 for the three
cluster-facing views. `usage_scope()` does the same with a second, independent resolver and a
stricter threshold for the Usage tab alone. Handlers pass the viewer into the store as a bound
query parameter; the UI renders `scope`/`viewer` off the wire and never computes a tier.
Full detail: `docs/ACCESS_CONTROL.md`.

## 4. The two defects that prompted this audit — the pattern to hunt

Both were **configured values that never reached behaviour**, and both survived a passing suite.

**(a) The TTL was masked by a duplicate default.** `kube.TIER_TTL_SECONDS = 60.0` was the
constructor default while `config.py` separately declared `60`. Nothing passed the setting
through, so the resolver used its own identical 60 and the knob did nothing. Every test that
exercised the *default* agreed with the bug, because both halves said the same number. Measured
before the fix: deleting `ttl_seconds=` from the usage construction left the suite **green**.

**(b) The subresource was parsed and dropped.** The chart's guard *accepts*
`adminSar.resource: pods/log`; `Settings` split it into `resource='pods'`, `subresource='log'`;
the review sent `{'verb':'get','resource':'pods','group':''}`. An operator narrowing the
threshold got a **different permission checked**, possibly a broader one, silently.

Found by asking of every `Settings` field: *does anything outside `config.py` read this?* 42
fields, 2 inert. That audit is now clean — but it is one shape of the question, and only for
`Settings`.

**The generalised pattern to hunt: a value, flag, key or branch that exists, is documented or
configurable, and does not change behaviour.** Also its inverse: an assertion that would pass
whether or not the code works.

## 5. What this audit must do

Prefer refutation, and prefer *measuring* to reading. For each item, one verdict —
**CONFIRMED**, **REFUTED**, or **FIX-INADEQUATE** — and the command you ran.

- **A1 — Inert configuration, beyond `Settings`.** Chart values that render nothing; ConfigMap
  keys the app never reads; env vars documented but unread; helper templates defined and never
  included; `values.yaml` keys with no consumer. Both directions: a key with no reader, and a
  reader with no key.
- **A2 — Inert code.** Functions, branches, constants and exports that nothing reaches. Two are
  already known and are NOT findings: `data.alertsScope` is set by the loader and consumed by no
  renderer, and `kube.TIER_SELF`/`TIER_ALL` are exported while `api.py` uses the string
  literals. Say if either is worse than it looks; otherwise find new ones.
- **A3 — Vacuous assertions.** Tests that pass whether or not the behaviour holds. The
  technique that found (a): mutate the implementation and check the test actually fails.
  Prioritise the security-relevant ones — fail-closed, the 403 gates, the alert allow-list, the
  self-scoped store queries. **A test whose mutation does not fail it is a finding.**
- **A4 — Validate MY RECENT FIXES specifically**, at `ec52fbb` and `509dfc2`. I am the least
  reliable reviewer of these. Check: is `VISIBILITY_TIER_TTL_DEFAULT` genuinely single-source
  now; do the two required constructor arguments actually prevent the silent-default failure, or
  merely move it; does the subresource reach the API server in the shape the API server expects
  (`resourceAttributes.subresource`, absent when empty — verify against the Kubernetes
  authorization API, not against my assertion); does the new behavioural TTL test fail for the
  right reason under mutation of BOTH resolvers; is the new `visibility.tierTtlSeconds` values
  key nil-safe and guarded on every path.
- **A5 — The premise itself.** §2 claims each addition is justified by a measurement. Attack any
  you think does not hold, especially: is the Usage tab genuinely irreproducible with `oc`
  (#9)?; is `groupsyncs` genuinely fully public on `/metrics` (#7)?; does the write-verb
  threshold genuinely separate the two roles on a stock cluster rather than only on CRC (#9)?
- **A6 — Anything new.** Attacker's eye: what does a self-tier reader still learn that they
  could not learn with `oc` as themselves?

Every finding: `file:line-or-symbol`; a concrete trigger; the consequence stated as **what a
reader or operator would believe that is false**; the complete replacement code ready to apply;
and a test that fails before and passes after. Comments say WHY and cite measurements — a
replacement that strips the reasoning is a regression even when its logic is right.

## 6. Scope fence

**Enhancement, not redesign.** The tier mechanism, the two thresholds, the fail-closed rule and
the refusal wording are settled and are not up for re-architecture. Fix what is inert, wrong or
unproven inside that design.

Out of scope: renaming or restructuring the `visibility.*` values surface; changing the default
thresholds; changing which tabs are administrator-only; adding features. If you believe one of
those is necessary, write it as a finding with the measurement and leave the code alone.

**This pass is REVIEW ONLY.** Findings into §7 below under `> **Fable:**` markers. Change no
code — I apply, or I hand the application back to you with instructions, after reading.

Do not commit, rebuild, redeploy, or mutate cluster RBAC. Read-only against the cluster;
SubjectAccessReview creates are queries and are fine. Throwaway scripts under `/tmp`, never in
the worktree.

---

## 7. Findings
