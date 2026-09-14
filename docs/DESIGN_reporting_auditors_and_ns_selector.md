# Reporting extension — auditor groups and namespace-mnemonic selection (design + technical spec)

**Status: proposed — round 1 reviewed, corrections folded in.** The round-1 adversarial review record is
`docs/REVIEW_reporting_ext_design.md` (both reviewers, every load-bearing claim re-checked against the
code). The snippets below are the corrected versions; where a correction is load-bearing it says
"(round 1: …)". A feature request that **extends** the existing reporting and access-control design; it
is not a new module. It reads on top of, and defers to, two maintained records:

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

### 2.3 templates/rbac-auditors.yaml (new file — full, round-1 corrected)

Round 1 corrections, all accepted: read the gate through the chart's nil-safe SAR helpers, not bare
`.Values.visibility.adminSar` (a present-but-nil `adminSar:` panics); guard the no-role case
(`createClusterRole=false` with an empty `existingClusterRole` would bind a role the chart does not
render); the ClusterRoleBinding `metadata.name` must be DNS-1123 while a group name is not (LDAP DNs,
underscores), so **hash the group** into the name and keep the real name only in `subjects[]`; and **omit
`users:`** on a `createLocal` Group (a templated `users: []` is reset on every `helm upgrade`, wiping any
membership). YAML comments use `#`, per the chart's convention.

```yaml
{{- /*
  Reporting auditors (docs/DESIGN_reporting_auditors_and_ns_selector.md §2). Opt-in read-only
  identity+RBAC role, and a ClusterRoleBinding per configured group. The Group is created only when
  createLocal is true (a synced group is owned by the group-sync operator; co-creating it locally
  would fight the sync). YAML comments use '#'.
*/ -}}
{{- if .Values.rbacAuditors.enabled }}
{{- if not (kindIs "bool" .Values.rbacAuditors.enabled) }}{{ fail "rbacAuditors.enabled must be true or false" }}{{ end }}
{{- $createRole := .Values.rbacAuditors.createClusterRole }}
{{- $existing := trim (toString (.Values.rbacAuditors.existingClusterRole | default "")) }}
{{- if and (not $createRole) (eq $existing "") }}
{{-   fail "rbacAuditors.createClusterRole=false requires rbacAuditors.existingClusterRole (otherwise the Binding names a ClusterRole this chart does not render)." }}
{{- end }}
{{- if and $createRole (ne $existing "") }}
{{-   fail "rbacAuditors.createClusterRole=true and rbacAuditors.existingClusterRole are mutually exclusive: either render the chart role, or bind one you made elsewhere." }}
{{- end }}
{{- if $createRole }}
{{-   $g := include "gsd.visibilitySarApiGroup" . }}
{{-   $r := include "gsd.visibilitySarResource" . }}
{{-   $v := include "gsd.visibilitySarVerb" . }}
{{-   $covered := dict
        "rbac.authorization.k8s.io/roles" true "rbac.authorization.k8s.io/rolebindings" true
        "rbac.authorization.k8s.io/clusterroles" true "rbac.authorization.k8s.io/clusterrolebindings" true
        "user.openshift.io/users" true "user.openshift.io/groups" true }}
{{-   $key := printf "%s/%s" $g $r }}
{{-   if not (hasKey $covered $key) }}
{{-     fail (printf "rbacAuditors.createClusterRole=true but visibility.adminSar (%s, verb %s) is not covered by the read-only audit role. Set rbacAuditors.existingClusterRole to a role that grants it, or add it to templates/rbac-auditors.yaml and this guard." $key $v) }}
{{-   end }}
{{-   if not (or (eq $v "get") (eq $v "list")) }}
{{-     fail (printf "rbacAuditors: visibility.adminSar.verb is %q, a non-read verb the read-only audit role will never grant. Retune adminSar to a read verb or use rbacAuditors.existingClusterRole." $v) }}
{{-   end }}
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: {{ printf "%s-report-auditor" (include "gsd.fullname" .) | trunc 253 | trimSuffix "-" }}
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
{{- $roleName := $existing | default (printf "%s-report-auditor" (include "gsd.fullname" .) | trunc 253 | trimSuffix "-") }}
{{- if not (kindIs "slice" (.Values.rbacAuditors.groups | default list)) }}{{ fail "rbacAuditors.groups must be a list" }}{{ end }}
{{- range $g := .Values.rbacAuditors.groups }}
{{-   if or (not (kindIs "map" $g)) (not $g.name) (eq (trim (toString $g.name)) "") }}{{ fail "rbacAuditors.groups[]: every entry needs a non-empty name" }}{{ end }}
{{-   if and (hasKey $g "createLocal") (not (kindIs "bool" $g.createLocal)) }}{{ fail (printf "rbacAuditors.groups[%s].createLocal must be true or false" $g.name) }}{{ end }}
{{-   if $g.createLocal }}
---
apiVersion: user.openshift.io/v1
kind: Group
metadata:
  name: {{ $g.name | quote }}
  labels:
    {{- include "gsd.labels" $ | nindent 4 }}
  annotations:
    # Membership is NOT in this manifest. Do not set createLocal on a group-sync-operator group —
    # the next sync overwrites the object and Helm reports drift.
    group-sync-dashboard/managed: local
# users omitted on purpose: a templated `users: []` is reset on every helm upgrade.
{{-   end }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  # CRB names are DNS-1123 (253). Group names are not (LDAP DNs, underscores). Hash the group.
  name: {{ printf "%s-ra-%s" (include "gsd.fullname" $) (sha256sum $g.name | trunc 12) | trunc 253 | trimSuffix "-" }}
  labels:
    {{- include "gsd.labels" $ | nindent 4 }}
  annotations:
    group-sync-dashboard/auditor-group: {{ $g.name | quote }}
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: {{ $roleName | quote }}
subjects:
  - apiGroup: rbac.authorization.k8s.io
    kind: Group
    name: {{ $g.name | quote }}
{{- end }}
{{- end }}
```

