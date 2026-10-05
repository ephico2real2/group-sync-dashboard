# Route exposure (PR #45, chart 0.8.0) — adversarial review record

**Target:** `feat/route-kind` at `6ec0320` (three commits: the feature, the redirect-URI matching-rule
citation, the design record). Both reviewers received the same ten-claim brief naming the exact file
and symbol per claim, ran read-only, and wrote to separate files. Every verdict below was re-checked
against a render, the code, or a primary source before being accepted; the disposition column is the
arbiter's, not the reviewer's.

**Baseline measured before the pass:** `cd local-development && .venv/bin/python -m pytest tests/ -q
--deselect tests/test_ui.py --deselect tests/test_live_smoke.py` → `1380 passed`.

## Verdicts

| Claim | Codex | Cursor | Re-check | Disposition |
|---|---|---|---|---|
| C1 `gsd.exposure` is the only gate | CONFIRMED | CONFIRMED | grep agrees: the two flags are read only inside the helper | accepted, no change |
| C2 `route.host` falls back to `ingress.host` | PLAUSIBLE — cannot distinguish pinned from Ingress-required | CONFIRMED mechanics; same trap named | real: a plain-Kubernetes hostname carried onto an OpenShift Route | **fixed**: NOTES names the origin and the remedy; values comments on both keys; test |
| C3 subdomain emitted, `spec.host` absent | REFUTED on the validity half: `fullnameOverride=Bad_Name` renders | CONFIRMED; pre-existing, API rejects | measured: renders; also renders on 0.7.1 for every object | **declined**: not a regression, the API rejects the Service the same way; recorded in the design doc |
| C4 redirect-reference JSON valid for any fullname | REFUTED: `fullnameOverride=x'y` breaks the YAML | CONFIRMED | measured: breaks on this branch, rendered fine on `main` — a regression on a degenerate input | **fixed**: `dict … \| toJson \| quote`; test with `x'y"z`; same-JSON test for ordinary names (keys now sorted, so bytes differ, meaning does not) |
| C5 upgrade transient with `HostAlreadyClaimed` | REFUTED: router admission is path-aware; old Route has path `/`, new has none, both admitted | PLAUSIBLE | `openshift/router` `unique_host.go` compares `Spec.Path`; matches the CRC observation of no refusal | **fixed**: docs now describe path-aware coexistence; the transient claim is withdrawn |
| C6 no SSA annotation on the Route; SSA would strip a server-set host | REFUTED: second half unsupported; old-server fallback populates host | CONFIRMED, "reasoning sound" | the ownership claim had no evidence either way | **fixed**: claim removed from template, README and design doc; old-server caveat added |
| C7 every values sentence true | REFUTED: "fails loudly at install time"; "would claim the same hostname"; "uses it as given"; "stays EMPTY" absolute | CONFIRMED except the C2 comment misleads | `HostAlreadyClaimed` is a status condition, Helm reports success — Codex right on all four | **fixed**: all four sentences, including two pre-existing ones on the Ingress path |
| C8 design-doc render claims | REFUTED on four qualifications | CONFIRMED | same four as C7 plus "unchanged in what it renders" | **fixed**; withdrawn claims recorded in the doc |
| C9 tests pin the behaviour | REFUTED: NOTES, exact error, neither+proxy-off, hostile names untested | CONFIRMED core; seven gaps listed, overlapping | both lists accurate | **fixed**: 10 tests added (NOTES ×4, hostile name ×2, SA/Route Argo annotation, no-SA, neither+proxy-off, exact error) |
| C10 render script derives only on `--set ingress.enabled=true` | REFUTED: unanchored substring match fires on unrelated arguments | CONFIRMED; cosmetic `ingress.host=` empty case | measured: `--set note=ingress.host=x` suppressed derivation | **fixed**: real `--set`/`--set-string` parser, comma-split, whole-pair match; 10 cases pass on bash 3.2 and 5.2 |

## Where the two disagreed, and who was right

- **C4.** Cursor: "valid JSON in single-quoted YAML for any fullname". Codex: refuted with an
  apostrophe. Measured: Codex. A CONFIRMED with no artefact to inspect is the weakest verdict.
- **C5.** Codex read the router source and found path-aware admission; Cursor reasoned about
  work-queues and stopped at PLAUSIBLE. The source settles it: Codex.
- **C6.** Cursor called the SSA inference "sound" and added an immutability argument of its own;
  Codex called it unsupported. Neither produced evidence, so the claim is gone rather than argued.
- **C7/C8.** Cursor found no false sentence; Codex found four, all real. "Fails loudly at install
  time" for an admission refusal is exactly the kind of claim that reads true and is not.

Codex found more, and every one of its findings survived re-checking. Cursor's one distinctive
contribution was a sharper statement of the C2 trap (a hostname "the OpenShift router does not
own"), which shaped the NOTES wording. Two of Cursor's four CONFIRMED verdicts were wrong.

## Declined

- **Validate `gsd.fullname` as a DNS label at render time** (Codex defect 1, first half). Every
  object in the chart carries the same name and the API server rejects them all identically; this
  is 0.7.1 behaviour and out of scope for an exposure change. Recorded in the design doc.
- **Fail the render when only `ingress.host` is set with the Route on** (Cursor defect 1, second
  option). It would break the intended compatibility path for a pinned upgrade. The NOTES signpost
  is the chosen remedy; both reviewers offered it as an acceptable one.

## Cursor invocation

`cursor agent -p --mode plan --output-format text --trust "<brief>"` returned exit 0 and **no
output** on the full brief while answering a one-word probe correctly; `--mode ask` with the same
brief produced the review. The configured model `cursor-grok-4.5-high-fast` was reported unavailable
and rerouted to Auto.
