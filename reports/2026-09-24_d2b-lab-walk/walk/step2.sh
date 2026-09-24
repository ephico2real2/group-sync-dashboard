source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
python3 - <<'PY'
import json, subprocess
groups = json.loads(subprocess.run(["oc", "get", "groups", "-o", "json"], check=True, capture_output=True, text=True).stdout)["items"]
for user in ("kubeadmin", "jane.smith", "developer", "test-user-002"):
    mine = [f"--as-group={g['metadata']['name']}" for g in groups if user in (g.get("users") or [])]
    can = subprocess.run(["oc", "auth", "can-i", "list", "clusterrolebindings", f"--as={user}",
                          "--as-group=system:authenticated", *mine], capture_output=True, text=True).stdout.strip()
    print(f"CRC  {user}: {can}")
PY
oc port-forward -n "$NS" svc/mock-openshift 16443:6443 >/dev/null & PF=$!; sleep 2
for u in kubeadmin jane.smith developer test-user-002; do
  printf 'mock %s: ' "$u"; curl -sk -X POST https://127.0.0.1:16443/_mock/sar-probe -H 'Content-Type: application/json' -d "{\"user\": \"$u\"}"; echo
done
kill "$PF"
