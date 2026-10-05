# Review — PR #138: advisory CVE scanning (SARIF to code scanning, don't fail the build)

Adversarial pass, 2026-09-16, on the `image`-job change that makes CVE scanning advisory (report to
GitHub code scanning, never fail CI). Reviewer: **Cursor Fable 5.1 (xhigh)**, ask mode (no shell —
traces from source, marks the unverifiable PLAUSIBLE). The change was designed via an Ultracode
research/verify workflow (SARIF route confirmed free on this public repo) and applied by the
orchestrator; this pass attacked the applied diff. Every verdict was re-checked here, and the
orchestrator ran the empirical checks the reviewer could not (the repo default-token setting, the
codeql-action tag, `test_workflow_pins`, and the PR's own `image` run).

## Verdicts

| Claim | Fable | Re-check | Decision |
|---|---|---|---|
| C1 no CVE-driven fail path remains | CONFIRMED | all four fixable scans `fail-build: false`; the only `exit 1` is the distro blindness check (not CVE-driven) | **Accepted** |
| C2 `security-events: write` scoped + safe | CONFIRMED | job-level on `image` only; top-level stays `contents: read`; every `with:` value static | **Accepted** |
| C3 SARIF wiring correct | PLAUSIBLE (fetches blocked) | categories distinct; `outputs.sarif` is the real output; the PR's own run uploaded and produced the `grype` check | **Accepted, verified by the live run** |
| C4 nothing else breaks | CONFIRMED | blindness-check JSON inventories untouched; `test_publish_paths` region assertions hold | **Accepted** |
| C5 fork-PR / no-code-scanning stays green | CONFIRMED | `continue-on-error` on the uploads swallows the read-capped-token failure | **Accepted** |
| NEW: `workflow_call` caller-grant gap | CONFIRMED (mechanism), PLAUSIBLE (fires?) | **it fires** — repo `default_workflow_permissions` is `read` | **Accepted, fixed in this PR** |
| Secondary: SARIF *generation* steps not `continue-on-error` | volunteered | see below | **Rejected (with reason)** |

## NEW finding — the `workflow_call` path fails at plan time (fixed)

**Finding (Fable).** `helm.yaml`'s `validate` job calls `ci.yml` with no `permissions:` block. A called
workflow can only DOWNGRADE the caller's token; if the repo default is `contents: read`, the nested
`image` job's request for `security-events: write` exceeds the caller's grant and GitHub refuses the job
at plan time — before any step or `continue-on-error` runs — blocking every chart release.

**Re-check.** CONFIRMED and it FIRES: `gh api …/actions/permissions/workflow` returns
`default_workflow_permissions: "read"`. So my change, as first written, would have broken `helm.yaml`.

**Decision.** Accepted; applied Fable's fix — `permissions: { contents: read, security-events: write }`
on the `validate` job in `helm.yaml`, with the reason in a comment.

## Secondary finding — SARIF generation steps are not best-effort (rejected)

**Finding (Fable).** `fail-build: false` covers findings, not execution: a grype DB-download flake in a
`Report … (SARIF)` step would fail the job, unlike its `continue-on-error` upload.

**Decision.** Rejected, on the reason Fable itself raised. A grype *execution* failure is
infrastructure, not a CVE, so it does not violate "don't fail on CVEs" (the operator's actual
requirement); the four table scans have the same exposure without `continue-on-error`; and silently
swallowing a generation failure is the "green run that shipped no evidence" this repo deliberately
guards against (the blindness check exists for exactly that). Infra failures on a non-required job are a
signal worth seeing.

## Orchestrator-found (not the reviewer) — the pin comment

`test_workflow_pins` requires every third-party pin to carry a `# vX.Y.Z` comment. The first draft
pinned `upload-sarif` to the `codeql-bundle-v2.27.0` release commit with that literal comment, which
does not match `#\s*v\d`, so `tests (3.11)/(3.14)` went red on the first PR run (caught by CI, not by
the local `test_publish_paths`-only check — the lesson: run the workflow-pin test too). Repinned to
codeql-action `v3.38.0` (`42c378f`), a proper action release, satisfying the pin test and the
pin-by-release-commit rule.

## Outcome

Six claims confirmed; one real defect I introduced (the `workflow_call` caller-grant) found by Fable
and fixed in this PR; one secondary suggestion rejected with reason; one CI-caught pin-comment defect
fixed. Re-validated: YAML parses, `actionlint` clean, the four workflow-reading tests green (172), and
the PR's own `image` run concluded **success** while the SARIF upload populated code scanning (the
`grype` check appeared) — the advisory posture proven end to end. Second CI run after the fixes confirms
`tests` green.
