#!/usr/bin/env bash
# PROOF 1 — #291's live proof as `developer`, never the fleet account: local-development/tests/test_live_fleet_login.py
# against the lab's API, with the OAuthAccessToken counts read by the test itself (before, during, after) and by
# capture.sh tokens around it (developer's and the fleet account's, counts only).
#   GSD_WALK_TMP=<a directory outside the repo> KUBECONFIG=<the lab's cluster-admin kubeconfig> scripts/proof1.sh
# developer's password is read from `crc console --credentials` into the test's environment only, never printed.
# The CA bundle is openshift-config/enterprise-and-cluster-ca-bundle written to a file in GSD_WALK_TMP: it verifies
# both api.crc.testing:6443 and oauth-openshift.apps-crc.testing (evidence/p1-ca-check.txt). The test's output passes
# through a sed that replaces every `sha256~` value before it reaches the folder (the test prints token_name=).
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
s="${here}/scripts"; ev="${here}/evidence"
repo="$(cd "${here}/../.." && pwd)"
py=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
: "${GSD_WALK_TMP:?}"; : "${KUBECONFIG:?}"
export GSD_WALK_TMP KUBECONFIG
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
ca="${GSD_WALK_TMP}/ca.crt"

oc get configmaps -n openshift-config enterprise-and-cluster-ca-bundle -o jsonpath='{.data.ca-bundle\.crt}' > "${ca}"
{
  echo "# oc get configmaps -n openshift-config enterprise-and-cluster-ca-bundle -o jsonpath='{.data.ca-bundle\\.crt}' > <tmp>/ca.crt"
  echo "# at $(now); certificates in the bundle: $(grep -c 'BEGIN CERTIFICATE' "${ca}")"
  for h in api.crc.testing:6443 oauth-openshift.apps-crc.testing:443; do
    echo "# openssl s_client -connect ${h} -servername ${h%:*} -CAfile <tmp>/ca.crt"
    openssl s_client -connect "${h}" -servername "${h%:*}" -CAfile "${ca}" < /dev/null 2> /dev/null | grep 'Verify return code'
  done
} > "${ev}/p1-ca-check.txt"

"${s}/capture.sh" tokens p1-before
{
  echo "# cd local-development && PYTHONPATH=<worktree>/local-development GSD_LIVE_LOGIN_API=https://api.crc.testing:6443 \\"
  echo "#   GSD_LIVE_LOGIN_USER=developer GSD_LIVE_LOGIN_PASSWORD=<crc console --credentials> GSD_LIVE_LOGIN_CA=<tmp>/ca.crt \\"
  echo "#   ${py} -m pytest -p no:cacheprovider tests/test_live_fleet_login.py -v -s --tb=short | sed 's/sha256~<token name>/sha256~<redacted>/'"
  echo "# started $(now)"
  rc=0
  ( cd "${repo}/local-development" && \
    PYTHONPATH="${repo}/local-development" PYTHONDONTWRITEBYTECODE=1 \
    GSD_LIVE_LOGIN_API=https://api.crc.testing:6443 GSD_LIVE_LOGIN_USER=developer GSD_LIVE_LOGIN_CA="${ca}" \
    GSD_LIVE_LOGIN_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
    "${py}" -m pytest -p no:cacheprovider tests/test_live_fleet_login.py -v -s --tb=short 2>&1 ) \
    | sed -E 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g' || rc=$?
  echo "# ended $(now); pytest pipeline exit ${rc}"
} > "${ev}/p1-pytest.txt"
"${s}/capture.sh" tokens p1-after
rm -f "${ca}"
grep -E 'passed|failed|skipped|error' "${ev}/p1-pytest.txt" | tail -1
