#!/usr/bin/env bash
# Phase 1's proofs, offline: nothing here reads or writes a cluster (`helm template`, pytest, python, podman with no
# network, and a stub `oc`). Based on reports/2026-09-30_selflogin-renewal-310/scripts/offline_proofs.sh.
# Usage: PY=<python with the repo's test deps> [REHEARSAL_IMAGE=<a local dashboard image>] bash scripts/offline_proofs.sh
#   1. offline-values.txt       the walk values are environments/crc.yaml outside their two WALK blocks (parsed), their
#                               `clusters` are the Argo CD Application's override exactly, and the line diff, with the
#                               fleet account's username shown as <the fleet account>
#   2. offline-render.txt       helm template of the walk values and of the Argo CD shape: line counts, the rendered
#                               ConfigMap's fleet keys, the fleet account named 0 times in the walk and 1 in the Argo
#                               shape (a count), no stanza naming anyone, and the `leases` rule in both renders
#   3. offline-rbac-diff.txt    rendered RBAC, the Argo shape -> the walk: REMOVED 1 without the keep-grant, 0 with it
#   4. offline-lease-name.txt   developer's Lease name from gsd/fleetstate.py#lease_name — the username alone, no salt
#   5. offline-hermetic.txt     this walk's arrangement test, the spec's own step-6 pins, the ClaimHeld tests SPEC_S4c
#                               §3.11 names (R1, R2, D1, C5) one by one, and their suites whole
#   6. offline-coordinator.txt  the program extracted from the spec, compiled, pinned in run.sh, and run VERBATIM inside
#                               the dashboard image against a fake API server: the Lease absent, free, and held
#   7. offline-restore.txt      sweep.sh four times against a stub `oc`: nothing removed early, everything at the end
#   8. offline-audit.txt        capture.sh audit against a stub `oc`: the counts from synthetic records; a failed read
#                               and a log that starts after the window both refuse to count
#   9. offline-lint.txt         bash -n and shellcheck -x on every script
set -euo pipefail
S="$(cd "$(dirname "$0")" && pwd)"
HERE="$(cd "${S}/.." && pwd)"
ROOT="$(git -C "${HERE}" rev-parse --show-toplevel)"
EV="${HERE}/evidence"; mkdir -p "${EV}"
PY="${PY:?PY must name a python with pytest and the repository test dependencies}"
IMAGE="${REHEARSAL_IMAGE:-localhost/group-sync-dashboard:2.0.0-708e6be104}"
export PYTHONDONTWRITEBYTECODE=1    # nothing below may leave a __pycache__ in the tree
T=$(mktemp -d); trap 'rm -rf "${T}"' EXIT
CHART="${ROOT}/charts/group-sync-dashboard"
VALUES="${HERE}/prepared/walk-values-claimheld.yaml"
ARGO="${HERE}/prepared/argo-clusters-override.yaml"
F=$(yq -r '.clusterConfig.fleetAccount.username' "${ROOT}/environments/crc.yaml")   # never printed
[ -n "${F}" ] && [ "${F}" != null ] && [ "${F}" != developer ] || { echo "environments/crc.yaml names no fleet account" >&2; exit 2; }
# shellcheck disable=SC2016  # $1 is sed's, not the shell's
DEV_LEASE=$(sed -nE 's/^DEV_LEASE=(gsd-fleet-[0-9a-f]{16})$/\1/p' "${S}/lib.sh")
COORD_PIN=$(sed -nE 's/^COORD_SHA256=([0-9a-f]{64})$/\1/p' "${S}/run.sh")
stamp() { echo "# $(date -u +%Y-%m-%dT%H:%M:%SZ); tree $(git -C "${ROOT}" rev-parse --short=10 HEAD); helm $(helm version --short); $(yq --version); $("${PY}" --version)"; }
ok=true

