#!/usr/bin/env bash
# The walk's read-only captures: each writes evidence/<label>-<kind>.txt beside scripts/, the command line first.
#   capture.sh version <label>          /api/version through the dashboard pod's loopback
#   capture.sh pvcs <label>             the kept PVCs' names and UIDs
#   capture.sh cani <label>             `oc auth can-i update clusterrolebindings --as=developer`
#   capture.sh grant <label>            the walk's grant, selected by the run label (empty once removed)
#   capture.sh secrets <label>          the walk's Secrets, by the run label: metadata, data and config KEYS only
#   capture.sh lease <label>            the fleet Lease: resourceVersion and holder only
#   capture.sh sharedqa <label>         shared-qa's Secret: resourceVersion only (never its data)
#   capture.sh discovery <label> <since>  the dashboard's `discovery cycle=` lines since <since> (RFC 3339)
#   capture.sh podlog <label> <since>   the dashboard container since <since>: cluster-refreshed, fleet-*,
#                                       cluster-rejoin*, and every line naming a throwaway entry, with counts
# Every command is a read. No password, token or token-object name is printed; the fleet account's name is read from
# its Lease into a variable and replaced by `<fleet account>` in everything written, and any `sha256~` token by
# `sha256~<redacted>`.
set -euo pipefail
kind="${1:?kind}"; label="${2:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"   # the report folder
out="${here}/evidence/${label}-${kind}.txt"
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=ui-1160-2026-09-28
lease_label=groupsync-dashboard.io/lease-type=fleet-account
throwaway='w462|result-w462|constructor'
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
fleet=$(oc get leases.coordination.k8s.io -n "${ns}" -l "${lease_label}" -o json \
  | jq -r '[.items[].metadata.annotations["groupsync-dashboard.io/account"]] | if length == 1 then .[0] else error("expected one fleet Lease") end')
redact() { sed -E -e 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g' -e "s/${fleet}/<fleet account>/g"; }

run() {  # the command line, the instant, then its output
  printf '# %s\n# at %s\n' "$*" "$(now)"
  bash -c "$*" 2>&1 | redact
}

podlog_since() {  # the dashboard container's lines since $1 into the file $2
  local pod
  pod=$(oc get pods -n "${ns}" -l app.kubernetes.io/name=group-sync-dashboard,app.kubernetes.io/component!=report \
        --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
  echo "# oc logs -n ${ns} ${pod} -c dashboard --timestamps --since-time=$1  (captured $(now))"
  oc logs -n "${ns}" "${pod}" -c dashboard --timestamps --since-time="$1" > "$2"
  echo "# lines in the window: $(wc -l < "$2" | tr -d ' ')"
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
  secrets)
    run "oc get secrets -n ${ns} -l ${run_label} -o json | jq '[.items[] | {name: .metadata.name, uid: .metadata.uid, resourceVersion: .metadata.resourceVersion, created: .metadata.creationTimestamp, labels: .metadata.labels, annotations: (.metadata.annotations // {}), data_keys: (.data | keys), name_value: (.data.name | @base64d), server: (.data.server | @base64d), config_keys: (.data.config | @base64d | fromjson | keys), tlsClientConfig: (.data.config | @base64d | fromjson | .tlsClientConfig)}]'" > "${out}"
    ;;
  lease)
    run "oc get leases.coordination.k8s.io -n ${ns} -l ${lease_label} -o jsonpath='{range .items[*]}name={.metadata.name} resourceVersion={.metadata.resourceVersion} holderIdentity=\"{.spec.holderIdentity}\" renewTime={.spec.renewTime}{\"\\n\"}{end}'" > "${out}"
    ;;
  sharedqa)
    run "oc get secrets gsd-cluster-shared-qa -n ${ns} -o jsonpath='resourceVersion={.metadata.resourceVersion}{\"\\n\"}'" > "${out}"
    ;;
  discovery)
    since="${3:?since (RFC 3339)}"
    raw=$(mktemp); trap 'rm -f "${raw}"' EXIT
    {
      podlog_since "${since}" "${raw}"
      echo "# discovery cycle lines:"
      grep -E ' discovery cycle=' "${raw}" | redact || true
      echo "# lines naming a throwaway entry, except poll-cycle timing:"
      grep -E "(^|[ =,:])(${throwaway})([ :,]|$)" "${raw}" | grep -v 'poll cycle took' | grep -v ' cluster-refreshed ' | redact || true
    } > "${out}"
    ;;
  podlog)
    since="${3:?since (RFC 3339)}"
    raw=$(mktemp); trap 'rm -f "${raw}"' EXIT
    {
      podlog_since "${since}" "${raw}"
      echo "# cluster-refreshed lines:"
      grep -E ' cluster-refreshed ' "${raw}" | redact || true
      for c in w462 result-w462 constructor; do
        echo "# cluster-refreshed cluster=${c} by=developer: $(grep ' cluster-refreshed ' "${raw}" | grep " cluster=${c} " | grep -c ' by=developer' || true)"
      done
      echo "# cluster-refreshed lines, all: $(grep -c ' cluster-refreshed ' "${raw}" || true), of them by=developer: $(grep ' cluster-refreshed ' "${raw}" | grep -c ' by=developer' || true)"
      for e in fleet-lookup fleet-lookup-failed fleet-ping fleet-ping-failed fleet-login fleet-login-refused fleet-login-failed fleet-logout cluster-rejoin-review cluster-rejoined cluster-rejoin-failed; do
        echo "# ${e} lines: $(grep -c " ${e} " "${raw}" || true)"
      done
      echo "# lines matching 'fleet-login': $(grep -c 'fleet-login' "${raw}" || true)"
      echo "# lines matching 'cluster-rejoin': $(grep -c 'cluster-rejoin' "${raw}" || true)"
      echo "# lines naming /rejoin: $(grep -c '/rejoin' "${raw}" || true)"
      echo "# lines naming the fleet account: $(grep -c -i -F "${fleet}" "${raw}" || true)"
      echo "# Traceback lines: $(grep -c 'Traceback' "${raw}" || true)"
      echo "# ERROR lines: $(grep -c ' ERROR ' "${raw}" || true)"
      grep -E ' ERROR |Traceback' "${raw}" | redact || true
    } > "${out}"
    ;;
  *) echo "unknown kind ${kind}" >&2; exit 2 ;;
esac
echo "wrote ${out}"
