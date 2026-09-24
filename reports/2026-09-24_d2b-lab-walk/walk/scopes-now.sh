source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
cat > "$WALK/scopes.py" <<'PY'
import json, sys
v = json.load(sys.stdin)["visibility"]["clusters"]
print("  ".join(c + "=" + str(v.get(c, {}).get("scope")) for c in sys.argv[1:]))
PY
for u in kubeadmin jane.smith developer test-user-002; do
  printf '  %-14s' "$u"; api_as "$u" /api/whoami | python3 "$WALK/scopes.py" dashboard shared-rnd shared-qa
done
echo "  tier warnings for shared-qa in the last 5 min: $(oc logs -n "$NS" "$(pod)" -c dashboard --since=5m | grep -c 'shared-qa: visibility tier')"
