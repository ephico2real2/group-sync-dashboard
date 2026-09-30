#!/usr/bin/env bash
# The pixel-level redaction check (after reports/2026-09-30_release-2.0.0-walk/scripts/ocr-redaction.sh): OCR every PNG
# in the folder and count, per image, the recognised lines that name the fleet account (the full name, or its middle
# fragment `cut -d- -f2-3`, any case). A text grep cannot read pixels; this can. The positive controls are UNMASKED
# captures of the same row kept outside the repo: each must hit at least once, or the check proves nothing.
# Writes evidence/ocr-redaction.txt: the command, the counts per image, never the name.
#   OCR=<a macOS Vision OCR binary printing "<path>\t<line>"> GSD_WALK_TMP=<a directory outside the repo> \
#   KUBECONFIG=<the lab kubeconfig> scripts/ocr-redaction.sh <positive-control image> ...
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
out="${here}/evidence/ocr-redaction.txt"
: "${OCR:?}"; : "${GSD_WALK_TMP:?}"; : "${KUBECONFIG:?}"
[ "$#" -gt 0 ] || { echo "name at least one positive-control image" >&2; exit 2; }
fleet=$(oc get leases.coordination.k8s.io -n group-sync-dashboard -l groupsync-dashboard.io/lease-type=fleet-account -o json \
  | jq -r '[.items[].metadata.annotations["groupsync-dashboard.io/account"]] | if length == 1 then .[0] else error("expected one fleet Lease") end')
mid=$(printf '%s' "${fleet}" | cut -d- -f2-3)
# count <file>: recognised lines in that one image naming the account (full name or middle fragment, any case)
count() { "${OCR}" "$1" | grep -i -F -c -e "${fleet}" -e "${mid}" || true; }
{
  echo "# OCR each image and count recognised lines naming the fleet account (full name or its middle fragment, any case)"
  echo "# at $(date -u +%Y-%m-%dT%H:%M:%SZ); OCR = macOS Vision (VNRecognizeTextRequest)"
  echo "# \"\${OCR}\" <image> | grep -i -F -c -e '<the fleet account>' -e '<its middle fragment: cut -d- -f2-3>'"
  echo "# positive controls (UNMASKED, outside the repo; each must be >= 1):"
  for f in "$@"; do echo "#   <tmp>/$(basename "${f}"): $(count "${f}")"; done
  echo "# every PNG in the folder (each must be 0):"
  total=0
  while IFS= read -r f; do
    n=$(count "${f}"); total=$((total + n))
    echo "#   ${f#"${here}/"}: ${n}"
  done < <(find "${here}" -name '*.png' | sort)
  echo "# PNGs in the folder: $(find "${here}" -name '*.png' | wc -l | tr -d ' '); lines naming the account across them: ${total}"
} > "${out}"
echo "wrote ${out}"
