"""render-manifests.sh renders the chart to one file per object and never reads a session key (#625).

Since chart 0.37.0 the secrets-mint hook mints `<fullname>-oauth-session` on the cluster only when it is absent,
so a render carries no session Secret and applying one signs nobody out. The script used to read the
pre-0.37.0 `<release>-oauth-cookie` and pass it as `oauthProxy.cookieSecret`, which rendered a different,
plain Secret; with no such Secret it warned, falsely, that the apply would sign everyone out. The real script
runs here against a stub `oc` that would hand back an old cookie, so the test fails if anything reads it again.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
SCRIPT = REPO / "local-development" / "render-manifests.sh"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def _render(tmp_path: pathlib.Path) -> tuple[subprocess.CompletedProcess, list[dict]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    oc = bin_dir / "oc"
    # Any `oc get secret` answers with an old session key, base64 encoded, as `-o jsonpath` would.
    oc.write_text('#!/bin/sh\ncase "$*" in *"get secret"*) printf %s b2xkLWNvb2tpZS12YWx1ZQ== ;; esac\n')
    oc.chmod(0o755)
    # The script's splitter needs PyYAML: exec this interpreter (a symlink would lose its virtualenv).
    py = bin_dir / "python3"
    py.write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n')
    py.chmod(0o755)
    out = tmp_path / "out"
    env = {**os.environ, "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}"}
    done = subprocess.run(["bash", str(SCRIPT), "-o", str(out)], env=env,
                          capture_output=True, text=True, timeout=180, check=False)
    docs = [yaml.safe_load(p.read_text()) for p in sorted(out.glob("[0-9][0-9]-*.yaml"))] if out.exists() else []
    return done, docs


def test_a_render_carries_no_session_secret_and_reads_no_old_cookie(tmp_path: pathlib.Path) -> None:
    done, docs = _render(tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert docs, done.stdout
    secrets = [d for d in docs if d["kind"] == "Secret"]
    assert not any("session_secret" in (d.get("data") or {}) for d in secrets), [d["metadata"]["name"] for d in secrets]


def test_the_summary_makes_no_sign_out_claim(tmp_path: pathlib.Path) -> None:
    done, _ = _render(tmp_path)
    assert done.returncode == 0, done.stdout + done.stderr
    assert "sign out" not in done.stdout and "cookie" not in done.stdout, done.stdout
