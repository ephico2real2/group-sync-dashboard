# Review — PR #82, A2: SBOM, keyless signing and build provenance

Adversarial second-opinion pass, 2026-09-05, on the ten-claim brief for #82
(`docs/specs/SPEC_A2_supply_chain.md` applied; no app or chart version change; the spec's five
deviations are in its orchestrator's notes). Nothing in this module can run locally end to end —
no registry credential, no OIDC token, no Fulcio — so the review is of the shape, the tools'
documented semantics, and the documentation, with local execution where possible (`bash -n`, sed,
YAML parsing, pytest). Cursor (Grok 4.6 high fast, ask mode) and Codex (gpt-5.6-sol, xhigh) are
recorded below; every verdict was re-checked here before a decision.

## Verdicts — Cursor

Read-only (no shell, no network in ask mode); every refutation re-measured here.

| Claim | Cursor | Decision |
|---|---|---|
| C1 the digest chain | REFUTED — `skopeo copy` without `--preserve-digests` may convert schema or compression ("source manifest type, with fallbacks"), and without `--all` copies a list's host-arch child while `--digestfile` recorded the list | **Accepted** — skopeo 1.20 here has both flags; both added, Cursor's test taken |
| C2 the job graph and permissions | CONFIRMED against GitHub's documented `needs`/status-function rules | — |
| C3 cosign 3 against quay.io | REFUTED on "readable on quay.io" — Quay's referrers API called incomplete; proposed `--new-bundle-format=false` | **Fact refuted, snippet rejected** — measured: quay.io answers `/v2/…/referrers/<digest>` for this repository with HTTP 200 and an OCI index; cosign 3.1.3 keeps the flag (default true) but marks it deprecated ("this will be the only supported format in future versions"), so pinning the legacy layout would pin a format cosign is removing; Q2 stays the operator's, its note on #63 corrected to say the flag is deprecated |
| C4 provenance | PLAUSIBLE (no fetch) | — ; the action's inputs were read from its `action.yml` at the pinned commit before the PR opened (spec deviation 4) |
| C5 sbom-action inputs and the artifact path | PLAUSIBLE (no fetch) | — ; same: inputs verified from `action.yml`; download-artifact v8 extracts a single named artifact into `.`, and the in-run `test -s sbom.spdx.json` refuses otherwise |
| C6 pins | PLAUSIBLE — the test does not dereference tags | — ; by design: the tests run offline; the tag→commit check is the release-time procedure (`gh api git/ref/tags`), done for all six on 2026-09-05 |
| C7 the sed extractors | CONFIRMED | — |
| C8 documentation | PLAUSIBLE — flags match; the subject is C10's | — |
| C9 fidelity | PLAUSIBLE — suspected the `--help` `awk` hunk and three unlisted files | **Partly accepted** — the `--help` hunk is on `main`, not in this diff (measured: `git diff origin/main` on the script carries no `awk`/`help` line); the three files (this spec's notes, the specs index, the review registration) are named by deviation (6); Cursor's diff-asserting test rejected (a test that pins a PR's file list rots the moment the PR merges) |
| C10 the first run on main | REFUTED — an ordinary merge signs only `:<appVersion>-<sha>` while §7 told operators to verify `:0.15.0`; a `workflow_dispatch` from another branch signs as `@refs/heads/<branch>` and passes its own read-back | **Accepted on both** — `attest` gated on `refs/heads/main` with the identity pinned to it (D9 in the design record; a branch dispatch pushes unsigned); §7 names the immutable tag and says when the alias verifies; RELEASING's "one digest, every tag" now says "under every tag that run pushed"; Cursor's two tests taken (the guide test adapted to the command text) |

**Not asked.** Accepted: D7 now states the two limits of the in-run proof (the cosign major it cannot
speak for, and the signature a failed read-back leaves behind). Rejected with the reason: the plan
step's `grep | awk` extractor stays — it must name the file chart-releaser actually packages, whatever
Chart.yaml says, or the attestation would point at a file that does not exist, whereas the label
step's strict `sed` is about which image an alias may name; `test_workflow_pins.py` stays offline
(above); `[ \t]` in the bracket class predates this change and prepare-release never writes a tab.

## Verdicts — Codex

Codex (gpt-5.6-sol, xhigh; read-only, on head d0d2985 — the same head Cursor reviewed) ran the
suites and `bash -n`, read the pinned actions' sources, and measured the sed patterns on BSD sed.

| Claim | Codex | Decision |
|---|---|---|
| C1 the digest chain | REFUTED on the same `skopeo copy` default as Cursor | **Accepted** (already applied from Cursor's pass) |
| C2 the job graph | CONFIRMED | — |
| C3 cosign 3 against quay.io | CONFIRMED — Sigstore's registry-support page lists Quay.io and Project Quay with OCI 1.1 referrers; a cosign 2.6 consumer must opt in with `--new-bundle-format=true` | — ; agrees with the probe here (HTTP 200 on the referrers endpoint) |
| C4 provenance | CONFIRMED against the pinned `action.yml`, `gh attestation verify`'s manual and chart-releaser's `cr.sh` | — |
| C5 sbom-action | REFUTED — the file inside the artifact is named after `artifact-name`; `test -s sbom.spdx.json` fails on the first run | **Accepted** — verified in `SyftGithubAction.ts` at the pinned commit (`${tempDir}/${fileName}` with `fileName = getArtifactName()`); the attest job downloads to a directory and reads `sbom-<sha>`; Codex's test taken. The single most important finding of the review: deterministic, and the in-run proof would have caught it only by failing the first run |
| C6 pins | REFUTED on wording only — the local reusable workflow is `./…`, which the test exempts by design | — ; the test is correct as written |
| C7 the sed extractors | REFUTED — `[ \t]` is not portable (BSD sed: literal `t`); `..*` is greedy | **Accepted** — `[[:blank:]]`, semver class for appVersion; the tests gained the tab, `1.2.3t`, extra-quote and rc cases |
| C8 documentation | REFUTED on three sentences — "travels with `skopeo copy --all`" (referrers are not platforms), "a fork signs as itself" (publish is skipped on forks), D7 (false while C5 stood) | **Accepted** — `oras cp --recursive` named for mirrors, D3 corrected, D7 rewritten under Cursor's pass |
| C9 fidelity | REFUTED — the two status hunks and the specs index were not named | **Accepted** — deviation (6) names them; Codex's diff-asserting test rejected (it pins a file list that rots at merge) |
| C10 the first run | REFUTED — C5 plus the alias/identity points Cursor made | **Accepted** as above |

**Not asked.** Accepted: the digest check is `^sha256:[0-9a-f]{64}$` (the glob accepted
`sha256:aNOT-A-DIGEST`); `helm.yaml`'s label step now copies with `--all --preserve-digests` and
compares the alias digest (it was an unqualified copy with no check — outside the spec's edits, so a
recorded deviation). Rejected: gating the `publish` job on `main` — a dispatch from a branch may
still push an unsigned immutable tag, and the design record now says so; the docs-prose test.

## Outcome

Two reviewers, one head. Cursor refuted three claims and Codex six; between them five accepted
defects that the first run on `main` would have surfaced as a red job or, worse, a green job whose
documented command fails: the SBOM filename, the skopeo copy contract, the branch-dispatch
identity, the unsigned alias in the install guide, and the BSD-sed bracket class. Every accepted
finding carries the reviewer's test or an adapted one; three snippets were rejected with a measured
reason (the deprecated legacy bundle flag, gating `publish`, the diff- and prose-asserting tests).
A second pass by both reviewers ran on the fixed head before merge (recorded below).
