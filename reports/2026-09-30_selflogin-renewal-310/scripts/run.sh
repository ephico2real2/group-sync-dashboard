#!/usr/bin/env bash
# #310 Part A, phase 2: observe a `userSelfLogin` session renew on the CRC lab, as `developer`, with oauth/cluster's
# accessTokenMaxAgeSeconds lowered to 600 for the walk and restored to 31536000 after it. README.md is the plan; this
# script is its only executor. Run it in the background, with one waiter on its exit.
#
# Usage: WALK_TMP=<scratch dir outside the repository> KUBECONFIG=<the lab's> bash scripts/run.sh
#   RENEWALS (default 2)   scheduled renewals to observe before the hand-back
#
# ORDER, and why it is not the brief's (README, "Order"):
#   read-only preflight and the start baseline → the EXIT trap → the walk grants → the walk values deployed (Helm)
#   → lab check 0 0 0 → oauth 600, settled → lab check 0 0 0 → the walk Secret → observe → the walk Secret removed
#   → oauth 31536000, settled → `release-crc.sh --argocd main` → sweep → the end baseline.
# The trap (scripts/sweep.sh) runs on EVERY exit before the hand-back completes: oauth/cluster back to 31536000, the
# walk Secret and `developer`'s grant removed, the keep-grant and `developer`'s Lease removed once nothing needs them.
set -euo pipefail
# shellcheck source-path=SCRIPTDIR source=lib.sh
. "$(dirname "$0")/lib.sh"
S="$(cd "$(dirname "$0")" && pwd)"
MAIN_SHA=708e6be1046ca302ffbef6ba1f17fe811295462f
V=reports/2026-09-30_selflogin-renewal-310/prepared/walk-values-selflogin.yaml   # repository-relative, as --values wants
RENEWALS="${RENEWALS:-2}"
: "${WALK_TMP:?WALK_TMP must name a scratch directory outside the repository}"
DEPLOY="${WALK_TMP}/deploy-${MAIN_SHA:0:8}"   # a clean clone at MAIN_SHA: release-crc.sh builds and deploys from it
RAW="${WALK_TMP}/raw"                         # the raw pod log and metrics samples; removed on exit
LOG="${EVIDENCE}/phase2-run.txt"
HANDBACK_DONE=false
exec > >(tee -a "${LOG}") 2>&1

abort() { say "ABORT: $*"; exit 1; }

# wait_for <n> <ok-regex> <fail-regex> <timeout s>: the n-th match of ok-regex in the LOCAL stream file. No cluster read:
# the follow in capture.sh is the only reader. A fail-regex match, the timeout or a dead follow ends it early.
wait_for() {
  local n="$1" ok="$2" bad="$3" deadline=$(( $(date +%s) + $4 )) got
  while :; do
    got=$(grep -c -E -- "${ok}" "${RAW}/podlog.raw" 2>/dev/null || true)
    if [ "${got:-0}" -ge "${n}" ]; then say "seen ${got} line(s) matching /${ok}/"; return 0; fi
    if [ -n "${bad}" ] && grep -q -E -- "${bad}" "${RAW}/podlog.raw" 2>/dev/null; then
      say "FAILURE LINE: $(grep -E -- "${bad}" "${RAW}/podlog.raw" | tail -1 | redact | cut -c1-400)"; return 2
    fi
    if [ "$(date +%s)" -ge "${deadline}" ]; then say "TIMEOUT: ${got:-0} of ${n} line(s) matching /${ok}/"; return 1; fi
    kill -0 "$(cat "${RAW}/podlog.pid")" 2>/dev/null || { say "the log follow is not running"; return 3; }
    sleep 5
  done
}

on_exit() {
  local rc=$?
  set +e
  [ -d "${RAW}" ] && bash "${S}/capture.sh" stream-stop "${RAW}"
  if [ "${HANDBACK_DONE}" != true ]; then
    say "run.sh is exiting (rc=${rc}) before the hand-back completed: the restore runs now"
    bash "${S}/sweep.sh" trap
    # The trap does not redeploy: a 15-minute Argo CD cutover is the operator's step, said here with its command.
    if oc get secrets -n "${NS}" -l owner=helm,name=group-sync-dashboard -o name | grep -q . \
       || ! oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o name >/dev/null 2>&1; then
      say "THE LAB IS NOT ON ARGO CD (a Helm release is installed, or the Application is gone). To finish: (cd ${DEPLOY}/local-development && ./release-crc.sh --argocd main), then bash ${S}/sweep.sh trap-after-handback"
    fi
  fi
  rm -rf "${RAW}"
  say "run.sh ends rc=${rc}"
  exit "${rc}"
}