Note for Issue A: `rbacAuditors.enabled: false` is a new `false` default, so it joins `KEPT_OFF` in
`local-development/tests/test_values_defaults.py` (that test asserts the false-default set exactly) with a
reason, and gets a chart README row. There is no `values.schema.json` in the tree.

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
 Helm: reporting.namespaceMetadata.labels = [company.net/mnemonic, …]   (captured keys — DASHBOARD pod)
       reporting.namespaceSelector.label   = company.net/mnemonic       (selector key — REPORT pod)
        │  (GSD_NS_METADATA_LABELS on the dashboard Deployment; GSD_REPORT_NS_SELECTOR_LABEL on the report Deployment)
        ▼
 poller.fetch_namespaces(label_keys)  ──reads metadata.labels for each CAPTURED key──▶  store.replace_namespaces
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

Round 1: `ClusterClient` has **no `self.settings`** (`__init__(cluster, timeout=15.0)`), so the keys are a
**parameter**, threaded from `Settings.namespace_metadata_labels` through `refresh_bindings` to the call.
The method builds `records` with `records.append`, skipping nameless items:

```python
# local-development/gsd/kube.py — ClusterClient.fetch_namespaces gains a label_keys argument:
def fetch_namespaces(self, label_keys: list[str] | None = None) -> list[dict] | None:
    keys = list(label_keys or ())
    with self._client() as client:
        try:
            items = self._list_all(client, NAMESPACE_API)
        except ClusterError as exc:
            if exc.outcome == FORBIDDEN and NAMESPACE_API in exc.message:
                log.debug("%s: not permitted to list namespaces — the namespace report cannot "
                          "attest absence", self.cluster.name)
                return None
            raise
    records: list[dict] = []
    for obj in items:
        meta = obj.get("metadata") or {}
        name = meta.get("name")
        if not name:
            continue
        labels = meta.get("labels") or {}
        # Only the CONFIGURED keys that are present — bounded and predictable; adding a key is a
        # values change, no migration. (Annotations, when later enabled, merge the same way.)
        records.append({
            "name": name,
            "created_at": meta.get("creationTimestamp"),
            "phase": (obj.get("status") or {}).get("phase"),
            "metadata": {k: labels[k] for k in keys if k in labels},
        })
    log.debug("fetched %d namespaces from %s", len(records), self.cluster.name)
    return records

# local-development/gsd/poller.py — refresh_bindings threads the keys (it has no Settings):
def refresh_bindings(store, cluster, timeout, audit_mode="off", audit_max_per_cycle=20,
                     namespaces_read=False, namespace_metadata_labels=None):
    ...
    namespaces = fetch_namespaces(namespace_metadata_labels)   # was fetch_namespaces()
# and the Poller call site passes namespace_metadata_labels=self.settings.namespace_metadata_labels
```

