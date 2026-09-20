#!/bin/zsh
# S1 validation on CRC (SPEC_S1 §S1.8): a real labelled Secret for the lab's mock cluster, a broken one, the
# API from the pod's loopback, the poller's log, the Secret deleted → the cluster retired with its rows.
export KUBECONFIG=~/.kube/crc.kubeconfig
NS=group-sync-dashboard
API() { oc -n $NS exec deploy/group-sync-dashboard -c dashboard -- sh -c "curl -s -H 'X-Forwarded-User: kubeadmin' 'http://127.0.0.1:8080$1'" 2>/dev/null; }
step() { echo; echo "### $1"; }
step "0. the running head and the Role the chart rendered"
oc -n $NS get role,rolebinding -l app.kubernetes.io/component=cluster-secrets -o name
oc -n $NS get cm group-sync-dashboard-config -o jsonpath='{.data.clusters\.yaml}' | grep -n 'clusterSecretsEnabled'
step "1. before: GET /api/clusterconfigs"
API /api/clusterconfigs | jq -c '{secrets, clusters: [.clusters[] | {id, source, credential, host, status}], findings}'
step "2. the mock cluster as a labelled Secret (its token and CA from mock-cluster-creds, which the Argo-managed Deployment does not mount — the #119 gap)"
TOKEN=$(oc -n $NS get secret mock-cluster-creds -o jsonpath='{.data.token}' | base64 -d)
CA=$(oc -n $NS get secret mock-cluster-creds -o jsonpath='{.data.ca\.crt}')
cat <<YAML | oc apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: gsd-cluster-mock
  namespace: $NS
  labels:
    groupsync-dashboard.io/secret-type: cluster
    environment: lab
type: Opaque
stringData:
  name: mock
  server: https://mock-openshift:6443
  config: '{"bearerToken": "$TOKEN", "tlsClientConfig": {"caData": "$CA"}}'
  visibility: inherit
  identity: same-as-host
YAML
cat <<YAML | oc apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: gsd-cluster-broken
  namespace: $NS
  labels:
    groupsync-dashboard.io/secret-type: cluster
type: Opaque
stringData:
  name: broken
  server: https://broken.example:6443
  config: '{not json'
YAML
step "3. wait for the discovery cycle, then GET /api/clusterconfigs"
for i in $(seq 1 40); do
  out=$(API /api/clusterconfigs)
  # a cluster retired by an earlier run keeps its Secret-sourced `source` on its row: the discovered one is the row
  # that is not retired AND carries the finding for the broken Secret beside it (both land in one cycle)
  echo "$out" | jq -e '(.clusters[] | select(.id=="mock") | select(.retired==false)) and (.findings[] | select(.secret=="gsd-cluster-broken"))' > /dev/null 2>&1 && break
  sleep 15
done
echo "$out" | jq -c '{secrets, clusters: [.clusters[] | {id, source, credential, host, labels, visibility, identity, tls, status, last_poll, error, retired}], findings}'
step "4. the poller's log lines for the discovery and the mock cluster"
oc -n $NS logs deploy/group-sync-dashboard -c dashboard --since=15m | grep -E 'cluster Secrets:|cluster mock:|Secret gsd-cluster-broken' | tail -6
step "5. the mock cluster polled: GET /api/clusters"
for i in $(seq 1 20); do
  st=$(API /api/clusters | jq -r '.[] | select(.id=="mock") | .status')
  [ -n "$st" ] && [ "$st" != "null" ] && break
  sleep 15
done
API /api/clusters | jq -c '.[] | select(.id=="mock") | {id, status, last_poll, group_count, groupsync_count, error}'
step "6. the credential never leaves the Secret: the sentinel in no response, no metric, no log line"
for p in /api/clusterconfigs /api/clusters /metrics /readyz; do printf '%s: ' $p; API $p | grep -c "$TOKEN"; done
printf 'log: '; oc -n $NS logs deploy/group-sync-dashboard -c dashboard --since=30m | grep -c "$TOKEN"
step "7. the broken Secret deleted → its finding gone; the mock Secret deleted → the cluster retired, rows kept"
oc -n $NS delete secret gsd-cluster-broken gsd-cluster-mock
for i in $(seq 1 40); do
  out=$(API /api/clusterconfigs)
  echo "$out" | jq -e '.clusters[] | select(.id=="mock") | select(.retired==true)' > /dev/null 2>&1 && break
  sleep 15
done
echo "$out" | jq -c '{clusters: [.clusters[] | {id, source, enabled, retired}], findings}'
API /api/clusters | jq -c '.[] | select(.id=="mock") | {id, enabled, group_count, status}'
oc -n $NS logs deploy/group-sync-dashboard -c dashboard --since=10m | grep -iE 'its Secret is gone' | tail -2
echo "### VALIDATE DONE"
