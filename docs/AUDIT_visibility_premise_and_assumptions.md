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

> **Fable:** Method. Copied `local-development/` to a throwaway tree and ran a 24-mutation
> harness (`scratchpad/mutate.py`): mutate one implementation line, run
> `test_visibility.py + test_view_scoping.py + test_visibility_tier.py`, restore, record
> KILLED / SURVIVED. **23 of 24 killed; one survived and is FINDING F1.** RBAC and API facts
> measured live against CRC as kubeadmin (SubjectAccessReview creates only). Chart facts from
> `helm template` + `oc get`. Every command below was run before the claim was written.
>
> **Verdict per item**
> - **A1 (inert config beyond Settings) — REFUTED for the visibility surface, one inert helper found (F3).**
>   `values.yaml`↔templates cross-referenced both directions programmatically (every leaf vs every
>   `.Values.*`): zero unreferenced keys, zero readers with no key. Every ConfigMap key in
>   `configmap.yaml` is read by `config.py`; every documented env var (`GSD_ENABLE_VIEW_RESTRICTIONS`,
>   `GSD_VISIBILITY_TIER_TTL_SECONDS`, the SAR-shape keys) is read. Defined-vs-included helper sweep
>   found one orphan → F3.
> - **A2 (inert code) — one finding (F2).** `LOGIN_OUTCOMES` is defined and read by nothing.
>   The two known non-findings assessed below.
> - **A3 (vacuous assertions) — one finding (F1).** 23/24 security mutations killed; the fail-closed
>   paths, the 403 gates, the alert allow-list and the self-scoped store queries all have assertions
>   that fail under mutation. The single survivor is F1.
> - **A4 (validate the three recent fixes) — ALL THREE HOLD.** Detail below; one comment-accuracy nit (F5).
> - **A5 (the premise) — all three challenged claims HOLD**, measured live.
> - **A6 (attacker's eye) — no new finding.** A self reader learns nothing beyond the credential-less
>   `/metrics` (aggregate counts + per-CR identity/state, measured) plus their own data; the one private
>   aggregate with no `/metrics` analogue (`operator_configs`) is withheld at self and that is tested.
> - **Coordinator's monitoring.yaml questions:** Q1 answered (dependency holds, cannot refute); Q2 is FINDING F4.
>
> ---
>
> ### F1 — MEDIUM — `usage_scope`'s restrictions-off branch is untested; a regression re-exposes presence records
> `local-development/gsd/api.py:312-313` (`usage_scope`, the `if not restrict: return viewer, "self"` branch).
>
> **Trigger.** `visibility.enabled=false` (the documented "restore the wide cluster view" escape hatch),
> proxy on, `userActivity.visibility` at its default `self`. A reader opens the Usage tab.
> **The code is CORRECT today** — measured: `scope=self`, only the caller's own row is returned. The value
> `visibility.yaml`/`api.py` protect is real and deliberate: Usage is presence data with no `oc` equivalent, so
> turning off *cluster*-data scoping must not, as a side effect, publish who-worked-when (values.yaml:371-377).
>
> **The defect is the missing assertion.** Mutating that one line to `return viewer, "all"` (harness M8b)
> leaves the **entire suite green** — verified against the full suite minus the coordinator's UI files:
> the failure set is byte-identical with and without the mutation (the only failures are pre-existing
> path artifacts from running the chart/docs tests out of the copy tree). So a future edit that flips
> `"self"`→`"all"`, or a refactor that lets this path fall through to the wide tier, ships an exposure —
> **every authenticated reader sees every colleague's presence records** — with nothing red.
>
> **False belief it would create:** an operator who set `visibility.enabled=false` believes (per the
> values.yaml contract) that presence records still stay per-person; a regression here silently breaks that.
>
> **Test (add to `tests/test_visibility.py::TestUsageAdminTier`). Verified: passes on HEAD, fails under M8b
> with `EXPOSURE: usage widened to all`.**
> ```python
>     def test_usage_stays_self_when_cluster_restrictions_are_off(self, tmp_path):
>         """visibility.enabled=false restores the wide CLUSTER view, but Usage — presence
>         records with no `oc` equivalent — must NOT widen with it (values.yaml:371-377). Only
>         userActivity.visibility=='all' widens Usage. Pins usage_scope's `if not restrict`
>         branch, which no other test exercises: mutation-proven (flip to "all" left the whole
>         suite green)."""
>         db = str(tmp_path / "gsd.db")
>         _seed_usage(db)
>         app = build_app(_settings(db, view_restrictions_enabled=False), run_poller=False)
>         with TestClient(app) as c:
>             body = c.get("/api/dashboard/activity", headers=H("alice")).json()
>         assert body["scope"] == "self", "presence records must not widen when cluster restrictions are off"
>         assert {r["user_name"] for r in body["activity"]} == {"alice"}
> ```
> Mitigating context: the exposure needs the non-default `visibility.enabled=false`, and such an operator has
> already accepted the wide *cluster* view. But the presence-record boundary is a distinct, documented promise,
> and it is the only fail-open direction in the usage path with no test behind it — hence MEDIUM not HIGH.
>
> ---
>
> ### F2 — LOW — `LOGIN_OUTCOMES` is inert (A2: exported/computed, read by nothing)
> `local-development/gsd/api.py:50-52`. Computed by iterating `vars(loginlog)` at import, repo-wide readers = 0
> (`grep -rn LOGIN_OUTCOMES gsd/ tests/` → only the definition). Its own comment claims a purpose — the outcome
> vocabulary is "read OFF THE PARSER … so a new one must not require editing a second list that then silently
> rejects it **in a query parameter**." But the `outcome` query parameter on `list_logins` (api.py:843-850) is a
> free `str | None` validated against nothing, and its allowed values are a **hand-maintained literal** in the
> description — exactly the "second list" the constant was meant to abolish. So the constant exists, is
> documented as load-bearing, and changes no behaviour. **False belief:** a maintainer reads the comment and
> believes adding an `OUTCOME_*` to `loginlog.py` automatically keeps the `/logins?outcome=` filter in sync; it
> does not. Fix: either wire it (`outcome: str | None = Query(..., pattern=...)` built from `LOGIN_OUTCOMES`, or
> validate against it in the handler) or delete the constant and its comment. Predates the visibility line
> (introduced at b557c60) — flagging as the same defect class, not as this branch's regression.
>
> ---
>
> ### F3 — LOW — `gsd.cookieSecretBytes` helper is defined and included by nothing (A1)
> `charts/group-sync-dashboard/templates/_helpers.tpl:192-204`. `grep -rn cookieSecretBytes charts/` → only the
> `define`. Git-confirmed: it backed the cookie-secret AES-length render guard in `oauth-secret.yaml`, and that
> guard was removed in `9281050` ("drop token revocation …") while the helper was left behind — the mirror image
> of the F2 pattern (the reader was deleted, the definition survived). It renders nothing and guards nothing now.
> **False belief:** an operator reading the chart believes a too-short `oauthProxy.cookieSecret` is caught at
> render time; it is not (the proxy would reject it at startup and crash-loop, which is the failure the guard
> existed to pre-empt). Fix: delete the helper, or re-wire the length guard in `oauth-secret.yaml`.
>
> ---
>
> ### F4 — LOW/MEDIUM — the ServiceMonitor TLS posture has no test (coordinator Q2 — CONFIRMED gap)
> `charts/group-sync-dashboard/templates/monitoring.yaml:35-66` (re-read at the coordinator's new revision).
> No test in the suite renders or asserts the ServiceMonitor's TLS block — searched all of `tests/` for
> `ServiceMonitor|serviceMonitor|tlsConfig|serverName|insecureSkipVerify` (the one hit, `test_config.py:59`, is
> the unrelated `ClusterConfig.insecureSkipVerify`). `test_chart_strategy.py` has 71 tests and none touch it, so
> a revert to `insecureSkipVerify: true`, a dropped `serverName` (which silently disables verification the field
> exists to enable), or a dropped `ca.configMap` would all ship green. **False belief:** the 71 passing chart
> tests imply the verified-TLS posture is protected; it is not.
>
> **Test (add to `tests/test_chart_strategy.py`). Verified against the new chart: proxy-on and proxy-off cases
> both pass; the old `insecureSkipVerify: true` posture fails the first assertion.**
> ```python
> import yaml
> def _service_monitor(out: str) -> dict:
>     for doc in yaml.safe_load_all(out):
>         if doc and doc.get("kind") == "ServiceMonitor":
>             return doc
>     raise AssertionError("no ServiceMonitor rendered")
>
> class TestServiceMonitorTLS:
>     """The scrape must VERIFY the serving cert, not skip verification. serverName sets the
>     name checked independently of the pod IP dialled (service-ca issues for the SERVICE DNS
>     name); dropping it, or setting insecureSkipVerify, silently unverifies every scrape."""
>     def test_proxy_on_scrapes_https_and_verifies_against_the_service_name(self):
>         ok, out = render(monitoring__serviceMonitor__enabled=True)
>         assert ok, out
>         ep = _service_monitor(out)["spec"]["endpoints"][0]
>         tls = ep.get("tlsConfig") or {}
>         assert ep.get("scheme") == "https"
>         assert not tls.get("insecureSkipVerify"), "verification must be ON"
>         assert tls["serverName"].endswith(".svc"), tls.get("serverName")
>         assert tls["ca"]["configMap"] == {"name": "openshift-service-ca.crt", "key": "service-ca.crt"}
>     def test_proxy_off_scrapes_plain_http_with_no_tls_block(self):
>         ok, out = render(monitoring__serviceMonitor__enabled=True,
>                          oauthProxy__enabled=False, visibility__enabled=False)
>         assert ok, out
>         ep = _service_monitor(out)["spec"]["endpoints"][0]
>         assert "scheme" not in ep and "tlsConfig" not in ep
> ```
> **Coordinator Q1 (is the OpenShift-only `openshift-service-ca.crt` dependency acceptable?) — cannot refute,
> it holds.** Measured on CRC: the ConfigMap is auto-injected into *every* namespace unconditionally — present in
> `group-sync-dashboard`, and in `default`, `openshift-authentication`, `group-sync-operator` (no opt-in label,
> unlike the trusted-CA bundle). It is maintained by the service-ca operator, a CVO-managed core operator that
> cannot be removed on a supported cluster. The Service carries `serving-cert-secret-name: group-sync-dashboard-tls`,
> so the serving cert whose SANs are the service DNS names is issued by the same operator. There is no state in
> which this chart's hard requirements (Routes, oauth-proxy, user.openshift.io) are met but the ConfigMap is
> absent. The comment's argument stands.
>
> ---
>
> ### A4 — the three recent fixes VALIDATED (ec52fbb / 509dfc2 / 3d29e81)
> **All three hold.** Point by point:
> 1. **Single-source TTL — HOLDS.** `VISIBILITY_TIER_TTL_DEFAULT = 60` is declared once (`config.py:37`).
>    `kube.TIER_TTL_SECONDS = float(VISIBILITY_TIER_TTL_DEFAULT)` re-exports it (kube.py:102); Settings default
>    (config.py:356) and the env fallback (config.py:733-735) both reference the constant; both `build_app`
>    construction sites pass `settings.visibility_tier_ttl_seconds`. No third literal, **no stray constructor
>    default** — `grep "ttl_seconds *=" ` finds only the two call-site keyword passes and the required parameter.
> 2. **Required constructor args PREVENT the silent default, do not relocate it — HOLDS.** `ttl_seconds` and
>    `subresource` are keyword-only with **no default** (after `*` in `TierResolver.__init__`, kube.py:1046-1056).
>    Deleting either at a call site is a `TypeError` at construction — the loudest possible failure. Proven:
>    harness M16/M17 (delete `ttl_seconds=` from each site) → **construction ERROR**, not a silent pass.
> 3. **`resourceAttributes.subresource` reaches the API server in the right shape — HOLDS, measured against the
>    API's own behaviour.** Live differential on CRC as dana.lee (cluster-reader): `get pods` → ALLOW,
>    `get pods/log` (subresource) → ALLOW, `get pods/exec` (subresource) → **deny**. If the field were dropped
>    all three would be identical (`get pods`); the log/exec split proves the server both receives and honours
>    `subresource`. Canonical field name confirmed from the cluster's own OpenAPI: `ResourceAttributes` properties
>    include exactly `subresource`. **Absent-when-empty is correct** (the code adds the key only when non-empty):
>    measured `get pods` with the key OMITTED == with `subresource:""` (both ALLOW) — because Kubernetes treats
>    the empty string as "the resource, no subresource", identical to absent. See F5.
> 4. **The behavioural TTL test fails for the right reason under BOTH resolvers — HOLDS.** M18 (wide resolver TTL
>    → hard-coded `60.0`, ignoring the setting) fails `test_the_configured_ttl_changes_how_often_the_cluster_IS_ASKED`
>    on the `/api/clusters/c1/groups` parametrization; M19 (usage resolver) fails the same test on the
>    `/api/dashboard/activity` parametrization. Each resolver's `ttl_seconds=` is independently pinned — the test
>    counts real SubjectAccessReviews over the transport, not an introspected `_ttl`.
> 5. **`visibility.tierTtlSeconds` is nil-safe on every path — HOLDS.** `gsd.visibilityTierTtl` (_helpers.tpl:353-368)
>    defaults `.Values.visibility` to a dict and treats a nil `tierTtlSeconds` as "not set" → shipped `60`; a
>    fractional/negative value FAILS the render (regex `^[0-9]+$`) rather than reaching the app's `int()` and
>    silently falling back. Chart-strategy tests cover the nilled-block, fractional/negative-refused, zero-legal,
>    and threads-to-configmap cases; all pass.
>
> ### F5 — LOW (accuracy) — the subresource-omission rationale is imprecise
> `tests/test_visibility_tier.py:158-164` docstring and the `if subresource:` comment at `kube.py:1079` both say
> the empty subresource must be omitted because "the API server treats the empty string as a DISTINCT value …
> sending it would change the question." **Measured, that is not so:** `subresource:""` and an omitted key
> produce the identical decision (both are "the resource, no subresource" — JSON-absent and `""` deserialize to
> the same Go zero value). The code's behaviour (omit when empty) is correct and clean; only the stated *reason*
> is wrong. Harmless to behaviour, but per the audit's own standard ("comments cite measurements") the claim
> should read: omitting is the canonical form and is equivalent to `""`, not that `""` would change the check.
>
> ### A2 known non-findings — assessed
> `kube.TIER_SELF`/`TIER_ALL` exported while `api.py` compares string literals `"all"`/`"self"`: **not worse than
> it looks, and the drift direction is safe.** If someone changed `TIER_ALL = "wide"` in kube.py, the resolver
> would return `"wide"`, `viewer_scope`'s `tier == "all"` would stop matching, and every reader would fail
> **closed** to self — over-restriction, never exposure. The wire contract is the literal strings (tests assert
> them); the constants are redundant but harmless. (`data.alertsScope` is in the JS file, outside my Python/chart
> scope, untouched.)
>
> ### A5 — the premise, measured live on CRC
> - **#9 Usage irreproducible with `oc` — HOLDS by construction.** Usage rows are generated by the dashboard's own
>   request middleware from `X-Forwarded-User`; no cluster API records "who opened this dashboard". Nothing to reproduce.
> - **#7 `groupsyncs` fully public on the unauthenticated `/metrics` — HOLDS, measured.** `curl -k https://<route>/metrics`
>   with no credential returns `gsd_groupsync_state{groupsync=…,namespace=…}`, `gsd_groupsync_last_sync_timestamp_seconds`
>   and `gsd_groupsync_groups_total` per CR — the same per-CR identity/state `/api/.../groupsyncs` serves. The same
>   scrape carries **no** person or group name (grep for the persona names → 0). Unauthenticated `/api/clusters` → 403.
> - **#9 write-verb threshold separates cluster-admin from cluster-reader on STOCK roles — HOLDS, measured.** SARs
>   built exactly as the resolver does (user + fresh groups + `system:authenticated[:oauth]`):
>   `update clusterrolebindings` → **ALLOW** for john.doe (cluster-admin via Group) and **deny** for dana.lee
>   (cluster-reader). The wide default `list groups` → ALLOW for both admin and reader, deny for the ordinary
>   readers lateef.o and jane.smith. cluster-reader is a stock, read-only ClusterRole and cluster-admin is stock
>   `*/*`, so the separation is a property of the stock role *rules*, not of CRC's bindings — it generalises.
>
> ---
>
> ### Note — an unannounced concurrent edit landed mid-audit (`kube.py` + `test_visibility_tier.py`)
> The brief said the Python surface was stable except the three UI files. It was not: the worktree's
> `local-development/gsd/kube.py` and `local-development/tests/test_visibility_tier.py` gained **uncommitted**
> single-flight changes to `TierResolver` at 10:07, ten minutes after my snapshot (my `mut` copy and my first
> Read both predate it and show the prior "left unserialised" version). `TierResolver.tier_for` now elects one
> leader per viewer and rides followers on its result; followers of a failed/timed-out leader fail closed to
> self, uncached. **This is not part of the three commits I was asked to validate** (ec52fbb/509dfc2/3d29e81).
>
> My findings are unaffected: F1/F2/F4 live in `api.py`/`_helpers.tpl`/`monitoring.yaml` (unchanged), and the
> mutations that established A3/A4 targeted lines present in both versions. I additionally audited the new
> single-flight code against the current worktree copy and it **holds under mutation**: flipping the follower
> fail-closed `return TIER_SELF`→`TIER_ALL` is killed by
> `test_followers_of_a_failed_leader_fail_closed_and_recovery_is_the_next_request`, and removing the leader dedup
> is killed by both `TestSingleFlight` tests. Flagging the provenance, not a defect — the code is sound.
