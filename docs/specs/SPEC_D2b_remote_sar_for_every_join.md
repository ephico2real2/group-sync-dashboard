# SPEC D2b — `remote-sar` for every way a cluster is joined

| | |
|---|---|
| Extends | `docs/specs/SPEC_D2_per_cluster_authorization.md` (per-cluster authorization, released in 0.19.0) |
| Design | `docs/DESIGN_remote_cluster_access.md` — D1, D2, D3 and D6, directed by the operator on 2026-09-23 |
| Release | — (post-programme; D2's step b, like E1 after the programme's R7) |
| Version on release | app and chart minor bumps at the PR |
| Version note | the next minor of the application and of the chart when the implementing pull request opens; CI refuses a `charts/` change without a `Chart.yaml` bump, and the version is not pinned here so that another release landing first does not make this spec wrong |
| Issue | [#338](https://github.com/ephico2real2/group-sync-dashboard/issues/338) |
| Status | specified |
| Source | written by the orchestrator on 2026-09-23 from a read-only map of main `b21f80b` and measurements on the lab — not a design agent's output; reviewed before any code is written (review of PR #339: Codex, Grok, OB1-lite; the decisions are under "Orchestrator's notes") |

## 1. The mandate, and what is out of scope

The operator, 2026-09-23: *"this is what I want: remote-sar for whatever method the cluster was joined."* A remote
cluster's own RBAC decides who sees its data wide, whether the cluster was declared in values with a token, as a
Secret created on the Cluster Configurations tab or by hand, or through `saTokenLookup`. A remote that states no
policy takes `remote-sar` + `same-as-host` (D2), and readers are matched by OpenShift username (D3, no code).

Out of scope, each decided or tracked elsewhere: D4's named finding and D5's per-outcome sentence (recommended, not
directed); `clusterAdminSar` (#322, D7); Rejoin and its remote check (#316, D8); whether `inherit` stays allowed on a
remote (not decided); a per-cluster label on the tier-check metric; the process-wide trusted-bundle cache (§3.1).

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
4. **The default is `self-only` / `none`**, set in `Settings.cluster_policy`, the loader's pairing rule, the poller's
   `_cluster_shape` and its `cluster-resolved` line, `CreateRequest`, the API's `_create_request`, both of the page's
   form defaults (`clusterForm` and `ccEmptyForm`), and `NOTES.txt`. The lookup writes the resolved pair into the
   Secret explicitly (`local-development/gsd/fleetlookup.py#store`).
5. **A lookup-written Secret shadows its stanza's policy.** Once written, the Secret replaces the values entry in
   `ClusterRegistry.merge`, and `writer.store_lookup` keeps the Secret's `visibility` on a re-lookup — so a later edit
   of the stanza's `visibility:`, or a change of default, never reaches the served policy.
6. **A failing remote is asked again by every viewer.** `TIER_CHECK_TIMEOUT_SECONDS` is 5 s and failures are not
   cached; a second request for the SAME viewer while one is in flight waits for it (single-flight), but every other
   viewer asks again, and `/api/whoami` walks every served cluster in turn.
7. **The review's error text is not redacted.** `ClusterClient.create_subject_access_review` puts `response.text`
   and the connect error into the `ClusterError` that `_resolve_and_cache` logs, without `_redact`; the group list,
   which goes through `_get`, redacts before truncating.
8. **This chart creates the auditor's grant only where it is installed.** With `rbacAuditors` enabled,
   `charts/group-sync-dashboard/templates/rbac-auditors.yaml` renders the read-only ClusterRole and one
   ClusterRoleBinding per auditor Group (and the Group itself where `createLocal` is set). On the lab the binding
   `group-sync-dashboard-ra-b78c05817c9d` carries `helm.sh/chart: group-sync-dashboard-0.52.1` (measured); whether a
   given remote lacks equivalent objects is deployment state, checked in §5.

## 3. Design

### 3.1 Resolvers follow the cluster's current configuration (D1)

A resolver is found, or built, **on the request**, from ONE merged `ClusterConfig` snapshot, and kept while that
snapshot's connection fingerprint is unchanged. No discovery hook: it works on every replica, in an app with no
poller (tests), and for a cluster that appears, rotates or leaves at runtime. The policy is resolved from the same
object (`remote_policy`, §3.2), never by a second read of the registry through `Settings.cluster_policy`.

`local-development/gsd/kube.py`, after `class TierResolver`:

```python
class RemoteTierResolvers:
    """One TierResolver per remote-sar cluster, from that cluster's CURRENT configuration (SPEC_D2b §3.1).

    Looked up per request rather than built once at start-up: a cluster declared through a Secret appears at
    runtime, and a rotated token or CA reaches it only as a new ClusterConfig whose credential fields are
    compare=False — so the connection fingerprint, not equality, decides when a resolver is rebuilt (and its
    per-viewer cache and failure hold with it). One snapshot per lookup: the policy is resolved from the object
    already read, so a discovery landing mid-lookup cannot pair one configuration with another's policy. A cluster
    that is gone, disabled, still pending its credential, the host, or not remote-sar + same-as-host gets None, which
    viewer_scope answers as self: fail closed. A lookup that begins after such a configuration is published makes no
    request; a request already in flight may finish. Thread-safe; a build does no I/O and happens under the lock.
    Only `.get` is offered — the one question viewer_scope asks; the map is built lazily, so its keys are not the
    set of remote-sar clusters and a membership test on it would mislead.
    """

    def __init__(self, settings: "Settings", make: Callable[[ClusterConfig], TierResolver]):
        self._settings = settings
        self._make = make
        self._lock = threading.Lock()
        self._built: dict[str, tuple[str, TierResolver]] = {}

    def get(self, cluster_id: str) -> TierResolver | None:
        cluster = self._settings.cluster(cluster_id)
        host = self._settings.host_cluster()
        policy = remote_policy(cluster.visibility, cluster.identity) if cluster is not None else None
        if (cluster is None or not cluster.enabled or cluster.credential_pending is not None
                or (host is not None and cluster.name == host.name)
                or policy != (VISIBILITY_REMOTE_SAR, IDENTITY_SAME_AS_HOST)):
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
        """A digest of everything a ClusterClient connects with that is fixed on this object. Equality cannot see a
        rotated Secret credential (those fields are compare=False by design), so a resolver keyed on this is rebuilt
        when — and only when — the connection changes. A tokenFile's content, a tokenEnv's value and an explicit
        caBundleFile are re-read by every ClusterClient._client call and need no rebuild; their names are here."""
        material = json.dumps([self.api_url, self.credential_kind, self.token_value or "", self.token_file or "",
                               self.token_env or "", self.oauth_username or "", self.oauth_password or "",
                               self.ca_data or "", self.ca_bundle_file or "", bool(self.insecure_skip_verify)])
        return hashlib.sha256(material.encode()).hexdigest()
```

**One input is outside the fingerprint's reach and out of scope:** `_trusted_ca_context` (`config.py`) caches the
process-wide trusted bundle by the `GSD_TRUSTED_CA_FILE` path, not its content, so a bundle replaced at the same path
is not seen until a restart. That is true of every poll today, not only of the review, and is tracked by its own
issue rather than widened into this change.

**Budget, per replica and per `remote-sar` cluster** (multiply by the replica count for a release): while the remote
answers, at most one group list and one review **per viewer per `tierTtlSeconds`** (60 s by default). While it fails:
the first failure costs one attempt for each distinct viewer whose request arrived while that first attempt was in
flight; from then on, at most **one attempt per `REMOTE_FAILURE_HOLD_SECONDS`** (§3.5) whatever the number of
viewers, because the request after a hold expires is the only probe and re-arms the hold before it calls. The first
success ends the hold for every viewer. A new URL, credential or explicit CA is used from the first request after
discovery publishes it, with no restart; a rebuild deliberately discards the verdict cache and the hold, so each of
`R` connection changes in a TTL costs at most one fresh attempt per viewer. A lookup beginning after a cluster is
published as retired, disabled or pending makes no request. A resolver is never built for the host.

### 3.2 The default is `remote-sar` + `same-as-host` (D2)

One pure function resolves a non-host cluster's pair; `Settings.cluster_policy`'s last line becomes
`return remote_policy(cluster.visibility, cluster.identity)`, and the poller's `_cluster_shape` uses it too.

`local-development/gsd/config.py`:

```python
def remote_policy(visibility: str | None, identity: str | None) -> tuple[str, str]:
    """A non-host cluster's (visibility, identity) with the defaults resolved (SPEC_D2b §3.2, design D2).

    A remote that states nothing is asked about the reader itself: remote-sar + same-as-host. `identity: none` says
    the host's username is nobody on that cluster, so it cannot be asked about them: with no visibility stated it
    keeps self-only, as before. Resolution only — the explicit pair remote-sar + none is refused where it is READ
    (the loader, the Secret parser, the chart), not here."""
    if visibility is None:
        visibility = VISIBILITY_SELF_ONLY if identity == IDENTITY_NONE else VISIBILITY_REMOTE_SAR
    if identity is None:
        identity = IDENTITY_SAME_AS_HOST if visibility == VISIBILITY_REMOTE_SAR else IDENTITY_NONE
    return visibility, identity
```

| `visibility` stated | `identity` stated | `remote_policy` returns | Accepted | Before |
|---|---|---|---|---|
| — | — | `remote-sar`, `same-as-host` | yes | `self-only`, `none` |
| — | `none` | `self-only`, `none` | yes | the same |
| — | `same-as-host` | `remote-sar`, `same-as-host` | yes | `self-only`, `same-as-host` |
| `remote-sar` | — | `remote-sar`, `same-as-host` | yes | refused |
| `remote-sar` | `none` | `remote-sar`, `none` | **no** — the loader, the parser and the chart refuse the explicit pair | refused |
| `inherit` / `self-only` / `hidden` | — | that, `none` | yes | the same |

The loader's pairing rule (`load_settings`) refuses only the explicit pair: `cluster.visibility ==
VISIBILITY_REMOTE_SAR and cluster.identity == IDENTITY_NONE`, with the message *"visibility remote-sar needs identity:
same-as-host — the review names the reader's OpenShift username on this cluster; set same-as-host or leave identity
out"*. The host's refusals are unchanged.

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

The parser's import from `..config` adds `IDENTITY_NONE`. The fix sentences in
`local-development/gsd/clusterconfig/reader.py` become *"visibility must be inherit, self-only, hidden or
remote-sar"* and *"identity must be none or same-as-host, and remote-sar needs same-as-host"*. The tab needs no
writer change beyond its defaults: `writer.validate` parses the Secret it would write, for create, the connection
test and the lookup's write alike. `CreateRequest` and `_create_request` default to `remote-sar` / `same-as-host`;
the page's option list offers `remote-sar`, both form defaults (`clusterForm` and `ccEmptyForm`) take the pair, and
`remote-sar` gets a hint (*"this cluster's own RBAC decides, for the reader's OpenShift username"*).

### 3.4 A lookup-owned Secret takes its stanza's policy

The stanza is the configuration item (SPEC_S3): the Secret the lookup writes for it carries the credential, the
stanza the policy. **Only that Secret.** An unowned Secret over a declared cluster keeps SPEC_S3's rule — *"the Secret
shadows the values entry and wins"*, with the `shadows-values-entry` finding, and the reconciler stands down.

Ownership is the test the reader already makes (`reader.py`: the Secret's `token-source` annotation equals the
stanza's mode). The reader records it on the parsed config — a new `ClusterConfig` field,
`token_source: str | None = field(default=None, repr=False)`, set with
`dataclasses.replace(parsed, token_source=token_source.get(secret_name))` beside the existing check — and
`ClusterRegistry.merge` uses it. The whole method, `local-development/gsd/clusterconfig/registry.py`:

```python
    def merge(self, values: list[ClusterConfig]) -> list[ClusterConfig]:
        """The values list with the discovered clusters laid over it: a Secret shadows a values entry of the same
        name (C2 — the shadow is reported by the reader as a finding); the host, values[0] enabled, is never replaced
        (the parser refuses a Secret naming it, so nothing here can). A Secret the lookup wrote FOR a mode stanza
        (its token-source is that stanza's mode — the reader's "ours") keeps the credential and takes the stanza's
        policy, so an edit of the stanza's visibility, or a change of default, reaches the served policy (SPEC_D2b
        §3.4); an unowned Secret still wins wholesale (SPEC_S3). A Secret with no values entry is appended."""
        with self._lock:
            discovered = dict(self._discovered)
        out: list[ClusterConfig] = []
        for c in values:
            found = discovered.pop(c.name, None)
            if found is None:
                out.append(c)
            elif c.connection_mode is not None and found.token_source == c.credential_kind:
                out.append(dataclasses.replace(found, visibility=c.visibility, identity=c.identity))
            else:
                out.append(found)
        out.extend(discovered.values())
        return out
```

**The `cluster-resolved` line prints the served pair**, `self.settings.cluster_policy(c.name)`, read after
`registry.replace` — never the parsed Secret's own fields, which for an owned Secret are not the ones served. In
`poller.py`, `_discover_once`:

```python
        for name in added + changed:
            c = next(x for x in clusters if x.name == name)
            mode = c.tls_mode
            # The SERVED policy, read through the merge the registry was just given: an owned Secret keeps its own
            # frozen copy, and its stanza's is the one served (SPEC_D2b §3.4).
            visibility, identity = self.settings.cluster_policy(c.name)
            event(log, logging.INFO, "cluster-resolved", cycle=cycle, cluster=c.name,
                  source=c.source, credential=c.credential_kind,
                  tls="insecure" if mode["insecure"] else mode["ca"],
                  visibility=visibility, identity=identity,
                  enabled=str(c.enabled).lower())
```

On the lab this is what moves `shared-rnd` (a stanza with no policy; its Secret written with `self-only` and
annotated `token-source: remote-lookup`, measured) to the new default without deleting the Secret.

### 3.5 A failing remote is held, not retried by every viewer

`TierResolver` gains `failure_hold_seconds: float = 0.0`. Zero — the host's resolvers, which do not pass it — keeps
today's observable behaviour: every indeterminate check is uncached and the next request asks again. Above zero, a
failed resolution holds the resolver: no call until the hold expires; the request after it expires is the single
probe and re-arms the hold BEFORE it calls; a success ends the hold for every viewer.

```python
REMOTE_FAILURE_HOLD_SECONDS = 30.0   # a failing remote is asked at most once per this, whatever the traffic
```

In `__init__`, beside `self._ttl`:

```python
        self._hold = failure_hold_seconds
        self._held_until = 0.0
```

`tier_for`'s first `with self._lock:` block becomes:

```python
        with self._lock:
            cached = self._cache.get(viewer)
            if cached is not None and cached[0] > now:
                return cached[1]
            if self._hold and self._held_until:
                if now < self._held_until:
                    return TIER_SELF
                # The hold has expired and the remote has not answered since it failed: this request is the one
                # probe. Re-armed BEFORE the call, so every other viewer who arrives while the probe is out answers
                # self without a call of its own; the probe's outcome ends the hold or restarts it.
                self._held_until = now + self._hold
            mine = self._inflight.get(viewer)
            leading = mine is None
            if leading:
                mine = self._inflight[viewer] = threading.Event()
```

A new method, called in both failure branches of `_resolve_and_cache` BEFORE `self._note(...)` — for the reason the
success path caches first: the observe callback is not bounded, and a stalled one must not leave the remote open to
every viewer:

```python
    def _start_hold(self) -> None:
        """A failed resolution holds a remote's resolver (SPEC_D2b §3.5): no call until the hold expires."""
        if self._hold:
            with self._lock:
                self._held_until = time.monotonic() + self._hold
```

and on success, inside the existing cache-write `with self._lock:` block, before the cache write:

```python
            if self._hold:
                self._held_until = 0.0      # the remote answered: the hold is over for every viewer
```

A cached allowed/denied answer still serves during a hold (the cache is checked first). Each real attempt is still
logged and counted, so `GroupSyncDashboardVisibilityChecksFailing` stays true for a remote that keeps failing under
traffic. Thirty seconds sits under the 60 s TTL and far under the alert's 15 minutes; it is a constant, like
`TIER_CHECK_TIMEOUT_SECONDS`, until an operator needs to tune it.

### 3.6 The review's error text is redacted before it is truncated

`ClusterClient.create_subject_access_review` redacts both messages as `_get` does — **before** any truncation: a
ServiceAccount JWT is longer than the 200-character window, and `redact_text` replaces only whole spellings. The
block, from `with self._client()` through the `>= 400` branch:

```python
        with self._client() as client:
            try:
                response = client.post(SAR_API, json=body)
            except httpx.HTTPError as exc:
                raise ClusterError(UNREACHABLE, self._redact(f"{type(exc).__name__}: {exc}")) from exc
        if response.status_code == 401:
            raise ClusterError(AUTH_FAILED, "401 Unauthorized creating a SubjectAccessReview")
        if response.status_code == 403:
            raise ClusterError(
                FORBIDDEN,
                f"403 Forbidden on {SAR_API} — the ServiceAccount lacks `create "
                f"subjectaccessreviews` (the system:auth-delegator grant)",
            )
        if response.status_code >= 400:
            raise ClusterError(
                UNREACHABLE, f"HTTP {response.status_code} on {SAR_API}: {self._redact(response.text)[:200]}"
            )
```

### 3.7 The auditor's grant on each remote — installed by `group-sync-operator-helm`

Under `remote-sar` an auditor is wide on a remote only if that remote binds the auditor Group to a role granting the
wide-tier question (`visibility.adminSar`, default `list clusterrolebindings`); the remote's review counts the
remote's bindings, and the reader's groups are read from the remote's Group objects. The objects a remote needs are
this chart's: a ClusterRole with the rules of `group-sync-dashboard-report-auditor`, one ClusterRoleBinding per
auditor Group, and — for an auditor Group the host creates locally (`rbacAuditors.groups[].createLocal: true`) — that
Group with its members, because a local Group exists only on the host.

**Decided by the operator (2026-09-23): `group-sync-operator-helm` installs them on every remote**, alongside the
Groups it already syncs in advance for RBAC and the poller ServiceAccount it already installs. That chart lives in
another repository; this spec records the objects and the contract, and `docs/ACCESS_CONTROL.md` §11 names them for
an operator.

### 3.8 Wording

- "clusters share an identity provider" (D3): the `identity` comment and the loader's message in
  `local-development/gsd/config.py`, the message in `charts/group-sync-dashboard/templates/_helpers.tpl`,
  `charts/group-sync-dashboard/values.yaml`, `charts/group-sync-dashboard/example-production.yaml`,
  `charts/group-sync-dashboard/README.md`, and the page's `same-as-host` hint — each says the reader is matched by
  OpenShift username, the `User` object's name.
- "the first enabled entry" for the host: `values.yaml`, the chart README and `environments/crc.yaml` say "the
  hosting entry" (`dashboardController: true`, else the first enabled one), as `docs/ACCESS_CONTROL.md` §11 now does.
- "self-only / none is the default for a remote" becomes the §3.2 rule in: `values.yaml` (the `visibility` comment's
  "THE DEFAULT FOR EVERY ENTRY BUT THE FIRST ENABLED ONE" and the `identity` comment's "THE DEFAULT for a remote"), the
  chart README's default column, `docs/ACCESS_CONTROL.md` §11's default column, the `ClusterConfig` field comment in
  `config.py`, `environments/crc.yaml`'s comments on `shared-rnd` and `mock`, and `docs/CLUSTER_STANZA.md` (the
  "remote-sar without identity: same-as-host" row becomes "remote-sar with identity: none"; the "saTokenLookup with
  visibility: remote-sar" row becomes accepted).
- `docs/ACCESS_CONTROL.md` §11's "failures are not cached" gains the hold (§3.5), and `docs/DESIGN_remote_cluster_access.md`
  §6's support table turns its two "refused" cells to "yes".

### 3.9 Chart

`_helpers.tpl`: the `saTokenLookup` refusal is deleted; the pairing refusal fires only for an explicit
`identity: none` with `remote-sar`. The ConfigMap still injects no default (a test pins it). `NOTES.txt` prints each
remote's resolved pair with the §3.2 rule and marks defaulted values `(default)`. The CHANGELOG's upgrade note names
every behaviour change in §6 and the two lines that keep the old behaviour (`visibility: self-only`, `identity: none`).

## 4. Tests

- **Parser, writer, chart:** the tests that pin the Secret and `saTokenLookup` + `remote-sar` refusals pin
  acceptance. Host `remote-sar` and explicit `remote-sar` + `identity: none` stay refused.
- **The pairing:** all six §3.2 rows, separately for `remote_policy`'s output and for acceptance by the loader, the
  parser and the chart (the stanza matrix's rows move with `docs/CLUSTER_STANZA.md`).
- **Defaults and behaviour:** every test that pinned `self-only` / `none` for an unstated remote pins the new pair,
  and the migration is tested: an unstated remote with an allowing stub serves full rows and the card's
  `operator_configs`; with a denying stub the reader's own person-scoped rows, not the old 403; Home includes the
  unstated remote without calling its resolver (`vouches_for_host_identity` is configuration-only); `/api/whoami`
  asks each unstated remote once and reports it.
- **`RemoteTierResolvers`:** a Secret-discovered cluster gets a resolver; the same one while nothing changes; a new
  one on a rotated token, a new explicit CA and a new URL; None — and the entry forgotten — for a retired, disabled,
  pending, host, `hidden` or non-`remote-sar` cluster; one configuration snapshot per lookup.
- **The hold** (`local-development/tests/test_remote_tier_hold.py`): after a hold expires, one probe goes out whatever
  the number of viewers; a success ends the hold for every viewer; a cached verdict serves during a hold; a hold-0
  resolver (the host) retries on every request, as today; a rebuild resets the cache and the hold.
- **The merge:** an owned Secret (token-source matching the stanza's mode) keeps its credential and source and takes
  the stanza's policy; an unowned or mismatched Secret wins wholesale and keeps `shadows-values-entry`; a plain values
  entry is replaced wholesale; a Secret with no values entry is appended; the `cluster-resolved` line prints the served
  pair; `fleetlookup.store` writes the same pair before and after its Secret is discovered.
- **Redaction:** a JWT echoed in a review's error body, longer than the 200-character window, never reaches the
  message; a connect error carrying the credential is redacted.
- **The controller test** (`test_dashboard_controller.py::TestBuildAppUsesTheDeclaredController::
  test_every_tier_resolver_reviews_on_the_declared_controller`) asks `.get("home") is None` instead of
  `"home" not in …`, which the object does not support.
- **Fixtures whose remotes flip to `remote-sar`** and test self-only behaviour state `visibility: self-only` and
  `identity: none`: those with an unset `token_env` (`test_ui.py` `scoped_server`, `reporting_server`,
  `review_restricted`; `test_home_api.py` `_app`) make no network call — resolution fails `auth_failed` — but would
  log a WARNING per resolution; those with a discovered Secret carrying a token (`test_clusterconfig.py` `TestApi`,
  `TestVanishedSecretIsNotServed`, `TestClusterConfigTier`; `test_clusterconfig_tab.py` `TestApi` and
  `TestClusterConfigTier`) would begin a real request to a fake host. `TierResolver` constructs
  `gsd.kube.ClusterClient`, so a `gsd.api.ClusterClient` monkeypatch does not intercept it.
- **The UI tests** that pin the old default (`TestHome`'s vouches-for-nobody selector, `TestClusterConfigPage`'s
  cards) move with it; the Playwright run is part of the implementing PR's gate.

## 5. Verification on the lab

Built and deployed with `release-crc.sh --argocd`, then walked. Two facts shape the walk: `shared-rnd` IS the host
(`apiUrl: https://api.crc.testing:6443`), so it cannot show that a review ran on another API server; the mock
(`https://mock-openshift:6443`) is a separate API server with its own RBAC (`mock_app/app.py` answers
`POST /apis/authorization.k8s.io/v1/subjectaccessreviews` from `fixtures/reference.yaml`). The lab runs one replica,
so per-replica behaviour is not measured here.

- **Every join path, policy unstated** — each shows `visibility=remote-sar identity=same-as-host` on its
  `cluster-resolved` line: a values entry with a token (the mock stanza, its policy removed for the walk); a
  hand-made Secret (`shared-qa`); a Secret created on the tab at runtime (a second mock cluster), reviewed within one
  discovery and no restart; `saTokenLookup` (`shared-rnd`), including after its derived Secret is deleted and the
  lookup writes it again. An unowned Secret placed over a mode stanza keeps its own policy and `shadows-values-entry`.
- **Authority on a different server** — personas chosen by measuring both sides first (`oc auth can-i … --as=` on CRC,
  the mock's `explain` endpoint): one allowed on CRC and denied on the mock (host-only), one the reverse (remote-only),
  one denied on both, and kubeadmin. Each gets the mock's answer on the mock cluster and CRC's on `shared-rnd`, in
  `/api/whoami`, the selector, one person-scoped tab, one administrator tab, and Home (§6).
- **The auditor** — on the mock, which has no auditor binding, the auditor persona is self; the prerequisite of §3.7
  is what would widen it.
- **Failure paths** — two scratch joining ServiceAccounts, one without `create subjectaccessreviews` and one without
  `list groups`; at least three personas concurrently: one WARNING per 30 s per cluster after the first burst, the
  metric's `outcome=forbidden`, the alert pending under sustained traffic.
- **Rotation** — `shared-qa`'s token, then its CA, then its URL on the tab: each first request after discovery uses
  the new value, the next one the cached verdict.
- **Lifecycle** — the tab-created mock cluster deleted, one cluster disabled: no review for either in the pod log
  after discovery publishes it.
- **Identity** — a defaulted remote serves a persona's own person-scoped rows (not a 403) and appears in Home; an
  entry stating `identity: none` alone stays `self-only`.
- The e2e walk captures the selector and a per-cluster tab for each persona; evidence on #338.

## 6. Risks

- **The default flip turns the critical alert on** for any remote whose joining ServiceAccount lacks `list groups` or
  `create subjectaccessreviews`. The upgrade note says so and names the fix, or `visibility: self-only`; the pod log
  names the cluster, the metric does not (no per-cluster label, out of scope).
- **The default flip changes identity too.** A remote that states nothing becomes `identity: same-as-host`: its
  person-scoped views (groups, users, logins, user bindings, the change feeds, cluster access) serve the reader's own
  rows under their host username instead of a 403, and Home counts that remote in `elsewhere`, `memberships_total`
  and "what changed". An allowed reader also sees the card's `operator_configs`. The upgrade note names each, and
  `identity: none` to keep the old behaviour.
- **A defaulted remote costs a live call** on each viewer's first request per `tierTtlSeconds` from `/api/whoami`,
  `/api/clusters` and alerts; an unreachable one adds up to `TIER_CHECK_TIMEOUT_SECONDS` to that first request before
  the hold (§3.5) takes over.
- **Secrets that state `self-only` keep it.** Tab-created Secrets always carry the form's pair; a lookup-owned one
  follows its stanza (§3.4). The upgrade note says how to move a tab-created cluster.
- **Caches and holds are per replica**, and the budget in §3.1 is stated per replica.

## Orchestrator's notes

- **Review of PR #339** (Codex at xhigh, Grok, OB1-lite on Opus 5.5 at high), all three "implementable after the
  named changes". Accepted, each re-checked in the source before it was written in:
  - the hold as specified let every distinct viewer through during a failure (Codex C3, Grok C3, OB1-lite C3, measured
    by OB1-lite: 5 attempts for 5 viewers in one hold window); OB1-lite's probe design is taken — the request after a
    hold expires re-arms it before calling, the hold is set before the failure is reported, a success clears it —
    over Codex's cluster-wide attempt lock, which would also serialise every healthy viewer's first review; the
    budget sentence now states the first-failure burst;
  - the merge snippet dropped `out.extend(discovered.values())` and with it every Secret-only cluster (Grok C6);
  - the review's error text was redacted after truncation, leaking a JWT's prefix (all three; OB1-lite measured it);
  - `"home" not in app.state.remote_tier_resolvers` breaks on the object (all three); the test changes to `.get`,
    and no `__contains__` is added (OB1-lite: the lazily built map is not the set of remote-sar clusters);
  - the policy is read from the same snapshot as the connection (Codex C2c);
  - the `cluster-resolved` line printed an owned Secret's own frozen policy, not the served one (OB1-lite C6);
  - the parser's import lacked `IDENTITY_NONE` (OB1-lite C5); the default table separates resolution from acceptance
    (Codex C4a); the missed default and wording sites, the auditor's locally created Group, the full behaviour change
    for an unstated remote, and a lab walk that separates the remote's server from the host (all three);
  - the specs index counted `D2b` as a programme row and the header lacked `Release`, failing CI (OB1-lite N1).
- **Decided between reviewers:** which Secret takes its stanza's policy. Grok and OB1-lite held that any Secret over a
  mode stanza should; Codex that only the lookup's own should. SPEC_S3 states the rule for the other case — *"an
  unowned Secret names a declared cluster: today's rule stands, unchanged: the Secret shadows the values entry and
  wins"* — and the broader overlay would override, with a default that may widen, a policy a person deliberately
  wrote into a Secret. Codex's rule is taken, keyed on the ownership test the reader already makes.
- **Rejected:** Codex's capture of the Authorization header to redact a token rotated between a request and its error
  (the same edge applies to `_get` and every poll; redaction here matches `_get`); a `__contains__` on the object
  (above); a setting for the hold (all three: a constant, like the timeout).
- **Out of scope, own issue:** the trusted-bundle cache keyed by path (Codex C2e).
- **Operator decision, 2026-09-23:** the auditor objects on each remote are installed by `group-sync-operator-helm`
  (§3.7).
