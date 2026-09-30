#!/usr/bin/env bash
# Local/read-only watcher used by run.sh: record when the exact walk pod UID is gone. It writes only its local output.
set -euo pipefail
pod_name="${1:?pod name}"
pod_uid="${2:?pod uid}"
out="${3:?output file}"
timeout_seconds="${4:-1200}"
# shellcheck source-path=SCRIPTDIR source=lib.sh
. "$(dirname "$0")/lib.sh"
wait_for_pod_end "${pod_name}" "${pod_uid}" "${out}" "${timeout_seconds}"
