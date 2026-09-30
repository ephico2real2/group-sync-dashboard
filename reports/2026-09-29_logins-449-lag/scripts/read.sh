#!/usr/bin/env bash
# One read of GET /api/clusters/<id>/logins for the new entry (logins-449) and for the control (dashboard), through
# the dashboard pod's loopback as developer (X-Forwarded-User; the app's own trust boundary, no login, no audit event),
# appended to evidence/reads.jsonl as one JSON line.
#   read.sh <trigger> <login-start>     <login-start> is the instant before the one `oc login`, as %Y-%m-%dT%H:%M:%S.%fZ
# "The login's row" is a row with kind cli, outcome success, user developer and `at` at or after <login-start>.
set -euo pipefail
trigger="${1:?trigger}"; since="${2:?login start}"
here="$(cd "$(dirname "$0")/.." && pwd)"
ns=group-sync-dashboard
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
one() {  # $1 cluster id -> {"http":…, …} for that cluster
  local raw code body
  raw=$(oc exec -n "${ns}" deploy/group-sync-dashboard -c dashboard -- curl -s -w '\n%{http_code}' \
    -H 'X-Forwarded-User: developer' "http://127.0.0.1:8080/api/clusters/$1/logins?kind=cli&limit=50")
  code=$(printf '%s\n' "${raw}" | tail -n 1)
  body=$(printf '%s\n' "${raw}" | sed '$d')
  if [ "${code}" != 200 ]; then
    jq -cn --arg c "$1" --arg code "${code}" --arg b "${body:0:200}" '{cluster: $c, http: ($code | tonumber? // $code), body: $b}'
    return
  fi
  printf '%s' "${body}" | jq -c --arg c "$1" --arg since "${since}" '
    [.attempts[] | select(.kind == "cli" and .outcome == "success" and .user_name == "developer" and .at >= $since)] as $row
    | {cluster: $c, http: 200, scope, total, rows_returned: (.attempts | length),
       cli_rows_since_login: ([.attempts[] | select(.at >= $since)] | length),
       login_row: ($row | length > 0), login_row_at: ($row[0].at // null), login_row_observed_at: ($row[0].observed_at // null),
       login_row_detail: ($row[0].detail // null),
       last_read_at, capture_started_at, read_interval_seconds}'
}
at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
entry=$(one logins-449)
control=$(one dashboard)
jq -cn --arg at "${at}" --arg t "${trigger}" --argjson e "${entry}" --argjson d "${control}" \
  '{instant: $at, trigger: $t, entry: $e, control: $d}' | tee -a "${here}/evidence/reads.jsonl"
