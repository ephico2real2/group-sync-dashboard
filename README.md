# GroupSync dashboard

Read-only, multi-cluster observability for the
[redhat-cop group-sync-operator](https://github.com/redhat-cop/group-sync-operator).
It observes; it never creates or edits a GroupSync CR.

Design doc: `docs/PLAN_group_sync_dashboard.md` in the
[chart repo](https://github.com/ephico2real2/group-sync-operator-helm-chart). Section
references below (§2, §11, …) point at it.

## Why

Everything this surfaces is an *absence*, and absences are what a human scanning
`oc get` output does not notice — none of these raise an event or a failed reconcile:

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

## Prerequisites

| Need | For | Notes |
|---|---|---|
| `podman` | building the image | Docker works too — the file is named `Containerfile`, which podman finds automatically and `docker build -f Containerfile` accepts |
| `oc` (or `kubectl`) | deploying | logged in to the target cluster |
| Python 3.11+ | developing or running locally | 3.11 is the floor; the image ships 3.11 |
| A container registry | shipping the image | Quay, ECR, Harbor, anything |
| Cluster admin, once | creating the ClusterRole in `deploy/dashboard.yaml` | the dashboard is read-only and needs no admin at runtime |

Nothing else. The image is self-contained: SQLite is a library inside the process, not a
service, so there is no database to run and one container is the whole deployment.

## Build and ship

**External registry — the real path.** Builds this Containerfile offline and pushes to any
registry your clusters can pull from. No dependency on a cluster's internal registry.

```bash
cp .env.example .env && chmod 600 .env && $EDITOR .env   # once
./build-and-push-external.sh                       # build + push
./build-and-push-external.sh --build-only          # no push, no credentials needed
./build-and-push-external.sh --deploy              # + roll out to K8S_NAMESPACE
./build-and-push-external.sh --create-pull-secret  # private repositories only
```

Everything is parameterised in `.env` — registry host, namespace, image name, credentials,
target namespace, pull secret. `.env.example` documents each; `.env` is gitignored.

Images are tagged `<version>-<git-sha>`, so the tag moves whenever the source does. A dirty
tree is refused unless you pass `--allow-dirty`, which tags `-dirty` rather than claiming a
commit the image does not match. The commit is stamped into the image, served at
`/api/version`, shown in the dashboard header, and read back out of the running pod after
deploy — because "the image was built before the fix and deployed after it" is a real thing
that happened here, and nothing revealed it.

**Local CRC development** lives in [`local-development/`](local-development/README.md).
The API is documented in [`local-development/API.md`](local-development/API.md); the running
instance also serves `/docs`, `/redoc` and `/openapi.json`, generated from the code.

### Credentials

`.env` is **parsed, not sourced**. Sourcing executes the file, which makes a `<change-me>`
placeholder a shell redirect and lets any command substitution inside it run. Login uses
`--password-stdin`, never `-p`, so the secret stays out of `ps` and shell history.

Use a registry **robot account** rather than a personal password — it can be revoked on its
own. If a token is ever pasted where it should not be, regenerate it; exposure is not undone
by deleting the message.

### Image pull secrets

Optional, and omitted from the deployment entirely unless `IMAGE_PULL_SECRET` is set. A
public repository needs none, and an empty secret reference makes a pod fail to schedule
rather than falling back to anonymous pull. For a private repository, set the name and run
with `--create-pull-secret`.

## Deploy

```bash
oc apply -f deploy/dashboard.yaml
```

One instance **per cluster**, each observing itself through the pod's projected
ServiceAccount token (§13.1). kubelet rotates that token and it is re-read on every poll, so
there is no long-lived credential to mint or expire. Multi-cluster still works — add entries
to the ConfigMap — but see the authorization caveat in `docs/PLAN_oauth_proxy.md`.

RBAC is read-only: `get`/`list` on groupsyncs, groups, rolebindings, clusterrolebindings. No
`watch`, no write verbs, and deliberately not `roles`/`clusterroles`, since role rules are
never evaluated.

> Verify per cluster rather than assuming: on CRC the Kyverno **admission** controller could
> not read `groups.user.openshift.io` while the **background** controller could. Being able
> to read core resources does not imply being able to read Groups.

## Monitoring

`/metrics` serves Prometheus exposition; `deploy/dashboard.yaml` ships a ServiceMonitor and
four alerting rules. Enabling OpenShift user-workload monitoring is a separate, deliberate
step — it is off by default and costs a Prometheus + Thanos Ruler pair. The one-liner is in
the manifest.

Cardinality is bounded on purpose: series are emitted per cluster and per GroupSync CR only,
never per group or per user. That is a scale concern — 500 groups must not mean 500 series —
and a disclosure one, since `/metrics` is unauthenticated so a ServiceMonitor can reach it.

`gsd_groupsync_last_sync_timestamp_seconds` is a unix timestamp rather than a precomputed age
or boolean, so the threshold lives in the alert where it can be seen and tuned:

```promql
(time() - gsd_groupsync_last_sync_timestamp_seconds) > 7200
```

## Develop

```bash
python3 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
./.venv/bin/playwright install chromium        # once, for the UI tests
./.venv/bin/python -m pytest tests/ -q
```

Running against a real cluster: [`local-development/README.md`](local-development/README.md).

UI tests run against a *seeded* store rather than a live cluster. The states worth testing
hardest — an overdue CR, a rejected token, a current reconcile error — are exactly the ones a
healthy cluster never shows, and live counts change while the test runs.

## What it shows

**Overview** — per cluster: reachable, CR count, group count, empty and unattributed groups,
bindings needing review, oldest last sync.

**GroupSync detail** — schedule, LDAP filter, last sync, next expected (from a real cron
parser), the accumulated sync timeline, and the groups the CR owns.

**Groups** — every group, filterable to `empty` and `unattributed`. Drill in for members,
when each was first seen, the membership change log, and the access the group grants.

**Users** — the reverse lookup: every group a user belongs to and every binding that reaches
them, each row naming the group that confers it. The cluster can only answer this by scanning
every Group object by hand.

**Access granted** — every group-subject binding, classified: `granted`, `dangling` (the
group was operator-managed and has disappeared), `unresolved` (names a group that has never
existed), `built_in` (Kubernetes virtual groups, expected and not a fault).

Direct bindings only. Role rules are never fetched or expanded, and the UI says so — an
incomplete effective-permission calculation could show access as absent when it is not, and a
false negative there gets an incident closed wrongly.

## Two things to know before reading a screen

**The API keeps no history.** A CR carries one timestamp and each Group carries one of its
own, so timelines and membership changes are *accumulated* by polling (§2). An empty timeline
means this dashboard has not seen a sync yet — not that the operator never synced.

**`ReconcileError` is sticky.** The operator never clears it on a later success, so a healthy
CR carries both `ReconcileSuccess` and `ReconcileError` at `status: True` indefinitely. An
error counts as current only when its `lastTransitionTime` is newer than the success's;
reading the condition's status alone would paint a healthy CR permanently red (§2.1).

## Not built yet

Effective-permission expansion, log-scrape enrichment, the group-count cliff alert (needs a
floor as well as a ratio), and authentication in front of the Route — see
`docs/PLAN_oauth_proxy.md`, researched and deliberately parked.
