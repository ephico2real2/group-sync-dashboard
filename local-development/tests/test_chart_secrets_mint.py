"""The secrets-mint hook (#212): the oauth-proxy session key and the shared report token are minted on
the cluster by a Job, only if absent, never rendered — Helm's `lookup`, which used to reuse them, is
empty under `helm template` (Argo CD's repo-server, Kustomize's helmCharts), so every render minted
fresh values and every sync rotated them. The first upgrade carries the old Secrets' values over into
the new names, so nobody is signed out.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
CHART = REPO / "charts" / "group-sync-dashboard"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def _render(*sets: str) -> list[dict]:
    args = ["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h"]
    for s in sets:
        args += ["--set", s]
    done = subprocess.run(args, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return [d for d in yaml.safe_load_all(done.stdout) if d]


def _one(docs, kind, name_contains=""):
    found = [d for d in docs if d["kind"] == kind and name_contains in d["metadata"]["name"]]
    assert len(found) == 1, f"{kind} {name_contains!r}: {len(found)} rendered"
    return found[0]


def _job(docs):
    job = _one(docs, "Job", "-secrets-mint")
    c = job["spec"]["template"]["spec"]["containers"][0]
    return job, [*c["command"], c["args"][0]], {e["name"]: e["value"] for e in c["env"]}


def _run(tmp_path, argv, env, shim_case: str):
    """The rendered script under bash with an `oc` shim: a bash `case "$*"` body, every call logged."""
    shim = tmp_path / "bin"
    shim.mkdir(exist_ok=True)
    calls = tmp_path / "calls"
    (shim / "oc").write_text("#!/bin/bash\n" f"echo \"$*\" >> {calls}\n" "case \"$*\" in\n" + shim_case + "\n  *) exit 1 ;;\nesac\n")
    (shim / "oc").chmod(0o755)
    done = subprocess.run(argv, env={**env, "PATH": f"{shim}:{os.environ['PATH']}"}, capture_output=True, text=True, timeout=60)
    return done, (calls.read_text().splitlines() if calls.exists() else [])


class TestRender:
    def test_no_generated_value_is_ever_rendered_and_the_pods_mount_the_minted_names(self):
        # WITH a schedule: the CronJob renders only then, and its mount is the one the first draft
        # missed (review of #215, Grok M8 — the range scope is `$`, so a replace on `.` skipped it)
        docs = _render("reporting.schedules[0].name=nightly", "reporting.schedules[0].report=namespace-access", "reporting.schedules[0].schedule=0 1 * * *")
        assert [d for d in docs if d["kind"] == "CronJob"], "the schedule must render a CronJob for this test to mean anything"
        secrets = [d["metadata"]["name"] for d in docs if d["kind"] == "Secret"]
        assert not [n for n in secrets if n.endswith(("-oauth-cookie", "-oauth-session", "-report-token", "-report-shared-token"))], secrets
        text = subprocess.run(["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h"], capture_output=True, text=True).stdout
        assert "lookup" not in re.sub(r"#[^\n]*", "", text), "no lookup survives in a rendered manifest"
        mounts = {(d["kind"], v["secret"]["secretName"]) for d in docs if d["kind"] in ("Deployment", "CronJob")
                  for v in (d["spec"]["template"]["spec"]["volumes"] if d["kind"] == "Deployment" else d["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"])
                  if "secret" in v}
        assert ("Deployment", "t-group-sync-dashboard-oauth-session") in mounts
        assert ("Deployment", "t-group-sync-dashboard-report-shared-token") in mounts
        assert ("CronJob", "t-group-sync-dashboard-report-shared-token") in mounts, "a schedule Job needs the token too"
        assert not [m for m in mounts if m[1].endswith(("-oauth-cookie", "-report-token"))], mounts

    def test_the_hook_shape(self):
        docs = _render()
        job, _, env = _job(docs)
        ann = job["metadata"]["annotations"]
        assert ann["helm.sh/hook"] == "pre-install,pre-upgrade,post-install,post-upgrade" and ann["helm.sh/hook-weight"] == "-5"
        assert ann["argocd.argoproj.io/hook"] == "PreSync,Sync" and ann["argocd.argoproj.io/sync-wave"] == "-1"
        for kind in ("ServiceAccount", "Role", "RoleBinding"):
            a = _one(docs, kind, "-secrets-mint")["metadata"]["annotations"]
            assert a["helm.sh/hook"] == "pre-install,pre-upgrade" and a["helm.sh/hook-weight"] == "-10", "the identity is a hook ahead of the Job"
            # Argo runs a phase's hooks lowest wave first: the identity must sit BELOW the Job's wave or a
            # first Argo install starts the Job with no ServiceAccount (review of #215, Grok M2)
            assert int(a["argocd.argoproj.io/sync-wave"]) < int(ann["argocd.argoproj.io/sync-wave"]), (kind, a)
        alert = (CHART / "templates" / "monitoring.yaml").read_text()
        assert "-shared-token Secret" in alert and "-report-token Secret" not in alert, "the usage-pull alert names the Secret an operator will find (Grok N3)"
        role = _one(docs, "Role", "-secrets-mint")
        assert role["rules"][0]["resourceNames"] == ["t-group-sync-dashboard-oauth-session", "t-group-sync-dashboard-oauth-cookie",
                                                     "t-group-sync-dashboard-report-shared-token", "t-group-sync-dashboard-report-token"]
        assert env["MINT_COOKIE"] == "true" and env["MINT_TOKEN"] == "true"
        assert job["spec"]["template"]["spec"]["containers"][0]["resources"]["limits"]["memory"] == "128Mi"

    def test_the_switches(self):
        # a supplied cookie value: a plain deterministic Secret, no cookie mint
        docs = _render("oauthProxy.cookieSecret=fixed")
        assert _one(docs, "Secret", "-oauth-session")["data"]["session_secret"] == "Zml4ZWQ="
        assert _job(docs)[2]["MINT_COOKIE"] == "false" and _job(docs)[2]["MINT_TOKEN"] == "true"
        # the proxy off: no cookie at all; the token still minted
        docs = _render("oauthProxy.enabled=false", "visibility.enabled=false", "route.enabled=false", "ingress.enabled=true", "trustedCA.injected.enabled=false", "loginCapture.enabled=false", "reporting.enabled=false")
        assert not [d for d in docs if d["metadata"]["name"].endswith("-secrets-mint")], "nothing to mint: no hook"
        docs = _render("secretsMint.enabled=false")
        assert not [d for d in docs if d["metadata"]["name"].endswith("-secrets-mint")]
        assert not [d for d in docs if d["kind"] == "Secret" and d["metadata"]["name"].endswith(("-oauth-session", "-shared-token"))], "off = you create them"


class TestTheScript:
    def test_absent_secrets_are_minted_with_the_right_keys_and_lengths(self, tmp_path):
        _, argv, env = _job(_render())
        done, calls = _run(tmp_path, argv, env, f"""
  'get secret '*) echo 'Error from server (NotFound): secrets "x" not found' >&2; exit 1 ;;
  'create secret generic t-group-sync-dashboard-oauth-session '*) cp /tmp/session_secret {tmp_path}/session_secret; exit 0 ;;
  'create secret generic t-group-sync-dashboard-report-shared-token '*) cp /tmp/token {tmp_path}/token; exit 0 ;;""")
        assert done.returncode == 0, done.stdout + done.stderr
        creates = [c for c in calls if c.startswith("create secret generic")]
        assert len(creates) == 2, calls
        assert "--from-file=session_secret=/tmp/session_secret" in next(c for c in creates if "-oauth-session" in c)
        assert "--from-file=token=/tmp/token" in next(c for c in creates if "-shared-token" in c)
        assert done.stdout.count("(minted)") == 2
        assert re.fullmatch(rb"[A-Za-z0-9]{32}", (tmp_path / "session_secret").read_bytes()) and re.fullmatch(rb"[A-Za-z0-9]{48}", (tmp_path / "token").read_bytes())

    def test_existing_secrets_are_kept_and_nothing_is_created(self, tmp_path):
        _, argv, env = _job(_render())
        done, calls = _run(tmp_path, argv, env, "  'get secret '*) exit 0 ;;")
        assert done.returncode == 0 and done.stdout.count("exists; kept") == 2
        assert not [c for c in calls if c.startswith("create")]

    def test_the_transition_carries_the_old_secrets_values_over(self, tmp_path):
        """The first upgrade from a chart before 0.37.0: the new names are absent, the old Helm-owned
        Secrets present — their values are copied, not replaced, so sessions and tickets survive."""
        _, argv, env = _job(_render())
        old_cookie = "b2xkLWNvb2tpZS1rZXktMzItY2hhcnMtbG9uZy0hISE="   # base64 of old-cookie-key-32-chars-long-!!!
        old_token = "b2xkLXRva2Vu"                                     # base64 of old-token
        done, calls = _run(tmp_path, argv, env, f"""
  'get secret t-group-sync-dashboard-oauth-session '*) exit 1 ;;
  'get secret t-group-sync-dashboard-report-shared-token '*) exit 1 ;;
  'get secret t-group-sync-dashboard-oauth-cookie -n x -o jsonpath={{.data.session_secret}}') printf '{old_cookie}' ;;
  'get secret t-group-sync-dashboard-report-token -n x -o jsonpath={{.data.token}}') printf '{old_token}' ;;
  'create secret generic t-group-sync-dashboard-oauth-session '*) cp /tmp/session_secret {tmp_path}/cookie; exit 0 ;;
  'create secret generic t-group-sync-dashboard-report-shared-token '*) cp /tmp/token {tmp_path}/token; exit 0 ;;""")
        assert done.returncode == 0, done.stdout + done.stderr
        assert (tmp_path / "cookie").read_bytes() == b"old-cookie-key-32-chars-long-!!!"
        assert (tmp_path / "token").read_bytes() == b"old-token"
        assert done.stdout.count("carried over from") == 2

    def test_the_carried_value_survives_byte_for_byte_and_a_read_error_is_not_absent(self, tmp_path):
        """A command substitution strips a trailing newline; the copy goes through a file instead
        (Grok N2). And a Forbidden on the legacy read is a failed Job to retry, never "absent → mint a
        new value" (Grok N6)."""
        import base64
        _, argv, env = _job(_render())
        with_newline = base64.b64encode(b"old-key-with-newline\n").decode()
        done, calls = _run(tmp_path, argv, env, f"""
  'get secret t-group-sync-dashboard-oauth-session '*) echo 'Error from server (NotFound): secrets "x" not found' >&2; exit 1 ;;
  'get secret t-group-sync-dashboard-report-shared-token '*) echo 'Error from server (NotFound): secrets "x" not found' >&2; exit 1 ;;
  'get secret t-group-sync-dashboard-oauth-cookie -n x -o jsonpath={{.data.session_secret}}') printf '{with_newline}' ;;
  'get secret t-group-sync-dashboard-report-token -n x -o jsonpath={{.data.token}}') echo 'Error from server (NotFound): secrets "t-group-sync-dashboard-report-token" not found' >&2; exit 1 ;;
  'create secret generic t-group-sync-dashboard-oauth-session '*) cp /tmp/session_secret {tmp_path}/carried; exit 0 ;;
  'create secret generic '*) exit 0 ;;""")
        assert done.returncode == 0, done.stdout + done.stderr
        assert (tmp_path / "carried").read_bytes() == b"old-key-with-newline\n", "the trailing newline survived"
        assert "--from-file=session_secret=/tmp/session_secret" in "\n".join(calls)
        assert "carried over from" in done.stdout and "(minted)" in done.stdout, "the cookie carried, the token (no legacy) minted"
        # a Forbidden on the legacy read: fail, do not mint
        (tmp_path / "calls").unlink()
        done, calls = _run(tmp_path, argv, env, """
  'get secret t-group-sync-dashboard-oauth-session '*) echo 'Error from server (NotFound): x' >&2; exit 1 ;;
  'get secret t-group-sync-dashboard-oauth-cookie '*) echo 'Error from server (Forbidden): secrets "x" is forbidden' >&2; exit 1 ;;
  'create secret generic '*) exit 0 ;;""")
        assert done.returncode == 1 and "could not read secret" in done.stderr
        assert not [c for c in calls if c.startswith("create")], "no mint on a read error"

    def test_a_lost_race_is_kept_and_a_real_failure_fails(self, tmp_path):
        _, argv, env = _job(_render())
        done, _ = _run(tmp_path, argv, env, """
  'get secret '*) echo 'Error from server (NotFound): x' >&2; exit 1 ;;
  'create secret generic '*) echo 'Error from server (AlreadyExists): secrets "x" already exists' >&2; exit 1 ;;""")
        assert done.returncode == 0 and done.stdout.count("appeared meanwhile; kept") == 2, done.stdout + done.stderr
        done, _ = _run(tmp_path, argv, env, """
  'get secret '*) echo 'Error from server (NotFound): x' >&2; exit 1 ;;
  'create secret generic '*) echo 'Error from server (Forbidden): secrets is forbidden' >&2; exit 1 ;;""")
        assert done.returncode == 1 and "FAIL: could not create" in done.stderr
