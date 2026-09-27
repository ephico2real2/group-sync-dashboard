#!/usr/bin/env python3
"""Promote a commit on main to the `release` branch that the lab's Argo CD tracks (#410).

    python3 local-development/promote.py                           # main's tip (what the workflow runs)
    python3 local-development/promote.py --sha <commit>            # a commit on main
    python3 local-development/promote.py --sha <commit> --rollback # even one older than what is promoted
    python3 local-development/promote.py --dry-run                 # read everything back, push nothing

The design, and every rule below, is docs/specs/SPEC_P1_promote_release_branch.md.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile

RELEASE = "release"
PIN = "promotion.yaml"
CARRIED = ("charts/group-sync-dashboard", "environments")
IMAGES = ("group-sync-dashboard", "group-sync-dashboard-report")
PUBLISH = ".github/workflows/publish.yml"
ISSUER = "https://token.actions.githubusercontent.com"
BOT = ("github-actions[bot]", "41898282+github-actions[bot]@users.noreply.github.com")


class Refused(Exception):
    """Nothing is promoted; the message says why."""


def run(*cmd: str, cwd: str | None = None, data: bytes | None = None) -> str:
    done = subprocess.run(cmd, cwd=cwd, input=data, capture_output=True)
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).decode(errors="replace").strip()
        raise Refused(f"`{' '.join(cmd[:4])}` failed: {detail}")
    return done.stdout.decode()


def git(*args: str) -> str:
    return run("git", *args).strip()


def image_inputs(publish_yml: str) -> list[str]:
    """publish.yml's on.push.paths. Read as text because the runner's python3 has no PyYAML."""
    lines = publish_yml.splitlines()
    try:
        start = lines.index("    paths:", lines.index("  push:"))
    except ValueError:
        raise Refused(f"{PUBLISH} has no on.push.paths list") from None
    paths = []
    for line in lines[start + 1:]:
        m = re.match(r"      - '([^']+)'", line)
        if not m:
            break
        paths.append(m.group(1))
    if not paths:
        raise Refused(f"{PUBLISH}'s on.push.paths list is empty")
    return paths


def image_candidates(target: str, first_parent: list[str], publish_yml: str) -> list[str]:
    """The main commits whose image is `target`'s image, newest first."""
    specs = [f":(glob){p}" for p in image_inputs(publish_yml)]
    changed = git("log", "--first-parent", "-1", "--format=%H", target, "--", *specs)
    if not changed:
        raise Refused(f"no commit at or before {target[:10]} changed an image input")
    line = first_parent[first_parent.index(target):]
    return line[:line.index(changed) + 1]


def built_image(repo: str, candidates: list[str]) -> tuple[str, int] | None:
    """(commit, run id) of the newest candidate publish.yml built on main; None while a run is still going."""
    running = False
    for sha in candidates:
        out = run("gh", "api", "-X", "GET", f"repos/{repo}/actions/workflows/publish.yml/runs",
                  "-f", f"head_sha={sha}", "-f", "per_page=100")
        runs = [r for r in json.loads(out)["workflow_runs"] if r.get("head_branch") == "main"]
        good = [r for r in runs if r.get("conclusion") == "success"]
        if good:
            return sha, good[0]["id"]
        running = running or any(r.get("status") != "completed" for r in runs)
    if running:
        return None
    raise Refused(f"no successful publish.yml run on main built this tree's image (tried "
                  f"{', '.join(c[:10] for c in candidates)}); an older image is not this tree's")


def read_back(ref: str, version: str, revision: str) -> str:
    """The digest of `ref`, once every Linux image in it is labelled with this version and 10-character sha."""
    digest = json.loads(run("skopeo", "inspect", "--no-tags", f"docker://{ref}")).get("Digest") or ""
    if not re.fullmatch(r"sha256:[0-9a-f]{64}", digest):
        raise Refused(f"{ref} reported no sha256 digest (got {digest!r})")
    image = ref.rsplit(":", 1)[0]
    # By digest, and every child of a list: skopeo's default reads only the runner's platform (#414).
    raw = json.loads(run("skopeo", "inspect", "--raw", f"docker://{image}@{digest}"))
    children = [m.get("digest", "") for m in raw["manifests"] if (m.get("platform") or {}).get("os") == "linux"] \
        if "manifests" in raw else [digest]
    if not children:
        raise Refused(f"{ref} is a manifest list with no Linux image")
    for child in children:
        config = json.loads(run("skopeo", "inspect", "--config", f"docker://{image}@{child}"))
        labels = (config.get("config") or {}).get("Labels") or {}
        got = (labels.get("org.opencontainers.image.version"), labels.get("org.opencontainers.image.revision"))
        if got != (version, revision):
            raise Refused(f"{image}@{child} is labelled version {got[0]!r}, revision {got[1]!r};"
                          f" expected {version!r}, {revision!r}")
    return digest


def verify_signature(image: str, digest: str, repo: str) -> None:
    identity = f"https://github.com/{repo}/.github/workflows/publish.yml@refs/heads/main"
    run("cosign", "verify", "--certificate-identity", identity, "--certificate-oidc-issuer", ISSUER, f"{image}@{digest}")


def field(text: str, pattern: str, what: str) -> str:
    m = re.search(pattern, text, re.M)
    if not m:
        raise Refused(f"cannot read {what}")
    return m.group(1)


