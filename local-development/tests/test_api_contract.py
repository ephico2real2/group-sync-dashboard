"""The API documents itself, and this makes that non-optional.

`docs/api-contract.md` states the rules; this file enforces them. A rule nobody checks is a
rule that lasts until the first hurried afternoon, and this repository has the receipts: an
endpoint shipped whose `(cluster-scoped)` sentinel was undiscoverable, a chart value went six
weeks undocumented, and a list endpoint was unbounded at three layers at once.

The rules are checked against the generated OpenAPI document rather than the source, because
that document is what a reader actually sees. Source can be well-commented and still produce
a schema that says nothing.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import re

import pytest

from gsd.api import build_app
from gsd.config import Settings

API_SRC = pathlib.Path(__file__).resolve().parents[1] / "gsd" / "api.py"
CONTRACT = pathlib.Path(__file__).resolve().parents[2] / "docs" / "api-contract.md"

# Not every path is an endpoint a reader consumes: the SPA shell and the three
# unauthenticated probe paths are infrastructure. They are listed rather than pattern-matched
# so that adding one is a visible decision.
# Not every path is an endpoint a reader consumes: the SPA shell, the three unauthenticated
# probe paths, the logout landing page and the sign-out action route are infrastructure.
# They are listed rather than pattern-matched so that adding one is a visible decision.
INFRASTRUCTURE = {"/", "/healthz", "/readyz", "/metrics", "/signed-out", "/sign-out"}


@pytest.fixture(scope="module")
def spec(tmp_path_factory) -> dict:
    db = str(tmp_path_factory.mktemp("contract") / "t.db")
    return build_app(Settings(db_path=db, clusters=[]), run_poller=False).openapi()


@pytest.fixture(scope="module")
def routes(spec) -> dict[str, dict]:
    """Documented endpoints, excluding infrastructure paths."""
    return {p: ops for p, ops in spec["paths"].items() if p not in INFRASTRUCTURE}


def test_the_contract_document_exists(spec):
    """The rules live next to the code, not in somebody's memory."""
    assert CONTRACT.exists(), f"{CONTRACT} is missing — the rules this file enforces"


def test_docs_are_published_under_api(spec):
    """R-location: the schema is authenticated exactly like the data it describes.

    oauthProxy.skipAuthRegex admits only the three probe paths, so anything under /api is
    behind the proxy. FastAPI's default /docs would be too, but naming it explicitly means a
    future upgrade that changes the default cannot quietly move the schema.
    """
    from fastapi.testclient import TestClient

    app = build_app(Settings(db_path=":memory:", clusters=[]), run_poller=False)
    # The ROUTES, not FastAPI's docs_url attribute. Those attributes are deliberately None:
    # the built-in handlers load Swagger UI and ReDoc from cdn.jsdelivr.net, so they are
    # replaced by handlers serving assets vendored into the image. Asserting the attribute
    # would have failed that improvement while proving nothing a reader cares about.
    assert app.openapi_url == "/api/openapi.json"
    with TestClient(app) as client:
        for path in ("/api", "/api/redoc", "/api/openapi.json"):
            assert client.get(path).status_code == 200, f"{path} is not served"


