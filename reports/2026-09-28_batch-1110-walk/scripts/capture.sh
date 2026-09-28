#!/usr/bin/env bash
# The walk's read-only captures: each writes evidence/<label>-<kind>.txt beside scripts/, the command line first.
#   capture.sh version <label>          /api/version through the dashboard pod's loopback
#   capture.sh pvcs <label>             the kept PVCs' names and UIDs
#   capture.sh cani <label>             `oc auth can-i update clusterrolebindings --as=developer`
#   capture.sh grant <label>            the walk's grant, selected by its label (empty once removed)
#   capture.sh lease <label>            the fleet Lease: resourceVersion and holder only
#   capture.sh sharedqa <label>         shared-qa's Secret: resourceVersion only (never its data)
#   capture.sh onboarding <label>       ConfigMaps carrying the onboarding label (#404's GitOps source)
#   capture.sh polls <label> <db>       poll_outcome of the enabled clusters in a store file, opened read-only
#                                       (`mode=ro&immutable=1`): `/data/backup/<file>` names a backup
#   capture.sh podlog <label> <since>   the dashboard container's lines since <since> (RFC 3339): cluster-refreshed,
#                                       fleet-login, cluster-rejoin*, cluster-unreachable, with their counts
# The #447 follow-up (run label walk.gsd.lab/run=batch-1110-447-2026-09-28, set with GSD_WALK_RUN):
#   capture.sh secret <label>           the throwaway Secret, by the run label: metadata, data and config KEYS only
#   capture.sh audit <label> <since>    the oauth-server audit log since <since> (RFC 3339), read through a pipe and never
#                                       written: counts for developer-walk, developer and the fleet account (by count only)
#   capture.sh podlog447 <label> <since> since <since>: discovery, cluster-refreshed, fleet-*, cluster-rejoin*, every
#                                       line naming walk-447 or /rejoin, with counts
# Every command is a read. No password, token or token-object name is printed; the fleet account's name is read from
# its Lease into a variable and replaced by `<fleet account>` in everything written.
set -euo pipefail
kind="${1:?kind}"; label="${2:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"   # the report folder
out="${here}/evidence/${label}-${kind}.txt"
ns=group-sync-dashboard
run_label="${GSD_WALK_RUN:-walk.gsd.lab/run=batch-1110-2026-09-28}"
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
  lease)
    run "oc get leases.coordination.k8s.io gsd-fleet-666f1ba7f2fdead0 -n ${ns} -o jsonpath='resourceVersion={.metadata.resourceVersion} holderIdentity=\"{.spec.holderIdentity}\" renewTime={.spec.renewTime}{\"\\n\"}'" > "${out}"
    ;;
  sharedqa)
    run "oc get secrets gsd-cluster-shared-qa -n ${ns} -o jsonpath='resourceVersion={.metadata.resourceVersion}{\"\\n\"}'" > "${out}"
    ;;
  onboarding)
    run "oc get configmaps -n ${ns} -l 'groupsync-dashboard.io/config-type in (onboard,sideload)' -o wide" > "${out}"
    ;;
  rollouts)
    run "oc get replicasets.apps -n ${ns} -l app.kubernetes.io/name=group-sync-dashboard -o jsonpath='{range .items[*]}{.metadata.creationTimestamp}  {.metadata.name}  {.spec.template.spec.containers[0].image}  replicas={.status.replicas}{\"\\n\"}{end}' | sort; oc get deployments.apps group-sync-dashboard -n ${ns} -o jsonpath='strategy={.spec.strategy.type}{\"\\n\"}'; oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- ls -l --time-style=+%Y-%m-%dT%H:%M:%S%z /data/backup" > "${out}"
    ;;
  polls)
    db="${3:?db path in the pod}"
    run "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- python3.14 -c 'import sqlite3; c = sqlite3.connect(\"file:${db}?mode=ro&immutable=1\", uri=True); [print(*r, sep=\"  \") for r in c.execute(\"SELECT p.cluster_id, p.observed_at, p.status, substr(coalesce(p.message, \\\"\\\"), 1, 120) FROM poll_outcome p JOIN cluster c ON c.id = p.cluster_id WHERE c.enabled = 1 ORDER BY 1\")]'" > "${out}"
    ;;
  podlog)
    since="${3:?since (RFC 3339)}"
    pod=$(oc get pods -n "${ns}" -l app.kubernetes.io/name=group-sync-dashboard -o jsonpath='{.items[0].metadata.name}')
    raw=$(mktemp); trap 'rm -f "${raw}"' EXIT
    oc logs -n "${ns}" "${pod}" -c dashboard --timestamps --since-time="${since}" > "${raw}"
    count() { grep -c -E "$1" "${raw}" || true; }
    {
      echo "# oc logs -n ${ns} ${pod} -c dashboard --timestamps --since-time=${since}  (captured $(now))"
      echo "# lines in the window: $(wc -l < "${raw}" | tr -d ' ')"
      echo "# cluster-refreshed lines:"
      grep -E ' cluster-refreshed ' "${raw}" | redact || true
      echo "# cluster-refreshed lines: $(count ' cluster-refreshed '), of them by=developer: $(grep ' cluster-refreshed ' "${raw}" | grep -c ' by=developer' || true)"
      echo "# fleet-login lines: $(count ' fleet-login ')"
      grep -E ' fleet-login ' "${raw}" | redact || true
      echo "# cluster-rejoin / cluster-rejoined lines: $(count ' cluster-rejoin')"
      grep -E ' cluster-rejoin' "${raw}" | redact || true
      echo "# cluster-unreachable lines: $(count ' cluster-unreachable ')"
      grep -E ' cluster-unreachable ' "${raw}" | redact || true
      echo "# ERROR or Traceback lines: $(count 'ERROR|Traceback')"
    } > "${out}"
    ;;
  secret)
    run "oc get secrets -n ${ns} -l ${run_label} -o json | jq '[.items[] | {name: .metadata.name, uid: .metadata.uid, resourceVersion: .metadata.resourceVersion, created: .metadata.creationTimestamp, labels: .metadata.labels, annotations: (.metadata.annotations // {}), data_keys: (.data | keys), name_value: (.data.name | @base64d), server: (.data.server | @base64d), config_keys: (.data.config | @base64d | fromjson | keys), tlsClientConfig: (.data.config | @base64d | fromjson | .tlsClientConfig)}]'" > "${out}"
    ;;
  audit)
    since="${3:?since (RFC 3339)}"
    {
      echo "# oc adm node-logs --role=master --path=oauth-server/<every audit*.log>, events at or after ${since}"
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
        | ($e | map(select(.user == "developer-walk"))) as $dw
        | ($e | map(select(.user == "developer"))) as $dev
        | ($e | map(select((.user | ascii_downcase) == ($fa | ascii_downcase)))) as $fl
        | "annotated login events since \($since): \($e | length)",
          "developer-walk, all: \($dw | length); authorize: \($dw | map(select(.uri | startswith("/oauth/authorize"))) | length)",
          "developer, all: \($dev | length); authorize: \($dev | map(select(.uri | startswith("/oauth/authorize"))) | length)",
          "fleet account, all: \($fl | length); authorize: \($fl | map(select(.uri | startswith("/oauth/authorize"))) | length)",
          "developer rows (instant, kind, decision, status):",
          ($dev[] | "  \(.at)Z  \(if (.uri | startswith("/oauth/authorize")) then (if (.uri | test("client_id=openshift-challenging-client")) then "cli" else "session" end) elif (.uri | startswith("/login")) then "credential" else "other" end)  \(.decision)  \(.status)")'
    } > "${out}"
    ;;
  podlog447)
    since="${3:?since (RFC 3339)}"
    pod=$(oc get pods -n "${ns}" -l app.kubernetes.io/name=group-sync-dashboard -o jsonpath='{.items[0].metadata.name}')
    raw=$(mktemp); trap 'rm -f "${raw}"' EXIT
    oc logs -n "${ns}" "${pod}" -c dashboard --timestamps --since-time="${since}" > "${raw}"
    {
      echo "# oc logs -n ${ns} ${pod} -c dashboard --timestamps --since-time=${since}  (captured $(now))"
      echo "# lines in the window: $(wc -l < "${raw}" | tr -d ' ')"
      echo "# discovery, cluster-refreshed, fleet-*, cluster-rejoin*, and every line naming walk-447 or /rejoin, except its poll-cycle timing:"
      grep -E ' (discovery|cluster-refreshed|fleet-[a-z-]*|cluster-rejoin[a-z-]*|cluster-rejoined) |walk-447|/rejoin' "${raw}" \
        | grep -v -e 'walk-447 poll cycle took' | redact || true
      echo "# 'walk-447 poll cycle' lines: $(grep -c 'walk-447 poll cycle took' "${raw}" || true)"
      for e in fleet-lookup fleet-lookup-failed fleet-ping fleet-ping-failed fleet-login fleet-login-refused fleet-login-failed fleet-logout cluster-rejoin-review cluster-rejoined cluster-rejoin-failed cluster-refreshed; do
        echo "# ${e} lines: $(grep -c " ${e} " "${raw}" || true)"
      done
      echo "# cluster-refreshed cluster=walk-447 by=developer outcome=auth_failed: $(grep ' cluster-refreshed ' "${raw}" | grep ' cluster=walk-447 ' | grep ' by=developer ' | grep -c ' outcome=auth_failed' || true)"
      echo "# lines naming /rejoin: $(grep -c '/rejoin' "${raw}" || true)"
      echo "# lines naming the fleet account: $(grep -c -i -F "${fleet}" "${raw}" || true)"
      echo "# ERROR or Traceback lines: $(grep -c -E 'ERROR|Traceback' "${raw}" || true)"
    } > "${out}"
    ;;
  *) echo "unknown kind ${kind}" >&2; exit 2 ;;
esac
echo "wrote ${out}"
