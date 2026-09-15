# gsd-mock — a fixture-driven mock OpenShift API for group-sync-dashboard

A self-contained HTTP(S) server that answers **exactly the request surface `gsd/kube.py`
issues** — the ~16 read endpoints, the two node-log-proxy shapes, the pod-log stream, and the
SubjectAccessReview POST — from one declarative YAML fixture. It is portable (pure Python, a
`cryptography`-only extra for TLS; no cluster, no VM, no container runtime for the CI/local
form), faithful (every response satisfies the parse contract in `gsd/kube.py` so the client
reaches its real code paths), and a **real RBAC authorizer** for SAR (the four measured
personas resolve to their measured tiers from fixture `(Cluster)RoleBinding`→`(Cluster)Role`
rules, not a hardcoded answer map).

See `../mock-plan/DESIGN_mock_cluster.md` (GitHub issue #116) for the full contract.

> **Scope.** This mock is wired to the **dashboard/poller only.** The report service needs
> nothing from it — its inputs are a snapshot SQLite file and the local ArtifactStore, and it
> never imports `kube`/`ClusterClient`/`ClusterConfig`. To integration-test the report you seed
> a `gsd-<stamp>.db` snapshot, not this mock.

## Layout

```
mock-app/
├── mock_app/
│   ├── app.py        FastAPI app + every route (a–p) + /_mock/*
│   ├── server.py     MockClusterServer: uvicorn + ephemeral-TLS lifecycle
│   ├── __main__.py   `python -m mock_app` CLI (container / lab form)
│   ├── fixture.py    typed dataclasses + from_yaml() loader/validator
│   ├── responses.py  k8s List/object envelopes; limit/continue paging; per-item shapes
│   ├── sar.py        SarAuthorizer: RBAC evaluation over the fixture
│   ├── auditlog.py   AuditServer: shorthand→audit JSON, HTML listing, Range/416
│   ├── podlog.py     pod-log text stream
│   ├── tls.py        ephemeral CA + serving leaf via `cryptography`
│   ├── inspect.py    /_mock/ HTML page + /_mock/state + request-log ring buffer
│   └── errors.py     forbidden_403(path) / crd_absent_404(path) / status_json
├── fixtures/         reference.yaml, crd-absent.yaml, forbidden.yaml, paging.yaml
├── containerfile/    Containerfile + entrypoint.sh (uvicorn on :6443, TLS)
├── tests/            conftest + request-surface / SAR-oracle / TLS / audit / poll-e2e
└── .github/workflows/mock-cluster.yml
```

## The two run forms

### Form A — in-process pytest fixture (CI + local)

The `mock_cluster` fixture (`tests/conftest.py`) starts the server on an **ephemeral port**
with a **fresh CA**, writes `ca.crt`, and yields a handle. A test builds a real
`ClusterConfig(ca_bundle_file=ca.crt)` and drives a real `ClusterClient` /
`poll_once` / `TierResolver` over **real verified TLS** — the coverage `httpx.MockTransport`
cannot give. Ephemeral port → parallel-safe.

```bash
cd local-development
python -m pip install -e .                 # the dashboard: gsd.ClusterClient / ClusterConfig
python -m pip install -e 'mock-app[test]'
pytest mock-app/tests -q
```

### Form B — container on :6443 (lab e2e)

```bash
cd local-development/mock-app
podman build -f containerfile/Containerfile -t mock-openshift .
mkdir -p out
podman run --rm -p 6443:6443 -v ./fixtures:/fixtures:ro -v ./out:/out mock-openshift
# CA is written to ./out/ca.crt; point the dashboard's clusters[0].caBundleFile at it.

curl --cacert out/ca.crt https://localhost:6443/_mock/state
curl --cacert out/ca.crt -H 'Authorization: Bearer mock-token-reference' \
     https://localhost:6443/apis/user.openshift.io/v1/groups
```

Or run it directly:

```bash
python -m mock_app --fixture fixtures/reference.yaml --host 0.0.0.0 --port 6443 \
    --tls --ca-out out/ca.crt --sans DNS:mock-openshift,DNS:localhost,IP:127.0.0.1
```

Point the dashboard's ConfigMap at it:

```yaml
clusters:
  - name: mock
    apiUrl: https://mock-openshift:6443
    tokenFile: /etc/gsd/mock-token          # contents = meta.token from the fixture
    caBundleFile: /etc/gsd/mock-ca/ca.crt    # the generated CA
```

## The CA / TLS model

The mock drives the **real** trust path in `config.py::verify()` —
`ssl.create_default_context(cafile=…)` with `CERT_REQUIRED` + hostname checking ON — not
`insecure_skip_verify`. The leaf carries a SAN matching the host in `api_url`
(`IP:127.0.0.1` / `DNS:localhost` in-process, `DNS:mock-openshift` in a container).

| Mode | How | Fixture / config |
|---|---|---|
| **2 — per-cluster bundle (default)** | `caBundleFile = ca.crt` | `handle.cluster_config()` |
| **3 — injected/enterprise fallback** | `GSD_TRUSTED_CA_FILE=ca.crt`, `ca_bundle_file=None` | `cluster_config(use_trusted_ca_env=True, ca_bundle=None)` |
| **negative control** | no CA anywhere → system trust → verify fails | `cluster_config(ca_bundle=None)` → `UNREACHABLE` |
| **escape hatch** | `insecure_skip_verify=True` → verify off | `cluster_config(insecure=True)` |

> **Cache gotcha (mode 3):** `gsd.config._ca_cache` is keyed on the raw env string and never
> caches a null result. A matrix reusing the same `GSD_TRUSTED_CA_FILE` value across cases with
> different CA contents serves a stale context — clear the cache (the fixtures do so in teardown).

## The SAR oracle

`spec.groups` is pre-resolved by the client (byte-exact Group memberships + virtual
`system:*` groups); the authorizer takes it as given and evaluates the fixture RBAC. Only
`status.allowed` (a real JSON boolean) is read; anything else fails the client closed to `self`.

| Persona | fixture RBAC | `list clusterrolebindings` (wide) | `update clusterrolebindings` (usage) |
|---|---|---|---|
| `kubeadmin` | `cluster-admin` CRB | ALLOW | ALLOW |
| `dana.lee` | `cluster-reader` CRB (read verbs, no `update`) | ALLOW | DENY |
| `lateef.o` | no admin CRB | DENY | DENY |
| `jane.smith` | in a group **named** `…-cluster-admin` with **no CRB behind it** | DENY | DENY |

`jane.smith` is the key negative fixture: a suggestively-named group must not grant the tier —
only a real `(Cluster)RoleBinding` reaching a `spec.groups`/`spec.user` subject does.

## Fixture format

One YAML file (JSON accepted); unknown top-level keys are rejected (fail-loud). Top-level keys:
`meta`, `groupsyncs`, `groups`, `users`, `identities`, `namespaces`, `roles`, `bindings`,
`operatorConfigs`, `nodes`, `oauth`, `oauthPods`, `auditLog`, `podLog`. See
`fixtures/reference.yaml` for the annotated reference cluster, and:

- `crd-absent.yaml` — GroupSync/operator/OAuth CRDs missing (the plain-404 branches).
- `forbidden.yaml` — users/identities/namespaces/nodes/oauth/pods answer 403 (tolerated → None).
- `paging.yaml` — `meta.pageSize` caps the page below kube.py's `limit=500` to drive its real
  continue-token loop with a tiny fixture (a real API server may return fewer than the limit).

Audit `lines` are **shorthand** (`{kind, decision, user, at, code, provider?}`) that the audit
server expands into full Kubernetes-audit JSON events `gsd/auditlog.py::parse_audit_line`
accepts — you never hand-write the envelope. `kind` ∈ `credential` (`/login`), `cli`
(`/oauth/authorize?client_id=openshift-challenging-client`), `session` (any other `client_id`).

## The `/_mock/*` control surface

Unauthenticated (it is a test tool), under a reserved prefix that never shadows a kube path:

- `GET /_mock/` — the fixture at a glance, a **live request log** (see the poller's traffic), and
  a **SAR probe** form (user + verb → computed allow/deny + the granting binding).
- `GET /_mock/state` — JSON `{fixture_summary, recent_requests, sar_cache_note}`.
- `POST /_mock/sar-probe` — `{user, verb, resource, group, namespace?}` → verdict + binding.
- `POST /_mock/reload` — re-read the fixture file and rebuild state (iterate in the lab).

## What makes kube.py parse without error

- Every JSON endpoint answers **200**, never a 3xx (the app sets `redirect_slashes=False`).
- Every LIST body carries an `items` key (array or null); `metadata.continue` only when a next
  page exists.
- The OAuth CR is a plain object with `spec.identityProviders` (no `items`).
- SAR returns `{"status":{"allowed": <bool>}}` with 201.
- Node-log endpoints honour `Accept: */*` (answer 406 to bare `application/json`), serve the
  directory as HTML with `<a href>` entries, and answer `416` + `Content-Range: bytes */<size>`
  at/after EOF; HEAD → 405.
- The Bearer gate requires `Authorization: Bearer <meta.token>`; a wrong/missing token → 401.
