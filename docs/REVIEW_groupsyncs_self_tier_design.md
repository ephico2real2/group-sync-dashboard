# Review: `/groupsyncs` self-tier design

Measured against the current worktree before implementation.

```text
cd local-development
.venv/bin/python - <<'PY'
# Build tests/test_visibility.py's seeded app and print reconcile_error alerts for alice/root.
PY

alice self
[{'cluster': 'c1', 'kind': 'reconcile_error', 'subject': 'ldap-sync',
  'detail': 'LDAP bind failed for cn=svc,ou=people: invalid credentials',
  'severity': 'critical'}]
root all
[{'cluster': 'c1', 'kind': 'reconcile_error', 'subject': 'ldap-sync',
  'detail': 'LDAP bind failed for cn=svc,ou=people: invalid credentials',
  'severity': 'critical'}]
```

```text
.venv/bin/python - <<'PY'
# Print the seeded wide row's keys and every gsd_groupsync_* sample from /metrics.
PY

wide_keys= ['error_at', 'error_generation', 'error_is_current', 'error_message',
 'generation', 'group_count', 'interval_seconds', 'last_sync_at', 'ldap_filter',
 'name', 'namespace', 'next_expected', 'observed_at', 'provider_keys', 'schedule',
 'schedule_valid', 'state']
groupsync_metric_names= ['gsd_groupsync_groups_total',
 'gsd_groupsync_last_sync_timestamp_seconds',
 'gsd_groupsync_reconcile_error_current', 'gsd_groupsync_state']
```

```text
.venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py

1 failed, 1214 passed, 4 deselected, 149 errors in 149.91s
```

That is not the stated `1363 passed / 4 deselected` baseline in this sandbox. Chromium cannot
start here (`MachPortRendezvousServer ... Permission denied`) and the UI server cannot bind a
loopback port. The one executable failure is also real: the untracked design document's three
line-number citations fail `test_no_citation_uses_a_line_number`. The non-browser tests otherwise
reached 1214 passes.

A disposable `/tmp` application of the Q1-Q4 blocks below produced:

```text
.venv/bin/python -m pytest \
  tests/test_visibility.py::TestTwoTiersPerEndpoint::test_groupsync_policy_is_exhaustive_and_admin_diagnostic_is_unchanged \
  tests/test_visibility.py::TestTwoTiersPerEndpoint::test_reconcile_alert_withholds_only_the_self_tier_diagnostic -q

2 passed, 1 warning in 1.30s

.venv/bin/python -m pytest tests/test_visibility.py tests/test_view_scoping.py -q

1 failed, 65 passed, 1 warning in 8.29s
```

The sole failure was the existing assertion that the response is a list. The candidate browser
script also parsed successfully under Node.

### Q1
CONFIRMED

Anchor: `gsd/api.py#list_groupsyncs`.

The object shape is justified. A bare list cannot state whether omitted keys are withheld or did
not exist, and keeping one exceptional collection shape is durable ambiguity. This is a deliberate,
loud breaking change; update the documented callers in the same commit. It does not narrow the
administrator row: **the administrator must retain `error_message` in full, byte-for-byte.** Without
the wrapper, a narrowed reader can falsely believe a missing filter means the CR has no LDAP filter.

