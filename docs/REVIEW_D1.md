# Review — PR #89, D1: login capture from the oauth-server audit log

Adversarial second-opinion pass, 2026-09-06, on the ten-claim brief for #89
(`docs/specs/SPEC_D1_audit_log_login_capture.md` applied as amended by its grounding note; application
0.17.0, chart 0.19.0; the deviations are in the spec's orchestrator's notes). Cursor (Grok 4.6 high fast,
ask mode) and Codex (gpt-5.6-sol, xhigh) reviewed the same head; every verdict was re-checked here
before a decision, and every accepted finding came with a test that failed before its change.

## Live run on the reference cluster

_(filled from the CRC deploy of this head with `loginCapture.source: audit-log`)_

## Verdicts — Cursor

Read-only (ask mode blocked execution; every proposed test was run here). Head reviewed: d2f2e5b50e.

| Claim | Cursor | Decision |
|---|---|---|
| C1 parser shapes | REFUTED — `GET /oauth/authorize` with no `client_id` (or `client_id=`) became a `session` row, a fourth shape | **Accepted** — `parse_audit_line` returns None without a client. Measured first: all 259 username-annotated authorize records on the reference cluster name a client, so nothing real is lost |
| C2 row and labels | CONFIRMED | — |
| C3 fingerprint identity | CONFIRMED ((a)–(e) each traced) | — |
| C4 whole lines and budget | CONFIRMED | — |
| C5 retention skip | CONFIRMED (boundary `closed == cutoff` is read, not skipped) | — |
| C6 correspondence | REFUTED — a credential retry 1 s after a pod-log row of the same class was linked to it instead of inserted | **Accepted in part** — `CORRESPONDENCE_SECONDS` is 0.25 (fifteen times the measured 16 ms pairing) and Cursor's test is taken. The "swallowed retry" framing is rejected on the data: the swallow needs the first attempt's own audit twin to be absent (events are processed in file order, and the twin links first), and the closest same-user credential retry in the cluster's 49,360-record log is 3.6 s apart (133 pairs, none under 2 s). Its second point — two audit rows with an identical microsecond stamp collide on the table's UNIQUE key — is **rejected**: zero same-user same-stamp pairs in the log, and the stamps are microseconds |
| C7 identity classification | CONFIRMED | — |
| C8 chart | REFUTED — `join ","` on `providers` and `ignoreIdentityPatterns` split a DN fragment (`ou=TrustedApplications,dc=example,dc=com`) into three patterns, and `dc=com` then dropped every person in the directory | **Accepted** — the three lists travel as `toJson` (as `usersProviders` already does) and `config.py#_string_list_setting` never splits a list; Cursor's chart tests taken, a settings-level test added |
| C9 API and metrics | CONFIRMED | — |
| C10 migration 10 | REFUTED — `SCHEMA` created `login_event_by_audit_id` before migration 10 could add the column; a real 0.16 database could not be opened | **Accepted** — and independently proven on the reference cluster, whose pod crashed with `no such column: audit_id` on the first deploy of this head. The index lives in migration 10 only; Cursor's `PRAGMA table_info` test (built from 0.16.0's own table definitions) is taken |

Beyond the brief, Cursor raised six points. Accepted: `read_ok` was set by a successful fingerprint
probe, so a cycle whose every body read failed still advanced the last-read stamp the stalled alert
watches (test added); the unmatched counter's label was named `decision` while carrying the
`outcome` vocabulary (renamed `outcome` everywhere); a rotated file whose last line lacks a
trailing newline was never marked complete and re-read forever (the tail is now taken as the final
line, since a closed file never gains the newline); `gsd.loginCaptureSource` refused `audit-log` +
`authLogLevel.enabled=true` even with `loginCapture.enabled=false`, when no RBAC renders and no log
is read (guarded). Rejected: that an unreadable OAuth CR (`_configured_providers` → empty set)
silently widens `identity_match` to any provider — the chart grants `get oauths` in
`templates/rbac.yaml`, so the path is reached only on an install that removed it; it now logs at
WARNING each cycle, and `loginCapture.auditLog.providers` pins the list; and the UNIQUE-key
collision above.

