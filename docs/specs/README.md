# Feature programme 2026-09 — the specifications

Thirteen modules, each specified with its complete code **before** any of them is implemented,
each tracked by one GitHub issue inside one GitHub milestone, and each implemented, released,
validated and audited **strictly one at a time**. This directory is the only source the
implementation is applied from: nothing is implemented from memory, and a specification is
applied file by file as written.

## The rule that governs this directory

Every `SPEC_*.md` was written by a design agent that read the repository, and its body is that
agent's text: sliced from the agent's output by heading and re-concatenated to the byte before the
file was written. It is verbatim with exactly two kinds of exception, both stated in the file: the
seam repair named in its Source row where the agent's output was cut across messages, and the
citation or name corrections listed in its orchestrator's notes, each changing a reference and
never a claim. The only hand-written parts are the header table, the "Orchestrator's notes" (what
supersedes a number in the body, the corrections, and deviations found in review or in
implementation) and this index. A deviation found necessary during implementation is written back into
the spec in the same pull request, with the reason, under the orchestrator's notes.

Two consequences for the tooling:

- A spec cites names its own code will create. `local-development/tests/test_docs_citations.py#_spec_introduces`
  lets a citation from a spec pass when the specs introduce the anchor: for a Python target, a
  name that the Python code blocks of some spec define (parsed, so a plausible name in prose
  cannot pass) or literal text inside one of those blocks; for any other target, the anchor text
  in some spec outside the citing span. Once the feature ships, the anchor exists in the cited
  file and the ordinary rule takes over. A spec citing a name that neither the code nor any spec
  introduces fails, which is how four wrong citations in the designs were found and corrected.
- The verbatim bodies are exempt from `markdownlint` (see the comment in the lint config at the
  repository root); this index is not.

## The programme's rules, from the operator

- **Modular, not blanket-off.** Every feature is a module with its own switch. The default is
  chosen per feature by judgment and the rationale sits in the values comment: on when cheap,
  safe, and needing no extra RBAC, credential, second image or cluster-wide side effect; off when
  it needs any of those or is a platform-policy choice. Switches that interact are modelled in the
  chart — refuse or derive, never both silently.
- **No tech debt.** Docs, chart README rows, the CHANGELOG entry, the Chart.yaml history line and
  tests land with each change. No placeholders, no "follow-up".
- **Nothing from memory.** The spec is the source; the reviewers' proposed snippets are accepted
  or rejected in writing; the adversarial pass is Codex and Cursor with a per-claim brief.
- **Main is branch-protected.** Every change is a pull request the operator merges; a merge to
  main is the release trigger for the image and the chart.

## The thirteen modules

