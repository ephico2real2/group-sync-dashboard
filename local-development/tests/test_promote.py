"""promote.py end to end: real git with a bare origin, stubs for gh, skopeo and cosign (#410, SPEC_P1)."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess

import pytest
import yaml

LOCAL_DEV = pathlib.Path(__file__).resolve().parents[1]
REPO = LOCAL_DEV.parent
SCRIPT = LOCAL_DEV / "promote.py"
PUBLISH = REPO / ".github" / "workflows" / "publish.yml"

STUB = r'''#!/usr/bin/env bash
# One line per call in STUB_LOG; answers come from JSON files the test writes.
printf '%s %s\n' "$(basename "$0")" "$*" >> "$STUB_LOG"
case "$(basename "$0")" in
  gh)
    all="$*"; sha="${all##*head_sha=}"; sha="${sha%% *}"
    python3 -c 'import json,sys; print(json.dumps({"workflow_runs": json.load(open(sys.argv[1])).get(sys.argv[2], [])}))' "$STUB_RUNS" "$sha" ;;
  skopeo)
    ref="${!#}"; python3 - "$STUB_REGISTRY" "${ref#docker://}" "$2" <<'EOF'
import json, sys
registry, ref, mode = json.load(open(sys.argv[1])), sys.argv[2], sys.argv[3]
if "@" in ref:   # by digest: the tag whose image has it
    image, digest = ref.split("@")
    ref = next((k for k, v in registry.items() if k.rsplit(":", 1)[0] == image and v["Digest"] == digest), "")
if ref not in registry:
    sys.exit(1)
entry = registry[ref]
print(json.dumps({"--raw": {"schemaVersion": 2, "config": {}, "layers": []},
                  "--config": {"os": "linux", "config": {"Labels": entry["Labels"]}}}.get(mode, entry)))
EOF
    ;;
  cosign) exit "${STUB_COSIGN_RC:-0}" ;;
esac
'''

GIT_ENV = {"GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null", "GIT_AUTHOR_NAME": "t",
           "GIT_AUTHOR_EMAIL": "t@example.invalid", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.invalid"}


def _load():
    spec = importlib.util.spec_from_file_location("promote", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def git(cwd: pathlib.Path, *args: str) -> str:
    done = subprocess.run(["git", *args], cwd=cwd, env={**os.environ, **GIT_ENV}, capture_output=True, text=True)
    assert done.returncode == 0, f"git {args}: {done.stderr}"
    return done.stdout.strip()


class Lab:
    def __init__(self, tmp: pathlib.Path):
        self.tmp, self.origin, self.src, self.runner = tmp, tmp / "origin.git", tmp / "src", tmp / "runner"
        self.runs, self.registry, self.log = tmp / "runs.json", tmp / "registry.json", tmp / "calls.log"
        self.runs.write_text("{}")
        self.registry.write_text("{}")
        git(tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        git(tmp, "init", "-q", "-b", "main", str(self.src))
        git(self.src, "remote", "add", "origin", str(self.origin))
        self.commit({".github/workflows/publish.yml": PUBLISH.read_text(), ".github/workflows/ci.yml": "name: ci\n",
                     "charts/group-sync-dashboard/Chart.yaml": 'name: group-sync-dashboard\nversion: 0.1.0\nappVersion: "1.1.0"\n',
                     "charts/group-sync-dashboard/values.yaml": 'image:\n  tag: ""\n',
                     "environments/crc.yaml": "logLevel: DEBUG\n", "docs/notes.md": "notes\n",
                     "local-development/pyproject.toml": 'version = "1.1.0"\n', "local-development/gsd/app.py": "v = 0\n"})
        git(self.src, "checkout", "-q", "--orphan", "release")
        git(self.src, "rm", "-rqf", ".")
        git(self.src, "commit", "-q", "--allow-empty", "-m", "the promotion branch")
        git(self.src, "push", "-q", "origin", "release")
        git(self.src, "checkout", "-q", "main")
        git(tmp, "clone", "-q", str(self.origin), str(self.runner))
        bindir = tmp / "bin"
        bindir.mkdir()
        for tool in ("gh", "skopeo", "cosign"):
            (bindir / tool).write_text(STUB)
            (bindir / tool).chmod(0o755)
        self.env = {**os.environ, **GIT_ENV, "PATH": f"{bindir}:{os.environ['PATH']}", "STUB_LOG": str(self.log),
                    "STUB_RUNS": str(self.runs), "STUB_REGISTRY": str(self.registry), "GITHUB_REPOSITORY": "o/r",
                    "REGISTRY": "quay.io", "REGISTRY_NAMESPACE": "example"}
        self.env.pop("SUPPLY_CHAIN_SIGNING", None)

    def commit(self, files: dict[str, str], message: str = "change") -> str:
        for path, text in files.items():
            (self.src / path).parent.mkdir(parents=True, exist_ok=True)
            (self.src / path).write_text(text)
        git(self.src, "add", "-A")
        git(self.src, "commit", "-qm", message)
        git(self.src, "push", "-q", "origin", "main")
        return git(self.src, "rev-parse", "HEAD")

    def publish(self, sha: str, conclusion: str | None = "success", version: str = "1.1.0", revision: str | None = None) -> None:
        """A publish.yml run for `sha`; with a conclusion of success, both images in the registry."""
        runs = json.loads(self.runs.read_text())
        runs.setdefault(sha, []).append({"id": len(runs) + 1, "head_branch": "main", "status": "completed" if conclusion else "in_progress",
                                         "conclusion": conclusion})
        self.runs.write_text(json.dumps(runs))
        if conclusion == "success":
            registry = json.loads(self.registry.read_text())
            for name in ("group-sync-dashboard", "group-sync-dashboard-report"):
                registry[f"quay.io/example/{name}:{version}-{sha[:10]}"] = {
                    "Digest": "sha256:" + (sha + name).encode().hex()[:64],
                    "Labels": {"org.opencontainers.image.version": version, "org.opencontainers.image.revision": revision or sha[:10]}}
            self.registry.write_text(json.dumps(registry))

    def promote(self, *args: str, **env: str) -> subprocess.CompletedProcess:
        return subprocess.run(["python3", str(SCRIPT), *args], cwd=self.runner, env={**self.env, **env}, capture_output=True, text=True)

    def release(self) -> str:
        return git(self.src, "ls-remote", "origin", "refs/heads/release").split()[0]

    def pin(self) -> str:
        git(self.src, "fetch", "-q", "origin", "release")
        return git(self.src, "show", "FETCH_HEAD:promotion.yaml")


@pytest.fixture
def lab(tmp_path: pathlib.Path) -> Lab:
    return Lab(tmp_path)


def test_a_code_merge_is_promoted_with_both_images_pinned_by_digest(lab):
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a)
    r = lab.promote()
    assert r.returncode == 0, r.stdout + r.stderr
    pin = lab.pin()
    assert f"# source: {a}" in pin and f'tag: "1.1.0-{a[:10]}"' in pin
    assert pin.count('digest: "sha256:') == 2
    tree = git(lab.src, "ls-tree", "-r", "--name-only", "FETCH_HEAD").split()
    assert sorted({p.split("/")[0] for p in tree}) == ["charts", "environments", "promotion.yaml"], tree
    assert "cosign verify" in lab.log.read_text(), "signing is on unless SUPPLY_CHAIN_SIGNING is false"


def test_a_chart_only_merge_carries_the_image_of_the_last_image_input_commit(lab):
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a)
    b = lab.commit({"charts/group-sync-dashboard/values.yaml": 'image:\n  tag: ""\nnew: 1\n'})
    r = lab.promote()
    assert r.returncode == 0, r.stdout + r.stderr
    pin = lab.pin()
    assert f"# source: {b}" in pin and f'tag: "1.1.0-{a[:10]}"' in pin
    assert "new: 1" in git(lab.src, "show", "FETCH_HEAD:charts/group-sync-dashboard/values.yaml")


def test_a_failed_publish_is_never_promoted_even_when_an_older_image_exists(lab):
    old = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(old)
    a = lab.commit({"local-development/gsd/app.py": "v = 2\n"})
    lab.publish(a, conclusion="failure")
    lab.commit({"environments/crc.yaml": "logLevel: INFO\n"})
    before = lab.release()
    r = lab.promote()
    assert r.returncode == 1 and "no successful publish.yml run" in r.stderr, r.stdout + r.stderr
    assert lab.release() == before


def test_a_publish_still_running_waits_for_its_own_completion(lab):
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a, conclusion=None)
    before = lab.release()
    r = lab.promote()
    assert r.returncode == 0 and "still being published" in r.stdout, r.stdout + r.stderr
    assert lab.release() == before


@pytest.mark.parametrize("version, revision", [("0.24.0", None), ("1.1.0", "0123456789")], ids=["version", "revision"])
def test_an_image_whose_labels_are_not_this_build_is_refused(lab, version, revision):
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a, revision=revision)
    if version != "1.1.0":
        registry = json.loads(lab.registry.read_text())
        for entry in registry.values():
            entry["Labels"]["org.opencontainers.image.version"] = version
        lab.registry.write_text(json.dumps(registry))
    before = lab.release()
    r = lab.promote()
    assert r.returncode == 1 and "is labelled version" in r.stderr, r.stdout + r.stderr
    assert lab.release() == before


def test_a_signature_that_does_not_verify_is_refused_and_signing_off_skips_it(lab):
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a)
    r = lab.promote(STUB_COSIGN_RC="1")
    assert r.returncode == 1 and "cosign verify" in r.stderr, r.stdout + r.stderr
    lab.log.write_text("")
    r = lab.promote(SUPPLY_CHAIN_SIGNING="false")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "cosign" not in lab.log.read_text()


def test_an_older_commit_needs_rollback_and_a_second_run_changes_nothing(lab):
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a)
    b = lab.commit({"local-development/gsd/app.py": "v = 2\n"})
    lab.publish(b)
    assert lab.promote().returncode == 0
    promoted = lab.release()
    assert lab.promote().returncode == 0 and lab.release() == promoted, "promoting the same tree again is a no-op"
    r = lab.promote("--sha", a)
    assert r.returncode == 1 and "does not descend from" in r.stderr, r.stdout + r.stderr
    r = lab.promote("--sha", a, "--rollback")
    assert r.returncode == 0, r.stdout + r.stderr
    assert f"# source: {a}" in lab.pin()


def test_without_a_release_branch_nothing_is_promoted(lab):
    git(lab.src, "push", "-q", "origin", "--delete", "release")
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a)
    r = lab.promote()
    assert r.returncode == 1 and "origin has no `release` branch" in r.stderr, r.stdout + r.stderr


@pytest.mark.parametrize("bad", ["version", "revision", "missing"])
def test_every_linux_image_of_a_manifest_list_is_read_back(monkeypatch, bad):
    """One arm64 child of another build, or unreadable, refuses the whole index."""
    promote = _load()
    index, amd, arm = ("sha256:" + n * 64 for n in "123")
    good = {"org.opencontainers.image.version": "1.1.0", "org.opencontainers.image.revision": "0123456789"}
    wrong = {**good, f"org.opencontainers.image.{'version' if bad == 'version' else 'revision'}": "other"}

    def registry(*cmd, **_):
        ref = cmd[-1]
        if "--raw" in cmd:
            return json.dumps({"manifests": [{"digest": amd, "platform": {"os": "linux", "architecture": "amd64"}},
                                             {"digest": arm, "platform": {"os": "linux", "architecture": "arm64"}}]})
        if "--config" in cmd:
            if ref.endswith(arm) and bad == "missing":
                raise promote.Refused("manifest unknown")
            return json.dumps({"os": "linux", "config": {"Labels": wrong if ref.endswith(arm) else good}})
        return json.dumps({"Digest": index, "Labels": good})

    monkeypatch.setattr(promote, "run", registry)
    with pytest.raises(promote.Refused):
        promote.read_back("quay.io/example/app:1.1.0-0123456789", "1.1.0", "0123456789")


def test_a_revert_or_a_second_parent_change_needs_its_own_publish(lab):
    a = lab.commit({"local-development/gsd/app.py": "v = 1\n"})
    lab.publish(a)
    reverted = lab.commit({"local-development/gsd/app.py": "v = 0\n"}, "revert")
    assert lab.promote().returncode == 1, "a revert is an image change"
    lab.publish(reverted)
    git(lab.src, "checkout", "-qb", "topic")
    topic = lab.commit({"local-development/gsd/app.py": "topic = 1\n"})
    git(lab.src, "checkout", "-q", "main")
    git(lab.src, "merge", "-q", "--no-ff", "-m", "merge topic", "topic")
    git(lab.src, "push", "-q", "origin", "main")
    merged = git(lab.src, "rev-parse", "HEAD")
    lab.publish(topic)
    assert lab.promote().returncode == 1, "the topic's build is not main's"
    lab.publish(merged)
    assert lab.promote().returncode == 0 and f"# images: {merged}" in lab.pin()


def test_the_image_input_reader_is_publish_ymls_path_filter():
    parsed = yaml.safe_load(PUBLISH.read_text())
    assert _load().image_inputs(PUBLISH.read_text()) == (parsed.get("on") or parsed[True])["push"]["paths"]
