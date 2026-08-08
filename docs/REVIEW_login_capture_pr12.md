# Adversarial review — PR #12, login capture and the cluster-access gate

**Status: OPEN. Codex first, then Fable. The arbiter applies nothing until both passes are in.**

One document, two reviewers, inline markers. Nothing in this file may be written from memory: every claim
needs a file path, a symbol or line range, and either a command that was run or the exact code being
quoted. A finding without those three is not a finding.

---

## The artefact

Branch `feat/login-capture` → `main`, 26 commits, 20 files, 8,729 insertions.
PR: https://github.com/ephico2real2/group-sync-dashboard/pull/12

Deployed and verified on CRC as `0.6.0-7dfc9b649e` (release rev 96) while it was being built.

| area | files |
|---|---|
| 1 parser | `local-development/gsd/loginlog.py`, `tests/test_loginlog.py` |
| 2 storage | `local-development/gsd/store.py`, `gsd/storage.py`, `tests/test_login_capture.py` |
| 3 capture loop | `local-development/gsd/logincapture.py`, `gsd/poller.py`, `tests/test_logincapture_loop.py` |
| 4 API | `local-development/gsd/api.py`, `local-development/API.md` |
| 5 UI | `local-development/gsd/static/index.html`, `tests/test_ui.py` |
| 6 chart | `charts/group-sync-dashboard/{values.yaml,templates/configmap.yaml,templates/rbac.yaml}`, `docs/examples/clusteraccess-groupsync.yaml` |
| 7 reader | `local-development/gsd/kube.py` |

Run the suite with `cd local-development && .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py`.
Baseline: **1024 passed, 1 skipped**.

---

## Marker convention

Write findings inline in this file, under the area they belong to, each one as a block quote prefixed
with your name, and one verdict per claim you were asked about:

```
> **Codex:** CONFIRMED — <what you verified, and how>
> **Codex:** REFUTED — <the premise that is wrong, and the evidence>
> **Codex:** FIX-INADEQUATE — <the defect is real, the proposed remedy does not fix it, and why>
> **Codex:** NEW — <something nobody asked about>
```

`FIX-INADEQUATE` is the most valuable verdict in this document. Use it whenever a remedy proposed here
would not actually close the defect it claims to.

Every finding must carry:

- **file:line or file#symbol** — not "the store".
- **a concrete trigger** — the input, state or sequence that produces it. "Could race" is not a trigger;
  "two replicas, A reads at T, B commits at T+2ms" is.
- **the consequence** — what a reader of the dashboard would believe that is false, or what breaks.
- **THE FULL CODE, IN THIS FILE.** See below. This is the requirement most often skipped and the one
  that makes the difference between a review and a to-do list.
- **a test that fails before and passes after**, as a complete test function, not a sentence describing
  one.

Severity: `high` = wrong data shown as fact, data loss, or a security consequence. `medium` = a real
defect with a bounded blast radius. `low` = correctness of documentation or comments.

### Full code snippets, in this document

Write the **complete replacement** — the whole function, the whole template block, the whole SQL
statement — inside a fenced code block in this file, ready to apply. Not a diff fragment, not
"add a check here", not "the method should also do X".

```
> **Codex:** CONFIRMED — high — gsd/store.py#login_events
>
> <the defect, its trigger, its consequence>
>
> ```python
> def login_events(self, cluster_id: str, ...) -> list[dict]:
>     """<the whole function, complete and runnable>"""
>     ...
> ```
>
> and the test:
>
> ```python
> def test_<name>(store):
>     """<why this test exists — what a reader would otherwise believe>"""
>     ...
> ```
```

Why this is mandatory: the arbiter applies what survives both passes, and a finding described in prose
has to be re-derived before it can be applied — which is where the meaning drifts. A finding written as
code either applies or is visibly wrong. If a fix touches three functions, write all three.

Preserve the surrounding style: comments in this codebase say WHY, not WHAT, and a replacement that
strips the reasoning out of a function is a regression even when its logic is right.

### Technical debt — assess it explicitly

Every finding, and the PR as a whole, gets a debt judgement. Three buckets, and say which:

- **DEBT-INTRODUCED** — this PR adds a maintenance cost that will be paid later. Name the cost, name who
  pays it, and say what it should be instead. Duplicated logic, a second source of truth for one fact, a
  predicate copied rather than shared, a constant restated, an invariant enforced by comment rather than
  by test, a shape that only works because of something elsewhere that nothing checks.
- **DEBT-ACCEPTED** — a shortcut that is *correct to take*, with the reason. Say what would make it worth
  paying down and roughly when. A deliberate limitation with a comment explaining it is not debt.
- **DEBT-AVOIDED** — where the PR paid a cost up front that it did not have to. Worth recording: it stops
  a later reviewer "simplifying" it back.

Be concrete about this area in particular, because it is where debt hides in this PR:

- the **outcome vocabulary** exists in `loginlog.py`, is derived in `api.py`, and is restated in
  `index.html`'s `OUTCOME_LABEL`/`OUTCOME_BADGE`. Two of those three are derived; one is hand-written.
  Is that debt, and if so what closes it without shipping the parser's constants to the browser?
- the **`_not_local_provider` predicate** is now shared between two SQL sites after being duplicated.
  Are there other predicates in `store.py` still duplicated the same way?
- the **login-gate DN** is resolved in `poller.py`, stored in `store.py`, read in `api.py` and matched in
  `kube.dn_equal`. Four files for one fact. Justified, or debt?
- **`docs/examples/clusteraccess-groupsync.yaml`** duplicates configuration that the platform chart also
  renders. Nothing tests that the two agree.
- the three test files carry **fixture-building helpers that overlap** (`_lines`, `_record`, `_iso`,
  `event_dict` wrappers). Is that acceptable test-local duplication or a shared fixture waiting to exist?

---

## Claims to test

Each is written as a claim so it can be refuted. **Prefer refutation.** Say "cannot refute" only after
actually checking, and say what you checked.

### Area 1 — the parser

- **P1** `_VERDICT` in `loginlog.py` matches both grammars and nothing else. Specifically: a line
  containing `Login with provider "x" succeeded for login "y"` inside a *quoted klog message that is not
  a verdict* cannot produce a false attempt.
- **P2** `parse()` correlates by username within `ATTEMPT_WINDOW` (1s). Claim: two DIFFERENT people
  logging in within the same second cannot have one's cause attached to the other's attempt. Read the
  `orphan` handling and the `newest` selection in the cause branch — that is where this would break.
- **P3** The orphan cause is adopted only within the window. Claim: a cause line from a *previous*
  attempt cannot attach to a later verdict.
- **P4** `_classify_bind` never returns `bad_password` for an AD sub-code it does not know.
- **P5** No raw log line, bind filter or user DN is ever carried into `detail`. This is the security one.
- **P6** A line with no kubelet timestamp is skipped, never given an invented time.

### Area 2 — storage

- **S1** `record_login_events` cannot insert a duplicate for the same (cluster, pod, user, at, outcome),
  and `pod_name` in the key cannot cause a *missed* attempt in any other scenario.
- **S2** `set_login_watermark` cannot move a watermark backwards, under any interleaving.
- **S3** `_not_local_provider` is applied identically in `ungoverned_login_users`' WHERE and in its
  `last_outcome` subquery, and the parameter binding order matches the SQL text order. Claim: no row can
  report an outcome from an attempt its own count excludes. **This was a real defect; check the fix.**
- **S4** `access_without_login` excludes the gate group from "holds access". Claim: with the gate group
  counted as access, the finding would be empty on every cluster — verify the exclusion is present in
  both the row query and the count.
- **S5** `prune_login_events` is bounded per call and cannot delete a row newer than `before_at`.
- **S6** `is_in_access_group` returns `{}` — meaning *unknown* — when no gate is known, and the API
  turns that into `None` rather than `False`.
- **S7** Migration 6 is replay-safe against a database that already has the table from `SCHEMA`.

### Area 3 — the capture loop

- **L1** `capture_once` never raises for a cluster-side problem. Trace every call it makes.
- **L2** The leadership recheck is immediately before the write, and nothing is written after a lost
  lease — including the watermark, the read stamp and the prune.
- **L3** `_settle_horizon` is measured from now, so a burst of logins inside `SETTLE_SECONDS` cannot stall
  the watermark. **This was a real defect; check the fix.**
