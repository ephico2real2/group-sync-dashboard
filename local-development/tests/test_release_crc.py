"""release-crc.sh and argocd-wait.sh, driven end to end against stubs.

A temporary repository (with a bare `origin`) carries the files the script reads; `oc`, `podman`
and `helm` are stubs on PATH that log their arguments to one file and answer from environment
variables. Real git, real bash, the real scripts — only the cluster and the container engine are
replaced. RELEASE_CRC_UNDER_TEST points the tests at another copy of the script (the failing-before
evidence in the review record was produced that way).
"""
from __future__ import annotations

import hashlib
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
REAL_OC = shutil.which("oc")   # found before the stubs go on PATH
LINUX_IMAGES = "--filter-by-os=linux/.* --show-multiarch -o json"   # how release-crc.sh asks oc for every Linux image

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
  "oc get application "*" -o name")
      case "${STUB_APP_EXISTS:-notfound}" in
        present) echo application.argoproj.io/group-sync-dashboard ;;
        notfound) echo 'Error from server (NotFound): applications.argoproj.io "group-sync-dashboard" not found' >&2; exit 1 ;;
        *) echo 'error: You must be logged in to the server (Unauthorized)' >&2; exit 1 ;;
      esac ;;
  "oc get application "*) exit 0 ;;
  "oc image info "*)     # the registry: STUB_IMAGES is "<ref>=<org.opencontainers.image.version> ..."; an unlisted ref is absent
      # STUB_OCI_DIR: the real oc reads a manifest list from its on-disk registry instead, same flags.
      [ -n "${STUB_OCI_DIR:-}" ] && exec "$STUB_REAL_OC" image info --dir "$STUB_OCI_DIR" file://review/multi:good "${@:4}"
      for entry in $STUB_IMAGES; do
        case "$entry" in "${3}="*) printf '{"digest":"sha256:stub","config":{"config":{"Labels":{"org.opencontainers.image.version":"%s"}}}}\n' "${entry#*=}"; exit 0 ;; esac
      done
      echo "error: unable to read image ${3}: manifest unknown" >&2; exit 1 ;;
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
    # The chart the branch path reads at origin/<branch>: the same lines helm.yaml reads from the same files.
    (repo / "charts" / "group-sync-dashboard").mkdir(parents=True)
    (repo / "charts" / "group-sync-dashboard" / "Chart.yaml").write_text(
        f'apiVersion: v2\nname: group-sync-dashboard\nversion: 0.1.0\nappVersion: "{_version()}"\n')
    (repo / "charts" / "group-sync-dashboard" / "values.yaml").write_text(
        "image:\n  repository: quay.io/example/group-sync-dashboard\n  tag: \"\"\n"
        "reporting:\n  image:\n    repository: quay.io/example/group-sync-dashboard-report\n    tag: \"\"\n")
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
        # The registry as publish.yml leaves it after the release merge: both aliases carry this version.
        "STUB_IMAGES": f"quay.io/example/group-sync-dashboard:{_version()}={_version()} "
                       f"quay.io/example/group-sync-dashboard-report:{_version()}={_version()}",
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
    r = run(lab, "--values", "environments/crc-local.yaml")
    assert r.returncode == 0, r.stderr
    assert "dirty" not in r.stdout + r.stderr
    assert f"-f {lab['repo']}/environments/crc-local.yaml" in calls(lab)
    # a regex over porcelain would have exempted this file too: `.` matched any character
    (lab["repo"] / "environments" / "crc-localXyaml").write_text("x: 1\n")
    r = run(lab, "--values", "environments/crc-local.yaml")
    assert r.returncode == 1 and "uncommitted changes" in r.stderr


def test_a_values_file_under_local_development_is_still_dirty(lab):
    (lab["repo"] / "local-development" / "mine.yaml").write_text("x: 1\n")
    r = run(lab, "--values", "local-development/mine.yaml")
    assert r.returncode == 1 and "uncommitted changes" in r.stderr


def test_a_missing_helm_values_file_is_refused_before_any_build(lab):
    r = run(lab, "--values", "environments/nope.yaml")
    assert r.returncode == 1 and "no release values file" in r.stderr
    assert "podman" not in calls(lab)


def test_build_only_refuses_argocd_and_values_and_a_dash_revision_is_not_one(lab):
    for args in (("--argocd", "main", "--build-only"), ("--build-only", "--argocd"), ("--values", "environments/crc.yaml", "--build-only")):
        r = run(lab, *args)
        assert r.returncode == 2 and "do not apply to a build" in r.stderr, args
    r = run(lab, "--argocd", "-x")
    assert r.returncode == 2 and "unknown argument: -x" in r.stderr
    assert calls(lab) == ""


