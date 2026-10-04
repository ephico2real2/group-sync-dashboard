#!/usr/bin/env bash
# SPEC_F5 §5 (#140) on the CRC lab, read-only: wait for application 4.5.0, then compare the report pod's
# gsd_report_schedule_status series with the status page's state for every schedule, and show the new rule in the
# deployed PrometheusRule. No cluster write.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; log="${here}/walk.log"; ns=group-sync-dashboard
: "${KUBECONFIG:?}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
run() { printf '$ %s\n' "$*" >> "${log}"; bash -c "$*" >> "${log}" 2>&1 || echo "(exit $?)" >> "${log}"; }
echo "# SPEC_F5 §5 check (#140), CRC lab; written by scripts/run.sh; started $(now)" > "${log}"
for _ in $(seq 1 90); do
  [ "$(oc get pods -n ${ns} -l app.kubernetes.io/instance=group-sync-dashboard -o jsonpath='{range .items[*]}{.spec.containers[0].image}{" "}{.status.containerStatuses[0].ready}{"\n"}{end}' | grep -cE ':4\.5\.0 true' || true)" -ge 2 ] && break
  sleep 20
done
run "oc get pods -n ${ns} -l app.kubernetes.io/instance=group-sync-dashboard -o 'custom-columns=NAME:.metadata.name,START:.status.startTime,IMAGE:.spec.containers[0].image' | grep -vE 'offsite-|verify-'"
run "oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json | jq -c '{sync: .status.sync.status, health: .status.health.status, revision: .status.sync.revision}'"
printf '$ %s\n' "oc exec deploy/group-sync-dashboard-report -- python3.14 -c <scripts/in_pod.py>" >> "${log}"
oc exec -n "${ns}" deploy/group-sync-dashboard-report -c report -- python3.14 -c "$(cat "${here}/scripts/in_pod.py")" > "${here}/state.json"
python3 - "${here}/state.json" >> "${log}" <<'PY'
import json, sys
d = json.load(open(sys.argv[1]))
ones = {}
for line in d["series"]:
    labels = dict(kv.split("=", 1) for kv in line[line.index("{") + 1:line.index("}")].replace('"', "").split(","))
    if float(line.rsplit(" ", 1)[1]) == 1.0:
        ones.setdefault(labels["schedule"], []).append(labels["status"])
print("series lines:", len(d["series"]))
fails = 0
for s in d["page"]:
    ok = ones.get(s["name"]) == [s["status"]]
    fails += not ok
    print(f"{'PASS' if ok else 'FAIL'} {s['name']}: page={s['status']} series_at_1={ones.get(s['name'])}")
print("result", {"schedules": len(d["page"]), "mismatches": fails})
PY
run "oc get prometheusrules.monitoring.coreos.com -n ${ns} group-sync-dashboard -o json | jq -r '.spec.groups[].rules[] | select(.alert==\"GroupSyncDashboardReportScheduleLate\") | {alert, expr, for, severity: .labels.severity}'"
run "oc get prometheusrules.monitoring.coreos.com -n ${ns} group-sync-dashboard -o json | jq '[.spec.groups[].rules[] | select(.alert)] | length'"
echo "done $(now)" >> "${log}"
