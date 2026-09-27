#!/usr/bin/env bash
# SPEC_S4c §3.12 step 0, the second check: the walk's values name only `developer`. Each file is rendered with
# `helm template` exactly as `release-crc.sh --values <file>` installs it (the chart from the tree, the file alone),
# and the rendered ConfigMap's clusters.yaml is read: fleetAccountUsername must be "developer", every
# ldapConnectionBootstrap must be developer, and `grep -c ocp-oauth-bind-serviceid` must be 0. The Argo CD shape
# (environments/crc.yaml, then the Application's valuesObject) is rendered beside them: it must count 1, so the check
# tells the two apart.
# Usage: render_check.sh <label> <repo root> <walk values file>...   -> evidence/<label>-render-check.txt
# Exit 0 only when every walk file passes and the Argo shape counts 1. Offline: helm template reads no cluster.
set -euo pipefail
label="${1:?label}"; root="${2:?repo root}"; shift 2
here="$(cd "$(dirname "$0")/.." && pwd)"
out="${here}/evidence/${label}-render-check.txt"
F=ocp-oauth-bind-serviceid
tmp=$(mktemp -d); trap 'rm -rf "${tmp}"' EXIT
chart="${root}/charts/group-sync-dashboard"
ok=true

clusters_yaml() {  # the rendered ConfigMap's clusters.yaml, from helm template's output on stdin
  yq -r 'select(.kind == "ConfigMap" and .metadata.name == "group-sync-dashboard-config") | .data["clusters.yaml"]'
}

{
  echo "# helm $(helm version --short); chart $(yq -r .version "${chart}/Chart.yaml"), appVersion $(yq -r .appVersion "${chart}/Chart.yaml"); tree $(git -C "${root}" rev-parse --short=10 HEAD); $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  for values in "$@"; do
    helm template group-sync-dashboard "${chart}" -n group-sync-dashboard -f "${values}" > "${tmp}/render.yaml"
    clusters_yaml < "${tmp}/render.yaml" > "${tmp}/clusters.yaml"
    user=$(grep -E '^fleetAccountUsername:' "${tmp}/clusters.yaml" || echo '(none)')
    boots=$(grep -E 'ldapConnectionBootstrap:' "${tmp}/clusters.yaml" | sed -E 's/^ *//' | sort | uniq -c | sed -E 's/^ +//' | tr '\n' ';' || true)
    others=$(grep -E 'ldapConnectionBootstrap:' "${tmp}/clusters.yaml" | grep -v -c -E 'ldapConnectionBootstrap: "?developer"?$' || true)
    n=$(grep -c "${F}" "${tmp}/clusters.yaml" || true)
    whole=$(grep -c "${F}" "${tmp}/render.yaml" || true)
    verdict=PASS
    [ "${user}" = 'fleetAccountUsername: "developer"' ] && [ "${others}" = 0 ] && [ -n "${boots}" ] && [ "${n}" = 0 ] || verdict=FAIL
    [ "${verdict}" = PASS ] || ok=false
    echo "${verdict} $(basename "${values}"): ${user}; ldapConnectionBootstrap lines: ${boots:-none}; not developer: ${others};" \
         "grep -c ${F} in clusters.yaml: ${n} (in the whole render: ${whole}); fleet keys: $(grep -E '^fleet' "${tmp}/clusters.yaml" | tr '\n' ' ')"
  done
  helm template group-sync-dashboard "${chart}" -n group-sync-dashboard -f "${root}/environments/crc.yaml" \
    -f "${here}/prepared/argo-clusters-override.yaml" > "${tmp}/argo.yaml"
  clusters_yaml < "${tmp}/argo.yaml" > "${tmp}/argo-clusters.yaml"
  a=$(grep -c "${F}" "${tmp}/argo-clusters.yaml" || true)
  [ "${a}" = 1 ] || ok=false
  echo "the Argo CD shape (environments/crc.yaml + prepared/argo-clusters-override.yaml): grep -c ${F} in clusters.yaml: ${a} (expected 1); $(grep -E '^fleetAccountUsername:' "${tmp}/argo-clusters.yaml")"
} > "${out}"   # a redirect, not a pipe: `ok` must survive the group
cat "${out}"
${ok}
