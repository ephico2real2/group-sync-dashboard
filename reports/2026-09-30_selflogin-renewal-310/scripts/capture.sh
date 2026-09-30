#!/usr/bin/env bash
# #310 Part A's read-only captures. Nothing here writes to the cluster. Raw material (the whole pod log, the metrics
# samples, the oauth-server audit log) lives in <raw>, a directory OUTSIDE the repository that scripts/run.sh removes;
# only derived, redacted lines reach evidence/.
#   capture.sh stream-start <raw>          background: `oc logs -f --timestamps` of the Running dashboard pod into
#                                          <raw>/podlog.raw, and a /metrics sample every 15 s into <raw>/metrics.raw
#                                          (the walk cluster's and the host's two gauges). PIDs in <raw>/*.pid.
#   capture.sh stream-stop <raw>           stops both.
#   capture.sh podlog <label> <raw>        evidence/<label>-podlog.txt: every fleet-login/-logout, self-login-* and
#                                          fleet-credential-* line, every `polled walk-self-login:` line, every failed
#                                          poll of the walk cluster, every ERROR/Traceback; sha256~ names redacted;
#                                          counts, and how many captured lines name the fleet account (a count only).
#   capture.sh metrics <label> <raw>       evidence/<label>-metrics.txt: the samples, as taken.
#   capture.sh audit <label> <since> [until]
#                                          evidence/<label>-audit.txt: challenging-client authorize records in
#                                          [since, until), derived: `developer`'s rows, the fleet account's COUNT, and
#                                          the count of records with no username. The raw log names every user and is
#                                          never kept: it lives in a mktemp directory removed on exit.
set -euo pipefail
kind="${1:?stream-start|stream-stop|podlog|metrics|audit}"
# shellcheck source-path=SCRIPTDIR source=lib.sh
. "$(dirname "$0")/lib.sh"

