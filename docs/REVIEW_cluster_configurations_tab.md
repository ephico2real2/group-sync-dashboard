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

## Re-validation

Round 1's fixes and the tier: the full hermetic suite, the UI suite (serial) and `helm lint` +
`helm template` with the writes switch off and on. Numbers in the PR comment for the head they ran on.
