# Review brief — two recorded debts: the tier constants, and `settling`

**Status:** brief only. Nothing implemented. Two reviewers write their verdicts into this file,
then a third arbitrates, then implementation follows.

**Scope is deliberately tiny.** Two changes, both claimed to be behaviour-preserving. That is
exactly why they need a review pass: a "pure rename" that quietly changes semantics is this
project's named failure mode (the Forensic 2nd-pass rule, §3 — *"a 'fix' that quietly changes
behaviour is a new bug"*). The question is not "is this nicer?" but **"is it identical?"**

---

## Baseline, measured

```
cd local-development && .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py
=> 1459 passed, 4 deselected
```

`main` is at `ee99856`, app `0.7.0`, chart `0.4.2`. The cluster runs `0.7.0-92aa8d5e0c`.

---

## Debt A — `TIER_SELF` / `TIER_ALL` are exported and then re-typed

`gsd/kube.py` declares both constants and uses them at every one of its own decision points,
including `gsd/kube.py#TierResolver.tier_for`'s terminal `tier = TIER_ALL if allowed else
TIER_SELF`. `tests/test_visibility_tier.py` imports them and asserts against them throughout.

`gsd/api.py` imports **only** `TierResolver` from that module (`gsd/api.py` line: `from .kube import
TierResolver`) and spells the strings itself at roughly fourteen sites. The two that carry the
policy are in `gsd/api.py#build_app`'s nested `viewer_scope` and `usage_scope`:

```python
scope = "all" if tier == "all" else "self"          # viewer_scope
if settings.user_activity_visibility == "all":      # usage_scope
```

### What I measured before writing this

I claimed to the operator that a divergence here would go uncaught. **That was wrong and I retract
it.** Mutating `TIER_ALL = "all"` to `"wide"` and running the full suite:

```
6 failed, 1453 passed
FAILED tests/test_visibility_tier.py::TestSettings::test_the_configured_ttl_changes_how_often_the_cluster_IS_ASKED[...]
```

That test drives the real resolver through real endpoints (`/api/clusters/c1/groups`,
`/api/dashboard/activity`), so the producer and the consumer *are* coupled by a test. The debt is
duplicated knowledge and unexpressed intent, **not** an unguarded hazard. Any verdict that treats
this as a live security gap is arguing against a measurement.

### The proposed change

In `gsd/api.py`, import `TIER_ALL` and `TIER_SELF` alongside `TierResolver` and use them in place
of the literals.

### Claims to confirm or REFUTE

- **A1.** The change is behaviour-identical. `TIER_ALL == "all"` and `TIER_SELF == "self"`, so every
  rewritten comparison and every rewritten return value is the same string. Refute with any site
  where substitution changes a value, a type, or an evaluation order.
