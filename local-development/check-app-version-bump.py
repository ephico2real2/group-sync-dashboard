#!/usr/bin/env python3
"""Require the next MINOR or MAJOR for image changes, comparing BASE to HEAD.

CI checks out the PR merge ref, so HEAD includes the current base. Run locally with
BASE=<commit> python local-development/check-app-version-bump.py from the repo root.
Only committed changes are inspected, just as in the chart version check.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tomllib

import yaml


WORKFLOW = ".github/workflows/publish.yml"
PYPROJECT = "local-development/pyproject.toml"
VERSION_LINES = {
    PYPROJECT: re.compile(r'^version\s*=\s*"[^"\r\n]+"\s*$'),
    "local-development/gsd/__init__.py": re.compile(r'^__version__\s*=\s*"[^"\r\n]+"\s*$'),
}


def git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True,
    )
    if result.returncode:
        raise ValueError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def validate_base(repo: Path, base: str) -> str:
    """Use the chart check's commit-resolution rule, before any content decision."""
    try:
        if base:
            return git(repo, "rev-parse", "--verify", "--quiet", f"{base}^{{commit}}").strip()
    except ValueError:
        pass
    raise ValueError(
        f"the base commit is '{base}' and cannot be resolved; nothing to compare the app "
        "against. github.event.pull_request.base.sha needs checkout fetch-depth: 0."
    )


def read_image_paths(repo: Path) -> list[str]:
    workflow = yaml.safe_load((repo / WORKFLOW).read_text())
    try:
        # PyYAML's YAML 1.1 loader reads an unquoted `on` as boolean True.
        triggers = workflow.get("on", workflow.get(True))
        paths = triggers["push"]["paths"]
    except (AttributeError, KeyError, TypeError) as exc:
        raise ValueError(f"{WORKFLOW} must define on.push.paths") from exc
    if not isinstance(paths, list) or not paths or not all(isinstance(p, str) and p for p in paths):
        raise ValueError(f"{WORKFLOW} on.push.paths must be a nonempty list of patterns")
    return paths


def path_matches(path: str, patterns: list[str]) -> bool:
    """GitHub path filters: full paths, * within a segment, ** across segments.

    **/ also matches zero directories. Ordered ! exclusions can be re-included
    by later patterns. GitHub's ? and + quantify the preceding character/class.
    """
    matched = False
    for pattern in patterns:
        excluded = pattern.startswith("!")
        pattern = pattern[1:] if excluded else pattern
        regex = ""
        i = 0
        while i < len(pattern):
            char = pattern[i]
            if pattern[i:i + 3] == "**/":
                regex += "(?:.*/)?"
                i += 3
            elif pattern[i:i + 2] == "**":
                regex += ".*"
                i += 2
            elif char == "*":
                regex += "[^/]*"
                i += 1
            elif char == "[" and "]" in pattern[i + 1:]:
                end = pattern.index("]", i + 1)
                regex += pattern[i:end + 1]
                i = end + 1
            elif char in "?+":
                regex += char
                i += 1
            else:
                regex += re.escape(char)
                i += 1
        if re.fullmatch(regex, path):
            matched = not excluded
    return matched


def changed_files(repo: Path, base: str) -> list[str]:
    # Disable rename detection so moving an input OUT of the image still counts.
    output = git(repo, "diff", "--no-ext-diff", "--no-renames", "--name-only", "-z",
                 base, "HEAD", "--")
    return [path for path in output.split("\0") if path]


def has_nonversion_change(repo: Path, base: str, path: str) -> bool:
    """Ignore only changed version assignment lines, never the entire file."""
    if path not in VERSION_LINES:
        return True
    diff = git(repo, "diff", "--no-ext-diff", "--no-textconv", "--no-renames",
               "--unified=0", base, "HEAD", "--", path)
    in_hunk = False
    for line in diff.splitlines():
        if line.startswith("Binary files ") or line.startswith("old mode "):
            return True
        if line.startswith("@@"):
            in_hunk = True
        elif in_hunk and line.startswith(("+", "-")):
            if not VERSION_LINES[path].fullmatch(line[1:]):
                return True
    return False


def image_content_changes(repo: Path, base: str) -> list[str]:
    patterns = read_image_paths(repo)
    return [path for path in changed_files(repo, base)
            if path_matches(path, patterns) and has_nonversion_change(repo, base, path)]


def app_version(repo: Path, ref: str) -> str:
    data = tomllib.loads(git(repo, "show", f"{ref}:{PYPROJECT}"))
    return data["project"]["version"]


def check(repo: Path, base: str) -> int:
    base = validate_base(repo, base)
    changed = image_content_changes(repo, base)
    if not changed:
        print("no image content changed (publish.yml paths, excluding version fields); no bump needed")
        return 0
    print("image content changed:\n" + "\n".join(f"  {path}" for path in changed))
    was, now = app_version(repo, base), app_version(repo, "HEAD")
    if not isinstance(was, str) or not re.fullmatch(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", was):
        raise ValueError(f"base application version must be X.Y.Z, got {was!r}")
    major, minor, _ = map(int, was.split("."))
    expected = (f"{major}.{minor + 1}.0", f"{major + 1}.0.0")
    print(f"application version: {was} -> {now}")
    if now not in expected:
        print(f"::error file={PYPROJECT}::image content changed; expected exactly "
              f"{expected[0]} (next MINOR) or {expected[1]} (next MAJOR), got {now}")
        return 1
    print("application version is the next MINOR or MAJOR; bump accepted")
    return 0


def main() -> int:
    try:
        repo = Path(git(Path.cwd(), "rev-parse", "--show-toplevel").strip())
        return check(repo, os.environ.get("BASE", ""))
    except (ValueError, KeyError, TypeError, OSError, yaml.YAMLError, re.error) as exc:
        message = str(exc).replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        print(f"::error::{message}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
