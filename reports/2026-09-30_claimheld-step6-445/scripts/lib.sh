# shellcheck shell=bash disable=SC2034  # sourced; the names are used by the scripts that source it
# Sourced by every script in this folder (bash only): #445's names, paths and the few helpers they share. Based on
# reports/2026-09-30_selflogin-renewal-310/scripts/lib.sh; this walk changes no cluster-wide object, so the oauth
# lifetime names are gone. No password, token or token-object name is ever printed by anything that sources this
# file; the fleet account's username is read into a variable when a count needs it and never written out.

NS=group-sync-dashboard
RUN=claimheld-445-2026-09-30
RUN_LABEL="walk.gsd.lab/run=${RUN}"
# Named by the walk values as the fleet password Secret and NEVER created: step 6 places no password, and with the
# Secret absent every bind path refuses before the wire (gsd/fleetlookup.py#fleet_password: fleet-credential-missing).
WALK_SECRET=gsd-walk-developer-password
# `developer`'s Lease: gsd/fleetstate.py#lease_name, "gsd-fleet-" + sha256(username)[:16]. The username alone: the
# password Secret's uid salts the DIGEST (lease_digest), never the name. offline_proofs.sh checks it against the code.
DEV_LEASE=gsd-fleet-88fa0d759f845b47
SA="system:serviceaccount:${NS}:group-sync-dashboard"

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

# `developer`'s Lease as one line: `absent`, or `holder=<id|none> renew=<t> duration=<s> rv=<n>`. A read that fails
# for any reason but NotFound prints nothing and returns 1: an unreadable Lease is never read as free.
dev_lease_state() {
  local out
  if ! out=$(oc get leases.coordination.k8s.io -n "${NS}" "${DEV_LEASE}" -o json 2>&1); then
    case "${out}" in *NotFound*|*"not found"*) echo absent; return 0 ;; *) return 1 ;; esac
  fi
  printf '%s' "${out}" | jq -r '"holder=\(.spec.holderIdentity // "" | if . == "" then "none" else . end) renew=\(.spec.renewTime // "-") duration=\(.spec.leaseDurationSeconds // "-") rv=\(.metadata.resourceVersion)"'
}

# Whether `developer`'s Lease is free, by the code's own rule (gsd/fleetstate.py#FleetRecord.in_flight: a holder AND
# renewTime + leaseDurationSeconds in the future): absent, no holder, or the claim past its duration. 0 free, 1 held,
# 2 unreadable.
dev_lease_free() {
  local state holder renew dur until
  state=$(dev_lease_state) || return 2
  [ "${state}" = absent ] && return 0
  holder=$(sed -E 's/^holder=([^ ]*) .*/\1/' <<<"${state}")
  [ "${holder}" = none ] && return 0
  renew=$(sed -E 's/.* renew=([^ ]*) .*/\1/' <<<"${state}" | sed -E 's/\.[0-9]+Z$/Z/')
  dur=$(sed -E 's/.* duration=([^ ]*) .*/\1/' <<<"${state}")
  [ "${renew}" != - ] && [ "${dur}" != - ] || return 1        # a holder with no instant: held (the safe reading)
  until=$(( $(date -j -u -f %Y-%m-%dT%H:%M:%SZ "${renew}" +%s) + dur ))
  [ "$(date -u +%s)" -ge "${until}" ]
}
