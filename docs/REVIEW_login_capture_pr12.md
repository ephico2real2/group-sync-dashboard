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

### Fable — method and command ledger

> **Fable:** The mandatory command was run first, exactly as specified, on this machine (Chromium
> launches here, so the browser tests ran):
>
> ```text
> cd local-development && .venv/bin/python -m pytest tests/ -q --deselect tests/test_live_smoke.py
> 1 failed, 1032 passed, 1 skipped, 4 deselected in 102.05s
> ```
>
> That is NOT the published baseline, and the delta is itself a finding (the last NEW below): the one
> failure is `test_docs_citations.py#test_no_citation_uses_a_line_number`, and every offender it lists
> is a `file:NNN` citation written into THIS DOCUMENT by pass 1. The suite was green before this file
> was committed; no product test fails.
>
> Everything else was measured on scratch copies of the `gsd` package — never on the repo files.
> Three sibling package trees were built under the session scratchpad: `repo/` (untouched copy,
> the control), `codex/` (every pass-1 replacement applied verbatim, transcribed from this file),
> and `fable/` (my corrected replacements plus the pass-1 fixes I endorse). The repo's own test
> files were run against each tree by invoking pytest from inside it, and the import path was
> verified before anything else was trusted (`gsd.loginlog.__file__` printed from each tree).
> Summary of the scratch outputs quoted throughout, so the arbiter can cross-check:
>
> ```text
> existing test_loginlog.py:            repo 36 passed | codex 36 passed | fable 36 passed
> AD bind, multi-provider (data 532):   repo password_expired | codex FAILED->failed | fable password_expired
> AD bind, orphan path (data 775):      repo account_locked   | codex FAILED->failed | fable account_locked
> discriminating parser battery (6):    repo 1/6 | codex 3/6 | fable 6/6
> test_logincapture_loop.py, verbatim:  codex replacement: 2 FAILED (both direct _settle_horizon calls)
> quiet-pod watermark (Codex's test):   repo FAILED (stays 30 days old) | fable passes
> sliced-read phantom:                  repo records (jane.smith, failed) AND (jane.smith, success), same instant
> store: fresh user_version:            repo 5 | codex 6   (latest migration is 6)
> store: prune max_rows=-1:             repo deleted 10 | codex deleted 0
> store: summary, 10,001 gate-only:     repo 10000 | codex 10001
> K2 '(memberOf==oops)':                repo '=oops' | codex None; 9-case real-DN battery: no false rejection
> fetch_pod_log byte cap (bytes kept):  repo 31 of a 20-byte cap (chars counted) | codex 20 | fable <=20
> fetch_pod_log cap direction:          repo keeps OLDEST but logs "newest lines are kept" | codex keeps newest
> two-cycle truncation simulation:      shipped direction: alice,bob then +carol (complete)
>                                       codex direction:   bob,carol then nothing — alice UNRECOVERABLE, capture green
> proposed tests/test_kube_reader.py:   repo 3 failed / 6 passed | codex 2 failed / 7 passed | fable 9 passed
> storage suites vs codex store fixes:  116 passed (capture, migrations, seam, store-poller, api-contract)
> composite (fable) focused suites:     147 passed (loginlog, loop-rewritten, capture, migrations, seam)
> composite (fable) FULL suite:         1 failed, 1072 passed, 1 skipped in 107s — the failure is the
>                                       pass-1 citation format below, cured by the REVIEW_ARTIFACTS fix
> offenders after that one-line fix:    NONE (rescanned every repo markdown with the extended tuple)
> ```

### Verdicts on the nine pass-1 findings, and on their code

> **Fable:** AGREE — high — `local-development/gsd/loginlog.py#_VERDICT` (P1 REFUTED stands).
>
> Reproduced: the pass-1 trigger line (`audit.go` header, verdict phrase mid-message) parses to a
> success for `alice` on the repo tree. The proposed anchor `\]\s+` is the right shape: every one of
> the four measured verdict grammars in `tests/test_loginlog.py` begins the klog MESSAGE with the
> phrase (the `]` closing the header immediately precedes it), so anchoring to the message start
> drops relayed copies without touching any real verdict. All 36 existing parser tests pass with the
> anchor applied, and a line whose quoted text embeds a full klog line INCLUDING the `x.go:1]` header
> remains unmatchable only by a request id the log does not have — that residue is acceptable and
> worth a sentence in the comment, not more code. Codex's regression test is kept verbatim.
>
> ONE DEFECT IN THE SUBMISSION, not the regex: the replacement block strips the forty-line measured
> comment above `_VERDICT` — the two-grammar story, the 29-versus-3 count, the reason the anchor is
> the phrase and not the file:line. That comment is the module's institutional memory and the reason
> P1's own fix is verifiable. The block to apply is the FULL one:
>
> ```python
> # THE VERDICT LINE COMES IN TWO GRAMMARS, and the difference is one word. Measured on the live
> # cluster, all four shapes the oauth-server actually emits:
> #
> #   basicauth.go:48]  Login with provider "developer" failed for login "jane.smith"
> #   basicauth.go:51]  Login with provider "ldap-local" succeeded for login "jane.smith"
> #   login.go:183]     Login with provider "developer" failed for "developer"
> #   login.go:191]     Login with provider "developer" succeeded for "developer": &groupmapper...
> #
> # basicauth.go serves the CLI (`oc login -u -p`, HTTP basic auth) and says `for login "<user>"`.
> # login.go serves the HTML FORM — the console, which is how people actually sign in — and says
> # `for "<user>"` with no `login`. So requiring the word dropped every browser login on the cluster
> # while capturing every CLI one, and the failure was silent: the tab simply showed fewer rows than
> # had happened. Found by signing in through the console and finding nothing recorded; counted in the
> # pod's whole log at the time, 29 CLI verdicts captured and 3 browser verdicts missed.
> #
> # `(?:login )?` rather than two patterns: it is one message with an optional word, and two regexes
> # would be two places to keep in step.
> #
> # Anchored on the phrase rather than the file:line, because those line numbers move between
> # OpenShift releases while the message has been stable — and anchored to the START of the klog
> # message (the `]` that closes the header, then whitespace) because the phrase alone also matched
> # itself QUOTED INSIDE another message: a line relaying text that contains the sentence produced a
> # login attempt for somebody who never logged in. The oauth-server writes its verdicts as the
> # message's first words; relayed copies sit mid-message. A relayed copy of a WHOLE klog line,
> # header included, would still match — only a request id could reject that, and the log has none.
> #
> # The correlation below needs no change for the new shape — it keys on username and window, not on
> # provider or call site. A browser login picks ONE provider (`idp=developer`), so there is no
> # provider chain and a lone `failed` is a real failure rather than the ordinary CLI noise; retries
> # arrive seconds apart, well outside ATTEMPT_WINDOW, so fail-fail-succeed stays three attempts.
> _VERDICT = re.compile(
>     r'\]\s+Login with provider "(?P<provider>[^"]*)" '
>     r'(?P<verdict>succeeded|failed) for (?:login )?"(?P<user>[^"]*)"'
> )
> ```
>
> Test: pass 1's `test_a_verdict_phrase_inside_an_unrelated_message_is_not_an_attempt`, unchanged.
> Verified failing on the repo tree (a false `alice` success is returned) and passing on both
> replacement trees. **DEBT-AVOIDED** by the anchor; **DEBT-INTRODUCED** by the submission's comment
> deletion, which the block above repays.