- **L4** A cycle in which no pod answered does not stamp `login_capture_status`.
- **L5** `prune_login_watermarks` is called with a pod list that is authoritative, and cannot delete a
  live pod's position. Claim: passing `[]` removes nothing.
- **L6** `poll_once`'s gate-group resolution cannot fail the poll. A `ClusterError` from
  `fetch_access_group_dn` must leave groups written and the outcome `ok`.
- **L7** The resolution writes inside `poll_snapshot()`, so the DN and the Group it names are one
  observation. Verify `_write()` joins rather than nesting.

### Area 4 — the API

- **A1** `list_logins` and `cluster_access` are `@consistent`, and every store call they make is inside
  that snapshot.
- **A2** `summary` describes the whole record and never the page, under every filter combination.
- **A3** `_refusal_reason` returns `None` for any outcome other than `rejected`, and `None` when no gate
  is known. Claim: it can never assert a reason it has no basis for.
- **A4** `/metrics` gained no username label. This is a hard invariant — `/metrics` is unauthenticated.
- **A5** No endpoint added here reads from a cluster. `test_read_snapshot_scope.py` guards `read_snapshot`;
  confirm the two new handlers are covered by the same reasoning.
- **A6** `read_interval_seconds` is the poll interval, and the UI's staleness threshold derives from it
  rather than from a hardcoded number.

### Area 5 — the UI

- **U1** Every value interpolated into `innerHTML` on the two new pages goes through `esc()`. This is the
  security one, and there was an XSS in this file before — check `title` attributes and `data-` attributes
  as well as text.
- **U2** An empty attempts list can never read as "nobody signed in": the window banner is
  unconditional, in all three branches of `captureSection`.
- **U3** `synced: false` renders as *no data*, never as a zero finding.
- **U4** The gate chip is suppressed on local-provider rows and only there.
- **U5** Every drill-down goes through `navigate()` and lands on a page that can render it.
- **U6** No literal `font-size` in the `<style>` block, and `--tab-logins` clears 4.5:1 in both themes.

### Area 6 — the chart

- **C1** `configmap.yaml` writes every key `config.py` reads, in both the enabled and disabled states.
  **The absence of exactly this was a real defect; check for others.**
- **C2** The `oauths` grant is `get` only, name-scoped to `cluster`, and declining it degrades to "set the
  DN explicitly" rather than an error.
- **C3** No template in this chart creates a GroupSync CR.
- **C4** `clusterAccess.group | quote` cannot break the rendered YAML for a DN containing commas, colons
  or spaces.

### Area 7 — the reader

- **K1** `fetch_pod_log` streams and is byte-bounded, so a large log cannot be buffered whole.
- **K2** `_access_group_from_ldap_url` cannot return a non-DN, and handles percent-encoding, both
  spellings, and a filter with no membership clause.
- **K3** `fetch_access_group_dn` returns `None` for FORBIDDEN and for a 404, and re-raises everything else.
  The 404 check must be anchored on the path, not on the string "404" appearing in a response body.

---

## Out of scope — do not spend effort here

- **Do not redesign the feature.** The design decisions in `docs/DESIGN_login_capture.md` were argued and
  measured; a finding that reopens one needs new evidence, not a preference.
- **Do not propose that the dashboard read LDAP directly.** Rejected deliberately: it would put a bind
  credential and a CA in a component that today holds only its own ServiceAccount token.
- **Do not propose that this chart manage GroupSync CRs.** They belong to the platform team; that chart
  is a separate repository and already ships the support (0.12.0).
- **Do not propose reconstructing logins from before capture was enabled.** The oauth-server's log dies
  with its pod. This is accepted, surfaced in the UI, and not solvable.
- **Do not suggest removing or disabling `kubeadmin`.** It is the lab's login.
- **Do not restyle the UI**, propose a component framework, or add a build step. One self-contained
  `index.html`, vanilla JS, strict CSP, no external assets.
- **Do not touch `authLogLevel`**, the oauth-proxy, or the SQLite engine choice.
- **`docs/DESIGN_login_capture.md` is a point-in-time record.** Do not review it for drift.

---

## Codex — pass 1

### Method and command ledger

> **Codex:** The mandatory command was run exactly as specified. It could not reproduce the published
> baseline inside this sandbox: the result was `914 passed, 1 skipped, 4 deselected, 111 errors in
> 85.87s`. Every error was test setup, either Chromium failing `bootstrap_check_in ... Permission
> denied (1100)` or `socket.bind(("127.0.0.1", 0))` failing `EPERM`; no test assertion failed. The
> focused non-browser command covering parser, storage, loop, snapshots, metrics, type scale,
> accessibility and migrations then returned `208 passed in 3.29s`. The individual S3 and L3 tests
> each returned `1 passed`. The individual UI test reproduced the same Chromium bootstrap error, so I
> do not count it as a pass.
>
> The scratch commands quoted below were run against temporary SQLite files or mocked HTTP streams:
>
> ```text
> P1 unrelated-message result: [('alice', 'success', 'ldap-local')]
> P2 interleaved result: alice=failed, bob=bad_password
> P3 cause(uid=alice) then verdict(bob), 0.9s later: bob=bad_password
> S1 same pod duplicate / other pod: [1, 0, 1], rows=2
> S2 concurrent later/earlier writes: 2026-08-07T02:00:00Z
> S3 filtered row: attempts=1, last_outcome=rejected
> S4 row/count: ['bob'], 1
> S5 max_rows=-1 deleted: 10
> S6 no gate: {}
> S7 existing-table replay: version=6, table=1
> NEW fresh migration version: 5 (latest migration is 6)
> L6 discovery error: outcome=ok, groups=['gate'], poll=ok
> L7 gate write transaction depth: 1
> NEW quiet pod: sinceSeconds=2592060, watermark unchanged
> A2 filtered endpoint: attempts=1, total=3, by_outcome has all 3 rows
> A4 usernames in /metrics: {'alice': False, 'bob': False}
> A6 configured poll interval 137: read_interval_seconds=137
> U6 --tab-logins contrast: light 4.67:1; dark 5.04:1; literal style font sizes=[]
> C1 enabled/disabled render: loginCaptureEnabled: true / false
> C2 enabled render: oauths, resourceNames ['cluster'], verbs ['get']; disabled render: no rule
> C3 rendered kind GroupSync matches: none
> C4 parsed inner YAML: str 'cn=Gate, ou=People:Tier 1, dc=example'
> K1 cap result: ['oldest-1', 'oldest-2']
> K2 invalid membership value: '=oops'
> K3 forbidden=None; path-anchored 404=None; 500 body mentioning 404=RAISED
> ```

### Area 1 — parser verdicts

> **Codex:** REFUTED — high — **P1** — `local-development/gsd/loginlog.py:133-136#_VERDICT`.
>
> Trigger: a timestamped, non-verdict klog message begins `request rejected; submitted text:` and then
> contains the exact verdict phrase. `_VERDICT.search()` returned a successful attempt for `alice`.
> A normally escaped quoted field did not match, but the claim says “and nothing else”; the message
> boundary is not enforced. The dashboard reader would believe Alice signed in when the oauth-server
> only logged text containing that sentence. **DEBT-INTRODUCED:** the grammar comment promises a
> boundary the regex does not encode; parser maintainers pay for that hidden invariant. Anchor the
> phrase at the start of the klog message while retaining the release-independent call-site policy.
>
> Complete replacement:
>
> ```python
> _VERDICT = re.compile(
>     r'\]\s+Login with provider "(?P<provider>[^"]*)" '
>     r'(?P<verdict>succeeded|failed) for (?:login )?"(?P<user>[^"]*)"'
> )
> ```
>
> Complete regression test:
>
> ```python
> def test_a_verdict_phrase_inside_an_unrelated_message_is_not_an_attempt():
>     """Quoted or relayed message text is not an oauth-server verdict."""
>     line = (
>         '2026-08-07T00:00:00.000000Z I0807 00:00:00.000000 1 audit.go:1] '
>         'request rejected; submitted text: Login with provider "ldap-local" '
>         'succeeded for login "alice"'
>     )
>     assert parse([line]) == []
> ```

