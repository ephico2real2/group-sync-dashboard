# Adversarial review — the visibility tier, admin gating, metrics, and the publish pin

**Target:** `main` at `8fa02a7`. Merged PRs #17 (per-user visibility, 19 commits), #18 (metrics +
5 audit findings), #19 (gh-pages publish), #20 (chart 0.2.0), #22 (publish pin race).

**Why this review exists.** These changes are deployed and passing 1297 local / 1150 CI tests, and
none of them has had an adversarial read. This project has already shipped a change that passed
every test and was completely broken in production: leader election emitted 3-digit milliseconds
where Kubernetes `MicroTime` demands exactly 6, so every `Lease` create was rejected 400, the pod
never took leadership, and the poller is gated on leadership — **no deployment polled at all** for
the life of that commit. It survived because the create path turned a 400 into a bare `False`,
indistinguishable from "another replica holds it". A reviewer reading the create path for error
handling would have caught it in a minute. That is the standard here.

---

## Ground rules

1. **One verdict per numbered claim: `CONFIRMED`, `REFUTED`, or `FIX-INADEQUATE`.** Prefer
   refutation. Say "cannot refute" only when you actually checked, and say what you checked.
2. **Add NEW findings** for anything nobody asked about. The numbered list is the floor, not the
   ceiling.
3. **Every finding carries full code**, not a diff fragment or "add a check". The complete
   replacement function / template block in a fenced block, ready to apply. If it spans three
   functions, write all three. **Preserve the comment style**: comments here say WHY, not WHAT, and
   a replacement that strips the reasoning is a regression even when its logic is right.
4. **Every finding carries a complete test function** that fails before and passes after.
5. **Every finding carries** a `file:line-or-symbol`, a concrete trigger (state / sequence / input,
   not "could race"), and the consequence stated as **what a reader of the dashboard would believe
   that is false**.
6. **MEASURE, DO NOT REASON.** Suite: `cd local-development && .venv/bin/python -m pytest tests/ -q
   --deselect tests/test_live_smoke.py`, baseline **1297 passed / 4 deselected**. Run it. Write
   throwaway scripts against a scratch SQLite database rather than arguing about storage. If you
   assert a behaviour, show the command and its output.

Write findings into **this file** under your own heading (`## Codex — pass 1` / `## Cursor — pass
1`), using a `> **Codex:**` / `> **Cursor:**` marker under each claim. Do not create a new
document. Do not modify any other file — the arbiter applies changes, you do not.

---

## The premise you are checking against

The dashboard is read-only observability over the redhat-cop group-sync-operator on OpenShift. Two
independent access tiers were added:

**Tier 1 — cluster data (`viewer_scope`).** A `SubjectAccessReview` decides whether a reader sees
every group's membership (`all`) or only the groups they are themselves in (`self`).

**Tier 2 — usage data (`usage_scope`, `docs/SPEC_usage_admin_tier.md`).** Stricter and
*independent*. The Usage tab is the only dataset that exists **only** in the dashboard's own
database and cannot be reproduced with `oc`, so it must not fall to the wide tier that
`cluster-reader` — the deliberate auditor persona — also passes.

**The governing principle, which is the thing to attack:** *gate what a reader cannot already
obtain with `oc`.* Group memberships and GroupSync CRs are readable with `oc` by any
cluster-reader, so gating them would be theatre. RBAC binding findings are **not** — an ordinary
reader (`lateef.o`) holds none of `list clusterrolebindings`, `list rolebindings`, `list groups`
(`oc auth can-i` says no to all three) and `/bindings/findings` handed him 236 rows anyway, 21
naming an admin role, including which group holds cluster-admin. That is a target list obtainable
through the dashboard and not with `oc`.

**Two facts that were measured and are load-bearing — verify them rather than assuming:**

- `-openshift-delegate-urls` gates **bearer tokens and client certs only**. Cookie sessions bypass
  it entirely. Every "the proxy already checks this" argument dies here.
- A `SubjectAccessReview` **resolves no group membership of its own**. A cluster-admin granted via
  a Group is refused with `spec.user` alone; `allowed: true` came back only once the group was
  supplied in `spec.groups`.
- **`/metrics` is unauthenticated on the route by deliberate operator ruling.** The consequence is
  *"no names in any metric"* — not "add auth". Any username, LDAP group name, DN, or binding/role
  name in a label is a leak.

---

## V — Admin-tier gating  (`local-development/gsd/api.py`)

| # | Claim | Anchor |
|---|---|---|
| **V1** | `require_admin_tier` fails closed on every path: no identity, resolver absent, resolver raising, junk tier string. Only the exact string `all` admits. | `api.py:368-392` |
| **V2** | Gating `binding_findings` and `operator_configs` is sufficient — there is **no other endpoint** that returns binding, role, or operator-config detail to a `self`-tier reader. Grep every route; the claim is about completeness, not about these two. | `api.py:1174`, `api.py:1311` |
| **V3** | `list_clusters` withholds the `operator_configs` summary at `self` tier without leaking its existence through a differing shape, key set, or count elsewhere in the same payload. | `api.py:555-620`, esp. `:604` |
| **V4** | `SELF_ALERT_KINDS` (`api.py:75-82`) leaks nothing at `self` tier. Each of the six kinds is claimed to have a `/metrics` analogue or a cluster-card equivalent, so exposing it is not new information. **Check each of the six individually** — `dangling_binding` and `config_reconcile_error` were deliberately REMOVED from this set; confirm nothing re-admits them by another route. |
| **V5** | `usage_scope` precedence is correct and cannot be widened by accident: `userActivity.visibility == "all"` wins first; `restrict` off yields `self` and **not** `all`; a resolver error degrades the view but never availability; only the exact `"all"` widens. | `api.py:305-352` |
| **V6** | `usage_scope` reads the **usage** resolver off its own `app.state` seam and never falls back to the wide tier's resolver — including when `app.state.usage_tier_resolver` is absent but the closure `usage_tier_resolver` is set, and vice versa. | `api.py:330-345` |
| **V7** | `LOGIN_OUTCOMES` drives the `outcome` query validation, so an unknown outcome is **rejected** rather than silently matching nothing. Confirm the regex cannot be defeated by case, whitespace, regex metacharacters in a future outcome name, or a partial match. | `api.py:50`, and the `Query(pattern=...)` on the logins route |

**V8 — the wording constraint, and it is a requirement not a preference.** The refusal must say
"For administrators only." and must **not** name the grant, role, ClusterRole, chart value, or any
route that would tell a non-administrator what to ask for. Operator's words: *"I also don't wanna
give them ideas on thinking that they can get this."* Check `refusalCard` (`index.html:532`) and
every 403 `detail` string. Grep for leaked identifiers — `cluster-admin`, `cluster-reader`,
`visibility`, `clusterrolebinding`, `SubjectAccessReview`, `oc auth can-i`.

