set -u
S=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad
export KUBECONFIG="$S/kc-crc"
cd /Users/olasumbo/gitRepos/group-sync-dashboard/local-development
BASE=https://group-sync-dashboard.apps-crc.testing
echo "== admin set (kubeadmin)"
GSD_UI_PASSWORD=$(cat ~/.crc/machines/crc/kubeadmin-password) .venv/bin/python capture-screenshots.py \
  --base "$BASE" --login-user kubeadmin --provider developer --out "$S/shots/admin"; echo "admin capture exit $?"
echo "== self set (developer)"
DEV_PW=$(crc console --credentials 2>/dev/null | sed -n "s/.*-u developer -p \([^ ]*\) .*/\1/p" | head -1)
if [ -n "$DEV_PW" ]; then
  GSD_UI_PASSWORD="$DEV_PW" .venv/bin/python capture-screenshots.py \
    --base "$BASE" --login-user developer --provider developer --out "$S/shots/self"; echo "self capture exit $?"
else
  echo "no developer credential from crc; self set skipped"
fi
echo "== e2e walk"
GSD_UI_PASSWORD=$(cat ~/.crc/machines/crc/kubeadmin-password) ./e2e-walk/run_walk.sh \
  --base "$BASE" --login-user kubeadmin --out "$S/e2e/2026-09-24_d2b"; echo "e2e exit $?"
