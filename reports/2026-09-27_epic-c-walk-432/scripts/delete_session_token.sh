#!/usr/bin/env bash
# SPEC_S4c §3.12 step 5: delete the self-login session's own OAuthAccessToken, as cluster-admin — exactly ONE object,
# never a pre-existing session (#286's record: a "user + client" filter once deleted four `developer` tokens).
# The session is the one the pod logged last: `fleet-login cluster=walk-self-login … expires_at=<E>`. The object is
# the `developer` openshift-challenging-client token whose creationTimestamp + expiresIn is within 3 s of <E> and
# which was created after <walk start>. Refuses unless exactly one object matches. The object's name is used, never
# printed.
# Usage: delete_session_token.sh <walk start, RFC 3339>
set -euo pipefail
start="${1:?walk start (RFC 3339)}"
ns=group-sync-dashboard
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
pod=$(oc get pods -n "${ns}" -l app.kubernetes.io/name=group-sync-dashboard -o jsonpath='{.items[0].metadata.name}')
line=$(oc logs -n "${ns}" "${pod}" -c dashboard --timestamps | grep -E ' fleet-login cluster=walk-self-login ' | tail -1 || true)
expires=$(printf '%s' "${line}" | sed -nE 's/.* expires_at=([0-9TZ:-]+).*/\1/p')
[ -n "${expires}" ] || { echo "no fleet-login line for walk-self-login in ${pod}'s log; nothing deleted" >&2; exit 1; }
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) the session: $(printf '%s' "${line}" | cut -c1-31) fleet-login cluster=walk-self-login expires_at=${expires}"
matches=$(oc get oauthaccesstokens.oauth.openshift.io -o json | jq -r --arg e "${expires}" --arg start "${start}" '
  ($e | fromdateiso8601) as $exp
  | [.items[] | select(.userName == "developer" and .clientName == "openshift-challenging-client"
                        and .metadata.creationTimestamp >= $start)
     | select(((.metadata.creationTimestamp | fromdateiso8601) + .expiresIn - $exp) | fabs <= 3)]
  | map("\(.metadata.name) \(.metadata.creationTimestamp) \(.expiresIn)") | .[]')
count=$(printf '%s' "${matches}" | grep -c . || true)
echo "matching objects: ${count} (developer, openshift-challenging-client, created since ${start}, creation + expiresIn within 3 s of ${expires})"
[ "${count}" = 1 ] || { echo "refused: exactly one object must match; nothing deleted" >&2; exit 1; }
name=$(printf '%s' "${matches}" | cut -d' ' -f1)
echo "deleting the one match, created $(printf '%s' "${matches}" | cut -d' ' -f2), expiresIn $(printf '%s' "${matches}" | cut -d' ' -f3): sha256~<redacted>"
oc delete oauthaccesstokens.oauth.openshift.io "${name}" | sed -E 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g'