# ── 0. Preflight: reads and local work only; nothing on the cluster changes before the trap is set ────────────────
say "#310 Part A phase 2 — run ${RUN}, main ${MAIN_SHA}, renewals wanted ${RENEWALS}"
[ "$(oc whoami)" = kubeadmin ] || abort "the kubeconfig is not kubeadmin's"
podman info >/dev/null 2>&1 || abort "podman is not reachable: release-crc.sh builds the images"
[ "$(token_config)" = "{\"accessTokenMaxAgeSeconds\":${LIFETIME_FOUND}}" ] \
  || abort "oauth/cluster is not as found ($(token_config)): the restore would not return the lab to it"
[ -z "$(oc get secrets,roles.rbac.authorization.k8s.io,rolebindings.rbac.authorization.k8s.io -A -l "${RUN_LABEL}" -o name)$(oc get clusterrolebindings.rbac.authorization.k8s.io -l "${RUN_LABEL}" -o name)" ] \
  || abort "objects labelled ${RUN_LABEL} already exist"
[ -z "$(oc get leases.coordination.k8s.io -n "${NS}" "gsd-fleet-$(printf developer | shasum -a 256 | cut -c1-16)" -o name --ignore-not-found)" ] \
  || abort "developer's Lease exists: another walk is under way or was not cleaned"
oc get applications.argoproj.io -n openshift-gitops group-sync-dashboard -o name >/dev/null || abort "no Argo CD Application"
remote=$(git -C "${HERE}" remote get-url origin)
origin_main=$(git ls-remote "${remote}" refs/heads/main | cut -f1)
[ "${origin_main}" = "${MAIN_SHA}" ] || abort "GitHub's main is ${origin_main}, not ${MAIN_SHA}: the hand-back would deploy another commit"
if [ ! -d "${DEPLOY}" ]; then
  git clone -q --no-hardlinks --no-checkout "$(git -C "${HERE}" rev-parse --show-toplevel)" "${DEPLOY}"
  git -C "${DEPLOY}" remote set-url origin "${remote}"
  git -C "${DEPLOY}" checkout -q --detach "${MAIN_SHA}"
fi
mkdir -p "$(dirname "${DEPLOY}/${V}")"; cp "${HERE}/prepared/walk-values-selflogin.yaml" "${DEPLOY}/${V}"
[ "$(git -C "${DEPLOY}" rev-parse HEAD)" = "${MAIN_SHA}" ] || abort "${DEPLOY} is not at ${MAIN_SHA}"
[ -z "$(git -C "${DEPLOY}" status --porcelain -- . ":(exclude,top,literal)${V}")" ] || abort "${DEPLOY} is not clean"
T_START=$(now)
bash "${S}/baseline.sh" phase2-start >/dev/null
say "baseline: evidence/phase2-start-baseline.txt"
bash "${S}/labcheck.sh" phase2-as-found-informational || true   # 1 0 0 expected: the Argo configuration names it

# ── the trap, before the first write ──────────────────────────────────────────────────────────────────────────────
trap on_exit EXIT
trap 'exit 130' INT TERM HUP

# ── 1. The walk's two grants (prepared/walk-rbac.yaml) ─────────────────────────────────────────────────────────────
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

# ── 3. Follow the new pod from here; it leads once the previous pod's leader Lease expires (25–31 s on 2026-09-27) ──
bash "${S}/capture.sh" stream-start "${RAW}"
wait_for 1 'gsd\.leader .*(became leader|taking it)' '' 180 || abort "the walk pod did not take the leader Lease"

# ── 4. The configuration names only developer; then the lifetime ──────────────────────────────────────────────────
bash "${S}/labcheck.sh" phase2-after-deploy || abort "the lab check did not print 0 0 0 after the deploy"
bash "${S}/oauth_lifetime.sh" set "${LIFETIME_WALK}" phase2-set-600 || abort "oauth/cluster did not settle at ${LIFETIME_WALK}"

# ── 5. The password, only after the lab check ─────────────────────────────────────────────────────────────────────
bash "${S}/labcheck.sh" phase2-before-walk-secret || abort "the lab check did not print 0 0 0 before the walk Secret"
T_SECRET=$(now)
bash "${S}/walk_secret.sh" phase2
FAIL_RE=" (fleet-login-refused|fleet-login-failed|fleet-credential-suspended|self-login-failed) .*cluster=${WALK_CLUSTER}( |$)|cluster-unreachable .*cluster=${WALK_CLUSTER}( |$)"

