#!/usr/bin/env bash
# The #452 walk's read-only captures (after SPEC_D4 Appendix D). Each writes evidence/<label>-<kind>.txt, the command first.
#   capture.sh version <label>          /api/version through the dashboard pod's loopback
#   capture.sh pvcs <label>             the kept PVCs' names and UIDs
#   capture.sh sharedqa <label>         gsd-cluster-shared-qa's resourceVersion (never its data)
#   capture.sh lease <label>            the fleet account's Lease: resourceVersion, spec, annotations, with the
#                                       password digest and the account's name withheld; a sha256 of the whole object
#   capture.sh tokens <label>           OAuth access tokens, counted: developer's by client, the fleet account's by client
#   capture.sh cani <label>             `oc auth can-i update clusterrolebindings --as=developer`
#   capture.sh grant <label>            the walk's binding, selected by its label (empty once removed)
#   capture.sh secret <label>           gsd-cluster-${GSD_WALK_ENTRY:-walk-452}: metadata, annotations, data and config KEYS only
#   capture.sh leases <label>           how many fleet-account Leases exist (a Lease for the made-up account would be a surprise)
#   capture.sh audit <label> <since>    the oauth-server audit log since <since> (RFC 3339), as COUNTS and derived rows
#                                       (instant, kind, decision, status) for developer; counts only for the fleet account
#   capture.sh tiers <label>            the pod's gsd_visibility_tier_checks_total{threshold="cluster_admin"} lines
#   capture.sh podlog <label> <since>   the pod's log since <since>: discovery, cluster-refreshed, fleet-login*,
#                                       fleet-logout*, cluster-rejoin*, and every line naming walk-452, with counts
# Every command is a read. No password or token is printed; any `sha256~` string is redacted; the fleet account's
# name is read from its Lease into a variable and replaced by `<fleet account>` in everything written.
set -euo pipefail
kind="${1:?kind}"; label="${2:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"
out="${here}/evidence/${label}-${kind}.txt"
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=walk-452-2026-09-28
entry="${GSD_WALK_ENTRY:-walk-452}"
lease_label=groupsync-dashboard.io/lease-type=fleet-account
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
fleet=$(oc get leases.coordination.k8s.io -n "${ns}" -l "${lease_label}" -o json \
  | jq -r '[.items[].metadata.annotations["groupsync-dashboard.io/account"]] | if length == 1 then .[0] else error("expected one fleet Lease") end')
