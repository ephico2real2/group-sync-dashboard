#!/usr/bin/env bash
# The lab left as found: two scripts/baseline.sh files compared on the lines #310's Definition of Done names. Offline.
# Usage: compare_baselines.sh <start label> <end label>   (reads evidence/<label>-baseline.txt)
# Exit 0 when every MUST line is equal (and oauth/cluster reads exactly 31536000); the INFO lines are printed for the
# README, and may differ for a stated reason (the product's own daily ping moves the fleet Lease's resourceVersion).
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
a="${here}/evidence/${1:?start label}-baseline.txt"; b="${here}/evidence/${2:?end label}-baseline.txt"
bad=0

pick() { grep -E -- "$2" "$1" || echo "(absent)"; }
must() {  # must <what> <regex>: the matching lines are identical in both files
  local x y; x=$(pick "${a}" "$2"); y=$(pick "${b}" "$2")
  if [ "${x}" = "${y}" ]; then echo "EQUAL     $1"; else echo "DIFFERENT $1"; bad=1; fi
  printf '  start: %s\n  end:   %s\n' "${x//$'\n'/$'\n         '}" "${y//$'\n'/$'\n         '}"
}
info() {
  printf 'INFO      %s\n  start: %s\n  end:   %s\n' "$1" "$(pick "${a}" "$2" | tr '\n' ' ')" "$(pick "${b}" "$2" | tr '\n' ' ')"
}

must "oauth/cluster spec.tokenConfig" '^spec\.tokenConfig: '
if grep -qxF 'spec.tokenConfig: {"accessTokenMaxAgeSeconds":31536000}' "${b}"; then
  echo "EQUAL     oauth/cluster reads exactly {\"accessTokenMaxAgeSeconds\":31536000} at the end"
else
  echo "DIFFERENT oauth/cluster does not read exactly {\"accessTokenMaxAgeSeconds\":31536000} at the end"; bad=1
fi
must "oauth/cluster spec, everything but tokenConfig (sha256)" '^sha256 of spec WITHOUT tokenConfig'
must "the challenging client's own overrides" '^oauthclient openshift-challenging-client overrides'
must "PVC UIDs" '^group-sync-dashboard-(data|report-artifacts) uid='
must "gsd-cluster-shared-qa (name, resourceVersion, created)" '^gsd-cluster-shared-qa '
must "gsd-cluster-shared-rnd (name, resourceVersion, created)" '^gsd-cluster-shared-rnd '
must "the fleet account's OAuthAccessTokens (challenging client)" '^the fleet account, openshift-challenging-client: '
must "the fleet account's OAuthAccessTokens (any client)" '^the fleet account, any client: '
must "developer's challenging-client OAuthAccessTokens (count and creation instants)" '^developer, openshift-challenging-client: '
must "objects labelled with the run" '^labelled walk\.gsd\.lab/run='
must "the walk Secret by name" '^the walk Secret by name: '
must "developer's Lease" "^developer's Lease "
must "the chart's fleet-account Role in openshift-config" "^the chart's group-sync-dashboard-fleet-account Role"
must "the ServiceAccount's get on ldap-oauth-bind-secret" '^ServiceAccount get openshift-config/ldap-oauth-bind-secret: '
must "the authentication ClusterOperator (conditions)" '^authentication conditions: '
info "the fleet account's Lease (the product's daily ping may move rv and ping-last-*; holder must be none)" "^the fleet account's Lease "
info "the fleet Lease's sha256" '^sha256 of that whole Lease'
info "Argo CD" '^\{"targetRevision"'
info "the dashboard Deployment" '^\{"images"'
info "/api/version" '^/api/version'
info "OAuthAccessTokens minted with expiresIn <= 600" '^tokens with expiresIn <= 600'
info "all OAuthAccessTokens" '^all objects: '
info "oauth-openshift" '^deployment oauth-openshift '
if grep -qE "^the fleet account's Lease .* holder=\(none\) " "${b}"; then
  echo "EQUAL     the fleet account's Lease has no holder at the end"
else
  echo "DIFFERENT the fleet account's Lease has a holder at the end"; bad=1
fi
if [ "${bad}" = 0 ]; then echo "LEFT AS FOUND on every MUST line"; else echo "NOT left as found: see DIFFERENT above"; fi
exit "${bad}"
