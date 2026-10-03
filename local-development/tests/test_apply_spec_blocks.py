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


FENCE = "`" * 3
# The two markers and the fences are assembled here, never written at column 0, so a specification can quote
# this file in a block of its own without the checker reading them as that block's markers or its fences.
STACKED = SPEC + "\n".join([
    "<!-- " + "deferred-block: pkg/a.py | edit -->", FENCE + "python", "gamma", FENCE, FENCE + "python", "GAMMA", FENCE, "",
    "<!-- " + "applied-block: pkg/done.py | create -->", FENCE + "python", 'print("already on main")', FENCE, "",
])


def test_deferred_and_applied_blocks_are_left_alone_and_counted_aloud(tmp_path):
    """A change that ships in two pull requests (SPEC_G4, #420) stages the later one's blocks as `deferred-block`
    and, once the earlier one is on main, retires its markers to `applied-block`. The tool applies neither, and
    says how many it left alone, so a check that reads "8 blocks check out" cannot hide sixteen more."""
    tree = tmp_path / "tree"
    write(tree / "pkg/a.py", "alpha\nbeta\ngamma\n")
    done = run(write(tmp_path / "spec.md", STACKED), tree, "--apply")
    assert done.returncode == 0, done.stderr
    assert "3 blocks check out across 2 files; left alone: 1 deferred-block, 1 applied-block" in done.stdout, done.stdout
    assert (tree / "pkg/a.py").read_text() == "alpha\ninserted\nBETA\ngamma\n"
    assert not (tree / "pkg/done.py").exists()


def test_a_marker_word_the_tool_does_not_know_is_refused_not_skipped(tmp_path):
    tree = tmp_path / "tree"
    write(tree / "pkg/a.py", "alpha\nbeta\ngamma\n")
    typo = SPEC.replace("<!-- block: pkg/new.py | create -->", "<!-- " + "defered-block: pkg/new.py | create -->")
    done = run(write(tmp_path / "spec.md", typo), tree)
    assert done.returncode == 1 and "unknown block marker" in done.stderr, done.stderr
    assert "defered-block" in done.stderr


def test_a_marker_the_tool_cannot_read_exactly_is_refused_before_anything_is_written(tmp_path):
    """A known word in a form the tool does not read (a capital, a stray or missing space, a misspelt kind) was
    skipped silently while "N blocks check out" counted the rest; every column-0 `<!-- <word>:` line must be exactly
    one of the three forms, or nothing is written (confirmation review of SPEC_G4, OB2)."""
    for n, marker in enumerate(("<!-- " + "Block: pkg/new.py | create -->",
                                "<!-- " + "deferred-Block: pkg/new.py | create -->",
                                "<!-- " + "block: pkg/new.py | create --> ",
                                "<!-- " + "block: pkg/new.py |create -->",
                                "<!-- " + "block: pkg/new.py | Create -->",
                                "<!--" + "block: pkg/new.py | create -->")):
        tree = tmp_path / f"tree{n}"
        write(tree / "pkg/a.py", "alpha\nbeta\ngamma\n")
        typo = SPEC.replace("<!-- block: pkg/new.py | create -->", marker)
        done = run(write(tmp_path / f"spec{n}.md", typo), tree, "--apply")
        assert done.returncode == 1 and "unknown block marker" in done.stderr, (marker, done.stdout, done.stderr)
        assert marker in done.stderr, (marker, done.stderr)
        assert (tree / "pkg/a.py").read_text() == "alpha\nbeta\ngamma\n" and not (tree / "pkg/new.py").exists(), marker


def test_a_dirty_git_tree_is_refused(tmp_path):
    tree = tmp_path / "tree"
    write(tree / "pkg/a.py", "alpha\nbeta\ngamma\n")
    subprocess.run(["git", "init", "-q", str(tree)], check=True)
    write(tree / "stray.txt", "uncommitted")
    done = run(write(tmp_path / "spec.md", SPEC), tree, "--apply")
    assert done.returncode == 1 and "uncommitted changes" in done.stderr
