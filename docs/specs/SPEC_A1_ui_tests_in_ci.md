# SPEC A1 — Playwright UI tests in CI

| | |
|---|---|
| Programme | Feature programme 2026-09 — index and version ladder in `docs/specs/README.md` |
| Batch | A — quality |
| Release | R1 — Quality and release tooling |
| Version on release | no version change (CI and docs only) |
| Issue | [#56](https://github.com/ephico2real2/group-sync-dashboard/issues/56) |
| Status | in progress |
| Source | design agent output `a38be666b46d57784`; one message; no seam |

## How to read this spec

Everything under "Batch preamble", "Design" and "Batch closing sections" is the design agent's text,
sliced from the agent's output by heading and re-concatenated to the byte before this file was
written. It is verbatim with exactly two kinds of exception, both stated in this file: the seam
repair named in the Source row where the agent's output was cut across messages, and the citation or
name corrections listed under "Orchestrator's notes", each of which changes a reference and never a
claim. Nothing else was rewritten by hand. Implementation applies the code in "Design" exactly as
written, one file at a time, with the orchestrator's notes governing where they and the body differ;
a deviation found necessary during implementation is written back into this file in the same pull
request, with the reason, under "Orchestrator's notes".

## Orchestrator's notes

- This is the first feature to land, so its `## Unreleased` heading in `docs/CHANGELOG.md` is the one every later spec extends; where a later spec says it introduces that heading, it edits the existing one instead.
- Citation corrected: the design cited the chart README with the anchor "(no `redirectMode` key)", which nests backticks that the citation grammar (path#anchor inside one backtick span) cannot express; the anchor now cites `redirectMode`, the row's own text.

- Deviation recorded at implementation (PR for #56): the closing section says a `README.md` variables row for `CI_UI_TESTS` is "included in A2's table rewrite; if A1 lands alone, add only that row". No such table exists on main today — A2 creates it — so A1 adds no README row; the switch is documented in the local-development README's Tests section, and A2's table carries the row when it lands.

- Found in review (PR #70, C1): the body's comment "anything but the string 'false' runs the job" is not GitHub's semantics — `==`/`!=` ignore case, so `False` and `FALSE` also turn the job off. Kept as the contract (an operator who writes `False` means off); the workflow comment and the test docstrings say so. The `toJSON` comparison the reviewer proposed, which would make the switch case-sensitive, was rejected. The unset case was measured: the repository has no variables and the job ran.
- Found in review (PR #70, C4): the body's risk sentence calls Playwright 1.62 an "abi3 wheel". Measured with `pip download` for CPython 3.14 on manylinux2014: `playwright-1.62.0-py3-none-manylinux1_x86_64.whl` (platform-tagged for the bundled driver, no Python ABI), `pytest_playwright-0.8.0-py3-none-any.whl`, and `greenlet-3.2.5-cp314-cp314-manylinux2014_x86_64…whl`. Nothing compiles from source; the greenlet half of the sentence is right, the abi3 half is not.

## Batch preamble (verbatim from the design)

# Design: A1 (UI tests in CI), A2 (SBOM, signing, provenance), A3 (release preparation script)

Every claim below is grounded in a file read in this session, cited as `path#anchor`. Nothing was written.

## 0. The amended house rule, applied

Each feature is a module with one switch; the default is a judgment, and the rationale is in the comment beside the switch.

| Feature | Switch | Default | Why |
|---|---|---|---|
| A1 browser tests in CI | repository variable `CI_UI_TESTS` (`ci.yml` `ui` job, `if: vars.CI_UI_TESTS != 'false'`) | **ON** | needs no credential, no cluster, no second image; only a Chromium download. The tests already exist (`local-development/tests/test_ui.py#dash`), and a green CI that skips them is the failure `ci.yml#Unit and integration tests` names. A fork or self-hosted runner that cannot fetch browsers sets it to `false`; the `tests` matrix is byte-identical either way. |
| A2 SBOM | repository variable `SUPPLY_CHAIN_SBOM` (`publish.yml` `sbom` job) | **ON** | reads the pushed image with the same registry credential the publish job already holds; produces a workflow artifact; no identity, no publication change. |
| A2 signing + provenance (image and chart) | repository variable `SUPPLY_CHAIN_SIGNING` (`publish.yml` `attest` job, `helm.yaml` chart attestation steps) | **ON** | keyless: GitHub OIDC (`id-token: write`) needs no secret. What it needs instead is stated in the workflow comment: egress to `fulcio.sigstore.dev`, `rekor.sigstore.dev`, `tuf-repo-cdn.sigstore.dev`, and a repository that is not a fork (forks are already skipped by `publish.yml#github.repository ==`). A self-hosted runner without that egress sets it to `false`. Signing changes nothing that is published — it adds referrers beside the image and records in GitHub's store. |
| A2 interaction | modelled, not left to chance | — | `attest` `needs: [publish, sbom]` with `!cancelled()`; the SBOM is attached only when `needs.sbom.result == 'success'`, and a step says by name when it is not. SBOM off + signing on: image signed, provenance attested, no SBOM attestation. SBOM on + signing off: SBOM artifact only. Chart attestation runs only when chart-releaser will publish a NEW version (`helm.yaml` `steps.plan.outputs.new`), so a skipped version attests nothing and says so. |
| A3 release script | invocation is the switch; side effects have their own: `--no-commit` (edit only), `--pr` (open the PR, off by default) | **ON** (exists; off = nobody ran it) | a script that edits a working tree and commits to a new branch has no cluster-wide side effect and never touches `main` — the `docs/RELEASING.md#Nothing else couples them` model is preserved. |

No Helm value is added by any feature. A chart value read by nothing is exactly the debt `charts/group-sync-dashboard/README.md#redirectMode` records removing, and `local-development/tests/test_environments_readme.py#test_every_key_in_the_table_still_exists_in_the_chart` would fail a README row with no key behind it. Nothing in A1–A3 runs in a pod. So the chart README values table gains no row, and Chart.yaml is not bumped (no PR touches `charts/`), which keeps `ci.yml#Chart changes bump the chart version` green without a version move.

Repository-wide conventions relied on:

- `docs/CHANGELOG.md` heading convention `## Application X — chart Y — date` (and `## Chart X — application Y — date` for chart-led releases). None of these PRs is a release, so A1 introduces a `## Unreleased` heading that A3's script converts into the release heading. The intro paragraph says so.
- `local-development/tests/test_docs_citations.py#CITATION` — every `` `path#anchor` `` in new docs below names a substring that exists in the cited file (`.py` anchors resolve through the AST or as a substring).
- Action pins: full commit of a release tag with the version in a comment (`ci.yml#ACTION PINS`). All SHAs below were resolved with `gh api repos/<owner>/<repo>/git/ref/tags/<tag>`, annotated tags through `git/tags/<sha>`:

| Action | Tag | Commit | `runs.using` |
|---|---|---|---|
| `actions/upload-artifact` | v7.0.1 | `043fb46d1a93c77aae656e7c1c64a875d1fc6a0a` | node24 |
| `actions/download-artifact` | v8.0.1 | `3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c` | node24 |
| `anchore/sbom-action` | v0.24.2 (annotated → commit) | `3ad7283483fc7af8ff2b4ea19663c2d5ca935e26` | node24 |
| `sigstore/cosign-installer` | v4.1.2 | `6f9f17788090df1f26f669e9d70d6ae9567deba6` | composite |
| `actions/attest-build-provenance` | v4.2.2 | `4d101475d8b20a2381f78447822ac1eab6504dd8` | composite (wraps `actions/attest` v4.2.1, pinned inside) |
| `helm/chart-releaser-action` | v1.7.0 (annotated → commit) | `cae68fefc6b5f367a0275617c9f83181ba54714f` | composite |

`helm.yaml` today uses `helm/chart-releaser-action@v1.7.0` — a mutable tag, against the rule at `ci.yml#ACTION PINS`. A2 pins it and adds a test so it cannot regress.

Tool pins: Syft `v1.51.1` (the version `docs/image-vulnerability-scan.md#Tools:` measured identifying Hummingbird; latest release on 2026-09-04), cosign `v3.1.3` (latest release; the installer's own default is v3.0.6), playwright `1.62.0` + pytest-playwright `0.8.0` (the pair in the local venv that runs the suite today; pytest-playwright 0.9.0 exists and is not yet exercised locally).

Order of PRs: **A1 → A2 → A3.** A1 creates `## Unreleased`; A2 adds the pin test that A1's actions must already satisfy; A3 converts `## Unreleased` and is documented in RELEASING.md on top of A2's diagram.

---


## Design (verbatim)

## FEATURE A1 — the Playwright UI tests run in CI

### Goal and switch

A separate `ui` job in `ci.yml` runs `tests/test_ui.py` once, on Python 3.14, with pinned Playwright + Chromium, uploading screenshots and traces only on failure. Switch: `vars.CI_UI_TESTS != 'false'` (ON by default). The `tests` matrix is unchanged; `test_live_smoke.py` stays deselected everywhere because it is `pytest.mark.skipif(not CONFIG…)` on `GSD_LIVE_CONFIG` and polls a real cluster through a token (`local-development/tests/test_live_smoke.py#GSD_LIVE_CONFIG`) — a runner has neither, and a skipped-by-default file that ran would only ever report "skipped".

Design decisions, each grounded:

- **Separate job, not a matrix leg.** The matrix exists to prove the interpreter floor and ceiling (`ci.yml#BOTH ENDS, not one`); `index.html` does not vary with the interpreter. One run, on the version the Containerfile ships (`local-development/Containerfile#hi/python:3.14`), keeps the matrix fast.
- **No `--no-sandbox` config.** The diagrams job needed one for puppeteer (`ci.yml#No usable sandbox!`). Playwright launches Chromium with the sandbox off unless asked: `chromium_sandbox … Defaults to \`false\`` in the installed `playwright/sync_api/_generated.py`. So the AppArmor restriction that broke mermaid-cli does not reach it.
- **Pinning.** `playwright install` fetches the Chromium build matching the installed `playwright` package, so pinning the package pins the browser. pyproject keeps `pytest-playwright>=0.5` (`local-development/pyproject.toml#dev`) for developers; CI pins in the `run:` block with a comment saying Dependabot does not read pins there.
- **No browser cache.** The download is ~150 MB, comparable to a cache restore; `--with-deps` runs apt either way; a stale cache is one more way to test yesterday's browser. Fewer moving parts wins.
- **Failure evidence.** pytest-playwright `--screenshot only-on-failure --tracing retain-on-failure` write under its default `--output` of `test-results` (verified in the installed `pytest_playwright.py#--output`), already gitignored (`.gitignore#test-results/`). `actions/upload-artifact` v7.0.1 (node24) with `if: failure()`.
- **Flakiness controls that already exist:** `_free_port`, the `/healthz` readiness loop, `wait_for_selector`/`wait_for_function` everywhere, the `dash` fixture's `pageerror` guard with a 10 s bound (`local-development/tests/test_ui.py#dash`). A few `wait_for_timeout(300–600)` sleeps exist (`test_the_skip_link_does_not_navigate` and neighbours) — those are the flake candidates. No rerun plugin: a pass on the second try is a flake and hiding it is how a flake becomes a habit; the trace artifact is how it gets fixed.
- **Timeout** `timeout-minutes: 25` (finite, generous; locally the file runs in minutes).
- **Required?** Recommend yes, after one week of green runs. That is a branch-protection setting only the operator can change (question Q1).
- The job also runs inside `helm.yaml`'s `validate` (`helm.yaml#uses: ./.github/workflows/ci.yml`), adding a few minutes to a chart release. Accepted: a chart release validated by the browser tests is the point of calling ci.yml there.

### Files

#### `.github/workflows/ci.yml` — edit 1 (the matrix job's comment; the command is unchanged)

Old:
```yaml
      - name: Unit and integration tests
        # test_ui.py needs a Playwright browser and test_live_smoke.py needs a real cluster,
        # so both are deselected — which is why the count here is lower than a local run, and
        # why a green CI is NOT a substitute for running the UI tests before shipping a
        # front-end change. A stray backtick once blanked the whole page while the suite was
        # green, and only the browser tests could have caught it.
        #
        # No hardcoded count in this comment: the last one said "285 of 340" and was stale by
        # a hundred and fifty tests, which makes it worse than no number at all.
        run: pytest tests/ -q --deselect tests/test_ui.py --deselect tests/test_live_smoke.py
```
New:
```yaml
      - name: Unit and integration tests
        # test_ui.py is deselected HERE because it runs in the `ui` job below — once, with a
        # browser — rather than twice across this matrix, whose variable is the interpreter and
        # not the page. test_live_smoke.py is deselected everywhere: it polls a real cluster
        # through a token (GSD_LIVE_CONFIG), and a runner has neither.
        #
        # No hardcoded count in this comment: the last one said "285 of 340" and was stale by
        # a hundred and fifty tests, which makes it worse than no number at all.
        run: pytest tests/ -q --deselect tests/test_ui.py --deselect tests/test_live_smoke.py
```

#### `.github/workflows/ci.yml` — edit 2 (new job, inserted between the `tests` job and the `chart` job)

Old (anchor: the two lines that begin the `chart` job):
```yaml
  chart:
    runs-on: ubuntu-latest
```
New:
```yaml
  ui:
    # THE BROWSER TESTS, IN CI AT LAST. A stray backtick inside a template literal once blanked
    # the whole page while this workflow was green: index.html is one file with no build step
    # and no type checker, and only a browser executes it. tests/test_ui.py starts the real app
    # (uvicorn, a seeded Store, the poller off) and drives it with Playwright, and until now it
    # ran only on a laptop that remembered to run it.
    #
    # A JOB OF ITS OWN, not a third leg of the `tests` matrix. That matrix proves the interpreter
    # floor and ceiling, and the page does not change with the interpreter; once, on the version
    # the Containerfile ships, keeps the matrix fast and the evidence in one place.
    #
    # THE SWITCH: repository variable CI_UI_TESTS. Anything but the string 'false' runs the job.
    # ON by default because it needs no credential, no cluster and no second image — only a
    # Chromium download — and a green run that skips tests which exist is the failure this repo
    # keeps naming. A fork or a self-hosted runner that cannot fetch browsers sets it to false;
    # the `tests` job above is byte-identical either way.
    #
    # NO --no-sandbox CONFIG, unlike the diagrams job below. Playwright launches Chromium with
    # sandboxing OFF unless asked (chromium_sandbox "Defaults to false" in its launch options),
    # so the AppArmor user-namespace restriction that broke puppeteer never reaches it.
    #
    # NO BROWSER CACHE, deliberately. The Chromium download is ~150 MB and takes about as long
    # as restoring a cache of the same bytes, --with-deps has to run apt either way, and a stale
    # cache is one more way for a green run to have tested yesterday's browser.
    name: Browser tests (Playwright, Chromium)
    if: vars.CI_UI_TESTS != 'false'
    runs-on: ubuntu-latest
    # Finite. Locally the file runs in a few minutes; a hung browser would otherwise hold the
    # runner for the six-hour default.
    timeout-minutes: 25
    defaults:
      run:
        working-directory: local-development
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1 # v7.0.1
      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97 # v7.0.0
        with:
          # What the Containerfile ships. The page is the variable in this job, not the interpreter.
          python-version: "3.14"
      - name: Install, with the browser driver pinned
        # pyproject's dev extra says pytest-playwright>=0.5 so a developer takes what pip has.
        # CI PINS BOTH PACKAGES: `playwright install` fetches the Chromium build that matches
        # the installed playwright package, so pinning the package pins the browser — and a
        # browser that moves under a green run is a variable this job exists to remove. Move
        # the two together, by hand, after a local run of tests/test_ui.py on the new pair;
        # Dependabot reads `uses:` lines, not pins inside a run: block.
        run: |
          python -m pip install --upgrade pip
          pip install -e '.[dev]' 'playwright==1.62.0' 'pytest-playwright==0.8.0'
      - name: Install Chromium and its system libraries
        run: python -m playwright install --with-deps chromium
      - name: Browser tests
        # EVIDENCE ON FAILURE ONLY. A screenshot and a Playwright trace per failed test land
        # under test-results/ (pytest-playwright's default --output, already gitignored) and the
        # next step uploads them; a green run writes and uploads nothing. No rerun plugin: a
        # test that passes on the second try is a flake, and hiding one is how it becomes a habit.
        run: >
          pytest tests/test_ui.py -q --browser chromium
          --screenshot only-on-failure --tracing retain-on-failure
      - name: Keep the evidence of a failure
        if: failure()
        uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7.0.1
        with:
          name: ui-test-failures-${{ github.run_id }}-${{ github.run_attempt }}
          path: local-development/test-results/
          if-no-files-found: ignore
          retention-days: 7

  chart:
    runs-on: ubuntu-latest
```

#### `local-development/tests/test_ci_ui_job.py` — new

```python
"""The browser tests run in CI, in a job of their own, and the switch that turns them off is real.

WHY THIS EXISTS. `tests/test_ui.py` has guarded the page since a stray backtick blanked the whole
dashboard while CI was green — and until the `ui` job it guarded it only on whichever laptop
remembered to run it. `ci.yml` now runs the file once, with a browser, next to the interpreter
matrix. A workflow is text, so the only way to keep that true is to read the text back.

BOTH STATES ARE ASSERTED. The switch is repository variable CI_UI_TESTS; ON unless the value is
exactly 'false'. The OFF state must be the workflow as it was before the job existed — the
`tests` matrix still deselecting the browser file and the live smoke test — so an operator who
turns the job off gets yesterday's CI and not a third variant of it.
"""

from __future__ import annotations

import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
CI = REPO / ".github" / "workflows" / "ci.yml"
CONTAINERFILE = REPO / "local-development" / "Containerfile"


def _jobs() -> dict:
    return yaml.safe_load(CI.read_text())["jobs"]


def _job(name: str) -> dict:
    jobs = _jobs()
    assert name in jobs, f"ci.yml has no job {name!r}; it has {sorted(jobs)}"
    return jobs[name]


def _code(job: dict) -> str:
    """Every run: block of a job with the comment lines removed, so a negative assertion cannot
    trip on the explanation of the very thing it forbids (the trap test_publish_release_decision
    documents)."""
    body = "\n".join(s.get("run") or "" for s in job["steps"])
    return "\n".join(ln for ln in body.splitlines() if not ln.strip().startswith("#"))


def test_the_ui_job_runs_the_browser_file_with_a_browser() -> None:
    code = _code(_job("ui"))
    assert "pytest tests/test_ui.py" in code, "the ui job does not run tests/test_ui.py"
    assert "playwright install --with-deps chromium" in code, (
        "no browser is installed, so the first test would fail at launch rather than at a page"
    )
    assert "--browser chromium" in code


def test_the_switch_is_a_repository_variable_that_is_on_unless_told_otherwise() -> None:
    """ON by default: no credential, no cluster, no second image. 'false' and nothing else turns it off."""
    assert _job("ui").get("if") == "vars.CI_UI_TESTS != 'false'", (
        f"the ui job's condition is {_job('ui').get('if')!r}; it must be exactly "
        "vars.CI_UI_TESTS != 'false' so an unset variable runs the job"
    )


def test_turning_it_off_leaves_the_matrix_job_as_it_was() -> None:
    """THE OFF STATE. With CI_UI_TESTS=false nothing else may change, so the matrix job must still
    deselect both files it deselected before the ui job existed, and carry no switch of its own."""
    tests = _job("tests")
    code = _code(tests)
    assert "--deselect tests/test_ui.py" in code
    assert "--deselect tests/test_live_smoke.py" in code
    assert tests.get("if") is None, "the tests matrix must run unconditionally"
    assert tests["strategy"]["matrix"]["python"] == ["3.11", "3.14"]


def test_the_live_smoke_test_runs_in_no_job() -> None:
    """It polls a real cluster through GSD_LIVE_CONFIG, which a runner does not have. Every pytest
    invocation either names files that are not it, or names tests/ and deselects it."""
    for name, job in _jobs().items():
        for line in _code(job).splitlines():
            if "pytest" not in line:
                continue
            targets_whole_dir = re.search(r"\btests/(\s|$)", line) is not None
            if targets_whole_dir:
                assert "--deselect tests/test_live_smoke.py" in line, (
                    f"job {name!r} runs tests/ without deselecting the live smoke test:\n  {line}"
                )
            else:
                assert "test_live_smoke" not in line, f"job {name!r} names the live smoke test"


def test_the_browser_driver_is_pinned_so_the_browser_is() -> None:
    """`playwright install` fetches the Chromium that matches the installed package, so pinning
    the package is pinning the browser. A floating driver is a browser that moves under a green run."""
    code = _code(_job("ui"))
    assert re.search(r"'playwright==\d+\.\d+\.\d+'", code), "playwright is not pinned"
    assert re.search(r"'pytest-playwright==\d+\.\d+\.\d+'", code), "pytest-playwright is not pinned"


def test_the_job_uses_the_interpreter_the_image_ships() -> None:
    """Read from the Containerfile, not assumed — the same drift the tests matrix comment records."""
    shipped = re.search(r"hi/python:(\d+\.\d+)", CONTAINERFILE.read_text())
    assert shipped, "the Containerfile no longer names hi/python:<minor>; update this test with it"
    setup = [s for s in _job("ui")["steps"] if "setup-python" in (s.get("uses") or "")]
    assert len(setup) == 1
    assert str(setup[0]["with"]["python-version"]) == shipped.group(1)


def test_a_failure_leaves_evidence_and_a_green_run_leaves_none() -> None:
    job = _job("ui")
    code = _code(job)
    assert "--screenshot only-on-failure" in code
    assert "--tracing retain-on-failure" in code
    uploads = [s for s in job["steps"] if "upload-artifact" in (s.get("uses") or "")]
    assert len(uploads) == 1, "exactly one artifact upload step"
    assert uploads[0].get("if") == "failure()", "evidence is uploaded on failure only"
    assert uploads[0]["with"]["path"].startswith("local-development/test-results"), (
        "the upload must point at pytest-playwright's output directory, relative to the workspace"
    )
    assert uploads[0]["with"]["if-no-files-found"] == "ignore"


def test_the_job_cannot_hold_a_runner_for_six_hours() -> None:
    minutes = _job("ui")["timeout-minutes"]
    assert 0 < int(minutes) <= 30, f"timeout-minutes is {minutes!r}; the default is 360"
```

#### `local-development/README.md` — edit (new section before `## The image`)

Old:
```markdown
## The image

`Containerfile` builds on the Red Hat Hardened Images: `hi/python:3.14-builder` to resolve the wheel
```
New:
```markdown
## Tests

```bash
./.venv/bin/python -m pytest tests/ -q                 # everything hermetic, browser tests included
./.venv/bin/python -m playwright install chromium      # once, for tests/test_ui.py
./.venv/bin/python -m pytest tests/test_ui.py -q       # the browser tests alone
```

`tests/test_ui.py` starts the real application on a free port with a seeded store and the poller
off, then drives it with Playwright (`tests/test_ui.py#server`). Its `dash` fixture turns any
uncaught page error into an immediate failure, which is how a stray backtick that blanked the whole
page was found. CI runs the file in a job of its own (`.github/workflows/ci.yml#ui`), on the
interpreter the image ships, with the Playwright package pinned so the browser is; screenshots and
traces are uploaded only when a test fails. Repository variable `CI_UI_TESTS=false` turns that job
off — for a fork or a runner that cannot download browsers — and leaves every other job as it is.

`tests/test_live_smoke.py` is the one file no CI job runs: it needs a cluster. See below.

## The image

`Containerfile` builds on the Red Hat Hardened Images: `hi/python:3.14-builder` to resolve the wheel
```

#### `docs/RELEASING.md` — edit

Old:
```text
        |   ci.yml:  tests(3.11) · tests(3.14) · chart · diagrams · image
```
New:
```text
        |   ci.yml:  tests(3.11) · tests(3.14) · ui · chart · diagrams · image
```

#### `docs/CHANGELOG.md` — edit (intro sentence and the `Unreleased` section)

Old:
```markdown
`appVersion` is listed under the application release it carries. The reasoning behind each change
lives next to the code and in the design and review records linked here.

## Application 0.11.0 — chart 0.10.0 — 2026-09-04
```
New:
```markdown
`appVersion` is listed under the application release it carries. The reasoning behind each change
lives next to the code and in the design and review records linked here. Changes merged since the
last release sit under `## Unreleased` until the release that carries them replaces that heading.

## Unreleased

- **The browser tests run in CI.** `tests/test_ui.py` — the real app on a free port, a seeded store,
  Playwright against it — now runs in a `ui` job of its own on every pull request and push, on the
  interpreter the image ships, with the Playwright package pinned so the Chromium build is too.
  Screenshots and traces are kept as a workflow artifact only when a test fails. Repository
  variable `CI_UI_TESTS=false` turns the job off and leaves the interpreter matrix exactly as it
  was; `test_live_smoke.py` still runs nowhere but against a cluster you name.

## Application 0.11.0 — chart 0.10.0 — 2026-09-04
```

### Verification (A1)

```sh
cd local-development && .venv/bin/python -m pytest tests/test_ci_ui_job.py -q
# expected: 8 passed
.venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py
# expected: the same pass count as before plus 8; no failures
.venv/bin/python -m pytest tests/test_docs_citations.py -q     # the new `tests/test_ui.py#server` and `ci.yml#ui` citations resolve
python3 -c "import yaml;yaml.safe_load(open('.github/workflows/ci.yml'))"   # parses
```
On the PR: the checks list shows `Browser tests (Playwright, Chromium)` green; the run log's "Browser tests" step ends with `N passed` where N is what `pytest tests/test_ui.py -q` prints locally. To prove the OFF state once: set `CI_UI_TESTS=false` under Settings → Secrets and variables → Actions → Variables, re-run — the job shows as skipped and every other job is unchanged; then delete the variable.

### Risks and how they close

- Playwright 1.62 wheel on Python 3.14 (abi3 wheel; greenlet ≥3.2 ships 3.14 wheels). If the install step fails, the failure is at `pip install`, visible, and the fix is the pin pair (never a silent skip).
- The fixed sleeps in `test_ui.py` (`wait_for_timeout`) may flake under runner load; the trace artifact names the test, and the fix is a `wait_for_function` in that test — not a rerun.
- The job runs in `helm.yaml`'s validate too; a flaky UI test would block a chart release. Accepted; the trace makes it a five-minute fix.

---


## Batch closing sections (verbatim)

## Order of PRs and what each needs from the operator

1. **A1** — `ci.yml`, `test_ci_ui_job.py`, `local-development/README.md`, `RELEASING.md` (one line), `CHANGELOG.md` (intro + `## Unreleased`), `README.md` variables row for `CI_UI_TESTS` (included in A2's table rewrite; if A1 lands alone, add only that row). No `charts/` change, no version bump.
2. **A2** — build script, `publish.yml`, `helm.yaml`, `test_supply_chain.py`, `test_workflow_pins.py`, `HELM_DOWNLOAD_AND_INSTALL.md`, `DESIGN_supply_chain.md`, `RELEASING.md`, `README.md`, `image-vulnerability-scan.md`, `CHANGELOG.md`. Merging it fires `publish.yml` (paths include the script and the workflow), which is the first signed image. No `charts/` change.
3. **A3** — `prepare-release.py`, `test_prepare_release.py`, `RELEASING.md`, `local-development/README.md`, `CHANGELOG.md`. The next real release then converts `## Unreleased`.

## Questions only the operator can answer

- **Q1 (A1):** make `Browser tests (Playwright, Chromium)` a required check under branch protection after a week of green runs? (a Settings change, not a repository file).
- **Q2 (A2):** which cosign major do consumers run? The workflow signs with cosign 3.1.3 in its default bundle layout and proves the round trip against Quay in-run; if a consumer population on cosign 2.x must verify, `cosign sign --new-bundle-format=false` is the one-flag change and the install guide would say "cosign 2.x or newer".
- **Q3 (A2):** is a public Rekor entry per push acceptable? It names the repository, the workflow file and the digest — nothing else — and is the property that makes keyless verifiable offline.
- **Q4 (A2):** should the quay robot account's token be scoped to allow pushing referrer artifacts (`sha256-<digest>.sig` / `.att` tags)? A write-scoped robot already can; a tag-restricted one would fail the sign step visibly.

### Critical Files for Implementation

- `/Users/olasumbo/gitRepos/group-sync-dashboard/.github/workflows/ci.yml`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/.github/workflows/publish.yml`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/.github/workflows/helm.yaml`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/build-and-push-external.sh`
- `/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/prepare-release.py` (new; conventions it edits live in `/Users/olasumbo/gitRepos/group-sync-dashboard/charts/group-sync-dashboard/Chart.yaml` and `/Users/olasumbo/gitRepos/group-sync-dashboard/docs/CHANGELOG.md`)