| Id | Specification | Batch | Milestone | Version on release | Issue | Status |
|---|---|---|---|---|---|---|
| A1 | [`SPEC_A1_ui_tests_in_ci.md`](SPEC_A1_ui_tests_in_ci.md) — Playwright UI tests in CI | A — quality | R1 | no version change (CI and docs only) | [#56](https://github.com/ephico2real2/group-sync-dashboard/issues/56) | released |
| A3 | [`SPEC_A3_release_script.md`](SPEC_A3_release_script.md) — release preparation script | A — release | R1 | no version change (a repository tool) | [#57](https://github.com/ephico2real2/group-sync-dashboard/issues/57) | released |
| B4 | [`SPEC_B4_group_count_cliff.md`](SPEC_B4_group_count_cliff.md) — group-count cliff alert with read-only silencing | B — alerts | R2 | app 0.12.0, chart 0.11.0 | [#58](https://github.com/ephico2real2/group-sync-dashboard/issues/58) | released |
| B2 | [`SPEC_B2_history_retention.md`](SPEC_B2_history_retention.md) — retention for membership_event and sync_event | B — data | R2 | app 0.13.0, chart 0.12.0 | [#59](https://github.com/ephico2real2/group-sync-dashboard/issues/59) | released |
| B3 | [`SPEC_B3_grafana_dashboard.md`](SPEC_B3_grafana_dashboard.md) — Grafana dashboard shipped with the chart | B — observability | R2 | chart 0.13.0 (chart only) | [#60](https://github.com/ephico2real2/group-sync-dashboard/issues/60) | in progress |
| C1 | [`SPEC_C1_table_export.md`](SPEC_C1_table_export.md) — CSV and JSON export of the table on screen | C — product | R3 | app 0.14.0, chart 0.14.0 | [#61](https://github.com/ephico2real2/group-sync-dashboard/issues/61) | specified |
| C2 | [`SPEC_C2_users_tab_providers_identities.md`](SPEC_C2_users_tab_providers_identities.md) — Users tab: provider allow-list and exact first login | C — product | R3 | app 0.15.0, chart 0.15.0 | [#62](https://github.com/ephico2real2/group-sync-dashboard/issues/62) | specified |
| A2 | [`SPEC_A2_supply_chain.md`](SPEC_A2_supply_chain.md) — SBOM, keyless signing, build and chart provenance | A — supply chain | R4 | no app or chart version change (workflows and the build script only) | [#63](https://github.com/ephico2real2/group-sync-dashboard/issues/63) | specified |
| B1 | [`SPEC_B1_offsite_backup.md`](SPEC_B1_offsite_backup.md) — off-volume backup CronJob and restore runbook | B — operations | R4 | chart 0.16.0 (chart only) | [#64](https://github.com/ephico2real2/group-sync-dashboard/issues/64) | specified |
| C4 | [`SPEC_C4_idle_timeout.md`](SPEC_C4_idle_timeout.md) — idle timeout with countdown | C — product | R5 | app 0.16.0, chart 0.17.0 | [#65](https://github.com/ephico2real2/group-sync-dashboard/issues/65) | specified |
| D1 | [`SPEC_D1_audit_log_login_capture.md`](SPEC_D1_audit_log_login_capture.md) — login capture from the oauth-server audit log | D — architecture | R5 | app 0.17.0, chart 0.18.0 | [#66](https://github.com/ephico2real2/group-sync-dashboard/issues/66) | specified |
| C3 | [`SPEC_C3_namespace_report.md`](SPEC_C3_namespace_report.md) — namespace access report, HTML core and optional PDF image | C — product | R6 | app 0.18.0, chart 0.19.0, reporting image 0.1.0 | [#67](https://github.com/ephico2real2/group-sync-dashboard/issues/67) | specified |
| D2 | [`SPEC_D2_per_cluster_authorization.md`](SPEC_D2_per_cluster_authorization.md) — per-cluster authorization for the multi-cluster case | D — architecture | R7 | app 0.19.0, chart 0.20.0 | [#68](https://github.com/ephico2real2/group-sync-dashboard/issues/68) | specified |

The rows are in **implementation order**, which is also the version ladder. Status moves
`specified → in progress → released` as each issue is worked; a spec's own header carries the same
status.

## Milestones

| Milestone | Contents, in order | Why this grouping |
|---|---|---|
| R1 — Quality and release tooling | A1, A3 | Makes every later UI change safer and every version bump cheap. No user-facing change. |
| R2 — Alerts, retention, Grafana | B4, B2, B3 | Small, self-contained operational modules. |
| R3 — Product wins | C1, C2 | Small UI and API modules; the first release with A1 guarding the UI. |
| R4 — Supply chain and backup | A2, B1 | Touches the publish and chart workflows; verified on a real publish. |
| R5 — Sessions and login source | C4, D1 | Both platform-policy modules, off by default. |
| R6 — Reporting | C3 | A second image with its own Containerfile and scan gate. |
| R7 — Multi-cluster authorization | D2 | The architectural item; retires the README caveat. |

A milestone closes when its last issue closes and the release is published and validated.

## The version ladder

Each feature is released on its own, so each one that changes the application or the chart takes
its own bump, MINOR for a new module (the chart's own convention: a value added is MINOR, an
appVersion move bumps the chart), and a chart-only module bumps only the chart. The design bodies
were written in isolation and each assumed it was the next release; the "Version on release"
column above supersedes every version number inside a body, and each spec's orchestrator's notes
say so.

## Definition of done, per issue

1. Branch `feat/<id>-<slug>`; the pull request is opened early and says `Closes #N`.
2. The spec is applied surgically, file by file, exactly as written; a necessary deviation is
   written back into the spec in the same pull request with the reason.
3. The full suite passes; `helm lint` and `helm template` pass for every switch state the spec
   names; the chart deploys to the reference cluster; the spec's live verification is run and its
   output recorded.
4. Adversarial review by Codex and Cursor with a per-claim brief. Every reviewer snippet is
   accepted or rejected in writing in `docs/REVIEW_<id>.md` with the reason; accepted ones are
   applied; the suite, deploy and live checks run again.
5. CI green; the operator merges; the release happens (the image published and scanned, the chart
   published and installable); the review record closes the audit; the issue is closed with a
   comment naming the release.
6. Only then the next issue.

## Reconciliations across the specs

Each design agent worked against the same main in isolation, so these collide and are resolved in
implementation order, never by any single body:

1. **Schema migrations.** B4, C2, C3 and D1 each claim the next migration number. Numbered in
   release order: B4 = 8, C2 = 9, D1 = 10, C3 = 11. B2 adds indexes only, in `SCHEMA`, and needs
   no migration.
2. **The `(cluster_id, observed_at)` index on `membership_event`.** Both B2 and B4 define
   `membership_event_by_time`. B4 ships first and defines it; B2 adds only `sync_event_by_time`.
3. **Version pairs.** Every release-bearing body assumed it was the next release (app 0.12.0,
   chart 0.11.0); the A batch explicitly carries no release. The header and the ladder above
   supersede every version number inside a body.
4. **The README's "Not built yet" sentence and the CHANGELOG's `## Unreleased` heading.** A1
   creates the heading; B4 then B2 each edit the sentence as it stands after the earlier merge.
5. **Shared constants.** B2 extends `RETENTION_TABLES`; B4 extends the alert-kind vocabulary and
   the self-tier detail list; D1 adds a login outcome. Each old/new text in a body is re-derived
   from main at implementation time, and a difference is recorded as a deviation.
6. **Found by the adversarial review of PR #69** (`docs/REVIEW_feature_specs.md`): A3 lands before
   A2, so the release-tooling docs describe signing and SBOMs only when A2 adds them; B1's chart
   README old text counts eleven alerts, which B4 makes twelve; and B2's retention is held while
   backups are disabled, so the default window never deletes what has no copy. Each is in the
   affected spec's orchestrator's notes.

## Decisions the operator has made

Recorded 2026-09-04, before implementation:

- **A2:** public Rekor transparency-log entries are acceptable; keyless cosign through GitHub OIDC.
- **B2:** `syncEventsDays: 730` on by default; `membershipEventsDays: 0` (forever).
- **B3:** no Grafana exists yet. Validation installs grafana-operator v5 in a test namespace on the
  reference cluster and imports the ConfigMap through a `GrafanaDashboard` with `configMapRef`;
  the README carries both the sidecar-label and the operator-CR recipes.
- **D1:** the rendered default when the module is on is cluster-wide `get nodes/proxy` and
  `list nodes`; `nodeNames` stays the optional narrowing. The module itself stays off.
- **A1:** the browser-tests job is a required status check on `main` from its first merge, not after a
  week of green runs: "this is real life testing, so it is needed."

Questions each design left for the operator are collected in the feature's issue and answered
before its pull request opens: A1 (when the browser job becomes a required check), A2 (the cosign
major consumers run), B1 (the AWS CLI as the default S3 command; keeping the permanently-firing
"unobserved" rule), B4 (the floor for the largest groups; whether the group-sync-operator preserves
a foreign Group annotation is **measured** on the reference cluster, not asked), C1 (recording
exports in activity — default no), C3 (classification marking; a UBI9 fallback for the PDF image;
`-pass-access-token` later), D1 (the cluster's audit profile; whether to backfill), D2 (one
identity provider across the fleet; remote ServiceAccount SAR grants).

## How the specs were produced

Five design agents, one per batch (A; B1/B2; B3/B4; C; D), each briefed with the operator's rules
and the repository, each required to cite `path#anchor` for every claim and to write complete code.
Their outputs were extracted from the session's task records, joined where the API had cut them
across messages (the seam rule is stated in each spec's header), sliced by feature heading, and
written here by a script that asserts the slices re-concatenate to the joined source exactly. The
orchestrator then read every design against the files it cites; what that pass found is in each
spec's orchestrator's notes and in the reconciliations above.
