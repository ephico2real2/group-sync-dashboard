#!/usr/bin/env bash
# CRC-ONLY convenience release. For anything other than a local CRC cluster use
# ../build-and-push-external.sh, which builds the same Containerfile and pushes to an external
# registry (Quay) that every cluster can pull from. This script talks to CRC's built-in
# registry over its default route and is not portable off that machine.
#
# Build, push and deploy an image tagged with the git commit it was built from.
#
# Why: a semver-only tag cannot tell you whether the running pod contains your change.
# That failed here for real — 0.3.1 was built, the source was then edited, and 0.3.1 was
# deployed. The commit had the fix, the pod did not, and nothing showed the gap because
# both were called "0.3.1". A commit-derived tag makes that impossible to miss: the tag
# changes when the source does.
#
#   ./scripts/release.sh              build + push + deploy
#   ./scripts/release.sh --build-only
#   ./scripts/release.sh --allow-dirty   build from an uncommitted tree (tagged -dirty)
#
# Immutability rule: a given <version>-<sha> tag always means the same source. Pushing a
# different image under an existing tag is refused rather than silently overwritten.

set -euo pipefail
cd "$(dirname "$0")/.."

REGISTRY="${REGISTRY:-default-route-openshift-image-registry.apps-crc.testing}"
NAMESPACE="${NAMESPACE:-group-sync-dashboard}"
IMAGE="${IMAGE:-group-sync-dashboard}"
BUILD_ONLY=false
ALLOW_DIRTY=false
for arg in "$@"; do
  case "$arg" in
    --build-only) BUILD_ONLY=true ;;
    --allow-dirty) ALLOW_DIRTY=true ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

VERSION=$(python3 -c "import re,pathlib;print(re.search(r'^version = \"(.+?)\"',pathlib.Path('pyproject.toml').read_text(),re.M).group(1))")
COMMIT=$(git rev-parse --short=10 HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)

# A dirty tree means no commit reproduces this image. Say so in the tag rather than
# stamping it with a commit whose content it does not match.
if [ -n "$(git status --porcelain)" ]; then
  if [ "$ALLOW_DIRTY" != true ]; then
    echo "ERROR: working tree has uncommitted changes." >&2
    echo "       Commit them, or pass --allow-dirty to build a '-dirty' image." >&2
    git status --short >&2
    exit 1
  fi
  COMMIT="${COMMIT}-dirty"
  echo "WARNING: building from a dirty tree; tagging as ${COMMIT}"
fi

TAG="${VERSION}-${COMMIT}"
REF="${REGISTRY}/${NAMESPACE}/${IMAGE}:${TAG}"

echo "version : ${VERSION}"
echo "commit  : ${COMMIT}  (branch ${BRANCH})"
echo "tag     : ${TAG}"

podman build \
  --build-arg "GIT_COMMIT=${COMMIT}" \
  --build-arg "GIT_BRANCH=${BRANCH}" \
  --build-arg "BUILD_VERSION=${VERSION}" \
  -t "${IMAGE}:${TAG}" -f Containerfile . >/dev/null

# Verify the stamp survived the build before anything is pushed — a label that silently
# failed to apply would defeat the entire point of tagging by commit.
STAMPED=$(podman run --rm --entrypoint sh "${IMAGE}:${TAG}" -c 'echo "$GSD_GIT_COMMIT"')
if [ "$STAMPED" != "$COMMIT" ]; then
  echo "ERROR: image reports commit '${STAMPED}', expected '${COMMIT}'" >&2
  exit 1
fi
echo "built   : ${IMAGE}:${TAG} (stamp verified)"

if [ "$BUILD_ONLY" = true ]; then exit 0; fi

podman login -u kubeadmin -p "$(oc whoami -t)" --tls-verify=false "${REGISTRY}" >/dev/null

if oc get istag "${IMAGE}:${TAG}" -n "${NAMESPACE}" >/dev/null 2>&1; then
  echo "ERROR: ${TAG} already exists in the registry." >&2
  echo "       Tags are immutable — commit your changes so the tag advances." >&2
  exit 1
fi

podman tag "${IMAGE}:${TAG}" "${REF}"
podman push --tls-verify=false "${REF}" >/dev/null
echo "pushed  : ${REF}"

INTERNAL="image-registry.openshift-image-registry.svc:5000/${NAMESPACE}/${IMAGE}:${TAG}"

# Write the released tag into the manifest FIRST, then apply it.
#
# The alternative — apply the manifest, then `oc set image` — leaves the file naming a
# different tag than the cluster runs. A later routine `oc apply` then silently rolls the
# deployment back to the older tag, undoing a release with no error and no obvious cause.
# Verified against this cluster with `--dry-run=server`: applying the unmodified manifest
# reverted 0.3.2-<sha> to 0.3.2.
#
# Updating the file makes the tree dirty, so the next release refuses until it is
# committed. That is deliberate: it keeps git the source of truth for what is deployed.
python3 - "$INTERNAL" <<'PY'
import pathlib, re, sys
ref = sys.argv[1]
path = pathlib.Path("deploy/dashboard.yaml")
text = path.read_text()
new, n = re.subn(
    r"(?m)^(\s+image: )image-registry\.openshift-image-registry\.svc:5000/\S+$",
    lambda m: m.group(1) + ref,
    text,
)
if n != 1:
    sys.exit(f"expected exactly one image line to rewrite, found {n}")
path.write_text(new)
PY
echo "manifest: deploy/dashboard.yaml now pins ${TAG}"

# Apply the whole manifest so config, RBAC and probe changes ship with the image, not just
# the image itself.
oc apply -f deploy/dashboard.yaml >/dev/null
oc rollout status "deploy/${IMAGE}" -n "${NAMESPACE}" --timeout=300s

# Prove the running pod is the build we just made, not a cached older one.
sleep 5
RUNNING=$(oc exec -n "${NAMESPACE}" "deploy/${IMAGE}" -- sh -c 'echo "$GSD_GIT_COMMIT"' 2>/dev/null | tr -d '\r\n')
if [ "$RUNNING" != "$COMMIT" ]; then
  echo "ERROR: pod reports commit '${RUNNING}', expected '${COMMIT}'" >&2
  exit 1
fi
echo "running : ${COMMIT} — verified in-pod"

# The manifest now differs from HEAD. Say so plainly: an uncommitted deploy manifest is how
# the cluster and git drift apart again.
if [ -n "$(git status --porcelain deploy/dashboard.yaml)" ]; then
  echo
  echo "NEXT: deploy/dashboard.yaml was updated to pin ${TAG}. Commit it so git records"
  echo "      what is deployed:  git commit -am 'deploy: pin ${TAG}'"
fi
