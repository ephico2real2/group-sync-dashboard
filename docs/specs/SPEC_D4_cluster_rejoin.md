# SPEC D4 — Rejoin: a cluster administrator signs in to a remote cluster as themselves, once, and the dashboard fetches a fresh poller token and forgets the password (#316)

| | |
|---|---|
| Programme | Epic D (#384), Reconnect a cluster from the screen — build step 3, after Refresh (#311, SPEC_D3) and the duplicate-URL warning (#314) |
| Batch | D — reconnect |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 1.5.0, chart 0.59.7 |
| Issue | [#316](https://github.com/ephico2real2/group-sync-dashboard/issues/316) |
| Status | merged |
| Source | OB3's specification of 2026-09-27 (implementer, phase 1: research and the spec, no production code), from issue #316 (its body, the runbook requirement and the design refinements of 2026-09-23, and D8 as the operator decided it on 2026-09-26), epic #384 and its mockup, SPEC_D3, SPEC_S4a, SPEC_S4c, SPEC_S4d and SPEC_S4e. Revised the same day after the reviews of Grok and Codex on `3cbc4e3` and the operator's decision on the gate's scope (orchestrator's notes). Measured on this machine against a fake remote, and read-only on the reference cluster. Appendix E's blocks were cut from a copy of `3cbc4e3` with the design implemented, and applied back to a clean clone for the proof in Appendix C |

## How to read this spec

Sections 1 to 4 are the design. Read them in order:

| § | what it answers |
|---|---|
| 1 | what changes, in one table |
| 2 | what one press may send: the safety budget, measured, with its scope |
| 3 | the exchange, step by step: the route, the rows, the steps, the answers, the provenance, the dialog, the redaction |
| 4 | every decision the issue left open, one line each |
| 5 to 7 | what must not change, what is left, and the change file by file |
| appendices | the evidence (A), the runbook's outline (B), the tests (C), the lab walk (D), the implementation blocks (E) |

The implementer applies Appendix E with:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_D4_cluster_rejoin.md . --apply

Line citations are plain `file:line` text at `3cbc4e3`, whose code the blocks apply to. `path#anchor` citations
are the maintained kind. An upstream source is cited at the commit it was read at, from the raw file with line numbers.

**The constraint over everything here:** nothing in this spec, its tests or its walk logs in as any account, and
never as the fleet account. The tests use made-up names against a fake remote.

## Orchestrator's notes

- **The per-cluster ids moved to the `_` scheme (#462).** Every per-cluster id on the Cluster Configurations page is
  now `cc-<kind>_<cluster id>`, the scheme #441 gave Refresh: `cc-rejoin_<id>`, `cc-rejoin-result_<id>`,
  `cc-rotate_<id>`, `cc-rotate-token_<id>`, `cc-rotate-go_<id>`, `cc-rotate-msg_<id>`, `cc-delete_<id>` and
  `cc-delete-msg_<id>`. No kind holds `_`, so an id's first `_` ends its kind, and one cluster's id can no longer
  equal another's whatever the clusters are called. A Secret's cluster name cannot hold `_`
  (`gsd/clusterconfig/parser.py#_NAME`), but a values entry's name may (`gsd/config.py#parse_cluster_entries` refuses
  only `/` and duplicates), so the rule rests on the kinds, not on the names. Joined with `-`, the Rejoin button of a
  cluster named `result-x` had the id of x's result line, and `token-x`'s Rotate link had the id of x's token field,
  so the lookups by id landed on the wrong card. Appendix E's #316 blocks, for the page and for its tests, still
  spell the ids from before #441 and #462 (`cc-refresh-<id>`, `cc-rejoin-<id>`); the page
  (`gsd/static/index.html#cc-<kind>_<cluster id>`) and its tests are the reference. The card's own id,
  `cc-cluster-<id>`, is unchanged.
- **A password inside the username (#447).** Refuse a Rejoin when the password, stripped and casefolded, is the
  username or lies inside it, in `gsd/rejoin.py#check`, before any request or credential-gate change. Answer `422`
  with the fixed detail `rejoin-password-within-username: the password must not be the username or a part of it,
  ignoring case and surrounding spaces; it was not sent`. No submitted value is repeated. Why wider than equality
  (OB2's review of #463, measured on the suite's rig): the scrub replaces the raw password at any length wherever it
  occurs, so a password inside the username left `account=<redacted>.admin` — the redacted span IS the password, and
  the name is in plain text in the Secret's annotations and on the Logins tab; and `redact_text` strips, so a password
  padded with spaces left `as <redacted>` in the answer beside `account=alice.admin` in the line. Not refused, and a
  stated residual: a password that is the username plus a neighbour the sentence has (`alice.admin,`) leaves
  `as <redacted> who may` — refusing every password that contains the username would close it, but NIST SP 800-63B-4
  §3.1.1.2 compares the entire password against the blocklist, "not substrings or words that might be contained
  therein", so that wider rule was not taken. This is smaller than always scrubbing usernames. Every password spelling
  in §3.7 stays scrubbed. The budget and D4-7's per-pod memory are unchanged.
- **The id and the file.** The issue proposed `SPEC_R1_rejoin.md`; the brief names `SPEC_D4_cluster_rejoin.md`, the
  next step of batch D after SPEC_D3. The index row sits between S4d (#315) and L1 (#321), in issue order.
- **The versions are the orchestrator's**, as for S4e. The release commit moves `pyproject.toml`, `gsd/__init__.py`
  and `appVersion` to the next MINOR, and the chart by the PATCH that move takes. No block touches them.
  `local-development/check-app-version-bump.py` and CI's `version-bump` job require that commit.
- **D8 is decided, in its simple form** (the operator, 2026-09-26, #316): *"we log the response from the remote cluster
  but don't make things very complicated. We can check if the person joining the cluster is also a cluster admin on
  the remote cluster."* §3.3 step 3 is exactly that.
- **S4e (#432) merged first, in #438 (application 1.4.0).** The daily ping now presents the password only as an
  account the configuration declares. This spec never writes the person's name into `lookup-account` or any
  declaration (§3.5), so it was safe before S4e and is safe with it;
  `test_the_daily_ping_never_logs_in_as_the_person_who_rejoined` runs the ping and counts the wire. With S4e taking
  index slot 31, this spec takes 32 (the orchestrator, merging main into this branch on 2026-09-27).
- **The runbook's commands are fenced with `~~~`.** `local-development/apply-spec-blocks.py` ends a block's fence at
  the first line that is exactly three backticks, so a Markdown file a block creates cannot use backtick fences.
- **The figure's PNGs are re-rendered in the implementing commit (§7).** The renderer is not byte-stable: three
  figures whose source did not change came out a few bytes different. Commit only the two `joining-a-cluster` PNGs.
- **Two things found while writing, outside this change.** (1) `gsd/fleetlookup.py#lookup` reads the token Secret
  inside the `FleetLogin` session but never hands that token to `FleetLogin.add_secrets`, so a revoke that fails with
  a body echoing it writes it into `fleet-logout-failed`. Rejoin does (§3.3); the lookup must not change here. (2) The
  card's ids `cc-refresh-<id>` and `cc-refresh-result-<id>` collide for clusters named `east` and `result-east`.
  Rejoin's dialog uses its own `rejoin-` prefix.
- **The review of 2026-09-27** (Grok and Codex on `3cbc4e3`). Taken, each with its red and green test (Appendix C):

  | finding | what changed |
  |---|---|
  | Codex C3 (a): a JSON key equal to the password came back in the 422 | the route refuses the body's shape in fixed words |
  | Codex C3 (b): an unexpected error in D8 left the route, and Uvicorn prints a traceback with its text | the route catches it and answers `rejoin-failed` in fixed words; the line records only that it happened |
  | Codex C3 (c): a password under four characters, echoed by D8, passed the emit helper's floor | D8's reason and every failure's evidence are scrubbed at any length before a line is written |
  | Codex C3 (d): a refused token read, then a failed revoke echoing that token, logged it | the refused read's secrets reach the login inside `with`, before the revoke runs |
  | Codex C1, the browser: a 307 or 308 re-sends the credential POST to its Location (measured in Chromium, Appendix A.7) | the credential fetch uses `redirect: "error"`; `test_fetch_refuses_redirects_and_submits_once` runs in Chromium |
  | Codex C3, the dialog's words | it no longer says the username is not stored, and says a password manager may ignore `autocomplete="off"` |
  | Grok C4 and Codex C4 | #438 made the shared username grammar `fullmatch`, so Rejoin's extra newline check and its explanation are gone; the newline cases stay and pass through the shared grammar |
  | Grok C1 and Codex C1: the budget's missing shapes | §2 gains every shape the reviewers measured, with honest counts |
  | Codex C7 | Appendix C says what was measured, where and on which tree |
  | Grok C8 and Codex C8 | this structure: the design first, the evidence and blocks in appendices |

  **The operator's decision on C2 (2026-09-27):** keep the per-pod memory gate (D4-7). Its rationale is rewritten in
  §2 and D4-7.

  Declined, one line each:

  | proposal | why declined |
  |---|---|
  | Codex's durable account hold, per-press receipt Secrets and request IDs (`guarded_rejoin`, `X-GSD-Rejoin-Request`) | the operator's decision on C2 |
  | Codex's changes to D4-6, D4-8, D4-12 and D4-17, its `rejoin-held` outcome and its "rearm" words | they follow from the declined hold; its D4-7, D4-9, D4-11, D4-14 and D4-15 points are taken above |
  | Codex's rearm section in the runbook | it follows from the declined hold |
  | Grok's username-only TTL mark | the same class of durable hold; recorded in D4-7 as the design that exists |
  | Codex's tests of the hold and receipts (`test_failure_is_held_across_pods_without_password_fingerprint`, `test_a_proxy_replaying_a_successful_post_to_another_pod_cannot_login_again`, `test_an_uncertain_guard_create_never_reaches_oauth`, `test_missing_request_id_never_logs_in`, `test_crash_after_login_leaves_hold_for_the_next_pod`) | they test the declined hold; the replay is measured as 2 in §2 instead |
  | Codex's `test_fleet_spellings_never_reach_the_wire` and `test_only_boolean_true_permits_token_read` | they passed before and after (Codex's count); the refusal cases and `test_a_review_that_does_not_answer_is_a_refusal_never_a_yes` hold those shapes |
  | Codex's `test_authorize_redirect_without_token_is_terminal` | the budget test now holds the same redirects, with their counts |
  | Codex's node-based fetch test | taken by name and intent, run in Chromium instead: CI's `tests` job sets up no node |
  | Codex's reworded test assertions for the before-run (C7) | Appendix C states each before-failure as measured instead |
  | Grok's belt-and-braces newline check | the orchestrator's decision (C4): removed, the shared grammar refuses it |
  | Grok's and Codex's tests over source and spec text (`test_d4_7_states_the_scope…`, `test_the_shared_grammar_already_refuses…`) | they pin comments and prose, not behaviour; the dialog test pins the dialog's scope sentence |
- **The confirmation review, round 1** (Grok and Codex on `2c227d9`). Grok: ready for phase 2. Codex: three
  minimum changes, all taken; the first two each with its red and green test (Appendix C):

  | finding | what changed |
  |---|---|
  | Codex P1: a short password JSON-escaped by the remote (`x"Z` as `x\"Z`, `éZ` as `\u00e9Z`) escaped every scrub, because the shared escaped forms stop at eight characters | `gsd/rejoin.py#_scrub` hands the fleet's scrub each secret also escaped once and twice, ASCII and not; `RejoinLogin._scrub` routes the login's own remote text through it. The fleet's scrub is unchanged |
  | Codex P2: an unexpected error after the login existed answered only "press Refresh", losing how the login ended | `rejoin` holds the login while `_exchange` runs, and on an unexpected error answers fixed words, then how the login ended; the route keeps its fallback for an error before a login exists |
  | Codex C3: the docstring said a password the directory "answered" is not sent again | it says "refused", for this exact username, by this pod; a success is not held, and §2, §3.3, `API.md` and the changelog say the same |

  Codex's Chromium check was blocked by its sandbox; `test_fetch_refuses_redirects_and_submits_once` passed here in
  Chromium on the applied tree, as it did for Grok. Taken in a smaller form: Codex's scrubber copied the escaped-form
  loop of `gsd/kube.py#redact_text` and replaced the fleet's scrub; this one keeps the fleet's scrub and hands it the
  escaped forms.
- **The confirmation review, round 2** (Grok and Codex on `64ecd80`). Grok: ready for phase 2. Codex: the twenty cases
  hold, and both reviewers found spellings they miss. Taken, the last round on this point, each with its red and
  green test (Appendix C):

  | finding | what changed |
  |---|---|
  | D8's client cut a failed answer's body at 200 characters BEFORE Rejoin's scrub, so a password straddling the cut left a fragment, in any spelling, the plain one included | `ClusterClient._send` already takes `secrets=`, but its `_redact` keeps `redact_text`'s eight-character floor; so D8 uses `_ReviewClient`, whose `_redact` adds Rejoin's scrub before the cut. The shared client is unchanged |
  | real encoders also write `/` as `\/`, and `\u` hex in upper case | `gsd/rejoin.py#_spellings` adds both to each escaped form |

  Not coded, stated instead (§3.7, §6): three layers of escaping, and any other encoding. The scrub covers accidental
  echoes; a hostile remote holds the password anyway, and can always choose an encoding no scrubber recognises.
  Codex's triple-escape probe is kept as an expected failure, `xfail(strict=True)`, so it runs every time and turns
  red if the residual ever closes. Declined: Codex's general unescape-and-map-back scrubber.
- **The confirmation review, round 3** (Grok and Codex on `4010a52`). Both: the pre-cut scrub holds at every offset,
  and the stated boundary and the strict expected failure hold. Both refuted one point, taken: Go's `encoding/json`,
  the encoder of the Kubernetes and OpenShift API servers and of the oauth-server, writes `<`, `>`, `&`, U+2028 and
  U+2029 as lower-case `\u` escapes and leaves every other character as is, `é\u2028Z` for one. `_spellings` adds
  that one spelling (`_GO`), once and twice like the others; its test rows are the Go runtime's own output (Codex's
  `go-spellings.json`). The Rejoin test file measured `104 passed, 5 xfailed` at `4010a52`, as both reviewers found;
  the 105 in round 3's hand-back counted one Chromium test run beside it. Declined, and stated in §3.7: Codex's
  per-character matcher for PHP's optional `JSON_HEX_*` flags and .NET's `JavaScriptEncoder` escapes.

## 1. The point

**A cluster administrator signs in to a remote cluster as themselves, once. The dashboard fetches the poller's token
there and forgets the password.**

| | |
|---|---|
| **What goes wrong today** | When a remote's stored token stops working, the only repair is `oc create token` on the remote plus `oc patch secret` on the host: someone cluster-admin on both clusters, with two sessions (#316). The Secret it leaves names nobody. |
| **The change** | `POST /api/clusterconfigs/{name}/rejoin`, offered on the card after Refresh answers `auth_failed` or `pending`. One login as the person, one question to the remote about that person (D8), one read of the poller's token Secret, the login revoked, one write of `gsd-cluster-<name>` with the person's provenance. |
| **The safety property** | One press sends the password in at most one authorize request, never retried, never stored, never as any other account, and the fleet account is never used. The pod that sent a refused password does not send it again; another pod does not know (§2). |
| **The gates** | The host: the cluster-admin tier (#322) and the writes switch. The remote: its own RBAC, asked about the person with the person's own login (D8). |
| **What it reuses** | #283's `FleetLogin`, #284's `read_sa_token` and `store`, #315's `CredentialGate` (the poller's one instance), #311's card and route pattern, #143's static dialog. |
| **What is new** | `gsd/rejoin.py`, the route, `rejoinable` on each row, the `rejoin` token-source and three provenance annotations, the dialog, `RUNBOOK.md`. |
| **What does not change** | Refresh, the credential gate, the lookup, the daily ping, self-login, Rotate, Delete, Test, the Add form and its `oauth` refusal, and the dashboard ServiceAccount's permissions (REMOVED 0, ADDED 0). |

## 2. The safety budget

**One press sends the password at most once. The pod that sent it does not send a refused password again. A
restarted pod, another replica, or a proxy that replays a press to another pod can send it once more: 2 at worst.**

The property, with its scope:

- A press sends the password in at most one authorize request, as the account that request names.
- The application never retries it.
- The pod that sent a password the directory refused for that username does not send it again until that pod
  restarts. A success is not held: two right presses send twice.
- Nothing stores the password.
- No fleet path presents the fleet password as the person, and the person is never presented as a fleet account.

**The unit is an authorize request the application submits,** counted by the fake remote in the hermetic tests
(`httpx.MockTransport`). What a remote OAuth server, a directory or a proxy does with that one request is outside this
count.

**The scope, stated (D4-7).** The gate lives in each pod's memory. After a failure, a deliberate press that reaches a
restarted pod or another replica sends the same password once more: 2 at worst. A proxy that replays a successful
press to a second pod is also 2. A durable hold would close this and was declined for its operating cost (D4-7).

| shape | authorize requests the app submits | outcomes, in order | measured by |
|---|---|---|---|
| one press, the right password | **1** | `rejoined` | `test_the_budget_over_the_system` |
| a double click on the dialog's button | **1** | one POST, one answer | `test_one_press_sends_the_password_once_and_the_page_keeps_it_nowhere` (Chromium) |
| a second press, from another tab or a script, while the first is out | **1** | the second answered `409`, nothing sent | `test_one_rejoin_at_a_time_in_this_process` |
| two presses in turn, the right password | 2 | `rejoined`, `rejoined` | `test_the_budget_over_the_system`: each press sends once; a success is not gated |
| a 401, then the same password | **1** | `login-refused`, `login-refused` (not sent) | the same |
| a 500 (a locked account), then the same password | **1** | `login-failed`, `login-refused` (not sent) | the same |
| a timeout after the password was written, then the same | **1** | `login-failed`, `login-refused` | the same |
| a 302 without a token, then the same | **1** | `login-failed`, `login-refused` | the same |
| a 302 to another host, then the same | **1** | `login-failed`, `login-refused` | the same |
| a 307 to another host, then the same | **1** | `login-failed`, `login-refused`: the redirect is not followed | the same |
| a failure before the password was written, then again | 1 | `login-failed` (not sent), `rejoined` | `test_a_failure_before_the_password_is_written_is_tried_once_and_is_not_gated` |
| a 401 on one cluster, then the same password on another | **1** | `login-refused`, `login-refused` | `test_a_bound_failure_is_one_authorize_and_the_same_password_is_not_sent_again` |
| a 401, then the right password | 2 | `login-refused`, `rejoined` | `test_the_budget_over_the_system` |
| a 401, then the same password on a restarted pod | 2 | `login-refused`, `login-refused` | the same: **the scope** |
| a 401, then the same password on another replica | 2 | `login-refused`, `login-refused` | the same: **the scope** |
| a proxy replays a successful press to another pod | 2 | `rejoined`, `rejoined` | the same: **the scope** |
| the pod restarts after the password was written, then the same password | 2 | no answer, then the new pod's | not measured: the gate dies with the pod, and the restarted-pod row measures the new pod's side |
| the page's own fetch | 1 per press, no retry | — | `test_fetch_refuses_redirects_and_submits_once` (Chromium) |
| a 307 or 308 in front of the dashboard | 0 more | the fetch refuses the redirect; the page says the answer did not arrive | the same |
| the browser's back or forward button | 0 | no `<form>` to resubmit; `pagehide` clears the fields | the `pagehide` clearing is measured; a real back/forward restore is not |
| a proxy or the remote resends the one authorize | outside this count | — | not the application's to count (above) |
| the daily ping after a Rejoin | 0 as the person | the ping presents only the fleet account's own pair | `test_the_daily_ping_never_logs_in_as_the_person_who_rejoined` |
| a fleet account's name, in any capitalisation | 0 | `422 rejoin-fleet-account` | `test_each_refusal_before_the_wire_sends_nothing_and_repeats_no_value` |
| a fleet account's name with a final newline | 0 | `422 rejoin-username-invalid`: the shared grammar refuses it (#438) | the same |

**Can anything make one press run twice?** Each layer was read (Appendix A.5). The page sends once and refuses
redirects. The router, oauth-proxy and the app do not replay a written POST. Only the browser resends a request it
already wrote, and only when a reused connection closes before any response header; the router answers a failed
backend with a status instead. Not measured end to end.

## 3. The exchange

### 3.1 The route and its gates

**`POST /api/clusterconfigs/{name}/rejoin`, registered only when writes are on, behind the tab's write gate, and
refused before anything is sent unless the request is exactly right.**

The route is `rejoin_cluster_config` inside `gsd/api.py#build_app`, beside Refresh. In order:

| step | check | refusal | anything sent? |
|---|---|---|---|
| 1 | the writes switch (`clusterConfig.secrets.writes.enabled`) | the route does not exist: `404` | no |
| 2 | `_writes_gate`: a proxy-verified identity and the cluster-admin tier (#322) — the **host's gate** | `403` | no |
| 3 | the body is exactly `{"username": <string>, "password": <string>}` | `422` in fixed words: a key can be the password, so none is repeated | no |
| 4 | the name is a live cluster | `404` | no |
| 5 | `gsd/rejoin.py#check`: the row is rejoinable (§3.2); the username fits the shared grammar; it is not a fleet account; the password is present, with no control character and no unpaired surrogate, and, stripped, is neither the username nor a part of it, ignoring case | `409 not-rejoinable`, or `422 rejoin-username-invalid`, `rejoin-fleet-account`, `rejoin-password-missing`, `rejoin-password-invalid`, `rejoin-password-within-username` | no |
| 6 | this process runs a poller, whose credential gate Rejoin uses | `409` | no |
| 7 | no other Rejoin is running in this process | `409`, never queued | no |
| 8 | `gsd/rejoin.py#rejoin` (§3.3) | `200` with an outcome (§3.4) | at most one login |
| 9 | any error step 8 did not expect | `200 rejoin-failed` in fixed words, then how the login ended (`gsd/rejoin.py#stopped_unexpectedly`) | at most the one login |

Why `body: Any = Body(None)`: a body typed `dict` lets FastAPI answer a non-object body with a 422 that quotes it
whole, password included (measured, Appendix A.4). With `Any`, FastAPI passes the body on unvalidated, and step 3
refuses it in fixed words.

Why step 9: an error's own text may quote the password, and an error that leaves the route is printed with its text
by Uvicorn. So it never leaves. `rejoin` catches it while it still holds the login, so the answer and the line say,
after the fixed words, how the login ended: signed out, or the token to delete. The route catches anything raised
before a login exists.

A success wakes discovery, as every write on the tab does, so the card polls within seconds.

### 3.2 Which cards may be rejoined

**Secret-sourced rows and `saTokenLookup` stanzas. `rejoinable` on each row is the route's own rule, so the page
offers Rejoin exactly where the route accepts it.**

| the row | rejoinable | what Rejoin writes | why |
|---|---|---|---|
| a Secret with a `bearerToken` (hand-written, created by the tab, or written by the lookup) | **yes** | updates it in place | the design's case: a stored token stopped working |
| a Secret that declares `saTokenLookup` | **yes** | updates it in place, as the lookup would | its token was never fetched, or the lookup is stuck |
| a Secret that declares `oauth` | **yes** | updates it in place: `bearerToken` replaces the `oauth` key | the declaration says a person supplies the credential |
| a values stanza that declares `saTokenLookup` | **yes** | creates `gsd-cluster-<name>` with the stanza's policy | the stanza is pending, for example while the fleet account is locked |
| a Secret or stanza that declares `userSelfLogin` | no | — | its credential is a session; a stored token would replace the mode |
| a Secret generated from a ConfigMap | no | — | its reconciler owns it |
| a values entry with its own token | no | — | a Secret would shadow it (`shadows-values-entry`) |
| the host | no | — | it polls as the pod's own ServiceAccount |
| a retired row | no | — (`404`) | nothing describes it any more |

### 3.3 The steps

**One login, one question, one read, one revoke, one write — in that order, and each failure stops it.** The route
holds a process-wide lock across all of them, so the gate's check and the login it guards are one step.

| step | what | on failure | the credential gate |
|---|---|---|---|
| 1 | `gate.account_refusal(username, password)`: has the directory refused this password for this username, in this pod? | `login-refused`; **nothing sent** | read |
| 2 | `RejoinLogin(..., policy=ONE_TRY)`: #283's login, as the person | a bound failure (401, 500, a timeout after the write, a 302 without a token): `login-refused` or `login-failed`. A failure before the write: `login-failed`, not sent | `refuse` after a **bound** failure only, as the lookup does (#315) |
| 3 | inside the session, D8: `remote_says_cluster_admin`, then the `cluster-rejoin-review` line with the remote's answer | `not-cluster-admin` (a no) or `access-review-failed` (no clean answer); nothing read or written | — |
| 4 | inside the session: `read_sa_token`; its token, or a refused read's, goes to `login.add_secrets` before the session ends | `sa-token-secret-missing`, `sa-token-unreadable`, `sa-token-invalidated`; nothing written | — |
| 5 | the session ends: `FleetLogin.__exit__` revokes the login, whatever happened | a failed revoke is a `fleet-logout-failed` line; the answer names the object to delete | — |
| 6 | `store(..., rejoin=(person, account, instant))`: update the Secret, or create it for a stanza | `lookup-write-failed`; nothing stored | — |
| 7 | the `cluster-rejoined` line; answer `rejoined` | — | — |

`ONE_TRY` is `RetryPolicy(attempts=1)`. The fleet's schedule retries a failure that bound nothing up to five times,
about a minute and a half. A person is waiting behind a router whose timeout is 30 s by default, and the next press
is the retry.

### 3.4 The answer

**`200 {outcome, message, at}` for every Rejoin that reached step 8, as Refresh answers.** `at` is ISO-8601 UTC.
`message` is scrubbed of every secret in play.

| `outcome` | when | password sent? | gate writes? | written here? |
|---|---|---|---|---|
| `rejoined` | the login, a yes, the read and the write all succeeded | once | no | the Secret |
| `login-refused` | this pod's gate already held this password for this account | **no** | no | no |
| `login-refused` | the remote answered 401 with a Basic challenge | once | **yes** | no |
| `login-failed` | written, and no session came back: a 500 (a locked account's LDAP code 19), a read timeout, a 302 without a token, any other answer | once | **yes** | no |
| `login-failed` | the login could not start: discovery, the connection or TLS failed | **no** | no | no |
| `not-cluster-admin` | the remote answered `allowed: false` | once | no | no |
| `access-review-failed` | the remote could not answer: 403, 500, a timeout, no boolean `allowed` | once | no | no |
| `sa-token-secret-missing`, `sa-token-unreadable`, `sa-token-invalidated` | the token Secret could not be used | once | no | no |
| `lookup-write-failed` | the token was read and the host refused the write | once | no | no |
| `rejoin-failed` | an error the design did not expect (§3.1 step 9); the message ends with how the login ended | unknown: press Refresh first | no | unknown |

Every answer after a session existed says how the login ended: "the login was signed out", or the object to delete
and the command (a token's name is not a secret). Refusals before anything is sent are HTTP errors (§3.1).

### 3.5 The provenance on the written Secret

**The Secret says a person fetched it, who, as which account, and when. It never says so in `lookup-account`.**

| annotation | value | on an update | on a create |
|---|---|---|---|
| `groupsync-dashboard.io/token-source` | `rejoin` | set | set |
| `groupsync-dashboard.io/source-namespace` | `group-sync-operator` (the configured source) | set | set |
| `groupsync-dashboard.io/source-service-account` | `group-sync-dashboard-cluster-poller` | set | set |
| `groupsync-dashboard.io/rejoined-by` | the host identity who pressed Rejoin (`X-Forwarded-User`) | set | set |
| `groupsync-dashboard.io/rejoin-account` | the account the remote signed in | set | set |
| `groupsync-dashboard.io/rejoined-at` | the instant, ISO-8601 UTC | set | set |
| `groupsync-dashboard.io/lookup-account` | — | **removed** | never written |
| `groupsync-dashboard.io/managed-by` | — | kept | `ui` |

Three rules:

1. **Never `lookup-account`.** The daily ping reads that annotation for the account it logs in as with the fleet
   password (poller.py:1734-1739, 1827; S4e now also requires a declaration). A Rejoin removes it, and a later lookup
   removes the three Rejoin keys (`writer.store_lookup`: one path's provenance replaces the other's).
2. **`rejoin` is not a mode's word.** `writer.owned_by_mode` counts `rejoin` over a `saTokenLookup` stanza as the
   stanza's own, so the stanza keeps its policy and raises no `shadows-values-entry`. Every other case answers as
   before.
3. **Two names on purpose.** `rejoined-by` is who the dashboard verified; `rejoin-account` is who the remote signed
   in. They can differ: two identity providers may spell one person differently.

### 3.6 The dialog

**A static `<dialog>` outside `#main`, like `#ns-preview`: the minute's repaint cannot touch what is typed.**

| part | what |
|---|---|
| where | `#rejoin-dialog`, next to `#ns-preview`, opened with `showModal()` |
| when the card offers it | a **Rejoin…** button after Refresh, where the row is `rejoinable` and Refresh answered `auth_failed` or `pending`; it stays while its own answer shows. Absent, not disabled, below the tier or with writes off |
| the words | "Sign in to `<name>` as yourself…" then: "**Your password is used for this one login and is not saved by the dashboard.** The Secret records your username and who pressed Rejoin. Browser password managers may ignore the request not to save these fields." |
| the two gates | "passed · 1 · this cluster, the host" and "decided there · 2 · `<name>`, the remote" |
| the one-try warning | "**One try per password on this pod.** If this password is refused, this pod does not send it again, to any cluster, while it is the same password. A restarted pod or another replica does not know that, and can send it once more: press Refresh before you press Rejoin again. A locked directory account answers HTTP 500, not 401, so trying again only locks it further." |
| the fields | username (`autocomplete="off"`, `autocapitalize="none"`, `spellcheck="false"`) and password (`type="password"`, `autocomplete="off"`), in no `<form>` |
| a press | reads both fields, empties the password field, disables the button, and sends one `POST` with `redirect: "error"`. A press while one is out sends nothing; so does one with a field empty. Enter in the password field is a press |
| the answer | on the card: "Rejoin: ● `<outcome>` · `<at>` — the message". A success closes the dialog; a refusal keeps it open with an empty password field. No answer (a gateway timeout, a refused redirect) says the Rejoin may have finished, and to press Refresh first |
| clearing | Cancel, Escape, `pagehide` and the idle sign-out clear both fields |
| state | `view.clusterRejoin[<id>]` holds the answer only, never a username or a password |

`autocomplete="off"` asks; it cannot forbid. The HTML Standard lets a browser override it (Appendix A.4), so the
dialog says so. The mockup drew `autocomplete="username"` and `"current-password"`; this spec uses `off` (D4-14).

### 3.7 Where the password could land, and what keeps it out

**The password crosses one TLS hop into the app and one into the remote's OAuth server. It is in no URL, log,
store, answer or browser storage the dashboard controls.**

| place | what keeps it out |
|---|---|
| a URL | no `<form>`; the password travels in a POST body |
| a redirect | the credential fetch uses `redirect: "error"` |
| the request logs | oauth-proxy's request log and Uvicorn's access log write the request line, never the body |
| a 422 | `body: Any`, and the shape refused in fixed words |
| an unexpected error | caught by `rejoin` while it holds the login, and by the route before one exists: fixed words and how the login ended, nothing of the error |
| the app's lines and answers | every line and answer is scrubbed of the password, its Basic form, the login's token and the token read, in every spelling of §3.7's covered set, at any length: the emit helper skips values under four characters, and the shared escaped forms stop at eight |
| a cut quote | the login's and D8's clients scrub a remote's body before cutting it to 200 characters, so a password straddling the cut leaves no fragment; the token read quotes no body at all (`gsd/fleetlookup.py#_status_only`) |
| a failed revoke | the token read, or a refused read's, is handed to the login before the revoke runs |
| the audit logs | the password is in a header, never the URI; the audit log is written at Metadata level |
| the database, the Secret, the gate | Rejoin writes no row; the Secret holds the token read and the provenance; the gate holds 64 bits of SHA-256, in memory |
| browser storage | the page stores only `gsd-mode` and `gsd-palette`; the fields are never copied into `view` |
| the back/forward cache | the fields are cleared on `pagehide` |
| a password manager | `autocomplete="off"` is a request a browser may ignore; the dialog says so |

**What the scrub is for: accidental echoes.** A remote that quotes the request back by mistake, a proxy's error page,
a debug handler. The covered set:

- the raw value;
- Python's `json.dumps`, ASCII or not, with `/` as `\/` or not, and `\u` hex in either case;
- Go's `encoding/json` default, the remote's own encoder: `<`, `>`, `&`, U+2028 and U+2029 as lower-case `\u`
  escapes, every other character as is;
- each of those up to two layers deep.

The scrub removes all of those. It does not claim more. Other encoders' optional escapes are outside the set: PHP's
`JSON_HEX_*` flags, .NET's `JavaScriptEncoder`. The remote is OpenShift, whose servers encode with Go. A hostile remote
already holds the password, since it received it, and it can always choose an encoding no scrubber recognises, base64
for one; three layers of escaping are in that class (§6).

**The redaction pin** (`tests/test_cluster_rejoin.py#test_the_password_appears_on_one_header_and_nowhere_else`, #283's,
carried) runs fourteen scenarios. In each, the fake remote plants every secret in play in every field it controls. The
test then looks for them in the answer, every log line at DEBUG, every stored Secret, the gate, the findings and the
whole database, and on the wire outside the one authorize's `Authorization` header.

## 4. The decisions

**Each is decided as recommended; the operator rules.** One line each: the choice, and why.

| # | decision | chosen, and why | declined alternative |
|---|---|---|---|
| D4-1 | the spec's name | `SPEC_D4_cluster_rejoin.md`: the next step of batch D | `SPEC_R1_rejoin.md`, the issue's placeholder |
| D4-2 | which rows are rejoinable | Secret rows and `saTokenLookup` stanzas (§3.2): the epic's decision; `oauth` Secrets say a person supplies the credential | `userSelfLogin` rows: a token would replace the mode |
| D4-3 | when the card offers it | after Refresh answers `auth_failed` or `pending`: diagnose first | always: invites a Rejoin that cannot help |
| D4-4 | D8's question | the host's `visibility.clusterAdminSar`, by a `SelfSubjectAccessReview` with the login's token: one definition of cluster administrator, no grant | a fixed question, or a review by a ServiceAccount, which needs a grant |
| D4-5 | D8's place | before the token read: a no reads nothing, and refuses a namespace `admin` of `group-sync-operator` | after the read: the token is already in hand |
| D4-6 | retries | none (`ONE_TRY`): a person is waiting, and the next press is the retry | the fleet's five attempts: a minute and a half behind a 30 s router timeout |
| D4-7 | where the gate lives | the poller's in-memory `CredentialGate`, per pod. **The exposure:** after a failure, a press on a restarted pod or another replica can send the password once more (2 at worst), and so can a proxy replaying a successful press to a second pod | a durable account hold keyed by the username, with no password fingerprint (Codex C2, Grok C2): it exists, and was declined by the operator for its operating cost — any failure would block that account's Rejoin on every pod until someone deleted the hold by hand, even after the right password |
| D4-8 | what the gate records | every bound failure (401, 500, a timeout after the write, a 302 without a token), as #315 | only a 401: a locked account's 500 would be walked further |
| D4-9 | the fleet account typed in | refused by name, casefolded, against the stripped and casefolded names of the chart's `fleetAccount.username`, every `ldapConnectionBootstrap` and every `lookup-account`; the shared grammar (`fullmatch` since #438) refuses a final newline | allowed: a person's retries would walk the account every cluster uses |
| D4-10 | the provenance | `token-source: rejoin`, `rejoined-by`, `rejoin-account`, `rejoined-at`; no `lookup-account` (§3.5) | `lookup-account` for the person: the ping reads it |
| D4-11 | the body | exactly `{username, password}`, strings, refused in fixed words; `body: Any`, so FastAPI never echoes it | a typed body: its 422 quotes the password |
| D4-12 | concurrency | one Rejoin per process, `409` for the second, never queued: the gate's check and the login are then one step | per cluster: two clusters could both send one wrong password |
| D4-13 | the Add form's `oauth` choice | unchanged, still refused: joining a new cluster by password is not this issue | build it here: a larger change with its own design |
| D4-14 | the dialog's autofill | `autocomplete="off"`, which asks the browser not to remember the fields; the dialog says a password manager may ignore it | the mockup's `username`/`current-password`: invites saving a remote's password |
| D4-15 | the answer's shape | `200 {outcome, message, at}` for every Rejoin that reached step 8, `rejoin-failed` included; HTTP errors before it | HTTP 4xx/5xx for the remote's refusals: the page could not tell them from the dashboard's |
| D4-16 | `rejoinable` on each row | served by the route's own rule | the page computing it: two copies of one rule |
| D4-17 | the log lines | #283's login lines with `rejoin_by=`; `cluster-rejoin-review` for D8 ("we log the response"); then `cluster-rejoined` or `cluster-rejoin-failed` | new names for the login lines: breaks #283's pinned vocabulary |
| D4-18 | the lab walk's administrator | a named person with a disposable `cluster-admin` binding (Appendix D): `kubeadmin` is never a Logins row | `kubeadmin`: the Logins check fails by design |

## 5. What must not change

| must not change | held by |
|---|---|
| Refresh (#434) | `gsd/clusterconfig/writer.py#refresh` and its route are untouched; `tests/test_cluster_refresh.py` passes unchanged. One UI assertion changes, as SPEC_D3 §4 anticipated: on `auth_failed` the line now names Rejoin |
| the credential gate | `gsd/fleetlookup.py#CredentialGate` is untouched; Rejoin calls `account_refusal` and `refuse`, as the lookup does |
| Epic C's ping and self-login | `gsd/poller.py`, `gsd/selflogin.py` and `gsd/fleetstate.py` are untouched; their tests pass unchanged |
| the lookup | `store` and `store_lookup` write the lookup's values byte for byte when `rejoin` is empty; `FleetLogin`'s fleet wording is byte-identical (Appendix C) |
| the dashboard ServiceAccount's permissions | no template changes; the rendered RBAC is identical in all eight renders (Appendix C) |
| every other feature | Rotate, Delete, Test, the Add form and its `oauth` refusal are untouched; nothing is removed, narrowed or deprecated |
| the other writes' fetch | `apiSend` keeps `redirect: "follow"` for every call but Rejoin's |

## 6. What is left, stated

1. **The gate's scope** (§2, D4-7): a restart, another replica or a replayed press can send a password once more.
2. **A transient 500 holds a correct password back** in that pod until it restarts: a 500 cannot be told from a
   locked account (the operator's ruling on #325). A new password works at once; the runbook says so.
3. **Directory aliases and spellings.** One directory entry known by two names (a `uid` and a `mail`) is not
   recognised as the fleet account under its other name (SPEC_S4d's residual). The gate compares the username as
   typed (#315's rule), so another capitalisation of the same wrong password is a new try, as a different password is.
4. **A failed revoke leaves a full-scope token.** The answer and the `fleet-logout-failed` line name it; nothing
   sweeps it (`CLUSTER_CREDENTIALS.md` §6, point 3).
5. **The login lines keep #283's names** (`fleet-login…`), pinned by `tests/test_fleet_login.py`; each carries
   `rejoin_by=` and the person's `account=`.
6. **An identity provider without password challenges** (OpenID Connect, GitHub, Google) cannot be rejoined.
7. **The browser's resend** of a written request is not guarded beyond the lock and the gate (§2).
8. **A password manager** may still offer to save what is typed (§3.6).
9. **Arbitrary encodings of an echo.** The scrub covers accidental echoes: §3.7's covered set, up to two layers.
   Three layers, other encoders' optional escapes, base64 or any other encoding a hostile remote may choose are not
   recognised; the remote holds the password already. `test_other_json_spellings_never_reach_evidence[triple-…]` records three
   layers as an expected failure (`xfail`, strict), on all five paths.

## 7. The change, file by file

| file | change | added | removed |
|---|---|---|---|
| `local-development/gsd/rejoin.py` | new: `_spellings`, `_scrub`, `RejoinLogin`, `refusal`, `fleet_accounts`, `check`, `question`, `question_words`, `_ReviewClient`, `remote_says_cluster_admin`, `rejoin`, `_exchange`, `stopped_unexpectedly` | +323 | −0 |
| `local-development/gsd/fleetlogin.py` | `FleetLogin.REFUSED_ACTION` and `FleetLogin.NEXT_TRY`: the refusal and next-try words as class attributes, byte-identical for the fleet | +11 | −8 |
| `local-development/gsd/clusterconfig/writer.py` | `TOKEN_SOURCE_REJOIN`, the three Rejoin annotations, `owned_by_mode`, `CreateRequest.rejoin`; `store_lookup` takes `rejoin` | +36 | −8 |
| `local-development/gsd/clusterconfig/reader.py` | the "ours" rule through `owned_by_mode` | +2 | −3 |
| `local-development/gsd/clusterconfig/registry.py` | the merge through `owned_by_mode` | +4 | −2 |
| `local-development/gsd/fleetlookup.py` | `store` takes `rejoin` | +10 | −8 |
| `local-development/gsd/api.py` | the route `rejoin_cluster_config`, its one-at-a-time lock and its catch for the unexpected; `rejoinable` on each live row | +48 | −1 |
| `local-development/gsd/static/index.html` | the dialog; the card's Rejoin button and line; the Refresh line's next step; `openRejoin`, `closeRejoin`, `clearRejoin`, `sendRejoin`; `apiSend`'s `redirect` argument; the `pagehide` listener; `idleExpire` closes the dialog | +120 | −5 |
| `local-development/gsd/static/app.css` | the dialog's width and its gates list | +6 | −0 |
| `local-development/tests/test_cluster_rejoin.py` | new: Appendix C | +758 | −0 |
| `local-development/tests/test_api_contract.py` | the carve-out gains the route | +3 | −2 |
| `local-development/tests/test_clusterconfig.py` | the pinned row gains `rejoinable` | +1 | −1 |
| `local-development/tests/test_ui.py` | Refresh's `auth_failed` assertion names Rejoin; three Rejoin tests | +160 | −2 |
| `charts/group-sync-dashboard/RUNBOOK.md` | new: Appendix B | +162 | −0 |
| `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md` | §4 names Rejoin; §5 describes it and links the runbook; its rules, with the gate's scope and what is stored | +25 | −12 |
| `charts/group-sync-dashboard/README.md` | links the runbook | +2 | −1 |
| `charts/group-sync-dashboard/values.yaml` | the `clusterAdminSar` comment: the remote asks the same question (a comment only) | +2 | −1 |
| `docs/README.md` | lists the runbook | +1 | −0 |
| `local-development/API.md` | `rejoinable`; the route; six write routes | +30 | −2 |
| `docs/DESIGN_remote_cluster_access.md` | D7 built, D8 directed and built; §7's text and twin | +17 | −16 |
| `docs/diagrams/remote-cluster-access/source.html` | Figure 4 and the D8 card drawn as built | +14 | −13 |
| `docs/specs/SPEC_D3_cluster_refresh.md` | a note: #316 builds the next step §4 names | +4 | −0 |
| `docs/CHANGELOG.md` | the `## Unreleased` entry | +15 | −0 |
| **total** | 23 files | **+1754** | **−85** |

Measured with `git diff --numstat` on the tree the blocks produce. Two steps the blocks cannot carry, both in the
implementing commit:

1. **The figure's PNGs.** Render with the command below, from the repository root. Commit only
   `joining-a-cluster.light.png` and `joining-a-cluster.dark.png`, and restore the other six (renderer noise).
2. **The release commit's versions** (orchestrator's notes).

The render command (`render.py` needs all four figure names):

    local-development/.venv/bin/python docs/diagrams/render.py docs/diagrams/remote-cluster-access/source.html \
      docs/diagrams/remote-cluster-access \
      policies-who-decides,inherit-vs-remote-sar-outcomes,remote-sar-decision-flow,joining-a-cluster

## Appendix A. Research and measurements

### A.1 The login, and what it leaves behind

**`oc login -u … -p …` is one GET on the remote's OAuth server with Basic auth. It leaves one `OAuthAccessToken`, a
full-scope token for that person, which must be revoked.**

| source | what it says or shows |
|---|---|
| openshift-docs `270ee60`, modules/oauth-token-requests.adoc | lines 22-23: `openshift-challenging-client` "Requests tokens with a user-agent that can handle `WWW-Authenticate` challenges". Lines 37-44: every token request goes to `/oauth/authorize`. Lines 56-60: Basic challenges need a non-empty `X-CSRF-Token`. Lines 62-66: a provider without challenges needs a browser |
| SPEC_S4a §2 (measured 2026-09-21) | the authorize GET is answered by a 302 whose `Location` fragment carries the token; its object is `sha256~` + base64url(sha256(the rest)); `DELETE …/useroauthaccesstokens/<name>` with the token as bearer answers 200 |
| the lab, read-only, 2026-09-27 | `oauthclients/openshift-challenging-client`: `grantMethod: auto`, `respondWithChallenges: true`. `oauths/cluster`: `accessTokenMaxAgeSeconds: 31536000`; providers `developer` (HTPasswd) and `ldap-local` (LDAP). All 30 challenging-client tokens carry `scopes: [user:full]` and `expiresIn: 31536000` (counted at 17:43Z) |
| OKD 4.20, "Managing user-owned OAuth access tokens" | `oc get useroauthaccesstokens` lists your own; `oc delete useroauthaccesstokens <name>` deletes one; "Token names are not sensitive and cannot be used to log in" |
| the lab's RBAC | `system:openshift:useroauthaccesstoken-manager` is bound to `system:authenticated:oauth`: any person may list and delete their own tokens |

### A.2 How the person's login reads the poller's token Secret

- `gsd/fleetlookup.py#read_sa_token` (fleetlookup.py:272-339) GETs
  `group-sync-operator/group-sync-dashboard-cluster-poller-token` with the session as bearer. It checks the type, the
  owner annotation and the legacy-token cleaner's `invalid-since` label, and decodes the token first, so every refusal
  carries it as a secret to scrub.
- The lab, read-only: the Secret exists, `type: kubernetes.io/service-account-token`, annotated
  `kubernetes.io/service-account.name: group-sync-dashboard-cluster-poller`, with `helm.sh/resource-policy: keep`.
- A cluster administrator may `get` it, and so may an `admin` of `group-sync-operator` who is not one
  (`docs/DESIGN_remote_cluster_access.md` §5). D8 is the stricter gate, and it runs first.

### A.3 D8: one SelfSubjectAccessReview, with the login's own token

| source | what it says or shows |
|---|---|
| kubernetes/website `ce7891d`, content/en/docs/reference/access-authn-authz/authorization.md | lines 403-405: `kubectl auth can-i` "uses the `SelfSubjectAccessReview` API". Lines 469-500: the answer is the object's `status` |
| kubernetes/kubernetes `6c1c770`, staging/src/k8s.io/api/authorization/v1/types.go | lines 56-58: "users should always be able to check whether they can perform an action". Lines 258-276: `status` carries `allowed`, `denied`, `reason`, `evaluationError` |
| the lab: who may ask | `create selfsubjectaccessreviews` reaches `system:authenticated` (`basic-users`, `self-access-reviewers`, `system:basic-user`): no grant needed |
| the lab: the exchange | asked `update clusterrolebindings.rbac.authorization.k8s.io`, answered `allowed: true` with an RBAC reason; `get` answers `MethodNotAllowed`: nothing kept |
| the lab: who passes | `oc adm policy who-can update clusterrolebindings.rbac.authorization.k8s.io`: `kubeadmin`, `system:cluster-admins`, `system:masters` and system ServiceAccounts |

The question is built as the host's `TierResolver` builds it (kube.py:1481-1495).

### A.4 Where the password could land: the sources

| place | source |
|---|---|
| a typed body's 422 | measured with FastAPI 0.141.1 and pydantic 2.13.5: a typed `dict` echoed `"input": "<the password>"` for a JSON string and a list; `Any` does not (also Grok C3, Codex C3) |
| a key equal to the password | measured on the implemented copy before the fix: `_reject_unknown` named the key in the 422 (Codex C3) |
| an unexpected error | Uvicorn 0.53.0 logs an exception that leaves the app with its traceback: `self.logger.error(msg, exc_info=exc)` in `run_asgi` (uvicorn/protocols/http/h11_impl.py lines 414-416); measured: before the fix the route answered 500, and before round 1's fix an error after the login existed lost how the login ended (4 cases) |
| a short password | `gsd/clusterconfig/events.py#redact` skips a secret shorter than `_MIN_SECRET` (4); measured before the fix: a three-character password in D8's reason or error reached the review and failure lines |
| a short password, JSON-escaped | `gsd/kube.py#redact_text` makes the escaped forms only for values of eight characters or more; measured before round 1's fix: `x"Z` and `éZ`, escaped once or twice, reached the review, failure, login and revoke lines and the answer (20 cases, Codex round 1) |
| other JSON spellings | measured before round 2's fix: `x\/Z` for `x/Z`, and `\u00E9Z` for `éZ`, reached the lines or the answer on all five paths (10 cases, Grok and Codex round 2) |
| Go's spelling | Go's `encoding/json.Marshal`, run on the Go runtime by Codex in round 3 (`go-spellings.json`: `x\u003cZ`, `é\u2028Z`, `x😀Z` as is, and each twice); measured before round 3's fix: 10 of its 12 rows reached the lines or the answer on all five paths (50 cases); the two left as is were already scrubbed |
| D8's cut | `ClusterClient._send` redacts through `kube.redact_text`, floor eight, then cuts the body at 200 characters (kube.py:666); measured before round 2's fix: a password straddling the cut, escaped or raw, left a fragment in the review's failure line and the answer (2 cases) |
| a refused read, then a failed revoke | measured before the fix: the token read reached `fleet-logout-failed` |
| the request logs | oauth-proxy's `-request-logging` (`values.yaml`, `requestLogging`) and Uvicorn's access format (uvicorn 0.53.0, config.py:94) write the request line only |
| the usage record | the activity middleware records the user and the email (api.py:939-942) |
| the audit logs | openshift-docs `270ee60`, modules/nodes-nodes-audit-config-about.adoc lines 35, 61-63: Metadata level, never headers |
| browser storage | index.html:16 and 82: only `gsd-mode` and `gsd-palette` |
| the back/forward cache | the page is served `Cache-Control: no-cache, must-revalidate`, not `no-store` (api.py:3231) |
| autofill | WHATWG HTML, "Autofilling form controls: the autocomplete attribute" and its processing model: `off` means "do not remember", and a user agent may still override it |

### A.5 Can one press run twice? Each layer

| layer | does it replay a POST it already sent? | source |
|---|---|---|
| the page | no: one request per press, the password field emptied as it leaves, redirects refused | §3.6, measured (Appendix C) |
| the browser (Chromium) | **yes, in one case**: a reused keep-alive connection that closes before any response header | chromium/src `71467d7`, net/http/http_network_transaction.cc lines 2103-2166 and 2331-2339 |
| the OpenShift router (HAProxy) | no: `retry-on` defaults to `conn-failure`, and the router's template sets none; a failed backend is answered 502 or 504 | HAProxy v2.8.0, doc/configuration.txt lines 375-400 and 11264-11344; openshift/router `6c5868c`, haproxy-config.template lines 164-170 and 652-693 |
| oauth-proxy (Go's `http.Transport`) | no: a written request is replayed only when idempotent or carrying `Idempotency-Key` | golang/go `2ff5743`, src/net/http/transport.go lines 836-881, request.go lines 1557-1571 |
| the app | no: one Rejoin per process, the second `409` | §3.1, measured |
| the login | no: `ONE_TRY` | §3.3, measured |

### A.6 The code reused, at `3cbc4e3`

| piece | where | reused as is, or changed |
|---|---|---|
| `FleetLogin` | fleetlogin.py:309-744 | reused: the flow, `policy=`, the revoke on exit (366-372), `add_secrets` (374-376). Its refusal and next-try words (718-744) speak to the fleet, so they become class attributes a subclass restates, byte-identical for the fleet |
| `CredentialGate` | fleetlookup.py:102-177 | reused: `account_refusal` (152) before the login, `refuse` (171) after a bound failure; never `spend` |
| `read_sa_token` | fleetlookup.py:272-339 | reused; its `action` names the fleet account, so Rejoin writes the person's sentence |
| `store`, `writer.store_lookup` | fleetlookup.py:360-391, writer.py:331-374 | changed: both take the Rejoin's provenance; the lookup's values are unchanged |
| the "ours" rule | reader.py:122-129, registry.py:99-102 | changed: through `writer.owned_by_mode` |
| the daily ping's targets | poller.py:1734-1739, 1827 | unchanged (§3.5 rule 1) |
| the Add form's `oauth` refusal | writer.py:182-183 | unchanged (D4-13) |
| the writes gate, the Refresh route's pattern | api.py:1180-1199, 1346-1368 | reused |
| `apiSend` | index.html, `apiSend` | gains a `redirect` argument, `"follow"` by default |
| the static dialog | index.html:132-146 (`#ns-preview`) | the pattern Rejoin's dialog follows |

### A.7 The review's measurements (2026-09-27)

- **A 307 in front of the dashboard forwards the password** (Chromium through Playwright 1.63.0, `probe_redirect.py`
  in the scratch record): a fetch POST answered 307 with `redirect: "follow"` re-sent `{"password":"Adm1n-pw"}` to the
  Location; with `redirect: "error"` nothing was sent there.
- **The four disclosures** each failed on the implemented copy before its fix and passed after: the cases named in
  Appendix C, and the mutants that revert each fix.
- **The shapes the reviewers measured** (Grok's `probe_c1_c4.py`, Codex's adversarial suite) are the new rows of §2,
  measured again by `test_the_budget_over_the_system`.

## Appendix B. The runbook

**`charts/group-sync-dashboard/RUNBOOK.md`, beside `values.yaml` and `CLUSTER_CREDENTIALS.md`: numbered operations,
each a command and what its answer looks like.** Its six sections are the ones the comment of 2026-09-23 lists:

| § | the operation | what it adds |
|---|---|---|
| 1 | decide whether the connection is broken: Refresh, and the log line | `auth_failed` and `pending` lead to Rejoin; `forbidden`, `unreachable` and `cert-verify-failed` do not |
| 2 | confirm the token on the remote | the stored token through your own remote context; `can-i update clusterrolebindings`; a live token Secret |
| 3 | Rejoin from the UI | who, what it asks, what it does, and how to confirm: the annotations, the lines, the remote's audit log |
| 4 | when Rejoin is not the answer | what each refusal means and what fixes it |
| 5 | the manual fallback | the two-cluster `oc create token` + `oc patch`, keeping the Secret's `tlsClientConfig` |
| 6 | what not to do | no repeated presses; the scope (a restarted pod or another replica can send once more); never the fleet account's password; after a lost answer, Refresh first, then delete your own leftover token |

`docs/README.md` lists it, and the chart's README and `CLUSTER_CREDENTIALS.md` link to it.

## Appendix C. Tests, before and after

**What was measured, and where.** Every count below is from `pytest` run from `local-development/` of the named tree,
with `PYTHONPATH` set to that tree (`gsd.__file__` printed with each run), `-p no:cacheprovider`,
`PYTHONDONTWRITEBYTECODE=1` and a `--basetemp` in the scratch directory. The remote is a fake (`httpx.MockTransport`);
the page runs in Chromium through Playwright; nothing touched a cluster.

| tree | what it is |
|---|---|
| **before** | the branch head (its code is `3cbc4e3`'s) plus Appendix E's blocks for the four test files only |
| **after** | the branch head with every block applied |
| **implemented, without a fix** | the after tree with one fix reverted: the review's red runs and the mutants |

**The new and changed tests.** "Before" is the first error each raised on the before tree, as measured; "after" is
the after tree.

| what it proves | test (`local-development/tests/…`) | before | after |
|---|---|---|---|
| the exchange: the wire in order, one authorize as the person, D8 with the login's token, the in-place write and its provenance, no `lookup-account`, the fleet password never read, the lines | `test_cluster_rejoin.py::test_a_secret_row_is_rejoined_in_place_with_the_persons_provenance` | `AssertionError` `{"detail":"Not Found"}`: no route | passed |
| a lookup-written Secret loses `lookup-account` and keeps `managed-by` | `…::test_a_lookup_written_secret_rejoined_drops_lookup_account_and_keeps_who_made_it` | `KeyError: 'outcome'` | passed |
| a pending `saTokenLookup` stanza: created with its policy, and counted as the stanza's own | `…::test_a_pending_satokenlookup_stanza_is_created_and_counted_as_the_lookups_own` | `AssertionError` `Not Found` | passed |
| the daily ping never presents the fleet password as the person who rejoined | `…::test_the_daily_ping_never_logs_in_as_the_person_who_rejoined` | `KeyError: 'outcome'` | passed |
| the body is `{username, password}` and nothing else, and no refusal echoes the password — a key equal to the password included (eight shapes) | `…::test_the_body_is_username_and_password_and_nothing_else` | ×8 `AssertionError` `Not Found` | ×8 passed |
| each refusal before the wire sends nothing and repeats no value: four rows, three username shapes (one the fleet name with a final newline), four fleet-account names (one recorded with a final newline), three password shapes | `…::test_each_refusal_before_the_wire_sends_nothing_and_repeats_no_value` | ×14 `AssertionError` `Not Found` | ×14 passed |
| below the cluster-admin tier, and without an identity: `403`, nothing sent | `…::test_below_the_cluster_admin_tier_is_403_and_nothing_is_sent` | `assert 404 == 403` | passed |
| an unknown or retired name: `404` naming it | `…::test_an_unknown_or_retired_name_is_404_and_nothing_is_sent` | `AssertionError` `Not Found` | passed |
| no poller, no gate, no login | `…::test_no_poller_means_no_gate_and_no_login` | `assert 404 == 409` | passed |
| writes off: the route does not exist | `…::test_with_the_writes_switch_off_the_route_does_not_exist` | passed: a guard, true both ways | passed |
| a bound failure (401, 500, a read timeout after the write) is one authorize; the same password is not sent again, to another cluster either; a different one is | `…::test_a_bound_failure_is_one_authorize_and_the_same_password_is_not_sent_again` | ×3 `KeyError: 'outcome'` | ×3 passed |
| a failure before the password is written: one request, no retry, not gated | `…::test_a_failure_before_the_password_is_written_is_tried_once_and_is_not_gated` | `KeyError: 'outcome'` | passed |
| D8's no: nothing read or written, the login revoked, the answer logged, the gate untouched | `…::test_the_remote_says_no_so_nothing_is_read_or_written_and_the_login_is_revoked` | `KeyError: 'outcome'` | passed |
| a review that does not answer (403, 500, no status, a string `"true"`, a timeout) is a refusal | `…::test_a_review_that_does_not_answer_is_a_refusal_never_a_yes` | ×5 `KeyError: 'outcome'` | ×5 passed |
| D8 asks the host's configured question | `…::test_the_review_asks_the_configured_cluster_admin_question` | `IndexError`: no review was asked | passed |
| a token read refusal (404, 403, invalidated) writes nothing and revokes the login | `…::test_a_token_read_refusal_writes_nothing_and_revokes_the_login` | ×3 `KeyError: 'outcome'` | ×3 passed |
| a refused write stores nothing and says so | `…::test_a_refused_write_stores_nothing_and_says_so` | `KeyError: 'outcome'` | passed |
| one Rejoin at a time in a process | `…::test_one_rejoin_at_a_time_in_this_process` | `AssertionError`: the first login never started | passed |
| the redaction pin, fourteen scenarios, a refused read followed by a failed revoke among them | `…::test_the_password_appears_on_one_header_and_nowhere_else` | ×14 `AssertionError` `Not Found` | ×14 passed |
| a three-character password echoed by D8 (allowed, denied, a 500) reaches no line | `…::test_short_password_echo_in_review_is_not_logged` | ×3 `assert 404 == 200` | ×3 passed |
| an unexpected error, inside the exchange and before a login exists: fixed words out, nothing of it logged, the login still revoked when there was one | `…::test_unexpected_exception_cannot_escape_with_secrets` | ×2 `ModuleNotFoundError: gsd.rejoin` | ×2 passed |
| a short password JSON-escaped once or twice (`x"Z`, `éZ`) in an allowed or denied review, a review 500, a login 500 or a revoke 500 reaches no line and no answer | `…::test_short_escaped_password_never_reaches_evidence` | ×20 `assert 404 == 200` | ×20 passed |
| an unexpected D8 or store error still says how the login ended, whether its revoke answered 200 or 500 | `…::test_unexpected_error_still_reports_cleanup` | ×4 `ModuleNotFoundError: gsd.rejoin` | ×4 passed |
| `x\/Z` for `x/Z`, `\u00E9Z` for `éZ`, and the Go runtime's twelve spellings, on all five paths, reach no line and no answer; three layers of escaping stay an expected failure (§6) | `…::test_other_json_spellings_never_reach_evidence` | ×70 `KeyError: 'message'`: no route; ×5 xfailed | ×70 passed; ×5 xfailed |
| a password straddling D8's 200-character cut, escaped or raw, leaves no fragment | `…::test_a_password_across_the_reviews_200_character_cut_leaves_no_fragment` | ×2 `KeyError: 'message'`: no route | ×2 passed |
| the dialog promises only what the dashboard controls, and states the gate's scope | `…::test_dialog_does_not_promise_to_control_password_managers` | `ValueError`: no dialog in the page | passed |
| the budget over the system (§2), twelve shapes | `…::test_the_budget_over_the_system` | `KeyError: 'outcome'` | passed |
| the runbook beside the values, six sections, linked | `…::test_the_runbook_sits_beside_the_values_with_six_sections_and_docs_links_it` | `FileNotFoundError` | passed |
| the carve-out, exact: six write routes | `test_api_contract.py::test_r6_the_only_writes_are_the_cluster_secret_routes_and_only_when_switched_on` | `AssertionError`: five routes | passed |
| the pinned row shape gains `rejoinable` | `test_clusterconfig.py::TestApi::test_the_payload_shape_the_tier_and_the_findings` | `AssertionError`: no `rejoinable` | passed |
| Refresh's `auth_failed` line names Rejoin and the card draws it | `test_ui.py::TestClusterConfigPage::test_refresh_shows_four_states_that_survive_a_repaint_with_one_probe_in_flight` | `AssertionError`: the line said "Rejoin (#316), not built yet" | passed |
| the dialog: offered only where accepted and only after a refused Refresh; static, outside `#main`; no form; survives a repaint; fits 375 px; Cancel and Escape clear it; absent with writes off | `…::test_rejoin_is_offered_after_a_refused_refresh_and_its_dialog_keeps_what_is_typed` | `TimeoutError`: no Rejoin button in 30 s | passed |
| one press, one request, the password once; emptied as it leaves; nothing in storage, the URL or `view`; `pagehide` and the idle sign-out clear it | `…::test_one_press_sends_the_password_once_and_the_page_keeps_it_nowhere` | `ModuleNotFoundError: gsd.rejoin` | passed |
| a 307 in front of the dashboard carries nothing on; one POST per press | `…::test_fetch_refuses_redirects_and_submits_once` | `TimeoutError`: no Rejoin button in 30 s | passed |

**The review's fixes, red and green on the implemented tree.** The before tree cannot show why a fix is needed,
because it has no route at all. So each fix was also measured on the implemented copy: its test failed without the
fix and passed with it, and the mutant that reverts it is caught.

| fix | the test's failure without the fix (measured) | mutant |
|---|---|---|
| (a) the shape refused in fixed words | `test_the_body_is_username_and_password_and_nothing_else[password-as-key]`: the 422 named the key, the password | caught |
| (b) the route's catch for the unexpected | `test_unexpected_exception_cannot_escape_with_secrets`: `assert 500 == 200`; since round 1 held by its `[RejoinLogin]` case, an error before a login exists | caught |
| (c) D8's text scrubbed at any length | `test_short_password_echo_in_review_is_not_logged[allowed, denied, review-500]`: `xyZ` in the review and failure lines | caught, one mutant per line (c1, c2) |
| (d) the refused read's secrets handed to the login | `test_the_password_appears_on_one_header_and_nowhere_else[read-refused-revoke-500]`: the token read in `fleet-logout-failed` | caught |
| (e) `redirect: "error"` | `test_fetch_refuses_redirects_and_submits_once`: "the 307 carried the password on" | caught |
| the honest dialog words | `test_dialog_does_not_promise_to_control_password_managers`: `password managers may ignore` absent | — |
| (P1) every spelling scrubbed, at any length (round 1) | `test_short_escaped_password_never_reaches_evidence`: 20 of 20 failed, the escaped password in the review, failure, login or revoke line or in the answer | caught, one mutant per part (P1a, P1b) |
| (P2) `rejoin`'s boundary keeps how the login ended (round 1) | `test_unexpected_error_still_reports_cleanup`: 4 of 4 failed, the answer said only to press Refresh | caught |
| (R2a) D8's client scrubs before its cut (round 2) | `test_a_password_across_the_reviews_200_character_cut_leaves_no_fragment`: 2 of 2 failed, the fragment in the failure line and the answer | caught |
| (R2b) `\/` and upper-case hex among the spellings (round 2) | `test_other_json_spellings_never_reach_evidence`: 10 of 10 failed, the spelling in a line or the answer; the triple escape failed 5 of 5, as expected | caught |
| (R3) Go's spelling (round 3) | `test_other_json_spellings_never_reach_evidence[go-…]`: 50 of 60 failed, the Go spelling in a line or the answer; the 10 emoji cases passed before, Go writing them as is | caught |

**The totals.**

| run | before | after |
|---|---|---|
| the new and changed tests alone | `169 failed, 84 passed, 5 xfailed in 82.88s`: the 84 are those files' other cases and the writes-off guard | `253 passed, 5 xfailed in 12.94s` |
| the Rejoin test file alone, `tests/test_cluster_rejoin.py` | — | `164 passed, 5 xfailed` |
| the whole suite, `pytest tests/ -q --deselect tests/test_live_smoke.py`, browser tests included | `169 failed, 6173 passed, 28 skipped, 4 deselected, 5 xfailed in 568.25s` | `6358 passed, 19 skipped, 4 deselected, 5 xfailed in 497.92s` |

The whole before-suite fails exactly the 169 of the table: the two lists of `FAILED` lines compare equal. The five
expected failures are the triple escape on both trees (§6). The after tree collects seven cases more, each
parametrized over something the other blocks add: `rejoin.py` in three module scans, `RUNBOOK.md` in the fence check,
and three citations the documents gain. The before tree skips nine citations more: this spec cites `gsd/rejoin.py`
nine times, and the before tree lacks the file. Both trees carried this spec;
both differences were measured, by diffing the two trees' `--collect-only` lists and the citation test's skip
reasons.

**The blocks.** On a clean clone of the branch head, `apply-spec-blocks.py` reports "70 blocks check out across 23 files",
and the applied tree equals the implemented copy byte for byte in all 23 files.

**Every design decision and every fix is held by a test.** Each was reverted in its own copy of the implemented tree
and its tests run against the mutant: all twenty-five were caught.

| reverted | caught by |
|---|---|
| the person written into `lookup-account`, under the lookup's `token-source` | `test_the_daily_ping_never_logs_in_as_the_person_who_rejoined` |
| a Rejoin over a `saTokenLookup` stanza counted as a shadow | `test_a_pending_satokenlookup_stanza_is_created_and_counted_as_the_lookups_own` |
| the fleet's five attempts instead of `ONE_TRY` | `test_a_failure_before_the_password_is_written_is_tried_once_and_is_not_gated` |
| the gate not asked before the login | `test_a_bound_failure_is_one_authorize_and_the_same_password_is_not_sent_again[401]` |
| a bound failure not written to the gate | the same |
| D8 not asked | `test_the_remote_says_no_so_nothing_is_read_or_written_and_the_login_is_revoked` |
| a typed body | `test_the_body_is_username_and_password_and_nothing_else[string]` |
| no one-at-a-time lock | `test_one_rejoin_at_a_time_in_this_process` |
| a fleet account's name accepted | `test_each_refusal_before_the_wire_sends_nothing_and_repeats_no_value[…SVC-GSD-Fleet…]` |
| the fleet names compared unstripped | `test_each_refusal_before_the_wire_sends_nothing_and_repeats_no_value[…padded-account…]` |
| (a) an unknown key named in the 422 | `test_the_body_is_username_and_password_and_nothing_else[password-as-key]` |
| (b) an unexpected error leaves the route | `test_unexpected_exception_cannot_escape_with_secrets[RejoinLogin]` |
| (c1) D8's reason logged as the remote wrote it | `test_short_password_echo_in_review_is_not_logged[allowed]` |
| (c2) a failure's evidence logged as the remote wrote it | `test_short_password_echo_in_review_is_not_logged[denied]` |
| (d) a refused read's token not handed to the login | `test_the_password_appears_on_one_header_and_nowhere_else[read-refused-revoke-500]` |
| (e) the credential fetch follows redirects | `test_fetch_refuses_redirects_and_submits_once` |
| (P1a) the login's own remote text scrubbed by the fleet's scrub alone | `test_short_escaped_password_never_reaches_evidence[…login-500]` |
| (P1b) the escaped spellings not handed to the scrub | `test_short_escaped_password_never_reaches_evidence[…allowed]` |
| (P2) no boundary in `rejoin`: the route's fallback answers | `test_unexpected_error_still_reports_cleanup` |
| (R2a) D8's client redacts only as the shared client does, then cuts | `test_a_password_across_the_reviews_200_character_cut_leaves_no_fragment[escaped]` |
| (R2b) no `\/` and no upper-case hex spellings | `test_other_json_spellings_never_reach_evidence[slash-allowed]` |
| (R3) no Go spelling | `test_other_json_spellings_never_reach_evidence[go-lt-once-allowed]` |
| the token read not handed to the login's scrub | `test_the_password_appears_on_one_header_and_nowhere_else[revoke-500]` |
| the password field kept after the press | `test_one_press_sends_the_password_once_and_the_page_keeps_it_nowhere` |
| no clearing on `pagehide` | the same |

**RBAC.** Rendered from the branch head and from the after tree, for the default values, `environments/crc.yaml`,
`environments/example-production.yaml` and `charts/group-sync-dashboard/example-production.yaml`, each with leader
election on and off: REMOVED 0, ADDED 0 in all eight (63 to 73 atoms each).

**`FleetLogin`'s fleet words are byte-identical.** One driver emits its three caller-facing texts (a refusal, a
terminal answer, a give-up after five attempts) against the branch head and against the after tree: seven lines, 855 bytes
each, and `cmp` finds them equal.

**Not measured:** the browser's resend of a written request (§2); a real back/forward restore; what a password manager
does with the dialog; the lab walk (Appendix D).

## Appendix D. On the lab, for the implementing pull request

**Break a throwaway entry, repair it with Rejoin as a named person, and prove the budget on the lab's own audit log.
`shared-qa` is never touched, and nobody logs in as the fleet account.**

The walk runs on the deployed PR head (`local-development/release-crc.sh`). Record the `group-sync-dashboard-data` and
`-report-artifacts` PVC UIDs before and after.

0. **Baseline, read-only.** `gsd-cluster-shared-qa`'s `resourceVersion`; the fleet account's Lease as JSON and its
   `openshift-challenging-client` token count (2 on 2026-09-27); the walker's own token count; the start instant for
   the oauth-server audit log.
1. **The walker.** `kubeadmin` is the only person who passes D8 on the lab today, and its logins are never a Logins row
   (`gsd/auditlog.py#SYSTEM_NAMES`). So a named person gets a disposable binding, removed in step 7:
   `oc create clusterrolebinding rejoin-walk-cluster-admin --clusterrole=cluster-admin --user=<walker>` (D4-18). No
   fleet path may name the walker (D4-9).
2. **The throwaway entry.** On the Add form, `rejoin-walk` at `https://api.crc.testing:6443`, trusted bundle, with a
   deliberately wrong token of eight or more characters. The card polls `auth_failed`.
3. **Refresh, then Rejoin.** Refresh answers `auth_failed`, and the card offers **Rejoin…**. Rejoin as the walker.
   Expect `rejoined`; Refresh then answers `connected`.
4. **The evidence.** The Secret's annotations (`token-source: rejoin`, `rejoined-by`, `rejoin-account`,
   `rejoined-at`, no `lookup-account`); the lines `fleet-login … rejoin_by=…`, then `cluster-rejoin-review …
   allowed=true` naming the ClusterRoleBinding `rejoin-walk-cluster-admin`, then `cluster-rejoined … revoked=true`;
   the walker's `cli` login on the Logins tab; the walker's token count back to step 0's.
5. **One wrong password, twice, on one pod.** `login-refused`, one `deny` in the audit log; the same wrong password
   again: `login-refused`, "so it was not sent", and **zero** new authorize in the audit log.
6. **The remote's no.** Remove the binding and Rejoin with the right password: `not-cluster-admin`,
   `allowed=false` in the log, the Secret's `resourceVersion` unchanged, the walker's token count unchanged.
7. **The end.** Delete `rejoin-walk` and the binding. `gsd-cluster-shared-qa`'s `resourceVersion` equals step 0's;
   the fleet account's token count is still 2, its audit-log authorizes 0 since step 0, and its Lease unchanged; the
   PVC UIDs are unchanged.

The evidence, with screenshots, goes under `reports/<date>_<slug>/`, pinned to the merge sha, and on #316 against its
Definition of Done.

## Appendix E. Implementation blocks

**Seventy blocks over twenty-three files, in apply order: the code, the tests, then the documents.** This spec's
Status and its index row move to `merged` by hand in the implementing commit, beside the applied blocks — a block
cannot, because its Old text would also match inside its own fence — so that `local-development/prepare-release.py`
promotes them. The PNGs and the versions are the two steps in §7.

<!-- block: local-development/gsd/fleetlogin.py | edit -->
```python
    entering it twice is refused.
    """

```

```python
    entering it twice is refused.
    """

    #: What a refusal line tells its reader to do, and when the next try comes: the fleet account's words. A person's
    #: own login (Rejoin, SPEC_D4) states its own (`gsd/rejoin.py#RejoinLogin`); the events and every rule are these.
    REFUSED_ACTION = ("rotate the fleet password Secret or correct ldapConnectionBootstrap — no second attempt is made, "
                      "because a retry is the lockout walk against the account the target authenticates every user with")
    NEXT_TRY = "the next lookup or ping"

```

<!-- block: local-development/gsd/fleetlogin.py | edit -->
```python
                    action=(f"the target refused the password for {self.username}: rotate the fleet "
                            f"password Secret or correct ldapConnectionBootstrap — no second attempt is "
                            f"made, because a retry is the lockout walk against the account the target "
                            f"authenticates every user with"),
```

```python
                    action=f"the target refused the password for {self.username}: {self.REFUSED_ACTION}",
```

<!-- block: local-development/gsd/fleetlogin.py | edit -->
```python
            action = "not retried: fix what detail names before the next lookup or ping"
        elif gave_up:
            action = (f"gave up after {ceiling} attempts: nothing more is tried until the next lookup or "
                      f"ping — check the API URL, the OAuth route and TLS trust for the OAuth host "
                      f"(the INGRESS CA, which the API's bundle may not carry) from this pod")
```

```python
            action = f"not retried: fix what detail names before {self.NEXT_TRY}"
        elif gave_up:
            action = (f"gave up after {ceiling} attempts: nothing more is tried until {self.NEXT_TRY} — check the "
                      f"API URL, the OAuth route and TLS trust for the OAuth host (the INGRESS CA, which the API's "
                      f"bundle may not carry) from this pod")
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
TOKEN_SOURCE_SELF_LOGIN = CREDENTIAL_SELF_LOGIN  # userSelfLogin
```

```python
TOKEN_SOURCE_SELF_LOGIN = CREDENTIAL_SELF_LOGIN  # userSelfLogin
#: Rejoin (#316, SPEC_D4): the lookup's read, started by a person with their own login. The one `token-source` that
#: is not a mode's word, because no declaration resolves to it; `owned_by_mode` says which stanza it may serve.
TOKEN_SOURCE_REJOIN = "rejoin"
#: Who pressed Rejoin (the host identity), the account the remote authenticated, and when. Never `lookup-account`:
#: the daily ping logs in as whatever account that annotation names, with the fleet password (#432).
REJOINED_BY_ANNOTATION = "groupsync-dashboard.io/rejoined-by"
REJOIN_ACCOUNT_ANNOTATION = "groupsync-dashboard.io/rejoin-account"
REJOINED_AT_ANNOTATION = "groupsync-dashboard.io/rejoined-at"
REJOIN_ANNOTATIONS = (REJOINED_BY_ANNOTATION, REJOIN_ACCOUNT_ANNOTATION, REJOINED_AT_ANNOTATION)
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
    onboarding: tuple[str, str, str] = ()
```

```python
    onboarding: tuple[str, str, str] = ()
    #: (who pressed Rejoin, the account, the instant) — REJOIN_ANNOTATIONS, in that order (SPEC_D4).
    rejoin: tuple[str, str, str] = ()
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python

def secret_object(req: CreateRequest, namespace: str, *, redact: bool = False) -> dict:
```

```python

def owned_by_mode(token_source: str | None, mode: str | None) -> bool:
    """Whether a Secret with this `token-source` is the retriever's own write for a values stanza whose mode resolves
    to `mode` (SPEC_S4 §1, SPEC_D2b §3.4): the mode's own word, or a Rejoin over a `saTokenLookup` stanza, which read
    the same token Secret the lookup reads (SPEC_D4). Such a Secret serves the stanza's policy and is no shadow."""
    if mode is None:
        return False
    return token_source == mode or (mode == TOKEN_SOURCE_LOOKUP and token_source == TOKEN_SOURCE_REJOIN)


def secret_object(req: CreateRequest, namespace: str, *, redact: bool = False) -> dict:
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
                                CONNECTION_HASH_ANNOTATION), req.onboarding))
```

```python
                                CONNECTION_HASH_ANNOTATION), req.onboarding))
    if req.rejoin:
        annotations.update(zip(REJOIN_ANNOTATIONS, req.rejoin))
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
                 source_namespace: str, source_service_account: str, lookup_account: str) -> None:
    """SPEC_S4b: a Secret that DECLARED `saTokenLookup` becomes the credential it asked for, in place.
```

```python
                 source_namespace: str, source_service_account: str, lookup_account: str | None,
                 rejoin: tuple[str, str, str] = ()) -> None:
    """SPEC_S4b: a Secret that DECLARED `saTokenLookup` becomes the credential it asked for, in place.
    With `rejoin` (SPEC_D4) it is a person's Rejoin of any Secret row: the same write, the person's provenance.
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
        meta["annotations"] = {**(meta.get("annotations") or {}),
                               TOKEN_SOURCE_ANNOTATION: TOKEN_SOURCE_LOOKUP,
                               SOURCE_NAMESPACE_ANNOTATION: source_namespace,
                               SOURCE_SERVICE_ACCOUNT_ANNOTATION: source_service_account,
                               LOOKUP_ACCOUNT_ANNOTATION: lookup_account}
```

```python
        # ONE PATH'S PROVENANCE REPLACES THE OTHER'S (SPEC_D4): a Rejoin leaves no `lookup-account`, which the daily
        # ping would log in as with the fleet password (#432), and a lookup leaves no stale Rejoin behind.
        stale = (LOOKUP_ACCOUNT_ANNOTATION,) if rejoin else REJOIN_ANNOTATIONS
        provenance = dict(zip(REJOIN_ANNOTATIONS, rejoin)) if rejoin else {LOOKUP_ACCOUNT_ANNOTATION: lookup_account}
        meta["annotations"] = {**{k: v for k, v in (meta.get("annotations") or {}).items() if k not in stale},
                               TOKEN_SOURCE_ANNOTATION: TOKEN_SOURCE_REJOIN if rejoin else TOKEN_SOURCE_LOOKUP,
                               SOURCE_NAMESPACE_ANNOTATION: source_namespace,
                               SOURCE_SERVICE_ACCOUNT_ANNOTATION: source_service_account, **provenance}
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
          by=MANAGED_BY_LOOKUP, secrets=(token,))
```

```python
          by=rejoin[0] if rejoin else MANAGED_BY_LOOKUP, secrets=(token,))
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
           "LOOKUP_ACCOUNT_ANNOTATION", "TOKEN_SOURCE_LOOKUP", "TOKEN_SOURCE_SELF_LOGIN",
           "TLS_MODES", "OAUTH_NOT_BUILT", "secret_object", "secret_name_for", "validate", "create", "rotate",
```

```python
           "LOOKUP_ACCOUNT_ANNOTATION", "TOKEN_SOURCE_LOOKUP", "TOKEN_SOURCE_SELF_LOGIN", "TOKEN_SOURCE_REJOIN",
           "REJOIN_ANNOTATIONS", "TLS_MODES", "OAUTH_NOT_BUILT", "secret_object", "secret_name_for", "owned_by_mode",
           "validate", "create", "rotate",
```

<!-- block: local-development/gsd/clusterconfig/reader.py | edit -->
```python
from .writer import LOOKUP_ACCOUNT_ANNOTATION, TOKEN_SOURCE_ANNOTATION
```

```python
from .writer import LOOKUP_ACCOUNT_ANNOTATION, TOKEN_SOURCE_ANNOTATION, owned_by_mode
```

<!-- block: local-development/gsd/clusterconfig/reader.py | edit -->
```python
            ours = (values_modes or {}).get(parsed.name) is not None \
                and token_source.get(secret_name) == (values_modes or {}).get(parsed.name)
```

```python
            ours = owned_by_mode(token_source.get(secret_name), (values_modes or {}).get(parsed.name))
```

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->
```python
from .parser import Finding
```

```python
from .parser import Finding
from .writer import owned_by_mode
```

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->
```python
        (its token-source is that stanza's credential kind — the reader's "ours") keeps the credential and takes
```

```python
        (its token-source is that stanza's credential kind, or a Rejoin's over a lookup stanza — the reader's "ours",
        `gsd/clusterconfig/writer.py#owned_by_mode`) keeps the credential and takes
```

<!-- block: local-development/gsd/clusterconfig/registry.py | edit -->
```python
            elif c.connection_mode is not None and found.token_source == c.credential_kind:
```

```python
            elif c.connection_mode is not None and owned_by_mode(found.token_source, c.credential_kind):
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
    MANAGED_BY_LOOKUP, MANAGED_BY_ONBOARD, TOKEN_SOURCE_LOOKUP, CreateRequest, WriteFailed, WriteRefused, create, secret_name_for,
    store_lookup,
```

```python
    MANAGED_BY_LOOKUP, MANAGED_BY_ONBOARD, MANAGED_BY_UI, TOKEN_SOURCE_LOOKUP, TOKEN_SOURCE_REJOIN, CreateRequest, WriteFailed,
    WriteRefused, create, secret_name_for, store_lookup,
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
          sa_token: SaToken, *, account: str) -> str:
    """Write the credential where the declaration says (SPEC_S4 §1): a values stanza gets a new
    `gsd-cluster-<name>` through `writer.create`; a declaring Secret is updated in place through
    `writer.store_lookup`. Returns `created` or `updated`."""
    provenance = dict(source_namespace=sa_token.namespace, source_service_account=sa_token.service_account,
                      lookup_account=account)
