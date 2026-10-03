# SPEC G3 — acknowledged direct grants: the operator's label and exception take a direct user grant out of the worklist and the alert, counted and listed; the operator chart's value is provenance (#503)

| | |
|---|---|
| Programme | Epic G (#387), access declared, platform identities configured — build step 3 of 4. #255 (SPEC_G2, in review) comes before it and changes the same direct-user view, alert and page notes; #420 comes after |
| Batch | G — access declared |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 3.3.0, chart 0.66.1 |
| Version note | The blocks are written against main `dd51b91f` (application 2.0.0, chart 0.59.25), so blocks 66 to 69 and the CHANGELOG bullet (block 65) carry application 2.1.0 and chart 0.59.26. SPEC_G2 merges first and takes application 2.1.0 and chart 0.60.0, so at this spec's turn those five are re-derived to application 2.2.0 and chart 0.60.1 (a PATCH: no value is added, `appVersion` moves). Orchestrator's note 1 lists every block G2 touches |
| Issue | [#503](https://github.com/ephico2real2/group-sync-dashboard/issues/503) |
| Status | merged |
| Source | OB1-lite's research and specification of 2026-10-01, written before any code from #503 (body refined 2026-10-01, "Decisions and corrections (2026-10-01)", and the comment of 2026-10-01 on the Namespaces card), its epic #387, the mock `docs/design/direct-user-grants-mock.html` and SPEC_G2 at `4c75c65b`. Measured on main `dd51b91f` on this machine (Python 3.14.7, SQLite 3.53.4) and read-only on the CRC lab (2026-10-01, 14:04Z). §7 was cut from an implemented copy of `dd51b91f` and proved against a clean tree and against a tree with SPEC_G2 applied first (§4.3). Revised the same day after the review of `aefde964` by OB3 and OB2 (orchestrator's note 5), on main `3b3d0010` (the same code as `dd51b91f`; SPEC_G1, SPEC_E2, SPEC_G2 and SPEC_E4 merged as specifications) |

## How to read this spec

**The point, in two sentences.** The operator decided how a deliberate direct grant to a person is acknowledged:
put the `rbac.ocp.io/config-source` label or the `rbac.ocp.io/unmanaged-exception` annotation on its binding. The
unmanaged finding already honours that, and after this change the direct-user worklist, its alert, the namespace
counts and the reports' review figures honour it too, while every acknowledged grant stays counted and listed.

A few words used throughout. A **direct user grant** is a RoleBinding or ClusterRoleBinding subject of kind `User`.
The **label** is `rbac.ocp.io/config-source` on the binding, with any value, the empty value included. The
**exception** is the `rbac.ocp.io/unmanaged-exception` annotation on the binding. A direct user grant that is not a
platform identity's and whose binding carries either is **acknowledged**. The **review rule** is "not the
platform's and not acknowledged": it decides what is listed and counted as a grant to migrate.

§1 is the mandate and what is out of scope. §2 is the research: each finding names its primary source, quoted, and
what was measured on this repository and on the lab. §2a is the alternatives the research turned up, why each was
chosen or rejected, and the reconciliation of each external claim with the line of code that behaves accordingly.
§3 is the design, one rule per subsection with its reason; §3.9 states the safety property as a budget over the
system. §4 maps every test case of the issue (`T503-1` to `T503-14`) to a test and shows each one failing on
`dd51b91f`. §5 is the lab walk the implementing pull request runs. §6 is what an operator sees and what it costs. §7
is the whole change as implementation blocks (`docs/specs/README.md`, "Implementation blocks"), applied to a clean
tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_G3_acknowledged_direct_grants.md . --apply

Line citations into the code at `dd51b91f` are written as plain text, file:line, to keep them apart from the
maintained `path#anchor` citations. This spec's row in the index moves through its lifecycle by the orchestrator's
hand; no block touches it. A block found wrong during implementation is corrected here, with the reason under the
orchestrator's notes, before it is applied again.

## Orchestrator's notes

1. **Merge order: SPEC_G2 (#255) first, then this spec.** The epic's build order says so (#387, "Build order", row
   3 depends on row 2), and G2 changes the same view and alert. SPEC_G2 is merged as a specification (main
   `f144a82b`, its blocks not yet applied). The blocks apply to main's code as written (`f144a82b` has
   `dd51b91f`'s code), and were checked against a tree with all 75 of main's SPEC_G2 blocks applied first (§4.3):
   - **Blocks 66 to 69** (the two `Chart.yaml` fields, `pyproject.toml`, `gsd/__init__.py`) fail after G2, because
     their Old text is the version G2 replaces. At this spec's turn they become application 2.1.0 → 2.2.0 and chart
     0.60.0 → 0.60.1, each history line placed after G2's, and block 65's CHANGELOG bullet names
     "application 2.2.0, chart 0.60.1". These five are the only re-derivations.
   - **Every other block applies unchanged after G2**, and was cut so: no Old text of this spec contains a line a
     G2 block changes. They sit next to G2's blocks in seven files, and the anchors were chosen to avoid them:
     `gsd/store.py` (G2 22–24: two comments and `user_binding_names`, inserted before the
     namespace-configuration-operator header; block 17 here inserts its methods after
     `platform_user_binding_count`, above that), `gsd/state.py` (G2 26 changes the marker line that blocks 20 and 21
     here enclose), `gsd/api.py` (G2 28–30: the `include_platform` text and the fields after `excluded_platform`; block 26
     here adds its three fields after `excluded_platform`'s value line, which G2 keeps, so they land before G2's
     two), `gsd/static/index.html` (G2 33–37: the namespace page's marker line and the platform notes; blocks
     32–41 here anchor on the lines around them),
     `charts/.../UNMANAGED_GRANT_EXCLUSIONS.md`, `local-development/API.md` and `docs/CHANGELOG.md` (G2 64–70; the
     CHANGELOG bullets both insert after `## Unreleased`, so this one lands first, newest first).
   - **Names taken from G2: none.** This spec's code reads the stored `is_platform` flag, which G2 keeps (G2 changes
     who sets it: the poller, from `platformUsers`). So after G2 "platform wins" (§3.3) means "a user the estate's
     `platformUsers` names wins", with no edit here. The tests drive the reader through
     `local-development/gsd/kube.py#_user_binding_views` and `_binding_views`, whose signatures G2 keeps, and never
     construct `UserBindingView`, whose `is_platform` field G2 removes. `tests/test_platform_classification_marker.py`
     gains its own `REVIEW_SITE` pattern instead of editing `SITE`, which G2 rewrites (G2 blocks 56–59).
   - **Measured:** the 65 blocks that are not release fields, applied after main's SPEC_G2 (75 blocks), check out.
     The hermetic suite on the result fails one test, the specs index's version check on SPEC_E2's row, which
     SPEC_G2 applied alone fails too: both name chart 0.60.0 (§4.3).
2. **Corrections to the issue, each with its evidence.**
   - **The reports' copy: the review figures, not every report.** The issue lists `snapshot.py:439, 448, 661-662,
     670`, and so names `Snapshot.user_bindings` itself. That method feeds six reports
     (local-development/gsd/reporting/catalogue/access_matrix.py:35, access_certification.py:101,
     namespace_access.py:97, privileged_access.py through snapshot.py:458, compliance_snapshot.py:24,
     binding_findings.py:49). Four of them list the access a person holds. An access certification that dropped an
     acknowledged `cluster-admin` grant would certify access the person still has. This is the issue's own reason
     for keeping the self tier's rows ("an acknowledged grant is still access they hold"). So the rule applies where
     a report counts **direct user grants to review**: the RBAC findings report's direct-user table and the
     compliance snapshot's "Direct user grants" figure. Each gets the acknowledged rows as a count of its own, and
     the findings report lists them. `Snapshot.user_bindings` keeps every non-platform row and now says which are
     acknowledged and with what. `namespaces_with_bindings` (snapshot.py:670) counts namespaces holding a binding,
     which is presence, not review, and is unchanged. Line 448 is the platform count, which keeps its meaning.
   - **The namespace page's "People who reach it" keeps acknowledged grants.** It counts who reaches the namespace,
     which is access. Its "Direct grants" count, its list's header and the envelope's `cluster_wide_grants` follow
     the review rule, as the issue decided.
   - **The join's shape.** The issue's join on the bare tables is refused by SQLite: both tables have
     `binding_namespace`, `binding_name`, `role_kind` and `role_name`, and the existing unqualified queries read
     `ambiguous column name: role_name` (measured, §2.4). The join reads a subquery of `rbac_group_binding` whose
     columns are renamed (`ack_*`). The planner flattens it into the same full primary-key lookup in every query
     that reads it (EXPLAIN QUERY PLAN, §2.4, held by a test), because none of them is DISTINCT: SQLite never
     flattens the right side of a LEFT JOIN into a DISTINCT query, so the rollup's people query groups instead.
     No existing query had to qualify a column.
   - **"Paged like `bindings`"** (T503-9) is read as: the same `limit` and `offset`, and never narrowed by
     `namespace`. The list belongs under the rollup, which is never narrowed either. The page fetches it with
     `offset` 0, and an API client can reach every row by paging.
   - **The field names** the issue left to the spec: `acknowledged` (the count, beside `excluded_platform`),
     `acknowledged_bindings` (the rows, each with `managed_source` and `exception`), `acknowledged_truncated`, and a
     0/1 `acknowledged` on each row of `bindings` and of the namespace page's grants.
   - **The issue's line numbers** (at `5c03a9b1`) hold on `dd51b91f`: `git diff 5c03a9b1 dd51b91f --stat` touches
     only `docs/design/`.
   - **T503-8 and T503-12 are partly new behaviour.** The issue calls them regression guards. Their guard halves
     pass on `dd51b91f`: the self reader's own row is listed, and no name reaches `/metrics`. Their new halves fail
     there: the `acknowledged` fields, and `gsd_alerts_total` on a cluster whose only grant is acknowledged (§4.2).
3. **Decisions made on "easy to manage, best practice"** (the operator's rule of 2026-09-05), each argued in §2a.
   - **`group-sync-operator-helm` is a constant beside `CHART_CONFIG_SOURCE`, not a values list.** The operator
     chart fixes the value to its chart name and gives it no values key ("The value is fixed to the chart name ...
     a configurable provenance invites a wrong one", its `_helpers.tpl` lines 41–43 at `65323a48`, §2.5). A values
     list could only hold a value neither chart lets the estate set (a Helm dependency `alias` renames it, which
     opens the gate: noisy, never silent, measured with helm v4.3.0), and it would add a chart key, a parser and a
     render check for that. Under the values-file rule a fixed upstream fact is not a switch.
   - **No migration.** The join reads what the binding refresh already stores (store.py:249-253, filled at
     kube.py:1892-1893), as the issue recommended. The schema, the report service's schema check and the lab's
     one-migration-branch rule are untouched.
   - **No chart value and no RBAC change.** The chart changes only in a document, `docs/UNMANAGED_GRANT_EXCLUSIONS.md`,
     so it takes a PATCH. Its rendered templates are byte-identical apart from the version label (§4.3).
4. **Open for the operator** (asked when #503 starts; it does not block the implementation).
   - The two console `user-settings-*` RoleBindings in `openshift-console-user-settings` (`jane.smith`,
     `developer`), measured again at 2026-10-01T14:04:12Z: they stay ordinary rows, and this spec builds no rule
     for them. Labelling them would acknowledge them with no code change, but the OpenShift console writes them, so
     a label could be removed when the console rewrites them. That is the operator's call.

5. **The review of `aefde964`** by OB3 (in Grok's seat) and OB2 (in Codex's seat; Codex was out of usage until
   2026-10-03), decided by the orchestrator on 2026-10-01. Each accepted change is applied in §2.4, §3 and §7, and
   measured again on the applied tree (§4).
   - **Accepted, F1 (OB3; OB2's C4 is the same finding).** Block 10 wrote the rollup's people query as
     `SELECT DISTINCT`. SQLite never flattens a subquery on the right of a LEFT JOIN into a DISTINCT query
     (sqlite.org/optoverview.html, flattening constraint 3), so that query materialized the provenance subquery:
     `MATERIALIZE`, `SCAN rbac_group_binding`, `AUTOMATIC COVERING INDEX`, on every load and repaint of the
     Namespace audit tab. §2.4 had claimed no such scan. Block 10 now groups (`GROUP BY namespace, user_name`),
     which gives the same pairs in the same order with the primary-key SEARCH.
   - **Accepted, the plan test and the join test (OB3, F1's second half; OB2's block 43a).** The two reviews proposed
     overlapping plan tests. OB3's is taken, because it is stricter:
     - it requires the full seven-column SEARCH, not just the index name;
     - it counts the nine joined queries the readers issue;
     - it skips below SQLite 3.40.0, the release from which an aggregate query is flattened at all.
     OB2's version is the same idea and is not applied a second time. OB3's
     `test_the_join_matches_each_grant_to_its_own_binding_row` pins the join's conditions. OB3 dropped each of
     the eight in turn, and all eight survived the 541 related tests of `aefde964`. With the two tests, each
     mutant fails 1 or 2 of them (§4.2, M13). Both tests are in block 43.
   - **Accepted, F2 (OB3).** Block 31's label claimed the acknowledged grants were "excluded from the direct-user
     figures", while "Privileged direct grants" in the same list counts them (measured). The figure is right: it is
     the privileged-access review's, which keeps access a person holds. So the label is what changes: "Acknowledged
     direct grants (excluded from Direct user grants)". Block 51 gains
     `test_t503_11_an_acknowledged_privileged_grant_is_still_privileged_access`, and §3.7 and block 65 say the same.
   - **Accepted, docs (OB2's N2).** §3.2 gains a row naming the access and presence sites the rule deliberately
     leaves alone.
   - **Accepted, wording (OB3's N1 and N2, offered as optional).**
     - N1: a Helm dependency `alias` renames the operator chart's value (measured with helm v4.3.0). Its
       Group bindings then open the gate, which is noisy, never silent. The constant stays. Four sentences that
       called the value unchangeable now say this (block 1, block 61, §2a D2, note 3).
     - N2: `poller.refresh_bindings` returns before the direct-user list when the binding list fails, so neither
       table changes. §3.9's row had filed that case under "alerting"; it now reads "frozen", beside the case of a
       failed direct-user list.
   - **The index.** G3 is the fortieth row, after G1, E2, G2 and E4, which merged first. It is excluded from the
     rising-issue assert by its id and pinned with `assert ROWS["G3"]["issue"] == "503"`, as G1, E2, G2, E4 and D5
     are (§4.2, M15).
   - **Rejected: none.** The §2.4 cost table was re-measured whole for this revision, rather than mixing OB3's
     re-measured rollup row with the first version's numbers.

6. **Corrections at implementation (2026-10-03), written into the blocks before any were applied.** SPEC_G2 (#556)
   merged first, as note 1 planned, and the tree also moved past SPEC_H1, E11 and G1. The re-derivation note 1 names:
   - **The release fields, blocks 65 to 69.** On today's tree (application 3.2.0, chart 0.66.0) they take the next
     free numbers under SPEC_E5's version rule: application 3.3.0 (`check-app-version-bump.py`'s next MINOR) and
     chart 0.66.1, a PATCH as before. Each block's Old text names the tree's numbers, and the history lines carry
     today's date. G4's planned versions move to 0.66.2 / 0.66.3.
   - **Block 57.** SPEC_G1 (#554) replaced the old three-column access table with the per-route declaration
     (`docs/ACCESS_CONTROL.md` §4), so the row it edits is now that declaration's `user-bindings` row
     (`apply-spec-blocks.py` said "Old text occurs 0 times"). The persona columns do not change: G3 changes what the
     answer holds, not who gets one. Its wording goes into the row's notes cell. G1's test reads the persona words,
     so it holds the row unchanged.
   - The prose's version numbers (§2, §4.3) are measurements from their own day, and stay as they were.

## 1. The mandate, and what is out of scope

The issue (#503, "What must be accomplished"):
1. A direct user grant on a labelled binding leaves the worklist, its total and the direct-user alert's count, and
   is counted as acknowledged (T503-1).
2. The same holds for a binding with the exception annotation and no label (T503-2).
3. Acknowledged is counted, never dropped: the wide tier sees the count beside `excluded_platform` and reaches each
   row with its label value or exception text (T503-9, T503-10).
4. An unlabelled, unannotated grant still alerts (T503-3).
5. A platform user stays platform (T503-7).
6. `group-sync-operator-helm` is provenance in the Group arm's gate (T503-4, T503-5).
7. Every surface that counts direct user grants for review uses the same rule (T503-11 and the decision).
8. Nothing else moves (T503-6, T503-8, T503-12, T503-13).
9. On CRC, `dashboard`'s two `group-sync-operator-helm` grants move from the worklist to acknowledged (T503-14).

Its decisions (2026-10-01) are followed, with the refinements in the orchestrator's note 2. They are: one review
rule everywhere; acknowledged rows counted and reachable, `null` at the self tier; the self tier's own acknowledged
grants still listed; platform wins; the provenance read by joining `rbac_group_binding`; the one-list-only case
keeps alerting, tested; the alert metric unchanged in meaning.

Out of scope, each owned elsewhere: the configurable platform-user list (#255, SPEC_G2, which merges first), the
tier declaration (#239), the Lease grant (#420), any rule for the console's `user-settings-*` RoleBindings (open
question 4), and any new way to acknowledge a grant. `expectedGrants` was withdrawn by the operator on 2026-09-26.
No binding name, Helm, OLM or Argo CD label acknowledges anything (#353).

## 2. Research, measured

Upstream documents were read from their source repositories at a pinned commit, fetched on 2026-10-01 with
`curl -sfL https://raw.githubusercontent.com/<repo>/<sha>/<path>` and cited from `nl -ba`:
kubernetes/website `980792fa`, kubernetes/apimachinery `1b8e5ed4`, kyverno/website `77f297fd`, FairwindsOps/polaris
`4ced8e86`, kubescape/kubescape `01ce227b`, ephico2real2/group-sync-operator-helm-chart `65323a48`. The SQLite
documents were fetched from sqlite.org the same day. The lab reads were `oc get clusterrolebindings,rolebindings
-A -o json`, `oc get pvc`, `oc get deploy`, the public `/metrics`, and three GETs through the dashboard pod's
loopback as the cluster-reader `dana.lee`. All were read-only.

### 2.1 A label is identifying and selectable, and its value may be empty; an annotation is free text

**Source.** Kubernetes, "Labels and Selectors" (`content/en/docs/concepts/overview/working-with-objects/labels.md`,
lines 13–15 and 29–31): "Labels are intended to be used to specify identifying attributes of objects that are
meaningful and relevant to users ... Labels can be used to organize and to select subsets of objects", and "Labels
allow for efficient queries and watches and are ideal for use in UIs and CLIs. Non-identifying information should
be recorded using annotations." Lines 77–81: "Valid label value: must be 63 characters or less (can be empty),
unless empty, must begin and end with an alphanumeric character". "Annotations" (`annotations.md`, line 8): "You can
use Kubernetes annotations to attach arbitrary non-identifying metadata to objects", and lines 16–20: "annotations
are not used to identify and select objects. The metadata in an annotation can be small or large, structured or
unstructured, and can include characters not permitted by labels." Line 78: "Valid annotation values have no
character set restrictions — unlike label values, annotation values may contain any string, including special
characters, whitespace, and structured data such as JSON or YAML."

**What it settles.** The two carriers mean what #353 uses them for. The label says who owns the binding, a short
selectable value (`oc get rolebindings -A -l rbac.ocp.io/config-source` finds every acknowledged binding). The
annotation carries the reviewer's sentence. A label with an empty value is a valid label, and the unmanaged finding
already treats it as present (its arm reads `b.managed_source IS NULL AND b.exception IS NULL`, store.py:2826-2827). The direct-user view does the same, so
the two cannot disagree on an empty value (tested, §4.1). The exception text can be any string: the page escapes it
(`esc`), wraps it in its cell (§3.6), and never puts it in a metric (§3.9).

### 2.2 How long an exception text can be

**Source.** kubernetes/apimachinery `pkg/api/validation/objectmeta.go`, line 39:
`const TotalAnnotationSizeLimitB int = 256 * (1 << 10) // 256 kB`. Lines 61–70 sum `len(k) + len(v)` over every
annotation of the object and refuse the object above that.

