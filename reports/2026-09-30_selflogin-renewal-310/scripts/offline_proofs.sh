#!/usr/bin/env bash
# Phase 1's proofs, offline: nothing here reads or writes a cluster (`helm template`, pytest, python and a stub `oc`).
# Usage: PY=<python with the repo's test deps> bash scripts/offline_proofs.sh   -> evidence/offline-*.txt
#   1. offline-values.txt     the walk values are environments/crc.yaml outside their two WALK blocks (parsed), and
#                             the line diff, with the fleet account's username shown as <the fleet account>
#   2. offline-render.txt     helm template of the walk values and of the Argo CD shape (environments/crc.yaml + the
#                             Application's valuesObject): line counts first, then the rendered ConfigMap's fleet keys;
#                             the fleet account named 0 times in the walk (the file, its clusters.yaml, its whole
#                             render) and 1 time in the Argo shape — a count; the name lives in a variable
#   3. offline-rbac-diff.txt  rendered RBAC, the Argo shape -> the walk: without the walk grants REMOVED 1 (the
#                             ServiceAccount's get on ldap-oauth-bind-secret), with them REMOVED 0
#   4. offline-hermetic.txt   SPEC_S4e's self-login walk test and the self-login lifecycle tests, from this tree
#   5. offline-timing.txt     gsd/selflogin.py#renew_at on a 600 s session, the floor, and the schedule on a 60 s cycle
#   6. offline-analyse.txt    analyse.py on a synthetic log in the 2026-09-27 lines' exact shapes: a good run passes,
#                             and a run with the old session revoked first and a missed poll fails on exactly those
#   7. offline-restore.txt    sweep.sh (and oauth_lifetime.sh inside it) run three times against a stub `oc`: one patch
#                             in all, the keep-grant and developer's Lease left until the chart's grant is back
set -euo pipefail
S="$(cd "$(dirname "$0")" && pwd)"
HERE="$(cd "${S}/.." && pwd)"
ROOT="$(git -C "${HERE}" rev-parse --show-toplevel)"
EV="${HERE}/evidence"; mkdir -p "${EV}"
PY="${PY:?PY must name a python with pytest and the repository test dependencies}"
T=$(mktemp -d); trap 'rm -rf "${T}"' EXIT
CHART="${ROOT}/charts/group-sync-dashboard"
VALUES="${HERE}/prepared/walk-values-selflogin.yaml"
ARGO="${HERE}/prepared/argo-clusters-override.yaml"
F=$(yq -r '.clusterConfig.fleetAccount.username' "${ROOT}/environments/crc.yaml")   # never printed
[ -n "${F}" ] && [ "${F}" != null ] && [ "${F}" != developer ] || { echo "environments/crc.yaml names no fleet account" >&2; exit 2; }
stamp() { echo "# $(date -u +%Y-%m-%dT%H:%M:%SZ); tree $(git -C "${ROOT}" rev-parse --short=10 HEAD); helm $(helm version --short); $(yq --version); $("${PY}" --version)"; }
ok=true

# ── 1. the values ──────────────────────────────────────────────────────────────────────────────────────────────────
{
  stamp
  strip='del(.clusters) | del(.clusterConfig.fleetAccount)'
  a=$(yq -o=json -I=0 "${strip}" "${ROOT}/environments/crc.yaml"); b=$(yq -o=json -I=0 "${strip}" "${VALUES}")
  if [ "${a}" = "${b}" ]; then echo "PASS outside .clusters and .clusterConfig.fleetAccount, the walk values parse equal to environments/crc.yaml"
  else echo "FAIL the walk values differ from environments/crc.yaml outside the two WALK blocks"; ok=false; fi
  echo "the walk's .clusters: $(yq -o=json -I=0 '.clusters' "${VALUES}")"
  echo "the walk's .clusterConfig.fleetAccount: $(yq -o=json -I=0 '.clusterConfig.fleetAccount' "${VALUES}")"
  echo "the walk's .clusterConfig.fleetAccount.ping: $(yq -o=json -I=0 '.clusterConfig.fleetAccount.ping' "${VALUES}") (null: the chart default)"
  n=$(grep -c -F -- "${F}" "${VALUES}" || true)
  if [ "${n}" = 0 ]; then echo "PASS grep -c <the fleet account> in the walk values file: 0"
  else echo "FAIL grep -c <the fleet account> in the walk values file: ${n}"; ok=false; fi
  echo "# diff environments/crc.yaml prepared/walk-values-selflogin.yaml (the fleet account's username shown as <the fleet account>):"
  diff "${ROOT}/environments/crc.yaml" "${VALUES}" | sed "s/${F}/<the fleet account>/g" || true
} > "${EV}/offline-values.txt"

