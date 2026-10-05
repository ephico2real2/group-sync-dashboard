"""promote.yml: the `release` branch holds only what was read back from the registry (#598, SPEC_P1).

The promotion step and the push step are RUN, as GitHub runs `shell: bash`, in a real git repository with a bare
`origin`, against test_supply_chain.py's stub skopeo and a stub cosign. Real git writes and pushes the `release`
commit; only the registry and Sigstore are replaced. The workflow's shape (its triggers, its scopes, its one writer)
is read from the YAML.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import shlex
import shutil
import subprocess

import pytest
import yaml

from test_supply_chain import APP, CHART_FILE, DASHBOARD, HELM, PUBLISH, REPORT, SKOPEO_STUB, VALUES_FILE, _jobs, _push, _released, _step

REPO = pathlib.Path(__file__).resolve().parents[2]
PROMOTE = REPO / ".github" / "workflows" / "promote.yml"
APPLICATION = REPO / "gitops" / "argocd-application-dashboard.yaml"
RELEASE_CRC = REPO / "local-development" / "release-crc.sh"
PUBLISHER = REPO / "local-development" / "build-and-push-external.sh"
GITOPS_README = REPO / "gitops" / "README.md"
STEP = "Read both images back and promote"
PUSH_STEP = "Push release"
IDENTITY = "https://github.com/ephico2real2/group-sync-dashboard/.github/workflows/publish.yml@refs/heads/main"

COSIGN_STUB = r'''#!/usr/bin/env bash
printf 'cosign %s\n' "$*" >> "$STUB_LOG"
for ref in $STUB_UNSIGNED; do [ "${@: -1}" = "$ref" ] && { echo "no signatures found" >&2; exit 1; }; done
exit 0
'''


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: pathlib.Path, message: str, files: dict[str, str]) -> str:
    for name, text in files.items():
        (repo / name).parent.mkdir(parents=True, exist_ok=True)
        (repo / name).write_text(text)
    _git(repo, "add", "-A")
    _git(repo, "commit", "-qm", message)
    _git(repo, "push", "-q", "origin", "main")
    return _git(repo, "rev-parse", "HEAD")


def _chart(version: str) -> str:
    return CHART_FILE.read_text().replace(f'\nappVersion: "{APP}"\n', f'\nappVersion: "{version}"\n', 1)


@pytest.fixture
def lab(tmp_path: pathlib.Path):
    """main with the real chart files, environments/ and files release must not carry; origin's `release` is the
    operator's one-time orphan commit with an empty tree."""
    repo, origin = tmp_path / "repo", tmp_path / "origin.git"
    repo.mkdir()
    _git(tmp_path, "init", "-q", "--bare", str(origin))
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.email", "t@example.invalid")
    _git(repo, "config", "user.name", "t")
    _git(repo, "remote", "add", "origin", str(origin))
    _commit(repo, "base", {
        "charts/group-sync-dashboard/Chart.yaml": _chart("0.0.1"),
        "charts/group-sync-dashboard/values.yaml": VALUES_FILE.read_text(),
        "charts/group-sync-dashboard/templates/x.yaml": "kind: ConfigMap\n",
        "charts/openshift-grafana/Chart.yaml": "name: openshift-grafana\n",
        "environments/crc.yaml": "logLevel: DEBUG\n",
        "local-development/README.md": "base image input\n",
        "local-development/app.py": "print('code')\n",
        ".github/workflows/ci.yml": "name: ci\n",
    })
    empty = _git(repo, "hash-object", "-t", "tree", "-w", "/dev/null")
    start = _git(repo, "commit-tree", empty, "-m", "release starts empty")
    _git(repo, "push", "-q", "origin", f"{start}:refs/heads/release")
    bindir = tmp_path / "bin"
    bindir.mkdir()
    for tool, stub in (("skopeo", SKOPEO_STUB), ("cosign", COSIGN_STUB)):
        (bindir / tool).write_text(stub)
        (bindir / tool).chmod(0o755)
    (tmp_path / "step.sh").write_text(_step(_jobs(PROMOTE)["promote"], STEP)["run"])
    (tmp_path / "push.sh").write_text(_step(_jobs(PROMOTE)["promote"], PUSH_STEP)["run"])
    return {"repo": repo, "origin": origin, "tmp": tmp_path, "bin": bindir, "start": start}


