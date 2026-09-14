# Reporting extension — auditor groups and namespace-mnemonic selection (design + technical spec)

**Status: proposed (design round 1).** A feature request that **extends** the existing reporting and
access-control design; it is not a new module. It reads on top of, and defers to, two maintained
records:

- `docs/DESIGN_reporting_service.md` — the two-pod report service, the ticket, the snapshot, the
  catalogue. Unchanged by this feature except where §3 and §4 below say so.
- `docs/ACCESS_CONTROL.md` — the tier model (self vs wide), the admin SubjectAccessReview gate, the
  stricter Usage gate. This feature adds a *supported way to put a chosen group over the existing
  gate* and *a stricter way to choose namespaces*; it changes no tier semantics.

The operator's ask, in their words: create the auditor group as part of the chart (local or matched to
an LDAP-synced group), bind it to a **least-privilege read-only** ClusterRole (not `cluster-reader`)
that lets a non-developer review users, groups and bindings both in OpenShift directly and in the
dashboard and run reports; and let a report select namespaces by the estate's own grouping label
(`company.net/mnemonic`) rather than by free-typed names, defaulting the label in Helm and offering the
values in the GUI.

Two independent extensions, decomposed into ordered issues in §7. Every code block below is the full
proposed change, with its file and where it goes, for the reviewers to attack in round 1.

---

## 1. As-is — how reporting is integrated today (measured 2026-09-14)

Application 0.19.0, chart 0.21.0 on the reference cluster. Nothing here is new; it is the ground the
extension stands on.

```
                        ┌────────────────────────── Pod: dashboard ──────────────────────────┐
   Browser              │  oauth-proxy :8443 (OpenShift login)                                │
   (wide-tier  ── TLS ──▶    -upstream=http://127.0.0.1:8080/           ── /api,/static,/ ───▶ dashboard app :8080
    reader)             │    -upstream=https://<fullname>-report.<ns>.svc:8443/report/         │   • GET /api/report/ticket  (require_admin_tier → HMAC ticket, 300s)
        │               │                                     │                                │   • poller: VACUUM INTO snapshot every 300s (leader)
        │               └─────────────────────────────────────┼────────────────────────────────┘   • poller: GET /report/api/usage every poll (Bearer token)
        │ session cookie + X-GSD-Report-Ticket (custom header)  │ /report/*  (X-Forwarded-User stamped)
        ▼                                                       ▼
   Reports tab                                    ┌──────────── Pod: report service ───────────┐
   POST /report/api/runs {report,cluster,params} │  gsd.reporting.server :8443 (TLS, no RBAC)  │
   GET  /report/api/runs, /runs/{id}, /artifact   │  • verifies ticket sig, exp, tier, viewer   │
                                                  │  • reads NEWEST read-only snapshot copy      │
                                                  │  • builds report → seals sha256 → PDF/A+HTML │
                                                  └──────────────────┬──────────────────────────┘
   PVC -data (RWX): /data/gsd.db (dashboard RW) ─── VACUUM INTO ────▶ /data/report/gsd-*.db (report RO)
   PVC -report (RWO): /artifacts/<run-id>/  ◀── the report writes the artefact, the browser downloads it
   Secret -report-token: HMAC key, mounted in both pods (ticket sign/verify, usage-pull auth)
```

**Authorization, as-is.** Running a report requires the **wide tier**, decided by one
SubjectAccessReview the dashboard runs as its own ServiceAccount: `list clusterrolebindings`
(`visibility.adminSar`, default `{apiGroup: rbac.authorization.k8s.io, resource: clusterrolebindings,
verb: list}`). The Usage tab has a stricter, separate gate: `update clusterrolebindings` (a write verb).
The dashboard reads the cluster with its **own** SA (get/list on groups, users, identities, rolebindings,
clusterrolebindings, namespaces); the tier gates only what is *displayed*, never what is read.

**Namespace selection, as-is.** Only the `namespace-access` report is per-namespace. Its `namespaces`
parameter is a comma-separated list of **names**, at most 50, plus the `(cluster-scoped)` sentinel
(`local-development/gsd/reporting/catalogue/namespace_access.py`).

### 1.1 As-is — the namespace poll, in detail

The namespace read is a small, deliberately-scoped part of the poll, and it is the ground Extension B
extends. Measured in `local-development/gsd/poller.py` and `local-development/gsd/kube.py`:

