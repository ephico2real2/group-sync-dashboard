# SPEC D2b — `remote-sar` for every way a cluster is joined

| | |
|---|---|
| Extends | `docs/specs/SPEC_D2_per_cluster_authorization.md` (per-cluster authorization, released in 0.19.0) |
| Design | `docs/DESIGN_remote_cluster_access.md` — D1, D2, D3, D5 and D6, directed by the operator on 2026-09-23 |
| Release | — (post-programme; D2's step b, like E1 after the programme's R7) |
| Version on release | app and chart minor bumps at the PR |
| Version note | §7's blocks write application 0.32.0 and chart 0.53.0 — the next minors after main's 0.31.0 and 0.52.1 on 2026-09-23 — and move S4c, specified on those two rungs and not begun, to 0.33.0 and 0.54.0 (§3.9). A release that lands first makes the version blocks fail their check, because each one's Old text is the version it replaces; the implementing pull request then corrects them here before applying (`docs/specs/README.md`) |
| Issue | [#338](https://github.com/ephico2real2/group-sync-dashboard/issues/338) |
| Status | released |
| Source | written by the orchestrator on 2026-09-23 from a read-only map of main `b21f80b` and measurements on the lab — not a design agent's output; reviewed before any code is written (review of PR #339: Codex, Grok, OB1-lite; the decisions are under "Orchestrator's notes"). Revised the same day by OB3 from the accepted findings of its third pass and of OB1-lite's confirmation pass, with D5 added at the operator's go-ahead. §7's blocks were generated from a copy of `b8e75b0` with this design implemented, and applied back to a clean copy for the proof |

## How to read this spec

§2 is measured; §3 is the design, one subsection per change, each with its reason; §4 lists the tests; §5 is the
procedure on the lab; §6 names every change an operator or a reader will see, and what it costs. **§7 is the
implementation**: every change as a block in the format `docs/specs/README.md` documents, applied in order to a clean
tree with

```bash
python3 local-development/apply-spec-blocks.py docs/specs/SPEC_D2b_remote_sar_for_every_join.md . --apply
```

The code quoted in §3 is cut from the same implemented copy as §7's blocks, so the two agree line for line: §3 quotes
what a reviewer needs to judge the design, and §7 carries all of it. A block found wrong during implementation is
corrected here, with the reason under the orchestrator's notes, before it is applied again.

## 1. The mandate, and what is out of scope

The operator, 2026-09-23: *"this is what I want: remote-sar for whatever method the cluster was joined."* A remote
cluster's own RBAC decides who sees its data wide, whether the cluster was declared in values with a token, as a
Secret created on the Cluster Configurations tab or by hand, or through `saTokenLookup`. A remote that states no
policy takes `remote-sar` + `same-as-host` (D2), and readers are matched by OpenShift username (D3, no code).

**D5 is in scope** since the operator's go-ahead of 2026-09-23: one line beside the cluster selector says which rule
decided the reader's view of the selected cluster (§3.11).

Out of scope, each decided or tracked elsewhere: D4's named finding (so D5's line cannot tell a reader the remote
denied from a remote that could not be asked, and names both); `clusterAdminSar` (#322, D7); Rejoin and its remote
check (#316, D8); whether `inherit` stays allowed on a remote (not decided); a per-cluster label on the tier-check
metric; the process-wide trusted-bundle cache (§3.1).

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
9. **The joining ServiceAccount's ClusterRole already carries both rights the review needs** (measured on the lab,
   read-only). The ClusterRole `group-sync-dashboard-cluster-poller` grants `create` on `subjectaccessreviews` and
   `get`/`list` on `user.openshift.io` `groups`, is labelled `helm.sh/chart: group-sync-operator-helm-0.14.0`, and is
   bound to the ServiceAccount `group-sync-dashboard-cluster-poller` in `group-sync-operator`; `shared-qa-poller`'s
   hand-made ClusterRoleBinding points at the same role. Of the lab's two remote Secrets, `gsd-cluster-shared-rnd`
   states `visibility: self-only` and `identity: none` and carries `token-source: remote-lookup` (the lookup wrote the
   pair `Settings.cluster_policy` served before this change), and `gsd-cluster-shared-qa` states neither.

## 3. Design

### 3.1 Resolvers follow the cluster's current configuration (D1)

A resolver is found, or built, **on the request**, from ONE merged `ClusterConfig` snapshot, and kept while that
snapshot's connection fingerprint is unchanged. No discovery hook: it works on every replica, in an app with no
poller (tests), and for a cluster that appears, rotates or leaves at runtime. The policy is resolved from the same
object (`remote_policy`, §3.2), never by a second read of the registry through `Settings.cluster_policy`.

`local-development/gsd/kube.py`, after `class TierResolver`, the whole class:

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

    def __init__(self, settings: Settings, make: Callable[[ClusterConfig], TierResolver]):
        self._settings = settings
        self._make = make
        self._lock = threading.Lock()
        self._built: dict[str, tuple[str, TierResolver]] = {}

    def get(self, cluster_id: str) -> TierResolver | None:
        host = self._settings.host_cluster()
        askable = {c.name: c for c in self._settings.effective_clusters()
                   if c.enabled and c.credential_pending is None
                   and (host is None or c.name != host.name)
                   and remote_policy(c.visibility, c.identity) == (VISIBILITY_REMOTE_SAR, IDENTITY_SAME_AS_HOST)}
        cluster = askable.get(cluster_id)
        with self._lock:
            # Every resolver whose cluster is no longer askable is dropped, not only the one asked about: a
            # retired or disabled cluster is never served, so nobody asks for it again, and its resolver holds
            # the configuration it was built on — the Secret's credential included — for the life of the
            # process (the rule the poller's _LAST_TOKEN states: a credential does not outlive its configuration).
            for name in [n for n in self._built if n not in askable]:
                del self._built[name]
        if cluster is None:
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

`local-development/gsd/config.py`, a method of `ClusterConfig`:

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

**Imports**, none of them a behaviour, each in §7: `kube.py`'s import from `.config` adds `IDENTITY_SAME_AS_HOST`,
`VISIBILITY_REMOTE_SAR`, `Settings` and `remote_policy`; `api.py` adds `REMOTE_FAILURE_HOLD_SECONDS` and
`RemoteTierResolvers` from `.kube`, `remote_policy` from `.config` and `Depends` from `fastapi` (§3.10); `config.py`
adds `hashlib` and `json`; `registry.py` and `reader.py` add `dataclasses`; `poller.py` replaces `IDENTITY_NONE,
VISIBILITY_SELF_ONLY` with `remote_policy`; the parser adds `IDENTITY_NONE`. `config.py` imports nothing from
`kube.py`, so `kube.py` importing `Settings` makes no cycle.

**One input is outside the fingerprint's reach and out of scope:** `_trusted_ca_context` (`config.py`) caches the
process-wide trusted bundle by the `GSD_TRUSTED_CA_FILE` path, not its content, so a bundle replaced at the same path
is not seen until a restart. That is true of every poll today, not only of the review, and is tracked by its own
issue rather than widened into this change.

**Budget, per replica and per `remote-sar` cluster** (multiply by the replica count for a release): while the remote
answers, at most one group list and one review **per viewer per `tierTtlSeconds`** (60 s by default). While it fails:
the first failure costs one attempt for each distinct viewer whose request arrived while that first attempt was in
flight; from then on, at most **one attempt per `REMOTE_FAILURE_HOLD_SECONDS`** (§3.5) whatever the number of
viewers, because the first request that would CALL after a hold expires is the only probe and re-arms the hold before
it calls, and every calling path — a leader, or a follower stealing a stuck slot — passes that one gate. A request for
a viewer already being resolved rides that resolution, the probe included, and gets its answer. The first success
ends the hold for every viewer; an attempt that began before the hold and fails after that success re-arms it — fail
closed, never an extra call. Each attempt is paid by the request that made it (§6). A new URL, credential or explicit
CA is used from the first request after discovery publishes it, with no restart; a rebuild deliberately discards the
verdict cache and the hold, so each of `R` connection changes in a TTL costs at most one fresh attempt per viewer. A
lookup beginning after a cluster is published as retired, disabled or pending makes no request. A resolver is never
built for the host. Every lookup also drops the resolver of any cluster that is no longer askable — retired, disabled, pending,
the host, or no longer `remote-sar` + `same-as-host` — from the same single snapshot, so the resolver of a cluster
that is no longer askable, and the credential it was built on, go at the next lookup of any `remote-sar` cluster
(review of the blocks, OB1-lite N3; §7's corrections). A cluster still askable whose credential changed keeps its old
resolver until the next lookup of that cluster, which builds the new one — at the latest the next `/api/clusters`,
which looks up every served cluster. With no discovery hook, that lookup is the only drop: a fleet whose last
`remote-sar` cluster is retired or disabled makes no lookup until one is served again, and keeps that cluster's
resolver, its token included, until then or until the pod restarts; nothing calls with it (measured through the routes
by OB3's confirmation pass).
Measured on the implemented copy with a fake clock bound to `gsd.kube` (ten viewers in flight at
the first failure, then 55 s of ten requests a second from fifty viewers): 10 attempts in the first burst, one probe
at 35.5 s, 11 attempts in 60 s — and 560 with the hold at zero, the host's behaviour.

### 3.2 The default is `remote-sar` + `same-as-host` (D2)

One pure function resolves a non-host cluster's pair. `Settings.cluster_policy`'s last line becomes
`return remote_policy(cluster.visibility, cluster.identity)`, the poller's `_cluster_shape` normalises with it, and
`_create_request` resolves a create that omits either key with it (§3.3).

`local-development/gsd/config.py`, after `CLUSTER_IDENTITIES`:

```python
def remote_policy(visibility: str | None, identity: str | None) -> tuple[str, str]:
    """A non-host cluster's (visibility, identity) with the defaults resolved (SPEC_D2b §3.2, design D2).

    A remote that states nothing is asked about the reader itself: remote-sar + same-as-host. `identity: none`
    says the host's username is nobody on that cluster, so it cannot be asked about them: with no visibility
    stated it keeps self-only, as before. Resolution only — the explicit pair remote-sar + none is refused
    where it is READ (the loader, the Secret parser, the chart), not here."""
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
    # Every visibility, remote-sar included (SPEC_D2b §3.3): the resolver is found per request from the
    # cluster's current configuration, so a Secret-declared cluster is asked like a values one.
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
test and the lookup's write alike.

**An omitted pair is resolved by the one rule.** `CreateRequest` defaults to `remote-sar` / `same-as-host` for a
caller that builds it directly (the lookup always passes the served pair: `fleetlookup.store`). `_create_request`
resolves an omitted `visibility` or `identity` with `remote_policy`, not field by field: a per-field default pairs a
request that states only `identity: none` with `remote-sar`, which the parser refuses (measured on the earlier
revision's code: HTTP 422 `identity-invalid`, where main answers 201 `self-only` / `none`), and gives one that states
only `visibility: self-only` the identity `same-as-host`, which §3.2's table does not. In
`local-development/gsd/api.py`, `_create_request`'s return:

```python
        # One rule for an omitted field, the one discovery applies to the Secret this request writes
        # (SPEC_D2b §3.2): nothing is remote-sar + same-as-host, and `identity: none` alone is
        # self-only — never the refused remote-sar + none.
        visibility, identity = remote_policy(str(body.get("visibility") or "").strip() or None,
                                             str(body.get("identity") or "").strip() or None)
        return CreateRequest(
            name=str(body.get("name") or "").strip(), server=str(body.get("server") or "").strip(),
            credential_kind=str(cred.get("kind") or "bearerToken"), token=cred.get("token"),
            tls_mode=str(tls.get("mode") or "trustedBundle"), ca_data=tls.get("caData"),
            visibility=visibility, identity=identity,
            labels={str(k): str(v) for k, v in labels.items()},
        )
```

The page's option list offers `remote-sar`; both form defaults (`clusterForm` and `ccEmptyForm`) take the pair;
`remote-sar` gets the hint *"this cluster's own RBAC decides, for the reader's OpenShift username"*, and
`same-as-host`'s hint says how a reader is matched (§3.8). The forms send both fields, so a person who picks
`self-only` on the form keeps the form's `same-as-host` unless they change it.

### 3.4 A lookup-owned Secret takes its stanza's policy and switch

The stanza is the configuration item (SPEC_S3): the Secret the lookup writes for it carries the credential, the
stanza the policy and the switch. **Only that Secret.** An unowned Secret over a declared cluster keeps SPEC_S3's
rule — *"the Secret shadows the values entry and wins"*, with the `shadows-values-entry` finding, and the reconciler
stands down.

Ownership is the test the reader already makes (`reader.py`: the Secret's `token-source` annotation equals the
stanza's mode). The reader records it on every Secret it accepts — a new `ClusterConfig` field,
`token_source: str | None = field(default=None, repr=False)` — beside the existing check:

```python
        # The ownership the check below makes, recorded on the config itself (SPEC_D2b §3.4): the merge
        # serves a stanza's policy over the Secret the lookup wrote for it, and only that Secret.
        parsed = dataclasses.replace(parsed, token_source=token_source.get(secret_name))
```

and `ClusterRegistry.merge` uses it. The whole method, `local-development/gsd/clusterconfig/registry.py`:

```python
    def merge(self, values: list[ClusterConfig]) -> list[ClusterConfig]:
        """The values list with the discovered clusters laid over it: a Secret shadows a values entry of the same
        name (C2 — the shadow is reported by the reader as a finding); the host, values[0] enabled, is never replaced
        (the parser refuses a Secret naming it, so nothing here can). A Secret the lookup wrote FOR a mode stanza
        (its token-source is that stanza's credential kind — the reader's "ours") keeps the credential and takes
        the stanza's policy and switch, so an edit of the stanza's visibility, a change of default, or the stanza
        set to `enabled: false` reaches what is served (SPEC_D2b §3.4); an unowned Secret still wins wholesale
        (SPEC_S3). A Secret with no values entry is appended."""
        with self._lock:
            discovered = dict(self._discovered)
        out: list[ClusterConfig] = []
        for c in values:
            found = discovered.pop(c.name, None)
            if found is None:
                out.append(c)
            elif c.connection_mode is not None and found.token_source == c.credential_kind:
                # Either side may disable it: the lookup writes the stanza's `enabled` into the Secret.
                out.append(dataclasses.replace(found, visibility=c.visibility, identity=c.identity,
                                               enabled=c.enabled and found.enabled))
            else:
                out.append(found)
        out.extend(discovered.values())
        return out
```

**Either side may disable an owned Secret.** The lookup writes the stanza's `enabled` into the Secret it creates, and
a stanza set to `enabled: false` afterwards must reach what is served: on the earlier revision's code the owned
Secret's own `enabled` won, and a lookup stanza switched off kept being served, reviewed and alerted on (measured:
served `enabled` true, `/api/whoami` scope `all`, a resolver built, the cluster row `enabled=1`).

**The `cluster-resolved` line prints the served pair and switch**, read through the merge after `registry.replace` —
never the parsed Secret's own fields, which for an owned Secret are not the ones served — and the leader writes the
served `enabled` on the cluster row, which `/api/alerts` and the retirement rule (#96) read. In `poller.py`,
`_discover_once`:

```python
            # The SERVED policy and switch, read through the merge the registry was just given: an owned
            # Secret keeps its own frozen copy, and its stanza's are the ones served (SPEC_D2b §3.4).
            visibility, identity = self.settings.cluster_policy(c.name)
            served = self.settings.cluster(c.name) or c
            event(log, logging.INFO, "cluster-resolved", cycle=cycle, cluster=c.name,
                  source=c.source, credential=c.credential_kind,
                  tls="insecure" if mode["insecure"] else mode["ca"],
                  visibility=visibility, identity=identity,
                  enabled=str(served.enabled).lower())
```

and below the leader check:

```python
            # The SERVED switch (SPEC_D2b §3.4): a lookup stanza set to `enabled: false` disables the
            # Secret it owns, and a row left enabled=1 would keep its frozen snapshot raising alerts (#96).
            served = self.settings.cluster(cluster.name) or cluster
            self.store.upsert_cluster(cluster.name, cluster.api_url, served.enabled,
                                      source=cluster.source, credential=cluster.credential_kind)
```

**Ownership is part of what "changed" means.** A Secret that gains or loses the lookup's `token-source` annotation
with nothing else edited changes the served pair — from its own to its stanza's, or back — and no field that
`_cluster_shape` compared: measured on the earlier revision's code, `self-only` → `remote-sar` with no
`cluster-resolved` line, only the `shadows-values-entry` finding clearing. `_cluster_shape` normalises the pair with
`remote_policy` and ends with the ownership:

```python
    secret_material = json.dumps([cluster.token_value or "", cluster.ca_data or "",
                                  cluster.oauth_username or "", cluster.oauth_password or "",
                                  cluster.token_file or "", cluster.token_env or ""])
    return (
        cluster.source, cluster.credential_kind,
        "insecure" if mode["insecure"] else mode["ca"],
        *remote_policy(cluster.visibility, cluster.identity), cluster.enabled,
        cluster.api_url, cluster.labels,
        hashlib.sha256(secret_material.encode()).hexdigest()[:12],
        cluster.token_source,
    )
```

On the lab this is what moves `shared-rnd` — a `saTokenLookup` stanza with no policy in `environments/crc.yaml`, its
Secret written with `self-only` / `none` and annotated `token-source: remote-lookup` (§2.9) — to the new default
without deleting the Secret, wherever that stanza is declared. Under Argo CD the stanza is not declared (§5).

### 3.5 A failing remote is held, not retried by every viewer

`TierResolver` gains `failure_hold_seconds: float = 0.0`. Zero — the host's resolvers, which do not pass it — keeps
today's observable behaviour: every indeterminate check is uncached and the next request asks again. Above zero, a
failed resolution holds the resolver: no attempt on the remote starts while the hold runs (one already in flight
when the failure lands may finish its attempt); the first request that would call after it expires is the single
probe — a request that arrived during the hold and outwaited a stuck resolution for its viewer included — and
re-arms the hold BEFORE it calls; a success ends the hold for every viewer. The hold
gates every request that would call the remote — a leader, and a follower that steals a stuck leader's slot —
through one helper, `_may_call`; a request for a viewer already being resolved rides that resolution as today, the
probe included, so one page's burst gets one answer.

The constant, beside `TIER_CHECK_TIMEOUT_SECONDS`:

```python
REMOTE_FAILURE_HOLD_SECONDS = 30.0
"""How long a remote-sar cluster's resolver stops asking after a failed resolution (SPEC_D2b §3.5).

A remote that fails — unreachable, a 401, a 403 because its joining ServiceAccount may not list groups
or create reviews — would otherwise be asked again by every viewer's first request, each paying up to
TIER_CHECK_TIMEOUT_SECONDS per call, one remote after another. Held, it is asked at most once per this
many seconds whatever the later traffic: the first request that would call after the hold expires is the
one probe; distinct viewers already in flight when the first failure lands may each pay that first attempt.
Under the 60 s tier TTL and far under the alert's 15 minutes, so a remote that keeps failing under
traffic still records a failed check every thirty seconds and GroupSyncDashboardVisibilityChecksFailing
stays true. A constant, like the timeout, until an operator needs to tune it.
"""
```

The gate and the hold, two methods beside `_note`:

```python
    def _may_call(self, now: float) -> bool:
        """Whether a request about to CALL the remote may (SPEC_D2b §3.5). Called under _lock, and only by
        a request that would call — a leader, or a follower stealing a stuck slot — so a request for a
        viewer already being resolved rides that resolution, the probe included. False while a hold runs;
        the first caller after it expires is the one probe and re-arms the hold BEFORE it calls, so every
        other caller answers self until the probe's outcome ends the hold or restarts it. Always True for
        a resolver built without a hold."""
        if not (self._hold and self._held_until):
            return True
        if now < self._held_until:
            return False
        self._held_until = now + self._hold
        return True

    def _start_hold(self) -> None:
        """A failed resolution holds a remote's resolver (SPEC_D2b §3.5): no call until the hold expires."""
        if self._hold:
            with self._lock:
                self._held_until = time.monotonic() + self._hold
```

`tier_for` asks the gate at the two places a request is about to call. As a leader, before it takes the
single-flight slot:

```python
            leading = mine is None
            if leading:
                if not self._may_call(now):
                    return TIER_SELF
                mine = self._inflight[viewer] = threading.Event()
```

As a follower that waited out a stuck leader, after the existing "the leader finished and failed, or a newer attempt
owns the slot" return and before it steals the slot:

```python
                if mine.is_set() or self._inflight.get(viewer) is not mine:
                    # The leader finished and failed (failures are deliberately not cached),
                    # or a newer attempt already owns the slot. Fail closed for THIS request,
                    # cache nothing — a failure is not a decision.
                    return TIER_SELF
                if not self._may_call(time.monotonic()):
                    # A stealer calls the remote as a leader does, so a held remote is not asked by it
                    # either: a failure elsewhere armed the hold while this request waited (SPEC_D2b §3.5).
                    return TIER_SELF
```

`_resolve_and_cache` calls `self._start_hold()` in both failure branches BEFORE `self._note(...)` — for the reason
the success path caches first: the observe callback is not bounded, and a stalled one must not leave a failing remote
open to every viewer — and on success clears the hold inside the existing cache-write `with self._lock:` block,
before the cache write:

```python
            if self._hold:
                self._held_until = 0.0      # the remote answered: the hold is over for every viewer
```

**Why the gate sits on the call, not on the request.** The earlier revision checked the hold before single-flight:
a request for the probe's own viewer answered self at once while the probe returned `all`, so one refresh read mixed
tiers; and a follower that stole a stuck leader's slot never consulted the hold, so it called inside one (measured on
that code: a second call for the same viewer at t = 2 s under a hold armed until t = 31 s, for a leader stuck in slow
paging and for one stalled in the observe callback). On this design both steals make no call during the hold, and the
probe's four sibling requests read the probe's `all` (§4 holds each).

A cached allowed/denied answer still serves during a hold (the cache is checked first). A hold that expires while its
probe is still out lets one more probe start: one start per hold window, two in flight only when a probe outlives the
hold. Each real attempt is still logged and counted, so `GroupSyncDashboardVisibilityChecksFailing` stays true for a
remote that keeps failing under traffic. Thirty seconds sits under the 60 s TTL and far under the alert's 15
minutes; it is a constant, like `TIER_CHECK_TIMEOUT_SECONDS`, until an operator needs to tune it.

### 3.6 The review's error text is redacted before it is truncated

`ClusterClient.create_subject_access_review` redacts both messages as `_get` does — **before** any truncation: a
ServiceAccount JWT is longer than the 200-character window, and `redact_text` replaces only whole spellings. The
connect error:

```python
                # Redacted as _get does (SPEC_D2b §3.6): an httpx error can carry the request URL.
                raise ClusterError(UNREACHABLE, self._redact(f"{type(exc).__name__}: {exc}")) from exc
```

and the error body, inside the `>= 400` branch's `ClusterError(...)`:

```python
                # REDACT BEFORE TRUNCATING, as _get does (SPEC_D2b §3.6): a ServiceAccount JWT is longer
                # than the window, and redact_text replaces only whole spellings.
                UNREACHABLE, f"HTTP {response.status_code} on {SAR_API}: {self._redact(response.text)[:200]}"
```

### 3.7 The auditor's grant on each remote — installed by `group-sync-operator-helm`

Under `remote-sar` an auditor is wide on a remote only if that remote binds the auditor Group to a role granting the
wide-tier question (`visibility.adminSar`, default `list clusterrolebindings`); the remote's review counts the
remote's bindings, and the reader's groups are read from the remote's Group objects. The objects a remote needs are
this chart's: a ClusterRole with the rules of `group-sync-dashboard-report-auditor`, one ClusterRoleBinding per
auditor Group, and — for an auditor Group the host creates locally (`rbacAuditors.groups[].createLocal: true`) — that
Group with its members, because a local Group exists only on the host.

**Decided by the operator (2026-09-23): `group-sync-operator-helm` installs them on every remote**, alongside the
Groups it already syncs in advance for RBAC and the joining ServiceAccount and ClusterRole it already installs
(§2.9). That chart lives in another repository; this spec records the objects and the contract, and the implementing
pull request names them for an operator in `docs/ACCESS_CONTROL.md` §11 (§3.8).

On the lab the mock stands in for a remote that has not got them: its fixture binds its own auditor Group
`app-ocp-rbac-demo-report-auditors` (member `developer`) to its own `group-sync-dashboard-report-auditor` through
`report-auditors-crb`, and nothing to the host's auditor Group `app-ocp-rbac-groupsync-ns-auditor` — so the host's
auditor `jane.smith` is self on the mock, and the mock's `developer` is wide there (§5).

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
  `config.py`, `environments/crc.yaml`'s comments on `shared-rnd` and `mock`, `docs/reference-architecture.md`'s one
  sentence, and `docs/CLUSTER_STANZA.md` (rows 13 and 14 for `remote-sar` alone and beside `saTokenLookup`; the
  "remote-sar without identity: same-as-host" row becomes "remote-sar with identity: none"; the "saTokenLookup with
  visibility: remote-sar" refusal row goes).
- `docs/ACCESS_CONTROL.md` §11, "How `remote-sar` decides": three sentences become false. "One
  `gsd/kube.py#TierResolver` per remote-sar cluster, constructed on that cluster's `ClusterConfig`" becomes a resolver
  found or built per request from the cluster's current configuration and rebuilt when its connection changes (§3.1);
  "is the self tier and is not cached" gains the hold (§3.5); "The remote RBAC is the operator's, by hand — this chart
  manages no remote RBAC" keeps "this chart manages no remote RBAC" and the `system:auth-delegator` note for a
  ServiceAccount joined by hand, and names what `group-sync-operator-helm` installs on each remote: the joining
  ServiceAccount's ClusterRole with `create subjectaccessreviews` and `list groups`, the auditor ClusterRole, one
  ClusterRoleBinding per auditor Group, and a locally created auditor Group with its members (§3.7). The identity
  paragraph drops "today `none` is the default for a remote entry that states nothing", and the UI sentence names
  D5's line (§3.11).
- `docs/DESIGN_remote_cluster_access.md`: §6's support table turns its two "refused" cells to "yes" and its
  explanation to the past; the status row and §8's D5 row say D5 is directed and built here.
- `local-development/API.md`: the create request's `visibility` and `identity` may be omitted, and how the pair is
  then resolved (§3.3).

### 3.9 Chart and versions

`_helpers.tpl`: the `saTokenLookup` refusal is deleted; the pairing refusal fires only for an explicit
`identity: none` with `remote-sar`. The ConfigMap still injects no default (a test pins it). `NOTES.txt` prints each
remote's resolved pair with the §3.2 rule and marks defaulted values `(default)`.

`Chart.yaml` moves to chart 0.53.0 and application 0.32.0, each with its history line; `pyproject.toml` and
`gsd/__init__.py` carry 0.32.0 (`tests/test_chart_versions.py` holds the three together). S4c was specified on those
two rungs and has not begun, and `tests/test_specs_index.py` holds such a spec above the tree's versions, so the same
change moves S4c to application 0.33.0 and chart 0.54.0: its index row, its header, its decision note and its two
version lines. The CHANGELOG's Unreleased entry names every behaviour change in §6 and the two lines that keep the
old behaviour (`visibility: self-only`, `identity: none`).

`fleetlookup.py` needs no change: `store` writes `settings.cluster_policy(cluster.name)` into the Secret it creates,
which is `remote_policy`'s pair.

### 3.10 Tiers are decided before a read snapshot opens

`/api/clusters` and `/api/alerts` are `@consistent` — each holds a SQLite read snapshot for its whole body — and each
asks `viewer_scope` per cluster inside it. Under `remote-sar` that is a group list and a review on the remote, up to
`TIER_CHECK_TIMEOUT_SECONDS` each, and `store.read_snapshot` forbids a network call inside a snapshot: a held
read-mark stalls `wal_checkpoint(TRUNCATE)`. The default flip makes that the case for every remote that states
nothing. Measured on the earlier revision's code with three unreachable defaulted remotes: `/api/clusters` held its
snapshot for 15.05 s and a concurrent `wal_checkpoint(TRUNCATE)` returned busy `(1, 10, 10)`; with the dependency
below, `(0, 0, 0)`. In `local-development/gsd/api.py`, beside `is_served`:

```python
    def served_scopes(request: Request) -> dict[str, str]:
        """This reader's decision for every served cluster, made BEFORE a handler's read snapshot opens
        (SPEC_D2b §3.10). FastAPI resolves a dependency before it calls the endpoint, and the snapshot is
        opened by the endpoint's @consistent wrapper. Under remote-sar a decision is a group list and a
        SubjectAccessReview on that cluster, up to TIER_CHECK_TIMEOUT_SECONDS each, and a snapshot held
        across a network call pins the WAL read-mark (store.read_snapshot). The rows are the ones the
        fleet handlers walk; a row that appears between this read and the handler's snapshot is decided
        inline, as before, so nothing is widened, dropped or decided twice."""
        return {row["id"]: viewer_scope(request, row["id"])[1] for row in store.clusters() if is_served(row["id"])}
```

`list_clusters(request: Request, scopes: dict[str, str] = Depends(served_scopes))` takes its row's scope as
`scopes[row["id"]] if row["id"] in scopes else viewer_scope(request, row["id"])[1]`, and `list_alerts` takes its
`cscope` the same way from its own dependency, `alert_scopes` (below). Each decision is still made, and counted, once
per request; the request still waits for it (§6) — only the snapshot no longer spans it. Behaviour-preserving,
measured: every persona × route answer
is identical with and without the dependency, and the resolver is called the same number of times (36 = 36).

**The per-cluster routes too** (review of the blocks, OB1-lite F1). Thirteen per-cluster routes are `@consistent`
and decide the named cluster's tier right after `require_cluster` — groups/{name}, users, users/{name}, logins,
cluster-access, bindings/findings, namespaces, namespaces/{name}, home, user-bindings, kyverno, membership-changes and
binding-changes — so under the default each would ask a remote with its snapshot held (measured: `read_depth` 1 at
every decision). A `@tier_first` decorator above `@consistent` asks the named cluster's resolver first and keeps the
answer on the request; `viewer_scope` serves it from there, so the remote is asked once and the decision counted once.
**`/api/alerts` decides on its own walk's predicate** (`alert_scopes`: a stored row that is enabled and not hidden),
not `served_scopes`', so it asks no remote its loop skips (review of the blocks, OB1-lite F2 and Codex B4). **One
window is left, deliberately:** a cluster that becomes decidable between the dependency's (or `@tier_first`'s) read
and the handler's snapshot — a new row, a row the leader writes back to `enabled=1`, or a configuration that starts
serving it as `remote-sar` — is decided inline, inside the snapshot, as before. That needs such a write within one
request's window, and costs one decision: a group list and a review on that remote, up to
`TIER_CHECK_TIMEOUT_SECONDS` each (measured: two calls at read depth 1 for a row re-enabled mid-request), after which
a failure's hold applies. Codex's retry-the-snapshot correction was rejected as more control flow than that window is
worth (Orchestrator's notes).

### 3.11 D5 — the reader is told which rule decided

Directed by the operator on 2026-09-23 (design D5). One short muted line beside the cluster selector names the rule
that decided the reader's view of the SELECTED cluster. It reads `/api/whoami`'s `visibility.clusters[<id>]` —
`{policy, identity, scope}`, which the server already serves for every served cluster — and derives nothing: no API
change.

| `policy` | `identity` | `scope` | The line |
|---|---|---|---|
| `inherit` | any | any | The host decides your view of this cluster. |
| `remote-sar` | `same-as-host` | `all` | This cluster's own RBAC gives you the full view. |
| `remote-sar` | `same-as-host` | `self` | This cluster's own RBAC shows your own rows, or could not be asked. |
| `self-only` | `same-as-host` | `self` | This cluster is self-only: everyone sees their own rows. |
| `self-only` | `none` | `self` | This cluster is self-only and does not treat your identity as its own. |

- **Truthful to the wire.** `scope: self` under `remote-sar` is either the remote's denial or a remote that could
  not be asked (unreachable, a 403 on the review or on the group list, a hold); the wire does not say which — that is
  D4's field, not built — so the line names both. `self-only` with `identity: none` serves no person-scoped rows (a
  403 there; cluster health still shows), so its line does not promise "your own rows"; its words are the refusal
  card's (*"does not treat your identity as one of its own"*).
- **The host.** The wire does not mark which cluster is the host — only `/api/clusterconfigs`, which is not every
  reader's, carries `host` — and the host's policy is `inherit` unless it states `self-only`. So the host shows the
  `inherit` line, which is literally true of it (the host's own RBAC decides), and the line never repeats the pill's
  "Full view" / "Your view".
- **No line** with restrictions off (`visibility.enabled === false`), with no authenticated identity, with no cluster
  selected (the Overview's "all clusters" is a position, not a cluster), on the fleet-wide pages (Usage, the KPI page),
  which have no selector, and for an id that has no entry.
- **Where and how long.** Inside the filter bar, right after the selector, with the existing `.filterbar-note` class
  (muted, `--text-sm`); the bar wraps, so at 375 px the line takes its own row inside the viewport. Every sentence is
  at most 70 characters (a test holds it).

The function, beside `narrowedOnHost` in `local-development/gsd/static/index.html`:

```js
/* D5 (SPEC_D2b §3.11): WHICH RULE decided this reader's view of the selected cluster, read off whoami's
   `visibility.clusters[id]` = {policy, identity, scope} and never derived. The wire does not tell a remote's
   "denied" from "could not be asked" (that is D4's field, not built), so that line names both; it does not mark
   the host either, so `inherit` says "the host decides", which is as true of the host as of a remote that
   inherits. Empty with restrictions off, with no authenticated identity, and with no cluster selected. */
function scopeWhy(w, cluster) {
  const vis = w && w.authenticated && w.visibility;
  if (!vis || vis.enabled === false || !cluster) return "";
  const c = vis.clusters && vis.clusters[cluster];
  if (!c) return "";
  if (c.policy === "inherit") return "The host decides your view of this cluster.";
  if (c.policy === "remote-sar") {
    return c.scope === "all" ? "This cluster's own RBAC gives you the full view."
      : "This cluster's own RBAC shows your own rows, or could not be asked.";
  }
  if (c.policy === "self-only") {
    return c.identity === "same-as-host" ? "This cluster is self-only: everyone sees their own rows."
      : "This cluster is self-only and does not treat your identity as its own.";
  }
  return "";
}
```

and the line in `renderFilters`:

```js
  // D5 (SPEC_D2b §3.11): the rule that decided the selected cluster's view, beside the selector that picks it.
  const why = fleetWide ? "" : scopeWhy(data.whoami, view.cluster);
  let html = fleetWide ? "" : `<label for="f-cluster">Cluster</label>
    <select id="f-cluster">${fleetOption}${goneOption}${opts}</select>${
      why ? `<span class="filterbar-note scope-why" id="scope-why">${esc(why)}</span>` : ""}`;
```

## 4. Tests

Four new files and one new browser class; every existing test that pinned the old default, the old refusals, or a
fixture that would now ask a made-up remote is edited in §7. The tree §7 produces passes the whole suite, the browser
suite included (measured 2026-09-23; OB3's validation record of this revision).

- **`local-development/tests/test_remote_tier_hold.py`** (new) — the hold and its gate on a fake clock bound to
  `gsd.kube`. After a hold expires one probe goes out whatever the number of viewers, and a failed probe re-arms it;
  a success ends it for every viewer; a cached verdict serves during a hold; the first failure costs one attempt per
  viewer already in flight and none after it; the first request after every expiry pays the call (`[1, 0, 1, 0, 1]`
  calls at t = 0, 10, 31, 40, 62 s — §6's cost, pinned); a hold-0 resolver, the host's, asks on every request as
  today. Every calling path passes the gate: the probe's own viewer rides the probe and reads its answer, and a
  follower of a leader stalled in the observe callback makes no call during the hold (OB1-lite's two tests, moved
  onto the fake clock); a follower that gives up on a leader stuck in paging makes none either; a follower of a stuck
  probe starts no second probe. A rotated token builds a new resolver that asks at once.
- **`local-development/tests/test_remote_tier_resolvers.py`** (new) — `RemoteTierResolvers`: a Secret-declared
  cluster gets a resolver and keeps the same one while nothing changes; a new one on a rotated token, a new explicit
  CA, a new URL and `insecure`; a values entry's file names move the fingerprint and their contents do not; a policy
  change is not a connection change; None — and the entry forgotten — for a retired, disabled, pending, host,
  `hidden`, `inherit`, `self-only` or `remote-sar` + `none` cluster; one configuration snapshot per lookup.
  `build_app` builds each remote's resolver on that remote's API with the hold and the adminSar attributes, and no
  pool with restrictions off. Redaction: a JWT echoed at offset 150 of a 502 body never reaches the message, even
  across the 200-character cut; a connect error carrying the credential is redacted.
- **`local-development/tests/test_remote_sar_default.py`** (new) — the pair rule: every row of §3.2's table through
  `remote_policy` and for acceptance by the loader, the parser and the chart; the chart accepts `remote-sar` beside
  `saTokenLookup`. An unstated remote end to end: with an allowing stub, `/api/whoami`, the card's
  `operator_configs`, every person-scoped route including Namespaces and its own Home, the three administrator tabs
  and its administrator alert; with a denying stub and with none, the reader's own rows instead of the old 403, the
  administrator tabs 403, no `operator_configs`; the host's Home counts it without asking its resolver; `/api/whoami`
  asks it once; `identity: none` alone keeps the 403. §3.10: every tier decision of `/api/clusters` and `/api/alerts`
  is made outside a read snapshot. §3.3: the create request resolves an omitted field by §3.2's rule, and the
  explicit pair is `422 identity-invalid`.
- **`local-development/tests/test_lookup_owned_secret.py`** (new) — the merge: an owned Secret keeps its credential
  and source and serves the stanza's pair; an unowned Secret, or one another mode wrote, wins wholesale; a plain values
  entry is replaced wholesale and a Secret with no entry appended; either side may disable; `dataclasses.replace`
  keeps every `compare=False` credential field. Discovery, through the real reader and `Poller._discover_once`: the
  `cluster-resolved` line prints the served pair; an ownership flip alone logs the pair now served; a disabled lookup
  stanza is not served, its row is `enabled=0` and no resolver is built. The lookup writes the pair it serves, before
  and after its Secret is discovered.
- **Edited** (§7 carries each): `test_multicluster_visibility.py` — `far` states `identity: none`, so the tests that
  need a self-only/none remote keep one, and the default and the loader's rule are pinned anew; `test_config.py`;
  `test_dashboard_controller.py` — the refusal is the explicit pair, `.get("home") is None` replaces `"home" not in
  …`, which the object does not support, and the remote is reviewed on its own API; `test_clusterconfig.py` and
  `test_clusterconfig_tab.py` — the explicit pair is the refused one, a discovered `east` is `remote-sar`, and
  `app.state.remote_tier_resolvers = {}` where no remote may be asked; `test_clusterconfig_logging.py`;
  `test_fleet_lookup.py`; `test_cluster_stanza_matrix.py`, with `docs/CLUSTER_STANZA.md`;
  `test_chart_connection_modes.py`; `test_chart_strategy.py`; `test_chart_dashboard_controller.py`; prose only in
  `test_home_api.py` and `test_visibility.py`.
- **No test reaches a host it did not reach before.** A fixture with an unstated remote and restrictions on now asks
  that remote, and `TierResolver` constructs `gsd.kube.ClusterClient`, which a `gsd.api.ClusterClient` monkeypatch
  does not intercept. Measured with a plugin that refuses and records every non-loopback connection: the applied
  tree's non-browser suite makes exactly the two it made before this change (`test_clusterconfig_tab.py`'s
  `TestClusterConfigTier`, `GET https://api.west.example:6443/version`), and the browser suite none.
- **The page** (`local-development/tests/test_ui.py`, Playwright). The restricted fixtures (`scoped_server`,
  `reporting_server`, `_review_server`) state `identity: none` on their remotes — the pair their tests were written
  against. The Cluster Configurations page reads `remote-sar` on a discovered card, offers `remote-sar` and starts on
  the default pair, and a create through the form writes that pair. `TestTheRuleBesideTheSelector` (D5), on its own
  fixture with one remote per rule and the `remote-sar` decision a stub, reads each row of §3.11's table on Home;
  follows the selector across every rule, back, and onto another tab; follows a flipped payload, so nothing is
  derived; shows no line on the fleet view, on the Usage page, without an identity or with restrictions off; wraps
  inside 375 px; and holds every sentence to 70 characters.

## 5. Verification on the lab

Built, deployed and walked on CRC; the evidence goes on #338. The walk proves #338's Definition of Done: `remote-sar`
on every join path; a rotated token, CA or URL used without a restart; a retired or disabled cluster never asked; the
default and its two exceptions; the hold and the redaction; `shared-rnd` and `shared-qa` on `remote-sar` under Argo
CD, kubeadmin wide on both once Step 11 rejoins `shared-qa` (it is `self` there until then: its token is expired on
purpose) and a non-admin self on both; and D5's line for each persona.

Facts that shape it (measured 2026-09-23, read-only):

- `shared-rnd` and `shared-qa` point at `https://api.crc.testing:6443`, the host's own API server: they show
  `remote-sar` resolving and deciding, not a review on another server. The mock (`https://mock-openshift:6443`,
  `local-development/mock-app`) is a separate API server whose RBAC is its fixture,
  `local-development/mock-app/fixtures/reference.yaml`, and whose `/_mock/state` keeps a request log.
- `shared-qa`'s Secret holds a 10-minute token for `group-sync-operator:shared-qa-poller` that is **expired on purpose**
  (the operator: set to expire, to demonstrate the path rather than use a long-term token). It is the lab's
  expired-credential case: the poller logs `auth_failed … rotate it in this cluster's Secret`, and under `remote-sar`
  every reader's check on it fails closed to `self` with an `auth_failed` warning. Its wide view is shown only in
  Step 7's working-token rows, and Step 7 restores it expired; Step 11 then rejoins it with a long-lived token, as the
  operator directed once the expired case was shown.
- Under Argo CD the Application's `valuesObject.clusters` is `dashboard` alone
  (`gitops/argocd-application-dashboard.yaml`): `shared-rnd` has no stanza there and is served from its Secret
  wholesale, and there is no `mock` values entry. Its Secret states `self-only` / `none` (§2.9). The Helm rounds use
  `environments/crc.yaml`, where `shared-rnd` is a `saTokenLookup` stanza that states no policy, so the owned-Secret
  merge serves `remote-sar` + `same-as-host` (§3.4); deleting the Secret in a Helm round makes the lookup write it
  again with that pair stated, which is what Argo CD then serves. Never delete it under Argo CD: with no stanza,
  nothing writes it again.
- Helm mode (`release-crc.sh` without `--argocd`) deletes the Application before it installs, and `--argocd` creates
  it again from the committed file. The recorded sync policy is therefore restored on the Application `--argocd`
  creates; the committed file carries the same policy today (automated prune and selfHeal, retry 3 from 30 s,
  `CreateNamespace`, `RespectIgnoreDifferences`, `ServerSideApply`).
- The `mock-creds` volume is not part of the chart: it is patched onto the Deployment after every Helm install
  (`local-development/mock-app/deploy/deploy-mock.sh`, step 5).
- The personas, measured on both servers: CRC's `list clusterrolebindings` with each user's Groups — kubeadmin yes,
  jane.smith yes (the host's auditor: `app-ocp-rbac-groupsync-ns-auditor` → `group-sync-dashboard-report-auditor`),
  developer no, test-user-002 no; the mock's `POST /_mock/sar-probe` — kubeadmin allowed (cluster-admin), developer
  allowed (the mock's own auditor, §3.7), jane.smith denied (her `platform-team-cluster-admin` is a decoy nothing
  binds), test-user-002 denied. So jane.smith is host-only, developer remote-only, test-user-002 neither, kubeadmin
  both.
- One replica: per-replica behaviour is not measured here.

**Step 0 — sessions and names.** A token session (release-crc.sh pushes with `oc whoami -t`), the implementing branch
checked out at the repository root and pushed, and a scratch directory outside the worktree, which release-crc.sh
would otherwise count as dirty. `api_as <user> <path>` reads the API as that person through the pod's loopback, the
proxy's trust boundary, with every tier decided by real reviews; `code_as` gives the status alone. Nothing runs a
shell inside the image:

```bash
export KUBECONFIG=<scratch>/kubeconfig-token    # oc login -u kubeadmin into a scratch kubeconfig first
NS=group-sync-dashboard; APP=group-sync-dashboard; ARGO_NS=openshift-gitops; WALK=$(mktemp -d)
PY=local-development/.venv/bin/python          # any Python with Playwright and its chromium, for Step 6
pod() { oc get pods -n "$NS" -l app.kubernetes.io/name=group-sync-dashboard --field-selector=status.phase=Running -o name | head -1; }
api_as() { oc exec -n "$NS" "$(pod)" -c dashboard -- curl -s -H "X-Forwarded-User: $1" "http://127.0.0.1:8080$2"; }
code_as() { oc exec -n "$NS" "$(pod)" -c dashboard -- curl -s -o /dev/null -w '%{http_code}' -H "X-Forwarded-User: $1" "http://127.0.0.1:8080$2"; }
resolved() { oc logs -n "$NS" "$(pod)" -c dashboard | grep cluster-resolved | grep "cluster=$1 " | tail -1; }
traffic() {  # traffic <seconds>: kubeadmin, jane.smith and developer ask /api/whoami at once, each in its own loop
  end=$(( $(date +%s) + $1 ))
  for u in kubeadmin jane.smith developer; do
    ( while [ "$(date +%s)" -lt "$end" ]; do api_as "$u" /api/whoami >/dev/null; done ) &
  done
  wait
}
```

**Step 1 — record the dashboard Application's sync policy, then pause its automated sync** — the dashboard's
Application only, never Grafana's or the operator's — so no automated sync starts before the first Helm round's
handover:

```bash
oc get application "$APP" -n "$ARGO_NS" -o jsonpath='{.spec.syncPolicy}' > "$WALK/syncpolicy.json"
oc patch application "$APP" -n "$ARGO_NS" --type json -p '[{"op": "remove", "path": "/spec/syncPolicy/automated"}]'
```

**Step 2 — measure the personas on both servers.** Expect the pairs above; if a persona's pair differs, choose another
user with that pair before going on. The Groups are passed as arguments from Python, not through the shell, so the
command is the same in bash and zsh:

```bash
python3 - <<'PY'
import json, subprocess
groups = json.loads(subprocess.run(["oc", "get", "groups", "-o", "json"], check=True, capture_output=True, text=True).stdout)["items"]
for user in ("kubeadmin", "jane.smith", "developer", "test-user-002"):
    mine = [f"--as-group={g['metadata']['name']}" for g in groups if user in (g.get("users") or [])]
    can = subprocess.run(["oc", "auth", "can-i", "list", "clusterrolebindings", f"--as={user}",
                          "--as-group=system:authenticated", *mine], capture_output=True, text=True).stdout.strip()
    print(f"CRC  {user}: {can}")
PY
oc port-forward -n "$NS" svc/mock-openshift 16443:6443 >/dev/null & PF=$!; sleep 2
for u in kubeadmin jane.smith developer test-user-002; do
  printf 'mock %s: ' "$u"; curl -sk -X POST https://127.0.0.1:16443/_mock/sar-probe -H 'Content-Type: application/json' -d "{\"user\": \"$u\"}"; echo
done
kill "$PF"
```

**Step 3 — Helm round 1: every join path at the default.** A values file equal to `environments/crc.yaml` but with
the mock stanza's two policy lines removed, so that values entry takes the default. It is untracked and outside
`local-development/`, which release-crc.sh does not count as dirty:

```bash
python3 - <<'PY'
import pathlib
src = pathlib.Path("environments/crc.yaml").read_text()
walk = src.replace("    visibility: inherit\n    identity: same-as-host\n", "", 1)
assert walk != src
pathlib.Path("environments/crc-d2b-walk.yaml").write_text(walk)
PY
./local-development/release-crc.sh --values environments/crc-d2b-walk.yaml
oc set volume deploy/group-sync-dashboard -n "$NS" --add --overwrite --name mock-creds --secret-name mock-cluster-creds --mount-path /etc/gsd/mock
oc rollout status deploy/group-sync-dashboard -n "$NS" --timeout=300s
```

Expect, after the first discovery: `oc logs -n "$NS" "$(pod)" -c dashboard | grep 'mock: per-cluster visibility
policy'` ends `remote-sar, identity same-as-host` (a values entry's policy is on this start-up line; `cluster-resolved`
is emitted for discovered Secrets only); `resolved shared-qa` and `resolved shared-rnd` both show
`visibility=remote-sar identity=same-as-host enabled=true` — `shared-rnd`'s own Secret still states `self-only` /
`none`, and the stanza's pair is the one served.

**Step 4 — ownership, then the lookup's own write** (§3.4; a Helm round only):

```bash
oc annotate secret gsd-cluster-shared-rnd -n "$NS" groupsync-dashboard.io/token-source-
#   next discovery: `resolved shared-rnd` shows visibility=self-only identity=none, and the Cluster Configurations tab
#   lists the shadows-values-entry finding: an unowned Secret wins wholesale
oc annotate secret gsd-cluster-shared-rnd -n "$NS" groupsync-dashboard.io/token-source=remote-lookup
#   next discovery: visibility=remote-sar identity=same-as-host again, and the finding clears
oc delete secret gsd-cluster-shared-rnd -n "$NS"
#   the lookup writes it again on a later discovery — every bindingIntervalSeconds, which a delete by hand does not
#   shorten — so wait for it; then read its two policy keys, and nothing else of it
until oc get secret gsd-cluster-shared-rnd -n "$NS" -o name >/dev/null 2>&1; do sleep 10; done
for k in visibility identity; do printf '%s=' "$k"; oc get secret gsd-cluster-shared-rnd -n "$NS" -o jsonpath="{.data.$k}" | base64 -d; echo; done
```

Expect `visibility=remote-sar` and `identity=same-as-host`.

**Step 5 — a Secret created at runtime, and the identity exception.** Through the tab's own route (the page's Create
calls it), with the mock's token — its fixture's `meta.token`, which `deploy-mock.sh` explains is not a secret — and
its CA, and neither policy key; the request goes on stdin:

```bash
TOKEN=$(awk '/^  token:/{gsub(/"/,"",$2); print $2; exit}' local-development/mock-app/fixtures/reference.yaml)
CA=$(oc get secret mock-ca -n "$NS" -o jsonpath='{.data.tls\.crt}')
create() {  # create <name> [<extra JSON members>]
  printf '{"name": "%s", "server": "https://mock-openshift:6443", "credential": {"kind": "bearerToken", "token": "%s"}, "tls": {"mode": "caData", "caData": "%s"}%s}' "$1" "$TOKEN" "$CA" "${2:-}" \
    | oc exec -i -n "$NS" "$(pod)" -c dashboard -- curl -s -X POST -H 'X-Forwarded-User: kubeadmin' \
        -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1:8080/api/clusterconfigs; echo
}
create mock-sar
create mock-none ', "identity": "none"'
for s in mock-sar mock-none; do for k in visibility identity; do printf '%s %s=' "$s" "$k"; oc get secret "gsd-cluster-$s" -n "$NS" -o jsonpath="{.data.$k}" | base64 -d; echo; done; done
```

Expect `mock-sar` written `remote-sar` / `same-as-host` and `mock-none` written `self-only` / `none` (§3.3); within
one discovery and with no restart, `resolved mock-sar` shows `visibility=remote-sar identity=same-as-host`,
`api_as developer /api/whoami` has `mock-sar` at `"scope": "all"`, and `code_as developer /api/clusters/mock-none/groups`
answers 403.

**Step 6 — the personas, on every cluster** (the pairs of Step 2 decide each answer). Through the loopback:

```bash
for u in kubeadmin jane.smith developer test-user-002; do
  echo "== $u"
  api_as "$u" /api/whoami | python3 -c 'import json, sys
v = json.load(sys.stdin)["visibility"]["clusters"]
for c in ("dashboard", "shared-rnd", "shared-qa", "mock", "mock-sar"):
    print(" ", c, v.get(c, {}).get("policy"), v.get(c, {}).get("scope"))'
  for c in shared-qa mock; do
    for p in groups bindings/findings home; do printf '  %s %s: %s\n' "$c" "$p" "$(code_as "$u" "/api/clusters/$c/$p")"; done
  done
done
```

Expect `dashboard` `inherit` for everyone; kubeadmin `all` on `shared-rnd`, `mock` and `mock-sar`; jane.smith `all` on
`shared-rnd` and `self` on `mock` and `mock-sar`; developer `self` on `shared-rnd` and `all` on `mock` and `mock-sar`;
test-user-002 `self` everywhere; and **every reader `self` on `shared-qa`**, whose token is expired on purpose (the
facts above): the first reader's check logs `shared-qa: visibility tier for '<reader>' is indeterminate (auth_failed:
401 …)` and arms the 30 s hold, so the readers after it are answered `self` without a call. Where a reader is `self`
on a remote, `groups` and `home` answer 200 with that reader's own rows — not the 403 of before — and
`bindings/findings` answers 403; where `all`, all three answer 200.

Then D5's line, in the page, for each persona: the pod's loopback forwarded to the workstation, and the page opened
with the identity header the proxy would set — **one fresh page for each reader and cluster**. On one page, moving
between clusters changes only the URL's fragment, and the check can match the previous cluster's line before the app
repaints for the new one: the first walk (2026-09-24) passed kubeadmin and jane.smith on `shared-qa` that way, on
`shared-rnd`'s text, while a fresh page showed them narrowed. Each check therefore starts from an empty line.

```bash
oc port-forward -n "$NS" "$(pod)" 18080:8080 >/dev/null & PF=$!; sleep 2
"$PY" - <<'PY'
from playwright.sync_api import sync_playwright
HOST, FULL = "The host decides your view of this cluster.", "This cluster's own RBAC gives you the full view."
OWN = "This cluster's own RBAC shows your own rows, or could not be asked."
# shared-qa is in no reader's set: its token is expired on purpose, so it is OWN for everyone.
wide = {"kubeadmin": {"shared-rnd", "mock", "mock-sar"}, "jane.smith": {"shared-rnd"},
        "developer": {"mock", "mock-sar"}, "test-user-002": set()}
with sync_playwright() as p:
    browser = p.chromium.launch()
    for user, full in wide.items():
        for cluster in ("dashboard", "shared-rnd", "shared-qa", "mock", "mock-sar"):
            want = HOST if cluster == "dashboard" else FULL if cluster in full else OWN
            context = browser.new_context(extra_http_headers={"X-Forwarded-User": user})
            page = context.new_page()
            page.goto(f"http://127.0.0.1:18080/#page=home&cluster={cluster}")
            try:
                page.wait_for_function("(t) => (document.getElementById('scope-why') || {}).textContent === t", arg=want, timeout=15000)
                print("ok ", user, cluster, want)
            except Exception:
                print("BAD", user, cluster, page.evaluate("() => (document.getElementById('scope-why') || {}).textContent"))
            context.close()
    browser.close()
PY
kill "$PF"
```

**Step 7 — rotation without a restart** (§3.1). The tab's in-place write takes a token only (`PUT
/api/clusterconfigs/<name>/credential` accepts `token` alone), so the CA and the URL are rotated by editing the
Secret. Each change is made twice — first to a value that fails, then to one that works — so the next request after
discovery shows which value it used; the working one answers at once, because the rebuilt resolver carries neither
the old cache nor the old hold. Keep the Secret to restore it, never printed:

```bash
oc get secret gsd-cluster-shared-qa -n "$NS" -o json > "$WALK/shared-qa.json"
rotate() {  # rotate <token>: the tab's route, the token on stdin
  printf '{"token": "%s"}' "$1" | oc exec -i -n "$NS" "$(pod)" -c dashboard -- curl -s -X PUT -H 'X-Forwarded-User: kubeadmin' \
    -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1:8080/api/clusterconfigs/shared-qa/credential; echo
}
set_trust() {  # set_trust <base64 PEM> [<server>]: shared-qa's config trusts exactly that CA; the token is untouched
  python3 - "$@" <<'PY'
import base64, json, subprocess, sys
s = json.loads(subprocess.run(["oc", "get", "secret", "gsd-cluster-shared-qa", "-n", "group-sync-dashboard", "-o", "json"],
                              check=True, capture_output=True, text=True).stdout)
config = json.loads(base64.b64decode(s["data"]["config"]))
config["tlsClientConfig"] = {"caData": sys.argv[1]}
s["data"]["config"] = base64.b64encode(json.dumps(config, separators=(",", ":")).encode()).decode()
if len(sys.argv) > 2:
    s["data"]["server"] = base64.b64encode(sys.argv[2].encode()).decode()
subprocess.run(["oc", "replace", "-f", "-"], input=json.dumps(s), check=True, capture_output=True, text=True)
PY
}
oc apply -n group-sync-operator -f - <<'YAML'
apiVersion: v1
kind: Secret
metadata:
  name: shared-qa-poller-d2b-walk
  annotations:
    kubernetes.io/service-account.name: shared-qa-poller
type: kubernetes.io/service-account-token
YAML
sleep 5   # the token controller fills the Secret
NEW_TOKEN=$(oc get secret shared-qa-poller-d2b-walk -n group-sync-operator -o jsonpath='{.data.token}' | base64 -d)
ROOT_CA=$(oc get configmap kube-root-ca.crt -n "$NS" -o jsonpath='{.data.ca\.crt}' | base64 | tr -d '\n')
```

Then, one change at a time, waiting for the `resolved shared-qa` line after each and reading
`api_as kubeadmin /api/whoami`'s `shared-qa` scope:

| Change | Command | Expect |
|---|---|---|
| a token that is not one | `rotate sha256~d2b-walk-not-a-token` | `self`; a WARNING naming `shared-qa`, `auth_failed` |
| a new token of the same ServiceAccount | `rotate "$NEW_TOKEN"` | `all`, at once |
| a CA that does not sign `api.crc.testing` | `set_trust "$CA"` (the mock's) | `self`; a WARNING, `unreachable` (certificate verification) |
| the cluster's own CA bundle | `set_trust "$ROOT_CA"` | `all`, at once |
| a URL nothing answers | `set_trust "$ROOT_CA" https://api.crc.testing:6444` | `self`; a WARNING, `unreachable` |

`kube-root-ca.crt` verifies `api.crc.testing:6443` (measured: `openssl s_client … -CAfile` returns 0; the mock's CA
returns 19). No row points `shared-qa` at the in-cluster API. By the operator's rule every in-cluster name is the
dashboard controller's own endpoint, used with the CA mounted into its pod, never a remote's; the parser enforces only
part of that rule: it refuses a Secret whose `server` is exactly `https://kubernetes.default.svc` or whose `name` is the
host's (`host-cluster-not-from-secret`, measured by the first walk: the cluster was retired until the next change), and
other spellings are not refused (closed as not a gap; see the notes). The dead-URL row shows a URL change taking effect with
no restart.
Restore — the saved
`resourceVersion` is stale by then and is stripped; `oc replace` of an object without one reads the live one and sends
it (measured with `oc` 4.22.13 against a recording API stand-in):
`python3 -c "import json,sys; s=json.load(open(sys.argv[1])); m=s['metadata']; [m.pop(k, None) for k in ('resourceVersion','uid','creationTimestamp','managedFields')]; print(json.dumps(s))" "$WALK/shared-qa.json" | oc replace -f -`,
then `oc delete secret shared-qa-poller-d2b-walk -n group-sync-operator`. The restore puts back the intentionally
expired token: expect `self` again, with an `auth_failed` warning.

**Step 8 — failure paths and the hold.** Two scratch joining ServiceAccounts, one without `create
subjectaccessreviews` and one without `list groups`, joined through the tab's route, then three personas at once for
two minutes:

```bash
oc create namespace d2b-walk
oc create serviceaccount no-sar -n d2b-walk; oc create serviceaccount no-groups -n d2b-walk
oc create clusterrole d2b-walk-no-sar --verb=get,list --resource=groups.user.openshift.io
oc create clusterrole d2b-walk-no-groups --verb=create --resource=subjectaccessreviews.authorization.k8s.io
oc create clusterrolebinding d2b-walk-no-sar --clusterrole=d2b-walk-no-sar --serviceaccount=d2b-walk:no-sar
oc create clusterrolebinding d2b-walk-no-groups --clusterrole=d2b-walk-no-groups --serviceaccount=d2b-walk:no-groups
for sa in no-sar no-groups; do
  printf '{"name": "d2b-%s", "server": "https://api.crc.testing:6443", "credential": {"kind": "bearerToken", "token": "%s"}, "tls": {"mode": "trustedBundle"}}' \
    "$sa" "$(oc create token "$sa" -n d2b-walk --duration=2h)" \
    | oc exec -i -n "$NS" "$(pod)" -c dashboard -- curl -s -X POST -H 'X-Forwarded-User: kubeadmin' \
        -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1:8080/api/clusterconfigs; echo
done
#   after the next discovery (resolved d2b-no-sar, resolved d2b-no-groups):
traffic 120
oc logs -n "$NS" "$(pod)" -c dashboard --since=3m | grep -cE 'd2b-no-(sar|groups): visibility tier for'
api_as kubeadmin /metrics | grep gsd_visibility_tier_checks_total | grep forbidden
```

Expect, per cluster, one WARNING per persona in the first burst and at most one per 30 s after it — at most 3 + 4
per cluster in the two minutes, 14 for the pair — each naming its cluster and `forbidden`; the metric's
`outcome="forbidden"` series rising by the same count; and `GroupSyncDashboardVisibilityChecksFailing` pending
(user-workload monitoring and the chart's PrometheusRule are on the lab). Then remove them: `DELETE
/api/clusterconfigs/d2b-no-sar` and `…/d2b-no-groups` through the loopback as kubeadmin, and `oc delete namespace
d2b-walk`, `oc delete clusterrolebinding d2b-walk-no-sar d2b-walk-no-groups`, `oc delete clusterrole
d2b-walk-no-sar d2b-walk-no-groups`.

**Step 9 — lifecycle: a retired and a disabled cluster are never asked.** Delete `mock-sar` and `mock-none` through the
tab's route (`DELETE /api/clusterconfigs/<name>`); then a second Helm round with the `shared-rnd` and `mock` stanzas
switched off — `shared-rnd` has a derived Secret, which its stanza now disables (§3.4), and `mock` has none:

```bash
python3 - <<'PY'
import pathlib
p = pathlib.Path("environments/crc-d2b-walk.yaml"); t = p.read_text()
for name in ("shared-rnd", "mock"):
    i = t.index(f"  - name: {name}\n"); j = t.index("    enabled: true\n", i)
    t = t[:j] + "    enabled: false\n" + t[j + len("    enabled: true\n"):]
p.write_text(t)
PY
./local-development/release-crc.sh --values environments/crc-d2b-walk.yaml
oc set volume deploy/group-sync-dashboard -n "$NS" --add --overwrite --name mock-creds --secret-name mock-cluster-creds --mount-path /etc/gsd/mock
oc rollout status deploy/group-sync-dashboard -n "$NS" --timeout=300s
```

Expect `resolved shared-rnd` to show `enabled=false`, and `api_as kubeadmin /api/whoami` to carry no `shared-rnd`,
`mock`, `mock-sar` or `mock-none`. Then nothing reaches the mock during a minute of traffic — its request log
(`/_mock/state`, which does not record `/_mock/*` itself) is the same before and after:

```bash
oc port-forward -n "$NS" svc/mock-openshift 16443:6443 >/dev/null & PF=$!; sleep 2
log() { curl -sk https://127.0.0.1:16443/_mock/state | python3 -c 'import json, sys; print(json.load(sys.stdin)["recent_requests"])' | shasum; }
before=$(log); traffic 60; after=$(log); kill "$PF"
[ "$before" = "$after" ] && echo "the mock was not asked" || echo "the mock WAS asked"
```

**Step 10 — hand back to Argo CD, restore the sync policy, check the Definition of Done.** Remove the scratch values
file, deploy the pushed head through Argo CD, then put back exactly the sync policy recorded in Step 1 (the
Application `--argocd` created carries the committed file's):

```bash
rm environments/crc-d2b-walk.yaml
./local-development/release-crc.sh --argocd
python3 - "$WALK/syncpolicy.json" <<'PY'
import json, subprocess, sys
want = json.load(open(sys.argv[1]))
live = json.loads(subprocess.run(["oc", "get", "application", "group-sync-dashboard", "-n", "openshift-gitops",
                                  "-o", "jsonpath={.spec.syncPolicy}"], check=True, capture_output=True, text=True).stdout)
if live != want:
    subprocess.run(["oc", "patch", "application", "group-sync-dashboard", "-n", "openshift-gitops", "--type", "json",
                    "-p", json.dumps([{"op": "replace", "path": "/spec/syncPolicy", "value": want}])], check=True)
print("syncPolicy:", "restored" if live != want else "already the recorded one")
PY
```

Expect Synced and Healthy, the pod running the head (release-crc.sh verifies it in-pod), and #338's final item:
`resolved shared-rnd` and `resolved shared-qa` both `visibility=remote-sar identity=same-as-host` — `shared-rnd` from
the Secret Step 4 had the lookup write again, `shared-qa` from the default; `api_as kubeadmin /api/whoami` `all` on
`shared-rnd` and `self` on `shared-qa` (its token is expired on purpose; its wide view is Step 7's), `api_as developer
/api/whoami` and `api_as test-user-002 /api/whoami` `self` on both. Then the e2e walk as
kubeadmin — `local-development/e2e-walk/run_walk.sh --base https://group-sync-dashboard.apps-crc.testing --login-user
kubeadmin --out <dir>`, as `reports/2026-09-23_release-walk/` ran it — with the selector and D5's line on each
cluster, committed under `reports/<date>_<slug>/` with the HTML walk document (no PDF) and embedded in #338 against
its Definition of Done.

**Step 11 — rejoin `shared-qa` with a long-lived token** (the operator, 2026-09-24: show the expired case, then fix it).
A ServiceAccount token Secret for the same `shared-qa-poller` carries no `exp`; it is written into `shared-qa`'s Secret
through the tab's own route, so the rejoin needs no restart:

```bash
oc apply -n group-sync-operator -f - <<'YAML'
apiVersion: v1
kind: Secret
metadata:
  name: shared-qa-poller-token
  annotations:
    kubernetes.io/service-account.name: shared-qa-poller
type: kubernetes.io/service-account-token
YAML
until [ -n "$(oc get secret shared-qa-poller-token -n group-sync-operator -o jsonpath='{.data.token}')" ]; do sleep 2; done
printf '{"token": "%s"}' "$(oc get secret shared-qa-poller-token -n group-sync-operator -o jsonpath='{.data.token}' | base64 -d)" \
  | oc exec -i -n "$NS" "$(pod)" -c dashboard -- curl -s -X PUT -H 'X-Forwarded-User: kubeadmin' \
      -H 'Content-Type: application/json' --data-binary @- http://127.0.0.1:8080/api/clusterconfigs/shared-qa/credential; echo
```

Expect the token to carry no `exp`; within one discovery `resolved shared-qa` `visibility=remote-sar
identity=same-as-host`, and the poller polling it with no `auth_failed`; `api_as kubeadmin /api/whoami` and
`api_as jane.smith /api/whoami` `all` on `shared-qa`, developer and test-user-002 `self`; and Step 6's page check, for
`shared-qa` alone, with kubeadmin and jane.smith in its `full` sets. Run Step 10's e2e walk after this step. The one
lifetime such a token has is Kubernetes' legacy-token cleaner, which invalidates a token Secret unused for a year; the
poller uses this one every cycle.

## 6. What changes, for whom, and what it costs

- **A reader a defaulted remote allows sees it wide** — the change itself, and the upgrade note's first item: every
  tab of that remote at the full tier, including the three administrator tabs (Bindings, Operator configs, Kyverno:
  403 before, 200 after), the card's `operator_configs`, and that remote's administrator alerts (its
  `dangling_binding` alert, withheld at self, measured). A remote that states only `identity: same-as-host` moves
  from `self-only` to `remote-sar` and widens the same way.
- **The default flip changes identity too.** A remote that states nothing becomes `identity: same-as-host`: its
  person-scoped views — groups and a group the reader belongs to, users and the reader's own user, logins, cluster
  access, namespaces, user bindings, the two change feeds, and that cluster's own Home — serve the reader's own rows
  under their OpenShift username instead of a 403, whatever the remote answers and when it cannot be asked, and the
  host's Home counts that remote in `elsewhere`, `memberships_total` and "what changed". `identity: none` keeps the old
  behaviour.
- **A lookup-owned Secret serves its stanza's policy and switch** (§3.4): a `saTokenLookup` stanza that states no
  policy moves to `remote-sar` although its Secret was written with `self-only` (the lab's `shared-rnd`), and a
  stanza set to `enabled: false` disables its cluster while the Secret exists — not served, not polled, not reviewed,
  its row `enabled=0`.
- **The critical alert can fire** for any remote whose joining ServiceAccount lacks `list groups` or `create
  subjectaccessreviews`. The ClusterRole `group-sync-operator-helm` installs carries both (§2.9); a ServiceAccount
  joined by hand may not. The pod log names the cluster, the metric does not (no per-cluster label, out of scope);
  the `admin` threshold's tier-check series now counts each remote's checks.
- **A defaulted remote costs a live call** on each viewer's first request per `tierTtlSeconds` from `/api/whoami`,
  `/api/clusters` and `/api/alerts`. An unreachable one costs up to `TIER_CHECK_TIMEOUT_SECONDS` (5 s) per remote,
  one remote after another, to the request that asks — before its hold engages, and again on the first request that
  would call after each hold expires, which is the probe; for as long as the remote stays unreachable and the traffic
  continues, some request pays it every 30 s. Measured with three unreachable defaulted remotes: 15.06 s for a fresh
  viewer's first `/api/whoami`, 0.01 s while held, 15.03 s for the first request after the holds expired (one remote:
  5.07 s, 0.01 s, 5.02 s). §3.10 keeps `/api/clusters` and `/api/alerts` from holding their read snapshot across those
  calls; the request itself still waits.
- **One page burst reads one tier.** The page sends its requests together, and a request for a viewer already being
  resolved rides that resolution, the probe included (§3.5).
- **The tab's create resolves an omitted field by the pair rule** (§3.3): nothing stated writes `remote-sar` +
  `same-as-host`; `identity: none` alone writes `self-only` + `none`; `visibility: self-only` alone writes
  `self-only` + `none`. Main wrote `self-only` / `none` for all three. The page's forms send both fields and start on
  the default pair.
- **A Secret that states a policy keeps it.** A Secret created on the tab before this change carries `self-only` /
  `none` and keeps it; a hand-made Secret that states nothing (the lab's `shared-qa`) takes the default. The upgrade
  note says how to move one: edit its `visibility` and `identity`, or delete both to take the default.
- **D5's line** appears beside the selector for an authenticated reader when restrictions are on (§3.11).
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
- **Review of the revision** (2026-09-23: OB3's third pass on Opus 5.5 at max, then OB1-lite's confirmation pass).
  Accepted — each measured on a copy with the earlier revision's code applied, or checked in the source — and written
  in by OB3 as the writer:
  - F1, OB3: a follower that steals a stuck leader's slot never consulted the hold and called inside one — superseded
    by N2's design (below), which closes it;
  - F2, OB3: an ownership flip alone changed the served pair and logged no `cluster-resolved` line; `token_source`
    now ends `_cluster_shape`'s tuple (§3.4);
  - F3, OB3: a lookup stanza set to `enabled: false` stayed served, polled and reviewed while its Secret existed; the
    owned branch takes `enabled=c.enabled and found.enabled`, and the served `enabled` goes on the row and on the
    line (§3.4);
  - F6, OB3: the default flip put every unstated remote's review inside the read snapshot of `/api/clusters` and
    `/api/alerts`; the smallest behaviour-preserving change is a FastAPI dependency that decides first (§3.10);
  - F7, OB3: the create request defaulted field by field, refusing `identity: none` alone (422) and giving
    `self-only` the identity `same-as-host`; it resolves the pair with `remote_policy` (§3.3);
  - D3, OB3: §6 omitted behaviour changes (the administrator tabs and alerts of an allowed reader, Namespaces and the
    remote's own Home, `identity: same-as-host` alone) and understated the cost, which is serial across remotes and
    recurs after every hold; §6 is rewritten with the measurements;
  - M1, OB3: §5 could not be executed — the tab does not rotate a CA or a URL, a values entry has no
    `cluster-resolved` line, disabling `shared-rnd` did not disable it, the kubeadmin walk omitted `shared-qa`, and
    the mock does bind an auditor Group (its own); §5 is now a procedure with commands and the measured personas;
  - M2, OB3, and N1, OB1-lite: the code blocks raised NameError where the prose put them; every import is in §7;
  - N2, OB1-lite: the hold, checked before single-flight, answered the probe's own sibling requests self while the
    probe returned `all`, and the steal path skipped it (the same hole as F1);
  - N3, OB1-lite: the mock has no `explain` endpoint; the route is `POST /_mock/sar-probe`;
  - N4, OB1-lite: §3.7 said `docs/ACCESS_CONTROL.md` §11 named the auditor objects, and it did not; §3.8 now names
    the three sentences of §11 that this change makes false, and §7 rewrites them.
- **Decided: N2's gate over F1's guard.** Both close the steal-path hole. F1 kept the hold ahead of single-flight and
  added a guard to the steal path, so the probe's own sibling requests still answered self while the probe returned
  `all` — one page burst read mixed tiers (measured: a probe `all`, its four siblings `self`). N2 gates only a request
  that is about to CALL, through one `_may_call(now)` under the lock, used by the leader and by the stealer; riders
  get the probe's answer, so there are no mixed tiers within one page burst. Re-measured on the written blocks with
  OB3's hold harness and OB1-lite's two tests: no call during a hold for a stuck or stalled leader's follower, the
  probe's siblings all `all`, and no hole found.
- **Operator decision, 2026-09-23: D5 is in scope** (the go-ahead relayed by the coordinator; D4 stays out). The line's
  words follow the coordinator's table; the `remote-sar` / `self` line names both possible causes because the wire
  does not tell them apart; `self-only` with `identity: none` gets the refusal card's words, because "your own rows"
  would be false there; the host shows the `inherit` line, which is true of it, because the wire does not mark the
  host and an API change is out of scope (§3.11).
- **Writing the blocks changed the design text in six places**, each recorded where it applies: S4c's rungs move to
  0.33.0 / 0.54.0 (§3.9 — `tests/test_specs_index.py` holds an unbegun spec above the tree, and this change takes
  0.32.0 / 0.53.0); "How to read this spec" is added, because `tests/test_specs_index.py` reads a spec's header up to
  that heading, and without it a block carrying another file's `Status` or `Version on release` row would be read as
  this spec's; `fleetlookup.py` needs no block (§3.9); the Argo CD Application declares only `dashboard`, so the lab
  makes `shared-rnd` resolve under Argo CD by having the lookup write its Secret again in a Helm round (§5); Helm mode
  deletes the Application, so the recorded sync policy is restored on the one `--argocd` creates, after it (§5); the
  restricted browser fixtures state `identity: none` on their remotes instead of asking a made-up API (§4).
- **Review of the blocks** (the 154 of `6b65a4e`; Codex at xhigh, Grok, OB1-lite on Opus 5.5 high; OB3, their writer,
  did not review them). Grok: everything it could read confirmed, no finding kept. Codex and OB1-lite applied the
  blocks and ran the suites (Codex 4900 passed, its two errors its sandbox's refused socket; OB1-lite 4902 non-browser
  and 593 browser passed, and 19 mutations each caught by a new test for its named reason). Accepted, written as the
  corrections at the end of §7 and each re-checked against the source before it was taken:
  - thirteen per-cluster routes decided a `remote-sar` tier inside their read snapshot — `@tier_first` (OB1-lite F1);
  - `/api/alerts` asked a remote its walk skips — `alert_scopes` on the handler's own predicate (OB1-lite F2, Codex
    B4; OB1-lite's version, which reads the loop's predicate rather than `is_served`);
  - a retired or disabled cluster's resolver, and the credential in it, was kept for the life of the process — every
    lookup drops the unaskable (OB1-lite N3);
  - the public wording "asked at most once per 30 s, whatever the traffic" left out the first in-flight burst — the
    chart README, `values.yaml`, the CHANGELOG (Codex B8/B9) and `kube.py`'s docstring (the orchestrator, from the
    same sweep);
  - the design document and its figures still called D1 and D5 unbuilt — Codex's three caption and table blocks, and
    the orchestrator's for the summary, the two "once D1 lands" lines, the page's cards, lede, captions and drawn
    footers; `docs/diagrams/render.py` is added so the figures are re-rendered from written instructions (§7);
  - §5's step 4 read `shared-rnd`'s Secret before the lookup wrote it again (OB1-lite F4).
  Rejected: Codex's retry-the-snapshot loop for a row published mid-request (§3.10: a rare window, one decision of
  two bounded calls, exception-driven control flow in two handlers); Codex's regression file (five of its seven tests
  match prose or execute the spec's own text — prose tests are refused on every PR here — and of its two behavioural
  tests one is OB1-lite's alerts test again and one tests the rejected loop); Codex's B10 request for per-test
  red/green proof, which OB1-lite's mutation run answers per mechanism (each of its 19 mutations caught by a new
  test), not per test; Codex's B11 on step 7's restore — measured by OB3's confirmation pass with `oc` 4.22.13 against
  a recording API stand-in, `oc replace` of an object with no `resourceVersion` reads the live one and sends it (the
  PUT carried the live 4242: `replaced`), so the restore that strips the saved, stale one stands as first written.
- **Confirmation pass on the corrections** (OB3 on `890f04c`): R1–R4 hold as measured; its findings, written as nine
  more blocks and text edits: the design document and the diagram page still called D5 a proposal in Figure 3's page
  caption and said both lab remotes are `self-only`, and §8/§9 did not say D1 is built; `docs/ACCESS_CONTROL.md` §11
  and §3.5 said no request calls a held remote, while one already in flight may finish its attempt; §3.1's quote and
  §3.5's no longer matched §7, and `kube.py`'s docstring had a 206-character line; §3.1 said a resolver never keeps a
  retired cluster's credential; `docs/diagrams/render.py` exited 0 with its web fonts unreachable.
- **Review of the confirmation pass** (`12d9d8d`; Codex on `gpt-6-astra` at high effort, and OB1-lite). Accepted:
  OB1-lite's three — §3.5's and `docs/ACCESS_CONTROL.md`'s hold sentence said no request that begins during the hold
  calls, while a request that arrived during it and outwaited a stuck resolution for its viewer may be the one probe
  after it expires (measured by both reviewers: a follower begun during the hold called once it expired, at t=1032
  from t=1010 in OB1-lite's run and at t=1031 from t=1029 in Codex's); §3.1's retention
  sentence, since a cluster still askable whose credential changed keeps its old resolver until that cluster is next
  looked up (measured: `east` kept `token-one` across a lookup of `west`); and `shared-qa` "has always been
  `self-only`". Codex's C6: the renderer watched only the two theme pages, so a failure on the 375 px page, where
  the sideways-scroll check is measured, exited 0 (measured with a Playwright stand-in; its test is the new
  `test_diagram_render.py`); one shared list also fails a theme-page request that dies after the load check, which
  the per-page list dropped (OB1-lite, a lazily loaded image: exit 0 before, 1 after). Codex's C7 on the facts: the design document's status line, D2's "(today)", D6's "until
  D1 ships" and "right now", and the page's D5 card, which called D5 built without saying that the narrowed line
  cannot tell a denial from a remote that could not be asked — each corrected in the fewest words, the options column
  kept as the record of what was proposed. Rejected: Codex's C3 code change, a `began_held` flag so that a request
  that arrived held never probes. The budget the hold exists for — at most one call per hold per resolver, whatever
  the traffic — holds without it (Codex's own measurement: 11 calls in 60 s, one probe at 35.5 s), so the flag would
  add state to make an over-stated sentence true; the sentence is corrected instead. Codex's five documentation
  contract tests: they assert phrases in the documents, which is a prose test. Codex's placement of the renderer
  test in `test_remote_sar_default.py`: it tests the renderer, so it gets its own file.
- **Confirmation of `8460257`** (OB1-lite): the renderer, its test and the counts hold, and its run of a held
  arrival under 50 viewers' traffic kept one call per 30 s hold, the held arrival being that hold's probe, which
  confirms the `began_held` rejection. Two wording corrections applied: the D5 line quoted on the page and in the
  design document is a `remote-sar` cluster's, not every remote's, and each reviewer's hold timings are its own.
- **The lab walk of #342** (2026-09-24, head `8e50ff8`; its record is on #338). Three corrections to §5 from it: Step 6's
  page check could pass on the previous cluster's text, so it opens a fresh page per reader and cluster; `shared-qa`'s
  token is expired on purpose (the operator), so Steps 6 and 10 expect `self` there for every reader; and Step 7's
  in-cluster row asked for a URL the reader refuses by design, so it is removed — an in-cluster name is the
  controller's endpoint, never a remote's (the operator). Step 3 also found that `release-crc.sh`'s Helm handover was
  refused once the chart version moved; #343 fixed it. Step 11 is added: once the expired case is shown, `shared-qa`
  is rejoined with a long-lived token (the operator). The host guard refuses only the exact string
  `https://kubernetes.default.svc`, so other spellings of the in-cluster endpoint pass it. Examined after the walk
  (2026-09-24) and closed as not a gap: a Secret never names the pod's token or CA file (`local-development/gsd/clusterconfig/parser.py` sets neither), so whatever URL it gives, the cluster is read with the Secret's own credential. Another spelling only lists the host again under that credential, as `shared-rnd` does on purpose.

## 7. Implementation blocks

221 blocks in 47 files — 41 edited, 6 created. The first 154 are the implementation as written; the last 67, under
"Corrections from the review of the blocks", apply on top of them. In application order: the Python (`kube.py`, `config.py`, `api.py`,
`poller.py`, then `clusterconfig/registry.py`, `reader.py`, `parser.py` and `writer.py`; `fleetlookup.py` needs none,
§3.9), the version (`gsd/__init__.py`, `pyproject.toml`), the page, the chart, `environments/crc.yaml`, the docs, and
the tests. Each block's Old text is sliced from the file as it stands after the earlier blocks for that file, at the
hunk positions git's own diff chooses (its indent heuristic keeps a hunk to whole statements), with the fewest context
lines that make it occur exactly once; blocks whose spans would touch are one block. Each file's lead-in names the §3
subsections its blocks implement. Applied to a clean `b8e75b0`, they reproduce the implemented copy byte for byte.

#### `local-development/gsd/kube.py`

§3.1 (the imports and `RemoteTierResolvers`), §3.5 (the hold: the constant, the constructor argument, the gate `_may_call` in the leader and the stealer branch, `_start_hold` before `_note`, the clear on success) and §3.6 (the review's error text redacted before it is truncated).

<!-- block: local-development/gsd/kube.py | edit -->

```python
from .config import VISIBILITY_TIER_TTL_DEFAULT, ClusterConfig, ConfigError
```

```python
from .config import (
    IDENTITY_SAME_AS_HOST, VISIBILITY_REMOTE_SAR, VISIBILITY_TIER_TTL_DEFAULT, ClusterConfig, ConfigError, Settings,
    remote_policy,
)
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
TierResolver.tier_for), so recovery costs nothing beyond the next request.
```

```python
TierResolver.tier_for), so recovery costs nothing beyond the next request — for the host's resolvers;
a remote's holds a failing remote instead (REMOTE_FAILURE_HOLD_SECONDS).
"""

REMOTE_FAILURE_HOLD_SECONDS = 30.0
"""How long a remote-sar cluster's resolver stops asking after a failed resolution (SPEC_D2b §3.5).

A remote that fails — unreachable, a 401, a 403 because its joining ServiceAccount may not list groups
or create reviews — would otherwise be asked again by every viewer's first request, each paying up to
TIER_CHECK_TIMEOUT_SECONDS per call, one remote after another. Held, it is asked at most once per this
many seconds whatever the traffic: the first request that would call after the hold expires is the one
probe. Under the 60 s tier TTL and far under the alert's 15 minutes, so a remote that keeps failing under
traffic still records a failed check every thirty seconds and GroupSyncDashboardVisibilityChecksFailing
stays true. A constant, like the timeout, until an operator needs to tune it.
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
                raise ClusterError(UNREACHABLE, f"{type(exc).__name__}: {exc}") from exc
```

```python
                # Redacted as _get does (SPEC_D2b §3.6): an httpx error can carry the request URL.
                raise ClusterError(UNREACHABLE, self._redact(f"{type(exc).__name__}: {exc}")) from exc
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
                UNREACHABLE, f"HTTP {response.status_code} on {SAR_API}: {response.text[:200]}"
```

```python
                # REDACT BEFORE TRUNCATING, as _get does (SPEC_D2b §3.6): a ServiceAccount JWT is longer
                # than the window, and redact_text replaces only whole spellings.
                UNREACHABLE, f"HTTP {response.status_code} on {SAR_API}: {self._redact(response.text)[:200]}"
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
    contract as the resolver's own error path.
```

```python
    contract as the resolver's own error path.

    A FAILING REMOTE IS HELD (SPEC_D2b §3.5). A resolver built with failure_hold_seconds > 0 — one
    per remote-sar cluster, from RemoteTierResolvers — stops asking after a failed resolution: until
    the hold expires every request that would CALL answers self without calling, and the first one
    after it expires is the single probe, re-arming the hold before it calls. The gate is `_may_call`,
    passed by a leader and by a follower that steals a stuck slot alike; a request for a viewer already
    being resolved rides that resolution, the probe included, so one page's burst gets one answer.
    The host's resolvers pass no hold and behave exactly as before.
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
        observe: Callable[[str], None] | None = None,
```

```python
        observe: Callable[[str], None] | None = None,
        failure_hold_seconds: float = 0.0,
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
        self._ttl = ttl_seconds
```

```python
        self._ttl = ttl_seconds
        # SPEC_D2b §3.5: a remote's resolver holds a failing remote for this many seconds
        # (REMOTE_FAILURE_HOLD_SECONDS); zero — the host's resolvers, which do not pass it — asks again on
        # every request, as before. `_held_until` is 0.0 when no hold runs; both are read and written
        # under _lock.
        self._hold = failure_hold_seconds
        self._held_until = 0.0
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
            if leading:
```

```python
            if leading:
                if not self._may_call(now):
                    return TIER_SELF
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
                # STEAL THE SLOT, and this is the fix for a real wedge rather than caution.
```

```python
                if not self._may_call(time.monotonic()):
                    # A stealer calls the remote as a leader does, so a held remote is not asked by it
                    # either: a failure elsewhere armed the hold while this request waited (SPEC_D2b §3.5).
                    return TIER_SELF
                # STEAL THE SLOT, and this is the fix for a real wedge rather than caution.
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
    def _note(self, outcome: str) -> None:
```

```python
    def _may_call(self, now: float) -> bool:
        """Whether a request about to CALL the remote may (SPEC_D2b §3.5). Called under _lock, and only by
        a request that would call — a leader, or a follower stealing a stuck slot — so a request for a
        viewer already being resolved rides that resolution, the probe included. False while a hold runs;
        the first caller after it expires is the one probe and re-arms the hold BEFORE it calls, so every
        other caller answers self until the probe's outcome ends the hold or restarts it. Always True for
        a resolver built without a hold."""
        if not (self._hold and self._held_until):
            return True
        if now < self._held_until:
            return False
        self._held_until = now + self._hold
        return True

    def _start_hold(self) -> None:
        """A failed resolution holds a remote's resolver (SPEC_D2b §3.5): no call until the hold expires."""
        if self._hold:
            with self._lock:
                self._held_until = time.monotonic() + self._hold

    def _note(self, outcome: str) -> None:
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
            # forbidden), which is exactly the metric's failure enum.
```

```python
            # forbidden), which is exactly the metric's failure enum. The hold is armed FIRST
            # (SPEC_D2b §3.5), for the reason the success path caches first: the observe callback is
            # not bounded, and a stalled one must not leave a failing remote open to every viewer.
            self._start_hold()
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
            self._note("error")
```

```python
            self._start_hold()
            self._note("error")
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
            # CACHE FIRST, REPORT SECOND. `_note` calls out to the observe seam, and while it
```

```python
            if self._hold:
                self._held_until = 0.0      # the remote answered: the hold is over for every viewer
            # CACHE FIRST, REPORT SECOND. `_note` calls out to the observe seam, and while it
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
def _condition(obj: dict, wanted: str) -> dict | None:
```

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

    def __init__(self, settings: Settings, make: Callable[[ClusterConfig], TierResolver]):
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


def _condition(obj: dict, wanted: str) -> dict | None:
```

#### `local-development/gsd/config.py`

§3.1 (`connection_fingerprint` and its two imports), §3.2 (`remote_policy`, `Settings.cluster_policy`, the loader's pairing rule), §3.4 (the `token_source` field) and §3.8 (the `identity` comment).

<!-- block: local-development/gsd/config.py | edit -->

```python
import logging
```

```python
import hashlib
import json
import logging
```

<!-- block: local-development/gsd/config.py | edit -->

```python
# Whether the host's username means the same person on this cluster. A claim about the two
# clusters' identity providers, which this chart cannot check — so it is stated, never assumed.
```

```python
# Whether the reader's OpenShift username — the `User` object's name, which the host authenticated — names
# the same person on this cluster. Readers are matched by that name on every cluster (design D3); `none` says
# the name is nobody here, so nothing on this cluster is keyed by it.
```

<!-- block: local-development/gsd/config.py | edit -->

```python
class ConfigError(Exception):
```

```python
def remote_policy(visibility: str | None, identity: str | None) -> tuple[str, str]:
    """A non-host cluster's (visibility, identity) with the defaults resolved (SPEC_D2b §3.2, design D2).

    A remote that states nothing is asked about the reader itself: remote-sar + same-as-host. `identity: none`
    says the host's username is nobody on that cluster, so it cannot be asked about them: with no visibility
    stated it keeps self-only, as before. Resolution only — the explicit pair remote-sar + none is refused
    where it is READ (the loader, the Secret parser, the chart), not here."""
    if visibility is None:
        visibility = VISIBILITY_SELF_ONLY if identity == IDENTITY_NONE else VISIBILITY_REMOTE_SAR
    if identity is None:
        identity = IDENTITY_SAME_AS_HOST if visibility == VISIBILITY_REMOTE_SAR else IDENTITY_NONE
    return visibility, identity


class ConfigError(Exception):
```

<!-- block: local-development/gsd/config.py | edit -->

```python
    # (its viewer IS a host identity), every other cluster is self-only/none. Resolved there and
    # not here so a hand-built Settings and a chart-rendered one agree on what a second cluster
    # serves by default — the direction that matters is that it never widens.
```

```python
    # (its viewer IS a host identity), every other cluster by remote_policy — remote-sar/same-as-host
    # when it states nothing, self-only/none when it states only `identity: none` (SPEC_D2b §3.2).
    # Resolved there and not here so a hand-built Settings and a chart-rendered one agree on what a
    # second cluster serves by default: its own RBAC decides, and every failure is the self tier.
```

<!-- block: local-development/gsd/config.py | edit -->

```python
    ldap_connection_bootstrap: str | None = None
```

```python
    ldap_connection_bootstrap: str | None = None
    # A Secret-sourced cluster's `groupsync-dashboard.io/token-source` annotation, recorded by the reader
    # (SPEC_D2b §3.4). When it names the credential kind of the values stanza of the same name, the Secret
    # is the lookup's own write for that stanza: ClusterRegistry.merge keeps its credential and serves the
    # stanza's policy and `enabled`. None for a values entry and for a Secret that carries no annotation.
    token_source: str | None = field(default=None, repr=False)
```

<!-- block: local-development/gsd/config.py | edit -->

```python
        return _trusted_ca_context() or True

```

```python
        return _trusted_ca_context() or True

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

<!-- block: local-development/gsd/config.py | edit -->

```python
        return (cluster.visibility or VISIBILITY_SELF_ONLY,
                cluster.identity or IDENTITY_NONE)
```

```python
        return remote_policy(cluster.visibility, cluster.identity)
```

<!-- block: local-development/gsd/config.py | edit -->

```python
        elif cluster.visibility == VISIBILITY_REMOTE_SAR and (cluster.identity or IDENTITY_NONE) != IDENTITY_SAME_AS_HOST:
```

```python
        elif cluster.visibility == VISIBILITY_REMOTE_SAR and cluster.identity == IDENTITY_NONE:
            # Only the EXPLICIT pair (SPEC_D2b §3.2): an omitted identity resolves to same-as-host beside
            # remote-sar, and `identity: none` stated alone resolves to self-only.
```

<!-- block: local-development/gsd/config.py | edit -->

```python
                f"{where}: visibility remote-sar needs identity: same-as-host — the review names "
                f"the host's username on this cluster, which only means something if the two "
                f"clusters share an identity provider"
```

```python
                f"{where}: visibility remote-sar needs identity: same-as-host — the review names the "
                f"reader's OpenShift username on this cluster; set same-as-host or leave identity out"
```

#### `local-development/gsd/api.py`

§3.1 (the pool replaces the start-up loop), §3.3 (`_create_request` resolves an omitted pair with `remote_policy`) and §3.10 (`served_scopes`, a dependency of `/api/clusters` and `/api/alerts`).

<!-- block: local-development/gsd/api.py | edit -->

```python
from fastapi import FastAPI, HTTPException, Query, Request
```

```python
from fastapi import Depends, FastAPI, HTTPException, Query, Request
```

<!-- block: local-development/gsd/api.py | edit -->

```python
    VISIBILITY_REMOTE_SAR, VISIBILITY_SELF_ONLY, Settings, load_settings,
```

```python
    VISIBILITY_REMOTE_SAR, VISIBILITY_SELF_ONLY, Settings, load_settings, remote_policy,
```

<!-- block: local-development/gsd/api.py | edit -->

```python
from .kube import TIER_ALL, TIER_SELF, ClusterClient, TierResolver
```

```python
from .kube import REMOTE_FAILURE_HOLD_SECONDS, TIER_ALL, TIER_SELF, ClusterClient, RemoteTierResolvers, TierResolver
```

<!-- block: local-development/gsd/api.py | edit -->

```python
    remote_resolvers: dict[str, TierResolver] = {}
    if settings.view_restrictions_enabled:
        for c in settings.clusters:
            if not c.enabled or c is local_cluster:
                continue
            if settings.cluster_policy(c.name)[0] != VISIBILITY_REMOTE_SAR:
                continue
            remote_resolvers[c.name] = TierResolver(
                c,
                verb=settings.visibility_admin_sar_verb,
                resource=settings.visibility_admin_sar_resource,
                api_group=settings.visibility_admin_sar_api_group,
                namespace=settings.visibility_admin_sar_namespace,
                subresource=settings.visibility_admin_sar_subresource,
                ttl_seconds=float(settings.visibility_tier_ttl_seconds),
                observe=functools.partial(signals.note_tier_check, "admin"),
            )
```

```python
    #
    # Found or built PER REQUEST (SPEC_D2b §3.1), from the cluster's CURRENT configuration — values entry or
    # Secret — rather than once here: a Secret-declared cluster appears at runtime, and a rotated token, CA or
    # URL reaches a resolver only as a new configuration. Each resolver holds a failing remote for
    # REMOTE_FAILURE_HOLD_SECONDS; the host's resolvers above hold nothing.
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

<!-- block: local-development/gsd/api.py | edit -->

```python
    def vouches_for_host_identity(cluster_id: str) -> bool:
```

```python
    def served_scopes(request: Request) -> dict[str, str]:
        """This reader's decision for every served cluster, made BEFORE a handler's read snapshot opens
        (SPEC_D2b §3.10). FastAPI resolves a dependency before it calls the endpoint, and the snapshot is
        opened by the endpoint's @consistent wrapper. Under remote-sar a decision is a group list and a
        SubjectAccessReview on that cluster, up to TIER_CHECK_TIMEOUT_SECONDS each, and a snapshot held
        across a network call pins the WAL read-mark (store.read_snapshot). The rows are the ones the
        fleet handlers walk; a row that appears between this read and the handler's snapshot is decided
        inline, as before, so nothing is widened, dropped or decided twice."""
        return {row["id"]: viewer_scope(request, row["id"])[1] for row in store.clusters() if is_served(row["id"])}

    def vouches_for_host_identity(cluster_id: str) -> bool:
```

<!-- block: local-development/gsd/api.py | edit -->

```python
        _reject_unknown("tls", tls, _TLS_KEYS)
```

```python
        _reject_unknown("tls", tls, _TLS_KEYS)
        # One rule for an omitted field, the one discovery applies to the Secret this request writes
        # (SPEC_D2b §3.2): nothing is remote-sar + same-as-host, and `identity: none` alone is
        # self-only — never the refused remote-sar + none.
        visibility, identity = remote_policy(str(body.get("visibility") or "").strip() or None,
                                             str(body.get("identity") or "").strip() or None)
```

<!-- block: local-development/gsd/api.py | edit -->

```python
            visibility=str(body.get("visibility") or "self-only"), identity=str(body.get("identity") or "none"),
```

```python
            visibility=visibility, identity=identity,
```

<!-- block: local-development/gsd/api.py | edit -->

```python
    def list_clusters(request: Request) -> list[dict]:
```

```python
    def list_clusters(request: Request, scopes: dict[str, str] = Depends(served_scopes)) -> list[dict]:
```

<!-- block: local-development/gsd/api.py | edit -->

```python
            _, scope = viewer_scope(request, row["id"])
```

```python
            scope = scopes[row["id"]] if row["id"] in scopes else viewer_scope(request, row["id"])[1]
```

<!-- block: local-development/gsd/api.py | edit -->

```python
    def list_alerts(request: Request) -> dict:
```

```python
    def list_alerts(request: Request, scopes: dict[str, str] = Depends(served_scopes)) -> dict:
```

<!-- block: local-development/gsd/api.py | edit -->

```python
            _, cscope = viewer_scope(request, cluster_id)
```

```python
            cscope = scopes[cluster_id] if cluster_id in scopes else viewer_scope(request, cluster_id)[1]
```

#### `local-development/gsd/poller.py`

§3.2 and §3.4: `_cluster_shape` normalises with `remote_policy` and ends with `token_source`; the `cluster-resolved` line and the cluster row carry the served pair and the served `enabled`.

<!-- block: local-development/gsd/poller.py | edit -->

```python
from .config import CREDENTIAL_LOOKUP, IDENTITY_NONE, VISIBILITY_SELF_ONLY, ClusterConfig, ConfigError, Settings
```

```python
from .config import CREDENTIAL_LOOKUP, ClusterConfig, ConfigError, Settings, remote_policy
```

<!-- block: local-development/gsd/poller.py | edit -->

```python
    are normalised — and to the words `Settings.cluster_policy` SERVES, not the words the first fix
    printed: every cluster in this set is Secret-sourced, so an omitted visibility is `self-only`,
```

```python
    are normalised — by the rule `Settings.cluster_policy` SERVES for a remote, `remote_policy`
    (SPEC_D2b §3.2), not the words the first fix printed: every cluster in this set is Secret-sourced,
```

<!-- block: local-development/gsd/poller.py | edit -->

```python
    so an edit to one is a change a reader should see and cannot chatter on its own.
```

```python
    so an edit to one is a change a reader should see and cannot chatter on its own.

    OWNERSHIP TOO (SPEC_D2b §3.4): a Secret the lookup wrote for a values stanza serves that stanza's
    policy and `enabled`, an unowned one its own, so a `token-source` annotation added or removed
    changes what is served with no other field moving.
```

<!-- block: local-development/gsd/poller.py | edit -->

```python
        cluster.visibility or VISIBILITY_SELF_ONLY, cluster.identity or IDENTITY_NONE, cluster.enabled,
```

```python
        *remote_policy(cluster.visibility, cluster.identity), cluster.enabled,
```

<!-- block: local-development/gsd/poller.py | edit -->

```python
        hashlib.sha256(secret_material.encode()).hexdigest()[:12],
```

```python
        hashlib.sha256(secret_material.encode()).hexdigest()[:12],
        cluster.token_source,
```

<!-- block: local-development/gsd/poller.py | edit -->

```python
            mode = c.tls_mode
```

```python
            mode = c.tls_mode
            # The SERVED policy and switch, read through the merge the registry was just given: an owned
            # Secret keeps its own frozen copy, and its stanza's are the ones served (SPEC_D2b §3.4).
            visibility, identity = self.settings.cluster_policy(c.name)
            served = self.settings.cluster(c.name) or c
```

<!-- block: local-development/gsd/poller.py | edit -->

```python
                  visibility=c.visibility or VISIBILITY_SELF_ONLY, identity=c.identity or IDENTITY_NONE,
                  enabled=str(c.enabled).lower())
```

```python
                  visibility=visibility, identity=identity,
                  enabled=str(served.enabled).lower())
```

<!-- block: local-development/gsd/poller.py | edit -->

```python
        for cluster in clusters:
            self.store.upsert_cluster(cluster.name, cluster.api_url, cluster.enabled,
```

```python
        for cluster in clusters:
            # The SERVED switch (SPEC_D2b §3.4): a lookup stanza set to `enabled: false` disables the
            # Secret it owns, and a row left enabled=1 would keep its frozen snapshot raising alerts (#96).
            served = self.settings.cluster(cluster.name) or cluster
            self.store.upsert_cluster(cluster.name, cluster.api_url, served.enabled,
```

#### `local-development/gsd/clusterconfig/registry.py`

§3.4: the whole `merge`, and its import.

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->

```python
import threading
```

```python
import dataclasses
import threading
```

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->

```python
        """The values list with the discovered clusters laid over it: a Secret shadows a values entry
        of the same name (C2 — the shadow is reported by the reader as a finding); the host, values[0]
        enabled, is never replaced (the parser refuses a Secret naming it, so nothing here can)."""
```

```python
        """The values list with the discovered clusters laid over it: a Secret shadows a values entry of the same
        name (C2 — the shadow is reported by the reader as a finding); the host, values[0] enabled, is never replaced
        (the parser refuses a Secret naming it, so nothing here can). A Secret the lookup wrote FOR a mode stanza
        (its token-source is that stanza's credential kind — the reader's "ours") keeps the credential and takes
        the stanza's policy and switch, so an edit of the stanza's visibility, a change of default, or the stanza
        set to `enabled: false` reaches what is served (SPEC_D2b §3.4); an unowned Secret still wins wholesale
        (SPEC_S3). A Secret with no values entry is appended."""
```

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->

```python
            out.append(discovered.pop(c.name, c))
```

```python
            found = discovered.pop(c.name, None)
            if found is None:
                out.append(c)
            elif c.connection_mode is not None and found.token_source == c.credential_kind:
                # Either side may disable it: the lookup writes the stanza's `enabled` into the Secret.
                out.append(dataclasses.replace(found, visibility=c.visibility, identity=c.identity,
                                               enabled=c.enabled and found.enabled))
            else:
                out.append(found)
```

#### `local-development/gsd/clusterconfig/reader.py`

§3.3 (the two fix sentences) and §3.4 (the ownership recorded on every accepted Secret).

<!-- block: local-development/gsd/clusterconfig/reader.py | edit -->

```python
from ..config import ClusterConfig
```

```python
import dataclasses

from ..config import ClusterConfig
```

<!-- block: local-development/gsd/clusterconfig/reader.py | edit -->

```python
    "visibility-invalid": "visibility must be inherit, self-only or hidden",
    "identity-invalid": "identity must be none or same-as-host",
```

```python
    "visibility-invalid": "visibility must be inherit, self-only, hidden or remote-sar",
    "identity-invalid": "identity must be none or same-as-host, and remote-sar needs same-as-host",
```

<!-- block: local-development/gsd/clusterconfig/reader.py | edit -->

```python
        secret_name = parsed.source.split(":", 1)[1]
```

```python
        secret_name = parsed.source.split(":", 1)[1]
        # The ownership the check below makes, recorded on the config itself (SPEC_D2b §3.4): the merge
        # serves a stanza's policy over the Secret the lookup wrote for it, and only that Secret.
        parsed = dataclasses.replace(parsed, token_source=token_source.get(secret_name))
```

#### `local-development/gsd/clusterconfig/parser.py`

§3.3: every visibility accepted; only the explicit pair refused.

<!-- block: local-development/gsd/clusterconfig/parser.py | edit -->

```python
    VISIBILITY_REMOTE_SAR, ClusterConfig, valid_bootstrap_username,
```

```python
    IDENTITY_NONE, VISIBILITY_REMOTE_SAR, ClusterConfig, valid_bootstrap_username,
```

<!-- block: local-development/gsd/clusterconfig/parser.py | edit -->

```python
    visibility = (data.get("visibility") or "").strip() or None
    allowed = tuple(v for v in CLUSTER_VISIBILITIES if v != VISIBILITY_REMOTE_SAR)
    if visibility is not None and visibility not in allowed:
        # remote-sar needs a TierResolver built at app start for that cluster (api.py's remote
        # resolvers); a cluster that appears at runtime has none, so viewer_scope would answer self
        # for every reader — it fails CLOSED ("a remote cluster with no resolver is a remote cluster
        # nobody may see wide"), which would make remote-sar silently mean self-only. D1 of
        # docs/DESIGN_remote_cluster_access.md builds them at discovery; until then the Secret says
        # inherit, self-only or hidden.
        return finding("visibility-invalid", f"data.visibility must be one of {', '.join(allowed)}"
                       + (" (remote-sar for a Secret-sourced cluster is S2)" if visibility == VISIBILITY_REMOTE_SAR else ""))
```

```python
    # Every visibility, remote-sar included (SPEC_D2b §3.3): the resolver is found per request from the
    # cluster's current configuration, so a Secret-declared cluster is asked like a values one.
    visibility = (data.get("visibility") or "").strip() or None
    if visibility is not None and visibility not in CLUSTER_VISIBILITIES:
        return finding("visibility-invalid", f"data.visibility must be one of {', '.join(CLUSTER_VISIBILITIES)}")
```

<!-- block: local-development/gsd/clusterconfig/parser.py | edit -->

```python
        return finding("identity-invalid", f"data.identity must be one of {', '.join(CLUSTER_IDENTITIES)}")
```

```python
        return finding("identity-invalid", f"data.identity must be one of {', '.join(CLUSTER_IDENTITIES)}")
    if visibility == VISIBILITY_REMOTE_SAR and identity == IDENTITY_NONE:
        return finding("identity-invalid", "data.identity none cannot pair with visibility remote-sar: the review "
                                           "names the reader's OpenShift username on this cluster; set same-as-host "
                                           "or leave identity out")
```

#### `local-development/gsd/clusterconfig/writer.py`

§3.3: `CreateRequest`'s defaults.

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->

```python
    visibility: str = "self-only"
    identity: str = "none"
```

```python
    visibility: str = "remote-sar"     # the default pair for a remote that states nothing (SPEC_D2b §3.2)
    identity: str = "same-as-host"
```

#### `local-development/gsd/__init__.py`

§3.9: the application version.

<!-- block: local-development/gsd/__init__.py | edit -->

```python
__version__ = "0.31.0"
```

```python
__version__ = "0.32.0"
```

#### `local-development/pyproject.toml`

§3.9: the application version's source of truth.

<!-- block: local-development/pyproject.toml | edit -->

```toml
version = "0.31.0"
```

```toml
version = "0.32.0"
```

#### `local-development/gsd/static/index.html`

§3.3 (both form defaults, the option list, the `CC_VIS_MEAN` and `CC_ID_MEAN` hints) and §3.11 (D5: `scopeWhy` and the line beside the selector).

<!-- block: local-development/gsd/static/index.html | edit -->

```html
                clusterForm: { name: "", server: "", token: "", caMode: "caData", caPem: "", visibility: "self-only", identity: "none",
```

```html
                clusterForm: { name: "", server: "", token: "", caMode: "caData", caPem: "", visibility: "remote-sar", identity: "same-as-host",
```

<!-- block: local-development/gsd/static/index.html | edit -->

```html
  return scopeFor(w, null) !== "all";
}
```

```html
  return scopeFor(w, null) !== "all";
}
/* D5 (SPEC_D2b §3.11): WHICH RULE decided this reader's view of the selected cluster, read off whoami's
   `visibility.clusters[id]` = {policy, identity, scope} and never derived. The wire does not tell a remote's
   "denied" from "could not be asked" (that is D4's field, not built), so that line names both; it does not mark
   the host either, so `inherit` says "the host decides", which is as true of the host as of a remote that
   inherits. Empty with restrictions off, with no authenticated identity, and with no cluster selected. */
function scopeWhy(w, cluster) {
  const vis = w && w.authenticated && w.visibility;
  if (!vis || vis.enabled === false || !cluster) return "";
  const c = vis.clusters && vis.clusters[cluster];
  if (!c) return "";
  if (c.policy === "inherit") return "The host decides your view of this cluster.";
  if (c.policy === "remote-sar") {
    return c.scope === "all" ? "This cluster's own RBAC gives you the full view."
      : "This cluster's own RBAC shows your own rows, or could not be asked.";
  }
  if (c.policy === "self-only") {
    return c.identity === "same-as-host" ? "This cluster is self-only: everyone sees their own rows."
      : "This cluster is self-only and does not treat your identity as its own.";
  }
  return "";
}
```

<!-- block: local-development/gsd/static/index.html | edit -->

```html
  const fleetWide = view.page === "usage" || view.page === "kpi";
```

```html
  const fleetWide = view.page === "usage" || view.page === "kpi";
  // D5 (SPEC_D2b §3.11): the rule that decided the selected cluster's view, beside the selector that picks it.
  const why = fleetWide ? "" : scopeWhy(data.whoami, view.cluster);
```

<!-- block: local-development/gsd/static/index.html | edit -->

```html
    <select id="f-cluster">${fleetOption}${goneOption}${opts}</select>`;
```

```html
    <select id="f-cluster">${fleetOption}${goneOption}${opts}</select>${
      why ? `<span class="filterbar-note scope-why" id="scope-why">${esc(why)}</span>` : ""}`;
```

<!-- block: local-development/gsd/static/index.html | edit -->

```html
  hidden: "polled and alerted on, never served through /api (404 like an unknown id)",
```

```html
  hidden: "polled and alerted on, never served through /api (404 like an unknown id)",
  "remote-sar": "this cluster's own RBAC decides, for the reader's OpenShift username",
```

<!-- block: local-development/gsd/static/index.html | edit -->

```html
  "same-as-host": "the host's username is the same person on this cluster (clusters share an identity provider)",
```

```html
  "same-as-host": "the reader is matched by OpenShift username, the User object's name, on this cluster",
```

<!-- block: local-development/gsd/static/index.html | edit -->

```html
        <select id="cc-visibility">${["inherit", "self-only", "hidden"].map((v) => opt(v, f.visibility, `${v} — ${CC_VIS_MEAN[v]}`)).join("")}</select></div>
```

```html
        <select id="cc-visibility">${["inherit", "self-only", "hidden", "remote-sar"].map((v) => opt(v, f.visibility, `${v} — ${CC_VIS_MEAN[v]}`)).join("")}</select></div>
```

<!-- block: local-development/gsd/static/index.html | edit -->

```html
  return { name: "", server: "", token: "", caMode: "caData", caPem: "", visibility: "self-only", identity: "none",
```

```html
  return { name: "", server: "", token: "", caMode: "caData", caPem: "", visibility: "remote-sar", identity: "same-as-host",
```

#### `charts/group-sync-dashboard/templates/_helpers.tpl`

§3.9: the `saTokenLookup` refusal deleted; the pairing refuses only an explicit `identity: none`.

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->

```text
{{- else if and (eq $vis "remote-sar") (eq (index $modeOf $name | default "") "saTokenLookup") -}}
{{- fail (printf "clusters[%d] (%s): visibility remote-sar with saTokenLookup — the lookup writes this cluster as a Secret, and remote-sar is not yet accepted from a Secret (SPEC_S1). Use inherit, self-only or hidden until it is." $i $name) -}}
{{- else if and (eq $vis "remote-sar") (ne $id "same-as-host") -}}
{{- fail (printf "clusters[%d] (%s): visibility remote-sar needs identity: same-as-host. The review names the host's username on that cluster, which only means something if both clusters share an identity provider — say so explicitly." $i $name) -}}
```

```text
{{- else if and (eq $vis "remote-sar") (eq $id "none") -}}
{{- fail (printf "clusters[%d] (%s): visibility remote-sar needs identity: same-as-host — the review names the reader's OpenShift username on this cluster; set same-as-host or leave identity out." $i $name) -}}
```

#### `charts/group-sync-dashboard/templates/NOTES.txt`

§3.9: each remote's resolved pair, by the §3.2 rule.

<!-- block: charts/group-sync-dashboard/templates/NOTES.txt | edit -->

```text
  {{ $c.name }}: visibility {{ if $vis }}{{ $vis }}{{ else if $isHost }}inherit (host){{ else }}self-only (default){{ end }}, identity {{ if $isHost }}same-as-host (host){{ else if $id }}{{ $id }}{{ else }}none (default){{ end }}
```

```text
{{- /* A remote's defaults, by the rule the application serves (SPEC_D2b §3.2, config.py#remote_policy): nothing
       stated is remote-sar + same-as-host; `identity: none` alone keeps self-only. */}}
{{- $defVis := ternary "self-only" "remote-sar" (eq $id "none") }}
{{- $defId := ternary "same-as-host" "none" (eq (default $defVis $vis) "remote-sar") }}
  {{ $c.name }}: visibility {{ if $vis }}{{ $vis }}{{ else if $isHost }}inherit (host){{ else }}{{ $defVis }} (default){{ end }}, identity {{ if $isHost }}same-as-host (host){{ else if $id }}{{ $id }}{{ else }}{{ $defId }} (default){{ end }}
```

#### `charts/group-sync-dashboard/values.yaml`

§3.8: the clusters comment.

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

```yaml
# The oauth-proxy authenticates a reader against THIS cluster only — the first enabled entry,
# the hosting cluster. What that reader may see ABOUT ANOTHER cluster is therefore a decision
# this file has to make, per entry, and it used to make it silently: the host's tier gated
# every cluster's rows, so a host cluster-admin saw a remote cluster's membership, bindings and
# login failures whether or not they held anything there. Two keys per entry now model it
# (docs/ACCESS_CONTROL.md §11):
```

```yaml
# The oauth-proxy authenticates a reader against THIS cluster only — the hosting entry
# (`dashboardController: true`, else the first enabled one). What that reader may see ABOUT
# ANOTHER cluster is therefore a decision this file has to make, per entry, and it used to make
# it silently: the host's tier gated every cluster's rows, so a host cluster-admin saw a remote
# cluster's membership, bindings and login failures whether or not they held anything there.
# Two keys per entry now model it (docs/ACCESS_CONTROL.md §11):
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

```yaml
#                             default (the host is the FIRST ENABLED entry). On a remote it is
```

```yaml
#                             default (the host is the HOSTING entry). On a remote it is
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

```yaml
#                 self-only   nobody is ever wide on this cluster. THE DEFAULT FOR EVERY ENTRY
#                             BUT THE FIRST ENABLED ONE, because it costs no RBAC, no credential
#                             and no cluster call, and can only narrow. On upgrade from chart
#                             0.20.x a multi-cluster install's remotes become self-only; set
#                             inherit to restore what you had.
```

```yaml
#                 self-only   nobody is ever wide on this cluster. It costs no RBAC, no credential
#                             and no cluster call, and can only narrow. The default only for a
#                             remote that states `identity: none` and no visibility. On upgrade to
#                             chart 0.53.0 a remote that states NEITHER key becomes remote-sar
#                             (below); set `visibility: self-only` and `identity: none` to keep
#                             the old view.
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

```yaml
#                 remote-sar  that cluster's OWN RBAC decides: the same SubjectAccessReview as
```

```yaml
#                 remote-sar  that cluster's OWN RBAC decides — THE DEFAULT FOR A REMOTE THAT
#                             STATES NEITHER KEY (SPEC_D2b): the same SubjectAccessReview as
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

```yaml
#                             every failure is the self tier. Needs `create subjectaccessreviews`
#                             on the remote (bind system:auth-delegator to the remote
#                             ServiceAccount by hand — this chart manages no remote RBAC) and
#                             identity: same-as-host below. Not allowed on the first enabled
#                             entry.
```

```yaml
#                             every failure is the self tier, and a failing remote is held for
#                             30 s — asked at most once per hold, whatever the traffic. Needs
#                             `create subjectaccessreviews` and `list groups` on the remote; the
#                             joining ServiceAccount's ClusterRole carries both
#                             (group-sync-dashboard-cluster-poller, installed on each remote by
#                             group-sync-operator-helm). With `identity: none` beside it the
#                             render refuses. Not allowed on the hosting entry.
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

```yaml
#   identity:     none          THE DEFAULT for a remote. The host's username is not treated as
#                               anyone on this cluster: under self-only, person-scoped views
#                               (groups, users, logins, grants) answer 403 there; cluster-level
#                               health still shows. Fail-closed, because "same username, same person" is a
#                               claim about the two clusters' identity providers that this
#                               chart cannot check — an htpasswd `developer` on two clusters is
#                               two people.
#                 same-as-host  the clusters share an identity provider and its username
#                               mapping, so the reader's self views apply to this cluster too.
#                               Required by remote-sar; forced on the first enabled entry.
```

```yaml
#   identity:     none          the reader's username is not treated as anyone on this cluster:
#                               under self-only, person-scoped views (groups, users, logins,
#                               grants) answer 403 there; cluster-level health still shows. The
#                               default beside an explicit inherit, self-only or hidden; stated
#                               alone, it keeps self-only.
#                 same-as-host  the reader is matched on this cluster by OpenShift username — the
#                               User object's name — so their self views apply here too. The
#                               default beside remote-sar and for a remote that states neither
#                               key; required by remote-sar; forced on the hosting entry.
```

#### `charts/group-sync-dashboard/README.md`

§3.8: the three `clusters` rows.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

```markdown
| `clusters` | the local cluster | add entries for multi-cluster. The reader is authenticated by the **first enabled** entry only; each other entry says what that reader may see about it, below |
| `clusters[].visibility` | `inherit` on the first enabled entry, `self-only` on the rest | `inherit` — the host's tier decides (the old behaviour); `self-only` — nobody is wide on this cluster; `hidden` — polled and alerted on, never served through `/api` (404 like an unknown id); `remote-sar` — that cluster's own RBAC decides through the same SubjectAccessReview, created on the remote with its token and its Group objects, cached per reader and cluster; every failure is the self tier. `hidden`/`remote-sar` are refused on the first enabled entry. **Upgrade note:** a multi-cluster install's remotes become `self-only` on chart 0.21.0; set `inherit` to keep the old view |
| `clusters[].identity` | `none` on every entry but the first enabled one | whether the host's username is the same person on this cluster. `none` fails closed: person-scoped views answer 403 there, cluster health still shows. `same-as-host` when the clusters share an identity provider; required by `remote-sar`. The first enabled entry is always `same-as-host` |
```

```markdown
| `clusters` | the local cluster | add entries for multi-cluster. The reader is authenticated by the **hosting** entry only — `dashboardController: true`, else the first enabled one; each other entry says what that reader may see about it, below |
| `clusters[].visibility` | `inherit` on the hosting entry; `remote-sar` on a remote that states neither key; `self-only` on a remote that states only `identity: none` | `inherit` — the host's tier decides (the old behaviour); `self-only` — nobody is wide on this cluster; `hidden` — polled and alerted on, never served through `/api` (404 like an unknown id); `remote-sar` — that cluster's own RBAC decides through the same SubjectAccessReview, created on the remote with its token and its Group objects, cached per reader and cluster; every failure is the self tier, and a failing remote is asked at most once per 30 s. It needs `create subjectaccessreviews` and `list groups` on the remote, which the joining ServiceAccount's ClusterRole carries. `hidden`/`remote-sar` are refused on the hosting entry. **Upgrade note:** on chart 0.53.0 a remote that states neither key moves from `self-only` to `remote-sar` (`docs/CHANGELOG.md`); set `visibility: self-only` and `identity: none` to keep the old view |
| `clusters[].identity` | `same-as-host` on the hosting entry (forced), beside `remote-sar`, and on a remote that states neither key; `none` beside an explicit `inherit`, `self-only` or `hidden` | whether the reader's OpenShift username — the `User` object's name — names the same person on this cluster. `none` fails closed: person-scoped views answer 403 there, cluster health still shows. `same-as-host` matches the reader by that name; `remote-sar` refuses `identity: none` |
```

#### `charts/group-sync-dashboard/example-production.yaml`

§3.8: the three entries' comments.

<!-- block: charts/group-sync-dashboard/example-production.yaml | edit -->

```yaml
    # The viewer's username on the host is not assumed to mean the same person here. Say so, and the
    # tier serves the self view rather than guessing. `identity: same-as-host` is a claim about two
    # identity providers that this chart cannot verify — state it only when it is true.
```

```yaml
    # The reader's OpenShift username is not treated as anyone here: `identity: none` with `self-only`
    # serves this cluster's health and no person-scoped rows. Left out, the two keys would make this
    # cluster's own RBAC decide instead — `remote-sar` + `same-as-host`, the default for a remote.
```

<!-- block: charts/group-sync-dashboard/example-production.yaml | edit -->

```yaml
  # `remote-sar` asks THAT cluster a SubjectAccessReview about the viewer, so it REQUIRES
  # `identity: same-as-host` — the review names the host's username, which only means something when
  # the two clusters share an identity provider. Without it the render refuses, by design.
```

```yaml
  # `remote-sar` asks THAT cluster a SubjectAccessReview about the reader's OpenShift username, the
  # `User` object's name — the default for a remote that states neither key, written out here.
  # `identity: same-as-host` is what it resolves to; `identity: none` beside it is refused at render,
  # because the review would name a username the entry says is nobody.
```

<!-- block: charts/group-sync-dashboard/example-production.yaml | edit -->

```yaml
  # The lookup runs on the next discovery cycle (SPEC_S4b): a login as `svc.gsd.fleet`, one GET of
```

```yaml
  # No visibility or identity: the cluster's own RBAC decides (`remote-sar` + `same-as-host`), and the
  # Secret the lookup writes follows this stanza's policy for as long as it is the lookup's own.
  #
  # The lookup runs on the next discovery cycle (SPEC_S4b): a login as `svc.gsd.fleet`, one GET of
```

#### `charts/group-sync-dashboard/Chart.yaml`

§3.9: chart 0.53.0 and application 0.32.0, each with its history line.

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```yaml
version: 0.52.1
```

```yaml
# CHART 0.53.0 (2026-09-23), MINOR: a remote that states no policy is asked about the reader itself —
# `remote-sar` + `same-as-host` is the default (#338, SPEC_D2b) — and `remote-sar` is accepted beside
# `saTokenLookup`; the render refuses only an explicit `identity: none` beside `remote-sar`, and NOTES
# prints each remote's resolved pair. appVersion moves to application 0.32.0 (below). A remote keeps the
# old view with `visibility: self-only` and `identity: none`.
version: 0.53.0
```

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```yaml
appVersion: "0.31.0"
```

```yaml
# 0.32.0 (2026-09-23). `remote-sar` for every way a cluster is joined (#338, SPEC_D2b): a resolver per
# remote cluster from its current configuration, values or Secret, rebuilt when its connection changes; a
# remote that states no policy defaults to `remote-sar` + `same-as-host`; a failing remote is held for 30 s;
# a lookup-owned Secret serves its stanza's policy and switch; a line beside the selector names the rule
# that decided. MINOR: behaviour changes on upgrade for a remote that states nothing (docs/CHANGELOG.md).
appVersion: "0.32.0"
```

#### `environments/crc.yaml`

§3.8: the `shared-rnd` and `mock` comments.

<!-- block: environments/crc.yaml | edit -->

```yaml
    # NO visibility / identity ON PURPOSE. `self-only` is the chart default for every entry but the
    # first enabled one, and it can only narrow: nobody is ever wide on this cluster. `mock` sets
    # `inherit` explicitly because it is a toy; a real remote should stay narrow until someone
    # decides otherwise. Copying mock's keys here would widen shared-rnd's membership to every host
    # cluster-admin — a decision, not a consistency fix.
```

```yaml
    # NO visibility / identity ON PURPOSE. A remote that states neither is asked about the reader
    # itself — `remote-sar` + `same-as-host` (SPEC_D2b) — so shared-rnd's OWN RBAC decides who sees it
    # wide, and the Secret the lookup writes follows this stanza for as long as it is the lookup's own.
    # `mock` sets `inherit` explicitly because it is a toy. Copying mock's keys here would widen
    # shared-rnd's membership to every host cluster-admin — a decision, not a consistency fix.
```

<!-- block: environments/crc.yaml | edit -->

```yaml
    # The mock is a demo cluster whose fixture makes kubeadmin cluster-admin and developer an editor.
    # A second cluster defaults to self-only/identity:none — the chart never ASSUMES a host identity
    # means the same thing elsewhere. Here we STATE it: a host-authenticated reader is the same identity
    # on the mock, so their tier is computed by SAR (not forced to self), and the admin tabs render.
```

```yaml
    # The mock is a demo cluster whose fixture makes kubeadmin cluster-admin and developer a report
    # auditor. A second cluster that states nothing takes remote-sar + same-as-host — its own RBAC
    # decides. Here we STATE `inherit` instead: the host's tier decides the mock's rows, as a toy's
    # should, and the reader is matched by OpenShift username.
```

#### `docs/ACCESS_CONTROL.md`

§3.7 and §3.8: §11's default column, "How `remote-sar` decides" (the three sentences N4 names), the identity paragraph and the UI sentence.

<!-- block: docs/ACCESS_CONTROL.md | edit -->

```markdown
| | `self-only` | every other entry | nobody is ever wide on this cluster; it costs no RBAC, no credential and no cluster call, and can only narrow |
```

```markdown
| | `self-only` | a remote that states only `identity: none` | nobody is ever wide on this cluster; it costs no RBAC, no credential and no cluster call, and can only narrow |
```

<!-- block: docs/ACCESS_CONTROL.md | edit -->

```markdown
| | `remote-sar` | | that cluster's own RBAC decides: the same SubjectAccessReview as `visibility.adminSar`, created on the remote API with that entry's token, naming the reader and the Group memberships read from the remote; refused on the host entry, and needs `identity: same-as-host` |
| `clusters[].identity` | `none` | every other entry | the host's username is not treated as anyone on this cluster: person-scoped views answer 403 there, cluster-level health still shows |
| | `same-as-host` | the hosting entry, forced | the reader is matched on this cluster by OpenShift username, the `User` object's name, so the reader's self views apply to this cluster too |
```

```markdown
| | `remote-sar` | a remote that states neither key | that cluster's own RBAC decides: the same SubjectAccessReview as `visibility.adminSar`, created on the remote API with that entry's token, naming the reader and the Group memberships read from the remote; refused on the host entry, and refused beside an explicit `identity: none` |
| `clusters[].identity` | `none` | beside an explicit `inherit`, `self-only` or `hidden` | the host's username is not treated as anyone on this cluster: person-scoped views answer 403 there, cluster-level health still shows |
| | `same-as-host` | the hosting entry, forced; beside `remote-sar`; a remote that states neither key | the reader is matched on this cluster by OpenShift username, the `User` object's name, so the reader's self views apply to this cluster too |
```

<!-- block: docs/ACCESS_CONTROL.md | edit -->

```markdown
**How `remote-sar` decides.** One `gsd/kube.py#TierResolver` per remote-sar cluster, constructed on
that cluster's `ClusterConfig`, so the review is created on the remote API with the remote token and
```

```markdown
**How `remote-sar` decides.** `gsd/kube.py#RemoteTierResolvers` finds or builds one `gsd/kube.py#TierResolver`
per remote-sar cluster on each request, from that cluster's current configuration — a values entry or a
Secret, written by hand, by the tab or by the lookup — and rebuilds it when the connection changes (its URL,
token or CA), so the review is created on the remote API with the remote token and
```

<!-- block: docs/ACCESS_CONTROL.md | edit -->

```markdown
review, unreachable, junk) is the self tier and is not cached. Failures count under the same signal
```

```markdown
review, unreachable, junk) is the self tier and is not cached — and it holds that cluster's resolver for
`gsd/kube.py#REMOTE_FAILURE_HOLD_SECONDS` (30 s): no request calls that remote until the hold expires, and the
first one after it is the one probe. Failures count under the same signal
```

<!-- block: docs/ACCESS_CONTROL.md | edit -->

```markdown
The remote RBAC is the operator's, by hand — this chart manages no remote RBAC: a
`ClusterRoleBinding` of `system:auth-delegator` to the remote ServiceAccount grants
`create subjectaccessreviews`.
```

```markdown
This chart manages no remote RBAC. On each remote, `group-sync-operator-helm` installs the joining
ServiceAccount's ClusterRole `group-sync-dashboard-cluster-poller`, which carries `create subjectaccessreviews`
and `list groups` (a ServiceAccount joined by hand needs the same two; a `ClusterRoleBinding` of
`system:auth-delegator` grants the first), and — so that an auditor is wide there too — the auditor ClusterRole,
one ClusterRoleBinding per auditor Group, and each auditor Group the host creates locally
(`rbacAuditors.groups[].createLocal`) with its members (`docs/specs/SPEC_D2b_remote_sar_for_every_join.md` §3.7).
```

<!-- block: docs/ACCESS_CONTROL.md | edit -->

```markdown
`docs/DESIGN_remote_cluster_access.md`, the operator's decision of 2026-09-23). `identity` is still stated per entry:
today `none` is the default for a remote entry that states nothing and fails closed, and `remote-sar` refuses to render or
start without `same-as-host`, because its review names that username on the remote.
```

```markdown
`docs/DESIGN_remote_cluster_access.md`, the operator's decision of 2026-09-23). A remote entry that states nothing
is `same-as-host` with `remote-sar` (SPEC_D2b); `none` fails closed and, stated alone, keeps `self-only`; and
`remote-sar` refuses to render or start beside `identity: none`, because its review names that username on the remote.
```

<!-- block: docs/ACCESS_CONTROL.md | edit -->

```markdown
The UI renders these — the selector marks a narrowed cluster, the header pill and the cluster-scoped
```

```markdown
The UI renders these — the selector marks a narrowed cluster, one line beside it says which rule decided the
selected cluster's view (the host, the cluster's own RBAC, or self-only), the header pill and the cluster-scoped
```

#### `docs/CLUSTER_STANZA.md`

§3.8: rows 13 and 14, the default sentence, and the two refusal rows.

<!-- block: docs/CLUSTER_STANZA.md | edit -->

```markdown
Each rendered and loaded. All twelve are accepted by both readers.
```

```markdown
Each rendered and loaded. All fourteen are accepted by both readers.
```

<!-- block: docs/CLUSTER_STANZA.md | edit -->

```markdown
| 12 | remote + `enabled: false` | kept in the config, not polled |
```

```markdown
| 12 | remote + `enabled: false` | kept in the config, not polled |
| 13 | remote + `visibility: remote-sar` alone | as 11: `identity` resolves to `same-as-host` |
| 14 | remote + `saTokenLookup` + `visibility: remote-sar` | as 6, and the cluster's own RBAC decides through its written Secret |

A remote that states neither `visibility` nor `identity` — rows 2 to 8 and 12 — resolves to `remote-sar` +
`same-as-host`: once it is polled, its own RBAC decides (SPEC_D2b). One that states only `identity: none` keeps
`self-only`.
```

<!-- block: docs/CLUSTER_STANZA.md | edit -->

```markdown
| `remote-sar` without `identity: same-as-host` | **refused** | refused |
```

```markdown
| `remote-sar` with `identity: none` | **refused** | refused |
```

<!-- block: docs/CLUSTER_STANZA.md | edit -->

```markdown
| `saTokenLookup` with `visibility: remote-sar` | **refused** | starts; the write would be refused `visibility-invalid` |
```

```markdown
```

#### `docs/DESIGN_remote_cluster_access.md`

§3.8 and §3.11: the status row, §6's two cells and its explanation, §8's D5 row.

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
| Status | **Proposed.** D1, D2 (`remote-sar` + `same-as-host` is the standard for every way a cluster is joined), D3, D6 and D7 directed by the operator; D4's fail-closed fallback directed, its named finding recommended; D5 and D8 open (§8) |
```

```markdown
| Status | **Proposed.** D1, D2 (`remote-sar` + `same-as-host` is the standard for every way a cluster is joined), D3, D5, D6 and D7 directed by the operator; D4's fail-closed fallback directed, its named finding recommended; D8 open (§8) |
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
| a Secret created on the Cluster Configurations tab | yes | **refused** | yes | yes |
| `saTokenLookup` (the lookup writes a Secret) | yes | **refused** | yes | yes |
```

```markdown
| a Secret created on the Cluster Configurations tab | yes | yes | yes | yes |
| `saTokenLookup` (the lookup writes a Secret) | yes | yes | yes | yes |
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
**Why refused.** The per-cluster `TierResolver` that asks a remote (`local-development/gsd/kube.py#TierResolver`) is
```

```markdown
**Why they were refused until SPEC_D2b.** The per-cluster `TierResolver` that asks a remote (`local-development/gsd/kube.py#TierResolver`) was
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
The way clusters are now joined is exactly the way that cannot ask the remote.
```

```markdown
The way clusters are now joined was exactly the way that could not ask the remote. SPEC_D2b (#338) finds or builds
each resolver per request from the cluster's current configuration, and both refusals are gone.
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
| **D5** | Say which rule decided the reader's view of a cluster | one line under the cluster selector: *the host decides* · *this cluster says you may see everything* · *this cluster says: your own rows* · *this cluster cannot check access* · *this cluster is self-only* | **Open**, recommended. The missing reason is why the lab's narrowing looked like a defect. |
```

```markdown
| **D5** | Say which rule decided the reader's view of a cluster | one line under the cluster selector: *the host decides* · *this cluster says you may see everything* · *this cluster says: your own rows* · *this cluster cannot check access* · *this cluster is self-only* | **Directed** (2026-09-23), built in D2b (`docs/specs/SPEC_D2b_remote_sar_for_every_join.md` §3.11): one line beside the selector, read from `/api/whoami` alone. *this cluster cannot check access* needs D4's field and is not built, so a `remote-sar` cluster's self line says the cluster either answered "your own rows" or could not be asked. |
```

#### `docs/reference-architecture.md`

§3.8: the one sentence that states the old default.

<!-- block: docs/reference-architecture.md | edit -->

```markdown
`gsd/api.py#viewer_scope`): a second cluster is `self-only` with no identity by default, may be
hidden from the API entirely, may inherit the host's tier as an explicit choice, or may be decided
by its own RBAC through the same review on its own API (`remote-sar`). `docs/ACCESS_CONTROL.md` §11
```

```markdown
`gsd/api.py#viewer_scope`): a second cluster that states nothing is decided by its own RBAC through
the same review on its own API (`remote-sar`, SPEC_D2b), and may instead be `self-only`, be hidden
from the API entirely, or inherit the host's tier as an explicit choice. `docs/ACCESS_CONTROL.md` §11
```

#### `local-development/API.md`

§3.3: an omitted pair on `POST /api/clusterconfigs`.

<!-- block: local-development/API.md | edit -->

```markdown
`tls.mode` is one of `trustedBundle` (the dashboard's own trust store — the default), `caData` (this
```

```markdown
`visibility` and `identity` may be omitted; the pair is resolved as discovery resolves the Secret it writes
(`gsd/config.py#remote_policy`, SPEC_D2b §3.2): neither stated is `remote-sar` + `same-as-host`, `identity: none`
alone is `self-only` + `none`, and `remote-sar` beside `identity: none` is `422 identity-invalid`.

`tls.mode` is one of `trustedBundle` (the dashboard's own trust store — the default), `caData` (this
```

#### `docs/specs/README.md`

§3.9: S4c's rungs move up one (the ladder, and `tests/test_specs_index.py`).

<!-- block: docs/specs/README.md | edit -->

```markdown
| S4c | [`SPEC_S4c_credential_lifecycle.md`](SPEC_S4c_credential_lifecycle.md) — S4 step C: the credential lifecycle — the daily ping, `self-login` renewal at the fixed margin, and the per-credential gate on a fleet-account Lease, durable and replica-shared; the design of #285 | S — cluster configuration | — | app 0.32.0, chart 0.53.0 | [#285](https://github.com/ephico2real2/group-sync-dashboard/issues/285) | specified |
```

```markdown
| S4c | [`SPEC_S4c_credential_lifecycle.md`](SPEC_S4c_credential_lifecycle.md) — S4 step C: the credential lifecycle — the daily ping, `self-login` renewal at the fixed margin, and the per-credential gate on a fleet-account Lease, durable and replica-shared; the design of #285 | S — cluster configuration | — | app 0.33.0, chart 0.54.0 | [#285](https://github.com/ephico2real2/group-sync-dashboard/issues/285) | specified |
```

#### `docs/specs/SPEC_S4c_credential_lifecycle.md`

§3.9: S4c's header, its decision note and its two version lines.

<!-- block: docs/specs/SPEC_S4c_credential_lifecycle.md | edit -->

```markdown
| Version on release | app 0.32.0, chart 0.53.0 |
```

```markdown
| Version on release | app 0.33.0, chart 0.54.0 |
```

<!-- block: docs/specs/SPEC_S4c_credential_lifecycle.md | edit -->

```markdown
  had already shipped (#307), and main is at 0.52.1 (#317).
```

```markdown
  had already shipped (#307), and main is at 0.52.1 (#317). SPEC_D2b's implementation (#338) took those two
  rungs first, so this spec now carries app 0.33.0, chart 0.54.0.
```

<!-- block: docs/specs/SPEC_S4c_credential_lifecycle.md | edit -->

```markdown
| `charts/…/Chart.yaml`, `pyproject.toml`, `gsd/__init__.py` | chart 0.53.0, app 0.32.0 — the next minor rungs after 0.52.1 and 0.31.0 on 2026-09-23; re-assigned at the implementing PR if the ladder has moved |
```

```markdown
| `charts/…/Chart.yaml`, `pyproject.toml`, `gsd/__init__.py` | chart 0.54.0, app 0.33.0 — the next minor rungs after SPEC_D2b's chart 0.53.0 and app 0.32.0; re-assigned at the implementing PR if the ladder has moved |
```

<!-- block: docs/specs/SPEC_S4c_credential_lifecycle.md | edit -->

```markdown
- `charts/group-sync-dashboard/Chart.yaml` — `# CHART 0.53.0 (…), MINOR:` history line; `version`,
```

```markdown
- `charts/group-sync-dashboard/Chart.yaml` — `# CHART 0.54.0 (…), MINOR:` history line; `version`,
```

#### `docs/CHANGELOG.md`

§3.9 and §6: the Unreleased entry with the upgrade note.

<!-- block: docs/CHANGELOG.md | edit -->

```markdown
- **Cluster credentials are documented beside the chart's values (chart 0.52.1).** `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md` records the separation the design rests on — an LDAP account bootstraps the connection, a long-lived ServiceAccount token does the polling, and the polling token deliberately carries no `exp` because renewing it would turn a once-per-onboarding bind into a recurring one against an account the whole estate shares. It also states what each failure outcome means (`auth_failed`, `forbidden`, `unreachable`, the cert outcomes), the limit that a bare 401 cannot distinguish an expired token from a revoked one, and the manual recovery that is the only path today — which needs cluster-admin on **both** clusters with two sessions. The planned Refresh (#311) and Rejoin (#316) flow is described and marked as not built, with the rule that governs it: Refresh probes with the stored credential and never re-binds; Rejoin takes the administrator's own credentials, uses them once, and stores nothing.
```

```markdown
- **`remote-sar` for every way a cluster is joined, and the default for a remote (application 0.32.0, chart 0.53.0; #338, `docs/specs/SPEC_D2b_remote_sar_for_every_join.md`).** A remote cluster's own RBAC decides who sees its data wide whether it was declared in values with a token, as a Secret made on the Cluster Configurations tab or by hand, or through `saTokenLookup`: the resolver is found or built per request from the cluster's current configuration and rebuilt when its URL, token or CA changes, with no restart. The Secret parser, the tab and the chart accept `remote-sar`; only an explicit `identity: none` beside it is refused. A failing remote is held for 30 s — asked at most once per hold, whatever the traffic — and the review's error text is redacted before it is truncated. A Secret the lookup wrote for a `saTokenLookup` stanza keeps its credential and serves the stanza's `visibility`, `identity` and `enabled`. `/api/clusters` and `/api/alerts` decide each cluster's tier before they open their database snapshot. One line beside the cluster selector names the rule that decided the selected cluster's view (design D5). **Upgrade note — a remote that states neither `visibility` nor `identity` changes behaviour:** (1) it is `remote-sar` + `same-as-host`, so a reader that cluster's own RBAC allows (`list clusterrolebindings` by default) sees it wide on every tab — Bindings, Operator configs and Kyverno included — with the card's operator-config summary and its administrator alerts; (2) a reader it denies, or one it cannot be asked about, gets their own rows under their OpenShift username on groups, users, logins, cluster access, namespaces, user bindings, the two change feeds and that cluster's Home instead of a 403, and the host's Home counts that cluster's memberships and changes; (3) a remote that states only `identity: same-as-host` moves from `self-only` to `remote-sar` the same way; (4) `/api/whoami`, `/api/clusters` and `/api/alerts` ask that cluster about each reader once per `visibility.tierTtlSeconds`, and an unreachable one costs up to 5 s per remote, one remote after another, on the request that asks — before its hold engages and again on the first request after each hold expires; (5) a remote whose joining ServiceAccount lacks `list groups` or `create subjectaccessreviews` makes `GroupSyncDashboardVisibilityChecksFailing` fire (the pod log names the cluster; the metric does not); (6) a `POST /api/clusterconfigs` that omits both keys writes `remote-sar` + `same-as-host`, and one that states only `identity: none` writes `self-only` + `none`; (7) a Secret the lookup wrote for a `saTokenLookup` stanza serves the stanza's `visibility`, `identity` and `enabled` — a stanza that states no policy moves to `remote-sar` although its Secret was written with `self-only`, and a stanza set to `enabled: false` disables its cluster while the Secret exists. Keep the old view for a cluster with `visibility: self-only` and `identity: none` — in its values stanza, or in its Secret for a Secret-declared cluster; a Secret that already states `self-only` keeps it, unless the lookup wrote it for a stanza (7).

- **Cluster credentials are documented beside the chart's values (chart 0.52.1).** `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md` records the separation the design rests on — an LDAP account bootstraps the connection, a long-lived ServiceAccount token does the polling, and the polling token deliberately carries no `exp` because renewing it would turn a once-per-onboarding bind into a recurring one against an account the whole estate shares. It also states what each failure outcome means (`auth_failed`, `forbidden`, `unreachable`, the cert outcomes), the limit that a bare 401 cannot distinguish an expired token from a revoked one, and the manual recovery that is the only path today — which needs cluster-admin on **both** clusters with two sessions. The planned Refresh (#311) and Rejoin (#316) flow is described and marked as not built, with the rule that governs it: Refresh probes with the stored credential and never re-binds; Rejoin takes the administrator's own credentials, uses them once, and stores nothing.
```

#### `local-development/tests/test_remote_tier_hold.py` — new

§4: the hold and its gate, on a fake clock.

<!-- block: local-development/tests/test_remote_tier_hold.py | create -->

```python
"""A failing remote is held, not asked again by every viewer (docs/specs/SPEC_D2b_remote_sar_for_every_join.md §3.5).

A remote-sar cluster's TierResolver is built with `failure_hold_seconds`: after a failed resolution no request
CALLS that remote until the hold expires, and the first one that would call after it is the single probe,
re-arming the hold before it calls. The gate (`TierResolver._may_call`) is passed by a leader and by a follower
that steals a stuck slot alike; a request for a viewer already being resolved rides that resolution, the probe
included. The host's resolvers pass no hold and must behave exactly as before.

The clock is `gsd.kube`'s own `time.monotonic`, replaced by a counter the test moves, so every window is exact;
a follower's give-up bound (`TIER_CHECK_TIMEOUT_SECONDS * 2 + 1` of REAL time) is shrunk where a case needs it.
"""

from __future__ import annotations

import threading
import time as real_time

import pytest

from gsd import kube
from gsd.config import ClusterConfig, Settings
from gsd.kube import TIER_ALL, TIER_SELF, ClusterError, RemoteTierResolvers, TierResolver

HOLD = 30.0


class _Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def monotonic(self) -> float:
        return self.t

    def __getattr__(self, name):
        return getattr(real_time, name)


class _Remote:
    """TierResolver._kube's two calls. `answer` is "fail" (the group list raises), "deny" or "allow". A viewer
    named in `gates` blocks inside its FIRST group list until the gate is set."""

    def __init__(self, answer: str = "fail") -> None:
        self.cluster = ClusterConfig("west", "https://api.west.example:6443", token_env="X")
        self.answer = answer
        self.calls: list[str] = []
        self.gates: dict[str, threading.Event] = {}
        self.entered = threading.Semaphore(0)
        self._lock = threading.Lock()

    def fetch_groups_of_user(self, viewer: str) -> list[str]:
        with self._lock:
            self.calls.append(viewer)
        self.entered.release()
        gate = self.gates.pop(viewer, None)
        if gate is not None:
            gate.wait(10)
        if self.answer == "fail":
            raise ClusterError("unreachable", "ConnectTimeout: timed out")
        return []

    def create_subject_access_review(self, viewer, groups, attrs) -> bool:
        return self.answer == "allow"


def _resolver(remote: _Remote, *, hold: float = HOLD, observe=None) -> TierResolver:
    r = TierResolver(remote.cluster, verb="list", resource="clusterrolebindings", api_group="rbac.authorization.k8s.io",
                     subresource="", ttl_seconds=60.0, observe=observe, failure_hold_seconds=hold)
    r._kube = remote
    return r


def _burst(r: TierResolver, viewers) -> tuple[list[threading.Thread], dict]:
    out: dict = {}
    threads = [threading.Thread(target=lambda v=v: out.__setitem__(v, r.tier_for(v))) for v in viewers]
    for t in threads:
        t.start()
    return threads, out


@pytest.fixture
def clock(monkeypatch):
    c = _Clock()
    monkeypatch.setattr(kube, "time", c)
    return c


class TestTheHold:
    def test_a_failure_holds_every_viewer_and_the_first_request_after_expiry_is_the_one_probe(self, clock):
        remote = _Remote()
        r = _resolver(remote)
        assert r.tier_for("a") == TIER_SELF                      # fails: held until t+30
        for v in ("b", "c", "d", "e", "a"):
            assert r.tier_for(v) == TIER_SELF
        assert remote.calls == ["a"], "a held remote was asked"
        clock.t += HOLD + 1
        remote.gates["p"] = gate = threading.Event()
        probe, _ = _burst(r, ["p"])
        assert remote.entered.acquire(timeout=5) and remote.entered.acquire(timeout=5)
        others, answers = _burst(r, [f"v{i}" for i in range(8)])
        for t in others:
            t.join(5)
        assert set(answers.values()) == {TIER_SELF} and remote.calls == ["a", "p"], "only the probe calls"
        gate.set()
        for t in probe:
            t.join(5)
        assert r.tier_for("q") == TIER_SELF and remote.calls == ["a", "p"], "the failed probe re-armed the hold"

    def test_a_success_ends_the_hold_for_every_viewer(self, clock):
        remote = _Remote()
        r = _resolver(remote)
        r.tier_for("a")
        clock.t += HOLD + 1
        remote.answer = "allow"
        assert r.tier_for("p") == TIER_ALL
        assert r.tier_for("q") == TIER_ALL and r.tier_for("a") == TIER_ALL
        assert remote.calls == ["a", "p", "q", "a"]

    def test_a_cached_verdict_still_serves_during_a_hold(self, clock):
        remote = _Remote(answer="allow")
        r = _resolver(remote)
        assert r.tier_for("admin") == TIER_ALL                   # cached for the TTL
        remote.answer = "fail"
        assert r.tier_for("other") == TIER_SELF                  # fails: the hold is armed
        assert r.tier_for("admin") == TIER_ALL, "a decided verdict is not a call and is not held"
        assert remote.calls == ["admin", "other"]

    def test_the_first_failure_costs_one_attempt_per_viewer_already_in_flight(self, clock):
        remote = _Remote()
        r = _resolver(remote)
        gate = threading.Event()
        for v in ("a", "b", "c", "d", "e"):
            remote.gates[v] = gate
        threads, _ = _burst(r, ["a", "b", "c", "d", "e"])
        for _ in range(5):
            assert remote.entered.acquire(timeout=5)
        gate.set()
        for t in threads:
            t.join(5)
        assert len(remote.calls) == 5
        for v in ("a", "b", "c", "d", "e", "f"):
            r.tier_for(v)
        assert len(remote.calls) == 5, "after the first failure landed, the hold covers everyone"

    def test_every_hold_expiry_makes_the_next_request_the_probe_that_pays_the_call(self, clock):
        """SPEC_D2b §6: an unreachable remote costs the request that asks, before the hold engages AND on the
        first request after every expiry — measured 15.03 s for three unreachable remotes."""
        remote = _Remote()
        r = _resolver(remote)
        per_request = []
        for at, viewer in ((0.0, "a"), (10.0, "b"), (31.0, "c"), (40.0, "d"), (62.0, "e")):
            clock.t = 1000.0 + at
            before = len(remote.calls)
            r.tier_for(viewer)
            per_request.append(len(remote.calls) - before)
        assert per_request == [1, 0, 1, 0, 1]

    def test_a_resolver_without_a_hold_asks_on_every_request_as_before(self, clock):
        """The host's resolvers pass no hold: every indeterminate check is uncached and asked again."""
        remote = _Remote()
        r = _resolver(remote, hold=0.0)
        for v in ("a", "a", "b"):
            assert r.tier_for(v) == TIER_SELF
        assert remote.calls == ["a", "a", "b"]


class TestEveryCallingPathPassesTheGate:
    """N2 of PR #339's confirmation pass: the gate sits on the CALL, not on the request."""

    def test_the_probes_own_viewer_rides_the_probe_and_gets_its_answer(self, clock):
        """A page sends four to seven requests in one burst: they must read one tier, not the probe's and self."""
        remote = _Remote()
        r = _resolver(remote)
        r.tier_for("a")
        clock.t += HOLD + 1
        remote.answer = "allow"
        remote.gates["admin"] = gate = threading.Event()
        probe, first = _burst(r, ["admin"])
        assert remote.entered.acquire(timeout=5) and remote.entered.acquire(timeout=5)
        siblings, rest = _burst(r, ["admin", "admin", "admin"])
        real_time.sleep(0.2)
        gate.set()
        for t in probe + siblings:
            t.join(5)
        assert first["admin"] == TIER_ALL and set(rest.values()) == {TIER_ALL}
        assert remote.calls == ["a", "admin"], "the siblings rode the probe"

    def test_a_follower_that_gives_up_on_a_stuck_leader_does_not_call_while_the_remote_is_held(self, clock, monkeypatch):
        monkeypatch.setattr(kube, "TIER_CHECK_TIMEOUT_SECONDS", 0.05)    # a follower gives up after 1.1 s of real time
        remote = _Remote()
        r = _resolver(remote)
        remote.gates["v"] = stuck = threading.Event()
        leader, _ = _burst(r, ["v"])
        assert remote.entered.acquire(timeout=5)
        follower, answers = _burst(r, ["v"])
        real_time.sleep(0.2)
        clock.t += 1.0
        assert r.tier_for("u") == TIER_SELF                       # another viewer's failure arms the hold
        held = list(remote.calls)
        for t in follower:
            t.join(5)
        stuck.set()
        for t in leader:
            t.join(5)
        assert remote.calls == held, f"a call went out during the hold: {remote.calls}"
        assert answers == {"v": TIER_SELF}

    def test_a_follower_of_a_leader_stalled_in_the_observe_callback_does_not_call_during_its_hold(self, clock, monkeypatch):
        """The threat model §3.5 orders `_start_hold` before `_note` for: the observe callback is not bounded."""
        monkeypatch.setattr(kube, "TIER_CHECK_TIMEOUT_SECONDS", 0.05)
        remote = _Remote()
        stall = threading.Event()
        r = _resolver(remote, observe=lambda outcome: stall.wait(10))
        remote.gates["v"] = release = threading.Event()
        leader, _ = _burst(r, ["v"])
        assert remote.entered.acquire(timeout=5)
        follower, answers = _burst(r, ["v"])
        real_time.sleep(0.2)
        release.set()                                             # fails, arms the hold, stalls in _note
        real_time.sleep(0.2)
        held = list(remote.calls)
        for t in follower:
            t.join(5)
        stall.set()
        for t in leader:
            t.join(5)
        assert remote.calls == held, f"a call went out during the hold: {remote.calls}"
        assert answers == {"v": TIER_SELF}

    def test_a_follower_of_a_stuck_probe_does_not_start_a_second_probe(self, clock, monkeypatch):
        monkeypatch.setattr(kube, "TIER_CHECK_TIMEOUT_SECONDS", 0.05)
        remote = _Remote()
        r = _resolver(remote)
        r.tier_for("a")
        clock.t += HOLD + 1
        remote.gates["p"] = stuck = threading.Event()
        probe, _ = _burst(r, ["p"])
        assert remote.entered.acquire(timeout=5) and remote.entered.acquire(timeout=5)
        follower, answers = _burst(r, ["p"])
        for t in follower:
            t.join(5)
        stuck.set()
        for t in probe:
            t.join(5)
        assert remote.calls == ["a", "p"] and answers == {"p": TIER_SELF}


class TestARebuildStartsFresh:
    def test_a_rotated_token_builds_a_new_resolver_without_the_old_hold_or_cache(self, clock, tmp_path):
        host = ClusterConfig("home", "https://kubernetes.default.svc", token_env="X", dashboard_controller=True)
        settings = Settings(clusters=[host], db_path=str(tmp_path / "r.db"), view_restrictions_enabled=True)
        east = ClusterConfig("east", "https://api.east.example:6443", token_value="sha256~first-token-aaaaaaa",
                             source="secret:gsd-cluster-east")
        settings.cluster_registry.replace([east], [], at="t0")
        remotes: list[_Remote] = []

        def make(c: ClusterConfig) -> TierResolver:
            remotes.append(_Remote())
            return _resolver(remotes[-1])

        pool = RemoteTierResolvers(settings, make)
        assert pool.get("east").tier_for("a") == TIER_SELF       # fails: that resolver is held
        assert pool.get("east").tier_for("b") == TIER_SELF and remotes[0].calls == ["a"]
        rotated = ClusterConfig("east", "https://api.east.example:6443", token_value="sha256~second-token-bbbbbb",
                                source="secret:gsd-cluster-east")
        settings.cluster_registry.replace([rotated], [], at="t1")
        assert pool.get("east").tier_for("b") == TIER_SELF
        assert len(remotes) == 2 and remotes[1].calls == ["b"], "the new connection is asked at once"
```

#### `local-development/tests/test_remote_tier_resolvers.py` — new

§4: the pool, the app's construction of it, and the redaction.

<!-- block: local-development/tests/test_remote_tier_resolvers.py | create -->

```python
"""Resolvers follow the cluster's current configuration (docs/specs/SPEC_D2b_remote_sar_for_every_join.md §3.1),
and the review's error text is redacted before it is truncated (§3.6).

`RemoteTierResolvers.get` finds or builds one TierResolver per remote-sar cluster on each request, from ONE merged
`ClusterConfig` snapshot, keyed by `ClusterConfig.connection_fingerprint()` — equality cannot see a rotated Secret
credential, which is compare=False by design.
"""

from __future__ import annotations

import dataclasses
import json

import httpx
import pytest

from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.kube import (
    REMOTE_FAILURE_HOLD_SECONDS, SAR_API, ClusterClient, ClusterError, RemoteTierResolvers, TierResolver,
)

PEM_A = "-----BEGIN CERTIFICATE-----\nAAAA\n-----END CERTIFICATE-----\n"
PEM_B = "-----BEGIN CERTIFICATE-----\nBBBB\n-----END CERTIFICATE-----\n"


def _settings(tmp_path, *values: ClusterConfig, **kw) -> Settings:
    host = ClusterConfig("home", "https://kubernetes.default.svc", token_env="X", dashboard_controller=True)
    return Settings(clusters=[host, *values], db_path=str(tmp_path / "r.db"), **{"view_restrictions_enabled": True, **kw})


def _secret(name: str = "east", **kw) -> ClusterConfig:
    base = dict(api_url=f"https://api.{name}.example:6443", token_value="sha256~token-one-aaaaaaaa",
                source=f"secret:gsd-cluster-{name}")
    return ClusterConfig(name, **{**base, **kw})


class _Built:
    """A `make` that records what it was built from and hands back a distinct object per build."""

    def __init__(self) -> None:
        self.configs: list[ClusterConfig] = []

    def __call__(self, c: ClusterConfig):
        self.configs.append(c)
        return object()


class TestTheResolverFollowsTheCurrentConfiguration:
    def test_a_secret_declared_cluster_gets_a_resolver_and_the_same_one_while_nothing_changes(self, tmp_path):
        settings = _settings(tmp_path)
        settings.cluster_registry.replace([_secret()], [], at="t0")
        built = _Built()
        pool = RemoteTierResolvers(settings, built)
        first = pool.get("east")
        assert first is not None and pool.get("east") is first
        settings.cluster_registry.replace([_secret()], [], at="t1")      # the next discovery, the same Secret
        assert pool.get("east") is first and len(built.configs) == 1

    @pytest.mark.parametrize("change", [
        {"token_value": "sha256~token-two-bbbbbbbb"},
        {"ca_data": PEM_B},
        {"api_url": "https://api.east-2.example:6443"},
        {"insecure_skip_verify": True},
    ], ids=["token", "ca", "url", "insecure"])
    def test_a_connection_change_builds_a_new_resolver_on_the_new_values(self, tmp_path, change):
        settings = _settings(tmp_path)
        settings.cluster_registry.replace([_secret(ca_data=PEM_A)], [], at="t0")
        built = _Built()
        pool = RemoteTierResolvers(settings, built)
        first = pool.get("east")
        settings.cluster_registry.replace([dataclasses.replace(_secret(ca_data=PEM_A), **change)], [], at="t1")
        second = pool.get("east")
        assert second is not first
        for key, value in change.items():
            assert getattr(built.configs[-1], key) == value

    def test_a_values_entry_rebuilds_on_a_named_file_but_not_on_its_content(self, tmp_path):
        """A tokenFile's content and a caBundleFile's are re-read by every ClusterClient._client call; only
        their names are fixed on the config, and only a name moves the fingerprint."""
        a = ClusterConfig("far", "https://api.far.example:6443", token_file="/etc/gsd/far/token")
        b = dataclasses.replace(a, token_file="/etc/gsd/far/token-2")
        assert a.connection_fingerprint() == dataclasses.replace(a).connection_fingerprint()
        assert a.connection_fingerprint() != b.connection_fingerprint()
        assert a.connection_fingerprint() != dataclasses.replace(a, ca_bundle_file="/etc/gsd/far/ca.crt").connection_fingerprint()

    def test_a_policy_change_is_not_a_connection_change(self, tmp_path):
        a = _secret()
        assert a.connection_fingerprint() == dataclasses.replace(a, visibility="remote-sar", identity="same-as-host",
                                                                  labels=(("team", "x"),)).connection_fingerprint()

    @pytest.mark.parametrize("case", ["retired", "disabled", "pending", "host", "hidden", "inherit", "self-only",
                                      "remote-sar with identity none"])
    def test_none_and_the_entry_forgotten_for_a_cluster_that_is_not_an_askable_remote(self, tmp_path, case):
        settings = _settings(tmp_path, ClusterConfig("rnd", "https://api.rnd.example:6443", sa_token_lookup=True))
        settings.cluster_registry.replace([_secret()], [], at="t0")
        built = _Built()
        pool = RemoteTierResolvers(settings, built)
        assert pool.get("east") is not None
        cluster = "east"
        if case == "retired":
            settings.cluster_registry.replace([], [], at="t1")
        elif case == "disabled":
            settings.cluster_registry.replace([_secret(enabled=False)], [], at="t1")
        elif case == "pending":
            cluster = "rnd"                                      # the stanza's lookup has not written its Secret
        elif case == "host":
            cluster = "home"
        elif case == "remote-sar with identity none":           # refused by every reader; a hand-built Settings
            settings.cluster_registry.replace([_secret(visibility="remote-sar", identity="none")], [], at="t1")
        else:
            settings.cluster_registry.replace([_secret(visibility=case)], [], at="t1")
        assert pool.get(cluster) is None
        if cluster == "east":
            assert "east" not in pool._built, "a cluster that stopped being askable keeps no resolver"
        assert len(built.configs) == 1

    def test_one_configuration_snapshot_per_lookup(self, tmp_path):
        settings = _settings(tmp_path)
        settings.cluster_registry.replace([_secret()], [], at="t0")
        reads = []
        real = settings.cluster_registry.merge

        def merge(values):
            reads.append(1)
            return real(values)
        object.__setattr__(settings.cluster_registry, "merge", merge)
        RemoteTierResolvers(settings, _Built()).get("east")
        assert len(reads) == 1, "the policy must be resolved from the snapshot the connection came from"


class TestTheAppBuildsThePool:
    def test_the_pool_builds_each_remote_on_its_own_api_with_the_hold(self, tmp_path):
        settings = _settings(tmp_path, ClusterConfig("far", "https://api.far.example:6443", token_env="X"),
                             oauth_proxy_enabled=True)
        settings.cluster_registry.replace([_secret()], [], at="t0")
        app = build_app(settings, run_poller=False)
        pool = app.state.remote_tier_resolvers
        assert isinstance(pool, RemoteTierResolvers) and pool.get("home") is None
        for name in ("far", "east"):                             # a values entry and a Secret, neither states a policy
            r = pool.get(name)
            assert isinstance(r, TierResolver) and r._kube.cluster.name == name
            assert r._hold == REMOTE_FAILURE_HOLD_SECONDS
            assert r._attributes == {"verb": "list", "resource": "clusterrolebindings", "group": "rbac.authorization.k8s.io"}

    def test_restrictions_off_builds_no_pool(self, tmp_path):
        app = build_app(_settings(tmp_path, view_restrictions_enabled=False), run_poller=False)
        assert app.state.remote_tier_resolvers == {}


# ── §3.6: the review's error text is redacted before it is truncated ─────────────────────────────────────────
JWT = "eyJhbGciOiJSUzI1NiJ9." + "A" * 700 + ".signature-part-zzzzzzzz"


def _client_answering(monkeypatch, handler) -> ClusterClient:
    cluster = ClusterConfig("west", "https://api.west.example:6443", token_value=JWT, source="secret:gsd-cluster-west")
    client = ClusterClient(cluster, timeout=5.0)
    monkeypatch.setattr(client, "_client", lambda: httpx.Client(
        base_url=cluster.api_url, headers={"Authorization": f"Bearer {JWT}"}, transport=httpx.MockTransport(handler)))
    return client


class TestTheReviewsErrorTextIsRedacted:
    def test_a_jwt_echoed_in_an_error_body_never_reaches_the_message_even_across_the_cut(self, monkeypatch):
        client = _client_answering(monkeypatch, lambda request: httpx.Response(
            502, text="x" * 150 + " proxy echo: Bearer " + JWT + " " + "y" * 100))
        with pytest.raises(ClusterError) as exc:
            client.create_subject_access_review("alice", [], {"verb": "list", "resource": "clusterrolebindings"})
        message = exc.value.message
        assert message.startswith(f"HTTP 502 on {SAR_API}: ") and "<redacted>" in message
        assert JWT[:24] not in message, "a prefix of the token survived the 200-character cut"

    def test_a_connect_error_carrying_the_credential_is_redacted(self, monkeypatch):
        def refuse(request):
            raise httpx.ConnectError(f"proxy said no to Bearer {JWT}", request=request)
        client = _client_answering(monkeypatch, refuse)
        with pytest.raises(ClusterError) as exc:
            client.create_subject_access_review("alice", [], {"verb": "list", "resource": "clusterrolebindings"})
        assert exc.value.outcome == "unreachable" and JWT[:24] not in exc.value.message
        assert json.dumps(exc.value.message).count("<redacted>") == 1
```

#### `local-development/tests/test_remote_sar_default.py` — new

§4: the pair rule by every reader, an unstated remote end to end, F6 and F7.

<!-- block: local-development/tests/test_remote_sar_default.py | create -->

```python
"""The default is `remote-sar` + `same-as-host` (docs/specs/SPEC_D2b_remote_sar_for_every_join.md §3.2, §3.3, §6),
and what that changes for a remote that states nothing — measured at the routes, through the app.state seams.

The rows of §3.2's table — its last row once for each of its three visibilities — are held twice: what
`remote_policy` RETURNS, and what each reader ACCEPTS — the loader, the Secret parser and the chart refuse only the
explicit pair `remote-sar` + `identity: none`.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest
import yaml
from fastapi.testclient import TestClient

import gsd.api as api_mod
from gsd.api import build_app
from gsd.clusterconfig import Finding, parse_secret, writer
from gsd.config import ClusterConfig, ConfigError, Settings, load_settings, remote_policy
from gsd.store import Store
from gsd.timeutil import now_iso

from test_clusterconfig import _secret

CHART = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"

#: (visibility stated, identity stated) -> what remote_policy returns, and whether the readers accept it
TABLE = [
    ((None, None), ("remote-sar", "same-as-host"), True),
    ((None, "none"), ("self-only", "none"), True),
    ((None, "same-as-host"), ("remote-sar", "same-as-host"), True),
    (("remote-sar", None), ("remote-sar", "same-as-host"), True),
    (("remote-sar", "none"), ("remote-sar", "none"), False),
    (("inherit", None), ("inherit", "none"), True),
    (("self-only", None), ("self-only", "none"), True),
    (("hidden", None), ("hidden", "none"), True),
]
IDS = [f"{v or '-'}+{i or '-'}" for (v, i), _, _ in TABLE]


def _stated(visibility, identity) -> dict:
    return {k: v for k, v in (("visibility", visibility), ("identity", identity)) if v is not None}


class TestThePairRule:
    @pytest.mark.parametrize("stated,resolved,accepted", TABLE, ids=IDS)
    def test_remote_policy_resolves_the_row(self, stated, resolved, accepted):
        assert remote_policy(*stated) == resolved

    @pytest.mark.parametrize("stated,resolved,accepted", TABLE, ids=IDS)
    def test_the_loader_accepts_or_refuses_the_row(self, tmp_path, stated, resolved, accepted):
        entry = {"name": "far", "apiUrl": "https://api.far.example:6443", "tokenEnv": "X", **_stated(*stated)}
        p = tmp_path / "clusters.yaml"
        p.write_text(yaml.safe_dump({"clusters": [
            {"name": "home", "apiUrl": "https://kubernetes.default.svc", "tokenEnv": "X", "dashboardController": True},
            entry]}))
        if accepted:
            assert load_settings(str(p)).cluster_policy("far") == resolved
        else:
            with pytest.raises(ConfigError, match="visibility remote-sar needs identity: same-as-host"):
                load_settings(str(p))

    @pytest.mark.parametrize("stated,resolved,accepted", TABLE, ids=IDS)
    def test_the_secret_parser_accepts_or_refuses_the_row(self, stated, resolved, accepted):
        parsed = parse_secret(_secret(**_stated(*stated)), host_name="home")
        if accepted:
            assert isinstance(parsed, ClusterConfig) and remote_policy(parsed.visibility, parsed.identity) == resolved
        else:
            assert isinstance(parsed, Finding) and parsed.code == "identity-invalid"
            assert "cannot pair with visibility remote-sar" in parsed.detail

    @pytest.mark.parametrize("stated,resolved,accepted", TABLE, ids=IDS)
    @pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
    def test_the_chart_accepts_or_refuses_the_row(self, tmp_path, stated, resolved, accepted):
        entry = {"name": "far", "apiUrl": "https://api.far.example:6443", "tokenEnv": "X", **_stated(*stated)}
        values = tmp_path / "v.yaml"
        values.write_text(yaml.safe_dump({"clusters": [
            {"name": "home", "apiUrl": "https://kubernetes.default.svc", "tokenEnv": "X", "dashboardController": True},
            entry]}))
        done = subprocess.run(["helm", "template", "t", str(CHART), "-f", str(values)],
                              capture_output=True, text=True, timeout=180)
        assert (done.returncode == 0) is accepted, done.stdout[-400:] + done.stderr[-400:]
        if not accepted:
            assert "visibility remote-sar needs identity: same-as-host" in done.stderr

    @pytest.mark.skipif(shutil.which("helm") is None, reason="helm is not installed")
    def test_the_chart_accepts_remote_sar_beside_the_lookup(self, tmp_path):
        values = tmp_path / "v.yaml"
        values.write_text(yaml.safe_dump({
            "clusters": [{"name": "home", "apiUrl": "https://kubernetes.default.svc", "tokenEnv": "X",
                          "dashboardController": True},
                         {"name": "rnd", "apiUrl": "https://api.rnd.example:6443", "saTokenLookup": True,
                          "visibility": "remote-sar"}],
            "clusterConfig": {"secrets": {"writes": {"enabled": True}}}}))
        done = subprocess.run(["helm", "template", "t", str(CHART), "-f", str(values)],
                              capture_output=True, text=True, timeout=180)
        assert done.returncode == 0, done.stderr[-600:]


# ── what the flip changes for a remote that states nothing (§6) ──────────────────────────────────────────────
ALICE = {"X-Forwarded-User": "alice"}


def _seed(db: str) -> None:
    store = Store(db)
    now = now_iso()
    for cid in ("host", "far"):
        store.upsert_cluster(cid, f"https://api.{cid}.example:6443", True)
        store.record_poll(cid, "ok", None)
        store.replace_group_state(cid, [
            {"name": f"{cid}-admins", "member_count": 1, "sync_provider": "ldap_ldap", "group_synced_at": now, "ldap_uid": None},
        ], now)
        store.sync_members(cid, {f"{cid}-admins": ["alice"]}, {}, now)
        store.record_managed_groups(cid, [{"name": f"{cid}-gone", "sync_provider": "ldap_ldap"}], now)
        store.replace_bindings(cid, [
            {"binding_kind": "RoleBinding", "binding_namespace": "ns1", "binding_name": f"{cid}-gone-rb",
             "role_kind": "ClusterRole", "role_name": "admin", "group_name": f"{cid}-gone"},
        ], now)
        store.replace_operator_configs(cid, [
            {"kind": "GroupConfig", "name": f"{cid}-gc", "error_at": None, "error_message": None, "success_at": now},
        ], now)
    store.close()


class _Map:
    def __init__(self, tiers: dict[str, str]):
        self.tiers, self.calls = tiers, 0

    def resolve(self, viewer: str) -> str:
        self.calls += 1
        return self.tiers.get(viewer, "self")


def _unstated_app(tmp_path, remote: _Map | None):
    db = str(tmp_path / "gsd.db")
    _seed(db)
    app = build_app(Settings(clusters=[ClusterConfig("host", "https://api.host.example:6443", token_env="X"),
                                       ClusterConfig("far", "https://api.far.example:6443", token_env="X")],
                             db_path=db, oauth_proxy_enabled=True, view_restrictions_enabled=True), run_poller=False)
    app.state.tier_resolver = _Map({})
    app.state.remote_tier_resolvers = {"far": remote} if remote is not None else {}
    return app


PERSON_SCOPED = ("groups", "groups/far-admins", "users", "users/alice", "logins", "cluster-access", "namespaces",
                 "user-bindings", "membership-changes", "binding-changes", "home")
ADMINISTRATOR = ("bindings/findings", "operator-configs", "kyverno")


class TestAnUnstatedRemote:
    def test_a_reader_it_allows_sees_it_wide_on_every_tab_the_card_and_its_alerts(self, tmp_path):
        with TestClient(_unstated_app(tmp_path, _Map({"alice": "all"}))) as c:
            who = c.get("/api/whoami", headers=ALICE).json()["visibility"]["clusters"]["far"]
            assert who == {"policy": "remote-sar", "identity": "same-as-host", "scope": "all"}
            card = next(x for x in c.get("/api/clusters", headers=ALICE).json() if x["id"] == "far")
            assert card["visibility"] == {"policy": "remote-sar", "scope": "all"}
            assert card["operator_configs"] == {"total": 1, "failing": 0}
            for path in PERSON_SCOPED:
                r = c.get(f"/api/clusters/far/{path}", headers=ALICE)
                assert r.status_code == 200 and r.json()["scope"] == "all", path
            for path in ADMINISTRATOR:
                assert c.get(f"/api/clusters/far/{path}", headers=ALICE).status_code == 200, path
            kinds = {a["kind"] for a in c.get("/api/alerts", headers=ALICE).json()["alerts"] if a["cluster"] == "far"}
            assert "dangling_binding" in kinds

    @pytest.mark.parametrize("remote", ["denies", "cannot be asked"])
    def test_a_reader_it_denies_or_cannot_ask_about_gets_their_own_rows_not_a_403(self, tmp_path, remote):
        with TestClient(_unstated_app(tmp_path, _Map({}) if remote == "denies" else None)) as c:
            for path in PERSON_SCOPED:
                r = c.get(f"/api/clusters/far/{path}", headers=ALICE)
                assert r.status_code == 200 and r.json()["scope"] == "self" and r.json()["viewer"] == "alice", path
            for path in ADMINISTRATOR:
                assert c.get(f"/api/clusters/far/{path}", headers=ALICE).status_code == 403, path
            card = next(x for x in c.get("/api/clusters", headers=ALICE).json() if x["id"] == "far")
            assert card["operator_configs"] is None

    def test_home_counts_it_without_asking_its_resolver(self, tmp_path):
        remote = _Map({"alice": "all"})
        with TestClient(_unstated_app(tmp_path, remote)) as c:
            home = c.get("/api/clusters/host/home", headers=ALICE).json()
        assert [e["cluster"] for e in home["elsewhere"]] == ["far"] and home["memberships_total"] == 2
        assert remote.calls == 0, "vouches_for_host_identity is configuration only"

    def test_whoami_asks_it_once_and_reports_it(self, tmp_path):
        remote = _Map({})
        with TestClient(_unstated_app(tmp_path, remote)) as c:
            who = c.get("/api/whoami", headers=ALICE).json()["visibility"]["clusters"]
        assert who["far"] == {"policy": "remote-sar", "identity": "same-as-host", "scope": "self"}
        assert remote.calls == 1

    def test_identity_none_alone_keeps_the_old_self_only_and_its_403(self, tmp_path):
        db = str(tmp_path / "gsd.db")
        _seed(db)
        app = build_app(Settings(clusters=[ClusterConfig("host", "https://api.host.example:6443", token_env="X"),
                                           ClusterConfig("far", "https://api.far.example:6443", token_env="X",
                                                         identity="none")],
                                 db_path=db, oauth_proxy_enabled=True), run_poller=False)
        app.state.tier_resolver = _Map({})
        with TestClient(app) as c:
            assert c.get("/api/clusters/far/groups", headers=ALICE).status_code == 403
            assert c.get("/api/whoami", headers=ALICE).json()["visibility"]["clusters"]["far"] == \
                {"policy": "self-only", "identity": "none", "scope": "self"}


class TestNoTierIsDecidedInsideASnapshot:
    """§3.10: under remote-sar a decision is a group list and a review on the remote, and a read snapshot held
    across it pins the WAL read-mark (store.read_snapshot) — measured busy (1, 10, 10) for 15 s."""

    def test_clusters_and_alerts_decide_every_tier_before_their_read_snapshot(self, tmp_path):
        app = _unstated_app(tmp_path, None)
        store = app.state.store
        depths: list[int] = []

        class Probe:
            def resolve(self, viewer: str) -> str:
                depths.append(getattr(store._local, "read_depth", 0))
                return "self"
        app.state.tier_resolver = Probe()
        app.state.remote_tier_resolvers = {"far": Probe()}
        with TestClient(app) as c:
            for path in ("/api/clusters", "/api/alerts"):
                assert c.get(path, headers=ALICE).status_code == 200, path
        assert len(depths) == 4 and max(depths) == 0, f"a tier was decided inside a read snapshot: {depths}"


class TestTheTabsCreateRequestResolvesThePair:
    """§3.3: an omitted `visibility` or `identity` is resolved by §3.2's rule, the one discovery applies to the
    Secret the request writes — never field by field."""

    @pytest.fixture
    def post(self, tmp_path, monkeypatch):
        written: list[tuple[str, str]] = []

        def create(host_client, namespace, req, *, host_name, taken, viewer):
            writer.validate(req, namespace, host_name=host_name, taken=taken)
            written.append((req.visibility, req.identity))
            return writer.secret_name_for(req.name)
        monkeypatch.setattr(api_mod, "own_namespace", lambda: "gsd")
        monkeypatch.setattr(writer, "create", create)
        app = build_app(Settings(clusters=[ClusterConfig("home", "https://kubernetes.default.svc", token_env="X",
                                                         dashboard_controller=True)],
                                 db_path=str(tmp_path / "t.db"), oauth_proxy_enabled=True, view_restrictions_enabled=True,
                                 cluster_secrets_enabled=True, cluster_secrets_writes_enabled=True),
                        run_poller=False, tier_resolver=lambda v: "all",
                        clusterconfig_view_resolver=lambda v: "all", clusterconfig_manage_resolver=lambda v: "all")

        def _post(**extra):
            body = {"name": "new", "server": "https://api.new.example:6443",
                    "credential": {"kind": "bearerToken", "token": "sha256~a-long-enough-token"}, **extra}
            with TestClient(app) as c:
                return c.post("/api/clusterconfigs", json=body, headers={"X-Forwarded-User": "kubeadmin"}), written
        return _post

    @pytest.mark.parametrize("extra,pair", [
        ({}, ("remote-sar", "same-as-host")),
        ({"identity": "none"}, ("self-only", "none")),
        ({"visibility": "self-only"}, ("self-only", "none")),
        ({"visibility": "inherit"}, ("inherit", "none")),
        ({"visibility": "remote-sar", "identity": "same-as-host"}, ("remote-sar", "same-as-host")),
    ], ids=["nothing", "identity-none", "self-only", "inherit", "both"])
    def test_an_omitted_field_is_resolved_by_the_pair_rule(self, post, extra, pair):
        r, written = post(**extra)
        assert r.status_code == 201, r.text
        assert written == [pair]

    def test_the_explicit_remote_sar_none_pair_is_refused_by_name(self, post):
        r, written = post(visibility="remote-sar", identity="none")
        assert r.status_code == 422 and r.json()["detail"].startswith("identity-invalid:") and written == []
```

#### `local-development/tests/test_lookup_owned_secret.py` — new

§4: the merge, the served line and row, the lookup's written pair.

<!-- block: local-development/tests/test_lookup_owned_secret.py | create -->

```python
"""A lookup-owned Secret takes its stanza's policy and switch; any other Secret wins wholesale
(docs/specs/SPEC_D2b_remote_sar_for_every_join.md §3.4).

Ownership is the test the reader already makes: the Secret's `groupsync-dashboard.io/token-source` annotation
equals the credential kind of the values stanza of the same name. The reader records it on the parsed config
(`ClusterConfig.token_source`) and `ClusterRegistry.merge` keeps the Secret's credential and serves the stanza's
`visibility`, `identity` and `enabled`. Driven through the real reader, registry and `Poller._discover_once` over
Secrets kept the way the API server keeps them.
"""

from __future__ import annotations

import base64
import copy
import dataclasses
import json
import logging

import pytest

import gsd.poller as poller_mod
from gsd.clusterconfig import ClusterRegistry
from gsd.config import ClusterConfig, Settings
from gsd.fleetlookup import SaToken, store
from gsd.kube import ClusterError, RemoteTierResolvers
from gsd.poller import Poller
from gsd.store import Store

TOKEN_SOURCE = "groupsync-dashboard.io/token-source"
SA_TOKEN = "eyJhbGciOiJSUzI1NiJ9.a-lookup-written-token-aaaaaaaaaaaaaaaa.sig"


class _Host:
    """The host API's labelled Secrets in the pod's namespace: LIST for discovery, GET/POST/PUT for the writer."""

    def __init__(self, cfg=None, timeout=15.0):
        pass

    secrets: dict[str, dict] = {}

    def _client(self):
        class _Ctx:
            def __enter__(self_inner):  # noqa: N805
                return self_inner

            def __exit__(self_inner, *a):  # noqa: N805
                return False
        return _Ctx()

    def _list_all_with(self, client, path, extra):
        return [copy.deepcopy(o) for o in _Host.secrets.values()]

    def _get(self, client, path, params):
        name = path.rsplit("/", 1)[1]
        if name not in _Host.secrets:
            raise ClusterError("unreachable", f"HTTP 404 on {path}: not found")
        return copy.deepcopy(_Host.secrets[name])

    def _send(self, client, method, path, *, json=None, secrets=()):
        obj = copy.deepcopy(json)
        data = dict(obj.get("data") or {})
        for k, v in (obj.pop("stringData", None) or {}).items():
            data[k] = base64.b64encode(str(v).encode()).decode()
        obj["data"] = data
        _Host.secrets[obj["metadata"]["name"]] = obj
        return None


def _secret(cluster: str, *, annotations: dict | None = None, **data) -> dict:
    payload = {"name": cluster, "server": f"https://api.{cluster}.example:6443",
               "config": json.dumps({"bearerToken": "sha256~a-hand-made-token-bbbbbbbb"}), **data}
    return {"metadata": {"name": f"gsd-cluster-{cluster}", "labels": {"groupsync-dashboard.io/secret-type": "cluster"},
                         "annotations": dict(annotations or {})},
            "data": {k: base64.b64encode(str(v).encode()).decode() for k, v in payload.items()}}


@pytest.fixture
def discovering(tmp_path, monkeypatch):
    monkeypatch.setattr(poller_mod, "own_namespace", lambda: "ns")
    monkeypatch.setattr(poller_mod, "ClusterClient", _Host)
    _Host.secrets = {}

    def make(*stanzas: ClusterConfig):
        settings = Settings(clusters=[ClusterConfig("home", "https://kubernetes.default.svc", token_env="X",
                                                    dashboard_controller=True), *stanzas],
                            db_path=str(tmp_path / "p.db"), view_restrictions_enabled=True)
        db = Store(settings.db_path)
        return settings, Poller(db, settings), db
    return make


RND = ClusterConfig("rnd", "https://api.rnd.example:6443", sa_token_lookup=True)
OWNED = {TOKEN_SOURCE: "remote-lookup"}


class TestTheMerge:
    def test_an_owned_secret_keeps_its_credential_and_source_and_serves_the_stanzas_policy(self):
        reg = ClusterRegistry()
        found = dataclasses.replace(ClusterConfig("rnd", "https://api.rnd.example:6443", token_value="sha256~t-aaaaaaaa",
                                                  source="secret:gsd-cluster-rnd", visibility="self-only",
                                                  identity="none"), token_source="remote-lookup")
        reg.replace([found], [], at="t")
        served, = [c for c in reg.merge([dataclasses.replace(RND, visibility="hidden")]) if c.name == "rnd"]
        assert (served.source, served.token_value, served.credential_kind) == ("secret:gsd-cluster-rnd", "sha256~t-aaaaaaaa", "bearer")
        assert (served.visibility, served.identity) == ("hidden", None), "the stanza's policy, as stated"

    @pytest.mark.parametrize("token_source", [None, "self-login"], ids=["unowned", "another-mode"])
    def test_any_other_secret_over_a_mode_stanza_wins_wholesale(self, token_source):
        reg = ClusterRegistry()
        found = dataclasses.replace(ClusterConfig("rnd", "https://api.rnd.example:6443", token_value="sha256~t-aaaaaaaa",
                                                  source="secret:gsd-cluster-rnd", visibility="self-only",
                                                  enabled=False), token_source=token_source)
        reg.replace([found], [], at="t")
        served, = [c for c in reg.merge([RND]) if c.name == "rnd"]
        assert served == found and (served.visibility, served.enabled) == ("self-only", False)

    def test_a_plain_values_entry_is_replaced_wholesale_and_a_secret_with_no_entry_is_appended(self):
        reg = ClusterRegistry()
        east = ClusterConfig("east", "https://api.east.example:6443", token_value="sha256~t-aaaaaaaa",
                             source="secret:gsd-cluster-east", token_source="remote-lookup")
        tab = ClusterConfig("tab", "https://api.tab.example:6443", token_value="sha256~t-bbbbbbbb", source="secret:gsd-cluster-tab")
        reg.replace([east, tab], [], at="t")
        stanza = ClusterConfig("east", "https://api.east.example:6443", token_env="X", visibility="self-only")
        merged = reg.merge([stanza])
        assert [c.name for c in merged] == ["east", "tab"]
        assert merged[0] is east, "no connection mode on the stanza: the Secret wins, policy included"

    @pytest.mark.parametrize("stanza_enabled,secret_enabled,served", [(False, True, False), (True, False, False),
                                                                       (True, True, True)])
    def test_either_side_may_disable_an_owned_secret(self, stanza_enabled, secret_enabled, served):
        reg = ClusterRegistry()
        reg.replace([dataclasses.replace(ClusterConfig("rnd", "https://api.rnd.example:6443", token_value="sha256~t-aaaaaaaa",
                                                       source="secret:gsd-cluster-rnd", enabled=secret_enabled),
                                         token_source="remote-lookup")], [], at="t")
        merged, = [c for c in reg.merge([dataclasses.replace(RND, enabled=stanza_enabled)]) if c.name == "rnd"]
        assert merged.enabled is served

    def test_replace_keeps_every_compare_false_credential_field(self):
        found = ClusterConfig("rnd", "https://api.rnd.example:6443", token_value="sha256~t-aaaaaaaa", ca_data="PEM",
                              source="secret:gsd-cluster-rnd", token_source="remote-lookup")
        served = dataclasses.replace(found, visibility="self-only", identity="none", enabled=True)
        assert (served.token_value, served.ca_data, served.oauth_username, served.oauth_password) == \
               ("sha256~t-aaaaaaaa", "PEM", None, None)
        assert served.connection_fingerprint() == found.connection_fingerprint()


class TestDiscoveryServesAndSaysTheStanzasPolicy:
    def test_the_resolved_line_prints_the_served_pair_not_the_secrets_own(self, discovering, caplog):
        settings, poller, _ = discovering(RND)
        _Host.secrets = {"gsd-cluster-rnd": _secret("rnd", annotations=OWNED, visibility="self-only", identity="none")}
        with caplog.at_level(logging.INFO, logger="gsd"):
            poller._discover_once()
        assert settings.cluster_policy("rnd") == ("remote-sar", "same-as-host")
        line, = [m for m in caplog.messages if m.startswith("cluster-resolved ") and "cluster=rnd" in m]
        assert "visibility=remote-sar identity=same-as-host enabled=true" in line, line

    def test_an_ownership_flip_alone_logs_the_pair_now_served(self, discovering, caplog):
        settings, poller, _ = discovering(RND)
        _Host.secrets = {"gsd-cluster-rnd": _secret("rnd", visibility="self-only")}
        poller._discover_once()
        assert settings.cluster_policy("rnd") == ("self-only", "none")
        for annotations, pair in ((OWNED, "visibility=remote-sar identity=same-as-host"),
                                  ({}, "visibility=self-only identity=none")):
            _Host.secrets["gsd-cluster-rnd"]["metadata"]["annotations"] = dict(annotations)
            caplog.clear()
            with caplog.at_level(logging.INFO, logger="gsd"):
                poller._discover_once()
            lines = [m for m in caplog.messages if m.startswith("cluster-resolved ") and "cluster=rnd" in m]
            assert lines and pair in lines[-1], caplog.messages

    def test_a_disabled_lookup_stanza_is_not_served_polled_or_reviewed(self, discovering, caplog):
        settings, poller, db = discovering(dataclasses.replace(RND, enabled=False))
        _Host.secrets = {"gsd-cluster-rnd": _secret("rnd", annotations=OWNED, visibility="remote-sar",
                                                    identity="same-as-host", enabled="true")}
        with caplog.at_level(logging.INFO, logger="gsd"):
            poller._discover_once()
        assert settings.cluster("rnd").enabled is False
        assert next(r for r in db.clusters() if r["id"] == "rnd")["enabled"] == 0
        assert any("cluster=rnd" in m and "enabled=false" in m for m in caplog.messages if m.startswith("cluster-resolved "))
        assert RemoteTierResolvers(settings, lambda c: pytest.fail("built for a disabled cluster")).get("rnd") is None


class TestTheLookupWritesThePairItServes:
    @pytest.mark.parametrize("stanza", [RND, dataclasses.replace(RND, visibility="self-only")], ids=["unstated", "self-only"])
    def test_the_pair_the_lookup_writes_is_the_pair_served_before_and_after_discovery(self, discovering, stanza):
        settings, poller, _ = discovering(stanza)
        before = settings.cluster_policy("rnd")
        store(_Host(), "ns", settings.cluster("rnd"), settings,
              SaToken(token=SA_TOKEN, namespace="group-sync-operator", service_account="group-sync-dashboard-cluster-poller"),
              account="ocp-oauth-bind-serviceid")
        data = {k: base64.b64decode(v).decode() for k, v in _Host.secrets["gsd-cluster-rnd"]["data"].items()}
        assert (data["visibility"], data["identity"]) == before
        poller._discover_once()
        assert settings.cluster("rnd").source == "secret:gsd-cluster-rnd"
        assert settings.cluster_policy("rnd") == before
```

#### `local-development/tests/test_multicluster_visibility.py`

`far` states `identity: none` (the tests that need a self-only/none remote); the defaults and the loader's rule.

<!-- block: local-development/tests/test_multicluster_visibility.py | edit -->

```python
        ClusterConfig("far", "https://api.far.example:6443", token_env="X"),   # the defaults
```

```python
        # `identity: none` alone: self-only/none, the default before SPEC_D2b — what the identity-none tests need
        ClusterConfig("far", "https://api.far.example:6443", token_env="X", identity="none"),
```

<!-- block: local-development/tests/test_multicluster_visibility.py | edit -->

```python
    def test_host_is_inherit_same_as_host_and_a_remote_is_self_only_none(self, db):
```

```python
    def test_host_is_inherit_same_as_host_and_a_remote_that_states_nothing_is_remote_sar_same_as_host(self, db):
```

<!-- block: local-development/tests/test_multicluster_visibility.py | edit -->

```python
        assert s.cluster_policy("far") == ("self-only", "none")
        assert s.cluster_policy("east") == ("self-only", "same-as-host")
```

```python
        assert s.cluster_policy("far") == ("self-only", "none"), "identity: none alone keeps self-only"
        assert s.cluster_policy("east") == ("self-only", "same-as-host")
        bare = Settings(clusters=[s.clusters[0], ClusterConfig("near", "https://api.near.example:6443", token_env="X")],
                        db_path=db)
        assert bare.cluster_policy("near") == ("remote-sar", "same-as-host"), "SPEC_D2b: the remote's own RBAC decides"
```

<!-- block: local-development/tests/test_multicluster_visibility.py | edit -->

```python
        assert s.cluster_policy("east") == ("self-only", "none")
```

```python
        assert s.cluster_policy("east") == ("remote-sar", "same-as-host")
```

<!-- block: local-development/tests/test_multicluster_visibility.py | edit -->

```python
            self._load(tmp_path, self.BASE + "    visibility: remote-sar\n")
```

```python
            self._load(tmp_path, self.BASE + "    visibility: remote-sar\n    identity: none\n")
        s = self._load(tmp_path, self.BASE + "    visibility: remote-sar\n")
        assert s.cluster_policy("east") == ("remote-sar", "same-as-host"), "an omitted identity resolves to same-as-host"
```

<!-- block: local-development/tests/test_multicluster_visibility.py | edit -->

```python
        assert settings.cluster_policy("east") == ("self-only", "none")
```

```python
        assert settings.cluster_policy("east") == ("remote-sar", "same-as-host")
```

#### `local-development/tests/test_config.py`

An unstated remote's resolved pair.

<!-- block: local-development/tests/test_config.py | edit -->

```python
        assert s.cluster_policy("first") == ("self-only", "none")
```

```python
        assert s.cluster_policy("first") == ("remote-sar", "same-as-host")   # a remote that states nothing (SPEC_D2b)
```

#### `local-development/tests/test_dashboard_controller.py`

The loader's refusal is the explicit pair; the controller test asks `.get`, which the object offers.

<!-- block: local-development/tests/test_dashboard_controller.py | edit -->

```python
    def test_remote_sar_without_same_as_host_is_still_refused_on_a_first_entry_that_is_not_the_host(self, tmp_path):
```

```python
    def test_remote_sar_with_identity_none_is_still_refused_on_a_first_entry_that_is_not_the_host(self, tmp_path):
```

<!-- block: local-development/tests/test_dashboard_controller.py | edit -->

```python
            _load(tmp_path, east="    visibility: remote-sar")
```

```python
            _load(tmp_path, east="    visibility: remote-sar\n    identity: none")
        s = _load(tmp_path, east="    visibility: remote-sar")
        assert s.cluster_policy("ocp-east") == ("remote-sar", "same-as-host"), "an omitted identity is same-as-host"
```

<!-- block: local-development/tests/test_dashboard_controller.py | edit -->

```python
        assert "home" not in app.state.remote_tier_resolvers
```

```python
        remotes = app.state.remote_tier_resolvers
        assert remotes.get("home") is None, "the controller is never asked as a remote"
        assert remotes.get("ocp-east")._kube.cluster.name == "ocp-east", "a remote is reviewed on its own API"
```

#### `local-development/tests/test_clusterconfig.py`

The explicit pair is the refused one; the discovered `east` is remote-sar, and no remote is asked.

<!-- block: local-development/tests/test_clusterconfig.py | edit -->

```python
        ({"visibility": "remote-sar"}, "visibility-invalid"),
```

```python
        ({"visibility": "remote-sar", "identity": "none"}, "identity-invalid"),
```

<!-- block: local-development/tests/test_clusterconfig.py | edit -->

```python
        # The read route is gated on clusterconfig:view, NOT the wide tier (#230, the operator's
```

```python
        # `east` states no policy, so it is remote-sar (SPEC_D2b); no resolver here, so no made-up remote is asked
        # and east is self for every reader, fail closed.
        app.state.remote_tier_resolvers = {}
        # The read route is gated on clusterconfig:view, NOT the wide tier (#230, the operator's
```

<!-- block: local-development/tests/test_clusterconfig.py | edit -->

```python
                              "labels": {"environment": "prod"}, "visibility": "self-only", "identity": "none",
```

```python
                              "labels": {"environment": "prod"}, "visibility": "remote-sar", "identity": "same-as-host",
```

<!-- block: local-development/tests/test_clusterconfig.py | edit -->

```python
        # served, and narrowed: a Secret-sourced cluster is self-only by default (D2), so the administrator view
        # refuses (403) rather than not knowing the cluster (404)
```

```python
        # served, and narrowed: a Secret-sourced cluster that states nothing is remote-sar (SPEC_D2b) and no resolver
        # answers here, so the administrator view refuses (403) rather than not knowing the cluster (404)
```

<!-- block: local-development/tests/test_clusterconfig.py | edit -->

```python
        store = app.state.store
```

```python
        app.state.remote_tier_resolvers = {}   # east is remote-sar (SPEC_D2b): self, with no remote asked
        store = app.state.store
```

<!-- block: local-development/tests/test_clusterconfig.py | edit -->

```python
            assert before["east"]["visibility"] == {"policy": "self-only", "scope": "self"}
```

```python
            assert before["east"]["visibility"] == {"policy": "remote-sar", "scope": "self"}
```

<!-- block: local-development/tests/test_clusterconfig.py | edit -->

```python
            app.state.tier_resolver = _MapResolver({"root": "all", "auditor": "all", "viewer": "all"})
```

```python
            app.state.tier_resolver = _MapResolver({"root": "all", "auditor": "all", "viewer": "all"})
            app.state.remote_tier_resolvers = {}   # the discovered east is remote-sar (SPEC_D2b); no remote is asked
```

#### `local-development/tests/test_clusterconfig_tab.py`

The same, for the tab's routes.

<!-- block: local-development/tests/test_clusterconfig_tab.py | edit -->

```python
               {"name": "west", "server": "https://api.west.example:6443", "visibility": "self-only", "identity": "none", "enabled": "true"}
```

```python
               {"name": "west", "server": "https://api.west.example:6443", "visibility": "remote-sar", "identity": "same-as-host", "enabled": "true"}
```

<!-- block: local-development/tests/test_clusterconfig_tab.py | edit -->

```python
        (dict(visibility="remote-sar"), "visibility-invalid"),
```

```python
        (dict(visibility="remote-sar", identity="none"), "identity-invalid"),
```

<!-- block: local-development/tests/test_clusterconfig_tab.py | edit -->

```python
        # The Cluster Configurations tier's own two seams (#230): root holds both levels here, and
```

```python
        app.state.remote_tier_resolvers = {}   # the discovered east is remote-sar (SPEC_D2b); no remote is asked
        # The Cluster Configurations tier's own two seams (#230): root holds both levels here, and
```

<!-- block: local-development/tests/test_clusterconfig_tab.py | edit -->

```python
        app.state.tier_resolver = _MapResolver({"root": "all", "viewer": "all", "auditor": "all"})
```

```python
        app.state.tier_resolver = _MapResolver({"root": "all", "viewer": "all", "auditor": "all"})
        app.state.remote_tier_resolvers = {}   # the discovered east is remote-sar (SPEC_D2b); no remote is asked
```

#### `local-development/tests/test_clusterconfig_logging.py`

The served pair on the `cluster-resolved` line.

<!-- block: local-development/tests/test_clusterconfig_logging.py | edit -->

```python
        serves as `self-only`."""
```

```python
        serves otherwise. A Secret that states nothing is served `remote-sar` + `same-as-host` (SPEC_D2b)."""
```

<!-- block: local-development/tests/test_clusterconfig_logging.py | edit -->

```python
        assert "visibility=self-only" in line and "identity=none" in line, line
```

```python
        assert "visibility=remote-sar" in line and "identity=same-as-host" in line, line
```

<!-- block: local-development/tests/test_clusterconfig_logging.py | edit -->

```python
        `self-only` for an omitted visibility, so `visibility: inherit` is a WIDENING, and the
        shape read it as nothing while the log claimed `inherit` all along."""
```

```python
        `remote-sar` + `same-as-host` for an omitted pair (SPEC_D2b), so `visibility: inherit` is a
        CHANGE, and the shape read it as nothing while the log claimed `inherit` all along."""
```

<!-- block: local-development/tests/test_clusterconfig_logging.py | edit -->

```python
        assert omitted == _cluster_shape(ClusterConfig(visibility="self-only", identity="none", **base))
```

```python
        assert omitted == _cluster_shape(ClusterConfig(visibility="remote-sar", identity="same-as-host", **base))
        assert omitted != _cluster_shape(ClusterConfig(visibility="self-only", identity="none", **base))
```

#### `local-development/tests/test_fleet_lookup.py`

The pair the lookup writes for an unstated stanza.

<!-- block: local-development/tests/test_fleet_lookup.py | edit -->

```python
        assert obj["stringData"]["visibility"] == "self-only" and obj["stringData"]["identity"] == "none"
```

```python
        assert obj["stringData"]["visibility"] == "remote-sar" and obj["stringData"]["identity"] == "same-as-host"
```

#### `local-development/tests/test_home_api.py`

Two docstrings that named the old default.

<!-- block: local-development/tests/test_home_api.py | edit -->

```python
    """The host and two remotes that treat the host's username as their own (`identity: same-as-host`);
    a remote left at the default (`none`) vouches for nobody and must not appear in `elsewhere`."""
```

```python
    """The host and two remotes that treat the host's username as their own (`identity: same-as-host`, so
    `remote-sar` since SPEC_D2b; Home asks no resolver either way); a remote that states `identity: none`
    vouches for nobody and must not appear in `elsewhere`."""
```

<!-- block: local-development/tests/test_home_api.py | edit -->

```python
    """A remote at the default identity policy (`none`) does not treat the host's username as its own, so
    nothing there is this person's: it is left out of `elsewhere`, its memberships out of the total."""
```

```python
    """A remote that states `identity: none` does not treat the host's username as its own, so nothing there
    is this person's: it is left out of `elsewhere`, its memberships out of the total."""
```

#### `local-development/tests/test_visibility.py`

A fixture comment that named the old default.

<!-- block: local-development/tests/test_visibility.py | edit -->

```python
        # c2 inherits explicitly: since D2 a second cluster is self-only by default, and these
        # tests pin the HOST tier's behaviour on every cluster (SPEC_D2 §D2.6 names this fixture).
```

```python
        # c2 inherits explicitly: a second cluster that states nothing is decided by its own RBAC
        # (remote-sar, SPEC_D2b), and these tests pin the HOST tier's behaviour on every cluster
        # (SPEC_D2 §D2.6 names this fixture).
```

#### `local-development/tests/test_cluster_stanza_matrix.py`

The matrix follows `docs/CLUSTER_STANZA.md`.

<!-- block: local-development/tests/test_cluster_stanza_matrix.py | edit -->

```python
    ("enabled false", [HOST, {**REMOTE, "tokenEnv": "R", "enabled": False}]),
```

```python
    ("enabled false", [HOST, {**REMOTE, "tokenEnv": "R", "enabled": False}]),
    ("remote-sar alone", [HOST, {**REMOTE, "tokenEnv": "R", "visibility": "remote-sar"}]),
    ("saTokenLookup + remote-sar", [HOST, {**REMOTE, "saTokenLookup": True, "visibility": "remote-sar"}]),
```

<!-- block: local-development/tests/test_cluster_stanza_matrix.py | edit -->

```python
    ("remote-sar without same-as-host", [HOST, {**REMOTE, "tokenEnv": "R", "visibility": "remote-sar"}], True),
```

```python
    ("remote-sar with identity none", [HOST, {**REMOTE, "tokenEnv": "R", "visibility": "remote-sar", "identity": "none"}], True),
```

#### `local-development/tests/test_chart_connection_modes.py`

`remote-sar` beside `saTokenLookup` renders.

<!-- block: local-development/tests/test_chart_connection_modes.py | edit -->

```python
    def test_remote_sar_with_the_lookup_is_refused_by_name(self, tmp_path):
        ok, out = _render_values(tmp_path, [HOME, {**RND, "visibility": "remote-sar", "identity": "same-as-host"}], values=WRITES)
        assert not ok and "clusters[1] (shared-rnd): visibility remote-sar with saTokenLookup" in out
```

```python
    def test_remote_sar_with_the_lookup_renders_and_only_identity_none_beside_it_is_refused(self, tmp_path):
        """SPEC_D2b: the lookup's Secret is asked like any other remote, so `remote-sar` is accepted beside it."""
        ok, out = _render_values(tmp_path, [HOME, {**RND, "visibility": "remote-sar"}], values=WRITES)
        assert ok, out[-600:]
        ok, out = _render_values(tmp_path, [HOME, {**RND, "visibility": "remote-sar", "identity": "none"}], values=WRITES)
        assert not ok and "clusters[1] (shared-rnd): visibility remote-sar needs identity: same-as-host" in out
```

#### `local-development/tests/test_chart_strategy.py`

The render's refusal and NOTES' defaults.

<!-- block: local-development/tests/test_chart_strategy.py | edit -->

```python
    def test_remote_sar_without_same_as_host_is_refused(self):
        ok, out = self._render(**{"clusters[1].visibility": "remote-sar"})
        assert not ok and "needs identity: same-as-host" in out
```

```python
    def test_remote_sar_with_identity_none_is_refused(self):
        ok, out = self._render(**{"clusters[1].visibility": "remote-sar", "clusters[1].identity": "none"})
        assert not ok and "needs identity: same-as-host" in out
        ok, _ = self._render(**{"clusters[1].visibility": "remote-sar"})
        assert ok, "an omitted identity resolves to same-as-host (SPEC_D2b)"
```

<!-- block: local-development/tests/test_chart_strategy.py | edit -->

```python
                         "first: visibility self-only (default), identity none (default)"], lines
```

```python
                         "first: visibility remote-sar (default), identity same-as-host (default)"], lines
```

<!-- block: local-development/tests/test_chart_strategy.py | edit -->

```python
                         "host: visibility self-only (default), identity none (default)"], lines
```

```python
                         "host: visibility remote-sar (default), identity same-as-host (default)"], lines
```

#### `local-development/tests/test_chart_dashboard_controller.py`

NOTES' defaults.

<!-- block: local-development/tests/test_chart_dashboard_controller.py | edit -->

```python
                         "ocp-east: visibility self-only (default), identity none (default)"], lines
```

```python
                         "ocp-east: visibility remote-sar (default), identity same-as-host (default)"], lines
```

#### `local-development/tests/test_ui.py`

The restricted fixtures state the pair their tests were written against; the Cluster Configurations page's rows; D5's fixture and class.

<!-- block: local-development/tests/test_ui.py | edit -->

```python
    kw = {"oauth_proxy_enabled": True} if restricted else {"view_restrictions_enabled": False}
```

```python
    kw = {"oauth_proxy_enabled": True} if restricted else {"view_restrictions_enabled": False}
    # The remotes state `identity: none` — self-only/none, the pair these tests were written against. Left
    # unstated they are remote-sar (SPEC_D2b), and a restricted server would ask their made-up APIs.
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
                  ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="Y")]
                 + [ClusterConfig(cid, f"https://api.{cid}.example.internal:6443", token_env="Z") for cid in extra],
        db_path=db, login_capture_enabled=True, **kw,