> **Fable:** FIX-INADEQUATE — high — `local-development/gsd/loginlog.py#parse` (P2/P3: the defect is
> real, the proposed remedy silently deletes the Active Directory sub-code feature).
>
> THE DEFECT, CONFIRMED: on the repo tree the six-case battery shows both misattributions. Alice's
> code-49 bind cause attaches to Bob under interleaving (P2), and an identified orphan cause is
> stolen by whichever verdict lands first (P3). Wrong data as fact — the dashboard tells Bob's
> manager he mistyped a password when it was Alice's expired one. High is right.
>
> THE REMEDY, MEASURED: `_cause_mentions_user` requires the cause's OWN text to name the verdict's
> username. On this lab that holds, because the IdP maps `preferredUsername: uid` and OpenLDAP DNs
> are `uid=jane.smith,...`. On Active Directory the verdict says `jsmith` (sAMAccountName) while the
> bind error quotes `CN=Jane Smith,OU=People,...` — they can never match. Applied verbatim to the
> codex tree and driven with real-shape AD lines:
>
> ```text
> repo  : multi-provider CLI  -> password_expired (data 532 read)   orphan -> account_locked (data 775 read)
> codex : multi-provider CLI  -> failed, code=None                  orphan -> failed, code=None
> ```
>
> Every AD failure degrades to a bare `failed`; `_AD_SUBCODE`, `_RESULT_CODE`'s refinements and the
> whole operational point of the sub-code map (reset a password, unlock an account) become dead code
> on the one directory family they exist for. And ALL 36 EXISTING TESTS STAY GREEN, because the AD
> fixtures in `tests/test_loginlog.py#TestActiveDirectorySubCodes` synthesise their AD diagnostics
> onto the OpenLDAP fixture DN (`uid=jane.smith`) — exactly the silent deletion the arbiter feared.
> A second, smaller loss: pass 1's orphan gate also DESTROYS an unadopted orphan at the first
> stranger's verdict (`orphan = None` runs whether or not the mention matched), so even on OpenLDAP
> the rightful owner arriving 50ms later gets nothing — its own battery result shows alice losing
> her cause to nobody.
>
> THE CORRECT INSTRUMENT IS ALREADY IN THE LOG. The measured grammar (module docstring, and the
> `ldap.go:148` fixtures) includes `found dn="<dn>" for (<filter>)`, written between the search and
> the bind — and the FILTER embeds the typed login on EVERY directory (`(uid=jane.smith)` here,
> `(sAMAccountName=jsmith)` on AD), because the IdP composes it from the login. Holding a one-window
> map of DN → found-line lets a bind error be attributed by identity on AD too, which closes P2 and
> P3 without the false-negative trade pass 1 accepted. Attribution precedence, in one place:
> identity when the evidence names exactly one pending login; adjacency only when nothing is named,
> nothing else is in flight, and the cause could not have identified anybody; otherwise hold it for
> the verdict that names it, or drop it rather than guess between two humans.
>
> Complete replacement — two new module-level names beside the existing cause regexes, and the whole
> of `parse`. Everything else in the module is untouched; the fixed `_VERDICT` is in the P1 block.
>
> ```python
> # The DN the directory search RESOLVED for one login — `found dn="<dn>" for (<filter>)` — logged
> # between `searching` and the bind. Progress, not a cause, but it is the ONLY line that ties a bind
> # DN back to the login that produced it: the filter it quotes embeds the typed login on every
> # directory, while the DN itself does so only on directories that happen to name entries by their
> # login attribute. OpenLDAP here writes `uid=jane.smith,...`; Active Directory writes
> # `CN=Jane Smith,...` for a login of `jsmith`, and without this line an AD bind error could not be
> # attributed to anybody by its own text.
> _FOUND = re.compile(r'found dn="(?P<dn>[^"]*)" for ')
>
>
> def _cause_mentions_user(text: str, user: str) -> bool:
>     """Whether an `attribute=value` assertion in this cause text names exactly this login.
>
>     The assertion forms are what the cause grammars actually carry: a bind error quotes the entry's
>     DN, `no entries matching` quotes the search filter (whose last clause embeds the typed login on
>     every directory), and a `found dn=` line quotes both. EXACT boundaries, not a substring test —
>     `uid=bob` must not be credited to `bobby` — which is the wrong-person bug this check exists to
>     prevent. Correlation only: nothing this reads is ever persisted (see _detail).
>     """
>     value = re.escape(user)
>     return re.search(
>         rf'(?i)["(,]\s*[a-z0-9.-]+\s*=\s*{value}\s*(?:[,)"]|$)', text
>     ) is not None
>
>
> def parse(lines: list[str] | str) -> list[LoginAttempt]:
>     """Every login attempt in these lines, oldest first.
>
>     Correlates by username within ATTEMPT_WINDOW: the provider-order noise means one attempt spans
>     several lines, and a `failed` for the same person can be part of a SUCCESS. An attempt is concluded
>     when a verdict arrives for a provider after the deciding one, when the window expires, or at the end
>     of the input.
>
>     CAUSE LINES NAME NO USER, so attribution is by evidence with a narrow adjacency fallback, never by
>     recency between two people: under interleaving, "the most recent attempt" assigned one person's
>     directory diagnosis to another, and a false cause is worse than the provider's honest no-reason
>     result. The evidence is the cause's own text plus the `found dn=` line that resolved its bind DN —
>     the latter because an Active Directory DN (`CN=Jane Smith,...`) never repeats the login (`jsmith`),
>     and requiring the cause itself to name the user would silently discard every AD cause.
>
>     Lines with no kubelet timestamp are skipped rather than guessed at — a record whose instant is
>     invented is worse than one that is absent.
>     """
>     if isinstance(lines, str):
>         lines = lines.splitlines()
>
>     pending: dict[str, _Pending] = {}
>     out: list[LoginAttempt] = []
>     # A cause can arrive BEFORE any line names its user, and on a cluster whose only identity provider
>     # is LDAP it always does — the attempt starts at `ldap.go:131 searching`, so nothing has created a
>     # pending entry yet. That is the ordinary production shape, not an edge case: this cluster only
>     # gets a username first because htpasswd is tried before ldap and logs a failure. Dropping these
>     # would lose every cause on a single-provider cluster, including expired passwords. A LIST, not a
>     # slot: an identified orphan waits for the verdict that names its person, so an interleaved
>     # stranger's verdict must be able to pass it by without destroying it.
>     orphans: list[dict] = []
>     # Recent `found dn=` lines by DN, kept one window: the bind error that follows quotes the DN, and
>     # this is what lets it be attributed on a directory whose DNs do not contain the login.
>     found: dict[str, dict] = {}
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
>             # Progress lines only, no verdict — nothing happened worth recording.
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
>     def adopt(p: _Pending, user: str, ts: datetime) -> None:
>         """Give a fresh pending attempt the orphan cause that belongs to it, if one is waiting.
>
>         An IDENTIFIED orphan (its evidence names a login) is taken only by that login's verdict —
>         adopting by arrival order is how one person's diagnosis reached another. An UNIDENTIFIED
>         orphan (a bind whose `found dn=` fell outside this read, so nothing ties its DN to a login)
>         goes to the first verdict inside the window: refusing it would discard every cause on a
>         directory whose DNs do not carry the login, which is a systematic loss, where the adjacency
>         guess is only wrong in a sliced read that also interleaves two people inside one second.
>         """
>         for i, o in enumerate(orphans):
>             if not timedelta(0) <= ts - o["at"] <= ATTEMPT_WINDOW:
>                 continue
>             if o["identified"] and not _cause_mentions_user(o["evidence"], user):
>                 continue
>             p.first_at = o["at"]
>             p.saw_no_entries = o["no_entries"]
>             p.bind_code = o["code"]
>             p.bind_diagnostic = o["diagnostic"]
>             del orphans[i]
>             return
>
>     for raw in lines:
>         ts = parse_timestamp(raw)
>         if ts is None:
>             continue
>
>         # Expire anything whose window has passed, so a long-running read does not merge two attempts
>         # by the same person minutes apart — and so stale correlation state cannot leak forward.
>         for user in [u for u, p in pending.items() if ts - p.first_at > ATTEMPT_WINDOW]:
>             conclude(user)
>         orphans[:] = [o for o in orphans if ts - o["at"] <= ATTEMPT_WINDOW]
>         for dn in [d for d, f in found.items() if ts - f["at"] > ATTEMPT_WINDOW]:
>             del found[dn]
>
>         v = _VERDICT.search(raw)
>         if v:
>             user = v.group("user")
>             provider = v.group("provider")
>             p = pending.get(user)
>             if p is None:
>                 p = pending[user] = _Pending(first_at=ts, last_at=ts)
>                 adopt(p, user, ts)
>             p.last_at = ts
>             if v.group("verdict") == "succeeded":
>                 p.succeeded = True
>                 p.provider = provider
>                 conclude(user)          # a success ends the attempt; nothing after it can change it
>             else:
>                 p.failures.append(provider)
>                 # The provider that decided a FAILURE is the last one to reject, so this is overwritten
>                 # deliberately as later providers are tried.
>                 p.provider = provider
>             continue
>
>         f = _FOUND.search(raw)
>         if f:
>             found[f.group("dn")] = {"at": ts, "raw": raw}
>             continue
>
>         no_entries = bool(_NO_ENTRIES.search(raw))
>         b = None if no_entries else _BIND_ERROR.search(raw)
>         if not no_entries and b is None:
>             continue
>
>         # What this cause can prove about WHO it belongs to. `no entries matching` quotes the search
>         # filter, which embeds the typed login on every directory. A bind error only quotes the DN, so
>         # it is identifying evidence only together with the `found dn=` line that resolved it.
>         evidence = raw
>         identified = no_entries
>         if b is not None:
>             ctx = found.get(b.group("dn"))
>             if ctx is not None:
>                 evidence = f'{raw} {ctx["raw"]}'
>                 identified = True
>
>         mentioned = [u for u in pending if _cause_mentions_user(evidence, u)]
>         if len(mentioned) == 1:
>             target = mentioned[0]
>         elif not mentioned and not identified and len(pending) == 1:
>             # A bind whose found line fell outside this read window: adjacency is the only evidence
>             # left, and with exactly one attempt in flight it is sound.
>             target = next(iter(pending))
>         else:
>             target = None
>
>         if target is not None:
>             if no_entries:
>                 pending[target].saw_no_entries = True
>             else:
>                 pending[target].bind_code = int(b.group("code"))
>                 pending[target].bind_diagnostic = b.group("diagnostic") or ""
>             pending[target].last_at = ts
>         elif len(mentioned) > 1:
>             # One cause naming two in-flight logins has no honest owner. Dropping it degrades both
>             # to the provider's own verdict, which is true; guessing would make one of them false.
>             pass
>         elif identified or not pending:
>             # Held for the verdict that names this person — see `orphans` above.
>             orphans.append({
>                 "at": ts,
>                 "evidence": evidence,
>                 "identified": identified,
>                 "no_entries": no_entries,
>                 "code": None if b is None else int(b.group("code")),
>                 "diagnostic": "" if b is None else (b.group("diagnostic") or ""),
>             })
>         # An unidentified cause with SEVERAL people in flight is dropped: any attachment would be a
>         # guess between named humans, and the guess is exactly the defect this branch replaced.
>
>     for user in list(pending):
>         conclude(user)
>
>     out.sort(key=lambda a: (a.at, a.user_name))
>     return out
> ```
>
> WHAT THIS PRESERVES, MEASURED: all 36 existing parser tests pass unchanged, including the two
> orphan-path tests that pin the single-provider cluster (the arbiter's first regression), and both
> AD scenarios keep their sub-codes. What it fixes beyond pass 1: interleaved attribution on AD as
> well as OpenLDAP, and an identified orphan surviving a stranger's verdict. What it accepts,
> deliberately: a login containing LDAP-filter metacharacters is escaped by the IdP before it reaches
> the filter, so its no-entries cause no longer matches the typed name and degrades to a bare
> `failed`/`rejected`-less row — honest, and confined to logins that contain `(`, `)`, `\` or `*`.
> A bare bind orphan with NO found line in the same read (only possible when a read boundary slices
> between two lines written microseconds apart) still adopts by adjacency, so pass 1's
> `test_orphan_cause_must_name_the_verdict_user` MUST NOT be applied as written — on AD that rule is
> indistinguishable from the systematic loss above, and the test below replaces it with the
> identified form. **DEBT-INTRODUCED**, named: the parser now depends on the `found dn=` grammar as
> well as the verdict/cause grammars — one more line shape release drift could break, carried by the
> same measured-fixture tests that carry the others. **DEBT-AVOIDED:** raw DN/filter text remains
> correlation-only and never reaches `detail`; the existing security test still passes.
>
> Complete tests — pass 1's two, kept verbatim where right, plus the four that discriminate. All six
> pass on the corrected tree; on the repo tree only the plain-AD one passes (the shipped parser keeps
> AD causes — by guessing); pass 1's tree fails the three marked:
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
>
>
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
> AD_DIAG = ('LDAP Result Code 49 "Invalid Credentials": 80090308: LdapErr: DSID-0C0903A9, '
>            'comment: AcceptSecurityContext error, data 532, v4563')
>
>
> def _line(iso: str, message: str) -> str:
>     return f"{iso} I0807 00:00:00.000000       1 x.go:1] {message}"
>
>
> def test_an_active_directory_cause_survives_without_the_login_in_the_dn():
>     """FAILS ON PASS 1'S TREE — the finding that rejects its parse replacement.
>
>     On AD the verdict says `jsmith` while the DN says `CN=Jane Smith`. The sub-code map exists FOR
>     this directory, so a correlation rule that requires the cause text to repeat the login deletes
>     the feature exactly where it matters, and no OpenLDAP fixture can notice."""
>     cli = parse([
>         _line('2026-08-07T10:00:00.000000000Z',
>               'Login with provider "developer" failed for login "jsmith"'),
>         _line('2026-08-07T10:00:00.100000000Z',
>               f'error binding password for "CN=Jane Smith,OU=People,DC=corp,DC=example": {AD_DIAG}'),
>         _line('2026-08-07T10:00:00.200000000Z',
>               'Login with provider "ad" failed for login "jsmith"'),
>     ])
>     assert cli[0].outcome == loginlog.OUTCOME_PASSWORD_EXPIRED, cli
>
>     orphaned = parse([
>         _line('2026-08-07T11:00:00.000000000Z',
>               f'error binding password for "CN=Jane Smith,OU=People,DC=corp,DC=example": {AD_DIAG}'),
>         _line('2026-08-07T11:00:00.001000000Z',
>               'Login with provider "ad" failed for "jsmith"'),
>     ])
>     assert orphaned[0].outcome == loginlog.OUTCOME_PASSWORD_EXPIRED, orphaned
>
>
> def test_an_identified_orphan_waits_for_the_verdict_that_names_it():
>     """P3 done right: alice's cause (tied to her by the found line) must not attach to bob's
>     verdict even when his lands first — and must still be there when hers lands. FAILS on the repo
>     tree (bob steals the cause) AND on pass 1's tree (the orphan is destroyed at bob's verdict)."""
>     got = parse([
>         _line('2026-08-07T12:00:00.000000000Z',
>               'found dn="uid=alice,dc=example" for (&(&(uid=*))(uid=alice))'),
>         _line('2026-08-07T12:00:00.050000000Z',
>               'error binding password for "uid=alice,dc=example": '
>               'LDAP Result Code 49 "Invalid Credentials": '),
>         _line('2026-08-07T12:00:00.900000000Z',
>               'Login with provider "ldap" failed for "bob"'),
>         _line('2026-08-07T12:00:00.950000000Z',
>               'Login with provider "ldap" failed for "alice"'),
>     ])
>     by_user = {a.user_name: a for a in got}
>     assert by_user["bob"].outcome == loginlog.OUTCOME_FAILED
>     assert by_user["bob"].ldap_result_code is None
>     assert by_user["alice"].outcome == loginlog.OUTCOME_BAD_PASSWORD
>     assert by_user["alice"].ldap_result_code == 49
>
>
> def test_the_mention_check_is_exact_not_substring():
>     """`uid=bob` must reach bob even when bobby's attempt is the more recent one — a substring
>     match reintroduces P3 one keystroke at a time."""
>     got = parse([
>         _line('2026-08-07T13:00:00.000000000Z',
>               'Login with provider "developer" failed for login "bob"'),
>         _line('2026-08-07T13:00:00.100000000Z',
>               'Login with provider "developer" failed for login "bobby"'),
>         _line('2026-08-07T13:00:00.200000000Z',
>               'no entries matching (&(&(uid=*)(memberOf=cn=gate,dc=example))(uid=bob))'),
>         _line('2026-08-07T13:00:00.300000000Z',
>               'Login with provider "ldap" failed for login "bob"'),
>         _line('2026-08-07T13:00:00.400000000Z',
>               'Login with provider "ldap" failed for login "bobby"'),
>     ])
>     by_user = {a.user_name: a for a in got}
>     assert by_user["bob"].outcome == loginlog.OUTCOME_REJECTED
>     assert by_user["bobby"].outcome == loginlog.OUTCOME_FAILED
>
>
> def test_two_people_in_flight_on_active_directory_attach_by_the_found_dn():
>     """The found line's filter carries `sAMAccountName=jsmith`, so the bind that follows belongs
>     to jsmith even though tbrown's attempt is more recent. FAILS on the repo tree (tbrown is
>     newest and takes the cause) and on pass 1's tree (the cause is dropped)."""
>     got = parse([
>         _line('2026-08-07T14:00:00.000000000Z',
>               'Login with provider "developer" failed for login "jsmith"'),
>         _line('2026-08-07T14:00:00.100000000Z',
>               'Login with provider "developer" failed for login "tbrown"'),
>         _line('2026-08-07T14:00:00.150000000Z',
>               'found dn="CN=Jane Smith,OU=People,DC=corp,DC=example" for '
>               '(&(&(objectClass=person)(memberOf=CN=gate,OU=Groups,DC=corp,DC=example))'
>               '(sAMAccountName=jsmith))'),
>         _line('2026-08-07T14:00:00.200000000Z',
>               f'error binding password for "CN=Jane Smith,OU=People,DC=corp,DC=example": {AD_DIAG}'),
>         _line('2026-08-07T14:00:00.300000000Z',
>               'Login with provider "ad" failed for login "jsmith"'),
>         _line('2026-08-07T14:00:00.400000000Z',
>               'Login with provider "ad" failed for login "tbrown"'),
>     ])
>     by_user = {a.user_name: a for a in got}
>     assert by_user["jsmith"].outcome == loginlog.OUTCOME_PASSWORD_EXPIRED
>     assert by_user["tbrown"].outcome == loginlog.OUTCOME_FAILED
>     assert by_user["tbrown"].ldap_result_code is None
> ```

> **Fable:** AGREE — medium, at the low edge — `local-development/gsd/store.py#Store.prune_login_events`
> (S5 REFUTED stands; apply the guard, but with the merged docstring below).
>
> Reproduced on a scratch database: `max_rows=-1` deleted all 10 old rows (`LIMIT -1` is SQLite's
> "no limit"), so the method's own contract — the docstring says "at most `max_rows` per call" — is
> unenforced at the storage seam. Severity honesty: no shipped caller can reach it (the only caller
> is `local-development/gsd/logincapture.py#_prune`, which passes no `max_rows`, and
> `login_retention_days` cannot produce one), so today this is a seam contract violation, not a live
> data-loss path; it becomes live with the first future caller. The guard is right and cheap.
> Pass 1's replacement, though, swaps the docstring for a thinner one and loses the sentence callers
> are built against ("a return of max_rows means backlog remains") plus both verified notes. Apply
> this version — the body is pass 1's, the docstring keeps what was already true:
>
> ```python
> def prune_login_events(self, cluster_id: str, before_at: str, max_rows: int = 5000) -> int:
>     """Delete events older than `before_at`, at most `max_rows` per call. Returns rows deleted.
>
>     BOUNDED, because this runs on the poll thread against a single-writer database: an unbounded
>     DELETE across a long retention backlog holds the write lock for as long as it takes, and
>     every reader and the next poll wait behind it. The caller treats a return of `max_rows` as
>     "backlog remains, continue next cycle". A non-positive limit deletes NOTHING rather than
>     everything: SQLite defines `LIMIT -1` as unlimited — the exact opposite of this method's
>     promise — so the bound is enforced here instead of trusted to every future caller.
>
>     `DELETE ... LIMIT` is NOT used — that syntax needs SQLITE_ENABLE_UPDATE_DELETE_LIMIT and is
>     not compiled into this build (verified: `near "LIMIT": syntax error`). The id-IN-subselect
>     form is core SQL and its inner select is index-served (verified: SEARCH login_event USING
>     COVERING INDEX login_event_lookup).
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
> Pass 1's regression test is kept verbatim (`test_a_negative_retention_limit_cannot_become_unbounded`,
> in `tests/test_login_capture.py` where `_record` and `_iso` live); measured failing on the repo
> tree (10 deleted) and passing with the guard (0 deleted, 10 retained). **DEBT-AVOIDED:** the seam
> contract is now code, not comment.

> **Fable:** AGREE — medium — `local-development/gsd/kube.py#_access_group_from_ldap_url` (K2 REFUTED
> stands; the replacement is correct and does not falsely reject real gates).
>
> Reproduced: `(memberOf==oops)` returns `'=oops'` on the repo tree — the poller stores it, no Group's
> `ldap.uid` can equal it, and the panel tells the reader the gate group is not synced on a cluster
> where the OAuth filter is merely odd. The proposed `_looks_like_dn` was the part needing adversarial
> attention, because its failure mode INVERTS the defect: a validator that rejects a real gate DN
> silently reports "no login gate is configured" — the same class of false statement K2 fixes. It was
> driven with a nine-case battery of directory-real shapes; no false rejection:
>
> ```text
> (memberOf==oops)                                             -> None   (the trigger, fixed)
> (memberOf=*)                                                 -> None   (stays rejected)
> cn=app-ssb-autobahnusers,ou=Groups,dc=ephico2real,dc=com     -> kept   (the reference cluster's gate)
> CN=Cluster Admins,OU=IT Groups,DC=corp,DC=example            -> kept   (AD, spaces in values)
> cn=Smith\, J,ou=x,dc=y                                       -> kept   (escaped comma)
> cn=a+ou=b,dc=y                                               -> kept   (multi-valued RDN)
> 0.9.2342.19200300.100.1.1=x,dc=y                             -> kept   (numeric OID attribute)
> percent-encoded filter, isMemberOf spelling, compound filter -> kept   (K2's confirmed behaviours retained)
> ```
>
> One deliberate strictness worth recording: a value with an UNESCAPED trailing space before a comma
> (`cn=gate ,dc=x`) is rejected — RFC 4514 requires the escape, some directories tolerate the
> violation, and an operator whose OAuth CR carries one will see "no gate known" until they either
> fix the filter or set `clusterAccess.group` explicitly, which is the documented degrade path.
> Acceptable; a warning log naming the rejected value would be the polish, not a blocker.
> **DEBT-INTRODUCED**, named: ~70 lines of RFC 4514 machinery guarding one discovery path — the
> validator is only as good as its own tests, and none of `_split_unescaped`, `_looks_like_dn` or
> the function had ANY test before this review (no test file imports them). Pass 1's single `==oops`
> test is necessary but nowhere near sufficient for code this shape-sensitive; the acceptance
> battery above must land WITH the validator. Complete test functions, including pass 1's, for the
> new `tests/test_kube_reader.py` proposed in the last NEW finding below:
>
> ```python
> def test_membership_value_with_an_empty_dn_attribute_is_rejected():
>     """`(memberOf==oops)` must not become a gate whose DN is `=oops` — the poller would store it,
>     nothing could ever match it, and the panel would claim the gate group is not synced."""
>     url = "ldaps://h/dc=x?uid?sub?(memberOf==oops)"
>     assert _access_group_from_ldap_url(url) is None
>
>
> @pytest.mark.parametrize("dn", [
>     pytest.param("cn=app-ssb-autobahnusers,ou=Groups,dc=ephico2real,dc=com", id="reference-gate"),
>     pytest.param("CN=Cluster Admins,OU=IT Groups,DC=corp,DC=example", id="ad-spaces"),
>     pytest.param("cn=Smith\\, J,ou=x,dc=y", id="escaped-comma"),
>     pytest.param("cn=a+ou=b,dc=y", id="multi-valued-rdn"),
>     pytest.param("0.9.2342.19200300.100.1.1=x,dc=y", id="numeric-oid"),
> ])
> def test_a_real_directory_dn_is_never_falsely_rejected(dn):
>     """The validator's failure mode INVERTS K2: rejecting a real gate reports 'no login gate is
>     configured' on a cluster that has one. Every shape here is legal RFC 4514 as a directory or an
>     admin actually writes it."""
>     assert _access_group_from_ldap_url(f"ldaps://h/dc=x?uid?sub?(memberOf={dn})") == dn
> ```

