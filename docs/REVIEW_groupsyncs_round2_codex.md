# Round 2 review: `/groupsyncs` self tier

Measured against the revised, unimplemented design.

```text
cd local-development
.venv/bin/python -m pytest tests/test_docs_citations.py tests/test_docs_diagrams.py -q

353 passed in 9.19s
```

After this review artifact added its own checked anchors (and the parallel round-2 artifact became
visible in the shared worktree), the final command reported `385 passed in 8.86s`.

```text
.venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py

1239 passed, 4 deselected, 1 warning, 149 errors in 172.21s
```

All 149 errors are environmental `tests/test_ui.py` setup errors: Chromium cannot register its
Mach rendezvous port (`Permission denied (1100)`), and the UI server cannot bind `127.0.0.1`
(`PermissionError: [Errno 1]`). No executable test failed. This sandbox therefore cannot reproduce
the stated `1363 passed / 4 deselected` browser-capable baseline.

The absent-alert-detail case was executed with the production `esc` and `alertsCard` functions
loaded from `index.html` under Node, because Chromium cannot start here:

```text
node <<'JS'
// Read index.html, evaluate its complete esc() and alertsCard(), and render an alert with no detail.
JS

detail_text=""
contains_undefined=false
```

### Q1
FIX-INADEQUATE

Anchor: `local-development/gsd/api.py#list_groupsyncs`.

No non-UI repository code calls the HTTP endpoint; the only runtime client is `refresh`. That does
not make UI reachability the endpoint's contract. `local-development/API.md#GroupSync CRs`, the
served OpenAPI document, and the visibility requirements/spec all define this as GroupSync
**health**, with only `ldap_filter` and `error_message` withheld at self. A list of anonymous
`{"provider_keys": [...]}` rows is not GroupSync health and cannot even identify which CR owns a row.

The sharp objection holds: deriving the API allowlist from today's self-tier UI consumer relocates
the debt. A new self-tier API/UI consumer must know this hidden coupling and widen the list, while an
existing external caller silently loses fourteen documented fields. That caller would falsely
believe a CR has no name, state, timestamps, schedule, or current-error bit when the server withheld
them solely because today's browser does not paint them. Explicitly classifying a genuinely new API
field is ordinary contract evolution; making each consumer reverse-engineer a UI-derived projection
is the hidden obligation.

Keep the fail-closed allowlist, but derive it from the published self-tier **API representation**.
This keeps every current field except the two fields the spec rules sensitive, keeps the bare list,
and leaves administrator rows untouched. Complete replacement policy, projector, and route:

```python
#: The public GroupSync-health representation. This is an API contract, not a census of fields the
#: current browser happens to paint. A new storage/enrichment field is not published until it is
#: classified here; `_project_groupsyncs_for_self` makes an unclassified production key loud.
#:
#: ldap_filter and error_message are the only current fields withheld: both can carry directory
#: structure or a bind DN. The administrator branch returns the original enriched dictionaries,
#: so the operator's diagnostic remains byte-for-byte unchanged.
SELF_TIER_GROUPSYNC_FIELDS = (
    "name",
    "namespace",
    "schedule",
    "last_sync_at",
    "generation",
    "observed_at",
    "error_at",
    "error_generation",
    "group_count",
    "provider_keys",
    "state",
    "next_expected",
    "interval_seconds",
    "schedule_valid",
    "error_is_current",
)

WITHHELD_AT_SELF_GROUPSYNC_FIELDS = frozenset({"ldap_filter", "error_message"})
GROUPSYNC_API_FIELDS = (
    frozenset(SELF_TIER_GROUPSYNC_FIELDS) | WITHHELD_AT_SELF_GROUPSYNC_FIELDS
)


def _project_groupsyncs_for_self(rows: list[dict]) -> list[dict]:
    """Return the declared self representation, refusing an unclassified runtime shape."""
    projected = []
    for row in rows:
        actual = set(row)
        if actual != GROUPSYNC_API_FIELDS:
            raise RuntimeError(
                "GroupSync self-tier policy does not classify the runtime shape: "
                f"unexpected={sorted(actual - GROUPSYNC_API_FIELDS)!r}, "
                f"missing={sorted(GROUPSYNC_API_FIELDS - actual)!r}"
            )
        projected.append({field: row[field] for field in SELF_TIER_GROUPSYNC_FIELDS})
    return projected


    @app.get("/api/clusters/{cluster_id}/groupsyncs")
    def list_groupsyncs(request: Request, cluster_id: str) -> list[dict]:
        """GroupSync CR health, with directory diagnostics withheld only at self.

        State is computed per request because storing it would make it stale as soon as a
        schedule boundary passes. The all tier receives each enriched row unchanged. The self
        tier receives the documented health representation through a fail-closed projector.
        """
        require_cluster(cluster_id)
        _, scope = viewer_scope(request)
        now = datetime.now(UTC)
        rows = [enrich(cr, now) for cr in store.groupsyncs(cluster_id)]
        return rows if scope == "all" else _project_groupsyncs_for_self(rows)
```