> **Codex:** REFUTED — high — **P2** — `local-development/gsd/loginlog.py:348-364#parse`.
>
> Trigger: Alice's provider-chain failure is pending at T, Bob's is pending at T+100ms, Alice's bind
> cause arrives at T+200ms, then their deciding verdicts arrive. `newest` attaches Alice's code 49 to
> Bob. The dashboard tells the reader Bob used a wrong password and Alice's provider gave no reason;
> both statements are false. **DEBT-INTRODUCED:** “closest line” is an undocumented attribution
> heuristic presented as a fact. A cause should attach only when the cause text itself identifies the
> pending username; a false negative becomes honest `failed`, never another person's diagnosis.
>
> **Codex:** REFUTED — high — **P3** — `local-development/gsd/loginlog.py:327-335#parse`.
>
> Trigger: a bind cause whose DN contains `uid=alice` at T followed by Bob's first verdict at T+900ms.
> The time check passes and Bob gets Alice's code 49. The window bounds age, not identity. The same
> replacement closes P2 and P3. **DEBT-AVOIDED by the replacement:** raw DN/filter text is used only as
> an ephemeral correlation hint and is still never persisted in `detail`.
>
> Complete replacement (`_cause_mentions_user` plus the whole `parse` function):
>
> ```python
> def _cause_mentions_user(raw: str, user: str) -> bool:
>     """Whether an LDAP assertion or DN in this cause names this exact login.
>
>     Cause lines have no request id. Guessing by recency assigns one person's directory diagnosis to
>     another under interleaving, which is worse than retaining the provider's honest no-reason result.
>     The raw line is used only here and is never copied into the stored detail.
>     """
>     value = re.escape(user)
>     return re.search(
>         rf'(?i)(?:["(,])\s*[a-z0-9.-]+\s*=\s*{value}\s*(?:[,)"]|$)', raw
>     ) is not None
>
>
> def parse(lines: list[str] | str) -> list[LoginAttempt]:
>     """Every login attempt in these lines, oldest first.
>
>     Correlates verdicts by username within ATTEMPT_WINDOW. LDAP causes carry no explicit request id,
>     so they are attached only when their own DN/filter identifies the same username; losing a cause
>     that used a different login attribute is honest, while assigning it to somebody else is not.
>     Lines with no kubelet timestamp are skipped rather than guessed at.
>     """
>     if isinstance(lines, str):
>         lines = lines.splitlines()
>
>     pending: dict[str, _Pending] = {}
>     out: list[LoginAttempt] = []
>     # Single-provider LDAP logs the cause before the verdict names a user. Retain it only long enough
>     # to compare its own DN/filter with that username; recency alone is not identity.
>     orphan: dict | None = None
>
>     def conclude(user: str) -> None:
>         p = pending.pop(user, None)
>         if p is None:
>             return
>         if p.succeeded:
>             outcome = OUTCOME_SUCCESS
>         elif p.bind_code is not None:
>             outcome = _classify_bind(p.bind_code, p.bind_diagnostic)
>         elif p.saw_no_entries:
>             outcome = OUTCOME_REJECTED
>         elif p.failures:
>             outcome = OUTCOME_FAILED
>         else:
>             return
>         out.append(LoginAttempt(
>             user_name=user,
>             outcome=outcome,
>             at=p.first_at,
>             provider=p.provider,
>             ldap_result_code=p.bind_code,
>             detail=_detail(p, outcome),
>         ))
>
>     for raw in lines:
>         ts = parse_timestamp(raw)
>         if ts is None:
>             continue
>         # A long read must not merge separate attempts by the same account minutes apart.
>         for user in [u for u, p in pending.items() if ts - p.first_at > ATTEMPT_WINDOW]:
>             conclude(user)
>
>         v = _VERDICT.search(raw)
>         if v:
>             user = v.group("user")
>             provider = v.group("provider")
>             p = pending.get(user)
>             if p is None:
>                 p = pending[user] = _Pending(first_at=ts, last_at=ts)
>                 # A directory whose DN does not repeat the login loses a diagnosis here, but the
>                 # conservative false negative is preferable to another person's diagnosis.
>                 if orphan is not None:
>                     age = ts - orphan["at"]
>                     if (timedelta(0) <= age <= ATTEMPT_WINDOW
>                             and _cause_mentions_user(orphan["raw"], user)):
>                         p.first_at = orphan["at"]
>                         p.saw_no_entries = orphan["no_entries"]
>                         p.bind_code = orphan["code"]
>                         p.bind_diagnostic = orphan["diagnostic"]
>                 orphan = None
>             p.last_at = ts
>             if v.group("verdict") == "succeeded":
>                 p.succeeded = True
>                 p.provider = provider
>                 # Success concludes the attempt; later provider noise cannot change it.
>                 conclude(user)
>             else:
>                 p.failures.append(provider)
>                 # The last provider to reject decides a failure, so later failures overwrite this.
>                 p.provider = provider
>             continue
>
>         no_entries = bool(_NO_ENTRIES.search(raw))
>         b = None if no_entries else _BIND_ERROR.search(raw)
>         if not no_entries and b is None:
>             continue
>
>         # Cause lines have no request id. Their own assertion is the only evidence strong enough to
>         # override a provider's otherwise honest “no reason” result under interleaving.
>         matches = [u for u in pending if _cause_mentions_user(raw, u)]
>         if len(matches) == 1:
>             matched = matches[0]
>             if no_entries:
>                 pending[matched].saw_no_entries = True
>             else:
>                 pending[matched].bind_code = int(b.group("code"))
>                 pending[matched].bind_diagnostic = b.group("diagnostic") or ""
>             pending[matched].last_at = ts
>         elif not pending:
>             orphan = {
>                 "at": ts,
>                 "raw": raw,
>                 "no_entries": no_entries,
>                 "code": None if b is None else int(b.group("code")),
>                 "diagnostic": "" if b is None else (b.group("diagnostic") or ""),
>             }
>
>     for user in list(pending):
>         conclude(user)
>     out.sort(key=lambda a: (a.at, a.user_name))
>     return out
> ```
>
> Complete regression tests:
>
> ```python
> def test_interleaved_people_do_not_swap_directory_causes():
>     def line(ms, message):
>         return f'2026-08-07T00:00:00.{ms:06d}Z I0807 00:00:00.0 1 x.go:1] {message}'
>     got = parse([
>         line(0, 'Login with provider "first" failed for login "alice"'),
>         line(100000, 'Login with provider "first" failed for login "bob"'),
>         line(200000, 'error binding password for "uid=alice,dc=example": '
>                      'LDAP Result Code 49 "Invalid Credentials": '),
>         line(300000, 'Login with provider "ldap" failed for login "alice"'),
>         line(400000, 'Login with provider "ldap" failed for login "bob"'),
>     ])
>     assert {a.user_name: a.outcome for a in got} == {
>         "alice": loginlog.OUTCOME_BAD_PASSWORD,
>         "bob": loginlog.OUTCOME_FAILED,
>     }
>
>
> def test_orphan_cause_must_name_the_verdict_user():
>     cause = ('2026-08-07T00:00:00.000000Z I0807 00:00:00.0 1 ldap.go:152] '
>              'error binding password for "uid=alice,dc=example": '
>              'LDAP Result Code 49 "Invalid Credentials": ')
>     bob = ('2026-08-07T00:00:00.900000Z I0807 00:00:00.9 1 login.go:183] '
>            'Login with provider "ldap" failed for "bob"')
>     got = parse([cause, bob])
>     assert got[0].user_name == "bob"
>     assert got[0].outcome == loginlog.OUTCOME_FAILED
>     assert got[0].ldap_result_code is None
> ```

> **Codex:** CONFIRMED — **P4** — `loginlog.py:219-234#_classify_bind`; the focused suite includes
> `test_an_unmapped_sub_code_is_failed_not_a_wrong_password` and passed. The `data 999` probe produced
> `failed` with the sub-code retained. **DEBT-AVOIDED:** the unknown case is explicit instead of falling
> through code 49's generic mapping.
>
> **Codex:** CONFIRMED — **P5** — `loginlog.py:381-399#_detail`; bind DN/filter/raw line are never
> interpolated, and the focused security test passed. Only integer result/sub-code and configured
> provider name reach detail. **DEBT-AVOIDED:** sensitive correlation input is discarded at the parser
> boundary.
>
> **Codex:** CONFIRMED — **P6** — `loginlog.py:253-260#parse_timestamp` and `310-313#parse`; the naked
> klog timestamp test passed and returned `[]`. **DEBT-AVOIDED:** absence is preferred to an invented
> year/zone.

