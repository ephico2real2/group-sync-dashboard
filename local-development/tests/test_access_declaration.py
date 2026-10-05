"""The access declaration (#239, docs/specs/SPEC_G1_tier_declaration.md): `docs/guides/ACCESS_CONTROL.md` §3 and §4 say
which tier every page and every route gives each reader, and this module holds both to the code.

What fails here, each the way the declaration was measured drifting (five routes and four tabs behind on 5c03a9b1):

* a route the app registers with no §4 row, a row for a route the app does not serve, or a row whose `registered`
  word disagrees with the writes switch (T239-1, T239-2, T239-7). The routes come from `app.routes`, built with every
  switch that registers one, never from the OpenAPI schema: the schema leaves out the five `include_in_schema=False`
  routes, FastAPI's own `/api/openapi.json` and the `/static` mount;
* a route that answers a persona differently from its row (T239-3, T239-9). Every row is requested by each of the five
  personas through the seams build_app publishes, so a gate dropped, swapped or moved to a lower tier turns a cell
  red: the mutant that moves `/api/kpi` to `require_admin_tier` fails on the auditor (T239-6);
* a row whose `gate` the handler does not call;
* a tab or page `gsd/static/index.html` can draw with no §3 row, or a §3 row for nothing it draws (T239-4).

The browser half, each persona's tab strip and refusal cards against §3, is tests/test_ui.py's TestTheDeclaredTabs
(T239-5).
"""

from __future__ import annotations

import inspect
import pathlib
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import Mount

import gsd.api
from gsd.api import build_app
from test_visibility import H, _MapResolver, _seed, _settings

REPO = pathlib.Path(__file__).resolve().parents[2]
DOC = REPO / "docs" / "guides" / "ACCESS_CONTROL.md"
PAGE = REPO / "local-development" / "gsd" / "static" / "index.html"

#: The one reader every persona but the first is. The seed makes her a member of g-adm, a user with a grant in ns1,
#: so a route naming her own group, user or namespace answers its narrowed 200 rather than "not yours".
VIEWER = "alice"

#: §4's reader columns, and what makes each: the answers of the wide, usage and cluster-admin seams for VIEWER.
#: Each persona passes exactly its own question; `None` sends no identity at all.
ROUTE_PERSONAS: dict[str, tuple[dict, dict, dict] | None] = {
    "no identity": None,
    "self": ({}, {}, {}),
    "auditor": ({VIEWER: "all"}, {}, {}),
    "usage": ({}, {VIEWER: "all"}, {}),
    "cluster-admin": ({}, {}, {VIEWER: "all"}),
}
ROUTE_WORDS = frozenset({"all", "self", "200", "403", "308", "admitted"})
PAGE_PERSONAS = ("self", "auditor", "usage", "cluster-admin")
PAGE_WORDS = frozenset({"all", "self", "refused", "absent"})
GATES = ("viewer_scope", "usage_scope", "require_admin_tier", "require_cluster_admin", "_writes_gate",
         "_housekeeping_gate", "_housekeeping_write")

#: The value each path parameter takes. `{name}` is keyed by the segment before it; a new parameter fails `_url` by
#: name until it is given one here.
PATH_VALUES = {"cluster_id": "c1", "groups": "g-adm", "users": VIEWER, "namespaces": "ns1",
               "groupsyncs": "ldap-sync", "clusterconfigs": "c1", "path": "app.css",
               "kind": "backup", "copies": "gsd-20260101T000000.000000Z.db", "run_id": "20260101T000000.000000Z-r1"}


def _section(number: int) -> str:
    text = DOC.read_text()
    head = re.search(rf"^## {number}\. .*$", text, re.M)
    assert head, f"docs/guides/ACCESS_CONTROL.md has no section {number}"
    rest = text[head.end():]
    following = re.search(r"^## ", rest, re.M)
    return rest[:following.start()] if following else rest


def _table(section: str, header: tuple[str, ...]) -> list[dict[str, str]]:
    """The rows of the one table in `section` whose header row starts with `header`, backticks stripped."""
    lines = section.split("\n")
    lead = "| " + " | ".join(header) + " |"
    starts = [i for i, line in enumerate(lines) if line.startswith(lead)]
    assert len(starts) == 1, f"expected one table headed {lead!r}, found {len(starts)}"
    columns = [c.strip() for c in lines[starts[0]].strip().strip("|").split("|")]
    rows = []
    for line in lines[starts[0] + 2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip().replace("`", "") for c in line.strip().strip("|").split("|")]
        assert len(cells) == len(columns), f"{len(cells)} cells under {len(columns)} columns: {line}"
        rows.append(dict(zip(columns, cells)))
    assert rows, f"the table headed {lead!r} has no rows"
    return rows


ROUTES = _table(_section(4), ("method", "path", "registered", "gate", *ROUTE_PERSONAS))
OTHER_SERVICES = _table(_section(4), ("path", "served by"))
PAGES = _table(_section(3), ("page", "tab", *PAGE_PERSONAS))