def promote(lab, registry: dict, *, event: str = "dispatch", run_sha: str = "", sha: str = "", rollback: bool = False,
            signing: str = "", unsigned: str = "", mirror_immutable: bool = True, unreachable: str = "",
            extra_path: str = "") -> tuple[subprocess.CompletedProcess, str]:
    state, log = lab["tmp"] / "registry.json", lab["tmp"] / "calls.log"
    # publish.yml always writes <appVersion>-<10-char sha>. Most tests start from the release aliases, so mirror
    # those exact digests under the immutable names the workflow now resolves. A race test disables this to model
    # main moving past the publish run that just completed.
    if mirror_immutable:
        target = sha or _git(lab["repo"], "rev-parse", "origin/main")
        image_commit = _git(lab["repo"], "log", "--first-parent", "-1", "--format=%H", target, "--",
                            "local-development/README.md")
        version = re.search(r'appVersion: "([0-9.]+)"', _git(lab["repo"], "show", f"{target}:charts/group-sync-dashboard/Chart.yaml")).group(1)
        for image in (DASHBOARD, REPORT):
            digest = registry["tags"].get(f"{image}:{version}")
            if digest:
                registry["tags"][f"{image}:{version}-{image_commit[:10]}"] = digest
    state.write_text(json.dumps(registry))
    log.write_text("")
    path = f"{extra_path}:" if extra_path else ""
    env = {**os.environ, "PATH": f"{path}{lab['bin']}:{os.environ['PATH']}", "STUB_REGISTRY": str(state), "STUB_LOG": str(log),
           "STUB_UNREACHABLE": unreachable, "STUB_UNSIGNED": unsigned, "REGISTRY": "quay.io", "REGISTRY_NAMESPACE": "example",
           "SIGNING": signing, "EVENT": event, "RUN_SHA": run_sha, "SHA": sha, "ROLLBACK": "true" if rollback else "false",
           "IDENTITY": IDENTITY, "ISSUER": "https://token.actions.githubusercontent.com"}
    done = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(lab["tmp"] / "step.sh")],
                          cwd=lab["repo"], env=env, capture_output=True, text=True)
    if done.returncode == 0:   # Actions runs "Push release" only after the step above succeeded
        pushed = subprocess.run(["bash", "--noprofile", "--norc", "-eo", "pipefail", str(lab["tmp"] / "push.sh")],
                                cwd=lab["repo"], env={**env, "RELEASE_DEPLOY_KEY": "test-only"},
                                capture_output=True, text=True)
        done = subprocess.CompletedProcess(done.args, pushed.returncode, done.stdout + pushed.stdout,
                                           done.stderr + pushed.stderr)
    return done, log.read_text()


def release(lab) -> str:
    return _git(lab["origin"], "rev-parse", "refs/heads/release")


def promotion(lab) -> dict:
    return yaml.safe_load(_git(lab["origin"], "show", "release:promotion.yaml"))


def _main_at(lab, version: str) -> str:
    return _commit(lab["repo"], f"application {version}", {"charts/group-sync-dashboard/Chart.yaml": _chart(version),
                                                           "local-development/README.md": f"application {version}\n"})


# ── What a promotion writes ───────────────────────────────────────────────────────────────────


def test_a_publish_completion_promotes_main_with_both_images_pinned_by_digest(lab) -> None:
    tip = _main_at(lab, APP)
    registry = _released()
    done, log = promote(lab, registry, event="workflow_run", run_sha=tip)
    assert done.returncode == 0, done.stdout + done.stderr
    head = release(lab)
    assert _git(lab["origin"], "log", "-1", "--format=%s", head) == f"promote: main {tip}"
    assert _git(lab["origin"], "rev-parse", f"{head}^") == lab["start"], "a fast-forward of what release held"
    assert _git(lab["origin"], "ls-tree", "--name-only", head).split() == ["charts", "environments", "promotion.yaml"]
    assert _git(lab["origin"], "ls-tree", "--name-only", f"{head}:charts").split() == ["group-sync-dashboard"]
    assert _git(lab["origin"], "show", f"{head}:charts/group-sync-dashboard/Chart.yaml") == _chart(APP).rstrip("\n")
    pins = promotion(lab)
    assert pins == {"image": {"repository": DASHBOARD, "digest": registry["tags"][f"{DASHBOARD}:{APP}"]},
                    "reporting": {"image": {"repository": REPORT, "digest": registry["tags"][f"{REPORT}:{APP}"]}}}
    for name, digest in ((DASHBOARD, pins["image"]["digest"]), (REPORT, pins["reporting"]["image"]["digest"])):
        assert f"cosign verify --certificate-identity {IDENTITY} --certificate-oidc-issuer " \
               f"https://token.actions.githubusercontent.com {name}@{digest}" in log


