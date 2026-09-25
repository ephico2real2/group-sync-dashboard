# SPEC U1 — the unmanaged finding on ServiceAccount and User subjects: the platform's own built-in, the rest silenced only by the operator's label (#353)

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

- **The mandate.** The amendment of 2026-09-24 works from the orchestrator's mandate for #353, which gathers
  the operator's rulings of that day in one place and supersedes every earlier message; the notes below quote
  the rulings it carries, and the requirement is not re-opened here.
- **The platform's own identities are never a finding — the operator's long-standing rule, restored
  (amendment, 2026-09-24).** The operator: *"Remember we are supposed to silence all platform service
  account that comes. This has been our long standing rules. We added exception those namespaces we
  excluded them in code and also add additional ones via values.yaml."* The orchestrator's brief for
  this spec had said "no inference from `system:` names or namespaces", which over-corrected that rule
  and is named here as the brief's error; the first merged version of this spec, and PR #360 built from
  it, reported every unlabelled ServiceAccount and User. The classification is the estate's own
  configured decision, not an inference, and it already exists: `PlatformNamespaces.matches` (the code's
  defaults `openshift-`/`kube-` and `default`, `openshift`, `kube-system`, `kube-public`, `kube-node-lease`,
  plus the values file's `additionalPrefixes`/`additionalSuffixes`/`additionalNames`, #255 — the one
  classifier Home and the namespace index use) for a ServiceAccount's effective namespace, and
  `is_platform_user` (`system:*`, `kubeadmin`, the node identities) for a User, as the direct-user view
  has always applied it. The rule as built: a platform identity is `built_in`, never a finding; anything
  else is reported unless its binding carries the label or the exception; nothing new is inferred — no
  Helm, OLM or Argo CD label, no binding name. The flag is computed in `refresh_bindings` from the
  settings, as the user path computes `user_binding.is_platform`, so a values change reclassifies on
  the next refresh; it is stored on the row (`is_platform`, in migration 20, unshipped). The tier: the
  existing `built_in`, so a platform row sits under the Built-in tile, behind the default filter, out of
  "to review", out of every report's listing (the reports' omit reads the flag beside the `system:` Group
  test), and under `finding="built_in"` on the metric. The Group arm is untouched. Measured on the lab
  (§2.2): the shipped namespace defaults silence 469 of the 668 ServiceAccount rows and 24 of the 35 User
  rows, leaving 210 rows on 203 bindings, 86 of them OpenShift's own per-project `system:image-builders` →
  `builder` and `system:deployers` → `deployer` RoleBindings (43 + 43, written by the project's controller).
  The operator ruled on those (2026-09-24): *"Nope. This too much. I wanna exclude by namespaces as designed.
  This is a big enterprise goal. Your approach to use other methods is not scalable. We have that logic built
  for a reason"* — and then: *"exclude the following default in all namespaces by design and additional
  system:image-builders/system:image-builder for SA builder, and system:deployers/system:deployer for SA
  deployer"*. So: the namespace classifier stays the one design, with no SA-name, binding-name or role rule of
  any kind; and, in addition, OpenShift's three per-project controller bindings are shipped defaults excluded
  by design in every namespace, matched on all three parts — (a) `system:image-builders` → ClusterRole
  `system:image-builder` → SA `builder`, (b) `system:deployers` → `system:deployer` → SA `deployer`, the
  subject in the binding's own namespace, and (c) `system:image-pullers` → `system:image-puller` → Group
  `system:serviceaccounts:<namespace>`, which the Group arm's `system:` rule already decides — listed together
  in `home.py`, marked, and pinned by tests; nothing broader, and no values key widens them. That leaves 124
  rows on 117 bindings on the lab (§2.2). The operator also noted *"There is also a service account called
  default"*: its default access is (c) — every ServiceAccount is in `system:serviceaccounts:<namespace>` —
  and OpenShift writes no binding of its own for SA `default` (measured: the only binding naming it is
  ClusterRoleBinding `cluster-version-operator` → `cluster-admin` in `openshift-cluster-version`, silent as a
  platform namespace), so SA `default` gets no name rule, and a hand-made grant to it in a project namespace
  stays a finding: pods run as `default`, and that is the escalation this finding exists to catch. The
  operator asked whether any other core account appears in every namespace; measured on the lab (OpenShift
  4.22.7, `oc get sa -A`, `oc get rolebindings -A`, `oc get clusterrolebindings`): 113 namespaces, 69 platform
  by the shipped defaults and 44 project; exactly three ServiceAccount names exist in all 113 — `builder`,
  `default`, `deployer` — and no other reaches half; exactly three bindings exist in every namespace, (a), (b)
  and (c) above; the only other binding naming any of the three accounts is the `cluster-version-operator`
  ClusterRoleBinding, and Red Hat's "Using service accounts in applications" names the same three accounts and
  roles. So (a), (b) and (c) are the complete core set. One candidate is noted and not built: OpenShift
  Pipelines, when installed, adds an SA `pipeline` and RoleBindings to every new project (Red Hat's docs); the
  lab has no Pipelines, so it is not measured, and the operator decides it later on a measured cluster in the
  same exact-shape way. The operator also asked to exclude `openshift-cluster-version`: it is already the
  platform's by the shipped prefix `openshift-`, so no rule changes, and the lab's own binding there is pinned
  by a test that names what decides it — the account's own namespace, since a ClusterRoleBinding has none.
  One more ruling, on OB1-lite's question in the review of #361 (2026-09-25): a User subject spelt
  `system:serviceaccount:<namespace>:<name>` — the same access as the ServiceAccount subject, since the
  authorizer matches a User by name (`rule.go` `appliesToUser`) — stays the platform's through
  `is_platform_user`'s `system:` prefix, unchanged; no namespace rule is added for it. The operator: keep it
  silent. Measured on the lab: 5 such rows, all `openshift-kube-apiserver:check-endpoints`, platform by either
  rule. The known consequence, recorded: a hand-made grant written that way in a project namespace is not
  reported, and the SA `default` rule above does not reach it.
- **Every line that decides or consumes "platform" carries the marker `PLATFORM-CLASSIFICATION (#255, #353)`**
  (the operator: *"tell it to add a marker to the code, so OB1 can review and help us review the logic and that
  it is working as intended"*): on the classifiers and their defaults, their settings parse and the chart's
  values → configmap → `clusters.yaml` path, the existing consumers (the namespace index, Home, the
  direct-user view), and every consumer on the finding path. `git grep PLATFORM-CLASSIFICATION` lists the whole
  logic end to end; the sites are listed in §3.12, and `tests/test_platform_classification_marker.py` fails
  when a call of `platform_namespaces.matches`, `is_platform_user` or the constants appears in
  `local-development/gsd/` without the marker on its line or the line above, so the map cannot rot.

- **Exclusion is the platform classification and the operator's label on the binding, and nothing else —
  the operator's rule, not a design choice.** *"The exclusion is not automatic … We are going to decide who
  to exclude"*, *"Using that label. We just need capabilities"*, *"We will labeling the role bindings or
  clusterrolebindings for users or groups or service account"* (#312, 2026-09-24), and the platform rule
  quoted above. A platform identity is `built_in` before the finding's arm is reached; every other
  ServiceAccount or User grant is `unmanaged` unless the binding carries `rbac.ocp.io/config-source` or
  `rbac.ocp.io/unmanaged-exception`. No Helm, OLM or Argo CD label and no binding name excludes anything
  (§3.4). The measured consequence on the lab is stated in §2.2 and §6 so that nobody reads it as a defect:
  703 of the lab's 710 stored ServiceAccount and User subject rows, on 689 bindings, carry no label today; 579
  of them are the platform's own and join the built-in tier, and the remaining 124, on 117 bindings, are
  findings until the operator labels the grants they decide are legitimate.
- **One table, widened in place; `group_name` keeps its name.** The rows join `rbac_group_binding`, with
  `subject_kind` and `subject_namespace` beside the subject's name, and the primary key gains both
  (migration 20, §3.2). A second table for the other kinds would have meant a second copy of the
  classification — the one thing `docs/unmanaged-audit-design.md` I2 forbids, because two copies drift and
  the log and the page then disagree about what a finding is. The column `group_name` holds the subject's
  name whatever its kind: it is read in 106 places in `store.py`, 33 in the report snapshot, 24 on the page
  and about a hundred in tests (measured with `grep -c`), so a rename is not a change this format can carry
  safely; the table comment, the API document and the row's `subject_kind` say what it names.
- **No gate for ServiceAccount and User subjects; the Group arm keeps #354's gate** — the same predicate, guarded by
  `subject_kind = 'Group'` because the table now holds other kinds. The first
  draft of this spec put one gate over every kind — a ServiceAccount or User grant was `unmanaged` only where
  some binding on the cluster carried a policy label. Codex refuted it on the premise and it is retracted: on a
  host with no label anywhere that gate silenced every unlabelled account and person by the cluster's state,
  which is not a decision anyone made — *"The exclusion is not automatic … We are going to decide who to
  exclude"*. What silences a ServiceAccount or User grant is the estate's own configured decision, twice: the
  platform classification (the amendment above), which makes the row `built_in` before this arm, and the label
  or the annotation the operator puts on the binding. So an unlabelled ServiceAccount or User grant that is not
  the platform's own is a finding from its first observation on every host. (An earlier version of this bullet
  said "no default that silences a grant"; that was the brief's over-correction, retracted above.) The Group arm
  is not this spec's to change: it keeps #354's gate — some other Group-subject binding labelled by something
  other than this chart — read over Group rows only, so the arm classifies exactly as it did before this spec
  (§3.4). The asymmetry that leaves (a plain host reports its hand-made account grants and not its hand-made
  group grants until a Group binding carries a policy label) is stated on #353 for the operator to rule on;
  widening or removing the Group gate is a decision, not a capability, and it is not taken here.
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
- **Three adjacent defects found by the reader map and the review are fixed here, because the blocks that fix
  them are the blocks this spec edits anyway.** (1) `poller.refresh_bindings` never forwarded `audit_stamped` to the store
  — `kube.py` read the `rbac.ocp.io/unmanaged` label into the view and the row dict dropped it, so
  `audit_stamped` was 0 for every live row, the RESOLVED line could never fire from live data and the RBAC
  policy page's "Audit-stamped" tile always read 0. The row dict now carries it (§3.6, tested §4). (2)
  `metrics.FINDINGS` lacked `unmanaged`, so `gsd_bindings_total{finding="unmanaged"}` was emitted only while
  such rows existed instead of being pre-seeded at 0 like the other four tiers — a series that vanishes
  breaks `by (finding)` aggregation and hides a count going to zero. The tuple gains the word (§3.10). (3)
  `policyPage` returned a "not installed" card before its hero whenever the namespace-configuration-operator
  was absent (Codex, review of SPEC_U1) — consistent while every finding needed that operator's labels, and a
  page that hides 703 findings once an account is a finding by the label alone. The card is rendered beside
  the findings now, not instead of them (§3.8).
- **The RBAC policy page counts the cluster, not the loaded page.** Its hero and "Unmanaged" tile read
  `f.unmanaged.length`, the rows the page fetched (at most `FINDINGS_PAGE`, 500), while `counts.unmanaged`
  is the cluster's. With one finding that was invisible; with 703 on the lab the tab would say 500. They
  read `counts.unmanaged` now and the list says how many of the total it shows (§3.8).
- **Migration 20's copy is `INSERT OR IGNORE`, so its replay converges from a populated `_v20` table**
  (Grok, review of SPEC_U1, accepted on the property with its premise refuted). Grok held that each
  statement of a migration commits on its own, so a crash between the copy and the drop would leave the
  new table populated and the replay would raise `IntegrityError`, which `_migrate` does not tolerate.
  Measured with the store's own `sqlite3.connect(path, check_same_thread=False)` on the images' Python
  3.14: `isolation_level ''`, legacy transaction control; the `CREATE` runs outside any transaction, the
  `INSERT` opens the implicit one, and the `DROP` and the `PRAGMA user_version` ride in it until
  `Store.__init__` commits — after a simulated crash the new table held 0 rows, the old one was intact and
  the version read 19, so the replay was already clean. `OR IGNORE` costs nothing and covers the one way
  a populated `_v20` can exist, a hand repair; the test builds that state directly.
- **The compliance snapshot names its two populations** (Grok; Codex on the third label): "Group bindings
  (Group subjects)" beside "Unmanaged (every subject kind)", because on this seed 1 beside 2 — and on the lab
  about 190 beside 703 — reads as a share of one population when it is two; and "Platform identity grants
  (excluded from the direct-user figures)", because a platform-named User grant is excluded from those figures
  and not from Unmanaged. Codex's explanatory note was rejected as the larger change for the same reading.
- **Five findings of OB1-lite's review, accepted and re-measured.** (1) A subject an OLM RoleBinding names
  twice was two rows in the reader and one in the store (10 on the lab: 925 entries, 915 rows), so the
  refresh line over-counted; the reader keeps a distinct (kind, namespace, name) once, and every number in
  this spec is the stored count: 915 rows, 703 finding rows on 689 bindings, 668 + 35 unlabelled. (2) The
  findings page was ordered by name across tiers, so on the lab 254 of 703 unmanaged rows and a dangling
  group named past `aa…` accounts fell off the 500-row page; it is ordered review tiers first, then name.
  (3) The report service accepts an older copy by design, and every binding read now names
  `subject_kind`: during the roll a schema-19 copy raised "no such column" on preview and run. It is read
  through a TEMP view that supplies the two columns as Group rows. (4) The report form's role picker
  offered every role any account is bound to (356 on the lab against 66 a report can match); it reads
  Group rows and direct user grants. (5) The compliance snapshot's Unmanaged figure now sits under the
  every-kind total it is a part of. And from its second pass: (6) neither ORDER BY named the two key
  columns migration 20 adds, so rows that tie on the old key — one binding naming an account in two
  namespaces, which the lab's `system:controller:horizontal-pod-autoscaler` does — came back in scan
  order and a `limit`/`offset` walk could skip or repeat one; both orderings end on the whole key. Also corrected: the 26 namespace-less subjects sit on 13 RoleBindings
  written by OLM (9), the cluster-version operator (3) and by hand (1), not "all OLM".
- **Found in the implementation's review (#360) and written back here, the same PR.** (1) The capped log
  listed the same sorted first twenty every cycle: `plan_audit_stamps` takes a sorted prefix, which
  converged only while the write path stamped what it listed; in log mode nothing is stamped, so on the
  lab 20 of 689 findings were announced every cycle and the other 669 never — and a new hand-made grant
  named past them was never announced at all, which is the DoD's first half in the log (Grok on the
  evidence procedure; Codex with the fix). Accepted with Codex's scheduler: `AuditLogProgress`, one per
  poll thread, in memory, new findings first, then the least recently listed; the sorted prefix stays for
  a call with no scheduler. Grok's alternative — naming the planted grant so it sorts first — was a
  procedure that hid the hole and is superseded. (2) The `finding_label` block reworded a label that only
  the Group-only reports read (Codex): removed, so those reports are byte for byte main's on the same seed.
  (3) Severity-first paging (OB1-lite's own second-pass fix) filled the lab's 500-row page with 456
  unmanaged and 44 unresolved rows, so the Access granted tab's Granted section and its granted and
  built-in filters rendered empty beside tiles that counted them (OB1-lite, the implementation's review):
  `all_bindings` and `/bindings/findings` take `finding=<tier>`, and the page's single-tier filters ask
  for their tier; the mixed views keep the one page. (4) The export bar's partial note pushed the page 29
  px sideways at 375 px once every lab page was partial (OB1-lite): it wraps. (5) No test read a
  ServiceAccount subject through the real TLS reader — the mock fixture names Group and User subjects only
  (Grok, Codex, OB1-lite): a mock e2e test adds one in memory. Also, the Unmanaged filter's copy said
  "other bindings on this cluster carry the label", which is false for an account or a person on a host
  with no label anywhere (OB1-lite, below its bar): reworded.
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
them with the same rule — the platform's own identities silenced as `built_in` by the estate's existing
platform classification, everything else a finding unless its binding carries the label or the exception —
and show them everywhere the finding is shown (the log, the Access granted and RBAC policy pages, the counts
on the Overview and the KPI page, the API, the reports and `/metrics`).

Out of scope, each stated in the notes above with its reason: any inference of legitimacy from how a grant
was applied beyond that classification (no Helm, OLM or Argo CD label, no binding name); a change to
`/user-bindings`; a ServiceAccount stream in `binding_event`; a `subject_kind` label on the metric family; a
rename of `group_name`.

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
| subject entries by kind (before deduplication) | Group 205 (50 cluster-wide, 155 namespaced); **ServiceAccount 685** (234, 451); **User 35** (16, 19) |
| stored subject rows by kind (after deduplication) | Group 205; **ServiceAccount 675**; **User 35** — **915** rows in total |
| `apiGroup` on subject entries | Group and User `rbac.authorization.k8s.io` (240 entries), ServiceAccount absent (685 entries) — the defaults of §2.1, nothing else |
| ServiceAccount subjects with no `namespace` | **26**, all on RoleBindings — 13 of them, 9 written by OLM (`cert-manager-operator.v1.20.0`, `grafana-operator.v5.24.0`, `group-sync-operator.v0.0.36`, …), 3 by the cluster-version operator (`console-operator`, `cluster-image-registry-operator`, `csi-snapshot-controller-operator-role`) and 1 by hand — so §2.1's default applies to real objects here |
| subject entries a binding repeats | **10**, every one a ServiceAccount an OLM-written RoleBinding names twice (`metallb-operator…` four accounts, and one each on six others); the reader keeps one, so 925 entries store **915** rows |
| RoleBinding ServiceAccount subjects naming another namespace | 85 — a stored namespace must be the subject's own, not the binding's, when the subject spells one |
| bindings by subject-kind set | Group only 200, ServiceAccount only 663, User only 27, Group+User 3, ServiceAccount+User 3 |
| `rbac.ocp.io/config-source` | 51 bindings: `baseline-nonprod-rbac` 26, `baseline-cluster-rbac` 11, `group-sync-dashboard` 8, `baseline-prod-rbac` 3, `custom-cluster-rbac` 1, `bdp-oud-group-rbac` 1, `trino-oud-group-rbac` 1 |
| subject rows on labelled bindings | Group 44; **ServiceAccount 7 — every one of them this chart's own** (`group-sync-dashboard-auth-delegator`, `-login-capture-audit`, `-reader`, `-cluster-secrets`, `-grafana-discovery`, `-secrets-mint`, `-fleet-account`); User 0 |
| `rbac.ocp.io/unmanaged-exception` | 0 |
| User subject names | 16 distinct: `system:kube-scheduler` 6, `system:kube-controller-manager` 5, `system:serviceaccount:openshift-kube-apiserver:check-endpoints` 5, `jdoe` 3, and one or two each of `kubeadmin`, `system:admin`, `system:master`, `system:kube-apiserver`, `system:kube-proxy`, `ocp-oauth-bind-serviceid`, `dana.lee`, `asmith`, `bwilliams`, `tmp-contractor-9931`, `jane.smith`, `developer` |

The platform classification, with the shipped defaults (`environments/crc.yaml` sets no `platformNamespaces`),
applied to those rows by the rules this spec builds — the account's effective namespace, the User's name
(the script and its output are in the session log):

| | |
|---|---|
| ServiceAccount rows with no label and no exception | 668; **469** of them in a platform namespace (`openshift-*`, `kube-*`, `default`, …) — 289 if the binding's namespace were the key instead, which it is not |
| User rows with no label and no exception | 35; **24** of them `is_platform_user` (`system:kube-scheduler` ×6, `system:kube-controller-manager` ×5, `system:serviceaccount:…:check-endpoints` ×5, `kubeadmin` ×2, …) |
| remaining | **210 rows on 203 bindings**: 199 accounts — `metallb-system` 25, `group-sync-operator` 20, `kyverno` 17, `cert-manager` 16, `group-sync-dashboard` 10, `namespace-configuration-operator` 10, `mongodb-poc` 9, `cert-manager-operator` 8, `hostpath-provisioner` 8, `envoy-gateway-system` 7, `modernize-demo` 4, `ldap-testing` 3, and 2 in each of 33 project namespaces — and 11 people (`jdoe` ×3, `ocp-oauth-bind-serviceid` ×2, `asmith`, `bwilliams`, `dana.lee`, `developer`, `jane.smith`, `tmp-contractor-9931`) |
| of the 199 accounts | 86 are OpenShift's per-project `system:image-builders` → `builder` and `system:deployers` → `deployer` RoleBindings (43 + 43, of 112 + 112 on the cluster, every one annotated "auto-managed by a controller"); the rest are operators' own accounts in their own namespaces — the namespaces `PlatformNamespaces`' docstring names as what an estate adds through `additionalNames` |
| remaining with the controller defaults too | **124 rows on 117 bindings**: 113 accounts — `metallb-system` 23, `group-sync-operator` 18, `kyverno` 15, `cert-manager` 14, `group-sync-dashboard` 8, `namespace-configuration-operator` 8, `mongodb-poc` 7, `cert-manager-operator` 6, `hostpath-provisioner` 6, `envoy-gateway-system` 5, `modernize-demo` 2, `ldap-testing` 1 — and the same 11 people; 579 rows silenced in all (469 by namespace, 24 by `is_platform_user`, 86 by the controller defaults) |
| User subjects spelt `system:serviceaccount:<ns>:<name>` | 5, all `openshift-kube-apiserver:check-endpoints`, platform by the `system:` prefix and by the namespace alike |
| with `values.yaml`'s own reference answer applied (`additionalSuffixes: ["-operator", "-manager", "-provisioner"]`, `additionalNames: ["kyverno", "group-sync-dashboard"]`) | **49 rows on 46 bindings** remain: `metallb-system` 23, `mongodb-poc` 7, `envoy-gateway-system` 5, `modernize-demo` 2, `ldap-testing` 1, and the 11 people — the values path the lab proof exercises (§5) |

So on the lab, after this spec: the chart's 7 ServiceAccount rows are `ok` by its own label, 579 platform
rows join the built-in tier, and the remaining **113 ServiceAccount and 11 User rows are `unmanaged`** until
labelled — with no gate to open; the Group arm's gate is open anyway (43 policy-operator Group rows beside the
chart's one) — 124 finding rows on 117 bindings: the summary line counts the bindings (117) and lists 20 per
cycle by `maxPerCycle`; the tiles, the KPI page and `/metrics` count the rows (124). That is the capability the
operator asked for; which of them are legitimate is their decision, made by labelling or by naming a namespace
in `platformNamespaces`.

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
| resolution tiers (`dangling`, `built_in`, `unresolved`) | as today | `built_in` when the account's effective namespace is one `platformNamespaces` names — the platform's own identity, never a finding; the other two never | `built_in` when `is_platform_user` names it (`system:*`, `kubeadmin`); the other two never |
| `unmanaged` | group operator-synced, no label, no exception, the gate open | not the platform's (`is_platform = 0`), no label, no exception | not the platform's (`is_platform = 0`), no label, no exception |
| `ok` | otherwise | otherwise | otherwise |
| the gate | some other Group-subject binding on the cluster carries `rbac.ocp.io/config-source` ≠ `group-sync-dashboard` (#354, unchanged) | none | none |
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

The three resolution arms apply to Group subjects only (`b.subject_kind = 'Group' AND …`). A fourth arm,
before provenance, makes a ServiceAccount or User row whose stored `is_platform` flag is set `built_in`: the
platform's own identity, never a finding (the note above). The provenance
arm requires, for a Group subject, an operator-synced group and #354's gate — some other Group-subject
binding on the cluster labelled by something other than this chart, read over Group rows only
(`m.subject_kind = 'Group'`), so the arm is #354's predicate, guarded by `subject_kind = 'Group'` because the table
now holds other kinds — and, for the other two kinds,
nothing but the absence of a label and an exception (`(b.subject_kind <> 'Group' OR …)` on both
conditions): no gate — the platform's own rows never reach it, because the `is_platform` arm above is decided
first, and for the rest the operator's label or exception is the only silence. The joins to
`group_state` and `managed_group_seen` — and the reach join — carry
`AND b.subject_kind = 'Group'`, so a ServiceAccount or User named like a group never borrows that group's
object, its sync record or its members: an account named `app-ocp-rbac-x` is judged on provenance alone
and its reach is `null`. No Helm, OLM or Argo CD label and no binding name enters the `CASE`; a `system:` name
or a platform namespace enters it only through the stored `is_platform` flag the poller computed, never
through the name in the row: a User stored with `is_platform = 1` is `built_in`, and the same name stored
with `0` is `unmanaged` when unlabelled (`test_the_store_classifies_a_user_by_the_stored_flag_not_its_name`).

### 3.5 Group-only readers, guarded

Each query in §2.3's Group-only list gains `subject_kind = 'Group'` in the same clause it already filters
on. Their outputs — a group's bindings, a person's access through groups, the namespace audit's via-groups
counts, the self-tier reach gate, a group's `binding_count`, the reports' group counts — are byte-identical
before and after this spec for a table that holds Group rows only, which the existing tests hold.

### 3.6 The poller and the announcer

The row dict carries `subject_kind`, `subject_namespace`, `is_platform` — computed by
`_binding_is_platform` from the settings' `platform_namespaces` (the Poller passes them; a direct call gets
the shipped defaults) and `is_platform_user` — and, the adjacent fix, `audit_stamped`. The
refresh line names the kinds it read. `audit.py` gains `AuditLogProgress`, the poll thread's schedule for the capped log — a finding first
seen this cycle is listed this cycle, then the least recently listed follow, so a new hand-made grant
is announced on the refresh that finds it and a backlog rotates through the cap instead of the same
twenty every cycle (invariant I6, rewritten) — and `subject_label(row)`, the one spelling of a subject
for the log and the reports: `group <name>`, `ServiceAccount <namespace>/<name>`, `user <name>`; the plan's
evidence lists `subjects` (the `groups` list, renamed, holding those labels), only for the rows classified
`unmanaged`, as before. The WARNING line reads `grants <role> to <subjects>`, which for a Group is the same
text as today; the RESOLVED line is unchanged.

### 3.7 The API

`/bindings/findings` rows gain `subject_kind` and `subject_namespace`; `group_name` is documented as the
subject's name; a `finding=<tier>` query pages one tier's rows (the page's single-tier filters ask for
theirs, because a page ordered review tiers first holds no `ok` or `built_in` row on a cluster with more
review rows than the page — OB1-lite, review of #360), with `counts` and `total` still the cluster's and
`truncated` measured against that tier's count. The counts, `/api/clusters`'s `unmanaged_bindings` and the
KPI posture count rows of every kind through the same `CASE`. No endpoint is added.

### 3.8 The page

The Access granted tab's header says "Bindings on this cluster" and "Granted"; its note names the three
kinds; the RBAC policy tab renders its findings whether or not the namespace-configuration-operator is
installed, with the "not installed" card beside them; the subject column is "Subject named by the binding", rendered by `subjectCell`: a Group drills as
before, a ServiceAccount is `ServiceAccount <namespace>/<name>` and a User `user <name>`, each with the kind
in muted text before the name and no drill. Search matches the namespace too; the export carries both new
fields. The Unmanaged notes say a grant of any kind is a finding and the label or annotation on the binding
is what clears it. The RBAC policy tab's hero and tile read `counts.unmanaged`, and its list says how many
of that total it holds. The Access granted tab's single-tier filters (granted, built-in, unmanaged) fetch their tier from the
server; its export bar wraps at phone width. The narrowed reader's own-access view, Home, the group pages
and the namespace audit are Group-only readers and do not change.

### 3.9 The reports

`_OMIT_SYSTEM_GROUP_SUBJECTS` becomes kind-aware — it drops `system:` **Group** subjects by name and every
platform ServiceAccount or User row by its stored flag (`AND b.is_platform = 0`), so a User named
`system:kube-scheduler` is omitted by the flag the poller stored, never by its name — and `_GROUP_SUBJECTS_ONLY`
guards the group counts. `Snapshot.group_bindings` takes `kinds` (default `("Group",)`, so
`namespace-access`, `privileged-access`, `access-matrix` and `access-certification` are unchanged); the
`binding-findings` report asks for every kind and names each subject with `subject_label` and its own
definitions; `finding_label`, which only the Group-only reports read, is unchanged. `findings_counts`
counts every kind, which is what
`compliance-snapshot`'s Unmanaged figure now says, and its RBAC figures name their populations: "Group
bindings (Group subjects)", "Unmanaged (every subject kind)", "Platform identity grants (excluded from the
direct-user figures)".

### 3.10 Metrics and KPI

`FINDINGS` gains `unmanaged`, so `gsd_bindings_total{finding="unmanaged"}` is pre-seeded at 0 like the
other tiers; the family's help text names the three kinds. No label is added (the note above). The KPI
rollup's `bindings` and the page's Bindings and To review figures count rows of every kind; on the lab the
To review figure rises by 703 the first refresh after this deploys, and that is the finding, not a
regression — the CHANGELOG entry says so.

### 3.12 The marked sites — `git grep "PLATFORM-CLASSIFICATION (#255, #353)"`

The classifiers and their defaults: `home.py` (`PLATFORM_NAMESPACE_PREFIXES`/`PLATFORM_NAMESPACES`,
`PLATFORM_CONTROLLER_BINDINGS`, `is_platform_namespace`);
`config.py` (`PlatformNamespaces.matches`, the `Settings.platform_namespaces` field,
`_platform_namespaces_setting` and its wiring in `load_settings`); `kube.py` (`PLATFORM_USER_PREFIXES`/`NAMES`,
`is_platform_user`'s return). The values path: `values.yaml` `platformNamespaces`, `templates/configmap.yaml`
where it becomes `clusters.yaml`, `_helpers.tpl` `gsd.validatePlatformNamespaces`. The existing consumers:
`api.py` (the namespace index's `platform` flag and its stale-pattern report, Home's `derive_answer`, the
direct-user view's `excluded_platform`), `kube.py` `_user_binding_views`, `poller.py`'s user-row flag,
`store.py`'s two `user_binding` predicates. The finding path (this spec): `poller.py` `_binding_is_platform`
(three decisions), the `PlatformNamespaces()` default when a caller passes none, and the row dict, `store.py`'s column, migration 20's column and the two `built_in` arms of
`_FINDING_CASE`, `reporting/snapshot.py`'s omit and its six `user_binding` predicates (the direct-user view's
flag on the reports' copy), `metrics.py`'s `FINDINGS` (a platform row counts under `built_in`), `index.html`'s
Home filters, its two platform badges and its export column. The consumers the review of #361 found unmarked, now marked:
`home.py` `derive_answer`'s signature (its `platform` callable and default) and its `ns_row` (the classifier the API passes in), `state.py`'s direct-user alert, `poller.py`'s
refresh-line people count and the Poller's hand-off of the settings' classifier, `api.py`'s Home cluster-wide counts, `store.py`'s Group `system:` rule and people count in
`namespace_detail`, the direct-grant count in `namespaces` and `user_bindings_by_namespace`'s two predicates, and
`index.html`'s namespace-index platform rows and hidden-with-findings list, Home's via/wide filters and the hand-made badge.
The guard also holds every read or write of the stored `is_platform` flag, in Python or in SQL, under `gsd/`.

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
claim; and the edits to existing tests that pin the old shape. Every test below fails on main (`244d4ab` when written; on `35fcddb`, the amendment's base, the two new modules error at collection against main's `gsd` — measured)
(the attribute, column, key or word does not exist there) and passes with §7 applied — except the values-path
test below, which pins existing #255 behaviour and passes on main too (measured, OB1-lite's review of #361).

- **The reader** (`TestReader`): every kind is kept with its kind; a RoleBinding ServiceAccount subject
  with no namespace stores the binding's; one with a namespace stores its own; a ClusterRoleBinding
  ServiceAccount stores its own; a User stores `''`; an unknown kind or an unnamed subject contributes
  nothing.
- **The marker** (`tests/test_platform_classification_marker.py`): every Python site that decides or consumes
  "platform" is marked, the marked path covers every file §3.12 names, and the chart path is marked.
- **The controller bindings and the default account** (`TestControllerBindingsAndTheDefaultAccount`): the two
  controller bindings are silent in a project namespace; any other shape with the same account or name — another
  role, another binding name, another account, another namespace, a `Role` instead of the ClusterRole — is
  reported; the third is a `system:` group and the Group arm decides it; a hand-made `admin` grant to SA
  `default` is reported in a project namespace and silent in a platform one; the lab's own
  `cluster-version-operator` → `cluster-admin` → SA `default` in `openshift-cluster-version` is silent, decided
  by the account's own namespace; `additionalPrefixes` and `additionalSuffixes` silence their namespaces; the
  direct-user view is unchanged.
- **The platform rule** (`TestPlatformRule`, through a real `refresh_bindings` against a fake client): an
  account in a default platform namespace is silent (`built_in`); an account in a namespace added via
  `additionalNames` is silent, and the same row reclassifies on the next refresh when the settings change;
  an account elsewhere is reported, then silent once its binding is labelled; a `system:` user and
  `kubeadmin` are silent and a person is not; the Group arm is unchanged beside platform rows; the reports
  omit a platform row as they omit a virtual group.
- **The classification** (`TestClassification`): an unlabelled ServiceAccount grant is `unmanaged` on a
  cluster where the policy operator is in use; the operator's label on the binding makes it `ok`; the
  exception annotation makes it `ok`; a User row stored with `is_platform = 0` is `unmanaged` whatever its
  name (the poller sets the flag; `TestPlatformRule` proves `system:` users are silent); on a cluster whose
  only labels are the chart's, the chart's ServiceAccount rows are `ok`, a
  hand-made account is `unmanaged` and a hand-made Group grant is `ok` until one policy label opens the
  Group gate (#354); an unlabelled account is a finding on a cluster with no label anywhere; a labelled
  account does not open the Group gate; an account named like a synced group is judged on provenance and
  its reach is `null`; the store classifies a User row by the stored flag, not its name; `all_bindings`
  carries the three new columns.
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
- **The values path** (an edit in `tests/test_config.py`, the logic review's one test gap):
  `platformNamespaces: {}` and the shipped block of three empty lists both load as the shipped rule, and
  `additionalSuffixes: ["-operator"]` widens it without touching the prefixes — a pin of existing #255 behaviour,
  which passes on main too.
- **The implementation review's** (`TestAuditLogProgress`: a backlog rotates through the cap and a new
  finding goes first, the poll loop announces a new grant on the refresh that finds it, and without a
  scheduler the sorted first page as before; `TestGroupOnlyReportWording`: `finding_label` unchanged;
  `TestOneTierPage`: a page smaller than the review items still reaches the granted rows through
  `finding=`; in `test_ui.py`, the granted filter asks the server for its tier and a partial export note
  fits a phone; in the mock cluster's tests, a ServiceAccount subject read through the real TLS reader).
- **The review's six** (`TestDuplicateSubjects`, `TestSeverityFirstPage`, `TestTotalOrder`,
  `TestAnOlderCopyInTheRollingWindow`, `TestRolePicker`, and the every-kind total in the compliance test): both
  orderings end on every primary-key column, so a page walks the set exactly once; a subject a binding names twice is one
  row; a page of findings holds the review tiers before the rest; a schema-19 copy is read as Group rows;
  a role bound only to an account is not offered by the report form; the Unmanaged figure sits under the
  total it is a part of.
- **Edits to pinned shapes:** `tests/test_rbac.py#TestParsing` keeps every kind; `tests/test_binding_reach.py`
  adds the two columns to the exact set; `tests/test_audit_stamp.py` reads `evidence[key]["subjects"]`; the
  three `user_version == 19` pins read 20; `tests/test_ui.py`'s four wording assertions move with the tile
  labels, and two UI tests are added — a ServiceAccount and a User row render named in full under
  Unmanaged with no drill, and the RBAC policy tab's hero counts the cluster.

## 5. Verification on the lab

Before the deploy, with `KUBECONFIG` set to the lab's scratch kubeconfig: read `PRAGMA user_version` from the
running pod's `/data/gsd.db` and record it in the evidence. Migration 20 was edited in place after PR #360 was
opened (the `is_platform` column joined it), and `_migrate` skips a database already at 20, so a database that
ran #360's version of the migration would never gain the column (OB1-lite, review of #361). #360 was never
deployed to the lab, so the reading is expected to be 19 — deploy as is. If it reads 20 without the column
(`PRAGMA table_info(rbac_group_binding)`), stop and tell the orchestrator before anything is built (the
smallest remedy would be a migration 21 `ALTER TABLE … ADD COLUMN is_platform`, approved 2026-09-25 only
against that measurement). Then, after the deploy (`local-development/release-crc.sh --argocd`, Synced/Healthy,
the commit verified in-pod, the PVC UIDs identical):

1. `PRAGMA user_version` in the pod's database reads 20 (`oc exec … -- python3 -c` over `/data/gsd.db`),
   and the report pod's `/report/readyz` is 200.
2. The first refresh line reads `refreshed N bindings for dashboard (205 Group, 675 ServiceAccount, 35 User
   subjects)` give or take the day's drift, and the summary line reads `NNN outside the policy system (20
   listed below, … held back by the per-cycle cap)` with NNN the binding count of §2.2's remainder — it counts
   bindings, the tiles count rows; the Built-in tile carries the platform rows beside the virtual groups —
   against the counts of §2.2.
3. `GET /api/clusters/dashboard/bindings/findings` as kubeadmin: `counts.unmanaged` equals the sum of
   unlabelled ServiceAccount and User rows plus any unlabelled synced-group grant; the chart's seven
   ServiceAccount rows are in `ok` with `managed_source: group-sync-dashboard`.
4. **The evidence the issue's Definition of Done names.** In a namespace of its own (`default` is a
   platform namespace, so a grant there is silent by rule): `oc create namespace gsd-evidence-353`,
   `oc create serviceaccount u1-evidence-sa -n gsd-evidence-353`, then a hand-made grant
   (`oc create clusterrolebinding u1-evidence --clusterrole=view --serviceaccount=gsd-evidence-353:u1-evidence-sa`),
   wait one refresh: the WARNING names `ServiceAccount gsd-evidence-353/u1-evidence-sa` — on that refresh,
   because a finding first seen is listed first, ahead of the lab's backlog of 117 bindings (`AuditLogProgress`) — the
   row is in `unmanaged`, the tile counts it. Label it as the operator would
   (`oc label clusterrolebinding u1-evidence rbac.ocp.io/config-source=platform-team`), wait one refresh:
   the row is `ok`, `managed_source: platform-team`, no WARNING. Then the platform half: a grant to an
   account in a platform namespace (`oc create clusterrolebinding u1-platform --clusterrole=view
   --serviceaccount=openshift-monitoring:u1-platform-sa`) is `built_in` on the next refresh, never in
   `unmanaged`, no WARNING. Remove both.
5. The Access granted page under `#page=bindings&cluster=dashboard` with the Unmanaged filter shows the
   account rows named in full; the RBAC policy page's hero equals `counts.unmanaged`; the Overview tile and
   the KPI page's To review carry the same number; `/metrics` reports
   `gsd_bindings_total{cluster="dashboard",finding="unmanaged"}` equal to it, with no name in any label.
6. The `binding-findings` report generated from the library lists the same account rows under Unmanaged.
7. **The values path.** By PR, `environments/crc.yaml` gains the reference answer `values.yaml`'s own comment
   documents — `platformNamespaces: {additionalSuffixes: ["-operator", "-manager", "-provisioner"],
   additionalNames: ["kyverno", "group-sync-dashboard"]}` — and main is redeployed (PVC UIDs identical). On the
   next binding refresh the accounts of `cert-manager`, `cert-manager-operator`, `group-sync-operator`,
   `hostpath-provisioner`, `kyverno`, `group-sync-dashboard` and `namespace-configuration-operator` are `built_in`
   and — the platform arm preceding provenance — the chart's own 7 labelled rows in `group-sync-dashboard` move
   from `ok` to `built_in` (measured through the store on the dump, OB1-lite: `ok` 7 → 0, `built_in` 740 → 822), so
   the Granted count drops by 7; nothing else changes: 49 rows on 46 bindings remain (§2.2), by namespace `metallb-system` 23, `mongodb-poc`
   7, `envoy-gateway-system` 5, `modernize-demo` 2, `ldap-testing` 1, plus the 11 people; the rendered ConfigMap's
   `clusters.yaml` carries the `platformNamespaces` block and the pod's log the reclassified refresh.

## 6. What changes, for whom, and what it costs

- **An operator with a policy operator** (the lab): every unlabelled ServiceAccount and User grant outside
  the platform's own namespaces, names and controller bindings is a finding from the first refresh after
  upgrade — 124 rows on 117 bindings on the lab under the shipped defaults, 579 platform rows silent under the
  Built-in tile.
  The log lists 20 bindings per cycle and counts the rest; the tiles, the KPI page and the metric carry the full number. The way down is the label on each
  legitimate grant, which is the operator's decision and the whole point.
- **An operator with no policy operator** (a plain host): every unlabelled ServiceAccount and User grant
  outside the platform's namespaces and names is a finding from the first refresh there too, and the
  estate's `additional*` lists are how it names its own operators' namespaces as the platform's; the Group finding stays silent, as #354 left it, until a Group
  binding carries a policy label. This spec changes nothing about the Group arm; the asymmetry is on #353.
- **Storage:** one row per (binding, subject) of every kind — on the lab 915 rows instead of 205 (925 subject entries, 10 of them a
  ServiceAccount an OLM RoleBinding names twice, kept once), plus the
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
    """Flatten one binding into a row per distinct subject, whatever its kind.

    Subject matching is on ``kind`` exactly, against the three kinds RBAC defines
    (SUBJECT_KINDS); a subject of any other kind, or with no name, contributes nothing. Every
    kind is a grant the unmanaged finding must see (#353, SPEC_U1).

    A ServiceAccount subject carries a namespace. On a ClusterRoleBinding the API server
    requires it (pkg/apis/rbac/validation/validation.go, ValidateRoleBindingSubject); on a
    RoleBinding it may be omitted, and the authorizer then reads it as the binding's own
    namespace (pkg/registry/rbac/validation/rule.go, appliesToUser: "default the namespace to
    namespace we're working in"). That resolved namespace is what is stored, so the row names
    the account RBAC actually matches — `system:serviceaccount:<namespace>:<name>`. Measured on
    the lab: 26 of 685 ServiceAccount subject entries omit it, on 13 RoleBindings — 9 written by
    OLM, 3 by the cluster-version operator, 1 by hand. User and Group subjects have no
    namespace; "" is stored, as for a ClusterRoleBinding's own.

    A subject a binding names twice is one row: the authorizer grants it once and the store's
    primary key keeps one. OLM writes some RoleBindings that way (10 repeated ServiceAccount
    entries on the lab, `metallb-operator…` naming four accounts twice), and a reader that yielded
    both made the refresh line count 925 subjects for the 915 rows the store held.
    """
    meta = obj.get("metadata") or {}
    role_ref = obj.get("roleRef") or {}
    labels = meta.get("labels") or {}
    annotations = meta.get("annotations") or {}
    # ClusterRoleBindings have no namespace; "" rather than None so it can sit in a NOT NULL
    # primary key column without a sentinel row per binding.
    binding_namespace = meta.get("namespace", "") or ""
    rows: list[BindingView] = []
    seen: set[tuple[str, str, str]] = set()
    for subject in obj.get("subjects") or []:
        kind = subject.get("kind")
        if kind not in SUBJECT_KINDS or not subject.get("name"):
            continue
        subject_namespace = ((subject.get("namespace") or binding_namespace)
                             if kind == SERVICE_ACCOUNT_KIND else "")
        identity = (kind, subject_namespace, subject["name"])
        if identity in seen:
            continue
        seen.add(identity)
        rows.append(
            BindingView(
                binding_kind=binding_kind,
                binding_namespace=binding_namespace,
                binding_name=meta.get("name", ""),
                role_kind=role_ref.get("kind", ""),
                role_name=role_ref.get("name", ""),
                group_name=subject["name"],
                subject_kind=kind,
                subject_namespace=subject_namespace,
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
    -- The platform's own identity, never a finding (the operator's rule, #353): a ServiceAccount whose
    -- effective namespace the estate's platformNamespaces name, or a User is_platform_user names.
    -- Computed at poll time from the settings (poller._binding_is_platform), so a values change
    -- reclassifies on the next refresh; a platform row is `built_in`, like a system: group.
    -- PLATFORM-CLASSIFICATION (#255, #353): the stored flag the finding reads
    is_platform         INTEGER NOT NULL DEFAULT 0,
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
                   is_platform         INTEGER NOT NULL DEFAULT 0,   -- PLATFORM-CLASSIFICATION (#255, #353)
                   group_name          TEXT NOT NULL,
                   observed_at         TEXT NOT NULL,
                   managed_source      TEXT,
                   exception           TEXT,
                   audit_stamped       INTEGER NOT NULL DEFAULT 0,
                   PRIMARY KEY(cluster_id, binding_kind, binding_namespace, binding_name,
                               subject_kind, subject_namespace, group_name)
               )""",
            # OR IGNORE: the replay converges from a v20 table that is already populated. A crash
            # cannot leave one — the INSERT opens the connection's implicit transaction and the DROP,
            # the RENAME and the version write ride in it until Store.__init__ commits, so a crash
            # rolls them back together and only the empty CREATE stands (measured, SPEC_U1 notes) —
            # but a hand repair can, and _migrate tolerates no IntegrityError.
            """INSERT OR IGNORE INTO rbac_group_binding_v20(
                   cluster_id, binding_kind, binding_namespace, binding_name, role_kind, role_name,
                   subject_kind, subject_namespace, is_platform, group_name, observed_at,
                   managed_source, exception, audit_stamped)
               SELECT cluster_id, binding_kind, binding_namespace, binding_name, role_kind, role_name,
                      'Group', '', 0, group_name, observed_at,
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
        rows = [{"subject_kind": GROUP_KIND, "subject_namespace": "", "is_platform": 0, "managed_source": None,
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
                       role_kind, role_name, subject_kind, subject_namespace, is_platform, group_name, observed_at,
                       managed_source, exception, audit_stamped)
                   VALUES(:cluster_id,:binding_kind,:binding_namespace,:binding_name,
                          :role_kind,:role_name,:subject_kind,:subject_namespace,:is_platform,:group_name,:observed_at,
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
                        -- PLATFORM-CLASSIFICATION (#255, #353): a system: group is the platform's — that decides OpenShift's
                        -- third per-project controller binding, system:image-pullers → Group
                        -- system:serviceaccounts:<namespace> (the comment beside home.py's controller defaults)
                        WHEN b.subject_kind = 'Group' AND g.name IS NULL AND b.group_name LIKE 'system:%'
                                                           THEN 'built_in'
                        WHEN b.subject_kind = 'Group' AND g.name IS NULL
                                                           THEN 'unresolved'
                        -- The platform's own identities are never a finding — the operator's
                        -- long-standing rule (#353): a ServiceAccount whose effective namespace
                        -- the estate's platformNamespaces name (the code's defaults plus the
                        -- values file's additional* lists), or a User is_platform_user names.
                        -- Computed at poll time and stored as is_platform; such a row joins the
                        -- built_in tier beside the system: groups — real access by design,
                        -- nothing of the operator's to resolve, nothing to review.
                        -- PLATFORM-CLASSIFICATION (#255, #353): the finding's arm
                        WHEN b.subject_kind <> 'Group' AND b.is_platform = 1
                                                           THEN 'built_in'
                        -- Provenance: a grant NO policy system manages is somebody bypassing
                        -- governance by hand. For a Group subject that is only worth saying
                        -- when the group is operator-SYNCED and the policy operator is in use
                        -- at all — some other Group-subject binding on the cluster carries a
                        -- label, read over Group rows only so this arm is exactly #354's — or
                        -- every binding on a cluster that has never heard of config-source
                        -- labels would flag; this chart's own label is not that evidence, its
                        -- auditor binding being on every host by default (#312). A
                        -- ServiceAccount or User row that reaches this arm is not the
                        -- platform's — those are already `built_in` above — so it is said
                        -- whenever the binding carries no label and no exception, on every
                        -- host, with no gate; a Helm, OLM or Argo CD label or a binding's name
                        -- never excludes it, only the operator's decision on the binding does
                        -- (#353, SPEC_U1).
                        -- An exception annotation on the binding acknowledges a deliberate one
                        -- and suppresses the finding.
                        WHEN b.managed_source IS NULL
                             AND b.exception IS NULL
                             AND (b.subject_kind <> 'Group' OR s.group_name IS NOT NULL)
                             AND (b.subject_kind <> 'Group' OR EXISTS (
                                      SELECT 1 FROM rbac_group_binding m
                                       WHERE m.cluster_id = b.cluster_id
                                         AND m.subject_kind = 'Group'
                                         AND m.managed_source IS NOT NULL
                                         AND m.managed_source <> '""" + CHART_CONFIG_SOURCE + """'))
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
                      b.role_kind, b.role_name, b.subject_kind, b.subject_namespace, b.is_platform, b.group_name,
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
from .kube import (AUTH_FAILED, OK, SERVICE_ACCOUNT_KIND, SUBJECT_KINDS, UNREACHABLE, USER_KIND, ClusterClient,
                   ClusterError, GroupSyncView, GroupView, dn_equal, is_platform_user)
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
                "is_platform": _binding_is_platform(b, platform),   # PLATFORM-CLASSIFICATION (#255, #353)
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

<!-- block: local-development/gsd/audit.py | edit -->
```python
        for key in list(stamp) + list(unstamp)
    }
    return StampPlan(stamp=stamp, unstamp=unstamp, capped=capped, evidence=evidence)
```
```python
        for key in list(stamp) + list(unstamp)
    }
    return StampPlan(stamp=stamp, unstamp=unstamp, capped=capped, evidence=evidence)


class AuditLogProgress:
    """Which findings the capped log lists this cycle: the new ones first, then the least recently
    listed. One per cluster poll thread, in memory; it changes no finding and writes no label.

    `plan_audit_stamps` takes a sorted prefix, which converged while the write path stamped each
    object it listed. In log mode nothing is stamped, so the same first `max_per_cycle` keys were
    listed every cycle and the rest never — on the lab 20 of 689, and a hand-made grant named past
    them was never announced at all (Codex, review of #360). A restarted thread starts at the sorted
    first page again; a stable backlog is covered in ceil(N / cap) cycles; a finding first seen this
    cycle is listed this cycle.
    """

    def __init__(self) -> None:
        self._last_logged: dict[tuple[str, str, str], int] = {}
        self._cycle = 0

    def plan(self, rows: list[dict], max_per_cycle: int = 20) -> StampPlan:
        complete = plan_audit_stamps(rows, max_per_cycle=0)
        current = set(complete.stamp)
        new = current - self._last_logged.keys()
        order = sorted(current, key=lambda key: (
            0 if key in new else 1, self._last_logged.get(key, -1), key))
        selected = order[:max_per_cycle] if max_per_cycle > 0 else order
        self._last_logged = {key: self._last_logged.get(key, -1) for key in current}
        for key in selected:
            self._last_logged[key] = self._cycle
        self._cycle += 1
        return StampPlan(
            stamp=selected, unstamp=complete.unstamp,
            capped=len(order) - len(selected),
            evidence={key: complete.evidence[key] for key in selected + complete.unstamp},
        )
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
from .config import CREDENTIAL_LOOKUP, ClusterConfig, ConfigError, Settings, remote_policy
```
```python
from .config import CREDENTIAL_LOOKUP, ClusterConfig, ConfigError, PlatformNamespaces, Settings, remote_policy
from .home import PLATFORM_CONTROLLER_BINDINGS
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
def refresh_bindings(
    store: StorageBackend,
    cluster: ClusterConfig,
```
```python
def _binding_is_platform(b, platform: PlatformNamespaces) -> int:
    """The platform's own identity, never a finding — the operator's long-standing rule (#353).

    A ServiceAccount is the platform's when its effective namespace — its own, or the RoleBinding's
    when it omits one, the account the authorizer matches — is one the estate's `platformNamespaces`
    name: the code's defaults (openshift-*, kube-*, default, …) plus the values file's `additional*`
    lists, the one classifier Home and the namespace index already use (#255). A User is the
    platform's when `is_platform_user` names it (system:*, kubeadmin, the node identities), as the
    direct-user view has always decided. And OpenShift's own per-project controller bindings —
    `system:image-builders` → ClusterRole `system:image-builder` → SA `builder`, `system:deployers` →
    `system:deployer` → SA `deployer`, the subject in the binding's own namespace — are the platform's in
    EVERY namespace, matched on all three parts and nothing broader (the controller defaults in home.py).
    Computed here, where the settings are, so a values change reclassifies on the next refresh; a Group
    subject is classified by its name in the store's CASE (the third controller binding,
    `system:image-pullers` → Group `system:serviceaccounts:<namespace>`, is built_in there).
    """
    if b.subject_kind == SERVICE_ACCOUNT_KIND:
        # PLATFORM-CLASSIFICATION (#255, #353): the effective namespace against the settings' classifier
        if platform.matches(b.subject_namespace):
            return 1
        own_namespace = (b.binding_kind == "RoleBinding" and b.role_kind == "ClusterRole"
                         and b.subject_namespace == b.binding_namespace)
        # PLATFORM-CLASSIFICATION (#255, #353): OpenShift's controller bindings, all three parts, in every namespace
        return 1 if own_namespace and (b.binding_name, b.role_name, b.group_name) in PLATFORM_CONTROLLER_BINDINGS else 0
    if b.subject_kind == USER_KIND:
        # PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's rule, applied to a User subject on the finding path
        return 1 if is_platform_user(b.group_name) else 0
    return 0


def refresh_bindings(
    store: StorageBackend,
    cluster: ClusterConfig,
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
    group_changes = store.replace_bindings(
        cluster.name,
        [
```
```python
    # PLATFORM-CLASSIFICATION (#255, #353): the shipped rule when a caller passes none (a direct call, a test); the Poller passes
    # the settings', which carry the values file's additional* lists.
    platform = platform_namespaces if platform_namespaces is not None else PlatformNamespaces()
    group_changes = store.replace_bindings(
        cluster.name,
        [
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
from .audit import plan_audit_stamps
```
```python
from .audit import AuditLogProgress, plan_audit_stamps
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
    kyverno: bool = False,
    kyverno_metrics_url: str = "",
) -> str:
```
```python
    kyverno: bool = False,
    kyverno_metrics_url: str = "",
    audit_progress: AuditLogProgress | None = None,
    platform_namespaces: PlatformNamespaces | None = None,
) -> str:
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
    if audit_mode == "log":
        plan = plan_audit_stamps(store.all_bindings(cluster.name), audit_max_per_cycle)
```
```python
    if audit_mode == "log":
        # The poll thread's scheduler lists the new findings first and rotates the rest through
        # the cap; without one (a direct call, a test) the sorted first page as before.
        rows = store.all_bindings(cluster.name)
        plan = (audit_progress.plan(rows, audit_max_per_cycle) if audit_progress is not None
                else plan_audit_stamps(rows, audit_max_per_cycle))
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
        next_binding_refresh = 0.0
        own_stop = self._cluster_stops.setdefault(cluster.name, threading.Event())
```
```python
        next_binding_refresh = 0.0
        audit_progress = AuditLogProgress()
        own_stop = self._cluster_stops.setdefault(cluster.name, threading.Event())
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
                        audit_max_per_cycle=self.settings.unmanaged_audit_max_per_cycle,
                        namespaces_read=self.settings.namespaces_read_enabled,
```
```python
                        audit_max_per_cycle=self.settings.unmanaged_audit_max_per_cycle,
                        audit_progress=audit_progress,
                        platform_namespaces=self.settings.platform_namespaces,
                        namespaces_read=self.settings.namespaces_read_enabled,
```

<!-- block: docs/unmanaged-audit-design.md | edit -->
```markdown
the true total is recoverable from the line (`audit.py#plan_audit_stamps`, `poller.py#refresh_bindings`). The cap takes a
sorted prefix, so deferred findings converge instead of being re-deferred forever. Resolutions
are never capped: a closed finding must not queue behind new ones. A misclassification bug costs one
screenful of log per 300s cycle rather than a cluster's worth. Tests:
```
```markdown
the true total is recoverable from the line (`audit.py#plan_audit_stamps`, `poller.py#refresh_bindings`). Each cluster's
poll thread keeps an in-memory schedule (`audit.py#AuditLogProgress`): a finding first seen this
cycle is listed this cycle, then the least recently listed follow, the key breaking ties, so a stable
backlog is covered in ceil(N / cap) cycles and a new hand-made grant is announced on the refresh that
finds it. The sorted prefix alone converged only while the write path stamped what it listed; in log
mode it listed the same 20 of the lab's 689 every cycle and the rest never (review of #360). A
restarted thread starts at the sorted first page again; nothing about a classification or an
acknowledgement is cached. Resolutions are never capped: a closed finding must not queue behind new
ones. A misclassification bug costs one screenful of log per 300s cycle rather than a cluster's worth.
Tests:
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
        resolution tiers are Group tiers; a ServiceAccount or User row is `built_in` when it is the platform's
        own identity (the stored `is_platform` flag), else `unmanaged` or `ok`.
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
#: The `system:` test is for Group subjects only; a platform ServiceAccount or User is omitted by
#: the flag the poller stored (is_platform: a platform namespace, a system: user, kubeadmin — the
#: operator's rule, #353), so no report lists the platform's own identities as a finding either.
#: PLATFORM-CLASSIFICATION (#255, #353): the reports' omit
_OMIT_SYSTEM_GROUP_SUBJECTS = (" AND NOT (b.subject_kind = 'Group' AND b.group_name LIKE 'system:%')"
                               " AND b.is_platform = 0")
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
                         b.subject_kind, b.subject_namespace, b.is_platform, b.group_name, b.managed_source, b.exception,""" + reach
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

<!-- block: local-development/gsd/reporting/catalogue/compliance_snapshot.py | edit -->
```python
            KeyValues("RBAC", [("Group bindings", c["group_bindings"]), ("Namespaces with bindings", c["namespaces_with_bindings"]),
                               ("Dangling", findings.get("dangling", 0)), ("Unresolved", findings.get("unresolved", 0)), ("Unmanaged", findings.get("unmanaged", 0)),
                               ("Direct user grants", c["user_bindings"]), ("Platform identity grants (excluded)", c["platform_user_bindings"]),
```
```python
            # Two populations side by side (SPEC_U1): the group figure counts Group subjects, the
            # finding figures count every subject kind, so each label says which — a reader must not
            # take Unmanaged for a share of Group bindings.
            KeyValues("RBAC", [("Group bindings (Group subjects)", c["group_bindings"]), ("Namespaces with bindings", c["namespaces_with_bindings"]),
                               ("Dangling", findings.get("dangling", 0)), ("Unresolved", findings.get("unresolved", 0)),
                               ("Bindings (every subject kind)", sum(findings.values())),
                               ("Unmanaged (every subject kind)", findings.get("unmanaged", 0)),
                               ("Direct user grants", c["user_bindings"]), ("Platform identity grants (excluded from the direct-user figures)", c["platform_user_bindings"]),
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
          <strong>${d.finding ? (c[d.finding] || 0) : (d.total || 0)}</strong> ${d.finding ? `${esc(d.finding)} ` : ""}bindings,
          ${d.finding ? "by subject name" : "review items first, then by subject name"}; the cluster has more. The
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
      `This binding carries neither the policy system's <code>rbac.ocp.io/config-source</code>
       label nor an exception — a grant to an operator-synced group (where other Group bindings on
       this cluster do carry the label), a ServiceAccount or a user, made by hand outside the policy
       system. The platform's own identities are built-in and never listed here; for the rest, no
       Helm, OLM or Argo CD label and no binding name excludes it. A legitimate one is silenced by
       labelling the binding with <code>rbac.ocp.io/config-source</code>, as this chart labels its
       own RBAC, or acknowledged with the <code>rbac.ocp.io/unmanaged-exception</code> annotation, which records
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
  // — 703 on the lab once ServiceAccount and User grants count — would have shown as 500.
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
      made by hand. The platform's own identities are built-in and never listed here; for the rest,
      no Helm, OLM or Argo CD label and no binding name excludes it. Silence a legitimate one by
      labelling the binding with <code>rbac.ocp.io/config-source</code>, as this chart labels its
      own RBAC, or acknowledge it with the <code>rbac.ocp.io/unmanaged-exception</code>
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
    return header + bindingSection("Built-in",
      `Kubernetes virtual groups such as <code>system:authenticated</code> and
       <code>system:serviceaccounts:*</code>. They authorise real access and no Group object
       exists for them by design, so their absence is expected and not a fault.`,
      f.built_in);
```
```javascript
    return header + bindingSection("Built-in",
      `Kubernetes virtual groups such as <code>system:authenticated</code> and
       <code>system:serviceaccounts:*</code>, which authorise real access with no Group object by
       design — and the platform's own identities: a ServiceAccount in a namespace the chart's
       <code>platformNamespaces</code> names, a <code>system:</code> user, <code>kubeadmin</code>.
       None of these is a finding.`,
      f.built_in);
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
      + bindingSection("Built-in", "Virtual groups; no Group object is expected.", f.built_in);
```
```javascript
      + bindingSection("Built-in", "Virtual groups and the platform's own identities; never a finding.", f.built_in);
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  bindings: ["finding", "group_name", "member_count", "logged_in_count", "role_kind", "role_name",
             "binding_kind", "binding_namespace", "binding_name", "managed_source", "exception"],
```
```javascript
  // PLATFORM-CLASSIFICATION (#255, #353): the export carries the stored flag beside the tier it decides
  bindings: ["finding", "subject_kind", "subject_namespace", "is_platform", "group_name", "member_count", "logged_in_count",
             "role_kind", "role_name", "binding_kind", "binding_namespace", "binding_name", "managed_source",
             "exception"],
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  if (oc && !oc.present) {
    return `<section class="card">
      <h2>RBAC policy</h2>
      <div class="empty-note">
        The namespace-configuration-operator is not installed on <code>${esc(view.cluster)}</code>.
        This page reports the health of its NamespaceConfig and GroupConfig CRs and finds
        grants that bypass them; without the operator there is no policy system to report on.
      </div>
    </section>`;
  }
```
```javascript
  // A host with no namespace-configuration-operator still has findings: since SPEC_U1 a ServiceAccount
  // or User grant is a finding by the label alone, so the "not installed" card is a card beside the
  // findings, not a return before them (it was one while every finding needed the operator's labels,
  // and it would have hidden 703 of them on the lab).
  const operatorCard = oc && !oc.present
    ? `<section class="card">
        <h2>Policy operator</h2>
        <div class="empty-note">
          The namespace-configuration-operator is not installed on <code>${esc(view.cluster)}</code>.
          This card reports the health of its NamespaceConfig and GroupConfig CRs where it is; the grants
          outside the policy system above are found by the label on each binding and do not need it.
        </div>
      </section>`
    : configHealth(oc);
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  ${configHealth(oc)}
```
```javascript
  ${operatorCard}
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

<!-- block: local-development/gsd/store.py | edit -->
```python
                ORDER BY b.group_name, b.binding_kind, b.binding_namespace, b.binding_name""")
        params: list = [cluster_id]
        if limit is not None:
```
```python
                ORDER BY CASE finding WHEN 'dangling' THEN 0 WHEN 'unresolved' THEN 1
                                      WHEN 'unmanaged' THEN 2 WHEN 'ok' THEN 3 ELSE 4 END,
                         b.group_name, b.binding_kind, b.binding_namespace, b.binding_name,
                         b.subject_kind, b.subject_namespace""")
        # Severity first, then subject name: a page (the findings endpoint's `limit`) holds every
        # review item before any healthy or built-in row. Since #353 a cluster holds hundreds of
        # ServiceAccount rows (703 unmanaged on the lab against FINDINGS_PAGE 500), and by name
        # alone they pushed a dangling group named past them off the page (OB1-lite, SPEC_U1).
        # The key ends on every primary-key column, so limit/offset walks the set exactly once: one
        # binding can name `x` as ServiceAccounts in two namespaces (the lab's
        # system:controller:horizontal-pod-autoscaler does), or as an account and a user.
        params: list = [cluster_id]
        if limit is not None:
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
      // Users and Logins tabs' rule. The page holds FINDINGS_PAGE rows ordered by group name; the
```
```javascript
      // Users and Logins tabs' rule. The page holds FINDINGS_PAGE rows, review tiers first, then by subject name; the
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
            self._tables = {r[0] for r in self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        except sqlite3.Error as exc:
```
```python
            self._tables = {r[0] for r in self._conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            # An OLDER copy is accepted (only a newer one is refused): while the pods roll, the newest copy
            # on the volume is the previous dashboard's until the new one writes. Before migration 20 the
            # binding table held Group rows only and had no subject columns, and every binding read here
            # names them — so the old table is read through a TEMP view that says what its rows are (a TEMP
            # object shadows the copy's own name; the immutable copy itself is never written) (SPEC_U1).
            if "rbac_group_binding" in self._tables and "subject_kind" not in {
                    r[1] for r in self._conn.execute("PRAGMA main.table_info(rbac_group_binding)")}:
                self._conn.execute("CREATE TEMP VIEW rbac_group_binding AS"
                                   " SELECT *, 'Group' AS subject_kind, '' AS subject_namespace, 0 AS is_platform"
                                   " FROM main.rbac_group_binding")
        except sqlite3.Error as exc:
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
        for table in ("rbac_group_binding", "user_binding"):
            if self.has_table(table):
                roles.update(r["role_name"] for r in self._rows(f"SELECT DISTINCT role_name FROM {table} WHERE cluster_id = ?", (cluster_id,)))
```
```python
        # The roles a report's role filter can match: those bound to a group (the Group rows) or named
        # directly to a person (user_binding). A role bound only to ServiceAccounts is never offered —
        # nothing that takes this list reads account grants (SPEC_U1; on the lab 356 roles against 66).
        for table, only in (("rbac_group_binding", " AND subject_kind = 'Group'"), ("user_binding", "")):
            if self.has_table(table):
                roles.update(r["role_name"] for r in self._rows(f"SELECT DISTINCT role_name FROM {table} WHERE cluster_id = ?{only}", (cluster_id,)))
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
                          b.group_name, b.binding_name"""
        return self._rows(sql, params)
```
```python
                          b.group_name, b.binding_name, b.subject_kind, b.subject_namespace"""
        return self._rows(sql, params)
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
# and a grant is silenced by the platform rule (`platformNamespaces`, OpenShift's two per-project controller
# bindings, `system:` users) or by the operator's `rbac.ocp.io/config-source` label or the exception annotation
# on its binding (#353, SPEC_U1). Schema migration 20 (the binding table's primary key gains
# the subject's kind and namespace); `/bindings/findings` rows gain `subject_kind` and
# `subject_namespace`. MINOR: additive on the wire; every unlabelled ServiceAccount and User grant outside
# the platform's own is a finding from the first refresh after upgrade, which is the capability.
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
  # and nothing on the cluster reports it. The platform's own identities are never a finding: a
  # ServiceAccount in a namespace `platformNamespaces` (below) names, a `system:` user, kubeadmin.
  # Nothing else about how a grant was applied (a Helm or OLM label, a binding's name) excludes
  # it: a legitimate one is silenced by labelling its binding `rbac.ocp.io/config-source=<who
  # decided>`, as this chart labels its own RBAC (#312, #353).
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
and nothing on the cluster reports it. Nothing else about how a grant was applied excludes it — not
a Helm, OLM or Argo CD label, not a binding's name; a legitimate one is silenced by labelling its
binding `rbac.ocp.io/config-source=<who decided>`, as this chart labels its own
RBAC. The platform's own identities are never a finding — the operator's long-standing rule: a
ServiceAccount in a namespace `platformNamespaces` names (the defaults below, plus the estate's
`additionalPrefixes`/`additionalSuffixes`/`additionalNames`), a `system:` user or `kubeadmin` join the
built-in tier. For a Group subject the classification also requires at least one *managed* Group
binding to exist on that cluster, labelled by something other than this chart, so a cluster that has
never used config-source labels reports no Group finding rather than flagging every binding on it
(#354); any other ServiceAccount or User grant needs no such evidence — nothing silences it but the
label or the annotation on its own binding (`local-development/gsd/store.py#Store._FINDING_CASE`).
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
to exclude. Exclusion is the estate's own configured decision, twice, and never an inference from how a
grant was applied: the platform classification — a ServiceAccount in a namespace `platformNamespaces` names
(the code's defaults plus the values file's `additional*` lists), a `system:` user, kubeadmin, and OpenShift's
two per-project controller bindings, all `built_in` — and the config-source label (or the exception
annotation) the operator puts on a grant they have decided is legitimate. Nothing else silences a grant: no
Helm, OLM or Argo CD label, no binding name. A Group subject is a finding only when its group is operator-synced and the cluster
uses the policy operator (the three resolution tiers below are Group tiers, and so is the gate of I2);
a ServiceAccount or User subject, which has no Group object to resolve, is a finding whenever its
binding carries no label and no exception and it is not the platform's own identity — the operator's
long-standing rule: a ServiceAccount whose effective namespace the estate's `platformNamespaces` name
(the code's defaults and the values file's `additional*` lists), a `system:` user or `kubeadmin` is
silenced as `built_in`, never reported; nothing else is inferred, and no other labelled binding is
required. A ServiceAccount
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
label and no exception annotation and — for a Group subject — its group resolves and is
operator-synced and the cluster demonstrably uses the policy operator: some other Group-subject
binding labelled by something other than this chart, so a cluster that has never heard of
`config-source` labels reports no Group finding rather than sixty (#354, unchanged). A ServiceAccount
or User subject has no group to resolve and no gate: it is a finding on the first two conditions
alone unless it is the platform's own identity, which is `built_in` and never a finding — a
ServiceAccount whose effective namespace `platformNamespaces` names, a `system:` user, `kubeadmin`
(the operator's rule, #353; `poller.py#_binding_is_platform`). All the conditions are one SQL `CASE` (`store.py#_FINDING_CASE`), which is also what the
API, the counts and the reports read, so the log and the UI cannot disagree about what a finding
is. Tests: `test_audit_stamp.py#TestI2TargetSet.test_only_unmanaged_rows_are_stamped`,
`test_rbac.py#TestUnmanagedFinding` and `local-development/tests/test_unmanaged_subjects.py`.
```

<!-- block: docs/reference-architecture.md | edit -->
```markdown
| `built_in` | `system:*` — a virtual group that authorises real access and has no object by design |
```
```markdown
| `built_in` | `system:*` — a virtual group that authorises real access and has no object by design; or the platform's own identity — a ServiceAccount whose effective namespace `platformNamespaces` names, OpenShift's per-project `system:image-builders`/`system:deployers` controller bindings (the third, `system:image-pullers`, is a `system:` group), a `system:` user, `kubeadmin` — never a finding (#353) |
```

<!-- block: docs/reference-architecture.md | edit -->
```markdown
| `unmanaged` | the group resolves and is synced, but no policy system manages this binding and no human has annotated an exception |
| `ok` | everything else |
```
```markdown
| `unmanaged` | no policy system manages this binding and no human has annotated an exception — for a Group subject, one that resolves and is synced, on a cluster whose Group bindings show the policy operator in use; for a ServiceAccount or User subject that is not the platform's own (`built_in`), always, on every host (#353) |
| `ok` | everything else |
```

<!-- block: docs/reference-architecture.md | edit -->
```markdown
`unmanaged` additionally requires that the cluster demonstrably *uses* the policy operator —
`EXISTS (… managed_source IS NOT NULL)`. Without that clause, every binding on a cluster
that has never heard of `config-source` labels would flag.
```
```markdown
For a Group subject, `unmanaged` additionally requires that the cluster demonstrably *uses* the
policy operator — `EXISTS (… managed_source IS NOT NULL …)` over Group-subject bindings other than
this chart's own (#354). Without that clause, every Group binding on a cluster that has never heard
of `config-source` labels would flag. A ServiceAccount or User subject has no such gate: the platform's own
are `built_in` before this arm (the stored `is_platform` flag: a namespace `platformNamespaces` names, a
`system:` user, kubeadmin, OpenShift's two per-project controller bindings), and nothing silences the rest but
the label or the annotation on its own binding. The three tiers above it are Group
tiers too: an account or a person has no Group object to resolve, so its row is `built_in` (the platform's
own), `unmanaged` or `ok`; no Helm, OLM or Argo CD label and no binding name excludes it
(`docs/specs/SPEC_U1_unmanaged_subjects.md`).
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
```
```markdown
Every binding subject — a Group, a ServiceAccount or a User — classified. Despite the path, this
returns **all** bindings, including healthy ones — the caller filters.
```

<!-- block: local-development/API.md | edit -->
```json
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
```
```json
  "total": 229, "limit": 500, "offset": 0, "truncated": false,
  "counts": {"ok": 70, "dangling": 0, "unresolved": 9, "built_in": 146, "unmanaged": 4},
  "ok": [
    {"binding_kind": "RoleBinding", "binding_namespace": "prod-ns", "binding_name": "managed-admin-rb",
     "role_kind": "ClusterRole", "role_name": "admin",
     "subject_kind": "Group", "subject_namespace": "", "is_platform": 0, "group_name": "app-ocp-rbac-alpha-ns-admin",
     "managed_source": "baseline-nonprod-rbac", "exception": null, "audit_stamped": 0, "finding": "ok",
     "member_count": 2, "logged_in_count": 1}
  ],
  "dangling": [], "unresolved": [], "built_in": [],
  "unmanaged": [
    {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "shared-qa-poller",
     "role_kind": "ClusterRole", "role_name": "cluster-admin",
     "subject_kind": "ServiceAccount", "subject_namespace": "group-sync-operator", "is_platform": 0, "group_name": "shared-qa-poller",
     "managed_source": null, "exception": null, "audit_stamped": 0, "finding": "unmanaged",
     "member_count": null, "logged_in_count": null}
  ],
  "operator_configs": {}
```

<!-- block: local-development/API.md | edit -->
```markdown
Every row, in every tier, has the same shape. `member_count` is the named group's synced members
```
```markdown
Every row, in every tier, has the same shape. `subject_kind` is `Group`, `ServiceAccount` or `User`
— the three kinds RBAC defines — and **`group_name` is the subject's name whatever its kind** (the
field predates the other two kinds; since #353 every kind is a row). `subject_namespace` is a
ServiceAccount's namespace — the subject's own, or the RoleBinding's when the subject omits it,
which is how the authorizer reads it — and `""` for the other kinds. `is_platform` is `1` for the
platform's own identity: a ServiceAccount whose effective namespace the chart's `platformNamespaces` names or
one of OpenShift's two per-project controller bindings, a `system:` user or `kubeadmin`; such a row is
`built_in`, never a finding (the operator's rule, #353).
`member_count` is the named group's synced members
```


<!-- block: local-development/API.md | edit -->
```markdown
| `built_in` | `system:*` virtual group; no object expected | no |
```
```markdown
| `built_in` | a `system:*` virtual group (no object expected), or the platform's own identity — a ServiceAccount whose effective namespace `platformNamespaces` names, OpenShift's per-project `system:image-builders`/`system:deployers` controller bindings, a `system:` user, `kubeadmin` — never a finding (#353) | no |
```

<!-- block: local-development/API.md | edit -->
```markdown
| `unmanaged` | the group IS operator-synced, but no policy CR templates this binding — somebody granted access by hand | no |
```
```markdown
| `unmanaged` | no policy system labels this binding and no exception is annotated — for a Group subject, one that IS operator-synced, on a cluster where some other Group binding carries a policy label (#354); for a ServiceAccount or User subject that is not the platform's own (`built_in`), always, on every host — somebody granted access by hand | no |
```

<!-- block: local-development/API.md | edit -->
```markdown
**Suppressing an `unmanaged` finding is a cluster-admin task, performed on the object:**
```
```markdown
The three "group does not exist" tiers are Group tiers: a ServiceAccount or User subject has no
Group object to resolve, so its row is `built_in` (the platform's own identity — a namespace
`platformNamespaces` names, a `system:` user, kubeadmin, OpenShift's two per-project controller bindings —
by the stored `is_platform` flag), `unmanaged` or `ok`; no Helm, OLM or Argo CD label and no binding name
excludes it — only that classification and the operator's label or exception on the binding do (#353).

**Suppressing an `unmanaged` finding is a cluster-admin task, performed on the object** — the
exception annotation, which records why, or the policy system's label, which names who decided:
```

<!-- block: local-development/API.md | edit -->
```markdown
The poller reads that annotation on its next binding refresh and stops classifying the binding
as `unmanaged`, so it leaves this response, the RBAC policy tab and the log together. The
```
```markdown
The poller reads that annotation — or the label, `oc label clusterrolebinding <name>
rbac.ocp.io/config-source=platform-team`, as this chart labels its own RBAC — on its next binding
refresh and stops classifying the binding as `unmanaged`, so it leaves this response, the RBAC policy
tab and the log together. The
```


<!-- block: docs/CHANGELOG.md | after: ## Unreleased -->
```markdown

- **The unmanaged finding reads ServiceAccount and User subjects: the platform's own built-in, the rest silenced only by the operator's label (application 0.33.0, chart 0.54.0; #353, `docs/specs/SPEC_U1_unmanaged_subjects.md`).** The binding table holds one row per subject of every kind RBAC defines — Group, ServiceAccount and User (schema migration 20, a primary-key rebuild that carries the rows) — and a grant to any of them is `unmanaged` when its binding carries neither `rbac.ocp.io/config-source` nor `rbac.ocp.io/unmanaged-exception` — a ServiceAccount or User grant on every host, with no gate, unless it is the platform's own identity: a ServiceAccount in a namespace `platformNamespaces` names (the shipped defaults plus the estate's `additional*` lists), one of OpenShift's per-project controller bindings (`system:image-builders`/`system:deployers`, matched on all three parts, in every namespace), a `system:` user or `kubeadmin` joins the built-in tier and is never a finding, the operator's long-standing rule; every line that decides or consumes it carries the marker `PLATFORM-CLASSIFICATION (#255, #353)`, held by a test; a Group grant, as before, also only where some other Group binding on the cluster carries a policy label (#354, unchanged). Nothing else about how a grant was applied excludes it — not a Helm, OLM or Argo CD label, not a binding's name; a legitimate one is silenced by labelling its binding, as the chart labels its own. **On upgrade every unlabelled ServiceAccount and User grant outside the platform's own is a finding from the first refresh** — on an OpenShift cluster that is over a hundred rows, most of them grants OLM wrote in its operators' namespaces (124 subject rows on 117 bindings on this project's CRC lab under the shipped defaults, OpenShift 4.22, measured 2026-09-24; 579 platform rows join the built-in tier): the poller lists 20 bindings per cycle and its summary line counts the bindings; the tiles, the KPI page and `gsd_bindings_total{finding="unmanaged"}` count the rows, and the metric is now pre-seeded at 0 like the other tiers. A subject a binding names twice is one row. The findings page is ordered review tiers first, so a page never drops a dangling group behind the accounts; a report service reading a copy written before migration 20 reads its rows as Group subjects. A ServiceAccount subject that omits its namespace on a RoleBinding is stored under the binding's, the account the authorizer matches. `/bindings/findings` rows gain `subject_kind` and `subject_namespace`; `group_name` is the subject's name whatever its kind (`local-development/API.md`). The poller's WARNING spells the subject by kind (`group <name>`, `ServiceAccount <namespace>/<name>`, `user <name>`), and forwards the `rbac.ocp.io/unmanaged` label it read, which it had dropped since the label became an input. The Access granted tab names each subject in full with no drill for an account or a person; the RBAC policy tab's hero counts the cluster rather than the loaded page; the `binding-findings` report lists every kind. The group pages, a person's access through groups, the namespace audit, the binding history and `/user-bindings` are unchanged.
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
                            "subject_kind", "subject_namespace", "is_platform", "group_name", "managed_source",
                            "exception", "audit_stamped", "finding"}
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
            { counts: Object.assign({}, data.findings.counts, { unmanaged: 703 }) }); render(); }""")
        assert dash.locator("#main .hero .value").first.inner_text().strip() == "703"
        body = " ".join(dash.locator("#main").inner_text().split())
        assert "Showing the first 1 of 703" in body, body
        dash.evaluate("() => refresh()")
        dash.wait_for_function("() => data.findings && data.findings.counts.unmanaged === 1")
        self._open(dash)
```

<!-- block: local-development/tests/test_ui.py | edit -->
```python
    def _open(self, dash):
        dash.click('button.tab:text-is("RBAC policy")')
        dash.wait_for_selector("h2:text-is('RBAC policy')")
```
```python
    def _open(self, dash):
        dash.click('button.tab:text-is("RBAC policy")')
        dash.wait_for_selector("h2:text-is('RBAC policy')")

    def test_the_findings_render_when_the_policy_operator_is_absent(self, dash):
        """SPEC_U1: a host with no namespace-configuration-operator still has findings — a ServiceAccount or
        User grant is a finding by the label alone — so the "not installed" card is a card beside them, not
        a return before them. Before, the page returned that card alone: 703 findings on the lab would have
        vanished behind it (Codex, review of SPEC_U1)."""
        self._open(dash)
        # The tab paints first and fetches after: the findings and the operator card land with the fetch.
        dash.wait_for_selector("h3:has-text('Policy operator')")
        dash.wait_for_function("() => data.findings && data.findings.counts")
        errors = []
        dash.on("pageerror", lambda e: errors.append(str(e)))
        dash.evaluate("""() => { data.operatorConfigs = { present: false, configs: [] };
            data.findings = Object.assign({}, data.findings,
                { counts: Object.assign({}, data.findings.counts, { unmanaged: 703 }) }); render(); }""")
        assert dash.locator("#main .hero .value").first.inner_text().strip() == "703"
        body = " ".join(dash.locator("#main").inner_text().split())
        assert "is not installed on" in body, body
        assert dash.locator("section.card:has(h2:has-text('Grants outside')) tbody tr").count() == 1
        assert errors == [], errors
```

<!-- block: local-development/gsd/store.py | edit -->
```python
    def all_bindings(
        self, cluster_id: str, limit: int | None = None, offset: int = 0, *, reach: bool = False
    ) -> list[dict]:
        """Every binding subject, each classified — one row per (binding, subject) of every kind.
```
```python
    def all_bindings(
        self, cluster_id: str, limit: int | None = None, offset: int = 0, *, reach: bool = False,
        finding: str | None = None,
    ) -> list[dict]:
        """Every binding subject, each classified — one row per (binding, subject) of every kind.

        `finding` keeps one tier's rows only, classified by the same CASE, so a page can hold the
        tier its reader asked for: a cluster with more review rows than the page (the lab held 703
        before the platform rule, 124 after) and severity-first ordering leaves no `ok` or `built_in`
        row on it — the Access granted tab's Granted section and its two filters read empty
        (OB1-lite, review of #360).
```

<!-- block: local-development/gsd/store.py | edit -->
```python
               + self._FINDING_JOINS + (self._REACH_JOIN if reach else "") + self._FINDING_WHERE
               + """
                ORDER BY CASE finding WHEN 'dangling' THEN 0 WHEN 'unresolved' THEN 1
```
```python
               + self._FINDING_JOINS + (self._REACH_JOIN if reach else "") + self._FINDING_WHERE
               + (" AND (" + self._FINDING_CASE + ") = ?" if finding is not None else "")
               + """
                ORDER BY CASE finding WHEN 'dangling' THEN 0 WHEN 'unresolved' THEN 1
```

<!-- block: local-development/gsd/store.py | edit -->
```python
        # system:controller:horizontal-pod-autoscaler does), or as an account and a user.
        params: list = [cluster_id]
        if limit is not None:
```
```python
        # system:controller:horizontal-pod-autoscaler does), or as an account and a user.
        params: list = [cluster_id] + ([finding] if finding is not None else [])
        if limit is not None:
```

<!-- block: local-development/gsd/storage.py | edit -->
```python
    def all_bindings(
        self, cluster_id: str, limit: int | None = None, offset: int = 0, *, reach: bool = False
    ) -> list[dict]: ...
```
```python
    def all_bindings(
        self, cluster_id: str, limit: int | None = None, offset: int = 0, *, reach: bool = False,
        finding: str | None = None,
    ) -> list[dict]: ...
```

<!-- block: local-development/gsd/api.py | edit -->
```python
        offset: int = Query(default=0, ge=0, description="Bindings to skip, for paging."),
    ) -> dict:
        """Every binding subject on a cluster — Group, ServiceAccount and User — classified into
```
```python
        offset: int = Query(default=0, ge=0, description="Bindings to skip, for paging."),
        finding: str | None = Query(
            default=None, pattern="^(ok|dangling|unresolved|built_in|unmanaged)$",
            description="Only this tier's rows, paged by `limit`/`offset`. `counts` and `total` still "
                        "describe the whole cluster; `truncated` compares against this tier's count."),
    ) -> dict:
        """Every binding subject on a cluster — Group, ServiceAccount and User — classified into
```

<!-- block: local-development/gsd/api.py | edit -->
```python
        rows = store.all_bindings(cluster_id, limit=limit, offset=offset, reach=True)
```
```python
        rows = store.all_bindings(cluster_id, limit=limit, offset=offset, reach=True, finding=finding)
```

<!-- block: local-development/gsd/api.py | edit -->
```python
            "offset": offset,
            "truncated": offset + len(rows) < total,
            # From the scalar query, NOT from by_tier — by_tier holds this page. Counting
```
```python
            "offset": offset,
            # The tier asked for, or null for every tier: the rows below are that tier's alone.
            "finding": finding,
            "truncated": offset + len(rows) < (counts.get(finding, 0) if finding else total),
            # From the scalar query, NOT from by_tier — by_tier holds this page. Counting
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
const FINDINGS_PAGE = 500;
```
```javascript
const FINDINGS_PAGE = 500;
/* The Access granted filters that paint ONE tier fetch that tier alone. Since #353 the lab holds 703
   unmanaged rows before the platform rule (124 after), and a 500-row page ordered review tiers first carried no `ok` or `built_in` row:
   "granted (group exists)" and "built-in" read empty beside a tile that counted them (OB1-lite,
   review of #360). The mixed views keep the one page and its truncation note. */
const SINGLE_TIER_FILTERS = ["ok", "built_in", "unmanaged"];
function findingsUrl(base) {
  const tier = view.page === "bindings" && SINGLE_TIER_FILTERS.includes(view.bindingFilter)
    ? view.bindingFilter : null;
  return `${base}/bindings/findings?limit=${FINDINGS_PAGE}${tier ? `&finding=${tier}` : ""}`;
}
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
        want.findings = guard403(get(`${base}/bindings/findings?limit=${FINDINGS_PAGE}`));
```
```javascript
        want.findings = guard403(get(findingsUrl(base)));
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
          const wide = await guard403(get(`${base}/bindings/findings?limit=${FINDINGS_PAGE}`));
```
```javascript
          const wide = await guard403(get(findingsUrl(base)));
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
             total: num(raw.total), scope: raw.scope || "all", viewer: raw.viewer || null,
```
```javascript
             // A one-tier payload is partial against that tier's count, not the cluster's total.
             total: num(raw.finding ? (raw.counts || {})[raw.finding] : raw.total),
             scope: raw.scope || "all", viewer: raw.viewer || null,
```

<!-- block: local-development/gsd/static/app.css | edit -->
```css
.export { display: inline-flex; align-items: center; gap: var(--space-3); }
```
```css
/* Wraps, and never wider than its bar: the partial note is nowrap, and at 375 px it pushed the page
   sideways once every Access granted page on the lab became partial (#353, review of #360). */
.export { display: inline-flex; flex-wrap: wrap; align-items: center; gap: var(--space-3); max-width: 100%; }
```

<!-- block: local-development/API.md | edit -->
```markdown
  "total": 229, "limit": 500, "offset": 0, "truncated": false,
```
```markdown
  "total": 229, "limit": 500, "offset": 0, "finding": null, "truncated": false,
```

<!-- block: local-development/API.md | edit -->
```markdown
| `offset` | `0` | for paging through `total` |
```
```markdown
| `offset` | `0` | for paging through `total` |
| `finding` | none | one tier's rows only (`ok`, `dangling`, `unresolved`, `built_in`, `unmanaged`); echoed as `finding` |
```

<!-- block: local-development/API.md | edit -->
```markdown
reaches a report. `truncated` says whether rows were dropped.
```
```markdown
reaches a report. `truncated` says whether rows were dropped — measured against `counts[finding]`
when `finding` is given. The page is ordered review tiers first, so on a cluster with more review
rows than `limit` (703 unmanaged on the lab since #353) a mixed page holds no `ok` or `built_in`
row; the Access granted tab's one-tier filters ask for their tier.
```

<!-- block: local-development/mock-app/tests/test_poll_end_to_end.py | edit -->
```python
def test_tier_resolver_fails_closed_on_no_viewer(mock_cluster):
    cfg = mock_cluster.cluster_config(name="mock")
    assert _resolver(cfg, "list").tier_for(None) == TIER_SELF
```
```python
def test_tier_resolver_fails_closed_on_no_viewer(mock_cluster):
    cfg = mock_cluster.cluster_config(name="mock")
    assert _resolver(cfg, "list").tier_for(None) == TIER_SELF


def test_refresh_bindings_stores_every_subject_kind_over_tls(tmp_path, store, caplog):
    """#353 end to end: the reference fixture names Group and User subjects only, so a ServiceAccount
    subject never crossed the real reader. This adds one RoleBinding naming an account twice — once with
    no namespace (26 such entries on the lab, stored under the binding's) and once with it — and reads
    it through poll_once + refresh_bindings into the Store (OB1-lite, review of #360)."""
    import dataclasses

    from conftest import FIXTURE_DIR, MockHandle, _clear_ca_cache
    from mock_app.fixture import Binding, Fixture, RoleRef, Subject
    from mock_app.server import MockClusterServer

    base = Fixture.from_yaml(FIXTURE_DIR / "reference.yaml")
    account = Binding(name="deployer-rb", namespace="acme-app", role_ref=RoleRef(kind="Role", name="viewer"),
                      subjects=(Subject(kind="ServiceAccount", name="deployer"),
                                Subject(kind="ServiceAccount", name="deployer", namespace="acme-app")))
    fixture = dataclasses.replace(base, role_bindings=base.role_bindings + (account,))
    server = MockClusterServer(fixture, host="127.0.0.1", port=0, tls=True)
    server.start()
    try:
        ca = tmp_path / "ca.crt"
        ca.write_bytes(server.ca_pem)
        cfg = MockHandle(base_url=server.base_url, token=fixture.token, ca_file=str(ca), server=server,
                         fixture=fixture).cluster_config(name="mock")
        assert poll_once(store, cfg, timeout=5.0) == "ok"
        with caplog.at_level("INFO", logger="gsd.poller"):
            assert refresh_bindings(store, cfg, timeout=5.0, audit_mode="log") == "ok"
    finally:
        server.stop()
        _clear_ca_cache()
    rows = {(r.get("subject_kind"), r.get("subject_namespace"), r["group_name"]): r["finding"]
            for r in store.all_bindings("mock")}
    assert rows.get(("ServiceAccount", "acme-app", "deployer")) == "unmanaged", rows
    assert rows.get(("User", "", "lateef.o")) == "unmanaged", rows
    assert "refreshed 6 bindings for mock (4 Group, 1 ServiceAccount, 1 User subjects)" in caplog.text, caplog.text
    assert "grants viewer to ServiceAccount acme-app/deployer" in caplog.text, caplog.text
```

<!-- block: local-development/tests/test_ui.py | edit -->
```python
        assert [c for c in pod_claims if c in off_audit] == [] and "None" in off_audit, off_audit
        assert [c for c in pod_claims if c not in off_pod] == [], off_pod
        assert "which oauth-server pod saw it" not in rows_audit and "control-plane node" in rows_audit, rows_audit
        assert "which oauth-server pod saw it" in rows_pod
```
```python
        assert [c for c in pod_claims if c in off_audit] == [] and "None" in off_audit, off_audit
        assert [c for c in pod_claims if c not in off_pod] == [], off_pod
        assert "which oauth-server pod saw it" not in rows_audit and "control-plane node" in rows_audit, rows_audit
        assert "which oauth-server pod saw it" in rows_pod


class TestAOneTierFilterFetchesItsTier:
    def test_the_granted_filter_asks_the_server_for_the_granted_tier(self, dash):
        """OB1-lite, review of #360: on the lab the 500-row page held no granted row once 703 unmanaged
        ServiceAccount and User rows sorted ahead of them, so this filter painted an empty table."""
        dash.locator("button[data-nav='bindings']").click()
        dash.wait_for_selector("text=grant nobody")
        with dash.expect_request(lambda r: "/bindings/findings" in r.url and "finding=ok" in r.url):
            dash.select_option("#f-binding", "ok")
        dash.wait_for_function("() => data.findings && data.findings.finding === 'ok'")
        rows = dash.locator("section.card:has(h2:has-text('Granted')) tbody tr")
        assert rows.count() == dash.evaluate("() => data.findings.counts.ok") > 0
        dash.select_option("#f-binding", "review")
        dash.wait_for_function("() => data.findings && data.findings.finding === null")


class TestAPartialExportFitsAPhone:
    def test_the_partial_export_note_does_not_scroll_the_page_sideways_at_375px(self, dash):
        """A partial export note is `white-space: nowrap` inside an inline-flex that did not wrap: at 375 px
        it pushed the document 29 px past the viewport. Before #353 a page was partial only past 500 group
        bindings; on the lab every Access granted page is partial now (916 rows) (OB1-lite, review of #360)."""
        dash.set_viewport_size({"width": 375, "height": 800})
        dash.locator("button[data-nav='bindings']").click()
        dash.wait_for_selector("text=grant nobody")
        dash.wait_for_function("() => data.findings && data.findings.counts")
        dash.evaluate("() => { data.findings = Object.assign({}, data.findings, { total: 916, truncated: true }); render(); }")
        assert "partial" in dash.locator("#export-note").inner_text()
        overflow = dash.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
        assert overflow <= 0, f"the page scrolls {overflow}px sideways at 375px"
```

<!-- block: local-development/gsd/home.py | edit -->
```python
PLATFORM_NAMESPACE_PREFIXES = ("openshift-", "kube-")
PLATFORM_NAMESPACES = frozenset({"default", "openshift", "kube-system", "kube-public", "kube-node-lease"})
```
```python
# The shipped namespace defaults — a namespace here, or starting with a prefix here, is the platform's;
# values.yaml `platformNamespaces.prefixes`/`names` replace them, `additionalPrefixes`/`additionalSuffixes`/
# `additionalNames` widen them (config.py PlatformNamespaces).
# PLATFORM-CLASSIFICATION (#255, #353): the namespace prefixes
PLATFORM_NAMESPACE_PREFIXES = ("openshift-", "kube-")
PLATFORM_NAMESPACES = frozenset({"default", "openshift", "kube-system", "kube-public", "kube-node-lease"})  # PLATFORM-CLASSIFICATION (#255, #353): the names
# OpenShift's per-project controller bindings, excluded by design in EVERY namespace, matched on all three
# parts — the binding's name, its ClusterRole, and the subject in the binding's own namespace — the shape
# the controller writes ("auto-managed by a controller"); nothing broader, and no values key widens it (the
# operator, 2026-09-24). The third such binding, `system:image-pullers` → ClusterRole `system:image-puller`
# → Group `system:serviceaccounts:<namespace>`, is decided by the store's Group `system:` rule (store.py
# _FINDING_CASE) and is listed here so all three stand in one place.
# PLATFORM-CLASSIFICATION (#255, #353): the controller defaults, exact shape
PLATFORM_CONTROLLER_BINDINGS = frozenset({
    ("system:image-builders", "system:image-builder", "builder"),
    ("system:deployers", "system:deployer", "deployer"),
})
```

<!-- block: local-development/gsd/home.py | edit -->
```python
    return name in PLATFORM_NAMESPACES or name.startswith(PLATFORM_NAMESPACE_PREFIXES)
```
```python
    return name in PLATFORM_NAMESPACES or name.startswith(PLATFORM_NAMESPACE_PREFIXES)
```

<!-- block: local-development/gsd/home.py | edit -->
```python
def is_platform_namespace(name: str) -> bool:
```
```python
# PLATFORM-CLASSIFICATION (#255, #353): the shipped rule alone, for a caller with no Settings
def is_platform_namespace(name: str) -> bool:
```

<!-- block: local-development/gsd/config.py | edit -->
```python
    def matches(self, name: str) -> bool:
        """Whether this namespace is the platform's. Exact names first: the cheapest test, and the
```
```python
    # THE namespace classifier — names, prefixes, suffixes, each with its values.yaml
    # `platformNamespaces.additional*` axis appended; every consumer of "is this namespace the platform's" calls it.
    # PLATFORM-CLASSIFICATION (#255, #353)
    def matches(self, name: str) -> bool:
        """Whether this namespace is the platform's. Exact names first: the cheapest test, and the
```

<!-- block: local-development/gsd/config.py | edit -->
```python
    # Which namespaces are the platform's (#255). Defaults to the rule gsd/home.py ships.
    platform_namespaces: PlatformNamespaces = PlatformNamespaces()
```
```python
    # Which namespaces are the platform's (#255). Defaults to the rule gsd/home.py ships.
    # PLATFORM-CLASSIFICATION (#255, #353): the settings every consumer reads it from (values.yaml platformNamespaces → clusters.yaml)
    platform_namespaces: PlatformNamespaces = PlatformNamespaces()
```

<!-- block: local-development/gsd/config.py | edit -->
```python
def _platform_namespaces_setting(raw: dict) -> PlatformNamespaces:
    """`platformNamespaces` from the settings file (#255), or the shipped rule when absent.
```
```python
# PLATFORM-CLASSIFICATION (#255, #353): values.yaml `platformNamespaces` → the chart's configmap → clusters.yaml → this parse
def _platform_namespaces_setting(raw: dict) -> PlatformNamespaces:
    """`platformNamespaces` from the settings file (#255), or the shipped rule when absent.
```

<!-- block: local-development/gsd/config.py | edit -->
```python
        platform_namespaces=_platform_namespaces_setting(raw),
```
```python
        platform_namespaces=_platform_namespaces_setting(raw),   # PLATFORM-CLASSIFICATION (#255, #353)
```

<!-- block: local-development/gsd/kube.py | edit -->
```python
PLATFORM_USER_PREFIXES = ("system:",)
```
```python
# The User classifier — a `system:` name or one of the identities below is the platform's; no values key
# widens it (the operator's rule keys Users on the name, ServiceAccounts on the namespace).
# PLATFORM-CLASSIFICATION (#255, #353): the User prefixes and names
PLATFORM_USER_PREFIXES = ("system:",)
```

<!-- block: local-development/gsd/kube.py | edit -->
```python
    """Whether a User subject is a cluster-internal identity rather than a person."""
    return name.startswith(PLATFORM_USER_PREFIXES) or name in PLATFORM_USER_NAMES
```
```python
    """Whether a User subject is a cluster-internal identity rather than a person."""
    return name.startswith(PLATFORM_USER_PREFIXES) or name in PLATFORM_USER_NAMES
```

<!-- block: local-development/gsd/kube.py | edit -->
```python
def is_platform_user(name: str) -> bool:
```
```python
# PLATFORM-CLASSIFICATION (#255, #353): the User classifier
def is_platform_user(name: str) -> bool:
```

<!-- block: local-development/gsd/kube.py | edit -->
```python
                user_name=subject["name"],
                is_platform=is_platform_user(subject["name"]),
```
```python
                user_name=subject["name"],
                # PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's rule, unchanged by #353
                is_platform=is_platform_user(subject["name"]),
```

<!-- block: local-development/gsd/api.py | edit -->
```python
        for row in rows:
            row["platform"] = settings.platform_namespaces.matches(row["name"])
```
```python
        for row in rows:
            # PLATFORM-CLASSIFICATION (#255, #353): the namespace index's hide-by-default flag
            row["platform"] = settings.platform_namespaces.matches(row["name"])
```

<!-- block: local-development/gsd/api.py | edit -->
```python
        stale_patterns = settings.platform_namespaces.unmatched([r["name"] for r in rows])
```
```python
        # PLATFORM-CLASSIFICATION (#255, #353): an `additional*` pattern that matches no namespace here is reported as stale
        stale_patterns = settings.platform_namespaces.unmatched([r["name"] for r in rows])
```

<!-- block: local-development/gsd/api.py | edit -->
```python
            "answer": derive_answer(groups, via, direct,
                                    platform=settings.platform_namespaces.matches),
```
```python
            "answer": derive_answer(groups, via, direct,
                                    # PLATFORM-CLASSIFICATION (#255, #353): Home's "platform" is this classifier, the same one
                                    platform=settings.platform_namespaces.matches),
```

<!-- block: local-development/gsd/api.py | edit -->
```python
            "excluded_platform":
                store.platform_user_binding_count(cluster_id) if scope == "all" else None,
```
```python
            # PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's excluded count (is_platform_user, stored at poll time)
            "excluded_platform":
                store.platform_user_binding_count(cluster_id) if scope == "all" else None,
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
              "role_name": u.role_name, "user_name": u.user_name,
              "is_platform": 1 if u.is_platform else 0} for u in user_rows],
```
```python
              "role_name": u.role_name, "user_name": u.user_name,
              # PLATFORM-CLASSIFICATION (#255, #353): the direct-user flag, from is_platform_user in the reader
              "is_platform": 1 if u.is_platform else 0} for u in user_rows],
```

<!-- block: local-development/gsd/store.py | edit -->
```python
        if not include_platform:
            sql += " AND is_platform=0"
```
```python
        if not include_platform:
            # PLATFORM-CLASSIFICATION (#255, #353): the direct-user view hides the platform's identities by default
            sql += " AND is_platform=0"
```

<!-- block: local-development/gsd/store.py | edit -->
```python
            "SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=1",
```
```python
            # PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's excluded count
            "SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=1",
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->
```yaml
platformNamespaces:
  # Uncomment to replace the shipped defaults outright (rarely what you want):
```
```yaml
# PLATFORM-CLASSIFICATION (#255, #353): the estate's own additions to "which namespaces are the platform's" (#255). What
# this decides: the namespace index and Home hide these namespaces by default, and since #353 a ServiceAccount
# in one of them is the platform's own — silent under the built-in tier, never an unmanaged finding.
platformNamespaces:
  # Uncomment to replace the shipped defaults outright (rarely what you want):
```

<!-- block: charts/group-sync-dashboard/templates/configmap.yaml | edit -->
```yaml
    {{- $_ := include "gsd.validatePlatformNamespaces" . }}
    {{- with .Values.platformNamespaces }}
```
```yaml
    # PLATFORM-CLASSIFICATION (#255, #353): values.yaml platformNamespaces → this file → config.py _platform_namespaces_setting
    {{- $_ := include "gsd.validatePlatformNamespaces" . }}
    {{- with .Values.platformNamespaces }}
```

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->
```yaml
{{- define "gsd.validatePlatformNamespaces" -}}
```
```yaml
{{/* PLATFORM-CLASSIFICATION (#255, #353): refuses an unknown key or a non-list axis at render, so a typo never silently widens or narrows it */}}
{{- define "gsd.validatePlatformNamespaces" -}}
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
                         FROM user_binding WHERE cluster_id=? AND is_platform=0)
```
```python
                         -- PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's flag, on the reports' copy
                         FROM user_binding WHERE cluster_id=? AND is_platform=0)
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
        if not include_platform:
            sql += " AND is_platform=0"
```
```python
        if not include_platform:
            # PLATFORM-CLASSIFICATION (#255, #353): the direct-user view hides the platform's identities by default
            sql += " AND is_platform=0"
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
        r = self._row("SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=1", (cluster_id,))
```
```python
        # PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's excluded count
        r = self._row("SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=1", (cluster_id,))
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
                              FROM user_binding WHERE is_platform = 0 GROUP BY cluster_id, user_name) d
```
```python
                              -- PLATFORM-CLASSIFICATION (#255, #353): a person's direct grants, the platform's identities left out
                              FROM user_binding WHERE is_platform = 0 GROUP BY cluster_id, user_name) d
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
            "user_bindings": one("SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=0"),
```
```python
            # PLATFORM-CLASSIFICATION (#255, #353): the compliance snapshot's user-binding scalars split on the direct-user view's flag
            "user_bindings": one("SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=0"),
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
                " WHERE cluster_id=? AND binding_namespace<>'' AND is_platform=0)", cluster_id),
```
```python
                # PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's flag, on the reports' copy
                " WHERE cluster_id=? AND binding_namespace<>'' AND is_platform=0)", cluster_id),
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  const people = direct.filter((x) => !x.is_platform);
```
```javascript
  // PLATFORM-CLASSIFICATION (#255, #353): Home reads the stored flags — a Group's system: rule, a User's is_platform_user — and never decides
  const people = direct.filter((x) => !x.is_platform);
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
        <td><button type="button" class="drill">${esc(g.group_name)}</button>${g.is_platform ? ' <span class="badge unknown"><span class="glyph" aria-hidden="true"></span>platform</span>' : ""}</td>
```
```javascript
        <td><button type="button" class="drill">${esc(g.group_name)}</button>${/* PLATFORM-CLASSIFICATION (#255, #353): the platform badge */ ""}${g.is_platform ? ' <span class="badge unknown"><span class="glyph" aria-hidden="true"></span>platform</span>' : ""}</td>
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
        <td><button type="button" class="drill">${esc(x.user_name)}</button>${x.is_platform ? ' <span class="badge unknown"><span class="glyph" aria-hidden="true"></span>platform</span>' : ""}</td>
```
```javascript
        <td><button type="button" class="drill">${esc(x.user_name)}</button>${/* PLATFORM-CLASSIFICATION (#255, #353): the platform badge */ ""}${x.is_platform ? ' <span class="badge unknown"><span class="glyph" aria-hidden="true"></span>platform</span>' : ""}</td>
```

<!-- block: local-development/gsd/metrics.py | edit -->
```python
FINDINGS = ("ok", "dangling", "unresolved", "built_in", "unmanaged")
```
```python
# PLATFORM-CLASSIFICATION (#255, #353): a platform ServiceAccount or User row is counted under finding=built_in, never unmanaged
FINDINGS = ("ok", "dangling", "unresolved", "built_in", "unmanaged")
```

<!-- block: local-development/tests/test_config.py | edit -->
```python
    def test_additional_appends_while_the_plain_axis_replaces(self, tmp_path):
        """An estate adds its own without restating the Red Hat list, which changes between releases."""
```
```python
    def test_an_empty_stanza_keeps_the_defaults_and_a_suffix_appends(self, tmp_path):
        """The chart drops empty lists before rendering the key (templates/configmap.yaml), and a hand-written
        `platformNamespaces: {}` reaches the loader as an empty mapping; both must be the shipped rule, and the
        suffix axis must widen it the way the prefix axis does (#353's logic review)."""
        for body in ("platformNamespaces: {}\n", "platformNamespaces:\n  additionalPrefixes: []\n  additionalSuffixes: []\n  additionalNames: []\n"):
            assert _load(tmp_path, body) == PlatformNamespaces(), body
        widened = _load(tmp_path, 'platformNamespaces:\n  additionalSuffixes: ["-operator"]\n')
        assert widened.matches("cert-manager-operator") and widened.matches("openshift-monitoring")
        assert not widened.matches("demo-prod")

    def test_additional_appends_while_the_plain_axis_replaces(self, tmp_path):
        """An estate adds its own without restating the Red Hat list, which changes between releases."""
```

<!-- block: local-development/gsd/home.py | edit -->
```python
    def ns_row(name: str) -> dict:
        return namespaces.setdefault(name, {"name": name, "platform": platform(name), "grants": []})
```
```python
    def ns_row(name: str) -> dict:
        # PLATFORM-CLASSIFICATION (#255, #353): Home's namespace rows, by the classifier the API passes in (settings.platform_namespaces.matches)
        return namespaces.setdefault(name, {"name": name, "platform": platform(name), "grants": []})
```

<!-- block: local-development/gsd/state.py | edit -->
```python
    people = [u for u in (user_bindings or []) if not u.get("is_platform")]
```
```python
    # PLATFORM-CLASSIFICATION (#255, #353): the direct-user alert leaves the platform's identities out, by the stored is_platform_user flag
    people = [u for u in (user_bindings or []) if not u.get("is_platform")]
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
        people = sum(1 for u in user_rows if not u.is_platform)
```
```python
        # PLATFORM-CLASSIFICATION (#255, #353): the refresh line counts people by the direct-user flag
        people = sum(1 for u in user_rows if not u.is_platform)
```

<!-- block: local-development/gsd/api.py | edit -->
```python
        cluster_wide_groups = len({g["group_name"] for g in wide["via_groups"] if not g["is_platform"]})
```
```python
        # PLATFORM-CLASSIFICATION (#255, #353): Home's cluster-wide counts leave the platform's identities out (a system: group, a platform user)
        cluster_wide_groups = len({g["group_name"] for g in wide["via_groups"] if not g["is_platform"]})
```

<!-- block: local-development/gsd/store.py | edit -->
```python
                      FROM user_binding WHERE cluster_id=? AND binding_namespace != '' AND is_platform = 0
```
```python
                      -- PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's flag
                      FROM user_binding WHERE cluster_id=? AND binding_namespace != '' AND is_platform = 0
```

<!-- block: local-development/gsd/store.py | edit -->
```python
                for r in out:
                    r["is_platform"] = 1 if r["group_name"].startswith(SYSTEM_GROUP_PREFIX) else 0
```
```python
                for r in out:
                    # PLATFORM-CLASSIFICATION (#255, #353): a system: group is the platform's — the Group rule, as the finding's CASE applies it
                    r["is_platform"] = 1 if r["group_name"].startswith(SYSTEM_GROUP_PREFIX) else 0
```

<!-- block: local-development/gsd/store.py | edit -->
```python
                people = len({r["user_name"] for r in members}
                             | {r["user_name"] for r in [*direct, *cluster_wide_grants] if not r["is_platform"]})
```
```python
                # PLATFORM-CLASSIFICATION (#255, #353): people are the non-platform direct and cluster-wide grants plus the members
                people = len({r["user_name"] for r in members}
                             | {r["user_name"] for r in [*direct, *cluster_wide_grants] if not r["is_platform"]})
```

<!-- block: local-development/gsd/store.py | edit -->
```python
                     FROM user_binding
                    WHERE cluster_id=? AND is_platform=0
                    GROUP BY namespace
```
```python
                     FROM user_binding
                    -- PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's flag
                    WHERE cluster_id=? AND is_platform=0
                    GROUP BY namespace
```

<!-- block: local-development/gsd/store.py | edit -->
```python
                     FROM user_binding
                    WHERE cluster_id=? AND is_platform=0
                    ORDER BY user_name""",
```
```python
                     FROM user_binding
                    -- PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's flag
                    WHERE cluster_id=? AND is_platform=0
                    ORDER BY user_name""",
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
    const name = `${esc(n.name)}${n.platform ? '<span class="plat">platform namespace</span>' : ""}`;
```
```javascript
    // PLATFORM-CLASSIFICATION (#255, #353): Home's namespace row wears the server's platform flag
    const name = `${esc(n.name)}${n.platform ? '<span class="plat">platform namespace</span>' : ""}`;
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  const platformCount = d.platform_count != null ? d.platform_count : all.filter((n) => n.platform).length;
```
```javascript
  // PLATFORM-CLASSIFICATION (#255, #353): the namespace index hides the server-flagged platform rows by default
  const platformCount = d.platform_count != null ? d.platform_count : all.filter((n) => n.platform).length;
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  const hiddenWithFindings = hidingPlatform
```
```javascript
  // PLATFORM-CLASSIFICATION (#255, #353): a hidden platform namespace with a direct grant is still named
  const hiddenWithFindings = hidingPlatform
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  const viaReal = via.filter((g) => !g.is_platform);
```
```javascript
  // PLATFORM-CLASSIFICATION (#255, #353): the via/wide filters read the stored flag
  const viaReal = via.filter((g) => !g.is_platform);
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
  const wideGrants = (d.cluster_wide_grants || []).filter((x) => !x.is_platform);
```
```javascript
  // PLATFORM-CLASSIFICATION (#255, #353): cluster-wide grants naming a person, by the stored flag
  const wideGrants = (d.cluster_wide_grants || []).filter((x) => !x.is_platform);
```

<!-- block: local-development/gsd/static/index.html | edit -->
```javascript
        <td class="muted">${esc(g.binding_kind)} <code>${esc(g.binding_name)}</code>${g.managed_source || g.is_platform ? "" : ' <span class="badge warning"><span class="glyph" aria-hidden="true"></span>hand-made</span>'}</td>
```
```javascript
        <td class="muted">${esc(g.binding_kind)} <code>${esc(g.binding_name)}</code>${/* PLATFORM-CLASSIFICATION (#255, #353): no hand-made badge on a platform row */ ""}${g.managed_source || g.is_platform ? "" : ' <span class="badge warning"><span class="glyph" aria-hidden="true"></span>hand-made</span>'}</td>
```

<!-- block: local-development/gsd/home.py | edit -->
```python
def derive_answer(groups: list[dict], via: list[dict], direct: list[dict],
                  *, platform=is_platform_namespace) -> dict:
```
```python
# PLATFORM-CLASSIFICATION (#255, #353): Home's per-namespace flag — `platform` is settings.platform_namespaces.matches when the API calls
# this, and the shipped rule alone for a caller without Settings (OB2, review of #361)
def derive_answer(groups: list[dict], via: list[dict], direct: list[dict],
                  *, platform=is_platform_namespace) -> dict:
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
                        audit_progress=audit_progress,
                        platform_namespaces=self.settings.platform_namespaces,
```
```python
                        audit_progress=audit_progress,
                        # PLATFORM-CLASSIFICATION (#255, #353): the settings' classifier, the values file's additional* lists included, handed to every refresh
                        platform_namespaces=self.settings.platform_namespaces,
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
                               " AND b.is_platform = 0")
```
```python
                               " AND b.is_platform = 0")   # PLATFORM-CLASSIFICATION (#255, #353): the flag the poller stored
```

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->
```python
            "platform_user_bindings": one("SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=1"),
```
```python
            "platform_user_bindings": one("SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=1"),   # PLATFORM-CLASSIFICATION (#255, #353)
```

<!-- block: local-development/tests/test_platform_classification_marker.py | create -->
```python
"""Every line that decides or consumes "platform" carries the marker `PLATFORM-CLASSIFICATION (#255, #353)`
on itself or the line above, so `git grep PLATFORM-CLASSIFICATION` lists the whole logic end to end — the
operator's requirement (2026-09-24), so the classification can be reviewed as one path and cannot rot when a
new call appears somewhere unmarked. Spec: docs/specs/SPEC_U1_unmanaged_subjects.md, "The marked sites"."""
from __future__ import annotations

import pytest
import re
from pathlib import Path

MARKER = "PLATFORM-CLASSIFICATION (#255, #353)"
ROOT = Path(__file__).resolve().parents[2]
GSD = ROOT / "local-development" / "gsd"
# A decision or a consumption: the classifiers' definitions and defaults, and every call of them.
SITE = re.compile(
    # A call, or the bound method passed as an argument (Home passes `settings.platform_namespaces.matches`);
    # prose in a docstring ends the name with a backtick or a period, which neither form matches (Grok, #361).
    r"platform_namespaces\.(matches|unmatched)\s*[(,)]|\bplatform\.matches\s*\(|PlatformNamespaces\(\)\.matches\s*\("
    r"|\bis_platform_user\s*\(|\bis_platform_namespace\s*\("
    r"|PLATFORM_CONTROLLER_BINDINGS\b|^PLATFORM_(NAMESPACE_PREFIXES|NAMESPACES|USER_PREFIXES) ="
    r"|^def _platform_namespaces_setting\(|_platform_namespaces_setting\(raw\)|^\s+platform_namespaces: PlatformNamespaces = "
    # ... and every read or write of the stored flag, in Python or in SQL (OB1-lite, review of #361)
    r'|\bis_platform\s*=\s*[01]\b|\["is_platform"\]\s*=')
CHART_SITES = {
    ROOT / "charts/group-sync-dashboard/values.yaml": "platformNamespaces:",
    ROOT / "charts/group-sync-dashboard/templates/configmap.yaml": ".Values.platformNamespaces",
    ROOT / "charts/group-sync-dashboard/templates/_helpers.tpl": 'define "gsd.validatePlatformNamespaces"',
}


def _sites(path: Path) -> list[tuple[int, str]]:
    lines = path.read_text(encoding="utf-8").splitlines()
    out = []
    for i, line in enumerate(lines):
        if line.lstrip().startswith(("import ", "from ")) or not SITE.search(line):
            continue
        above = lines[i - 1] if i else ""
        if MARKER not in line and MARKER not in above:
            out.append((i + 1, line.strip()))
    return out


def test_every_python_site_that_decides_or_consumes_platform_is_marked() -> None:
    unmarked = {str(p.relative_to(ROOT)): _sites(p) for p in sorted(GSD.rglob("*.py")) if _sites(p)}
    assert unmarked == {}, f"unmarked platform-classification sites (add the marker on the line or the line above): {unmarked}"


def test_the_marked_python_path_is_complete() -> None:
    """The marker names every hop the spec lists: the classifiers, their settings, the direct-user path,
    and the finding path. A hop that loses its marker, or a file that drops out, fails here."""
    marked = {str(p.relative_to(ROOT)) for p in GSD.rglob("*.py") if MARKER in p.read_text(encoding="utf-8")}
    assert {"local-development/gsd/home.py", "local-development/gsd/config.py", "local-development/gsd/kube.py",
            "local-development/gsd/api.py", "local-development/gsd/poller.py", "local-development/gsd/store.py",
            "local-development/gsd/state.py", "local-development/gsd/reporting/snapshot.py"} <= marked, marked


def test_the_chart_path_is_marked() -> None:
    for path, needle in CHART_SITES.items():
        lines = path.read_text(encoding="utf-8").splitlines()
        hit = next(i for i, line in enumerate(lines) if needle in line)
        window = "\n".join(lines[max(0, hit - 3):hit + 1])
        assert MARKER in window, (str(path.relative_to(ROOT)), needle, window)

@pytest.mark.parametrize("line, is_site", [
    ('            row["platform"] = settings.platform_namespaces.matches(row["name"])', True),
    ("                                    platform=settings.platform_namespaces.matches),", True),
    ("        if platform.matches(b.subject_namespace):", True),
    ("    return PlatformNamespaces().matches(name)", True),
    ('    ok = is_platform_user ("kubeadmin")', True),
    ("                    WHERE cluster_id=? AND is_platform=0", True),
    ('                    r["is_platform"] = 1 if r["group_name"].startswith(SYSTEM_GROUP_PREFIX) else 0', True),
    ("    is_platform         INTEGER NOT NULL DEFAULT 0,", False),
    ('    """The shipped rule. Callers holding a `Settings` use `settings.platform_namespaces.matches`', False),
    ("from .config import PlatformNamespaces", False),
])
def test_the_site_pattern_sees_a_call_and_a_bound_method_pass_but_not_prose(line: str, is_site: bool) -> None:
    assert bool(SITE.search(line)) is is_site, line
```

<!-- block: local-development/tests/test_unmanaged_subjects.py | create -->
```python
"""The unmanaged finding on ServiceAccount and User subjects (#353, docs/specs/SPEC_U1_unmanaged_subjects.md).

The operator's rule, tested layer by layer: the platform's own identities are `built_in` by the estate's
classification (a namespace `platformNamespaces` names, a `system:` user, kubeadmin, OpenShift's two
per-project controller bindings); every other grant is excluded ONLY by the `rbac.ocp.io/config-source`
label or the `rbac.ocp.io/unmanaged-exception` annotation on its binding, whoever it names — no Helm or
OLM label, no binding name.
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

    def test_the_store_classifies_a_user_by_the_stored_flag_not_its_name(self, store):
        """The `system:` name test in the CASE is the Group tier's; a User row is `built_in` by the flag
        the poller stored from is_platform_user (TestPlatformRule), and a row seeded without it — as
        every test seed here is — classifies on provenance alone."""
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("managed", managed_source="prod-rbac"),
                                       user("scheduler", person="system:kube-scheduler"),
                                       user("flagged", person="system:kube-scheduler", is_platform=1),
                                       group("virtual", subject="system:authenticated")], T)
        assert findings(store) == {"managed": "ok", "scheduler": "unmanaged", "flagged": "built_in", "virtual": "built_in"}

    def test_the_charts_own_label_silences_only_its_own_accounts(self, store):
        """#354 carried over for the Group arm: the chart labels its seven ServiceAccount bindings, and
        on a host with no policy operator a hand-made GROUP grant is not reported until one policy label
        exists. A hand-made account outside the platform's namespaces is reported regardless: the new kinds
        have no gate (Codex, review of SPEC_U1 — a gate keyed on the cluster's labels silenced them by the
        cluster's state; the only defaults that silence are the platform classification's)."""
        _synced(store, SYNCED)
        chart = [sa(f"chart-{i}", account="group-sync-dashboard", namespace="group-sync-dashboard",
                    managed_source=CHART_CONFIG_SOURCE) for i in range(2)]
        store.replace_bindings("crc", chart + [sa("hand-made-sa"), group("hand-made")], T)
        assert findings(store) == {"chart-0": "ok", "chart-1": "ok", "hand-made-sa": "unmanaged", "hand-made": "ok"}
        store.replace_bindings("crc", chart + [sa("hand-made-sa"), group("hand-made"),
                                               group("managed", managed_source="prod-rbac")], T)
        assert findings(store) == {"chart-0": "ok", "chart-1": "ok", "hand-made-sa": "unmanaged",
                                   "hand-made": "unmanaged", "managed": "ok"}

    def test_an_unlabelled_account_is_a_finding_with_no_label_anywhere_on_the_cluster(self, store):
        """No gate for the new kinds: on a host with no label at all, the non-platform accounts and the person report;
        the Group grant does not, as #354 left it."""
        _synced(store, SYNCED)
        store.replace_bindings("crc", [sa("hand-made-sa"), user("hand-made-user"), group("hand-made")], T)
        assert findings(store) == {"hand-made-sa": "unmanaged", "hand-made-user": "unmanaged", "hand-made": "ok"}

    def test_a_labelled_account_does_not_open_the_group_gate(self, store):
        """The Group arm's gate reads Group rows only, so it is #354's (guarded by subject_kind): the operator's label
        on an account silences that account and changes nothing for a hand-made Group grant."""
        _synced(store, SYNCED)
        store.replace_bindings("crc", [sa("decided", managed_source="platform-team"),
                                       sa("hand-made-sa"), group("hand-made")], T)
        assert findings(store) == {"decided": "ok", "hand-made-sa": "unmanaged", "hand-made": "ok"}

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

    def test_a_v20_table_left_populated_still_opens(self, tmp_path):
        """The replay converges from a populated rbac_group_binding_v20 beside the old table (Grok,
        review of SPEC_U1). A crash cannot produce that state — the copy, the drop and the rename ride
        one implicit transaction — but a hand repair can, and without OR IGNORE the replay raised
        IntegrityError, which _migrate does not tolerate, so the pod could not open its database."""
        db = str(tmp_path / "repaired.db")
        _v19_database(db)
        conn = sqlite3.connect(db)
        conn.executescript("""
            CREATE TABLE rbac_group_binding_v20 (
                cluster_id TEXT NOT NULL, binding_kind TEXT NOT NULL, binding_namespace TEXT NOT NULL,
                binding_name TEXT NOT NULL, role_kind TEXT NOT NULL, role_name TEXT NOT NULL,
                subject_kind TEXT NOT NULL DEFAULT 'Group', subject_namespace TEXT NOT NULL DEFAULT '',
                is_platform INTEGER NOT NULL DEFAULT 0,
                group_name TEXT NOT NULL, observed_at TEXT NOT NULL, managed_source TEXT, exception TEXT,
                audit_stamped INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(cluster_id, binding_kind, binding_namespace, binding_name,
                            subject_kind, subject_namespace, group_name));
            INSERT INTO rbac_group_binding_v20
                SELECT cluster_id, binding_kind, binding_namespace, binding_name, role_kind, role_name,
                       'Group', '', 0, group_name, observed_at, managed_source, exception, audit_stamped
                  FROM rbac_group_binding;
        """)
        conn.commit(); conn.close()
        store = Store(db)
        try:
            assert store._conn.execute("PRAGMA user_version").fetchone()[0] == 20
            rows = store.all_bindings("crc")
            assert len(rows) == 1
            assert (rows[0]["group_name"], rows[0]["managed_source"], rows[0]["audit_stamped"]) == (
                "app-ocp-rbac-team-ns-audit", "prod-rbac", 1)
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
        assert set(rows) == {"managed", "shared-qa-poller", "scheduler"}, "the virtual group is omitted; a row seeded without the platform flag is not"
        assert rows["shared-qa-poller"]["finding"] == "unmanaged" and rows["scheduler"]["finding"] == "unmanaged"
        assert rows["shared-qa-poller"]["member_count"] is None
        assert snap.findings_counts("crc") == {"ok": 1, "unmanaged": 2}
        assert snap.counts("crc")["group_bindings"] == 1

    @staticmethod
    def _build(snap, name):
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
        spec, build = REGISTRY[name]
        return build(snap, ctx, validate_params(spec, {}))

    def test_the_binding_findings_report_names_the_account(self, snap):
        built = self._build(snap, "binding-findings")
        unmanaged = next(b for s in built.sections if s.title == "Unmanaged bindings" for b in s.blocks)
        assert unmanaged.columns[0] == "subject"
        subjects = sorted(r[0] for r in unmanaged.rows)
        assert subjects == ["ServiceAccount group-sync-operator/shared-qa-poller", "user system:kube-scheduler"]
        assert built.totals["unmanaged"] == 2

    def test_the_compliance_snapshot_names_its_two_populations(self, snap):
        """The group figure counts Group subjects; the Unmanaged figure counts every kind (Grok, review
        of SPEC_U1): 1 beside 2 on this seed, which read as two of one binding under the old labels."""
        built = self._build(snap, "compliance-snapshot")
        rbac = next(b for s in built.sections if s.title == "Key figures" for b in s.blocks if getattr(b, "title", None) == "RBAC")
        figures = dict(rbac.items)
        assert figures["Group bindings (Group subjects)"] == 1
        assert figures["Unmanaged (every subject kind)"] == 2
        # The every-kind total the Unmanaged figure is a part of (OB1-lite): 3 here, not the 1 Group binding.
        assert figures["Bindings (every subject kind)"] == 3
        assert figures["Unmanaged (every subject kind)"] <= figures["Bindings (every subject kind)"]
        assert "Platform identity grants (excluded from the direct-user figures)" in figures
        assert "Group bindings" not in figures and "Unmanaged" not in figures


class TestDuplicateSubjects:
    def test_a_subject_named_twice_on_one_binding_is_one_row(self):
        """OLM writes some RoleBindings with the same ServiceAccount twice (10 on the lab, e.g.
        metallb-system/metallb-operator.v4.22.0-202609151747 naming four accounts twice). The authorizer
        grants it once and the store's primary key keeps one row, so the reader must yield one — or the
        refresh line counts 925 subjects while the store holds 915 (OB1-lite, review of SPEC_U1)."""
        obj = {"metadata": {"name": "op.v1", "namespace": "alpha"},
               "roleRef": {"kind": "Role", "name": "op.v1"},
               "subjects": [{"kind": "ServiceAccount", "name": "controller"},
                            {"kind": "ServiceAccount", "name": "controller"},
                            {"kind": "ServiceAccount", "name": "controller", "namespace": "alpha"},
                            {"kind": "Group", "name": "g"}, {"kind": "Group", "name": "g"}]}
        rows = _binding_views(obj, "RoleBinding")
        assert [(r.subject_kind, r.subject_namespace, r.group_name) for r in rows] == [
            ("ServiceAccount", "alpha", "controller"), ("Group", "", "g")]


class TestSeverityFirstPage:
    def test_a_page_of_findings_holds_the_review_tiers_before_the_rest(self, store):
        """all_bindings(limit=…) is the page the Access granted and RBAC policy tabs render. Ordered by
        subject name alone, 500 unmanaged ServiceAccount rows named `aa…` pushed a dangling group named
        `zz…` off the page; severity first keeps every review item ahead of ok and built-in."""
        store.record_managed_groups("crc", [{"name": "zz-was-synced", "sync_provider": "ldap"},
                                            {"name": SYNCED, "sync_provider": "ldap"}], T)
        store.replace_group_state("crc", [{"name": SYNCED, "member_count": 1, "sync_provider": "ldap",
                                           "group_synced_at": None, "ldap_uid": None}], T)
        rows = [group("managed", managed_source="prod-rbac"), group("gone", subject="zz-was-synced")]
        rows += [sa(f"sa-{i}", account=f"aa-{i:03d}", namespace="ns") for i in range(3)]
        store.replace_bindings("crc", rows, T)
        page = [r["finding"] for r in store.all_bindings("crc", limit=2, offset=0)]
        assert page == ["dangling", "unmanaged"], page
        assert [r["finding"] for r in store.all_bindings("crc")] == ["dangling", "unmanaged", "unmanaged", "unmanaged", "ok"]


class TestAnOlderCopyInTheRollingWindow:
    def test_a_copy_written_before_migration_20_is_read_as_group_rows(self, tmp_path):
        """The report service accepts an OLDER copy by design (only a newer one is refused): while the
        pods roll, the newest snapshot on the volume is the 0.32.0 dashboard's, schema 19, until the new
        dashboard writes one. Every binding read now names subject_kind; against that copy each one raised
        "no such column: b.subject_kind" — a 500 on preview, a failed run — instead of reading the Group
        rows the copy holds (OB1-lite, review of SPEC_U1)."""
        from gsd.reporting.snapshot import Snapshot
        store = Store(str(tmp_path / "live.db"))
        store.upsert_cluster("crc", "https://x", True)
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("managed", managed_source="prod-rbac"), group("hand-made")], T)
        d = tmp_path / "snapshots"; d.mkdir()
        path = store.snapshot(str(d), keep=2)
        store.close()
        # The copy as release 0.32.0 wrote it: migration 20's one change undone, user_version 19.
        conn = sqlite3.connect(path)
        conn.executescript("""
            CREATE TABLE old AS SELECT cluster_id, binding_kind, binding_namespace, binding_name, role_kind,
                                       role_name, group_name, observed_at, managed_source, exception, audit_stamped
                                  FROM rbac_group_binding;
            DROP TABLE rbac_group_binding;
            ALTER TABLE old RENAME TO rbac_group_binding;
            PRAGMA user_version = 19;""")
        conn.commit(); conn.close()
        with Snapshot(Path(path)) as s:
            assert s.schema_version == 19
            assert s.findings_counts("crc") == {"ok": 1, "unmanaged": 1}
            assert s.counts("crc")["group_bindings"] == 2
            rows = s.group_bindings("crc", kinds=SUBJECT_KINDS)
            assert {(r["binding_name"], r["subject_kind"], r["subject_namespace"], r["is_platform"]) for r in rows} == {
                ("managed", "Group", "", 0), ("hand-made", "Group", "", 0)}
            assert {g["name"]: g["bindings"] for g in s.groups("crc")} == {SYNCED: 2}


class TestRolePicker:
    def test_a_role_bound_only_to_an_account_is_not_offered(self, tmp_path):
        """The report form's role picker (privileged-access `roles`) matches Group rows and direct user
        grants only. Reading every subject kind offered roles no report that takes the list can match —
        on the lab 356 distinct roles where 66 can (OB1-lite, review of SPEC_U1)."""
        from gsd.reporting.snapshot import Snapshot
        store = Store(str(tmp_path / "w.db"))
        store.upsert_cluster("crc", "https://x", True)
        store.replace_bindings("crc", [group("team-admin"),
                                       sa("scc", account="builder", namespace="ci") | {"role_name": "system:openshift:scc:privileged"}], T)
        d = tmp_path / "snapshots"; d.mkdir()
        path = store.snapshot(str(d), keep=2)
        store.close()
        with Snapshot(Path(path)) as s:
            assert s.discovered("crc", "", "")["roles"]["values"] == ["admin"]


class TestTotalOrder:
    """A page and a report are ordered by the whole primary key. Before #353 the ORDER BY (subject name,
    binding kind, namespace, name) named every key column; migration 20 added subject_kind and
    subject_namespace to the key, and one binding can now name `x` twice — as ServiceAccounts in two
    namespaces (the lab's system:controller:horizontal-pod-autoscaler names kube-system/ and
    openshift-infra/horizontal-pod-autoscaler), or as an account and a user. Rows that tie on the ORDER BY
    come back in whatever order SQLite scans them, so neither `/bindings/findings`' limit/offset walk nor
    a report's row order was defined by content (OB1-lite, second pass of SPEC_U1)."""

    def _rows(self):
        hpa = "horizontal-pod-autoscaler"
        # Inserted in the reverse of content order, so an order that falls back on the scan shows it.
        return [user("same", person=hpa) | {"binding_kind": "ClusterRoleBinding", "binding_namespace": "",
                                            "binding_name": "system:controller:hpa"},
                sa("system:controller:hpa", account=hpa, namespace="openshift-infra"),
                sa("system:controller:hpa", account=hpa, namespace="kube-system")]

    def test_the_findings_page_orders_ties_by_subject_kind_and_namespace(self, store):
        store.replace_bindings("crc", self._rows(), T)
        want = [("ServiceAccount", "kube-system"), ("ServiceAccount", "openshift-infra"), ("User", "")]
        assert [(r["subject_kind"], r["subject_namespace"]) for r in store.all_bindings("crc")] == want
        walked = [(r["subject_kind"], r["subject_namespace"])
                  for o in range(3) for r in store.all_bindings("crc", limit=1, offset=o)]
        assert walked == want

    def test_a_report_orders_ties_by_subject_kind_and_namespace(self, tmp_path):
        from gsd.reporting.snapshot import Snapshot
        live = Store(str(tmp_path / "w.db"))
        live.upsert_cluster("crc", "https://x", True)
        live.replace_bindings("crc", self._rows(), T)
        d = tmp_path / "snapshots"; d.mkdir()
        path = live.snapshot(str(d), keep=2)
        live.close()
        with Snapshot(Path(path)) as s:
            rows = s.group_bindings("crc", kinds=SUBJECT_KINDS)
        assert [(r["subject_kind"], r["subject_namespace"]) for r in rows] == [
            ("ServiceAccount", "kube-system"), ("ServiceAccount", "openshift-infra"), ("User", "")]


class TestAuditLogProgress:
    """The capped log lists new findings first, then the least recently listed (Codex, review of
    #360). Without it the sorted prefix listed the same 20 of the lab's 689 every cycle and a
    hand-made grant named past them never."""

    @staticmethod
    def _row(name):
        return {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": name,
                "group_name": name, "subject_kind": "ServiceAccount", "subject_namespace": "default",
                "finding": "unmanaged", "audit_stamped": False, "role_name": "view"}

    def test_a_backlog_rotates_through_the_cap_and_a_new_finding_goes_first(self):
        from gsd.audit import AuditLogProgress
        progress = AuditLogProgress()
        rows = [self._row(n) for n in "abcd"]
        names = lambda plan: [k[2] for k in plan.stamp]  # noqa: E731
        first = progress.plan(rows, 2)
        assert names(first) == ["a", "b"] and first.capped == 2
        assert names(progress.plan(rows, 2)) == ["c", "d"]
        # A finding first seen this cycle is listed this cycle, ahead of the rotation.
        assert names(progress.plan(rows + [self._row("u1-evidence")], 2)) == ["u1-evidence", "a"]
        # Labelled (no longer a finding): it leaves the schedule, and the rotation continues.
        third = progress.plan(rows, 2)
        assert names(third) == ["b", "c"] and third.capped == 2
        assert set(third.evidence) == set(third.stamp)

    def test_without_a_scheduler_the_poller_lists_the_sorted_first_page(self):
        from gsd.audit import plan_audit_stamps
        plan = plan_audit_stamps([self._row(n) for n in "dcba"], 2)
        assert [k[2] for k in plan.stamp] == ["a", "b"] and plan.capped == 2

    def test_the_poll_loop_announces_a_new_grant_on_the_refresh_that_finds_it(self, monkeypatch, caplog):
        """The scheduler wired into _run_cluster: four findings under a cap of two, a fifth appearing on
        the second cycle and labelled on the third. Every finding is announced, the new one on its own
        cycle and once, eight WARNING lines over four cycles (Codex, review of #360)."""
        from gsd import poller
        from gsd.config import ClusterConfig, Settings
        cluster = ClusterConfig("c", "https://x", token_env="TOKEN")
        store = Store(":memory:")
        store.upsert_cluster("c", "https://x", True)
        settings = Settings(clusters=[cluster], binding_interval_seconds=0, unmanaged_audit_mode="log",
                            unmanaged_audit_max_per_cycle=2, kyverno_enabled=False)
        runner = poller.Poller(store, settings)
        monkeypatch.setattr(poller, "poll_once", lambda *a, **kw: "ok")
        monkeypatch.setattr(poller, "capture_once", lambda *a, **kw: None)
        monkeypatch.setattr(runner, "_after_poll", lambda *a: None)
        tick = iter(range(10000))
        monkeypatch.setattr(poller.time, "monotonic", lambda: next(tick) * 1000.0)
        cycles: list[int] = []

        class Client:
            def __init__(self, *a, **kw): pass
            def fetch_bindings(self):
                cycle = len(cycles); cycles.append(cycle)
                names = ["a", "b", "c", "d"] + (["u1-evidence"] if cycle >= 1 else [])
                if cycle == 3:
                    runner._stop.set()
                # A project namespace: `default` is the platform's, and a platform row is never a finding.
                return [BindingView("ClusterRoleBinding", "", n, "ClusterRole", "view", n,
                                    subject_kind="ServiceAccount", subject_namespace="apps",
                                    managed_source="platform-team" if n == "u1-evidence" and cycle >= 2 else None)
                        for n in names]
            def fetch_user_bindings(self): return []
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", Client)
        with caplog.at_level("INFO", logger="gsd.poller"):
            runner._run_cluster(cluster)
        warnings = [r.message for r in caplog.records if r.levelname == "WARNING" and "UNMANAGED GRANT" in r.message]
        assert "apps/a," in warnings[0] and "apps/b," in warnings[1]
        assert "apps/u1-evidence," in warnings[2]
        assert any("apps/d," in line for line in warnings), warnings
        assert sum("apps/u1-evidence," in line for line in warnings) == 1
        assert len(warnings) == 8
        assert store.count_bindings_by_finding("c")["unmanaged"] == 4
        store.close()


class TestGroupOnlyReportWording:
    def test_the_group_only_reports_keep_their_group_only_finding_label(self, tmp_path):
        """`finding_label` serves namespace-access and privileged-access, whose rows are Group subjects
        only; a label naming accounts and people there described rows the report never holds (Codex,
        review of #360)."""
        from gsd.reporting.catalogue.common import finding_label
        assert finding_label("unmanaged") == "UNMANAGED — synced group granted by hand, no policy operator source"


class TestOneTierPage:
    """A 500-row page ordered review tiers first held no `ok` row on the lab (703 unmanaged rows since
    #353), so the Access granted tab's Granted section and its "granted" filter read empty beside a tile
    that counted them. `finding=` pages one tier (OB1-lite, review of #360)."""

    @pytest.fixture()
    def client(self, tmp_path):
        db = str(tmp_path / "t.db")
        store = Store(db)
        store.upsert_cluster("c1", "https://x", True)
        store.replace_group_state("c1", [{"name": SYNCED, "member_count": 1, "sync_provider": "gs_ldap",
                                          "group_synced_at": None, "ldap_uid": None}], T)
        store.record_managed_groups("c1", [{"name": SYNCED, "sync_provider": "gs_ldap"}], T)
        store.replace_bindings("c1", [group("managed", managed_source="prod-rbac")]
                               + [sa(f"acct-{i}", account=f"acct-{i}") for i in range(3)], T)
        store.close()
        settings = Settings(db_path=db, clusters=[ClusterConfig("c1", "https://x", token_env="T")])
        return TestClient(build_app(settings, run_poller=False))

    def test_a_page_smaller_than_the_review_items_still_reaches_the_granted_rows(self, client):
        mixed = client.get("/api/clusters/c1/bindings/findings?limit=2").json()
        assert mixed["ok"] == [] and len(mixed["unmanaged"]) == 2 and mixed["truncated"] is True
        d = client.get("/api/clusters/c1/bindings/findings?limit=2&finding=ok").json()
        assert [r["binding_name"] for r in d["ok"]] == ["managed"]
        assert d["unmanaged"] == [] and d["finding"] == "ok" and d["truncated"] is False
        assert d["counts"] == mixed["counts"] and d["total"] == 4
        paged = client.get("/api/clusters/c1/bindings/findings?limit=2&finding=unmanaged").json()
        assert len(paged["unmanaged"]) == 2 and paged["ok"] == [] and paged["truncated"] is True
        assert client.get("/api/clusters/c1/bindings/findings?finding=bogus").status_code == 422


class TestPlatformRule:
    """The platform's own identities are never a finding — the operator's long-standing rule (#353): a
    ServiceAccount in a namespace `platformNamespaces` names (the code's defaults, plus the values file's
    additional* lists), a `system:` user, kubeadmin. The poller computes the flag from the settings on
    every refresh and stores it; the store classifies by the stored flag; the Group arm is untouched."""

    @staticmethod
    def _refresh(store, monkeypatch, rows, platform=None):
        from gsd import poller
        from gsd.config import ClusterConfig

        class FakeClient:
            def __init__(self, *a, **kw): pass
            def fetch_bindings(self): return rows
            def fetch_user_bindings(self): return []
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", FakeClient)
        poller.refresh_bindings(store, ClusterConfig("crc", "https://x", token_env="T"), timeout=5,
                                platform_namespaces=platform)
        return {r["binding_name"]: (r["finding"], r["is_platform"]) for r in store.all_bindings("crc")}

    @staticmethod
    def _sa(name, namespace, **kw):
        return BindingView("ClusterRoleBinding", "", name, "ClusterRole", "view", f"{name}-sa",
                           subject_kind="ServiceAccount", subject_namespace=namespace, **kw)

    def test_an_account_in_a_default_platform_namespace_is_silent(self, store, monkeypatch):
        got = self._refresh(store, monkeypatch, [self._sa("monitoring", "openshift-monitoring"),
                                                 self._sa("dflt", "default"), self._sa("apps", "apps")])
        assert got == {"monitoring": ("built_in", 1), "dflt": ("built_in", 1), "apps": ("unmanaged", 0)}

    def test_an_account_in_a_namespace_added_via_additional_names_is_silent(self, store, monkeypatch):
        """And a values change reclassifies on the next refresh: the same row, flagged by the next
        settings, not by anything remembered."""
        from gsd.config import PlatformNamespaces
        rows = [self._sa("kyverno", "kyverno")]
        assert self._refresh(store, monkeypatch, rows) == {"kyverno": ("unmanaged", 0)}
        added = PlatformNamespaces(additional_names=frozenset({"kyverno"}))
        assert self._refresh(store, monkeypatch, rows, added) == {"kyverno": ("built_in", 1)}
        assert self._refresh(store, monkeypatch, rows) == {"kyverno": ("unmanaged", 0)}

    def test_an_account_elsewhere_is_reported_then_silent_once_its_binding_is_labelled(self, store, monkeypatch):
        assert self._refresh(store, monkeypatch, [self._sa("evidence", "gsd-evidence")]) == {"evidence": ("unmanaged", 0)}
        assert self._refresh(store, monkeypatch, [self._sa("evidence", "gsd-evidence", managed_source="platform-team")]) == {
            "evidence": ("ok", 0)}

    def test_a_system_user_and_kubeadmin_are_silent_and_a_person_is_not(self, store, monkeypatch):
        def u(name, person):
            return BindingView("ClusterRoleBinding", "", name, "ClusterRole", "cluster-admin", person, subject_kind="User")
        got = self._refresh(store, monkeypatch, [u("sched", "system:kube-scheduler"), u("admin", "kubeadmin"), u("jdoe", "jdoe")])
        assert got == {"sched": ("built_in", 1), "admin": ("built_in", 1), "jdoe": ("unmanaged", 0)}

    def test_the_group_arm_is_unchanged_beside_platform_rows(self, store, monkeypatch):
        """#354's Group arm: a hand-made Group grant is `ok` until some Group binding carries a policy
        label, and `unmanaged` after — whatever platform rows sit beside it."""
        _synced(store, SYNCED)
        g = lambda name, **kw: BindingView("RoleBinding", "ns-a", name, "ClusterRole", "admin", SYNCED, **kw)  # noqa: E731
        got = self._refresh(store, monkeypatch, [g("hand-made"), self._sa("dflt", "default")])
        assert got == {"hand-made": ("ok", 0), "dflt": ("built_in", 1)}
        got = self._refresh(store, monkeypatch, [g("hand-made"), g("managed", managed_source="prod-rbac"), self._sa("dflt", "default")])
        assert got == {"hand-made": ("unmanaged", 0), "managed": ("ok", 0), "dflt": ("built_in", 1)}
        assert store.count_bindings_by_finding("crc") == {"unmanaged": 1, "ok": 1, "built_in": 1}

    def test_the_reports_omit_a_platform_row_like_a_virtual_group(self, tmp_path, monkeypatch):
        from gsd.reporting.snapshot import Snapshot
        store = Store(str(tmp_path / "w.db"))
        store.upsert_cluster("crc", "https://x", True)
        _synced(store, SYNCED)
        self._refresh(store, monkeypatch, [self._sa("dflt", "default"), self._sa("apps", "apps"),
                                           BindingView("RoleBinding", "ns-a", "managed", "ClusterRole", "admin", SYNCED,
                                                       managed_source="prod-rbac")])
        d = tmp_path / "snapshots"; d.mkdir()
        path = store.snapshot(str(d), keep=2)
        store.close()
        with Snapshot(Path(path)) as s:
            assert {r["binding_name"] for r in s.group_bindings("crc", kinds=SUBJECT_KINDS)} == {"managed", "apps"}
            assert s.findings_counts("crc") == {"ok": 1, "unmanaged": 1}


class TestControllerBindingsAndTheDefaultAccount:
    """OpenShift's three per-project controller bindings are the platform's in every namespace, matched on
    all three parts (the operator, 2026-09-24: "exclude the following default in all namespaces by design").
    SA `default` gets no rule: OpenShift writes no binding of its own for it — its access is (c) — and a
    hand-made grant to it in a project namespace is the escalation this finding exists to catch."""

    _refresh = staticmethod(TestPlatformRule._refresh)

    @staticmethod
    def _rb(binding, namespace, role, account, *, sa_namespace=None, role_kind="ClusterRole", **kw):
        return BindingView("RoleBinding", namespace, binding, role_kind, role, account, subject_kind="ServiceAccount",
                           subject_namespace=namespace if sa_namespace is None else sa_namespace, **kw)

    def test_the_two_controller_bindings_are_silent_in_a_project_namespace(self, store, monkeypatch):
        from gsd.home import PLATFORM_CONTROLLER_BINDINGS
        assert PLATFORM_CONTROLLER_BINDINGS == {("system:image-builders", "system:image-builder", "builder"),
                                               ("system:deployers", "system:deployer", "deployer")}
        got = self._refresh(store, monkeypatch, [self._rb("system:image-builders", "apps", "system:image-builder", "builder"),
                                                 self._rb("system:deployers", "apps", "system:deployer", "deployer")])
        assert got == {"system:image-builders": ("built_in", 1), "system:deployers": ("built_in", 1)}

    def test_any_other_shape_with_the_same_account_or_name_is_reported(self, store, monkeypatch):
        # One refresh per shape: the table's key has no role columns, so two shapes that differ only by role
        # would be one row and the second would replace the first before the assert (Codex, review of #361).
        for row in [
            self._rb("system:image-builders", "apps", "admin", "builder"),                # another role
            self._rb("builder-admin", "apps", "system:image-builder", "builder"),         # another binding name
            self._rb("system:deployers", "apps", "system:deployer", "ci-bot"),            # another account
            self._rb("system:deployers", "apps", "system:deployer", "deployer", sa_namespace="other"),   # another namespace
            self._rb("system:image-builders", "apps", "system:image-builder", "builder", role_kind="Role"),  # a Role, not the ClusterRole
        ]:
            got = self._refresh(store, monkeypatch, [row])
            assert got == {row.binding_name: ("unmanaged", 0)}, (row, got)

    def test_the_third_controller_binding_is_a_system_group_and_the_group_arm_decides_it(self, store, monkeypatch):
        # (c) system:image-pullers → ClusterRole system:image-puller → Group system:serviceaccounts:<own namespace>:
        # no constant and no new arm — the store's Group `system:` rule (#354) decides it, is_platform stays 0.
        row = BindingView("RoleBinding", "apps", "system:image-pullers", "ClusterRole", "system:image-puller",
                          "system:serviceaccounts:apps")
        assert self._refresh(store, monkeypatch, [row]) == {"system:image-pullers": ("built_in", 0)}

    def test_a_hand_made_grant_to_the_default_account_is_reported_in_a_project_namespace_only(self, store, monkeypatch):
        # The same binding name in two namespaces: _refresh's by-name dict would fold them, so read the rows.
        self._refresh(store, monkeypatch, [self._rb("give-default-admin", "apps", "admin", "default"),
                                           self._rb("give-default-admin", "openshift-monitoring", "admin", "default")])
        rows = {(r["binding_namespace"], r["finding"], r["is_platform"]) for r in store.all_bindings("crc")}
        assert rows == {("apps", "unmanaged", 0), ("openshift-monitoring", "built_in", 1)}

    def test_the_labs_cluster_version_operator_binding_is_silent_by_the_accounts_own_namespace(self, store, monkeypatch):
        """The lab's real binding: ClusterRoleBinding `cluster-version-operator` → ClusterRole `cluster-admin` →
        ServiceAccount `default` in `openshift-cluster-version`. A ClusterRoleBinding has no namespace; the
        account's own decides, and `openshift-` is a shipped prefix — so no rule changes for it."""
        row = BindingView("ClusterRoleBinding", "", "cluster-version-operator", "ClusterRole", "cluster-admin", "default",
                          subject_kind="ServiceAccount", subject_namespace="openshift-cluster-version")
        assert self._refresh(store, monkeypatch, [row]) == {"cluster-version-operator": ("built_in", 1)}

    def test_additional_prefixes_and_suffixes_silence_their_namespaces(self, store, monkeypatch):
        from gsd.config import PlatformNamespaces
        rows = [TestPlatformRule._sa("team", "team-tools"), TestPlatformRule._sa("op", "metallb-operator"),
                TestPlatformRule._sa("app", "apps")]
        got = self._refresh(store, monkeypatch, rows, PlatformNamespaces(additional_prefixes=("team-",),
                                                                          additional_suffixes=("-operator",)))
        assert got == {"team": ("built_in", 1), "op": ("built_in", 1), "app": ("unmanaged", 0)}

    def test_the_direct_user_view_is_unchanged(self, store, monkeypatch):
        """The same account spelt as a User subject keeps the direct-user view's own rule and count; the
        finding path's flag never reaches user_binding."""
        from gsd import poller
        from gsd.config import ClusterConfig
        from gsd.kube import UserBindingView, is_platform_user

        class FakeClient:
            def __init__(self, *a, **kw): pass
            def fetch_bindings(self): return [TestPlatformRule._sa("apps-sa", "apps")]
            def fetch_user_bindings(self):
                return [UserBindingView("RoleBinding", "apps", "sa-as-user", "ClusterRole", "edit",
                                        "system:serviceaccount:apps:deployer", is_platform_user("system:serviceaccount:apps:deployer")),
                        UserBindingView("RoleBinding", "apps", "person", "ClusterRole", "edit", "jdoe", is_platform_user("jdoe"))]
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", FakeClient)
        poller.refresh_bindings(store, ClusterConfig("crc", "https://x", token_env="T"), timeout=5)
        assert store.platform_user_binding_count("crc") == 1
        assert [r["user_name"] for r in store.direct_user_bindings("crc")] == ["jdoe"]
        assert {r["binding_name"]: r["finding"] for r in store.all_bindings("crc")} == {"apps-sa": "unmanaged"}
```
