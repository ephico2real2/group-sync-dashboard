"""release-crc.sh and argocd-wait.sh, driven end to end against stubs.

A temporary repository (with a bare `origin`) carries the files the script reads; `oc`, `podman`
and `helm` are stubs on PATH that log their arguments to one file and answer from environment
variables. Real git, real bash, the real scripts — only the cluster and the container engine are
replaced. RELEASE_CRC_UNDER_TEST points the tests at another copy of the script (the failing-before
evidence in the review record was produced that way).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

LOCAL_DEV = Path(__file__).resolve().parents[1]
REPO = LOCAL_DEV.parent
SCRIPT = Path(os.environ.get("RELEASE_CRC_UNDER_TEST", LOCAL_DEV / "release-crc.sh"))
WAITER = Path(os.environ.get("ARGOCD_WAIT_UNDER_TEST", LOCAL_DEV / "argocd-wait.sh"))

STUB = r'''#!/usr/bin/env bash
# Every call is logged as one line: <tool> <args>. Answers come from STUB_* variables.
printf '%s %s\n' "$(basename "$0")" "$*" >> "$STUB_LOG"
case "$(basename "$0") $*" in
  "oc get istag "*)      name="${2#istag }"; name="${*:3:1}"; case " $STUB_ISTAGS " in *" ${name} "*) exit 0;; *) exit 1;; esac ;;
  "oc whoami -t")        echo token ;;
  "oc exec "*)           echo "$STUB_COMMIT" ;;
  "oc patch --local "*)  cat "$STUB_APP_FILE" 2>/dev/null || echo '{}' ;;   # the merged object, as JSON on stdout
  "oc apply -f -")       cat > "$STUB_APPLIED" ;;
  "oc get application "*" -o json") cat "$STUB_APP_JSON" ;;
  "oc get application "*) exit "${STUB_APP_EXISTS:-1}" ;;
  "helm status "*)       exit "${STUB_HELM_EXISTS:-1}" ;;
  "podman run "*)        echo "$STUB_COMMIT" ;;
esac
exit 0
'''


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


@pytest.fixture
def lab(tmp_path: Path):
    """A repository shaped like this one where the script's inputs live, plus the stubs."""
    repo = tmp_path / "repo"
    (repo / "local-development").mkdir(parents=True)
    (repo / "environments").mkdir()
    (repo / "gitops").mkdir()
    shutil.copy(SCRIPT, repo / "local-development" / "release-crc.sh")
    shutil.copy(WAITER, repo / "local-development" / "argocd-wait.sh")
    shutil.copy(LOCAL_DEV / "pyproject.toml", repo / "local-development" / "pyproject.toml")
    for name in ("Containerfile", "Containerfile.report"):
        (repo / "local-development" / name).write_text("FROM scratch\n")
    (repo / "environments" / "crc.yaml").write_text("logLevel: DEBUG\n")
    shutil.copy(REPO / "gitops" / "argocd-application-dashboard.yaml", repo / "gitops" / "argocd-application-dashboard.yaml")
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", "base")
    origin = tmp_path / "origin.git"
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    _git(repo, "remote", "add", "origin", str(origin))
    _git(repo, "push", "-q", "-u", "origin", "main")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool in ("oc", "podman", "helm"):
        p = bindir / tool
        p.write_text(STUB)
        p.chmod(0o755)
    full = _git(repo, "rev-parse", "HEAD")
    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "STUB_LOG": str(tmp_path / "calls.log"),
        "STUB_COMMIT": full[:10],
        "STUB_ISTAGS": "",
        "STUB_APP_FILE": str(tmp_path / "app-merged.json"),
        "STUB_APPLIED": str(tmp_path / "applied.json"),
        "STUB_APP_JSON": str(tmp_path / "app-status.json"),
        "ARGOCD_WAIT_INTERVAL": "1",
        "ARGOCD_WAIT_TIMEOUT": "3",
    }
    (tmp_path / "app-merged.json").write_text('{"kind":"Application"}')
    return {"repo": repo, "origin": origin, "env": env, "log": tmp_path / "calls.log", "full": full, "tmp": tmp_path}


def run(lab, *args: str, **env_over: str) -> subprocess.CompletedProcess:
    env = {**lab["env"], **env_over}
    return subprocess.run(["bash", str(lab["repo"] / "local-development" / "release-crc.sh"), *args],
                          cwd=lab["repo"] / "local-development", env=env, capture_output=True, text=True)


def calls(lab) -> str:
    return lab["log"].read_text() if lab["log"].exists() else ""


