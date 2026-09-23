# Polling, cluster discovery, and forcing a refresh

How the dashboard decides *when* to read a cluster, how a cluster enters the fleet in the first
place, and what can and cannot be made to happen sooner. Companion to
`reference-architecture.md`'s §3, which covers what a poll *does*; this covers what makes one
happen, and when.

Every number below is either a chart default, quoted from the code, or a measurement taken on the
reference cluster on 2026-09-23 with the command shown.

## 1. Two cadences, one thread per cluster

`gsd/poller.py#Poller._run_cluster` runs one thread per enabled cluster — separate threads rather
than one sequential loop, because a cluster that black-holes TCP would otherwise hold every other
cluster's data hostage for the length of the timeout.

| what | cadence | default |
|---|---|---|
| Groups and GroupSync CRs | `pollIntervalSeconds` | **60s** |
| RoleBindings, operator-config health, **and cluster discovery** | `bindingIntervalSeconds` | **300s** |

Bindings are deliberately slower: they are listed across every namespace — roughly 154 paged
requests at 100× the reference cluster's scale — and they change on administrative action rather
than on a schedule, so minute-level freshness buys nothing
(`charts/group-sync-dashboard/values.yaml#bindingIntervalSeconds`).

Polling is gated on leadership (`gsd/leader.py#LeaderElector`). A pod that does not hold the Lease
stands by and re-checks in 5s rather than one poll interval, so a failover costs seconds.

## 2. How a cluster enters the fleet

Two sources, and the difference decides how fast a change takes effect.

**A values stanza** (`clusters:` in the values file) is read at startup. Changing one means a Helm
upgrade and a restart.

**A labelled Secret** is discovered at runtime: any Secret in the release namespace carrying
`groupsync-dashboard.io/secret-type: cluster` is parsed by `gsd/clusterconfig/reader.py#discover`
and becomes a cluster. This is the path the Cluster Configurations tab writes, and the path GitOps
writes.

Discovery itself runs in `gsd/poller.py#Poller._discover_once`, on the binding cadence. It logs only
on **transitions** — a cluster added, removed, changed, or a finding appearing or clearing — so a
steady fleet is silent and a standing bad Secret does not flood the log every cycle.

## 3. The part that surprises people: how soon a Secret takes effect

The discovery loop does not sleep. It **waits on an event**, so the wait can be cut short:

```python
self._discover_now.wait(self.settings.binding_interval_seconds)
```

`gsd/poller.py#Poller.request_discovery` sets that event, and its docstring states the rule exactly:

> Wake the discovery thread now: a Secret the tab just wrote is discovered within seconds instead of
> on the next cadence tick. **A GitOps-written Secret still rides the cadence.**

It is already called by all three write endpoints in `gsd/api.py` — `POST /api/clusterconfigs`,
`PUT /api/clusterconfigs/{name}/credential` and `DELETE /api/clusterconfigs/{name}`.

So there are two speeds, and which one you get depends on **how the Secret was written, not on what
it says**:

| how the Secret was written | when it takes effect |
|---|---|
| through the API (the tab, or a direct call) | **seconds** — the write wakes discovery |
| by `oc`, `kubectl`, Argo CD, or any GitOps flow | **up to one binding interval** (300s default) |

### Measured

Onboarding a cluster by writing the Secret with `oc create secret` — i.e. the GitOps path:

```
00:08:50   Secret created with `oc create secret`
00:17:20   first poll                              <- 8m30s
```

and rotating its credential with `oc patch`:

```
01:22:38   Secret patched with a new token
01:26:20   discovery noticed: `discovery cycle=81 ... changed=shared-qa`   <- 3m42s
```

Both are the documented behaviour, not a defect: neither command goes through the API, so neither
woke the discovery thread. Both exceed one binding interval because the observed latency is the
remainder of the current wait, plus discovery, plus starting the cluster's poll thread, plus its
first poll.