# ── 2. the render ──────────────────────────────────────────────────────────────────────────────────────────────────
helm template group-sync-dashboard "${CHART}" -n group-sync-dashboard -f "${VALUES}" > "${T}/walk.yaml"
helm template group-sync-dashboard "${CHART}" -n group-sync-dashboard -f "${ROOT}/environments/crc.yaml" -f "${ARGO}" > "${T}/argo.yaml"
cm() { yq -r 'select(.kind == "ConfigMap" and .metadata.name == "group-sync-dashboard-config") | .data["clusters.yaml"]' "$1"; }
cm "${T}/walk.yaml" > "${T}/walk-clusters.yaml"; cm "${T}/argo.yaml" > "${T}/argo-clusters.yaml"
{
  stamp
  for f in walk argo walk-clusters argo-clusters; do
    n=$(wc -l < "${T}/${f}.yaml" | tr -d ' ')
    echo "lines in the ${f} render: ${n}"; [ "${n}" -gt 0 ] || { echo "FAIL: an empty render"; ok=false; }
  done
  echo "walk clusters.yaml: $(grep -E '^(fleetAccountUsername|fleetPingEnabled|fleetPingIntervalSeconds|pollIntervalSeconds):' "${T}/walk-clusters.yaml" | tr '\n' ' ')"
  echo "walk clusters.yaml: ldapConnectionBootstrap lines: $(grep -E 'ldapConnectionBootstrap:' "${T}/walk-clusters.yaml" | sed -E 's/^ +//' | sort | uniq -c | tr -s ' ' | tr '\n' ';'); userSelfLogin: true lines: $(grep -c 'userSelfLogin: true' "${T}/walk-clusters.yaml" || true); saTokenLookup: true lines: $(grep -c 'saTokenLookup: true' "${T}/walk-clusters.yaml" || true)"
  w1=$(grep -c -F -- "${F}" "${T}/walk-clusters.yaml" || true); w2=$(grep -c -F -- "${F}" "${T}/walk.yaml" || true)
  a1=$(grep -c -F -- "${F}" "${T}/argo-clusters.yaml" || true)
  echo "grep -c <the fleet account>: walk clusters.yaml ${w1}, the whole walk render ${w2}; the Argo shape's clusters.yaml ${a1} (expected 1: the check tells the two apart)"
  if [ "${w1}" = 0 ] && [ "${w2}" = 0 ] && [ "${a1}" = 1 ] \
     && grep -qxE 'fleetAccountUsername: "?developer"?' "${T}/walk-clusters.yaml" \
     && ! grep -E 'ldapConnectionBootstrap:' "${T}/walk-clusters.yaml" | grep -qvE 'ldapConnectionBootstrap: "?developer"?$'; then
    echo "PASS the walk names only developer (SPEC_S4c §3.12 step 0)"
  else echo "FAIL the walk render names an account other than developer"; ok=false; fi
} > "${EV}/offline-render.txt"

# ── 3. RBAC ────────────────────────────────────────────────────────────────────────────────────────────────────────
{
  stamp
  echo "# before: the Argo CD shape; after: the walk values (then + prepared/walk-rbac.yaml). Lines: $(wc -l < "${T}/argo.yaml" | tr -d ' ') / $(wc -l < "${T}/walk.yaml" | tr -d ' ') / $(wc -l < "${HERE}/prepared/walk-rbac.yaml" | tr -d ' ')"
  echo "## without the walk grants"
  "${PY}" "${ROOT}/reports/2026-09-27_epic-c-walk-432/scripts/rbac_grants.py" "${T}/argo.yaml" "${T}/walk.yaml" | sed "s|${T}/||g"
  echo "## with prepared/walk-rbac.yaml beside the walk render"
  "${PY}" "${ROOT}/reports/2026-09-27_epic-c-walk-432/scripts/rbac_grants.py" "${T}/argo.yaml" "${T}/walk.yaml" "${HERE}/prepared/walk-rbac.yaml" \
    | sed -e "s|${T}/||g" -e "s|${HERE}/||g" | tee "${T}/with.txt"
} > "${EV}/offline-rbac-diff.txt"
if ! { grep -qx 'REMOVED 0' "${T}/with.txt" \
        && grep -qx 'REMOVED for ServiceAccount:group-sync-dashboard:group-sync-dashboard: 0' "${T}/with.txt"; }; then
  echo "FAIL: the walk with its grants removes an RBAC atom" >> "${EV}/offline-rbac-diff.txt"; ok=false
