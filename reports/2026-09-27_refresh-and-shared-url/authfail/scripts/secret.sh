#!/usr/bin/env bash
# The throwaway cluster Secret the addendum refreshes: a bearer token no server ever issued, so the API answers 401.
#   secret.sh apply    build gsd-cluster-walk-authfail in a mktemp file and `oc apply -f` it; the file is removed on exit
#   secret.sh delete   delete it by the walk's label
# The token is `sha256~` + 44 random hex characters, generated here and never printed. `tlsClientConfig` is copied
# from gsd-cluster-shared-qa (read only; jq selects that one field, never the token beside it), so TLS verifies the
# same way and the only thing wrong is the token. No password of any kind is in the Secret.
set -euo pipefail
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=authfail-2026-09-27
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"

case "${1:?apply|delete}" in
  apply)
    tls=$(oc get secrets -n "${ns}" gsd-cluster-shared-qa -o json | jq -c '.data.config | @base64d | fromjson | .tlsClientConfig')
    manifest=$(mktemp); trap 'rm -f "${manifest}"' EXIT
    jq -n --arg token "sha256~$(openssl rand -hex 22)" --argjson tls "${tls}" '{
      apiVersion: "v1", kind: "Secret", type: "Opaque",
      metadata: {name: "gsd-cluster-walk-authfail", namespace: "group-sync-dashboard",
                 labels: {"groupsync-dashboard.io/secret-type": "cluster", "walk.gsd.lab/run": "authfail-2026-09-27"}},
      stringData: {name: "walk-authfail", server: "https://api.crc.testing:6443",
                   config: ({bearerToken: $token, tlsClientConfig: $tls} | tojson)}}' > "${manifest}"
    echo "# tlsClientConfig copied from gsd-cluster-shared-qa: ${tls}"
    oc apply -f "${manifest}"
    ;;
  delete)
    oc delete secrets -n "${ns}" -l "${run_label}"
    ;;
  *) echo "usage: secret.sh apply|delete" >&2; exit 2 ;;
esac
