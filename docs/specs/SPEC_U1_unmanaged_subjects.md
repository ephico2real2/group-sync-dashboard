# SPEC U1 — the unmanaged finding on ServiceAccount and User subjects, silenced only by the operator's label (#353)

| | |
|---|---|
| Programme | Unmanaged-grant discovery (`docs/unmanaged-audit-design.md`), continued after #312: the finding reads Group subjects only; this makes it read every subject kind Kubernetes defines and honour the same label on all of them |
| Batch | U — unmanaged-grant discovery |
| Release | — (post-programme) |
| Version on release | app 0.33.0, chart 0.54.0 |
| Issue | [#353](https://github.com/ephico2real2/group-sync-dashboard/issues/353) |
| Status | specified |
| Source | OB1's implementation specification of 2026-09-24, written before any code from the operator's words on #312 and #353, the upstream Kubernetes sources cited in §2.1, the lab measured read-only on 2026-09-24 (§2.2), and a map of every reader of the binding table on main `244d4ab` (§2.3) |

## How to read this spec

"Measured" is what the lab or an upstream source answered, with the command. "Design" is the code, file by
file, in implementation blocks applied **verbatim** by `local-development/apply-spec-blocks.py`: an edit
block's Old text is replaced by its New text and must match exactly once; a create block is a whole new
file. A block found wrong during implementation is corrected **here first**, with the reason under
"Orchestrator's notes", and only then applied.

## Orchestrator's notes

Decisions taken where the issue was silent, each with its reason. They bind the code below.

- **Exclusion is the operator's label on the binding, and nothing else — the operator's rule, not a
  design choice.** *"The exclusion is not automatic … We are going to decide who to exclude"*, *"Using that
  label. We just need capabilities"*, *"We will labeling the role bindings or clusterrolebindings for users
  or groups or service account"* (#312, 2026-09-24). A ServiceAccount or User grant is `unmanaged` unless the
  binding carries `rbac.ocp.io/config-source` or `rbac.ocp.io/unmanaged-exception`. No `system:` name, no
  platform namespace, no Helm, OLM or Argo CD label excludes anything (§3.4). The measured consequence on the
  lab is stated in §2.2 and §6 so that nobody reads it as a defect: 713 of the lab's 720 ServiceAccount and
  User subject rows carry no label today, and every one of them becomes a finding until the operator labels
  the grants they decide are legitimate.
- **One table, widened in place; `group_name` keeps its name.** The rows join `rbac_group_binding`, with
  `subject_kind` and `subject_namespace` beside the subject's name, and the primary key gains both
  (migration 20, §3.2). A second table for the other kinds would have meant a second copy of the
  classification — the one thing `docs/unmanaged-audit-design.md` I2 forbids, because two copies drift and
  the log and the page then disagree about what a finding is. The column `group_name` holds the subject's
  name whatever its kind: it is read in 106 places in `store.py`, 33 in the report snapshot, 24 on the page
  and about a hundred in tests (measured with `grep -c`), so a rename is not a change this format can carry
  safely; the table comment, the API document and the row's `subject_kind` say what it names.
- **One gate per cluster, over every subject kind.** `unmanaged` still requires that some binding on the
  cluster carries a config-source other than this chart's own (#354). The gate now reads labelled bindings
  of every kind: a policy operator that labels only Group bindings (the lab's) opens the finding for
  ServiceAccount and User grants too, and an operator with no policy operator opens it the moment they label
  their first legitimate grant of any kind. The issue asked what "in use" means for kinds the policy
  operator may never label; the answer is that the operator's own label IS the policy system for those
  kinds, and one gate keeps one rule (§3.4). A per-kind gate was considered and rejected: it would leave
  the lab's 713 unlabelled grants silent until someone labelled one of each kind, and it is a second rule
  for the same label.
- **A ServiceAccount subject that omits its namespace on a RoleBinding is stored under the binding's
  namespace**, because that is the account the authorizer matches (§2.1, `appliesToUser`). The row names
  what RBAC grants to, not what the object happens to spell. The lab has 26 such subjects (§2.2).
- **The binding history stays Group + User.** `binding_event` records Group subjects from this table and
  User subjects from `user_binding` (`docs/DESIGN_binding_events.md` bounds `subject_kind` at two, and the
  metric `gsd_binding_changes_total` is pre-seeded on that pair). Recording User rows from the widened table
  too would double every User event; a ServiceAccount stream is a change to that design, its identity rule
  (a namespace-qualified subject) and its metric vocabulary, and it is not #353's capability. So
  `replace_bindings` diffs Group rows only (§3.2), and a ServiceAccount grant that appears or disappears is a
  finding on the next refresh but not a line on Home's "what changed". Stated here so a reviewer reads it as
  a decision, not an omission.
- **`/user-bindings` is not changed.** It answers a different question — is a person named directly, an
  offboarding risk — and the issue says it keeps its own platform count. A User grant is therefore visible
  twice, under two questions: on `/user-bindings` whether or not it is labelled, and on `/bindings/findings`
  as `unmanaged` until it is. The 35 User rows on the lab are stored twice for it (§6). `fetch_user_bindings`
  keeps its own two list calls; folding it into `fetch_bindings` is a pre-existing duplication this spec
  does not touch.
- **Two adjacent defects found by the reader map are fixed here, because the blocks that fix them are the
  blocks this spec edits anyway.** (1) `poller.refresh_bindings` never forwarded `audit_stamped` to the store
  — `kube.py` read the `rbac.ocp.io/unmanaged` label into the view and the row dict dropped it, so
  `audit_stamped` was 0 for every live row, the RESOLVED line could never fire from live data and the RBAC
  policy page's "Audit-stamped" tile always read 0. The row dict now carries it (§3.6, tested §4). (2)
  `metrics.FINDINGS` lacked `unmanaged`, so `gsd_bindings_total{finding="unmanaged"}` was emitted only while
  such rows existed instead of being pre-seeded at 0 like the other four tiers — a series that vanishes
  breaks `by (finding)` aggregation and hides a count going to zero. The tuple gains the word (§3.10).
- **The RBAC policy page counts the cluster, not the loaded page.** Its hero and "Unmanaged" tile read
  `f.unmanaged.length`, the rows the page fetched (at most `FINDINGS_PAGE`, 500), while `counts.unmanaged`
  is the cluster's. With one finding that was invisible; with 713 on the lab the tab would say 500. They
  read `counts.unmanaged` now and the list says how many of the total it shows (§3.8).
- **`_OBSERVATION_SEEDS` is not changed.** The first draft narrowed the `binding:Group` seed to Group rows;
  the scratch application refuted it: migration 14 splices those statements into its own list, so the clause
  ran against a v0 database's old shape ("no such column: subject_kind"). And it was unnecessary — the marker
  is consumed by the refresh that observes the cluster, empty or not, so a cluster holding only account rows
  has observed groups by the existing design (§3.2). A migration's spliced statements must stay valid on every
  shape it can meet; that is the general lesson, recorded here.
- **The metric family keeps its label set.** `gsd_bindings_total{cluster, finding}` now counts rows of every
  kind; a `subject_kind` label was considered and not added, because a label-set change re-keys every
  scraper's series (the chart's own Grafana panel aggregates and would survive; an operator's recording
  rule might not) and the per-kind split is on the API. The help string says what the family counts.
- **Versions: app 0.33.0, chart 0.54.0.** A schema migration means the report image must be rebuilt at the
  same appVersion (`gsd/reporting/snapshot.py#KNOWN_SCHEMA_VERSION` refuses a newer copy), and the API rows
  gain two fields: MINOR on the application, and the appVersion move bumps the chart MINOR, as 0.53.0 did
  for 0.32.0. SPEC_S4c had reserved exactly these two numbers while "specified"; its header and index row move
  to the next rungs, app 0.34.0 and chart 0.55.0, because `tests/test_specs_index.py` requires a
  specified spec to name versions above the tree's (§3.11).
- **Wording on the page changes where it would be false.** "Group bindings on this cluster" and "Grant a
  real group" name a total that now includes accounts and people; the four UI assertions that pin those
  words move with them (§4). Wording that stays true — "grant nobody", the Dangling and Unresolved notes,
  which are Group tiers — is untouched.

## 1. The mandate, and what is out of scope

The finding exists to find grants made by hand that bypass policy, on any subject: *"the goal is
legitimately find manually created grants that violate policies … These grants can be on service accounts
or groups or users etc."* (the operator on #312). Today `kube.py#_binding_views` keeps `kind: Group`
subjects only, so a hand-made ClusterRoleBinding to a ServiceAccount — the lab's `shared-qa-poller`, made
for #310's testing — is not seen at all.

In scope: the capability to read ServiceAccount and User subjects, store them beside Group ones, classify
them with the same rule, silence them with the same label, and show them everywhere the finding is shown
(the log, the Access granted and RBAC policy pages, the counts on the Overview and the KPI page, the API,
the reports and `/metrics`).

Out of scope, each stated in the notes above with its reason: any inference of legitimacy from how a grant
was applied; a change to `/user-bindings`; a ServiceAccount stream in `binding_event`; a `subject_kind`
label on the metric family; a rename of `group_name`.

## 2. Research

### 2.1 Upstream Kubernetes — what a subject is

Read from the upstream sources on 2026-09-24 (`gh api repos/kubernetes/kubernetes/contents/<path>`,
kubernetes/kubernetes master `90777f0b13827dcae8301137ea64f699f3449dbc`; kubernetes/api master
`1e25e01b2361a6355f5a59bfaed63cab4ad26a89`):

- **Three kinds, no more.** `rbac/v1/types.go` `Subject`: "kind of object being referenced. Values defined
  by this API group are "User", "Group", and "ServiceAccount". If the Authorizer does not recognized the
  kind value, the Authorizer should report an error." The constants are `GroupKind = "Group"`,
  `ServiceAccountKind = "ServiceAccount"`, `UserKind = "User"` (lines 34–36). `ValidateRoleBindingSubject`
  (`pkg/apis/rbac/validation/validation.go`, line 245) refuses any other kind at admission, so a stored row
  never needs a fourth value.
- **`apiGroup` is derived from the kind**, `""` for ServiceAccount and `rbac.authorization.k8s.io` for User
  and Group (`pkg/apis/rbac/v1/defaults.go` `SetDefaults_Subject`, validation.go lines 226 and 235). It
  carries no information the kind does not, so it is not stored.
- **Only a ServiceAccount subject has a namespace.** types.go: "namespace of the referenced object. If the
  object kind is non-namespace, such as "User" or "Group", and this value is not empty the Authorizer
  should report an error." For a ServiceAccount, validation.go line 229 requires it on a ClusterRoleBinding
  (`!isNamespaced && len(subject.Namespace) == 0` → Required) and permits its absence on a RoleBinding.
- **An absent namespace on a RoleBinding means the binding's own.** `pkg/registry/rbac/validation/rule.go`
  `appliesToUser`, lines 289–300: "default the namespace to namespace we're working in if its available.
  This allows rolebindings that reference SAs in th local namespace to avoid having to qualify them" —
  `saNamespace := namespace; if len(subject.Namespace) > 0 { saNamespace = subject.Namespace }`, then
  `serviceaccount.MatchesUsername(saNamespace, subject.Name, user.GetName())`. The identity RBAC matches is
  `system:serviceaccount:<namespace>:<name>`, so the row stores the resolved namespace (§3.3).

### 2.2 The lab — what the cluster holds (CRC, OpenShift 4.22.7, 2026-09-24)

`oc get clusterrolebindings -o json` and `oc get rolebindings -A -o json`, tabulated by a script over the
two files (the script and its output are in the session log):

| | |
|---|---|
| bindings | 292 ClusterRoleBindings, 605 RoleBindings; 1 with no subjects (`system:node`) |
| subject rows by kind | Group 205 (50 cluster-wide, 155 namespaced); **ServiceAccount 685** (234, 451); **User 35** (16, 19) |
| `apiGroup` | Group and User `rbac.authorization.k8s.io` (240 rows), ServiceAccount absent (685 rows) — the defaults of §2.1, nothing else |
| ServiceAccount subjects with no `namespace` | **26**, all on RoleBindings (OLM-written: `cert-manager-operator.v1.20.0`, `grafana-operator.v5.24.0`, `group-sync-operator.v0.0.36`), so §2.1's default applies to real objects here |
| RoleBinding ServiceAccount subjects naming another namespace | 85 — a stored namespace must be the subject's own, not the binding's, when the subject spells one |
| bindings by subject-kind set | Group only 200, ServiceAccount only 663, User only 27, Group+User 3, ServiceAccount+User 3 |
| `rbac.ocp.io/config-source` | 51 bindings: `baseline-nonprod-rbac` 26, `baseline-cluster-rbac` 11, `group-sync-dashboard` 8, `baseline-prod-rbac` 3, `custom-cluster-rbac` 1, `bdp-oud-group-rbac` 1, `trino-oud-group-rbac` 1 |
| subject rows on labelled bindings | Group 44; **ServiceAccount 7 — every one of them this chart's own** (`group-sync-dashboard-auth-delegator`, `-login-capture-audit`, `-reader`, `-cluster-secrets`, `-grafana-discovery`, `-secrets-mint`, `-fleet-account`); User 0 |
| `rbac.ocp.io/unmanaged-exception` | 0 |
| User subject names | 16 distinct: `system:kube-scheduler` 6, `system:kube-controller-manager` 5, `system:serviceaccount:openshift-kube-apiserver:check-endpoints` 5, `jdoe` 3, and one or two each of `kubeadmin`, `system:admin`, `system:master`, `system:kube-apiserver`, `system:kube-proxy`, `ocp-oauth-bind-serviceid`, `dana.lee`, `asmith`, `bwilliams`, `tmp-contractor-9931`, `jane.smith`, `developer` |

So on the lab, after this spec: the gate is open (44 policy-operator Group rows), the chart's 7
ServiceAccount rows are `ok` by its own label, and the remaining **678 ServiceAccount and 35 User rows are
`unmanaged`** until labelled — 713 findings, listed 20 per cycle by `maxPerCycle` and counted in full on the
summary line, the tiles, the KPI page and `/metrics`. That is the capability the operator asked for; which
of them are legitimate is their decision, made by labelling.

### 2.3 The code today — every reader of the table (main `244d4ab`)

Measured by reading each file; the map is what §3 is applied against.

- **Rows in:** `kube.py#_binding_views` keeps Group subjects; `poller.py#refresh_bindings` writes them with
  `store.replace_bindings`, which diffs them into `binding_event` as `binding:Group` and replaces the
  table. The row dict carries no `audit_stamped` (the label is read and dropped).
- **The classification:** `store.py#_FINDING_CASE`, one SQL `CASE` — three resolution tiers over
  `group_state` and `managed_group_seen`, then provenance gated on a labelled binding other than the
  chart's — read by `all_bindings`, `count_bindings_by_finding`, `binding_findings`, and by the report
  snapshot's `group_bindings` and `findings_counts` through the same string.
- **Group-only readers, which must stay Group-only:** `store.group_bindings` (a group's page),
  `store.user_bindings` (a person's access through their groups, joined on `group_member`),
  `store.namespaces` (distinct groups per namespace), `store.namespace_reach` (the self-tier gate),
  `store.namespace_detail` (who reaches a namespace), `store.groups` (a group's `binding_count`), and in the
  report snapshot `binding_namespaces`,
  `groups` and `counts` — every one joins or counts by `group_name` and would silently take an account or
  a person for a group of the same name.
- **Readers of the finding, which must see every kind:** `api.py` `/api/clusters` (`unmanaged_bindings`,
  through `_binding_counts`) and `/bindings/findings`; `audit.py#plan_audit_stamps` and the poller's
  WARNING and RESOLVED lines; `metrics.py` `gsd_bindings_total`; `kpi/rollup.py` and
  `kpi/render_json.py` (`posture.bindings`); the page's Access granted tab (`bindingsPage`,
  `bindingTable`, `groupNameCell`, the export), the RBAC policy tab (`policyPage`), the Overview's
  "Bindings to review" and the KPI page's "To review"; the reports `binding-findings`
  (`snap.group_bindings`, `findings_counts`) and `compliance-snapshot` (`findings_counts`);
  `local-development/cluster-report.py` (counts only).
- **Tests that pin shapes:** `tests/test_binding_reach.py` holds `all_bindings`'s exact column set;
  `tests/test_audit_stamp.py` reads `evidence[key]["groups"]`; `tests/test_rbac.py#TestParsing` asserts
  that only Group subjects are kept; three tests pin `PRAGMA user_version` at 19; four UI assertions pin
  the tile words "Group bindings on this cluster" and "Grant a real group" and the note "grant a real
  group follow".

## 3. Design

### 3.1 The contract, in one table

| | Group subject (as today) | ServiceAccount subject (new) | User subject (new) |
|---|---|---|---|
| stored as | `subject_kind='Group'`, `subject_namespace=''`, `group_name=<name>` | `'ServiceAccount'`, the subject's namespace or the RoleBinding's, `<name>` | `'User'`, `''`, `<name>` |
| resolution tiers (`dangling`, `built_in`, `unresolved`) | as today | never — no Group object is expected | never |
| `unmanaged` | group operator-synced, no label, no exception, gate open | no label, no exception, gate open | no label, no exception, gate open |
| `ok` | otherwise | otherwise | otherwise |
| the gate | some binding on the cluster, of any kind, carries `rbac.ocp.io/config-source` ≠ `group-sync-dashboard` | same | same |
| reach (`member_count`, `logged_in_count`) | the group's | `null` | `null` |
| binding history (`binding_event`) | `binding:Group`, from this table | none | `binding:User`, from `user_binding` |
| the log line | `grants <role> to group <name>` (unchanged) | `grants <role> to ServiceAccount <namespace>/<name>` | `grants <role> to user <name>` |
| the page | a drill to the group page (ok, unmanaged, dangling) | named in full, no drill | named in full, no drill |
| Group-only readers | as today | not seen | not seen |

### 3.2 Storage and migration 20

`rbac_group_binding` gains `subject_kind TEXT NOT NULL DEFAULT 'Group'` and
`subject_namespace TEXT NOT NULL DEFAULT ''`, and its primary key becomes
`(cluster_id, binding_kind, binding_namespace, binding_name, subject_kind, subject_namespace, group_name)`.
SQLite cannot alter a primary key, so migration 20 rebuilds the table: create the new shape under a
temporary name, copy every row across as a Group subject (every row an older release wrote is one), drop
the old table, rename, recreate the index. The rows are carried rather than dropped for two reasons the
existing migration tests already state: the bindings view must not go blank until the next 300 s cycle,
and the next refresh's `binding_event` diff must see the Group rows it left — a drop would have re-recorded
every binding on the cluster as `added`. On a fresh database the SCHEMA already created the new shape and
the rebuild copies an empty table onto itself.

`replace_bindings` defaults `subject_kind` to `Group` and `subject_namespace` to `''` for a row that names
neither, so every existing caller and test seed keeps its meaning; it diffs Group rows only into
`binding_event` (the note above) and writes every row. `_OBSERVATION_SEEDS` is untouched: the `binding:Group`
marker is consumed by the refresh that observes the cluster whether or not it finds Group rows
(`docs/DESIGN_binding_events.md`, "empty or not"), so a cluster holding only account rows has observed groups
by the existing design; and migration 14 splices those seed statements into its own list, so they must stay
valid on every table shape a migration can meet — the first scratch application of this spec proved that a
`WHERE subject_kind` there fails a v0 database at migration 14 with "no such column".

### 3.3 The reader — `kube.py`

`_binding_views` keeps every subject whose kind is one of `SUBJECT_KINDS` and whose name is set. A
ServiceAccount's `subject_namespace` is the subject's own or, absent, the binding's (§2.1); User and Group
rows store `''`. `BindingView` gains the two fields with those defaults, so the positional construction in
`tests/test_rbac.py` and every keyword construction stay valid. `fetch_bindings` says what it fetched.

### 3.4 The classification — `_FINDING_CASE`

The three resolution arms apply to Group subjects only (`b.subject_kind = 'Group' AND …`); the provenance
arm requires an operator-synced group for a Group subject and nothing but the absence of a label and an
exception for the other two kinds (`(b.subject_kind <> 'Group' OR s.group_name IS NOT NULL)`); the gate is
unchanged in text and now naturally reads every kind, because the rows of every kind are in the table it
reads. The joins to `group_state` and `managed_group_seen` — and the reach join — carry
`AND b.subject_kind = 'Group'`, so a ServiceAccount or User named like a group never borrows that group's
object, its sync record or its members: an account named `app-ocp-rbac-x` is judged on provenance alone
and its reach is `null`. Nothing about a `system:` name, a namespace or a Helm, OLM or Argo CD label
enters the `CASE`: the `built_in` arm is a Group arm, so a User named `system:kube-scheduler` is
`unmanaged` when unlabelled, as the operator decided.

### 3.5 Group-only readers, guarded

Each query in §2.3's Group-only list gains `subject_kind = 'Group'` in the same clause it already filters
on. Their outputs — a group's bindings, a person's access through groups, the namespace audit's via-groups
counts, the self-tier reach gate, a group's `binding_count`, the reports' group counts — are byte-identical
before and after this spec for a table that holds Group rows only, which the existing tests hold.

### 3.6 The poller and the announcer

The row dict carries `subject_kind`, `subject_namespace` and — the adjacent fix — `audit_stamped`. The
refresh line names the kinds it read. `audit.py` gains `subject_label(row)`, the one spelling of a subject
for the log and the reports: `group <name>`, `ServiceAccount <namespace>/<name>`, `user <name>`; the plan's
evidence lists `subjects` (the `groups` list, renamed, holding those labels), only for the rows classified
`unmanaged`, as before. The WARNING line reads `grants <role> to <subjects>`, which for a Group is the same
text as today; the RESOLVED line is unchanged.

### 3.7 The API

`/bindings/findings` rows gain `subject_kind` and `subject_namespace`; `group_name` is documented as the
subject's name. The counts, `/api/clusters`'s `unmanaged_bindings` and the KPI posture count rows of every
kind through the same `CASE`. No endpoint is added: the finding is one list, and a reader who wants one
kind filters on the field.

### 3.8 The page

The Access granted tab's header says "Bindings on this cluster" and "Granted"; its note names the three
kinds; the subject column is "Subject named by the binding", rendered by `subjectCell`: a Group drills as
before, a ServiceAccount is `ServiceAccount <namespace>/<name>` and a User `user <name>`, each with the kind
in muted text before the name and no drill. Search matches the namespace too; the export carries both new
fields. The Unmanaged notes say a grant of any kind is a finding and the label or annotation on the binding
is what clears it. The RBAC policy tab's hero and tile read `counts.unmanaged`, and its list says how many
of that total it holds. The narrowed reader's own-access view, Home, the group pages and the namespace
audit are Group-only readers and do not change.

### 3.9 The reports

`_OMIT_SYSTEM_GROUP_SUBJECTS` becomes kind-aware — it drops `system:` **Group** subjects only, so a User
named `system:kube-scheduler` is not dropped as if it were a virtual group — and `_GROUP_SUBJECTS_ONLY`
guards the group counts. `Snapshot.group_bindings` takes `kinds` (default `("Group",)`, so
`namespace-access`, `privileged-access`, `access-matrix` and `access-certification` are unchanged); the
`binding-findings` report asks for every kind and names each subject with `subject_label`; its per-tier
tables' first column is "subject". `findings_counts` counts every kind, which is what
`compliance-snapshot`'s Unmanaged figure now says.

### 3.10 Metrics and KPI

`FINDINGS` gains `unmanaged`, so `gsd_bindings_total{finding="unmanaged"}` is pre-seeded at 0 like the
other tiers; the family's help text names the three kinds. No label is added (the note above). The KPI
rollup's `bindings` and the page's Bindings and To review figures count rows of every kind; on the lab the
To review figure rises by 713 the first refresh after this deploys, and that is the finding, not a
regression — the CHANGELOG entry says so.

### 3.11 Versions, chart documents, CHANGELOG, indexes

Application 0.33.0 (`pyproject.toml`, `gsd/__init__.py`, `Chart.yaml` `appVersion` with its paragraph);
chart 0.54.0 with its history line, MINOR because the appVersion moves and the chart's README and values
comment describe the finding. `docs/CHANGELOG.md` gains the entry under Unreleased.
`docs/unmanaged-audit-design.md`, `docs/reference-architecture.md`, the chart README, the values comment and
`local-development/API.md` say what the finding covers now. The index edits are the spec PR's own, not
implementation blocks: `docs/specs/README.md` gains the U1 row and SPEC_S4c's version cell moves to
app 0.34.0, chart 0.55.0 in its header and its index row, which `local-development/tests/test_specs_index.py`
holds equal and requires to sit above the tree's versions; the implementation PR moves the row's status.

## 4. Tests — what fails before and passes after

New file `local-development/tests/test_unmanaged_subjects.py`, one class per layer, each test named for its
claim; and the edits to existing tests that pin the old shape. Every test below fails on main `244d4ab`
(the attribute, column, key or word does not exist there) and passes with §7 applied.

- **The reader** (`TestReader`): every kind is kept with its kind; a RoleBinding ServiceAccount subject
  with no namespace stores the binding's; one with a namespace stores its own; a ClusterRoleBinding
  ServiceAccount stores its own; a User stores `''`; an unknown kind or an unnamed subject contributes
  nothing.
- **The classification** (`TestClassification`): an unlabelled ServiceAccount grant is `unmanaged` on a
  cluster where the policy operator is in use; the operator's label on the binding makes it `ok`; the
  exception annotation makes it `ok`; a User named `system:kube-scheduler` is `unmanaged` and never
  `built_in`; on a cluster whose only labels are the chart's, the chart's ServiceAccount rows and a
  hand-made one are all `ok` (the gate stays shut, #354) and one policy label opens it; the operator's
  label on one ServiceAccount grant opens the gate for every kind; an account named like a synced group
  is judged on provenance and its reach is `null`; `all_bindings` carries the two new columns.
- **Group-only readers** (`TestGroupOnlyReaders`): with a ServiceAccount and a User row named like a group
  present, `group_bindings`, `user_bindings`, `groups` (`binding_count`), `namespaces` (`via_groups`) and
  `namespace_reach` answer exactly as they do without them.
- **History and the store's writer** (`TestWriter`): `replace_bindings` records no `binding_event` for a
  ServiceAccount or User row and the Group diff is unaffected; a row that names no kind is stored as a
  Group.
- **Migration 20** (`TestMigration20`): a database as release 0.32.0 left it — the old table shape, one
  row, `user_version` 19 — opens with the new columns and primary key, the row surviving as a Group subject
  with its provenance, `user_version` 20, and reopening is idempotent; the report service's
  `KNOWN_SCHEMA_VERSION` is 20.
- **The announcer** (`TestAnnouncer`): `subject_label` spells the three kinds; the plan's evidence names
  a ServiceAccount subject and, on a binding naming a labelled group and an unlabelled account, only the
  account; one real `refresh_bindings` against a fake client logs
  `grants cluster-admin to ServiceAccount group-sync-operator/shared-qa-poller` for the unlabelled account,
  logs `unmanaged grant RESOLVED` for a labelled Group binding that carries the `rbac.ocp.io/unmanaged`
  label (I3: a stamped object is never re-announced, and a stamped one no longer unmanaged is resolved),
  and stores `audit_stamped` from the view — 1 for that binding, 0 for the account.
- **The API** (`TestApi`): a `/bindings/findings` row for a ServiceAccount carries `subject_kind`,
  `subject_namespace` and `member_count: null`; `/api/clusters` counts it under `unmanaged_bindings`.
- **The reports** (`TestReports`): the snapshot's `group_bindings` default omits the account, and with
  every kind lists it; `findings_counts` counts it; a `system:`-named User is not omitted; the
  `binding-findings` report's Unmanaged table names `ServiceAccount <namespace>/<name>`.
- **Metrics** (an edit in `tests/test_metrics.py`): `gsd_bindings_total{finding="unmanaged"}` is emitted
  at 0 on a cluster with none.
- **Edits to pinned shapes:** `tests/test_rbac.py#TestParsing` keeps every kind; `tests/test_binding_reach.py`
  adds the two columns to the exact set; `tests/test_audit_stamp.py` reads `evidence[key]["subjects"]`; the
  three `user_version == 19` pins read 20; `tests/test_ui.py`'s four wording assertions move with the tile
  labels, and two UI tests are added — a ServiceAccount and a User row render named in full under
  Unmanaged with no drill, and the RBAC policy tab's hero counts the cluster.

## 5. Verification on the lab

After the deploy (`local-development/release-crc.sh --argocd`, Synced/Healthy, the commit verified in-pod,
the PVC UIDs identical), with `KUBECONFIG` set to the lab's scratch kubeconfig:

1. `PRAGMA user_version` in the pod's database reads 20 (`oc exec … -- python3 -c` over `/data/gsd.db`),
   and the report pod's `/report/readyz` is 200.
2. The first refresh line reads `refreshed N bindings for dashboard (205 Group, 685 ServiceAccount, 35 User
   subjects)` give or take the day's drift, and the summary line reads `713 outside the policy system (20
   listed below, 693 held back by the per-cycle cap)` against the counts of §2.2.
3. `GET /api/clusters/dashboard/bindings/findings` as kubeadmin: `counts.unmanaged` equals the sum of
   unlabelled ServiceAccount and User rows plus any unlabelled synced-group grant; the chart's seven
   ServiceAccount rows are in `ok` with `managed_source: group-sync-dashboard`.
4. **The evidence the issue's Definition of Done names.** Plant a hand-made ServiceAccount grant
   (`oc create clusterrolebinding u1-evidence --clusterrole=view --serviceaccount=default:u1-evidence-sa`),
   wait one refresh: the WARNING names `ServiceAccount default/u1-evidence-sa`, the row is in `unmanaged`,
   the tile counts it. Label it as the operator would
   (`oc label clusterrolebinding u1-evidence rbac.ocp.io/config-source=platform-team`), wait one refresh:
   the row is `ok`, `managed_source: platform-team`, no WARNING. Remove it.
5. The Access granted page under `#page=bindings&cluster=dashboard` with the Unmanaged filter shows the
   account rows named in full; the RBAC policy page's hero equals `counts.unmanaged`; the Overview tile and
   the KPI page's To review carry the same number; `/metrics` reports
   `gsd_bindings_total{cluster="dashboard",finding="unmanaged"}` equal to it, with no name in any label.
6. The `binding-findings` report generated from the library lists the same account rows under Unmanaged.

## 6. What changes, for whom, and what it costs

- **An operator with a policy operator** (the lab): every unlabelled ServiceAccount and User grant is a
  finding from the first refresh after upgrade — 713 on the lab. The log lists 20 per cycle and counts the
  rest; the tiles, the KPI page and the metric carry the full number. The way down is the label on each
  legitimate grant, which is the operator's decision and the whole point.
- **An operator with no policy operator** (a plain host): nothing changes until they label a grant with a
  value other than the chart's; then every unlabelled grant of every kind is a finding.
- **Storage:** one row per (binding, subject) of every kind — on the lab 925 rows instead of 205, plus the
  35 User rows already held by `user_binding` — replaced every refresh as before; migration 20 rebuilds the
  table once, carrying the rows.
- **The API and the page:** two fields on every finding row; the tile words; the subject column. A reader
  of `group_name` on a row of another kind reads the subject's name, as documented.
- **The reports:** the `binding-findings` and `compliance-snapshot` figures include the new kinds; the
  group-shaped reports are unchanged.
- **The history feed and `/user-bindings`:** unchanged, by the notes above.

## 7. Implementation blocks

<!-- block: local-development/gsd/kube.py | edit -->
```python
CHART_CONFIG_SOURCE = "group-sync-dashboard"
```
```python
CHART_CONFIG_SOURCE = "group-sync-dashboard"

# The three subject kinds RBAC defines (k8s.io/api rbac/v1 types.go: GroupKind, ServiceAccountKind,
# UserKind); the API server refuses any other at admission (pkg/apis/rbac/validation,
# ValidateRoleBindingSubject). Every one is a grant the unmanaged finding reads (#353, SPEC_U1).
GROUP_KIND = "Group"
SERVICE_ACCOUNT_KIND = "ServiceAccount"
USER_KIND = "User"
SUBJECT_KINDS = (GROUP_KIND, SERVICE_ACCOUNT_KIND, USER_KIND)
```

<!-- block: local-development/gsd/kube.py | edit -->
```python
@dataclass
class BindingView:
    """One (binding, Group subject) pair.

    Flattened per subject rather than per binding: a binding naming three groups is three
    rows, which is the shape both drill-downs read it in ("which bindings name THIS
    group?"). Only ``kind: Group`` subjects are kept — User and ServiceAccount subjects
    cannot contribute to a user's access-via-groups, which is the question being answered.
    """

    binding_kind: str          # RoleBinding | ClusterRoleBinding
    binding_namespace: str     # "" for ClusterRoleBinding
    binding_name: str
    role_kind: str             # Role | ClusterRole
    role_name: str
    group_name: str
    managed_source: str | None = None
```
```python
@dataclass
class BindingView:
    """One (binding, subject) pair.

    Flattened per subject rather than per binding: a binding naming three groups is three
    rows, which is the shape both drill-downs read it in ("which bindings name THIS
    group?"). Every subject kind is kept — Group, ServiceAccount and User (#353): the unmanaged
    finding must see a hand-made grant whoever it names. The Group-only questions (a person's
    access through their groups, a group's page) filter on `subject_kind` in the store.
    """

    binding_kind: str          # RoleBinding | ClusterRoleBinding
    binding_namespace: str     # "" for ClusterRoleBinding
    binding_name: str
    role_kind: str             # Role | ClusterRole
    role_name: str
    group_name: str
    """The subject's NAME, whatever its kind. The field predates the other two kinds and every
    reader of these rows names it; `subject_kind` says what it names."""
    subject_kind: str = GROUP_KIND
    subject_namespace: str = ""
    """A ServiceAccount's namespace — the subject's own, or the RoleBinding's when the subject
    omits it, which is how the authorizer reads it (see _binding_views). "" for the other kinds."""
    managed_source: str | None = None
```

<!-- block: local-development/gsd/kube.py | edit -->
```python
    def fetch_bindings(self) -> list[BindingView]:
        """Every RoleBinding and ClusterRoleBinding subject of kind Group.

        Separate from fetch() and on its own slower cadence: this lists bindings across
        every namespace, which is far more expensive than the two list calls above, and
        bindings change on administrative action rather than on a sync schedule.
        """
        out: list[BindingView] = []
        with self._client() as client:
            for obj in self._list_all(client, ROLEBINDING_API):
                out.extend(_binding_views(obj, "RoleBinding"))
            for obj in self._list_all(client, CLUSTERROLEBINDING_API):
                out.extend(_binding_views(obj, "ClusterRoleBinding"))
        log.debug("fetched %d group-subject binding rows from %s", len(out), self.cluster.name)
        return out
```
```python
    def fetch_bindings(self) -> list[BindingView]:
        """Every RoleBinding and ClusterRoleBinding subject — Group, ServiceAccount and User.

        Separate from fetch() and on its own slower cadence: this lists bindings across
        every namespace, which is far more expensive than the two list calls above, and
        bindings change on administrative action rather than on a sync schedule.
        """
        out: list[BindingView] = []
        with self._client() as client:
            for obj in self._list_all(client, ROLEBINDING_API):
                out.extend(_binding_views(obj, "RoleBinding"))
            for obj in self._list_all(client, CLUSTERROLEBINDING_API):
                out.extend(_binding_views(obj, "ClusterRoleBinding"))
        log.debug("fetched %d binding subject rows from %s", len(out), self.cluster.name)
        return out
```

<!-- block: local-development/gsd/kube.py | edit -->
```python
def _binding_views(obj: dict, binding_kind: str) -> list[BindingView]:
    """Flatten one binding into a row per Group subject.

    Subject matching is on ``kind`` exactly. A binding with no Group subject contributes
    nothing, which is why 530 RoleBindings on the target cluster reduce to 178 rows.
    """
    meta = obj.get("metadata") or {}
    role_ref = obj.get("roleRef") or {}
    labels = meta.get("labels") or {}
    annotations = meta.get("annotations") or {}
    rows: list[BindingView] = []
    for subject in obj.get("subjects") or []:
        if subject.get("kind") != "Group" or not subject.get("name"):
            continue
        rows.append(
            BindingView(
                binding_kind=binding_kind,
                # ClusterRoleBindings have no namespace; "" rather than None so it can sit
                # in a NOT NULL primary key column without a sentinel row per binding.
                binding_namespace=meta.get("namespace", "") or "",
                binding_name=meta.get("name", ""),
                role_kind=role_ref.get("kind", ""),
                role_name=role_ref.get("name", ""),
                group_name=subject["name"],
                managed_source=labels.get(CONFIG_SOURCE_LABEL),
                exception=annotations.get(UNMANAGED_EXCEPTION_ANNOTATION),
                audit_stamped=labels.get(UNMANAGED_LABEL) == "true",
            )
        )
    return rows
```
```python
def _binding_views(obj: dict, binding_kind: str) -> list[BindingView]:
    """Flatten one binding into a row per subject, whatever its kind.

    Subject matching is on ``kind`` exactly, against the three kinds RBAC defines
    (SUBJECT_KINDS); a subject of any other kind, or with no name, contributes nothing. Every
    kind is a grant the unmanaged finding must see (#353, SPEC_U1).

    A ServiceAccount subject carries a namespace. On a ClusterRoleBinding the API server
    requires it (pkg/apis/rbac/validation/validation.go, ValidateRoleBindingSubject); on a
    RoleBinding it may be omitted, and the authorizer then reads it as the binding's own
    namespace (pkg/registry/rbac/validation/rule.go, appliesToUser: "default the namespace to
    namespace we're working in"). That resolved namespace is what is stored, so the row names
    the account RBAC actually matches — `system:serviceaccount:<namespace>:<name>`. Measured on
    the lab: 26 of 685 ServiceAccount subjects omit it, all on OLM-written RoleBindings. User and
    Group subjects have no namespace; "" is stored, as for a ClusterRoleBinding's own.
    """
    meta = obj.get("metadata") or {}
    role_ref = obj.get("roleRef") or {}
    labels = meta.get("labels") or {}
    annotations = meta.get("annotations") or {}
    # ClusterRoleBindings have no namespace; "" rather than None so it can sit in a NOT NULL
    # primary key column without a sentinel row per binding.
    binding_namespace = meta.get("namespace", "") or ""
    rows: list[BindingView] = []
    for subject in obj.get("subjects") or []:
        kind = subject.get("kind")
        if kind not in SUBJECT_KINDS or not subject.get("name"):
            continue
        rows.append(
            BindingView(
                binding_kind=binding_kind,
                binding_namespace=binding_namespace,
                binding_name=meta.get("name", ""),
                role_kind=role_ref.get("kind", ""),
                role_name=role_ref.get("name", ""),
                group_name=subject["name"],
                subject_kind=kind,
                subject_namespace=((subject.get("namespace") or binding_namespace)
                                   if kind == SERVICE_ACCOUNT_KIND else ""),
                managed_source=labels.get(CONFIG_SOURCE_LABEL),
                exception=annotations.get(UNMANAGED_EXCEPTION_ANNOTATION),
                audit_stamped=labels.get(UNMANAGED_LABEL) == "true",
            )
        )
    return rows
```

<!-- block: local-development/gsd/store.py | edit -->
```python
from .kube import CHART_CONFIG_SOURCE, SYSTEM_GROUP_PREFIX
```
```python
from .kube import CHART_CONFIG_SOURCE, GROUP_KIND, SYSTEM_GROUP_PREFIX
```

<!-- block: local-development/gsd/store.py | edit -->
```sql
-- One row per (binding, Group subject). Current state, replaced each refresh: a binding
-- is fully re-readable from the API, so nothing here is irreplaceable history.
CREATE TABLE IF NOT EXISTS rbac_group_binding (
    cluster_id          TEXT NOT NULL,
    binding_kind        TEXT NOT NULL,   -- RoleBinding | ClusterRoleBinding
    binding_namespace   TEXT NOT NULL,   -- '' for ClusterRoleBinding
    binding_name        TEXT NOT NULL,
    role_kind           TEXT NOT NULL,   -- Role | ClusterRole
    role_name           TEXT NOT NULL,
    group_name          TEXT NOT NULL,
    observed_at         TEXT NOT NULL,
```
```sql
-- One row per (binding, subject). Current state, replaced each refresh: a binding
-- is fully re-readable from the API, so nothing here is irreplaceable history.
--
-- Every subject kind RBAC defines is held — Group, ServiceAccount and User (#353, SPEC_U1,
-- migration 20) — because the unmanaged finding must see a hand-made grant whoever it names.
-- `group_name` is the subject's NAME whatever its kind: the column predates the other two
-- kinds and every reader of this table names it, so it kept its name; `subject_kind` says
-- what it names. The Group-only readers (a group's page, a person's access through groups,
-- the namespace audit, the history stream) filter on subject_kind = 'Group'.
CREATE TABLE IF NOT EXISTS rbac_group_binding (
    cluster_id          TEXT NOT NULL,
    binding_kind        TEXT NOT NULL,   -- RoleBinding | ClusterRoleBinding
    binding_namespace   TEXT NOT NULL,   -- '' for ClusterRoleBinding
    binding_name        TEXT NOT NULL,
    role_kind           TEXT NOT NULL,   -- Role | ClusterRole
    role_name           TEXT NOT NULL,
    subject_kind        TEXT NOT NULL DEFAULT 'Group',   -- Group | ServiceAccount | User
    -- A ServiceAccount's namespace: the subject's own, or the RoleBinding's when the subject
    -- omits it, which is how the authorizer reads it (kube.py _binding_views). '' otherwise.
    subject_namespace   TEXT NOT NULL DEFAULT '',
    group_name          TEXT NOT NULL,   -- the subject's name, whatever subject_kind says
    observed_at         TEXT NOT NULL,
```

<!-- block: local-development/gsd/store.py | edit -->
```sql
    audit_stamped       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(cluster_id, binding_kind, binding_namespace, binding_name, group_name)
);
```
```sql
    audit_stamped       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY(cluster_id, binding_kind, binding_namespace, binding_name,
                subject_kind, subject_namespace, group_name)
);
```

<!-- block: local-development/gsd/store.py | edit -->
```python
            "ALTER TABLE cluster ADD COLUMN credential TEXT NOT NULL DEFAULT ''",
        ],
    ),
]
```
```python
            "ALTER TABLE cluster ADD COLUMN credential TEXT NOT NULL DEFAULT ''",
        ],
    ),
    (
        20,
        "rbac_group_binding holds ServiceAccount and User subjects beside Group ones (#353, SPEC_U1)",
        [
            # A table rebuild: the primary key gains the subject's kind and namespace, and SQLite
            # cannot alter a primary key in place. The rows are carried across as Group subjects
            # (every row an older release wrote is one) rather than dropped, so the bindings view
            # is not blank until the next 300 s cycle and the next refresh's binding_event diff sees
            # the same Group rows it left — a DROP alone would have re-recorded every binding on the
            # cluster as `added`. On a fresh database the SCHEMA already created this shape and the
            # rebuild copies an empty table onto itself, which is harmless. Migrations 1 and 2 have
            # run by now, so the provenance and stamp columns exist on every source table.
            """CREATE TABLE IF NOT EXISTS rbac_group_binding_v20 (
                   cluster_id          TEXT NOT NULL,
                   binding_kind        TEXT NOT NULL,
                   binding_namespace   TEXT NOT NULL,
                   binding_name        TEXT NOT NULL,
                   role_kind           TEXT NOT NULL,
                   role_name           TEXT NOT NULL,
                   subject_kind        TEXT NOT NULL DEFAULT 'Group',
                   subject_namespace   TEXT NOT NULL DEFAULT '',
                   group_name          TEXT NOT NULL,
                   observed_at         TEXT NOT NULL,
                   managed_source      TEXT,
                   exception           TEXT,
                   audit_stamped       INTEGER NOT NULL DEFAULT 0,
                   PRIMARY KEY(cluster_id, binding_kind, binding_namespace, binding_name,
                               subject_kind, subject_namespace, group_name)
               )""",
            """INSERT INTO rbac_group_binding_v20(
                   cluster_id, binding_kind, binding_namespace, binding_name, role_kind, role_name,
                   subject_kind, subject_namespace, group_name, observed_at,
                   managed_source, exception, audit_stamped)
               SELECT cluster_id, binding_kind, binding_namespace, binding_name, role_kind, role_name,
                      'Group', '', group_name, observed_at,
                      managed_source, exception, audit_stamped
                 FROM rbac_group_binding""",
            "DROP TABLE rbac_group_binding",
            "ALTER TABLE rbac_group_binding_v20 RENAME TO rbac_group_binding",
            "CREATE INDEX IF NOT EXISTS rbac_binding_by_group ON rbac_group_binding(cluster_id, group_name)",
        ],
    ),
]
```

<!-- block: local-development/gsd/store.py | edit -->
```python
                f"""SELECT binding_namespace AS ns,
                           COUNT(DISTINCT CASE WHEN substr(group_name, 1, ?) = ? THEN NULL ELSE group_name END) AS n
                      FROM rbac_group_binding WHERE cluster_id=? AND binding_namespace != ''
```
```python
                f"""SELECT binding_namespace AS ns,
                           COUNT(DISTINCT CASE WHEN substr(group_name, 1, ?) = ? THEN NULL ELSE group_name END) AS n
                      FROM rbac_group_binding WHERE cluster_id=? AND subject_kind = 'Group' AND binding_namespace != ''
```

<!-- block: local-development/gsd/store.py | edit -->
```python
            """SELECT EXISTS(SELECT 1 FROM rbac_group_binding
                              WHERE cluster_id=? AND binding_namespace IN (?, '')
                                AND group_name IN (SELECT value FROM json_each(?)))
```
```python
            """SELECT EXISTS(SELECT 1 FROM rbac_group_binding
                              WHERE cluster_id=? AND subject_kind = 'Group' AND binding_namespace IN (?, '')
                                AND group_name IN (SELECT value FROM json_each(?)))
```

<!-- block: local-development/gsd/store.py | edit -->
```python
                         WHERE b.cluster_id=? AND b.binding_namespace=?{own_groups}
                         ORDER BY b.role_name, b.group_name""",
```
```python
                         WHERE b.cluster_id=? AND b.subject_kind = 'Group' AND b.binding_namespace=?{own_groups}
                         ORDER BY b.role_name, b.group_name""",
```

<!-- block: local-development/gsd/store.py | edit -->
```python
        with self._write() as conn:
            changes = self._append_binding_events(
                conn, cluster_id, "Group", "group_name",
                current=conn.execute(
                    """SELECT binding_kind, binding_namespace, binding_name, group_name AS subject,
                              role_kind, role_name, 0 AS is_platform
                         FROM rbac_group_binding WHERE cluster_id=?""", (cluster_id,)).fetchall(),
                incoming=rows, observed_at=observed_at,
            )
            conn.execute("DELETE FROM rbac_group_binding WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT OR REPLACE INTO rbac_group_binding(
                       cluster_id, binding_kind, binding_namespace, binding_name,
                       role_kind, role_name, group_name, observed_at,
                       managed_source, exception, audit_stamped)
                   VALUES(:cluster_id,:binding_kind,:binding_namespace,:binding_name,
                          :role_kind,:role_name,:group_name,:observed_at,
                          :managed_source,:exception,:audit_stamped)""",
                [{"managed_source": None, "exception": None, "audit_stamped": 0, **r,
                  "cluster_id": cluster_id, "observed_at": observed_at} for r in rows],
            )
        return changes
```
```python
        # Every row is a subject of some kind. A caller that names no kind wrote a Group row —
        # every caller before #353 did, and the test seeds still do — so the defaults keep that
        # meaning rather than making every one of them say it.
        rows = [{"subject_kind": GROUP_KIND, "subject_namespace": "", "managed_source": None,
                 "exception": None, "audit_stamped": 0, **r} for r in rows]
        with self._write() as conn:
            # The history stream stays the Group subjects' (binding:Group). User subjects are
            # recorded by replace_user_bindings from the same bindings under binding:User, and a
            # second recording here would double every one of them; ServiceAccount subjects have
            # no stream (docs/DESIGN_binding_events.md bounds subject_kind at two), a decision
            # SPEC_U1 states rather than widens here.
            changes = self._append_binding_events(
                conn, cluster_id, "Group", "group_name",
                current=conn.execute(
                    """SELECT binding_kind, binding_namespace, binding_name, group_name AS subject,
                              role_kind, role_name, 0 AS is_platform
                         FROM rbac_group_binding WHERE cluster_id=? AND subject_kind = 'Group'""",
                    (cluster_id,)).fetchall(),
                incoming=[r for r in rows if r["subject_kind"] == GROUP_KIND], observed_at=observed_at,
            )
            conn.execute("DELETE FROM rbac_group_binding WHERE cluster_id=?", (cluster_id,))
            conn.executemany(
                """INSERT OR REPLACE INTO rbac_group_binding(
                       cluster_id, binding_kind, binding_namespace, binding_name,
                       role_kind, role_name, subject_kind, subject_namespace, group_name, observed_at,
                       managed_source, exception, audit_stamped)
                   VALUES(:cluster_id,:binding_kind,:binding_namespace,:binding_name,
                          :role_kind,:role_name,:subject_kind,:subject_namespace,:group_name,:observed_at,
                          :managed_source,:exception,:audit_stamped)""",
                [{**r, "cluster_id": cluster_id, "observed_at": observed_at} for r in rows],
            )
        return changes
```

<!-- block: local-development/gsd/store.py | edit -->
```python
            """SELECT binding_kind, binding_namespace, binding_name, role_kind, role_name
                 FROM rbac_group_binding
                WHERE cluster_id=? AND group_name=?
                ORDER BY binding_kind, binding_namespace, binding_name""",
```
```python
            """SELECT binding_kind, binding_namespace, binding_name, role_kind, role_name
                 FROM rbac_group_binding
                WHERE cluster_id=? AND subject_kind = 'Group' AND group_name=?
                ORDER BY binding_kind, binding_namespace, binding_name""",
```

<!-- block: local-development/gsd/store.py | edit -->
```python
                 JOIN rbac_group_binding b
                   ON b.cluster_id = m.cluster_id AND b.group_name = m.group_name
                WHERE m.cluster_id=? AND m.user_name=?
```
```python
                 JOIN rbac_group_binding b
                   ON b.cluster_id = m.cluster_id AND b.group_name = m.group_name
                  AND b.subject_kind = 'Group'
                WHERE m.cluster_id=? AND m.user_name=?
```

<!-- block: local-development/gsd/store.py | edit -->
```python
        """Classify every binding whose Group subject has no Group object.
```
```python
        """Every classified binding that is not `ok`: a Group subject with no Group object, or a
        grant outside the policy system, whoever it names (#353).
```

<!-- block: local-development/gsd/store.py | edit -->
```python
    _FINDING_CASE = """
                      CASE
                        -- Broken-resolution tiers first: a binding that grants NOBODY is
                        -- worse than one that grants outside governance, whoever made it.
                        WHEN g.name IS NULL AND s.group_name IS NOT NULL
                                                           THEN 'dangling'
                        WHEN g.name IS NULL AND b.group_name LIKE 'system:%'
                                                           THEN 'built_in'
                        WHEN g.name IS NULL                THEN 'unresolved'
                        -- The group resolves. Now provenance: an operator-SYNCED group
                        -- granted access by a binding NO policy system manages is somebody
                        -- bypassing governance by hand. Requires the policy operator to be
                        -- in use at all (any managed binding on the cluster), or every
                        -- binding on a cluster that has never heard of config-source
                        -- labels would flag. This chart's own label is not that evidence:
                        -- its auditor binding is on every host by default (#312). An
                        -- exception annotation on the binding acknowledges a deliberate
                        -- one and suppresses the finding.
                        WHEN b.managed_source IS NULL
                             AND b.exception IS NULL
                             AND s.group_name IS NOT NULL
                             AND EXISTS (SELECT 1 FROM rbac_group_binding m
                                          WHERE m.cluster_id = b.cluster_id
                                            AND m.managed_source IS NOT NULL
                                            AND m.managed_source <> '""" + CHART_CONFIG_SOURCE + """')
                                                           THEN 'unmanaged'
                        ELSE 'ok'
                      END"""
```
```python
    _FINDING_CASE = """
                      CASE
                        -- Broken-resolution tiers first, for Group subjects: a binding that
                        -- grants NOBODY is worse than one that grants outside governance,
                        -- whoever made it. A ServiceAccount or User subject has no Group
                        -- object to resolve, so these three arms never apply to it (#353);
                        -- the joins below already never match it.
                        WHEN b.subject_kind = 'Group' AND g.name IS NULL AND s.group_name IS NOT NULL
                                                           THEN 'dangling'
                        WHEN b.subject_kind = 'Group' AND g.name IS NULL AND b.group_name LIKE 'system:%'
                                                           THEN 'built_in'
                        WHEN b.subject_kind = 'Group' AND g.name IS NULL
                                                           THEN 'unresolved'
                        -- Provenance: a grant NO policy system manages is somebody bypassing
                        -- governance by hand. For a Group subject that is only worth saying
                        -- when the group is operator-SYNCED; for a ServiceAccount or a User it
                        -- is said whenever the binding carries no label and no exception —
                        -- nothing about how the grant was applied (a `system:` name, a platform
                        -- namespace, a Helm, OLM or Argo CD label) excludes it, only the
                        -- operator's decision on the binding does (#353, SPEC_U1). Requires the
                        -- policy operator to be in use at all — some labelled binding of any
                        -- kind on the cluster — or every binding on a cluster that has never
                        -- heard of config-source labels would flag. This chart's own label is
                        -- not that evidence: its auditor binding is on every host by default
                        -- (#312). An exception annotation on the binding acknowledges a
                        -- deliberate one and suppresses the finding.
                        WHEN b.managed_source IS NULL
                             AND b.exception IS NULL
                             AND (b.subject_kind <> 'Group' OR s.group_name IS NOT NULL)
                             AND EXISTS (SELECT 1 FROM rbac_group_binding m
                                          WHERE m.cluster_id = b.cluster_id
                                            AND m.managed_source IS NOT NULL
                                            AND m.managed_source <> '""" + CHART_CONFIG_SOURCE + """')
                                                           THEN 'unmanaged'
                        ELSE 'ok'
                      END"""
```

<!-- block: local-development/gsd/store.py | edit -->
```python
    _FINDING_JOINS = """
                 FROM rbac_group_binding b
                 LEFT JOIN group_state g
                        ON g.cluster_id = b.cluster_id AND g.name = b.group_name
                 LEFT JOIN managed_group_seen s
                        ON s.cluster_id = b.cluster_id AND s.group_name = b.group_name"""
```
```python
    # Group objects, sync records and members are joined to Group subjects only: an account or a
    # person named like a group must not borrow that group's object, its provenance or its reach.
    _FINDING_JOINS = """
                 FROM rbac_group_binding b
                 LEFT JOIN group_state g
                        ON g.cluster_id = b.cluster_id AND g.name = b.group_name
                       AND b.subject_kind = 'Group'
                 LEFT JOIN managed_group_seen s
                        ON s.cluster_id = b.cluster_id AND s.group_name = b.group_name
                       AND b.subject_kind = 'Group'"""
```

<!-- block: local-development/gsd/store.py | edit -->
```python
                        ON li.cluster_id = b.cluster_id AND li.group_name = b.group_name
                 LEFT JOIN ocp_user_status ust
```
```python
                        ON li.cluster_id = b.cluster_id AND li.group_name = b.group_name
                       AND b.subject_kind = 'Group'
                 LEFT JOIN ocp_user_status ust
```

<!-- block: local-development/gsd/store.py | edit -->
```python
        """Every group-subject binding, each classified.
```
```python
        """Every binding subject, each classified — one row per (binding, subject) of every kind.
```

<!-- block: local-development/gsd/store.py | edit -->
```python
        sql = ("""SELECT b.binding_kind, b.binding_namespace, b.binding_name,
                      b.role_kind, b.role_name, b.group_name,
                      b.managed_source, b.exception, b.audit_stamped,""" + reach_cols
```
```python
        sql = ("""SELECT b.binding_kind, b.binding_namespace, b.binding_name,
                      b.role_kind, b.role_name, b.subject_kind, b.subject_namespace, b.group_name,
                      b.managed_source, b.exception, b.audit_stamped,""" + reach_cols
```

<!-- block: local-development/gsd/store.py | edit -->
```python
        grants = """(SELECT COUNT(*) FROM rbac_group_binding b
                      WHERE b.cluster_id = g.cluster_id AND b.group_name = g.name) AS binding_count"""
```
```python
        grants = """(SELECT COUNT(*) FROM rbac_group_binding b
                      WHERE b.cluster_id = g.cluster_id AND b.subject_kind = 'Group'
                        AND b.group_name = g.name) AS binding_count"""
```

<!-- block: local-development/gsd/audit.py | edit -->
```python
@dataclass(frozen=True)
class StampPlan:
```
```python
def subject_label(row: dict) -> str:
    """One binding row's subject as the log and the reports name it: `group <name>`,
    `ServiceAccount <namespace>/<name>` or `user <name>` (#353).

    One spelling, so a reader greps the poller's WARNING, a report and a test for the same
    words. `group_name` is the subject's name whatever its kind — the column predates the other
    two kinds — and a row that carries no kind is a Group row, as every row was before #353.
    """
    kind = row.get("subject_kind") or "Group"
    name = row.get("group_name") or ""
    if kind == "ServiceAccount":
        return f"ServiceAccount {row.get('subject_namespace') or ''}/{name}"
    if kind == "User":
        return f"user {name}"
    return f"group {name}"


@dataclass(frozen=True)
class StampPlan:
```

<!-- block: local-development/gsd/audit.py | edit -->
```python
    # Exists so a log line can stand alone as evidence. "ClusterRoleBinding
    # -/demo-cluster-admin-crb" tells a reader which object and nothing about why it matters;
    # naming the role and the group makes the line actionable without opening the dashboard,
    # which is the whole point of publishing the discovery rather than stamping it.
    evidence: dict[tuple[str, str, str], dict] = field(default_factory=dict)
```
```python
    # Exists so a log line can stand alone as evidence. "ClusterRoleBinding
    # -/demo-cluster-admin-crb" tells a reader which object and nothing about why it matters;
    # naming the role and the subjects (`role`, `subjects` — each spelt by subject_label) makes
    # the line actionable without opening the dashboard, which is the whole point of publishing
    # the discovery rather than stamping it.
    evidence: dict[tuple[str, str, str], dict] = field(default_factory=dict)
```

<!-- block: local-development/gsd/audit.py | edit -->
```python
    `rows` is store.all_bindings() output: one row per (binding, Group subject), so a
    binding naming two groups appears twice — and its two rows can be classified
    DIFFERENTLY (one subject's group managed, the other built-in). Decisions are therefore
    made per OBJECT, not per row:
```
```python
    `rows` is store.all_bindings() output: one row per (binding, subject) of any kind, so a
    binding naming two subjects appears twice — and its two rows can be classified
    DIFFERENTLY (one subject's group managed, the other built-in). Decisions are therefore
    made per OBJECT, not per row:
```

<!-- block: local-development/gsd/audit.py | edit -->
```python
        entry = per_object.setdefault(
            key, {"unmanaged": False, "stamped": False, "role": None, "groups": set()})
        entry["stamped"] = entry["stamped"] or bool(row.get("audit_stamped"))
        # A binding has ONE roleRef, so every row for an object agrees about the role; the
        # first non-empty value is the answer rather than a set to reconcile.
        entry["role"] = entry["role"] or row.get("role_name")
        if row["finding"] == "unmanaged":
            entry["unmanaged"] = True
            # Only the groups whose rows were classified unmanaged. A binding naming two
            # groups can have one managed and one not, and reporting the managed one as
            # evidence would send a reader to look at a grant that is fine.
            if row.get("group_name"):
                entry["groups"].add(row["group_name"])
```
```python
        entry = per_object.setdefault(
            key, {"unmanaged": False, "stamped": False, "role": None, "subjects": set()})
        entry["stamped"] = entry["stamped"] or bool(row.get("audit_stamped"))
        # A binding has ONE roleRef, so every row for an object agrees about the role; the
        # first non-empty value is the answer rather than a set to reconcile.
        entry["role"] = entry["role"] or row.get("role_name")
        if row["finding"] == "unmanaged":
            entry["unmanaged"] = True
            # Only the subjects whose rows were classified unmanaged. A binding naming two
            # subjects can have one managed and one not, and reporting the managed one as
            # evidence would send a reader to look at a grant that is fine.
            if row.get("group_name"):
                entry["subjects"].add(subject_label(row))
```

<!-- block: local-development/gsd/audit.py | edit -->
```python
    evidence = {
        key: {"role": per_object[key]["role"],
              "groups": sorted(per_object[key]["groups"])}
        for key in list(stamp) + list(unstamp)
    }
```
```python
    evidence = {
        key: {"role": per_object[key]["role"],
              "subjects": sorted(per_object[key]["subjects"])}
        for key in list(stamp) + list(unstamp)
    }
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
from .kube import AUTH_FAILED, OK, UNREACHABLE, ClusterClient, ClusterError, GroupSyncView, GroupView, dn_equal
```
```python
from .kube import (AUTH_FAILED, OK, SUBJECT_KINDS, UNREACHABLE, ClusterClient, ClusterError, GroupSyncView,
                   GroupView, dn_equal)
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
        [
            {
                "binding_kind": b.binding_kind,
                "binding_namespace": b.binding_namespace,
                "binding_name": b.binding_name,
                "role_kind": b.role_kind,
                "role_name": b.role_name,
                "group_name": b.group_name,
                "managed_source": b.managed_source,
                "exception": b.exception,
            }
            for b in bindings
        ],
```
```python
        [
            {
                "binding_kind": b.binding_kind,
                "binding_namespace": b.binding_namespace,
                "binding_name": b.binding_name,
                "role_kind": b.role_kind,
                "role_name": b.role_name,
                "subject_kind": b.subject_kind,
                "subject_namespace": b.subject_namespace,
                "group_name": b.group_name,
                "managed_source": b.managed_source,
                "exception": b.exception,
                # Read from the object's rbac.ocp.io/unmanaged label by kube.py and, until
                # SPEC_U1, dropped here: every live row stored 0, so the RESOLVED line never
                # fired from live data and the RBAC policy page's Audit-stamped tile read 0.
                "audit_stamped": 1 if b.audit_stamped else 0,
            }
            for b in bindings
        ],
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
    log.info("refreshed %d group bindings for %s", len(bindings), cluster.name)
```
```python
    by_kind = {kind: sum(1 for b in bindings if b.subject_kind == kind) for kind in SUBJECT_KINDS}
    log.info("refreshed %d bindings for %s (%d Group, %d ServiceAccount, %d User subjects)",
             len(bindings), cluster.name, by_kind["Group"], by_kind["ServiceAccount"], by_kind["User"])
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
            evidence = plan.evidence.get(key, {})
            groups = evidence.get("groups") or []
```
```python
            evidence = plan.evidence.get(key, {})
            subjects = evidence.get("subjects") or []
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
            log.warning(
                "UNMANAGED GRANT DISCOVERED — %s: %s %s grants %s to group %s, "
                "outside the policy system (no config-source label, no exception annotation)",
                cluster.name, kind,
                f"{ns}/{name}" if ns else f"{name} (cluster-wide)",
                evidence.get("role") or "an unknown role",
                ", ".join(groups) if groups else "an operator-synced group",
            )
```
```python
            # `subjects` are spelt by audit.subject_label — `group <name>`, `ServiceAccount
            # <namespace>/<name>`, `user <name>` — so a Group finding reads exactly as it did
            # before #353 and the other kinds say what they are.
            log.warning(
                "UNMANAGED GRANT DISCOVERED — %s: %s %s grants %s to %s, "
                "outside the policy system (no config-source label, no exception annotation)",
                cluster.name, kind,
                f"{ns}/{name}" if ns else f"{name} (cluster-wide)",
                evidence.get("role") or "an unknown role",
                ", ".join(subjects) if subjects else "a subject outside the policy system",
            )
```

<!-- block: local-development/gsd/metrics.py | edit -->
```python
FINDINGS = ("ok", "dangling", "unresolved", "built_in")
```
```python
# Every tier Store._FINDING_CASE names, so each is pre-seeded at 0 and a series never vanishes
# when its count does. `unmanaged` was missing until SPEC_U1 and appeared only while such rows
# existed, which breaks `by (finding)` aggregation and hides a count going to zero.
FINDINGS = ("ok", "dangling", "unresolved", "built_in", "unmanaged")
```

<!-- block: local-development/gsd/metrics.py | edit -->
```python
        bindings = GaugeMetricFamily(
            "gsd_bindings_total",
            "Group-subject RoleBindings/ClusterRoleBindings by finding. "
            "finding=dangling means the binding grants nobody.",
            labels=["cluster", "finding"],
        )
```
```python
        bindings = GaugeMetricFamily(
            "gsd_bindings_total",
            "RoleBinding/ClusterRoleBinding subjects of every kind (Group, ServiceAccount, User) "
            "by finding. finding=dangling means the binding grants nobody; finding=unmanaged means "
            "a grant outside the policy system, whoever it names.",
            labels=["cluster", "finding"],
        )
```

<!-- block: local-development/gsd/api.py | edit -->
```python
            # A grant of a synced group made outside the policy system: a review item beside the two
            # that grant nobody, so a cluster's "Bindings to review" counts it (#347).
```
```python
            # A grant made outside the policy system — to a synced group, a ServiceAccount or a user
            # (#353): a review item beside the two that grant nobody, so a cluster's "Bindings to
            # review" counts it (#347).
```

<!-- block: local-development/gsd/api.py | edit -->
```python
        """Every group-subject binding on a cluster, classified into five tiers.
```
```python
        """Every binding subject on a cluster — Group, ServiceAccount and User — classified into
        five tiers. Each row carries `subject_kind` and `subject_namespace` (a ServiceAccount's; ''
        otherwise); `group_name` is the subject's name whatever its kind (#353, SPEC_U1). The three
        resolution tiers are Group tiers; a ServiceAccount or User row is `unmanaged` or `ok`.
```

<!-- block: local-development/gsd/kpi/render_json.py | edit -->
```python
        # Every tier _FINDING_CASE names, `unmanaged` included: the page's Bindings figure is the
        # cluster's group bindings less the built-in ones, and a tier left out here left a hand-made
        # grant out of that count (measured: 3 of 4 on the UI seed).
```
```python
        # Every tier _FINDING_CASE names, `unmanaged` included: the page's Bindings figure is the
        # cluster's classified bindings — subjects of every kind since #353 — less the built-in
        # ones, and a tier left out here left a hand-made grant out of that count (measured: 3 of 4
        # on the UI seed).
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
#: Report-only: drop system:* GROUP subjects (the Store's built_in arm,
#: `g.name IS NULL AND b.group_name LIKE 'system:%'`). They stay in the copy so
#: the RBAC-policy tab and unmanaged-audit still see them; reports must not list
#: them as a person's grant or as unmanaged/handmade (#147). Same LIKE as the CASE.
_OMIT_SYSTEM_GROUP_SUBJECTS = " AND b.group_name NOT LIKE 'system:%'"
```
```python
#: Report-only: drop system:* GROUP subjects (the Store's built_in arm,
#: `g.name IS NULL AND b.group_name LIKE 'system:%'`). They stay in the copy so
#: the RBAC-policy tab and unmanaged-audit still see them; reports must not list
#: them as a person's grant or as unmanaged/handmade (#147). Same LIKE as the CASE.
#: Group subjects ONLY: a User named `system:kube-scheduler` is not a virtual group, and
#: nothing about its name excludes it from the unmanaged finding (#353, SPEC_U1).
_OMIT_SYSTEM_GROUP_SUBJECTS = " AND NOT (b.subject_kind = 'Group' AND b.group_name LIKE 'system:%')"
#: The group-shaped reads (a namespace's groups, a group's binding count): Group subjects only.
_GROUP_SUBJECTS_ONLY = " AND b.subject_kind = 'Group'"
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
                 FROM (SELECT CASE WHEN b.binding_namespace='' THEN ? ELSE b.binding_namespace END AS ns, 1 AS g, 0 AS u
                         FROM rbac_group_binding b WHERE b.cluster_id=?"""
            + _OMIT_SYSTEM_GROUP_SUBJECTS + """
```
```python
                 FROM (SELECT CASE WHEN b.binding_namespace='' THEN ? ELSE b.binding_namespace END AS ns, 1 AS g, 0 AS u
                         FROM rbac_group_binding b WHERE b.cluster_id=?"""
            + _GROUP_SUBJECTS_ONLY + _OMIT_SYSTEM_GROUP_SUBJECTS + """
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
    def group_bindings(self, cluster_id: str, namespaces: list[str] | None = None) -> list[dict]:
        """Group-subject bindings a report may list, classified by the dashboard's own CASE, with reach.

        `system:*` virtual groups are omitted here (see `_OMIT_SYSTEM_GROUP_SUBJECTS`). The CASE is
        still Store._FINDING_CASE — a remaining row cannot disagree with the RBAC-policy tab.
        Ordered namespace, finding severity, group, binding — deterministic so two reports diff cleanly."""
        reach = """
                      CASE WHEN g.name IS NULL THEN NULL ELSE COALESCE(li.member_count, 0) END AS member_count,
                      CASE WHEN g.name IS NULL OR ust.cluster_id IS NULL THEN NULL
                           ELSE COALESCE(li.logged_in_count, 0) END AS logged_in_count,"""
        sql = ("""SELECT b.binding_kind, b.binding_namespace, b.binding_name, b.role_kind, b.role_name,
                         b.group_name, b.managed_source, b.exception,""" + reach
               + Store._FINDING_CASE + " AS finding"
               + Store._FINDING_JOINS + Store._REACH_JOIN + Store._FINDING_WHERE
               + _OMIT_SYSTEM_GROUP_SUBJECTS)
        params: list = [cluster_id]
        if namespaces is not None:
```
```python
    def group_bindings(self, cluster_id: str, namespaces: list[str] | None = None, *,
                       kinds: tuple[str, ...] = ("Group",)) -> list[dict]:
        """Bindings a report may list, classified by the dashboard's own CASE, with reach.

        `kinds` is the subject kinds to list: Group only by default, which is what the group-shaped
        reports (namespace access, privileged access, the matrix, the certification) want; the
        binding-findings report asks for every kind, because a ServiceAccount or User grant outside
        the policy system is a finding too (#353, SPEC_U1). A row of another kind carries
        `subject_kind`, `subject_namespace` and null reach.

        `system:*` virtual groups are omitted here (see `_OMIT_SYSTEM_GROUP_SUBJECTS`). The CASE is
        still Store._FINDING_CASE — a remaining row cannot disagree with the RBAC-policy tab.
        Ordered namespace, finding severity, subject, binding — deterministic so two reports diff cleanly."""
        reach = """
                      CASE WHEN g.name IS NULL THEN NULL ELSE COALESCE(li.member_count, 0) END AS member_count,
                      CASE WHEN g.name IS NULL OR ust.cluster_id IS NULL THEN NULL
                           ELSE COALESCE(li.logged_in_count, 0) END AS logged_in_count,"""
        sql = ("""SELECT b.binding_kind, b.binding_namespace, b.binding_name, b.role_kind, b.role_name,
                         b.subject_kind, b.subject_namespace, b.group_name, b.managed_source, b.exception,""" + reach
               + Store._FINDING_CASE + " AS finding"
               + Store._FINDING_JOINS + Store._REACH_JOIN + Store._FINDING_WHERE
               + _OMIT_SYSTEM_GROUP_SUBJECTS
               + " AND b.subject_kind IN (" + ",".join("?" * len(kinds)) + ")")
        params: list = [cluster_id, *kinds]
        if namespaces is not None:
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
                      (SELECT COUNT(*) FROM rbac_group_binding b WHERE b.cluster_id = g.cluster_id AND b.group_name = g.name) AS bindings
```
```python
                      (SELECT COUNT(*) FROM rbac_group_binding b WHERE b.cluster_id = g.cluster_id AND b.subject_kind = 'Group' AND b.group_name = g.name) AS bindings
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
            "group_bindings": one("SELECT COUNT(*) AS n FROM rbac_group_binding b WHERE b.cluster_id=?"
                                  + _OMIT_SYSTEM_GROUP_SUBJECTS),
```
```python
            "group_bindings": one("SELECT COUNT(*) AS n FROM rbac_group_binding b WHERE b.cluster_id=?"
                                  + _GROUP_SUBJECTS_ONLY + _OMIT_SYSTEM_GROUP_SUBJECTS),
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
                "SELECT b.binding_namespace FROM rbac_group_binding b"
                " WHERE b.cluster_id=? AND b.binding_namespace<>''"
                + _OMIT_SYSTEM_GROUP_SUBJECTS
```
```python
                "SELECT b.binding_namespace FROM rbac_group_binding b"
                " WHERE b.cluster_id=? AND b.binding_namespace<>''"
                + _GROUP_SUBJECTS_ONLY + _OMIT_SYSTEM_GROUP_SUBJECTS
```

<!-- block: local-development/gsd/reporting/catalogue/binding_findings.py | edit -->
```python
from ..model import KeyValues, Note, Section, Table
from ..snapshot import Snapshot
from .common import Built, ReportSpec, RunContext, cut, ns_label

SPEC = ReportSpec(
    name="binding-findings", title="RBAC binding findings",
    summary="Dangling, unresolved and unmanaged group bindings and direct user grants; system:* virtual groups are omitted (a platform built-in, not a person's grant).",
    values_key="bindingFindings",
)

_DEFINITIONS = [
    ("dangling", "the group was observed operator-managed and is now absent — something broke; the binding grants nobody"),
    ("unresolved", "the group has never been seen managed and does not exist — the binding names something that never existed"),
    ("unmanaged", "a synced group granted by a binding no policy operator manages, with no exception annotation — governance bypassed by hand"),
    ("ok", "resolves normally"),
]


def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    counts = snap.findings_counts(cid)
    rows = snap.group_bindings(cid)
```
```python
from ...audit import subject_label
from ...kube import SUBJECT_KINDS
from ..model import KeyValues, Note, Section, Table
from ..snapshot import Snapshot
from .common import Built, ReportSpec, RunContext, cut, ns_label

SPEC = ReportSpec(
    name="binding-findings", title="RBAC binding findings",
    summary="Dangling, unresolved and unmanaged bindings — the subject a group, a ServiceAccount or a user — and direct user grants; system:* virtual groups are omitted (a platform built-in, not a person's grant).",
    values_key="bindingFindings",
)

_DEFINITIONS = [
    ("dangling", "the group was observed operator-managed and is now absent — something broke; the binding grants nobody"),
    ("unresolved", "the group has never been seen managed and does not exist — the binding names something that never existed"),
    ("unmanaged", "a grant no policy operator manages, with no exception annotation — a synced group, a ServiceAccount or a user granted by hand; governance bypassed"),
    ("ok", "resolves normally, or carries the policy system's label"),
]


def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    counts = snap.findings_counts(cid)
    # Every subject kind: a ServiceAccount or User grant outside the policy system is a finding
    # (#353); the group-shaped reports keep the Group default.
    rows = snap.group_bindings(cid, kinds=SUBJECT_KINDS)
```

<!-- block: local-development/gsd/reporting/catalogue/binding_findings.py | edit -->
```python
        sections.append(Section(f"{tier.capitalize()} bindings", [Table(
            tier, ["group", "scope", "role", "binding", "kind", "source", "exception"],
            [[r["group_name"], ns_label(r["binding_namespace"]), f"{r['role_kind']}/{r['role_name']}", r["binding_name"], r["binding_kind"],
              r["managed_source"] or "hand-made", r["exception"] or ""] for r in tier_rows],
            empty_text=f"no {tier} bindings")], page_break=True))
    exceptions = [r for r in rows if r["exception"]]
    sections.append(Section("Acknowledged exceptions", [Table(
        "Bindings carrying rbac.ocp.io/unmanaged-exception", ["group", "scope", "role", "binding", "exception"],
        [[r["group_name"], ns_label(r["binding_namespace"]), r["role_name"], r["binding_name"], r["exception"]] for r in exceptions],
```
```python
        sections.append(Section(f"{tier.capitalize()} bindings", [Table(
            tier, ["subject", "scope", "role", "binding", "kind", "source", "exception"],
            [[subject_label(r), ns_label(r["binding_namespace"]), f"{r['role_kind']}/{r['role_name']}", r["binding_name"], r["binding_kind"],
              r["managed_source"] or "hand-made", r["exception"] or ""] for r in tier_rows],
            empty_text=f"no {tier} bindings")], page_break=True))
    exceptions = [r for r in rows if r["exception"]]
    sections.append(Section("Acknowledged exceptions", [Table(
        "Bindings carrying rbac.ocp.io/unmanaged-exception", ["subject", "scope", "role", "binding", "exception"],
        [[subject_label(r), ns_label(r["binding_namespace"]), r["role_name"], r["binding_name"], r["exception"]] for r in exceptions],
```

<!-- block: local-development/gsd/reporting/catalogue/common.py | edit -->
```python
            "unmanaged": "UNMANAGED — synced group granted by hand, no policy operator source",
```
```python
            "unmanaged": "UNMANAGED — granted by hand (a synced group, a ServiceAccount or a user), no policy operator source",
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
function bindingMatches(r, q) {
  return matchesSearch([r.group_name, r.role_name, r.binding_namespace, r.binding_name], q);
}
```
```javascript
function bindingMatches(r, q) {
  return matchesSearch([r.group_name, r.subject_namespace, r.role_name, r.binding_namespace, r.binding_name], q);
}
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
    return refusalCard("Access granted",
      `Every group-subject binding on this cluster — who has been granted what — is the
       cluster's RBAC surface.`);
```
```javascript
    return refusalCard("Access granted",
      `Every binding on this cluster — who has been granted what — is the
       cluster's RBAC surface.`);
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
      <div class="kpi"><div class="label">Group bindings on this cluster</div>
        <div class="value">${d.total || 0}</div></div>
      <div class="kpi"><div class="label">Grant a real group</div>
        <div class="value muted">${c.ok || 0}</div></div>
```
```javascript
      <div class="kpi"><div class="label">Bindings on this cluster</div>
        <div class="value">${d.total || 0}</div></div>
      <div class="kpi"><div class="label">Granted</div>
        <div class="value muted">${c.ok || 0}</div></div>
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
    <div class="filterbar-note mt-5">
      Direct RoleBindings and ClusterRoleBindings whose subject is a Group. Role rules are
      <strong>not</strong> evaluated, so this is what has been granted, not a computed list
      of permitted actions.
    </div>
```
```javascript
    <div class="filterbar-note mt-5">
      Direct RoleBindings and ClusterRoleBindings, one row per subject — a Group, a
      ServiceAccount or a User. Role rules are <strong>not</strong> evaluated, so this is what
      has been granted, not a computed list of permitted actions.
    </div>
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
          <strong>${d.total || 0}</strong> group bindings, by group name; the cluster has more. The
          Find box and the sort work only over these, so a binding past the cut cannot be found here.</div>` : ""}
    ${searching ? `<div class="filterbar-note mt-3" id="binding-search-note">Filtered by
      <strong>${esc(q.trim())}</strong> — every word must appear in the group, role, namespace or binding
      name. ${visible.reduce((n, t) => n + f[t].length, 0)} of
```
```javascript
          <strong>${d.total || 0}</strong> bindings, by subject name; the cluster has more. The
          Find box and the sort work only over these, so a binding past the cut cannot be found here.</div>` : ""}
    ${searching ? `<div class="filterbar-note mt-3" id="binding-search-note">Filtered by
      <strong>${esc(q.trim())}</strong> — every word must appear in the subject, role, namespace or binding
      name. ${visible.reduce((n, t) => n + f[t].length, 0)} of
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  if (view.bindingFilter === "unmanaged") {
    return header + bindingSection("Unmanaged",
      `The group is operator-synced, other bindings on this cluster carry the policy
       operator's <code>config-source</code> label, and this one carries none — somebody
       granted access by hand, outside the policy system. A deliberate one can be
       acknowledged with the <code>rbac.ocp.io/unmanaged-exception</code> annotation on the
       binding itself, which records the justification next to the object and clears it
       from this list.`,
      f.unmanaged, sevBadge("warning", "unmanaged"));
  }
```
```javascript
  if (view.bindingFilter === "unmanaged") {
    return header + bindingSection("Unmanaged",
      `Other bindings on this cluster carry the policy system's
       <code>rbac.ocp.io/config-source</code> label and this one carries none — a grant to an
       operator-synced group, a ServiceAccount or a user, made by hand outside the policy system.
       Nothing about how it was applied excludes it; a legitimate one is silenced by labelling the
       binding with <code>rbac.ocp.io/config-source</code>, as the platform's own grants are, or
       acknowledged with the <code>rbac.ocp.io/unmanaged-exception</code> annotation, which records
       the justification next to the object. Either clears it from this list.`,
      f.unmanaged, sevBadge("warning", "unmanaged"));
  }
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
      + bindingSection("Unmanaged", "Hand-made grant on an operator-synced group, outside the "
          + "policy system.", f.unmanaged, sevBadge("warning", "unmanaged"))
```
```javascript
      + bindingSection("Unmanaged", "Hand-made grant — to a synced group, a ServiceAccount or a user — "
          + "outside the policy system.", f.unmanaged, sevBadge("warning", "unmanaged"))
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
      perfectly healthy object. The ${c.ok || 0} bindings that grant a real group follow
      below; the ${c.built_in || 0} built-in ones are behind the filter above.
```
```javascript
      perfectly healthy object. The ${c.ok || 0} granted bindings follow
      below; the ${c.built_in || 0} built-in ones are behind the filter above.
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  ${bindingSection("Unmanaged",
      `Hand-made grants on operator-synced groups, outside the policy system. Acknowledge
       a deliberate one with the <code>rbac.ocp.io/unmanaged-exception</code> annotation on
       the binding; the justification then lives next to the object and clears it here.`,
      f.unmanaged, sevBadge("warning", "unmanaged"))}
```
```javascript
  ${bindingSection("Unmanaged",
      `Hand-made grants outside the policy system — to operator-synced groups, ServiceAccounts
       or users. Silence a legitimate one by labelling the binding with
       <code>rbac.ocp.io/config-source</code>, or acknowledge it with the
       <code>rbac.ocp.io/unmanaged-exception</code> annotation; either lives next to the object
       and clears it here.`,
      f.unmanaged, sevBadge("warning", "unmanaged"))}
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
/* The group name, as a drill only where a group page can answer. A built-in virtual group
   (system:authenticated, system:serviceaccounts:*) never has a Group object, and an unresolved
   binding names a group that has never existed here — both drilled to a 404 card that blamed a
   deletion which never happened (operator, 2026-09-04). Dangling and granted groups keep the
   drill: the object exists, or existed and left history the page can show. */
function groupNameCell(r) {
  // A POSITIVE rule: drill only for the tiers where a group page can answer. Written as a
  // negative rule it drilled for a row that carried no tier at all (an older server), which is
  // exactly the dead end it was meant to remove (Codex second pass, 2026-09-04).
  if (r.finding === "ok" || r.finding === "unmanaged" || r.finding === "dangling") {
```
```javascript
/* The subject, as a drill only where a page can answer. A ServiceAccount or a User subject
   (#353) has no group page: the cell names it in full — `ServiceAccount <namespace>/<name>`,
   the account RBAC matches, or `user <name>` — with the kind in front so a reader never takes
   an account for a group. A Group drills as before: a built-in virtual group
   (system:authenticated, system:serviceaccounts:*) never has a Group object, and an unresolved
   binding names a group that has never existed here — both drilled to a 404 card that blamed a
   deletion which never happened (operator, 2026-09-04). Dangling and granted groups keep the
   drill: the object exists, or existed and left history the page can show. */
function subjectCell(r) {
  const kind = r.subject_kind || "Group";
  if (kind === "ServiceAccount") {
    return `<span class="muted">ServiceAccount</span> <span class="mono">${esc(r.subject_namespace || "")}/${esc(r.group_name)}</span>`;
  }
  if (kind === "User") {
    return `<span class="muted">user</span> <span class="mono">${esc(r.group_name)}</span>`;
  }
  // A POSITIVE rule: drill only for the tiers where a group page can answer. Written as a
  // negative rule it drilled for a row that carried no tier at all (an older server), which is
  // exactly the dead end it was meant to remove (Codex second pass, 2026-09-04).
  if (r.finding === "ok" || r.finding === "unmanaged" || r.finding === "dangling") {
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
      <thead><tr>${th("Group named by the binding", "group")}
        ${th("Reaches", "reaches")}
        ${th("Grants", "grants")}${th("Scope", "scope")}
        ${th("Binding", "binding")}</tr></thead>
      <tbody>${sorted.map((r) => `<tr>
        <td>${groupNameCell(r)}</td>
```
```javascript
      <thead><tr>${th("Subject named by the binding", "group")}
        ${th("Reaches", "reaches")}
        ${th("Grants", "grants")}${th("Scope", "scope")}
        ${th("Binding", "binding")}</tr></thead>
      <tbody>${sorted.map((r) => `<tr>
        <td>${subjectCell(r)}</td>
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  const f = data.findings || {};
  const unmanaged = f.unmanaged || [];
  const stamped = unmanaged.filter((r) => r.audit_stamped).length;
```
```javascript
  const f = data.findings || {};
  const unmanaged = f.unmanaged || [];
  // The cluster's number, not the page's: `unmanaged` holds at most FINDINGS_PAGE rows, and
  // `counts` describe the whole cluster (the findings endpoint's contract). Before SPEC_U1 the
  // hero counted the rows it had loaded, which a cluster with more findings than the page holds
  // — 713 on the lab once ServiceAccount and User grants count — would have shown as 500.
  const unmanagedTotal = f.counts && f.counts.unmanaged != null ? f.counts.unmanaged : unmanaged.length;
  const stamped = unmanaged.filter((r) => r.audit_stamped).length;
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
    <div class="hero">
      <span class="value mono">${unmanaged.length}</span>
      <span class="label">grant${unmanaged.length === 1 ? "" : "s"} outside the policy system</span>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="label">Policy CRs</div>
        <div class="value mono">${(oc && oc.configs || []).length}</div></div>
      <div class="kpi ${unmanaged.length ? "flag-warning" : ""}">
        <div class="label">Unmanaged</div>
        <div class="value mono ${unmanaged.length ? "" : "muted"}">${unmanaged.length}</div></div>
      <div class="kpi"><div class="label">Audit-stamped</div>
        <div class="value mono ${stamped ? "" : "muted"}">${stamped}</div></div>
    </div>
    <div class="filterbar-note mt-5">
      A grant is <strong>unmanaged</strong> when it names an operator-synced group but
      carries none of the policy operator's provenance — somebody granted access by hand.
      Acknowledge a deliberate one with the
      <code>rbac.ocp.io/unmanaged-exception</code> annotation on the binding; the
      justification then lives next to the object and clears it here.
```
```javascript
    <div class="hero">
      <span class="value mono">${unmanagedTotal}</span>
      <span class="label">grant${unmanagedTotal === 1 ? "" : "s"} outside the policy system</span>
    </div>
    <div class="kpis">
      <div class="kpi"><div class="label">Policy CRs</div>
        <div class="value mono">${(oc && oc.configs || []).length}</div></div>
      <div class="kpi ${unmanagedTotal ? "flag-warning" : ""}">
        <div class="label">Unmanaged</div>
        <div class="value mono ${unmanagedTotal ? "" : "muted"}">${unmanagedTotal}</div></div>
      <div class="kpi"><div class="label">Audit-stamped</div>
        <div class="value mono ${stamped ? "" : "muted"}">${stamped}</div></div>
    </div>
    <div class="filterbar-note mt-5">
      A grant is <strong>unmanaged</strong> when its binding carries none of the policy
      system's provenance — a grant to an operator-synced group, a ServiceAccount or a user,
      made by hand. Nothing about how it was applied excludes it. Silence a legitimate one by
      labelling the binding with <code>rbac.ocp.io/config-source</code>, as the platform's own
      grants are, or acknowledge it with the <code>rbac.ocp.io/unmanaged-exception</code>
      annotation; the justification then lives next to the object and clears it here.
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  ${bindingSection("Grants outside the policy system",
      `Each names a group the operator syncs, and nothing templates the grant itself.`,
      unmanaged, sevBadge("warning", "unmanaged"))}`;
```
```javascript
  ${bindingSection("Grants outside the policy system",
      `Nothing in the policy system templates or labels the grant itself, whoever it names.`
      + (unmanagedTotal > unmanaged.length
          ? ` Showing the first ${unmanaged.length} of ${unmanagedTotal}, by subject name; the cluster has more.`
          : ""),
      unmanaged, sevBadge("warning", "unmanaged"))}`;
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  bindings: ["finding", "group_name", "member_count", "logged_in_count", "role_kind", "role_name",
             "binding_kind", "binding_namespace", "binding_name", "managed_source", "exception"],
```
```javascript
  bindings: ["finding", "subject_kind", "subject_namespace", "group_name", "member_count", "logged_in_count",
             "role_kind", "role_name", "binding_kind", "binding_namespace", "binding_name", "managed_source",
             "exception"],
```

<!-- block: local-development/cluster-report.py | edit -->
```python
            w(f"**Group bindings — {f.get('total', 0)} total**")
```
```python
            w(f"**Bindings — {f.get('total', 0)} total** (one row per subject: a group, a ServiceAccount or a user)")
```

<!-- block: local-development/cluster-report.py | edit -->
```python
                    ("unmanaged", "hand-made on an operator-synced group, outside policy"),
```
```python
                    ("unmanaged", "hand-made, outside policy — a synced group, a ServiceAccount or a user"),
```

<!-- block: local-development/pyproject.toml | edit -->
```toml
version = "0.32.0"
```
```toml
version = "0.33.0"
```

<!-- block: local-development/gsd/__init__.py | edit -->
```python
__version__ = "0.32.0"
```
```python
__version__ = "0.33.0"
```

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->
```yaml
# Metadata only: no rule, subject or role changes.
version: 0.53.1
```
```yaml
# Metadata only: no rule, subject or role changes.
# CHART 0.54.0 (2026-09-24), MINOR: appVersion moves to application 0.33.0 (below) — the unmanaged finding
# reads ServiceAccount and User subjects and honours the same label on them (#353, SPEC_U1). The README and
# the values comment say what the finding covers; no template changes.
version: 0.54.0
```

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->
```yaml
# that decided. MINOR: behaviour changes on upgrade for a remote that states nothing (docs/CHANGELOG.md).
appVersion: "0.32.0"
```
```yaml
# that decided. MINOR: behaviour changes on upgrade for a remote that states nothing (docs/CHANGELOG.md).
# 0.33.0 (2026-09-24). The unmanaged finding reads every subject kind — Group, ServiceAccount and User —
# and a grant is silenced only by the operator's `rbac.ocp.io/config-source` label or the exception
# annotation on its binding (#353, SPEC_U1). Schema migration 20 (the binding table's primary key gains
# the subject's kind and namespace); `/bindings/findings` rows gain `subject_kind` and
# `subject_namespace`. MINOR: additive on the wire; every unlabelled ServiceAccount and User grant is a
# finding from the first refresh after upgrade, which is the capability.
appVersion: "0.33.0"
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->
```yaml
  # A binding is `unmanaged` when it names an operator-synced group but carries neither the
  # policy operator's config-source label nor an `rbac.ocp.io/unmanaged-exception`
  # annotation — somebody granted access by hand, outside the governance system, and nothing
  # on the cluster reports it.
```
```yaml
  # A binding is `unmanaged` when it carries neither the policy system's config-source label
  # nor an `rbac.ocp.io/unmanaged-exception` annotation and names an operator-synced group, a
  # ServiceAccount or a user — somebody granted access by hand, outside the governance system,
  # and nothing on the cluster reports it. Nothing about how a grant was applied (a `system:`
  # name, a platform namespace, a Helm or OLM label) excludes it: a legitimate one is silenced
  # by labelling its binding `rbac.ocp.io/config-source=<who decided>`, as this chart labels its
  # own RBAC (#312, #353).
```

<!-- block: charts/group-sync-dashboard/README.md | edit -->
```markdown
A binding is `unmanaged` when it grants an operator-synced group access and carries neither
the policy operator's `rbac.ocp.io/config-source` label nor an
`rbac.ocp.io/unmanaged-exception` annotation — somebody granted access by hand, outside the
governance system, and nothing on the cluster reports it. The classification also requires at
least one *managed* binding to exist on that cluster, so a cluster that has never used
config-source labels reports zero rather than flagging every binding on it
(`local-development/gsd/store.py#Store.user_bindings`).
```
```markdown
A binding is `unmanaged` when it carries neither the policy system's `rbac.ocp.io/config-source`
label nor an `rbac.ocp.io/unmanaged-exception` annotation and names an operator-synced group, a
ServiceAccount or a user (#353) — somebody granted access by hand, outside the governance system,
and nothing on the cluster reports it. Nothing about how a grant was applied excludes it — not a
`system:` name, a platform namespace or a Helm, OLM or Argo CD label; a legitimate one is silenced
by labelling its binding `rbac.ocp.io/config-source=<who decided>`, as this chart labels its own
RBAC. The classification also requires at least one *managed* binding to exist on that cluster,
of any subject kind and labelled by something other than this chart, so a cluster that has never
used config-source labels reports zero rather than flagging every binding on it
(`local-development/gsd/store.py#Store._FINDING_CASE`).
```

<!-- block: charts/group-sync-dashboard/README.md | edit -->
```markdown
Which object, what it grants, to whom, and why that is a finding — the line is actionable
without opening the dashboard, and the fixed `UNMANAGED GRANT DISCOVERED` prefix is there to
be alerted on. Only the groups whose rows were classified unmanaged are named: a binding can
name two groups and be unmanaged for only one, and citing the managed one would send a reader
to inspect a grant that is fine.
```
```markdown
Which object, what it grants, to whom, and why that is a finding — the line is actionable
without opening the dashboard, and the fixed `UNMANAGED GRANT DISCOVERED` prefix is there to
be alerted on. The subject is spelt by its kind — `group <name>`,
`ServiceAccount <namespace>/<name>` or `user <name>` — and only the subjects whose rows were
classified unmanaged are named: a binding can name two subjects and be unmanaged for only one,
and citing the managed one would send a reader to inspect a grant that is fine.
```

<!-- block: docs/unmanaged-audit-design.md | edit -->
```markdown
A binding is `unmanaged` when it names an operator-synced group and carries neither the policy
operator's `rbac.ocp.io/config-source` label nor an `rbac.ocp.io/unmanaged-exception`
annotation — somebody granted access by hand, outside the governance system, and nothing else
on the cluster reports it. On the reference cluster 77 of 85 convention bindings carry the
label, and the handful that do not are exactly the hand-made ones, including a
ClusterRoleBinding granting `cluster-admin` that nothing manages
(`local-development/tests/test_rbac.py#TestUnmanagedFinding`).

**What it covers today: Group subjects only** (`kube.py#_binding_views` keeps no other kind). The goal
is wider, in the operator's words (2026-09-24, #312): find grants made by hand that bypass policy,
whether the subject is a group, a ServiceAccount or a user, and silence the legitimate ones the
operator decides to exclude. Exclusion is never inferred: the operator puts the config-source label
(or the exception annotation) on a grant they have decided is legitimate, and only that silences
it. Extending the finding to ServiceAccount and User subjects, with the same label, is not built
yet (#353).
```
```markdown
A binding is `unmanaged` when it carries neither the policy system's `rbac.ocp.io/config-source`
label nor an `rbac.ocp.io/unmanaged-exception` annotation and names an operator-synced group, a
ServiceAccount or a user — somebody granted access by hand, outside the governance system, and
nothing else on the cluster reports it. On the reference cluster 77 of 85 convention bindings
carry the label, and the handful that do not are exactly the hand-made ones, including a
ClusterRoleBinding granting `cluster-admin` that nothing manages
(`local-development/tests/test_rbac.py#TestUnmanagedFinding`).

**What it covers: every subject kind RBAC defines** — Group, ServiceAccount and User
(`kube.py#_binding_views`, since #353, `docs/specs/SPEC_U1_unmanaged_subjects.md`). The goal, in
the operator's words (2026-09-24, #312): find grants made by hand that bypass policy, whether the
subject is a group, a ServiceAccount or a user, and silence the legitimate ones the operator decides
to exclude. Exclusion is never inferred: the operator puts the config-source label (or the exception
annotation) on a grant they have decided is legitimate, and only that silences it — nothing about
how a grant was applied (a `system:` name, a platform namespace, a Helm, OLM or Argo CD label)
excludes it. A Group subject is a finding only when its group is operator-synced (the three
resolution tiers below are Group tiers); a ServiceAccount or User subject, which has no Group object
to resolve, is a finding whenever its binding carries no label and no exception. A ServiceAccount
subject is stored under the namespace RBAC matches it in — its own, or the RoleBinding's when it
omits one, as the authorizer reads it.
```

<!-- block: docs/unmanaged-audit-design.md | edit -->
```markdown
**I2 — Finding set.** Unchanged in substance, renamed from "Target set" because nothing is
targeted now. An object is a finding only if its group resolves, its group is operator-synced,
the binding carries no `config-source` label, the binding carries no exception annotation, and
the cluster demonstrably uses the policy operator — some managed binding exists other than this
chart's own, so a cluster that has never heard of `config-source` labels reports zero findings
rather than sixty. All five
conditions are one SQL `CASE` (`store.py#_FINDING_CASE`), which is also what the API and the counts
read, so the log and the UI cannot disagree about what a finding is. Tests:
`test_audit_stamp.py#TestI2TargetSet.test_only_unmanaged_rows_are_stamped` and `test_rbac.py#TestUnmanagedFinding`.
```
```markdown
**I2 — Finding set.** Unchanged in substance, renamed from "Target set" because nothing is
targeted now. A (binding, subject) row is a finding only if the binding carries no `config-source`
label, the binding carries no exception annotation, the cluster demonstrably uses the policy
system — some managed binding exists, of any subject kind, labelled by something other than this
chart, so a cluster that has never heard of `config-source` labels reports zero findings rather
than sixty — and, for a Group subject, its group resolves and is operator-synced; a ServiceAccount
or User subject has no group to resolve and is a finding on the first three conditions alone
(#353). All the conditions are one SQL `CASE` (`store.py#_FINDING_CASE`), which is also what the
API, the counts and the reports read, so the log and the UI cannot disagree about what a finding
is. Tests: `test_audit_stamp.py#TestI2TargetSet.test_only_unmanaged_rows_are_stamped`,
`test_rbac.py#TestUnmanagedFinding` and `local-development/tests/test_unmanaged_subjects.py`.
```

<!-- block: docs/reference-architecture.md | edit -->
```markdown
| `unmanaged` | the group resolves and is synced, but no policy system manages this binding and no human has annotated an exception |
| `ok` | everything else |
```
```markdown
| `unmanaged` | no policy system manages this binding and no human has annotated an exception — for a Group subject, one that resolves and is synced; for a ServiceAccount or User subject, always (#353) |
| `ok` | everything else |
```

<!-- block: docs/reference-architecture.md | edit -->
```markdown
`unmanaged` additionally requires that the cluster demonstrably *uses* the policy operator —
`EXISTS (… managed_source IS NOT NULL)`. Without that clause, every binding on a cluster
that has never heard of `config-source` labels would flag.
```
```markdown
`unmanaged` additionally requires that the cluster demonstrably *uses* the policy system —
`EXISTS (… managed_source IS NOT NULL …)`, some labelled binding of any subject kind other than
this chart's own. Without that clause, every binding on a cluster that has never heard of
`config-source` labels would flag. The three tiers above it are Group tiers: a ServiceAccount or
User subject has no Group object to resolve, so its row is `unmanaged` or `ok` and nothing about
its name or namespace excludes it (`docs/specs/SPEC_U1_unmanaged_subjects.md`).
```

<!-- block: local-development/API.md | edit -->
```markdown
`dangling_bindings`, `unresolved_bindings` and `unmanaged_bindings` are the three findings a
person reviews — bindings that grant nobody, and grants of a synced group made outside the policy
system; a cluster's "Bindings to review" is their sum. `builtin_bindings` are expected and not
counted.
```
```markdown
`dangling_bindings`, `unresolved_bindings` and `unmanaged_bindings` are the three findings a
person reviews — bindings that grant nobody, and grants made outside the policy system to a synced
group, a ServiceAccount or a user; a cluster's "Bindings to review" is their sum. `builtin_bindings`
are expected and not counted.
```

<!-- block: local-development/API.md | edit -->
```markdown
Every group-subject binding, classified. Despite the path, this returns **all** bindings,
including healthy ones — the caller filters.

```json
{
  "total": 229, "limit": 500, "offset": 0, "truncated": false,
  "counts": {"ok": 70, "dangling": 0, "unresolved": 9, "built_in": 146, "unmanaged": 4},
  "ok": [
    {"binding_kind": "RoleBinding", "binding_namespace": "prod-ns", "binding_name": "managed-admin-rb",
     "role_kind": "ClusterRole", "role_name": "admin", "group_name": "app-ocp-rbac-alpha-ns-admin",
     "managed_source": "baseline-nonprod-rbac", "exception": null, "audit_stamped": 0, "finding": "ok",
     "member_count": 2, "logged_in_count": 1}
  ],
  "dangling": [], "unresolved": [], "built_in": [], "unmanaged": [],
  "operator_configs": {}
}
```

Every row, in every tier, has the same shape. `member_count` is the named group's synced members
```
```markdown
Every binding subject — a Group, a ServiceAccount or a User — classified. Despite the path, this
returns **all** bindings, including healthy ones — the caller filters.

```json
{
  "total": 229, "limit": 500, "offset": 0, "truncated": false,
  "counts": {"ok": 70, "dangling": 0, "unresolved": 9, "built_in": 146, "unmanaged": 4},
  "ok": [
    {"binding_kind": "RoleBinding", "binding_namespace": "prod-ns", "binding_name": "managed-admin-rb",
     "role_kind": "ClusterRole", "role_name": "admin",
     "subject_kind": "Group", "subject_namespace": "", "group_name": "app-ocp-rbac-alpha-ns-admin",
     "managed_source": "baseline-nonprod-rbac", "exception": null, "audit_stamped": 0, "finding": "ok",
     "member_count": 2, "logged_in_count": 1}
  ],
  "dangling": [], "unresolved": [], "built_in": [],
  "unmanaged": [
    {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "shared-qa-poller",
     "role_kind": "ClusterRole", "role_name": "cluster-admin",
     "subject_kind": "ServiceAccount", "subject_namespace": "group-sync-operator", "group_name": "shared-qa-poller",
     "managed_source": null, "exception": null, "audit_stamped": 0, "finding": "unmanaged",
     "member_count": null, "logged_in_count": null}
  ],
  "operator_configs": {}
}
```

Every row, in every tier, has the same shape. `subject_kind` is `Group`, `ServiceAccount` or `User`
— the three kinds RBAC defines — and **`group_name` is the subject's name whatever its kind** (the
field predates the other two kinds; since #353 every kind is a row). `subject_namespace` is a
ServiceAccount's namespace — the subject's own, or the RoleBinding's when the subject omits it,
which is how the authorizer reads it — and `""` for the other kinds. `member_count` is the named group's synced members
```

<!-- block: local-development/API.md | edit -->
```markdown
| `unmanaged` | the group IS operator-synced, but no policy CR templates this binding — somebody granted access by hand | no |
```
```markdown
| `unmanaged` | no policy system labels this binding and no exception is annotated — for a Group subject, one that IS operator-synced; for a ServiceAccount or User subject, always — somebody granted access by hand | no |
```

<!-- block: local-development/API.md | edit -->
```markdown
**Suppressing an `unmanaged` finding is a cluster-admin task, performed on the object:**

```bash
oc annotate clusterrolebinding <name> \
  rbac.ocp.io/unmanaged-exception="approved in TICKET-123, break-glass access"
```
```
```markdown
The three "group does not exist" tiers are Group tiers: a ServiceAccount or User subject has no
Group object to resolve, so its row is `unmanaged` or `ok`, and nothing about its name (`system:…`),
its namespace or the labels that applied it excludes it — only the operator's decision on the
binding does (#353).

**Suppressing an `unmanaged` finding is a cluster-admin task, performed on the object** — either
the policy system's label, naming who decided the grant is legitimate, as the chart labels its own
RBAC:

```bash
oc label clusterrolebinding <name> rbac.ocp.io/config-source=platform-team
```

or the exception annotation, which records why:

```bash
oc annotate clusterrolebinding <name> \
  rbac.ocp.io/unmanaged-exception="approved in TICKET-123, break-glass access"
```
```

<!-- block: docs/CHANGELOG.md | after: ## Unreleased -->
```markdown

- **The unmanaged finding reads ServiceAccount and User subjects, silenced only by the operator's label (application 0.33.0, chart 0.54.0; #353, `docs/specs/SPEC_U1_unmanaged_subjects.md`).** The binding table holds one row per subject of every kind RBAC defines — Group, ServiceAccount and User (schema migration 20, a primary-key rebuild that carries the rows) — and a grant to any of them is `unmanaged` when its binding carries neither `rbac.ocp.io/config-source` nor `rbac.ocp.io/unmanaged-exception` and some binding on the cluster is labelled by something other than this chart. Nothing about how a grant was applied excludes it: not a `system:` name, a platform namespace or a Helm, OLM or Argo CD label; a legitimate one is silenced by labelling its binding, as the chart labels its own. **On upgrade every unlabelled ServiceAccount and User grant is a finding from the first refresh** — 713 on the lab, listed 20 per cycle and counted in full on the summary line, the tiles, the KPI page and `gsd_bindings_total{finding="unmanaged"}`, which is now pre-seeded at 0 like the other tiers. A ServiceAccount subject that omits its namespace on a RoleBinding is stored under the binding's, the account the authorizer matches. `/bindings/findings` rows gain `subject_kind` and `subject_namespace`; `group_name` is the subject's name whatever its kind (`local-development/API.md`). The poller's WARNING spells the subject by kind (`group <name>`, `ServiceAccount <namespace>/<name>`, `user <name>`), and forwards the `rbac.ocp.io/unmanaged` label it read, which it had dropped since the label became an input. The Access granted tab names each subject in full with no drill for an account or a person; the RBAC policy tab's hero counts the cluster rather than the loaded page; the `binding-findings` report lists every kind. The group pages, a person's access through groups, the namespace audit, the binding history and `/user-bindings` are unchanged.
```

<!-- block: local-development/tests/test_rbac.py | edit -->
```python
from gsd.kube import CHART_CONFIG_SOURCE, BindingView, _binding_views
```
```python
from gsd.kube import CHART_CONFIG_SOURCE, SUBJECT_KINDS, BindingView, _binding_views
```

<!-- block: local-development/tests/test_rbac.py | edit -->
```python
class TestParsing:
    def test_only_group_subjects_are_kept(self):
        """User and ServiceAccount subjects cannot contribute to access-via-groups."""
        obj = {
            "metadata": {"name": "mixed-rb", "namespace": "alpha"},
            "roleRef": {"kind": "ClusterRole", "name": "edit"},
            "subjects": [
                {"kind": "Group", "name": "app-team"},
                {"kind": "User", "name": "alice"},
                {"kind": "ServiceAccount", "name": "builder", "namespace": "alpha"},
            ],
        }
        rows = _binding_views(obj, "RoleBinding")
        assert [r.group_name for r in rows] == ["app-team"]
```
```python
class TestParsing:
    def test_every_subject_kind_is_kept_with_its_kind(self):
        """#353: a hand-made grant is a finding whoever it names, so User and ServiceAccount
        subjects are rows too, each saying what it is; the Group-only questions filter in the store."""
        obj = {
            "metadata": {"name": "mixed-rb", "namespace": "alpha"},
            "roleRef": {"kind": "ClusterRole", "name": "edit"},
            "subjects": [
                {"kind": "Group", "name": "app-team"},
                {"kind": "User", "name": "alice"},
                {"kind": "ServiceAccount", "name": "builder", "namespace": "alpha"},
            ],
        }
        rows = _binding_views(obj, "RoleBinding")
        assert [(r.subject_kind, r.subject_namespace, r.group_name) for r in rows] == [
            ("Group", "", "app-team"), ("User", "", "alice"), ("ServiceAccount", "alpha", "builder")]
        assert set(SUBJECT_KINDS) == {"Group", "User", "ServiceAccount"}
```

<!-- block: local-development/tests/test_binding_reach.py | edit -->
```python
    assert set(rows[0]) == {"binding_kind", "binding_namespace", "binding_name", "role_kind", "role_name",
                            "group_name", "managed_source", "exception", "audit_stamped", "finding"}
```
```python
    assert set(rows[0]) == {"binding_kind", "binding_namespace", "binding_name", "role_kind", "role_name",
                            "subject_kind", "subject_namespace", "group_name", "managed_source", "exception",
                            "audit_stamped", "finding"}
```

<!-- block: local-development/tests/test_audit_stamp.py | edit -->
```python
        assert plan.evidence[key]["role"] == "cluster-admin"
        assert plan.evidence[key]["groups"] == ["app-ocp-rbac-demo"]
```
```python
        assert plan.evidence[key]["role"] == "cluster-admin"
        assert plan.evidence[key]["subjects"] == ["group app-ocp-rbac-demo"]
```

<!-- block: local-development/tests/test_audit_stamp.py | edit -->
```python
        assert plan.evidence[key]["groups"] == ["hand-made-group"], (
            "a managed group must never be cited as evidence of being unmanaged"
        )
```
```python
        assert plan.evidence[key]["subjects"] == ["group hand-made-group"], (
            "a managed group must never be cited as evidence of being unmanaged"
        )
```

<!-- block: local-development/tests/test_audit_stamp.py | edit -->
```python
        def binding(name, group, managed_source=None):
            return types.SimpleNamespace(
                binding_kind="RoleBinding", binding_namespace="ns", binding_name=name,
                role_kind="ClusterRole", role_name="admin", group_name=group,
                managed_source=managed_source, exception=None,
            )
```
```python
        def binding(name, group, managed_source=None):
            # The fields a BindingView carries; the poller reads every one of them (SPEC_U1).
            return types.SimpleNamespace(
                binding_kind="RoleBinding", binding_namespace="ns", binding_name=name,
                role_kind="ClusterRole", role_name="admin", group_name=group,
                subject_kind="Group", subject_namespace="", audit_stamped=False,
                managed_source=managed_source, exception=None,
            )
```

<!-- block: local-development/tests/test_reporting_catalogue.py | edit -->
```python
        assert [r[0] for r in unmanaged_tbl.rows] == ["team-b"]
```
```python
        assert [r[0] for r in unmanaged_tbl.rows] == ["group team-b"]
```

<!-- block: local-development/tests/test_metrics.py | edit -->
```python
    def test_binding_findings_are_broken_out(self, scrape):
        text, _ = scrape
        found = series(text, "gsd_bindings_total")
        assert found['gsd_bindings_total{cluster="crc",finding="ok"}'] == 1
        assert found['gsd_bindings_total{cluster="crc",finding="unresolved"}'] == 1
        assert found['gsd_bindings_total{cluster="crc",finding="built_in"}'] == 1
```
```python
    def test_binding_findings_are_broken_out(self, scrape):
        text, _ = scrape
        found = series(text, "gsd_bindings_total")
        assert found['gsd_bindings_total{cluster="crc",finding="ok"}'] == 1
        assert found['gsd_bindings_total{cluster="crc",finding="unresolved"}'] == 1
        assert found['gsd_bindings_total{cluster="crc",finding="built_in"}'] == 1
        # Pre-seeded like the other tiers (SPEC_U1): the seed has no unmanaged grant, and the series
        # is still there at 0, so `by (finding)` never loses it when a count returns to zero.
        assert found['gsd_bindings_total{cluster="crc",finding="unmanaged"}'] == 0
```

<!-- block: local-development/tests/test_binding_events.py | edit -->
```python
            assert store._conn.execute("PRAGMA user_version").fetchone()[0] == 19
            assert store._conn.execute("SELECT baseline FROM membership_event").fetchone()[0] == 0
```
```python
            assert store._conn.execute("PRAGMA user_version").fetchone()[0] == 20
            assert store._conn.execute("SELECT baseline FROM membership_event").fetchone()[0] == 0
```

<!-- block: local-development/tests/test_migrations.py | edit -->
```python
        assert upgraded._conn.execute("PRAGMA user_version").fetchone()[0] == max(t for t, _, _ in _MIGRATIONS) == 19
```
```python
        assert upgraded._conn.execute("PRAGMA user_version").fetchone()[0] == max(t for t, _, _ in _MIGRATIONS) == 20
```

<!-- block: local-development/tests/test_migrations.py | edit -->
```python
    upgraded = Store(db)
    try:
        assert upgraded._conn.execute("PRAGMA user_version").fetchone()[0] == 19
        markers = [tuple(r) for r in upgraded._conn.execute(
```
```python
    upgraded = Store(db)
    try:
        assert upgraded._conn.execute("PRAGMA user_version").fetchone()[0] == 20
        markers = [tuple(r) for r in upgraded._conn.execute(
```

<!-- block: local-development/tests/test_ui.py | edit -->
```python
        assert "grant nobody" in dash.locator("#main").inner_text()
        assert "grant a real group follow" in dash.locator("#main").inner_text()
```
```python
        assert "grant nobody" in dash.locator("#main").inner_text()
        assert "granted bindings follow" in dash.locator("#main").inner_text()
```

<!-- block: local-development/tests/test_ui.py | edit -->
```python
        assert "of 900 group bindings" in note and "past the cut cannot be found here" in note, note
```
```python
        assert "of 900 bindings" in note and "past the cut cannot be found here" in note, note
```

<!-- block: local-development/tests/test_ui.py | edit -->
```python
        # The header counts the cluster, never the match.
        assert "Group bindings on this cluster" in dash.locator("#main").inner_text()
```
```python
        # The header counts the cluster, never the match.
        assert "Bindings on this cluster" in dash.locator("#main").inner_text()
```

<!-- block: local-development/tests/test_ui.py | edit -->
```python
        self._open(dash)
        assert "Group bindings on this cluster" in dash.locator("body").inner_text()
        dash.select_option("#f-binding", "all")
```
```python
        self._open(dash)
        assert "Bindings on this cluster" in dash.locator("body").inner_text()
        dash.select_option("#f-binding", "all")
```

<!-- block: local-development/tests/test_ui.py | edit -->
```python
        total = tiles["Group bindings on this cluster"]
        parts = (tiles["Grant a real group"], tiles["Need review"], tiles["Built-in"])
```
```python
        total = tiles["Bindings on this cluster"]
        parts = (tiles["Granted"], tiles["Need review"], tiles["Built-in"])
```

<!-- block: local-development/tests/test_ui.py | after:         dash.wait_for_function("() => data.findings && data.findings.ok[0].member_count !== undefined") -->
```python

    def test_a_serviceaccount_and_a_user_subject_are_named_in_full_and_never_drilled(self, dash):
        """#353: a ServiceAccount or User grant outside the policy system is listed under Unmanaged
        with its kind in front — the account's namespace included, since that is the account RBAC
        matches — and has no group page to drill to. Injected into the fetched payload, so the seed
        and the counts the other tests pin stay as they are."""
        self._open(dash)
        errors = []
        dash.on("pageerror", lambda e: errors.append(str(e)))
        dash.evaluate("""() => {
            const d = data.findings;
            const sa = { binding_kind: "ClusterRoleBinding", binding_namespace: "", binding_name: "poller-crb",
                         role_kind: "ClusterRole", role_name: "cluster-admin", group_name: "shared-qa-poller",
                         subject_kind: "ServiceAccount", subject_namespace: "group-sync-operator",
                         managed_source: null, exception: null, audit_stamped: 0, finding: "unmanaged",
                         member_count: null, logged_in_count: null };
            const user = Object.assign({}, sa, { binding_name: "contractor-rb", binding_namespace: "ldap-testing",
                         role_name: "edit", group_name: "tmp-contractor-9931", subject_kind: "User", subject_namespace: "" });
            data.findings = Object.assign({}, d, { unmanaged: d.unmanaged.concat([sa, user]),
                                                   counts: Object.assign({}, d.counts, { unmanaged: d.counts.unmanaged + 2 }) });
            render();
        }""")
        section = dash.locator("section.card:has(h2:has-text('Unmanaged'))").first
        text = " ".join(section.inner_text().split())
        assert "ServiceAccount group-sync-operator/shared-qa-poller" in text, text
        assert "user tmp-contractor-9931" in text, text
        assert section.locator("button.drill[data-group='shared-qa-poller']").count() == 0
        assert section.locator("button.drill[data-group='tmp-contractor-9931']").count() == 0
        assert section.locator("button.drill[data-group='app-ocp-rbac-alpha-ns-admin']").count() == 1
        # The account's reach is nothing to say, not "0 members".
        assert "0 members" not in text
        assert errors == [], errors
        dash.evaluate("() => refresh()")
        dash.wait_for_function("() => data.findings && data.findings.unmanaged.length === 1")

    def test_the_policy_page_counts_the_cluster_not_the_loaded_page(self, dash):
        """The RBAC policy hero and its Unmanaged tile read `counts.unmanaged`, the cluster's number;
        the list below is the page, at most FINDINGS_PAGE rows. Before SPEC_U1 they counted the rows
        loaded, so a cluster with more unmanaged grants than the page holds under-reported the one
        number the tab exists to show."""
        dash.locator("button[data-nav='policy']").click()
        dash.wait_for_selector("section.card:has(h2:has-text('Grants outside')) tbody tr")
        dash.evaluate("""() => { data.findings = Object.assign({}, data.findings,
            { counts: Object.assign({}, data.findings.counts, { unmanaged: 713 }) }); render(); }""")
        assert dash.locator("#main .hero .value").first.inner_text().strip() == "713"
        body = " ".join(dash.locator("#main").inner_text().split())
        assert "Showing the first 1 of 713" in body, body
        dash.evaluate("() => refresh()")
        dash.wait_for_function("() => data.findings && data.findings.counts.unmanaged === 1")
        self._open(dash)
```

<!-- block: local-development/tests/test_unmanaged_subjects.py | create -->
```python
"""The unmanaged finding on ServiceAccount and User subjects (#353, docs/specs/SPEC_U1_unmanaged_subjects.md).

The operator's rule, tested layer by layer: a grant is excluded ONLY by the `rbac.ocp.io/config-source`
label or the `rbac.ocp.io/unmanaged-exception` annotation on its binding, whoever it names; nothing
about how it was applied — a `system:` name, a platform namespace, a Helm or OLM label — excludes it.
The Group-only questions (a group's page, a person's access through groups, the namespace audit, the
history stream) never see the new kinds. Every test here fails on the tree before SPEC_U1.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.audit import plan_audit_stamps, subject_label
from gsd.config import ClusterConfig, Settings
from gsd.kube import CHART_CONFIG_SOURCE, SUBJECT_KINDS, BindingView, _binding_views
from gsd.store import Store, _MIGRATIONS

T = "2026-09-24T20:00:00Z"
SYNCED = "app-ocp-rbac-team-ns-admin"


@pytest.fixture()
def store():
    s = Store(":memory:")
    s.upsert_cluster("crc", "https://x", True)
    yield s
    s.close()


def _synced(store, *names):
    """Groups the operator syncs: a Group object and a sync record for each."""
    store.replace_group_state(
        "crc", [{"name": n, "member_count": 1, "sync_provider": "ldap-groupsync_ldap",
                 "group_synced_at": None, "ldap_uid": None} for n in names], T)
    store.record_managed_groups("crc", [{"name": n, "sync_provider": "ldap-groupsync_ldap"} for n in names], T)


def group(name, subject=SYNCED, **kw):
    return {"binding_kind": "RoleBinding", "binding_namespace": "ns-a", "binding_name": name,
            "role_kind": "ClusterRole", "role_name": "admin", "group_name": subject, **kw}


def sa(name, account="poller", namespace="group-sync-operator", **kw):
    return {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": name,
            "role_kind": "ClusterRole", "role_name": "cluster-admin", "group_name": account,
            "subject_kind": "ServiceAccount", "subject_namespace": namespace, **kw}


def user(name, person="tmp-contractor-9931", **kw):
    return {"binding_kind": "RoleBinding", "binding_namespace": "ldap-testing", "binding_name": name,
            "role_kind": "ClusterRole", "role_name": "edit", "group_name": person,
            "subject_kind": "User", "subject_namespace": "", **kw}


def findings(store):
    return {r["binding_name"]: r["finding"] for r in store.all_bindings("crc")}


class TestReader:
    def _obj(self, kind, subjects, namespace="alpha"):
        meta = {"name": "b"} if kind == "ClusterRoleBinding" else {"name": "b", "namespace": namespace}
        return {"metadata": meta, "roleRef": {"kind": "ClusterRole", "name": "edit"}, "subjects": subjects}

    def test_a_rolebinding_serviceaccount_with_no_namespace_is_stored_under_the_bindings(self):
        """rule.go appliesToUser: the authorizer reads an omitted namespace as the binding's own, so the
        row names the account RBAC matches. 26 of the lab's 685 ServiceAccount subjects omit it."""
        rows = _binding_views(self._obj("RoleBinding", [{"kind": "ServiceAccount", "name": "builder"}]), "RoleBinding")
        assert [(r.subject_kind, r.subject_namespace, r.group_name) for r in rows] == [("ServiceAccount", "alpha", "builder")]

    def test_a_serviceaccount_that_names_a_namespace_keeps_its_own(self):
        rows = _binding_views(self._obj("RoleBinding", [{"kind": "ServiceAccount", "name": "builder", "namespace": "other"}]),
                              "RoleBinding")
        assert rows[0].subject_namespace == "other"
        rows = _binding_views(self._obj("ClusterRoleBinding", [{"kind": "ServiceAccount", "name": "poller",
                                                                "namespace": "group-sync-operator"}]), "ClusterRoleBinding")
        assert (rows[0].binding_namespace, rows[0].subject_namespace) == ("", "group-sync-operator")

    def test_users_and_groups_carry_no_namespace_and_unknown_kinds_nothing(self):
        rows = _binding_views(self._obj("RoleBinding", [
            {"kind": "User", "name": "alice"}, {"kind": "Group", "name": "g"},
            {"kind": "Robot", "name": "r2"}, {"kind": "ServiceAccount"}]), "RoleBinding")
        assert [(r.subject_kind, r.subject_namespace, r.group_name) for r in rows] == [
            ("User", "", "alice"), ("Group", "", "g")]
        assert SUBJECT_KINDS == ("Group", "ServiceAccount", "User")

    def test_a_view_built_the_old_way_is_a_group(self):
        v = BindingView("RoleBinding", "ns", "b", "ClusterRole", "r", "some-group")
        assert (v.subject_kind, v.subject_namespace) == ("Group", "")


class TestClassification:
    def test_an_unlabelled_serviceaccount_grant_is_unmanaged_where_the_policy_operator_is_in_use(self, store):
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("managed", managed_source="prod-rbac"), sa("hand-made-sa")], T)
        assert findings(store) == {"managed": "ok", "hand-made-sa": "unmanaged"}
        assert store.count_bindings_by_finding("crc")["unmanaged"] == 1

    def test_the_operators_label_on_the_binding_silences_it(self, store):
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("managed", managed_source="prod-rbac"),
                                       sa("decided", managed_source="platform-team"),
                                       user("person-decided", managed_source="platform-team")], T)
        assert findings(store) == {"managed": "ok", "decided": "ok", "person-decided": "ok"}

    def test_the_exception_annotation_silences_it(self, store):
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("managed", managed_source="prod-rbac"),
                                       sa("break-glass", exception="approved in TICKET-123")], T)
        assert findings(store)["break-glass"] == "ok"

    def test_a_system_named_user_is_unmanaged_and_never_built_in(self, store):
        """No inference from a `system:` name: the built_in tier is a Group tier. The lab's
        `system:kube-scheduler` User grants (6) are findings until labelled."""
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("managed", managed_source="prod-rbac"),
                                       user("scheduler", person="system:kube-scheduler"),
                                       group("virtual", subject="system:authenticated")], T)
        assert findings(store) == {"managed": "ok", "scheduler": "unmanaged", "virtual": "built_in"}

    def test_the_charts_own_label_silences_its_accounts_without_opening_the_gate(self, store):
        """#354 carried over: the chart labels its seven ServiceAccount bindings; on a host with no
        policy system nothing is reported, and one policy label switches the finding on."""
        _synced(store, SYNCED)
        chart = [sa(f"chart-{i}", account="group-sync-dashboard", namespace="group-sync-dashboard",
                    managed_source=CHART_CONFIG_SOURCE) for i in range(2)]
        store.replace_bindings("crc", chart + [sa("hand-made-sa"), group("hand-made")], T)
        assert findings(store) == {"chart-0": "ok", "chart-1": "ok", "hand-made-sa": "ok", "hand-made": "ok"}
        store.replace_bindings("crc", chart + [sa("hand-made-sa"), group("hand-made"),
                                               group("managed", managed_source="prod-rbac")], T)
        assert findings(store) == {"chart-0": "ok", "chart-1": "ok", "hand-made-sa": "unmanaged",
                                   "hand-made": "unmanaged", "managed": "ok"}

    def test_the_operators_label_on_one_account_opens_the_gate_for_every_kind(self, store):
        """One gate per cluster (SPEC_U1): the operator's first label is the policy system for a
        host that has no policy operator, and every unlabelled grant of every kind reports."""
        _synced(store, SYNCED)
        store.replace_bindings("crc", [sa("decided", managed_source="platform-team"),
                                       sa("hand-made-sa"), user("hand-made-user"), group("hand-made")], T)
        assert findings(store) == {"decided": "ok", "hand-made-sa": "unmanaged",
                                   "hand-made-user": "unmanaged", "hand-made": "unmanaged"}

    def test_an_account_named_like_a_synced_group_borrows_nothing_from_it(self, store):
        """The joins to the Group object, its sync record and its members are Group-only: the
        account is judged on provenance and its reach is null, not the group's members."""
        _synced(store, SYNCED)
        store.sync_members("crc", {SYNCED: ["alice"]}, {SYNCED: T}, T)
        store.replace_bindings("crc", [group("managed", managed_source="prod-rbac"),
                                       sa("same-name", account=SYNCED, managed_source="platform-team"),
                                       sa("same-name-unlabelled", account=SYNCED)], T)
        rows = {r["binding_name"]: r for r in store.all_bindings("crc", reach=True)}
        assert rows["same-name"]["finding"] == "ok" and rows["same-name-unlabelled"]["finding"] == "unmanaged"
        assert rows["same-name"]["member_count"] is None and rows["same-name-unlabelled"]["member_count"] is None
        assert rows["managed"]["member_count"] == 1

    def test_rows_carry_their_kind_and_namespace(self, store):
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("g"), sa("s"), user("u")], T)
        rows = {r["binding_name"]: (r["subject_kind"], r["subject_namespace"], r["group_name"]) for r in store.all_bindings("crc")}
        assert rows == {"g": ("Group", "", SYNCED), "s": ("ServiceAccount", "group-sync-operator", "poller"),
                        "u": ("User", "", "tmp-contractor-9931")}


class TestGroupOnlyReaders:
    @pytest.fixture()
    def mixed(self, store):
        """A synced group `devs` with one member, bound in ns-a; an account and a person each named
        `devs` too, bound in the same namespace and cluster-wide. Every Group-only reader must answer
        as if the account and the person were not there."""
        _synced(store, "devs")
        store.sync_members("crc", {"devs": ["alice"]}, {"devs": T}, T)
        store.replace_namespaces("crc", [{"name": "ns-a", "phase": "Active", "metadata": {}}], T)
        store.replace_bindings("crc", [
            group("devs-edit", subject="devs", managed_source="prod-rbac"),
            sa("devs-sa", account="devs", namespace="ns-a"),
            {**sa("devs-sa-ns", account="devs", namespace="ns-a"), "binding_kind": "RoleBinding", "binding_namespace": "ns-a"},
            {**user("devs-user", person="devs"), "binding_namespace": "ns-a"},
        ], T)
        return store

    def test_a_groups_bindings_and_count(self, mixed):
        assert [b["binding_name"] for b in mixed.group_bindings("crc", "devs")] == ["devs-edit"]
        assert {g["name"]: g["binding_count"] for g in mixed.groups("crc")} == {"devs": 1}

    def test_a_persons_access_through_groups(self, mixed):
        assert [b["binding_name"] for b in mixed.user_bindings("crc", "alice")] == ["devs-edit"]

    def test_the_namespace_audit(self, mixed):
        ns = {n["name"]: n["via_groups"] for n in mixed.namespaces("crc")}
        assert ns == {"ns-a": 1}
        assert mixed.namespace_reach("crc", "ns-a", "alice", ["devs"]) is True
        assert mixed.namespace_reach("crc", "ns-a", "nobody", []) is False
        detail = mixed.namespace_detail("crc", "ns-a")
        assert [b["binding_name"] for b in detail["via_groups"]] == ["devs-edit"]


class TestWriter:
    def test_no_history_event_for_an_account_or_a_person_and_the_group_diff_is_unaffected(self, store):
        counts = store.replace_bindings("crc", [group("g"), sa("s"), user("u")], T)
        assert counts == {"added": 1, "removed": 0}
        assert [(e["subject_kind"], e["subject_name"]) for e in store.binding_events("crc")] == [("Group", SYNCED)]
        counts = store.replace_bindings("crc", [group("g"), sa("s2")], "2026-09-24T20:05:00Z")
        assert counts == {"added": 0, "removed": 0}

    def test_a_row_that_names_no_kind_is_a_group(self, store):
        store.replace_bindings("crc", [group("g")], T)
        row = store.all_bindings("crc")[0]
        assert (row["subject_kind"], row["subject_namespace"]) == ("Group", "")


def _v19_database(path: str) -> None:
    """A database as release 0.32.0 left it: the old table shape, one row, user_version 19."""
    conn = sqlite3.connect(path)
    conn.executescript("""
        CREATE TABLE rbac_group_binding (
            cluster_id          TEXT NOT NULL,
            binding_kind        TEXT NOT NULL,
            binding_namespace   TEXT NOT NULL,
            binding_name        TEXT NOT NULL,
            role_kind           TEXT NOT NULL,
            role_name           TEXT NOT NULL,
            group_name          TEXT NOT NULL,
            observed_at         TEXT NOT NULL,
            managed_source      TEXT,
            exception           TEXT,
            audit_stamped       INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(cluster_id, binding_kind, binding_namespace, binding_name, group_name)
        );
        CREATE INDEX rbac_binding_by_group ON rbac_group_binding(cluster_id, group_name);
        INSERT INTO rbac_group_binding VALUES
            ('crc', 'RoleBinding', 'ns-a', 'old-row', 'ClusterRole', 'view',
             'app-ocp-rbac-team-ns-audit', '2026-09-01T00:00:00Z', 'prod-rbac', NULL, 1);
        PRAGMA user_version = 19;
    """)
    conn.commit()
    conn.close()


class TestMigration20:
    def test_the_table_is_rebuilt_and_the_rows_carried_as_group_subjects(self, tmp_path):
        db = str(tmp_path / "old.db")
        _v19_database(db)
        store = Store(db)
        try:
            cols = [r[1] for r in store._conn.execute("PRAGMA table_info(rbac_group_binding)")]
            assert "subject_kind" in cols and "subject_namespace" in cols
            pk = [r[1] for r in sorted(store._conn.execute("PRAGMA table_info(rbac_group_binding)"), key=lambda r: r[5]) if r[5]]
            assert pk == ["cluster_id", "binding_kind", "binding_namespace", "binding_name",
                          "subject_kind", "subject_namespace", "group_name"]
            rows = store.all_bindings("crc")
            assert len(rows) == 1
            assert (rows[0]["subject_kind"], rows[0]["subject_namespace"], rows[0]["group_name"],
                    rows[0]["managed_source"], rows[0]["audit_stamped"]) == ("Group", "", "app-ocp-rbac-team-ns-audit", "prod-rbac", 1)
            assert store._conn.execute("PRAGMA user_version").fetchone()[0] == 20
            assert [r[1] for r in store._conn.execute("PRAGMA index_list(rbac_group_binding)")].count("rbac_binding_by_group") == 1
        finally:
            store.close()

    def test_reopening_is_idempotent_and_the_report_service_knows_the_version(self, tmp_path):
        from gsd.reporting.snapshot import KNOWN_SCHEMA_VERSION
        db = str(tmp_path / "old.db")
        _v19_database(db)
        for _ in range(3):
            Store(db).close()
        store = Store(db)
        try:
            assert store._conn.execute("PRAGMA user_version").fetchone()[0] == max(t for t, _, _ in _MIGRATIONS) == 20
            assert len(store.all_bindings("crc")) == 1
        finally:
            store.close()
        assert KNOWN_SCHEMA_VERSION == 20


class TestAnnouncer:
    def test_subject_label_spells_the_three_kinds(self):
        assert subject_label({"group_name": "g"}) == "group g"
        assert subject_label({"subject_kind": "Group", "group_name": "g"}) == "group g"
        assert subject_label({"subject_kind": "ServiceAccount", "subject_namespace": "ns", "group_name": "a"}) == "ServiceAccount ns/a"
        assert subject_label({"subject_kind": "User", "group_name": "p"}) == "user p"

    def test_the_evidence_names_the_account_and_only_the_unmanaged_subject(self):
        row = {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "poller-crb",
               "role_name": "cluster-admin", "audit_stamped": False}
        plan = plan_audit_stamps([
            {**row, "subject_kind": "ServiceAccount", "subject_namespace": "group-sync-operator",
             "group_name": "shared-qa-poller", "finding": "unmanaged"},
            {**row, "subject_kind": "Group", "subject_namespace": "", "group_name": "labelled-group", "finding": "ok"},
        ])
        key = ("ClusterRoleBinding", "", "poller-crb")
        assert plan.stamp == [key]
        assert plan.evidence[key] == {"role": "cluster-admin", "subjects": ["ServiceAccount group-sync-operator/shared-qa-poller"]}

    def test_one_refresh_logs_the_account_and_stores_the_stamp_it_read(self, tmp_path, monkeypatch, caplog):
        from gsd import poller
        store = Store(str(tmp_path / "t.db"))
        store.upsert_cluster("c1", "https://x", True)
        _synced_c1 = [{"name": SYNCED, "sync_provider": "gs_ldap"}]
        store.record_managed_groups("c1", _synced_c1, T)
        store.replace_group_state("c1", [{"name": SYNCED, "member_count": 1, "sync_provider": "gs_ldap",
                                          "group_synced_at": None, "ldap_uid": None}], T)
        # The labelled Group binding carries the rbac.ocp.io/unmanaged label (audit_stamped): it is `ok`, so
        # the plan RESOLVES it (I4) — and the stamp reaches the store, which it never did before SPEC_U1.
        # The account is unlabelled and unstamped, so it is announced (I3 never re-announces a stamped one).
        rows = [
            BindingView("RoleBinding", "ns", "managed", "ClusterRole", "admin", SYNCED, managed_source="policy",
                        audit_stamped=True),
            BindingView("ClusterRoleBinding", "", "shared-qa-poller", "ClusterRole", "cluster-admin", "shared-qa-poller",
                        subject_kind="ServiceAccount", subject_namespace="group-sync-operator"),
        ]

        class FakeClient:
            def __init__(self, *a, **kw): pass
            def fetch_bindings(self): return rows
            def fetch_user_bindings(self): return []
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", FakeClient)
        with caplog.at_level("INFO", logger="gsd.poller"):
            poller.refresh_bindings(store, ClusterConfig("c1", "https://x", token_env="T"), timeout=5, audit_mode="log")
        assert "grants cluster-admin to ServiceAccount group-sync-operator/shared-qa-poller" in caplog.text, caplog.text
        assert "unmanaged grant RESOLVED — c1: RoleBinding ns/managed" in caplog.text, caplog.text
        assert "1 outside the policy system, 1 resolved" in caplog.text, caplog.text
        assert "refreshed 2 bindings for c1 (1 Group, 1 ServiceAccount, 0 User subjects)" in caplog.text, caplog.text
        stamped = {r["binding_name"]: r["audit_stamped"] for r in store.all_bindings("c1")}
        assert stamped == {"managed": 1, "shared-qa-poller": 0}
        store.close()


class TestApi:
    @pytest.fixture()
    def client(self, tmp_path):
        db = str(tmp_path / "t.db")
        store = Store(db)
        store.upsert_cluster("c1", "https://x", True)
        store.replace_group_state("c1", [{"name": SYNCED, "member_count": 1, "sync_provider": "gs_ldap",
                                          "group_synced_at": None, "ldap_uid": None}], T)
        store.record_managed_groups("c1", [{"name": SYNCED, "sync_provider": "gs_ldap"}], T)
        store.replace_bindings("c1", [group("managed", managed_source="prod-rbac"),
                                      sa("shared-qa-poller", account="shared-qa-poller")], T)
        store.close()
        settings = Settings(db_path=db, clusters=[ClusterConfig("c1", "https://x", token_env="T")])
        return TestClient(build_app(settings, run_poller=False))

    def test_a_finding_row_carries_its_kind_and_the_cluster_counts_it(self, client):
        d = client.get("/api/clusters/c1/bindings/findings").json()
        assert d["counts"]["unmanaged"] == 1 and d["counts"]["ok"] == 1
        row = d["unmanaged"][0]
        assert (row["subject_kind"], row["subject_namespace"], row["group_name"]) == ("ServiceAccount", "group-sync-operator", "shared-qa-poller")
        assert row["member_count"] is None and row["logged_in_count"] is None
        assert d["ok"][0]["subject_kind"] == "Group"
        clusters = {c["id"]: c for c in client.get("/api/clusters").json()}
        assert clusters["c1"]["unmanaged_bindings"] == 1


class TestReports:
    @pytest.fixture()
    def snap(self, tmp_path):
        from gsd.reporting.snapshot import Snapshot
        store = Store(str(tmp_path / "w.db"))
        store.upsert_cluster("crc", "https://x", True)
        _synced(store, SYNCED)
        store.replace_bindings("crc", [
            group("managed", managed_source="prod-rbac"),
            sa("shared-qa-poller", account="shared-qa-poller"),
            user("scheduler", person="system:kube-scheduler"),
            group("virtual", subject="system:authenticated"),
        ], T)
        d = tmp_path / "snapshots"; d.mkdir()
        path = store.snapshot(str(d), keep=2)
        store.close()
        s = Snapshot(Path(path))
        yield s
        s.close()

    def test_the_snapshot_lists_groups_by_default_and_every_kind_on_request(self, snap):
        assert [r["binding_name"] for r in snap.group_bindings("crc")] == ["managed"]
        rows = {r["binding_name"]: r for r in snap.group_bindings("crc", kinds=SUBJECT_KINDS)}
        assert set(rows) == {"managed", "shared-qa-poller", "scheduler"}, "the virtual group is omitted, the system-named user is not"
        assert rows["shared-qa-poller"]["finding"] == "unmanaged" and rows["scheduler"]["finding"] == "unmanaged"
        assert rows["shared-qa-poller"]["member_count"] is None
        assert snap.findings_counts("crc") == {"ok": 1, "unmanaged": 2}
        assert snap.counts("crc")["group_bindings"] == 1

    def test_the_binding_findings_report_names_the_account(self, snap):
        from gsd.reporting.catalogue import REGISTRY, RunContext, validate_params
        from gsd.reporting.config import ReportSettings
        from datetime import UTC, datetime
        vendor = Path(__file__).resolve().parents[1] / "gsd" / "static" / "vendor"
        settings = ReportSettings(pdf_enabled=False, pdf_variant="pdf/a-2b", font_regular=str(vendor / "DejaVuSans.ttf"),
                                  font_bold=str(vendor / "DejaVuSans-Bold.ttf"), login_capture_enabled=False,
                                  namespaces_read_enabled=False)
        info = snap.info()
        now = datetime(2026, 9, 24, 20, 0, tzinfo=UTC)
        ctx = RunContext(settings=settings, cluster=snap.cluster("crc"), now=now, run_id="20260924T200000.000000Z-ab12",
                         generated_by="root", generated_by_note="proxy-verified", snapshot_stamp=info.stamp,
                         snapshot_age_seconds=info.age_seconds(now), schema_version=info.schema_version)
        spec, build = REGISTRY["binding-findings"]
        built = build(snap, ctx, validate_params(spec, {}))
        unmanaged = next(b for s in built.sections if s.title == "Unmanaged bindings" for b in s.blocks)
        assert unmanaged.columns[0] == "subject"
        subjects = sorted(r[0] for r in unmanaged.rows)
        assert subjects == ["ServiceAccount group-sync-operator/shared-qa-poller", "user system:kube-scheduler"]
        assert built.totals["unmanaged"] == 2
```
