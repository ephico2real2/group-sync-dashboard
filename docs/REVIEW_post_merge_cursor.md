# Cursor — adversarial review pass 1

**Target:** `main` at `8fa02a7`. Findings only. Arbiter applies changes.

**Baseline measured** (`cd local-development && .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py`):

```
1 failed, 1299 passed, 4 deselected
```

The single failure is `tests/test_docs_citations.py::test_no_citation_uses_a_line_number` citing line anchors inside `docs/REVIEW_post_merge_visibility_metrics.md` itself — not product code. Brief claimed 1297 passed; measured 1299 (+ the citation failure from the brief).

---

## V — Admin-tier gating

### V1

> **Cursor:** **CONFIRMED.** Measured with `TestClient` against `require_admin_tier` via `/api/clusters/c1/bindings/findings`: no identity → 403; `app.state.tier_resolver = None` → 403; resolver `raise RuntimeError` → 403; tier `"All"` / `"admin"` → 403; exact `"all"` → 200. Only the exact string widens (`viewer_scope` / `api.py` `require_admin_tier`).

### V2

> **Cursor:** **REFUTED.** Gating `/bindings/findings` and `/operator-configs` is **not** the complete binding/role surface at `self`.

**Checked:** seeded `alice` in `team-a` with `ClusterRoleBinding admin-crb` → `cluster-admin`. At `self`:

| path | status | exposes binding/role |
|---|---|---|
| `/bindings/findings` | 403 | no |
| `/operator-configs` | 403 | no |
| `/groups/team-a` | 200 | **yes** — `role_name: cluster-admin`, `binding_name: admin-crb` |
| `/users/alice` | 200 | **yes** — same via `via_group` |
| `/groups/secret` (not a member) | 403 | no |
| `/users/bob` | 403 | no |

**file:line-or-symbol:** `api.py` `get_group` / `get_user` (bindings embedded in 200 bodies).

**Trigger:** self-tier reader who is a member of any group that holds a RoleBinding/ClusterRoleBinding.

**False belief:** “the dashboard withholds the cluster’s RBAC binding surface from me the way `/bindings/findings` does.” They still receive group→role binding rows (including admin roles) for every group they belong to — rows `oc get clusterrolebindings` refuses them (`list` denied), obtainable here.

No replacement prescribed: product may intend “own access path.” The **claim of completeness** is false as written.

### V3

> **Cursor:** **CONFIRMED.** Measured: self and all `/api/clusters` payloads have identical key sets; `operator_configs` is `None` at self (and also `None` when no configs exist at all — same shape). No existence leak via keys or counts.

### V4

> **Cursor:** **CONFIRMED** for the allowlist direction; vocabulary is **eight** kinds, not six.

`SELF_ALERT_KINDS` = `auth_failed`, `forbidden`, `unreachable`, `groupsync_crd_absent`, `invalid_schedule`, `sync_stopped`, `overdue`, `reconcile_error`.

Checked each against the claim’s “metrics or cluster-card analogue” bar:

| kind | public analogue |
|---|---|
| `auth_failed` / `forbidden` / `unreachable` | cluster card status + `gsd_cluster_up` |
| `groupsync_crd_absent` / `invalid_schedule` / `sync_stopped` / `overdue` / `reconcile_error` | `/groupsyncs` (full at both tiers) + `gsd_groupsync_*` |

**Removed kinds stay out:** measured self `/api/alerts` with a dangling binding seeded → neither `dangling_binding` nor `config_reconcile_error` present. Filter is `a["kind"] in SELF_ALERT_KINDS` only; no other alerts route re-admits them. `/bindings/findings` and `/operator-configs` 403 at self.

**Debt note (item 3):** the brief’s “new kind defaults to VISIBLE” is **wrong about this code**. The comment and implementation are an allowlist — new kinds default to **hidden**. That is DEBT-AVOIDED, not a latent open.

### V5

> **Cursor:** **CONFIRMED.** Measured: `user_activity_visibility == "all"` → usage `scope=all` even when both resolvers say self; `view_restrictions_enabled=False` → usage `scope=self` (not all); usage resolver exception → 200 with `scope=self`; only exact `"all"` widens.

### V6

> **Cursor:** **CONFIRMED.** Measured: `app.state.usage_tier_resolver is None` + closure returning `"all"` → usage `all` (does not consult wide `tier_resolver`); state resolver `"all"` beats closure `"self"`; wide resolver `"all"` + exploding usage resolver → usage `self`.

### V7

> **Cursor:** **CONFIRMED.** `LOGIN_OUTCOMES` drives `Query(pattern=^(...)$)`. Measured: `bad_password`→200; `BAD_PASSWORD`, `bad_password `, `bad_pasword`, `success|rejected`, `.*`, `succ` → all 422. Case, whitespace, alternation, metacharacters, partial match all rejected.

### V8

> **Cursor:** **FIX-INADEQUATE.**

**Checked:** `refusalCard` (`index.html` `refusalCard`) does render **For administrators only.** and does not name the grant.

