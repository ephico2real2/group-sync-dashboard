#!/usr/bin/env bash
# #447's throwaway cluster Secret, in the shape of the 2026-09-27 walk-authfail entry: a bearer token no server ever
# issued, so the API answers 401, Refresh answers auth_failed, and the card offers Rejoin.
#   secret-447.sh apply    build gsd-cluster-walk-447 in a 0600 mktemp file and `oc apply -f` it; the exit trap removes it
#   secret-447.sh delete   delete it by the run label
# The token is `sha256~` + 44 random hex characters, generated here and never printed. `tlsClientConfig` is copied
# read-only from gsd-cluster-shared-qa (jq selects that one field, never the token beside it). The Secret carries no
# annotation and its config only `bearerToken` and `tlsClientConfig`: no saTokenLookup, no userSelfLogin, no
# ldapConnectionBootstrap, no token-source or lookup-account, and no password of any kind.
set -euo pipefail
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=batch-1110-447-2026-09-28
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"

case "${1:?apply|delete}" in
  apply)
    tls=$(oc get secrets -n "${ns}" gsd-cluster-shared-qa -o json | jq -c '.data.config | @base64d | fromjson | .tlsClientConfig')
    umask 077
    manifest=$(mktemp); trap 'rm -f "${manifest}"' EXIT
    jq -n --arg token "sha256~$(openssl rand -hex 22)" --argjson tls "${tls}" '{
      apiVersion: "v1", kind: "Secret", type: "Opaque",
      metadata: {name: "gsd-cluster-walk-447", namespace: "group-sync-dashboard",
                 labels: {"groupsync-dashboard.io/secret-type": "cluster", "walk.gsd.lab/run": "batch-1110-447-2026-09-28"}},
      stringData: {name: "walk-447", server: "https://api.crc.testing:6443",
                   config: ({bearerToken: $token, tlsClientConfig: $tls} | tojson)}}' > "${manifest}"
    echo "# manifest mode: $(stat -f %Lp "${manifest}")"
    echo "# tlsClientConfig copied from gsd-cluster-shared-qa: ${tls}"
    oc apply -f "${manifest}"
    ;;
  delete)
    oc delete secrets -n "${ns}" -l "${run_label}"
    ;;
  *) echo "usage: secret-447.sh apply|delete" >&2; exit 2 ;;
esac
