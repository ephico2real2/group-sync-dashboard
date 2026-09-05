# Review — PR #76, C3 spec: reporting as a microservice

Adversarial second-opinion pass, 2026-09-05, on the ten-claim brief for #76, a specification pull
request: `docs/specs/SPEC_C3_reporting_microservice.md` (5,400 lines, the complete code the R6
implementation will be applied from) replaces the earlier HTML-core-plus-loopback-PDF-sidecar body.
The claims attack the design's premises (oauth-proxy routing, the snapshot data path, the ticket, CSRF,
the PDF library, the chart guards, the dashboard changes, the catalogue SQL, the tests, CI and docs).
Cursor (Grok 4.6 high fast, ask mode, shell and network blocked) traced the spec against the chart
and application on the branch; Codex (gpt-5.6-sol, xhigh) is recorded below when its pass completes.
Every verdict was re-checked here against the spec text before a decision, and accepted corrections
are applied **in the spec body** — the spec stays the single source — with an orchestrator's note
listing them.

## Verdicts — Cursor

| Claim | Cursor | Decision |
|---|---|---|
| C1 oauth-proxy premises (multi-upstream path routing, identity header, `-upstream-ca`) | PLAUSIBLE | **Accepted** — §5.1 now states the ServeMux rule (`/report` without a slash is a 301 to `/report/`, forwarded to neither upstream), the `-pass-user-headers` default the repo already measured, and that `-upstream-ca` is unverified on the shipped tag; Cursor's ServeMux-simulation test rejected (it tests Python's `http.server`, not the proxy) |
| C2 the snapshot data path (temp name + rename, `immutable=1`, access modes) | CONFIRMED | — ; the writer renames atomically and the reader's filename pattern never opens `.tmp`; RWO pins the report pod by required affinity |
| C3 the ticket (HMAC, expiry, viewer binding, shared token via `lookup`) | CONFIRMED | — |
| C4 CSRF on `POST /report/api/runs`; dashboard API stays GET-only | CONFIRMED | — ; the custom ticket header makes the POST non-simple and the service answers 401 without it; no SameSite flag on the proxy cookie (documented, not relied on) |
| C5 fpdf2, its wheels, and the Hummingbird measurement | PLAUSIBLE | **Accepted** — §6.1 requires the `dnf list` re-measure at implementation; Cursor's `pip download` test rejected (a network call in the suite) |
| C6 switches against 0.14.0's rules; the guards; the Service/ServiceMonitor labels | REFUTED | **Accepted** — see below |
| C7 migration 11, leader-only snapshot and pull, usage tier on `/api/dashboard/reports` | CONFIRMED | — ; highest migration today is 8, C2 = 9 and D1 = 10 per the index's reconciliation, so 11 is right at R6 |
| C8 the catalogue's SQL against `SCHEMA` and the `Store` classification strings | CONFIRMED | — ; classification is `Store._FINDING_CASE`/`_FINDING_JOINS`/`_FINDING_WHERE`, concatenated not copied |
| C9 the test helpers the spec names | REFUTED | **Accepted** — see below |
| C10 CI/publish fit, version agreement, citations | PLAUSIBLE | **Accepted on one point** — §11's doc texts cited the deleted filename; corrected; Cursor's filename test rejected (prose) |

## C6 — the render guards printed into the manifests; the Service lacked the monitor's labels

**Finding (Cursor).** `gsd.reportingGuards` said "emits nothing" and then included `gsd.reportPdfVariant`
and `gsd.reportEnabledReports`, which return `pdf/a-2b` and the comma-joined catalogue; included from
both Deployments, the default render would begin each with that text and not be YAML. Separately, the
report Service's labels were `gsd.reportLabels` (the dashboard's `app.kubernetes.io/name`) while the
ServiceMonitor selects `gsd.reportSelectorLabels` (`…-report`): the scrape would find no Service, the
same trap `templates/service.yaml` records for the dashboard. And `monitoring.prometheusRule.for.
reportPull/reportSnapshot` were read by the rules but only mentioned in prose.

