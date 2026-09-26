"""A migration ships with an application release (#298).

The chart's default image is `:<appVersion>`, and publish.yml moves that alias only on the push
that changes pyproject's version. A migration merged without a version bump leaves the default
image one schema behind main, so any database main's code has touched makes it refuse readiness.
This compares the highest migration at HEAD with the one at the commit that released HEAD's
version, reading history with git only: CI's `tests` job checks out with fetch-depth: 0 for it.
"""

from __future__ import annotations

import importlib.util
import itertools
import os
import pathlib
import subprocess

import pytest

from gsd.store import KNOWN_SCHEMA_VERSION

HERE = pathlib.Path(__file__).resolve().parents[1]      # local-development/
REPO = HERE.parent

_spec = importlib.util.spec_from_file_location("prepare_release", HERE / "prepare-release.py")
prep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prep)

# The synthetic repositories' commits must not depend on the developer's git config.
GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_CONFIG_SYSTEM": "/dev/null",
    "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
    "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
}


def assert_schema_released(repo: pathlib.Path) -> None:
    release, then, now = prep.schema_since_app_release(repo)
    assert now <= then, (
        f"_MIGRATIONS reaches {now} at HEAD but {then} at {release[:12]}, the commit that released "
        "this application version. The chart's default image is built there and would refuse a "
        "database HEAD has migrated. Release the application in this PR: "
        "`local-development/prepare-release.py --app <next> \"<reason>\" --no-commit`, then commit.")


# One second per git call, so commits made in the same second still sort newest-first.
_CLOCK = itertools.count(1_700_000_000)


def git(repo: pathlib.Path, *args: str) -> None:
    date = f"{next(_CLOCK)} +0000"
    env = {**GIT_ENV, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", "-C", str(repo), *args], env=env, check=True, capture_output=True)


def commit(repo: pathlib.Path, version: str, migrations: list[int], note: str = "") -> None:
    """One commit carrying this version and these migration targets (and `note`, to force a change)."""
    store = repo / "local-development" / "gsd" / "store.py"
    store.parent.mkdir(parents=True, exist_ok=True)
    (repo / "local-development" / "pyproject.toml").write_text(f'[project]\nversion = "{version}"\n')
    entries = "".join(f'    ({n}, "migration {n}", []),\n' for n in migrations)
    store.write_text(f"# {note}\n_MIGRATIONS: list[tuple[int, str, list[str]]] = [\n{entries}]\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", f"{version} {migrations} {note}")


@pytest.fixture()
def released(tmp_path: pathlib.Path) -> pathlib.Path:
    """Application 0.1.0 released carrying migrations 1 and 2, then an ordinary merge."""
    git(tmp_path, "init", "-q", "-b", "main")
    commit(tmp_path, "0.0.9", [1])
    commit(tmp_path, "0.1.0", [1, 2])
    commit(tmp_path, "0.1.0", [1, 2], note="an ordinary change")
    return tmp_path


def test_a_migration_without_a_version_bump_fails(released: pathlib.Path) -> None:
    commit(released, "0.1.0", [1, 2, 3])
    with pytest.raises(AssertionError, match=r"reaches 3 at HEAD but 2 at .*prepare-release.py --app"):
        assert_schema_released(released)


def test_a_migration_with_a_version_bump_passes(released: pathlib.Path) -> None:
    commit(released, "0.1.0", [1, 2, 3])
    commit(released, "0.2.0", [1, 2, 3])
    assert_schema_released(released)


def test_no_migration_since_the_release_passes(released: pathlib.Path) -> None:
    assert prep.schema_since_app_release(released)[1:] == (2, 2)
    assert_schema_released(released)


def test_the_release_is_the_merge_that_moved_the_version(released: pathlib.Path) -> None:
    """First parent only, as publish.yml compares a push with the one before it: a PR that bumps
    and then adds a migration is released by its merge, not by its own bump commit."""
    git(released, "checkout", "-qb", "topic")
    commit(released, "0.2.0", [1, 2])
    commit(released, "0.2.0", [1, 2, 3])
    git(released, "checkout", "-q", "main")
    git(released, "merge", "-q", "--no-ff", "topic", "-m", "merge topic")
    assert_schema_released(released)


def test_a_history_too_shallow_to_reach_the_release_fails_loudly(released: pathlib.Path,
                                                                  tmp_path_factory) -> None:
    shallow = tmp_path_factory.mktemp("shallow")
    git(shallow, "clone", "-q", "--depth", "1", f"file://{released}", str(shallow / "repo"))
    with pytest.raises(prep.ReleaseError, match="fetch-depth: 0"):
        prep.schema_since_app_release(shallow / "repo")


def test_the_parse_reads_what_the_store_declares() -> None:
    """Without this, a reshaped _MIGRATIONS would parse as 0 at HEAD and every check would pass."""
    assert prep.highest_migration((HERE / "gsd" / "store.py").read_text()) == KNOWN_SCHEMA_VERSION


def test_this_repository_released_its_highest_migration() -> None:
    assert_schema_released(REPO)