### Area 2 — storage verdicts

> **Codex:** CONFIRMED — **S1** — `store.py:306-318` and `1526-1548#record_login_events`. Scratch
> SQLite produced `[1, 0, 1]` and two rows for same-pod reread then same instant on another pod. I also
> checked two byte-identical successes in one pod/timestamp: the parser can emit two but the store can
> retain only one. That is observational ambiguity in all key fields, not a miss caused by `pod_name`;
> no added key can distinguish those occurrences stably across overlapping reads. **DEBT-ACCEPTED:**
> exact byte-identical occurrences are collapsed; pay it down only if the upstream API exposes a stable
> log offset/request id.
>
> **Codex:** CONFIRMED — **S2** — `store.py:1550-1570#set_login_watermark`. Two Store instances were
> released concurrently with later/earlier values; SQLite serialization plus SQL `max()` retained the
> later value. **DEBT-AVOIDED:** monotonicity is enforced by the atomic upsert, not caller ordering.
>
> **Codex:** CONFIRMED — **S3** — `store.py:1892-1960#_not_local_provider` and
> `#ungoverned_login_users`. The individual regression passed; scratch output was `attempts=1,
> last_outcome=rejected`. SQL placeholder order is subquery providers, cluster, outer providers, limit,
> exactly matching the text. **DEBT-AVOIDED:** one provider predicate now supplies both SQL sites.
>
> **Codex:** CONFIRMED — **S4** — `store.py:1758-1815#access_without_login` and
> `#count_access_without_login`. With Alice in gate+RBAC and Bob in RBAC only, row and count were
> `['bob']`/`1`; both SQL statements contain `m.group_name <> gate`. **DEBT-INTRODUCED:** the complete
> access predicate remains copied between row and count queries. The existing agreement test limits
> risk, but a shared WHERE helper like `_ungoverned_where` should replace the duplication when either
> predicate next changes.
>
> **Codex:** REFUTED — medium — **S5** — `store.py:1604-1626#prune_login_events`.
>
> Trigger: call the public storage method with `max_rows=-1`. SQLite defines `LIMIT -1` as no limit;
> the scratch database deleted all 10 old rows, so the call is not bounded. A malformed setting or
> future caller can hold the single-writer lock across the entire retention backlog; dashboard readers
> then see requests stall and can believe the dashboard is down although polling data is intact. Rows
> newer than `before_at` were not deleted. **DEBT-INTRODUCED:** the storage seam documents a bound but
> leaves its only bound parameter unchecked.
>
> Complete replacement:
>
> ```python
> def prune_login_events(self, cluster_id: str, before_at: str, max_rows: int = 5000) -> int:
>     """Delete old events in a bounded chunk. Non-positive limits deliberately delete nothing.
>
>     SQLite treats LIMIT -1 as unlimited, so validating here is part of the single-writer latency
>     contract rather than something every caller may be trusted to remember.
>
>     The id-IN-subselect is core SQLite rather than DELETE LIMIT, which depends on an optional compile
>     flag absent from the deployment build. Its inner lookup remains served by login_event_lookup.
>     """
>     if max_rows <= 0:
>         return 0
>     with self._write() as conn:
>         before = conn.total_changes
>         conn.execute(
>             """DELETE FROM login_event WHERE id IN (
>                    SELECT id FROM login_event
>                     WHERE cluster_id=? AND at < ?
>                     ORDER BY at LIMIT ?)""",
>             (cluster_id, before_at, max_rows),
>         )
>         return conn.total_changes - before
> ```
>
> Complete regression test:
>
> ```python
> def test_a_negative_retention_limit_cannot_become_unbounded(store):
>     """SQLite LIMIT -1 means every row, the opposite of this method's contract."""
>     _record(store, [(f"old{i}", loginlog.OUTCOME_FAILED, 60 * 60 * 24 * 500 + i,
>                      "ldap-local") for i in range(10)])
>     before = _iso(datetime.now(UTC) - timedelta(days=400))
>     assert store.prune_login_events("crc-local", before, max_rows=-1) == 0
>     assert len(store.login_events("crc-local", limit=100)) == 10
> ```
>
> **Codex:** CONFIRMED — **S6** — `store.py:1871-1890#is_in_access_group` and
> `api.py:531-546#list_logins`. Scratch output with no gate was `{}`; the endpoint probe emitted
> `in_access_group: null` and `_refusal_reason` returned `None`. **DEBT-AVOIDED:** unknown is a distinct
> wire state, not a false boolean.
>
> **Codex:** CONFIRMED — **S7** — `store.py:431-447` migration 6 and `494-508#_migrate`. Replaying from
> `user_version=5` against a database whose SCHEMA already created the table returned version 6/table
> present. **DEBT-AVOIDED:** `IF NOT EXISTS` makes fresh and upgraded paths converge.

> **Codex:** NEW — low — `store.py:380-491#_MIGRATIONS`, `494-508#_migrate`.
>
> Trigger: open a fresh database at version 0. Migration 6 appears before migration 5; `_migrate`
> neither sorts nor updates its local `version`, so it applies 6, then 5, and leaves `user_version=5`.
> The next restart repairs it to 6, but the first process logs an impossible migration history and any
> future migration gated on version 6 can be replayed unexpectedly. **DEBT-INTRODUCED:** list ordering
> silently controls persistent schema state despite numeric target identifiers.
>
> Complete replacement:
>
> ```python
> def _migrate(conn: sqlite3.Connection) -> None:
>     """Apply every unapplied migration in numeric order, independent of source layout."""
>     version = int(conn.execute("PRAGMA user_version").fetchone()[0])
>     for target, title, statements in sorted(_MIGRATIONS, key=lambda migration: migration[0]):
>         if version >= target:
>             continue
>         for sql in statements:
>             try:
>                 conn.execute(sql)
>             except sqlite3.OperationalError as exc:
>                 # Fresh databases already carry additive columns from SCHEMA; only that exact replay
>                 # is harmless. Every other DDL error must still abort startup.
>                 if "duplicate column name" not in str(exc):
>                     raise
>         conn.execute(f"PRAGMA user_version = {target}")
>         version = target
>         log.info("schema migration %d applied: %s", target, title)
> ```
>
> Complete regression test:
>
> ```python
> def test_a_fresh_database_lands_on_the_latest_migration(tmp_path):
>     """Tuple placement must not make a fresh database report an older schema version."""
>     from gsd.store import _MIGRATIONS
>     store = Store(str(tmp_path / "fresh.db"))
>     try:
>         got = store._conn.execute("PRAGMA user_version").fetchone()[0]
>         assert got == max(target for target, _, _ in _MIGRATIONS)
>     finally:
>         store.close()
> ```

