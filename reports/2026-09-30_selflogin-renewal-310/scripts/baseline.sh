#!/usr/bin/env bash
# The lab's invariants for #310 Part A, read-only: evidence/<label>-baseline.txt. Run at the start, and again at the
# end of phase 2; the two files are compared by scripts/compare_baselines.sh.
# Usage: baseline.sh <label> [--get-only]
#   --get-only  `oc get` and `oc get --raw` only: skips /api/version (it needs `oc exec`: the app answers on the pod's
#               loopback only) and the `oc auth can-i` reads (each is a SubjectAccessReview POST that stores nothing).
#               Phase 1 was held to `oc get`, so its baseline used it.
# Otherwise the commands are `oc get`, `oc get --raw`, `oc auth can-i` and that one `oc exec` of a GET. Nothing is
# written to the cluster. No password,
# token or token-object name is printed: OAuthAccessTokens are counted and dated, never named; Secrets are read as
# name and resourceVersion columns only; the fleet account's username lives in a variable and is never printed.
set -euo pipefail
label="${1:?label}"; full=true; [ "${2:-}" = --get-only ] && full=false
# shellcheck source-path=SCRIPTDIR source=lib.sh
. "$(dirname "$0")/lib.sh"
out="${EVIDENCE}/${label}-baseline.txt"

section() { printf '\n## %s  (read %s)\n' "$1" "$(now)"; }

F=$(fleet_account) || { echo "ABORT: not exactly one fleet-account Lease for an account other than developer" >&2; exit 2; }
fleet_lease="gsd-fleet-$(printf '%s' "${F}" | shasum -a 256 | cut -c1-16)"
dev_lease="gsd-fleet-$(printf '%s' developer | shasum -a 256 | cut -c1-16)"

