#!/usr/bin/env bash
# Read-only snapshot of the lab's Epic C invariants (the walk's "start" and "end" measurements).
# Usage: scripts/snapshot.sh <label>   -> evidence/<label>-*.txt beside scripts/
# Every command here is a read (`oc get`, `oc exec … urlopen(GET)`); nothing is written to the cluster.
# No password, token or token-object name is printed: OAuthAccessTokens are counted, never listed by name.
set -euo pipefail
label="${1:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"   # the report folder
out="${here}/evidence"
mkdir -p "${out}"
ns=group-sync-dashboard
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"

run() {  # run <file> <command…>: the command line, then its output, into evidence/<label>-<file>.txt
  local file="${out}/${label}-$1.txt"; shift
  { printf '# %s\n# at %s\n' "$*" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"; bash -c "$*" 2>&1; } > "${file}"
}

run shared-rnd-secret \
  "oc get secrets -n ${ns} gsd-cluster-shared-rnd -o json | jq '{resourceVersion: .metadata.resourceVersion, uid: .metadata.uid, labels: .metadata.labels, annotations: (.metadata.annotations | with_entries(select(.key | startswith(\"groupsync-dashboard.io/\"))))}'"

run oauth-tokens \
  "oc get oauthaccesstokens.oauth.openshift.io -o json | jq -r '
     def n(f): [.items[] | select(f)] | length;
     \"all objects: \(.items | length)\",
     \"developer, openshift-challenging-client: \(n(.userName==\"developer\" and .clientName==\"openshift-challenging-client\"))\",
     \"developer, any client: \(n(.userName==\"developer\"))\",
     \"ocp-oauth-bind-serviceid, openshift-challenging-client: \(n(.userName==\"ocp-oauth-bind-serviceid\" and .clientName==\"openshift-challenging-client\"))\",
     \"ocp-oauth-bind-serviceid, any client: \(n(.userName==\"ocp-oauth-bind-serviceid\"))\",
     \"fleet account token creation instants: \([.items[] | select(.userName==\"ocp-oauth-bind-serviceid\") | .metadata.creationTimestamp] | sort | join(\", \"))\",
     \"developer challenging-client creation instants: \([.items[] | select(.userName==\"developer\" and .clientName==\"openshift-challenging-client\") | .metadata.creationTimestamp] | sort | join(\", \"))\",
     \"by client:\",
     (.items | group_by(.clientName) | map(\"  \(.[0].clientName): \(length)\") | .[])'"

run pvcs \
  "oc get persistentvolumeclaims -n ${ns} -o custom-columns='NAME:.metadata.name,UID:.metadata.uid,VOLUME:.spec.volumeName,CREATED:.metadata.creationTimestamp'"

run argo-application \
  "oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json | jq '{syncPolicy: .spec.syncPolicy, targetRevision: .spec.source.targetRevision, helm: .spec.source.helm, sync: .status.sync.status, syncedRevision: .status.sync.revision, health: .status.health.status}'"

run api-version \
  "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- python3.14 -c 'import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8080/api/version\").read().decode())'"

run oauth-lifetime \
  "oc get oauths.config.openshift.io cluster -o jsonpath='{.spec.tokenConfig}'; echo"

run leases \
  "oc get leases.coordination.k8s.io -n ${ns} -o json | jq '[.items[] | {name: .metadata.name, resourceVersion: .metadata.resourceVersion, labels: .metadata.labels, annotations: (.metadata.annotations // {} | with_entries(select(.key | startswith(\"groupsync-dashboard.io/\")))), holder: .spec.holderIdentity, leaseDurationSeconds: .spec.leaseDurationSeconds, renewTime: .spec.renewTime}]'"

run deployment \
  "oc get deployments.apps -n ${ns} group-sync-dashboard -o json | jq '{replicas: .spec.replicas, strategy: .spec.strategy.type, images: [.spec.template.spec.containers[] | {name, image}], observedGeneration: .status.observedGeneration}'; oc get pods -n ${ns} -l app.kubernetes.io/name=group-sync-dashboard -o custom-columns='NAME:.metadata.name,START:.status.startTime,IMAGEID:.status.containerStatuses[*].imageID'"

run config-fleet-keys \
  "oc get configmaps -n ${ns} group-sync-dashboard-config -o json | jq -r '.data[\"clusters.yaml\"]' | grep -n -E '^(fleet|discoveryIntervalSeconds|pollIntervalSeconds|requestTimeoutSeconds|replicaCount|leaderElection|clusterSecrets)' || true"

run configmap-onboarding \
  "oc get configmaps -n ${ns} -l 'groupsync-dashboard.io/config-type in (onboard,sideload)' -o name; echo \"(end of labelled onboarding ConfigMaps)\""

run cluster-secrets \
  "oc get secrets -n ${ns} -o json | jq -r '.items[] | select(.metadata.name | startswith(\"gsd-cluster-\")) | \"\(.metadata.name) rv=\(.metadata.resourceVersion) managed-by=\(.metadata.labels[\"groupsync-dashboard.io/managed-by\"] // .metadata.annotations[\"groupsync-dashboard.io/managed-by\"] // \"-\") lookup-account=\(.metadata.annotations[\"groupsync-dashboard.io/lookup-account\"] // \"-\") token-source=\(.metadata.annotations[\"groupsync-dashboard.io/token-source\"] // .metadata.labels[\"groupsync-dashboard.io/token-source\"] // \"-\")\"'"

echo "snapshot ${label} written to ${out}"
