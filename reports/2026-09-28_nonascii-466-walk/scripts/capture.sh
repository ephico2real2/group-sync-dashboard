#!/usr/bin/env bash
# The #466 walk's read-only captures: each writes evidence/<label>-<kind>.txt beside scripts/, the command line first.
# The shape of ../../2026-09-28_batch-1110-walk/scripts/capture.sh, with this run's label and a pod-log reader for #466.
#   capture.sh version <label>          /api/version through the dashboard pod's loopback
#   capture.sh pvcs <label>             the kept PVCs' names and UIDs
#   capture.sh cani <label>             `oc auth can-i update clusterrolebindings --as=developer`
#   capture.sh grant <label>            the walk's grant, selected by its label (empty once removed)
#   capture.sh lease <label>            the fleet Lease: resourceVersion and holder only
#   capture.sh sharedqa <label>         shared-qa's Secret: resourceVersion only (never its data)
#   capture.sh secret <label>           the throwaway Secret, by the run label: metadata, data and config KEYS, and
#                                       facts about caData (its non-ASCII code points, its first line, its PEM
#                                       markers); never the bearer token
#   capture.sh podlog <label> <since>   the dashboard container's lines since <since> (RFC 3339): every discovery and
#                                       secret-refused line, every line naming walk-466, the `polled <cluster>:`
#                                       count per cluster, and the Traceback / TypeError / unhandled / ERROR counts (a secret-
#                                       refused line's detail may itself name TypeError: it is counted apart)
# Every command is a read. No password or token is printed; the fleet account's name is read from its Lease into a
# variable and replaced by `<fleet account>` in everything written, and any `sha256~` token is redacted.
set -euo pipefail
kind="${1:?kind}"; label="${2:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"   # the report folder
out="${here}/evidence/${label}-${kind}.txt"
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=nonascii-466-2026-09-28
lease_label=groupsync-dashboard.io/lease-type=fleet-account
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
fleet=$(oc get leases.coordination.k8s.io -n "${ns}" -l "${lease_label}" -o json \
  | jq -r '[.items[].metadata.annotations["groupsync-dashboard.io/account"]] | if length == 1 then .[0] else error("expected one fleet Lease") end')
redact() { sed -E -e 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g' -e "s/${fleet}/<fleet account>/g"; }

run() {  # the command line, the instant, then its output
  printf '# %s\n# at %s\n' "$*" "$(now)"
  bash -c "$*" 2>&1 | redact
}

case "${kind}" in
  version)
    run "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- python3.14 -c 'import urllib.request; print(urllib.request.urlopen(\"http://127.0.0.1:8080/api/version\").read().decode())'" > "${out}"
    ;;
  pvcs)
    run "oc get persistentvolumeclaims -n ${ns} -o custom-columns=N:.metadata.name,U:.metadata.uid" > "${out}"
    ;;
  cani)
    run "oc auth can-i update clusterrolebindings.rbac.authorization.k8s.io --as=developer || true" > "${out}"
    ;;
  grant)
    run "oc get clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io -l ${run_label} -o wide" > "${out}"
    ;;
  lease)
    run "oc get leases.coordination.k8s.io gsd-fleet-666f1ba7f2fdead0 -n ${ns} -o jsonpath='resourceVersion={.metadata.resourceVersion} holderIdentity=\"{.spec.holderIdentity}\" renewTime={.spec.renewTime}{\"\\n\"}'" > "${out}"
    ;;
  sharedqa)
    run "oc get secrets gsd-cluster-shared-qa -n ${ns} -o jsonpath='resourceVersion={.metadata.resourceVersion}{\"\\n\"}'" > "${out}"
    ;;
  secret)
    run "oc get secrets -n ${ns} -l ${run_label} -o json | jq '[.items[] | (.data.config | @base64d | fromjson) as \$cfg | (\$cfg.tlsClientConfig.caData // \"\" | @base64d) as \$ca | {name: .metadata.name, uid: .metadata.uid, resourceVersion: .metadata.resourceVersion, created: .metadata.creationTimestamp, labels: .metadata.labels, annotations: (.metadata.annotations // {}), data_keys: (.data | keys), name_value: (.data.name | @base64d), server: (.data.server | @base64d), config_keys: (\$cfg | keys), tlsClientConfig_keys: (\$cfg.tlsClientConfig | keys), caData_first_line: (\$ca | split(\"\\n\")[0]), caData_non_ascii_code_points: (\$ca | explode | map(select(. > 127))), caData_pem_begin_lines: (\$ca | [scan(\"-----BEGIN [A-Z ]+-----\")]), caData_pem_end_lines: (\$ca | [scan(\"-----END [A-Z ]+-----\")])}]'" > "${out}"
    ;;
  podlog)
    since="${3:?since (RFC 3339)}"
    pod=$(oc get pods -n "${ns}" -l app.kubernetes.io/name=group-sync-dashboard -o jsonpath='{.items[0].metadata.name}')
    raw=$(mktemp); trap 'rm -f "${raw}"' EXIT
    oc logs -n "${ns}" "${pod}" -c dashboard --timestamps --since-time="${since}" > "${raw}"
    count() { grep -c -E -- "$1" "${raw}" || true; }
    {
      echo "# oc logs -n ${ns} ${pod} -c dashboard --timestamps --since-time=${since}  (captured $(now))"
      echo "# lines in the window: $(wc -l < "${raw}" | tr -d ' ')"
      echo "# discovery and secret-refused lines, and every line naming walk-466:"
      grep -E ' gsd.clusterconfig (discovery|secret-refused) |walk-466' "${raw}" | redact || true
      echo "# discovery lines: $(count ' gsd.clusterconfig discovery ')"
      echo "# secret-refused lines: $(count ' gsd.clusterconfig secret-refused ')"
      echo "# lines naming walk-466: $(count 'walk-466')"
      echo "# 'polled <cluster>:' lines per cluster (one per successful poll):"
      grep -o -E ' gsd.poller polled [a-z0-9-]+:' "${raw}" | awk '{print $3}' | sort | uniq -c || true
      echo "# the last 'polled <cluster>:' line per cluster:"
      grep -E ' gsd.poller polled [a-z0-9-]+:' "${raw}" \
        | awk '{c=$7; sub(":", "", c); last[c]=$0} END {for (c in last) print last[c]}' | sort -k7 | redact || true
      echo "# cluster-unreachable lines: $(count ' cluster-unreachable ')"
      echo "# fleet-login lines: $(count ' fleet-login ')"
      echo "# Traceback lines: $(count 'Traceback')"
      echo "# TypeError lines, all: $(count 'TypeError')"
      echo "# TypeError lines other than a secret-refused finding's detail: $(grep -v ' gsd.clusterconfig secret-refused ' "${raw}" | grep -c 'TypeError' || true)"
      echo "# 'TypeError:' (an exception's own line): $(count 'TypeError:')"
      echo "# 'unhandled error discovering' lines: $(count 'unhandled error discovering')"
      echo "# ERROR lines: $(count ' ERROR ')"
    } > "${out}"
    ;;
  *) echo "unknown kind ${kind}" >&2; exit 2 ;;
esac
echo "wrote ${out}"
