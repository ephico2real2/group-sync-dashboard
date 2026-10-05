# Review record — release-crc.sh's Argo mode, the Helm↔Argo handover and `--values` (#212, PR #216)

Branch `feat/212-release-crc-argocd`, base `main`. Head reviewed: `7deba92` (the branch moved on under
the pass — `e65f245` Codex's and Grok's findings, `ed6341e` OB3's). Three reviewers on one brief of ten
claims (`review_brief_212b.md` in the session scratchpad; restated in the table): Grok 4.6 (Cursor, ask
mode — from the source, no shell), Codex (GPT-5.6, xhigh — the script traced under `bash -x` with the
cluster stubbed, `oc patch --local` for every patch document, a fixture repository for the dirty
exemption, a broken remote for the fetch), OB3 (Opus 5 — 26 stubbed invocations, the Application's own
history, the application-controller log and the kube-apiserver audit log for the waiter's race, the
Argo CD v3.4.7 and apimachinery v0.35 sources). Every verdict was re-checked on the branch and, where it
touched the cluster, measured on CRC. Line numbers are those of `7deba92`.

## Claims × reviewers × decision

| # | Claim | Grok | Codex | OB3 | Re-check / decision |
|---|---|---|---|---|---|
| M1 | The parser handles every matrix row | CONFIRMED; N1 `--values --argocd` eats the flag | REFUTED — the same | REFUTED — the same, plus `--argocd main --build-only` runs a cutover with nothing built, `--build-only --argocd` ignores the flag, `--argocd -x` takes `-x` as the revision | **Accepted (`e65f245`, `ed6341e`).** An option after `--values` is refused; `--build-only` combines with `--allow-dirty` only; a revision never starts with `-`. Tests: `test_values_does_not_consume_an_option`, `test_build_only_refuses_argocd_and_values_and_a_dash_revision_is_not_one`. |
| M2 | The two values paths (`-f` absolute; `valueFiles: [../../X]`) | CONFIRMED | REFUTED on a `"` in the filename | CONFIRMED | Holds. **Codex's finding rejected** — not a shape the script documents and it failed loudly; moot since the document is `json.dumps`-built (`e65f245`). |
| M3 | The dirty exemption: the named file only, not under `local-development/` | CONFIRMED; N2 the pattern is a regex | REFUTED — `crc_yaml`/`crcXyaml` exempted by `.`, a quoted path with a space missed | REFUTED — the same, measured | **Accepted (`e65f245`)** — git's own `:(exclude,top,literal)` pathspec. Test: `test_local_values_variant_is_not_dirty_but_a_lookalike_is`. |
| M4 | The Argo values checks are top-level; the fetch updates the tracking ref | CONFIRMED | REFUTED — `fetch \|\| true` accepted a stale ref with origin unreachable | PLAUSIBLE — the same, plus a single-branch clone never has `refs/remotes/origin/<branch>` | **Accepted (`e65f245`, `ed6341e`)** — the fetch is fatal, by `refs/heads/<branch>`, read from `FETCH_HEAD`, before the Helm release goes. Tests: `test_argocd_branch_fetch_failure_is_fatal`, `test_argocd_branch_works_in_a_single_branch_clone`. |
| M5 | The JSON patches and `oc apply`'s reset of `valueFiles` | **REFUTED — apply keeps a patched `valueFiles`** | CONFIRMED (docs; every patch run through kubectl's library) | PLAUSIBLE — the documents apply on both live states; the fallback hides a real failure | **Grok's verdict rejected on measurement**: run D (03:00Z) showed `valueFiles` back at `crc.yaml` after a `crc-info.yaml` run, and kubectl's apply sets file fields that differ from the *live* object. **The fallback finding accepted** — moot: the Application is written once now (N1 below). |
| M6 | The waiter's `comparedTo` guard | PLAUSIBLE | REFUTED — a symbolic `main` that did not change while main moved satisfies the guard with the old status | REFUTED "measured on the cluster" — run D | **Codex accepted (`e65f245`)**: the caller passes the expected commit and `status.sync.revision` must match, prefix either way (both forms observed live); a refresh annotation follows the write. **OB3's evidence re-read**: run D ran at `3a9c2be`, the *pre-guard* waiter; the guard was added in `7deba92` and printed `(status is for the previous spec)` on every run since (03:02:50Z, 03:44:49Z). Its neighbour case (a consistent pre-write document) cannot occur after the write returns — the read is linearizable — but the same-branch case is real and is what the expected revision closes. Tests: `test_waiter_rejects_a_status_computed_for_the_previous_spec`, `test_waiter_matches_the_expected_commit_by_prefix_either_way`, `test_argocd_branch_clears_the_image_parameters_and_waits_for_its_commit`. |
| M7 | The handovers; the PVCs and the minted Secrets survive | CONFIRMED (templates) | PLAUSIBLE (its sandbox could not reach the API) | CONFIRMED (live RVs) | Holds — rv `643531`/`643532` unchanged through eleven handovers tonight. OB3's "observed, not pursued": a sync mid-run during the Helm-mode delete — **taken (`ed6341e`)**, a bounded wait for `operationState.phase != Running`. |
| M8 | Image reuse without rebuilding; `-dirty` never reused | REFUTED — it rebuilds first, only the dashboard tag gates both pushes | REFUTED — the same; 10-hex collision odds 4.4×10⁻⁷ per pair | REFUTED — the same | **Accepted (`e65f245`)** — both tags checked before building; both present → no build; one present → both rebuilt and pushed (same commit, same source). Codex's per-image partial push rejected as more than needed. Tests: `test_both_tags_present_means_no_build_and_no_push`, `test_one_tag_missing_rebuilds_and_pushes_both`. |
| M9 | The matrix rows match the code | REFUTED — `--build-only` never pushed | REFUTED — the same, the `--values` row's restriction, the branch path's missing in-pod check | REFUTED — the same, plus the branch path never checked the branch existed, the values file was checked after the builds | **Accepted (`e65f245`, `ed6341e`)** — rows corrected; the values file is checked before any build; the branch is resolved before `helm uninstall`. Tests: `test_the_matrix_rows_match_the_script`, `test_a_missing_helm_values_file_is_refused_before_any_build`. |
| M10 | `set -e` safety, portability | CONFIRMED | REFUTED — a failed `oc` ends the process substitution before its echo; the waiter dies silently | REFUTED — the same, measured (`W6`: exit 1, both streams empty) | **Accepted (`e65f245`, `ed6341e`)** — the pipeline may fail; the line reads "application status unavailable: <oc's error>". Test: `test_waiter_survives_an_unavailable_api`. |
| N1 | Apply-the-file-then-patch: two writes | N4 (the hidden fallback) | CONFIRMED — the controller can sync the file's `main` with the published image in between | N2 — **measured in the live history**: run B entry 0 = `main` with no parameters (the published image) deployed for 15 s; run D entry 2 = `main` with the previous image | **Accepted (`e65f245`)** — one write: `oc patch --local` merges the revision, the image parameters and the values file into the committed file; `oc apply -f -` once. Test: `test_argocd_writes_the_application_once_with_everything_in_it`. |
| N1 (OB3) | The Helm-mode probe reads any `oc` failure as "no Application" | — | — | REFUTED — Helm would install under an Application whose selfHeal undoes it | **Accepted (`ed6341e`)** — only NotFound means absent. Test: `test_helm_mode_probe_accepts_only_notfound_as_absent`. |
| N5 (Grok) | No `--request-timeout` on the `oc` calls | N5 | — | — | **Rejected** — no hang has been measured; the waiter has its own timeout. |

## Measured on CRC after the fixes

- `e65f245`, `--argocd`: first read `03:44:49Z Synced Healthy Succeeded (status is for the previous spec) (revision 7deba92ebc, want e65f245e3e)` — both guards at once; the sync ran 03:45:05→03:45:35Z; `running : e65f245e3e — verified in-pod`. Second run on the same commit: `reused … both images … not building`, the waiter accepted the unchanged, current, correct-revision status at 03:45:42Z.
- `ed6341e`: the Helm handover (the probe, the wait for a running operation, the delete, the install) and `--argocd` back — recorded on PR #216.
- `local-development/tests/test_release_crc.py` (20): 9 fail on `7deba92`'s scripts, 5 more on `e65f245`'s, 20 pass on the head.

## What the pass changed in the tooling

The scripts are now driven end to end in tests — a temporary repository with an `origin`, stub
`oc`/`podman`/`helm` logging every call — which is what every reviewer had to build for itself. OB3's
audit-log reading is the method for any future "the waiter said X but the cluster did Y": the
kube-apiserver audit log carries every read and write with its timestamp, and the controller log says
when the comparison was made.