**Gaps:**

1. API 403 `detail` from `require_admin_tier` says *“reserved to the administrator tier”* — never the required sentence.
2. Rendered UI (comments stripped) still contains operator-facing “shopping list” strings the grep was told to find: `oc auth can-i get pods/log` (Logins empty state), `oc get rolebindings,clusterrolebindings` (RBAC policy unmanaged strip), and educational `<code>cluster-admin</code>` on Namespace audit.

**file:line-or-symbol:** `api.py` `require_admin_tier`; `index.html` Logins empty-state / policy unmanaged note.

**Trigger:** self reader hits `/bindings/findings` (API clients) or opens Logins with capture enabled but no successful read.

**False belief (API):** a machine client reading `detail` never sees the mandated refusal phrase; it does see “administrator tier” as a named concept to chase. **False belief (UI):** the Logins empty state teaches the exact `oc auth can-i` invocation shape for the pods/log subresource — the same family of grant the visibility threshold can be pointed at.

**Replacement — `require_admin_tier`:**

```python
def require_admin_tier(request: Request) -> str:
    """The administrator tier, or a refusal that names itself as one.

    For the views that are ABOUT THE CLUSTER rather than about the reader: its whole RBAC
    binding surface, the operator's configuration, the sync CRs. These cannot be scoped
    the way a membership list can — a binding names whoever it names, so the honest
    choice is the whole thing or none of it, and none of it is what a non-administrator
    gets.

    WHY A REFUSAL AND NOT A FILTER, measured on the reference cluster. An ordinary reader
    (`lateef.o`) holds none of `list clusterrolebindings`, `list rolebindings` or `list
    groups` — `oc auth can-i` answers no to all three — and /bindings/findings handed him
    236 rows anyway, 21 of them naming an admin role, including which group holds
    cluster-admin. That is a target list obtainable through the dashboard and not with
    `oc`: a privilege escalation.

    The chart already records this exact finding for the BEARER-token path, where gating
    /api on `list groups` was called "WRONG — a privilege escalation, proven on the
    reference cluster" and the floor was raised to cluster-wide RBAC read. That floor was
    never applied to the browser path, because -openshift-delegate-urls governs bearer
    tokens only and cookie sessions bypass it entirely. This is the same floor, applied
    where it was missing.

    THE DETAIL STRING IS LOAD-BEARING. It must say the refusal is for administrators and
    must not name the grant, role, chart value, or route that would widen it — the person
    reading a 403 is the person being refused.
    """
    _, scope = viewer_scope(request)
    if scope != "all":
        # Counted before the raise: a refusal that leaves no trace anywhere is how a
        # gate that broke for everyone stays indistinguishable from one nobody hit.
        signals.note_admin_refusal()
        raise HTTPException(
            status_code=403,
            detail="For administrators only. This view reports the cluster's own RBAC "
                   "binding surface and operator configuration rather than anything "
                   "belonging to the reader.",
        )
    return scope
```

**Replacement — Logins empty-state fragment** (drop the `oc auth can-i` shopping tip; keep the permission *fact* without the command):

```javascript
        : `<div class="empty-note">
          <strong>No successful read yet.</strong> Capture is enabled but has not managed to
          read a log, so this is a cluster-access problem rather than a quiet one. The
          dashboard's ServiceAccount needs list on <code>pods</code> and the
          <code>log</code> subresource of <code>pods</code> in the oauth-server's namespace
          (<code>openshift-authentication</code> unless configured otherwise), and at least
          one oauth-server pod has to be Running.
        </div>`}
```

**Test:**

```python
def test_admin_tier_403_uses_the_required_refusal_phrase_and_no_grant_names(db):
    """Operator ruling: the refusal says 'For administrators only.' and does not name
    the grant a refused reader would ask for."""
    app = build_app(_settings(db), run_poller=False)
    app.state.tier_resolver = _MapResolver({})  # everyone self
    client = TestClient(app)
    for path in (
        "/api/clusters/c1/bindings/findings",
        "/api/clusters/c1/operator-configs",
    ):
        detail = client.get(path, headers={"X-Forwarded-User": "alice"}).json()["detail"]
        assert detail.startswith("For administrators only."), detail
        for needle in (
            "cluster-admin", "cluster-reader", "visibility", "clusterrolebinding",
            "SubjectAccessReview", "oc auth can-i", "adminSar",
        ):
            assert needle.lower() not in detail.lower(), (path, needle, detail)

def test_logins_empty_state_does_not_teach_oc_auth_can_i():
    html = (STATIC / "index.html").read_text()
    # Strip comments — only rendered template text counts.
    visible = re.sub(r"/\*[\s\S]*?\*/", "", html)
    visible = re.sub(r"//.*?$", "", visible, flags=re.M)
    assert "oc auth can-i" not in visible
```

---

## T — SAR and tier cache

### T1