def synced_status(lab, revision: str) -> None:
    """An Application whose status was computed for its current spec, Synced/Healthy at `revision`."""
    src = {"repoURL": "x", "path": "charts/group-sync-dashboard", "targetRevision": "main"}
    (lab["tmp"] / "app-status.json").write_text(json.dumps({
        "spec": {"source": src},
        "status": {"sync": {"status": "Synced", "revision": revision, "comparedTo": {"source": src}},
                   "health": {"status": "Healthy"}, "operationState": {"phase": "Succeeded", "message": "ok"}}}))


# --- the parser -----------------------------------------------------------------------------

def test_values_does_not_consume_an_option(lab):
    r = run(lab, "--values", "--argocd")
    assert r.returncode == 2, r.stdout + r.stderr
    assert "--values needs a path" in r.stderr
    assert calls(lab) == "", "refused before any tool ran"


def test_allow_dirty_and_argocd_are_refused_either_way(lab):
    for order in (("--allow-dirty", "--argocd"), ("--argocd", "--allow-dirty")):
        r = run(lab, *order)
        assert r.returncode == 2 and "do not combine" in r.stderr, order
    assert calls(lab) == ""


# --- the dirty-tree exemption -------------------------------------------------------------------

def test_local_values_variant_is_not_dirty_but_a_lookalike_is(lab):
    (lab["repo"] / "environments" / "crc-local.yaml").write_text("logLevel: INFO\n")
    r = run(lab, "--values", "environments/crc-local.yaml", "--build-only")
    assert r.returncode == 0, r.stderr
    assert "dirty" not in r.stdout + r.stderr
    # a regex over porcelain would have exempted this file too: `.` matched any character
    (lab["repo"] / "environments" / "crc-local.yaml").unlink()
    (lab["repo"] / "environments" / "crc-localXyaml").write_text("x: 1\n")
    r = run(lab, "--values", "environments/crc-local.yaml", "--build-only")
    assert r.returncode == 1 and "uncommitted changes" in r.stderr


def test_a_values_file_under_local_development_is_still_dirty(lab):
    (lab["repo"] / "local-development" / "mine.yaml").write_text("x: 1\n")
    r = run(lab, "--values", "local-development/mine.yaml", "--build-only")
    assert r.returncode == 1 and "uncommitted changes" in r.stderr


# --- the Argo values checks --------------------------------------------------------------------

def test_argocd_branch_fetch_failure_is_fatal(lab):
    _git(lab["repo"], "remote", "set-url", "origin", str(lab["tmp"] / "gone.git"))
    r = run(lab, "--argocd", "main", "--values", "environments/crc.yaml")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "could not fetch origin/main" in r.stderr
    assert "helm" not in calls(lab) and "oc" not in calls(lab)


def test_argocd_branch_values_must_exist_on_origin(lab):
    (lab["repo"] / "environments" / "other.yaml").write_text("x: 1\n")
    _git(lab["repo"], "add", "-A"); _git(lab["repo"], "commit", "-qm", "other")   # committed, NOT pushed
    r = run(lab, "--argocd", "main", "--values", "environments/other.yaml")
    assert r.returncode == 1 and "does not exist on origin/main" in r.stderr


def test_argocd_head_values_must_be_committed_and_clean(lab):
    (lab["repo"] / "environments" / "other.yaml").write_text("x: 1\n")
    r = run(lab, "--argocd", "--values", "environments/other.yaml")
    assert r.returncode == 1 and "is not committed" in r.stderr
    _git(lab["repo"], "add", "-A"); _git(lab["repo"], "commit", "-qm", "other")
    (lab["repo"] / "environments" / "other.yaml").write_text("x: 2\n")
    r = run(lab, "--argocd", "--values", "environments/other.yaml")
    assert r.returncode == 1 and "has uncommitted changes" in r.stderr


# --- the image: reuse decided before building, on both tags ------------------------------------

def test_both_tags_present_means_no_build_and_no_push(lab):
    synced_status(lab, lab["full"])
    tag = f"{_version()}-{lab['full'][:10]}"
    r = run(lab, "--argocd", STUB_ISTAGS=f"group-sync-dashboard:{tag} group-sync-dashboard-report:{tag}")
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(lab)
    assert "podman build" not in log and "podman push" not in log
    assert "reused" in r.stdout and "verified in-pod" in r.stdout


def test_one_tag_missing_rebuilds_and_pushes_both(lab):
    synced_status(lab, lab["full"])
    tag = f"{_version()}-{lab['full'][:10]}"
    r = run(lab, "--argocd", STUB_ISTAGS=f"group-sync-dashboard:{tag}")
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(lab)
    assert log.count("podman build") == 2 and log.count("podman push") == 2


