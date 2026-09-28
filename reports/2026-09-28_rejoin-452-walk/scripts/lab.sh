#!/usr/bin/env bash
# The #452 walk's only writes to the lab, each logged to evidence/ with its command and instant:
#   lab.sh apply    step 2: the throwaway Secret gsd-cluster-walk-452 in S4e's POST-RETRIEVAL shape — a bearer token
#                   (random, bogus, never printed), its own `ldapConnectionBootstrap` (a made-up account in no
#                   directory), `token-source: remote-lookup` and NO `lookup-account`. It is not a pending lookup
#                   (no saTokenLookup), not a ping target (no lookup-account) and not a self-login, so no fleet path
#                   presents the fleet password for it. `oc create`, not `apply`: no last-applied annotation copies
#                   the token into the metadata.
#   lab.sh grant    step 4: the disposable binding for `developer` (SPEC_D4 D4-18), then the walk's label
#   lab.sh delete   step 7: the Secret and the binding, BY THE WALK'S LABEL (so this is also the cleanup whatever happened)
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
ns=group-sync-dashboard
entry=walk-452
run_label=walk.gsd.lab/run=walk-452-2026-09-28
binding=walk-452-cluster-admin
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
log() { local out="${here}/evidence/$1"; shift; { printf '# %s\n# at %s\n' "$*" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"; "$@" 2>&1; } >> "${out}"; }

case "${1:?apply|grant|delete}" in
  apply)
    umask 077
    manifest=$(mktemp)
    trap 'rm -f "${manifest}"' EXIT
    # shared-qa's tlsClientConfig, read-only: jq keeps that object alone, and its token never leaves the pipe
    tls=$(oc get secrets -n "${ns}" gsd-cluster-shared-qa -o json | jq -c '.data.config | @base64d | fromjson | .tlsClientConfig')
    # The token reaches jq through its environment, never an argument, and is written only to the 0600 manifest
    GSD_WALK_TOKEN="sha256~$(openssl rand -hex 22)" jq -n --argjson tls "${tls}" --arg entry "${entry}" \
      --arg label "${run_label#*=}" '{
        apiVersion: "v1", kind: "Secret", type: "Opaque",
        metadata: {name: ("gsd-cluster-" + $entry), namespace: "group-sync-dashboard",
                   labels: {"groupsync-dashboard.io/secret-type": "cluster", "walk.gsd.lab/run": $label},
                   annotations: {"groupsync-dashboard.io/token-source": "remote-lookup"}},
        stringData: {name: $entry, server: "https://api.crc.testing:6443", enabled: "true",
                     config: ({bearerToken: env.GSD_WALK_TOKEN, tlsClientConfig: $tls,
                               ldapConnectionBootstrap: "walk-bootstrap-452"} | tojson)}}' > "${manifest}"
    log step2-apply.txt oc create -f "${manifest}"
    ;;
  grant)
    log step4-binding-create.txt oc create clusterrolebinding "${binding}" --clusterrole=cluster-admin --user=developer
    log step4-binding-create.txt oc label clusterrolebindings.rbac.authorization.k8s.io "${binding}" "${run_label}"
    ;;
  delete)
    log step7-delete.txt oc delete secrets -n "${ns}" -l "${run_label}" --ignore-not-found
    log step7-delete.txt oc delete clusterrolebindings.rbac.authorization.k8s.io -l "${run_label}" --ignore-not-found
    ;;
  *) echo "usage: lab.sh apply|grant|delete" >&2; exit 2 ;;
esac
case "$1" in apply) f=step2-apply ;; grant) f=step4-binding-create ;; *) f=step7-delete ;; esac
cat "${here}/evidence/${f}.txt"
