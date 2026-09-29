#!/usr/bin/env bash
# #481's walk: read-only captures, each written to evidence/<label>-<kind>.txt with its command and instant.
# Never prints the fleet account's name (the Lease's `account` annotation is dropped; any match is replaced).
set -euo pipefail
label="${1:?label}"; here="$(cd "$(dirname "$0")/.." && pwd)"; ns=group-sync-dashboard
: "${KUBECONFIG:?KUBECONFIG must name the lab kubeconfig}"
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
lsel=groupsync-dashboard.io/lease-type=fleet-account
fleet=$(oc get leases.coordination.k8s.io -n $ns -l $lsel -o json | jq -r '[.items[].metadata.annotations["groupsync-dashboard.io/account"] // empty] | .[0] // "<none>"')
redact() { if [ "$fleet" = "<none>" ]; then cat; else sed -E -e "s/${fleet}/<fleet account>/g" -e 's/sha256~[A-Za-z0-9_-]+/sha256~<redacted>/g'; fi; }
out() { echo "$here/evidence/${label}-$1.txt"; }
{ printf '# /api/version via the pod loopback\n# at %s\n' "$(now)"
  oc exec -n $ns deploy/group-sync-dashboard -c dashboard -- python3.14 -c 'import urllib.request; print(urllib.request.urlopen("http://127.0.0.1:8080/api/version").read().decode())'
  printf '# pods\n'; oc get pods -n $ns -o 'custom-columns=N:.metadata.name,START:.status.startTime,RESTARTS:.status.containerStatuses[0].restartCount' --no-headers | grep '^group-sync-dashboard-'
} > "$(out version)" 2>&1
{ printf '# PVCs and shared-qa\n# at %s\n' "$(now)"
  oc get persistentvolumeclaims.v1. -n $ns -o 'custom-columns=N:.metadata.name,UID:.metadata.uid' --no-headers
  echo "shared-qa resourceVersion=$(oc get secrets.v1. gsd-cluster-shared-qa -n $ns -o jsonpath='{.metadata.resourceVersion}')"
} > "$(out state)" 2>&1
{ printf '# the fleet Lease (the account annotation dropped)\n# at %s\n' "$(now)"
  oc get leases.coordination.k8s.io -n $ns -l $lsel -o json | jq '[.items[] | {name: .metadata.name, uid: .metadata.uid, resourceVersion: .metadata.resourceVersion, created: .metadata.creationTimestamp, holderIdentity: .spec.holderIdentity, annotations: (.metadata.annotations | with_entries(select(.key|test("account$")|not)))}]'
  printf '# every Lease in the cluster: count, and the oldest creationTimestamp\n'
  oc get leases.coordination.k8s.io -A -o json | jq -r '"count=\(.items|length) oldest=\([.items[].metadata.creationTimestamp]|min)"'
} > "$(out lease)" 2>&1
{ printf '# /data/fleet-gate.json on the dashboard pod, compared with the Lease annotations\n# at %s\n' "$(now)"
  lease=$(oc get leases.coordination.k8s.io -n $ns -l $lsel -o json | jq -c '[.items[] | {(.metadata.name): (.metadata.annotations | with_entries(select(.key|test("account$")|not)))}] | add // {}')
  oc exec -n $ns deploy/group-sync-dashboard -c dashboard -- python3.14 -c "import json,os,sys; p='/data/fleet-gate.json'; e=os.path.exists(p); print('exists', e); f=json.load(open(p)) if e else {}; print('mode', oct(os.stat(p).st_mode & 0o777) if e else '-'); print(json.dumps(f, sort_keys=True, indent=1)); l=json.loads(sys.argv[1]); print('equal_to_lease', {k: f.get(k) == v for k, v in l.items()})" "$lease"
} 2>&1 | redact > "$(out file)"