### 3.4 Data path — store the metadata key/value (store.py, one new table)

A child table keyed by `(cluster_id, name, key)` — extensible to any captured key with no further
migration, and it replaces whole each cycle alongside `cluster_namespace`:

Round 1: `replace_namespaces` **already** wraps its DELETE+INSERT+status in one `with self._write()`, so
the child-table SQL goes **inside that same block** — not a second transaction — or a report can read a
namespace whose metadata was deleted but not yet re-inserted. The table ships both as module-level schema
and as a new numbered `_MIGRATIONS` entry (12), idempotent (`CREATE TABLE IF NOT EXISTS`, no `ALTER`).

```sql
-- store.py, module schema and migration 12:
CREATE TABLE IF NOT EXISTS cluster_namespace_label (
    cluster_id TEXT NOT NULL,
    name       TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    PRIMARY KEY (cluster_id, name, key),
    FOREIGN KEY(cluster_id, name) REFERENCES cluster_namespace(cluster_id, name) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_cnl_key_value ON cluster_namespace_label(cluster_id, key, value);
```

```python
# store.py — replace_namespaces, the child rows INSIDE the existing `with self._write() as conn:`
conn.execute("DELETE FROM cluster_namespace_label WHERE cluster_id=?", (cluster_id,))
conn.executemany(
    "INSERT INTO cluster_namespace_label(cluster_id, name, key, value) VALUES(?,?,?,?)",
    [(cluster_id, n["name"], k, v)
     for n in rows for k, v in (n.get("metadata") or {}).items() if v is not None and v != ""])
```

An old snapshot without the table degrades to "no values" rather than crashing (§3.5 guards with
`has_table`, which exists; `has_column` is neither present nor needed).

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
```

Round 1, the validation-timing correctness point: the endpoint documents a **422** for bad params, but
validation inside `build()` runs after the 202 (it becomes a *failed run*). So the pure-input checks move
to a **ReportSpec `validator` hook** run in `validate_params` at the endpoint (422); only the
snapshot-dependent check (a mnemonic expanding to nothing) stays in `build()`. `ReportError` does not
exist — the type is `ValidationError` (`catalogue/common.py`); the cap constant is `MAX_NAMESPACES`;
`RunContext` gains `namespace_selector_label` (and `ReportSettings` supplies it — §3.8).

```python
# namespace_access.py — the validator runs at the endpoint (422 on bad input):
def _validate_selection(params: dict) -> None:
    mnemonics = params.get("mnemonics") or []
    names = params.get("namespaces") or []
    if mnemonics and names:
        raise ValidationError("choose namespaces by mnemonic OR by explicit name, not both")
    if not mnemonics and not names:
        raise ValidationError("select at least one namespace, by mnemonic or by explicit name")
    if len(mnemonics) > MAX_NAMESPACES:
        raise ValidationError(f"at most {MAX_NAMESPACES} mnemonic values per report")
# SPEC = ReportSpec(..., validator=_validate_selection); validate_params calls spec.validator(out).

# build(): the snapshot-dependent expansion; a failed run (needs the snapshot) is correct here.
def build(snap, ctx, params):
    cid = ctx.cluster["id"]
    mnemonics = params.get("mnemonics") or []
    names = params.get("namespaces") or []
    if mnemonics:
        names = snap.namespaces_for_metadata(cid, ctx.namespace_selector_label, mnemonics)
        if not names:
            raise ValidationError(f"no namespace carries the selector label with value(s) {', '.join(mnemonics)}")
    capped = len(names) > MAX_NAMESPACES
    names = names[:MAX_NAMESPACES]              # cap AFTER expansion; a coverage note when capped
    # …the rest of build() is unchanged; `capped` is recorded in the coverage/truncation block.
```

The `type: "namespaces"` parser errors on `[]`, so the empty advanced field must arrive omitted/`None`
(which `validate_params` treats as "not provided"), never as `[]`; `parse_namespaces` is unchanged (a
test asserts it still errors at 51 explicit names).

### 3.7 The GUI — a multi-select of the values (index.html, server.py)

The report catalogue response gains, per cluster, the selector label and its values, so the form can
render the control from data it already fetches:

Round 1: `list_reports` is **global** today (no cluster, no snapshot); it must open the snapshot and key
values **by cluster** (the install is multi-cluster), swallowing snapshot errors so a missing first
snapshot never 500s the Reports tab. And the GUI `onchange` serialises with `el.value`, which for a
`<select multiple>` is the **first** option — a `readParamEl` helper returns an array.

```python
# reporting/server.py, list_reports: open the snapshot, key selector values by cluster id.
selectors: dict[str, dict] = {}
try:
    with Snapshot(newest_snapshot(settings.snapshot_dir)) as snap:
        label = settings.namespace_selector_label
        for row in snap.clusters():
            selectors[row["id"]] = {"label": label,
                                    "values": snap.namespace_metadata_values(row["id"], label) if label else []}
