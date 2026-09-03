"""No class in gsd/ may define the same method twice.

Python binds the LAST definition in a class body and says nothing about the first. `Store` carried
two `login_without_access` methods for almost a month (from 736ec16, 2026-08-08): the first with the
full rationale in its docstring, the second — a paste that should have been a replacement — with one
line. The bodies happened to be identical, so nothing misbehaved. The trap was the next edit: change
the documented copy, the one a reader finds first, and nothing changes at runtime while every test
keeps passing against the copy below it.

This walks the AST rather than importing, so a duplicate is reported by file and line before any
module-level side effect runs, and so it covers a class whose duplicate is only reached under
conditions the tests never exercise.
"""

from __future__ import annotations

import ast
import pathlib

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "gsd"
MODULES = sorted(p for p in PACKAGE.rglob("*.py") if "vendor" not in p.parts and "static" not in p.parts)


def _duplicate_methods(module: pathlib.Path) -> list[str]:
    tree = ast.parse(module.read_text(), filename=str(module))
    findings = []
    for cls in ast.walk(tree):
        if not isinstance(cls, ast.ClassDef):
            continue
        seen: dict[str, int] = {}
        for node in cls.body:
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            # @property setters/deleters and @overload legitimately repeat a name; skip them.
            decorators = {ast.unparse(d) for d in node.decorator_list}
            if any(d.endswith(".setter") or d.endswith(".deleter") or d in {"overload", "typing.overload"} for d in decorators):
                continue
            if node.name in seen:
                findings.append(f"{module.name}: class {cls.name} defines {node.name} at lines {seen[node.name]} and {node.lineno}; only the last one runs")
            else:
                seen[node.name] = node.lineno
    return findings


@pytest.mark.parametrize("module", MODULES, ids=lambda p: p.name)
def test_no_class_defines_a_method_twice(module: pathlib.Path) -> None:
    assert _duplicate_methods(module) == []


def test_the_check_would_have_caught_the_store_duplicate(tmp_path: pathlib.Path) -> None:
    """The test proves itself against the shape of the defect it exists for."""
    bad = tmp_path / "store_like.py"
    bad.write_text(
        "class Store:\n"
        "    def login_without_access(self):\n"
        '        """The documented copy."""\n'
        "        return 1\n"
        "    def login_without_access(self):\n"
        '        """The paste."""\n'
        "        return 1\n"
    )
    assert _duplicate_methods(bad) == [
        "store_like.py: class Store defines login_without_access at lines 2 and 5; only the last one runs"
    ]
