# SPEC G1 — the access declaration: every route and page names the tier each reader gets, in ACCESS_CONTROL.md §3 and §4, and a test proves it per persona (#239)

| | |
|---|---|
| Programme | Epic G (#387), access declared and platform identities configured: build step 1 of 4, the safety net the later steps (#255, #503, #420) change access under |
| Batch | G — access declared |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | no version change (tests and docs only) |
| Issue | [#239](https://github.com/ephico2real2/group-sync-dashboard/issues/239) |
| Status | merged |
| Source | OB1-lite's research and specification of 2026-10-01, written before any code from the issue's body of 2026-10-01 and its "Decisions and corrections (2026-10-01)", the epic (#387) and its decisions of 2026-09-30 and 2026-10-01. Measured on main `5c03a9b1` on this machine (Python 3.14, FastAPI 0.141.1, Starlette 1.6.0, the versions the venv and the image carry), in a browser (Playwright, Chromium), and read-only on the lab. §7's blocks were cut from a copy of `5c03a9b1` with the design implemented and proved against a clean tree (§4.4). Revised the same day after the review of `de42286a` by OB3 (in Grok's seat) and Codex, on the orchestrator's decisions (Orchestrator's notes, "The review of `de42286a`"), and re-proved on main `dd51b91f` (§4.4) |

## How to read this spec

The plain point first. The dashboard already decides correctly who sees what: every route calls its gate in
`local-development/gsd/api.py`. What is missing is one written table that says, for every route and every page,
what each kind of reader gets, and a test that fails when the code and the table disagree. Today the table in
`docs/ACCESS_CONTROL.md` is written by hand, is thirteen routes and four tabs behind, and nothing checks it, so a new
route could ship with no gate and the suite would stay green. This spec makes §4 of that document the declaration
for routes and §3 the declaration for pages, and adds the test that holds both to the running code.

§1 is the mandate. §2 is the research: each finding names its source (a primary document with the date it was
fetched, upstream code read from the raw file, or a probe run on main), and quotes what it relies on; §2a weighs the
alternatives and reconciles each external claim with the line here that behaves accordingly. Line citations
into upstream code and into main at `5c03a9b1` are written as plain text, never as backticked `path:line`, to keep them
apart from the maintained `path#anchor` citations. §3 is the design, one rule per subsection with its reason. §4 maps
every test case of the issue (T239-1 to T239-11) to a test, shows each failing without the change, and shows the
mutants each one kills. §5 is the walk on the lab. §6 is what an operator sees and what it costs. §7 is the whole
change as implementation blocks (`docs/specs/README.md`, "Implementation blocks"), applied to a clean tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_G1_tier_declaration.md . --apply

No block touches `local-development/gsd/` or `charts/`: this change is tests and documents only. This spec's own row
in the index moves through the lifecycle by the orchestrator's hand, as M1's did; no block touches it. A block found
wrong during implementation is corrected here, with the reason under the orchestrator's notes, before it is applied
again.

## Orchestrator's notes

Decisions taken on "easy to manage, best practice" where the issue left room, and corrections to the issue, each with
its evidence. The issue's own decisions of 2026-10-01 are followed as written (the key is method and path; the app is
built with the writes on and its routes read from `app.routes`; §4 has a column per persona; §3 covers every page;
every declared tier is proved per persona; SPEC_T1 becomes `in progress` with a note).

1. **The declaration is the document, read by a test; no registry in code.** The epic settled it on 2026-09-30
   ("#239's declaration lives in the docs, proved by a test"). OWASP ASVS 5.0 asks for exactly this artefact,
   "authorization documentation" defining "function-level and data-specific access" (8.1.1, §2.6), and the test is
   what keeps that documentation true. The registry, `visibility.tiers` and the renames are not designed here (the
   mandate); see the open question.
2. **One identity, five settings of the seams.** The issue's T239-3 names the seams of
   `local-development/tests/test_cluster_admin_tier.py#_app` and `H(who)`. Every persona here is the same seeded reader,
   `alice`, and only the three resolver stubs change. Measured on main with a different name per persona (§2.4), the
   usage persona answered 403 on `/api/clusters/c1/groups/g-adm` and two other detail routes because that name was not
   a member, not the user and held no grant there: a fact about the name, not the tier. With one identity every route that names the reader's own group, user or namespace answers its
   tier's outcome, and the declaration states tiers, not membership.
3. **Each persona passes exactly its own question.** The cluster-admin persona passes `visibility.clusterAdminSar`
   alone, so its column also proves #322's grant of the wide view and Usage (`local-development/gsd/api.py#viewer_scope`,
   `local-development/gsd/api.py#usage_scope`); a real `cluster-admin` passes all three questions and is answered the
   same.
4. **The assertion is equality, not a floor.** The issue asks that moving a route to a lower tier fail. Comparing the
   declared word for equality also fails a route moved to a higher tier, which is a behaviour change the issue's
   "Must not change" forbids just as firmly.
5. **The writes are declared `admitted` for the cluster-admin, not a status.** Past `_writes_gate` a write reaches its
   own validation, the Secret writer and the network; what it answers there is held by its own tests
   (`local-development/tests/test_clusterconfig_tab.py`, `local-development/tests/test_cluster_admin_tier.py`). The
   test stubs the namespace read (`local-development/gsd/leader.py#own_namespace`) so an admitted write stops in the
   process with a 409 and never leaves it, whatever `GSD_NAMESPACE` says on the machine running the suite.
6. **Every entry of `app.routes` is a row; nothing is excluded by name.** The issue allowed FastAPI's
   `/api/openapi.json` and the `/static` mount to be "rows too, or excluded by name with the reason". Both are rows:
   the key is each route's `path_format` (a mount's is `/static/{path}`, Starlette routing.py line 388), and `HEAD`
   beside `GET` is left out because Starlette adds it to every `Route` that has `GET` (routing.py lines 233-238).
   FastAPI's `APIRoute` carries exactly the methods it is declared with (fastapi/routing.py lines 1019-1021), so a
   route declared for `HEAD` alone (`@app.head`) keeps `HEAD` and needs its row. A rule with no exceptions is the
   simpler one to keep.
7. **`/report/**` leaves the declaration table for its own small table, "Served by another service".** That is
   T239-2's "marker for another service", and a test holds it to name no route of this application.
