# The pod's own log, for the times the README quotes: every binding refresh of the three CRC entries and every
# line that names the planted grant, since the pod started. Read once, after the walk, while the pod still lives.
source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/ob1/walk312/lib.sh
echo "# pod log excerpt — $(date -u +%Y-%m-%dT%H:%M:%SZ) — pod $(pod) — TZ=$(oc exec -n "$NS" "$(pod)" -c dashboard -- sh -c 'echo $TZ')"
oc logs -n "$NS" "$(pod)" -c dashboard | grep -E "refreshed [0-9]+ group bindings for (dashboard|shared-qa|shared-rnd)|evidence-347" | cut -c1-170