```

```python
          sa_token: SaToken, *, account: str, rejoin: tuple[str, str, str] = ()) -> str:
    """Write the credential where the declaration says (SPEC_S4 §1): a values stanza gets a new
    `gsd-cluster-<name>` through `writer.create`; a declaring Secret is updated in place through
    `writer.store_lookup`. Returns `created` or `updated`. `rejoin` is (who pressed, the account, the
    instant) for a person's Rejoin (SPEC_D4): the same write, with the person's provenance."""
    provenance = dict(source_namespace=sa_token.namespace, source_service_account=sa_token.service_account,
                      lookup_account=None if rejoin else account, rejoin=rejoin)
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
        req = CreateRequest(name=cluster.name, server=cluster.api_url, credential_kind="bearerToken",
                            token=sa_token.token, tls_mode=tls_mode, ca_data=ca_data,
                            visibility=visibility, identity=identity, enabled=cluster.enabled,
                            managed_by=MANAGED_BY_ONBOARD if cluster.onboarding else MANAGED_BY_LOOKUP,
                            onboarding=cluster.onboarding, token_source=TOKEN_SOURCE_LOOKUP, **provenance)
```

```python
        managed_by = MANAGED_BY_UI if rejoin else MANAGED_BY_ONBOARD if cluster.onboarding else MANAGED_BY_LOOKUP
        req = CreateRequest(name=cluster.name, server=cluster.api_url, credential_kind="bearerToken",
                            token=sa_token.token, tls_mode=tls_mode, ca_data=ca_data,
                            visibility=visibility, identity=identity, enabled=cluster.enabled,
                            managed_by=managed_by, onboarding=cluster.onboarding,
                            token_source=TOKEN_SOURCE_REJOIN if rejoin else TOKEN_SOURCE_LOOKUP, **provenance)