---

## T — The SubjectAccessReview and the tier cache  (`local-development/gsd/kube.py`)

| # | Claim | Anchor |
|---|---|---|
| **T1** | The SAR always carries `spec.groups` including the virtual groups every real token holds, so a cluster-admin granted **via a Group** resolves to `all`. | `kube.py:87-101`, `:964-989` |
| **T2** | Groups are fetched **fresh** per resolution rather than from the poll snapshot, and a failure to fetch them degrades to `self` rather than to `all` or to an exception that 500s the request. | `kube.py:942-962` |
| **T3** | `TierResolver.__init__` requires `subresource` and `ttl_seconds` as keyword-only with **no defaults**, so a dropped wire is a `TypeError` at construction and not a silently-wrong default. | `kube.py:1053-1090` |
| **T4** | `subresource` reaches the SAR only when non-empty (`kube.py:1087-1088`), and `subresource: ""` is equivalent to omitting the key at the API. **This was measured as equivalent — try to refute the measurement**, since an earlier claim that they are distinct was wrong. |
| **T5** | The per-viewer single-flight (`self._inflight`, `kube.py:1100`) cannot deadlock, cannot serve one viewer's tier to another, and cannot leave an `Event` set forever if the resolving thread raises. **Attack the exception path specifically**, and the case where two viewers hash to interleaved waits. |
| **T6** | The TTL is single-sourced from `config.py`'s `VISIBILITY_TIER_TTL_DEFAULT` (`kube.py:103`), so the documented worst-case staleness window is the real one. A reader demoted from admin keeps admin sight for at most one TTL — state that window and confirm it. |

---

## M — Metrics, on an unauthenticated endpoint  (`local-development/gsd/metrics.py`)

| # | Claim | Anchor |
|---|---|---|
| **M1** | **No metric label carries a username, LDAP group name, DN, or binding/role name.** This is the highest-value check in the document, because `/metrics` is public by ruling. Enumerate EVERY `labels=[...]` and every `add_metric([...])` value, not just the label names — a label named `cluster` holding a DN is still a leak. | `metrics.py:168-400+` |
| **M2** | `gsd_bindings_total{finding=...}` (`metrics.py:304-308`) exposes finding *counts* only. Confirm `finding` is a bounded enum of kinds and can never take a subject, group or role name — including for a finding kind added later. |
| **M3** | Label cardinality is bounded. A per-cluster gauge is fine; anything keyed by user or group would let a scraper enumerate the directory **and** blow up Prometheus. Name the bound for each metric. |
| **M4** | The visibility-decision counters (`signals.note_decision`) count decisions without recording **who** got which decision, at any aggregation. |
| **M5** | `prometheus-client` is a declared dependency and the exporter uses the custom-collector API. (Recorded because an earlier claim that this module was hand-rolled was **wrong** — a grep for `Gauge(`/`Counter(` missed the collector API. Confirm the dependency is declared in `pyproject.toml` and the collector is registered exactly once.) |

---

## U — The UI, after the paint-first change  (`local-development/gsd/static/index.html`)

| # | Claim | Anchor |
|---|---|---|
| **U1** | **XSS.** This file has had one before. Check `title=`, `data-*` attributes and every interpolation, not only text nodes. Group names, usernames and DNs are attacker-influenced via LDAP. | whole file |
| **U2** | Paint-first (`:791` — `navigate()` then `render()` then `refresh()`) cannot paint **wrong** data. Two real regressions were already found and fixed here: cold Groups flashed "No groups match this filter" because `data.groups` initialised `[]`, and after a cluster switch it painted cluster A's rows under cluster B's title. Attack `applyPosition` (`:117`) for a third. |
| **U3** | The auto-refresh fingerprint (`:2868-2881`) covers every payload field the UI renders. A field on the wire but absent from the fingerprint is a repaint that silently never happens. Enumerate the rendered fields against the fingerprint's members — `data.alertsScope` was added late, so treat the list as suspect. |
| **U4** | The fingerprint is computed over **fetched payloads only** and never over `view`, so a reader-driven change always repaints even when the data is identical. | `:2863-2873` |
| **U5** | `POLL_INTERVAL_MS = 60000` with the `document.hidden` guard and the `visibilitychange` catch-up (`:2986-3005`) cannot double-fire, cannot stampede on tab focus, and cannot skip a refresh forever if `lastRefreshStartedAt` is never updated on a failed fetch. |
| **U6** | `narrowedReader()` (`:509`) reads `whoami.visibility.scope` and degrades safely when the field is missing — showing the narrow view rather than implying the wide one. |

---

## C — Chart  (`charts/group-sync-dashboard/`)

| # | Claim | Anchor |
|---|---|---|
| **C1** | The ServiceMonitor verifies TLS properly: `ca.configMap` → `openshift-service-ca.crt`, plus `serverName` naming the **Service** (not the pod IP), replacing an earlier `insecureSkipVerify: true`. Confirm the configMap reference resolves in the **ServiceMonitor's own** namespace as claimed, and that `serverName` matches the certificate service-ca actually issues. | `templates/monitoring.yaml:35-66` |
| **C2** | `scheme: https` is correct because the Service port named `http` targets the **proxy** container port when the proxy is on. Check the `oauthProxy.enabled=false` path — does the ServiceMonitor then point at a plaintext port while still asking for HTTPS? | `monitoring.yaml:24-35` |
| **C3** | The new `templates/pdb.yaml` cannot make a single-replica install unevictable and thereby block a node drain. |
| **C4** | `Chart.yaml` `appVersion` is held to `pyproject.toml` by `tests/test_chart_versions.py`, and the chart `version` gates publishing (chart-releaser **skips** an already-released version, so a template change without a bump publishes nothing and still reports success). |

---

## P — The publish pin step  (`.github/workflows/publish.yml:126-235`)

Lowest priority: it has five tests and a verified production run. Included only because a
**second** pair of eyes on a step that pushes to `main` is cheap.

| # | Claim |
|---|---|
| **P1** | Re-applying the tag onto `FETCH_HEAD` makes the conflict structurally impossible, and the three-attempt bound is sufficient rather than arbitrary. Try to construct a sequence that still loses a pin. |
| **P2** | The `--hard` reset cannot lose work. Nothing local needs preserving because the tag lives in `$TAG` and the image is already pushed — refute that if you can. |
| **P3** | The `[skip publish]` marker cannot be evaded, so the pin commit cannot re-trigger the workflow. |

