#!/usr/bin/env bash
# The pixel-level redaction check: OCR every PNG in the folder and every image embedded in e2e-walk.html, and count the
# recognised lines that name the fleet account (the full name, or its middle fragment `cut -d- -f2-3`, any case).
# A text grep cannot read pixels; this can. Writes evidence/ocr-redaction.txt: the commands, the counts per set, and
# the file names that hit — never the name.
#   OCR=<a macOS Vision OCR binary printing "<path>\t<line>"> GSD_WALK_TMP=<a directory outside the repo> \
#   KUBECONFIG=<the lab kubeconfig> scripts/ocr-redaction.sh [<positive-control image> ...]
# The positive-control images (kept outside the repo) must hit at least once, or the check proves nothing.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
out="${here}/evidence/ocr-redaction.txt"
: "${OCR:?}"; : "${GSD_WALK_TMP:?}"; : "${KUBECONFIG:?}"
fleet=$(oc get leases.coordination.k8s.io -n group-sync-dashboard -l groupsync-dashboard.io/lease-type=fleet-account -o json \
  | jq -r '[.items[].metadata.annotations["groupsync-dashboard.io/account"]] | if length == 1 then .[0] else error("expected one fleet Lease") end')
mid=$(printf '%s' "${fleet}" | cut -d- -f2-3)
emb="${GSD_WALK_TMP}/embedded"; rm -rf "${emb}"; mkdir -p "${emb}"
python3 - "${here}/e2e-walk.html" "${emb}" <<'PY'
import base64, pathlib, re, sys
html = pathlib.Path(sys.argv[1]).read_text()
for i, m in enumerate(re.finditer(r'src="data:image/(\w+);base64,([^"]+)"', html)):
    pathlib.Path(sys.argv[2], f"{i:02d}.{m.group(1)}").write_bytes(base64.b64decode(m.group(2)))
PY
# check <label> <files...>: the number of files, the number of recognised lines naming the account, the files that hit
check() {
  local label="$1"; shift
  local hits; hits=$("${OCR}" "$@" | grep -i -F -e "${fleet}" -e "${mid}" | cut -f1 || true)
  echo "# ${label}: files ${#}; lines naming the account $(printf '%s' "${hits}" | grep -c . || true)"
  printf '%s\n' "${hits}" | grep . | sort | uniq -c | sed -E "s|${GSD_WALK_TMP}|<tmp>|; s|${here}/||; s|^|#   hit: |" || true
}
{
  echo "# OCR every image and count recognised lines naming the fleet account (full name or its middle fragment, any case)"
  echo "# at $(date -u +%Y-%m-%dT%H:%M:%SZ); OCR = macOS Vision (VNRecognizeTextRequest, accurate, 1400-px bands)"
  echo "# \"\${OCR}\" <files> | grep -i -F -e '<the fleet account>' -e '<its middle fragment>'"
  if [ "$#" -gt 0 ]; then check "positive control (outside the repo)" "$@"; fi
  mapfile -t pngs < <(find "${here}" -name '*.png' | sort)
  mapfile -t embedded < <(find "${emb}" -type f | sort)
  check "every PNG in the folder" "${pngs[@]}"
  check "every image embedded in e2e-walk.html (extracted outside the repo)" "${embedded[@]}"
} > "${out}"
rm -rf "${emb}"
echo "wrote ${out}"
