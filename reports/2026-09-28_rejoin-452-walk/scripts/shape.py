#!/usr/bin/env python3
"""Step 3, hermetic: the walk Secret's shape through the application's own parser, under three token-sources.
A dummy token of the same form stands in for the walk's random one. Run with PYTHONPATH=<a tree>/local-development."""
import base64, json, os
import gsd
from gsd.clusterconfig.parser import Finding, parse_secret
from gsd.config import CREDENTIAL_LOOKUP, CREDENTIAL_SELF_LOGIN

b64 = lambda s: base64.b64encode(s.encode()).decode()
config = {"bearerToken": "sha256~" + "0" * 44, "tlsClientConfig": {"insecure": False},
          "ldapConnectionBootstrap": "walk-bootstrap-452"}


def secret(token_source: str | None) -> dict:
    annotations = {"groupsync-dashboard.io/token-source": token_source} if token_source else {}
    return {"metadata": {"name": "gsd-cluster-walk-452", "annotations": annotations,
                         "labels": {"groupsync-dashboard.io/secret-type": "cluster", "walk.gsd.lab/run": "walk-452-2026-09-28"}},
            "data": {"name": b64("walk-452"), "server": b64("https://api.crc.testing:6443"), "config": b64(json.dumps(config))}}


print(f"# gsd {gsd.__version__}; lookup kind {CREDENTIAL_LOOKUP!r}, self-login kind {CREDENTIAL_SELF_LOGIN!r}")
for source in ("remote-lookup", "rejoin", None):
    p = parse_secret(secret(source), host_name="dashboard")
    if isinstance(p, Finding):
        print(f"token-source={source!s:14} -> finding {p.code}: {p.detail}")
    else:
        print(f"token-source={source!s:14} -> loads: credential_kind={p.credential_kind!r} connection_mode={p.connection_mode!r} "
              f"credential_pending={p.credential_pending!r} lookup_account={p.lookup_account!r} "
              f"ldap_connection_bootstrap={p.ldap_connection_bootstrap!r}")
