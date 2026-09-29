#!/usr/bin/env bash
# The #449 measurement's only writes to the lab, each logged to evidence/<file> with its command and instant:
#   lab.sh secret        the throwaway cluster Secret gsd-cluster-logins-449 (name logins-449, server
#                        https://api.crc.testing:6443). Its config is gsd-cluster-shared-rnd's `bearerToken` and
#                        `tlsClientConfig`, copied through a jq pipe into a 0600 mktemp manifest this script removes: the
#                        token is never printed and never on an argv. No annotation is copied (shared-rnd's name the
#                        fleet account); no saTokenLookup and no ldapConnectionBootstrap, so no fleet path can run for it.
#   lab.sh login <dir>   ONE `oc login` as developer into a throwaway kubeconfig <dir>/kubeconfig (KUBECONFIG is
#                        pointed at it for that one command, so the lab kubeconfig is never written). The password is
#                        read from `crc console --credentials` into a variable and reaches oc on its stdin through
#                        bash's printf builtin: never an argument, never printed. The API's CA comes from the lab
#                        kubeconfig's certificate-authority-data, so TLS is verified.
#   lab.sh logout <dir>  `oc logout` on that throwaway kubeconfig: the login's OAuth token is revoked
#   lab.sh delete        everything carrying the run's label (the Secret)
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=logins-449-2026-09-29
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
redact() { sed -E -e 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g'; }
log() { local out="${here}/evidence/$1"; shift; { printf '# %s\n# at %s\n' "$*" "$(now)"; "$@" 2>&1 | redact; } >> "${out}"; }

case "${1:?secret|login|logout|delete}" in
  secret)
    umask 077
    manifest=$(mktemp)
    trap 'rm -f "${manifest}"' EXIT
    oc get secrets -n "${ns}" gsd-cluster-shared-rnd -o json | jq --arg label "${run_label#*=}" '{
        apiVersion: "v1", kind: "Secret", type: "Opaque",
        metadata: {name: "gsd-cluster-logins-449", namespace: "group-sync-dashboard",
                   labels: {"groupsync-dashboard.io/secret-type": "cluster", "walk.gsd.lab/run": $label}},
        data: {name: ("logins-449" | @base64), server: ("https://api.crc.testing:6443" | @base64),
               config: (.data.config | @base64d | fromjson | {bearerToken, tlsClientConfig} | tojson | @base64)}}' > "${manifest}"
    log secret-create.txt stat -f 'manifest mode %Lp' "${manifest}"
    log secret-create.txt oc create -f "${manifest}"
    f=secret-create
    ;;
  login)
    dir="${2:?the throwaway directory}"
    kc="${dir}/kubeconfig"; ca="${dir}/ca.crt"
    oc config view --raw --minify -o json | jq -r '.clusters[0].cluster["certificate-authority-data"]' | base64 -d > "${ca}"
    pw="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)"
    stamp() { python3 -c 'import datetime; print(datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))'; }
    {
      printf '# KUBECONFIG=<throwaway>/kubeconfig oc login https://api.crc.testing:6443 -u developer --certificate-authority=<the lab CA> (password on stdin)\n'
      printf '# started at %s\n' "$(stamp)"
      set +e
      printf '%s\n' "${pw}" | KUBECONFIG="${kc}" oc login https://api.crc.testing:6443 -u developer \
        --certificate-authority="${ca}" 2>&1 | redact
      rc=${PIPESTATUS[1]}
      set -e
      printf '# exit %s, ended at %s\n' "${rc}" "$(stamp)"
      printf '# whoami on the throwaway kubeconfig: %s\n' "$(KUBECONFIG="${kc}" oc whoami 2>&1)"
    } >> "${here}/evidence/login.txt"
    unset pw
    f=login
    ;;
  logout)
    dir="${2:?the throwaway directory}"
    log logout.txt env KUBECONFIG="${dir}/kubeconfig" oc logout
    f=logout
    ;;
  delete)
    log delete.txt oc delete secrets -n "${ns}" -l "${run_label}" --ignore-not-found
    f=delete
    ;;
  *) echo "usage: lab.sh secret|login <dir>|logout <dir>|delete" >&2; exit 2 ;;
esac
cat "${here}/evidence/${f}.txt"
