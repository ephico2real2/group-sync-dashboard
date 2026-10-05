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
- **Do not use `group-sync-dashboard` or `group-sync-operator-helm`.** These values are reserved for two charts' own
  RBAC: this chart's (`templates/_helpers.tpl`, `gsd.rbacLabels`) and the group-sync-operator chart's (its
  `group-sync-operator-helm.rbacLabels`, from chart 0.14.1). Each chart sets its own name on every RBAC object it
  renders, with no values key for it. They silence those charts' bindings, but neither is ever taken as
  evidence that a policy system is in use (#354, #503). An umbrella chart that installs either under a
  dependency `alias` renders the alias instead, which counts as a policy system's value.
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
| User | the user is a platform user: by default the name starts with `system:`, or is `kube-apiserver`, `kubelet`, `kube-controller-manager`, `kube-scheduler`, `kube-proxy`, `kubeadmin` or `kube:admin` | the shipped defaults, plus your `platformUsers.additionalPrefixes` and `additionalNames` in `values.yaml` (or a ConfigMap, `platformUsers.existingConfigMap`); the same list the direct-user view uses |

To silence the ServiceAccounts of a whole namespace (an operator's namespace, say), add it to `platformNamespaces` in
`values.yaml` instead of labelling each binding:

```yaml
platformNamespaces:
  additionalSuffixes: ["-operator", "-manager", "-provisioner"]
  additionalNames: ["kyverno", "group-sync-dashboard"]
```

To silence a user who is the estate's own (a bind account, a break-glass login), add the name to
`platformUsers.additionalNames` in the release's values file and roll it out through the release's deployment
pipeline. OpenShift's break-glass login is shipped under both of its names: `kubeadmin`, and `kube:admin`, the
user it signs in as outside CRC.

Nothing else silences a grant. A Helm, OLM or Argo CD label, the binding's name, or a ServiceAccount's name
(`default` included) does not. A hand-made `admin` grant to the `default` ServiceAccount in a project namespace is
reported.

## Not a way to silence a grant

- **`rbac.ocp.io/unmanaged=true`** is set by a person or CI (the dashboard never writes it) to acknowledge that the log
  has announced a finding, so the WARNING is not repeated. The grant is still reported everywhere else.
- **Group grants:** a hand-made grant to an operator-synced group is reported only once the cluster shows that a
  policy system is in use. That means some other group binding carries a `config-source` value other than
  `group-sync-dashboard` and `group-sync-operator-helm`, the two charts' own (#503). ServiceAccount and User grants
  have no such condition.

## When it takes effect

At the next binding refresh: `bindingIntervalSeconds`, 3600 seconds (one hour) by default. A labelled or annotated binding then
moves out of **Unmanaged**, and a grant it gives a user directly moves out of the Namespace audit worklist and the
direct-user alert into the acknowledged count (#503). On the Access granted page it is counted as granted. A platform identity is counted as
**Built-in**. A change to `platformNamespaces` or `platformUsers` in the values file restarts the pod, whose first
refresh applies it; a list kept in a ConfigMap is read at start, so after editing it change its
`existingConfigMap.revision` in the values file and roll the release out.

## The direct-user view follows the same rule

A grant that names a user directly is also listed on the **Namespace audit** tab, as one to migrate to a group,
and raises the direct-user alert. The label and the annotation above acknowledge it there too (#503). It
leaves the worklist, its counts, the namespace index's counts and the alert at the next binding refresh. It is
counted as acknowledged beside the platform identities, and listed under the worklist with its label value or
its exception text. A user's own acknowledged grants stay on their own view, because they are still access that
user holds. A platform user stays a platform user, whatever its binding carries.

## Where the rule is written

- The design: `docs/unmanaged-audit-design.md` and `docs/specs/SPEC_U1_unmanaged_subjects.md`, both from the
  repository root.
- Every line of code that decides or reads "platform" carries the marker `PLATFORM-CLASSIFICATION (#255, #353)`, so
  `git grep "PLATFORM-CLASSIFICATION"` lists the whole rule.
