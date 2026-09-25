# Silencing an unmanaged grant — which labels, and what is silenced without one

The dashboard reports an **unmanaged grant**: a RoleBinding or ClusterRoleBinding made outside the policy system. It
covers bindings to groups, ServiceAccounts and users (#353). You see these grants in several places:
- the **RBAC policy** tab;
- the **Unmanaged** section of **Access granted**;
- the pod log, as `UNMANAGED GRANT DISCOVERED` at WARNING;
- `GET /api/clusters/<id>/bindings/findings?finding=unmanaged`;
- the `/metrics` count with `finding="unmanaged"`.

A legitimate grant is silenced by a decision recorded **on the binding**, and by nothing else. This page lists the two
ways to record that decision, and the grants the platform rule silences without one.

## 1. The label `rbac.ocp.io/config-source` — a grant your policy system or your team owns

```bash
oc label rolebinding <name> -n <namespace> rbac.ocp.io/config-source=platform-team
oc label clusterrolebinding <name> rbac.ocp.io/config-source=platform-team
```

- **Where it goes:** on the RoleBinding or ClusterRoleBinding. It covers every subject that binding names, whatever
  its kind.
- **Its value:** any value silences the binding. Use one that names who decided: the policy configuration or the
  team.
- **Do not use `group-sync-dashboard`.** That value is reserved for this chart's own RBAC, which carries it by default
  (`templates/_helpers.tpl`, `gsd.rbacLabels`). It silences the chart's bindings, but it is never taken as evidence
  that a policy system is in use (#354).
- **Your policy configurations already use it.** They put `config-source=<the configuration's name>` on the bindings
  they render; on the lab these are `baseline-nonprod-rbac`, `baseline-cluster-rbac` and others. Those bindings are
  already silenced.

## 2. The annotation `rbac.ocp.io/unmanaged-exception` — a one-off grant a person reviewed and accepted

```bash
oc annotate rolebinding <name> -n <namespace> \
  rbac.ocp.io/unmanaged-exception="approved by <who> on <date>: <why>"
```

The justification lives on the object it justifies, where the next reviewer finds it. Use it for a deliberate
exception, and the label for a grant that belongs to a managed set.

## 3. Silenced without any metadata — the platform rule

These are never reported; they appear under **Built-in** instead.

| Subject | Silenced when | Where it is decided |
|---|---|---|
| ServiceAccount | its namespace is a platform namespace (the ServiceAccount's own namespace, or the RoleBinding's when the subject names none) | the shipped defaults, prefixes `openshift-` and `kube-` and the names `default`, `openshift`, `kube-system`, `kube-public`, `kube-node-lease`; plus your `platformNamespaces.additionalPrefixes`, `additionalSuffixes` and `additionalNames` in `values.yaml` |
| ServiceAccount | the binding is one of OpenShift's per-project controller bindings, all three parts matching, in the binding's own namespace: `system:image-builders` → `system:image-builder` → `builder`; `system:deployers` → `system:deployer` → `deployer` | shipped defaults, in every namespace |
| Group | the group's name starts with `system:`. That covers `system:image-pullers` → Group `system:serviceaccounts:<namespace>`, the third controller binding | the Group rule |
| User | the name starts with `system:`, or is `kube-apiserver`, `kubelet`, `kube-controller-manager`, `kube-scheduler`, `kube-proxy` or `kubeadmin` | the same rule the direct-user view uses |

To silence the ServiceAccounts of a whole namespace (an operator's namespace, say), add it to `platformNamespaces` in
`values.yaml` instead of labelling each binding:

```yaml
platformNamespaces:
  additionalSuffixes: ["-operator", "-manager", "-provisioner"]
  additionalNames: ["kyverno", "group-sync-dashboard"]
```

Nothing else silences a grant. A Helm, OLM or Argo CD label, the binding's name, or a ServiceAccount's name
(`default` included) does not. A hand-made `admin` grant to the `default` ServiceAccount in a project namespace is
reported.

## Not a way to silence a grant

- **`rbac.ocp.io/unmanaged=true`** marks a finding the log has already announced, so it is not announced again. The
  grant is still reported everywhere else.
- **Group grants:** a hand-made grant to an operator-synced group is reported only once the cluster shows that a
  policy system is in use. That means some other group binding carries a `config-source` value other than
  `group-sync-dashboard`. ServiceAccount and User grants have no such condition.

## When it takes effect

At the next binding refresh: `bindingIntervalSeconds`, 300 seconds by default. A labelled or annotated binding then
moves out of **Unmanaged**. On the Access granted page it is counted as granted. A platform identity is counted as
**Built-in**.

## Where the rule is written

- The design: `docs/unmanaged-audit-design.md` and `docs/specs/SPEC_U1_unmanaged_subjects.md`, both from the
  repository root.
- Every line of code that decides or reads "platform" carries the marker `PLATFORM-CLASSIFICATION (#255, #353)`, so
  `git grep "PLATFORM-CLASSIFICATION"` lists the whole rule.
