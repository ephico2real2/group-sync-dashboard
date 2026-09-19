#!/usr/bin/env bash
# Re-capture the mock cluster's manifests from a running cluster.
#
# kubectl-neat removes what the API server and admission controllers inject — empty `resources: {}`,
# `securityContext: {}`, status, managedFields, the last-applied annotation. It deliberately KEEPS
# cluster-specific metadata (namespace, creationTimestamp: null, deployment revision, restartedAt),
# which is right for a round-trip but wrong for a manifest committed to git, so a second pass drops it.
#
#   kubectl krew install neat     # once, see DEPLOY.md
#   ./capture.sh                  # rewrites the three manifests beside this script
set -euo pipefail
cd "$(dirname "$0")"
NS="${NS:-group-sync-dashboard}"
command -v kubectl-neat >/dev/null || { echo "kubectl-neat not on PATH (kubectl krew install neat)" >&2; exit 1; }

strip() {                      # drop what neat keeps but a committed manifest must not carry
  python3 -c "
import sys, yaml
d = yaml.safe_load(sys.stdin)
m = d.setdefault('metadata', {})
for k in ('namespace', 'creationTimestamp', 'resourceVersion', 'uid', 'generation', 'managedFields'):
    m.pop(k, None)
ann = m.get('annotations') or {}
for k in ('deployment.kubernetes.io/revision', 'kubectl.kubernetes.io/restartedAt',
          'kubectl.kubernetes.io/last-applied-configuration'):
    ann.pop(k, None)
if ann: m['annotations'] = ann
else:   m.pop('annotations', None)
t = d.get('spec', {}).get('template', {}).get('metadata')
if t:
    t.pop('creationTimestamp', None)
    a = t.get('annotations') or {}
    a.pop('kubectl.kubernetes.io/restartedAt', None)
    if a: t['annotations'] = a
    else: t.pop('annotations', None)
sys.stdout.write(yaml.safe_dump(d, sort_keys=False, width=100))
"
}

for spec in "deploy/mock-openshift:mock-openshift-deployment.yaml" \
            "svc/mock-openshift:mock-openshift-service.yaml" \
            "cm/mock-fixture:mock-fixture-configmap.yaml"; do
  obj=${spec%%:*}; out=${spec##*:}
  oc get "$obj" -n "$NS" -o yaml | kubectl neat | strip > "$out"
  echo "  $out  $(wc -c < "$out" | tr -d ' ') bytes"
done
echo "validating:"
oc apply --dry-run=server -n "$NS" -f mock-openshift-deployment.yaml -f mock-openshift-service.yaml \
  -f mock-fixture-configmap.yaml 2>&1 | sed 's/^/  /'