```

```python
                  ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="Y", identity="none")]
                 + [ClusterConfig(cid, f"https://api.{cid}.example.internal:6443", token_env="Z", identity="none")
                    for cid in extra],
        db_path=db, login_capture_enabled=True, **kw,
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
            ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="Y"),
        ],
        db_path=db,
        login_capture_enabled=True,
```

```python
            # `identity: none`: self-only/none, the pair these tests were written against (Home's refusal on
            # prod-east among them). Left unstated it is remote-sar (SPEC_D2b), and its made-up API is asked.
            ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="Y", identity="none"),
        ],
        db_path=db,
        login_capture_enabled=True,
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
        not the host cluster and its identity policy is the default `none` — it does not treat the host's
```

```python
        not the host cluster and the fixture states its identity policy `none` — it does not treat the host's
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
        # what the nav lists, and a several-cluster run needs a second target the service can render.
```

```python
        # what the nav lists, and a several-cluster run needs a second target the service can render.
        # prod-east states `identity: none` (self-only/none, the pair these tests were written against): left
        # unstated it is remote-sar (SPEC_D2b), and whoami would ask its made-up API on every page load.
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
                  ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="X")],
```

```python
                  ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="X", identity="none")],
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
        monkeypatch.setattr("gsd.api.own_namespace", lambda: "gsd-ns")