def test_the_docs_do_not_depend_on_the_internet(tmp_path):
    """A disconnected cluster must still render /api and /api/redoc.

    This chart pulls oauth-proxy from the cluster's internal registry, injects a trusted CA
    bundle and documents a disconnected-mirror override — it is built for clusters with no
    route out. FastAPI's stock docs handlers load their JS from cdn.jsdelivr.net, so before
    this they rendered a blank page there, and the dashboard itself is deliberately one
    self-contained file with no external assets.

    A source checkout has no vendored bundle and legitimately falls back to the CDN with a
    warning, so this asserts the wiring rather than the checkout: when the bundle is
    present, the pages reference it and not a CDN.
    """
    from fastapi.testclient import TestClient

    from gsd import api as api_mod

    vendor = pathlib.Path(api_mod.STATIC_DIR) / "vendor"
    vendor.mkdir(exist_ok=True)
    created = []
    for name in ("redoc.standalone.js", "swagger-ui-bundle.js", "swagger-ui.css"):
        f = vendor / name
        if not f.exists():
            f.write_text("/* test stub */")
            created.append(f)
    try:
        app = build_app(Settings(db_path=str(tmp_path / "t.db"), clusters=[]),
                        run_poller=False)
        with TestClient(app) as client:
            for path in ("/api", "/api/redoc"):
                html = client.get(path).text
                assert "cdn.jsdelivr.net" not in html, (
                    f"{path} still loads from a CDN with the vendored bundle present"
                )
                assert "/static/vendor/" in html, f"{path} does not use the vendored asset"
    finally:
        for f in created:
            f.unlink()
        if not any(vendor.iterdir()):
            vendor.rmdir()


def test_r1_every_endpoint_has_a_description(routes):
    """R1: the docstring becomes the description, and a bare path helps nobody."""
    missing = [
        f"{method.upper()} {path}"
        for path, ops in routes.items()
        for method, op in ops.items()
        if not (op.get("description") or "").strip()
    ]
    assert not missing, (
        "endpoints with no docstring: " + ", ".join(sorted(missing))
        + ". Add one — its first line becomes the summary in /api."
    )


def test_r1_the_summary_stands_alone(routes):
    """A summary that needs the body to make sense is not a summary.

    Catches the two habits that produce useless schemas: naming the handler instead of
    describing the result, and a first line that trails into the second.
    """
    bad = []
    for path, ops in routes.items():
        for method, op in ops.items():
            lines = (op.get("description") or "").strip().splitlines()
            first = lines[0].strip() if lines else ""
            # An absent description is R1's failure, not this one's — reporting it twice
            # makes the suite noisier without telling anyone anything new.
            if not first:
                continue
            if len(first) < 15 or first.lower().startswith(("handler", "endpoint", "get ")):
                bad.append(f"{method.upper()} {path}: {first!r}")
    assert not bad, (
        "summaries that do not describe the result: " + "; ".join(sorted(bad))
    )


def test_r2_every_query_parameter_is_described(routes):
    """R2: `namespace` looks self-evident and hides a sentinel value.

    /user-bindings?namespace=(cluster-scoped) is the only way to reach the cluster-scoped
    rows, because the stored value is '' and an absent parameter means "everything".
    """
    missing = [
        f"{method.upper()} {path} ?{param['name']}"
        for path, ops in routes.items()
        for method, op in ops.items()
        for param in op.get("parameters", [])
        if param.get("in") == "query" and not (param.get("description") or "").strip()
    ]
    assert not missing, (
        "query parameters with no description: " + ", ".join(sorted(missing))
        + ". Use Query(default=..., description=...)."
    )


def _handlers() -> dict[str, ast.FunctionDef]:
    """Route handlers defined inside build_app, by function name."""
    tree = ast.parse(API_SRC.read_text())
    build = next(n for n in tree.body
                 if isinstance(n, ast.FunctionDef) and n.name == "build_app")
    return {
        n.name: n
        for n in build.body
        if isinstance(n, ast.FunctionDef)
        and any("app.get" in ast.unparse(d) or "app.post" in ast.unparse(d)
                for d in n.decorator_list)
    }