{
  echo "# #310 Part A baseline '${label}' — $(now) — oc $(oc version --client -o json | jq -r .clientVersion.gitVersion), as $(oc whoami)"

  section "oauth/cluster"
  spec=$(oc get oauths.config.openshift.io cluster -o json | jq -S -c .spec)
  echo "spec.tokenConfig: $(printf '%s' "${spec}" | jq -c .tokenConfig)"
  echo "spec keys: $(printf '%s' "${spec}" | jq -c keys)"
  echo "sha256 of spec WITHOUT tokenConfig (jq -S -c 'del(.tokenConfig)'): $(printf '%s' "${spec}" | jq -S -c 'del(.tokenConfig)' | shasum -a 256 | cut -d' ' -f1)"
  echo "oauthclient openshift-challenging-client overrides: $(oc get oauthclients.oauth.openshift.io openshift-challenging-client -o json | jq -c '{accessTokenMaxAgeSeconds, accessTokenInactivityTimeoutSeconds}')"

  section "the authentication ClusterOperator and the oauth-openshift rollout"
  oc get clusteroperators.config.openshift.io authentication -o json \
    | jq -r '[.status.conditions[] | select(.type | test("^(Available|Progressing|Degraded)$"))] | sort_by(.type)
             | "authentication conditions: \(map("\(.type)=\(.status)") | join(" "))",
               "  since: \(map("\(.type) \(.lastTransitionTime)") | join(", "))"'
  oc get deployments.apps -n openshift-authentication oauth-openshift -o json \
    | jq -r '"deployment oauth-openshift generation=\(.metadata.generation) observed=\(.status.observedGeneration) replicas=\(.status.replicas) updated=\(.status.updatedReplicas) ready=\(.status.readyReplicas)"'
  oc get pods -n openshift-authentication -l app=oauth-openshift -o json \
    | jq -r '.items[] | "pod \(.metadata.name) phase=\(.status.phase) started=\(.status.startTime) ready=\([.status.conditions[]? | select(.type=="Ready") | .status] | first)"'

  section "the dashboard release"
  oc get deployments.apps -n "${NS}" group-sync-dashboard -o json \
    | jq -c '{images: [.spec.template.spec.containers[] | {name, image}], chart: .metadata.labels["helm.sh/chart"], managedBy: .metadata.labels["app.kubernetes.io/managed-by"], version: .metadata.labels["app.kubernetes.io/version"]}'
  pod=$(dashboard_pod || true)
  echo "pod: ${pod:-none} started $(oc get pods -n "${NS}" "${pod}" -o jsonpath='{.status.startTime}' 2>/dev/null || echo '?')"
  if ${full}; then
    echo "/api/version (oc exec … python3.14 urlopen on the pod's loopback): $(oc exec -n "${NS}" deploy/group-sync-dashboard -c dashboard -- python3.14 -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/api/version").read().decode())')"
  else
    echo "/api/version: not read (--get-only; the app answers on the pod's loopback only)"
  fi
  echo "helm release records in ${NS} (Secrets owner=helm, names only): $(oc get secrets -n "${NS}" -l owner=helm -o custom-columns=NAME:.metadata.name --no-headers | tr '\n' ' ')"

  section "Argo CD"
  oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json 2>/dev/null \
    | jq -c '{targetRevision: .spec.source.targetRevision, syncPolicy: .spec.syncPolicy.automated, sync: .status.sync.status, revision: .status.sync.revision, health: .status.health.status, notHealthy: [.status.resources[]? | select(.health.status? and .health.status != "Healthy") | "\(.kind)/\(.name) \(.health.status): \(.health.message // "")"]}' \
    || echo "(no Application group-sync-dashboard)"
  oc get jobs.batch -n "${NS}" -o json \
    | jq -r '.items[] | "job \(.metadata.name) start=\(.status.startTime) succeeded=\(.status.succeeded // 0) failed=\(.status.failed // 0) \([.status.conditions[]? | select(.status=="True") | "\(.type):\(.reason // "")"] | join(","))"'

  section "PVCs"
  oc get persistentvolumeclaims -n "${NS}" -o json \
    | jq -r '.items[] | "\(.metadata.name) uid=\(.metadata.uid) volume=\(.spec.volumeName) resource-policy=\(.metadata.annotations["helm.sh/resource-policy"] // "-")"'

  section "cluster Secrets (name and resourceVersion columns only; shared-qa must not move)"
  oc get secrets -n "${NS}" -l groupsync-dashboard.io/secret-type=cluster \
    -o custom-columns=NAME:.metadata.name,RV:.metadata.resourceVersion,CREATED:.metadata.creationTimestamp --no-headers

  section "fleet-account Leases"
  echo "fleet-account Leases: $(oc get leases.coordination.k8s.io -n "${NS}" -l groupsync-dashboard.io/lease-type=fleet-account -o name | tr '\n' ' ')"
  obj=$(oc get leases.coordination.k8s.io -n "${NS}" "${fleet_lease}" -o json)
  printf '%s' "${obj}" | jq -r '"the fleet account'\''s Lease \(.metadata.name) rv=\(.metadata.resourceVersion) holder=\(.spec.holderIdentity // "" | if . == "" then "(none)" else . end) ping-last-attempt=\(.metadata.annotations["groupsync-dashboard.io/ping-last-attempt"] // "-") ping-last-ok=\(.metadata.annotations["groupsync-dashboard.io/ping-last-ok"] // "-") ping-last-outcome=\(.metadata.annotations["groupsync-dashboard.io/ping-last-outcome"] // "-") refused=\(if .metadata.annotations["groupsync-dashboard.io/refused"] then "present" else "absent" end)"'
  echo "sha256 of that whole Lease (jq -S -c .): $(printf '%s' "${obj}" | jq -S -c . | shasum -a 256 | cut -d' ' -f1)"
  echo "developer's Lease ${dev_lease}: $(oc get leases.coordination.k8s.io -n "${NS}" "${dev_lease}" -o jsonpath='rv={.metadata.resourceVersion} holder={.spec.holderIdentity}' 2>&1 | sed 's/^Error from server (NotFound): //')"

  section "OAuthAccessTokens (counted and dated, never named)"
  oc get oauthaccesstokens.oauth.openshift.io -o json | jq -r --arg f "${F}" '
    def sel(f): [.items[] | select(f)];
    "all objects: \(.items | length)",
    "developer, openshift-challenging-client: \(sel(.userName=="developer" and .clientName=="openshift-challenging-client") | length) created \(sel(.userName=="developer" and .clientName=="openshift-challenging-client") | map(.metadata.creationTimestamp) | sort | join(", "))",
    "developer, any client: \(sel(.userName=="developer") | length)",
    "the fleet account, openshift-challenging-client: \(sel(.userName==$f and .clientName=="openshift-challenging-client") | length) created \(sel(.userName==$f and .clientName=="openshift-challenging-client") | map(.metadata.creationTimestamp) | sort | join(", "))",
    "the fleet account, any client: \(sel(.userName==$f) | length)",
    "tokens with expiresIn <= 600 (minted while the walk lifetime held): \(sel(.expiresIn <= 600) | length), by client: \(sel(.expiresIn <= 600) | group_by(.clientName) | map("\(.[0].clientName)=\(length)") | join(", "))"'

  section "grants"
  if ${full}; then
  echo "ServiceAccount get openshift-config/ldap-oauth-bind-secret: $(oc auth can-i get secrets/ldap-oauth-bind-secret -n openshift-config --as="${SA}" 2>/dev/null || true)"
  echo "ServiceAccount get ${NS}/${WALK_SECRET}: $(oc auth can-i get "secrets/${WALK_SECRET}" -n "${NS}" --as="${SA}" 2>/dev/null || true)"
  echo "developer list groups.user.openshift.io (the poller ClusterRole): $(oc auth can-i list groups.user.openshift.io --as=developer 2>/dev/null || true)"
  else
    echo "oc auth can-i: not run (--get-only)"
  fi
  echo "the chart's group-sync-dashboard-fleet-account Role in openshift-config: $(oc get roles.rbac.authorization.k8s.io -n openshift-config group-sync-dashboard-fleet-account -o json 2>/dev/null | jq -c '.rules' || echo absent)"

  section "the walk's objects"
  echo "labelled ${RUN_LABEL}: $(oc get secrets,roles.rbac.authorization.k8s.io,rolebindings.rbac.authorization.k8s.io -A -l "${RUN_LABEL}" -o name | tr '\n' ' ') $(oc get clusterrolebindings.rbac.authorization.k8s.io -l "${RUN_LABEL}" -o name | tr '\n' ' ')"
  echo "the walk Secret by name: $(oc get secrets -n "${NS}" "${WALK_SECRET}" -o name 2>&1 | sed 's/^Error from server (NotFound): //')"

  section "/metrics (via the pod proxy, the oauth-proxy's skip-auth path)"
  metrics | grep -E '^gsd_cluster_(up|last_poll_timestamp_seconds)\{' || echo "(metrics not read)"
} > "${out}" 2>&1

cat "${out}"