def test_helm_mode_probe_accepts_only_notfound_as_absent(lab):
    r = run(lab, STUB_APP_EXISTS="unauthorized")
    assert r.returncode == 1 and "cannot tell whether Application" in r.stderr
    assert "helm upgrade" not in calls(lab)
    r = run(lab, STUB_APP_EXISTS="present")
    assert r.returncode == 0, r.stderr
    assert "oc delete application" in calls(lab) and "helm upgrade" in calls(lab)


def test_helm_mode_takes_the_fields_argo_left_on_the_surviving_objects(lab):
    # The PVCs outlive the handover with argocd-controller owning their labels; a chart bump makes
    # Helm 4's server-side apply refuse them unless the install forces its own values (CRC, 0.53.0).
    r = run(lab, STUB_APP_EXISTS="present")
    assert r.returncode == 0, r.stderr
    upgrade = [line for line in calls(lab).splitlines() if line.startswith("helm upgrade --install")]
    assert len(upgrade) == 1 and "--force-conflicts" in upgrade[0].split(), upgrade


# --- the Argo values checks --------------------------------------------------------------------

def test_argocd_branch_fetch_failure_is_fatal(lab):
    _git(lab["repo"], "remote", "set-url", "origin", str(lab["tmp"] / "gone.git"))
    r = run(lab, "--argocd", "main", "--values", "environments/crc.yaml")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "branch main is not on origin, or origin is unreachable" in r.stderr
    assert "helm" not in calls(lab) and "oc" not in calls(lab)


def test_argocd_branch_works_in_a_single_branch_clone(lab):
    _git(lab["repo"], "config", "remote.origin.fetch", "+refs/heads/main:refs/remotes/origin/main")
    _git(lab["repo"], "checkout", "-qb", "topic")
    (lab["repo"] / "environments" / "topic.yaml").write_text("x: 1\n")
    _git(lab["repo"], "add", "-A"); _git(lab["repo"], "commit", "-qm", "topic"); _git(lab["repo"], "push", "-q", "origin", "topic")
    synced_status(lab, _git(lab["repo"], "rev-parse", "HEAD"))
    r = run(lab, "--argocd", "topic", "--values", "environments/topic.yaml")
    assert r.returncode == 0, r.stdout + r.stderr          # refs/remotes/origin/topic never exists here; FETCH_HEAD does


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


# --- the published image the branch path hands to Argo (#410) -----------------------------------

def _stale_alias(lab, image: str, version: str) -> None:
    """`:<appVersion>` of `image` exists but is another build: a chart-version label on an old image."""
    ref = f"quay.io/example/{image}:{_version()}"
    entries = [e for e in lab["env"]["STUB_IMAGES"].split() if not e.startswith(f"{ref}=")]
    lab["env"]["STUB_IMAGES"] = " ".join(entries + [f"{ref}={version}"])


def test_argocd_branch_refuses_an_alias_that_is_another_application_version(lab):
    """#410 as measured on quay: `:0.39.0` existed before application 0.39.0 and was application 0.24.0."""
    synced_status(lab, lab["full"])
    _stale_alias(lab, "group-sync-dashboard", "0.24.0")
    r = run(lab, "--argocd", "main")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"quay.io/example/group-sync-dashboard:{_version()} is application 0.24.0, not {_version()} (#410)" in r.stderr
    log = calls(lab)
    assert "helm uninstall" not in log and "oc patch" not in log and "oc apply" not in log, log


def test_argocd_branch_refuses_a_stale_report_alias_too(lab):
    """The chart resolves both images at appVersion; the report pod refuses a newer snapshot, so an old one 503s."""
    synced_status(lab, lab["full"])
    _stale_alias(lab, "group-sync-dashboard-report", "0.24.0")
    r = run(lab, "--argocd", "main")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"group-sync-dashboard-report:{_version()} is application 0.24.0" in r.stderr
    assert "oc apply" not in calls(lab)


def test_argocd_branch_refuses_an_alias_publish_has_not_pushed_yet(lab):
    synced_status(lab, lab["full"])
    r = run(lab, "--argocd", "main", STUB_IMAGES="")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"quay.io/example/group-sync-dashboard:{_version()} is not in the registry" in r.stderr
    assert "--release-tags" in r.stderr
    assert "oc apply" not in calls(lab)