# ── 1. the values ──────────────────────────────────────────────────────────────────────────────────────────────────
{
  stamp
  strip='del(.clusters) | del(.clusterConfig.fleetAccount)'
  a=$(yq -o=json -I=0 "${strip}" "${ROOT}/environments/crc.yaml"); b=$(yq -o=json -I=0 "${strip}" "${VALUES}")
  if [ "${a}" = "${b}" ]; then echo "PASS outside .clusters and .clusterConfig.fleetAccount, the walk values parse equal to environments/crc.yaml"
  else echo "FAIL the walk values differ from environments/crc.yaml outside the two WALK blocks"; ok=false; fi
  if [ "$(yq -o=json -I=0 '.clusters' "${VALUES}")" = "$(yq -o=json -I=0 '.clusters' "${ARGO}")" ]; then
    echo "PASS the walk's .clusters equal the Argo CD Application's override (prepared/argo-clusters-override.yaml): no walk stanza"
  else echo "FAIL the walk's .clusters are not the Argo override's"; ok=false; fi
  echo "the walk's .clusterConfig.fleetAccount: $(yq -o=json -I=0 '.clusterConfig.fleetAccount' "${VALUES}")"
  echo "the walk's .clusterConfig.fleetAccount.ping: $(yq -o=json -I=0 '.clusterConfig.fleetAccount.ping' "${VALUES}") (null: the chart default)"
  n=$(grep -c -F -- "${F}" "${VALUES}" || true)
  if [ "${n}" = 0 ]; then echo "PASS grep -c <the fleet account> in the walk values file: 0"
  else echo "FAIL grep -c <the fleet account> in the walk values file: ${n}"; ok=false; fi
  echo "# diff environments/crc.yaml prepared/walk-values-claimheld.yaml (the fleet account's username shown as <the fleet account>):"
  diff "${ROOT}/environments/crc.yaml" "${VALUES}" | sed "s/${F}/<the fleet account>/g" || true
} > "${EV}/offline-values.txt"

# ── 2. the render ──────────────────────────────────────────────────────────────────────────────────────────────────
helm template group-sync-dashboard "${CHART}" -n group-sync-dashboard -f "${VALUES}" > "${T}/walk.yaml"
helm template group-sync-dashboard "${CHART}" -n group-sync-dashboard -f "${ROOT}/environments/crc.yaml" -f "${ARGO}" > "${T}/argo.yaml"
cm() { yq -r 'select(.kind == "ConfigMap" and .metadata.name == "group-sync-dashboard-config") | .data["clusters.yaml"]' "$1"; }
cm "${T}/walk.yaml" > "${T}/walk-clusters.yaml"; cm "${T}/argo.yaml" > "${T}/argo-clusters.yaml"
leases() {  # every rule on leases in a render, with the role that holds it and the subjects bound to that role
  "${PY}" - "$1" <<'LEASES'
import json, sys, yaml
docs = [d for d in yaml.safe_load_all(open(sys.argv[1])) if isinstance(d, dict)]
for role in docs:
    if role.get("kind") not in ("Role", "ClusterRole"):
        continue
    rules = [r for r in role.get("rules") or [] if "leases" in (r.get("resources") or [])]
    if not rules:
        continue
    bound = sorted(f"{s['kind']}:{s.get('namespace', '')}:{s['name']}" for b in docs
                   if b.get("kind") in ("RoleBinding", "ClusterRoleBinding")
                   and b["roleRef"]["kind"] == role["kind"] and b["roleRef"]["name"] == role["metadata"]["name"]
                   for s in b.get("subjects") or [])
    print(json.dumps({"role": f"{role['kind']}/{role['metadata']['name']}", "rules": rules, "bound": bound}, sort_keys=True))
LEASES
}
{
  stamp
  for f in walk argo walk-clusters argo-clusters; do
    n=$(wc -l < "${T}/${f}.yaml" | tr -d ' ')
    echo "lines in the ${f} render: ${n}"; [ "${n}" -gt 0 ] || { echo "FAIL: an empty render"; ok=false; }
  done
  echo "walk clusters.yaml: $(grep -E '^(fleetAccountUsername|fleetPasswordSecret[A-Za-z]*|fleetPingEnabled|fleetPingIntervalSeconds|pollIntervalSeconds|discoveryIntervalSeconds|requestTimeoutSeconds):' "${T}/walk-clusters.yaml" | tr '\n' ' ')"
  echo "walk clusters.yaml: ldapConnectionBootstrap lines: $(grep -c 'ldapConnectionBootstrap:' "${T}/walk-clusters.yaml" || true); saTokenLookup: true lines: $(grep -c 'saTokenLookup: true' "${T}/walk-clusters.yaml" || true); userSelfLogin: true lines: $(grep -c 'userSelfLogin: true' "${T}/walk-clusters.yaml" || true)"
  w1=$(grep -c -F -- "${F}" "${T}/walk-clusters.yaml" || true); w2=$(grep -c -F -- "${F}" "${T}/walk.yaml" || true)
  a1=$(grep -c -F -- "${F}" "${T}/argo-clusters.yaml" || true)
  echo "grep -c <the fleet account>: walk clusters.yaml ${w1}, the whole walk render ${w2}; the Argo shape's clusters.yaml ${a1} (expected 1: the check tells the two apart)"
  if [ "${w1}" = 0 ] && [ "${w2}" = 0 ] && [ "${a1}" = 1 ] \
     && grep -qxE 'fleetAccountUsername: "?developer"?' "${T}/walk-clusters.yaml" \
     && ! grep -qE 'ldapConnectionBootstrap:|saTokenLookup: true|userSelfLogin: true' "${T}/walk-clusters.yaml"; then
    echo "PASS the walk names only developer, and no stanza names anyone (SPEC_S4c §3.12 step 0)"
  else echo "FAIL the walk render names an account other than developer, or carries a stanza"; ok=false; fi
  echo "the leases rule, walk render:  $(leases "${T}/walk.yaml")"
  echo "the leases rule, Argo render:  $(leases "${T}/argo.yaml")"
  if [ -n "$(leases "${T}/walk.yaml")" ] && [ "$(leases "${T}/walk.yaml")" = "$(leases "${T}/argo.yaml")" ]; then
    echo "PASS both renders carry the same leases rule (get, create, update): step 6's processes act as the ServiceAccount"
  else echo "FAIL the leases rule differs or is absent"; ok=false; fi
} > "${EV}/offline-render.txt"