except (SnapshotError, OSError):
    selectors = {}          # a missing first snapshot must not 500 the catalogue; the UI hides the control
# … return {..., "namespaceSelectors": selectors}
```

```javascript
// index.html reportFormCard(): the mnemonic multi-select for THIS cluster, ahead of the advanced names input.
const sel = (cat.namespaceSelectors && cat.namespaceSelectors[view.cluster]) || {label: "", values: []};
const mnem = spec.name === "namespace-access" && sel.values.length ? `
  <div class="report-field"><label for="report-mnemonics">${esc(sel.label)}</label>
    <select id="report-mnemonics" data-param="mnemonics" multiple size="6">
      ${sel.values.map((v) => `<option value="${esc(v)}">${esc(v)}</option>`).join("")}
    </select>
    <span class="muted">Select one or more; the report expands each to the namespaces carrying that label.</span>
  </div>` : "";

// wireReports()'s data-param onchange must read a multiple select as an ARRAY:
function readParamEl(el) {
  if (el.type === "checkbox") return el.checked;
  if (el.tagName === "SELECT" && el.multiple) return Array.from(el.selectedOptions).map((o) => o.value);
  return el.value;
}
// f[el.dataset.param] = readParamEl(el);   // the id #report-param-namespace-access-namespaces stays (test_ui fills it)
```

### 3.8 Chart wiring (values + deployment env)

Round 1, two corrections. **(a) The default is OFF, not the mnemonic.** Capture rides `if namespaces_read`,
and `rbac.namespaces` is `false` by default (the chart's 0.14.0 "no RBAC you don't need" rule, enforced by
`KEPT_OFF`). Defaulting the label to `company.net/mnemonic` while the grant is off would make the selector
always empty and would trip the render guard on a default `helm template`. So the feature is opt-in like
the read it depends on: `labels: []` and `selector.label: ""` by default; the operator enables three
values plus the grant. This also reconciles §4 (the mechanism is a bounded list; the default is empty).
**(b) The selector lives in the REPORT pod, not the dashboard.** The catalogue and the expansion run in
`gsd.reporting.server`/`ReportSettings`; only the poller (dashboard) captures. So two envs on two pods.

```yaml
# values.yaml, under reporting. Both empty by default; enabling needs rbac.namespaces=true as well.
reporting:
  namespaceMetadata:
    # Label keys the poll captures per namespace (bounded — only these, never the whole map). Add keys
    # (environment, owner, cost-centre) with no migration. Enabling needs rbac.namespaces=true.
    labels: []                       # e.g. [company.net/mnemonic]
  namespaceSelector:
    # The captured key the namespace-access report selects on. MUST be one of namespaceMetadata.labels.
    # "" hides the selector (explicit names only).
    label: ""                        # e.g. company.net/mnemonic
```

A `gsd.reportingGuards` helper (in `_helpers.tpl`) asserts, with `| default list` so a commented-out
stanza never panics `join`: (1) if `namespaceMetadata.labels` is non-empty while `rbac.namespaces` is
false → fail (the poll never lists namespaces, so the selector is always empty); (2) if
`namespaceSelector.label` is set but not among `namespaceMetadata.labels` → fail (it points at a key the
poll does not capture).

```yaml
# templates/deployment.yaml — DASHBOARD container (the poller captures):
- name: GSD_NS_METADATA_LABELS
  value: {{ join "," (((.Values.reporting | default dict).namespaceMetadata).labels | default list) | quote }}

# templates/report-deployment.yaml — REPORT container (the catalogue + build expand):
- name: GSD_REPORT_NS_SELECTOR_LABEL
  value: {{ (((.Values.reporting | default dict).namespaceSelector).label | default "") | quote }}
