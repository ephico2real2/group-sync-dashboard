"""The publish workflow's pin step, replayed against the collision that broke it.

WHAT WENT WRONG, TWICE. The `publish` run failed in "Pin the published tag on main" on 2026-08-09
and again on 2026-08-10, both times with

    CONFLICT (content): Merge conflict in charts/group-sync-dashboard/values.yaml
    error: could not apply e2c8b3d... chore(chart): pin image tag 0.6.0-d5d1959d47

The step used to commit the pin and then `git pull --rebase`, on the stated premise that "this
commit touches one line nobody else edits". The PREVIOUS publish run edits exactly that line, so
the contended case is two publishes rather than two humans, and rebase had nothing to go on.

NOT A CONCURRENCY BUG, which matters for what the tests have to model. The workflow's
`concurrency: publish-main` group does serialize: both times, the second job started after the
first had finished (2026-08-09 05:42:22 versus 05:42:13; 2026-08-10 16:32:04 versus 16:32:01). The
problem is the CHECKOUT — actions/checkout takes github.sha, the triggering commit, not the branch
tip — so the second run is always sitting on a commit that predates the first run's pin.
Serialization makes that reliable rather than rare. The tests below therefore run the two publishes
in sequence, not in parallel.

WHY A TEST AND NOT A COMMENT. It needs two merges close together, so it passes every time you try
it by hand and fails only in the situation that matters. And the cost is quiet: the image is pushed
to the registry before this step runs, so a red run loses only the pin and main keeps pointing at
the PREVIOUS image. `0.6.0-6f88f2a9aa` from 2026-08-09 appears in no commit in this repository —
built, pushed, never referenced. The 2026-08-10 case was covered up by a third merge landing after
it; had either been the last push, the chart would deploy code one merge behind with nothing but a
failed workflow to say so.

These tests read the step out of the real YAML rather than restating it, so editing the workflow
re-tests the workflow. They run bash and git in a throwaway sandbox — no network, no registry, no
cluster; the "image build" is simply a rewritten tag line, because the tag is the only thing the
pin step consumes.
"""

from __future__ import annotations

import pathlib
import re
import subprocess

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "publish.yml"
CHART = "charts/group-sync-dashboard"
VALUES = f"{CHART}/values.yaml"
CHART_YAML = f"{CHART}/Chart.yaml"


def pin_step() -> str:
    """The `run:` body of the pin step, taken from the workflow that will actually run."""
    workflow = yaml.safe_load(WORKFLOW.read_text())
    steps = workflow["jobs"]["publish"]["steps"]
    matched = [s for s in steps if s.get("name") == "Pin the published tag on main"]
    assert len(matched) == 1, f"expected one pin step, found {len(matched)}"
    return matched[0]["run"]


# Isolated from the developer's own git config: a global hooksPath or commit.gpgsign would
# otherwise reach into the sandbox and fail the run for reasons that have nothing to do with the
# step under test.
GIT_ENV = {
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_TERMINAL_PROMPT": "0",
    "HOME": "/nonexistent",
    "PATH": "/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin",
    # The step reads these; GitHub sets them on every run.
    "GITHUB_SHA": "deadbeefcafe",
    "REGISTRY": "quay.io",
    "REGISTRY_NAMESPACE": "ephico2real",
}


