source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/walk/lib.sh
metric() { api_as kubeadmin /metrics | grep '^gsd_visibility_tier_checks_total' | grep 'outcome="forbidden"' ; }
oc create namespace d2b-walk
oc create serviceaccount no-sar -n d2b-walk; oc create serviceaccount no-groups -n d2b-walk
oc create clusterrole d2b-walk-no-sar --verb=get,list --resource=groups.user.openshift.io
oc create clusterrole d2b-walk-no-groups --verb=create --resource=subjectaccessreviews.authorization.k8s.io
oc create clusterrolebinding d2b-walk-no-sar --clusterrole=d2b-walk-no-sar --serviceaccount=d2b-walk:no-sar
oc create clusterrolebinding d2b-walk-no-groups --clusterrole=d2b-walk-no-groups --serviceaccount=d2b-walk:no-groups
for sa in no-sar no-groups; do
  printf '{"name": "d2b-%s", "server": "https://api.crc.testing:6443", "credential": {"kind": "bearerToken", "token": "%s"}, "tls": {"mode": "trustedBundle"}}' \
    "$sa" "$(oc create token "$sa" -n d2b-walk --duration=2h)" \
    | oc exec -i -n "$NS" "$(pod)" -c dashboard -- curl -s -X POST -H 'X-Forwarded-User: kubeadmin' \
        -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1:8080/api/clusterconfigs | head -c 200; echo
done
echo "== waiting for discovery (resolved d2b-no-sar, resolved d2b-no-groups)"
for _ in $(seq 1 60); do resolved d2b-no-sar | grep -q . && resolved d2b-no-groups | grep -q . && break; sleep 10; done
resolved d2b-no-sar; resolved d2b-no-groups
echo "== metric before"; metric
T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)
traffic 120
echo "== warnings in the two minutes, per cluster"
for c in d2b-no-sar d2b-no-groups; do
  printf '%s: ' "$c"; oc logs -n "$NS" "$(pod)" -c dashboard --since-time="$T0" | grep -cE "$c: visibility tier for"
done
printf 'pair total: '; oc logs -n "$NS" "$(pod)" -c dashboard --since-time="$T0" | grep -cE 'd2b-no-(sar|groups): visibility tier for'
echo "== the warnings, time and reader"
oc logs -n "$NS" "$(pod)" -c dashboard --since-time="$T0" | grep -E 'd2b-no-(sar|groups): visibility tier for' | sed -E "s/^[0-9-]+ ([0-9:,]+).*(d2b-no-[a-z]+): visibility tier for '([^']+)'.*\(([a-z_]+).*/  \1 \2 \3 \4/"
echo "== metric after"; metric
echo "== the alert (user-workload monitoring)"
oc exec -n openshift-user-workload-monitoring prometheus-user-workload-0 -c prometheus -- curl -s 'http://127.0.0.1:9090/api/v1/alerts' 2>/dev/null \
  | python3 -c 'import json,sys
try: a=json.load(sys.stdin)["data"]["alerts"]
except Exception as e: print("  no answer from prometheus-user-workload:", e); sys.exit()
hits=[x for x in a if x["labels"].get("alertname")=="GroupSyncDashboardVisibilityChecksFailing"]
print("  ", [(x["state"], x.get("activeAt")) for x in hits] or "not present")'
echo "== cleanup"
for c in d2b-no-sar d2b-no-groups; do
  oc exec -n "$NS" "$(pod)" -c dashboard -- curl -s -o /dev/null -w "DELETE $c: %{http_code}\n" -X DELETE -H 'X-Forwarded-User: kubeadmin' "http://127.0.0.1:8080/api/clusterconfigs/$c"
done
oc delete namespace d2b-walk
oc delete clusterrolebinding d2b-walk-no-sar d2b-walk-no-groups
oc delete clusterrole d2b-walk-no-sar d2b-walk-no-groups