```

<!-- block: local-development/gsd/fleetlookup.py | edit -->
```python
               viewer=MANAGED_BY_LOOKUP)
```

```python
               viewer=rejoin[0] if rejoin else MANAGED_BY_LOOKUP)
```

<!-- block: local-development/gsd/rejoin.py | create -->
```python
"""Rejoin (#316, SPEC_D4): a cluster administrator signs in to a remote cluster as themselves, once; the dashboard
reads the poller's token there, writes it here, and forgets the password.

The exchange is the lookup's, started by a person: `RejoinLogin` (#283's login), D8's one question, #284's
`read_sa_token`, the revoke on every exit, and #284's `store` with the person's provenance. What keeps the
password safe, in the order it runs:
  1. the route's host gate (the cluster-admin tier, #322), then `check`: a rejoinable row, a valid username, and
     never a fleet account;
  2. `ONE_TRY`: one authorize per press, and nothing retried;
  3. the poller's `CredentialGate` (#315): a password the directory REFUSED for this exact username is not sent
     again BY THIS POD. A success is not held: two right presses send twice. The gate lives in memory; a durable
     account hold was declined for its operating cost (SPEC_D4, D4-7);
  4. D8: the remote says whether the person is its cluster administrator, and a no reads and writes nothing;
  5. every answer and line is scrubbed of the password, its Basic form, the login's token and the token read.
"""

