"""#244 CA visibility: the enterprise root, validity dates, and the #314 warnings channel."""
from __future__ import annotations

import base64
import hashlib
import logging
import os
import ssl
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.clusterconfig import FINDING_CODES
from gsd.clusterconfig.ca import (match_enterprise, sha256_of_pem, summarise_cluster,
                                  summarise_pem, tls_verify_failure, validity_word)
from gsd.clusterconfig.warnings import ca_warnings
from gsd.clusterconfig.writer import CreateRequest, WriteRefused, validate
from gsd.clusterconfig.writer import test_connection as probe_connection   # not a test: pytest would collect the name
from gsd.config import ClusterConfig, Settings
from gsd.kube import ClusterError, UNREACHABLE
from gsd.poller import Poller, _log_poll_failure
from gsd.store import Store
from test_visibility import H, _MapResolver


def _cert(tmp_path: Path, cn: str, days: int, *, ca: bool = True) -> Path:
    crt = tmp_path / f"{cn}.crt"
    if ca:
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", f"-days", str(days),
                        "-subj", f"/CN={cn}", "-keyout", str(tmp_path / f"{cn}.key"),
                        "-out", str(crt)], check=True, capture_output=True)
        return crt
    ca_crt = _cert(tmp_path, f"{cn}-ca", 3650, ca=True)
    cnf = tmp_path / f"{cn}.cnf"
    cnf.write_text("[v3]\nbasicConstraints=CA:FALSE\nsubjectAltName=DNS:leaf\n")
    subprocess.run(["openssl", "req", "-new", "-newkey", "rsa:2048", "-nodes",
                    "-subj", f"/CN={cn}", "-keyout", str(tmp_path / f"{cn}.key"),
                    "-out", str(tmp_path / f"{cn}.csr")], check=True, capture_output=True)
    subprocess.run(["openssl", "x509", "-req", "-in", str(tmp_path / f"{cn}.csr"),
                    "-CA", str(ca_crt), "-CAkey", str(tmp_path / f"{cn}-ca.key"),
                    "-CAcreateserial", "-days", str(days), "-extfile", str(cnf), "-extensions", "v3",
                    "-out", str(crt)], check=True, capture_output=True)
    return crt


def test_a_ca_pem_lists_subject_issuer_dates_and_fingerprint(tmp_path):
    crt = _cert(tmp_path, "ldap-enterprise-ca", 365)
    pem = crt.read_text()
    certs = summarise_pem(pem)
    assert len(certs) == 1
    assert certs[0]["subject"] == "CN=ldap-enterprise-ca"
    assert certs[0]["issuer"] == "CN=ldap-enterprise-ca"
    assert certs[0]["notAfter"].endswith("Z") and "T" in certs[0]["notAfter"]
    assert certs[0]["notBefore"].endswith("Z")
    assert certs[0]["sha256"] == sha256_of_pem(pem)


def test_a_leaf_pasted_as_cadata_is_listed(tmp_path):
    crt = _cert(tmp_path, "mock-privateca", 90, ca=False)
    certs = summarise_pem(crt.read_text())
    assert len(certs) == 1
    assert certs[0]["subject"] == "CN=mock-privateca"
    assert ssl.create_default_context(cadata=crt.read_text()).get_ca_certs() == []


def test_a_pasted_bundle_is_not_merged_with_the_system_store(tmp_path):
    crt = _cert(tmp_path, "only-this", 30)
    certs = summarise_pem(crt.read_text())
    assert [c["subject"] for c in certs] == ["CN=only-this"]
    assert len(certs) == 1


def test_sha256_matches_openssl(tmp_path):
    crt = _cert(tmp_path, "fp", 30)
    pem = crt.read_text()
    openssl = subprocess.run(["openssl", "x509", "-noout", "-fingerprint", "-sha256", "-in", str(crt)],
                             check=True, capture_output=True, text=True).stdout
    hexed = openssl.split("=", 1)[1].replace(":", "").strip().lower()
    assert sha256_of_pem(pem) == hexed
    assert hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem.strip() + "\n")).hexdigest() == hexed


