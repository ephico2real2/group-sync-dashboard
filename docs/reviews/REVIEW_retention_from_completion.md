# Review record — artefact retention ages from completion (#163, PR #202)

Branch `fix/retention-ages-from-completion`, base `main`. Head reviewed: `f3c9f61`. Three reviewers on
one brief of eight claims (`review_brief_163.md` in the session scratchpad; restated in the table):
Grok 4.6 (Cursor, ask mode — no shell; verdicts from the source), OB3 (Opus 5 — wrote a differential
harness that drove `main`'s and the head's `prune` over 200 randomised runs at several `now` values,
ran every proposed test fail-before/pass-after on a copy, and treated C2/C4 as deep), Codex (GPT-5.6,
xhigh — the same differential independently, a 10,000-id format harness, and the render comparison on
`git archive` exports). Every verdict was re-checked on the branch before a decision. Line numbers are
those of `f3c9f61` and are not maintained.

## Claims × reviewers × decision

| # | Claim | Grok | OB3 | Codex | Re-check / decision |
|---|---|---|---|---|---|
| C1 | `retention_stamp` returns an aware UTC second; the id fallback cannot raise for a minted id | CONFIRMED | CONFIRMED, one hole volunteered | CONFIRMED (10,000 ids parse) | Holds for what the worker writes. OB3's hole is real: a non-string `finished_at` in a hand-edited manifest raised `TypeError`, which `_maybe_prune` swallows — one manifest switched retention off for the whole store. **F2** |
| C2 | `older_than` is exact at the boundary: on the cutoff second kept, one second earlier doomed | REFUTED — the "±1 s" story is not the code | REFUTED on the "i.e." clause | REFUTED (harness: −1 s, +0 s, +1 s all `pruned=0`) | The brief's wording was wrong and so was the predicate: `stamp + 1 s < cutoff` kept a run stamped one second BEFORE the cutoff for one more second. `<=` is the exact reading. **F1** |
| C3 | Both tiers order by `(retention_stamp, id)` descending | CONFIRMED | CONFIRMED | CONFIRMED (requested-first/finished-last survives keep-K) | Holds. Codex's scheduled-tier construction becomes a regression test — it fails on `main` on behaviour (**F4**) |
| C4 | For a run finished the second it was requested, decisions are identical to `main`'s | REFUTED | REFUTED at exactly one second, whole-second `now` only | REFUTED (200 runs: `main=125 head=123`, two edge runs; `<=` → `diff=0`) | The difference is C2's predicate, measured twice independently. With F1 applied the differential is zero at every `now` — the preservation property is proven, not claimed |
| C5 | The four new tests fail on `main` for the behavioural reason | REFUTED — the fourth only `ImportError`s | REFUTED for the fourth | REFUTED (`4 failed` on main, one an `ImportError`) | Accepted. `main` aged unstamped runs by the id too, so the fallback test cannot fail on behaviour: it is a pin, renamed and pointed at the two runs that actually take the fallback (**F3**). Codex's scheduled-tier test is the fourth behavioural one (**F4**) |
| C6 | Chart 0.34.1, docs state the semantic, lint passes, render byte-identical to `main` | REFUTED — a bump cannot render identical | CONFIRMED | REFUTED (`cmp_status=1`; 25 `helm.sh/chart` labels, generated Secrets, `checksum/config`) | The claim was wrong as written: the chart label carries the version into every object and both charts generate Secrets. Codex's normalised comparison: `config_data_equal=True normalized_objects_equal=True objects=25`. No code change; the brief's next render-identity claim scrubs those fields |
| C7 | No other retention decision is keyed on the id | CONFIRMED | CONFIRMED | CONFIRMED (`rg`: the watermark, the directory removal, the download filename remain — none retention) | Holds |
| C8 | The first prune after upgrade deletes nothing `main` kept except by completion | CONFIRMED | CONFIRMED by construction | REFUTED — an unstamped failed run displaced from keep-K by a completed run is deleted where `main` kept it | **Rejected.** The construction is the bug the PR fixes seen from the other side: `main` kept a 101-day-old failure record and deleted a report that finished five seconds earlier. A run without a stamp is never `done` (`runs.py:149–157` stamps every completion in `finally`; measured) — it is a failure record with no artefact, and its only instant IS its request time. Codex's fix (a "legacy" id-ordered protection set in both tiers, permanent, not migration-only) would carry the old ordering forever for exactly the runs that have nothing to protect, and doubles `prune`'s branches. The changelog and docstrings say what the fallback covers instead |

## Findings

