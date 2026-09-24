source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
set -o pipefail
./local-development/release-crc.sh --values environments/crc-d2b-walk.yaml || { echo "release-crc exit $?"; exit 1; }
oc set volume deploy/group-sync-dashboard -n "$NS" --add --overwrite --name mock-creds --secret-name mock-cluster-creds --mount-path /etc/gsd/mock
oc rollout status deploy/group-sync-dashboard -n "$NS" --timeout=300s
echo "step3 done: $(pod)"
oc get pvc -n "$NS" -o custom-columns='NAME:.metadata.name,UID:.metadata.uid,VOLUME:.spec.volumeName,STATUS:.status.phase,CREATED:.metadata.creationTimestamp,KEEP:.metadata.annotations.helm\.sh/resource-policy' > "$WALK/pvc-after-step3.txt"
diff "$WALK/pvc-baseline.txt" "$WALK/pvc-after-step3.txt" && echo "PVCs: identical to the baseline (same UIDs, volumes, creation times)"
