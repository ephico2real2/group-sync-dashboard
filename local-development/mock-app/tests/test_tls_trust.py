"""The three verify() trust modes (DESIGN §4) plus the negative control, over real TLS."""

from __future__ import annotations

import os

import pytest

from gsd.kube import UNREACHABLE, ClusterClient, ClusterError


def test_mode2_ca_bundle_file(mock_cluster):
    """Mode 2: the ephemeral CA handed over as caBundleFile verifies the corporate-signed leaf."""
    client = ClusterClient(mock_cluster.cluster_config(), timeout=5.0)
    _, groups = client.fetch()
    assert groups                                       # a full verified poll completes


def test_mode3_trusted_ca_env(mock_cluster):
    """Mode 3: the injected/enterprise fallback via GSD_TRUSTED_CA_FILE (ca_bundle_file=None)."""
    import gsd.config as gsd_config

    with gsd_config._ca_cache_lock:  # §4.3 stale-context guard
        gsd_config._ca_cache.clear()
    os.environ["GSD_TRUSTED_CA_FILE"] = mock_cluster.ca_file
    try:
        cfg = mock_cluster.cluster_config(use_trusted_ca_env=True, ca_bundle=None)
        client = ClusterClient(cfg, timeout=5.0)
        _, groups = client.fetch()
        assert groups
    finally:
        os.environ.pop("GSD_TRUSTED_CA_FILE", None)
        with gsd_config._ca_cache_lock:
            gsd_config._ca_cache.clear()


def test_negative_control_no_ca_is_unreachable(mock_cluster):
    """No CA anywhere → system trust → the corporate leaf fails → UNREACHABLE (the outage the
    fallback exists to fix)."""
    import gsd.config as gsd_config

    with gsd_config._ca_cache_lock:
        gsd_config._ca_cache.clear()
    os.environ.pop("GSD_TRUSTED_CA_FILE", None)
    cfg = mock_cluster.cluster_config(ca_bundle=None)
    client = ClusterClient(cfg, timeout=5.0)
    with pytest.raises(ClusterError) as exc:
        client.fetch()
    assert exc.value.outcome == UNREACHABLE


def test_insecure_skip_verify_reachable(mock_cluster):
    """The escape hatch: verify=False makes the same server reachable with no CA."""
    cfg = mock_cluster.cluster_config(insecure=True)
    client = ClusterClient(cfg, timeout=5.0)
    _, groups = client.fetch()
    assert groups


def test_generated_leaf_survives_a_long_running_form_b():
    # review #118 C1: a 1-day leaf failed a >24h Form B lab or a >1h-behind runner clock.
    import datetime as dt
    from cryptography import x509
    from mock_app.tls import default_sans, generate_ca_and_leaf
    now = dt.datetime.now(dt.timezone.utc)
    pair = generate_ca_and_leaf(default_sans("0.0.0.0"))
    leaf = x509.load_pem_x509_certificate(pair.leaf_cert_pem)
    assert leaf.not_valid_before_utc <= now - dt.timedelta(hours=23)
    assert leaf.not_valid_after_utc >= now + dt.timedelta(days=29, hours=23)