def _pin_on_branch(lab, branch: str, dashboard_tag: str, report_tag: str) -> None:
    """Commit values.yaml with these two tags on origin/<branch>, the checkout left on main."""
    _git(lab["repo"], "checkout", "-qb", branch)
    (lab["repo"] / "charts" / "group-sync-dashboard" / "values.yaml").write_text(
        f'image:\n  repository: quay.io/example/group-sync-dashboard\n  tag: "{dashboard_tag}"\n'
        f'reporting:\n  image:\n    repository: quay.io/example/group-sync-dashboard-report\n    tag: "{report_tag}"\n')
    _git(lab["repo"], "add", "-A"); _git(lab["repo"], "commit", "-qm", branch); _git(lab["repo"], "push", "-q", "origin", branch)
    _git(lab["repo"], "checkout", "-q", "main")
    synced_status(lab, _git(lab["repo"], "rev-parse", branch))


def test_argocd_branch_reads_the_chart_at_the_branch_not_the_checkout(lab):
    """A pin on origin/<branch> is the operator's choice: deployed as pinned, whatever the local tree says."""
    _pin_on_branch(lab, "pin", "0.9.9-abcdef1234", "0.9.9-abcdef1234")
    r = run(lab, "--argocd", "pin", STUB_IMAGES="")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "pinned in values.yaml" in r.stdout
    assert "oc image info" not in calls(lab)


def test_argocd_branch_deploys_when_both_aliases_are_the_release(lab):
    synced_status(lab, lab["full"])
    r = run(lab, "--argocd", "main")
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(lab)
    assert f"oc image info quay.io/example/group-sync-dashboard:{_version()} {LINUX_IMAGES}" in log
    assert f"oc image info quay.io/example/group-sync-dashboard-report:{_version()} {LINUX_IMAGES}" in log
    assert log.index("oc image info") < log.index("oc patch --local"), "the registry is read before the Application is written"


def test_argocd_branch_still_checks_report_when_only_the_dashboard_tag_is_pinned(lab):
    """image.tag pinned is the operator's choice for the dashboard only; the report still resolves appVersion."""
    _pin_on_branch(lab, "dashpin", "0.9.9-abcdef1234", "")
    _stale_alias(lab, "group-sync-dashboard-report", "0.24.0")
    r = run(lab, "--argocd", "dashpin")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"group-sync-dashboard-report:{_version()} is application 0.24.0" in r.stderr
    assert "oc apply" not in calls(lab)


def test_argocd_branch_skips_only_the_pinned_report_alias(lab):
    """reporting.image.tag pinned, image.tag empty: check the dashboard alias, not the unused report alias."""
    _pin_on_branch(lab, "reppin", "", "0.9.9-abcdef1234")
    r = run(lab, "--argocd", "reppin", STUB_IMAGES=f"quay.io/example/group-sync-dashboard:{_version()}={_version()}")
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(lab)
    assert f"oc image info quay.io/example/group-sync-dashboard:{_version()} {LINUX_IMAGES}" in log
    assert "group-sync-dashboard-report" not in log
    assert "pinned in values.yaml" in r.stdout


def test_argocd_branch_reads_the_shipped_values_file(lab):
    """The real values.yaml (150 KB, reporting.image.tag commented, secretsMint's tag first): both aliases checked."""
    shipped = (REPO / "charts" / "group-sync-dashboard" / "values.yaml").read_text()
    (lab["repo"] / "charts" / "group-sync-dashboard" / "values.yaml").write_text(shipped.replace("quay.io/ephico2real/", "quay.io/example/"))
    _git(lab["repo"], "commit", "-qam", "shipped values"); _git(lab["repo"], "push", "-q", "origin", "main")
    synced_status(lab, _git(lab["repo"], "rev-parse", "HEAD"))
    r = run(lab, "--argocd", "main")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"group-sync-dashboard-report:{_version()} is application {_version()}" in r.stdout


