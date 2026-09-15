# Session change log — group-sync-dashboard, 2026-09-14 (reporting extension + B3 GUI)

Continues `2026-09-11_c3-d2-release.md` (merged in #95). That file closed at the C3/D2 release and the
session-tooling commit; everything below is the 2026-09-14 work that followed it — the reporting
**extension** programme (auditor groups + namespace-mnemonic selection), the cluster-retirement fix, and
the B3 GUI now in final review. Each line names the commit, PR, or committed artifact behind it; nothing
here is recalled from memory alone. Times are git author times (America/Chicago).

Outcome in one line: **the reporting extension shipped to `main` through A → B1 → B2, the auditor group
was defaulted and its LDAP-takeover behaviour validated and documented, cluster retirement (#96) landed,
and B3 (the mnemonic GUI) is on its second review pass — chart 0.21.0 → 0.25.0, appVersion still 0.19.0
(quay.io read-only all session, so every build is local).**

| | Start of 2026-09-14 | Now |
|---|---|---|
| Chart / app on main | 0.21.0 / 0.19.0 | **0.25.0** / 0.19.0 |
| Reporting extension | designed, unmerged | A (#110), B1 (#111), B2 (#112) merged; B3 (#117) in review |
| Auditor group | not in values | defaulted in `values.yaml`, createLocal collision guarded (#113) |
| Cluster retirement | a removed cluster lingered as `ok` (#96, #97) | retired on the fly, RBAC intact (#115) |
| Open PRs | — | #117 (B3 GUI), #118 (mock-cluster), #105 (reporting-output design) |

---

## Part 1 — the extension design and its round-1 review (#99)

- `docs/DESIGN_reporting_auditors_and_ns_selector.md` — the extension framed as two additions over the
  existing report gate: an opt-in least-privilege **auditor group**, and **namespace selection by the
  estate's grouping label** with a bounded, extensible metadata capture. Round-1 adversarial pass
  (`docs/REVIEW_reporting_ext_design.md`): both reviewers, every load-bearing claim re-checked against the
  code; six of eight snippet claims refuted and folded (ValidationError not ReportError, MAX_NAMESPACES not
  NS_CAP, a hashed ClusterRoleBinding name with no templated `users:`, the child table inside the existing
  `replace_namespaces` transaction, per-cluster catalogue values, the multi-select serialised as an array).
  Issue decomposition recorded: A #100, B1 #101, B2 #102 (needs #101), B3 #103 (needs #102). Merged **#99**.
- A parallel reporting-**output** backlog + design (CSV, change diffs, delivery, preview counts) had its own
  round-1 pass (its review record rides PR **#105**, still open); cut as #106–#109.

## Part 2 — A: the auditor group (#100 → #110), commit `84cd671` + reviews

- `charts/group-sync-dashboard/templates/rbac-auditors.yaml` — an opt-in group bound to a read-only
  ClusterRole over the report gate's surface (list, not update). Two-reviewer pass on the real chart
  (`docs/REVIEW_rbacAuditors_impl.md`): fixes applied — validate `enabled`/`createClusterRole` **types**
  before Helm truthiness (a string `"false"` would otherwise render the role), fail `enabled=true` with no
  groups, the ClusterRoleBinding name hashes group **and** role so switching `existingClusterRole` changes
  the immutable `roleRef` via a new binding rather than an upgrade-breaking patch, duplicate group names
  rejected. Chart 0.22.0. Merged **#110**.

## Part 3 — B1: bounded namespace-metadata capture (#101 → #111), commit `4d6fa59`

- The poller captures a bounded per-namespace metadata set into a child table
  (`cluster_namespace_label`), off by default behind two guards, added in the same `replace_namespaces`
  transaction so a report never reads a namespace whose labels were deleted-but-not-reinserted (migration
  12 → schema v11 parity). Two-reviewer pass (`docs/REVIEW_ns_metadata_capture_impl.md`): Codex ran pytest,
  the migrations, helm; confirmed C1–C5 (bounded capture, atomic child write, poller forwarding,
  off-by-default, comma/unicode/4KiB values, the seam and chart-version tests). No defect. Merged **#111**.

## Part 4 — B2: select namespaces by the mnemonic label (#102 → #112), commit `f7cc267`

- The namespace-access report gains a `mnemonics` parameter (an XOR alternative to explicit names) that
  expands to namespace names via the captured label. Three review findings applied (`docs/REVIEW_*` for the
  B2 selector), second pass recorded no new finding (`a9c7056`). Merged **#112** (chart 0.24.0).

## Part 5 — the auditor group defaulted + the LDAP-takeover validation (#113), commits `f7ac65a`, `6f654a0`

- The operator asked what happens when a chart-local auditor group collides with an LDAP-synced group of
  the same name. Validated end-to-end against the LDAP GroupSync operator and documented in
  `docs/FINDINGS_auditor_group_ldap_sync_interaction.md`: the three-marker ownership chain
  (`openshift.io/ldap.host` label — a hard guard whose mismatch errors the whole CR sync;
  `openshift.io/ldap.url` annotation; the `sync-provider` label), the **denial-of-sync** a same-named
  unmarked local group causes for the whole family, and **adoption** (members overwritten from LDAP, Helm
  labels preserved) once fully stamped — proven with a bogus member.
- `docs/TROUBLESHOOTING_auditor_groups.md` — the step-by-step and the metadata added.
- `charts/.../templates/rbac-auditors.yaml` — a **createLocal collision guard**: on a real install (Helm
  `lookup` returns `{}` in template/dry-run, so the guard fires only on a real install) it refuses to
  create a local group that already exists unless this release fully owns it
  (`meta.helm.sh/release-name` + `-namespace` + `managed-by: Helm`), and tells the operator to turn
  createLocal off for existing groups. `rbacAuditors.groups` defaults to the auditor group
  (`createLocal` omitted = bind-only). Two-reviewer pass: `docs/REVIEW_auditor_createlocal_guard.md`.
  Merged **#113** (chart 0.25.0). Deployed to CRC; the auditor group synced from LDAP with `managed-by`
  empty (a synced group, not a Helm-owned one), confirming bind-only.

## Part 6 — #96: retire clusters removed from the configuration (#115), commits `5e1ac28`…`0797b28`

- A cluster dropped from `clusters:` (or `enabled: false`) no longer lingers in the UI as `ok` with frozen
  data and stale alerts. `store.retire_absent_clusters` sets the row `enabled = 0` (history kept); the
  poller reconciles at the start of every cycle; `/api/clusters`, `/api/whoami`, `/api/alerts`, `/metrics`
  and `/api/clusters/{id}/…` (404s like an unknown id) skip it; with no served cluster, `/api/alerts` fails
  closed to `scope: self`. Declared in the `StorageBackend` Protocol (the storage-seam test). Two-reviewer
  pass: `docs/REVIEW_retire_clusters.md`. Merged **#115**; verified live on CRC (prod-east retired,
  `enabled=0`, the poller logged "retired 1 cluster(s)"). The parked reporter/auditor tier-lockdown idea
  was filed as **#114**.

## Part 7 — evidence: two end-to-end walks (#98)

- The reports/ folder gained two 2026-09-14 walk directories (e2e-walk and e2e-walk-nonadmin) —
  Playwright walks of 0.19.0 on CRC, administrator and non-administrator (the
  non-admin captured as `lateef.o`, added to the auditor group; SARs proved the auditor group is the sole
  deciding factor for the wide report view). Findings from the walk became **#96** (lingering removed
  cluster) and **#97** (report pod preempted on the saturated node). Merged **#98**.

## Part 8 — the mock-cluster (#116 → #118, open), commit `bb5f984`

- A new local-development/mock-app/ — a portable, cert-backed fake OpenShift API (FastAPI, ~1900 LOC, 42
  tests that exercise the real `gsd.poller`/`gsd.kube` over real TLS), so local and CI testing need neither
  CRC nor a live cluster. Its design doc and CI job ride PR **#118** (open). Built by a 6-agent background
  workflow — still owes its own two-reviewer pass before merge.

## Part 9 — B3: the mnemonic multi-select GUI (#103 → #117, open), commits `b67619b`, `091d6c1`

- `f97…b67619b` — the report catalogue returns per-cluster `namespaceSelectors`; the namespace-access form
  renders a `<select multiple>` of the captured values ahead of the advanced explicit-names field;
  `readParamEl` serialises it as an array.
- `091d6c1` — the two-reviewer pass applied (`docs/REVIEW_ns_selector_gui.md`). **C1**: a corrupt snapshot
  500'd the whole Reports tab; both reviewers proposed `import sqlite3` in `server.py`, which the storage-
  seam test proved breaks the seam — fixed instead in the backend (`Snapshot.__init__` translates
  `sqlite3.Error` → `SnapshotError`). **C4**: a cluster switch left a stale mnemonic that posted invisibly
  against the new cluster — cleared in `applyPosition`. **C5**: the test rewritten to capture the real POST
  and switch via `navigate()`. Each fix has a proven fail-before/pass-after test. CI green on `091d6c1`.
- **Second pass** (same commit's head): Codex proved a query-time gap the first fix missed — a copy that
  opens cleanly then fails a table read still 500'd — closed by moving the whole gather behind
  `Snapshot.namespace_selectors` (still no `sqlite3` in `server.py`), locked by a parametrised test.
  Cursor confirmed the rest; the `generateReport` belt and a boot-code rewrite were rejected as complexity
  for non-bugs. Full non-UI 2912 + UI 274 green. PR **#117** ready for the operator once the post-second-pass
  commit is pushed and CI re-runs.
