#!/usr/bin/env bash
# The release 2.0.0 walk's read-only captures (after reports/2026-09-30_chip-492-walk/scripts/capture.sh). Each writes
# evidence/<label>-<kind>.txt, the command first.
#   capture.sh version <label>          /api/version through the dashboard pod's loopback
#   capture.sh pod <label>              the dashboard pods' names, start times, restart counts and images
#   capture.sh chart <label>            each Deployment's helm.sh/chart and app.kubernetes.io/version labels
#   capture.sh argo <label>             the dashboard Application's sync, health and revision, and every resource
#                                       whose health is not Healthy
#   capture.sh cronjob <label>          the report CronJobs' schedules, last schedule and last success
#   capture.sh pvcs <label>             the PVCs' names and UIDs
#   capture.sh sharedqa <label>         gsd-cluster-shared-qa's resourceVersion (never its data)
#   capture.sh lease <label>            the fleet-account Lease: how many, and each one's resourceVersion and holder only
#   capture.sh cani <label>             `oc auth can-i update clusterrolebindings --as=developer`
#   capture.sh grant <label>            the ClusterRole and ClusterRoleBinding carrying the walk's label
#   capture.sh secrets <label>          every cluster Secret's name and resourceVersion, and anything carrying the
#                                       walk's label (Secrets, ClusterRoles, ClusterRoleBindings, all namespaces)
#   capture.sh podlog <label> <since>   the dashboard container's log since <since>: discovery, fleet-*,
#                                       cluster-refreshed, with counts
#   capture.sh redaction <label>        the report folder itself searched for what must not be in it: any `sha256~`
#                                       value and the fleet account's name (any case, screenshots and PDFs included,
#                                       the PDFs' text too); file counts only, nothing quoted
# Every command is a read. No password or token is printed; any `sha256~` string is redacted; the fleet account's
# name is read from its Lease into a variable and replaced by `<fleet account>` in everything written.
set -euo pipefail
kind="${1:?kind}"; label="${2:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"
out="${here}/evidence/${label}-${kind}.txt"
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=release-200-2026-09-30
lease_label=groupsync-dashboard.io/lease-type=fleet-account
tmp="${GSD_WALK_TMP:?GSD_WALK_TMP must name the walk temp directory outside the repo}"
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
fleet=$(oc get leases.coordination.k8s.io -n "${ns}" -l "${lease_label}" -o json \
  | jq -r '[.items[].metadata.annotations["groupsync-dashboard.io/account"]] | if length == 1 then .[0] else error("expected one fleet Lease") end')