**The practical consequence.** If you onboard a cluster with a short-lived credential written
outside the API, the credential can be most of the way through its life before the first poll. A
10-minute ServiceAccount token — the shortest the TokenRequest API will issue — had **84 seconds**
of useful life left by the time it was first used.

## 4. What has no mechanism at all

Discovery is not a poll. Even for a cluster already in the fleet, there is **no way to force a fresh
read** — no endpoint, no signal, nothing. `request_discovery` wakes the *discovery thread*
fleet-wide; it does not make any particular cluster poll.

That is the gap behind the "I just fixed it — did it work?" case: after rotating a credential
outside the API, the only thing to do is wait for the cadence.

A per-cluster refresh endpoint is proposed in **issue #311** —
`POST /api/clusters/{name}/refresh` — and a control in the UI that calls it. **Neither exists
today.** When it is built, the constraint that governs it is not performance but safety.

**Which modes bind, precisely.** `userSelfLogin` does **not** bind today — it sits in
`gsd/config.py#CREDENTIAL_PENDING_REASONS` ("the self-login mode is S3b's #285, not built"), and a
kind in that table is never handed to `ClusterClient`. The mode that binds today is
**`saTokenLookup`**, whose fleet login puts the password on the wire; `userSelfLogin` joins it when
#285 lands.

So a refresh on a `saTokenLookup` cluster *is a bind*, and it must honour
`gsd/fleetlookup.py#CredentialGate` — returning a gated credential's standing refusal **without
binding**. An on-demand re-bind that ignores the gate is the most convenient way to lock out the
account the whole estate authenticates with.

## 5. What a poll does when the credential has expired

Measured twice on the reference cluster, with a ServiceAccount token deliberately allowed to lapse:

```
WARNING gsd.poller cluster-unreachable phase=poll outcome=auth_failed cluster=shared-qa
  source=secret:gsd-cluster-shared-qa tls=trusted-bundle credential=bearer
  action="the token is invalid or expired: rotate it in this cluster's Secret"
  detail="401 Unauthorized — token invalid or expired"
```

Three things worth knowing about that line:

- **It names what to fix** — the source Secret, the credential kind and the TLS mode.
- **Failures are scoped.** The audit-log capture degraded on its own ("could not list nodes … group
  data is unaffected") rather than failing the whole poll.
- **It cannot tell expiry from revocation.** An expired token, a revoked token and a withdrawn grant
  are all a bare 401. "invalid or expired" is the honest limit of what a 401 supports.

### A token outlives its own `exp`

Measured directly against the API with a token allowed to lapse, probing by offset from `exp`:

```
exp -10s  ACCEPTED      exp +56s  ACCEPTED
exp  +5s  ACCEPTED      exp +62s  rejected     <- the boundary
exp +20s  ACCEPTED      exp +70s  rejected
exp +35s  ACCEPTED      exp +85s  rejected
exp +50s  ACCEPTED      exp+130s  rejected
```

**The flip is between +56s and +62s** — a one-minute JWT validation leeway (go-jose's
`DefaultLeeway`), not a cache. The poller corroborates it independently: across three runs it
accepted polls at `exp+8s`, `exp+36s` and `exp+42s`, and refused the next poll each time.

**Treat it as free slack, never as budget.** It is a server-side validation detail, not a contract.
Anything that schedules a renewal should compute it from `exp` alone.

## 6. Tuning, and what moves with what

`pollIntervalSeconds` is not independent. Three values are tied to it and must move with it, and two
of them fail loudly if they do not (`charts/group-sync-dashboard/values.yaml#pollIntervalSeconds`):

- `scheduleGraceSeconds` — or every healthy CR flaps to `late`, because a sync lands seconds after
  its cron minute and is observed up to a poll interval later;
- `monitoring.prometheusRule.notPollingSeconds` — or that alert fires forever;
- `bindingIntervalSeconds` — which must stay above it, or the expensive call becomes the frequent
  one.