---

## Technical debt — three buckets, name them explicitly

- **DEBT-INTRODUCED** by these merges.
- **DEBT-ACCEPTED** knowingly, with the reason.
- **DEBT-AVOIDED** — where a shortcut was available and not taken.

Four places debt is likely hiding, address each **by name**:

1. `kube.py` exports `TIER_SELF` / `TIER_ALL` while `api.py` compares against string literals.
2. `usage_scope` duplicates `viewer_scope`'s fail-closed logic rather than sharing it — deliberate
   independence, or copy-paste that will drift?
3. `SELF_ALERT_KINDS` is a hand-maintained allowlist; a new alert kind defaults to **visible**.
4. The two-seam resolver lookup (`app.state` *and* closure) in `usage_scope`.

Finish with a whole-PR debt summary and one sentence on whether the debt is worth the features.

## Out of scope

Full redesigns. Moving `/metrics` to a separate port (designed in
`docs/DESIGN_metrics_refresh.md` §7, deliberately not applied). Adding authentication to
`/metrics` — the operator ruled it public; the consequence is "no names in metrics". Renaming
things for taste. Test-suite restructuring.

## Codex — pass 1

### Measurement record

> **Codex:** The requested object is `8fa02a70e923cfbc56851ffbdab87e2d3e4e4aa0`, whose parent is
> the checked-out `d8d8770f16f52fb2d21f608bfbebd025c79eaa30`; `git diff
> HEAD..8fa02a7` contains only the expected `values.yaml` image-tag pin. All reviewed code is
> therefore byte-identical to the target.
>
> The exact suite command ran. It could not reproduce the stated green baseline in this managed
> sandbox: Chromium aborted at launch with `MachPortRendezvousServer ... Permission denied`,
> producing `1153 passed, 4 deselected, 1 failed, 146 errors`. The one non-browser failure is
> caused by this mandated, currently-untracked review document itself: its supplied line anchors
> violate `test_no_citation_uses_a_line_number`. With only that pre-existing document check and
> the sandbox-blocked browser file excluded, the result was `1154 passed, 5 deselected`.
> The focused command over visibility, scoping, tier, metrics, chart-version, and publish-pin tests
> returned `166 passed`; separately: `test_view_scoping.py` returned `30 passed`,
> `test_metrics.py` returned `29 passed`, the single-flight tests returned `2 passed`, chart
> versions returned `3 passed`, and the repeated-push-race test returned `1 passed`.

### V1

> **Codex:** **CONFIRMED.** Cannot refute with restrictions enabled: missing identity, missing
> resolver, resolver exception, and every value other than exact lowercase `"all"` reach `self`
> before `require_admin_tier` refuses. I checked both resolver seams and the `scope != "all"`
> comparison. Restrictions-off deliberately returns `all`; that is an operator override, not a
> fail-closed path.

### V2

> **Codex:** **REFUTED** as literally written, but no code change is warranted. Grepping every
> route found three intentional self-scoped RBAC-detail paths:
> `group_detail` returns bindings of a group the viewer belongs to, `user_detail` returns bindings
> reachable through the viewer's groups, and `direct_user_bindings` returns bindings naming the
> viewer. None returns another person's grants or the cluster-wide finding/operator-config rows;
> the requirements explicitly require “their own grants.” The two administrator gates are
> sufficient for the prohibited cluster-wide surfaces, but the absolute “no binding or role
> detail” statement is false.

### V3

> **Codex:** **CONFIRMED.** At `list_clusters`, both tiers have identical keys and cluster counts;
> `operator_configs` is `None` at self rather than omitted or zeroed. The only failing-config
> aggregate elsewhere is already public as the unauthenticated alert metric.

### V4

> **Codex:** **REFUTED** as written because the allowlist has eight kinds, not six. All eight were
> checked: `auth_failed`, `forbidden`, and `unreachable` have cluster-card/`gsd_cluster_up` backing;
> `groupsync_crd_absent`, `invalid_schedule`, `sync_stopped`, `overdue`, and `reconcile_error` have
> the full-at-self GroupSync/card backing and public CR/alert metrics. The actual filter is
> fail-closed (`kind in SELF_ALERT_KINDS`), so a new kind defaults hidden, contrary to the debt
> premise below. `dangling_binding` and `config_reconcile_error` stay excluded; their detail routes
> 403 and no second alert route re-admits them.

### V5

> **Codex:** **CONFIRMED.** Checked precedence and outputs: activity visibility `all` returns
> `all` first; restrictions/proxy off returns `self`; missing identity/resolver, exception, and
> junk return `self`; only exact `"all"` widens.

### V6

> **Codex:** **CONFIRMED.** `usage_scope` reads only `app.state.usage_tier_resolver`, falling back
> only to the injected `usage_tier_resolver` closure. It never reads `tier_resolver` or
> `app.state.tier_resolver`; each one-seam-present case is covered by the focused 166-test run.

### V7 — finding: future outcome literals are interpreted as regex

