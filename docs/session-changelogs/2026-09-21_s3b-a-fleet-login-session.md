# Session change log — group-sync-dashboard, 2026-09-21 (OB1: #283, the fleet login session)

What this session did, when, and how each claim was measured. Times are git author times in
America/Chicago. Every "measured" claim below is one the session ran a command for; nothing here is
recalled from memory alone. The product changelog (`docs/CHANGELOG.md`) says what each release
changed for an operator; this says what a working session did. The session is OB1's implementation of
issue #283 under the S3b programme board (#288), spec-first from `docs/specs/SPEC_S4a_fleet_login_session.md`.

Outcome in one line: **pending**

| | Before the session | After |
|---|---|---|
| main | `0cf1030` (#287 merged: SPEC_S4 on main) | pending |
| chart / app | 0.49.0 / 0.30.0 | pending |
| #283 | open, no branch; the issue's precondition section superseded by SPEC_S4 §10.1 | pending |
| open PRs | none | pending |
| the lab (CRC) | `developer` / `openshift-challenging-client` OAuthAccessToken count: 0 | pending |

---

## Part 1 — #283: the login session, spec first (2026-09-21)

### The spec, the module and the proof (16:0x → 17:37) — commit `aefe7aa`, PR #289

- Read in full before writing anything: issue #283, board #288, `docs/specs/SPEC_S4_token_retrieval.md`
  (all 304 lines; §3, §3.1, §5, §6, §8, §9 binding), `docs/specs/SPEC_S3_connection_modes.md`,
  `gsd/auditlog.py`, `gsd/kube.py#ClusterError`, `gsd/clusterconfig/events.py`, `gsd/poller.py#_log_poll_failure`,
  `charts/group-sync-dashboard/templates/fleet-account-rbac.yaml`.
- **Measured** the mechanism on CRC with the htpasswd `developer` account (`oc get user developer` →
  identity `developer:developer`; provider `developer:HTPasswd`), never the LDAP fleet account: discovery
  document names `https://oauth-openshift.apps-crc.testing/oauth/authorize`; the login answers **302,
  0-byte body**, fragment keys `access_token, expires_in, scope, token_type`, `expires_in=31536000`;
  the derived object name matched the server's (`userName=developer`, `expiresIn=31536000`); `DELETE
  useroauthaccesstokens/<name>` as the token's own user → **200**; 0.51 s end to end.
- **Found by the measurement, mine:** the CSRF probe (no `X-CSRF-Token`) answered 302 and minted a
  second token I had not captured — SPEC_S4 §6's "returns 401" did not reproduce. Revoked it as
  cluster-admin (`oc delete oauthaccesstoken sha256~00H6…`); count for `developer`/challenging-client
  back to **0** before any further work. Recorded in the spec's notes.
- Wrote `docs/specs/SPEC_S4a_fleet_login_session.md` with every change as a fenced block, then applied
  it with a script that writes whole-file blocks verbatim and refuses an edit whose Old text does not
  match exactly once. **Three deviations, all recorded in the spec with the reason:** the CHANGELOG
  Old text quoted a one-line bullet as two lines (refused by the script, corrected to anchor on the
  heading); two test assertions grepped prose (`gave_up` in an `action=` sentence, `sched` in the
  docstring) and were rewritten as field-syntax and AST assertions. The module's Python block applied
  verbatim on the first pass and was not changed.
- `tests/test_fleet_login.py`: **5 failed / 39 passed** on the first run (the two prose greps), **44
  passed** after the spec correction. Mutation check: refusal made `retryable=True` → 2 tests fail;
  revoke removed from `__exit__` → 6 tests fail.
- **Found by the live run, mine:** the first live test asserted a 401 on the first request after the
  session closed; CRC answered **200**. Re-measured once a second: the object was absent from
  `oc get oauthaccesstokens` at once (count **0 → 1 → 0**, the name present during and gone after) and
  the revoked token authenticated for **121 s** before 401 — the API server's token authenticator
  cache. Spec §2, the `_revoke` docstring and the live test corrected (it waits for the death, up to
  `GSD_LIVE_LOGIN_DEAD_WAIT`); second live run **1 passed in 121.00 s**, manual count 0 before / 0 after.
- Full hermetic suite on the head: **4622 passed, 16 skipped, 563 deselected in 227.98 s** (baseline
  on `a94e6c1` before #287's index row: 4566 passed, 2 failed — both `test_specs_index.py`, fixed by #287).
- `docs/specs/README.md` row `S4a`, `test_specs_index.py` id pattern `[A-Z]\d[a-z]?` and count 20,
  `docs/CHANGELOG.md` Unreleased entry. No chart change, no version bump.
- Review: pending (Codex + OB seats per #288's loop; Cursor cannot execute, measured by the orchestrator).

### The review's six findings (18:2x → 18:17) — commit `d6e5759`, PR #289

- Three seats (Codex gpt-5.6-sol xhigh, Cursor Grok 4.6, OB1-lite) reviewed head `aefe7aa`; C1/C3/C5/C8/C9
  **CONFIRMED** by all three; six findings, each decided by the business owner and recorded in
  `docs/REVIEW_S4a.md`. Every fix was written into `docs/specs/SPEC_S4a_fleet_login_session.md`'s blocks
  first (its notes carry the deviations and the inverted tests) and the files regenerated from the spec.
- **Found by all three, accepted:** a remote-controlled `expires_in` overflowed the instant arithmetic and
  the minted token was abandoned (Codex measured `authorize_count 1 delete_count 0`); bounded at int32
  and guarded by a `BaseException` revoke — both halves. **Found by all three, the strict rule accepted,
  OB1-lite's narrower retry set rejected:** every answer after the password is on the wire is terminal;
  only `ConnectError`/`ConnectTimeout` retry (upstream: 401 only for LDAP codes 48/49, 500 for all else,
  a locked account's code 19 included). **Found by Codex alone, accepted:** a 401 on the revoke is not
  "already gone". **Found by all three, accepted:** three raise sites left `str(exc)` unscrubbed. **Found
  by Cursor and OB1-lite, accepted:** the name test was circular — pinned to the `openssl` literal (re-run
  by OB1: `AVSmBSfwHu_fqo50RnV0Ghp9zEjQrjfPXEV7qa7DuJY`, identical). **Found by Codex, accepted:** a
  non-UTC injected clock.
- The corrected `tests/test_fleet_login.py` against the PREVIOUS module (the new constant shimmed in so
  it imports): **18 failed / 40 passed**; against this head: **58 passed**. Four tests inverted because
  they asserted the defect (named in the spec's notes and the review record).
- Full hermetic suite on this head: **4641 passed, 16 skipped, 563 deselected in 227.21 s**. Doc checks
  over the review record: 1065 passed.
- Live on CRC as `developer` after the fix: count **0 → 1 → 0**, the session's name present during and
  gone after, the revoked token dead after **121 s**; manual `oc` count 0 before / 0 after.

### The confirmation pass's seven findings (19:0x → 19:03) — commits `00f862e` (merge of main), `1bded21`, PR #289

- `origin/main` merged in first (#290, SPEC_S4 §9's renewal formula) so CI runs on a current head.
- Codex (harness) and Cursor (reading) on `28d4bec`: **not mergeable**, seven residual defects, one
  introduced by P1-2; Codex's measured result wins where they disagree. All seven **accepted**,
  written into the spec's blocks first, recorded in `docs/REVIEW_S4a.md`'s "Confirmation pass".
- **Found while applying R2-1, mine (measured):** the first test's hostile `Location`
  (`https://[::1/…`) was refused by httpx itself — `RemoteProtocolError` from
  `_send_handling_redirects`, which builds the redirect request even with `follow_redirects=False` —
  so the 302 never reached the module. The measured case Codex hit is `https://example.com]/…`:
  delivered as a 302, `urlsplit` raises. The test uses that; the limit (a token this process never
  sees) is recorded in the module docstring beside the read timeout.
- The invariant **restated** at the owner's instruction: revocation is attempted exactly once and a
  failure is surfaced, never swallowed; `FleetLogin.revoked` carries the answer. Nothing shared
  (`events.redact`, `kube.redact_text`) changed.
- The corrected `tests/test_fleet_login.py` against the previous module: **10 failed / 54 passed**
  (the `Basic` case reproduced Codex's `unreachable`); against this head: **64 passed**.
- Full hermetic suite: **4648 passed, 16 skipped, 563 deselected in 230.06 s**. Doc checks: 990 passed.
- Live on CRC as `developer`: count **0 → 1 → 0**, name present during and gone after, the revoked
  token dead after **121 s**; manual `oc` count 0 before / 0 after.

### The split the lab cannot show (19:5x → 19:25) — commit `06494b5`, PR #289

- **Found by both reviewers as a plausible risk, measured by the operator as a lab blind spot,
  accepted:** CRC's `kube-root-ca.crt` carries the ingress leaf and CA among its six certificates, so
  the API-CA/ingress-CA split cannot occur on the reference cluster. Re-measured from the poller SA's
  bundle with `openssl x509 -noout -subject`: six subjects, `c4 CN=*.apps-crc.testing`,
  `c5 CN=ingress-operator@1785325954`. Recorded in the spec's §2.1 and `docs/REVIEW_S4a.md`.
- `TestTheSplitCATheLabCannotShow`: two CAs generated per test with OpenSSL 3.6.4 (config-file
  extensions; measured before writing the block: A-only bundle → `unable to get local issuer
  certificate`, A+B → 200), two loopback TLS servers, the owner's five assertions in order, plus the
  both-CAs control (one `Basic` header, terminal 302). Both **ran, not skipped** (2 passed in 2.90 s).
- Full hermetic suite: **4650 passed, 16 skipped, 563 deselected in 231.70 s**. Doc checks: 990 passed.
- Nothing of #284's configuration contract implemented; `cryptography` not added (not a dependency).

### The third pass, and the split-CA proof made unskippable in CI (20:2x → 19:48) — commit `f2c221f`, PR #289

- **The CI-skip change (the operator):** a `-q` CI log could not show whether the split-CA pair ran;
  the counts (local 4650/16, CI 4652/13) reconciled under both hypotheses. Matched the suite's existing
  convention (`test_chart_grafana_dashboard.py`: `pytest.fail` under `CI`, `pytest.skip` otherwise)
  rather than a new marker. Proven locally in both directions: `PATH=/nonexistent` with `CI` unset →
  2 skipped; with `CI=true` → `Failed: … must never be skipped here`. Measured from the CI logs: on
  `28d4bec` (before the pair) **4643 passed, 13 skipped**; on `0169ce7` (with it) **4652 passed, 13
  skipped** — the skipped count did not move across two skippable tests, so they were running.
- **Third Codex pass, four findings, all accepted; R3-3 is a reversal of the operator's own round-2
  decision, recorded as such.** The guard is now anchored on the response (`_token_in` re-read on
  failure) instead of on a binding that three refactors moved; `revoked` is the target's answer from
  every site; redaction is scoped by three rules (classify raw, never substring-redact a structured
  value, free text only); the revoke tests assert `revoked` per status.
- **Found while applying R3-3, mine (measured):** the first classification-word test passed on the OLD
  module because its message carried the uppercase `CERTIFICATE_VERIFY_FAILED` marker the
  case-sensitive scrub left intact; the test uses the lowercase phrase alone and fails before.
- The corrected `tests/test_fleet_login.py` against the previous module (`06494b5`): **10 failed / 61
  passed**; against this head: **71 passed**. Full hermetic suite: **4656 passed, 16 skipped, 563
  deselected in 230.40 s**. Doc checks: 991 passed.
- Live on CRC as `developer`: count **0 → 1 → 0**, issuer `https://oauth-openshift.apps-crc.testing`
  intact, the revoked token dead after **121 s**; manual `oc` count 0 before / 0 after.

### Round five — every `Location` header is read (21:0x → 22:59) — commit `9a40691`, PR #289

- The final scoped pass could execute nothing; the operator verified each claim on this head and OB1
  re-measured before writing: `headers.get` comma-joins two `Location` headers and `_token_in` returned
  **None** for a token in the second (R5-1, **accepted, P0**); `get_list` separates them, and a
  pre-joined single value — the case `get_list` alone misses — is covered by splitting every `#`.
  R5-2/R5-3/R5-4 **accepted** (narrow). The `parse_qs` claim **refuted**: 200 000 fields → 200 000 keys,
  no raise; recorded in `docs/REVIEW_S4a.md` with both measurements, nothing implemented.
- F2 confirmed by the operator: `revoked` truthful from every site, the structural guard holds; its
  shape was not changed.
- The corrected `tests/test_fleet_login.py` against the previous module (`f2c221f`): **4 failed / 70
  passed** — exactly the four new tests; against this head: **74 passed**. Full hermetic suite: **4660
  passed, 16 skipped, 563 deselected in 231.14 s**. Doc checks: 992 passed.
- Live on CRC as `developer`: count **0 → 1 → 0**, the revoked token dead after **121 s**; manual `oc`
  count 0 before / 0 after.

### R5-1 corrected by the standard — `Location` is a singleton field (21:4x → 23:08) — commit `e42bf60`, PR #289

- **The operator retracted the R5-1 shape after research** (RFC 9110 §5.5: `Location` is a singleton
  field; a systems control client "might consider any form of error recovery to be dangerous"; the
  recovery was attacker-steerable). The recovery helpers shipped in `9a40691` are **deleted**: more
  than one `Location` is a typed terminal stop, what it carried is revoked best-effort (`best_effort=true`
  on the line, `revoked` truthful, None when nothing could be named and the message says #286), and one
  `Location` takes the simple path. The implicit-flow deprecation note recorded in §2.2 (no code).
- No evidence a legitimate OpenShift OAuth server sends two `Location` headers; CRC sends one.
- The corrected `tests/test_fleet_login.py` against `9a40691`: **1 failed / 73 passed** — the new
  malformed-response test; against this head: **74 passed**. Full hermetic suite: **4659 passed, 16
  skipped, 563 deselected in 231.77 s**. Doc checks: 991 passed (a stale citation of the deleted
  helper in the review record was replaced with plain text; the record keeps the history).
- Live on CRC as `developer`: count **0 → 1 → 0**, token dead after **121 s**; manual count 0 / 0.

---

## Part 2 — the orchestration, and what research changed (2026-09-21 → 2026-09-22)

The entries above are the implementer's. This part is the orchestrator's: what merged, what the
research overturned, and the two decisions that were wrong and are recorded as such.

### #283 merged and closed (2026-09-22 04:25) — `400c5f5`, PR #289

Five review rounds across Codex (`gpt-5.6-sol` xhigh), Cursor (Grok 4.6) and OB1-lite; **21 findings**.
Validated before merge: the orchestrator's own suite run on the PR head (**4659 passed, 16 skipped,
0 failed**, matching the implementer's), CI green, the deploy `Synced/Healthy` with `readyz`/`healthz`/
`metrics` all 200 and the module's constants read back **inside the pod**, and an independent live run
(`count_before=0 during=1 after=0`, the revoked token dead after **121 s**).

**Two of the 21 findings were caused by the orchestrator's own instructions**, and are recorded in
`docs/REVIEW_S4a.md` as such rather than attributed to a reviewer:

- A redaction rule ("redact the credential regardless of length") that corrupted classification
  inputs — measured: password `app` turned the issuer into
  `https://oauth-openshift.<redacted>s.example.com`, and password `certificate` made
  `ConnectError: certificate verify failed` stop classifying, giving `phase=connect` instead of `tls`.
- A `Location`-header fix shaped as *recovery* — which **RFC 9110 §5.5** refuted (see below).

**One reviewer claim was refuted and rejected**: that a large fragment could make `parse_qs` raise.
Measured: 200 000 fields, no raise. Recorded with the measurement so the record does not overstate
the reviewers.

### The standard beat the reasoning — `Location` is a singleton field

`RFC 9110 §5.5` classifies `Location` as a singleton, and states that a *systems control client*
"might consider any form of error recovery to be dangerous". The orchestrator had specified a fix
that searched **every** `Location` value for a token; that is the recovery the RFC warns against, and
it was **attacker-steerable** — a target sending two `Location` headers would choose which token
became the cluster credential. Replaced with count-then-refuse plus a best-effort revoke. **The
standard produced less code, not more**: `_fragments_of` and `_token_in` were deleted.

### A research claim of the orchestrator's, retracted

Posted to #284 and #285: that the stored ServiceAccount token carries a **one-year fuse** from the
Kubernetes legacy-token cleaner. **Refuted by the implementer from upstream source, then verified
here before retracting.** `legacy_serviceaccount_token_cleaner.go:171` skips any Secret the
ServiceAccount's `.secrets` does not reference, and a manually created token Secret — the only kind
OpenShift 4.16+ has — is never referenced. Measured on the lab: the poller ServiceAccount's `.secrets`
lists **only** its dockercfg, while the token Secret points back by annotation. A `last-used` **tracking**
label had been read as a countdown. Retracted on both issues with the citation.

### Merges (all validated on `main` after merging, branches deleted as a separate step)

| PR | what | evidence |
|---|---|---|
| **#290** | `SPEC_S4` §9 still described #285's renewal as `0.8 × lifetime`, superseded by the fixed margin §3.1 states | on CRC's measured `expires_in=31536000`, the stale rule renews **73 days** early vs **2 h** — five needless tokens a year per cluster, the litter #286 exists to stop |
| **#292** | the adversarial-review skill gains **Step 0: research first, spec second, code third** | the two findings above, neither reachable by code-reading, reasoning, or any of three reviewer seats |
| **#294** | `SPEC_S4b` — #284's design, **reviewed and merged before its implementation existed** | 57 fenced blocks, each anchor matching exactly once when applied |
| **#296** | the brief template names the interpreter's absolute path and requires a reviewer without it to say so in its first line | two Codex passes had run source-only on `httpx ModuleNotFoundError`, visible only in stderr |

### Issues opened

- **#291** — five rounds grew `fleetlogin.py` **443 → 729 lines (+65%)**, against the repo's rule that a
  review must not grow the code's complexity. Behaviour-preserving consolidation, tracked separately
  so it is not mixed into a fix PR.
- **#293** — a labelled ConfigMap of cluster stanzas that **generates** the Secrets, so nobody
  hand-makes one. Researched against prior art: it is essentially External Secrets Operator's
  `ExternalSecret`, and Argo CD is Secret-only because **its** declaration contains the kubeconfig
  while ours separates declaration from credential.

### Measured on the lab, and kept

- The estate's Role grants the fleet account **two** retrieval paths, both scoped to one named object:
  `get` on the token Secret, and `create` on `serviceaccounts/token` (**TokenRequest**). The operator
  mandated the long-term token; the TokenRequest grant is recorded as deliberately unused.
- **CRC cannot reproduce the split-CA failure**: its `kube-root-ca.crt` is six certificates, two of
  them the ingress leaf and the ingress CA. That merge is a CRC convenience, so a customer whose
  ingress is enterprise-signed fails where the lab cannot. Closed with a hermetic two-CA test plus a
  control, mutation-checked (forcing `verify=False` fails the split test while the control passes).
- A locked 389-ds account returns LDAP code **19** — not 48/49 — so `oauth-server` answers **HTTP 500**,
  not 401. Before #283 that was retried five times against an already-locked account.

### #284 in flight at the time of writing

PR #295, three review rounds: **7 → 5 → 2** findings. Not logged here until merged.

**Corrected 2026-09-22.** An earlier revision of this paragraph said the code "got *simpler* each
round" and that "the last round deleted `final`". Both are false, and were measured only when
adversarial review challenged them:

```
fleetlookup.py   cd00f2f 346 lines / 13 defs -> d94887a 388/14 -> 9e1abb2 395/15 -> 188930c 410/15
'final' count    d94887a 4 | 9e1abb2 1 | 188930c 1          -> deleted in round TWO
```

The module grew **+18.5%** and gained two functions. The defensible claim is that it grew a quarter as
fast as #283's `fleetlogin.py` (+65%) — not that it shrank. The same wording was in the review skill
and in a memory note; all three are corrected. The lesson is the one this session kept re-learning:
a claim that flatters the process is exactly the one to measure before writing it down.

---

## Part 3 — the review pass that found the claims were wrong (2026-09-22)

Two PRs were open and **neither had had its adversarial pass**: #307 (the fleet-account stanza, the
validation record and a new cluster-wide CA script) and #299 (a skill addition). Both were reviewed
this part, and both came back *not mergeable*. The theme of the part is that the defects were in the
claims, not only in the code — three separate documents asserted things no one had measured.

### #307 CI, and a guard doing its job (11:05) — commit `b2c9fe5`, PR #307

- CI was red on both Python versions: `test_the_table_covers_every_key_crc_overrides` failed because
  `crc.yaml` declared four `clusterConfig.fleetAccount.*` keys the `environments/README.md` table did
  not list. **Found by the suite.** The table's stated remit is the security question, and a fleet
  account whose password mints cluster access is squarely inside it, so no `EXEMPT_FROM_TABLE` entry.
- The privileged fact was **measured, not read off the template's comments**:
  `oc get role group-sync-dashboard-fleet-account -n openshift-config -o jsonpath='{.rules}'` →
  `[{"apiGroups":[""],"resourceNames":["ldap-oauth-bind-secret"],"resources":["secrets"],"verbs":["get"]}]`.
- Suite **4710 passed, 16 skipped**, 236 s.

### #299 — OB1-lite refuted four statements of fact (11:28) — commit `10bf81c`, PR #299

- **Found by OB1-lite** (Fable 5.1, default effort), all four **accepted** after re-measurement here;
  **three were the orchestrator's own claims**, two of them repeated to the operator in a summary.

  | claim as written | measured |
  |---|---|
  | `443 → 729` is `+61%` | `+64.6%`; `+61%` belongs to 712, round four |
  | #284's code "got simpler each round" | `fleetlookup.py` 346 → 410 lines, 13 → 15 `def`s (**+18.5%**) |
  | "the last round deleted a mechanism" | `final` went 4 → 1 occurrences at `9e1abb2` — round **two** |
  | "a reviewer's `CONFIRMED`" missed it | `3 C1: REFUTED`, **zero** CONFIRMED — the reviewers caught it |

- The fifth finding is the one that mattered: the section taught a budget of *"at most one bind per
  (target, credential), **ever**"*, while `CredentialGate`'s own docstring reads *"Best-effort and per
  process; the durable, replica-shared gate is #285's"*. A section about measuring budgets stated one
  the code cannot honour. Scope is now part of the claim, and the rule was wired into Step 1, the
  checklist and `brief-template.md`'s new C8 — **a rule stated only in its own section never fires**.
- **Snippets rejected**: the proposed blocks imported round-by-round attributions and line deltas over
  `gsd/` that had not been measured here. Facts taken, text rewritten shorter.
- Proof: the reviewer's prose checker **fails 9 on `0123a39`, passes 0 on `10bf81c`**. Nothing in
  `local-development/tests` or `.github/workflows` reads `.claude/skills`; docs citations
  **952 passed, 12 skipped**.

### #307 — three seats, one verdict (11:45) — commit `620e01d`, PR #307

**Found by Codex (`gpt-5.6-sol` xhigh), Cursor (`cursor-grok-4.6-high-fast`) and OB3 (Opus 5)**, run
in three separate detached worktrees. All three returned DO NOT MERGE; all three refuted C1–C4
independently. Codex and Cursor were given **no cluster credentials** (their claims are answerable
with `openssl` and `helm template`); only OB3 had live read-only access.

- **The defect.** `oc get cm X -o jsonpath='{.data.ca-bundle\.crt}'` exits **0 with empty output**
  when the ConfigMap exists under a different data key, and `|| die` catches only a nonzero exit.
  Measured against `openshift-config/ca-config-map`, whose key is `ca.crt`:

  ```
  head    ENTERPRISE_CM=ca-config-map -> enterprise: 0 of 0 kept / combined: 5 certs, 5985 bytes, exit 0
  fixed   ENTERPRISE_CM=ca-config-map -> ERROR: ... has no 'ca-bundle.crt' key
  ```

  A typo in the variable the script's own header tells you to set wrote a cluster-wide trust bundle
  without the enterprise root — into the object feeding **20** injected bundles on this lab.
- **Found by Codex alone**: `/BEGIN CERT/` does not match `-----BEGIN TRUSTED CERTIFICATE-----`, so
  such a block was invisible to the splitter.
- **Accepted**: source `[ -s ]` guards, a splitter matching any CERTIFICATE banner, `is_anchor()`
  replacing the text grep, an unreadable block that names itself, a failed proxy read that no longer
  looks like "no trustedCA", `revert_hint()` correct in all three branches and printed in the dry run,
  and **a guard on the result** — refuse if any anchor the proxy names today would be missing
  (`ALLOW_DROP=1` overrides). Input guards close enumerated paths; a result guard closes the rest.
- **Rejected**: Cursor's request to give `shared-rnd` `mock`'s `visibility: inherit`. `self-only` is
  the chart default for every entry but the first and can only narrow; copying `mock` would widen that
  cluster's membership to every host cluster-admin. Left narrow, reason written into `crc.yaml`.
- **Reviewer disagreement resolved without a fourth seat**: OB3 wanted an anchored-only match, Cursor a
  whitespace-tolerant one. Took both, on blast-radius asymmetry — dropping a real anchor breaks the
  cluster, keeping a non-anchor is inert.
- **Corrections to the orchestrator's own doc**: the Step F2 `Result:` block was a **hand-edited
  transcript the code cannot produce** (a 66-character subject from a line ending `| cut -c1-54`,
  under a heading no version emits) — replaced with a verbatim re-run, stating that the pre-apply run
  was never captured. It concealed a real bug: the script printed `from the proxy's current bundle`
  even when `ENTERPRISE_CM` named another source. Also corrected "dedup … so any input is safe
  regardless" and "the count staying at 152 … is the proof the filtering was right", and qualified a
  stale `147` that Case E moved to `152`.
- `docs/examples/cluster-secret-shared-rnd.redacted.yaml` **did not parse** (`ScannerError`, block
  scalar at column 0). Fixed; it leaks nothing — no `data`, no annotations, both credential-shaped
  values are placeholders.
- **Behaviour preserved**, verified against the live bundles: `1 of 1`, `5 of 6`,
  `combined: 6 CA certificate(s), 7949 bytes`, same `*.apps-crc.testing` leaf dropped.
- New `tests/test_refresh_cluster_wide_ca.py`: **5 of 6 fail on `b2c9fe5`, all 6 pass on `620e01d`**;
  the sixth passes on both as the behaviour-preservation check. Suite **4716 passed, 16 skipped**.

### Two process defects, both the orchestrator's

- **A stale local branch ref pushed instead of the commit.** Three worktrees existed for one PR; the
  branch was checked out in one at the pre-merge commit while the commit was made in a *detached*
  second. `git push origin <branch>` pushed the stale ref. Recovered by pushing the sha explicitly (a
  true fast-forward), fast-forwarding the real worktree and removing the two redundant ones.
- **`pgrep -fc` reported every reviewer dead.** The `-c` flag is Linux-only; on BSD it errors into the
  `|| echo 0` fallback. All four processes were alive throughout. This is already a recorded scar and
  it was written again.
