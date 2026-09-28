#!/usr/bin/env bash
# Watches the fleet Lease for the length of the walk and writes one line per change to evidence/lease-watch.txt:
# the instant it was seen, the watch event, resourceVersion, holder, acquire/renew and the ping-last-* fields.
# A claim and its release last about a second, so a single `oc get` would miss the holder; the watch does not.
# A read (`oc get -w`); stop it with a signal once the walk's end state is captured.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
out="${here}/evidence/lease-watch.txt"
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
echo "# oc get leases.coordination.k8s.io gsd-fleet-666f1ba7f2fdead0 -n group-sync-dashboard -w --output-watch-events -o json" > "${out}"
echo "# started $(date -u +%Y-%m-%dT%H:%M:%SZ); holderIdentity names the dashboard pod, never the account" >> "${out}"
oc get leases.coordination.k8s.io gsd-fleet-666f1ba7f2fdead0 -n group-sync-dashboard -w --output-watch-events -o json \
  | jq --unbuffered -c '{event: .type, resourceVersion: .object.metadata.resourceVersion,
      holderIdentity: .object.spec.holderIdentity, acquireTime: .object.spec.acquireTime, renewTime: .object.spec.renewTime,
      ping: (.object.metadata.annotations | with_entries(select(.key | test("ping-last-"))))}' \
  | while IFS= read -r line; do printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${line}" >> "${out}"; done