redact() { sed -E -e 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g' -e "s/${fleet}/<fleet account>/g"; }
run() {  # the command line, the instant, then its output
  printf '# %s\n# at %s\n' "$*" "$(now)"
  bash -c "$*" 2>&1 | redact
}
loopback() { printf '%s' "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- python3.14 -c 'import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8080$1\").read().decode())'"; }

case "${kind}" in
  version) run "$(loopback /api/version)" > "${out}" ;;
  pvcs) run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=N:.metadata.name,U:.metadata.uid" > "${out}" ;;
  sharedqa) run "oc get secrets -n ${ns} gsd-cluster-shared-qa -o jsonpath='{.metadata.name} resourceVersion={.metadata.resourceVersion}{\"\\n\"}'" > "${out}" ;;
  lease)
    q='.items[0] | {name: .metadata.name, resourceVersion: .metadata.resourceVersion, spec, annotations: (.metadata.annotations | with_entries(if .key == "groupsync-dashboard.io/ping-digest" then .value = "<withheld>" else . end))}'
    {
      run "oc get leases.coordination.k8s.io -n ${ns} -l ${lease_label} -o json | jq '${q}'"
      printf 'sha256 of the whole Lease minus managedFields: '
      oc get leases.coordination.k8s.io -n "${ns}" -l "${lease_label}" -o json \
        | jq -cS '.items[0] | del(.metadata.managedFields)' | shasum -a 256 | sed 's/ .*//'
    } > "${out}"
    ;;
  tokens)
    run "oc get oauthaccesstokens.oauth.openshift.io -o json | jq --arg fa \"\$(oc get leases.coordination.k8s.io -n ${ns} -l ${lease_label} -o jsonpath='{.items[0].metadata.annotations.groupsync-dashboard\\.io/account}')\" '{developer: ([.items[] | select(.userName == \"developer\") | .clientName] | group_by(.) | map({client: .[0], n: length})), fleet_account: ([.items[] | select(.userName == \$fa) | .clientName] | group_by(.) | map({client: .[0], n: length}))}'" > "${out}"
    ;;
  cani) run "oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer || true" > "${out}" ;;
  grant) run "oc get clusterrolebindings.rbac.authorization.k8s.io -l ${run_label} -o wide" > "${out}" ;;
  secret)
    run "oc get secrets -n ${ns} -l groupsync-dashboard.io/secret-type=cluster -o json | jq '[.items[] | select(.metadata.name == \"gsd-cluster-${entry}\") | {name: .metadata.name, uid: .metadata.uid, resourceVersion: .metadata.resourceVersion, created: .metadata.creationTimestamp, labels: .metadata.labels, annotations: .metadata.annotations, data_keys: (.data | keys), stringData_name: (.data.name | @base64d), stringData_server: (.data.server | @base64d), config_keys: (.data.config | @base64d | fromjson | keys), tlsClientConfig: (.data.config | @base64d | fromjson | .tlsClientConfig)}]'" > "${out}"
    ;;
  leases) run "oc get leases.coordination.k8s.io -n ${ns} -l ${lease_label} -o name | wc -l" > "${out}" ;;
  tiers) run "$(loopback /metrics) | grep 'gsd_visibility_tier_checks_total{.*threshold=\"cluster_admin\"}' | grep -E 'allowed|denied'" > "${out}" ;;
  audit)
    since="${3:?since (RFC 3339)}"
    {
      echo "# oc adm node-logs --role=master --path=oauth-server/audit.log (and any rotated file), events at or after ${since}"
      echo "# captured $(now); the raw log is read through a pipe and never written"
      oc adm node-logs --role=master --path=oauth-server/ | awk '{print $2}' | grep -E '^audit' | while read -r f; do
        oc adm node-logs --role=master --path="oauth-server/${f}"
      done | sed 's/^[^ ]* //' | jq -r --arg since "${since}" --arg fa "${fleet}" -s '
        [ .[] | select(.requestReceivedTimestamp >= $since)
          | (.annotations // {}) as $a
          | select($a["authentication.openshift.io/username"] != null)
          | { at: .requestReceivedTimestamp[0:19], user: $a["authentication.openshift.io/username"],
              decision: $a["authentication.openshift.io/decision"], status: .responseStatus.code, uri: .requestURI } ]
        as $e
        | ($e | map(select(.user == "developer"))) as $dev
        | ($e | map(select((.user | ascii_downcase) == ($fa | ascii_downcase)))) as $fl
        | "annotated login events since \($since): \($e | length)",
          "developer, all: \($dev | length)",
          "developer, cli authorize (GET /oauth/authorize, client_id=openshift-challenging-client): \($dev | map(select(.uri | startswith("/oauth/authorize") and test("client_id=openshift-challenging-client"))) | length)",
          "  of them allow: \($dev | map(select((.uri | startswith("/oauth/authorize") and test("client_id=openshift-challenging-client")) and .decision == "allow")) | length), deny: \($dev | map(select((.uri | startswith("/oauth/authorize") and test("client_id=openshift-challenging-client")) and .decision == "deny")) | length), error: \($dev | map(select((.uri | startswith("/oauth/authorize") and test("client_id=openshift-challenging-client")) and .decision == "error")) | length)",
          "fleet account, all: \($fl | length)",
          "fleet account, authorize: \($fl | map(select(.uri | startswith("/oauth/authorize"))) | length)",
          "developer rows (instant, kind, decision, status):",
          ($dev[] | "  \(.at)Z  \(if (.uri | startswith("/oauth/authorize")) then (if (.uri | test("client_id=openshift-challenging-client")) then "cli" else "session" end) elif (.uri | startswith("/login")) then "credential" else "other" end)  \(.decision)  \(.status)")'
    } > "${out}"
    ;;
  podlog)
    since="${3:?since (RFC 3339)}"
    pod=$(oc get pods -n "${ns}" -l app.kubernetes.io/name=group-sync-dashboard -o jsonpath='{.items[0].metadata.name}')
    raw=$(mktemp); trap 'rm -f "${raw}"' EXIT
    oc logs -n "${ns}" "${pod}" -c dashboard --timestamps --since-time="${since}" > "${raw}"
    {
      echo "# oc logs -n ${ns} ${pod} -c dashboard --timestamps --since-time=${since}  (captured $(now))"
      echo "# lines in the window: $(wc -l < "${raw}" | tr -d ' ')"
      echo "# discovery, cluster-refreshed, fleet-*, cluster-rejoin*, cluster-secret-*, unsupported-config-key, and every line naming walk-452 except its poll-cycle timing:"
      grep -E ' (discovery|cluster-refreshed|fleet-[a-z-]*|cluster-rejoin[a-z-]*|cluster-rejoined|cluster-secret-[a-z-]*) |unsupported-config-key|walk-452' "${raw}" \
        | grep -v -e 'walk-452 poll cycle took' -e 'unmanaged-grant discovery' | redact || true
      echo "# 'walk-452 poll cycle' lines: $(grep -c 'walk-452 poll cycle took' "${raw}" || true)"
      echo "# unsupported-config-key lines: $(grep -c 'unsupported-config-key' "${raw}" || true)"
      for e in fleet-lookup fleet-lookup-failed fleet-ping fleet-ping-failed fleet-login fleet-login-refused fleet-login-failed fleet-logout fleet-logout-failed cluster-rejoin-review cluster-rejoined cluster-rejoin-failed cluster-refreshed; do
        echo "# ${e} lines: $(grep -c " ${e} " "${raw}" || true)"
      done
      echo "# lines naming the fleet account: $(grep -c -i -F "${fleet}" "${raw}" || true)"
      echo "# ERROR or Traceback lines: $(grep -c -E 'ERROR|Traceback' "${raw}" || true)"
    } > "${out}"
    ;;
  *) echo "unknown kind ${kind}" >&2; exit 2 ;;
esac
echo "wrote ${out}"
