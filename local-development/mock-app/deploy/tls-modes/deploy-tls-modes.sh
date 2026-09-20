#!/usr/bin/env bash
# The three TLS trust modes of a Secret-declared cluster, proven against three copies of the mock
# OpenShift API (#230 S1; the operator, 2026-09-20: "duplicate the mock app as much as possible with new
# names as a way to test the 3 modes of connecting to the cluster"). Repeatable: the rig stays deployed
# and S2's walk uses it.
#
#   ./deploy-tls-modes.sh            deploy the PKI, the three workloads, the four labelled Secrets; then prove
#   ./deploy-tls-modes.sh --prove    prove only (the rig is already up)
#   ./deploy-tls-modes.sh --down     remove the four Secrets and the three workloads (the PKI stays)
#
# What each copy proves (the dashboard's GET /api/clusterconfigs is the witness, from the pod's loopback):
#   mock-trusted     leaf signed by the CA the lab's trusted bundle carries  → DEFAULT mode polls (tls.ca trusted-bundle)
#   mock-privateca   leaf signed by a new CA nothing trusts                  → DEFAULT fails (the x509 error, a poll
#                                                                              outcome); OVERRIDE with caData polls
#   mock-selfsigned  a bare self-signed leaf                                 → only insecure: true polls
#   the refusal      caData AND insecure on one Secret                       → a finding naming both, no cluster, pod alive
set -euo pipefail
cd "$(dirname "$0")"
NS="${NS:-group-sync-dashboard}"
MODE_ONLY=false; DOWN=false
for a in "$@"; do case "$a" in --prove) MODE_ONLY=true ;; --down) DOWN=true ;; *) echo "unknown argument: $a" >&2; exit 2 ;; esac; done
say() { printf '\n==> %s\n' "$*"; }
render() { NAME="$1" MODE="$2" CLUSTER="${3:-}" TOKEN="${4:-}" CONFIG="${5:-}" envsubst '$NAME $MODE $CLUSTER $TOKEN $CONFIG' < "$6"; }
API() { oc -n "$NS" exec deploy/group-sync-dashboard -c dashboard -- sh -c "curl -s --max-time 5 -H 'X-Forwarded-User: kubeadmin' 'http://127.0.0.1:8080$1'" 2>/dev/null; }
wait_json() {  # jq filter on /api/clusterconfigs, up to ~7 min (one binding cadence + a poll)
  local i; for i in $(seq 1 30); do local out; out=$(API /api/clusterconfigs); echo "$out" | jq -e "$1" >/dev/null 2>&1 && { echo "$out"; return 0; }; sleep 15; done
  API /api/clusterconfigs; return 1
}
show() { jq -c --arg id "$1" '.clusters[] | select(.id==$id) | {id, source, credential, tls, status, last_poll, error}'; }

TOKEN=$(awk '/^  token:/{gsub(/"/,"",$2); print $2; exit}' ../../fixtures/reference.yaml)
[ -n "$TOKEN" ] || { echo "no meta.token in ../../fixtures/reference.yaml" >&2; exit 1; }

if [ "$DOWN" = true ]; then
  say "removing the four Secrets and the three workloads (the PKI stays)"
  oc -n "$NS" delete secret -l groupsync-dashboard.io/tls-mode --ignore-not-found
  for n in mock-trusted mock-privateca mock-selfsigned; do oc -n "$NS" delete deploy,svc "$n" --ignore-not-found; done
  exit 0
fi

