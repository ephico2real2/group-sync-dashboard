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
#   --values X                      Helm     worktree            as above              X (-f); X outside  X exists
#                                                                                      local-development/
#                                                                                      may be untracked
#                                                                                      or edited: not in
#                                                                                      the build context,
#                                                                                      so not "dirty"
#   --argocd                        Argo     GitHub @ HEAD       built, handed to the  the Application's  commit on a
#                                                                Application as        default (crc.yaml) remote branch
#                                                                helm.parameters
#   --argocd --values X             Argo     GitHub @ HEAD       same                  valueFiles          X committed,
#                                                                                      [../../X]          clean, pushed
#   --argocd <branch>               Argo     GitHub @ <branch>   the chart's default   default            branch on
#                                                                (the PUBLISHED quay                      origin; no
#                                                                image — lags main)                       in-pod check
#   --argocd <branch> --values X    Argo     GitHub @ <branch>   same                  [../../X]          X present at
#                                                                                                         origin/<branch>
#   --build-only                    (none)   —                   built, NOT pushed     —                  —
#   --allow-dirty --argocd          REFUSED: Argo deploys a commit and a dirty tree has none — the image
#                                   would not match the chart Argo reads, and uncommitted chart edits
#                                   would silently not deploy.
#   --build-only --argocd|--values  REFUSED: neither applies to a build (measured by review: `--argocd main
#                                   --build-only` ran the cutover with nothing built).
#
# Typical loop: iterate with the bare script (or --values for a local variant); before merging,
# --argocd on the pushed head; after a merge, --argocd main. The published images may lag main's
# code, not its schema: CI fails a migration merged without an app release (#298).
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
# (quay.io …:<appVersion>), which lags main's code whenever the app version is not bumped. Its
# schema no longer lags (#298); before that guard, the first Argo sync of the dashboard met a report
# image that understood snapshot schema 12 against main's 17 and answered readyz 503.
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
    revision) case "$arg" in -*) ;; *) ARGO_REVISION="$arg"; expect=""; continue ;; esac; expect="" ;;
    values) case "$arg" in -*) echo "--values needs a path, got ${arg}" >&2; exit 2 ;; esac
            VALUES_FILE="$arg"; expect=""; continue ;;
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
if [ "$BUILD_ONLY" = true ] && { [ "$ARGOCD" = true ] || [ -n "$VALUES_FILE" ]; }; then
  # `--argocd main --build-only` would run the branch path — a full cutover with nothing built.
  echo "ERROR: --build-only combines with --allow-dirty only; --argocd and --values do not apply to a build." >&2
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

# --argocd <branch>: the branch is resolved on origin FIRST. A fetch that fails must not fall
# through to a stale remote-tracking ref (measured by review: with the remote unreachable,
# `fetch || true` accepted a file that no longer existed there), and the commit it resolves to is
# what the waiter has to see synced — the Application's symbolic `targetRevision: main` does not
# change when main moves, so without it the previous sync's status would satisfy the waiter.
EXPECTED_REVISION=""
if [ "$ARGOCD" = true ] && [ -n "$ARGO_REVISION" ]; then
  # By the full ref, read back from FETCH_HEAD: a single-branch clone's refspec never creates
  # refs/remotes/origin/<branch>, and a fetch of a branch that is not there fails — both measured.
  if ! git fetch -q origin "refs/heads/${ARGO_REVISION}"; then
    echo "ERROR: branch ${ARGO_REVISION} is not on origin, or origin is unreachable; Argo CD reads from there." >&2
    exit 1
  fi
  EXPECTED_REVISION=$(git rev-parse --verify --quiet 'FETCH_HEAD^{commit}')
fi

# The values file under Argo is read from the repository: at origin/<branch> for the branch path,
# at this commit (so committed and clean) for the build path. Checked at the top level — an exit
# inside a command substitution would only leave the subshell.
if [ "$ARGOCD" = true ] && [ -n "$VALUES_FILE" ]; then
  if [ -n "$ARGO_REVISION" ]; then
    if ! git cat-file -e "${EXPECTED_REVISION}:${VALUES_FILE}" 2>/dev/null; then
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