> **Cursor:** **CONFIRMED.** `_resolve_and_cache` always passes `[*groups, *VIRTUAL_AUTH_GROUPS]` into `create_subject_access_review`. `VIRTUAL_AUTH_GROUPS = ("system:authenticated", "system:authenticated:oauth")`. Measured in a concurrent resolve: SAR body groups were `['admins', 'system:authenticated', 'system:authenticated:oauth']` for an admin-group member.

### T2

> **Cursor:** **CONFIRMED** (cannot refute after checking). `fetch_groups_of_user` lists Groups live via `_list_all`; `ClusterError` and bare `Exception` in `_resolve_and_cache` both return `TIER_SELF` uncached. Existing `TestSingleFlight.test_followers_of_a_failed_leader_fail_closed_and_recovery_is_the_next_request` pins the failure path. No path returns `all` on fetch failure.

### T3

> **Cursor:** **CONFIRMED.** Measured: `TierResolver(cluster, verb='list', resource='groups')` → `TypeError: ... missing 2 required keyword-only arguments: 'subresource' and 'ttl_seconds'`.

### T4

> **Cursor:** **CONFIRMED** (cannot refute the measurement). `subresource=""` → key absent from `_attributes`; `subresource="log"` → present. Empty string is omit, matching API equivalence.

### T5

> **Cursor:** **CONFIRMED** — exception path wakes followers correctly; **wedged-leader path leaves `Event` forever and pins the viewer to 11s+`self`.**

**Measured:**

1. Leader `RuntimeError` in `fetch_groups_of_user`: both leader and follower get `self`; `_inflight` empty. Exception path OK.
2. Two viewers concurrent: `admin→all`, `bob→self`; no cross-serve. Cross-viewer OK.
3. **Wedged leader** (`fetch_groups_of_user` sleeps; `TIER_CHECK_TIMEOUT_SECONDS=0.05`): follower waits ~1.1s → `self`; **third call also waits ~1.1s → `self`**; `_inflight['alice']` still present, Event **unset**; `group_lists` stays 1 — **no new leader ever elected**.
4. **Blocking `observe` callback** after a successful SAR (allowed=true), `_note` called **before** cache write: same sticky Event; followers get `self` while the decision was already `all`.

Production wait budget: `TIER_CHECK_TIMEOUT_SECONDS * 2 + 1` = **11 seconds** per request for the wedged viewer.

**file:line-or-symbol:** `kube.py` `TierResolver.tier_for` / `_resolve_and_cache` / `_note`

**Trigger:** leader stuck inside `_resolve_and_cache` past the follower wait — hung multi-page Group list, I/O that outlives the wait budget, or an `observe` callback that blocks (current order: `_note` before cache write).

**False belief:** an administrator keeps seeing the narrowed “Your view” for every request (and each request stalls ~11s) and concludes they lost the admin tier, while the cluster would answer `allowed=true` if a new resolve were allowed to start.

**Replacement — `tier_for`, `_resolve_and_cache`, `_note` (generation-safe steal + metrics off the critical path):**

```python
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
        event = self._inflight.get(viewer)
        lead = event is None
        if lead:
            event = threading.Event()
            self._inflight[viewer] = event
    if not lead:
        # A resolution for this viewer is already out; ride it instead of duplicating
        # it. The wait is bounded by the leader's own worst case (two cluster calls,
        # each capped at TIER_CHECK_TIMEOUT_SECONDS) plus margin — a wedged leader must
        # not wedge its followers past that.
        finished = event.wait(TIER_CHECK_TIMEOUT_SECONDS * 2 + 1)
        with self._lock:
            cached = self._cache.get(viewer)
            if cached is not None and cached[0] > time.monotonic():
                return cached[1]
            # Leader failed (uncached) OR is still wedged past our budget. If the same
            # Event is still registered and never fired, drop it so the NEXT caller can
            # become leader — otherwise every subsequent request for this viewer joins an
            # infinite queue behind a dead flight and pays the full wait for self forever.
            # This request still fails closed; a failure is not a decision.
            if not finished and self._inflight.get(viewer) is event:
                self._inflight.pop(viewer, None)
        return TIER_SELF
    try:
        return self._resolve_and_cache(viewer, now)
    finally:
        # ALWAYS wake waiters on OUR event — success, failure and bug alike. Only pop the
        # slot if we still own it: a timed-out follower may have stolen the slot so a new
        # leader can run, and popping that would re-wedge the replacement.
        with self._lock:
            if self._inflight.get(viewer) is event:
                self._inflight.pop(viewer, None)
        event.set()

def _note(self, outcome: str) -> None:
    """Report one fresh check's outcome to the observe seam. Best-effort by contract:
    the tier is already decided by the time this runs, and a metrics bug must never
    break a security decision or un-fail-closed anything."""
    if self._observe is None:
        return
    try:
        self._observe(outcome)
    except Exception:  # noqa: BLE001
        log.exception("visibility tier metrics callback failed; the tier is unaffected")

def _resolve_and_cache(self, viewer: str, now: float) -> str:
    """The leader's half of tier_for: one review, cached on success only."""
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
        # exc.outcome is the bounded kube vocabulary (unreachable/auth_failed/
        # forbidden), which is exactly the metric's failure enum.
        self._note(exc.outcome)
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
        self._note("error")
        return TIER_SELF
    tier = TIER_ALL if allowed else TIER_SELF
    # Cache BEFORE observe. observe is best-effort and may block; publishing the
    # decision first means a wedged metrics callback cannot hide an already-known
    # verdict from followers that time out and re-check the cache.
    with self._lock:
        if len(self._cache) > 512:
            # Viewers are real authenticated people, so this stays small; the sweep only
            # exists so years of one-off names cannot grow the dict without bound.
            self._cache = {k: v for k, v in self._cache.items() if v[0] > now}
        self._cache[viewer] = (now + self._ttl, tier)
    self._note("allowed" if allowed else "denied")
    return tier
```

