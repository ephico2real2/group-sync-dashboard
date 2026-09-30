#!/usr/bin/env bash
# The walk's throwaway CA and throwaway cluster Secret (cut down from reports/2026-09-29_ca-244-walk/scripts/secrets.sh).
#   secrets.sh ca       one self-signed CA in $GSD_WALK_TMP (outside the repo), and its public summary on stdout:
#                         wrong-ca.pem  `/CN=walk-492 wrong CA`, 365 days (it did not sign mock-privateca's server)
#   secrets.sh create   gsd-cluster-w492-fail (name w492-fail, caData = wrong-ca.pem, mock-privateca's server URL)
#   secrets.sh delete   delete it by the run label
# The bearer token is `sha256~` + 44 random hex characters, generated here, never printed, and kept only in
# $GSD_WALK_TMP/tokens (mode 0600) so the pod log and the folder can be searched for it; that directory is deleted at
# the end. config holds only `bearerToken` and `tlsClientConfig.caData`: no saTokenLookup, no userSelfLogin, no
# ldapConnectionBootstrap, no password of any kind, so nothing binds as the fleet account. The TLS handshake fails
# before any request is sent, so the token never leaves the pod. `oc create` writes no last-applied annotation.
set -euo pipefail
ns=group-sync-dashboard
run=chip-492-2026-09-30
tmp="${GSD_WALK_TMP:?GSD_WALK_TMP must name the walk temp directory outside the repo}"
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"

case "${1:?ca|create|delete}" in
  ca)
    umask 077
    openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=walk-492 wrong CA" \
      -keyout "${tmp}/wrong-ca.key" -out "${tmp}/wrong-ca.pem" 2>/dev/null
    echo "# openssl x509 -in <tmp>/wrong-ca.pem -noout -subject -issuer -dates -fingerprint -sha256 -ext basicConstraints -nameopt RFC2253"
    openssl x509 -in "${tmp}/wrong-ca.pem" -noout -subject -issuer -dates -fingerprint -sha256 -ext basicConstraints -nameopt RFC2253
    ;;
  create)
    server=$(oc get secrets -n "${ns}" gsd-cluster-mock-privateca -o json | jq -r '.data.server | @base64d')
    echo "# server copied from gsd-cluster-mock-privateca: ${server}"
    umask 077
    token="sha256~$(openssl rand -hex 22)"
    printf '%s\n' "${token}" >> "${tmp}/tokens"
    manifest=$(mktemp "${tmp}/manifest.XXXXXX"); trap 'rm -f "${manifest}"' EXIT
    jq -n --arg token "${token}" --arg ca "$(base64 < "${tmp}/wrong-ca.pem" | tr -d '\n')" --arg server "${server}" \
          --arg run "${run}" '{
      apiVersion: "v1", kind: "Secret", type: "Opaque",
      metadata: {name: "gsd-cluster-w492-fail", namespace: "group-sync-dashboard",
                 labels: {"groupsync-dashboard.io/secret-type": "cluster", "walk.gsd.lab/run": $run}},
      stringData: {name: "w492-fail", server: $server, visibility: "inherit", identity: "none",
                   config: ({bearerToken: $token, tlsClientConfig: {caData: $ca}} | tojson)}}' > "${manifest}"
    echo "# manifest mode: $(stat -f %Lp "${manifest}"); tokens file mode: $(stat -f %Lp "${tmp}/tokens")"
    oc create -f "${manifest}"
    ;;
  delete)
    oc delete secrets -n "${ns}" -l "walk.gsd.lab/run=${run}"
    ;;
  *) echo "usage: secrets.sh ca|create|delete" >&2; exit 2 ;;
esac