from __future__ import annotations

import base64
import dataclasses
import json
import logging
import re

from .clusterconfig.events import event, failure
from .clusterconfig.writer import WriteRefused, secret_name_for
from .config import CREDENTIAL_SELF_LOGIN, ClusterConfig, Settings, valid_bootstrap_username
from .fleetlogin import TOKEN_PREFIX, FleetLogin, LoginError, RetryPolicy, _without_userinfo
from .fleetlookup import CredentialGate, LookupRefused, LookupSource, read_sa_token, store
from .fleetlookup import _scrub as _fleet_scrub
from .kube import AUTH_FAILED, UNREACHABLE, ClusterClient, ClusterError
from .timeutil import now_iso

log = logging.getLogger(__name__)

#: The success word. Every other outcome is a refusal's code: the lookup's (`gsd/fleetlookup.py#CODES`) or these three.
REJOINED = "rejoined"
NOT_CLUSTER_ADMIN = "not-cluster-admin"
REVIEW_FAILED = "access-review-failed"
STOPPED = "rejoin-failed"
#: One attempt and no retry, not even before the password is written: a person is waiting, and the next press is the retry.
ONE_TRY = RetryPolicy(attempts=1)
SSAR_API = "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews"
#: What the person reads when the token read refuses (#284's codes); the lookup's own `action` speaks to the fleet.
READ_SAYS = {
    "sa-token-secret-missing": "{cluster} has no poller token Secret to read: create it there first",
    "sa-token-invalidated": "the poller token Secret on {cluster} was invalidated by its legacy-token cleaner: delete "
                            "and recreate it there",
    "sa-token-unreadable": "the poller token Secret on {cluster} could not be used",
}


_HEX = re.compile(r"\\u([0-9a-f]{4})")
#: Go's encoding/json, the remote's own encoder, writes these five as lower-case `\\u` escapes and every other character
#: as is: for any value `check` lets through (no control character, no lone surrogate), Python's non-ASCII spelling
#: with these five replaced is Go's.
_GO = str.maketrans({"<": "\\u003c", ">": "\\u003e", "&": "\\u0026", "\u2028": "\\u2028", "\u2029": "\\u2029"})


def _spellings(value: str) -> set[str]:
    """`value` escaped once, as JSON encoders write it: ASCII or not, `/` as `\\/` or not, `\\u` hex in either case,
    and Go's `encoding/json` default."""
    out = set()
    for ascii_ in (True, False):
        escaped = json.dumps(value, ensure_ascii=ascii_)[1:-1]
        for form in (escaped, escaped.replace("/", "\\/")):
            out |= {form, _HEX.sub(lambda m: "\\u" + m[1].upper(), form)}
    out.add(json.dumps(value, ensure_ascii=False)[1:-1].translate(_GO))
    return out


def _scrub(text: str, secrets) -> str:
    """The fleet's scrub, handed each secret as written and in its `_spellings` once and twice escaped: a remote may
    quote a JSON document inside another, and the shared escaped forms stop at eight characters, while a person's
    password may be three. It covers accidental echoes; a hostile remote holds the password anyway (SPEC_D4 §3.7)."""
    forms = set()
    for secret in filter(None, secrets):
        layer = {secret}
        forms |= layer
        for _ in range(2):
            layer = set().union(*map(_spellings, layer))
            forms |= layer
    return _fleet_scrub(text, list(forms))


class RejoinLogin(FleetLogin):
    """#283's login as the person who pressed Rejoin: the same wire, events and rules, in a person's words."""

    REFUSED_ACTION = ("check the username and password — it is not sent again by this pod while it is the same "
                      "password, because each refused try counts toward the directory's lockout of the account")
    NEXT_TRY = "the next Rejoin"

    def __init__(self, cluster: ClusterConfig, username: str, password: str, *, person: str, **knobs):
        super().__init__(cluster, username, password, **knobs)
        self.person = person

    def _scrub(self, text: str, *more: str | None) -> str:
        # FleetLogin scrubs every remote text with this before cutting it; the fleet's own scrub stays as it is.
        return _scrub(text, (self._password, *self._secrets, *more))

    def _fields(self) -> dict[str, str]:
        return {**super()._fields(), "rejoin_by": self.person}


def refusal(cluster: ClusterConfig, settings: Settings) -> str | None:
    """Why this cluster cannot be rejoined, or None: Secret rows and `saTokenLookup` stanzas only (the epic's decision,
    SPEC_D4 §3.2). `/api/clusterconfigs` serves it as `rejoinable`, so the page and the route answer alike."""
    host = settings.host_cluster()
    if host is not None and cluster.name == host.name:
        return "the host polls as the pod's own ServiceAccount; there is no token to fetch"
    if cluster.onboarding or cluster.source.startswith("configmap:"):
        return "a ConfigMap declares it, and its Secret is generated from the stanza there"
    if cluster.credential_kind == CREDENTIAL_SELF_LOGIN:
        return "it declares userSelfLogin: its credential is a session, and a stored token would replace that mode"
    if cluster.source.startswith("secret:") or cluster.sa_token_lookup:
        return None
    return "the chart's values give it its own credential, and a Secret would shadow that entry"


def fleet_accounts(settings: Settings) -> set[str]:
    """Every account a fleet path may present the fleet password as: the chart's, each stanza's
    `ldapConnectionBootstrap`, each Secret's `lookup-account`. Stripped and casefolded: over-refusing is the safe side."""
    names = {settings.fleet_account_username}
    for c in (*settings.clusters, *settings.effective_clusters()):
        names.update((c.ldap_connection_bootstrap, c.lookup_account))
    return {name.strip().casefold() for name in names if name}


def check(cluster: ClusterConfig, settings: Settings, username: str, password: str) -> None:
    """The refusals made before anything is sent (SPEC_D4 §3.1). Each is a `WriteRefused`; none repeats a value."""
    reason = refusal(cluster, settings)
    if reason is not None:
        raise WriteRefused("not-rejoinable", f"{cluster.name} cannot be rejoined: {reason}", conflict=True)
    if not valid_bootstrap_username(username):
        raise WriteRefused("rejoin-username-invalid", "a username is letters, digits and . _ @ -, starting with a letter "
                                                      "or digit, at most 255 characters (RFC 7617 forbids a colon and "
                                                      "control characters); the value is not repeated")
    if username.casefold() in fleet_accounts(settings):
        raise WriteRefused("rejoin-fleet-account", "that username is an account the dashboard's fleet paths log in as; "
                                                   "Rejoin takes a person's own account, never the fleet account")
    if not password:
        raise WriteRefused("rejoin-password-missing", "a password is required")
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F or 0xD800 <= ord(ch) <= 0xDFFF for ch in password):
        raise WriteRefused("rejoin-password-invalid", "the password holds a control character, which RFC 7617 forbids, "
                                                      "or an unpaired surrogate, which UTF-8 cannot carry; it was not "
                                                      "sent")


def question(settings: Settings) -> dict[str, str]:
    """#322's cluster-admin question as a review's resourceAttributes, built as the host's `TierResolver` builds it."""
    attrs = {"verb": settings.visibility_cluster_admin_sar_verb,
             "resource": settings.visibility_cluster_admin_sar_resource,
             "group": settings.visibility_cluster_admin_sar_api_group}
    if settings.visibility_cluster_admin_sar_namespace:
        attrs["namespace"] = settings.visibility_cluster_admin_sar_namespace
    if settings.visibility_cluster_admin_sar_subresource:
        attrs["subresource"] = settings.visibility_cluster_admin_sar_subresource
    return attrs


def question_words(settings: Settings) -> str:
    """The question as the answer and the log say it: `update clusterrolebindings`."""
    attrs = question(settings)
    resource = "/".join(part for part in (attrs["resource"], attrs.get("subresource")) if part)
    where = f" in namespace {attrs['namespace']}" if attrs.get("namespace") else ""
    return f"{attrs['verb']} {resource}{where}"


class _ReviewClient(ClusterClient):
    """D8's client: `_send` cuts a failed answer's body at 200 characters after `_redact`, so Rejoin's scrub runs here."""

    secrets: tuple[str, ...] = ()

    def _redact(self, text: str, *more: str | None) -> str:
        return _scrub(super()._redact(text, *more), self.secrets)


def remote_says_cluster_admin(session_token: str, cluster: ClusterConfig, settings: Settings, *,
                              timeout: float, secrets=()) -> tuple[bool, str]:
    """D8: one SelfSubjectAccessReview on the remote, sent with the login's own token, so the remote answers for the
    person and the groups it resolves for them. (allowed, the remote's reason). Only a boolean `status.allowed` is an
    answer; anything else raises ClusterError, and the caller refuses: no answer is never a yes."""
    as_session = dataclasses.replace(cluster, token_value=session_token, sa_token_lookup=False, user_self_login=False,
                                     ldap_connection_bootstrap=None)
    remote = _ReviewClient(as_session, timeout=timeout)
    remote.secrets = tuple(secrets)
    body = {"apiVersion": "authorization.k8s.io/v1", "kind": "SelfSubjectAccessReview",
            "spec": {"resourceAttributes": question(settings)}}
    with remote._client() as client:
        answer = remote._send(client, "POST", SSAR_API, json=body)
    status = answer.get("status") if isinstance(answer, dict) else None
    allowed = status.get("allowed") if isinstance(status, dict) else None
    if not isinstance(allowed, bool):
        raise ClusterError(UNREACHABLE, f"{SSAR_API} answered without a boolean status.allowed")
    return allowed, "; ".join(str(status[key]) for key in ("reason", "evaluationError") if status.get(key))


def rejoin(cluster: ClusterConfig, settings: Settings, host_client: ClusterClient, *, own_namespace: str,
           gate: CredentialGate, username: str, password: str, viewer: str) -> dict:
    """One Rejoin, after `check`: the gate, the login, D8, the read, the revoke, the write. Answers `{outcome, message,
    at}`: `rejoined`, or a refusal's code with the person's sentence. The caller holds the one-at-a-time lock, so the
    gate's check and the login it guards are one step in this process."""
    # The password as the Basic header carries it (RFC 7617): a remote that quotes the header quotes this.
    secrets = [password, base64.b64encode(f"{username}:{password}".encode("utf-8")).decode("ascii")]
    login = RejoinLogin(cluster, username, password, person=viewer, timeout=settings.request_timeout_seconds,
                        policy=ONE_TRY)
    try:
        return _exchange(cluster, settings, host_client, own_namespace=own_namespace, gate=gate, username=username,
                         password=password, viewer=viewer, login=login, secrets=secrets)
    except Exception:  # noqa: BLE001 - its text may quote the password: fixed words, then how the login ended
        return stopped_unexpectedly(cluster.name, viewer, cleanup=_logged_out(login, cluster), secrets=secrets)


def _exchange(cluster: ClusterConfig, settings: Settings, host_client: ClusterClient, *, own_namespace: str,
              gate: CredentialGate, username: str, password: str, viewer: str, login: RejoinLogin,
              secrets: list[str]) -> dict:
    """`rejoin`'s steps, inside its boundary, which keeps the login to say how it ended."""
    timeout = settings.request_timeout_seconds
    asked = question_words(settings)
    who = dict(cluster=cluster.name, by=viewer, account=username)

    def refused(code: str, said: str, detail: str | None = None, *, phase: str = "credential") -> dict:
        """One failure line and the answer: the person's sentence, then the evidence; both scrubbed."""
        said = f"{said}{_logged_out(login, cluster)}"
        detail = _scrub(detail, secrets) if detail else None   # any length: the emit helper skips values under four
        failure(log, "cluster-rejoin-failed", phase=phase, outcome=code, **who, action=said, detail=detail,
                secrets=secrets)
        return {"outcome": code, "message": _scrub(f"{said} ({detail})" if detail else said, secrets), "at": now_iso()}

    answered = gate.account_refusal(username, password)
    if answered is not None:
        shown = _without_userinfo(answered) or "an earlier cluster"
        return refused("login-refused", f"{shown} already refused this password for {username}, so it was not sent: "
                                        f"type the right password (this pod holds a refused password back until it "
                                        f"restarts)")
    stopped: tuple[str, str, str | None] | None = None      # D8 refused, or could not be asked
    try:
        with login as session:
            secrets.append(session.token)
            try:
                allowed, reason = remote_says_cluster_admin(session.token, cluster, settings, timeout=timeout,
                                                            secrets=secrets)
            except ClusterError as exc:
                stopped = (REVIEW_FAILED, f"{cluster.name} could not be asked whether {username} may {asked} there, "
                                          f"so nothing was read or written", f"{exc.outcome}: {exc.message}")
            else:
                event(log, logging.INFO, "cluster-rejoin-review", **who, question=asked,
                      allowed="true" if allowed else "false", reason=_scrub(reason, secrets) or None, secrets=secrets)
                if not allowed:
                    stopped = (NOT_CLUSTER_ADMIN, f"{cluster.name} says {username} may not {asked} there, so nothing "
                                                  f"was read or written: Rejoin needs a cluster administrator of "
                                                  f"{cluster.name}", reason or None)
                else:
                    try:
                        sa_token = read_sa_token(session.token, cluster, LookupSource.from_settings(settings),
                                                 timeout=timeout)
                    except LookupRefused as exc:
                        login.add_secrets(*exc.secrets)   # the revoke on leaving `with` runs before any outer handler
                        raise
                    secrets.append(sa_token.token)
                    login.add_secrets(sa_token.token)   # the revoke line quotes the remote's body too
    except LoginError as exc:
        if exc.bound:
            # THE PASSWORD WAS ON THE WIRE (#283): the account's entry, exactly as the lookup writes it (#315).
            gate.refuse(cluster.api_url, username, password)
            if exc.outcome == AUTH_FAILED:
                return refused("login-refused", f"{cluster.name} refused the password for {username}: check the "
                                                f"username and password; it is not sent again by this pod while it is "
                                                f"the same password", exc.message)
            return refused("login-failed", f"the password for {username} was sent to {cluster.name} and no session "
                                           f"came back; it is not sent again by this pod while it is the same "
                                           f"password, and a locked directory account answers HTTP 500, so check the "
                                           f"account before you try again", exc.message)
        hint = "; the cluster's trust must verify both the API host and the OAuth route" if exc.phase == "tls" else ""
        return refused("login-failed", f"could not reach {cluster.name}'s login, so the password was not sent{hint}",
                       exc.message, phase=exc.phase)
    except LookupRefused as exc:
        exc.scrub(secrets)
        said = READ_SAYS.get(exc.code, "the poller token Secret could not be read").format(cluster=cluster.name)
        return refused(exc.code, f"{said}; nothing was written", exc.detail)
    if stopped is not None:
        return refused(*stopped)
    at = now_iso()
    try:
        written = store(host_client, own_namespace, cluster, settings, sa_token, account=username,
                        rejoin=(viewer, username, at))
    except LookupRefused as exc:
        exc.scrub(secrets)
        return refused(exc.code, f"the token was read on {cluster.name} but writing {secret_name_for(cluster.name)} "
                                 f"here failed, so nothing was stored", exc.detail)
    event(log, logging.INFO, "cluster-rejoined", **who, secret=secret_name_for(cluster.name), written=written,
          revoked="true" if login.revoked else "false", secrets=secrets)
    message = (f"Signed in to {cluster.name} as {username}, who may {asked} there; read the poller's token and "
               f"{written} {secret_name_for(cluster.name)} here. The cluster is read again within seconds"
               f"{_logged_out(login, cluster)}")
    return {"outcome": REJOINED, "message": _scrub(message, secrets), "at": at}


def stopped_unexpectedly(cluster: str, viewer: str, *, cleanup: str = "", secrets=()) -> dict:
    """The answer to an error the design did not expect: fixed words, because the error's own may quote the password,
    then how the login ended when there was one. The line records only that it happened."""
    said = _scrub("Rejoin stopped unexpectedly, and nothing of the error is shown or logged: press Refresh before "
                  f"Rejoin again{cleanup}", secrets)
    failure(log, "cluster-rejoin-failed", phase="credential", outcome=STOPPED, cluster=cluster, by=viewer, action=said,
            secrets=secrets)
    return {"outcome": STOPPED, "message": said, "at": now_iso()}


def _logged_out(login: FleetLogin, cluster: ClusterConfig) -> str:
    """How the login ended, for every answer after a session existed: revoked, or what to delete. An unprefixed
    token is its own object's name, so it is never shown (`gsd/fleetlogin.py#token_object_name`)."""
    if login.session is None:
        return ""
    if login.revoked:
        return "; the login was signed out"
    name = login.session.token_name if login.session.token.startswith(TOKEN_PREFIX) else "the login's token"
    return (f"; the login could NOT be signed out on {cluster.name}: delete {name} there (oc delete "
            f"useroauthaccesstokens <name>, as yourself)")


__all__ = ["NOT_CLUSTER_ADMIN", "ONE_TRY", "READ_SAYS", "REJOINED", "REVIEW_FAILED", "STOPPED", "RejoinLogin", "check",
           "fleet_accounts", "question", "question_words", "refusal", "rejoin", "remote_says_cluster_admin",
           "stopped_unexpectedly"]
```

<!-- block: local-development/gsd/api.py | edit -->
```python

from fastapi import Depends, FastAPI, HTTPException, Query, Request
```

```python
from typing import Any

from fastapi import Body, Depends, FastAPI, HTTPException, Query, Request
```

<!-- block: local-development/gsd/api.py | edit -->
```python
        from .clusterconfig.warnings import shared_api_warnings