> **Codex:** NEW — high — `store.py:1817-1846#login_without_access` and
> `1848-1869#cluster_access_summary`.
>
> Trigger: a gate group with 10,001 members and no other memberships. Scratch SQLite proved the true
> count is 10,001 while the summary reports 10,000 because it computes `len(list(limit=10_000))`.
> The dashboard reader believes exactly 10,000 people may log in but hold no access, a false whole-set
> KPI. **DEBT-INTRODUCED:** a magic pagination cap is being used as a count and the predicate lacks a
> scalar counterpart.
>
> Complete replacement functions:
>
> ```python
> @staticmethod
> def _login_without_access_where() -> str:
>     """One predicate for both the page and its whole-set count."""
>     return """ WHERE m.cluster_id = ?
>                  AND m.group_name = ?
>                  AND NOT EXISTS(SELECT 1 FROM group_member g
>                                  WHERE g.cluster_id = m.cluster_id
>                                    AND g.user_name  = m.user_name
>                                    AND g.group_name <> ?)"""
>
> def login_without_access(self, cluster_id: str, limit: int = 200) -> list[dict]:
>     """People in the gate group who hold no access through another synced group."""
>     access = self.cluster_access_group(cluster_id)
>     if not access or not access["group_name"]:
>         return []
>     where = self._login_without_access_where()
>     return self._rows(
>         """SELECT m.user_name, m.first_seen_at, u.full_name,
>                   EXISTS(SELECT 1 FROM login_event e
>                           WHERE e.cluster_id=m.cluster_id AND e.user_name=m.user_name) AS has_tried
>              FROM group_member m
>              LEFT JOIN ocp_user u
>                     ON u.cluster_id=m.cluster_id AND u.user_name=m.user_name"""
>         + where + " ORDER BY m.user_name LIMIT ?",
>         (cluster_id, access["group_name"], access["group_name"], limit),
>     )
>
> def count_login_without_access(self, cluster_id: str) -> int:
>     """Whole-set count for a list that is deliberately paged."""
>     access = self.cluster_access_group(cluster_id)
>     if not access or not access["group_name"]:
>         return 0
>     rows = self._rows(
>         "SELECT COUNT(*) AS n FROM group_member m" + self._login_without_access_where(),
>         (cluster_id, access["group_name"], access["group_name"]),
>     )
>     return rows[0]["n"] if rows else 0
>
> def cluster_access_summary(self, cluster_id: str) -> dict:
>     """Whole-cluster counts, never counts inferred from a page."""
>     access = self.cluster_access_group(cluster_id)
>     if not access or not access["group_name"]:
>         return {"gated_members": 0, "with_access": 0, "access_without_login": 0,
>                 "login_without_access": 0}
>     gate = access["group_name"]
>     rows = self._rows(
>         """SELECT
>              (SELECT COUNT(*) FROM group_member
>                WHERE cluster_id=? AND group_name=?) AS gated_members,
>              (SELECT COUNT(DISTINCT user_name) FROM group_member
>                WHERE cluster_id=? AND group_name<>?) AS with_access""",
>         (cluster_id, gate, cluster_id, gate),
>     )
>     base = rows[0] if rows else {"gated_members": 0, "with_access": 0}
>     return {
>         "gated_members": base["gated_members"],
>         "with_access": base["with_access"],
>         "access_without_login": self.count_access_without_login(cluster_id),
>         "login_without_access": self.count_login_without_access(cluster_id),
>     }
> ```
>
> Also add the complete protocol member:
>
> ```python
> def count_login_without_access(self, cluster_id: str) -> int: ...
> ```
>
> Complete regression test:
>
> ```python
> def test_gate_only_summary_is_not_capped_at_ten_thousand(store):
>     """A whole-cluster KPI must not secretly be the length of a capped page."""
>     with store._write() as conn:
>         conn.executemany(
>             """INSERT INTO group_member(cluster_id,group_name,user_name,
>                                           first_seen_at,last_seen_at) VALUES(?,?,?,?,?)""",
>             [("crc-local", "gate", f"user{i}", "t", "t") for i in range(10_001)],
>         )
>     store.set_cluster_access_group("crc-local", "cn=gate,dc=x", "config", "gate", "t")
>     assert store.cluster_access_summary("crc-local")["login_without_access"] == 10_001
> ```

### Area 3 — capture-loop verdicts

> **Codex:** CONFIRMED — **L1** — `logincapture.py:100-217#capture_once`. The call trace is:
> constructor (no I/O), `fetch_oauth_pods` (caught `ClusterError`), `login_watermarks`, per-pod
> `fetch_pod_log` (caught `ClusterError`), pure `parse/_settle_horizon/event_dict`, then store writes.
> Store failures remain loud, correctly: they are not cluster-side failures. Focused list/read failure
> tests passed. **DEBT-AVOIDED:** capture failure is isolated from group polling.
>
> **Codex:** CONFIRMED — **L2** — `logincapture.py:179-216#capture_once` and `220-242#_prune`.
> The executable elector tests prove false at the per-pod recheck writes no event/watermark, and later
> guards cover watermark pruning, read stamp and retention. The lease is explicitly best-effort, not a
> fence; the few-instruction post-check window is **DEBT-ACCEPTED** because closing it needs a fencing
> token, while event uniqueness and monotonic watermark make the residual write idempotent.
>
> **Codex:** CONFIRMED — **L3** — `logincapture.py:75-97#_settle_horizon`. The individual 10-login burst
> test passed; cutoff is `datetime.now(UTC) - SETTLE_SECONDS`, not batch-relative. **DEBT-AVOIDED:** the
> regression test asserts watermark progress, not merely inserted rows.
>
> **Codex:** CONFIRMED — **L4** — `logincapture.py:147,167-170,206-214`. Only a non-`None` response sets
> `read_ok`; all-refused cycles return before `record_login_read`. The focused test passed.
>
> **Codex:** CONFIRMED — **L5** — `logincapture.py:131-143,192-204` and
> `store.py:1582-1602#prune_login_watermarks`. Pruning uses the successful pod-list response; list
> error/forbidden/empty returns earlier, and the store independently makes `[]` a no-op.
>
> **Codex:** CONFIRMED — **L6** — `poller.py:243-270#poll_once`. Forced discovery `ClusterError` produced
> `ok`, persisted the Group, and recorded poll `ok`. **DEBT-AVOIDED:** optional enrichment cannot poison
> the primary observation.
>
> **Codex:** CONFIRMED — **L7** — `poller.py:208-294#poll_once`, `store.py:649-698#_write/poll_snapshot`.
> Instrumentation observed transaction depth 1 at `set_cluster_access_group`, and `_write` joins at any
> positive depth. DN, resolved Group and poll outcome therefore commit together.

> **Codex:** NEW — high — `logincapture.py:145-177#capture_once` and
> `75-97#_settle_horizon`.
>
> Trigger: a pod has a 30-day-old watermark and returns only ordinary timestamped oauth log lines, no
> verdict. `parse()` returns no attempts and the loop continues without advancing. Scratch output was
> `sinceSeconds=2592060`, watermark unchanged. The read window grows for the life of a quiet pod; once
> it hits the byte cap, the current K1 behavior keeps old lines and can omit a new login while still
> stamping capture live. The reader believes “no login lines matched” although the new attempt was
> outside the retained prefix. **DEBT-INTRODUCED:** a read cursor is incorrectly derived from business
> events rather than from successfully read log time.
>
> Complete replacements (including the changed import):
>
> ```python
> from .loginlog import LoginAttempt, parse, parse_timestamp
>
>
> def _settle_horizon(attempts: list[LoginAttempt], lines: list[str]) -> str | None:
>     """Newest raw log instant old enough to settle, whether or not it was a login.
>
>     The watermark is a read cursor. Basing it only on parsed attempts makes a quiet pod's relative
>     read grow forever; raw timestamps advance the cursor without inventing a login record.
>     """
>     from datetime import UTC, datetime
>     cutoff = datetime.now(UTC).timestamp() - SETTLE_SECONDS
>     stamps = [stamp for raw in lines if (stamp := parse_timestamp(raw)) is not None
>               and stamp.timestamp() <= cutoff]
>     return max(stamps).strftime("%Y-%m-%dT%H:%M:%S.%fZ") if stamps else None
>
>
> def capture_once(store: StorageBackend, cluster: ClusterConfig, settings: Settings,
>                  elector=None, timeout: float = 15.0) -> int:
>     """One cluster pass; cluster failures degrade capture and never fail group polling."""
>     if not settings.login_capture_enabled:
>         return 0
>     ns = settings.login_capture_namespace
>     client = ClusterClient(cluster, timeout=timeout)
>     try:
>         pods = client.fetch_oauth_pods(ns)
>     except ClusterError as exc:
>         log.warning("%s: login capture could not list pods: %s — group data is unaffected",
>                     cluster.name, exc.message)
>         return 0
>     if pods is None:
>         log.info("%s: login capture is not permitted to list pods in %s; nothing recorded",
>                  cluster.name, ns)
>         return 0
>     if not pods:
>         log.info("%s: no Running oauth-server pods in %s", cluster.name, ns)
>         return 0
>
>     watermarks = store.login_watermarks(cluster.name)
>     recorded = 0
>     read_ok = False
>     for pod in pods:
>         settled_through = watermarks.get(pod)
>         if settled_through is None:
>             # First sight is bounded because a long-lived Debug pod can have an enormous history.
>             since = FIRST_SIGHT_SECONDS
>         else:
>             # Relative sinceSeconds is coarse. The overlap makes a multi-line attempt whole in one
>             # parse, and the uniqueness key makes the repeated settled region harmless.
>             age = _seconds_since(settled_through)
>             since = (max(OVERLAP_SECONDS, int(age) + OVERLAP_SECONDS)
>                      if age is not None else FIRST_SIGHT_SECONDS)
>         try:
>             lines = client.fetch_pod_log(ns, pod, since_seconds=since)
>         except ClusterError as exc:
>             log.warning("%s: login capture failed reading %s: %s",
>                         cluster.name, pod, exc.message)
>             continue
>         if lines is None:
>             continue
>         # An empty list is still a successful read; None is refusal/roll noise and cannot prove liveness.
>         read_ok = True
>         attempts = parse(lines)
>         horizon = _settle_horizon(attempts, lines)
>         if not attempts and horizon is None:
>             continue
>         observed_at = now_iso()
>         events = [event_dict(a, pod, observed_at) for a in attempts]
>
>         # This is best-effort fencing; the store's uniqueness and monotonic cursor make the residual
>         # instruction window harmless, while a network-length stale-leader window would not be.
>         if elector is not None and not elector.is_leader:
>             log.info("%s: lost leadership while reading %s — discarding %d event(s) unwritten",
>                      cluster.name, pod, len(events))
>             return recorded
>         if events:
>             n = store.record_login_events(cluster.name, events)
>             recorded += n
>             if n:
>                 log.info("%s: recorded %d login attempt(s) from %s", cluster.name, n, pod)
>         if horizon is not None:
>             store.set_login_watermark(cluster.name, pod, horizon, observed_at)
>
>     # Pod-list success makes this set authoritative even when individual log reads were refused.
>     if elector is None or elector.is_leader:
>         dropped = store.prune_login_watermarks(cluster.name, pods)
>         if dropped:
>             log.info("%s: forgot %d stale read position(s) for pods that no longer exist",
>                      cluster.name, dropped)
>     if not read_ok:
>         return recorded
>     if elector is not None and not elector.is_leader:
>         return recorded
>     store.record_login_read(cluster.name, now_iso())
>     _prune(store, cluster, settings, elector)
>     return recorded
> ```
>
> Complete regression test:
>
> ```python
> def test_non_login_lines_advance_a_quiet_pods_watermark(store, settings, install):
>     """The cursor follows successful log time, not only business events."""
>     old = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
>     recent = datetime.now(UTC) - timedelta(seconds=SETTLE_SECONDS + 10)
>     stamp = recent.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
>     progress = f"{stamp} I0807 00:00:00.0 1 httplog.go:1] ordinary request"
>     store.set_login_watermark(CLUSTER.name, POD, old, "x")
>     install(FakeClient(logs={POD: [progress]}))
>     capture_once(store, CLUSTER, settings)
>     assert store.login_watermarks(CLUSTER.name)[POD] == stamp
> ```

