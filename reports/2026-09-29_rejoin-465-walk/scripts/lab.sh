#!/usr/bin/env bash
# The #465 walk's only writes to the lab, each logged to evidence/<file> with its command and instant:
#   lab.sh secret   the throwaway cluster Secret gsd-cluster-w465 (name w465, server https://api.crc.testing:6443): a
#                   random bogus bearer token generated here and never printed, shared-qa's tlsClientConfig copied
#                   read-only, no saTokenLookup, no ldapConnectionBootstrap, no annotation. `oc create` from a 0600
#                   mktemp manifest the exit trap removes, so no last-applied annotation copies the token.
#   lab.sh grant    grant.yaml: ClusterRole gsd-walk-crb-update (update clusterrolebindings) and its binding to developer
#   lab.sh delete   everything carrying the walk's label: the Secret, the ClusterRoleBinding, the ClusterRole
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=rejoin-465-2026-09-29
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
log() { local out="${here}/evidence/$1"; shift; { printf '# %s\n# at %s\n' "$*" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"; "$@" 2>&1; } >> "${out}"; }

case "${1:?secret|grant|delete}" in
  secret)
    umask 077
    manifest=$(mktemp)
    trap 'rm -f "${manifest}"' EXIT
    # shared-qa's tlsClientConfig, read-only: jq keeps that object alone, and its token never leaves the pipe
    tls=$(oc get secrets -n "${ns}" gsd-cluster-shared-qa -o json | jq -c '.data.config | @base64d | fromjson | .tlsClientConfig')
    # The token reaches jq through its environment, never an argument, and is written only to the 0600 manifest
    GSD_WALK_TOKEN="sha256~$(openssl rand -hex 22)" jq -n --argjson tls "${tls}" --arg label "${run_label#*=}" '{
        apiVersion: "v1", kind: "Secret", type: "Opaque",
        metadata: {name: "gsd-cluster-w465", namespace: "group-sync-dashboard",
                   labels: {"groupsync-dashboard.io/secret-type": "cluster", "walk.gsd.lab/run": $label}},
        stringData: {name: "w465", server: "https://api.crc.testing:6443",
                     config: ({bearerToken: env.GSD_WALK_TOKEN, tlsClientConfig: $tls} | tojson)}}' > "${manifest}"
    log secret-create.txt stat -f 'manifest mode %Lp' "${manifest}"
    log secret-create.txt oc create -f "${manifest}"
    f=secret-create
    ;;
  grant)
    log grant-create.txt oc create -f "${here}/scripts/grant.yaml"
    f=grant-create
    ;;
  delete)
    log delete.txt oc delete secrets -n "${ns}" -l "${run_label}" --ignore-not-found
    log delete.txt oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io \
      -l "${run_label}" --ignore-not-found
    f=delete
    ;;
  *) echo "usage: lab.sh secret|grant|delete" >&2; exit 2 ;;
esac
cat "${here}/evidence/${f}.txt"