# ── 3. RBAC ────────────────────────────────────────────────────────────────────────────────────────────────────────
{
  stamp
  echo "# before: the Argo CD shape; after: the walk values (then + prepared/walk-rbac.yaml). Lines: $(wc -l < "${T}/argo.yaml" | tr -d ' ') / $(wc -l < "${T}/walk.yaml" | tr -d ' ') / $(wc -l < "${HERE}/prepared/walk-rbac.yaml" | tr -d ' ')"
  echo "## without the walk grant"
  "${PY}" "${ROOT}/reports/2026-09-27_epic-c-walk-432/scripts/rbac_grants.py" "${T}/argo.yaml" "${T}/walk.yaml" | sed "s|${T}/||g" | tee "${T}/without.txt"
  echo "## with prepared/walk-rbac.yaml beside the walk render"
  "${PY}" "${ROOT}/reports/2026-09-27_epic-c-walk-432/scripts/rbac_grants.py" "${T}/argo.yaml" "${T}/walk.yaml" "${HERE}/prepared/walk-rbac.yaml" \
    | sed -e "s|${T}/||g" -e "s|${HERE}/||g" | tee "${T}/with.txt"
} > "${EV}/offline-rbac-diff.txt"
if ! { grep -qx 'REMOVED 1' "${T}/without.txt" && grep -qx 'REMOVED 0' "${T}/with.txt" \
        && grep -qx 'REMOVED for ServiceAccount:group-sync-dashboard:group-sync-dashboard: 0' "${T}/with.txt"; }; then
  echo "FAIL: the walk with its grant removes an RBAC atom, or the grant is not the one atom it keeps" >> "${EV}/offline-rbac-diff.txt"; ok=false
else
  echo "PASS REMOVED 1 without the keep-grant (the ServiceAccount's get on ldap-oauth-bind-secret), REMOVED 0 with it" >> "${EV}/offline-rbac-diff.txt"
fi

