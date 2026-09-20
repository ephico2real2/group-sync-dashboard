#!/usr/bin/env bash
# CRC-ONLY convenience release. For anything else use ../build-and-push-external.sh, which
# builds the same Containerfile and pushes to an external registry every cluster can pull
# from. This one talks to CRC's built-in registry over its default route and is portable
# nowhere else.
#
# Build, push and deploy an image tagged with the git commit it was built from.
#
# Why: a semver-only tag cannot tell you whether the running pod contains your change.
# That failed here for real — 0.3.1 was built, the source was then edited, and 0.3.1 was
# deployed. The commit had the fix, the pod did not, and nothing showed the gap because
# both were called "0.3.1". A commit-derived tag makes that impossible to miss: the tag
# changes when the source does.
#
# THE MODES AND THEIR COMBINATIONS. Two managers, one release: the bare script is the safe local
# loop (Helm, from this worktree); --argocd is the gate (Argo CD, from GitHub — what a real install
# does at that commit). --values applies to both. Each row says where the chart, the image and the
# values come from, and what the run needs; anything not in the table is refused.
#
#   invocation                      manager  chart from          image                 values             needs
#   (none)                          Helm     this worktree       built <ver>-<sha>;    environments/      clean tree,
#                                                                an existing clean     crc.yaml (-f)      token session
#                                                                tag is reused
#   --allow-dirty                   Helm     worktree            <ver>-<sha>-dirty,    same               —
#                                                                never reused
#   --values X                      Helm     worktree            as above              X (-f); X may be   X exists
#                                                                                      untracked/edited —
#                                                                                      it is outside the
#                                                                                      build context, so
#                                                                                      it is not "dirty"
#   --argocd                        Argo     GitHub @ HEAD       built, handed to the  the Application's  commit on a
#                                                                Application as        default (crc.yaml) remote branch
#                                                                helm.parameters
#   --argocd --values X             Argo     GitHub @ HEAD       same                  valueFiles          X committed,
#                                                                                      [../../X]          clean, pushed
#   --argocd <branch>               Argo     GitHub @ <branch>   the chart's default   default            branch on
#                                                                (the PUBLISHED quay                      origin
#                                                                image — lags main)
#   --argocd <branch> --values X    Argo     GitHub @ <branch>   same                  [../../X]          X present at
#                                                                                                         origin/<branch>
#   --build-only                    (none)   —                   built + pushed        —                  —
#   --allow-dirty --argocd          REFUSED: Argo deploys a commit and a dirty tree has none — the image
#                                   would not match the chart Argo reads, and uncommitted chart edits
#                                   would silently not deploy.
#
# Typical loop: iterate with the bare script (or --values for a local variant); before merging,
# --argocd on the pushed head; after a merge, --argocd main — once the app release is cut, because
# the published images lag main (measured: report schema 12 against main's 17, readyz 503).
#
# TWO MANAGERS, ONE RELEASE, NEVER BOTH (#212). The release name and namespace are the same under
# Helm and under Argo CD, so the modes hand over: Helm mode deletes the Argo Application first
# (its cascade removes what Argo created; the data and artefacts PVCs carry helm.sh/resource-policy:
# keep and the minted Secrets were never Argo's, so history, sessions and tickets survive), then
# installs from this worktree; --argocd uninstalls the Helm release first (the same survivors),
# then points gitops/argocd-application-dashboard.yaml at the commit and the image just built and
# waits for Synced/Healthy. Helm cannot adopt objects Argo created (measured: "cannot be imported
# into the current release"), which is why the handover is a delete-and-install and not an adopt.
#
# --argocd NEEDS THE COMMIT ON GITHUB: Argo pulls the chart from the repository, not from this
# tree, so an unpushed commit cannot be synced — the script refuses with the push to run. It also
# needs the image PASSED to the Application: the chart's default is the last PUBLISHED image
# (quay.io …:<appVersion>), which lags main whenever the app version is not bumped — measured on
# the first Argo sync of the dashboard: the published report image understood snapshot schema 12
# against main's 17 and answered readyz 503 until the built tag was handed over.
#
# Immutability rule: a given <version>-<sha> tag always means the same source. Pushing a
# different image under an existing tag is refused rather than silently overwritten.

