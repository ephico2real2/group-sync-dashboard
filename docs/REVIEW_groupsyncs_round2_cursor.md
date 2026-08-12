# Round 2 review — `/groupsyncs` self-tier design (revised)

Measured 2026-08-11 against this worktree. Nothing implemented; findings only.

```text
cd local-development && .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py
1388 passed, 4 deselected, 1 warning in 178.75s

.venv/bin/python -m pytest tests/test_docs_citations.py -q
275 passed in 8.72s

.venv/bin/python -m pytest tests/test_ui.py -q
149 passed in 68.72s
```

Baseline here is **1388 / 4 deselected**, not the brief's 1363.

Admin constraint checked first: the revision's self-only projection and
`SELF_ALERT_DETAILS` rewrite do **not** narrow an `all`-tier row. No admin defect in the
shape as written. The defects are in what the self tier keeps, and in a false UI premise
for alert `detail`.

---

### Q1
REFUTED

Anchor: `gsd/api.py#list_groupsyncs`, and the unfinished SPEC test
`docs/SPEC_per_user_visibility.md` § `test_groupsyncs_omit_directory_detail_at_self`.

`frozenset({"provider_keys"})` is too strict. Measured non-UI / contract consumers that
require more than `provider_keys` at self:

1. **The SPEC this design claims to finish.** Its drafted test says *"CR health is
   governance data and stays visible; ldap_filter and error_message …"* and asserts the
   list is non-empty while only those two fields go. A `provider_keys`-only row fails that
   contract:

```text
provider_keys-only drops health fields the SPEC keeps:
[{'provider_keys': ['ldap-sync_ldap']}]
```

2. **`local-development/API.md`** documents the full CR health object for
   `GET .../groupsyncs` and states only that endpoint "does not vary by tier" today — the
   documented self-tier shape is the health row, not a colour-slot stub.
3. **`tests/test_view_scoping.py#test_cr_health_stays_full_view_because_metrics_already_publishes_it`**
   pins the /metrics theatre rule for this endpoint. Measured `/metrics` on the visibility
   seed still publishes per-CR `name`, `namespace`, `state`, `group_count`, `last_sync_at`,
   and the reconcile-error **bit**. Withholding those behind login while `/metrics` serves
   them unauthenticated is the theatre that comment forbids.

No separate shell script curls `/groupsyncs`. The real unmet requirement is the SPEC/API
contract the design itself cites — not a third-party client.

**Debt objection (holds):** deriving the allowlist from "what `crSlot` reads today" relocates
SKIP_AUTH_PATHS debt into feature completeness. A new self-tier consumer (or the SPEC's
already-written health expectation) silently gets an empty hole until somebody widens the
frozenset. Fail-closed is right for *security*; claiming it is "no debt" and "the opposite
of SKIP_AUTH_PATHS" is false — it is the same shape of list, with the failure mode flipped
from leak to lie. Durable form: allowlist = every field the SPEC keeps (all current keys
minus the two directory diagnostics), enforced by the partition test. New fields still fail
closed until classified; UI growth does not redefine the API.

Attacked: searched the repo for `/groupsyncs` callers; ran the visibility seed; compared
`/metrics` samples to the wide row's 17 keys; simulated `provider_keys`-only against the
SPEC assertion.

Complete replacement constants + route (admin row untouched):