**What it settles.** One exception text is at most 256 KiB, minus the object's other annotations. The API returns
it whole, as the RBAC findings API and the findings report already do for every binding's exception. The page puts
it in a table cell inside `.scroll-x`, with `overflow-wrap: anywhere`, so a long text wraps instead of widening the
page (T503-10 at 375 px).

### 2.3 How comparable tools acknowledge a finding: kept visible, not deleted

- **Kyverno** (`src/content/docs/docs/guides/exceptions.md`). Line 17: "A `PolicyException` is a Namespaced Custom
  Resource which allows a resource(s) to be allowed past a given policy and rule combination." Line 29: "If the
  match condition evaluates to `true`, the referenced rule is **skipped** and logged accordingly in
  **PolicyReports**." Lines 86–90 show the report entry, `result: skip` with "rule is skipped due to policy
  exception". Line 9: "PolicyExceptions are disabled by default."
- **Kubescape** (`examples/exceptions/README.md`, line 3): "Kubescape Exceptions let you suppress or acknowledge
  findings for specific resources. For evaluated findings, use `disable` when an accepted finding should pass with
  exceptions and stop affecting the compliance score. Use `alertOnly` when the finding should be annotated as
  acknowledged but remain failed and continue affecting the score."
- **Polaris** (`docs/customization/exemptions.md`, lines 17 and 22): "To exempt a controller from all checks via
  annotations, use the annotation `polaris.fairwinds.com/exempt=true`", and per check
  `polaris.fairwinds.com/<check>-exempt=true`.

**What it settles.** In each tool an acknowledged finding still shows up somewhere: Kyverno records the skip in the
report, Kubescape counts it as "passed with exceptions", and Polaris records the exemption on the object. In each
tool the acknowledgement is recorded on, or next to, the object, not in the scanner's own list. That is #353's rule
(the label or the annotation on the binding), and it is the issue's "suppressed means counted, not deleted": a
count and a list beside `excluded_platform`. Kubescape's `alertOnly` is the alternative of keeping the grant in the
alert; §2a rejects it.

### 2.4 SQLite: the join, its plan and its cost

**Sources.** SQLite, "EXPLAIN QUERY PLAN" (sqlite.org/eqp.html): "If the query were able to use an index, then the
SCAN/SEARCH record would include the name of the index and, for a SEARCH record, an indication of how the subset of
rows visited is identified", and "'SCAN' is used for a full-table scan". "The SQLite Query Optimizer Overview"
(sqlite.org/optoverview.html), on automatic indexes: "When no indexes are available to aid the evaluation of a
query, SQLite might create an automatic index that lasts only for the duration of a single SQL statement."

**The key.** `rbac_group_binding`'s primary key is (cluster_id, binding_kind, binding_namespace, binding_name,
subject_kind, subject_namespace, group_name) (store.py:258-259). A User subject is stored with `subject_namespace`
`''` (kube.py:1877, and its docstring at kube.py:1855-1856: "User and Group subjects have no namespace; "" is stored"). So matching a `user_binding`
row on all seven columns finds at most one row.

**A bare join is refused.** Both tables carry `binding_namespace`, `binding_name`, `role_kind` and `role_name`, and
the existing queries name them unqualified. Measured on SQLite 3.53.4:

```text
sqlite3.OperationalError: ambiguous column name: role_name
```

The join therefore reads `(SELECT cluster_id AS ack_cluster, binding_kind AS ack_kind, binding_namespace AS
ack_namespace, binding_name AS ack_name, group_name AS ack_user, managed_source, exception FROM rbac_group_binding
WHERE subject_kind = 'User' AND subject_namespace = '')`. No renamed column collides, and every existing query keeps
its unqualified names.

**The plan.** On a store built by the real `Store` from the lab's 931 binding objects (950 subject rows: 701
ServiceAccount, 214 Group, 35 User; 35 `user_binding` rows), `EXPLAIN QUERY PLAN` of the worklist count:

```text
SEARCH user_binding USING INDEX user_binding_by_namespace (cluster_id=?)
SEARCH rbac_group_binding USING INDEX sqlite_autoindex_rbac_group_binding_1 (cluster_id=? AND binding_kind=? AND binding_namespace=? AND binding_name=? AND subject_kind=? AND subject_namespace=? AND group_name=?) LEFT-JOIN
```

The subquery is flattened: one primary-key SEARCH per `user_binding` row, no SCAN of `rbac_group_binding`, and no
automatic index. Every query that reads the join plans this way, on two conditions from SQLite's own flattening
rules (sqlite.org/optoverview.html, constraint 3; `src/select.c`). The outer query must not be DISTINCT, in any
version: the rollup's people query, written `SELECT DISTINCT`, read `MATERIALIZE (subquery-1)`, `SCAN
rbac_group_binding` and `SEARCH (subquery-1) USING AUTOMATIC COVERING INDEX` (measured, lab and ×100), so block 10
groups its pairs instead. And an aggregate outer query (every COUNT and GROUP BY here) is flattened only from
SQLite 3.40.0 (`select.c` at version-3.39.0 still lists "(3c) the outer query may not be an aggregate"). The
2.0.0 image runs SQLite 3.53.4 (`python3.14 -c 'import sqlite3; print(sqlite3.sqlite_version)'` in it), the
version these plans were read on. `test_every_provenance_query_searches_rbac_group_binding_by_its_primary_key`
reads every reader's plan and skips below 3.40.0.

**The cost.** Each query was run 50 times, and the mean is shown in milliseconds. "Main" is `f144a82b` (the same
code as `dd51b91f`), and "this spec" is that tree with §7 applied. "×100" repeats every binding a hundred times
under new names (95,000 and 3,500 rows). Re-measured for the revision of the spec, 2026-10-01:

| query | main, lab | this spec, lab | main, ×100 | this spec, ×100 |
|---|---|---|---|---|
| worklist rows (`direct_user_bindings`, limit 200) | 0.021 | 0.035 | 0.508 | 1.135 |
| worklist count | 0.003 | 0.007 | 0.194 | 0.834 |
| rollup (`user_bindings_by_namespace`) | 0.023 | 0.028 | 0.671 | 1.944 |
| acknowledged rows (limit 200) | — | 0.029 | — | 1.089 |
| acknowledged count | — | 0.007 | — | 0.813 |
| namespace index (`namespaces`) | 0.122 | 0.140 | 7.433 | 8.592 |

With the rollup's people query written `SELECT DISTINCT`, as the first version of block 10 had it, the rollup
read 11.777 ms at ×100 here (12.583 ms in OB3's run of the review, 13.7 ms in OB2's): the SCAN above.

At the lab's size every query stays under 0.15 ms. At a hundred times the lab, the rollup's two queries go from
0.7 ms to 1.9 ms, read once per page load and per 60-second repaint of the Namespace audit tab. The worklist,
computed through this spec's code on the lab's own objects, reads 9 rows, 2 acknowledged and 24 platform, which are
T503-14's numbers.

### 2.5 The operator chart's value is fixed

**Source.** ephico2real2/group-sync-operator-helm-chart `charts/group-sync-operator-helm/templates/_helpers.tpl` at
`65323a48` (main, after #76 `ef351b5`), lines 41–47: "The value is fixed to the chart name, as the dashboard's own
gsd.rbacLabels is: this chart renders these objects, so it is their config source, and a configurable provenance
invites a wrong one", and `rbac.ocp.io/config-source: {{ .Chart.Name }}`. Its `Chart.yaml` line 2:
`name: group-sync-operator-helm`. PR #76's body: "The value is fixed and has no values key", and "If a Group is set
in `groupSyncDashboard.extraSubjects` or `token.readers`, the labelled binding would count as evidence that a policy
system is in use. The dashboard should treat this chart's value as provenance only, as it treats its own."

**What it settles.** `group-sync-operator-helm` is a constant upstream, like `group-sync-dashboard` here
(`local-development/gsd/kube.py#CHART_CONFIG_SOURCE`). The Group gate ignores both (§3.8).

### 2.6 This repository at `dd51b91f`

- **The unmanaged finding already holds the rule.** The arm is `WHEN b.managed_source IS NULL AND b.exception IS
  NULL ... THEN 'unmanaged'`, after `built_in` (store.py:2808-2809, then :2826-2834). For a User row it has no
  gate, so a User grant is `ok` exactly when its binding is labelled or annotated
  (`local-development/gsd/store.py#_FINDING_CASE`).
- **The direct-user view does not.** Every worklist query filters on the flag alone (store.py:3839, :3853, :3888).
  The alert keeps every non-platform row (state.py:498), and the namespace index (store.py:1840), the namespace
  page (store.py:1917-1922), the envelope (api.py:2280-2281, :2318) and the reports' copy (snapshot.py:439,
  :661-662, :670) do the same.
- **The provenance is stored for Users.** `_binding_views` keeps every subject kind and sets `managed_source` and
  `exception` from the binding's metadata (kube.py:1892-1893). `refresh_bindings` writes it to `rbac_group_binding`
  (poller.py:667 and :678-701) and then writes `user_binding` from a separate list call (poller.py:709-722), in a
  separate transaction.
- **The Group gate.** It skips only this chart's own value: `AND m.managed_source <> 'group-sync-dashboard'`
  (store.py:2834, `CHART_CONFIG_SOURCE` at kube.py:335).
- **Who reads the direct-user rows.** The `/user-bindings` handler (api.py:2493-2515); Home with
  `include_platform=True, user_name=me` (api.py:2393); the alert, through `direct_user_bindings(cluster_id)` with
  its defaults, on `/api/alerts` (api.py:2748) and `/metrics` (metrics.py:620). So the store's default is what the
  alert counts.
- **The page.** The worklist and its platform note are in `directUserGrants` (index.html:7019-7292). The
  disclosure idiom is "Every grant": `view.nsGrantsOpen`, a `button.disclose` with `aria-expanded`, and its handler
  in the page's wiring (index.html:7237-7261, :7613-7614). The namespace page reads `is_platform` from each row
  (index.html:5545-5565, :5637-5643).

### 2.7 The lab, read-only (CRC 4.22.7, chart 0.59.25, image `quay.io/ephico2real/group-sync-dashboard:2.0.0`)

Every User subject on every binding, classified by the shipped rule, with the binding's label and annotation
(2026-10-01T14:04:12Z):

```text
binding objects 931 subject rows (rbac_group_binding shape) 950 {'ServiceAccount': 701, 'Group': 214, 'User': 35}
user rows 35 platform 24 not 11
not-platform labelled 2 annotated 0 neither 9
   ('ClusterRoleBinding', '', 'group-sync-dashboard-cluster-poller', 'ocp-oauth-bind-serviceid', 'group-sync-operator-helm', None)
   ('RoleBinding', 'group-sync-operator', 'group-sync-dashboard-cluster-poller-token-reader', 'ocp-oauth-bind-serviceid', 'group-sync-operator-helm', None)
platform rows carrying a label: []
Group subjects with a config-source value: {'baseline-cluster-rbac': 12, 'custom-cluster-rbac': 1, 'group-sync-dashboard': 1, 'baseline-prod-rbac': 3, 'baseline-nonprod-rbac': 28, 'bdp-oud-group-rbac': 1, 'trino-oud-group-rbac': 1}
```

The other nine are `dana.lee` (`cluster-reader`), `jdoe` (three bindings), `asmith`, `bwilliams`,
`tmp-contractor-9931`, and the console's `jane.smith` and `developer`. No Group subject carries
`group-sync-operator-helm`, and 46 carry another value, so the Group gate stays open on the lab and the gate change
has no effect a walk can see (the issue's correction 3). The public `/metrics` (14:04:37Z):

```text
gsd_bindings_total{cluster="dashboard",finding="unmanaged"} 53.0
gsd_bindings_total{cluster="shared-qa",finding="unmanaged"} 53.0
gsd_bindings_total{cluster="shared-rnd",finding="unmanaged"} 53.0
gsd_alerts_total{cluster="dashboard",kind="direct_user_binding",severity="warning"} 1.0
gsd_bindings_total{cluster="dashboard",finding="ok"} 43.0
gsd_bindings_total{cluster="dashboard",finding="unresolved"} 6.0
gsd_bindings_total{cluster="dashboard",finding="built_in"} 848.0
```

The four findings add up to 950, the row count above. Through the dashboard pod's loopback, as `dana.lee`
(14:04:51Z):

```text
scope all total 11 excluded_platform 24 namespaces 5
[('dashboard', '11 direct user grants')]
cluster_wide_grants 3 platform_with_findings 2 gso direct [1]
```

These are the "before" numbers of T503-14. PVC UIDs: `group-sync-dashboard-data`
`f065b7a4-535c-4ef1-868c-58f5afee4953`, `group-sync-dashboard-report-artifacts`
`08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, the same as the issue's.

## 2a. Alternatives considered

**A. Where the view reads the provenance.**

| option | source | cost here | decision |
|---|---|---|---|
| A1. Join each `user_binding` row to its own row in `rbac_group_binding` | the issue's decision 2; §2.4 | one SQL fragment and two predicates in `gsd/store.py`, reused by the report snapshot; no schema change | **chosen** |
| A2. A `managed_source`/`exception` column on `user_binding` | the issue's alternative | migration 21, the report service's `KNOWN_SCHEMA_VERSION`, the one-migration-branch rule on the lab, `replace_user_bindings` and its callers; the same facts stored twice | rejected |
| A3. An `acknowledged` flag on `user_binding`, computed by the poller | — | a migration as A2, and a stored conclusion that would lag the label by a refresh exactly as A1 does | rejected |
| A4. Read the label in `UserBindingView` | — | the reader would carry provenance only to store it (A2) | rejected |

**B. What an acknowledged grant becomes.**

| option | source | cost here | decision |
|---|---|---|---|
| B1. Left out of the worklist and the alert, counted beside `excluded_platform`, each one listed | the issue; Kyverno's `skip` result in the PolicyReport, Kubescape's "pass with exceptions" (§2.3) | a count, a paged list, a disclosure on the page | **chosen** |
| B2. Dropped | — | a grant the operator stops seeing at all; the issue's "never dropped" | rejected |
| B3. Kept in the worklist and the alert with a badge | Kubescape's `alertOnly` (§2.3) | the alert's count would not drop, which is what the operator's ruling of 2026-09-26 asks for | rejected |

**C. How a grant is acknowledged.**

| option | source | cost here | decision |
|---|---|---|---|
| C1. The label or the exception annotation on the binding | #353's rule; the ruling of 2026-09-26 (#255) | none: the refresh already reads both | **chosen** |
| C2. A values-file list of grants (`expectedGrants`) | — | withdrawn by the operator, 2026-09-26 | rejected |
| C3. A separate resource naming the exception, like Kyverno's `PolicyException` | §2.3 | a CRD, an RBAC grant to read it, and a second place an acknowledgement can live; Kyverno ships it disabled by default | rejected |
| C4. A per-check annotation, like Polaris' `…/<check>-exempt` | §2.3 | a second annotation for a decision the existing one already records | rejected |

**D. The operator chart's value in the Group gate.**

| option | source | cost here | decision |
|---|---|---|---|
| D1. A second constant beside `CHART_CONFIG_SOURCE` | §2.5 (the value is fixed upstream) | one constant and one tuple; the gate reads the tuple | **chosen** |
| D2. A values list whose default holds both | the issue's alternative | a chart key, a loader, a render check and docs for a value neither chart lets an estate set (only a Helm dependency `alias` renames it, and that fails noisy: the gate opens, nothing is silenced) | rejected |

**E. The acknowledged list on the wire.**

| option | cost here | decision |
|---|---|---|
| E1. Fields on `/user-bindings`, paged by its `limit` and `offset`, not narrowed by `namespace` | the page's one fetch per repaint carries it; every row is reachable by paging | **chosen** |
| E2. Its own `limit`/`offset` parameters | two more parameters for a list the page reads from offset 0 | rejected |
| E3. A separate endpoint | a second fetch per repaint and a second route to gate | rejected |

**F. Which reports follow the rule.**

| option | cost here | decision |
|---|---|---|
| F1. The review figures: the findings report's direct-user table and the compliance snapshot's "Direct user grants", each with the acknowledged count beside it | two consumers filter one flag | **chosen** |
| F2. Every report through `Snapshot.user_bindings` | the access matrix, the certification pack, the namespace report and the privileged-access review would stop listing access a person holds | rejected (orchestrator's note 2) |

**Reconciliation — each external claim, and the code that behaves accordingly.**

| research says | the code does it at |
|---|---|
| a label's value may be empty (§2.1) | `local-development/gsd/store.py#_USER_ACKNOWLEDGED` tests `managed_source IS NOT NULL`, as `_FINDING_CASE` does; `test_the_view_and_the_finding_read_one_rule` labels a binding `config-source: ""` |
| a label selects, an annotation carries text (§2.1) | `acknowledgedGrants` in `local-development/gsd/static/index.html#function acknowledgedGrants(ub)` shows the label as `config-source: <value>` and the exception as quoted text |
| an annotation value can be any string up to 256 KiB (§2.2) | the cell is escaped (`esc`) and wraps (`local-development/gsd/static/app.css#.ack td { overflow-wrap: anywhere; }`); `/metrics` never reads it (T503-12) |
| comparable tools keep an acknowledged finding visible (§2.3) | `local-development/gsd/store.py#def acknowledged_user_bindings` and `#def acknowledged_user_binding_count`, served as `acknowledged_bindings` and `acknowledged` |
| the seven-column key finds at most one row; the subquery flattens to a primary-key SEARCH unless the outer query is DISTINCT (§2.4) | `local-development/gsd/store.py#_USER_PROVENANCE` matches all seven columns, `subject_kind = 'User' AND subject_namespace = ''` among them; the rollup's people query groups instead of DISTINCT (block 10); `test_the_join_matches_each_grant_to_its_own_binding_row` pins each key column and `test_every_provenance_query_searches_rbac_group_binding_by_its_primary_key` every reader's plan |
| the operator chart's value is fixed (§2.5) | `local-development/gsd/kube.py#OPERATOR_CHART_CONFIG_SOURCE` and `PROVENANCE_ONLY_CONFIG_SOURCES`, read by the gate in `_FINDING_CASE` |

## 3. The design

### 3.1 The rule, written once

Four class attributes on `Store`, beside the direct-user methods:

- `_USER_PROVENANCE`: the LEFT JOIN of §2.4, appended after `FROM user_binding`.
- `_USER_ACKNOWLEDGED`: `(is_platform = 0 AND (managed_source IS NOT NULL OR exception IS NOT NULL))`.
- `_USER_TO_REVIEW`: `(is_platform = 0 AND managed_source IS NULL AND exception IS NULL)`, the review rule.
- `_DIRECT_USER_ORDER`: the worklist's existing order, moved out of `direct_user_bindings` so the acknowledged list
  is ordered the same way.

The report service's `Snapshot` reads the same attributes, as it already reads `_FINDING_CASE`, so a report and
the page cannot disagree about one grant. Each line that reads `_USER_ACKNOWLEDGED` or `_USER_TO_REVIEW` carries the
`PLATFORM-CLASSIFICATION (#255, #353)` marker, and the marker test now finds them by name (§3.10).

Reason: the issue's decision 1 is "one review filter everywhere". One definition makes a second one impossible to
write by accident.

### 3.2 Where the rule applies

| surface | before (`dd51b91f`) | after |
|---|---|---|
| worklist rows, `total` (`direct_user_bindings`, `count_direct_user_bindings`) | `is_platform=0` | `is_platform=0` and not acknowledged, unless `include_acknowledged` |
| rollup (`user_bindings_by_namespace`), so the tiles, the cluster-wide card and the namespace select | `is_platform=0` | the review rule |
| the direct-user alert (`compute_alerts`, from the store's default rows) | not `is_platform` | the store's rows, and a row marked `acknowledged` is dropped too |
| the namespace index's `direct_grants`, so `platform_with_findings` | `is_platform = 0` | the review rule at the wide tier; the viewer's own rows at self, as before |
| the envelope's `cluster_wide_grants` | not `is_platform` | not `is_platform` and not acknowledged at the wide tier |
| the namespace page's grants | flag per row; a platform direct grant badged, a platform cluster-wide grant left out of the list | `acknowledged` per row; at the wide tier an acknowledged direct grant is badged and out of the count, and an acknowledged cluster-wide grant is left out of the list, each the way a platform one is |
| the findings report's "Bindings naming a person" | `is_platform=0` | the review rule; the acknowledged ones in their own table |
| the compliance snapshot's "Direct user grants" | `is_platform=0` | the review rule; "Acknowledged direct grants" beside it |
| the access reports, `namespaces_with_bindings`, the namespace page's "People who reach it" | access | unchanged: access (orchestrator's note 2) |
| the compliance snapshot's "Privileged direct grants" and its privileged table (through `Snapshot.user_bindings`, compliance_snapshot.py:24-26), the users report's per-person `direct_bindings` (snapshot.py:512), `Snapshot.binding_namespaces` (snapshot.py:389, the namespace report's "observed" set), the refresh log line's "naming a person" (poller.py:725) | access, presence, or a log line | unchanged: none counts grants to review; each lists or counts access a person holds, or a namespace's presence on a binding (review of the spec, OB2's N2) |

### 3.3 Platform wins

`_USER_ACKNOWLEDGED` requires `is_platform = 0`. A platform identity whose binding is labelled stays in
`excluded_platform` and is never counted as acknowledged, so `excluded_platform` keeps its meaning and its count.
This is the finding's order, where `built_in` is decided before provenance (store.py:2808-2809 before :2826).
`include_platform=true` still lists platform rows whatever their binding carries.

### 3.4 The self tier

A reader's own grants are access they hold, so they are listed acknowledged or not. `/user-bindings` at the self
tier asks with `include_acknowledged`, and so does Home. `acknowledged`, `acknowledged_bindings` and
`acknowledged_truncated` are `null` there, like `excluded_platform`, because they describe other people's grants.
The namespace index at self counts the viewer's own rows as before. The namespace page at self counts every row of
the viewer's and shows no acknowledged badge.

### 3.5 The API

`GET /api/clusters/{c}/user-bindings` gains, at the wide tier:

- `acknowledged`: the count before any limit;
- `acknowledged_bindings`: the rows, worst first, each with `binding_kind`, `binding_namespace`, `binding_name`,
  `role_kind`, `role_name`, `user_name`, `managed_source` and `exception`, paged by the request's `limit` and
  `offset`, never narrowed by `namespace`;
- `acknowledged_truncated`: `offset + len(acknowledged_bindings) < acknowledged`.

Each row of `bindings` gains `acknowledged` (0 or 1). At the wide tier it is always 0. At the self tier it is 1 on
a viewer's own acknowledged grant, and the label value and exception text are not sent there. The namespace page's
`direct_grants` and `cluster_wide_grants` rows gain the same `acknowledged`. No parameter is added and none
changes.

### 3.6 The page

Under the "Exposure by namespace" table, after the platform note, and also on the card shown when no grant is left
to migrate, `acknowledgedGrants(ub)` draws the mock's block: "N grants acknowledged by the operator — counted here
and not in the worklist above or the alert ...", a `Show the N` / `Hide the N` disclosure, and a table with the
columns Person, Grants, Scope, Binding and Acknowledged by. The last column shows a `label` chip with
`config-source: <value>`, an `exception` chip with the quoted text, or both. It starts closed, like "Every grant".
Its state lives in `view.nsAckOpen`, so the 60-second repaint keeps it, and it has an `aria-expanded` button. It
renders nothing when the count is 0 or `null`. Three rules in `app.css` let its head wrap at 375 px and break a
long value inside its cell. The tiles, the cluster-wide card, the namespace select and "Every grant" read the
server's numbers, so they follow the rule with no page change. On the namespace page, at the wide tier, an
acknowledged row wears an `acknowledged` badge beside where a platform row wears `platform`. The header reads
`· N · M platform · K acknowledged`, and the "Direct grants" tile counts N. Its "Reached cluster-wide" list leaves an
acknowledged grant out, as it leaves a platform user's out, so it agrees with the envelope's `cluster_wide_grants`.

### 3.7 The reports

`Snapshot.user_bindings` returns every non-platform direct grant, as before, plus `managed_source`, `exception`
and `acknowledged`. The RBAC findings report filters its "Bindings naming a person" table by the flag, adds the
table "Acknowledged by the operator" (user, scope, role, binding, config-source, exception), and adds
`acknowledged_user` to its totals. `Snapshot.counts` gains `acknowledged_user_bindings`, and its `user_bindings`
becomes the review count. The compliance snapshot shows "Acknowledged direct grants (excluded from Direct user
grants)" beside the platform figure: its "Privileged direct grants", the privileged-access review's figure,
keeps them, as that report does, so the label names the one figure they leave. The other reports change
nothing.

