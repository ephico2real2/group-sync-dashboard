#!/usr/bin/env bash
# Waits for gsd-cluster-gitops-404 to exist (`present`) or to be gone (`absent`), reading it every 5 s, and writes
# evidence/<label>-wait.txt: the instant the wait began (<t0>, RFC 3339: the apply or the delete), the instant the
# state was seen, and the seconds between. Exit 1 on the timeout. A read only.
#   wait-secret.sh present|absent <label> <t0> <timeout seconds>
set -euo pipefail
want="${1:?present|absent}"; label="${2:?label}"; t0="${3:?t0}"; limit="${4:?timeout}"
here="$(cd "$(dirname "$0")/.." && pwd)"
out="${here}/evidence/${label}-wait.txt"
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
epoch() { date -j -u -f %Y-%m-%dT%H:%M:%SZ "$1" +%s; }   # BSD date (macOS)
start=$(epoch "${t0}")
while :; do
  if oc get secrets gsd-cluster-gitops-404 -n group-sync-dashboard -o name >/dev/null 2>&1; then state=present; else state=absent; fi
  seen=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  if [ "${state}" = "${want}" ]; then
    printf 'wanted %s; from %s; seen %s; elapsed %ss (read every 5 s)\n' "${want}" "${t0}" "${seen}" "$(( $(epoch "${seen}") - start ))" > "${out}"
    exit 0
  fi
  if [ $(( $(epoch "${seen}") - start )) -ge "${limit}" ]; then
    printf 'wanted %s; from %s; still %s at %s; gave up after %ss\n' "${want}" "${t0}" "${state}" "${seen}" "${limit}" > "${out}"
    exit 1
  fi
  sleep 5
done
