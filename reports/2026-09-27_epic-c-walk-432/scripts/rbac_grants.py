"""Effective grants, per subject, of a rendered chart: every (Cluster)RoleBinding expanded through the rules of the
(Cluster)Role it names, one atom per (subject, scope, apiGroup, resource, verb, resourceName). A binding whose role
is not in the input (a ClusterRole the cluster already has) is one atom naming that role. REMOVED is what the
second set no longer grants; the operator's rule is REMOVED 0 for the dashboard's ServiceAccount.

Usage: python rbac_grants.py <before.yaml> <after.yaml> [<extra manifest applied beside the after render>...]
The inputs are `helm template` output (and, for extras, plain manifests). The release namespace is
group-sync-dashboard, the default for a namespaced object that names none."""
import sys

import yaml

RELEASE_NS = "group-sync-dashboard"


def load(paths: list[str]) -> list[dict]:
    docs = []
    for path in paths:
        with open(path) as fh:
            docs += [d for d in yaml.safe_load_all(fh) if isinstance(d, dict)]
    return docs


def grants(docs: list[dict]) -> set[tuple]:
    roles = {}
    for d in docs:
        if d.get("kind") in ("Role", "ClusterRole"):
            ns = d["metadata"].get("namespace", RELEASE_NS) if d["kind"] == "Role" else ""
            roles[(d["kind"], ns, d["metadata"]["name"])] = d.get("rules") or []
    out = set()
    for d in docs:
        if d.get("kind") not in ("RoleBinding", "ClusterRoleBinding"):
            continue
        ns = d["metadata"].get("namespace", RELEASE_NS) if d["kind"] == "RoleBinding" else ""
        ref = d["roleRef"]
        rules = roles.get((ref["kind"], ns if ref["kind"] == "Role" else "", ref["name"]))
        scope = ns or "(cluster)"
        for s in d.get("subjects") or []:
            subject = f"{s['kind']}:{s.get('namespace', '')}:{s['name']}"
            if rules is None:
                out.add((subject, scope, f"roleRef {ref['kind']}/{ref['name']}", "", "", ""))
                continue
            for rule in rules:
                for group in rule.get("apiGroups") or [""]:
                    for resource in rule.get("resources") or rule.get("nonResourceURLs") or []:
                        for verb in rule.get("verbs") or []:
                            for name in rule.get("resourceNames") or ["*"]:
                                out.add((subject, scope, group, resource, verb, name))
    return out


before = grants(load([sys.argv[1]]))
after = grants(load(sys.argv[2:]))
print(f"inputs: before {sys.argv[1]}; after {' + '.join(sys.argv[2:])}")
print(f"grants: before {len(before)}, after {len(after)}")
for label, atoms in (("REMOVED", before - after), ("ADDED", after - before)):
    print(f"{label} {len(atoms)}")
    for atom in sorted(atoms):
        print(("  - " if label == "REMOVED" else "  + ") + " | ".join(a for a in atom if a))
sa = f"ServiceAccount:{RELEASE_NS}:group-sync-dashboard"
print(f"REMOVED for {sa}: {len([a for a in before - after if a[0] == sa])}")
