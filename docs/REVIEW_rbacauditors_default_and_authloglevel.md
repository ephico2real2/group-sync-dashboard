# Review — PR #121 (rbacAuditors ON by default) + PR #122 (crc authLogLevel off)

Adversarial pass, 2026-09-15, on a five-claim brief covering two small chart/env changes that both came
out of a real incident: a `helm upgrade -f environments/crc.yaml` had dropped the auditor RBAC (it was
opt-in and crc.yaml never repeated it), so lateef.o — a member of the auditor group — lost report access;
and the auth-loglevel Job (a post-upgrade hook forced on by crc.yaml) hung the upgrade on a CPU-saturated
node. Codex ran `gpt-5.6-sol`/xhigh with a shell (helm renders, an in-memory `applyPosition`/SAR trace,
the real FastAPI route); Cursor ran `cursor-grok-4.6-high-fast` in ask mode, source only. Both were on a
combined copy (main with #121 merged, plus #122's changes).

## Verdicts

| Claim | Cursor | Codex | Decision |
|---|---|---|---|
| C1 the rbacAuditors default is safe for every install; not a privilege escalation | CONFIRMED (scoped: "no members of that group") | **REFUTED (d)** | **Policy, not code** — see below |
| C2 the test edits do not weaken coverage | CONFIRMED (w/ an adjacent note) | **REFUTED** | **Accepted (converged on the real one)**: `test_declining_the_grant_drops_the_rule_and_keeps_the_rest`'s `groups_granted` check scanned every ClusterRole, so the always-on audit role satisfied it — deleting the MAIN reader's groups rule would still pass (Codex proved by mutation). Scoped to the main role, like `_users_rules` |
| C3 no other test/template assumes auditors are off; docs complete | CONFIRMED (tests); **README drift found** | REFUTED (docs incomplete) | **Accepted (F1, converged)**: the chart README still said default `false`/opt-in. Corrected; an UPGRADE NOTE added to the CHANGELOG |
| C4 crc authLogLevel management off is safe and complete | CONFIRMED | CONFIRMED | — (the Job/hook is fully gated by `manage`; the operator CR is at Normal, so nothing is stranded) |
| C5 the README/env contract holds | CONFIRMED | CONFIRMED | — |

## The policy finding (C1(d) / Additional attack), and the decision

Codex REFUTED C1 on **policy, not correctness**: the rendered objects are read-only and bind-only, but
defaulting `rbacAuditors.enabled: true` in the **chart** means that on any cluster where the named group
`app-ocp-rbac-groupsync-ns-auditor` already exists, a `0.26 → 0.27` upgrade **grants its members** new
cluster-wide identity/RBAC reads AND the dashboard's **wide report tier** (the audit role grants exactly
the `list clusterrolebindings` SAR the report gate checks). The settled record
`docs/FINDINGS_auditor_group_ldap_sync_interaction.md` explicitly recommends keeping the feature opt-in
for this reason. Codex's proposed alternative: keep the chart default OFF and pin `enabled: true` in
`crc.yaml` (fixes lateef.o for the estate, no escalation for other consumers).

**Decision (operator, 2026-09-15): keep the chart default ON.** The operator's chart philosophy is sane
defaults ON in `values.yaml`, environments disabling explicitly, and they accepted the grant as intended
(a chosen group over the report gate is the feature's whole purpose). Codex's finding is not rejected on
the merits — it is a real, correctly-identified escalation — but the design choice is the operator's, and
it is now **documented prominently**: the CHANGELOG carries an UPGRADE NOTE (a cluster that does not want
the grant sets `enabled: false` before upgrading), the values comment and the chart README state the
inert-until-populated / wide-tier behaviour. Both reviewers agree the binding is inert where the group has
no members.

## What was applied (follow-up PR #123)

- **C2** — the `groups_granted` scan scoped to the main role (excludes `report-auditor`); a deleted main
  groups rule now fails the test.
- **F1** — the chart README `rbacAuditors.enabled` default corrected to `true` with the full behaviour.
- **Docs** — the CHANGELOG UPGRADE NOTE for the 0.26 → 0.27 escalation; chart bumped to 0.28.0 (the
  README lives under `charts/`, which the version-bump gate requires a bump for).

## Rejected

- **Codex's revert-to-opt-in.** The operator decided default-on; the finding is documented rather than
  applied. Recorded here so the decision and its reason are not lost.

## Outcome

The code was correct on both PRs; #122 (authLogLevel off) was CONFIRMED clean by both reviewers. The one
converged code finding (the weakened `groups_granted` test) is fixed, the doc drift and the upgrade note
are addressed, and the load-bearing policy question — a security-relevant chart default every consumer
inherits — was surfaced by both reviewers and consciously owned by the operator.
