# Review — PR #111, namespace-metadata capture (issue #101, B1)

Adversarial pass on the real code (Extension B1 applied from
`docs/DESIGN_reporting_auditors_and_ns_selector.md` §3.3–3.4, §3.8). 2026-09-14. Codex (gpt-5.6-sol,
xhigh, shell — ran pytest, the migrations, and helm) and Cursor (Grok 4.6 high fast, ask mode — its
allowlist refused the shell, so it traced the source and marked runs PLAUSIBLE).

## Verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 capture is bounded and correct | CONFIRMED (ran pytest; a 10-label probe) | CONFIRMED (source) | — |
| C2 the store write is atomic and correct | CONFIRMED (concurrent-reader, stale-row, FK, extra-param checks) | CONFIRMED | — |
| C3 migration 12 is safe | CONFIRMED (v11→migrate vs fresh; user_version=12; idempotent) | CONFIRMED | — |
| C4 the poller threads the labels; nothing else breaks | CONFIRMED (forwarding, 403, transient retention, loader) | CONFIRMED | — |
| C5 off by default; the guards hold | CONFIRMED (default render; guard states; helm lint; one define) | CONFIRMED | — |

## Outcome

No defect found in the B1 scope by either reviewer. Codex measured every claim on the real code: the
capture filters to the configured keys and skips nameless items; `replace_namespaces` writes the child
table inside the one existing `_write()` (a reader never sees half-written metadata); migration 12 opens a
v11 database to parity with a fresh one at `user_version=12`; the poller forwards the labels and the
loader reads `namespaceMetadataLabels`; the default install renders unchanged and the two guards fire only
when they should; exactly one `gsd.reportingGuards` define exists, included by both Deployments. Codex
also confirmed comma/Unicode/4-KiB label values round-trip and that `test_storage_seam`/`test_chart_versions`
pass (the docstring carries no `SELECT … FROM` shape). Cursor confirmed the same from source.

The two recorded deviations from the round-1 wording (the ConfigMap key rather than a `GSD_NS_METADATA_LABELS`
env; the guards folded into the existing helper) were noted and neither reviewer objected. A second pass on
the same head follows, per the skill's confirmation step.