def _key(row: dict[str, str]) -> tuple[str, str]:
    return row["method"], row["path"]


def _route_keys(route) -> set[tuple[str, str]]:
    """The (method, path) pairs one route answers. HEAD beside GET is left out: Starlette adds it to every `Route`
    that has GET (FastAPI's own schema route is one), so there it is not a route of its own. A route declared for
    HEAD alone (`@app.head`) keeps it, and needs its row. A mount answers GET under its `path_format`,
    `/static/{path}`."""
    if isinstance(route, Mount):
        return {("GET", route.path_format)}
    return {(method, route.path_format) for method in route.methods
            if method != "HEAD" or "GET" not in route.methods}


def _keys(app) -> set[tuple[str, str]]:
    return set().union(*(_route_keys(route) for route in app.routes))


def _url(path: str) -> str:
    parts = path.split("/")
    out = []
    for i, part in enumerate(parts):
        if part.startswith("{"):
            # A {name} is named by the segment before it, or the one before that when that is a placeholder too
            # (/api/housekeeping/copies/{kind}/{name}).
            before = parts[i - 1] if not parts[i - 1].startswith("{") else parts[i - 2]
            key = before if part == "{name}" else part[1:-1]
            assert key in PATH_VALUES, f"{path}: no value for {part}; add {key!r} to PATH_VALUES"
            out.append(PATH_VALUES[key])
        else:
            out.append(part)
    return "/".join(out)


def _word(response) -> str:
    """The §4 word for an answer: a 200's `scope` (on /api/whoami, `visibility.scope`), else its status."""
    if response.status_code != 200:
        return str(response.status_code)
    try:
        body = response.json()
    except ValueError:
        return "200"
    if not isinstance(body, dict):
        return "200"
    scope = body.get("scope")
    if scope is None and isinstance(body.get("visibility"), dict):
        scope = body["visibility"].get("scope")
    return scope if scope in ("all", "self") else "200"


def _gates_called(route) -> set[str]:
    """The gates a handler calls: its own source and its dependencies' (`served_scopes`, `alert_scopes`)."""
    if not isinstance(route, APIRoute):
        return set()
    calls = [route.endpoint, *(dep.call for dep in route.dependant.dependencies)]
    source = "".join(inspect.getsource(inspect.unwrap(call)) for call in calls)
    return {gate for gate in GATES if re.search(rf"\b{gate}\(", source)}


def _app(root: pathlib.Path, *, writes: bool = True, housekeeping: bool = True):
    """The seeded app in the posture §4 declares: proxy on, restrictions on, reporting on, and the writes and
    housekeeping switches."""
    db = str(root / "gsd.db")
    _seed(db)
    token, key = root / "report-token", root / "report-ticket-key"
    token.write_bytes(b"t" * 48 + b"\n")
    key.write_bytes(b"k" * 48 + b"\n")
    return build_app(_settings(db, cluster_secrets_writes_enabled=writes, housekeeping_enabled=housekeeping,
                               reporting_url="https://gsd-report.ns.svc:8443", reporting_token_file=str(token),
                               reporting_ticket_key_file=str(key)),
                     run_poller=False)


@pytest.fixture(scope="module")
def app(tmp_path_factory):
    return _app(tmp_path_factory.mktemp("declared"))


@pytest.fixture(scope="module")
def client(app):
    with TestClient(app, follow_redirects=False) as c:
        yield c


def test_every_route_the_app_registers_has_a_row(app):
    """T239-1: a route added without a §4 row fails here by name, with the row to fill in."""
    missing = sorted(_keys(app) - {_key(row) for row in ROUTES})
    rows = "\n".join(f"| {method} | `{path}` | <always, writes on or housekeeping on> | <gate or none> | <no identity> | <self> "
                     f"| <auditor> | <usage> | <cluster-admin> | <notes> |" for method, path in missing)
    assert not missing, f"routes with no row in docs/guides/ACCESS_CONTROL.md §4; add one each (§4 names the words):\n{rows}"


def test_every_row_names_one_route_the_app_serves(app):
    """T239-2: a row for a route that is gone, renamed or never existed fails here, and so does a second row for one."""
    keys = [_key(row) for row in ROUTES]
    assert len(keys) == len(set(keys)), f"rows declared twice: {sorted({k for k in keys if keys.count(k) > 1})}"
    unserved = sorted(set(keys) - _keys(app))
    assert not unserved, f"§4 rows the app does not serve: {unserved}"


def test_another_services_rows_name_no_route_of_this_app(app):
    """T239-2: the rows marked as another service's are the only ones exempt, so none may cover one of ours."""
    paths = {path for _, path in _keys(app)}
    for row in OTHER_SERVICES:
        prefix = row["path"].split("*", 1)[0]
        assert not any(path.startswith(prefix) for path in paths), (row["path"], "is served by this app")


