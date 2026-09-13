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


def test_release_tags_cannot_inherit_the_dashboards_image_name(tmp_path):
    """Codex, review C3 second pass: the wrapper defaulted IMAGE_NAME from the environment, so a shell
    that had exported the dashboard's .env (IMAGE_NAME=group-sync-dashboard) built Containerfile.report
    under the dashboard's name and, with --release-tags, moved the dashboard's aliases onto report
    bytes. Run for real: fake git (a clean tree, so --release-tags is allowed), podman and skopeo on
    PATH, the ambient IMAGE_NAME poisoned; every name the run pushes or copies must be the report's."""
    import re
    import yaml
    bin_dir = tmp_path / "bin"; bin_dir.mkdir()
    log = tmp_path / "tools.log"
    digest = "sha256:" + "a" * 64
    (bin_dir / "git").write_text("""#!/usr/bin/env bash
case "$*" in
  "rev-parse --short=10 HEAD") echo 0123456789 ;;
  "rev-parse --abbrev-ref HEAD") echo main ;;
  "status --porcelain") exit 0 ;;
  *) exit 1 ;;
esac
""")
    (bin_dir / "podman").write_text(f"""#!/usr/bin/env bash
printf 'podman %s\\n' "$*" >> "{log}"
case "$1" in
  run) echo 0123456789 ;;
  push) shift; while [ "$#" -gt 0 ]; do if [ "$1" = "--digestfile" ]; then printf '%s\\n' "{digest}" > "$2"; break; fi; shift; done ;;
esac
exit 0
""")
    (bin_dir / "skopeo").write_text(f"""#!/usr/bin/env bash
printf 'skopeo %s\\n' "$*" >> "{log}"
[ "$1" = "inspect" ] && echo "{digest}"
exit 0
""")
    for tool in ("git", "podman", "skopeo"):
        (bin_dir / tool).chmod((bin_dir / tool).stat().st_mode | stat.S_IEXEC)
    digest_file = tmp_path / "reported.digest"
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}",
           "REGISTRY": "registry.example", "REGISTRY_NAMESPACE": "ns", "REGISTRY_USERNAME": "robot", "REGISTRY_PASSWORD": "secret",
           "IMAGE_NAME": "group-sync-dashboard", "CONTAINERFILE": "Containerfile", "DIGEST_FILE": str(digest_file)}
    done = subprocess.run([str(WRAPPER), "--release-tags"], cwd=LOCAL, env=env, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stdout + done.stderr
    app_version = re.search(r'^version = "([^"]+)"$', (LOCAL / "pyproject.toml").read_text(), re.M).group(1)
    chart_version = yaml.safe_load((LOCAL.parent / "charts" / "group-sync-dashboard" / "Chart.yaml").read_text())["version"]
    calls = log.read_text()
    report = "registry.example/ns/group-sync-dashboard-report:"
    assert f"{report}{app_version}-0123456789" in calls and f"{report}{app_version}" in calls and f"{report}{chart_version}" in calls, calls
    assert "registry.example/ns/group-sync-dashboard:" not in calls, calls
    assert "-f Containerfile.report" in calls, calls
    assert digest_file.read_text().strip() == digest


def test_the_wrapper_refuses_the_two_flags_that_target_the_dashboard(tmp_path):
    env, _ = _env(tmp_path)
    for flag in ("--update-values", "--deploy"):
        done = subprocess.run([str(WRAPPER), flag], cwd=LOCAL, env=env, capture_output=True, text=True, timeout=60)
        assert done.returncode == 2 and "reporting.image" in done.stderr, (flag, done.stderr)
