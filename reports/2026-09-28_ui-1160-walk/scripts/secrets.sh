#!/usr/bin/env bash
# The walk's three throwaway cluster Secrets, in the shape of the #447 walk's `secret-447.sh`
# (`reports/2026-09-28_batch-1110-walk/scripts/secret-447.sh`): a bearer token no server ever issued, so the API
# answers 401, Refresh answers auth_failed, and the card offers Rejoin.
#   gsd-cluster-w462         name w462          } a pair whose ids collided under the old `cc-<kind>-<id>` scheme (#462):
#   gsd-cluster-result-w462  name result-w462   } `cc-rejoin-result-w462` was both w462's result line and this button
#   gsd-cluster-constructor  name constructor     a name Object's prototype answers on `{}` (#459)
#   secrets.sh create   build the three in one 0600 mktemp manifest and `oc create -f` it; the exit trap removes it
#   secrets.sh delete   delete them by the run label
# Each token is `sha256~` + 44 random hex characters, generated here and never printed. `tlsClientConfig` is copied
# read-only from gsd-cluster-shared-qa (jq selects that one field, never the token beside it). No annotation; config
# holds only `bearerToken` and `tlsClientConfig`: no saTokenLookup, no userSelfLogin, no ldapConnectionBootstrap, no
# token-source or lookup-account, and no password of any kind. `oc create` writes no last-applied annotation.
set -euo pipefail
ns=group-sync-dashboard
run=ui-1160-2026-09-28
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"

secret() {  # $1 = the cluster name; the Secret is gsd-cluster-$1
  jq -n --arg name "$1" --arg token "sha256~$(openssl rand -hex 22)" --argjson tls "${tls}" --arg run "${run}" '{
    apiVersion: "v1", kind: "Secret", type: "Opaque",
    metadata: {name: ("gsd-cluster-" + $name), namespace: "group-sync-dashboard",
               labels: {"groupsync-dashboard.io/secret-type": "cluster", "walk.gsd.lab/run": $run}},
    stringData: {name: $name, server: "https://api.crc.testing:6443",
                 config: ({bearerToken: $token, tlsClientConfig: $tls} | tojson)}}'
}

case "${1:?create|delete}" in
  create)
    tls=$(oc get secrets -n "${ns}" gsd-cluster-shared-qa -o json | jq -c '.data.config | @base64d | fromjson | .tlsClientConfig')
    umask 077
    manifest=$(mktemp); trap 'rm -f "${manifest}"' EXIT
    { secret w462; secret result-w462; secret constructor; } | jq -s '{apiVersion: "v1", kind: "List", items: .}' > "${manifest}"
    echo "# manifest mode: $(stat -f %Lp "${manifest}")"
    echo "# tlsClientConfig copied from gsd-cluster-shared-qa: ${tls}"
    oc create -f "${manifest}"
    ;;
  delete)
    oc delete secrets -n "${ns}" -l "walk.gsd.lab/run=${run}"
    ;;
  *) echo "usage: secrets.sh create|delete" >&2; exit 2 ;;
esac
