# Documentation

Start with the operator guides below to install, configure and run the dashboard. Development
records follow separately; their status and measurements belong to the work they document.

## For operators

### Install and configure

- [HELM_DOWNLOAD_AND_INSTALL.md](HELM_DOWNLOAD_AND_INSTALL.md) — download, verify and install the chart.
- [Chart README](../charts/group-sync-dashboard/README.md) — deployment instructions and the values reference.
- [CLUSTER_CREDENTIALS.md](../charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md) — how a cluster connection is made, fails and recovers.
- [CLUSTER_STANZA.md](CLUSTER_STANZA.md) — accepted cluster configurations and ConfigMap onboarding.
- [TUTORIAL_ca_trust_hashed_directory.md](TUTORIAL_ca_trust_hashed_directory.md) — container CA trust and OpenShift trust bundles.

### Access, polling and reports

- [ACCESS_CONTROL.md](ACCESS_CONTROL.md) — who can enter the dashboard and what each reader can see.
- [api-access.md](api-access.md) — call the API from outside the cluster with curl or Postman.
- [polling-and-discovery.md](polling-and-discovery.md) — polling cadences, how a cluster enters the fleet, ConfigMap cleanup, and why a fresh read cannot yet be forced.
- [AUDIT_LOG_CAPTURE.md](AUDIT_LOG_CAPTURE.md) — audit-log login capture and how to check it is working.
- [LOGIN_CAPTURE_QUICKCHECK.md](LOGIN_CAPTURE_QUICKCHECK.md) — a step-by-step check that audit-log login capture works; its OAuth Debug transcript is history, not guidance.
- [UNMANAGED_GRANT_EXCLUSIONS.md](../charts/group-sync-dashboard/docs/UNMANAGED_GRANT_EXCLUSIONS.md) — which unmanaged grants are silenced automatically, and the label or annotation that records an exclusion.
- [Reports](reports/README.md) — report contents, parameters and scheduling.

### Troubleshooting and runbooks

- [TROUBLESHOOTING_auditor_groups.md](TROUBLESHOOTING_auditor_groups.md) — auditor groups, `createLocal` and LDAP GroupSync collisions.
- [RUNBOOK_backup_restore.md](RUNBOOK_backup_restore.md) — back up and restore the dashboard's history.

### Understand the deployment and its releases

- [reference-architecture.md](reference-architecture.md) — components, data flow and deployment constraints.
- [CHANGELOG.md](CHANGELOG.md) — what each application and chart release changed.

## For development

### Records by convention

- `REVIEW_*.md` — review findings and decisions, kept in this directory at their cited paths.
- `SPEC_*.md` — the original specifications in this directory; the feature programme's specifications
  live in `specs/`, with status and release information in the [specification index](specs/README.md).
- `DESIGN_*.md` — design decisions and implementation records in this directory. The separate
  [design index](design/README.md) covers the `design/` mocks, research and feature contracts.
- `BENCHMARK_*.md` and `VALIDATION_*.md` — performance measurements and validation evidence.
- `session-changelogs/` — working-session history, collected in the [session index](session-changelogs/README.md).
- `handoff/` — lab and workstation handoff plans and notes, separate from dashboard operator runbooks.

### Requirements, findings and history

- [AUDIT_visibility_premise_and_assumptions.md](AUDIT_visibility_premise_and_assumptions.md) — the per-user visibility audit brief and assumptions.
- [FINDINGS_auditor_group_ldap_sync_interaction.md](FINDINGS_auditor_group_ldap_sync_interaction.md) — measured evidence behind the auditor-group troubleshooting guide.
- [REQUIREMENTS_per_user_visibility.md](REQUIREMENTS_per_user_visibility.md) — requirements and constraints preceding the visibility design.
- [REPORTING_ENHANCEMENTS.md](REPORTING_ENHANCEMENTS.md) — reporting feature backlog.
- [OAUTH_LOGLEVEL_REVIEW.md](OAUTH_LOGLEVEL_REVIEW.md) — review record for the retired OAuth Debug Jobs.
- [HANDOVER_2026-09-20.md](HANDOVER_2026-09-20.md) — programme handover and dated state updates.
- [image-vulnerability-scan.md](image-vulnerability-scan.md) — dated image and base-image scan evidence.

### Development guides and design records

- [RELEASING.md](RELEASING.md) — application and chart release procedures and version ownership.
- [api-contract.md](api-contract.md) — documentation and schema rules for new API endpoints.
- [storage-coupling.md](storage-coupling.md) — the SQLite storage seam and requirements for another backend.
- [unmanaged-audit-design.md](unmanaged-audit-design.md) — unmanaged-grant discovery design and invariants.
- [namespace-report-design.md](namespace-report-design.md) — superseded namespace-report proposal and its design lineage.
- [TUTORIAL_mermaid_diagrams.md](TUTORIAL_mermaid_diagrams.md) — author, check and render diagrams in this repository.
- [updating-vendored-assets.md](updating-vendored-assets.md) — refresh the vendored API documentation bundles.
