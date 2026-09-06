"""build-and-push-report.sh names the REPORT image and recipe whatever a .env says (measured defect,
2026-09-06: a .env naming the dashboard image overrode the wrapper's IMAGE_NAME, so the report image
was tagged group-sync-dashboard:<tag> — and --release-tags would have pushed it over the dashboard's
aliases). Run for real with a fake podman on PATH: the script's own logic, not a reading of its text."""
from __future__ import annotations

import os
import pathlib
import stat
import subprocess

LOCAL = pathlib.Path(__file__).resolve().parents[1]
WRAPPER = LOCAL / "build-and-push-report.sh"


def _fake_podman(bin_dir: pathlib.Path, log: pathlib.Path) -> None:
    commit = subprocess.run(["git", "rev-parse", "--short=10", "HEAD"], cwd=LOCAL, capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(["git", "status", "--porcelain"], cwd=LOCAL, capture_output=True, text=True).stdout.strip()
    stamp = f"{commit}-dirty" if dirty else commit
    fake = bin_dir / "podman"
    fake.write_text(f"""#!/usr/bin/env bash
printf '%s\\n' "$*" >> "{log}"
case "$1" in
  run) echo "{stamp}" ;;         # the stamp check: what the built image would report
  *) exit 0 ;;
esac
""")
    fake.chmod(fake.stat().st_mode | stat.S_IEXEC)


def _env(tmp_path):
    bin_dir = tmp_path / "bin"; bin_dir.mkdir()
    log = tmp_path / "podman.log"
    _fake_podman(bin_dir, log)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "REGISTRY": "registry.example", "REGISTRY_NAMESPACE": "ns", "REGISTRY_USERNAME": "u", "REGISTRY_PASSWORD": "p"}
    env.pop("IMAGE_NAME", None); env.pop("CONTAINERFILE", None)
    return env, log


def test_the_wrapper_builds_the_report_recipe_under_the_report_name(tmp_path):
    env, log = _env(tmp_path)
    done = subprocess.run([str(WRAPPER), "--build-only", "--allow-dirty"], cwd=LOCAL, env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    builds = [l for l in log.read_text().splitlines() if l.startswith("build ")]
    assert len(builds) == 1, log.read_text()
    assert "-f Containerfile.report" in builds[0], builds[0]
    tags = [t for t in builds[0].split() if t.startswith("registry.example/ns/")]
    assert tags and all(t.startswith("registry.example/ns/group-sync-dashboard-report:") for t in tags), builds[0]


def test_the_wrapper_refuses_the_two_flags_that_target_the_dashboard(tmp_path):
    env, _ = _env(tmp_path)
    for flag in ("--update-values", "--deploy"):
        done = subprocess.run([str(WRAPPER), flag], cwd=LOCAL, env=env, capture_output=True, text=True, timeout=60)
        assert done.returncode == 2 and "reporting.image" in done.stderr, (flag, done.stderr)
