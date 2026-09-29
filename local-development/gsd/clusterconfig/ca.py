"""Read a cluster's trusted certificates and say whether they are the enterprise root (#244).

A CA is public PKI. A Secret and a ConfigMap are equal sources. Nothing here is scrubbed.
"""
from __future__ import annotations

import functools
import hashlib
import os
import re
import ssl
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import httpx

from ..config import SA_CA_PATH, ClusterConfig, Settings

PEM_BLOCK = re.compile(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", re.S)

VALID = "valid"
EXPIRING = "expiring"
EXPIRED = "expired"
NOT_YET = "not-yet-valid"


def openssl_time(value: str) -> datetime:
    """OpenSSL's `Dec 31 08:38:15 2030 GMT` (or a double-spaced day) as UTC."""
    return datetime.strptime(" ".join(value.split()), "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)


def iso_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def dn_text(name: object) -> str:
    """get_ca_certs() subject/issuer tuples as a readable DN."""
    if isinstance(name, str):
        return name
    parts = []
    for rdn in name or ():
        for key, val in rdn:
            short = {"commonName": "CN", "organizationName": "O", "organizationalUnitName": "OU",
                     "countryName": "C", "stateOrProvinceName": "ST", "localityName": "L"}.get(key, key)
            parts.append(f"{short}={val}")
    return ",".join(parts)


def sha256_of_pem(pem: str) -> str:
    return hashlib.sha256(ssl.PEM_cert_to_DER_cert(pem.strip() + "\n")).hexdigest()


def normalise_sha256(value: str) -> str:
    return re.sub(r"[^0-9a-fA-F]", "", value or "").lower()


def pem_blocks(text: str) -> list[str]:
    return [m.group(0) for m in PEM_BLOCK.finditer(text or "")]


def _from_info(info: dict, pem: str | None) -> dict:
    return {
        "subject": dn_text(info.get("subject")),
        "issuer": dn_text(info.get("issuer")),
        "notBefore": iso_utc(openssl_time(info["notBefore"])),
        "notAfter": iso_utc(openssl_time(info["notAfter"])),
        "sha256": sha256_of_pem(pem) if pem else "",
    }


def decode_one(pem: str) -> dict | None:
    """One PEM block: get_ca_certs() for a CA, the private decoder for a leaf.

    create_default_context(cadata=) with a CA:FALSE leaf returns an empty list
    (measured on Python 3.14.7 / OpenSSL 3.6.4). _test_decode_cert is the same
    decoder getpeercert uses; it needs a path, so the block is written to a temp file.

    A block holding a non-ASCII character is not a certificate (RFC 7468 text is ASCII), and ssl
    raises TypeError, not SSLError, for such a cadata: it is skipped here, because a summary runs
    in the API, in the poller's start and in every discovery cycle, and must never raise.
    """
    if not pem.isascii():
        return None
    try:
        listed = ssl.create_default_context(cadata=pem).get_ca_certs()
    except ssl.SSLError:
        listed = []
    if listed:
        return _from_info(listed[0], pem)
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".crt", delete=False) as tmp:
            tmp.write(pem if pem.endswith("\n") else pem + "\n")
            path = tmp.name
        try:
            info = ssl._ssl._test_decode_cert(path)
        finally:
            os.unlink(path)
    except (OSError, ValueError, ssl.SSLError):
        return None
    return _from_info(info, pem)


def summarise_pem(pem: str) -> list[dict]:
    """Every certificate in a PEM bundle, including a pasted leaf."""
    out = []
    for block in pem_blocks(pem):
        cert = decode_one(block)
        if cert:
            out.append(cert)
    return out


@functools.lru_cache(maxsize=1024)
def _decode_der(der: bytes) -> dict | None:
    """One root of the store the verifier uses, decoded once per process: the DER bytes are the
    certificate, so a hit is never stale. Uncached, 193 roots cost 25 ms per summary (measured,
    OpenSSL 3.6.4), and the API makes two summaries per live cluster per read. Callers copy, never mutate."""
    return decode_one(ssl.DER_cert_to_PEM_cert(der))


_BUNDLE_CACHE: dict[str, tuple[tuple[int, int, int], list[dict]]] = {}


def summarise_file(path: str) -> list[dict]:
    """One bundle file's certificates, cached on (inode, mtime_ns, size), the key
    `config._trusted_ca_context` uses: kubelet updates a mounted ConfigMap by swapping the `..data`
    symlink to a new directory (#340), so a changed bundle is a new inode even when its size and
    mtime equal the old one's. The API summarises every live cluster on every read and the poller
    on every cycle, and a 128-block bundle costs 17 ms to decode (measured, Python 3.14.7 /
    OpenSSL 3.6.4). A race between the API thread and the poller costs one redundant decode,
    never a wrong list."""
    try:
        st = os.stat(path)
    except OSError:
        return []
    key = (st.st_ino, st.st_mtime_ns, st.st_size)
    hit = _BUNDLE_CACHE.get(path)
    if hit is not None and hit[0] == key:
        return hit[1]
    try:
        # A PEM block is ASCII; OpenSSL skips whatever lies between blocks, so a comment in another
        # encoding must not hide the certificates the verifier loads from this file.
        certs = summarise_pem(Path(path).read_text(errors="replace"))
    except (OSError, UnicodeDecodeError, ValueError):
        return []  # never cache a failure: a later readable file must be retried
    _BUNDLE_CACHE[path] = (key, certs)
    return certs


def summarise_paths(paths: list[str]) -> list[dict]:
    out, seen = [], set()
    for path in paths:
        for cert in summarise_file(path):
            if cert["sha256"] in seen:
                continue
            seen.add(cert["sha256"])
            out.append(cert)
    return out


def trusted_paths() -> list[str]:
    paths = []
    for part in os.environ.get("GSD_TRUSTED_CA_FILE", "").split(":"):
        path = part.strip()
        if path and Path(path).is_file():
            paths.append(path)
    return paths


def match_enterprise(cert: dict, sha256: str, subject: str) -> bool:
    want = normalise_sha256(sha256)
    if want:
        return normalise_sha256(cert.get("sha256") or "") == want
    if subject:
        got = cert.get("subject") or ""
        return got == subject or got.endswith(subject)
    return False


def validity_word(not_before: str, not_after: str, now: datetime, warn_days: int) -> str:
    start = datetime.fromisoformat(not_before.replace("Z", "+00:00"))
    end = datetime.fromisoformat(not_after.replace("Z", "+00:00"))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    if now < start:
        return NOT_YET
    if now > end:
        return EXPIRED
    if (end - now).total_seconds() <= warn_days * 86400:
        return EXPIRING
    return VALID


def tls_verify_failure(cluster: ClusterConfig) -> tuple[str, str]:
    """The one (action, store) pair for a cert-verify-failed line and the card."""
    mode = cluster.tls_mode
    if mode["ca"] == "caData":
        secret = cluster.source.split(":", 1)[-1]
        action = (f"this cluster pins its own CA: replace tlsClientConfig.caData in Secret "
                  f"{secret} with the CA that signs its API server")
        store = f"secret:{secret}/tlsClientConfig.caData"
    elif mode["ca"] == "trusted-bundle":
        action = ("add the CA to the chart's trustedCA.existingConfigMap (fleet-wide), or set "
                  "tlsClientConfig.caData on this cluster's Secret (this cluster only)")
        store = os.environ.get("GSD_TRUSTED_CA_FILE") or "the system trust store"
    else:
        action = (f"the CA comes from {mode['ca']}: point it at the CA that signs this "
                  f"cluster's API server")
        store = cluster.ca_bundle_file or mode["ca"]
    return action, store


def store_of(cluster: ClusterConfig) -> tuple[str, str]:
    """(store label, sourceKind). Kind is a fact, never a security distinction."""
    mode = cluster.tls_mode
    if mode["insecure"]:
        return "insecure", "none"
    if mode["ca"] == "caData":
        secret = cluster.source.split(":", 1)[-1]
        return f"secret:{secret}/tlsClientConfig.caData", "secret"
    if mode["ca"] == "serviceAccount":
        return SA_CA_PATH, "file"
    if mode["ca"] == "caBundleFile":
        return cluster.ca_bundle_file or "caBundleFile", "file"
    if trusted_paths():
        return os.environ.get("GSD_TRUSTED_CA_FILE") or "the trusted bundle", "configmap"
    return "the system trust store", "system"


def annotate(certs: list[dict], settings: Settings, now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    pinned = bool(settings.enterprise_ca_sha256 or settings.enterprise_ca_subject)
    out = []
    for cert in certs:
        row = dict(cert)
        row["enterpriseRoot"] = (match_enterprise(row, settings.enterprise_ca_sha256,
                                                  settings.enterprise_ca_subject) if pinned else None)
        row["validity"] = validity_word(row["notBefore"], row["notAfter"], now,
                                        settings.ca_expiry_warning_days)
        out.append(row)
    return out


def summarise_cluster(cluster: ClusterConfig, settings: Settings,
                      now: datetime | None = None) -> dict:
    now = now or datetime.now(timezone.utc)
    store, kind = store_of(cluster)
    mode = cluster.tls_mode
    if mode["insecure"]:
        return {"store": store, "sourceKind": kind, "count": 0, "enterpriseRoot": None,
                "certificates": []}
    if cluster.ca_data:
        certs = summarise_pem(cluster.ca_data)
    elif cluster.ca_bundle_file:
        certs = summarise_paths([cluster.ca_bundle_file])
    else:
        # The store verify() hands httpx (kube.py#ClusterClient._client): every mounted path loaded
        # over OpenSSL's default store (config._trusted_ca_context), or, with none mounted, `True`,
        # which httpx turns into its own default: certifi's bundle unless SSL_CERT_FILE or
        # SSL_CERT_DIR is set. Count and pin against that store, each root fingerprinted from its DER.
        paths = trusted_paths()
        context = ssl.create_default_context() if paths else httpx.create_ssl_context()
        by_digest = {}
        for der in context.get_ca_certs(binary_form=True):
            cert = _decode_der(der)
            if cert:
                by_digest[cert["sha256"]] = cert
        for cert in summarise_paths(paths):
            by_digest[cert["sha256"]] = cert
        certs = list(by_digest.values())
    shown = annotate(certs, settings, now)
    pinned = bool(settings.enterprise_ca_sha256 or settings.enterprise_ca_subject)
    enterprise = any(c["enterpriseRoot"] for c in shown) if pinned else None
    if mode["ca"] == "trusted-bundle":
        listed = [c for c in shown if c["enterpriseRoot"]] if pinned else []
    else:
        listed = shown
    return {"store": store, "sourceKind": kind, "count": len(shown),
            "enterpriseRoot": enterprise, "certificates": listed}