**Re-check.** All three read in the spec text: the two `include` lines at the end of the helper; the
Service `labels:` line; the rules' `for:` references at §8.17.13 with the prose-only values sentence.

**Decision.** Accepted. The helper assigns the validating helper's output to `$_` and reuses the
`splitList` it already had; the Service carries both label sets with a comment naming the trap; the
`for` keys are a values block. Cursor's tests (`test_chart_reporting.py` shapes) are the right tests
for R6 and are noted for implementation; nothing renders in a spec PR.

## C9 — the spec named test helpers with the wrong shapes

**Finding (Cursor).** §9.9 said "reusing `render()` and `_config_data()` from `test_chart_strategy.py`"
for document assertions, but `render(**values)` returns `(ok, text)` with `__` for dots; `_docs` is an
instance method; there is no `tests/conftest.py`; the document-list helper is `_render` in
`tests/test_chart_pdb.py`.

**Decision.** Accepted; §9.9 and §9.11 rewritten to name the helpers that exist and where the Playwright
fixture lives. Cursor's `inspect.signature` test rejected: it pins the suite's own helper signatures,
which is not a product invariant.

## Not asked, and what happened to it

- **Cursor N1, `namespace_access.py` imports.** The flagship report constructed `KeyValues(...)` and
  `Note(...)` but imported only `Section, Table`; a Generate would have failed before any SQL. Re-check:
  four constructions, two imports. Accepted; the import line is corrected. Cursor's AST test rejected in
  favour of the R6 suite importing and building the report.
- **Cursor N2, the ServiceMonitor/Service labels** — covered under C6.
- **Cursor, `-upstream-ca` and SameSite as accepted debt** — recorded in §5.1 and operator question 6.

## Verdicts — Codex

Codex reviewed commit `b7011eb` (the checkout moved to the Cursor-corrected head during its run; it
pinned every read to that commit), worked read-only because its sandbox refused the scratch
subdirectory, and cited the exact oauth-proxy commit Red Hat maps to the shipped image tag.

| Claim | Codex | Decision |
|---|---|---|
| C1 oauth-proxy premises | CONFIRMED | — ; agrees with the §5.1 text Cursor's pass added (ServeMux most-specific match, bare `/report` 301) |
| C2 the data path | REFUTED | **Accepted** — the snapshot half is sound; the RWO derivation is not lifecycle-safe (see below) |
| C3 the ticket | PLAUSIBLE | **Accepted** — the verifier ignored `iat`; executing §8.3 accepted a ticket minted 9,000 s in the future; bounded now (30 s skew, 3600 s lifetime), Codex's module and tests applied |
| C4 CSRF; dashboard GET-only | CONFIRMED | — |
| C5 fpdf2 and the Hummingbird measurement | CONFIRMED | — ; wheel names and fpdf2 2.8.8's OutputIntent cited from PyPI and source |
| C6 guards, Service labels | REFUTED | **Accepted** — the same two defects Cursor found, already applied; Codex's regression test is in §9.9 |
| C7 migration, leader-only, usage tier | REFUTED | **Accepted** — "leader only" was too strong: `poller.py` calls leadership best-effort admission control, the check is a cycle old by `_after_poll`; the tail now re-checks before the snapshot and before the pull, §4.1 says so, Codex's test in §9.8 |
| C8 catalogue SQL | CONFIRMED | — ; Codex executed all 33 snapshot queries against the current schema plus migration 11 with no failure |
| C9 the tests | REFUTED | **Accepted** — beyond Cursor's helper-shape finding, §9.7 said an expired ticket is a 403 while §9.11 relied on a 401 to re-mint; `principal()` now answers expiry with 401 and everything else with 403, §9.7 rewritten, Codex's test in §9.7 |
| C10 CI/publish, versions, citations | REFUTED | **Accepted** — §10.2 scanned only the final report image while the repository's own gate scans the pack stage too; the block now builds and scans both and keeps the Hummingbird-blindness check; every remaining code comment cites this file |

