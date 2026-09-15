"""``python -m mock_app`` — the container / lab entrypoint (form B, DESIGN §8.2).

    python -m mock_app --fixture /fixtures/reference.yaml \
        --host 0.0.0.0 --port 6443 --tls \
        --ca-out /out/ca.crt [--ca-in /certs] [--sans DNS:mock-openshift,IP:10.0.0.5]

On start it EITHER loads a pre-generated CA+leaf from ``--ca-in`` (stable across restarts, for a
persistent lab) OR generates an ephemeral one and writes the CA cert to ``--ca-out`` so the
dashboard can mount it as ``caBundleFile``. Port 6443 mirrors a real API server so ``oc login`` /
a browser / the e2e-walk can poke it.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .fixture import Fixture
from .server import MockClusterServer
from .tls import CaLeaf, default_sans, generate_ca_and_leaf


def _parse_sans(raw: str | None, host: str) -> list[str]:
    if not raw:
        return default_sans(host)
    return [s.strip() for s in raw.split(",") if s.strip()]


def _load_ca_in(directory: str) -> CaLeaf:
    """Load a persistent CA+leaf from a directory holding ca.crt, tls.crt, tls.key."""
    base = Path(directory)
    ca = (base / "ca.crt").read_bytes()
    leaf = (base / "tls.crt").read_bytes()
    key = (base / "tls.key").read_bytes()
    return CaLeaf(ca_pem=ca, leaf_cert_pem=leaf, leaf_key_pem=key)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="mock_app", description=__doc__)
    parser.add_argument("--fixture", required=True, help="path to the fixture YAML/JSON")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=6443)
    parser.add_argument("--tls", dest="tls", action="store_true", default=True)
    parser.add_argument("--no-tls", dest="tls", action="store_false")
    parser.add_argument("--ca-out", default=None,
                        help="write the (generated) CA cert here for the dashboard to trust")
    parser.add_argument("--ca-in", default=None,
                        help="load a persistent ca.crt/tls.crt/tls.key from this directory")
    parser.add_argument("--sans", default=None,
                        help="comma-separated SANs, e.g. 'DNS:mock-openshift,IP:10.0.0.5'")
    parser.add_argument("--log-level", default="info")
    args = parser.parse_args(argv)

    fixture = Fixture.from_yaml(args.fixture)
    sans = _parse_sans(args.sans, args.host)

    ca_leaf: CaLeaf | None = None
    if args.tls:
        if args.ca_in:
            ca_leaf = _load_ca_in(args.ca_in)
        else:
            ca_leaf = generate_ca_and_leaf(sans)
            if args.ca_out:
                out = Path(args.ca_out)
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(ca_leaf.ca_pem)
                print(f"wrote CA cert to {out}", file=sys.stderr)

    server = MockClusterServer(
        fixture, host=args.host, port=args.port, tls=args.tls,
        sans=sans, ca_leaf=ca_leaf, log_level=args.log_level,
    )
    server.start()
    print(f"mock-openshift serving {fixture.cluster_name} at {server.base_url} "
          f"(fixture: {args.fixture})", file=sys.stderr)
    try:
        # Block forever; the daemon serve-thread does the work.
        server._thread.join()  # noqa: SLF001 - intentional block on the serve thread
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