- **A2.** No site is a false friend. Specifically: is every `"all"` / `"self"` in `gsd/api.py`
  actually a *tier*? Candidates for NOT being one — `settings.user_activity_visibility == "all"`
  (a chart value, `userActivity.visibility`, whose vocabulary is the operator's config and not the
  resolver's return), the `scope` field serialised onto the wire in responses, and any docstring or
  log string. Name each site you would leave alone and why. **I consider this the highest-value
  claim in this brief**: substituting a resolver constant into a place that means a config value
  couples two vocabularies that are free to diverge, which is the opposite of the intended fix.
- **A3.** The fail-closed discipline is preserved exactly. `gsd/api.py#build_app`'s `viewer_scope`
  documents "only the exact string `all` widens". Confirm the rewrite keeps *identity* comparison
  against one constant and does not become membership in a set, a truthiness test, or a
  `startswith`.
- **A4.** Direction of the dependency. `api.py` already imports from `kube.py`, so no cycle is
  introduced. Confirm, and say whether the constants belong in `kube.py` at all or whether the tier
  vocabulary should live somewhere neither module owns. A recommendation to move them is in scope;
  actually moving them in this PR is probably not, and say so if you agree.
- **A5.** Is the wire contract touched? `scope` appears in JSON responses
  (`/api/alerts`, `/api/whoami`, `/api/clusters/{c}/groups`, …). Confirm the serialised strings are
  byte-identical after the change, because a consumer parses them.

---

## Debt B — `settling` holds what has finished settling

In `gsd/logincapture.py#capture_once`:

```python
parsed   = parse(lines)
settling = _recordable(parsed)
attempts = _not_clipped(settling, window_start)
```

`gsd/logincapture.py#_recordable` returns *"only the attempts old enough that every one of their
lines must already have arrived"* — its body is `[a for a in attempts if a.at <= cutoff]`. So the
list bound to `settling` is the **survivors**: the ones that have finished settling. The attempts
genuinely still settling are `parsed - settling`, which is exactly how the DEBUG line computes
them:

```python
"... parsed %d, withheld %d still settling (returns next cycle), dropped %d clipped ..."
len(parsed), len(parsed) - len(settling), len(settling) - len(attempts), len(attempts)
```

The log line is correct. The variable name is its own complement.

### The proposed change

Rename the local to `settled` (or `recordable`, matching the function that produces it). Local
scope only — it is not exported, not a field, not in any signature.

### Claims to confirm or REFUTE

- **B1.** The name is genuinely inverted, not a defensible reading. Steelman the current name
  before agreeing: is there a sense in which `_recordable`'s output is "settling"? If yes, say so
  and the rename is refused.
- **B2.** Every occurrence is local to one function and the rename is total. Four occurrences were
  found by `grep -n settling gsd/logincapture.py`. Confirm the count, confirm none is a string, a
  key, a column name, or a log format token, and confirm nothing outside this module reads it.
- **B3.** The DEBUG line's arithmetic is unchanged. The three counts must remain
  `len(parsed) - len(new_name)`, `len(new_name) - len(attempts)`, `len(attempts)`. A rename that
  "tidies" the arithmetic is out of scope and must be refused.
- **B4.** Which name. `settled` reads against `still settling` in the same log line;
  `recordable` matches `_recordable`. Pick one and give the reason. A third option is welcome.
- **B5.** Is there a better fix than renaming — e.g. does the withheld count deserve to be a named
  local (`withheld = len(parsed) - len(settled)`) so the log line stops recomputing it inline?
  Say whether that is an improvement or scope creep.

---

## Out of scope — do not review these

- The self-tier projection (#33), the release-chain fix (#34), the `0.7.0` bump (#35). All merged,
  all reviewed or measured live.
- `_recordable`'s and `_not_clipped`'s semantics, the settle horizon, `OVERLAP_SECONDS` /
  `SETTLE_SECONDS` arithmetic. The filters are correct; only the *name* of one local is in
  question.
- Whether `viewer_scope` should exist, or the tier model itself.
- Anything in `gsd/kube.py` beyond the two constant declarations and whether they belong there.

## What a finding must carry

1. A verdict per claim: **CONFIRMED**, **REFUTED**, or **FIX-INADEQUATE**. "Cannot refute" only
   after saying what you checked.
2. `file#symbol` or an exact quoted line. Prefer symbols; line numbers are permitted in this file
   because it is registered in `tests/test_docs_citations.py#REVIEW_ARTIFACTS`.
3. **Full replacement code**, not a description. If you would leave a site alone, show the site.
4. Any behaviour difference you find, stated as *what a reader of the dashboard would believe that
   is false* — or, for these two, *what a maintainer would believe that is false*.
5. Whether the change is worth making at all. "Correct but not worth the diff" is a legitimate
   verdict for debt this small, and saying so is more useful than inventing work.

---

## Codex — pass 1

<!-- Codex writes verdicts here, using `> **Codex:**` markers. -->

> **Codex:** **A1 — CONFIRMED, for the narrow replacement shown under A2.** At `ee99856`,
> `git show HEAD:local-development/gsd/kube.py` gives `TIER_ALL = "all"` and
> `TIER_SELF = "self"`; an interpreter check gave two plain `str` values equal to those
> literals. I evaluated the old and proposed fail-closed expressions for `"all"`, `"self"`,
> `"wide"`, `""`, `None`, and `1`; every old/new result matched. No type, returned scope, or
> evaluation order changes when only the two resolver-result comparisons use `TIER_ALL`.
> This is duplicated knowledge, not an untested exposure: while the concurrent mutation
> `TIER_ALL = "wide"` was present, the unmodified comparison failed the named behavioural test
> in all six parameter cases, while the in-memory narrow replacement passed those same six cases.
> The change is worth its three-line diff because it names the producer's vocabulary exactly at
> its two consumers; importing `TIER_SELF` despite having no resolver-`self` comparison is not.

> **Codex:** **A2 — REFUTED.** An AST inventory found **43** exact runtime literals whose complete
> value is `"all"` or `"self"`; only two are resolver tiers. Here is the exhaustive classification:
>
> - **Resolver tier — rewrite:** `gsd/api.py#viewer_scope` line 463's `tier == "all"`, and
>   `gsd/api.py#usage_scope` line 511's `tier == "all"`. These compare the value returned by
>   `TierResolver` (or its injected seam), so `TIER_ALL` is the right vocabulary.
> - **Operator chart value — leave alone:** `gsd/api.py#usage_scope` line 486,
>   `settings.user_activity_visibility == "all"`. This is parsed from
>   `userActivity.visibility`. Coupling it to a resolver constant would make a future resolver
>   rename silently rename an operator-owned config value that is free to remain `all`.
> - **Wire `scope` vocabulary and its internal consumers — leave alone:** lines 440, 451, 460,
>   both result arms on 463, 490, 497, 501, 510, both result arms on 511, 574, 773, 825, 864,
>   900, 929, 1004, 1031, 1119, 1138, 1190, 1208, 1240, 1254, 1392, 1465, 1478, 1480,
>   1508, 1539, 1630, and 1775. These create, serialize, or consume the response `scope`; a
>   client parses that contract. They deliberately stay `"all"`/`"self"` even if the resolver's
>   internal vocabulary changes.
> - **Observability labels — leave alone:** `signals.note_decision` at lines 450, 459, 489, 500,
>   and 509. These label the served scope (`admin|usage` by `all|self`), not the resolver's raw
>   return. Changing them with the resolver would change the metric series while the served wire
>   scope remained unchanged.
> - **Group-state filter — leave alone:** `gsd/api.py#list_groups` line 882's query default and
>   `gsd/api.py#list_alerts` line 1596's `store.groups(cluster_id, "all")`. Here `all` means all
>   group states versus `empty`/`unattributed`; it is neither a tier nor a response scope.
>
> For avoidance of doubt, this is the exact unchanged-site manifest; it shows every runtime
> occurrence above rather than asking the arbiter to infer sites from line numbers:
>
> ```python
> # gsd/api.py#viewer_scope — served scope and its metric labels, not raw resolver vocabulary
> return viewer, "all"
> signals.note_decision("admin", "self")
> return viewer, "self"
> signals.note_decision("admin", "self")
> return viewer, "self"
> scope = "all" if tier == TIER_ALL else "self"  # result arms stay wire vocabulary
>
> # gsd/api.py#usage_scope — config vocabulary, served scope, and metric labels
> if settings.user_activity_visibility == "all":
> signals.note_decision("usage", "all")
> return viewer, "all"
> return viewer, "self"
> signals.note_decision("usage", "self")
> return viewer, "self"
> signals.note_decision("usage", "self")
> return viewer, "self"
> scope = "all" if tier == TIER_ALL else "self"  # result arms stay wire vocabulary
>
> # Every downstream scope consumer/static wire value, in source order
> if scope != "all":
> _config_summary(row["id"]) if scope == "all" else None
> if scope == "self":
> "scope": "all",
> user_name=None if scope == "all" else require_viewer(viewer)
> if scope == "self" and not store.is_group_member(
> user_name=None if scope == "all" else require_viewer(viewer)
> if scope == "self" and name != require_viewer(viewer):
> if scope == "self":
> if scope == "all" else None
> summary["total"] if scope == "all" else store.count_login_events(cluster_id, user)
> } if scope == "all" else None
> if scope == "self":
> "scope": "self",
> "scope": "all",
> me = None if scope == "all" else require_viewer(viewer)
> store.user_bindings_by_namespace(cluster_id) if scope == "all" else None
> store.platform_user_binding_count(cluster_id) if scope == "all" else None
> "scope": "all",
> user_name=None if scope == "all" else require_viewer(viewer)
> if scope == "self":
> scope_to = None if scope == "all" else viewer
>
> # Unrelated group-state vocabulary
> default="all", pattern="^(all|empty|unattributed)$"
> groups=store.groups(cluster_id, "all")
> ```
>
> The quote-delimited prose inventory is also complete: `gsd/api.py#build_app` line 296;
> `viewer_scope` lines 433-436 and its line-461 comment; `usage_scope` lines 475, 477, and 480;
> the `binding_findings` comment at line 1387; the `dashboard_activity` comment at line 1772;
> and the app-state seam comment at line 1929. Those are docstrings/comments explaining either
> resolver or wire vocabulary and remain human-readable literals. There is no quote-delimited
> `"all"`/`"self"` logging message; the exact strings passed to `note_decision` are metric labels,
> classified above. Human log prose such as `"serving the self view"` is not a tier value and is
> also left alone.
>
> ```text
> build_app: `tier_resolver` answers "which tier is this viewer?" — "all" or "self".
> viewer_scope: `scope` is "all" only ... POSITIVELY answers "all" ... "self", never on the wide view.
> viewer_scope comment: Only the exact string "all" widens.
> usage_scope: userActivity.visibility == "all" ... exact "all" widens ... only the exact string "all" ever widens.
> binding_findings comment: Always "all".
> dashboard_activity comment: scope is "all" only via the blunt override or a positive usage-SAR verdict.
> app-state comment: resolve(viewer) -> "all" | "self".
> ```
>
> A blanket substitution is therefore a regression disguised as cleanup. The complete safe
> replacement is the import plus every site that should change—exactly two:
>
> ```python
> from .kube import TIER_ALL, TierResolver
>
> # gsd/api.py#viewer_scope
> scope = "all" if tier == TIER_ALL else "self"
>
> # gsd/api.py#usage_scope
> scope = "all" if tier == TIER_ALL else "self"
> ```

> **Codex:** **A3 — CONFIRMED.** The replacement remains the one exact-value equality
> `tier == TIER_ALL`; it does not use identity (`is`), membership, truthiness, prefix matching,
> or `TIER_SELF` as an allow condition. The measured truth table was `all -> all` and each of
> `self`, `wide`, empty, `None`, and `1 -> self` at `ee99856`. Under the concurrent
> `TIER_ALL = "wide"` mutation, the same expression widened only the resolver's exact new value
> and still emitted wire scope `"all"`. The full replacement is the A2 code block.

> **Codex:** **A4 — CONFIRMED.** AST inspection showed `api.py` already imports `TierResolver`
> from `kube.py`, `kube.py` has no module-level import from `api.py`, and importing `build_app`,
> `TierResolver`, and both constants together succeeded; adding one name to that existing import
> cannot create a cycle. The constants describe `TierResolver`'s return vocabulary, so `kube.py`
> is a defensible owner. A neutral vocabulary module would add a dependency merely to house two
> strings and is not worth this PR; actually moving them is out of scope. The full replacement is
> the A2 code block.

> **Codex:** **A5 — CONFIRMED.** The A2 replacement changes comparisons only. Every return arm,
> static `"scope"` field, and downstream `scope` comparison stays literal
> `"all"`/`"self"`. This was measured more strongly than equality at the current spelling:
> with the concurrent `TIER_ALL = "wide"` mutation, the unmodified implementation produced
> `['self', 'self', 'self']` and the six real-endpoint behavioural cases failed; after applying
> that mutation to producer and consumer in memory, the narrow replacement passed all six and
> continued serializing `scope=all`.
> Thus the resolver vocabulary may move while the consumer-facing bytes do not. The full
> replacement is the A2 code block.

> **Codex:** **B1 — CONFIRMED.** Steelman: `settling` can be read as “the output of the settling
> stage,” just as a pipeline variable might be named for the operation that produced it. That
> reading loses against the local evidence: `_recordable` returns attempts at or before the
> cutoff, and the same DEBUG line names `parsed - settling` as the attempts **still settling**.
> A maintainer reading `settling` as unfinished would believe the variable contains precisely
> its complement. `settled` removes that inversion and is worth the local-only rename. The
> complete replacement function is under B2.

> **Codex:** **B2 — REFUTED as counted, while the proposed identifier rename is total.**
> `rg -n '\bsettling\b' gsd/logincapture.py` reports four matching **lines**, not four lexical
> occurrences. Python tokenization measured four `NAME` tokens—definition line 256, consumer
> line 257, and two uses on line 273—and one `STRING` token on line 269, `"still settling"`.
> All four identifiers are locals in `gsd/logincapture.py#capture_once`; project-wide Python
> search found no external identifier reader. The fifth occurrence is intentional operator-facing
> prose and must not be renamed: the withheld attempts really are still settling. Here is the
> complete replacement function, preserving all WHY comments and changing only those four name
> tokens:
>
> ```python
> def capture_once(
>     store: StorageBackend,
>     cluster: ClusterConfig,
>     settings: Settings,
>     elector=None,
>     timeout: float = 15.0,
>     signals=None,
> ) -> int:
>     """One capture pass over one cluster. Returns events recorded. NEVER raises for cluster problems.
>
>     ── THE LEADERSHIP RECHECK, AND WHY IT IS WHERE IT IS ─────────────────────────────────────────────
>     `poller.py` says of its lease, in its own words, that it is "BEST-EFFORT admission control, NOT a
>     write fence", and `_run_cluster` checks it once per cycle. That is fine for group polling and not
>     fine here, because this reads logs over the network: the check can pass, the read can block, the
>     lease can expire and pass to another replica, and the old leader's read can then return and write.
>     Codex named the sequence exactly — leader check true → log GET blocks → lease lost → new leader
>     starts → old GET returns → old leader records events and watermark.
>
>     So leadership is rechecked IMMEDIATELY BEFORE the write transaction, which narrows the window from
>     "the length of a log read" to "the few instructions between the check and the INSERT". It does not
>     close it, and this comment exists so nobody later mistakes it for a fence: closing it needs a
>     fencing token the lease does not provide. What makes the residual window tolerable is the dedup
>     key — two leaders writing the same lines produce the same rows, and INSERT OR IGNORE collapses
>     them. The watermark is the part that could regress, and `set_login_watermark` takes max() precisely
>     so a late write from a demoted leader cannot rewind it.
>     """
>     if not settings.login_capture_enabled:
>         # DEBUG, not INFO: this is a configuration state rather than an event, so at INFO it would
>         # repeat once per cluster per cycle forever and say nothing new. But it must be sayable
>         # SOMEWHERE — "the Logins tab is empty" and "capture is switched off" are the same symptom,
>         # and this is the only line that tells them apart.
>         log.debug("%s: login capture is disabled, so no oauth-server logs are read and the Logins "
>                   "tab will stay empty; set loginCapture.enabled=true to change that", cluster.name)
>         return 0
>
>     ns = settings.login_capture_namespace
>     client = ClusterClient(cluster, timeout=timeout)
>
>     try:
>         pods = client.fetch_oauth_pods(ns)
>     except ClusterError as exc:
>         log.warning("%s: login capture could not list pods: %s — group data is unaffected",
>                     cluster.name, exc.message)
>         return 0
>     if pods is None:
>         # WARNING, not INFO, and the contract decides it: reaching here means capture is ENABLED
>         # (the check above returned otherwise) and RBAC forbids the read, so the feature is
>         # configured but inert and will not self-heal until somebody applies the grant. That is
>         # the contract's WARNING case in its own words.
>         #
>         # It was INFO, which also made it invisible to anyone watching WARNING and above — while
>         # kube.py#fetch_oauth_pods logs its own INFO for the same 403, so a forbidden cluster
>         # emitted two INFO lines every cycle and nothing an operator would ever be paged on.
>         log.warning("%s: login capture is enabled but not permitted to list pods in %s, so no "
>                     "logins will be recorded until the grant is applied", cluster.name, ns)
>         return 0
>     if not pods:
>         log.info("%s: no Running oauth-server pods in %s", cluster.name, ns)
>         return 0
>
>     watermarks = store.login_watermarks(cluster.name)
>     recorded = 0
>     read_ok = False
>
>     for pod in pods:
>         settled_through = watermarks.get(pod)
>         if settled_through is None:
>             since = FIRST_SIGHT_SECONDS
>         else:
>             # Seconds back from now to the watermark, plus the overlap. sinceSeconds is relative and
>             # coarse (whole seconds), which is exactly why the dedup key rather than arithmetic is what
>             # guarantees correctness here.
>             age = _seconds_since(settled_through)
>             since = max(OVERLAP_SECONDS, int(age) + OVERLAP_SECONDS) if age is not None \
>                 else FIRST_SIGHT_SECONDS
>
>         from datetime import UTC, datetime, timedelta
>         try:
>             lines = client.fetch_pod_log(ns, pod, since_seconds=since)
>         except ClusterError as exc:
>             # An AUTH_FAILED here is worth surfacing but must not stop the other pods.
>             log.warning("%s: login capture failed reading %s: %s", cluster.name, pod, exc.message)
>             continue
>         if lines is None:
>             continue                      # roll noise or a missing grant; both already logged
>         read_ok = True
>
>         # Stamped AFTER the response, and that direction is load-bearing. The kubelet resolves
>         # sinceSeconds against its own RECEIVE time, so the true boundary is `receive - since`, which
>         # this bounds from above: taking the stamp before the request would put the derived edge up to
>         # one request-latency too EARLY, and the leading-edge guard would then miss exactly the attempts
>         # a slow read clipped. An 8 MiB read can take longer than ATTEMPT_WINDOW, so that is not
>         # hypothetical. Erring late costs at most a row near the edge, which in steady state was
>         # already recorded a cycle ago.
>         window_start = datetime.now(UTC) - timedelta(seconds=since)
>         # SPLIT INTO NAMED STAGES so the DEBUG line below can report each one. This was a single
>         # composed expression, which is tidier to read and impossible to explain: the two filters
>         # remove attempts for OPPOSITE reasons, and from outside both look like "the parser found
>         # things and the store got none".
>         #   _recordable  withholds an attempt whose success line may not be written yet — it comes
>         #                back next cycle (see its docstring).
>         #   _not_clipped drops an attempt whose earlier lines may lie behind the window's leading
>         #                edge — "dropped for good, not deferred", in its own words.
>         parsed = parse(lines)
>         settled = _recordable(parsed)
>         attempts = _not_clipped(settled, window_start)
>         horizon = _settle_horizon(lines)
>
>         # THE LINE THAT MAKES SILENCE LEGIBLE, and the reason this module gained any DEBUG at all.
>         # In steady state every path from here down is quiet — no NEW attempts means no INFO — so a
>         # working capture and a broken one produce identical logs. Measured on the reference
>         # cluster: 73 attempts stored, 13 distinct users, and not one line in the pod log to say
>         # capture was running.
>         #
>         # "settled through", not "advances to": store.set_login_watermark applies max(), so a late
>         # write from a demoted leader cannot rewind it and this horizon may not become the new one.
>         log.debug("%s: %s read %d line(s) covering the last %ds from read position %s — parsed %d, "
>                   "withheld %d still settling (returns next cycle), dropped %d clipped at the "
>                   "window's leading edge (gone for good), %d to write; log settled through %s",
>                   cluster.name, pod, len(lines), since,
>                   settled_through or "none (first-sight window)",
>                   len(parsed), len(parsed) - len(settled), len(settled) - len(attempts),
>                   len(attempts), horizon or "nothing yet — read position holds")
>
>         if lines and not parsed:
>             # GATED ON `parsed`, NOT ON `attempts`, and that distinction is the whole point. If the
>             # parser found attempts and the two filters withheld them, the cause is this module's
>             # own arithmetic and the line above already says so — blaming the cluster there would
>             # send an operator to the wrong place.
>             #
>             # Nothing parsed at all has one overwhelmingly likely cause, and it is not "nobody
>             # logged in": the oauth-server writes the line naming a person ONLY while the
>             # authentication OPERATOR is at spec.logLevel: Debug. That is a different log level from
>             # this chart's `logLevel`, on a different object, in a different vocabulary
>             # (Normal/Debug/Trace/TraceAll) — and confusing the two is the likeliest reason a
>             # healthy-looking deployment records nothing. Both honest possibilities are stated,
>             # because a genuinely quiet cluster reads identically.
>             log.debug("%s: %s: %d line(s) read and no login attempt in any of them — either nobody "
>                       "logged in, or authentications.operator.openshift.io/cluster is not at "
>                       "spec.logLevel: Debug, without which the lines naming a person are never "
>                       "written (chart value authLogLevel, NOT logLevel; see "
>                       "docs/LOGIN_CAPTURE_QUICKCHECK.md)", cluster.name, pod, len(lines))
>
>         if not attempts and horizon is None:
>             continue
>
>         observed_at = now_iso()
>         events = [event_dict(a, pod, observed_at) for a in attempts]
>
>         # THE RECHECK. Everything above is reads; everything below writes.
>         if elector is not None and not elector.is_leader:
>             log.info("%s: lost leadership while reading %s — discarding %d event(s) unwritten",
>                      cluster.name, pod, len(events))
>             return recorded
>
>         n = store.record_login_events(cluster.name, events) if events else 0
>         recorded += n
>         if horizon is not None:
>             store.set_login_watermark(cluster.name, pod, horizon, observed_at)
>         if n:
>             log.info("%s: recorded %d login attempt(s) from %s", cluster.name, n, pod)
>         elif attempts:
>             # The commonest steady-state path, and previously the most confusing: attempts WERE
>             # found and none were new, because the overlap deliberately re-reads a window that was
>             # already recorded. Without this, a working capture that has caught up is silent in
>             # exactly the way a broken one is.
>             log.debug("%s: %s: all %d attempt(s) in the window were already stored — the %ds "
>                       "overlap re-reads them by design, so this is steady state, not a failure",
>                       cluster.name, pod, len(attempts), OVERLAP_SECONDS)
>
>     # Forget read positions for pods that are gone. Every oauth roll replaces them, so without this
>     # the table grows by one row per pod name the cluster has ever had.
>     #
>     # Done on the strength of the POD LIST — which succeeded above, or we would have returned — and
>     # NOT gated on whether any read worked: a cluster whose log reads are all refused would otherwise
>     # keep every dead pod's position forever, which is the case most likely to accumulate them. It is
>     # also independent of `login_retention_days`, because this is a leak rather than a policy about
>     # how long to keep data; _prune's docstring claimed to do it and never did.
>     if elector is None or elector.is_leader:
>         dropped = store.prune_login_watermarks(cluster.name, pods)
>         if dropped:
>             log.info("%s: forgot %d stale read position(s) for pods that no longer exist",
>                      cluster.name, dropped)
>
>     if not read_ok:
>         # Not a single pod answered. Do NOT stamp a successful read: `started_at` would then claim we
>         # have been watching since a cycle that saw nothing, and `last_read_at` is the liveness signal
>         # that tells somebody capture has stopped.
>         #
>         # SAY SO, because the decision above is invisible otherwise. Its whole effect is a metric
>         # that stops moving (gsd_login_capture_last_read_timestamp_seconds), and a gauge going flat
>         # is not self-explaining — nothing marked the cycle where it happened. WARNING rather than
>         # ERROR: group polling is untouched and an oauth roll self-heals it within a cycle or two.
>         log.warning("%s: login capture read none of the %d oauth-server pod(s) in %s this cycle; "
>                     "the last-read stamp is deliberately not advanced, so the dashboard will report "
>                     "capture as stale until one answers", cluster.name, len(pods), ns)
>         return recorded
>
>     if elector is not None and not elector.is_leader:
>         return recorded
>     store.record_login_read(cluster.name, now_iso())
>
>     _prune(store, cluster, settings, elector, signals)
>     return recorded
> ```

> **Codex:** **B3 — CONFIRMED.** The complete replacement above retains, in the original order,
> `len(parsed) - len(settled)`, `len(settled) - len(attempts)`, and `len(attempts)`. Compiling the
> old and renamed functions in memory produced identical `co_code`, `co_consts`, and `co_names`;
> the sole code-object difference was `co_varnames` changing `('settling', 'settled')`, with the
> same 31 locals. Any reviewer proposal to introduce named counts, algebraically rearrange them,
> or otherwise “tidy” this DEBUG call must be refused in this change even if its arithmetic is
> equivalent.

> **Codex:** **B4 — CONFIRMED: choose `settled`.** It is the direct complement of the unchanged
> phrase `still settling`, so the DEBUG arithmetic becomes readable without consulting the helper:
> `parsed - settled` is withheld; `settled - attempts` is clipped. `recordable` is also accurate,
> but it makes the log expression bridge two vocabularies instead of one grammatical contrast.
> The complete replacement is under B2.

> **Codex:** **B5 — REFUTED as a better fix for this debt.** A named `withheld` count could be a
> reasonable independent readability change, but it is scope creep here and is explicitly barred
> by B3: it changes more than identifier metadata and turns the claimed pure rename into a second
> refactor. The bytecode-identity measurement would no longer hold. Keep the inline arithmetic
> exactly as shown in the complete B2 replacement.

> **Codex:** **Behaviour-preservation run and new findings.** Before the concurrent mutation, the
> unmodified code passed the permitted suite command
> `cd local-development && .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py --ignore tests/test_ui.py`:
> **1310 passed, 4 deselected**. Chromium was not launched, per the brief, so I do not claim to have
> reproduced the supplied 1459 count that includes `test_ui.py`. The same 1310/4 result passed with
> both proposed edits injected in memory and no source/test write. During a transient concurrent
> `kube.py` change to `TIER_ALL = "wide"`, the named real-endpoint test against unmodified `api.py`
> reproduced exactly **6 failed**. Repeating that mutation entirely in memory with the narrow
> candidate made the same six cases pass, proving the two comparisons follow the resolver while
> the wire stays `all`. No additional in-scope finding was found.

## Cursor — pass 1

<!-- Cursor writes verdicts here, using `> **Cursor:**` markers. -->

> **Cursor:** **Measurements first (commands + outputs).** HEAD `ee99856b1c74c847c2e98bbd2857e7593bd3e8e0`
> (`ee99856 chore(chart): pin image tag 0.7.0-92aa8d5e0c [skip publish]`).
>
> ```text
> $ .venv/bin/python -c 'from gsd.kube import TIER_ALL, TIER_SELF; print(repr(TIER_ALL), repr(TIER_SELF), TIER_ALL=="all", TIER_SELF=="self")'
> 'all' 'self' True True
>
> $ .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py
> 1460 passed, 4 deselected, 1 warning in 268.79s
> ```
>
> Brief said 1459; this tree has an uncommitted `tests/test_docs_citations.py` registration for
> this artifact, which accounts for the +1. `tests/test_ui.py` is included in that 1460 (not
> ignored). Debt A is **not** a live uncaught hazard — mutating only the producer:
>
> ```text
> $ # TIER_ALL = "all" -> TIER_ALL = "wide" in gsd/kube.py, then:
> $ .venv/bin/python -m pytest tests/test_visibility_tier.py::TestSettings::test_the_configured_ttl_changes_how_often_the_cluster_IS_ASKED -q
> 6 failed, 1 warning in 4.20s
> # every case: got ['self','self','self'] expected ['all','all','all']
>
> $ .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py
> 6 failed, 1454 passed, 4 deselected, 1 warning in 202.55s
> ```
>
> Restored: `TIER_ALL = "all"` at `gsd/kube.py` line 85. A verdict that calls Debt A an unguarded
> security gap argues against this measurement and is refused.

> **Cursor:** **A1 — CONFIRMED** (behaviour-identical *today* for any site whose meaning is the
> visibility-tier vocabulary). Attacked by (1) `TIER_ALL == "all"` / `TIER_SELF == "self"` above,
> (2) the mutation suite proving the producer already returns these exact strings into
> `viewer_scope` / `usage_scope`, (3) reading every rewritten comparison as still a single
> `==` against one `str`. No site was found where substituting the constant changes type or
> evaluation order while the constant holds its current value. Sites that are **not** that
> vocabulary are out of A1 — they are A2 false friends; substituting them is still
> byte-identical *today* and still wrong. Worth doing only at the decision sites shown under
> A2; a repo-wide literal sweep is not justified by this measurement.

> **Cursor:** **A2 — REFUTED** ("no site is a false friend"). Exhaustive inventory of every
> quote-delimited `"all"` / `"self"` in `gsd/api.py` (grep + read). False friends that must
> **stay literals**:
>
> 1. **Operator chart value** — `gsd/api.py#usage_scope`:
> ```python
> if settings.user_activity_visibility == "all":
> ```
> This is `userActivity.visibility` / `GSD_USER_ACTIVITY_VISIBILITY`, parsed by
> `gsd/config.py#_visibility_setting`. It is free to keep spelling `all` even if the resolver
> vocabulary moves. `TIER_ALL` here couples two owners. **Leave alone.**
>
> 2. **Groups state filter** (not a tier) — `gsd/api.py#list_groups` Query and
> `gsd/api.py#list_alerts`'s store call:
> ```python
> state: str = Query(
>     default="all", pattern="^(all|empty|unattributed)$",
>     description="`all`; `empty` for groups with zero members, whatever created them; "
>                 "`unattributed` for groups no GroupSync CR claims. The two overlap: a "
>                 "hand-made group with no members is both."),
> )
> # ...
> groups=store.groups(cluster_id, "all"),
> ```
> Here `all` means "no empty/unattributed filter" (`gsd/store.py#Store.groups`'s `state`).
> **Leave alone.**
>
> 3. **Docstrings / comments / log prose** — leave the human-readable spellings. Examples that
> must not become f-strings over constants: `build_app`'s `tier_resolver` docstring; 
> `viewer_scope` / `usage_scope` docstrings (including the chart line
> `userActivity.visibility == "all"`); the `# Only the exact string "all" widens` comment;
> `log.exception("... serving the self view")`; app-state seam comment
> `resolve(viewer) -> "all" | "self"`.
>
> **Not a false friend — same vocabulary by design.** `gsd/kube.py` states the constants exist
> so they can sit directly in the response `scope` field. Wire `scope`, fail-closed returns,
> and `signals.note_decision(..., tier)` labels are that vocabulary exported, not a second
> dialect. Treating them as untouchable "wire literals" while only rewriting `tier == "all"`
> leaves the duplication the debt named mostly intact, and invents a translation layer the
> codebase does not document. Downstream `if scope == "all"` handlers may keep literals
> (they compare an already-decided string) without paying much; the decision functions should
> not.
>
> **Rewrite these — full replacement (import + both decision functions).** WHY-comments
> preserved; only the tier/scope vocabulary sites move to constants. Config comparison stays
> a literal.
>
> ```python
> from .kube import TIER_ALL, TIER_SELF, TierResolver
> ```
>
> ```python
> def viewer_scope(request: Request) -> tuple[str | None, str]:
>     """Resolve this request to (viewer, scope). The failure direction IS the control.
>
>     `scope` is "all" only when restrictions are off, or when the tier resolver
>     POSITIVELY answers "all" for this viewer. Everything else — no viewer, no
>     resolver wired, a resolver error or timeout, an unrecognised answer — lands on
>     "self", never on the wide view (requirements §5.4, decision D1).
>     """
>     viewer = trusted_viewer(request)
>     if not restrict:
>         return viewer, TIER_ALL
>     # Read off app.state PER REQUEST — the published seam (see app.state.tier_resolver
>     # below), so a test-substituted resolver is honoured by every handler. The
>     # build-time `tier_resolver` callable is the fallback for an app built with an
>     # injected decision and nothing published.
>     state_resolver = getattr(app.state, "tier_resolver", None)
>     if not viewer or (state_resolver is None and tier_resolver is None):
>         # Counted like every decision below; only the restrictions-off return above is
>         # not a decision. gsd_visibility_decisions_total is what makes the served
>         # all:self mix visible — the everyone-silently-narrowed signature.
>         signals.note_decision("admin", TIER_SELF)
>         return viewer, TIER_SELF
>     try:
>         tier = (state_resolver.resolve(viewer) if state_resolver is not None
>                 else tier_resolver(viewer))
>     except Exception:  # noqa: BLE001
>         # Logged with the trace, served as self: an API-server blip degrades the VIEW,
>         # never the availability — the reader sees their own data, not an error page.
>         log.exception("tier resolution failed for %r; serving the self view", viewer)
>         signals.note_decision("admin", TIER_SELF)
>         return viewer, TIER_SELF
>     # Only the exact string "all" widens — the _visibility_setting discipline applied
>     # to the resolver's answer, so a buggy resolver cannot widen by returning junk.
>     # Compared against TIER_ALL (the producer's vocabulary) and emitted as that same
>     # constant so the wire `scope` cannot drift from what TierResolver returns.
>     scope = TIER_ALL if tier == TIER_ALL else TIER_SELF
>     signals.note_decision("admin", scope)
>     return viewer, scope
> ```
>
> ```python
> def usage_scope(request: Request) -> tuple[str | None, str]:
>     """Resolve this request to (viewer, scope) for the USAGE tab specifically.
>
>     A SECOND, STRICTER threshold than viewer_scope, and INDEPENDENT of it
>     (docs/SPEC_usage_admin_tier.md). The Usage tab is the one dataset that lives only in the
>     dashboard's own database and cannot be reproduced with `oc`, so it must not fall to the
>     wide tier that cluster-reader — the deliberate auditor persona — also passes. Precedence:
>
>       1. userActivity.visibility == "all" -> every admitted reader sees all rows. The
>          existing blunt escape hatch, kept unchanged.
>       2. otherwise the USAGE resolver decides: its exact "all" widens; everything else — no
>          resolver, an error, a junk string, no identity — is the reader's own rows.
>
>     Fail closed like viewer_scope: only the exact string "all" ever widens. Reads the usage
>     resolver off its OWN app.state seam, never the wide tier's.
>     """
>     viewer = trusted_viewer(request)
>     # Precedence 1: the blunt operator override, independent of any tier. Preserved verbatim
>     # from the pre-tier behaviour so a deployment that set it keeps working.
>     # LITERAL "all": this is the chart/config vocabulary (userActivity.visibility), not
>     # TierResolver's return. Do not substitute TIER_ALL here.
>     if settings.user_activity_visibility == "all":
>         # A served wide decision, counted as one: a deployment that set the blunt
>         # override should see that fact on the graph rather than a mysterious all-tier.
>         signals.note_decision("usage", TIER_ALL)
>         return viewer, TIER_ALL
>     # Restrictions off (or proxy off) runs no tier machinery — but Usage is NOT the wide
>     # view, so it stays self here rather than widening. This mirrors the pre-tier behaviour,
>     # where /api/dashboard/activity was governed by userActivity.visibility alone and never
>     # by the visibility tier: turning cluster-data restrictions off must not, as a side
>     # effect, expose colleagues' presence records.
>     if not restrict:
>         return viewer, TIER_SELF
>     state_resolver = getattr(app.state, "usage_tier_resolver", None)
>     if not viewer or (state_resolver is None and usage_tier_resolver is None):
>         signals.note_decision("usage", TIER_SELF)
>         return viewer, TIER_SELF
>     try:
>         tier = (state_resolver.resolve(viewer) if state_resolver is not None
>                 else usage_tier_resolver(viewer))
>     except Exception:  # noqa: BLE001
>         # An API-server blip degrades the Usage VIEW to the reader's own rows, never the
>         # availability and never the wide set — the same discipline viewer_scope follows.
>         log.exception("usage tier resolution failed for %r; serving the self view", viewer)
>         signals.note_decision("usage", TIER_SELF)
>         return viewer, TIER_SELF
>     scope = TIER_ALL if tier == TIER_ALL else TIER_SELF
>     signals.note_decision("usage", scope)
>     return viewer, scope
> ```
>
> Optional polish (behaviour-identical, not required to pay the debt): rewrite
> `require_admin_tier`'s `scope != "all"` and the static `"scope": "all"` / `"scope": "self"`
> stamps the same way. **Do not** touch the three leave-alone classes above. A blanket
> substitute-all is the regression A2 exists to catch.

> **Cursor:** **A3 — CONFIRMED.** The replacement keeps a single equality against one constant
> (`tier == TIER_ALL`) and maps everything else to `TIER_SELF`. It is not a set membership
> test, not truthiness, not `startswith`, not `is`. The comment that records the discipline
> ("Only the exact string `all` widens") stays. Full replacement is the `viewer_scope` /
> `usage_scope` block under A2.

> **Cursor:** **A4 — CONFIRMED.** `gsd/api.py` already imports `TierResolver` from `gsd/kube.py`;
> `gsd/kube.py` has no import of `gsd.api` (only API *path* constants and comments). Measured:
> `import gsd.api; import gsd.kube` succeeds and prints `ok all`. Adding `TIER_ALL` /
> `TIER_SELF` to the existing import cannot create a cycle. The constants describe
> `TierResolver.tier_for`'s return vocabulary and already document the wire `scope` purpose
> in `kube.py` — that is a defensible owner. Moving them to a neutral module is in-scope as a
> recommendation and **out of scope for this PR**; two string assignments do not justify a new
> module. Full replacement is the import line under A2.

> **Cursor:** **A5 — CONFIRMED** for the A2 replacement: with constants equal to `"all"` /
> `"self"`, every serialised `scope` byte stays identical. Attacked via the baseline suite
> (1460 passed) on unmodified code, and via the mutation run showing consumers already assert
> the literal `"all"` on the wire through real endpoints. After the A2 rewrite, returns use
> `TIER_ALL`/`TIER_SELF` which are those same objects/values today — `json` emits the same
> characters. If a future edit changes the constant's spelling, the wire changes *by the
> constants' own documented purpose*; that is not a silent contract break introduced by this
> diff, it is an intentional vocabulary change. The false-friend sites left as literals are
> what keep an accidental constant rename from rewriting config or the groups filter.

> **Cursor:** **Debt A worth-making.** Correct, small, and **not** a live hazard (measured).
> Worth the decision-site diff under A2 because it names the producer's vocabulary at the two
> policy chokepoints and documents the config false friend in a comment. Not worth a
> mechanical replace of every `"all"`/`"self"` in the file. "Correct but not worth inventing
> more work" applies to sweeping every handler's `scope == "all"`.

> **Cursor:** **B1 — CONFIRMED.** Steelman first: `settling` could mean "the list that left the
> settling stage" (pipeline-stage name), the way `parsed` names the parse stage's output.
> That reading loses against the same function's DEBUG line, which calls
> `len(parsed) - len(settling)` the count **still settling**. Measured with a scratch script
> against the real helpers:
>
> ```text
> SETTLE 30 WINDOW 0:00:01
> OLD at … recordable: True
> NEW at … recordable: False
> result users: ['old_user']
> ```
>
> `_recordable` keeps the attempt that has **finished** settling and drops the one still
> inside the horizon. A maintainer who trusts the local name would believe the complement.
> Rename is worth the three identifier edits. Full replacement under B2.

> **Cursor:** **B2 — REFUTED as "four occurrences, none a string".** Measured:
>
> ```text
> $ grep -n settling local-development/gsd/logincapture.py
> 256:        settling = _recordable(parsed)
> 257:        attempts = _not_clipped(settling, window_start)
> 269:                  "withheld %d still settling (returns next cycle), dropped %d clipped at the "
> 273:                  len(parsed), len(parsed) - len(settling), len(settling) - len(attempts),
> ```
>
> Four matching *lines*; three bind/use the local (`256`, `257`, two NAME uses on `273`);
> line `269` is a **log format string** whose phrase `still settling` is correct English for
> the withheld count and must **not** be renamed. Project-wide Python search finds no reader
> outside `gsd/logincapture.py#capture_once` (only this review's citation test mentions the
> word). The rename is total over the **identifier**, not over the substring in the log.
> Replacement — only the local, arithmetic shape unchanged, WHY-comments kept:
>
> ```python
>         parsed = parse(lines)
>         settled = _recordable(parsed)
>         attempts = _not_clipped(settled, window_start)
>         horizon = _settle_horizon(lines)
>
>         # THE LINE THAT MAKES SILENCE LEGIBLE, and the reason this module gained any DEBUG at all.
>         # In steady state every path from here down is quiet — no NEW attempts means no INFO — so a
>         # working capture and a broken one produce identical logs. Measured on the reference
>         # cluster: 73 attempts stored, 13 distinct users, and not one line in the pod log to say
>         # capture was running.
>         #
>         # "settled through", not "advances to": store.set_login_watermark applies max(), so a late
>         # write from a demoted leader cannot rewind it and this horizon may not become the new one.
>         log.debug("%s: %s read %d line(s) covering the last %ds from read position %s — parsed %d, "
>                   "withheld %d still settling (returns next cycle), dropped %d clipped at the "
>                   "window's leading edge (gone for good), %d to write; log settled through %s",
>                   cluster.name, pod, len(lines), since,
>                   settled_through or "none (first-sight window)",
>                   len(parsed), len(parsed) - len(settled), len(settled) - len(attempts),
>                   len(attempts), horizon or "nothing yet — read position holds")
> ```

> **Cursor:** **B3 — CONFIRMED.** The three counts remain
> `len(parsed) - len(settled)`, `len(settled) - len(attempts)`, `len(attempts)` in that order.
> Any rename that also introduces `withheld = …`, rearranges the tuple, or "clarifies" the
> arithmetic is **refused** here even if algebraically equivalent. Full replacement is the B2
> block.

> **Cursor:** **B4 — CONFIRMED: `settled`.** It is the grammatical complement of the unchanged
> log token `still settling`, so the DEBUG line reads without a glossary.
> `recordable` matches `_recordable` but forces the log reader to translate between helper
> vocabulary and the sentence in the same format string. No third name beats that contrast.
> Full replacement is the B2 block.

> **Cursor:** **B5 — REFUTED as a better fix for this debt.** A `withheld = len(parsed) - len(settled)`
> local would make the log line prettier and is a fine *later* cleanup. It is scope creep for
> a claimed pure rename, and B3 forbids it in this change. Keep the inline arithmetic.

> **Cursor:** **Debt B worth-making.** Yes — three identifier edits, measured local-only, log
> prose left correct, arithmetic untouched. Higher clarity per line changed than Debt A.

> **Cursor:** **Whole-change debt summary.**
> - **DEBT-AVOIDED:** not coupling `user_activity_visibility` or the groups `state` filter to
>   `TIER_*`; not tidying the capture DEBUG arithmetic; not moving the constants to a new module.
> - **DEBT-ACCEPTED:** downstream handlers may keep `scope == "all"` literals after
>   `viewer_scope` has already normalised the vocabulary — duplicated spelling, low risk.
> - **DEBT-INTRODUCED:** none, if the A2 leave-alone sites are respected; a blanket literal
>   sweep would introduce the false-friend coupling A2 names.
>
> Both changes are behaviour-preserving at current constant values. Debt B is worth landing.
> Debt A is worth landing only as the decision-site rewrite; it is duplicated knowledge already
> guarded by `tests/test_visibility_tier.py`, not an open hazard.

---

## Arbitration (Claude, after both passes)

Both reviewers **refuted A2 and B2**, the two claims most likely to turn a "pure rename" into a
regression. They **converge** on A1, A3, A4, A5, B1, B3, B4 (`settled`) and B5 (scope creep,
refused). One genuine disagreement, resolved below on documented evidence.

### The disagreement: how far does the A2 rewrite go?

- **Codex:** rewrite ONLY the two `tier == "all"` comparisons. It classified ~32 wire-`scope` sites
  as a separate vocabulary that "deliberately stay `all`/`self` even if the resolver's internal
  vocabulary changes".
- **Cursor:** rewrite the two DECISION FUNCTIONS whole — comparisons, return arms and
  `note_decision` labels — because treating the wire as a second dialect "invents a translation
  layer the codebase does not document", and leaves the named duplication mostly intact.

**RULED FOR CURSOR, on the declaration's own comment.** `gsd/kube.py`, immediately above the
constants:

```python
# The two visibility tiers. Plain strings rather than an enum so they can sit directly in the
# `scope` field the API's responses already carry (/api/dashboard/activity's shipped contract).
TIER_SELF = "self"
TIER_ALL = "all"
```

The constants exist **precisely** to be the wire values. Codex's "separate wire dialect" premise is
contradicted by the line that declares them, so its narrow remedy is under-scoped — correct as far
as it goes, but it would leave the debt in place and add an undocumented distinction. Verified by
reading `gsd/kube.py` directly, not taken from either reviewer's summary.

Codex's classification work is still what makes this safe: its 43-literal AST inventory found the
false friends, including one neither I nor the brief anticipated — `store.groups(cluster_id, "all")`,
where `all` means all group *states*, not a tier.

### SETTLED SCOPE — Debt A

Import: `from .kube import TIER_ALL, TIER_SELF, TierResolver`

**Rewrite, in `gsd/api.py#build_app`'s `viewer_scope` and `usage_scope` only:** every `"all"` /
`"self"` that is a tier or a served scope — the restrictions-off return, both `scope = ... if tier
== ... else ...` expressions, every fail-closed `return viewer, ...`, and every
`signals.note_decision(...)` scope argument.

**LEAVE AS LITERALS — all three agreed, and a blanket sweep here is the regression:**

1. `settings.user_activity_visibility == "all"` in `usage_scope` — the operator's
   `userActivity.visibility` chart value, parsed by `gsd/config.py#_visibility_setting`. A different
   owner and a vocabulary free to diverge.
2. `gsd/api.py#list_groups`'s `state: str = Query(default="all", pattern="^(all|empty|unattributed)$")`
   and `gsd/api.py#list_alerts`'s `store.groups(cluster_id, "all")` — a group-STATE filter, not a
   tier.
3. Every docstring, comment and log string, including the `# Only the exact string "all" widens`
   comment and the `resolve(viewer) -> "all" | "self"` seam comment. Prose stays prose.
4. Downstream `scope == "all"` consumers outside the two decision functions. **DEBT-ACCEPTED**,
   recorded rather than fixed: they compare an already-normalised string, so the duplication is
   low-risk, and sweeping them would multiply the diff without adding safety.

### SETTLED SCOPE — Debt B

Rename the local `settling` → `settled`. **Exactly four `NAME` tokens** (`gsd/logincapture.py`
lines 256, 257, and twice on 273). Confirmed independently three times: Codex by Python
tokenization, Cursor by read, and by me — `grep -c` reports four *lines* while `grep -o '\bsettling\b'`
reports five *matches*.

**The fifth match is the trap.** Line 269's format string `"withheld %d still settling (returns
next cycle)"` is correct operator-facing prose about the withheld attempts. A `sed
s/settling/settled/g` would rewrite it and make the log line state the opposite of what it counts.

`settled` over `recordable`: it is the grammatical complement of the unchanged `still settling` in
the same format string, so `parsed - settled` reads as withheld without consulting the helper.

**Do NOT** hoist the withheld count into a named local (B5). Both reviewers refused it as scope
creep on a claimed pure rename; it is a legitimate separate change.

### Is it worth landing?

Debt B: yes — highest clarity per line changed, and the inverted name is a live trap for the next
editor. Debt A: yes, but **only** as the decision-site rewrite. It is duplicated knowledge already
guarded by `tests/test_visibility_tier.py` — six failures on a mutated constant — not an open
hazard. Neither claim should be sold as a security fix.

### The measurement discrepancy — RESOLVED, and Codex was right

Codex reported **1310 passed** with `--ignore tests/test_ui.py` and honestly declined to claim the
brief's 1459. I recorded that as an unexplained off-by-one. It is explained, and the error was mine:

- The brief's 1459 was measured at `ee99856` with a clean tree, BEFORE this review doc existed.
- Adding this doc adds exactly one parameterised case,
  `tests/test_docs_diagrams.py::test_every_fence_is_closed[REVIEW_tier_constants_and_settling_name.md]`
  — a fence-balance check that runs over every doc. Measured: `--collect-only` reports 1463 at HEAD
  and 1464 with the doc present.
- So the real baseline while both reviewers were working was **1460 passed, 4 deselected**, and
  1460 − 150 (the Chromium tests Codex cannot run) = **1310**. Codex's number was internally
  consistent the whole time.

Fable proposed a different explanation — that the `REVIEW_ARTIFACTS` registration in
`tests/test_docs_citations.py` added the test. Measured and **refuted**: that module reports 328
with the doc present and 328 with it absent, because registering an artifact *excludes* it from the
citation scan rather than adding a case.

**The gate for implementation is therefore 1460 → 1460, not 1459.**