Each names who found it, the re-check, and the test that fails on `f3c9f61` and passes on the fixed
tree. Fail-before was run against `f3c9f61`'s `artifacts.py` swapped into the fixed test file: `3 failed,
1 passed` (F1, F2, F5 fail; F4 already right at `f3c9f61`); against `main`'s: F4 fails on the assertion
(`late` kept), F3 fails with the `ImportError` it documents. Reporting suite after the fixes: 61 passed.

### F1 — the boundary predicate was over-conservative (Grok, OB3, Codex) — accepted
`older_than` used `<`. Measured by two independent differentials: at a whole-second `now`, a run stamped
one second before the cutoff — which finished, at the latest, a millisecond before it — survived one more
second, and the doomed set differed from `main`'s for prompt runs. `<=`, exactly; the comment states the
three cases. `test_completion_rounding_can_never_delete_early` now pins all three (OB3's rewrite).
Cursor's proposed test was rejected: it pinned the `<` behaviour.

### F2 — a wrong-typed `finished_at` silently halted retention (OB3, volunteered) — accepted
`retention_stamp` caught `ValueError` only; a JSON number in one hand-edited manifest raised `TypeError`,
`_maybe_prune` swallowed it, and no run in the store was ever pruned again. Now `(ValueError, TypeError)`,
skipped like a malformed stamp. `test_a_hand_edited_finished_at_of_the_wrong_type_does_not_stop_retention`.

### F3 — the "legacy manifest" story was false (OB3) — accepted
`finished_at` has been in every manifest since the first release; the fallback is live for the run the
pod died under (`_load`) and, before this PR, the run a full queue refused. Docstrings, `values.yaml`,
README and CHANGELOG reworded; the fourth test replaced by
`test_a_run_that_never_completed_ages_from_its_id`, which pins the fallback on those two runs.

### F4 — scheduled keep-K by completion had no behavioural test (Codex, C5) — accepted
`test_scheduled_keep_uses_completion_order`: an early request that finished last owns the single keep
slot. `main`: `1 failed` (the later id was kept); head: passes.

### F5 — a naive `now` from an injected clock halted retention (Grok, volunteered) — accepted
The stamps are aware; comparing against a naive `now` raises `TypeError` into the same swallow as F2.
`prune` reads a naive instant as UTC (the clocks are UTC by contract). `test_a_naive_now_does_not_stop_retention`.

### F6 — a queue refusal did not stamp `finished_at` (OB3, volunteered) — accepted
Every other terminal transition stamps in `runs.py` (the render's `finally`, the window recheck); `submit`'s
`queue.Full` path did not, so a refused run took the id fallback. One line; `test_a_run_refused_by_a_full_queue_is_stamped_finished`.

## Rejected

- **Codex C8** — see the table.
- **Cursor: `list()` should order by completion** — the listing is request order by contract (the usage
  watermark `since_id` walks it); retention ordering and listing ordering answer different questions.
- **Cursor's boundary test** — pinned the `<` predicate F1 removes.

## Validation, pass 1

`tests/test_reporting_server.py`: 61 passed. Full hermetic suite from `local-development/`
(`--deselect tests/test_ui.py --deselect tests/test_live_smoke.py`): 3468 passed, 13 skipped.

## Pass 2 — the confirmation, at `916200a`

Seven claims (`review_brief_163b.md`), the same three reviewers. OB3 re-ran the differential at
9,036 runs (3 seeds × 6 `now` values × 2 caps): head vs `main` symmetric difference 0, and 72 for
`f3c9f61` — the harness still sees the gap it was built for; Codex's independent 200-run
differential: `ALL_DOOMED_SETS_IDENTICAL=True`. P1 (the predicate), P3 (the clocks are UTC), P4 (the
refusal stamp changes nothing else — every reader of `finished_at` traced) and P5 (the fail-before
matrix: exactly rounding/wrong-type/naive-now/refused fail against `f3c9f61`'s code; four behavioural
failures and one ImportError against `main`'s) CONFIRMED by all three with artefacts.

| # | Claim | Grok | OB3 | Codex | Decision |
|---|---|---|---|---|---|
| P2 | No exception escapes `retention_stamp` for a manifest `_load` accepts | REFUTED (the id) | REFUTED (the id) | REFUTED (the id) | **F7, accepted.** `_load` never read the id: the index key was the directory name, `Run.id` whatever the manifest said, and the fallback's `strptime(id[:15])` sat outside the `try`. A hand-edited id that is not a stamp raised out of every prune — the F2 hole on the other field, and a regression against `main`, whose string comparison could not raise. OB3 also measured a non-string id breaking `list()` (GET /runs and the usage pull 500) and an id that is a stamp but not its directory's name being doomed every hour and never leaving (`rmtree(_dir(run.id))`). The loader now refuses a manifest whose id is not its directory's name or does not parse, with the warning an unreadable manifest gets; 300 system-minted manifests reload identically (OB3's load-identity run). `test_a_hand_edited_id_does_not_stop_retention` |
| P6 | The C8 rejection: no path yields `done` + no stamp; an unstamped run has no artefact | REFUTED — a SIGKILL between the file write and the `done` persist leaves files under a `failed` run | CONFIRMED (drove every terminal transition through the real RunManager; `done + None on disk: []`) | REFUTED — the same window; "the rejected protection could save concrete files" | **Rejection stands; the sentence was imprecise.** The window exists, but the download handler (`gsd/reporting/server.py`, the `run.status != "done"` check) answers 404 for any run that is not `done`, so the files under a restart-failed run are not servable by anyone — "no artefact" means no *servable* artefact, and that is what retention protects. Cursor's mtime-based stamp and Codex's delete-on-restart were both rejected: the first reinstates a stamp for a run that never completed, the second adds a deletion path for files the next prune removes anyway |
| P7 | The five surfaces say the same thing | REFUTED | REFUTED | REFUTED | **F9, accepted.** Two docstring sentences and the CHANGELOG still said a queue refusal is unstamped — false at `916200a` — and the CHANGELOG contradicted itself in one entry; "every other terminal transition" was also wrong (the restart flip cannot stamp: the pod died at no known instant). Reworded per OB3's patch; Cursor's request that `values.yaml` and the README name the fallback added as one sentence each. Cursor's prose-agreement test rejected: it pins words, not behaviour |
| N1 | (volunteered, OB3) the startup seed of the last-success gauge catches `ValueError` only | — | found | — | **Accepted.** The manifest F2 makes retention tolerate — a JSON number in `finished_at` on a done, scheduled run — raised `TypeError` out of `build_report_app`: a crashloop on the very input retention now survives. One token; `test_a_hand_edited_finished_at_does_not_crashloop_the_seed` |

Validation, pass 2: `tests/test_reporting_server.py` 63 passed; full hermetic suite 3471 passed,
13 skipped.