def test_r3_a_paged_response_admits_when_it_is_partial():
    """R3: a `limit` with no `truncated` lets a short page look like the whole set.

    The requirement is the GUARANTEE, not a particular field. Two ways to satisfy it, both
    already in this codebase:

      * exact — count before the limit and return `total` (user-bindings, activity). Needed
        when a caller computes a headline from the response, because a KPI has to state a
        number rather than a hedge;
      * cheap — ask the store for `limit + 1` rows and return `truncated` (list_users).
        Enough when the reader only needs to know more exists, and it avoids a COUNT over a
        table that grows with the directory.

    Broken twice before this test existed. The direct-grant list was unbounded at the store,
    the API and the renderer simultaneously; the activity endpoint capped at 500 rows while
    the Usage tab reported 167 days where the truth was 364.
    """
    src = API_SRC.read_text()
    offenders = []
    for name, node in _handlers().items():
        body = ast.get_source_segment(src, node) or ""
        takes_limit = re.search(r"\blimit\s*:\s*int\s*=\s*Query", body)
        if takes_limit and '"total"' not in body and '"truncated"' not in body:
            offenders.append(name)
    assert not offenders, (
        "handlers taking `limit` but reporting neither `total` nor `truncated`: "
        + ", ".join(sorted(offenders))
        + ". A response that silently drops rows cannot be told apart from a complete one."
    )


def test_r5_multi_store_handlers_take_a_snapshot():
    """R5: two store calls in one handler are two points in time without @consistent."""
    src = API_SRC.read_text()
    offenders = []
    for name, node in _handlers().items():
        body = ast.get_source_segment(src, node) or ""
        calls = len(re.findall(r"\bstore\.\w+\(", body))
        decorated = any("consistent" in ast.unparse(d) for d in node.decorator_list)
        if calls > 1 and not decorated:
            offenders.append(f"{name} ({calls} store calls)")
    assert not offenders, (
        "multi-call handlers without @consistent: " + ", ".join(sorted(offenders))
        + ". Each call is its own snapshot, so the response can contradict itself."
    )


def test_r6_the_api_is_read_only(spec):
    """R6: the ServiceAccount is read-only by design, and the API should reflect that."""
    writes = [
        f"{method.upper()} {path}"
        for path, ops in spec["paths"].items()
        for method in ops
        if method.lower() not in {"get", "head", "options"}
    ]
    assert not writes, (
        "non-GET endpoints: " + ", ".join(sorted(writes))
        + ". See docs/unmanaged-audit-design.md before adding a write path."
    )


def test_r7_hidden_routes_are_explained():
    """R7: a route missing from the schema is invisible to everyone who trusts it."""
    src = API_SRC.read_text()
    for match in re.finditer(r"include_in_schema=False", src):
        # A window either side: the reason may be a comment block above the decorator or the
        # handler's own docstring just below it. Both are explanations a reader will find.
        window = src[max(0, match.start() - 700):match.start() + 400]
        assert re.search(r"#[^\n]*\n|\"\"\"", window), (
            "include_in_schema=False with no nearby comment or docstring explaining why"
        )


def test_the_alias_redirects_rather_than_duplicating(tmp_path):
    """/api/docs and /api must never render two different schemas."""
    from fastapi.testclient import TestClient

    app = build_app(Settings(db_path=str(tmp_path / "t.db"), clusters=[]), run_poller=False)
    with TestClient(app) as client:
        alias = client.get("/api/docs", follow_redirects=False)
        assert alias.status_code == 308
        assert alias.headers["location"] == "/api"
        assert client.get("/api").status_code == 200

def test_every_endpoint_appears_in_api_md(spec):
    """API.md must name every route, or it quietly becomes a partial map.

    It had drifted by six: /user-bindings, /operator-configs, /whoami,
    /dashboard/activity and the two docs-UI routes. The first is the one that mattered — its
    `(cluster-scoped)` namespace sentinel is the only way to reach the cluster-wide rows and
    is not guessable, so an undocumented endpoint there is an unusable one.

    Checked against the generated spec rather than the source, so a route that exists only in
    a comment does not count, and matched on the literal path so a rename fails loudly.
    """
    api_md = pathlib.Path(__file__).resolve().parents[1] / "API.md"
    assert api_md.exists(), f"{api_md} is missing"
    text = api_md.read_text()
    missing = [p for p in sorted(spec["paths"]) if p not in text]
    assert not missing, (
        "endpoints absent from API.md: " + ", ".join(missing)
        + ". Document them, or a reader trusts an incomplete reference."
    )