def test_a_run_promotes_nothing_while_mains_version_is_still_being_published(lab) -> None:
    """The race #598 removes: a release merge moves appVersion before publish.yml has pushed it."""
    older = _main_at(lab, "0.9.0")
    tip = _main_at(lab, APP)
    for event, run_sha in (("push", ""), ("workflow_run", older)):
        done, log = promote(lab, {"tags": {}, "manifests": {}, "blobs": {}}, event=event, run_sha=run_sha)
        assert done.returncode == 0, done.stdout + done.stderr
        assert tip[:10] in done.stdout and "Nothing was promoted" in done.stdout
        assert ("skopeo" in log) is (event == "push")
        assert release(lab) == lab["start"]


def test_a_push_after_publish_completion_promotes_if_the_workflow_run_was_replaced(lab) -> None:
    """GitHub concurrency keeps one pending run; a later push may replace the publish completion (review of #613, F1)."""
    tip = _main_at(lab, APP)
    done, _ = promote(lab, _released(), event="push")
    assert done.returncode == 0, done.stdout + done.stderr
    assert _git(lab["origin"], "log", "-1", "--format=%s", "release") == f"promote: main {tip}"


def test_a_chart_merge_after_a_rollback_returns_release_to_main(lab) -> None:
    """A rollback must not make later chart-only promotions stick on the rolled-back version (review of #613, F1)."""
    older = _main_at(lab, "0.9.0")
    _main_at(lab, APP)
    registry = _released()
    _push(registry, DASHBOARD, "0.9.0", "0.9.0")
    _push(registry, REPORT, "0.9.0", "0.9.0")
    assert promote(lab, registry)[0].returncode == 0
    assert promote(lab, registry, sha=older, rollback=True)[0].returncode == 0
    chart_only = _commit(lab["repo"], "a template", {"charts/group-sync-dashboard/templates/x.yaml": "kind: Secret\n"})
    done, _ = promote(lab, registry, event="push")
    assert done.returncode == 0, done.stdout + done.stderr
    assert _git(lab["origin"], "log", "-1", "--format=%s", "release") == f"promote: main {chart_only}"
    assert promotion(lab)["image"]["digest"] == registry["tags"][f"{DASHBOARD}:{APP}"]