# ── 4. developer's Lease name, from the code ───────────────────────────────────────────────────────────────────────
PYTHONPATH="${ROOT}/local-development" "${PY}" - "${ROOT}" "${DEV_LEASE}" > "${EV}/offline-lease-name.txt" <<'PY'
"""The Lease step 6 names, derived by the shipped code: the username alone. The password Secret's uid salts the
DIGEST a Lease records (lease_digest), never its name — so a new walk Secret, or none, gives the same Lease."""
import inspect
import sys

from gsd.fleetstate import lease_digest, lease_name

root, pinned = sys.argv[1], sys.argv[2]
print(f"gsd imported from: {inspect.getfile(lease_name).replace(root + '/', '<this tree>/')}")
print(f"lease_name{inspect.signature(lease_name)}; lease_digest{inspect.signature(lease_digest)}")
print(f"lease_name('developer') = {lease_name('developer')}; lib.sh's DEV_LEASE = {pinned}; the spec's = gsd-fleet-88fa0d759f845b47")
print("PASS" if lease_name("developer") == pinned == "gsd-fleet-88fa0d759f845b47" else "FAIL")
PY
grep -qx PASS "${EV}/offline-lease-name.txt" || ok=false

# ── 5. hermetic tests ──────────────────────────────────────────────────────────────────────────────────────────────
{
  stamp
  cd "${ROOT}/local-development"
  export PYTHONPATH="${ROOT}/local-development:${ROOT}/local-development/tests"
  echo "gsd imported from: $("${PY}" -c 'import gsd; print(gsd.__file__)' | sed "s|${ROOT}/|<this tree>/|")"
  run() { "${PY}" -m pytest -p no:cacheprovider -p conftest "$@" 2>&1; }
  echo "## this walk's arrangement: pytest -v scripts/test_step6_arrangement.py"
  run -v "${S}/test_step6_arrangement.py" | grep -E 'PASSED|FAILED|ERROR|passed|failed' | sed -E -e 's/ +\[ *[0-9]+%\]$//' -e "s|${HERE}/||" | tee -a "${T}/pytest"
  echo "## the spec's own step-6 pins: pytest -v tests/test_s4c_step6_walk.py"
  run -v tests/test_s4c_step6_walk.py | grep -E 'PASSED|FAILED|ERROR|passed|failed' | sed -E 's/ +\[ *[0-9]+%\]$//' | tee -a "${T}/pytest"
  echo "## ClaimHeld across processes, the tests SPEC_S4c §3.11 names: pytest -v"
  run -v \
    "tests/test_fleet_lifecycle.py::test_r1_two_processes_cannot_both_win_one_claim_and_no_claim_is_no_bind" \
    "tests/test_fleet_lifecycle.py::test_r2_the_budget_over_the_system_one_authorize_across_two_processes_three_targets_a_restart_and_an_edit" \
    "tests/test_fleet_lifecycle.py::test_d1_clock_skew_does_not_admit_a_second_bind" \
    "tests/test_fleet_lifecycle.py::test_d1_skew_takeover_at_each_point_of_the_attempt" \
    "tests/test_fleet_lifecycle.py::test_d1_a_paused_winner_resumes_after_the_takeover_and_does_not_bind" \
    "tests/test_fleet_lifecycle.py::test_d1_paused_winner_success_clears_its_own_reservation_on_409" \
    "tests/test_fleet_lifecycle.py::test_d1_paused_winner_complete_does_not_erase_a_foreign_refusal" \
    | grep -E 'PASSED|FAILED|ERROR|passed|failed' | sed -E 's/ +\[ *[0-9]+%\]$//' | tee -a "${T}/pytest"
  for sel in "tests/test_fleet_lifecycle.py tests/test_fleet_lifecycle_round3.py tests/test_fleet_gate_backstop.py" \
             "tests/test_ping_account_scope.py"; do
    echo "## pytest -q ${sel}"
    # shellcheck disable=SC2086  # several files in one selection
    run -q ${sel} | tail -1 | tee -a "${T}/pytest"
  done
} > "${EV}/offline-hermetic.txt"
# A test NAME may say "failed" (test_step6_coordinator_shows_why_b_failed): match the outcome words only.
grep -qE ' (FAILED|ERROR)$|[0-9]+ (failed|errors?)[ ,]' "${T}/pytest" && ok=false
[ "$(grep -cE '^=+ [0-9]+ passed' "${T}/pytest" || true)" = 3 ] && [ "$(grep -cE '^[0-9]+ passed' "${T}/pytest" || true)" = 2 ] || ok=false

