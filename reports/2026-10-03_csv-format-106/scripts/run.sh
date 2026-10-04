#!/usr/bin/env bash
# SPEC_F2 §5 (#106, CSV as a report format) on the CRC lab: the manual half, through the page.
#   1. the before-facts (PVC UIDs, Argo CD, pods, the report pod's format settings);
#   2. the exit trap, then the labelled grant, then 70 s for the dashboard's tier cache;
#   3. walk.py;
#   4. the grant's delete and can-i;
#   5. the after-facts.
#
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh
#
# Everything goes to walk.log beside this folder's README, each command first. developer's UI password is read from
# `crc console --credentials` into walk.py's environment only, never printed. The only cluster writes are the
# labelled grant's create and delete; the run is the product's, made through its page.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
s="${here}/scripts"; log="${here}/walk.log"
ns=group-sync-dashboard
label=walk.gsd.lab/run=csv-format-106-2026-10-03
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
: "${KUBECONFIG:?}"
export KUBECONFIG PYTHONDONTWRITEBYTECODE=1
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
pw() { crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password; }
redact() { sed -E 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g'; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() {  # the command line, then its output; a failing command is recorded, not fatal
  printf '$ %s\n' "$*" >> "${log}"
  bash -c "$*" 2>&1 | redact >> "${log}" || echo "(exit ${PIPESTATUS[0]})" >> "${log}"
}
facts() {
  run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
  run "oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json | jq -c '{sync: .status.sync.status, health: .status.health.status, revision: .status.sync.revision}'"
  run "oc get pods -n ${ns} -l app.kubernetes.io/instance=group-sync-dashboard -o custom-columns=NAME:.metadata.name,START:.status.startTime,IMAGE:.spec.containers[0].image"
  run "oc get deployments.apps -n ${ns} group-sync-dashboard-report -o json | jq -c '[.spec.template.spec.containers[0].env[] | select(.name | test(\"FORMATS\"))]'"
  run "oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer 2>/dev/null || true"
  run "oc get clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io -l ${label} -o name"
}
sweep() { oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found >/dev/null 2>&1 || true; }

{ echo "# SPEC_F2 §5 walk (#106), CRC lab; written by scripts/run.sh"; echo "# started $(now); kube context $(oc config current-context)"; } > "${log}"
rc=0
note "Before"
facts
trap sweep EXIT
note "The grant (labelled ${label}), then 70 s for the tier cache"
run "oc apply -f '${s}/grant.yaml'"
sleep 70
note "walk.py"
printf '$ %s\n' "GSD_UI_PASSWORD=<from crc console --credentials> ${py} scripts/walk.py" >> "${log}"
GSD_UI_PASSWORD="$(pw)" "${py}" "${s}/walk.py" >> "${log}" 2>&1 || rc=$?
note "The grant removed"
run "oc delete -f '${s}/grant.yaml' --ignore-not-found"
note "After"
facts
echo "walk.py exit ${rc}" >> "${log}"
exit "${rc}"
