#!/usr/bin/env bash
# The Tech debt sweep (application 4.7.0, chart 0.70.0) on the CRC lab, after Argo CD deployed main.
#   1. the before-facts (PVC UIDs, Argo CD, pods and images, the deployed version);
#   2. #594: the chart at this commit refuses PDF on a schedule, in three places, and keeps it for manual runs;
#      the lab's report pod and CronJobs name no pdf;
#   3. #555: the deployed recovery script waits on the signal wakeup pipe;
#   4. in_pod.py as dana.lee, through a dashboard-minted ticket: #585, #588, #589;
#   5. walk.py as developer under the labelled grant: #587, #577, #546, #548 (screenshots);
#   6. the grant removed, then the after-facts.
#
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh
#
# Everything goes to walk.log beside this folder's README, each command first. The ticket reaches the report pod on
# stdin only; developer's UI password reaches walk.py through its environment only; neither is printed. The cluster
# writes are the labelled grant's create and delete and one access-certification run, made by the product.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; s="${here}/scripts"; log="${here}/walk.log"
repo="$(git -C "${here}" rev-parse --show-toplevel)"
ns=group-sync-dashboard; viewer=dana.lee
label=walk.gsd.lab/run=tech-debt-sweep-470-2026-10-04
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
: "${KUBECONFIG:?}"; export KUBECONFIG PYTHONDONTWRITEBYTECODE=1
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
pw() { crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password; }
redact() { sed -E 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g'; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() {  # the command line, then its output; a failing command is recorded, not fatal
  printf '$ %s\n' "$*" >> "${log}"
  bash -c "$*" 2>&1 | redact >> "${log}" || echo "(exit ${PIPESTATUS[0]})" >> "${log}"
}
dash() { oc exec -n "${ns}" deploy/group-sync-dashboard -c dashboard -- python3.14 -c "
import sys, urllib.request
req = urllib.request.Request('http://127.0.0.1:8080' + sys.argv[1], headers={'X-Forwarded-User': sys.argv[2]})
print(urllib.request.urlopen(req, timeout=30).read().decode())" "$1" "${viewer}"; }
facts() {
  run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
  run "oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json | jq -c '{sync: .status.sync.status, health: .status.health.status, revision: .status.sync.revision}'"
  run "oc get pods -n ${ns} -l app.kubernetes.io/instance=group-sync-dashboard -o custom-columns=NAME:.metadata.name,START:.status.startTime,IMAGE:.spec.containers[0].image"
  run "oc get clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io -l ${label} -o name"
}
render() {  # helm template of this commit's chart with one --set; prints the exit code and any refusal line
  printf '$ helm template t charts/group-sync-dashboard --set %s\n' "$*" >> "${log}"
  local out rc=0
  out=$(helm template t "${repo}/charts/group-sync-dashboard" --set "$@" 2>&1) || rc=$?
  { echo "exit ${rc}"; printf '%s\n' "${out}" | grep -o 'reporting\.[^"]*PDF copy' | sort -u || true; } >> "${log}"
}
sweep() { oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found >/dev/null 2>&1 || true; }

{ echo "# The Tech debt sweep's lab walk (4.7.0); written by scripts/run.sh"; echo "# started $(now); kube context $(oc config current-context); chart from $(git -C "${repo}" rev-parse HEAD)"; } > "${log}"
rc=0
note "Before"
facts
run "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- python3.14 -c 'import gsd; print(gsd.__version__)'"

note "#594: the chart refuses PDF on a schedule (three places) and keeps it for manual runs"
render 'reporting.formats.scheduled={html,json,pdf}'
render 'reporting.schedules[0].name=weekly,reporting.schedules[0].report=groups,reporting.schedules[0].cluster=dashboard,reporting.schedules[0].schedule=0 22 * * 0,reporting.schedules[0].formats={pdf}'
render 'reporting.schedules[0].name=weekly,reporting.schedules[0].report=groups,reporting.schedules[0].cluster=dashboard,reporting.schedules[0].schedule=0 22 * * 0,reporting.schedules[0].deliver.kind=webhook,reporting.schedules[0].deliver.webhookUrlSecret.name=hook,reporting.schedules[0].deliver.webhookUrlSecret.key=url,reporting.schedules[0].deliver.attach=pdf'
render 'reporting.formats.manual={html,json,pdf}'
note "#594: the lab names no pdf for schedules"
run "oc get deployments.apps -n ${ns} group-sync-dashboard-report -o json | jq -c '[.spec.template.spec.containers[0].env[] | select(.name | test(\"FORMATS\"))]'"
run "oc get cronjobs.batch -n ${ns} -o json | jq -c '[.items[] | {name: .metadata.name, formats: [.spec.jobTemplate.spec.template.spec.containers[0].command as \$c | range(0; \$c | length) | select(\$c[.] == \"--format\" or \$c[.] == \"--attach\") | \$c[.:.+2] | join(\" \")], pdf: ([.spec.jobTemplate.spec.template.spec.containers[0].command[] | select(. == \"pdf\")] | length)}]'"

note "#555: the deployed recovery script waits on the signal wakeup pipe"
run "oc get configmaps -n ${ns} group-sync-dashboard-recovery -o jsonpath='{.data.recovery_mode\\.py}' | grep -nE 'set_wakeup_fd|select\\.select|os\\.pipe|set_blocking'"
run "oc get deployments.apps -n ${ns} group-sync-dashboard-recovery -o custom-columns=NAME:.metadata.name,REPLICAS:.spec.replicas,READY:.status.readyReplicas"

note "in_pod.py as ${viewer}: #585, #588, #589"
printf '$ %s\n' "printf '<viewer>\\n<ticket>\\n' | oc exec -i deploy/group-sync-dashboard-report -c report -- python3.14 -c \"\$(cat scripts/in_pod.py)\"" >> "${log}"
ticket=$(dash /api/report/ticket | python3 -c 'import json,sys; print(json.load(sys.stdin)["ticket"])')
printf '%s\n%s\n' "${viewer}" "${ticket}" \
  | oc exec -i -n "${ns}" deploy/group-sync-dashboard-report -c report -- python3.14 -c "$(cat "${s}/in_pod.py")" >> "${log}" 2>&1 || rc=1
unset ticket

trap sweep EXIT
note "walk.py as developer: the grant (labelled ${label}), then 70 s for the tier cache"
run "oc apply -f '${s}/grant.yaml'"
sleep 70
printf '$ %s\n' "GSD_UI_PASSWORD=<from crc console --credentials> ${py} scripts/walk.py" >> "${log}"
GSD_UI_PASSWORD="$(pw)" "${py}" "${s}/walk.py" >> "${log}" 2>&1 || rc=1
note "The grant removed"
run "oc delete -f '${s}/grant.yaml' --ignore-not-found"
run "oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer || true"
note "After"
facts
echo "run.sh exit ${rc}" >> "${log}"
exit "${rc}"