```

```python
        from .clusterconfig.warnings import shared_api_warnings
        from .rejoin import refusal as rejoin_refusal
```

<!-- block: local-development/gsd/api.py | edit -->
```python
                "retired": False, "onboarding_configmap": c.onboarding[0] if c.onboarding else None,
```

```python
                "retired": False, "onboarding_configmap": c.onboarding[0] if c.onboarding else None,
                # SPEC_D4 (#316): the route's own rule, so the page offers Rejoin exactly where the route accepts it.
                "rejoinable": rejoin_refusal(c, settings) is None,
```

<!-- block: local-development/gsd/api.py | edit -->
```python
                    refreshing.discard(name)
```

```python
                    refreshing.discard(name)

        # One Rejoin at a time in this process (SPEC_D4 §3.3): the gate's check and the login it guards are then one step,
        # so a double click, two tabs or a script can never both reach a password's first use. Refused, never queued.
        rejoining = threading.Lock()

        @app.post("/api/clusterconfigs/{name}/rejoin")
        def rejoin_cluster_config(request: Request, name: str, body: Any = Body(None)) -> dict:
            """SPEC_D4 (#316): a cluster administrator's own username and password, for ONE login to the remote; the
            dashboard reads the poller's token there, writes it here and keeps no password. `body: Any`, so FastAPI
            neither validates nor echoes what arrived (a typed body's 422 quotes a non-object body whole): the shape is
            refused here in fixed words, because even a key can be the password. Registered with the writes."""
            from . import rejoin
            from .clusterconfig.writer import WriteRefused
            viewer, namespace, host_client = _writes_gate(request)
            if not isinstance(body, dict) or set(body) - {"username", "password"}:
                raise HTTPException(status_code=422, detail="body: an object with username and password, and no other key")
            username, password = body.get("username"), body.get("password")
            if not isinstance(username, str) or not isinstance(password, str):
                raise HTTPException(status_code=422, detail="username and password: each must be a string")
            cluster = settings.cluster(name)
            if cluster is None:
                raise HTTPException(status_code=404, detail=f"unknown cluster {name!r}")
            try:
                rejoin.check(cluster, settings, username, password)
            except WriteRefused as exc:
                raise _write_error(exc) from exc
            # The poller's gate (#315), the one the lookup and self-login use: no poller, no gate, so no login.
            gate = getattr(getattr(app.state, "poller", None), "_credential_gate", None)
            if gate is None:
                raise HTTPException(status_code=409, detail="this process runs no poller, so it holds no credential "
                                                            "gate; nothing was sent")
            if not rejoining.acquire(blocking=False):
                raise HTTPException(status_code=409, detail="a Rejoin is already in flight on this pod; nothing was sent")
            try:
                answer = rejoin.rejoin(cluster, settings, host_client, own_namespace=namespace, gate=gate,
                                       username=username, password=password, viewer=viewer)
            except Exception:  # noqa: BLE001 - its text may quote the password: fixed words, and nothing of it logged
                answer = rejoin.stopped_unexpectedly(cluster.name, viewer)
            finally:
                rejoining.release()
            if answer["outcome"] == rejoin.REJOINED:
                _request_discovery()
            return answer
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
</dialog>

<script>
```

```html
</dialog>

<!-- #316 (SPEC_D4 §3.6): Rejoin's dialog. Static and outside #main for #ns-preview's reason: render() replaces #main on
     every poll and would erase what is typed. No <form>, so no submission can carry the password into a URL; the
     fields are cleared on close and on pagehide, and autocomplete="off" asks the browser not to remember them. -->
<dialog id="rejoin-dialog" class="ns-preview cc-rejoin" aria-labelledby="rejoin-title">
  <h2 id="rejoin-title">Rejoin <span id="rejoin-name"></span></h2>
  <p>Sign in to <span class="mono rejoin-cluster"></span> as yourself. The dashboard logs in once to
    <span class="mono" id="rejoin-server"></span>, asks it whether you are a cluster administrator there, reads the
    poller's token, writes <span class="mono" id="rejoin-secret"></span>, and signs that login out.
    <strong>Your password is used for this one login and is not saved by the dashboard.</strong> The Secret records
    your username and who pressed Rejoin. Browser password managers may ignore the request not to save these fields.</p>
  <div class="cc-field"><label for="rejoin-username">Username on <span class="rejoin-cluster"></span></label>
    <input id="rejoin-username" autocomplete="off" autocapitalize="none" spellcheck="false"></div>
  <div class="cc-field"><label for="rejoin-password">Password</label>
    <input id="rejoin-password" type="password" autocomplete="off"></div>
  <ul class="cc-gates" aria-label="Two gates, on two clusters">
    <li><span class="badge ok"><span class="glyph" aria-hidden="true"></span>passed</span> <strong>1 · this cluster, the
      host.</strong> You hold the cluster-admin tier here, which is why Rejoin is shown to you at all.</li>
    <li><span class="badge unknown"><span class="glyph" aria-hidden="true"></span>decided there</span> <strong>2 ·
      <span class="rejoin-cluster"></span>, the remote.</strong> Once you are signed in, it is asked the same question
      about you. If it says no, nothing is read or written, and this dashboard cannot override it.</li>
  </ul>
  <div class="cc-warn"><strong>One try per password on this pod.</strong> If this password is refused, this pod does not
    send it again, to any cluster, while it is the same password. A restarted pod or another replica does not know
    that, and can send it once more: press Refresh before you press Rejoin again. A locked directory account answers
    HTTP 500, not 401, so trying again only locks it further.</div>
  <p class="cc-hint" id="rejoin-msg" aria-live="polite"></p>
  <div class="idle-actions rejoin-acts">
    <button type="button" id="rejoin-cancel">Cancel</button>
    <button type="button" class="btn cc-btn-acc" id="rejoin-go">Rejoin</button>
  </div>
</dialog>

<script>
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
                clusterRotate: null, clusterDeleteArmed: null, clusterMsg: {}, clusterCreating: false, clusterRefresh: {},
```

```html
                clusterRotate: null, clusterDeleteArmed: null, clusterMsg: {}, clusterCreating: false, clusterRefresh: {},
                clusterRejoin: {},   // #316: each card's Rejoin answer by cluster id — never a username or a password
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
    out += `<div class="cc-hint">The stored credential was refused. Next step: Rejoin (#316), not built yet — until then, replace the credential where it is written.</div>`;
  }
  return out + "</div>";
```

```html
    out += `<div class="cc-hint">The stored credential was refused. Refresh only probes with it; it never logs in. ${c.rejoinable
      ? "To fetch a new token with your own account, use Rejoin." : "Replace the credential where it is written."}</div>`;
  }
  return out + "</div>";
}
/* #316 (SPEC_D4 §3.6): Rejoin is offered where the route accepts it (`rejoinable`, the server's rule), once Refresh has
   said the stored credential is refused or not there yet — and stays while its own answer is shown. */