```

```python
        monkeypatch.setattr("gsd.api.own_namespace", lambda: "gsd-ns")
        # The discovered Secrets state no policy, so they are remote-sar (SPEC_D2b): no resolver here, so no
        # made-up remote is asked and each is the self tier for every reader, fail closed.
        monkeypatch.setattr(app.state, "remote_tier_resolvers", {})
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
        assert "bearerToken" in east and "trusted-bundle" in east and "environment=prod" in east and "self-only" in east
```

```python
        assert "bearerToken" in east and "trusted-bundle" in east and "environment=prod" in east and "remote-sar" in east
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
    def test_the_yaml_twin_follows_the_form_and_the_ca_mode(self, page, cc_rig):
```

```python
    def test_the_form_offers_remote_sar_and_starts_on_the_default_pair(self, page, cc_rig):
        """SPEC_D2b §3.3: the form starts on the pair a remote that states nothing resolves to, and offers
        remote-sar with its meaning; same-as-host says how a reader is matched (design D3)."""
        base, host, settings = cc_rig
        _open_as(page, base, "root")
        page.click("#tab-clusters"); page.wait_for_selector("#cc-form")
        assert page.eval_on_selector("#cc-visibility", "s => s.value") == "remote-sar"
        assert page.eval_on_selector("#cc-identity", "s => s.value") == "same-as-host"
        assert page.eval_on_selector_all("#cc-visibility option", "os => os.map(o => o.value)") == \
               ["inherit", "self-only", "hidden", "remote-sar"]
        assert "this cluster's own RBAC decides, for the reader's OpenShift username" in \
               page.locator("#cc-visibility option[value='remote-sar']").inner_text()
        assert "matched by OpenShift username" in page.locator("#cc-identity option[value='same-as-host']").inner_text()

    def test_the_yaml_twin_follows_the_form_and_the_ca_mode(self, page, cc_rig):
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
        assert written["metadata"]["annotations"] == {"groupsync-dashboard.io/managed-by": "ui"}