def git(cwd: pathlib.Path, *args: str) -> str:
    done = subprocess.run(
        ["git", *args], cwd=cwd, env=GIT_ENV, capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, f"git {' '.join(args)} failed:\n{done.stdout}\n{done.stderr}"
    return done.stdout


def write_tag(values: pathlib.Path, tag: str) -> None:
    """Stand in for build-and-push-external.sh --update-values, which rewrites just this line."""
    text = values.read_text()
    new, count = re.subn(r'(?m)^(  tag: ).*$', rf'\1"{tag}"', text)
    assert count == 1
    values.write_text(new)


def tag_of(values_text: str) -> str:
    found = re.search(r'(?m)^  tag: "(.+?)"$', values_text)
    assert found, f"no tag line in:\n{values_text}"
    return found.group(1)


def chart_version_of(chart_text: str) -> str:
    """The chart's own version, read the way chart-releaser reads it: column zero."""
    found = re.search(r"(?m)^version: (\d+\.\d+\.\d+)[ \t]*$", chart_text)
    assert found, f"no version line in:\n{chart_text}"
    return found.group(1)


def app_version_of(chart_text: str) -> str:
    found = re.search(r'(?m)^appVersion: "(.+?)"[ \t]*$', chart_text)
    assert found, f"no appVersion line in:\n{chart_text}"
    return found.group(1)


class Sandbox:
    """A bare origin, a seed clone that plays "other people merging", and per-run checkouts."""

    def __init__(self, root: pathlib.Path) -> None:
        self.root = root
        self.origin = root / "origin.git"
        self.seed = root / "seed"
        git(root, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(root, "clone", "-q", str(self.origin), str(self.seed))
        (self.seed / CHART).mkdir(parents=True)
        (self.seed / VALUES).write_text(
            'image:\n  repository: quay.io/x/y\n  tag: "0.6.0-BASE000000"\n'
        )
        # Chart.yaml is seeded because the step now bumps it, and it carries two decoys the real
        # file's shape makes possible: `appVersion` ends in `version:` and an indented comment can
        # mention one. Both must survive, so the anchor is proven to be column zero and not a
        # substring match.
        (self.seed / CHART_YAML).write_text(
            "apiVersion: v2\n"
            "name: group-sync-dashboard\n"
            "  # version: 9.9.9 — an indented decoy; the bump must not touch it\n"
            "version: 0.4.0\n"
            'appVersion: "0.6.0"\n'
        )
        (self.seed / "src").mkdir()
        (self.seed / "src" / "app.txt").write_text("base\n")
        self._commit(self.seed, "C0")
        git(self.seed, "push", "-q", "origin", "main")

    def _commit(self, where: pathlib.Path, message: str) -> None:
        git(where, "add", "-A")
        git(where, "-c", "user.email=t@t", "-c", "user.name=t", "-c", "commit.gpgsign=false",
            "commit", "-qm", message)

    def merge(self, filename: str) -> str:
        """Someone else's PR lands on main. Returns the new tip."""
        git(self.seed, "fetch", "-q", "origin", "main")
        git(self.seed, "reset", "-q", "--hard", "FETCH_HEAD")
        (self.seed / "src" / filename).write_text(filename)
        self._commit(self.seed, f"merge {filename}")
        git(self.seed, "push", "-q", "origin", "main")
        return git(self.seed, "rev-parse", "HEAD").strip()

    def runner(self, name: str, at_sha: str, tag: str) -> pathlib.Path:
        """A publish run: a checkout at the pushed sha, with the built tag already written in."""
        path = self.root / name
        git(self.root, "clone", "-q", str(self.origin), str(path))
        git(path, "checkout", "-q", at_sha)
        git(path, "config", "user.email", "r@t")
        git(path, "config", "user.name", "r")
        git(path, "config", "commit.gpgsign", "false")
        write_tag(path / VALUES, tag)
        return path

    def run_step(self, path: pathlib.Path) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", "-c", pin_step()], cwd=path, env=GIT_ENV,
            capture_output=True, text=True, check=False,
        )

    def on_main(self, path: str) -> str:
        git(self.seed, "fetch", "-q", "origin", "main")
        return git(self.seed, "show", f"FETCH_HEAD:{path}")

    def main_log(self) -> str:
        git(self.seed, "fetch", "-q", "origin", "main")
        return git(self.seed, "log", "--oneline", "FETCH_HEAD")


@pytest.fixture()
def sandbox(tmp_path: pathlib.Path) -> Sandbox:
    return Sandbox(tmp_path)


def test_two_runs_colliding_on_the_tag_line_both_succeed(sandbox: Sandbox) -> None:
    """The observed failure itself: two merges close together, one contested line.

    Run B is checked out at its own trigger commit, which predates run A's pin — the real
    arrangement, since the concurrency group means A has already pushed by the time B starts. Note
    the two steps run in SEQUENCE here, because that is what actually happens.

    Before the fix, run B committed its pin and rebased onto run A's, hit `CONFLICT (content)` on
    values.yaml, and exited 1 — leaving main pinning run A's OLDER image while run B's image sat in
    the registry with nothing pointing at it.
    """
    at_a = sandbox.merge("a.txt")
    at_b = sandbox.merge("b.txt")
    run_a = sandbox.runner("runA", at_a, "0.6.0-AAAAAAAAAA")
    run_b = sandbox.runner("runB", at_b, "0.6.0-BBBBBBBBBB")

    result_a = sandbox.run_step(run_a)
    assert result_a.returncode == 0, f"run A failed:\n{result_a.stdout}\n{result_a.stderr}"

    result_b = sandbox.run_step(run_b)
    assert result_b.returncode == 0, (
        "run B failed to pin, so main still points at run A's older image — this is the 16:31 "
        f"regression:\n{result_b.stdout}\n{result_b.stderr}"
    )
    assert "CONFLICT" not in result_b.stdout + result_b.stderr

    assert tag_of(sandbox.on_main(VALUES)) == "0.6.0-BBBBBBBBBB", (
        "main must pin the NEWEST build. Pinning the older one is the quiet half of this bug: "
        "the chart installs and runs, it just deploys code one merge behind."
    )


def test_the_pin_commit_does_not_revert_a_merge_that_landed_mid_run(sandbox: Sandbox) -> None:
    """The pin must be a one-line change against the tip, whatever the run was checked out at.

    Re-applying the tag onto the current tip needs a HARD reset. A soft one leaves the index
    describing the run's own older tree, so the commit carries a revert of everything that landed
    in between — and pushes it green. Caught while writing the fix: with `--soft`, this test's
    sandbox produced `3 files changed` and `delete mode 100644 src/c.txt`.
    """
    at_a = sandbox.merge("a.txt")
    at_b = sandbox.merge("b.txt")
    run_a = sandbox.runner("runA", at_a, "0.6.0-AAAAAAAAAA")
    run_b = sandbox.runner("runB", at_b, "0.6.0-BBBBBBBBBB")

    assert sandbox.run_step(run_a).returncode == 0
    sandbox.merge("c.txt")          # a third PR lands while run B is still building

    result = sandbox.run_step(run_b)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    for filename in ("app.txt", "a.txt", "b.txt", "c.txt"):
        sandbox.on_main(f"src/{filename}")   # raises if the pin commit deleted it

    head = git(sandbox.seed, "show", "--stat", "--oneline", "FETCH_HEAD")
    assert "2 files changed" in head, (
        "the pin commit must touch values.yaml and Chart.yaml and NOTHING else — two, because the "
        "tag and the chart version have to move together or the new pin is never published; more "
        f"than two means the reset regressed and the commit is carrying somebody's merge:\n{head}"
    )
    assert "src/" not in head, f"the pin commit reached outside charts/:\n{head}"


def test_a_rerun_of_an_already_pinned_tag_commits_nothing(sandbox: Sandbox) -> None:
    """Re-running the same commit is not an error and must not add an empty pin commit.

    The tag embeds the git sha, so an identical tag means identical source. Worth holding: a step
    that committed anyway would push a no-op commit to main on every re-run, and each of those
    would need the `[skip publish]` marker to avoid triggering the workflow again.
    """
    at_a = sandbox.merge("a.txt")
    run = sandbox.runner("runA", at_a, "0.6.0-AAAAAAAAAA")
    assert sandbox.run_step(run).returncode == 0
    before = sandbox.main_log()

    again = sandbox.runner("runA2", at_a, "0.6.0-AAAAAAAAAA")
    result = sandbox.run_step(again)
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert sandbox.main_log() == before, "a re-run must not add a second pin commit"


def test_losing_the_push_race_repeatedly_fails_loudly(sandbox: Sandbox) -> None:
    """Exhausting the retries must be a red run, not a silent skip.

    The image is already in the registry by this point, so an unpinned chart is a real
    inconsistency and the only place it can be reported is this step's exit code.
    """
    at_a = sandbox.merge("a.txt")
    run = sandbox.runner("runA", at_a, "0.6.0-LOSER00000")

    # A pre-push hook that advances origin every time, so no attempt can ever fast-forward.
    hook = run / ".git" / "hooks" / "pre-push"
    hook.write_text(
        "#!/usr/bin/env bash\n"
        f'cd "{sandbox.seed}" && '
        'git -c user.email=t@t -c user.name=t -c commit.gpgsign=false '
        'commit -q --allow-empty -m "competing merge" && git push -q origin main\n'
    )
    hook.chmod(0o755)

    result = sandbox.run_step(run)
    assert result.returncode == 1, (
        f"exhausting the retries must fail the job:\n{result.stdout}\n{result.stderr}"
    )
    assert "::error::" in result.stdout, "the failure must say the image is published but unpinned"
    assert tag_of(sandbox.on_main(VALUES)) != "0.6.0-LOSER00000"


def test_the_step_does_not_rebase_the_pin_commit(sandbox: Sandbox) -> None:
    """A guard on the APPROACH, because the behavioural tests above cannot see a near-miss.

    `git pull --rebase` is what produced the conflict: it asks git to reconcile two edits to the
    same line when nothing in the history says which should win. Re-applying the tag onto the
    fetched tip has no divergent commit to reconcile. If someone reintroduces a rebase here, the
    collision comes back — and only under a timing window that hand-testing will not reproduce.
    """
    body = pin_step()
    code = "\n".join(line for line in body.splitlines() if not line.strip().startswith("#"))
    assert "--rebase" not in code, (
        "the pin step must not rebase its own commit onto main; write the tag onto the fetched "
        "tip instead (see this file's docstring for the failure it caused)"
    )


# ── The published chart must carry the image the pin commit just built ────────────────────
#
# THE DEFECT THESE EXIST FOR SHIPPED A DATA EXPOSURE. Measured on this repository on
# 2026-08-12, straight off the live Helm repo:
#
#     published chart 0.4.0   image.tag  "0.6.0-424b3fdd63"      <- #31's merge
#     main                    image.tag  "0.6.0-d0c0edaeea"      <- #33's merge
#
# so `helm install group-sync-dashboard/group-sync-dashboard` deployed an image without the
# wide-tier threshold fix (#32) AND without the self-tier projection (#33) — the latter being
# what stops a narrowed reader receiving directory DNs. Two causes, both needed:
#
#   1. chart-releaser skips a version it has already released, so rewriting image.tag under an
#      unchanged `version:` publishes nothing and reports success.
#   2. a push made with GITHUB_TOKEN does not trigger workflows at all, so the pin commit could
#      not have published the chart even with a bump.
#
# The fix pairs a patch bump with every pin and then dispatches Release Charts explicitly.
# These hold that pairing, because nothing else can: a stale published chart installs cleanly,
# runs, passes its probes, and serves the wrong code.


def test_the_pin_commit_bumps_the_chart_patch_version(sandbox: Sandbox) -> None:
    """A new pin must arrive with a new chart version, or chart-releaser publishes nothing."""
    at_a = sandbox.merge("a.txt")
    before = chart_version_of(sandbox.on_main(CHART_YAML))
    assert before == "0.4.0"

    result = sandbox.run_step(sandbox.runner("runA", at_a, "0.6.0-AAAAAAAAAA"))
    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"

    chart = sandbox.on_main(CHART_YAML)
    assert chart_version_of(chart) == "0.4.1", (
        "the chart version did not move with the pin, so the published chart keeps serving the "
        "PREVIOUS image — install-time staleness that no test of the tag line alone can see"
    )
    assert tag_of(sandbox.on_main(VALUES)) == "0.6.0-AAAAAAAAAA"


def test_the_bump_leaves_app_version_and_indented_decoys_alone(sandbox: Sandbox) -> None:
    """Only `version:` at column zero moves.

    `appVersion` ends in the same six characters and is held to pyproject.toml by
    tests/test_chart_versions.py, so bumping it here would break that pairing and silently
    claim an application release that never happened.
    """
    at_a = sandbox.merge("a.txt")
    assert sandbox.run_step(sandbox.runner("runA", at_a, "0.6.0-AAAAAAAAAA")).returncode == 0

    chart = sandbox.on_main(CHART_YAML)
    assert app_version_of(chart) == "0.6.0", "appVersion must not move with a chart patch bump"
    assert "# version: 9.9.9" in chart, "the indented decoy was rewritten; the anchor is not ^"


def test_a_rerun_that_pins_nothing_does_not_bump_the_chart(sandbox: Sandbox) -> None:
    """The already-pinned early exit must not manufacture a chart release.

    Bumping on a no-op would publish a new chart version whose only difference from the last one
    is the number — and, worse, would do it on every re-run of the same commit.
    """
    at_a = sandbox.merge("a.txt")
    assert sandbox.run_step(sandbox.runner("runA", at_a, "0.6.0-AAAAAAAAAA")).returncode == 0
    after_first = chart_version_of(sandbox.on_main(CHART_YAML))
    log_before = sandbox.main_log()

    again = sandbox.run_step(sandbox.runner("runA2", at_a, "0.6.0-AAAAAAAAAA"))
    assert again.returncode == 0, f"{again.stdout}\n{again.stderr}"
    assert chart_version_of(sandbox.on_main(CHART_YAML)) == after_first, (
        "a re-run pinning the same tag bumped the chart anyway"
    )
    assert sandbox.main_log() == log_before


def test_sequential_publishes_each_get_their_own_chart_version(sandbox: Sandbox) -> None:
    """The bump reads the FETCHED tip, not the run's own checkout.

    This is the concurrency case that broke the tag line, applied to the version: run B is
    checked out at a commit predating run A's bump, so a version captured before the loop would
    compute 0.4.1 twice. The second push would then either collide or re-release a version
    chart-releaser has already published — the original defect, one layer down.
    """
    at_a = sandbox.merge("a.txt")
    at_b = sandbox.merge("b.txt")
    run_a = sandbox.runner("runA", at_a, "0.6.0-AAAAAAAAAA")
    run_b = sandbox.runner("runB", at_b, "0.6.0-BBBBBBBBBB")

    assert sandbox.run_step(run_a).returncode == 0
    assert chart_version_of(sandbox.on_main(CHART_YAML)) == "0.4.1"

    result_b = sandbox.run_step(run_b)
    assert result_b.returncode == 0, f"{result_b.stdout}\n{result_b.stderr}"
    assert chart_version_of(sandbox.on_main(CHART_YAML)) == "0.4.2", (
        "run B reused run A's version number, so its image is published under a chart version "
        "that already exists and chart-releaser drops it"
    )
    assert tag_of(sandbox.on_main(VALUES)) == "0.6.0-BBBBBBBBBB"


def test_a_human_minor_bump_is_respected_rather_than_overwritten(sandbox: Sandbox) -> None:
    """MINOR stays a human decision; the automation only ever adds to the third component.

    A template change that earns 0.5.0 must not be flattened back to 0.4.x by the next image
    build, which would publish the behaviour change under a version consumers read as a patch.
    """
    git(sandbox.seed, "fetch", "-q", "origin", "main")
    git(sandbox.seed, "reset", "-q", "--hard", "FETCH_HEAD")
    chart = sandbox.seed / CHART_YAML
    chart.write_text(chart.read_text().replace("version: 0.4.0", "version: 0.5.0"))
    sandbox._commit(sandbox.seed, "feat(chart): a template change worth a minor bump")
    git(sandbox.seed, "push", "-q", "origin", "main")
    at_a = git(sandbox.seed, "rev-parse", "HEAD").strip()

    assert sandbox.run_step(sandbox.runner("runA", at_a, "0.6.0-AAAAAAAAAA")).returncode == 0
    assert chart_version_of(sandbox.on_main(CHART_YAML)) == "0.5.1", (
        "the automation must build on the human's minor bump, not reset it"
    )


# ── The dispatch, which is the half a push cannot do ──────────────────────────────────────


def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text())