### 3.8 The Group gate

`PROVENANCE_ONLY_CONFIG_SOURCES = (CHART_CONFIG_SOURCE, OPERATOR_CHART_CONFIG_SOURCE)` in `gsd/kube.py`, and the
gate reads `m.managed_source NOT IN ('group-sync-dashboard', 'group-sync-operator-helm')`. With nothing else
labelled, a hand-made grant to a synced Group stays `ok` when the only other Group label is the operator chart's
(T503-4). Any other value still opens the gate (T503-6). ServiceAccount and User rows have no gate, so they are
unchanged.

### 3.9 The budget

**Over the whole system (every polled cluster, every replica, every restart), a direct user grant moves between
"to review" and "acknowledged" only by what the last binding refresh read on its own binding:**

| situation | worklist, `total`, alert | `acknowledged` | when |
|---|---|---|---|
| the binding gains the label or the annotation | −1 | +1 | the next binding refresh (default 3600 s) |
| the label and annotation are removed | +1 | −1 | the next binding refresh |
| the binding list saw the label, the direct-user list then saw the user, in one refresh | −1 | +1 | that refresh |
| the direct-user list saw a user the binding list did not (a binding created between the two calls) | stays | 0 | until a refresh reads both: the alerting direction (tested) |
| the binding list failed (the refresh returns before the direct-user list) | no change: both tables keep the last refresh that read them, so a label removed since stays acknowledged, as the unmanaged finding stays `ok` | no change | until the binding list reads again; the pod log says `binding refresh for <cluster> failed` |
| the direct-user list failed after the binding list read | each kept row reads the fresh provenance: a label added or removed counts at once, a deleted binding's kept row stays a grant to review | follows the label | until the direct-user list reads again |
| the label was removed between the two calls of one refresh | −1 for one more refresh | +1 | the next refresh; the unmanaged finding has the same staleness, one interval |
| a platform identity's binding is labelled | not listed (platform) | 0 | — |
| a restart, a second replica, a values edit | no change: each pod reads the same stored rows | | — |

At most one move per (binding, user) per refresh. Every moved row stays counted (`acknowledged`) and listed
(`acknowledged_bindings`, every row reachable by paging). Nothing is written to any cluster, no permission is added
or removed, no schema changes, and no name enters `/metrics`. `gsd_alerts_total{kind="direct_user_binding"}` still
counts alerts, one per cluster with a grant left to review. The worst case is a label someone added by mistake,
which takes a grant out of the alert. The grant stays listed with its label value, the page counts it, and
`oc get rolebindings,clusterrolebindings -A -l rbac.ocp.io/config-source` finds the label on the cluster.

### 3.10 What does not change

The unmanaged finding's results, except what the gate change rules (T503-6). On the lab
`gsd_bindings_total{finding="unmanaged"}` stays 53. `excluded_platform` keeps its meaning and its count. `/metrics`
carries no names. The `PLATFORM-CLASSIFICATION (#255, #353)` marker stays on every site, and
`tests/test_platform_classification_marker.py` gains `REVIEW_SITE`, so a new read of `_USER_ACKNOWLEDGED` or
`_USER_TO_REVIEW` without the marker fails (T503-13). Other things that stay as they are: the dashboard
ServiceAccount's permissions; every rendered template apart from the chart label; the schema and the report
service's `KNOWN_SCHEMA_VERSION`; the access reports; the self tier's lists; Home; and binding events, since the
event diff reads `user_binding` alone (`local-development/gsd/store.py#Store._append_binding_events`).

### 3.11 Versions

