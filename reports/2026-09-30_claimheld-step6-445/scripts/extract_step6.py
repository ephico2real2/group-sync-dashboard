"""SPEC_S4c §3.12 step 6's in-pod coordinator, extracted from the spec so the walk runs exactly what the spec says.

The extraction is the repository's own: `local-development/tests/test_s4c_step6_walk.py`'s `live_step6()` (the live
§3.12 walk, step 6 up to step 7) and `_HEREDOC` (the body of the `<<'PY' … PY` heredoc), dedented as that test's
`test_step6_script_claims_and_never_reads_a_password` dedents it. A second copy in this folder would be the one that
drifts (OB2's review of #461), so none is kept: the program is written to <out> at run time, from the tree named.

Usage: python extract_step6.py <repository root> <out file>
  Prints three lines: the spec's command line (the part before `<<'PY'`), the program's sha256, its line count.
  Exits 1 unless there is exactly one heredoc in step 6 and its command is the one scripts/run.sh runs.
"""
import hashlib
import pathlib
import sys
import textwrap

root, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
sys.dont_write_bytecode = True       # the import below must leave no __pycache__ in the tree it reads
sys.path.insert(0, str(root / "local-development" / "tests"))
import test_s4c_step6_walk as spec  # noqa: E402  (the module resolves the spec from its own location: `root`)

if pathlib.Path(spec.SPEC).resolve() != (root / "docs/specs/SPEC_S4c_credential_lifecycle.md").resolve():
    sys.exit(f"the extractor read {spec.SPEC}, not the spec under {root}")
step = spec.live_step6()
bodies = spec._HEREDOC.findall(step)
if len(bodies) != 1:
    sys.exit(f"step 6 holds {len(bodies)} <<'PY' heredocs; the walk runs exactly one")
commands = [line.strip() for line in step.splitlines() if line.rstrip().endswith("<<'PY'")]
if len(commands) != 1:
    sys.exit(f"step 6 holds {len(commands)} lines ending in <<'PY'")
command = commands[0].removesuffix("<<'PY'").rstrip()
EXPECTED = "oc exec -i -n group-sync-dashboard deploy/group-sync-dashboard -c dashboard -- python3.14 -"
if command != EXPECTED:
    sys.exit(f"step 6's command is {command!r}; scripts/run.sh runs {EXPECTED!r}")
program = textwrap.dedent(bodies[0]) + "\n"
out.write_text(program, encoding="utf-8")
print(command)
print(hashlib.sha256(program.encode("utf-8")).hexdigest())
print(len(program.splitlines()))