def dispatch_step() -> dict:
    steps = workflow()["jobs"]["publish"]["steps"]
    matched = [s for s in steps if "gh workflow run" in (s.get("run") or "")]
    assert len(matched) == 1, (
        "expected exactly one step dispatching a workflow; a pin that lands on main cannot "
        f"publish the chart by itself, so this step is load-bearing. Found {len(matched)}"
    )
    return matched[0]


def test_the_job_may_dispatch_a_workflow() -> None:
    """Without `actions: write` the dispatch is a 403 and the chart silently stops publishing."""
    perms = workflow()["jobs"]["publish"]["permissions"]
    assert perms.get("actions") == "write", (
        "publish needs actions: write to dispatch Release Charts; the pin commit cannot trigger "
        "it by pushing, because pushes made with GITHUB_TOKEN do not create workflow runs"
    )
    assert perms.get("contents") == "write", "still needs contents: write to push the pin"


def test_the_dispatch_targets_the_chart_release_on_main() -> None:
    """--ref main, not the triggering sha: the pin commit is a CHILD of github.sha.

    Dispatching at github.sha would package the chart exactly as it was before the pin — the
    original staleness, reproduced deliberately.
    """
    run = dispatch_step()["run"]
    assert "helm.yaml" in run, "the dispatch must name the chart-release workflow"
    assert "--ref main" in run, (
        "dispatch at main, not github.sha: the pin commit does not exist at the triggering sha"
    )


