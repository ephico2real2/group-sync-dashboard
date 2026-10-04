#!/usr/bin/env bash
# SPEC_F6 §5 (#392) on the CRC lab. Read-only, except the two refused POSTs (refused, so nothing is created) and one
# real viewer run. Waits for application 4.6.0. No key, token or ticket value is printed.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; log="${here}/walk.log"; ns=group-sync-dashboard; viewer=dana.lee
: "${KUBECONFIG:?}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() { printf '$ %s\n' "$*" >> "${log}"; bash -c "$*" >> "${log}" 2>&1 || echo "(exit $?)" >> "${log}"; }
echo "# SPEC_F6 §5 check (#392), CRC lab; written by scripts/run.sh; started $(now)" > "${log}"
for _ in $(seq 1 90); do
  [ "$(oc get pods -n ${ns} -l app.kubernetes.io/instance=group-sync-dashboard -o jsonpath='{range .items[*]}{.spec.containers[0].image}{" "}{.status.containerStatuses[0].ready}{"\n"}{end}' | grep -cE ':4\.6\.0 true' || true)" -ge 2 ] && break
  sleep 20
done
note "The release"
run "oc get pods -n ${ns} -l app.kubernetes.io/instance=group-sync-dashboard -o 'custom-columns=NAME:.metadata.name,START:.status.startTime,IMAGE:.spec.containers[0].image' | grep -vE 'offsite-|verify-'"
run "oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json | jq -c '{sync: .status.sync.status, health: .status.health.status, revision: .status.sync.revision}'"
run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
note "The minted Secret, by name and key names only (no data)"
run "oc get secret group-sync-dashboard-report-ticket-key -n ${ns} -o json | jq -c '{name: .metadata.name, created: .metadata.creationTimestamp, keys: (.data | keys)}'"
note "Where it is mounted (volume names and paths only)"
run "oc get deploy -n ${ns} -o json | jq -c '.items[] | {name: .metadata.name, ticket_key_volumes: [.spec.template.spec.volumes[]? | select(.secret.secretName? == \"group-sync-dashboard-report-ticket-key\") | {name, items: .secret.items}], mounts: [.spec.template.spec.containers[].volumeMounts[]? | select(.mountPath | test(\"report-ticket\")) | .mountPath]}'"
run "oc get cronjobs.batch -n ${ns} -o json | jq -c '[.items[] | {name: .metadata.name, mounts_ticket_key: ([.spec.jobTemplate.spec.template.spec.volumes[]? | select(.secret.secretName? == \"group-sync-dashboard-report-ticket-key\")] | length)}]'"
note "The report pod's start line"
run "oc logs -n ${ns} deploy/group-sync-dashboard-report -c report | grep -E 'ticket key loaded' | head -3"
note "A ticket forged with the service token (both formats), posted to the report service's loopback"
printf '$ %s\n' "oc exec deploy/group-sync-dashboard-report -- python3.14 -c <scripts/forge.py>" >> "${log}"
oc exec -n "${ns}" deploy/group-sync-dashboard-report -c report -- python3.14 -c "$(cat "${here}/scripts/forge.py")" >> "${log}" 2>&1
note "No run is attributed to the forger"
run "oc exec -n ${ns} deploy/group-sync-dashboard-report -c report -- python3.14 -c 'import json, pathlib; print(sum(1 for m in pathlib.Path(\"/artifacts\").glob(\"*/run.json\") if json.loads(m.read_text()).get(\"generated_by\") == \"walk-forger-392\"))'"
note "A real ticket from the dashboard works: one viewer run as ${viewer}"
ticket=$(oc exec -n "${ns}" deploy/group-sync-dashboard -c dashboard -- python3.14 -c "import sys,urllib.request; print(urllib.request.urlopen(urllib.request.Request('http://127.0.0.1:8080/api/report/ticket', headers={'X-Forwarded-User': '${viewer}'}), timeout=30).read().decode())" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d["ticket"])')
echo "ticket format: prefix $(printf '%s' "${ticket}" | cut -d. -f1), parts $(printf '%s' "${ticket}" | awk -F. '{print NF}')" >> "${log}"
code=$(printf '%s\n%s\n' "${viewer}" "${ticket}" | oc exec -i -n "${ns}" deploy/group-sync-dashboard-report -c report -- python3.14 -c "
import json, ssl, sys, urllib.error, urllib.request
viewer, ticket = (sys.stdin.readline().strip() for _ in range(2))
ctx = ssl.create_default_context(); ctx.check_hostname = False; ctx.verify_mode = ssl.CERT_NONE
req = urllib.request.Request('https://127.0.0.1:8443/report/api/runs', method='POST', data=json.dumps({'report': 'groups', 'cluster': 'dashboard'}).encode(), headers={'Content-Type': 'application/json', 'X-GSD-Report-Ticket': ticket, 'X-Forwarded-User': viewer})
try:
    r = urllib.request.urlopen(req, context=ctx, timeout=30); d = json.loads(r.read()); print(r.status, d.get('id'), d.get('generated_by'))
except urllib.error.HTTPError as e:
    print(e.code, e.read()[:200])
")
unset ticket
echo "real ticket POST: ${code}" >> "${log}"
note "After"
run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
echo "done $(now)" >> "${log}"