Application MINOR (it changes `local-development/gsd/`) and chart PATCH (`appVersion` moves and one chart document
changes; no value is added), each with its history line, set by hand as the last releases were. The CHANGELOG
bullet goes first under `## Unreleased` and names the chart version, as
`local-development/tests/test_kyverno.py#test_f3_unreleased_cites_the_current_chart_version_when_it_moved_since_the_last_release`
requires. Against `dd51b91f`, those are application 2.1.0 and chart 0.59.26. After SPEC_G2 they are application
2.2.0 and chart 0.60.1 (orchestrator's note 1).

## 4. Tests

### 4.1 One test per test case of the issue

| ID | test (file) | what it holds | why it fails on `dd51b91f` (measured, §4.2) |
|---|---|---|---|
| T503-1 | `test_t503_1_a_labelled_grant_leaves_the_worklist_and_the_alert_and_is_counted` (`tests/test_rbac.py`); `test_t503_1_the_index_and_the_envelope_count_by_the_review_rule` and `test_t503_1_the_detail_lists_an_acknowledged_grant_marked_as_it_lists_a_platform_one` (`tests/test_namespaces_api.py`) | through the real reader and a real binding refresh: a ClusterRoleBinding labelled `config-source: team-x` naming `jdoe` and an unlabelled one naming `asmith` give rows, total and rollup `asmith` only, the alert "1 direct user grant" (also when the alert is handed rows marked acknowledged), acknowledged 1 with `team-x`; on the lab's shape the index reads `group-sync-operator` 0, `cluster_wide_grants` 2 and `platform_with_findings` 0, the self view of the bind account still counts its own, and the namespace page marks the row | the worklist holds `jdoe`; the index reads `group-sync-operator` 1; the page's rows carry no `acknowledged` |
| T503-2 | `test_t503_2_the_exception_annotation_alone_acknowledges_it` (`tests/test_rbac.py`) | the same with `rbac.ocp.io/unmanaged-exception: "vendor access, TICKET-1"` and no label; the row carries the text | the worklist holds `jdoe` |
| T503-3 | `test_t503_3_an_unlabelled_unannotated_grant_still_alerts` (`tests/test_rbac.py`) | Helm's and OLM's labels acknowledge nothing: both grants stay, "2 direct user grants" | regression guard: passes on `dd51b91f` |
| T503-4 | `test_t503_4_the_operator_charts_label_on_a_group_does_not_open_the_gate` (`tests/test_unmanaged_subjects.py`) | a hand-made grant to a synced Group stays `ok` when the only other Group label is `group-sync-operator-helm` | the gate opens: `hand-made` is `unmanaged` |
| T503-5 | `test_t503_5_this_charts_own_label_on_a_group_keeps_the_gate_closed` (same file) | `group-sync-dashboard` on a Group keeps the gate closed | regression guard: passes |
| T503-6 | `test_t503_6_any_other_value_still_opens_it_and_the_lab_shape_counts_the_same` (same file), and the file's existing 53 tests | a policy value still opens the gate; on the lab's shape (the operator chart's value on ServiceAccount and User rows) the counts are `ok` 3, `unmanaged` 3 | regression guard: passes |
| T503-7 | `test_t503_7_a_platform_identity_stays_platform_when_its_binding_is_labelled` (`tests/test_rbac.py`) | a labelled `kubeadmin` counts in `excluded_platform` (1), acknowledged 0, and `include_platform` lists it with `acknowledged` 0 | `acknowledged_user_binding_count` does not exist |
| T503-8 | `test_t503_8_a_self_readers_own_acknowledged_grant_stays_listed_and_the_count_is_withheld` (`tests/test_view_scoping.py`) | at self the viewer's own labelled grant is listed, `total` 1, the three acknowledged fields `null`, Home's `direct_count` 1; at the wide tier it leaves `bindings` and is listed with `team-x` | guard half passes; the new half fails: `KeyError: 'acknowledged'` |
| T503-9 | `test_t503_9_the_acknowledged_grants_are_counted_and_listed_with_what_acknowledged_them`, `test_t503_9_the_acknowledged_list_pages_like_bindings_and_ignores_the_namespace_filter` (`tests/test_user_binding_paging.py`) | three acknowledged (two by the label, one by the exception) and one to review, a labelled platform row: `bindings` `jdoe`, `excluded_platform` 1, `acknowledged` 3 in order with `managed_source`/`exception`; `limit=2` pages them 2 + 1 with `acknowledged_truncated`; `namespace=pay` narrows `bindings` and not the list | `bindings` holds all four people; `KeyError: 'acknowledged_bindings'` |
| T503-10 | `TestAcknowledgedGrantsDisclosure` (`tests/test_ui.py`): the count and the closed disclosure, each row with its label or its quoted exception; the open state across a repaint whose payload changed; nothing when the count is 0 or `null`; no horizontal overflow open or closed at 375, 768 and 1280 px, light and dark; the namespace page's `acknowledged` badge, header and tile | `#du-acknowledged` is never drawn: the page has no `acknowledgedGrants` |
| T503-11 | `test_t503_11_the_snapshot_counts_by_the_review_rule_and_keeps_every_grant_as_access` (`tests/test_reporting_snapshot.py`), `test_t503_11_the_findings_report_lists_them_apart_and_the_snapshot_counts_them` and `test_t503_11_an_acknowledged_privileged_grant_is_still_privileged_access` (`tests/test_reporting_catalogue.py`) | the snapshot's `user_bindings` 1, `acknowledged_user_bindings` 2, `platform_user_bindings` 1, every row with its state; the findings report's direct-user table `frank` only, its acknowledged table the two with their label or text, totals 1/2/1; the compliance snapshot's figures 1 and 2; the access matrix still lists all three | `KeyError: 'acknowledged'`; the findings table lists all three |
| T503-12 | `test_t503_12_the_alert_series_counts_alerts_and_names_nobody` (`tests/test_metrics.py`) | `gsd_alerts_total{kind="direct_user_binding"}` is 1 on the cluster with a grant to review and absent on the one whose only grant is acknowledged; no user, binding, label value or text in the exposition | the name half passes; the count half fails: `c2` alerts too |
| T503-13 | `test_the_review_rule_pattern_sees_its_two_names_but_not_prose` and `test_every_python_site_that_decides_or_consumes_platform_is_marked` (`tests/test_platform_classification_marker.py`) | `REVIEW_SITE` finds `_USER_ACKNOWLEDGED` and `_USER_TO_REVIEW`; every such line is marked | regression guard: passes (nothing reads the names); mutation M5 (§4.2) shows it bite |
| T503-14 | the lab walk, §5 | rows 11 → 9, acknowledged 0 → 2, the alert subject "11 direct user grants" → "9 direct user grants" | the lab runs 2.0.0 |

Added by the research: `test_a_binding_seen_by_one_list_call_and_not_the_other_keeps_alerting` (the issue's
decision 2: one refresh whose direct-user list saw a labelled binding its binding list did not keeps it alerting,
and the next refresh that reads both acknowledges it), `test_the_view_and_the_finding_read_one_rule` (for every
person's row, acknowledged exactly when the unmanaged finding says `ok`, an empty label value included, §2.1), and
`test_a_persons_own_grants_keep_the_acknowledged_ones` (`include_acknowledged`, §3.4),
`test_the_join_matches_each_grant_to_its_own_binding_row` (two clusters, one binding name in two namespaces, one
person on two bindings, two people on one binding, and a Group and a ServiceAccount named like the User on a
labelled binding: each grant reads its own row, none twice) and
`test_every_provenance_query_searches_rbac_group_binding_by_its_primary_key` (every reader of the join, nine
queries, plans a primary-key SEARCH and no SCAN, MATERIALIZE or automatic index, §2.4), all in `tests/test_rbac.py`.

### 4.2 Each test fails without the change

The tests' blocks (43 to 56) were applied alone to a clean export of `dd51b91f`, with `PYTHONPATH` at its
`local-development` (the imported `gsd` read `2.0.0` from that tree), and the new tests run there:

```text
FAILED tests/test_rbac.py::TestAcknowledgedDirectGrants::test_t503_1_a_labelled_grant_leaves_the_worklist_and_the_alert_and_is_counted
    AssertionError: ... At index 0 diff: ['asmith', 'jdoe'] != ['asmith']
FAILED tests/test_rbac.py::TestAcknowledgedDirectGrants::test_t503_2_the_exception_annotation_alone_acknowledges_it
    AssertionError: ... At index 0 diff: ['asmith', 'jdoe'] != ['asmith']
FAILED ...::test_t503_7_a_platform_identity_stays_platform_when_its_binding_is_labelled
    AttributeError: 'Store' object has no attribute 'acknowledged_user_binding_count'
FAILED ...::test_a_binding_seen_by_one_list_call_and_not_the_other_keeps_alerting
    AttributeError: 'Store' object has no attribute 'acknowledged_user_binding_count'
FAILED ...::test_the_view_and_the_finding_read_one_rule
    AttributeError: 'Store' object has no attribute 'acknowledged_user_bindings'
FAILED ...::test_a_persons_own_grants_keep_the_acknowledged_ones
    AssertionError: assert [{'binding_ki...erRole', ...}] == []
FAILED tests/test_namespaces_api.py::...::test_t503_1_the_index_and_the_envelope_count_by_the_review_rule
    AssertionError: assert {'group-sync-...-payments': 1} == {'group-sync-...-payments': 1}  (group-sync-operator 1, not 0)
FAILED tests/test_namespaces_api.py::...::test_t503_1_the_detail_lists_an_acknowledged_grant_marked_as_it_lists_a_platform_one
    KeyError: 'acknowledged'
FAILED tests/test_unmanaged_subjects.py::TestClassification::test_t503_4_the_operator_charts_label_on_a_group_does_not_open_the_gate
    AssertionError: assert {'hand-made':...reader': 'ok'} == {'reader': 'o...d-made': 'ok'}  (hand-made: unmanaged)
FAILED tests/test_view_scoping.py::test_t503_8_a_self_readers_own_acknowledged_grant_stays_listed_and_the_count_is_withheld
    KeyError: 'acknowledged'
FAILED tests/test_user_binding_paging.py::test_t503_9_the_acknowledged_grants_are_counted_and_listed_with_what_acknowledged_them
    AssertionError: ... 'ocp-oauth-bind-serviceid' != 'jdoe'
FAILED tests/test_user_binding_paging.py::test_t503_9_the_acknowledged_list_pages_like_bindings_and_ignores_the_namespace_filter
    KeyError: 'acknowledged_bindings'
FAILED tests/test_reporting_snapshot.py::...::test_t503_11_the_snapshot_counts_by_the_review_rule_and_keeps_every_grant_as_access
    KeyError: 'acknowledged'
FAILED tests/test_reporting_catalogue.py::...::test_t503_11_the_findings_report_lists_them_apart_and_the_snapshot_counts_them
    AssertionError: assert ['frank', 'oc...ndor-support'] == ['frank']
FAILED tests/test_metrics.py::...::test_t503_12_the_alert_series_counts_alerts_and_names_nobody
    AssertionError: {... cluster="c1" ...: 1.0, ... cluster="c2" ...: 1.0}
FAILED tests/test_rbac.py::TestAcknowledgedDirectGrants::test_the_join_matches_each_grant_to_its_own_binding_row
    AttributeError: 'Store' object has no attribute 'acknowledged_user_bindings'
FAILED ...::test_every_provenance_query_searches_rbac_group_binding_by_its_primary_key
    AttributeError: 'Store' object has no attribute 'acknowledged_user_bindings'
FAILED tests/test_reporting_catalogue.py::...::test_t503_11_an_acknowledged_privileged_grant_is_still_privileged_access
    AssertionError: assert (1, 1) == (0, 1)
18 failed, 8 passed
```

The 8 that pass are the guards: T503-3, T503-5, T503-6 and the five cases of
`test_the_review_rule_pattern_sees_its_two_names_but_not_prose`. The browser tests (T503-10) need the page's
`acknowledgedGrants`, which `dd51b91f` does not have. Mutation M11 below removes it from the implemented page and
turns them red.

Mutations of the implemented copy, each in a full copy of the tree, each running the named test files:

| run | the change | result | red |
|---|---|---|---|
| M1 | the worklist keeps acknowledged rows (`include_acknowledged` ignored) | 5 failed, 37 passed | T503-1, T503-2, the one-list case, the finding's rule, a person's own grants |
| M2 | `_USER_ACKNOWLEDGED` without `is_platform = 0` (platform does not win) | 3 failed, 51 passed | T503-7, both T503-9 |
| M3 | the gate skips only `group-sync-dashboard` | 1 failed, 55 passed | T503-4 |
| M4 | the self tier drops its own acknowledged grants | 1 failed, 33 passed | T503-8 |
| M5 | a read of `_USER_TO_REVIEW` loses its marker | 1 failed, 17 passed | `test_every_python_site_that_decides_or_consumes_platform_is_marked` (T503-13) |
| M6 | the alert keeps a row marked acknowledged | 1 failed, 41 passed | T503-1 |
| M7 | the envelope counts acknowledged cluster-wide grants | 1 failed, 26 passed | T503-1 (index and envelope) |
| M8 | the namespace index counts acknowledged grants | 1 failed, 26 passed | T503-1 (index and envelope) |
| M9 | the findings report's direct-user table keeps acknowledged rows | 1 failed, 47 passed | T503-11 (reports) |
| M10 | the snapshot's direct-user figure counts acknowledged rows | 2 failed, 58 passed | both T503-11 |
| M11 | the page drops the disclosure under the worklist | 8 failed, 2 passed | T503-10: the count, the repaint, all six overflow cases |
| M12 | the disclosure's state is kept in the DOM instead of `view` | 1 failed | T503-10: the open state across the repaint |
| M13 | one condition of `_USER_PROVENANCE` dropped, each of the eight in turn (cluster, binding kind, namespace, binding name, user, `subject_kind`, `subject_namespace`, both subject conditions) | over the nine related test files: 2 failed (cluster, binding namespace, binding name, user, `subject_kind`, both subject conditions) or 1 failed (binding kind, `subject_namespace`), of 290 with 3 skipped | the plan test for all eight; the join test for the six that change a result |
| M14 | the rollup's people query back to `SELECT DISTINCT` | 1 failed, 286 passed, 3 skipped | the plan test: `MATERIALIZE (subquery-1)`, `SCAN rbac_group_binding` |
| M15 | G3's index row names #502 (`docs/specs/README.md` and the spec's header) | 1 failed, 85 passed (`tests/test_specs_index.py`, 40 rows) | the pin: `AssertionError: ('G3 is #503', '502')` |

### 4.3 The proof

§7 was not written by hand. The design was implemented in a copy of `dd51b91f`, and each block's Old and New text
was cut from that copy at whole lines with the shortest context that is unique at its turn. Eight blocks were then
moved to anchors no SPEC_G2 block changes (orchestrator's note 1). The 69 blocks, applied in order to a clean
export of `dd51b91f`, gave the implemented copy byte for byte (`cmp` over all 28 files). The review's corrections
(note 5) changed blocks 1, 10, 31, 43, 51, 61 and 65 in place; the count stays 69.

The revision was proved on a fresh `git worktree add --detach … f144a82b`, main after SPEC_G1, SPEC_E2 and SPEC_G2
merged as specifications, with the same code as `dd51b91f`. Main then took SPEC_E4 (`3b3d0010`), which changes no
code (`git diff --stat f144a82b 3b3d0010 -- local-development/gsd charts` is empty); the check below was run there
again, with the same result:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_G3_acknowledged_direct_grants.md <tree>
    69 blocks check out across 28 files
    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_G3_acknowledged_direct_grants.md <tree> --apply
    28 files changed, 916 insertions(+), 62 deletions(-)

On that tree, with `PYTHONPATH` at its `local-development`:

| check | command | result |
|---|---|---|
| the new tests before | the test blocks alone (43–56) on a clean export of `f144a82b` | `18 failed`, each for §4.2's reason; the 8 guards pass |
| hermetic suite | `pytest tests/ -q -p no:cacheprovider --deselect tests/test_ui.py --deselect tests/test_live_smoke.py` | `1 failed, 6252 passed, 26 skipped, 665 deselected, 5 xfailed`; the 26 new hermetic tests pass. The one failure is `test_a_spec_the_changelog_has_not_begun_names_versions_the_tree_has_not_reached` on **SPEC_G2's** row: `('G2', 'app 2.1.0, chart 0.60.0', 'pyproject.toml is already 2.1.0')`. Applied alone on main, this spec's release fields take application 2.1.0, which SPEC_G2's specified row claims. In the build order G2 is implemented first, its row leaves `specified`, and blocks 66–69 are re-derived to 2.2.0 (orchestrator's note 1) |
| browser suite | `pytest tests/test_ui.py -q -p no:cacheprovider --browser chromium` | `661 passed`: the 10 new ones among them |
| mutations | §4.2's M13 (each of the eight join conditions), M14 (`SELECT DISTINCT`), M15 (the index pin) | each red, as §4.2 lists |
| the spec index and citations | `pytest tests/test_specs_index.py tests/test_docs_citations.py` in the spec's own tree (40 rows, on `3b3d0010`) | `1587 passed, 22 skipped` |
| markdown | `markdownlint-cli2` on the CHANGELOG, `API.md`, the exclusions document and `ACCESS_CONTROL.md`, before and after | the same 11 findings before and after (MD004 2, MD012 2, MD018 1, MD040 6), all already on main; the specs index: 0 |
| chart | `helm lint`; `helm template t charts/group-sync-dashboard` of `f144a82b` and of the applied tree (helm v4.3.0), diffed | lint clean; the only differences are the chart label (0.59.25 → 0.59.26) and `app.kubernetes.io/version` on 34 objects each, the two image tags following `appVersion`, and `checksum/config` |
| RBAC | every rendered Role, ClusterRole and binding, atom by atom (rule × group × resource × verb × name; binding × subject) | 66 before, 66 after; REMOVED 0, ADDED 0 |
| Python 3.11 | `ast.parse(source, feature_version=(3, 11))` on the 20 changed Python files | all parse; CI's 3.11 job was not run here |
| after SPEC_G2 | main's SPEC_G2 (75 blocks) applied to a fresh worktree of `f144a82b`, then this spec's blocks 1–65 | 65 apply, 66–69 do not (the release fields, orchestrator's note 1); the hermetic suite on that git tree: `1 failed, 6307 passed, 26 skipped, 675 deselected, 5 xfailed`. The one failure is the same index test on **SPEC_E2's** row, `('E2', 'chart 0.60.0 (chart only)', 'Chart.yaml is already 0.60.0')`, and SPEC_G2 applied alone gives it too: SPEC_E2 and SPEC_G2 both name chart 0.60.0 on main. It is not this spec's, and it is reported to the orchestrator |

The probes (§2.4's plan and timings, §2.7's classification, the mutation runs) ran in a scratch directory and are
not committed. Each is described well enough to repeat: the plan and the timings build a `Store` from
`oc get clusterrolebindings,rolebindings -A -o json`, flattened the way `_binding_views` and `_user_binding_views`
flatten it, and time each store call 50 times; the mutations copy the implemented tree and replace one line each.

## 5. On the lab (the implementing pull request)

Read-only parts were measured on 2026-10-01 (§2.7). The implementing pull request runs the rest, after SPEC_G2's
own walk (its E7 is reverted inside that walk, so these numbers hold), deploying with `release-crc.sh` (a lab walk
is development):

1. Record the UIDs of `group-sync-dashboard-data` and `group-sync-dashboard-report-artifacts` (2026-10-01:
   `f065b7a4-535c-4ef1-868c-58f5afee4953`, `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`).
2. Before: through the pod's loopback as `dana.lee` (the commands of §2.7), on `dashboard`: `total` 11,
   `excluded_platform` 24, the alert subject "11 direct user grants", `cluster_wide_grants` 3,
   `platform_with_findings` 2, `group-sync-operator`'s `direct_grants` 1; on `/metrics`,
   `gsd_alerts_total{cluster="dashboard",kind="direct_user_binding"}` 1.0 and `gsd_bindings_total{finding="unmanaged"}`
   53.0 on `dashboard`, `shared-rnd` and `shared-qa`.
3. Deploy the branch. Wait for the binding refresh line (`<cluster>: N direct-user binding(s), M naming a person`,
   `local-development/gsd/poller.py#naming a person`), which runs at once after a start.
4. After, the same reads: `total` 9, `excluded_platform` 24, `acknowledged` 2 with both rows naming
   `ocp-oauth-bind-serviceid` and `managed_source` `group-sync-operator-helm`, the alert subject "9 direct user
   grants", `cluster_wide_grants` 2, `platform_with_findings` 1 (`openshift-console-user-settings` keeps its two
   console grants), `group-sync-operator`'s `direct_grants` 0; on `/metrics`, the alert series still 1.0 and the
   three `unmanaged` series still 53.0.
5. As `developer` (the self tier, through the pod's loopback): `/user-bindings` lists `developer`'s own console
   RoleBinding, and `acknowledged`, `acknowledged_bindings` and `acknowledged_truncated` are `null`.
6. Screenshots of the Namespace audit tab as `dana.lee`, with the disclosure closed and open, at 375, 768 and 1280
   px, light and dark, with no horizontal overflow, committed under `reports/<date>_<slug>/`.
7. The UIDs again: unchanged.

## 6. What an operator sees, and what it costs

- **On the Namespace audit tab (wide tier):**
  - the worklist, its tiles, the cluster-wide card, the namespace select and "Every grant" drop every grant whose
    binding carries the label or the exception;
  - under the worklist, "N grants acknowledged by the operator", which opens to each grant with its label value or
    exception text;
  - the Namespaces card's "cluster-wide direct grants", its "N of them have a direct grant", and each namespace's
    Direct grants count the same way;
  - a namespace page lists an acknowledged grant with a badge and leaves it out of its Direct grants count.
- **On the lab** (§2.4 computed through this code on the lab's objects; §5 to be read): 11 → 9 grants to
  migrate, 0 → 2 acknowledged, 5 → 4 namespaces at risk, 8 → 7 people exposed; the alert reads "9 direct user
  grants".
- **In the reports:** the RBAC findings report gains a table, "Acknowledged by the operator". The compliance
  snapshot gains a figure, "Acknowledged direct grants". The access reports change nothing.
- **To acknowledge a grant:** label or annotate its binding through whatever owns it (the policy configuration, or
  the team's GitOps repository). The next binding refresh, by default within an hour, applies it. Nothing in this
  chart's values file changes.
- **Time:** under 0.15 ms per query at the lab's size. At a hundred times the lab, the rollup takes 1.9 ms instead
  of 0.7 ms (§2.4).
- **Code:** the table below.

Lines added and removed by §7, from `git diff --numstat` on the implemented copy:

| file | added | removed |
|---|---|---|
| `local-development/gsd/store.py` | 113 | 30 |
| `local-development/gsd/static/index.html` | 54 | 6 |
| `local-development/gsd/api.py` | 31 | 4 |
| `local-development/gsd/reporting/catalogue/binding_findings.py` | 14 | 3 |
| `local-development/gsd/reporting/snapshot.py` | 13 | 4 |
| `local-development/gsd/kube.py` | 9 | 0 |
| `local-development/gsd/storage.py` | 6 | 0 |
| `local-development/gsd/state.py` | 5 | 2 |
| `local-development/gsd/static/app.css` | 5 | 0 |
| `local-development/gsd/reporting/catalogue/compliance_snapshot.py` | 1 | 0 |
| `local-development/tests/test_rbac.py` | 206 | 0 |
| `local-development/tests/test_ui.py` | 88 | 0 |
| `local-development/tests/test_namespaces_api.py` | 57 | 0 |
| `local-development/tests/test_user_binding_paging.py` | 52 | 0 |
| `local-development/tests/test_unmanaged_subjects.py` | 33 | 0 |
| `local-development/tests/test_view_scoping.py` | 30 | 0 |
| `local-development/tests/test_metrics.py` | 28 | 0 |
| `local-development/tests/reporting_seed.py` | 24 | 0 |
| `local-development/tests/test_reporting_catalogue.py` | 48 | 0 |
| `local-development/tests/test_reporting_snapshot.py` | 18 | 0 |
| `local-development/tests/test_platform_classification_marker.py` | 16 | 1 |
| `local-development/API.md` | 22 | 2 |
| `charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md` | 19 | 5 |
| `docs/CHANGELOG.md` | 15 | 0 |
| `charts/group-sync-dashboard/Chart.yaml` | 6 | 2 |
| `docs/ACCESS_CONTROL.md` | 1 | 1 |
| `local-development/pyproject.toml` | 1 | 1 |
| `local-development/gsd/__init__.py` | 1 | 1 |

## 7. Implementation blocks

Applied in this order: `gsd/kube.py` (1), `gsd/store.py` (2–17), `gsd/storage.py` (18–19), `gsd/state.py`
(20–21), `gsd/api.py` (22–26), the report service (27–31), the page (32–42), the tests (43–56), the documents
(57–65), and the release fields (66–69, re-derived after SPEC_G2).

### Block 1 — local-development/gsd/kube.py: the operator chart's fixed config-source, and the two values the Group gate reads as provenance only (§3.8)

<!-- block: local-development/gsd/kube.py | edit -->

Old text:

```python
CHART_CONFIG_SOURCE = "group-sync-dashboard"
```

New text:

```python
CHART_CONFIG_SOURCE = "group-sync-dashboard"
# The config-source the group-sync-operator chart writes on every RBAC object it renders: its chart name, fixed,
# with no values key (`group-sync-operator-helm.rbacLabels`, chart 0.14.1, group-sync-operator-helm-chart#76).
# Provenance for that chart's own objects, like ours, so the gate ignores it too (#503): otherwise a Group added
# through that chart's extraSubjects or token.readers would read as a policy operator in use.
OPERATOR_CHART_CONFIG_SOURCE = "group-sync-operator-helm"
# The config-source values that never show a policy operator is in use: the two charts' own provenance. A
# constant, not a values key: each chart renders its own name and has no key for it. An umbrella chart that
# aliases one renders the alias (Helm's .Chart.Name), which opens the gate as a policy value would: noisy, never silent.
PROVENANCE_ONLY_CONFIG_SOURCES = (CHART_CONFIG_SOURCE, OPERATOR_CHART_CONFIG_SOURCE)
```

### Block 2 — local-development/gsd/store.py: the import the gate reads

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
from .kube import CHART_CONFIG_SOURCE, GROUP_KIND, SYSTEM_GROUP_PREFIX
```

New text:

```python
from .kube import GROUP_KIND, PROVENANCE_ONLY_CONFIG_SOURCES, SYSTEM_GROUP_PREFIX
```

### Block 3 — local-development/gsd/store.py: the namespace index counts by the review rule at the wide tier, the viewer's own rows at self (§3.2, §3.4)

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
            direct = {r["ns"]: r["n"] for r in self._rows(
                f"""SELECT binding_namespace AS ns, COUNT(*) AS n
                      -- PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's flag
                      FROM user_binding WHERE cluster_id=? AND binding_namespace != '' AND is_platform = 0
                      {"AND user_name = ?" if own else ""}
```

New text:

```python
            # The wide tier counts the grants to review (#503: the worklist's rule, so this column, the
            # envelope's counts and the Namespace audit agree); the self tier counts the viewer's own,
            # acknowledged or not — access they hold, as their own rows stay listed.
            direct = {r["ns"]: r["n"] for r in self._rows(
                f"""SELECT binding_namespace AS ns, COUNT(*) AS n
                      FROM user_binding{self._USER_PROVENANCE}
                      -- PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's flag, and at the wide tier the review rule (#503)
                     WHERE cluster_id=? AND binding_namespace != '' AND {"is_platform = 0 AND user_name = ?" if own else self._USER_TO_REVIEW}
```

### Block 4 — local-development/gsd/store.py: the namespace page's grants carry their acknowledged state (§3.2)

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
            def named(namespace: str) -> list[dict]:
                return self._rows(
                    f"""SELECT user_name, binding_kind, binding_name, role_kind, role_name, is_platform
                          FROM user_binding WHERE cluster_id=? AND binding_namespace=?{" AND user_name=?" if own else ""}
                         ORDER BY is_platform, role_name, user_name""",
```

New text:

```python
            # Each grant naming a person carries whether the operator acknowledged it (#503), so the page
            # shows it the way it shows a platform row: listed, badged, and out of the count it reviews.
            def named(namespace: str) -> list[dict]:
                return self._rows(
                    f"""SELECT user_name, binding_kind, binding_name, role_kind, role_name, is_platform,
                               -- PLATFORM-CLASSIFICATION (#255, #353): the row's acknowledged state (#503)
                               CASE WHEN {self._USER_ACKNOWLEDGED} THEN 1 ELSE 0 END AS acknowledged
                          FROM user_binding{self._USER_PROVENANCE}
                         WHERE cluster_id=? AND binding_namespace=?{" AND user_name=?" if own else ""}
                         ORDER BY is_platform, acknowledged, role_name, user_name""",
```

### Block 5 — local-development/gsd/store.py: the finding's comment names the operator chart's value

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
                        -- auditor binding being on every host by default (#312). A
```

New text:

```python
                        -- auditor binding being on every host by default (#312), and neither is
                        -- the group-sync-operator chart's (#503): each is a chart's provenance. A
```

### Block 6 — local-development/gsd/store.py: the Group gate skips both charts' values (§3.8)

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
                                         AND m.managed_source <> '""" + CHART_CONFIG_SOURCE + """'))
```

New text:

```python
                                         AND m.managed_source NOT IN (""" + ", ".join(
                                             f"'{v}'" for v in PROVENANCE_ONLY_CONFIG_SOURCES) + """)))
```

### Block 7 — local-development/gsd/store.py: the rule, written once — `_USER_PROVENANCE`, `_USER_ACKNOWLEDGED`, `_USER_TO_REVIEW`, `_DIRECT_USER_ORDER` (§3.1)

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
        }

    def user_bindings_by_namespace(self, cluster_id: str) -> list[dict]:
```

New text:

```python
        }

    # A DIRECT USER GRANT THE OPERATOR ACKNOWLEDGED (#503). The operator's rule (#353) is the unmanaged
    # finding's: a grant that is not a platform identity's is silenced only by the rbac.ocp.io/config-source
    # label (any value) or the rbac.ocp.io/unmanaged-exception annotation on its binding. The binding refresh
    # already stores both for every subject kind, a User's included, on rbac_group_binding, so a direct-user
    # row reads them from its own (binding, User) row there: no column, no migration. The join matches that
    # table's whole primary key, so it finds at most one row, and its columns are renamed so that no column
    # of user_binding becomes ambiguous in a query that joins it. The two tables are written from two list
    # calls of one refresh: a row seen by one and not the other has no provenance here, and stays a grant to
    # review — the alerting direction. Platform wins: a platform row is never acknowledged, so
    # excluded_platform keeps its meaning and its count.
    _USER_PROVENANCE = """
          LEFT JOIN (SELECT cluster_id AS ack_cluster, binding_kind AS ack_kind, binding_namespace AS ack_namespace,
                            binding_name AS ack_name, group_name AS ack_user, managed_source, exception
                       FROM rbac_group_binding WHERE subject_kind = 'User' AND subject_namespace = '')
                 ON ack_cluster = user_binding.cluster_id AND ack_kind = user_binding.binding_kind
                AND ack_namespace = user_binding.binding_namespace AND ack_name = user_binding.binding_name
                AND ack_user = user_binding.user_name"""
    # PLATFORM-CLASSIFICATION (#255, #353): acknowledged (#503) — not the platform's, and the operator's label or exception on the binding
    _USER_ACKNOWLEDGED = "(is_platform = 0 AND (managed_source IS NOT NULL OR exception IS NOT NULL))"
    # PLATFORM-CLASSIFICATION (#255, #353): the one review rule (#503) — neither the platform's nor acknowledged
    _USER_TO_REVIEW = "(is_platform = 0 AND managed_source IS NULL AND exception IS NULL)"
    # cluster-admin first, then cluster-scoped, then namespaced: the order somebody migrating would work in.
    # Ordering is applied BEFORE any limit, so a truncated page is the worst N rather than an arbitrary N.
    _DIRECT_USER_ORDER = """ ORDER BY CASE WHEN role_name='cluster-admin' THEN 0 ELSE 1 END,
                            CASE WHEN binding_namespace='' THEN 0 ELSE 1 END,
                            binding_namespace, user_name"""

    def user_bindings_by_namespace(self, cluster_id: str) -> list[dict]:
```

### Block 8 — local-development/gsd/store.py: the rollup's docstring

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
        say what it left out rather than quietly shrinking the number.
```

New text:

```python
        say what it left out rather than quietly shrinking the number. Grants the operator
        acknowledged on their binding leave it the same way and are counted by
        `acknowledged_user_binding_count` (#503).
```

### Block 9 — local-development/gsd/store.py: the rollup's counts follow the review rule

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
                              AS cluster_scoped
                     FROM user_binding
                    -- PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's flag
                    WHERE cluster_id=? AND is_platform=0
                    GROUP BY namespace
```

New text:

```python
                              AS cluster_scoped
                     FROM user_binding""" + self._USER_PROVENANCE + """
                    -- PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's review rule (#503)
                    WHERE cluster_id=? AND """ + self._USER_TO_REVIEW + """
                    GROUP BY namespace
```

### Block 10 — local-development/gsd/store.py: the rollup's people follow the review rule, grouped rather than DISTINCT so the join stays a primary-key SEARCH (§2.4)

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
                """SELECT DISTINCT
                          CASE WHEN binding_namespace = '' THEN '(cluster-scoped)'
                               ELSE binding_namespace END AS namespace,
                          user_name
                     FROM user_binding
                    -- PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's flag
                    WHERE cluster_id=? AND is_platform=0
                    ORDER BY user_name""",
```

New text:

```python
                # GROUP BY, not DISTINCT (#503): SQLite never flattens a subquery on the right of a LEFT
                # JOIN into a DISTINCT query (optoverview.html, flattening constraint 3), so DISTINCT read
                # _USER_PROVENANCE by materializing it — a SCAN of all of rbac_group_binding and an
                # automatic index — where GROUP BY keeps the primary-key SEARCH. The same pairs.
                """SELECT CASE WHEN binding_namespace = '' THEN '(cluster-scoped)'
                               ELSE binding_namespace END AS namespace,
                          user_name
                     FROM user_binding""" + self._USER_PROVENANCE + """
                    -- PLATFORM-CLASSIFICATION (#255, #353): the direct-user view's review rule (#503)
                    WHERE cluster_id=? AND """ + self._USER_TO_REVIEW + """
                    GROUP BY namespace, user_name
                    ORDER BY user_name""",
```

### Block 11 — local-development/gsd/store.py: `_direct_user_binding_where` takes `include_acknowledged`

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
        self, cluster_id: str, include_platform: bool, namespace: str | None,
        user_name: str | None = None,
    ) -> tuple[str, list]:
```

New text:

```python
        self, cluster_id: str, include_platform: bool, namespace: str | None,
        user_name: str | None = None, include_acknowledged: bool = False,
    ) -> tuple[str, list]:
```

### Block 12 — local-development/gsd/store.py: its docstring

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
        dedicated index until a real cluster shows it needed.
```

New text:

```python
        dedicated index until a real cluster shows it needed.

        `include_acknowledged` keeps the grants the operator acknowledged on their binding
        (#503). Off, they leave as the platform's identities do: the review worklist and the
        alert. On, for a person's own grants (the self tier, Home), which stay access they
        hold. It never brings back a platform row: platform wins.
```

### Block 13 — local-development/gsd/store.py: off, the acknowledged grants leave the rows and the count (§3.2)

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
            sql += " AND is_platform=0"
```

New text:

```python
            sql += " AND is_platform=0"
        if not include_acknowledged:
            # PLATFORM-CLASSIFICATION (#255, #353): and the grants the operator acknowledged (#503); a platform row stays the platform's
            sql += " AND NOT " + self._USER_ACKNOWLEDGED
```

### Block 14 — local-development/gsd/store.py: `direct_user_bindings` takes `include_acknowledged`

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
        offset: int = 0,
        user_name: str | None = None,
    ) -> list[dict]:
```

New text:

```python
        offset: int = 0,
        user_name: str | None = None,
        include_acknowledged: bool = False,
    ) -> list[dict]:
```

### Block 15 — local-development/gsd/store.py: each row carries `acknowledged`; the order is the shared one

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
        """
        where, params = self._direct_user_binding_where(
            cluster_id, include_platform, namespace, user_name)
        sql = ("""SELECT binding_kind, binding_namespace, binding_name, role_kind,
                         role_name, user_name, is_platform
                    FROM user_binding""" + where +
               # cluster-admin first, then cluster-scoped, then namespaced: the order
               # somebody migrating would work in. Ordering is applied BEFORE the limit, so
               # a truncated page is the worst N rather than an arbitrary N.
               """ ORDER BY CASE WHEN role_name='cluster-admin' THEN 0 ELSE 1 END,
                            CASE WHEN binding_namespace='' THEN 0 ELSE 1 END,
                            binding_namespace, user_name""")
```

New text:

```python

        Each row says whether the operator acknowledged it (`acknowledged`, #503), which is 0
        unless `include_acknowledged` let one in, and never carries the label's value or the
        exception's text: those are `acknowledged_user_bindings`', for the wide tier.
        """
        where, params = self._direct_user_binding_where(
            cluster_id, include_platform, namespace, user_name, include_acknowledged)
        sql = ("""SELECT binding_kind, binding_namespace, binding_name, role_kind,
                         role_name, user_name, is_platform,
                         -- PLATFORM-CLASSIFICATION (#255, #353): the row's acknowledged state (#503)
                         CASE WHEN """ + self._USER_ACKNOWLEDGED + """ THEN 1 ELSE 0 END AS acknowledged
                    FROM user_binding""" + self._USER_PROVENANCE + where + self._DIRECT_USER_ORDER)
```

### Block 16 — local-development/gsd/store.py: `count_direct_user_bindings` takes `include_acknowledged`

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
    ) -> int:
        """How many rows `direct_user_bindings` would return before its limit."""
        where, params = self._direct_user_binding_where(
            cluster_id, include_platform, namespace, user_name)
        rows = self._rows(
            "SELECT COUNT(*) AS n FROM user_binding" + where, tuple(params))
```

New text:

```python
        include_acknowledged: bool = False,
    ) -> int:
        """How many rows `direct_user_bindings` would return before its limit."""
        where, params = self._direct_user_binding_where(
            cluster_id, include_platform, namespace, user_name, include_acknowledged)
        rows = self._rows(
            "SELECT COUNT(*) AS n FROM user_binding" + self._USER_PROVENANCE + where, tuple(params))
```

### Block 17 — local-development/gsd/store.py: `acknowledged_user_bindings` and `acknowledged_user_binding_count` (§3.5)

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python
            "SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=1",
            (cluster_id,),
        )
        return int(rows[0]["n"]) if rows else 0
```

New text:

```python
            "SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=1",
            (cluster_id,),
        )
        return int(rows[0]["n"]) if rows else 0

    def acknowledged_user_bindings(
        self, cluster_id: str, limit: int | None = None, offset: int = 0,
    ) -> list[dict]:
        """The direct user grants the operator acknowledged (#503), worst first, each with what
        acknowledged it: `managed_source` (the rbac.ocp.io/config-source label's value) and
        `exception` (the rbac.ocp.io/unmanaged-exception annotation's text), either or both.
        Counted and listed, never dropped: the worklist and the alert leave them out, and this is
        where a reader reaches each one. Never a platform row: platform wins."""
        sql = ("""SELECT binding_kind, binding_namespace, binding_name, role_kind, role_name,
                         user_name, managed_source, exception
                    FROM user_binding""" + self._USER_PROVENANCE + """
                    -- PLATFORM-CLASSIFICATION (#255, #353): the acknowledged rows (#503)
                   WHERE cluster_id=? AND """ + self._USER_ACKNOWLEDGED + self._DIRECT_USER_ORDER)
        params: list = [cluster_id]
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params += [limit, offset]
        return self._rows(sql, tuple(params))

    def acknowledged_user_binding_count(self, cluster_id: str) -> int:
        """How many direct user grants the operator acknowledged (#503): the count beside
        `platform_user_binding_count`, before any limit."""
        rows = self._rows(
            "SELECT COUNT(*) AS n FROM user_binding" + self._USER_PROVENANCE
            # PLATFORM-CLASSIFICATION (#255, #353): the acknowledged count (#503)
            + " WHERE cluster_id=? AND " + self._USER_ACKNOWLEDGED,
            (cluster_id,),
        )
        return int(rows[0]["n"]) if rows else 0
```

### Block 18 — local-development/gsd/storage.py: the contract declares `include_acknowledged` on the rows

<!-- block: local-development/gsd/storage.py | edit -->

Old text:

```python
        offset: int = 0,
        user_name: str | None = None,
    ) -> list[dict]: ...
```

New text:

```python
        offset: int = 0,
        user_name: str | None = None,
        include_acknowledged: bool = False,
    ) -> list[dict]: ...
```

### Block 19 — local-development/gsd/storage.py: on the count, and the two new methods (`tests/test_storage_seam.py`)

<!-- block: local-development/gsd/storage.py | edit -->

Old text:

```python
        user_name: str | None = None,
    ) -> int: ...
    def user_bindings_by_namespace(self, cluster_id: str) -> list[dict]: ...
```

New text:

```python
        user_name: str | None = None,
        include_acknowledged: bool = False,
    ) -> int: ...
    def acknowledged_user_bindings(
        self, cluster_id: str, limit: int | None = None, offset: int = 0,
    ) -> list[dict]: ...
    def acknowledged_user_binding_count(self, cluster_id: str) -> int: ...
    def user_bindings_by_namespace(self, cluster_id: str) -> list[dict]: ...
```

### Block 20 — local-development/gsd/state.py: the alert's comment (the issue's correction 4: the detail lives on the Namespace audit tab)

<!-- block: local-development/gsd/state.py | edit -->

Old text:

```python
    # migration effort, not each row. The detail lives on the RBAC policy page.
```

New text:

```python
    # migration effort, not each row. The detail lives on the Namespace audit tab. A grant the
    # operator acknowledged on its binding (#503) is left out as a platform identity is: the store's
    # worklist rows never carry one, and a row that says so is dropped here too, so the count and
    # the worklist cannot disagree.
```

### Block 21 — local-development/gsd/state.py: the alert drops a row marked acknowledged (§3.2)

<!-- block: local-development/gsd/state.py | edit -->

Old text:

```python
    people = [u for u in (user_bindings or []) if not u.get("is_platform")]
```

New text:

```python
    people = [u for u in (user_bindings or []) if not u.get("is_platform") and not u.get("acknowledged")]
```

### Block 22 — local-development/gsd/api.py: the envelope's `cluster_wide_grants` follows the review rule at the wide tier (§3.2)

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
        cluster_wide_grants = len([d for d in wide["cluster_wide_grants"] if not d["is_platform"]])
```

New text:

```python
        # ... and the grants the operator acknowledged (#503) at the wide tier, the worklist's rule; the self
        # tier counts its own, acknowledged or not, as the store's namespace counts do.
        # PLATFORM-CLASSIFICATION (#255, #353): the cluster-wide grants to review (#503)
        cluster_wide_grants = len([d for d in wide["cluster_wide_grants"]
                                   if not d["is_platform"] and not (d["acknowledged"] and me is None)])
```

### Block 23 — local-development/gsd/api.py: Home keeps the viewer's own acknowledged grants (§3.4)

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
        direct = store.direct_user_bindings(cluster_id, include_platform=True, user_name=me)
```

New text:

```python
        # The viewer's own direct grants, acknowledged ones included (#503): access they hold.
        direct = store.direct_user_bindings(cluster_id, include_platform=True, user_name=me,
                                            include_acknowledged=True)
```

### Block 24 — local-development/gsd/api.py: the `/user-bindings` docstring

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
        always reported so the page can say what it left out.

        `bindings` IS PAGED; `by_namespace` IS NOT, and the asymmetry is deliberate. The
```

New text:

```python
        always reported so the page can say what it left out.

        A grant the operator acknowledged on its binding — the `rbac.ocp.io/config-source`
        label, any value, or the `rbac.ocp.io/unmanaged-exception` annotation, the rule the
        unmanaged finding keeps (#353) — leaves `bindings`, `total` and `by_namespace` the same
        way (#503) and is counted in `acknowledged`, beside `excluded_platform`.
        `acknowledged_bindings` lists each one with its `managed_source` (the label's value) or
        `exception` (the annotation's text), worst first and paged by the same `limit` and
        `offset` as `bindings`, never narrowed by `namespace`: like `by_namespace` it is the
        cluster's. A platform identity's grant is never acknowledged: it stays in
        `excluded_platform`. At the self tier all three are null, and the viewer's own grants
        are listed acknowledged or not: they are access the viewer holds.

        `bindings` IS PAGED; `by_namespace` IS NOT, and the asymmetry is deliberate. The
```

### Block 25 — local-development/gsd/api.py: the review rule at the wide tier, the viewer's own grants at self; the acknowledged count and rows (§3.5)

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
        total = store.count_direct_user_bindings(
            cluster_id, include_platform=include_platform, namespace=namespace,
            user_name=me)
        rows = store.direct_user_bindings(
            cluster_id, include_platform=include_platform, namespace=namespace,
            limit=limit, offset=offset, user_name=me)
```

New text:

```python
        # The review rule at the wide tier; the viewer's own grants at self, acknowledged or not (#503).
        total = store.count_direct_user_bindings(
            cluster_id, include_platform=include_platform, namespace=namespace,
            user_name=me, include_acknowledged=me is not None)
        rows = store.direct_user_bindings(
            cluster_id, include_platform=include_platform, namespace=namespace,
            limit=limit, offset=offset, user_name=me, include_acknowledged=me is not None)
        acknowledged = store.acknowledged_user_binding_count(cluster_id) if scope == "all" else None
        acknowledged_rows = (store.acknowledged_user_bindings(cluster_id, limit=limit, offset=offset)
                             if scope == "all" else None)
```

### Block 26 — local-development/gsd/api.py: the three fields, beside `excluded_platform`

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
                store.platform_user_binding_count(cluster_id) if scope == "all" else None,
```

New text:

```python
                store.platform_user_binding_count(cluster_id) if scope == "all" else None,
            # #503: the grants the operator acknowledged on the binding — counted beside the platform's,
            # and each one reachable with what acknowledged it. Withheld at self, as the platform count is.
            "acknowledged": acknowledged,
            "acknowledged_bindings": acknowledged_rows,
            "acknowledged_truncated":
                None if acknowledged is None else offset + len(acknowledged_rows) < acknowledged,
```

### Block 27 — local-development/gsd/reporting/snapshot.py: every direct grant says whether it is acknowledged, and with what (§3.7)

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->

Old text:

```python
        sql = """SELECT binding_kind, binding_namespace, binding_name, role_kind, role_name, user_name, is_platform
                   FROM user_binding WHERE cluster_id=?"""
```

New text:

```python
        """Every direct user grant: the access a person holds by name, which the access reports list in full.
        Each row says whether the operator acknowledged it (#503, the Store's rule), with what: the
        direct-user finding and its count leave those rows out and say how many."""
        sql = """SELECT binding_kind, binding_namespace, binding_name, role_kind, role_name, user_name, is_platform,
                        managed_source, exception,
                        -- PLATFORM-CLASSIFICATION (#255, #353): the row's acknowledged state (#503)
                        CASE WHEN """ + Store._USER_ACKNOWLEDGED + """ THEN 1 ELSE 0 END AS acknowledged
                   FROM user_binding""" + Store._USER_PROVENANCE + """ WHERE cluster_id=?"""
```

### Block 28 — local-development/gsd/reporting/snapshot.py: the snapshot's direct-user figure follows the review rule, the acknowledged count beside it

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->

Old text:

```python
            # PLATFORM-CLASSIFICATION (#255, #353): the compliance snapshot's user-binding scalars split on the direct-user view's flag
            "user_bindings": one("SELECT COUNT(*) AS n FROM user_binding WHERE cluster_id=? AND is_platform=0"),
```

New text:

```python
            # PLATFORM-CLASSIFICATION (#255, #353): the compliance snapshot's user-binding scalars split on the direct-user view's review rule (#503)
            "user_bindings": one("SELECT COUNT(*) AS n FROM user_binding" + Store._USER_PROVENANCE
                                 + " WHERE cluster_id=? AND " + Store._USER_TO_REVIEW),   # PLATFORM-CLASSIFICATION (#255, #353)
            "acknowledged_user_bindings": one("SELECT COUNT(*) AS n FROM user_binding" + Store._USER_PROVENANCE
                                              + " WHERE cluster_id=? AND " + Store._USER_ACKNOWLEDGED),   # PLATFORM-CLASSIFICATION (#255, #353)
```

### Block 29 — local-development/gsd/reporting/catalogue/binding_findings.py: the direct-user table is the worklist's

<!-- block: local-development/gsd/reporting/catalogue/binding_findings.py | edit -->

Old text:

```python
    users = snap.user_bindings(cid)
    users, t = cut(users)
```

New text:

```python
    # The dashboard's one review rule (#503): a grant the operator acknowledged on its binding leaves the
    # direct-user finding as it leaves the worklist and the alert, and is listed in its own table.
    every = snap.user_bindings(cid)
    acknowledged = [u for u in every if u["acknowledged"]]
    users, t = cut([u for u in every if not u["acknowledged"]])
    truncated = truncated or t
    acknowledged_shown, t = cut(acknowledged)
```

### Block 30 — local-development/gsd/reporting/catalogue/binding_findings.py: the acknowledged grants in their own table, and in the totals

<!-- block: local-development/gsd/reporting/catalogue/binding_findings.py | edit -->

Old text:

```python
    ], page_break=True))
    totals = {**{k: counts.get(k, 0) for k, _ in _DEFINITIONS}, "direct_user": len(users), "platform_user": snap.platform_user_binding_count(cid)}
```

New text:

```python
        Table("Acknowledged by the operator", ["user", "scope", "role", "binding", "config-source", "exception"],
              [[u["user_name"], ns_label(u["binding_namespace"]), f"{u['role_kind']}/{u['role_name']}", u["binding_name"],
                "" if u["managed_source"] is None else u["managed_source"], u["exception"] or ""] for u in acknowledged_shown],
              note=f"{len(acknowledged)} direct grant(s) whose binding carries rbac.ocp.io/config-source or the rbac.ocp.io/unmanaged-exception annotation: excluded from the table above, as from the dashboard's worklist and alert, and listed here so a reviewer can re-judge each one.",
              empty_text="none"),
    ], page_break=True))
    totals = {**{k: counts.get(k, 0) for k, _ in _DEFINITIONS}, "direct_user": len(users), "platform_user": snap.platform_user_binding_count(cid),
              "acknowledged_user": len(acknowledged)}
