# Review — PR #93, D2: per-cluster authorization for the multi-cluster case

Adversarial second-opinion pass, 2026-09-13, on the twelve-claim brief for #93
(`docs/specs/SPEC_D2_per_cluster_authorization.md` applied as amended by its orchestrator's notes,
deviations 1–8; application 0.19.0, chart 0.21.0). Codex (gpt-5.6-sol, xhigh) and Cursor (Grok 4.6 high
fast, ask mode) review the head after the first CRC deploy; every verdict is re-checked here before a
decision, and every accepted finding comes with a test that failed before its change.

## Live run on the reference cluster

Head 05cbf3f (the spec applied, the release bump), deployed by `release-crc.sh` with `environments/crc.yaml`
unchanged — one cluster — then upgraded three times with a second entry, `prod-east`, pointing at the same API
with the pod's own token (Helm never merges lists, so the whole list travels, the chart's default entry first):

| Measured | Value |
|---|---|
| startup | `INFO gsd.api prod-east: per-cluster visibility policy self-only, identity none` — once |
| `/api/whoami`, kubeadmin | `scope: all`; `clusters: {crc-local: {inherit, same-as-host, all}, prod-east: {self-only, none, self}}` — §D2.8's expected shape byte for byte |
| `/api/clusters` rows | `crc-local {inherit, all}`, `prod-east {self-only, self}` |
| person-scoped views on prod-east | `groups` → 403 with the §11 sentence; `bindings/findings` → 403; `groupsyncs` → 200; the host's `groups` → 200 |
| `/api/alerts` | `scope: self` — the narrowest served; administrator-tier kinds from `crc-local` only |
| prod-east `hidden` | `{"detail":"unknown cluster 'prod-east'"}` and `{"detail":"unknown cluster 'no-such'"}` — the same 404; absent from `/api/clusters`, `/api/whoami` and `/api/alerts`; still 37 series on `/metrics` |
| `remote-sar` without `same-as-host` | refused at render: `needs identity: same-as-host` |
| **found by the check** | with `--set clusters[1].…` on a values file that does not define the list, Helm pads index 0 with `null` and `gsd.validateClusters` died on a Go nil pointer (`nil pointer evaluating interface {}.name`); fixed in daa39a9 — the guard refuses a non-map entry by index and names the remedy; a chart test pins the padded case (deviation 8) |
| restoring one cluster | the first attempt failed on the chart's post-upgrade `auth-loglevel` hook exceeding `activeDeadlineSeconds`; re-measured with the hook pod watched: `Pending / Unschedulable` for 70 s on the node at 95 % CPU requests, then scheduled, ran 10 s ("already Normal — nothing to do"), upgrade complete. A lab-capacity condition, the same class as the C3 run's `Insufficient cpu`, not a code path |
| after | release `deployed`, both pods `Running`, `/api/whoami` names `crc-local` only; the store keeps `prod-east`'s row, as `Settings.cluster_policy`'s docstring states (a data decision, not a tier one) |

## Verdicts — Cursor

_(pending)_

## Verdicts — Codex

_(pending)_
