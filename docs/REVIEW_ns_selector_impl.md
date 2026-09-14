# Review — PR #112, the mnemonic namespace selector (issue #102, B2)

Adversarial pass on the real code (Extension B2 applied from
`docs/DESIGN_reporting_auditors_and_ns_selector.md` §3.5–3.6). 2026-09-14. Codex (gpt-5.6-sol, xhigh,
shell — ran pytest, the endpoint probe, and helm) and Cursor (Grok 4.6 high fast, ask mode — its
allowlist refused every Shell call, so it traced the source and marked runs PLAUSIBLE).

## Verdicts

| Claim | Codex | Cursor | Decision |
|---|---|---|---|
| C1 the XOR validator is a 422 at the endpoint | CONFIRMED (both=422, neither=422, mnemonic-only=202) | PLAUSIBLE (traced `create_run`'s `except ValidationError`) | — |
| C2 expansion, cap, and the failed-run lifecycle are correct | REFUTED in part (F1: false truncation note) | REFUTED (F1: same) | F1 accepted |
| C3 the explicit-names path is unchanged | CONFIRMED (51 names still 422, no KeyError, e2e still posts `namespaces`) | PLAUSIBLE (traced the same) | — |
| C4 the wiring and the chart value are correct | REFUTED in part (F2: nil-unsafe render) | PLAUSIBLE — called the value "nil-safe" (**missed F2**) | F2 accepted |
| (volunteered) the empty-selector message | F3: misleading when no key is configured | — | F3 accepted |

## Findings

### F1 (Medium) — a selector cap printed a false "table cut at 5000 rows" note

**Finding.** `namespace_access.py` correctly added the 50-name Coverage note, but also set
`Built.truncated = truncated or selector_capped`. `assemble()` reads `truncated` as "a `cut()` hit
`ROW_LIMIT`" and inserts a Truncation section reading "At least one table was cut at 5000 rows; `totals`
carries the whole counts." For a 60→50 selector cap neither clause is true — no table was row-cut and
`totals` reflects the 50 covered namespaces. Both reviewers flagged it; Cursor's one-line diagnosis:
"`Built.truncated` means a `cut()` at `ROW_LIMIT`. Assemble's sentence is that meaning. The Coverage
section is already the cap record (design §3.6). Do not or-in the cap."

**Re-check.** Traced `assemble()` (`common.py:285`): the note is gated only on `built.truncated`. The
two proposed fixes close the same hole differently — Codex adds a `truncation_explained` field to the
`Built` dataclass and suppresses the note when it is set; Cursor simply stops or-ing the cap into
`truncated`, leaving the Coverage section as the sole cap record. Both are correct.

**Decision — accepted on the fact; Cursor's snippet chosen over Codex's.** Per the "review fixes stay
simple" rule (the smallest fix that closes the hole; a review must not grow the code's complexity), I
took Cursor's form: `return Built(sections, totals, truncated, include_members)` — the selector cap no
longer touches `truncated`, so `assemble()`'s note is correct with no new dataclass state. Codex's
`truncation_explained` field would have added a state whose only job is to suppress a note the simpler
fix never emits. `truncated` now carries exactly one meaning (a `ROW_LIMIT` cut) at every call site.

### F2 (Medium) — the render aborted when `namespaceSelector` was absent or null

**Finding.** `gsd.reportingGuards` in `_helpers.tpl` read
`trim (toString ((.Values.reporting|default dict).namespaceSelector|default dict).label | default "")`.
`toString` runs on `nil` and yields the string `"<nil>"` *before* `default ""` can act, so an absent
`reporting.namespaceSelector` stanza (or `--set-json reporting.namespaceSelector=null`) produced the
selector `"<nil>"`, which is not in `namespaceMetadata.labels`, and the guard `fail`ed the render with
`exit 1`. Codex caught it by running `helm template`; Cursor, with no shell, traced the `| default dict`
on `namespaceSelector` and concluded "helm value is nil-safe" — it could not see the `toString`
conversion, and **missed the finding**. This is the exact divergence the two-reviewer pass exists for.

**Re-check.** Reproduced: on the pre-fix head `--set-json reporting.namespaceSelector=null` exited 1
with `selector "<nil>"`. Applied Codex's verified block — split the expression so `default ""` acts on
the label before `toString`:

```gotemplate
{{- $nsSelector := (.Values.reporting | default dict).namespaceSelector | default dict -}}
{{- $nsSel := trim (toString ($nsSelector.label | default "")) -}}
```

**Decision — accepted.** After: a default install renders `GSD_REPORT_NS_SELECTOR_LABEL=""`, the
explicit-null stanza renders `exit 0`, a configured-and-declared label renders its value, and the two
mis-configuration guards (label not in `namespaceMetadata.labels`; labels set with `rbac.namespaces`
off) still fail with their messages. `helm lint`: 1 chart linted, 0 failed. This bug was inherited by
the B1-merged helper; the fix lands here in B2 where the selector value is first consumed. (The
whole-`reporting`-stanza null case still nil-points at `configmap.yaml:108` — a pre-existing, separate
lack of guard on an unsupported input, out of scope for this finding.)

### F3 (Low) — the failed-run message named the wrong cause when no selector key is configured

**Finding.** In `build`, a `mnemonics` selection on a deployment where `namespace_selector_label` is
empty (no `GSD_REPORT_NS_SELECTOR_LABEL`) fell through to `namespaces_for_metadata`, matched nothing,
and failed the run with "no namespace carries the selector label with value(s) …" — blaming the data
when the real cause is that the selector is not configured on this deployment.

**Re-check.** Traced: `namespaces_for_metadata` returns `[]` for an empty key, so the message was always
the data-blaming one. Added the guard before the expansion:

```python
if not ctx.namespace_selector_label:
    raise ValidationError(
        "mnemonic namespace selection is not configured on this deployment; set "
        "reporting.namespaceSelector.label or use explicit namespace names")
```

**Decision — accepted.** Same 202→failed lifecycle (it needs the snapshot, so it stays a failed run, not
a 422), now naming the configuration problem. A test asserts the "not configured" message.

## Not asked

- Codex confirmed a mnemonic value with an embedded comma/space round-trips as one value, a
  `Terminating` namespace is still selected and attested, `include_members=true` through a mnemonic
  includes the roster, and the JSON artefact `params` retains `mnemonics=["beta"], namespaces=null`.
- Codex noted the live e2e walk was not rerun (no route/credential supplied); the walk's
  namespace-access helper still posts `{"namespaces": …}`, unaffected by the new optional parameter.

## Outcome

Three findings, all accepted; F1's snippet taken from Cursor (the simpler of two correct fixes), F2 and
F3 from Codex's verified blocks. The selector cap is now recorded only in the Coverage section;
`Built.truncated` means a `ROW_LIMIT` cut and nothing else; the render is nil-safe across a default
install, an explicit-null stanza, and a fully-configured selector; and a mnemonic selection on an
unconfigured deployment fails with the right message. Two new tests cover the 60→50 cap (Coverage
present, no Truncation note, `truncated` False, 50 sections) and the not-configured guard. F2 is the
review's headline result — a helm-only bug that the shell-less reviewer traced past. A second pass on
the fixed head follows, per the skill's confirmation step.

## Second pass (fixed head 3851996)

Same two models on the head with the three fixes applied, verifying each fix closed its hole and opened
no other, and attacking what the first pass did not (the both-caps-together case, the next real use, two
runs in a row, boundary values). Both reviewers: **no new code finding.**

| Claim | Codex | Cursor |
|---|---|---|
| SC1 selector cap records only in Coverage; `truncated` is a pure ROW_LIMIT signal; the two are independent | CONFIRMED (ran it — `REAL_SC1A`: 60→50, Coverage/no Truncation, `truncated` False; `REAL_SC1B`: a 5001-binding namespace among the first 50 → BOTH Coverage and Truncation) | CONFIRMED (source; independence table) |
| SC2 render nil-safe across every `namespaceSelector` state; behaviour unchanged when set | CONFIRMED (full helm matrix: default/`=null`/`.label=null` → `""`; undeclared label still exit 1; declared → value; whitespace `"  "` renders literally then `.strip()`s to `""` in app config) | PLAUSIBLE (no shell) |
| SC3 the not-configured guard fires only on the mnemonic path | CONFIRMED (`REAL_SC3_EXPLICIT` succeeds; `REAL_SC3_MNEMONIC` names the config problem) | CONFIRMED |
| SC4 no shared mutable state across two runs; JSON `params` carries `namespaces=None` not `[]` | PLAUSIBLE (the sandbox denied every temp dir, so the full-suite-twice run could not start; `REAL_SC4` state-isolation passed: params + RunContext unchanged, `namespaces: None`) | PLAUSIBLE |
| SC5 boundary values (50/51 mnemonics; 50/51 expanded; comma/unicode; the `(cluster-scoped)` sentinel) | CONFIRMED (none mis-caps, double-counts or crashes; comma/unicode label values are invalid in real Kubernetes so only arise in corrupt data, and the sentinel can't come from an RFC-1123 Namespace name — both handled safely) | CONFIRMED |

**Outcome.** The fixes hold. Codex executed the independence case (`REAL_SC1B`) that Cursor could only
reason about, confirming a report that both selector-caps and row-truncates carries both notes and
neither suppresses the other — so the untested combination Cursor flagged as "a gap, not a hole" is now
demonstrated safe by a real run (no dedicated regression added: the two flags are provably independent
in source, and a 5001-row fixture is disproportionate — review-fixes-stay-simple). CI green on 3851996.