def render_pin(source: str, image_commit: str, run_id: int, pins: list[tuple[str, str, str]]) -> str:
    (dash, dash_tag, dash_digest), (report, report_tag, report_digest) = pins
    return (
        "# Written by .github/workflows/promote.yml after both images were read back. Do not edit.\n"
        f"# source: {source}\n"
        f"# images: {image_commit} (publish.yml run {run_id})\n"
        "image:\n"
        f"  repository: {dash}\n"
        f'  tag: "{dash_tag}"\n'
        f'  digest: "{dash_digest}"\n'
        "reporting:\n"
        "  image:\n"
        f"    repository: {report}\n"
        f'    tag: "{report_tag}"\n'
        f'    digest: "{report_digest}"\n'
    )


def promoted_source() -> str | None:
    """The main commit `release` carries now; None before the first promotion."""
    if not git("ls-tree", "--name-only", f"origin/{RELEASE}", PIN):
        return None
    return field(git("show", f"origin/{RELEASE}:{PIN}"), r"^# source: ([0-9a-f]{40})$", f"the source in {RELEASE}:{PIN}")


def commit_release(target: str, pin: str, message: str, dry_run: bool) -> str | None:
    """Make `release` the carried paths at `target` plus the pin, and push it as a fast-forward."""
    with tempfile.TemporaryDirectory() as tmp:
        tree = str(pathlib.Path(tmp) / RELEASE)
        git("worktree", "add", "-q", "--detach", tree, f"origin/{RELEASE}")
        try:
            run("git", "rm", "-rq", "--ignore-unmatch", ".", cwd=tree)
            run("tar", "-x", "-C", tree, data=subprocess.run(["git", "archive", target, *CARRIED],
                                                            capture_output=True, check=True).stdout)
            pathlib.Path(tree, PIN).write_text(pin)
            run("git", "add", "-A", cwd=tree)
            if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=tree).returncode == 0:
                return None
            if dry_run:
                print(run("git", "diff", "--cached", "--stat", cwd=tree))
                return None
            run("git", "-c", f"user.name={BOT[0]}", "-c", f"user.email={BOT[1]}", "commit", "-qm", message, cwd=tree)
            # No --force: a push that is not a fast-forward is refused, never overwritten.
            run("git", "push", "-q", "origin", f"HEAD:refs/heads/{RELEASE}", cwd=tree)
            return run("git", "rev-parse", "HEAD", cwd=tree).strip()
        finally:
            git("worktree", "remove", "--force", tree)


def promote(sha: str | None, rollback: bool, dry_run: bool) -> int:
    repo = os.environ["GITHUB_REPOSITORY"]
    registry = f"{os.environ.get('REGISTRY') or 'quay.io'}/{os.environ.get('REGISTRY_NAMESPACE') or 'ephico2real'}"
    signing = os.environ.get("SUPPLY_CHAIN_SIGNING", "") != "false"
    git("fetch", "-q", "origin", "+refs/heads/main:refs/remotes/origin/main")
    try:
        git("fetch", "-q", "origin", f"+refs/heads/{RELEASE}:refs/remotes/origin/{RELEASE}")
    except Refused:
        raise Refused(f"origin has no `{RELEASE}` branch; create it once (docs/CICD.md, Rollback and setup)") from None
    first_parent = git("rev-list", "--first-parent", "origin/main").split()
    target = git("rev-parse", "--verify", f"{sha or first_parent[0]}^{{commit}}")
    if target not in first_parent:
        raise Refused(f"{target[:10]} is not on main's first-parent line; only what main merged is promoted")

    chosen = built_image(repo, image_candidates(target, first_parent, git("show", f"{target}:{PUBLISH}")))
    if chosen is None:
        print(f"::notice::the image of {target[:10]} is still being published; that run's completion promotes it")
        return 0
    image_commit, run_id = chosen
    version = field(git("show", f"{image_commit}:local-development/pyproject.toml"), r'^version = "(.+?)"$',
                    "pyproject.toml's version")
    app_version = field(git("show", f"{target}:charts/group-sync-dashboard/Chart.yaml"), r'^appVersion: "(.+?)"$',
                        "Chart.yaml's appVersion")
    if version != app_version:
        raise Refused(f"the chart at {target[:10]} deploys appVersion {app_version}, the image is {version}")
    short = git("rev-parse", "--short=10", image_commit)
    tag = f"{version}-{short}"
    pins = []
    for name in IMAGES:
        image = f"{registry}/{name}"
        digest = read_back(f"{image}:{tag}", version, short)
        if signing:
            verify_signature(image, digest, repo)
        pins.append((image, tag, digest))
        print(f"image   : {image}:{tag} -> {digest}{' (signature verified)' if signing else ''}")

    promoted = promoted_source()
    if promoted and promoted != target and not rollback \
            and subprocess.run(["git", "merge-base", "--is-ancestor", promoted, target]).returncode != 0:
        raise Refused(f"{RELEASE} carries {promoted[:10]}, which {target[:10]} does not descend from;"
                      " dispatch with rollback to move the lab back on purpose")
    message = (f"promote main@{target[:10]}: {tag}\n\nsource: {target}\nimages: {image_commit} (publish.yml run {run_id})\n"
               + "".join(f"{image}@{digest}\n" for image, _, digest in pins))
    pushed = commit_release(target, render_pin(target, image_commit, run_id, pins), message, dry_run)
    print(f"release : {pushed or 'unchanged'} (main@{target[:10]}, {tag}{', dry run' if dry_run else ''})")
    return 0


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    parser.add_argument("--sha", help="the commit on main to promote (default: main's tip)")
    parser.add_argument("--rollback", action="store_true", help="allow a commit older than the one promoted")
    parser.add_argument("--dry-run", action="store_true", help="read back and show the change; push nothing")
    args = parser.parse_args(argv)
    try:
        return promote(args.sha, args.rollback, args.dry_run)
    except Refused as exc:
        print(f"::error::not promoted: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