```

```python
        assert written["metadata"]["annotations"] == {"groupsync-dashboard.io/managed-by": "ui"}
        import base64 as _b64, json as _json
        assert [_b64.b64decode(written["data"][k]).decode() for k in ("visibility", "identity")] == \
               ["remote-sar", "same-as-host"], "the form's defaults are the default pair (SPEC_D2b §3.3)"
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
        page.wait_for_function("() => (document.getElementById('cc-rotate-msg-west') || {innerText: ''}).innerText.includes('overwritten')")
        import base64 as _b64, json as _json
```

```python
        page.wait_for_function("() => (document.getElementById('cc-rotate-msg-west') || {innerText: ''}).innerText.includes('overwritten')")
```

<!-- block: local-development/tests/test_ui.py | edit -->

```python
            assert "users picked on crc-local was cleared" in " ".join(page.locator("#report-cluster-note").inner_text().split())
            assert not errors, errors
        finally:
            ctx.close()
```

```python
            assert "users picked on crc-local was cleared" in " ".join(page.locator("#report-cluster-note").inner_text().split())
            assert not errors, errors
        finally:
            ctx.close()


# ── D5 (SPEC_D2b §3.11): the rule that decided the selected cluster's view, beside the selector ───────────────
WHY_REMOTES = {
    "far-sar": {},                                                     # states nothing: remote-sar + same-as-host
    "far-self": {"visibility": "self-only", "identity": "same-as-host"},
    "far-none": {"identity": "none"},                                  # identity none alone: self-only + none
    "far-inherit": {"visibility": "inherit"},
}