def test_the_dispatch_only_fires_when_a_pin_actually_landed() -> None:
    """Gated on the pin step's output, so a no-op run does not ask for a redundant release."""
    guard = dispatch_step().get("if", "")
    assert "steps.pin.outputs.pinned" in guard, (
        f"the dispatch must be conditional on the pin having landed; guard is {guard!r}"
    )
    body = pin_step()
    assert "pinned=true" in body and "GITHUB_OUTPUT" in body, (
        "the pin step must emit the output the dispatch is gated on"
    )


def test_the_pin_step_writes_both_files_it_commits() -> None:
    """A guard on the APPROACH: the two edits must be staged together, in one commit.

    Two commits would mean a window where main pins an image under a version already published —
    and if the second push lost the race, that window becomes permanent.
    """
    body = pin_step()
    added = [ln for ln in body.splitlines() if ln.strip().startswith("git add")]
    assert len(added) == 1, f"expected one `git add`, found {len(added)}: {added}"
    assert "values.yaml" in added[0] and "Chart.yaml" in added[0], (
        f"both files must be staged in the same commit as the pin; got {added[0]!r}"
    )


# ── The dispatch must wait for the ref it is about to package ──────────────────────────────
#
# THE SCAR, AND IT IS MINE FROM THE SAME DAY. The dispatch step was added to fix the published
# chart lagging main. It then lost a different race, on 2026-08-12. `gh workflow run helm.yaml
# --ref main` resolves `main` when GITHUB PROCESSES the dispatch, not when we pushed, and one run
# resolved it to the pre-push tip. The sha each Release Charts run actually packaged:
#
#   00:56  ef6d41db25  the pin commit    -> chart 0.4.1 published
#   02:18  ee99856b1c  the pin commit    -> chart 0.4.2 published
#   05:02  01d86756f4  the MERGE commit  -> published NOTHING
#   05:05  f67af3254e  the pin commit    -> chart 0.4.3, dispatched BY HAND
#
# chart-releaser packaged Chart.yaml at the merge commit, where `version:` was still the already
# released value, skipped it, and exited zero. **All four runs report `success`** — the same
# silent-green property that let the original staleness bug hide for three merges. It won twice and
# lost once, so nothing about it announces itself; the only reason it was caught is that the
# published index was checked by hand after the merge.
#
# These run the dispatch step's REAL body out of the workflow, against a sandbox origin, with a
# fake `gh` on PATH that records whether it was called — the only way to assert the thing that
# matters: on a stale ref the dispatch must NOT happen.


