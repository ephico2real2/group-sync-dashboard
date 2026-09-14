#!/usr/bin/env bash
# The cluster-side facts the walk document states, measured with oc and helm at build time and
# written as JSON. KUBECONFIG must point at the cluster the walk ran against — on the lab that is
# the separate kubeadmin kubeconfig, never the default oc context, which may be another cluster.
#
#   env_facts.sh <namespace> <helm release> > env.json
set -euo pipefail
ns="${1:?namespace}"; rel="${2:?helm release}"
node="$(oc get pods -n "${ns}" -o jsonpath='{.items[0].spec.nodeName}')"

pods="$(oc get pods -n "${ns}" --no-headers | awk '$3=="Running"{printf "%s (%s) ", $1, $2}')"
images="$(oc get deploy -n "${ns}" -o jsonpath='{range .items[*]}{.metadata.name}: {.spec.template.spec.containers[0].image}{"; "}{end}' \
  | sed 's|image-registry.openshift-image-registry.svc:5000/[^/]*/||g')"
helm_json="$(helm list -n "${ns}" -o json)"
chart="$(jq -r --arg r "${rel}" '.[] | select(.name==$r) | .chart' <<<"${helm_json}")"
rev="$(jq -r --arg r "${rel}" '.[] | select(.name==$r) | .revision' <<<"${helm_json}")"
upd="$(jq -r --arg r "${rel}" '.[] | select(.name==$r) | .updated' <<<"${helm_json}" | cut -c1-19)"
osv="$(oc get clusterversion version -o jsonpath='OpenShift {.status.desired.version}' 2>/dev/null || echo "Kubernetes $(oc version -o json | jq -r .serverVersion.gitVersion)")"
cpu="$(oc describe node "${node}" | grep -A 6 'Allocated resources' | awk '/cpu/{print $2" "$3}')"
pre="$(oc get events -n "${ns}" -o json \
  | jq -r '[.items[] | select(.reason=="Preempted") | (.eventTime // .firstTimestamp)] | sort | {n: length, first: (.[0] // ""), last: (.[-1] // "")}')"

jq -n --arg pods "${pods}" --arg images "${images}" --arg chart "${chart}" --arg rev "${rev}" --arg upd "${upd}" \
      --arg osv "${osv}" --arg cpu "${cpu}" --arg node "${node}" --argjson pre "${pre}" \
  '{pods:$pods, images:$images, chart:$chart, helm_revision:$rev, helm_updated:$upd, openshift:$osv,
    node:$node, node_cpu:$cpu, preemptions:$pre.n,
    preempt_first:(if $pre.first=="" then "" else $pre.first[0:19]+"Z" end),
    preempt_last:(if $pre.last=="" then "" else $pre.last[0:19]+"Z" end)}'
