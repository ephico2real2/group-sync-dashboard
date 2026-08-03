# API contract — the rules a new endpoint must satisfy

The schema is published at **`/api`** (Swagger UI), `/api/docs` (redirects there),
`/api/redoc`, and `/api/openapi.json`. It is generated from the code, so it cannot describe
an endpoint that does not exist — but it can happily describe one badly, and a generated
document that nobody checks drifts into being decoration.

`tests/test_api_contract.py` enforces every numbered rule below. If you add an endpoint and
skip the documentation, the suite fails and names the endpoint. That is deliberate: this
repository has already shipped an endpoint whose `(cluster-scoped)` namespace sentinel was
undiscoverable, and a chart value nobody documented for six weeks. Documentation that
depends on remembering is documentation that lags.

## Why the docs sit under `/api` and not at FastAPI's `/docs`

`oauthProxy.skipAuthRegex` admits `^/(healthz|readyz|metrics)$` and nothing else. Putting the
schema under `/api` means the proxy authenticates it exactly like the data it describes.

That is not ceremony. The schema names every endpoint, parameter and field this dashboard
exposes — which is a map of the cluster's RBAC surface, and of which namespaces and groups
are interesting enough to have endpoints. It belongs behind the same door as the data.

## The rules

**R1 — Every route has a docstring, and its first line is a sentence.**
FastAPI uses the docstring as the endpoint description; without one the schema shows a bare
path and the reader has to open the source. The first line becomes the summary, so it must
stand alone — "Roles granted DIRECTLY to a user" and not "Handler for the user endpoint".

**R2 — Every query parameter has a `description`.**
Use `Query(default=..., description="...")`. A parameter named `namespace` looks obvious and
is not: `/user-bindings?namespace=(cluster-scoped)` is the only way to ask for cluster-scoped
rows, because the underlying value is `''` and an empty query string is indistinguishable
from an absent one. Nobody guesses that. It has to be written down where they are looking.

**R3 — Anything that can grow without bound is paged, and says so.**
A list endpoint whose size follows cluster size takes `limit` and `offset`, and the response
carries `total` — counted BEFORE the limit — plus `truncated`. Order before you limit, so a
truncated page is the *worst* N and not an arbitrary N.

This rule exists because it was broken twice. The direct-grant list was unbounded at the
store, the API and the renderer simultaneously. The activity endpoint capped rows at 500 and
returned no total, so the Usage tab reported 167 days where the truth was 364.

**R4 — Timestamps are UTC and end in `Z`.**
No endpoint returns a local time. `TZ` on the container moves log lines only.

**R5 — A handler that calls the store more than once is `@consistent`.**
Otherwise its parts come from different snapshots and the response can contradict itself.
`tests/test_read_snapshot_scope.py` checks what happens *inside* a snapshot; this rule is
about taking one at all.

**R6 — New endpoints are `GET`.**
The ServiceAccount is read-only by design. If a change needs a write, it needs the argument
in `docs/unmanaged-audit-design.md` first. A write path was proposed there, built, measured
against a live cluster and then removed, because Kubernetes privilege-escalation prevention
caps what an RBAC reader can ever patch; that reasoning applies to any successor.

**R7 — `include_in_schema=False` needs a comment saying why.**
There is exactly one today: the `/api/docs` redirect, hidden because it is an alias rather
than an endpoint. Anything else hidden from the schema is invisible to every reader who
trusts it, so the exemption is deliberate and explained or it is not taken.

## Citing code from a document

Cite a **name**, never a line number: `` `gsd/store.py#Store.groups` ``. The anchor is a def, a
class, a `Class.method`, a module-level constant, or — in a Helm template, where there are no
symbols — any distinctive substring, usually the key the surrounding comment documents
(`` `templates/rbac.yaml#leases` ``). A citation with no anchor means the whole file is the
subject.

`test_docs_citations.py` resolves every anchor: Python through the AST, so `Store.groups` works
even though that exact string never appears in the file, and everything else by content. It also
**fails the build on any `path:123` citation**, because that format is the reason this rule
exists.

Line numbers were the convention until 2026-08-03 and rotted continuously — any edit above the
line invalidates it, which is most edits. The check that replaced them can only prove a line
exists, not that it still says the same thing, and two citations in one paragraph of
`reference-architecture.md` were found pointing at unrelated code while the suite was green
(`gsd/api.py` 487-489 → 615-617, `gsd/store.py` 1156-1159 → 1197-1200). Converting all 219 of
them surfaced eight more that were already wrong, including one off by 42 lines.

The remaining limitation, stated because it is not obvious: an anchor proves the citation points
at something real, not that the prose describes it correctly. Renaming a function and forgetting
the docs is now caught. Changing what a function does and leaving the prose stale is not.

## When you add an endpoint

1. Write the docstring first. If the first sentence is hard, the endpoint is doing two things.
2. Give every parameter a `description`.
3. Decide whether the result can grow with the cluster. If it can, apply R3 now — retrofitting
   paging means changing the store, the API and the renderer together, which is how the
   defect above stayed alive across three layers.
4. Run `pytest tests/test_api_contract.py`. It will tell you which rule you missed.
5. Check `/api` renders it the way you meant. The schema is the reader's first contact with
   this service and usually their only one.

## What the contract deliberately does not cover

Response *shapes* are not schema-typed: handlers return `dict`, so the spec documents the
endpoint but not its fields. Typing all of them with Pydantic models would be a large change
for a read-only API whose consumer is one page in the same repository, and half-typing them
would be worse than the honest gap. Recorded here so the omission is a decision rather than
an oversight; `docs/reference-architecture.md` carries the data model in the meantime.