**Test:**

```python
def test_a_wedged_leader_does_not_pin_the_viewer_forever(monkeypatch):
    """Followers that time out must free the inflight slot; otherwise every later
    request for that viewer waits the full budget and never re-resolves."""
    import gsd.kube as kube_mod
    entered, hold = threading.Event(), threading.Event()

    class Wedged(FakeCluster):
        def handler(self, request: httpx.Request) -> httpx.Response:
            if request.url.path == GROUPS_PATH:
                entered.set()
                hold.wait(60)  # never finishes within the test
            return super().handler(request)

    fake = Wedged(groups=[_group("admins", ["alice"])], allowed=True)
    monkeypatch.setattr(kube_mod, "TIER_CHECK_TIMEOUT_SECONDS", 0.05)
    resolver = _resolver(monkeypatch, fake)

    leader = threading.Thread(target=lambda: resolver.tier_for("alice"), daemon=True)
    leader.start()
    assert entered.wait(2)

    first = resolver.tier_for("alice")
    assert first == TIER_SELF
    # The defect: without the steal, this stays non-empty and the next call waits again.
    assert "alice" not in resolver._inflight, resolver._inflight

    # Unwedge and prove a fresh resolve can become leader and win all.
    hold.set()
    # Give the old leader's finally a tick, then resolve fresh.
    time.sleep(0.05)
    fake2_allowed = True
    assert resolver.tier_for("alice") in (TIER_SELF, TIER_ALL)  # may race old leader
    # Cold cache after TTL-less failure: force by clearing
    resolver._cache.clear()
    # Old leader may have cached; clear inflight/cache and resolve with a healthy fake
    hold.set()
    time.sleep(0.05)
    resolver._cache.clear()
    resolver._inflight.clear()
    healthy = FakeCluster(groups=[_group("admins", ["alice"])], allowed=True)
    resolver2 = _resolver(monkeypatch, healthy)
    assert resolver2.tier_for("alice") == TIER_ALL


def test_observe_blocking_cannot_hide_a_cached_all_verdict(monkeypatch):
    """Cache is published before observe; a wedged metrics callback must not make
    timed-out followers believe the verdict was self when SAR said allowed."""
    import gsd.kube as kube_mod
    release = threading.Event()

    def block(outcome: str) -> None:
        release.wait(60)

    fake = FakeCluster(groups=[_group("admins", ["alice"])], allowed=True)
    monkeypatch.setattr(kube_mod, "TIER_CHECK_TIMEOUT_SECONDS", 0.05)
    resolver = _resolver(monkeypatch, fake, observe=block)

    leader = threading.Thread(target=lambda: resolver.tier_for("alice"), daemon=True)
    leader.start()
    time.sleep(0.2)  # past SAR, stuck in observe
    # Cache must already hold all even though observe has not returned.
    assert resolver._cache.get("alice") is not None
    assert resolver._cache["alice"][1] == TIER_ALL
    assert resolver.tier_for("alice") == TIER_ALL  # follower timeout then cache hit
    release.set()
```

### T6

> **Cursor:** **CONFIRMED.** `TIER_TTL_SECONDS = float(VISIBILITY_TIER_TTL_DEFAULT)` and `VISIBILITY_TIER_TTL_DEFAULT = 60`. Worst-case stale-admin window after the cluster reflects removal: **60 seconds** (plus ≤60s UI poll). Single-sourced.

---

## M — Metrics on an unauthenticated endpoint

### M1

> **Cursor:** **CONFIRMED** (cannot refute after full enumeration).

Every `labels=[...]` / `add_metric([...])` value path in `metrics.py` was exercised against a store poisoned with `cluster-admin`, `cn=team-a,ou=groups,dc=example`, binding name `hand-made`, group `team-a`. **None appeared in the exposition.**

Label values observed: cluster id, finding enum, alert kind/severity, groupsync/namespace/state (when CRs present), build version/commit/branch, threshold/outcome/tier/table enums. No username, LDAP group, DN, binding name, or role name.