Complete failing-before/passing-after test for
`local-development/tests/test_visibility.py#TestTwoTiersPerEndpoint`:

```python
    def test_groupsync_self_contract_withholds_only_directory_diagnostics(self, client):
        mine = client.get("/api/clusters/c1/groupsyncs", headers=H("alice")).json()[0]
        wide = client.get("/api/clusters/c1/groupsyncs", headers=H("root")).json()[0]

        assert set(mine) == {
            "name", "namespace", "schedule", "last_sync_at", "generation",
            "observed_at", "error_at", "error_generation", "group_count",
            "provider_keys", "state", "next_expected", "interval_seconds",
            "schedule_valid", "error_is_current",
        }
        assert mine["name"] == "ldap-sync"
        assert mine["state"] in {"ok", "late", "overdue", "unknown"}
        assert mine["provider_keys"] == ["ldap-sync_ldap"]
        assert "ldap_filter" not in mine and "error_message" not in mine

        assert wide["ldap_filter"] == "(&(objectClass=groupOfNames)(cn=app-*))"
        assert wide["error_message"] == (
            "LDAP bind failed for cn=svc,ou=people: invalid credentials"
        )
```

### Q2
FIX-INADEQUATE

Anchors: `local-development/gsd/store.py#Store._groupsyncs` and
`local-development/gsd/api.py#enrich`.

The proposed fixture partition catches today's shape: `_groupsyncs` explicitly selects every key,
including nulls, and `enrich` unconditionally adds every derived key. It does **not** prove the
stated invariant for a key that appears only with production data or from another `StoreLike`
implementation. Because `enrich` starts with `{**cr}`, such a key reaches the wide fixture only if
that fixture happens to produce it. The allowlist prevents disclosure, but the promised red build
does not happen; the narrowed caller silently receives omission and falsely believes the production
object lacks the new field.

The Q1 projector is the required production block: it validates the runtime key set before self
projection, while the administrator branch bypasses it and retains every value. Its complete
field-universe block is:

```python
SELF_TIER_GROUPSYNC_FIELDS = (
    "name", "namespace", "schedule", "last_sync_at", "generation", "observed_at",
    "error_at", "error_generation", "group_count", "provider_keys", "state",
    "next_expected", "interval_seconds", "schedule_valid", "error_is_current",
)
WITHHELD_AT_SELF_GROUPSYNC_FIELDS = frozenset({"ldap_filter", "error_message"})
GROUPSYNC_API_FIELDS = (
    frozenset(SELF_TIER_GROUPSYNC_FIELDS) | WITHHELD_AT_SELF_GROUPSYNC_FIELDS
)


def _project_groupsyncs_for_self(rows: list[dict]) -> list[dict]:
    """Fail closed and loud when production returns a field the policy did not classify."""
    projected = []
    for row in rows:
        actual = set(row)
        unexpected = actual - GROUPSYNC_API_FIELDS
        missing = GROUPSYNC_API_FIELDS - actual
        if unexpected or missing:
            raise RuntimeError(
                "GroupSync self-tier policy does not classify the runtime shape: "
                f"unexpected={sorted(unexpected)!r}, missing={sorted(missing)!r}"
            )
        projected.append({field: row[field] for field in SELF_TIER_GROUPSYNC_FIELDS})
    return projected
```

