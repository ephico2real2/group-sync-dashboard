# #354's premise on the lab: which bindings carry rbac.ocp.io/config-source, and how many name a Group
# (the only subject kind the unmanaged gate reads on this release), by label value.
source /private/tmp/claude-501/-Users-olasumbo-gitRepos-group-sync-dashboard/77d32da9-736f-4cfc-b61c-10c627692308/scratchpad/ob1/walk312/lib.sh
echo "# config-source on the lab — $(date -u +%Y-%m-%dT%H:%M:%SZ)"
oc get clusterrolebindings,rolebindings -A -o json | python3 -c 'import json,sys,collections
K = "rbac.ocp.io/config-source"
lab = [i for i in json.load(sys.stdin)["items"] if K in (i["metadata"].get("labels") or {})]
grp = lambda i: any(s.get("kind") == "Group" for s in i.get("subjects") or [])
print("   labelled bindings", len(lab), "| with a Group subject", sum(map(grp, lab)))
for v, n in sorted(collections.Counter(i["metadata"]["labels"][K] for i in lab).items(), key=lambda x: (-x[1], x[0])):
    print("  ", v, "bindings", n, "| with a Group subject", sum(1 for i in lab if grp(i) and i["metadata"]["labels"][K] == v))'