8. **Correction to the issue: §3 has sixteen pages, not fifteen.** The issue names the fourteen tab buttons and the
   Reporting status page. `render()` in `local-development/gsd/static/index.html#function render()` also dispatches on
   `lookup`, the search page the search box opens, which has no tab (measured: the union of the `tab(...)` calls and
   render()'s `view.page === "..."` branches is 16). The test derives the set from the page, so it is §3 that must
   follow the page, never a count.
9. **Home is `self` for every persona in §3, while §4's `/home` row reads `all` for the wide personas.** Not a
   contradiction: Home is the reader's own access at every tier by design (#158; the handler's docstring, "SELF-SCOPED
   BY DEFINITION, on every tier"), and its payload's `scope` names the tier that decided. §3 says what the reader
   sees; §4 says what the wire says. Both rows say so.
10. **Correction to main's §3: the refusal card does not say "For cluster administrators only".** Main's §3 put that
    sentence in the KPI and Cluster Configurations cells. It is the API's `detail`
    (`local-development/gsd/api.py#require_cluster_admin`); the page's card, `refusalCard` in
    `local-development/gsd/static/index.html#function refusalCard`, draws "For administrators only." for every refused
    page. The new §3 names no sentence; the sentences themselves are unchanged ("Must not change").
11. **§5's diagram listed three users of `require_admin_tier`; there are four.** The Kyverno route is the fourth
    (§2.3). One word added; no other line of §5 moves.
12. **A gate column, checked.** The issue asked for the persona columns. A column naming the gate each handler calls
    is what a reader follows into the code, so the test also checks that the handler (or its dependency) calls the
    function the row names, and that a `none` row calls none. It costs one small helper; mutant M11 (§4.3) is a row
    whose gate is wrong while every outcome is right, and only this check fails on it.
13. **T239-5 checks more than the strip.** It loads every page as every persona and holds each refusal card to §3, not
    only the tab strip, because "absent" and "refused" are §3's two claims a browser can check and the API cannot.
    Measured cost: 4 tests, about 5 s (§4.4). The usage persona is added to the issue's three, since §3 has its
    column.
14. **The spec's own commit edits `local-development/tests/test_specs_index.py`, outside the blocks.** The index row
    added with this spec moves the row count from 35 to 36, and G1 shares #239 with T1, so the "issues rise down the
    table" and "programme issues are unique" checks name G1 as an exception, as they already name D5 and the S steps,
    and pin G1's issue to T1's, so the exception covers that one sharing and no other number (review of the spec, OB3:
    without the pin, a G1 row mistyped as #504 in the index and the header passed all 79 tests). That edit lands with
    the row, in the spec's commit; §7's block for the same file adds T239-8's test at the end of the file and does not
    touch those lines, so it applies on main and on main with this spec alike.
15. **Found, not changed: a stale comment in `api.py`.** The comment above `FastAPI(...)` in
    `local-development/gsd/api.py#build_app` says `skipAuthRegex` admits `^/(healthz|readyz|metrics)$` and nothing
    else; the chart's regex also admits `/signed-out` and two static assets
    (`charts/group-sync-dashboard/values.yaml#skipAuthRegex`). Correcting it changes the image (a MINOR), which this
    tests-and-docs change does not take; §3 and §4 cite the chart's regex, the source of truth.

16. **Correction at implementation (2026-10-03): #542's five routes, written into the blocks before any were applied.**
    SPEC_H1 (#547, application 3.1.0) merged after this spec, and it registers five routes with `housekeeping.enabled`:
    `GET /api/housekeeping/copies`, `DELETE /api/housekeeping/copies/{kind}/{name}`,
    `POST /api/housekeeping/copies/cleanup`, `DELETE /api/housekeeping/reports/{run_id}` and
    `POST /api/housekeeping/reports/cleanup`. It also added their row to the table block 8 replaces, so block 8's Old
    text failed to match (`apply-spec-blocks.py`: "Old text occurs 0 times"). Corrected here:
    - **Block 8.** The Old text carries #547's row. The New text declares the five routes, registered
      `housekeeping on`:
      - the listing is gated by `_housekeeping_gate`, and answers 200 to the cluster-admin and 403 to every other
        persona;
      - the four writes are gated by `_housekeeping_write`, and are `admitted` for the cluster-admin;
      - the posture paragraph names the switch.
    - **Block 1:**
      - `GATES` gains `_housekeeping_gate` and `_housekeeping_write`;
      - `_app` turns `housekeeping` on as well;
      - `registered` accepts `housekeeping on`;
      - a test mirrors T239-7 for that switch;
      - `PATH_VALUES` gains `kind`, `copies` and `run_id`;
      - `_url` fills a `{name}` that follows another placeholder from the segment before that one (`copies`).
    - **The page's header.** A write carries the page's `X-GSD-Interaction` header, because the page sends it with
      every write and `_housekeeping_write` refuses a write without it (OWASP's custom-request-header defence,
      SPEC_H1 §2.3). So the declaration describes the page's requests. The header changes nothing for
      `_writes_gate`'s routes.

 (OB3 in Grok's seat, Codex gpt-5.6-sol at xhigh, 2026-10-01), as the orchestrator
accepted it; each hunk was traced before it was applied, and none was rejected:

- **F1, a route declared for `HEAD` alone escaped the declaration (OB3, required).** `_route_keys` dropped `HEAD`
  everywhere, but Starlette adds it only beside `GET`; an ungated `@app.head("/api/probe")` passed all 270 tests.
  `HEAD` now stays a key where the route has no `GET` (note 6, §3.2, §2a's reconciliation); mutant M13 (§4.3) is the
  proof.
- **F2 = Codex C6, the G1 exception was wider than its comment (both).** Unpinned, a G1 row mistyped as another
  issue in the index and the header passed all 79 index tests. The spec's own commit now asserts
  `ROWS["G1"]["issue"] == ROWS["T1"]["issue"] == "239"` before excluding G1 (note 14): OB3's pin to T1's issue,
  with Codex's literal `"239"`.
- **F4, F5 (OB3), clearer failures for the next person adding a route.** The missing-route message prints a row to
  fill in; the path-value message names the key to add.
- **F6 (OB3), the posture names the other clusters.** Every other cluster inherits the host's decision in the rows'
  posture; `/api/alerts` reads every cluster, so a `remote-sar` cluster the reader is not wide on makes it `self`
  (§3.3, §4's posture paragraph).
- **F3 (OB3)** lets the tab pattern accept spaces inside `tab( "id" , "Label" )`; **F7 (OB3)** says `/signed-out`
  reads no *identity* header; **N1 (OB3)** gives block 2 PEP 8's two blank lines on both sides.
- **Codex C1–C5 and C8 confirmed** with their own probes; **C7 plausible** only because its sandbox refused Chromium
  and two loopback binds. OB3 ran both suites green, and §4.4 is re-run here on `dd51b91f`. Codex's extra mutant (a
  `list_groups` that keeps `scope: self` but serves every row) survives this module and dies in
  `local-development/tests/test_visibility.py`, as §1 scopes it: field and row projections keep their own tests.

**The operator's rules of 2026-10-01.** §2a answers *"verify the claims and alternative solutions … and reconcile your
research and code logic"*. The Helm-values-first rule touches nothing here: no chart value, template or command
changes; the new §3 and §4 name settings by their values keys (`reporting.enabled`,
`clusterConfig.secrets.writes.enabled`), and no document text gives a `helm`, `--set` or Argo CD step as a path. §2.7
cites Argo CD's RBAC model only as the design analogy the mandate asked for; the `argocd admin settings rbac can`
command appears there as a quotation of that model, not as a step of this change.

**Open for the operator** (the issue's own question, asked when this issue starts; not designed here):

- Keep the 2026-09-20 model's remaining parts (the `TIER_BY_SURFACE` registry in `gsd/`, `visibility.tiers` on
  `/api/whoami`, and the `adminSar` → `auditorSar` / `usageAdminSar` → `adminSar` renames with a one-release alias) as a
  later step, or withdraw them? None of it changes who sees what. One fact from the research bears on it: the OWASP
  Authorization Cheat Sheet prefers checks with "global, application-wide configuration rather than needing to be
  applied individually to every method or class" (§2.6), which is the registry's argument. This spec gets the
  completeness that sentence is after another way, by failing CI on any route the declaration does not cover;
  whether to centralise the gates as well is the operator's call. Either answer leaves SPEC_T1 at `in progress`, with
  the answer written into its header (the issue's decision 2).

## 1. The mandate, and what is out of scope

The issue (#239, "What must be accomplished"): `docs/ACCESS_CONTROL.md` §4 has one row for every route the app
registers with the cluster-configuration writes on, keyed by method and path, naming the tier each persona gets, the
six write routes marked as registered only with `clusterConfig.secrets.writes.enabled`; every §4 row names something
the app serves, except rows marked as another service's; §3 has one row for every tab and page, naming what each
persona sees; a test drives every §4 row with the five personas and asserts the declared outcome, so moving a route to
a lower tier or dropping its gate fails the suite; SPEC_T1 and its index row say what #322 delivered, what this issue
delivers and what is not built; and nobody gains or loses a route, a row, a field or a tab. Its Definition of Done
adds: the mutant that moves `/api/kpi` to `require_admin_tier` shown failing; a dummy `@app.get("/api/probe")` and a
deleted §4 row each failing T239-1; the lab walk (T239-10); no version bump unless the spec touches
`local-development/gsd/`.

Out of scope, each owned elsewhere or ruled: the `TIER_BY_SURFACE` registry, `visibility.tiers` and the setting
renames (the operator's open question); #114 (closed, not planned, 2026-09-27); per-cluster policies, which decide first
and keep their own tests (`ACCESS_CONTROL.md` §11, `local-development/tests/test_multicluster_visibility.py`); the proxy-off
and restrictions-off postures (§8, `local-development/tests/test_cluster_admin_tier.py#TestFailClosed`); the field-level
projections inside a 200 (`ldap_filter` and `error_message` on `groupsyncs`, `operator_configs` on `/api/clusters`),
which keep their own tests (`local-development/tests/test_visibility.py#TestTwoTiersPerEndpoint.test_groupsyncs_omit_directory_detail_at_self`,
`local-development/tests/test_view_scoping.py#test_operator_config_summary_is_withheld_at_self_on_the_cluster_list`);
and every gate's code, which does not change.

## 2. Research, measured

The probes ran with the repository's venv against a copy of `5c03a9b1`, each printing the `gsd` it imported (the
copy's, not the main checkout's). They are described below well enough to repeat and are not committed.

### 2.1 The routes, as the app registers them

**Probe** (`build_app` with `cluster_secrets_enabled` and `cluster_secrets_writes_enabled` true, then with the writes
off; for each entry of `app.routes`, its type, methods, path and `include_in_schema`):

```text
writes=True: len(app.routes) = 44
  Route    GET,HEAD   /api/openapi.json                                       schema=False
  APIRoute GET        /api/clusterconfigs                                     schema=True
  APIRoute POST       /api/clusterconfigs                                     schema=True
  APIRoute PUT        /api/clusterconfigs/{name}/credential                   schema=True
  APIRoute DELETE     /api/clusterconfigs/{name}                              schema=True
  APIRoute POST       /api/clusterconfigs/test                                schema=True
  APIRoute POST       /api/clusterconfigs/{name}/refresh                      schema=True
  APIRoute POST       /api/clusterconfigs/{name}/rejoin                       schema=True
  APIRoute GET        /api/clusters                                           schema=True
  APIRoute GET        /api/clusters/{cluster_id}/groupsyncs                   schema=True
  APIRoute GET        /api/clusters/{cluster_id}/groupsyncs/{name}/events     schema=True
  APIRoute GET        /api/clusters/{cluster_id}/groups                       schema=True
  APIRoute GET        /api/clusters/{cluster_id}/groups/{name}                schema=True
  APIRoute GET        /api/clusters/{cluster_id}/users                        schema=True
  APIRoute GET        /api/clusters/{cluster_id}/users/{name}                 schema=True
  APIRoute GET        /api/clusters/{cluster_id}/logins                       schema=True
  APIRoute GET        /api/clusters/{cluster_id}/cluster-access               schema=True
  APIRoute GET        /api/clusters/{cluster_id}/bindings/findings            schema=True
  APIRoute GET        /api/clusters/{cluster_id}/namespaces                   schema=True
  APIRoute GET        /api/clusters/{cluster_id}/namespaces/{name}            schema=True
  APIRoute GET        /api/clusters/{cluster_id}/home                         schema=True
  APIRoute GET        /api/clusters/{cluster_id}/user-bindings                schema=True
  APIRoute GET        /api/clusters/{cluster_id}/operator-configs             schema=True
  APIRoute GET        /api/clusters/{cluster_id}/kyverno                      schema=True
  APIRoute GET        /api/clusters/{cluster_id}/membership-changes           schema=True
  APIRoute GET        /api/clusters/{cluster_id}/binding-changes              schema=True
  APIRoute GET        /api/alerts                                             schema=True
  APIRoute GET        /metrics                                                schema=True
  APIRoute GET        /healthz                                                schema=True
  APIRoute GET        /api/kpi                                                schema=True
  APIRoute GET        /api/whoami                                             schema=True
  APIRoute GET        /api/dashboard/activity                                 schema=True
  APIRoute GET        /api/report/ticket                                      schema=True
  APIRoute GET        /api/dashboard/reports                                  schema=True
  APIRoute GET        /api/version                                            schema=True
  APIRoute GET        /readyz                                                 schema=True
  APIRoute GET        /api                                                    schema=False
  APIRoute GET        /api/redoc                                              schema=False
  APIRoute GET        /api/docs                                               schema=False
  APIRoute GET        /                                                       schema=True
  APIRoute GET        /signed-out                                             schema=True
  APIRoute GET        /static/index.html                                      schema=False
  APIRoute GET        /static/signed-out.html                                 schema=False
  Mount               /static                                                 schema=None
writes=False: len(app.routes) = 38
```

This confirms the issue's decision 5: 44 entries with the writes on (42 decorated routes, FastAPI's schema `Route`
and the `/static` `Mount`) and 38 with them off; the generated OpenAPI schema leaves out the five
`include_in_schema=False` routes and the two non-`APIRoute` entries, so the test reads `app.routes`. Every
`/api/clusters/{cluster_id}/…` route is one of 17 (measured in §4.1, T239-11).

### 2.2 What a route's method and path are, upstream

Read from the raw files at the installed tags, which `cmp` found byte-identical to the venv's copies (fetched
2026-10-01):

- **Starlette 1.6.0, `starlette/routing.py`**
  (`https://raw.githubusercontent.com/encode/starlette/1.6.0/starlette/routing.py`). `Route.__init__`, lines
  233-238: `self.methods = {method.upper() for method in methods}` and `if "GET" in self.methods:
  self.methods.add("HEAD")`. `Mount.__init__`, line 388: `self.path_regex, self.path_format, self.param_convertors =
  compile_path(self.path + "/{path:path}")`. **Settles:** `HEAD` is implied by `GET` on a Starlette `Route` and is not
  a route of its own; a mount's own key is its `path_format`, `/static/{path}`.
- **FastAPI 0.141.1, `fastapi/routing.py`**
  (`https://raw.githubusercontent.com/fastapi/fastapi/0.141.1/fastapi/routing.py`). `APIRoute.__init__` (line 1193)
  calls `_populate_api_route_state`, not Starlette's `Route.__init__`, and that function sets, lines 1019-1021,
  `if methods is None: methods = ["GET"]` and `route.methods = {method.upper() for method in methods}`.
  **Settles:** an `APIRoute` declared with `@app.get` carries `{"GET"}` alone (the probe above agrees), so the key
  `(method, path_format)` has exactly one row per decorator.
- **FastAPI 0.141.1, `fastapi/applications.py`**, line 1120: `self.add_route(self.openapi_url, openapi,
  include_in_schema=False)`. **Settles:** `/api/openapi.json` is a plain Starlette `Route` (hence `GET,HEAD`) that the
  schema never lists, so only `app.routes` can see it.

### 2.3 Which gate each handler calls

**Probe:** for every `APIRoute`, `inspect.getsource(inspect.unwrap(route.endpoint))` and the names of its
`Depends()` calls, searched for the five gates. Measured (summarised by gate; the per-route list is §4's table):

| gate | routes |
|---|---|
| `viewer_scope` | 16: `/api/clusters`, `groupsyncs`, `groups`, `groups/{name}`, `users`, `users/{name}`, `user-bindings`, `membership-changes`, `binding-changes`, `logins`, `cluster-access`, `namespaces`, `namespaces/{name}`, `home`, `/api/alerts`, `/api/whoami` (`/api/clusters` and `/api/alerts` through the dependencies `served_scopes` and `alert_scopes`) |
| `require_admin_tier` | 4: `bindings/findings`, `operator-configs`, `kyverno`, `/api/report/ticket` |
| `usage_scope` | 2: `/api/dashboard/activity`, `/api/dashboard/reports` |
| `require_cluster_admin` | 2: `GET /api/clusterconfigs`, `/api/kpi` |
| `_writes_gate` | 6: the write routes, which call `require_cluster_admin` inside it (`local-development/gsd/api.py#_writes_gate`) |
| none | 1 by ruling (`groupsyncs/{name}/events`) and 11 infrastructure or page routes, plus the schema route and the mount |

This matches the issue's census (16, 4, 2, 2, 6, 1, 11) and adds that `kyverno` is a `require_admin_tier` route, which
§5's diagram omitted (note 11).

### 2.4 What every route answers each persona, on main

**Probe:** the app of §2.1 (writes on), seeded by `local-development/tests/test_visibility.py#_seed`, reporting
configured, the namespace read stubbed; each `(method, path)` requested once per persona with the cluster `c1` and
`alice`'s own group (`g-adm`), user, namespace (`ns1`) and the seeded GroupSync; the three seams set per persona as
§3.3 states; printed the status and, on a 200, the body's `scope` (`visibility.scope` on `/api/whoami`):

```text
GET    /api/openapi.json                                    none=200  self=200  auditor=200  usage=200  cluster-admin=200
GET    /api/clusterconfigs                                  none=403  self=403  auditor=403  usage=403  cluster-admin=200/all
POST   /api/clusterconfigs                                  none=403  self=403  auditor=403  usage=403  cluster-admin=409
PUT    /api/clusterconfigs/{name}/credential                none=403  self=403  auditor=403  usage=403  cluster-admin=409
DELETE /api/clusterconfigs/{name}                           none=403  self=403  auditor=403  usage=403  cluster-admin=409
POST   /api/clusterconfigs/test                             none=403  self=403  auditor=403  usage=403  cluster-admin=409
POST   /api/clusterconfigs/{name}/refresh                   none=403  self=403  auditor=403  usage=403  cluster-admin=409
POST   /api/clusterconfigs/{name}/rejoin                    none=403  self=403  auditor=403  usage=403  cluster-admin=409
GET    /api/clusters                                        none=200  self=200  auditor=200  usage=200  cluster-admin=200
GET    /api/clusters/{cluster_id}/groupsyncs                none=200  self=200  auditor=200  usage=200  cluster-admin=200
GET    /api/clusters/{cluster_id}/groupsyncs/{name}/events  none=200/all  self=200/all  auditor=200/all  usage=200/all  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/groups                    none=403  self=200/self  auditor=200/all  usage=200/self  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/groups/{name}             none=403  self=200/self  auditor=200/all  usage=200/self  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/users                     none=403  self=200/self  auditor=200/all  usage=200/self  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/users/{name}              none=403  self=200/self  auditor=200/all  usage=200/self  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/logins                    none=403  self=200/self  auditor=200/all  usage=200/self  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/cluster-access            none=403  self=200/self  auditor=200/all  usage=200/self  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/bindings/findings         none=403  self=403  auditor=200/all  usage=403  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/namespaces                none=403  self=200/self  auditor=200/all  usage=200/self  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/namespaces/{name}         none=403  self=200/self  auditor=200/all  usage=200/self  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/home                      none=403  self=200/self  auditor=200/all  usage=200/self  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/user-bindings             none=403  self=200/self  auditor=200/all  usage=200/self  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/operator-configs          none=403  self=403  auditor=200/all  usage=403  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/kyverno                   none=403  self=403  auditor=200/all  usage=403  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/membership-changes        none=403  self=200/self  auditor=200/all  usage=200/self  cluster-admin=200/all
GET    /api/clusters/{cluster_id}/binding-changes           none=403  self=200/self  auditor=200/all  usage=200/self  cluster-admin=200/all
GET    /api/alerts                                          none=200/self  self=200/self  auditor=200/all  usage=200/self  cluster-admin=200/all
GET    /metrics                                             none=200  self=200  auditor=200  usage=200  cluster-admin=200
GET    /healthz                                             none=200  self=200  auditor=200  usage=200  cluster-admin=200
GET    /api/kpi                                             none=403  self=403  auditor=403  usage=403  cluster-admin=200/all
GET    /api/whoami                                          none=200  self=200/self  auditor=200/all  usage=200/self  cluster-admin=200/all
GET    /api/dashboard/activity                              none=403  self=200/self  auditor=200/self  usage=200/all  cluster-admin=200/all
GET    /api/report/ticket                                   none=403  self=403  auditor=200  usage=403  cluster-admin=200
GET    /api/dashboard/reports                               none=403  self=200/self  auditor=200/self  usage=200/all  cluster-admin=200/all
GET    /api/version                                         none=200  self=200  auditor=200  usage=200  cluster-admin=200
GET    /readyz                                              none=200  self=200  auditor=200  usage=200  cluster-admin=200
GET    /api                                                 none=200  self=200  auditor=200  usage=200  cluster-admin=200
GET    /api/redoc                                           none=200  self=200  auditor=200  usage=200  cluster-admin=200
GET    /api/docs                                            none=308  self=308  auditor=308  usage=308  cluster-admin=308
GET    /                                                    none=200  self=200  auditor=200  usage=200  cluster-admin=200
GET    /signed-out                                          none=200  self=200  auditor=200  usage=200  cluster-admin=200
GET    /static/index.html                                   none=200  self=200  auditor=200  usage=200  cluster-admin=200
GET    /static/signed-out.html                              none=200  self=200  auditor=200  usage=200  cluster-admin=200
GET    /static                                              none=200  self=200  auditor=200  usage=200  cluster-admin=200
```

(The last line is the mount, requested as `/static/app.css`.) These are §4's persona columns, word for word under
§3.4's mapping. The issue's T239-9 measurement agrees for every row it names: `/api/whoami`, `/api/clusters`,
`/api/alerts`, `groupsyncs` and its events answer 200 with no identity; `groups` and `/api/kpi` 403; `/api/docs` 308.

The same probe run first with a different name per persona (`alice`, `auditor`, `usage`, `root`) differed in three cells
only: the usage persona got 403 on `groups/{name}`, `users/{name}` and `namespaces/{name}`, because `usage` is not a
member of `g-adm`, not the user `alice` and holds no grant in `ns1`. That is note 2's reason for one identity.

### 2.5 What every page shows each persona, in a browser

**Probe:** the seeded app of `local-development/tests/test_ui.py` served with the proxy on, restrictions on, reporting
and the writes on, `_TierByName` stubs per seam (`auditor` wide, `usage` usage, `root` cluster-admin); Chromium loaded
`/#page=<id>` for each page, waited for the network to go idle, and recorded the tab strip and whether `#main` held a
`.scope-refusal`:

```text
alice tabs: ['home', 'overview', 'groups', 'users', 'bindings', 'policy', 'kyverno', 'nsaudit', 'logins', 'usage', 'reports', 'library']
   home=shown overview=REFUSED kpi=REFUSED groups=shown users=shown bindings=shown policy=REFUSED kyverno=REFUSED nsaudit=shown logins=shown usage=shown reports=REFUSED library=REFUSED clusters=REFUSED reporting=REFUSED lookup=shown errors: []
auditor tabs: ['home', 'overview', 'groups', 'users', 'bindings', 'policy', 'kyverno', 'nsaudit', 'logins', 'usage', 'reports', 'library']
   home=shown overview=shown kpi=REFUSED groups=shown users=shown bindings=shown policy=shown kyverno=shown nsaudit=shown logins=shown usage=shown reports=shown library=shown clusters=REFUSED reporting=shown lookup=shown errors: []
usage tabs: ['home', 'overview', 'groups', 'users', 'bindings', 'policy', 'kyverno', 'nsaudit', 'logins', 'usage', 'reports', 'library']
   home=shown overview=REFUSED kpi=REFUSED groups=shown users=shown bindings=shown policy=REFUSED kyverno=REFUSED nsaudit=shown logins=shown usage=shown reports=REFUSED library=REFUSED clusters=REFUSED reporting=REFUSED lookup=shown errors: []
root tabs: ['home', 'overview', 'kpi', 'groups', 'users', 'bindings', 'policy', 'kyverno', 'nsaudit', 'logins', 'usage', 'reports', 'library', 'clusters']
   home=shown overview=shown kpi=shown groups=shown users=shown bindings=shown policy=shown kyverno=shown nsaudit=shown logins=shown usage=shown reports=shown library=shown clusters=shown reporting=shown lookup=shown errors: []
```

**Settles:** §3's refused and absent cells. Below the cluster-admin tier the KPIs and Cluster Configurations tabs are
not drawn and their URL is a refusal card (`absent`); Overview, RBAC policy, Kyverno, Reports, Library and the
Reporting status page are drawn and refused below the wide tier (`refused`); the rest are drawn for everyone. The
page draws from `/api/whoami` (`clusterAdmin()`, `narrowedOnHost()`) and from each route's 403, never from a tier of its
own (`ACCESS_CONTROL.md` §7). The self and auditor strips are equal; what separates them is which pages refuse.

### 2.6 Authorization as a testable property: OWASP

- **OWASP ASVS 5.0.0, V8 Authorization** (`https://raw.githubusercontent.com/OWASP/ASVS/v5.0.0_release/5.0/en/0x17-V8-Authorization.md`,
  fetched 2026-10-01). Line 16, 8.1.1 (level 1): "Verify that authorization documentation defines rules for
  restricting function-level and data-specific access based on consumer permissions and resource attributes." Line 27,
  8.2.1: "Verify that the application ensures that function-level access is restricted to consumers with explicit
  permissions." Line 38, 8.3.1: "Verify that the application enforces authorization rules at a trusted service layer
  and doesn't rely on controls that an untrusted consumer could manipulate, such as client-side JavaScript."
  **Settles:** the declaration is a level-1 requirement in its own right (8.1.1), and it is checkable against 8.2.1
  only if every function, here every route, is in it. 8.3.1 is why §4, the server's answer, is the contract and §3's
  "absent" is a consequence: a tab left out is client-side, so §3 never stands without the 403 in §4 behind it
  (`ACCESS_CONTROL.md` §7, "Hiding a tab is never the control").
- **OWASP Authorization Cheat Sheet** (`https://raw.githubusercontent.com/OWASP/CheatSheetSeries/master/cheatsheets/Authorization_Cheat_Sheet.md`,
  commit `84dfd96458dc`, fetched 2026-10-01). Line 32, "Deny by Default": "the application cannot remain neutral when
  an entity is requesting access to a particular resource … For security purposes an application should be configured
  to deny access by default." Line 41, "Validate the Permissions on Every Request": "Validating permissions correctly
  on just the majority of requests is insufficient", and "The technology used to perform such checks should allow for
  global, application-wide configuration rather than needing to be applied individually to every method or class."
  Line 133, "Create Unit and Integration Test Cases for Authorization Logic": "automated unit and integration testing
  of access control logic can help reduce the number of security flaws that make it into production."
  **Settles:** "every request" is the property the test makes total, by enumerating `app.routes` rather than a hand
  list; a route nobody declared is refused by CI, which is deny-by-default at the moment a route is added, not at
  runtime (the runtime default stays each handler's gate, unchanged). The "global, application-wide configuration"
  sentence argues for a central gate; that is the operator's open question, recorded above, not designed here.

### 2.7 The model the operator named: Argo CD RBAC

**Source:** `docs/operator-manual/rbac.md` at Argo CD v3.5.3, the latest release on 2026-10-01
(`https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.3/docs/operator-manual/rbac.md`). Line 24: "When a user is
authenticated in Argo CD, it will be granted the role specified in `policy.default`." Line 58: "Syntax: `p,
<role/user/group>, <resource>, <action>, <object>, <effect>`". Lines 72-86: "a table that summarizes all possible
resources and which actions are valid for each of them" (applications, clusters, projects, … by get, create, update,
delete, …). Lines 304-305: "After all policies are evaluated, if there was at least one `allow` effect and no `deny`,
access will be granted." Lines 456-460, "Testing a policy": "To test whether a role or subject … has sufficient
permissions to execute certain actions on certain resources, you can use the `argocd admin settings rbac can`
command."

**Settles,** mapped to this design: Argo's fixed resources × actions table is §4's (method, path) rows, the closed
vocabulary a reviewer reads at once; its `policy.default` is the default a request falls to, which here is each
gate's fail-closed answer (`self`, or a 403) and, for a route nobody declared, a red CI run; and `argocd admin settings
rbac can`, one subject asked one action on one resource, is exactly what the persona test does per cell. What does not
map: Argo's policy is configuration a site edits, while §4 records gates and configures nothing (the settings that do
are §10's); bringing that half over is the registry the operator has left open.

### 2.8 The lab, read-only (2026-10-01T12:17Z)

- The deployed image is `quay.io/ephico2real/group-sync-dashboard:2.0.0`; its `/api/version` (read from the pod's
  loopback with no identity, so no activity row is written) says commit `b40b5cf82a`, and `git diff --stat
  b40b5cf82a 5c03a9b1 -- local-development/gsd` is empty: the lab serves main's application code exactly.
- `group-sync-dashboard-config` sets `clusterSecretsWritesEnabled: true` and a `reportingUrl`, so the lab's posture is
  §4's, and every tab in §3 can be drawn there.
- The three walk personas, asked the dashboard's two default questions with `oc auth can-i --as <user>` plus
  `system:authenticated` and `system:authenticated:oauth` (and, for `dana.lee`, her six Groups): `kubeadmin` list
  `clusterrolebindings` yes, update yes; `dana.lee` yes, no (`ClusterRoleBinding cluster-reader`); `developer` no, no.
  So `kubeadmin` is the cluster-admin column, `dana.lee` the auditor column and `developer` the self column.
- PVCs: `group-sync-dashboard-data` `f065b7a4-535c-4ef1-868c-58f5afee4953`, `group-sync-dashboard-report-artifacts`
  `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` (the issue's values, unchanged).

## 2a. Alternatives considered

Six ways to make "every route declares its tier" true were weighed (the operator's rule of 2026-10-01: verify the
alternatives and reconcile the research with the code). Each was researched at its primary source and, where a claim
could be measured on this app, measured.

| alternative | source, quoted | what it would cost here | decision |
|---|---|---|---|
| **A1. The declaration as tables in `docs/ACCESS_CONTROL.md`, read by a test that walks `app.routes` and drives every cell** | ASVS 5.0.0 8.1.1, "authorization documentation defines rules for restricting function-level … access" (§2.6); the Authorization Cheat Sheet, line 133, "automated unit and integration testing of access control logic can help reduce the number of security flaws that make it into production" | one test module (269 lines), one browser test, the two tables; no change under `gsd/` or `charts/`, so no image and no release | **chosen**: the epic's decision of 2026-09-30, the only option that changes no behaviour, and the only one that is the documentation ASVS asks for |
| **A2. Generate §4 from the code** (a script that probes every route and writes the table) | — (a design option, not a published practice) | small, but the table would then record whatever the code does: a route shipped with the wrong gate would regenerate a wrong row and stay green | **rejected**: a declaration must be written by a person and compared with the code, or it proves nothing; generation is how the drift would be hidden, not caught |
| **A3. A `TIER_BY_SURFACE` registry in `gsd/`** (SPEC_T1's step T1) | the Cheat Sheet, line 41: checks "should allow for global, application-wide configuration rather than needing to be applied individually to every method or class" | every gate re-pointed at the registry, `visibility.tiers` on `/api/whoami`, an image MINOR, and the setting renames that came with it in SPEC_T1 | **not designed here**: it is the operator's open question on #239 (the mandate). The Cheat Sheet's sentence is its best argument and is recorded under "Open for the operator" |
| **A4. Enforcement in FastAPI itself: a global dependency, or a custom `APIRoute` class, that refuses a route with no declared tier at runtime** | FastAPI 0.141.1 docs, `tutorial/dependencies/global-dependencies.md` lines 3-7: "you can add them to the `FastAPI` application … they will be applied to all the *path operations* in the application"; `how-to/custom-request-and-route.md` line 3: "you may want to override the logic used by the `Request` and `APIRoute` classes" | measured on FastAPI 0.141.1 with a global dependency that refuses every request: `/decorated 403`, `/hidden 403` (an `include_in_schema=False` route), `/openapi.json 200`, `/static/a.css 200`. A path operation is an `APIRoute`, so the schema route and the mount, two of this app's 44 entries, are out of its reach; it also needs the tier table in code (A3), turns a forgotten declaration into a refusal served in production instead of a red build, and changes the image | **rejected**: it covers fewer routes than A1's walk of `app.routes`, and moves the failure from CI to readers |
| **A5. Tag each route in its OpenAPI operation** (`openapi_extra={"x-tier": …}`) and test the schema | FastAPI 0.141.1 docs, `advanced/path-operation-advanced-configuration.md` line 83: "You can extend the OpenAPI schema for a *path operation* using the parameter `openapi_extra`"; line 128: it "will be deeply merged with the automatically generated OpenAPI schema" | 42 decorator edits under `gsd/` (an image MINOR), and the schema leaves out 7 of the 44 entries (the five `include_in_schema=False` routes, the schema route, the mount: §2.1), so a test of the schema cannot be complete | **rejected**: the issue's decision 5 already ruled the schema out for this reason |
| **A6. An Argo CD-style policy file** (Casbin `p, <subject>, <resource>, <action>, <object>, <effect>` rows and a `policy.default`) | Argo CD v3.5.3 `rbac.md` line 45: "The model syntax is based on Casbin"; line 58, the `p, …` syntax; `assets/builtin-policy.csv` lines 9-12, `p, role:readonly, applications, get, */*, allow` | a policy engine dependency, a policy file the chart would have to carry as a value, and every gate rewritten to ask it: a configuration layer the mandate excludes, and one that would let a site change who sees what by editing a file the dashboard's SubjectAccessReviews do not govern | **rejected**: OpenShift RBAC is already the policy (each tier is a SubjectAccessReview, §2 of `ACCESS_CONTROL.md`); what Argo's model contributes here is the shape, a closed resources × actions table with a default, which A1's §4 is |

**Reconciliation: each external claim, and the line here that behaves accordingly.**

- *Starlette adds `HEAD` to a `Route` that has `GET`* (routing.py lines 237-238): FastAPI's schema route is such a
  `Route`, measured `GET,HEAD` (§2.1), and the test's `_route_keys` drops `HEAD` only where `GET` is also present
  (§7, block 1), so `/api/openapi.json` is one row, `GET`.
- *FastAPI's `APIRoute` carries exactly its declared methods* (fastapi/routing.py lines 1019-1021): every `@app.get`
  route is measured `GET` alone (§2.1), and a route declared with `@app.head` keeps `HEAD` as its key and fails the
  walk until it has a row (mutant M13, §4.3).
- *A mount's path is `<path>/{path:path}`* (routing.py line 388): measured `path_format` `/static/{path}`, the §4 row
  `GET /static/{path}`.
- *FastAPI registers the schema route with `include_in_schema=False`* (applications.py line 1120), and five decorated
  routes opt out too (`local-development/gsd/api.py#build_app`): why the test walks `app.routes`, never the schema.
- *ASVS 8.2.1, function-level access restricted to explicit permissions*: each gated handler calls its gate before it
  reads a row, for instance `local-development/gsd/api.py#require_cluster_admin` at the top of `/api/kpi` and
  `local-development/gsd/api.py#require_admin_tier` at the top of `operator-configs`; the gate column check (§3.5)
  holds each row to that call.
- *ASVS 8.3.1, a trusted service layer, never client-side JavaScript*: the page draws the KPIs and Cluster
  Configurations tabs only when `/api/whoami` says so (`local-development/gsd/static/index.html#function clusterAdmin()`),
  and the 403 comes first from the server; §3's `absent` is always backed by §4's 403 on the same surface.
- *The Cheat Sheet's "deny by default", and Argo CD's `policy.default`*: every tier decision falls to the narrow answer
  when nothing positively widens it: no viewer, no resolver, an error or a junk answer is `self`
  (`local-development/gsd/api.py#_decide`), and the cluster-admin tier is `False` on any of those
  (`local-development/gsd/api.py#_cluster_admin_granted`). The persona test's no-identity column measures that
  default on every row.
- *"Validate the Permissions on Every Request"*: the resolvers are read off `app.state` on each request, not captured
  at build time (`local-development/gsd/api.py#viewer_scope`, `local-development/gsd/api.py#usage_scope`), which is
  also the seam the persona test swaps per persona.

## 3. The design

### 3.1 Where the declaration lives

In `docs/ACCESS_CONTROL.md`, the document an operator already reads for who sees what: §4 for routes, §3 for pages.
Not in code: the epic decided it (2026-09-30), it needs no image change, and a reviewer reads one table instead of a
data structure and the code that consults it. The test parses the two tables, so the document cannot drift from the
code without CI failing. The table records the gates; it configures nothing.

### 3.2 The key

A route is `(method, path_format)` over every entry of `app.routes` of an app built with every switch that registers a
route (`cluster_secrets_enabled` and `cluster_secrets_writes_enabled` true). `HEAD` is a key only on a route declared
without `GET` (§2.2: Starlette adds it beside `GET`; an `@app.head` route declares it). A mount is
`GET <its path_format>`. Each row says `registered: always` or `registered: writes on`; T239-7 builds the app again with
the writes off and requires the difference to be exactly the `writes on` rows.

### 3.3 The posture and the personas

The rows describe the default posture with every route registered: the proxy on, `visibility.enabled: true`, the host
cluster `inherit` and every other cluster inheriting its decision (the fixture's second cluster is `inherit`),
reporting on, and the writes on. `/api/alerts` is the one row that reads every cluster: its `scope` is the narrowest
across the clusters it carries, so a `remote-sar` cluster the reader is not wide on makes it `self` (measured: with
the second cluster at its default, `remote-sar`, 2 of the 220 cells move, both `/api/alerts`). Five personas, one
identity (`alice`, seeded as a member of `g-adm`, a user, and holder of a grant in `ns1`), set through the seams
`build_app` publishes per request (`app.state.tier_resolver`, `.usage_tier_resolver`, `.cluster_admin_resolver`):

| persona | identity | wide stub | usage stub | cluster-admin stub |
|---|---|---|---|---|
| no identity | none | — | — | — |
| self | `alice` | self | self | self |
| auditor | `alice` | all | self | self |
| usage | `alice` | self | all | self |
| cluster-admin | `alice` | self | self | all |

### 3.4 The words

§4: `all` (200, `scope: all`), `self` (200, `scope: self`), `200` (200 with no `scope`), `403`, `308`, and `admitted`
(any answer but 401 or 403: the gate let it through). §3: `all`, `self`, `refused` (tab drawn, refusal card), `absent`
(no tab; the URL is the refusal card). A cell is one word; prose goes in the last column. The test compares for
equality (note 4).

### 3.5 The gate column

Each §4 row names the gate its handler calls (`viewer_scope`, `usage_scope`, `require_admin_tier`,
`require_cluster_admin`, `_writes_gate`) or `none`. The test reads the handler's source through `inspect.unwrap` (the
`@consistent` and `@tier_first` wrappers) plus its `Depends()` callables, and requires a call of the named gate, or of
none for a `none` row.

### 3.6 Pages

§3's pages are the union of `index.html`'s `tab("<id>", "<Label>")` calls and `render()`'s `view.page === "<id>"`
branches, measured at 16 (note 8). Each row names the page id, its tab label or `—`, a word per persona and a sentence
of what a narrowed or refused reader sees. Rows are in strip order, so the browser test compares each persona's strip
as a list.

### 3.7 SPEC_T1

Its header's Status becomes `in progress` and a `Delivered` row says: step T3 delivered by #322 in another shape
(SPEC_T2); the declaration delivered by #239 as SPEC_G1, in the document rather than in code; not built and open for
the operator: the registry, `visibility.tiers` and the renames; #114 closed as not planned. One orchestrator's note
says the same. The body, the 2026-09-20 design, is unchanged, as `docs/specs/README.md` requires of a spec body.

### 3.8 What does not change

Every file under `local-development/gsd/` and `charts/`: no route, gate, field, tab, sentence, setting, chart value or
RBAC rule. Per-cluster policies decide first, as before (`ACCESS_CONTROL.md` §11). The existing hand-listed tier tests
stay; T239-11 replaces only the hand list of the hidden-cluster sweep with the derived one.

### 3.9 The budget

This change writes nothing, retries nothing and widens no access: zero lines change under `local-development/gsd/` and
`charts/` (`git diff --numstat` on the applied copy, §6). What it adds is CI failing where it passes today, on any of:
a route of `app.routes` (writes on) with no §4 row; a §4 row naming no route; a `registered` word the writes switch
contradicts; a cell any of the five personas is answered differently from, in the posture of §3.3; a gate the handler
does not call; a page `index.html` can draw with no §3 row, or a §3 row for none; a persona's tab strip or a page's
refusal card differing from §3. Its scope is that posture: remote-cluster policies (§11) and the proxy-off and
restrictions-off states (§8) are held by their own tests, not by this one.

## 4. Tests

### 4.1 One test per test case of the issue

`local-development/tests/test_access_declaration.py` is new (§7, block 1); the others are edits.

| ID | test | why it fails without the change |
|---|---|---|
| T239-1 | `test_access_declaration.py#test_every_route_the_app_registers_has_a_row` | main's §4 has no declaration table: the module stops at collection, `expected one table headed '\| method \| path \| registered \| gate \| no identity \| self \| auditor \| usage \| cluster-admin \|', found 0`. Against main's old table, the issue measured 13 served paths with no row |
| T239-2 | `test_every_row_names_one_route_the_app_serves`, `test_another_services_rows_name_no_route_of_this_app` | the same collection failure; on main, `/report/**` sat in the route table unmarked and one row counted four writes where six are registered |
| T239-3 | `test_each_route_answers_each_persona_as_its_row_declares`, 220 cases (44 rows × 5 personas) | the same collection failure. Once the rows exist it is a guard on gates that are correct on main; its worth is T239-6 and §4.3 |
| T239-4 | `test_every_tab_and_page_has_one_row_and_every_row_names_one` | the same collection failure; main's §3 had 10 rows for 16 pages (Home, Users, Kyverno, Library, the Reporting status page and the search page missing) |
| T239-5 | `test_ui.py#TestTheDeclaredTabs.test_the_tab_strip_and_every_refusal_are_the_declared_ones`, one per persona | on main all four fail: the test reads §3 through `test_access_declaration`, whose collection fails as above. Once §3 exists it guards the page against it |
| T239-6 | the mutant M1 of §4.3 (`/api/kpi` on `require_admin_tier`) | a mutant proof: T239-3 fails on `GET /api/kpi \| auditor`, and the gate column's test on `GET /api/kpi` |
| T239-7 | `test_the_rows_marked_writes_on_are_the_routes_the_switch_registers` | the same collection failure; the switch itself (`api.py`'s `writes_on`) is unchanged and already held by `local-development/tests/test_api_contract.py#test_r6_the_only_writes_are_the_cluster_secret_routes_and_only_when_switched_on` |
| T239-8 | `test_specs_index.py#test_t1_says_what_was_delivered_and_what_was_not` | fails on main: `AssertionError: specified` (SPEC_T1's index row) |
| T239-9 | the `no identity` cases of T239-3, 44 of them | as T239-3; the column did not exist on main |
| T239-10 | the lab walk, §5 | evidence, not a CI test |
| T239-11 | `test_multicluster_visibility.py#TestHiddenIsNotAnOracle.test_every_cluster_handler_answers_hidden_like_unknown`, over `_cluster_suffixes(app)` | a guard: on main it sweeps 17 routes and passes (44 passed in the module). Mutant M12 shows the difference: drop `require_cluster` from the Kyverno handler and the derived sweep fails on `kyverno`, while main's hand list of 16 passes |

Added by the research: `test_every_cell_is_a_declared_word` (a cell outside the vocabulary would compare as a
mismatch with a confusing message), and `test_the_gate_column_names_what_the_handler_calls`, 44 cases (note 12).

### 4.2 Each test without the change

On a detached worktree of `5c03a9b1` with the four test files of §7 copied in and the documents left as main has them:

| run | result |
|---|---|
| `pytest tests/test_access_declaration.py` | `ERROR tests/test_access_declaration.py`: `AssertionError: expected one table headed '\| method \| path \| registered \| gate \| no identity \| self \| auditor \| usage \| cluster-admin \|', found 0` |
| `pytest tests/test_specs_index.py` | `1 failed, 76 passed`: `test_t1_says_what_was_delivered_and_what_was_not`, `AssertionError: specified` |
| `pytest tests/test_multicluster_visibility.py` | `44 passed` (T239-11 is a guard) |
| `pytest tests/test_ui.py -k TestTheDeclaredTabs --browser chromium` | `4 failed`, each on the same `expected one table headed …` raised by the import of §3 |

### 4.3 The mutants each test kills

Each mutant is a fresh copy of the implemented tree with one change, the module run against it (the two page mutants
run the browser test instead):

| run | the change | result | tests that go red |
|---|---|---|---|
| M0 | none | 270 passed | none |
| M1 | `/api/kpi` calls `require_admin_tier` instead of `require_cluster_admin` (T239-6) | 2 failed | `test_each_route_answers_each_persona_as_its_row_declares[GET /api/kpi \| auditor]`, `test_the_gate_column_names_what_the_handler_calls[GET /api/kpi]` |
| M2 | `operator-configs` loses its `require_admin_tier` call | 4 failed | its `no identity`, `self` and `usage` cases, and its gate column |
| M3 | `/api/dashboard/activity` asks `viewer_scope` instead of `usage_scope` | 3 failed | its `auditor` (now `all`) and `usage` (now `self`) cases, and its gate column: a move to another tier fails both ways |
| M4 | `_writes_gate` loses its `require_cluster_admin` call | 18 failed | the `self`, `auditor` and `usage` cases of all six writes |
| M5 | a new `@app.get("/api/probe")` with no row (the issue's check) | 1 failed | `test_every_route_the_app_registers_has_a_row`, printing the §4 row to fill in for `GET /api/probe` |
| M6 | the `/api/kpi` row deleted from §4 (the issue's check) | 1 failed | `test_every_route_the_app_registers_has_a_row`, printing the §4 row to fill in for `GET /api/kpi` |
| M7 | a new `tab("audit2", "Audit two")` in the strip with no §3 row | 1 failed | `test_every_tab_and_page_has_one_row_and_every_row_names_one` |
| M8 | the Kyverno row deleted from §3 | 1 failed | the same |
| M9 | §3 declares the Overview `all` for the self persona | 1 failed | `TestTheDeclaredTabs…[chromium-self]`: the page draws the refusal card |
| M10 | the KPIs tab drawn for every reader | 3 failed | `TestTheDeclaredTabs…` for self, auditor and usage: the strip has `kpi` |
| M11 | §4 names `viewer_scope` as the Kyverno route's gate, every outcome left right | 1 failed | `test_the_gate_column_names_what_the_handler_calls[GET /api/clusters/{cluster_id}/kyverno]` |
| M12 | the Kyverno handler loses `require_cluster` | 1 failed with the derived sweep; 16 passed with main's hand list | `test_every_cluster_handler_answers_hidden_like_unknown`: `AssertionError: kyverno` |
| M13 | a new `@app.head("/api/probe")` with no row (review of the spec, OB3: it survived the first module, 270 passed) | 1 failed | `test_every_route_the_app_registers_has_a_row`, printing the §4 row to fill in for `HEAD /api/probe` |

M7's first version used an id the test's pattern did not match (`[a-z]+` against `audit2`) and survived; the patterns
in §7 accept any `[\w-]+` id, and the guard `len(tabs) >= 14` catches a pattern that stops matching altogether.

### 4.4 The proof

§7 was not written by hand. The design was implemented in a detached worktree of `5c03a9b1`; a generator cut each
block's Old text from main and its New text from the implemented copy, at whole lines, widening each Old text until it
occurs once, and the CHANGELOG entry was written as an `after: ## Unreleased` block. The review's fixes (notes, "The
review of `de42286a`") were then applied to the blocks as OB3's patch wrote them, after tracing, and the proof below
was run again on main `dd51b91f`. No file a block touches changed between `5c03a9b1` and `dd51b91f` (`git diff
--stat` on the eight paths is empty), and the blocks check on `afa01bb8` too:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_G1_tier_declaration.md <git archive of afa01bb8>
    14 blocks check out across 8 files
    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_G1_tier_declaration.md <git archive of dd51b91f>
    14 blocks check out across 8 files

Before applying, the four test files of §7 copied onto a worktree of `dd51b91f` give §4.2's results again (the module
stops at collection, T239-8 fails with `specified`, the sweep passes 44, the browser test fails 4). On a clean
detached worktree of `dd51b91f`, with `--apply`, and `PYTHONPATH` at its `local-development`:

| check | command | result |
|---|---|---|
| the blocks | `apply-spec-blocks.py --apply` on the clean worktree | applied; every changed file identical (`cmp`) to the same blocks applied to the archive |
| nothing else moves | `git diff --stat -- local-development/gsd charts` | empty |
| the new module | `pytest tests/test_access_declaration.py` | `270 passed` (6 table tests, 44 gate cases, 220 persona cases), 0.95 s |
| the browser test | `pytest tests/test_ui.py -k TestTheDeclaredTabs --browser chromium` | `4 passed`, 5.20 s |
| the files the change touches | `pytest` on `test_access_declaration`, `test_specs_index`, `test_docs_citations`, `test_multicluster_visibility`, `test_values_defaults`, `test_api_contract`, `test_cluster_admin_tier`, `test_visibility` | `1846 passed, 18 skipped` |
| hermetic suite, main | `pytest tests/ -q -p no:cacheprovider --deselect tests/test_ui.py --deselect tests/test_live_smoke.py` on a worktree of `dd51b91f` | `6126 passed, 22 skipped, 655 deselected, 5 xfailed` |
| hermetic suite, applied | the same on the applied worktree | `6384 passed, 22 skipped, 659 deselected, 5 xfailed`: +270 (the module), +1 (T239-8), −15 (the sweep's 16 parametrized cases become one test), +2 (`test_docs_citations` checks the two new anchored citations in §3) |
| browser suite, main | `pytest tests/test_ui.py -q -p no:cacheprovider --browser chromium` on the worktree of `dd51b91f` | `651 passed` |
| browser suite, applied | the same on the applied worktree | `655 passed`: main's 651 and the 4 new |
| markdown | `markdownlint-cli2` on `ACCESS_CONTROL.md`, `CHANGELOG.md`, the specs index | the same findings before and after (6 MD040 on `ACCESS_CONTROL.md`'s unlabelled fences, 1 MD012 on the CHANGELOG), none new |
| Python 3.11 | `ast.parse(source, feature_version=(3, 11))` on the four test modules | all parse; CI's 3.11 job was not run here |
| the mutants | §4.3, each a fresh copy of the applied worktree | all fourteen runs as tabulated; M13 also run against the first version's key rule, where it survives (`270 passed`) |
| F6's measurement | the module with the fixture's second cluster at its default policy (`remote-sar`) | `2 failed, 268 passed`: `GET /api/alerts` for the auditor and the cluster-admin, as §3.3 says |

## 5. On the lab (the implementing pull request)

No image or chart changes, so there is nothing to deploy: the lab already runs this code (§2.8: the deployed commit's
`gsd/` is main's). The walk is T239-10, run against the deployed 2.0.0 after the pull request merges, and committed
under `reports/<date>_tier-declaration/` with the screenshots, pinned to the full merge sha:

1. Record the UIDs of `group-sync-dashboard-data` and `group-sync-dashboard-report-artifacts` (measured on 2026-10-01:
   `f065b7a4-535c-4ef1-868c-58f5afee4953`, `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`). Nothing is deployed, so they must
   read the same at the end.
2. Log in through the route, one browser context each (the self tier is cookie-only, so a bearer token would land on
   the wide view): `kubeadmin` (§3's cluster-admin column), `dana.lee` (the auditor column; `ClusterRoleBinding
   cluster-reader`, measured), `developer` (the self column). No temporary binding is needed: §2.8 measured all three.
3. For each: `/api/whoami`'s `visibility.scope` and `visibility.cluster_admin` (`all`/`true`, `all`/`false`,
   `self`/`false`); a screenshot of the tab strip, which must equal §3's for the column (14 tabs for `kubeadmin`;
   12 for `dana.lee` and `developer`, without KPIs and Cluster Configurations); and `#page=overview`, `#page=kpi`,
   `#page=clusters` and `#page=policy`, each a page or a refusal card as §3 says for that column.
4. The usage column has no persona on the lab: on the default settings the usage question and the cluster-admin
   question are the same one (`update clusterrolebindings`), so no reader passes one and not the other. It is proved
   in CI only.
5. The PVC UIDs again: unchanged.

## 6. What an operator sees, and what it costs

- In `docs/ACCESS_CONTROL.md`: §3, one row for each of the sixteen pages with a word per reader; §4, one row for each
  of the 44 routes with a word per reader, the gate it calls and whether the writes switch registers it, and
  `/report/**` in its own small table. The same tables CI reads.
- In CI: a red build when a route or page ships without a row, a row outlives its route, a reader is answered
  differently from the row, or a row names a gate the handler does not call. The failure names the route or page.
- Not seen: any change on the dashboard, its API, its chart or its RBAC. No image is built and no chart is published
  for this change; it rides no release.
- Time: the module runs in under a second (270 tests, §4.3's M0), the browser test in about five seconds (§4.4).
- Lines, from `git diff --numstat` on the applied tree (§4.4):

| file | added | removed |
|---|---|---|
| `local-development/tests/test_access_declaration.py` (new) | 269 | 0 |
| `local-development/tests/test_ui.py` | 63 | 0 |
| `local-development/tests/test_multicluster_visibility.py` | 29 | 16 |
| `local-development/tests/test_specs_index.py` | 12 | 0 |
| `docs/ACCESS_CONTROL.md` | 133 | 40 |
| `docs/specs/SPEC_T1_tier_model.md` | 7 | 2 |
| `docs/specs/README.md` | 1 | 1 |
| `docs/CHANGELOG.md` | 10 | 0 |
| `local-development/gsd/`, `charts/` | 0 | 0 |

The spec's own commit adds this file and its index row (`docs/specs/README.md`, 3 added and 2 removed, the count
included) and changes `local-development/tests/test_specs_index.py` (9 added, 4 removed: note 14); none of that is a block.

## 7. Implementation blocks

Applied in this order: blocks 1 to 5 are the tests, 6 to 13 the documents, 14 the CHANGELOG. Nothing under
`local-development/gsd/` or `charts/` changes.

### Block 1 — local-development/tests/test_access_declaration.py: the declaration test (T239-1, -2, -3, -4, -6, -7, -9)

The new module: the two tables parsed, `app.routes` walked, every row requested as every persona, the gate column checked, the pages compared (§3, §4).

<!-- block: local-development/tests/test_access_declaration.py | create -->

```python
"""The access declaration (#239, docs/specs/SPEC_G1_tier_declaration.md): `docs/ACCESS_CONTROL.md` §3 and §4 say
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
DOC = REPO / "docs" / "ACCESS_CONTROL.md"
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
    assert head, f"docs/ACCESS_CONTROL.md has no section {number}"
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
    token = root / "report-token"
    token.write_bytes(b"t" * 48 + b"\n")
    return build_app(_settings(db, cluster_secrets_writes_enabled=writes, housekeeping_enabled=housekeeping,
                               reporting_url="https://gsd-report.ns.svc:8443", reporting_token_file=str(token)),
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
    assert not missing, f"routes with no row in docs/ACCESS_CONTROL.md §4; add one each (§4 names the words):\n{rows}"


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
```

### Block 2 — local-development/tests/test_ui.py: the browser test of §3 (T239-5)

A server in §3's posture with one stub per tier, and one test per persona: the tab strip as a list, and each page's refusal card (§3.6, note 13). Inserted before `_home`, after `_open_as`, which it uses.

<!-- block: local-development/tests/test_ui.py | edit -->

Old text:

```python

def _home(page, base, user="alice"):
```

New text:

```python
# ── #239: the declared tabs (docs/ACCESS_CONTROL.md §3, SPEC_G1) ────────────────────────────────────
# §3 says, per persona, which tabs the strip draws and which pages are a refusal card. This loads every page as
# every persona and holds the page to it; tests/test_access_declaration.py holds §3 to the pages index.html can draw.

#: The reader each §3 persona is here, and what the stubs below let each one pass: exactly its own question.
DECLARED_READERS = {"self": "alice", "auditor": "auditor", "usage": "usage", "cluster-admin": "root"}
#: A page has painted its verdict: a card is drawn and nothing on it is still loading.
PAGE_SETTLED = """() => { const m = document.querySelector('#main');
  return !!m && !!m.querySelector('.card') && !m.innerText.includes('Loading…'); }"""


@pytest.fixture(scope="module")
def declared_server(tmp_path_factory):
    """The posture §3 declares: the proxy on, restrictions on, reporting on (Reports and Library are drawn only then)
    and the writes on, one stub per tier so each persona passes its own question and no other."""
    root = tmp_path_factory.mktemp("gsd-declared")
    db = str(root / "ui.db")
    _seed(db)
    token = root / "report-token"
    token.write_bytes(b"t" * 48 + b"\n")
    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X")],
        db_path=db, login_capture_enabled=True, oauth_proxy_enabled=True, cluster_secrets_writes_enabled=True,
        reporting_url="https://gsd-report.ns.svc:8443", reporting_token_file=str(token),
    )
    app = build_app(settings, run_poller=False)
    app.state.tier_resolver = _TierByName("auditor")
    app.state.usage_tier_resolver = _TierByName("usage")
    app.state.cluster_admin_resolver = _TierByName("root")
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
        raise RuntimeError("declared dashboard server did not start")
    yield base
    srv.should_exit = True
    thread.join(timeout=5)


class TestTheDeclaredTabs:
    """T239-5: the tab strip each persona is drawn, and the refusal card on each page, are §3's."""

    @pytest.mark.parametrize("persona", list(DECLARED_READERS))
    def test_the_tab_strip_and_every_refusal_are_the_declared_ones(self, page, declared_server, persona):
        from test_access_declaration import PAGES
        _open_as(page, declared_server, DECLARED_READERS[persona])
        drawn = page.eval_on_selector_all("nav.tabs .tab", "els => els.map(e => e.dataset.nav)")
        assert drawn == [row["page"] for row in PAGES if row["tab"] != "—" and row[persona] != "absent"], persona
        for row in PAGES:
            page.goto(f"{declared_server}/#page={row['page']}")
            page.reload()
            page.wait_for_function(PAGE_SETTLED, timeout=10_000)
            refused = page.locator("#main .scope-refusal").count() > 0
            assert refused == (row[persona] in ("refused", "absent")), (persona, row["page"], row[persona])


def _home(page, base, user="alice"):
```

### Block 3 — local-development/tests/test_multicluster_visibility.py: the sweep's names, derived from `app.routes` (T239-11)

The hand list `CLUSTER_ENDPOINTS` (16 of 17) is replaced by the routes themselves; `prod-ns` keeps its place (§3.8).

<!-- block: local-development/tests/test_multicluster_visibility.py | edit -->

Old text:

```python
CLUSTER_ENDPOINTS = ("groupsyncs", "groupsyncs/x/events", "groups", "groups/x", "users", "users/x", "logins",
                     "cluster-access", "bindings/findings", "user-bindings", "operator-configs", "membership-changes",
                     "binding-changes",
                     # #167's two. The sweep is what proves a handler answers `hidden` exactly as `unknown`,
                     # and a mutation shows it earns its place: delete `require_cluster` from
                     # `namespace_detail` and only the second of these fails (OB3, integration review, C8).
                     "namespaces", "namespaces/prod-ns",
                     "home")
```

New text:

```python
#: The `{name}` each cluster route is swept with, keyed by the segment before it; `x` where none is named. `prod-ns`
#: is #167's: a mutation shows the sweep earns its place there — delete `require_cluster` from `namespace_detail`
#: and only that route fails (OB3, integration review, C8).
SWEEP_NAMES = {"namespaces": "prod-ns"}


def _cluster_suffixes(app) -> list[str]:
    """Every `/api/clusters/{cluster_id}/…` route the app registers, as the suffix the sweep requests. Derived from
    `app.routes`, so a new cluster handler is swept the day it is added: the hand list it replaces had 16 of 17 and
    missed `kyverno` (#239, SPEC_G1)."""
    prefix = "/api/clusters/{cluster_id}/"
    suffixes = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if path.startswith(prefix):
            parts = path[len(prefix):].split("/")
            suffixes.append("/".join(SWEEP_NAMES.get(parts[i - 1], "x") if part == "{name}" else part
                                     for i, part in enumerate(parts)))
    return sorted(suffixes)
```

### Block 4 — local-development/tests/test_multicluster_visibility.py: the sweep test reads the derived list (T239-11)

One test over every cluster route, with a floor of 17 so a derivation that stops matching cannot pass empty.

<!-- block: local-development/tests/test_multicluster_visibility.py | edit -->

Old text:

```python
    @pytest.mark.parametrize("suffix", CLUSTER_ENDPOINTS)
    def test_every_cluster_handler_answers_hidden_like_unknown(self, client, suffix):
        """Codex, review D2: the twelve `/api/clusters/{id}/…` handlers, each measured — the same
        status and the same sentence, differing only by the id the caller sent (which is the
        caller's own input, not information about the server)."""
        for headers in (ROOT, ALICE):
            a = client.get(f"/api/clusters/dark/{suffix}", headers=headers)
            b = client.get(f"/api/clusters/no-such/{suffix}", headers=headers)
            assert a.status_code == b.status_code == 404, suffix
            assert a.json()["detail"].replace("dark", "X") == b.json()["detail"].replace("no-such", "X"), suffix
```

New text:

```python
    def test_every_cluster_handler_answers_hidden_like_unknown(self, client):
        """Codex, review D2: every `/api/clusters/{id}/…` handler the app registers, each measured — the same
        status and the same sentence, differing only by the id the caller sent (which is the
        caller's own input, not information about the server)."""
        suffixes = _cluster_suffixes(client.app)
        assert len(suffixes) >= 17, f"the sweep found only {suffixes}: the derivation from app.routes stopped matching"
        for suffix in suffixes:
            for headers in (ROOT, ALICE):
                a = client.get(f"/api/clusters/dark/{suffix}", headers=headers)
                b = client.get(f"/api/clusters/no-such/{suffix}", headers=headers)
                assert a.status_code == b.status_code == 404, suffix
                assert a.json()["detail"].replace("dark", "X") == b.json()["detail"].replace("no-such", "X"), suffix
```

### Block 5 — local-development/tests/test_specs_index.py: SPEC_T1's header says what was delivered (T239-8)

Appended after the file's last test; the spec's own commit changes other lines of this file (note 14), and this block touches none of them.

<!-- block: local-development/tests/test_specs_index.py | edit -->

Old text:

```python
            assert re.search(r"\bapp \d+\.\d+\.\d+", row["version"]), (fid, row["version"])

```

New text:

```python
            assert re.search(r"\bapp \d+\.\d+\.\d+", row["version"]), (fid, row["version"])


def test_t1_says_what_was_delivered_and_what_was_not() -> None:
    """#239 (SPEC_G1, T239-8): SPEC_T1 predates #322, which delivered its step T3 in another shape, and #239 delivers
    its declaration as SPEC_G1. A header still at `specified` invites someone to build from blocks main has outgrown,
    so the header names what was delivered and by which spec, and what is not built."""
    head = (SPECS / "SPEC_T1_tier_model.md").read_text().split("## How to read this spec", 1)[0]
    assert ROWS["T1"]["status"] != "specified", ROWS["T1"]["status"]
    delivered = re.search(r"^\| Delivered \| (?P<value>.+) \|$", head, re.M)
    assert delivered, "SPEC_T1's header has no Delivered row"
    for name in ("#322", "SPEC_T2", "SPEC_G1", "TIER_BY_SURFACE"):
        assert name in delivered["value"], f"the Delivered row does not name {name}"

```

### Block 6 — docs/ACCESS_CONTROL.md: §3, the pages: the introduction, the words and the table

Replaces main's ten-row tab table (§3.6).

<!-- block: docs/ACCESS_CONTROL.md | edit -->

Old text:

```markdown
| tab | ordinary reader | `cluster-reader` (auditor) | `cluster-admin` |
|---|---|---|---|
| Groups | their own groups | all | all |
| Namespace audit | grants affecting them | all | all |
| Logins | their own attempts | all | all |
| Usage | their own activity | **their own activity** | all |
| Reports | *For administrators only* | all | all |
| Overview | *For administrators only* | all | all |
| Access granted | their own grants, via their groups | all | all |
| RBAC policy | *For administrators only* | all | all |
| KPIs | *For cluster administrators only* | **absent** | all |
| Cluster Configurations | *For cluster administrators only* | **absent** | all |
```

New text:

```markdown
One row for every page the dashboard draws: its fourteen tabs, in the order of the tab strip, then the two pages
that have no tab of their own (the Reporting status page, opened from Reports, and the search page, opened from the
search box). The reader columns are §4's personas. A reader with no identity never sees the page: the proxy admits
nobody to `/` without a session, and `charts/group-sync-dashboard/values.yaml#skipAuthRegex` lists the only paths it
lets through. Reports, Library and Reporting status exist only with reporting on (`reporting.enabled`, on by
default); with it off, no reader is drawn those two tabs. Each reader cell is one word:

| word | what the reader gets |
|---|---|
| all | the page, with the whole cluster's rows |
| self | the page, narrowed to the reader's own rows and saying so |
| refused | the tab is drawn, and the page is a named refusal card |
| absent | no tab is drawn; reached by URL, the page is the refusal card |

The page decides none of this (§7): it draws what `/api/whoami` and each response's `scope` declare, and every
refusal is the server's 403 first. `local-development/tests/test_access_declaration.py` holds this table to the tabs and
pages `local-development/gsd/static/index.html` can draw, and `local-development/tests/test_ui.py#TestTheDeclaredTabs`
loads every page as every persona and holds the tab strip and each refusal card to it.

| page | tab | self | auditor | usage | cluster-admin | what a narrowed or refused reader sees |
|---|---|---|---|---|---|---|
| home | Home | self | self | self | self | their own access, at every tier by design (#158): an administrator's Home is theirs, never everyone's |
| overview | Overview | refused | all | refused | all | the refusal card: the Overview is the cluster's own health |
| kpi | KPIs | absent | absent | absent | all | no tab; by URL, the refusal card |
| groups | Groups | self | all | self | all | the groups they belong to |
| users | Users | self | all | self | all | their own row |
| bindings | Access granted | self | all | self | all | their own grants, through their groups, with the group named |
| policy | RBAC policy | refused | all | refused | all | the refusal card: the whole binding surface has no per-reader subset |
| kyverno | Kyverno | refused | all | refused | all | the refusal card: a policy finding is about the cluster, not the reader |
| nsaudit | Namespace audit | self | all | self | all | the namespaces and grants that reach them |
| logins | Logins | self | all | self | all | their own attempts |
| usage | Usage | self | self | all | all | their own activity; the auditor too, because Usage is the usage tier's (§2) |
| reports | Reports | refused | all | refused | all | the refusal card: reports are documents about the cluster |
| library | Library | refused | all | refused | all | the refusal card, as Reports |
| clusters | Cluster Configurations | absent | absent | absent | all | no tab; by URL, the refusal card |
| reporting | — | refused | all | refused | all | the refusal card, as Reports |
| lookup | — | self | all | self | all | the search over their own groups, users and namespaces |
```

### Block 7 — docs/ACCESS_CONTROL.md: §3, why the refused pages are refused

Main's paragraph named two refused tabs; there are six refused pages, and two absent ones.

<!-- block: docs/ACCESS_CONTROL.md | edit -->

Old text:

```markdown
Two tabs are **refused** rather than narrowed, because their content is about the cluster rather
than about any reader: the Overview is the cluster's own health, and RBAC policy is the whole
binding surface against the policy operator — the cluster-wide list, which has no honest per-reader
subset. (Access granted has one: a reader's own path, above.)
```

New text:

```markdown
The refused pages are refused rather than narrowed because their content is about the cluster rather
than about any reader: the Overview is the cluster's own health, RBAC policy is the whole binding
surface against the policy operator, Kyverno's findings are cluster-wide, and a report is a document
over the whole cluster. None has an honest per-reader subset. (Access granted has one: a reader's own
path, above.) KPIs and Cluster Configurations are left out of the strip rather than refused (#322):
the tab is not drawn for a reader the cluster-admin tier refuses.
```

### Block 8 — docs/ACCESS_CONTROL.md: §4, the declaration

Replaces main's twenty-one-row table: the posture, the personas, the words, the 44 rows, and `/report/**` in its own table (§3.1 to §3.5, note 7). The two asymmetries and the self-tier subsection after it are unchanged.

<!-- block: docs/ACCESS_CONTROL.md | edit -->

Old text:

```markdown
`scope` and `viewer` ride on every collection response so a client never has to guess.

| endpoint | at the self tier | at the wide tier |
|---|---|---|
| `/api/clusters/{c}/groups` | groups they belong to | all |
| `/api/clusters/{c}/groups/{name}` | 403 unless a member — **and a member's 200 names the group's bindings**, see below | all |
| `/api/clusters/{c}/users` | their own row (with `first_login_source`) | all |
| `/api/clusters/{c}/users/{name}` | 403 unless it is them — **their own 200 names the bindings reaching them**, see below | all |
| `/api/clusters/{c}/user-bindings` | their own grants | all |
| `/api/clusters/{c}/membership-changes` | changes affecting them | all |
| `/api/clusters/{c}/logins` | their own attempts | all |
| `/api/clusters/{c}/cluster-access` | their own gate status | all |
| `/api/alerts` | filtered to `SELF_ALERT_KINDS`; the `reconcile_error` detail is replaced with a generic sentence | all kinds, full detail |
| `/api/dashboard/activity` | their own rows | all — **usage tier only** |
| `/api/report/ticket` | **403** | a signed ticket for the report service, bound to this viewer |
| `/api/dashboard/reports` | their own runs | all — **usage tier only**, like activity |
| `/report/**` | the report service's API behind the same proxy, admitted only by a ticket (viewer) or the service token; a viewer without a ticket gets 401, a ticket for another identity 403 | — |
| `/api/clusters/{c}/bindings/findings` | **403** | all |
| `/api/clusters/{c}/operator-configs` | **403** | all |
| `/api/kpi` | **403** | **403** unless the reader passes the cluster-admin tier (#322) |
| `/api/clusterconfigs` and its four write routes | **403** | **403** unless the reader passes the cluster-admin tier (#322); the writes also need `clusterConfig.secrets.writes.enabled` |
| `/api/housekeeping/**`: the copies listing and the four delete routes (#542) | **403** | **403** unless the reader passes the cluster-admin tier (#322) with a proxy-verified identity; exist only with `housekeeping.enabled` |
| `/api/clusters` | reachable; cluster-wide `operator_configs` withheld | full card |
| `/api/clusters/{c}/groupsyncs` | full CR health **minus `ldap_filter` and `error_message`** | full row |
| `/api/clusters/{c}/groupsyncs/{name}/events` | unchanged at both tiers | same |
| `/api/whoami` | own identity + declared tier | same |
```

New text:

```markdown
This section is the declaration: one row for every route the application registers, keyed by method and
path, because `GET /api/clusterconfigs` and `POST /api/clusterconfigs` share a path and not a gate.
`local-development/tests/test_access_declaration.py` builds the app with every switch that registers a route turned
on, walks `app.routes`, and fails when a route has no row, when a row names a route the app does not serve, or when
any persona is answered differently from its row. A route that ships without a gate, or with a lower one, fails
CI. The table records the gates; it does not configure them (§10 does).

**The posture the rows describe:** the oauth-proxy on, `visibility.enabled: true`, the host cluster deciding
(`inherit`, §11) for every cluster the dashboard reads, reporting on, for the six rows registered `writes on`,
`clusterConfig.secrets.writes.enabled: true`, and, for the five rows registered `housekeeping on`, `housekeeping.enabled: true`
(the chart's default) with each write carrying the page's `X-GSD-Interaction` header. §8 says what changes with the proxy or the restrictions off, and §11
what a remote cluster's own policy changes; of these rows only `/api/alerts` reads every cluster, and its `scope` is
the narrowest across them, so a `remote-sar` or `self-only` cluster that does not widen the reader makes it `self`.

**The personas.** Each is one reader, so a path naming the reader's own group, user or namespace resolves:

| persona | what it passes |
|---|---|
| no identity | nothing: the proxy is on and sent no `X-Forwarded-User`. In a deployment the proxy lets a request through without a session only on the paths `skipAuthRegex` lists; this column is the app's own answer behind it |
| self | none of the three questions (§2) |
| auditor | `visibility.adminSar` only: a `cluster-reader` |
| usage | `visibility.usageAdminSar` only |
| cluster-admin | `visibility.clusterAdminSar` only. It grants the wide view and Usage (#322), so a `cluster-admin`, who passes all three, is answered the same |

**The words in the persona columns:**

| word | the answer |
|---|---|
| all | 200, and the body's `scope` is `all` (`visibility.scope` on `/api/whoami`) |
| self | 200, and the body's `scope` is `self` |
| 200 | 200, with no `scope` in the body |
| 403 | refused |
| 308 | a redirect to `/api` |
| admitted | past the gate: the write reaches its own checks, which its own tests hold |

**gate** names the function in `local-development/gsd/api.py` the handler calls, or `none`, and the test checks that
the handler calls it. **registered** is `always`, or `writes on` for the six routes that exist only with
`clusterConfig.secrets.writes.enabled`. `scope` and `viewer` ride on every collection response, so a client never has
to guess.

| method | path | registered | gate | no identity | self | auditor | usage | cluster-admin | notes |
|---|---|---|---|---|---|---|---|---|---|
| GET | `/api/clusters` | always | viewer_scope | 200 | 200 | 200 | 200 | 200 | reachable for everyone, because the cluster selector needs it on every tab; each row carries `visibility.scope` for this reader, and `operator_configs` is `null` below the wide tier |
| GET | `/api/clusters/{cluster_id}/groupsyncs` | always | viewer_scope | 200 | 200 | 200 | 200 | 200 | full CR health at every tier, minus `ldap_filter` and `error_message` below the wide tier (below) |
| GET | `/api/clusters/{cluster_id}/groupsyncs/{name}/events` | always | none | all | all | all | all | all | the same at every tier, by ruling |
| GET | `/api/clusters/{cluster_id}/groups` | always | viewer_scope | 403 | self | all | self | all | at self, the groups they belong to |
| GET | `/api/clusters/{cluster_id}/groups/{name}` | always | viewer_scope | 403 | self | all | self | all | at self, 403 unless a member; a member's 200 names the group's bindings (below) |
| GET | `/api/clusters/{cluster_id}/users` | always | viewer_scope | 403 | self | all | self | all | at self, their own row (with `first_login_source`) |
| GET | `/api/clusters/{cluster_id}/users/{name}` | always | viewer_scope | 403 | self | all | self | all | at self, 403 unless it is them; their own 200 names the bindings reaching them (below) |
| GET | `/api/clusters/{cluster_id}/user-bindings` | always | viewer_scope | 403 | self | all | self | all | at self, their own grants |
| GET | `/api/clusters/{cluster_id}/membership-changes` | always | viewer_scope | 403 | self | all | self | all | at self, changes affecting them |
| GET | `/api/clusters/{cluster_id}/binding-changes` | always | viewer_scope | 403 | self | all | self | all | at self, rows naming them or a group they belong to |
| GET | `/api/clusters/{cluster_id}/logins` | always | viewer_scope | 403 | self | all | self | all | at self, their own attempts |
| GET | `/api/clusters/{cluster_id}/cluster-access` | always | viewer_scope | 403 | self | all | self | all | at self, their own gate status |
| GET | `/api/clusters/{cluster_id}/namespaces` | always | viewer_scope | 403 | self | all | self | all | at self, the namespaces their memberships or grants reach |
| GET | `/api/clusters/{cluster_id}/namespaces/{name}` | always | viewer_scope | 403 | self | all | self | all | at self, 403 before any lookup unless it reaches them; then their own paths only |
| GET | `/api/clusters/{cluster_id}/home` | always | viewer_scope | 403 | self | all | self | all | the reader's own access at every tier; `scope` names the tier that decided |
| GET | `/api/alerts` | always | viewer_scope | self | self | all | self | all | at self, the kinds in `SELF_ALERT_KINDS`, with the `reconcile_error` detail replaced by a generic sentence |
| GET | `/api/whoami` | always | viewer_scope | 200 | self | all | self | all | their identity and declared tier; with no identity, no `visibility` claim |
| GET | `/api/clusters/{cluster_id}/bindings/findings` | always | require_admin_tier | 403 | 403 | all | 403 | all | the cluster's whole binding surface |
| GET | `/api/clusters/{cluster_id}/operator-configs` | always | require_admin_tier | 403 | 403 | all | 403 | all | the operator's configuration |
| GET | `/api/clusters/{cluster_id}/kyverno` | always | require_admin_tier | 403 | 403 | all | 403 | all | Kyverno's policy findings, cluster-wide |
| GET | `/api/report/ticket` | always | require_admin_tier | 403 | 403 | 200 | 403 | 200 | a signed ticket for the report service, bound to the viewer; 404 with reporting off |
| GET | `/api/dashboard/activity` | always | usage_scope | 403 | self | self | all | all | at self, their own rows; `userActivity.visibility: all` widens it for everyone (§10) |
| GET | `/api/dashboard/reports` | always | usage_scope | 403 | self | self | all | all | at self, their own report runs |
| GET | `/api/kpi` | always | require_cluster_admin | 403 | 403 | 403 | 403 | all | the cluster-admin tier, whatever `visibility.enabled` says (§8) |
| GET | `/api/clusterconfigs` | always | require_cluster_admin | 403 | 403 | 403 | 403 | all | the cluster-admin tier, whatever `visibility.enabled` says (§8) |
| POST | `/api/clusterconfigs` | writes on | _writes_gate | 403 | 403 | 403 | 403 | admitted | an identity and the cluster-admin tier first, then the switch |
| PUT | `/api/clusterconfigs/{name}/credential` | writes on | _writes_gate | 403 | 403 | 403 | 403 | admitted | as above |
| DELETE | `/api/clusterconfigs/{name}` | writes on | _writes_gate | 403 | 403 | 403 | 403 | admitted | as above |
| POST | `/api/clusterconfigs/test` | writes on | _writes_gate | 403 | 403 | 403 | 403 | admitted | as above |
| POST | `/api/clusterconfigs/{name}/refresh` | writes on | _writes_gate | 403 | 403 | 403 | 403 | admitted | as above |
| POST | `/api/clusterconfigs/{name}/rejoin` | writes on | _writes_gate | 403 | 403 | 403 | 403 | admitted | as above |
| GET | `/api/housekeeping/copies` | housekeeping on | _housekeeping_gate | 403 | 403 | 403 | 403 | 200 | the database copies on this pod's volume (#542); an identity and the cluster-admin tier |
| DELETE | `/api/housekeeping/copies/{kind}/{name}` | housekeeping on | _housekeeping_write | 403 | 403 | 403 | 403 | admitted | an identity, the cluster-admin tier, then the page's header; the newest copy of each directory is refused (409) |
| POST | `/api/housekeeping/copies/cleanup` | housekeeping on | _housekeeping_write | 403 | 403 | 403 | 403 | admitted | as above; a preview without `confirm`, a delete of exactly that set with it (409 when it changed) |
| DELETE | `/api/housekeeping/reports/{run_id}` | housekeeping on | _housekeeping_write | 403 | 403 | 403 | 403 | admitted | as above; the report service deletes it at the dashboard's request with the service token |
| POST | `/api/housekeeping/reports/cleanup` | housekeeping on | _housekeeping_write | 403 | 403 | 403 | 403 | admitted | as above |
| GET | `/metrics` | always | none | 200 | 200 | 200 | 200 | 200 | public by ruling, so it carries no name |
| GET | `/healthz` | always | none | 200 | 200 | 200 | 200 | 200 | the liveness probe |
| GET | `/readyz` | always | none | 200 | 200 | 200 | 200 | 200 | the readiness probe |
| GET | `/api/version` | always | none | 200 | 200 | 200 | 200 | 200 | the running build |
| GET | `/api/openapi.json` | always | none | 200 | 200 | 200 | 200 | 200 | FastAPI's own schema route, behind the proxy like the data it describes |
| GET | `/api` | always | none | 200 | 200 | 200 | 200 | 200 | the schema browser |
| GET | `/api/redoc` | always | none | 200 | 200 | 200 | 200 | 200 | the reference rendering |
| GET | `/api/docs` | always | none | 308 | 308 | 308 | 308 | 308 | the conventional path, redirected to `/api` |
| GET | `/` | always | none | 200 | 200 | 200 | 200 | 200 | the page; it draws what `/api/whoami` declares (§3) |
| GET | `/signed-out` | always | none | 200 | 200 | 200 | 200 | 200 | the proxy's sign-out target; it reads no identity header |
| GET | `/static/index.html` | always | none | 200 | 200 | 200 | 200 | 200 | the page again, rendered, shadowing the raw file |
| GET | `/static/signed-out.html` | always | none | 200 | 200 | 200 | 200 | 200 | the sign-out page again, rendered, shadowing the raw file |
| GET | `/static/{path}` | always | none | 200 | 200 | 200 | 200 | 200 | the stylesheet, icon and vendored scripts (a mount; it refuses the page sources) |

**Served by another service**, behind the same proxy, and not a route of this application:

| path | served by | who is admitted |
|---|---|---|
| `/report/**` | the report service | a ticket from `/api/report/ticket` (a viewer) or the service token; a viewer without a ticket gets 401, a ticket for another identity 403 |
```

### Block 9 — docs/ACCESS_CONTROL.md: §5, the fourth user of `require_admin_tier`

Note 11.

<!-- block: docs/ACCESS_CONTROL.md | edit -->

Old text:

```markdown
    │     used by: bindings/findings, operator-configs, mint ticket (/api/report/ticket)
```

New text:

```markdown
    │     used by: bindings/findings, operator-configs, kyverno, mint ticket (/api/report/ticket)
```

### Block 10 — docs/specs/README.md: the index: SPEC_T1 is `in progress`

The whole row is the Old text: with SPEC_G1's row in the index, the issue link and the status alone occur twice.

<!-- block: docs/specs/README.md | edit -->

Old text:

```markdown
| T1 | [`SPEC_T1_tier_model.md`](SPEC_T1_tier_model.md) — the named dashboard tier model: self / auditor / admin / cluster-admin, one declared SAR question each | T — tiers | — | app and chart minor bumps per step, assigned at each step's PR | [#239](https://github.com/ephico2real2/group-sync-dashboard/issues/239) | specified |
```

New text:

```markdown
| T1 | [`SPEC_T1_tier_model.md`](SPEC_T1_tier_model.md) — the named dashboard tier model: self / auditor / admin / cluster-admin, one declared SAR question each | T — tiers | — | app and chart minor bumps per step, assigned at each step's PR | [#239](https://github.com/ephico2real2/group-sync-dashboard/issues/239) | in progress |
```

### Block 11 — docs/specs/SPEC_T1_tier_model.md: SPEC_T1's header: the programme row no longer claims #114 or #230's pair

§3.7.

<!-- block: docs/specs/SPEC_T1_tier_model.md | edit -->

Old text:

```markdown
| Programme | Named dashboard tiers (#239), steps T1 / T2 / T3 — after the 2026-09 programme's ladder; T2 closes #114, T3 folds in #230's pair |
```

New text:

```markdown
| Programme | Named dashboard tiers (#239), steps T1 / T2 / T3 — after the 2026-09 programme's ladder. As first written, T2 closed #114 and T3 folded in #230's pair; both are superseded (the Delivered row) |
```

### Block 12 — docs/specs/SPEC_T1_tier_model.md: SPEC_T1's header: the status and the Delivered row

§3.7; `test_specs_index.py` holds the status equal to the index row's (block 10).

<!-- block: docs/specs/SPEC_T1_tier_model.md | edit -->

Old text:

```markdown
| Status | specified |
```

New text:

```markdown
| Status | in progress |
| Delivered | Step T3 by #322, in another shape: one `visibility.clusterAdminSar` question gates KPIs and the whole Cluster Configurations tab and grants the lower host tiers (SPEC_T2, released in app 0.35.0). The declaration T1 asked of `TIER_BY_SURFACE` — every route and tab with its tier, and a test failing on one left out — by #239 as SPEC_G1, in `docs/ACCESS_CONTROL.md` §3 and §4 rather than in code. Not built, and open for the operator on #239: the `TIER_BY_SURFACE` registry, `visibility.tiers` on `/api/whoami`, and the `adminSar` → `auditorSar` and `usageAdminSar` → `adminSar` renames. #114 was closed as not planned on 2026-09-27. Re-derive any block below from main before building from it |
```

### Block 13 — docs/specs/SPEC_T1_tier_model.md: SPEC_T1's orchestrator's notes: why the status moved

§3.7. The body below the notes is unchanged.

<!-- block: docs/specs/SPEC_T1_tier_model.md | edit -->

Old text:

```markdown

The operator's rulings this spec rests on, one line each, verbatim where quoted:
```

New text:

```markdown

**2026-10-01 (#239, SPEC_G1): the status is `in progress`, not `specified`.** #322 delivered step T3 in another
shape and SPEC_G1 delivers the declaration; the header's Delivered row says what, and what is not built. The body
below is the design of 2026-09-20 and is kept as written.

The operator's rulings this spec rests on, one line each, verbatim where quoted:
```

### Block 14 — docs/CHANGELOG.md: the CHANGELOG entry

Under `## Unreleased`, as tests and docs: no application or chart release carries it.

<!-- block: docs/CHANGELOG.md | after: ## Unreleased -->

```markdown

- **Every route and page declares its tier, and CI holds the code to it (#239, SPEC_G1).** `docs/ACCESS_CONTROL.md`
  §4 has one row for each route the application registers (44 with the cluster-configuration writes on), keyed by
  method and path, naming what each of five readers gets: no identity, self, auditor, usage and cluster-admin. §3 has
  one row for each page: the fourteen tabs, the Reporting status page and the search page. A new test builds the app,
  walks `app.routes` and requests every row as every reader, so a route with no row, a row for a route that is gone,
  or a route answering a reader differently from its row fails the suite; a browser test holds each reader's tab
  strip and refusal cards to §3, and the hidden-cluster sweep now covers every cluster route, `kyverno` included.
  `SPEC_T1`'s status is `in progress`, with what #322 and #239 delivered. Nobody gains or loses a route, a row or a
  tab: tests and docs only, no application or chart change.
```