fi

# ── 4. hermetic tests ──────────────────────────────────────────────────────────────────────────────────────────────
{
  stamp
  cd "${ROOT}/local-development"
  export PYTHONPATH="${ROOT}/local-development:tests"
  echo "gsd imported from: $("${PY}" -c 'import gsd; print(gsd.__file__)' | sed "s|${ROOT}/|<this tree>/|")"
  for sel in \
    "tests/test_ping_account_scope.py::test_the_self_login_walk_arrangement_with_the_ping_on_presents_nothing_as_the_fleet_account" \
    "tests/test_ping_account_scope.py" \
    "tests/test_fleet_lifecycle.py tests/test_fleet_lifecycle_round3.py"; do
    echo "## pytest -p no:cacheprovider -q ${sel}"
    # shellcheck disable=SC2086  # two files in the last selection
    "${PY}" -m pytest -p no:cacheprovider -q ${sel} 2>&1 | tail -1 | tee -a "${T}/pytest"
  done
  # The 2 h branch of the margin (any lifetime of 8 h or more) cannot fire on a lab walk of minutes: it is proven by
  # these injected-clock cases, named one by one; R6 is the renewal's order on the 1/4 branch (a 3600 s session).
  echo "## pytest -p no:cacheprovider -v  R5 (the margin, both branches) and R6 (the order)"
  "${PY}" -m pytest -p no:cacheprovider -v \
    "tests/test_fleet_lifecycle.py::test_r5_renewal_is_a_fixed_margin_before_expiry" \
    "tests/test_fleet_lifecycle.py::test_r6_renewal_answers_the_new_login_before_the_old_token_is_revoked" 2>&1 \
    | grep -E '(PASSED|FAILED|ERROR)|passed|failed' | sed -E 's/ +\[ *[0-9]+%\]$//' | tee -a "${T}/pytest"
} > "${EV}/offline-hermetic.txt"
grep -qE 'failed|error' "${T}/pytest" && ok=false

# ── 5. timing ──────────────────────────────────────────────────────────────────────────────────────────────────────
PYTHONPATH="${ROOT}/local-development" "${PY}" - "${ROOT}" > "${EV}/offline-timing.txt" <<'PY'
"""The schedule a 600 s session gets from the shipped code, on the chart's 60 s poll cycle."""
from datetime import UTC, datetime, timedelta

import gsd
from gsd.fleetlogin import FleetSession
from gsd.selflogin import MARGIN, renew_at

import sys
print(f"gsd imported from: {gsd.__file__.replace(sys.argv[1] + '/', '<this tree>/')}")
t0, poll, life = datetime(2026, 9, 30, 12, 0, tzinfo=UTC), 60, 600
s = FleetSession("walk-self-login", "developer", "t", obtained_at=t0, expires_in=life, issuer="i", attempts=1)
print(f"MARGIN (the ceiling) = {MARGIN}; renew_at(600 s session) = expires_at - {(s.expires_at - renew_at(s)).total_seconds():.0f} s")
print("the margin by lifetime, from gsd.selflogin.renew_at (min(2 h, expires_in / 4)):")
for lifetime, what in ((31536000, "CRC as found (crc-org/snc oauth_cr.yaml)"), (86400, "OpenShift's documented default"),
                       (28800, "8 h: the two branches meet"), (3600, "a tightened estate"), (600, "this walk")):
    x = FleetSession("c", "u", "t", obtained_at=t0, expires_in=lifetime, issuer="i", attempts=1)
    margin = (x.expires_at - renew_at(x)).total_seconds()
    branch = "2 h cap" if margin == MARGIN.total_seconds() and lifetime / 4 > margin else (
        "both (equal)" if lifetime / 4 == MARGIN.total_seconds() else "1/4 of the lifetime")
    print(f"  {lifetime:>9} s  margin {margin:>6.0f} s  renews {(renew_at(x) - t0).total_seconds():>9.0f} s after login  [{branch}] {what}")
