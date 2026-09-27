#!/usr/bin/env bash
# The #432 walk's read-only captures. Every command is a read; nothing here writes to the cluster.
#   capture.sh podlog <label> <since>        the dashboard container's lines since <since> (RFC 3339): every fleet-*,
#                                            self-login*, cluster-secret-* and discovery line, every line naming a walk
#                                            cluster except its poll-cycle timing, and the counts. Token object names
#                                            (sha256~…) redacted.
#   capture.sh metrics <label>               /metrics through the pod's loopback: the fleet families and cluster-up
#   capture.sh audit <label> <since> [until] the oauth-server audit log, DERIVED: challenging-client authorize records
#                                            in [since, until) for `developer` and the fleet account only, with counts.
#                                            The raw log names every user and is never kept: it lives in a mktemp file
#                                            removed on exit.
# Output: evidence/<label>-<kind>.txt beside scripts/.
set -euo pipefail
kind="${1:?kind}"; label="${2:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"   # the report folder
out="${here}/evidence/${label}-${kind}.txt"
ns=group-sync-dashboard
fleet=ocp-oauth-bind-serviceid
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
redact() { sed -E 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g'; }
tmp=$(mktemp -d); trap 'rm -rf "${tmp}"' EXIT

case "${kind}" in
  podlog)
    since="${3:?since (RFC 3339)}"
    pod=$(oc get pods -n "${ns}" -l app.kubernetes.io/name=group-sync-dashboard -o jsonpath='{.items[0].metadata.name}')
    oc logs -n "${ns}" "${pod}" -c dashboard --timestamps --since-time="${since}" > "${tmp}/raw"
    {
      echo "# oc logs -n ${ns} ${pod} -c dashboard --timestamps --since-time=${since}  (captured $(now)); sha256~ names redacted"
      echo "# pod started: $(oc get pods -n "${ns}" "${pod}" -o jsonpath='{.status.startTime}'); lines in the window: $(wc -l < "${tmp}/raw" | tr -d ' ')"
      echo "# every line of the fleet, self-login, lookup-state and discovery loggers; leadership changes; failed polls;"
      echo "# a walk cluster's start and stop; ERROR/CRITICAL/Traceback. Routine poll lines are counted below, not listed:"
      grep -E ' gsd\.(clusterconfig(\.writer)?|fleetlogin|selflogin|fleetstate|fleetlookup) | gsd\.leader .*(became leader|taking it)| cluster-unreachable |Traceback| ERROR | CRITICAL |gsd\.poller .*walk-(lookup|self-login)(: polling started| .*not polling|: its Secret is gone)' "${tmp}/raw" \
        | redact || true
      for c in shared-rnd walk-lookup walk-self-login; do
        echo "# successful '${c}' polls ('polled ${c}:' lines): $(grep -c "polled ${c}:" "${tmp}/raw" || true); failed polls (cluster-unreachable … cluster=${c}): $(grep -c -E "cluster-unreachable .*cluster=${c}( |$)" "${tmp}/raw" || true)"
      done
      for e in fleet-login fleet-login-failed fleet-login-refused fleet-logout fleet-logout-failed fleet-lookup fleet-lookup-failed \
               fleet-ping fleet-ping-failed fleet-credential-suspended self-login-renewed self-login-failed fleet-state-unavailable; do
        echo "# '${e}' lines: $(grep -c -E " ${e} " "${tmp}/raw" || true), naming ${fleet}: $(grep -E " ${e} " "${tmp}/raw" | grep -c "${fleet}" || true)"
      done
      echo "# ERROR or Traceback lines: $(grep -c -E ' ERROR |Traceback' "${tmp}/raw" || true)"
    } > "${out}"
    ;;
  metrics)
    {
      echo "# oc exec … -c dashboard -- python3.14 urlopen(http://127.0.0.1:8080/metrics) | grep the families  ($(now))"
      oc exec -n "${ns}" deploy/group-sync-dashboard -c dashboard -- python3.14 -c \
        'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/metrics").read().decode())' \
        | grep -E '^gsd_(fleet_|cluster_up|cluster_last_poll_success)' || true
    } > "${out}"
    ;;
  audit)
    since="${3:?since (ISO-8601 UTC)}"; until="${4:-9999-12-31T00:00:00Z}"
    files=$(oc adm node-logs --role=master --path=oauth-server/ | awk '{print $2}' | grep -E '^audit.*\.log$' || true)
    : > "${tmp}/raw"
    for f in ${files}; do oc adm node-logs --role=master --path="oauth-server/${f}" >> "${tmp}/raw"; done
    sed -E 's/^[^{]*//' "${tmp}/raw" | jq -r --arg since "${since}" --arg until "${until}" --arg fleet "${fleet}" '
        select(.stage? == "ResponseComplete" and (.requestURI // "" | startswith("/oauth/authorize"))
               and (.requestURI | test("client_id=openshift-challenging-client"))
               and .stageTimestamp >= $since and .stageTimestamp < $until)
        | (.annotations["authentication.openshift.io/username"] // "") as $u
        | if $u == "developer" or $u == $fleet then
            "\(.stageTimestamp) user=\($u) decision=\(.annotations["authentication.openshift.io/decision"] // "-") code=\(.responseStatus.code)"
          elif $u == "" then "\(.stageTimestamp) user=(none) decision=\(.annotations["authentication.openshift.io/decision"] // "-") code=\(.responseStatus.code)"
          else empty end' 2>/dev/null | sort > "${tmp}/rows" || true
    {
      echo "# oc adm node-logs --role=master --path=oauth-server/<${files//$'\n'/,}>  (captured $(now)), DERIVED:"
      echo "# ResponseComplete GET /oauth/authorize?client_id=openshift-challenging-client in [${since}, ${until}),"
      echo "# for developer and ${fleet} only, and the records that carry no username (another user's name is never printed)"
      echo "# audit records read: $(sed -E 's/^[^{]*//' "${tmp}/raw" | grep -c '^{' || true); earliest: $(sed -E 's/^[^{]*//' "${tmp}/raw" | jq -r '.stageTimestamp? // empty' 2>/dev/null | sort | head -1)"
      grep -v 'user=(none)' "${tmp}/rows" || true
      echo "# counts in [${since}, ${until}):"
      for u in developer "${fleet}"; do
        for d in allow deny error; do
          echo "#   ${u} ${d}: $(grep -c " user=${u} decision=${d} " "${tmp}/rows" || true)"
        done
        echo "#   ${u} authorize records, any decision: $(grep -c " user=${u} " "${tmp}/rows" || true)"
      done
      echo "#   records with no username (an unauthenticated challenge a client may send first): $(grep -c 'user=(none)' "${tmp}/rows" || true)"
    } > "${out}"
    ;;
  *) echo "unknown kind ${kind}" >&2; exit 2 ;;
esac
echo "wrote ${out}"
