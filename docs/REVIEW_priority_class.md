# Review — priorityClassName on both Deployments (PR #145, #97)

The feature was **generated and verified by Codex** (gpt-5.6-sol, xhigh) in an isolated copy — baseline
`3 failed / 1 passed` → `4 passed`, plus `299 passed` on the full chart suite, `helm lint`, and a raw
render matrix — then applied here and re-verified. **Cursor Fable-high** (`claude-fable-5-thinking-high`,
ask mode) was the independent reviewer on the applied head. One reviewer here, by design: Codex was the
generator, so its own verification is not an independent pass; Fable is.

## Claims × verdicts

| Claim | Verdict |
|---|---|
| C1 rendered only when set, correct pod, independent | **CONFIRMED** (4 renders, per-Deployment) |
| C2 behaviour-preserving | **REFUTED → F2** (the report pod rolls on a defaults-only upgrade) |
| C3 scalar quoting | **REFUTED → F1** (a legal YAML-hostile name breaks the manifest) |
| C4 gate + doc consistency | **CONFIRMED** (0.33.0 / appVersion 0.24.0; changelog heading; 15 gate tests) |
| C5 test quality | **CONFIRMED** (fails if the guard is dropped; the default-off case is a preservation test) |
| C6 next real use | measured — both-set works; report Deployment renders by default (`reporting.enabled: true`); 2 PDBs by default; the #97 preemptions happened *with* the report PDB enabled |

## Findings

### F1 — unquoted scalar breaks legal PriorityClass names (accepted)
**Finding.** The templates emitted `priorityClassName: {{ . }}` unquoted. A PriorityClass name is a
DNS-1123 subdomain, which permits all-numeric / bool-like labels (`0600`, `0x1a`, `no`); those are YAML
1.1 int/bool literals, so unquoted they render as a number/bool and kubectl/apiserver reject them
(`cannot unmarshal number into … type string`). The #97 names (`openshift-user-critical`, …) are safe,
so the shipped case worked — but the class of breakage existed.
**Re-check.** Reproduced with `--set-string priorityClassName=0600` → rendered `384`. `{{ . | quote }}`
keeps it a string. Standard Helm practice for string scalars.
**Decision.** Accepted — `| quote` in both templates, with a `--set-string` yaml-hostile-name test.

### F2 — the values key rolls the report pod on a defaults-only upgrade (accepted)
**Finding.** `checksum/reporting` hashed `toYaml .Values.reporting`, so merely ADDING
`reporting.priorityClassName: ""` (the 0.33.0 default) changed the hash and, with `strategy: Recreate`,
rolled the report pod on a defaults-only 0.32.0→0.33.0 upgrade — killing any in-flight run, the exact
pod #97 exists to protect. The changelog's "nothing changes by default" was therefore false.
**Re-check.** Confirmed: the config checksum exists to restart the report pod when config the *process*
reads changes; `priorityClassName` is pod-spec (it rolls the pod via the template diff on its own) and
is not read by the process, so hashing it too is both redundant and the cause of the spurious roll.
`omit .Values.reporting "priorityClassName"` excludes it; measured, the defaults render's
`checksum/reporting` returns to the 0.32.0 value `38059229…`, so the upgrade no longer restarts the pod.
**Decision.** Accepted — the `omit` fix (not merely correcting the changelog), and the changelog claim
tightened to say the report pod is not rolled. A checksum-stability test guards it.

## Accepted debt
- The **chart** README row for the two keys is held by no test (`test_the_root_readme_rows_state_the_real_defaults`
  reads the *root* README only). Accurate today, unenforced.
- The checksum-of-everything design means **any** future key added under `reporting:` re-creates the
  roll unless similarly omitted — a deliberate trade for never missing a real config change.

## Outcome
The feature is correctly built and gated; the two refutations — a robustness hole on legal-but-hostile
names and an undisclosed one-time report-pod restart on upgrade — are both two-line template changes
with proven tests. 20 priority/version/defaults + 42 chart/reporting tests green, helm lint clean.
Fixes committed `0850f26`. #97's 29 preemptions in ~3h are measured, and a PriorityClass is the only
mechanism that stops them.
