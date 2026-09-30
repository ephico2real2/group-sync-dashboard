#!/usr/bin/env bash
# The #449 measurement's read-only captures (after reports/2026-09-29_rejoin-465-walk/scripts/capture.sh). Each writes
# evidence/<label>-<kind>.txt, the command first.
#   capture.sh version <label>           /api/version through the dashboard pod's loopback
#   capture.sh pvcs <label>              the PVCs' names and UIDs
#   capture.sh sharedqa <label>          gsd-cluster-shared-qa's resourceVersion (never its data)
#   capture.sh lease <label>             the fleet-account Lease: how many, and each one's resourceVersion and holder only
#   capture.sh tokens <label>            OAuth access tokens, counted by client: developer's and the fleet account's
#   capture.sh secret <label>            gsd-cluster-logins-449: metadata, labels, data and config KEYS only
#   capture.sh kubeconfig <label>        the sha256 of the lab kubeconfig FILE (never its content): the login must not touch it
#   capture.sh auditfile <label>         audit.log's size on the node, through the same nodes/proxy path the dashboard reads
#   capture.sh audit <label> <since>     the oauth-server audit log since <since> (RFC 3339): developer's rows (instant, kind,
#                                        decision, status, auditID, and the BYTE OFFSET of the event's line in audit.log);
#                                        counts only for the fleet account
#   capture.sh podlog <label> <since>    the dashboard container's log since <since>: discovery, every audit-log line of
#                                        logins-449 and of dashboard (the control), with counts
# Every command is a read. No password or token is printed; any `sha256~` string is redacted; the fleet account's name
# is read from its Lease into a variable and replaced by `<fleet account>` in everything written.
set -euo pipefail
kind="${1:?kind}"; label="${2:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"
out="${here}/evidence/${label}-${kind}.txt"
ns=group-sync-dashboard
entry=logins-449
node=crc
lease_label=groupsync-dashboard.io/lease-type=fleet-account
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
fleet=$(oc get leases.coordination.k8s.io -n "${ns}" -l "${lease_label}" -o json \
  | jq -r '[.items[].metadata.annotations["groupsync-dashboard.io/account"]] | if length == 1 then .[0] else error("expected one fleet Lease") end')