> **Codex:** **FIX-INADEQUATE.** `api.py:list_logins` / the `LOGIN_OUTCOMES` query pattern.
> Trigger: add a legitimate parser outcome `failed.v2`; Pydantic accepts both `failed.v2` and
> `failedXv2` because the vocabulary is joined without escaping. Measured with Pydantic's actual
> validator: `failed.v2 ACCEPTED`, `failedXv2 ACCEPTED`. Current case, leading/trailing space,
> and misspelling inputs do reject, and the existing endpoint test passed; the defect is exactly
> the future-metacharacter case the claim requires. Consequence: filtering on `failedXv2` returns
> an empty 200, so a dashboard reader believes there were no `failed.v2` events when they supplied
> a value that is not an outcome at all.
>
> Complete replacement validation blocks (add `import re` with the standard-library imports and
> replace the vocabulary/query blocks as shown):
>
> ```python
> import functools
> import logging
> import os
> import re
> import time
> from collections.abc import Callable
> from contextlib import asynccontextmanager
> from datetime import UTC, datetime, timedelta
>
> # The outcome vocabulary, read OFF THE PARSER rather than restated here. loginlog.py is where an
> # outcome is decided, so a new one (a new AD sub-code, say) must not require editing a second list that
> # then silently rejects it in a query parameter. Each value is escaped because this vocabulary is
> # DATA inside the validator, never regex syntax; otherwise a later dot, bracket or pipe widens what
> # the query accepts while the store still compares the value literally.
> LOGIN_OUTCOMES = tuple(
>     v for k, v in vars(loginlog).items() if k.startswith("OUTCOME_") and isinstance(v, str)
> )
> def _login_outcome_pattern(outcomes: tuple[str, ...]) -> str:
>     """Treat parser outcomes as literal vocabulary, never as regex source text."""
>     return f"^({'|'.join(re.escape(value) for value in outcomes)})$"
>
>
> LOGIN_OUTCOME_PATTERN = _login_outcome_pattern(LOGIN_OUTCOMES)
>
> outcome: str | None = Query(
>     default=None,
>     # VALIDATED against the parser's own vocabulary, and this is what LOGIN_OUTCOMES is
>     # for — it was computed and then read by nothing, so the guarantee its comment
>     # promised did not exist. An unknown value used to return HTTP 200 with zero
>     # attempts, which is byte-identical to a valid filter that genuinely matches
>     # nothing: `outcome=bad_pasword` read as "no failed logins" in a tool whose whole
>     # job is telling you when there ARE some. 422 now, matching /groups' `state`.
>     #
>     # Derived rather than restated so a new outcome in loginlog.py becomes queryable
>     # the moment it can be parsed, instead of being rejected by a second list nobody
>     # remembered to extend. The derived values are regex-escaped at construction: a
>     # future literal containing punctuation must remain one literal outcome.
>     pattern=LOGIN_OUTCOME_PATTERN,
>     description="Return only attempts with this outcome. The vocabulary is the parser's: "
>                 "success, bad_password, rejected (not found OR not permitted — the log "
>                 "cannot tell those apart), password_expired, must_change_password, "
>                 "account_locked, account_disabled, account_expired, logon_not_permitted, "
>                 "and failed (the provider gave no reason — the normal shape on an "
>                 "HTPasswd provider, which logs a verdict and nothing else).",
> )
> ```
>
> Complete replacement route function (the validation-block code above supplies
> `LOGIN_OUTCOME_PATTERN`; the rest is retained verbatim so its WHY comments are not lost):
>
> ```python
>     @app.get("/api/clusters/{cluster_id}/logins")
>     @consistent
>     def list_logins(
>         request: Request,
>         cluster_id: str,
>         outcome: str | None = Query(
>             default=None,
>             # VALIDATED against the parser's own vocabulary, and this is what LOGIN_OUTCOMES is
>             # for — it was computed and then read by nothing, so the guarantee its comment
>             # promised did not exist. An unknown value used to return HTTP 200 with zero
>             # attempts, which is byte-identical to a valid filter that genuinely matches
>             # nothing: `outcome=bad_pasword` read as "no failed logins" in a tool whose whole
>             # job is telling you when there ARE some. 422 now, matching /groups' `state`.
>             #
>             # Derived rather than restated so a new outcome in loginlog.py becomes queryable
>             # the moment it can be parsed, instead of being rejected by a second list nobody
>             # remembered to extend.
>             pattern=LOGIN_OUTCOME_PATTERN,
>             description="Return only attempts with this outcome. The vocabulary is the parser's: "
>                         "success, bad_password, rejected (not found OR not permitted — the log "
>                         "cannot tell those apart), password_expired, must_change_password, "
>                         "account_locked, account_disabled, account_expired, logon_not_permitted, "
>                         "and failed (the provider gave no reason — the normal shape on an "
>                         "HTPasswd provider, which logs a verdict and nothing else)."),
>         user: str | None = Query(
>             default=None,
>             description="Only attempts for this exact username — the login that was TYPED, which "
>                         "may match no User object and no group member. That mismatch is a finding, "
>                         "not an error."),
>         limit: int = Query(
>             default=200, ge=1, le=2000,
>             description="Maximum attempts returned, newest first. `truncated` says whether older "
>                         "ones were dropped; `total` and `summary` always describe the whole "
>                         "retained record, never this page."),
>     ) -> dict:
>         """Login attempts against this cluster's oauth-server: who, when, and why it failed.
> 
>         THE RECORD IS A WINDOW, and both of its edges are carried as data rather than implied.
>         `capture_started_at` is when watching began and is stable; `retained_since` is the oldest
>         attempt still kept and moves under retention. Nothing before capture began exists to fetch —
>         the log dies with its pod — so an empty list is a statement about the window and never proof
>         that nobody logged in. The UI has to say that, which is why it is here and not a footnote.
> 
>         EVERY username is recorded, successful or not, member or not. `known_user: false` marks an
>         account in NO synced group, which is the most valuable row this produces; `has_history: true`
>         separates "access was removed and they are still trying" from "nobody ever governed this
>         name". `ungoverned` lists those accounts separately so a paged chronology cannot bury them.
>         """
>         require_cluster(cluster_id)
>         # THE MOST SENSITIVE ENDPOINT IN THE APPLICATION (requirements §2): it names people
>         # and states that their password was wrong or their account locked. SELF-SCOPED
>         # under view restrictions, and byte-exact on purpose: the capture stores the name
>         # AS TYPED (measured live: rows for both `lateef.o` and `LATEEF.O`), while the
>         # viewer arrives in the directory form, so a case-variant attempt stays visible to
>         # the wide tier only. A COLLATE NOCASE match was measured to degrade the query to
>         # the cluster-wide index scan AND would cross-leak between two OpenShift Users
>         # differing only by case — User names are case-sensitive.
>         viewer, scope = viewer_scope(request)
>         if scope == "self":
>             me = require_viewer(viewer)
>             if user is not None and user != me:
>                 raise HTTPException(
>                     status_code=403,
>                     detail="login attempts other than your own need the wide tier",
>                 )
>             user = me
>         # Which provider NAMES are HTPasswd is deployment configuration — the log carries only the
>         # name. Passed to the ungoverned queries so their rows and their count share ONE predicate in
>         # the store, and applied per row below for the break_glass label.
>         htpasswd = tuple(settings.login_capture_htpasswd_providers)
>         status = store.login_capture_status(cluster_id)
>         # Computed at BOTH tiers: the self view keeps the window edges (capture_started_at,
>         # retained_since — facts about the record, not about a person) and withholds the
>         # personnel aggregates below.
>         summary = store.login_event_summary(cluster_id, exclude_providers=htpasswd)
>         ungoverned = (
>             store.ungoverned_login_users(cluster_id, exclude_providers=htpasswd, limit=50)
>             if scope == "all" else None
>         )
>         # limit + 1 to learn whether more exist — the list_users idiom. `summary` carries the exact
>         # whole-record numbers, so no headline figure is ever computed from this page.
>         rows = store.login_events(cluster_id, user_name=user, outcome=outcome, limit=limit + 1)
>         truncated = len(rows) > limit
>         attempts = rows[:limit]
> 
>         by_outcome = summary["by_outcome"]
>         successes = by_outcome.get(loginlog.OUTCOME_SUCCESS, 0)
>         # Gate membership for the names on this page, in ONE batch lookup rather than a call per row.
>         # An empty dict means no gate is known, and the rows then carry None — "unknown", which is a
>         # different statement from False and the reason a `rejected` row can only sometimes be
>         # explained. With a gate known, `in_access_group: false` on a person who IS in a synced group
>         # turns "not found OR not permitted" into "a real person, not gated".
>         gate = store.is_in_access_group(cluster_id, [r["user_name"] for r in attempts])
>         for row in attempts:
>             # Normalised here so the UI never re-derives a flag from raw fields, and so the wire
>             # carries real booleans whatever 0/1 shape SQLite returned.
>             row["break_glass"] = row.get("provider") in htpasswd
>             row["known_user"] = bool(row.get("known_user"))
>             row["has_history"] = bool(row.get("has_history"))
>             # None, not False, when no gate is known. The UI must be able to say "we cannot tell"
>             # rather than asserting a non-membership it has no basis for.
>             row["in_access_group"] = gate.get(row["user_name"])
>             row["refusal_reason"] = _refusal_reason(row)
>         for row in ungoverned or []:
>             row["has_history"] = bool(row.get("has_history"))
> 
>         return {
>             "cluster": cluster_id,
>             "scope": scope,
>             "viewer": viewer,
>             "enabled": settings.login_capture_enabled,
>             "note": "read from the oauth-server log at Debug verbosity; covers only the period "
>                     "since capture began — earlier logins were never recorded and cannot be "
>                     "fetched, and rows older than the configured retention age out",
>             # Set once by the capture loop's first successful read. Falls back to the oldest retained
>             # attempt for the one-cycle window after a crash before that row exists — an honest floor
>             # rather than null, which the UI would have to render as "unknown".
>             "capture_started_at": (status or {}).get("started_at") or summary["first_at"],
>             "last_read_at": (status or {}).get("last_read_at"),
>             # How often `last_read_at` is EXPECTED to advance — capture runs on the poll thread, so
>             # the poll interval is its cadence. Sent because the browser is the only place that can
>             # decide whether a read is overdue and the only place that knows what a reader is
>             # looking at, but it has no way to learn the cadence: a hardcoded threshold in the page
>             # would call a 900s poll "stalled" every single cycle.
>             "read_interval_seconds": settings.poll_interval_seconds,
>             "retained_since": summary["first_at"],
>             # At self, the whole-record count OF THE VIEWER (one indexed scalar), never the
>             # cluster-wide total — a number computed over rows the response withholds would
>             # be the count-versus-page defect reintroduced deliberately.
>             "total": summary["total"] if scope == "all" else
>                      store.count_login_events(cluster_id, user),
>             "limit": limit,
>             "truncated": truncated,
>             # The personnel aggregates are WITHHELD at self, as None rather than zeros:
>             # failure counts, distinct users and the ungoverned list are personnel data
>             # even without names (the gsd_dashboard_active_users removal is the precedent),
>             # and a fabricated 0 would read as "nothing happened". Never recomputed over
>             # the visible subset either — "distinct users among yourself" is 1 by
>             # construction, a number whose label would lie.
>             "summary": {
>                 "distinct_users": summary["distinct_users"],
>                 "successes": successes,
>                 "failures": summary["total"] - successes,
>                 "by_outcome": by_outcome,
>                 "ungoverned_users": summary["ungoverned_users"],
>                 "first_at": summary["first_at"],
>                 "last_at": summary["last_at"],
>             } if scope == "all" else None,
>             # One row per account in no synced group, most recent first. Bounded at 50 and honest
>             # about it: summary.ungoverned_users beside it is the whole-set count, from the SAME
>             # store predicate, so the two cannot disagree.
>             "ungoverned": ungoverned,
>             "attempts": attempts,
>         }
> ```
>
> Complete test function:
>
> ```python
> def test_a_future_outcome_with_regex_punctuation_remains_literal() -> None:
>     import re
>
>     from gsd.api import LOGIN_OUTCOMES, _login_outcome_pattern
>
>     outcomes = (*LOGIN_OUTCOMES, "failed.v2")
>     pattern = _login_outcome_pattern(outcomes)
>     assert re.fullmatch(pattern, "failed.v2")
>     assert re.fullmatch(pattern, "failedXv2") is None
> ```

