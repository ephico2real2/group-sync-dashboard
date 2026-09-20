#!/bin/zsh
# The three TLS trust modes and the refusal, PROVEN on CRC (the operator, 2026-09-20: "as long as the option
# works"). Every probe is a real second connection to CRC's EXTERNAL API (https://api.crc.testing:6443) under its
# own cluster id, with the dashboard ServiceAccount's own token — the internal URL is refused by the contract (the
# host is never sourced from a Secret), and the external one is signed by kube-apiserver-lb-signer, which the pod's
# GSD_TRUSTED_CA_FILE bundle (147 certs, system trust) does NOT carry and the SA ca.crt (6 certs) does. So mode 1
# must FAIL here with the exact TLS error, mode 2 with that CA must succeed, mode 3 must succeed, and mode 4 is
# the refusal. The poll interval on the lab is short enough that one binding cadence (300 s) covers discovery.
export KUBECONFIG=~/.kube/crc.kubeconfig
NS=group-sync-dashboard
API() { oc -n $NS exec deploy/group-sync-dashboard -c dashboard -- sh -c "curl -s -H 'X-Forwarded-User: kubeadmin' 'http://127.0.0.1:8080$1'" 2>/dev/null; }
step() { echo; echo "### $1"; }
SA_TOKEN=$(oc -n $NS create token group-sync-dashboard --duration=2h)
SA_CA_B64=$(oc -n $NS get secret -o json | jq -r '.items[] | select(.type=="kubernetes.io/service-account-token") | .data["ca.crt"]' | head -1)
[ -n "$SA_CA_B64" ] || SA_CA_B64=$(oc get cm kube-root-ca.crt -n $NS -o jsonpath='{.data.ca\.crt}' | base64 | tr -d '\n')
EXT=https://api.crc.testing:6443
mk() {  # name, cluster id, config json
cat <<YAML | oc apply -f -
apiVersion: v1
kind: Secret
metadata:
  name: $1
  namespace: $NS
  labels:
    groupsync-dashboard.io/secret-type: cluster
    probe: tls
type: Opaque
stringData:
  name: $2
  server: $EXT
  config: '$3'
YAML
}
wait_for() {  # jq filter on /api/clusterconfigs
  for i in $(seq 1 30); do out=$(API /api/clusterconfigs); echo "$out" | jq -e "$1" > /dev/null 2>&1 && return 0; sleep 15; done; return 1
}
step "0. the pod's trust store, measured (python inside the pod)"
POD=$(oc -n $NS get pod -l app.kubernetes.io/name=group-sync-dashboard -o jsonpath='{.items[?(@.metadata.labels.app\.kubernetes\.io/component!="report")].metadata.name}' | cut -d' ' -f1)
PROBE='import os,ssl,urllib.request
b=os.environ["GSD_TRUSTED_CA_FILE"]; sa="/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"
print("GSD_TRUSTED_CA_FILE",b,"certs:",open(b).read().count("BEGIN CERT"),"| SA ca.crt certs:",open(sa).read().count("BEGIN CERT"))
for cafile,label in ((b,"external via GSD_TRUSTED_CA_FILE"),(sa,"external via SA ca.crt")):
    try: urllib.request.urlopen("https://api.crc.testing:6443/version",context=ssl.create_default_context(cafile=cafile),timeout=5); print(label,"-> verified OK")
    except Exception as e: print(label,"->",type(e).__name__,str(e)[:100])'
oc -n $NS exec $POD -c dashboard -- python3 -c "import base64; exec(base64.b64decode('$(printf %s "$PROBE" | base64 | tr -d '\n')').decode())"

step "1. DEFAULT — bearer token, no caData: the dashboard's own trust store, which does not carry the lb-signer → the poll must fail with the TLS error, said"
mk gsd-cluster-tls-default crc-tls-default "{\"bearerToken\": \"$SA_TOKEN\"}"
wait_for '.clusters[] | select(.id=="crc-tls-default") | select(.status != null)' || echo "(no poll outcome within the wait)"
API /api/clusterconfigs | jq -c '.clusters[] | select(.id=="crc-tls-default") | {id, source, credential, tls, status, error}'
oc -n $NS logs deploy/group-sync-dashboard -c dashboard --since=10m 2>/dev/null | grep -E 'crc-tls-default' | tail -2

step "2. OVERRIDE — the same cluster with tlsClientConfig.caData = the SA ca.crt (carries kube-apiserver-lb-signer) → the poll succeeds"
mk gsd-cluster-tls-cadata crc-tls-cadata "{\"bearerToken\": \"$SA_TOKEN\", \"tlsClientConfig\": {\"caData\": \"$SA_CA_B64\"}}"
wait_for '.clusters[] | select(.id=="crc-tls-cadata") | select(.status == "ok")' || echo "(status ok not reached within the wait)"
API /api/clusterconfigs | jq -c '.clusters[] | select(.id=="crc-tls-cadata") | {id, source, credential, tls, status, error}'
API /api/clusters | jq -c '.[] | select(.id=="crc-tls-cadata") | {id, status, group_count, groupsync_count}'

step "3. INSECURE — tlsClientConfig.insecure: true, no caData → the poll succeeds, tls.insecure true"
mk gsd-cluster-tls-insecure crc-tls-insecure "{\"bearerToken\": \"$SA_TOKEN\", \"tlsClientConfig\": {\"insecure\": true}}"
wait_for '.clusters[] | select(.id=="crc-tls-insecure") | select(.status == "ok")' || echo "(status ok not reached within the wait)"
API /api/clusterconfigs | jq -c '.clusters[] | select(.id=="crc-tls-insecure") | {id, source, credential, tls, status, error}'

step "4. REFUSAL — caData AND insecure together → a finding naming both fields, no cluster, the pod alive"
mk gsd-cluster-tls-both crc-tls-both "{\"bearerToken\": \"$SA_TOKEN\", \"tlsClientConfig\": {\"caData\": \"$SA_CA_B64\", \"insecure\": true}}"
wait_for '.findings[] | select(.secret=="gsd-cluster-tls-both")' || echo "(finding not reported within the wait)"
API /api/clusterconfigs | jq -c '{findings: [.findings[] | select(.secret=="gsd-cluster-tls-both")], both_listed: [.clusters[] | select(.id=="crc-tls-both") | .id]}'
oc -n $NS get pod -l app.kubernetes.io/name=group-sync-dashboard -o custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount --no-headers | head -2

step "5. the token in no response and no log line"
for p in /api/clusterconfigs /api/clusters /metrics; do printf '%s: ' $p; API $p | grep -c "$SA_TOKEN"; done
printf 'log: '; oc -n $NS logs deploy/group-sync-dashboard -c dashboard --since=30m | grep -c "$SA_TOKEN"

step "6. cleanup: the four probe Secrets deleted → the three clusters retired, the finding gone"
oc -n $NS delete secret -l probe=tls
wait_for '[.clusters[] | select(.id | startswith("crc-tls-")) | .retired] | all and length == 3' || echo "(retirement not reached within the wait)"
API /api/clusterconfigs | jq -c '{tls_probes: [.clusters[] | select(.id | startswith("crc-tls-")) | {id, enabled, retired}], findings}'
echo "### VALIDATE TLS DONE"