def test_enterprise_root_matches_fingerprint_not_a_colliding_subject(tmp_path):
    first = _cert(tmp_path, "shared-dn", 40)
    other = tmp_path / "other"
    other.mkdir()
    second = _cert(other, "shared-dn", 40)
    fa, fb = sha256_of_pem(first.read_text()), sha256_of_pem(second.read_text())
    assert fa != fb
    ca, cb = summarise_pem(first.read_text())[0], summarise_pem(second.read_text())[0]
    assert ca["subject"] == cb["subject"]
    assert match_enterprise(ca, fa, "") and not match_enterprise(cb, fa, "")
    assert match_enterprise(cb, "", "CN=shared-dn")


def test_an_empty_pin_does_not_claim_an_enterprise_root(tmp_path):
    crt = _cert(tmp_path, "any", 365)
    cluster = ClusterConfig("east", "https://api.east.example:6443", token_env="X",
                            ca_data=crt.read_text())
    trust = summarise_cluster(cluster, Settings())
    assert trust["enterpriseRoot"] is None
    assert trust["certificates"][0]["enterpriseRoot"] is None
    assert ca_warnings([cluster], Settings()) == []


def test_expiring_at_the_threshold_and_not_the_day_before():
    now = datetime(2026, 9, 28, tzinfo=timezone.utc)
    def word(days):
        end = now + timedelta(days=days)
        return validity_word("2020-01-01T00:00:00Z", end.strftime("%Y-%m-%dT%H:%M:%SZ"), now, 30)
    assert word(30) == "expiring"
    assert word(31) == "valid"
    # exactly notAfter: 0 days left → expiring; one second past → expired
    assert validity_word("2020-01-01T00:00:00Z", "2026-09-28T00:00:00Z", now, 30) == "expiring"
    assert validity_word("2020-01-01T00:00:00Z", "2026-09-27T23:59:59Z", now, 30) == "expired"
    assert validity_word("2026-10-01T00:00:00Z", "2027-01-01T00:00:00Z", now, 30) == "not-yet-valid"


def test_trusted_bundle_expiry_watches_only_the_enterprise_root(tmp_path, monkeypatch):
    root = _cert(tmp_path, "enterprise", 10)
    other = _cert(tmp_path, "public-ca", 5)
    bundle = tmp_path / "bundle.pem"
    bundle.write_text(root.read_text() + other.read_text())
    monkeypatch.setenv("GSD_TRUSTED_CA_FILE", str(bundle))
    settings = Settings(enterprise_ca_sha256=sha256_of_pem(root.read_text()), ca_expiry_warning_days=30)
    cluster = ClusterConfig("east", "https://api.east.example:6443", token_env="X")
    trust = summarise_cluster(cluster, settings)
    assert trust["count"] == len(cluster.verify().get_ca_certs())
    assert [c["subject"] for c in trust["certificates"]] == ["CN=enterprise"]
    codes = {w["code"] for w in ca_warnings([cluster], settings)}
    assert codes == {"ca-expiring"}
    assert all("public-ca" not in w["detail"] for w in ca_warnings([cluster], settings))


def test_ca_warnings_are_not_findings():
    for code in ("ca-expiring", "ca-expired", "ca-not-yet-valid", "ca-not-enterprise"):
        assert code not in FINDING_CODES


