#!/bin/sh
# Container entrypoint (DESIGN §8.2): generate/load a CA, then exec the mock on :6443.
#
# Env knobs (all defaulted in the Containerfile):
#   MOCK_FIXTURE  path to the fixture YAML                 (default /fixtures/reference.yaml)
#   MOCK_HOST     bind address                             (default 0.0.0.0)
#   MOCK_PORT     bind port                                (default 6443)
#   MOCK_CA_OUT   write the generated CA cert here         (default /out/ca.crt)
#   MOCK_CA_IN    load a persistent ca.crt/tls.crt/tls.key from this dir (optional)
#   MOCK_SANS     comma-separated SANs for the leaf cert
set -eu

ARGS="--fixture ${MOCK_FIXTURE} --host ${MOCK_HOST} --port ${MOCK_PORT} --tls"

if [ -n "${MOCK_SANS:-}" ]; then
  ARGS="${ARGS} --sans ${MOCK_SANS}"
fi

if [ -n "${MOCK_CA_IN:-}" ]; then
  # Persistent CA mounted in — stable across restarts.
  ARGS="${ARGS} --ca-in ${MOCK_CA_IN}"
else
  ARGS="${ARGS} --ca-out ${MOCK_CA_OUT}"
fi

echo "starting mock-openshift: python -m mock_app ${ARGS}" >&2
exec python -m mock_app ${ARGS}
