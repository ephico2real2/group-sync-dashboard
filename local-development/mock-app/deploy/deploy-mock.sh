#!/usr/bin/env bash
# Deploy the mock OpenShift cluster onto CRC, end to end.
#
# WHY THIS EXISTS: every object of the mock cluster was created by hand with `oc apply` — measured on
# 2026-09-18, all five carry kubectl's last-applied annotation and belong to no Helm release. The
# migration runbook called it the slowest part of a rebuild for exactly that reason. This script is
# that sequence, written down.
#
#   ./deploy-mock.sh              build, push, deploy, wire the dashboard, verify
#   ./deploy-mock.sh --no-build   skip the image, everything else
#   ./deploy-mock.sh --verify     check only, change nothing
#
# Order is load-bearing: the PKI first, because the Deployment mounts the leaf secret it issues.
set -euo pipefail
cd "$(dirname "$0")"

NS="${NS:-group-sync-dashboard}"
REGISTRY="${REGISTRY:-default-route-openshift-image-registry.apps-crc.testing}"
INTERNAL="${INTERNAL:-image-registry.openshift-image-registry.svc:5000}"
IMAGE="${IMAGE:-mock-openshift}"
TAG="${TAG:-test}"
FIXTURE="${FIXTURE:-reference.yaml}"
BUILD=true; VERIFY_ONLY=false
for a in "$@"; do
  case "$a" in
    --no-build) BUILD=false ;;
    --verify)   VERIFY_ONLY=true ;;
    *) echo "unknown argument: $a" >&2; exit 2 ;;
  esac
done
say() { printf '==> %s\n' "$*"; }

verify() {
  say "verifying"
  oc get deploy,svc mock-openshift -n "$NS" 2>/dev/null || { echo "  mock workload absent" >&2; return 1; }
  oc get certificate mock-ca mock-tls -n "$NS" 2>/dev/null || echo "  WARNING: the cert-manager chain is missing"
  oc get secret mock-cluster-creds -n "$NS" >/dev/null 2>&1 \
    && echo "  secret mock-cluster-creds present" || echo "  WARNING: mock-cluster-creds absent"
  if oc get configmap mock-fixture -n "$NS" >/dev/null 2>&1; then
    want=$(oc get deploy mock-openshift -n "$NS" \
      -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="MOCK_FIXTURE")].value}' 2>/dev/null)
    key=$(basename "${want:-unknown}")
    oc get configmap mock-fixture -n "$NS" -o jsonpath="{.data.${key//./\\.}}" >/dev/null 2>&1 \
      && echo "  configmap mock-fixture holds ${key}, which MOCK_FIXTURE asks for" \
      || echo "  WARNING: mock-fixture does not hold ${key} — the pod will not start"
  else
    echo "  WARNING: configmap mock-fixture absent — the pod cannot start"
  fi
  # The volume patch is invisible to Helm and is the step most often forgotten: without it the
  # dashboard reports the mock cluster's token and ca files as absent, and fails silently.
  if oc get deploy group-sync-dashboard -n "$NS" -o json 2>/dev/null \
     | grep -q '"name": *"mock-creds"'; then
    echo "  dashboard carries the mock-creds volume"
  else
    echo "  WARNING: the dashboard is MISSING the mock-creds volume — re-run without --verify"
  fi
}
[ "$VERIFY_ONLY" = true ] && { verify; exit 0; }

oc whoami >/dev/null || { echo "not logged in to a cluster" >&2; exit 1; }
oc get crd certificates.cert-manager.io >/dev/null 2>&1 \
  || { echo "cert-manager is not installed — the PKI step needs it" >&2; exit 1; }
oc get ns "$NS" >/dev/null 2>&1 || oc create ns "$NS"

if [ "$BUILD" = true ]; then
  say "building and pushing ${IMAGE}:${TAG}"
  # release-crc.sh does NOT build this image; it is the mock's own Containerfile.
  podman build -t "${IMAGE}:${TAG}" -f ../containerfile/Containerfile ..
  podman login -u "$(oc whoami)" -p "$(oc whoami -t)" --tls-verify=false "$REGISTRY" >/dev/null
  podman tag "${IMAGE}:${TAG}" "${REGISTRY}/${NS}/${IMAGE}:${TAG}"
  podman push --tls-verify=false "${REGISTRY}/${NS}/${IMAGE}:${TAG}"
fi

say "1/5  the cert-manager chain (must precede the workload)"
oc apply -n "$NS" -f certmanager-tls.yaml
oc wait --for=condition=Ready certificate/mock-tls -n "$NS" --timeout=120s

say "2/5  the fixture ConfigMap (the Deployment mounts it at /fixtures)"
# MISSED on the first cut of this script and caught by the operator: without this the pod cannot
# start, because MOCK_FIXTURE points inside a volume that would not exist. The live ConfigMap was
# byte-for-byte identical to the committed fixture, so it is simply rebuilt from the file.
if [ "$FIXTURE" = "reference.yaml" ] && [ -f mock-fixture-configmap.yaml ]; then
  # The captured manifest, exactly as it ran on CRC. Verified identical to ../fixtures/reference.yaml.
  oc apply -n "$NS" -f mock-fixture-configmap.yaml
else
  # Any other scenario is built from its fixture file.
  oc create configmap mock-fixture -n "$NS" --from-file="../fixtures/${FIXTURE}" \
    --dry-run=client -o yaml | oc apply -f -
fi

say "3/5  the workload"
oc apply -n "$NS" -f mock-openshift-deployment.yaml -f mock-openshift-service.yaml
oc rollout status deploy/mock-openshift -n "$NS" --timeout=180s

say "4/5  the credentials the dashboard reads"
# ca.crt MUST be the mock-ca root, or the dashboard's TLS verification of the mock fails.
# The token is not a secret: it is meta.token from the fixture the pod serves.
ca=$(oc get secret mock-ca -n "$NS" -o jsonpath='{.data.tls\.crt}' | base64 -d)
tok=$(awk '/^  token:/{gsub(/"/,"",$2); print $2; exit}' "../fixtures/${FIXTURE}")
[ -n "$tok" ] || { echo "no meta.token in ../fixtures/${FIXTURE}" >&2; exit 1; }
oc create secret generic mock-cluster-creds -n "$NS" \
  --from-literal=token="$tok" --from-literal=ca.crt="$ca" \
  --dry-run=client -o yaml | oc apply -f -

say "5/5  wire it into the dashboard (invisible to Helm — re-apply after EVERY helm install)"
oc patch deploy group-sync-dashboard -n "$NS" --type=json -p '[
  {"op":"add","path":"/spec/template/spec/volumes/-",
   "value":{"name":"mock-creds","secret":{"secretName":"mock-cluster-creds","defaultMode":420}}},
  {"op":"add","path":"/spec/template/spec/containers/0/volumeMounts/-",
   "value":{"name":"mock-creds","mountPath":"/etc/gsd/mock"}}
]' 2>/dev/null && oc rollout status deploy/group-sync-dashboard -n "$NS" --timeout=180s \
  || echo "  patch not applied (already present, or the container index differs) — check with --verify"

verify