def test_an_older_publish_completion_cannot_promote_a_later_same_version_image_change(lab) -> None:
    """Two PRs that chose the same next MINOR: the older image must not ride the later tree (review of #613, F2)."""
    first = _main_at(lab, APP)
    second = _commit(lab["repo"], "parallel PR reused the version",
                     {"local-development/README.md": "a second image at the same version\n"})
    registry = _released()
    for image in (DASHBOARD, REPORT):
        registry["tags"][f"{image}:{APP}-{first[:10]}"] = registry["tags"][f"{image}:{APP}"]
    done, _ = promote(lab, registry, event="workflow_run", run_sha=first, mirror_immutable=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "Nothing was promoted" in done.stdout and second[:10] in done.stdout
    assert release(lab) == lab["start"]


def test_a_same_version_image_whose_alias_names_another_build_is_red(lab) -> None:
    """The second PR's own publish completion: its immutable image exists, but `:<appVersion>` is the first's."""
    _main_at(lab, APP)
    second = _commit(lab["repo"], "parallel PR reused the version",
                     {"local-development/README.md": "a second image at the same version\n"})
    registry = _released()
    for image in (DASHBOARD, REPORT):
        _push(registry, image, f"{APP}-{second[:10]}", APP, APP)
    done, _ = promote(lab, registry, event="workflow_run", run_sha=second, mirror_immutable=False)
    assert done.returncode == 1, done.stdout + done.stderr
    assert "A same-version image change reached main" in done.stdout
    assert release(lab) == lab["start"]


def test_a_chart_only_merge_carries_the_images_release_already_runs(lab) -> None:
    tip = _main_at(lab, APP)
    registry = _released()
    assert promote(lab, registry, event="workflow_run", run_sha=tip)[0].returncode == 0
    pins = promotion(lab)
    chart_only = _commit(lab["repo"], "a template", {"charts/group-sync-dashboard/templates/x.yaml": "kind: Secret\n"})
    done, _ = promote(lab, registry, event="push")
    assert done.returncode == 0, done.stdout + done.stderr
    assert _git(lab["origin"], "log", "-1", "--format=%s", "release") == f"promote: main {chart_only}"
    assert _git(lab["origin"], "show", "release:charts/group-sync-dashboard/templates/x.yaml") == "kind: Secret"
    assert promotion(lab) == pins


# ── What is refused, and changes nothing ──────────────────────────────────────────────────────


@pytest.mark.parametrize("image, versions", [(DASHBOARD, ("0.24.0",)), (REPORT, ("0.24.0",)), (DASHBOARD, (APP, "0.24.0"))],
                         ids=["stale-dashboard-alias", "stale-report-alias", "stale-arm64-child"])
def test_an_image_that_is_not_mains_application_is_refused(lab, image, versions) -> None:
    tip = _main_at(lab, APP)
    registry = _released()
    _push(registry, image, APP, *versions)
    done, _ = promote(lab, registry, event="workflow_run", run_sha=tip)
    assert done.returncode == 1, done.stdout + done.stderr
    assert image in done.stdout and "is application" in done.stdout and "0.24.0" in done.stdout
    assert release(lab) == lab["start"]


def test_a_signature_that_does_not_verify_is_refused_and_signing_off_skips_cosign(lab) -> None:
    tip = _main_at(lab, APP)
    registry = _released()
    report = f"{REPORT}@{registry['tags'][f'{REPORT}:{APP}']}"
    done, _ = promote(lab, registry, event="workflow_run", run_sha=tip, unsigned=report)
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"{report} carries no signature from publish.yml on main" in done.stdout
    assert release(lab) == lab["start"]
    done, log = promote(lab, registry, event="workflow_run", run_sha=tip, signing="false", unsigned=report)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "cosign" not in log


def test_an_older_commit_needs_rollback_and_the_same_tree_twice_changes_nothing(lab) -> None:
    older = _main_at(lab, "0.9.0")
    tip = _main_at(lab, APP)
    registry = _released()
    _push(registry, DASHBOARD, "0.9.0", "0.9.0")
    _push(registry, REPORT, "0.9.0", "0.9.0")
    assert promote(lab, registry)[0].returncode == 0
    promoted = release(lab)
    done, _ = promote(lab, registry)
    assert done.returncode == 0 and "nothing to promote" in done.stdout and release(lab) == promoted
    done, _ = promote(lab, registry, sha=older)
    assert done.returncode == 1 and "rollback checked" in done.stdout and release(lab) == promoted
    done, _ = promote(lab, registry, sha=older, rollback=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert _git(lab["origin"], "log", "-1", "--format=%s", "release") == f"promote: main {older}"
    assert promotion(lab)["image"]["digest"] == registry["tags"][f"{DASHBOARD}:0.9.0"]
    assert tip != older


def test_a_commit_that_is_not_on_main_is_refused(lab) -> None:
    _main_at(lab, APP)
    _git(lab["repo"], "checkout", "-qb", "topic")
    (lab["repo"] / "environments" / "crc.yaml").write_text("logLevel: INFO\n")
    _git(lab["repo"], "commit", "-qam", "topic")
    _git(lab["repo"], "push", "-q", "origin", "topic")
    done, _ = promote(lab, _released(), sha=_git(lab["repo"], "rev-parse", "HEAD"))
    assert done.returncode == 1 and "is not on main" in done.stdout
    assert release(lab) == lab["start"]


def test_without_a_release_branch_nothing_is_promoted(lab) -> None:
    _main_at(lab, APP)
    _git(lab["origin"], "update-ref", "-d", "refs/heads/release")
    done, log = promote(lab, _released())
    assert done.returncode == 1 and "origin has no release branch" in done.stdout
    assert "skopeo" not in log


def test_a_pinned_tag_is_promoted_as_pinned(lab) -> None:
    values = VALUES_FILE.read_text().replace('\n  tag: ""\n', '\n  tag: "1.4.0"\n', 1)
    _commit(lab["repo"], "pin", {"charts/group-sync-dashboard/values.yaml": values})
    _main_at(lab, APP)
    registry = _released()
    pinned = _push(registry, DASHBOARD, "1.4.0", "1.4.0")
    _push(registry, DASHBOARD, APP, "0.24.0")          # the unpinned alias is not what the chart deploys
    done, _ = promote(lab, registry)
    assert done.returncode == 0, done.stdout + done.stderr
    assert promotion(lab)["image"]["digest"] == pinned


def _mirror(lab, registry: dict, target: str) -> str:
    image_commit = _git(lab["repo"], "log", "--first-parent", "-1", "--format=%H", target, "--", "local-development/README.md")
    for image in (DASHBOARD, REPORT):
        registry["tags"][f"{image}:{APP}-{image_commit[:10]}"] = registry["tags"][f"{image}:{APP}"]
    return image_commit


def test_a_chart_push_during_a_registry_outage_is_red_not_a_green_notice(lab) -> None:
    """Review of #614 (OB2 F2): a chart-only merge has no publish run coming, so unreachable must not read as absent."""
    tip = _main_at(lab, APP)
    registry = _released()
    _mirror(lab, registry, tip)
    assert promote(lab, registry, event="workflow_run", run_sha=tip, mirror_immutable=False)[0].returncode == 0
    promoted = release(lab)
    chart_only = _commit(lab["repo"], "a template", {"charts/group-sync-dashboard/templates/x.yaml": "kind: Secret\n"})
    image_commit = _git(lab["repo"], "log", "--first-parent", "-1", "--format=%H", chart_only, "--", "local-development/README.md")
    for ref in (f"{DASHBOARD}:{APP}-{image_commit[:10]}", f"{DASHBOARD}:{APP}"):
        done, _ = promote(lab, registry, event="push", unreachable=ref, mirror_immutable=False)
        assert done.returncode == 1, f"{ref}: a registry outage was reported as a green notice:\n{done.stdout}{done.stderr}"
        assert "cannot read" in done.stdout and "no such host" in done.stdout, done.stdout
        assert "Nothing was promoted by this run" not in done.stdout
        assert release(lab) == promoted
    registry["tags"].pop(f"{DASHBOARD}:{APP}-{image_commit[:10]}")   # genuinely absent: still the notice
    done, _ = promote(lab, registry, event="push", mirror_immutable=False)
    assert done.returncode == 0 and "is not ready" in done.stdout, done.stdout + done.stderr


def test_a_release_that_moved_after_the_fetch_refuses_the_push(lab) -> None:
    """Review of #614 (OB2): the push is a plain fast-forward; a hand commit that landed meanwhile stands."""
    tip = _main_at(lab, APP)
    registry = _released()
    _mirror(lab, registry, tip)
    real_git = shutil.which("git")
    stranger = _git(lab["repo"], "commit-tree", _git(lab["repo"], "hash-object", "-t", "tree", "-w", "/dev/null"),
                    "-p", lab["start"], "-m", "a hand commit on release")
    _git(lab["repo"], "push", "-q", "origin", f"{stranger}:refs/heads/by-hand")   # the object reaches origin
    shim = lab["tmp"] / "shim"
    shim.mkdir()
    (shim / "git").write_text(f"""#!/usr/bin/env bash
for arg in "$@"; do
  if [ "$arg" = push ]; then {real_git} --git-dir="{lab['origin']}" update-ref refs/heads/release {stranger}; break; fi
done
exec {real_git} "$@"
""")
    (shim / "git").chmod(0o755)
    done, _ = promote(lab, registry, event="workflow_run", run_sha=tip, mirror_immutable=False, extra_path=str(shim))
    assert done.returncode != 0, done.stdout + done.stderr
    assert "rejected" in done.stderr or "failed to update ref" in done.stderr, done.stderr
    assert release(lab) == stranger, "the hand commit stands; nothing was forced over it"


def test_a_dispatch_rebuild_at_a_commit_that_changed_no_image_input_promotes_nothing(lab) -> None:
    """Review of #614 (OB2): publish.yml run by hand at such a tip tags that tip's sha; promote needs the
    image-input commit's own tag (docs/RELEASING.md, its troubleshooting row)."""
    image = _main_at(lab, APP)
    tip = _commit(lab["repo"], "a template", {"charts/group-sync-dashboard/templates/x.yaml": "kind: Secret\n"})
    registry = _released()
    for name in (DASHBOARD, REPORT):   # the rebuild's tag, and no tag for the image-input commit
        registry["tags"][f"{name}:{APP}-{tip[:10]}"] = registry["tags"][f"{name}:{APP}"]
    done, _ = promote(lab, registry, event="workflow_run", run_sha=tip, mirror_immutable=False)
    assert done.returncode == 0 and "is not ready" in done.stdout, done.stdout + done.stderr
    assert release(lab) == lab["start"] and image != tip


def test_a_green_publish_that_pushed_nothing_is_a_red_promotion(lab) -> None:
    """Review of #614 (OB2): publish.yml is green with REGISTRY_* unset; its completion reaches the strict path."""
    tip = _main_at(lab, APP)
    done, _ = promote(lab, {"tags": {}, "manifests": {}, "blobs": {}}, event="workflow_run", run_sha=tip,
                      mirror_immutable=False)
    assert done.returncode == 1 and "cannot read" in done.stdout, done.stdout + done.stderr
    assert release(lab) == lab["start"]


def test_an_identical_chart_at_a_new_target_writes_a_new_release_commit(lab) -> None:
    """Review of #614 (OB2): promotion.yaml's first line names the target, so "nothing to promote" holds only for the
    same commit; the new commit changes that one line."""
    tip = _main_at(lab, APP)
    registry = _released()
    _mirror(lab, registry, tip)
    assert promote(lab, registry, event="workflow_run", run_sha=tip, mirror_immutable=False)[0].returncode == 0
    first = release(lab)
    workflow = _commit(lab["repo"], "promote.yml itself", {".github/workflows/promote.yml": "name: promote\n"})
    done, _ = promote(lab, registry, event="push", mirror_immutable=False)
    assert done.returncode == 0, done.stdout + done.stderr
    assert release(lab) != first and _git(lab["origin"], "log", "-1", "--format=%s", "release") == f"promote: main {workflow}"
    assert _git(lab["origin"], "diff", "--stat", first, "release").strip().endswith("1 file changed, 1 insertion(+), 1 deletion(-)")


# ── The workflow's shape ──────────────────────────────────────────────────────────────────────


def _workflow() -> dict:
    return yaml.safe_load(PROMOTE.read_text())


def test_it_runs_after_a_successful_publish_on_main_and_after_a_chart_or_environment_merge() -> None:
    wf = _workflow()
    on = wf.get("on", wf.get(True))
    assert on["workflow_run"] == {"workflows": ["publish"], "types": ["completed"], "branches": ["main"]}
    assert on["push"]["branches"] == ["main"]
    assert on["push"]["paths"] == ["charts/group-sync-dashboard/**", "environments/**", ".github/workflows/promote.yml"]
    assert set(on["workflow_dispatch"]["inputs"]) == {"sha", "rollback"}
    condition = " ".join(wf["jobs"]["promote"]["if"].split())
    assert "github.ref == 'refs/heads/main'" in condition
    assert "github.event.workflow_run.conclusion == 'success'" in condition


def test_one_promotion_at_a_time_read_only_token_and_the_deploy_key_from_the_release_environment() -> None:
    wf = _workflow()
    job = wf["jobs"]["promote"]
    assert wf["concurrency"] == {"group": "promote-release", "cancel-in-progress": False}
    assert wf["permissions"] == {"contents": "read"} and "permissions" not in job
    assert job["environment"] == "release"
    checkout = next(s for s in job["steps"] if str(s.get("uses", "")).startswith("actions/checkout@"))
    assert checkout["with"] == {"ref": "main", "fetch-depth": 0, "persist-credentials": False}


def test_the_deploy_key_is_loaded_only_by_the_push_step(tmp_path) -> None:
    """Review of #614 (Codex F1): the key bypasses the release ruleset, so no other step may hold it."""
    job = _workflow()["jobs"]["promote"]
    push = _step(job, PUSH_STEP)
    assert job["steps"][-1] is push
    assert push["env"] == {"RELEASE_DEPLOY_KEY": "${{ secrets.RELEASE_DEPLOY_KEY }}"}
    assert [s.get("name") or s.get("uses") for s in job["steps"] if "RELEASE_DEPLOY_KEY" in str(s.get("with", "")) + str(s.get("env", ""))] == [
        "Check the release deploy key is configured", PUSH_STEP]   # the first only asks whether it is set
    assert "git push" not in _step(job, STEP)["run"]
    run = push["run"]
    assert run.startswith("set +x\n") and "-o StrictHostKeyChecking=yes" in run and "--force" not in run and "+${commit}" not in run
    # GitHub's published Ed25519 host key (SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU)
    assert "github.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOMqqnkVzrm0SdG6UOoqKLsabgH5C9okWi0dh2l9GKJl" in run
    # only the push goes over SSH: checkout's https origin keeps its fetch URL
    option = re.search(r"git -c (url\.\S+) push origin", run).group(1)
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "remote", "add", "origin", "https://github.com/ephico2real2/group-sync-dashboard"], check=True)
    url = lambda *args: subprocess.run(["git", "-C", str(tmp_path), "-c", option, "remote", "get-url", *args, "origin"],  # noqa: E731
                                       capture_output=True, text=True, check=True).stdout.strip()
    assert url("--push") == "git@github.com:ephico2real2/group-sync-dashboard"
    assert url() == "https://github.com/ephico2real2/group-sync-dashboard"


