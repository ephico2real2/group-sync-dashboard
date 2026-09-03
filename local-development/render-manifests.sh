#!/usr/bin/env bash
# Render the Helm chart to plain YAML, one file per object, for inspection and testing.
#
#   ./render-manifests.sh                    # render to deploy/
#   ./render-manifests.sh -n my-namespace    # render for a different namespace
#   ./render-manifests.sh -o /tmp/x          # render somewhere else
#   ./render-manifests.sh --set key=value    # any extra helm flags, passed straight through
#
# Then look at what you got, and apply it yourself:
#
#   oc diff  -f deploy/     # what would change
#   oc apply -f deploy/     # do it
#
# This script never applies anything. That is the point — the folder exists so a human (or a
# review, or a diff in a ticket) sees the exact objects before the cluster does.
#
# WHY THIS EXISTS AT ALL, given `helm upgrade` is right there: a hand-written copy of the
# manifests used to live in deploy/. It went 62 commits stale without anyone noticing, missed
# the coordination.k8s.io/leases grant the poller needs to poll at all, and applying it over a
# live release stripped the oauth-proxy sidecar off a dashboard that serves group membership.
# A second hand-maintained source of truth for RBAC and config cannot be kept honest. A
# generated one is honest by construction: it is the chart, rendered.
#
# THE SUPPORTED DEPLOY IS STILL `helm upgrade --install`. Applying rendered YAML leaves no
# Helm release, so `helm list`, `helm rollback` and `helm diff` know nothing about it. Use
# this folder to read, to test, and to hand to something that wants plain YAML. Do not mix
# the two paths against the same namespace and expect Helm's stored state to stay truthful.

set -euo pipefail
cd "$(dirname "$0")"

CHART="../charts/group-sync-dashboard"
RELEASE="group-sync-dashboard"
NAMESPACE="${K8S_NAMESPACE:-group-sync-dashboard}"
OUTDIR="deploy"
EXTRA=()

while [ $# -gt 0 ]; do
  case "$1" in
    -n|--namespace) NAMESPACE="$2"; shift 2 ;;
    -o|--output)    OUTDIR="$2";    shift 2 ;;
    -h|--help)      sed -n '2,27p' "$0"; exit 0 ;;
    *)              EXTRA+=("$1");  shift ;;
  esac
done

# ---------------------------------------------------------------------------
# Two values the chart normally reads from the live cluster
# ---------------------------------------------------------------------------
# `helm template` runs with no cluster connection, so every `lookup` in the chart returns
# empty. Two of them matter, and both fail QUIETLY rather than loudly, which is why they are
# resolved here instead of being left to the chart.

# 1. The Ingress host — ONLY when the Ingress is turned on. The default Route needs no host:
#    the router names it from spec.subdomain, so the chart does no lookup and the render needs
#    no cluster at all — that default exists precisely for renderers like this one. With
#    `--set ingress.enabled=true` the chart's own guard aborts a hostless render (deliberately:
#    a hostless Ingress produces no Route on OpenShift, so the release would install cleanly
#    and be unreachable), so derive the host the same way the chart does when it can.
#
#    <release>.<domain>, matching the chart's gsd.externalHost — NOT <release>-<namespace>,
#    which is what this line used to derive and what the chart never emitted.
#
#    Only `--set` / `--set-string` assignments are inspected, parsed as Helm parses them: the
#    option's value (attached with `=` or as the next argument), split on commas, each piece
#    matched as a whole `key=value`. A bare substring match was the previous shape and the Codex
#    review of #45 showed it firing on unrelated arguments that merely CONTAINED the text. A
#    values file that turns the Ingress on must also carry its host; -f is not read here.
INGRESS_ON=""; HOST=""
inspect_assignments() {
  # $1: a comma-separated list of key=value assignments from one --set/--set-string option.
  local IFS=','; local pair
  for pair in $1; do
    case "$pair" in
      ingress.enabled=true) INGRESS_ON="yes" ;;
      ingress.host=?*)      HOST="already-set" ;;
    esac
  done
}
# The `${EXTRA[@]+...}` form is the bash-3.2-safe way to expand a possibly-empty array under
# `set -u`, and macOS ships bash 3.2 at /bin/bash.
pending=""
for arg in "${EXTRA[@]+"${EXTRA[@]}"}"; do
  if [ -n "$pending" ]; then inspect_assignments "$arg"; pending=""; continue; fi
  case "$arg" in
    --set|--set-string)     pending="yes" ;;
    --set=*|--set-string=*) inspect_assignments "${arg#*=}" ;;
  esac
done
if [ -n "$INGRESS_ON" ] && [ -z "$HOST" ]; then
  DOMAIN=$(oc get ingresses.config/cluster -o jsonpath='{.spec.domain}' 2>/dev/null || true)
  if [ -z "$DOMAIN" ]; then
    echo "ERROR: ingress.enabled=true, but the cluster apps domain could not be read and no ingress.host was given." >&2
    echo "  Either log in to a cluster, or pass:  --set ingress.host=<host>" >&2
    exit 1
  fi
  EXTRA+=(--set "ingress.host=${RELEASE}.${DOMAIN}")
