#!/usr/bin/env bash
# #445's read-only captures. Nothing here writes to the cluster. Raw material (the whole pod log, the oauth-server
# audit log) lives OUTSIDE the repository and is removed; only derived, redacted lines reach evidence/.
#   capture.sh podlog <label> <raw>        evidence/<label>-podlog.txt: the Running dashboard pod's whole log (and its
#                                          previous container's, if it restarted), read ONCE — step 6 needs no follow,
#                                          so #310's streaming loops are not carried — derived: the leader lines, every
#                                          line naming developer's Lease, every fleet-*/self-login-* line, every
#                                          ERROR/CRITICAL/Traceback; sha256~ names redacted, the fleet account's name
#                                          replaced; with counts.
#   capture.sh audit <label> <since> [until]
#                                          evidence/<label>-audit.txt: challenging-client authorize records in
#                                          [since, until), derived: `developer`'s rows, the fleet account's COUNT, and
#                                          the count of records with no username. The raw log names every user and is
#                                          never kept: it lives in a mktemp directory removed on exit.
#                                          reports/2026-09-30_selflogin-renewal-310/scripts/capture.sh's `audit`,
#                                          unchanged (SPEC_S4c §3.12 step 6.4 cites the 2026-09-27 original).
set -euo pipefail
kind="${1:?podlog|audit}"
# shellcheck source-path=SCRIPTDIR source=lib.sh
. "$(dirname "$0")/lib.sh"

# The fleet account's name, as it appears in a line, replaced — by string, not by regex.
hide() { awk -v f="$1" 'f != "" { while ((i = index($0, f)) > 0) $0 = substr($0, 1, i - 1) "<the fleet account>" substr($0, i + length(f)) } { print }'; }

case "${kind}" in
  podlog)
    label="${2:?label}"; raw="${3:?raw dir}"; out="${EVIDENCE}/${label}-podlog.txt"; mkdir -p "${raw}"
    F=$(fleet_account) || { echo "the fleet account's Lease was not found" >&2; exit 2; }
    pod=$(dashboard_pod); [ -n "${pod}" ] || { echo "no Running dashboard pod" >&2; exit 2; }
    restarts=$(oc get pods -n "${NS}" "${pod}" -o jsonpath='{.status.containerStatuses[?(@.name=="dashboard")].restartCount}')
    oc logs --timestamps -n "${NS}" "${pod}" -c dashboard > "${raw}/podlog.raw"
    if [ "${restarts:-0}" != 0 ]; then
      oc logs --timestamps --previous -n "${NS}" "${pod}" -c dashboard > "${raw}/podlog.previous.raw" 2>&1 || true
      cat "${raw}/podlog.previous.raw" "${raw}/podlog.raw" > "${raw}/podlog.all"; mv "${raw}/podlog.all" "${raw}/podlog.raw"
    fi
    src="${raw}/podlog.raw"
    {
      echo "# oc logs --timestamps -n ${NS} ${pod} -c dashboard$( [ "${restarts:-0}" != 0 ] && echo ' (and --previous)'), read once at $(now); sha256~ names redacted; the fleet account's name replaced"
      echo "# container restarts: ${restarts:-?}; lines read: $(wc -l < "${src}" | tr -d ' '); first line at: $(head -1 "${src}" | cut -d' ' -f1)"
      grep -E "gsd\.leader |${DEV_LEASE}| fleet-[a-z-]+ | self-login-[a-z-]+ |Traceback| ERROR | CRITICAL " "${src}" | redact | hide "${F}" || true
      echo "# counts:"
      echo "#   leader lines (became leader / taking it): $(grep -c -E 'gsd\.leader .*(became leader|taking it)' "${src}" || true)"
      echo "#   lines naming ${DEV_LEASE} (the pod's own; step 6's processes write to the exec stream, not here): $(grep -c -F -- "${DEV_LEASE}" "${src}" || true)"
      echo "#   fleet-*/self-login-* lines: $(grep -c -E ' fleet-[a-z-]+ | self-login-[a-z-]+ ' "${src}" || true)"
      echo "#   fleet-*/self-login-* lines naming account=developer: $(grep -E ' fleet-[a-z-]+ | self-login-[a-z-]+ ' "${src}" | grep -c -E 'account=developer( |$)' || true)"
      echo "#   fleet-* lines naming the fleet account: $(grep -E ' fleet-[a-z-]+ ' "${src}" | grep -c -F -- "${F}" || true)"
      echo "#   ERROR/CRITICAL/Traceback lines: $(grep -c -E ' ERROR | CRITICAL |Traceback' "${src}" || true)"
    } > "${out}"
    rm -f "${raw}"/podlog.*
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
    # A read that failed, or a log that does not reach back to `since`, never counts as 0 authorizes.
    earliest=$(sed -E 's/^[^{]*//' "${tmp}/raw" | jq -r '.stageTimestamp? // empty' 2>/dev/null | sort | head -1 || true)
    if [ -z "${earliest}" ]; then
      echo "# READ FAILED at $(now): no oauth-server audit record was read (files: ${files:-none})" > "${out}"; cat "${out}" >&2; exit 2
    fi
    if [[ "${earliest}" > "${since}" ]]; then
      echo "# INCOMPLETE at $(now): the earliest audit record read is ${earliest}, after the window's start ${since}" > "${out}"; cat "${out}" >&2; exit 3
    fi
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
      echo "# audit records read: $(sed -E 's/^[^{]*//' "${tmp}/raw" | grep -c '^{' || true); the earliest at ${earliest}"
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