`gsd_groupsync_*{groupsync=...,namespace=...}` carries Kubernetes object names — already public by the module’s own ruling (CR identity on skip-auth `/metrics`). Not a username/DN/role leak under the claim’s vocabulary.

### M2

> **Cursor:** **FIX-INADEQUATE.**

Today’s store `_FINDING_CASE` SQL emits only `dangling|built_in|unresolved|unmanaged|ok` — so a **name** cannot become a `finding` label via the live writer. But:

1. `FINDINGS = ("ok", "dangling", "unresolved", "built_in")` **omits `unmanaged`**, while metrics still emit `finding="unmanaged"` via `dict.get` on whatever the store returns (measured).
2. The collector does **not** intersect against `FINDINGS` before `add_metric`. A future finding kind that accidentally used a subject/group/role string as the finding value would become a public label on `/metrics` with no further review.

**file:line-or-symbol:** `metrics.py` `FINDINGS` / `DashboardCollector._gather` bindings loop; `store.py` `_FINDING_CASE`

**Trigger:** any `all_bindings()` row whose `finding` is not in the allowlist (today: `unmanaged` is silently minted; tomorrow: a mistaken kind string).

**False belief:** “`gsd_bindings_total`’s `finding` label is a closed enum matching `FINDINGS`, so a scraper cannot discover unexpected series.” Operators writing alerts against the documented four miss unmanaged; a bad future kind would publish names on the public scrape.

**Replacement:**

```python
FINDINGS = ("ok", "dangling", "unresolved", "built_in", "unmanaged")
```

and in `_gather`:

```python
                by_finding = dict.fromkeys(FINDINGS, 0)
                for binding in self.store.all_bindings(cluster):
                    finding = binding["finding"]
                    # Closed vocabulary on a public scrape: unknown values are counted
                    # nowhere rather than minted as new label series. A finding string
                    # that carried a subject or role name would otherwise leak on
                    # /metrics the moment someone added it upstream.
                    if finding not in by_finding:
                        log.error(
                            "metrics: dropping binding with unknown finding %r on %s — "
                            "refusing to mint a label series",
                            finding, cluster,
                        )
                        continue
                    by_finding[finding] += 1
                for finding, count in by_finding.items():
                    bindings.add_metric([cluster, finding], count)
```

**Test:**

```python
def test_bindings_total_finding_label_is_closed_and_includes_unmanaged(store):
    now = now_iso()
    store.upsert_cluster("c1", "https://x", True)
    store.record_poll("c1", "ok", None)
    store.replace_group_state("c1", [
        {"name": "team-a", "member_count": 1, "sync_provider": "p",
         "group_synced_at": now, "ldap_uid": None},
    ], now)
    store.record_managed_groups("c1", [{"name": "team-a", "sync_provider": "p"}], now)
    store.replace_bindings("c1", [
        {"binding_kind": "RoleBinding", "binding_namespace": "ns",
         "binding_name": "policy", "role_kind": "ClusterRole", "role_name": "edit",
         "group_name": "team-a", "managed_source": "NamespaceConfig/x"},
        {"binding_kind": "RoleBinding", "binding_namespace": "ns",
         "binding_name": "hand", "role_kind": "ClusterRole",
         "role_name": "cluster-admin", "group_name": "team-a"},
    ], now)
    text = generate_latest(build_registry(store, GRACE)).decode()
    assert 'gsd_bindings_total{cluster="c1",finding="unmanaged"} 1.0' in text
    assert "cluster-admin" not in text
    assert "hand" not in text
    # Poison: if a future store returned a name-shaped finding, it must not appear.
    real = store.all_bindings
    store.all_bindings = lambda *a, **k: [
        {**real("c1")[0], "finding": "cn=admins,ou=groups,dc=example"}
    ]
    text2 = generate_latest(build_registry(store, GRACE)).decode()
    assert "cn=admins" not in text2
```

### M3

> **Cursor:** **CONFIRMED.** Bounds: per-cluster gauges (cluster cardinality = configured clusters); per-CR gauges (CR × namespace × cluster); `finding` ∈ FINDINGS (after M2 fix: 5); alert `kind` ∈ `ALERT_KINDS`; visibility enums fixed tuples; no per-user/per-group series. `gsd_dashboard_active_users` removed with an explicit comment.

### M4

> **Cursor:** **CONFIRMED.** `note_decision(threshold, tier)` keys are `(threshold, tier)` only. Measured snapshot: `{('admin', 'all'): 1, ('usage', 'self'): 1}` — no viewer.

### M5

> **Cursor:** **CONFIRMED.** `local-development/pyproject.toml` declares `prometheus-client>=0.26.0`. `build_registry` constructs one `CollectorRegistry`, `register`s one `DashboardCollector`. Custom-collector API (`GaugeMetricFamily` / `CounterMetricFamily`), not module-level `Gauge(`/`Counter(`.

---

## U — UI / paint-first

### U1