Complete failing-before/passing-after test for
`local-development/tests/test_visibility.py#TestTwoTiersPerEndpoint`:

```python
def test_a_production_only_groupsync_field_fails_loud_at_self(client, monkeypatch):
    """Do not let a fixture-only partition claim to classify every production key."""
    original = Store.groupsyncs

    def groupsyncs_with_future_field(self, cluster_id):
        return [
            row | {"future_secret": "present only for a production CR variant"}
            for row in original(self, cluster_id)
        ]

    monkeypatch.setattr(Store, "groupsyncs", groupsyncs_with_future_field)

    wide = client.get("/api/clusters/c1/groupsyncs", headers=H("root")).json()
    assert wide[0]["future_secret"] == "present only for a production CR variant"

    with pytest.raises(RuntimeError, match=r"unexpected=\['future_secret'\]"):
        client.get("/api/clusters/c1/groupsyncs", headers=H("alice"))
```

### Q3
CONFIRMED

Anchors: `local-development/gsd/static/index.html#function alertsCard` and
`local-development/gsd/static/index.html#function esc`.

An absent `detail` does **not** render `undefined`: `esc(undefined)` returns `""`. It produces an
empty `.what` column. That is still worse than the generic string because `Alert.detail` is a
required string and the blank row tells the narrowed reader no reason exists, when the truth is that
the reason is deliberately withheld. Replacing the value preserves the alert schema and explains
the omission.

The administrator path must remain full. The following complete block copies and replaces only a
self-tier `reconcile_error`; the all tier never calls it and retains the original bind-DN text
byte-for-byte:

```python
# Alert-kind admission and self-tier detail policy are one structure so they cannot drift. None
# preserves a detail already available on the kind's self-visible backing page; a string replaces
# operator-only diagnostic text while preserving the actionable signal.
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


def _alerts_for_self(alerts: list[dict]) -> list[dict]:
    """Apply admission and detail policy together; new kinds default to withheld."""
    narrowed = []
    for alert in alerts:
        if alert["kind"] not in SELF_ALERT_DETAILS:
            continue
        replacement = SELF_ALERT_DETAILS[alert["kind"]]
        narrowed.append(alert if replacement is None else {**alert, "detail": replacement})
    return narrowed
```

Complete replacement in `local-development/gsd/api.py#list_alerts`:

```python
        if scope == "self":
            alerts = _alerts_for_self(alerts)
```

Complete failing-before/passing-after test for
`local-development/tests/test_visibility.py#TestTwoTiersPerEndpoint`:

```python
def test_reconcile_alert_replaces_only_the_self_detail(client):
    mine = client.get("/api/alerts", headers=H("alice")).json()["alerts"]
    wide = client.get("/api/alerts", headers=H("root")).json()["alerts"]
    mine_error = next(a for a in mine if a["kind"] == "reconcile_error")
    wide_error = next(a for a in wide if a["kind"] == "reconcile_error")

    assert mine_error["detail"] == (
        "reconcile failed; diagnostic text is withheld in the self view"
    )
    assert "cn=svc,ou=people" not in mine_error["detail"]
    assert wide_error["detail"] == (
        "LDAP bind failed for cn=svc,ou=people: invalid credentials"
    )
```

### Q4
CONFIRMED

Anchors: `local-development/gsd/state.py#compute_alerts`,
`local-development/gsd/api.py#list_events`,
`local-development/gsd/static/index.html#function alertsCard`, and
`charts/group-sync-dashboard/templates/monitoring.yaml#GroupSyncOverdue`.

After Q3's replacement, no second GroupSync reconcile-error path remains. Measured:

- `subject` is the CR name (`ldap-sync`), already exposed by the per-CR metrics;
- the alert row has no tooltip and renders only `x.detail`;
- the events payload contains timestamps, schedule, group count, and a static accumulation note;
- PrometheusRule annotations use metric labels/times and never receive `error_message`.

Poll-failure kinds retain their detail, but that is the same cluster-poll message intentionally
served to the self tier as `/api/clusters[].error`; it is not the GroupSync reconcile diagnostic or
an alternate path around this fix. Otherwise a narrowed reader could falsely believe the bind DN was
withheld while reading it from a tooltip, timeline note, or rule annotation.