```

`Settings.namespace_metadata_labels` (dashboard, `local-development/gsd/config.py`) reads
`GSD_NS_METADATA_LABELS` (comma-split, `[]` when empty); `ReportSettings.namespace_selector_label` (report
pod, `local-development/gsd/reporting/config.py`) reads `GSD_REPORT_NS_SELECTOR_LABEL` (`""` allowed).
`runs.py`'s render passes it into `RunContext.namespace_selector_label` so `build` expands on the right key.

### 3.9 Auto-discovery in the report forms (round-2 enhancement)

The operator's later asks, reconciled: *strict applies only to namespace discovery — the reviewer stays
free-type. Namespaces are a drop-down where you check multiple auto-discovered namespaces, like an
existing tab; free-form search / type / pattern-match are now the optional secondary paths.* Both assists
are fed by data the catalogue already reaches, and neither changes a report's output or the tier.

**The discovery source, per cluster, in the catalogue.** The catalogue call already opens the snapshot
(B3) and already returns `viewer` (the ticket identity — the person generating the report). It gains two
bounded, per-cluster lists a wide-tier reader may already see on the Users and Namespace tabs:

```python
# reporting/server.py, list_reports — beside the per-cluster namespaceSelectors (B3):
discovery[row["id"]] = {
    "namespaces": [r["name"] for r in snap.cluster_namespaces(row["id"])],   # the checkable list
    "users": [u["user_name"] for u in snap.users(row["id"])][:2000],         # reviewer autocomplete, capped
}
# … and the payload keeps "viewer": p.name (the reviewer default). Snapshot errors already swallowed.
```

**Reviewer — auto-discovered, NOT strict (access-certification).** Resolved with the operator: strict is
for namespaces only. The `reviewer` parameter stays `str` and required; the GUI pre-fills it with
`cat.viewer` (you, the person generating the pack) when empty, and backs the text input with a
`<datalist>` of known users so a different reviewer autocompletes. **Free-type is the default** — an
external auditor is a valid reviewer who is not a cluster user — so the only validation is required,
non-empty, trimmed; the pack still records "printed, not verified". No hard "must be a known user" mode.

**Namespaces — a checkable multi-select of auto-discovered namespaces, strict (namespace-access).** The
primary control becomes a drop-down where the user **checks multiple** discovered namespaces — the same
shape as the Namespace-audit tab's namespace picker (`gsd/static/index.html`, `#ns-pick`), made `multiple`
and fed from the catalogue's per-cluster `discovery.namespaces` plus the `(cluster-scoped)` sentinel. This
is the **strict** path: every selected value is a real, discovered namespace, and the report receives them
as the existing `namespaces` array — the wire contract (B2) is unchanged, the multi-select is a GUI
affordance over it. A small **search box filters the list** as the user types (client-side, over the
discovered names). The mnemonic multi-select (B3) sits above it as a one-click grouping that pre-checks
the namespaces carrying a label value.

**The free-form paths are now optional.** Typing a name the discovery did not list, or a prefix / glob
pattern, is a secondary affordance behind an "advanced" toggle, not the default. It keeps the current
comma-separated **format** and its per-entry format validation (`parse_namespaces`), and — because the
report exists in part to attest **absence** ("this namespace does NOT exist on the cluster") — an
unknown-but-valid name is still accepted there rather than rejected. Pattern/glob expansion, if wanted, is
a later follow-up; the strict default is the checkable discovered list.

```javascript
// index.html reportFormCard(), namespace-access: the strict checkable multi-select (modelled on #ns-pick).
const disc = (cat.discovery && cat.discovery[view.cluster]) || {namespaces: [], users: []};
const nsOptions = ["(cluster-scoped)", ...disc.namespaces];
// <input type="search" id="ns-filter" placeholder="filter…">   // optional, client-side narrows the list
// <select id="report-param-namespace-access-namespaces" data-param="namespaces" multiple size="10">
//   {nsOptions.filter(byFilter).map(n => `<option value="${esc(n)}">${esc(n)}</option>`)}   // checked = selected
// wireReports()'s readParamEl returns Array.from(el.selectedOptions).map(o=>o.value) for a multiple select.
// Advanced (optional) toggle reveals the comma-format text input (the old free-form path) for a name not listed.
// reviewer field (access-certification): value defaults to (form.reviewer ?? cat.viewer ?? ""); <input list="user-list">.
```

This is a catalogue-and-GUI change (Issue B4 in §7); it needs the per-cluster catalogue shape B3
introduces, and the discovered-namespace list needs `rbac.namespaces` on (the same dependency as the
mnemonic). When the list is empty (the grant is off), the form falls back to the optional free-form field.