```

### Block 31 — local-development/gsd/reporting/catalogue/compliance_snapshot.py: the acknowledged figure

<!-- block: local-development/gsd/reporting/catalogue/compliance_snapshot.py | edit -->

Old text:

```python
                               ("Direct user grants", c["user_bindings"]), ("Platform identity grants (excluded from the direct-user figures)", c["platform_user_bindings"]),
```

New text:

```python
                               ("Direct user grants", c["user_bindings"]), ("Platform identity grants (excluded from the direct-user figures)", c["platform_user_bindings"]),
                               ("Acknowledged direct grants (excluded from Direct user grants)", c["acknowledged_user_bindings"]),
```

### Block 32 — local-development/gsd/static/index.html: the disclosure's state, closed on arrival (§3.6)

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
                nsGrantsOpen: false };
```

New text:

```html
                nsGrantsOpen: false,
                /* The acknowledged grants' list (#503) starts closed too, like Every grant: the
                   count beside it is the finding, the rows are the detail. */
                nsAckOpen: false };
```

### Block 33 — local-development/gsd/static/index.html: the namespace page decides `self` first and names the acknowledged test

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
  const via = d.via_groups || [], wide = d.cluster_wide_groups || [], direct = d.direct_grants || [];
```

New text:

```html
  const via = d.via_groups || [], wide = d.cluster_wide_groups || [], direct = d.direct_grants || [];
  const self = d.scope === "self";
  // #503: at the wide tier a grant the operator acknowledged is listed and badged, and left out of the counts
  // the way a platform row is; at self the rows are the viewer's own, and every one counts.
  const acknowledged = (x) => !self && !!x.acknowledged;