### Area 4 — API verdicts

> **Codex:** CONFIRMED — **A1** — `api.py:479-585#list_logins` and `587-668#cluster_access` both have
> `@consistent`. AST found only store calls in the handlers (five and four respectively), all in the
> decorated bodies. **DEBT-AVOIDED:** multi-query answers share a read snapshot.
>
> **Codex:** CONFIRMED — **A2** — `api.py:521-579#list_logins`. A simultaneous user+outcome+limit filter
> returned one attempt while `total=3` and the summary retained all three outcomes.
>
> **Codex:** CONFIRMED — **A3** — `api.py:74-90#_refusal_reason`. Probes returned `None` for success and
> unknown gate, and `not_gated` only for rejected+known+false membership.
>
> **Codex:** CONFIRMED — **A4** — `metrics.py:170-176#DashboardCollector.collect`; seeded names were
> absent from `/metrics`. No username-labelled family was added. **DEBT-AVOIDED:** personnel detail
> remains behind authenticated API routes.
>
> **Codex:** CONFIRMED — **A5** — the AST scope guard passed. Neither new handler imports/constructs a
> cluster client or performs network I/O; both call only `StorageBackend` methods.
>
> **Codex:** CONFIRMED — **A6** — `api.py:561-566` returns `settings.poll_interval_seconds`; the endpoint
> probe with 137 returned 137, and `index.html:1666-1674#captureSection` computes five intervals with a
> five-minute floor. No cadence is hardcoded.

### Area 5 — UI verdicts

> **Codex:** CONFIRMED — **U1** — `index.html:1049-1052#esc`, `1593-1617`, `1690-1809`, and
> `1870-1962`. I audited every API string on the two panels: username is escaped in both text and
> `data-user`; refusal tooltip text is escaped in `title`; outcome/provider/detail/pod/DN/group/name and
> group lists are escaped. Remaining interpolations are numbers, booleans, or closed local maps. `esc`
> encodes `& < > " '`. The Playwright regression could not launch in this sandbox, so this is source and
> sink verification, not a browser pass. **DEBT-AVOIDED:** title/data attributes use the same encoder as
> text instead of a weaker attribute-specific path.
>
> **Codex:** CONFIRMED — **U2** — `index.html:1641-1748#captureSection`. Capture-off explicitly says no
> capture; both enabled empty sub-branches and the non-empty branch include the unconditional `window_`
> sentence “nothing was observed, never that nobody signed in.”
>
> **Codex:** CONFIRMED — **U3** — `index.html:1868-1880#accessCard`; `synced:false` returns before all
> KPIs and explicitly says missing data, not a clean result.
>
> **Codex:** CONFIRMED — **U4** — `index.html:1795-1803`; gate chip requires
> `in_access_group === false && !break_glass`, and API derives `break_glass` solely from configured local
> providers. Directory rows remain labelled.
>
> **Codex:** CONFIRMED — **U5** — `index.html:2845-2882#wireDrilldown`; every emitted `data-user` or
> `data-group` control calls `navigate({page:'groups', ...})`, the only page whose render dispatch handles
> those details. Nonexistent users deliberately are not drill-downs.
>
> **Codex:** CONFIRMED — **U6** — `index.html:5-713#style`; static scan found no literal `font-size` in
> style, and the derived accessibility test passed. Measured `--tab-logins` is 4.67:1 light and 5.04:1
> dark. **DEBT-AVOIDED:** tests derive tab tokens, so a new tab cannot silently escape contrast coverage.

### Area 6 — chart verdicts

> **Codex:** CONFIRMED — **C1** — `templates/configmap.yaml:33-47`. Helm renders all four capture keys
> plus `clusterAccessGroup`; most importantly `loginCaptureEnabled` is present as `true` and `false`, so
> the disabled state is explicit rather than omission/default. I cross-checked `config.py:447-474`; the
> other absent keys are deliberately environment-backed or defaulted/conditional backup settings, not
> feature switches. **DEBT-AVOIDED:** the previously missing application switch is now rendered.
>
> **Codex:** CONFIRMED — **C2** — `templates/rbac.yaml:46-60`; enabled output is exactly oauths/get,
> `resourceNames: ['cluster']`; disabled output has no oauth rule. K3 and L6 prove refusal returns None
> and poll remains ok.
>
> **Codex:** CONFIRMED — **C3** — `charts/group-sync-dashboard/templates`; rendered output and source
> search contain no `kind: GroupSync`. The only CR is the explicitly out-of-chart example.
>
> **Codex:** CONFIRMED — **C4** — `templates/configmap.yaml:47`. Helm-rendered nested YAML with commas,
> colon and spaces parsed back to the exact Python string.

### Area 7 — reader verdicts

> **Codex:** CONFIRMED — **K1** — `kube.py:623-684#fetch_pod_log` uses `client.stream` and caps the
> returned line storage by `max_bytes`; it does not call `response.text` on a successful log. That narrow
> claim holds. The direction of truncation does not, and is the NEW finding immediately below.

