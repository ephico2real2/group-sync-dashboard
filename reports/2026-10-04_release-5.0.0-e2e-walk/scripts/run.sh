#!/usr/bin/env bash
# The post-release e2e walk of 5.0.0 (Epic F) on the CRC lab, after reports/2026-10-03_release-4.0.0-e2e-walk:
#   1. the facts and a precheck of what `developer` gets without a grant;
#   2. the labelled grant (scripts/grant.yaml, the cluster-admin tier), then 70 s for the tier's cache;
#   3. local-development/e2e-walk/run_walk.sh as `developer`: the login path, every tab, every report generated,
#      downloaded and integrity-checked, the second pass, env facts and the document;
#   4. the grant's delete (and an exit trap), then the facts again;
#   5. the Epic F surfaces, read with oc: CSV and the scheduled formats (#106, #594), the webhook-delivery CronJob
#      (#109), the stale-schedule rule and gauge (#140), the ticket key's mounts and start line (#392);
#   6. an OCR pass over every PNG for secret-shaped text, with a positive control.
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh
# developer's UI password is read from `crc console --credentials` into the tools' environment only, never printed.
# No Secret's data is read: the ticket key is named and its mounts are listed, nothing more.
set -uo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; ev="${here}/evidence"; log="${ev}/run.log"
ns=group-sync-dashboard; label=walk.gsd.lab/run=release-500-e2e-2026-10-04
# run_walk.sh runs from the main checkout: it needs the venv under its own repository (or GSD_WALK_PYTHON, #591).
tools=/Users/olasumbo/gitRepos/group-sync-dashboard
ocr=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/2a50a92d-2994-4c92-a78c-87e7648effc4/scratchpad/ocr
: "${KUBECONFIG:?}"; export KUBECONFIG
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() { printf '$ %s\n' "$*" >> "${log}"; bash -c "$*" >> "${log}" 2>&1 || echo "(exit ${PIPESTATUS[0]})" >> "${log}"; }
pw() { crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password; }
host=$(oc get routes.route.openshift.io -n ${ns} group-sync-dashboard -o jsonpath='{.status.ingress[0].host}')
mkdir -p "${ev}"; { echo "# 5.0.0 e2e walk; written by scripts/run.sh"; echo "# started $(now); kube context $(oc config current-context); host ${host}"; } > "${log}"
facts() {
  run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
  run "oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o jsonpath='{.status.sync.revision} {.status.sync.status} {.status.health.status}{\"\\n\"}'"
  run "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- curl -s http://127.0.0.1:8080/api/version | jq -c '{version, commit, features}'"
  run "oc get deployments.apps -n ${ns} -l app.kubernetes.io/instance=group-sync-dashboard -o custom-columns=NAME:.metadata.name,IMAGE:.spec.template.spec.containers[0].image,WANT:.spec.replicas,READY:.status.readyReplicas"
}
cleanup() { { printf '\n## exit trap  (%s)\n' "$(now)"; oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found 2>&1
  echo "can-i after the trap: $(oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer 2>/dev/null || true)"; } >> "${log}"; }
trap cleanup EXIT
rc=0

note "1. Facts and the precheck (no grant)"
facts
run "oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer"

note "2. The grant"
run "oc create -f '${here}/scripts/grant.yaml'"; granted=$(date +%s)
sleep 70; echo "grant created at $(date -u -r ${granted} +%H:%M:%SZ); tier cache waited until $(now)" >> "${log}"

note "3. run_walk.sh (every tab, every report, integrity, env, the document)"
printf '$ %s\n' "GSD_UI_PASSWORD=<from crc> run_walk.sh --base https://${host} --login-user developer --provider developer --out ${here}" >> "${log}"
GSD_UI_PASSWORD="$(pw)" "${tools}/local-development/e2e-walk/run_walk.sh" --base "https://${host}" --login-user developer --provider developer --out "${here}" >> "${ev}/run_walk.txt" 2>&1 || rc=$?
echo "run_walk.sh exit ${rc}" >> "${log}"

note "4. The grant's delete, then the facts"
run "oc delete -f '${here}/scripts/grant.yaml'"; echo "grant held $(( $(date +%s) - granted )) s" >> "${log}"
facts

note "5. The Epic F surfaces"
run "oc get deployments.apps -n ${ns} group-sync-dashboard-report -o json | jq -c '[.spec.template.spec.containers[0].env[] | select(.name | test(\"FORMATS\"))]'"
run "oc get cronjobs.batch -n ${ns} -o json | jq -c '[.items[] | .spec.jobTemplate.spec.template.spec.containers[0].command as \$c | {name: .metadata.name, deliver: [range(0; \$c | length) | select(\$c[.] == \"--deliver\" or \$c[.] == \"--attach\" or \$c[.] == \"--format\") | \$c[.:.+2] | join(\" \")], pdf: ([\$c[] | select(. == \"pdf\")] | length)}]'"
run "oc get prometheusrules.monitoring.coreos.com -n ${ns} group-sync-dashboard -o json | jq -c '[.spec.groups[].rules[] | select(.alert == \"GroupSyncDashboardReportScheduleLate\") | {alert, for, severity: .labels.severity}], ([.spec.groups[].rules[] | select(.alert)] | length)'"
run "oc exec -n ${ns} deploy/group-sync-dashboard-report -c report -- curl -sk https://127.0.0.1:8443/report/metrics | grep -E '^gsd_report_schedule_status' | sort"
run "oc get deployments.apps -n ${ns} -o json | jq -c '[.items[] | {name: .metadata.name, ticket_key_volumes: [.spec.template.spec.volumes[]? | select(.secret.secretName == \"group-sync-dashboard-report-ticket-key\") | .name]}]'"
run "oc logs -n ${ns} deploy/group-sync-dashboard-report -c report | grep -m1 'ticket key loaded'"

note "6. OCR: secret-shaped text in every PNG (positive control: the word Overview)"
find "${here}" -name '*.png' > "${ev}/pngs.txt"
xargs "${ocr}" < "${ev}/pngs.txt" > "${ev}/ocr-all.txt" 2>/dev/null || true
echo "pngs $(wc -l < "${ev}/pngs.txt" | tr -d ' '); ocr lines $(wc -l < "${ev}/ocr-all.txt" | tr -d ' '); sha256~ $(grep -c 'sha256~' "${ev}/ocr-all.txt"); password $(grep -ci 'password' "${ev}/ocr-all.txt"); control Overview $(grep -c 'Overview' "${ev}/ocr-all.txt")" >> "${log}"
echo "walk exit=${rc} at $(now)" >> "${log}"
exit "${rc}"
