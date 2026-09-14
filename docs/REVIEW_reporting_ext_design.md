# Review — reporting extension, ROUND 1 (design + snippets), PR #99

Adversarial review of `docs/DESIGN_reporting_auditors_and_ns_selector.md` **before any code** — the
operator's process: round 1 on the design and its snippets, adjudicate, fold in, then cut the issues in
the settled order (each its own PR, reviewed again at implementation). 2026-09-14. Codex (gpt-5.6-sol,
xhigh, shell, `git archive` export, stdin closed) measured against the real code; Cursor (Grok 4.6 high
fast, ask mode, no shell) traced from the tree and marked runtime PLAUSIBLE. Every load-bearing claim was
re-checked here against the code before a decision — all ten held.

## Verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 report gate `list clusterrolebindings`; Usage `update`; the audit role covers one, not the other | CONFIRMED | CONFIRMED | — |
| C2 the dashboard reads with its own SA; the tier gates display only | CONFIRMED | CONFIRMED | — (Cursor's qualifier N1 folded) |
| C3 namespaces polled on the binding cadence, gated by rbac.namespaces, only name/created/phase | CONFIRMED | CONFIRMED | — |
| C4 the chart render guard is correct Helm | REFUTED | REFUTED | **Accepted** — use the SAR helpers, nil-safe, guard the no-role case |
| C5 the Group/Binding rendering is correct and safe | REFUTED | REFUTED | **Accepted** — hash the CRB name; omit `users:` |
| C6 the data-path snippets match the real shapes | REFUTED | REFUTED | **Accepted** — no `self.settings`; label keys as a param; child table in the same `_write()` |
| C7 the report param change preserves behaviour; the migration is safe | REFUTED | REFUTED | **Accepted** — `ValidationError` not `ReportError`; `MAX_NAMESPACES`; validate at the endpoint |
| C8 the selector is strict and the estate model holds | REFUTED | REFUTED | **Accepted** — cross-process boundary; per-cluster catalogue; multi-select serialises an array |

## Re-check (the ten claims, measured here)

`ValidationError` exists in `catalogue/common.py:25`, `ReportError` nowhere in `gsd/`; `MAX_NAMESPACES = 50`
(`common.py:16`), no `NS_CAP`; `RunContext` (`common.py:64-72`) has no `namespace_selector_label`;
`ClusterClient.__init__(cluster, timeout=15.0)` — no `self.settings`, `fetch_namespaces(self)` takes no
key argument (`kube.py:544,695`); `replace_namespaces` already wraps DELETE+INSERT+status in one
`with self._write()` (`store.py:1235-1236`); the three SAR helpers exist (`_helpers.tpl:279,292,305`);
`list_reports` (`server.py:153`) opens no snapshot; `KEPT_OFF` (`test_values_defaults.py:17`) is asserted
an exact set (`:83`); the report pod's `ReportSettings` reads `GSD_REPORT_*` (`reporting/config.py:90-121`);
`has_table` exists, `has_column` does not (`snapshot.py:121`). Every reviewer claim confirmed.

## The accepted corrections, by theme

### Chart (C4, C5) — the auditor template

Both reviewers rewrote `templates/rbac-auditors.yaml`. The accepted version (Cursor's, which is the
smaller and uses the chart's own helpers):

- Read the gate through `gsd.visibilitySarApiGroup` / `…Resource` / `…Verb` (nil-safe includes the
  ConfigMap already uses), never bare `.Values.visibility.adminSar` (a present-but-nil `adminSar:`
  panics; `toString` of a nil leaf is `"<nil>"`, not `""`).
- **Guard the no-role case:** `createClusterRole=false` with an empty `existingClusterRole` must FAIL
  (the Binding would name a ClusterRole the chart does not render); `createClusterRole=true` with a
  non-empty `existingClusterRole` is mutually exclusive and must FAIL.
- **The CRB `metadata.name` must be DNS-1123** but the group name is not (LDAP DNs, underscores,
  uppercase). Hash the group into the binding name (`…-ra-<sha256sum|trunc 12>`) and keep the real name
  only in `subjects[].name`. CRB names are 253-char subdomains, not 63.
- **Omit `users:` on a `createLocal` Group** — a templated `users: []` is reset on every `helm upgrade`,
  wiping any membership added by `oc adm groups add-users`; the annotation already says membership is
  managed outside the chart.
- The coverage-of-`adminSar` guard and the read-verb guard are kept, expressed against the helper values.

### Data path (C6) — capture

- `ClusterClient.fetch_namespaces(self, label_keys: list[str] | None = None)` — the keys are a
  **parameter**, threaded from `Settings.namespace_metadata_labels` through `refresh_bindings` to the
  call, never read from a non-existent `self.settings`. The mapping uses `records.append`, skips nameless
  items, and captures only the configured keys present.
- `replace_namespaces` gains the child-table DELETE+INSERT **inside the existing `with self._write()`**,
  so a report never sees a namespace with stale or half-written metadata. Both the module-level
  `CREATE TABLE cluster_namespace_label` and a new numbered `_MIGRATIONS` entry (12) ship.
- Snapshot uses `has_table` (which exists); `has_column` is neither present nor needed.

### Report (C7) — parameters and validation

- `ValidationError` (not the non-existent `ReportError`); `MAX_NAMESPACES` (not `NS_CAP`).
- **Validation timing is a correctness point:** the endpoint documents a 422 for bad params
  (`server.py:178-184`), and validation inside `build()` runs only after the 202 (it becomes a *failed
  run*). So the pure-input checks — mnemonics XOR namespaces, the count and 63-char limits — move to a
  ReportSpec `validator` hook run in `validate_params` at the endpoint (422); only the snapshot-dependent
  check (a mnemonic that expands to nothing) stays in `build()` as a failed run, which is correct because
  it needs the snapshot.
- `RunContext` gains `namespace_selector_label: str = ""`; `ReportSettings` gains it too and reads
  `GSD_REPORT_NS_SELECTOR_LABEL`; `runs.py`'s render passes it into the `RunContext`.
- The `type: "namespaces"` parser errors on `[]`; the empty advanced field must arrive omitted/`None`
  (which `validate_params` already treats as "not provided"), never as `[]`.

### GUI + catalogue + the cross-process boundary (C8, N2 — the most important)

- **The selector runs in the report pod, not the dashboard.** `GET /report/api/reports` and `build()`
  are `ReportSettings`/`GSD_REPORT_*`. So: the **dashboard** Deployment gets `GSD_NS_METADATA_LABELS`
  (the poller captures), and the **report** Deployment gets `GSD_REPORT_NS_SELECTOR_LABEL` (the catalogue
  and the expansion select). The design's §3.8 wired only the dashboard — wrong pod for the selector.
- `list_reports` is global today; it must open the snapshot and key the selector values **by cluster**
  (`namespaceSelectors: {clusterId: {label, values}}`), because the install is multi-cluster. Snapshot
  errors are swallowed (a missing first snapshot must not 500 the Reports tab — the UI hides the control
  when values are empty).
- The GUI `onchange` serialises with `el.value`, which for `<select multiple>` is the **first** option,
  not an array. A `readParamEl` helper returns an array for a multiple select; `generateReport` then
  posts a real array (which the API's `dict` params and `_string_items` already accept).
- `#report-param-namespace-access-namespaces` stays (a `test_ui.py` fixture fills it); `parse_namespaces`
  is not changed to cap (a `test_reporting_catalogue.py` case asserts it errors at 51 explicit names).

## Not asked — accepted, and folded

- **N1 (dead feature):** capture rides `if namespaces_read`, and `rbac.namespaces` defaults **false**
  (`KEPT_OFF`), so on a default install the selector is always empty. Resolution (in scope, a render
  guard, not a new tier): default `reporting.namespaceMetadata.labels: []` and
  `reporting.namespaceSelector.label: ""` — the feature is opt-in, like the namespace read it depends on.
  A `gsd.reportingGuards` helper fails the render if `namespaceMetadata.labels` is non-empty while
  `rbac.namespaces` is false, and if `namespaceSelector.label` is set but not among the captured labels.
  This also reconciles **N4** (§3's list mechanism vs §4's "single label"): the *mechanism* is a bounded
  list; the *default* is empty; enabling it is three explicit values plus the namespace grant.
- **N3:** `rbacAuditors.enabled` and any new false default are added to `KEPT_OFF` with a reason, and to
  the chart README's documented keys. There is no `values.schema.json` in the tree.
- **N5 / issue order:** bind the N1 guard to Issue A/B1, the report-pod selector env to B2 (build needs
  the label), the catalogue and GUI to B3 — §7 rewritten below.
- **N7 / N8:** swallow non-`SnapshotError` in `list_reports`; `| default list` before any `join` on the
  labels so a commented-out stanza does not panic.

## Rejected / not adopted as written

- Codex's very heavy per-field `kindIs` guard cascade in the template was **not** adopted wholesale — the
  chart's convention is the nil-safe helper plus a targeted `fail`, and Cursor's smaller version matches
  it. The type errors the cascade catches (a non-bool `enabled`, a non-list `groups`) are real, so a
  reduced set of `kindIs` guards on `enabled`, `groups`, and each entry's `name`/`createLocal` is kept.
- Neither reviewer's full `assemble`/`Built` rewrite is adopted as a design snippet; the truncation-note
  plumbing is real but is B2 implementation detail, recorded there rather than expanded in the design.

## Outcome

Six of eight claims refuted, all as defects in my design snippets (the two CONFIRMED were the as-is
facts). Every load-bearing claim re-checked against the code and confirmed. The two extensions are the
right shape — a chart-only auditor over the existing gate, and a bounded label capture into a child
table — but the snippets as first written would not compile or would violate the 422 contract, the
process boundary, and the chart's DNS-1123 and boolean-default-policy rules. All accepted corrections are
folded into the design (the snippets, §4's reconciliation, §5's tests, §7's issue order). The issues are
then cut from the corrected §7, each implemented and reviewed as its own PR — where the reviewers' full
corrected snippets (in the scratchpad review outputs) become the starting point and are re-attacked on
real code.

---

## Round 2 — the §3.9 auto-discovery content, same models

After the §3.9 enhancement (reviewer prefill; a checkable namespace multi-select) a second pass on the
same head. Both reviewers converged again; every load-bearing claim re-checked here.

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 the catalogue `discovery` payload is sound and safe | REFUTED | REFUTED | **Accepted — do not put usernames on the catalogue at all** |
| C2 the namespace multi-select preserves the wire contract | REFUTED | REFUTED | **Accepted** — new id for the select, keep the text id, never POST `[]` |
| C3 the sentinel and empty-list fallback | PLAUSIBLE | REFUTED | **Accepted** — fallback on `disc.namespaces.length`, not `nsOptions.length` |
| C4 the reviewer prefill is free-type and does not break the report | REFUTED | REFUTED | **Accepted** — seed `reportForm` so Generate posts it; trim required strings |
| C5 the report-pod boundary and per-cluster catalogue held | CONFIRMED | CONFIRMED | — |
| C6 defaults stay off | REFUTED | REFUTED | **Accepted** — §3.1/§4 stale text fixed; B4 changes reporting-enabled installs, honestly stated |

**C1 — the username dump (the biggest).** §3.9 called `snap.users(cluster_id)` on the catalogue and
sliced `[:2000]`. Re-checked: `Snapshot.users` (`snapshot.py:276`) is an unpaged join over `ocp_user`,
`group_member` and `user_binding` with `json.loads` on `providers` — it materialises the whole user
table on every Reports-tab load, and its `sqlite3.Error` is not in B3's `except (SnapshotError, OSError)`.
Decision (Cursor's, the cleaner): **the catalogue's `discovery` carries only `namespaces`** (from
`cluster_namespaces`, already simple, inside B3's existing try — no new error surface). The reviewer
`<datalist>` sources from the dashboard's own paged `/api/clusters/{id}/users` (`api.py:1153`), which the
wide-tier reader already has, not from the report catalogue. This also settles the disclosure question in
scope: the fix is "do not dump users on the catalogue", not a new tier.

**C2 — the namespace multi-select.** A `<select multiple>`'s empty selection serialises to `[]`, which
`parse_namespaces` rejects — so `readParamEl` returning `[]` must **delete** the param, never post it.
The existing `test_ui.py:4061` fills `#report-param-namespace-access-namespaces` as a **text** input, so
that id stays on the advanced text field and the discovered multi-select gets a **new** id
(`#report-ns-discovered`); the generic `field()` renderer skips `namespaces` so only one
`data-param="namespaces"` control exists. The client filter hides options (`option.hidden`), never
rebuilds `innerHTML` (which would drop a selected-but-filtered name).

**C3 — the fallback.** `nsOptions` always contains the `(cluster-scoped)` sentinel, so a
`nsOptions.length` test never falls back; the branch keys on `disc.namespaces.length`. Sentinel confirmed
`(cluster-scoped)` → `""` in `build`.

**C4 — the reviewer prefill would not post.** `generateReport` reads `view.reportForm[spec.name]`
(`index.html:1860`), not the DOM, and a painted `value=cat.viewer` never writes `reportForm` nor fires
`onchange` — so an untouched prefill sends nothing and the required field 422s. Decision: seed
`view.reportForm["access-certification"].reviewer = cat.viewer` when the key was never touched (a cleared
field stays cleared and correctly 422s); and the `str` validator trims a whitespace-only required value.
`cat.viewer` is `null` for a service-token run — the `??` handles it.

**C6 and the honest scope.** §3.1 still carried round-1's pre-correction "on-defaults" wording, and §4
claimed "none changes a default install" — but reporting defaults on, so B4's form assists (an empty
`discovery`, the reviewer prefill) do touch a reporting-enabled install. Both fixed: B4 is stated as form
assists on reporting-enabled installs that add no RBAC, tier, ticket, snapshot or gate. With C1's fix
(namespaces only, empty when the grant is off) the default-install delta is minimal and honest.

**Not asked — accepted:** the §3.2 ASCII still showed round-1's singular `namespaceSelector` and `NS_CAP`
(fixed to `namespaceSelectors[clusterId]` and `MAX_NAMESPACES`); >50 discovered selections are a 422, not
a silent truncation (a client note at 50, `parse_namespaces` unchanged); the mnemonic control cannot
"pre-check" namespaces (the catalogue has no value→namespace map) — it is an independent alternative that
XOR-clears `namespaces`; form state is keyed by report, so a namespace picked on one cluster must be
dropped on a cluster switch.

**Rejected:** Codex's dedicated `discovery_user_names` snapshot method (it still puts usernames on the
catalogue — Cursor's "use the dashboard Users API" avoids the disclosure and the new query entirely);
Codex's `renderedReportParams()` reading the DOM (the seed-`reportForm` approach matches the existing
Generate path and is smaller).

**Outcome of round 2.** Five of six claims refuted, all as defects in the §3.9 additions; C5 (the round-1
pod split and per-cluster catalogue) held. All corrections folded into §3.9 and the stale §3.1/§3.2/§4
text; issue #104 updated. The auto-discovery is the right B4 — the snippets as first written would have
422'd the main path, broken the one UI test that generates a report, and queried the user table on a
default install.