```
 poll_once(cluster)  [binding cadence: bindingIntervalSeconds, default 300s — NOT the 60s poll]
   └─ if namespaces_read  (chart rbac.namespaces granted get/list on namespaces; optional)
        └─ client.fetch_namespaces()          kube.py  — ONE list call over the namespaces API
             ├─ None      → store.mark_namespaces_unavailable(cluster, now)   (a 403: recorded, not fatal)
             ├─ raises    → keep last cycle's rows, log a warning                (a transient failure)
             └─ [ {name, created_at, phase}, … ]  → store.replace_namespaces(cluster, rows, now)
                                                        (FULL replace: DELETE then INSERT the cycle's set)
```

- **Cadence and gate.** Namespaces ride the *binding* cadence (300s), not the 60s poll, and only when
  the chart granted `namespaces [get,list]` (`rbac.namespaces` → `namespacesReadEnabled`). The grant is
  optional; a 403 is *recorded* (`mark_namespaces_unavailable`) so a report's coverage block can say why
  absence is not attested, and never fails the poll.
- **Why it exists at all.** So the `namespace-access` report can attest **absence** — "this namespace
  exists and has no grants" — rather than "none observed" (`docs/specs/SPEC_C3_reporting_microservice.md`
  §7). Knowing a namespace *exists* is the whole point of the read.
- **What is captured, and what is not.** Exactly three fields per namespace: `name`,
  `created_at` (`metadata.creationTimestamp`), `phase` (`status.phase`). Stored in
  `cluster_namespace(cluster_id, name, created_at, phase, observed_at)` and replaced whole each cycle.
  **No labels, no annotations, no owner or quota metadata.** That is the gap: the estate's grouping
  labels exist on the objects but never reach the store, so a report cannot select on them.
- **The path from store to report.** `cluster_namespace` → `Snapshot.cluster_namespaces` (over the
  `VACUUM INTO` read-only copy) → `namespace_access.build` (existence check) → PDF/HTML. The GUI reads
  the report catalogue from `/report/api/reports` and renders the form; nothing about namespaces is
  offered to the user beyond the free-text names box.

**So the one real gap this feature fills** is that no namespace metadata beyond name/created/phase is
captured; §3 extends the poll to capture a *configurable, bounded set* of namespace metadata (labels,
extensible to annotations), of which the mnemonic is the first and the default selector.

---

## 2. Extension A — auditor groups and a least-privilege audit role (chart only)

### 2.1 Decisions (settled with the operator, 2026-09-14)

1. **Not `cluster-reader`.** It grants read on the whole cluster (all workloads and config). An auditor
   needs none of that from the dashboard, which reads with its own SA. The role is a purpose-built
   read-only **identity + RBAC** role.
2. **The role is broader than the bare gate, by intent** — it lets the auditor review in OpenShift
   directly (`oc get users`, `oc get groups`, `oc get rolebindings -A`), not only through the dashboard.
   The rules:

   ```yaml
   rules:
     - apiGroups: ["user.openshift.io"]
       resources: ["users", "groups"]
       verbs: ["get", "list"]
     - apiGroups: ["rbac.authorization.k8s.io"]
       resources: ["roles", "rolebindings", "clusterroles", "clusterrolebindings"]
       verbs: ["get", "list"]
   ```

3. **Two automatic, enforced properties.** The role includes `list clusterrolebindings`, so it clears
   the report gate — and the chart **asserts** at render that the role covers whatever `adminSar` is set
   to, failing the render otherwise, so the gate and the role can never drift. The role is read-only, so
   it can never satisfy the Usage gate (`update clusterrolebindings`, a write verb): auditors get reports
   and the audit views but **not** the Usage tab, with no extra configuration.
4. **No workload access.** No `view`/`edit` verb on any workload resource. An auditor's actual view/edit
   access, if any, comes only from their *other* group memberships; the auditor group is additive and
   read-only.
5. **The group exists either way; the binding is name-based.** An OpenShift `Group` is a single object
   with one members list — it does not merge from two sources. The group-sync operator owns groups it
   syncs (label `group-sync-operator.redhat-cop.io/sync-provider`, annotations `openshift.io/ldap.*` —
   measured on 64 groups) and rewrites their membership from LDAP. So:
   - **LDAP-synced group →** `createLocal: false`. The sync creates and owns the group; the chart creates
     only the ClusterRoleBinding, which is valid even before the group exists.
   - **Local-only group →** `createLocal: true`. The chart creates the `Group`; the binding grants it the
     role. `createLocal: true` and "this name is synced" are mutually exclusive (a co-created local group
     would be overwritten by the next sync and show as Helm drift).