# ── 6. the coordinator: extracted, compiled, pinned, and rehearsed verbatim in the image ───────────────────────────
mkdir -p "${T}/rehearse"; printf 'group-sync-dashboard' > "${T}/rehearse/namespace"
cat > "${T}/rehearse/clusters.yaml" <<'YAML'
clusters:
  - name: dashboard
    dashboardController: true
    apiUrl: http://127.0.0.1:18443
    tokenEnv: GSD_REHEARSAL_TOKEN
    enabled: true
requestTimeoutSeconds: 15
YAML
{
  stamp
  echo "## the extraction: ${PY} scripts/extract_step6.py <this tree> <out>  (the repository's own tests/test_s4c_step6_walk.py regexes)"
  "${PY}" "${S}/extract_step6.py" "${ROOT}" "${T}/coordinator.py" | tee "${T}/extracted"
  sha=$(sed -n 2p "${T}/extracted")
  echo "## python -m py_compile: $("${PY}" -c 'import sys; compile(open(sys.argv[1], encoding="utf-8").read(), sys.argv[1], "exec"); print("compiles")' "${T}/coordinator.py")"
  if [ "${sha}" = "${COORD_PIN}" ]; then echo "PASS run.sh pins COORD_SHA256=${COORD_PIN}, the program extracted here"
  else echo "FAIL run.sh pins ${COORD_PIN}, the extraction gives ${sha}"; fi
  echo "## the image's gsd against this tree's: every local-development/gsd/**/*.py by sha256 (${IMAGE})"
  ( cd "${ROOT}/local-development" && find gsd -name '*.py' | sort | xargs shasum -a 256 ) > "${T}/tree.sha"
  podman run --rm --network none --entrypoint python3.14 "${IMAGE}" -c '
import hashlib, pathlib
root = pathlib.Path("/install/lib/python3.14/site-packages")
for p in sorted((root / "gsd").rglob("*.py")):
    print(f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(root)}")' > "${T}/image.sha"
  if diff "${T}/tree.sha" "${T}/image.sha" > "${T}/sha.diff"; then
    echo "PASS $(wc -l < "${T}/tree.sha" | tr -d ' ') modules, identical: the rehearsal runs the code main ships"
  else echo "FAIL the image's gsd differs from this tree's:"; cat "${T}/sha.diff"; fi
  for scenario in absent free held; do
    echo "## the rehearsal, the Lease ${scenario}: podman run -i --network none … ${IMAGE} python3.14 /walk/rehearse_step6.py ${scenario} < <the program>"
    set +e
    podman run --rm -i --network none \
      -v "${T}/rehearse/namespace:/var/run/secrets/kubernetes.io/serviceaccount/namespace:ro" \
      -v "${T}/rehearse/clusters.yaml:/etc/gsd/clusters.yaml:ro" \
      -v "${S}/stub/rehearse_step6.py:/walk/rehearse_step6.py:ro" \
      -e GSD_CONFIG=/etc/gsd/clusters.yaml -e GSD_REHEARSAL_TOKEN=not-a-token \
      --entrypoint python3.14 "${IMAGE}" /walk/rehearse_step6.py "${scenario}" < "${T}/coordinator.py" > "${T}/${scenario}.out" 2>&1
    rc=$?
    set -e
    sed -E 's/until [0-9T:-]+Z/until <instant>/' "${T}/${scenario}.out"
    echo "exit ${rc}"
    echo "${scenario} ${rc}" >> "${T}/rehearsal-rc"
  done
} > "${EV}/offline-coordinator.txt" 2>&1
grep -q '^PASS run.sh pins' "${EV}/offline-coordinator.txt" || ok=false
grep -q '^PASS [0-9]* modules, identical' "${EV}/offline-coordinator.txt" || ok=false
for s in absent free; do
  grep -qx "${s} 0" "${T}/rehearsal-rc" && grep -qx "HELD walk-step6-a ${DEV_LEASE}" "${T}/${s}.out" \
    && grep -q "^ClaimHeld walk-step6-a holds ${DEV_LEASE} until " "${T}/${s}.out" && grep -qx RELEASED "${T}/${s}.out" \
    && grep -q '^# fake API: the Lease at the end: .*"holderIdentity": ""' "${T}/${s}.out" || ok=false
