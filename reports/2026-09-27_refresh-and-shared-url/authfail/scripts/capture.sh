#!/usr/bin/env bash
# The addendum's read-only captures: each writes evidence/<label>-<kind>.txt beside scripts/, the command line first.
#   capture.sh version <label>          /api/version through the dashboard pod's loopback
#   capture.sh pvcs <label>             the kept PVCs' names and UIDs
#   capture.sh cani <label>             `oc auth can-i update clusterrolebindings --as=developer`
#   capture.sh grant <label>            the walk's grant, selected by its label (empty once removed)
#   capture.sh secret <label>           the throwaway Secret, selected by its label: metadata and data KEYS only
#   capture.sh podlog <label> <since>   since <since> (RFC 3339): discovery and shared-api-url lines, every line naming
#                                       walk-authfail, the cluster-refreshed and fleet-login lines, with counts
# Every command is a read. No password or token is printed, and any `sha256~` string is redacted.
set -euo pipefail
kind="${1:?kind}"; label="${2:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"   # the addendum folder
out="${here}/evidence/${label}-${kind}.txt"
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=authfail-2026-09-27
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
  secret)
    run "oc get secrets -n ${ns} -l ${run_label} -o json | jq '[.items[] | {name: .metadata.name, uid: .metadata.uid, resourceVersion: .metadata.resourceVersion, created: .metadata.creationTimestamp, labels: .metadata.labels, data_keys: (.data | keys), config_keys: (.data.config | @base64d | fromjson | keys), tlsClientConfig: (.data.config | @base64d | fromjson | .tlsClientConfig)}]'" > "${out}"
    ;;
  podlog)
    since="${3:?since (RFC 3339)}"
    pod=$(oc get pods -n "${ns}" -l app.kubernetes.io/name=group-sync-dashboard -o jsonpath='{.items[0].metadata.name}')
    raw=$(mktemp); trap 'rm -f "${raw}"' EXIT
    oc logs -n "${ns}" "${pod}" -c dashboard --timestamps --since-time="${since}" > "${raw}"
    {
      echo "# oc logs -n ${ns} ${pod} -c dashboard --timestamps --since-time=${since}  (captured $(now))"
      echo "# lines in the window: $(wc -l < "${raw}" | tr -d ' ')"
      echo "# discovery, shared-api-url, cluster-refreshed, fleet-login, and every line naming walk-authfail except its poll-cycle timing:"
      grep -E ' (discovery|shared-api-url|cluster-refreshed|fleet-login) |walk-authfail' "${raw}" \
        | grep -v 'walk-authfail poll cycle took' | redact || true
      echo "# 'walk-authfail poll cycle' lines: $(grep -c 'walk-authfail poll cycle took' "${raw}" || true)"
      echo "# cluster-refreshed lines: $(grep -c ' cluster-refreshed ' "${raw}" || true), of them cluster=walk-authfail by=developer outcome=auth_failed: $(grep ' cluster-refreshed ' "${raw}" | grep ' cluster=walk-authfail ' | grep ' by=developer ' | grep -c ' outcome=auth_failed' || true)"
      echo "# fleet-login lines: $(grep -c ' fleet-login ' "${raw}" || true)"
      echo "# ERROR or Traceback lines: $(grep -c -E 'ERROR|Traceback' "${raw}" || true)"
    } > "${out}"
    ;;
  *) echo "unknown kind ${kind}" >&2; exit 2 ;;
esac
echo "wrote ${out}"