```

### Block 34 — local-development/gsd/static/index.html: its Direct grants count leaves an acknowledged row out at the wide tier

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
  const people = direct.filter((x) => !x.is_platform);
```

New text:

```html
  const people = direct.filter((x) => !x.is_platform && !acknowledged(x));
```

### Block 35 — local-development/gsd/static/index.html: so does its list of cluster-wide grants naming a person

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
  const wideGrants = (d.cluster_wide_grants || []).filter((x) => !x.is_platform);
  const wideBindings = wide.length + wideGrants.length;
  const self = d.scope === "self";
```

New text:

```html
  const wideGrants = (d.cluster_wide_grants || []).filter((x) => !x.is_platform && !acknowledged(x));
  const wideBindings = wide.length + wideGrants.length;
```

### Block 36 — local-development/gsd/static/index.html: its header counts the acknowledged rows apart

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
    <h2>Direct grants <span class="muted fw-normal">· ${people.length}${direct.length > people.length ? ` · ${direct.length - people.length} platform` : ""}</span></h2>
```

New text:

```html
    <h2>Direct grants <span class="muted fw-normal">· ${people.length}${direct.some((x) => x.is_platform) ? ` · ${direct.filter((x) => x.is_platform).length} platform` : ""}${direct.some(acknowledged) ? ` · ${direct.filter(acknowledged).length} acknowledged` : ""}</span></h2>
```

### Block 37 — local-development/gsd/static/index.html: an acknowledged row wears its badge

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
        <td><button type="button" class="drill">${esc(x.user_name)}</button>${/* PLATFORM-CLASSIFICATION (#255, #353): the platform badge */ ""}${x.is_platform ? ' <span class="badge unknown"><span class="glyph" aria-hidden="true"></span>platform</span>' : ""}</td>
```

New text:

```html
        <td><button type="button" class="drill">${esc(x.user_name)}</button>${/* PLATFORM-CLASSIFICATION (#255, #353): the platform badge */ ""}${x.is_platform ? ' <span class="badge unknown"><span class="glyph" aria-hidden="true"></span>platform</span>' : ""}${acknowledged(x) ? ' <span class="badge unknown"><span class="glyph" aria-hidden="true"></span>acknowledged</span>' : ""}</td>
```

### Block 38 — local-development/gsd/static/index.html: the disclosure on the card with no grant left to migrate

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
      </div>
    </section>`;
  }

  const worst = rows[0].risk;
```

New text:

```html
      </div>
      ${acknowledgedGrants(ub)}
    </section>`;
  }

  const worst = rows[0].risk;
```

### Block 39 — local-development/gsd/static/index.html: the disclosure under the worklist

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
  </section>

  <section class="card">
    <h3>How to close it</h3>
```

New text:

```html
    ${acknowledgedGrants(ub)}
  </section>

  <section class="card">
    <h3>How to close it</h3>
```

### Block 40 — local-development/gsd/static/index.html: `acknowledgedGrants` (§3.6)

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
}

/* The policy operator's CR health. Rendered only when the CRDs exist on the cluster —
```

New text:

```html
}

/* The direct user grants the operator acknowledged on their binding (#503): the
   `rbac.ocp.io/config-source` label, any value, or the `rbac.ocp.io/unmanaged-exception` annotation —
   the rule the unmanaged finding keeps. They leave the worklist, its tiles and the alert, and are
   counted and listed here, each with what acknowledged it: suppressed means counted, never dropped.
   Wide tier only; at self the server sends null and nothing renders. */
function acknowledgedGrants(ub) {
  const n = ub.acknowledged || 0;
  if (!n) return "";
  const rows = ub.acknowledged_bindings || [];
  const open = !!view.nsAckOpen;
  const by = (b) => [
    b.managed_source != null ? `<span class="rp-chip k-identity">label</span> <code>config-source: ${esc(b.managed_source)}</code>` : "",
    b.exception != null ? `<span class="rp-chip k-rbac">exception</span> “${esc(b.exception)}”` : "",
  ].filter(Boolean).join("<br>");
  return `<div class="ack mt-6" id="du-acknowledged">
    <div class="section-head">
      <span class="filterbar-note"><strong>${n} grant${n === 1 ? "" : "s"} acknowledged by the operator</strong> — counted
        here and not in the worklist above or the alert, because each binding carries <code>rbac.ocp.io/config-source</code>
        or the <code>rbac.ocp.io/unmanaged-exception</code> annotation, the rule the unmanaged finding already keeps.</span>
      <button type="button" class="disclose" data-ns-ack aria-expanded="${open}" aria-controls="ack-rows">
        <span class="disclose-arrow" aria-hidden="true">${open ? "▾" : "▸"}</span>
        ${open ? "Hide" : "Show"} the ${n}</button>
    </div>
    <div id="ack-rows" class="scroll-x mt-4"${open ? "" : " hidden"}><table class="audit-table">
      <thead><tr><th>Person</th><th>Grants</th><th>Scope</th><th>Binding</th><th>Acknowledged by</th></tr></thead>
      <tbody>${rows.map((b) => `<tr>
        <td><strong>${esc(b.user_name)}</strong></td>
        <td><code class="priv">${esc(b.role_name)}</code> <span class="muted">${esc(b.role_kind)}</span></td>
        <td>${b.binding_namespace ? esc(b.binding_namespace) : "cluster-wide"}</td>
        <td class="muted">${esc(b.binding_name)}</td>
        <td>${by(b)}</td>
      </tr>`).join("")}</tbody>
    </table>
    ${ub.acknowledged_truncated ? `<div class="filterbar-note truncation-note">Showing the
      <strong>${rows.length}</strong> highest-privilege of <strong>${n}</strong> acknowledged grants.</div>` : ""}</div>
  </div>`;
}

/* The policy operator's CR health. Rendered only when the CRDs exist on the cluster —
```

### Block 41 — local-development/gsd/static/index.html: its button's handler

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
  if (disclose) disclose.onclick = () => { view.nsGrantsOpen = !view.nsGrantsOpen; render(); };
```

New text:

```html
  if (disclose) disclose.onclick = () => { view.nsGrantsOpen = !view.nsGrantsOpen; render(); };
  const ack = document.querySelector("[data-ns-ack]");
  if (ack) ack.onclick = () => { view.nsAckOpen = !view.nsAckOpen; render(); };
```

### Block 42 — local-development/gsd/static/app.css: the disclosure's head wraps at 375 px, a long value breaks in its cell

<!-- block: local-development/gsd/static/app.css | edit -->

Old text:

```css
.section-head .flush { flex: 1; }
```

New text:

```css
.section-head .flush { flex: 1; }
/* The acknowledged grants (#503): a sentence beside its button, so the head wraps at 375 px instead of
   pushing the page sideways, and a label value or exception text breaks inside its cell. */
.ack .section-head { flex-wrap: wrap; align-items: flex-start; }
.ack .section-head .filterbar-note { flex: 1 1 260px; min-width: 0; overflow-wrap: anywhere; }
.ack td { overflow-wrap: anywhere; }
```

### Block 43 — local-development/tests/test_rbac.py: T503-1, T503-2, T503-3, T503-7, the one-list case, the finding's rule, a person's own grants

<!-- block: local-development/tests/test_rbac.py | edit -->

Old text:

```python


class TestDirectUserAlert:
```

New text:

```python


class TestAcknowledgedDirectGrants:
    """#503: a direct user grant whose binding carries the operator's `rbac.ocp.io/config-source` label (any
    value) or the `rbac.ocp.io/unmanaged-exception` annotation is acknowledged. It leaves the worklist, its
    total, its rollup and the alert — the unmanaged finding's own rule (#353) — and is counted and listed
    instead, never dropped. The rows go through the real reader and a real binding refresh, so the provenance
    the view reads is the one the refresh stored."""

    @staticmethod
    def _crb(name, user, role="edit", labels=None, annotations=None):
        return {"metadata": {"name": name, "labels": labels or {}, "annotations": annotations or {}},
                "roleRef": {"kind": "ClusterRole", "name": role}, "subjects": [{"kind": "User", "name": user}]}

    def _refresh(self, store, monkeypatch, objects, user_list_only=()):
        """One binding refresh over ClusterRoleBindings. `user_list_only` are seen by the direct-user list
        call and not by the binding list call — the two calls of one refresh disagreeing."""
        from gsd import poller
        from gsd.config import ClusterConfig
        from gsd.kube import _user_binding_views

        class FakeClient:
            def __init__(self, *a, **kw): pass
            def fetch_bindings(self):
                return [v for o in objects for v in _binding_views(o, "ClusterRoleBinding")]
            def fetch_user_bindings(self):
                return [v for o in [*objects, *user_list_only] for v in _user_binding_views(o, "ClusterRoleBinding")]
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", FakeClient)
        poller.refresh_bindings(store, ClusterConfig("crc", "https://x", token_env="T"), timeout=5)

    @staticmethod
    def _alert_subjects(store, include_acknowledged=False):
        from datetime import UTC, datetime, timedelta as td
        import gsd.state as st
        rows = (store.direct_user_bindings("crc", include_acknowledged=True) if include_acknowledged
                else store.direct_user_bindings("crc"))
        return [a.subject for a in st.compute_alerts("crc", [], [], datetime.now(UTC), td(minutes=2), user_bindings=rows)]

    def _worklist(self, store):
        return ([r["user_name"] for r in store.direct_user_bindings("crc")],
                store.count_direct_user_bindings("crc"),
                [(r["namespace"], r["users"]) for r in store.user_bindings_by_namespace("crc")])

    def test_t503_1_a_labelled_grant_leaves_the_worklist_and_the_alert_and_is_counted(self, store, monkeypatch):
        self._refresh(store, monkeypatch, [
            self._crb("jdoe-edit", "jdoe", labels={"rbac.ocp.io/config-source": "team-x"}),
            self._crb("asmith-edit", "asmith")])
        assert self._worklist(store) == (["asmith"], 1, [("(cluster-scoped)", ["asmith"])])
        assert self._alert_subjects(store) == ["1 direct user grant"]
        assert self._alert_subjects(store, include_acknowledged=True) == ["1 direct user grant"], (
            "the alert drops a row that says it is acknowledged, whoever hands it the rows")
        assert store.acknowledged_user_binding_count("crc") == 1
        assert [(r["user_name"], r["binding_name"], r["managed_source"], r["exception"])
                for r in store.acknowledged_user_bindings("crc")] == [("jdoe", "jdoe-edit", "team-x", None)]
        assert store.platform_user_binding_count("crc") == 0

    def test_t503_2_the_exception_annotation_alone_acknowledges_it(self, store, monkeypatch):
        self._refresh(store, monkeypatch, [
            self._crb("jdoe-edit", "jdoe", annotations={"rbac.ocp.io/unmanaged-exception": "vendor access, TICKET-1"}),
            self._crb("asmith-edit", "asmith")])
        assert self._worklist(store) == (["asmith"], 1, [("(cluster-scoped)", ["asmith"])])
        assert self._alert_subjects(store) == ["1 direct user grant"]
        assert [(r["user_name"], r["managed_source"], r["exception"]) for r in store.acknowledged_user_bindings("crc")] == [
            ("jdoe", None, "vendor access, TICKET-1")]

    def test_t503_3_an_unlabelled_unannotated_grant_still_alerts(self, store, monkeypatch):
        """Regression guard against over-suppression: a Helm or OLM label, or a name, acknowledges nothing."""
        self._refresh(store, monkeypatch, [
            self._crb("jdoe-edit", "jdoe", labels={"app.kubernetes.io/managed-by": "Helm",
                                                  "olm.owner": "x"}),
            self._crb("asmith-edit", "asmith")])
        assert self._worklist(store) == (["asmith", "jdoe"], 2, [("(cluster-scoped)", ["asmith", "jdoe"])])
        assert self._alert_subjects(store) == ["2 direct user grants"]

    def test_t503_7_a_platform_identity_stays_platform_when_its_binding_is_labelled(self, store, monkeypatch):
        """Platform wins, as in the finding, where built_in is decided before provenance: excluded_platform
        keeps its meaning and its count."""
        self._refresh(store, monkeypatch, [
            self._crb("ka", "kubeadmin", role="cluster-admin", labels={"rbac.ocp.io/config-source": "team-x"})])
        assert store.platform_user_binding_count("crc") == 1
        assert store.acknowledged_user_binding_count("crc") == 0 and store.acknowledged_user_bindings("crc") == []
        assert [(r["user_name"], r["is_platform"], r["acknowledged"])
                for r in store.direct_user_bindings("crc", include_platform=True)] == [("kubeadmin", 1, 0)]

    def test_a_binding_seen_by_one_list_call_and_not_the_other_keeps_alerting(self, store, monkeypatch):
        """The two tables come from two list calls of one refresh (poller.refresh_bindings). A labelled binding
        the direct-user list saw and the binding list did not has no stored provenance, so it stays a grant to
        review: the alerting direction, until the next refresh reads both."""
        labelled = self._crb("jdoe-edit", "jdoe", labels={"rbac.ocp.io/config-source": "team-x"})
        self._refresh(store, monkeypatch, [], user_list_only=[labelled])
        assert self._worklist(store) == (["jdoe"], 1, [("(cluster-scoped)", ["jdoe"])])
        assert self._alert_subjects(store) == ["1 direct user grant"]
        assert store.acknowledged_user_binding_count("crc") == 0
        self._refresh(store, monkeypatch, [labelled])
        assert self._worklist(store) == ([], 0, []) and self._alert_subjects(store) == []
        assert store.acknowledged_user_binding_count("crc") == 1

    def test_the_view_and_the_finding_read_one_rule(self, store, monkeypatch):
        """For every person's row, acknowledged here exactly when the unmanaged finding says `ok` — an empty
        label value included, which Kubernetes allows and the finding already honours (IS NOT NULL)."""
        self._refresh(store, monkeypatch, [
            self._crb("a", "ann", labels={"rbac.ocp.io/config-source": ""}),
            self._crb("b", "bob", labels={"rbac.ocp.io/config-source": "group-sync-operator-helm"}),
            self._crb("c", "cat", annotations={"rbac.ocp.io/unmanaged-exception": "break-glass"}),
            self._crb("d", "dan")])
        finding = {r["group_name"]: r["finding"] for r in store.all_bindings("crc") if r["subject_kind"] == "User"}
        acknowledged = {r["user_name"] for r in store.acknowledged_user_bindings("crc")}
        assert finding == {"ann": "ok", "bob": "ok", "cat": "ok", "dan": "unmanaged"}
        assert acknowledged == {u for u, f in finding.items() if f == "ok"}
        assert [r["user_name"] for r in store.direct_user_bindings("crc")] == ["dan"]

    def test_a_persons_own_grants_keep_the_acknowledged_ones(self, store, monkeypatch):
        """The self tier and Home ask with include_acknowledged: an acknowledged grant is still access held."""
        self._refresh(store, monkeypatch, [self._crb("jdoe-edit", "jdoe", labels={"rbac.ocp.io/config-source": "team-x"})])
        assert store.direct_user_bindings("crc", user_name="jdoe") == []
        own = store.direct_user_bindings("crc", user_name="jdoe", include_acknowledged=True)
        assert [(r["user_name"], r["acknowledged"]) for r in own] == [("jdoe", 1)]
        assert store.count_direct_user_bindings("crc", user_name="jdoe", include_acknowledged=True) == 1

    def test_the_join_matches_each_grant_to_its_own_binding_row(self, store, monkeypatch):
        """The provenance join matches the whole primary key: the cluster, the binding (kind, namespace, name)
        and the User subject. Each pair below differs from its neighbour in one of those only, so a join that
        dropped one would lend a label to the wrong grant or count one grant twice."""
        from gsd import poller
        from gsd.config import ClusterConfig
        from gsd.kube import _user_binding_views

        def rb(ns, name, subjects, labelled):
            labels = {"rbac.ocp.io/config-source": "team-x"} if labelled else {}
            return {"kind": "RoleBinding", "metadata": {"name": name, "namespace": ns, "labels": labels},
                    "roleRef": {"kind": "ClusterRole", "name": "edit"}, "subjects": subjects}

        def user(name):
            return {"kind": "User", "name": name}

        objects = {"crc": [rb("ns-a", "edit", [user("jdoe")], True), rb("ns-b", "edit", [user("jdoe")], False),
                           rb("ns-c", "bob-a", [user("bob")], True), rb("ns-c", "bob-b", [user("bob")], False),
                           rb("ns-d", "pair", [user("ann"), user("cat")], True),
                           rb("ns-e", "dev", [{"kind": "Group", "name": "dev"}, user("dev")], True),
                           rb("ns-f", "builder", [{"kind": "ServiceAccount", "name": "builder", "namespace": "ci"},
                                                  user("builder")], True),
                           rb("ns-g", "shared", [user("eve")], True)],
                   "other": [rb("ns-g", "shared", [user("eve")], False)]}

        class FakeClient:
            def __init__(self, cluster, timeout):
                self.objects = objects[cluster.name]
            def fetch_bindings(self):
                return [v for o in self.objects for v in _binding_views(o, o["kind"])]
            def fetch_user_bindings(self):
                return [v for o in self.objects for v in _user_binding_views(o, o["kind"])]
            def fetch_operator_configs(self): return None

        monkeypatch.setattr(poller, "ClusterClient", FakeClient)
        store.upsert_cluster("other", "https://y", True)
        for name in ("crc", "other"):
            poller.refresh_bindings(store, ClusterConfig(name, "https://x", token_env="T"), timeout=5)
        key = lambda rows: sorted((r["binding_namespace"], r["binding_name"], r["user_name"]) for r in rows)  # noqa: E731
        acknowledged = [("ns-a", "edit", "jdoe"), ("ns-c", "bob-a", "bob"), ("ns-d", "pair", "ann"), ("ns-d", "pair", "cat"),
                        ("ns-e", "dev", "dev"), ("ns-f", "builder", "builder"), ("ns-g", "shared", "eve")]
        to_review = [("ns-b", "edit", "jdoe"), ("ns-c", "bob-b", "bob")]
        assert key(store.acknowledged_user_bindings("crc")) == acknowledged
        assert store.acknowledged_user_binding_count("crc") == 7
        assert key(store.direct_user_bindings("crc")) == to_review and store.count_direct_user_bindings("crc") == 2
        assert key(store.direct_user_bindings("crc", include_acknowledged=True)) == sorted(acknowledged + to_review)
        assert key(store.direct_user_bindings("other")) == [("ns-g", "shared", "eve")]
        assert store.acknowledged_user_binding_count("other") == 0

    def test_every_provenance_query_searches_rbac_group_binding_by_its_primary_key(self, store, monkeypatch):
        """Each query that reads _USER_PROVENANCE must look up a grant's own row by rbac_group_binding's
        whole primary key, never read the subquery by materializing it: that is a SCAN of every subject
        row on the cluster, ServiceAccounts and Groups included, plus an automatic index. SQLite never
        flattens a subquery on the right of a LEFT JOIN into a DISTINCT query (optoverview.html,
        flattening constraint 3), and a join that loses a key column loses the full SEARCH too."""
        import sqlite3
        if sqlite3.sqlite_version_info < (3, 40, 0):
            pytest.skip("SQLite flattens a LEFT JOIN's subquery under an aggregate from 3.40.0 (select.c, rule 3c)")
        self._refresh(store, monkeypatch, [
            self._crb("jdoe-edit", "jdoe", labels={"rbac.ocp.io/config-source": "team-x"}),
            self._crb("asmith-edit", "asmith")])
        real, seen = Store._rows, []

        def recording(self_, sql, params=()):
            seen.append((sql, tuple(params)))
            return real(self_, sql, params)

        monkeypatch.setattr(Store, "_rows", recording)
        store.direct_user_bindings("crc", limit=10)
        store.count_direct_user_bindings("crc")
        store.user_bindings_by_namespace("crc")
        store.acknowledged_user_bindings("crc", limit=10)
        store.acknowledged_user_binding_count("crc")
        store.namespaces("crc")
        store.namespace_detail("crc", "")
        joined = [(sql, params) for sql, params in seen if "ack_cluster" in sql]
        assert len(joined) == 9, len(joined)
        search = ("SEARCH rbac_group_binding USING INDEX sqlite_autoindex_rbac_group_binding_1 (cluster_id=? AND "
                  "binding_kind=? AND binding_namespace=? AND binding_name=? AND subject_kind=? AND "
                  "subject_namespace=? AND group_name=?)")
        for sql, params in joined:
            plan = [r["detail"] for r in real(store, "EXPLAIN QUERY PLAN " + sql, params)]
            assert any(line.startswith(search) for line in plan), (plan, sql)
            assert not any(line.startswith(("SCAN rbac_group_binding", "MATERIALIZE")) or "AUTOMATIC" in line
                           for line in plan), (plan, sql)


