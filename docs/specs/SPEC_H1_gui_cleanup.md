# SPEC H1 — delete report runs and database copies from the page: one item, or a one-off cleanup previewed and confirmed, for the cluster-admin tier, recorded (#542)

| | |
|---|---|
| Programme | none: the operator's request of 2026-10-02 (#542), scheduled ahead of #532 and Epic G |
| Batch | H — housekeeping |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 3.1.0, chart 0.62.0 |
| Version note | The next free MINOR is filled at implementation. The change is image content (both services and the page) and adds a chart value, so the implementing pull request runs `local-development/prepare-release.py --app <next free MINOR> --chart <next free MINOR> --no-commit "…"`: the chart takes a MINOR because a value is added (the index's version ladder), not the PATCH `--app` alone derives. No block carries a version field. Read from `docs/specs/README.md` on `2d20d0fb` (application 3.0.0, chart 0.61.3), the numbers already claimed are G3 (app 3.1.0, chart 0.61.6), G2 (app 3.2.0, chart 0.63.0), G4 (chart 0.61.4 and 0.61.5) and W1 (chart 0.62.0), so the next free pair above all of them, keeping the rows' order, is app 3.3.0 and chart 0.64.0. This spec is scheduled ahead of Epic G: under the rule SPEC_E5 states (`local-development/tests/test_specs_index.py#test_a_spec_the_changelog_has_not_begun_names_versions_the_tree_has_not_reached`), whichever implementation merges first takes the next free numbers then, and in the same pull request moves every `specified` spec whose numbers are no longer above the tree, in its header and its index row, keeping its MINOR or PATCH |
| Issue | [#542](https://github.com/ephico2real2/group-sync-dashboard/issues/542) |
| Status | merged |
| Source | OB1-lite's research and specification of 2026-10-02, written before any code from #542 (its body, "The change", with the operator's decisions of 2026-10-02) and the mandate's design questions. Measured on main `2d20d0fb` (application 3.0.0, chart 0.61.3) on this machine (Python 3.14.7, FastAPI 0.141.1, Starlette 1.6.0, helm v4, Chromium through Playwright). The CRC lab was down during authoring (the operator was rebooting it): its figures are the ones #542 and the mandate measured on 2026-10-02, cited as such, and every further lab read is stated as not measured, with its command (§5). §7's blocks were cut from a copy of `2d20d0fb` with the design implemented and proved against a clean worktree of this spec's commit (§4.3) |

## How to read this spec

**The point in one sentence: a cluster administrator can now delete a finished report run or an old database copy
from the page, or clean either up once with a tighter bound, and the page shows exactly what will go before
anything goes; nothing is saved, so the chart's retention values stay the only standing policy.**

Plainly, what changes:

- **Who.** Only a reader who passes the cluster-admin tier (#322, `visibility.clusterAdminSar`), with an identity
  the OAuth proxy verified. Everyone else sees no control, and the API refuses them with the tier's own sentence,
  `For cluster administrators only. …`.
- **What.** Report runs that have finished (never one that is queued or running), and the database copies in
  exactly three directories on the dashboard's data volume: the scheduled backups (`config.backup.dir`,
  `/data/backup`), `pre-upgrade/` and `pre-restore/` beside the database. The newest copy in each of the three is
  always kept, so a restore always has a copy to restore and a way back.
- **Where.** The Library tab's run drawer (delete this run) and a new **Clean up** card under the Library's
  sections; the KPI page's new **Database copies** card under the Backups card.
- **How.** One item: **Delete**, then **Confirm delete**. A cleanup: pick the bound, press **Preview**, read the
  list, press **Delete these N**. The confirm carries a digest of the previewed list; if the list changed in
  between (a new backup landed, retention removed a run), the server refuses with 409 and shows the new list.
- **Recorded.** One log line per deleted item naming the person, and a counter on `/metrics` by kind, with no
  names.
- **Switch.** `housekeeping.enabled: true` in the chart, on by default because it costs no RBAC, credential or
  second image. Off, neither pod registers a delete route and the page shows no control.

§1 is the mandate. §2 is the research, each source quoted with what it settles. §2a weighs the alternatives and
reconciles each external claim with this repository's code. §3 is the design, one rule per subsection with its reason
and, for each deletion path, the safety property as a budget with its scope. §4 is the tests, each failing without
the change for a stated reason. §5 is the lab walk the implementing pull request runs. §6 is what an operator sees
and what it costs. §7 is the whole change as implementation blocks (`docs/specs/README.md`, "Implementation
blocks"), applied to a clean tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_H1_gui_cleanup.md . --apply

Line citations into code at `2d20d0fb` are written as plain text, file:line, to keep them apart from the maintained
`path#anchor` citations. This spec's own row in the index moves through the lifecycle by the orchestrator's hand; no
block touches it. A block found wrong during implementation is corrected here, with the reason under these notes,
before it is applied again.

## Orchestrator's notes

The mandate's eight design questions, settled on "easy to manage, best practice" (the operator's rule of
2026-09-05), with the evidence each rests on; then the corrections research made, and the two questions only the
operator can answer.

1. **The report service's authority for a delete: (b), the dashboard deletes server-to-server with the service
   token, after its own cluster-admin gate.** Measured: the ticket is built to carry the wide tier and nothing
   else. `mint` refuses any other tier ("only the wide tier is ever minted", `local-development/gsd/reporting/ticket.py#mint`)
   and `verify` refuses a ticket without it (`#verify`, "ticket does not carry the wide tier"); the report
   service's `Principal` has two kinds, `viewer` and `service` (`local-development/gsd/reporting/server.py#Principal`), and the
   service holds no cluster credential (the chart's values comment on `reporting`), so the cluster-admin tier can
   only be decided in the dashboard. Option (a) would add a second ticket scope to a protocol three reviews hardened
   (C3), and it buys no narrower trust: the ticket's HMAC key is the service token itself, so whoever holds the
   token can already mint any ticket. Option (b) keeps one gate and one audit in one process, beside the copies,
   which are the dashboard's own files anyway, and uses the client the poller already uses for the usage pull
   (`local-development/gsd/poller.py#Poller._pull_report_usage`). The report service's two new routes accept the
   service token only (`dashboard_only`), and exist only with the switch (note 7), so where the operator turns the
   deletes off the token gains no power to delete.
2. **Where the controls live.** Report runs: the Library tab (SPEC_E1), a two-step **Delete this run** in the
   run drawer's actions and a **Clean up** card below the sections. DB copies: a **Database copies** card on the KPI
   page, under SPEC_E6's Backups card. Measured: the KPI page and its route are already the cluster-admin tier
   (`require_cluster_admin` in `/api/kpi`, local-development/gsd/api.py:2873 at `2d20d0fb`; the page draws it only
   when `clusterAdmin()` is true). Below the tier the page draws no control (T542-8) and the API refuses with the
   tier's sentence (T542-1).
3. **The bounds, kept small.** Report runs: `older_than_days` (0 is any age) and `keep_newest` per (schedule,
   cluster), applied together, manual runs being one group per cluster; and a `scope` of all runs, the manual
   runs, or one schedule by name, including a schedule no longer configured, which is how the 70 runs of the retired
   `nightly-namespace-access` (#541) can be cleaned up. Copies: `older_than_days`, over one directory or all three.
   Nothing else: a byte budget or a per-cluster filter would be a second policy language beside the chart's.
4. **Never doomed.** A queued or running run (the per-run delete answers 409; a cleanup never lists one, as
   `prune` never dooms one: `local-development/gsd/reporting/artifacts.py#ArtifactStore.prune`); the newest copy in each directory
   (§3.6); and anything outside the three directories: a name is matched against the directory's own listing and
   never joined onto a path, symlinks are never listed (T542-5).
5. **The record.** One `event-name key=value` line per deleted item through #245's `event`
   (`local-development/gsd/clusterconfig/events.py#event`): `report-run-deleted run=… report=… cluster=… schedule=… bytes=… by=<viewer>`
   and `db-copy-deleted kind=… copy=… directory=… bytes=… by=<viewer>`; the record's timestamp is the when. The field is
   `copy=`, not `name=`: `event`'s own second parameter is called `name`, and the first version of the implemented
   copy raised `TypeError: event() got multiple values for argument 'name'` (measured, then corrected). And one
   counter, `gsd_housekeeping_deleted_total{kind}`, whose only label is a closed set of four words (T542-7).
6. **Concurrency** is §3.7: run deletions share `prune`'s lock; copy deletions are serialised per process, the
   backup rotation is tolerated in both orders, and the digest makes a confirm that lands on another replica, with
   another set, a 409.
7. **The chart: one switch, `housekeeping.enabled: true`.** It exists because the dashboard's API is read-only at
   the code's default by design (`local-development/tests/test_api_contract.py#test_r6_the_api_is_read_only`), these are the first
   routes that delete evidence, and an estate whose policy is that only the standing retention removes evidence
   needs a way to say so in its values file. On by default under the chart's defaults rule (no RBAC, no credential,
   no second image, no cluster-wide write): measured, every rendered Role, ClusterRole and binding, rule by rule, is
   63 lines before and 63 after, REMOVED 0, ADDED 0 (§4.3). The application's own default stays off, as
   `cluster_secrets_writes_enabled`'s does, so R6's GET-only default and the report service's two-non-GET contract
   hold unchanged; the chart renders the value into both pods.
8. **Recovery mode (SPEC_E2).** The app does not serve then, so nothing in this feature runs; `restore-db.sh`, the
   runbook's restore path and its undo are unchanged (§3.12).

**Corrections and observations from research.**

9. **The 409, not 412.** The mandate names HTTP `If-Match` as a precedent. RFC 9110 §15.5.13 reserves 412 for
   "conditions given in the request header fields"; the preview's digest is a field of the request body, as the
   preview itself is a body and not a representation of the target resource. Kubernetes answers a failed delete
   precondition, which is likewise in the body (`DeleteOptions.preconditions`), with 409 (§2.2). So 409, with the
   new preview in the body, as RFC 9110 §15.5.10 asks: "enough information for a user to recognize the source of the
   conflict".
10. **`pre-restore/` holds three shapes, not one.** The issue counts "7 `<stamp>/gsd.db` directories plus a
    `pre-upgrade-…db` file". The committed walk records show `restore-db.py` stamps a kept set with microseconds
    (`20261002T013241.786235Z/`), the runbook's manual fallback with whole seconds (`20261002T150951Z`), and a copy
    moved aside per runbook §6 brings its `.sha256` with it; an interrupted keep leaves `<stamp>.tmp/`. The listing
    accepts both stamps, takes a sidecar with its copy, and never lists a `.tmp` (§2.6, §3.5).
11. **`/data/report` is out of scope, proved.** It is the report service's snapshot source (`local-development/gsd/reporting/snapshot.py#newest_snapshot`), written by the
    dashboard's leader every `reporting.snapshot.intervalSeconds` (300) and rotated to `keep: 2` by the same
    `_vacuum_into` (`local-development/gsd/store.py#Store.snapshot`). A deletion there frees nothing durable (the next snapshot
    replaces it within five minutes) and deleting the newest makes the report service's `/readyz` 503 and every run
    fail until then (`readyz` reads `newest_snapshot`). The mandate's lean is right.
12. **Two observations outside #542, for the operator** (open questions A and B below).

**Open questions only the operator can answer.**

- **A.** The top-level `README.md` "What it shows" still says "Eight tabs" and describes neither the Library nor the
  KPI page, and "The one thing it writes" describes the removed `annotate` mode (read at `2d20d0fb`). There is
  therefore no user-doc section for the Library or the Backups card to extend; this spec updates `API.md`, the
  chart README, the runbook and `ACCESS_CONTROL.md`. Should a README refresh be filed as its own issue?
- **B.** SPEC_E6's Backups card prints `config.backup.dir` in its heading, unwrapped: on the browser rig, whose
  temporary path is long, that heading ends at 461 px on a 375 px phone (measured, §4.4). On the lab the path is
  `/data/backup` and fits. File it, or leave it?

## 1. The mandate, and what is out of scope

The operator, 2026-10-02 (#542): *"We need to have a way to delete documents and override retention policies in gui.
So that we can just do a cleanup from gui."* The decisions of the same day, settled: "override retention" is a
one-off cleanup and nothing is persisted, as two actions (delete chosen items; clean up now with a tighter bound,
previewed, then confirmed); the chart's `reporting.retention` and the backup values stay the standing policy, and no
retention value is stored in the database or edited from the page; only the cluster-admin tier, behind a
proxy-verified identity, with every deletion recorded (who, what, when); and the scope is report runs, scheduled and
manual, and the on-volume DB copies in `/data/backup`, `/data/pre-upgrade` and `/data/pre-restore`.

Must not change (#542): retention's automatic behaviour and every chart value and default; `restore-db.sh` and the
runbook's restore path still find a copy (at least the newest backup is kept); the dashboard ServiceAccount's RBAC
(nothing removed; the deletion needs no new permission, which this spec verifies); viewers below the tier see no
control and get the tier's refusal; no identity names in metrics.

Out of scope: editing or storing retention values (decision 1); deleting the off-volume copies (`backup.offsite`,
another claim, and the CronJob's own rotation); `/data/report` (note 11); the live database; the report service's
history of who ran what in the dashboard's `report_run` table (Usage), which records an event and is kept, as it is
when retention deletes a run; and a trash or undo for a deletion (§2a).

## 2. Research, measured

The probes ran with the repository's venv against copies of the tree, each printing the `gsd` it imported. No lab
read was possible during authoring (note on the Source row).

### 2.1 RFC 9110: DELETE, idempotency, and the bulk action

**Source.** RFC 9110, HTTP Semantics (rfc-editor.org/rfc/rfc9110.txt, fetched 2026-10-02). §9.3.5: "If a DELETE
method is successfully applied, the origin server SHOULD send … a 204 (No Content) status code if the action has been
enacted and no further information is to be supplied, or a 200 (OK) status code if the action has been enacted and
the response message includes a representation describing the status." And: "content received in a DELETE request
has no generally defined semantics, cannot alter the meaning or target of the request, and might lead some
implementations to reject the request". §9.2.2: "A request method is considered 'idempotent' if the intended effect
on the server of multiple identical requests with that method is the same as the effect for a single such request.
Of the request methods defined by this specification, PUT, DELETE, and safe request methods are idempotent." §9.3.3:
POST "requests that the target resource process the representation enclosed in the request according to the
resource's own specific semantics". §15.5.10: 409 "indicates that the request could not be completed due to a
conflict with the current state of the target resource … The server SHOULD generate content that includes enough
information for a user to recognize the source of the conflict." §15.5.13: 412 "indicates that one or more conditions
given in the request header fields evaluated to false".

**What it settles.** One item is a `DELETE` on the item's own URI, answered 200 with the deleted item described
(the audit wants what was deleted, so not 204); a repeat is a 404, whose effect on the server is the same, which is
what idempotent means. A cleanup is not a DELETE with a body, which has no defined semantics: it is a `POST` to an
action resource, `…/cleanup`, whose body is the bound and, on the confirm, the preview's digest. A changed set is 409
with the new set in the body (note 9).

### 2.2 Preview, then confirm, without a race

**Sources.** Kubernetes, "Kubernetes API Concepts", Dry-run (raw `content/en/docs/reference/using-api/api-concepts.md`
at kubernetes/website `2cc9ebbcb931`, fetched 2026-10-02): "Kubernetes guarantees that dry-run requests will not be
persisted in storage or have any other side effects"; `All`: "Every stage runs as normal, except for the final
storage stage where side effects are prevented"; and "Authorization for dry-run and non-dry-run requests is
identical." kubernetes/apimachinery `pkg/apis/meta/v1/types.go` at `e00f8382f7de` (raw, fetched 2026-10-02),
`DeleteOptions.Preconditions`: "Must be fulfilled before a deletion is carried out. If not possible, a 409 Conflict
status will be returned."; `Preconditions` carries `UID` ("Specifies the target UID") and `ResourceVersion`.

**What it settles.** The preview is a dry run of the cleanup: the same route, the same gate (authorization identical),
the same computation, nothing deleted. The confirm carries a precondition: the digest of the set the person saw. The
server computes the set again under the lock that deletes it and deletes only if the digest matches, else 409. That
makes the confirm delete exactly the previewed set or nothing, the time-of-check-to-time-of-use window closed by the
lock (§3.7). The digest is sha256 over the sorted ids, one per line, so it does not depend on the order either side
listed them.

### 2.3 CSRF: the cookie session behind the OAuth proxy

**Source.** OWASP Cross-Site Request Forgery Prevention Cheat Sheet (raw
`cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.md` at OWASP/CheatSheetSeries `b239889925f2`, fetched
2026-10-02). "Disallowing simple content types": "For a request to be deemed simple, it must have one of the
following content types - `application/x-www-form-urlencoded`, `multipart/form-data` or `text/plain`. … a simple
mitigation is for the server or API to disallow these simple content types." "Employing Custom Request Headers for
AJAX/API": "When handling the request, the API checks for the existence of this header. If the header does not exist,
the backend rejects the request as potential forgery … This defense relies on the CORS preflight mechanism … All modern
browsers designate requests with custom headers as 'to be preflighted'." And its caveat: "Should a browser bug allow
custom HTTP headers, or not enforce preflight on non-simple content types, it could compromise your security."

**Measured on this repository.** The session is the oauth-proxy's cookie; the chart sets no `-cookie-samesite`
(`grep cookie` over the templates: `-cookie-secret-file` and `-cookie-expire` only), so SameSite is not counted as a
defence. The app has no CORS middleware (`grep -in "cors\|access-control"` over `local-development/gsd/*.py` and
`gsd/reporting/*.py`: no match). The page's writes go through `apiSend`, which sends `Content-Type: application/json`
and the custom header `X-GSD-Interaction: 1` (`local-development/gsd/static/index.html#apiSend`); the existing write routes check neither
header, relying on the JSON body and the non-simple method. Probe (`probe_csrf.py`, FastAPI 0.141.1, a `body: dict`
POST and a DELETE route as the dashboard writes them):

    POST body:dict Content-Type 'application/x-www-form-urlencoded': 422 {"detail":[{"type":"dict_type","loc":["body"],"msg":"Input should be a valid dictionary","
    POST body:dict Content-Type 'multipart/form-data; boundary=x': 422 {"detail":[{"type":"dict_type",…
    POST body:dict Content-Type 'text/plain': 422 {"detail":[{"type":"dict_type",…
    POST body:dict Content-Type 'application/json': 200 {"got":{"a":1}}
    POST body:dict with no Content-Type: 422 {"detail":[{"type":"dict_type",…
    preflight OPTIONS /d/x: 405 Access-Control-Allow-Origin: None

The installed FastAPI reads a body as JSON only when the content type's main type is `application` and its subtype
`json` or `+json` (its `fastapi/routing.py`, lines 436 to 446 of 0.141.1), and with `strict_content_type` on by
default it reads no JSON from a request without a content type (lines 437 to 439).

**What it settles.** A cross-site form cannot send a body these routes read, and a cross-site `fetch` with a JSON
body, a DELETE or a custom header is preflighted, and this app answers no preflight. The deletes add OWASP's
custom-header check as well (`X-GSD-Interaction`, which the page already sends), so a deletion needs a preflight even
if a browser bug let a simple request through: one header check, no token, no state (T542-10).

### 2.4 What a restore needs, and the guard

**Measured.** `restore-db.sh --list` lists the copies `restore-db.py`'s `catalogue` finds: `gsd-*.db` in
`config.backup.dir`, `pre-upgrade-*.db` in `pre-upgrade/` beside the database, and the offsite claim when recovery
mode mounts it (`local-development/restore-db.py#catalogue`). `pre-restore/` is not listed: it is the live set a restore replaced,
kept under `pre-restore/<stamp>/` (`local-development/restore-db.py#keep`), and runbook §4, "Undo a restore", is the way back from it.
Runbook §6: "the database as it was before the upgrade is the only way back to the previous image", and the copy is
taken once per upgrade, so deleting it lets a retried upgrade copy a half-migrated database
(`docs/RUNBOOK_backup_restore.md#6. Pre-upgrade copies`, "Once per upgrade").

**What it settles.** The guard keeps the newest copy of each directory: the newest scheduled backup, so `--list`
always has a backup to restore (the mandate's minimum); the newest pre-upgrade copy, the only way back to the image
before the last schema upgrade; and the newest pre-restore set, the undo of the last restore. Each costs at most one
copy, about the size of the database. In `pre-restore/` the candidates are the kept sets (directories) only: a copy
moved aside there is not the undo of anything.

### 2.5 What `/data/report` is

**Measured.** `local-development/gsd/reporting/snapshot.py#newest_snapshot` reads `/data/report` (`ReportSettings.snapshot_dir`); the dashboard's leader writes it
on `_maybe_report_snapshot` (local-development/gsd/poller.py:1117 at `2d20d0fb`) through `Store.snapshot`, which is
`_vacuum_into` with `keep = reporting.snapshot.keep` (2; `intervalSeconds: 300`, `charts/group-sync-dashboard/values.yaml#intervalSeconds: 300`). The
report service's `readyz` and every run read the newest there. Out of scope (note 11).

### 2.6 The data volume, as measured (the issue's and the walk records')

From #542 and the mandate (read-only through the pods' Python, 2026-10-02): `/data` holds 198.9 MiB; `backup` 4
copies, 54.7 MiB; `pre-upgrade` empty; `pre-restore` 8 entries, 98.3 MiB; `report` 2 copies, 27.4 MiB; the
artefact store 81 runs, 2.8 MiB, 70 of them `schedule:nightly-namespace-access` (retired by #541) and 11 manual; both
claims on one 153 GB filesystem at 82% used, so this cleanup will not relieve the lab's disk pressure. From the
committed walk logs: `reports/2026-10-02_restore-db-302/walk.log` lists `/data/pre-restore` as
`20261002T013241.786235Z/` (a kept set: `gsd.db`, `gsd.db-wal`, `gsd.db-shm`) and the moved-aside
`pre-upgrade-20261002T012959.076526Z-schema-20-to-21-group-sync-dashboard-779c754858-tlp2t.db` with its `.sha256`;
`reports/2026-10-02_runbook-corrections-533/walk.log` shows the manual keep `/data/pre-restore/20261002T150951Z`.
Nothing rotates `pre-restore/`: `git grep -n "pre-restore\|pre_restore"` finds one writer, `restore-db.py`'s `keep`,
whose only removal is of an unfinished `*.tmp` before the next restore (local-development/restore-db.py:695).

### 2.7 Concurrency in the code

**Measured by reading.** `ArtifactStore.prune` deletes under `self._lock` (`local-development/gsd/reporting/artifacts.py#ArtifactStore.prune`), and `write` recreates a
pruned directory for a run still rendering. `Store._vacuum_into` writes a backup under a `.tmp` name, renames it, then
deletes all but `keep` with `stale.unlink()` and logs `could not remove old backup` on an `OSError`
(`local-development/gsd/store.py#Store._vacuum_into`); it runs on the poll thread, outside any lock a request handler takes. The pre-upgrade copy
is written in `Store.__init__`, before the app serves (`local-development/gsd/store.py#_pre_upgrade_copy`); `pre-restore/` only in recovery mode, when the
app does not serve. Above one replica each pod has its own database and its own `pre-upgrade/` and `pre-restore/`
under `/data/<pod>/`, and the backup directory is shared, each pod writing `gsd-<stamp>-<pod>.db` (SPEC_E4,
`local-development/gsd/storage.py#backup_copies`).

## 2a. Alternatives considered

| Option | Source | What it would cost here | Decision |
|---|---|---|---|
| A cluster-admin ticket scope, verified by the report service (design question 1, a) | `local-development/gsd/reporting/ticket.py#mint`, `#verify` | a second tier in a ticket protocol built and reviewed to carry one (C3); the browser would call the report service directly for a run and the dashboard for a copy, two APIs and two audit places for one card; no narrower trust, because the ticket's HMAC key is the service token | rejected (note 1) |
| The dashboard deletes server-to-server with the service token after its own gate (b) | `local-development/gsd/poller.py#Poller._pull_report_usage` already calls the service with the token | an HTTP client and an error mapping in the dashboard (`_report_call`), and two service-only routes on the report service, which exist only with the switch | **chosen** |
| `DELETE` with a body for a bulk delete | RFC 9110 §9.3.5: DELETE content "has no generally defined semantics" | a body some intermediaries reject | rejected: `POST …/cleanup`, an action resource (§2.1) |
| The confirm sends the list of ids to delete | — | the server deletes whatever ids arrive: the bound on the page is not evaluated again, so "older than 30 days" is no longer what is deleted | rejected: the confirm sends the bound and the digest; the server computes the set again and compares (§2.2) |
| A preview token stored on the server, the confirm naming it | — | state to keep, expire and share across replicas; the operator's decision is that nothing is persisted | rejected |
| `If-Match` with an ETag of the set, 412 on a mismatch | RFC 9110 §13.1.1, §15.5.13 | the same binding in a header; 412 is defined for header preconditions on the target's representation, and a cleanup's set is not the target resource's representation | rejected for the body digest and 409, the shape Kubernetes uses for a delete precondition (note 9) |
| A synchronizer or double-submit CSRF token | OWASP, "Token-Based Mitigation" | server state or a second cookie, and a change to every write | rejected: OWASP's custom-header defence, with JSON bodies and no CORS, is what the page already sends; checked on these routes (§2.3) |
| A Fetch Metadata check (`Sec-Fetch-Site`) | OWASP, "Fetch Metadata headers": "a fallback to standard origin verification headers is a mandatory requirement" | a second mechanism and an `Origin` fallback for the property the custom header already gives | rejected |
| Retention overrides stored in the database and edited on the page | #542's request ("override retention") | a second source of truth beside the values file | rejected by the operator's decision 1 |
| A trash: deleted items moved aside and purged later | — | a fourth directory, its own retention, and the space not freed until then | rejected: a deletion is explicit, previewed and confirmed, and the guard keeps a restore possible |
| No guard on `pre-restore/` or `pre-upgrade/` | the mandate's minimum is the newest backup | a cleanup could remove the undo of the last restore or the way back across the last upgrade | rejected: the newest of each is kept (§2.4) |
| The guard as `config.backup.keep` | — | the page could delete nothing the rotation would not delete next | rejected: the newest only |
| `/data/report` in scope | the mandate's question | frees nothing durable; deleting the newest makes the report service unready | rejected (note 11) |
| No switch | the chart's defaults rule | the dashboard's read-only default (R6) would gain deletes no estate could refuse | rejected: one switch, on by default (note 7) |

**Reconciliation: each external claim, and the code that behaves accordingly.**

- RFC 9110 §9.3.5 says a DELETE that was enacted and describes the result answers 200: `delete_housekeeping_copy` and
  `delete_housekeeping_report` answer 200 with `{"deleted": {…}}` (`local-development/gsd/api.py#delete_housekeeping_copy`,
  `#delete_housekeeping_report`). §9.2.2 says DELETE is idempotent: a repeated delete finds no listed copy and answers
  404, the server's state the same (T542-3, `test_the_only_backup_is_kept`, deletes, then is refused, then lists).
- RFC 9110 §9.3.5 says DELETE content has no defined semantics: the two cleanups are `POST` routes whose body is a
  validated model (`local-development/gsd/housekeeping.py#RunCleanupRequest`, `#CopyCleanupRequest`).
- Kubernetes says a delete whose precondition fails answers 409: the set is computed again under the lock and a
  digest that differs raises `CleanupChanged`, answered 409 with the new preview
  (`local-development/gsd/housekeeping.py#cleanup_copies`, `local-development/gsd/reporting/artifacts.py#ArtifactStore.cleanup`,
  `local-development/gsd/reporting/server.py#build_report_app`'s `cleanup_runs`). Kubernetes says dry-run authorization is identical: the preview
  goes through the same `_housekeeping_write` gate as the confirm.
- OWASP says to reject a request without the custom header: `_housekeeping_write` refuses a write without
  `X-GSD-Interaction` (403, T542-10). OWASP says to disallow simple content types: FastAPI 0.141.1 reads JSON only for
  an `application/json` or `+json` content type (its `routing.py` lines 436 to 446), measured 422 for the three simple
  types (§2.3) and on these routes (T542-10). OWASP's custom-header defence relies on a preflight the app does not
  answer: no CORS middleware in `gsd/`, and the probe's preflight answered 405 with no `Access-Control-Allow-Origin`.

## 3. The design

### 3.1 Who, and through which door

Every route checks, in this order: a proxy-verified identity with view restrictions on (else 403, "needs an
authenticated identity to record the deletion against", the rule `_writes_gate` states for the cluster-configuration
writes), then the cluster-admin tier (`require_cluster_admin`, else 403 `For cluster administrators only. …`), then,
for the four writes, the `X-GSD-Interaction` header (else 403). The tier is asked once per request through the same
cached resolver the KPI page and the Cluster Configurations tab use, so the page, the tab strip and the routes cannot
disagree. A report run is deleted by the report service at the dashboard's request: the dashboard sends the service
token (`report_secret`, the bytes it already reads at startup) to `DELETE /report/api/runs/{id}` or
`POST /report/api/runs/cleanup`, which accept the token only (`dashboard_only`); a viewer's ticket is refused there
(T542-9). Its 404, 409 and 422 pass through with their detail; anything else, or no answer, is a 502 that names the
report service (T542-11).

### 3.2 What a copy is

Three directories, as their writers name them (`copy_dirs`): `config.backup.dir` (absent when backups are off),
and `pre-upgrade/` and `pre-restore/` beside the database (`/data/<pod>/` above one replica). In each, a copy is:

| directory | a copy | never a copy |
|---|---|---|
| `backup` | a file matching `BACKUP_NAME`, `gsd-<stamp>[-<pod>].db` | a `.tmp` (the writer's unfinished file) |
| `pre-upgrade` | a file matching `PRE_UPGRADE_NAME` | a `.tmp`; the `.sha256`, which goes with its copy |
| `pre-restore` | a directory named by a stamp, with or without microseconds (a restore's kept set); a `*.db` file (a copy moved aside, runbook §6) | `<stamp>.tmp/` (an interrupted keep); a `.sha256`, which goes with its copy |

In all three: a hidden entry and a symlink are never copies. A copy's instant is the stamp in its name, else its
modification time; its size is the file and its sidecar, or the regular files directly inside a kept set.

### 3.3 One item, or a cleanup bound to its preview

One item: `DELETE /api/housekeeping/copies/{kind}/{name}` or `DELETE /api/housekeeping/reports/{run_id}`. The page
asks twice (Delete, then Confirm delete), the Cluster Configurations tab's pattern.

A cleanup: `POST …/cleanup` with the bound and no `confirm` is the preview: the set, its size, and its digest
(sha256 of the sorted ids, one per line: the run id, or `<kind>/<name>`), nothing deleted. The same body with
`confirm: <digest>` computes the set again, under the lock that deletes it, and deletes it only when its digest is the
one confirmed; otherwise 409 `{"message", "preview"}` with the set as it is now, nothing deleted, and the page shows
the new list for a new decision. Report runs: finished runs in `scope`, completed more than `older_than_days` ago,
beyond the newest `keep_newest` of their (schedule, cluster), manual runs one group per cluster, ages as retention
measures them (`retention_stamp`: completion, else the id). Copies: unguarded copies in the chosen directories taken
more than `older_than_days` ago.

### 3.4 Never a run in flight

A queued or running run is the worker's: `ArtifactStore.delete` refuses it (`RunInFlight`, 409, the status named)
and a cleanup considers only `done` and `failed` runs, as `prune` does.

### 3.5 No path from the request

The kind is one of three words; the name is looked up in the directory's own `os.scandir` listing and is never joined
onto a path. So `..`, an encoded slash, the live database's name, a symlink named like a copy and a symlinked
directory are each "not listed", 404, and nothing outside the three directories can be reached (T542-5).

### 3.6 The guard

The newest copy of each directory is never deleted from the page: in `backup` the newest backup (a restore always has
a copy: `restore-db.sh --list` reads this directory), in `pre-upgrade` the newest pre-upgrade copy (the only way back
across the last schema upgrade, and the copy whose presence stops a retried upgrade copying a half-migrated database),
in `pre-restore` the newest kept set (the undo of the last restore; a copy moved aside there is not a candidate).
Asked to delete it, the route answers 409 with the reason; a cleanup lists it under `kept` and never in the set.

### 3.7 Concurrency, as budgets

**Report runs.** Budget: per confirm, at most the previewed set is deleted, across retention's prune and every page,
for the report service's one process. Scope: the store's `_lock`, which `prune`, `create`, `update`, `delete` and
`cleanup` all take; one report pod (the chart renders one). The set is computed and deleted in one hold of the lock,
so a run retention removed in between changes the digest (409), and a run cannot be deleted twice.

**Copies.**

| system shape | what bounds it | budget |
|---|---|---|
| one replica, two administrators | the module's `_lock` serialises every listing-and-delete in the process | per confirm, at most the previewed set; the guarded copies never |
| a backup lands between preview and confirm | the new copy is the newest, so the old newest joins the set: the digest differs | 409, nothing deleted (T542-2) |
| the rotation deletes a copy the page is deleting | `unlink(missing_ok=True)` | the page's deletion succeeds; the copy is gone either way |
| the page deletes a copy the rotation is about to delete | the rotation's `stale.unlink()` raises, logs `could not remove old backup` and goes on (`Store._vacuum_into`) | one WARNING line; nothing else |
| the newest backup and the rotation | the rotation runs right after writing a newer copy and keeps `keep` ≥ 1 newest (or all at 0); the page never deletes the newest at its confirm | at least one backup in the directory after any page deletion |
| above one replica | each pod lists the shared backup directory whole and its own `pre-upgrade/` and `pre-restore/`; a confirm answered by another pod computes that pod's set | a different set is a 409; an equal set deletes the same files; two confirms racing on two pods can each delete a file the other already removed (`missing_ok`), so an item may be audited twice, and nothing outside the previewed set is deleted |

The pre-upgrade copy is written in `Store.__init__` before the app serves, and a pre-restore set only in recovery
mode, so neither writer runs while a page request can.

### 3.8 The switch

`housekeeping.enabled` (default `true`) renders `housekeepingEnabled` into the dashboard's ConfigMap and
`GSD_REPORT_HOUSEKEEPING_ENABLED` into the report pod. Off, neither pod registers a delete route (a request is a 404 or
405, not a route that refuses) and `/api/version` says `features.housekeeping: false`, so the page draws nothing. The
application's own default is off, as `cluster_secrets_writes_enabled`'s is: the code's default API stays GET-only
(R6) and the report service's default contract two non-GETs. No RBAC: the dashboard deletes files in its own volume,
the report service in its own (§4.3).

### 3.9 CSRF

§2.3: JSON bodies only, no CORS, and the custom header on every write.

### 3.10 The record

One line per deleted item, at INFO, through `event` (redacted, one field vocabulary): who (`by=`), what (`run=`,
`report=`, `cluster=`, `schedule=`, or `kind=`, `copy=`, `directory=`; and `bytes=`); the record's own timestamp is
when. A cleanup's confirm writes one line per item it deleted, none for a failure (reported in `failed`). On
`/metrics`, `gsd_housekeeping_deleted_total{kind}`, `kind` one of `report-run`, `backup`, `pre-upgrade`,
`pre-restore`, pre-seeded to 0: never a name, a run id or a copy's name, the rule `/metrics` keeps because it is public.

### 3.11 The page

`housekeepingOn()` is the deployment's switch (`features.housekeeping`) and the reader's tier (`clusterAdmin()`, read
from `/api/whoami`). Below either, nothing is drawn and nothing is fetched. The Library's run drawer gains **Delete this
run** for a finished run; the Library gains a **Clean up** card whose scope offers every configured schedule and every
schedule a run still names; the KPI page gains **Database copies** under Backups: each copy with its directory, when
it was taken, its size, and a **Delete** button, or for a guarded copy the reason it is kept, and a cleanup form. The
typed bound and the last answer live in one object (`hk`), never in the URL, and survive the poll's repaints; a
changed bound clears a stale preview.

### 3.12 Recovery mode, the restore path, and what does not change

In recovery mode (SPEC_E2) the app does not serve, so nothing here runs; `restore-db.sh`, the runbook's restore path
and its undo are unchanged, and the guard keeps what they read. Retention's automatic behaviour, every chart value
and default other than the new one, the dashboard ServiceAccount's RBAC, the ticket and its protocol, `/data/report`,
and the dashboard's `report_run` history are unchanged.

## 4. Tests

### 4.1 One test per case

The issue's checks and the mandate's, as `T542-k`. All but two are in `local-development/tests/test_housekeeping.py`
(block 33), run against the real report app through the `app.state.report_client` seam and a data volume laid out
as the lab's (§2.6); T542-8 and T542-12 are browser tests in `local-development/tests/test_ui.py` (block 34). Each
says why it fails without the change; §4.2 shows each property's own test failing when only that property is broken.

| case | test | fails without the change because |
|---|---|---|
| T542-1 the tier, at the API | `TestT542_1_TheTier`: `auditor` (the wide tier) and `alice` get 403 `For cluster administrators only.` from all five routes and nothing is deleted; no identity, and restrictions off, are refused; the tier lists the copies with each guard's reason | the routes do not exist: 404, not the tier's sentence |
| T542-2 the preview binds the confirm | `TestT542_2_ThePreviewBindsTheConfirm`: a run added, or a backup landing, between preview and confirm is a 409 carrying the new set, and nothing is deleted; the new digest deletes exactly the new set; a digest of another set never deletes | the routes do not exist |
| T542-3 the last-copy guard | `TestT542_3_TheGuard`: the newest backup, pre-upgrade copy and pre-restore set are refused with their reasons; the widest cleanup leaves exactly them, the unfinished keep and the live database; the only backup left is kept | the routes do not exist |
| T542-4 a run in flight is never deleted | `TestT542_4_InFlightRunsStay`: the per-run delete answers 409 naming `queued` or `running`; the widest cleanup leaves both; age and keep-newest apply together | the routes do not exist |
| T542-5 no path traversal | `TestT542_5_NoPathFromTheRequest`: `%2E%2E`, `..%2Fgsd.db`, `gsd.db`, a symlink named like the newest backup, a symlinked kept set, kind `..` and kind `data` are 404 or 405 and no file changes; a real copy is deletable through the same route | the routes do not exist (404 for every case too, so the test also proves a real copy IS deletable) |
| T542-6 the audit line | `TestT542_6_TheAuditLine`: `report-run-deleted run=… report=groups cluster=c1 bytes=300 by=jane.admin`, `db-copy-deleted kind=backup copy=… directory=… bytes=20 by=jane.admin`, one line per item of a cleanup | no route, no line |
| T542-7 the metric names no one | `TestT542_7_TheMetricNamesNoOne`: pre-seeded 0 per kind, then 1 for `report-run` and `backup`; the viewer, the run id and the copy's stamp are nowhere in `/metrics` | the family does not exist |
| T542-8 no control below the tier, in the browser | `TestHousekeepingPage::test_t542_8_below_the_tier_there_is_no_control`: as `auditor`, with the deployment's switch on, the drawer has no delete, there is no Clean up card and no KPI tab, and the copies listing answers 403 | the rig cannot be built: `ReportSettings` has no `housekeeping_enabled` |
| T542-9 the switch and the contract | `TestT542_9_TheSwitchAndTheContract`: off (the code's default) no route on either service; on, exactly the four writes and the report service's two; a viewer's ticket cannot delete on the report service | the setting does not exist |
| T542-10 the custom header and JSON | `TestT542_10_TheCustomHeader`: every write without `X-GSD-Interaction` is 403; a `text/plain` body is 422 | the routes do not exist |
| T542-11 the report service's answers | `TestT542_11_TheReportServicesAnswers`: reporting off is 404 with its sentence; an unreachable service is 502 naming it | the routes do not exist |
| T542-12 the administrator's flows, in the browser | `TestHousekeepingPage::test_t542_12_a_cluster_administrator_deletes_previews_and_confirms`: Delete then Confirm delete removes a run; the retired schedule's three runs are previewed (nothing deleted), confirmed, and gone, the running run kept; on the KPI page the newest backup's row says why it stays and has no button, and an older one is deleted in two steps; plus `test_the_cards_fit_a_phone`, both cards inside 375 px | as T542-8 |
| T542-13 the chart | `TestT542_13_TheChart`: the ConfigMap key and the report pod's variable follow `housekeeping.enabled`, on by default and off when set | neither is rendered |

One existing test changes: `local-development/tests/test_report_ticket_api.py#TestTheTicket` pins `/api/version`'s `features` whole and
now reads `housekeeping: false` (block 35); it was the only test the change failed in the full run before the edit
(`AssertionError: … Left contains 1 more item: {'housekeeping': False}`).

### 4.2 Each property's test goes red when only that property is broken

The mutation harness (§4.4) copies the implemented tree, replaces one text (asserted to occur exactly once) and runs
`tests/test_housekeeping.py` with the copy's `gsd` first on the path. Each row is one mutation, and the tests it turns
red are the ones written for that property; the unmutated copy passes all 29.

| run | the mutation | result | the tests that go red |
|---|---|---|---|
| M1 | the guard removed (no copy is `guarded`) | 8 failed, 21 passed | the three `test_the_newest_of_each_directory_is_refused`, `test_the_only_backup_is_kept`, the widest cleanup, `test_database_copies` (its preview's `kept`), the listing's guards, the audit test (the guarded set deleted) |
| M2 | the copies' digest not compared | 2 failed | `test_database_copies`, `test_a_digest_of_another_set_never_deletes` |
| M3 | the runs' digest not compared | 1 failed | `test_report_runs` |
| M4 | a queued or running run deletable | 2 failed | both `test_the_per_run_delete_refuses` |
| M5 | a cleanup counts runs in flight | 3 failed | `test_report_runs`, `test_the_widest_cleanup_leaves_them`, `test_keep_newest_and_the_age_apply_together` |
| M6 | symlinks listed | 1 failed | `test_traversal_and_symlinks_are_not_copies` |
| M7 | the name joined onto the directory instead of looked up | 6 failed | `test_traversal_and_symlinks_are_not_copies`, the three guard refusals, `test_the_only_backup_is_kept`, the audit test |
| M8 | the wide tier instead of the cluster-admin tier | 2 failed | both `test_below_the_tier_every_route_refuses_with_the_tiers_sentence` (`auditor`, `alice`) |
| M9 | no custom-header check | 1 failed | `test_a_write_without_the_header_is_refused` |
| M10 | no audit line for a copy | 1 failed | `test_one_line_per_item` |
| M11 | the counter not yielded | 1 failed | `test_counted_by_kind_and_nothing_else` |
| M12 | the routes registered whatever the switch | 1 failed | `test_the_dashboard` |
| M13 | a viewer's ticket accepted by the report service's delete | 1 failed | `test_a_viewers_ticket_cannot_delete_on_the_report_service` |

### 4.3 The proof

Measured on 2026-10-02 in the scratch directory, with the repository's venv and `PYTHONPATH` set to the tree under
test. The logs are not committed; their last lines are quoted.

| run | tree | result |
|---|---|---|
| hermetic suite, before | a git checkout of main `2d20d0fb` | `6864 passed, 26 skipped, 661 deselected, 5 xfailed` |
| hermetic suite, after | the same tree with every block applied (`apply-spec-blocks.py … --apply`) | `6899 passed, 23 skipped, 664 deselected, 5 xfailed` |
| browser suite, before | main `2d20d0fb` | `657 passed` |
| browser suite, after | with every block applied | `660 passed` |
| the new and touched test files, after | with every block applied | `1937 passed, 19 skipped` |

- **The arithmetic.** The 35 more hermetic passes are the 32 new tests plus 3 that skipped before and now run:
  6864 + 32 + 3 = 6899, and 26 − 3 = 23 skipped. The browser suite gains the 3 new page tests.
- **A baseline that does not count.** A first "before" run in an export with no git history failed 3 tests that
  read git: `test_build_and_push_report`, `test_migration_needs_app_release` and `test_tree_hygiene`. It is not the
  baseline; the git checkout above is.
- **Fails before.** "Fails before the change" is §4.2's mutation table: each property's tests go red when only that
  property is broken.

### 4.4 The probes

The probes ran in the scratch directory and are not committed; they are here as they ran.

`probe_csrf.py` (§2.3), with the repository's venv:

    """H1 research: what FastAPI 0.141.1 does with the bodies a cross-site <form> can send, on a `body: dict` POST
    like the dashboard's write routes, and whether an app with no CORS middleware answers a preflight."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()


    @app.post("/w")
    def w(body: dict) -> dict:
        return {"got": body}


    @app.delete("/d/{name}")
    def d(name: str) -> dict:
        return {"deleted": name}


    c = TestClient(app)
    for ctype in ("application/x-www-form-urlencoded", "multipart/form-data; boundary=x", "text/plain", "application/json"):
        r = c.post("/w", content=b'{"a": 1}', headers={"Content-Type": ctype})
        print(f"POST body:dict Content-Type {ctype!r}: {r.status_code} {r.text[:90]}")
    r = c.post("/w", content=b'{"a": 1}')
    print("POST body:dict with no Content-Type:", r.status_code, r.text[:90])
    r = c.options("/d/x", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "DELETE"})
    print("preflight OPTIONS /d/x:", r.status_code, "Access-Control-Allow-Origin:", r.headers.get("access-control-allow-origin"))

`mutate.py` (§4.2): for each row, `shutil.copytree` of the implemented tree without `.git`, one `str.replace` asserted
to match once, then `python -m pytest -q tests/test_housekeeping.py` in the copy's `local-development` with
`PYTHONPATH` set to it, so the copy's `gsd` is the one imported.

The phone-width measurement (open question B): on the browser rig at 375 px, with the Database copies card removed
from the KPI page, `scrollWidth - clientWidth` was still 86 px; the only element past the viewport outside a scroll box
was SPEC_E6's `span.asof` in the Backups heading (`on-volume · <config.backup.dir> · every 6 h · keep 4`), its right edge
at 461 px, the directory being the rig's long pytest path. The first version of this spec's card put the directories in
its heading the same way; they now sit in a wrapping line under it (block 28), and `test_the_cards_fit_a_phone` holds
each card's own elements inside the viewport.

The block generator (§4.3) cut each changed file into whole-line hunks against `2d20d0fb`, widened each hunk's context
to the fewest unchanged lines that make its Old text occur once in the file as the earlier blocks leave it, and
asserted that the hunks applied in order reproduce the implemented file byte for byte and that no fence body holds a
line the block parser ends on.

## 5. On the lab (the implementing pull request)

**Not measured: the lab was down during authoring (2026-10-02)**, the operator rebooting it (`oc get pods -n
group-sync-dashboard` answered `connection reset by peer` from `api.crc.testing:6443` at 21:14Z and 21:19Z, and no
further read was tried). The figures in §2.6 are #542's and the mandate's of the same day. The read-only checks the
walk opens with, to run first (development and troubleshooting commands, the walk being development):

    oc exec -n group-sync-dashboard deploy/group-sync-dashboard -c dashboard -- ls -la /data /data/backup /data/pre-upgrade /data/pre-restore /data/report
    oc exec -n group-sync-dashboard deploy/group-sync-dashboard-report -- python3.14 -c 'import json, pathlib, collections; runs = [json.loads(p.read_text()) for p in pathlib.Path("/artifacts").glob("*/run.json")]; print(len(runs), collections.Counter(r["generated_by"] if r["generated_by"].startswith("schedule:") else "manual" for r in runs))'
    oc get pvc -n group-sync-dashboard group-sync-dashboard-data group-sync-dashboard-report-artifacts -o custom-columns=NAME:.metadata.name,UID:.metadata.uid

The walk, on the deployed head (built and deployed with `release-crc.sh`), with screenshots committed under
`reports/<date>_<slug>/` and posted on #542, pinned to the merge sha:

1. **The claims.** Record the UIDs of `group-sync-dashboard-data` and `group-sync-dashboard-report-artifacts` (the
   third command above).
2. **One manual run, as kubeadmin** (cluster-admin) in the browser: Library, open a manual run, **Delete this run**,
   **Confirm delete**. The run leaves the Library; the dashboard's log has one `report-run-deleted … by=kubeadmin` line;
   `/metrics` shows `gsd_housekeeping_deleted_total{kind="report-run"} 1`.
3. **The retired schedule's runs** (70 on 2026-10-02): the Library's **Clean up**, runs `schedule
   nightly-namespace-access`, older than 0 days, keep the newest 0, **Preview**: the list holds every run of that
   schedule and its count matches the second read-only command; **Delete these N runs**; the count is gone from the
   artefact store and the log has N lines.
4. **One pre-restore copy**: the KPI page's **Database copies**, a `pre-restore` set that is not the newest,
   **Delete**, **Confirm delete**; `ls /data/pre-restore` no longer holds it; one `db-copy-deleted kind=pre-restore …
   by=kubeadmin` line.
5. **The newest backup is refused**: its row reads `kept: the newest scheduled backup is kept, …` and has no button;
   through the pod's loopback as kubeadmin,
   `curl -s -X DELETE -H 'X-Forwarded-User: kube:admin' -H 'X-GSD-Interaction: 1' http://127.0.0.1:8080/api/housekeeping/copies/backup/<newest>`
   answers 409 with that sentence, and the file is still there.
6. **Below the tier**: the readers the earlier walks used, through the pod's loopback (the dashboard trusts
   `X-Forwarded-User` from its proxy, as `reports/2026-09-20_cluster-secrets-230/validate-tier.sh` uses it):
   `auditor` (cluster-reader, the wide tier) and `developer` each get 403 `For cluster administrators only. …` from
   all five routes, and in the browser as `developer` the Library's drawer has no delete and no Clean up card. Never
   the fleet account.
7. **The claims again**: the same two UIDs.

## 6. What an operator sees, and what it costs

- A cluster administrator sees **Delete this run** in the Library's run drawer, a **Clean up** card below the
  Library's sections, and a **Database copies** card on the KPI page with every copy, its age and size, a Delete
  button on all but the newest of each directory, and a cleanup form. Every cleanup shows its list first. Anyone
  else sees nothing new.
- Every deleted item is one INFO line in the dashboard's log naming the person and the item, and one count in
  `gsd_housekeeping_deleted_total{kind}`.
- `housekeeping.enabled: false` in the release's values file, rolled out through the release's deployment pipeline,
  removes every route and control.
- On the lab today the copies an administrator could remove amount to most of `pre-restore`'s 98.3 MiB and the
  backups past the newest; the retired schedule's 70 runs are part of 2.8 MiB. The claims share the node's disk, so
  this does not relieve the lab's 82% (§2.6).
- No new RBAC, credential, image, migration or Kubernetes object; one value. Cost in code, from `git diff --numstat`
  on the implemented copy:

| file | added | removed |
|---|---|---|
| `local-development/gsd/housekeeping.py` (new) | 241 | 0 |
| `local-development/gsd/api.py` | 152 | 1 |
| `local-development/gsd/reporting/server.py` | 54 | 2 |
| `local-development/gsd/reporting/artifacts.py` | 52 | 0 |
| `local-development/gsd/metrics.py` | 20 | 1 |
| `local-development/gsd/config.py` | 5 | 0 |
| `local-development/gsd/reporting/config.py` | 4 | 0 |
| `local-development/gsd/static/index.html` | 176 | 0 |
| `local-development/gsd/static/app.css` | 7 | 0 |
| `local-development/tests/test_housekeeping.py` (new) | 436 | 0 |
| `local-development/tests/test_ui.py` | 167 | 0 |
| `local-development/tests/test_report_ticket_api.py` | 2 | 1 |
| `local-development/API.md` | 24 | 0 |
| `docs/ACCESS_CONTROL.md` | 1 | 0 |
| `docs/RUNBOOK_backup_restore.md` | 9 | 1 |
| `docs/CHANGELOG.md` | 20 | 0 |
| `docs/specs/SPEC_D6_scrub_span.md` (the live emit count, block 42) | 6 | 3 |
| `charts/group-sync-dashboard/values.yaml` | 25 | 0 |
| `charts/group-sync-dashboard/templates/configmap.yaml` | 2 | 0 |
| `charts/group-sync-dashboard/templates/report-deployment.yaml` | 3 | 0 |
| `charts/group-sync-dashboard/README.md` | 6 | 0 |

## 7. Implementation blocks

Applied in this order: the shared module and the report service (blocks 1 to 10), the dashboard (11 to 22), the page
(23 to 32), the tests (33 to 35), the documents (36 to 42), the chart (43 to 46). No block carries a version field
(the Version note).

### Block 1 — local-development/gsd/housekeeping.py: the module both pods share, and the dashboard's copies

The request shapes, the set digest, `CleanupChanged`, and the listing, guard and deletion of the database copies in the three directories (§3.2 to §3.6). A name is matched against `os.scandir`, never joined onto a path (§3.5).

<!-- block: local-development/gsd/housekeeping.py | create -->

```python
"""Deleting report runs and database copies from the page (#542, docs/specs/SPEC_H1_gui_cleanup.md).

A one-off cleanup, nothing persisted: the chart's `reporting.retention` and `backup.*` stay the standing policy,
and a person in the cluster-admin tier either deletes items they chose or previews a tighter bound and confirms
it. This module holds what both pods share (the request shapes and the set digest) and the dashboard's own half:
the database copies on its data volume, in exactly three directories.

THE GUARD. In each directory the newest copy is never deleted from the page: the newest scheduled backup (a
restore needs a copy, docs/RUNBOOK_backup_restore.md §4), the newest pre-upgrade copy (the only way back across the
last schema upgrade, §6) and the newest pre-restore set (the way back from the last restore, §4 "Undo a restore").

THE BINDING. A cleanup's confirm carries the digest of the set its preview showed. The set is computed again under
the lock that deletes it, and a different set is refused (409) with the new preview, so the confirm deletes
exactly what the person saw or nothing (Kubernetes answers a failed delete precondition with 409 the same way).

NO PATH FROM THE REQUEST. A name is matched against the directory's own listing (os.scandir), never joined onto
a path, so `..`, a slash or a symlink cannot reach outside the three directories.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from .storage import BACKUP_NAME
from .store import PRE_UPGRADE_DIR, PRE_UPGRADE_NAME

#: The three directories on the dashboard's data volume a copy may be deleted from, in the order the page lists them.
COPY_KINDS = ("backup", "pre-upgrade", "pre-restore")
#: Every kind of item the page deletes: the vocabulary of the audit line and of gsd_housekeeping_deleted_total.
KINDS = ("report-run", *COPY_KINDS)
#: Where a restore keeps the live set it replaced: beside the database, as restore-db.py's Layout names it.
PRE_RESTORE_DIR = "pre-restore"
#: A copy's own instant in its name: restore-db.py's keep and every copy writer stamp microseconds; the runbook's
#: manual keep (§4a) stamps whole seconds.
_STAMP = re.compile(r"(\d{8}T\d{6})(?:\.(\d{6}))?Z")
#: Why the newest copy of each kind is kept, in the words the page and the 409 say.
GUARDS = {
    "backup": "the newest scheduled backup is kept, so a restore always has a copy to restore "
              "(docs/RUNBOOK_backup_restore.md §4)",
    "pre-upgrade": "the newest pre-upgrade copy is kept: it is the only way back to the image before the last "
                   "schema upgrade (docs/RUNBOOK_backup_restore.md §6)",
    "pre-restore": "the newest pre-restore set is kept: it is the way back from the last restore "
                   "(docs/RUNBOOK_backup_restore.md §4, \"Undo a restore\")",
}
#: A schedule's name as the chart and the report service accept it: a short DNS label.
_SCHEDULE = r"[a-z0-9]([-a-z0-9]{0,40}[a-z0-9])?"


def set_digest(ids: Iterable[str]) -> str:
    """The digest a cleanup's confirm carries: sha256 of the sorted ids, one per line. Order-free, so the
    preview and the confirm agree however each listed the set."""
    return hashlib.sha256("\n".join(sorted(ids)).encode("utf-8")).hexdigest()


class CleanupChanged(Exception):
    """The set a confirmed cleanup would delete now is not the set its preview showed; nothing was deleted."""

    def __init__(self, plan: list) -> None:
        super().__init__("the set changed since the preview")
        self.plan = plan


class RunCleanupRequest(BaseModel):
    """A one-off cleanup of report runs: preview without `confirm`, delete with the preview's digest."""

    scope: str = Field(default="all", pattern=rf"^(all|manual|schedule:{_SCHEDULE})$",
                       description="Which runs: all, manual (a person's runs), or schedule:<name>, a schedule's runs "
                                   "whether or not the schedule is still configured.")
    older_than_days: int = Field(default=0, ge=0, le=3650,
                                 description="Only runs completed more than this many days ago; 0 is any age.")
    keep_newest: int = Field(default=0, ge=0, le=1000,
                             description="Keep the newest K runs of each (schedule, cluster); manual runs are one group "
                                         "per cluster. 0 keeps none.")
    confirm: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$",
                                description="The preview's digest: delete exactly that set, or 409 if it changed.")


class CopyCleanupRequest(BaseModel):
    """A one-off cleanup of database copies: preview without `confirm`, delete with the preview's digest."""

    kinds: list[Literal["backup", "pre-upgrade", "pre-restore"]] = Field(
        default_factory=lambda: list(COPY_KINDS), min_length=1, max_length=3,
        description="The directories to clean: backup, pre-upgrade, pre-restore.")
    older_than_days: int = Field(default=0, ge=0, le=3650,
                                 description="Only copies taken more than this many days ago; 0 is any age.")
    confirm: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$",
                                description="The preview's digest: delete exactly that set, or 409 if it changed.")


@dataclass(frozen=True)
class Copy:
    """One database copy on the data volume: a file (a backup, a pre-upgrade copy, a copy moved aside into
    pre-restore/) or a directory (a restore's kept live set)."""

    kind: str
    name: str
    path: Path
    is_dir: bool
    bytes: int
    at: datetime
    guarded: str | None

    @property
    def key(self) -> str:
        """The copy's id in a digest and in the API's path: `<kind>/<name>`."""
        return f"{self.kind}/{self.name}"

    def public(self) -> dict:
        return {"kind": self.kind, "name": self.name, "directory": str(self.path.parent),
                "type": "directory" if self.is_dir else "file", "bytes": self.bytes,
                "at": self.at.strftime("%Y-%m-%dT%H:%M:%SZ"), "guarded": self.guarded}


class CopyNotFound(LookupError):
    """No copy of that kind and name is listed (the name was never a copy, or it is already gone)."""


class CopyGuarded(Exception):
    """The copy named is the one its directory's guard keeps."""

    def __init__(self, copy: Copy) -> None:
        super().__init__(copy.guarded)
        self.copy = copy


def copy_dirs(db_path: str, backup_dir: str) -> dict[str, Path | None]:
    """The three directories, as the writers name them: config.backup.dir (None when backups are off), and
    pre-upgrade/ and pre-restore/ beside the database (/data/<pod>/ above one replica)."""
    beside = Path(db_path).parent
    return {"backup": Path(backup_dir) if backup_dir else None,
            "pre-upgrade": beside / PRE_UPGRADE_DIR, "pre-restore": beside / PRE_RESTORE_DIR}


def _is_copy(kind: str, name: str, is_dir: bool) -> bool:
    """Whether a directory entry is a copy of this kind. A writer's unfinished `.tmp`, a `.sha256` sidecar (it
    goes with its copy) and a hidden entry are never copies."""
    if name.startswith(".") or name.endswith((".tmp", ".sha256")):
        return False
    if kind == "backup":
        return not is_dir and BACKUP_NAME.fullmatch(name) is not None
    if kind == "pre-upgrade":
        return not is_dir and PRE_UPGRADE_NAME.fullmatch(name) is not None
    return (is_dir and _STAMP.fullmatch(name) is not None) or (not is_dir and name.endswith(".db"))


def _instant(name: str, path: Path) -> datetime:
    """The copy's own instant: the stamp in its name, else the file's modification time."""
    if (m := _STAMP.search(name)) is not None:
        return datetime.strptime(m.group(1) + "." + (m.group(2) or "000000"), "%Y%m%dT%H%M%S.%f").replace(tzinfo=UTC)
    return datetime.fromtimestamp(path.lstat().st_mtime, UTC)


def _size(path: Path, is_dir: bool) -> int:
    """Bytes the copy holds: a file and its sidecar, or the regular files directly inside a kept set."""
    if is_dir:
        with os.scandir(path) as inside:
            return sum(e.stat(follow_symlinks=False).st_size for e in inside if e.is_file(follow_symlinks=False))
    sidecar = path.with_name(path.name + ".sha256")
    return path.lstat().st_size + (sidecar.lstat().st_size if sidecar.is_file() else 0)


def list_copies(db_path: str, backup_dir: str) -> list[Copy]:
    """Every copy in the three directories, newest first, the newest of each kind guarded. A symlink is never
    listed, so nothing reached through one can be deleted."""
    out: list[Copy] = []
    for kind, directory in copy_dirs(db_path, backup_dir).items():
        if directory is None or not directory.is_dir():
            continue
        found = []
        with os.scandir(directory) as entries:
            for entry in entries:
                if entry.is_symlink():
                    continue
                is_dir = entry.is_dir(follow_symlinks=False)
                if _is_copy(kind, entry.name, is_dir):
                    path = Path(entry.path)
                    found.append((entry.name, path, is_dir, _instant(entry.name, path), _size(path, is_dir)))
        # The guard's candidates: in pre-restore/ only a restore's kept set, never a copy moved aside into it.
        candidates = [f for f in found if kind != "pre-restore" or f[2]]
        newest = max(candidates, key=lambda f: (f[3], f[0]))[0] if candidates else None
        out.extend(Copy(kind, name, path, is_dir, size, at, GUARDS[kind] if name == newest else None)
                   for name, path, is_dir, at, size in found)
    return sorted(out, key=lambda c: (c.at, c.key), reverse=True)


#: One deletion at a time in this process: a listing and the deletions it decides are one step.
_lock = threading.Lock()


def _remove(copy: Copy) -> None:
    if copy.is_dir:
        shutil.rmtree(copy.path)
    else:
        copy.path.unlink(missing_ok=True)
        copy.path.with_name(copy.path.name + ".sha256").unlink(missing_ok=True)


def delete_copy(db_path: str, backup_dir: str, kind: str, name: str) -> Copy:
    """Delete one copy the listing names, unless it is the one its directory's guard keeps."""
    with _lock:
        found = next((c for c in list_copies(db_path, backup_dir) if c.kind == kind and c.name == name), None)
        if found is None:
            raise CopyNotFound(f"no {kind} copy named {name!r}")
        if found.guarded:
            raise CopyGuarded(found)
        _remove(found)
    return found


def cleanup_copies(db_path: str, backup_dir: str, *, kinds: list[str], older_than_days: int, now: datetime,
                   confirm: str | None) -> tuple[list[Copy], list[Copy], list[tuple[Copy, str]]]:
    """(the set, the guarded copies in scope, the failures). Without `confirm` nothing is deleted: the set is the
    preview. With it, the set is computed again under the lock and deleted only if its digest is `confirm`;
    otherwise CleanupChanged carries the set as it is now."""
    cutoff = now - timedelta(days=older_than_days)
    with _lock:
        listed = [c for c in list_copies(db_path, backup_dir) if c.kind in kinds]
        plan = [c for c in listed if not c.guarded and c.at < cutoff]
        kept = [c for c in listed if c.guarded]
        if confirm is None:
            return plan, kept, []
        if set_digest(c.key for c in plan) != confirm:
            raise CleanupChanged(plan)
        failed = []
        for copy in plan:
            try:
                _remove(copy)
            except OSError as exc:
                failed.append((copy, f"{type(exc).__name__}: {exc}"))
    return plan, kept, failed
```

### Block 2 — local-development/gsd/reporting/artifacts.py: the digest and the refusal it shares

`set_digest` and `CleanupChanged` come from `gsd/housekeeping.py`, so both services compute one digest (§3.3).

<!-- block: local-development/gsd/reporting/artifacts.py | edit -->

Old text:

```python

log = logging.getLogger(__name__)
```

New text:

```python

from ..housekeeping import CleanupChanged, set_digest

log = logging.getLogger(__name__)
```

### Block 3 — local-development/gsd/reporting/artifacts.py: `RunInFlight`

The refusal a queued or running run gets (§3.4), carrying the run so the 409 can name its status.

<!-- block: local-development/gsd/reporting/artifacts.py | edit -->

Old text:

```python
STATUSES = ("queued", "running", "done", "failed")
```

New text:

```python
STATUSES = ("queued", "running", "done", "failed")


class RunInFlight(Exception):
    """A queued or running run was asked to be deleted: it is still the worker's (#542)."""

    def __init__(self, run: "Run") -> None:
        super().__init__(f"run {run.id} is {run.status}")
        self.run = run
```

### Block 4 — local-development/gsd/reporting/artifacts.py: `ArtifactStore.delete` and `ArtifactStore.cleanup`, under the lock `prune()` takes

One run, or a cleanup's preview and confirm, computed and deleted in one hold of `_lock`, so retention and the page never delete one run twice and a confirm deletes exactly the set it was bound to (§3.3, §3.7).

<!-- block: local-development/gsd/reporting/artifacts.py | edit -->

Old text:

```python

    def disk_bytes(self) -> int:
```

New text:

```python

    def delete(self, run_id: str) -> Run:
        """Remove one finished run and its files, at the dashboard's request (#542). Under the lock prune() takes,
        so the two never delete one run twice. A queued or running run is the worker's: refused, as prune() never
        dooms one. KeyError when there is no such run."""
        with self._lock:
            run = self._runs[run_id]
            if run.status not in ("done", "failed"):
                raise RunInFlight(run)
            shutil.rmtree(self._dir(run.id), ignore_errors=True)
            self._runs.pop(run.id, None)
        return run

    def cleanup(self, *, scope: str, older_than_days: int, keep_newest: int, now: datetime,
                confirm: str | None) -> list[Run]:
        """A one-off cleanup (#542): the finished runs in `scope` completed before `now - older_than_days`, beyond
        the newest `keep_newest` of their (schedule, cluster), manual runs being one group per cluster. Without
        `confirm` nothing is deleted: the list is the preview. With it, the list is computed again under the
        lock that deletes it, and deleted only when its digest is `confirm`; otherwise CleanupChanged carries the
        list as it is now. Ages are retention's (`retention_stamp`): completion, else the id."""
        if now.tzinfo is None:
            now = now.replace(tzinfo=UTC)
        cutoff = now - timedelta(days=older_than_days)
        with self._lock:
            finished = [r for r in self._runs.values() if r.status in ("done", "failed")]
            if scope == "manual":
                finished = [r for r in finished if not r.schedule]
            elif scope.startswith("schedule:"):
                finished = [r for r in finished if r.schedule == scope.split(":", 1)[1]]
            groups: dict[tuple[str, str], list[Run]] = {}
            for r in sorted(finished, key=lambda r: (retention_stamp(r), r.id), reverse=True):
                groups.setdefault((r.schedule or "", r.cluster), []).append(r)
            plan = sorted((r for group in groups.values() for i, r in enumerate(group)
                           if i >= keep_newest and retention_stamp(r) < cutoff), key=lambda r: r.id)
            if confirm is None:
                return plan
            if set_digest(r.id for r in plan) != confirm:
                raise CleanupChanged(plan)
            for r in plan:
                shutil.rmtree(self._dir(r.id), ignore_errors=True)
                self._runs.pop(r.id, None)
        return plan

    def disk_bytes(self) -> int:
```

### Block 5 — local-development/gsd/reporting/config.py: the report service's switch

`housekeeping_enabled`, off in the code so the service's default contract stays two non-GETs (§3.8).

<!-- block: local-development/gsd/reporting/config.py | edit -->

Old text:

```python
    max_queued_runs: int = 8
```

New text:

```python
    max_queued_runs: int = 8
    #: The page's deletes (#542, SPEC_H1): DELETE /report/api/runs/{id} and POST /report/api/runs/cleanup, for the
    #: dashboard's service token only. Off, neither route exists, so the token cannot delete a run.
    housekeeping_enabled: bool = False
```

### Block 6 — local-development/gsd/reporting/config.py: read from the environment

`GSD_REPORT_HOUSEKEEPING_ENABLED`, which the chart renders from `housekeeping.enabled` (block 45).

<!-- block: local-development/gsd/reporting/config.py | edit -->

Old text:

```python
        max_queued_runs=_int_env("GSD_REPORT_MAX_QUEUED_RUNS", 8, lo=1, hi=100),
```

New text:

```python
        max_queued_runs=_int_env("GSD_REPORT_MAX_QUEUED_RUNS", 8, lo=1, hi=100),
        housekeeping_enabled=_bool_env("GSD_REPORT_HOUSEKEEPING_ENABLED", False),
```

### Block 7 — local-development/gsd/reporting/server.py: the module docstring names the two routes

The contract the module states for itself (the review of #224 held the docstring to the routes).

<!-- block: local-development/gsd/reporting/server.py | edit -->

Old text:

```python
paths listed by name. Auth is a dependency (`principal`), so a route
```

New text:

```python
paths listed by name. With `housekeeping_enabled` (#542) two more, for the dashboard's service token only:
DELETE /report/api/runs/{run_id} and POST /report/api/runs/cleanup. Auth is a dependency (`principal`), so a route
```

### Block 8 — local-development/gsd/reporting/server.py: the imports

The cleanup request and the digest from `gsd/housekeeping.py`; `RunInFlight` from the store.

<!-- block: local-development/gsd/reporting/server.py | edit -->

Old text:

```python
from .artifacts import FORMATS, ArtifactStore, Run, new_run_id
```

New text:

```python
from ..housekeeping import CleanupChanged, RunCleanupRequest, set_digest
from .artifacts import FORMATS, ArtifactStore, Run, RunInFlight, new_run_id
```

### Block 9 — local-development/gsd/reporting/server.py: `dashboard_only`: the service token, never a ticket

The tier a deletion needs is decided in the dashboard; a viewer's ticket carries only the wide tier (§3.1).

<!-- block: local-development/gsd/reporting/server.py | edit -->

Old text:

```python
            raise HTTPException(status_code=403, detail="the usage feed is read by the dashboard, not by viewers")
```

New text:

```python
            raise HTTPException(status_code=403, detail="the usage feed is read by the dashboard, not by viewers")
        return p

    def dashboard_only(p: Principal = Depends(principal)) -> Principal:
        # #542: the tier a deletion needs (cluster-admin) is decided in the dashboard, which holds the cluster
        # credential this service does not; a viewer's ticket carries only the wide tier, so it never deletes.
        if p.kind != "service":
            raise HTTPException(status_code=403, detail="report runs are deleted through the dashboard, not by viewers")
```

### Block 10 — local-development/gsd/reporting/server.py: `DELETE /report/api/runs/{run_id}` and `POST /report/api/runs/cleanup`

Registered only with the switch, for the service token only; 404, 409 and the 409 carrying the new preview (§3.3, §3.4).

<!-- block: local-development/gsd/reporting/server.py | edit -->

Old text:

```python

    # -- the dashboard's pull -------------------------------------------------------------------
```

New text:

```python

    # -- the page's deletes (#542, docs/specs/SPEC_H1_gui_cleanup.md) --------------------------------

    def _plan_view(plan: list[Run]) -> dict:
        items = [{"id": r.id, "report": r.report, "cluster": r.cluster, "schedule": r.schedule, "status": r.status,
                  "finished_at": r.finished_at, "bytes": sum((r.bytes or {}).values())} for r in plan]
        return {"items": items, "count": len(items), "bytes": sum(i["bytes"] for i in items),
                "digest": set_digest(r.id for r in plan)}

    if settings.housekeeping_enabled:
        @app.delete(f"{REPORT_PREFIX}/api/runs/{{run_id}}")
        def delete_run(run_id: str, p: Principal = Depends(dashboard_only)) -> dict:
            """Delete one finished run and its files, at the dashboard's request; the service token only.

            The dashboard has decided the cluster-admin tier and records who asked. A queued or running run is
            the worker's: 409, as retention never deletes one either. 404 when there is no such run."""
            try:
                run = store.delete(run_id)
            except KeyError as exc:
                raise HTTPException(status_code=404, detail="no such run") from exc
            except RunInFlight as exc:
                raise HTTPException(status_code=409, detail=f"run {run_id} is {exc.run.status}: a queued or running "
                                                            "run is the worker's and is not deleted") from exc
            log.info("deleted report run %s at the dashboard's request", run_id)
            return run.public()

        @app.post(f"{REPORT_PREFIX}/api/runs/cleanup")
        def cleanup_runs(body: RunCleanupRequest, p: Principal = Depends(dashboard_only)) -> dict:
            """Preview a one-off cleanup of finished runs, or delete exactly the previewed set; the service token only.

            Without `confirm` nothing is deleted and the answer is the set with its digest. With the digest, the
            set is computed again under the store's lock and deleted only if it is the same set; otherwise 409
            with the set as it is now, and nothing deleted."""
            try:
                plan = store.cleanup(scope=body.scope, older_than_days=body.older_than_days,
                                     keep_newest=body.keep_newest, now=now(), confirm=body.confirm)
            except CleanupChanged as exc:
                raise HTTPException(status_code=409, detail={
                    "message": "the runs this cleanup would delete changed since the preview; nothing was deleted",
                    "preview": _plan_view(exc.plan)}) from exc
            if body.confirm is not None:
                log.info("deleted %d report run(s) in a cleanup at the dashboard's request", len(plan))
            return {"preview": body.confirm is None, **_plan_view(plan)}

    # -- the dashboard's pull -------------------------------------------------------------------
```

### Block 11 — local-development/gsd/config.py: the dashboard's switch

`housekeeping_enabled`, off in the code so `test_r6_the_api_is_read_only` keeps its GET-only default; the chart renders it on (§3.8).

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
    cluster_secrets_writes_enabled: bool = False
```

New text:

```python
    cluster_secrets_writes_enabled: bool = False
    # SPEC_H1 (#542): the page's deletes of report runs and database copies, for the cluster-admin tier. OFF here so
    # the code's default API stays GET-only (test_r6_the_api_is_read_only); the chart's `housekeeping.enabled`
    # renders it ON (no RBAC, credential or second image: the deletion is file work in the pods' own volumes).
    housekeeping_enabled: bool = False
```

### Block 12 — local-development/gsd/config.py: read from the ConfigMap

`housekeepingEnabled` in `clusters.yaml`, as `clusterSecretsWritesEnabled` is read (block 44 renders it).

<!-- block: local-development/gsd/config.py | edit -->

Old text:

```python
        cluster_secrets_writes_enabled=_bool_setting(raw, "GSD_CLUSTER_SECRETS_WRITES_ENABLED", "clusterSecretsWritesEnabled", False),
```

New text:

```python
        cluster_secrets_writes_enabled=_bool_setting(raw, "GSD_CLUSTER_SECRETS_WRITES_ENABLED", "clusterSecretsWritesEnabled", False),
        housekeeping_enabled=_bool_setting(raw, "GSD_HOUSEKEEPING_ENABLED", "housekeepingEnabled", False),
```

### Block 13 — local-development/gsd/api.py: the imports

#245's `event` for the audit line and the new module.

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
from .activity import EMAIL_HEADER, INTERACTION_HEADER, USER_HEADER, ActivityRecorder
```

New text:

```python
from .activity import EMAIL_HEADER, INTERACTION_HEADER, USER_HEADER, ActivityRecorder
from .clusterconfig.events import event
from . import housekeeping
```

### Block 14 — local-development/gsd/api.py: the gate, the report-service call, the audit, and the five routes

A proxy-verified identity and the cluster-admin tier on every route, the custom header on every write (§3.1, §3.9); copies deleted here, runs through the report service with the service token (§3.1); one audit line and one count per item (§3.10).

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
                _request_discovery()
```

New text:

```python
                _request_discovery()
            return answer

    # ── SPEC_H1 (#542): deleting report runs and database copies from the page ───────────────────────
    # A one-off cleanup, nothing persisted: reporting.retention and config.backup stay the standing policy. Five
    # routes, registered only with `housekeeping.enabled`, each behind a proxy-verified identity and the
    # cluster-admin tier (#322), as the cluster-configuration writes are; one audit line per deleted item and
    # gsd_housekeeping_deleted_total{kind}, never a name. A copy is file work on this pod's data volume; a report
    # run is deleted by the report service at this process's request, with the service token, because the tier is
    # decided here (the report service holds no cluster credential).

    def _housekeeping_gate(request: Request) -> str:
        """The viewer a deletion is recorded against: a proxy-verified identity and the cluster-admin tier, or
        the refusal. With restrictions off or no proxy there is no identity to record, so it refuses, as
        `_writes_gate` does."""
        viewer = trusted_viewer(request)
        if not viewer or not restrict:
            signals.note_admin_refusal()
            raise HTTPException(status_code=403,
                                detail="Deleting reports and database copies is reserved to cluster administrators, "
                                       "and needs an authenticated identity to record the deletion against.")
        require_cluster_admin(request, "Deleting reports and database copies is reserved to cluster administrators.")
        return viewer

    def _housekeeping_write(request: Request) -> str:
        """The gate, then the custom header the page sends with every write (OWASP's custom-request-header
        defence): a browser preflights a cross-site request carrying it, and this app answers no preflight."""
        viewer = _housekeeping_gate(request)
        if not request.headers.get(INTERACTION_HEADER):
            raise HTTPException(status_code=403, detail="a deletion is sent by the dashboard's page, with the "
                                                        "X-GSD-Interaction header; this request has none")
        return viewer

    def _report_call(method: str, path: str, body: dict | None = None) -> dict:
        """One call to the report service as the dashboard, with the service token. Its 404, 409 and 422 are passed
        through with their detail; anything else it answers, or no answer, is a 502 that names the report service."""
        import httpx
        if not settings.reporting_url or report_secret is None:
            raise HTTPException(status_code=404, detail="reporting is not enabled on this deployment")
        client = getattr(app.state, "report_client", None)
        if client is None:
            client = httpx.Client(base_url=settings.reporting_url, verify=settings.reporting_ca_file or True,
                                  timeout=settings.request_timeout_seconds)
            app.state.report_client = client
        try:
            r = client.request(method, f"{REPORT_PREFIX}{path}", json=body,
                               headers={"Authorization": f"Bearer {report_secret.decode('utf-8')}"})
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=502, detail=f"the report service could not be reached: "
                                                        f"{type(exc).__name__}") from exc
        if r.status_code in (404, 409, 422):
            try:
                detail = r.json().get("detail")
            except ValueError:
                detail = r.text[:200]
            raise HTTPException(status_code=r.status_code, detail=detail)
        if r.status_code != 200:
            raise HTTPException(status_code=502, detail=f"the report service answered {r.status_code}")
        return r.json()

    def _record_run(run: dict, viewer: str) -> None:
        event(log, logging.INFO, "report-run-deleted", run=run.get("id"), report=run.get("report"),
              cluster=run.get("cluster"), schedule=run.get("schedule"),
              bytes=run["bytes"] if isinstance(run.get("bytes"), int) else sum((run.get("bytes") or {}).values()),
              by=viewer)
        signals.note_housekeeping_deleted("report-run", 1)

    def _record_copy(copy: housekeeping.Copy, viewer: str) -> None:
        event(log, logging.INFO, "db-copy-deleted", kind=copy.kind, copy=copy.name, directory=str(copy.path.parent),
              bytes=copy.bytes, by=viewer)
        signals.note_housekeeping_deleted(copy.kind, 1)

    if settings.housekeeping_enabled:
        @app.get("/api/housekeeping/copies")
        def housekeeping_copies(request: Request) -> dict:
            """SPEC_H1 (#542): the database copies on this pod's data volume, newest first, the guarded ones with why."""
            _housekeeping_gate(request)
            dirs = housekeeping.copy_dirs(settings.db_path, settings.backup_dir)
            copies = housekeeping.list_copies(settings.db_path, settings.backup_dir)
            return {"pod": os.environ.get("POD_NAME") or None,
                    "directories": {kind: str(d) if d else None for kind, d in dirs.items()},
                    "copies": [c.public() for c in copies]}

        @app.delete("/api/housekeeping/copies/{kind}/{name}")
        def delete_housekeeping_copy(request: Request, kind: str, name: str) -> dict:
            """SPEC_H1 (#542): delete one database copy this pod lists; the newest of each directory is refused (409)."""
            viewer = _housekeeping_write(request)
            if kind not in housekeeping.COPY_KINDS:
                raise HTTPException(status_code=404, detail=f"unknown kind {kind!r}; one of {', '.join(housekeeping.COPY_KINDS)}")
            try:
                copy = housekeeping.delete_copy(settings.db_path, settings.backup_dir, kind, name)
            except housekeeping.CopyNotFound as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
            except housekeeping.CopyGuarded as exc:
                raise HTTPException(status_code=409, detail=exc.copy.guarded) from exc
            except OSError as exc:
                raise HTTPException(status_code=500, detail=f"{kind}/{name} could not be deleted: {type(exc).__name__}: "
                                                            f"{exc}") from exc
            _record_copy(copy, viewer)
            return {"deleted": copy.public()}

        @app.post("/api/housekeeping/copies/cleanup")
        def cleanup_housekeeping_copies(request: Request, body: housekeeping.CopyCleanupRequest) -> dict:
            """SPEC_H1 (#542): preview a one-off cleanup of database copies, or delete exactly the previewed set.

            Without `confirm` nothing is deleted. With the preview's digest, the set is computed again and deleted
            only if it is the same set; otherwise 409 with the set as it is now. The guarded copies are never in it."""
            viewer = _housekeeping_write(request)

            def view(plan: list[housekeeping.Copy]) -> dict:
                return {"items": [c.public() for c in plan], "count": len(plan), "bytes": sum(c.bytes for c in plan),
                        "digest": housekeeping.set_digest(c.key for c in plan)}

            try:
                plan, kept, failed = housekeeping.cleanup_copies(
                    settings.db_path, settings.backup_dir, kinds=list(body.kinds),
                    older_than_days=body.older_than_days, now=datetime.now(UTC), confirm=body.confirm)
            except housekeeping.CleanupChanged as exc:
                raise HTTPException(status_code=409, detail={
                    "message": "the copies this cleanup would delete changed since the preview; nothing was deleted",
                    "preview": view(exc.plan)}) from exc
            out = {"preview": body.confirm is None, **view(plan), "kept": [c.public() for c in kept]}
            if body.confirm is not None:
                broken = {c.key for c, _ in failed}
                for copy in plan:
                    if copy.key not in broken:
                        _record_copy(copy, viewer)
                out["failed"] = [{"kind": c.kind, "name": c.name, "error": why} for c, why in failed]
            return out

        @app.delete("/api/housekeeping/reports/{run_id}")
        def delete_housekeeping_report(request: Request, run_id: str) -> dict:
            """SPEC_H1 (#542): delete one finished report run and its files; a queued or running run is refused (409)."""
            viewer = _housekeeping_write(request)
            run = _report_call("DELETE", f"/api/runs/{quote(run_id, safe='')}")
            _record_run(run, viewer)
            return {"deleted": run}

        @app.post("/api/housekeeping/reports/cleanup")
        def cleanup_housekeeping_reports(request: Request, body: housekeeping.RunCleanupRequest) -> dict:
            """SPEC_H1 (#542): preview a one-off cleanup of report runs, or delete exactly the previewed set.

            The report service computes the set under its store's lock, the lock its retention prunes under, and
            refuses a confirm whose digest is not the set's now (409, with the set as it is now)."""
            viewer = _housekeeping_write(request)
            answer = _report_call("POST", "/api/runs/cleanup", body.model_dump())
            if body.confirm is not None:
                for run in answer.get("items", []):
                    _record_run(run, viewer)
```

### Block 15 — local-development/gsd/api.py: `features.housekeeping` on `/api/version`

The page shows its controls only where the deployment switched the deletes on (§3.11).

<!-- block: local-development/gsd/api.py | edit -->

Old text:

```python
                "reporting": bool(settings.reporting_url), "reporting_prefix": REPORT_PREFIX}
```

New text:

```python
                "reporting": bool(settings.reporting_url), "reporting_prefix": REPORT_PREFIX,
                "housekeeping": settings.housekeeping_enabled}
```

### Block 16 — local-development/gsd/metrics.py: the kind vocabulary

The counter's only label comes from `KINDS`, a closed set (§3.10).

<!-- block: local-development/gsd/metrics.py | edit -->

Old text:

```python
from . import __version__, state as st
```

New text:

```python
from . import __version__, state as st
from .housekeeping import KINDS as HOUSEKEEPING_KINDS
```

### Block 17 — local-development/gsd/metrics.py: the counter's store

Process-local, like every event counter in `RuntimeSignals`.

<!-- block: local-development/gsd/metrics.py | edit -->

Old text:

```python
        self._admin_refusals = 0
```

New text:

```python
        self._admin_refusals = 0
        self._housekeeping: dict[str, int] = {}
```

### Block 18 — local-development/gsd/metrics.py: `note_housekeeping_deleted`

The call site names the kind and a count, never who or which (§3.10).

<!-- block: local-development/gsd/metrics.py | edit -->

Old text:

```python

    def note_binding_changes(self, cluster: str, change: str, subject_kind: str, count: int) -> None:
```

New text:

```python

    def note_housekeeping_deleted(self, kind: str, count: int) -> None:
        """Items a person deleted from the page (#542), by kind — never who, never which."""
        if count <= 0:
            return
        with self._lock:
            self._housekeeping[kind] = self._housekeeping.get(kind, 0) + count

    def note_binding_changes(self, cluster: str, change: str, subject_kind: str, count: int) -> None:
```

### Block 19 — local-development/gsd/metrics.py: the snapshot carries it

One consistent copy for the collector, as for the other counters.

<!-- block: local-development/gsd/metrics.py | edit -->

Old text:

```python
                "backup_failures": self._backup_failures,
```

New text:

```python
                "backup_failures": self._backup_failures,
                "housekeeping": dict(self._housekeeping),
```

### Block 20 — local-development/gsd/metrics.py: `gsd_housekeeping_deleted_total`

Declared on a bare collector with no samples, the rule `test_event_families_are_declared_even_unwired` states for event families.

<!-- block: local-development/gsd/metrics.py | edit -->

Old text:

```python
        )
        binding_changes = CounterMetricFamily(
```

New text:

```python
        )
        housekeeping_deleted = CounterMetricFamily(
            "gsd_housekeeping_deleted_total",
            "Items deleted from the page by a cluster administrator (#542): report runs, and database copies by "
            "directory (backup, pre-upgrade, pre-restore). Who and which are in the audit log line, never here. "
            "Retention's own deletions are not counted. Pre-seeded to 0 per kind. Per replica: sum().",
            labels=["kind"],
        )
        binding_changes = CounterMetricFamily(
```

### Block 21 — local-development/gsd/metrics.py: pre-seeded to 0 per kind

So `increase()` has a baseline from the first scrape.

<!-- block: local-development/gsd/metrics.py | edit -->

Old text:

```python
            backup_failures.add_metric([], snap["backup_failures"])
```

New text:

```python
            backup_failures.add_metric([], snap["backup_failures"])
            for kind in HOUSEKEEPING_KINDS:
                housekeeping_deleted.add_metric([kind], snap["housekeeping"].get(kind, 0))
```

### Block 22 — local-development/gsd/metrics.py: yielded

Beside the backup failures it sits next to.

<!-- block: local-development/gsd/metrics.py | edit -->

Old text:

```python
        yield from (checks, decisions, refusals, retention, backup_failures, audit_unmatched,
```

New text:

```python
        yield from (checks, decisions, refusals, retention, backup_failures, housekeeping_deleted, audit_unmatched,
```

### Block 23 — local-development/gsd/static/index.html: `data.hkCopies`

The copies listing the KPI page fetches (§3.11).

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
             libraryRun: null,   // #229: the positioned run by id — a history past the listing's page still opens (Codex)
```

New text:

```html
             libraryRun: null,   // #229: the positioned run by id — a history past the listing's page still opens (Codex)
             hkCopies: null,   // #542: the database copies on the answering pod's data volume, for the KPI page
```

### Block 24 — local-development/gsd/static/index.html: the KPI page draws the copies card under Backups

SPEC_E6's card is the place the copies are already described (mandate, design question 2).

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
  ${kpiBackups(k)}
```

New text:

```html
  ${kpiBackups(k)}
  ${kpiCopiesCard()}
```

### Block 25 — local-development/gsd/static/index.html: `wireKpi` wires the card

The card's buttons and form.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
  });
  if (kpiAgoTimer == null) {
```

New text:

```html
  });
  wireHousekeeping();
  if (kpiAgoTimer == null) {
```

### Block 26 — local-development/gsd/static/index.html: the run drawer's delete

A two-step Delete / Confirm delete in the drawer's actions, absent below the tier and for a run in flight (§3.11).

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
        <button type="button" class="btn" id="drawer-close-2">Close</button>
      </div>
```

New text:

```html
        ${libraryDeleteControl(run)}
        <button type="button" class="btn" id="drawer-close-2">Close</button>
      </div>
      ${libraryDeleteNote(run)}
```

### Block 27 — local-development/gsd/static/index.html: the Library draws the Clean up card

Below the sections, above the drawer (mandate, design question 2).

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
    ${sections.length ? sections.map((sec) => librarySectionHtml(sec, allRuns)).join("") : `<section class="card"><div class="empty-note">No report is enabled on this deployment.</div></section>`}
```

New text:

```html
    ${sections.length ? sections.map((sec) => librarySectionHtml(sec, allRuns)).join("") : `<section class="card"><div class="empty-note">No report is enabled on this deployment.</div></section>`}
    ${libraryCleanupCard(allRuns)}
```

### Block 28 — local-development/gsd/static/index.html: `wireLibrary` wires them, and the page's half of #542

`housekeepingOn`, the two cards, the drawer control, and `wireHousekeeping`: the preview, the confirm with its digest, the 409's new preview (§3.11).

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
  if (openHtml) openHtml.onclick = () => { openArtifactInNewTab(openHtml.dataset.openHtml).catch((err) => { openHtml.textContent = `Could not open: ${err.message}`; }); };
}


```

New text:

```html
  if (openHtml) openHtml.onclick = () => { openArtifactInNewTab(openHtml.dataset.openHtml).catch((err) => { openHtml.textContent = `Could not open: ${err.message}`; }); };
  wireHousekeeping();
}


/* ─── #542 SPEC_H1: deleting report runs and database copies — docs/specs/SPEC_H1_gui_cleanup.md ─────────────────
   For the cluster-admin tier only (#322), and only where the deployment switched it on (`housekeeping.enabled`):
   the API refuses everyone else with the tier's own sentence, and the page draws no control for them. A one-off
   cleanup, nothing saved: `reporting.retention` and `config.backup` stay the standing policy. A cleanup is a preview
   of exactly what goes, then a confirm that carries the preview's digest; a set that changed in between is refused
   (409) and its new preview shown. A single delete is the Cluster Configurations tab's two steps: Delete, then
   Confirm delete. */
function housekeepingOn() {
  const v = data.version;
  return !!(v && v.features && v.features.housekeeping === true) && clusterAdmin();
}
// What the reader typed and what the last answer said, kept across the poll's repaints; never in the URL.
const hk = { runs: { scope: "all", days: 30, keep: 2, preview: null, note: "" },
             copies: { kind: "", days: 30, preview: null, note: "" },
             armed: null, notes: Object.create(null) };

function hkPreviewHtml(which, p, noun) {
  if (!p) return "";
  if (!p.count) return `<p class="hk-note" id="hk-${which}-none">Nothing matches: no ${noun} would be deleted.</p>`;
  const rows = p.items.map((i) => `<li class="mono">${esc(which === "runs"
    ? `${i.id} · ${i.report} · ${i.cluster} · ${i.schedule || "manual"}` : `${i.kind}/${i.name}`)} · ${esc(fmtBytes(i.bytes))}</li>`).join("");
  return `<div class="hk-preview" id="hk-${which}-preview">
    <p>${p.count} ${noun}${p.count === 1 ? "" : "s"}, ${esc(fmtBytes(p.bytes))}, would be deleted:</p>
    <ul class="hk-list">${rows}</ul>
    <div class="acts"><button type="button" class="btn btn-acc" id="hk-${which}-confirm">Delete ${p.count === 1 ? `this ${noun}` : `these ${p.count} ${noun}s`}</button>
      <button type="button" class="btn" id="hk-${which}-cancel">Cancel</button></div></div>`;
}

// The Library's "Clean up" card: every schedule the service knows and every schedule a run still names, so the
// runs of a retired schedule (kept by keepPerSchedule forever) can be chosen too.
function libraryCleanupCard(allRuns) {
  if (!housekeepingOn()) return "";
  const f = hk.runs;
  const names = [...new Set([...((data.reportStatus && data.reportStatus.schedules) || []).map((s) => s.name),
                             ...allRuns.map((r) => r.schedule).filter(Boolean)])].sort();
  const opt = (v, label) => `<option value="${esc(v)}"${f.scope === v ? " selected" : ""}>${esc(label)}</option>`;
  return `<section class="card" id="lib-cleanup">
    <h2>Clean up</h2>
    <div class="filterbar-note">A one-off cleanup for cluster administrators: nothing is saved, and <code>reporting.retention</code> stays the
      standing policy. A queued or running run is never deleted. Preview first: the delete removes exactly the runs the preview lists.</div>
    <div class="hk-form">
      <label>Runs <select id="hk-runs-scope">${opt("all", "every run")}${opt("manual", "manual runs")}${names.map((n) => opt(`schedule:${n}`, `schedule ${n}`)).join("")}</select></label>
      <label>Older than <input type="number" id="hk-runs-days" min="0" max="3650" value="${esc(String(f.days))}"> days</label>
      <label>Keep the newest <input type="number" id="hk-runs-keep" min="0" max="1000" value="${esc(String(f.keep))}"> of each schedule and cluster</label>
      <button type="button" class="btn" id="hk-runs-preview">Preview</button>
    </div>
    ${f.note ? `<p class="hk-note" id="hk-runs-note" role="status">${esc(f.note)}</p>` : ""}
    ${hkPreviewHtml("runs", f.preview, "run")}
  </section>`;
}

// The run drawer's delete: absent below the tier, and for a run still queued or running (the worker's).
function libraryDeleteControl(run) {
  if (!housekeepingOn() || (run.status !== "done" && run.status !== "failed")) return "";
  const key = `run:${run.id}`;
  return `<button type="button" class="btn" id="drawer-delete" data-hk-run="${esc(run.id)}">${hk.armed === key ? "Confirm delete" : "Delete this run"}</button>`;
}
function libraryDeleteNote(run) {
  const key = `run:${run.id}`;
  const text = hk.armed === key ? "Deletes the run and its files. This cannot be undone." : hk.notes[key];
  return housekeepingOn() && text ? `<p class="hk-note" id="drawer-delete-msg" role="status">${esc(text)}</p>` : "";
}

// The KPI page's "Database copies" card, under Backups: the copies on the answering pod's data volume.
function kpiCopiesCard() {
  if (!housekeepingOn()) return "";
  const d = data.hkCopies;
  if (!d || d.forbidden) return `<section class="card kpi-page" id="hk-copies"><h2>Database copies</h2><div class="empty-note">${d ? "Not available to this reader." : "Loading…"}</div></section>`;
  const f = hk.copies;
  const rows = d.copies.map((c) => {
    const key = `${c.kind}/${c.name}`;
    const act = c.guarded
      ? `<span class="hk-kept">kept: ${esc(c.guarded)}</span>`
      : `<button type="button" class="btn" data-hk-copy="${esc(key)}" id="hk-del-${esc(key)}">${hk.armed === `copy:${key}` ? "Confirm delete" : "Delete"}</button>${hk.notes[`copy:${key}`] ? ` <span class="hk-note">${esc(hk.notes[`copy:${key}`])}</span>` : ""}`;
    return `<tr data-hk-row="${esc(key)}"><td>${esc(c.kind)}</td><td class="mono cname">${esc(c.name)}${c.type === "directory" ? "/" : ""}</td>
      <td>${fmtTime(c.at)}</td><td class="num">${esc(fmtBytes(c.bytes))}</td><td>${act}</td></tr>`;
  }).join("");
  const opt = (v, label) => `<option value="${esc(v)}"${f.kind === v ? " selected" : ""}>${esc(label)}</option>`;
  const dirs = Object.entries(d.directories).filter(([, v]) => v).map(([k, v]) => `${esc(k)} <span class="mono">${esc(v)}</span>`).join(" · ");
  return `<section class="card kpi-page" id="hk-copies">
    <h2>Database copies${d.pod ? ` <span class="asof">on ${esc(d.pod)}</span>` : ""}</h2>
    <div class="hk-note">${dirs}</div>
    <div class="filterbar-note">For cluster administrators: delete a copy, or clean up a directory once. Nothing is saved, and
      <code>config.backup</code> stays the standing policy. The newest copy in each directory is always kept: the newest backup (a restore needs
      one), the newest pre-upgrade copy (the way back across the last upgrade) and the newest pre-restore set (the way back from the last restore).</div>
    ${d.copies.length ? `<div class="scroll-x"><table><thead><tr><th>Directory</th><th>Copy</th><th>Taken</th><th class="num">Size</th><th></th></tr></thead>
      <tbody>${rows}</tbody></table></div>` : `<div class="empty-note">No copies in these directories.</div>`}
    <div class="hk-form">
      <label>Directory <select id="hk-copies-kind">${opt("", "all three")}${opt("backup", "backup")}${opt("pre-upgrade", "pre-upgrade")}${opt("pre-restore", "pre-restore")}</select></label>
      <label>Older than <input type="number" id="hk-copies-days" min="0" max="3650" value="${esc(String(f.days))}"> days</label>
      <button type="button" class="btn" id="hk-copies-preview">Preview</button>
    </div>
    ${f.note ? `<p class="hk-note" id="hk-copies-note" role="status">${esc(f.note)}</p>` : ""}
    ${hkPreviewHtml("copies", f.preview, "copy")}
  </section>`;
}

// A number field as the API takes it: a whole number within the field's bounds.
function hkWhole(value, max) { const n = Math.floor(Number(value)); return Number.isFinite(n) ? Math.min(Math.max(n, 0), max) : 0; }

function wireHousekeeping() {
  if (!housekeepingOn()) return;
  const drawerDelete = $("drawer-delete");
  if (drawerDelete) drawerDelete.onclick = async () => {
    const id = drawerDelete.dataset.hkRun, key = `run:${id}`;
    if (hk.armed !== key) { hk.armed = key; render(); return; }
    hk.armed = null;
    try {
      await apiSend(`/api/housekeeping/reports/${encodeURIComponent(id)}`, "DELETE");
      hk.runs.note = `Run ${id} deleted.`;
      navigate({ run: null });
    } catch (e) { hk.notes[key] = e.message; }
    render(); refresh();
  };
  document.querySelectorAll("[data-hk-copy]").forEach((el) => {
    el.onclick = async () => {
      const name = el.dataset.hkCopy, key = `copy:${name}`, slash = name.indexOf("/");
      if (hk.armed !== key) { hk.armed = key; render(); return; }
      hk.armed = null;
      try {
        await apiSend(`/api/housekeeping/copies/${encodeURIComponent(name.slice(0, slash))}/${encodeURIComponent(name.slice(slash + 1))}`, "DELETE");
        hk.copies.note = `${name} deleted.`;
      } catch (e) { hk.notes[key] = e.message; }
      render(); refresh();
    };
  });
  const forms = {
    runs: { path: "/api/housekeeping/reports/cleanup", noun: "run",
            body: () => ({ scope: hk.runs.scope, older_than_days: hkWhole(hk.runs.days, 3650), keep_newest: hkWhole(hk.runs.keep, 1000) }),
            fields: { scope: "hk-runs-scope", days: "hk-runs-days", keep: "hk-runs-keep" } },
    copies: { path: "/api/housekeeping/copies/cleanup", noun: "copy",
              body: () => ({ kinds: hk.copies.kind ? [hk.copies.kind] : ["backup", "pre-upgrade", "pre-restore"], older_than_days: hkWhole(hk.copies.days, 3650) }),
              fields: { kind: "hk-copies-kind", days: "hk-copies-days" } },
  };
  Object.entries(forms).forEach(([which, form]) => {
    const state = hk[which];
    // A changed bound is a different set: the preview on screen no longer describes it.
    Object.entries(form.fields).forEach(([field, id]) => {
      const el = $(id);
      if (el) el.onchange = () => { state[field] = el.value; if (state.preview) { state.preview = null; render(); } };
    });
    const send = async (confirm) => {
      try {
        const r = await apiSend(form.path, "POST", confirm ? { ...form.body(), confirm } : form.body());
        if (confirm) {
          state.preview = null;
          state.note = `Deleted ${r.count} ${form.noun}${r.count === 1 ? "" : "s"}, ${fmtBytes(r.bytes)}.`
            + (r.failed && r.failed.length ? ` ${r.failed.length} could not be deleted: ${r.failed.map((x) => `${x.kind}/${x.name} (${x.error})`).join(", ")}.` : "");
          refresh();
        } else { state.preview = r; state.note = ""; }
      } catch (e) {
        if (e.status === 409 && e.detail && e.detail.preview) {
          state.preview = e.detail.preview;
          state.note = `${e.detail.message}. This is the set now; delete it, or cancel.`;
        } else { state.note = e.message; }
      }
      render();
    };
    const preview = $(`hk-${which}-preview`), confirmBtn = $(`hk-${which}-confirm`), cancel = $(`hk-${which}-cancel`);
    if (preview) preview.onclick = () => send(null);
    if (confirmBtn) confirmBtn.onclick = () => send(state.preview.digest);
    if (cancel) cancel.onclick = () => { state.preview = null; state.note = ""; render(); };
  });
}

```

### Block 29 — local-development/gsd/static/index.html: the fingerprint carries the copies

A copy the rotation adds or removes must repaint the card (the #157/#167/#228 omission).

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
    kpi: data.kpi,   // #157 (review, Codex): left out, a poll whose only change was a KPI never repainted the page
```

New text:

```html
    kpi: data.kpi,   // #157 (review, Codex): left out, a poll whose only change was a KPI never repainted the page
    hkCopies: data.hkCopies,   // #542: a copy the rotation added or removed must repaint the copies card
```

### Block 30 — local-development/gsd/static/index.html: the KPI page fetches the copies

Only where the deployment switched the deletes on and for the tier the page already requires.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
      want.kpi = guard403(get("/api/kpi"));
```

New text:

```html
      want.kpi = guard403(get("/api/kpi"));
      // #542: the copies card, only where the deployment switched the deletes on; same tier as the page
      if (housekeepingOn()) want.hkCopies = guard403(get("/api/housekeeping/copies"));
```

### Block 31 — local-development/gsd/static/index.html: the answer is kept

As every other payload is.

<!-- block: local-development/gsd/static/index.html | edit -->

Old text:

```html
    if ("library" in got) data.library = got.library;
```

New text:

```html
    if ("library" in got) data.library = got.library;
    if ("hkCopies" in got) data.hkCopies = got.hkCopies;
```

### Block 32 — local-development/gsd/static/app.css: the two cards' styles

Tokens only (`tests/test_type_scale.py`); the preview list scrolls inside the card.

<!-- block: local-development/gsd/static/app.css | edit -->

Old text:

```css
.note-found { padding: var(--space-6) 0; color: var(--text-secondary); }
```

New text:

```css
.note-found { padding: var(--space-6) 0; color: var(--text-secondary); }
/* #542 (SPEC_H1): the Library's "Clean up" card and the KPI page's "Database copies" card */
.hk-form { display: flex; flex-wrap: wrap; align-items: center; gap: var(--space-4) var(--space-8); margin-top: var(--space-6); font-size: var(--text-sm); }
.hk-form input[type="number"] { width: 6em; }
.hk-note, .hk-kept { font-size: var(--text-sm); color: var(--text-muted); overflow-wrap: anywhere; }
.hk-preview { margin-top: var(--space-6); font-size: var(--text-sm); }
.hk-list { list-style: none; margin: var(--space-4) 0; padding: 0; max-height: 320px; overflow: auto; overflow-wrap: anywhere; }
.hk-preview .acts { display: flex; flex-wrap: wrap; gap: var(--space-4); }
```

### Block 33 — local-development/tests/test_housekeeping.py: T542-1 to T542-7, T542-9 to T542-11 and T542-13

The API's half, against the real report app through the `app.state.report_client` seam and a data volume laid out as the lab's (§4).

<!-- block: local-development/tests/test_housekeeping.py | create -->

```python
"""SPEC_H1 (#542): deleting report runs and database copies from the page — the API's half.

The dashboard decides the cluster-admin tier and records who deleted what; a report run is deleted by the report
service at the dashboard's request, with the service token; a database copy is file work on the dashboard's own
data volume. Every case runs against the real report app, reached through the `app.state.report_client` seam,
and a data volume laid out the way the lab's is (docs/specs/SPEC_H1_gui_cleanup.md §2): scheduled backups, two
pre-upgrade copies with their sidecars, and in pre-restore/ two kept sets (one stamped by restore-db.py, one by
the runbook's manual keep), a copy moved aside with its sidecar, and a keep that never finished.

Personas: `jane.admin` passes the cluster-admin tier; `auditor` passes the wide tier and fails this one (the
negative control); `alice` passes neither.
"""

from __future__ import annotations

import dataclasses
import logging
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from gsd import housekeeping
from gsd.api import build_app
from gsd.config import ClusterConfig, Settings
from gsd.reporting import REPORT_PREFIX
from gsd.reporting.artifacts import Run
from gsd.reporting.config import ReportSettings
from gsd.reporting.server import build_report_app
from test_visibility import _MapResolver

SECRET = b"h" * 48
SENTENCE = "For cluster administrators only."
ADMIN = "jane.admin"
SCHEDULE = "nightly-namespace-access"
NOW = datetime.now(UTC)


def H(user: str | None, *, page: bool = True) -> dict:
    """The proxy's identity header, and the custom header the page sends with every write."""
    headers = {"X-Forwarded-User": user} if user else {}
    return {**headers, "X-GSD-Interaction": "1"} if page else headers


def _stamp(days: float, *, micro: bool = True) -> str:
    return (NOW - timedelta(days=days)).strftime("%Y%m%dT%H%M%S.%fZ" if micro else "%Y%m%dT%H%M%SZ")


def _run(rid: str, *, days: float, schedule: str | None = None, status: str = "done", report: str = "groups") -> Run:
    finished = (NOW - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return Run(id=rid, report=report, cluster="c1", params={}, formats=["html"],
               generated_by=f"schedule:{schedule}" if schedule else "jane.smith", generated_by_note="n",
               schedule=schedule, requested_at=finished, started_at=finished,
               finished_at=finished if status in ("done", "failed") else None, status=status,
               bytes={"json": 100, "html": 200} if status == "done" else {})


def _file(path: Path, data: bytes = b"SQLite format 3\x00copy", *, sidecar: bool = False) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    if sidecar:
        path.with_name(path.name + ".sha256").write_text(f"{'0' * 64}  {path.name}\n")
    return path


@dataclasses.dataclass
class Rig:
    client: TestClient
    app: object
    report_app: object
    data: Path

    @property
    def runs(self) -> set[str]:
        return set(self.report_app.state.store._runs)

    def names(self, kind: str) -> set[str]:
        return {c.name for c in housekeeping.list_copies(str(self.data / "gsd.db"), str(self.data / "backup"))
                if c.kind == kind}


def _layout(data: Path) -> None:
    """The lab's shapes, measured 2026-10-02 (SPEC_H1 §2.6): ages in days before now."""
    _file(data / "backup" / f"gsd-{_stamp(20)}.db")
    _file(data / "backup" / f"gsd-{_stamp(10)}.db")
    _file(data / "backup" / f"gsd-{_stamp(1)}.db")                       # the newest: guarded
    _file(data / "pre-upgrade" / f"pre-upgrade-{_stamp(40)}-schema-19-to-20-pod-a.db", sidecar=True)
    _file(data / "pre-upgrade" / f"pre-upgrade-{_stamp(5)}-schema-20-to-21-pod-b.db", sidecar=True)   # guarded
    _file(data / "pre-restore" / _stamp(30) / "gsd.db")                 # restore-db.py's keep
    _file(data / "pre-restore" / _stamp(30) / "gsd.db-wal", b"wal")
    _file(data / "pre-restore" / _stamp(3, micro=False) / "gsd.db")     # the runbook's manual keep: guarded
    _file(data / "pre-restore" / f"pre-upgrade-{_stamp(2)}-schema-21-to-22-pod-c.db", sidecar=True)   # moved aside
    _file(data / "pre-restore" / f"{_stamp(1)}.tmp" / "gsd.db")         # a keep that never finished: never listed


def _rig(tmp_path: Path, **over) -> tuple[TestClient, object, object, Path]:
    data, artifacts, snapshots = tmp_path / "data", tmp_path / "artifacts", tmp_path / "snapshots"
    for d in (data, artifacts, snapshots):
        d.mkdir()
    token = tmp_path / "token"
    token.write_bytes(SECRET)
    _layout(data)
    report_app = build_report_app(ReportSettings(snapshot_dir=str(snapshots), artifact_dir=str(artifacts),
                                                 pdf_enabled=False, housekeeping_enabled=True), secret=SECRET)
    store = report_app.state.store
    for run in (_run("20260101T000000.000000Z-m0ld", days=10), _run("20260102T000000.000000Z-mnew", days=1),
                *(_run(f"2026010{i}T000000.000000Z-s00{i}", days=5.5 - i, schedule=SCHEDULE) for i in range(1, 5)),
                _run("20260109T000000.000000Z-qued", days=0, status="queued"),
                _run("20260109T000001.000000Z-runn", days=0, schedule=SCHEDULE, status="running")):
        store.create(run)
        if run.status == "done":
            store.write(run.id, "html", b"<p>run</p>")
    settings = dict(clusters=[ClusterConfig("c1", "https://api.c1.example.com:6443", token_env="X")],
                    db_path=str(data / "gsd.db"), backup_dir=str(data / "backup"), oauth_proxy_enabled=True,
                    housekeeping_enabled=True, reporting_url="http://report", reporting_token_file=str(token))
    settings.update(over)
    app = build_app(Settings(**settings), run_poller=False)
    app.state.tier_resolver = _MapResolver({ADMIN: "all", "auditor": "all"})
    app.state.cluster_admin_resolver = _MapResolver({ADMIN: "all"})
    app.state.report_client = TestClient(report_app, base_url="http://report")
    return app, report_app, data


@pytest.fixture
def rig(tmp_path):
    app, report_app, data = _rig(tmp_path)
    with TestClient(app) as client:
        yield Rig(client, app, report_app, data)


def _five(c: TestClient, who: dict) -> list:
    """Every housekeeping route once, as `who`."""
    return [c.get("/api/housekeeping/copies", headers=who),
            c.delete(f"/api/housekeeping/copies/backup/gsd-{_stamp(20)}.db", headers=who),
            c.post("/api/housekeeping/copies/cleanup", json={}, headers=who),
            c.delete("/api/housekeeping/reports/20260101T000000.000000Z-m0ld", headers=who),
            c.post("/api/housekeeping/reports/cleanup", json={}, headers=who)]


class TestT542_1_TheTier:
    """T542-1: the API refuses every route below the cluster-admin tier with the tier's own sentence, and refuses
    a request with no proxy-verified identity to record; nothing is deleted. Fails without the change: the
    routes do not exist (404 for each, not the refusal)."""

    @pytest.mark.parametrize("user", ["auditor", "alice"])
    def test_below_the_tier_every_route_refuses_with_the_tiers_sentence(self, rig, user):
        before = (rig.runs, rig.names("backup"))
        answers = _five(rig.client, H(user))
        assert [r.status_code for r in answers] == [403] * 5
        assert all(r.json()["detail"].startswith(SENTENCE) for r in answers)
        assert (rig.runs, rig.names("backup")) == before

    def test_no_identity_is_refused_with_the_reason(self, rig):
        answers = _five(rig.client, H(None))
        assert [r.status_code for r in answers] == [403] * 5
        assert all("needs an authenticated identity" in r.json()["detail"] for r in answers)

    def test_with_restrictions_off_nobody_can_delete(self, tmp_path):
        app, _, _ = _rig(tmp_path, view_restrictions_enabled=False)
        with TestClient(app) as c:
            assert [r.status_code for r in _five(c, H(ADMIN))] == [403] * 5

    def test_the_tier_lists_the_copies_with_the_guard_said(self, rig):
        body = rig.client.get("/api/housekeeping/copies", headers=H(ADMIN)).json()
        guarded = {c["kind"]: c["name"] for c in body["copies"] if c["guarded"]}
        assert guarded == {"backup": f"gsd-{_stamp(1)}.db",
                           "pre-upgrade": f"pre-upgrade-{_stamp(5)}-schema-20-to-21-pod-b.db",
                           "pre-restore": _stamp(3, micro=False)}
        assert [c["at"] for c in body["copies"]] == sorted((c["at"] for c in body["copies"]), reverse=True)
        assert body["directories"]["backup"] == str(rig.data / "backup")


class TestT542_2_ThePreviewBindsTheConfirm:
    """T542-2: a confirm deletes exactly the set its preview showed, or nothing: a set that changed in between is
    refused with 409 and the set as it is now. Fails without the change: the routes do not exist (404)."""

    def test_report_runs(self, rig):
        body = {"scope": f"schedule:{SCHEDULE}", "older_than_days": 0, "keep_newest": 0}
        preview = rig.client.post("/api/housekeeping/reports/cleanup", json=body, headers=H(ADMIN)).json()
        assert preview["preview"] is True and preview["count"] == 4 and preview["bytes"] == 1200
        assert rig.runs >= {i["id"] for i in preview["items"]}                      # a preview deletes nothing
        rig.report_app.state.store.create(_run("20260105T000000.000000Z-s005", days=0.5, schedule=SCHEDULE))
        stale = rig.client.post("/api/housekeeping/reports/cleanup", json={**body, "confirm": preview["digest"]},
                                headers=H(ADMIN))
        assert stale.status_code == 409
        assert stale.json()["detail"]["preview"]["count"] == 5
        assert "20260105T000000.000000Z-s005" in rig.runs and len(rig.runs) == 9   # nothing deleted
        fresh = stale.json()["detail"]["preview"]["digest"]
        done = rig.client.post("/api/housekeeping/reports/cleanup", json={**body, "confirm": fresh},
                               headers=H(ADMIN)).json()
        assert done["preview"] is False and done["count"] == 5
        assert not any(r.startswith("2026010") and r.endswith(("s001", "s002", "s003", "s004", "s005"))
                       for r in rig.runs)
        assert {"20260109T000001.000000Z-runn", "20260101T000000.000000Z-m0ld"} <= rig.runs

    def test_database_copies(self, rig):
        body = {"kinds": ["backup"], "older_than_days": 0}
        preview = rig.client.post("/api/housekeeping/copies/cleanup", json=body, headers=H(ADMIN)).json()
        assert {i["name"] for i in preview["items"]} == {f"gsd-{_stamp(20)}.db", f"gsd-{_stamp(10)}.db"}
        assert [k["name"] for k in preview["kept"]] == [f"gsd-{_stamp(1)}.db"]
        _file(rig.data / "backup" / f"gsd-{_stamp(0)}.db")      # a scheduled backup lands between the two
        stale = rig.client.post("/api/housekeeping/copies/cleanup", json={**body, "confirm": preview["digest"]},
                                headers=H(ADMIN))
        assert stale.status_code == 409 and stale.json()["detail"]["preview"]["count"] == 3
        assert len(rig.names("backup")) == 4                                       # nothing deleted
        done = rig.client.post("/api/housekeeping/copies/cleanup",
                               json={**body, "confirm": stale.json()["detail"]["preview"]["digest"]},
                               headers=H(ADMIN)).json()
        assert done["count"] == 3 and done["failed"] == []
        assert rig.names("backup") == {f"gsd-{_stamp(0)}.db"}

    def test_a_digest_of_another_set_never_deletes(self, rig):
        r = rig.client.post("/api/housekeeping/copies/cleanup", json={"confirm": "0" * 64}, headers=H(ADMIN))
        assert r.status_code == 409 and len(rig.names("backup")) == 3


class TestT542_3_TheGuard:
    """T542-3: the newest copy in each directory is never deleted from the page, so restore-db.sh --list keeps a
    backup to restore, the last upgrade keeps its way back and the last restore its undo. Fails without the
    change: the routes do not exist (404)."""

    @pytest.mark.parametrize("kind, name", [
        ("backup", lambda: f"gsd-{_stamp(1)}.db"),
        ("pre-upgrade", lambda: f"pre-upgrade-{_stamp(5)}-schema-20-to-21-pod-b.db"),
        ("pre-restore", lambda: _stamp(3, micro=False)),
    ])
    def test_the_newest_of_each_directory_is_refused(self, rig, kind, name):
        r = rig.client.delete(f"/api/housekeeping/copies/{kind}/{name()}", headers=H(ADMIN))
        assert r.status_code == 409 and r.json()["detail"] == housekeeping.GUARDS[kind]
        assert name() in rig.names(kind)

    def test_the_widest_cleanup_leaves_the_guarded_copies_and_what_is_not_a_copy(self, rig):
        body = {"kinds": list(housekeeping.COPY_KINDS), "older_than_days": 0}
        digest = rig.client.post("/api/housekeeping/copies/cleanup", json=body, headers=H(ADMIN)).json()["digest"]
        done = rig.client.post("/api/housekeeping/copies/cleanup", json={**body, "confirm": digest},
                               headers=H(ADMIN)).json()
        assert done["count"] == 5
        assert rig.names("backup") == {f"gsd-{_stamp(1)}.db"}
        assert sorted(p.name for p in (rig.data / "pre-upgrade").iterdir()) == sorted(
            [f"pre-upgrade-{_stamp(5)}-schema-20-to-21-pod-b.db", f"pre-upgrade-{_stamp(5)}-schema-20-to-21-pod-b.db.sha256"])
        # the moved-aside copy went with its sidecar; the guarded set and the unfinished keep stayed
        assert sorted(p.name for p in (rig.data / "pre-restore").iterdir()) == sorted(
            [_stamp(3, micro=False), f"{_stamp(1)}.tmp"])
        assert (rig.data / "gsd.db").is_file()

    def test_the_only_backup_is_kept(self, rig):
        for name in (f"gsd-{_stamp(20)}.db", f"gsd-{_stamp(10)}.db"):
            assert rig.client.delete(f"/api/housekeeping/copies/backup/{name}", headers=H(ADMIN)).status_code == 200
        only = f"gsd-{_stamp(1)}.db"
        assert rig.client.delete(f"/api/housekeeping/copies/backup/{only}", headers=H(ADMIN)).status_code == 409
        assert rig.names("backup") == {only}


class TestT542_4_InFlightRunsStay:
    """T542-4: a queued or running run is never deleted, by the per-run delete (409) or by any cleanup. Fails
    without the change: the routes do not exist (404)."""

    @pytest.mark.parametrize("rid, status", [("20260109T000000.000000Z-qued", "queued"),
                                             ("20260109T000001.000000Z-runn", "running")])
    def test_the_per_run_delete_refuses(self, rig, rid, status):
        r = rig.client.delete(f"/api/housekeeping/reports/{rid}", headers=H(ADMIN))
        assert r.status_code == 409 and f"is {status}" in r.json()["detail"]
        assert rid in rig.runs

    def test_the_widest_cleanup_leaves_them(self, rig):
        body = {"scope": "all", "older_than_days": 0, "keep_newest": 0}
        preview = rig.client.post("/api/housekeeping/reports/cleanup", json=body, headers=H(ADMIN)).json()
        assert preview["count"] == 6
        rig.client.post("/api/housekeeping/reports/cleanup", json={**body, "confirm": preview["digest"]},
                        headers=H(ADMIN))
        assert rig.runs == {"20260109T000000.000000Z-qued", "20260109T000001.000000Z-runn"}

    def test_keep_newest_and_the_age_apply_together(self, rig):
        body = {"scope": "all", "older_than_days": 3, "keep_newest": 1}
        ids = {i["id"] for i in rig.client.post("/api/housekeeping/reports/cleanup", json=body,
                                                 headers=H(ADMIN)).json()["items"]}
        # manual: m0ld (10 d) goes, mnew is the newest of its group; scheduled: s001 (4.5 d) and s002 (3.5 d) go,
        # s003 (2.5 d, not older than 3 days) and s004 (the newest) stay
        assert ids == {"20260101T000000.000000Z-m0ld", "20260101T000000.000000Z-s001",
                       "20260102T000000.000000Z-s002"}


class TestT542_5_NoPathFromTheRequest:
    """T542-5: a name is matched against the directory's own listing, never joined onto a path: a dot-dot, an
    encoded slash, the live database's name and a symlink named like a copy are all 404, and nothing outside
    the three directories changes. Fails without the change: the routes do not exist (404 too, so the test also
    asserts that a real copy IS deletable through the same route)."""

    def test_traversal_and_symlinks_are_not_copies(self, rig):
        live = rig.data / "gsd.db"
        assert live.is_file()
        (rig.data / "backup" / f"gsd-{_stamp(-1)}.db").symlink_to(live)          # named like the newest copy
        (rig.data / "pre-restore" / _stamp(-1)).symlink_to(rig.data, target_is_directory=True)
        before = sorted(p.name for p in rig.data.rglob("*"))
        for kind, name in (("backup", "%2E%2E"), ("backup", "..%2Fgsd.db"), ("backup", "gsd.db"),
                           ("pre-restore", "%2E%2E"), ("backup", f"gsd-{_stamp(-1)}.db"),
                           ("pre-restore", _stamp(-1)), ("..", "gsd.db"), ("data", "gsd.db")):
            r = rig.client.delete(f"/api/housekeeping/copies/{kind}/{name}", headers=H(ADMIN))
            assert r.status_code in (404, 405), (kind, name, r.status_code)
        assert sorted(p.name for p in rig.data.rglob("*")) == before and live.is_file()
        listed = rig.client.get("/api/housekeeping/copies", headers=H(ADMIN)).json()["copies"]
        assert not any(c["name"] == _stamp(-1) or c["name"] == f"gsd-{_stamp(-1)}.db" for c in listed)
        r = rig.client.delete(f"/api/housekeeping/copies/backup/gsd-{_stamp(20)}.db", headers=H(ADMIN))
        assert r.status_code == 200 and r.json()["deleted"]["name"] == f"gsd-{_stamp(20)}.db"


class TestT542_6_TheAuditLine:
    """T542-6: one `event-name key=value` line per deleted item, naming the viewer (who), the item (what); the
    log record's time is when. Fails without the change: no route, so no line."""

    def test_one_line_per_item(self, rig, caplog):
        caplog.set_level(logging.INFO, logger="gsd.api")
        rig.client.delete("/api/housekeeping/reports/20260101T000000.000000Z-m0ld", headers=H(ADMIN))
        rig.client.delete(f"/api/housekeeping/copies/backup/gsd-{_stamp(20)}.db", headers=H(ADMIN))
        body = {"kinds": ["pre-restore"], "older_than_days": 0}
        digest = rig.client.post("/api/housekeeping/copies/cleanup", json=body, headers=H(ADMIN)).json()["digest"]
        rig.client.post("/api/housekeeping/copies/cleanup", json={**body, "confirm": digest}, headers=H(ADMIN))
        lines = [r.getMessage() for r in caplog.records if r.name == "gsd.api"]
        assert ("report-run-deleted run=20260101T000000.000000Z-m0ld report=groups cluster=c1 bytes=300 "
                f"by={ADMIN}") in lines
        assert f"db-copy-deleted kind=backup copy=gsd-{_stamp(20)}.db directory={rig.data / 'backup'} bytes=20 by={ADMIN}" in lines
        assert sum(1 for line in lines if line.startswith("db-copy-deleted kind=pre-restore ")) == 2
        assert all(line.endswith(f"by={ADMIN}") for line in lines if "-deleted " in line)


class TestT542_7_TheMetricNamesNoOne:
    """T542-7: gsd_housekeeping_deleted_total counts by kind, pre-seeded to 0, and the public /metrics carries no
    viewer, run id or copy name. Fails without the change: the family does not exist."""

    def test_counted_by_kind_and_nothing_else(self, rig):
        assert 'gsd_housekeeping_deleted_total{kind="pre-upgrade"} 0.0' in rig.client.get("/metrics").text
        rig.client.delete("/api/housekeeping/reports/20260101T000000.000000Z-m0ld", headers=H(ADMIN))
        rig.client.delete(f"/api/housekeeping/copies/backup/gsd-{_stamp(20)}.db", headers=H(ADMIN))
        text = rig.client.get("/metrics").text
        assert 'gsd_housekeeping_deleted_total{kind="report-run"} 1.0' in text
        assert 'gsd_housekeeping_deleted_total{kind="backup"} 1.0' in text
        for secret in (ADMIN, "m0ld", _stamp(20)):
            assert secret not in text, secret


class TestT542_9_TheSwitchAndTheContract:
    """T542-9: `housekeeping_enabled` off (the code's default) registers no route on either service, so R6's
    GET-only default holds; on, the writes are exactly these four and the report service's two. Fails without
    the change: the setting does not exist."""

    WRITES = ["DELETE /api/housekeeping/copies/{kind}/{name}", "DELETE /api/housekeeping/reports/{run_id}",
              "POST /api/housekeeping/copies/cleanup", "POST /api/housekeeping/reports/cleanup"]

    @staticmethod
    def _writes(app) -> list[str]:
        return sorted(f"{m.upper()} {p}" for p, ops in app.openapi()["paths"].items() for m in ops
                      if m.lower() not in ("get", "head", "options") and p.startswith("/api/housekeeping"))

    def test_the_dashboard(self, tmp_path):
        on, _, _ = _rig(tmp_path)
        assert self._writes(on) == self.WRITES
        off = build_app(Settings(clusters=[], db_path=str(tmp_path / "off.db")), run_poller=False)
        assert self._writes(off) == [] and "/api/housekeeping/copies" not in off.openapi()["paths"]
        with TestClient(off) as c:
            assert c.get("/api/version").json()["features"]["housekeeping"] is False
            assert c.delete("/api/housekeeping/reports/x", headers=H(ADMIN)).status_code in (404, 405)

    def test_the_report_service(self, tmp_path):
        def non_get(app):
            return sorted((m, r.path) for r in app.routes if hasattr(r, "methods")
                          for m in r.methods - {"GET", "HEAD", "OPTIONS"})
        base = dict(snapshot_dir=str(tmp_path), artifact_dir=str(tmp_path / "a"), pdf_enabled=False)
        off = build_report_app(ReportSettings(**base), secret=SECRET)
        on = build_report_app(ReportSettings(**base, housekeeping_enabled=True), secret=SECRET)
        assert non_get(off) == [("POST", f"{REPORT_PREFIX}/api/preview"), ("POST", f"{REPORT_PREFIX}/api/runs")]
        assert non_get(on) == sorted(non_get(off) + [("DELETE", f"{REPORT_PREFIX}/api/runs/{{run_id}}"),
                                                     ("POST", f"{REPORT_PREFIX}/api/runs/cleanup")])

    def test_a_viewers_ticket_cannot_delete_on_the_report_service(self, rig):
        from gsd.reporting import TICKET_HEADER
        from gsd.reporting.ticket import mint
        direct = TestClient(rig.report_app)
        ticket = {TICKET_HEADER: mint(SECRET, ADMIN, "all", 300), "X-Forwarded-User": ADMIN}
        r = direct.delete(f"{REPORT_PREFIX}/api/runs/20260101T000000.000000Z-m0ld", headers=ticket)
        assert r.status_code == 403 and "20260101T000000.000000Z-m0ld" in rig.runs


class TestT542_10_TheCustomHeader:
    """T542-10: every write needs the X-GSD-Interaction header the page sends (OWASP's custom-request-header
    defence), and a body a cross-site form can send is not read as JSON. Fails without the change: 404."""

    def test_a_write_without_the_header_is_refused(self, rig):
        answers = _five(rig.client, H(ADMIN, page=False))
        assert answers[0].status_code == 200                                   # the GET listing needs no header
        assert [r.status_code for r in answers[1:]] == [403] * 4
        assert all("X-GSD-Interaction" in r.json()["detail"] for r in answers[1:])

    def test_a_form_body_is_not_json(self, rig):
        r = rig.client.post("/api/housekeeping/copies/cleanup", content=b'{"older_than_days": 0}',
                            headers={**H(ADMIN), "Content-Type": "text/plain"})
        assert r.status_code == 422


class TestT542_11_TheReportServicesAnswers:
    """T542-11: with reporting off the report routes say so (404); an unreachable report service is a 502 that
    names it. Fails without the change: 404 for every case, with no such sentence."""

    def test_reporting_off(self, tmp_path):
        app, _, _ = _rig(tmp_path, reporting_url="")
        with TestClient(app) as c:
            r = c.delete("/api/housekeeping/reports/20260101T000000.000000Z-m0ld", headers=H(ADMIN))
            assert r.status_code == 404 and r.json()["detail"] == "reporting is not enabled on this deployment"

    def test_unreachable(self, tmp_path):
        import httpx
        app, _, _ = _rig(tmp_path)

        def refuse(request):
            raise httpx.ConnectError("connection refused", request=request)

        app.state.report_client = httpx.Client(base_url="http://report", transport=httpx.MockTransport(refuse))
        with TestClient(app) as c:
            r = c.post("/api/housekeeping/reports/cleanup", json={}, headers=H(ADMIN))
            assert r.status_code == 502 and r.json()["detail"] == "the report service could not be reached: ConnectError"


class TestT542_13_TheChart:
    """T542-13: `housekeeping.enabled` reaches both pods — the dashboard's ConfigMap key and the report pod's
    environment — on by default and off when set; it adds no RBAC (§4.3 diffs every rendered rule). Fails without
    the change: neither the key nor the variable is rendered."""

    @pytest.mark.parametrize("sets, word", [((), "true"), (("housekeeping.enabled=false",), "false")])
    def test_both_pods_read_the_value(self, sets, word):
        from test_chart_pdb import _render
        docs = _render(*sets)
        config = next(d for d in docs if d.get("kind") == "ConfigMap" and "clusters.yaml" in (d.get("data") or {}))
        assert f"housekeepingEnabled: {word}" in config["data"]["clusters.yaml"]
        report = next(d for d in docs if d.get("kind") == "Deployment" and d["metadata"]["name"].endswith("-report"))
        env = {e["name"]: e.get("value") for e in report["spec"]["template"]["spec"]["containers"][0]["env"]}
        assert env["GSD_REPORT_HOUSEKEEPING_ENABLED"] == word
```

### Block 34 — local-development/tests/test_ui.py: T542-8 and T542-12, in the browser

No control below the tier; a cluster administrator deletes, previews and confirms; both cards at 375 px (§4).

<!-- block: local-development/tests/test_ui.py | edit -->

Old text:

```python
        assert overflow <= 0, f"the page scrolls {overflow}px sideways at 375px"
```

New text:

```python
        assert overflow <= 0, f"the page scrolls {overflow}px sideways at 375px"


@pytest.fixture(scope="module")
def housekeeping_server(tmp_path_factory):
    """#542 (SPEC_H1): the reporting rig with `housekeeping.enabled`, a data volume holding copies, and the
    dashboard's server-to-server calls reaching the same report app through the `app.state.report_client` seam.
    `root` passes the cluster-admin tier; `auditor` passes the wide tier only — the negative control."""
    from datetime import UTC as _UTC, datetime as _dt
    from fastapi.testclient import TestClient
    from gsd.reporting.artifacts import Run
    from gsd.reporting.config import REPORT_NAMES, ReportSettings
    from gsd.reporting.server import build_report_app
    from gsd.store import Store as _Store

    root = tmp_path_factory.mktemp("gsd-housekeeping")
    db = str(root / "ui.db")
    _seed(db)
    snapshots, artifacts, token = root / "snapshots", root / "artifacts", root / "token"
    snapshots.mkdir(); artifacts.mkdir(); token.write_bytes(REPORT_SECRET)
    writer = _Store(db)
    assert writer.snapshot(str(snapshots), keep=2)
    writer.close()
    now = _dt.now(_UTC)
    for days in (9, 5, 1):
        (root / "backup").mkdir(exist_ok=True)
        (root / "backup" / f"gsd-{(now - timedelta(days=days)).strftime('%Y%m%dT%H%M%S.%fZ')}.db").write_bytes(b"SQLite format 3\x00")
    for days in (8, 2):
        kept = root / "pre-restore" / (now - timedelta(days=days)).strftime("%Y%m%dT%H%M%S.%fZ")
        kept.mkdir(parents=True)
        (kept / "gsd.db").write_bytes(b"SQLite format 3\x00")
    report_app = build_report_app(ReportSettings(snapshot_dir=str(snapshots), artifact_dir=str(artifacts), pdf_enabled=False,
                                                 enabled_reports=tuple(n for n in REPORT_NAMES if n != "login-activity"),
                                                 housekeeping_enabled=True), secret=REPORT_SECRET)
    store = report_app.state.store

    def run(rid, days, schedule=None, status="done", report="groups"):
        at = (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        store.create(Run(id=rid, report=report, cluster="crc-local", params={}, formats=["html"],
                         generated_by=f"schedule:{schedule}" if schedule else "jane.smith", generated_by_note="n",
                         schedule=schedule, requested_at=at, started_at=at, finished_at=at if status == "done" else None,
                         status=status, bytes={"html": 1000, "json": 500} if status == "done" else {}))
        if status == "done":
            store.write(rid, "html", b"<p>run</p>")

    run("20260901T000000.000000Z-man1", 20)
    for i in range(3):     # a retired schedule's runs: no section shows them, the cleanup's scope still names them
        run(f"2026090{i + 2}T000000.000000Z-nna{i}", 10 - i, schedule="nightly-namespace-access", report="namespace-access")
    run("20260909T000000.000000Z-runn", 0, status="running")
    settings = Settings(
        clusters=[ClusterConfig("crc-local", "https://api.crc.testing:6443", token_env="X"),
                  ClusterConfig("prod-east", "https://api.prod-east.example.com:6443", token_env="X", identity="none")],
        db_path=db, backup_dir=str(root / "backup"), login_capture_enabled=True, oauth_proxy_enabled=True,
        reporting_url="http://report", reporting_token_file=str(token), reporting_ticket_ttl_seconds=120,
        housekeeping_enabled=True,
    )
    dash_app = build_app(settings, run_poller=False)
    dash_app.state.tier_resolver = _TierByName("root", "auditor")
    dash_app.state.cluster_admin_resolver = _TierByName("root")
    dash_app.state.report_client = TestClient(report_app, base_url="http://report")

    async def router(scope, receive, send):
        if scope["type"] == "lifespan":
            return
        target = report_app if scope.get("path", "").startswith("/report") else dash_app
        await target(scope, receive, send)

    port = _free_port()
    srv = uvicorn.Server(uvicorn.Config(router, host="127.0.0.1", port=port, log_level="warning", lifespan="off"))
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
        raise RuntimeError("housekeeping dashboard server did not start")
    yield base, report_app, root
    srv.should_exit = True
    thread.join(timeout=5)


class TestHousekeepingPage:
    """#542 (SPEC_H1): the page's deletes. T542-8: a reader below the cluster-admin tier is shown no control; T542-12:
    a cluster administrator deletes a run from the drawer, cleans up a retired schedule's runs through the preview,
    and deletes a copy from the KPI page, the newest backup's row saying why it stays."""

    def test_t542_8_below_the_tier_there_is_no_control(self, browser, housekeeping_server):
        base, _, _ = housekeeping_server
        ctx, page, errors = _reports_page(browser, base, "auditor")
        try:
            page.goto(base + "#page=library&cluster=crc-local&run=20260901T000000.000000Z-man1")
            page.wait_for_selector("#library-drawer #drawer-copy-link")
            assert page.evaluate("() => data.version.features.housekeeping") is True     # the deployment's switch is on
            assert page.locator("#drawer-delete").count() == 0
            assert page.locator("#lib-cleanup").count() == 0
            assert page.locator("#tab-kpi").count() == 0                                 # and so no copies card
            assert page.evaluate("async () => (await fetch('/api/housekeeping/copies')).status") == 403
            assert not errors, errors
        finally:
            ctx.close()

    def test_t542_12_a_cluster_administrator_deletes_previews_and_confirms(self, browser, housekeeping_server):
        base, report_app, root = housekeeping_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.goto(base + "#page=library&cluster=crc-local&run=20260901T000000.000000Z-man1")
            page.wait_for_selector("#drawer-delete")
            page.click("#drawer-delete")
            page.wait_for_function("() => document.getElementById('drawer-delete').textContent === 'Confirm delete'")
            assert "cannot be undone" in page.locator("#drawer-delete-msg").inner_text()
            page.click("#drawer-delete")
            page.wait_for_function("() => !document.getElementById('library-drawer')")
            assert report_app.state.store.get("20260901T000000.000000Z-man1") is None
            page.wait_for_selector("#hk-runs-note")
            assert page.locator("#hk-runs-note").inner_text() == "Run 20260901T000000.000000Z-man1 deleted."

            page.select_option("#hk-runs-scope", "schedule:nightly-namespace-access")
            page.fill("#hk-runs-days", "0"); page.dispatch_event("#hk-runs-days", "change")
            page.fill("#hk-runs-keep", "0"); page.dispatch_event("#hk-runs-keep", "change")
            page.click("#hk-runs-preview")
            page.wait_for_selector("#hk-runs-preview .hk-list")
            assert page.locator("#hk-runs-preview .hk-list li").count() == 3
            assert report_app.state.store.get("20260902T000000.000000Z-nna0") is not None   # a preview deletes nothing
            page.click("#hk-runs-confirm")
            page.wait_for_function("() => (document.getElementById('hk-runs-note') || {}).textContent?.startsWith('Deleted 3 runs')")
            assert all(report_app.state.store.get(f"2026090{i + 2}T000000.000000Z-nna{i}") is None for i in range(3))
            assert report_app.state.store.get("20260909T000000.000000Z-runn") is not None   # running: never deleted

            page.goto(base + "#page=kpi")
            page.wait_for_selector("#hk-copies table")
            rows = page.locator("#hk-copies tbody tr")
            assert rows.count() == 5
            newest = sorted(p.name for p in (root / "backup").iterdir())[-1]
            assert "kept: the newest scheduled backup" in page.locator(f"tr[data-hk-row='backup/{newest}']").inner_text()
            assert page.locator(f"tr[data-hk-row='backup/{newest}'] button").count() == 0
            oldest = sorted(p.name for p in (root / "backup").iterdir())[0]
            button = page.locator(f"[data-hk-copy='backup/{oldest}']")
            button.click()
            page.wait_for_function(f"() => document.querySelector(\"[data-hk-copy='backup/{oldest}']\").textContent === 'Confirm delete'")
            page.locator(f"[data-hk-copy='backup/{oldest}']").click()
            page.wait_for_function(f"() => !document.querySelector(\"tr[data-hk-row='backup/{oldest}']\")")
            assert not (root / "backup" / oldest).exists() and (root / "backup" / newest).exists()
            assert not errors, errors
        finally:
            ctx.close()

    def test_the_cards_fit_a_phone(self, browser, housekeeping_server):
        base, _, _ = housekeeping_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.set_viewport_size({"width": 375, "height": 800})
            # Each card's own elements, outside its table's scroll box, stay inside the viewport. The page as a whole is
            # not measured on the KPI page: the Backups card's heading carries config.backup.dir, and this rig's
            # temporary path is long enough to push it past 375 px with or without these cards (SPEC_H1 §4.4).
            for where, card in (("#page=library&cluster=crc-local", "#lib-cleanup"), ("#page=kpi", "#hk-copies")):
                page.goto(base + where)
                page.wait_for_selector(card + (" table" if card == "#hk-copies" else ""))
                outside = page.evaluate("""(card) => { const vw = document.documentElement.clientWidth;
                  return [...document.querySelectorAll(card + ' *')].filter((e) => !e.closest('.scroll-x')
                    && e.getBoundingClientRect().right > vw + 1).map((e) => e.tagName + '.' + e.className); }""", card)
                assert outside == [], f"{where}: {outside} reach past 375px"
            assert not errors, errors
        finally:
            ctx.close()
```

### Block 35 — local-development/tests/test_report_ticket_api.py: the deployment's features name the new module

This test pins `features` whole; with the code's default it reads `housekeeping: false` (measured: the only test the change failed).

<!-- block: local-development/tests/test_report_ticket_api.py | edit -->

Old text:

```python
        assert c.get("/api/version").json()["features"] == {"export": True, "reporting": True, "reporting_prefix": "/report"}
```

New text:

```python
        assert c.get("/api/version").json()["features"] == {"export": True, "reporting": True, "reporting_prefix": "/report",
                                                             "housekeeping": False}   # #542: off in the code, on in the chart
```

### Block 36 — local-development/API.md: the five routes

Every route is in `API.md` (`tests/test_api_contract.py#test_every_endpoint_appears_in_api_md` holds the default schema; these exist only with the switch).

<!-- block: local-development/API.md | edit -->

Old text:

```text

## The report service's API
```

New text:

```text

### Deleting report runs and database copies (#542, `housekeeping.enabled`)

Five routes, registered only when the chart's `housekeeping.enabled` is on (its default; off, they do not
exist and `features.housekeeping` on `/api/version` is `false`). Each needs a proxy-verified identity and the
**cluster-admin tier** (#322): below it, `403` with the tier's sentence, `For cluster administrators only. …`;
with no identity to record, or with `visibility.enabled` false, `403` for everyone. The four writes also need the
`X-GSD-Interaction` header the page sends (`403` without it), and a `POST` body must be `application/json`.
A one-off cleanup: nothing is saved, and `reporting.retention` and `config.backup` stay the standing policy.
Every deleted item is one log line, `report-run-deleted run=… report=… cluster=… schedule=… bytes=… by=<viewer>`
or `db-copy-deleted kind=… copy=… directory=… bytes=… by=<viewer>`, and one count in
`gsd_housekeeping_deleted_total{kind}` (`report-run`, `backup`, `pre-upgrade`, `pre-restore`; no names).

| Method and path | What |
|---|---|
| `GET /api/housekeeping/copies` | the copies on the answering pod's data volume, newest first: `{"pod", "directories": {"backup", "pre-upgrade", "pre-restore"}, "copies": [{"kind", "name", "directory", "type", "bytes", "at", "guarded"}]}`. The directories are `config.backup.dir` (`null` when backups are off) and `pre-upgrade/` and `pre-restore/` beside the database. A copy is a `gsd-*.db` backup, a `pre-upgrade-*.db` copy, or in `pre-restore/` a restore's kept set (a `<stamp>/` directory) or a copy moved aside there (`*.db`); a `.sha256` goes with its copy, and a `.tmp` (a writer's unfinished file), a hidden entry and a symlink are never listed. `guarded` is the reason the newest copy of each directory is kept, else `null` |
| `DELETE /api/housekeeping/copies/{kind}/{name}` | delete one listed copy (a file with its `.sha256`, or a kept set whole): `200` `{"deleted": {…}}`; `409` with the reason for the guarded one; `404` for a name that is not listed, so `..`, a slash or a symlink never reaches a file |
| `POST /api/housekeeping/copies/cleanup` | `{"kinds": ["backup", "pre-upgrade", "pre-restore"], "older_than_days": 0, "confirm": null}`: without `confirm`, the preview `{"preview": true, "items", "count", "bytes", "digest", "kept"}` (`kept`: the guarded copies in scope); with `confirm` set to that digest, the same set is computed again and deleted, `{"preview": false, …, "failed": []}`, or `409` `{"detail": {"message", "preview"}}` with the set as it is now and nothing deleted |
| `DELETE /api/housekeeping/reports/{run_id}` | delete one finished report run and its files through the report service: `200` `{"deleted": {…}}`; `409` for a queued or running run; `404` for none; `502` when the report service cannot be reached; `404` when reporting is off |
| `POST /api/housekeeping/reports/cleanup` | `{"scope": "all" \| "manual" \| "schedule:<name>", "older_than_days": 0, "keep_newest": 0, "confirm": null}`: finished runs completed more than `older_than_days` ago and beyond the newest `keep_newest` of their (schedule, cluster), manual runs being one group per cluster; the preview and the confirm as for copies, computed by the report service under the lock its retention prunes under. A schedule no longer configured can still be named, so a retired schedule's runs can be cleaned up |

The `digest` is the sha256 of the set's ids sorted, one per line (`<kind>/<name>` for a copy, the run id for a
run): a confirm deletes exactly the previewed set or nothing.

## The report service's API
```

### Block 37 — local-development/API.md: the report service's two

Its table names every route and who may call it.

<!-- block: local-development/API.md | edit -->

Old text:

```text
| `GET /report/api/usage?since_id=&limit=` | **token only** | finished runs for the dashboard's pull; viewers read them from the dashboard at the usage tier |
```

New text:

```text
| `GET /report/api/usage?since_id=&limit=` | **token only** | finished runs for the dashboard's pull; viewers read them from the dashboard at the usage tier |
| `DELETE /report/api/runs/{id}`, `POST /report/api/runs/cleanup` | **token only**, with `housekeeping.enabled` | the dashboard's deletes (#542, above): one finished run, or a cleanup's preview and confirm. A viewer's ticket is refused (`403`): the cluster-admin tier is decided by the dashboard, which holds the cluster credential this service does not |
```

### Block 38 — docs/ACCESS_CONTROL.md: §4's row

Every route names the tier each reader gets (SPEC_G1's rule).

<!-- block: docs/ACCESS_CONTROL.md | edit -->

Old text:

```text
| `/api/clusterconfigs` and its four write routes | **403** | **403** unless the reader passes the cluster-admin tier (#322); the writes also need `clusterConfig.secrets.writes.enabled` |
```

New text:

```text
| `/api/clusterconfigs` and its four write routes | **403** | **403** unless the reader passes the cluster-admin tier (#322); the writes also need `clusterConfig.secrets.writes.enabled` |
| `/api/housekeeping/**`: the copies listing and the four delete routes (#542) | **403** | **403** unless the reader passes the cluster-admin tier (#322) with a proxy-verified identity; exist only with `housekeeping.enabled` |
```

### Block 39 — docs/RUNBOOK_backup_restore.md: §4: the page deletes copies, and never the newest

Where the runbook names `pre-restore/` and the undo; recovery mode is unchanged (§3.12).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
fold can lack every row its `-wal` held.
```

New text:

```text
fold can lack every row its `-wal` held.

**Deleting copies from the page (#542).** Nothing rotates `pre-restore/`: every restore adds a set. A cluster
administrator removes the ones no longer needed from the KPI page's **Database copies** card (one at a time, or a
cleanup previewed and confirmed), which also lists the scheduled backups and the pre-upgrade copies. The newest copy
of each directory is never deleted there: the newest backup (this section always has a copy to restore), the newest
pre-upgrade copy (§6) and the newest pre-restore set (the undo of the last restore). The page runs only while the
app serves, so it plays no part in recovery mode and changes nothing in the steps above.
```

### Block 40 — docs/RUNBOOK_backup_restore.md: §6: an older pre-upgrade copy may be deleted from the page

Where the runbook says what keeps the copies.

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
  much space as the database and counts against `persistence.size`.
```

New text:

```text
  much space as the database and counts against `persistence.size`. A cluster administrator may delete an older
  one from the KPI page's **Database copies** card (#542); the newest is always kept there.
```

### Block 41 — docs/CHANGELOG.md: the CHANGELOG entry

Under a new `## Unreleased`: 3.0.0 was cut on this main, so none exists.

<!-- block: docs/CHANGELOG.md | edit -->

Old text:

```text
which `local-development/prepare-release.py` does when the release is cut.
```

New text:

```text
which `local-development/prepare-release.py` does when the release is cut.

## Unreleased

- **Delete report runs and database copies from the page (#542, `docs/specs/SPEC_H1_gui_cleanup.md`;
  `housekeeping.enabled`, on by default).** A cluster administrator (the cluster-admin tier, #322, behind a
  proxy-verified identity) deletes a finished report run from the Library tab's run drawer and a database copy from
  the KPI page's new **Database copies** card, or cleans either up once with a tighter bound picked on the page:
  report runs older than N days beyond the newest K of each schedule and cluster (all runs, the manual runs, or one
  schedule, a retired one included), copies older than N days in one directory or all three. A cleanup is a preview
  of exactly what goes, then a confirm bound to that set by its digest: a set that changed in between is refused
  (409) with the new preview, and nothing is deleted. **Nothing is saved**: `reporting.retention` and
  `config.backup` stay the standing policy. The copies are those in `config.backup.dir` and in `pre-upgrade/` and
  `pre-restore/` beside the database, and the newest of each directory is always kept, so a restore keeps a copy
  and a way back; a queued or running run is never deleted; `/data/report`, the live database and anything else on
  the volume are never listed. Every deleted item is one audit line naming the person (`report-run-deleted …` /
  `db-copy-deleted … by=<viewer>`) and one count in the new `gsd_housekeeping_deleted_total{kind}`, which names no
  one. The report service gains `DELETE /report/api/runs/{id}` and `POST /report/api/runs/cleanup` for the service
  token only, registered with the same value. No RBAC change: every rendered rule and binding, before and after,
  63 lines, none removed and none added. `housekeeping.enabled: false` in the release's values file removes every
  route and control.
```

### Block 42 — docs/specs/SPEC_D6_scrub_span.md: the live count of `event` call sites

`tests/test_scrub_span_spec.py#test_emit_callsite_measurement` holds SPEC_D6's notes to the count the code has; the two audit lines make it 48 in 7 modules (measured: 46 in 6 on `2d20d0fb`), recorded as #244's implementation recorded its own (`e0b10db2`).

<!-- block: docs/specs/SPEC_D6_scrub_span.md | edit -->

Old text:

```text
- **#244's implementation (SPEC_D5) adds one call site** in `gsd/poller.py`, the CA warning's `event` in the
  discovery cycle: with it applied, `event` and `failure` have 46 call sites in 6 consuming modules. The counts in
  the notes below are as each change left them; the live count is this one, and
  `tests/test_scrub_span_spec.py#test_emit_callsite_measurement` holds it.
```

New text:

```text
- **#542's implementation (SPEC_H1) adds two call sites** in `gsd/api.py`, the audit lines of the page's deletes
  (`report-run-deleted`, `db-copy-deleted`): with it applied, `event` and `failure` have
  48 call sites in 7 consuming modules. The counts in the notes below are as each change left them; the live count is this one, and
  `tests/test_scrub_span_spec.py#test_emit_callsite_measurement` holds it.

- **#244's implementation (SPEC_D5) adds one call site** in `gsd/poller.py`, the CA warning's `event` in the
  discovery cycle: with it applied, `event` and `failure` have 46 call sites in 6 consuming modules.
```

### Block 43 — charts/group-sync-dashboard/values.yaml: `housekeeping.enabled: true`, with its reason

On by default under the chart's defaults rule: no RBAC, credential or second image (§3.8).

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```yaml
        stagingSizeLimit: 2Gi
```

New text:

```yaml
        stagingSizeLimit: 2Gi

# ---------------------------------------------------------------------------
# Deleting reports and database copies from the page (#542, docs/specs/SPEC_H1_gui_cleanup.md)
# ---------------------------------------------------------------------------
# A cluster administrator (visibility.clusterAdminSar, #322) deletes a report run from the Library
# tab's run drawer, a database copy from the KPI page, or cleans either up once with a tighter bound
# picked on the page: a preview of exactly what goes, then a confirm. NOTHING IS SAVED: the standing
# policy is still reporting.retention and config.backup in this values file. Every deletion is one
# audit log line naming the person, and gsd_housekeeping_deleted_total counts them by kind, no names.
#
# What can go: report runs that finished (never one queued or running), and the copies in three
# directories on the data volume — config.backup.dir, and pre-upgrade/ and pre-restore/ beside the
# database. The newest copy in each of the three is always kept (the newest backup, the newest
# pre-upgrade copy, the newest pre-restore set), so a restore always has a copy and a way back.
# Never the report service's snapshot (/data/report), the live database or anything else.
#
# DEFAULT ON (the chart's defaults rule): no RBAC, no credential, no second image — the deletion is
# file work in the pods' own volumes, the report run deleted by the report service at the
# dashboard's request with the token both pods already mount. It needs a proxy-verified identity, so
# with oauthProxy.enabled or visibility.enabled false every deletion is refused. Set
# `housekeeping.enabled: false` in this release's values file and roll it out through the release's
# deployment pipeline where only the standing retention may remove evidence: the page then shows no
# control and neither pod registers a delete route.
housekeeping:
  enabled: true
```

### Block 44 — charts/group-sync-dashboard/templates/configmap.yaml: the dashboard reads the value

`housekeepingEnabled` beside `clusterSecretsWritesEnabled`.

<!-- block: charts/group-sync-dashboard/templates/configmap.yaml | edit -->

Old text:

```yaml
    clusterSecretsWritesEnabled: {{ .Values.clusterConfig.secrets.writes.enabled }}
```

New text:

```yaml
    clusterSecretsWritesEnabled: {{ .Values.clusterConfig.secrets.writes.enabled }}
    # The page's deletes of report runs and database copies (#542, SPEC_H1), for the cluster-admin tier.
    housekeepingEnabled: {{ .Values.housekeeping.enabled }}
```

### Block 45 — charts/group-sync-dashboard/templates/report-deployment.yaml: the report pod reads the value

`GSD_REPORT_HOUSEKEEPING_ENABLED`, so off means neither pod registers a delete route.

<!-- block: charts/group-sync-dashboard/templates/report-deployment.yaml | edit -->

Old text:

```yaml
              value: {{ .Values.config.bindingIntervalSeconds | quote }}
```

New text:

```yaml
              value: {{ .Values.config.bindingIntervalSeconds | quote }}
            # The two delete routes the dashboard calls with the service token (#542, SPEC_H1); off, neither exists.
            - name: GSD_REPORT_HOUSEKEEPING_ENABLED
              value: {{ .Values.housekeeping.enabled | quote }}
```

### Block 46 — charts/group-sync-dashboard/README.md: the chart README's row

Every value has its row; this one after Backups, which it acts on.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
them ([runbook §6](../../docs/RUNBOOK_backup_restore.md#6-pre-upgrade-copies)).
```

New text:

```text
them ([runbook §6](../../docs/RUNBOOK_backup_restore.md#6-pre-upgrade-copies)).

### Deleting reports and database copies — `housekeeping`

| Key | Default | Notes |
|---|---|---|
| `housekeeping.enabled` | `true` | a cluster administrator (`visibility.clusterAdminSar`, #322) deletes a finished report run from the Library tab's run drawer or a database copy from the KPI page's **Database copies** card, or cleans either up once with a tighter bound picked on the page (report runs: older than N days, keep the newest K of each schedule and cluster, one schedule or the manual runs or all; copies: older than N days, one directory or all three): a preview of exactly what goes, then a confirm that deletes that set or, if it changed, nothing (`docs/specs/SPEC_H1_gui_cleanup.md`). **Nothing is saved**: `reporting.retention` and `config.backup` stay the standing policy. The copies are those in `config.backup.dir` and in `pre-upgrade/` and `pre-restore/` beside the database; the newest of each directory is always kept, so a restore keeps a copy and a way back. A queued or running run is never deleted; `/data/report`, the live database and anything else on the volume are never listed. One audit line per item (`report-run-deleted …` / `db-copy-deleted … by=<person>`) and `gsd_housekeeping_deleted_total{kind}`, no names. **On by default**: no RBAC, credential or second image (the deletion is file work in the pods' own volumes; the run is deleted by the report service at the dashboard's request with the token both pods mount); it needs a proxy-verified identity, so with `oauthProxy.enabled` or `visibility.enabled` false every deletion is refused. Off, the page shows no control and neither pod registers a delete route |
```