def _manifest_list(directory: Path, arm64_version: str) -> Path:
    """oc's on-disk registry (`--dir`, file://review/multi:good): a linux/amd64 + linux/arm64 manifest list."""
    root = directory / "v2" / "review" / "multi"
    (root / "manifests").mkdir(parents=True)
    (root / "blobs").mkdir()

    def blob(obj: dict, kind: str) -> dict:
        data = json.dumps(obj, separators=(",", ":")).encode()
        digest = "sha256:" + hashlib.sha256(data).hexdigest()
        (root / kind / digest).write_bytes(data)
        return {"mediaType": obj.get("mediaType", "application/vnd.docker.container.image.v1+json"),
                "size": len(data), "digest": digest}

    children = []
    for arch, version in (("amd64", _version()), ("arm64", arm64_version)):
        config = blob({"architecture": arch, "os": "linux", "rootfs": {"type": "layers", "diff_ids": []},
                       "config": {"Labels": {"org.opencontainers.image.version": version}}}, "blobs")
        child = blob({"schemaVersion": 2, "mediaType": "application/vnd.docker.distribution.manifest.v2+json",
                      "config": config, "layers": []}, "manifests")
        children.append({**child, "platform": {"architecture": arch, "os": "linux"}})
    index = blob({"schemaVersion": 2, "mediaType": "application/vnd.docker.distribution.manifest.list.v2+json",
                  "manifests": children}, "manifests")
    (root / "manifests" / "good").symlink_to(index["digest"])
    return directory


@pytest.mark.skipif(REAL_OC is None, reason="oc is not installed")
@pytest.mark.parametrize("arm64_version, deploys", [(None, True), ("0.24.0", False)], ids=["every-child-is-the-release", "stale-arm64-child"])
def test_argocd_branch_reads_every_linux_image_of_a_manifest_list(lab, arm64_version, deploys):
    """The real oc refuses a manifest list without --filter-by-os, and a workstation is not the node's OS."""
    synced_status(lab, lab["full"])
    oci = _manifest_list(lab["tmp"] / "oci", arm64_version or _version())
    r = run(lab, "--argocd", "main", STUB_OCI_DIR=str(oci), STUB_REAL_OC=REAL_OC)
    assert (r.returncode == 0) is deploys, r.stdout + r.stderr
    if not deploys:
        assert "0.24.0" in next(line for line in r.stderr.splitlines() if "is application" in line)
        assert "oc apply" not in calls(lab)


# --- the opt-in: the lab deploys what promote.yml read back (#598) --------------------------------

DASHBOARD_DIGEST, REPORT_DIGEST = "sha256:" + "a" * 64, "sha256:" + "b" * 64
PROMOTION = (f"image:\n  repository: quay.io/example/group-sync-dashboard\n  digest: {DASHBOARD_DIGEST}\n"
             f"reporting:\n  image:\n    repository: quay.io/example/group-sync-dashboard-report\n    digest: {REPORT_DIGEST}\n")


def _release_branch(lab, promotion: str | None) -> None:
    """origin/release as promote.yml writes it: the chart, environments/ and promotion.yaml (or none)."""
    _git(lab["repo"], "checkout", "-qb", "release")
    if promotion is not None:
        (lab["repo"] / "promotion.yaml").write_text(promotion)
    _git(lab["repo"], "add", "-A"); _git(lab["repo"], "commit", "-q", "--allow-empty", "-m", "promote: main")
    _git(lab["repo"], "push", "-q", "origin", "release")
    _git(lab["repo"], "checkout", "-q", "main")
    synced_status(lab, _git(lab["repo"], "rev-parse", "release"))


def test_argocd_release_without_a_promotion_is_refused_before_anything_is_written(lab):
    _release_branch(lab, None)
    r = run(lab, "--argocd", "release")
    assert r.returncode == 1, r.stdout + r.stderr
    assert "origin/release has no promotion.yaml" in r.stderr
    log = calls(lab)
    assert "helm uninstall" not in log and "oc patch" not in log and "oc apply" not in log, log


def test_argocd_release_reads_the_pinned_digests_back_and_lists_promotion_yaml_last(lab):
    _release_branch(lab, PROMOTION)
    r = run(lab, "--argocd", "release",
            STUB_IMAGES=f"quay.io/example/group-sync-dashboard@{DASHBOARD_DIGEST}={_version()} "
                        f"quay.io/example/group-sync-dashboard-report@{REPORT_DIGEST}={_version()}")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "the digests in promotion.yaml" in r.stdout
    log = calls(lab)
    assert f"oc image info quay.io/example/group-sync-dashboard@{DASHBOARD_DIGEST} {LINUX_IMAGES}" in log
    assert f"oc image info quay.io/example/group-sync-dashboard-report@{REPORT_DIGEST} {LINUX_IMAGES}" in log
    assert f":{_version()} " not in log, "the aliases are not what release deploys"
    patch_line = next(l for l in log.splitlines() if l.startswith("oc patch --local"))
    patch = json.loads(patch_line.split(" -p ", 1)[1].split(" -o json")[0])
    assert patch["spec"]["source"] == {"targetRevision": "release", "helm": {
        "parameters": [], "valueFiles": ["../../environments/crc.yaml", "../../promotion.yaml"]}}


