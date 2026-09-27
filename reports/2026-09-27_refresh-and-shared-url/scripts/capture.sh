#!/usr/bin/env bash
# The walk's read-only captures: each writes evidence/<label>-<kind>.txt beside scripts/, the command line first.
#   capture.sh version <label>          /api/version through the dashboard pod's loopback
#   capture.sh pvcs <label>             the kept PVCs' names and UIDs
#   capture.sh cani <label>             `oc auth can-i update clusterrolebindings --as=developer`
#   capture.sh grant <label>            the walk's grant, selected by its label (empty once removed)
#   capture.sh podlog <label> <since>   the dashboard container's cluster-refreshed and fleet-login lines since
#                                       <since> (RFC 3339), token object names redacted, with their counts
# Every command is a read. No password, token or token-object name is printed.
set -euo pipefail
kind="${1:?kind}"; label="${2:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"   # the report folder
out="${here}/evidence/${label}-${kind}.txt"
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=refresh-shared-url-2026-09-27
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
redact() { sed -E 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g'; }

run() {  # the command line, the instant, then its output
  printf '# %s\n# at %s\n' "$*" "$(now)"
  bash -c "$*" 2>&1 | redact
}

case "${kind}" in
  version)
    run "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- python3.14 -c 'import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8080/api/version\").read().decode())'" > "${out}"
    ;;
  pvcs)
    run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=N:.metadata.name,U:.metadata.uid" > "${out}"
    ;;
  cani)
    run "oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer || true" > "${out}"
    ;;
  grant)
    run "oc get clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io -l ${run_label} -o wide" > "${out}"
    ;;
  podlog)
    since="${3:?since (RFC 3339)}"
    pod=$(oc get pods -n "${ns}" -l app.kubernetes.io/name=group-sync-dashboard -o jsonpath='{.items[0].metadata.name}')
    raw=$(mktemp); trap 'rm -f "${raw}"' EXIT
    oc logs -n "${ns}" "${pod}" -c dashboard --timestamps --since-time="${since}" > "${raw}"
    {
      echo "# oc logs -n ${ns} ${pod} -c dashboard --timestamps --since-time=${since}  (captured $(now))"
      echo "# lines in the window: $(wc -l < "${raw}" | tr -d ' ')"
      echo "# cluster-refreshed lines:"
      grep -E ' cluster-refreshed ' "${raw}" | redact || true
      echo "# cluster-refreshed lines: $(grep -c ' cluster-refreshed ' "${raw}" || true), of them by=developer: $(grep ' cluster-refreshed ' "${raw}" | grep -c ' by=developer' || true)"
      echo "# fleet-login lines:"
      grep -E ' fleet-login ' "${raw}" | redact || true
      echo "# fleet-login lines: $(grep -c ' fleet-login ' "${raw}" || true)"
      echo "# ERROR or Traceback lines: $(grep -c -E 'ERROR|Traceback' "${raw}" || true)"
    } > "${out}"
    ;;
  *) echo "unknown kind ${kind}" >&2; exit 2 ;;
esac
echo "wrote ${out}"
