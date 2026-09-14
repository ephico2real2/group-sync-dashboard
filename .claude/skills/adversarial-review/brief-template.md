ADVERSARIAL REVIEW — PR #<n> "<title>", repository <abs path>, branch <branch> (checked out, head <sha>).
Diff: `git diff main...HEAD`. Spec applied: docs/specs/SPEC_<id>_<slug>.md (sections "### Files",
"### Verification", and the "Orchestrator's notes", which supersede the body where they differ).

For EACH claim return one line `C<n>: CONFIRMED | REFUTED | PLAUSIBLE` and the artefact (a command and its
output, file:line, a quoted line from an installed package's source). A bare CONFIRMED with no artefact counts
as nothing. For EVERY finding — a REFUTED verdict, a PLAUSIBLE verdict that names a risk, and anything you
volunteer at the end — give the FULL code of the fix: the whole function, block or file section as it should
read, with the file path and where it goes, never a fragment or a description; AND a test that fails before
the fix and passes after, in full. A finding without its full snippet and its test is not a finding and will
be discarded. Measure; do not reason from memory. The interpreter is <venv>/bin/python. Do not modify tracked
files, do not commit, run the thing under review only in a COPY outside the repository, create NOTHING inside
the repository tree, delete every temp file you create.

C1. <file>, <symbol> (lines a–b). CLAIM: <one sentence>. Refute with <the concrete way to break it>; show it by
    <the measurement>.
C2. <the semantics the change relies on — an expression, an option default, a wheel tag>. CLAIM: … Cite the
    documentation or measured behaviour.
C3. <the OFF state and every switch interaction>. CLAIM: … grep both files.
C4. <fidelity to the spec's NEW blocks, and that nothing else changed>. CLAIM: … diff each block.
C5. <dependents, `needs:`, workflows that call this one>. CLAIM: …
C6. <the next real use of this change on this repository>. Run it in a copy and read the result; refute
    anything an operator would have to fix by hand.
C7. <what could go red with no code change>. CLAIM: … name every source and the worst one.

Finish with: the single most important finding, and anything you saw that was not asked — each with its full
snippet and test, the same as a claim.
