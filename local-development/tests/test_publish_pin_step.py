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
    assert "1 file changed" in head, (
        f"the pin commit must touch values.yaml alone; it touched more:\n{head}"
    )


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
