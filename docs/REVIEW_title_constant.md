# Review: the dashboard's name in one place

Adversarial review of PR #43 before merge, in the shape `docs/REVIEW_group_search.md` set. Codex
ran the pass read-only against `git diff main...feat/configurable-title`. The Cursor pass is still
unavailable (its CLI is not logged in on the machine).

Citations are by symbol (`file#symbol`), never by line, so this file stays true after the next edit.

## The change

The header used to be a literal in five files, and the previous rename (`8fc97a8`) changed one of
them and left the rest to be caught up by hand. Now `gsd.TITLE` is the name, the two HTML files carry
a `__GSD_TITLE__` token, `gsd/api.py#named_page` fills it, HTML-escaped, and the API docs read the
same constant. `tests/test_title.py` holds every surface to it, including the README heading, which
cannot import a Python constant.

## What was claimed, and what came back

| Claim | Verdict | Note |
|---|---|---|
| The pages are served as before except for the name, with `Cache-Control` unchanged | **refuted** | Cache-Control survived, but the first version returned a bare `HTMLResponse`: no `ETag`, no `Last-Modified`, and `If-None-Match` answered 200 with the full 181,769 bytes. See below for what the old handler actually did. |
| The token cannot reach a reader | **refuted** | The `/static` mount serves the whole directory, source pages included: measured 200 at `/static/index.html` with the token unfilled. |
| Escaping is right for both text nodes | confirmed | |
| The JS never rewrites the header; the cluster suffix comes from the scope-note span | confirmed | `index.html#renderScopePill` and the `scope-note` assignment are unchanged. |
| Reading the file per request is acceptable | **refuted** | A 181 KB synchronous read per request, and, with no validator, a full transfer per reload. |
| The tests hold what they claim | confirmed | The monkeypatch of `gsd.api.TITLE` reaches `named_page`, which reads the module global at call time. |
| The old names are gone from shipped code | **refuted** | "GroupSync dashboard" survived in the package docstring and the favicon's accessible label; the guard test only searched for the pre-rename header. |

## What the research settled before fixing

Checked against the sources rather than from memory, on the operator's instruction:

- **Substitution vs a template engine.** FastAPI's documented mechanism for HTML with values is
  `Jinja2Templates`, which needs the `jinja2` dependency; Starlette's implementation enables
  autoescaping but sets no cache headers itself. For one text node in two files an escaped token
  substitution is equivalent and adds no engine. The page contains no Jinja-style braces, so the
  door stays open.
- **Caching.** MDN's pattern for HTML that must always be fresh is `Cache-Control: no-cache` with
  `ETag` and `Last-Modified`, answered by a bodiless `304`; `no-cache` permits storing and forbids
  reuse without revalidation. RFC 9110 §15.4.5: a 304 MUST carry any of `Date`, `Cache-Control`,
  `Content-Location`, `ETag`, `Expires` and `Vary` that the 200 would have carried, MUST NOT
  carry a body, and SHOULD NOT carry other representation metadata (`Last-Modified` is the
  example given, useful only when there is no ETag); §13.1.2: `If-None-Match` uses weak
  comparison, over a comma-separated list; §5.6.7: an HTTP-date is always GMT.
- **What the old handler did.** Starlette's `FileResponse` computes an ETag from mtime and size and
  sets `Last-Modified`, but never answers a conditional request; only `StaticFiles` does (its
  `is_not_modified`). So the old `/` sent validators and always answered 200 with the body. The
  review's 304 was measured on `/static/index.html`, which the mount served.
- **Route precedence.** Starlette's router tries routes in registration order and the first full
  match wins, so a route declared before the `/static` mount shadows the file the mount would
  serve. `include_in_schema=False` is FastAPI's documented way to keep such a route out of the
  OpenAPI schema, which this repo already uses for the docs-UI routes.

## What changed because of it

- `gsd/api.py#named_page` renders once per file and name (cached on the file's mtime and the
  constant, keeping the newer render if two threads race), sends a strong `ETag` over the rendered
  body plus `Last-Modified` on the 200, compares `If-None-Match` weakly over a list, falls back to
  `If-Modified-Since` only when no tag is offered and only for a GMT date (a zone-less value is not
  an HTTP-date and could have answered 304 for a moment the client never named — the re-review's
  finding), and answers `304` with `Cache-Control` and `ETag` and no body. Better than the
  `FileResponse` it replaced, which never answered a 304.
- Two routes ahead of the mount serve the rendered pages at `/static/index.html` and
  `/static/signed-out.html`, out of the schema, documented in `API.md`.
- The package docstring and the favicon label no longer name the product; the guard test searches
  for both old names.
- Tests added for each of the above.

Sources: FastAPI templates and path-operation configuration docs; Starlette `staticfiles.py`,
`responses.py`, `routing.py`, `templating.py`; MDN HTTP caching guide; RFC 9110 §13.1.2, §15.4.5.
