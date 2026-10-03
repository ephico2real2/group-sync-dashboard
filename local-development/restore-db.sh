#!/usr/bin/env bash
# restore-db.sh — list the database copies the recovery pod can restore, and restore one (#302).
#
#   local-development/restore-db.sh --list
#   local-development/restore-db.sh --from-version <ID> [--yes]
#   options: --namespace <ns> (default group-sync-dashboard)
#            --release <name> (default group-sync-dashboard: the pods are found by app=<name>-recovery, or
#                              app=<name> on a chart before 0.65.0, as in the runbook)
#
# Runs on your laptop with oc, as you: nothing is added to any ServiceAccount; you need get on pods and
# create on pods/exec in the namespace. It refuses unless the release's one pod is in recovery mode (#303:
# recovery.enabled: true in the release's values file) with at least ten minutes of recovery.ttl left, then
# streams restore-db.py into that pod's dashboard container (oc exec -i ... python3.14 /dev/stdin): the work
# runs under the image the pod runs, the older one a rollback targets included, and nothing has to be shipped
# in it. --from-version shows what the restore discards and asks before it writes (--yes does not ask).
# docs/RUNBOOK_backup_restore.md, section 4, is the manual fallback; docs/specs/SPEC_E3_restore_db.md the design.
#
# Exit status: 0 done; 1 failed (the output says what changed); 2 refused, the pod is not ready for a
# restore; 3 refused, the copy; 4 not confirmed; 64 usage.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HELPER="${HERE}/restore-db.py"
NS=group-sync-dashboard
REL=group-sync-dashboard
MODE=""
ID=""
YES=0

usage() {
  sed -n '4,7p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --list)
      if [ -n "${MODE}" ]; then usage >&2; exit 64; fi          # one action per call
      MODE=list ;;
    --from-version|--namespace|--release)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then usage >&2; exit 64; fi
      case "$1" in
        --from-version)
          if [ -n "${MODE}" ]; then usage >&2; exit 64; fi
          MODE=restore; ID="$2" ;;
        --namespace) NS="$2" ;;
        --release) REL="$2" ;;
      esac
      shift ;;
    --yes) YES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 64 ;;
  esac
  shift
done
if [ -z "${MODE}" ]; then usage >&2; exit 64; fi

# The release's one pod, in recovery mode, with enough of its TTL left: read from the pod spec, no exec.
# Prints "<pod>\t<image>\t<time left>", or refuses (exit 2) with the reason and what to set.
# Both workloads' pods are listed (#532): an app pod still terminating beside the recovery pod makes two,
# and two are refused.
preflight() {
  local pods
  pods=$(oc get pods -n "${NS}" -l "app in (${REL},${REL}-recovery)" -o json) || return
  printf '%s' "${pods}" | python3 "${HELPER}" preflight --release "${REL}" --namespace "${NS}"
}

# The helper, streamed into the pod's dashboard container: it runs under that pod's image.
in_pod() {
  oc exec -i -n "${NS}" "${POD}" -c dashboard -- python3.14 /dev/stdin "$@" < "${HELPER}"
}

FOUND=$(preflight) || exit $?
IFS=$'\t' read -r POD IMAGE LEFT <<< "${FOUND}"
printf 'pod      %s · recovery mode, at least %s of its TTL left\nimage    %s\n' "${POD}" "${LEFT}" "${IMAGE}"

if [ "${MODE}" = list ]; then
  in_pod list
  exit 0
fi

# The plan. Its confirmation line binds the restore below to the copy's bytes and to the live set the plan
# describes: `restore` refuses either if it changed while the question was open.
CHECKED=$(in_pod check "${ID}") || exit $?
printf '%s\n' "${CHECKED}"
CONFIRMED=$(printf '%s\n' "${CHECKED}" | sed -n 's/^confirmation sha256=\([0-9a-f]\{64\}\) size=\([0-9][0-9]*\) live-sha256=\([0-9a-f]\{64\}\)$/\1 \2 \3/p')
if [ -z "${CONFIRMED}" ] || [ "$(printf '%s\n' "${CONFIRMED}" | wc -l | tr -d ' ')" -ne 1 ]; then
  echo "failed: the check printed no single confirmation line; nothing changed" >&2
  exit 1
fi
read -r SHA256 SIZE LIVE_SHA256 <<< "${CONFIRMED}"
if [ "${YES}" -ne 1 ]; then
  printf 'Restore %s over the live database? [y/N] ' "${ID}"
  answer=""
  read -r answer || true
  case "${answer}" in
    y|Y|yes|YES) ;;
    *) echo "not restored: not confirmed; nothing changed" >&2; exit 4 ;;
  esac
fi

# The answer may have taken a while: the pod and its TTL again, just before the session that writes.
AGAIN=$(preflight) || exit $?
if [ "${AGAIN%%$'\t'*}" != "${POD}" ]; then
  echo "refused: the recovery pod changed from ${POD} to ${AGAIN%%$'\t'*} since the check; run this again" >&2
  exit 2
fi
in_pod restore "${ID}" --expected-sha256 "${SHA256}" --expected-size "${SIZE}" --expected-live-sha256 "${LIVE_SHA256}"