def test_every_cell_is_a_declared_word():
    for row in ROUTES:
        assert row["method"] in {"GET", "POST", "PUT", "DELETE"}, row
        assert row["registered"] in {"always", "writes on", "housekeeping on"}, row
        assert row["gate"] in {*GATES, "none"}, row
        assert {row[p] for p in ROUTE_PERSONAS} <= ROUTE_WORDS, row
    for row in PAGES:
        assert {row[p] for p in PAGE_PERSONAS} <= PAGE_WORDS, row


def test_the_rows_marked_writes_on_are_the_routes_the_switch_registers(app, tmp_path):
    """T239-7: built with the writes off, exactly the rows marked `writes on` are gone, and nothing else."""
    off = _keys(_app(tmp_path, writes=False))
    assert off <= _keys(app)
    assert _keys(app) - off == {_key(row) for row in ROUTES if row["registered"] == "writes on"}


def test_the_rows_marked_housekeeping_on_are_the_routes_the_switch_registers(app, tmp_path):
    """SPEC_G1 note 16, as T239-7: built with housekeeping off, exactly the rows marked `housekeeping on` are gone."""
    off = _keys(_app(tmp_path, housekeeping=False))
    assert off <= _keys(app)
    assert _keys(app) - off == {_key(row) for row in ROUTES if row["registered"] == "housekeeping on"}


@pytest.mark.parametrize("row", ROUTES, ids=[f"{r['method']} {r['path']}" for r in ROUTES])
def test_the_gate_column_names_what_the_handler_calls(app, row):
    route = next(r for r in app.routes if _key(row) in _route_keys(r))
    called = _gates_called(route)
    if row["gate"] == "none":
        assert not called, f"{row['method']} {row['path']} calls {sorted(called)}; its row says none"
    else:
        assert row["gate"] in called, f"{row['method']} {row['path']} calls {sorted(called)}, not {row['gate']}"


CASES = [(row, persona) for row in ROUTES for persona in ROUTE_PERSONAS]


@pytest.mark.parametrize("row,persona", CASES, ids=[f"{r['method']} {r['path']} | {p}" for r, p in CASES])
def test_each_route_answers_each_persona_as_its_row_declares(app, client, monkeypatch, row, persona):
    """T239-3 and T239-9: the row's word for this persona is what the route answers. Equality, not a floor: a route
    moved to a lower tier fails on the persona it newly admits, and one moved higher on the persona it newly refuses."""
    # An admitted write reads the pod's namespace next: answered "none here", so it stops with a 409 in this process.
    monkeypatch.setattr(gsd.api, "own_namespace", lambda: None)
    stubs = ROUTE_PERSONAS[persona]
    wide, usage, cluster_admin = stubs or ({}, {}, {})
    app.state.tier_resolver = _MapResolver(wide)
    app.state.usage_tier_resolver = _MapResolver(usage)
    app.state.cluster_admin_resolver = _MapResolver(cluster_admin)
    # A write carries the header the page sends with every write: _housekeeping_write refuses one without it.
    page = {"X-GSD-Interaction": "declaration"} if row["method"] != "GET" else {}
    response = client.request(row["method"], _url(row["path"]), headers={**H(VIEWER), **page} if stubs else {},
                              **({"json": {}} if row["method"] in ("POST", "PUT") else {}))
    declared = row[persona]
    if declared == "admitted":
        assert response.status_code not in (401, 403), (persona, response.status_code, response.text[:200])
    else:
        assert _word(response) == declared, (persona, response.status_code, response.text[:200])


def _tabs() -> dict[str, str]:
    """The tab buttons the page can draw, id -> label: every `tab("<id>", "<Label>")` call in index.html."""
    return dict(re.findall(r'\btab\(\s*"([\w-]+)"\s*,\s*"([^"]+)"\s*\)', PAGE.read_text()))


def _pages() -> set[str]:
    """Every page the page can show: the tabs, and every page render() dispatches on (the Reporting status page and
    the search page have no tab)."""
    render = PAGE.read_text().split("\nfunction render() {", 1)[1].split("\nfunction ", 1)[0]
    return set(re.findall(r'view\.page === "([\w-]+)"', render)) | set(_tabs())


def test_every_tab_and_page_has_one_row_and_every_row_names_one():
    """T239-4: §3 lists every page index.html can draw, once, under the label its tab button carries."""
    tabs = _tabs()
    assert len(tabs) >= 14, f"the tab() calls are no longer matched: {tabs}"
    pages = [row["page"] for row in PAGES]
    assert len(pages) == len(set(pages)), f"pages declared twice: {sorted({p for p in pages if pages.count(p) > 1})}"
    assert set(pages) == _pages(), (
        f"§3 lacks {sorted(_pages() - set(pages))}; §3 names pages the page cannot draw: {sorted(set(pages) - _pages())}")
    for row in PAGES:
        assert row["tab"] == tabs.get(row["page"], "—"), (row["page"], row["tab"], tabs.get(row["page"]))
