#!/bin/zsh
# The cluster-configuration tier on the lab (#230): who is refused, who is not, and that the
# refusal names nothing. The dashboard trusts X-Forwarded-User from its proxy, so the pod's
# loopback can put any identity in front of the gate — which is exactly the auditor probe we need.
set -u
NS=group-sync-dashboard
API() { oc -n $NS exec deploy/group-sync-dashboard -c dashboard -- sh -c \
  "curl -s -o /tmp/b -w '%{http_code}' -H 'X-Forwarded-User: $1' 'http://127.0.0.1:8080$2'; cat /tmp/b" 2>/dev/null; }

echo "### 0. what the cluster says about the two questions (the tier's defaults)"
echo "cluster-reader rules covering core/secrets:"
oc get clusterrole cluster-reader -o json | python3 -c "import json,sys; d=json.load(sys.stdin); print(len([r for r in d['rules'] if any(g in ('','*') for g in r.get('apiGroups',[])) and any(x in ('secrets','*') for x in r.get('resources',[]))]), 'of', len(d['rules']), 'rules')"
for v in get create; do
  printf 'kubeadmin  can-i %-6s secrets -n %s : %s\n' $v $NS "$(oc auth can-i $v secrets -n $NS 2>&1 | tail -1)"
  printf 'lateef.o   can-i %-6s secrets -n %s : %s\n' $v $NS "$(oc auth can-i $v secrets -n $NS --as=lateef.o 2>&1 | tail -1)"
done

echo "\n### 1. the wide tier admits the auditor persona; the new tier does not"
echo "lateef.o  /api/clusters      -> $(API lateef.o /api/clusters | tail -c 80)"
echo "lateef.o  /api/clusterconfigs -> $(API lateef.o /api/clusterconfigs)"
echo "kubeadmin /api/clusterconfigs -> $(API kubeadmin /api/clusterconfigs | head -c 1)$(API kubeadmin /api/clusterconfigs | tail -c 0)"

echo "\n### 2. the refusal names no cluster, no Secret, no namespace"
API lateef.o /api/clusterconfigs | python3 -c "
import json,sys,re
raw=sys.stdin.read(); body=raw[3:] if raw[:3].isdigit() else raw
d=json.loads(body); detail=d.get('detail','')
print(repr(detail))
words=set(re.findall(r'[A-Za-z0-9_.-]+', detail))
leaks=words & {'crc-local','mock','mock-trusted','mock-privateca','mock-selfsigned','group-sync-dashboard','secrets','gsd-cluster-mock'}
print('leaks:', leaks or 'none')"

echo "\n### 3. the surface is not reachable by another route for the refused reader"
for p in /api/clusters /api/kpi /metrics; do
  n=$(API lateef.o $p | grep -c 'secret:gsd-cluster' || true)
  echo "lateef.o $p : occurrences of 'secret:gsd-cluster' = $n"
done

echo "\n### 4. the three TLS-mode clusters still poll under the tier (regression)"
API kubeadmin /api/clusterconfigs | python3 -c "
import json,sys
raw=sys.stdin.read(); body=raw[3:] if raw[:3].isdigit() else raw
d=json.loads(body)
for c in d['clusters']:
    print(' ', json.dumps({k:c[k] for k in ('id','source','credential','tls','status')}))
print('  findings:', json.dumps(d['findings']))"

echo "\n### 5. the metric series exist, pre-seeded"
API kubeadmin /metrics | grep 'threshold="clusterconfig' | head -4
echo "### TIER VALIDATE DONE"
