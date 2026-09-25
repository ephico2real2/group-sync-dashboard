# #293 on the lab: one labelled ConfigMap, two stanzas → two generated Secrets; removal; a repeated name; a credential; cleanup.
export KUBECONFIG=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/kc-crc
D=/private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/deploy293
PY=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python
NS=group-sync-dashboard
state() { $PY "$D/state.py"; }
wait_for() {  # wait_for <label> <python expression over s (the state dict)> [max seconds]
  local label="$1" expr="$2" max="${3:-900}" t=0
  while [ $t -lt $max ]; do
    if state | $PY -c "import json,sys; s=json.load(sys.stdin); sys.exit(0 if ($expr) else 1)"; then echo "   [$label] met after ${t}s"; return 0; fi
    sleep 20; t=$((t+20))
  done
  echo "   [$label] NOT met after ${max}s"; return 1
}
cm() {  # cm <file>: apply the ConfigMap body from a file
  oc apply -n $NS -f "$1"
}
echo "# #293 proof — $(date -u +%FT%TZ) — $(oc get application group-sync-dashboard -n openshift-gitops -o jsonpath='{.status.sync.revision}')"
echo "== 0. baseline"; state
cat > "$D/cm-1.yaml" <<'YAML'
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-onboarding
  namespace: group-sync-dashboard
  labels:
    groupsync-dashboard.io/config-type: onboard
data:
  clusters.yaml: |
    clusters:
      - name: cm-demo-a
        apiUrl: https://api.crc.testing:6443
        saTokenLookup: true
      - name: cm-demo-b
        apiUrl: https://192.168.127.2:6443
        saTokenLookup: true
        insecureSkipVerify: true
YAML
echo "== 1. one ConfigMap, two stanzas (A verified TLS; B by IP with insecureSkipVerify)"; cm "$D/cm-1.yaml"
wait_for "both Secrets generated and both clusters ok" "s['secrets'].get('gsd-cluster-cm-demo-a')=='configmap-onboarding' and s['secrets'].get('gsd-cluster-cm-demo-b')=='configmap-onboarding' and s['clusters'].get('cm-demo-a',{}).get('status')=='ok' and s['clusters'].get('cm-demo-b',{}).get('status')=='ok'" 900
state
oc get secret -n $NS gsd-cluster-cm-demo-b -o json | $PY -c 'import json,sys,base64; d=json.load(sys.stdin); c=json.loads(base64.b64decode(d["data"]["config"])); print("   B tlsClientConfig:", c.get("tlsClientConfig")); print("   B annotations:", sorted(d["metadata"]["annotations"]))'
bash "$D/shots.sh" step1
cat > "$D/cm-2.yaml" <<'YAML'
apiVersion: v1
kind: ConfigMap
metadata:
  name: cluster-onboarding
  namespace: group-sync-dashboard
  labels:
    groupsync-dashboard.io/config-type: onboard
data:
  clusters.yaml: |
    clusters:
      - name: cm-demo-a
        apiUrl: https://api.crc.testing:6443
        saTokenLookup: true
      - name: cm-demo-dup
        apiUrl: https://api.crc.testing:6443
        saTokenLookup: true
      - name: cm-demo-dup
        apiUrl: https://api.crc.testing:6443
        saTokenLookup: true
      - name: cm-demo-cred
        apiUrl: https://api.crc.testing:6443
        saTokenLookup: true
        bearerToken: not-a-real-token
YAML
echo "== 2. B removed; a name repeated; a credential in a stanza"; cm "$D/cm-2.yaml"
wait_for "B deleted, A ok, dup and cred refused" "'gsd-cluster-cm-demo-b' not in s['secrets'] and s['clusters'].get('cm-demo-a',{}).get('status')=='ok' and 'gsd-cluster-cm-demo-dup' not in s['secrets'] and 'gsd-cluster-cm-demo-cred' not in s['secrets'] and sum(1 for f in s['findings'] if f['code']=='duplicate-cluster-name')>=2 and any(f['code']=='onboarding-invalid' for f in s['findings'])" 900
state
bash "$D/shots.sh" step2
echo "== 3. the ConfigMap deleted"; oc delete configmap cluster-onboarding -n $NS
wait_for "A's generated Secret removed" "'gsd-cluster-cm-demo-a' not in s['secrets']" 900
state
echo "== log lines naming the demo"
P=$(oc get pods -n $NS -l app.kubernetes.io/name=group-sync-dashboard --field-selector=status.phase=Running -o name | head -1)
oc logs -n $NS "$P" -c dashboard | grep -E "cm-demo|cluster-onboarding" | cut -c1-230 | head -40
echo "== leftovers (must be none)"; oc get configmap,secret -n $NS 2>/dev/null | grep -E "cluster-onboarding|cm-demo" || echo "   none"