done
grep -qx 'held 2' "${T}/rehearsal-rc" && grep -qx 'ABORT: process A did not hold' "${T}/held.out" \
  && [ "$(grep -cE '^#   (POST|PUT) ' "${T}/held.out" || true)" = 0 ] || ok=false

# ── 7. the restore, four times, against a stub oc ──────────────────────────────────────────────────────────────────
mkdir -p "${T}/state" "${T}/ev"
( cd "${T}/state" && printf 0 > chart && printf 0 > secret && printf 1 > keep && printf 1 > cm_developer && printf held > lease )
stub() {  # the stub first on PATH, under bash, with nothing inherited but what the scripts need
  env -i HOME="${HOME}" PATH="${S}/stub:/usr/bin:/bin:$(dirname "$(command -v jq)")" STUB_STATE="${T}/state" \
    EVIDENCE_DIR="${T}/ev" KUBECONFIG=/dev/null bash "${S}/sweep.sh" "$1" > "${T}/$1.out" 2>&1
}
{
  stamp
  set +e
  stub run-1; r1=$?
  echo "## run 1 — the walk values deployed (no chart grant, the configuration names developer, A's claim live): exit ${r1} (5 = left on purpose)"
  sed -E 's/^[0-9TZ:-]+ //' "${T}/run-1.out"
  ( cd "${T}/state" && printf 1 > chart && printf 0 > cm_developer )   # what `release-crc.sh --argocd main` restores
  stub run-2; r2=$?
  echo "## run 2 — after the hand-back, A's claim still live (a coordinator killed inside its 195 s): exit ${r2}"
  sed -E 's/^[0-9TZ:-]+ //' "${T}/run-2.out"
  printf free > "${T}/state/lease"                                      # the claim released, or past its duration
  stub run-3; r3=$?
  echo "## run 3 — the claim released: exit ${r3}"
  sed -E 's/^[0-9TZ:-]+ //' "${T}/run-3.out"
  stub run-4; r4=$?
  echo "## run 4 — again, nothing left: exit ${r4}"
  sed -E 's/^[0-9TZ:-]+ //' "${T}/run-4.out"
  set -e
  echo "## the stub's call log: $(grep -c '^delete ' "${T}/state/calls" || true) delete call(s) (each --ignore-not-found); unexpected calls: $(cat "${T}"/run-*.out | grep -c 'unexpected call' || true)"
  echo "final state: secret=$(cat "${T}/state/secret") keep=$(cat "${T}/state/keep") lease=$(cat "${T}/state/lease")"
  if [ "${r1}" = 5 ] && [ "${r2}" = 5 ] && [ "${r3}" = 0 ] && [ "${r4}" = 0 ] \
     && grep -q '2. LEFT: the keep-grant stays' "${T}/run-1.out" && grep -q '3. LEFT: .* still names developer' "${T}/run-1.out" \
     && grep -q 'removing the keep-grant' "${T}/run-2.out" && grep -q '3. LEFT: .* a live claim holds it' "${T}/run-2.out" \
     && [ "$(cat "${T}/state/keep")$(cat "${T}/state/lease")" = 0absent ]; then
    echo "PASS the restore is safe to run again and again: nothing removed early (the keep-grant before the chart's grant, the Lease before the configuration stops naming developer or while a claim is live), everything removed at the end"
  else echo "FAIL"; fi
} > "${EV}/offline-restore.txt"
grep -q '^PASS' "${EV}/offline-restore.txt" || ok=false

# ── 8. the audit capture against a stub oc ─────────────────────────────────────────────────────────────────────────
"${PY}" - "${T}/state" <<'PY'
"""Synthetic oauth-server audit records in the shape capture.sh reads: in and out of the window, three users."""
import json
import sys

