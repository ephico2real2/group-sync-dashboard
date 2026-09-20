#!/usr/bin/env bash
# Wait for an Argo CD Application to reach Synced/Healthy after a source change, and say why it
# did not: the failed hook or resource, and the retry it is on. Used by release-crc.sh --argocd;
# usable on its own:  ./local-development/argocd-wait.sh group-sync-dashboard openshift-gitops [timeout] [revision]
#
# The status is only meaningful once it was computed for THIS spec: after a source change (a new
# revision, another values file) the controller still reports the PREVIOUS comparison until it
# refreshes — measured: "Synced/Healthy" 11 s after a valueFiles patch, one second before the sync
# for it started. status.sync.comparedTo.source is written in the same status update as
# sync.status, so equality with spec.source is the guard. It is not enough for a symbolic
# targetRevision (`main`) that has not changed while the branch moved: the spec is the same, the
# comparison is current, and the status is the old commit's — so the caller passes the commit it
# expects and status.sync.revision must match it (either may be the short form).
set -euo pipefail
APP="${1:?application name}"; NS="${2:-openshift-gitops}"; TIMEOUT="${3:-900}"; EXPECTED="${4:-}"
INTERVAL="${ARGOCD_WAIT_INTERVAL:-15}"
start=$(date +%s)
while :; do
  # A failed `oc` (the API away for a moment) must not end the waiter: under pipefail the process
  # substitution would exit before its echo, `read` would fail at EOF and set -e would take the
  # script with it, silently. So the pipeline is allowed to fail and the line is then empty.
  read -r same rev_ok sync health phase revision msg < <( (oc get application "$APP" -n "$NS" -o json | python3 -c '
import json, sys
expected = sys.argv[1]
a = json.load(sys.stdin); st = a.get("status", {}); sy = st.get("sync", {}); op = st.get("operationState", {})
same = json.dumps(a["spec"]["source"], sort_keys=True) == json.dumps(sy.get("comparedTo", {}).get("source"), sort_keys=True)
rev = sy.get("revision", "")
rev_ok = not expected or (bool(rev) and (expected.startswith(rev) or rev.startswith(expected)))
print("current" if same else "stale", "rev-ok" if rev_ok else "rev-old", sy.get("status", "?"), st.get("health", {}).get("status", "?"),
      op.get("phase", "?"), rev or "?", op.get("message", "").replace("\n", " ")[:100])
' "$EXPECTED") 2>/dev/null || true; echo)
  note=""
  [ -z "${same:-}" ] && note="(application status unavailable) "
  [ "${same:-}" = stale ] && note="(status is for the previous spec) "
  [ "${rev_ok:-}" = rev-old ] && note="${note}(revision ${revision:-?}, want ${EXPECTED:0:10}) "
  printf '%s  %-10s %-12s %-10s %s%s\n' "$(date -u +%H:%M:%SZ)" "${sync:-?}" "${health:-?}" "${phase:-?}" "$note" "${msg:-}"
  if [ "${same:-}" = current ] && [ "${rev_ok:-}" = rev-ok ] && [ "${sync:-}" = Synced ] && [ "${health:-}" = Healthy ] && [ "${phase:-}" = Succeeded ]; then
    echo "argocd  : ${APP} Synced/Healthy"; exit 0
  fi
  if [ $(( $(date +%s) - start )) -ge "$TIMEOUT" ]; then
    echo "ERROR: ${APP} did not reach Synced/Healthy in ${TIMEOUT}s" >&2
    oc get application "$APP" -n "$NS" -o json 2>/dev/null | jq -r '.status.operationState.syncResult.resources[]? | select(.status=="SyncFailed" or .hookPhase=="Failed") | "  \(.kind)/\(.name) \(.hookPhase // .status): \(.message)"' >&2 || true
    oc get application "$APP" -n "$NS" -o json 2>/dev/null | jq -r '.status.resources[]? | select(.health.status != null and .health.status != "Healthy") | "  \(.kind)/\(.name) health=\(.health.status): \(.health.message // "")"' >&2 || true
    exit 1
  fi
  sleep "$INTERVAL"
done
