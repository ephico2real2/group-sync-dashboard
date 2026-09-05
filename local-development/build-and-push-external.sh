#!/usr/bin/env bash
# Build the image from the Containerfile and push it to an EXTERNAL registry.
#
# This is the enterprise path: the image is built locally (offline, from the Containerfile
# in this repo) and pushed to a registry like Quay that every cluster can pull from. It has
# no dependency on any cluster's internal registry — unlike scripts/release.sh, which is a
# CRC-only convenience and only works against one cluster's built-in registry.
#
#   cp .env.example .env && $EDITOR .env      # once
#   ./build-and-push-external.sh                       # build + push
#   ./build-and-push-external.sh --build-only          # no push, no credentials needed
#   ./build-and-push-external.sh --deploy              # also roll it out to K8S_NAMESPACE
#   ./build-and-push-external.sh --create-pull-secret  # private repo: create/refresh the secret
#   ./build-and-push-external.sh --update-values       # build, push, and write the ref into
#                                                      # the chart's values.yaml for Helm
#   ./build-and-push-external.sh --release-tags        # ALSO publish the release aliases
#                                                      # :<appVersion> and :<chartVersion>
#
# THIS SCRIPT IS THE DISASTER-RECOVERY PATH. With --release-tags it does everything the publish
# workflow does, so a laptop can cut a release on the day GitHub Actions is unavailable. Nothing
# here depends on CI, and CI depends on this — .github/workflows/publish.yml calls this same file
# rather than reimplementing the tag scheme.
#
# TWO KINDS OF TAG, and the difference matters:
#   <appVersion>-<sha>  IMMUTABLE. Always pushed. A given tag always means the same source.
#   <appVersion>        A MOVING ALIAS, and what the chart resolves by default. Only with
#   <chartVersion>      --release-tags, because pushing these overwrites what the last release
#                       published — see the block above the push for why that is opt-in.
#
# ONE DIGEST, HOWEVER MANY NAMES. The immutable tag is pushed once and podman records the digest
# the registry acknowledged (--digestfile); the aliases are then made by `skopeo copy` from that
# pushed manifest, server side, and read back — so every name this script publishes resolves to
# the same bytes and a signature over the digest covers all of them. DIGEST_FILE=<path> in the
# environment receives a copy of the digest, which is how .github/workflows/publish.yml hands it
# to the job that signs it. --release-tags therefore needs skopeo, which ships beside podman.
#
# Configuration comes from .env (gitignored) or the environment. Credentials are never
# written to disk by this script, never echoed, and never passed on a command line that
# would show up in `ps`.

set -euo pipefail
cd "$(dirname "$0")"

BUILD_ONLY=false
DEPLOY=false
CREATE_PULL_SECRET=false
UPDATE_VALUES=false
ALLOW_DIRTY=false
RELEASE_TAGS=false
for arg in "$@"; do
  case "$arg" in
    --build-only)         BUILD_ONLY=true ;;
    --deploy)             DEPLOY=true ;;
    --create-pull-secret) CREATE_PULL_SECRET=true ;;
    --update-values)      UPDATE_VALUES=true ;;
    --allow-dirty)        ALLOW_DIRTY=true ;;
    --release-tags)       RELEASE_TAGS=true ;;
    # Prints the whole header rather than a hardcoded line range. `sed -n '2,20p'` silently
    # truncated --help the moment the header grew past line 20, which is how documentation
    # disappears without anyone noticing: the flag still works, it just stops being described.
    -h|--help)            awk 'NR>1 && !/^#/ {exit} NR>1' "$0"; exit 0 ;;
    *) echo "unknown argument: $arg" >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
