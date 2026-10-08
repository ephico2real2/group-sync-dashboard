# Documentation

Start with the operator guides below to install, configure and run the dashboard. Development
records follow separately; their status and measurements belong to the work they document.

## Guides — `guides/`

- [TUTORIAL_ca_trust_hashed_directory.md](guides/TUTORIAL_ca_trust_hashed_directory.md) — container CA trust and OpenShift trust bundles.
- [ACCESS_CONTROL.md](guides/ACCESS_CONTROL.md) — who can enter the dashboard and what each reader can see.
- [api-access.md](guides/api-access.md) — call the API from outside the cluster with curl or Postman.
- [AUDIT_LOG_CAPTURE.md](guides/AUDIT_LOG_CAPTURE.md) — audit-log login capture and how to check it is working.
- [LOGIN_CAPTURE_QUICKCHECK.md](guides/LOGIN_CAPTURE_QUICKCHECK.md) — a step-by-step check that audit-log login capture works; its OAuth Debug transcript is history, not guidance.
- [architecture-overview.md](guides/architecture-overview.md) — the architecture in seven figures: the components, one process, a poll, a request, a report, credentials, retention.
- [reference-architecture.md](guides/reference-architecture.md) — components, data flow and deployment constraints.
- [image-vulnerability-scan.md](guides/image-vulnerability-scan.md) — dated image and base-image scan evidence.
- [RELEASING.md](guides/RELEASING.md) — application and chart release procedures and version ownership.
- [RELEASE_BRANCH_SETUP.md](guides/RELEASE_BRANCH_SETUP.md) — the `release` branch's one-time GitHub setup (deploy key, environment, branch, ruleset), its checks and upkeep.
- [api-contract.md](guides/api-contract.md) — documentation and schema rules for new API endpoints.
- [TUTORIAL_mermaid_diagrams.md](guides/TUTORIAL_mermaid_diagrams.md) — author, check and render diagrams in this repository.
- [updating-vendored-assets.md](guides/updating-vendored-assets.md) — refresh the vendored API documentation bundles.

## Packaged chart guides — `charts/group-sync-dashboard/docs/`

These install and operate guides ship inside the Helm chart.

- [HELM_DOWNLOAD_AND_INSTALL.md](../charts/group-sync-dashboard/docs/HELM_DOWNLOAD_AND_INSTALL.md) — download, verify and install the chart.
- [CLUSTER_CREDENTIALS.md](../charts/group-sync-dashboard/docs/CLUSTER_CREDENTIALS.md) — how a cluster connection is made, fails and recovers.
- [CLUSTER_STANZA.md](../charts/group-sync-dashboard/docs/CLUSTER_STANZA.md) — accepted cluster configurations and ConfigMap onboarding.
- [UNMANAGED_GRANT_EXCLUSIONS.md](../charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md) — which unmanaged grants are silenced automatically, and the label or annotation that records an exclusion.
- [TROUBLESHOOTING_auditor_groups.md](../charts/group-sync-dashboard/docs/TROUBLESHOOTING_auditor_groups.md) — auditor groups, `createLocal` and LDAP GroupSync collisions.
- [RUNBOOK_backup_restore.md](../charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md) — back up and restore the dashboard's history.
- [RUNBOOK.md](../charts/group-sync-dashboard/docs/RUNBOOK.md) — a remote cluster's connection is broken: find out why, then Refresh and Rejoin; kept beside the chart's values.

## Reports and releases

- [Chart README](../charts/group-sync-dashboard/README.md) — deployment instructions and the values reference.
- [Reports](reports/README.md) — report contents, parameters and scheduling.
- [CHANGELOG.md](CHANGELOG.md) — what each application and chart release changed.

## Design — `design/`

- `DESIGN_*.md` — design decisions and implementation records in `design/`. The
  [design index](design/README.md) covers the `design/` mocks, research and feature contracts.
- [polling-and-discovery.md](design/polling-and-discovery.md) — polling cadences, how a cluster enters the fleet, ConfigMap cleanup, and why a fresh read cannot yet be forced.
- [REQUIREMENTS_per_user_visibility.md](design/REQUIREMENTS_per_user_visibility.md) — requirements and constraints preceding the visibility design.
- [REPORTING_ENHANCEMENTS.md](design/REPORTING_ENHANCEMENTS.md) — reporting feature backlog.
- [storage-coupling.md](design/storage-coupling.md) — the SQLite storage seam and requirements for another backend.
- [unmanaged-audit-design.md](design/unmanaged-audit-design.md) — unmanaged-grant discovery design and invariants.
- [namespace-report-design.md](design/namespace-report-design.md) — superseded namespace-report proposal and its design lineage.
- `SPEC_*.md` — the original specifications in `design/`; the feature programme's specifications
  live in `specs/`, with status and release information in the [specification index](specs/README.md).

## Reviews — `reviews/`

- `REVIEW_*.md` — review findings and decisions, kept in `reviews/` at their cited paths.
- [DOCS_AUDIT_2026-10-05_b1_chart_operate.md](reviews/DOCS_AUDIT_2026-10-05_b1_chart_operate.md) — docs content audit, batch 1: the chart's install and operate guides, claim by claim.
- [DOCS_AUDIT_2026-10-05_b2_chart_reference.md](reviews/DOCS_AUDIT_2026-10-05_b2_chart_reference.md) — docs content audit, batch 2: the chart README and the backup/restore runbook, claim by claim.
- [DOCS_AUDIT_2026-10-05_b3_access_guides.md](reviews/DOCS_AUDIT_2026-10-05_b3_access_guides.md) — docs content audit, batch 3: the access-control, login-capture and API guides, claim by claim.
- [DOCS_AUDIT_2026-10-05_b4_release_build.md](reviews/DOCS_AUDIT_2026-10-05_b4_release_build.md) — docs content audit, batch 4: the release, build and repository guides, the root README and `local-development/README.md`, claim by claim.
- [DOCS_AUDIT_2026-10-05_b5_reference_architecture.md](reviews/DOCS_AUDIT_2026-10-05_b5_reference_architecture.md) — docs content audit, batch 5: the reference architecture, its diagrams and its citations, claim by claim.
- [DOCS_AUDIT_2026-10-05_b6_tutorials.md](reviews/DOCS_AUDIT_2026-10-05_b6_tutorials.md) — docs content audit, batch 6: the CA-trust and mermaid tutorials, their commands run where no cluster write was needed, claim by claim.

## Research — `research/`

- `BENCHMARK_*.md` and `VALIDATION_*.md` — performance measurements and validation evidence in `research/`.
- [AUDIT_visibility_premise_and_assumptions.md](research/AUDIT_visibility_premise_and_assumptions.md) — the per-user visibility audit brief and assumptions.
- [FINDINGS_auditor_group_ldap_sync_interaction.md](research/FINDINGS_auditor_group_ldap_sync_interaction.md) — measured evidence behind the auditor-group troubleshooting guide.
- [OAUTH_LOGLEVEL_REVIEW.md](research/OAUTH_LOGLEVEL_REVIEW.md) — review record for the retired OAuth Debug Jobs.

## History — `history/`

- [HANDOVER_2026-09-20.md](history/HANDOVER_2026-09-20.md) — programme handover and dated state updates.
- `history/session-changelogs/` — working-session history, collected in the [session index](history/session-changelogs/README.md).
- `history/handoff/` — lab and workstation handoff plans and notes, separate from dashboard operator runbooks.
