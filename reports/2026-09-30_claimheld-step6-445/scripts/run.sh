#!/usr/bin/env bash
# #445, phase 2: SPEC_S4c §3.12 step 6 on the CRC lab, as `developer`, at application 2.0.0 (main 57735e9e). Two
# claim-only processes inside the dashboard pod prove the durable Lease's ClaimHeld on `developer`'s Lease. README.md
# is the plan; this script is its only executor. Run it in the background, with one waiter on its exit.
#
# Usage: WALK_TMP=<scratch dir outside the repository> KUBECONFIG=<the lab's> PY=<python with pytest and PyYAML>
#        bash scripts/run.sh
#
# ORDER: read-only preflight, the coordinator extracted from the spec at MAIN_SHA and pinned, the start baseline →
# the EXIT trap → the keep-grant → the walk values deployed (Helm) → the walk pod leads → 6.0 (lab check 0 0 0,
# developer's Lease free, the instants and counts) → 6.1-6.3 (the spec's one `oc exec -i … python3.14 -`) → 6.4
# (the derived audit and the counts) → `release-crc.sh --argocd main` → sweep → the end baseline and comparison.
# No password is placed: the walk Secret the values name is never created. No cluster-wide object is written.
# The trap (scripts/sweep.sh) runs on EVERY exit before the hand-back completes.
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=lib.sh
. "$(dirname "$0")/lib.sh"
S="$(cd "$(dirname "$0")" && pwd)"
MAIN_SHA=57735e9ee8fe4a8bf7cf6df97b0ebde50ca21a61
# The in-pod program, as scripts/extract_step6.py extracts it from SPEC_S4c at MAIN_SHA (evidence/offline-coordinator.txt).
COORD_SHA256=2b5e210329a66ce6dc3387470ade604bb835028e36dc00e04a28298dca5be9c2
V=reports/2026-09-30_claimheld-step6-445/prepared/walk-values-claimheld.yaml   # repository-relative, as --values wants
: "${WALK_TMP:?WALK_TMP must name a scratch directory outside the repository}"
: "${PY:?PY must name a python with pytest and PyYAML: the extraction imports the step-6 test module of the repository}"
DEPLOY="${WALK_TMP}/deploy-${MAIN_SHA:0:8}"   # a clean clone at MAIN_SHA: release-crc.sh builds and deploys from it
RAW="${WALK_TMP}/raw"                         # the coordinator program and raw reads; removed on exit
LOG="${EVIDENCE}/phase2-run.txt"
HANDBACK_DONE=false
EXPECT_HELD="HELD walk-step6-a ${DEV_LEASE}"
EXPECT_CLAIMHELD="ClaimHeld walk-step6-a holds ${DEV_LEASE} until "
exec > >(tee -a "${LOG}") 2>&1

abort() { say "ABORT: $*"; exit 1; }

on_exit() {
  local rc=$?
  set +e
  # Nothing may stop the restore half-way. A SIGTERM or SIGHUP sent to the process group also kills the `tee` behind
  # stdout, and the trap's first write then ended this shell with SIGPIPE before the sweep ran; a second Ctrl-C killed
  # the sweep in the middle (both measured by the review of #310's phase 1). Ignored here, the signals stay ignored in
  # every command this trap starts; the log file is written directly.
  trap '' INT TERM HUP PIPE
  exec >>"${LOG}" 2>&1
  if [ "${HANDBACK_DONE}" != true ]; then
    say "run.sh is exiting (rc=${rc}) before the hand-back completed: the sweep runs now"
    local swept=0; bash "${S}/sweep.sh" trap || swept=$?
    # The trap does not redeploy: the Argo CD cutover is the operator's step, said here with its command — and only
    # after a sweep that settled (exit 0, or 5: something left on purpose until the hand-back).
    if [ "${swept}" != 0 ] && [ "${swept}" != 5 ]; then
      say "THE SWEEP DID NOT COMPLETE: sweep.sh exited ${swept} (evidence/trap-sweep.txt). Run bash ${S}/sweep.sh trap-again and read what it says before anything else."
    elif oc get secrets -n "${NS}" -l owner=helm,name=group-sync-dashboard -o name | grep -q . \
       || ! oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o name >/dev/null 2>&1; then
      say "THE LAB IS NOT ON ARGO CD (a Helm release is installed, or the Application is gone). To finish: (cd ${DEPLOY}/local-development && ./release-crc.sh --argocd main), then bash ${S}/sweep.sh trap-after-handback"
    fi
  fi
  rm -rf "${RAW}"
  say "run.sh ends rc=${rc}"
  exit "${rc}"
}

