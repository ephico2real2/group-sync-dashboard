source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
for c in mock-sar mock-none; do
  oc exec -n "$NS" "$(pod)" -c dashboard -- curl -s -o /dev/null -w "DELETE $c: %{http_code}\n" -X DELETE -H 'X-Forwarded-User: kubeadmin' "http://127.0.0.1:8080/api/clusterconfigs/$c"
done
python3 - <<'PY'
import pathlib
p = pathlib.Path("environments/crc-d2b-walk.yaml"); t = p.read_text()
for name in ("shared-rnd", "mock"):
    i = t.index(f"  - name: {name}\n"); j = t.index("    enabled: true\n", i)
    t = t[:j] + "    enabled: false\n" + t[j + len("    enabled: true\n"):]
p.write_text(t)
PY
diff environments/crc.yaml environments/crc-d2b-walk.yaml
set -o pipefail
./local-development/release-crc.sh --values environments/crc-d2b-walk.yaml || { echo "release-crc exit $?"; exit 1; }
echo "== after the forced Helm apply, before mock-creds is patched again (review C2):"
oc get deploy/group-sync-dashboard -n "$NS" -o jsonpath='{range .spec.template.spec.volumes[*]}{.name}{" "}{end}'; echo
oc set volume deploy/group-sync-dashboard -n "$NS" --add --overwrite --name mock-creds --secret-name mock-cluster-creds --mount-path /etc/gsd/mock
oc rollout status deploy/group-sync-dashboard -n "$NS" --timeout=300s
oc get pvc -n "$NS" -o custom-columns='NAME:.metadata.name,UID:.metadata.uid,VOLUME:.spec.volumeName,STATUS:.status.phase,CREATED:.metadata.creationTimestamp,KEEP:.metadata.annotations.helm\.sh/resource-policy' > "$WALK/pvc-after-step9.txt"
diff "$WALK/pvc-baseline.txt" "$WALK/pvc-after-step9.txt" && echo "PVCs: identical to the baseline"
echo "== waiting for the first discovery"
for _ in $(seq 1 60); do resolved shared-rnd | grep -q . && break; sleep 10; done
resolved shared-rnd
api_as kubeadmin /api/whoami | python3 -c 'import json,sys; v=json.load(sys.stdin)["visibility"]["clusters"]; print("whoami clusters:", sorted(v)); print("absent as expected:", all(c not in v for c in ("shared-rnd","mock","mock-sar","mock-none")))'
oc port-forward -n "$NS" svc/mock-openshift 16443:6443 >/dev/null & PF=$!; sleep 2
log() { curl -sk https://127.0.0.1:16443/_mock/state | python3 -c 'import json, sys; print(json.load(sys.stdin)["recent_requests"])' | shasum; }
before=$(log); traffic 60; after=$(log); kill "$PF"
[ "$before" = "$after" ] && echo "the mock was not asked" || echo "the mock WAS asked"
