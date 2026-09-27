"""Exercise the PR gate against real commits, including its command-line entry point."""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml


REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "local-development/check-app-version-bump.py"
SPEC = importlib.util.spec_from_file_location("app_version_bump", SCRIPT)
gate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(gate)
PROJECT = "local-development/pyproject.toml"
INIT = "local-development/gsd/__init__.py"
WORKFLOW = ".github/workflows/publish.yml"
PATHS = ["local-development/gsd/**", PROJECT]


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


def write(repo, name, text):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


def versions(repo, version):
    write(repo, PROJECT, f'[project]\nname = "fixture"\nversion = "{version}"\n')
    write(repo, INIT, f'__version__ = "{version}"\n')


def commit(repo):
    git(repo, "add", ".")
    git(repo, "commit", "-qm", "fixture", "--allow-empty")
    return git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path):
    git(tmp_path, "init", "-q")
    git(tmp_path, "config", "user.email", "test@example.invalid")
    git(tmp_path, "config", "user.name", "Test")
    git(tmp_path, "config", "commit.gpgsign", "false")
    versions(tmp_path, "1.0.0")
    # Unquoted on deliberately exercises YAML 1.1's True key.
    write(tmp_path, WORKFLOW, "on:\n  push:\n    paths:\n" +
          "".join(f"      - '{path}'\n" for path in PATHS))
    write(tmp_path, "local-development/gsd/api.py", "CONTENT = 1\n")
    return tmp_path, commit(tmp_path)


def assert_check(repo, base, expected, capsys):
    assert gate.check(repo, base) == expected
    output = capsys.readouterr().out
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=repo,
                            env={**os.environ, "BASE": base}, capture_output=True, text=True)
    assert result.returncode == expected, result.stdout + result.stderr
    assert result.stdout == output
    return output


@pytest.mark.parametrize("version,code", [
    ("1.0.0", 1), ("1.1.0", 0), ("2.0.0", 0),
    ("1.2.0", 1), ("0.9.0", 1), ("1.0.1", 1),
    ("1.1.1", 1), ("2.0.1", 1), ("3.0.0", 1),
    ("1.1.0-rc.1", 1), ("01.1.0", 1),
])
def test_image_change_requires_exact_next_minor_or_major(repo, version, code, capsys):
    root, base = repo
    versions(root, version)
    write(root, "local-development/gsd/api.py", "CONTENT = 2\n")
    commit(root)
    assert gate.image_content_changes(root, base) == ["local-development/gsd/api.py"]
    output = assert_check(root, base, code, capsys)
    assert f"application version: 1.0.0 -> {version}" in output
    if code:
        error = next(line for line in output.splitlines() if line.startswith("::error"))
        assert "1.1.0 (next MINOR) or 2.0.0 (next MAJOR)" in error


@pytest.mark.parametrize("kind", ["docs", "version-fields", "unchanged"])
def test_no_image_content_needs_no_bump(repo, kind, capsys):
    root, base = repo
    if kind == "docs":
        write(root, "docs/guide.md", "Documentation\n")
    elif kind == "version-fields":
        versions(root, "1.2.0")  # The rule does not restrict a version-only release.
    commit(root)
    assert gate.image_content_changes(root, base) == []
    assert "no image content changed" in assert_check(root, base, 0, capsys)


@pytest.mark.parametrize("path", [PROJECT, INIT])
def test_other_lines_in_version_files_are_image_content(repo, path, capsys):
    root, base = repo
    with (root / path).open("a") as stream:
        stream.write("# This comment is image content too.\n")
    commit(root)
    assert gate.image_content_changes(root, base) == [path]
    assert_check(root, base, 1, capsys)


@pytest.mark.parametrize("base", ["", "no-such-commit"])
def test_bad_base_fails_even_without_image_changes(repo, base):
    root, _ = repo
    with pytest.raises(ValueError, match="cannot be resolved"):
        gate.check(root, base)
    result = subprocess.run([sys.executable, str(SCRIPT)], cwd=root,
                            env={**os.environ, "BASE": base}, capture_output=True, text=True)
    assert result.returncode == 1
    assert "::error::the base commit" in result.stdout
    assert "fetch-depth: 0" in result.stdout