# ONE write to the Application. The committed file is the base; the revision, the image parameters
# and the values file are merged into it locally and the result applied in a single request — an
# apply of the file followed by a patch would let the controller see the file's `main` with the
# published image in between and start syncing it (review finding). Merging locally also means the
# next apply carries the same fields in last-applied, so a run without --values or without an
# image really does return to the file's defaults. Arguments: revision, then the four image values
# or nothing (the branch path: the chart's default image, parameters cleared).
apply_application() {
  local revision="$1"; shift
  local patch
  patch=$(python3 - "$revision" "$ARGO_VALUES" "$@" <<'PY'
import json, sys
revision, values, *image = sys.argv[1:]
helm = {"parameters": [
    {"name": "image.repository", "value": image[0]}, {"name": "image.tag", "value": image[1]},
    {"name": "reporting.image.repository", "value": image[2]}, {"name": "reporting.image.tag", "value": image[3]},
] if image else []}
if values:
    helm["valueFiles"] = [values]
print(json.dumps({"spec": {"source": {"targetRevision": revision, "helm": helm}}}))
PY
)
  oc patch --local -f ../gitops/argocd-application-dashboard.yaml --type merge -p "$patch" -o json \
    | oc apply -f - >/dev/null
  # A spec change refreshes the comparison; a re-run on the same branch does not — force it, or
  # the waiter sits through the controller's polling interval (3 min by default).
  oc annotate application "${APP_NAME}" -n "${ARGO_NAMESPACE}" --overwrite argocd.argoproj.io/refresh=normal >/dev/null
}

# The values file Helm reads from this tree, before anything is built or pushed for it.
if [ "$ARGOCD" != true ] && [ ! -f "$RELEASE_VALUES" ]; then
  echo "ERROR: no release values file at ${RELEASE_VALUES}" >&2
  echo "       Deploying without one resets the release to chart defaults and silently" >&2
  echo "       drops whatever a previous upgrade configured." >&2
  echo "       Fix: RELEASE_VALUES=<path>, or restore ../environments/crc.yaml." >&2
  exit 1
fi

# --argocd <branch> with no build: point the Application at that branch and its chart's default
# image, e.g. `--argocd main` after a merge. Any other --argocd use builds this commit first.
if [ "$ARGOCD" = true ] && [ -n "$ARGO_REVISION" ]; then
  echo "argocd  : ${APP_NAME} -> revision ${ARGO_REVISION} (${EXPECTED_REVISION:0:10}), the chart's default image"
  if helm status "${IMAGE}" -n "${NAMESPACE}" >/dev/null 2>&1; then
    echo "helm    : uninstalling release ${IMAGE} (the PVCs and the minted Secrets survive)"
    helm uninstall "${IMAGE}" -n "${NAMESPACE}" --wait --timeout 5m
  fi
  [ -n "$ARGO_VALUES" ] && echo "values  : ${VALUES_FILE} (the Application's valueFiles)"
  apply_application "$ARGO_REVISION"
  exec ./argocd-wait.sh "${APP_NAME}" "${ARGO_NAMESPACE}" "${ARGOCD_WAIT_TIMEOUT:-900}" "${EXPECTED_REVISION}"
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
    *) DIRTY="$(git -C "$REPO_ROOT" status --porcelain -- . ":(exclude,top,literal)${VALUES_FILE}")" ;;
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

