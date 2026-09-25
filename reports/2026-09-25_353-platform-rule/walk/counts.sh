#!/bin/bash
# counts.sh <label>: the finding counts on the lab through the pod's loopback API, after a deploy.
# Writes ${W}/counts-<label>.txt. Read-only.
set -uo pipefail
source "$(dirname "$0")/lib.sh"
label="${1:?usage: counts.sh <label>}"
out="${W}/counts-${label}.txt"
{
  echo "# counts (${label}) — $(date -u +%Y-%m-%dT%H:%M:%SZ) — pod $(pod)"
  echo "## Argo: $(argo)"
  echo "## image: $(oc get pods -n "$NS" -l app.kubernetes.io/name=group-sync-dashboard --field-selector=status.phase=Running -o jsonpath='{.items[0].spec.containers[?(@.name=="dashboard")].image}')"
  echo "## /api/version"; api_as kubeadmin /api/version; echo
  echo "## schema"; schema
  echo "## /api/clusters/dashboard/bindings/findings — counts"
  api_as kubeadmin "/api/clusters/dashboard/bindings/findings?limit=1" | python3 -c 'import json,sys
d = json.load(sys.stdin); print("   total", d["total"], "| counts", d["counts"])'
  echo "## unmanaged rows, by kind, by namespace, distinct bindings  (finding=unmanaged&limit=5000)"
  api_as kubeadmin "/api/clusters/dashboard/bindings/findings?finding=unmanaged&limit=5000" | python3 -c 'import json,sys
from collections import Counter
d = json.load(sys.stdin); rows = d["unmanaged"]
print("   rows", len(rows), "| truncated", d["truncated"], "| bindings", len({(r["binding_kind"], r["binding_namespace"], r["binding_name"]) for r in rows}))
print("   by kind", dict(Counter(r["subject_kind"] for r in rows)))
print("   ServiceAccount rows by the account namespace:")
for ns, n in Counter(r["subject_namespace"] for r in rows if r["subject_kind"] == "ServiceAccount").most_common(): print(f"     {n:4d}  {ns}")
print("   User rows:", sorted(Counter(r["group_name"] for r in rows if r["subject_kind"] == "User").items()))
print("   Group rows:", sorted(Counter(r["group_name"] for r in rows if r["subject_kind"] == "Group").items()))'
  echo "## built_in rows by kind  (finding=built_in&limit=5000)"
  api_as kubeadmin "/api/clusters/dashboard/bindings/findings?finding=built_in&limit=5000" | python3 -c 'import json,sys
from collections import Counter
d = json.load(sys.stdin); rows = d["built_in"]
print("   rows", len(rows), "| by kind", dict(Counter(r["subject_kind"] for r in rows)), "| is_platform=1", sum(1 for r in rows if r.get("is_platform")))'
  echo "## /api/clusters (dashboard)"
  api_as kubeadmin /api/clusters | python3 -c 'import json,sys
for c in json.load(sys.stdin):
    if c["id"] == "dashboard": print("   ", {k: c.get(k) for k in ("id", "bindings", "ok_bindings", "dangling_bindings", "unresolved_bindings", "unmanaged_bindings", "builtin_bindings")})'
  echo "## /metrics gsd_bindings_total{cluster=\"dashboard\"}"
  oc exec -n "$NS" "$(pod)" -c dashboard -- curl -s http://127.0.0.1:8080/metrics | grep 'gsd_bindings_total{cluster="dashboard"'
  echo "## the poller's last binding refresh lines (dashboard)"
  oc logs -n "$NS" "$(pod)" -c dashboard --since=30m | grep -E "binding refresh|unmanaged|UNMANAGED|WARNING" | grep -v "shared-\|mock-" | tail -8 | cut -c1-220
} | tee "${out}"
