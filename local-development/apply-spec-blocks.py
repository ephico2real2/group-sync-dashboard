#!/usr/bin/env python3
"""Check and apply a specification's implementation blocks to a tree (docs/specs/README.md, "Implementation blocks").

    python3 local-development/apply-spec-blocks.py <spec.md> <tree> [--apply]

Each block in the spec is introduced by one HTML comment line, then its fenced code:

    <!-- block: local-development/gsd/kube.py | edit -->      two fences follow: the Old text, then the New text
    <!-- block: local-development/tests/test_x.py | create -->  one fence follows: the whole new file
    <!-- block: docs/CHANGELOG.md | after: ## Unreleased -->  one fence follows, inserted after the anchor line

Without --apply it only checks: every edit's Old text occurs EXACTLY ONCE in its file (after the earlier blocks
for the same file are applied, in order), every create names a file that does not exist, every anchor exists
once. With --apply it writes the result into <tree>. A git tree must be clean first, so that the diff after applying
is exactly the specification's blocks and nothing else. Exit 1 on the first mismatch, naming the block and why.
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

MARK = re.compile(r"^<!-- block: (?P<path>[^|]+?) \| (?P<kind>edit|create|after: .+?) -->$", re.M)
FENCE = re.compile(r"^```[\w-]*\n(?P<body>.*?)^```$", re.M | re.S)


def blocks(spec: str) -> list[dict]:
    out = []
    marks = list(MARK.finditer(spec))
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(spec)
        fences = [f.group("body") for f in FENCE.finditer(spec, m.end(), end)]
        kind = m.group("kind")
        need = 2 if kind == "edit" else 1
        if len(fences) < need:
            raise SystemExit(f"block {i + 1} ({m.group('path')} | {kind}): expected {need} fenced blocks, found {len(fences)}")
        out.append({"n": i + 1, "path": m.group("path").strip(), "kind": kind, "fences": fences[:need]})
    return out


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__)
        return 2
    spec, tree = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2]).resolve()
    apply = "--apply" in sys.argv[3:]
    if apply and (tree / ".git").exists():
        dirty = subprocess.run(["git", "-C", str(tree), "status", "--porcelain"], capture_output=True, text=True).stdout
        if dirty.strip():
            raise SystemExit(f"refusing to apply into {tree}: it has uncommitted changes, so the result would not be "
                             "the specification's blocks alone")
    files: dict[str, str] = {}
    for b in blocks(spec.read_text()):
        target = tree / b["path"]
        if b["kind"] == "create":
            if b["path"] in files or target.exists():
                return fail(b, "create names a file that already exists")
            files[b["path"]] = b["fences"][0]
            continue
        text = files.get(b["path"])
        if text is None:
            if not target.exists():
                return fail(b, "file does not exist")
            text = target.read_text()
        if b["kind"] == "edit":
            old, new = b["fences"]
            count = text.count(old)
            if count != 1:
                return fail(b, f"Old text occurs {count} times (must be exactly once)")
            text = text.replace(old, new)
        else:
            anchor = b["kind"].split(": ", 1)[1]
            lines = text.split("\n")
            hits = [i for i, line in enumerate(lines) if line == anchor]
            if len(hits) != 1:
                return fail(b, f"anchor {anchor!r} occurs {len(hits)} times (must be exactly once)")
            lines[hits[0] + 1:hits[0] + 1] = b["fences"][0].rstrip("\n").split("\n")
            text = "\n".join(lines)
        files[b["path"]] = text
    print(f"{len(blocks(spec.read_text()))} blocks check out across {len(files)} files")
    if apply:
        for path, text in files.items():
            (tree / path).parent.mkdir(parents=True, exist_ok=True)
            (tree / path).write_text(text)
        print(f"applied to {tree}")
    return 0


def fail(b: dict, why: str) -> int:
    print(f"FAIL block {b['n']} ({b['path']} | {b['kind']}): {why}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
