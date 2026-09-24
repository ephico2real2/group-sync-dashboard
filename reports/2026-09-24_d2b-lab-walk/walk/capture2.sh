set -u
S=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad
export KUBECONFIG="$S/kc-crc"
cd /Users/olasumbo/gitRepos/group-sync-dashboard/local-development
BASE=https://group-sync-dashboard.apps-crc.testing
GSD_UI_PASSWORD=$(cat ~/.crc/machines/crc/kubeadmin-password) .venv/bin/python capture-screenshots.py \
  --base "$BASE" --login-user kubeadmin --provider developer --out "$S/shots2/admin"; echo "admin capture exit $?"
DEV_PW=$(crc console --credentials 2>/dev/null | sed -n "s/.*-u developer -p \([^ ]*\) .*/\1/p" | head -1)
GSD_UI_PASSWORD="$DEV_PW" .venv/bin/python capture-screenshots.py \
  --base "$BASE" --login-user developer --provider developer --out "$S/shots2/self"; echo "self capture exit $?"