case "${kind}" in
  stream-start)
    raw="${2:?raw dir}"; mkdir -p "${raw}"
    pod=$(dashboard_pod); [ -n "${pod}" ] || { echo "no Running dashboard pod" >&2; exit 2; }
    echo "${pod}" > "${raw}/pod"
    # A follow that ends (the API server closed it, the network blinked) is resumed from the last instant it wrote, on
    # whichever pod is Running then; a line at that instant may arrive twice, and `podlog` drops exact duplicates.
    # Both loops run with errexit OFF: a subshell inherits `set -e`, and with it a follow that exits non-zero — or
    # stream-stop killing it — ended the loop instead of resuming it (review of phase 1, OB3).
    (
      set +e
      since=""
      while :; do
        p=$(dashboard_pod); [ -n "${p}" ] && echo "${p}" > "${raw}/pod"
        oc logs -f --timestamps -n "${NS}" "${p:-${pod}}" -c dashboard ${since:+--since-time="${since}"} \
          >> "${raw}/podlog.raw" 2>> "${raw}/podlog.err"
        echo "$(now) the follow ended; resuming" >> "${raw}/podlog.err"
        since=$(tail -1 "${raw}/podlog.raw" | cut -d' ' -f1 | sed -E 's/\.[0-9]+Z$/Z/')
        sleep 2
      done
    ) &
    echo $! > "${raw}/podlog.pid"
    (
      set +e
      while :; do
        # Stamped BEFORE the read: a sample stamped at or after an instant was read after it (analyse.py relies on it).
        t=$(now)
        m=$(metrics 2>/dev/null | grep -E "^gsd_cluster_(up|last_poll_timestamp_seconds)\{cluster=\"(${WALK_CLUSTER}|dashboard)\"\}" || true)
        printf '%s\n' "${m:-(no sample)}" | sed "s/^/${t} /" >> "${raw}/metrics.raw"
        sleep 15
      done
    ) &
    echo $! > "${raw}/metrics.pid"
    say "streaming ${pod}'s log and sampling /metrics every 15 s into ${raw}"
    ;;
  stream-stop)
    raw="${2:?raw dir}"
    for p in podlog metrics; do
      # The loop's children (the oc logs follow, a sleep) first, then the loop itself: the background subshells share
      # the caller's process group, so each is stopped by PID. Either may be gone already; neither ends this loop early.
      if [ -f "${raw}/${p}.pid" ]; then
        pkill -P "$(cat "${raw}/${p}.pid")" 2>/dev/null || true
        kill "$(cat "${raw}/${p}.pid")" 2>/dev/null || true
      fi
      rm -f "${raw}/${p}.pid"
    done
    say "streams stopped"
    ;;
  podlog)
    label="${2:?label}"; raw="${3:?raw dir}"; out="${EVIDENCE}/${label}-podlog.txt"
    F=$(fleet_account) || { echo "the fleet account's Lease was not found" >&2; exit 2; }
    src="${raw}/podlog.raw"
    {
      echo "# oc logs -f --timestamps -n ${NS} $(cat "${raw}/pod") -c dashboard, streamed; captured $(now); sha256~ names redacted"
      echo "# lines in the stream: $(wc -l < "${src}" | tr -d ' '); stream errors: $(wc -l < "${raw}/podlog.err" | tr -d ' ')"
      awk '!seen[$0]++' "${src}" > "${src}.dedup" && mv "${src}.dedup" "${src}"
      grep -E " (fleet-login|fleet-login-failed|fleet-login-refused|fleet-logout|fleet-logout-failed|self-login-renewed|self-login-failed|fleet-credential-suspended|fleet-state-unavailable) .*cluster=${WALK_CLUSTER}( |$)| fleet-credential-suspended |polled ${WALK_CLUSTER}:|cluster-unreachable .*cluster=${WALK_CLUSTER}( |$)|${WALK_CLUSTER}: (polling started|self-login raised)|Traceback| ERROR | CRITICAL " "${src}" \
        | redact || true
      echo "# counts:"
      # `clusters?=`: fleet-credential-suspended names its clusters in `clusters=<a,b,…>` (gsd/selflogin.py#_suspend).
      for e in fleet-login fleet-login-failed fleet-login-refused fleet-logout fleet-logout-failed self-login-renewed self-login-failed fleet-credential-suspended; do
        echo "#   '${e} … cluster=${WALK_CLUSTER}' lines: $(grep -c -E " ${e} .*clusters?=([^ ]*,)?${WALK_CLUSTER}(,| |$)" "${src}" || true)"
      done
      echo "#   'polled ${WALK_CLUSTER}:' lines: $(grep -c "polled ${WALK_CLUSTER}:" "${src}" || true)"
      echo "#   failed polls of ${WALK_CLUSTER}: $(grep -c -E "cluster-unreachable .*cluster=${WALK_CLUSTER}( |$)" "${src}" || true)"
      echo "#   ERROR/CRITICAL/Traceback lines: $(grep -c -E ' ERROR | CRITICAL |Traceback' "${src}" || true)"
      echo "#   fleet-* lines in the whole stream that name the fleet account: $(grep -E ' fleet-[a-z-]+ ' "${src}" | grep -c -F -- "${F}" || true)"
    } > "${out}"
    echo "wrote ${out}"
    ;;
  metrics)
    label="${2:?label}"; raw="${3:?raw dir}"; out="${EVIDENCE}/${label}-metrics.txt"
    { echo "# /metrics via the pod proxy every 15 s: <instant> <sample>"; cat "${raw}/metrics.raw"; } > "${out}"
    echo "wrote ${out}"
    ;;
  audit)
    label="${2:?label}"; since="${3:?since (ISO-8601 UTC)}"; until="${4:-9999-12-31T00:00:00Z}"
    out="${EVIDENCE}/${label}-audit.txt"
    F=$(fleet_account) || { echo "the fleet account's Lease was not found" >&2; exit 2; }
    tmp=$(mktemp -d); trap 'rm -rf "${tmp}"' EXIT
    files=$(oc adm node-logs --role=master --path=oauth-server/ | awk '{print $2}' | grep -E '^audit.*\.log$' || true)
    : > "${tmp}/raw"
    for f in ${files}; do oc adm node-logs --role=master --path="oauth-server/${f}" >> "${tmp}/raw"; done
    sed -E 's/^[^{]*//' "${tmp}/raw" | jq -r --arg since "${since}" --arg until "${until}" --arg fleet "${F}" '
        select(.stage? == "ResponseComplete" and (.requestURI // "" | startswith("/oauth/authorize"))
               and (.requestURI | test("client_id=openshift-challenging-client"))
               and .stageTimestamp >= $since and .stageTimestamp < $until)
        | (.annotations["authentication.openshift.io/username"] // "") as $u
        | (.annotations["authentication.openshift.io/decision"] // "-") as $d
        | if $u == "developer" then "\(.stageTimestamp) user=developer decision=\($d) code=\(.responseStatus.code)"
          elif $u == $fleet then "\(.stageTimestamp) user=(the fleet account) decision=\($d) code=\(.responseStatus.code)"
          elif $u == "" then "\(.stageTimestamp) user=(none) decision=\($d) code=\(.responseStatus.code)"
          else empty end' 2>/dev/null | sort > "${tmp}/rows" || true
    {
      echo "# oc adm node-logs --role=master --path=oauth-server/<$(tr '\n' ',' <<<"${files}")>  (captured $(now)), DERIVED:"
      echo "# ResponseComplete GET /oauth/authorize?client_id=openshift-challenging-client in [${since}, ${until})"
      echo "# audit records read: $(sed -E 's/^[^{]*//' "${tmp}/raw" | grep -c '^{' || true)"
      grep ' user=developer ' "${tmp}/rows" || true
      echo "# counts in [${since}, ${until}):"
      for d in allow deny error; do
        echo "#   developer ${d}: $(grep -c " user=developer decision=${d} " "${tmp}/rows" || true)"
      done
      echo "#   developer authorize records, any decision: $(grep -c ' user=developer ' "${tmp}/rows" || true)"
      echo "#   the fleet account's authorize records, any decision: $(grep -c ' user=(the fleet account) ' "${tmp}/rows" || true)"
      grep ' user=(the fleet account) ' "${tmp}/rows" | sed 's/^/#   the fleet account: /' || true
      echo "#   records with no username (an unauthenticated challenge a client may send first): $(grep -c 'user=(none)' "${tmp}/rows" || true)"
    } > "${out}"
    echo "wrote ${out}"
    ;;
  *) echo "unknown kind ${kind}" >&2; exit 2 ;;
esac
