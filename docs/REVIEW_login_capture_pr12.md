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

Write below. Nothing yet.

Finish with a **debt summary** for the PR as a whole: what it introduces, what it accepts and why, what
it avoids — and one sentence on whether the debt is worth the feature.

---

## Fable — pass 2

Write below. Nothing yet. Same requirements: full code in this file, a test per finding, and an explicit
debt judgement. Additionally, mark each of Codex's findings AGREE / DISAGREE with evidence — a second
pass that only adds findings has not reviewed the first pass.

---

## Arbitration

The arbiter fills this in after both passes: what is applied, what is rejected and why, and what is
deferred with the reason. A finding rejected here must say which evidence contradicted it.
