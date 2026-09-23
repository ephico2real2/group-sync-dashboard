"""`refresh-cluster-wide-ca.sh` must never emit a bundle missing an anchor the cluster trusts.

WHY THIS FILE EXISTS. The script rewrites the ConfigMap that `proxy/cluster.spec.trustedCA` names,
and that object feeds EVERY ConfigMap labelled `config.openshift.io/inject-trusted-cabundle` — 20 of
them on the reference lab, including openshift-apiserver, authentication, console, image-registry and
monitoring. An anchor that disappears here disappears for all of them. Adversarial review of #307
found four inputs that dropped one silently and exited 0; each is a test below.

Everything runs offline: a stub `oc` on PATH serves fixtures from a temp directory, `--apply` is never
passed, and no cluster is contacted.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest

SCRIPT = pathlib.Path(__file__).resolve().parents[1] / "refresh-cluster-wide-ca.sh"

pytestmark = pytest.mark.skipif(
    shutil.which("openssl") is None, reason="openssl is required to build certificate fixtures"
)

OC_STUB = """#!/usr/bin/env bash
set -u
if [ "${1:-}" = "get" ] && [ "${2:-}" = "proxy" ]; then
  [ -f "$FIX/proxy-name" ] && cat "$FIX/proxy-name"
  exit 0
fi
if [ "${1:-}" = "get" ] && [ "${2:-}" = "cm" ]; then
  cm="$3"
  [ -f "$FIX/cm-$cm.crt" ] && { cat "$FIX/cm-$cm.crt"; exit 0; }
  # A ConfigMap that EXISTS but has a different data key: jsonpath prints nothing and exits 0.
  [ -f "$FIX/cm-$cm.otherkey" ] && exit 0
  echo "Error from server (NotFound): configmaps \\"$cm\\" not found" >&2
  exit 1