fi

# 2. The oauth-proxy cookie secret. THIS IS THE ONE THAT BITES.
#
#    The chart generates `randAlpha 32` when it cannot find an existing Secret, and reuses the
#    existing one when it can — via `lookup`, which works during `helm upgrade` and returns
#    empty here. So every render mints a NEW key, and applying two renders in a row signs
#    every logged-in user out. Measured: two consecutive `helm template` runs produce two
#    different session_secret values.
#
#    Reading the live one back keeps sessions alive across applies. If there is no live
#    Secret, the chart's fresh value is correct — say so, rather than letting it be a surprise.
COOKIE=$(oc get secret "${RELEASE}-oauth-cookie" -n "$NAMESPACE" \
           -o jsonpath='{.data.session_secret}' 2>/dev/null | base64 -d 2>/dev/null || true)
if [ -n "$COOKIE" ]; then
  EXTRA+=(--set "oauthProxy.cookieSecret=${COOKIE}")
  COOKIE_NOTE="reused from the live Secret — existing sessions survive this apply"
else
  COOKIE_NOTE="NEWLY GENERATED (no live Secret found) — applying this will sign out any existing sessions"
fi

# ---------------------------------------------------------------------------
# Render
# ---------------------------------------------------------------------------
# Clear only what a previous run wrote, never the directory itself.
#
# `rm -rf "$OUTDIR"` was the obvious way to do this and is a trap: OUTDIR comes from -o, so a
# mistyped path would delete something that has nothing to do with this project. Removing
# only files matching the generated NN-kind-name.yaml shape means the worst a bad -o can do
# is nothing at all, and it also refuses to quietly swallow a directory somebody was using
# for something else.
mkdir -p "$OUTDIR"
GENERATED=$(find "$OUTDIR" -maxdepth 1 -type f -name '[0-9][0-9]-*.yaml' | wc -l | tr -d ' ')
OTHER=$(find "$OUTDIR" -maxdepth 1 -type f ! -name '[0-9][0-9]-*.yaml' | wc -l | tr -d ' ')
if [ "$OTHER" != "0" ]; then
  echo "ERROR: ${OUTDIR}/ holds ${OTHER} file(s) this script did not generate." >&2
  echo "  Refusing to write into a directory that is not exclusively render output." >&2
  echo "  Move them, or choose another directory with -o." >&2
  find "$OUTDIR" -maxdepth 1 -type f ! -name '[0-9][0-9]-*.yaml' -exec basename {} \; >&2
  exit 1
fi
[ "$GENERATED" != "0" ] && find "$OUTDIR" -maxdepth 1 -type f -name '[0-9][0-9]-*.yaml' -delete

RAW=$(mktemp -t gsd-render).yaml
trap 'rm -f "$RAW"' EXIT
helm template "$RELEASE" "$CHART" --namespace "$NAMESPACE" \
  "${EXTRA[@]+"${EXTRA[@]}"}" > "$RAW"

# One file per OBJECT, not per template.
#
# `helm template --output-dir` splits per TEMPLATE, so rbac.yaml arrives holding both the
# ClusterRole and its binding. That renders fine, but it makes a review diff read as "rbac
# changed" when one of two unrelated objects moved. Splitting on kind+name means a diff names
# the object that actually changed.
#
# The NN- prefix is apply order, not decoration: `oc apply -f <dir>` processes files
# alphabetically, and the ServiceAccount has to exist before the binding that names it.
python3 - "$RAW" "$OUTDIR" <<'PY'
import pathlib
import sys

import yaml

raw, outdir = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])

# Creation order. Anything unlisted sorts after these, alphabetically by kind, so a new
# object type added to the chart still lands somewhere sensible without editing this.
ORDER = ["ServiceAccount", "Secret", "ConfigMap", "PersistentVolumeClaim",
         "ClusterRole", "ClusterRoleBinding", "Role", "RoleBinding",
         "Service", "Deployment", "Ingress", "PodDisruptionBudget",
         "ServiceMonitor", "PrometheusRule"]

docs = [d for d in yaml.safe_load_all(raw.read_text()) if d]
docs.sort(key=lambda d: (ORDER.index(d["kind"]) if d["kind"] in ORDER else len(ORDER),
                         d["kind"], d["metadata"]["name"]))

for i, doc in enumerate(docs, start=1):
    kind, name = doc["kind"], doc["metadata"]["name"]
    path = outdir / f"{i:02d}-{kind.lower()}-{name}.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False, default_flow_style=False))
    print(f"  {path.name}")

print(f"\n{len(docs)} objects")
PY

echo
echo "namespace : ${NAMESPACE}"
echo "cookie    : ${COOKIE_NOTE}"
echo
echo "NEXT — review, then apply yourself:"
echo "  oc diff  -f ${OUTDIR}/     # what would change"
echo "  oc apply -f ${OUTDIR}/     # do it"
echo
echo "The supported path is still: helm upgrade --install ${RELEASE} ${CHART} -n ${NAMESPACE}"
