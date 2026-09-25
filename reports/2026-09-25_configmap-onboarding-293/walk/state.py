"""Read-only state for #293's proof: the cluster Secrets and /api/clusterconfigs, as JSON on stdout."""
import json, subprocess, sys
NS = "group-sync-dashboard"
def sh(*a): return subprocess.run(a, capture_output=True, text=True).stdout
secrets = json.loads(sh("oc", "get", "secret", "-n", NS, "-l", "groupsync-dashboard.io/secret-type=cluster", "-o", "json") or '{"items":[]}')["items"]
gen = {s["metadata"]["name"]: (s["metadata"].get("annotations") or {}).get("groupsync-dashboard.io/managed-by") for s in secrets}
pod = sh("oc", "get", "pods", "-n", NS, "-l", "app.kubernetes.io/name=group-sync-dashboard", "--field-selector=status.phase=Running", "-o", "name").split()[0]
raw = sh("oc", "exec", "-n", NS, pod, "-c", "dashboard", "--", "curl", "-s", "-H", "X-Forwarded-User: kubeadmin", "http://127.0.0.1:8080/api/clusterconfigs")
d = json.loads(raw)
rows = d.get("clusters", []) if isinstance(d, dict) else d
out = {
    "secrets": {k: v for k, v in gen.items() if "cm-demo" in k},
    "clusters": {r["id"]: {"status": r.get("status"), "source": r.get("source"), "retired": r.get("retired"),
                            "onboarding_configmap": r.get("onboarding_configmap")} for r in rows if "cm-demo" in r["id"]},
    "findings": [{k: f.get(k) for k in ("secret", "code", "detail")} for f in (d.get("findings") or []) if "cm-demo" in json.dumps(f) or "cluster-onboarding" in json.dumps(f)],
}
json.dump(out, sys.stdout, indent=1)