def test_nothing_in_it_builds_and_it_verifies_with_the_cosign_publish_signs_with() -> None:
    text = PROMOTE.read_text()
    for word in ("podman", "docker build", "buildah", "./build-and-push", "cosign sign", "skopeo copy"):
        assert word not in text, word
    installer = re.compile(r"uses: (sigstore/cosign-installer@\S+)[\s\S]*?cosign-release: (v[\d.]+)")
    assert installer.search(text).groups() == installer.search(PUBLISH.read_text()).groups()
    assert f"IDENTITY: https://github.com/${{{{ github.repository }}}}/.github/workflows/publish.yml@refs/heads/main" in text


def test_the_label_readers_are_helm_yamls() -> None:
    """One rule in three places, as release-crc.sh and helm.yaml already hold it (#410)."""
    ours, theirs = _step(_jobs(PROMOTE)["promote"], STEP)["run"], _step(_jobs(HELM)["release"], "Label the image")["run"]
    function = re.compile(r"^image_versions\(\) \{\n.*?^\}$", re.M | re.S)
    walker = re.compile(r"^REPORT_PINNED=\$\(python3 -c '\n(.*?)^' < ", re.M | re.S)
    assert function.search(ours).group(0) == function.search(theirs).group(0)
    assert walker.search(ours).group(1) == walker.search(theirs).group(1)