# ── 0. Preflight: reads and local work only; nothing on the cluster changes before the trap is set ────────────────
say "#445 phase 2 — run ${RUN}, main ${MAIN_SHA}"
[ "$(oc whoami)" = kubeadmin ] || abort "the kubeconfig is not kubeadmin's"
podman info >/dev/null 2>&1 || abort "podman is not reachable: release-crc.sh builds the images"
"${PY}" -c 'import pytest, yaml' || abort "${PY} lacks pytest or PyYAML"
[ -z "$(oc get secrets,roles.rbac.authorization.k8s.io,rolebindings.rbac.authorization.k8s.io -A -l "${RUN_LABEL}" -o name)$(oc get clusterrolebindings.rbac.authorization.k8s.io -l "${RUN_LABEL}" -o name)" ] \
  || abort "objects labelled ${RUN_LABEL} already exist"
# The sweep deletes developer's Lease at the end; it may only delete what this walk created.
[ "$(dev_lease_state)" = absent ] || abort "developer's Lease ${DEV_LEASE} exists: another walk is under way or was not cleaned"
[ -z "$(oc get secrets -n "${NS}" "${WALK_SECRET}" -o name --ignore-not-found)" ] || abort "${WALK_SECRET} exists: this walk places no password"
argo=$(oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o json) || abort "no Argo CD Application"
[ "$(jq -r '"\(.spec.source.targetRevision) \(.status.sync.status) \(.status.sync.revision)"' <<<"${argo}")" = "main Synced ${MAIN_SHA}" ] \
  || abort "Argo CD is not Synced at main ${MAIN_SHA}: $(jq -r '"\(.spec.source.targetRevision) \(.status.sync.status) \(.status.sync.revision)"' <<<"${argo}")"