@pytest.fixture(scope="module")
def why_server(tmp_path_factory):
    """The scoped shape (proxy on, restrictions on) with one remote per rule. No remote is asked: far-sar's
    decision is a `_TierByName` on the published seam, `app.state.remote_tier_resolvers` — wide for `root`,
    self for everyone else, which is also what an unreachable remote serves."""
    db = str(tmp_path_factory.mktemp("gsd-why") / "ui.db")
    _seed(db)
    store = Store(db)
    try:
        for cid in WHY_REMOTES:
            store.upsert_cluster(cid, f"https://api.{cid}.example:6443", True)
            store.record_poll(cid, "ok", None)
    finally:
        store.close()
    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")]
                 + [ClusterConfig(cid, f"https://api.{cid}.example:6443", token_env="Y", **kw)
                    for cid, kw in WHY_REMOTES.items()],
        db_path=db, oauth_proxy_enabled=True,
    )
    app = build_app(settings, run_poller=False)
    app.state.tier_resolver = _TierByName()
    app.state.remote_tier_resolvers = {"far-sar": _TierByName()}
    # The other seams answer by name too, so nothing here builds a resolver on a cluster the test does not have.
    app.state.usage_tier_resolver = _TierByName()
    app.state.clusterconfig_view_resolver = _TierByName()
    app.state.clusterconfig_manage_resolver = _TierByName()
    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=srv.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    for _ in range(100):
        try:
            if httpx.get(f"{base}/healthz", timeout=1).status_code == 200:
                break
        except httpx.HTTPError:
            time.sleep(0.1)
    else:
        raise RuntimeError("dashboard server did not start")
    yield base
    srv.should_exit = True
    thread.join(timeout=5)


