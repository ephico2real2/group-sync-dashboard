#!/usr/bin/env bash
# The walk Secret, gsd-walk-developer-password in group-sync-dashboard, labelled walk.gsd.lab/run=<the run>.
#   create  `developer`'s password, read from `crc console --credentials` inside this command
#   wrong   a random 32-hex-digit password, rotated in place with `oc replace` (SPEC_S4c §3.12 steps 3 and 5)
#   right   `developer`'s password again, rotated back in place with `oc replace`
# The password is read into a variable inside this process and handed to oc through `--from-literal` and a pipe:
# never echoed, never written to a file, a log or this script. `oc replace`, never `oc apply`: apply would copy the
# value into the last-applied annotation. `oc create` and `oc replace` save no last-applied copy. A rotation keeps
# the Secret's uid, which salts the Lease's digests (gsd/fleetstate.py#lease_digest).
# Prints the Secret's name, resourceVersion and uid — never its data.
set -euo pipefail
action="${1:?create|wrong|right}"
ns=group-sync-dashboard; name=gsd-walk-developer-password; run=epic-c-walk-432-2026-09-27
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
case "${action}" in
  create|right) pw=$(crc console --credentials -o json | jq -r '.clusterConfig.developerCredentials.password') ;;
  wrong) pw=$(openssl rand -hex 16) ;;
  *) echo "usage: walk_secret.sh create|wrong|right" >&2; exit 2 ;;
esac
if [ -z "${pw}" ] || [ "${pw}" = null ]; then echo "no password was read; nothing written" >&2; exit 1; fi
verb=replace; [ "${action}" = create ] && verb=create
printf '%s action=%s: ' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${action}"
oc create secret generic "${name}" -n "${ns}" --from-literal=password="${pw}" --dry-run=client -o json \
  | jq --arg run "${run}" '.metadata.labels = {"walk.gsd.lab/run": $run}' \
  | oc "${verb}" -f - -o jsonpath='{.metadata.name} resourceVersion={.metadata.resourceVersion} uid={.metadata.uid} last-applied={.metadata.annotations.kubectl\.kubernetes\.io/last-applied-configuration}{"\n"}'
unset pw
