# Session change log — group-sync-dashboard, 2026-09-20 → 2026-09-20

What this session did to PR #247 (#245: the cluster-connection module's self-diagnosing logging, the
separate HTTP log level, the four flows as mermaid and ASCII), in the order it happened. Times are
git author times in America/Chicago; test totals are the summary lines of runs this session launched;
every "measured" claim is one the session ran a command for; nothing below is recalled from memory
alone. The session resumed a fork that died on an Opus session limit mid-suite, with the first-pass
fixes uncommitted in the worktree.

Outcome in one line: **pending**

| | Before the session | After |
|---|---|---|
| `main` | `95b8c0f` (#242 merged); the branch was six commits behind it | pending |
| PR #247 | open at `28c9e89`, ten files modified and uncommitted (the first-pass fixes), the review record untracked with only two of three seats' columns | pending |
| Review passes on #247 | one: Codex, Grok and OB3 on `250cc54`, their reports in the session scratchpad, the fixes half-applied | pending |
| Chart | `0.43.0` on the branch (`0.42.1` on `main`) | pending |
| Session changelog | none for today | this file |

---

## Part 1 — the first pass folded in, the PR brought up to main (2026-09-20)
### The first pass folded in (17:44) — commit `cd0f773`

- Resumed with the predecessor's fixes for the Codex, Grok and OB3 first-pass findings uncommitted in
  the worktree; read all three reports and the diff before touching anything.
- **Found by re-reading the diff:** the announce-once fix emitted every finding as
  `secret-refused phase=parse`, so `phase=credential` lost its only producer and a shadowed values
  entry — which loads — was called refused. `reader.finding_event` owns the event name and phase per code.
- **Accepted from OB3** (its column had not been in the record): the `discovery-failed` line passes the
  host's credentials; the boundary pin that plants a credential in every field the parser reads; `root=`
  refused in `GSD_LOG_LEVELS`; the worked example's field order; flow 2 redrawn as the parser's decision
  tree with the two values-only modes named; the `httpLogLevel` helper moved below `gsd.logLevel`.
- **Rejected from OB3:** echoing a dotted logger name (a value that looks like a name is still a value);
  `cycle=` seeded from the clock (per-pod logs scope it already).
- Every new pin mutated on a throwaway copy before it was kept: four mutants, each killed by exactly the
  intended test (the two harness artefacts of the copy layout aside).
- Measured: `helm lint` clean; `helm template` unset / both set / junk (refused); all four mermaid blocks
  rendered with `@mermaid-js/mermaid-cli@11` (38 266 / 30 494 / 18 969 / 18 454 B) and the two redrawn
  flows viewed as PNG.

### Merged main, suite green (17:44 → 17:56) — merge `5d38425`, commit `b13b44e`

- `origin/main` at `95b8c0f` merged clean. Hermetic **4199 passed, 15 skipped**; UI **486 passed**
  (serially, after the other worktree's run); helm clean in three states.
- **Operator deliverable (via the coordinator):** the TLS verification record from #244's newest comment
  placed beside the three-modes picture. The comment carried the numbers, not the commands, so both were
  re-measured read-only against the lab from this worktree (pod `group-sync-dashboard-76d5bb4ff8-w8pbx`):
  `ssl_verify_result` **0 / 20 / 18** for `mock-trusted` / `mock-privateca` / `mock-selfsigned` on port
  6443 with the pod's own `.curlrc` stores, and `/api/clusterconfigs` serving `trusted-bundle` / `caData` /
  `insecure` all `ok` plus the `insecure-with-ca` finding word for word. Commands written down as run.
- Pushed; the four seats launched on `b13b44e` (Codex xhigh on a `git archive` export, Grok attached —
  two `nohup` launches died silently with 0-byte output, the attached run worked — OB2 and OB3).

### CI red, then behind main (18:25) — commits `81c357c`, merge `e92ad27`

- **Found by CI (relayed by the coordinator):** `ModuleNotFoundError: No module named 'tests'` — two
  `from tests.test_clusterconfig import _Host` imports in the predecessor's test file; the suite has no
  `tests` package and imports siblings by bare module name. Fixed to the bare form.
- `origin/main` had moved to `14a9624` (#233 merged); merged clean, and `git diff --stat origin/main HEAD`
  verified to touch only this PR's files — no deletions under `reports/`, no `test_ui.py` reverts.
- Hermetic, run from `local-development/` exactly as CI does: **4227 passed, 15 skipped**. CI on `e92ad27`:
  all ten checks concluded, nine success and `container-smoke` skipped.

### The second pass folded in (18:39) — commit `c518085`

- Four seats' reports read in full; every premise re-verified against the code before deciding
  (`Settings.cluster_policy`'s default, the `ConfigError` chain through `poll_once`, the labels tuple, the
  logger names emitted). Decisions in the record's second-pass table.
- **Accepted from Grok** — the finding of the pass: the first fix's `inherit` default where the tier
  serves `self-only`, a widening the shape read as no change. **Accepted from OB2:** the ConfigError
  provenance branch, the transport actions by exception name, labels in the shape, the Unicode line
  separators, `redact` never raising, the token cache popped on removal, the 200-character logger-name
  bound. **Accepted from Codex:** the delimiter-ambiguous digest (measured: `"x|"+"y"` vs `"x"+"|y"`),
  complaints counted per kind rather than per entry (50 000 measured). **Rejected:** `_MIN_SECRET = 1`,
  `ReadTimeout` as `poll`, `cluster=` on parse refusals via `Finding.public()`, a 4 096-character cap on
  the whole variable, `gsd.poller` in the docs (the logger was moved instead).
- Eleven pins mutated before being kept; the delimiter pin **survived** its first version (the example
  did not collide under the join) and was rewritten until its mutant died.
- Hermetic **4241 passed, 15 skipped**; helm clean; four blocks re-rendered (38 370 / 33 716 / 18 969 /
  18 454 B). CI on `c518085`: all ten checks concluded, nine success and `container-smoke` skipped.
### OB3's seat folded in (18:58) — commit `0e2a548`

- OB3 (Opus 5 at max, briefed on C1, C2 and C6) reported after the other three had been applied and
  named which of its findings the live tree already closed. Four were open: **Accepted** the
  standing-discovery-failure gate (measured 1/1/1/1 WARNINGs over four failing cycles; now once, keyed
  on the outcome, with `discovery-recovered`), the one `_text` guard for every conversion in
  `events.py`, the unknown-key echo in the parser (described by length unless a key the contract
  knows), and flow 1's shadow route plus every event name in the document. **Decided, not patched:**
  N1 — the poll-failure line stays one per poll here (1 440 a day per down cluster at the default 60 s
  is recorded for a follow-up); N5 — `_EVENTS` says why `discovery-failed` is not in it.
- Its three code pins mutated before being kept (the gate, the guard, the echo): each killed.
- Hermetic **4257 passed, 15 skipped**; UI **496 passed** (serially); helm clean; four blocks
  re-rendered (42 606 / 33 716 / 18 969 / 18 454 B), flow 1 viewed as PNG.