### V8 — finding: API refusals do not use the mandated sentence

> **Codex:** **FIX-INADEQUATE.** `api.py:require_admin_tier`; `index.html:refusalCard` is correct
> and prints “For administrators only.” exactly once without grant/role/config identifiers. Both
> administrator API routes instead returned 403 detail ending “reserved to the administrator
> tier.” Trigger: a self-tier reader calls either `/bindings/findings` or `/operator-configs`.
> Measured output for both was the same noncompliant detail. Consequence: an API-backed dashboard
> client presents wording the reader reasonably believes is the operator-approved refusal, but it
> is not, and it introduces a named tier the operator explicitly did not approve as guidance.
>
> Complete replacement function:
>
> ```python
> def require_admin_tier(request: Request) -> str:
>     """The administrator tier, or the operator-approved refusal.
>
>     For the views that are ABOUT THE CLUSTER rather than about the reader: its whole RBAC
>     binding surface and the operator's configuration. These cannot be scoped the way a
>     membership list can — a binding names whoever it names, so the honest choice is the
>     whole thing or none of it, and none of it is what a non-administrator gets.
>
>     WHY A REFUSAL AND NOT A FILTER, measured on the reference cluster. An ordinary reader
>     (`lateef.o`) holds none of `list clusterrolebindings`, `list rolebindings` or `list
>     groups` — `oc auth can-i` answers no to all three — and /bindings/findings handed him
>     236 rows anyway, 21 of them naming an admin role, including which group holds
>     cluster-admin. That is a target list obtainable through the dashboard and not with
>     `oc`: a privilege escalation.
>
>     The refusal is intentionally terse. The person receiving it cannot change the gate,
>     and naming a grant, role, chart value or check would turn a refusal into a shopping list.
>     """
>     _, scope = viewer_scope(request)
>     if scope != "all":
>         # Counted before the raise: a refusal that leaves no trace anywhere is how a
>         # gate that broke for everyone stays indistinguishable from one nobody hit.
>         signals.note_admin_refusal()
>         raise HTTPException(status_code=403, detail="For administrators only.")
>     return scope
> ```
>
> Complete test function:
>
> ```python
> def test_admin_route_403s_use_only_the_operator_approved_sentence(tmp_path) -> None:
>     db = str(tmp_path / "admin-wording.db")
>     store = Store(db)
>     store.upsert_cluster("c1", "https://x", True)
>     store.close()
>     settings = Settings(
>         clusters=[ClusterConfig("c1", "https://x", token_env="T")],
>         db_path=db,
>         oauth_proxy_enabled=True,
>     )
>     app = build_app(settings, run_poller=False, tier_resolver=lambda _: "self")
>     with TestClient(app) as client:
>         for path in (
>             "/api/clusters/c1/bindings/findings",
>             "/api/clusters/c1/operator-configs",
>         ):
>             response = client.get(path, headers={"X-Forwarded-User": "reader"})
>             assert response.status_code == 403
>             assert response.json() == {"detail": "For administrators only."}
> ```

