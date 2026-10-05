# Review record — the Kyverno discovery record (#170 step 0, PR #227)

Branch `feat/170-kyverno-discovery`, base `main` (`1ef1dc8`). A measurement record, so the review was a
re-measurement: OB3 (Opus 5; read-only `oc` on the lab, four in-pod scrapes, the Kyverno v1.19.1 and
OTel SDK sources; a re-runnable drive script) and Cursor Grok 4.6 (ask mode: the record against the
research and the Kyverno source, no cluster). Codex was not run — nothing here is code, and Grok's seat
covered the source reading.

| # | Claim | Grok | OB3 | Decision |
|---|---|---|---|---|
| M1 | What is served, the controllers' flags | PLAUSIBLE (no cluster) | CONFIRMED but the background controller's `--enableReporting` was misquoted (`validate,mutate,mutateExisting,imageVerify,generate`), `--maxBackgroundReports` is a flag of both controllers set on neither, and `kyverno.io` also serves `policyexceptions` | **Accepted**, corrected. |
| M2 | The reports and results | REFUTED — 9 CEL results, not 6; `rule: None` is a missing key, not the wire | REFUTED, the same, plus: two of the four legacy policies produce all 667 results and the two Group-matching ones can never report (the reports controller lacks RBAC on `groups.user.openshift.io`, 20 log lines) — a page state; "removed in 1.20" unsourced; the drift since the dump 0 in counts, 221 timestamps re-stamped by the hourly scan | **Accepted**, all corrected; the RBAC-gap state added to §2. |
| M3 | Finding 10's cause | REFUTED — the generator's own word is `not enabled`, not the CEL | REFUTED, the same, from the object's status and `generate-vap.go:76-89`; and a generated policy reports under the VAP alone (`vpol-<name>`), never under both — the merged 09-19 record (PR #205) had probed exactly this and was not cited | **Accepted**: §3 rewritten; the 09-19 record indexed and cited. A forensic failure on my side: the docs index was not grepped before writing. |
| M4 | The breaker | PLAUSIBLE (no scrape) | CONFIRMED with the OTel SDK's code for the lazy export; three circuits on three endpoints; `resource_namespace` IS a label on three Kyverno families | **Accepted**: §4 rewritten; the module scrapes every endpoint named and copies no namespace label. |
| M5 | What it settles | REFUTED — `KyvernoDeletingPolicy` does not exist; the store key loses `source` | REFUTED, the same, with the four constants of `source.go`, the two admission-policy sources, the `namespace/name` policy string and the resource UID | **Accepted**: §5 rewritten; the module's `CEL_SOURCES`, `GENERATED_SOURCES` and the store key follow it. |
| N1 | (OB3) the measurement time misstated | — | REFUTED (the dumps are stamped 05:57 CDT) | **Accepted**. |