# Immutable tags: an existing <version>-<sha> is never overwritten. A CLEAN commit whose BOTH
# images are already in the registry is the same source, so it is REUSED without building — a
# Helm→Argo handover of the same commit does not rebuild — but a -dirty tag is a snapshot of
# nothing reproducible and is refused. One tag present without the other (an interrupted push)
# is rebuilt and pushed whole: the same commit under the same tag is the same source.
REPORT_IMAGE="${IMAGE}-report"
REPORT_REF="${REGISTRY}/${NAMESPACE}/${REPORT_IMAGE}:${TAG}"
BUILD=true
if [ "$BUILD_ONLY" != true ]; then
  have_dash=false; have_report=false
  oc get istag "${IMAGE}:${TAG}" -n "${NAMESPACE}" >/dev/null 2>&1 && have_dash=true
  oc get istag "${REPORT_IMAGE}:${TAG}" -n "${NAMESPACE}" >/dev/null 2>&1 && have_report=true
  if [ "$have_dash" = true ] || [ "$have_report" = true ]; then
    case "$TAG" in
      *-dirty)
        echo "ERROR: ${TAG} already exists in the registry." >&2
        echo "       Tags are immutable — commit your changes so the tag advances." >&2
        exit 1 ;;
    esac
  fi
  if [ "$have_dash" = true ] && [ "$have_report" = true ]; then
    echo "reused  : ${TAG} is already in the registry, both images (the same commit); not building"
    BUILD=false
  fi
fi

if [ "$BUILD" = true ]; then
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
podman tag "${IMAGE}:${TAG}" "${REF}"
podman push --tls-verify=false "${REF}" >/dev/null
echo "pushed  : ${REF}"
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
  echo "argocd  : ${APP_NAME} -> revision ${COMMIT}, image ${TAG}"
  [ -n "$ARGO_VALUES" ] && echo "values  : ${VALUES_FILE} (the Application's valueFiles)"
  apply_application "$COMMIT" "${INTERNAL%:*}" "$TAG" "${REPORT_INTERNAL%:*}" "$TAG"
  ./argocd-wait.sh "${APP_NAME}" "${ARGO_NAMESPACE}" "${ARGOCD_WAIT_TIMEOUT:-900}" "$(git rev-parse HEAD)"
else
  # Only NotFound means Argo does not own the release. Any other failure (no token, no RBAC on
  # openshift-gitops, the API away) must not read as "absent": Helm would install under an
  # Application whose selfHeal undoes it (review finding).
  probe_err=$(oc get application "${APP_NAME}" -n "${ARGO_NAMESPACE}" -o name 2>&1 >/dev/null) && app_state=present || {
    case "$probe_err" in
      *NotFound*|*"not found"*) app_state=absent ;;
      *) echo "ERROR: cannot tell whether Application ${APP_NAME} exists: ${probe_err}" >&2; exit 1 ;;
    esac; }
  if [ "$app_state" = present ]; then
    # A sync mid-run (a hook Job) would re-create objects the finalizer is deleting, and Helm cannot
    # adopt them; let the operation finish first, bounded.
    for _ in $(seq 1 20); do
      [ "$(oc get application "${APP_NAME}" -n "${ARGO_NAMESPACE}" -o jsonpath='{.status.operationState.phase}' 2>/dev/null)" = Running ] || break
      echo "argocd  : a sync is running; waiting for it before the handover"; sleep 15
    done
    echo "argocd  : deleting Application ${APP_NAME} — Helm takes the release over (the PVCs and the minted Secrets survive)"
    oc delete application "${APP_NAME}" -n "${ARGO_NAMESPACE}" --timeout=5m
    # the hook identity Argo's cascade leaves behind would refuse Helm's adoption
    oc delete sa,role,rolebinding "${IMAGE}-secrets-mint" -n "${NAMESPACE}" --ignore-not-found >/dev/null
  fi
# --force-conflicts: the objects that survive the handover (the two PVCs) keep the fields Argo CD's
# server-side apply wrote, owned by argocd-controller. Helm 4 applies server-side too, so once the
# chart version moves their helm.sh/chart and app.kubernetes.io/version labels conflict and the
# install is refused (measured on CRC with Helm 4.3.0, chart 0.52.1 -> 0.53.0: "Apply failed with 3
# conflicts: conflicts with argocd-controller"). The chart is the desired state in this mode, so
# Helm takes those fields. The flag is server-side apply's only (`helm upgrade --help`), and Helm
# accepts it beside --server-side true, false and auto alike (measured, --dry-run=client).
helm upgrade --install "${IMAGE}" ../charts/group-sync-dashboard \
  --namespace "${NAMESPACE}" --create-namespace --force-conflicts \
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
