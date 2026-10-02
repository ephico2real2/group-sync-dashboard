#!/usr/bin/env bash
# SPEC_E6 §5 (#306, the KPI page's Backups card) on the CRC lab, end to end, after
# reports/2026-09-30_release-2.0.0-walk/scripts/run.sh: the before-captures, the steps that need no grant (T306-15's
# chart diff, the RBAC render diff, T306-8 in the browser harness), the exit trap, the grant, 70 s for the tier's
# cache, walk.py kpi, the grant's delete and can-i, 70 s again, walk.py refused, the after-captures.
#   GSD_WALK_TMP=<a directory outside the repo> KUBECONFIG=<the lab kubeconfig> scripts/run.sh
# Everything goes to walk.log beside this folder's README, each command first. developer's UI password is read from
# `crc console --credentials` into walk.py's environment only, never printed. Nothing here deploys or changes the
# Argo CD Application; the only cluster writes are the labelled grant's create and delete.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
s="${here}/scripts"; log="${here}/walk.log"
repo="$(cd "${here}/../.." && pwd)"
ns=group-sync-dashboard
label=walk.gsd.lab/run=kpi-backups-306-2026-10-02
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
merged=c57f2927070faa8ee8c6d741bd3f94c903b41e1a     # PR #526's merge
base=53efb10bd2d73a77c77aaccb7c503577a7041b4a       # its merge base: main before #526
: "${GSD_WALK_TMP:?}"; : "${KUBECONFIG:?}"
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
  run "oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer 2>/dev/null || true"
  run "oc get clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io,secrets -A -l ${label} -o name"
}

{ echo "# SPEC_E6 §5 walk (#306), CRC lab; written by scripts/run.sh"; echo "# started $(now); kube context $(oc config current-context)"; } > "${log}"
rc=0

note "Step 1 — before"
facts
run "oc get configmap -n ${ns} group-sync-dashboard-config -o jsonpath='{.data.clusters\\.yaml}' | grep -n -E '^(backupDir|backupIntervalHours|backupKeep|replicaCount):'"
run "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- ls -la --time-style=full-iso /data/backup"

note "Step 5 — T306-15: git diff --name-only <merge base of #526> -- charts/"
run "git -C '${repo}' diff --name-only ${base} ${merged} -- charts/"
run "git -C '${repo}' diff ${base} ${merged} -- charts/ | grep -E '^[+-]' | grep -v -E '^(\\+\\+\\+|---) '"

note "Step 5 — the rendered RBAC rules, main before #526 against ${merged:0:8}, -f environments/crc.yaml -f the Application's valuesObject"
rt="${GSD_WALK_TMP}/rbac"; rm -rf "${rt}"; mkdir -p "${rt}/before" "${rt}/after"
git -C "${repo}" archive "${base}" charts environments | tar -x -C "${rt}/before"
git -C "${repo}" archive "${merged}" charts environments | tar -x -C "${rt}/after"
oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json | jq '.spec.source.helm.valuesObject' > "${rt}/values-object.json"
for side in before after; do
  run "helm template group-sync-dashboard '${rt}/${side}/charts/group-sync-dashboard' -n ${ns} -f '${rt}/${side}/environments/crc.yaml' -f '${rt}/values-object.json' > '${rt}/${side}.yaml' && grep -c '^kind: ' '${rt}/${side}.yaml'"
done
run "'${py}' '${repo}/reports/2026-09-27_epic-c-walk/scripts/rbac_rules.py' '${rt}/before.yaml' '${rt}/after.yaml'"
run "diff <(grep -v -E '^ *(helm.sh/chart|app.kubernetes.io/version|checksum/[a-z-]+): ' '${rt}/before.yaml') <(grep -v -E '^ *(helm.sh/chart|app.kubernetes.io/version|checksum/[a-z-]+): ' '${rt}/after.yaml') | head -40; echo \"rendered lines differing beyond the chart/version labels and checksums: \$(diff <(grep -v -E '^ *(helm.sh/chart|app.kubernetes.io/version|checksum/[a-z-]+): ' '${rt}/before.yaml') <(grep -v -E '^ *(helm.sh/chart|app.kubernetes.io/version|checksum/[a-z-]+): ' '${rt}/after.yaml') | grep -c -E '^[<>]')\""
rm -rf "${rt}"

note "Step 6 — the disabled state is the browser harness's (T306-8), run at ${merged:0:8} in this worktree"
run "cd '${repo}/local-development' && PYTHONPATH='${repo}/local-development' '${py}' -m pytest tests/test_ui.py -p no:cacheprovider --browser chromium -q -k 'test_t306_8 or test_t306_13' 2>&1 | tail -3"

cleanup() {  # everything carrying the walk's label, whatever state the run stopped in
  { printf '\n## exit trap  (%s)\n' "$(now)"
    oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found 2>&1
    oc delete secrets -A -l "${label}" --ignore-not-found 2>&1
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

note "Steps 2, 3, 4 — walk.py kpi (the cluster-admin tier)"
printf '$ %s\n' "GSD_UI_PASSWORD=<from crc console --credentials> ${py} scripts/walk.py kpi" >> "${log}"
GSD_UI_PASSWORD="$(pw)" "${py}" "${s}/walk.py" kpi 2>&1 | redact >> "${log}" || rc=$?

note "The grant's delete"
run "oc delete -f '${s}/grant.yaml'"
echo "grant deleted at $(now); held $(( $(date +%s) - granted )) s" >> "${log}"
run "oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer 2>/dev/null || true"
run "oc get clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io,secrets -A -l ${label} -o name"
sleep 70; echo "waited 70 s for the tier's cache until $(now)" >> "${log}"

note "The lower tier — walk.py refused (no grant)"
printf '$ %s\n' "GSD_UI_PASSWORD=<from crc console --credentials> ${py} scripts/walk.py refused" >> "${log}"
GSD_UI_PASSWORD="$(pw)" "${py}" "${s}/walk.py" refused 2>&1 | redact >> "${log}" || rc=$?

note "Step 7 — after"
facts
echo "walk exit=${rc} at $(now)" >> "${log}"
exit "${rc}"