```python
#: Self-tier GroupSync projection. Allowlist = SPEC "FULL except ldap_filter and
#: error_message", not "whatever the Groups tab reads today".
#:
#: Why not frozenset({"provider_keys"}): that couples the HTTP contract to one UI helper
#: (crSlot). The unfinished SPEC test this change ships already requires the CR health
#: row to stay visible; /metrics already publishes name/namespace/state/group_count/
#: last_sync_at/error bit to a credential-less curl, so withholding those here is theatre.
#: provider_keys stays because crSlot needs it AND /groups already serves the same
#: <cr>_<provider> string at self (measured).
#:
#: New enrich()/store columns are withheld until listed here or in WITHHELD — fail-closed,
#: same shape as SELF_ALERT_KINDS, with the partition test forcing an explicit choice.
SELF_TIER_GROUPSYNC_FIELDS = frozenset({
    "name",
    "namespace",
    "schedule",
    "schedule_valid",
    "state",
    "last_sync_at",
    "next_expected",
    "interval_seconds",
    "generation",
    "group_count",
    "observed_at",
    "provider_keys",
    "error_at",
    "error_generation",
    "error_is_current",
})

#: Directory diagnostics omitted at self. Partitioned against SELF_TIER_GROUPSYNC_FIELDS
#: so a newly added key is a red build rather than a quiet leak or a quiet UI hole.
WITHHELD_AT_SELF_GROUPSYNC_FIELDS = frozenset({"ldap_filter", "error_message"})


@app.get("/api/clusters/{cluster_id}/groupsyncs")
def list_groupsyncs(request: Request, cluster_id: str) -> list[dict]:
    """GroupSync CRs on one cluster, with their derived state.

    `state`, `next_expected` and `error_is_current` are computed per request from the
    schedule and the last sync, never stored — a stored state would be wrong the moment
    the clock moved past it.

    Bare list on purpose: this is field-withholding, like `/api/clusters` (not row-scoping).
    The all tier receives the complete enriched row, including `ldap_filter` and
    `error_message` byte-for-byte. The self tier is projected through
    SELF_TIER_GROUPSYNC_FIELDS so a new store/enrichment column is withheld until it is
    explicitly ruled on. The two withheld fields can embed directory DNs and the gate
    group, which `/metrics` deliberately never carries.
    """
    require_cluster(cluster_id)
    _, scope = viewer_scope(request)
    now = datetime.now(UTC)
    rows = [enrich(cr, now) for cr in store.groupsyncs(cluster_id)]
    if scope == "self":
        rows = [
            {field: cr[field] for field in SELF_TIER_GROUPSYNC_FIELDS}
            for cr in rows
        ]
    return rows
```

Complete test (fails before, passes after):

```python
def test_groupsyncs_omits_directory_detail_at_self(client):
    """CR health stays; only ldap_filter and error_message go. Admin unchanged."""
    mine = client.get("/api/clusters/c1/groupsyncs", headers=H("alice")).json()
    wide = client.get("/api/clusters/c1/groupsyncs", headers=H("root")).json()
    assert mine and isinstance(mine, list)
    for cr in mine:
        assert "ldap_filter" not in cr
        assert "error_message" not in cr
        assert "name" in cr and "state" in cr and "provider_keys" in cr
        assert set(cr) == SELF_TIER_GROUPSYNC_FIELDS
    assert wide[0]["ldap_filter"] == "(&(objectClass=groupOfNames)(cn=app-*))"
    assert wide[0]["error_message"] == (
        "LDAP bind failed for cn=svc,ou=people: invalid credentials"
    )
```

Measured against current code: `AssertionError` on `ldap_filter` still present for alice.

