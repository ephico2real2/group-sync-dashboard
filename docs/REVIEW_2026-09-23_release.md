# Review — the 2026-09-23 release: #324–#334

Adversarial passes on eleven pull requests merged on 2026-09-23. **First pass** on #261 parts 2–4: OB3 (Opus 5.5,
max effort), which confirmed the gaps and drafted the code for #326–#330. **Second pass** on #324–#330 against an
integration head (main `8eb73d9` with all seven merged, `d86acd6`), on a 23-claim brief:

- Codex (gpt-5.6-sol, xhigh): had a shell, but its sandbox refused Chromium (`MachPortRendezvousServer … Permission
  denied`), so its UI claims are structural.
- Grok 4.6 high fast (Cursor, ask mode): no shell; traced from source.
- OB1-lite (Fable 5.1): measured on a copy.

A Grok **confirmation pass** covered the fix commits. #331, #333 and #334 had their own passes. Every verdict below
was re-checked by the orchestrator before a decision, and every applied fix was proven by a test that fails on the
previous head and passes on the fixed one.

## Verdicts — the second pass (#324–#330)

| Claim | Codex | Grok | OB1-lite | Decision |
|---|---|---|---|---|
| C1 #326 count and named list are one population | CONFIRMED | CONFIRMED | CONFIRMED | — |
| C2 #326 "still ranked above" true for every name | PLAUSIBLE (torn snapshot) | CONFIRMED | CONFIRMED | **Accepted on the fact; snippet rejected** |
| C3 #326 self tier "listed in your grants above" | REFUTED (200-row page) | CONFIRMED, residual named | CONFIRMED | **Accepted** |
| C4–C7 #327 card at self tier, empty branches, label, ids | CONFIRMED | CONFIRMED | CONFIRMED | — |
| C8 #328 `member_count` can print "null" | CONFIRMED (never null) | REFUTED (never null) | CONFIRMED (never null) | — (OB3's first-pass risk overturned: the store coalesces to 0) |
| C9 #328 disclosure state across clusters | CONFIRMED | CONFIRMED | PLAUSIBLE, fix F1 | **Accepted** |
| C10 #328 tile and split arithmetic | CONFIRMED | CONFIRMED | CONFIRMED | — |
| C11 #329 the separator can lead a line | PLAUSIBLE (structural) | PLAUSIBLE, nowrap fix | CONFIRMED with caveat | **Accepted on the fact; both snippets rejected** |
| C12–C15, C17–C20 | CONFIRMED | CONFIRMED / PLAUSIBLE | CONFIRMED | — |
| C16 the suites on the integration head | errors (no Chromium) | PLAUSIBLE | 1107 passed | — (the orchestrator's full run: 5339 passed) |
| C21 #325 the refusal budget | REFUTED | REFUTED | REFUTED | **Accepted; the operator chose between two fixes** |
| C22 #325 the release versions | REFUTED | REFUTED | REFUTED | **Accepted; Codex's test rejected** |
| C23 #325 its code citations still resolve | CONFIRMED | CONFIRMED | CONFIRMED | — |

## C2/C3 — the reconciling clause claimed more than it held (#326)

**Finding (Codex; Grok on C3).** The index and the worklist are two requests under two snapshots, so a poll between
them could name a namespace the worklist did not hold yet. At the self tier the grants above are a served page
capped at 200 rows, so "listed in your grants above" could be false.

**Re-check.** Both mechanisms confirmed in the source.

**Decision.** Accepted. Codex's three-way sentence ("the two audit snapshots do not agree") was rejected: a transient
torn read resolves on the next poll, and an alarm sentence grows the code for a state the reader cannot act on. The
wide tier now names only what the rollup holds; the self tier says "still among your direct grants". Two tests fail
on the previous head and pass (`96bdea7`).

## C9 — the disclosure survived a cluster switch (#328)

**Finding (OB1-lite).** The comment called `view.nsWideOpen` "a preference like the fold", but the cluster-change
block resets the fold and left this flag. **Decision.** Accepted, OB1-lite's F1 as written: one reset plus the
comment. The test fails with `[True, None, '']` and passes (`05a30a9`).

## C11 — the name separator could lead a line (#329)

**Finding (Grok, Codex, OB1-lite).** The space before " ·" was a break opportunity inside a cell that breaks names
anywhere.

**Re-check.** A sweep of 240 name lengths per width: separated at 17 (375), 17 (393), 4 (768) and 2 (1280).
Grok's `white-space: nowrap` on the chip made the cell overflow (scroll width 522 in 230). A no-break space before
the dot, tried by OB1-lite and here, still separated 14 of 240 at 375.

**Decision.** Accepted on the fact; both snippets rejected on those measurements. The fix puts the last code point
and the separator in a nowrap tail — the mechanism Codex also proposed — measured at 0 separations and 0
overflowing cells at all four widths (`ce87be1`).

## C21 — the credential gate was per target; a lockout is per account (#325)

**Finding (all three).** The spec's gate was one entry per target, so T clusters on one fleet account could present
one wrong password T times (#315).

**Two fixes proposed.** Grok and OB1-lite: gate a 401 per account and a 500 per target (keeping R2-1). Codex: gate
every bound failure per account, because a locked account's 500 (LDAP code 19) cannot be told from a sick target's.

**Decision.** The operator chose Codex's rule (2026-09-23), reversing R2-1. The spec text was written against the
spec's own sections rather than pasted from Codex's shortened §3.3, which would have dropped the R3-1 and R3-2 detail.
The confirmation pass then found two leftover per-target sentences (§3.1, §3.6), fixed with the pin test extended
(`be0c7dc`, `078ebfd`).

## C22 — the release versions (#325)

**Decision.** Accepted: app 0.32.0, chart 0.53.0, in four places. OB1-lite's test was taken: a spec the CHANGELOG
has not begun must name a version above the tree's. Codex's was rejected: it pinned "current chart + 1 minor",
which breaks the moment another PR bumps the chart before S4c ships.

## #331, #333 and #334

- **#331** (the IME lookup test race, found by CI on #329): Grok accepted. Its one REFUTED point — the new wait times
  out on an empty cluster list — cannot happen with the fixture, and a bounded timeout is correct there.
- **#333** (#332, focus under the sticky Generate bar): Grok found the 7rem padding short once the totals preview
  painted. Measured, the bar ranges from 44 px to 160.5 px (320 px wide, two clusters), so Grok's 10rem was also
  0.5 px short. **Accepted on the fact, snippet rejected**: a ResizeObserver writes the bar's real height into the
  padding. The confirmation pass (C5) replaced a 200 ms sleep in the guard test with a wait on the observer.
- **#334** (the walk's evidence): Grok found three README numbers not in the committed files — "16 tabs" (14), a tile
  value the check never recorded (53), and "76" captures (75). All corrected. **Rejected:** "no `screenshots/`
  directory" — ten PNGs are committed; the reviewer's ask mode does not list binaries.

## Not asked, and what happened to it

- OB3: the risk tint lost on even rows, and a keyboard reader's focus lost from an index row on every poll — shipped
  as #330.
- OB1-lite NA-1: the specs index still lists S3 and S4b as `specified` although steps shipped. Recorded; the status
  is the operator's to state.
- OB1-lite NA-2: markdownlint MD012 in `docs/specs/README.md`. Pre-existing; unchanged.

## The orchestrator's own errors

A record listing only the reviewers' findings is worth less than one that does not.

- Composing #327, a JavaScript comment was moved out of a `${…}` expression into the template literal, where it
  would have rendered as text in every worklist row. Caught before the suite, by reading the result.
- The first release checks proved less than they claimed. #320 accepted the oauth-proxy's `session` row; #330
  counted even rows across every table rather than per `tbody`. Both were re-measured precisely, and the script was
  corrected and re-run (`results_release_7e68a93.json`, 15/15).
- A per-PR file check in zsh passed an unquoted file list as one pathspec and reported "none" for every PR. Caught,
  retracted and re-run with a proper split.
- The walk's README carried three numbers the files did not; the #334 review caught them.

## Outcome

Eleven PRs merged; every one green 8/8 on the exact head merged, refreshed onto main first. Reviewer findings on
code: 6 accepted (C2, C3, C9, C11, #333's C4, #333's C5), 4 snippets rejected with measurements (Codex's C2 sentence,
Grok's and OB1-lite's C11, Grok's 10rem), 1 test rejected as brittle (Codex's C22). Spec findings: C21 and C22
accepted, C21 decided by the operator. Deployed through Argo CD (`7f1856a920`, `e3b3731b78`, `7e68a93565`, each
verified in-pod) and walked: 84/84, 24/24, 11/11 integrity, 15/15 release checks, #332 re-measured 0/40.