# ── 6. Observe: the first session, then RENEWALS scheduled renewals, then two more poll cycles ────────────────────
wait_for 1 " fleet-login cluster=${WALK_CLUSTER} " "${FAIL_RE}" 240 || abort "no first self-login"
first=$(grep -E " fleet-login cluster=${WALK_CLUSTER} " "${RAW}/podlog.raw" | head -1)
at=$(cut -d' ' -f1 <<<"${first}" | sed -E 's/\.[0-9]+Z$/Z/'); exp=$(sed -E 's/.* expires_at=([^ ]+).*/\1/' <<<"${first}")
lifetime=$(( $(date -j -u -f %Y-%m-%dT%H:%M:%SZ "${exp}" +%s) - $(date -j -u -f %Y-%m-%dT%H:%M:%SZ "${at}" +%s) ))
say "first session: logged in ${at}, expires_at ${exp}: ${lifetime} s"
[ "${lifetime}" -ge 590 ] && [ "${lifetime}" -le 610 ] || abort "the served lifetime is ${lifetime} s, not ${LIFETIME_WALK}"
wait_for "${RENEWALS}" " self-login-renewed cluster=${WALK_CLUSTER} " "${FAIL_RE}" $(( RENEWALS * 540 + 300 )) \
  || abort "fewer than ${RENEWALS} renewals"
say "two more poll cycles, so the evidence shows polling after the last renewal"
sleep 130
bash "${S}/baseline.sh" phase2-observed >/dev/null
bash "${S}/capture.sh" stream-stop "${RAW}"
bash "${S}/capture.sh" podlog phase2 "${RAW}"
bash "${S}/capture.sh" metrics phase2 "${RAW}"
set +e
python3 "${S}/analyse.py" "${EVIDENCE}/phase2-podlog.txt" "${EVIDENCE}/phase2-metrics.txt" \
  --lifetime "${LIFETIME_WALK}" --renewals "${RENEWALS}" > "${EVIDENCE}/phase2-analysis.txt"
analysis_rc=$?
set -e
cat "${EVIDENCE}/phase2-analysis.txt"; say "analyse.py exited ${analysis_rc}"

# ── 7. Hand back: no password first, then the lifetime, then Argo, then what is left ────────────────────────────
say "the walk Secret: $(oc delete secrets -n "${NS}" -l "${RUN_LABEL}" --ignore-not-found 2>&1 | tr '\n' ' ')"
sweep_rc=0; bash "${S}/sweep.sh" handback-1 || sweep_rc=$?
[ "${sweep_rc}" = 0 ] || [ "${sweep_rc}" = 5 ] || abort "the restore of oauth/cluster did not complete (sweep.sh exited ${sweep_rc})"
say "release-crc.sh --argocd main (from ${DEPLOY})"
set +e
( cd "${DEPLOY}/local-development" && ./release-crc.sh --argocd main ) > "${EVIDENCE}/phase2-handback-release-crc-argocd-main.log" 2>&1
argo_rc=$?
set -e
say "release-crc.sh --argocd main exited ${argo_rc} (evidence/phase2-handback-release-crc-argocd-main.log)"
sweep_rc=0; bash "${S}/sweep.sh" handback-2 || sweep_rc=$?
say "sweep.sh handback-2 exited ${sweep_rc}"

# ── 8. The evidence at the end ────────────────────────────────────────────────────────────────────────────────────
set +e
bash "${S}/capture.sh" audit phase2-window "${T_START}"
bash "${S}/capture.sh" audit phase2-since-secret "${T_SECRET}"
bash "${S}/baseline.sh" phase2-end >/dev/null
bash "${S}/compare_baselines.sh" phase2-start phase2-end > "${EVIDENCE}/phase2-compare.txt"; compare_rc=$?
cat "${EVIDENCE}/phase2-compare.txt"
set -e
say "done: analysis rc=${analysis_rc}, argocd main rc=${argo_rc}, final sweep rc=${sweep_rc}, compare rc=${compare_rc}"
# Only a complete sweep ends the trap's duty; otherwise it runs the sweep once more and says what is left.
[ "${sweep_rc}" = 0 ] && HANDBACK_DONE=true
[ "${analysis_rc}" = 0 ] && [ "${sweep_rc}" = 0 ] && [ "${compare_rc}" = 0 ]
