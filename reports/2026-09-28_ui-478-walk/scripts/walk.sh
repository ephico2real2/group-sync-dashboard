#!/usr/bin/env bash
# The whole walk, in order. Run from anywhere with KUBECONFIG naming the lab:
#   KUBECONFIG=<lab kubeconfig> scripts/walk.sh [rerun]
# `rerun` is the second pass: the same steps, its files prefixed `r2-`, and walk.py's granted-rerun / ungranted-rerun
# phases (no Create; see walk.py).
# 1. the removal of the grant is armed FIRST (a shell trap on EXIT deletes it by the run label), then the grant is
#    created (scripts/grant.yaml), `can-i` read, and 70 s waited (the dashboard caches a tier decision for 60 s);
# 2. walk.py granted (the stale link, the Add-cluster form, the namespace pages);
# 3. the grant deleted explicitly by the run label, `can-i` read, 70 s waited;
# 4. walk.py ungranted (the stale link again);
# 5. the after captures, the pod log since the grant was created.
# The developer password is read from `crc console --credentials` into the environment and never printed.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
ev="${here}/evidence"
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
run_label=walk.gsd.lab/run=ui-478-2026-09-28
pass="${1:-first}"
case "${pass}" in
  first) pre="";    phase_g=granted;       phase_u=ungranted ;;
  rerun) pre="r2-"; phase_g=granted-rerun; phase_u=ungranted-rerun ;;
  *) echo "usage: walk.sh [rerun]" >&2; exit 2 ;;
esac
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
cap() { bash "${here}/scripts/capture.sh" "$@"; }

remove_grant() {  # $1: why (explicit | trap)
  {
    echo "# oc delete clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io -l ${run_label} --ignore-not-found  (${1})"
    echo "# at $(now)"
    oc delete clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io -l "${run_label}" --ignore-not-found 2>&1
    echo "# done at $(now)"
  } >> "${ev}/${pre}grant-delete.txt"
}
trap 'remove_grant trap' EXIT          # armed BEFORE the grant exists
trap 'exit 143' TERM INT HUP           # a signal exits through the EXIT trap

GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)"
[ -n "${GSD_UI_PASSWORD}" ] && [ "${GSD_UI_PASSWORD}" != null ] || { echo "no developer password" >&2; exit 1; }
export GSD_UI_PASSWORD

t0=$(now)
echo "t0=${t0}" > "${ev}/${pre}t0.txt"
{ echo "# oc create -f scripts/grant.yaml"; echo "# at $(now)"; oc create -f "${here}/scripts/grant.yaml" 2>&1; } > "${ev}/${pre}grant-create.txt"
cap cani "${pre}granted"; cap grant "${pre}granted"
echo "# waiting 70 s for the tier cache: from $(now)" > "${ev}/${pre}wait-granted.txt"
sleep 70
echo "# to $(now)" >> "${ev}/${pre}wait-granted.txt"

set +e
"${py}" "${here}/scripts/walk.py" "${phase_g}" > "${ev}/${pre}walk-granted.txt" 2>&1
granted_rc=$?
set -e
echo "walk exit=${granted_rc}" >> "${ev}/${pre}walk-granted.txt"

remove_grant explicit
cap cani "${pre}removed"; cap grant "${pre}removed"
echo "# waiting 70 s for the tier cache: from $(now)" > "${ev}/${pre}wait-ungranted.txt"
sleep 70
echo "# to $(now)" >> "${ev}/${pre}wait-ungranted.txt"

set +e
"${py}" "${here}/scripts/walk.py" "${phase_u}" > "${ev}/${pre}walk-ungranted.txt" 2>&1
ungranted_rc=$?
set -e
echo "walk exit=${ungranted_rc}" >> "${ev}/${pre}walk-ungranted.txt"

for k in version pvcs secret lease sharedqa cani grant; do cap "${k}" "${pre}after"; done
cap podlog "${pre}after" "${t0}"
echo "granted_rc=${granted_rc} ungranted_rc=${ungranted_rc}"