set -euo pipefail
cd "$(dirname "$0")"

REGISTRY="${REGISTRY:-default-route-openshift-image-registry.apps-crc.testing}"
NAMESPACE="${NAMESPACE:-group-sync-dashboard}"
IMAGE="${IMAGE:-group-sync-dashboard}"
BUILD_ONLY=false
ALLOW_DIRTY=false
ARGOCD=false
ARGO_REVISION=""
VALUES_FILE=""                                        # repository-relative, e.g. environments/crc.yaml
APP_NAME="${APP_NAME:-group-sync-dashboard}"          # the Application in openshift-gitops
ARGO_NAMESPACE="${ARGO_NAMESPACE:-openshift-gitops}"
expect=""
for arg in "$@"; do
  case "$expect" in
    revision) [ "${arg#--}" = "$arg" ] && { ARGO_REVISION="$arg"; expect=""; continue; }; expect="" ;;
    values) VALUES_FILE="$arg"; expect=""; continue ;;
  esac
  case "$arg" in
    --build-only) BUILD_ONLY=true ;;
    --allow-dirty) ALLOW_DIRTY=true ;;
    --argocd) ARGOCD=true; expect=revision ;;
    --values) expect=values ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done
[ "$expect" = values ] && { echo "--values needs a path" >&2; exit 2; }
if [ "$ARGOCD" = true ] && [ "$ALLOW_DIRTY" = true ]; then
  echo "ERROR: --allow-dirty and --argocd do not combine: Argo CD deploys a commit, and a dirty tree has none." >&2
  echo "       Commit (and push) to test through Argo, or drop --argocd for the local Helm loop." >&2
  exit 2
fi

# The values file, repository-relative (this script runs in local-development/). Helm reads it from
# this tree; Argo reads it from the repository at the revision it tracks, as a path relative to the
# chart directory — so in --argocd mode it must be committed and pushed, or the sync fails on a
# file the repository does not have.
REPO_ROOT="$(git rev-parse --show-toplevel)"
if [ -n "$VALUES_FILE" ]; then
  RELEASE_VALUES="${REPO_ROOT}/${VALUES_FILE}"
  ARGO_VALUES="../../${VALUES_FILE}"
else
  RELEASE_VALUES="${RELEASE_VALUES:-../environments/crc.yaml}"
  ARGO_VALUES=""                                       # the Application's own default
fi
if [ "$ARGOCD" = true ] && [ -n "$VALUES_FILE" ]; then
  # Checked here, at the top level: inside $(argo_values_patch) an exit would only leave the subshell.
  if [ -n "$ARGO_REVISION" ]; then
    # The Application will read the file from origin/<branch>, whatever this tree holds.
    git fetch -q origin "$ARGO_REVISION" 2>/dev/null || true
    if ! git cat-file -e "origin/${ARGO_REVISION}:${VALUES_FILE}" 2>/dev/null; then
      echo "ERROR: --values ${VALUES_FILE} does not exist on origin/${ARGO_REVISION}; Argo CD reads it from there." >&2; exit 1
    fi
  else
    if ! git ls-files --error-unmatch "${REPO_ROOT}/${VALUES_FILE}" >/dev/null 2>&1; then
      echo "ERROR: --values ${VALUES_FILE} is not committed; Argo CD reads it from the repository." >&2; exit 1
    fi
    if [ -n "$(git status --porcelain -- "${REPO_ROOT}/${VALUES_FILE}")" ]; then
      echo "ERROR: --values ${VALUES_FILE} has uncommitted changes; Argo CD would read the committed one." >&2; exit 1
    fi
  fi
