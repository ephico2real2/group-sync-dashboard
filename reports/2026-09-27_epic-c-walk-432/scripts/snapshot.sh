#!/usr/bin/env bash
# Read-only snapshot of the lab's invariants for the #432 walk: evidence/<label>-<kind>.txt beside scripts/.
# Usage: snapshot.sh <label>
# Every command is a read (`oc get`, `oc auth can-i`, `oc exec … urlopen(GET)` on the pod's loopback). Nothing is
# written to the cluster. No password, token or token-object name is printed: OAuthAccessTokens are counted and
# dated, never named. Lease digests (`ping-digest`, the `refused` entry's `digest`) are shown as <redacted>; the
# byte-identity check is the sha256 of the whole unredacted object (`oc get … -o json | jq -S -c .`).
set -euo pipefail
label="${1:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"   # the report folder
out="${here}/evidence"
mkdir -p "${out}"
ns=group-sync-dashboard
run=epic-c-walk-432-2026-09-27
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"

run() {  # run <kind> <command…>: the command line, the instant, then its output
  local file="${out}/${label}-$1.txt"; shift
  { printf '# %s\n# at %s\n' "$*" "$(date -u +%Y-%m-%dT%H:%M:%SZ)"; bash -c "$*" 2>&1 | sed -E 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g'; } > "${file}"
}

run tokens \
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
  "oc get persistentvolumeclaims -n ${ns} -o json | jq -r '.items[] | \"\(.metadata.name) uid=\(.metadata.uid) volume=\(.spec.volumeName) created=\(.metadata.creationTimestamp) resource-policy=\(.metadata.annotations[\"helm.sh/resource-policy\"] // \"-\") argocd-sync-options=\(.metadata.annotations[\"argocd.argoproj.io/sync-options\"] // \"-\")\"'"

run argo \
  "oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json | jq '{syncPolicy: .spec.syncPolicy, targetRevision: .spec.source.targetRevision, helm: .spec.source.helm, sync: .status.sync.status, syncedRevision: .status.sync.revision, health: .status.health.status, operation: .status.operationState.phase}' || echo '(no Application)'"

run version \
  "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- python3.14 -c 'import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8080/api/version\").read().decode())'; oc get deployments.apps -n ${ns} group-sync-dashboard -o json | jq -c '{replicas: .spec.replicas, strategy: .spec.strategy.type, images: [.spec.template.spec.containers[] | {name, image}], chart: .metadata.labels[\"helm.sh/chart\"], managedBy: .metadata.labels[\"app.kubernetes.io/managed-by\"]}'; oc get pods -n ${ns} -l app.kubernetes.io/name=group-sync-dashboard -o json | jq -r '.items[] | \"pod \(.metadata.name) started \(.status.startTime) \([.status.containerStatuses[] | \"\(.name)=\(.imageID | split(\"@\") | last)\"] | join(\" \"))\"'"

run leases \
  "for l in \$(oc get leases.coordination.k8s.io -n ${ns} -o name | grep '/gsd-fleet-'); do
     obj=\$(oc get -n ${ns} \"\${l}\" -o json)
     printf '%s' \"\${obj}\" | jq '{name: .metadata.name, resourceVersion: .metadata.resourceVersion, uid: .metadata.uid, labels: .metadata.labels,
         annotations: (.metadata.annotations // {} | with_entries(select(.key | startswith(\"groupsync-dashboard.io/\")))
           | (if has(\"groupsync-dashboard.io/ping-digest\") then .[\"groupsync-dashboard.io/ping-digest\"] = \"<redacted>\" else . end)
           | (if has(\"groupsync-dashboard.io/refused\") then .[\"groupsync-dashboard.io/refused\"] |= (fromjson? // {} | if has(\"digest\") then .digest = \"<redacted>\" else . end | tojson) else . end)),
         spec: .spec}'
     echo \"sha256 of the whole unredacted object (jq -S -c .): \$(printf '%s' \"\${obj}\" | jq -S -c . | shasum -a 256 | cut -d' ' -f1)\"
   done; echo \"(fleet-account Leases: \$(oc get leases.coordination.k8s.io -n ${ns} -l groupsync-dashboard.io/lease-type=fleet-account -o name | wc -l | tr -d ' '))\""

run secrets \
  "oc get secrets -n ${ns} -l groupsync-dashboard.io/secret-type=cluster -o json | jq -r '.items[] | \"\(.metadata.name) uid=\(.metadata.uid) rv=\(.metadata.resourceVersion) managed-by=\(.metadata.annotations[\"groupsync-dashboard.io/managed-by\"] // \"-\") token-source=\(.metadata.annotations[\"groupsync-dashboard.io/token-source\"] // \"-\") lookup-account=\(.metadata.annotations[\"groupsync-dashboard.io/lookup-account\"] // \"-\") config-keys=\((.data.config // \"\" | @base64d | fromjson? // {}) | keys | join(\",\")) ldapConnectionBootstrap=\((.data.config // \"\" | @base64d | fromjson? // {}).ldapConnectionBootstrap // \"-\")\"'"

run config \
  "cm=\$(oc get configmaps -n ${ns} group-sync-dashboard-config -o json)
   echo \"ConfigMap group-sync-dashboard-config resourceVersion \$(printf '%s' \"\${cm}\" | jq -r .metadata.resourceVersion); clusters.yaml: the fleet, cadence and election keys, then the whole clusters list\"
   printf '%s' \"\${cm}\" | jq -r '.data[\"clusters.yaml\"]' | awk '/^clusters:/{p=1} p || /^(fleet|saTokenLookup|discoveryIntervalSeconds|pollIntervalSeconds|requestTimeoutSeconds|replicaCount|leaderElection|clusterSecrets)/'
   echo \"onboarding ConfigMaps (label key groupsync-dashboard.io/config-type): \$(oc get configmaps -n ${ns} -l groupsync-dashboard.io/config-type -o name | wc -l | tr -d ' ')\""

run cani \
  "echo \"ServiceAccount get openshift-config/ldap-oauth-bind-secret: \$(oc auth can-i get secrets/ldap-oauth-bind-secret -n openshift-config --as=system:serviceaccount:${ns}:group-sync-dashboard || true)\"
   echo \"ServiceAccount get ${ns}/gsd-walk-developer-password: \$(oc auth can-i get secrets/gsd-walk-developer-password -n ${ns} --as=system:serviceaccount:${ns}:group-sync-dashboard || true)\"
   echo \"developer get group-sync-operator/group-sync-dashboard-cluster-poller-token: \$(oc auth can-i get secrets/group-sync-dashboard-cluster-poller-token -n group-sync-operator --as=developer || true)\"
   echo \"developer list groups.user.openshift.io (the poller ClusterRole): \$(oc auth can-i list groups.user.openshift.io --as=developer 2>/dev/null || true)\"
   echo \"developer update clusterrolebindings (the dashboard's cluster-admin tier): \$(oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer 2>/dev/null || true)\"
   oc get roles.rbac.authorization.k8s.io,rolebindings.rbac.authorization.k8s.io -n openshift-config -o json | jq -r '.items[] | select(.metadata.name | test(\"group-sync-dashboard|gsd-walk\")) | \"openshift-config \(.kind) \(.metadata.name)\"'"

run oauth \
  "echo \"oauths.config.openshift.io/cluster spec.tokenConfig: \$(oc get oauths.config.openshift.io cluster -o jsonpath='{.spec.tokenConfig}')\""

run walkobjects \
  "echo 'objects labelled walk.gsd.lab/run=${run}:'
   oc get secrets,roles.rbac.authorization.k8s.io,rolebindings.rbac.authorization.k8s.io -A -l walk.gsd.lab/run=${run} -o name
   oc get clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io -l walk.gsd.lab/run=${run} -o name
   echo 'the product-made walk objects, by name:'
   oc get secrets -n ${ns} gsd-cluster-walk-lookup -o name 2>&1 | sed 's/^Error from server (NotFound): //'
   oc get leases.coordination.k8s.io -n ${ns} gsd-fleet-88fa0d759f845b47 -o name 2>&1 | sed 's/^Error from server (NotFound): //'
   echo 'the walk Secret, by name:'
   oc get secrets -n ${ns} gsd-walk-developer-password -o name 2>&1 | sed 's/^Error from server (NotFound): //'"

echo "snapshot ${label} written to ${out}"
