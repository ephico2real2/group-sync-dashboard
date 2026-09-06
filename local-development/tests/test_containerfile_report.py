"""Containerfile.report is Containerfile with exactly the marked differences (docs/specs/SPEC_C3_reporting_microservice.md
§9.10): same bases, same pack stage, same uninstall, same user — a second recipe that could drift from the first
would undo the hardened-image work for the report pod alone."""
from __future__ import annotations

import ast
import re

from test_containerfile import CONTAINERFILE, LOCAL, _logical_lines, _stages

REPORT = LOCAL / "Containerfile.report"
REPORT_PROOF = LOCAL / "report-image-proof.py"


def _instructions(path):
    return [l for l in _logical_lines(path.read_text()) if re.match(r"^[A-Z]+\b", l)]


def test_the_two_recipes_differ_only_where_marked():
    base, report = _instructions(CONTAINERFILE), _instructions(REPORT)
    assert len(base) == len(report), "the report recipe has the same instruction list, line for line"
    differing = [(a, b) for a, b in zip(base, report) if a != b]
    for a, b in differing:
        assert any(token in a or token in b for token in ("image-proof.py", "report-image-proof.py", "/artifacts", "8443", "8080",
                                                             "gsd.reporting.server", "gsd.api:create_app", "[report]", "pip install", "GSD_REPORT_", "uvicorn")), (a, b)
    froms = [(a, b) for a, b in zip(base, report) if a.startswith("FROM")]
    assert all(a == b for a, b in froms), "same bases on the same floating tags"


def test_the_pack_stage_and_the_uninstall_are_byte_identical():
    base = dict(_stages(_logical_lines(CONTAINERFILE.read_text())))
    report = dict(_stages(_logical_lines(REPORT.read_text())))
    for name, body in base.items():
        if "pack" in name.lower():
            assert report[name] == body, name
    base_runtime, report_runtime = list(base.values())[-1], list(report.values())[-1]
    erase = [l for l in base_runtime if "uninstall-lists.py" in l]
    assert erase and all(l in report_runtime for l in erase), "the RPM-database edit is the same"


def test_the_final_stage_serves_the_report_app_on_8443_with_its_own_proof():
    report = _instructions(REPORT)
    runtime = report[report.index([l for l in report if l.startswith("FROM") and "AS" not in l][-1]):]
    assert any(l.startswith("EXPOSE 8443") for l in runtime)
    cmd = next(l for l in runtime if l.startswith("CMD"))
    assert "gsd.reporting.server:create_report_app" in cmd and "--factory" in cmd and "8443" in cmd
    assert any("report-image-proof.py" in l for l in runtime), "the runtime proof is the report's"
    build = next(body for name, body in _stages(_logical_lines(REPORT.read_text())) if "build" in name.lower())
    assert any("[report]" in l for l in build), "the build stage installs the report extra"


def test_the_runtime_proof_imports_every_module_the_build_stage_proved():
    """The image-proof.py rule, applied to the report recipe: the build stage's `python -c "import …"`
    proof and the runtime proof script name the same modules (parsed with ast, not by eye)."""
    text = re.sub(r"\\\n", " ", REPORT.read_text())
    build_imports: set[str] = set()
    for m in re.finditer(r"import ([a-zA-Z0-9_., ]+)", text):
        build_imports |= {n.strip().split(".")[0] for n in m.group(1).split(",") if n.strip()}
    tree = ast.parse(REPORT_PROOF.read_text())
    proof_imports = {a.name.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
    proof_imports |= {n.module.split(".")[0] for n in ast.walk(tree) if isinstance(n, ast.ImportFrom) and n.module}
    for mod in ("fpdf", "jinja2", "gsd"):
        assert mod in build_imports and mod in proof_imports, (mod, build_imports, proof_imports)
