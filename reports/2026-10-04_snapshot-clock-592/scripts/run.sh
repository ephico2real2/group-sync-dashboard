#!/usr/bin/env bash
# SPEC_F7 §5 on the CRC lab, after Argo CD deployed 5.1.0 from main:
#   1. the before-facts (PVC UIDs, Argo CD, pods, the deployed version);
#   2. in_pod.py as dana.lee, one phase per call, each with a fresh dashboard-minted ticket: step 1 (#592), step 2 (#607);
#   3. walk.py as developer under the labelled grant: step 3 (#593), with screenshots;
#   4. the grant removed, then the after-facts.
#   KUBECONFIG=<the lab kubeconfig> scripts/run.sh
# The ticket reaches the report pod on stdin only, and developer's UI password reaches walk.py through its environment
# only; neither is printed. The cluster writes are the grant's create and delete and the product's own report runs.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"; s="${here}/scripts"; log="${here}/walk.log"
ns=group-sync-dashboard; viewer=dana.lee; label=walk.gsd.lab/run=snapshot-clock-592-2026-10-04
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
: "${KUBECONFIG:?}"; export KUBECONFIG PYTHONDONTWRITEBYTECODE=1
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
pw() { crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password; }
note() { printf '\n## %s  (%s)\n' "$*" "$(now)" >> "${log}"; }
run() { printf '$ %s\n' "$*" >> "${log}"; bash -c "$*" 2>&1 | sed -E 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g' >> "${log}" || echo "(exit ${PIPESTATUS[0]})" >> "${log}"; }
dash() { oc exec -n "${ns}" deploy/group-sync-dashboard -c dashboard -- python3.14 -c "
import sys, urllib.request
req = urllib.request.Request('http://127.0.0.1:8080' + sys.argv[1], headers={'X-Forwarded-User': sys.argv[2]})
print(urllib.request.urlopen(req, timeout=30).read().decode())" "$1" "${viewer}"; }
facts() {
  run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=NAME:.metadata.name,UID:.metadata.uid"
  run "oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json | jq -c '{sync: .status.sync.status, health: .status.health.status, revision: .status.sync.revision}'"
  run "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- curl -s http://127.0.0.1:8080/api/version | jq -c '{version, commit}'"
  run "oc get clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io -l ${label} -o name"
}
sweep() { oc delete clusterrolebindings.rbac.authorization.k8s.io,clusterroles.rbac.authorization.k8s.io -l "${label}" --ignore-not-found >/dev/null 2>&1 || true; }

{ echo "# SPEC_F7 §5 lab check (5.1.0); written by scripts/run.sh"; echo "# started $(now); kube context $(oc config current-context)"; } > "${log}"
rc=0
note "Before"
facts
note "in_pod.py as ${viewer}: step 1 (#592) and step 2 (#607)"
inpod() {  # one phase with a fresh ticket ($1 the phase, $2 its argument); the ticket reaches the pod on stdin only
  local ticket
  ticket=$(dash /api/report/ticket | python3 -c 'import json,sys; print(json.load(sys.stdin)["ticket"])')
  printf '%s\n%s\n%s\n%s\n' "${viewer}" "${ticket}" "$1" "${2:-}" \
    | oc exec -i -n "${ns}" deploy/group-sync-dashboard-report -c report -- python3.14 -c "$(cat "${s}/in_pod.py")"
}
printf '$ %s\n' "for each phase: printf '<viewer>\\n<fresh ticket>\\n<phase>\\n<arg>\\n' | oc exec -i deploy/group-sync-dashboard-report -c report -- python3.14 -c \"\$(cat scripts/in_pod.py)\"" >> "${log}"
for attempt in 1 2 3; do                  # a pair that straddles a new copy is run again (SPEC_F7 §5)
  code=0; inpod pair >> "${log}" 2>&1 || code=$?
  [ "${code}" = 3 ] || break
done
[ "${code}" = 0 ] || rc=1
first=$(inpod first) || rc=1
echo "${first}" >> "${log}"
c1=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["id"])' "${first}")
stamp=$(python3 -c 'import json,sys; print(json.loads(sys.argv[1])["stamp"])' "${first}")
for i in $(seq 1 50); do                  # wait for the next snapshot copy (every 300 s by default)
  [ "$(inpod stamp)" != "${stamp}" ] && break; sleep 15
done
inpod second "${c1}" >> "${log}" 2>&1 || rc=1
trap sweep EXIT
note "walk.py as developer: step 3 (#593); the grant (labelled ${label}), then 70 s for the tier cache"
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