redact() { sed -E -e 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g' -e "s/${fleet}/<fleet account>/gI"; }
run() {  # the command line, the instant, then its output
  printf '# %s\n# at %s\n' "$*" "$(now)"
  bash -c "$*" 2>&1 | redact
}
loopback() { printf '%s' "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- python3.14 -c 'import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8080$1\").read().decode())'"; }

case "${kind}" in
  version) run "$(loopback /api/version)" > "${out}" ;;
  pod) run "oc get pods -n ${ns} -l app.kubernetes.io/instance=group-sync-dashboard -o custom-columns=NAME:.metadata.name,START:.status.startTime,RESTARTS:.status.containerStatuses[*].restartCount,IMAGE:.spec.containers[0].image" > "${out}" ;;
  chart) run "oc get deployments.apps -n ${ns} -l app.kubernetes.io/instance=group-sync-dashboard -o custom-columns='NAME:.metadata.name,CHART:.metadata.labels.helm\\.sh/chart,VERSION:.metadata.labels.app\\.kubernetes\\.io/version,IMAGE:.spec.template.spec.containers[0].image'" > "${out}" ;;
  argo) run "oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json | jq -c '{sync: .status.sync.status, health: .status.health.status, revision: .status.sync.revision, not_healthy: [.status.resources[] | select(.health.status != null and .health.status != \"Healthy\") | {kind, name, health: .health.status, message: .health.message}]}'" > "${out}" ;;
  cronjob) run "oc get cronjobs.batch -n ${ns} -o custom-columns=NAME:.metadata.name,SCHEDULE:.spec.schedule,TZ:.spec.timeZone,LAST_SCHEDULE:.status.lastScheduleTime,LAST_SUCCESS:.status.lastSuccessfulTime" > "${out}" ;;
  pvcs) run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=N:.metadata.name,U:.metadata.uid" > "${out}" ;;
  sharedqa) run "oc get secrets -n ${ns} gsd-cluster-shared-qa -o jsonpath='{.metadata.name} resourceVersion={.metadata.resourceVersion}{\"\\n\"}'" > "${out}" ;;
  lease) run "oc get leases.coordination.k8s.io -n ${ns} -l ${lease_label} -o json | jq -c '{fleet_account_leases: (.items | length), leases: [.items[] | {resourceVersion: .metadata.resourceVersion, holder: .spec.holderIdentity}]}'" > "${out}" ;;
  cani) run "oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer || true" > "${out}" ;;
  grant) run "oc get clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io -l ${run_label} -o name" > "${out}" ;;
  secrets)
    {
      run "oc get secrets -n ${ns} -l groupsync-dashboard.io/secret-type=cluster -o custom-columns=NAME:.metadata.name,RV:.metadata.resourceVersion,CREATED:.metadata.creationTimestamp"
      run "oc get secrets,clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io -A -l ${run_label} -o name"
    } > "${out}"
    ;;
  podlog)
    since="${3:?since (RFC 3339)}"
    raw="${tmp}/podlog-${label}.raw"
    oc logs -n "${ns}" deploy/group-sync-dashboard -c dashboard --timestamps --since-time="${since}" > "${raw}"
    {
      echo "# oc logs -n ${ns} deploy/group-sync-dashboard -c dashboard --timestamps --since-time=${since}  (captured $(now))"
      echo "# lines in the window: $(wc -l < "${raw}" | tr -d ' ')"
      echo "# discovery cycles, fleet-* and cluster-refreshed lines:"
      grep -E ' (discovery cycle=|(fleet-[a-z-]*|cluster-refreshed) )' "${raw}" | redact || true
      echo "# discovery cycle lines: $(grep -c ' discovery cycle=' "${raw}" || true)"
      for e in fleet-lookup fleet-ping fleet-login fleet-login-refused fleet-login-failed fleet-logout cluster-refreshed cluster-rejoined; do
        echo "# ${e} lines: $(grep -c " ${e} " "${raw}" || true)"
      done
      echo "# lines naming the fleet account: $(grep -c -i -F "${fleet}" "${raw}" || true)"
      echo "# Traceback lines: $(grep -c 'Traceback' "${raw}" || true)"
      echo "# ERROR lines (the string anywhere): $(grep -c 'ERROR' "${raw}" || true)"
    } > "${out}"
    rm -f "${raw}"
    ;;
  redaction)
    {
      echo "# the report folder searched at $(now); counts of FILES, nothing quoted"
      echo "# grep -rl 'sha256~[A-Za-z0-9]' <folder>   (a token that escaped the filter, screenshots included; the placeholder is sha256~<redacted>)"
      echo "# files: $(grep -rl 'sha256~[A-Za-z0-9]' "${here}" | wc -l | tr -d ' ')"
      echo "# grep -rli -F '<the fleet account>' <folder>   (its real name, any case, screenshots included)"
      echo "# files: $(grep -rli -F -- "${fleet}" "${here}" | wc -l | tr -d ' ')"
      n=0; total=0
      while IFS= read -r -d '' pdf; do
        total=$((total + 1))
        if pdftotext -q "${pdf}" - | grep -qi -F -- "${fleet}"; then n=$((n + 1)); fi
      done < <(find "${here}" -name '*.pdf' -print0)
      echo "# pdftotext <each PDF> - | grep -i -F '<the fleet account>'   (the PDFs' extracted text)"
      echo "# PDFs: ${total}; naming the fleet account: ${n}"
      echo "# the screenshots are masked where the page's DOM named the fleet account: evidence/mask-log.jsonl"
    } > "${out}"
    ;;
  *) echo "unknown kind ${kind}" >&2; exit 2 ;;
esac
echo "wrote ${out}"
