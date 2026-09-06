#!/usr/bin/env bash
# The reporting image, through the SAME script and tag scheme as the dashboard image.
# build-and-push-external.sh already reads IMAGE_NAME and CONTAINERFILE from the environment; this
# wrapper sets them and refuses the two flags that target the dashboard's chart values
# (--update-values rewrites image.tag, --deploy rolls out deploy/<IMAGE_NAME>): the report image is
# resolved by the chart's reporting.image.* and deployed by the same `helm upgrade` as the dashboard.
set -euo pipefail
cd "$(dirname "$0")"
for arg in "$@"; do
  case "$arg" in
    --update-values|--deploy)
      echo "ERROR: $arg targets the dashboard image's values; the report image is reporting.image.* in the chart" >&2
      exit 2 ;;
  esac
done
IMAGE_NAME="${IMAGE_NAME:-group-sync-dashboard-report}" CONTAINERFILE=Containerfile.report exec ./build-and-push-external.sh "$@"
