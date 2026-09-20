#!/usr/bin/env bash
# Wait for an Argo CD Application to reach Synced/Healthy after a source change, and say why it
# did not: the failed hook or resource, and the retry it is on. Used by release-crc.sh --argocd;
# usable on its own:  ./local-development/argocd-wait.sh group-sync-dashboard openshift-gitops
set -euo pipefail
APP="${1:?application name}"; NS="${2:-openshift-gitops}"; TIMEOUT="${3:-900}"
start=$(date +%s)
while :; do
  read -r sync health phase msg < <(oc get application "$APP" -n "$NS" -o jsonpath='{.status.sync.status} {.status.health.status} {.status.operationState.phase} {.status.operationState.message}' 2>/dev/null || echo "")
  printf '%s  %-10s %-12s %-10s %s\n' "$(date -u +%H:%M:%SZ)" "${sync:-?}" "${health:-?}" "${phase:-?}" "$(printf '%s' "${msg:-}" | cut -c1-100)"
  if [ "${sync:-}" = Synced ] && [ "${health:-}" = Healthy ] && [ "${phase:-}" = Succeeded ]; then
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
