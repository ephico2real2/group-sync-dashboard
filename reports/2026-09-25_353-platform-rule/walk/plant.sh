#!/bin/bash
# plant.sh: the mandate's lab proof item 4 — an unlabelled ServiceAccount grant in a non-platform namespace of its
# own is reported; labelled, it is silent; and the platform half (a grant to an account in a platform namespace)
# is built-in. Everything it creates it removes. Writes ${W}/plant.out. One refresh is up to 300 s
# (bindingIntervalSeconds); each wait polls the pod's loopback API until the row shows the expected tier.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
EV=gsd-evidence-353; SA=u1-evidence-sa; CRB=u1-evidence; PNS=openshift-monitoring; PSA=u1-platform-sa; PCRB=u1-platform
row() {  # row <binding_name>: "<finding> <is_platform> <subject_kind> <subject_namespace>/<name>" or "absent"
  api_as kubeadmin "/api/clusters/dashboard/bindings/findings?limit=5000" | python3 -c 'import json,sys
d = json.load(sys.stdin); name = sys.argv[1]
for tier in ("ok", "dangling", "unresolved", "built_in", "unmanaged"):
    for r in d[tier]:
        if r["binding_name"] == name:
            print(r["finding"], r["is_platform"], r["subject_kind"], f"{r[\"subject_namespace\"]}/{r[\"group_name\"]}", "managed_source=" + str(r["managed_source"])); sys.exit(0)
print("absent")' "$1"
}
wait_for() {  # wait_for <binding_name> <expected first word of row()>  (up to 420 s)
  local t0=$(date +%s) got
  while :; do got=$(row "$1"); [ "${got%% *}" = "$2" ] && { echo "   $(date -u +%H:%M:%SZ) ${1}: ${got}  (after $(( $(date +%s) - t0 )) s)"; return 0; }
    [ $(( $(date +%s) - t0 )) -ge 420 ] && { echo "   TIMEOUT ${1}: ${got}"; return 1; }; sleep 10; done
}
{
echo "# planted-grant proof — $(date -u +%Y-%m-%dT%H:%M:%SZ) — pod $(pod)"
echo "== 1. an unlabelled ServiceAccount grant in a namespace of its own (not the platform's)"
oc create namespace "$EV" && oc create serviceaccount "$SA" -n "$EV" && oc create clusterrolebinding "$CRB" --clusterrole=view --serviceaccount="${EV}:${SA}"
oc get clusterrolebinding "$CRB" -o jsonpath='   labels: {.metadata.labels}  subject: {.subjects[0].kind} {.subjects[0].namespace}/{.subjects[0].name}{"\n"}'
wait_for "$CRB" unmanaged
echo "   log: $(oc logs -n "$NS" "$(pod)" -c dashboard --since=15m | grep -i "unmanaged" | grep "$CRB" | tail -1 | cut -c1-200)"
echo "== 2. the operator's label silences it"
oc label clusterrolebinding "$CRB" rbac.ocp.io/config-source=platform-team
wait_for "$CRB" ok
echo "== 3. the platform half: a grant to an account in a platform namespace is built-in by rule"
oc create serviceaccount "$PSA" -n "$PNS" && oc create clusterrolebinding "$PCRB" --clusterrole=view --serviceaccount="${PNS}:${PSA}"
wait_for "$PCRB" built_in
echo "== 4. removed"
oc delete clusterrolebinding "$CRB" "$PCRB" && oc delete serviceaccount "$PSA" -n "$PNS" && oc delete namespace "$EV" --wait=false
wait_for "$CRB" absent; wait_for "$PCRB" absent
echo "   namespace: $(oc get namespace "$EV" -o jsonpath='{.status.phase}' 2>&1 | head -1)"
echo "# done — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
} 2>&1 | tee "${W}/plant.out"
