#!/usr/bin/env bash
# The post-release e2e walk of 4.0.0 (Epic G) on the CRC lab, after reports/2026-09-30_release-2.0.0-walk:
#   1. the facts and a precheck of what `developer` gets without a grant;
#   2. the labelled grant (scripts/grant.yaml, the cluster-admin tier), then 70 s for the tier's cache;
#   3. local-development/e2e-walk/run_walk.sh as `developer`: the login path, every tab, every report generated,
#      downloaded and integrity-checked, the second pass, env facts and the document;
#   4. scripts/surfaces_400.py: the 4.0.0 surfaces, view only;
#   5. the grant's delete (and an exit trap), then the facts again, the recovery Deployment and the Lease Role;
#   6. an OCR pass over every PNG for secret-shaped text, with a positive control.
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh
# developer's UI password is read from `crc console --credentials` into the tools' environment only, never printed.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; repo="$(cd "${here}/../.." && pwd)"; ev="${here}/evidence"; log="${ev}/run.log"
ns=group-sync-dashboard; label=walk.gsd.lab/run=release-400-e2e-2026-10-03
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
# run_walk.sh runs from the main checkout: it needs the venv under its own repository, and a worktree has none.
tools=/Users/olasumbo/gitRepos/group-sync-dashboard
ocr=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/2a50a92d-2994-4c92-a78c-87e7648effc4/scratchpad/ocr
: "${KUBECONFIG:?}"; export KUBECONFIG
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() { printf '$ %s\n' "$*" >> "${log}"; bash -c "$*" >> "${log}" 2>&1 || echo "(exit ${PIPESTATUS[0]})" >> "${log}"; }
pw() { crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password; }
host=$(oc get routes.route.openshift.io -n ${ns} group-sync-dashboard -o jsonpath='{.status.ingress[0].host}')
mkdir -p "${ev}"; { echo "# 4.0.0 e2e walk; written by scripts/run.sh"; echo "# started $(now); kube context $(oc config current-context); host ${host}"; } > "${log}"
facts() {
  run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
  run "oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o jsonpath='{.status.sync.revision} {.status.sync.status} {.status.health.status}{\"\\n\"}'"
  run "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- curl -s http://127.0.0.1:8080/api/version | jq -c '{version, commit, features}'"
}
cleanup() { { printf '\n## exit trap  (%s)\n' "$(now)"; oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found 2>&1
  echo "can-i after the trap: $(oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer 2>/dev/null || true)"; } >> "${log}"; }
trap cleanup EXIT
rc=0

note "1. Facts and the precheck (no grant)"
facts
run "oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer"
run "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- curl -s -H 'X-Forwarded-User: developer' http://127.0.0.1:8080/api/whoami | jq -c '{scope: .visibility.scope, cluster_admin: .visibility.cluster_admin}'"

note "2. The grant"
run "oc create -f '${here}/scripts/grant.yaml'"; granted=$(date +%s)
sleep 70; echo "grant created at $(date -u -r ${granted} +%H:%M:%SZ); tier cache waited until $(now)" >> "${log}"

note "3. run_walk.sh (every tab, every report, integrity, env, the document)"
printf '$ %s\n' "GSD_UI_PASSWORD=<from crc> run_walk.sh --base https://${host} --login-user developer --provider developer --out ${here}" >> "${log}"
GSD_UI_PASSWORD="$(pw)" "${tools}/local-development/e2e-walk/run_walk.sh" --base "https://${host}" --login-user developer --provider developer --out "${here}" >> "${ev}/run_walk.txt" 2>&1 || rc=$?
echo "run_walk.sh exit ${rc}" >> "${log}"

note "4. The 4.0.0 surfaces, view only"
GSD_UI_PASSWORD="$(pw)" GSD_BASE="https://${host}" "${py}" "${here}/scripts/surfaces_400.py" "${here}" >> "${ev}/surfaces-400.txt" 2>&1 || rc=$?
tail -1 "${ev}/surfaces-400.txt" >> "${log}"

note "5. The grant's delete, then the facts and the 4.0.0 objects"
run "oc delete -f '${here}/scripts/grant.yaml'"; echo "grant held $(( $(date +%s) - granted )) s" >> "${log}"
facts
run "oc get deployments.apps -n ${ns} group-sync-dashboard group-sync-dashboard-recovery -o custom-columns=NAME:.metadata.name,WANT:.spec.replicas,READY:.status.readyReplicas"
run "oc get roles.rbac.authorization.k8s.io group-sync-dashboard-leases -n ${ns} -o jsonpath='{.rules}'; echo; oc get clusterroles.rbac.authorization.k8s.io group-sync-dashboard-reader -o json | jq '[.rules[] | select((.resources // []) | index(\"leases\"))] | length'"

note "6. OCR: secret-shaped text in every PNG (positive control: the word Overview)"
find "${here}" -name '*.png' > "${ev}/pngs.txt"
xargs "${ocr}" < "${ev}/pngs.txt" > "${ev}/ocr-all.txt" 2>/dev/null || true
echo "pngs $(wc -l < "${ev}/pngs.txt" | tr -d ' '); ocr lines $(wc -l < "${ev}/ocr-all.txt" | tr -d ' '); sha256~ $(grep -c 'sha256~' "${ev}/ocr-all.txt"); password $(grep -ci 'password' "${ev}/ocr-all.txt"); control Overview $(grep -c 'Overview' "${ev}/ocr-all.txt")" >> "${log}"
echo "walk exit=${rc} at $(now)" >> "${log}"
exit "${rc}"
