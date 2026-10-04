#!/usr/bin/env bash
# SPEC_F2 §5 (#106), the scheduled half: with `csv` in the lab's reporting.formats.scheduled (PR #576), a run of a
# schedule stores json, html and csv. Service-token runs are confined to the night window (22:00-06:00 New York), so
# this waits for the window, then creates one Job from the CronJob `quarterly-compliance` (the schedule's own Job
# template: the trigger, the service token, `--schedule`). The Job is labelled and deleted after its record is read.
#
#   KUBECONFIG=<the lab kubeconfig> scripts/scheduled.sh
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; log="${here}/scheduled.log"
ns=group-sync-dashboard; cj=group-sync-dashboard-report-quarterly-compliance
job="walk-106-scheduled-$(date -u +%H%M%S)"; label=walk.gsd.lab/run=csv-format-106-2026-10-03
: "${KUBECONFIG:?}"; export KUBECONFIG
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() { printf '$ %s\n' "$*" >> "${log}"; bash -c "$*" >> "${log}" 2>&1 || echo "(exit $?)" >> "${log}"; }
formats_env() { oc get deployments.apps -n "${ns}" group-sync-dashboard-report -o json | jq -r '.spec.template.spec.containers[0].env[] | select(.name=="GSD_REPORT_FORMATS_SCHEDULED") | .value'; }
echo "# SPEC_F2 §5 scheduled walk (#106); written by scripts/scheduled.sh; started $(now)" > "${log}"
note "Wait for PR #576's setting on the report pod"
for _ in $(seq 1 120); do [[ "$(formats_env)" == *csv* ]] && break; sleep 30; done
run "oc get deployments.apps -n ${ns} group-sync-dashboard-report -o json | jq -c '[.spec.template.spec.containers[0].env[] | select(.name | test(\"FORMATS\"))]'"
run "oc rollout status deployment/group-sync-dashboard-report -n ${ns} --timeout=600s"
run "oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json | jq -c '{sync: .status.sync.status, health: .status.health.status, revision: .status.sync.revision}'"
note "Wait for the window (22:00 New York)"
until [ "$(TZ=America/New_York date +%H)" -ge 22 ]; do sleep 30; done
sleep 30
run "TZ=America/New_York date"
started="$(now)"
note "One Job from the CronJob ${cj}"
run "oc create job ${job} --from=cronjob/${cj} -n ${ns}"
run "oc label job ${job} -n ${ns} ${label}"
run "oc wait --for=condition=complete job/${job} -n ${ns} --timeout=900s"
run "oc logs job/${job} -n ${ns} --tail=40"
note "The run records written by this Job (schedule quarterly-compliance, requested at or after ${started})"
run "oc exec -n ${ns} deploy/group-sync-dashboard-report -- python3.14 -c 'import json, pathlib
for m in sorted(pathlib.Path(\"/artifacts\").glob(\"*/run.json\")):
    j = json.loads(m.read_text())
    if j.get(\"schedule\") == \"quarterly-compliance\" and (j.get(\"requested_at\") or \"\") >= \"${started}\":
        print(json.dumps({k: j.get(k) for k in (\"id\", \"status\", \"schedule\", \"cluster\", \"formats\", \"bytes\", \"sha256\", \"requested_at\")}))
        print(\"  files:\", sorted(p.name for p in m.parent.iterdir()))'"
note "Clean up"
run "oc delete job ${job} -n ${ns} --ignore-not-found"
run "oc get jobs.batch -n ${ns} -l ${label} -o name"
run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
echo "done $(now)" >> "${log}"