### T1

> **Codex:** **CONFIRMED.** Every SAR body contains the freshly resolved group names plus exactly
> `system:authenticated` and `system:authenticated:oauth`. The group-granted-admin test passed.

### T2

> **Codex:** **CONFIRMED.** `fetch_groups_of_user` performs a fresh paged `GROUP_API` list for each
> uncached resolution, byte-exact matches the viewer, and resolver catches both `ClusterError` and
> unexpected exceptions to uncached `self`; no exception reaches the request.

### T3

> **Codex:** **CONFIRMED.** `subresource` and `ttl_seconds` are keyword-only and have no defaults;
> omission raises construction-time `TypeError`.

### T4

> **Codex:** **CONFIRMED.** Cannot refute the recorded API measurement. Locally I verified an empty
> value omits `resourceAttributes.subresource`, while non-empty `log` reaches the exact SAR body;
> the focused tier tests passed. No local cluster was available to repeat the live equivalence.

### T5

> **Codex:** **CONFIRMED.** I attacked the unexpected-exception path and two interleaved viewers.
> With Alice's group read raising `RuntimeError` while an Alice follower and Bob resolve
> concurrently, output was `alive [False, False, False]`, results
> `[('alice','self'),('alice','self'),('bob','all')]`, `_inflight {}`, and calls showed one Alice
> read plus Bob's independent read/SAR. The leader's `finally` pops under lock and then sets the
> exact viewer's Event; failures are uncached, so neither deadlock nor cross-viewer verdict occurs.

### T6

> **Codex:** **CONFIRMED.** `config.py:VISIBILITY_TIER_TTL_DEFAULT` is the one numeric default (60),
> `kube.py:TIER_TTL_SECONDS` re-exports it, Settings supplies it to both resolvers, and cache expiry
> is `decision_start + ttl`. Default worst-case retained admin visibility is at most 60 seconds
> from the cluster reflecting demotion, plus a response already painted in the browser; an
> operator-configured TTL deliberately changes that bound.

### M1

> **Codex:** **CONFIRMED.** I enumerated every `add_metric` value, not just declarations:
> build=`version/commit/branch`; leader/WAL/checkpoint/journal/capture-enabled/backup/refusal counters
> have no labels; cluster health/poll/capture/group counts/poll duration use configured cluster ID;
> binding count uses cluster + SQL finding; the four GroupSync families use cluster + CR name + CR
> namespace (+ fixed state); alerts use cluster + bounded kind + severity; tier checks/decisions use
> fixed threshold/outcome/tier; retention uses fixed table. A scratch SQLite store containing an
> attacker username, LDAP group/DN, binding name, and `cluster-admin` role printed all four as
> `absent`; only `finding="ok"` appeared. GroupSync CR and namespace names are Kubernetes object
> identifiers, not usernames, LDAP groups/DNs, or binding/role names.

### M2

> **Codex:** **CONFIRMED.** The production SQLite statement derives `finding` only from five CASE
> literals: `ok`, `dangling`, `unresolved`, `built_in`, `unmanaged`. Attacker-controlled subject,
> group, binding and role columns never become that value. A future classification requires a code
> literal; there is no persisted free-form finding column.

### M3

> **Codex:** **CONFIRMED.** Bounds per replica are: build/leader/storage/capture/backup/refusal = 1
> each; cluster_up/last_poll/group totals/capture-last-read/poll-duration = C each; bindings = at
> most 5C; GroupSync last-sync/groups/error = at most C×R, state = 4C×R; alerts = at most C times
> the fixed alert-kind/severity vocabulary; tier checks = 12, decisions = 4, retention = 2.
> `C` is configured clusters and `R` is GroupSync CRs, never directory users/groups. The 500-group
> cardinality test passed.

### M4

> **Codex:** **CONFIRMED.** `note_decision` receives only threshold and tier; snapshots and exporter
> contain no viewer field, per-viewer map, or hashed identity. Export loops fixed vocabularies.

### M5

> **Codex:** **CONFIRMED.** `prometheus-client>=0.26.0` is declared in `pyproject.toml`.
> `build_registry` creates a fresh custom `CollectorRegistry` and calls `register` exactly once with
> one `DashboardCollector`; the app constructs that registry once.

### NEW M6 — finding: `unmanaged` disappears instead of exporting zero

> **Codex:** **REFUTED** the implied completeness of the metric vocabulary.
> `metrics.py:FINDINGS` omits the real SQL outcome `unmanaged`. Trigger measured against scratch
> SQLite: one managed and one manual binding produced SQL `['ok', 'unmanaged']` and metric
> `finding="unmanaged" 1.0`; after removing the manual binding SQL became `['ok']` and the metric
> emitted no unmanaged sample rather than zero. Consequence: a metrics/dashboard reader sees the
> unmanaged series vanish and can believe that classification stopped being exported, rather than
> the true statement that the count is now zero.
>
> Complete replacement vocabulary block:
>
> ```python
> STATES = (st.OK, st.LATE, st.OVERDUE, st.UNKNOWN)
> # Every SQL classification is pre-seeded. A resolved problem disappearing must become a
> # measured zero, not an absent series that is indistinguishable from exporter drift.
> FINDINGS = ("ok", "dangling", "unresolved", "built_in", "unmanaged")
> ```
>
> Complete test function:
>
> ```python
> def test_unmanaged_binding_is_preseeded_back_to_zero() -> None:
>     now = now_iso()
>     store = Store(":memory:")
>     group = {
>         "name": "g", "member_count": 1, "sync_provider": "p",
>         "group_synced_at": now, "ldap_uid": None,
>     }
>     def binding(name: str, managed_source: str | None) -> dict:
>         return {
>             "binding_kind": "RoleBinding", "binding_namespace": "ns",
>             "binding_name": name, "role_kind": "ClusterRole", "role_name": "view",
>             "group_name": "g", "managed_source": managed_source,
>         }
>     try:
>         store.upsert_cluster("c1", "https://x", True)
>         store.record_poll("c1", "ok", None)
>         store.replace_group_state("c1", [group], now)
>         store.record_managed_groups("c1", [group], now)
>         store.replace_bindings(
>             "c1", [binding("managed", "NamespaceConfig/x"), binding("manual", None)], now)
>         first = generate_latest(build_registry(store, GRACE)).decode()
>         assert 'gsd_bindings_total{cluster="c1",finding="unmanaged"} 1.0' in first
>
>         store.replace_bindings("c1", [binding("managed", "NamespaceConfig/x")], now)
>         fixed = generate_latest(build_registry(store, GRACE)).decode()
>         assert 'gsd_bindings_total{cluster="c1",finding="unmanaged"} 0.0' in fixed
>     finally:
>         store.close()
> ```

