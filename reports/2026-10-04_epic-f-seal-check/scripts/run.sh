#!/usr/bin/env bash
# Epic F's seal check on the CRC lab, as the epic's Definition of Done words it (#386): two compliance-snapshot runs
# over one snapshot give one sha256; a run over an older snapshot with changed data gives another, and a report-diff
# between them shows the change. Runs scripts/in_pod.py in the report pod as dana.lee, through a dashboard-minted
# ticket that reaches the pod on stdin only and is never printed. The only writes are the product's three runs.
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; s="${here}/scripts"; log="${here}/walk.log"
ns=group-sync-dashboard; viewer=dana.lee; earlier=20261004T020102.809069Z-3804
: "${KUBECONFIG:?}"; export KUBECONFIG
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
run() { printf '$ %s\n' "$*" >> "${log}"; bash -c "$*" >> "${log}" 2>&1 || echo "(exit $?)" >> "${log}"; }
dash() { oc exec -n "${ns}" deploy/group-sync-dashboard -c dashboard -- python3.14 -c "
import sys, urllib.request
req = urllib.request.Request('http://127.0.0.1:8080' + sys.argv[1], headers={'X-Forwarded-User': sys.argv[2]})
print(urllib.request.urlopen(req, timeout=30).read().decode())" "$1" "${viewer}"; }
{ echo "# Epic F seal check; written by scripts/run.sh"; echo "# started $(now); kube context $(oc config current-context)"; } > "${log}"
run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
run "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- curl -s http://127.0.0.1:8080/api/version | jq -c '{version, commit}'"
printf '$ %s\n' "printf '<viewer>\\n<ticket>\\n${earlier}\\n' | oc exec -i deploy/group-sync-dashboard-report -c report -- python3.14 -c \"\$(cat scripts/in_pod.py)\"" >> "${log}"
ticket=$(dash /api/report/ticket | python3 -c 'import json,sys; print(json.load(sys.stdin)["ticket"])')
printf '%s\n%s\n%s\n' "${viewer}" "${ticket}" "${earlier}" \
  | oc exec -i -n "${ns}" deploy/group-sync-dashboard-report -c report -- python3.14 -c "$(cat "${s}/in_pod.py")" >> "${log}" 2>&1
unset ticket
run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
echo "finished $(now)" >> "${log}"