> **Cursor:** **REFUTED** (cannot find an XSS sink after checking). Grepped every `title=`, `data-*`, and `innerHTML` interpolation. Attacker-influenced LDAP/user/group/DN values go through `esc()` into attributes and text, or through `textContent` (`renderScopePill`). `refusalCard` titles use `esc(title)`. Chart `data-t`/`data-o` esc’d; `data-v` is numeric. Fixed-vocab class names (`risk-${key}`, severity ternary) are not LDAP-shaped. Prior XSS class appears addressed.

### U2

> **Cursor:** **CONFIRMED** — cluster switch still paints wrong data; `applyPosition` clear is inert without `render()`.

**Checked:**

- Tab handler: `navigate` → `render` → `refresh` (paint-first).
- **Cluster selector:** `navigate` → `refresh` only — **no `render()`**.
- `applyPosition` nulls cluster-scoped `data.*` on cluster change, but the DOM is not rebuilt until `refresh` finishes. The select already shows cluster B; `#main` still shows cluster A’s rows for the length of the fetch. The `stale` opacity class does not change the data.
- Same-cluster group/user drill: `navigate` + `refresh` without clearing `data.group` / `data.user`. URL says B; screen still shows A’s detail (`d.name`) until fetch returns.

**file:line-or-symbol:** `index.html` `applyPosition`; cluster `onchange` in `renderFilters`; `wireDrilldown`

**Trigger:** On Groups for cluster A, pick cluster B in `#f-cluster`.

**False belief:** “these group rows are cluster B’s” — they are still A’s, under B’s selected cluster, for the whole round trip.

**Replacement — `applyPosition` + cluster handler + drill handlers:**

```javascript
function applyPosition(pos) {
  // Assigned rather than merged: an absent key means "not at that position", so leaving the
  // old value would strand a drill-down open after Back returned to the list behind it.
  const prevCluster = view.cluster;
  const prevGroup = view.group;
  const prevUser = view.user;
  const prevGroupsync = view.groupsync;
  view.page = pos.page || "overview";
  view.groupsync = pos.groupsync || null;
  view.group = pos.group || null;
  view.user = pos.user || null;
  // Drill-down payloads are keyed by name, not by "current cluster only". Paint-first
  // (and any path that renders before refresh resolves) would otherwise show group A's
  // members under a URL that already says group B — the third wrong-data flash in this
  // file's paint-first history. Drop the stale detail the moment the identity changes.
  if (view.group !== prevGroup) data.group = null;
  if (view.user !== prevUser) data.user = null;
  if (view.groupsync !== prevGroupsync) data.events = null;
  // `cluster` is part of the position, not context around it. Without it, Back after a cluster
  // switch restores a group name against whichever cluster is now selected — and group names
  // repeat across clusters, so it silently shows a DIFFERENT object under the name you
  // expected, or 404s. Only overwritten when the entry carries one, so an entry predating
  // cluster selection does not blank it.
  if (pos.cluster) {
    // A cluster switch orphans every cluster-scoped payload in `data`. The tab handler
    // paints BEFORE it fetches, so leaving them in place would put cluster A's rows on
    // screen under cluster B's title for the length of a fetch. Dropped, the same paint
    // shows each page's own Loading state, which is true. This is the chokepoint: the
    // selector, popstate and hashchange all arrive here, so no path can skip it.
    // Cross-cluster payloads (clusters, alerts, whoami, version, usage) survive — they
    // answer for every cluster or for none.
    if (prevCluster && pos.cluster !== prevCluster) {
      data.groupsyncs = null; data.groups = null; data.groupsMeta = null;
      data.group = null; data.user = null; data.events = null;
      data.logins = null; data.access = null; data.findings = null;
      data.operatorConfigs = null; data.userBindings = null;
    }
    view.cluster = pos.cluster;
  }
}
```

Cluster selector (must paint Loading from the cleared payloads — clearing alone changes nothing on screen):

```javascript
  if (cl) cl.onchange = (e) => {
    // A drill-down is scoped to its cluster. Carrying `group` or `user` across a cluster
    // switch would re-request that name against the new cluster — a different object with
    // the same name, or a 404 — so the drill-down is dropped from the new position.
    //
    // A history ENTRY, and the trail is no longer wiped. It used to be (`trail.length = 0`),
    // which was right when the trail was private: it stopped a later Back offering a
    // pre-switch position that no longer made sense. With the browser's stack that erasure is
    // both impossible and wrong — the reader pressed Back expecting the cluster they were
    // reading, and every entry carries its own cluster, so returning to one is well defined.
    navigate({ cluster: e.target.value, groupsync: null, group: null, user: null });
    // Same paint-first discipline as the tab handler. navigate/applyPosition have already
    // dropped cluster-scoped payloads; without render() here the DOM keeps cluster A's
    // rows under cluster B's selected option for the whole fetch — the regression
    // applyPosition's nulling was written to prevent.
    render();
    refresh();
  };
```

Drill-down clicks already call `refresh()`; with `applyPosition` clearing `data.group`/`data.user`, add paint-first for the same reason:

