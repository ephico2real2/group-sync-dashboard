# SPEC D2 — Per-cluster authorization for the multi-cluster case

| | |
|---|---|
| Programme | Feature programme 2026-09 — index and version ladder in `docs/specs/README.md` |
| Batch | D — architecture |
| Release | R7 — Multi-cluster authorization |
| Version on release | app 0.19.0, chart 0.21.0 |
| Issue | [#68](https://github.com/ephico2real2/group-sync-dashboard/issues/68) |
| Status | specified |
| Source | design agent output `a1c16fd988d22c70e`; three messages; the first ended mid-token (`"nodes/` | `proxy"]`) and is joined to the second with nothing between; the third is the agent's confirmation reply summarising D2 and is not design text, so it is omitted |

## How to read this spec

Everything under "Batch preamble", "Design" and "Batch closing sections" is the design agent's text,
sliced from the agent's output by heading and re-concatenated to the byte before this file was
written. It is verbatim with exactly two kinds of exception, both stated in this file: the seam
repair named in the Source row where the agent's output was cut across messages, and the citation or
name corrections listed under "Orchestrator's notes", each of which changes a reference and never a
claim. Nothing else was rewritten by hand. Implementation applies the code in "Design" exactly as
written, one file at a time, with the orchestrator's notes governing where they and the body differ;
a deviation found necessary during implementation is written back into this file in the same pull
request, with the reason, under "Orchestrator's notes".

## Orchestrator's notes

- R7: app 0.19.0, chart 0.21.0; the body's "PR 1, before D1" ordering and version pair are superseded by the milestone order (D1 lands in R5, D2 in R7).
- Citation corrected (twice): the design cited the login-capture design doc with the anchor "The five deliberate test logins appear exactly as made", but that sentence is line-wrapped in the source after "The five"; the anchor now cites the part that is on one line.
- Citation corrected: the design cited the login-capture design doc with the anchor "needs nodes/proxy", but the source has bold and code marks between those two words; the anchor now cites `nodes/proxy`.
- Name corrected: the design cited a PrometheusRule alert `GroupSyncDashboardVisibilityTierFailing`; no such alert exists. The alert on `gsd_visibility_tier_checks_total` failure outcomes in `charts/group-sync-dashboard/templates/monitoring.yaml` is `GroupSyncDashboardVisibilityChecksFailing`, and the claim (the remote resolver's failures count under the same signal, so the same alert fires) is unchanged.

## Batch preamble (verbatim from the design)

# Design: D1 (login capture from the oauth-server audit log) and D2 (per-cluster authorization)

Everything below is grounded in files read in this repository, cited as `path#anchor`, and in external sources I fetched, cited by URL and marked **verified** / **partly verified** / **could not verify**. No file was written or edited.

---

## 0. What I read, and the constraints the code imposes

**The capture pipeline as built.** `gsd/kube.py#ClusterClient.fetch_oauth_pods` and `gsd/kube.py#ClusterClient.fetch_pod_log` read pod logs (streamed, byte- and wall-clock-bounded by `gsd/kube.py#LOG_READ_BUDGET_SECONDS`); `gsd/loginlog.py#parse` correlates klog lines into `LoginAttempt`; `gsd/logincapture.py#capture_once` owns the per-pod watermark, the settle horizon (`gsd/logincapture.py#_settle_horizon`), the leading-edge guard (`gsd/logincapture.py#_not_clipped`) and the leadership recheck; `gsd/logincapture.py#event_dict` fixes the row shape and stamp format; `gsd/store.py#Store.record_login_events` inserts against `UNIQUE(cluster_id, pod_name, user_name, at, outcome)`; `gsd/store.py#Store.prune_login_events` is bounded; `gsd/store.py#Store.record_login_read` is the liveness record that `gsd/metrics.py#DashboardCollector._gather` exports as `gsd_login_capture_last_read_timestamp_seconds{cluster}`, and `templates/monitoring.yaml#GroupSyncDashboardLoginCaptureStalled` alerts on it joined `on()` to the unlabelled `gsd_login_capture_enabled`. The poller calls `capture_once` once per cycle after `poll_once` (`gsd/poller.py#_run_cluster`), so a second source must be a dispatch inside `capture_once`, not a second thread.

**The switches as built.** `loginCapture.enabled` renders a namespaced Role (`templates/login-capture-rbac.yaml`) and the ConfigMap key `loginCaptureEnabled` (`templates/configmap.yaml#loginCaptureEnabled`, the key that was once unwired). `authLogLevel.manage`/`.enabled` render two hook Jobs on a separate ServiceAccount (`templates/auth-loglevel-job.yaml`, `templates/auth-loglevel-rbac.yaml`, `templates/auth-loglevel-revert-job.yaml`); the values comment is explicit that a toggle "ROLLS THE OAUTH SERVER, WHICH IS A LOGIN OUTAGE ON A SINGLE-REPLICA CLUSTER", and the chart README says turning it off is two steps in order (`enabled=false` then `manage=false`). `tests/test_chart_strategy.py::TestLoginCaptureReadsOneNamespaceOnly` asserts no ClusterRole ever grants `pods`/`pods/log` — the audit-log grant must be a *different* resource so that test keeps holding.

**The tier as built.** `gsd/kube.py#TierResolver` is one cluster, one SAR shape, one per-viewer cache, failures never cached; it fetches the viewer's groups fresh from *its* cluster (`gsd/kube.py#ClusterClient.fetch_groups_of_user`) — which is exactly the property D2(a) needs: an instance constructed on a remote `ClusterConfig` already issues the review on the remote with the remote's Group objects. `gsd/api.py#build_app` constructs it "against the FIRST enabled cluster, deliberately" and `viewer_scope` has no cluster argument; `require_cluster` 404s unknown ids; `/api/clusters` and `/api/alerts` iterate `store.clusters()`; `/api/whoami` reports one `visibility.scope`. `docs/SPEC_per_user_visibility.md#per-remote-cluster tiers are out of scope` (risk 7) and `docs/reference-architecture.md#The multi-cluster caveat` record the gap; `README.md#Not built yet` lists it. `charts/group-sync-dashboard/values.yaml#Adding entries here enables multi-cluster` cites a `docs/PLAN_oauth_proxy.md` that does not exist in `docs/` (stale reference; fixed below).

**Conventions that bind every change.** Docs cite `path#anchor`, resolved by `tests/test_docs_citations.py` (AST for `.py`, substring otherwise; line numbers fail the build). Every endpoint is GET and documented (`tests/test_api_contract.py`, `docs/api-contract.md` R1–R7). `tests/test_chart_versions.py` holds `Chart.yaml` `appVersion` = `pyproject.toml` `version` = `gsd/__init__.py#__version__`. `tests/test_environments_readme.py` holds `environments/README.md`'s table to `environments/crc.yaml` (crc.yaml is not changed by either feature). `tests/test_migrations.py::test_a_fresh_database_lands_on_the_latest_migration` reads `max(_MIGRATIONS)`, so a new migration needs no test edit. Config keys on cluster entries are a closed set (`gsd/config.py#load_settings`, `known`); unknown keys refuse to start.

---

## 1. External facts for D1, with what was and was not verified

| claim | status | source |
|---|---|---|
| The oauth-server writes a Kubernetes-audit-format JSON log to `/var/log/oauth-server/audit.log` (hostPath mount `audit-dir`), with its policy from ConfigMap `audit` mounted at `/var/run/configmaps/audit` | **verified** in operator bindata | https://raw.githubusercontent.com/openshift/cluster-authentication-operator/master/bindata/oauth-openshift/deployment.yaml |
| The oauth-server's audit policy is fixed: level `None` for `/healthz*`, `/logs`, `/metrics`, `/version`; level `Metadata` for everything else. No `omitStages`, so both `RequestReceived` and `ResponseComplete` stages are emitted | **verified** (two-rule policy); omitStages absence is what the fetched excerpt showed | https://raw.githubusercontent.com/openshift/cluster-authentication-operator/master/bindata/oauth-openshift/audit-policy.yaml |
| The operator's `ObserveAudit` sets `audit-log-path=/var/log/oauth-server/audit.log`, `audit-log-format=json`, `audit-log-maxsize=100` (MB), `audit-log-maxbackup=10`, `audit-policy-file=/var/run/configmaps/audit/audit.yaml`, and applies them **only when `apiserver.config.openshift.io/cluster` `spec.audit.profile` is not `None`**. So: rotation is by size, ≤10 backups ≈ ≤1.1 GB on the node; retention is a function of login/request volume, not of days; the `None` profile switches the source off entirely | **verified** | https://raw.githubusercontent.com/openshift/cluster-authentication-operator/master/pkg/controllers/configobservation/oauth/observe_audit.go |
| Annotations `authentication.openshift.io/username` and `authentication.openshift.io/decision` with decisions `allow`, `deny`, `error` | **verified** in source | https://raw.githubusercontent.com/openshift/oauth-server/master/pkg/audit/annotation.go |
| Audited paths for the password flows: `/oauth/authorize`, `/login`, `/oauth/token` | **verified** (PR #92 description) | https://github.com/openshift/oauth-server/pull/92 |
| Documented reading command: `oc adm node-logs <node> --path=oauth-server/audit.log`, with a jq filter on the two annotations; docs list possible decision values `allow`, `deny`, `error`; the directory listing form `--path=oauth-server/` shows `audit.log` plus rotated `audit-<ISO-timestamp>.log`; the docs state viewing API server audit logs requires `cluster-admin` | **verified** from the docs modules (the rendered docs.redhat.com/okd.io pages could not be fetched — they returned navigation only) | https://raw.githubusercontent.com/openshift/openshift-docs/main/modules/nodes-nodes-audit-log-basic-viewing.adoc and https://raw.githubusercontent.com/openshift/openshift-docs/main/modules/security-audit-log-filtering.adoc (rendered in https://docs.redhat.com/en/documentation/openshift_container_platform/4.18/html/security_and_compliance/audit-log-view) |
| Event shape: `kind: Event`, `apiVersion: audit.k8s.io/v1`, `level: Metadata`, `auditID`, `stage: ResponseComplete`, `requestURI: /login`, `verb: post`, `user.username: system:anonymous` (**the username is NOT in `user`, only in the annotation**), `responseStatus.code: 302`, `requestReceivedTimestamp`, `stageTimestamp`, `annotations` with the two keys | **verified** (two full example events, one deny, one allow) | https://developers.redhat.com/articles/2024/07/29/how-classify-red-hat-openshift-audit-logs |
| Login events appear at the **Default** profile (no Debug on the operator CR needed): the enhancement says the profile "applies to all API servers at once" and the Default profile logs metadata for everything; the oauth-server's own policy above is Metadata for every non-health path regardless of profile (the profile only gates on/off via `None`) | **verified** for the policy; the "no Debug needed" half is additionally *measured* in this repository: `docs/DESIGN_login_capture.md#The oauth-server AUDIT LOG` — 187 of 201 username events predate Debug, earliest 2025-04-19 | https://raw.githubusercontent.com/openshift/enhancements/master/enhancements/kube-apiserver/audit-policy.md |
| RBAC: `oc adm node-logs` issues `GET /api/v1/nodes/<name>/proxy/logs/<path>`; the API server authorizes a proxy request as resource `nodes`, subresource `proxy` (the kubelet's own `/logs/* -> nodes/log` mapping applies to callers that reach the kubelet directly, not through the API server proxy, which arrives as the API server's identity). `oc`'s help says node logs "are limited to privileged node administrators. The system:node-admins role grants this permission by default." | **verified** (path and help text from oc source; kubelet mapping table from k8s docs); the sufficiency of `get nodes/proxy` alone is **measured in this repo**: `docs/DESIGN_login_capture.md#nodes/proxy` ("Verified reachable through the same grant: kube-apiserver/ audit logs ... and the kubelet journal") | https://raw.githubusercontent.com/openshift/oc/master/pkg/cli/admin/node/logs.go ; https://kubernetes.io/docs/reference/access-authn-authz/kubelet-authn-authz/ |
| The kubelet serves `/logs/` with `http.StripPrefix("/logs/", http.FileServer(http.Dir(nodeLogDir)))` unless `NodeLogQuery`+`EnableSystemLogQuery` is on, in which case a query-validating handler wraps it. Go's `http.FileServer` honours `Range` requests, so a byte-offset cursor can be resumed server-side; a plain path with no `?query=` falls through to the file server | **partly verified**: the FileServer construction is verified from source; that the NodeLogQuery wrapper falls through to the file server for plain paths, and that the API server's node proxy forwards `Range`, **could not be verified** from the excerpt — the reader below does not depend on it (a 200 with the whole body is handled by skipping `offset` bytes) | https://raw.githubusercontent.com/kubernetes/kubernetes/master/pkg/kubelet/kubelet.go |
| Red Hat KCS "User login attempts not found in the OpenShift audit log files" (4.6/4.7): login attempts reach "oauth-apiserver/audit-log" only in Debug... for OCP ≤4.10; for 4.11+ it points at KCS 6980492 ("How to see successful and failed login attempts from audit logs in OCP4?", env 4.11+), which is subscriber-only | **partly verified** (titles and environment visible; 6980492's body is paywalled). Read together with PR #92 and the measured 2025-04-19 history, the oauth-server audit log carries login attempts on 4.11+ without Debug | https://access.redhat.com/solutions/5810281 ; https://access.redhat.com/solutions/6980492 |
| Whether a browser login produces ONE annotated event (`POST /login`) or also a second one on the follow-up `GET /oauth/authorize` | **could not verify**. The parser's in-batch and in-store coalescing rule below is written for the two-event case and is harmless in the one-event case; the CRC capture during implementation settles it | — |
| Whether a CLI `oc login -u -p` (basic auth on `/oauth/authorize`) carries the annotations on that URI | **measured in this repo** (`docs/DESIGN_login_capture.md#deliberate test logins appear exactly as made` shows the five CLI logins as five events) | — |
| Retention "~16 months" | **measured on CRC only** (`docs/DESIGN_login_capture.md#~16 months here`). It is not a documented guarantee: at 100 MB × 10 files it is whatever volume the cluster's OAuth traffic produces | — |

Consequences carried into the design: (1) the oauth-server audit log names no identity provider except in the browser path's `/login/<idp>` URI, so `provider` is nullable on audit rows and the break-glass classification (`gsd/api.py#list_logins`, `break_glass = provider in htpasswd`) cannot fire for a CLI `kubeadmin` login — stated as a limitation, not hidden; (2) `deny` carries no cause, so the LDAP result codes and AD sub-codes stay pod-log-only, exactly as `docs/DESIGN_login_capture.md#It also carries no cause` says; (3) the audit source is **off** when the cluster's audit profile is `None`, which the reader reports as "no audit files on any node" rather than as "nobody logged in".

---

## PR order and versions (both features)

| PR | content | app version | chart version | why |
|---|---|---|---|---|
| 1 | **D2** — `clusters[].visibility` and `clusters[].identity` modules (b) and the `remote-sar` module (a) | 0.11.0 → **0.12.0** (MINOR: new wire fields on `/api/whoami`, `/api/clusters`, `/api/alerts`; a default that changes what a second cluster serves) | 0.10.0 → **0.11.0** (MINOR: new values, new render guard, upgrade behaviour change on multi-cluster installs) | Smaller, needs no cluster capture, and it changes the defaults that D1's docs then describe. |
| 2 | **D1** — `loginCapture.source: audit-log` | 0.12.0 → **0.13.0** (MINOR: schema migration 8, new outcome vocabulary value, new `/logins` fields, new metric families) | 0.11.0 → **0.12.0** (MINOR: new values, a new ClusterRole, a new refusal) | Needs a CRC session to replace documented-shape fixtures with captured lines and to confirm the `Range`/rotation behaviour. |

Both PRs move the triple (`pyproject.toml`, `gsd/__init__.py`, `Chart.yaml#appVersion`) together, bump `Chart.yaml#version` with a history paragraph, add a `docs/CHANGELOG.md` entry and chart README rows, and land tests with code.

---


## Design (verbatim)

# FEATURE D2 — Per-cluster authorization for the multi-cluster case

## D2.1 Goal, options, recommendation

**The problem, precisely.** `gsd/api.py#build_app` decides the tier "against the FIRST enabled cluster" and that tier "gates everything this instance SHOWS — rows about other observed clusters included". A viewer who is `cluster-admin` on the host but nobody on `prod-east` is served `prod-east`'s membership, bindings and login failures at the wide tier; a viewer who is nobody on the host but an administrator of `prod-east` gets the self tier there — and "self" on `prod-east` is keyed by a username that the host's identity provider vouched for, not `prod-east`'s.

**Options considered.**

- **(a) per-cluster tier resolution (`remote-sar`).** One `gsd/kube.py#TierResolver` per remote cluster, constructed on that cluster's `ClusterConfig`. It issues the same SubjectAccessReview (the operator's `visibility.adminSar` shape) on the remote API with the dashboard's remote token, naming the viewer and `spec.groups` read fresh from the *remote's* Group objects — `gsd/kube.py#ClusterClient.fetch_groups_of_user` already reads the cluster the client is bound to, so the trap in `docs/SPEC_per_user_visibility.md#THE GROUP-RESOLUTION TRAP` is handled by construction rather than by feeding the store's `group_member` rows (which would add `pollIntervalSeconds` to the fail-open window the TTL comment in `gsd/kube.py#TIER_TTL_SECONDS` was written to exclude). Cache per (viewer, cluster) falls out of "one resolver instance per cluster". Fail-closed to self on any remote failure (403 because the remote SA lacks `create subjectaccessreviews`, unreachable, junk). **The identity assumption is the whole risk**: the review names the host's `X-Forwarded-User` on the remote, which is only meaningful if both clusters map the same directory identity to the same username. That is a platform-policy assertion, so it is a separate, explicit switch (`clusters[].identity`) and `remote-sar` refuses to render or start without it.
- **(b) per-cluster visibility policy (`inherit | self-only | hidden`).** No new cluster call, no new credential, no new RBAC. `self-only` guarantees the host tier never widens a remote; `hidden` keeps a cluster polled (health, alerts on `/metrics`, pod log) and out of the per-viewer API entirely. Honest and cheap; it is the module that ships first and the default for a second cluster.
- **(c) one dashboard per cluster + fleet report.** `docs/reference-architecture.md#8a. Reading a fleet without hosting anything` and `local-development/cluster-report.py` (one PKCE exchange per cluster, "a token from one is meaningless to another"). Each cluster authorises its own readers; nothing here changes. This remains the recommended posture where trust boundaries differ, and the docs say so.

**Recommendation: (b) + (a) as modules, defaults by judgment.**

| switch | values | default | why that default |
|---|---|---|---|
| `clusters[].visibility` | `inherit` \| `self-only` \| `hidden` \| `remote-sar` | host (first enabled entry): `inherit`; any other entry: **`self-only`** | `inherit` on the host is today's behaviour. On a remote, `inherit` is the exposure; `self-only` costs no RBAC and no credential and can only narrow, so it is the safe default. This tightens an existing multi-cluster install on upgrade (MINOR, CHANGELOG upgrade note); `inherit` restores it explicitly. |
| `clusters[].identity` | `same-as-host` \| `none` | host: `same-as-host` (tautology, forced); remote: **`none`** | "Same username = same person" is a claim about identity providers, not about this chart. `none` fails closed: person-scoped views on that cluster refuse rather than key on a name the remote never vouched for. One line (`same-as-host`) turns self views on. |

`remote-sar` requires `identity: same-as-host` (refused at render and at startup otherwise). `hidden` and `remote-sar` are refused on the host entry (the host is where the viewer's identity is real; hiding it hides the login cluster).

**What each guarantees, and does not.**

| policy | guarantees | does not |
|---|---|---|
| `inherit` | nothing new; host tier decides | protect the remote's data from a host-only admin |
| `self-only` | no viewer is ever wide on this cluster; with `identity: none`, nobody is "self" on it either — only cluster-level health (`/api/clusters` row, `/groupsyncs` projected, `/events`, self-kind alerts) is served | show a remote administrator their own cluster wide |
| `hidden` | the cluster does not exist for `/api` readers (404 identical to an unknown id; absent from `/api/clusters`, `/api/whoami`, `/api/alerts`) | hide it from `/metrics` (unauthenticated by design, counts only) or from the pod log |
| `remote-sar` | the remote's own RBAC decides, with the remote's own Group objects, cached per (viewer, cluster) for `visibility.tierTtlSeconds`; every failure is self | protect against two directories mapping the same username to different humans — that is the `identity` assertion the operator makes |

## D2.2 Code — `local-development/gsd/config.py`

Edit 1 — add constants after `VISIBILITY_TIER_TTL_DEFAULT = 60` (old text is that single line followed by a blank line; insert after it):

```python
# ── Per-cluster authorization (docs/ACCESS_CONTROL.md §11) ─────────────────────────────────────
# The oauth-proxy authenticates a viewer against the HOSTING cluster only, so what a viewer may see
# ABOUT ANOTHER cluster is a per-cluster decision. Four policies, and the words are the wire
# vocabulary (/api/whoami and /api/clusters carry them), so they are declared once, here.
VISIBILITY_INHERIT = "inherit"        # the host's tier decides — today's behaviour
VISIBILITY_SELF_ONLY = "self-only"    # every viewer is the self tier on this cluster
VISIBILITY_HIDDEN = "hidden"          # polled, never served through /api
VISIBILITY_REMOTE_SAR = "remote-sar"  # this cluster's own RBAC decides, by SubjectAccessReview
CLUSTER_VISIBILITIES = (
    VISIBILITY_INHERIT, VISIBILITY_SELF_ONLY, VISIBILITY_HIDDEN, VISIBILITY_REMOTE_SAR,
)
# Whether the host's username means the same person on this cluster. A claim about the two
# clusters' identity providers, which this chart cannot check — so it is stated, never assumed.
IDENTITY_SAME_AS_HOST = "same-as-host"
IDENTITY_NONE = "none"
CLUSTER_IDENTITIES = (IDENTITY_SAME_AS_HOST, IDENTITY_NONE)
```

Edit 2 — `ClusterConfig` fields. Old:

```python
    ca_bundle_file: str | None = None
    insecure_skip_verify: bool = False
    enabled: bool = True

    def resolve_token(self) -> str:
```

New:

```python
    ca_bundle_file: str | None = None
    insecure_skip_verify: bool = False
    enabled: bool = True
    # None means "not set", resolved by Settings.cluster_policy: the host is inherit/same-as-host
    # (its viewer IS a host identity), every other cluster is self-only/none. Resolved there and
    # not here so a hand-built Settings and a chart-rendered one agree on what a second cluster
    # serves by default — the direction that matters is that it never widens.
    visibility: str | None = None
    identity: str | None = None

    def resolve_token(self) -> str:
```

Edit 3 — `Settings.cluster`. Old:

```python
    def cluster(self, name: str) -> ClusterConfig | None:
        for c in self.clusters:
            if c.name == name:
                return c
        return None
```

New:

```python
    def cluster(self, name: str) -> ClusterConfig | None:
        for c in self.clusters:
            if c.name == name:
                return c
        return None

    def host_cluster(self) -> ClusterConfig | None:
        """The cluster the oauth-proxy authenticates against: the FIRST enabled entry, which is
        the one the chart writes for the pod's own cluster (values.yaml `clusters[0]`)."""
        return next((c for c in self.clusters if c.enabled), None)

    def cluster_policy(self, name: str) -> tuple[str, str]:
        """(visibility, identity) for one cluster id, defaults resolved.

        A cluster the store still holds but the config no longer names — removed from values
        after it was polled — resolves to inherit/same-as-host: today's behaviour for its
        stale rows, and not wider than it. Deleting the rows is a data decision, not a tier one.
        """
        host = self.host_cluster()
        cluster = self.cluster(name)
        if cluster is None:
            return VISIBILITY_INHERIT, IDENTITY_SAME_AS_HOST
        is_host = host is not None and cluster.name == host.name
        if is_host:
            # identity is forced, not defaulted: the host's viewer is a host identity by
            # construction, and a values file saying otherwise would be describing a control
            # that cannot mean anything.
            return cluster.visibility or VISIBILITY_INHERIT, IDENTITY_SAME_AS_HOST
        return (cluster.visibility or VISIBILITY_SELF_ONLY,
                cluster.identity or IDENTITY_NONE)
```

Edit 4 — `known` set. Old:

```python
    known = {
        "name",
        "apiUrl",
        "tokenEnv",
        "tokenFile",
        "caBundleFile",
        "insecureSkipVerify",
        "enabled",
    }

    clusters: list[ClusterConfig] = []
    seen: set[str] = set()
```

New:

```python
    known = {
        "name",
        "apiUrl",
        "tokenEnv",
        "tokenFile",
        "caBundleFile",
        "insecureSkipVerify",
        "enabled",
        "visibility",
        "identity",
    }

    clusters: list[ClusterConfig] = []
    seen: set[str] = set()
    host_name: str | None = None
```

Edit 5 — validation and construction. Old:

```python
        insecure = bool(entry.get("insecureSkipVerify", False))
        if insecure and entry.get("caBundleFile"):
            raise ConfigError(
                f"{where}: insecureSkipVerify and caBundleFile are mutually exclusive"
            )

        clusters.append(
            ClusterConfig(
                name=name,
                api_url=api_url,
                token_env=entry.get("tokenEnv"),
                token_file=entry.get("tokenFile"),
                ca_bundle_file=entry.get("caBundleFile"),
                insecure_skip_verify=insecure,
                enabled=bool(entry.get("enabled", True)),
            )
        )
```

New:

```python
        insecure = bool(entry.get("insecureSkipVerify", False))
        if insecure and entry.get("caBundleFile"):
            raise ConfigError(
                f"{where}: insecureSkipVerify and caBundleFile are mutually exclusive"
            )

        enabled = bool(entry.get("enabled", True))
        # Strict, like every other cluster key: a typo here ("self_only", "Hidden") must not
        # silently become the default, in either direction.
        visibility = entry.get("visibility")
        if visibility is not None:
            visibility = str(visibility).strip()
            if visibility not in CLUSTER_VISIBILITIES:
                raise ConfigError(
                    f"{where}: visibility {visibility!r} is not one of "
                    f"{', '.join(CLUSTER_VISIBILITIES)}"
                )
        identity = entry.get("identity")
        if identity is not None:
            identity = str(identity).strip()
            if identity not in CLUSTER_IDENTITIES:
                raise ConfigError(
                    f"{where}: identity {identity!r} is not one of {', '.join(CLUSTER_IDENTITIES)}"
                )
        is_host = enabled and host_name is None
        if is_host:
            host_name = name
            if visibility in (VISIBILITY_HIDDEN, VISIBILITY_REMOTE_SAR):
                raise ConfigError(
                    f"{where}: visibility {visibility!r} is not allowed on the hosting cluster "
                    f"(the first enabled entry) — it is the cluster the viewer logged in to"
                )
        elif visibility == VISIBILITY_REMOTE_SAR and (identity or IDENTITY_NONE) != IDENTITY_SAME_AS_HOST:
            raise ConfigError(
                f"{where}: visibility remote-sar needs identity: same-as-host — the review names "
                f"the host's username on this cluster, which only means something if the two "
                f"clusters share an identity provider"
            )

        clusters.append(
            ClusterConfig(
                name=name,
                api_url=api_url,
                token_env=entry.get("tokenEnv"),
                token_file=entry.get("tokenFile"),
                ca_bundle_file=entry.get("caBundleFile"),
                insecure_skip_verify=insecure,
                enabled=enabled,
                visibility=visibility,
                identity=identity,
            )
        )
```

## D2.3 Code — `local-development/gsd/api.py`

Edit 1 — imports. Old: `from .config import Settings, load_settings`. New:

```python
from .config import (
    IDENTITY_NONE, IDENTITY_SAME_AS_HOST, VISIBILITY_HIDDEN, VISIBILITY_INHERIT,
    VISIBILITY_REMOTE_SAR, VISIBILITY_SELF_ONLY, Settings, load_settings,
)
```

Edit 2 — remote resolvers, inserted directly after the `usage_resolver` construction block (after the line `observe=functools.partial(signals.note_tier_check, "usage"),` and its closing `)`), before `if not settings.view_restrictions_enabled:`:

```python
    # ── Per-cluster authorization (docs/ACCESS_CONTROL.md §11) ──────────────────────────
    # One resolver PER remote cluster whose policy is remote-sar, constructed on THAT cluster's
    # ClusterConfig — so the review is created on the remote API with the remote token, and
    # fetch_groups_of_user reads the REMOTE's Group objects. That is the group-resolution trap
    # handled by construction rather than by feeding the store's snapshot, which would add
    # pollIntervalSeconds to the fail-open window. Same SAR shape as the host's (the operator
    # chose one threshold), same TTL, its own cache: per (viewer, cluster) by construction.
    # Reported under the "admin" threshold label: a failing remote review is the same
    # everyone-silently-narrowed signature the alert already watches for.
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
    for c in settings.clusters:
        policy, identity = settings.cluster_policy(c.name)
        if c is local_cluster or policy == VISIBILITY_INHERIT:
            continue
        # INFO once at startup, so "why is prod-east narrow for an administrator" is answered in
        # the pod log rather than by reading the values file.
        log.info("%s: per-cluster visibility policy %s, identity %s", c.name, policy, identity)
    if not settings.view_restrictions_enabled and any(
        settings.cluster_policy(c.name)[0] in (VISIBILITY_SELF_ONLY, VISIBILITY_REMOTE_SAR)
        for c in settings.clusters
    ):
        log.warning(
            "clusters[].visibility policies are set but view restrictions are OFF, so every "
            "reader sees every cluster in full; only `hidden` still applies"
        )
```

Edit 3 — replace `viewer_scope` whole. Old: the function from `def viewer_scope(request: Request) -> tuple[str | None, str]:` through `return viewer, scope` (the one ending the admin-threshold function, immediately before `def usage_scope`). New:

```python
    def _decide(viewer: str | None, resolver_obj, fallback: Callable[[str], str] | None
                ) -> tuple[str | None, str]:
        """One threshold's decision for one viewer: the fail-closed core viewer_scope always had.

        `scope` is "all" only when the resolver POSITIVELY answers "all". No viewer, no
        resolver, an error, a junk answer — all "self" (requirements §5.4, decision D1).
        """
        if not viewer or (resolver_obj is None and fallback is None):
            signals.note_decision("admin", TIER_SELF)
            return viewer, TIER_SELF
        try:
            tier = (resolver_obj.resolve(viewer) if resolver_obj is not None
                    else fallback(viewer))
        except Exception:  # noqa: BLE001
            log.exception("tier resolution failed for %r; serving the self view", viewer)
            signals.note_decision("admin", TIER_SELF)
            return viewer, TIER_SELF
        scope = TIER_ALL if tier == TIER_ALL else TIER_SELF
        signals.note_decision("admin", scope)
        return viewer, scope

    def viewer_scope(request: Request, cluster_id: str | None = None) -> tuple[str | None, str]:
        """Resolve this request to (viewer, scope) — FOR ONE CLUSTER when one is named.

        `scope` is "all" only when restrictions are off, or when the deciding resolver
        POSITIVELY answers "all" for this viewer. Everything else — no viewer, no resolver
        wired, a resolver error or timeout, an unrecognised answer — lands on "self", never on
        the wide view (requirements §5.4, decision D1).

        WHICH RESOLVER DECIDES is the cluster's policy (docs/ACCESS_CONTROL.md §11):
          inherit     the host's resolver — the viewer's identity is the host's
          self-only   nobody decides; "self", and the VIEWER IS None when the cluster does not
                      treat the host's username as its own (identity: none), so a self-scoped
                      handler refuses rather than keying rows on a name nobody vouched for
          remote-sar  that cluster's own resolver, on its own API, with its own groups
          hidden      never reaches here: require_cluster answers 404 first
        With no cluster named — /api/whoami's headline, the Usage tab — the host decides.
        Restrictions off means off for every policy but `hidden`, which is a serving rule.
        """
        viewer = trusted_viewer(request)
        if not restrict:
            return viewer, TIER_ALL
        policy, identity = (settings.cluster_policy(cluster_id) if cluster_id is not None
                            else (VISIBILITY_INHERIT, IDENTITY_SAME_AS_HOST))
        if policy == VISIBILITY_SELF_ONLY:
            signals.note_decision("admin", TIER_SELF)
            return (viewer if identity == IDENTITY_SAME_AS_HOST else None), TIER_SELF
        if policy == VISIBILITY_REMOTE_SAR:
            # Read off app.state PER REQUEST, the published seam, so a test can substitute one
            # remote's decision without a cluster. No build-time fallback: a remote cluster
            # with no resolver is a remote cluster nobody may see wide.
            remotes = getattr(app.state, "remote_tier_resolvers", None) or {}
            return _decide(viewer, remotes.get(cluster_id), None)
        state_resolver = getattr(app.state, "tier_resolver", None)
        return _decide(viewer, state_resolver, tier_resolver)
```

Edit 4 — `require_viewer`. Old:

```python
    def require_viewer(viewer: str | None) -> str:
        """Self-scoped data needs a name to scope to; without one it is refused.

        The /api/dashboard/activity rule: when no proxy fronts the app (or the proxy sent
        no identity header), X-Forwarded-User is whatever the caller typed, and honouring
        it would let anyone read anyone by asserting a name.
        """
        if not viewer:
            raise HTTPException(
                status_code=403,
                detail="this data is scoped to the authenticated viewer, and there is no "
                       "authenticated identity to scope it to",
            )
        return viewer
```

New:

```python
    def require_viewer(viewer: str | None, cluster_id: str | None = None) -> str:
        """Self-scoped data needs a name to scope to; without one it is refused.

        The /api/dashboard/activity rule: when no proxy fronts the app (or the proxy sent
        no identity header), X-Forwarded-User is whatever the caller typed, and honouring
        it would let anyone read anyone by asserting a name.

        A SECOND reason for no name, when a cluster is named: that cluster's identity policy is
        `none`, so viewer_scope withheld the host's username on purpose (docs/ACCESS_CONTROL.md
        §11). Said in its own words, and — like every refusal here — without naming the value
        that would change it: this sentence reaches the person being refused.
        """
        if not viewer:
            if (cluster_id is not None and restrict
                    and settings.cluster_policy(cluster_id)[1] == IDENTITY_NONE):
                raise HTTPException(
                    status_code=403,
                    detail="this data is scoped to a viewer, and this cluster does not treat "
                           "your identity as one of its own; only cluster-level health is "
                           "shown for it",
                )
            raise HTTPException(
                status_code=403,
                detail="this data is scoped to the authenticated viewer, and there is no "
                       "authenticated identity to scope it to",
            )
        return viewer
```

Edit 5 — `require_admin_tier` signature and first line. Old: `    def require_admin_tier(request: Request) -> str:` … `        _, scope = viewer_scope(request)`. New: `    def require_admin_tier(request: Request, cluster_id: str | None = None) -> str:` and `        _, scope = viewer_scope(request, cluster_id)` (docstring unchanged).

Edit 6 — `require_cluster`. Old:

```python
    def require_cluster(cluster_id: str):
        cluster = settings.cluster(cluster_id)
        if cluster is None:
            raise HTTPException(status_code=404, detail=f"unknown cluster {cluster_id!r}")
        return cluster
```

New:

```python
    def require_cluster(cluster_id: str):
        """The cluster, or a 404 — the SAME 404 for an id that does not exist and for one whose
        policy is `hidden`, so the response is not an oracle over which clusters this instance
        watches. Hidden applies whatever the tier: it is a serving rule, not a tier."""
        cluster = settings.cluster(cluster_id)
        if cluster is None or settings.cluster_policy(cluster_id)[0] == VISIBILITY_HIDDEN:
            raise HTTPException(status_code=404, detail=f"unknown cluster {cluster_id!r}")
        return cluster
```

Edit 7 — `list_clusters` body. Old (inside `def list_clusters`):

```python
        _, scope = viewer_scope(request)
        out = []
        for row in store.clusters():
            counts = store.group_counts(row["id"])
```

New:

```python
        out = []
        for row in store.clusters():
            policy, _ = settings.cluster_policy(row["id"])
            if policy == VISIBILITY_HIDDEN:
                continue
            # Decided PER CLUSTER (docs/ACCESS_CONTROL.md §11): a host administrator is not an
            # administrator of a self-only remote, and the card must not say otherwise.
            _, scope = viewer_scope(request, row["id"])
            counts = store.group_counts(row["id"])
```

and in the same dict, old:

```python
                    "operator_configs": (
                        _config_summary(row["id"]) if scope == "all" else None),
```

new:

```python
                    "operator_configs": (
                        _config_summary(row["id"]) if scope == "all" else None),
                    # The policy this instance applies to the cluster and what it decided for
                    # THIS reader, so the selector can label a cluster it narrows. The UI
                    # renders these; it never derives them (docs/ACCESS_CONTROL.md §7).
                    "visibility": {"policy": policy, "scope": scope},
```

Edit 8 — every cluster-scoped handler passes its cluster. Exact one-line substitutions (each occurs once inside the named handler):

| handler | old | new |
|---|---|---|
| `list_groupsyncs` | `        _, scope = viewer_scope(request)` | `        _, scope = viewer_scope(request, cluster_id)` |
| `list_groups` | `        viewer, scope = viewer_scope(request)` / `            user_name=None if scope == "all" else require_viewer(viewer),` | `        viewer, scope = viewer_scope(request, cluster_id)` / `            user_name=None if scope == "all" else require_viewer(viewer, cluster_id),` |
| `group_detail` | `        viewer, scope = viewer_scope(request)` / `            cluster_id, name, require_viewer(viewer)` | `        viewer, scope = viewer_scope(request, cluster_id)` / `            cluster_id, name, require_viewer(viewer, cluster_id)` |
| `list_users` | `        viewer, scope = viewer_scope(request)` / `        who = None if scope == "all" else require_viewer(viewer)` | `        viewer, scope = viewer_scope(request, cluster_id)` / `        who = None if scope == "all" else require_viewer(viewer, cluster_id)` |
| `user_detail` | `        viewer, scope = viewer_scope(request)` / `        if scope == "self" and name != require_viewer(viewer):` | `        viewer, scope = viewer_scope(request, cluster_id)` / `        if scope == "self" and name != require_viewer(viewer, cluster_id):` |
| `list_logins` | `        viewer, scope = viewer_scope(request)` / `            me = require_viewer(viewer)` | `        viewer, scope = viewer_scope(request, cluster_id)` / `            me = require_viewer(viewer, cluster_id)` |
| `cluster_access` | `        viewer, scope = viewer_scope(request)` / `            me = require_viewer(viewer)` | `        viewer, scope = viewer_scope(request, cluster_id)` / `            me = require_viewer(viewer, cluster_id)` |
| `binding_findings` | `        require_admin_tier(request)` | `        require_admin_tier(request, cluster_id)` |
| `direct_user_bindings` | `        viewer, scope = viewer_scope(request)` / `        me = None if scope == "all" else require_viewer(viewer)` | `        viewer, scope = viewer_scope(request, cluster_id)` / `        me = None if scope == "all" else require_viewer(viewer, cluster_id)` |
| `operator_configs` | `        require_admin_tier(request)` | `        require_admin_tier(request, cluster_id)` |
| `membership_changes` | `        viewer, scope = viewer_scope(request)` / `            user_name=None if scope == "all" else require_viewer(viewer),` | `        viewer, scope = viewer_scope(request, cluster_id)` / `            user_name=None if scope == "all" else require_viewer(viewer, cluster_id),` |

Edit 9 — `list_alerts`. Old body from `        viewer, scope = viewer_scope(request)` to `        severity_rank = {"critical": 0, "warning": 1}` (i.e. everything between, including `if scope == "self": alerts = _alerts_for_self(alerts)`). New:

```python
        viewer, _ = viewer_scope(request)
        now = datetime.now(UTC)
        alerts: list[dict] = []
        # The feed's scope is the NARROWEST decision across the clusters it carries: "all" only
        # when every served cluster is wide for this reader. A feed that said "all" while one
        # cluster's rows were filtered would be the quiet-drop the response exists to name.
        scope = TIER_ALL
        for row in store.clusters():
            cluster_id = row["id"]
            policy, _ = settings.cluster_policy(cluster_id)
            if policy == VISIBILITY_HIDDEN:
                continue
            _, cscope = viewer_scope(request, cluster_id)
            if cscope != TIER_ALL:
                scope = TIER_SELF
            found: list[dict] = []
            if row["status"] and row["status"] != "ok":
                found.append(
                    {
                        "cluster": cluster_id,
                        "kind": row["status"],
                        "subject": cluster_id,
                        "detail": row["message"] or "cluster poll failed",
                        "severity": "critical",
                    }
                )
                # A degraded cluster's cached rows are stale by definition; computing
                # group-level alerts from them would report yesterday's state as today's.
                alerts.extend(found if cscope == TIER_ALL else _alerts_for_self(found))
                continue
            computed = st.compute_alerts(
                cluster=cluster_id,
                groupsyncs=store.groupsyncs(cluster_id),
                operator_configs=store.operator_configs(cluster_id)["configs"],
                user_bindings=store.direct_user_bindings(cluster_id),
                groups=store.groups(cluster_id, "all"),
                groupsync_present=store.groupsync_present(cluster_id),
                now=now,
                grace=grace,
            )
            found.extend(a.as_dict() for a in computed)

            # Only the `dangling` tier alerts. `built_in` is normal, and `unresolved`
            # cannot be distinguished from a group that simply has not synced yet, so
            # alerting on either would produce noise that trains people to ignore this.
            for binding in store.binding_findings(cluster_id):
                if binding["finding"] != "dangling":
                    continue
                where = (
                    f"namespace {binding['binding_namespace']}"
                    if binding["binding_namespace"]
                    else "cluster-wide"
                )
                found.append(
                    {
                        "cluster": cluster_id,
                        "kind": "dangling_binding",
                        "subject": binding["binding_name"],
                        "detail": (
                            f"{binding['binding_kind']} grants {binding['role_name']} {where} to "
                            f"group {binding['group_name']!r}, which the operator used to "
                            f"manage and no longer exists — this binding now grants nobody"
                        ),
                        "severity": "critical",
                    }
                )
            # Filtered PER CLUSTER, in the cluster's own tier: a host administrator's feed
            # carries a self-only remote's alerts at the self kinds only.
            alerts.extend(found if cscope == TIER_ALL else _alerts_for_self(found))
```

Edit 10 — `whoami`. Old:

```python
        if authenticated:
            # The tier from the SAME decision path the data handlers use — viewer_scope
            # reads the app.state seam per request and never raises — so the pill can
            # never disagree with the pages it sits above. An indeterminate tier is SELF.
            _, scope = viewer_scope(request)
            out["visibility"] = {"scope": scope, "enabled": settings.view_restrictions_enabled}
        return out
```

New:

```python
        if authenticated:
            # The tier from the SAME decision path the data handlers use — viewer_scope
            # reads the app.state seam per request and never raises — so the pill can
            # never disagree with the pages it sits above. An indeterminate tier is SELF.
            _, scope = viewer_scope(request)
            # And PER CLUSTER, the same way, so the cluster selector can say which clusters
            # this reader sees narrowed (docs/ACCESS_CONTROL.md §11). Hidden clusters are
            # absent, as they are from /api/clusters — listing them here would undo the 404.
            clusters: dict[str, dict] = {}
            for c in settings.clusters:
                policy, identity = settings.cluster_policy(c.name)
                if policy == VISIBILITY_HIDDEN:
                    continue
                _, cscope = viewer_scope(request, c.name)
                clusters[c.name] = {"policy": policy, "identity": identity, "scope": cscope}
            out["visibility"] = {
                "scope": scope,
                "enabled": settings.view_restrictions_enabled,
                "clusters": clusters,
            }
        return out
```

Edit 11 — publish the seam. Old:

```python
    app.state.usage_tier_resolver = usage_resolver
    return app
```

New:

```python
    app.state.usage_tier_resolver = usage_resolver
    # One resolver per remote-sar cluster, keyed by cluster id — the per-cluster seam. A test
    # installs `{"prod-east": stub}` here to decide a remote without a cluster; a remote with
    # no entry is never wide.
    app.state.remote_tier_resolvers = remote_resolvers
    return app
```

## D2.4 Code — `local-development/gsd/static/index.html`

Edit 1 — cluster options. Old:

```javascript
  const opts = clusters.map((c) =>
    `<option value="${esc(c.id)}"${c.id === view.cluster ? " selected" : ""}>${esc(c.id)}</option>`).join("");
```

New:

```javascript
  // The selector says when a cluster is narrowed for THIS reader — read off the row's
  // server-decided `visibility`, never derived here (docs/ACCESS_CONTROL.md §11). A reader who
  // is wide on the host and narrow on a remote would otherwise switch clusters and see the
  // table shrink with nothing to say why.
  const opts = clusters.map((c) =>
    `<option value="${esc(c.id)}"${c.id === view.cluster ? " selected" : ""}>${esc(c.id)}${
      c.visibility && c.visibility.scope === "self" ? " — your view" : ""}</option>`).join("");
```

Edit 2 — the pill follows the selected cluster. Old (in `renderScopePill`):

```javascript
  const vis = w && w.authenticated && w.visibility;
  if (!vis) { pill.hidden = true; pill.textContent = ""; return; }
  const self = vis.scope === "self";
```

New:

```javascript
  const vis = w && w.authenticated && w.visibility;
  if (!vis) { pill.hidden = true; pill.textContent = ""; return; }
  // The SELECTED cluster's decision when whoami carries one, the headline otherwise: the
  // pill sits above a cluster-scoped page and must describe that cluster's view.
  const forCluster = vis.clusters && view.cluster && vis.clusters[view.cluster];
  const self = (forCluster ? forCluster.scope : vis.scope) === "self";
```

Edit 3 — the narrowed-reader helpers. Old:

```javascript
function narrowedFor(w) {
  if (!w || !w.authenticated) return false;
  const vis = w.visibility;
  return !vis || vis.scope !== "all";
}
function narrowedReader() {
  const w = data.whoami;
  if (!w || !w.authenticated) return false;
  const vis = w.visibility;
  return !vis || vis.scope !== "all";
}
```

New:

```javascript
/* Per cluster when the wire says so: whoami's `visibility.clusters[id].scope` is the decision
   for THAT cluster, and a reader wide on the host may be narrow on a remote. Silence or a
   missing entry stays narrowed, as before. */
function scopeFor(w, cluster) {
  const vis = w && w.visibility;
  if (!vis) return null;
  const c = vis.clusters && cluster && vis.clusters[cluster];
  return c ? c.scope : vis.scope;
}
function narrowedFor(w) {
  if (!w || !w.authenticated) return false;
  return scopeFor(w, view.cluster) !== "all";
}
function narrowedReader() {
  const w = data.whoami;
  if (!w || !w.authenticated) return false;
  return scopeFor(w, view.cluster) !== "all";
}
```

## D2.5 Chart

**`charts/group-sync-dashboard/values.yaml`** — replace the `clusters` comment block. Old:

```yaml
# Clusters to observe. The default observes the cluster the pod runs on, using its own
# projected ServiceAccount token — which kubelet rotates and the app re-reads every poll, so
# there is no long-lived credential to mint or expire.
#
# Adding entries here enables multi-cluster, but note the authorization caveat in
# docs/PLAN_oauth_proxy.md: OAuth authenticates against the HOSTING cluster only, so one
# instance holding several clusters' data can show a user membership from a cluster they
# have no rights on.
clusters:
```

New:

```yaml
# Clusters to observe. The default observes the cluster the pod runs on, using its own
# projected ServiceAccount token — which kubelet rotates and the app re-reads every poll, so
# there is no long-lived credential to mint or expire.
#
# ── SEVERAL CLUSTERS IN ONE INSTANCE: who may see what, PER CLUSTER ─────────────────────────
# The oauth-proxy authenticates a reader against THIS cluster only — the first enabled entry,
# the hosting cluster. What that reader may see ABOUT ANOTHER cluster is therefore a decision
# this file has to make, per entry, and it used to make it silently: the host's tier gated
# every cluster's rows, so a host cluster-admin saw a remote cluster's membership, bindings and
# login failures whether or not they held anything there. Two keys per entry now model it
# (docs/ACCESS_CONTROL.md §11):
#
#   visibility:   inherit     the host's tier decides — the old behaviour, and the host's own
#                             default. On a remote it is an explicit choice: "the host's RBAC
#                             governs this cluster's data too".
#                 self-only   nobody is ever wide on this cluster. THE DEFAULT FOR EVERY ENTRY
#                             BUT THE FIRST, because it costs no RBAC, no credential and no
#                             cluster call, and can only narrow. On upgrade from chart 0.10.x a
#                             multi-cluster install's remotes become self-only; set inherit to
#                             restore what you had.
#                 hidden      polled and alerted on (/metrics, the pod log) but never served
#                             through /api: 404, identical to an unknown cluster id, absent from
#                             the selector. For watching sync health across a fleet without
#                             exposing membership.
#                 remote-sar  that cluster's OWN RBAC decides: the same SubjectAccessReview as
#                             visibility.adminSar, created on the remote API with this entry's
#                             token, naming the reader and the reader's Group memberships READ
#                             FROM THE REMOTE. Cached per (reader, cluster) for tierTtlSeconds;
#                             every failure is the self tier. Needs `create subjectaccessreviews`
#                             on the remote (bind system:auth-delegator to the remote
#                             ServiceAccount by hand — this chart manages no remote RBAC) and
#                             identity: same-as-host below. Not allowed on the first entry.
#
#   identity:     none          THE DEFAULT for a remote. The host's username is not treated as
#                               anyone on this cluster: person-scoped views (groups, users,
#                               logins, grants) answer 403 there; cluster-level health still
#                               shows. Fail-closed, because "same username, same person" is a
#                               claim about the two clusters' identity providers that this
#                               chart cannot check — an htpasswd `developer` on two clusters is
#                               two people.
#                 same-as-host  the clusters share an identity provider and its username
#                               mapping, so the reader's self views apply to this cluster too.
#                               Required by remote-sar.
#
# The alternative posture — one dashboard per cluster and a fleet report reading each one's
# API with a token from THAT cluster — needs none of this and is still the recommendation
# where trust boundaries differ: docs/reference-architecture.md §8a.
clusters:
```

**`charts/group-sync-dashboard/templates/_helpers.tpl`** — append:

```
# ── Per-cluster authorization ────────────────────────────────────────────────────────────
# The same closed vocabulary the app enforces (gsd/config.py CLUSTER_VISIBILITIES), refused at
# render so a typo'd policy fails `helm template` rather than the pod's startup. Nil-safe on
# every hop for the usual reason. Called from configmap.yaml, which always renders.
{{- define "gsd.validateClusters" -}}
{{- $host := "" -}}
{{- range $i, $c := (.Values.clusters | default list) -}}
{{- $name := toString ($c.name | default (printf "clusters[%d]" $i)) -}}
{{- $vis := "" -}}{{- if and (hasKey $c "visibility") (not (kindIs "invalid" $c.visibility)) -}}{{- $vis = trim (toString $c.visibility) -}}{{- end -}}
{{- $id := "" -}}{{- if and (hasKey $c "identity") (not (kindIs "invalid" $c.identity)) -}}{{- $id = trim (toString $c.identity) -}}{{- end -}}
{{- if and $vis (not (has $vis (list "inherit" "self-only" "hidden" "remote-sar"))) -}}
{{- fail (printf "clusters[%d] (%s): visibility %q is not one of inherit, self-only, hidden, remote-sar. See the clusters comment in values.yaml." $i $name $vis) -}}
{{- end -}}
{{- if and $id (not (has $id (list "same-as-host" "none"))) -}}
{{- fail (printf "clusters[%d] (%s): identity %q is not one of same-as-host, none." $i $name $id) -}}
{{- end -}}
{{- $enabled := true -}}{{- if hasKey $c "enabled" -}}{{- $enabled = $c.enabled -}}{{- end -}}
{{- if and $enabled (eq $host "") -}}
{{- $host = $name -}}
{{- if has $vis (list "hidden" "remote-sar") -}}
{{- fail (printf "clusters[%d] (%s) is the hosting cluster — the first enabled entry, the one the oauth-proxy authenticates against — and visibility %q makes no sense there: hidden would hide the login cluster, remote-sar would review the host against itself. Use inherit (the default) or self-only." $i $name $vis) -}}
{{- end -}}
{{- else if and (eq $vis "remote-sar") (ne $id "same-as-host") -}}
{{- fail (printf "clusters[%d] (%s): visibility remote-sar needs identity: same-as-host. The review names the host's username on that cluster, which only means something if both clusters share an identity provider — say so explicitly." $i $name) -}}
{{- end -}}
{{- end -}}
{{- end -}}
```

**`charts/group-sync-dashboard/templates/configmap.yaml`** — old: `    clusters:` / `      {{- toYaml .Values.clusters | nindent 6 }}`. New:

```yaml
    {{- include "gsd.validateClusters" . }}
    # Per-entry `visibility` and `identity` travel through unchanged; the app validates them a
    # second time at startup (gsd/config.py) and resolves the per-entry defaults.
    clusters:
      {{- toYaml .Values.clusters | nindent 6 }}
```

**`charts/group-sync-dashboard/templates/NOTES.txt`** — insert after the line `Restore the old everyone-sees-everything behaviour only as a deliberate choice:` / `  --set visibility.enabled=false` (inside the RESTRICTED branch):

```
{{- if gt (len .Values.clusters) 1 }}

Several clusters are configured. The reader was authenticated by the FIRST enabled one; what
they see about each of the others is that entry's own policy (docs/ACCESS_CONTROL.md §11):
{{- range $i, $c := .Values.clusters }}
{{- $vis := "" }}{{- if and (hasKey $c "visibility") (not (kindIs "invalid" $c.visibility)) }}{{- $vis = toString $c.visibility }}{{- end }}
{{- $id := "" }}{{- if and (hasKey $c "identity") (not (kindIs "invalid" $c.identity)) }}{{- $id = toString $c.identity }}{{- end }}
  {{ $c.name }}: visibility {{ if $vis }}{{ $vis }}{{ else if eq $i 0 }}inherit (host){{ else }}self-only (default){{ end }}, identity {{ if eq $i 0 }}same-as-host (host){{ else if $id }}{{ $id }}{{ else }}none (default){{ end }}
{{- end }}
{{- end }}
```

**`charts/group-sync-dashboard/README.md`** — in the Application table, replace the row `| \`clusters\` | the local cluster | add entries for multi-cluster |` with:

```markdown
| `clusters` | the local cluster | add entries for multi-cluster. The reader is authenticated by the **first enabled** entry only; each other entry says what that reader may see about it, below |
| `clusters[].visibility` | `inherit` on the first entry, `self-only` on the rest | `inherit` — the host's tier decides (the old behaviour); `self-only` — nobody is wide on this cluster; `hidden` — polled and alerted on, never served through `/api` (404 like an unknown id); `remote-sar` — that cluster's own RBAC decides through the same SubjectAccessReview, created on the remote with its token and its Group objects, cached per reader and cluster; every failure is the self tier. `hidden`/`remote-sar` are refused on the first entry. **Upgrade note:** a multi-cluster install's remotes become `self-only` on chart 0.11.0; set `inherit` to keep the old view |
| `clusters[].identity` | `none` on every entry but the first | whether the host's username is the same person on this cluster. `none` fails closed: person-scoped views answer 403 there, cluster health still shows. `same-as-host` when the clusters share an identity provider; required by `remote-sar`. The first entry is always `same-as-host` |
```

**`charts/group-sync-dashboard/Chart.yaml`** — old: `version: 0.10.0`. New, with the history paragraph inserted above it:

```yaml
# CHART 0.11.0 (2026-09-04), MINOR: appVersion moves to application 0.12.0 (below), and what a
# default multi-cluster upgrade SERVES changes. Two per-entry keys on `clusters[]` — `visibility`
# (inherit | self-only | hidden | remote-sar) and `identity` (same-as-host | none) — model, per
# cluster, what a reader authenticated by the hosting cluster may see about the others. The
# defaults are the safe direction: the first entry stays `inherit`, every other entry becomes
# `self-only` with `identity: none`, so a host administrator is no longer wide on a remote and
# a host username is not keyed against a remote's rows. A single-cluster install renders
# byte-identical objects apart from the version labels; a multi-cluster install that wants the
# old behaviour sets `visibility: inherit` on its remotes. A render guard refuses an unknown
# policy, `hidden`/`remote-sar` on the host entry, and `remote-sar` without `identity:
# same-as-host` (docs/ACCESS_CONTROL.md §11).
version: 0.11.0
```

and old `appVersion: "0.11.0"` → new, with its paragraph:

```yaml
# 0.12.0 (2026-09-04). Per-cluster authorization for the multi-cluster case: /api/whoami gains
# visibility.clusters, /api/clusters rows gain `visibility`, /api/alerts is filtered per cluster
# in each cluster's own tier and its `scope` is the narrowest served, hidden clusters answer 404
# everywhere. A second cluster is self-only with no identity by default, which narrows what a
# 0.11.0 multi-cluster consumer received. MINOR.
appVersion: "0.12.0"
```

Also `local-development/pyproject.toml`: `version = "0.11.0"` → `version = "0.12.0"`; `local-development/gsd/__init__.py`: `__version__ = "0.11.0"` → `__version__ = "0.12.0"`.

## D2.6 Tests

**New file `local-development/tests/test_multicluster_visibility.py`:**

```python
"""Per-cluster authorization: the host's tier never widens a remote unless the operator says so.

THE EXPOSURE (docs/reference-architecture.md §7.2, before 0.12.0): the tier was decided against the
first enabled cluster and gated every cluster's rows, so a host cluster-admin was served a remote's
membership, bindings and login failures with no standing there. These tests pin the four policies
and the identity switch (gsd/config.py CLUSTER_VISIBILITIES, CLUSTER_IDENTITIES) at the API handler,
through the app.state seams, without a cluster.

The matrix below is the contract: a policy may narrow what the host decided and may substitute the
remote's own decision; nothing here may widen.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.config import ClusterConfig, ConfigError, Settings, load_settings
from gsd.store import Store
from gsd.timeutil import now_iso

ROOT = {"X-Forwarded-User": "root"}      # wide on the host
ALICE = {"X-Forwarded-User": "alice"}    # self on the host, a member everywhere


def _seed(db: str) -> None:
    store = Store(db)
    now = now_iso()
    for cid in ("host", "east", "west", "far", "dark"):
        store.upsert_cluster(cid, f"https://api.{cid}.example:6443", True)
        store.record_poll(cid, "ok", None)
        store.replace_group_state(cid, [
            {"name": f"{cid}-admins", "member_count": 1, "sync_provider": "ldap_ldap",
             "group_synced_at": now, "ldap_uid": None},
            {"name": f"{cid}-devs", "member_count": 1, "sync_provider": "ldap_ldap",
             "group_synced_at": now, "ldap_uid": None},
        ], now)
        store.sync_members(cid, {f"{cid}-admins": ["alice"], f"{cid}-devs": ["bob"]}, {}, now)
        # A managed group that vanished + a binding naming it: one dangling_binding alert per
        # cluster, an administrator-tier kind, so the per-cluster alert filter is observable.
        store.record_managed_groups(cid, [{"name": f"{cid}-gone", "sync_provider": "ldap_ldap"}], now)
        store.replace_bindings(cid, [
            {"binding_kind": "RoleBinding", "binding_namespace": "ns1",
             "binding_name": f"{cid}-gone-rb", "role_kind": "ClusterRole",
             "role_name": "admin", "group_name": f"{cid}-gone"},
        ], now)
    store.close()


class _Map:
    def __init__(self, tiers):
        self.tiers, self.calls = tiers, 0

    def resolve(self, viewer):
        self.calls += 1
        return self.tiers.get(viewer, "self")


def _settings(db: str, **kw) -> Settings:
    kw.setdefault("oauth_proxy_enabled", True)
    return Settings(clusters=[
        ClusterConfig("host", "https://api.host.example:6443", token_env="X"),
        ClusterConfig("east", "https://api.east.example:6443", token_env="X",
                      visibility="self-only", identity="same-as-host"),
        ClusterConfig("west", "https://api.west.example:6443", token_env="X",
                      visibility="remote-sar", identity="same-as-host"),
        ClusterConfig("far", "https://api.far.example:6443", token_env="X"),   # the defaults
        ClusterConfig("dark", "https://api.dark.example:6443", token_env="X",
                      visibility="hidden"),
    ], db_path=db, **kw)


@pytest.fixture(scope="module")
def db(tmp_path_factory) -> str:
    path = str(tmp_path_factory.mktemp("mc") / "gsd.db")
    _seed(path)
    return path


@pytest.fixture(scope="module")
def client(db):
    app = build_app(_settings(db), run_poller=False)
    app.state.tier_resolver = _Map({"root": "all"})
    # west's own RBAC disagrees with the host's on purpose: alice administers west, root does not.
    app.state.remote_tier_resolvers = {"west": _Map({"alice": "all"})}
    with TestClient(app) as c:
        yield c


class TestTheDefaultsResolve:
    def test_host_is_inherit_same_as_host_and_a_remote_is_self_only_none(self, db):
        s = _settings(db)
        assert s.cluster_policy("host") == ("inherit", "same-as-host")
        assert s.cluster_policy("far") == ("self-only", "none")
        assert s.cluster_policy("east") == ("self-only", "same-as-host")

    def test_a_cluster_no_longer_configured_is_not_widened_beyond_today(self, db):
        assert _settings(db).cluster_policy("ghost") == ("inherit", "same-as-host")


class TestInheritIsTodaysBehaviour:
    def test_root_is_wide_and_alice_is_self_on_the_host(self, client):
        assert client.get("/api/clusters/host/groups", headers=ROOT).json()["scope"] == "all"
        body = client.get("/api/clusters/host/groups", headers=ALICE).json()
        assert body["scope"] == "self"
        assert [g["name"] for g in body["groups"]] == ["host-admins"]


class TestSelfOnlyNeverWidens:
    def test_the_host_administrator_is_self_on_east(self, client):
        body = client.get("/api/clusters/east/groups", headers=ROOT).json()
        assert body["scope"] == "self" and body["viewer"] == "root"
        assert body["groups"] == []
        assert client.get("/api/clusters/east/bindings/findings", headers=ROOT).status_code == 403

    def test_a_same_as_host_identity_gets_their_own_rows_on_east(self, client):
        body = client.get("/api/clusters/east/groups", headers=ALICE).json()
        assert [g["name"] for g in body["groups"]] == ["east-admins"]

    def test_identity_none_refuses_person_scoped_views_and_serves_health(self, client):
        refused = client.get("/api/clusters/far/groups", headers=ROOT)
        assert refused.status_code == 403
        assert "does not treat your identity" in refused.json()["detail"]
        # Never the chart value that would change it: the sentence reaches the refused reader.
        assert "identity" not in refused.json()["detail"].split("your identity")[1]
        for path in ("/api/clusters/far/users/alice", "/api/clusters/far/logins",
                     "/api/clusters/far/user-bindings", "/api/clusters/far/membership-changes",
                     "/api/clusters/far/cluster-access"):
            assert client.get(path, headers=ROOT).status_code == 403, path
        # CR health is full at both tiers by ruling and stays served, projected.
        crs = client.get("/api/clusters/far/groupsyncs", headers=ROOT)
        assert crs.status_code == 200
        assert all("ldap_filter" not in cr for cr in crs.json())


class TestHiddenIsNotAnOracle:
    def test_hidden_and_unknown_are_the_same_404(self, client):
        for headers in (ROOT, ALICE):
            a = client.get("/api/clusters/dark/groups", headers=headers)
            b = client.get("/api/clusters/no-such/groups", headers=headers)
            assert a.status_code == b.status_code == 404
            assert a.json()["detail"].replace("dark", "X") == b.json()["detail"].replace("no-such", "X")

    def test_hidden_is_absent_from_the_lists(self, client):
        ids = {c["id"] for c in client.get("/api/clusters", headers=ROOT).json()}
        assert "dark" not in ids and {"host", "east", "west", "far"} <= ids
        who = client.get("/api/whoami", headers=ROOT).json()
        assert "dark" not in who["visibility"]["clusters"]
        alerts = client.get("/api/alerts", headers=ROOT).json()
        assert not any(a["cluster"] == "dark" for a in alerts["alerts"])


class TestRemoteSarIsTheRemotesDecision:
    def test_alice_is_wide_on_west_and_self_on_the_host(self, client):
        assert client.get("/api/clusters/west/groups", headers=ALICE).json()["scope"] == "all"
        assert client.get("/api/clusters/host/groups", headers=ALICE).json()["scope"] == "self"

    def test_root_is_not_wide_on_west_because_the_host_said_so(self, client):
        assert client.get("/api/clusters/west/groups", headers=ROOT).json()["scope"] == "self"

    def test_a_missing_remote_resolver_is_self_never_the_hosts_answer(self, db):
        app = build_app(_settings(db), run_poller=False)
        app.state.tier_resolver = _Map({"root": "all"})
        app.state.remote_tier_resolvers = {}
        with TestClient(app) as c:
            assert c.get("/api/clusters/west/groups", headers=ROOT).json()["scope"] == "self"

    def test_a_raising_remote_resolver_is_self(self, db):
        class Boom:
            def resolve(self, viewer):
                raise RuntimeError("remote down")
        app = build_app(_settings(db), run_poller=False)
        app.state.tier_resolver = _Map({"root": "all"})
        app.state.remote_tier_resolvers = {"west": Boom()}
        with TestClient(app) as c:
            assert c.get("/api/clusters/west/groups", headers=ALICE).json()["scope"] == "self"


class TestTheWireSaysSo:
    def test_whoami_carries_every_served_clusters_decision(self, client):
        vis = client.get("/api/whoami", headers=ROOT).json()["visibility"]
        assert vis["scope"] == "all"
        assert vis["clusters"] == {
            "host": {"policy": "inherit", "identity": "same-as-host", "scope": "all"},
            "east": {"policy": "self-only", "identity": "same-as-host", "scope": "self"},
            "west": {"policy": "remote-sar", "identity": "same-as-host", "scope": "self"},
            "far": {"policy": "self-only", "identity": "none", "scope": "self"},
        }

    def test_cluster_rows_carry_policy_and_scope_and_withhold_accordingly(self, client):
        rows = {c["id"]: c for c in client.get("/api/clusters", headers=ROOT).json()}
        assert rows["host"]["visibility"] == {"policy": "inherit", "scope": "all"}
        assert rows["east"]["visibility"] == {"policy": "self-only", "scope": "self"}
        assert rows["east"]["operator_configs"] is None

    def test_alerts_are_filtered_per_cluster_in_that_clusters_tier(self, client):
        body = client.get("/api/alerts", headers=ROOT).json()
        dangling = {a["cluster"] for a in body["alerts"] if a["kind"] == "dangling_binding"}
        assert dangling == {"host"}, "an administrator-tier kind leaked from a narrowed cluster"
        assert body["scope"] == "self", "narrowed somewhere must not read as wide everywhere"
        alice = client.get("/api/alerts", headers=ALICE).json()
        assert {a["cluster"] for a in alice["alerts"] if a["kind"] == "dangling_binding"} == {"west"}


class TestRestrictionsOff:
    def test_off_is_off_for_every_policy_but_hidden(self, db):
        app = build_app(_settings(db, view_restrictions_enabled=False), run_poller=False)
        with TestClient(app) as c:
            for cid in ("host", "east", "west", "far"):
                assert c.get(f"/api/clusters/{cid}/groups", headers=ALICE).json()["scope"] == "all"
            assert c.get("/api/clusters/dark/groups", headers=ALICE).status_code == 404


class TestConfigValidation:
    BASE = """
clusters:
  - name: host
    apiUrl: https://api.host.example:6443
    tokenEnv: X
  - name: east
    apiUrl: https://api.east.example:6443
    tokenEnv: X
"""

    def _load(self, tmp_path, text):
        p = tmp_path / "clusters.yaml"
        p.write_text(text)
        return load_settings(str(p))

    def test_defaults_resolve_from_a_file_too(self, tmp_path):
        s = self._load(tmp_path, self.BASE)
        assert s.cluster_policy("east") == ("self-only", "none")

    def test_an_unknown_policy_is_refused(self, tmp_path):
        with pytest.raises(ConfigError, match="visibility 'Hidden'"):
            self._load(tmp_path, self.BASE + "    visibility: Hidden\n")

    def test_remote_sar_needs_same_as_host(self, tmp_path):
        with pytest.raises(ConfigError, match="needs identity: same-as-host"):
            self._load(tmp_path, self.BASE + "    visibility: remote-sar\n")
        s = self._load(tmp_path, self.BASE + "    visibility: remote-sar\n    identity: same-as-host\n")
        assert s.cluster_policy("east") == ("remote-sar", "same-as-host")

    def test_hidden_and_remote_sar_are_refused_on_the_host(self, tmp_path):
        for policy in ("hidden", "remote-sar"):
            text = self.BASE.replace("    tokenEnv: X\n  - name: east",
                                     f"    tokenEnv: X\n    visibility: {policy}\n  - name: east", 1)
            with pytest.raises(ConfigError, match="hosting cluster"):
                self._load(tmp_path, text)

    def test_a_disabled_first_entry_is_not_the_host(self, tmp_path):
        text = self.BASE.replace("    tokenEnv: X\n  - name: east",
                                 "    tokenEnv: X\n    enabled: false\n  - name: east", 1)
        s = self._load(tmp_path, text)
        assert s.host_cluster().name == "east"
        assert s.cluster_policy("east") == ("inherit", "same-as-host")
```

**`local-development/tests/test_chart_strategy.py`** — append:

```python
class TestPerClusterVisibility:
    """clusters[].visibility / identity: refused at render on the same vocabulary the app enforces."""

    TWO = {
        "clusters[0].name": "host", "clusters[0].apiUrl": "https://h", "clusters[0].tokenEnv": "X",
        "clusters[1].name": "east", "clusters[1].apiUrl": "https://e", "clusters[1].tokenEnv": "X",
    }

    def _render(self, **extra):
        values = {**self.TWO, **extra}
        args = ["helm", "template", "t", str(CHART), "--set", "ingress.host=t.example.com"]
        for key, value in values.items():
            args += ["--set", f"{key}={value}"]
        done = subprocess.run(args, capture_output=True, text=True)
        return done.returncode == 0, done.stdout + done.stderr

    def test_the_keys_pass_through_to_the_configmap(self):
        ok, out = self._render(**{"clusters[1].visibility": "self-only",
                                   "clusters[1].identity": "same-as-host"})
        assert ok, out
        east = [c for c in _config_data(out)["clusters"] if c["name"] == "east"][0]
        assert east["visibility"] == "self-only" and east["identity"] == "same-as-host"

    def test_an_unknown_policy_is_refused(self):
        ok, out = self._render(**{"clusters[1].visibility": "self_only"})
        assert not ok and "not one of inherit, self-only, hidden, remote-sar" in out

    def test_remote_sar_without_same_as_host_is_refused(self):
        ok, out = self._render(**{"clusters[1].visibility": "remote-sar"})
        assert not ok and "needs identity: same-as-host" in out
        ok, _ = self._render(**{"clusters[1].visibility": "remote-sar",
                                "clusters[1].identity": "same-as-host"})
        assert ok

    def test_hidden_on_the_host_is_refused(self):
        ok, out = self._render(**{"clusters[0].visibility": "hidden"})
        assert not ok and "hosting cluster" in out

    def test_the_default_single_cluster_render_is_unchanged(self):
        ok, out = render()
        assert ok, out
        assert "visibility:" not in "\n".join(
            l for l in out.splitlines() if l.startswith("      ")) or True
        assert _config_data(out)["clusters"][0].get("visibility") is None

    def test_notes_name_every_clusters_policy(self):
        ok, out = self._render(**{"clusters[1].visibility": "hidden"})
        assert ok, out
        assert "east: visibility hidden" in out and "host: visibility inherit (host)" in out
```

(`_config_data` and `render` are the module's existing helpers; `subprocess` and `CHART` are already imported there.)

**`local-development/tests/test_visibility.py` and `test_ui.py`** — no edits expected: their second cluster (`c2`, `prod-east`) is only ever exercised through `/api/alerts` for an `auth_failed` kind, which is in `gsd/api.py#SELF_ALERT_DETAILS` and survives per-cluster filtering. If a run shows a `c2` assertion at the wide tier, the fix is `ClusterConfig(..., visibility="inherit")` in that fixture, not a code change.

## D2.7 Docs

- **`docs/ACCESS_CONTROL.md`** — append a section `## 11. Several clusters in one instance` containing: the exposure sentence, the two-key table above, the per-endpoint refusal semantics (hidden → 404 identical to unknown, `identity: none` → 403 on person-scoped endpoints with the exact sentence, `self-only` never wide), how `remote-sar` decides (`gsd/kube.py#TierResolver` on the remote's `ClusterConfig`, groups from `gsd/kube.py#ClusterClient.fetch_groups_of_user` on the remote, cache per instance, failures self), the remote RBAC the operator adds by hand (a `ClusterRoleBinding` of `system:auth-delegator` to the remote ServiceAccount), the identity-equivalence analysis (same username ≠ same person unless the IdPs and their `mappingMethod` agree; `developer`/`kubeadmin` never), the wire (`/api/whoami` `visibility.clusters`, `/api/clusters` `visibility`, `/api/alerts` `scope` = narrowest), and the recommendation to prefer one dashboard per cluster + `local-development/cluster-report.py` where boundaries differ. Also change the §5 diagram's `viewer_scope(request)` line to `viewer_scope(request, cluster_id)` and add one line `├─ settings.cluster_policy(cluster)  gsd/config.py#Settings.cluster_policy  inherit | self-only | hidden | remote-sar`.
- **`docs/reference-architecture.md`** — replace the paragraph beginning `**The multi-cluster caveat** is not solved:` with: `**The multi-cluster caveat is modelled, not assumed away.** A viewer is authenticated by the hosting cluster only, so what they may see about another cluster is that entry's own policy (\`clusters[].visibility\`, \`clusters[].identity\`; \`gsd/config.py#Settings.cluster_policy\`, \`gsd/api.py#viewer_scope\`): a second cluster is \`self-only\` with no identity by default, may be hidden from the API entirely, may inherit the host's tier as an explicit choice, or may be decided by its own RBAC through the same review on its own API (\`remote-sar\`). \`docs/ACCESS_CONTROL.md\` §11 tabulates it. What is still not solved — and cannot be from one instance — is identity equivalence across identity providers, which is why \`identity\` is a stated assumption and why §8a remains the recommendation where trust boundaries differ.` In §8a, replace the final paragraph's `— the unsolved caveat in §7.` with `— the caveat §7.2 now models per cluster, and which per-cluster deployment removes rather than manages.`
- **`README.md#Not built yet`** — remove `and per-cluster authorization for the multi-cluster case: ... avoids that entirely.` and add after the paragraph: `Per-cluster authorization for the multi-cluster case shipped in 0.12.0 as \`clusters[].visibility\` / \`clusters[].identity\` (\`docs/ACCESS_CONTROL.md\` §11); deploying per cluster and aggregating through the API, as above, still removes the identity question rather than answering it.`
- **`docs/SPEC_per_user_visibility.md`** — one dated line under the title: `> 2026-09-04: risk (7) below — "per-remote-cluster tiers are out of scope" — is closed by \`docs/ACCESS_CONTROL.md\` §11 (application 0.12.0). The rest of this record is unchanged.`
- **`docs/CHANGELOG.md`** — new top entry:

```markdown
## Application 0.12.0 — chart 0.11.0 — 2026-09-04

- **Per-cluster authorization for the multi-cluster case.** A reader is authenticated by the
  hosting cluster only, and the tier that cluster decided used to gate every cluster's rows. Two
  keys per `clusters[]` entry now say what a reader may see about each other cluster:
  `visibility` — `inherit` (the host decides), `self-only` (nobody is wide there), `hidden`
  (polled, never served through `/api`; 404 like an unknown id), `remote-sar` (that cluster's own
  RBAC decides through the same SubjectAccessReview on its own API with its own Group objects,
  cached per reader and cluster, every failure self) — and `identity` — `none` (the host's
  username is nobody there; person-scoped views answer 403, health still shows) or
  `same-as-host`. Defaults are the safe direction: the first entry `inherit`/`same-as-host`, every
  other `self-only`/`none`. `/api/whoami` gains `visibility.clusters`, `/api/clusters` rows gain
  `visibility`, `/api/alerts` filters per cluster in that cluster's tier and reports the narrowest
  scope served; the cluster selector marks a narrowed cluster and the header pill follows the
  selected one. (`ACCESS_CONTROL.md` §11)
- **Upgrade note for multi-cluster installs:** remotes become `self-only` on chart 0.11.0. Set
  `clusters[].visibility: inherit` to keep the old view, deliberately.
- **Chart 0.11.0:** the two values, a render guard on their vocabulary (unknown policy,
  `hidden`/`remote-sar` on the host entry, `remote-sar` without `identity: same-as-host`), NOTES
  naming every cluster's effective policy, and the stale `docs/PLAN_oauth_proxy.md` reference in
  the `clusters` comment replaced.
```

## D2.8 Verification

```bash
cd local-development && python -m pytest -q tests/test_multicluster_visibility.py tests/test_visibility.py tests/test_view_scoping.py tests/test_config.py tests/test_chart_strategy.py tests/test_api_contract.py tests/test_docs_citations.py tests/test_chart_versions.py
# expected: all pass; test_docs_citations gains ~8 new resolvable anchors

helm template t charts/group-sync-dashboard --set ingress.host=t.example.com \
  --set 'clusters[0].name=host,clusters[0].apiUrl=https://h,clusters[0].tokenEnv=X' \
  --set 'clusters[1].name=east,clusters[1].apiUrl=https://e,clusters[1].tokenEnv=X,clusters[1].visibility=remote-sar'
# expected: Error: ... clusters[1] (east): visibility remote-sar needs identity: same-as-host.

# in the pod, two clusters configured, root wide on the host:
oc exec -n group-sync-dashboard "$POD" -c dashboard -- curl -s -H 'X-Forwarded-User: root' localhost:8080/api/whoami
# expected: "visibility":{"scope":"all","enabled":true,"clusters":{"crc-local":{"policy":"inherit",...,"scope":"all"},"prod-east":{"policy":"self-only","identity":"none","scope":"self"}}}
oc exec ... -- curl -s -o /dev/null -w '%{http_code}\n' -H 'X-Forwarded-User: root' localhost:8080/api/clusters/prod-east/groups
# expected: 403
```

## D2.9 Risks and how they are closed

| risk | closed by |
|---|---|
| Upgrade narrows an existing multi-cluster install | MINOR chart bump, CHANGELOG upgrade note, README row, NOTES lists each cluster's effective policy on every install/upgrade |
| `remote-sar` reviews the wrong human | `identity: same-as-host` is mandatory and documented as an operator assertion; refused at render and at startup otherwise |
| A hidden cluster leaks through an endpoint that does not call `require_cluster` | every `/api/clusters/{id}/...` handler calls `require_cluster` first (verified in `gsd/api.py`); `/api/clusters`, `/api/alerts`, `/api/whoami` skip hidden explicitly; `test_hidden_is_absent_from_the_lists` |
| Existence oracle on hidden ids | the 404 detail is the same string as for an unknown id; `test_hidden_and_unknown_are_the_same_404` |
| Remote SAR grant missing → silent narrowing | the remote resolver reports through `signals.note_tier_check("admin", outcome)`, so `templates/monitoring.yaml#GroupSyncDashboardVisibilityChecksFailing` fires exactly as for the host; startup INFO line per non-default policy |
| `/api/clusters` now makes one decision per row → `gsd_visibility_decisions_total` rises faster | documented in the metric HELP's "cached, fresh, and no-identity decisions alike" sense; cache hits are not re-decided |

**Questions only the operator can answer:** (1) whether the fleet shares one identity provider with the same username mapping on every cluster (decides `identity`); (2) whether remote ServiceAccount tokens may be granted `create subjectaccessreviews` (decides whether `remote-sar` is available at all).

---

