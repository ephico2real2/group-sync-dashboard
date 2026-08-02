# GroupSync dashboard

Read-only observability for the
[redhat-cop group-sync-operator](https://github.com/redhat-cop/group-sync-operator).
It observes; it never creates or edits a GroupSync CR.

Everything this surfaces is an *absence* — and absences are what a human scanning `oc get`
output does not notice. None of these raise an event or a failed reconcile:

| Failure | How it presents without this |
|---|---|
| A RoleBinding names a Group that does not exist | nothing — the binding looks healthy and grants nobody |
| Group synced but empty | nothing — a blank USERS column |
| CR not honouring its schedule | nothing until you diff timestamps by hand |
| A group silently stopped being refreshed | nothing — the CR still reports success |
| A user quietly dropped out of a group | nothing — no event, no log |

On the reference cluster it finds **9 RoleBindings granting `admin`, `view` and `edit` to
groups that have never existed** — access reaching nobody, in three namespaces, which
`oc get rolebinding` reports as perfectly healthy.

## Layout

The application, its build tooling and its manifests all live in
**[`local-development/`](local-development/)**. This directory is deliberately kept clear
for the Helm chart, which will be generated from
[`local-development/deploy/dashboard.yaml`](local-development/deploy/dashboard.yaml).

| Where | What |
|---|---|
| [`local-development/README.md`](local-development/README.md) | prerequisites, build, ship, deploy, and running against CRC |
| [`local-development/API.md`](local-development/API.md) | every endpoint, what each field means, and the ones routinely misread |
| `local-development/gsd/` | the application |
| `local-development/deploy/dashboard.yaml` | Deployment, RBAC, Service, Route, ServiceMonitor, PrometheusRule — the source for the chart |
| `local-development/build-and-push-external.sh` | build offline and push to an external registry |
| `local-development/release-crc.sh` | CRC-only convenience release |

## Quick start

```bash
cd local-development
cp .env.example .env && chmod 600 .env && $EDITOR .env   # registry credentials
./build-and-push-external.sh --deploy                    # build, push, roll out
oc apply -f deploy/dashboard.yaml                        # or deploy by hand
```

Full detail, including prerequisites and the credential handling, is in
[`local-development/README.md`](local-development/README.md).

## Current deployment

The image ships to an external registry so any cluster can pull it, with no dependency on a
cluster's internal registry:

```text
quay.io/ephico2real/group-sync-dashboard:<version>-<git-sha>
```

Public pull, so no image pull secret is required. Tags carry the git commit, the commit is
stamped into the image, and the running pod reports it at `/api/version` — so "is my change
deployed?" is answerable by looking, not by inspecting an image.