> **Codex:** NEW — high — `kube.py:636-640,660-677#fetch_pod_log`.
>
> Trigger: stream `oldest-1`, `oldest-2`, `newest-3` with a 19-byte cap. The method returned the two
> oldest lines and stopped. The comment claims newest lines are kept, but Kubernetes streams oldest to
> newest. Combined with an old watermark, a current login is omitted while capture can remain green; the
> dashboard reader believes no attempt occurred. `iter_lines()` can also construct a single line larger
> than the cap before this code measures it. **DEBT-INTRODUCED:** the byte-bound and tail-retention
> contracts are comments contradicted by iteration direction and abstraction level.
>
> Complete replacement:
>
> ```python
> def fetch_pod_log(self, namespace: str, pod_name: str,
>                   since_seconds: int | None = None,
>                   max_bytes: int = 8 * 1024 * 1024) -> list[str] | None:
>     """Timestamped tail of one pod log, streamed with bounded retained bytes.
>
>     Kubernetes sends oldest first. A rolling byte tail must therefore consume the stream rather than
>     stop at the cap; stopping keeps precisely the lines least useful for current capture.
>     """
>     from collections import deque
>
>     params: dict[str, Any] = {"timestamps": "true"}
>     if since_seconds is not None:
>         params["sinceSeconds"] = str(since_seconds)
>     path = f"{POD_API_TMPL % namespace}/{pod_name}/log"
>     if max_bytes <= 0:
>         return []
>
>     chunks: deque[bytes] = deque()
>     size = 0
>     truncated = False
>     try:
>         with self._client() as client:
>             with client.stream("GET", path, params=params) as response:
>                 if response.status_code >= 400:
>                     response.read()
>                     return self._log_read_refused(response, namespace, pod_name)
>                 for chunk in response.iter_bytes(chunk_size=min(64 * 1024, max_bytes)):
>                     if len(chunk) >= max_bytes:
>                         chunks.clear()
>                         chunks.append(chunk[-max_bytes:])
>                         size = max_bytes
>                         truncated = True
>                         continue
>                     excess = size + len(chunk) - max_bytes
>                     while excess > 0 and chunks:
>                         first = chunks[0]
>                         if len(first) <= excess:
>                             chunks.popleft()
>                             size -= len(first)
>                             excess -= len(first)
>                         else:
>                             chunks[0] = first[excess:]
>                             size -= excess
>                             excess = 0
>                         truncated = True
>                     chunks.append(chunk)
>                     size += len(chunk)
>     except httpx.HTTPError as exc:
>         log.info("%s: could not read %s log (%s: %s)",
>                  self.cluster.name, pod_name, type(exc).__name__, exc)
>         return None
>
>     payload = b"".join(chunks)
>     if truncated:
>         # The retained tail can begin halfway through a line. Discard that fragment so the parser
>         # never sees a fabricated prefix with no timestamp.
>         boundary = payload.find(b"\n")
>         payload = payload[boundary + 1:] if boundary >= 0 else b""
>         log.info("%s: %s log exceeded the %d-byte cap; retained its newest complete lines",
>                  self.cluster.name, pod_name, max_bytes)
>     return payload.decode("utf-8", errors="replace").splitlines()
> ```
>
> Complete regression test:
>
> ```python
> def test_log_cap_retains_the_tail_without_buffering_the_whole_response(monkeypatch):
>     """A cap hit must keep current attempts, not the beginning of the requested window."""
>     import httpx
>     from gsd.config import ClusterConfig
>     from gsd.kube import ClusterClient
>     cluster = ClusterConfig("c", "https://api.example", token_env="X")
>     class Chunks(httpx.SyncByteStream):
>         def __init__(self):
>             self.values = [b"oldest-1\n", b"oldest-2\n", b"newest-3\n"]
>             self.yielded = 0
>         def __iter__(self):
>             for value in self.values:
>                 self.yielded += 1
>                 yield value
>     stream = Chunks()
>     transport = httpx.MockTransport(
>         lambda request: httpx.Response(200, stream=stream, request=request))
>     client = ClusterClient(cluster)
>     monkeypatch.setattr(client, "_client",
>                         lambda: httpx.Client(transport=transport, base_url="https://api.example"))
>     got = client.fetch_pod_log("ns", "pod", max_bytes=20)
>     assert stream.yielded == 3
>     assert "newest-3" in got and "oldest-1" not in got
> ```

> **Codex:** REFUTED — medium — **K2** — `kube.py:135-160#_access_group_from_ldap_url`.
>
> Trigger: `ldaps://h/dc=x?uid?sub?(memberOf==oops)`. The function returned `=oops`; checking only for
> the presence of `=` does not establish a non-empty attribute type. The poller stores this as the gate,
> no Group matches, and the reader is falsely instructed that the gate group has not been synced.
> Percent decoding, both spellings and no-membership all passed. **DEBT-INTRODUCED:** a syntactic
> security/correctness boundary is represented by a one-character heuristic.
>
> Complete replacement helpers and function:
>
> ```python
> _DN_ATTRIBUTE = re.compile(r"(?:[A-Za-z][A-Za-z0-9-]*|[0-9]+(?:\.[0-9]+)+)\Z")
>
>
> def _split_unescaped(value: str, delimiter: str) -> list[str] | None:
>     """Split RFC 4514 separators while preserving escaped punctuation."""
>     parts, current, escaped = [], [], False
>     for char in value:
>         if escaped:
>             current.extend(("\\", char))
>             escaped = False
>         elif char == "\\":
>             escaped = True
>         elif char == delimiter:
>             parts.append("".join(current))
>             current = []
>         else:
>             current.append(char)
>     if escaped:
>         return None
>     parts.append("".join(current))
>     return parts
>
>
> def _looks_like_dn(value: str) -> bool:
>     """Validate the RFC 4514 structure needed before a filter value is treated as a group DN."""
>     def valid_attribute_value(raw: str) -> bool:
>         if not raw:
>             return False
>         if raw.startswith("#"):
>             encoded = raw[1:]
>             return bool(encoded) and len(encoded) % 2 == 0 and bool(
>                 re.fullmatch(r"[0-9A-Fa-f]+", encoded))
>         if raw[0] in {" ", "#"} or raw[-1] == " ":
>             return False
>         index = 0
>         while index < len(raw):
>             char = raw[index]
>             if char == "\\":
>                 if index + 1 >= len(raw):
>                     return False
>                 if (index + 2 < len(raw)
>                         and re.fullmatch(r"[0-9A-Fa-f]{2}", raw[index + 1:index + 3])):
>                     index += 3
>                 else:
>                     index += 2
>                 continue
>             if char in {'"', ";", "<", ">"}:
>                 return False
>             index += 1
>         return True
>
>     rdns = _split_unescaped(value, ",")
>     if not rdns or any(not rdn for rdn in rdns):
>         return False
>     for rdn in rdns:
>         avas = _split_unescaped(rdn, "+")
>         if not avas:
>             return False
>         for ava in avas:
>             attribute, separator, attr_value = ava.partition("=")
>             if (not separator or not _DN_ATTRIBUTE.fullmatch(attribute.strip())
>                     or not valid_attribute_value(attr_value)):
>                 return False
>     return True
>
>
> def _access_group_from_ldap_url(url: str) -> str | None:
>     """A syntactically valid gated-group DN from an RFC 2255 URL, or None."""
>     _, separator, rest = url.partition("://")
>     if not separator:
>         return None
>     parts = rest.split("?")
>     if len(parts) < 4:
>         return None
>     filt = unquote(parts[3]).strip()
>     match = _ACCESS_GROUP_CLAUSE.search(filt) if filt else None
>     if not match:
>         return None
>     dn = match.group(1).strip()
>     return dn if _looks_like_dn(dn) else None
> ```
>
> Complete regression test:
>
> ```python
> def test_membership_value_with_an_empty_dn_attribute_is_rejected():
>     url = "ldaps://h/dc=x?uid?sub?(memberOf==oops)"
>     assert _access_group_from_ldap_url(url) is None
> ```

> **Codex:** CONFIRMED — **K3** — `kube.py:537-587#fetch_access_group_dn`. Forced results were
> forbidden→None, exact OAuth-path 404→None, and HTTP 500 whose body says 404→raised. The check is
> anchored with `startswith('HTTP 404 on ' + OAUTH_API)`.

### The five named debt checks

