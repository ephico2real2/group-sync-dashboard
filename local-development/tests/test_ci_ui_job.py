"""The browser tests run in CI, in a job of their own, and the switch that turns them off is real.

WHY THIS EXISTS. `tests/test_ui.py` has guarded the page since a stray backtick blanked the whole
dashboard while CI was green — and until the `ui` job it guarded it only on whichever laptop
remembered to run it. `ci.yml` now runs the file once, with a browser, next to the interpreter
matrix. A workflow is text, so the only way to keep that true is to read the text back.

BOTH STATES ARE ASSERTED. The switch is repository variable CI_UI_TESTS; ON unless the value is
'false' — in any letter case, because GitHub ignores case when comparing strings, so an operator
who writes False gets off, which is what they meant. The OFF state must be the workflow as it was before the job existed — the
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
    """ON by default: no credential, no cluster, no second image. Only the value false, in any letter
    case, turns it off; an unset variable is the empty string and runs the job (measured: the first run
    of this job was on a repository with no variables at all)."""
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