redact() { sed -E -e 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g' -e "s/${fleet}/<fleet account>/gI"; }
run() {  # the command line, the instant, then its output
  printf '# %s\n# at %s\n' "$*" "$(now)"
  bash -c "$*" 2>&1 | redact
}
loopback() { printf '%s' "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- curl -s http://127.0.0.1:8080$1"; }

case "${kind}" in
  version) run "$(loopback /api/version)" > "${out}" ;;
  pvcs) run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=N:.metadata.name,U:.metadata.uid" > "${out}" ;;
  sharedqa) run "oc get secrets -n ${ns} gsd-cluster-shared-qa -o jsonpath='{.metadata.name} resourceVersion={.metadata.resourceVersion}{\"\\n\"}'" > "${out}" ;;
  lease) run "oc get leases.coordination.k8s.io -n ${ns} -l ${lease_label} -o json | jq -c '{fleet_account_leases: (.items | length), leases: [.items[] | {resourceVersion: .metadata.resourceVersion, holder: .spec.holderIdentity}]}'" > "${out}" ;;
  tokens)
    run "oc get oauthaccesstokens.oauth.openshift.io -o json | jq -c --arg fa \"\$(oc get leases.coordination.k8s.io -n ${ns} -l ${lease_label} -o jsonpath='{.items[0].metadata.annotations.groupsync-dashboard\\.io/account}')\" '{developer: ([.items[] | select(.userName == \"developer\") | .clientName] | group_by(.) | map({client: .[0], n: length})), fleet_account: ([.items[] | select(.userName == \$fa) | .clientName] | group_by(.) | map({client: .[0], n: length}))}'" > "${out}"
    ;;
  secret)
    # The copy is compared with shared-rnd's token inside one jq program over one list: neither token reaches an argv.
    run "oc get secrets -n ${ns} -l groupsync-dashboard.io/secret-type=cluster -o json | jq '([.items[] | select(.metadata.name == \"gsd-cluster-shared-rnd\") | .data.config | @base64d | fromjson | .bearerToken][0]) as \$rnd | [.items[] | select(.metadata.name == \"gsd-cluster-${entry}\") | {name: .metadata.name, uid: .metadata.uid, resourceVersion: .metadata.resourceVersion, created: .metadata.creationTimestamp, labels: .metadata.labels, annotations: .metadata.annotations, data_keys: (.data | keys), name_value: (.data.name | @base64d), server: (.data.server | @base64d), config_keys: (.data.config | @base64d | fromjson | keys), tlsClientConfig: (.data.config | @base64d | fromjson | .tlsClientConfig), token_equals_shared_rnd: ((.data.config | @base64d | fromjson | .bearerToken) == \$rnd)}]'" > "${out}"
    ;;
  kubeconfig) run "shasum -a 256 \"${KUBECONFIG}\" | cut -c1-16" > "${out}" ;;
  auditfile) run "oc get --raw /api/v1/nodes/${node}/proxy/logs/oauth-server/audit.log | wc -c" > "${out}" ;;
  audit)
    since="${3:?since (RFC 3339)}"
    raw=$(mktemp); trap 'rm -f "${raw}"' EXIT
    # The raw log lives only in this 0600 temp file for the grep -b offsets; it is removed by the trap.
    chmod 600 "${raw}"
    oc get --raw "/api/v1/nodes/${node}/proxy/logs/oauth-server/audit.log" > "${raw}"
    {
      echo "# oc get --raw /api/v1/nodes/${node}/proxy/logs/oauth-server/audit.log, events at or after ${since}"
      echo "# captured $(now); audit.log was $(wc -c < "${raw}" | tr -d ' ') bytes; the raw log is never written to this folder"
      jq -r --arg since "${since}" --arg fa "${fleet}" -s '
        [ .[] | select(.requestReceivedTimestamp >= $since)
          | (.annotations // {}) as $a
          | select($a["authentication.openshift.io/username"] != null)
          | { at: .stageTimestamp, user: $a["authentication.openshift.io/username"], stage: .stage,
              decision: $a["authentication.openshift.io/decision"], status: .responseStatus.code, uri: .requestURI,
              id: .auditID } ]
        as $e
        | ($e | map(select(.user == "developer"))) as $dev
        | ($e | map(select((.user | ascii_downcase) == ($fa | ascii_downcase)))) as $fl
        | "annotated login events since \($since): \($e | length)",
          "developer, all: \($dev | length)",
          "fleet account, all: \($fl | length)",
          "fleet account, authorize: \($fl | map(select(.uri | startswith("/oauth/authorize"))) | length)",
          "developer rows (stageTimestamp, kind, decision, status, stage, auditID):",
          ($dev[] | "  \(.at)  \(if (.uri | startswith("/oauth/authorize")) then (if (.uri | test("client_id=openshift-challenging-client")) then "cli" else "session" end) elif (.uri | startswith("/login")) then "credential" else "other" end)  \(.decision)  \(.status)  \(.stage)  \(.id)")' "${raw}"
      echo "developer rows' byte offsets in audit.log (the first byte of the event's line; grep -b on the auditID):"
      jq -r --arg since "${since}" 'select(.requestReceivedTimestamp >= $since and ((.annotations // {})["authentication.openshift.io/username"] == "developer")) | .auditID' "${raw}" \
        | sort -u | while read -r id; do
          printf '  %s  %s\n' "${id}" "$(grep -b -F "\"auditID\":\"${id}\"" "${raw}" | cut -d: -f1 | tr '\n' ' ')"
        done
    } > "${out}"
    ;;
  podlog)
    since="${3:?since (RFC 3339)}"
    raw=$(mktemp); trap 'rm -f "${raw}"' EXIT
    oc logs -n "${ns}" deploy/group-sync-dashboard -c dashboard --timestamps --since-time="${since}" > "${raw}"
    {
      echo "# oc logs -n ${ns} deploy/group-sync-dashboard -c dashboard --timestamps --since-time=${since}  (captured $(now))"
      echo "# lines in the window: $(wc -l < "${raw}" | tr -d ' ')"
      echo "# discovery, every line of ${entry} except its poll-cycle timing, and dashboard's audit-log lines:"
      grep -E " discovery |${entry}|gsd\.auditlog dashboard: " "${raw}" \
        | grep -v -e "${entry} poll cycle took" -e 'unmanaged-grant discovery' | redact || true
      echo "# '${entry}: crc: audit.log read' lines: $(grep -c "${entry}: crc: audit.log read" "${raw}" || true)"
      echo "# '${entry}: recorded' lines: $(grep -c "${entry}: recorded" "${raw}" || true)"
      for e in fleet-lookup fleet-ping fleet-login fleet-logout cluster-rejoin-failed cluster-rejoined; do
        echo "# ${e} lines: $(grep -c " ${e} " "${raw}" || true)"
      done
      echo "# lines naming the fleet account: $(grep -c -i -F "${fleet}" "${raw}" || true)"
      echo "# Traceback lines: $(grep -c 'Traceback' "${raw}" || true)"
      echo "# ERROR lines (the string anywhere): $(grep -c 'ERROR' "${raw}" || true)"
    } > "${out}"
    ;;
  *) echo "unknown kind ${kind}" >&2; exit 2 ;;
esac
echo "wrote ${out}"