### U1

> **Codex:** **CONFIRMED.** Cannot refute after enumerating every template interpolation and all
> `innerHTML` sinks. LDAP/user/group/DN values pass `esc()` in text, `title`, `data-*`, option
> values, SVG data attributes, and error text. Direct property assignments use `textContent` or
> the DOM `title` property. Unescaped class/data fragments are derived from fixed local enums or
> numeric calculations. The crafted-hash XSS regression test exists; browser execution was blocked
> by this sandbox as recorded above.

### U2

> **Codex:** **CONFIRMED.** I attacked `applyPosition` across cold page, cluster switch, same-cluster
> drilldown, popstate/hashchange, and superseded requests. Cluster changes synchronously null every
> cluster payload before any tab's paint-first `render`; cold cluster payloads start `null`; same-
> cluster drilldowns do not paint under a changed object title before fetch, and `navSeq` discards
> both stale writes and paints. I found no third wrong-data paint.

### U3 — finding: a recovered version fetch never paints

> **Codex:** **FIX-INADEQUATE.** `index.html:refresh` fingerprint block. Trigger: the initial
> `/api/version` request transiently fails, the first automatic retry succeeds, and every other
> payload is unchanged. Measured simulation printed `version retry changes fingerprint: false`.
> `data.version` is set and its timezone adopted, but the unchanged fingerprint returns before
> `render()`. Consequence: the reader sees a blank build identity and timestamps still painted in
> the old zone, and believes the server did not provide build/timezone data when it did.
>
> Complete replacement fingerprint block:
>
> ```javascript
> // The fingerprint is over the fetched payloads only, never over `view`: a repaint the reader
> // caused by navigating is not an "unchanged" case, and mixing the two here would suppress it.
> // Include version because a failed boot fetch is retried: the first successful retry must repaint
> // the build identity and every timestamp whose display zone was just learned.
> // alertsScope rides along even though nothing renders it yet: it arrives on the same wire as
> // fields that DO, and omitting a payload field silently suppresses its first rendered change.
> const fingerprint = JSON.stringify([
>   data.clusters, data.alerts, data.alertsScope, data.groupsyncs, data.groups,
>   data.groupsMeta, data.group, data.user, data.events, data.logins, data.access,
>   data.usage, data.findings, data.operatorConfigs, data.userBindings, data.whoami,
>   data.version,
> ]);
> ```
>
> Complete test function:
>
> ```python
> def test_a_recovered_version_fetch_repaints_the_header(page, scoped_server) -> None:
>     calls = 0
>     def version(route) -> None:
>         nonlocal calls
>         calls += 1
>         if calls == 1:
>             route.fulfill(status=500, content_type="application/json", body='{"detail":"blip"}')
>         else:
>             route.fulfill(
>                 status=200, content_type="application/json",
>                 body='{"version":"9.9.9","commit":"abc","branch":"main",'
>                      '"dirty":false,"timezone":{"name":"UTC","abbrev":"UTC"}}')
>     page.route("**/api/version", version)
>     page.set_extra_http_headers({"X-Forwarded-User": "root"})
>     page.goto(scoped_server)
>     page.wait_for_selector("#main .card")
>     assert page.locator("#build-info").inner_text() == ""
>     page.evaluate("() => refresh({auto: true})")
>     page.wait_for_function("() => document.querySelector('#build-info').textContent.includes('9.9.9')")
>     assert calls == 2
> ```

### U4

> **Codex:** **CONFIRMED.** `view` is absent from the fingerprint. Every reader-driven navigation
> either renders first or calls non-auto `refresh`, and the equality early-return is auto-only.

### U5 — finding: focus catch-up and interval can double-fire

> **Codex:** **REFUTED.** `index.html` automatic-refresh scheduling block. Trigger: a tab has been
> hidden for at least 60 seconds, becomes visible immediately before the interval callback,
> `visibilitychange` starts a due refresh, then the interval callback runs. Only the visibility
> handler checks age; the interval starts a second burst. Measured simulation printed
> `refresh bursts after focus/tick: 2`. `navSeq` discards the first result but cannot un-send its
> requests. Consequence: visibility-decision metrics count two request bursts for one catch-up, so
> a metrics reader believes two dashboard refresh decisions occurred when the reader caused one.
> Failed fetches do update `lastRefreshStartedAt` at entry, so they retry on a later interval rather
> than being skipped forever.
>
> Complete replacement scheduling block:
>
> ```javascript
> const POLL_INTERVAL_MS = 60000;
>
> // Both clocks enter through one due check. A visibility event and an interval callback can be
> // adjacent in the same event loop; refresh() stamps its start synchronously, so the second caller
> // observes that work is already current and cannot dispatch a duplicate endpoint burst.
> function autoRefreshIfDue() {
>   if (document.hidden) return;
>   if (Date.now() - lastRefreshStartedAt < POLL_INTERVAL_MS) return;
>   refresh({ auto: true });
> }
>
> setInterval(autoRefreshIfDue, POLL_INTERVAL_MS);
>
> // Catch up on becoming visible again, so a tab left in the background is not stale on return.
> // The shared due guard also covers the regular tick that may already be queued immediately after
> // this event; one visibility transition therefore produces at most one refresh burst.
> document.addEventListener("visibilitychange", autoRefreshIfDue);
> ```
>
> Complete test function:
>
> ```python
> def test_visibility_catchup_and_interval_share_one_due_guard(page, scoped_server) -> None:
>     page.add_init_script("""
>       window.__autoTick = null;
>       window.setInterval = (fn) => { window.__autoTick = fn; return 1; };
>     """)
>     page.set_extra_http_headers({"X-Forwarded-User": "root"})
>     page.goto(scoped_server)
>     page.wait_for_selector("#main .card")
>     calls = page.evaluate("""async () => {
>       let count = 0;
>       lastRefreshStartedAt = 0;
>       refresh = () => { count += 1; lastRefreshStartedAt = Date.now(); };
>       Object.defineProperty(document, "hidden", {configurable: true, value: false});
>       document.dispatchEvent(new Event("visibilitychange"));
>       window.__autoTick();
>       return count;
>     }""")
>     assert calls == 1
> ```