# Step 2's cascade deletes every object the Application tracks; a PVC survives it only by its LIVE
# `argocd.argoproj.io/sync-options: …Delete=false…` (helm.sh/resource-policy: keep protects `helm uninstall` alone).
oc get persistentvolumeclaims -n "${NS}" -o json \
  | jq -e '[.items[] | select(.metadata.name | test("^group-sync-dashboard-(data|report-artifacts)$"))]
           | length == 2 and all(.[]; ((.metadata.annotations["argocd.argoproj.io/sync-options"] // "") | split(",") | index("Delete=false"))
                                      and .metadata.annotations["helm.sh/resource-policy"] == "keep")' >/dev/null \
  || abort "the data and report-artifacts PVCs must both carry Delete=false and resource-policy keep: the handover's cascade deletes a PVC without them"
remote=$(git -C "${HERE}" remote get-url origin)
origin_main=$(git ls-remote "${remote}" refs/heads/main | cut -f1)
[ "${origin_main}" = "${MAIN_SHA}" ] || abort "GitHub's main is ${origin_main}, not ${MAIN_SHA}: the hand-back would deploy another commit"
if [ ! -d "${DEPLOY}" ]; then
  git clone -q --no-hardlinks --no-checkout "$(git -C "${HERE}" rev-parse --show-toplevel)" "${DEPLOY}"
  git -C "${DEPLOY}" remote set-url origin "${remote}"
  git -C "${DEPLOY}" checkout -q --detach "${MAIN_SHA}"
fi
mkdir -p "$(dirname "${DEPLOY}/${V}")"; cp "${HERE}/prepared/walk-values-claimheld.yaml" "${DEPLOY}/${V}"
[ "$(git -C "${DEPLOY}" rev-parse HEAD)" = "${MAIN_SHA}" ] || abort "${DEPLOY} is not at ${MAIN_SHA}"
[ -z "$(git -C "${DEPLOY}" status --porcelain -- . ":(exclude,top,literal)${V}")" ] || abort "${DEPLOY} is not clean"
# The program 6.1-6.3 runs: extracted from the spec AT MAIN_SHA by the repository's own step-6 test module, never typed.
mkdir -p "${RAW}"
extracted=$("${PY}" "${S}/extract_step6.py" "${DEPLOY}" "${RAW}/step6-coordinator.py") || abort "the coordinator could not be extracted from the spec"
say "extracted from ${DEPLOY}/docs/specs/SPEC_S4c_credential_lifecycle.md §3.12 step 6: $(tr '\n' ' ' <<<"${extracted}")"
[ "$(sed -n 2p <<<"${extracted}")" = "${COORD_SHA256}" ] || abort "the spec's program is not the one phase 1 rehearsed (sha256 ${COORD_SHA256})"
"${PY}" -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec")' "${RAW}/step6-coordinator.py" \
  || abort "the extracted program does not compile"
T_START=$(now)
bash "${S}/baseline.sh" phase2-start >/dev/null
say "baseline: evidence/phase2-start-baseline.txt"
bash "${S}/labcheck.sh" phase2-as-found-informational || true   # 1 0 0 expected: the Argo configuration names it

# ── the trap, before the first write ──────────────────────────────────────────────────────────────────────────────
trap on_exit EXIT
trap 'exit 130' INT TERM HUP
say "IF THIS RUN IS KILLED FROM HERE ON (kill -9: no trap runs): (cd ${DEPLOY}/local-development && ./release-crc.sh --argocd main), then bash ${S}/sweep.sh manual — no step of this walk leaves a password or a cluster-wide change behind"

# ── 1. The keep-grant (prepared/walk-rbac.yaml) ────────────────────────────────────────────────────────────────────
oc create -f "${HERE}/prepared/walk-rbac.yaml" --dry-run=server -o name
oc create -f "${HERE}/prepared/walk-rbac.yaml" -o name | tee "${EVIDENCE}/phase2-walk-rbac-create.txt"

# ── 2. The walk values, Helm mode, from the clean clone (deletes the Argo Application; the PVCs are kept) ──────────
say "release-crc.sh --values ${V} (from ${DEPLOY})"
set +e
( cd "${DEPLOY}/local-development" && ./release-crc.sh --values "${V}" ) 2>&1 \
  | grep -v 'Copying blob' > "${EVIDENCE}/phase2-deploy-release-crc.log"
deploy_rc=${PIPESTATUS[0]}
set -e
say "release-crc.sh --values exited ${deploy_rc} (evidence/phase2-deploy-release-crc.log)"
[ "${deploy_rc}" = 0 ] || abort "the walk values did not deploy"

# ── 3. The walk pod leads (the previous pod's leader Lease expires first: 25-31 s on 2026-09-27) ───────────────────
deadline=$(( $(date +%s) + 180 )); led=0
while [ "$(date +%s)" -lt "${deadline}" ]; do
  pod=$(dashboard_pod || true)
  if [ -n "${pod}" ]; then
    led=$(oc logs -n "${NS}" "${pod}" -c dashboard 2>/dev/null | grep -c -E 'gsd\.leader .*(became leader|taking it)' || true)
    [ "${led:-0}" -ge 1 ] && break
  fi
  sleep 5
done
[ "${led:-0}" -ge 1 ] || abort "the walk pod did not take the leader Lease in 180 s"
T_LEADS=$(now)
say "the walk pod ${pod} leads (${T_LEADS})"

# ── 6.0 Abort checks before any claim() ────────────────────────────────────────────────────────────────────────────
bash "${S}/labcheck.sh" phase2-step6.0 || abort "the lab check did not print 0 0 0"
F=$(fleet_account) || abort "the fleet account's Lease was not found"
fleet_lease="gsd-fleet-$(printf '%s' "${F}" | shasum -a 256 | cut -c1-16)"
counts() {   # step 1's jq: the two challenging-client counts, the fleet account's by count only
  oc get oauthaccesstokens.oauth.openshift.io -o json | jq -r --arg f "${F}" '
    [.items[] | select(.clientName == "openshift-challenging-client")] as $c
    | "developer, openshift-challenging-client: \([$c[] | select(.userName == "developer")] | length)",
      "the fleet account, openshift-challenging-client: \([$c[] | select(.userName == $f)] | length)"'
}
fleet_sha() { oc get leases.coordination.k8s.io -n "${NS}" "${fleet_lease}" -o json | jq -S -c . | shasum -a 256 | cut -d' ' -f1; }
deadline=$(( $(date +%s) + 180 )); free=1
while :; do
  set +e; dev_lease_free; free=$?; set -e
  [ "${free}" = 0 ] && break
  [ "${free}" = 2 ] && abort "developer's Lease could not be read"
  [ "$(date +%s)" -ge "${deadline}" ] && abort "developer's Lease is still held after three minutes: $(dev_lease_state)"
  sleep 5
done
STEP6_SINCE=$(now)
start_counts=$(counts); start_fleet_sha=$(fleet_sha)
{
  echo "# SPEC_S4c §3.12 step 6.0 at ${STEP6_SINCE}. The lab check: evidence/phase2-step6.0-labcheck.txt (0 0 0)."
  echo "# the spec's Lease read, verbatim:"
  printf '%s\n' "#   oc get leases.coordination.k8s.io ${DEV_LEASE} -n ${NS} -o jsonpath='{.spec.holderIdentity} {.spec.renewTime} {.spec.leaseDurationSeconds}{\"\\n\"}'"
  oc get leases.coordination.k8s.io "${DEV_LEASE}" -n "${NS}" -o jsonpath='{.spec.holderIdentity} {.spec.renewTime} {.spec.leaseDurationSeconds}{"\n"}' 2>&1 || true
  echo "developer's Lease: $(dev_lease_state) — free by gsd/fleetstate.py#FleetRecord.in_flight's rule (absent reads as unheld)"
  echo "STEP6_SINCE=${STEP6_SINCE}"
  echo "${start_counts}"
  echo "sha256 of the fleet account's Lease (jq -S -c . | shasum -a 256): ${start_fleet_sha}"
} | tee "${EVIDENCE}/phase2-step6.0.txt"

# ── 6.1-6.3 Hold, challenge, release: the spec's one command, its program on stdin ─────────────────────────────────
say "6.1-6.3: oc exec -i -n ${NS} deploy/group-sync-dashboard -c dashboard -- python3.14 - < <the program, sha256 ${COORD_SHA256}>"
set +e
oc exec -i -n "${NS}" deploy/group-sync-dashboard -c dashboard -- python3.14 - \
  < "${RAW}/step6-coordinator.py" > "${RAW}/step6.out" 2> "${RAW}/step6.err"
coord_rc=$?
set -e
after=$(dev_lease_state || echo '(unreadable)')
{
  echo "# SPEC_S4c §3.12 step 6.1-6.3 at $(now): oc exec -i -n ${NS} deploy/group-sync-dashboard -c dashboard -- python3.14 - <<'PY' … PY"
  echo "# the program: SPEC_S4c at ${MAIN_SHA}, extracted by scripts/extract_step6.py, sha256 ${COORD_SHA256}"
  echo "## stdout"; redact < "${RAW}/step6.out"
  echo "## stderr"; redact < "${RAW}/step6.err"
  echo "## exit code: ${coord_rc}"
  echo "## developer's Lease after: ${after}"
} | tee "${EVIDENCE}/phase2-step6.1-6.3.txt"
step6_ok=true
[ "${coord_rc}" = 0 ] || step6_ok=false
[ "$(wc -l < "${RAW}/step6.out" | tr -d ' ')" = 3 ] || step6_ok=false
[ "$(sed -n 1p "${RAW}/step6.out")" = "${EXPECT_HELD}" ] || step6_ok=false
[[ "$(sed -n 2p "${RAW}/step6.out")" == "${EXPECT_CLAIMHELD}"* ]] || step6_ok=false
[ "$(sed -n 3p "${RAW}/step6.out")" = RELEASED ] || step6_ok=false
[[ "${after}" == "holder=none "* ]] || step6_ok=false
${step6_ok} || abort "step 6.1-6.3 did not print HELD, ClaimHeld, RELEASED and exit 0 with the Lease released (evidence/phase2-step6.1-6.3.txt): the spec says inspect the Lease with 6.0 and wait for it before any retry"

# ── 6.4 Counts ─────────────────────────────────────────────────────────────────────────────────────────────────────
bash "${S}/capture.sh" audit phase2-step6.4 "${STEP6_SINCE}" || abort "the audit window [${STEP6_SINCE}, now) could not be read whole"
end_counts=$(counts); end_fleet_sha=$(fleet_sha)
dev_auth=$(sed -nE 's/^#   developer authorize records, any decision: ([0-9]+)$/\1/p' "${EVIDENCE}/phase2-step6.4-audit.txt")
fleet_auth=$(sed -nE "s/^#   the fleet account's authorize records, any decision: ([0-9]+)\$/\\1/p" "${EVIDENCE}/phase2-step6.4-audit.txt")
{
  echo "# SPEC_S4c §3.12 step 6.4 at $(now): the derived audit in [${STEP6_SINCE}, now) is evidence/phase2-step6.4-audit.txt"
  echo "#   developer authorize records, any decision: ${dev_auth:-?}   (expected 0)"
  echo "#   the fleet account's authorize records, any decision: ${fleet_auth:-?}   (expected 0)"
  echo "# challenging-client token counts, 6.0 -> now:"
  paste -d'|' <(printf '%s\n' "${start_counts}") <(printf '%s\n' "${end_counts}") | sed 's/|/  ->  /'
  echo "# the fleet account's Lease sha256, 6.0 -> now: ${start_fleet_sha} -> ${end_fleet_sha}"
} | tee "${EVIDENCE}/phase2-step6.4.txt"
[ "${dev_auth:-x}" = 0 ] && [ "${fleet_auth:-x}" = 0 ] || abort "an authorize ran in the window"
[ "${start_counts}" = "${end_counts}" ] || abort "a challenging-client token count moved in the window"
[ "$(sed -nE 's/^the fleet account, openshift-challenging-client: ([0-9]+)$/\1/p' <<<"${end_counts}")" = 2 ] \
  || abort "the fleet account's challenging-client count is not 2"
[ "${start_fleet_sha}" = "${end_fleet_sha}" ] || abort "the fleet account's Lease changed in the window"
say "STEP 6 PASSED: HELD, ClaimHeld, RELEASED, exit 0; 0 authorizes for developer and for the fleet account; counts and the fleet Lease unchanged"
bash "${S}/capture.sh" podlog phase2 "${RAW}"

# ── 7. Hand back: Argo, then what is left ─────────────────────────────────────────────────────────────────────────
T_HANDBACK=$(now)
say "release-crc.sh --argocd main (from ${DEPLOY})"
set +e
( cd "${DEPLOY}/local-development" && ./release-crc.sh --argocd main ) > "${EVIDENCE}/phase2-handback-release-crc-argocd-main.log" 2>&1
argo_rc=$?
set -e
say "release-crc.sh --argocd main exited ${argo_rc} (evidence/phase2-handback-release-crc-argocd-main.log)"
sweep_rc=0; bash "${S}/sweep.sh" handback || sweep_rc=$?
say "sweep.sh handback exited ${sweep_rc}"

# ── 8. The evidence at the end ────────────────────────────────────────────────────────────────────────────────────
set +e
bash "${S}/capture.sh" audit phase2-before-walk-pod "${T_START}" "${T_LEADS}"      # INFO: the Argo pod's own ping, if due
bash "${S}/capture.sh" audit phase2-walk-pod "${T_LEADS}" "${T_HANDBACK}"; tenure_rc=$?
bash "${S}/capture.sh" audit phase2-after-handback "${T_HANDBACK}"                  # INFO: the restored pod's own ping
tenure=$(grep -E "^#   (developer|the fleet account's) authorize records, any decision: " "${EVIDENCE}/phase2-walk-pod-audit.txt" | sed -E 's/.*: //' | tr '\n' ' ')
bash "${S}/baseline.sh" phase2-end >/dev/null
bash "${S}/compare_baselines.sh" phase2-start phase2-end > "${EVIDENCE}/phase2-compare.txt"; compare_rc=$?
cat "${EVIDENCE}/phase2-compare.txt"
# The fleet account is counted, never named: a count of its name across everything this run wrote (the name itself
# stays in the variable).
named=$(grep -r -c -F -- "${F}" "${EVIDENCE}" | awk -F: '{ s += $NF } END { print s + 0 }')
set -e
say "done: step 6 passed, argocd main rc=${argo_rc}, sweep rc=${sweep_rc}, walk-pod audit (developer, fleet)=${tenure}(rc ${tenure_rc}), compare rc=${compare_rc}, the fleet account named in evidence/: ${named} time(s)"
# Only a complete sweep ends the trap's duty; otherwise it runs the sweep once more and says what is left.
[ "${sweep_rc}" = 0 ] && HANDBACK_DONE=true
[ "${sweep_rc}" = 0 ] && [ "${compare_rc}" = 0 ] && [ "${tenure_rc}" = 0 ] && [ "${tenure}" = "0 0 " ] && [ "${named}" = 0 ]