def test_the_image_input_list_is_publish_ymls_and_the_immutable_tag_is_source_bound() -> None:
    run = _step(_jobs(PROMOTE)["promote"], STEP)["run"]
    array = shlex.split(re.search(r"IMAGE_INPUTS=\(\n(.*?)^\)", run, re.M | re.S).group(1))
    assert array == yaml.safe_load(PUBLISH.read_text()).get(True)["push"]["paths"]
    assert 'git log --first-parent -1 --format=%H "${target}" -- "${IMAGE_INPUTS[@]}"' in run
    assert 'tag="${this_pin:-${app_version}-${image_commit:0:10}}"' in run
    assert 'if [ "${alias_digest}" != "${digest}" ]; then' in run
    publisher = PUBLISHER.read_text()
    assert "COMMIT=$(git rev-parse HEAD)" in publisher
    assert 'COMMIT="${COMMIT:0:10}"' in publisher
    assert "git rev-parse --short=10 HEAD" not in publisher


def test_the_gitops_readme_names_the_dashboard_application_main_by_default_and_the_opt_in() -> None:
    """SPEC_P1 Block 13 (review of #614: OB2 F1, Codex F2, the row the first commit left out)."""
    rows = [line for line in GITOPS_README.read_text().splitlines() if line.startswith("| `argocd-application-dashboard.yaml`")]
    assert len(rows) == 1, "gitops/README.md has no row for the dashboard Application (SPEC_P1 Block 13)"
    assert "`main`" in rows[0] and "--argocd release" in rows[0] and "promotion.yaml" in rows[0] and "--argocd main" in rows[0]


def test_the_lab_tracks_main_by_default_and_release_crc_names_the_file_promote_writes() -> None:
    """The operator, 2026-10-04: "main by default; release optional". `--argocd release` is the opt-in."""
    source = yaml.safe_load(APPLICATION.read_text())["spec"]["source"]
    assert source["targetRevision"] == "main"
    assert source["helm"]["valueFiles"] == ["../../environments/crc.yaml"]
    assert "git update-index --add --cacheinfo \"100644,${blob},promotion.yaml\"" in PROMOTE.read_text()
    script = RELEASE_CRC.read_text()
    assert '"../../promotion.yaml"' in script and 'git show "${revision}:promotion.yaml"' in script
