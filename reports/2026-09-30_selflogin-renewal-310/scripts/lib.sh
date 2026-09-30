# shellcheck shell=bash disable=SC2034  # sourced; the names are used by the scripts that source it
# Sourced by every script in this folder (bash only). Names, paths and the few helpers they share.
# No password, token or token-object name is ever printed by anything that sources this file; the fleet account's
# username is read into a variable when a count needs it and never written out.

NS=group-sync-dashboard
RUN=selflogin-310-2026-09-30
RUN_LABEL="walk.gsd.lab/run=${RUN}"
WALK_CLUSTER=walk-self-login
WALK_SECRET=gsd-walk-developer-password
SA="system:serviceaccount:${NS}:group-sync-dashboard"
LIFETIME_WALK=600          # #310: a 150 s margin, min(2 h, 600 / 4)
LIFETIME_FOUND=31536000    # oauth/cluster as found on 2026-09-22, 2026-09-27 and 2026-09-30

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # the report folder
EVIDENCE="${EVIDENCE_DIR:-${HERE}/evidence}"   # EVIDENCE_DIR: offline_proofs.sh points the stub runs elsewhere
mkdir -p "${EVIDENCE}"

: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"

now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
# OAuthAccessToken object names are derived from the token; they leave no capture.
redact() { sed -E 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g'; }
say() { printf '%s %s\n' "$(now)" "$*"; }

# The fleet account's username, from the one fleet-account Lease whose account is not `developer`. Into a variable
# only: callers count with it and never print it. Fails (non-zero, empty output) unless exactly one such Lease exists.
fleet_account() {
  local names
  names=$(oc get leases.coordination.k8s.io -n "${NS}" -l groupsync-dashboard.io/lease-type=fleet-account -o json \
    | jq -r '[.items[] | .metadata.annotations["groupsync-dashboard.io/account"] // empty | select(. != "developer")]
             | if length == 1 then .[0] else empty end') || return 1
  [ -n "${names}" ] || return 1
  printf '%s' "${names}"
}

# The Running dashboard pod's name (the Deployment runs one replica, Recreate; the report pod has another name label).
dashboard_pod() {
  oc get pods -n "${NS}" -l app.kubernetes.io/name=group-sync-dashboard \
    --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

# /metrics through the oauth-proxy's skip-auth path, via the API server's pod proxy: a GET, no exec.
metrics() {
  local pod; pod=$(dashboard_pod) || return 1
  [ -n "${pod}" ] || return 1
  oc get --raw "/api/v1/namespaces/${NS}/pods/https:${pod}:8443/proxy/metrics"
}

# oauth/cluster's spec.tokenConfig, compact.
token_config() { oc get oauths.config.openshift.io cluster -o json | jq -c '.spec.tokenConfig'; }
