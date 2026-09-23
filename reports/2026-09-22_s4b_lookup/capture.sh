#!/usr/bin/env bash
# SPEC_S4b §5 live-check evidence, captured after release-crc.sh --values environments/crc-lookup.yaml.
# Every command's output goes to $OUT/<step>.txt; nothing here changes the cluster except step 7's
# Secret-declared probe, which the cleanup removes.
set -uo pipefail
OUT="$1"; mkdir -p "$OUT"
NS=group-sync-dashboard
oc() { command oc "$@"; }
{
  echo "# head"; git -C "$(dirname "$0")/../../../../../../../Users/olasumbo/gitRepos/group-sync-dashboard" rev-parse HEAD 2>/dev/null || git rev-parse HEAD
  echo "# release"; helm list -n $NS
  echo "# pod image"; oc -n $NS get deploy group-sync-dashboard -o jsonpath='{.spec.template.spec.containers[0].image}{"\n"}'
  echo "# app version"; oc -n $NS exec deploy/group-sync-dashboard -- python -c 'import gsd; print(gsd.__version__)' 2>/dev/null
} > "$OUT/00-release.txt" 2>&1

# 3. the pod log, in order
oc -n $NS logs deploy/group-sync-dashboard --since=30m 2>/dev/null \
  | grep -E 'fleet-(login|lookup|logout)|discovery |cluster-resolved cluster=rnd-lookup|secret-shadows|fleet-lookup-failed' \
  > "$OUT/03-pod-log.txt" 2>&1

# 4. the Secret, field for field against the hand-made one
{
  for s in gsd-cluster-shared-rnd gsd-cluster-rnd-lookup; do
    echo "## $s"
    oc -n $NS get secret "$s" -o json | jq -c '{keys:(.data|keys), config:(.data.config|@base64d|fromjson|keys),
      tls:(.data.config|@base64d|fromjson|.tlsClientConfig|{insecure, caDataBytes:((.caData//"")|length)}),
      name:(.data.name|@base64d), server:(.data.server|@base64d), enabled:(.data.enabled|@base64d),
      visibility:(.data.visibility|@base64d), identity:(.data.identity|@base64d),
      labels:.metadata.labels, ann:(.metadata.annotations|del(.["kubectl.kubernetes.io/last-applied-configuration"]))}'
  done
} > "$OUT/04-secrets.txt" 2>&1

# 5. the API, as a bearer-token reader (wide tier)
ROUTE=$(oc -n $NS get route group-sync-dashboard -o jsonpath='{.spec.host}')
curl -sk -H "Authorization: Bearer $(oc whoami -t)" "https://$ROUTE/api/clusterconfigs" \
  | jq '{clusters:[.clusters[] | select(.id|test("rnd-lookup")) | {id, source, credential, tls, status, last_poll, error}], findings}' \
  > "$OUT/05-api-clusterconfigs.txt" 2>&1
curl -sk -H "Authorization: Bearer $(oc whoami -t)" "https://$ROUTE/api/clusters" \
  | jq '[.[]? // .clusters[]? | select(.id|test("rnd-lookup"))]' > "$OUT/05-api-clusters.txt" 2>&1

# 6. the target's token count for developer (S4a §5's command)
oc get oauthaccesstokens -o json | jq '[.items[] | select(.userName=="developer" and .clientName=="openshift-challenging-client")] | length' \
  > "$OUT/06-token-count-after.txt" 2>&1
echo done
