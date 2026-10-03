#!/usr/bin/env bash
# #270 on the lab: two viewer runs of one report over one snapshot must carry the same sha256.
# Usage: run.sh <out dir> [report] [viewer]. KUBECONFIG must point at the CRC lab.
# The ticket is read into a variable and handed to the pod on stdin; it is never printed or written.
set -euo pipefail
out="${1:?out dir}"; report="${2:-groups}"; viewer="${3:-dana.lee}"; ns=group-sync-dashboard
here="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "${out}"
pvcs() { oc get pvc -n "${ns}" -o jsonpath='{range .items[*]}{.metadata.name} {.metadata.uid}{"\n"}{end}'; }
{
  echo "== $(date -u +%FT%TZ) before"; pvcs
  oc get deploy -n "${ns}" -o jsonpath='{range .items[*]}{.metadata.name} {.spec.template.spec.containers[0].image} {.status.readyReplicas}/{.spec.replicas}{"\n"}{end}'
} > "${out}/run.log"
dash() { oc exec -n "${ns}" deploy/group-sync-dashboard -c dashboard -- python3.14 -c "
import json, sys, urllib.request
req = urllib.request.Request('http://127.0.0.1:8080' + sys.argv[1], headers={'X-Forwarded-User': sys.argv[2]})
print(urllib.request.urlopen(req, timeout=30).read().decode())" "$1" "${viewer}"; }
cluster=$(dash /api/clusters | python3 -c 'import json,sys; d=json.load(sys.stdin); c=d["clusters"] if isinstance(d,dict) else d; print(c[0]["id"])')
ticket=$(dash /api/report/ticket | python3 -c 'import json,sys; print(json.load(sys.stdin)["ticket"])')
report_deploy=$(oc get deploy -n "${ns}" -l app.kubernetes.io/component=report -o jsonpath='{.items[0].metadata.name}')
echo "== $(date -u +%FT%TZ) runs: report=${report} cluster=${cluster} viewer=${viewer} via deploy/${report_deploy}" >> "${out}/run.log"
printf '%s\n%s\n%s\n%s\n' "${viewer}" "${ticket}" "${cluster}" "${report}" \
  | oc exec -i -n "${ns}" "deploy/${report_deploy}" -c report -- python3.14 -c "$(cat "${here}/in_pod.py")" > "${out}/runs.json"
unset ticket
{ echo "== $(date -u +%FT%TZ) after"; pvcs; } >> "${out}/run.log"