def run_dispatch(path: pathlib.Path, pinned_sha: str) -> tuple[subprocess.CompletedProcess, str]:
    """Run the dispatch step's body with `gh` stubbed, returning (result, recorded gh args).

    The stub records rather than refuses, because "did it dispatch?" is the assertion. A stub that
    exited non-zero would conflate "declined to dispatch" with "dispatched and failed" — the exact
    distinction these tests exist to make.
    """
    bin_dir = path / "fakebin"
    bin_dir.mkdir(exist_ok=True)
    calls = bin_dir / "gh-calls.txt"
    stub = bin_dir / "gh"
    stub.write_text(f'#!/usr/bin/env bash\nprintf "%s\\n" "$*" >> "{calls}"\n')
    stub.chmod(0o755)

    env = dict(GIT_ENV)
    env["PATH"] = f"{bin_dir}:{env['PATH']}"
    env["PINNED_SHA"] = pinned_sha
    env["GH_TOKEN"] = "stub-token-never-used"
    done = subprocess.run(
        ["bash", "-c", dispatch_step()["run"]], cwd=path, env=env,
        capture_output=True, text=True, check=False,
    )
    return done, (calls.read_text() if calls.exists() else "")


def test_the_dispatch_fires_once_the_ref_carries_the_pin_commit(sandbox: Sandbox) -> None:
    """The healthy path: origin/main IS the pin commit, so the release is dispatched for it."""
    at_a = sandbox.merge("a.txt")
    run = sandbox.runner("runA", at_a, "0.6.0-AAAAAAAAAA")
    assert sandbox.run_step(run).returncode == 0

    pinned = git(sandbox.seed, "ls-remote", "origin", "main").split()[0]
    result, calls = run_dispatch(run, pinned)

    assert result.returncode == 0, f"{result.stdout}\n{result.stderr}"
    assert calls.count("workflow run helm.yaml --ref main") == 1, (
        f"expected exactly one dispatch of the chart release; gh received:\n{calls!r}"
    )
    assert "ref converged" in result.stdout


