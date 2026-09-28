#!/usr/bin/env bash
# The #404 walk's read-only captures: each writes evidence/<label>-<kind>.txt beside scripts/, the command line first.
#   capture.sh version <label>          /api/version through the dashboard pod's loopback
#   capture.sh pvcs <label>             the kept PVCs' names and UIDs
#   capture.sh cani <label>             `oc auth can-i update clusterrolebindings --as=developer`
#   capture.sh grant <label>            the walk's grant, selected by its run label (empty once removed)
#   capture.sh lease <label>            the fleet Lease: resourceVersion, holder, acquire/renew, its annotation keys
#                                       and the ping-last-* fields
#   capture.sh sharedqa <label>         shared-qa's Secret: resourceVersion only (never its data)
#   capture.sh onboarding <label>       ConfigMaps carrying the onboarding label, and the walk's map by its run label
#   capture.sh secret <label>           gsd-cluster-gitops-404: metadata and annotations only, or NotFound
#   capture.sh clusterrows <label>      the store's cluster rows (id, enabled, source, kind), opened read-only
#   capture.sh tokens <label>           the fleet account's OAuth access tokens, counted per client (never a name)
#   capture.sh audit <label> <since>    the oauth-server audit log since <since> (RFC 3339), read through a pipe and
#                                       never written: the fleet account's events, counted, and its rows
#   capture.sh podlog <label> <since>   the dashboard container since <since>: discovery, fleet-*, cluster-secret-*,
#                                       shared-api-url, every line naming gitops-404 except its per-minute poll lines
#                                       and its binding findings, with counts
# Every command is a read. No password or token is printed; any `sha256~` token is redacted, and the fleet account's
# name is read from its Lease into a variable and replaced by `<fleet account>` in everything written.
set -euo pipefail
kind="${1:?kind}"; label="${2:?label}"
here="$(cd "$(dirname "$0")/.." && pwd)"   # the report folder
out="${here}/evidence/${label}-${kind}.txt"
ns=group-sync-dashboard
run_label=walk.gsd.lab/run=gitops-404-2026-09-28
lease=gsd-fleet-666f1ba7f2fdead0
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
fleet=$(oc get leases.coordination.k8s.io "${lease}" -n "${ns}" -o jsonpath='{.metadata.annotations.groupsync-dashboard\.io/account}')
[ -n "${fleet}" ] || { echo "no account on Lease ${lease}" >&2; exit 2; }
redact() { sed -E -e 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g' -e "s/${fleet}/<fleet account>/g"; }

run() {  # the command line, the instant, then its output; all three redacted
  printf '# %s\n# at %s\n' "$*" "$(now)" | redact
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
    run "oc get leases.coordination.k8s.io ${lease} -n ${ns} -o json | jq -c '{resourceVersion: .metadata.resourceVersion, holderIdentity: .spec.holderIdentity, acquireTime: .spec.acquireTime, renewTime: .spec.renewTime, annotation_keys: (.metadata.annotations | keys), ping: (.metadata.annotations | with_entries(select(.key | test(\"ping-last-\"))))}'" > "${out}"
    ;;
  sharedqa)
    run "oc get secrets gsd-cluster-shared-qa -n ${ns} -o jsonpath='resourceVersion={.metadata.resourceVersion}{\"\\n\"}'" > "${out}"
    ;;
  onboarding)
    run "oc get configmaps -n ${ns} -l 'groupsync-dashboard.io/config-type in (onboard,sideload)' -o wide; oc get configmaps -n ${ns} -l ${run_label} -o wide" > "${out}"
    ;;
  secret)
    run "oc get secrets gsd-cluster-gitops-404 -n ${ns} -o json | jq '{name: .metadata.name, uid: .metadata.uid, resourceVersion: .metadata.resourceVersion, created: .metadata.creationTimestamp, labels: .metadata.labels, annotations: .metadata.annotations, data_keys: (.data | keys)}'" > "${out}"
    ;;
  tokens)
    run "oc get oauthaccesstokens.oauth.openshift.io -o json | jq -c --arg fa '${fleet}' '[.items[] | select(.userName == \$fa) | .clientName] | group_by(.) | map({client: .[0], n: length})'" > "${out}"
    ;;
  audit)
    since="${3:?since (RFC 3339)}"
    {
      echo "# oc adm node-logs --role=master --path=oauth-server/<every audit*.log>, events at or after ${since}"
      echo "# captured $(now); the raw log is read through a pipe and never written"
      oc adm node-logs --role=master --path=oauth-server/ | awk '{print $2}' | grep -E '^audit' | while read -r f; do
        oc adm node-logs --role=master --path="oauth-server/${f}"
      done | sed 's/^[^ ]* //' | jq -r --arg since "${since}" --arg fa "${fleet}" -s '
        [ .[] | select(.requestReceivedTimestamp >= $since)
          | (.annotations // {}) as $a
          | select($a["authentication.openshift.io/username"] != null)
          | { at: .requestReceivedTimestamp[0:19], user: $a["authentication.openshift.io/username"],
              decision: $a["authentication.openshift.io/decision"], status: .responseStatus.code, uri: .requestURI } ]
        as $e
        | ($e | map(select((.user | ascii_downcase) == ($fa | ascii_downcase)))) as $fl
        | ($fl | map(select(.uri | startswith("/oauth/authorize")))) as $fa_auth
        | "annotated login events since \($since): \($e | length)",
          "fleet account, all: \($fl | length); authorize: \($fa_auth | length); of them client_id=openshift-challenging-client: \($fa_auth | map(select(.uri | test("client_id=openshift-challenging-client"))) | length)",
          "fleet account rows (instant, kind, decision, status):",
          ($fl[] | "  \(.at)Z  \(if (.uri | startswith("/oauth/authorize")) then (if (.uri | test("client_id=openshift-challenging-client")) then "challenging-client authorize" else "authorize" end) elif (.uri | startswith("/login")) then "credential" else "other" end)  \(.decision)  \(.status)")'
    } > "${out}"
    ;;
  clusterrows)
    run "oc exec -n ${ns} deploy/group-sync-dashboard -c dashboard -- python3.14 -c 'import sqlite3; c = sqlite3.connect(\"file:/data/gsd.db?mode=ro\", uri=True); [print(*r, sep=\"  \") for r in c.execute(\"SELECT id, enabled, source, credential FROM cluster ORDER BY source LIKE \\\"secret:%\\\", 1\")]'" > "${out}"
    ;;
  podlog)
    since="${3:?since (RFC 3339)}"
    pod=$(oc get pods -n "${ns}" -l app.kubernetes.io/name=group-sync-dashboard -o jsonpath='{.items[0].metadata.name}')
    raw=$(mktemp); trap 'rm -f "${raw}"' EXIT
    oc logs -n "${ns}" "${pod}" -c dashboard --timestamps --since-time="${since}" > "${raw}"
    c() { grep -c -E -e "$1" "${raw}" || true; }
    {
      echo "# oc logs -n ${ns} ${pod} -c dashboard --timestamps --since-time=${since}  (captured $(now))"
      echo "# lines in the window: $(wc -l < "${raw}" | tr -d ' ')"
      echo "# discovery, fleet-*, cluster-secret-*, and every line naming gitops-404 except its per-minute poll lines:"
      grep -E ' (discovery|fleet-[a-z-]*|cluster-secret-[a-z]*|shared-api-url) |gitops-404' "${raw}" \
        | grep -v -E 'polled gitops-404:|gitops-404 poll cycle took|UNMANAGED GRANT DISCOVERED' | redact || true
      echo "# per-minute poll lines for gitops-404 ('polled gitops-404:'): $(c 'polled gitops-404:')"
      echo "# 'UNMANAGED GRANT DISCOVERED — gitops-404' lines (the first poll's binding findings, not listed): $(c 'UNMANAGED GRANT DISCOVERED — gitops-404')"
      for e in fleet-login fleet-logout fleet-lookup fleet-lookup-failed fleet-ping fleet-ping-failed cluster-secret-created cluster-secret-deleted; do
        echo "# ${e} lines: $(c " ${e} ")"
      done
      echo "# fleet-logout ... outcome=revoked: $(grep ' fleet-logout ' "${raw}" | grep -c 'outcome=revoked' || true)"
      echo "# cluster-secret-created ... cluster=gitops-404 ... by=sa-token-lookup: $(grep ' cluster-secret-created ' "${raw}" | grep ' cluster=gitops-404 ' | grep -c 'by=sa-token-lookup' || true)"
      echo "# 'cluster gitops-404: polling started': $(c 'cluster gitops-404: polling started')"
      echo "# discovery ... removed=gitops-404: $(c 'removed=gitops-404')"
      echo "# ERROR or Traceback lines: $(c 'ERROR|Traceback')"
    } > "${out}"
    ;;
  *) echo "unknown kind ${kind}" >&2; exit 2 ;;
esac
echo "wrote ${out}"
