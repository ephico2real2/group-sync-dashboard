"""The tool that applies a specification's implementation blocks does exactly what the spec says, or refuses."""

from __future__ import annotations

import pathlib
import subprocess
import sys

TOOL = pathlib.Path(__file__).resolve().parents[1] / "apply-spec-blocks.py"


def run(spec: pathlib.Path, tree: pathlib.Path, *extra: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, str(TOOL), str(spec), str(tree), *extra], capture_output=True, text=True)


def write(path: pathlib.Path, text: str) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


SPEC = """# a spec

<!-- block: pkg/a.py | edit -->
```python
beta
```
```python
BETA
```

<!-- block: pkg/a.py | after: alpha -->
```python
inserted
```

<!-- block: pkg/new.py | create -->
```python
print("new")
```
"""


def test_edit_after_and_create_apply_in_order(tmp_path):
    tree = tmp_path / "tree"
    write(tree / "pkg/a.py", "alpha\nbeta\ngamma\n")
    done = run(write(tmp_path / "spec.md", SPEC), tree, "--apply")
    assert done.returncode == 0, done.stderr
    assert (tree / "pkg/a.py").read_text() == "alpha\ninserted\nBETA\ngamma\n"
    assert (tree / "pkg/new.py").read_text() == 'print("new")\n'


def test_a_check_writes_nothing(tmp_path):
    tree = tmp_path / "tree"
    write(tree / "pkg/a.py", "alpha\nbeta\ngamma\n")
    assert run(write(tmp_path / "spec.md", SPEC), tree).returncode == 0
    assert (tree / "pkg/a.py").read_text() == "alpha\nbeta\ngamma\n" and not (tree / "pkg/new.py").exists()


def test_old_text_that_is_not_unique_is_refused(tmp_path):
    tree = tmp_path / "tree"
    write(tree / "pkg/b.py", "x\nx\n")
    spec = write(tmp_path / "spec.md", "<!-- block: pkg/b.py | edit -->\n```\nx\n```\n```\ny\n```\n")
    done = run(spec, tree, "--apply")
    assert done.returncode == 1 and "occurs 2 times" in done.stderr
    assert (tree / "pkg/b.py").read_text() == "x\nx\n"


def test_create_over_an_existing_file_and_a_missing_anchor_are_refused(tmp_path):
    tree = tmp_path / "tree"
    write(tree / "pkg/a.py", "alpha\n")
    create = write(tmp_path / "c.md", "<!-- block: pkg/a.py | create -->\n```\nz\n```\n")
    assert "already exists" in run(create, tree).stderr
    anchor = write(tmp_path / "a.md", "<!-- block: pkg/a.py | after: omega -->\n```\nz\n```\n")
    assert "occurs 0 times" in run(anchor, tree).stderr


def test_a_dirty_git_tree_is_refused(tmp_path):
    tree = tmp_path / "tree"
    write(tree / "pkg/a.py", "alpha\nbeta\ngamma\n")
    subprocess.run(["git", "init", "-q", str(tree)], check=True)
    write(tree / "stray.txt", "uncommitted")
    done = run(write(tmp_path / "spec.md", SPEC), tree, "--apply")
    assert done.returncode == 1 and "uncommitted changes" in done.stderr