def record(at, user, decision="allow", code=302, uri="/oauth/authorize?client_id=openshift-challenging-client&response_type=token"):
    ann = {"authentication.openshift.io/decision": decision}
    if user:
        ann["authentication.openshift.io/username"] = user
    return json.dumps({"stage": "ResponseComplete", "requestURI": uri, "stageTimestamp": at, "annotations": ann,
                       "responseStatus": {"code": code}})

rows = [record("2026-09-30T09:00:00.000000Z", "developer"),                  # before the window
        record("2026-09-30T10:00:01.000000Z", "developer"),                  # in it
        record("2026-09-30T10:00:02.000000Z", "developer", "deny", 401),
        record("2026-09-30T10:00:03.000000Z", "stub-fleet-account"),
        record("2026-09-30T10:00:04.000000Z", ""),
        record("2026-09-30T10:00:05.000000Z", "someone-else"),               # never printed, never counted
        record("2026-09-30T10:00:06.000000Z", "developer", uri="/oauth/authorize?client_id=console"),
        record("2026-09-30T11:00:00.000000Z", "developer")]                  # after it
open(f"{sys.argv[1]}/audit.log", "w").write("\n".join(rows) + "\n")
PY
audit() {
  env -i HOME="${HOME}" PATH="${S}/stub:/usr/bin:/bin:$(dirname "$(command -v jq)")" STUB_STATE="${T}/state" \
    EVIDENCE_DIR="${T}/ev" KUBECONFIG=/dev/null bash "${S}/capture.sh" audit "$@" > /dev/null 2>&1
}
{
  stamp
  set +e
  audit stub-window 2026-09-30T10:00:00Z 2026-09-30T10:30:00Z; a1=$?
  echo "## [10:00:00Z, 10:30:00Z) over 8 synthetic records: exit ${a1}"; cat "${T}/ev/stub-window-audit.txt"
  audit stub-late 2026-09-30T08:00:00Z; a2=$?
  echo "## a window that starts before the earliest record (09:00:00Z): exit ${a2} (3 = refuses to count)"; cat "${T}/ev/stub-late-audit.txt"
  : > "${T}/state/audit.log"
  audit stub-empty 2026-09-30T10:00:00Z; a3=$?
  echo "## nothing read: exit ${a3} (2 = refuses to count)"; cat "${T}/ev/stub-empty-audit.txt"
  set -e
  if [ "${a1}" = 0 ] && [ "${a2}" = 3 ] && [ "${a3}" = 2 ] \
     && grep -qx '#   developer authorize records, any decision: 2' "${T}/ev/stub-window-audit.txt" \
     && grep -qx "#   the fleet account's authorize records, any decision: 1" "${T}/ev/stub-window-audit.txt" \
     && ! grep -q 'someone-else\|stub-fleet-account' "${T}/ev/stub-window-audit.txt"; then
    echo "PASS the counts are the window's (developer 2, the fleet account 1, unnamed), and a read that is empty or starts late never counts as 0"
  else echo "FAIL"; fi
} > "${EV}/offline-audit.txt"
grep -q '^PASS' "${EV}/offline-audit.txt" || ok=false

# ── 9. lint ────────────────────────────────────────────────────────────────────────────────────────────────────────
{
  stamp
  for f in "${S}"/*.sh "${S}/stub/oc"; do bash -n "${f}" && echo "bash -n: ${f#"${HERE}"/}"; done
  if (cd "${S}" && shellcheck -x ./*.sh stub/oc); then echo "PASS shellcheck $(shellcheck --version | sed -n 's/^version: //p') -x: no finding"; else echo "FAIL shellcheck"; fi
} > "${EV}/offline-lint.txt" 2>&1
grep -q '^PASS' "${EV}/offline-lint.txt" || ok=false

for f in values render rbac-diff lease-name hermetic coordinator restore audit lint; do
  echo "== evidence/offline-${f}.txt"; grep -E '^(PASS|FAIL)|REMOVED|passed|failed|^exit|^HELD|^ClaimHeld|^RELEASED|^ABORT' "${EV}/offline-${f}.txt" || true
done
if ${ok}; then echo "ALL OFFLINE PROOFS PASS"; else echo "SOME OFFLINE PROOF FAILED"; exit 1; fi