> **Fable:** AGREE — high — `local-development/gsd/store.py#Store.cluster_access_summary` (the NEW
> pagination-cap KPI is real; the fix is right and SHARES the predicate; one docstring must survive).
>
> Reproduced: 10,001 gate-only members → the repo tree's summary reports `login_without_access:
> 10000` while `gated_members: 10001` sits beside it in the same payload — a whole-set KPI that is
> secretly `len()` of a capped page, and the two numbers contradict each other on screen. With
> pass 1's replacement applied: 10,001. The arbiter's sixth worry is satisfied by construction —
> `_login_without_access_where` is one string used by the row query and the count, so this fix does
> not reintroduce the S3 class it sits next to. The protocol addition (`count_login_without_access`
> beside `count_access_without_login` in `local-development/gsd/storage.py#StorageBackend`) is
> right, and the 10,001-row regression test passes in ~11s on this machine — acceptable for what it
> pins. Ran the storage suites against the applied replacement: 116 passed, no collateral damage.
>
> ONE AMENDMENT: pass 1's `login_without_access` swaps a documented WHY for a one-liner. The shipped
> docstring explains what the quieter half of the panel is FOR (the newly onboarded, and the oauth
> BIND account surfacing as the gate group's eighth member) — that is the sentence that stops a
> future maintainer "simplifying" the panel away. Apply pass 1's code with the original docstring
> plus one line for the helper:
>
> ```python
> def login_without_access(self, cluster_id: str, limit: int = 200) -> list[dict]:
>     """People in the login-gate group who hold no access through any other synced group.
>
>     The quieter half, and not automatically a problem: somebody newly onboarded, or an account
>     that only ever needs to read something granted to `system:authenticated`. It is worth showing
>     because it is also how a service identity inside the gate group surfaces — on the reference
>     directory the group's eighth member is the oauth BIND account, which carries a `uid` and so
>     syncs like a person.
>
>     The WHERE comes from _login_without_access_where, shared with count_login_without_access so
>     the page and its whole-set count cannot disagree — the S3 lesson, applied before it recurs.
>     """
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
> ```
>
> The rest of the trio (`_login_without_access_where`, `count_login_without_access`,
> `cluster_access_summary`), the protocol line and the regression test: apply as pass 1 wrote them.
> **DEBT-AVOIDED:** the predicate is shared. **DEBT-INTRODUCED**, still open and now named twice:
> `access_without_login` / `count_access_without_login` remain the LAST copied row/count predicate
> pair in the file — pass 1 said "share it when it next changes"; I would share it in the same
> commit, because "next time" is when it will be forgotten.

> **Fable:** AGREE — low — `local-development/gsd/store.py#_migrate` (the NEW ordering finding is
> real; the fix is correct; add the list reorder it makes safe).
>
> Reproduced on a fresh scratch database: `user_version` lands at 5 while the highest migration is 6
> — migration 6 sits ABOVE migration 5 in `_MIGRATIONS`, and `_migrate` neither sorts nor refreshes
> its local `version`, so the first process applies 6 then 5 and stamps 5; the next restart replays
> 6 (harmless only because of `IF NOT EXISTS`) and stamps 6. With pass 1's `_migrate`: a fresh
> database lands at 6, and the migrations suite plus the replay-safety tests still pass. The sorted
> iteration plus `version = target` is the right fix — it removes the invariant instead of
> documenting it. Apply pass 1's `_migrate` and test verbatim; and since the sort makes source order
> purely cosmetic, ALSO swap the two tuples so migration 5 reads above migration 6 — the next person
> scanning the list should not have to discover the sort to trust it. **DEBT-AVOIDED** once applied:
> list layout can no longer control persisted schema state.

> **Fable:** FIX-INADEQUATE — high — `local-development/gsd/logincapture.py#capture_once` and
> `#_settle_horizon` (the quiet-pod NEW finding is real; the submitted replacement breaks two
> existing tests it never ran, carries a dead parameter, and misses the second defect in the same
> function).
>
> THE DEFECT, CONFIRMED: with a 30-day-old watermark and a log of ordinary timestamped lines and no
> verdicts, the repo tree leaves the watermark untouched — pass 1's regression test fails there
> exactly as claimed, and `sinceSeconds` therefore grows by one poll interval per cycle for the life
> of the pod. Raw-line-based cursoring is the right direction. But the replacement was never run
> against the suite it changes: `_settle_horizon` gains a REQUIRED second parameter while
> `tests/test_logincapture_loop.py#TestTheSettleHorizon` calls it with one argument in two tests —
> applied verbatim, the loop suite fails 2 of 34. The `attempts` parameter it keeps is also never
> read — a signature that lies about its inputs. And the same read path has a second, unhandled
> wrong-data defect (next finding) whose fix lands in the same two functions, so one corrected
> replacement below serves both.
>
> **Fable:** NEW — high — `local-development/gsd/logincapture.py#capture_once` records attempts
> whose lines are still arriving, and the dedup key cannot repair the result.
>
> Trigger, demonstrated with the loop's own fixtures: a read returns the provider-chain
> `failed for login "jane.smith"` line of a login whose success line has not yet been written (every
> cycle's read races the live tip; the measured gap inside one attempt is 30–125ms). `parse`
> honestly concludes `failed` from what it has; `capture_once` writes it immediately — the shipped
> test even pins this ("recording early and advancing late is the safe order"), on the stated
> premise that the re-read is harmless because of the dedup key. The premise is FALSE for exactly
> this case: the finished attempt concludes `success` with the same `at`, the UNIQUE key includes
> `outcome`, and both rows persist. Measured on the repo tree via a sliced-then-whole read pair:
>
> ```text
> login_events -> (jane.smith, success, 2026-08-08T05:13:10.026811Z, ldap-local)
>                 (jane.smith, failed,  2026-08-08T05:13:10.026811Z, developer)
> ```
>
> The reader sees a failed login that never happened, at the same instant as the success it was part
> of — for a break-glass account that row is an incident. The fix: record only attempts old enough
> that every line must have arrived — the same wall-clock horizon the watermark already uses, minus
> the attempt window — and let the overlap re-read deliver them whole one cycle later.
> `OVERLAP_SECONDS (60) > SETTLE_SECONDS (30) + ATTEMPT_WINDOW (1)` is the inequality that makes
> withholding safe, and the corrected `_settle_horizon` keeps the cursor at or behind the same
> horizon, so a withheld attempt can never fall out of the next window. Residual, accepted and
> documented in the code: a byte-cap boundary can still slice a SETTLED attempt (rare after the
> cursor fix; the cap message marks the cycle), and an attempt inside the final 31 seconds of a pod
> that is deleted before the next cycle is lost with its log — the same bargain first-sight already
> makes. The shipped pinning test is rewritten below with its premise corrected.
>
> Complete replacement — the changed import, `_settle_horizon`, the new `_recordable`, and the whole
> `capture_once`. `_prune`, `_seconds_since`, `_iso_days_ago` and `event_dict` are untouched:
>
> ```python
> from .loginlog import ATTEMPT_WINDOW, LoginAttempt, parse, parse_timestamp
> ```
>
> ```python
> def _settle_horizon(lines: list[str]) -> str | None:
>     """The newest log instant old enough to be called settled, or None if none is yet.
>
>     A READ CURSOR OVER LOG TIME, NOT OVER ATTEMPTS. The first shipped version took only parsed
>     attempts, which stalls on a pod that logs plenty and authenticates nobody: the watermark never
>     moves, sinceSeconds grows by the full poll interval every cycle for the life of the pod, and
>     once the window outgrows the byte cap the newest lines are deferred every cycle while capture
>     still stamps itself live. Any timestamped line proves the log was read through that instant,
>     so any timestamped line may advance the cursor — without inventing a login record.
>
>     RELATIVE TO NOW, not to the newest line in the batch — and that distinction is a bug I shipped
>     into the first draft. Measuring from the newest meant a BURST of logins inside SETTLE_SECONDS
>     made every one of them "unsettled" relative to its own peers, so the watermark never advanced
>     at all: the same window was re-read forever. Caught by the healthy-path test writing zero
>     watermarks. Measuring from now is what the horizon is actually for: a line stops being at risk
>     of belonging to a still-arriving attempt once wall-clock has moved past it.
>     """
>     from datetime import UTC, datetime
>     cutoff = datetime.now(UTC).timestamp() - SETTLE_SECONDS
>     stamps = [ts for raw in lines if (ts := parse_timestamp(raw)) is not None
>               and ts.timestamp() <= cutoff]
>     if not stamps:
>         return None
>     return max(stamps).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
>
>
> def _recordable(attempts: list[LoginAttempt]) -> list[LoginAttempt]:
>     """Only the attempts old enough that every one of their lines must already have arrived.
>
>     An attempt read MID-FLIGHT concludes on partial evidence: the provider-chain `failed` line is
>     in the read, the success that follows it is not yet written, and the parse honestly returns a
>     failure that never happened. The dedup key cannot collapse that with the finished attempt —
>     the outcome differs — so the sliced row would sit beside the real one forever, and the page
>     would show a failed login that is provider-order noise. Withholding an attempt until
>     wall-clock has passed its whole window costs at most one cycle of latency, and nothing is
>     lost: the watermark (same cutoff, minus the window) never advances past a withheld attempt,
>     and OVERLAP_SECONDS exceeds SETTLE_SECONDS plus the attempt window, so the next read has the
>     whole attempt again.
>     """
>     from datetime import UTC, datetime, timedelta
>     cutoff = datetime.now(UTC) - timedelta(seconds=SETTLE_SECONDS) - ATTEMPT_WINDOW
>     return [a for a in attempts if a.at <= cutoff]
> ```
>
> ```python
> def capture_once(
>     store: StorageBackend,
>     cluster: ClusterConfig,
>     settings: Settings,
>     elector=None,
>     timeout: float = 15.0,
> ) -> int:
>     """One capture pass over one cluster. Returns events recorded. NEVER raises for cluster problems.
>
>     ── THE LEADERSHIP RECHECK, AND WHY IT IS WHERE IT IS ─────────────────────────────────────────────
>     `poller.py` says of its lease, in its own words, that it is "BEST-EFFORT admission control, NOT a
>     write fence", and `_run_cluster` checks it once per cycle. That is fine for group polling and not
>     fine here, because this reads logs over the network: the check can pass, the read can block, the
>     lease can expire and pass to another replica, and the old leader's read can then return and write.
>     Codex named the sequence exactly — leader check true → log GET blocks → lease lost → new leader
>     starts → old GET returns → old leader records events and watermark.
>
>     So leadership is rechecked IMMEDIATELY BEFORE the write transaction, which narrows the window from
>     "the length of a log read" to "the few instructions between the check and the INSERT". It does not
>     close it, and this comment exists so nobody later mistakes it for a fence: closing it needs a
>     fencing token the lease does not provide. What makes the residual window tolerable is the dedup
>     key — two leaders writing the same lines produce the same rows, and INSERT OR IGNORE collapses
>     them. The watermark is the part that could regress, and `set_login_watermark` takes max() precisely
>     so a late write from a demoted leader cannot rewind it.
>     """
>     if not settings.login_capture_enabled:
>         return 0
>
>     ns = settings.login_capture_namespace
>     client = ClusterClient(cluster, timeout=timeout)
>
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
>
>     for pod in pods:
>         settled_through = watermarks.get(pod)
>         if settled_through is None:
>             since = FIRST_SIGHT_SECONDS
>         else:
>             # Seconds back from now to the watermark, plus the overlap. sinceSeconds is relative and
>             # coarse (whole seconds), which is exactly why the dedup key rather than arithmetic is what
>             # guarantees correctness here.
>             age = _seconds_since(settled_through)
>             since = max(OVERLAP_SECONDS, int(age) + OVERLAP_SECONDS) if age is not None \
>                 else FIRST_SIGHT_SECONDS
>
>         try:
>             lines = client.fetch_pod_log(ns, pod, since_seconds=since)
>         except ClusterError as exc:
>             # An AUTH_FAILED here is worth surfacing but must not stop the other pods.
>             log.warning("%s: login capture failed reading %s: %s", cluster.name, pod, exc.message)
>             continue
>         if lines is None:
>             continue                      # roll noise or a missing grant; both already logged
>         read_ok = True
>
>         attempts = _recordable(parse(lines))
>         horizon = _settle_horizon(lines)
>         if not attempts and horizon is None:
>             continue
>
>         observed_at = now_iso()
>         events = [event_dict(a, pod, observed_at) for a in attempts]
>
>         # THE RECHECK. Everything above is reads; everything below writes.
>         if elector is not None and not elector.is_leader:
>             log.info("%s: lost leadership while reading %s — discarding %d event(s) unwritten",
>                      cluster.name, pod, len(events))
>             return recorded
>
>         n = store.record_login_events(cluster.name, events) if events else 0
>         recorded += n
>         if horizon is not None:
>             store.set_login_watermark(cluster.name, pod, horizon, observed_at)
>         if n:
>             log.info("%s: recorded %d login attempt(s) from %s", cluster.name, n, pod)
>
>     # Forget read positions for pods that are gone. Every oauth roll replaces them, so without this
>     # the table grows by one row per pod name the cluster has ever had.
>     #
>     # Done on the strength of the POD LIST — which succeeded above, or we would have returned — and
>     # NOT gated on whether any read worked: a cluster whose log reads are all refused would otherwise
>     # keep every dead pod's position forever, which is the case most likely to accumulate them. It is
>     # also independent of `login_retention_days`, because this is a leak rather than a policy about
>     # how long to keep data; _prune's docstring claimed to do it and never did.
>     if elector is None or elector.is_leader:
>         dropped = store.prune_login_watermarks(cluster.name, pods)
>         if dropped:
>             log.info("%s: forgot %d stale read position(s) for pods that no longer exist",
>                      cluster.name, dropped)
>
>     if not read_ok:
>         # Not a single pod answered. Do NOT stamp a successful read: `started_at` would then claim we
>         # have been watching since a cycle that saw nothing, and `last_read_at` is the liveness signal
>         # that tells somebody capture has stopped.
>         return recorded
>
>     if elector is not None and not elector.is_leader:
>         return recorded
>     store.record_login_read(cluster.name, now_iso())
>
>     _prune(store, cluster, settings, elector)
>     return recorded
> ```
>
> Complete tests. Pass 1's quiet-pod test is KEPT (docstring widened); the shipped early-recording
> test and the two one-argument horizon tests are REWRITTEN — their subjects changed, and the
> replacements say why. All five live in `tests/test_logincapture_loop.py`; measured: five fail on
> the repo tree for the right reasons, 36 pass on the corrected tree, and the rest of the loop suite
> is untouched:
>
> ```python
>     def test_attempts_newer_than_the_horizon_are_withheld_not_written(
>             self, store, settings, install):
>         """A read can slice a live attempt mid-flight: the chain `failed` line has arrived, the
>         success that follows it has not. Concluded from partial lines it records a failure that
>         never happened, and the dedup key cannot collapse that with the finished attempt because
>         the outcome differs. So nothing inside the settle window is written yet — the watermark
>         holds behind it, and OVERLAP_SECONDS > SETTLE_SECONDS + ATTEMPT_WINDOW guarantees the next
>         cycle re-reads the whole attempt."""
>         install(FakeClient(logs={POD: _lines(datetime.now(UTC))}))
>         assert capture_once(store, CLUSTER, settings) == 0
>         assert store.login_events(CLUSTER.name) == []
>         assert store.login_watermarks(CLUSTER.name) == {}, (
>             "the position advanced past an attempt whose lines may still be arriving"
>         )
>
>     def test_a_sliced_read_cannot_record_a_failure_that_never_happened(
>             self, store, settings, install, monkeypatch):
>         """The regression the withholding exists for, end to end: first read ends between the
>         provider-chain `failed` line and the success; the next read has the whole attempt. One
>         person, one login, one row — never a failed row beside the success it belonged to."""
>         whole = _lines(datetime.now(UTC) - timedelta(seconds=2))
>         client = install(FakeClient(logs={POD: whole[:1]}))
>         capture_once(store, CLUSTER, settings)          # sliced: chain-failure line only
>         client._logs = {POD: whole}
>         monkeypatch.setattr(logincapture, "SETTLE_SECONDS", 0)   # the attempt ages past the window
>         capture_once(store, CLUSTER, settings)
>         rows = store.login_events(CLUSTER.name)
>         assert [(r["user_name"], r["outcome"]) for r in rows] == [
>             ("jane.smith", loginlog.OUTCOME_SUCCESS)
>         ], rows
>
>     def test_non_login_lines_advance_a_quiet_pods_watermark(self, store, settings, install):
>         """The cursor follows successfully read log time, not only business events.
>
>         A pod that logs plenty and authenticates nobody otherwise pins its watermark forever:
>         sinceSeconds grows by a poll interval per cycle for the life of the pod, and once the
>         window outgrows the byte cap the newest lines are deferred every cycle while capture
>         still stamps itself live."""
>         old = (datetime.now(UTC) - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
>         recent = datetime.now(UTC) - timedelta(seconds=SETTLE_SECONDS + 10)
>         stamp = recent.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
>         progress = f"{stamp} I0807 00:00:00.0 1 httplog.go:1] ordinary request"
>         store.set_login_watermark(CLUSTER.name, POD, old, "x")
>         install(FakeClient(logs={POD: [progress]}))
>         capture_once(store, CLUSTER, settings)
>         assert store.login_watermarks(CLUSTER.name)[POD] == stamp
>
>     def test_the_horizon_is_the_newest_settled_line(self):
>         """Any timestamped line proves the log was read through that instant, so any timestamped
>         line may advance the cursor — attempts are not required (the quiet-pod case), and a line
>         newer than the horizon may not (its attempt can still be arriving)."""
>         now = datetime.now(UTC)
>         def line(when):
>             return f"{when.strftime('%Y-%m-%dT%H:%M:%S.%fZ')} I0807 0:0:0.0 1 httplog.go:1] request"
>         settled = now - timedelta(seconds=SETTLE_SECONDS + 30)
>         horizon = logincapture._settle_horizon([
>             line(now - timedelta(seconds=SETTLE_SECONDS + 90)),
>             line(settled),
>             line(now),                                   # newer than the horizon
>         ])
>         assert horizon == settled.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
>
>     def test_no_settled_lines_means_no_horizon(self):
>         assert logincapture._settle_horizon([]) is None
>         now_line = (f"{datetime.now(UTC).strftime('%Y-%m-%dT%H:%M:%S.%fZ')} "
>                     "I0807 0:0:0.0 1 httplog.go:1] request")
>         assert logincapture._settle_horizon([now_line]) is None
> ```
>
> **DEBT-ACCEPTED**, restated from the code: up to one poll interval plus 31 seconds of recording
> latency, and the last-31-seconds-before-pod-deletion loss window — both are the price of never
> publishing a row the next read could contradict. **DEBT-AVOIDED:** the watermark and the recording
> gate share one clock and one inequality, asserted by the withheld test rather than by comment.

> **Fable:** DISAGREE with the fix, AGREE with the defect — high —
> `local-development/gsd/kube.py#ClusterClient.fetch_pod_log` (the comment lies; the submitted
> replacement converts a one-cycle delay into permanent, invisible data loss).
>
> WHAT IS ACTUALLY WRONG ON THE REPO TREE, measured with a mocked stream: the code keeps the OLDEST
> lines and stops at the cap — while its own log message says "the newest lines are kept" and its
> docstring says truncation "leaves the oldest of this window unparsed". Both statements describe
> the opposite of the behaviour. Two real defects ride along: the cap is counted in CHARACTERS of
> lines `iter_lines()` has already assembled (a 20-byte cap retained 31 bytes of multi-byte text,
> and a single line larger than the cap is buffered whole before it can be measured), and K1's
> confirmation upstream leans on the false comment.
>
> WHY THE DIRECTION MUST NOT CHANGE: keeping the oldest is not the bug — it is load-bearing. The
> watermark only ever advances through lines the read RETURNED, so oldest-first truncation defers
> the newest lines into the next cycle's window and the record stays complete, merely late. Pass 1's
> rolling tail advances the cursor past everything the cap displaced. Two-cycle simulation, real
> `capture_once` and real store on both trees, three attempts (50 min, 40 min, 2 min old), cap sized
> to two attempts:
>
> ```text
> shipped direction: cycle 1 -> alice,bob   cycle 2 -> alice,bob,carol      (complete, carol one cycle late)
> pass 1 direction:  cycle 1 -> bob,carol   cycle 2 -> bob,carol            (alice UNRECOVERABLE)
> ```
>
> After pass 1's version, the watermark sits past alice forever, `record_login_read` stamps the
> cycle green, and the dashboard reader believes alice never signed in — the exact false statement
> this feature exists to prevent, introduced by a fix. The replacement also violates the arbiter's
> stated worry in its own terms: it consumes the ENTIRE stream on every cap hit (its own regression
> test asserts full consumption), paying transfer for bytes it then throws away; and its
> drop-to-first-newline trim returns `[]` for a stream whose first line was complete and parseable
> (measured: `whole-line\n` + one oversized line, cap 30 → `[]`). Pass 1's regression test
> `test_log_cap_retains_the_tail_without_buffering_the_whole_response` pins the wrong contract and
> MUST NOT be applied.
>
> Complete replacement — byte-true bound, transfer stopped at the cap, direction kept and finally
> documented, the cut line withheld for the next cycle's overlap:
>
> ```python
>     def fetch_pod_log(
>         self,
>         namespace: str,
>         pod_name: str,
>         since_seconds: int | None = None,
>         max_bytes: int = 8 * 1024 * 1024,
>     ) -> list[str] | None:
>         """Timestamped log lines for one pod, or None when this pod cannot be read right now.
>
>         NOT THROUGH `_get()`, and that is mandatory rather than stylistic: `_get` always calls
>         `response.json()`, and this endpoint returns TEXT. `_client()` IS used — it only supplies the
>         bearer token and CA verification, which this needs exactly as much as any other call.
>
>         STREAMED, AND BYTE-BOUNDED — in BYTES, counted before any line is assembled. The previous
>         draft counted characters of lines `iter_lines()` had already buffered whole, so a single
>         line larger than the cap was held in memory before it could be measured, and a multi-byte
>         log undercounted. Stopping at the cap also ends the transfer instead of paying for lines
>         that would be discarded.
>
>         A CAP HIT KEEPS THE OLDEST LINES OF THE WINDOW, deliberately. The kubelet streams oldest
>         first, and oldest-first is the direction the watermark machinery REQUIRES: the cursor only
>         advances through lines actually returned, so the deferred newest lines fall inside the next
>         cycle's window and nothing is lost — only late. Keeping the newest instead would let the
>         cursor advance past everything the cap displaced and silently drop it forever; recency is
>         what the next cycle gets back anyway, completeness is not. (An earlier comment here claimed
>         the newest lines were kept; it described the opposite of what the code did.) The line the
>         cap cuts in half is dropped for the same reason: a truncated diagnostic can mis-parse — a
>         bind error losing its `data` sub-code reads as a plain wrong password — and the whole line
>         is inside the next cycle's overlap.
>
>         `timestamps=true` is what makes the result usable at all — it prefixes each line with the
>         kubelet's RFC3339 UTC stamp. klog's own stamp carries no year and no timezone.
>
>         RETURNS None FOR THE ORDINARY ROLL, RAISES FOR THE REST, and the distinction is the point:
>
>           404              the pod went away between listing and reading. Every roll does this.
>           400 not-ready    the container has not started, so there is no log yet. Measured message:
>                            "container nope is not valid for pod ..." — reason BadRequest.
>           403              the grant is missing. LOGGED AT WARNING, because it is permanent and will
>                            not fix itself, and a silent None here looks identical to "nobody logged
>                            in" forever.
>           any other        raised, so a real outage is not mistaken for roll noise.
>         """
>         params: dict[str, Any] = {"timestamps": "true"}
>         if since_seconds is not None:
>             params["sinceSeconds"] = str(since_seconds)
>         path = f"{POD_API_TMPL % namespace}/{pod_name}/log"
>
>         chunks: list[bytes] = []
>         size = 0
>         truncated = False
>         try:
>             with self._client() as client:
>                 with client.stream("GET", path, params=params) as response:
>                     if response.status_code >= 400:
>                         response.read()
>                         return self._log_read_refused(response, namespace, pod_name)
>                     for chunk in response.iter_bytes(chunk_size=min(64 * 1024, max(1, max_bytes))):
>                         room = max_bytes - size
>                         if len(chunk) >= room:
>                             chunks.append(chunk[:room])
>                             size = max_bytes
>                             truncated = True
>                             break
>                         chunks.append(chunk)
>                         size += len(chunk)
>         except httpx.HTTPError as exc:
>             # A connect error or timeout reading ONE pod must not fail the cycle: the other pods still
>             # have lines, and this one is retried next time from the same watermark.
>             log.info("%s: could not read %s log (%s: %s)",
>                      self.cluster.name, pod_name, type(exc).__name__, exc)
>             return None
>
>         # errors="replace" cannot corrupt a kept line: the only place a multi-byte character can be
>         # split is the cap boundary, and the line holding it is popped below.
>         lines = b"".join(chunks).decode("utf-8", errors="replace").splitlines()
>         if truncated:
>             if lines:
>                 lines.pop()
>             log.info(
>                 "%s: %s log hit the %d-byte cap after %d lines; the OLDEST lines of this window "
>                 "are kept, and the rest fall inside the next cycle's window once the watermark "
>                 "has advanced",
>                 self.cluster.name, pod_name, max_bytes, len(lines),
>             )
>         return lines
> ```
>
> Complete tests — these are the first unit tests this function has ever had (nothing under `tests/`
> imports it; the loop suite substitutes a fake client). Measured: the repo tree fails the first two
> (31 bytes kept of a 20-byte cap; the message claims the newest are kept), pass 1's tree fails the
> last two (returns the newest and consumes the whole stream; returns `[]` past a complete line),
> the corrected tree passes all three:
>
> ```python
> class Chunks(httpx.SyncByteStream):
>     def __init__(self, values):
>         self.values = values
>         self.yielded = 0
>
>     def __iter__(self):
>         for value in self.values:
>             self.yielded += 1
>             yield value
>
>
> def _client_for(monkeypatch, stream):
>     cluster = ClusterConfig("c", "https://api.example", token_env="X")
>     transport = httpx.MockTransport(
>         lambda request: httpx.Response(200, stream=stream, request=request))
>     client = ClusterClient(cluster)
>     monkeypatch.setattr(
>         client, "_client",
>         lambda: httpx.Client(transport=transport, base_url="https://api.example"))
>     return client
>
>
> def test_the_byte_cap_is_measured_in_bytes_not_line_characters(monkeypatch):
>     """A multi-byte log must not blow through the cap: max_bytes is a MEMORY bound, and a
>     character count taken after the line was already assembled is neither."""
>     stream = Chunks([("€" * 10 + "\n").encode(), b"x\n"])       # 31 bytes, 11 characters
>     client = _client_for(monkeypatch, stream)
>     got = client.fetch_pod_log("ns", "pod", max_bytes=20)
>     assert got is not None
>     assert sum(len(line.encode()) for line in got) <= 20, got
>
>
> def test_a_cap_hit_keeps_the_oldest_lines_and_stops_the_transfer(monkeypatch, caplog):
>     """The watermark machinery REQUIRES oldest-first retention: the cursor only advances through
>     returned lines, so the deferred newest fall inside the next window and are late, not lost.
>     Keeping the newest would advance the cursor past the displaced middle and silently drop it
>     forever — and reading on after the cap pays for bytes that are then thrown away."""
>     stream = Chunks([b"oldest-1\n", b"oldest-2\n", b"newest-3\n", b"newest-4\n"])
>     client = _client_for(monkeypatch, stream)
>     with caplog.at_level(logging.INFO):
>         got = client.fetch_pod_log("ns", "pod", max_bytes=20)
>     assert got == ["oldest-1", "oldest-2"], got
>     assert stream.yielded < 4, "the read continued past the cap"
>     assert "OLDEST lines of this window are kept" in caplog.text
>
>
> def test_the_line_the_cap_cuts_in_half_is_dropped_not_parsed(monkeypatch):
>     """A truncated line can mis-parse — a bind diagnostic losing its `data` sub-code reads as a
>     plain wrong password — so the cut line waits for the next cycle's overlap instead."""
>     stream = Chunks([b"whole-line\n" + b"cut-here-" * 10])
>     client = _client_for(monkeypatch, stream)
>     got = client.fetch_pod_log("ns", "pod", max_bytes=30)
>     assert got == ["whole-line"], got
> ```
>
> **DEBT-AVOIDED:** the truncation contract is now enforced by tests on the real HTTP path instead
> of asserted by a comment that said the opposite. **DEBT-ACCEPTED**, named: under PERSISTENT
> overflow — a pod writing more than the cap per cycle indefinitely — the oldest-first cursor lags
> reality without bound; the cap log line marks every such cycle, and the honest escalation is a
> bigger cap or a shorter poll interval, not a direction change that trades the backlog for silent
> holes.

### The six regressions the arbiter named, answered

> **Fable:** 1. SINGLE-PROVIDER ORPHAN — preserved. The corrected `parse` keeps the orphan path as a
> list with an adjacency fallback; the two shipped orphan tests (`tests/test_loginlog.py`, browser
> wrong-password and cause-before-any-username) pass unchanged on the corrected tree.
> 2. ACTIVE DIRECTORY — real, exactly as feared. Pass 1's gate loses every AD bind cause in both the
> multi-provider and orphan shapes (measured: `password_expired`→`failed`, `account_locked`→`failed`)
> while all 36 OpenLDAP-shaped tests stay green. Fixed by attributing binds through the measured
> `found dn=` line, whose filter carries the login on every directory; the AD test above is the pin.
> 3. EXACT MATCHING — verified: pass 1's boundary regex rejects `uid=bob`→`bobby` in both directions;
> the same primitive is kept in the corrected parse and pinned by its own test.
> 4. WATERMARK PAST AN UNSETTLED ATTEMPT — cannot happen in the corrected composite, by inequality:
> the cursor never exceeds now − SETTLE_SECONDS, recording stops a further ATTEMPT_WINDOW behind it,
> and the next window reaches OVERLAP_SECONDS (60) behind a watermark that is at most 31 seconds
> ahead of any withheld attempt. The withheld test asserts the visible half; the burst and healthy
> path tests still pass, so the L3 fix is not regressed.
> 5. WHOLE-LOG BUFFERING — pass 1's rolling deque does bound MEMORY, but it consumes the entire
> transfer on every capped read (its own test asserts full consumption) — the cost the bound exists
> to avoid, paid on the network instead of in RAM. The corrected version stops both at the cap.
> 6. SHARED PREDICATE — satisfied: the summary fix routes both the page and the count through
> `_login_without_access_where`. The one remaining copied pair in the file is named under S4's debt.

### New findings (secondary, as briefed)

> **Fable:** NEW — low — `local-development/tests/test_docs_citations.py#REVIEW_ARTIFACTS`.
>
> Trigger: run the mandatory suite command on this branch as it stands. Result: `1 failed` —
> `test_no_citation_uses_a_line_number` lists ten offenders, every one a `file:NNN` citation inside
> THIS review document, written by pass 1 (whose own method section demanded "file:line or
> file#symbol"). Consequence: the suite is red on the PR branch for a documentation-format reason,
> and a reader of the pipeline believes the login-capture code is failing tests when no product test
> fails. The suite already owns the answer: review documents are point-in-time artifacts, exempted
> BY NAME because "rewriting those to symbol names as the code changes would falsify the record of
> what was reviewed" — the tuple simply predates this file. Complete replacement:
>
> ```python
> REVIEW_ARTIFACTS = (
>     "OAUTH_LOGLEVEL_REVIEW.md",
>     "REVIEW_login_capture_pr12.md",
> )
> ```
>
> The failing test is its own regression test: red before, green after, and the tuple's comment
> already documents why. **DEBT-AVOIDED:** the alternative — rewriting pass 1's citations to symbol
> form — would edit another reviewer's findings, which this process forbids for good reason.
>
> **Fable:** NEW — low — `local-development/gsd/kube.py#_access_group_from_ldap_url` and
> `#ClusterClient.fetch_pod_log` have no test home: NOTHING under `tests/` imports either (verified
> by grep across the suite; the loop tests substitute `FakeClient`). Consequence: every K-area
> regression test in this review has nowhere to land, which is how the K1 comment lie survived — the
> only "test" of the truncation contract was the comment itself. Fix: create
> `tests/test_kube_reader.py` holding the three `fetch_pod_log` tests and the two
> `_access_group_from_ldap_url` tests above, with this header:
>
> ```python
> """The cluster reader's pure seams: the log truncation contract and the OAuth-filter DN parse.
>
> These are the first direct tests of kube.py's reader helpers. The capture-loop suite deliberately
> fakes the client, which is right for loop semantics and useless for the contracts the fakes
> assume — the byte cap's direction was documented backwards for a full release because nothing
> executed the real path. HTTP is mocked at the transport, so no cluster is needed.
> """
> from __future__ import annotations
>
> import logging
>
> import httpx
> import pytest
>
> from gsd.config import ClusterConfig
> from gsd.kube import ClusterClient, _access_group_from_ldap_url
> ```
>
> **DEBT-INTRODUCED** by the PR (now partially repaid): a reader module whose contracts were
> comment-only. The remaining unexercised seam is `fetch_access_group_dn`'s 404-path anchoring (K3)
> — confirmed by pass 1 with scratch probes, still without a committed test; port those probes into
> the same file when it lands.

### Whole-PR debt judgement, second opinion

> **Fable:** Concur with pass 1's ledger, with three amendments. (1) The heaviest DEBT-INTRODUCED
> item is not on its list: the correctness of cause attribution and of capture recording rested on
> UNSTATED distribution assumptions — "the DN contains the login" and "a read never splits an
> attempt" — that held on this lab and fail on Active Directory and under ordinary timing,
> respectively. Both are now explicit code paths with tests, which is the only durable repayment.
> (2) Its outcome-vocabulary invariant test is worth applying as written — it passes today and is
> the cheapest insurance in the whole review — but note it pins `OUTCOME_LABEL`/`OUTCOME_BADGE`
> key-completeness only; wording drift remains human. (3) The `docs/examples` agreement gap it
> names is real but belongs to the platform-chart repo's CI, not this one; recording it here and
> fixing it there is the right split. **DEBT-ACCEPTED**, jointly: best-effort leases without
> fencing, byte-identical occurrence collapse, first-sight history loss, and now the 31-second
> recording latency — each is documented in code beside the decision it prices.

### Verdict

> **Fable:** This PR is SAFE TO MERGE once the surviving fixes are applied — with the explicit
> caveat that two of pass 1's nine proposed remedies must NOT be applied as written, because each
> would ship a silent feature-deletion the suite cannot see: the `parse` identity gate erases the
> Active Directory sub-code feature (the corrected replacement above keeps its intent and the AD
> contract), and the `fetch_pod_log` tail-retention erases displaced log history permanently (the
> corrected replacement keeps the byte-bound fix and the truthful message). Apply as written from
> pass 1: `_VERDICT`'s anchor (with the preserved comment block), the S5 guard (merged docstring),
> the K2 validator plus acceptance battery, the summary trio (restored docstring), `_migrate`, the
> protocol line, and the quiet-pod test; apply from this pass: the corrected `parse`,
> `capture_once`/`_settle_horizon`/`_recordable`, `fetch_pod_log`, the five loop-test rewrites, the
> parser battery, `tests/test_kube_reader.py`, and the one-line `REVIEW_ARTIFACTS` fix. The measured
> end state of exactly that composite is 1072 passed, 1 skipped, plus the one failure this document
> itself causes — pass 1's citation format — which the tuple removes (rescanned every repo markdown
> with the extended tuple: zero offenders). FIX FIRST: the parse attribution rewrite — it is the only finding where wrong
> data is shown as fact about a NAMED PERSON, both the shipped code and the proposed fix get it
> wrong in different ways, and every day it waits is a day the lab's OpenLDAP shape keeps certifying
> a parser that Active Directory would quietly break.

---

## Arbitration

**CLOSED.** Every finding from both passes is ruled on below. Nothing was applied on either agent's
word: each ruling was reproduced first on a scratch package tree — never the repo — and only then
ported. Final state: **1039 passed, 1 skipped, 0 failed**, and the parser is byte-identical to the
shipped one on the real 33-attempt cluster log.

### What was applied

| # | finding | ruling | reproduced by the arbiter as |
|---|---|---|---|
| 1 | `_VERDICT` matched the phrase anywhere in a line | **Codex's anchor** | a quoted verdict inside an `audit.go` message produced an attempt; anchored, 0 |
| 2 | a cause attached to the wrong person | **Fable's `parse`** | AD `data 532`/`775` survive; alice keeps code 49 and bob is given nothing; `uid=bobby` is not `bob` |
| 3 | `prune_login_events` unbounded on a negative cap | **Codex's fix**, Fable's docstring | `max_rows=-1` deleted 10 rows; now 0, normal call still 10 |
| 4 | migrations applied out of order, wrong `user_version` | **Codex's sorted `_migrate`** + Fable's reorder | fresh database stamped 5 with 6 as the highest; now 6. Source order was `[1,2,3,4,6,5]` |
| 5 | a whole-set KPI computed from a pagination cap | **Codex's scalar count** | 10,001 gate-only members reported as exactly 10,000; now 10,001 |
| 6 | the DN validator accepted a non-DN | **Codex's `_looks_like_dn`** | `(memberOf==oops)` returned `'=oops'`; now `None`, with the live URL, `isMemberOf`, an AD DN with spaces and percent-encoding all still accepted |
| 7 | a quiet pod froze the read cursor | **Fable's composite** | a 30-day-old watermark stayed 30 days old; now advances to 2 minutes |
| 8 | a phantom `failed` row beside the real success | **Fable's `_recordable`** | two rows at the same microsecond, `(jane.smith, failed)` and `(jane.smith, success)`; now the mid-flight attempt is withheld and recorded whole one cycle later |
| 9 | the byte cap kept the wrong end, and the comment said the opposite | **Fable's reader** | see the rejection below |
| 10 | this review document broke the suite | **Fable's one-liner** | `test_no_citation_uses_a_line_number` failed on pass 1's own markers |
| 11 | the reader's seams had no direct tests | **Fable's `test_kube_reader.py`** | — |

### What was rejected, and the evidence that contradicted it

**Codex's `_cause_mentions_user` gate (finding 2).** It requires the cause's own text to name the
login. On Active Directory the DN is `CN=Jane Smith,OU=…` and the login is `jsmith`, so the two can
never match: every AD cause degrades to a bare `failed` and the whole sub-code map — 532 expired, 773
must-change, 775 locked — becomes dead code on the one directory family it exists for. Confirmed on my
own tree, and confirmed as INVISIBLE: `tests/test_loginlog.py#TestActiveDirectorySubCodes` synthesises
its AD diagnostics onto the OpenLDAP fixture DN `uid=jane.smith`, so the gate matches in every test and
fails only in production. All 36 stay green either way. Fable's replacement attributes a bind error via
the `found dn="…" for (<filter>)` line instead, because the filter embeds the typed login on every
directory — verified against the live cluster's own log line.

**Codex's `fetch_pod_log` rolling tail (finding 9).** The defect is real: the code keeps the OLDEST
lines while its log message claims the newest are kept. But the DIRECTION is load-bearing, because the
cursor only ever advances through lines the read RETURNED — so oldest-first truncation defers the newest
into the next window and the record stays complete, merely late. My own two-cycle simulation, three
attempts and a cap sized for two:

```text
keep OLDEST  cycle 1 -> alice, bob      cycle 2 -> alice, bob, carol     (complete)
keep NEWEST  cycle 1 -> bob, carol      cycle 2 -> bob, carol            (alice LOST FOREVER)
```

Keeping the newest advances the cursor past what the cap displaced, `record_login_read` stamps the cycle
green, and the reader believes alice never signed in — a fix introducing the exact false statement this
feature exists to prevent. Fable's version keeps the direction, makes the bound byte-true (the shipped
one retained 31 bytes of a 20-byte cap because it counted characters), stops the transfer at the cap
rather than consuming the whole stream, and corrects the comment. Verified: 33 bytes under a 40-byte
cap, oldest kept, 40 of 99 bytes transferred, and a complete first line survives an oversized second.

**Two of Codex's tests, because they pin the wrong contract.**
`test_orphan_cause_must_name_the_verdict_user` encodes the AD-deleting rule above.
`test_log_cap_retains_the_tail_without_buffering_the_whole_response` asserts the direction that loses
data, and asserts full stream consumption as a feature.

### Nothing was deferred

Every finding is closed. The debt both passes named as ACCEPTED is unchanged and already documented in
the code it belongs to: two indistinguishable log occurrences cannot be separated without an upstream
id; the leader lease is best-effort without a fencing token; first-sight and retention deliberately
bound history; a login containing LDAP-filter metacharacters loses its cause attribution and degrades
to an honest bare outcome.

### Mistakes the arbiter made, recorded because they nearly landed

Five, all of them mine, all caught by verifying rather than by reading the edit back. A script that died
before `write_text`, so the P1 anchor silently never applied — found only because a probe still returned
1 attempt where it needed 0. A helper that replaced up to "the next `def`" and swallowed the
`_PRAGMA_WORDS` constant between two functions. The document's fenced methods sitting at column 0, so
three "methods" spliced in as module-level functions and vanished off `Store`. Deleting
`_ACCESS_GROUP_CLAUSE`, which Codex's block assumes survives. And an assert that tested for a NAME
rather than a DEFINITION, so a restore silently no-opped. None reached the repository; the audit below
is what proves it.

### The audit run before committing

- **Zero definitions lost.** Every module-level name and every method compared against `HEAD` by AST
  across all five changed modules: 0 missing, and every addition accounted for.
- **Comments and docstrings net +15 and +11.** One file lost three comment lines — `logincapture.py` —
  and they are exactly the false premise that documented finding 8 as safe: *"the next cycle re-reads
  them harmlessly because of the dedup key. Recording early and advancing late is the safe order."*
  Its replacement states the corrected reasoning and cites the inequality that makes withholding safe.
- **Every module imports; no Protocol method is missing from `Store`; no conflict markers.**
- **The app boots** and all nine endpoints answer 200, with `refusal_reason` resolving as designed
  (`not_gated` for a known person, `no_record` for an unknown name, `None` for outcomes that were never
  ambiguous).
- **The real 33-attempt cluster log parses identically** to the shipped code.
