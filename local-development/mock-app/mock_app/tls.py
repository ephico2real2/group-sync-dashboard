"""Ephemeral CA + serving certificate for the mock, generated with `cryptography`.

The whole point of a TLS mock (over ``httpx.MockTransport``) is to drive the *real* trust
path in ``gsd.config.ClusterConfig.verify()`` — ``ssl.create_default_context(cafile=…)`` with
``CERT_REQUIRED`` and hostname checking ON (config.py:161-197). So the leaf we serve MUST:

* chain to a CA whose PEM we hand the dashboard as ``caBundleFile`` (mode 2) or via
  ``GSD_TRUSTED_CA_FILE`` (mode 3);
* carry a SubjectAltName that matches the host in ``api_url`` — ``IP:127.0.0.1`` for the
  in-process form, ``DNS:mock-openshift`` for the container form.

Nothing here is cached or reused across servers: each :class:`MockClusterServer` gets a fresh
CA so the trust path is reproducible on any machine with no pre-provisioned root (DESIGN §4.4).
"""

from __future__ import annotations

import datetime as _dt
import ipaddress
from typing import NamedTuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID


class CaLeaf(NamedTuple):
    """A freshly minted CA and the leaf it signed.

    ``ca_pem`` is what the dashboard trusts (``caBundleFile``); ``leaf_cert_pem`` +
    ``leaf_key_pem`` are what the server presents.
    """

    ca_pem: bytes
    leaf_cert_pem: bytes
    leaf_key_pem: bytes


def _san_entry(spec: str) -> x509.GeneralName:
    """Turn a ``"IP:127.0.0.1"`` / ``"DNS:localhost"`` spec into an x509 GeneralName."""
    kind, _, value = spec.partition(":")
    kind = kind.strip().upper()
    value = value.strip()
    if kind == "IP":
        return x509.IPAddress(ipaddress.ip_address(value))
    if kind == "DNS":
        return x509.DNSName(value)
    raise ValueError(f"unsupported SAN spec {spec!r} (use 'IP:<addr>' or 'DNS:<name>')")


def generate_ca_and_leaf(sans: list[str]) -> CaLeaf:
    """Generate a self-signed CA and a ``serverAuth`` leaf carrying ``sans``.

    ``sans`` e.g. ``["IP:127.0.0.1", "DNS:localhost", "DNS:mock-openshift"]``. RSA-2048 keys
    (broadly compatible with every OpenSSL/Python build), valid from one hour ago (clock skew)
    to one day out — long enough for any test run or lab session, short enough that a leaked
    key is worthless tomorrow.
    """
    if not sans:
        raise ValueError("at least one SAN is required so hostname verification can pass")

    now = _dt.datetime.now(_dt.timezone.utc)
    not_before = now - _dt.timedelta(days=1)      # backdate a day: tolerate a runner clock behind
    not_after = now + _dt.timedelta(days=30)      # 30 days: survive a long-running Form B lab

    # ── CA ────────────────────────────────────────────────────────────────────────────────
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "mock-openshift-ca")])
    ca_cert = (
        x509.CertificateBuilder()
        .subject_name(ca_name)
        .issuer_name(ca_name)
        .public_key(ca_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_cert_sign=True, crl_sign=True,
                content_commitment=False, key_encipherment=False, data_encipherment=False,
                key_agreement=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False
        )
        .sign(ca_key, hashes.SHA256())
    )

    # ── Leaf, signed by the CA ──────────────────────────────────────────────────────────────
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    leaf_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "mock-openshift")])
    leaf_cert = (
        x509.CertificateBuilder()
        .subject_name(leaf_name)
        .issuer_name(ca_name)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(not_before)
        .not_valid_after(not_after)
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .add_extension(
            x509.SubjectAlternativeName([_san_entry(s) for s in sans]), critical=False
        )
        .add_extension(
            x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True, key_encipherment=True, content_commitment=False,
                data_encipherment=False, key_agreement=False, key_cert_sign=False,
                crl_sign=False, encipher_only=False, decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
            critical=False,
        )
        .sign(ca_key, hashes.SHA256())
    )

    return CaLeaf(
        ca_pem=ca_cert.public_bytes(serialization.Encoding.PEM),
        leaf_cert_pem=leaf_cert.public_bytes(serialization.Encoding.PEM),
        leaf_key_pem=leaf_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ),
    )


def default_sans(host: str) -> list[str]:
    """Sensible SANs for a server bound to ``host``.

    Always includes loopback (the in-process form reaches it as ``127.0.0.1``) and the
    container service name so an in-cluster caller verifies too.
    """
    sans = ["IP:127.0.0.1", "DNS:localhost", "DNS:mock-openshift"]
    try:
        ipaddress.ip_address(host)
        entry = f"IP:{host}"
    except ValueError:
        entry = f"DNS:{host}"
    if entry not in sans and host not in {"0.0.0.0", "::"}:
        sans.append(entry)
    return sans
