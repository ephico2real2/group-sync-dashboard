"""The e2e walk's second-cluster step must skip the Overview's fleet option (#172): its value is empty
and its label is "all clusters", and choosing options by label kept the walk on the fleet while it
recorded "switch cluster to all clusters" as the second cluster's evidence (Codex, review of #172,
pass 2)."""
from __future__ import annotations

import ast
import importlib.util
import inspect
import pathlib


def _capture_module():
    path = pathlib.Path(__file__).resolve().parents[1] / "e2e-walk" / "e2e_capture.py"
    spec = importlib.util.spec_from_file_location("gsd_e2e_capture", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_walk_skips_the_fleet_option_when_choosing_the_second_cluster():
    pick = _capture_module().next_configured_cluster
    options = [{"value": "", "label": "all clusters"},
               {"value": "crc-local", "label": "crc-local"},
               {"value": "prod-east", "label": "prod-east"}]
    assert pick(options, "") == options[2]
    assert pick(options, "crc-local") == options[2]
    assert pick(options, "prod-east") == options[1]
    assert pick([{"value": "", "label": "all clusters"}], "") is None
    assert pick([{"value": "", "label": "all clusters"}, {"value": "only", "label": "only"}], "") == {"value": "only", "label": "only"}


def test_every_page_call_in_the_walk_binds_to_the_installed_playwright_api():
    """`e2e_extra.py` passed `cluster_id` positionally to `page.wait_for_function`, whose `arg` is
    keyword-only in Playwright's Python API — a TypeError the moment the walk reached its second cluster,
    which `bash -n`, an AST parse and the by-path import of `next_configured_cluster` cannot see (OB1,
    review of #172, pass 3). Every `page.<method>(...)` in the walk scripts is bound, by its shape, against
    the installed `Page` signature — the walk only ever runs against a deployed cluster, so this is the
    one place a wrong call shape is caught before it does."""
    from playwright.sync_api import Page

    walk = pathlib.Path(__file__).resolve().parents[1] / "e2e-walk"
    problems = []
    for script in ("e2e_capture.py", "e2e_extra.py"):
        tree = ast.parse((walk / script).read_text(), script)
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and isinstance(node.func.value, ast.Name) and node.func.value.id == "page"):
                continue
            method = getattr(Page, node.func.attr, None)
            if method is None or any(isinstance(a, ast.Starred) for a in node.args) or any(k.arg is None for k in node.keywords):
                continue
            try:
                inspect.signature(method).bind(None, *[None] * len(node.args), **{k.arg: None for k in node.keywords})
            except TypeError as e:
                problems.append(f"{script}:{node.lineno} page.{node.func.attr}(...): {e}")
    assert problems == [], "\n".join(problems)

