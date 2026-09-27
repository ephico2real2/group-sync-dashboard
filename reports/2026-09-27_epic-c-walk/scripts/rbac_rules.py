"""Expand every Role/ClusterRole rule of a rendered chart into one line per (kind, namespace, role, apiGroup,
resource, verb, resourceName) and diff two renders: REMOVED is what the second render no longer grants.

Usage: python rbac_rules.py <before.yaml> <after.yaml>   (the output of `helm template`)."""
import sys

import yaml


def rules(path: str) -> set[tuple]:
    out = set()
    for doc in yaml.safe_load_all(open(path)):
        if not doc or doc.get("kind") not in ("Role", "ClusterRole"):
            continue
        meta = doc["metadata"]
        for rule in doc.get("rules") or []:
            for group in rule.get("apiGroups") or [""]:
                for resource in rule.get("resources") or []:
                    for verb in rule.get("verbs") or []:
                        for name in rule.get("resourceNames") or ["*"]:
                            out.add((doc["kind"], meta.get("namespace", "-"), meta["name"], group, resource, verb, name))
    return out


before, after = rules(sys.argv[1]), rules(sys.argv[2])
print(f"rules: before {len(before)}, after {len(after)}")
print(f"REMOVED {len(before - after)}")
for r in sorted(before - after):
    print("  - " + " ".join(r))
print(f"ADDED {len(after - before)}")
for r in sorted(after - before):
    print("  + " + " ".join(r))
