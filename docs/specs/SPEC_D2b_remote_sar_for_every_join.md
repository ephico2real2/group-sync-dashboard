# SPEC D2b — `remote-sar` for every way a cluster is joined

| | |
|---|---|
| Extends | `docs/specs/SPEC_D2_per_cluster_authorization.md` (per-cluster authorization, released in 0.19.0) |
| Design | `docs/DESIGN_remote_cluster_access.md` — D1, D2, D3 and D6, directed by the operator on 2026-09-23 |
| Issue | [#338](https://github.com/ephico2real2/group-sync-dashboard/issues/338) |
| Source | written by the orchestrator on 2026-09-23 from a read-only map of main `b21f80b` and measurements on the lab — not a design agent's output; reviewed before any code is written |
| Version on release | the next minor of the application and of the chart when the pull request opens (CI refuses a `charts/` change without a `Chart.yaml` bump; the version is not pinned here, so another release landing first does not make this spec wrong) |
| Status | specified — for review before any code is written |

## 1. The mandate, and what is out of scope

The operator, 2026-09-23: *"this is what I want: remote-sar for whatever method the cluster was joined."* A remote
cluster's own RBAC decides who sees its data wide, whether the cluster was declared in values with a token, as a
Secret created on the Cluster Configurations tab or by hand, or through `saTokenLookup`. A remote that states no
policy takes `remote-sar` + `same-as-host` (D2), and readers are matched by OpenShift username (D3, no code).

Out of scope, each decided or tracked elsewhere: D4's named finding and D5's per-outcome sentence (recommended, not
directed); `clusterAdminSar` (#322, D7); Rejoin and its remote check (#316, D8); whether `inherit` stays allowed on a
remote (not decided); a per-cluster label on the tier-check metric.

## 2. What the code does today (measured 2026-09-23 on main `b21f80b`)

1. **Resolvers are built once, before discovery.** `build_app` creates one `TierResolver` per `remote-sar` entry of
   `settings.clusters` — the values list — before the lifespan starts the poller's first discovery
   (`local-development/gsd/api.py#remote_resolvers`). A cluster that arrives through a Secret never gets one, and
   `viewer_scope` answers a cluster with no resolver as self: fail closed.
2. **A resolver keeps the config it was built with.** `TierResolver` holds a `ClusterClient` on that
   `ClusterConfig`; a Secret's token and CA are fields of the frozen config, declared `compare=False`
   (`local-development/gsd/config.py#ClusterConfig`), so neither equality nor an existing resolver sees a rotation.
3. **Three refusals.** The Secret parser refuses `remote-sar` (`local-development/gsd/clusterconfig/parser.py`,
   "remote-sar for a Secret-sourced cluster is S2"), which also refuses it on the tab (`writer.validate` parses the
   Secret it would write) and in the lookup's write; the chart refuses it beside `saTokenLookup`
   (`charts/group-sync-dashboard/templates/_helpers.tpl`, "not yet accepted from a Secret (SPEC_S1)").
4. **The default is `self-only` / `none`**, set in `Settings.cluster_policy`, the poller's `_cluster_shape` and its
   `cluster-resolved` line, `CreateRequest`, the API's `_create_request`, and the page's add-cluster form. The lookup
   writes the resolved pair into the Secret explicitly (`local-development/gsd/fleetlookup.py#store`).
5. **A lookup-written Secret shadows its stanza's policy.** Once written, the Secret replaces the values entry in
   `ClusterRegistry.merge`, and `writer.store_lookup` keeps the Secret's `visibility` on a re-lookup — so a later edit
   of the stanza's `visibility:`, or a change of default, never reaches the served policy.
6. **A failing remote is asked again on every request.** `TIER_CHECK_TIMEOUT_SECONDS` is 5 s, failures are not
   cached, and `/api/whoami` walks every served cluster in turn.
7. **The review's error text is not redacted.** `ClusterClient.create_subject_access_review` puts `response.text`
   and the connect error into the `ClusterError` that `_resolve_and_cache` logs, without `_redact`; the group list,
   which goes through `_get`, is redacted.
8. **The auditor's grant exists only where the dashboard runs.** `rbacAuditors` renders the Group → read-only role
   binding with this chart (`charts/group-sync-dashboard/templates/rbac-auditors.yaml`); measured on the lab,
   `group-sync-dashboard-ra-b78c05817c9d` carries `helm.sh/chart: group-sync-dashboard-0.52.1`. A synced auditor
   Group on a remote has membership there but no binding.

## 3. Design

### 3.1 Resolvers follow the cluster's current configuration (D1)

A resolver is found, or built, **on the request**, from the cluster's current merged configuration, and kept while
that configuration's connection is unchanged. No discovery hook: it works on every replica, in an app with no poller
(tests), and for a cluster that appears, rotates or leaves at runtime.

`local-development/gsd/kube.py`, after `class TierResolver`:

```python
class RemoteTierResolvers:
    """One TierResolver per remote-sar cluster, from that cluster's CURRENT configuration (SPEC_D2b §3.1).

    Looked up per request rather than built once at start-up: a cluster declared through a Secret appears at
    runtime, and a rotated token or CA reaches it only as a new ClusterConfig whose credential fields are
    compare=False — so the connection fingerprint, not equality, decides when a resolver is rebuilt (and its
    per-viewer cache with it). A cluster that is gone, disabled, still pending its credential, the host, or no
    longer remote-sar gets None, which viewer_scope answers as self: fail closed. Thread-safe; a build is cheap
    (no network) and happens under the lock, so two requests cannot race two resolvers into the map.
    """

    def __init__(self, settings: "Settings", make: Callable[[ClusterConfig], TierResolver]):
        self._settings = settings
        self._make = make
        self._lock = threading.Lock()
        self._built: dict[str, tuple[str, TierResolver]] = {}

    def get(self, cluster_id: str) -> TierResolver | None:
        settings = self._settings
        cluster = settings.cluster(cluster_id)
        host = settings.host_cluster()
        if (cluster is None or not cluster.enabled or cluster.credential_pending is not None
                or (host is not None and cluster.name == host.name)
                or settings.cluster_policy(cluster_id)[0] != VISIBILITY_REMOTE_SAR):
            with self._lock:
                self._built.pop(cluster_id, None)
            return None
        key = cluster.connection_fingerprint()
        with self._lock:
            held = self._built.get(cluster_id)
            if held is not None and held[0] == key:
                return held[1]
            resolver = self._make(cluster)
            self._built[cluster_id] = (key, resolver)
            return resolver
```

`build_app` replaces the start-up loop with the object; `app.state.remote_tier_resolvers` keeps its name and its
`.get(cluster_id)` shape, so `viewer_scope` does not change and the tests that install a dict there keep working:

```python
    remote_resolvers = RemoteTierResolvers(settings, lambda c: TierResolver(
        c,
        verb=settings.visibility_admin_sar_verb,
        resource=settings.visibility_admin_sar_resource,
        api_group=settings.visibility_admin_sar_api_group,
        namespace=settings.visibility_admin_sar_namespace,
        subresource=settings.visibility_admin_sar_subresource,
        ttl_seconds=float(settings.visibility_tier_ttl_seconds),
        observe=functools.partial(signals.note_tier_check, "admin"),
        failure_hold_seconds=REMOTE_FAILURE_HOLD_SECONDS,
    )) if settings.view_restrictions_enabled else {}
```

`local-development/gsd/config.py`, a method of `ClusterConfig` (adds `import hashlib` and `import json`):

```python
    def connection_fingerprint(self) -> str:
        """A digest of everything a ClusterClient connects with. Equality cannot see a rotated Secret credential
        (those fields are compare=False by design), so a resolver keyed on this is rebuilt when — and only when —
        the connection changes. A tokenFile's CONTENT is re-read per request and needs no rebuild; its path is here."""
        material = json.dumps([self.api_url, self.credential_kind, self.token_value or "", self.token_file or "",
                               self.token_env or "", self.oauth_username or "", self.oauth_password or "",
                               self.ca_data or "", self.ca_bundle_file or "", bool(self.insecure_skip_verify)])
        return hashlib.sha256(material.encode()).hexdigest()
```

**Budget, per replica and per `remote-sar` cluster** (multiply by the replica count for a release): while the remote
answers, at most one group list and one review **per viewer per `tierTtlSeconds`** (60 s by default); while it
fails, at most **one attempt per `REMOTE_FAILURE_HOLD_SECONDS`** (§3.5) whatever the number of viewers; a new URL,
credential or trust is used from the first request after discovery publishes it, with no restart; a retired,
disabled or pending cluster is never asked. A resolver is never built for the host.

### 3.2 The default is `remote-sar` + `same-as-host` (D2)

One rule, in one function, read by every place that resolved the old default (`cluster_policy`, the poller's
`_cluster_shape` and its `cluster-resolved` line):

`local-development/gsd/config.py`:

```python
def remote_policy(visibility: str | None, identity: str | None) -> tuple[str, str]:
    """A non-host cluster's (visibility, identity) with the defaults resolved (SPEC_D2b §3.2, design D2).

    A remote that states nothing is asked about the reader itself: remote-sar + same-as-host. `identity: none`
    says the host's username is nobody on that cluster, so it cannot be asked about them: with no visibility
    stated it keeps self-only, as before. remote-sar with an explicit `none` is refused where it is read."""
    if visibility is None:
        visibility = VISIBILITY_SELF_ONLY if identity == IDENTITY_NONE else VISIBILITY_REMOTE_SAR
    if identity is None:
        identity = IDENTITY_SAME_AS_HOST if visibility == VISIBILITY_REMOTE_SAR else IDENTITY_NONE
    return visibility, identity
```

and `Settings.cluster_policy`'s last line becomes `return remote_policy(cluster.visibility, cluster.identity)`.

| `visibility` stated | `identity` stated | Resolved | Before |
|---|---|---|---|
| — | — | `remote-sar`, `same-as-host` | `self-only`, `none` |
| — | `none` | `self-only`, `none` | the same |
| — | `same-as-host` | `remote-sar`, `same-as-host` | `self-only`, `same-as-host` |
| `remote-sar` | — | `remote-sar`, `same-as-host` | refused |
| `remote-sar` | `none` | **refused** (values, chart, Secret) | refused |
| `inherit` / `self-only` / `hidden` | — | that, `none` | the same |

The loader's pairing rule refuses only the explicit pair: `cluster.visibility == VISIBILITY_REMOTE_SAR and
cluster.identity == IDENTITY_NONE`, with the message *"visibility remote-sar needs identity: same-as-host — the
review names the reader's OpenShift username on this cluster; set same-as-host or leave identity out"*. The host's
refusals are unchanged.

### 3.3 Secrets and the tab accept `remote-sar` (D1)

`local-development/gsd/clusterconfig/parser.py` — the visibility check accepts every value of
`CLUSTER_VISIBILITIES`, and the pairing becomes a refusal with an existing code (the code set is a page contract):

```python
    visibility = (data.get("visibility") or "").strip() or None
    if visibility is not None and visibility not in CLUSTER_VISIBILITIES:
        return finding("visibility-invalid", f"data.visibility must be one of {', '.join(CLUSTER_VISIBILITIES)}")
    identity = (data.get("identity") or "").strip() or None
    if identity is not None and identity not in CLUSTER_IDENTITIES:
        return finding("identity-invalid", f"data.identity must be one of {', '.join(CLUSTER_IDENTITIES)}")
    if visibility == VISIBILITY_REMOTE_SAR and identity == IDENTITY_NONE:
        return finding("identity-invalid", "data.identity none cannot pair with visibility remote-sar: the review "
                                           "names the reader's OpenShift username on this cluster; set same-as-host "
                                           "or leave identity out")
```

The fix sentences in `local-development/gsd/clusterconfig/reader.py` become *"visibility must be inherit, self-only,
hidden or remote-sar"* and *"identity must be none or same-as-host, and remote-sar needs same-as-host"*. The tab
needs no writer change beyond its defaults: `writer.validate` parses the Secret it would write. `CreateRequest` and
`_create_request` default to `remote-sar` / `same-as-host`; the page's form offers `remote-sar`, defaults to the pair,
and gives `remote-sar` a hint (*"this cluster's own RBAC decides, for the reader's OpenShift username"*).

### 3.4 A lookup-written Secret takes its stanza's policy

The stanza is the configuration item (SPEC_S3): the Secret the lookup writes carries the credential, the stanza the
policy. `local-development/gsd/clusterconfig/registry.py`, `ClusterRegistry.merge`:

```python
        for c in values:
            found = discovered.pop(c.name, None)
            if found is None:
                out.append(c)
            elif c.connection_mode is not None:
                # The stanza declares how it is joined; the Secret written for it holds the credential only. Its
                # policy is the stanza's, so an edit of the stanza's visibility — or a change of default — reaches
                # the served policy, which the Secret's frozen copy never did (SPEC_D2b §3.4).
                out.append(dataclasses.replace(found, visibility=c.visibility, identity=c.identity))
            else:
                out.append(found)
```

On the lab this is what moves `shared-rnd` (a stanza with no policy, a Secret written with `self-only`) to the new
default without deleting the Secret.

### 3.5 A failing remote is held, not retried on every request

`TierResolver` gains `failure_hold_seconds: float = 0.0`. Zero — the host's resolvers — keeps today's behaviour
exactly. Above zero, a failed resolution (a `ClusterError`, or any other exception on that path) makes the resolver
answer self **without a call** until the hold expires; a cached allowed/denied answer still serves until its own
expiry. The failure is logged and counted once per attempt, so the alert still fires on a remote that keeps failing.

```python
REMOTE_FAILURE_HOLD_SECONDS = 30.0   # a failing remote is asked at most once per this, whatever the traffic
```

In `__init__`, beside `self._ttl`:

```python
        self._hold = failure_hold_seconds
        self._held_until = 0.0
```

In `tier_for`, inside the first `with self._lock:` block, after the per-viewer cache check and before
single-flighting:

```python
            if self._hold and now < self._held_until:
                return TIER_SELF
```

and in both failure branches of `_resolve_and_cache`, beside `self._note(...)`:

```python
            if self._hold:
                with self._lock:
                    self._held_until = time.monotonic() + self._hold
```

### 3.6 The review's error text is redacted

`ClusterClient.create_subject_access_review` passes both messages through `self._redact(...)`, as `_get` does: the
connect error and `HTTP {status} on {SAR_API}: {response.text[:200]}`.

### 3.7 The auditor's grant on each remote — a prerequisite outside this repository

Under `remote-sar` an auditor is wide on a remote only if that remote binds the auditor Group to a role granting the
wide-tier question (`visibility.adminSar`, default `list clusterrolebindings`). This chart renders that binding only
where the dashboard runs (§2.8). The objects a remote needs are this chart's two: a ClusterRole with the rules of
`group-sync-dashboard-report-auditor`, and one ClusterRoleBinding per auditor Group. The natural owner is the chart
that already installs the poller ServiceAccount and its roles on each remote (the operator's
`group-sync-operator-helm`, another repository). This spec documents the objects in `docs/ACCESS_CONTROL.md` §11; who
installs them is the operator's decision, recorded under "Orchestrator's notes" when made.

### 3.8 Wording the reviews routed here

- "clusters share an identity provider" (D3): `local-development/gsd/config.py` (the `identity` comment and the
  loader's message), `charts/group-sync-dashboard/templates/_helpers.tpl`, `charts/group-sync-dashboard/values.yaml`,
  `charts/group-sync-dashboard/example-production.yaml`, `charts/group-sync-dashboard/README.md`, and the page's
  `same-as-host` hint — each says the reader is matched by OpenShift username, the `User` object's name.
- "the first enabled entry" for the host: `values.yaml`, the chart README and `environments/crc.yaml` say "the
  hosting entry" (`dashboardController: true`, else the first enabled one), as `docs/ACCESS_CONTROL.md` §11 now does.

### 3.9 Chart

`_helpers.tpl`: the `saTokenLookup` refusal is deleted; the pairing refusal fires only for an explicit
`identity: none` with `remote-sar`. The ConfigMap still injects no default (a test pins it). `NOTES.txt` prints each
remote's resolved pair with the §3.2 rule and marks defaulted values `(default)`.

## 4. Tests

- **Flip:** the parser, writer and chart tests that pin the `remote-sar` refusal now pin acceptance; the chart test
  for `saTokenLookup` + `remote-sar` renders.
- **The pairing:** the loader, chart and stanza-matrix tests that pinned "remote-sar without same-as-host is refused"
  pin "remote-sar with identity none is refused" and "remote-sar with no identity resolves same-as-host".
- **Defaults:** every test that pinned `self-only` / `none` for an unstated remote pins the §3.2 table; one test
  walks all six rows through `load_settings`, the parser and the chart's NOTES.
- **Fixtures that would start asking real remotes** (`test_ui.py` `scoped_server`, `test_home_api.py` `_app`,
  `test_dashboard_controller.py` `TestBuildApp…`): they test self-only behaviour, so they state
  `visibility: self-only` explicitly.
- **New:** `RemoteTierResolvers` builds for a Secret-discovered cluster, returns the same resolver while nothing
  changes, rebuilds on a rotated token, a new CA and a new URL, and returns None — and forgets the entry — for a
  retired, disabled, pending, host or non-`remote-sar` cluster; the hold makes N requests inside it one remote
  attempt, retries after it, and leaves a hold-0 resolver retrying on every request; `merge` gives a mode stanza's
  policy to its Secret and replaces a plain entry wholesale; a token planted in a review's error body never reaches
  the WARNING; the tab writes the new defaults and offers `remote-sar`.

## 5. Verification on the lab

Built and deployed with `release-crc.sh --argocd`, then walked:

- `cluster-resolved` shows `shared-rnd` and `shared-qa` as `visibility=remote-sar identity=same-as-host`.
- `/api/whoami` as kubeadmin: `visibility.clusters` gives `all` for both remotes; as a non-admin persona, `self`;
  as `jane.smith` (auditor), `all` on `shared-rnd` (the binding exists there: it is the same cluster).
- A remote whose joining ServiceAccount lacks `create subjectaccessreviews` (a scratch SA): every reader self, one
  WARNING per 30 s under load, `outcome=forbidden` on the metric.
- Rotating `shared-qa`'s token on the tab: the next request after discovery reviews with the new token.
- The e2e walk captures the selector and a per-cluster tab for each persona.

## 6. Risks

- **The default flip turns the critical alert on** for any remote whose joining ServiceAccount lacks the two grants.
  The CHANGELOG's upgrade note says so and names the fix, or `visibility: self-only` to keep the old behaviour; the
  pod log names the cluster (the metric does not).
- **Secrets that state `self-only` keep it.** Tab-created Secrets always carry the form's pair; a lookup-managed one
  follows its stanza (§3.4). The upgrade note says how to move a tab-created cluster.
- **Caches are per replica** — the budget in §3.1 is per replica, stated as such.

## Orchestrator's notes

(none yet)
