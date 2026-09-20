# Review record — the Cluster Configurations tab (#230 S2, PR #237)

Branch `feat/230-cluster-configurations-tab`, stacked on `feat/230-cluster-secrets` (S1, PR #235).

**Round 1** on head `1ff9771`: Cursor Grok 4.6 (ask mode, from source) and Codex GPT-5.6 xhigh (a `git
archive` export with the venv; executable probes of the write path, the parser backstop, the YAML twin
and the audit line) both returned **REQUEST CHANGES**. OB3's seat died mid-run on the account's weekly
limit (429 at 43 turns, no report) and is re-run in round 2.

**Between the rounds the gate changed.** The operator ruled this surface cluster-admin only — *"available
to cluster admin view only and not report auditor … we cannot allow auditor view or change this"*, then
*"we can create a new tier boss — look at how argocd does it"* — so both reviewers' C7 (**CONFIRMED**: every
route calls `require_admin_tier`) verified a gate that is no longer the right one. `require_admin_tier` is
the WIDE tier, which `gsd/api.py` itself describes as *"the wide tier that cluster-reader — the deliberate
auditor persona — also passes"*. Round 2 re-reviews the new gate; see C14 in the brief.

## Claims × decision — round 1

| # | Claim | Grok | Codex | Decision |
|---|---|---|---|---|
| C1 | Label/namespace enforcement on every write | CONFIRMED | CONFIRMED (`../victim → 422`, `%2E%2E → 404`, values cluster → 409, foreign Secret refused, `calls=[]` each time) | Holds. |
| C2 | The credential reaches no response, log, row or metric | REFUTED — the pin covers the happy path only; a 422 body is where a handler echoes the request | CONFIRMED on the happy path and its three mutants | **Accepted** on the fact: the pin now drives five refusal paths (422 name, 422 caData, 422 unknown field, 409 duplicate, the connection test) and asserts the token in none of them. |
| C3 | `credential.kind: oauth` refused with the operator's reason, before any I/O | CONFIRMED | CONFIRMED (`validate()`'s first line, the disabled radio and its exact sentence) | Holds. |
| C4 | The request shape cannot express a contradiction | CONFIRMED (parser backstop intact) | REFUTED — `tls: {mode: caData, caData: …, insecure: true}` answered **201** and wrote `insecure: false`; a raw `config` blob was accepted and ignored | **Accepted** — unknown keys are refused by name at `body`, `credential` and `tls`, before any request to the API server. The operator's rule for this surface is that `caData` beside `insecure` is *refused naming both fields*, never normalised. `username`/`password` stay in the shape so the **oauth** refusal keeps its own sentence rather than becoming a shape complaint. |
| C5 | One credential-free audit line per write, naming the person | PLAUSIBLE | REFUTED — with the proxy off, `trusted_viewer` is None, the tier machinery is inert and the write proceeded, audited as `"created by anonymous"` | **Accepted** — the gate refuses a reader with no trusted identity, so every audit line names a person by construction. Folded into the new tier's gate (below), which is where the identity check belongs. |
| C6 | The page's YAML twin equals the Secret the API writes | REFUTED — no equality test exists | REFUTED — measured `yaml_labels {…, True: False}` against the API's strings; `whole_object_equal False` | **Accepted** — every operator-supplied scalar in `ccYaml()` is double-quoted (a label value `true`, `yes`, `8080` or one containing a colon parsed as a YAML bool/int/mapping, and Kubernetes label values are strings), and a UI test now PARSES the pane and compares it field for field with `writer.secret_object(…, redact=True)`. Key order was **not** a defect (both emit `tlsClientConfig` then `bearerToken`) — that half of Grok's C6 is **rejected** as already correct. |
| C7 | The tier | CONFIRMED (`require_admin_tier` on all five routes) | CONFIRMED (targeted run, 2 passed) | **Superseded by the operator's ruling** — see the tier section below. Both verdicts were true of the code as it stood and are no longer the standard. |
| C8 | The writes switch defaults off; off means the routes are not registered | CONFIRMED | CONFIRMED (the default in `Settings` and in `values.yaml`; RBAC exact; mutations caught) | Holds. |
| C9 | The fingerprint and the form's state survive a poll | CONFIRMED | PLAUSIBLE | Holds. |
| C10 | 375 px: nothing past the viewport | REFUTED — the test never mounts a finding, and the findings row is the longest unbroken string the page draws | PLAUSIBLE — same gap | **Accepted** — the 375 test seeds a finding with a long Secret name and a long detail. |
| C11 | `--tab-clusters` contrast | CONFIRMED | CONFIRMED (light 8.897:1, dark 8.669:1, measured with the suite's own `ratio`) | Holds. |
| C12 | `request_discovery()` wakes the thread and `stop()` releases it | CONFIRMED | CONFIRMED (live thread probe) | Holds. |
| C13 | Next real use | — | REFUTED — three: the fake's create→rotate loop, `/version` + `users/~` 401, the clipboard fallback | **Accepted** the connection test (below). **Rejected** the clipboard fallback — the pane's text is selectable and Grok measured the same thing and said "acceptable; do not chase"; a non-secure-context copy is a browser constraint, not this PR's defect. The fake's round-trip is a test-fidelity note recorded for round 2, not a product defect (Codex: "production rotation is safe because Kubernetes returns `data`"). |
| — | The connection test says `reachable` | REFUTED — `/version` is open on OpenShift, so a wrong, expired or revoked token reported a working connection | (same, as C13) | **Accepted** — `reachable` is set LAST, after the credential has been used for something the API server authorises; the order is the assertion, and a test pins `/version` 200 + `users/~` 401 → `reachable: False` with the version still reported. |

## The tier (the operator's ruling, 2026-09-20) — what changed after round 1

Argo CD's model expressed in OpenShift RBAC: a named pair of SAR questions about the objects this surface
exposes. `clusterconfig:view` (`get secrets` in the dashboard's namespace) gates the tab's EXISTENCE and the
read; `clusterconfig:manage` (`create secrets`) gates the four writes and the form's Create / Rotate /
Delete / Test. Measured on CRC 2026-09-20: `cluster-reader` carries **zero** rules covering `secrets`, so the
auditor fails both levels by construction. Fail closed on no identity, no resolver or a resolver that
raised; one resolver and cache per level; `manage` does not imply `view`. A reader without `view` gets no tab
button, no dispatch and **no request** — being refused by a route would itself disclose the surface. The page
no longer defers to the wide tier for this payload (`narrowedOnHost()` left its fetch plan): the route asks
`clusterconfig:view` alone, so a reader the wide tier narrows but this tier admits gets the page the API
would answer. With `view_restrictions_enabled: false` no review is asked for anything, so nothing can tell an
auditor from an administrator and the tier fails closed there too — stated, and the unrestricted tab-walk no
longer includes this tab.

## The design review (OB2, Fable, live SARs on CRC) — between the rounds

OB2 reviewed the tier as designed and **REFUTED** it on two counts, both accepted:

- **The ladder was not ordered (its C1).** Measured on CRC 2026-09-20 with `oc auth can-i --as --as-group`:
  a member of a group bound to `ClusterRole/admin` by ClusterRoleBinding — the lab has seven such —
  answers NO to `list clusterrolebindings` and NO to `update clusterrolebindings` while answering YES to
  `get secrets` and `create secrets` in the dashboard's namespace, because the stock `admin` ClusterRole
  grants `secrets` create/get/list/update and only `roles`/`rolebindings` in rbac. Asked alone, this tier
  would have handed the fleet's credential store — and these writes — to a reader the dashboard holds at
  `self` on every other tab. **The finding was accepted and then the fix was REVERSED by the operator**
  (2026-09-20): *"A user with cluster admin and auditor is fine. That is how Kubernetes RBAC works. As
  long as the user has the role needed or can get the right SAR needed, we are good."* RBAC is additive;
  the SAR is the action's own question; anyone who passes it can do the same with `oc`, and the
  dashboard's ServiceAccount performing the write grants nobody a permission they lack. So each level
  gates on its own SAR alone. The "no auditor" ruling survives by measurement, not composition: the pure
  auditor persona answers `no` to both questions. (OB2's own patch was separately wrong on mechanism —
  it asked the rung through `usage_scope()`, which returns `all` for every viewer under
  `userActivity.visibility: all` and widens under `visibility.enabled: false` — so it would have
  dissolved under exactly the two escape hatches it had to survive.) S2 re-implements nothing: it gates
  on S1's `require_clusterconfig_view` / `…_manage`, and there is one definition.
- **The write path admitted an anonymous caller (its C7).** With `visibilityEnabled: false` and the proxy
  off there is no identity at all, and the write proceeded, audited as `"anonymous"`. **Accepted**, and it
  is S2's to fix: `_writes_gate` refuses a caller with no proxy-verified viewer or with the tier machinery
  off, before the manage level is asked, so every audit line names a person. A test drives all four routes
  in that configuration and asserts nothing reached the API server.

## A gap found on the lab while the seats ran (the coordinator, 2026-09-20)

`GET /api/clusterconfigs` reported **`tls: null`** for four leftover rows on CRC, one of them carrying a
stale `CERTIFICATE_VERIFY_FAILED` — the mode a reader debugging that error needs most. **Accepted on the
fact; the proposed cause was corrected by measurement.** It is not an absent `tlsClientConfig` (a `config`
of `{"bearerToken": …}` reports `{"insecure": false, "ca": "trusted-bundle"}` — measured) but an absent
`config` key, which the reader REFUSES as the finding `config-missing`; such a Secret is therefore never a
cluster, and the null can only be a **retired** row, whose source no longer describes how it was trusted.
Reporting `trusted-bundle` there would invent a fact. So: a listed live cluster always reports its effective
mode (pinned by a test), `tls: null` is documented as "retired only", and the tab renders those rows as
**unknown — its source no longer describes it** rather than a bare dash. The four leftover Secrets are the
earlier validation round's and can be deleted when the lab is free; one of them is what surfaced this, so it
is worth keeping until the walk confirms the rendering.

## #244's CA-experience items, and what this PR does with them

Two of #244's five items were routed here; items 1–3 stay there as reader/API follow-up.

- **Item 5 (`tls: null`)** — done, with the cause corrected by measurement; see the section above.
- **Item 4 (validate the pasted PEM before writing; the connection test does the real handshake)** —
  **already on this head, and tested.** `validate()` refuses `caData` that is absent, not base64, or not a
  PEM, as `ca-data-invalid` naming the field, **before any request reaches the API server** (three
  parametrised cases). The connection test builds its probe client from the entered material —
  `ClusterConfig.verify()` returns `ssl.create_default_context(cadata=…)` — so the handshake is the real
  one, against the pasted bundle. **Deferred to #244**: showing the subject / issuer / `notAfter` the PEM
  resolved to. That needs an X.509 parser, and the image ships none — `cryptography` is not a runtime
  dependency (`pyproject.toml` lists fastapi, uvicorn, httpx, croniter, PyYAML, prometheus-client) — so
  adding one is a supply-chain decision for #244, not a cheap change here.

## The coordinator's own pass on the merged head (2026-09-20, before round 2)

The fork that ran round 1 died on its session limit before launching round 2; this one merged `origin/main`
(#241, #243, #242 — two index conflicts, S2 and T1 both kept, sixteen rows) and read the whole branch
against the operator's rulings before the seats were launched. Findings, each with its test:

| # | Finding | Decision |
|---|---|---|
| K1 | **The CHANGELOG's S2 entry still described the withdrawn ladder** — "the tier is ordered: each level asks the administrator rung first" — the instruction the operator reversed the same afternoon ("each level gates on its own SAR"). The code, API.md's tier section and S1's entry were right; this sentence was not. | **Fixed**: the entry states the no-composition ruling and why. |
| K2 | **`_send` did not redact** the host's own token from an echoed error, where S1's `_get` does (the f3081db rule: redact, then truncate). And no client can redact the token a caller asked us to WRITE, which is in the request body a webhook or proxy can quote on a 4xx — Codex C2 had measured the sentinel in the 502 on round 1 and the round-1 fix covered only the app's own refusal bodies. | **Fixed**: `_send` mirrors `_get`; the writer scrubs every form it put on the wire (the plain token; on rotate the base64 `data.config` blob too — the first run of the new test failed on that form) from `WriteFailed` and the probe's `error`. Four tests: the writer on create and rotate over an echoing host, the real `_send` over an httpx transport that echoes (redacted, then cut), and the API-level pin driving an echoing host into the 502 and an echoing remote into the connection test. All four fail on the round-1 head. |
| K3 | **Rotate replaced an unparseable config** with `{"bearerToken": …}`, dropping `tlsClientConfig`. | **Fixed**: `409 config-not-json`, nothing written; a test with two broken configs and an empty one. |
| K4 | **The twin left label keys unquoted** — `on`/`yes`/`true` are valid keys and YAML booleans. | **Fixed** in `ccYaml()`; the page-vs-API equality test adds the key `on`. |
| K5 | **Hypothesis: a cold `#page=clusters` flashed the refusal card** to an administrator before whoami landed (`ccMayView()` is false until then). | **RETRACTED — refuted by measurement.** A MutationObserver armed from before the first paint (the first version observed `documentElement`, which does not exist when an init script runs, and threw; the second observes `document` until the root appears) counted the refusal's sentence on the UNCHANGED page: zero. The "Loading…" branch and its test were removed again; the page renders as the round-1 head did. |
| K8 | **The twin was equal only once parsed**, not byte for byte: `json.dumps` writes `", "`/`": "`, `JSON.stringify` writes none, and the pane's `config: \|` block adds a trailing newline (round 1 measured `config_bytes_equal False`). The coordinator asked for byte equality. | **Fixed**: compact separators in `secret_object`, `\|-` on the page; the UI test compares `stringData` as strings and the whole document; the writer test pins the exact bytes. Fails on the round-1 head (the label key trips first; the string comparison second). |
| K6 | **Stale "administrator tier" wording** on the routes in `API.md`, the chart README's row, `values.yaml`'s comment, the page's head card and an `api.py` comment — "administrator tier" is this codebase's word for the WIDE tier, which the auditor passes. | **Fixed**: each names `clusterconfig:manage` and the identity requirement. |
| K7 | **The test fake kept `stringData`** where the API server stores `data` (Codex C13, round 1). | **Fixed**: `_Host` folds `stringData` into `data` on every write. |

**The `tls: null` item, re-read against the lab's own record.** The coordinator's message called
`gsd-cluster-tls-default` "live and polling". The S1 lab record (`reports/2026-09-20_cluster-secrets-230/README.md`,
the retired-rows block) lists `crc-tls-default` as `retired=True enabled=False`, and the code path agrees: a Secret
with no `config` key is refused by the parser as `config-missing` (`gsd/clusterconfig/parser.py`), so it is never in
`effective_clusters()`, and `retire_absent_clusters` marks its row `enabled=0` — a retired row does not poll; its
`unreachable` / `CERTIFICATE_VERIFY_FAILED` is the frozen last outcome from before its Secret lost `config`. The
predecessor's decision stands: a live row always reports its effective mode (`ClusterConfig.tls_mode` supplies
`trusted-bundle` when nothing overrides it — tested), a retired row's `tls` is `null` because nothing describes how
it was trusted any more, and the tab renders that as "unknown — its source no longer describes it", never a dash.
Reporting `trusted-bundle` for a retired row would state a fact the store does not hold. If the lab shows that
Secret polling when it is next free, that is a new finding against this reading and the row's `retired` flag is
the thing to measure first.

## Round 2 — four seats on `aac7f4e` (the merged, fixed head)

Cursor Grok 4.6 (ask mode, from source), Codex GPT-5.6 xhigh (an export with the venv; executable probes),
**OB2 — Fable 5.1, Claude Code Agent** (an export; mutants, a driven page, a patch proved on a copy) and
**OB3 — Opus 5** (an export; the deep claims). The brief was written before K5's retraction and still described
a "Loading…" branch and a MutationObserver test on this head; three seats refuted that claim of the brief, not
the head — recorded under C3 below.

| # | Claim | Grok | Codex | OB2 | OB3 | Decision |
|---|---|---|---|---|---|---|
| C1 | Every write behind `require_clusterconfig_manage`, the read behind `…_view`; a revert to `require_admin_tier` fails a test | CONFIRMED | CONFIRMED (five mutants) | CONFIRMED (five mutants run, 4 failed each) | *pending* | Holds. The test was renamed (`…_is_the_manage_level_…`) — round 1's name said "administrator tier". |
| C2 | An identity required — anonymous, or restrictions off: 403 before the API server | CONFIRMED | CONFIRMED | CONFIRMED | *pending* | Holds. |
| C3 | No tab, no request without `view`; the refusal card by URL | CONFIRMED on the surface; REFUTED the brief's "Loading…" claim | same | same, and **one real defect**: `render()` with `data.whoami === null` — a poll whose whoami request failed keeps null — painted the refusal card for an administrator until the next poll | *pending* | The brief was stale against K5 (three seats). **OB2's null-whoami case accepted**: the branch paints "Loading…" when whoami is null (the KPI rule) — a *measured* defect this time, with a test that fails on the head; distinct from the retracted cold-URL flash, which OB2 also measured at zero paints before whoami. |
| C4 | No `restrict` short-circuit, no composition, one definition | CONFIRMED | CONFIRMED (AST: nothing forbidden) | CONFIRMED in the tier; **one composition outside it**: whoami answered `manage: false` whenever `view` was false, so the strip and the routes disagreed for a reader granted `create` without `get` | *pending* | **Accepted**: whoami asks each level on its own; test with a manage-only reader. |
| C5 | Writes only on labelled Secrets in the pod's namespace; the path and the body attacked | CONFIRMED | CONFIRMED (`../`, `%2E%2E`, `%2F`, values, retired, unknown → no write) | CONFIRMED for create/delete; **the rotate body** accepted `metadata`/`stringData` beside `token` and dropped them silently | *pending* | **Accepted**: `_reject_unknown("body", …, {"token"})` on rotate; test. |
| C6 | One audit line per write, naming the person, verb and Secret | CONFIRMED | REFUTED the wording — the lines carry `req.name` / `req.server`, which ARE request fields | CONFIRMED | *pending* | **Accepted on the wording, snippet rejected**: the spec now says "never a credential-bearing field"; Codex's narrower lines dropped the cluster id and the server, which the audit needs. |
| C7 | No credential anywhere, the echo forms included | REFUTED: a JSON-escaped token | REFUTED: JSON-escaped, `< 8` characters, and the 200-character cut happening BEFORE the writer's scrub | REFUTED: the same escaped forms and the short token | *pending* | **Accepted, one redactor**: `kube.redact_text` replaces the raw value and its JSON spellings (once/twice, ASCII and not), longest first; `_send` takes the body's secrets and redacts before truncating; a bearer under eight characters is refused as a typo (no cluster mints one) rather than dropping the floor. Tests: the spellings over an echoing host, a raw-UTF-8 echo, the truncation boundary through the real `_send`, the short token. |
| C8 | The twin byte for byte | REFUTED: `y()` left a raw newline | REFUTED: the same, with PyYAML folding it to a space | CONFIRMED for every value the form can produce; the newline unreachable from an `<input>` and invalid in Kubernetes | *pending* | **Accepted, Codex's snippet**: `y()` is `JSON.stringify` — a JSON string is a YAML double-quoted scalar. And **the layer**: `validate()` refuses label keys and values by Kubernetes' own rules, naming the key (OB2 F4, Grok C16). |
| C9 | `tls: null` retired-only; a live row's effective mode | CONFIRMED | CONFIRMED | CONFIRMED | *pending* | Holds — with the lab record's `retired=True` line cited. |
| C10 | Rotate refuses an unparseable config; the fake stores `data` | CONFIRMED | CONFIRMED (round trip re-parses) | CONFIRMED | *pending* | Holds. |
| C11 | The fingerprint entry; focus survival | CONFIRMED | CONFIRMED | **REFUTED on "which test fails"**: none — a new cluster also changes whoami's `visibility.clusters`, so that repaint rode another payload; a finding-only poll is what the entry alone carries | *pending* | **Accepted**: `test_a_poll_whose_only_change_is_a_finding_repaints_the_tab`, measured to fail on the mutant. |
| C12 | 375 px | PLAUSIBLE (no browser) | PLAUSIBLE (Chromium blocked) | CONFIRMED, plus a 273-character error and a 63/63 chip | *pending* | Holds. |
| C13 | Contrast 8.90 / 8.67 | CONFIRMED | CONFIRMED | CONFIRMED | *pending* | Holds. |
| C14 | The chart and app switch | CONFIRMED | CONFIRMED | CONFIRMED | *pending* | Holds. |
| C15 | The default's exception; no "administrator tier" claim left | REFUTED: `list_cluster_configs`'s docstring | REFUTED: the same, the test name, S1's CHANGELOG phrase | CONFIRMED | *pending* | **Accepted** all three; Codex's grep-test rejected (a phrase test pins prose, not behaviour). |
| C16 | The next real use | 409 on rotate read "unreachable"; a double-click sent two POSTs; a 64-character key reached the wire | 409 is "not a release blocker" | the same 409 (on create too), the double-click, the key; the token stored unstripped | *pending* | **Accepted**: `secret-changed` on a rotate 409, `secret-exists` on a create 409, one Create in flight, labels validated, the token stripped on write. |

**Rejected / routed.** Codex's C3 alternative ("paint Loading on the cold URL") — the cold URL never paints before
whoami (OB2: 0 paints, whoami at 36.9 ms, first paint at 50.6 ms); the null-whoami guard covers the reachable case.
Codex's C6 audit lines — see the row. Codex's C15 grep test — see the row. OB2's "no length floor" on the redactor —
replaced by refusing the short token at validate, so the floor never meets a real credential.

## Re-validation

Round 1's fixes and the tier: the full hermetic suite, the UI suite (serial) and `helm lint` +
`helm template` with the writes switch off and on. Numbers in the PR comment for the head they ran on.
