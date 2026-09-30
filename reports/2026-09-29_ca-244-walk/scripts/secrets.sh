#!/usr/bin/env bash
# The walk's two throwaway CAs and two throwaway cluster Secrets (after
# reports/2026-09-28_ui-1160-walk/scripts/secrets.sh).
#   secrets.sh cas      two self-signed CAs in $GSD_WALK_TMP (outside the repo), and their public summary on stdout:
#                         wrong-ca.pem     `/CN=walk-244 wrong CA`, 365 days  (C: it did not sign mock-privateca's server)
#                         expiring-ca.pem  `/CN=walk-244 expiring CA`, 10 days (D: inside the 30-day window)
#   secrets.sh create   gsd-cluster-w244-fail (name w244-fail, caData = wrong-ca.pem) and gsd-cluster-w244-exp
#                       (name w244-exp, caData = expiring-ca.pem), both with mock-privateca's server URL
#   secrets.sh delete   delete them by the run label
# Each bearer token is `sha256~` + 44 random hex characters, generated here, never printed, and kept only in
# $GSD_WALK_TMP/tokens (mode 0600) so the pod log can be searched for it; that directory is deleted at the end.
# config holds only `bearerToken` and `tlsClientConfig.caData`: no saTokenLookup, no userSelfLogin, no
# ldapConnectionBootstrap, no password of any kind, so nothing binds as the fleet account. The TLS handshake fails
# before any request is sent, so the token never leaves the pod. `oc create` writes no last-applied annotation.
set -euo pipefail
ns=group-sync-dashboard
run=ca-244-2026-09-29
tmp="${GSD_WALK_TMP:?GSD_WALK_TMP must name the walk temp directory outside the repo}"
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"

secret() {  # $1 = the cluster name, $2 = the CA PEM file; the Secret is gsd-cluster-$1
  local token; token="sha256~$(openssl rand -hex 22)"
  printf '%s\n' "${token}" >> "${tmp}/tokens"
  jq -n --arg name "$1" --arg token "${token}" --arg ca "$(base64 < "$2" | tr -d '\n')" --arg server "${server}" --arg run "${run}" '{
    apiVersion: "v1", kind: "Secret", type: "Opaque",
    metadata: {name: ("gsd-cluster-" + $name), namespace: "group-sync-dashboard",
               labels: {"groupsync-dashboard.io/secret-type": "cluster", "walk.gsd.lab/run": $run}},
    stringData: {name: $name, server: $server, visibility: "inherit", identity: "none",
                 config: ({bearerToken: $token, tlsClientConfig: {caData: $ca}} | tojson)}}'
}

case "${1:?cas|create|delete}" in
  cas)
    umask 077
    openssl req -x509 -newkey rsa:2048 -nodes -days 365 -subj "/CN=walk-244 wrong CA" \
      -keyout "${tmp}/wrong-ca.key" -out "${tmp}/wrong-ca.pem" 2>/dev/null
    openssl req -x509 -newkey rsa:2048 -nodes -days 10 -subj "/CN=walk-244 expiring CA" \
      -keyout "${tmp}/expiring-ca.key" -out "${tmp}/expiring-ca.pem" 2>/dev/null
    for f in wrong-ca expiring-ca; do
      echo "# openssl x509 -in <tmp>/${f}.pem -noout -subject -issuer -dates -fingerprint -sha256 -ext basicConstraints -nameopt RFC2253"
      openssl x509 -in "${tmp}/${f}.pem" -noout -subject -issuer -dates -fingerprint -sha256 -ext basicConstraints -nameopt RFC2253
    done
    ;;
  create)
    server=$(oc get secrets -n "${ns}" gsd-cluster-mock-privateca -o json | jq -r '.data.server | @base64d')
    echo "# server copied from gsd-cluster-mock-privateca: ${server}"
    umask 077
    manifest=$(mktemp "${tmp}/manifest.XXXXXX"); trap 'rm -f "${manifest}"' EXIT
    { secret w244-fail "${tmp}/wrong-ca.pem"; secret w244-exp "${tmp}/expiring-ca.pem"; } \
      | jq -s '{apiVersion: "v1", kind: "List", items: .}' > "${manifest}"
    echo "# manifest mode: $(stat -f %Lp "${manifest}"); tokens file mode: $(stat -f %Lp "${tmp}/tokens")"
    oc create -f "${manifest}"
    ;;
  delete)
    oc delete secrets -n "${ns}" -l "walk.gsd.lab/run=${run}"
    ;;
  *) echo "usage: secrets.sh cas|create|delete" >&2; exit 2 ;;
esac
