#!/usr/bin/env bash
# The #449 measurement end to end: when does a newly added entry's Logins show a login made just after it was added?
#   KUBECONFIG=<the lab kubeconfig> reports/2026-09-29_logins-449-lag/scripts/run.sh
# Order: exit trap (deletes everything carrying the run's label, logs the throwaway login out, removes the temp dir),
# before captures, the Secret, the ONE login, then a read of both entries' Logins after every audit read of the new
# entry (and after each of the control's until its row shows), until the row shows on the new entry or the new entry
# has made BOUND_READS audit reads; then logout, delete, the wait for discovery's removal, and the after captures.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
s="${here}/scripts"; e="${here}/evidence"
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=logins-449-2026-09-29
entry=logins-449
# 3 audit cadences after the first read is the 4th read (the brief's bound); two more are read to see past it.
BOUND_READS=6
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
say() { printf '%s %s\n' "$(now)" "$*" | tee -a "${e}/run-output.txt"; }
tmp=$(mktemp -d)

# shellcheck disable=SC2329  # invoked by the EXIT trap
cleanup() {
  { printf '# exit trap at %s\n' "$(now)"
    if [ -s "${tmp}/kubeconfig" ]; then KUBECONFIG="${tmp}/kubeconfig" oc logout 2>&1 || true; fi
    oc delete secrets -n "${ns}" -l "${run_label}" --ignore-not-found 2>&1
    rm -rf "${tmp}" && echo "removed the throwaway directory"; } >> "${e}/trap-delete.txt"
}
trap cleanup EXIT

logs() { oc logs -n "${ns}" deploy/group-sync-dashboard -c dashboard --timestamps --since-time="$1"; }
count() { logs "$1" | grep -c -- "$2" || true; }

T0=$(now); echo "${T0}" > "${e}/start-instant.txt"; say "the run began: ${T0}"
for k in version pvcs sharedqa lease tokens secret kubeconfig auditfile; do "${s}/capture.sh" "${k}" before; done

"${s}/lab.sh" secret
created=$(date +%s); say "the Secret was created"

L0=$(python3 -c 'import datetime; print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))')
echo "${L0}" > "${e}/login-start-instant.txt"
"${s}/lab.sh" login "${tmp}"
say "the one login was made (started ${L0})"
for k in tokens kubeconfig auditfile; do "${s}/capture.sh" "${k}" login; done
"${s}/capture.sh" audit login "${T0}"

seen_e=0; seen_d=0; control_row=false; entry_row=false; first_read=""
while :; do
  n_e=$(count "${T0}" "${entry}: crc: audit.log read")
  n_d=$(count "${L0%.*}Z" "gsd.auditlog dashboard: crc: audit.log read")
  if [ "${n_e}" -gt "${seen_e}" ]; then
    seen_e=${n_e}; [ -n "${first_read}" ] || first_read=$(date +%s)
    sleep 5
    line=$("${s}/read.sh" "entry audit read ${n_e}" "${L0}")
    say "after ${entry}'s audit read ${n_e}: $(printf '%s' "${line}" | jq -c '{entry_row: .entry.login_row, entry_http: .entry.http, control_row: .control.login_row}')"
    entry_row=$(printf '%s' "${line}" | jq -r '.entry.login_row // false')
    control_row=$(printf '%s' "${line}" | jq -r '.control.login_row // false')
    [ "${entry_row}" = true ] && { say "the row is on ${entry} after its audit read ${n_e}"; break; }
    [ "${n_e}" -ge "${BOUND_READS}" ] && { say "bound: ${n_e} audit reads of ${entry} and no row"; break; }
  elif [ "${control_row}" != true ] && [ "${n_d}" -gt "${seen_d}" ]; then
    seen_d=${n_d}
    sleep 5
    line=$("${s}/read.sh" "control audit read ${n_d} since the login" "${L0}")
    control_row=$(printf '%s' "${line}" | jq -r '.control.login_row // false')
    say "after dashboard's audit read ${n_d} since the login: control_row=${control_row}"
  fi
  if [ -z "${first_read}" ] && [ $(( $(date +%s) - created )) -gt 420 ]; then
    say "no audit read of ${entry} within 420 s of the Secret"; break
  fi
  if [ -n "${first_read}" ] && [ $(( $(date +%s) - first_read )) -gt $(( BOUND_READS * 60 + 60 )) ]; then
    say "wall-clock bound after the first read"; break
  fi
  sleep 5
done
"${s}/capture.sh" podlog reads "${T0}"
"${s}/capture.sh" audit reads "${T0}"

"${s}/lab.sh" logout "${tmp}"
"${s}/lab.sh" delete
say "logged out and deleted by label"
for k in tokens secret; do "${s}/capture.sh" "${k}" deleted; done
for _ in $(seq 70); do
  if logs "${T0}" | grep ' discovery ' | grep -q "removed=[^ ]*${entry}"; then break; fi
  sleep 5
done
say "discovery removed ${entry}: $(logs "${T0}" | grep ' discovery ' | grep -c "removed=[^ ]*${entry}" || true) line(s)"
for k in version pvcs sharedqa lease tokens secret kubeconfig; do "${s}/capture.sh" "${k}" after; done
"${s}/capture.sh" audit after "${T0}"
"${s}/capture.sh" podlog after "${T0}"
say "done"
