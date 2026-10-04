#!/usr/bin/env bash
# SPEC_F4 §5 (#109, webhook delivery) on the CRC lab, inside the reporting window. Steps 1-6 of the spec:
# the receiver, the Secret (a random marker in its URL's path), Job 1 from the suspended CronJob `delivery-walk`,
# the checks (check.py; the marker, the receiver's host and `/hook/` grepped in the Job's log and YAML), the failure
# path (Job 2 with the receiver deleted), and the removal by label. The marker is kept in a variable and only counted.
#
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; s="${here}/scripts"; log="${here}/walk.log"
ns=group-sync-dashboard; cj=group-sync-dashboard-report-delivery-walk; host=gsd-delivery-walk.${ns}.svc
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
: "${KUBECONFIG:?}"; export KUBECONFIG PYTHONDONTWRITEBYTECODE=1
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() { printf '$ %s\n' "$*" >> "${log}"; bash -c "$*" >> "${log}" 2>&1 || echo "(exit $?)" >> "${log}"; }
remove() { oc delete pod,service,secret -n "${ns}" -l app=gsd-delivery-walk --ignore-not-found >/dev/null 2>&1 || true
           oc delete job -n "${ns}" delivery-walk-1 delivery-walk-2 --ignore-not-found >/dev/null 2>&1 || true; }
facts() {
  run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
  run "oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json | jq -c '{sync: .status.sync.status, health: .status.health.status, revision: .status.sync.revision}'"
  run "oc get pods -n ${ns} -l app.kubernetes.io/instance=group-sync-dashboard -o 'custom-columns=NAME:.metadata.name,START:.status.startTime,IMAGE:.spec.containers[0].image' | grep -vE 'offsite-|verify-'"
  run "oc get cronjobs.batch -n ${ns} ${cj} -o 'custom-columns=NAME:.metadata.name,SUSPEND:.spec.suspend,SCHEDULE:.spec.schedule,TZ:.spec.timeZone'"
  run "oc get all,secret -n ${ns} -l app=gsd-delivery-walk -o name"
}
echo "# SPEC_F4 §5 walk (#109), CRC lab; written by scripts/run.sh; started $(now) ($(TZ=America/New_York date '+%H:%M %Z'))" > "${log}"
trap remove EXIT
note "Wait for application 4.4.0 and the CronJob"
for _ in $(seq 1 90); do
  ready=$(oc get pods -n ${ns} -l app.kubernetes.io/instance=group-sync-dashboard -o jsonpath='{range .items[*]}{.spec.containers[0].image}{" "}{.status.containerStatuses[0].ready}{"\n"}{end}' | grep -cE ':4\.4\.0 true' || true)
  [ "${ready}" -ge 2 ] && oc get cronjobs.batch -n ${ns} ${cj} >/dev/null 2>&1 && break
  sleep 20
done
note "Before"; facts
note "Step 1: the receiver"
run "oc apply -f '${s}/receiver.yaml'"
run "oc wait --for=condition=Ready pod/gsd-delivery-walk -n ${ns} --timeout=180s"
note "Step 2: the Secret (the URL's path holds a random marker; the command line is not recorded)"
marker=$(openssl rand -hex 16)
oc create secret generic gsd-delivery-walk -n "${ns}" --from-literal=url="http://${host}:8080/hook/${marker}" >/dev/null
run "oc label secret gsd-delivery-walk -n ${ns} app=gsd-delivery-walk walk.gsd.lab/run=webhook-delivery-109-2026-10-04"
note "Step 3: Job 1 from the CronJob"
run "oc create job delivery-walk-1 --from=cronjob/${cj} -n ${ns}"
run "oc wait --for=condition=complete job/delivery-walk-1 -n ${ns} --timeout=900s"
oc logs job/delivery-walk-1 -n "${ns}" > "${here}/job1.log" 2>&1 || true
oc logs pod/gsd-delivery-walk -n "${ns}" > "${here}/receiver.log" 2>&1 || true
run "cat '${here}/job1.log'"
note "Step 4: the checks"
"${py}" -c 'import json,sys; [print(json.loads(l)["id"]) for l in open(sys.argv[1]) if l.startswith("{") and "\"status\"" in l and "\"delivered\"" not in l]' "${here}/job1.log" \
  | oc exec -i -n "${ns}" deploy/group-sync-dashboard-report -c report -- python3.14 -c "$(cat "${s}/artifact_sha.py")" > "${here}/artifacts.jsonl"
"${py}" "${s}/check.py" "${here}" >> "${log}" 2>&1 || echo "check.py failed" >> "${log}"
rm -f "${here}/receiver.log"                     # the cut copy (bodies replaced by their length) is the evidence
{ echo "marker in Job 1's log: $(grep -c "${marker}" "${here}/job1.log" || true)"
  echo "receiver host in Job 1's log: $(grep -c "${host}" "${here}/job1.log" || true)"
  echo "'/hook/' in Job 1's log: $(grep -c '/hook/' "${here}/job1.log" || true)"
  echo "marker in Job 1's YAML: $(oc get job delivery-walk-1 -n "${ns}" -o yaml | grep -c "${marker}" || true)"
  echo "marker in the receiver's cut log: $(grep -c "${marker}" "${here}/receiver-cut.log" || true)"; } >> "${log}"
note "Step 5: the failure path (the receiver Pod deleted, the Service kept)"
run "oc delete pod gsd-delivery-walk -n ${ns} --wait=true"
run "oc create job delivery-walk-2 --from=cronjob/${cj} -n ${ns}"
run "oc wait --for=condition=failed job/delivery-walk-2 -n ${ns} --timeout=900s"
oc logs job/delivery-walk-2 -n "${ns}" > "${here}/job2.log" 2>&1 || true
run "cat '${here}/job2.log'"
{ echo "marker in Job 2's log: $(grep -c "${marker}" "${here}/job2.log" || true)"
  echo "receiver host in Job 2's log: $(grep -c "${host}" "${here}/job2.log" || true)"
  echo "'/hook/' in Job 2's log: $(grep -c '/hook/' "${here}/job2.log" || true)"
  echo "delivery failures named in Job 2's log: $(grep -cE 'delivery failed for run .*(ConnectError|ConnectTimeout|no attempt fits)' "${here}/job2.log" || true)"
  echo "runs done in Job 2's log: $(grep -c '"status": "done"' "${here}/job2.log" || true)"; } >> "${log}"
unset marker
note "Step 6: removal"
remove
run "oc get all,secret -n ${ns} -l app=gsd-delivery-walk -o name"
note "After"; facts
echo "done $(now)" >> "${log}"