function ccRejoinButton(c) {
  const r = view.clusterRefresh[c.id] || {};
  if (!c.rejoinable || !(["auth_failed", "pending"].includes(r.outcome) || view.clusterRejoin[c.id])) return "";
  const busy = (view.clusterRejoin[c.id] || {}).state === "flight";
  return `<button type="button" class="btn cc-btn-acc" id="cc-rejoin-${esc(c.id)}" data-cc-rejoin="${esc(c.id)}"${busy ? ` disabled aria-busy="true"` : ""}>${busy ? "Rejoining…" : "Rejoin…"}</button>`;
}
function ccRejoinLine(c) {
  const r = view.clusterRejoin[c.id];
  if (!r) return "";
  const head = `<div class="cc-consq" id="cc-rejoin-result-${esc(c.id)}"><strong>Rejoin:</strong> `;
  if (r.state === "flight") return `${head}signing in once and reading the poller's token…</div>`;
  const shape = r.outcome === "rejoined" ? "ok" : r.outcome === "unknown" ? "unknown" : "critical";
  let out = `${head}${ccBadge(shape, r.outcome)}`;
  if (r.at) out += ` · <span class="mono">${esc(r.at)}</span>`;
  return out + (r.message ? ` — ${esc(r.message)}` : "") + "</div>";
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
  const refresh = !c.retired && ccWritesOn() ? ccRefreshButton(c) : "";
```

```html
  const refresh = !c.retired && ccWritesOn() ? ccRefreshButton(c) + ccRejoinButton(c) : "";
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
    <div class="cc-kv"><span class="k">connection</span><span class="v">${ccConnection(c)}${ccRefreshLine(c)}</span></div>
```

```html
    <div class="cc-kv"><span class="k">connection</span><span class="v">${ccConnection(c)}${ccRefreshLine(c)}${ccRejoinLine(c)}</span></div>
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
async function apiSend(path, method, body) {
  const res = await fetch(path, { method, headers: { Accept: "application/json", "Content-Type": "application/json", "X-GSD-Interaction": "1" },
```

```html
async function apiSend(path, method, body, redirect = "follow") {
  const res = await fetch(path, { method, redirect, headers: { Accept: "application/json", "Content-Type": "application/json", "X-GSD-Interaction": "1" },
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
  });
  document.querySelectorAll("[data-cc-delete]").forEach((el) => {
```

```html
  });
  document.querySelectorAll("[data-cc-rejoin]").forEach((el) => {
    el.onclick = () => openRejoin(el.dataset.ccRejoin);
  });
  const rejoinDlg = $("rejoin-dialog");
  if (rejoinDlg) {
    $("rejoin-go").onclick = sendRejoin;
    $("rejoin-cancel").onclick = closeRejoin;
    $("rejoin-password").onkeydown = (e) => { if (e.key === "Enter") { e.preventDefault(); sendRejoin(); } };
    rejoinDlg.onclose = () => {
      clearRejoin();
      const b = $(`cc-rejoin-${rejoinDlg.dataset.cluster}`);   // by id: a repaint replaced the button that opened it
      if (b) b.focus();
    };
  }
  document.querySelectorAll("[data-cc-delete]").forEach((el) => {
```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
           labels: {}, labelKey: "", labelVal: "", test: null };
}

```

```html
           labels: {}, labelKey: "", labelVal: "", test: null };
}
/* #316 (SPEC_D4 §3.6): the Rejoin dialog. What is typed lives only in its two fields: never in `view`, storage or a URL. */
function openRejoin(id) {
  const c = ((data.clusterconfigs || {}).clusters || []).find((x) => x.id === id);
  const dlg = $("rejoin-dialog");
  if (!c || !dlg || dlg.open) return;
  dlg.dataset.cluster = id;
  $("rejoin-name").textContent = id;
  $("rejoin-server").textContent = c.api_url || "";
  $("rejoin-secret").textContent = `gsd-cluster-${id}`;
  document.querySelectorAll(".rejoin-cluster").forEach((el) => { el.textContent = id; });
  $("rejoin-msg").textContent = "";
  dlg.showModal();
  $("rejoin-username").focus();
}
function closeRejoin() {
  const dlg = $("rejoin-dialog");
  clearRejoin();                      // now: the close event fires from a queued task
  if (dlg && dlg.open) dlg.close();   // Escape closes without this; the close handler clears then
}
function clearRejoin() {
  ["rejoin-username", "rejoin-password"].forEach((id) => { const el = $(id); if (el) el.value = ""; });
}
async function sendRejoin() {
  const dlg = $("rejoin-dialog"), id = dlg.dataset.cluster, field = $("rejoin-password");
  const username = $("rejoin-username").value.trim(), password = field.value;
  if ((view.clusterRejoin[id] || {}).state === "flight") return;          // one press, one request
  if (!username || !password) { $("rejoin-msg").textContent = "Type your username and your password."; return; }
  field.value = "";                                                       // sent once: another try means typing it again
  view.clusterRejoin[id] = { state: "flight" };
  $("rejoin-go").disabled = true;
  $("rejoin-msg").textContent = "Signing in once…";
  render();
  try {
    // "error": a 307 or 308 in front of the dashboard would re-send the password to its Location (#316)
    view.clusterRejoin[id] = { state: "done", ...(await apiSend(`/api/clusterconfigs/${encodeURIComponent(id)}/rejoin`, "POST", { username, password }, "error")) };
  } catch (e) {
    // No JSON answer (a gateway timeout, a dropped connection): the server may still have finished the Rejoin.
    view.clusterRejoin[id] = e.status ? { state: "done", outcome: `HTTP ${e.status}`, message: e.message, at: null }
      : { state: "done", outcome: "unknown", at: null, message: "The answer did not arrive, and the Rejoin may have "
          + "finished anyway. Press Refresh in a minute; do not press Rejoin again until Refresh answers." };
  }
  const r = view.clusterRejoin[id];
  $("rejoin-go").disabled = false;
  if (r.outcome === "rejoined") closeRejoin(); else $("rejoin-msg").textContent = `${r.outcome} — ${r.message}`;
  render(); refresh();
}
// The back/forward cache keeps a page's DOM, typed values included: a page left with the dialog open keeps none (#316).
window.addEventListener("pagehide", clearRejoin);

```

<!-- block: local-development/gsd/static/index.html | edit -->
```html
  navSeq++;
  $("idle-modal").hidden = true;
  setIdleChrome(false);
```

```html
  navSeq++;
  $("idle-modal").hidden = true;
  closeRejoin();   // #316: a typed username is on screen too, and it leaves with the rest
  setIdleChrome(false);
```

<!-- block: local-development/gsd/static/app.css | edit -->
```css
  dialog.ns-preview { border: 2px solid CanvasText; }
}

```

```css
  dialog.ns-preview { border: 2px solid CanvasText; }
}
/* #316 (SPEC_D4 §3.6): the Rejoin dialog wears #ns-preview's look, wider for two fields and the two gates. */
dialog.cc-rejoin { max-width: min(560px, calc(100% - 2 * var(--space-8))); }
dialog.cc-rejoin ul.cc-gates { max-height: none; overflow: visible; display: grid; gap: var(--space-4); }
dialog.cc-rejoin ul.cc-gates li { border: 1px solid var(--gridline); border-radius: var(--radius-md); padding: var(--space-5) var(--space-6);
  font-size: var(--text-md); color: var(--text-secondary); overflow-wrap: anywhere; }
dialog.cc-rejoin .rejoin-acts { justify-content: flex-end; margin-top: var(--space-6); }

```

<!-- block: local-development/tests/test_cluster_rejoin.py | create -->
```python
"""Rejoin (#316, docs/specs/SPEC_D4_cluster_rejoin.md): `POST /api/clusterconfigs/{name}/rejoin` takes a cluster
administrator's own username and password for ONE login to the remote, asks the remote whether that person is a
cluster administrator there (D8), reads the poller's token Secret, revokes the login and writes gsd-cluster-<name>
here. The password is presented at most once per press, never retried, never stored, never presented as any other
account, and the fleet account is never used. The page's dialog is in tests/test_ui.py::TestClusterConfigPage.

The remote is S4b's fake target, which records every request in order (`presented` decodes each authorize's Basic
header, so every budget here counts the wire), plus D8's SelfSubjectAccessReview. The host is the tab's in-memory
namespace (`_Host`). No real account or password appears here: ADMIN is a made-up administrator, and USER the fleet
harness's own fleet account."""

from __future__ import annotations

import base64
import dataclasses
import json
import logging
import pathlib
import re
import sqlite3
import threading

import httpx
import pytest
from fastapi.testclient import TestClient

from gsd.api import build_app
from gsd.clusterconfig import parse_secret
from gsd.clusterconfig.reader import discover
from gsd.clusterconfig.writer import (
    LOOKUP_ACCOUNT_ANNOTATION, MANAGED_BY_ANNOTATION, SOURCE_NAMESPACE_ANNOTATION, SOURCE_SERVICE_ACCOUNT_ANNOTATION,
    TOKEN_SOURCE_ANNOTATION,
)
from gsd.config import ClusterConfig
from gsd.fleetlookup import INVALID_SINCE_LABEL, CredentialGate
from test_clusterconfig import TOKEN as STORED_TOKEN, _secret
from test_clusterconfig_tab import NS, _Host
from test_fleet_lifecycle import LeaseHost, process, retrieved
from test_fleet_login import DISCOVERY_PATH, OAUTH, PASSWORD, TOKEN, USER, USER_TOKEN_API, down, login_302, refused_401
from test_fleet_lookup import SA_TOKEN, SOURCE, LookupTarget, sa_secret
from test_visibility import H, _MapResolver, _seed, _settings

REPO = pathlib.Path(__file__).resolve().parents[2]
#: The contract's own strings, written out rather than imported: a test that imported them would pass whatever they said.
SSAR_API = "/apis/authorization.k8s.io/v1/selfsubjectaccessreviews"
REJOINED_BY_ANNOTATION = "groupsync-dashboard.io/rejoined-by"
REJOIN_ACCOUNT_ANNOTATION = "groupsync-dashboard.io/rejoin-account"
REJOINED_AT_ANNOTATION = "groupsync-dashboard.io/rejoined-at"
ADMIN, ADMIN_PASSWORD = "alice.admin", "Adm1n-pw-7f3e9c"
BASIC = base64.b64encode(f"{ADMIN}:{ADMIN_PASSWORD}".encode()).decode()
ISO = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
ADMIN_REASON = 'RBAC: allowed by ClusterRoleBinding "cluster-admins" of ClusterRole "cluster-admin" to Group "admins"'


def review(allowed=True, reason: str | None = ADMIN_REASON, **status) -> httpx.Response:
    """The remote's SelfSubjectAccessReview answer, in the shape measured on the lab (SPEC_D4, Appendix A.3)."""
    body = {"allowed": allowed, **({"reason": reason} if reason else {}), **status}
    return httpx.Response(201, json={"kind": "SelfSubjectAccessReview", "apiVersion": "authorization.k8s.io/v1",
                                     "metadata": {}, "status": body})


class RemoteTarget(LookupTarget):
    """S4b's fake target plus D8's review, answered from `review` (a Response, or a callable given the request)."""

    def __init__(self, *answers, review_answer=None, **kw):
        super().__init__(*answers, **kw)
        self.review = review() if review_answer is None else review_answer

    def __call__(self, request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == SSAR_API:
            self.requests.append(request)
            return self._answer(self.review, request)
        return super().__call__(request)

    @property
    def reviews(self) -> list[httpx.Request]:
        return [r for r in self.requests if r.url.path == SSAR_API]


def presented(target) -> list[tuple[str, str]]:
    """(username, password) of every authorize request, in the order it reached the target."""
    out = []
    for request in target.authorize:
        user, _, password = base64.b64decode(request.headers["authorization"].split(" ", 1)[1]).decode().partition(":")
        out.append((user, password))
    return out


class _Poller:
    """The route's two needs from the poller: its one credential gate (#315) and the discovery wake."""

    def __init__(self):
        self._credential_gate = CredentialGate()
        self.woke = 0

    def request_discovery(self):
        self.woke += 1


@pytest.fixture
def remote(monkeypatch):
    """Every httpx.Client the login, the review and the read build goes to one fake target."""
    target = RemoteTarget(login_302())
    real = httpx.Client

    def client(**kw):
        return real(transport=httpx.MockTransport(target), base_url=kw.get("base_url", "https://api.east.example:6443"),
                    headers=kw.get("headers"), follow_redirects=False)
    monkeypatch.setattr(httpx, "Client", client)
    return target


def _app(tmp_path, monkeypatch, host, *discovered, name="gsd", **kw):
    """One dashboard process: its own store, its own poller gate, `discovered` on its registry."""
    db = str(tmp_path / f"{name}.db"); _seed(db)
    settings = dataclasses.replace(_settings(db), cluster_secrets_writes_enabled=True, **kw)
    settings.cluster_registry.namespace = NS
    settings.cluster_registry.replace(list(discovered), [], at="2026-09-27T14:00:00Z")
    monkeypatch.setattr("gsd.api.ClusterClient", lambda cfg, timeout=15.0: host)
    monkeypatch.setattr("gsd.api.own_namespace", lambda: NS)
    app = build_app(settings, run_poller=False)
    app.state.tier_resolver = _MapResolver({"root": "all", "auditor": "all"})
    app.state.remote_tier_resolvers = {}
    app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
    app.state.poller = _Poller()
    return app, settings


@pytest.fixture
def rig(tmp_path, monkeypatch, remote):
    host = _Host({"gsd-cluster-east": _secret(), "gsd-cluster-west": _secret("gsd-cluster-west", cluster="west",
                                                                           server="https://api.west.example:6443")})
    east = parse_secret(_secret(), host_name="c1")
    west = parse_secret(_secret("gsd-cluster-west", cluster="west", server="https://api.west.example:6443"), host_name="c1")
    app, settings = _app(tmp_path, monkeypatch, host, east, west)
    with TestClient(app) as c:
        yield c, app, settings, host, remote


def _rejoin(c, name="east", who="root", *, username=ADMIN, password=ADMIN_PASSWORD):
    return c.post(f"/api/clusterconfigs/{name}/rejoin", headers=H(who), json={"username": username, "password": password})


def _writes(host) -> list[tuple[str, str]]:
    return [call for call in host.calls if call[0] != "GET"]


# ── the exchange ─────────────────────────────────────────────────────────────────────────────────────────────

def test_a_secret_row_is_rejoined_in_place_with_the_persons_provenance(rig, caplog, monkeypatch):
    c, app, settings, host, remote = rig

    def never(*a, **kw):
        raise AssertionError("Rejoin entered the fleet account's lookup")
    monkeypatch.setattr("gsd.fleetlookup.lookup", never)
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"outcome", "message", "at"} and body["outcome"] == "rejoined" and ISO.match(body["at"])
    assert "Signed in to east as alice.admin, who may update clusterrolebindings there" in body["message"]
    assert "the login was signed out" in body["message"]
    # the wire: discovery, ONE authorize as the person, D8 with the login's token, the read, the revoke
    order = [(q.method, q.url.path) for q in remote.requests]
    assert order[:4] == [("GET", DISCOVERY_PATH), ("GET", "/oauth/authorize"), ("POST", SSAR_API), ("GET", SOURCE)]
    assert len(order) == 5 and order[4][0] == "DELETE" and order[4][1].startswith(USER_TOKEN_API + "/")
    assert presented(remote) == [(ADMIN, ADMIN_PASSWORD)]
    assert remote.reviews[0].headers["authorization"] == f"Bearer {TOKEN}" == remote.reads[0].headers["authorization"]
    assert json.loads(remote.reviews[0].content) == {
        "apiVersion": "authorization.k8s.io/v1", "kind": "SelfSubjectAccessReview",
        "spec": {"resourceAttributes": {"verb": "update", "resource": "clusterrolebindings",
                                        "group": "rbac.authorization.k8s.io"}}}
    # the host: updated in place with the person's provenance, and no lookup-account
    assert _writes(host) == [("PUT", f"/api/v1/namespaces/{NS}/secrets/gsd-cluster-east")]
    assert [path for _, path in host.calls if "gsd-fleet-account" in path] == [], "the fleet password was read"
    stored = host.secrets["gsd-cluster-east"]
    assert json.loads(base64.b64decode(stored["data"]["config"])) == {"bearerToken": SA_TOKEN}
    assert stored["metadata"]["annotations"] == {
        TOKEN_SOURCE_ANNOTATION: "rejoin", SOURCE_NAMESPACE_ANNOTATION: "group-sync-operator",
        SOURCE_SERVICE_ACCOUNT_ANNOTATION: "group-sync-dashboard-cluster-poller",
        REJOINED_BY_ANNOTATION: "root", REJOIN_ACCOUNT_ANNOTATION: ADMIN, REJOINED_AT_ANNOTATION: body["at"]}
    assert app.state.poller.woke == 1, "a write wakes discovery, as every write in the tab does"
    # the lines: the login's own, marked as a Rejoin; the remote's answer, as D8 asks; the outcome
    assert any(m.startswith("fleet-login ") and "account=alice.admin" in m and "rejoin_by=root" in m for m in caplog.messages)
    assert any(m.startswith("cluster-rejoin-review cluster=east by=root account=alice.admin") and "allowed=true" in m
               and 'question="update clusterrolebindings"' in m and "cluster-admins" in m for m in caplog.messages)
    assert "cluster-rejoined cluster=east by=root account=alice.admin secret=gsd-cluster-east written=updated revoked=true" in caplog.text
    assert "cluster-secret-rotated secret=gsd-cluster-east namespace=ns cluster=east by=root" in caplog.text


def test_a_lookup_written_secret_rejoined_drops_lookup_account_and_keeps_who_made_it(rig):
    """A Secret the lookup wrote records the fleet account in `lookup-account`. Rejoin replaces the provenance and
    removes that key — the daily ping logs in as whatever account it names (#432) — and keeps `managed-by`."""
    c, app, settings, host, remote = rig
    written = _secret(); written["metadata"]["annotations"] = {
        MANAGED_BY_ANNOTATION: "sa-token-lookup", TOKEN_SOURCE_ANNOTATION: "remote-lookup",
        SOURCE_NAMESPACE_ANNOTATION: "group-sync-operator", SOURCE_SERVICE_ACCOUNT_ANNOTATION: "group-sync-dashboard-cluster-poller",
        LOOKUP_ACCOUNT_ANNOTATION: USER}
    host.secrets["gsd-cluster-east"] = written
    assert _rejoin(c).json()["outcome"] == "rejoined"
    ann = host.secrets["gsd-cluster-east"]["metadata"]["annotations"]
    assert LOOKUP_ACCOUNT_ANNOTATION not in ann and ann[MANAGED_BY_ANNOTATION] == "sa-token-lookup"
    assert ann[TOKEN_SOURCE_ANNOTATION] == "rejoin" and ann[REJOIN_ACCOUNT_ANNOTATION] == ADMIN


def test_a_pending_satokenlookup_stanza_is_created_and_counted_as_the_lookups_own(tmp_path, monkeypatch, remote):
    """A values stanza whose lookup has not written its Secret yet (the fleet account locked, say): Rejoin creates
    gsd-cluster-rnd with the stanza's policy, `managed-by: ui`, and the person's provenance; discovery then counts it
    as the stanza's own (`owned_by_mode`), so it is no shadow and the stanza's policy is what is served."""
    rnd = ClusterConfig("rnd", "https://api.rnd.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=USER,
                        visibility="self-only", identity="none")
    host = _Host({})
    app, settings = _app(tmp_path, monkeypatch, host)
    settings.clusters.append(rnd)
    with TestClient(app) as c:
        r = _rejoin(c, "rnd")
    assert r.status_code == 200 and r.json()["outcome"] == "rejoined", r.text
    assert _writes(host) == [("POST", f"/api/v1/namespaces/{NS}/secrets")]
    stored = host.secrets["gsd-cluster-rnd"]
    ann = stored["metadata"]["annotations"]
    assert ann[MANAGED_BY_ANNOTATION] == "ui" and ann[TOKEN_SOURCE_ANNOTATION] == "rejoin"
    assert ann[REJOINED_BY_ANNOTATION] == "root" and ann[REJOIN_ACCOUNT_ANNOTATION] == ADMIN
    assert LOOKUP_ACCOUNT_ANNOTATION not in ann
    data = {k: base64.b64decode(v).decode() for k, v in stored["data"].items()}
    assert (data["visibility"], data["identity"]) == ("self-only", "none")
    clusters, findings = discover(None, NS, host_name="c1", values_names=("c1", "c2", "rnd"),
                                  values_modes={"rnd": "remote-lookup"}, items=[stored])
    assert [f.code for f in findings] == [], "the rejoined Secret over its own stanza is no shadow"
    settings.cluster_registry.replace(clusters, findings, at="2026-09-27T14:05:00Z")
    served = settings.cluster("rnd")
    assert served.credential_kind == "bearer" and served.token_source == "rejoin" and served.lookup_account is None
    assert (served.visibility, served.identity) == ("self-only", "none"), "the stanza's policy, not the Secret's own"


def test_the_daily_ping_never_logs_in_as_the_person_who_rejoined(rig, tmp_path, monkeypatch):
    """#432, read forward: the ping logs in as whatever account a retrieved Secret's `lookup-account` names, WITH THE
    FLEET PASSWORD. Had Rejoin written the person there, the ping would present the fleet password as the person —
    a refused login counted against their directory entry, once a day. It writes `rejoin-account` instead."""
    c, app, settings, host, remote = rig
    assert _rejoin(c).json()["outcome"] == "rejoined"
    rejoined, findings = discover(None, NS, host_name="c1", items=[host.secrets["gsd-cluster-east"]])
    assert findings == [] and rejoined[0].token_source == "rejoin"
    remote.answers = [login_302()] * 4
    start = len(remote.authorize)
    lease_host = LeaseHost()
    lease_host.rotate(PASSWORD)
    fleet = process(tmp_path, monkeypatch, lease_host, discovered=[*rejoined, retrieved("shared-rnd")],
                    fleet_account_username=USER)
    fleet._ping_accounts()
    assert presented(remote)[start:] == [(USER, PASSWORD)], "the ping presented the fleet password as someone else"


# ── the route's refusals: nothing is sent, and no value is repeated ─────────────────────────────────────────

@pytest.mark.parametrize("raw", [
    f'"{ADMIN_PASSWORD}"',                                                        # a JSON string: a typed body quoted it whole
    f'["{ADMIN}", "{ADMIN_PASSWORD}"]',
    "12345",
    "",                                                                           # no body at all
    f'{{"username": "{ADMIN}", "password": "{ADMIN_PASSWORD}", "token": "x"}}',  # a key the contract does not know
    f'{{"username": "{ADMIN}", "password": "{ADMIN_PASSWORD}", "{ADMIN_PASSWORD}": "x"}}',  # a key that IS the password
    f'{{"username": "{ADMIN}", "password": 12345}}',
    f'{{"username": "{ADMIN}", "password": "{ADMIN_PASSWORD}"',                  # not JSON
], ids=["string", "list", "number", "empty", "unknown-key", "password-as-key", "not-a-string", "malformed"])
def test_the_body_is_username_and_password_and_nothing_else(rig, raw):
    c, app, settings, host, remote = rig
    r = c.post("/api/clusterconfigs/east/rejoin", headers={**H("root"), "Content-Type": "application/json"}, content=raw)
    assert r.status_code == 422, r.text
    assert ADMIN_PASSWORD not in r.text and remote.requests == [] and _writes(host) == []


@pytest.mark.parametrize("name,username,password,status,code", [
    ("c1", ADMIN, ADMIN_PASSWORD, 409, "not-rejoinable"),                  # the host: the pod's own ServiceAccount
    ("c2", ADMIN, ADMIN_PASSWORD, 409, "not-rejoinable"),                  # a values entry with its own credential
    ("sl", ADMIN, ADMIN_PASSWORD, 409, "not-rejoinable"),                  # a Secret declaring userSelfLogin
    ("cm", ADMIN, ADMIN_PASSWORD, 409, "not-rejoinable"),                  # generated from a ConfigMap
    ("east", "alice:admin", ADMIN_PASSWORD, 422, "rejoin-username-invalid"),   # RFC 7617: no colon in a user-id
    ("east", "alice admin", ADMIN_PASSWORD, 422, "rejoin-username-invalid"),
    ("east", "SVC-GSD-Fleet\n", ADMIN_PASSWORD, 422, "rejoin-username-invalid"),  # a final newline: refused by the grammar (#438)
    ("east", "SVC-GSD-Fleet", ADMIN_PASSWORD, 422, "rejoin-fleet-account"),    # the chart's fleet account, any case
    ("east", "stanza-account", ADMIN_PASSWORD, 422, "rejoin-fleet-account"),   # a stanza's ldapConnectionBootstrap
    ("east", "recorded-account", ADMIN_PASSWORD, 422, "rejoin-fleet-account"), # a Secret's lookup-account
    ("east", "padded-account", ADMIN_PASSWORD, 422, "rejoin-fleet-account"),   # one recorded with a final newline
    ("east", ADMIN, "", 422, "rejoin-password-missing"),
    ("east", ADMIN, "Adm1n-pw\nsecond-line", 422, "rejoin-password-invalid"),  # RFC 7617: no control characters
    ("east", ADMIN, "Adm1n-pw-\ud800", 422, "rejoin-password-invalid"),        # not encodable: an unpaired surrogate
])
def test_each_refusal_before_the_wire_sends_nothing_and_repeats_no_value(tmp_path, monkeypatch, remote, name, username,
                                                                          password, status, code):
    west = parse_secret(_secret("gsd-cluster-west", cluster="west", server="https://api.west.example:6443"), host_name="c1")
    discovered = [parse_secret(_secret(), host_name="c1"),
                  ClusterConfig("sl", "https://api.sl.example:6443", user_self_login=True, ldap_connection_bootstrap="svc-sl",
                                source="secret:gsd-cluster-sl"),
                  dataclasses.replace(west, name="cm", source="secret:gsd-cluster-cm", onboarding=("fleet", "uid-1", "0" * 64)),
                  dataclasses.replace(west, name="rec", source="secret:gsd-cluster-rec", token_source="remote-lookup",
                                      lookup_account="recorded-account"),
                  dataclasses.replace(west, name="pad", source="secret:gsd-cluster-pad", token_source="remote-lookup",
                                      lookup_account="padded-account\n")]
    host = _Host({"gsd-cluster-east": _secret()})
    app, settings = _app(tmp_path, monkeypatch, host, *discovered, fleet_account_username=USER)
    settings.clusters.append(ClusterConfig("st", "https://api.st.example:6443", sa_token_lookup=True,
                                           ldap_connection_bootstrap="stanza-account"))
    with TestClient(app) as c:
        r = c.post(f"/api/clusterconfigs/{name}/rejoin", headers={**H("root"), "Content-Type": "application/json"},
                   content=json.dumps({"username": username, "password": password}))
    assert r.status_code == status and r.json()["detail"].startswith(f"{code}: "), r.text
    assert remote.requests == [] and _writes(host) == []
    if code.startswith("rejoin-"):
        assert username not in r.text and (not password or password not in r.text), "a refusal repeats no value"
    gate = app.state.poller._credential_gate
    assert gate._refused == {} and gate._spent == set(), "a refusal before the wire records nothing"


def test_below_the_cluster_admin_tier_is_403_and_nothing_is_sent(rig):
    c, app, settings, host, remote = rig
    assert _rejoin(c, who="auditor").status_code == 403       # the wide tier, not the cluster-admin tier
    assert c.post("/api/clusterconfigs/east/rejoin", json={"username": ADMIN, "password": ADMIN_PASSWORD}).status_code == 403
    assert remote.requests == [] and _writes(host) == []


def test_an_unknown_or_retired_name_is_404_and_nothing_is_sent(rig):
    c, app, settings, host, remote = rig
    app.state.store.upsert_cluster("gone", "https://api.gone:6443", False)
    for name in ("nope", "gone"):
        r = _rejoin(c, name)
        assert r.status_code == 404 and name in r.json()["detail"], r.text
    assert remote.requests == []


def test_no_poller_means_no_gate_and_no_login(rig):
    c, app, settings, host, remote = rig
    app.state.poller = None
    r = _rejoin(c)
    assert r.status_code == 409 and "nothing was sent" in r.json()["detail"] and remote.requests == []


def test_with_the_writes_switch_off_the_route_does_not_exist(tmp_path):
    db = str(tmp_path / "off.db"); _seed(db)
    app = build_app(_settings(db), run_poller=False)
    app.state.cluster_admin_resolver = _MapResolver({"root": "all"})
    with TestClient(app) as c:
        assert c.post("/api/clusterconfigs/c1/rejoin", headers=H("root"), json={}).status_code in (404, 405)
    assert "/api/clusterconfigs/{name}/rejoin" not in app.openapi()["paths"]


# ── the gate: once the password is on the wire, the outcome is terminal (#283, #315) ─────────────────────────

@pytest.mark.parametrize("answer,first", [
    (refused_401, "login-refused"),
    (lambda: httpx.Response(500, text="Internal Server Error"), "login-failed"),    # a LOCKED account's LDAP code 19
    (lambda: (lambda request: httpx.ReadTimeout("timed out")), "login-failed"),     # written, then no answer
], ids=["401", "500", "read-timeout"])
def test_a_bound_failure_is_one_authorize_and_the_same_password_is_not_sent_again(rig, answer, first):
    c, app, settings, host, remote = rig
    remote.answers = [answer(), login_302()]
    r1 = _rejoin(c)
    assert r1.json()["outcome"] == first and len(remote.authorize) == 1
    assert "it is not sent again" in r1.json()["message"]
    r2 = _rejoin(c, "west")                                  # another cluster: the gate is the ACCOUNT's (#315)
    assert r2.json()["outcome"] == "login-refused" and "so it was not sent" in r2.json()["message"]
    assert len(remote.authorize) == 1, "the same password reached the directory twice"
    r3 = _rejoin(c, password="Adm1n-pw-corrected")          # a different password is a different entry
    assert r3.json()["outcome"] == "rejoined" and len(remote.authorize) == 2
    assert _writes(host) == [("PUT", f"/api/v1/namespaces/{NS}/secrets/gsd-cluster-east")]


def test_a_failure_before_the_password_is_written_is_tried_once_and_is_not_gated(rig):
    """ONE_TRY: the fleet's schedule retries a failure that bound nothing; a person is waiting, so it is answered at
    once, and the password is free to be sent on the next press."""
    c, app, settings, host, remote = rig
    remote.discovery = down
    r1 = _rejoin(c)
    assert r1.json()["outcome"] == "login-failed" and "the password was not sent" in r1.json()["message"]
    assert [q.url.path for q in remote.requests] == [DISCOVERY_PATH], "one attempt, no retry"
    remote.discovery = {"issuer": OAUTH, "authorization_endpoint": f"{OAUTH}/oauth/authorize"}
    assert _rejoin(c).json()["outcome"] == "rejoined" and presented(remote) == [(ADMIN, ADMIN_PASSWORD)]


# ── D8: the remote decides, with the login's own token ─────────────────────────────────────────────────────────

def test_the_remote_says_no_so_nothing_is_read_or_written_and_the_login_is_revoked(rig, caplog):
    c, app, settings, host, remote = rig
    remote.review = review(allowed=False, reason=None)
    with caplog.at_level(logging.INFO):
        r = _rejoin(c)
    body = r.json()
    assert body["outcome"] == "not-cluster-admin" and "east says alice.admin may not update clusterrolebindings" in body["message"]
    assert "the login was signed out" in body["message"]
    assert remote.reads == [] and _writes(host) == [] and len(remote.revokes) == 1
    assert "cluster-rejoin-review cluster=east by=root account=alice.admin" in caplog.text and "allowed=false" in caplog.text
    assert app.state.poller._credential_gate.account_refusal(ADMIN, ADMIN_PASSWORD) is None, "the password was right"


@pytest.mark.parametrize("answer", [
    httpx.Response(403, text="forbidden"),
    httpx.Response(500, text="Internal Server Error"),
    httpx.Response(201, json={"kind": "SelfSubjectAccessReview", "status": {}}),
    httpx.Response(201, json={"kind": "SelfSubjectAccessReview", "status": {"allowed": "true"}}),
    lambda request: httpx.ReadTimeout("timed out"),
], ids=["403", "500", "no-status", "string-true", "timeout"])
def test_a_review_that_does_not_answer_is_a_refusal_never_a_yes(rig, answer):
    c, app, settings, host, remote = rig
    remote.review = answer
    r = _rejoin(c)
    assert r.json()["outcome"] == "access-review-failed" and "could not be asked" in r.json()["message"]
    assert remote.reads == [] and _writes(host) == [] and len(remote.revokes) == 1


def test_the_review_asks_the_configured_cluster_admin_question(tmp_path, monkeypatch, remote):
    """#322's question is configurable (visibility.clusterAdminSar); the remote is asked the host's own question."""
    host = _Host({"gsd-cluster-east": _secret()})
    app, settings = _app(tmp_path, monkeypatch, host, parse_secret(_secret(), host_name="c1"),
                         visibility_cluster_admin_sar_verb="get", visibility_cluster_admin_sar_resource="secrets",
                         visibility_cluster_admin_sar_api_group="", visibility_cluster_admin_sar_namespace="group-sync-operator")
    with TestClient(app) as c:
        r = _rejoin(c)
    assert json.loads(remote.reviews[0].content)["spec"]["resourceAttributes"] == {
        "verb": "get", "resource": "secrets", "group": "", "namespace": "group-sync-operator"}
    assert "may get secrets in namespace group-sync-operator there" in r.json()["message"]


# ── the read, the write, and one Rejoin at a time ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("secret,code", [
    (httpx.Response(404, text="not found"), "sa-token-secret-missing"),
    (httpx.Response(403, text="forbidden"), "sa-token-unreadable"),
    (httpx.Response(200, json=sa_secret(labels={INVALID_SINCE_LABEL: "2027-09-22"})), "sa-token-invalidated"),
])
def test_a_token_read_refusal_writes_nothing_and_revokes_the_login(rig, secret, code):
    c, app, settings, host, remote = rig
    remote.secret = secret
    r = _rejoin(c)
    assert r.json()["outcome"] == code and "nothing was written" in r.json()["message"]
    assert _writes(host) == [] and len(remote.revokes) == 1
    assert app.state.poller._credential_gate.account_refusal(ADMIN, ADMIN_PASSWORD) is None


def test_a_refused_write_stores_nothing_and_says_so(rig):
    c, app, settings, host, remote = rig
    host.refuse = True
    r = _rejoin(c)
    assert r.json()["outcome"] == "lookup-write-failed" and "nothing was stored" in r.json()["message"]
    assert json.loads(base64.b64decode(host.secrets["gsd-cluster-east"]["data"]["config"])) == {"bearerToken": STORED_TOKEN}


def test_one_rejoin_at_a_time_in_this_process(rig):
    """A second press — the other tab, a script, another cluster — while the first is out is refused, never queued:
    the gate's check and the login it guards are one step, so no two presses reach a password's first use."""
    c, app, settings, host, remote = rig
    inside, release, answers = threading.Event(), threading.Event(), {}

    def slow(request):
        inside.set()
        release.wait(10)
        return login_302()

    remote.answers = [slow]
    first = threading.Thread(target=lambda: answers.setdefault("first", _rejoin(c)))
    first.start()
    try:
        assert inside.wait(10), "the first login started"
        answers["second"] = _rejoin(c, "west")
    finally:
        release.set()
        first.join(10)
    assert answers["second"].status_code == 409 and "already in flight" in answers["second"].json()["detail"]
    assert answers["first"].json()["outcome"] == "rejoined" and len(remote.authorize) == 1
    remote.answers = [login_302()]
    assert _rejoin(c, "west").json()["outcome"] == "rejoined", "the slot is released when the Rejoin ends"


# ── the redaction pin (#283's, carried): the password is on one header of one request, and nowhere else ─────

def _planted(target_kind: str) -> dict:
    """One scenario's remote, with every secret in play at that point planted in every field it controls: the
    password and its Basic form from the authorize on, the login's token from the 302 on, the token read from the
    read on. A value the dashboard has not been handed yet is not its secret to scrub, and is not planted."""
    login = f"pw={ADMIN_PASSWORD} basic={BASIC}"
    session = f"{login} bearer={TOKEN}"
    read = f"{session} sa={SA_TOKEN}"
    return {
        "401": dict(answers=[refused_401(body=login)]),
        "401-challenge": dict(answers=[httpx.Response(401, headers={"Www-Authenticate": f'Basic realm="{ADMIN_PASSWORD}"'})]),
        "500": dict(answers=[httpx.Response(500, text=login)]),
        "302-error": dict(answers=[httpx.Response(302, headers={"Location": f"{OAUTH}/oauth/token/implicit#error={ADMIN_PASSWORD}"})]),
        "issuer": dict(discovery={"issuer": f"https://{ADMIN}:{ADMIN_PASSWORD}@oauth.example", "authorization_endpoint": f"{OAUTH}/oauth/authorize"}),
        "review-reason": dict(review_answer=review(reason=session, evaluationError=session)),
        "review-denied": dict(review_answer=review(allowed=False, reason=session)),
        "review-500": dict(review_answer=httpx.Response(500, text=session)),
        "read-500": dict(secret=httpx.Response(500, text=session)),
        "read-owner": dict(secret=httpx.Response(200, json=sa_secret(sa=read))),
        "revoke-500": dict(revoke=httpx.Response(500, text=read)),
        # the read is refused AFTER the token was decoded, then the revoke fails echoing it (review of the spec, C3)
        "read-refused-revoke-500": dict(secret=httpx.Response(200, json=sa_secret(sa="wrong-owner")),
                                        revoke=httpx.Response(500, text=read)),
        "write-echo": dict(host_echo=True),
        "success": {},
    }[target_kind]


@pytest.mark.parametrize("kind", ["401", "401-challenge", "500", "302-error", "issuer", "review-reason", "review-denied",
                                  "review-500", "read-500", "read-owner", "revoke-500", "read-refused-revoke-500",
                                  "write-echo", "success"])
def test_the_password_appears_on_one_header_and_nowhere_else(tmp_path, monkeypatch, remote, caplog, kind):
    """The scrub is for accidental echoes: a remote, a proxy's error page or a debug handler that quotes what it got,
    as written or as Python's or Go's JSON encoder writes it, up to two layers (SPEC_D4 §3.7 lists the set). A hostile
    remote already holds the password and can pick an encoding nothing recognises; that is stated, not claimed (§6)."""
    scenario = _planted(kind)
    for field in ("answers", "discovery", "secret", "revoke"):
        if field in scenario:
            setattr(remote, field, scenario[field])
    remote.review = scenario.get("review_answer", remote.review)
    host = _Host({"gsd-cluster-east": _secret()}, echo=scenario.get("host_echo", False))
    app, settings = _app(tmp_path, monkeypatch, host, parse_secret(_secret(), host_name="c1"))
    with caplog.at_level(logging.DEBUG), TestClient(app) as c:
        r = _rejoin(c)
    assert r.status_code == 200, r.text
    gate = app.state.poller._credential_gate
    kept = "\n".join([r.text, caplog.text, json.dumps(host.secrets), repr(gate._refused), repr(gate._spent),
                      json.dumps([f.public() for f in settings.cluster_registry.findings()]),
                      "\n".join(sqlite3.connect(settings.db_path).iterdump())])
    for value in (ADMIN_PASSWORD, BASIC, TOKEN):
        assert value not in kept, f"{kind}: a secret was kept or echoed"
    assert SA_TOKEN not in kept.replace(json.dumps(host.secrets), ""), f"{kind}: the token read was echoed"
    for request in remote.requests:                        # on the wire: the authorize's Basic header, once
        seen = f"{request.url} {request.content!r} " + " ".join(f"{k}={v}" for k, v in request.headers.items()
                                                                if not (request.url.path == "/oauth/authorize" and k == "authorization"))
        assert ADMIN_PASSWORD not in seen and BASIC not in seen, (kind, request.method, request.url.path)
    assert len(remote.authorize) <= 1


@pytest.mark.parametrize("answer", [review(reason="remote echo: xyZ"), review(allowed=False, reason="remote echo: xyZ"),
                                    httpx.Response(500, text="remote echo: xyZ")], ids=["allowed", "denied", "review-500"])
def test_short_password_echo_in_review_is_not_logged(rig, caplog, answer):
    """The emit helper skips a secret under four characters, and a password can be that short: D8's text is
    scrubbed before any line, whatever the length (review of the spec, C3)."""
    c, app, settings, host, remote = rig
    remote.review = answer
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c, password="xyZ")
    assert r.status_code == 200 and "xyZ" not in caplog.text + r.text


def _escaped(value: str, layers: int) -> str:
    for _ in range(layers):
        value = json.dumps(value)[1:-1]
    return value


def _echo(remote, phase: str, text: str) -> None:
    """Plant `text` in the free text the remote answers with at `phase`: a review's reason, or a 500's body."""
    if phase in ("allowed", "denied"):
        remote.review = review(allowed=phase == "allowed", reason=text)
    elif phase == "review-500":
        remote.review = httpx.Response(500, text=text)
    elif phase == "login-500":
        remote.answers = [httpx.Response(500, text=text)]
    else:
        remote.revoke = httpx.Response(500, text=text)


PHASES = ["allowed", "denied", "review-500", "login-500", "revoke-500"]


@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize("password", ['x"Z', "éZ"])
@pytest.mark.parametrize("layers", [1, 2])
def test_short_escaped_password_never_reaches_evidence(rig, caplog, phase, password, layers):
    """A remote may quote the password JSON-escaped, once or twice, so a quote or a non-ASCII letter changes its
    spelling. The shared escaped-form scrub stops at eight characters; Rejoin removes every spelling at any length
    (review round 1, P1)."""
    c, app, settings, host, remote = rig
    escaped = _escaped(password, layers)
    _echo(remote, phase, "remote echo: " + escaped)
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c, password=password)
    assert r.status_code == 200
    shown = caplog.text + r.json()["message"]
    assert escaped not in shown and password not in shown
    assert escaped.replace('"', "'") not in caplog.text   # a line's value has its double quotes turned single


#: Go's encoding/json.Marshal of each password, once and twice, as the Go runtime wrote them (review round 3, Codex's
#: go-spellings.json): `<`, `>`, `&`, U+2028 and U+2029 as lower-case `\\u` escapes, every other character as is.
GO_SPELLINGS = [
    ("lt", "x<Z", "x\\u003cZ", "x\\\\u003cZ"),
    ("gt", "x>Z", "x\\u003eZ", "x\\\\u003eZ"),
    ("amp", "x&Z", "x\\u0026Z", "x\\\\u0026Z"),
    ("e-lt", "é<Z", "é\\u003cZ", "é\\\\u003cZ"),
    ("e-2028", "é\u2028Z", "é\\u2028Z", "é\\\\u2028Z"),
    ("emoji", "x😀Z", "x😀Z", "x😀Z"),
]


@pytest.mark.parametrize("phase", PHASES)
@pytest.mark.parametrize("password,spelled", [
    pytest.param("x/Z", "x\\/Z", id="slash"),         # `/` as `\/`, which some encoders write
    pytest.param("éZ", "\\u00E9Z", id="hex-case"),    # `\u` hex in upper case, which other encoders write
    *(pytest.param(password, spelled, id=f"go-{name}-{layer}") for name, password, *spelled_by_layer in GO_SPELLINGS
      for layer, spelled in zip(("once", "twice"), spelled_by_layer)),
    pytest.param('x"Z', _escaped('x"Z', 3), id="triple", marks=pytest.mark.xfail(strict=True, reason=(
        "a stated residual (SPEC_D4 §6): three layers of escaping are no accidental echo, and the scrub covers two"))),
])
def test_other_json_spellings_never_reach_evidence(rig, caplog, phase, password, spelled):
    """Real JSON encoders also write `/` as `\\/` and `\\u` hex in upper case (review round 2), and Go's, the remote's
    own, escapes five characters and leaves the rest as is (round 3). Three layers are left, stated: a hostile remote
    holds the password anyway."""
    c, app, settings, host, remote = rig
    _echo(remote, phase, "remote echo: " + spelled)
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c, password=password)
    shown = caplog.text + r.json()["message"]
    assert r.status_code == 200 and spelled not in shown and password not in shown
    assert spelled.replace('"', "'") not in caplog.text


@pytest.mark.parametrize("spelled", [_escaped('x"Z', 1), 'x"Z'], ids=["escaped", "raw"])
def test_a_password_across_the_reviews_200_character_cut_leaves_no_fragment(rig, caplog, spelled):
    """D8's client quotes a failed answer's body cut at 200 characters. A password straddling the cut left a fragment
    no later scrub could recognise, so every spelling is removed before the cut (review round 2)."""
    c, app, settings, host, remote = rig
    remote.review = httpx.Response(500, text="Q" * 198 + spelled)
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c, password='x"Z')
    fragment = "Q" * 198 + spelled[:2]
    shown = caplog.text + r.json()["message"]
    assert r.status_code == 200 and fragment not in shown and fragment.replace('"', "'") not in caplog.text


@pytest.mark.parametrize("phase", ["review", "store"])
@pytest.mark.parametrize("revoke_status", [200, 500])
def test_unexpected_error_still_reports_cleanup(rig, monkeypatch, caplog, phase, revoke_status):
    """An unexpected error after the login exists still says how the login ended: signed out, or the token to delete
    (review round 1, P2). The error's own words never appear."""
    c, app, settings, host, remote = rig

    def explode(*args, **kwargs):
        raise RuntimeError(ADMIN_PASSWORD)
    monkeypatch.setattr("gsd.rejoin." + ("remote_says_cluster_admin" if phase == "review" else "store"), explode)
    remote.revoke = httpx.Response(revoke_status, text="answer")
    with caplog.at_level(logging.DEBUG):
        r = _rejoin(c)
    message = r.json()["message"]
    assert r.json()["outcome"] == "rejoin-failed" and len(remote.revokes) == 1
    if revoke_status == 500:
        assert "could NOT be signed out" in message and "oc delete useroauthaccesstokens" in message
    else:
        assert "the login was signed out" in message
    assert ADMIN_PASSWORD not in r.text + caplog.text


@pytest.mark.parametrize("where", ["remote_says_cluster_admin", "RejoinLogin"])
def test_unexpected_exception_cannot_escape_with_secrets(rig, monkeypatch, caplog, where):
    """An error the design did not expect may quote the password. It never leaves the route, so the server has no
    traceback to print: the answer and the line are fixed text. Inside the exchange Rejoin answers it and the login is
    still revoked; before a login exists the route does (review, C3; round 1, P2)."""
    c, app, settings, host, remote = rig

    def explode(*args, **kwargs):
        raise RuntimeError(f"{ADMIN_PASSWORD} {BASIC} {TOKEN}")
    monkeypatch.setattr(f"gsd.rejoin.{where}", explode)
    with caplog.at_level(logging.DEBUG):
        r = TestClient(app, raise_server_exceptions=False).post(
            "/api/clusterconfigs/east/rejoin", headers=H("root"), json={"username": ADMIN, "password": ADMIN_PASSWORD})
    assert r.status_code == 200 and r.json()["outcome"] == "rejoin-failed", r.text
    assert all(secret not in r.text + caplog.text for secret in (ADMIN_PASSWORD, BASIC, TOKEN))
    assert len(remote.revokes) == (where == "remote_says_cluster_admin") and _writes(host) == []


def test_dialog_does_not_promise_to_control_password_managers():
    """The dialog says what the dashboard controls and nothing more (review of the spec, C3): the HTML Standard lets
    a browser override autocomplete="off", and the Secret records the username. It says the gate's scope (D4-7)."""
    page = (REPO / "local-development/gsd/static/index.html").read_text()
    start = page.index('<dialog id="rejoin-dialog"')
    dialog = " ".join(page[start:page.index("</dialog>", start)].split())   # the source wraps its sentences
    assert "password managers may ignore" in dialog
    assert "Secret records your username" in dialog
    assert "Your username and password are used for this one login and are not stored" not in dialog
    assert "A restarted pod or another replica" in dialog


# ── the budget over the system ───────────────────────────────────────────────────────────────────────────────

#: SPEC_D4 §2's rows: (the remote's answers in order, the presses as (process, password)). A new process name is a
#: restart or a second replica: its own poller gate, over the same host and remote.
OTHER = "https://elsewhere.example"


def _moved(status: int, host: str) -> httpx.Response:
    """An authorize answered by a redirect that carries no token: the password was sent, and no session came back."""
    return httpx.Response(status, headers={"Location": f"{host}/oauth/token/implicit#error=access_denied"})


BUDGET = {
    "one press, the right password": ([login_302()], [("p", ADMIN_PASSWORD)]),
    "two presses, the right password": ([login_302(), login_302()], [("p", ADMIN_PASSWORD)] * 2),
    "a 401, then the same password": ([refused_401(), login_302()], [("p", "Wr0ng-pw-1")] * 2),
    "a 500 (a locked account), then the same password": ([httpx.Response(500), login_302()], [("p", "L0cked-pw-1")] * 2),
    "a timeout after the password was sent, then the same": (
        [lambda request: httpx.ReadTimeout("timed out"), login_302()], [("p", "T1meout-pw-1")] * 2),
    "a 401, then the right password": ([refused_401(), login_302()], [("p", "Wr0ng-pw-2"), ("p", ADMIN_PASSWORD)]),
    "a 401, then the same password on a restarted process": (
        [refused_401(), refused_401()], [("p", "Wr0ng-pw-3"), ("restarted", "Wr0ng-pw-3")]),
    "a 401, then the same password on a second replica": (
        [refused_401(), refused_401()], [("p", "Wr0ng-pw-4"), ("replica", "Wr0ng-pw-4")]),
    "a 302 without a token, then the same": ([_moved(302, OAUTH), login_302()], [("p", "N0-token-pw-1")] * 2),
    "a 302 to another host, then the same": ([_moved(302, OTHER), login_302()], [("p", "N0-token-pw-2")] * 2),
    "a 307 to another host, then the same": ([_moved(307, OTHER), login_302()], [("p", "N0-token-pw-3")] * 2),
    "a proxy replaying a successful press to another pod": (
        [login_302(), login_302()], [("p", ADMIN_PASSWORD), ("replica", ADMIN_PASSWORD)]),
}


def test_the_budget_over_the_system(tmp_path, monkeypatch, remote):
    """SPEC_D4 §2's table, measured: authorize requests on the wire for each shape. One press presents the password
    at most once, and a password the directory answered is not presented again by that process. A restart, a second
    replica and a replay to another pod each meet an empty gate: the stated scope (D4-7)."""
    host = _Host({"gsd-cluster-east": _secret()})
    east = parse_secret(_secret(), host_name="c1")
    measured = {}
    for n, (shape, (answers, presses)) in enumerate(BUDGET.items()):
        remote.requests.clear()
        remote.answers = list(answers)
        outcomes, clients = [], {}
        for process_name, password in presses:
            if process_name not in clients:
                app, _ = _app(tmp_path, monkeypatch, host, east, name=f"budget-{n}-{process_name}")
                clients[process_name] = TestClient(app).__enter__()
            outcomes.append(_rejoin(clients[process_name], password=password).json()["outcome"])
        for client in clients.values():
            client.__exit__(None, None, None)
        measured[shape] = (len(remote.authorize), outcomes)
    assert measured == {
        "one press, the right password": (1, ["rejoined"]),
        "two presses, the right password": (2, ["rejoined", "rejoined"]),
        "a 401, then the same password": (1, ["login-refused", "login-refused"]),
        "a 500 (a locked account), then the same password": (1, ["login-failed", "login-refused"]),
        "a timeout after the password was sent, then the same": (1, ["login-failed", "login-refused"]),
        "a 401, then the right password": (2, ["login-refused", "rejoined"]),
        "a 401, then the same password on a restarted process": (2, ["login-refused", "login-refused"]),
        "a 401, then the same password on a second replica": (2, ["login-refused", "login-refused"]),
        "a 302 without a token, then the same": (1, ["login-failed", "login-refused"]),
        "a 302 to another host, then the same": (1, ["login-failed", "login-refused"]),
        "a 307 to another host, then the same": (1, ["login-failed", "login-refused"]),
        "a proxy replaying a successful press to another pod": (2, ["rejoined", "rejoined"]),
    }, measured


# ── the runbook (the 2026-09-23 requirement) ───────────────────────────────────────────────────────────────

def test_the_runbook_sits_beside_the_values_with_six_sections_and_docs_links_it():
    runbook = REPO / "charts/group-sync-dashboard/RUNBOOK.md"
    headings = re.findall(r"^## (\d)\. ", runbook.read_text(), re.M)
    assert headings == ["1", "2", "3", "4", "5", "6"], headings
    assert "../charts/group-sync-dashboard/RUNBOOK.md" in (REPO / "docs/README.md").read_text()
    assert "(RUNBOOK.md)" in (REPO / "charts/group-sync-dashboard/README.md").read_text()
    credentials = (REPO / "charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md").read_text()
    assert "Rejoin **PLANNED**" not in credentials and "(RUNBOOK.md)" in credentials
```

<!-- block: local-development/tests/test_api_contract.py | edit -->
```python
    "POST /api/clusterconfigs/{name}/refresh",     # SPEC_D3 (#311): a probe that writes nothing, carved out like /test
```

```python
    "POST /api/clusterconfigs/{name}/refresh",     # SPEC_D3 (#311): a probe that writes nothing, carved out like /test
    "POST /api/clusterconfigs/{name}/rejoin",      # SPEC_D4 (#316): a person's one login, then the Secret write
```

<!-- block: local-development/tests/test_api_contract.py | edit -->
```python
    """The carve-out, exact: with the switch on the schema carries these five non-GET routes and no
    other; any sixth, on or off, fails here or above."""
```

```python
    """The carve-out, exact: with the switch on the schema carries these six non-GET routes and no
    other; any seventh, on or off, fails here or above."""
```

<!-- block: local-development/tests/test_clusterconfig.py | edit -->
```python
                              "onboarding_configmap": None}
```

```python
                              "onboarding_configmap": None, "rejoinable": True}
```

<!-- block: local-development/tests/test_ui.py | edit -->
```python
            assert "Rejoin (#316), not built yet" in refused and page.locator("#cc-cluster-east [data-cc-rejoin]").count() == 0
```

```python
            # #316 (SPEC_D4): the next step is Rejoin, drawn where the route accepts it — the Secret row here
            assert "use Rejoin" in refused and page.locator("#cc-cluster-east [data-cc-rejoin]").count() == 1
```

<!-- block: local-development/tests/test_ui.py | edit -->
```python
            assert page.locator("[data-cc-refresh]").count() == 0
        finally:
            gate.set()
```

```python
            assert page.locator("[data-cc-refresh], [data-cc-rejoin]").count() == 0
        finally:
            gate.set()

    def test_rejoin_is_offered_after_a_refused_refresh_and_its_dialog_keeps_what_is_typed(self, page, cc_rig, monkeypatch):
        """#316 (SPEC_D4 §3.6): Rejoin appears only where the route accepts it (`rejoinable`) and only once Refresh said
        the stored credential is refused. Its dialog is static, outside #main, so the minute's repaint keeps what is
        typed; there is no form, so no submission can carry the password into a URL; Cancel clears both fields."""
        from gsd.kube import AUTH_FAILED, ClusterClient, ClusterError
        base, host, settings = cc_rig

        class _Refused(ClusterClient):
            def _client(self):
                import contextlib
                return contextlib.nullcontext(object())

            def _get(self, client, path, params):
                raise ClusterError(AUTH_FAILED, "401 Unauthorized — token invalid or expired")

        monkeypatch.setattr("gsd.clusterconfig.writer.ClusterClient", _Refused)
        _open_as(page, base, "root")
        page.click("#tab-clusters"); page.wait_for_selector("#cc-cluster-east")
        assert page.locator("[data-cc-rejoin]").count() == 0, "no Rejoin before Refresh has said anything"
        page.click("#cc-refresh-east")
        page.wait_for_selector("#cc-rejoin-east")
        assert page.locator("#cc-cluster-east .cc-acts #cc-refresh-east + #cc-rejoin-east + #cc-delete-east").count() == 1
        assert "use Rejoin" in page.locator("#cc-refresh-result-east").inner_text()
        # the host and the values entry are refused by the route, so they are never offered it, refused or not
        page.click("#cc-refresh-crc-local"); page.click("#cc-refresh-prod-east")
        page.wait_for_function("() => ['crc-local', 'prod-east'].every((id) => (view.clusterRefresh[id] || {}).state === 'done')")
        assert page.locator("#cc-rejoin-crc-local, #cc-rejoin-prod-east").count() == 0
        assert "Replace the credential where it is written" in page.locator("#cc-refresh-result-prod-east").inner_text()
        page.click("#cc-rejoin-east")
        page.wait_for_selector("#rejoin-dialog[open]")
        assert page.evaluate("() => !document.getElementById('main').contains(document.getElementById('rejoin-dialog'))")
        text = page.locator("#rejoin-dialog").inner_text()
        assert "Rejoin east" in text and "is used for this one login and is not saved" in text and "decided there" in text
        assert "https://api.east.example:6443" in text and "gsd-cluster-east" in text
        assert page.locator("#rejoin-password").get_attribute("type") == "password"
        assert page.locator("#rejoin-username").get_attribute("autocomplete") == "off" == page.locator("#rejoin-password").get_attribute("autocomplete")
        assert page.locator("#rejoin-dialog form").count() == 0
        page.fill("#rejoin-username", "alice.admin"); page.fill("#rejoin-password", "Adm1n-pw-typed")
        # a real repaint of #main, proved by a marker the old button carries and the new one lacks
        page.evaluate("() => { document.getElementById('cc-rejoin-east').dataset.old = '1'; lastFingerprint = null; return refresh({ auto: true }); }")
        page.wait_for_function("() => !document.getElementById('cc-rejoin-east').dataset.old")
        assert page.input_value("#rejoin-username") == "alice.admin" and page.input_value("#rejoin-password") == "Adm1n-pw-typed"
        assert page.evaluate("() => document.getElementById('rejoin-dialog').open")
        page.set_viewport_size({"width": 375, "height": 812}); page.wait_for_timeout(200)
        box = page.locator("#rejoin-dialog").bounding_box()
        assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth") and box["x"] >= 0 and box["x"] + box["width"] <= 375
        page.click("#rejoin-cancel")
        page.wait_for_function("() => !document.getElementById('rejoin-dialog').open")
        assert page.input_value("#rejoin-username") == "" and page.input_value("#rejoin-password") == ""
        page.click("#cc-rejoin-east"); page.wait_for_selector("#rejoin-dialog[open]")
        page.fill("#rejoin-password", "Adm1n-pw-escaped"); page.keyboard.press("Escape")   # closes without closeRejoin
        page.wait_for_function("() => !document.getElementById('rejoin-dialog').open && !document.getElementById('rejoin-password').value")
        page.evaluate("() => { data.clusterconfigs.secrets.writes = false; render(); }")
        assert page.locator("[data-cc-rejoin]").count() == 0, "absent, not disabled, where the writes are off"

    def test_one_press_sends_the_password_once_and_the_page_keeps_it_nowhere(self, page, cc_rig, monkeypatch):
        """#316 (SPEC_D4 §3.6, §2): a press is one request carrying the typed password once. The field is emptied as the
        request leaves, so a double click, and a second press before it is typed again, send nothing more. A refusal
        keeps the dialog open with its sentence; a success closes it; both land on the card. The password is in no
        storage, no URL and no page state, and pagehide and the idle timeout clear what is typed."""
        import threading
        from gsd.fleetlookup import CredentialGate
        from gsd.kube import AUTH_FAILED, ClusterClient, ClusterError
        base, host, settings = cc_rig
        release, calls, answers = threading.Event(), [], ["login-refused", "rejoined"]

        class _Refused(ClusterClient):
            def _client(self):
                import contextlib
                return contextlib.nullcontext(object())

            def _get(self, client, path, params):
                raise ClusterError(AUTH_FAILED, "401 Unauthorized — token invalid or expired")

        class _Poller:
            _credential_gate = CredentialGate()

            def request_discovery(self):
                pass

        def rejoin(cluster, settings, host_client, *, own_namespace, gate, username, password, viewer):
            calls.append((cluster.name, username, password, viewer))
            release.wait(10)
            return {"outcome": answers.pop(0), "message": "the remote said so", "at": "2026-09-27T14:05:40Z"}

        monkeypatch.setattr("gsd.clusterconfig.writer.ClusterClient", _Refused)
        monkeypatch.setattr(_SCOPED_APP.state, "poller", _Poller(), raising=False)
        monkeypatch.setattr("gsd.rejoin.rejoin", rejoin)
        posts: list[str] = []
        page.on("request", lambda r: posts.append(r.post_data) if r.method == "POST" and r.url.endswith("/rejoin") else None)
        kept = "() => JSON.stringify([Object.entries(localStorage), Object.entries(sessionStorage), location.href, JSON.stringify(view)])"
        try:
            _open_as(page, base, "root")
            page.click("#tab-clusters"); page.wait_for_selector("#cc-cluster-east")
            page.click("#cc-refresh-east"); page.wait_for_selector("#cc-rejoin-east")
            page.click("#cc-rejoin-east"); page.wait_for_selector("#rejoin-dialog[open]")
            page.fill("#rejoin-username", "alice.admin"); page.fill("#rejoin-password", "Adm1n-pw-once")
            page.dblclick("#rejoin-go")
            page.wait_for_selector("#cc-rejoin-east[disabled][aria-busy='true']")
            assert page.input_value("#rejoin-password") == "", "emptied as the request left"
            assert "Adm1n-pw-once" not in page.evaluate(kept)
            release.set()
            page.wait_for_function("() => (document.getElementById('cc-rejoin-result-east') || {innerText: ''}).innerText.includes('login-refused')")
            release.clear()
            assert page.evaluate("() => document.getElementById('rejoin-dialog').open") and "login-refused" in page.inner_text("#rejoin-msg")
            page.click("#rejoin-go")                                     # nothing typed again: nothing is sent
            assert "Type your username and your password" in page.inner_text("#rejoin-msg")
            assert [json.loads(p) for p in posts] == [{"username": "alice.admin", "password": "Adm1n-pw-once"}]
            page.fill("#rejoin-password", "Adm1n-pw-twice"); page.press("#rejoin-password", "Enter")
            release.set()
            page.wait_for_function("() => !document.getElementById('rejoin-dialog').open")
            assert "rejoined" in page.inner_text("#cc-rejoin-result-east")
            assert [c[1:] for c in calls] == [("alice.admin", "Adm1n-pw-once", "root"), ("alice.admin", "Adm1n-pw-twice", "root")]
            assert len(posts) == 2 and not any(p in page.evaluate(kept) for p in ("Adm1n-pw-once", "Adm1n-pw-twice"))
            # pagehide (the back/forward cache keeps typed values) and the idle timeout both clear the fields
            page.click("#cc-rejoin-east"); page.wait_for_selector("#rejoin-dialog[open]")
            page.fill("#rejoin-username", "alice.admin"); page.fill("#rejoin-password", "Adm1n-pw-left")
            page.evaluate("() => window.dispatchEvent(new Event('pagehide'))")
            assert page.input_value("#rejoin-username") == "" and page.input_value("#rejoin-password") == ""
            page.fill("#rejoin-password", "Adm1n-pw-left")
            page.evaluate("() => { idle.logoutUrl = null; idleExpire(); }")
            assert not page.evaluate("() => document.getElementById('rejoin-dialog').open")
            assert page.input_value("#rejoin-password") == ""
        finally:
            release.set()

    def test_fetch_refuses_redirects_and_submits_once(self, page, cc_rig, monkeypatch):
        """#316 (review of the spec, C1): a 307 or 308 in front of the dashboard would re-send the POST, password and
        all, to its Location (measured in Chromium). The credential fetch refuses redirects and is sent once."""
        from gsd.kube import AUTH_FAILED, ClusterClient, ClusterError
        base, host, settings = cc_rig

        class _Refused(ClusterClient):
            def _client(self):
                import contextlib
                return contextlib.nullcontext(object())

            def _get(self, client, path, params):
                raise ClusterError(AUTH_FAILED, "401 Unauthorized — token invalid or expired")

        monkeypatch.setattr("gsd.clusterconfig.writer.ClusterClient", _Refused)
        seen: list[tuple[str, str]] = []
        page.on("request", lambda r: seen.append((r.method, r.url)))
        page.route("**/api/clusterconfigs/east/rejoin",
                   lambda route: route.fulfill(status=307, headers={"Location": f"{base}/elsewhere"}))
        _open_as(page, base, "root")
        page.click("#tab-clusters"); page.wait_for_selector("#cc-cluster-east")
        page.click("#cc-refresh-east"); page.wait_for_selector("#cc-rejoin-east")
        page.click("#cc-rejoin-east"); page.wait_for_selector("#rejoin-dialog[open]")
        page.fill("#rejoin-username", "alice.admin"); page.fill("#rejoin-password", "Adm1n-pw-redirected")
        page.click("#rejoin-go")
        page.wait_for_function("() => (view.clusterRejoin.east || {}).state === 'done'")
        assert [url for method, url in seen if url.endswith("/elsewhere")] == [], "the 307 carried the password on"
        assert [url for method, url in seen if method == "POST" and url.endswith("/rejoin")] == [
            f"{base}/api/clusterconfigs/east/rejoin"]
        assert page.evaluate("() => view.clusterRejoin.east.outcome") == "unknown"
```

<!-- block: charts/group-sync-dashboard/RUNBOOK.md | create -->
```markdown
# Runbook — a remote cluster's connection is broken: Refresh, then Rejoin

The dashboard polls each remote cluster with a token it keeps in a Secret, `gsd-cluster-<name>`. When that token
stops working, this runbook finds out why and repairs it. Why it works this way is in
[`CLUSTER_CREDENTIALS.md`](CLUSTER_CREDENTIALS.md), beside this file. This page is only the steps.

Refresh and Rejoin are on the Cluster Configurations tab. They need two things: you pass the dashboard's
cluster-admin tier (`visibility.clusterAdminSar`), and the release sets `clusterConfig.secrets.writes.enabled: true`.
Without that switch the tab has no Refresh and no Rejoin, and section 5 is the path. Commands run from a workstation
with `oc` and `jq`, logged in to the dashboard's cluster, with a second kubeconfig context logged in to the remote
cluster as yourself. Set these once:

~~~sh
NS=group-sync-dashboard; REL=group-sync-dashboard   # the release namespace and fullname (oc get deploy -n $NS)
C=shared-qa                                         # the cluster, by the name on its card
REMOTE=shared-qa-me                                 # your kubeconfig context on that cluster (oc config get-contexts)
~~~

## 1. Decide whether the connection is actually broken

On the Cluster Configurations tab, find the cluster's card and press **Refresh**. It probes the cluster with the
token the dashboard already holds. It never logs in and changes nothing. The same answer is in the pod's log:

~~~sh
oc logs -n $NS deploy/$REL -c dashboard --since=15m | grep -E "cluster-(unreachable|refreshed) .*cluster=$C " | tail -3
~~~

The word under the card's `connection` row, or `outcome=` in the line, says what to do next:

| outcome | what it means | next |
|---|---|---|
| `connected` (`ok` in the log) | the stored token works | nothing is broken; the card turns green at the next poll |
| `auth_failed` | the remote refused the stored token: expired, revoked, or wrong | section 2, then 3 |
| `pending` | no token was ever fetched: a `saTokenLookup` cluster whose lookup has not written its Secret | section 3 |
| `forbidden` | the token works, but the remote's RBAC does not let it read | section 4 |
| `unreachable` | the network, DNS, or the API server | section 4 |
| `cert-verify-failed` | the dashboard does not trust the remote's certificate | section 4 |
| `not-probed` | a `userSelfLogin` cluster: its credential is a session, which the card's credential row shows | not Rejoin; see `CLUSTER_CREDENTIALS.md` |

## 2. Confirm the token on the remote before you rejoin

A token that still works on the remote means the problem is elsewhere, and Rejoin will not fix it. Present the stored
token to the remote, through your remote context:

~~~sh
oc get secret -n $NS gsd-cluster-$C -o jsonpath='{.data.config}' | base64 -d | jq -r .bearerToken \
  | xargs -I{} oc --context="$REMOTE" whoami --token={}
~~~

- `system:serviceaccount:group-sync-operator:group-sync-dashboard-cluster-poller`: the token works. Go to section 4.
- `error: You must be logged in to the server (Unauthorized)`: the token is refused. Rejoin fixes this.

Then check the two things Rejoin needs on the remote:

~~~sh
oc --context="$REMOTE" auth can-i update clusterrolebindings.rbac.authorization.k8s.io
oc --context="$REMOTE" get secret -n group-sync-operator group-sync-dashboard-cluster-poller-token \
  -o jsonpath='{.type}{"  invalid-since="}{.metadata.labels.kubernetes\.io/legacy-token-invalid-since}{"\n"}'
~~~

- `yes`: you are a cluster administrator there, so Rejoin will accept you. `no`: ask someone who is.
- `kubernetes.io/service-account-token  invalid-since=` with nothing after the `=`: the token Secret is there and
  alive. `NotFound`, or a date after `invalid-since=`, is section 4.

## 3. Rejoin from the UI

**Who may do it.** Someone who passes the dashboard's cluster-admin tier **and** is a cluster administrator of the
remote. The dashboard asks the remote, with your own login, whether you may `update clusterrolebindings` there. If
it says no, nothing is read or written. Use **your own** account: the dashboard refuses the fleet account's name.

**What to do.** On the card, once Refresh answers `auth_failed` or `pending`, press **Rejoin…**. Type your username
and password for that cluster, and press **Rejoin**.

**What it does.** One login to the remote as you, and one question to the remote about you. One read of
`group-sync-operator/group-sync-dashboard-cluster-poller-token`. The login is signed out, and the token is written to
`gsd-cluster-<name>` here. Your password is used for that one login and is not stored. The Secret records your
username as `rejoin-account`.

**How to confirm it worked.** The card's `Rejoin:` line reads `rejoined`, and **Refresh** then reads `connected`.
The Secret carries the Rejoin's provenance:

~~~sh
oc get secret -n $NS gsd-cluster-$C -o json \
  | jq '.metadata.annotations | with_entries(select(.key | startswith("groupsync-dashboard.io/")))'
~~~

~~~json
{
  "groupsync-dashboard.io/rejoin-account": "alice",
  "groupsync-dashboard.io/rejoined-at": "2026-09-27T14:05:40Z",
  "groupsync-dashboard.io/rejoined-by": "alice",
  "groupsync-dashboard.io/source-namespace": "group-sync-operator",
  "groupsync-dashboard.io/source-service-account": "group-sync-dashboard-cluster-poller",
  "groupsync-dashboard.io/token-source": "rejoin"
}
~~~

`rejoined-by` is who pressed Rejoin, as the dashboard knows them. `rejoin-account` is the account the remote signed
in. A Secret the tab or the lookup created also keeps its `managed-by`. The pod's log has the remote's answer and the
outcome:

~~~sh
oc logs -n $NS deploy/$REL -c dashboard --since=15m | grep -E "cluster-rejoin(ed|-review|-failed) .*cluster=$C "
~~~

Your login is in the remote's audit log under your name. When login capture reads that cluster, the Logins tab lists
it as a `cli` login there; `kubeadmin`'s logins are never listed.

## 4. When Rejoin is not the answer

A new token fixes only a refused token. For everything else, Rejoin either refuses or repeats the failure:

| what you see | why Rejoin does not help | what fixes it |
|---|---|---|
| `forbidden` on Refresh | the token works; the remote's RBAC is missing | bind the poller ServiceAccount to the dashboard's reader ClusterRole on the remote |
| `unreachable` on Refresh | nothing answered | the cluster's API URL, DNS, a NetworkPolicy or a proxy, from this pod |
| `cert-verify-failed` on Refresh | the trust is wrong | the cluster's CA (`tlsClientConfig.caData`) or the chart's `trustedCA` |
| `sa-token-secret-missing` from Rejoin | the remote has no token Secret to read | create it there: a `kubernetes.io/service-account-token` Secret named `group-sync-dashboard-cluster-poller-token`, annotated `kubernetes.io/service-account.name: group-sync-dashboard-cluster-poller` |
| `sa-token-invalidated` from Rejoin | the remote's legacy-token cleaner killed that token | delete and recreate that Secret on the remote |
| `not-cluster-admin` from Rejoin | the remote says you may not `update clusterrolebindings` there | ask a cluster administrator of the remote |
| `login-failed` from Rejoin, saying the password was not sent | the dashboard could not reach the remote's login | the checks for `unreachable`; the trust must cover the OAuth route too |

## 5. The manual fallback, when the UI is not available

The two-cluster path. It needs someone who is cluster-admin on **both** clusters, with two sessions open.

~~~sh
# on the REMOTE cluster: a token for the poller ServiceAccount (it expires after --duration)
oc --context="$REMOTE" create token group-sync-dashboard-cluster-poller -n group-sync-operator --duration=20m

# on the DASHBOARD's cluster: the whole config, not only the token, because a merge replaces the config value.
# Keep the tlsClientConfig the Secret has now: oc get secret -n $NS gsd-cluster-$C -o jsonpath='{.data.config}' | base64 -d
oc patch secret gsd-cluster-$C -n $NS --type=merge \
  -p '{"stringData":{"config":"{\"bearerToken\":\"<token>\",\"tlsClientConfig\":{\"insecure\":false}}"}}'
~~~

A token from `oc create token` expires. To store the long-lived token that Rejoin stores, read `.data.token` of
`group-sync-operator/group-sync-dashboard-cluster-poller-token` on the remote instead, and base64-decode it.

A Secret written by `oc` rides the discovery cadence: it takes effect within `discoveryIntervalSeconds` (300 seconds
by default), not in seconds as a write from the tab does. It carries no provenance either: nothing on it says who
wrote it or where the token came from.

## 6. What not to do

- **Do not press Rejoin again and again.** Once your password is sent, the answer is final. The pod that sent it
  does not send a refused password again while it is the same password. A restarted pod, or another replica behind
  the Route, does not know that and can send it once more, so check before you press again. A locked directory
  account answers LDAP code 19, which OpenShift turns into an **HTTP 500, not a 401**, so trying again only locks it
  further. After a 500, check the account with your directory's administrators first. That pod holds the password
  back until it restarts, even once the account is fixed; a new password works at once.
- **Do not type the fleet account's password into Rejoin.** The dashboard refuses the fleet account's name, and a
  lockout of that account stops every cluster.
- **If the dialog says the answer did not arrive, or the pod restarted during a Rejoin, do not rejoin blindly.**
  Press Refresh first: the Rejoin may have finished. Then list your password logins on the remote and delete any the
  dashboard did not sign out. A token's name is not a secret and cannot log anyone in.

~~~sh
oc --context="$REMOTE" get useroauthaccesstokens --field-selector=clientName=openshift-challenging-client \
  --sort-by=.metadata.creationTimestamp
oc --context="$REMOTE" delete useroauthaccesstokens <name>
~~~
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
## 4. Recovering a cluster today

There is **no in-product way** to re-establish a credential. Today it is done by hand, and it
requires being cluster-admin on **both** clusters with two sessions:
```

```markdown
## 4. Recovering a cluster by hand

With writes on, Rejoin (§5) re-establishes a credential from the tab. Without writes, or without the UI, it is done
by hand, and it requires being cluster-admin on **both** clusters with two sessions. The steps, with what each
answer means, are in [`RUNBOOK.md`](RUNBOOK.md), beside this file:
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
## 5. The intended recovery flow — Refresh **BUILT**, Rejoin **PLANNED**
```

```markdown
## 5. The recovery flow — Refresh, then Rejoin
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
**Rejoin (#316).** When Refresh reports `auth_failed`, an administrator clicks Rejoin and supplies
**their own** cluster-admin username and password *at that moment*. The dashboard authenticates to
the remote cluster as that person, retrieves the ServiceAccount token, writes
`gsd-cluster-<name>`, and **discards the credentials**. Nothing is stored.
```

```markdown
**Rejoin (#316, `docs/specs/SPEC_D4_cluster_rejoin.md`).** When Refresh reports `auth_failed`, or `pending` for a
cluster whose token was never fetched, the card offers **Rejoin…** on a Secret-sourced cluster or a `saTokenLookup`
stanza. An administrator types **their own** username and password for that cluster, *at that moment*. The dashboard
logs in to the remote once as that person (`gsd/rejoin.py#RejoinLogin`), asks the remote whether that person may
`update clusterrolebindings` there (D8, one `SelfSubjectAccessReview` with the login's own token), reads the poller's
token Secret, signs the login out, and writes `gsd-cluster-<name>` with `token-source: rejoin` and the person's name
(`rejoined-by`, `rejoin-account`, `rejoined-at`). **The password is discarded**: nothing about it is stored. The route is
`POST /api/clusterconfigs/{name}/rejoin` (`local-development/API.md`), and the steps are in
[`RUNBOOK.md`](RUNBOOK.md).
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
- Rejoin's credentials are never stored, never logged, never echoed — in the Secret, a finding, or an
  error.
- The credential gate still applies to Rejoin: once a password is on the wire the outcome is
  terminal. No retry on a 401, and **none on the HTTP 500 a locked directory returns** — a locked
  389-ds account answers LDAP code 19, which OpenShift surfaces as a 500, so "it failed, try again"
  is wrong precisely when the account is already locked.
- Both are admin-tier only.
```

```markdown
- Rejoin's password is never stored, never logged, never echoed — in the Secret, a finding, or an
  error. The Secret records the username as provenance (`rejoin-account`).
- The credential gate still applies to Rejoin: once a password is on the wire the outcome is
  terminal. No retry on a 401, and **none on the HTTP 500 a locked directory returns** — a locked
  389-ds account answers LDAP code 19, which OpenShift surfaces as a 500, so "it failed, try again"
  is wrong precisely when the account is already locked. A Rejoin sends the password at most once per
  press, and the poller's gate holds a refused password back in that pod until it restarts. The gate
  lives in memory, so a press that reaches a restarted pod or another replica can send the same
  password once more. A durable hold keyed by the username alone was declined for its operating cost:
  any failure would block that account's Rejoin on every pod until someone deleted the hold by hand,
  even after the right password (SPEC_D4, D4-7).
- Rejoin never uses the fleet account: it refuses any name a fleet path logs in as, and it writes
  `rejoin-account`, never `lookup-account`, which the daily ping logs in as with the fleet password.
- Both are for the cluster-admin tier only (#322), and exist only with writes on.
```

<!-- block: charts/group-sync-dashboard/README.md | edit -->
```markdown
[`CLUSTER_CREDENTIALS.md`](CLUSTER_CREDENTIALS.md), beside this file.
```

```markdown
[`CLUSTER_CREDENTIALS.md`](CLUSTER_CREDENTIALS.md), beside this file. The repair itself, step by step (Refresh,
then Rejoin, then the manual fallback), is [`RUNBOOK.md`](RUNBOOK.md).
```

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->
```yaml
  #   Rejoin (#316), when it is built
```

```yaml
  #   Rejoin (#316) — and, asked of the REMOTE with the person's own login, the same question decides whether a
  #     Rejoin may read the token Secret there (SPEC_D4, D8)
```

<!-- block: docs/README.md | edit -->
```markdown
- [RUNBOOK_backup_restore.md](RUNBOOK_backup_restore.md) — back up and restore the dashboard's history.
```

```markdown
- [RUNBOOK_backup_restore.md](RUNBOOK_backup_restore.md) — back up and restore the dashboard's history.
- [RUNBOOK.md](../charts/group-sync-dashboard/RUNBOOK.md) — a remote cluster's connection is broken: find out why, then Refresh and Rejoin; kept beside the chart's values.
```

<!-- block: local-development/API.md | edit -->
```markdown
`/api/whoami`'s `visibility.cluster_admin`) and the four write routes below; `can.manage` is `true`
```

```markdown
`/api/whoami`'s `visibility.cluster_admin`) and the write routes below; `can.manage` is `true`
```

<!-- block: local-development/API.md | edit -->
```markdown
### The Cluster Configurations tab's writes (#230 S2)

Five routes, all the cluster-admin tier (above — never the wide tier) and each needing a proxy-verified
```

```markdown
**`rejoinable`** (#316) is on every live row: `true` where `POST /api/clusterconfigs/{name}/rejoin` accepts the
cluster — a Secret-sourced cluster that does not declare `userSelfLogin` and was not generated from a ConfigMap, or a
`saTokenLookup` stanza — and `false` for the host, a values entry with its own credential, a `userSelfLogin` cluster and
a ConfigMap-generated one. It is the route's own rule (`gsd/rejoin.py#refusal`). A retired row carries none.

### The Cluster Configurations tab's writes (#230 S2)

Six routes, all the cluster-admin tier (above — never the wide tier) and each needing a proxy-verified
```

<!-- block: local-development/API.md | edit -->
```markdown
same cluster is running in this process is `409`. One `cluster-refreshed` line per call, with no credential.
```

```markdown
same cluster is running in this process is `409`. One `cluster-refreshed` line per call, with no credential.

`POST /api/clusterconfigs/{name}/rejoin` (#316, `docs/specs/SPEC_D4_cluster_rejoin.md`) with `{"username": "…",
"password": "…"}` → `200 {"outcome": "rejoined", "message": "Signed in to east as alice, who may update
clusterrolebindings there; …", "at": "2026-09-27T14:05:40Z"}`. A cluster administrator's **own** username and password,
for ONE login to the remote: the dashboard logs in as that person, asks the remote with that login's own token whether
the person may `update clusterrolebindings` there (the host's `visibility.clusterAdminSar` question; a no reads and
writes nothing), reads `group-sync-operator/group-sync-dashboard-cluster-poller-token`, signs the login out, and writes
the token to `gsd-cluster-<name>` with `token-source: rejoin`, `rejoined-by`, `rejoin-account` and `rejoined-at` — never
`lookup-account`. **The password is never stored, logged or echoed.** It is sent at most once per request and never
retried, and a password the directory refused for this exact username is not sent again by this process while it is the
same password (the poller's credential gate, #315). `outcome` is `rejoined` or a refusal's code: `login-refused`,
`login-failed`, `not-cluster-admin`, `access-review-failed`, `sa-token-secret-missing`, `sa-token-unreadable`,
`sa-token-invalidated`, `lookup-write-failed`, or `rejoin-failed` for an error the design did not expect (fixed words,
because that error's own text may quote the password, then how the login ended when there was one). Refused before
anything is sent: `403` below the cluster-admin tier or without an identity; `404` for an unknown or retired name, and
with writes off (the route does not exist); `409 not-rejoinable` where `rejoinable` is false; `409` while another Rejoin
is in flight in this process, or when the process runs no poller; `422` for a body that is not exactly `{username,
password}` as strings (fixed words: no key or value is repeated, because a key can be the password),
`rejoin-username-invalid` (outside the bootstrap grammar), `rejoin-fleet-account` (a name a fleet path logs in as,
compared stripped and casefolded), `rejoin-password-missing`, `rejoin-password-invalid` (a control character, which
RFC 7617 forbids, or an unpaired surrogate, which UTF-8 cannot carry) and `rejoin-password-within-username` (the
password, stripped and casefolded, is the username or lies inside it; #447). A success wakes discovery. One
`cluster-rejoin-review` line carries the remote's answer, then `cluster-rejoined` or `cluster-rejoin-failed`; each names
the person and the account and carries no credential.
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
| Status | D1, D2 (`remote-sar` + `same-as-host`, the standard for every way a cluster is joined) and D5 built in SPEC_D2b (#338), the remote failure hold with them; D3 needs no code; D6's lab policy applied there; D4's fail-closed fallback built, its named finding recommended, not built; D7 directed, not built (#322); D8 open (§8) |
```

```markdown
| Status | D1, D2 (`remote-sar` + `same-as-host`, the standard for every way a cluster is joined) and D5 built in SPEC_D2b (#338), the remote failure hold with them; D3 needs no code; D6's lab policy applied there; D4's fail-closed fallback built, its named finding recommended, not built; D7 built (#322); D8 directed 2026-09-26 and built with Rejoin (#316, `docs/specs/SPEC_D4_cluster_rejoin.md`) |
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
is joined. It also defines who may join or rejoin a cluster (§7): D7 (directed, not built) makes a person's join or
Rejoin a cluster-admin action checked on the host. Today the tab's writes ask only `create secrets` in the dashboard's
namespace, and the automatic lookup is started by configuration, not by a person.
```

```markdown
is joined. It also defines who may join or rejoin a cluster (§7): D7 (built with #322) makes a person's join or Rejoin a
cluster-admin action checked on the host, and D8 (built with #316) has the remote confirm it with the person's own
login. The automatic lookup is started by configuration, not by a person.
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
exchange started by a person with their own credentials. It is not built: the tab accepts only a pasted bearer token
and refuses a username and password with `oauth-exchange-not-built`
(`local-development/gsd/clusterconfig/writer.py#validate`).
```

```markdown
exchange started by a person with their own credentials (`local-development/gsd/rejoin.py#rejoin`,
`docs/specs/SPEC_D4_cluster_rejoin.md`). The Add form still takes only a pasted bearer token: a username and password
there is refused with `oauth-exchange-not-built` (`local-development/gsd/clusterconfig/writer.py#validate`).
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
not cluster admin (§5). A person's Rejoin would be gated twice: on the host before the password exists (D7), and on
the remote once it does (D8). Dashed boxes are proposed and not built.*
```

```markdown
not cluster admin (§5). A person's Rejoin is gated twice: on the host before the password exists (D7), and on
the remote once it does (D8).*
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
 HOST    Rejoin (#316, not built), a person on the tab
```

```markdown
 HOST    Rejoin (#316), a person on the tab
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
 REMOTE  2 (D8, proposed, Rejoin only) SelfSubjectAccessReview: update clusterrolebindings?
             no -> refuse and revoke; the fleet account skips this step
```

```markdown
 REMOTE  2 (D8, Rejoin only) SelfSubjectAccessReview: update clusterrolebindings?
             the answer is logged; no -> nothing is read or written, and the login is revoked;
             the fleet account skips this step
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
| Rejoin (#316) | not built | `clusterAdminSar`, then D8 on the remote | the host, then the remote | the person's own username and password, once, never stored |
```

```markdown
| Rejoin (#316) | `clusterAdminSar` on the host, then D8 on the remote | unchanged | the host, then the remote | the person's own username and password, once, never stored |
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
| **D8** | Confirm a Rejoin credential on the remote | none; or one `SelfSubjectAccessReview` with the login's own token (`update clusterrolebindings`, #322's cluster-admin question), refusing and revoking on no | **Open**, recommended for Rejoin only. It enforces D7's rule with the remote's own RBAC once a credential exists and needs no new grant (`system:basic-user`). The login's token is `user:full` (`docs/DESIGN_session_and_signout.md`), so the review answers with the person's own RBAC and groups, with no group lookup. It refuses a namespace admin of `group-sync-operator`, whom the `admin` role lets read the token Secret (§5). Like #322's, the question is a threshold: `cluster-admin` passes it, and so would any other role that grants the verb. The fleet account skips it. |
```

```markdown
| **D8** | Confirm a Rejoin credential on the remote | none; or one `SelfSubjectAccessReview` with the login's own token (`update clusterrolebindings`, #322's cluster-admin question), refusing and revoking on no | **Directed** (the operator, 2026-09-26: *"we log the response from the remote cluster but don't make things very complicated. We can check if the person joining the cluster is also a cluster admin on the remote cluster."*), in its simple form, and built with Rejoin (#316, `docs/specs/SPEC_D4_cluster_rejoin.md`): one review, the remote's answer logged, a no reads and writes nothing. It enforces D7's rule with the remote's own RBAC once a credential exists and needs no new grant (`system:basic-user`). The login's token is `user:full` (`docs/DESIGN_session_and_signout.md`), so the review answers with the person's own RBAC and groups, with no group lookup. It refuses a namespace admin of `group-sync-operator`, whom the `admin` role lets read the token Secret (§5). Like #322's, the question is a threshold: `cluster-admin` passes it, and so would any other role that grants the verb. The fleet account skips it. |
```

<!-- block: docs/DESIGN_remote_cluster_access.md | edit -->
```markdown
`self-only` and `hidden` clusters nothing changes. #322's Rejoin row is D7: the host will decide who may start one,
and D8, if accepted, lets the remote refuse a credential that does not pass the same question there.
```

```markdown
`self-only` and `hidden` clusters nothing changes. #322's Rejoin row is D7: the host decides who may start one,
and D8 lets the remote refuse a credential that does not pass the same question there (#316).
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
      fleet account does it, automatically. Rejoin (#316) is the same exchange started by a person.</p>
    <figure>
      <div class="fig-scroll">
        <svg viewBox="0 0 980 870" role="img" aria-label="How a cluster is joined. On the host, saTokenLookup starts automatically: it stops first if cluster-Secret writes are off, then the leader or sole replica reads the fleet account's password from one host Secret, and a password the account was already refused, by any target, is not sent again. Rejoin, proposed, starts with a person who must pass clusterAdminSar on the host, update clusterrolebindings, and types their own username and password. On the remote, the dashboard logs in as that account, a proposed SelfSubjectAccessReview asks #322's cluster-admin question of a Rejoin credential there, it reads the poller's token Secret by name in group-sync-operator, and tries once to revoke the login's own token. Back on the host it writes gsd-cluster-shared-rnd. Once joined, the poller's token authenticates every later call; its rights on the remote are the ClusterRole group-sync-dashboard-cluster-poller, and under remote-sar the same token asks the remote about each reader.">
```

```html
      fleet account does it automatically, and Rejoin (#316) is the same exchange started by a person.</p>
    <figure>
      <div class="fig-scroll">
        <svg viewBox="0 0 980 870" role="img" aria-label="How a cluster is joined. On the host, saTokenLookup starts automatically: it stops first if cluster-Secret writes are off, then the leader or sole replica reads the fleet account's password from one host Secret, and a password the account was already refused, by any target, is not sent again. Rejoin starts with a person who must pass clusterAdminSar on the host, update clusterrolebindings, and types their own username and password. On the remote, the dashboard logs in as that account, a SelfSubjectAccessReview asks #322's cluster-admin question of a Rejoin credential there and logs the answer, it reads the poller's token Secret by name in group-sync-operator, and tries once to revoke the login's own token. Back on the host it writes gsd-cluster-shared-rnd. Once joined, the poller's token authenticates every later call; its rights on the remote are the ClusterRole group-sync-dashboard-cluster-poller, and under remote-sar the same token asks the remote about each reader.">
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
              <rect x="260" y="64" width="200" height="62" rx="6" stroke="currentColor" stroke-dasharray="5 4"/>
              <rect x="30" y="152" width="200" height="62" rx="6" stroke="currentColor"/>
              <rect x="30" y="240" width="200" height="62" rx="6" stroke="currentColor"/>
              <rect x="260" y="240" width="200" height="62" rx="6" stroke="currentColor" stroke-dasharray="5 4"/>
            </g>
            <rect x="260" y="152" width="200" height="62" rx="8" fill="var(--host-wash)" stroke="var(--host)" stroke-width="1.5" stroke-dasharray="5 4"/>
            <text x="130" y="86" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-weight="600">saTokenLookup: true</text>
            <text x="130" y="103" text-anchor="middle">a stanza or Secret · automatic</text>
            <text x="130" y="119" text-anchor="middle" fill="var(--muted)">stops first if writes are off</text>
            <text x="360" y="86" text-anchor="middle" font-weight="600">Rejoin (#316, not built)</text>
```

```html
              <rect x="260" y="64" width="200" height="62" rx="6" stroke="currentColor"/>
              <rect x="30" y="152" width="200" height="62" rx="6" stroke="currentColor"/>
              <rect x="30" y="240" width="200" height="62" rx="6" stroke="currentColor"/>
              <rect x="260" y="240" width="200" height="62" rx="6" stroke="currentColor"/>
            </g>
            <rect x="260" y="152" width="200" height="62" rx="8" fill="var(--host-wash)" stroke="var(--host)" stroke-width="1.5"/>
            <text x="130" y="86" text-anchor="middle" font-family="IBM Plex Mono, monospace" font-weight="600">saTokenLookup: true</text>
            <text x="130" y="103" text-anchor="middle">a stanza or Secret · automatic</text>
            <text x="130" y="119" text-anchor="middle" fill="var(--muted)">stops first if writes are off</text>
            <text x="360" y="86" text-anchor="middle" font-weight="600">Rejoin (#316)</text>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
            <rect x="530" y="388" width="420" height="62" rx="6" fill="none" stroke="var(--remote)" stroke-width="1.2" stroke-dasharray="5 4"/>
            <text x="546" y="410" font-weight="600" fill="var(--remote)">② proposed (D8) · Rejoin only</text>
```

```html
            <rect x="530" y="388" width="420" height="62" rx="6" fill="none" stroke="var(--remote)" stroke-width="1.2"/>
            <text x="546" y="410" font-weight="600" fill="var(--remote)">② D8 · Rejoin only · the answer is logged</text>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
            <text x="30" y="852" fill="var(--host)" font-weight="600">Dashed = proposed, not built: Rejoin (#316), clusterAdminSar (#322, D7), the remote's confirmation (D8).</text>
```

```html
            <text x="30" y="852" fill="var(--host)" font-weight="600">Built: Rejoin (#316), its host gate clusterAdminSar (#322, D7) and the remote's check (D8).</text>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
        fleet account is configuration, not a person, and holds no cluster-admin grant (measured on the lab). A person's Rejoin would be gated twice: by the
```

```html
        fleet account is configuration, not a person, and holds no cluster-admin grant (measured on the lab). A person's Rejoin is gated twice: by the
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
          <tr><td>Rejoin (#316)</td><td>not built</td><td><code>clusterAdminSar</code>, then D8 on the remote</td><td>host, then remote</td><td>the person's own username and password, once, never stored</td></tr>
```

```html
          <tr><td>Rejoin (#316)</td><td><code>clusterAdminSar</code>, then D8 on the remote</td><td>unchanged</td><td>host, then remote</td><td>the person's own username and password, once, never stored</td></tr>
```

<!-- block: docs/diagrams/remote-cluster-access/source.html | edit -->
```html
        <div class="rec"><strong>Recommend: yes, for Rejoin only.</strong> It enforces D7's rule on the remote with
          the remote's own RBAC, after the join credential exists.</div>
```

```html
        <div class="rec"><strong>Directed, and built with Rejoin (#316)</strong> (the operator, 2026-09-26): <em>"we log the
          response from the remote cluster but don't make things very complicated."</em> One review, its answer logged;
          a no reads and writes nothing.</div>
```

<!-- block: docs/specs/SPEC_D3_cluster_refresh.md | edit -->
```markdown
  discovery to close that gap: it forces nothing (§3). A rotation made in the tab wakes discovery itself.
```

```markdown
  discovery to close that gap: it forces nothing (§3). A rotation made in the tab wakes discovery itself.
- **#316 builds the next step §4 names (`docs/specs/SPEC_D4_cluster_rejoin.md`).** On `auth_failed` the line now
  says to use Rejoin, and the card draws its **Rejoin…** control where the row is `rejoinable`; §4's "Rejoin (#316),
  not built yet" and "No Rejoin control is drawn until Rejoin exists" describe the page before #316. The route, the
  probe, the words and the four states are unchanged.
```

<!-- block: docs/CHANGELOG.md | edit -->
```markdown
## Unreleased
```

```markdown
## Unreleased

- **Rejoin: an administrator signs in to a remote cluster as themselves, once, and the dashboard fetches a fresh
  poller token (#316, Epic D #384, `docs/specs/SPEC_D4_cluster_rejoin.md`).** When Refresh answers `auth_failed`, or
  `pending` for a token that was never fetched, a Secret-sourced card or a `saTokenLookup` stanza offers **Rejoin…**.
  Its dialog takes the administrator's own username and password for that cluster. The new
  `POST /api/clusterconfigs/{name}/rejoin` logs in once as that person and asks the remote, with that login's own
  token, whether the person may `update clusterrolebindings` there (D8: the answer is logged, and a no reads and writes
  nothing). It reads the poller's token Secret, signs the login out, and writes `gsd-cluster-<name>` with
  `token-source: rejoin`, `rejoined-by`, `rejoin-account` and `rejoined-at`. **The password is used for that one login
  and is never stored, logged or echoed.** One press presents it at most once, nothing is retried, and a password the
  directory refused for that username is not sent again by that pod while it is the same password (the poller's
  credential gate, #315). The fleet account's name is refused. The route sits in the writes carve-out, so a default
  install has no Rejoin. `GET /api/clusterconfigs` rows gain `rejoinable`, and discovery counts a Rejoin over a
  `saTokenLookup` stanza as that stanza's own Secret. `charts/group-sync-dashboard/RUNBOOK.md` walks the repair:
  Refresh, then Rejoin, then the manual fallback. No RBAC change.
```