def _why(p) -> str | None:
    el = p.locator("#scope-why")
    return el.inner_text() if el.count() else None


def _select_and_read(p, cluster: str, expected: str) -> None:
    p.select_option("#f-cluster", cluster)
    p.wait_for_function("(c) => view.cluster === c", arg=cluster)
    p.wait_for_function("(t) => { const e = document.getElementById('scope-why'); return !!e && e.textContent === t; }",
                        arg=expected, timeout=10_000)


class TestTheRuleBesideTheSelector:
    """D5, directed 2026-09-23 and built in SPEC_D2b (§3.11): one muted line beside the cluster selector names
    the rule that decided this reader's view of the SELECTED cluster, read off whoami's
    `visibility.clusters[id]` = {policy, identity, scope} and never derived. It follows the selector, it never
    tells a denial from a remote that could not be asked (the wire does not), and it is absent wherever there is
    no rule to state."""

    LINES = {
        ("root", "crc-local"): "The host decides your view of this cluster.",
        ("alice", "crc-local"): "The host decides your view of this cluster.",
        ("root", "far-sar"): "This cluster's own RBAC gives you the full view.",
        ("alice", "far-sar"): "This cluster's own RBAC shows your own rows, or could not be asked.",
        ("alice", "far-self"): "This cluster is self-only: everyone sees their own rows.",
        ("alice", "far-none"): "This cluster is self-only and does not treat your identity as its own.",
        ("alice", "far-inherit"): "The host decides your view of this cluster.",
    }

    def test_every_line_is_one_short_sentence(self):
        """One muted line, not a paragraph: each sentence fits about seventy characters (the design's D5)."""
        assert all(len(line) <= 70 and line.endswith(".") and line.count(". ") == 0 for line in self.LINES.values())

    @pytest.mark.parametrize("user,cluster", list(LINES), ids=[f"{u}-{c}" for u, c in LINES])
    def test_each_rule_is_stated_for_the_selected_cluster_on_home(self, page, why_server, user, cluster):
        p = _home(page, why_server, user)
        _select_and_read(p, cluster, self.LINES[(user, cluster)])
        assert p.evaluate("() => view.page") == "home"
        line = p.locator("#filters #scope-why")
        assert line.count() == 1 and "filterbar-note" in (line.get_attribute("class") or ""), "muted, in the bar"
        assert p.evaluate("(c) => data.whoami.visibility.clusters[c].policy", cluster) == \
               {"crc-local": "inherit", "far-sar": "remote-sar", "far-self": "self-only",
                "far-none": "self-only", "far-inherit": "inherit"}[cluster]

    def test_the_line_follows_the_selector_across_every_rule_and_back(self, page, why_server):
        p = _home(page, why_server, "alice")
        p.wait_for_function("() => (document.getElementById('scope-why') || {}).textContent === "
                            "'The host decides your view of this cluster.'")
        for cluster in ("far-sar", "far-self", "far-none", "far-inherit", "crc-local"):
            _select_and_read(p, cluster, self.LINES[("alice", cluster)])
        p.locator("button[data-nav='groups']").click()
        p.wait_for_function("() => view.page === 'groups'")
        _select_and_read(p, "far-sar", self.LINES[("alice", "far-sar")])

    def test_the_line_is_the_wires_decision_not_a_derived_one(self, page, why_server):
        """Flip the payload's scope and the line follows it: nothing on the page recomputes a tier."""
        p = _home(page, why_server, "alice")
        _select_and_read(p, "far-sar", self.LINES[("alice", "far-sar")])
        p.evaluate("() => { data.whoami.visibility.clusters['far-sar'].scope = 'all'; render(); }")
        assert _why(p) == self.LINES[("root", "far-sar")]

    def test_no_line_on_the_fleet_view_or_a_fleet_wide_page(self, page, why_server):
        p = _open_as(page, why_server, "root")
        p.goto(f"{why_server}/#page=overview")
        # The bar is repainted for the fleet position when its selector reads "all clusters" (value "").
        p.wait_for_function("() => { const s = document.getElementById('f-cluster'); "
                            "return view.page === 'overview' && view.cluster === null && !!s && s.value === ''; }")
        assert _why(p) is None, "all clusters is not a cluster: no rule decided it"
        _select_and_read(p, "far-sar", self.LINES[("root", "far-sar")])
        p.goto(f"{why_server}/#page=usage")
        p.wait_for_function("() => view.page === 'usage' && !document.getElementById('f-cluster')")
        assert _why(p) is None

    def test_no_line_without_an_identity_or_with_restrictions_off(self, page, why_server, server, idle_server):
        page.goto(f"{why_server}/#page=overview&cluster=far-sar")          # no X-Forwarded-User: not authenticated
        page.wait_for_selector("#f-cluster")
        page.wait_for_function("() => data.whoami !== null")
        assert _why(page) is None
        for base in (server, idle_server):                                  # restrictions off: proxy off, then on
            page.set_extra_http_headers({"X-Forwarded-User": "alice"})
            page.goto(f"{base}/#page=overview&cluster=crc-local")
            page.wait_for_selector("#f-cluster")
            page.wait_for_function("() => data.whoami !== null")
            assert _why(page) is None, base

    def test_the_line_wraps_inside_a_phone_width(self, page, why_server):
        p = _home(page, why_server, "alice")
        p.set_viewport_size({"width": 375, "height": 740})
        _select_and_read(p, "far-sar", self.LINES[("alice", "far-sar")])
        assert p.evaluate("() => document.documentElement.scrollWidth <= innerWidth")
        assert p.evaluate("() => document.getElementById('scope-why').getBoundingClientRect().right <= innerWidth")
