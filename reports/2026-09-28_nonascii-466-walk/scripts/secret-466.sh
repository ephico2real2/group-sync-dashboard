#!/usr/bin/env bash
# #466's throwaway cluster Secret, in the shape of ../../2026-09-28_batch-1110-walk/scripts/secret-447.sh: a bearer
# token no server ever issued, and a tlsClientConfig.caData whose text holds a non-ASCII character outside the PEM
# block, so the parser refuses it as `ca-data-invalid` (1.12.0) instead of raising TypeError (before 1.12.0).
#   secret-466.sh check    build the manifest and run THIS checkout's parser on it, hermetically, printing only the
#                          finding's secret, code and detail; nothing is sent to a cluster
#   secret-466.sh create   build the manifest and `oc create -f` it
#   secret-466.sh delete   delete it by the run label
# The CA is generated here: `openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 30
# -subj /CN=walk-466`. Its key, the certificate and the manifest live only in a 0700 mktemp directory, which the exit
# trap removes; the key is never used again and never committed. caData is the base64 of the text
# `# lab walk #466 — non-breaking space here:` + U+00A0 + a newline + the PEM certificate. The token is `sha256~` + 44
# random hex characters, generated here and never printed. config carries only `bearerToken` and `tlsClientConfig`
# (`caData` alone): no saTokenLookup, no userSelfLogin, no ldapConnectionBootstrap, no insecure, and no annotation.
set -euo pipefail
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=nonascii-466-2026-09-28
here="$(cd "$(dirname "$0")" && pwd)"
repo="$(cd "${here}/../../.." && pwd)"

build() {  # writes the manifest to $1; the CA's key and certificate stay in the same private directory
  local dir="$1"
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 -nodes -days 30 -subj /CN=walk-466 \
    -keyout "${dir}/ca.key" -out "${dir}/ca.pem" 2>/dev/null
  local ca_data
  ca_data=$(python3 -c 'import base64, sys
text = "# lab walk #466 — non-breaking space here: \n" + open(sys.argv[1], encoding="ascii").read()
print(base64.b64encode(text.encode("utf-8")).decode("ascii"))' "${dir}/ca.pem")
  jq -n --arg token "sha256~$(openssl rand -hex 22)" --arg ca "${ca_data}" --arg ns "${ns}" '{
    apiVersion: "v1", kind: "Secret", type: "Opaque",
    metadata: {name: "gsd-cluster-walk-466", namespace: $ns,
               labels: {"groupsync-dashboard.io/secret-type": "cluster", "walk.gsd.lab/run": "nonascii-466-2026-09-28"}},
    stringData: {name: "walk-466", server: "https://api.crc.testing:6443",
                 config: ({bearerToken: $token, tlsClientConfig: {caData: $ca}} | tojson)}}' > "${dir}/manifest.json"
  echo "# manifest mode: $(stat -f %Lp "${dir}/manifest.json"), directory mode: $(stat -f %Lp "${dir}")"
  echo "# CA: $(openssl x509 -in "${dir}/ca.pem" -noout -subject -enddate | tr '\n' ' ')"
}

case "${1:?check|create|delete}" in
  check|create)
    umask 077
    dir=$(mktemp -d); trap 'rm -rf "${dir}"' EXIT
    build "${dir}"
    if [[ "$1" == check ]]; then
      PYTHONPATH="${repo}/local-development" "${GSD_VENV_PYTHON:?GSD_VENV_PYTHON names the venv python}" \
        -c 'import json, os, sys, gsd
print("# gsd imported from <this checkout>/" + os.path.relpath(gsd.__file__, sys.argv[2]), "version", gsd.__version__)
from gsd.clusterconfig.parser import parse_secret, Finding
r = parse_secret(json.load(open(sys.argv[1])), host_name="host")
print("# parse_secret:", {"secret": r.secret, "code": r.code, "detail": r.detail} if isinstance(r, Finding) else type(r).__name__)' \
        "${dir}/manifest.json" "${repo}"
    else
      : "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
      oc create -f "${dir}/manifest.json"
    fi
    ;;
  delete)
    : "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
    oc delete secrets -n "${ns}" -l "${run_label}"
    ;;
  *) echo "usage: secret-466.sh check|create|delete" >&2; exit 2 ;;
esac