def test_a_stale_ref_is_never_dispatched(sandbox: Sandbox) -> None:
    """THE 05:02 REGRESSION. If origin/main does not carry the pin commit, DO NOT DISPATCH.

    Dispatching anyway is what happened: chart-releaser packaged an already-released version,
    skipped, and reported success. A red run nobody can misread is strictly better than a green run
    that published nothing — so this asserts BOTH halves: `gh` untouched, and a non-zero exit
    carrying `::error::`.

    Before the fix this cannot pass: the step called `gh workflow run` unconditionally, so `calls`
    would contain the dispatch and the exit code would be 0.
    """
    at_a = sandbox.merge("a.txt")
    run = sandbox.runner("runA", at_a, "0.6.0-AAAAAAAAAA")
    assert sandbox.run_step(run).returncode == 0

    # A sha origin will never report. Stands in for the real case — a tip that has not yet caught
    # UP — because both mean the same thing here: origin/main is not the commit we are about to ask
    # chart-releaser to package.
    stale_pin = "0" * 40

    result, calls = run_dispatch(run, stale_pin)

    assert calls == "", (
        "the step dispatched a chart release for a ref that does not carry the pin commit — "
        f"chart-releaser would package a stale Chart.yaml and report success. gh got:\n{calls!r}"
    )
    assert result.returncode == 1, (
        f"a refused dispatch must fail the job, not pass quietly:\n{result.stdout}\n{result.stderr}"
    )
    assert "::error::" in result.stdout, "the refusal must be legible in the run log"
    assert "gh workflow run helm.yaml --ref main" in result.stdout, (
        "the error must tell the operator how to force the release by hand"
    )


def test_the_dispatch_consumes_the_sha_the_pin_step_published() -> None:
    """A guard on the SEAM, because the behavioural tests above supply PINNED_SHA themselves.

    The step must read the pin step's own output rather than re-deriving HEAD, which would work
    only by accident: the pin loop happens to leave HEAD on the pin commit, and nothing states
    that. Rename this seam on one side only and PINNED_SHA is empty, the comparison never matches,
    and every publish ends in the refusal path above — loud, but wrong.
    """
    step = dispatch_step()
    assert step.get("env", {}).get("PINNED_SHA") == "${{ steps.pin.outputs.pinned_sha }}", (
        f"the dispatch must consume the pin step's published sha; env is {step.get('env')!r}"
    )
    body = pin_step()
    assert "pinned_sha=$(git rev-parse HEAD)" in body, (
        "the pin step must publish the sha it landed, as `pinned_sha`"
    )
    assert "ls-remote" in step["run"], (
        "the dispatch must verify the remote ref before asking for a release"
    )
