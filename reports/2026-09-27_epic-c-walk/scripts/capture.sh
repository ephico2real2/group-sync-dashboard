#!/usr/bin/env bash
# The walk's read-only captures. Every command is a read; nothing here writes to the cluster.
#   capture.sh podlog <label>           the dashboard container's fleet-*, self-login* and walk-* lines, and the
#                                        shared-rnd poll count, token object names redacted
#   capture.sh metrics <label>          /metrics through the pod's loopback: the fleet, self-login and cluster-up families
#   capture.sh api <label>              /api/clusterconfigs through the route, as the kubeconfig's existing kubeadmin
#                                        session (bearer; the token is never printed): the fleet block and the walk rows
#   capture.sh audit <label> <since>    the oauth-server audit log, DERIVED: challenging-client authorize records since
#                                        <since> (ISO-8601 UTC) for `developer` and the fleet account only — the raw
#                                        log holds every user's name and is never kept
#   capture.sh leases <label>           the fleet accounts' Leases (annotations and claim)
# Output: evidence/<label>-<kind>.txt beside scripts/. Temporary files (the raw log, the lab's public CA bundle) are
# mktemp files, removed on exit: the raw audit log holds every user's name and is never kept.
set -euo pipefail
kind="${1:?kind}"; label="${2:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"   # the report folder
out="${here}/evidence/${label}-${kind}.txt"
ns=group-sync-dashboard
fleet=ocp-oauth-bind-serviceid
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
redact() { sed -E 's/(token|token_name)=sha256~[A-Za-z0-9_-]+/\1=sha256~<redacted>/g'; }

case "${kind}" in
  podlog)
    pod=$(oc get pods -n "${ns}" -l app.kubernetes.io/name=group-sync-dashboard -o jsonpath='{.items[0].metadata.name}')
    raw=$(mktemp); trap 'rm -f "${raw}"' EXIT
    oc logs -n "${ns}" "${pod}" -c dashboard --timestamps > "${raw}"
    {
      echo "# oc logs -n ${ns} ${pod} -c dashboard --timestamps  (captured $(now)); token object names redacted"
      echo "# pod started: $(oc get pods -n "${ns}" "${pod}" -o jsonpath='{.status.startTime}')"
      echo "# fleet-*, self-login*, and every line naming a walk cluster other than its poll-cycle timing:"
      grep -E ' (fleet-[a-z-]+|self-login[a-z-]*|cluster-resolved) |walk-(self-login|renewal)' "${raw}" \
        | grep -v -E 'walk-(self-login|renewal) poll cycle took' | redact || true
      for c in shared-rnd walk-self-login walk-renewal; do
        n=$(grep -c "${c} poll cycle took" "${raw}" || true)
        echo "# '${c} poll cycle' lines: ${n}"
        [ "${n}" -gt 0 ] && grep "${c} poll cycle took" "${raw}" | sed -n '1p;$p' | cut -c1-150
      done
      echo "# fleet-login lines naming shared-rnd: $(grep -c 'fleet-login cluster=shared-rnd' "${raw}" || true)"
    } > "${out}"
    rm -f "${raw}"
    ;;
  metrics)
    {
      echo "# oc exec … -c dashboard -- python3.14 urlopen(http://127.0.0.1:8080/metrics) | grep the families  ($(now))"
      oc exec -n "${ns}" deploy/group-sync-dashboard -c dashboard -- python3.14 -c \
        'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/metrics").read().decode())' \
        | grep -E '^gsd_(fleet_|self_login|cluster_up|cluster_last_poll_success)' || true
    } > "${out}"
    ;;
  api)
    host=$(oc get routes.route.openshift.io -n "${ns}" group-sync-dashboard -o jsonpath='{.status.ingress[0].host}')
    ca=$(mktemp); trap 'rm -f "${ca}"' EXIT      # the public bundle crc.yaml says verifies the API and the routes
    oc get configmaps -n openshift-config enterprise-and-cluster-ca-bundle -o jsonpath='{.data.ca-bundle\.crt}' > "${ca}"
    {
      echo "# GET https://${host}/api/clusterconfigs, bearer = the kubeconfig's existing kubeadmin session  ($(now))"
      curl -sS --cacert "${ca}" -H "Authorization: Bearer $(oc whoami -t)" \
        "https://${host}/api/clusterconfigs" \
        | jq '{fleet, clusters: [.clusters[] | select(.id == "shared-rnd" or (.id | startswith("walk-")))
               | {id, status, credential, source, retired, last_poll, session, error}],
               findings: [(.findings // [])[] | select(tostring | test("shared-rnd|walk-"))]}'
    } > "${out}"
    ;;
  audit)
    since="${3:?since (ISO-8601 UTC)}"
    raw=$(mktemp); trap 'rm -f "${raw}" "${raw}.rows"' EXIT
    oc adm node-logs --role=master --path=oauth-server/audit.log > "${raw}"
    {
      echo "# oc adm node-logs --role=master --path=oauth-server/audit.log  (captured $(now)), DERIVED:"
      echo "# ResponseComplete GET /oauth/authorize?client_id=openshift-challenging-client records since ${since},"
      echo "# for developer and ${fleet} only (another user's name is never printed)"
      sed -E 's/^[^{]*//' "${raw}" | jq -r --arg since "${since}" --arg fleet "${fleet}" '
        select(.stage? == "ResponseComplete" and (.requestURI // "" | startswith("/oauth/authorize"))
               and (.requestURI | test("client_id=openshift-challenging-client")) and .stageTimestamp >= $since)
        | (.annotations["authentication.openshift.io/username"] // "") as $u
        | select($u == "developer" or $u == $fleet)
        | "\(.stageTimestamp) user=\($u) decision=\(.annotations["authentication.openshift.io/decision"]) code=\(.responseStatus.code)"' \
        2>/dev/null | sort > "${raw}.rows" || true
      cat "${raw}.rows"
      echo "# counts since ${since}:"
      for u in developer "${fleet}"; do
        for d in allow deny; do
          echo "#   ${u} ${d}: $(grep -c " user=${u} decision=${d} " "${raw}.rows" || true)"
        done
      done
      echo "# unnamed denies since ${since} (the unauthenticated challenge a client may send first): $(sed -E 's/^[^{]*//' "${raw}" | jq -r --arg since "${since}" 'select(.stage? == "ResponseComplete" and (.requestURI // "" | startswith("/oauth/authorize")) and (.requestURI | test("client_id=openshift-challenging-client")) and .stageTimestamp >= $since and (.annotations["authentication.openshift.io/username"] // "") == "") | .stageTimestamp' 2>/dev/null | wc -l | tr -d ' ')"
    } > "${out}"
    rm -f "${raw}" "${raw}.rows"
    ;;
  leases)
    {
      echo "# oc get leases.coordination.k8s.io -n ${ns} -l groupsync-dashboard.io/lease-type=fleet-account  ($(now))"
      oc get leases.coordination.k8s.io -n "${ns}" -l groupsync-dashboard.io/lease-type=fleet-account -o json \
        | jq '[.items[] | {name: .metadata.name, resourceVersion: .metadata.resourceVersion,
               annotations: (.metadata.annotations // {} | with_entries(select(.key | startswith("groupsync-dashboard.io/")))),
               holder: .spec.holderIdentity, renewTime: .spec.renewTime}]'
    } > "${out}"
    ;;
  *) echo "unknown kind ${kind}" >&2; exit 2 ;;
esac
echo "wrote ${out}"
