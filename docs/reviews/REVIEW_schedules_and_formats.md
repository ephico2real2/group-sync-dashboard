# Review record — cluster-agnostic schedules, origin formats, enable/pause (#149 R1/R3/R4, PR #220)

Branch `feat/149-schedules-formats`, base `main`. Head reviewed: `59e8cd1` (the branch moved on under the
pass — `0f26a31` Codex's and Grok's findings, `5e3a51b` OB3's). Three reviewers on one brief of seven
claims (`review_brief_149a.md` in the session scratchpad): Grok 4.6 (Cursor, ask mode — from the source),
Codex (GPT-5.6, xhigh — the API driven in a TestClient with a two-cluster snapshot and `max_queued_runs=1`,
`_formats_env` with nine inputs, the trigger with a fake client, base and head charts rendered and parsed),
OB3 (Opus 5 — the same, plus the id loop attacked with a canned `new_run_id`, the queue measured with the
worker blocked and against nine and ten clusters, and the PR's own CI read). Every verdict was re-checked
on the branch; the live checks ran on CRC. Line numbers are those of `59e8cd1`.

## Claims × reviewers × decision

| # | Claim | Grok | Codex | OB3 | Re-check / decision |
|---|---|---|---|---|---|
| M1 | The fan-out: one run per enabled cluster, distinct ids, the shapes, 422/503 | CONFIRMED | REFUTED — ids unique within the batch only; the store's `create` overwrites silently | CONFIRMED, with the same edge and an unlistable directory as a 500 | **Accepted (`0f26a31`, `5e3a51b`)** — drawn until unique in the batch AND the store; `OSError` → 503. Tests with a rigged `new_run_id` and a file for a directory. |
| M2 | The queue on a fan-out | REFUTED — a partial 429 is the wrong contract for a Job that retries | REFUTED — the same, measured; nine clusters cannot fit the default eight | REFUTED — the same, measured with the worker blocked | **Accepted (`0f26a31`)** — a fan-out is ONE queue slot (`submit_batch`), all or nothing; the cap bounds schedules, a fleet of forty is one entry; the worker renders the batch in turn; `queued` counts runs. |
| M3 | Origin formats; the env | CONFIRMED | CONFIRMED | CONFIRMED (nine inputs) | Holds. |
| M4 | The trigger: flags, a fan-out waited whole, timeouts | CONFIRMED | REFUTED — `{"runs": []}` exited 0; the single-run stdout line changed shape | PLAUSIBLE — the same two, plus: the Job's `backoffLimit: 1` re-POSTs the whole fan-out after a 202 on any exit 1 | **Accepted** — the single-run line as it was; an empty fan-out fails the Job; **`backoffLimit: 0`** with an in-process retry only for a POST that never reached the service (three attempts; a ReadTimeout is not repeated); `--timeout 840` from the 900 s deadline (`5e3a51b`). |
| M5 | The chart: no `--cluster`/`--format` by default, suspend, the guards | REFUTED — a quoted `"false"` (`--set-string`) is truthy: no suspend, the paused schedule fires | REFUTED — the same, plus `formats: [json]` renders a `--format` argparse refuses | REFUTED — the same two | **Accepted (`0f26a31`)** — the literal word `false` (`eq (toString .) "false"`, the window's own scar); json filtered out of `--format`. |
| M6 | Behaviour preservation for a pinned schedule; the R3 upgrade consequence | CONFIRMED | CONFIRMED (the CronJob identical to 0.37.0's) | CONFIRMED; the CHANGELOG had no upgrade note | **Accepted** — the upgrade note (`5e3a51b`). |
| M7 | The docs; the DoD; the PR body | PLAUSIBLE | REFUTED — `docs/reports/README.md` taught a plural `clusters:` and called R1/R3 planned; the design docs required `--cluster` | REFUTED — the same, **and the PR's CI was red on its own fan-out tests**: `from tests.reporting_seed import …` does not resolve under CI's `pytest tests/` (no `tests` package on `sys.path`); `python -m pytest` passed locally | **Accepted** — the docs say what ships (`0f26a31`); the module's own `from reporting_seed import` (`5e3a51b`). The lesson is recorded below. |

## Measured on CRC (deployed `cb74ce1`, the stacked head with the status page)

- The three CronJobs as rendered from `environments/crc.yaml`: `nightly-namespace-access` carries no
  `--cluster` (its trigger command: `--report namespace-access --schedule nightly-namespace-access --wait
  --params-json …`), `biweekly-groups` is `suspend: true`, `quarterly-compliance` runs with its retention
  override.
- `oc create job --from=cronjob/…nightly-namespace-access`: the Job succeeded; the trigger printed
  `{"submitted": ["20260920T061631.075114Z-ede4"], "report": "namespace-access", "clusters": ["crc-local"]}`
  (the fan-out shape resolved from the snapshot) and the run `done` with `bytes: {json, html}` — no PDF,
  R3 by origin.
- Tests: `test_reporting_server` +10, `test_p2_selectors` +4, `test_chart_reporting` +5; hermetic suite
  3747 passed, 15 skipped; CI green on `5e3a51b`.

## What the pass changed in the tooling

`python -m pytest` and the bare `pytest` entry point differ in what is on `sys.path`, and CI uses the
bare one: a test that imports a sibling as `tests.x` passes locally and fails there. The files' own
convention (`from reporting_seed import …`) is the rule; a local run under the bare entry point from a
worktree imports the venv's editable `gsd` of the main checkout, not the worktree's, so CI is the proof.