class TestDirectUserAlert:
```

### Block 44 — local-development/tests/test_namespaces_api.py: T503-1 on the namespace index, the envelope and the namespace page

<!-- block: local-development/tests/test_namespaces_api.py | edit -->

Old text:

```python


class TestTheDetail:
```

New text:

```python


class TestAcknowledgedGrantsCountLikeTheWorklist:
    """#503: the Namespaces card counted the same rows the worklist drops — "3 cluster-wide direct grants",
    "2 of them have a direct grant", group-sync-operator's "Direct grants 1" on the lab while the worklist
    above them, with the label honoured, says 2 and leaves that namespace out. One review rule everywhere:
    the index, the envelope and the detail leave the acknowledged grants out of their counts at the wide
    tier; the detail still lists each one, marked; the self tier counts the viewer's own, acknowledged or not."""

    BIND = "ocp-oauth-bind-serviceid"

    def _client(self, tmp_path) -> TestClient:
        db = str(tmp_path / "ack.db")
        s = Store(db)
        now = now_iso()
        s.upsert_cluster("crc", "https://api.crc.testing:6443", True)
        s.record_poll("crc", "ok", None)
        s.replace_namespaces("crc", [{"name": n, "created_at": now, "phase": "Active", "metadata": {}}
                                     for n in ("group-sync-operator", "legacy-payments")], now)
        grants = [("ClusterRoleBinding", "", "group-sync-dashboard-cluster-poller", self.BIND, "group-sync-operator-helm"),
                  ("RoleBinding", "group-sync-operator", "group-sync-dashboard-cluster-poller-token-reader", self.BIND,
                   "group-sync-operator-helm"),
                  ("ClusterRoleBinding", "", "jdoe-edit", "jdoe", None),
                  ("ClusterRoleBinding", "", "cluster-reader", "dana.lee", None),
                  ("RoleBinding", "legacy-payments", "asmith-admin", "asmith", None)]
        s.replace_user_bindings("crc", [
            {"binding_kind": k, "binding_namespace": ns, "binding_name": name, "role_kind": "ClusterRole",
             "role_name": "view", "user_name": user, "is_platform": 0} for k, ns, name, user, _ in grants], now)
        s.replace_bindings("crc", [
            {"binding_kind": k, "binding_namespace": ns, "binding_name": name, "role_kind": "ClusterRole",
             "role_name": "view", "group_name": user, "subject_kind": "User", "managed_source": label}
            for k, ns, name, user, label in grants], now)
        s.close()
        settings = Settings(clusters=[ClusterConfig("crc", "https://api.crc.testing:6443", token_env="X")],
                            db_path=db, oauth_proxy_enabled=True, namespace_metadata_labels=KEYS,
                            platform_namespaces=PlatformNamespaces(additional_suffixes=("-operator",)))
        app = build_app(settings, run_poller=False)
        app.state.tier_resolver = _Map({"root": "all"})
        return TestClient(app)

    def test_t503_1_the_index_and_the_envelope_count_by_the_review_rule(self, tmp_path):
        with self._client(tmp_path) as c:
            body = c.get("/api/clusters/crc/namespaces", headers=ROOT).json()
            mine = c.get("/api/clusters/crc/namespaces", headers={"X-Forwarded-User": self.BIND}).json()
        direct = {n["name"]: n["direct_grants"] for n in body["namespaces"]}
        assert direct == {"group-sync-operator": 0, "legacy-payments": 1}
        assert (body["cluster_wide_grants"], body["platform_with_findings"]) == (2, 0)
        assert mine["scope"] == "self", "the bind account's own view counts its own grants, acknowledged or not"
        assert ({n["name"]: n["direct_grants"] for n in mine["namespaces"]}["group-sync-operator"],
                mine["cluster_wide_grants"]) == (1, 1)

    def test_t503_1_the_detail_lists_an_acknowledged_grant_marked_as_it_lists_a_platform_one(self, tmp_path):
        with self._client(tmp_path) as c:
            d = c.get("/api/clusters/crc/namespaces/group-sync-operator", headers=ROOT).json()
        assert [(x["user_name"], x["is_platform"], x["acknowledged"]) for x in d["direct_grants"]] == [(self.BIND, 0, 1)]
        assert sorted((x["user_name"], x["acknowledged"]) for x in d["cluster_wide_grants"]) == [
            ("dana.lee", 0), ("jdoe", 0), (self.BIND, 1)]


class TestTheDetail:
```

### Block 45 — local-development/tests/test_unmanaged_subjects.py: the operator chart's value, written out

<!-- block: local-development/tests/test_unmanaged_subjects.py | edit -->

Old text:

```python
SYNCED = "app-ocp-rbac-team-ns-admin"
```

New text:

```python
SYNCED = "app-ocp-rbac-team-ns-admin"
# The group-sync-operator chart's fixed config-source (its rbacLabels helper, chart 0.14.1), written out so this
# file still collects on a tree without gsd.kube's constant for it (#503).
OPERATOR_CHART = "group-sync-operator-helm"
```

### Block 46 — local-development/tests/test_unmanaged_subjects.py: T503-4, T503-5, T503-6

<!-- block: local-development/tests/test_unmanaged_subjects.py | edit -->

Old text:

```python
        assert findings(store) == {"decided": "ok", "hand-made-sa": "unmanaged", "hand-made": "ok"}

    def test_an_account_named_like_a_synced_group_borrows_nothing_from_it(self, store):
```

New text:

```python
        assert findings(store) == {"decided": "ok", "hand-made-sa": "unmanaged", "hand-made": "ok"}

    def test_t503_4_the_operator_charts_label_on_a_group_does_not_open_the_gate(self, store):
        """#503: the group-sync-operator chart labels every RBAC object it renders with its own name
        (`group-sync-operator-helm`, fixed, no values key), so a Group added through its extraSubjects carries
        it. That is the chart's provenance, like this chart's own value, never evidence that a policy operator
        is in use: a hand-made grant to a synced Group stays `ok` while it is the only Group label."""
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("reader", managed_source=OPERATOR_CHART), group("hand-made")], T)
        assert findings(store) == {"reader": "ok", "hand-made": "ok"}
        assert store.count_bindings_by_finding("crc") == {"ok": 2}

    def test_t503_5_this_charts_own_label_on_a_group_keeps_the_gate_closed(self, store):
        """Regression guard (#312, #354): the chart's own value on a Group binding is provenance, as before."""
        _synced(store, SYNCED)
        store.replace_bindings("crc", [group("auditor", managed_source=CHART_CONFIG_SOURCE), group("hand-made")], T)
        assert findings(store) == {"auditor": "ok", "hand-made": "ok"}

    def test_t503_6_any_other_value_still_opens_it_and_the_lab_shape_counts_the_same(self, store):
        """Regression guard: a policy operator's value still opens the gate, and on the lab's shape — the
        operator chart's value on ServiceAccount and User rows only, other values on Group rows (measured
        2026-10-01) — every count is what it was before #503."""
        _synced(store, SYNCED)
        rows = [group("baseline", managed_source="baseline-nonprod-rbac"), group("hand-made"),
                sa("poller-sa", managed_source=OPERATOR_CHART),
                user("poller-user", person="ocp-oauth-bind-serviceid", managed_source=OPERATOR_CHART),
                user("person"), sa("hand-made-sa")]
        store.replace_bindings("crc", rows, T)
        assert findings(store) == {"baseline": "ok", "hand-made": "unmanaged", "poller-sa": "ok", "poller-user": "ok",
                                   "person": "unmanaged", "hand-made-sa": "unmanaged"}
        assert store.count_bindings_by_finding("crc") == {"ok": 3, "unmanaged": 3}

    def test_an_account_named_like_a_synced_group_borrows_nothing_from_it(self, store):
```

### Block 47 — local-development/tests/test_view_scoping.py: T503-8

<!-- block: local-development/tests/test_view_scoping.py | edit -->

Old text:

```python


def test_self_membership_changes_are_the_viewers_only(tmp_path):
```

New text:

```python


def test_t503_8_a_self_readers_own_acknowledged_grant_stays_listed_and_the_count_is_withheld(tmp_path):
    """#503: the acknowledged filter is the wide tier's review rule. A reader's own grant whose binding the
    operator labelled is still access they hold, so the self view and Home keep it; the acknowledged count
    and list aggregate other people's grants, so self gets null for both, as for excluded_platform."""
    c = _client(tmp_path)
    wide_client = _client(tmp_path, tier_resolver=_admin)
    store = Store(str(tmp_path / "t.db"))
    store.replace_bindings("c1", [
        {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "crb-gone",
         "role_kind": "ClusterRole", "role_name": "view", "group_name": "gone-group"},
        {"binding_kind": "RoleBinding", "binding_namespace": "dev", "binding_name": "rb1", "role_kind": "ClusterRole",
         "role_name": "edit", "group_name": VIEWER, "subject_kind": "User", "managed_source": "team-x"},
    ], now_iso())
    store.close()

    body = c.get("/api/clusters/c1/user-bindings", headers=AS_VIEWER).json()
    assert body["scope"] == "self"
    assert [b["user_name"] for b in body["bindings"]] == [VIEWER] and body["total"] == 1
    assert body["acknowledged"] is None and body["acknowledged_bindings"] is None
    assert body["acknowledged_truncated"] is None
    home = c.get("/api/clusters/c1/home", headers=AS_VIEWER).json()
    assert home["answer"]["direct_count"] == 1, "Home still counts the viewer's own acknowledged grant"

    wide = wide_client.get("/api/clusters/c1/user-bindings", headers=AS_VIEWER).json()
    assert wide["scope"] == "all"
    assert [b["user_name"] for b in wide["bindings"]] == ["jdoe"], "the worklist leaves it out"
    assert wide["acknowledged"] == 1
    assert [(b["user_name"], b["managed_source"]) for b in wide["acknowledged_bindings"]] == [(VIEWER, "team-x")]


def test_self_membership_changes_are_the_viewers_only(tmp_path):
```

### Block 48 — local-development/tests/test_user_binding_paging.py: T503-9

<!-- block: local-development/tests/test_user_binding_paging.py | edit -->

Old text:

```python


def test_limit_is_bounded(client):
```

New text:

```python


# ── #503: the grants the operator acknowledged — counted beside the platform's, each one reachable ──

def _acknowledged_app(tmp_path):
    """Three acknowledged grants (two by the label, one by the exception annotation), one to review, and a
    platform identity whose binding is labelled too: the platform wins."""
    db = str(tmp_path / "ack.db")
    store = Store(db)
    store.upsert_cluster("c1", "https://x", True)
    grants = [("ClusterRoleBinding", "", "poller", "cluster-admin", "ocp-oauth-bind-serviceid", 0, "group-sync-operator-helm", None),
              ("RoleBinding", "ops", "reader", "view", "ocp-oauth-bind-serviceid", 0, "group-sync-operator-helm", None),
              ("RoleBinding", "pay", "vendor-view", "view", "vendor-support", 0, None, "vendor read-only access, TICKET-7"),
              ("RoleBinding", "pay", "jdoe-edit", "edit", "jdoe", 0, None, None),
              ("ClusterRoleBinding", "", "ka", "cluster-admin", "kubeadmin", 1, "team-x", None)]
    store.replace_user_bindings("c1", [
        {"binding_kind": k, "binding_namespace": ns, "binding_name": name, "role_kind": "ClusterRole",
         "role_name": role, "user_name": user, "is_platform": platform}
        for k, ns, name, role, user, platform, _, _ in grants], now_iso())
    store.replace_bindings("c1", [
        {"binding_kind": k, "binding_namespace": ns, "binding_name": name, "role_kind": "ClusterRole",
         "role_name": role, "group_name": user, "subject_kind": "User", "is_platform": platform,
         "managed_source": label, "exception": exception}
        for k, ns, name, role, user, platform, label, exception in grants], now_iso())
    store.close()
    settings = Settings(db_path=db, clusters=[ClusterConfig("c1", "https://x", token_env="T")])
    return TestClient(build_app(settings, run_poller=False))


def test_t503_9_the_acknowledged_grants_are_counted_and_listed_with_what_acknowledged_them(tmp_path):
    body = _acknowledged_app(tmp_path).get("/api/clusters/c1/user-bindings").json()
    assert [b["user_name"] for b in body["bindings"]] == ["jdoe"] and body["total"] == 1
    assert [r["namespace"] for r in body["by_namespace"]] == ["pay"]
    assert body["excluded_platform"] == 1, "a labelled platform identity stays the platform's"
    assert body["acknowledged"] == 3 and body["acknowledged_truncated"] is False
    assert [(b["user_name"], b["binding_namespace"], b["binding_name"], b["role_name"], b["managed_source"], b["exception"])
            for b in body["acknowledged_bindings"]] == [
        ("ocp-oauth-bind-serviceid", "", "poller", "cluster-admin", "group-sync-operator-helm", None),
        ("ocp-oauth-bind-serviceid", "ops", "reader", "view", "group-sync-operator-helm", None),
        ("vendor-support", "pay", "vendor-view", "view", None, "vendor read-only access, TICKET-7")]


def test_t503_9_the_acknowledged_list_pages_like_bindings_and_ignores_the_namespace_filter(tmp_path):
    client = _acknowledged_app(tmp_path)
    get_ = lambda **p: client.get("/api/clusters/c1/user-bindings", params=p).json()   # noqa: E731
    first, second = get_(limit=2), get_(limit=2, offset=2)
    assert [b["binding_name"] for b in first["acknowledged_bindings"]] == ["poller", "reader"]
    assert first["acknowledged_truncated"] is True and first["acknowledged"] == 3
    assert [b["binding_name"] for b in second["acknowledged_bindings"]] == ["vendor-view"]
    assert second["acknowledged_truncated"] is False
    narrowed = get_(namespace="pay")
    assert narrowed["total"] == 1 and narrowed["acknowledged"] == 3 and len(narrowed["acknowledged_bindings"]) == 3


def test_limit_is_bounded(client):
```

### Block 49 — local-development/tests/reporting_seed.py: the acknowledged seed, written through the Store

<!-- block: local-development/tests/reporting_seed.py | edit -->

Old text:

```python
    return snapshots, artifacts
```

New text:

```python
    return snapshots, artifacts


def seed_acknowledged(db_path: str) -> Store:
    """The direct user grants of #503, written through the Store as a binding refresh writes them — each User
    row twice, in user_binding and with its binding's provenance in rbac_group_binding: one to review (frank),
    two the operator acknowledged (the bind account by the operator chart's label, vendor-support by the
    exception annotation) and a platform account whose binding is labelled too (the platform wins)."""
    now = _iso(NOW)
    store = Store(db_path)
    store.upsert_cluster(CLUSTER, "https://api.crc.testing:6443", True)
    store.record_poll(CLUSTER, "ok", None)
    grants = [("ClusterRoleBinding", "", "frank-admin", "cluster-admin", "frank", 0, None, None),
              ("ClusterRoleBinding", "", "poller", "view", "ocp-oauth-bind-serviceid", 0, "group-sync-operator-helm", None),
              ("RoleBinding", "pay", "vendor-view", "view", "vendor-support", 0, None, "vendor read-only access, TICKET-7"),
              ("ClusterRoleBinding", "", "sa-admin", "cluster-admin", "system:serviceaccount:openshift-x:y", 1, "team-x", None)]
    store.replace_user_bindings(CLUSTER, [
        {"binding_kind": k, "binding_namespace": ns, "binding_name": name, "role_kind": "ClusterRole", "role_name": role,
         "user_name": user, "is_platform": platform} for k, ns, name, role, user, platform, _, _ in grants], now)
    store.replace_bindings(CLUSTER, [
        {"binding_kind": k, "binding_namespace": ns, "binding_name": name, "role_kind": "ClusterRole", "role_name": role,
         "group_name": user, "subject_kind": "User", "is_platform": platform, "managed_source": label, "exception": exception}
        for k, ns, name, role, user, platform, label, exception in grants], now)
    store.replace_operator_configs(CLUSTER, None, now)
    return store
```

### Block 50 — local-development/tests/test_reporting_snapshot.py: T503-11 on the snapshot

<!-- block: local-development/tests/test_reporting_snapshot.py | edit -->

Old text:

```python
            assert RAW_ERROR not in repr(crs) and "error_message" not in crs[0]
```

New text:

```python
            assert RAW_ERROR not in repr(crs) and "error_message" not in crs[0]


class TestAcknowledgedDirectGrants:
    def test_t503_11_the_snapshot_counts_by_the_review_rule_and_keeps_every_grant_as_access(self, tmp_path):
        """#503: the reports' copy uses the dashboard's one review rule. The direct-user figure leaves out
        the grants the operator acknowledged and a count of its own carries them; the rows stay access a
        person holds, each saying whether it is acknowledged and with what, for the access reports."""
        from reporting_seed import seed_acknowledged
        store = seed_acknowledged(str(tmp_path / "w.db"))
        d = tmp_path / "s"; d.mkdir(); path = write_snapshot(store, d)
        store.close()
        with Snapshot(path) as snap:
            counts = snap.counts(CLUSTER)
            rows = {r["user_name"]: (r["acknowledged"], r["managed_source"], r["exception"]) for r in snap.user_bindings(CLUSTER)}
        assert (counts["user_bindings"], counts["acknowledged_user_bindings"], counts["platform_user_bindings"]) == (1, 2, 1)
        assert rows == {"frank": (0, None, None),
                        "ocp-oauth-bind-serviceid": (1, "group-sync-operator-helm", None),
                        "vendor-support": (1, None, "vendor read-only access, TICKET-7")}
```

### Block 51 — local-development/tests/test_reporting_catalogue.py: T503-11 on the reports

<!-- block: local-development/tests/test_reporting_catalogue.py | edit -->

Old text:

```python
        assert grp.totals["groups"] == 1 and grp.totals["changes"] <= self._built(snapshot, "groups").totals["changes"]
```

New text:

```python
        assert grp.totals["groups"] == 1 and grp.totals["changes"] <= self._built(snapshot, "groups").totals["changes"]


class TestAcknowledgedDirectGrants:
    def test_t503_11_the_findings_report_lists_them_apart_and_the_snapshot_counts_them(self, tmp_path):
        """#503: the RBAC findings report's direct-user table is the worklist's — the acknowledged grants
        leave it and are listed in a table of their own with what acknowledged them — and the compliance
        snapshot's direct-user figure is the alert's, with the acknowledged count beside the platform's.
        The access reports still list every grant: it is access a person holds."""
        from reporting_seed import seed_acknowledged
        store = seed_acknowledged(str(tmp_path / "w.db"))
        d = tmp_path / "s"; d.mkdir(); path = write_snapshot(store, d)
        store.close()
        with Snapshot(path) as snap:
            bf, cs, am = (_build(snap, n) for n in ("binding-findings", "compliance-snapshot", "access-matrix"))
        tables = {b.title: b for s in bf.sections for b in s.blocks if getattr(b, "kind", "") == "table"}
        assert [r[0] for r in tables["Bindings naming a person"].rows] == ["frank"]
        assert [(r[0], r[4], r[5]) for r in tables["Acknowledged by the operator"].rows] == [
            ("ocp-oauth-bind-serviceid", "group-sync-operator-helm", ""), ("vendor-support", "", "vendor read-only access, TICKET-7")]
        assert (bf.totals["direct_user"], bf.totals["acknowledged_user"], bf.totals["platform_user"]) == (1, 2, 1)
        figures = {k: v for s in cs.sections for b in s.blocks if getattr(b, "items", None) for k, v in b.items}
        assert figures["Direct user grants"] == 1
        assert figures["Acknowledged direct grants (excluded from Direct user grants)"] == 2
        matrix = next(b for s in am.sections for b in s.blocks if getattr(b, "title", "") == "Matrix")
        assert sorted(r[1] for r in matrix.rows) == ["frank", "ocp-oauth-bind-serviceid", "vendor-support"]

    def test_t503_11_an_acknowledged_privileged_grant_is_still_privileged_access(self, tmp_path):
        """An acknowledged grant leaves the review figure only. A break-glass cluster-admin that carries the
        exception is still privileged access, so "Privileged direct grants" (the privileged-access review's
        figure) and its table keep it, and the acknowledged figure names the one figure it is left out of."""
        from gsd.store import Store
        from reporting_seed import _iso
        store = Store(str(tmp_path / "w.db"))
        now = _iso(NOW)
        store.upsert_cluster(CLUSTER, "https://api.crc.testing:6443", True)
        store.record_poll(CLUSTER, "ok", None)
        grant = {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "breakglass-admin",
                 "role_kind": "ClusterRole", "role_name": "cluster-admin"}
        store.replace_user_bindings(CLUSTER, [{**grant, "user_name": "breakglass", "is_platform": 0}], now)
        store.replace_bindings(CLUSTER, [{**grant, "group_name": "breakglass", "subject_kind": "User",
                                          "exception": "break-glass account, INC-1"}], now)
        store.replace_operator_configs(CLUSTER, None, now)
        d = tmp_path / "s"; d.mkdir(); path = write_snapshot(store, d)
        store.close()
        with Snapshot(path) as snap:
            cs = _build(snap, "compliance-snapshot")
        figures = {k: v for s in cs.sections for b in s.blocks if getattr(b, "items", None) for k, v in b.items}
        assert (figures["Direct user grants"], figures["Privileged direct grants"]) == (0, 1)
        assert figures["Acknowledged direct grants (excluded from Direct user grants)"] == 1