def test_argocd_release_refuses_a_pinned_digest_that_is_not_the_release(lab):
    _release_branch(lab, PROMOTION)
    r = run(lab, "--argocd", "release",
            STUB_IMAGES=f"quay.io/example/group-sync-dashboard@{DASHBOARD_DIGEST}={_version()} "
                        f"quay.io/example/group-sync-dashboard-report@{REPORT_DIGEST}=0.24.0")
    assert r.returncode == 1, r.stdout + r.stderr
    assert f"group-sync-dashboard-report@{REPORT_DIGEST} is application 0.24.0" in r.stderr
    assert "oc apply" not in calls(lab)


def test_argocd_main_after_release_returns_to_the_files_values_and_the_aliases(lab):
    """main stays the dev-phase default (#598): switching back sends no promotion.yaml and reads the aliases."""
    _release_branch(lab, PROMOTION)
    synced_status(lab, lab["full"])
    r = run(lab, "--argocd", "main")
    assert r.returncode == 0, r.stdout + r.stderr
    log = calls(lab)
    assert f"oc image info quay.io/example/group-sync-dashboard:{_version()} {LINUX_IMAGES}" in log
    patch_line = next(l for l in log.splitlines() if l.startswith("oc patch --local"))
    patch = json.loads(patch_line.split(" -p ", 1)[1].split(" -o json")[0])
    assert patch["spec"]["source"] == {"targetRevision": "main", "helm": {"parameters": []}}


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


def test_waiter_reads_an_empty_field_as_argo_cd_does(lab):
    """#534: the branch path writes `helm.parameters: []`, and Argo CD writes status.sync.comparedTo from Go structs whose
    fields are `omitempty` (argo-cd v3.4.7 types.go L542), so the empty list is absent there. The same source with and
    without the empty key is the current comparison; another values file is still the previous spec."""
    synced_status(lab, "abc")
    d = json.loads((lab["tmp"] / "app-status.json").read_text())
    d["spec"]["source"]["helm"] = {"parameters": [], "valueFiles": ["../../environments/crc.yaml"]}
    d["status"]["sync"]["comparedTo"]["source"]["helm"] = {"valueFiles": ["../../environments/crc.yaml"]}
    (lab["tmp"] / "app-status.json").write_text(json.dumps(d))
    assert wait(lab, "2", "abc").returncode == 0
    d["status"]["sync"]["comparedTo"]["source"]["helm"]["valueFiles"] = ["../../environments/other.yaml"]
    (lab["tmp"] / "app-status.json").write_text(json.dumps(d))
    r = wait(lab, "2", "abc")
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


def test_argocd_release_deploys_a_pinned_tag_as_promote_yml_pinned_it(lab):
    """Review of #614 (OB2 F3): promote.yml pins a values.yaml tag's digest without a label check (SPEC_P1 note 8), so
    `--argocd release` must deploy that digest as pinned, and still read the unpinned report image back."""
    values = lab["repo"] / "charts" / "group-sync-dashboard" / "values.yaml"
    pinned = values.read_text().replace('\n  tag: ""\n', '\n  tag: "1.4.0"\n', 1)
    assert 'tag: "1.4.0"' in pinned
    values.write_text(pinned)
    _release_branch(lab, PROMOTION)
    r = run(lab, "--argocd", "release",
            STUB_IMAGES=f"quay.io/example/group-sync-dashboard@{DASHBOARD_DIGEST}=0.24.0 "
                        f"quay.io/example/group-sync-dashboard-report@{REPORT_DIGEST}={_version()}")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "pinned in values.yaml" in r.stdout and DASHBOARD_DIGEST in r.stdout, r.stdout
    log = calls(lab)
    assert f"oc image info quay.io/example/group-sync-dashboard@{DASHBOARD_DIGEST}" not in log
    assert f"oc image info quay.io/example/group-sync-dashboard-report@{REPORT_DIGEST} {LINUX_IMAGES}" in log


def _version() -> str:
    import re
    return re.search(r'^version = "(.+?)"', (LOCAL_DEV / "pyproject.toml").read_text(), re.M).group(1)