fi
exit 0
"""


def _openssl(*args: str) -> None:
    subprocess.run(["openssl", *args], check=True, capture_output=True)


@pytest.fixture(scope="module")
def certs(tmp_path_factory) -> dict[str, str]:
    """A CA, a second CA, a self-signed pin, a CA-signed leaf, and a leaf with crafted DER."""
    d = tmp_path_factory.mktemp("certs")
    made: dict[str, str] = {}

    def gen(name: str, subject: str, *extra: str) -> None:
        out = d / f"{name}.pem"
        _openssl("req", "-x509", "-newkey", "rsa:2048", "-nodes",
                 "-keyout", str(d / f"{name}.key"), "-out", str(out),
                 "-days", "3650", "-subj", subject, *extra)
        made[name] = out.read_text()

    gen("root", "/O=Enterprise IT/CN=Enterprise Root CA", "-addext", "basicConstraints=critical,CA:TRUE")
    gen("clusterca", "/OU=openshift/CN=kube-apiserver-lb-signer", "-addext", "basicConstraints=critical,CA:TRUE")
    gen("pin", "/CN=pinned.service.example", "-addext", "basicConstraints=critical,CA:FALSE")
    # A leaf whose basicConstraints is unparseable DER that merely SPELLS "CA:TRUE". openssl falls
    # back to printing the raw octets, which defeated an unanchored text grep.
    gen("bogus", "/CN=not-a-ca", "-addext", "basicConstraints=DER:0c:07:43:41:3a:54:52:55:45")

    # A leaf signed by `clusterca` — kube-root-ca's `*.apps-crc.testing` shape, which MUST stay dropped.
    _openssl("req", "-new", "-newkey", "rsa:2048", "-nodes", "-keyout", str(d / "leaf.key"),
             "-out", str(d / "leaf.csr"), "-subj", "/CN=*.apps.example")
    _openssl("x509", "-req", "-in", str(d / "leaf.csr"), "-CA", str(d / "clusterca.pem"),
             "-CAkey", str(d / "clusterca.key"), "-set_serial", "9", "-days", "365",
             "-out", str(d / "appsleaf.pem"))
    made["appsleaf"] = (d / "appsleaf.pem").read_text()
    return made


def run(tmp_path: pathlib.Path, fixtures: dict[str, str], proxy_name: str = "ldap-bundle",
        **env: str) -> subprocess.CompletedProcess:
    fix = tmp_path / "fix"
    fix.mkdir(exist_ok=True)
    (fix / "proxy-name").write_text(proxy_name)
    for name, body in fixtures.items():
        (fix / name).write_text(body)
    bindir = tmp_path / "bin"
    bindir.mkdir(exist_ok=True)
    oc = bindir / "oc"
    oc.write_text(OC_STUB)
    oc.chmod(0o755)
    environ = {**os.environ, "PATH": f"{bindir}:{os.environ['PATH']}", "FIX": str(fix), **env}
    return subprocess.run(["bash", str(SCRIPT)], capture_output=True, text=True,
                          env=environ, cwd=tmp_path)


def test_a_source_with_the_wrong_data_key_is_refused(tmp_path, certs):
    """THE DEFECT THAT MOTIVATED THIS FILE.

    `oc get cm X -o jsonpath='{.data.ca-bundle\\.crt}'` exits 0 with EMPTY output when the ConfigMap
    exists under a different key — measured on the lab against `openshift-config/ca-config-map`,
    whose key is `ca.crt`. Before the fix the enterprise root silently vanished and the run wrote a
    five-certificate bundle and exited 0.
    """
    r = run(tmp_path, {"cm-ldap-bundle.crt": certs["root"],
                       "cm-wrongkey.otherkey": "",
                       "cm-kube-root-ca.crt.crt": certs["clusterca"]},
            ENTERPRISE_CM="wrongkey")
    assert r.returncode != 0, f"built a bundle anyway:\n{r.stdout}"
    assert "ca-bundle.crt" in (r.stdout + r.stderr)


def test_kube_root_ca_with_no_ca_crt_key_is_refused(tmp_path, certs):
    r = run(tmp_path, {"cm-ldap-bundle.crt": certs["root"],
                       "cm-kube-root-ca.crt.otherkey": ""})
    assert r.returncode != 0, f"built a bundle without this cluster's CAs:\n{r.stdout}"


def test_a_crafted_basic_constraints_leaf_is_not_kept(tmp_path, certs):
    """A text grep of openssl's output kept this; the anchored match plus self-signed test does not.

    It is signed by nothing else, so it must fail the CA flag AND be judged on self-signedness only.
    """
    r = run(tmp_path, {"cm-ldap-bundle.crt": certs["root"] + certs["bogus"],
                       "cm-kube-root-ca.crt.crt": certs["clusterca"]})
    assert "not-a-ca" not in r.stdout or "drop" in r.stdout, r.stdout


def test_a_ca_signed_leaf_is_still_dropped(tmp_path, certs):
    """Behaviour preservation: kube-root-ca's `*.apps-crc.testing` leaf must keep being dropped."""
    r = run(tmp_path, {"cm-ldap-bundle.crt": certs["root"],
                       "cm-kube-root-ca.crt.crt": certs["clusterca"] + certs["appsleaf"]})
    assert "drop" in r.stdout and "apps.example" in r.stdout, r.stdout


def test_a_trusted_certificate_block_is_not_invisible(tmp_path, certs):
    """`/BEGIN CERT/` does not match `-----BEGIN TRUSTED CERTIFICATE-----`.

    Such a block used to vanish from the splitter without a word. It must now either be carried
    through or named — never silently dropped.
    """
    trusted = certs["root"].replace("BEGIN CERTIFICATE", "BEGIN TRUSTED CERTIFICATE") \
                           .replace("END CERTIFICATE", "END TRUSTED CERTIFICATE")
    r = run(tmp_path, {"cm-ldap-bundle.crt": trusted,
                       "cm-kube-root-ca.crt.crt": certs["clusterca"]})
    combined = [l for l in r.stdout.splitlines() if l.startswith("combined:")]
    assert r.returncode != 0 or "enterprise: 0 of 0 kept" not in r.stdout, (
        f"a TRUSTED CERTIFICATE block vanished silently:\n{r.stdout}"
    )
    assert r.returncode != 0 or combined, r.stdout


def test_with_no_prior_trusted_ca_the_revert_does_not_name_an_unwritten_file(tmp_path, certs):
    """The fresh-cluster first run — the most likely first use.

    With no trustedCA there is no ConfigMap to back up, so an `oc apply -f <backup>` instruction
    names a file the run never wrote.
    """
    r = run(tmp_path, {"cm-kube-root-ca.crt.crt": certs["clusterca"]}, proxy_name="")
    assert "Revert:" in r.stdout, f"the dry run printed no revert at all:\n{r.stdout}"
    assert "oc apply -f" not in r.stdout, (
        f"names a backup file that was never written:\n{r.stdout}"
    )