def test_build_only_builds_and_never_pushes(lab):
    r = run(lab, "--build-only")
    assert r.returncode == 0, r.stderr
    log = calls(lab)
    assert log.count("podman build") == 2
    assert "podman login" not in log and "podman push" not in log and "oc " not in log


# --- the Application write: one apply, the file's values merged in -----------------------------

def test_argocd_writes_the_application_once_with_everything_in_it(lab):
    synced_status(lab, lab["full"])
    (lab["repo"] / "environments" / "other.yaml").write_text("x: 1\n")
    _git(lab["repo"], "add", "-A"); _git(lab["repo"], "commit", "-qm", "other"); _git(lab["repo"], "push", "-q")
    full = _git(lab["repo"], "rev-parse", "HEAD")
    synced_status(lab, full)
    r = run(lab, "--argocd", "--values", "environments/other.yaml", STUB_COMMIT=full[:10])
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(lab)
    assert "oc patch application" not in log, "no server-side patch after an apply"
    assert log.count("oc apply -f -") == 1
    patch_line = next(l for l in log.splitlines() if l.startswith("oc patch --local"))
    patch = json.loads(patch_line.split(" -p ", 1)[1].split(" -o json")[0])
    assert patch["spec"]["source"]["targetRevision"] == full[:10]
    assert patch["spec"]["source"]["helm"]["valueFiles"] == ["../../environments/other.yaml"]
    names = [p["name"] for p in patch["spec"]["source"]["helm"]["parameters"]]
    assert names == ["image.repository", "image.tag", "reporting.image.repository", "reporting.image.tag"]
    assert "argocd.argoproj.io/refresh=normal" in log


def test_argocd_branch_clears_the_image_parameters_and_waits_for_its_commit(lab):
    synced_status(lab, lab["full"])
    r = run(lab, "--argocd", "main")
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(lab)
    assert "podman" not in log
    patch_line = next(l for l in log.splitlines() if l.startswith("oc patch --local"))
    patch = json.loads(patch_line.split(" -p ", 1)[1].split(" -o json")[0])
    assert patch["spec"]["source"] == {"targetRevision": "main", "helm": {"parameters": []}}
    # the branch moved on origin but the Application's `main` did not: the old status must not satisfy the waiter
    synced_status(lab, "0" * 40)
    r = run(lab, "--argocd", "main", ARGOCD_WAIT_INTERVAL="1")
    assert r.returncode == 1, "the waiter accepted a status for a commit that is not origin/main"


# --- the waiter on its own ----------------------------------------------------------------------

def wait(lab, *args: str, **env_over: str) -> subprocess.CompletedProcess:
    return subprocess.run(["bash", str(lab["repo"] / "local-development" / "argocd-wait.sh"), "app", "ns", *args],
                          cwd=lab["repo"] / "local-development", env={**lab["env"], **env_over}, capture_output=True, text=True)


def test_waiter_rejects_a_status_computed_for_the_previous_spec(lab):
    synced_status(lab, "abc")
    d = json.loads((lab["tmp"] / "app-status.json").read_text())
    d["spec"]["source"]["targetRevision"] = "def"          # spec changed; comparedTo still the old one
    (lab["tmp"] / "app-status.json").write_text(json.dumps(d))
    r = wait(lab, "2")
    assert r.returncode == 1 and "status is for the previous spec" in r.stdout


def test_waiter_matches_the_expected_commit_by_prefix_either_way(lab):
    synced_status(lab, "0123456789abcdef" * 2 + "01234567")
    assert wait(lab, "2", "0123456789").returncode == 0                       # short expected, full status
    synced_status(lab, "0123456789")
    assert wait(lab, "2", "0123456789abcdef" * 2 + "01234567").returncode == 0  # full expected, short status
    r = wait(lab, "2", "fedcba9876")
    assert r.returncode == 1 and "want fedcba9876" in r.stdout


def test_waiter_survives_an_unavailable_api(lab):
    r = wait(lab, "2", STUB_APP_JSON="/nonexistent/app.json")
    assert r.returncode == 1
    assert "application status unavailable" in r.stdout and "did not reach" in r.stderr


# --- the docs tell the truth --------------------------------------------------------------------

def test_the_matrix_rows_match_the_script():
    header = (LOCAL_DEV / "release-crc.sh").read_text()
    readme = (LOCAL_DEV / "README.md").read_text()
    assert "built + pushed" not in header and "built + pushed" not in readme
    assert "built, NOT pushed" in header and "built, **not** pushed" in readme
    assert header.index('if [ "$BUILD_ONLY" = true ]; then exit 0; fi') < header.index("podman login")


def _version() -> str:
    import re
    return re.search(r'^version = "(.+?)"', (LOCAL_DEV / "pyproject.toml").read_text(), re.M).group(1)