Complete replacement route (apply with Q2's constants):

```python
    @app.get("/api/clusters/{cluster_id}/groupsyncs")
    def list_groupsyncs(request: Request, cluster_id: str) -> dict:
        """GroupSync CRs on one cluster, with their derived state and declared scope.

        State is derived per request: storing it would make it wrong as soon as the clock
        crosses a schedule boundary. The all tier receives the complete row, including the
        operator's diagnostic text unchanged. The self tier is projected from an allowlist,
        so a newly added store/enrichment field is withheld until it is explicitly ruled on.

        This response is an object because omission now varies by tier. `scope` distinguishes
        a withheld field from a field the CR never supplied; clients must never infer that
        distinction from key absence.
        """
        require_cluster(cluster_id)
        viewer, scope = viewer_scope(request)
        now = datetime.now(UTC)
        rows = [enrich(cr, now) for cr in store.groupsyncs(cluster_id)]
        if scope == "self":
            rows = [
                {field: cr[field] for field in SELF_TIER_GROUPSYNC_FIELDS}
                for cr in rows
            ]
        return {
            "cluster": cluster_id,
            "scope": scope,
            "viewer": viewer,
            "groupsyncs": rows,
        }
```

Complete failing-before/passing-after test for `tests/test_visibility.py#TestTwoTiersPerEndpoint`:

```python
    def test_groupsync_collection_declares_scope_and_preserves_admin_text(self, client):
        mine = client.get("/api/clusters/c1/groupsyncs", headers=H("alice")).json()
        wide = client.get("/api/clusters/c1/groupsyncs", headers=H("root")).json()

        assert mine["cluster"] == "c1"
        assert mine["scope"] == "self" and mine["viewer"] == "alice"
        assert wide["scope"] == "all" and wide["viewer"] == "root"
        assert wide["groupsyncs"][0]["error_message"] == (
            "LDAP bind failed for cn=svc,ou=people: invalid credentials"
        )
```

### Q2
FIX-INADEQUATE

Anchors: `gsd/metrics.py#DashboardCollector.collect`, `gsd/api.py#enrich`, and
`gsd/store.py#Store.groupsyncs`.

The allowlist direction passes the stale-denylist standard: projection defaults new fields to
withheld, and an exhaustive partition test turns an unclassified addition into a red build. It does
not merely move `SKIP_AUTH_PATHS` debt. The proposed membership and justification are wrong,
however. Metrics expose only name/namespace, state, last sync, group count, and the current-error
bit. They do not expose schedule, generation, observed time, provider keys, error time, or derived
schedule fields. The proposed partition also omits the existing `error_generation`, so its own test
would fail today. A narrowed reader would falsely believe all delivered fields were already public
on `/metrics`.

Schedule and its derivations may remain only because the unchanged events response already delivers
schedule at this tier. Diagnostic metadata, poll metadata, generations, and provider inventory have
no measured public analogue and should be withheld.

Complete replacement policy block:

```python
#: Fields a self-tier reader may receive for a GroupSync CR. New row/enrichment fields are
#: withheld by construction until deliberately classified here and in the companion withheld
#: set; the partition test makes an unclassified addition fail instead of leak.
#:
#: Identity, state, last sync, group count and the current-error bit are already published on
#: /metrics. Schedule is already returned by the unchanged events endpoint; its derived fields
#: reveal nothing beyond it. Diagnostic/configuration and per-poll metadata remain administrator-
#: only. In particular, the administrator's error_message is never projected or rewritten.
SELF_TIER_GROUPSYNC_FIELDS = (
    "name",
    "namespace",
    "schedule",
    "schedule_valid",
    "last_sync_at",
    "group_count",
    "state",
    "next_expected",
    "interval_seconds",
    "error_is_current",
)

WITHHELD_AT_SELF_GROUPSYNC_FIELDS = frozenset({
    "ldap_filter",
    "error_message",
    "error_at",
    "error_generation",
    "generation",
    "observed_at",
    "provider_keys",
})
```

Complete failing-before/passing-after test (including imports):

```python
from gsd.api import (
    SELF_TIER_GROUPSYNC_FIELDS,
    WITHHELD_AT_SELF_GROUPSYNC_FIELDS,
)


def test_groupsync_policy_is_exhaustive_and_admin_diagnostic_is_unchanged(client):
    """A field addition must be classified, self defaults closed, and admin stays whole."""
    mine = client.get("/api/clusters/c1/groupsyncs", headers=H("alice")).json()
    wide = client.get("/api/clusters/c1/groupsyncs", headers=H("root")).json()
    mine_row = mine["groupsyncs"][0]
    wide_row = wide["groupsyncs"][0]

    assert set(wide_row) == (
        set(SELF_TIER_GROUPSYNC_FIELDS) | WITHHELD_AT_SELF_GROUPSYNC_FIELDS
    )
    assert tuple(mine_row) == SELF_TIER_GROUPSYNC_FIELDS
    assert wide_row["error_message"] == (
        "LDAP bind failed for cn=svc,ou=people: invalid credentials"
    )
    assert not (set(mine_row) & WITHHELD_AT_SELF_GROUPSYNC_FIELDS)
```

### Q3
REFUTED

Anchors: `gsd/api.py#list_alerts`, `gsd/api.py#SELF_ALERT_KINDS`, and
`gsd/state.py#compute_alerts`.

Measured: `/api/alerts` gives `alice` the complete DN-bearing reconcile text. `compute_alerts`
copies `error_message` into `detail`, and the self-kind allowlist retains `reconcile_error`. Closing
`/groupsyncs` alone leaves the busier door open. A narrowed reader would falsely believe the alert
diagnostic contains no directory/service identity the CR endpoint withholds.

Keep the signal and sanitize only its self-tier detail; removing the kind would hide a public
current-error fact. Admin alerts and `/groupsyncs` remain unchanged and full.

Complete replacement allowlist block:

```python
# Alert kinds and detail policy for the self tier. This mapping is the one allowlist: a kind added
# elsewhere is hidden until both its backing page and its payload are ruled on. None means its
# existing detail is safe; a string is the complete replacement detail at self.
#
# Poll failures are already shown on cluster cards. GroupSync identity/state and the existence of
# a current reconcile error are public on /metrics. The reconcile diagnostic is different: it can
# contain a bind DN, so self keeps the actionable signal but not the operator-only text.
#
# Group/person/RBAC/config kinds remain absent because their backing pages are scoped or admin-only:
# empty_group, unattributed, stale_group, direct_user_binding, dangling_binding, and
# config_reconcile_error. Adding any of them here must be an explicit policy decision.
SELF_ALERT_DETAILS: dict[str, str | None] = {
    "auth_failed": None,
    "forbidden": None,
    "unreachable": None,
    "groupsync_crd_absent": None,
    "invalid_schedule": None,
    "sync_stopped": None,
    "overdue": None,
    "reconcile_error": "reconcile failed; diagnostic text is withheld in the self view",
}

SELF_ALERT_KINDS = frozenset(SELF_ALERT_DETAILS)
```

Complete replacement self-filter block inside `list_alerts`:

```python
        if scope == "self":
            narrowed = []
            for alert in alerts:
                if alert["kind"] not in SELF_ALERT_DETAILS:
                    continue
                detail = SELF_ALERT_DETAILS[alert["kind"]]
                narrowed.append(alert if detail is None else {**alert, "detail": detail})
            alerts = narrowed
```

Complete failing-before/passing-after test:

```python
def test_reconcile_alert_withholds_only_the_self_tier_diagnostic(client):
    """The alert bus must not reopen the diagnostic closed on /groupsyncs."""
    mine = client.get("/api/alerts", headers=H("alice")).json()
    wide = client.get("/api/alerts", headers=H("root")).json()
    mine_error = next(a for a in mine["alerts"] if a["kind"] == "reconcile_error")
    wide_error = next(a for a in wide["alerts"] if a["kind"] == "reconcile_error")

    assert mine_error["detail"] == (
        "reconcile failed; diagnostic text is withheld in the self view"
    )
    assert "cn=svc,ou=people" not in mine_error["detail"]
    assert wide_error["detail"] == (
        "LDAP bind failed for cn=svc,ou=people: invalid credentials"
    )
```

### Q4
REFUTED

Anchors: `gsd/poller.py#provider_keys_for` and `index.html#function crSlot`.

`provider_keys` is not a harmless CR identity field. It is the observed Group label value and
includes the arbitrary provider name. Measured with the real function,
`provider_names=("svc-ou-people",)` plus label `ldap-sync_svc-ou-people` returns that value
unchanged. It cannot contain literal comma/equal DN syntax as a Kubernetes label value, but it can
encode directory/provider topology, is absent from `/metrics`, and inventories providers belonging
to groups the narrowed reader cannot list with `oc`. Such a reader would falsely believe the
dashboard has not exposed provider identifiers outside their own group rows.

Withhold the all-CR `provider_keys` inventory via Q2. Preserve colour grouping by hashing the
`sync_provider` already present on each group row the reader is allowed to receive.

Complete replacement function:

```javascript
function crSlot(provider) {
  if (!provider) return null;
  // The provider label already arrives on each group row the reader is allowed to see. Hash
  // that value instead of downloading every CR's provider labels merely to allocate colours.
  // FNV-1a is deterministic across filtering, polling and clients; collisions affect colour
  // decoration only, while the provider text remains the accessible identity.
  let hash = 0x811c9dc5;
  for (let i = 0; i < provider.length; i += 1) {
    hash ^= provider.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0) % 8 + 1;
}
```

Complete failing-before/passing-after UI test for `tests/test_ui.py`:

```python
def test_provider_colour_does_not_require_the_all_cr_provider_inventory(dash):
    """A self-visible group keeps a stable source colour without hidden CR provider rows."""
    provider = "ldap-sync_svc-ou-people"
    with_inventory = dash.evaluate(
        """provider => {
          data.groupsyncs = [{provider_keys: [provider]}];
          return crSlot(provider);
        }""",
        provider,
    )
    without_inventory = dash.evaluate(
        """provider => {
          data.groupsyncs = [];
          return crSlot(provider);
        }""",
        provider,
    )
    assert with_inventory == without_inventory
    assert 1 <= without_inventory <= 8
```

### Q5
FIX-INADEQUATE

Anchor: `index.html#async function refresh`.

The object/list mismatch itself fails loudly (`flatMap`, `map`, and `find` are not functions on the
object). Do not teach all four render sites the wire wrapper. Unwrap once at the transport boundary;
the renderers retain their existing honest `null` versus `[]` states. The silent regression is Q4:
once the corrected allowlist withholds `provider_keys`, the old `crSlot` quietly removes every
source dot. Without both changes, a narrowed reader can falsely read missing source decoration as an
unmapped provider rather than withheld inventory.

Complete replacement assignment block in `refresh`:

```javascript
    if (view.cluster) {
      // Unwrap once at the transport boundary. Renderers keep their honest null/list states,
      // while API clients still receive the collection's explicit scope and viewer.
      data.groupsyncs = got.groupsyncs.groupsyncs;
      data.events = view.groupsync ? got.events : null;
    }
```

Complete failing-before/passing-after browser contract test:

```python
def test_groupsync_collection_object_is_unwrapped_at_the_transport_boundary(page, server):
    """Exercise the new wire shape against the browser before the backend route changes."""
    errors: list[str] = []
    page.on("pageerror", lambda error: errors.append(str(error)))

    def wrap_groupsyncs(route):
        response = route.fetch()
        rows = response.json()
        route.fulfill(
            status=response.status,
            json={
                "cluster": "crc-local",
                "scope": "all",
                "viewer": None,
                "groupsyncs": rows,
            },
        )

    page.route("**/api/clusters/*/groupsyncs", wrap_groupsyncs)
    page.goto(server)
    page.wait_for_selector("h2:text-is('GroupSync CRs')")

    assert not errors
    assert page.locator("tr[data-cr='ldap-groupsync']").count() == 1
```

### NEW-1
FIX-INADEQUATE

Anchor: `tests/test_docs_citations.py#test_no_citation_uses_a_line_number`.

The design document itself makes the requested baseline fail because it uses three forbidden line
citations. If committed unchanged, a future operator can follow a moved line and falsely believe an
unrelated block enforces the visibility rule. Replace the complete three cited spans as follows:

```markdown
`docs/SPEC_per_user_visibility.md#The decision rule, applied uniformly`
`static/index.html#async function refresh`
`index.html#function crSlot`
```

The complete existing failing-before/passing-after test is already correct and needs no new logic:

```python
def test_no_citation_uses_a_line_number():
    """Line numbers rot when code above them moves; named anchors move with the subject."""
    offenders = [
        f"{md.relative_to(REPO)}:{n} -> {match.group(0)}"
        for md in _markdown()
        for n, line in enumerate(md.read_text().split("\n"), start=1)
        for match in [LINE_NUMBER_CITATION.search(line)]
        if match
    ]
    assert not offenders, (
        "these citations use a line number; cite a name instead so the reference moves with "
        "the code:\n  " + "\n  ".join(offenders)
    )
```
