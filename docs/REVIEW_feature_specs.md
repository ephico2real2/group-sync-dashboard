# Review — PR #69, the feature programme's thirteen specifications

Adversarial second-opinion pass, 2026-09-04, two reviewers on one eight-claim brief: Codex (GPT-5.6,
with a shell) and Cursor (ask mode, shell blocked, reading Codex's measurements where it could not
make its own). Both records are reproduced from the reviewers' output; each verdict was re-checked
here before acceptance. A verdict is not a result; the artefact is.

## The brief, and both verdicts

| Claim | Codex | Cursor | Accepted? |
|---|---|---|---|
| C1 `_spec_introduces`: a spec citation passes only when a spec's own content carries the anchor | REFUTED | REFUTED | **Yes** |
| C2 The joined design text is verbatim except the three stated seam repairs | REFUTED | REFUTED | **Yes** (wording) |
| C3 The reconciliation rows (migrations, shared index, version pairs) | REFUTED (row 3) | REFUTED (row 3) | **Yes** |
| C4 The four citation corrections point at real text and keep the sentence's meaning | CONFIRMED | CONFIRMED | — plus one note fixed |
| C5 Index rows equal spec headers and GitHub issues | REFUTED | REFUTED | **Yes** |
| C6 The markdownlint ignore covers the bodies and not the index | CONFIRMED | CONFIRMED | — |
| C7 No default breaks the modular rule and no interaction is unmodelled | REFUTED | REFUTED | **Yes**, as an interaction |
| C8 No spec's old text is produced only by a later spec | REFUTED | REFUTED | **Yes**, three inversions |

## C1 — the citation rule certified prose. Accepted; rule rewritten twice

**Finding.** Codex wrote a probe spec citing `docs/DESIGN_login_capture.md#operator amendment applied`,
an anchor that exists nowhere in that document, and the test passed it: the phrase is a heading in
`SPEC_C1_table_export.md`. Cursor added that `Bogus.group_count_changes` would pass on B4's
`def group_count_changes(` because the bare member was accepted without its class.

**Re-check.** Reproduced with both probes before the fix. During the review the rule had already
been moved from a substring search to parsed Python definitions for `.py` targets (my own probe
had found `Store.name` passing on an unrelated assignment in prose), but the non-Python branch still searched
prose, and the bare-member match had no class check.

**Applied.** `_spec_introduces` now accepts, for a Python target, only a name some spec's Python code
block defines (parsed; line-start definition forms for fragments that cannot parse) or literal text
inside such a block, and a bare-member match requires the class to be defined by the cited file or a
spec; for any other target, the anchor must sit inside a fenced block of a spec. Both fence patterns
are anchored to line start, because the C-batch specs quote triple backticks inside sentences and an
unanchored pattern paired one with a real fence and swallowed a page of prose as code — which is
why the probe still passed after the first fix. Final probe: the four anchors that must fail (the
prose phrase, the wrong class, `Store.name`, a missing symbol) fail; the four that must pass (a
method quoted as a fragment, a method in an unparseable two-level fragment, an index name inside a
SQL string, a YAML anchor in a D1 fence) pass; the full test passes.

**Rejected part.** Codex's snippet restricted non-Python anchors to fences with a fixed language
list. Any line-start fence is the right set: the specs open fences with `markdown`, `text`, `diff`
and no language at all.

## C2 — "verbatim" overstated. Accepted; wording

Both reviewers measured the joined files against the raw blocks: the three seam repairs are exactly
as stated, and every spec's preamble, body and closing parts are substrings of the joined source.
The four citation corrections were also in the joined text, and the header paragraph said "nothing
in it was rewritten by hand". The corrections were always listed in the notes; the paragraph was
wrong. Header and index now say: verbatim with exactly two kinds of exception, both stated in the
file, each changing a reference and never a claim.

## C3 — row 3 false for the A batch. Accepted

The A design says "Chart.yaml is not bumped" and "none of these PRs is a release". The row now
says release-bearing bodies assumed the next release and the A batch carries none.

## C4 — confirmed, and a note of mine corrected

Both reviewers quoted the target lines. Cursor noticed my D2 note named a metric
`gsd_tier_check` that does not exist; the alert's expression is over
`gsd_visibility_tier_checks_total`. Fixed in the note.

## C5 — five version strings differed in wording. Accepted; a test holds them now

Issue numbers matched everywhere; the index abbreviated five version strings. The index now
carries the header strings, and `tests/test_specs_index.py` holds every index row to its spec's
header (release, version, issue, status), holds the file set equal, and holds the issue numbers to
the implementation order. Neither reviewer could reach GitHub from its sandbox to check the
milestones; verified here with the `gh` CLI when the issues were created.

## C7 — retention on, backups off. Accepted as an interaction, not a default change

Both reviewers found the same combination: `syncEventsDays: 730` on by default while the design
lets retention run when `backup_dir` is empty — an irreversible delete with no copy anywhere. The
operator chose the 730 default deliberately; what was missing is the model for the combination.
Resolution recorded in the B2 spec's notes: derive — the prune is held whenever backups are
disabled, exactly as it is held until the first successful backup, with the same once-only warning;
the test and the values prose change accordingly. Codex's snippet (default to 0) was rejected
because it reverses an operator decision the rule does not require reversing once the interaction
is modelled.

## C8 — three ladder inversions. Accepted; recorded in A3, B2 and B1

- A3 lands before A2 but says "after the A2 bullet" and documents signed images with SBOM and
  provenance and an attested chart, which only A2 produces.
- B2's "Not built yet" new text keeps the cliff clause that B4, which lands first, removes.
- B1's chart README old text says "eleven" alerts; B4 makes it twelve and B1 fourteen.

Each is a note that governs the body at implementation. The index's reconciliations list gained a
sixth row pointing here.

## Not asked, and what happened to it

- Cursor: the B2 note "adds only `sync_event_by_time`" while the body still inserts the membership
  index. The note now says the body's insertion is skipped because B4 made it.
- Codex: the full citation test showed failures during its run. Those were the probe files of the
  rule rewrite in flight; the test is green on the committed tree.

## Outcome

Six of eight claims refuted by both reviewers, all six accepted after re-checking, none accepted as
proposed without change: two snippets rejected on grounds recorded above. The most consequential
finding was C1 — the guarantee the specs rest on was open on the prose side — and the second
rewrite plus the eight-line probe is what closed it.