@pytest.mark.parametrize("quoted_on", [False, True])
def test_workflow_is_the_path_source(repo, quoted_on, capsys):
    root, base = repo
    write(root, "extra/input.txt", "new image input\n")
    commit(root)
    assert_check(root, base, 0, capsys)
    key = '"on"' if quoted_on else "on"
    write(root, WORKFLOW, f"{key}:\n  push:\n    paths: ['extra/**']\n")
    commit(root)
    assert gate.read_image_paths(root) == ["extra/**"]
    assert gate.image_content_changes(root, base) == ["extra/input.txt"]
    assert_check(root, base, 1, capsys)


@pytest.mark.parametrize("pattern,path,matched", [
    ("local-development/gsd/**", "local-development/gsd/deep/module.py", True),
    ("local-development/gsd/**", "local-development/gsd/.hidden", True),
    ("local-development/gsd/*", "local-development/gsd/deep/module.py", False),
    ("**/*.md", "README.md", True),
    ("**/*.md", "docs/deep/guide.md", True),
    ("local-development/**/api.py", "local-development/api.py", True),
    ("local-development/gsd/**", "other/local-development/gsd/api.py", False),
    ("local-development/gsd", "local-development/gsd/api.py", False),
    ("**/v[12].[0-9]+.py", "modules/v2.123.py", True),
    ("**/tests?.py", "test.py", True),
])
def test_path_filter_globs(repo, pattern, path, matched, capsys):
    root, base = repo
    write(root, WORKFLOW, yaml.safe_dump({"on": {"push": {"paths": [pattern]}}}))
    write(root, path, "changed\n")
    commit(root)
    assert gate.path_matches(path, [pattern]) == matched
    assert_check(root, base, int(matched), capsys)


def test_ordered_exclusions_and_reinclusions(repo, capsys):
    root, base = repo
    patterns = ["local-development/gsd/**", "!**/*.txt", "**/keep.txt"]
    write(root, WORKFLOW, yaml.safe_dump({"on": {"push": {"paths": patterns}}}))
    write(root, "local-development/gsd/skip.txt", "excluded\n")
    commit(root)
    assert_check(root, base, 0, capsys)
    write(root, "local-development/gsd/keep.txt", "included again\n")
    commit(root)
    assert_check(root, base, 1, capsys)


@pytest.mark.parametrize("action", ["delete", "rename-out"])
def test_removed_image_content_requires_bump(repo, action, capsys):
    root, base = repo
    source = root / "local-development/gsd/api.py"
    if action == "delete":
        source.unlink()
    else:
        source.rename(root / "outside.py")
    commit(root)
    assert "local-development/gsd/api.py" in gate.image_content_changes(root, base)
    assert_check(root, base, 1, capsys)


def test_merge_ref_compares_to_updated_base(repo, capsys):
    root, _ = repo
    versions(root, "1.1.0")
    base = commit(root)  # Another issue already claimed 1.1.0 on main.
    write(root, "local-development/gsd/api.py", "CONTENT = 2\n")
    commit(root)
    assert "1.2.0 (next MINOR) or 2.0.0 (next MAJOR)" in assert_check(root, base, 1, capsys)
    versions(root, "1.2.0")
    commit(root)
    assert_check(root, base, 0, capsys)


def test_real_publish_allowlist():
    assert gate.read_image_paths(REPO) == [
        "local-development/gsd/**",
        "local-development/pyproject.toml",
        "local-development/README.md",
        "local-development/uninstall-lists.py",
        "local-development/image-proof.py",
        "local-development/Containerfile",
        "local-development/.containerignore",
        "local-development/build-and-push-external.sh",
        "local-development/Containerfile.report",
        "local-development/report-image-proof.py",
        "local-development/build-and-push-report.sh",
        ".github/workflows/publish.yml",
    ]
