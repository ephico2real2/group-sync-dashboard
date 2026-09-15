# Session change log — group-sync-dashboard, 2026-09-14 evening → 2026-09-15

Continues `2026-09-14_reporting-extension-and-b3.md` (which closed with B3 developed but its review
in flight). This session finished the B3 review, cut the **0.20.0** application release, applied the
mock-cluster (#118) review, handled a real auditor-RBAC incident and its fix, settled the per-cluster
connection-auth design, and linked the Cilium PoC's running-test captures upstream. Each line names
the commit, PR or measurement behind it; nothing is recalled from memory alone. Times are git author
times (America/Chicago).

Outcome in one line: **application 0.20.0 / chart 0.28.0 on main — Extension B complete (the B3 GUI
released), the mock OpenShift API landed, and the auditor gate defaulted on after it was accidentally
dropped; the PR board is clear.**

| | Start of the session | End |
|---|---|---|
| Application / chart on main | 0.19.0 / 0.25.0 | **0.20.0 / 0.28.0** |
| Extension B | B1/B2 shipped, B3 GUI mid-review | complete — B3 released (#117) |
| Mock OpenShift API (#116) | built, unreviewed (PR #118) | reviewed, fixed, merged |
| Reporting auditors | opt-in (default off) | ON by default (#121), incident-driven |
| Open PRs | #117, #118, #105, #120 (+ designs) | none |

---

## Part 1 — B3, the mnemonic multi-select GUI (#117 → app 0.20.0)

- **The two-reviewer pass, both findings converged.** Codex `gpt-5.6-sol`/xhigh + Cursor
  `grok-4.6-high-fast` on the namespace-access form. **C1**: a corrupt snapshot 500'd the whole Reports
  tab; both reviewers proposed `import sqlite3` in `server.py`, which `test_storage_seam` proved breaks the
  enforced storage seam — fixed instead at the backend boundary (`Snapshot.__init__` translates
  `sqlite3.Error` → `SnapshotError`, `server.py` unchanged). **C4**: a cluster switch left a stale mnemonic
  that posted invisibly against the new cluster — cleared in `applyPosition`. **C5**: the test rewritten to
  capture the real POST and switch via `navigate()`. Each fix has a fail-before/pass-after test.
- **Second pass found a real gap (Codex D1).** The `__init__` wrap closed open-time corruption but not a
  TABLE read that fails after a clean open — proven `query_time_api_status=500`. Closed by moving the whole
  gather behind a backend `Snapshot.namespace_selectors()` (still no sqlite3 in `server.py`), locked by a
  parametrised test. Record: `docs/REVIEW_ns_selector_gui.md`.
- **Released application 0.20.0 — chart 0.26.0.** `pyproject.toml`, `gsd/__init__.py` `__version__` and
  `Chart.yaml appVersion` all advanced together (held equal by `tests/test_chart_versions.py`); this caught
  up the app version to include B1+B2 (which had shipped under chart bumps 0.22–0.24 while appVersion stayed
  0.19.0). Merged **#117** (`557ffb3`). Full suite: 2914 non-UI + 274 UI green.
- **Validated live against the mock cluster on CRC** (see Part 2): the 0.20.0 image polling a mock cluster
  over real TLS, its `team` namespace labels captured and surfaced as the mnemonic multi-select
  (`acme`, `platform`), a report generated to done. An all-features e2e walk of the deployed 0.20.0 app
  passed **75/75 steps, 11/11 report integrity**.

## Part 2 — the mock OpenShift API (#116 → #118)

- **Built earlier by a 6-agent workflow** (recorded in the prior log); this session ran its **two-reviewer
  pass** and applied the findings. Codex + Cursor on `local-development/mock-app/`.
- **Applied (converged or Codex-proven):** the CI blocker — `mock-cluster.yml` had literal
  `@<...-sha>` placeholders so the branch's own `test_workflow_pins.py` was RED (pinned to the repo's
  actual action SHAs, added `workflow_dispatch`, and `poller.py`/`store.py` to the paths); the SAR
  authorizer ignored `kind: ServiceAccount` subjects (a CRB to an SA denied the canonical
  `system:serviceaccount:…` user); every non-core List emitted `apiVersion: "unknown"`; two vacuous poll
  tests (one asserted only `"ok"`, one had zero assertions) rewritten to assert the persisted rows; every
  handle shared `GSD_MOCK_TOKEN` (two servers clobbered the token); the leaf cert was valid only 1h/1d;
  Cursor's machine-path `sys.path` fallback in conftest removed. Deferred (own follow-up): the
  `/_mock/reload` 422 + fail-loud fixture validation, an endpoint-parity guard, the bind-mount chmod.
  Record: `docs/REVIEW_mock_cluster.md`. Mock-app suite: 55 tests green. Merged **#118** (`0f64098`).

## Part 3 — the auditor-RBAC incident, and the on-by-default fix (#121, #122, #123)

- **The bug, from data.** After the mock-cluster deploy (`release-crc.sh -f environments/crc.yaml`), the
  operator found lateef.o — a member of `app-ocp-rbac-groupsync-ns-auditor` — could no longer see reports.
  Diagnosed: the auditor Group and his membership were intact, but the auditor ClusterRole +
  ClusterRoleBinding were GONE, and `rbacAuditors` was absent from the release values. Cause: `rbacAuditors`
  was opt-in (default off) and `crc.yaml` never enabled it, so a `helm upgrade -f` reset it away — the exact
  reset-trap `release-crc.sh`'s header warns about.
- **Restored at runtime** (helm rev 231/232) and SAR-verified: as an auditor-group member he `can`
  `list clusterrolebindings` and `list groups` — the wide-tier signals; a non-member gets `no`.
- **The root-cause fix, #121 (chart 0.27.0):** `rbacAuditors.enabled` now defaults to `true`, per the
  chart's on-by-default rule, so an environment file must DISABLE it explicitly rather than accidentally
  drop it. Four tests that assumed default-off fixed. Merged.
- **#122 (crc, authLogLevel off):** the CRC env forced `authLogLevel.manage: true`, whose Job (a
  post-upgrade HOOK for the pod-log login source) ran on every upgrade and, on the CPU-saturated node,
  couldn't schedule and HUNG the whole upgrade. The lab uses `loginCapture.source: audit-log`, which needs
  no elevated verbosity, and the operator CR is at Normal — so management is off. Merged.
- **The policy finding, owned.** Codex's #121 review REFUTED "safe for every install" on policy: defaulting
  on GRANTS the named group cluster-wide reads AND the wide report tier on a `0.26 → 0.27` upgrade wherever
  that group exists — the settled record recommends opt-in. **Operator decision: keep default-on**;
  documented with a CHANGELOG UPGRADE NOTE and the chart README corrected. One real test gap (Codex C2 — the
  `groups_granted` check scanned the always-on auditor role) fixed. **#123 (chart 0.28.0).** Record:
  `docs/REVIEW_rbacauditors_default_and_authloglevel.md`.

## Part 4 — per-cluster connection-auth design (#119 / #120 / #124)

- The #117 test exposed that the chart mounts a fixed volume set with **no per-cluster bearer-token mount**
  (the mock cluster needed a hand `oc set volumes` patch). `docs/DESIGN_per_cluster_connection_auth.md`
  proposes a per-cluster `credentials` stanza the chart turns into deterministic mounts + a computed
  clusters.yaml, over three modes (inCluster SA, remote token+CA, remote LDAP bind — Phase 2). Issue **#119**,
  design PR **#120** (merged). Decisions then settled with the operator and folded into the doc (**#124**):
  operator-chosen cluster names (everything derives from `<name>`), values-only override surface,
  `inCluster` auto-default for the first entry, and P1 migrating the default `crc-local` entry to
  `inCluster: true`.

## Part 5 — Cilium PoC: linking the running-test captures upstream (external repos)

- The upstream maintainer began merging the fork PRs. Added the `ci-captures` running-test branch link
  (a fresh two-cluster Cilium 1.20.1 ClusterMesh on kind per CI run, with Grafana/Hubble/cf2cnp screenshots)
  to both upstream PRs — onzack/hubble-observer#13 and onzack/cf2cnp#3 — and to both fork `develop` READMEs
  (ephico2real2/hubble-observer, ephico2real2/cf2cnp), on `develop` rather than the actively-merging feat
  branches so the links carry into the next merge without disturbing the current one.

## Part 6 — reporting-output design merged (#105)

- The parked round-1 design for the reporting-output features (CSV, change diffs, delivery, preview counts)
  merged, resolving a `REVIEW_ARTIFACTS` conflict in `test_docs_citations.py` by keeping both sides' review
  records.

---

**End state:** main at chart 0.28.0 / app 0.20.0, zero open PRs, CRC running 0.20.0 with the auditor RBAC
and the mock cluster intact. quay.io was read-only for the whole session, so every image was a local CRC
build; a formal publish waits for quay to be writable.
