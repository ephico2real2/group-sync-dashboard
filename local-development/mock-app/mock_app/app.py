"""The FastAPI application — every path kube.py issues, plus the /_mock/* control surface.

Routing is deliberately explicit and ordered: the reserved ``/_mock/*`` prefix first, then the
exact API paths, then the two templated node-proxy shapes. ``redirect_slashes`` is OFF so a
trailing-slash mismatch never becomes a 3xx — kube.py treats any <400 non-JSON as UNREACHABLE
(DESIGN §3.1), so every JSON endpoint must answer 200, never a redirect.

Each handler consults the fixture's ``forbidden`` / ``crd_absent`` flags and calls the helpers
in ``errors.py`` to reach kube.py's tolerated branches on purpose.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response

from . import errors
from .auditlog import AuditServer, parse_range
from .fixture import Fixture
from .inspect import RequestLog, render_page, state_json
from .responses import (
    binding_item,
    group_item,
    groupsync_item,
    identity_item,
    k8s_list,
    namespace_item,
    node_item,
    oauth_object,
    operator_config_item,
    paginate,
    user_item,
)
from .sar import SarAuthorizer

# ── Paths (verbatim from gsd/kube.py) ─────────────────────────────────────────────────────
GROUPSYNC_API = "/apis/redhatcop.redhat.io/v1alpha1/groupsyncs"
GROUP_API = "/apis/user.openshift.io/v1/groups"
USER_API = "/apis/user.openshift.io/v1/users"
IDENTITY_API = "/apis/user.openshift.io/v1/identities"
NAMESPACE_API = "/api/v1/namespaces"
ROLEBINDING_API = "/apis/rbac.authorization.k8s.io/v1/rolebindings"
CLUSTERROLEBINDING_API = "/apis/rbac.authorization.k8s.io/v1/clusterrolebindings"
NAMESPACECONFIG_API = "/apis/redhatcop.redhat.io/v1alpha1/namespaceconfigs"
GROUPCONFIG_API = "/apis/redhatcop.redhat.io/v1alpha1/groupconfigs"
NODE_API = "/api/v1/nodes"
OAUTH_API = "/apis/config.openshift.io/v1/oauths/cluster"
SAR_API = "/apis/authorization.k8s.io/v1/subjectaccessreviews"

VIRTUAL_AUTH_GROUPS = ("system:authenticated", "system:authenticated:oauth")
SERVICEACCOUNT_PREFIX = "system:serviceaccount:"


# ── Helpers ────────────────────────────────────────────────────────────────────────────────


def _virtual_groups_for(viewer: str) -> tuple[str, ...]:
    """Mirror kube.py::_virtual_groups_for so the /_mock/ probe matches the real SAR input."""
    if viewer.startswith(SERVICEACCOUNT_PREFIX):
        parts = viewer.split(":")
        if len(parts) == 4 and parts[2] and parts[3]:
            return ("system:serviceaccounts", f"system:serviceaccounts:{parts[2]}",
                    "system:authenticated")
    return VIRTUAL_AUTH_GROUPS


def groups_for_user(fixture: Fixture, user: str) -> list[str]:
    """The union kube.py sends as spec.groups: byte-exact Group memberships + virtual groups.

    Byte-exact because OpenShift User names are case-sensitive (kube.py::fetch_groups_of_user).
    Used only by the /_mock/ SAR probe — the real SAR carries its own pre-resolved groups.
    """
    memberships = sorted(
        g.name
        for g in fixture.groups
        if g.users and any(str(m) == user for m in g.users)
    )
    return [*memberships, *_virtual_groups_for(user)]


def _limit(request: Request) -> int:
    raw = request.query_params.get("limit")
    try:
        return int(raw) if raw is not None else 500
    except ValueError:
        return 500


def _cursor(request: Request) -> str | None:
    return request.query_params.get("continue")


def _accepts_wildcard(request: Request) -> bool:
    """Whether the client will accept a non-JSON body (Accept contains */* or is absent).

    The node-log proxy answers 406 to a bare ``application/json`` — the failure this code was
    written around (kube.py:447-452). kube.py sends ``Accept: */*`` for node-log calls only.
    """
    accept = request.headers.get("accept", "")
    if not accept:
        return True
    return "*/*" in accept or "text/html" in accept or "text/plain" in accept


def _selector_matches(labels: dict[str, str], selector: str) -> bool:
    """Match a Kubernetes label selector: ``key``, ``key=value`` (``key=`` → empty value),
    ``key!=value``, comma-separated AND terms. Enough for the control-plane node selector
    (``node-role.kubernetes.io/master=``)."""
    if not selector:
        return True
    for term in selector.split(","):
        term = term.strip()
        if not term:
            continue
        if "!=" in term:
            key, _, val = term.partition("!=")
            if labels.get(key.strip()) == val.strip():
                return False
        elif "=" in term:
            key, _, val = term.partition("=")
            if labels.get(key.strip()) != val.strip():
                return False
        else:
            if term not in labels:
                return False
    return True


# ── Application factory ──────────────────────────────────────────────────────────────────


def build_app(fixture: Fixture) -> FastAPI:
    app = FastAPI(title=f"mock-openshift ({fixture.cluster_name})", redirect_slashes=False)

    state = app.state
    state.fixture = fixture
    state.sar = SarAuthorizer(fixture)
    state.audit = AuditServer(fixture.audit)
    state.reqlog = RequestLog()

    def authorized(request: Request) -> bool:
        expected = f"Bearer {state.fixture.token}"
        return request.headers.get("authorization", "") == expected

    def list_response(request: Request, items: list[dict], kind: str, endpoint: str) -> Response:
        # A real API server MAY return fewer than the requested limit. `meta.pageSize` caps the
        # page below kube.py's fixed limit=500 so a tiny fixture still drives its continue loop.
        effective = _limit(request)
        if state.fixture.page_size is not None:
            effective = min(effective, state.fixture.page_size)
        page, next_cursor = paginate(items, effective, _cursor(request))
        request.state.endpoint = endpoint
        return JSONResponse(k8s_list(page, kind=kind, continue_token=next_cursor))

    # ── request-log middleware ─────────────────────────────────────────────────────────────
    @app.middleware("http")
    async def _record(request: Request, call_next):
        request.state.endpoint = "-"
        response = await call_next(request)
        try:
            length = int(response.headers.get("content-length", 0))
        except (TypeError, ValueError):
            length = 0
        endpoint = getattr(request.state, "endpoint", "-")
        if not request.url.path.startswith("/_mock"):
            state.reqlog.record(request.method, request.url.path, response.status_code,
                                endpoint, length)
        return response

    # ── auth gate for the kube API surface ──────────────────────────────────────────────────
    # Applied inside each API handler via `authorized(request)`; /_mock/* is exempt.

    def gate(request: Request):
        if not authorized(request):
            request.state.endpoint = "auth"
            return errors.unauthorized_401()
        return None

    # ── (a) GroupSync CRs ───────────────────────────────────────────────────────────────────
    @app.get(GROUPSYNC_API)
    def groupsyncs(request: Request):
        if (r := gate(request)) is not None:
            return r
        if state.fixture.groupsyncs_crd_absent:
            request.state.endpoint = "a"
            return errors.crd_absent_404(GROUPSYNC_API)
        items = [groupsync_item(g) for g in state.fixture.groupsyncs]
        return list_response(request, items, "GroupSyncList", "a")

    # ── (b) Groups ──────────────────────────────────────────────────────────────────────────
    @app.get(GROUP_API)
    def groups(request: Request):
        if (r := gate(request)) is not None:
            return r
        items = [group_item(g) for g in state.fixture.groups]
        return list_response(request, items, "GroupList", "b")

    # ── (c) Users ───────────────────────────────────────────────────────────────────────────
    @app.get(USER_API)
    def users(request: Request):
        if (r := gate(request)) is not None:
            return r
        if state.fixture.users.forbidden:
            request.state.endpoint = "c"
            return errors.forbidden_403(USER_API)
        items = [user_item(u) for u in state.fixture.users.entries]
        return list_response(request, items, "UserList", "c")

    # ── (d) Identities ──────────────────────────────────────────────────────────────────────
    @app.get(IDENTITY_API)
    def identities(request: Request):
        if (r := gate(request)) is not None:
            return r
        if state.fixture.identities.forbidden:
            request.state.endpoint = "d"
            return errors.forbidden_403(IDENTITY_API)
        items = [identity_item(i) for i in state.fixture.identities.entries]
        return list_response(request, items, "IdentityList", "d")

    # ── (e) Namespaces ──────────────────────────────────────────────────────────────────────
    @app.get(NAMESPACE_API)
    def namespaces(request: Request):
        if (r := gate(request)) is not None:
            return r
        if state.fixture.namespaces.forbidden:
            request.state.endpoint = "e"
            return errors.forbidden_403(NAMESPACE_API)
        items = [namespace_item(n) for n in state.fixture.namespaces.entries]
        return list_response(request, items, "NamespaceList", "e")

    # ── (f) RoleBindings ────────────────────────────────────────────────────────────────────
    @app.get(ROLEBINDING_API)
    def rolebindings(request: Request):
        if (r := gate(request)) is not None:
            return r
        items = [binding_item(b, "RoleBinding") for b in state.fixture.role_bindings]
        return list_response(request, items, "RoleBindingList", "f")

    # ── (g) ClusterRoleBindings ──────────────────────────────────────────────────────────────
    @app.get(CLUSTERROLEBINDING_API)
    def clusterrolebindings(request: Request):
        if (r := gate(request)) is not None:
            return r
        items = [binding_item(b, "ClusterRoleBinding") for b in state.fixture.cluster_role_bindings]
        return list_response(request, items, "ClusterRoleBindingList", "g")

    # ── (h) NamespaceConfigs ─────────────────────────────────────────────────────────────────
    @app.get(NAMESPACECONFIG_API)
    def namespaceconfigs(request: Request):
        if (r := gate(request)) is not None:
            return r
        oc = state.fixture.operator_configs
        if oc.namespace_configs_crd_absent:
            request.state.endpoint = "h"
            return errors.crd_absent_404(NAMESPACECONFIG_API)
        items = [operator_config_item(c.name, c.conditions, "NamespaceConfig")
                 for c in oc.namespace_configs]
        return list_response(request, items, "NamespaceConfigList", "h")

    # ── (i) GroupConfigs ─────────────────────────────────────────────────────────────────────
    @app.get(GROUPCONFIG_API)
    def groupconfigs(request: Request):
        if (r := gate(request)) is not None:
            return r
        oc = state.fixture.operator_configs
        if oc.group_configs_crd_absent:
            request.state.endpoint = "i"
            return errors.crd_absent_404(GROUPCONFIG_API)
        items = [operator_config_item(c.name, c.conditions, "GroupConfig")
                 for c in oc.group_configs]
        return list_response(request, items, "GroupConfigList", "i")

    # ── (j) Nodes ────────────────────────────────────────────────────────────────────────────
    @app.get(NODE_API)
    def nodes(request: Request):
        if (r := gate(request)) is not None:
            return r
        if state.fixture.nodes.forbidden:
            request.state.endpoint = "j"
            return errors.forbidden_403(NODE_API)
        selector = request.query_params.get("labelSelector", "")
        matched = [n for n in state.fixture.nodes.entries if _selector_matches(n.labels, selector)]
        items = [node_item(n) for n in matched]
        return list_response(request, items, "NodeList", "j")

    # ── (k) OAuth CR (single object, no items) ───────────────────────────────────────────────
    @app.get(OAUTH_API)
    def oauth_cr(request: Request):
        if (r := gate(request)) is not None:
            return r
        request.state.endpoint = "k"
        if state.fixture.oauth.forbidden:
            return errors.forbidden_403(OAUTH_API)
        if state.fixture.oauth.crd_absent:
            return errors.crd_absent_404(OAUTH_API)
        return JSONResponse(oauth_object(state.fixture.oauth))

    # ── (n)+(o) Node-log proxy ───────────────────────────────────────────────────────────────
    @app.api_route("/api/v1/nodes/{node}/proxy/logs/{subpath:path}",
                   methods=["GET", "HEAD"])
    def node_log(request: Request, node: str, subpath: str):
        if (r := gate(request)) is not None:
            return r
        # HEAD is never issued by the client; the real node proxy answers it 405.
        if request.method == "HEAD":
            request.state.endpoint = "o"
            return Response(status_code=405)
        # The node proxy answers 406 to application/json — only */* returns bytes/HTML.
        if not _accepts_wildcard(request):
            request.state.endpoint = "n"
            return PlainTextResponse("406 Not Acceptable", status_code=406)

        audit = state.audit
        if node != state.fixture.audit.node:
            request.state.endpoint = "o"
            return errors.not_found_404(request.url.path)

        # A trailing slash → a directory listing (endpoint n); else a file read (endpoint o).
        if subpath.endswith("/"):
            request.state.endpoint = "n"
            directory = subpath.rstrip("/").rsplit("/", 1)[-1]
            if directory != state.fixture.audit.directory:
                return errors.not_found_404(request.url.path)
            return HTMLResponse(content=audit.listing_html(), media_type="text/html")

        request.state.endpoint = "o"
        filename = subpath.rsplit("/", 1)[-1]
        if not audit.has_file(filename):
            return errors.not_found_404(request.url.path)
        rng = parse_range(request.headers.get("range"))
        result = audit.read(filename, rng)
        return Response(content=result.body, status_code=result.status, headers=result.headers)

    # ── (p) SubjectAccessReview (POST) ───────────────────────────────────────────────────────
    @app.post(SAR_API)
    async def subject_access_review(request: Request):
        if (r := gate(request)) is not None:
            return r
        request.state.endpoint = "p"
        try:
            body = await request.json()
        except Exception:
            return JSONResponse(status_code=400, content={"message": "invalid JSON body"})
        spec = (body or {}).get("spec") or {}
        user = spec.get("user", "")
        groups = list(spec.get("groups") or [])
        attrs = spec.get("resourceAttributes") or {}
        allowed = state.sar.review(user, groups, attrs)
        # 201 mirrors the real API server (a SAR is a create-shaped query); kube.py accepts
        # any <400 and reads only status.allowed, which MUST be a real JSON boolean.
        return JSONResponse(
            status_code=201,
            content={
                "apiVersion": "authorization.k8s.io/v1",
                "kind": "SubjectAccessReview",
                "status": {"allowed": bool(allowed)},
            },
        )

    # ── /_mock/* control + inspection (no Bearer gate) ───────────────────────────────────────
    @app.get("/_mock/", response_class=HTMLResponse)
    @app.get("/_mock", response_class=HTMLResponse)
    def mock_index():
        return HTMLResponse(render_page(state.fixture, state.reqlog))

    @app.get("/_mock/state")
    def mock_state():
        return JSONResponse(state_json(state.fixture, state.reqlog))

    @app.post("/_mock/sar-probe")
    async def mock_sar_probe(request: Request):
        data = await request.json()
        user = data.get("user", "")
        groups = groups_for_user(state.fixture, user)
        attrs: dict[str, Any] = {
            "verb": data.get("verb", "list"),
            "resource": data.get("resource", "clusterrolebindings"),
            "group": data.get("group", "rbac.authorization.k8s.io"),
        }
        if data.get("namespace"):
            attrs["namespace"] = data["namespace"]
        if data.get("subresource"):
            attrs["subresource"] = data["subresource"]
        allowed, binding = state.sar.explain(user, groups, attrs)
        return JSONResponse({"allowed": allowed, "binding": binding, "groups": groups})

    @app.post("/_mock/reload")
    def mock_reload():
        """Re-read the fixture from disk and rebuild server state — iterate in the lab without a
        restart (DESIGN §9). Only works when the fixture was loaded from a file."""
        path = state.fixture.source_path
        if not path:
            return JSONResponse(status_code=409,
                                content={"reloaded": False, "reason": "fixture has no source file"})
        fresh = Fixture.from_yaml(path)
        state.fixture = fresh
        state.sar = SarAuthorizer(fresh)
        state.audit = AuditServer(fresh.audit)
        return JSONResponse({"reloaded": True, "summary": fresh.summary()})

    @app.get("/healthz")
    @app.get("/livez")
    @app.get("/readyz")
    def healthz():
        return PlainTextResponse("ok")

    return app