No additional production block beyond the complete `_alerts_for_self` function in Q3 is required.
The complete regression test is:

```python
def test_reconcile_diagnostic_has_no_second_self_tier_path(client):
    import json
    from pathlib import Path

    secret = "LDAP bind failed for cn=svc,ou=people: invalid credentials"
    alerts = client.get("/api/alerts", headers=H("alice")).json()["alerts"]
    reconcile = next(a for a in alerts if a["kind"] == "reconcile_error")
    syncs = client.get("/api/clusters/c1/groupsyncs", headers=H("alice")).json()
    events = client.get(
        "/api/clusters/c1/groupsyncs/ldap-sync/events", headers=H("alice")
    ).json()

    assert reconcile["subject"] == "ldap-sync"
    assert secret not in json.dumps(alerts)
    assert secret not in json.dumps(syncs)
    assert secret not in json.dumps(events)

    repo = Path(__file__).resolve().parents[2]
    html = (repo / "local-development/gsd/static/index.html").read_text()
    alert_renderer = html[
        html.index("function alertsCard("):html.index("function groupsyncTable(")
    ]
    rules = (
        repo / "charts/group-sync-dashboard/templates/monitoring.yaml"
    ).read_text()
    assert "x.detail" in alert_renderer and "title=" not in alert_renderer
    assert "error_message" not in rules

    wide = client.get("/api/alerts", headers=H("root")).json()["alerts"]
    wide_error = next(a for a in wide if a["kind"] == "reconcile_error")
    assert wide_error["detail"] == secret
```

### Q5
CONFIRMED

Anchor: `local-development/tests/test_visibility.py#TestAdminSeesExactlyToday`.

Nothing else from round 1 was silently dropped. Bare-list transport, `provider_keys`, no UI unwrap,
unchanged events, the single derived alert-policy structure, administrator preservation, and the
documentation updates are all accounted for. Q1 and Q2 above are new round-2 defects in the revised
rationale/test guarantee, not omitted round-1 decisions.

The false operator belief this closure test prevents is that “admin unchanged” means only the keys
survived while the diagnostic value was sanitized. No additional production block is warranted;
Q1's route returns the original admin row and Q3's filter runs only at self. Complete
failing-before/passing-after closure test:

```python
def test_round_two_closure_keeps_transport_events_and_admin_diagnostics(client):
    mine = client.get("/api/clusters/c1/groupsyncs", headers=H("alice"))
    wide = client.get("/api/clusters/c1/groupsyncs", headers=H("root"))
    events = client.get(
        "/api/clusters/c1/groupsyncs/ldap-sync/events", headers=H("alice")
    ).json()
    mine_alerts = client.get("/api/alerts", headers=H("alice")).json()["alerts"]
    wide_alerts = client.get("/api/alerts", headers=H("root")).json()["alerts"]

    assert isinstance(mine.json(), list) and isinstance(wide.json(), list)
    assert mine.json()[0]["provider_keys"] == ["ldap-sync_ldap"]
    assert "ldap_filter" not in mine.json()[0] and "error_message" not in mine.json()[0]
    assert events["scope"] == "all"
    assert events["note"] == (
        "accumulated from polling; covers only the period since this dashboard started"
    )

    mine_error = next(a for a in mine_alerts if a["kind"] == "reconcile_error")
    wide_error = next(a for a in wide_alerts if a["kind"] == "reconcile_error")
    assert mine_error["detail"] == (
        "reconcile failed; diagnostic text is withheld in the self view"
    )
    assert wide.json()[0]["error_message"] == wide_error["detail"] == (
        "LDAP bind failed for cn=svc,ou=people: invalid credentials"
    )
```

### NEW-1
CONFIRMED

Anchor: `local-development/tests/test_docs_citations.py#test_no_citation_uses_a_line_number`.

The revised design has no line-number citation, and the combined citation/diagram suite passes all
353 tests. Without that guard, an operator could follow a moved line and falsely believe unrelated
code enforces the visibility rule. No production change is required. The complete existing test is:

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
