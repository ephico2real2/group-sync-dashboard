"""Clusters declared as labelled Secrets, discovered by the app (docs/specs/SPEC_S1_cluster_secrets.md, #230).

The model is Argo CD's: a Secret in the pod's own namespace carrying one label is a cluster; the label
is the only thing discovery selects on, the Secret's name is a convention for people, and the cluster's
id is the `name` in its data. What differs from Argo is stated in the spec's notes: the host cluster is
never sourced from a Secret (the reader tier rests on its identity), and a bad Secret is a finding on
the tab, never an error that stops the others.
"""

from __future__ import annotations

SECRET_TYPE_LABEL = "groupsync-dashboard.io/secret-type"
SECRET_TYPE_CLUSTER = "cluster"
LABEL_SELECTOR = f"{SECRET_TYPE_LABEL}={SECRET_TYPE_CLUSTER}"

# The closed set of finding codes — the tab renders each with its own sentence, so a new code is a
# page change too (SPEC_S1 §S1.2).
FINDING_CODES = (
    "name-missing", "name-invalid", "server-missing", "server-invalid",
    "config-missing", "config-not-json", "unsupported-config-key",
    "credential-missing", "credential-ambiguous", "ca-data-invalid", "insecure-with-ca",
    "visibility-invalid", "identity-invalid", "enabled-invalid",
    "host-cluster-not-from-secret", "duplicate-cluster-name", "shadows-values-entry",
    "oauth-exchange-not-built", "discovery-failed",
)

from .parser import Finding, parse_secret  # noqa: E402
from .registry import ClusterRegistry  # noqa: E402
from .reader import discover  # noqa: E402

__all__ = ["SECRET_TYPE_LABEL", "SECRET_TYPE_CLUSTER", "LABEL_SELECTOR", "FINDING_CODES",
           "Finding", "parse_secret", "ClusterRegistry", "discover"]