---

## 4. What stays out of scope (stated so a reviewer holds me to it)

- No change to the tier model, the ticket, the snapshot mechanism, the artefact store, or the report
  gate SAR. Extension A only supplies a group over the existing gate; Extension B only changes how the
  one per-namespace report chooses namespaces.
- **Capture is a bounded, configured list, never the whole label map** (round 1 reconciled §3 and this
  section): the *mechanism* is a list of keys, so it extends to environment or owner labels later; the
  *default* is empty, and only the explicitly configured keys are stored. The whole label map is never
  persisted.
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

Ordered by dependency (round 1 reworked the boundaries per N5); Extension A is independent and can land
first, Extension B is a chain B1 → B2 → B3.

Cut as issues after round 1: **A = #100**, **B1 = #101**, **B2 = #102 (needs #101)**, **B3 = #103 (needs #102)**, **B4 = #104 (needs #103)** — the §3.9 auto-discovery form assists. Each is its own PR, re-reviewed on real code at implementation.

1. **Issue A — chart: `rbacAuditors` stanza** (Extension A, no app code). The values stanza, the
   round-1-corrected `templates/rbac-auditors.yaml` (helpers, guards, hashed CRB name, no `users:`), the
   `rbacAuditors.enabled` entry in `KEPT_OFF`, the chart README rows, a `test_chart_strategy.py` class
   covering each render state (off; synced group → Binding only; local group → Group+Binding;
   `existingClusterRole` → no Role; a retuned/non-read `adminSar` → fail). Independent. Chart minor bump.
2. **Issue B1 — data path + capture value + the reporting guards** (Extension B, foundation).
   `config.py` `Settings.namespace_metadata_labels`; `kube.py` `fetch_namespaces(label_keys=…)`;
   `poller.py` threading; `store.py` `cluster_namespace_label` (module schema + migration 12) and the
   child rows inside the existing `replace_namespaces` transaction; the values `reporting.namespaceMetadata.labels`
   (default `[]`) and `reporting.namespaceSelector.label` (default `""`); `GSD_NS_METADATA_LABELS` on the
   **dashboard** Deployment; the `gsd.reportingGuards` render guards (labels-need-rbac.namespaces;
   selector-in-labels); the poller/store tests. No report or GUI change. Depends on nothing.
3. **Issue B2 — snapshot + report + the report-pod selector env** (Extension B). `snapshot.py`
   `namespace_metadata_values`/`namespaces_for_metadata` (guarded by `has_table`); `RunContext` and
   `ReportSettings` gain `namespace_selector_label`; `GSD_REPORT_NS_SELECTOR_LABEL` on the **report**
   Deployment; `runs.py` passes it to `RunContext`; `namespace_access.py` params, the `_validate_selection`
   validator (422 at the endpoint) and `build` (expansion + cap); the report tests. Depends on B1 (needs
   the stored rows). The API accepts `mnemonics` here, before any GUI sends it.
4. **Issue B3 — catalogue + GUI** (Extension B). `server.py` `list_reports` opens the snapshot and returns
   `namespaceSelectors` keyed by cluster (errors swallowed); `index.html` the multi-select and the
   `readParamEl` array serialisation (keeping the advanced explicit-names field and its test id);
   `test_ui.py` for the multi-select posting an array and the per-cluster values. Depends on B2.

5. **Issue B4 — auto-discovery in the report forms** (§3.9). `list_reports` adds per-cluster `discovery`
   (namespace names + a capped users list) beside `namespaceSelectors`; the namespace-access form gets a
   **checkable multi-select of discovered namespaces** (strict; modelled on `#ns-pick`) with a client-side
   filter, and the free-form comma-format field moves behind an optional advanced toggle; the
   access-certification `reviewer` pre-fills with the viewer and gets a known-users `<datalist>`, free-type
   (not strict). `test_ui.py`. Depends on B3 (the per-cluster catalogue shape).

Each issue is scoped to pass CI on its own and leaves no half-wired state on main: B1 captures behind the
default-off values; B2's report accepts `mnemonics` and validates before any GUI sends it; B3 surfaces it;
B4 assists the form. Because the defaults are off, none of them changes a default install's behaviour.

---

*Round 1 of review runs on THIS document (the design and the snippets), not on code. The reviewers'
edits, full snippets and gotchas are folded in; then the issues above are cut in the settled order,
and each is implemented and reviewed as its own PR.*