```

#### Corrections from the review of the blocks

Written after the review of the 154 blocks (Orchestrator's notes): OB1-lite's twenty (the per-cluster routes, the alerts' predicate, the unaskable resolvers and their tests), Codex's three wording and three design-document blocks, and the orchestrator's twenty (`kube.py`'s hold docstring, the design document, the diagram page and `docs/diagrams/render.py`), then OB3's nine from the confirmation pass (`docs/ACCESS_CONTROL.md`'s hold, the design document's and the diagram page's remaining D1/D5 and lab statements), then OB1-lite's two from the review of that pass (`shared-qa` "has always been `self-only`", in the design document and on the diagram page), then the orchestrator's ten from Codex's review of it (the renderer's 375 px page and its test, and the design document's and the diagram page's status, D2, D5 and D6 statements). Each applies to the files as the earlier blocks leave them.

<!-- block: local-development/gsd/api.py | edit -->

```python
        if policy == VISIBILITY_REMOTE_SAR:
            # Read off app.state PER REQUEST, the published seam, so a test can substitute one
```

```python
        if policy == VISIBILITY_REMOTE_SAR:
            # Decided before this handler's read snapshot opened (@tier_first, SPEC_D2b §3.10): served
            # from the request, so the remote is asked once and the decision is still counted once, here.
            decided = getattr(request.state, "remote_tiers", {})
            if cluster_id in decided:
                return _decide(viewer, None, lambda _viewer: decided[cluster_id])
            # Read off app.state PER REQUEST, the published seam, so a test can substitute one
```

<!-- block: local-development/gsd/api.py | edit -->

```python
    def is_served(cluster_id: str) -> bool:
```

```python
    def tier_first(fn):
        """Decide the named cluster's remote-sar tier BEFORE the @consistent snapshot below opens
        (SPEC_D2b §3.10, the per-cluster routes). Under remote-sar a decision is a group list and a
        SubjectAccessReview on that cluster, up to TIER_CHECK_TIMEOUT_SECONDS each, and the default makes
        every remote that states nothing one; a snapshot held across that call pins the WAL read-mark
        (store.read_snapshot). Applied ABOVE @consistent, and only to a handler that decides the named
        cluster's tier right after require_cluster, so it asks nothing the handler would not have asked.
        The answer is kept on the request and viewer_scope serves it from there; any other policy, an
        unserved cluster or no viewer asks nothing here, and viewer_scope decides as before."""
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            request, cluster_id = kwargs.get("request"), kwargs.get("cluster_id")
            viewer = trusted_viewer(request) if isinstance(request, Request) else None
            if (restrict and viewer and isinstance(cluster_id, str) and is_served(cluster_id)
                    and settings.cluster_policy(cluster_id)[0] == VISIBILITY_REMOTE_SAR):
                resolver = (getattr(app.state, "remote_tier_resolvers", None) or {}).get(cluster_id)
                if resolver is not None:
                    try:
                        request.state.remote_tiers = {cluster_id: resolver.resolve(viewer)}
                    except Exception:  # noqa: BLE001 — viewer_scope asks again and fails closed, as before
                        pass
            return fn(*args, **kwargs)
        return wrapper

    def is_served(cluster_id: str) -> bool:
```

<!-- block: local-development/gsd/api.py | edit -->

```python
    def vouches_for_host_identity(cluster_id: str) -> bool:
```

```python
    def alert_scopes(request: Request) -> dict[str, str]:
        """served_scopes for /api/alerts, whose walk is its own (SPEC_D2b §3.10): it skips a row the store holds
        at enabled=0 even while the configuration serves that cluster — a re-joined cluster before the leader's
        next cycle writes its row, or any cycle on a replica that is not the leader — and it decides a row still
        enabled=1 whose configuration has gone. Decided on list_alerts' own predicate, so the feed asks no remote
        its loop would not have asked, and leaves none to decide inside its snapshot."""
        return {row["id"]: viewer_scope(request, row["id"])[1] for row in store.clusters()
                if row["enabled"] and settings.cluster_policy(row["id"])[0] != VISIBILITY_HIDDEN}

    def vouches_for_host_identity(cluster_id: str) -> bool:
```

<!-- block: local-development/gsd/api.py | edit -->

```python
    def list_alerts(request: Request, scopes: dict[str, str] = Depends(served_scopes)) -> dict:
```

```python
    def list_alerts(request: Request, scopes: dict[str, str] = Depends(alert_scopes)) -> dict:
```

<!-- block: local-development/gsd/api.py | after:     @app.get("/api/clusters/{cluster_id}/groups/{name}") -->

```python
    @tier_first
```

<!-- block: local-development/gsd/api.py | after:     @app.get("/api/clusters/{cluster_id}/users") -->

```python
    @tier_first
```

<!-- block: local-development/gsd/api.py | after:     @app.get("/api/clusters/{cluster_id}/users/{name}") -->

```python
    @tier_first
```

<!-- block: local-development/gsd/api.py | after:     @app.get("/api/clusters/{cluster_id}/logins") -->

```python
    @tier_first
```

<!-- block: local-development/gsd/api.py | after:     @app.get("/api/clusters/{cluster_id}/cluster-access") -->

```python
    @tier_first
```

<!-- block: local-development/gsd/api.py | after:     @app.get("/api/clusters/{cluster_id}/bindings/findings") -->

```python
    @tier_first
```

<!-- block: local-development/gsd/api.py | after:     @app.get("/api/clusters/{cluster_id}/namespaces") -->

```python
    @tier_first
```

<!-- block: local-development/gsd/api.py | after:     @app.get("/api/clusters/{cluster_id}/namespaces/{name}") -->

```python
    @tier_first
```

<!-- block: local-development/gsd/api.py | after:     @app.get("/api/clusters/{cluster_id}/home") -->

```python
    @tier_first
```

<!-- block: local-development/gsd/api.py | after:     @app.get("/api/clusters/{cluster_id}/user-bindings") -->

```python
    @tier_first
```

<!-- block: local-development/gsd/api.py | after:     @app.get("/api/clusters/{cluster_id}/kyverno") -->

```python
    @tier_first
```

<!-- block: local-development/gsd/api.py | after:     @app.get("/api/clusters/{cluster_id}/membership-changes") -->

```python
    @tier_first
```

<!-- block: local-development/gsd/api.py | after:     @app.get("/api/clusters/{cluster_id}/binding-changes") -->

```python
    @tier_first
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
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
```

```python
    def get(self, cluster_id: str) -> TierResolver | None:
        host = self._settings.host_cluster()
        askable = {c.name: c for c in self._settings.effective_clusters()
                   if c.enabled and c.credential_pending is None
                   and (host is None or c.name != host.name)
                   and remote_policy(c.visibility, c.identity) == (VISIBILITY_REMOTE_SAR, IDENTITY_SAME_AS_HOST)}
        cluster = askable.get(cluster_id)
        with self._lock:
            # Every resolver whose cluster is no longer askable is dropped, not only the one asked about: a
            # retired or disabled cluster is never served, so nobody asks for it again, and its resolver holds
            # the configuration it was built on — the Secret's credential included — for the life of the
            # process (the rule the poller's _LAST_TOKEN states: a credential does not outlive its configuration).
            for name in [n for n in self._built if n not in askable]:
                del self._built[name]
        if cluster is None:
            return None
        key = cluster.connection_fingerprint()
        with self._lock:
            held = self._built.get(cluster_id)
```

<!-- block: local-development/tests/test_remote_sar_default.py | edit -->

```python
        assert len(depths) == 4 and max(depths) == 0, f"a tier was decided inside a read snapshot: {depths}"
```

```python
        assert len(depths) == 4 and max(depths) == 0, f"a tier was decided inside a read snapshot: {depths}"

    @pytest.mark.parametrize("path", (*PERSON_SCOPED, *ADMINISTRATOR, "namespaces/ns1"))
    def test_a_named_remotes_tier_is_decided_once_and_before_the_routes_read_snapshot(self, tmp_path, path):
        """The per-cluster routes are @consistent too, and each decides the named cluster's tier: under the
        default that is the remote's own review, which must not run with the snapshot's read-mark held."""
        app = _unstated_app(tmp_path, None)
        store = app.state.store
        depths: list[int] = []

        class Probe:
            def resolve(self, viewer: str) -> str:
                depths.append(getattr(store._local, "read_depth", 0))
                return "all"
        app.state.remote_tier_resolvers = {"far": Probe()}
        with TestClient(app) as c:
            r = c.get(f"/api/clusters/far/{path}", headers=ALICE)
        assert r.status_code == 200, (path, r.text)                 # the decision made first is the one served
        assert depths == [0], f"{path}: the remote was asked {len(depths)} time(s), at snapshot depth {depths}"

    def test_a_route_that_decides_no_tier_asks_the_remote_nothing(self, tmp_path):
        remote = _Map({"alice": "all"})
        with TestClient(_unstated_app(tmp_path, remote)) as c:
            c.get("/api/clusters/far/groupsyncs/any/events", headers=ALICE)
        assert remote.calls == 0

    def test_alerts_ask_no_remote_that_their_walk_skips(self, tmp_path):
        """A row at enabled=0 while the configuration serves the cluster (a re-joined cluster before the leader's
        next cycle, or a replica that is not the leader): list_alerts skips it, so nothing may ask its remote."""
        remote = _Map({"alice": "all"})
        app = _unstated_app(tmp_path, remote)
        with TestClient(app) as c:
            app.state.store.upsert_cluster("far", "https://api.far.example:6443", False)
            assert c.get("/api/alerts", headers=ALICE).status_code == 200
        assert remote.calls == 0, f"the remote of a row the feed skips was asked {remote.calls} time(s)"
```

<!-- block: local-development/tests/test_remote_tier_resolvers.py | edit -->

```python
    def test_one_configuration_snapshot_per_lookup(self, tmp_path):
```

```python
    @pytest.mark.parametrize("case", ["retired", "disabled"])
    def test_a_cluster_nobody_asks_about_again_keeps_no_resolver_or_credential(self, tmp_path, case):
        """A retired or disabled cluster is not served, so viewer_scope never asks the pool for it again: the next
        lookup of ANY remote must drop its resolver, and with it the configuration carrying the Secret's token."""
        settings = _settings(tmp_path)
        settings.cluster_registry.replace([_secret(), _secret("west")], [], at="t0")
        pool = RemoteTierResolvers(settings, _Built())
        assert pool.get("east") is not None and pool.get("west") is not None
        gone = [_secret("west")] if case == "retired" else [_secret(enabled=False), _secret("west")]
        settings.cluster_registry.replace(gone, [], at="t1")
        assert pool.get("west") is not None
        assert "east" not in pool._built, "a resolver outlived its cluster's configuration"

    def test_one_configuration_snapshot_per_lookup(self, tmp_path):
```

<!-- block: charts/group-sync-dashboard/README.md | edit -->
```markdown
| `clusters[].visibility` | `inherit` on the hosting entry; `remote-sar` on a remote that states neither key; `self-only` on a remote that states only `identity: none` | `inherit` — the host's tier decides (the old behaviour); `self-only` — nobody is wide on this cluster; `hidden` — polled and alerted on, never served through `/api` (404 like an unknown id); `remote-sar` — that cluster's own RBAC decides through the same SubjectAccessReview, created on the remote with its token and its Group objects, cached per reader and cluster; every failure is the self tier, and a failing remote is asked at most once per 30 s. It needs `create subjectaccessreviews` and `list groups` on the remote, which the joining ServiceAccount's ClusterRole carries. `hidden`/`remote-sar` are refused on the hosting entry. **Upgrade note:** on chart 0.53.0 a remote that states neither key moves from `self-only` to `remote-sar` (`docs/CHANGELOG.md`); set `visibility: self-only` and `identity: none` to keep the old view |
```
```markdown
| `clusters[].visibility` | `inherit` on the hosting entry; `remote-sar` on a remote that states neither key; `self-only` on a remote that states only `identity: none` | `inherit` — the host's tier decides (the old behaviour); `self-only` — nobody is wide on this cluster; `hidden` — polled and alerted on, never served through `/api` (404 like an unknown id); `remote-sar` — that cluster's own RBAC decides through the same SubjectAccessReview, created on the remote with its token and its Group objects, cached per reader and cluster; every failure is the self tier. Distinct viewers already in flight may each pay that first attempt; after the first failure lands, the remote is probed at most once per 30 s. It needs `create subjectaccessreviews` and `list groups` on the remote, which the joining ServiceAccount's ClusterRole carries. `hidden`/`remote-sar` are refused on the hosting entry. **Upgrade note:** on chart 0.53.0 a remote that states neither key moves from `self-only` to `remote-sar` (`docs/CHANGELOG.md`); set `visibility: self-only` and `identity: none` to keep the old view |
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->
```yaml
#                             every failure is the self tier, and a failing remote is held for
#                             30 s — asked at most once per hold, whatever the traffic. Needs
```
```yaml
#                             every failure is the self tier. Distinct viewers already in flight
#                             may each pay that first attempt; after the first failure lands, the
#                             remote is held for 30 s and probed at most once per hold, whatever
#                             later traffic. Needs
```

<!-- block: docs/CHANGELOG.md | edit -->
```markdown
- **`remote-sar` for every way a cluster is joined, and the default for a remote (application 0.32.0, chart 0.53.0; #338, `docs/specs/SPEC_D2b_remote_sar_for_every_join.md`).** A remote cluster's own RBAC decides who sees its data wide whether it was declared in values with a token, as a Secret made on the Cluster Configurations tab or by hand, or through `saTokenLookup`: the resolver is found or built per request from the cluster's current configuration and rebuilt when its URL, token or CA changes, with no restart. The Secret parser, the tab and the chart accept `remote-sar`; only an explicit `identity: none` beside it is refused. A failing remote is held for 30 s — asked at most once per hold, whatever the traffic — and the review's error text is redacted before it is truncated. A Secret the lookup wrote for a `saTokenLookup` stanza keeps its credential and serves the stanza's `visibility`, `identity` and `enabled`. `/api/clusters` and `/api/alerts` decide each cluster's tier before they open their database snapshot. One line beside the cluster selector names the rule that decided the selected cluster's view (design D5). **Upgrade note — a remote that states neither `visibility` nor `identity` changes behaviour:** (1) it is `remote-sar` + `same-as-host`, so a reader that cluster's own RBAC allows (`list clusterrolebindings` by default) sees it wide on every tab — Bindings, Operator configs and Kyverno included — with the card's operator-config summary and its administrator alerts; (2) a reader it denies, or one it cannot be asked about, gets their own rows under their OpenShift username on groups, users, logins, cluster access, namespaces, user bindings, the two change feeds and that cluster's Home instead of a 403, and the host's Home counts that cluster's memberships and changes; (3) a remote that states only `identity: same-as-host` moves from `self-only` to `remote-sar` the same way; (4) `/api/whoami`, `/api/clusters` and `/api/alerts` ask that cluster about each reader once per `visibility.tierTtlSeconds`, and an unreachable one costs up to 5 s per remote, one remote after another, on the request that asks — before its hold engages and again on the first request after each hold expires; (5) a remote whose joining ServiceAccount lacks `list groups` or `create subjectaccessreviews` makes `GroupSyncDashboardVisibilityChecksFailing` fire (the pod log names the cluster; the metric does not); (6) a `POST /api/clusterconfigs` that omits both keys writes `remote-sar` + `same-as-host`, and one that states only `identity: none` writes `self-only` + `none`; (7) a Secret the lookup wrote for a `saTokenLookup` stanza serves the stanza's `visibility`, `identity` and `enabled` — a stanza that states no policy moves to `remote-sar` although its Secret was written with `self-only`, and a stanza set to `enabled: false` disables its cluster while the Secret exists. Keep the old view for a cluster with `visibility: self-only` and `identity: none` — in its values stanza, or in its Secret for a Secret-declared cluster; a Secret that already states `self-only` keeps it, unless the lookup wrote it for a stanza (7).
```
```markdown
- **`remote-sar` for every way a cluster is joined, and the default for a remote (application 0.32.0, chart 0.53.0; #338, `docs/specs/SPEC_D2b_remote_sar_for_every_join.md`).** A remote cluster's own RBAC decides who sees its data wide whether it was declared in values with a token, as a Secret made on the Cluster Configurations tab or by hand, or through `saTokenLookup`: the resolver is found or built per request from the cluster's current configuration and rebuilt when its URL, token or CA changes, with no restart. The Secret parser, the tab and the chart accept `remote-sar`; only an explicit `identity: none` beside it is refused. Distinct viewers already in flight may each pay that first attempt; after the first failure lands, the remote is held for 30 s and probed at most once per hold, whatever later traffic — and the review's error text is redacted before it is truncated. A Secret the lookup wrote for a `saTokenLookup` stanza keeps its credential and serves the stanza's `visibility`, `identity` and `enabled`. `/api/clusters` and `/api/alerts` decide each cluster's tier before they open their database snapshot. One line beside the cluster selector names the rule that decided the selected cluster's view (design D5). **Upgrade note — a remote that states neither `visibility` nor `identity` changes behaviour:** (1) it is `remote-sar` + `same-as-host`, so a reader that cluster's own RBAC allows (`list clusterrolebindings` by default) sees it wide on every tab — Bindings, Operator configs and Kyverno included — with the card's operator-config summary and its administrator alerts; (2) a reader it denies, or one it cannot be asked about, gets their own rows under their OpenShift username on groups, users, logins, cluster access, namespaces, user bindings, the two change feeds and that cluster's Home instead of a 403, and the host's Home counts that cluster's memberships and changes; (3) a remote that states only `identity: same-as-host` moves from `self-only` to `remote-sar` the same way; (4) `/api/whoami`, `/api/clusters` and `/api/alerts` ask that cluster about each reader once per `visibility.tierTtlSeconds`, and an unreachable one costs up to 5 s per remote, one remote after another, on the request that asks — before its hold engages and again on the first request after each hold expires; (5) a remote whose joining ServiceAccount lacks `list groups` or `create subjectaccessreviews` makes `GroupSyncDashboardVisibilityChecksFailing` fire (the pod log names the cluster; the metric does not); (6) a `POST /api/clusterconfigs` that omits both keys writes `remote-sar` + `same-as-host`, and one that states only `identity: none` writes `self-only` + `none`; (7) a Secret the lookup wrote for a `saTokenLookup` stanza serves the stanza's `visibility`, `identity` and `enabled` — a stanza that states no policy moves to `remote-sar` although its Secret was written with `self-only`, and a stanza set to `enabled: false` disables its cluster while the Secret exists. Keep the old view for a cluster with `visibility: self-only` and `identity: none` — in its values stanza, or in its Secret for a Secret-declared cluster; a Secret that already states `self-only` keeps it, unless the lookup wrote it for a stanza (7).
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
*Figure 1. Only the middle row differs. `inherit` never contacts the remote about the reader; `remote-sar` asks the
remote with the credential the dashboard already holds for it; `self-only` asks nobody. The example is `shared-rnd`;
today it can take only the first or the third column, because a Secret-declared cluster is refused `remote-sar` (§6).*
```
```markdown
*Figure 1. Only the middle row differs. `inherit` never contacts the remote about the reader; `remote-sar` asks the
remote with the credential the dashboard already holds for it; `self-only` asks nobody. Since SPEC_D2b, every join
path can take all three columns, and an unstated remote defaults to `remote-sar`.*
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
*Figure 3. Today every path except "allowed" narrows, which is the fail-closed direction. Allowed and denied are
cached; failures are not. A failure at either remote call reaches only the pod log and the tier-check metric, and
the reader sees the same generic narrowed view for every one. Today this flow runs only for a values-declared
`remote-sar` cluster (§6). Naming the failure (D4) and saying which rule decided (D5) are proposals (§8).*
```
```markdown
*Figure 3. Every path except "allowed" narrows, which is the fail-closed direction. Allowed and denied are cached;
failures are not. Since SPEC_D2b this flow runs for `remote-sar` on every join path, a failure holds the remote
resolver for 30 s, and D5 names the deciding rule beside the selector. D4's separate named failure remains a
proposal, so denied and could-not-ask deliberately share D5's narrowed sentence.*
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
| Outcome | Reader sees | Cached | What the page says today | Proposed |
|---|---|---|---|---|
| allowed | the wide view on this cluster | yes, per (reader, cluster) | the scope pill reads *Full view — you are seeing everything*; the selector adds no suffix and no self banner shows | D5: *this cluster says you may see everything* |
| denied | own rows | yes: a real answer | the scope pill reads *Your view — &lt;user&gt;*, the cluster selector appends " — your view", and the five views that carry a self banner (groups, users, access, logins, grants: `SCOPE_BANNER` in `local-development/gsd/static/index.html`) show their generic one | D5: *this cluster says: your own rows* |
| 403 listing the reader's groups | own rows, for every reader | no | the same generic text as denied | D4: a finding naming the fix, grant `list groups`; D5: *this cluster cannot check access* |
| 403 creating the review | own rows, for every reader | no | the same generic text | D4: a finding naming the fix, grant `create subjectaccessreviews`; D5: the same sentence |
| 401 at either call: the joining token is invalid or expired | own rows, for every reader | no | the same generic text | D5: *this cluster cannot check access* |
| unreachable, unparseable, or any other error | own rows | no | the same generic text | D5: *this cluster could not be asked just now* |
```
```markdown
| Outcome | Reader sees | Cached | Line beside the selector now (D5) | Named failure not built (D4) |
|---|---|---|---|---|
| allowed | the wide view on this cluster | yes, per (reader, cluster) | *This cluster's own RBAC gives you the full view.* | — |
| denied | own rows | yes: a real answer | *This cluster's own RBAC shows your own rows, or could not be asked.* | — |
| 403 listing the reader's groups | own rows, for every reader | no | the same deliberately indistinguishable narrowed line | a finding naming the fix: grant `list groups` |
| 403 creating the review | own rows, for every reader | no | the same deliberately indistinguishable narrowed line | a finding naming the fix: grant `create subjectaccessreviews` |
| 401 at either call: the joining token is invalid or expired | own rows, for every reader | no | the same deliberately indistinguishable narrowed line | a finding naming the invalid credential |
| unreachable, unparseable, or any other error | own rows | no | the same deliberately indistinguishable narrowed line | a finding naming that the cluster could not be asked |
```

