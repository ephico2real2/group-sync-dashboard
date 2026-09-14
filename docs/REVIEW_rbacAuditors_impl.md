# Review — PR #110, rbacAuditors implementation (issue #100)

Adversarial pass on the real chart (Extension A applied from
`docs/DESIGN_reporting_auditors_and_ns_selector.md` §2). 2026-09-14. Codex (gpt-5.6-sol, xhigh, shell,
rendered with `helm template`) and Cursor (Grok 4.6 high fast, ask mode — its allowlist refused `helm`,
so it reviewed the commit's patch and marked live renders PLAUSIBLE). Every verdict re-checked here by
rendering.

## Verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 the guards fire exactly, never spuriously | CONFIRMED | CONFIRMED | — |
| C2 the binding name is DNS-1123; the real name only in subjects | REFUTED | CONFIRMED | **Accepted on the fact; the annotation is deliberate — kept** |
| C3 the role is read-only and covers the gate | CONFIRMED | CONFIRMED | — |
| C4 the local Group is upgrade-safe; the synced path makes no Group | CONFIRMED | CONFIRMED | — |
| C5 the tests and defaults hold | CONFIRMED | CONFIRMED | — |
| N1 the non-bool validation is complete | REFUTED | — | **Accepted** |
| N2 enabled with no groups | PLAUSIBLE | — | **Accepted** |
| Finding 1 (Cursor): the CHANGELOG heading still names chart 0.21.0 | — | (will go red) | **Accepted** |
| Finding 3 (Cursor): the read-only test does not pin resources | — | risk PLAUSIBLE | **Accepted** |

## C2 — the group name is also in an annotation (accepted on the fact, annotation kept)

Codex is right that the real group name appears in the `group-sync-dashboard/auditor-group` annotation as
well as `subjects[0].name`, so "the real name ONLY in subjects" (my brief's wording) is literally false.
But the annotation is deliberate: the binding's `metadata.name` is a hash, so the annotation is what lets
an operator map a hashed binding back to its group. An annotation has no DNS-1123 constraint and no length
limit that a group name would breach. Cursor noted the same annotation approvingly. Re-check: all sampled
names (LDAP DN, underscore, uppercase, 300-char) render a strict DNS-1123 `metadata.name` and preserve the
exact name in `subjects[0].name`; 1000 distinct groups → 1000 unique binding names, 0 collisions. Decision:
the finding is correct, the fix (remove the annotation) is rejected — the annotation is the whole point of
hashing the name. The brief's wording was imprecise, not the template.

## N1 — non-bool `enabled`/`createClusterRole` (accepted)

The type guard on `enabled` sat inside `{{- if .Values.rbacAuditors.enabled }}`, so it only checked a
*truthy* value; and `createClusterRole` had no type guard at all — a string `"false"` is truthy in Helm,
so `createClusterRole: "false"` would render the role the operator meant to suppress. Re-check confirmed
both. Fix: validate `enabled`'s type before the truthiness decides (`--set-string
rbacAuditors.enabled=true` now fails with "must be true or false"), and add a `kindIs "bool"` guard on
`createClusterRole` (`--set-string createClusterRole=false` now fails). Tested.

## N2 — `enabled=true` with no groups (accepted)

Rendered an unused, unbound ClusterRole. Harmless (an unbound role grants nothing) but almost certainly a
misconfiguration, and the chart's house style is to fail fast on those. Fix: `enabled=true` with an empty
`groups` list fails the render with the remedy. Tested.

## Findings 1 and 3 (accepted)

- **The CHANGELOG heading** still named chart 0.21.0 while Chart.yaml is 0.22.0, so
  `test_chart_versions.py::test_the_changelog_heading_names_the_current_release_pair` would go red in CI.
  Added the 0.22.0 entry for the auditor feature.
- **The read-only test** asserted the role's verbs are `{get, list}` but not the resource set, so a future
  rule adding a workload resource with get/list would pass. Strengthened to pin the exact
  identities-and-RBAC resource set.

## Outcome

Four of five claims confirmed on the real render; C2 refuted on wording only (the annotation is
deliberate). Two "not asked" findings (the type guards, the empty-groups guard) and two Cursor findings
(the CHANGELOG heading, the resource pin) accepted and applied, each with a render or test check. The
implementation matches the reviewed design; the corrections harden the input validation and the test.
Re-validated: `helm lint`; the twenty-case `TestReportingAuditors`; `test_chart_versions`. A second pass
on the fixed head follows.
