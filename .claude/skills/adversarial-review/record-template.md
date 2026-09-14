# Review — PR #<n>, <id>: <title>

Adversarial second-opinion pass, <date>, on the <k>-claim brief for #<n> (`docs/specs/SPEC_<id>_<slug>.md`
applied). Codex (gpt-5.6-sol, xhigh) had a shell and measured; Cursor (Grok 4.6 high fast, ask mode, shell
blocked) traced from source and marked what it could not measure PLAUSIBLE. Every verdict was re-checked
here before a decision.

## Verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 <claim> | CONFIRMED | REFUTED | **Accepted** |
| C2 <claim> | REFUTED | PLAUSIBLE | **Accepted on the fact; snippet rejected** |
| C3 <claim> | CONFIRMED | CONFIRMED | — |

## C<n> — <what was found>

**Finding (<reviewer>).** <the claim, the artefact, the proposed fix>.

**Re-check.** <what you measured yourself: the command, the output, the documentation line>.

**Decision.** <accepted / accepted on the fact, snippet rejected because … / rejected because … / routed to
SPEC_<x> because that spec owns the file>. <what was applied, where the deviation is recorded>.

## Not asked, and what happened to it

- <reviewer>: <the volunteered observation> — <applied / recorded / no change, and why>.

## Outcome

<how many claims refuted, how many accepted, which snippets rejected and why in one clause, what was
re-validated after the edits (tests, suite, helm, image, CRC, live checks, CI), and whether a second pass
on the fixed head ran and what it found>.
