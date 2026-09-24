source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
rm environments/crc-d2b-walk.yaml
git status --short | head -3
set -o pipefail
./local-development/release-crc.sh --argocd || { echo "release-crc --argocd exit $?"; exit 1; }
python3 - "$WALK/syncpolicy.json" <<'PY'
import json, subprocess, sys
want = json.load(open(sys.argv[1]))
live = json.loads(subprocess.run(["oc", "get", "application", "group-sync-dashboard", "-n", "openshift-gitops",
                                  "-o", "jsonpath={.spec.syncPolicy}"], check=True, capture_output=True, text=True).stdout)
if live != want:
    subprocess.run(["oc", "patch", "application", "group-sync-dashboard", "-n", "openshift-gitops", "--type", "json",
                    "-p", json.dumps([{"op": "replace", "path": "/spec/syncPolicy", "value": want}])], check=True)
print("syncPolicy:", "restored" if live != want else "already the recorded one")
PY
oc get application "$APP" -n "$ARGO_NS" -o jsonpath='{.status.sync.status} {.status.health.status} {.status.sync.revision}{"\n"}'
oc get pvc -n "$NS" -o custom-columns='NAME:.metadata.name,UID:.metadata.uid,VOLUME:.spec.volumeName,STATUS:.status.phase,CREATED:.metadata.creationTimestamp,KEEP:.metadata.annotations.helm\.sh/resource-policy' > "$WALK/pvc-after-step10.txt"
diff "$WALK/pvc-baseline.txt" "$WALK/pvc-after-step10.txt" && echo "PVCs: identical to the baseline"
for _ in $(seq 1 60); do resolved shared-rnd | grep -q . && resolved shared-qa | grep -q . && break; sleep 10; done
resolved shared-rnd; resolved shared-qa
for u in kubeadmin developer test-user-002; do
  printf '%s: ' "$u"; api_as "$u" /api/whoami | python3 -c 'import json,sys; v=json.load(sys.stdin)["visibility"]["clusters"]; print({c: (v.get(c,{}).get("policy"), v.get(c,{}).get("scope")) for c in ("shared-rnd","shared-qa")})'
done