### 2.2 values.yaml (new top-level stanza)

```yaml
# ---------------------------------------------------------------------------
# Reporting auditors (docs/DESIGN_reporting_auditors_and_ns_selector.md §2)
# ---------------------------------------------------------------------------
# Put a chosen group over the report gate without making anyone a cluster admin. Members can review
# users, groups and bindings in OpenShift directly AND run reports in the dashboard — read-only, no
# workload access, no Usage tab. OFF by default (opt-in): an install that does not ask for auditors
# renders no Group, Role or Binding.
rbacAuditors:
  enabled: false
  # The ClusterRole to bind. Default: the chart renders its own least-privilege read-only audit role
  # (§2.1). Set `existingClusterRole` to bind one you made elsewhere (e.g. via the namespace-config
  # operator) instead — the chart then renders no Role and only the Binding.
  createClusterRole: true
  existingClusterRole: ""          # non-empty => bind this instead of the chart-rendered role
  # The groups to grant it. Each is bound by NAME, so a synced group and a local group work the same.
  groups: []
  # - name: app-ocp-rbac-groupsync-ns-auditor
  #   createLocal: false           # false: an LDAP sync owns the Group. true: the chart creates a local Group.
```

### 2.3 templates/rbac-auditors.yaml (new file — full)

```yaml
{{- /*
  Reporting auditors (docs/DESIGN_reporting_auditors_and_ns_selector.md §2). Opt-in read-only
  identity+RBAC role, and a ClusterRoleBinding per configured group. The Group is created only when
  createLocal is true (a synced group is owned by the group-sync operator; co-creating it locally
  would fight the sync). YAML comments use '#', per the chart's convention (memory: yaml-comments-use-hash).
*/ -}}
{{- if .Values.rbacAuditors.enabled }}
{{- $admin := .Values.visibility.adminSar }}
{{- /*
  The audit role MUST cover the report gate, or members are bound but cannot run reports. Assert it
  before rendering. The rendered role grants list+get on rbac.authorization.k8s.io/{roles,rolebindings,
  clusterroles,clusterrolebindings} and user.openshift.io/{users,groups}; the default adminSar
  (list clusterrolebindings) is covered. If an operator retunes adminSar to something outside this set,
  fail the render with the remedy rather than shipping a group that silently cannot report.
*/ -}}
{{- if .Values.rbacAuditors.createClusterRole }}
{{-   $covered := dict
        "rbac.authorization.k8s.io/roles" true "rbac.authorization.k8s.io/rolebindings" true
        "rbac.authorization.k8s.io/clusterroles" true "rbac.authorization.k8s.io/clusterrolebindings" true
        "user.openshift.io/users" true "user.openshift.io/groups" true }}
{{-   $key := printf "%s/%s" (trim (toString $admin.apiGroup)) (trim (toString $admin.resource)) }}
{{-   $verb := trim (toString $admin.verb) }}
{{-   if not (hasKey $covered $key) }}
{{-     fail (printf "rbacAuditors.createClusterRole=true but visibility.adminSar (%s, verb %s) is not covered by the read-only audit role. Either set rbacAuditors.existingClusterRole to a role that grants it, or add it to templates/rbac-auditors.yaml and this guard." $key $verb) }}
{{-   end }}
{{-   if not (or (eq $verb "get") (eq $verb "list")) }}
{{-     fail (printf "rbacAuditors: visibility.adminSar.verb is %q, a non-read verb the read-only audit role will never grant. Retune adminSar to a read verb or use rbacAuditors.existingClusterRole." $verb) }}
{{-   end }}
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: {{ include "gsd.fullname" . }}-report-auditor
  labels:
    {{- include "gsd.labels" . | nindent 4 }}
rules:
  - apiGroups: ["user.openshift.io"]
    resources: ["users", "groups"]
    verbs: ["get", "list"]
  - apiGroups: ["rbac.authorization.k8s.io"]
    resources: ["roles", "rolebindings", "clusterroles", "clusterrolebindings"]
    verbs: ["get", "list"]
{{- end }}
{{- $roleName := .Values.rbacAuditors.existingClusterRole | default (printf "%s-report-auditor" (include "gsd.fullname" .)) }}
{{- range $g := .Values.rbacAuditors.groups }}
{{-   if not $g.name }}{{ fail "rbacAuditors.groups[]: every entry needs a name" }}{{ end }}
{{-   if $g.createLocal }}
---
apiVersion: user.openshift.io/v1
kind: Group
metadata:
  name: {{ $g.name }}
  labels:
    {{- include "gsd.labels" $ | nindent 4 }}
  annotations:
    # A placeholder membership managed outside the chart. Do NOT set createLocal on a group the
    # group-sync operator syncs — the sync would overwrite this object and Helm would see drift.
    "group-sync-dashboard/managed": "local"
users: []
{{-   end }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: {{ include "gsd.fullname" $ }}-report-auditor-{{ $g.name }}
  labels:
    {{- include "gsd.labels" $ | nindent 4 }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: {{ $roleName }}
subjects:
  - apiGroup: rbac.authorization.k8s.io
    kind: Group
    name: {{ $g.name }}
{{- end }}
{{- end }}
```

