#!/usr/bin/env bash
# The #492 walk's read-only captures (cut down from reports/2026-09-29_ca-244-walk/scripts/capture.sh). Each writes
# evidence/<label>-<kind>.txt, the command first.
#   capture.sh version <label>          /api/version through the dashboard pod's loopback
#   capture.sh pod <label>              the dashboard pod's name, start time, restart counts and image
#   capture.sh pvcs <label>             the PVCs' names and UIDs
#   capture.sh sharedqa <label>         gsd-cluster-shared-qa's resourceVersion (never its data)
#   capture.sh lease <label>            the fleet-account Lease: how many, and each one's resourceVersion and holder only
#   capture.sh cani <label>             `oc auth can-i update clusterrolebindings --as=developer`
#   capture.sh grant <label>            the ClusterRole and ClusterRoleBinding carrying the walk's label
#   capture.sh secrets <label>          every cluster Secret's name and resourceVersion, and anything carrying the
#                                       walk's label (Secrets, ClusterRoles, ClusterRoleBindings, all namespaces)
#   capture.sh walksecrets <label>      the walk's Secret: metadata, labels, name, server and config KEYS, and the
#                                       tlsClientConfig's keys; never the token
#   capture.sh podlog <label> <since>   the dashboard container's log since <since>: discovery, cert-verify-failed,
#                                       fleet-*, every line naming w492-, with counts; the walk's token counted, never
#                                       printed
#   capture.sh redaction <label>        the report folder itself searched for what must not be in it: any `sha256~`
#                                       value, the fleet account's name (any case, screenshots included) and the
#                                       walk's token; file counts only, nothing quoted
# Every command is a read. No password or token is printed; any `sha256~` string is redacted; the fleet account's
# name is read from its Lease into a variable and replaced by `<fleet account>` in everything written.
set -euo pipefail
kind="${1:?kind}"; label="${2:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"
out="${here}/evidence/${label}-${kind}.txt"
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=chip-492-2026-09-30
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
  pod) run "oc get pods -n ${ns} -l app.kubernetes.io/name=group-sync-dashboard -o custom-columns=NAME:.metadata.name,START:.status.startTime,RESTARTS:.status.containerStatuses[*].restartCount,IMAGE:.spec.containers[0].image" > "${out}" ;;
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
  walksecrets)
    run "oc get secrets -n ${ns} -l ${run_label} -o json | jq '[.items[] | {name: .metadata.name, uid: .metadata.uid, resourceVersion: .metadata.resourceVersion, created: .metadata.creationTimestamp, labels: .metadata.labels, annotations: .metadata.annotations, data_keys: (.data | keys), name_value: (.data.name | @base64d), server: (.data.server | @base64d), visibility: (.data.visibility | @base64d), identity: (.data.identity | @base64d), config_keys: (.data.config | @base64d | fromjson | keys), tls_keys: (.data.config | @base64d | fromjson | .tlsClientConfig | keys), bearer_token_length: (.data.config | @base64d | fromjson | .bearerToken | length)}]'" > "${out}"
    ;;
  podlog)
    since="${3:?since (RFC 3339)}"
    raw="${tmp}/podlog-${label}.raw"
    oc logs -n "${ns}" deploy/group-sync-dashboard -c dashboard --timestamps --since-time="${since}" > "${raw}"
    {
      echo "# oc logs -n ${ns} deploy/group-sync-dashboard -c dashboard --timestamps --since-time=${since}  (captured $(now))"
      echo "# lines in the window: $(wc -l < "${raw}" | tr -d ' ')"
      echo "# discovery, cert-verify-failed, fleet-*, and every line naming w492- except its poll-cycle timing and unmanaged-grant summary:"
      grep -E ' (discovery|fleet-[a-z-]*) |cert-verify-failed|w492-' "${raw}" \
        | grep -v -e 'poll cycle took' -e 'unmanaged-grant discovery' | redact || true
      for e in discovery fleet-lookup fleet-ping fleet-login fleet-login-refused fleet-login-failed fleet-logout; do
        echo "# ${e} lines: $(grep -c " ${e} " "${raw}" || true)"
      done
      echo "# cert-verify-failed lines: $(grep -c 'outcome=cert-verify-failed' "${raw}" || true)"
      echo "# lines naming the fleet account: $(grep -c -i -F "${fleet}" "${raw}" || true)"
      echo "# Traceback lines: $(grep -c 'Traceback' "${raw}" || true)"
      echo "# ERROR lines (the string anywhere): $(grep -c 'ERROR' "${raw}" || true)"
      if [ -s "${tmp}/tokens" ]; then
        while IFS= read -r tok; do
          echo "# the walk's bearer token (never printed): $(grep -c -F -- "${tok}" "${raw}" || true) lines"
        done < "${tmp}/tokens"
      else
        echo "# no walk token recorded yet"
      fi
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
      if [ -s "${tmp}/tokens" ]; then
        while IFS= read -r tok; do
          echo "# the walk's bearer token (never printed): $(grep -rl -F -- "${tok}" "${here}" | wc -l | tr -d ' ') files"
        done < "${tmp}/tokens"
      else
        echo "# no walk token recorded"
      fi
    } > "${out}"
    ;;
  *) echo "unknown kind ${kind}" >&2; exit 2 ;;
esac
echo "wrote ${out}"
