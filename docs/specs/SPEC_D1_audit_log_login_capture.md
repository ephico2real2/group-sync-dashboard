# SPEC D1 — Login capture from the oauth-server audit log

| | |
|---|---|
| Programme | Feature programme 2026-09 — index and version ladder in `docs/specs/README.md` |
| Batch | D — architecture |
| Release | R5 — Sessions and login source |
| Version on release | app 0.17.0, chart 0.18.0 |
| Issue | [#66](https://github.com/ephico2real2/group-sync-dashboard/issues/66) |
| Status | specified |
| Source | design agent output `a1c16fd988d22c70e`; three messages; the first ended mid-token (`"nodes/` | `proxy"]`) and is joined to the second with nothing between; the third is the agent's confirmation reply summarising D2 and is not design text, so it is omitted |

## How to read this spec

Everything under "Batch preamble", "Design" and "Batch closing sections" is the design agent's text,
**verbatim** — it was sliced from the agent's output by heading and re-concatenated to the byte before
this file was written, and nothing in it was rewritten by hand. Implementation applies the code in
"Design" exactly as written, one file at a time; a deviation found necessary during implementation is
written back into this file in the same pull request, with the reason, under "Orchestrator's notes".

## Orchestrator's notes

- Second feature of R5: app 0.17.0, chart 0.18.0; schema migration 10 (the body says 8). The operator chose cluster-wide `get nodes/proxy` + `list nodes` as the rendered default when the module is on; `nodeNames` stays the optional narrowing. The body's audit-log fixtures are documented-shape and MUST be replaced by lines captured on CRC during implementation, as the design itself says.
- Citation corrected (twice): the design cited the login-capture design doc with the anchor "The five deliberate test logins appear exactly as made", but that sentence is line-wrapped in the source after "The five"; the anchor now cites the part that is on one line.
- Citation corrected: the design cited the login-capture design doc with the anchor "needs nodes/proxy", but the source has bold and code marks between those two words; the anchor now cites `nodes/proxy`.

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

# FEATURE D1 — Login capture from the oauth-server audit log

## D1.1 Goal, the switch, and its default

**Goal.** Record the same `login_event` rows — who, when, provider where known, outcome — from `/var/log/oauth-server/audit.log` on the control-plane nodes, so an operator can retire the `authLogLevel` Jobs (no Debug, no OAuth roll, no login outage) and gain the history the pod log never had, while the store, the Logins tab, retention and the metrics stay as they are.

**The switch.** `loginCapture.source: pod-log | audit-log`, **default `pod-log`**. Rationale (in the values comment): `audit-log` needs a cluster-wide grant — `get nodes/proxy` reads anything the kubelet serves over GET (every container's log on that node via `/containerLogs`, the kube-apiserver audit log, the journal) — and a `list nodes` grant unless node names are pinned; that is categorically wider than the namespaced `pods/log` Role and it is a standing capability. A grant of that width is opted into, never defaulted. `both` is deliberately not offered in this PR: it would keep Debug on, which is the thing this source lets an operator retire; the `audit_id` link column below is what a later `both` mode would use, so nothing here forecloses it.

**How the two switches interact (modelled, per house rule):**

| `loginCapture.source` | `authLogLevel.manage` | `authLogLevel.enabled` | render |
|---|---|---|---|
| `pod-log` | any | any | as today |
| `audit-log` | `false` | `false` | renders: no Jobs, the audit ClusterRole, no namespaced Role |
| `audit-log` | `true` | `false` | renders: the Job converges the cluster to `Normal` (this is the retirement path: step 1 of the README's two-step) |
| `audit-log` | any | `true` | **refused** with a message naming the contradiction and the order to retire in |

Refuse rather than derive `enabled` off, because deriving would roll the OAuth server as a side effect of changing a *read* setting — a login outage on a single-replica cluster caused by a value that never mentions the OAuth server. Derive rather than refuse for the grants: `source` decides which RBAC object renders, so the two never coexist.

**Which source is authoritative.** With `source: audit-log`, the audit log is the only source read and the authoritative who/when/allow-deny record; pod-log rows already stored are kept and, where an audit event corresponds to one (same user, same success class, within 2 s — measured 16 ms apart in `docs/DESIGN_login_capture.md#deliberate test logins appear exactly as made`), the audit event is **linked** to the existing row (`audit_id` set) rather than inserted beside it, so the row keeps its LDAP cause and the record does not double.

## D1.2 The reader — `local-development/gsd/kube.py`

Insert after the line `POD_API_TMPL = "/api/v1/namespaces/%s/pods"`:

```python
# The nodes and the kubelet's file server behind them, for the oauth-server AUDIT log
# (docs/DESIGN_login_capture.md, "The oauth-server AUDIT LOG"). `oc adm node-logs <node>
# --path=oauth-server/audit.log` is GET /api/v1/nodes/<node>/proxy/logs/oauth-server/audit.log —
# the API server authorises it as `get nodes/proxy` and forwards it to the kubelet, which serves
# /var/log through Go's http.FileServer (kubelet.go: `http.StripPrefix("/logs/",
# http.FileServer(http.Dir(nodeLogDir)))`). A directory path answers an HTML listing; a file
# path answers the bytes, and honours Range so a byte cursor can resume server-side.
NODE_API = "/api/v1/nodes"
NODE_LOG_PROXY_TMPL = "/api/v1/nodes/%s/proxy/logs/%s"

# One audit-file read's byte budget per cycle. The same figure as the pod-log cap and for the
# same reason — a bounded transfer on the poll thread — and it is what bounds a backfill:
# ten rotated files of 100 MB drain at this rate over cycles, not in one.
AUDIT_READ_MAX_BYTES = 8 * 1024 * 1024
```

Insert after `_log_read_refused` (i.e. immediately before `    def fetch_bindings(self) -> list[BindingView]:`):

```python
    def fetch_nodes(self, label_selector: str) -> list[str] | None:
        """Names of the nodes matching a label selector, or None when we may not list them.

        For the audit-log source: the oauth-server writes its audit log to a hostPath on whichever
        control-plane node runs it, so the nodes to read are the control-plane nodes — by
        selector, not by asking the oauth pods where they are, because a drained node's file still
        holds history and a pod list would never name it. `loginCapture.auditLog.nodeNames` is the
        no-list alternative: with names pinned this is never called.

        None means FORBIDDEN, distinct from [] (permitted, no node matched): the grant is optional
        and an image upgraded without re-applying RBAC must degrade, not fail the poll.
        """
        with self._client() as client:
            try:
                items = self._list_all_with(client, NODE_API, {"labelSelector": label_selector})
            except ClusterError as exc:
                if exc.outcome == FORBIDDEN and NODE_API in exc.message:
                    log.debug("%s: forbidden listing nodes; returning no nodes", self.cluster.name)
                    return None
                raise
        return sorted(
            name for obj in items if (name := (obj.get("metadata") or {}).get("name"))
        )

    def _list_all_with(self, client: httpx.Client, path: str, extra: dict[str, Any]) -> list[dict]:
        """_list_all with extra query parameters carried through every page."""
        items: list[dict] = []
        params: dict[str, Any] = {"limit": PAGE_SIZE, **extra}
        while True:
            payload = self._get(client, path, params)
            if "items" not in payload:
                raise ClusterError(
                    UNREACHABLE,
                    f"{path} returned HTTP 200 without an 'items' field "
                    f"(kind={payload.get('kind')!r}) — refusing to treat this as an empty "
                    f"collection",
                )
            page = payload.get("items")
            if page is not None and not isinstance(page, list):
                raise ClusterError(
                    UNREACHABLE, f"{path} returned 'items' of type {type(page).__name__}"
                )
            items.extend(page or [])
            token = (payload.get("metadata") or {}).get("continue")
            if not token:
                return items
            params = {"limit": PAGE_SIZE, "continue": token, **extra}

    def list_node_log_files(self, node: str, directory: str) -> list[str] | None:
        """File names under /var/log/<directory>/ on one node, or None when it cannot be read.

        The kubelet's file server answers a directory with an HTML listing — one `<a href="...">`
        per entry — which is what `oc adm node-logs --path=oauth-server/` turns into text. Names
        only: no size, no mtime, which is why the audit cursor is by name and byte offset.

        None for 403 (WARNING: permanent, and silence here looks like "no history") and 404 (the
        directory does not exist on this node — it never ran the oauth-server, or the cluster's
        audit profile is None, which switches the oauth-server's audit log off entirely; DEBUG).
        """
        path = NODE_LOG_PROXY_TMPL % (node, directory.rstrip("/") + "/")
        try:
            with self._client() as client:
                response = client.get(path)
        except httpx.HTTPError as exc:
            log.info("%s: could not list %s on %s (%s: %s)",
                     self.cluster.name, directory, node, type(exc).__name__, exc)
            return None
        if response.status_code == 403:
            log.warning(
                "%s: FORBIDDEN reading node logs on %s — audit-log capture will record nothing "
                "until this is fixed. The chart grants it with loginCapture.source=audit-log "
                "(a ClusterRole on nodes/proxy).", self.cluster.name, node,
            )
            return None
        if response.status_code == 404:
            log.debug("%s: no %s directory on %s", self.cluster.name, directory, node)
            return None
        if response.status_code == 401:
            raise ClusterError(AUTH_FAILED, f"401 Unauthorized listing node logs on {node}")
        if response.status_code >= 400:
            log.warning("%s: unexpected HTTP %d listing %s on %s: %s", self.cluster.name,
                        response.status_code, directory, node, response.text[:200])
            return None
        names = []
        for href in re.findall(r'href="([^"?#]+)"', response.text):
            name = unquote(href).rstrip("/").rsplit("/", 1)[-1]
            if name and name not in names:
                names.append(name)
        return names

    def fetch_node_log_file(
        self, node: str, path: str, offset: int = 0, max_bytes: int = AUDIT_READ_MAX_BYTES,
    ) -> NodeLogRead | None:
        """Up to `max_bytes` of /var/log/<path> on one node from byte `offset`, or None if unreadable.

        RESUMABLE BY BYTE OFFSET, and correct whether or not the server honours it. A `Range`
        header asks the file server to start at the offset; a 206 means it did. A 200 means
        something in the path ignored the header, and the first `offset` bytes are discarded
        from the stream instead — same result, more bytes on the wire, never a wrong cursor.

        ROTATION IS DETECTED HERE, not guessed at: a 416 (Range past the end), or a stream that
        ends before `offset` bytes have been skipped, means the file is now SHORTER than the
        cursor — audit.log was rotated to audit-<stamp>.log and a new one started. The caller
        moves the cursor to the rotated file; nothing is re-read and nothing is skipped.

        Bounded in bytes and in wall-clock (LOG_READ_BUDGET_SECONDS), like fetch_pod_log, and a
        truncated read keeps the OLDEST bytes for the same reason it does there: the cursor
        advances only through bytes actually returned.
        """
        url = NODE_LOG_PROXY_TMPL % (node, path)
        headers = {"Range": f"bytes={offset}-"} if offset > 0 else {}
        chunks: list[bytes] = []
        size = 0
        skip = 0
        truncated = False
        started = time.monotonic()
        try:
            with self._client() as client:
                with client.stream("GET", url, headers=headers) as response:
                    if response.status_code == 416:
                        return NodeLogRead(data=b"", offset=offset, truncated=False, rotated=True)
                    if response.status_code >= 400:
                        response.read()
                        return self._node_log_refused(response, node, path)
                    if response.status_code == 200 and offset > 0:
                        skip = offset
                        length = response.headers.get("content-length")
                        if length is not None and int(length) < offset:
                            return NodeLogRead(data=b"", offset=offset, truncated=False,
                                               rotated=True)
                    for chunk in response.iter_bytes(chunk_size=64 * 1024):
                        if time.monotonic() - started > LOG_READ_BUDGET_SECONDS:
                            truncated = True
                            break
                        if skip:
                            take = min(skip, len(chunk))
                            skip -= take
                            chunk = chunk[take:]
                            if not chunk:
                                continue
                        room = max_bytes - size
                        if len(chunk) >= room:
                            chunks.append(chunk[:room])
                            size = max_bytes
                            truncated = True
                            break
                        chunks.append(chunk)
                        size += len(chunk)
        except httpx.HTTPError as exc:
            log.info("%s: could not read %s on %s (%s: %s)",
                     self.cluster.name, path, node, type(exc).__name__, exc)
            return None
        if skip:
            # The whole body was shorter than the cursor: rotated.
            return NodeLogRead(data=b"", offset=offset, truncated=False, rotated=True)
        return NodeLogRead(data=b"".join(chunks), offset=offset, truncated=truncated,
                           rotated=False)

    def _node_log_refused(self, response: httpx.Response, node: str, path: str) -> None:
        if response.status_code == 404:
            log.debug("%s: %s is gone on %s (rotated away between listing and reading)",
                      self.cluster.name, path, node)
            return None
        if response.status_code == 403:
            log.warning(
                "%s: FORBIDDEN reading %s on %s — audit-log capture will record nothing until "
                "this is fixed (loginCapture.source=audit-log renders the nodes/proxy grant)",
                self.cluster.name, path, node,
            )
            return None
        if response.status_code == 401:
            raise ClusterError(AUTH_FAILED, f"401 Unauthorized reading {path} on {node}")
        log.warning("%s: unexpected HTTP %d reading %s on %s: %s", self.cluster.name,
                    response.status_code, path, node, response.text[:200])
        return None
```

And the dataclass, inserted after `class OperatorConfigView` (any position among the views):

```python
@dataclass
class NodeLogRead:
    """One bounded read of a file under /var/log on a node — see ClusterClient.fetch_node_log_file."""

    data: bytes
    offset: int
    """Where `data` starts, as the caller asked; the cursor advances by the bytes it consumes."""
    truncated: bool
    """More remains after `data` (byte cap or wall-clock budget); read again next cycle."""
    rotated: bool
    """The file is now shorter than `offset`: it was rotated away and a fresh one started."""
```

(`re`, `unquote`, `time`, `httpx`, `Any` are already imported in `kube.py`.)

## D1.3 The vocabulary — `local-development/gsd/loginlog.py`

Insert after the `OUTCOME_FAILED` docstring block (after the line `cause would surface, which is a signal that the grammar has grown a case worth adding.` and its closing `"""`):

```python
OUTCOME_PROVIDER_ERROR = "provider_error"
"""The identity provider could not answer — the audit log's `decision: error`.

Only the AUDIT source produces it (gsd/auditlog.py): the oauth-server annotates a request `error`
when an identity provider failed rather than refused — a directory that would not bind, a
timeout — which is an operational action (fix the provider) and not a person's mistake. Distinct
from `failed` because folding it in would report a directory outage as a run of wrong passwords.
The pod log has no equivalent line at any verbosity, so this never arrives from that source.
"""
```

`gsd/api.py#LOGIN_OUTCOMES` derives from `OUTCOME_*`, so `/logins?outcome=provider_error` becomes queryable with no further edit; the `outcome` Query `description` in `list_logins` gains `, provider_error (the identity provider could not answer — audit-log source only)` before `and failed`.

## D1.4 The second front end — new file `local-development/gsd/auditlog.py`

```python
"""Read the oauth-server's AUDIT log and record who logged in — the second capture source.

WHAT THIS READS. Every OpenShift 4.11+ cluster writes the oauth-server's Kubernetes-audit-format
JSON to /var/log/oauth-server/audit.log on the control-plane node running it, one event per
request, at Metadata level, at every audit profile but `None` (cluster-authentication-operator's
`ObserveAudit`: audit-log-maxsize=100, audit-log-maxbackup=10). A login attempt is the event whose
annotations carry BOTH `authentication.openshift.io/username` and
`authentication.openshift.io/decision` — allow, deny or error (openshift/oauth-server
pkg/audit/annotation.go). No `spec.logLevel: Debug`, so no OAuth roll and no login outage; and
history as far back as the rotated files reach. See docs/DESIGN_login_capture.md.

WHAT IT CANNOT SAY. `deny` carries no cause: the LDAP result codes and AD sub-codes exist only in
the pod log at Debug, so `bad_password` / `password_expired` / `account_locked` never arrive from
here — a deny is `failed`, and says so in `detail`. The identity provider is named only on the
browser path (`/login/<idp>`), so a CLI login carries provider=None and the break-glass label
cannot fire for it. Both are stated on the Logins tab rather than hidden.

THE SHAPE OF ONE READ. Per node: list /var/log/oauth-server/, read each unread or partially read
file from its byte cursor (rotated files ascending by their stamp, then audit.log), parse whole
lines only, record, advance the cursor to the last newline consumed. A first sight is a BACKFILL
bounded by loginRetentionDays (a rotated file whose stamp is older than the cutoff is skipped
whole — everything in it is older still) and by AUDIT_READ_MAX_BYTES per node per cycle, so a
large history drains over cycles on the poll thread instead of blocking it.

DE-DUPLICATION IS BY auditID, and by correspondence with the pod log. Every event carries a
per-request auditID, stored on the row and unique per cluster, so a re-read is free. During a
migration from the pod-log source both records exist for the same login; an audit event matching
a pod-log row for the same user and success class within CORRESPONDENCE_SECONDS is LINKED to it
(audit_id set on the existing row) rather than inserted beside it — the row keeps its cause.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .config import ClusterConfig, Settings
from .kube import AUDIT_READ_MAX_BYTES, ClusterClient, ClusterError
from .loginlog import (
    ATTEMPT_WINDOW, OUTCOME_FAILED, OUTCOME_PROVIDER_ERROR, OUTCOME_SUCCESS,
)
from .storage import StorageBackend
from .timeutil import now_iso

log = logging.getLogger(__name__)

# The two annotation keys and three decisions, verbatim from openshift/oauth-server
# pkg/audit/annotation.go. The decision is the outcome; the username is the row's key.
USERNAME_ANNOTATION = "authentication.openshift.io/username"
DECISION_ANNOTATION = "authentication.openshift.io/decision"
DECISION_OUTCOME = {
    "allow": OUTCOME_SUCCESS,
    "deny": OUTCOME_FAILED,
    "error": OUTCOME_PROVIDER_ERROR,
}

AUDIT_DIR = "oauth-server"
AUDIT_FILE = "audit.log"
# lumberjack's backup name: audit-<RFC3339 with dashes for colons>.<ms>.log — documented listing
# `audit-2021-03-09T00-12-19.834.log`. The stamp is the moment the file was CLOSED, so every
# event in it is older than the stamp; that is what makes the retention skip below sound.
ROTATED = re.compile(r"^audit-(\d{4}-\d{2}-\d{2})T(\d{2})-(\d{2})-(\d{2})\.(\d+)\.log$")

# A pod-log row and an audit event for ONE login sit this close: measured 16 ms apart on the
# reference cluster (audit stageTimestamp 16:56:28.251 vs kubelet stamp 16:56:28.267). Two
# seconds absorbs a slow directory without reaching the next human retry.
CORRESPONDENCE_SECONDS = 2

# A cursor row that marks a rotated file as skipped by retention: nothing to read, ever.
SKIPPED = -1

# The stamp format every login_event row uses (gsd/logincapture.py#event_dict). Fixed once.
STAMP = "%Y-%m-%dT%H:%M:%S.%fZ"


@dataclass
class AuditLogin:
    """One login attempt as the audit log states it: no correlation, no inference."""

    audit_id: str
    user_name: str
    decision: str
    at: datetime
    request_path: str
    provider: str | None
    response_code: int | None


def parse_stamp(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def parse_audit_line(line: str) -> AuditLogin | None:
    """One JSON line to a login attempt, or None for everything that is not one.

    Not one: unparsable JSON, a non-Event, an event without BOTH annotations (the oauth-server
    audits every request; token refreshes, the well-known document and redirects carry neither),
    a decision outside the three, a stage other than ResponseComplete — the policy omits no
    stages, so RequestReceived is written too, before the annotations exist — and a stamp that
    cannot be read. `user.username` is NOT consulted: on a login request it is system:anonymous
    (the request is what authenticates), which is precisely why the annotation exists.

    The request path is kept WITHOUT its query string: /oauth/authorize carries client_id,
    redirect_uri and a PKCE challenge, none of them secret and none of them ours to store.
    """
    try:
        event = json.loads(line)
    except ValueError:
        return None
    if not isinstance(event, dict) or event.get("kind") != "Event":
        return None
    if event.get("stage") != "ResponseComplete":
        return None
    annotations = event.get("annotations") or {}
    user = annotations.get(USERNAME_ANNOTATION)
    decision = annotations.get(DECISION_ANNOTATION)
    if not user or decision not in DECISION_OUTCOME:
        return None
    at = parse_stamp(event.get("stageTimestamp")) or parse_stamp(event.get("requestReceivedTimestamp"))
    audit_id = event.get("auditID")
    if at is None or not audit_id:
        return None
    path = str(event.get("requestURI") or "").split("?", 1)[0]
    # The browser form is served per identity provider at /login/<idp> — the ONLY place the
    # audit log names a provider. The CLI's basic auth lands on /oauth/authorize and names none.
    provider = None
    if path.startswith("/login/") and len(path) > len("/login/"):
        provider = path[len("/login/"):].split("/", 1)[0] or None
    code = (event.get("responseStatus") or {}).get("code")
    return AuditLogin(
        audit_id=str(audit_id), user_name=str(user), decision=decision, at=at,
        request_path=path, provider=provider,
        response_code=int(code) if isinstance(code, int) else None,
    )


def audit_event_dict(login: AuditLogin, node: str, observed_at: str) -> dict:
    """The store row for an audit login — gsd/logincapture.py#event_dict's shape, plus the two
    columns this source owns. `pod_name` carries the NODE: it is "the unit of log this was read
    from" in the dedup key, and a node is that unit here."""
    return {
        "pod_name": node,
        "user_name": login.user_name,
        "outcome": DECISION_OUTCOME[login.decision],
        "at": login.at.strftime(STAMP),
        "provider": login.provider,
        "ldap_result_code": None,
        # Short and non-sensitive, and it carries the path on purpose: it is how a browser
        # login's two annotated requests (POST /login, then GET /oauth/authorize) are told
        # apart from two real attempts — see Store.record_audit_login_events.
        "detail": f"audit: {login.decision} via {login.request_path or '?'}"
                  + ("" if login.decision == "allow" else " (the audit log records no cause)"),
        "observed_at": observed_at,
        "source": "audit-log",
        "audit_id": login.audit_id,
    }


def rotated_at(name: str) -> datetime | None:
    """When a rotated file was closed, from its name; None for audit.log or an unexpected name."""
    m = ROTATED.match(name)
    if not m:
        return None
    day, hh, mm, ss, frac = m.groups()
    try:
        return datetime.fromisoformat(f"{day}T{hh}:{mm}:{ss}.{frac[:6]:0<6}+00:00")
    except ValueError:
        return None


def complete_lines(data: bytes) -> tuple[list[str], int]:
    """Whole lines from a byte read, and how many bytes they occupy.

    The last line of a live file is usually half-written; it is left for the next read by not
    counting it, so the cursor never lands mid-JSON. errors="replace" cannot corrupt a kept line:
    the only place a multi-byte character can be split is the end, and the end is not kept.
    """
    cut = data.rfind(b"\n")
    if cut < 0:
        return [], 0
    return data[:cut].decode("utf-8", errors="replace").split("\n"), cut + 1


def _coalesce(logins: list[AuditLogin]) -> list[AuditLogin]:
    """Collapse a browser login's paired events inside one batch: same user, same decision, within
    ATTEMPT_WINDOW, DIFFERENT path — keep the earliest. Two attempts on the same path stay two."""
    kept: list[AuditLogin] = []
    for login in sorted(logins, key=lambda l: (l.at, l.audit_id)):
        dup = any(
            k.user_name == login.user_name and k.decision == login.decision
            and k.request_path != login.request_path
            and timedelta(0) <= login.at - k.at <= ATTEMPT_WINDOW
            for k in kept
        )
        if not dup:
            kept.append(login)
    return kept


def capture_once(
    store: StorageBackend,
    cluster: ClusterConfig,
    settings: Settings,
    elector=None,
    timeout: float = 15.0,
    signals=None,
) -> int:
    """One audit-log capture pass over one cluster. Returns rows recorded. NEVER raises for a
    cluster problem — the same contract, and the same leadership recheck before every write, as
    gsd/logincapture.py#capture_once, which dispatches here on loginCapture.source=audit-log."""
    from .logincapture import _prune  # here, not at module level: logincapture imports this module

    client = ClusterClient(cluster, timeout=timeout)
    nodes: list[str] | None
    if settings.login_capture_audit_node_names:
        nodes = list(settings.login_capture_audit_node_names)
    else:
        try:
            nodes = client.fetch_nodes(settings.login_capture_audit_node_selector)
        except ClusterError as exc:
            log.warning("%s: audit-log capture could not list nodes: %s — group data is "
                        "unaffected", cluster.name, exc.message)
            return 0
        if nodes is None:
            log.warning("%s: audit-log capture is enabled but not permitted to list nodes, so no "
                        "logins will be recorded until the grant is applied (or pin "
                        "loginCapture.auditLog.nodeNames)", cluster.name)
            return 0
    if not nodes:
        log.info("%s: no node matched %r; audit-log capture has nothing to read",
                 cluster.name, settings.login_capture_audit_node_selector)
        return 0

    cutoff: datetime | None = None
    if settings.login_retention_days > 0:
        cutoff = datetime.now(UTC) - timedelta(days=settings.login_retention_days)

    recorded = 0
    read_ok = False
    for node in nodes:
        names = client.list_node_log_files(node, AUDIT_DIR)
        if names is None:
            continue
        files = [n for n in names if n == AUDIT_FILE or ROTATED.match(n)]
        if not files:
            # The directory exists and holds nothing audit-shaped: the audit profile is None,
            # or this node never ran the oauth-server. Not "nobody logged in".
            log.info("%s: %s has no audit files under /var/log/%s — is the cluster's audit "
                     "profile None? (apiserver.config.openshift.io/cluster spec.audit.profile)",
                     cluster.name, node, AUDIT_DIR)
            continue
        cursors = store.audit_cursors(cluster.name, node)
        order = sorted((n for n in files if n != AUDIT_FILE), key=lambda n: rotated_at(n) or datetime.min.replace(tzinfo=UTC))
        if AUDIT_FILE in files:
            order.append(AUDIT_FILE)
        budget = AUDIT_READ_MAX_BYTES
        first_sight = not cursors
        for name in order:
            if budget <= 0:
                log.debug("%s: %s: byte budget spent; %s waits for the next cycle",
                          cluster.name, node, name)
                break
            cur = cursors.get(name)
            if cur is not None and (cur["byte_offset"] == SKIPPED or cur["complete"]):
                continue
            offset = cur["byte_offset"] if cur is not None else 0
            if cur is None and name != AUDIT_FILE and cutoff is not None:
                closed = rotated_at(name)
                if closed is not None and closed < cutoff:
                    # Older than retention when it was closed, so everything inside it is too.
                    store.set_audit_cursor(cluster.name, node, name, SKIPPED, None, now_iso(),
                                           complete=True)
                    continue
            read = client.fetch_node_log_file(node, f"{AUDIT_DIR}/{name}", offset=offset,
                                              max_bytes=budget)
            if read is None:
                continue
            read_ok = True
            if read.rotated:
                if name == AUDIT_FILE:
                    # The bytes we had read now live under the newest rotated name. Hand the
                    # cursor over and start audit.log again; both are read next cycle.
                    fresh = [n for n in order if n != AUDIT_FILE and n not in cursors]
                    if fresh:
                        store.set_audit_cursor(cluster.name, node, fresh[-1], offset, None,
                                               now_iso(), complete=False)
                    store.set_audit_cursor(cluster.name, node, AUDIT_FILE, 0, None, now_iso(),
                                           complete=False)
                    log.info("%s: %s: audit.log rotated at byte %d; cursor handed to %s",
                             cluster.name, node, offset, fresh[-1] if fresh else "(unknown)")
                else:
                    log.warning("%s: %s: rotated file %s shrank below its cursor; re-reading "
                                "from 0 (auditID makes that free)", cluster.name, node, name)
                    store.set_audit_cursor(cluster.name, node, name, 0, None, now_iso(),
                                           complete=False)
                continue
            lines, consumed = complete_lines(read.data)
            budget -= len(read.data)
            parsed = [l for l in (parse_audit_line(x) for x in lines) if l is not None]
            in_window = [l for l in parsed if cutoff is None or l.at >= cutoff]
            logins = _coalesce(in_window)
            log.debug("%s: %s: %s read %d byte(s) from offset %d%s — %d line(s), %d login "
                      "event(s), %d inside retention, %d after pairing",
                      cluster.name, node, name, len(read.data), offset,
                      " (first sight: backfill)" if first_sight else "",
                      len(lines), len(parsed), len(in_window), len(logins))
            if lines and not parsed and name == AUDIT_FILE:
                log.debug("%s: %s: %d audit line(s) and no login attempt in any of them — either "
                          "nobody logged in, or this oauth-server build annotates nothing",
                          cluster.name, node, len(lines))
            observed_at = now_iso()
            events = [audit_event_dict(l, node, observed_at) for l in logins]

            # THE RECHECK. Everything above is reads; everything below writes.
            if elector is not None and not elector.is_leader:
                log.info("%s: lost leadership while reading %s on %s — discarding %d event(s)",
                         cluster.name, name, node, len(events))
                return recorded
            inserted, linked = (store.record_audit_login_events(
                cluster.name, events, CORRESPONDENCE_SECONDS) if events else (0, 0))
            recorded += inserted
            settled = max((l.at for l in parsed), default=None)
            complete = name != AUDIT_FILE and not read.truncated and consumed == len(read.data)
            store.set_audit_cursor(
                cluster.name, node, name, offset + consumed,
                settled.strftime(STAMP) if settled else (cur or {}).get("settled_through"),
                observed_at, complete=complete,
            )
            if inserted or linked:
                log.info("%s: recorded %d login attempt(s) from the audit log on %s (%s)%s",
                         cluster.name, inserted, node, name,
                         f", linked {linked} to pod-log rows" if linked else "")
        if elector is None or elector.is_leader:
            dropped = store.prune_audit_cursors(cluster.name, node, files)
            if dropped:
                log.info("%s: %s: forgot %d cursor(s) for audit files that rotated away",
                         cluster.name, node, dropped)

    if not read_ok:
        log.warning("%s: audit-log capture read none of the %d node(s) this cycle; the last-read "
                    "stamp is deliberately not advanced", cluster.name, len(nodes))
        return recorded
    if elector is not None and not elector.is_leader:
        return recorded
    store.record_login_read(cluster.name, now_iso())
    _prune(store, cluster, settings, elector, signals)
    return recorded
```

**`local-development/gsd/logincapture.py`** — dispatch. Old:

```python
    ns = settings.login_capture_namespace
    client = ClusterClient(cluster, timeout=timeout)
```

New:

```python
    if settings.login_capture_source == "audit-log":
        # The second source (docs/DESIGN_login_capture.md): same store, same status row, same
        # retention, a different reader. Dispatched here so the poller keeps one call site and
        # the never-take-the-poll-down contract is one contract.
        from .auditlog import capture_once as capture_audit_once
        return capture_audit_once(store, cluster, settings, elector, timeout, signals)

    ns = settings.login_capture_namespace
    client = ClusterClient(cluster, timeout=timeout)
```

## D1.5 Config — `local-development/gsd/config.py`

Insert after `login_retention_days: int = 400` (and its comment):

```python
    # WHICH LOG. `pod-log` reads the oauth-server pods' logs, which name a person only at
    # spec.logLevel: Debug on the authentication operator CR. `audit-log` reads
    # /var/log/oauth-server/audit.log on the control-plane nodes through the API server's node
    # proxy: no Debug, no OAuth roll, history back to the rotated files — and a cluster-wide read
    # grant, which is why the chart defaults it off. Anything unrecognised is pod-log: the
    # shipped default, and inert rather than wide.
    login_capture_source: str = "pod-log"
    # Which nodes hold the audit log: the control-plane ones, by selector — or by name, in which
    # case no node is ever listed and the nodes/proxy grant is pinned to those names.
    login_capture_audit_node_selector: str = "node-role.kubernetes.io/master="
    login_capture_audit_node_names: tuple[str, ...] = ()
```

Add a parser after `_visibility_setting`:

```python
def _login_capture_source_setting(raw: dict) -> str:
    """pod-log | audit-log. Fail SAFE to pod-log: it is the shipped default and needs nothing
    the audit source needs; a typo must not be what widens the read."""
    source = os.environ.get("GSD_LOGIN_CAPTURE_SOURCE")
    if source is None:
        source = raw.get("loginCaptureSource", "pod-log")
    word = str(source).strip().lower()
    if word in ("pod-log", "audit-log"):
        return word
    log.warning("loginCaptureSource=%r is not pod-log/audit-log; using 'pod-log'", source)
    return "pod-log"
```

And in `load_settings`, after `login_retention_days=int(raw.get("loginRetentionDays", 400)),`:

```python
        login_capture_source=_login_capture_source_setting(raw),
        login_capture_audit_node_selector=str(
            raw.get("loginCaptureAuditNodeSelector") or "node-role.kubernetes.io/master="
        ).strip(),
        login_capture_audit_node_names=tuple(
            n.strip() for n in str(raw.get("loginCaptureAuditNodeNames", "") or "").split(",")
            if n.strip()
        ),
```

## D1.6 Store — `local-development/gsd/store.py` and `local-development/gsd/storage.py`

**SCHEMA** — old `login_event` definition's columns `    detail              TEXT,` / `    observed_at         TEXT NOT NULL,` / `    UNIQUE(cluster_id, pod_name, user_name, at, outcome)` / `);` / the two indexes. New:

```sql
    detail              TEXT,
    observed_at         TEXT NOT NULL,
    -- 'pod-log' or 'audit-log' (migration 8). For an audit row pod_name carries the NODE the
    -- file was read from: the same "unit of log" role in the dedup key.
    source              TEXT NOT NULL DEFAULT 'pod-log',
    -- The audit event's own per-request id. Unique per cluster where present, so a re-read is
    -- free; SET on a pod-log row when an audit event corresponds to it, so one login read from
    -- both sources is one row that keeps its LDAP cause.
    audit_id            TEXT,
    UNIQUE(cluster_id, pod_name, user_name, at, outcome)
);
CREATE INDEX IF NOT EXISTS login_event_lookup ON login_event(cluster_id, at DESC);
CREATE INDEX IF NOT EXISTS login_event_by_user ON login_event(cluster_id, user_name, at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS login_event_by_audit_id
    ON login_event(cluster_id, audit_id) WHERE audit_id IS NOT NULL;

-- Where each audit FILE on each node has been read to, in bytes. Per file because rotation
-- renames the current file and starts a new one; the cursor follows the bytes, not the name.
-- settled_through is the newest event stamp read from that file — the per-node liveness that
-- gsd_login_capture_audit_settled_timestamp_seconds exports. complete=1 marks a rotated file
-- read to its end (immutable from then on); byte_offset=-1 marks one skipped by retention.
CREATE TABLE IF NOT EXISTS login_audit_cursor (
    cluster_id          TEXT NOT NULL,
    node_name           TEXT NOT NULL,
    file_name           TEXT NOT NULL,
    byte_offset         INTEGER NOT NULL,
    settled_through     TEXT,
    complete            INTEGER NOT NULL DEFAULT 0,
    updated_at          TEXT NOT NULL,
    PRIMARY KEY(cluster_id, node_name, file_name)
);
```

**Migration 8** — append to `_MIGRATIONS` after the `7` tuple:

```python
    (
        8,
        "login_event gains source + audit_id; login_audit_cursor for the audit-log source",
        [
            "ALTER TABLE login_event ADD COLUMN source TEXT NOT NULL DEFAULT 'pod-log'",
            "ALTER TABLE login_event ADD COLUMN audit_id TEXT",
            """CREATE UNIQUE INDEX IF NOT EXISTS login_event_by_audit_id
                   ON login_event(cluster_id, audit_id) WHERE audit_id IS NOT NULL""",
            """CREATE TABLE IF NOT EXISTS login_audit_cursor (
                   cluster_id          TEXT NOT NULL,
                   node_name           TEXT NOT NULL,
                   file_name           TEXT NOT NULL,
                   byte_offset         INTEGER NOT NULL,
                   settled_through     TEXT,
                   complete            INTEGER NOT NULL DEFAULT 0,
                   updated_at          TEXT NOT NULL,
                   PRIMARY KEY(cluster_id, node_name, file_name)
               )""",
            # Every existing row is a pod-log row, which the DEFAULT states. No backfill of
            # audit_id: the correspondence is established when the audit source first reads —
            # which, on a first sight, is a backfill that walks past every row already here.
        ],
    ),
```

**`record_login_events`** — old SQL columns `cluster_id, pod_name, user_name, outcome, at,` / `provider, ldap_result_code, detail, observed_at)` / `VALUES(:cluster_id,:pod_name,:user_name,:outcome,:at,` / `:provider,:ldap_result_code,:detail,:observed_at)""",` / `[{**e, "cluster_id": cluster_id} for e in events],`. New:

```python
                """INSERT OR IGNORE INTO login_event(
                       cluster_id, pod_name, user_name, outcome, at,
                       provider, ldap_result_code, detail, observed_at, source, audit_id)
                   VALUES(:cluster_id,:pod_name,:user_name,:outcome,:at,
                          :provider,:ldap_result_code,:detail,:observed_at,:source,:audit_id)""",
                [{"source": "pod-log", "audit_id": None, **e, "cluster_id": cluster_id}
                 for e in events],
```

**`login_events`** SELECT — old `                      e.pod_name, e.observed_at,` → new `                      e.pod_name, e.observed_at, e.source, e.audit_id,`.

**New methods**, inserted after `prune_login_watermarks`:

```python
    def record_audit_login_events(
        self, cluster_id: str, events: list[dict], correspondence_seconds: int = 2
    ) -> tuple[int, int]:
        """Insert audit-source attempts, LINKING one to an existing pod-log row where the two
        describe the same login. Returns (inserted, linked).

        Three checks per event, in order, each one index-served:
          1. its auditID is already stored — a re-read; nothing to do.
          2. a pod-log row for the same user, same success class, within the window and not yet
             linked — the same login seen from the other source: set audit_id on that row and
             keep it, because it carries the cause the audit log cannot.
          3. an audit row for the same user, same outcome, within ATTEMPT_WINDOW, with a
             DIFFERENT path in detail — a browser login's second annotated request; skipped.
        Otherwise it is a new row. Per event rather than one executemany because 2 and 3 read
        before they write; batches are bounded by the byte budget upstream.
        """
        inserted = linked = 0
        with self._write() as conn:
            for e in events:
                if conn.execute(
                    "SELECT 1 FROM login_event WHERE cluster_id=? AND audit_id=?",
                    (cluster_id, e["audit_id"]),
                ).fetchone():
                    continue
                at = datetime.fromisoformat(e["at"].replace("Z", "+00:00"))
                stamp = "%Y-%m-%dT%H:%M:%S.%fZ"
                lo = (at - timedelta(seconds=correspondence_seconds)).strftime(stamp)
                hi = (at + timedelta(seconds=correspondence_seconds)).strftime(stamp)
                success = 1 if e["outcome"] == "success" else 0
                twin = conn.execute(
                    """SELECT id FROM login_event
                        WHERE cluster_id=? AND user_name=? AND source='pod-log'
                          AND audit_id IS NULL AND at BETWEEN ? AND ?
                          AND (outcome='success') = ?
                        ORDER BY abs(julianday(at) - julianday(?)) LIMIT 1""",
                    (cluster_id, e["user_name"], lo, hi, success, e["at"]),
                ).fetchone()
                if twin:
                    conn.execute("UPDATE login_event SET audit_id=? WHERE id=?",
                                 (e["audit_id"], twin["id"]))
                    linked += 1
                    continue
                lo1 = (at - timedelta(seconds=1)).strftime(stamp)
                hi1 = (at + timedelta(seconds=1)).strftime(stamp)
                if conn.execute(
                    """SELECT 1 FROM login_event
                        WHERE cluster_id=? AND user_name=? AND source='audit-log'
                          AND outcome=? AND at BETWEEN ? AND ? AND detail IS NOT ?""",
                    (cluster_id, e["user_name"], e["outcome"], lo1, hi1, e["detail"]),
                ).fetchone():
                    continue
                before = conn.total_changes
                conn.execute(
                    """INSERT OR IGNORE INTO login_event(
                           cluster_id, pod_name, user_name, outcome, at,
                           provider, ldap_result_code, detail, observed_at, source, audit_id)
                       VALUES(:cluster_id,:pod_name,:user_name,:outcome,:at,
                              :provider,:ldap_result_code,:detail,:observed_at,:source,:audit_id)""",
                    {**e, "cluster_id": cluster_id},
                )
                inserted += conn.total_changes - before
        return inserted, linked

    def audit_cursors(self, cluster_id: str, node_name: str) -> dict[str, dict]:
        """{file_name: {byte_offset, settled_through, complete}} for one node."""
        return {
            r["file_name"]: {"byte_offset": r["byte_offset"],
                             "settled_through": r["settled_through"],
                             "complete": bool(r["complete"])}
            for r in self._rows(
                """SELECT file_name, byte_offset, settled_through, complete
                     FROM login_audit_cursor WHERE cluster_id=? AND node_name=?""",
                (cluster_id, node_name),
            )
        }

    def set_audit_cursor(
        self, cluster_id: str, node_name: str, file_name: str, byte_offset: int,
        settled_through: str | None, updated_at: str, *, complete: bool = False,
    ) -> None:
        """Write one file's cursor. A plain assignment, not a max(): rotation legitimately moves
        audit.log's cursor BACK to 0, and a late write from a demoted leader is harmless here
        because auditID makes a re-read free — the opposite trade from the pod-log watermark."""
        with self._write() as conn:
            conn.execute(
                """INSERT INTO login_audit_cursor(
                       cluster_id, node_name, file_name, byte_offset, settled_through, complete,
                       updated_at)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(cluster_id, node_name, file_name) DO UPDATE SET
                       byte_offset     = excluded.byte_offset,
                       settled_through = COALESCE(excluded.settled_through, settled_through),
                       complete        = excluded.complete,
                       updated_at      = excluded.updated_at""",
                (cluster_id, node_name, file_name, byte_offset, settled_through,
                 int(complete), updated_at),
            )

    def prune_audit_cursors(self, cluster_id: str, node_name: str, live_files: list[str]) -> int:
        """Forget cursors for files that rotated away (audit-log-maxbackup=10 deletes the oldest).
        An empty list removes nothing, for the reason prune_login_watermarks gives."""
        if not live_files:
            return 0
        with self._write() as conn:
            before = conn.total_changes
            conn.execute(
                "DELETE FROM login_audit_cursor WHERE cluster_id=? AND node_name=? "
                "AND file_name NOT IN (%s)" % ",".join("?" * len(live_files)),
                (cluster_id, node_name, *live_files),
            )
            return conn.total_changes - before

    def audit_settled_by_node(self, cluster_id: str) -> dict[str, str]:
        """{node: newest settled_through across its files} — the per-node liveness the metrics export."""
        return {
            r["node_name"]: r["settled"]
            for r in self._rows(
                """SELECT node_name, MAX(settled_through) AS settled
                     FROM login_audit_cursor WHERE cluster_id=? AND settled_through IS NOT NULL
                    GROUP BY node_name""",
                (cluster_id,),
            )
        }
```

(`timedelta` must be added to `store.py`'s `from datetime import UTC, datetime` → `from datetime import UTC, datetime, timedelta`.)

**`storage.py` Protocol** — after `def prune_login_watermarks(...) -> int: ...` add:

```python
    # The audit-log source (gsd/auditlog.py). Same writer thread, same status row.
    def record_audit_login_events(
        self, cluster_id: str, events: list[dict], correspondence_seconds: int = 2
    ) -> tuple[int, int]: ...
    def audit_cursors(self, cluster_id: str, node_name: str) -> dict[str, dict]: ...
    def set_audit_cursor(
        self, cluster_id: str, node_name: str, file_name: str, byte_offset: int,
        settled_through: str | None, updated_at: str, *, complete: bool = False,
    ) -> None: ...
    def prune_audit_cursors(self, cluster_id: str, node_name: str, live_files: list[str]) -> int: ...
    def audit_settled_by_node(self, cluster_id: str) -> dict[str, str]: ...
```

## D1.7 API and UI

**`gsd/api.py#list_logins`** — old:

```python
            "enabled": settings.login_capture_enabled,
            "note": "read from the oauth-server log at Debug verbosity; covers only the period "
                    "since capture began — earlier logins were never recorded and cannot be "
                    "fetched, and rows older than the configured retention age out",
```

New:

```python
            "enabled": settings.login_capture_enabled,
            # Which log the rows come from, and what that source can and cannot say — the two
            # differ in exactly the ways a reader of this page needs to know (no cause and no
            # CLI provider from the audit log; no history from the pod log).
            "source": settings.login_capture_source,
            "note": (
                "read from the oauth-server audit log on the control-plane nodes: no Debug "
                "verbosity needed, and history back to the oldest rotated audit file on a first "
                "read. The audit log records no cause for a refusal and names the identity "
                "provider only for browser logins, so `failed` rows here carry no LDAP code and "
                "CLI logins carry no provider; rows older than the configured retention age out"
                if settings.login_capture_source == "audit-log" else
                "read from the oauth-server log at Debug verbosity; covers only the period "
                "since capture began — earlier logins were never recorded and cannot be "
                "fetched, and rows older than the configured retention age out"
            ),
```

**`gsd/static/index.html`** — the table header cell `<th>Replica</th>` becomes `<th>${d.source === "audit-log" ? "Node" : "Replica"}</th>` (the cell already renders `r.pod_name`, which carries the node for audit rows). Everything else on the tab reads `d.note`, `capture_started_at` and `last_read_at`, which are source-independent.

## D1.8 Metrics — `local-development/gsd/metrics.py`

Add the label decision first: **a separate family, not a `source` label on the existing gauge.** Adding a label changes the series identity of `gsd_login_capture_last_read_timestamp_seconds{cluster}` — every recording rule and dashboard keyed on it breaks, and `templates/monitoring.yaml#GroupSyncDashboardLoginCaptureStalled` would fire on the stale old series through a restart. An info gauge joins cleanly: `gsd_login_capture_last_read_timestamp_seconds * on(cluster) group_left(source) gsd_login_capture_source_info`.

In `_gather`, after the `capture_last_read = GaugeMetricFamily(...)` declaration add:

```python
        capture_source = GaugeMetricFamily(
            "gsd_login_capture_source_info",
            "Always 1; `source` is which log login capture reads for this cluster (pod-log or "
            "audit-log). Join it onto gsd_login_capture_last_read_timestamp_seconds with "
            "on(cluster) group_left(source) — a separate family so that series keeps its "
            "identity and the stalled alert keeps firing across the switch. Absent when "
            "capture is off.",
            labels=["cluster", "source"],
        )
        audit_settled = GaugeMetricFamily(
            "gsd_login_capture_audit_settled_timestamp_seconds",
            "Unix time of the newest audit-log event read from this node, audit-log source "
            "only. One control-plane node lagging the others while last_read advances is a "
            "node whose file cannot be read. Absent until the node's file has been read once.",
            labels=["cluster", "node"],
        )
```

In the per-cluster loop, after `capture_last_read.add_metric([cluster], read_ts)` block:

```python
                if (self.settings is not None
                        and getattr(self.settings, "login_capture_enabled", False)):
                    capture_source.add_metric(
                        [cluster, getattr(self.settings, "login_capture_source", "pod-log")], 1)
                    if getattr(self.settings, "login_capture_source", "pod-log") == "audit-log":
                        for node, settled in sorted(
                                self.store.audit_settled_by_node(cluster).items()):
                            settled_ts = _epoch(settled)
                            if settled_ts is not None:
                                audit_settled.add_metric([cluster, node], settled_ts)
```

And extend the final `yield from (... alerts, capture_last_read,)` to `... alerts, capture_last_read, capture_source, audit_settled,`. Both families are declared unconditionally, which `tests/test_metrics.py::test_event_families_are_declared_even_unwired`'s discipline expects; add their names to that test's list.

## D1.9 Chart

**`values.yaml`** — under `loginCapture:`, after `  enabled: false`:

```yaml
  # WHICH LOG TO READ. Two sources, and the whole point of the second is what it does not need:
  #
  #   pod-log     (default) the oauth-server pods' logs, through a Role in openshift-authentication
  #               on `pods` and `pods/log`. Names a person ONLY at spec.logLevel: Debug on the
  #               authentication operator CR (authLogLevel below), which rolls the OAuth server —
  #               a login outage at one replica — and history dies with every pod. What it has that
  #               the audit log does not: the LDAP result code and AD sub-code behind a refusal.
  #   audit-log   /var/log/oauth-server/audit.log on the control-plane nodes, read through the API
  #               server's node proxy (what `oc adm node-logs --path=oauth-server/audit.log` does).
  #               Written at every audit profile but None, at the DEFAULT verbosity: no Debug, no
  #               roll, no outage, and a first read backfills as far back as the rotated files
  #               reach (audit-log-maxsize 100 MB x maxbackup 10 — by volume, not by days; one lab
  #               cluster held sixteen months). It records allow/deny/error and the username,
  #               never a cause, and names the identity provider only for browser logins.
  #
  # THE COST OF audit-log, STATED: the grant is a ClusterRole with `get` on `nodes/proxy`, which
  # is READ ACCESS TO EVERYTHING THE KUBELET SERVES OVER GET on those nodes — every container's
  # logs on them (/containerLogs), the kube-apiserver and openshift-apiserver audit logs, the
  # journal — and `list nodes` to find the control-plane nodes. That is categorically wider than
  # a namespaced pods/log Role and it is a standing capability, which is why this defaults to
  # pod-log despite the audit log being the better source in every other respect. Narrow it with
  # auditLog.nodeNames below (resourceNames on nodes/proxy, and no list at all).
  #
  # HOW IT MEETS authLogLevel: with source audit-log, Debug is unnecessary. The chart REFUSES
  # source=audit-log together with authLogLevel.enabled=true — it will not roll the OAuth server
  # as a side effect of a read setting — and the retirement order is the README's two-step:
  #   1. loginCapture.source=audit-log  authLogLevel.manage=true   authLogLevel.enabled=false
  #      (the Job converges the cluster to Normal; one last roll)
  #   2. authLogLevel.manage=false once the rollout has finished.
  # The audit log is the authoritative record from then on; pod-log rows already stored are kept,
  # and an audit event that corresponds to one is linked to it rather than recorded twice.
  source: pod-log

  auditLog:
    # Which nodes hold the file: the control-plane nodes. A label selector, listed each cycle.
    nodeSelector: "node-role.kubernetes.io/master="
    # OR the names, pinned. Set this and the chart grants nodes/proxy on exactly these names and
    # drops the list grant. Names are cluster-specific, so it cannot be a default:
    #   nodeNames: [master-0, master-1, master-2]
    nodeNames: []
```

**`_helpers.tpl`** — append:

```
# ── Login capture source ──────────────────────────────────────────────────────────────────
# pod-log | audit-log, validated where it is resolved, and the ONE place the two switches that
# interact are reconciled: audit-log makes Debug unnecessary, so a render that asks for both is a
# contradiction and is refused — never resolved by quietly rolling the OAuth server.
{{- define "gsd.loginCaptureSource" -}}
{{- $lc := .Values.loginCapture | default dict -}}
{{- $s := "pod-log" -}}
{{- if and (hasKey $lc "source") (not (kindIs "invalid" $lc.source)) -}}{{- $s = trim (toString $lc.source) -}}{{- end -}}
{{- if not (has $s (list "pod-log" "audit-log")) -}}
{{- fail (printf "loginCapture.source %q is not one of pod-log, audit-log." $s) -}}
{{- end -}}
{{- if and (eq $s "audit-log") ((.Values.authLogLevel | default dict).enabled) -}}
{{- fail "loginCapture.source=audit-log and authLogLevel.enabled=true contradict each other: the audit log names every login at the DEFAULT verbosity, so Debug on the authentication operator CR buys nothing and costs an OAuth roll. The chart will not roll the OAuth server as a side effect of a read setting. Retire Debug in order:\n  1. --set loginCapture.source=audit-log --set authLogLevel.manage=true --set authLogLevel.enabled=false   (converges the cluster to Normal; one last roll — a login outage at one replica)\n  2. --set authLogLevel.manage=false once the rollout has finished.\nPass your whole values file each time (see the chart README)." -}}
{{- end -}}
{{- $s -}}
{{- end -}}
```

**`templates/login-capture-rbac.yaml`** — replace the whole file's opening `{{- if .Values.loginCapture.enabled }}` with a two-branch file:

```yaml
{{- $source := include "gsd.loginCaptureSource" . }}
{{- if and .Values.loginCapture.enabled (eq $source "audit-log") }}
# Lets the DASHBOARD read the oauth-server's AUDIT log on the control-plane nodes.
#
# A ClusterRole, and the reason is the resource: node logs are reached through the API server's
# node proxy — GET /api/v1/nodes/<node>/proxy/logs/oauth-server/audit.log, what `oc adm node-logs`
# issues — which the API server authorises as `get nodes/proxy`. That verb on that subresource is
# READ ACCESS TO EVERYTHING THE KUBELET SERVES OVER GET: every container's log on the node
# (/containerLogs/<ns>/<pod>/<container>), the kube-apiserver and openshift-apiserver audit logs,
# the journal. Read-only, and far wider than the namespaced pods/log Role the pod-log source
# uses; values.yaml says why it is worth it and why it is opt-in. `resourceNames` narrows it to
# named nodes when loginCapture.auditLog.nodeNames is set — honoured for `get`, which is the only
# verb here — and then no `list nodes` is needed or granted.
#
# Still no write verb: rbac.yaml's "NO WRITE VERB" invariant is untouched, and
# tests/test_chart_strategy.py::TestLoginCaptureReadsOneNamespaceOnly still holds — this role
# grants no pods and no pods/log anywhere.
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: {{ include "gsd.fullname" . }}-login-capture-audit
  labels:
    {{- include "gsd.labels" . | nindent 4 }}
    app.kubernetes.io/component: login-capture
rules:
  - apiGroups: [""]
    resources: ["nodes/proxy"]
    verbs: ["get"]
    {{- with .Values.loginCapture.auditLog.nodeNames }}
    resourceNames: {{ toJson . }}
    {{- end }}
  {{- if not .Values.loginCapture.auditLog.nodeNames }}
  # Discovery of the control-plane nodes by selector. Node objects are metadata (names, labels,
  # addresses, versions); `list` cannot be narrowed by name, which is exactly what pinning
  # nodeNames buys — with names set this rule does not render.
  - apiGroups: [""]
    resources: ["nodes"]
    verbs: ["list"]
  {{- end }}
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: {{ include "gsd.fullname" . }}-login-capture-audit
  labels:
    {{- include "gsd.labels" . | nindent 4 }}
    app.kubernetes.io/component: login-capture
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: {{ include "gsd.fullname" . }}-login-capture-audit
subjects:
  - kind: ServiceAccount
    name: {{ include "gsd.serviceAccountName" . }}
    namespace: {{ .Release.Namespace }}
{{- else if .Values.loginCapture.enabled }}
```

…followed by the existing Role/RoleBinding text unchanged, ending in the existing `{{- end }}`. The pod-log render is byte-identical to today.

**`templates/configmap.yaml`** — after `    loginCaptureNamespace: {{ .Values.loginCapture.namespace | quote }}` add:

```yaml
    # Which log capture reads. Through the helper, which is also where source=audit-log and
    # authLogLevel.enabled=true are refused as a contradiction.
    loginCaptureSource: {{ include "gsd.loginCaptureSource" . | quote }}
    loginCaptureAuditNodeSelector: {{ .Values.loginCapture.auditLog.nodeSelector | quote }}
    loginCaptureAuditNodeNames: {{ .Values.loginCapture.auditLog.nodeNames | join "," | quote }}
```

**`templates/NOTES.txt`** — after the Visibility block, add:

```
{{- if and .Values.loginCapture.enabled (eq (include "gsd.loginCaptureSource" .) "audit-log") }}

Login capture: AUDIT LOG. The dashboard reads /var/log/oauth-server/audit.log on the
control-plane nodes through the API server's node proxy — a ClusterRole with `get nodes/proxy`,
which is read access to everything the kubelet serves on those nodes. No Debug verbosity is
needed; if authLogLevel.manage is still true with enabled=false, the Job is converging the
cluster back to Normal and you can set manage=false once the rollout has finished.
First read backfills as far as the rotated audit files reach, {{ .Values.loginCapture.retentionDays }} days at most.
{{- end }}
```

**Chart README rows** (RBAC and monitoring table, before the `authLogLevel.manage` row):

```markdown
| `loginCapture.enabled` | `false` | lets the dashboard read the oauth-server's log so the Logins tab has a source. Which log is `source` |
| `loginCapture.source` | `pod-log` | `pod-log` — a Role on `pods`/`pods/log` in `loginCapture.namespace`; names a person only at Debug (`authLogLevel`), keeps the LDAP cause, loses history with every pod. `audit-log` — `/var/log/oauth-server/audit.log` on the control-plane nodes through the node proxy: no Debug, no OAuth roll, history back to the rotated files; a **ClusterRole on `get nodes/proxy`**, which reads everything the kubelet serves on those nodes, plus `list nodes` unless `auditLog.nodeNames` is set — read-only, cluster-wide, hence not the default. Refused together with `authLogLevel.enabled=true`; the audit log is authoritative from the switch on and corresponding pod-log rows are linked, not doubled |
| `loginCapture.namespace` | `openshift-authentication` | pod-log source only: where the oauth-server pods run |
| `loginCapture.htpasswdProviders` | `[developer]` | identity-provider **names** whose successes are break-glass accounts, excluded from "accounts in no synced group". The audit log names a provider only for browser logins, so a CLI `kubeadmin` login recorded from it is not labelled break-glass |
| `loginCapture.retentionDays` | `400` | how long an attempt is kept; also the bound on the audit-log backfill. `0` disables pruning |
| `loginCapture.auditLog.nodeSelector` | `node-role.kubernetes.io/master=` | audit-log source: which nodes hold the file, listed each cycle |
| `loginCapture.auditLog.nodeNames` | `[]` | audit-log source: pin the nodes instead; `nodes/proxy` is then granted on exactly these names and `list nodes` is not granted at all |
```

**`Chart.yaml`** — bump `version: 0.11.0` → `0.12.0`, `appVersion: "0.12.0"` → `"0.13.0"`, with history paragraphs:

```yaml
# CHART 0.12.0 (2026-09-04), MINOR: appVersion moves to application 0.13.0 (below), and login
# capture gains a second source. `loginCapture.source: audit-log` reads the oauth-server's audit
# log on the control-plane nodes — no Debug on the authentication operator CR, so the
# authLogLevel Jobs can be retired — and renders a ClusterRole on `get nodes/proxy` (+ `list
# nodes`, or resourceNames from loginCapture.auditLog.nodeNames) INSTEAD of the namespaced Role.
# Default pod-log: the render is byte-identical to 0.11.0. New refusal: source=audit-log with
# authLogLevel.enabled=true (docs/DESIGN_login_capture.md).
```

```yaml
# 0.13.0 (2026-09-04). Login capture from the oauth-server audit log: schema migration 8 (source,
# audit_id, login_audit_cursor), outcome vocabulary gains provider_error, /logins carries `source`
# and a source-specific note, rows carry source and audit_id, two new metric families. MINOR.
```

`pyproject.toml` and `gsd/__init__.py` move to `0.13.0`.

## D1.10 Tests

**New file `local-development/tests/test_auditlog.py`** — fixtures are marked DOCUMENTED-SHAPE (from https://developers.redhat.com/articles/2024/07/29/how-classify-red-hat-openshift-audit-logs and the CLI form measured in `docs/DESIGN_login_capture.md`), to be replaced by lines captured on CRC during implementation:

```python
"""The audit-log source: the parser, the cursor, the backfill, and the link to pod-log rows.

FIXTURES ARE DOCUMENTED-SHAPE, NOT MEASURED. The browser events reproduce the two examples in Red
Hat's "How to classify OpenShift audit logs" (2024-07-29) verbatim in field set and values; the CLI
event is the same shape on /oauth/authorize, which docs/DESIGN_login_capture.md measured five of.
Replace them with lines captured on CRC (`oc adm node-logs --path=oauth-server/audit.log`) during
implementation and keep this docstring's provenance sentence current.
"""
from __future__ import annotations

import json
import logging
from datetime import UTC, datetime, timedelta

import pytest

from gsd import auditlog, logincapture, loginlog
from gsd.auditlog import (AUDIT_FILE, SKIPPED, audit_event_dict, capture_once, complete_lines,
                          parse_audit_line, rotated_at)
from gsd.config import ClusterConfig, Settings
from gsd.kube import ClusterError, NodeLogRead
from gsd.logincapture import event_dict
from gsd.loginlog import LoginAttempt
from gsd.store import Store

CLUSTER = ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")
NODE = "crc-master-0"


def _event(user, decision, at, uri="/login", audit_id=None, stage="ResponseComplete", code=302):
    """DOCUMENTED-SHAPE oauth-server audit event."""
    return json.dumps({
        "kind": "Event", "apiVersion": "audit.k8s.io/v1", "level": "Metadata",
        "auditID": audit_id or f"{user}-{at.timestamp()}-{uri}", "stage": stage,
        "requestURI": uri, "verb": "post" if uri.startswith("/login") else "get",
        "user": {"username": "system:anonymous", "groups": ["system:unauthenticated"]},
        "sourceIPs": ["10.128.8.1"], "userAgent": "Mozilla/5.0",
        "responseStatus": {"metadata": {}, "code": code},
        "requestReceivedTimestamp": (at - timedelta(milliseconds=40)).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "stageTimestamp": at.strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
        "annotations": {
            "authentication.openshift.io/decision": decision,
            "authentication.openshift.io/username": user,
            "authorization.k8s.io/decision": "allow", "authorization.k8s.io/reason": "",
        },
    })


class TestTheParser:
    def test_allow_deny_error_map_to_the_vocabulary(self):
        at = datetime(2024, 6, 25, 10, 46, 59, 895431, tzinfo=UTC)
        assert parse_audit_line(_event("foo", "allow", at)).decision == "allow"
        row = audit_event_dict(parse_audit_line(_event("foo", "allow", at)), NODE, "x")
        assert row["outcome"] == loginlog.OUTCOME_SUCCESS and row["source"] == "audit-log"
        assert audit_event_dict(parse_audit_line(_event("bar", "deny", at)), NODE, "x")["outcome"] == loginlog.OUTCOME_FAILED
        assert audit_event_dict(parse_audit_line(_event("bar", "error", at)), NODE, "x")["outcome"] == loginlog.OUTCOME_PROVIDER_ERROR

    def test_the_username_comes_from_the_annotation_never_from_user(self):
        at = datetime.now(UTC)
        login = parse_audit_line(_event("foo", "allow", at))
        assert login.user_name == "foo", "user.username is system:anonymous on a login request"

    def test_request_received_and_unannotated_events_are_not_attempts(self):
        at = datetime.now(UTC)
        assert parse_audit_line(_event("foo", "allow", at, stage="RequestReceived")) is None
        plain = json.loads(_event("foo", "allow", at))
        plain["annotations"] = {"authorization.k8s.io/decision": "allow"}
        assert parse_audit_line(json.dumps(plain)) is None
        assert parse_audit_line("not json") is None
        assert parse_audit_line(json.dumps({"kind": "Status"})) is None

    def test_the_provider_is_read_from_the_browser_path_only(self):
        at = datetime.now(UTC)
        assert parse_audit_line(_event("a", "allow", at, uri="/login/ldap-local?then=%2F")).provider == "ldap-local"
        assert parse_audit_line(_event("a", "allow", at, uri="/login")).provider is None
        cli = parse_audit_line(_event("a", "allow", at, uri="/oauth/authorize?client_id=openshift-challenging-client&code_challenge=abc&response_type=code"))
        assert cli.provider is None and cli.request_path == "/oauth/authorize"

    def test_the_query_string_is_never_persisted(self):
        at = datetime.now(UTC)
        row = audit_event_dict(parse_audit_line(_event("a", "allow", at, uri="/oauth/authorize?code_challenge=SECRETISH")), NODE, "x")
        assert "SECRETISH" not in json.dumps(row)

    def test_the_stamp_is_microseconds_utc_in_the_shared_format(self):
        at = datetime(2024, 6, 25, 10, 46, 59, 895431, tzinfo=UTC)
        assert audit_event_dict(parse_audit_line(_event("a", "allow", at)), NODE, "x")["at"] == "2024-06-25T10:46:59.895431Z"


class TestLinesAndNames:
    def test_only_whole_lines_are_consumed(self):
        lines, used = complete_lines(b'{"a":1}\n{"b":2}\n{"half')
        assert lines == ['{"a":1}', '{"b":2}'] and used == 16

    def test_a_rotated_name_yields_its_close_time(self):
        assert rotated_at("audit-2021-03-09T00-12-19.834.log") == datetime(2021, 3, 9, 0, 12, 19, 834000, tzinfo=UTC)
        assert rotated_at("audit.log") is None and rotated_at("kube-apiserver.log") is None


class FakeNodeClient:
    """The four calls capture_once makes, with a byte-addressable fake filesystem per node."""

    def __init__(self, nodes=None, files=None, forbidden_nodes=False, honour_range=True):
        self._nodes = nodes if nodes is not None else [NODE]
        self.files = files or {}                        # {node: {name: bytes}}
        self.forbidden_nodes = forbidden_nodes
        self.honour_range = honour_range
        self.reads: list[tuple[str, str, int]] = []
        self.rotated_names: set[tuple[str, str]] = set()

    def fetch_nodes(self, selector):
        return None if self.forbidden_nodes else list(self._nodes)

    def list_node_log_files(self, node, directory):
        return sorted(self.files.get(node, {})) if node in self.files else None

    def fetch_node_log_file(self, node, path, offset=0, max_bytes=8 << 20):
        name = path.split("/", 1)[1]
        self.reads.append((node, name, offset))
        data = self.files[node].get(name)
        if data is None:
            return None
        if offset > len(data):
            return NodeLogRead(data=b"", offset=offset, truncated=False, rotated=True)
        chunk = data[offset:offset + max_bytes]
        return NodeLogRead(data=chunk, offset=offset, truncated=offset + max_bytes < len(data), rotated=False)


@pytest.fixture()
def store(tmp_path):
    s = Store(str(tmp_path / "audit.db"))
    s.upsert_cluster(CLUSTER.name, CLUSTER.api_url, True)
    yield s
    s.close()


@pytest.fixture()
def settings(tmp_path):
    return Settings(clusters=[CLUSTER], db_path=str(tmp_path / "audit.db"),
                    login_capture_enabled=True, login_capture_source="audit-log")


@pytest.fixture()
def install(monkeypatch):
    def _install(client):
        monkeypatch.setattr(auditlog, "ClusterClient", lambda *a, **kw: client)
        return client
    return _install


def _file(*events):
    return ("\n".join(events) + "\n").encode()


class TestDispatchAndRefusals:
    def test_logincapture_dispatches_on_the_source(self, store, settings, install):
        client = install(FakeNodeClient(files={NODE: {AUDIT_FILE: _file(_event("a", "allow", datetime.now(UTC)))}}))
        assert logincapture.capture_once(store, CLUSTER, settings) == 1
        assert client.reads

    def test_forbidden_node_list_records_nothing_and_warns(self, store, settings, install, caplog):
        install(FakeNodeClient(forbidden_nodes=True))
        with caplog.at_level(logging.WARNING):
            assert capture_once(store, CLUSTER, settings) == 0
        assert "not permitted to list nodes" in caplog.text
        assert store.login_capture_status(CLUSTER.name) is None

    def test_pinned_node_names_skip_the_list(self, store, install, tmp_path):
        s = Settings(clusters=[CLUSTER], db_path=str(tmp_path / "audit.db"), login_capture_enabled=True,
                     login_capture_source="audit-log", login_capture_audit_node_names=("pinned",))
        client = install(FakeNodeClient(forbidden_nodes=True, files={"pinned": {AUDIT_FILE: _file(_event("a", "allow", datetime.now(UTC)))}}))
        assert capture_once(store, CLUSTER, s) == 1

    def test_no_audit_files_is_not_nobody_logged_in(self, store, settings, install, caplog):
        install(FakeNodeClient(files={NODE: {"other.log": b""}}))
        with caplog.at_level(logging.INFO):
            assert capture_once(store, CLUSTER, settings) == 0
        assert "audit profile None" in caplog.text
        assert store.login_capture_status(CLUSTER.name) is None

    def test_lost_leadership_writes_nothing(self, store, settings, install):
        class Lost:
            is_leader = False
        install(FakeNodeClient(files={NODE: {AUDIT_FILE: _file(_event("a", "allow", datetime.now(UTC)))}}))
        assert capture_once(store, CLUSTER, settings, elector=Lost()) == 0
        assert store.login_events(CLUSTER.name) == [] and store.audit_cursors(CLUSTER.name, NODE) == {}


class TestTheCursor:
    def test_the_cursor_stops_at_the_last_newline_and_resumes_there(self, store, settings, install):
        now = datetime.now(UTC)
        whole = _file(_event("a", "allow", now))
        client = install(FakeNodeClient(files={NODE: {AUDIT_FILE: whole + b'{"half'}}))
        assert capture_once(store, CLUSTER, settings) == 1
        assert store.audit_cursors(CLUSTER.name, NODE)[AUDIT_FILE]["byte_offset"] == len(whole)
        client.files[NODE][AUDIT_FILE] = whole + _file(_event("b", "deny", now + timedelta(seconds=5)))
        assert capture_once(store, CLUSTER, settings) == 1
        assert client.reads[-1] == (NODE, AUDIT_FILE, len(whole))

    def test_a_re_read_is_free_by_audit_id(self, store, settings, install):
        now = datetime.now(UTC)
        client = install(FakeNodeClient(files={NODE: {AUDIT_FILE: _file(_event("a", "allow", now, audit_id="id-1"))}}))
        assert capture_once(store, CLUSTER, settings) == 1
        store.set_audit_cursor(CLUSTER.name, NODE, AUDIT_FILE, 0, None, "x")   # a rewound cursor
        assert capture_once(store, CLUSTER, settings) == 0
        assert len(store.login_events(CLUSTER.name)) == 1

    def test_first_sight_backfills_rotated_files_oldest_first_within_retention(self, store, settings, install):
        now = datetime.now(UTC)
        old = "audit-2020-01-01T00-00-00.000.log"          # closed before the 400-day cutoff
        mid = (now - timedelta(days=30)).strftime("audit-%Y-%m-%dT%H-%M-%S.000.log")
        client = install(FakeNodeClient(files={NODE: {
            old: _file(_event("ancient", "allow", now - timedelta(days=2000))),
            mid: _file(_event("recent", "allow", now - timedelta(days=31))),
            AUDIT_FILE: _file(_event("live", "allow", now)),
        }}))
        assert capture_once(store, CLUSTER, settings) == 2
        assert [r[1] for r in client.reads] == [mid, AUDIT_FILE], "oldest readable first, audit.log last"
        cursors = store.audit_cursors(CLUSTER.name, NODE)
        assert cursors[old]["byte_offset"] == SKIPPED and cursors[mid]["complete"] is True
        assert {r["user_name"] for r in store.login_events(CLUSTER.name)} == {"recent", "live"}

    def test_rotation_hands_the_cursor_to_the_new_name(self, store, settings, install):
        now = datetime.now(UTC)
        first = _file(_event("a", "allow", now - timedelta(minutes=2)))
        client = install(FakeNodeClient(files={NODE: {AUDIT_FILE: first}}))
        assert capture_once(store, CLUSTER, settings) == 1
        rotated = now.strftime("audit-%Y-%m-%dT%H-%M-%S.000.log")
        client.files[NODE] = {rotated: first + _file(_event("b", "allow", now - timedelta(minutes=1))),
                              AUDIT_FILE: _file(_event("c", "allow", now))}
        capture_once(store, CLUSTER, settings)            # detects the shrink, hands over
        cursors = store.audit_cursors(CLUSTER.name, NODE)
        assert cursors[rotated]["byte_offset"] == len(first) and cursors[AUDIT_FILE]["byte_offset"] == 0
        assert capture_once(store, CLUSTER, settings) == 2
        assert {r["user_name"] for r in store.login_events(CLUSTER.name)} == {"a", "b", "c"}

    def test_the_byte_budget_defers_rather_than_drops(self, store, settings, install, monkeypatch):
        now = datetime.now(UTC)
        events = [_event(f"u{i}", "allow", now - timedelta(seconds=100 - i)) for i in range(20)]
        monkeypatch.setattr(auditlog, "AUDIT_READ_MAX_BYTES", len(_file(*events[:5])) + 1)
        install(FakeNodeClient(files={NODE: {AUDIT_FILE: _file(*events)}}))
        first = capture_once(store, CLUSTER, settings)
        assert 0 < first < 20
        total = first
        for _ in range(10):
            total += capture_once(store, CLUSTER, settings)
        assert total == 20

    def test_stale_cursors_are_pruned_and_last_read_advances(self, store, settings, install):
        client = install(FakeNodeClient(files={NODE: {"audit-2025-01-01T00-00-00.000.log": b"", AUDIT_FILE: b""}}))
        capture_once(store, CLUSTER, settings)
        client.files[NODE] = {AUDIT_FILE: b""}
        capture_once(store, CLUSTER, settings)
        assert "audit-2025-01-01T00-00-00.000.log" not in store.audit_cursors(CLUSTER.name, NODE)
        assert store.login_capture_status(CLUSTER.name)["last_read_at"]


class TestCorrespondenceWithThePodLog:
    def test_an_audit_event_links_to_its_pod_log_twin_instead_of_doubling(self, store):
        at = datetime.now(UTC) - timedelta(minutes=5)
        store.record_login_events(CLUSTER.name, [event_dict(
            LoginAttempt("jane", loginlog.OUTCOME_BAD_PASSWORD, at, provider="ldap-local", ldap_result_code=49),
            "oauth-openshift-aaa", "x")])
        row = audit_event_dict(parse_audit_line(_event("jane", "deny", at + timedelta(milliseconds=16), audit_id="aud-1")), NODE, "x")
        assert store.record_audit_login_events(CLUSTER.name, [row], 2) == (0, 1)
        rows = store.login_events(CLUSTER.name)
        assert len(rows) == 1 and rows[0]["audit_id"] == "aud-1"
        assert rows[0]["outcome"] == loginlog.OUTCOME_BAD_PASSWORD, "the pod-log row keeps its cause"

    def test_a_success_does_not_link_to_a_failure(self, store):
        at = datetime.now(UTC) - timedelta(minutes=5)
        store.record_login_events(CLUSTER.name, [event_dict(LoginAttempt("jane", loginlog.OUTCOME_FAILED, at), "p", "x")])
        row = audit_event_dict(parse_audit_line(_event("jane", "allow", at, audit_id="aud-2")), NODE, "x")
        assert store.record_audit_login_events(CLUSTER.name, [row], 2) == (1, 0)

    def test_a_browser_logins_second_request_is_one_attempt(self, store):
        at = datetime.now(UTC) - timedelta(minutes=5)
        a = parse_audit_line(_event("bob", "allow", at, uri="/login/ldap-local", audit_id="x1"))
        b = parse_audit_line(_event("bob", "allow", at + timedelta(milliseconds=300), uri="/oauth/authorize?x=y", audit_id="x2"))
        rows = [audit_event_dict(l, NODE, "x") for l in auditlog._coalesce([b, a])]
        assert len(rows) == 1 and rows[0]["provider"] == "ldap-local"
        # and across batches, the store applies the same rule
        store.record_audit_login_events(CLUSTER.name, rows, 2)
        late = audit_event_dict(b, NODE, "x")
        assert store.record_audit_login_events(CLUSTER.name, [late], 2) == (0, 0)

    def test_two_real_attempts_on_one_path_stay_two(self, store):
        at = datetime.now(UTC) - timedelta(minutes=5)
        rows = [audit_event_dict(parse_audit_line(_event("bob", "deny", at + timedelta(seconds=i * 3), uri="/login", audit_id=f"r{i}")), NODE, "x") for i in range(2)]
        assert store.record_audit_login_events(CLUSTER.name, rows, 2) == (2, 0)


class TestMigrationEight:
    def test_an_existing_row_is_a_pod_log_row(self, tmp_path):
        s = Store(str(tmp_path / "m.db"))
        s.upsert_cluster("c", "https://x", True)
        s.record_login_events("c", [event_dict(LoginAttempt("a", loginlog.OUTCOME_SUCCESS, datetime.now(UTC)), "p", "x")])
        row = s.login_events("c")[0]
        assert row["source"] == "pod-log" and row["audit_id"] is None
        s.close()
```

Plus: `tests/test_config.py` — three tests (`loginCaptureSource` parses, junk falls back to `pod-log` with a warning, node names split); `tests/test_chart_strategy.py::TestAuditLogSource` — default renders no `login-capture-audit`; `audit-log` renders the ClusterRole with exactly `[("nodes/proxy",),("get",)]` and `[("nodes",),("list",)]` and **no** Role in `openshift-authentication`; `nodeNames` set → `resourceNames` present and no `nodes` list rule; `TestLoginCaptureReadsOneNamespaceOnly.test_the_log_read_is_never_cluster_scoped` re-run with `loginCapture__source=audit-log` in its `extra` list; `audit-log` + `authLogLevel__enabled=true` refused with "contradict"; `audit-log` + `manage=true` + `enabled=false` renders and the Job's `WANT=Normal`; `loginCapture__source=both` refused; ConfigMap carries `loginCaptureSource: "audit-log"`. `tests/test_metrics.py` — `gsd_login_capture_source_info{cluster="crc",source="audit-log"} 1` when settings say so, absent when capture is off; `gsd_login_capture_audit_settled_timestamp_seconds{cluster,node}` after a `set_audit_cursor`; both names added to `test_event_families_are_declared_even_unwired`. `tests/test_users_tab_logins.py`-style API test: `/logins` carries `source` and the audit note; `?outcome=provider_error` is accepted (200).

## D1.11 Docs

- **`docs/DESIGN_login_capture.md`** — replace the heading `## The oauth-server AUDIT LOG — a better source, not used` and its first paragraph (`Found after the design was written ... not an oversight.`) with `## The oauth-server AUDIT LOG — the second source (0.13.0)` and: `Found after the design was written, measured on the live cluster, parked for a release because of the grant it needs, and adopted in 0.13.0 as \`loginCapture.source: audit-log\` — opt-in, for exactly that reason. The reader is \`gsd/kube.py#ClusterClient.fetch_node_log_file\` (byte cursor, Range, rotation detection), the front end is \`gsd/auditlog.py#parse_audit_line\`, the loop is \`gsd/auditlog.py#capture_once\`, and the link to pod-log rows is \`gsd/store.py#Store.record_audit_login_events\`. What follows is the measurement that justified it.` Keep the table; replace `**Why it was not chosen.**` paragraph's last sentence `For an application whose defining invariant ... wrong trade.` with `For an application whose defining invariant is that it reads narrowly and writes nothing, that is a trade the operator makes, not the chart: default off, the blast radius stated in values.yaml, narrowable to named nodes.` Replace `**If it is ever revisited**, the dedup key changes ...` paragraph with the as-built rule: auditID unique per cluster (\`gsd/store.py#login_event_by_audit_id\`), \`pod_name\` carrying the node, correspondence linking within \`gsd/auditlog.py#CORRESPONDENCE_SECONDS\`, the browser pair coalesced by path within \`ATTEMPT_WINDOW\`; and the sentence: **the audit log is authoritative once selected; the pod log is not read at all in that mode, and \`both\` is deliberately not offered because it would keep the Debug roll the audit source exists to retire.** Also amend `## Accepted limitation: the past cannot be reconstructed` with a final sentence: `That limitation is the pod-log source's. The audit source backfills to the oldest rotated file on first read, bounded by \`loginRetentionDays\` and drained at \`gsd/kube.py#AUDIT_READ_MAX_BYTES\` per node per cycle.` And in "Not recorded": `the audit event's query string (client_id, redirect_uri, PKCE challenge) — the path only.`
- **`docs/LOGIN_CAPTURE_QUICKCHECK.md`** — append `## 6. The audit-log source, in three commands`: `oc adm node-logs --role=master --path=oauth-server/` (expect `audit.log` and rotated names), `oc adm node-logs <node> --path=oauth-server/audit.log | jq 'select(.annotations["authentication.openshift.io/username"] != null) | {t:.stageTimestamp, u:.annotations["authentication.openshift.io/username"], d:.annotations["authentication.openshift.io/decision"], uri:.requestURI}'` (expect the five test logins), and the SA-token proof: `curl -sk -H "Authorization: Bearer $TOK" "$API/api/v1/nodes/<node>/proxy/logs/oauth-server/audit.log" -H 'Range: bytes=0-999'` — expect `206` (or `200`; both are handled, note which you saw) — with `oc auth can-i get nodes --subresource=proxy --as=$SA` yes / `oc auth can-i list pods -n openshift-authentication --as=$SA` no when `source=audit-log`. Add a row to "If you see nothing": `source is audit-log and every node reports no audit files → apiserver.config.openshift.io/cluster spec.audit.profile is None, which switches the oauth-server's audit log off`.
- **`docs/ACCESS_CONTROL.md`** — Logins row in §2: append `; with \`loginCapture.source: audit-log\`, \`oc adm node-logs --path=oauth-server/audit.log\`, which needs \`get nodes/proxy\` (cluster-admin / node-admin) — still nothing the wide tier's \`cluster-reader\` cannot read`.
- **`docs/reference-architecture.md`** §7.1 — after the `templates/rbac.yaml` table add: `A third role, on the dashboard's own ServiceAccount and only when \`loginCapture.source: audit-log\` (\`templates/login-capture-rbac.yaml#nodes/proxy\`): \`get nodes/proxy\` (optionally \`resourceNames\`) and \`list nodes\`. Read-only and cluster-wide — read access to everything the kubelet serves over GET on those nodes — which is why it is the one grant in this chart whose default is off for breadth rather than for writing.`
- **`README.md`** line 70 sentence `Read from the oauth-server pod log, which names the person only at Debug` → `Read from the oauth-server pod log (names the person only at Debug) or, with \`loginCapture.source: audit-log\`, from the oauth-server audit log on the control-plane nodes — no Debug, and history back to the rotated files`.
- **`docs/CHANGELOG.md`** entry:

```markdown
## Application 0.13.0 — chart 0.12.0 — 2026-09-04

- **Login capture from the oauth-server audit log.** `loginCapture.source: audit-log` reads
  `/var/log/oauth-server/audit.log` on the control-plane nodes through the API server's node
  proxy — what `oc adm node-logs --path=oauth-server/audit.log` does — at the default verbosity,
  so the `authLogLevel` Jobs and their OAuth roll can be retired, and a first read backfills as
  far as the rotated files reach (bounded by `retentionDays`, drained at 8 MiB per node per
  cycle). One event per attempt with an `auditID`, so de-duplication is exact; an event that
  corresponds to a pod-log row already stored is linked to it rather than recorded twice, and the
  row keeps its LDAP cause. `deny` carries no cause and the provider is named only for browser
  logins — the Logins tab says so. New outcome `provider_error` for the audit log's `error`.
  Schema migration 8. Two new metric families, `gsd_login_capture_source_info{cluster,source}`
  and `gsd_login_capture_audit_settled_timestamp_seconds{cluster,node}`; the stalled alert and
  its gauge are untouched. (design `DESIGN_login_capture.md`)
- **Chart 0.12.0:** `loginCapture.source`, `loginCapture.auditLog.nodeSelector`/`.nodeNames`; with
  `audit-log` a ClusterRole on `get nodes/proxy` (+ `list nodes`, or `resourceNames`) renders
  instead of the namespaced Role — read-only, cluster-wide, off by default, its breadth stated in
  values. `source=audit-log` with `authLogLevel.enabled=true` is refused: the chart will not roll
  the OAuth server as a side effect of a read setting. Default renders are byte-identical.
```

## D1.12 Verification

```bash
cd local-development && python -m pytest -q tests/test_auditlog.py tests/test_logincapture_loop.py tests/test_login_capture.py tests/test_login_capture_cross_seam.py tests/test_migrations.py tests/test_metrics.py tests/test_chart_strategy.py tests/test_config.py tests/test_api_contract.py tests/test_docs_citations.py tests/test_chart_versions.py
# expected: pass; test_a_fresh_database_lands_on_the_latest_migration reports 8

helm template t charts/group-sync-dashboard --set ingress.host=t.example.com --set loginCapture.enabled=true --set loginCapture.source=audit-log --set authLogLevel.manage=true --set authLogLevel.enabled=true
# expected: Error: ... loginCapture.source=audit-log and authLogLevel.enabled=true contradict each other ...

helm template ... --set loginCapture.enabled=true --set loginCapture.source=audit-log | grep -A6 'kind: ClusterRole' | grep -E 'nodes/proxy|resources: \["nodes"\]'
# expected: both lines; and no `kind: Role` with namespace openshift-authentication

# on CRC, after upgrade with source=audit-log (Debug already Normal):
oc logs -n group-sync-dashboard deploy/group-sync-dashboard -c dashboard | grep -i 'audit'
# expected: "crc-local: crc-master-0: audit.log read N byte(s) from offset 0 (first sight: backfill) — ..." then
#           "recorded N login attempt(s) from the audit log on crc-master-0 (audit.log), linked M to pod-log rows"
curl -sk https://<host>/api/clusters/crc-local/logins -H 'Authorization: Bearer <admin>' | jq '{source, capture_started_at, retained_since, total}'
# expected: source "audit-log", retained_since in 2025 (the backfill), total > the pod-log count
curl -sk https://<host>/metrics | grep -E 'gsd_login_capture_(source_info|audit_settled)'
```

**During implementation, replace the documented-shape fixtures**: capture `oc adm node-logs <node> --path=oauth-server/audit.log | tail -50` after the five QUICKCHECK logins, one browser login (to settle the one-vs-two-events question and the coalescing rule), and confirm the `Range` response code.

## D1.13 Risks and how they are closed

| risk | closed by |
|---|---|
| The grant is cluster-wide read | default `pod-log`; breadth stated in values, README, NOTES and reference-architecture §7.1; `nodeNames` narrows; the existing no-`pods/log`-ClusterRole test still holds |
| Switching source rolls the OAuth server by accident | render refusal on `audit-log` + `authLogLevel.enabled=true`; retirement order in the refusal text, values and NOTES |
| Double rows during migration | `auditID` unique index; correspondence link within 2 s (measured 16 ms); browser pair coalesced by path; tests for each |
| `Range` unsupported or proxied away | 200 handled by skipping `offset` bytes; correctness never depends on 206 |
| Rotation between cycles | 416 / short-body detection hands the cursor to the newest unread rotated name; test |
| Backfill stalls the poll thread | 8 MiB per node per cycle and `LOG_READ_BUDGET_SECONDS` per read; deferred, never dropped; test |
| Audit profile `None` | reported as "no audit files — is the audit profile None?" at INFO and no `last_read` stamp, so the stalled alert fires rather than the tab reading empty |
| `kubeadmin` CLI logins appear ungoverned | documented on the tab note, values and README; the Users tab's `providers` (from `User.identities`) is the corroborating source |
| Stalled alert breaks across the switch | `gsd_login_capture_last_read_timestamp_seconds{cluster}` unchanged; source rides a separate info family |

**Questions only the operator can answer:** (1) whether a cluster-wide `get nodes/proxy` on the dashboard's ServiceAccount is acceptable under their policy, or whether `nodeNames` pinning is required; (2) the cluster's `spec.audit.profile` (if `None`, the source cannot exist); (3) whether history predating the dashboard should be backfilled at all (`retentionDays` is the only bound — set it lower than 400 if not).

---

### Critical Files for Implementation
- /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/api.py
- /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/config.py
- /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/auditlog.py (new)
- /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/kube.py
- /Users/olasumbo/gitRepos/group-sync-dashboard/local-development/gsd/store.py
- /Users/olasumbo/gitRepos/group-sync-dashboard/charts/group-sync-dashboard/templates/_helpers.tpl (with `login-capture-rbac.yaml`, `configmap.yaml`, `values.yaml`)
