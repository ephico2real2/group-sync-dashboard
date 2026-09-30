#!/usr/bin/env bash
# The walk Secret, gsd-walk-developer-password in group-sync-dashboard, labelled with the run: `developer`'s password,
# read from `crc console --credentials` inside this process. reports/2026-09-27_epic-c-walk-432/scripts/walk_secret.sh's
# `create`, for this run; this walk never rotates it.
# The password is held in a variable of this process and reaches oc on its stdin (`printf`, a bash builtin, and
# `--from-file=password=/dev/stdin`), so it is never on any process's command line — the one change from the
# 2026-09-27 script, whose `--from-literal` put it in `oc`'s argv. Never echoed, never written to a file, a log or
# this script. `oc create`, never `oc apply`: apply would copy the value into
# the last-applied annotation. Prints the Secret's name, resourceVersion, uid and that (empty) annotation — never data.
# Usage: walk_secret.sh <label>   -> evidence/<label>-walk-secret.txt
set -euo pipefail
label="${1:?label}"
# shellcheck source-path=SCRIPTDIR source=lib.sh
. "$(dirname "$0")/lib.sh"
out="${EVIDENCE}/${label}-walk-secret.txt"
pw=$(crc console --credentials -o json | jq -r '.clusterConfig.developerCredentials.password')
if [ -z "${pw}" ] || [ "${pw}" = null ]; then echo "no password was read; nothing written" >&2; exit 1; fi
{
  printf '%s oc create secret %s -n %s (labelled %s): ' "$(now)" "${WALK_SECRET}" "${NS}" "${RUN_LABEL}"
  printf '%s' "${pw}" \
    | oc create secret generic "${WALK_SECRET}" -n "${NS}" --from-file=password=/dev/stdin --dry-run=client -o json \
    | jq --arg run "${RUN}" '.metadata.labels = {"walk.gsd.lab/run": $run}' \
    | oc create -f - -o jsonpath='{.metadata.name} resourceVersion={.metadata.resourceVersion} uid={.metadata.uid} last-applied={.metadata.annotations.kubectl\.kubernetes\.io/last-applied-configuration}{"\n"}'
} | tee -a "${out}"
unset pw