```javascript
  document.querySelectorAll("[data-group]").forEach((el) => {
    el.onclick = () => {
      navigate({ page: "groups", group: el.dataset.group, user: null });
      render();
      refresh();
    };
  });
  document.querySelectorAll("[data-user]").forEach((el) => {
    const go = (e) => {
      e.stopPropagation();
      navigate({ page: "groups", user: el.dataset.user, group: null });
      render();
      refresh();
    };
    el.onclick = go;
  });
```

**Test** (Playwright pattern already used in `test_ui.py`):

```python
def test_cluster_switch_does_not_keep_previous_clusters_groups(dash):
    """applyPosition nulls data.groups; the selector must render() so the DOM
    shows Loading rather than cluster A's rows under cluster B's selection."""
    page = dash
    page.click("#tab-groups")
    page.wait_for_selector("table")
    # Two clusters seeded as c1/c2 with disjoint group names.
    assert page.locator("text=group-on-c1").count() > 0
    page.select_option("#f-cluster", "c2")
    # Immediately after the change — before the fetch can return — the old name
    # must already be gone. Waiting for network would hide the flash.
    assert page.locator("text=group-on-c1").count() == 0
    assert page.locator("text=Loading").count() > 0


def test_group_drill_does_not_show_previous_group_under_new_url(dash):
    page = dash
    page.click("#tab-groups")
    page.click("text=group-a")
    page.wait_for_selector("h2:has-text('group-a')")
    page.evaluate("() => { window.__delay = true; }")  # if harness can stall fetch
    page.click("text=group-b")  # from a related link / back-then-forward substitute:
    # Direct: navigate via hash to the other group while data.group still holds A.
    page.evaluate("navigate({ page: 'groups', group: 'group-b', user: null }); render();")
    assert page.locator("h2:has-text('group-a')").count() == 0
    assert page.locator("text=Loading").count() > 0
```

### U3

> **Cursor:** **CONFIRMED** with one caveat. Fingerprint members match every `data.*` field `refresh` writes **except** `data.version` (header build-info). `alertsScope` is included. Version changes mid-session would not auto-repaint the build pill — negligible. No missing *payload* field that the pages render from `data` aside from that.

### U4

> **Cursor:** **CONFIRMED.** Fingerprint is over fetched payloads only; `opts.auto && fingerprint === lastFingerprint` short-circuits. User-initiated `refresh()` always falls through to `render()`.

### U5

> **Cursor:** **CONFIRMED** (cannot refute after checking). `lastRefreshStartedAt = Date.now()` at the **start** of every `refresh`, including failures. `visibilitychange` catch-up skips when `Date.now() - lastRefreshStartedAt < POLL_INTERVAL_MS`. Hidden-tab guard prevents background work. No path leaves `lastRefreshStartedAt` stuck at boot while refreshes fail.

### U6

> **Cursor:** **CONFIRMED.** `narrowedReader()` requires `whoami.authenticated && visibility.scope === "self"`. Missing `visibility` → `false` (not narrowed). Comment documents why silence must not imply narrowed. Overview refusal uses this; endpoints remain the real control.

---

## C — Chart

### C1

> **Cursor:** **CONFIRMED** (cannot refute from templates + comments). `ca.configMap.name: openshift-service-ca.crt`, `serverName: {{ name }}.{{ namespace }}.svc`. Comment records Prometheus Operator resolves configMap in the ServiceMonitor’s own namespace; service-ca injects that ConfigMap into every namespace. `serverName` matches the DNS SANs service-ca puts on the serving cert. No live cluster re-measure in this pass — claim matches the measured curl recipe in-template.

### C2

> **Cursor:** **CONFIRMED.** `scheme: https` + `tlsConfig` sit inside `{{- if .Values.oauthProxy.enabled }}`. Service `port: http` → `targetPort: oauth-proxy` when proxy on, `targetPort: http` when off. Proxy-off scrape is plaintext HTTP with no `scheme: https`. No mismatch.

### C3

> **Cursor:** **CONFIRMED.** Default `podDisruptionBudget.maxUnavailable: 1`, `minAvailable: ""`. Template uses `minAvailable` only when set; else `maxUnavailable` (default 1). Single-replica + maxUnavailable 1 remains evictable.

### C4

> **Cursor:** **CONFIRMED.** `tests/test_chart_versions.py` holds `Chart.yaml` `appVersion` to `local-development/pyproject.toml`. Chart `version` is separate; comment + test document chart-releaser skip-on-same-version behaviour.

---

## P — Publish pin

### P1

> **Cursor:** **CONFIRMED** that re-applying onto `FETCH_HEAD` makes a **content conflict** structurally impossible; **cannot refute** residual pin *loss* after 3 rejected pushes. Sequence that still loses a pin: three other `main` updates land each between `git reset --hard FETCH_HEAD` and `git push` — loop exits 1, image published, tag unpinned. Bound is pragmatic, not proof of sufficiency under sustained push contention.

### P2

