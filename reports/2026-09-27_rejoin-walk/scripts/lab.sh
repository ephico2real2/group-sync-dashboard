#!/usr/bin/env bash
# The walk's only writes to the lab, each written to evidence/ with its command and instant (SPEC_D4 Appendix D):
#   lab.sh grant    step 1: the disposable binding (D4-18), then its label
#   lab.sh delete   step 7: the throwaway entry's Secret, by name; the binding, by name (both --ignore-not-found,
#                   so this is also the cleanup whatever happened)
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
ns=group-sync-dashboard
entry="${GSD_WALK_ENTRY:-rejoin-walk}"       # run 1: rejoin-walk; run 2: rejoin-walk-2
run="${GSD_RUN:-}"                            # run 2 writes r2-step1-grant.txt and r2-step7-delete.txt
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
log() { local out="${here}/evidence/$1"; shift; { printf '# %s\n# at %s\n' "$*" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"; "$@" 2>&1; } >> "${out}"; }

case "${1:?grant|delete}" in
  grant)
    log "${run}step1-binding-create.txt" oc create clusterrolebinding rejoin-walk-cluster-admin --clusterrole=cluster-admin --user=developer
    log "${run}step1-binding-create.txt" oc label clusterrolebindings.rbac.authorization.k8s.io rejoin-walk-cluster-admin walk.gsd.lab/run=rejoin-2026-09-27
    ;;
  delete)
    log "${run}step7-delete.txt" oc delete secrets -n "${ns}" "gsd-cluster-${entry}" --ignore-not-found
    log "${run}step7-delete.txt" oc delete clusterrolebindings.rbac.authorization.k8s.io rejoin-walk-cluster-admin --ignore-not-found
    ;;
  *) echo "usage: lab.sh grant|delete" >&2; exit 2 ;;
esac
cat "${here}/evidence/${run}step$([ "$1" = grant ] && echo 1-binding-create || echo 7-delete).txt"