### U6 — finding: missing visibility defaults to the wide-looking UI

> **Codex:** **REFUTED.** `index.html:narrowedReader`. Trigger: `/api/whoami` is unavailable or an
> older response has authenticated identity but no `visibility`; current output measured
> `missing visibility treated narrowed: false`. The renderer takes the overview/full branch even
> while sensitive endpoints independently 403. Consequence: a self-tier reader sees the wide
> overview layout and reasonably believes they have the full view, which is false.
>
> Complete replacement function:
>
> ```javascript
> /* Is this reader on the narrowed tier? Only an explicit server declaration of scope=all may
>    paint the wide-only layout. Missing whoami/visibility is indeterminate and therefore narrow:
>    the API remains the security boundary, while the page avoids claiming a tier it did not learn. */
> function narrowedReader() {
>   const w = data.whoami;
>   const vis = w && w.authenticated && w.visibility;
>   return !vis || vis.scope !== "all";
> }
> ```
>
> Complete test function:
>
> ```python
> def test_missing_visibility_declaration_paints_the_narrow_refusal(page, scoped_server) -> None:
>     def whoami(route) -> None:
>         route.fulfill(
>             status=200, content_type="application/json",
>             body='{"authenticated":true,"user":"alice","email":null,'
>                  '"logout_url":"/oauth/sign_out","session":{"cookie_expire_seconds":14400}}',
>         )
>     page.route("**/api/whoami", whoami)
>     page.set_extra_http_headers({"X-Forwarded-User": "alice"})
>     page.goto(scoped_server)
>     page.wait_for_selector(".scope-refusal")
>     assert "For administrators only" in page.locator(".scope-refusal").inner_text()
>     assert page.locator(".hero").count() == 0
> ```

### C1

> **Codex:** **CONFIRMED.** Helm rendered the ServiceMonitor and Service in `review-ns`; the CA
> selector is `openshift-service-ca.crt/service-ca.crt`, and `serverName` rendered
> `review-group-sync-dashboard.review-ns.svc`, exactly the annotated Service DNS identity.
> Prometheus Operator's selector is namespaced to the ServiceMonitor object, and OpenShift's
> service-ca documentation confirms the generated certificate is valid for
> `<service>.<namespace>.svc` and the bundle key is `service-ca.crt`.

### C2

> **Codex:** **CONFIRMED.** Measured Helm output: proxy on renders Service target
> `oauth-proxy`, `scheme: https`, and TLS config; proxy off renders Service target `http` and omits
> both `scheme` and TLS config, so Prometheus uses plaintext HTTP.

### C3

> **Codex:** **REFUTED** as an absolute, but the shipped default is safe. Measured render with PDB
> enabled gives `maxUnavailable: 1`; explicitly setting `minAvailable=1` renders exactly that and
> can block a single-replica drain indefinitely. This is a deliberate, prominently documented
> operator choice, so no code change is recommended; the claim should say “the default cannot.”

### C4

> **Codex:** **CONFIRMED.** The three version tests passed: `appVersion` equals pyproject, image-tag
> prefix equals appVersion, chart version is bare semver. `helm.yaml` uses chart-releaser
> `skip_existing: true`; an existing version emits a warning and publishes nothing while the job
> remains green, so Chart version is indeed the publication gate.

### P1

> **Codex:** **REFUTED.** Re-applying onto `FETCH_HEAD` structurally removes the same-line rebase
> conflict. Three attempts are not sufficient in the mathematical sense: the repository's own
> `test_losing_the_push_race_repeatedly_fails_loudly` advances main before every push and exhausts
> all three; it passed in 6.26s by proving exit 1 and an unpinned tag. Any finite retry count can be
> defeated by the same number of branch moves. No code change is recommended: loud failure after a
> bounded retry budget is the correct operational contract; “sufficient” should be replaced with
> “bounded and fails loudly.”

### P2

> **Codex:** **CONFIRMED.** Before reset the only needed local result is captured in scalar `TAG`;
> the build script asserts it rewrites only repository/tag, and the image is already pushed. The
> hard reset is necessary to prevent the old index from reverting merges; the collision test
> confirms the resulting commit changes one file and preserves an intervening merge.

### P3

> **Codex:** **CONFIRMED.** The generated subject always contains exact lowercase
> `[skip publish]`; the job condition checks `github.event.head_commit.message` for that exact
> marker. The bot's push has the pin as its head commit, so the triggered workflow is skipped.

### Technical debt

> **Codex:** **DEBT-INTRODUCED.** `kube.py` exports `TIER_SELF` / `TIER_ALL` while `api.py` compares
> string literals. The wire should remain strings, but importing the constants would remove a
> second spelling of the security boundary. Also introduced: the two-seam resolver lookup
> (`app.state` plus closure) makes precedence non-obvious; tests cover it, but publishing one
> adapter on `app.state` would leave one runtime seam.
>
> **Codex:** **DEBT-ACCEPTED.** `usage_scope` duplicates `viewer_scope`'s fail-closed skeleton to
> preserve the intentionally independent threshold, cache, override precedence, and metrics label.
> That independence is worth the small drift risk, but paired tests must continue. The three-push
> retry is also accepted operational debt: it is a bounded best effort with loud failure, not a
> guarantee. `minAvailable: 1` is accepted operator-controlled debt because the chart documents
> exactly how it blocks drains.
>
> **Codex:** **DEBT-AVOIDED.** `SELF_ALERT_KINDS` is hand-maintained, but the implementation chose
> an allowlist filter, so a new kind defaults **hidden**, not visible; the review premise has the
> direction backwards. The debt that remains is silent loss of new alerts until classified, plus
> no test that holds every allowlisted kind to its claimed public/full backing. Separate usage and
> admin resolver instances avoid cross-threshold cache contamination; required constructor wires
> avoid silent TTL/subresource defaults; the custom metrics registry avoids global duplicate
> registration; `FETCH_HEAD` + hard reset avoids both rebase conflict and merge rollback.
>
> **Codex:** Whole-PR summary: the features are worth the debt—the core access boundaries,
> unauthenticated metric privacy, single-flight failure direction, TLS verification, and pin-race
> structure hold—but the six concrete fixes above should land, and the four named debt seams should
> remain explicit regression-test targets rather than folklore.
