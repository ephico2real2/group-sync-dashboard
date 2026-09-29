#!/usr/bin/env bash
# The walk's read-only captures: each writes evidence/<label>-<kind>.txt beside scripts/, the command line first.
#   capture.sh version <label>          /api/version through the dashboard pod's loopback
#   capture.sh pvcs <label>             the kept PVCs' names and UIDs
#   capture.sh cani <label>             `oc auth can-i update clusterrolebindings --as=developer`
#   capture.sh grant <label>            the walk's grant, selected by the run label (empty once removed)
#   capture.sh secret <label>           the Secret the form would write, `gsd-cluster-walk-478` (NotFound expected),
#                                       and any Secret carrying the run label
#   capture.sh lease <label>            the fleet Lease: resourceVersion and holder only
#   capture.sh sharedqa <label>         shared-qa's Secret: resourceVersion only (never its data)
#   capture.sh podlog <label> <since>   the dashboard container since <since> (RFC 3339): the create's lines, fleet-*,
#                                       cluster-rejoin*, Traceback and ERROR, with counts
# Every command is a read. No password or token is printed; the fleet account's name is read from its Lease into a
# variable and replaced by `<fleet account>` in everything written, and any `sha256~` value by `sha256~<redacted>`.
set -euo pipefail
kind="${1:?kind}"; label="${2:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"   # the report folder
out="${here}/evidence/${label}-${kind}.txt"
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=ui-478-2026-09-28
lease_label=groupsync-dashboard.io/lease-type=fleet-account
form_secret=gsd-cluster-walk-478
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
fleet=$(oc get leases.coordination.k8s.io -n "${ns}" -l "${lease_label}" -o json \
  | jq -r '[.items[].metadata.annotations["groupsync-dashboard.io/account"]] | if length == 1 then .[0] else error("expected one fleet Lease") end')
redact() { sed -E -e 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g' -e "s/${fleet}/<fleet account>/g"; }

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
    {
      run "oc get secrets.v1. ${form_secret} -n ${ns} || true"
      run "oc get secrets.v1. -n ${ns} -l ${run_label} -o name"
    } > "${out}"
    ;;
  lease)
    run "oc get leases.coordination.k8s.io -n ${ns} -l ${lease_label} -o jsonpath='{range .items[*]}name={.metadata.name} resourceVersion={.metadata.resourceVersion} holderIdentity=\"{.spec.holderIdentity}\"{\"\\n\"}{end}'" > "${out}"
    ;;
  sharedqa)
    run "oc get secrets.v1. gsd-cluster-shared-qa -n ${ns} -o jsonpath='resourceVersion={.metadata.resourceVersion}{\"\\n\"}'" > "${out}"
    ;;
  podlog)
    since="${3:?since (RFC 3339)}"
    raw=$(mktemp); trap 'rm -f "${raw}"' EXIT
    pod=$(oc get pods -n "${ns}" -l app.kubernetes.io/name=group-sync-dashboard,app.kubernetes.io/component!=report \
          --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
    {
      echo "# oc logs -n ${ns} ${pod} -c dashboard --timestamps --since-time=${since}  (captured $(now))"
      oc logs -n "${ns}" "${pod}" -c dashboard --timestamps --since-time="${since}" > "${raw}"
      echo "# lines in the window: $(wc -l < "${raw}" | tr -d ' ')"
      echo "# lines naming walk-478, label-invalid, __proto__ or a POST to /api/clusterconfigs:"
      grep -E 'walk-478|label-invalid|__proto__|POST /api/clusterconfigs' "${raw}" | redact || true
      echo "# cluster-secret-created lines: $(grep -c 'cluster-secret-created' "${raw}" || true)"
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
