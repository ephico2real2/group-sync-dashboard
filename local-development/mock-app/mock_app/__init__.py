"""gsd-mock — a fixture-driven mock of the OpenShift API surface group-sync-dashboard reads.

Stands up exactly the request surface ``gsd/kube.py`` issues (the ~16 read endpoints, the two
node-log-proxy shapes and the SubjectAccessReview POST) from a declarative
YAML fixture, over real TLS on an ephemeral CA. See the DESIGN doc and README for the contract.
"""

from __future__ import annotations

from .fixture import Fixture, FixtureError, load_fixture
from .sar import SarAuthorizer
from .server import MockClusterServer
from .tls import CaLeaf, generate_ca_and_leaf

__version__ = "0.1.0"

__all__ = [
    "Fixture",
    "FixtureError",
    "load_fixture",
    "MockClusterServer",
    "SarAuthorizer",
    "CaLeaf",
    "generate_ca_and_leaf",
    "__version__",
]
