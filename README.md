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
| Group referenced by a RoleBinding but absent | nothing — the binding looks healthy and grants nobody |
| Group synced but empty | nothing — a blank USERS column |
| CR not honouring its schedule | nothing until you diff timestamps by hand |
| A group silently stopped being refreshed | nothing — the CR still reports success |

## The constraint

**The API keeps no sync history.** A GroupSync CR carries one timestamp
(`.status.lastSyncSuccessTime`) and each Group carries one of its own
(`group-sync-operator.redhat-cop.io/sync-time`). So a timeline cannot be fetched — it is
*accumulated* by polling and storing an observation each time a timestamp changes (§2).

Two consequences worth knowing before reading a screen:

* An empty timeline means *this dashboard* has not seen a sync yet. It does not mean the
  operator never synced.
* `ReconcileError` is **sticky**. The operator never clears it on a later success, so a CR
  in perfect health carries both `ReconcileSuccess` and `ReconcileError` at `status: True`
  indefinitely. The dashboard calls an error current only when its `lastTransitionTime` is
  newer than the success's — reading the condition's status alone would paint a healthy CR
  permanently red (§2.1).

## Run it locally

```bash
python3 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"

# CA bundle from your kubeconfig — preferred over insecureSkipVerify, even for dev
kubectl config view --raw --minify \
  -o jsonpath='{.clusters[0].cluster.certificate-authority-data}' | base64 -d > crc-ca.crt

cp clusters.example.yaml clusters.yaml
export GSD_TOKEN_CRC=$(oc whoami -t)
./.venv/bin/uvicorn gsd.api:create_app --factory --port 8099
```

Then open <http://127.0.0.1:8099>.

## Tests

```bash
./.venv/bin/python -m pytest tests/ -q                    # unit + Playwright UI
./.venv/bin/playwright install chromium                   # once, for the UI tests

# optional: smoke against a real cluster
GSD_TOKEN_CRC=$(oc whoami -t) GSD_LIVE_CONFIG=clusters.yaml \
  ./.venv/bin/python -m pytest tests/test_live_smoke.py -q
```

The UI tests run against a *seeded* store, not a live cluster: the states worth testing
hardest — an overdue CR, a rejected token, a current reconcile error — are exactly the ones
a healthy cluster never shows, and live counts change while the test runs.

## Configuration

See `clusters.example.yaml`. No token appears in it — only the name of the env var or the
path of the mounted Secret holding one. The API never returns a token and the browser never
holds a cluster credential (§9, §11).

`GSD_DB_PATH` overrides `dbPath`, so the config can ship as a ConfigMap that does not need
to know where the writable volume is mounted.

## RBAC per observed cluster

```bash
oc create sa group-sync-dashboard -n group-sync-operator
oc create clusterrole group-sync-reader \
  --verb=get,list --resource=groupsyncs.redhatcop.redhat.io,groups.user.openshift.io
oc adm policy add-cluster-role-to-user group-sync-reader \
  -z group-sync-dashboard -n group-sync-operator
oc create token group-sync-dashboard -n group-sync-operator --duration=8760h
```

No `watch`, no write verbs anywhere (§4, §6). Token lifetime is an open question — see §13.

> Verify per cluster rather than assuming: on CRC the Kyverno **admission** controller could
> not read `groups.user.openshift.io` while the **background** controller could. Being able
> to read core resources does not imply being able to read Groups.

## Container

```bash
podman build -t group-sync-dashboard:0.2.3 -f Containerfile .
```

Runs as a non-root UID with a group-writable `/data`, so it works both standalone and under
OpenShift's arbitrary-UID SCC. One worker on purpose: the poller runs in-process and owns
the SQLite file, so a second worker would mean two pollers racing on it.

## API

All read-only (§11).

```text
GET /api/clusters                                     id, reachable, last_poll, error, counts
GET /api/clusters/{id}/groupsyncs                     schedule, filter, last_sync, next_expected, state
GET /api/clusters/{id}/groupsyncs/{name}/events       the accumulated sync timeline
GET /api/clusters/{id}/groups?state=all|empty|unattributed
GET /api/clusters/{id}/groups/{name}                  members, owner, and membership changes
GET /api/clusters/{id}/users                          every user, with a group count
GET /api/clusters/{id}/users/{name}                   reverse lookup: every group a user is in
GET /api/clusters/{id}/membership-changes             who joined or left, cluster-wide
GET /api/alerts                                       computed, across all clusters
GET /healthz  /readyz
```

`state` is computed, never stored:

```text
ok        age <= 1 interval + grace
late      age >  1 interval + grace
overdue   age >  2 intervals + grace     -> alert
unknown   unreachable, no sync seen yet, or an unparseable schedule
```

`grace` (default 120s) exists because the literal thresholds flap. A sync lands 3–14s after
its cron minute and we observe it up to a poll interval later, so a healthy CR's observed
age exceeds one interval for ~70s at the end of *every* cycle. Without grace the state
blinks `late` once per cycle and operators learn to ignore it.

`next_expected` uses a real cron parser. `0 * * * *` and `*/30 * * * *` both look hourly if
you only measure gaps between events — they differ only at `:30`.

## Membership

Group detail shows the members themselves, not just a count: a count answers "is this group
empty?", only the names answer "why does this person have access?".

Membership is accumulated the same way sync events are, because the API keeps no history:

* **Member since** is when *this dashboard* first observed the user in the group — not when
  LDAP added them. It cannot predate the dashboard.
* **Membership changes** record joins and departures. A user quietly dropping out of a group
  is the invisible absence this exists for: nothing logs it, no event fires, and the group
  looks perfectly healthy afterwards.
* Each change carries the group's `sync-time` at the moment it was seen, which distinguishes
  *"the operator did this"* from *"someone edited the object"*. A change stamped with a stale
  sync-time did not come from a sync.
* **Reverse lookup** (`/users/{name}`) answers the RBAC question the cluster can only answer
  by scanning every Group object by hand.

## Deployment model

**One instance per cluster**, each observing itself via the pod's projected ServiceAccount
token (§13.1). That token is rotated by kubelet and re-read on every poll, so there is no
long-lived credential to mint or expire.

Multi-cluster is still supported — add entries to the config. Be aware it reopens the
authorization gap in `docs/PLAN_oauth_proxy.md`: OAuth authenticates against the hosting
cluster only, so one instance holding several clusters' data can show a user membership from
a cluster they have no rights on.

## Not in this slice

Binding health (dangling RoleBinding subjects), log-scrape enrichment, and the group-count
cliff alert — the last needs a floor as well as a ratio, since a CR owning three groups
loses 33% by losing one (§8, §14).