print(f"the floor: expires_in must exceed 4 x pollIntervalSeconds = {4 * poll} s; 600 > {4 * poll}: {life > 4 * poll}")
# The check runs at the top of each cycle; a cycle starts every `poll` seconds (Poller._wait_cycle subtracts the work).
cycle, session, k = t0, s, 0
while k < 3:
    cycle += timedelta(seconds=poll)
    if cycle >= renew_at(session):
        k += 1
        left = (session.expires_at - cycle).total_seconds()
        print(f"renewal {k} at login + {(cycle - t0).total_seconds():.0f} s: {(cycle - renew_at(session)).total_seconds():.0f} s "
              f"after renew_at, {left:.0f} s before the old session's expires_at")
        session = FleetSession("walk-self-login", "developer", "t", obtained_at=cycle, expires_in=life, issuer="i", attempts=1)
PY

# ── 6. analyse.py on synthetic logs in the real lines' shapes ──────────────────────────────────────────────────────
"${PY}" - "${T}" <<'PY'
"""Two synthetic runs, each line in the exact shape of reports/2026-09-27_epic-c-walk-432/evidence/step4-5-pod-podlog.txt."""
import sys
from datetime import datetime, timedelta

out = sys.argv[1]
t0 = datetime(2026, 9, 30, 18, 0, 0, 394561)
def ts(t): return t.strftime("%Y-%m-%dT%H:%M:%S.%f") + "123Z " + (t - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S,") + f"{t.microsecond // 1000:03d}-0400"
def z(t): return t.strftime("%Y-%m-%dT%H:%M:%SZ")
LOGIN = "{} INFO    gsd.fleetlogin fleet-login cluster=walk-self-login account=<redacted> tls=trusted-bundle oauth=https://oauth-openshift.apps-crc.testing expires_at={}"
LOGOUT = "{} INFO    gsd.fleetlogin fleet-logout cluster=walk-self-login account=<redacted> tls=trusted-bundle token=sha256~<redacted> outcome=revoked"
RENEWED = "{} INFO    gsd.selflogin self-login-renewed cluster=walk-self-login account=<redacted> expires_at={} renew_at={}"
POLLED = "{} INFO    gsd.poller polled walk-self-login: 3 CRs, 66 groups, 0 new sync event(s), 0 membership change(s)"

def run(bad: bool):
    lines, samples, t = [], [], t0
    lines.append(LOGIN.format(ts(t), z(t.replace(microsecond=0) + timedelta(seconds=600))))
    for k in range(1, 19):                       # 18 cycles of 60 s: renewals fall on cycles 8 and 16
        c = t0 + timedelta(seconds=60 * k)
        if k in (8, 16):
            new = c + timedelta(milliseconds=90)
            exp = new.replace(microsecond=0) + timedelta(seconds=600)
            if bad and k == 16:                  # the old session revoked BEFORE the new one exists
                lines.append(LOGOUT.format(ts(c + timedelta(milliseconds=10))))
                lines.append(LOGIN.format(ts(new), z(exp)))
            else:
                lines.append(LOGIN.format(ts(new), z(exp)))
                lines.append(LOGOUT.format(ts(new + timedelta(milliseconds=20))))
            lines.append(RENEWED.format(ts(new + timedelta(milliseconds=21)), z(exp), z(exp - timedelta(seconds=150))))
        if not (bad and k == 12):                # a missed poll: a 120 s gap
            lines.append(POLLED.format(ts(c + timedelta(milliseconds=300))))
        samples.append(f"{z(c + timedelta(seconds=5))} gsd_cluster_up{{cluster=\"walk-self-login\"}} 1.0")
        samples.append(f"{z(c + timedelta(seconds=5))} gsd_cluster_last_poll_timestamp_seconds{{cluster=\"walk-self-login\"}} "
                       f"{(c - datetime(1970, 1, 1)).total_seconds():.9e}")
    name = "bad" if bad else "good"
    open(f"{out}/{name}-podlog.txt", "w").write("\n".join(lines) + "\n")
    open(f"{out}/{name}-metrics.txt", "w").write("\n".join(samples) + "\n")

run(False); run(True)
PY
{
  stamp
  for run in good bad; do
    echo "## analyse.py on the ${run} synthetic run"
    set +e; "${PY}" "${S}/analyse.py" "${T}/${run}-podlog.txt" "${T}/${run}-metrics.txt"; rc=$?; set -e
    echo "exit ${rc}"
    echo "${run} ${rc}" >> "${T}/analyse-rc"
  done
} > "${EV}/offline-analyse.txt"
grep -qx 'good 0' "${T}/analyse-rc" && grep -qx 'bad 1' "${T}/analyse-rc" || ok=false

# ── 7. the restore, three times, against a stub oc ─────────────────────────────────────────────────────────────────
mkdir -p "${T}/state" "${T}/ev"
( cd "${T}/state" && printf 600 > lifetime && printf 16 > gen && printf 0 > chart \
  && for f in secret crb keep lease cm_developer; do printf 1 > "${f}"; done )
stub() {  # the stub first on PATH, under bash, with nothing inherited but what the scripts need
  env -i HOME="${HOME}" PATH="${S}/stub:/usr/bin:/bin:$(dirname "$(command -v jq)")" STUB_STATE="${T}/state" \
    EVIDENCE_DIR="${T}/ev" KUBECONFIG=/dev/null bash "${S}/sweep.sh" "$1" > "${T}/$1.out" 2>&1
}
{
  stamp
  set +e
  stub run-1; r1=$?
  echo "## run 1 — the walk values still deployed (no chart grant, the configuration names developer): exit ${r1} (5 = left on purpose)"
  sed -E 's/^[0-9TZ:-]+ //' "${T}/run-1.out"
  ( cd "${T}/state" && printf 1 > chart && printf 0 > cm_developer )   # what `release-crc.sh --argocd main` restores
  stub run-2; r2=$?
  echo "## run 2 — after the hand-back (the chart's grant back, developer named nowhere): exit ${r2}"
  sed -E 's/^[0-9TZ:-]+ //' "${T}/run-2.out"
  stub run-3; r3=$?
  echo "## run 3 — again, nothing left: exit ${r3}"
  sed -E 's/^[0-9TZ:-]+ //' "${T}/run-3.out"
  set -e
  patches=$(grep -c '^patch oauths' "${T}/state/calls" || true)
  deletes=$(grep -c '^delete ' "${T}/state/calls" || true)
  echo "## the stub's call log: ${patches} patch(es) of oauth/cluster in three runs; ${deletes} delete call(s) (each --ignore-not-found)"
  echo "final state: lifetime=$(cat "${T}/state/lifetime") secret=$(cat "${T}/state/secret") crb=$(cat "${T}/state/crb") keep=$(cat "${T}/state/keep") lease=$(cat "${T}/state/lease")"
  if [ "${r1}" = 5 ] && [ "${r2}" = 0 ] && [ "${r3}" = 0 ] && [ "${patches}" = 1 ] \
     && [ "$(cat "${T}/state/lifetime")" = 31536000 ] && [ "$(cat "${T}/state/keep")$(cat "${T}/state/lease")" = 00 ]; then
    echo "PASS the restore is safe to run twice (three times here): one patch, nothing removed early, everything removed at the end"
  else echo "FAIL"; fi
} > "${EV}/offline-restore.txt"
grep -q '^PASS' "${EV}/offline-restore.txt" || ok=false

for f in values render rbac-diff hermetic timing analyse restore; do echo "== evidence/offline-${f}.txt"; grep -E '^(PASS|FAIL)|REMOVED|passed|failed|renewal|floor|MARGIN|^exit|grep -c' "${EV}/offline-${f}.txt" || true; done
if ${ok}; then echo "ALL OFFLINE PROOFS PASS"; else echo "SOME OFFLINE PROOF FAILED"; exit 1; fi
