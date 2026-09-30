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

# Whether the lab is on Argo CD: the Application exists and is not being deleted, and no Helm release of the dashboard
# is installed. A signal that cuts `release-crc.sh --values` short inside `oc delete application` leaves the Application
# with a deletionTimestamp while Argo CD goes on deleting what it tracks, the chart's fleet-account Role in
# openshift-config among them, so the Application's presence alone does not mean the lab is on Argo CD. 0 yes; 1 no,
# or a read failed (a failed read never counts as "on Argo CD").
on_argo() {
  local deleting helm
  deleting=$(oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard \
    -o jsonpath='{.metadata.deletionTimestamp}' 2>/dev/null) || return 1
  helm=$(oc get secrets -n "${NS}" -l owner=helm,name=group-sync-dashboard -o name 2>/dev/null) || return 1
  [ -z "${deleting}" ] && [ -z "${helm}" ]
}

# The Running dashboard pod's name (the Deployment runs one replica, Recreate; the report pod has another name label).
dashboard_pod() {
  oc get pods -n "${NS}" -l app.kubernetes.io/name=group-sync-dashboard \
    --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}' 2>/dev/null
}

# Wait until one exact pod UID is gone, then write the next whole-second instant. Using that as an exclusive audit bound
# starts this before Helm is handed back to Argo, so the audit can use the walk pod's real lifetime rather than leader
# detection and hand-back initiation. A transient read failure is not absence. 0 gone, 1 timeout/unreadable.
wait_for_pod_end() {
  local pod_name="${1:?pod name}" pod_uid="${2:?pod uid}" out="${3:?output file}" timeout_seconds="${4:-1200}"
  local deadline=$(( $(date +%s) + timeout_seconds )) obj current
  while [ "$(date +%s)" -lt "${deadline}" ]; do
    if obj=$(oc get pods -n "${NS}" "${pod_name}" -o json 2>&1); then
      current=$(printf '%s' "${obj}" | jq -r '.metadata.uid // empty') || current=
      if [ -n "${current}" ] && [ "${current}" != "${pod_uid}" ]; then
        date -u -r "$(( $(date +%s) + 1 ))" +%Y-%m-%dT%H:%M:%SZ > "${out}"
        return 0
      fi
    else
      case "${obj}" in
        *NotFound*|*"not found"*) date -u -r "$(( $(date +%s) + 1 ))" +%Y-%m-%dT%H:%M:%SZ > "${out}"; return 0 ;;
      esac
    fi
    sleep 1
  done
  return 1
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