<!-- block: local-development/gsd/kube.py | edit -->

```python
many seconds whatever the traffic: the first request that would call after the hold expires is the one
probe. Under the 60 s tier TTL and far under the alert's 15 minutes, so a remote that keeps failing under
```

```python
many seconds whatever the later traffic: the first request that would call after the hold expires is the
one probe; distinct viewers already in flight when the first failure lands may each pay that first attempt.
Under the 60 s tier TTL and far under the alert's 15 minutes, so a remote that keeps failing under
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
`shared-rnd`'s own RBAC, and it answers correctly for every reader measured (§5). The dashboard cannot use that
answer for these two clusters because `remote-sar`, the policy that asks the remote, is refused for any cluster
declared through a Secret, and both are (§6).
```

```markdown
`shared-rnd`'s own RBAC, and it answers correctly for every reader measured (§5). Until SPEC_D2b the dashboard could
not use that answer for these two clusters, because `remote-sar`, the policy that asks the remote, was refused for
any cluster declared through a Secret, and both are (§6). Since SPEC_D2b (#338) every join path takes it, and a
remote that states no policy defaults to it.
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```text
             group-sync-dashboard-cluster-poller; once D1 lands, under remote-sar the same token asks
             the remote about each reader (Figure 3)
```

```text
             group-sync-dashboard-cluster-poller; under remote-sar the same token asks the remote
             about each reader (Figure 3)
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
clusterrolebindings` (D7, #322). A Rejoin may still hold a working poller token, and once D1 lands that token could
ask the remote about the person's host username (§4). It would still say nothing about the credential just typed; that
```

```markdown
clusterrolebindings` (D7, #322). A Rejoin may still hold a working poller token, and that token can
ask the remote about the person's host username (§4). It would still say nothing about the credential just typed; that
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
SVG, light and dark palettes), at twice the pixel density: open it in a browser, set `data-theme` on the root element
to `light` or `dark`, and screenshot each `.fig-scroll` element. The pictures depict the decision points in §2, §3,
```

```markdown
SVG, light and dark palettes), at twice the pixel density, by `docs/diagrams/render.py`, which screenshots each
`.fig-scroll` element in both themes and checks the page at phone width — from the repository root:
`local-development/.venv/bin/python docs/diagrams/render.py docs/diagrams/remote-cluster-access/source.html
docs/diagrams/remote-cluster-access policies-who-decides,inherit-vs-remote-sar-outcomes,remote-sar-decision-flow,joining-a-cluster`. The pictures depict the decision points in §2, §3,
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
      <code>self-only</code>, so nobody is asked. The remote could answer this itself, and today our code will not let it.</p>
```

```html
      <code>self-only</code>, so nobody is asked. The remote could answer this itself; since SPEC_D2b it does, for every
      way a cluster is joined.</p>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
        dashboard already holds for it. <strong>self-only</strong> is today's default for every cluster except the
        host, and is what <code>shared-rnd</code> and <code>shared-qa</code> are set to. The example is <code>shared-rnd</code>;
        today it can take only the first or the third column, because a Secret-declared cluster is refused
        <code>remote-sar</code>.</figcaption>
```

```html
        dashboard already holds for it. <strong>self-only</strong> was the default for every cluster except the host
        until SPEC_D2b, which made <strong>remote-sar</strong> the default and let every join path take all three
        columns.</figcaption>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
            <text x="20" y="384" fill="var(--host)" font-weight="600">The mandate (D1, directed, not built): remote-sar for every way a cluster is joined. Today it works only for a values-declared cluster.</text>
```

```html
            <text x="20" y="384" fill="var(--muted)">Built in SPEC_D2b (#338): remote-sar for every way a cluster is joined, and the default for a remote.</text>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
        <svg viewBox="0 0 980 490" role="img" aria-label="remote-sar today: a cached verdict, or list the reader's groups on the remote and create a SubjectAccessReview there with the joining token. Allowed gives the wide view and denied gives self, both cached. A 401, 403 or unreachable answer at either remote call gives self, not cached, with a pod-log warning and the tier-check metric; any other exception gives self, not cached, with an ERROR and the metric outcome error. The named finding and the per-outcome sentence are proposals D4 and D5.">
```

```html
        <svg viewBox="0 0 980 490" role="img" aria-label="remote-sar today: a cached verdict, or list the reader's groups on the remote and create a SubjectAccessReview there with the joining token. Allowed gives the wide view and denied gives self, both cached. A 401, 403 or unreachable answer at either remote call gives self, not cached, with a pod-log warning and the tier-check metric; any other exception gives self, not cached, with an ERROR and the metric outcome error. A failure holds the cluster's resolver for 30 s; the line beside the selector (D5) names the rule; the named finding is proposal D4.">
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
            <text x="40" y="432" fill="var(--muted)">Today every narrowed outcome shows the reader the same generic "Your view" text; only the pod log and the tier-check metric name the failure.</text>
```

```html
            <text x="40" y="432" fill="var(--muted)">A failure holds that cluster's resolver 30 s. The line beside the selector (D5) says this cluster's RBAC decided.</text>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
            <text x="40" y="472" fill="var(--host)" font-weight="600">Proposed: D4 names the two 403s as a finding with their fix · D5 gives the reader one sentence per outcome.</text>
```

```html
            <text x="40" y="472" fill="var(--host)" font-weight="600">Proposed: D4 names the two 403s as a finding with their fix.</text>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
          <tr><td>a Secret from the Cluster Configurations tab</td><td class="yes">yes</td><td class="cell-gap"><span class="no">refused</span></td><td class="yes">yes</td><td class="yes">yes</td></tr>
```

```html
          <tr><td>a Secret from the Cluster Configurations tab</td><td class="yes">yes</td><td class="yes">yes</td><td class="yes">yes</td><td class="yes">yes</td></tr>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
          <tr><td><code>saTokenLookup</code> (the lookup writes a Secret)</td><td class="yes">yes</td><td class="cell-gap"><span class="no">refused</span></td><td class="yes">yes</td><td class="yes">yes</td></tr>
```

```html
          <tr><td><code>saTokenLookup</code> (the lookup writes a Secret)</td><td class="yes">yes</td><td class="yes">yes</td><td class="yes">yes</td><td class="yes">yes</td></tr>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
    <p class="muted">Why refused: the per-cluster resolver that asks the remote is built <strong>once, at start-up</strong>,
      from the values list (<code>gsd/api.py</code>). A Secret-declared cluster appears <strong>at runtime</strong>
      and never gets one. The parser says so: <em>"remote-sar for a Secret-sourced cluster is S2"</em>. That work
      was never done, and it is the gap that bit you: the way we now join clusters is exactly the way that cannot
      ask the remote.</p>
```

```html
    <p class="muted">Since SPEC_D2b (#338) every row takes <code>remote-sar</code>: the resolver is found or built per
      request from the cluster's current configuration, values entry or Secret, and rebuilt when its connection
      changes. Before it, the resolver was built <strong>once, at start-up</strong>, from the values list, and a
      Secret-declared cluster never got one: the way clusters are now joined was exactly the way that could not ask
      the remote.</p>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
            <text x="46" y="790">once D1 lands, under remote-sar the same token asks shared-rnd about each reader (Figure 3)</text>
```

```html
            <text x="46" y="790">under remote-sar, the same token asks shared-rnd about each reader (Figure 3)</text>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
        <svg viewBox="0 0 980 870" role="img" aria-label="How a cluster is joined. On the host, saTokenLookup starts automatically: it stops first if cluster-Secret writes are off, then the leader or sole replica reads the fleet account's password from one host Secret, and a password the target already refused is not sent again. Rejoin, proposed, starts with a person who must pass clusterAdminSar on the host, update clusterrolebindings, and types their own username and password. On the remote, the dashboard logs in as that account, a proposed SelfSubjectAccessReview asks #322's cluster-admin question of a Rejoin credential there, it reads the poller's token Secret by name in group-sync-operator, and tries once to revoke the login's own token. Back on the host it writes gsd-cluster-shared-rnd. Once joined, the poller's token authenticates every later call; its rights on the remote are the ClusterRole group-sync-dashboard-cluster-poller, and once D1 lands, under remote-sar the same token asks the remote about each reader.">
```

```html
        <svg viewBox="0 0 980 870" role="img" aria-label="How a cluster is joined. On the host, saTokenLookup starts automatically: it stops first if cluster-Secret writes are off, then the leader or sole replica reads the fleet account's password from one host Secret, and a password the target already refused is not sent again. Rejoin, proposed, starts with a person who must pass clusterAdminSar on the host, update clusterrolebindings, and types their own username and password. On the remote, the dashboard logs in as that account, a proposed SelfSubjectAccessReview asks #322's cluster-admin question of a Rejoin credential there, it reads the poller's token Secret by name in group-sync-operator, and tries once to revoke the login's own token. Back on the host it writes gsd-cluster-shared-rnd. Once joined, the poller's token authenticates every later call; its rights on the remote are the ClusterRole group-sync-dashboard-cluster-poller, and under remote-sar the same token asks the remote about each reader.">
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
          for a looked-up remote are "the host decides" or "nobody is wide".</div>
```

```html
          for a looked-up remote were "the host decides" or "nobody is wide". Built in SPEC_D2b (#338).</div>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
        <div class="rec"><strong>Recommend: yes.</strong> Today the page narrowed you and gave no reason, which is how
          this looked like a bug.</div>
```

```html
        <div class="rec"><strong>Directed</strong> (2026-09-23), built in SPEC_D2b: one line beside the selector, read
          from <code>/api/whoami</code> alone. Before it, the page narrowed you and gave no reason, which is how this
          looked like a bug.</div>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
          model the mandate replaces. Both remotes stay <code>self-only</code> until D1 ships, then take
          <code>remote-sar</code> + <code>same-as-host</code>.</div>
```

```html
          model the mandate replaces. Both remotes stayed <code>self-only</code> until D1 shipped in SPEC_D2b, and now
          take <code>remote-sar</code> + <code>same-as-host</code>.</div>
```

<!-- block: docs/diagrams/render.py | create -->

```python
#!/usr/bin/env python3
"""Render every .fig-scroll figure of a diagram page to light and dark PNGs, and check the page.

    local-development/.venv/bin/python docs/diagrams/render.py <page.html> <out-dir> <name-1>,<name-2>,...

One name per .fig-scroll, in document order; each becomes <out-dir>/<name>.light.png and
<name>.dark.png at 2x pixel density. The page may be a fragment (an Artifact page starts at
<title>): it is wrapped in a document for rendering, never modified. Exit status is non-zero on a
page error, a request that did not load (a web font that fails leaves the figures in a fallback
face), a name/figure count mismatch, or horizontal page scroll at 375 px — the defects a code review
of the SVG text does not see.
"""

from __future__ import annotations

import pathlib
import sys
import tempfile

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sys.exit("playwright is not installed: python3 -m pip install playwright && python3 -m playwright install chromium")


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__)
        return 2
    page_path, out_dir = pathlib.Path(sys.argv[1]).resolve(), pathlib.Path(sys.argv[2]).resolve()
    names = [n.strip() for n in sys.argv[3].split(",") if n.strip()]
    out_dir.mkdir(parents=True, exist_ok=True)

    text = page_path.read_text()
    if "<html" not in text.lower():
        text = ('<!doctype html><html><head><meta charset="utf-8">'
                '<meta name="viewport" content="width=device-width,initial-scale=1"></head><body>'
                f"{text}</body></html>")
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp, sync_playwright() as p:
        doc = pathlib.Path(tmp) / "page.html"
        doc.write_text(text)
        browser = p.chromium.launch()
        for theme in ("light", "dark"):
            page = browser.new_page(viewport={"width": 1180, "height": 900}, device_scale_factor=2)
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            # A failed request, not a fixed sleep, is what says the fonts are missing: Chromium keeps an empty
            # sheet for a stylesheet that failed and document.fonts.check() answers true for a face never declared.
            unloaded: list[str] = []
            page.on("requestfailed", lambda r: unloaded.append(r.url))
            page.on("response", lambda r: unloaded.append(f"{r.url} ({r.status})") if r.status >= 400 else None)
            page.goto(doc.as_uri(), wait_until="networkidle")
            page.evaluate(f"() => document.documentElement.setAttribute('data-theme', '{theme}')")
            page.evaluate("document.fonts.ready.then(() => true)")
            if unloaded:
                failures.append(f"{theme}: did not load: {', '.join(sorted(set(unloaded)))}")
                break
            figures = page.locator(".fig-scroll")
            if figures.count() != len(names):
                failures.append(f"{figures.count()} .fig-scroll figures but {len(names)} names given")
                break
            for i, name in enumerate(names):
                target = out_dir / f"{name}.{theme}.png"
                figures.nth(i).screenshot(path=str(target))
                print(f"wrote {target} ({target.stat().st_size} bytes)")
            failures += [f"{theme}: page error: {e}" for e in errors]
            page.close()
        phone = browser.new_page(viewport={"width": 375, "height": 800})
        phone.goto(doc.as_uri(), wait_until="networkidle")
        width = phone.evaluate("document.fonts.ready.then(() => document.documentElement.scrollWidth)")
        print(f"375 px viewport: scrollWidth {width}")
        if width > 375:
            failures.append(f"the page scrolls sideways at 375 px (scrollWidth {width})")
        browser.close()
    for f in failures:
        print(f"FAIL: {f}", file=sys.stderr)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

<!-- block: docs/ACCESS_CONTROL.md | edit -->

```markdown
review, unreachable, junk) is the self tier and is not cached — and it holds that cluster's resolver for
`gsd/kube.py#REMOTE_FAILURE_HOLD_SECONDS` (30 s): no request calls that remote until the hold expires, and the
first one after it is the one probe. Failures count under the same signal
```

```markdown
review, unreachable, junk) is the self tier and is not cached — and it holds that cluster's resolver for
`gsd/kube.py#REMOTE_FAILURE_HOLD_SECONDS` (30 s): no attempt on that remote starts while the hold runs, and the
first request that would call after it expires is the one probe; distinct viewers already in flight when the first
failure lands may each finish their attempt. Failures count under the same signal
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
On the lab, `kubeadmin` is `cluster-admin` and sees everything on the host cluster, `dashboard`. On `shared-rnd` and
`shared-qa` it sees only its own rows. Both remotes resolve to `visibility=self-only identity=none` (the pod's
`cluster-resolved` log line), so **nobody is asked** whether a reader may see them wide.
```

```markdown
On the lab, `kubeadmin` is `cluster-admin` and sees everything on the host cluster, `dashboard`. Before SPEC_D2b it saw
only its own rows on `shared-rnd` and `shared-qa`: both remotes resolved to `visibility=self-only identity=none` (the
pod's `cluster-resolved` log line, 2026-09-23), so **nobody was asked** whether a reader may see them wide.
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
| See a joined remote wide | the cluster's policy (`self-only` on both lab remotes) | `remote-sar` + `same-as-host`, the standard (D2) | the remote, with the poller's token | none: the token is already held |
```

```markdown
| See a joined remote wide | the cluster's policy: `remote-sar` + `same-as-host`, the standard (D2), on both lab remotes since SPEC_D2b (`self-only` before it) | unchanged | the remote, with the poller's token | none: the token is already held |
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
| **D1** | Support `remote-sar` for every way a cluster is joined | build the remote resolver when discovery finds the cluster, rebuild it when the Secret's credential changes, drop it when the cluster is retired; accept `remote-sar` from a Secret and from a `saTokenLookup` stanza | **Directed** by the operator: *"we need to have both supported and clearly defined"*, and the mandate of 2026-09-23: *"this is what I want: remote-sar for whatever method the cluster was joined"* |
```

```markdown
| **D1** | Support `remote-sar` for every way a cluster is joined | build the remote resolver when discovery finds the cluster, rebuild it when the Secret's credential changes, drop it when the cluster is retired; accept `remote-sar` from a Secret and from a `saTokenLookup` stanza | **Directed** by the operator: *"we need to have both supported and clearly defined"*, and the mandate of 2026-09-23: *"this is what I want: remote-sar for whatever method the cluster was joined"*. Built in SPEC_D2b (#338): the resolver is found or built on each request from the cluster's current configuration, with no discovery hook, and dropped at the next lookup once its cluster is no longer askable |
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
| **D6** | The lab until D1 ships | `inherit` + `same-as-host` on `shared-rnd` now, or `self-only` until D1 lands and `remote-sar` after | **Directed**: no `inherit` stopgap. `inherit` would copy the host's answer to the remote rather than ask it, which is the model the mandate replaces (D1). `shared-rnd` and `shared-qa` stay `self-only` until D1 ships, then take `remote-sar` + `same-as-host`. |
```

```markdown
| **D6** | The lab until D1 ships | `inherit` + `same-as-host` on `shared-rnd` now, or `self-only` until D1 lands and `remote-sar` after | **Directed**: no `inherit` stopgap. `inherit` would copy the host's answer to the remote rather than ask it, which is the model the mandate replaces (D1). `shared-rnd` and `shared-qa` stayed `self-only` until D1 shipped in SPEC_D2b, and now take `remote-sar` + `same-as-host`. |
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
- **Code (D1, D2):** a `TierResolver` per `remote-sar` cluster owned by the discovery registry instead of built once
  in `create_app`; keyed by cluster and rebuilt when the cluster's credential or trust changes; the parser and the
  chart stop refusing `remote-sar` for Secret-declared clusters. The parser, once it accepts `remote-sar`, must
```

```markdown
- **Code (D1, D2), built in SPEC_D2b (#338):** a `TierResolver` per `remote-sar` cluster, found or built on each
  request from the cluster's current configuration (`local-development/gsd/kube.py#RemoteTierResolvers`) instead
  of built once in `create_app`; rebuilt when the cluster's URL, credential or trust changes; the parser and the
  chart stop refusing `remote-sar` for Secret-declared clusters. The parser, once it accepts `remote-sar`, must
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
    <p class="lede">You are <code>cluster-admin</code> on the lab. On <code>dashboard</code> you see everything; on
      <code>shared-rnd</code> and <code>shared-qa</code> you see only your own rows. Both remotes are configured
      <code>self-only</code>, so nobody is asked. The remote could answer this itself; since SPEC_D2b it does, for every
      way a cluster is joined.</p>
```

```html
    <p class="lede">You are <code>cluster-admin</code> on the lab, and on <code>dashboard</code> you see everything.
      Before SPEC_D2b, on <code>shared-rnd</code> and <code>shared-qa</code> you saw only your own rows: both remotes
      were <code>self-only</code>, so nobody was asked. The remote could answer this itself; since SPEC_D2b it does, for
      every way a cluster is joined.</p>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
      <figcaption>Today, every path except "allowed" narrows, which is the fail-closed direction; allowed and
        denied are cached, failures are not. A failure at either remote call is visible only in the pod log and the
        tier-check metric. The reader sees the same generic text for every narrowed outcome. Naming the failure (D4)
        and saying which rule decided (D5) are proposals, in the decisions below. Both behaviours are in
        <code>docs/ACCESS_CONTROL.md</code> §11.</figcaption>
```

```html
      <figcaption>Every path except "allowed" narrows, which is the fail-closed direction; allowed and denied are
        cached, failures are not, and a failure holds that cluster's resolver for 30 s. The cause of a failure is
        visible only in the pod log and the tier-check metric. Since SPEC_D2b the line beside the selector (D5) names
        the rule that decided; naming the failure (D4) is still a proposal, in the decisions below, so a denied reader
        and one the remote could not be asked about read the same narrowed line. Both behaviours are in
        <code>docs/ACCESS_CONTROL.md</code> §11.</figcaption>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
          <tr><td>See a joined remote wide</td><td>the policy: <code>self-only</code> on both lab remotes</td><td><code>remote-sar</code> + <code>same-as-host</code>, the standard (D2)</td><td>remote, with the poller's token</td><td>none: the token is already held</td></tr>
```

```html
          <tr><td>See a joined remote wide</td><td>the policy: <code>remote-sar</code> + <code>same-as-host</code>, the standard (D2), on both lab remotes since SPEC_D2b (<code>self-only</code> before it)</td><td>unchanged</td><td>remote, with the poller's token</td><td>none: the token is already held</td></tr>
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
`self-only`, and the host's cluster-admin stopped being wide there. `shared-qa` is a hand-made Secret from #310's
testing with no visibility key, so it has always been `self-only`.
```

```markdown
`self-only`, and the host's cluster-admin stopped being wide there. `shared-qa` is a hand-made Secret from #310's
testing with no visibility key, so it was `self-only` until SPEC_D2b; since then both remotes take the default for a
remote that states no policy, `remote-sar` + `same-as-host`.
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
        <li><code>shared-qa</code> is a hand-made Secret from #310's testing with no visibility key, so it has always
          been <code>self-only</code>.</li>
```

```html
        <li><code>shared-qa</code> is a hand-made Secret from #310's testing with no visibility key, so it was
          <code>self-only</code> until SPEC_D2b; since then both remotes take the default for a remote that states no
          policy, <code>remote-sar</code> + <code>same-as-host</code>.</li>
```

<!-- block: docs/diagrams/render.py | edit -->

```python
    failures: list[str] = []
```

```python
    failures: list[str] = []

    def watch(page, label: str) -> None:
        # Every page reports for its whole life, the 375 px one included: its load is where the sideways-scroll
        # check is measured. A failed request, not a fixed sleep, is what says the fonts are missing: Chromium keeps
        # an empty sheet for a stylesheet that failed and document.fonts.check() answers true for a face never declared.
        page.on("pageerror", lambda e: failures.append(f"{label}: page error: {e}"))
        page.on("requestfailed", lambda r: failures.append(f"{label}: did not load: {r.url}"))
        page.on("response", lambda r: failures.append(f"{label}: did not load: {r.url} ({r.status})")
                if r.status >= 400 else None)
```

<!-- block: docs/diagrams/render.py | edit -->

```python
            errors: list[str] = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            # A failed request, not a fixed sleep, is what says the fonts are missing: Chromium keeps an empty
            # sheet for a stylesheet that failed and document.fonts.check() answers true for a face never declared.
            unloaded: list[str] = []
            page.on("requestfailed", lambda r: unloaded.append(r.url))
            page.on("response", lambda r: unloaded.append(f"{r.url} ({r.status})") if r.status >= 400 else None)
            page.goto(doc.as_uri(), wait_until="networkidle")
            page.evaluate(f"() => document.documentElement.setAttribute('data-theme', '{theme}')")
            page.evaluate("document.fonts.ready.then(() => true)")
            if unloaded:
                failures.append(f"{theme}: did not load: {', '.join(sorted(set(unloaded)))}")
                break
```

```python
            watch(page, theme)
            page.goto(doc.as_uri(), wait_until="networkidle")
            page.evaluate(f"() => document.documentElement.setAttribute('data-theme', '{theme}')")
            page.evaluate("document.fonts.ready.then(() => true)")
            if failures:
                break
```

<!-- block: docs/diagrams/render.py | edit -->

```python
            failures += [f"{theme}: page error: {e}" for e in errors]
            page.close()
        phone = browser.new_page(viewport={"width": 375, "height": 800})
        phone.goto(doc.as_uri(), wait_until="networkidle")
```

```python
            page.close()
        phone = browser.new_page(viewport={"width": 375, "height": 800})
        watch(phone, "375 px")
        phone.goto(doc.as_uri(), wait_until="networkidle")
```

<!-- block: local-development/tests/test_diagram_render.py | create -->

```python
"""docs/diagrams/render.py's exit status, on every path its docstring promises (SPEC_D2b §7).

The renderer's value is its refusals: a figure drawn in a fallback face, or a page that scrolls sideways at
375 px, looks like a design choice once it is a PNG. So every page it opens, the 375 px one included, must turn a
page error, a failed request or an HTTP error into a non-zero exit. Playwright is replaced by a stand-in that fires
those events on demand, so this needs no browser and no network; the real render is SPEC_D2b §7's "After the
blocks" step.
"""

from __future__ import annotations

import importlib.util
import pathlib
from types import SimpleNamespace

import pytest

RENDER = pathlib.Path(__file__).resolve().parents[2] / "docs" / "diagrams" / "render.py"

# case -> (fired on the 375 px page?, event, payload); "ok", "mismatch" and "scroll" fire nothing.
EVENTS = {
    "offline": (False, "requestfailed", SimpleNamespace(url="https://fonts.invalid/face.woff2")),
    "404": (False, "response", SimpleNamespace(url="https://fonts.invalid/face.woff2", status=404)),
    "pageerror": (False, "pageerror", RuntimeError("broken page")),
    "phone-requestfailed": (True, "requestfailed", SimpleNamespace(url="https://fonts.invalid/face.woff2")),
    "phone-404": (True, "response", SimpleNamespace(url="https://fonts.invalid/face.woff2", status=404)),
    "phone-pageerror": (True, "pageerror", RuntimeError("broken page")),
}


def _render():
    spec = importlib.util.spec_from_file_location("diagram_render", RENDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("case", ["ok", "mismatch", "scroll", *EVENTS])
def test_every_page_turns_a_failure_into_a_non_zero_exit(monkeypatch, tmp_path, case):
    render = _render()

    class Page:
        def __init__(self, phone: bool):
            self.phone, self.handlers = phone, {}

        def on(self, name, callback):
            self.handlers.setdefault(name, []).append(callback)

        def goto(self, url, **kwargs):
            assert url.startswith("file:")
            on_phone, event, payload = EVENTS.get(case, (None, None, None))
            if on_phone is self.phone:
                for callback in self.handlers.get(event, []):
                    callback(payload)

        def evaluate(self, expression):
            return (500 if case == "scroll" else 375) if "scrollWidth" in expression else True

        def locator(self, selector):
            assert selector == ".fig-scroll"
            return self

        def count(self):
            return 3 if case == "mismatch" else 4

        def nth(self, index):
            return self

        def screenshot(self, path):
            pathlib.Path(path).write_bytes(b"png")

        def close(self):
            pass

    class Browser:
        def new_page(self, *, viewport, **kwargs):
            return Page(viewport["width"] == 375)

        def close(self):
            pass

    class Playwright:
        chromium = SimpleNamespace(launch=Browser)

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

    monkeypatch.setattr(render, "sync_playwright", Playwright)
    page = tmp_path / "page.html"
    page.write_text("<html><body>four figures</body></html>")
    out = tmp_path / "png"
    monkeypatch.setattr(render.sys, "argv", ["render.py", str(page), str(out), "a,b,c,d"])
    assert render.main() == (0 if case == "ok" else 1), case
    if case == "ok":
        assert len(list(out.glob("*.png"))) == 8
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
| Status | **Proposed.** D1, D2 (`remote-sar` + `same-as-host` is the standard for every way a cluster is joined), D3, D5, D6 and D7 directed by the operator; D4's fail-closed fallback directed, its named finding recommended; D8 open (§8) |
```

```markdown
| Status | D1, D2 (`remote-sar` + `same-as-host`, the standard for every way a cluster is joined) and D5 built in SPEC_D2b (#338), the remote failure hold with them; D3 needs no code; D6's lab policy applied there; D4's fail-closed fallback built, its named finding recommended, not built; D7 directed, not built (#322); D8 open (§8) |
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
| **D2** | The default for a newly joined remote | `self-only` (today) or `remote-sar` | **Directed**: `remote-sar` + `same-as-host` is the standard. The operator: *"we should be looking up user's permission on the remote host to determine their access … unless the service account that joined the remote cluster doesn't have the right permissions"*, and *"I agree with your recommendation to build out remote-sar + same-as-host as our standard"* |
```

```markdown
| **D2** | The default for a newly joined remote | `self-only` (the default until SPEC_D2b) or `remote-sar` | **Directed**: `remote-sar` + `same-as-host` is the standard. The operator: *"we should be looking up user's permission on the remote host to determine their access … unless the service account that joined the remote cluster doesn't have the right permissions"*, and *"I agree with your recommendation to build out remote-sar + same-as-host as our standard"* |
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->

```markdown
| **D6** | The lab until D1 ships | `inherit` + `same-as-host` on `shared-rnd` now, or `self-only` until D1 lands and `remote-sar` after | **Directed**: no `inherit` stopgap. `inherit` would copy the host's answer to the remote rather than ask it, which is the model the mandate replaces (D1). `shared-rnd` and `shared-qa` stayed `self-only` until D1 shipped in SPEC_D2b, and now take `remote-sar` + `same-as-host`. |
```

```markdown
| **D6** | The lab until D1 shipped | `inherit` + `same-as-host` on `shared-rnd` then, or `self-only` until D1 landed and `remote-sar` after | **Directed**: no `inherit` stopgap. `inherit` would copy the host's answer to the remote rather than ask it, which is the model the mandate replaces (D1). `shared-rnd` and `shared-qa` stayed `self-only` until D1 shipped in SPEC_D2b, and now take `remote-sar` + `same-as-host`. |
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
        <div class="q"><code>self-only</code> (today), or <code>remote-sar</code>?</div>
```

```html
        <div class="q"><code>self-only</code> (the default until SPEC_D2b), or <code>remote-sar</code>?</div>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
        <div class="rec"><strong>Directed</strong> (2026-09-23), built in SPEC_D2b: one line beside the selector, read
          from <code>/api/whoami</code> alone. Before it, the page narrowed you and gave no reason, which is how this
          looked like a bug.</div>
```

```html
        <div class="rec"><strong>Directed</strong> (2026-09-23), built in SPEC_D2b: one line beside the selector, read
          from <code>/api/whoami</code> alone. <em>cannot check access</em> needs D4's field and is not built, so a
          <code>remote-sar</code> cluster's narrowed line reads <em>This cluster's own RBAC shows your own rows, or
          could not be asked.</em>
          Before D5, the page narrowed you and gave no reason, which is how this looked like a bug.</div>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->

```html
        <div class="id">D6 · the lab, right now</div>
        <div class="q">Until D1 ships, what should <code>shared-rnd</code> and <code>shared-qa</code> be?</div>
```

```html
        <div class="id">D6 · the lab until D1 shipped</div>
        <div class="q">Until D1 shipped, what were <code>shared-rnd</code> and <code>shared-qa</code> to be?</div>
```

#### After the blocks

The figures of `docs/DESIGN_remote_cluster_access.md` are PNGs, which a block cannot carry. With the blocks applied,
re-render them from the updated page and commit the PNGs that changed (Figures 2, 3 and 4 carry text these blocks
change; Figure 1 does not), from the repository root:

```sh
local-development/.venv/bin/python docs/diagrams/render.py docs/diagrams/remote-cluster-access/source.html \
  docs/diagrams/remote-cluster-access policies-who-decides,inherit-vs-remote-sar-outcomes,remote-sar-decision-flow,joining-a-cluster
```

It exits non-zero on a page error, a request that did not load (the web fonts among them: offline, the figures would be
drawn in a fallback face), a name/figure mismatch, or sideways scroll at 375 px; read the PNGs before committing.