### C2 — ReadWriteOnce was not lifecycle-safe for two independently restarting pods

**Finding (Codex).** The design derived `ReadWriteOnce` into a required pod affinity from the report
pod to the dashboard. Affinity is `IgnoredDuringExecution`: it holds only when the report pod is
scheduled. Replacing the dashboard alone can put the new dashboard pod on another node while the
report pod still holds the single-node claim, and the dashboard's own rollout blocks on the attach.

**Re-check.** Kubernetes access-mode and affinity semantics as Codex cited; the reference cluster's
claim is `ReadWriteMany` on `crc-csi-hostpath-provisioner` (measured), so refusing RWO costs the
programme nothing.

**Decision.** Accepted: the guard refuses any mode other than `ReadWriteMany` with the reason; the §2
row, §4.1 and the report Deployment's affinity block follow; Codex's parametrised refusal test is in
§9.9. Codex's rewritten §2 row and §4.1 paragraph were used as the source but re-worded to the spec's
voice.

### Rejected from Codex's pass

Every prose-asserting test (the filename test, the four-record phrase test of the first PR's pattern);
the full §8.7.3 module replacement (only the import line was wrong — Cursor's finding, already
applied). Codex's request to rewrite "How to read" and the first orchestrator's note in its words was
rejected in favour of the orchestrator's own text; the substance (no path to the deleted file) is
applied.

## Second pass — on the corrected head

A ten-claim brief: seven claims that each first-pass correction closed its hole and opened no other,
three the first pass never attacked (the NetworkPolicy, the `immutable` open against the pruner, the
catalogue against the operator's monitoring and PDB decisions). Cursor traced; Codex executed the
ticket module, the poll tail and the JavaScript retry, pinned to the head it was given (`6a9c99e`)
while the Cursor-round commit landed beside it.

| Claim | Cursor | Decision |
|---|---|---|
| C1 the guard helper emits nothing, refusal polarity right | PLAUSIBLE (no render) | — |
| C2 the ticket module's bounds | PLAUSIBLE (no exec) | — |
| C3 one 401 reason, `reportFetch` retries once | CONFIRMED | — ; the compared string is byte-identical to the raised message |
| C4 `is_leader` exists, order preserved | CONFIRMED | — ; `leader.py` `@property is_leader` |
| C5 nothing still derives from `ReadWriteOnce` | REFUTED | **Accepted** — see below |
| C6 §10.2 matches the dashboard's gate; `AS pack` exists | CONFIRMED | — |
| C7 citations resolve | REFUTED | **Accepted** — §7.4 cited `report.py#build` (no such file) and the notes cited the deleted filename in backticks; both reworded; Cursor's prose test rejected |
| C8 the NetworkPolicy | PLAUSIBLE | **Accepted as a live check** — whether the plugin applies policy to kubelet probes is unmeasured; §12 gains the readiness check with the remedy if it fails |
| C9 `immutable=1` against the pruner | CONFIRMED | — ; the writer never rewrites a named copy; one open per run |
| C10 the catalogue against the operator's decisions | CONFIRMED | — |

### C5 — the RWO withdrawal was finished in one place and left open in three

**Finding (Cursor).** Correction 12 refused RWO in the guard and §4.1 but §8.17.1's values comment
still said the data-claim affinity is "DERIVED", §8.17.8 still branched the affinity stanza on
`eq $mode "ReadWriteOnce"`, and §9.9 still told the implementer RWO "adds the podAffinity" while the
Codex test in the same section refuses RWO.

**Re-check.** All three present at the cited lines.

**Decision.** Accepted: comment rewritten, the `$mode` assignment and branch removed (the stanza is
now `with .Values.reporting.affinity`), §9.9's derivation dropped and RWO added to its refusals.
Cursor's test on the spec's own text rejected (prose).

### Verdicts — Codex, second pass

| Claim | Codex | Decision |
|---|---|---|
| C1 guard emits nothing | PLAUSIBLE (sandbox refused the render) | — |
| C2 ticket bounds | CONFIRMED by execution — eight cases, all as claimed | — |
| C3 one 401, one retry | CONFIRMED by execution (`401 then 200` returns, `401 then 401` throws, `403` throws) | — ; its note that a still-expired fresh ticket means the report clock is **ahead** corrected §13's direction |
| C4 `is_leader`, order | CONFIRMED by execution of §8.15.5 with §9.8's construction | — |
| C5 RWO leftovers | REFUTED | **Accepted** — the same three sites Cursor found, fixed in the Cursor round |
| C6 §10.2 matches the gate | CONFIRMED | — |
| C7 citations | REFUTED | **Accepted** — the same two dead citations Cursor found, fixed in the Cursor round; the suite ran green for Codex (961 passed) |
| C8 the NetworkPolicy | REFUTED | **Accepted** — the monitoring peer had only a `namespaceSelector`, admitting every pod in both monitoring namespaces; it now also selects `app.kubernetes.io/name: prometheus`; Codex's test in §9.9 |
| C9 `immutable` against the pruner | REFUTED | **Accepted** — `Snapshot.info()` called `os.path.getsize` after the open; Codex reproduced `FileNotFoundError` on a pruned copy; the size now comes from `PRAGMA page_count * page_size` on the open connection; Codex's test in §9.3 |
| C10 catalogue vs operator decisions | CONFIRMED | — |

**Volunteered (Codex N1, accepted):** the first-pass Service fix wrote `gsd.reportLabels` (which
included `gsd.labels`, the dashboard's name and `app`) *and* `gsd.reportSelectorLabels` into one
mapping — duplicate YAML keys with different values, working only by last-key-wins. `gsd.reportLabels`
now carries the report's selector keys exactly once, the Service uses it alone, CronJobs get their own
`gsd.reportScheduleLabels`, and a strict-YAML test in §9.9 refuses any duplicate key. Codex's N2 and N3
duplicate Cursor's N1 and N2, already applied. Codex's prose citation test rejected.

### Not asked, second pass

- **N1, §9.9's default report count.** The spec said ten names without `login-activity`; with chart
  0.14.0's `loginCapture.enabled: true` the follow yields eleven. Accepted; the sentence states both
  cases, Cursor's env-var test noted for R6.
- **N2, the refresh fingerprint.** The spec added `reportCatalog` and `reportRuns` payloads to
  `refresh()` but not to its fingerprint, so an idle cluster's auto-refresh would never re-render the
  Reports tab. Re-check: the spec had no fingerprint edit. Accepted; §8.15.8 gains the Old/New block
  and a Playwright test description.
- **N3, the clock-skew 401's wording.** A re-minted ticket that is still expired paints the generic
  API-error card. Not a loop (C3). Recorded in §13 as a risk; the dedicated message is a product
  change left to the operator, as Cursor itself suggested.

## The templates note (PR #80)

The operator's requirement that report generation use dynamic templates was recorded as an
orchestrator's note and reviewed on its own five-claim brief. Cursor (read-only) refuted four claims;
Codex is recorded below when its pass lands.

| Claim | Cursor | Decision |
|---|---|---|
| C1 the note against the body | REFUTED | **Accepted** — `render_html` is §8.8 and `render_pdf` §8.9; both already have one helper per block kind, so the change is the HTML move to Jinja2 files and the catalogue staying data-only; §8.8's "No template engine" is the superseded sentence; access-certification's decision columns are data, named as such |
| C2 Jinja2 in the image | PLAUSIBLE | **Accepted** — MarkupSafe is Jinja2's dependency (a C-accelerator wheel, still no `dnf`); the `report` extra, §6.1's inventory, §8.1's "only addition" and `package-data` all follow |
| C3 autoescaping | REFUTED | **Accepted** — `autoescape=True` (boolean; `select_autoescape` would leave suffix-less override keys unescaped), no `|safe`/`Markup`/`autoescape false` on model values, the `<style>` wrapper not overridable, `write_html` banned on the PDF path |
| C4 the override ConfigMap | REFUTED | **Accepted** — a default `Environment` reaches `os.environ` and the HMAC token file from a template; `SandboxedEnvironment` with a data-only context is required, and the override ships only if question 9 is answered yes |
| C5 the tests | REFUTED | **Accepted** — an AST import allow-list replaces the `<`-walk (which false-positives on `n < p.lo` and misses ElementTree or a sidecar file); partial markers plus the §9.6 escape case through an override |

Codex (gpt-5.6-sol, xhigh; read-only, on the head that already carried Cursor's corrections) confirmed
C1 and refuted C2–C5 with measurements:

| Claim | Codex | Decision |
|---|---|---|
| C1 | CONFIRMED at the corrected head | — |
| C2 | REFUTED — two wheels, one native (MarkupSafe 3.0.3 cp314 manylinux); §6.1, §3.3, §8.16 and §9 still said fpdf2 only | **Accepted** — floors `Jinja2>=3.1.6`, `MarkupSafe>=3.0.3` (both verified on PyPI here), the inventory row, and every fpdf2-only passage corrected |
| C3 | REFUTED — a marking beginning with a newline closes the CSS string in `@page { content: "…" }`; HTML autoescape is not CSS escaping | **Accepted** — a `css_string` filter (six-digit CSS escapes) for model values inside `<style>`; the `<script>` case confirmed handled by autoescape |
| C4 | REFUTED — `SandboxedEnvironment` let a template mutate the supplied dict and call public methods; mounted ConfigMaps update live, bypassing a one-time startup check | **Accepted** — `ImmutableSandboxedEnvironment`, cleared globals, `safe` removed, `StrictUndefined`, a detached `json.loads(report.to_json())` context, keys snapshotted at startup into a `DictLoader`, changes need a restart or an atomic swap; ConfigMap writers named trusted authors of report HTML |
| C5 | REFUTED — `data-gsd-partial` markers are self-reported; an override can omit, rename or duplicate them | **Accepted** — a recording loader asserts the exact templates resolved; the exact module list and the §9.5 `Built` loop kept alongside the AST allow-list |

Codex's "not asked": the issue text said eight operator questions (now nine), and the verification
output line still names only fpdf2's version — left as it is, because the proof script §8.16 ships
prints fpdf2's version and the templates add no PDF-side check.

Not asked and accepted: question 9 added to §14 in the same change; §8.1's extra and `package-data`
updated; the ConfigMap value's shape (a name, default empty) and mount path named; `write_html`
forbidden by name.

## Outcome

First pass: Cursor refuted two claims and marked three plausible; Codex refuted six and marked one
plausible. Second pass: Cursor two refuted, one live check added, three volunteered defects accepted; Codex
four refuted (two overlapping Cursor's), one volunteered defect in a first-pass fix accepted, three
claims confirmed by execution. In total
every refutation and named risk was re-checked against the spec text and accepted on the fact, and
applied in the spec body (fourteen corrections listed in its orchestrator's notes, with the tests the
reviewers supplied placed in §9). Rejected: every prose- or history-pinning test, the network-dependent
wheel test, the ServeMux simulation, whole-section rewrites where one line was wrong. Re-validated
after each round: `test_docs_citations.py`, `test_docs_diagrams.py`, `test_specs_index.py`; CI green
on the branch after the Cursor round and re-run after the Codex round. The spec's operator questions
(eight, in issue #67) stay open; the review changed none of them.