```

### Block 52 — local-development/tests/test_metrics.py: T503-12

<!-- block: local-development/tests/test_metrics.py | edit -->

Old text:

```python


class TestResilience:
```

New text:

```python


class TestAcknowledgedGrantsMoveCountsNeverNames:
    """#503: /metrics is unauthenticated by decision, so the acknowledged grants reach it only as a count:
    `gsd_alerts_total{kind="direct_user_binding"}` counts ALERTS — one per cluster with any grant still to
    review, whatever its total — and no user or binding name appears, acknowledged or not."""

    def test_t503_12_the_alert_series_counts_alerts_and_names_nobody(self):
        store = Store(":memory:")
        names = {"c1": [("jdoe-edit", "jdoe", None), ("bind-acct-crb", "ocp-oauth-bind-serviceid", "group-sync-operator-helm")],
                 "c2": [("vendor-view", "vendor-support", "team-x")]}
        for cluster, grants in names.items():
            store.upsert_cluster(cluster, "https://x", True)
            store.record_poll(cluster, "ok", None)
            store.replace_user_bindings(cluster, [
                {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": b, "role_kind": "ClusterRole",
                 "role_name": "edit", "user_name": u, "is_platform": 0} for b, u, _ in grants], _iso(datetime.now(UTC)))
            store.replace_bindings(cluster, [
                {"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": b, "role_kind": "ClusterRole",
                 "role_name": "edit", "group_name": u, "subject_kind": "User", "managed_source": label}
                for b, u, label in grants], _iso(datetime.now(UTC)))
        text = generate_latest(build_registry(store, GRACE)).decode()
        store.close()
        alerts = {k: v for k, v in series(text, "gsd_alerts_total").items() if 'kind="direct_user_binding"' in k}
        assert alerts == {'gsd_alerts_total{cluster="c1",kind="direct_user_binding",severity="warning"}': 1.0}, alerts
        for needle in ("jdoe", "ocp-oauth-bind-serviceid", "vendor-support", "jdoe-edit", "bind-acct-crb", "vendor-view",
                       "group-sync-operator-helm", "team-x"):
            assert needle not in text, needle


class TestResilience:
```

### Block 53 — local-development/tests/test_platform_classification_marker.py: `REVIEW_SITE`, the review rule's two names (T503-13)

<!-- block: local-development/tests/test_platform_classification_marker.py | edit -->

Old text:

```python
GSD = ROOT / "local-development" / "gsd"
```

New text:

```python
GSD = ROOT / "local-development" / "gsd"
# #503's review rule, by its two names (gsd/store.py Store._USER_ACKNOWLEDGED, Store._USER_TO_REVIEW): every
# query that reads one reads the stored platform flag too, so it carries the marker like the flag's own sites.
REVIEW_SITE = re.compile(r"\b_USER_(ACKNOWLEDGED|TO_REVIEW)\b")
```

### Block 54 — local-development/tests/test_platform_classification_marker.py: the site test reads both patterns

<!-- block: local-development/tests/test_platform_classification_marker.py | edit -->

Old text:

```python
        if line.lstrip().startswith(("import ", "from ")) or not SITE.search(line):
```

New text:

```python
        if line.lstrip().startswith(("import ", "from ")) or not (SITE.search(line) or REVIEW_SITE.search(line)):
```

### Block 55 — local-development/tests/test_platform_classification_marker.py: the pattern's own test

<!-- block: local-development/tests/test_platform_classification_marker.py | edit -->

Old text:

```python
    assert bool(SITE.search(line)) is is_site, line
```

New text:

```python
    assert bool(SITE.search(line)) is is_site, line


@pytest.mark.parametrize("line, is_site", [
    ('                    WHERE cluster_id=? AND """ + self._USER_TO_REVIEW + """', True),
    ('            sql += " AND NOT " + self._USER_ACKNOWLEDGED', True),
    ('                        CASE WHEN """ + Store._USER_ACKNOWLEDGED + """ THEN 1 ELSE 0 END AS acknowledged', True),
    ('    _USER_PROVENANCE = """', False),
    ("    # A DIRECT USER GRANT THE OPERATOR ACKNOWLEDGED (#503). The operator's rule (#353) is the unmanaged", False),
])
def test_the_review_rule_pattern_sees_its_two_names_but_not_prose(line: str, is_site: bool) -> None:
    """#503 (T503-13): a new read of the review rule without the marker fails the site test above."""
    assert bool(REVIEW_SITE.search(line)) is is_site, line
```

### Block 56 — local-development/tests/test_ui.py: T503-10, and the namespace page's badge

<!-- block: local-development/tests/test_ui.py | edit -->

Old text:

```python


class TestUsagePage:
```

New text:

```python


class TestAcknowledgedGrantsDisclosure:
    """#503 (T503-10): the grants the operator acknowledged on their binding are counted under the worklist and
    reachable behind a disclosure, each with its label value or its exception text. The served rig has none,
    so they are injected into the payload on the 60 s poll's own path; the second poll changes the payload, so
    the page really repaints, and the open state must survive it."""

    ROWS = [{"binding_kind": "ClusterRoleBinding", "binding_namespace": "", "binding_name": "group-sync-dashboard-cluster-poller",
             "role_kind": "ClusterRole", "role_name": "group-sync-dashboard-cluster-poller", "user_name": "ocp-oauth-bind-serviceid",
             "managed_source": "group-sync-operator-helm", "exception": None},
            {"binding_kind": "RoleBinding", "binding_namespace": "payments-sandbox", "binding_name": "vendor-support-view",
             "role_kind": "ClusterRole", "role_name": "view", "user_name": "vendor-support", "managed_source": None,
             "exception": "vendor read-only access for the payments integration, reviewed quarterly"}]

    def _open(self, dash, rows):
        import json as _json
        dash.click('button.tab:text-is("Namespace audit")')
        dash.wait_for_selector("h2:text-is('Namespace audit')")
        current = {"rows": rows}

        def inject(route):
            body = route.fetch().json()
            body.update(acknowledged=len(current["rows"]), acknowledged_bindings=current["rows"], acknowledged_truncated=False)
            route.fulfill(status=200, content_type="application/json", body=_json.dumps(body))

        dash.route("**/api/clusters/*/user-bindings*", inject)
        dash.evaluate("() => refresh({auto: true})")
        dash.wait_for_selector("#du-acknowledged")
        return current

    def _text(self, dash, selector):
        return " ".join(dash.locator(selector).inner_text().split())

    def test_the_count_renders_closed_and_opens_to_each_grant_with_what_acknowledged_it(self, dash):
        self._open(dash, self.ROWS)
        head = self._text(dash, "#du-acknowledged .section-head")
        assert head.startswith("2 grants acknowledged by the operator — counted here and not in the worklist above or the alert")
        assert head.endswith("Show the 2"), head
        assert dash.locator("#ack-rows").is_hidden()
        dash.click("[data-ns-ack]")
        assert dash.locator("[data-ns-ack]").get_attribute("aria-expanded") == "true"
        rows = [" ".join(t.split()) for t in dash.locator("#ack-rows tbody tr").all_inner_texts()]
        assert rows == [
            "ocp-oauth-bind-serviceid group-sync-dashboard-cluster-poller ClusterRole cluster-wide "
            "group-sync-dashboard-cluster-poller label config-source: group-sync-operator-helm",
            "vendor-support view ClusterRole payments-sandbox vendor-support-view exception "
            "“vendor read-only access for the payments integration, reviewed quarterly”"], rows

    def test_the_open_state_survives_the_repaint(self, dash):
        current = self._open(dash, self.ROWS[:1])
        dash.click("[data-ns-ack]")
        current["rows"] = self.ROWS            # the next poll brings a second row: a real repaint
        dash.evaluate("() => refresh({auto: true})")
        dash.wait_for_function("() => document.querySelectorAll('#ack-rows tbody tr').length === 2")
        assert dash.locator("[data-ns-ack]").get_attribute("aria-expanded") == "true"
        assert dash.locator("#ack-rows").is_visible()

    def test_nothing_renders_without_an_acknowledged_grant_or_at_the_self_tier(self, dash):
        dash.click('button.tab:text-is("Namespace audit")')
        dash.wait_for_selector("h2:text-is('Namespace audit')")
        assert dash.locator("#du-acknowledged").count() == 0, "the seeded rig has none"
        dash.evaluate("""() => { Object.assign(data.userBindings, {acknowledged: null, acknowledged_bindings: null,
            acknowledged_truncated: null}); render(); }""")
        assert dash.locator("#du-acknowledged").count() == 0

    def test_the_namespace_page_lists_an_acknowledged_grant_marked_and_leaves_it_out_of_its_count(self, dash):
        """The namespace detail shows an acknowledged grant the way it shows a platform row: listed, badged, and
        out of the Direct grants count — the index's column, the envelope and the worklist count the same."""
        dash.click('button.tab:text-is("Namespace audit")')
        dash.locator("tr[data-ns='prod-ns'] button.drill").click()
        dash.wait_for_selector("#back")
        dash.evaluate("() => { data.ns.direct_grants.forEach((x) => { x.acknowledged = 1; }); render(); }")
        head = " ".join(dash.locator("h2", has_text="Direct grants").inner_text().split())
        assert head == "Direct grants · 0 · 1 acknowledged", head
        assert dash.locator(".kpi", has_text="Direct grants").locator(".value").inner_text().strip() == "0"
        assert dash.locator("tr[data-user] .badge", has_text="acknowledged").count() == 1

    @pytest.mark.parametrize("width", [375, 768, 1280])
    @pytest.mark.parametrize("theme", ["light", "dark"])
    def test_no_horizontal_overflow_open_or_closed(self, dash, width, theme):
        dash.set_viewport_size({"width": width, "height": 900})
        self._open(dash, self.ROWS)
        dash.evaluate("(theme) => document.documentElement.setAttribute('data-theme', theme)", theme)
        for _ in range(2):
            overflow = dash.evaluate("() => document.documentElement.scrollWidth - document.documentElement.clientWidth")
            assert overflow <= 0, f"the page scrolls {overflow}px sideways at {width}px ({theme})"
            dash.click("[data-ns-ack]")


class TestUsagePage:
```

### Block 57 — docs/ACCESS_CONTROL.md: §4's `/user-bindings` row

<!-- block: docs/ACCESS_CONTROL.md | edit -->

Old text:

```text
| GET | `/api/clusters/{cluster_id}/user-bindings` | always | viewer_scope | 403 | self | all | self | all | at self, their own grants |
```

New text:

```text
| GET | `/api/clusters/{cluster_id}/user-bindings` | always | viewer_scope | 403 | self | all | self | all | at self, their own grants, acknowledged or not, with the acknowledged count and list `null`; at the wide tier, the grants the operator acknowledged are counted and listed apart (#503) |
```

### Block 58 — local-development/API.md: the example payload

<!-- block: local-development/API.md | edit -->

Old text:

```text
  "bindings": []
```

New text:

```text
  "bindings": [],
  "acknowledged": 2,
  "acknowledged_bindings": [
    {"binding_kind": "ClusterRoleBinding", "binding_namespace": "",
     "binding_name": "group-sync-dashboard-cluster-poller", "role_kind": "ClusterRole",
     "role_name": "group-sync-dashboard-cluster-poller", "user_name": "ocp-oauth-bind-serviceid",
     "managed_source": "group-sync-operator-helm", "exception": null}
  ],
  "acknowledged_truncated": true
```

### Block 59 — local-development/API.md: `limit` pages both lists

<!-- block: local-development/API.md | edit -->

Old text:

```text
| `limit` | `200` (max 5000) | applies to `bindings` only |
```

New text:

```text
| `limit` | `200` (max 5000) | applies to `bindings` and `acknowledged_bindings` |
```

### Block 60 — local-development/API.md: the acknowledged grants

<!-- block: local-development/API.md | edit -->

Old text:

```text
### `GET /api/clusters/{cluster_id}/operator-configs`
```

New text:

```text
**A grant the operator acknowledged is counted, not listed as one to migrate (#503).** Its binding carries the
`rbac.ocp.io/config-source` label (any value) or the `rbac.ocp.io/unmanaged-exception` annotation, the rule the
unmanaged finding already keeps. It leaves `bindings`, `total`, `by_namespace` and the direct-user alert, and
`acknowledged` counts it beside `excluded_platform`. `acknowledged_bindings` lists each one, worst first, with
`managed_source` (the label's value) or `exception` (the annotation's text), or both. It is paged by the same
`limit` and `offset` as `bindings`, with `acknowledged_truncated` set the same way. It is never narrowed by
`namespace`: like `by_namespace`, it is the whole cluster's. A platform identity's grant stays in
`excluded_platform`, whatever its binding carries. At the self tier the three are `null`, and `bindings` keeps
the viewer's own grants, acknowledged or not: an acknowledged grant is still access the viewer holds. Each row of
`bindings` carries `acknowledged` (`0` or `1`); at the wide tier it is always `0`. The provenance is the one the
binding refresh stores for the unmanaged finding, so it takes effect at the next refresh.

### `GET /api/clusters/{cluster_id}/operator-configs`
```

### Block 61 — charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md: both reserved values

<!-- block: charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md | edit -->

Old text:

```text
- **Do not use `group-sync-dashboard`.** That value is reserved for this chart's own RBAC, which carries it by default
  (`templates/_helpers.tpl`, `gsd.rbacLabels`). It silences the chart's bindings, but it is never taken as evidence
  that a policy system is in use (#354).
```

New text:

```text
- **Do not use `group-sync-dashboard` or `group-sync-operator-helm`.** These values are reserved for two charts' own
  RBAC: this chart's (`templates/_helpers.tpl`, `gsd.rbacLabels`) and the group-sync-operator chart's (its
  `group-sync-operator-helm.rbacLabels`, from chart 0.14.1). Each chart sets its own name on every RBAC object it
  renders, with no values key for it. They silence those charts' bindings, but neither is ever taken as
  evidence that a policy system is in use (#354, #503). An umbrella chart that installs either under a
  dependency `alias` renders the alias instead, which counts as a policy system's value.
```

### Block 62 — charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md: the Group gate names both values

<!-- block: charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md | edit -->

Old text:

```text
  `group-sync-dashboard`. ServiceAccount and User grants have no such condition.
```

New text:

```text
  `group-sync-dashboard` and `group-sync-operator-helm`, the two charts' own (#503). ServiceAccount and User grants
  have no such condition.
```

### Block 63 — charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md: "When it takes effect" covers the direct-user view

<!-- block: charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md | edit -->

Old text:

```text
moves out of **Unmanaged**. On the Access granted page it is counted as granted. A platform identity is counted as
```

New text:

```text
moves out of **Unmanaged**, and a grant it gives a user directly moves out of the Namespace audit worklist and the
direct-user alert into the acknowledged count (#503). On the Access granted page it is counted as granted. A platform identity is counted as
```

### Block 64 — charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md: the direct-user view follows the same rule

<!-- block: charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md | edit -->

Old text:

```text
## Where the rule is written
```

New text:

```text
## The direct-user view follows the same rule

A grant that names a user directly is also listed on the **Namespace audit** tab, as one to migrate to a group,
and raises the direct-user alert. The label and the annotation above acknowledge it there too (#503). It
leaves the worklist, its counts, the namespace index's counts and the alert at the next binding refresh. It is
counted as acknowledged beside the platform identities, and listed under the worklist with its label value or
its exception text. A user's own acknowledged grants stay on their own view, because they are still access that
user holds. A platform user stays a platform user, whatever its binding carries.

## Where the rule is written
```

### Block 65 — docs/CHANGELOG.md: the bullet, first under Unreleased (re-derived after SPEC_G2, orchestrator's note 1)

<!-- block: docs/CHANGELOG.md | edit -->

Old text:

```text
## Unreleased

```

New text:

```text
## Unreleased

- **A direct user grant the operator acknowledged leaves the worklist and the alert, and is counted (#503, Epic G
  #387, `docs/specs/SPEC_G3_acknowledged_direct_grants.md`; application 3.3.0, chart 0.66.1).** A grant that names
  a user directly, on a binding carrying the `rbac.ocp.io/config-source` label (any value) or the
  `rbac.ocp.io/unmanaged-exception` annotation, is acknowledged: the rule the unmanaged finding already keeps. It
  leaves the Namespace audit worklist and its tiles, the namespace index's counts, the namespace page's count and
  the direct-user alert's total, the RBAC findings report's direct-user table and the compliance snapshot's
  "Direct user grants".
  `/user-bindings` counts it in `acknowledged`, beside `excluded_platform`, and lists it in `acknowledged_bindings`
  with its label value or its exception text; the tab shows the count and a disclosure listing each one. A platform
  user stays a platform user. A reader's own acknowledged grants stay on their self view and Home, and the access
  reports still list every grant. The provenance is read from what the binding refresh already stores, so there is
  no migration. `group-sync-operator-helm`, the group-sync-operator chart's fixed value, is now a chart's provenance
  in the Group arm's gate, as `group-sync-dashboard` is. `gsd_alerts_total{kind="direct_user_binding"}` still counts
  alerts, not grants. No new permission.

```

### Block 66 — charts/group-sync-dashboard/Chart.yaml: the chart PATCH and its history line (re-derived after SPEC_G2)

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

Old text:

```yaml
version: 0.66.0
```

New text:

```yaml
# CHART 0.66.1 (2026-10-03), PATCH: docs/UNMANAGED_GRANT_EXCLUSIONS.md names group-sync-operator-helm
# beside group-sync-dashboard and says the direct-user view follows the label; appVersion moves to
# application 3.3.0 (below); #503.
version: 0.66.1
```

### Block 67 — charts/group-sync-dashboard/Chart.yaml: `appVersion` and its history line (re-derived after SPEC_G2)

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

Old text:

```yaml
appVersion: "3.2.0"
```

New text:

```yaml
# 3.3.0 (2026-10-03). A direct user grant whose binding carries the operator's config-source label or exception annotation leaves the Namespace audit worklist, its counts and the direct-user alert, and is counted and listed as acknowledged; group-sync-operator-helm is a chart's provenance in the Group gate (#503). MINOR.
appVersion: "3.3.0"
```

### Block 68 — local-development/pyproject.toml: the application MINOR (re-derived after SPEC_G2)

<!-- block: local-development/pyproject.toml | edit -->

Old text:

```toml
version = "3.2.0"
```

New text:

```toml
version = "3.3.0"
```

### Block 69 — local-development/gsd/__init__.py: the application MINOR (re-derived after SPEC_G2)

<!-- block: local-development/gsd/__init__.py | edit -->

Old text:

```python
__version__ = "3.2.0"
```

New text:

```python
__version__ = "3.3.0"
```