> **Codex:** **DEBT-INTRODUCED — outcome vocabulary.** `loginlog.py:69-90` is authoritative and
> `api.py:41-46` derives from it; `index.html:1520-1551` must hand-author reader wording/severity, which
> is justified because parser constants should not be shipped to the browser. What is missing is a
> cross-language invariant test. UI maintainers pay when a new parser outcome renders raw/unknown.
> Close it with this complete test (it passes today and fails on the next unmapped outcome):
>
> ```python
> def test_every_parser_outcome_has_browser_label_and_badge():
>     import re
>     from pathlib import Path
>     from gsd import loginlog
>     html = (Path(__file__).parents[1] / "gsd/static/index.html").read_text()
>     outcomes = {v for k, v in vars(loginlog).items()
>                 if k.startswith("OUTCOME_") and isinstance(v, str)}
>     def keys(name):
>         block = re.search(rf"const {name} = \{{(.*?)\n\}};", html, re.S).group(1)
>         return set(re.findall(r"^\s*([a-z_]+):", block, re.M))
>     assert keys("OUTCOME_LABEL") == outcomes
>     assert keys("OUTCOME_BADGE") == outcomes
> ```
>
> **Codex:** **DEBT-AVOIDED / DEBT-INTRODUCED — SQL predicates.** `_not_local_provider` and the
> ungoverned base WHERE are shared and regression-tested, avoiding the shipped S3 drift. The
> `access_without_login` row/count predicate is still duplicated; current outputs agree, but storage
> maintainers pay on the next gate-rule change. Share it then, as done in the NEW gate-only replacement.
>
> **Codex:** **DEBT-AVOIDED — login-gate DN across four files.** `kube.py` owns syntax/equality,
> `poller.py` resolves against one observation, `store.py` persists that observation, and `api.py` reads
> it without cluster I/O. These are justified boundaries, not four sources of truth; L7 proves the
> join. Collapsing them would reintroduce torn observations or cluster reads in handlers.
>
> **Codex:** **DEBT-INTRODUCED — `docs/examples/clusteraccess-groupsync.yaml`.** It duplicates the
> separate platform chart's 0.12.0 configuration with no agreement test. Platform operators pay when
> that chart's values/schema changes and this runnable example still looks authoritative. Keep the CR
> out of this chart, but validate this fixture in CI against the pinned platform-chart schema/render;
> revisit at every platform-chart upgrade.
>
> **Codex:** **DEBT-ACCEPTED — fixture helpers.** `_lines` is a loop-level real-log builder, `_record`
> is a storage seeder, `_iso` fixes storage formatting, and `event_dict` is already shared production
> code. Combining them would couple tests across layer boundaries for little reuse. Pay down only if a
> fourth test module starts hand-building the same layer's shape or a field change requires synchronized
> edits in more than one helper.

### Whole-PR debt summary

> **Codex:** **DEBT-INTRODUCED:** unsafe cause attribution, unvalidated retention bounds, migration
> ordering dependence, two capped “whole”/tail semantics, the browser outcome-map invariant, one copied
> access predicate, and an untested cross-repository example. **DEBT-ACCEPTED:** exact byte-identical
> log occurrences cannot be distinguished without an upstream id; leadership is best-effort without a
> fencing token; first-sight/retention deliberately limit history; test helpers remain layer-local.
> **DEBT-AVOIDED:** S3's predicate is shared, L3 is now wall-clock-relative, C1 renders both boolean
> states, API reads are snapshotted and cluster-free, unknown gate membership stays nullable, sensitive
> LDAP text stops at the parser, chart RBAC is optional/name-scoped, and the chart does not own GroupSync
> CRs. The debt is worth the feature only after the high-severity wrong-data findings above are fixed;
> with those fixes, the remaining accepted debt is proportionate to a forward-only log-derived record.

---

## Fable — pass 2

**NARROWED, deliberately.** Codex CONFIRMED 36 of the 44 claims with measurements. Re-covering those
spends the pass on settled ground. Your job is the 9 findings it did NOT confirm, and above all the code
it proposes to fix them with.

### What you are here to do, in priority order

1. **VALIDATE CODEX'S REPLACEMENTS AS LOGIC.** Nine findings, 36 code blocks. Read each replacement and
   decide whether it does what it claims, whether it breaks something else, and whether it is the right
   fix rather than merely a fix. This is the whole point of a second pass: the arbiter is about to apply
   this code, and nobody has checked it.
2. **AGREE / DISAGREE on every one of Codex's 9 findings, with evidence.** Not an opinion — a command
   you ran, a line you read, a scratch script's output. A pass that only adds its own findings has not
   reviewed the first one.
3. **Where you DISAGREE, or where the fix is inadequate, write the corrected FULL replacement** in this
   file. Same bar as Codex: the whole function, ready to apply, a complete test that fails before and
   passes after, and the comment style preserved — this codebase's comments say WHY, and stripping the
   reasoning out of a function is a regression even when the logic is right.
4. **New findings are welcome but secondary.** Only in the seven areas the brief lists, and only what the
   out-of-scope section does not rule out.

### The findings to validate

| where | verdict | severity |
|---|---|---|
| `loginlog.py#_VERDICT` — P1, phrase not anchored to the message | REFUTED | high |
| `loginlog.py#parse` — P2/P3, a cause attaches to the wrong person | REFUTED | high |
| `store.py#prune_login_events` — S5 | REFUTED | medium |
| `kube.py#_access_group_from_ldap_url` — K2 | REFUTED | medium |
| `store.py#login_without_access` + `cluster_access_summary` — a KPI from a pagination cap | NEW | high |
| `logincapture.py#capture_once` + `_settle_horizon` — the cursor never advances on a quiet pod | NEW | high |
| `kube.py#fetch_pod_log` — the byte cap keeps the OLDEST lines | NEW | high |
| `store.py#_MIGRATIONS` / `_migrate` | NEW | low |

### SPECIFIC REGRESSIONS TO HUNT — these are the ones the arbiter is worried about

Not hypotheticals. Each is a property the current code has, that a proposed fix could take away.

- **The `parse()` rewrite must not break the SINGLE-PROVIDER cluster.** On a cluster whose only identity
  provider is LDAP, an attempt STARTS with `ldap.go:131 searching` — the cause arrives BEFORE any line
  names the user, so there is no pending attempt to attach it to. That is the `orphan` path, and it
  exists because dropping those loses every cause on such a cluster, including expired passwords. It was
  a real defect once. Codex's `_cause_mentions_user` gate must still admit the orphan case.
- **`_cause_mentions_user` may silently break ACTIVE DIRECTORY.** It matches the cause text against the
  username from the verdict. On this lab those agree, because the IdP maps `preferredUsername: uid` and
  the DN is `uid=jane.smith,...`. On AD the username is commonly `sAMAccountName` while the DN is
  `CN=Jane Smith,OU=People,...` — **the two do not match**, so every AD cause would be rejected and every
  AD failure would degrade to a bare `failed`. That would delete the entire AD sub-code feature
  (`data 532` expired, `775` locked, and the rest) without a single test failing, because this lab is
  OpenLDAP. Check this specifically, and say what the fix should be if it is real.
- **Exact matching, not substring.** P3's own trigger is a DN containing `uid=alice` being credited to a
  different user. A fix that greps for the username as a substring reintroduces it: `uid=bob` matches
  `uid=bobby`. Verify the boundary.
- **The watermark fix must not advance past an UNSETTLED attempt.** The settle horizon exists because the
  newest lines of a live log are the ones most likely to be mid-attempt — failure lines written, success
  line not yet. A cursor derived from "log time successfully read" is the right direction, but it must
  not skip an attempt whose lines are still arriving.
- **The `fetch_pod_log` fix must not buffer the whole log.** Keeping the NEWEST lines under a byte cap
  while reading an oldest-to-newest stream is the actual problem. A fix that reads everything and then
  takes the tail defeats the byte bound it is fixing — the bound exists so a large log cannot be held in
  memory. Check what it does at the boundary, including a single line larger than the cap.
- **The summary-count fix must SHARE the predicate.** S3 was a real defect precisely because a count and
  its list used two copies of one predicate. A fix that adds a second scalar query with the predicate
  written out again reintroduces that class of bug. It must go through one helper.

### Requirements, unchanged from pass 1

Full code in this document. A complete test per finding. The three debt buckets
(DEBT-INTRODUCED / DEBT-ACCEPTED / DEBT-AVOIDED). Honour the out-of-scope list. Measure rather than
reason: the suite is `cd local-development && .venv/bin/python -m pytest tests/ -q --deselect
tests/test_live_smoke.py`, baseline **1024 passed, 1 skipped**. Run it. Write scratch scripts against a
scratch SQLite database. If you assert a behaviour, show the command and its output.

Finish with a one-paragraph verdict: **is this PR safe to merge once the surviving fixes are applied**,
and which single finding would you fix first.

---

## Arbitration

The arbiter fills this in after both passes: what is applied, what is rejected and why, and what is
deferred with the reason. A finding rejected here must say which evidence contradicted it.