## Verdicts — Codex

Codex (gpt-5.6-sol, xhigh) reviewed the same head, d2f2e5b50e, with a read-only sandbox that could
run the temp-directory-free tests (19 passed) and `helm template`, but not `test_migrations.py`.
Five of its findings are the ones Cursor made (C1's client-less authorize, C3's `read_ok` on a probe,
C6's same-stamp collision, C8's comma join, C9's label vocabulary) and were already applied when its
report arrived; the decisions above stand, with one difference noted under C9.

| Claim | Codex | Decision |
|---|---|---|
| C1 | REFUTED — also `POST /login/<idp>/extra` was accepted as a credential login for `<idp>` | **Accepted** — the path is exactly `/login` or `/login/<one segment>`. Measured first: the 147 credential records on the reference cluster are all depth one or two |
| C2 | CONFIRMED | — |
| C3 | REFUTED (the probe-sets-`read_ok` finding, as Cursor) | **Accepted** — and Codex's second half too: the re-read after a fingerprint mismatch now sets `read_ok` when it succeeds, so a cycle that legitimately read a rotated-away file is not reported as a dead cycle |
| C4 | CONFIRMED | — |
| C5 | CONFIRMED (Lumberjack's backup stamps are UTC; Kubernetes does not enable local time) | — |
| C6 | REFUTED — two audit IDs for one person, node, microsecond and outcome collapse on the table's UNIQUE key; proposed rebuilding `login_event` in migration 10 with a partial pod-log-only index | **Rejected as a rebuild, accepted as a visible event** — zero same-user same-stamp pairs in the cluster's 49,360 records, and rebuilding the table that holds every install's login history for a collision never observed is more upgrade risk than the defect. The ignored row is logged at WARNING with its auditID (no username), with a test |
| C7 | REFUTED — (a) an OAuth CR that was read and lists no provider was treated like an unreadable one ("match anything"); (b) a bare HTPasswd username that happens to be valid base64url of a DN fragment was decoded and dropped by the ignore pattern | **Accepted, both** — `_configured_providers` returns None for unreadable and a set otherwise, and an empty set matches nothing; identities of `loginCapture.htpasswdProviders` are compared as written and never decoded. Tests for both |
| C8 | REFUTED (as Cursor) | **Accepted** — Codex's end-to-end test (the rendered ConfigMap loaded by `load_settings`) taken as well |
| C9 | REFUTED — the label said `decision`, the values were outcomes; Codex would keep the name and pass the audit decision | **Accepted as Cursor framed it** — the label is renamed `outcome`; one rename instead of a second vocabulary on the wire |
| C10 | CONFIRMED (an in-memory migration-9 comparison passed) | **Its verdict was wrong** — the reference cluster crashed on this head's `SCHEMA`, and Cursor's file-backed test reproduces it. Codex's in-memory check evidently did not run `Store.__init__`'s `executescript(SCHEMA)` against a table lacking `audit_id`; it did ask for exactly the `table_info` parity test that now exists |

Beyond the brief, Codex found `NOTES.txt` saying a first read backfills "0 days at most" when
`retentionDays` is 0, the value that means no limit — fixed.

## The live run, second attempt

The second deploy of the branch (after Cursor's fixes) opened the cluster's existing database —
"schema migration 10 applied" in the log — rendered the ClusterRole (`oc auth can-i get nodes
--subresource=proxy --as=<the SA>` yes; `list pods -n openshift-authentication` no) and the manager
Job returned the operator CR to `Normal`. It then read nothing: every listing of
`/api/v1/nodes/crc/proxy/logs/oauth-server/` answered `406 Not Acceptable`. Measured with curl and
the admin token, the API server's proxy negotiates the response against the request's `Accept`: an
explicit `application/json`, `text/html` or `text/plain` all get 406 and `*/*` (or no header) gets
the listing — and the reader had inherited the client's `application/json`. Both node-log methods
now send `*/*` (`gsd/kube.py#NODE_LOG_HEADERS`), with a transport-level test.
