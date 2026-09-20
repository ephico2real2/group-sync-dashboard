# OpenShift GitOps (Argo CD) files

Argo CD runs in `openshift-gitops`; the Application objects live there and deploy into the
dashboard's namespace. Apply in this order.

| file | what it is |
|---|---|
| `argocd-rbac-kubeadmin.yaml` | a patch for the `openshift-gitops` ArgoCD CR: OpenShift GitOps' default policy grants `role:admin` to the *groups* `system:cluster-admins` / `cluster-admins`, but Dex's OpenShift connector puts only `system:authenticated` in a token's `groups` (kubeadmin's cluster-admin membership is a virtual group Dex never sees — measured on CRC 2026-09-19: `PermissionDenied` on every list, an empty UI). This matches the `name` claim too and grants `kubeadmin` admin. On a cluster where a `cluster-admins` Group object exists this is not needed |
| `argocd-repo-github.yaml` | the repository connection: a Secret in `openshift-gitops` with the label `argocd.argoproj.io/secret-type: repository` and the repo `url` — that label is what registers it (Argo's declarative setup). This repository is public; a private one adds `username`/`password` or `sshPrivateKey` |
| `argocd-application-grafana.yaml` | the `openshift-grafana` chart from this git repository (`charts/openshift-grafana` on `main`), release `grafana`, destination `group-sync-dashboard`, automated sync |

```sh
oc patch argocd openshift-gitops -n openshift-gitops --type merge --patch-file gitops/argocd-rbac-kubeadmin.yaml
oc apply -f gitops/argocd-repo-github.yaml
oc apply -f gitops/argocd-application-grafana.yaml
oc -n openshift-gitops get application grafana -w
```

Log out of the Argo UI and back in after the RBAC patch: the role is evaluated per session.

Measured on CRC 2026-09-19 (first sync from a namespace where `helm uninstall` had left the operator's
CSV behind): the secrets hook kept the minted Secrets, the reclaim deleted the orphan, the approver
approved `install-w9z52`, the CSV reached Succeeded. Argo's built-in Subscription health check read
`ResolutionFailed` in the same wave, before the reclaim had acted, and failed the first attempt; the
Application's `retry` converged on the next — which is why the Application carries one.