Consequence if the design ships as written: a narrowed reader (or the SPEC's own test)
believes `/groupsyncs` at self carries no CR identity or health, while credential-less
`/metrics` and the unfinished SPEC both say the opposite — and an operator believes the
SPEC ruling was implemented when it was replaced by a UI-helper stub.

---

### Q2
CONFIRMED

Anchor: `gsd/store.py#Store.groupsyncs`, `gsd/api.py#enrich`.

Attacked the slip the question names: a production field absent from the fixture wide
payload. Measured on the visibility seed and on a minimal CR (`ldap_filter=None`,
`schedule=None`, no error row):

```text
fixture wide keys  == minimal enriched keys
both always:
['error_at', 'error_generation', 'error_is_current', 'error_message', 'generation',
 'group_count', 'interval_seconds', 'last_sync_at', 'ldap_filter', 'name', 'namespace',
 'next_expected', 'observed_at', 'provider_keys', 'schedule', 'schedule_valid', 'state']
```

`Store.groupsyncs` SELECT lists every column; `enrich` always adds the derived keys. NULL
is still a present key. A partition of `set(wide_row) == ALLOWLIST | WITHHELD` against a
live wide response therefore fails when a new column appears — it cannot slip by being
"absent from the fixture while present in production" under the current read path.

Confirmed only for that shape of test. A test that merely checks
`ldap_filter not in mine` without the exhaustive union is FIX-INADEQUATE (not what the
design proposes).

Complete partition test:

```python
def test_groupsync_tier_policy_is_exhaustive(client):
    """Every wide key is classified; alice's row is exactly the allowlist."""
    wide = client.get("/api/clusters/c1/groupsyncs", headers=H("root")).json()[0]
    mine = client.get("/api/clusters/c1/groupsyncs", headers=H("alice")).json()[0]
    assert SELF_TIER_GROUPSYNC_FIELDS.isdisjoint(WITHHELD_AT_SELF_GROUPSYNC_FIELDS)
    assert set(wide) == SELF_TIER_GROUPSYNC_FIELDS | WITHHELD_AT_SELF_GROUPSYNC_FIELDS
    assert set(mine) == SELF_TIER_GROUPSYNC_FIELDS
```

Measured against current code: fails because alice still receives the withheld keys.

Consequence if the partition is skipped or only checks two names: a new enrich column
reaches every self-tier browser download (refresh fetches `/groupsyncs` on every page)
and a reader believes the dashboard does not expose a field that their network tab holds.

---

### Q3
REFUTED

Anchor: `index.html#function esc`, `index.html#function alertsCard`,
`index.html#function render` (Overview branch), `gsd/api.py#list_alerts`.

The revision prefers replacing `detail` because an absent key "may render as
`undefined`". Measured false on both axes:

1. **`esc` already collapses nullish to empty string:**

```javascript
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
```

```text
node: esc(undefined) => ""
     esc(null)      => ""
     absent key     => <div class="what"></div>   # not "undefined"
```

2. **A narrowed reader never paints `alertsCard`.** The only call site is the admin
   Overview branch; `narrowedReader()` renders `refusalCard("Overview", …)` instead.
   Measured: two `alertsCard()` occurrences (definition + admin branch); zero inside the
   self Overview block. Self still *downloads* `/api/alerts` every refresh — the leak is
   real — but the "undefined in the alert card" premise is about a code path that does
   not run for that tier.

So replacing is **not** required to save the UI. Omitting the key matches the
`/groupsyncs` convention and is safe for `esc`. A generic substitute string is optional
copy, not a defect fix. Prefer omit (or `detail: null` with the key kept) over a second
prose vocabulary for "withheld".

Admin must stay byte-for-byte — only the self branch rewrites.

Complete replacement (Codex's one-structure shape, with omit for reconcile_error):

```python
#: Alert kinds and per-kind detail policy for the self tier. One mapping so the kind
#: allowlist cannot drift from the detail policy (the SKIP_AUTH_PATHS shape, inverted).
#:
#: None  → keep the computed detail (safe at self).
#: False → omit the detail key (reconcile_error: the text can carry a bind DN; measured
#:         on the visibility seed). Existence of the failure stays — kind + subject +
#:         gsd_groupsync_reconcile_error_current on public /metrics.
#:
#: Why omit rather than a generic string: index.html#function esc already renders
#: nullish detail as "" (not "undefined"), and alertsCard is not reachable at self
#: (Overview is admin-only). Omitting matches /groupsyncs field omission. Admin alerts
#: are not projected.
SELF_ALERT_DETAILS: dict[str, str | None | bool] = {
    "auth_failed": None,
    "forbidden": None,
    "unreachable": None,
    "groupsync_crd_absent": None,
    "invalid_schedule": None,
    "sync_stopped": None,
    "overdue": None,
    "reconcile_error": False,
}

SELF_ALERT_KINDS = frozenset(SELF_ALERT_DETAILS)
```

Self-filter block inside `list_alerts` (replace the bare kind filter):

```python
        if scope == "self":
            narrowed = []
            for alert in alerts:
                policy = SELF_ALERT_DETAILS.get(alert["kind"], Ellipsis)
                if policy is Ellipsis:
                    continue
                if policy is False:
                    narrowed.append({k: v for k, v in alert.items() if k != "detail"})
                elif policy is None:
                    narrowed.append(alert)
                else:
                    narrowed.append({**alert, "detail": policy})
            alerts = narrowed
```

Carry forward the existing WHY comment on `SELF_ALERT_KINDS` (backing pages / fail-closed);
only the structure changes. Do not delete the measured dangling/config history.

Complete test:

```python
def test_reconcile_alert_omits_detail_at_self(client):
    """Closing /groupsyncs must not leave the bind DN on the alert bus."""
    mine = client.get("/api/alerts", headers=H("alice")).json()
    wide = client.get("/api/alerts", headers=H("root")).json()
    mine_error = next(a for a in mine["alerts"] if a["kind"] == "reconcile_error")
    wide_error = next(a for a in wide["alerts"] if a["kind"] == "reconcile_error")
    assert "detail" not in mine_error
    assert mine_error["subject"] == "ldap-sync"
    assert wide_error["detail"] == (
        "LDAP bind failed for cn=svc,ou=people: invalid credentials"
    )
```

Measured against current code: alice's `detail` still contains `cn=svc,ou=people`.

Consequence if the design ships a generic string *because of* the undefined fear: the
arbiter believes the UI required that string, which is false — and a future change that
"restores" a richer self Overview would still be safe with an omitted key because of
`esc`. If they ship replace anyway as copy, that is harmless; the defect is the rationale
and the inconsistency with `/groupsyncs` omission.

---

### Q4
CONFIRMED

Anchors: `gsd/state.py#compute_alerts`, `gsd/api.py#list_events`,
`charts/group-sync-dashboard/templates/monitoring.yaml`, `gsd/metrics.py` (groupsync
collectors).

Attacked every path the question names:

| path | carries bind/error text at self? | measured |
|---|---|---|
| alert `subject` | no — CR name only (`ldap-sync`) | visibility seed |
| alert `detail` | **yes — the Q3 hole** | `cn=svc,ou=people` |
| `/groupsyncs/{name}/events` `note` | no — fixed string about accumulation window | `list_events` |
| event rows | no — `synced_at, observed_at, schedule, group_count` | SQL in design, rechecked |
| PrometheusRule annotations | no `GroupSyncReconcileError` rule; config rule is a count, no message | `monitoring.yaml` |
| `/metrics` | bit only: `gsd_groupsync_reconcile_error_current` / `gsd_alerts_total{kind=…}` | scrape of seed |

After Q3's alert-detail omit (or replace), no remaining self-tier path in this set still
hands over the reconcile diagnostic text. Cluster poll `detail` on `auth_failed` is a
different string (`401 Unauthorized…`) and is intentionally self-visible.

No code change beyond Q3 for this question. Preservation test for admin detail is in Q3.

Consequence if Q3 is skipped: a narrowed reader believes `/groupsyncs` no longer exposes
the bind DN while `/api/alerts` in their network tab still does — false closure.

---

### Q5
REFUTED

Round 1 left at least four things unsettled that this revision silently drops or leaves
contradictory:

1. **SPEC policy vs UI-consumption allowlist.** Round 1 overruled the `/metrics`
   justification for *eight* fields; it did not overrule the SPEC's "FULL except two
   fields" ruling. The revision replaces that ruling with `provider_keys` alone without
   recording a SPEC reversal. The unfinished test the design cites as authority would
   fail against the revised allowlist (`name`/`state` absent).
2. **Null-vs-omit inside the field-withholding class.** Q1 correctly dropped the envelope
   by citing `/api/clusters`. That endpoint withholds by **keeping the key and setting
   `null`** (`list_clusters` / `operator_configs`). The revision omits keys instead. Bare
   list + key absence is exactly the "missing means withheld or never present?" ambiguity
   round 1 called durable debt; joining the clusters class without joining its null
   pattern leaves that unsettled.
3. **Stale false paragraph still in the design.** § "What needs NO change" still claims
   `state`, `next_expected`, `last_sync_at`, group counts, `provider_keys` are "all already
   served … by `/metrics`". Round 1 Q2 measured that false for eight fields including
   `provider_keys`. The revised allowlist section corrects this; the earlier section was
   not updated — a doc that disagrees with itself (constraint 2).
4. **Orphaned §4 "honesty test" for `/metrics` coverage.** The allowlist is now
   UI-derived; an honesty test that every allowlist justification claims `/metrics`
   coverage would either fail on `provider_keys` or force the old false justification
   back. Unsettled which test survives.

Also must be rewritten in the same commit (design §5 lists docs, not this):
`tests/test_view_scoping.py#test_cr_health_stays_full_view_because_metrics_already_publishes_it`
and the `SELF_ALERT_KINDS` comment that still says GroupSync CR health is "full-view at
both tiers".

Complete fix for (2) if the arbiter keeps a bare list — null the withheld fields rather
than drop keys (clusters precedent), admin still byte-identical when scope is `all`:

```python
        if scope == "self":
            rows = [
                {
                    **{field: cr[field] for field in SELF_TIER_GROUPSYNC_FIELDS},
                    **{field: None for field in WITHHELD_AT_SELF_GROUPSYNC_FIELDS},
                }
                for cr in rows
            ]
```

Complete test for the silent SPEC drop:

```python
def test_self_groupsync_row_keeps_metrics_public_identity(client):
    """Self may omit directory diagnostics; it may not omit what /metrics already names."""
    mine = client.get("/api/clusters/c1/groupsyncs", headers=H("alice")).json()[0]
    metrics = client.get("/metrics").text
    assert mine["name"] == "ldap-sync"
    assert f'groupsync="{mine["name"]}"' in metrics
    assert "state" in mine and "group_count" in mine and "last_sync_at" in mine
```

Against the revised `provider_keys`-only design this fails; against Q1's allowlist it passes.

Consequence: an operator reading only the "Review round 1" section believes the SPEC
exception (two fields) was implemented, while the revised design ships a different
product rule driven by one UI helper.

---

### NEW-1
REFUTED (design premise: self UI "consumes" alert detail)

Anchor: `index.html#function render`, `index.html#async function refresh`.

The design's Q2 table treats UI consumption as the derivation for `/groupsyncs`, but does
not apply the same measurement to `/api/alerts`. Measured: self fetches alerts every
refresh and never renders them (Overview refusal). The alert-detail leak is
**delivery-only** — same class as the groupsyncs network-tab argument — not a painted
card. Closing it remains mandatory; justifying the *shape* of the close by appeal to
`alertsCard` rendering is false.

No extra code beyond Q3. Test that pins the delivery leak without requiring Playwright:

```python
def test_self_refresh_payload_does_not_carry_reconcile_bind_dn(client):
    """What a self browser downloads every 60s — not what Overview paints."""
    alerts = client.get("/api/alerts", headers=H("alice")).json()["alerts"]
    syncs = client.get("/api/clusters/c1/groupsyncs", headers=H("alice")).json()
    blob = repr(alerts) + repr(syncs)
    assert "cn=svc,ou=people" not in blob
    wide_blob = repr(client.get("/api/alerts", headers=H("root")).json())
    assert "cn=svc,ou=people" in wide_blob
```

Consequence: a reviewer signs off on a generic `detail` string "for the alert card" when
no self-tier card exists — and may later reopen the DN by "improving" copy without a test
on the download path.

---

### NEW-2
FIX-INADEQUATE (design §4 / §5 test list vs `test_cr_health_stays_full_view_…`)

Anchor: `tests/test_view_scoping.py#test_cr_health_stays_full_view_because_metrics_already_publishes_it`.

Shipping `provider_keys`-only (or even SPEC-aligned omission) **must** rewrite this test's
thesis in the same commit. Today it asserts self gets a list because `/metrics` already
publishes CR identity. After any self projection, either:

- keep the theatre rule and allowlist the metrics-public fields (Q1), and change the test
  to assert those fields remain; or
- deliberately reverse the theatre rule and replace the test with one that records why
  self may see less than `/metrics`.

Leaving it green while the docstring lies is the SKIP_AUTH_PATHS shape again.

```python
def test_cr_health_self_matches_metrics_public_surface_not_directory_diagnostics(tmp_path):
    """Self keeps the unauthenticated /metrics CR surface; directory text goes."""
    c = _client(tmp_path)
    syncs = c.get("/api/clusters/c1/groupsyncs", headers=AS_VIEWER).json()
    assert syncs.status_code == 200 if False else True  # status already 200
    row = c.get("/api/clusters/c1/groupsyncs", headers=AS_VIEWER).json()[0]
    for key in ("name", "namespace", "state", "group_count", "last_sync_at", "provider_keys"):
        assert key in row
    assert "ldap_filter" not in row or row.get("ldap_filter") is None
    assert "error_message" not in row or row.get("error_message") is None
    events = c.get("/api/clusters/c1/groupsyncs/x/events", headers=AS_VIEWER).json()
    assert events["scope"] == "all"
```

(Use the null-or-absent assertion that matches the chosen clusters-class pattern.)

---

## Debt summary

| bucket | item |
|---|---|
| **DEBT-INTRODUCED** | UI-derived `frozenset({"provider_keys"})` as API policy — a list that must be widened when any new self consumer appears, sold as "no debt". |
| **DEBT-INTRODUCED** | Bare-list key omission vs `/api/clusters` null-withholding — ambiguity round 1 left open. |
| **DEBT-ACCEPTED** | Fail-closed allowlist/partition (same as `SELF_ALERT_KINDS`) — acceptable **if** the allowlist is SPEC/metrics-shaped, not `crSlot`-shaped. |
| **DEBT-AVOIDED** | Envelope / UI unwrap (Q1) — correctly dropped after `/api/clusters` measurement. |
| **DEBT-AVOIDED** | Dual `SELF_ALERT_KINDS` + separate detail set — one derived mapping kept. |

The debt of the UI-consumption allowlist is **not** worth the feature. The feature the
SPEC named is "omit two directory fields"; the revision implements a different, stricter,
UI-coupled rule and calls it the same work. Ship Q1's SPEC-aligned allowlist + Q3's omit
(or null) of alert `detail`, rewrite the stale design paragraph and
`test_cr_health_stays_full_view_…` in the same commit, preserve admin bytes.
