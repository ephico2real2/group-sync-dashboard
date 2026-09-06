# Review — PR #89, D1: login capture from the oauth-server audit log

Adversarial second-opinion pass, 2026-09-06, on the ten-claim brief for #89
(`docs/specs/SPEC_D1_audit_log_login_capture.md` applied as amended by its grounding note; application
0.17.0, chart 0.19.0; the deviations are in the spec's orchestrator's notes). Cursor (Grok 4.6 high fast,
ask mode) and Codex (gpt-5.6-sol, xhigh) reviewed the same head; every verdict was re-checked here
before a decision, and every accepted finding came with a test that failed before its change.

## Live run on the reference cluster

Three deploys of the branch to CRC with `environments/crc.yaml` switched to `loginCapture.source:
audit-log` and `authLogLevel.enabled: false` (manager left on). The first crashed on open —
`sqlite3.OperationalError: no such column: audit_id` — which is Cursor's C10 below. The second opened
the database ("schema migration 10 applied"), rendered the ClusterRole and retired Debug, and read
nothing: 406 from the proxy, the section after Codex's verdicts. The third, head 3282d9e, is the one
this record describes:

| Measured | Value |
|---|---|
| audit.log on the node | 27,825,157 bytes, never rotated; drained in four cycles under the 8 MiB budget |
| cursor after the drain | offset 27,825,157, fingerprint of the first 1,024 bytes, settled through the newest event |
| audit rows recorded | 280 — credential 42 (37 success, 5 failed), cli 101 (83 success, 18 failed), session 137 |
| pod-log rows linked to their audit twin | 110 of 129, at a 0.25 s window |
| `identity_match` | developer 185, ldap-local 82, unmatched 13 |
| two fresh `oc login` attempts (wrong then right password, developer) | both rows within two minutes: `cli failed 401 "Authentication failed, attempted: basic"` and `cli success 302`, provider `developer` resolved through the User's Identity — the break-glass label the pod-log source could never give a CLI login |
| `/metrics` | `gsd_login_capture_source_info{source="audit-log"} 1`, `gsd_login_capture_audit_settled_timestamp_seconds{node="crc"}`, last-read advancing; no name in any label |
| `/logins` envelope | `source: audit-log`, `kinds` `[credential, cli]` by default and all three on `?kind=all`, `retained_since` 2025-08-08 (the backfill), `?outcome=provider_error` accepted |
| RBAC | `oc auth can-i get nodes --subresource=proxy --as=<SA>` yes; `list pods -n openshift-authentication` no; no pod-log Role rendered |
| operator CR | `spec.logLevel` back to `Normal` by the manager's Job |

Usernames were not copied out of the cluster for this record; the counts above come from grouped
queries run inside the pod.

## Second pass — Cursor

Head 3282d9e (the pass-1 fixes), ten claims on the fixes themselves. All ten CONFIRMED, with a
traced table for every `continue` in the capture loop (no path leaves `read_ok` wrong except a
one-cycle case where a 416-rotation read counts as a body and the from-0 re-read then fails — the
next cycle is honest, and the definition of "body read" includes that 416 on purpose) and a check of
httpx 0.28.1's header merge from the installed wheel (a request header REPLACES the client default;
it does not join it). Its residuals, all taken: tests for the re-read after a fingerprint mismatch
advancing last-read, for an OAuth CR that lists no provider (`identityProviders: []` and the field
absent) reaching `_configured_providers` as an empty set, for the newline-less tail counting in the
fingerprint and a truncated tailless rotated file staying open, for opening v5 and v8 databases (not
only v9), for the 16 ms pairing at the production window, for the NOTES sentence at retentionDays 0
and 400, and for every `loginCapture.*` README cell against values.yaml; the Accept test now runs
against the client's real `application/json` default; the stale `correspondence_seconds: int = 2`
hint, migration 7's comment about SCHEMA's shape, the CHANGELOG's "by decision" and the README's
unqualified "refused together with `authLogLevel.enabled=true`" are corrected. Its one accepted
limitation: an audit list set with `--set-string` arrives as a string and takes the comma-split
hand-written path — the list path is the chart's, and the values comment says lists.

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