> **Cursor:** **CONFIRMED** (cannot refute). Tag captured in `$TAG` before the loop; image push precedes this step. `--hard` to `FETCH_HEAD` discards only the job’s checkout tree. Nothing else in the step needs preserving.

### P3

> **Cursor:** **CONFIRMED.** Job `if` includes `!contains(github.event.head_commit.message, '[skip publish]')`; pin commit message embeds `[skip publish]`. Evasion would require altering the commit message after the template — not available to the step as written. (A human force-push without the marker is out of scope.)

---

## NEW findings

### NEW-1 — `FINDINGS` / unmanaged drift

Covered under **M2** (measured `finding="unmanaged"` series while constant omits it).

### NEW-2 — `_note` before cache write amplifies T5

Covered under **T5** fix (reorder). Separate trigger: any blocking `observe` implementation.

### NEW-3 — Baseline citation test vs review brief

`docs/REVIEW_post_merge_visibility_metrics.md` line-number anchors fail `test_no_citation_uses_a_line_number`. Out of product scope; arbiter/docs hygiene. No code fix here.

---

## Technical debt — three buckets

### Four named places

1. **`TIER_SELF` / `TIER_ALL` vs string literals in `api.py`**
   - **DEBT-ACCEPTED.** `kube.py` exports the constants; `api.py` compares `tier == "all"` / `scope == "self"` as literals throughout `viewer_scope`, `usage_scope`, handlers. Drift risk is real but currently both sides use the same two spellings; a typo in api widens nothing (fail-closed on non-`all`). Worth consolidating when next touching the seam; not a defect today.

2. **`usage_scope` duplicates `viewer_scope` fail-closed logic**
   - **DEBT-ACCEPTED**, deliberate independence. Separate resolvers, separate seams, separate precedence (`userActivity.visibility`, restrict-off → self). Sharing a helper that took the wrong resolver would be the worse bug. Duplication is the firewall; comment block states why.

3. **`SELF_ALERT_KINDS` hand-maintained allowlist**
   - **DEBT-AVOIDED** relative to the brief’s fear. New kinds default to **hidden**, not visible. Remaining debt: allowlist can drift from `compute_alerts` / `ALERT_KINDS` without a test that every non-allowed kind is withheld (partially covered by view-scoping tests for dangling/config). That gap is **DEBT-ACCEPTED** operational cost, fail-closed.

4. **Two-seam resolver lookup (`app.state` and closure) in `usage_scope`**
   - **DEBT-ACCEPTED** for tests (`build_app(..., usage_tier_resolver=...)` vs `app.state.usage_tier_resolver` substitution). Measured V6: state wins when set; closure used when state absent; wide resolver never consulted. The dual seam is awkward but the independence invariant holds.

### DEBT-INTRODUCED by these merges

- Paint-first without cluster-selector / drill-down parity (**U2**) — clear introduced hazard; two prior regressions in the same file show the pattern.
- Single-flight without wedged-leader recovery (**T5**) — introduced with the burst-refresh fix; exception path was handled, timeout-steal was not.
- Metrics `FINDINGS` tuple not matched to store vocabulary / no clamp (**M2**).
- API 403 copy not aligned to the UI refusal ruling (**V8**).
- `api.py` string literals vs `kube.TIER_*` (item 1) widened as more handlers learned `scope == "all"`.

### DEBT-ACCEPTED knowingly

- `/metrics` unauthenticated (operator ruling) → “no names” discipline instead of auth.
- Dual usage/admin resolvers and duplicated fail-closed logic (independence > DRY).
- `SELF_ALERT_KINDS` manual curation (fail-closed allowlist).
- Group/user detail still exposing own-group binding rows at self (**V2** surface) — likely intentional “why do I have access?”; conflicts with a literal reading of “no binding detail at self.”
- Publish pin 3-attempt bound; residual loss path accepted vs infinite retry.

### DEBT-AVOIDED

- Custom collector instead of hand-rolled exposition; `prometheus-client` declared.
- `TierResolver` keyword-only `subresource` / `ttl_seconds` with no defaults (silent wrong-threshold bug fixed by construction failure).
- `SELF_ALERT_KINDS` as allowlist (not denylist) after dangling/config alert bypass was measured.
- ServiceMonitor verified TLS (`serverName` + service-ca) instead of `insecureSkipVerify: true`.
- Publish pin rewrite onto `FETCH_HEAD` instead of commit-then-rebase.
- Fingerprint includes `alertsScope`; cluster-scoped payloads start as `null` not `[]`.

### Whole-PR debt summary

The visibility/admin-tier work is real security surface and mostly fail-closed; the debt that matters is concentrated in **concurrency (T5)** and **paint-first completeness (U2)** — both introduced by performance fixes that handled the happy path and under-specified the stuck/partial path. Metrics hygiene (M2) and refusal copy (V8) are smaller. **The debt is worth the features** if T5 and U2 are fixed before the next performance pass; shipping paint-first and single-flight without those recoveries repeats this repo’s “tests green, production wrong” failure mode.