if [ -f .env ]; then
  # Parsed, NOT sourced. `. ./.env` executes the file, so a placeholder like <change-me>
  # is a shell redirect and a syntax error, and any command substitution in the file would
  # run with your privileges. This reads KEY=VALUE literally: no evaluation, no execution,
  # and a password containing $ ` " or spaces survives intact.
  while IFS= read -r line || [ -n "$line" ]; do
    case "$line" in ''|'#'*) continue ;; esac
    case "$line" in *=*) ;; *) continue ;; esac
    key=${line%%=*}
    value=${line#*=}
    key=$(printf '%s' "$key" | tr -d '[:space:]')
    # Strip one layer of matching surrounding quotes, if present.
    case "$value" in
      \"*\") value=${value#\"}; value=${value%\"} ;;
      \'*\') value=${value#\'}; value=${value%\'} ;;
    esac
    export "$key=$value"
  done < .env
  echo "config  : .env"
else
  echo "config  : environment only (no .env found — copy .env.example if you need one)"
fi

REGISTRY="${REGISTRY:-}"
REGISTRY_NAMESPACE="${REGISTRY_NAMESPACE:-}"
IMAGE_NAME="${IMAGE_NAME:-group-sync-dashboard}"
K8S_NAMESPACE="${K8S_NAMESPACE:-group-sync-dashboard}"
IMAGE_PULL_SECRET="${IMAGE_PULL_SECRET:-}"
CONTAINERFILE="${CONTAINERFILE:-Containerfile}"

missing=()
[ -z "$REGISTRY" ] && missing+=(REGISTRY)
[ -z "$REGISTRY_NAMESPACE" ] && missing+=(REGISTRY_NAMESPACE)
if [ ${#missing[@]} -gt 0 ]; then
  echo "ERROR: missing required config: ${missing[*]}" >&2
  echo "       set them in .env (see .env.example) or in the environment" >&2
  exit 1
fi
# Checked BEFORE the build, not at the alias step forty seconds of build later. The aliases are
# server-side copies (see the release block), and skopeo is what makes them.
if [ "$RELEASE_TAGS" = true ] && ! command -v skopeo >/dev/null 2>&1; then
  echo "ERROR: --release-tags copies the aliases with skopeo, which is not on PATH." >&2
  exit 1
fi

# ---------------------------------------------------------------------------
# Version + immutable tag derived from the commit
# ---------------------------------------------------------------------------
VERSION=$(python3 -c "import re,pathlib;print(re.search(r'^version = \"(.+?)\"',pathlib.Path('pyproject.toml').read_text(),re.M).group(1))")
COMMIT=$(git rev-parse --short=10 HEAD)
BRANCH=$(git rev-parse --abbrev-ref HEAD)

if [ -n "$(git status --porcelain)" ]; then
  if [ "$ALLOW_DIRTY" != true ]; then
    echo "ERROR: working tree has uncommitted changes." >&2
    echo "       A tag derived from a commit must describe that commit's source." >&2
    echo "       Commit, or pass --allow-dirty to build a '-dirty' image." >&2
    git status --short >&2
    exit 1
  fi
  COMMIT="${COMMIT}-dirty"
  echo "WARNING: dirty tree; tagging ${COMMIT} — no commit reproduces this image"
fi

TAG="${VERSION}-${COMMIT}"
REF="${REGISTRY}/${REGISTRY_NAMESPACE}/${IMAGE_NAME}:${TAG}"

echo "registry: ${REGISTRY}/${REGISTRY_NAMESPACE}"
echo "image   : ${IMAGE_NAME}:${TAG}"
echo "commit  : ${COMMIT} (${BRANCH})"

# ---------------------------------------------------------------------------
# Build — offline, from the Containerfile in this repo
# ---------------------------------------------------------------------------
podman build \
  --build-arg "GIT_COMMIT=${COMMIT}" \
  --build-arg "GIT_BRANCH=${BRANCH}" \
  --build-arg "BUILD_VERSION=${VERSION}" \
  -t "${REF}" -f "${CONTAINERFILE}" .

# The stamp is the only thing tying a running pod back to source. If the build arg silently
# failed to apply, everything downstream would report a commit the image does not contain —
# so check it here, before anything is pushed anywhere.
STAMPED=$(podman run --rm --entrypoint sh "${REF}" -c 'echo "$GSD_GIT_COMMIT"' | tr -d '\r\n')
if [ "$STAMPED" != "$COMMIT" ]; then
  echo "ERROR: image reports commit '${STAMPED}', expected '${COMMIT}'" >&2
  exit 1
fi
echo "built   : ${REF} (stamp verified)"

if [ "$BUILD_ONLY" = true ]; then
  echo "done    : --build-only, nothing pushed"
  exit 0
fi

# ---------------------------------------------------------------------------
# Push
# ---------------------------------------------------------------------------
if [ -z "${REGISTRY_USERNAME:-}" ] || [ -z "${REGISTRY_PASSWORD:-}" ]; then
  echo "ERROR: REGISTRY_USERNAME and REGISTRY_PASSWORD are required to push." >&2
  echo "       Set them in .env, or use --build-only." >&2
  exit 1
fi
case "${REGISTRY_PASSWORD}" in
  "<change-me>"|"") echo "ERROR: REGISTRY_PASSWORD is still the placeholder." >&2; exit 1 ;;
esac

# --password-stdin, never -p: a password on the command line is visible in `ps` to every
# user on the machine and is captured by shell history.
if ! printf '%s' "${REGISTRY_PASSWORD}" \
     | podman login --username "${REGISTRY_USERNAME}" --password-stdin "${REGISTRY}" >/dev/null 2>&1; then
  echo "ERROR: podman login to ${REGISTRY} failed for user ${REGISTRY_USERNAME}" >&2
  echo "       (credential not echoed; check it in .env)" >&2
  exit 1
fi
echo "login   : ok as ${REGISTRY_USERNAME}"

# --digestfile: the digest the REGISTRY acknowledged, which is the only digest worth recording.
# `podman inspect` reports a local image ID, and a manifest digest computed before the push can
# differ from what lands after compression. Whatever signs this image signs THIS value.
DIGEST_OUT=$(mktemp)
podman push --digestfile "${DIGEST_OUT}" "${REF}"
DIGEST=$(tr -d '\r\n' < "${DIGEST_OUT}")
rm -f "${DIGEST_OUT}"
case "${DIGEST}" in
  sha256:[0-9a-f]*) ;;
  *) echo "ERROR: podman reported no sha256 digest for ${REF} (got '${DIGEST}')" >&2; exit 1 ;;
