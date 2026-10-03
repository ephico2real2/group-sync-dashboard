#!/usr/bin/env bash
# SPEC_H1 §5 (#542, deleting report runs and database copies from the page) on the CRC lab, end to end, after
# reports/2026-10-02_kpi-backups-306/scripts/run.sh. In order:
#   1. the before-captures and the rendered RBAC diff;
#   2. the exit trap, then the grant, then 70 s for the tier's cache;
#   3. walk.py admin;
#   4. the grant's delete and can-i, then 70 s again;
#   5. walk.py refused;
#   6. the audit lines and the counter;
#   7. the after-captures.
#
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh <merge sha of #547>
#
# Everything goes to walk.log beside this folder's README, each command first. developer's UI password is read from
# `crc console --credentials` into walk.py's environment only, never printed. Nothing here deploys or changes the
# Argo CD Application. The only cluster writes are the labelled grant's create and delete; the deletions are the
# product's, made through its page.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
s="${here}/scripts"; log="${here}/walk.log"
repo="$(cd "${here}/../.." && pwd)"
ns=group-sync-dashboard
label=walk.gsd.lab/run=gui-cleanup-542-2026-10-02
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
merged="${1:?the merge sha of #547}"
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
loopback() { printf '%s' "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- python3.14 -c 'import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8080$1\").read().decode())'"; }
facts() {
  run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
  run "oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json | jq -c '{sync: .status.sync.status, health: .status.health.status, revision: .status.sync.revision}'"
  run "oc get pods -n ${ns} -l app.kubernetes.io/instance=group-sync-dashboard -o custom-columns=NAME:.metadata.name,START:.status.startTime,RESTARTS:.status.containerStatuses[*].restartCount,IMAGE:.spec.containers[0].image"
  run "$(loopback /api/version)"
  run "$(loopback /metrics) | grep -E '^gsd_(build_info|housekeeping_deleted_total)'"
  run "oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer 2>/dev/null || true"
  run "oc get clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io -l ${label} -o name"
}

{ echo "# SPEC_H1 §5 walk (#542), CRC lab; written by scripts/run.sh"; echo "# started $(now); kube context $(oc config current-context); merge ${merged}"; } > "${log}"
rc=0

note "Before"
facts
run "oc get configmap -n ${ns} group-sync-dashboard-config -o jsonpath='{.data.clusters\\.yaml}' | grep -n -E '^(housekeepingEnabled|backupDir):'"
run "oc get deployments.apps -n ${ns} group-sync-dashboard-report -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name==\"GSD_REPORT_HOUSEKEEPING_ENABLED\")]}'"

note "The rendered RBAC rules, main before #547 against ${merged:0:8}, -f environments/crc.yaml"
rt="$(mktemp -d)"; mkdir -p "${rt}/before" "${rt}/after"
git -C "${repo}" archive "${merged}^1" charts environments | tar -x -C "${rt}/before"
git -C "${repo}" archive "${merged}" charts environments | tar -x -C "${rt}/after"
for side in before after; do
  run "helm template group-sync-dashboard '${rt}/${side}/charts/group-sync-dashboard' -n ${ns} -f '${rt}/${side}/environments/crc.yaml' > '${rt}/${side}.yaml' && grep -c '^kind: ' '${rt}/${side}.yaml'"
done
run "'${py}' '${repo}/reports/2026-09-27_epic-c-walk/scripts/rbac_rules.py' '${rt}/before.yaml' '${rt}/after.yaml'"
rm -rf "${rt}"

cleanup() {  # everything carrying the walk's label, whatever state the run stopped in
  { printf '\n## exit trap  (%s)\n' "$(now)"
    oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found 2>&1
    echo "can-i after the trap: $(oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer 2>/dev/null || true)"
  } >> "${log}"
}
trap cleanup EXIT

note "The grant"
run "oc create -f '${s}/grant.yaml'"
granted=$(date +%s); echo "grant created at $(now)" >> "${log}"
run "oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer 2>/dev/null || true"
left=$(( 70 - ($(date +%s) - granted) )); [ "${left}" -gt 0 ] && sleep "${left}"
echo "waited for the tier's cache until $(now)" >> "${log}"

note "Steps 1-4: walk.py admin (the cluster-admin tier)"
printf '$ %s\n' "GSD_UI_PASSWORD=<from crc console --credentials> ${py} scripts/walk.py admin" >> "${log}"
GSD_UI_PASSWORD="$(pw)" "${py}" "${s}/walk.py" admin 2>&1 | redact >> "${log}" || rc=$?

note "The grant's delete"
run "oc delete -f '${s}/grant.yaml'"
echo "grant deleted at $(now); held $(( $(date +%s) - granted )) s" >> "${log}"
run "oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer 2>/dev/null || true"
sleep 70; echo "waited 70 s for the tier's cache until $(now)" >> "${log}"

note "Step 5: walk.py refused (no grant)"
printf '$ %s\n' "GSD_UI_PASSWORD=<from crc console --credentials> ${py} scripts/walk.py refused" >> "${log}"
GSD_UI_PASSWORD="$(pw)" "${py}" "${s}/walk.py" refused 2>&1 | redact >> "${log}" || rc=$?

note "Step 6: the record, one audit line per deleted item (the dashboard's log since the grant)"
run "oc logs -n ${ns} deploy/group-sync-dashboard -c dashboard --since=15m | grep -E 'report-run-deleted|db-copy-deleted' | cut -c1-400 | tail -n 100"
run "oc logs -n ${ns} deploy/group-sync-dashboard -c dashboard --since=15m | grep -c -E 'report-run-deleted|db-copy-deleted'"

note "After"
facts
echo "walk exit=${rc} at $(now)" >> "${log}"
exit "${rc}"
