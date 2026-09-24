source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
set -o pipefail
./local-development/release-crc.sh --values environments/crc-d2b-walk.yaml || { echo "release-crc exit $?"; exit 1; }
oc set volume deploy/group-sync-dashboard -n "$NS" --add --overwrite --name mock-creds --secret-name mock-cluster-creds --mount-path /etc/gsd/mock
oc rollout status deploy/group-sync-dashboard -n "$NS" --timeout=300s
echo "step3 done: $(pod)"
