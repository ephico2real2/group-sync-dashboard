#!/usr/bin/env bash
# Wait for an Argo CD Application to reach Synced/Healthy after a source change, and say why it
# did not: the failed hook or resource, and the retry it is on. Used by release-crc.sh --argocd;
# usable on its own:  ./local-development/argocd-wait.sh group-sync-dashboard openshift-gitops
set -euo pipefail
APP="${1:?application name}"; NS="${2:-openshift-gitops}"; TIMEOUT="${3:-900}"
start=$(date +%s)
while :; do
  # The status is only meaningful once it was computed for THIS spec: after a source change
  # (a new revision, another values file) the controller still reports the PREVIOUS comparison
  # until it refreshes — measured: "Synced/Healthy" 11 s after a valueFiles patch, one second
  # before the sync for it started. status.sync.comparedTo.source is written in the same update
  # as sync.status, so equality with spec.source is the guard. `read` returns 1 at EOF without
  # a newline and set -e would end the script on it; the echo supplies the newline.
  read -r same sync health phase msg < <(oc get application "$APP" -n "$NS" -o json 2>/dev/null | python3 -c '
import json, sys
a = json.load(sys.stdin); st = a.get("status", {}); op = st.get("operationState", {})
same = json.dumps(a["spec"]["source"], sort_keys=True) == json.dumps(st.get("sync", {}).get("comparedTo", {}).get("source"), sort_keys=True)
print("current" if same else "stale", st.get("sync", {}).get("status", "?"), st.get("health", {}).get("status", "?"), op.get("phase", "?"), op.get("message", "").replace("\n", " ")[:100])
' 2>/dev/null; echo)
  printf '%s  %-10s %-12s %-10s %s\n' "$(date -u +%H:%M:%SZ)" "${sync:-?}" "${health:-?}" "${phase:-?}" "$([ "${same:-}" = stale ] && printf '(status is for the previous spec) ')${msg:-}"
  if [ "${same:-}" = current ] && [ "${sync:-}" = Synced ] && [ "${health:-}" = Healthy ] && [ "${phase:-}" = Succeeded ]; then
    echo "argocd  : ${APP} Synced/Healthy"; exit 0
  fi
  if [ $(( $(date +%s) - start )) -ge "$TIMEOUT" ]; then
    echo "ERROR: ${APP} did not reach Synced/Healthy in ${TIMEOUT}s" >&2
    oc get application "$APP" -n "$NS" -o json | jq -r '.status.operationState.syncResult.resources[]? | select(.status=="SyncFailed" or .hookPhase=="Failed") | "  \(.kind)/\(.name) \(.hookPhase // .status): \(.message)"' >&2
    oc get application "$APP" -n "$NS" -o json | jq -r '.status.resources[]? | select(.health.status != null and .health.status != "Healthy") | "  \(.kind)/\(.name) health=\(.health.status): \(.health.message // "")"' >&2
    exit 1
  fi
  sleep 15
done