fi
argo_values_patch() {
  # A JSON-patch op for the Application's valueFiles, or nothing to leave the file's default.
  [ -n "$ARGO_VALUES" ] || return 0
  printf ',{"op":"replace","path":"/spec/source/helm/valueFiles","value":["%s"]}' "$ARGO_VALUES"
}

# --argocd <branch> with no build: point the Application at that revision and its chart's default
# image, e.g. `--argocd main` after a merge. Any other --argocd use builds this commit first.
if [ "$ARGOCD" = true ] && [ -n "$ARGO_REVISION" ]; then
  echo "argocd  : ${APP_NAME} -> revision ${ARGO_REVISION}, the chart's default image"
  if helm status "${IMAGE}" -n "${NAMESPACE}" >/dev/null 2>&1; then
    echo "helm    : uninstalling release ${IMAGE} (the PVCs and the minted Secrets survive)"
    helm uninstall "${IMAGE}" -n "${NAMESPACE}" --wait --timeout 5m
  fi
  oc apply -f ../gitops/argocd-application-dashboard.yaml >/dev/null
  [ -n "$ARGO_VALUES" ] && echo "values  : ${VALUES_FILE} (the Application's valueFiles)"
  oc patch application "${APP_NAME}" -n "${ARGO_NAMESPACE}" --type json -p "[
    {\"op\": \"replace\", \"path\": \"/spec/source/targetRevision\", \"value\": \"${ARGO_REVISION}\"},
    {\"op\": \"remove\", \"path\": \"/spec/source/helm/parameters\"}$(argo_values_patch)]" 2>/dev/null \
  || oc patch application "${APP_NAME}" -n "${ARGO_NAMESPACE}" --type json -p "[
    {\"op\": \"replace\", \"path\": \"/spec/source/targetRevision\", \"value\": \"${ARGO_REVISION}\"}$(argo_values_patch)]"
  exec ./argocd-wait.sh "${APP_NAME}" "${ARGO_NAMESPACE}"
fi

VERSION=$(python3 -c "import re,pathlib;print(re.search(r'^version = \"(.+?)\"',pathlib.Path('pyproject.toml').read_text(),re.M).group(1))")
COMMIT=$(git rev-parse --short=10 HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)

# A dirty tree means no commit reproduces this image. Say so in the tag rather than
# stamping it with a commit whose content it does not match.
DIRTY="$(git status --porcelain)"
if [ "$ARGOCD" != true ] && [ -n "$VALUES_FILE" ]; then
  # A local variant of the values file does not dirty the IMAGE: the build context is this
  # directory and its Containerfiles COPY named paths only, so a file elsewhere in the repository
  # cannot reach the tag. (--argocd mode refused an uncommitted one above.)
  case "$VALUES_FILE" in
    local-development/*) ;;
    *) DIRTY="$(printf '%s\n' "$DIRTY" | grep -v -- " ${VALUES_FILE}\$" || true)" ;;
  esac
fi
if [ -n "$DIRTY" ]; then
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
# THE REPORT IMAGE, same commit, same tag (C3, docs/specs/SPEC_C3_reporting_microservice.md §3.3): the
# chart resolves reporting.image.* at the dashboard's appVersion, so the lab release must ship both
# images from one build or the report pod would pull a tag this registry does not hold.
REPORT_IMAGE="${IMAGE}-report"
podman build \
  --build-arg "GIT_COMMIT=${COMMIT}" \
  --build-arg "GIT_BRANCH=${BRANCH}" \
  --build-arg "BUILD_VERSION=${VERSION}" \
  -t "${REPORT_IMAGE}:${TAG}" -f Containerfile.report . >/dev/null
STAMPED=$(podman run --rm --entrypoint sh "${REPORT_IMAGE}:${TAG}" -c 'echo "$GSD_GIT_COMMIT"')
if [ "$STAMPED" != "$COMMIT" ]; then
  echo "ERROR: report image reports commit '${STAMPED}', expected '${COMMIT}'" >&2
  exit 1
fi
echo "built   : ${REPORT_IMAGE}:${TAG} (stamp verified)"

if [ "$BUILD_ONLY" = true ]; then exit 0; fi

podman login -u kubeadmin -p "$(oc whoami -t)" --tls-verify=false "${REGISTRY}" >/dev/null

# Immutable tags: an existing <version>-<sha> is never overwritten. A CLEAN commit already in the
# registry is the same source, so it is REUSED — a Helm→Argo handover of the same commit does not
# rebuild — but a -dirty tag is a snapshot of nothing reproducible and is refused as before.
PUSH=true
if oc get istag "${IMAGE}:${TAG}" -n "${NAMESPACE}" >/dev/null 2>&1; then
  case "$TAG" in
    *-dirty)
      echo "ERROR: ${TAG} already exists in the registry." >&2
      echo "       Tags are immutable — commit your changes so the tag advances." >&2
      exit 1 ;;
    *)
      echo "reused  : ${TAG} is already in the registry (the same commit); not rebuilding"
      PUSH=false ;;
  esac
fi

if [ "$PUSH" = true ]; then
podman tag "${IMAGE}:${TAG}" "${REF}"
podman push --tls-verify=false "${REF}" >/dev/null
echo "pushed  : ${REF}"
REPORT_REF="${REGISTRY}/${NAMESPACE}/${REPORT_IMAGE}:${TAG}"
podman tag "${REPORT_IMAGE}:${TAG}" "${REPORT_REF}"
podman push --tls-verify=false "${REPORT_REF}" >/dev/null
echo "pushed  : ${REPORT_REF}"
fi

INTERNAL="image-registry.openshift-image-registry.svc:5000/${NAMESPACE}/${IMAGE}:${TAG}"
REPORT_INTERNAL="image-registry.openshift-image-registry.svc:5000/${NAMESPACE}/${REPORT_IMAGE}:${TAG}"

# Deploy through the chart, which is the only place RBAC, config and probes are defined.
#
# This used to rewrite an image line in a hand-maintained deploy/dashboard.yaml and apply
# that. Two things were wrong with it. The rewrite was already dead — its regex required the
# internal-registry form and the file had been switched to a Quay ref, so it matched 0 lines
# and the script would have aborted on `found 0`. And the manifest itself had drifted 62
# commits behind the chart, missing the coordination.k8s.io/leases grant without which the
# poller never polls while both probes still pass.
#
# The tag no longer needs writing anywhere: --set carries it, and `helm get values` records
# what is deployed. For plain YAML to read or diff, use ./render-manifests.sh.
#
# -f IS MANDATORY, and this script shipped without it. `helm upgrade` does NOT carry forward
# the previous upgrade's --set values: it starts from the chart defaults and applies only what
# this invocation passes. So an upgrade carrying just the image tag RESETS everything else.
#
# Measured, on this cluster, by this script: a deploy that passed only --set image.* reported
# "successfully rolled out" and silently turned oauthProxy.apiTokenAccess off, removing
# -openshift-delegate-urls from the proxy container. Bearer-token API access — curl and
# Postman against the destination cluster — was gone, with nothing in the Helm output, the
# rollout status or the pod events to say so. build-and-push-external.sh was fixed for this
# exact defect and this script was missed.
#
# Passing -f every time makes the upgrade declarative: the file is the desired state and --set
# carries only what genuinely varies per invocation (the tag just built).
if [ ! -f "$RELEASE_VALUES" ]; then
  echo "ERROR: no release values file at ${RELEASE_VALUES}" >&2
  echo "       Deploying without one resets the release to chart defaults and silently" >&2
  echo "       drops whatever a previous upgrade configured." >&2
  echo "       Fix: RELEASE_VALUES=<path>, or restore ../environments/crc.yaml." >&2
  exit 1
fi
echo "release : ${RELEASE_VALUES}"

if [ "$ARGOCD" = true ]; then
  # The commit must be on the remote the Application pulls from.
  if ! git branch -r --contains "${COMMIT%-dirty}" 2>/dev/null | grep -q .; then
    echo "ERROR: commit ${COMMIT} is not on any remote branch; Argo CD pulls from GitHub, not this tree." >&2
    echo "       Push it first:  git push -u origin ${BRANCH}" >&2
    exit 1
  fi
  if helm status "${IMAGE}" -n "${NAMESPACE}" >/dev/null 2>&1; then
    echo "helm    : uninstalling release ${IMAGE} (the PVCs and the minted Secrets survive)"
    helm uninstall "${IMAGE}" -n "${NAMESPACE}" --wait --timeout 5m
  fi
  oc apply -f ../gitops/argocd-application-dashboard.yaml >/dev/null
  echo "argocd  : ${APP_NAME} -> revision ${COMMIT}, image ${TAG}"
  [ -n "$ARGO_VALUES" ] && echo "values  : ${VALUES_FILE} (the Application's valueFiles)"
  oc patch application "${APP_NAME}" -n "${ARGO_NAMESPACE}" --type json -p "[
    {\"op\":\"replace\",\"path\":\"/spec/source/targetRevision\",\"value\":\"${COMMIT}\"},
    {\"op\":\"add\",\"path\":\"/spec/source/helm/parameters\",\"value\":[
      {\"name\":\"image.repository\",\"value\":\"${INTERNAL%:*}\"},
      {\"name\":\"image.tag\",\"value\":\"${TAG}\"},
      {\"name\":\"reporting.image.repository\",\"value\":\"${REPORT_INTERNAL%:*}\"},
      {\"name\":\"reporting.image.tag\",\"value\":\"${TAG}\"}]}$(argo_values_patch)]"
  ./argocd-wait.sh "${APP_NAME}" "${ARGO_NAMESPACE}"
else
  if oc get application "${APP_NAME}" -n "${ARGO_NAMESPACE}" >/dev/null 2>&1; then
    echo "argocd  : deleting Application ${APP_NAME} — Helm takes the release over (the PVCs and the minted Secrets survive)"
    oc delete application "${APP_NAME}" -n "${ARGO_NAMESPACE}" --timeout=5m
    # the hook identity Argo's cascade leaves behind would refuse Helm's adoption
    oc delete sa,role,rolebinding "${IMAGE}-secrets-mint" -n "${NAMESPACE}" --ignore-not-found >/dev/null
  fi
helm upgrade --install "${IMAGE}" ../charts/group-sync-dashboard \
  --namespace "${NAMESPACE}" --create-namespace \
  -f "$RELEASE_VALUES" \
  --set image.repository="${INTERNAL%:*}" \
  --set image.tag="${TAG}" \
  --set reporting.image.repository="${REPORT_INTERNAL%:*}" \
  --set reporting.image.tag="${TAG}"
fi
oc rollout status "deploy/${IMAGE}" -n "${NAMESPACE}" --timeout=300s
if oc get "deploy/${IMAGE}-report" -n "${NAMESPACE}" >/dev/null 2>&1; then
  oc rollout status "deploy/${IMAGE}-report" -n "${NAMESPACE}" --timeout=300s
fi

# Prove the running pod is the build we just made, not a cached older one.
sleep 5
RUNNING=$(oc exec -n "${NAMESPACE}" "deploy/${IMAGE}" -- sh -c 'echo "$GSD_GIT_COMMIT"' 2>/dev/null | tr -d '\r\n')
if [ "$RUNNING" != "$COMMIT" ]; then
  echo "ERROR: pod reports commit '${RUNNING}', expected '${COMMIT}'" >&2
  exit 1
fi
echo "running : ${COMMIT} — verified in-pod"