### 2.4 What this does NOT change

No new tier, no change to `viewer_scope`, `require_admin_tier` or any SAR. The gate is the same
`adminSar`; this only supplies a supported, least-privilege way to put a group over it. The dashboard
app and the report service are untouched by Extension A.

---

## 3. Extension B — select namespaces by the estate's grouping label (the mnemonic)

### 3.1 The gap and the decision

Every namespace in this estate carries `company.net/mnemonic` (measured: on 17 namespaces, values
`alpha`, `beta`, `demo`, `jeff`, `klt`…), and neighbouring grouping labels (`company.net/app-environment`
on 15, `company.net/oud-group` on 4). The whole RBAC model keys on them. The `namespace-access` report
today takes free-typed names, which drift and force the auditor to know the names. The operator's rule:
**select by the label**, default the label in Helm (override at install), offer the values in the GUI,
and be strict — a namespace without the label is outside the audit model. Keep explicit names as an
advanced fallback (operator's later note); page or raise the 50-cap when a mnemonic expands past it.

**Capture is extensible, not single-label.** The operator asked that the poll be extended to capture
*more* namespace metadata over time, not one hard-wired label. So the design is a **configurable,
bounded capture set**: `reporting.namespaceMetadata.labels` is a list of label keys to persist (default
`[company.net/mnemonic]`), stored key/value in a child table so adding a key is a values change and no
migration. The report's *selector* defaults to one of the captured keys
(`reporting.namespaceSelector.label`, default `company.net/mnemonic`). Bounded on purpose: only the
configured keys are stored, never the whole label map — that keeps out data the feature does not use and
that could be sensitive, while leaving the door open to environment, owner or cost-centre labels next.
Annotations are the same shape when wanted (`namespaceMetadata.annotations`), off by default; §3.3 notes
the one extra guard they need (size).

### 3.2 The flow (ASCII)

```
 Helm: reporting.namespaceMetadata.labels = [company.net/mnemonic, …]   (captured keys)
       reporting.namespaceSelector.label   = company.net/mnemonic       (the selector's key)
        │  (GSD_NS_METADATA_LABELS + GSD_NS_SELECTOR_LABEL on the Deployment; Settings reads them)
        ▼
 poller.fetch_namespaces  ──reads metadata.labels for each CAPTURED key──▶  store.replace_namespaces
        │                                                            │  child table cluster_namespace_label(name,key,value)
        ▼                                                            ▼    replaced whole each cycle, beside cluster_namespace
 dashboard app                                            report snapshot copy (VACUUM INTO, unchanged)
   GET /api/report/ticket (unchanged)                     Snapshot.namespace_metadata_values(cid, key) → ["alpha","beta",…]
        │                                                 Snapshot.namespaces_for_metadata(cid, key, ["beta"]) → ["beta-prod","beta-rnd",…]
        ▼
 GUI Reports tab: the namespace-access form shows a MULTI-SELECT of the selector key's values
   (data.reportCatalog.namespaceSelector = {label, values:[…]})           │
        │  user picks {beta, demo}  OR (advanced) explicit names
        ▼
 POST /report/api/runs {report:"namespace-access", params:{mnemonics:["beta","demo"]}}
        ▼
 namespace_access.build: expand mnemonics → names via snap.namespaces_for_metadata(cid, selector_key, mnemonics)
   (explicit `namespaces` still accepted; `mnemonics` is the strict, default path)
        ▼  ≤ NS_CAP names, else paged with a coverage note
 report renders per-namespace sections exactly as today
```

### 3.3 Data path — capture the configured metadata keys (kube.py)

`fetch_namespaces` gains a captured subset of labels. It returns the existing three fields plus a
`metadata` dict of `{key: value}` for exactly the configured keys that are present — never the whole
label map. Full replacement of the per-record mapping:

```python
# in PollClient.fetch_namespaces (local-development/gsd/kube.py), where each item is mapped:
#   OLD: {"name": …, "created_at": …, "phase": …}
keys = self.settings.namespace_metadata_labels        # e.g. ["company.net/mnemonic"]; [] disables capture
labels = (obj.get("metadata") or {}).get("labels") or {}
rows.append({
    "name": (obj.get("metadata") or {}).get("name"),
    "created_at": (obj.get("metadata") or {}).get("creationTimestamp"),
    "phase": (obj.get("status") or {}).get("phase"),
    # Only the CONFIGURED keys that are present, so the captured set is bounded and predictable. Adding
    # a key is a values change, no migration. Annotations, when enabled, are merged the same way with a
    # length guard (they can be large; a label is capped at 63 chars by the API, an annotation is not).
    "metadata": {k: labels[k] for k in keys if k in labels},
})
```

### 3.4 Data path — store the metadata key/value (store.py, one new table)

A child table keyed by `(cluster_id, name, key)` — extensible to any captured key with no further
migration, and it replaces whole each cycle alongside `cluster_namespace`:

```python
# schema (store.py, beside cluster_namespace):
CREATE TABLE IF NOT EXISTS cluster_namespace_label (
    cluster_id TEXT NOT NULL,
    name       TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    PRIMARY KEY (cluster_id, name, key)
);
CREATE INDEX IF NOT EXISTS idx_cnl_key_value ON cluster_namespace_label(cluster_id, key, value);

# replace_namespaces: after replacing cluster_namespace, replace this cluster's label rows in the SAME
# transaction, so a report never sees a namespace with stale metadata or a half-written cycle:
conn.execute("DELETE FROM cluster_namespace_label WHERE cluster_id=?", (cluster_id,))
conn.executemany(
    "INSERT INTO cluster_namespace_label(cluster_id, name, key, value) VALUES(?,?,?,?)",
    [(cluster_id, n["name"], k, v)
     for n in namespaces for k, v in (n.get("metadata") or {}).items() if v is not None and v != ""])
```

The migration is only the `CREATE TABLE`/`CREATE INDEX` (idempotent); no `ALTER`, and an old snapshot
without the table degrades to "no values" rather than crashing (§3.5 guards with `has_table`).

### 3.5 Snapshot — expose the values and the expansion (reporting/snapshot.py)

Keyed by metadata key, so the same two methods serve the mnemonic and any future captured key:

```python
def namespace_metadata_values(self, cluster_id: str, key: str) -> list[str]:
    """Distinct values captured for one metadata key, for the GUI's multi-select. Empty when the table
    is absent (pre-migration snapshot), the key is not captured, or no namespace carries it."""
    if not key or not self.has_table("cluster_namespace_label"):
        return []
    return [r["value"] for r in self._rows(
        "SELECT DISTINCT value FROM cluster_namespace_label "
        "WHERE cluster_id=? AND key=? ORDER BY value", (cluster_id, key))]

def namespaces_for_metadata(self, cluster_id: str, key: str, values: list[str]) -> list[str]:
    """Namespace names whose metadata `key` is one of `values`. The strict selector's expansion."""
    if not key or not values or not self.has_table("cluster_namespace_label"):
        return []
    marks = ",".join("?" for _ in values)
    return [r["name"] for r in self._rows(
        f"SELECT name FROM cluster_namespace_label WHERE cluster_id=? AND key=? AND value IN ({marks}) "
        "ORDER BY name", (cluster_id, key, *values))]
```

### 3.6 The report — accept the mnemonic, expand it (namespace_access.py)

```python
# SPEC.params gains `mnemonics` (the strict, default path); `namespaces` stays as the advanced fallback.
params=(
    ParamSpec("mnemonics", "csv", None,
              "Select namespaces by the estate's grouping label (see the Reports form). "
              "Strict and current; leave namespaces empty when using this.", required=False),
    ParamSpec("namespaces", "namespaces", None,
              "Advanced: explicit namespace names, at most 50; `(cluster-scoped)` for cluster-wide bindings.",
              required=False),
    ParamSpec("include_members", "bool", False, "Expand group rosters. Off by default …"),
)

# build(): resolve names from mnemonics first, else the explicit list; exactly one must be non-empty.
def build(snap, ctx, params):
    cid = ctx.cluster["id"]
    mnemonics = params.get("mnemonics") or []
    names = params.get("namespaces") or []
    if mnemonics and names:
        raise ReportError("choose namespaces by mnemonic OR by explicit name, not both")
    if mnemonics:
        names = snap.namespaces_for_metadata(cid, ctx.namespace_selector_label, mnemonics)
        if not names:
            raise ReportError(f"no namespace carries the selector label with value(s) {', '.join(mnemonics)}")
    if not names:
        raise ReportError("select at least one namespace (by mnemonic or by name)")
    names, capped = (names[:NS_CAP], len(names) > NS_CAP)   # NS_CAP = 50; coverage note when capped
    # …the rest of build() is unchanged; `capped` is recorded in the coverage block.
```

### 3.7 The GUI — a multi-select of the values (index.html, server.py)

The report catalogue response gains, per cluster, the selector label and its values, so the form can
render the control from data it already fetches:

```python
# reporting/server.py, GET /report/api/reports (catalogue): add the selector to the payload. The
# selector key must be one of the captured keys, else its values are always empty — the render guard
# in the chart (§3.8) enforces that at install; here it degrades to an empty list, hiding the control.
"namespaceSelector": {
    "label": settings.namespace_selector_label,
    "values": snap.namespace_metadata_values(cluster_id, settings.namespace_selector_label),
},
```

```javascript
// index.html reportFormCard(): for the namespace-access report, render the mnemonic multi-select from
// data.reportCatalog.namespaceSelector, ahead of the advanced explicit-names input.
const sel = cat.namespaceSelector;
const mnem = spec.name === "namespace-access" && sel && sel.values.length ? `
  <div class="report-field"><label for="report-mnemonics">${esc(sel.label)}</label>
    <select id="report-mnemonics" data-param="mnemonics" multiple size="6">
      ${sel.values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("")}
    </select>
    <span class="muted">Select one or more; the report expands each to the namespaces carrying that label.</span>
  </div>` : "";
// the existing explicit-names field is kept under a "// advanced" note; generateReport() sends
// mnemonics as an array when any option is selected, else falls back to the names field.
```

### 3.8 Chart wiring (values + deployment env)

```yaml
# values.yaml, under reporting:
reporting:
  # Namespace metadata capture and selection (docs …§3).
  namespaceMetadata:
    # The label keys the poll captures per namespace (bounded — only these, never the whole map).
    # Add keys here (environment, owner, cost-centre) with no migration. [] disables capture.
    labels:
      - company.net/mnemonic
    # annotations: []          # same shape, off by default; large-value guard applies (§3.3)
  namespaceSelector:
    # The captured key the namespace-access report selects on. MUST be one of namespaceMetadata.labels,
    # or its value list is always empty. Override at install; "" hides the selector (names only).
    label: company.net/mnemonic
```

A chart render guard asserts `reporting.namespaceSelector.label` is either empty or a member of
`reporting.namespaceMetadata.labels`, failing with the remedy — the selector can never point at a key
the poll does not capture.

```yaml
# templates/deployment.yaml, dashboard container env (the poller reads both; the report service reads
# the selector value from the catalogue call, not the env):
- name: GSD_NS_METADATA_LABELS
  value: {{ join "," .Values.reporting.namespaceMetadata.labels | quote }}
- name: GSD_NS_SELECTOR_LABEL
  value: {{ .Values.reporting.namespaceSelector.label | quote }}
```

`Settings.namespace_metadata_labels` reads `GSD_NS_METADATA_LABELS` (comma-split, `[]` when empty) and
`Settings.namespace_selector_label` reads `GSD_NS_SELECTOR_LABEL` (default `company.net/mnemonic`, `""`
allowed), beside the other `GSD_*` settings in `local-development/gsd/config.py`. `RunContext` carries
`namespace_selector_label` to `build` so the report expands on the right key.

---

## 4. What stays out of scope (stated so a reviewer holds me to it)

- No change to the tier model, the ticket, the snapshot mechanism, the artefact store, or the report
  gate SAR. Extension A only supplies a group over the existing gate; Extension B only changes how the
  one per-namespace report chooses namespaces.
- No label capture beyond the single configured selector label. The whole label map is not stored.
- No per-namespace *tier* (an auditor scoped to only their namespaces) — that remains the larger change
  §5 of `docs/ACCESS_CONTROL.md` would own, and is explicitly not this feature.

---

## 5. Test plan (each issue carries its slice)

- **Chart (Extension A):** `helm template` with `rbacAuditors.enabled=false` renders none of the three
  objects; with one synced group (`createLocal:false`) renders Binding only; with one local group
  renders Group+Binding; `createClusterRole:false`+`existingClusterRole` renders no Role; a retuned
  `adminSar` outside the audit set fails the render with the remedy; a write-verb `adminSar` fails.
  A `test_chart_strategy.py` class asserts each.
- **Data path (Extension B):** a poller test that a namespace's configured labels land in
  `cluster_namespace_label` and an unconfigured label does not; a migration test (old snapshot without
  the table → `namespace_metadata_values` returns `[]`, no crash); `namespaces_for_metadata` returns the
  right names for a key; capturing two keys keeps them distinct.
- **Report:** `mnemonics` expands to names; `mnemonics`+`namespaces` together is refused; neither is
  refused; a mnemonic matching nothing is refused with its message; >50 caps with the coverage note.
- **GUI:** `test_ui.py` — the multi-select renders from the catalogue, a selection posts `mnemonics`
  as an array, the advanced names field still works.
- **Live:** the `e2e-walk` skill re-run picks a real mnemonic (`beta`) and captures the report; a
  second walk as an auditor-group member (once the group is bound) shows the Reports tab allowed.

---

## 6. As-is → to-be, one line

| | As-is | To-be |
|---|---|---|
| Auditor over the gate | hand-made ClusterRoleBinding, per operator | opt-in `rbacAuditors` stanza, least-privilege role, name-based binding |
| Report namespace choice | free-typed names, ≤50 | the estate's mnemonic label (strict, default), names as advanced |
| Namespace labels captured | none | the one configured selector label |

---

## 7. Proposed issue order (finalised after review round 1 — each issue is its own PR)

Ordered by dependency; Extension B's issues are a chain, Extension A is independent and can land first.

1. **Issue A — chart: `rbacAuditors` stanza** (Extension A, no app code). The values stanza, the
   `templates/rbac-auditors.yaml`, the render guard, the chart README rows, the `test_chart_strategy.py`
   class. Independent; can merge first. Chart minor bump.
2. **Issue B1 — data path: capture configured namespace metadata** (Extension B, foundation). `config.py`
   (`namespace_metadata_labels`, `namespace_selector_label`), `kube.py` `fetch_namespaces`, the `store.py`
   `cluster_namespace_label` table and `replace_namespaces`, the chart env wiring
   (`GSD_NS_METADATA_LABELS`), the poller test. No user-visible change yet. Depends on nothing.
3. **Issue B2 — snapshot + report: the mnemonic selector** (Extension B). `snapshot.py`
   `namespace_metadata_values`/`namespaces_for_metadata`, `RunContext.namespace_selector_label`,
   `namespace_access.py` params and `build`, the report tests. Depends on B1 (needs the stored rows).
4. **Issue B3 — GUI + catalogue + chart value: surface the selector** (Extension B). `server.py`
   catalogue payload, `index.html` multi-select, the `reporting.namespaceSelector.label` value, the
   selector-in-captured-set render guard, `test_ui.py`. Depends on B2 (needs the report to accept
   `mnemonics`).

Each issue is scoped to pass CI on its own (B1 and B2 ship behind the not-yet-wired GUI; the report
accepts `mnemonics` before the GUI sends it). The order guarantees no half-wired state on main.

---

*Round 1 of review runs on THIS document (the design and the snippets), not on code. The reviewers'
edits, full snippets and gotchas are folded in; then the issues above are cut in the settled order,
and each is implemented and reviewed as its own PR.*
