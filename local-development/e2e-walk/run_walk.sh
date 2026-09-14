#!/usr/bin/env bash
# One command for the whole walk: capture → second pass → integrity → env facts → document.
# Run from anywhere; uses local-development/.venv. The password comes from the environment only
# (GSD_UI_PASSWORD), never an argument — argv is visible to every process on the host.
#
#   GSD_UI_PASSWORD=$(cat ~/.crc/machines/crc/kubeadmin-password) \
#   KUBECONFIG=<the cluster's kubeconfig> \
#     local-development/e2e-walk/run_walk.sh \
#       --base https://group-sync-dashboard.apps-crc.testing --login-user kubeadmin \
#       --out /tmp/e2e/2026-09-14 [--provider developer] [--namespace group-sync-dashboard]
#       [--release group-sync-dashboard] [--namespaces ns1,ns2] [--skip-env]
#
# Exit 0 only if every scripted step and every integrity check passed. The document is built
# either way, so a failing walk still leaves the evidence of what failed.
set -euo pipefail
# Location-independent: everything resolves from the script's own path, so a fresh clone can run
# this from any working directory (`.../e2e-walk/run_walk.sh`, or via $PATH). No cwd assumption.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo="$(git -C "${here}" rev-parse --show-toplevel 2>/dev/null || printf '%s' "${here%/local-development/e2e-walk}")"
py="${here}/../.venv/bin/python"
[ -x "${py}" ] || py="${repo}/local-development/.venv/bin/python"
base=""; user=""; provider="developer"; out=""; ns="group-sync-dashboard"; rel="group-sync-dashboard"; namespaces=""; skip_env=0
while [ $# -gt 0 ]; do
  case "$1" in
    --base) base="$2"; shift 2 ;;
    --login-user) user="$2"; shift 2 ;;
    --provider) provider="$2"; shift 2 ;;
    --out) out="$2"; shift 2 ;;
    --namespace) ns="$2"; shift 2 ;;
    --release) rel="$2"; shift 2 ;;
    --namespaces) namespaces="$2"; shift 2 ;;
    --skip-env) skip_env=1; shift ;;
    *) echo "unknown argument: $1" >&2; exit 2 ;;
  esac
done
[ -n "${base}" ] && [ -n "${user}" ] && [ -n "${out}" ] || { echo "--base, --login-user and --out are required" >&2; exit 2; }
[ -n "${GSD_UI_PASSWORD:-}" ] || { echo "GSD_UI_PASSWORD is required in the environment" >&2; exit 2; }
[ -x "${py}" ] || { echo "no venv interpreter at ${py}" >&2; exit 2; }
mkdir -p "${out}"
rc=0

echo "== 1/5 main walk (login, every tab, every report)"
extra_args=(); [ -n "${namespaces}" ] && extra_args=(--namespaces "${namespaces}")
"${py}" "${here}/e2e_capture.py" --base "${base}" --login-user "${user}" --provider "${provider}" --out "${out}" "${extra_args[@]}" || rc=1

echo "== 2/5 second pass (second cluster, light theme, HTML reports opened, PDF page 1)"
"${py}" "${here}/e2e_extra.py" "${out}" --base "${base}" --login-user "${user}" --provider "${provider}" || rc=1

echo "== 3/5 integrity of the artefacts"
"${py}" "${here}/integrity_check.py" "${out}" || rc=1

if [ "${skip_env}" -eq 0 ]; then
  echo "== 4/5 environment facts (oc/helm through KUBECONFIG=${KUBECONFIG:-<unset>})"
  "${here}/env_facts.sh" "${ns}" "${rel}" > "${out}/env.json"
else
  echo "== 4/5 environment facts skipped (--skip-env); env.json must exist"; [ -f "${out}/env.json" ]
fi

echo "== 5/5 the document"
"${py}" "${here}/build_doc.py" "${out}" "${out}/env.json"
echo "walk finished with rc=${rc}: ${out}/doc/e2e_walk.pdf"
exit "${rc}"