if [ "$MODE_ONLY" = false ]; then
  oc get clusterissuer ldap-enterprise-ca >/dev/null || { echo "ClusterIssuer ldap-enterprise-ca is absent: mock-trusted needs the CA the lab's bundle carries" >&2; exit 1; }
  say "1/4  the PKI: three shapes"
  oc apply -n "$NS" -f pki-trusted.yaml -f pki-privateca.yaml -f pki-selfsigned.yaml
  oc wait --for=condition=Ready certificate/mock-trusted-tls certificate/mock-privateca-tls certificate/mock-selfsigned-tls -n "$NS" --timeout=180s
  say "2/4  the three workloads (the same image and fixture as mock-openshift)"
  for pair in mock-trusted:trusted mock-privateca:privateca mock-selfsigned:selfsigned; do
    render "${pair%%:*}" "${pair##*:}" "" "" "" workload.yaml.tmpl | oc apply -n "$NS" -f -
  done
  for n in mock-trusted mock-privateca mock-selfsigned; do oc -n "$NS" rollout status deploy/"$n" --timeout=180s; done
  say "3/4  the labelled Secrets"
  PRIVATE_CA_B64=$(oc -n "$NS" get secret mock-privateca-ca -o jsonpath='{.data.ca\.crt}')
  render mock-trusted    trusted    mock-trusted    "$TOKEN" "{\"bearerToken\": \"$TOKEN\"}" cluster-secret.yaml.tmpl | oc apply -f -
  render mock-privateca  privateca  mock-privateca  "$TOKEN" "{\"bearerToken\": \"$TOKEN\"}" cluster-secret.yaml.tmpl | oc apply -f -   # DEFAULT first: must fail
  render mock-selfsigned selfsigned mock-selfsigned "$TOKEN" "{\"bearerToken\": \"$TOKEN\", \"tlsClientConfig\": {\"insecure\": true}}" cluster-secret.yaml.tmpl | oc apply -f -
  render mock-selfsigned refusal    mock-refusal    "$TOKEN" "{\"bearerToken\": \"$TOKEN\", \"tlsClientConfig\": {\"caData\": \"$PRIVATE_CA_B64\", \"insecure\": true}}" cluster-secret.yaml.tmpl | oc apply -f -
fi

say "4/4  the proofs (GET /api/clusterconfigs from the pod's loopback)"
say "the lab's trusted bundle: the one non-system root, and whether mock-privateca's CA is in it (it must not be)"
oc -n openshift-config get cm "$(oc get proxy cluster -o jsonpath='{.spec.trustedCA.name}')" -o jsonpath='{.data.ca-bundle\.crt}' | openssl x509 -noout -subject
oc -n "$NS" get secret mock-privateca-ca -o jsonpath='{.data.ca\.crt}' | base64 -d | openssl x509 -noout -subject

say "A. mock-trusted — DEFAULT (no caData): the enterprise-signed leaf verifies against the trusted bundle"
wait_json '.clusters[] | select(.id=="mock-trusted") | select(.status=="ok")' | show mock-trusted

say "B1. mock-privateca — DEFAULT (no caData): the x509 error, as a poll outcome"
wait_json '.clusters[] | select(.id=="mock-privateca") | select(.status!=null and .status!="ok")' | show mock-privateca
oc -n "$NS" logs deploy/group-sync-dashboard -c dashboard --since=10m | grep -E 'mock-privateca' | grep -iE 'certificate|ssl|tls' | tail -1 | cut -c1-300

say "B2. mock-privateca — OVERRIDE: the same Secret with tlsClientConfig.caData = the private CA's PEM"
PRIVATE_CA_B64=$(oc -n "$NS" get secret mock-privateca-ca -o jsonpath='{.data.ca\.crt}')
render mock-privateca privateca mock-privateca "$TOKEN" "{\"bearerToken\": \"$TOKEN\", \"tlsClientConfig\": {\"caData\": \"$PRIVATE_CA_B64\"}}" cluster-secret.yaml.tmpl | oc apply -f -
wait_json '.clusters[] | select(.id=="mock-privateca") | select(.status=="ok" and .tls.ca=="caData")' | show mock-privateca

say "C. mock-selfsigned — INSECURE: insecure: true polls the bare self-signed leaf"
wait_json '.clusters[] | select(.id=="mock-selfsigned") | select(.status=="ok")' | show mock-selfsigned

say "D. the refusal — caData AND insecure on one Secret: a finding naming both fields, no cluster, the pod alive"
wait_json '.findings[] | select(.secret=="gsd-cluster-mock-refusal")' | jq -c '{findings: [.findings[] | select(.secret=="gsd-cluster-mock-refusal")], listed: [.clusters[] | select(.id=="mock-refusal") | .id]}'
oc -n "$NS" get pod -l app.kubernetes.io/name=group-sync-dashboard -o custom-columns=NAME:.metadata.name,READY:.status.containerStatuses[0].ready,RESTARTS:.status.containerStatuses[0].restartCount --no-headers

say "E. the three beside crc-local, with the fixture's counts (GET /api/clusters)"
API /api/clusters | jq -c '.[] | {id, status, groupsync_count, group_count}'
say "F. the token in no response and no log line"
for p in /api/clusterconfigs /api/clusters /metrics; do printf '%s: ' "$p"; API "$p" | grep -c "$TOKEN" || true; done
printf 'log: '; oc -n "$NS" logs deploy/group-sync-dashboard -c dashboard --since=1h | grep -c "$TOKEN" || true
echo; echo "==> TLS MODES DONE"