def test_the_action_text_is_identical_in_the_log_and_the_api(tmp_path, caplog):
    cluster = ClusterConfig("east", "https://api.east.example:6443", token_env="X",
                            source="secret:gsd-cluster-east")
    action, store = tls_verify_failure(cluster)
    with caplog.at_level(logging.WARNING, logger="gsd.poller"):
        _log_poll_failure(cluster, ClusterError(
            UNREACHABLE, "ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"))
    line = caplog.messages[-1]
    # events._format_value quotes a value with a space: store="the system trust store", store=/a/path
    assert action in line and (f"store={store}" in line or f'store="{store}"' in line)
    db = str(tmp_path / "a.db")
    store_db = Store(db)
    store_db.upsert_cluster("east", "https://api.east.example:6443", True,
                            source="secret:gsd-cluster-east", credential="bearer")
    store_db.record_poll("east", "unreachable",
                         "ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
    settings = Settings(clusters=[cluster], db_path=db, oauth_proxy_enabled=True)
    app = build_app(settings, run_poller=False)
    app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
    app.state.tier_resolver = _MapResolver({"root": "all"})
    with TestClient(app) as client:
        row = client.get("/api/clusterconfigs", headers=H("root")).json()["clusters"]
    east = next(c for c in row if c["id"] == "east")
    assert east["action"] == action and east["store"] == store
    assert east["error"].startswith("ConnectError:")


def test_the_test_response_carries_the_certificate_summary(tmp_path, monkeypatch):
    import gsd.clusterconfig.writer as writer
    crt = _cert(tmp_path, "form-ca", 60)
    pem = crt.read_text()
    req = CreateRequest(name="west", server="https://api.west.example:6443",
                        credential_kind="bearerToken", token="t" * 20, tls_mode="caData",
                        ca_data=base64.b64encode(pem.encode()).decode())
    monkeypatch.setattr(writer, "_probe",
                        lambda *a, **k: ({"reachable": True, "server_version": "v1.0",
                                          "identity": "system:serviceaccount:ns:sa"}, None))
    out = probe_connection(req, "ns", host_name="host", timeout=1, viewer="root")
    assert [c["subject"] for c in out["certificates"]] == ["CN=form-ca"]
    assert out["certificates"][0]["notAfter"].endswith("Z")


def test_ca_data_invalid_returns_what_decoded(tmp_path):
    good = _cert(tmp_path, "half-good", 30).read_text()
    pem = good + "-----BEGIN CERTIFICATE-----\nnot-a-cert\n-----END CERTIFICATE-----\n"
    req = CreateRequest(name="west", server="https://api.west.example:6443",
                        credential_kind="bearerToken", token="t" * 20, tls_mode="caData",
                        ca_data=base64.b64encode(pem.encode()).decode())
    try:
        validate(req, "ns", host_name="host", taken={})
    except WriteRefused as exc:
        assert exc.code == "ca-data-invalid"
        assert [c["subject"] for c in exc.certificates] == ["CN=half-good"]
    else:
        raise AssertionError("expected WriteRefused")


def test_a_secret_and_a_configmap_are_equal_sources(tmp_path, monkeypatch):
    """The same PEM is listed the same way; the Kubernetes kind is a fact, not a scrub."""
    pem = _cert(tmp_path, "shared-root", 365).read_text()
    digest = sha256_of_pem(pem)
    secret = ClusterConfig("from-secret", "https://api.a.example:6443", token_env="X",
                           ca_data=pem, source="secret:gsd-cluster-from-secret")
    bundle = tmp_path / "from-cm.pem"
    bundle.write_text(pem)
    monkeypatch.setenv("GSD_TRUSTED_CA_FILE", str(bundle))
    declared = ClusterConfig("from-cm", "https://api.b.example:6443", token_env="X",
                             source="configmap:declare:0")
    settings = Settings(enterprise_ca_sha256=digest)
    a, b = summarise_cluster(secret, settings), summarise_cluster(declared, settings)
    assert a["certificates"][0]["sha256"] == b["certificates"][0]["sha256"] == digest
    assert a["sourceKind"] == "secret" and b["sourceKind"] == "configmap"
    assert a["certificates"][0]["subject"] == b["certificates"][0]["subject"] == "CN=shared-root"


def test_a_bundle_file_is_decoded_once_until_it_changes(tmp_path, monkeypatch):
    """Not asked (OB2): the API summarises every live cluster on every read; a bundle is decoded once per
    (mtime, size), like config._trusted_ca_context, and again when the file changes."""
    import os
    import gsd.clusterconfig.ca as ca
    bundle = tmp_path / "bundle.pem"
    bundle.write_text(_cert(tmp_path, "first", 365).read_text())
    os.utime(bundle, ns=(1_000_000_000, 1_000_000_000))
    decoded = []
    real = ca.summarise_pem
    monkeypatch.setattr(ca, "summarise_pem", lambda pem: decoded.append(1) or real(pem))
    monkeypatch.setattr(ca, "_BUNDLE_CACHE", {}, raising=False)
    first = ca.summarise_paths([str(bundle)])
    again = ca.summarise_paths([str(bundle)])
    assert [c["subject"] for c in first] == ["CN=first"] and again == first
    assert len(decoded) == 1, "the second read of an unchanged bundle decodes nothing"
    bundle.write_text(_cert(tmp_path, "second", 365).read_text())
    os.utime(bundle, ns=(2_000_000_000, 2_000_000_000))
    assert [c["subject"] for c in ca.summarise_paths([str(bundle)])] == ["CN=second"]
    assert len(decoded) == 2, "a changed bundle is decoded again"


def test_the_action_and_store_agree_in_the_log_and_the_api_for_every_mode(tmp_path, caplog):
    """Not asked (OB2): the DoD names three modes (trusted-bundle, caData, a file); the spec's test held only
    the first. Each mode's poller line carries exactly the pair the API row carries."""
    pem = _cert(tmp_path, "pin", 365).read_text()
    modes = {
        "trusted-bundle": ClusterConfig("east", "https://api.east.example:6443", token_env="X",
                                        source="secret:gsd-cluster-east"),
        "caData": ClusterConfig("east", "https://api.east.example:6443", token_env="X",
                                source="secret:gsd-cluster-east", ca_data=pem),
        "caBundleFile": ClusterConfig("east", "https://api.east.example:6443", token_env="X",
                                      source="values", ca_bundle_file=str(tmp_path / "pin.crt")),
    }
    for mode, cluster in modes.items():
        assert cluster.tls_mode["ca"] == mode
        action, store = tls_verify_failure(cluster)
        caplog.clear()
        with caplog.at_level(logging.WARNING, logger="gsd.poller"):
            _log_poll_failure(cluster, ClusterError(
                UNREACHABLE, "ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed"))
        line = caplog.messages[-1]
        assert action in line and (f"store={store}" in line or f'store="{store}"' in line), mode
        db = str(tmp_path / f"{mode}.db")
        store_db = Store(db)
        store_db.upsert_cluster("east", "https://api.east.example:6443", True,
                                source=cluster.source, credential="bearer")
        store_db.record_poll("east", "unreachable",
                             "ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed")
        settings = Settings(clusters=[cluster], db_path=db, oauth_proxy_enabled=True)
        app = build_app(settings, run_poller=False)
        app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
        app.state.tier_resolver = _MapResolver({"root": "all"})
        with TestClient(app) as client:
            east = next(c for c in client.get("/api/clusterconfigs", headers=H("root")).json()["clusters"]
                        if c["id"] == "east")
        assert (east["action"], east["store"]) == (action, store), mode


def test_system_root_can_match_enterprise_fingerprint(tmp_path, monkeypatch):
    root = _cert(tmp_path, "system-root", 365)
    monkeypatch.delenv("GSD_TRUSTED_CA_FILE", raising=False)
    monkeypatch.setenv("SSL_CERT_FILE", str(root))
    monkeypatch.setenv("SSL_CERT_DIR", str(tmp_path / "absent"))
    settings = Settings(enterprise_ca_sha256=sha256_of_pem(root.read_text()))
    cluster = ClusterConfig("east", "https://unused.invalid")
    trust = summarise_cluster(cluster, settings)
    assert trust["enterpriseRoot"] is True
    assert trust["certificates"][0]["sha256"] == settings.enterprise_ca_sha256


def test_mounted_bundle_count_includes_system_roots(tmp_path, monkeypatch):
    system = _cert(tmp_path, "system", 365)
    mounted = _cert(tmp_path, "mounted", 365)
    monkeypatch.setenv("SSL_CERT_FILE", str(system))
    monkeypatch.setenv("SSL_CERT_DIR", str(tmp_path / "absent"))
    monkeypatch.setenv("GSD_TRUSTED_CA_FILE", str(mounted))
    cluster = ClusterConfig("east", "https://unused.invalid")
    trust = summarise_cluster(cluster, Settings())
    assert trust["count"] == len(cluster.verify().get_ca_certs()) == 2


def test_non_text_bundle_does_not_crash_inventory(tmp_path):
    path = tmp_path / "malformed-ca.pem"
    path.write_bytes(bytes([255]))
    cluster = ClusterConfig("east", "https://unused.invalid", ca_bundle_file=str(path))
    assert summarise_cluster(cluster, Settings())["count"] == 0


def test_warning_does_not_start_a_fractional_day_early():
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = now + timedelta(days=30, seconds=1)
    assert validity_word("2020-01-01T00:00:00Z", end.isoformat(), now, 30) == "valid"


def test_a_non_ascii_character_in_a_mounted_block_breaks_neither_the_read_nor_the_start(tmp_path, monkeypatch):
    """Not asked (OB3): one pasted no-break space inside a PEM block of a mounted bundle. OpenSSL refuses the
    bundle and the poller says so (`cannot load trusted CA bundle`), but ssl raises TypeError, not SSLError,
    for a non-ASCII cadata: it escaped summarise_cluster, GET /api/clusterconfigs answered 500, and
    poller.start() raised before its first poll, so the app did not start."""
    system = _cert(tmp_path, "system-root", 365)
    monkeypatch.setenv("SSL_CERT_FILE", str(system))
    monkeypatch.setenv("SSL_CERT_DIR", str(tmp_path / "absent"))
    pasted = _cert(tmp_path, "pasted", 365).read_text()
    bundle = tmp_path / "ca-bundle.crt"
    bundle.write_text(pasted.replace("-----END CERTIFICATE-----", " \n-----END CERTIFICATE-----"))
    monkeypatch.setenv("GSD_TRUSTED_CA_FILE", str(bundle))
    cluster = ClusterConfig("east", "https://api.east.example:6443", token_env="X")
    assert summarise_cluster(cluster, Settings())["count"] == 1  # the system root; the pasted block is skipped
    db = str(tmp_path / "p.db")
    settings = Settings(clusters=[cluster], db_path=db, oauth_proxy_enabled=True)
    Poller(Store(db), settings)._announce_shared_api_urls()  # what poller.start() runs before its first poll
    app = build_app(settings, run_poller=False)
    app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
    app.state.tier_resolver = _MapResolver({"root": "all"})
    with TestClient(app) as client:
        assert client.get("/api/clusterconfigs", headers=H("root")).status_code == 200


def test_a_bundle_swapped_by_kubelet_is_read_again_at_the_same_size_and_mtime(tmp_path, monkeypatch):
    """Not asked (OB3): kubelet updates a mounted ConfigMap by pointing `..data` at a new timestamped
    directory (#340), so the changed file is a new inode. config._trusted_ca_context keys on the inode; a
    summary keyed on (mtime_ns, size) alone served the old list while the verifier trusted the new one."""
    import gsd.clusterconfig.ca as ca
    monkeypatch.setattr(ca, "_BUNDLE_CACHE", {}, raising=False)
    before = _cert(tmp_path, "swap-before", 365).read_text()
    after = _cert(tmp_path, "swap-after-x", 365).read_text()
    size = max(len(before), len(after)) + 8

    def padded(pem):
        return pem + "#" * (size - len(pem) - 1) + "\n"  # text between PEM blocks is ignored

    volume = tmp_path / "volume"
    first = volume / "..2026_01_01_00_00_00.000000001"
    first.mkdir(parents=True)
    (first / "ca-bundle.crt").write_text(padded(before))
    (volume / "..data").symlink_to(first.name)
    (volume / "ca-bundle.crt").symlink_to("..data/ca-bundle.crt")
    path = str(volume / "ca-bundle.crt")
    assert [c["subject"] for c in ca.summarise_file(path)] == ["CN=swap-before"]
    old = os.stat(path)
    second = volume / "..2026_01_01_00_00_01.000000002"
    second.mkdir()
    (second / "ca-bundle.crt").write_text(padded(after))
    os.utime(second / "ca-bundle.crt", ns=(old.st_atime_ns, old.st_mtime_ns))  # written in the same tick
    (volume / "..data_tmp").symlink_to(second.name)
    os.rename(volume / "..data_tmp", volume / "..data")  # AtomicWriter's swap
    new = os.stat(path)
    assert (new.st_mtime_ns, new.st_size) == (old.st_mtime_ns, old.st_size) and new.st_ino != old.st_ino
    assert [c["subject"] for c in ca.summarise_file(path)] == ["CN=swap-after-x"]


def test_without_a_mounted_bundle_the_summary_is_the_store_httpx_verifies_with(tmp_path, monkeypatch):
    """Not asked (OB3): with GSD_TRUSTED_CA_FILE unset, or naming nothing that exists, verify() returns True and
    httpx builds its own default store (certifi's bundle unless SSL_CERT_FILE or SSL_CERT_DIR), not OpenSSL's:
    measured, 193 OpenSSL roots were counted and pinnable while the verifier loaded certifi's 121."""
    import certifi
    import httpx
    root = _cert(tmp_path, "certifi-only-root", 365)
    for var in ("GSD_TRUSTED_CA_FILE", "SSL_CERT_FILE", "SSL_CERT_DIR"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(certifi, "where", lambda: str(root))
    settings = Settings(enterprise_ca_sha256=sha256_of_pem(root.read_text()))
    cluster = ClusterConfig("east", "https://unused.invalid")
    for configured in (None, str(tmp_path / "absent" / "ca-bundle.crt")):
        if configured:
            monkeypatch.setenv("GSD_TRUSTED_CA_FILE", configured)
        assert cluster.verify() is True
        trust = summarise_cluster(cluster, settings)
        assert trust["count"] == len(httpx.create_ssl_context().get_ca_certs()) == 1
        assert trust["enterpriseRoot"] is True


def test_the_trust_store_is_decoded_once_per_certificate(tmp_path, monkeypatch):
    """Not asked (OB3): the union decodes every root of the verifier's store. Uncached that is 25 ms per
    summary (193 roots), two summaries per live cluster per read: one read with ten trusted-bundle clusters
    took 0.52 s, the cost the bundle cache was added to remove. A root is decoded once per process."""
    import gsd.clusterconfig.ca as ca
    system = tmp_path / "system.pem"
    system.write_text(_cert(tmp_path, "sys-a", 365).read_text() + _cert(tmp_path, "sys-b", 365).read_text())
    monkeypatch.setenv("SSL_CERT_FILE", str(system))
    monkeypatch.setenv("SSL_CERT_DIR", str(tmp_path / "absent"))
    monkeypatch.setenv("GSD_TRUSTED_CA_FILE", str(_cert(tmp_path, "mounted-c", 365)))
    if hasattr(ca, "_decode_der"):
        ca._decode_der.cache_clear()
    decoded = []
    real = ca.decode_one
    monkeypatch.setattr(ca, "decode_one", lambda pem: decoded.append(1) or real(pem))
    cluster = ClusterConfig("east", "https://unused.invalid")
    first = summarise_cluster(cluster, Settings())
    after_first = len(decoded)
    again = summarise_cluster(cluster, Settings())
    assert first == again and first["count"] == 3
    assert after_first == 3 and len(decoded) == after_first, "a second summary of an unchanged store decodes nothing"


def test_only_a_ca_data_invalid_refusal_carries_the_certificates(tmp_path):
    """Not asked (OB3): §3.6 gives the object answer {code, message, certificates} to a `ca-data-invalid`
    refusal that decoded a block; every other refusal keeps today's string. The writer attached what decoded
    to ANY parser refusal of a caData request, so a `server-invalid` answered an object too."""
    pem = _cert(tmp_path, "form-ca", 365).read_text()
    req = CreateRequest(name="west", server="https://api.west.example:6443/some/path",
                        credential_kind="bearerToken", token="t" * 20, tls_mode="caData",
                        ca_data=base64.b64encode(pem.encode()).decode())
    try:
        validate(req, "ns", host_name="host", taken={})
    except WriteRefused as exc:
        assert exc.code == "server-invalid" and exc.certificates == []
    else:
        raise AssertionError("expected WriteRefused")


def test_a_non_utf8_comment_does_not_hide_a_bundle_the_verifier_loads(tmp_path):
    """Not asked (OB3): OpenSSL skips what lies between PEM blocks, so a bundle with a Latin-1 comment loads
    and verifies; read as UTF-8 it summarised to nothing, and a pinned root in it read `ca-not-enterprise`."""
    root = _cert(tmp_path, "latin1-root", 365).read_text()
    bundle = tmp_path / "corp-bundle.crt"
    bundle.write_bytes("# Société Générale\n".encode("latin-1") + root.encode())
    cluster = ClusterConfig("west", "https://api.west.example:6443", token_env="X", ca_bundle_file=str(bundle))
    assert len(cluster.verify().get_ca_certs()) == 1
    settings = Settings(enterprise_ca_sha256=sha256_of_pem(root))
    trust = summarise_cluster(cluster, settings)
    assert trust["count"] == 1 and trust["enterpriseRoot"] is True
    assert ca_warnings([cluster], settings) == []


def test_the_trust_store_context_is_built_once_until_the_store_changes(tmp_path, monkeypatch):
    """Not asked (OB2, #489): `_decode_der` caches each root's decode, but every summary of a trusted-bundle
    cluster still built the verifier's context — 2.4-3.7 ms (measured, OpenSSL 3.6.4), twice per live cluster
    per read: ten such clusters cost GET /api/clusterconfigs 53 ms bare and 83 ms with a mounted 128-block
    bundle, against 0.8 ms on main. The store's list is kept per identity — each mounted file's (inode,
    mtime_ns, size), SSL_CERT_FILE, SSL_CERT_DIR and certifi's path — and a swapped bundle is a new store."""
    import gsd.clusterconfig.ca as ca
    monkeypatch.setattr(ca, "_STORE_CACHE", {}, raising=False)
    built = []
    real_ssl, real_httpx = ca.ssl.create_default_context, ca.httpx.create_ssl_context

    def counted(*a, **k):
        if "cadata" not in k:   # decode_one builds a context per block; only the store's build counts
            built.append("store")
        return real_ssl(*a, **k)

    monkeypatch.setattr(ca.ssl, "create_default_context", counted)
    monkeypatch.setattr(ca.httpx, "create_ssl_context", lambda *a, **k: built.append("store") or real_httpx(*a, **k))
    monkeypatch.setenv("SSL_CERT_FILE", str(_cert(tmp_path, "system", 365)))
    monkeypatch.setenv("SSL_CERT_DIR", str(tmp_path / "absent"))
    mounted = _cert(tmp_path, "mounted", 365)
    monkeypatch.setenv("GSD_TRUSTED_CA_FILE", str(mounted))
    cluster = ClusterConfig("east", "https://unused.invalid")
    first = summarise_cluster(cluster, Settings())
    assert first["count"] == 2 and built == ["store"]
    assert summarise_cluster(cluster, Settings()) == first
    assert built == ["store"], "a second summary of an unchanged store builds no context"
    replacement = _cert(tmp_path, "mounted-2", 365).read_text()
    mounted.write_text(replacement)
    os.utime(mounted, ns=(2_000_000_000, 2_000_000_000))
    pinned = Settings(enterprise_ca_sha256=sha256_of_pem(replacement))
    assert summarise_cluster(cluster, pinned)["enterpriseRoot"] is True
    assert built == ["store", "store"], "a swapped bundle is a new store"


def test_a_paste_that_is_not_utf8_keeps_the_parsers_sentence_and_carries_what_decoded(tmp_path):
    """Not asked (OB2, #489): #466 refuses a caData that is not UTF-8 with the cause in the sentence
    (`… does not decode to a PEM bundle that loads: UnicodeDecodeError`). The writer's own decode answered
    `tls.caData must be a base64 PEM bundle` for the same paste — which is base64 — and carried no
    certificates. The summary reads the paste as summarise_file reads a bundle; the parser keeps its word."""
    good = _cert(tmp_path, "good", 365).read_text()
    raw = good.encode() + "# Société Générale\n".encode("latin-1")
    req = CreateRequest(name="west", server="https://api.west.example:6443",
                        credential_kind="bearerToken", token="t" * 20, tls_mode="caData",
                        ca_data=base64.b64encode(raw).decode())
    try:
        validate(req, "ns", host_name="host", taken={})
    except WriteRefused as exc:
        assert exc.code == "ca-data-invalid"
        assert exc.detail == "tlsClientConfig.caData does not decode to a PEM bundle that loads: UnicodeDecodeError"
        assert [c["subject"] for c in exc.certificates] == ["CN=good"]
    else:
        raise AssertionError("expected WriteRefused")


def test_the_poller_announces_a_ca_warning_once_when_it_appears_and_once_when_it_clears(tmp_path, caplog):
    """Not asked (OB2, #489), coverage: §3.3 says the poller logs a CA warning on appear and on clear the way it
    does for shared-api-url, and no test held it. One WARNING when a 10-day CA appears, nothing while it
    stands, one INFO when a 365-day CA replaces it."""
    from gsd.clusterconfig import parse_secret
    from test_clusterconfig import _secret

    def east(days, cn):
        pem = _cert(tmp_path, cn, days).read_text()
        cfg = {"bearerToken": "t" * 20, "tlsClientConfig": {"insecure": False,
               "caData": base64.b64encode(pem.encode()).decode()}}
        return parse_secret(_secret(config=cfg), host_name="crc-local")

    db = str(tmp_path / "p.db")
    settings = Settings(clusters=[], db_path=db, oauth_proxy_enabled=True)
    poller = Poller(Store(db), settings)
    settings.cluster_registry.replace([east(10, "soon-root")], [], at="now")

    def said():
        return [r for r in caplog.records if r.getMessage().startswith("ca-expiring")]

    with caplog.at_level(logging.INFO, logger="gsd.clusterconfig"):
        poller._announce_shared_api_urls()
        assert len(said()) == 1 and said()[0].levelno == logging.WARNING
        assert "state=appeared" in said()[0].getMessage() and "soon-root" in said()[0].getMessage()
        poller._announce_shared_api_urls()
        assert len(said()) == 1, "a standing warning speaks once"
        settings.cluster_registry.replace([east(365, "fresh-root")], [], at="now")
        poller._announce_shared_api_urls()
    assert len(said()) == 2 and said()[1].levelno == logging.INFO and "state=cleared" in said()[1].getMessage()