esac
echo "pushed  : ${REF}"
echo "digest  : ${DIGEST}"
if [ -n "${DIGEST_FILE:-}" ]; then
  printf '%s\n' "${DIGEST}" > "${DIGEST_FILE}"
  echo "digest  : written to ${DIGEST_FILE}"
fi

# ---------------------------------------------------------------------------
# Optional: the release aliases
# ---------------------------------------------------------------------------
# OPT-IN, AND THAT IS DELIBERATE. These two tags MOVE. `:<appVersion>` is what the chart resolves
# by default (values.yaml ships image.tag: "" and gsd.image falls back to .Chart.AppVersion), and
# values.yaml sets imagePullPolicy: Always — so every container creation re-resolves it. Pushing it
# from a routine build would silently make somebody's working tree the image every consumer runs,
# on their next crash or node drain, with no chart change to show for it.
#
# So: default off, and on only when you mean "this is the release". CI passes it exactly when a
# human changed `version` in pyproject.toml. Run it by hand when Actions is down and you are cutting
# a real release — that is the whole reason the flag exists rather than being CI-only behaviour.
if [ "$RELEASE_TAGS" = true ]; then
  # A DIRTY BUILD MUST NEVER BECOME AN ALIAS. The immutable tag already says `-dirty` and is honest
  # about it; an alias cannot be, because its name claims to be a released version. Refusing here
  # rather than warning: this is the one path where the mistake reaches every consumer.
  case "$COMMIT" in
    *-dirty) echo "ERROR: refusing --release-tags from a dirty tree." >&2
             echo "       The ${TAG} image is honest about being unreproducible; an alias named" >&2
             echo "       ${VERSION} would not be. Commit, then re-run." >&2
             exit 1 ;;
  esac

  # Read from the chart rather than taking it as an argument, for the same reason VERSION is read
  # from pyproject.toml: one definition of "what version is this", not two that can disagree.
  CHART="${CHART_FILE:-../charts/group-sync-dashboard/Chart.yaml}"
  if [ ! -f "$CHART" ]; then
    echo "ERROR: chart not found at ${CHART}; set CHART_FILE to point at it" >&2
    exit 1
  fi
  CHART_VERSION=$(python3 -c "import re,pathlib,sys
m = re.search(r'(?m)^version: (\d+\.\d+\.\d+)[ \t]*\$', pathlib.Path(sys.argv[1]).read_text())
sys.exit('no bare-semver version line in the chart') if not m else print(m.group(1))" "$CHART")

  # COPIED IN THE REGISTRY, NOT PUSHED AGAIN. A second `podman push` re-uploads from the local
  # store and can produce a different manifest digest for the same image — and then the alias
  # `:<appVersion>` would not resolve to the digest that was signed, so `cosign verify` on the
  # name every chart resolves would fail. `skopeo copy` between two tags of one repository moves
  # the manifest server side — the same call helm.yaml makes to label a chart's image — and the
  # digest is read back and compared, so an alias that is not byte-identical to the immutable
  # tag is a refusal here rather than a signature that fails on somebody's cluster.
  for alias in "${VERSION}" "${CHART_VERSION}"; do
    ALIAS_REF="${REGISTRY}/${REGISTRY_NAMESPACE}/${IMAGE_NAME}:${alias}"
    # --preserve-digests: skopeo's default is "the source manifest type, with fallbacks", and a
    # fallback (OCI<->Docker schema, gzip<->zstd) rewrites the manifest; with the flag skopeo fails
    # rather than modifying the image, which is the refusal this block wants, one step earlier.
    # --all: if podman pushed an index, copy the index and not only the host-arch child — otherwise
    # --digestfile (the index digest) and inspect (a child's) could never agree (review of A2).
    skopeo copy --all --preserve-digests "docker://${REF}" "docker://${ALIAS_REF}"
    ALIAS_DIGEST=$(skopeo inspect --no-tags --format '{{.Digest}}' "docker://${ALIAS_REF}")
    if [ "${ALIAS_DIGEST}" != "${DIGEST}" ]; then
      echo "ERROR: ${ALIAS_REF} resolves to ${ALIAS_DIGEST}, not ${DIGEST} — the alias is not the" >&2
      echo "       image that was pushed. Nothing else was changed; inspect both before retrying." >&2
      exit 1
    fi
    echo "pushed  : ${ALIAS_REF}  (alias of ${TAG}, ${DIGEST})"
  done
  echo "release : app ${VERSION}, chart ${CHART_VERSION} — both aliases now point at ${COMMIT}"
fi

# ---------------------------------------------------------------------------
# Optional: hand the built image to the Helm chart
# ---------------------------------------------------------------------------
# This is the Helm path: the script's job ends at producing an image and recording where it
# is. `helm upgrade` does the deploying, so values.yaml — not a patched manifest — is the
# record of what is deployed.
#
# Only image.repository and image.tag are touched. Rewriting more would silently discard
# whatever else the operator has tuned in that file.
if [ "$UPDATE_VALUES" = true ]; then
  VALUES="${VALUES_FILE:-../charts/group-sync-dashboard/values.yaml}"
  if [ ! -f "$VALUES" ]; then
    echo "ERROR: values file not found: ${VALUES}" >&2
    echo "       set VALUES_FILE to point at your chart's values.yaml" >&2
    exit 1
  fi
  python3 - "$VALUES" "${REGISTRY}/${REGISTRY_NAMESPACE}/${IMAGE_NAME}" "$TAG" <<'VALS'
import pathlib, re, sys
path, repo, tag = pathlib.Path(sys.argv[1]), sys.argv[2], sys.argv[3]
text = path.read_text()
text, n_repo = re.subn(r"(?m)^(  repository: ).*$", lambda m: m.group(1) + repo, text, count=1)
text, n_tag = re.subn(r'(?m)^(  tag: ).*$', lambda m: m.group(1) + f'"{tag}"', text, count=1)
if n_repo != 1 or n_tag != 1:
    sys.exit(f"expected one repository and one tag line under image:, found {n_repo}/{n_tag}")
path.write_text(text)
VALS
  echo "values  : ${VALUES} now pins ${TAG}"
  echo
  echo "NEXT: deploy with Helm"
  echo "  helm upgrade --install group-sync-dashboard ../charts/group-sync-dashboard \\"
  echo "    --namespace ${K8S_NAMESPACE} --create-namespace"
fi

# ---------------------------------------------------------------------------
# Optional: pull secret, only needed for a PRIVATE repository
# ---------------------------------------------------------------------------
if [ "$CREATE_PULL_SECRET" = true ]; then
  if [ -z "$IMAGE_PULL_SECRET" ]; then
    echo "ERROR: --create-pull-secret needs IMAGE_PULL_SECRET set in .env" >&2
    exit 1
  fi
  # Recreated rather than patched so a rotated credential fully replaces the old one.
  oc create secret docker-registry "${IMAGE_PULL_SECRET}" \
    --docker-server="${REGISTRY}" \
    --docker-username="${REGISTRY_USERNAME}" \
    --docker-password="${REGISTRY_PASSWORD}" \
    -n "${K8S_NAMESPACE}" --dry-run=client -o yaml | oc apply -f - >/dev/null
  echo "secret  : ${IMAGE_PULL_SECRET} created/updated in ${K8S_NAMESPACE}"
fi

if [ "$DEPLOY" != true ]; then
  echo
  echo "NEXT: deploy with"
  echo "  IMAGE_REF=${REF} ./build-and-push-external.sh --deploy"
  echo "or point your manifest at ${REF}"
  exit 0
fi

# ---------------------------------------------------------------------------
# Optional deploy
# ---------------------------------------------------------------------------
# The chart is the deployment path — the same reasoning as --update-values above, applied to
# the deploy step rather than only printed.
#
# This used to `oc apply -f deploy/dashboard.yaml`, a hand-maintained copy of the manifests.
# It went 62 commits stale without anything noticing. It lacked the coordination.k8s.io/leases
# grant the poller needs to poll at all, so a cluster deployed that way came up healthy on
# both probes and silently never polled; and because every object name collides with the Helm
# release, applying it over a live cluster stripped the oauth-proxy sidecar off a dashboard
# that serves group membership. A second hand-written source of truth for RBAC and config
# cannot be kept honest.
#
# For plain YAML — to read, to diff, or to hand to something that wants files — use
# ./render-manifests.sh, which generates it FROM this chart into deploy/.
#
# ingress.host is deliberately not passed: the chart derives it from the cluster's apps
# domain via `lookup`, which works here because this is a real upgrade, not a template render.
# THE VALUES FILE IS NOT OPTIONAL, and omitting it was a real bug in this script.
#
# Helm's upgrade precedence: with no -f and no --set it reuses the previous release's
# user-supplied values, but the moment EITHER is given it resets to chart defaults plus only
# what this invocation passed. So `--set image.tag=...` alone silently discards every value a
# previous upgrade set. Measured on this release — one `helm upgrade --set logLevel=DEBUG`
# turned oauthProxy.apiTokenAccess off, reported STATUS: deployed, and removed the
# delegate-urls flag from the pod, with no warning anywhere.
#
# Passing -f every time makes the upgrade declarative and idempotent: the file is the desired
# state, --set carries only what genuinely varies per invocation (the tag just built), and
# nothing depends on remembering a flag.
# RELEASE_VALUES, not VALUES_FILE: that name is already taken above for the CHART's
# values.yaml that --update-values rewrites. Reusing it would have made one variable mean two
# different files depending on which flag you passed — the kind of collision this project has
# been bitten by before.
RELEASE_VALUES="${RELEASE_VALUES:-../environments/${GSD_ENV:-crc}.yaml}"
if [ ! -f "$RELEASE_VALUES" ]; then
  echo "ERROR: no release values file at ${RELEASE_VALUES}" >&2
  echo "  Deploying without one resets the release to chart defaults and silently drops" >&2
  echo "  whatever a previous upgrade configured." >&2
  echo "  Fix: GSD_ENV=<name> for ../environments/<name>.yaml, or RELEASE_VALUES=<path>." >&2
  echo "  Start from ../environments/example-production.yaml." >&2
  exit 1
fi
echo "release : ${RELEASE_VALUES}"

helm upgrade --install group-sync-dashboard ../charts/group-sync-dashboard \
  --namespace "${K8S_NAMESPACE}" --create-namespace \
  -f "$RELEASE_VALUES" \
  --set image.repository="${REGISTRY}/${REGISTRY_NAMESPACE}/${IMAGE_NAME}" \
  --set image.tag="${TAG}" \
  ${IMAGE_PULL_SECRET:+--set "image.pullSecrets[0].name=${IMAGE_PULL_SECRET}"}
oc rollout status "deploy/${IMAGE_NAME}" -n "${K8S_NAMESPACE}" --timeout=300s

RUNNING=$(oc exec -n "${K8S_NAMESPACE}" "deploy/${IMAGE_NAME}" -- sh -c 'echo "$GSD_GIT_COMMIT"' 2>/dev/null | tr -d '\r\n')
if [ "$RUNNING" != "$COMMIT" ]; then
  echo "ERROR: pod reports commit '${RUNNING}', expected '${COMMIT}'" >&2
  exit 1
fi
echo "running : ${COMMIT} — verified in-pod"
