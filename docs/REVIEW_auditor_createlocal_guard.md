# Review — PR #113, the auditor `createLocal` collision guard + default group (chart 0.25.0)

Adversarial pass on the real code. 2026-09-14. Codex (gpt-5.6-sol, xhigh, shell — ran `helm
template`/`helm lint` and pytest offline; `lookup` needs a live cluster so guard-firing was traced) and
Cursor (Grok 4.6 high fast, ask mode — its allowlist refused the shell, so it traced from source). The
guard fires only on a real install/upgrade, so the orchestrator verified it live on CRC.

## Verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 the guard fires only on a real collision | REFUTED (ownership by release-name alone) | CONFIRMED a/b/c, but **N2**: same finding | **F1 accepted** |
| C2 the guard doesn't break `helm template`/CI | CONFIRMED (render + lint) | PLAUSIBLE (no shell) | — |
| C3 nil-safety + message correctness | PLAUSIBLE (nil-safe for valid metadata) | CONFIRMED | — |
| C4 the values default preserves the invariants | CONFIRMED (default off, empty-list rejection) | CONFIRMED | — |
| C5 the two changed tests measure what they claim | REFUTED (default-group test is substring-only) | CONFIRMED | **F2 accepted** |
| C6 docs accurate + citations resolve | CONFIRMED (FINDINGS/TROUBLESHOOTING tables agree) | REFUTED (**chart README drift**) | **F3 accepted** |

## Findings

### F1 (both reviewers) — the guard's ownership check was incomplete

**Finding.** The guard identified "owned by this release" by `meta.helm.sh/release-name` alone. Helm
releases are namespace-scoped and Groups are cluster-scoped, so two `helm install group-sync-dashboard`
in different namespaces (or any non-Helm object with a matching name) would pass the check as "owned" —
a false negative that lets the very collision the guard exists to catch through to Helm's opaque
ownership error. Codex's contract probe found `missing=['release namespace marker', 'current namespace',
'Helm managed-by marker']`.

**Re-check.** Confirmed at `rbac-auditors.yaml:67-68` (the old check). Helm's own ownership is
(`release-name`, `release-namespace`) plus the `app.kubernetes.io/managed-by: Helm` label. A group is
"ours" only when all three match; otherwise (a different namespace, a different release, or an
operator-owned/hand-made group with none of them) it is foreign and the guard must fire.

**Decision — accepted.** Applied Codex's verified block: derive `$ownerName`, `$ownerNamespace`,
`$managedBy`, and `$ownedByThisRelease := and (eq $ownerName $.Release.Name) (eq $ownerNamespace
$.Release.Namespace) (eq $managedBy "Helm")`; fire `if not $ownedByThisRelease`. Verified live on CRC:
`helm upgrade --set createLocal=true` against the operator-owned auditor group still fails with the
remedy (the operator group has none of the three markers). Offline `helm template` still renders exactly
one Group under `createLocal: true` (guard inert without `lookup`); `helm lint` clean.

### F2 (Codex) — the default-group test was substring-only

**Finding.** `test_enabled_true_uses_the_default_auditor_group` asserted only
`"app-ocp-rbac-groupsync-ns-auditor" in out` and `"\nkind: Group\n" not in out`. Codex mutated the
rendered CRB subject to `WRONG-GROUP` while leaving the annotation: `current_test_would_pass=True`,
`structural_subject_check=False`. So a regression that bound the wrong group would pass the test.

**Re-check.** Confirmed. The repo already has `_auditor_docs()` (parses `--show-only
rbac-auditors.yaml` into YAML documents) for exactly this — the substring test did not use it.

**Decision — accepted.** Rewrote the test to assert the ClusterRoleBinding's `subjects` is exactly
`[{apiGroup, kind: Group, name: <group>}]`, the `group-sync-dashboard/auditor-group` annotation, and the
`roleRef` pointing at the rendered ClusterRole. It now fails on a wrong-subject render. 1058 chart tests
pass.

### F3 (Cursor) — the chart README still documented the old `[]` default

**Finding.** `charts/group-sync-dashboard/README.md` listed `rbacAuditors.groups` default as `[]`. This
PR changed it to `[{name: app-ocp-rbac-groupsync-ns-auditor}]` (bind-only). An operator following the
README (`[]` ⇒ "I must supply groups or it refuses") who sets only `enabled: true` would silently bind
`app-ocp-rbac-groupsync-ns-auditor` to the cluster-scoped read-only audit role — a confident wrong grant,
not a refused render. This is the "brief the reviewers on the docs an operator actually opens" case; the
`test_docs_citations`/`KEPT_OFF` suites did not catch a list-default drift.

**Re-check.** Confirmed at README line 419. `test_values_defaults`'s `CURRENT_DOCS` check is about
KEPT_OFF booleans, not a list default, so CI was green while the README was wrong.

**Decision — accepted.** Updated the README row to the new default and its consequence (enabling with no
override binds it), and noted the chart now refuses `createLocal: true` for a group owned elsewhere.

## Not asked

- Cursor's **N1 (lookup RBAC miss)**: `lookup` returns `{}` on a Forbidden, so the guard is inert if the
  installer lacks `get groups.user.openshift.io`. Debt-accepted — the guard cannot fail-closed without
  breaking `helm template`; already documented in `docs/TROUBLESHOOTING_auditor_groups.md`.
- Cursor noted a mixed groups list aborts the whole render on any one collision (fail-closed, correct).

## Outcome

Three findings, all accepted; F1 is the headline — both reviewers converged that the ownership check was
release-name-only, and the completed check (name + namespace + `managed-by`) matches Helm's actual
ownership model and still fires live on the operator-owned group. F2 hardened a substring test into a
structural subject assertion; F3 fixed the chart README an operator reads. `helm lint` clean, 1058 chart
tests pass, the guard verified live. Second pass on the fixed head follows if run; otherwise the fixes
were each verified directly (live guard fire, structural test, doc).
