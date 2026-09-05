# Review — PR #79, C2: Users tab provider allow-list and exact first login

Adversarial second-opinion pass, 2026-09-05, on the ten-claim brief for #79
(`docs/specs/SPEC_C2_users_tab_providers_identities.md` applied; app 0.15.0, chart 0.16.0; the spec's
tests were descriptions and the code was written from them, as its orchestrator's notes record). Cursor
(Grok 4.6 high fast, ask mode, shell blocked) traced the tree; Codex (gpt-5.6-sol, xhigh) is recorded
below when its pass lands. Every verdict was re-checked here — against the code, the OpenShift API's
own documentation and the reference cluster — before a decision.

## Verdicts — Cursor

| Claim | Cursor | Decision |
|---|---|---|
| C1 `fetch_identities` | REFUTED | **Accepted, twice** — see below |
| C2 the poller's identity branch | REFUTED | **Accepted** — see below |
| C3 store predicate, `_user_row`, migration 9 | CONFIRMED | — ; the image's SQLite (3.53.4) builds JSON1 in |
| C4 the API envelope and the tiers | CONFIRMED | — ; a narrowed reader's `total` is 0 or 1 for themselves and cannot reveal an excluded user |
| C5 the chart | CONFIRMED | — ; `rbac.create=false` leaves the read switch on and renders no rule (bring your own grant), as the spec says |
| C6 `_providers_setting` | PLAUSIBLE | **Accepted on the fact, snippet rejected** — see below |
| C7 chips, note, export column | CONFIRMED | — ; an absent `identities_source` (an older server) renders silence, not a wrong sentence |
| C8 fidelity | PLAUSIBLE (no diff) | — ; accounted for here; Cursor's one miss under "not asked" |
| C9 the reference cluster | PLAUSIBLE (no oc) | — ; measured here: `identities_source: off`, `providers_filter: []`, every row `user`, `oc auth can-i list identities` as the ServiceAccount answers `no` |
| C10 what goes red with no code change | REFUTED on one point | **Accepted** — the migration-9 test's `== 9` becomes `>= 9`; the fresh-database test already tracked the maximum |

## C1 — string minimum is not time minimum; lookup-mapped Identities

**Finding (Cursor).** `fetch_identities` kept the earliest Identity by string comparison. The API server
has marshalled `metav1.Time` both as `…:05Z` and `…:05.000000Z` across releases, and between those two
widths `.` sorts before `Z`, so the later instant wins as "earliest". Separately, a provider with
`mappingMethod: lookup` needs its Identity created by an administrator before the first login, so that
Identity's creation time is the administrator's create, and the page would still label it `exact`.

**Re-check.** The comparison was `created < earliest[user]` on the raw strings; the docstring itself
named the lookup case as "before its first mapping".

**Decision.** Accepted. Times are parsed with `datetime.fromisoformat` and compared as instants (the
stored value stays the server's string; an unparsable stamp is skipped); Cursor's mixed-width test
added. The lookup caveat is stated in the docstring and in `docs/DESIGN_users_tab_logins.md` — a
mapping-method-aware label would need the OAuth CR's `mappingMethod` per provider, which the poller
does not read for this purpose; recorded as the caveat the label carries.

## C2 — a transient failure downgraded every row while the status said "ok"

**Finding (Cursor).** On a 503 from the identities API the poller left `identities_source` at `ok`
(correct: a 503 is not a verdict) but wrote the rows with `identity_created=None`, so every row fell
back to the User time. The Users tab then said "First-login times are exact" over rows whose chips
said "approx." — the product's own failure mode, a confident contradiction. The spec's own test
(`test_a_transient_failure_leaves_the_status_as_it_was`) had encoded both halves as intended.

**Re-check.** `replace_users` deletes and re-inserts, so nothing survived from the previous cycle.

**Decision.** Accepted. A transient failure (and a client without the method) now reuses the store's
last-known exact times (`poller._last_known_exact`), so the status and the rows agree; the test is
renamed and asserts the exact time survives. Recorded as deviation (8).

## C6 — the provider-name rule

**Finding (Cursor).** `_PROVIDER_NAME` accepted `!!!`, `foo_bar` and `LDAP`; Cursor proposed a
DNS-1123 subdomain pattern on the assumption that the OAuth CR validates names that way.

**Re-check.** `oc explain oauth.spec.identityProviders.name` on the reference cluster: "a valid path
segment: name cannot equal '.' or '..' or contain '/' or '%' or ':'". Upper case and underscores are
legal. The DNS-1123 form would have refused names OpenShift accepts.

**Decision.** Accepted on the fact, snippet rejected. The rule is now exactly the API's (plus
whitespace, which a comma list cannot carry); the test asserts both the refusals and that `LDAP`,
`foo_bar`, `ldap-local` and `corp.example` pass; Cursor's empty-env-var test added as written.

## Not asked, and what happened to it

- **Cursor N1, `local-development/API.md`** still documented the pre-C2 users envelope — the spec's docs
  list did not name the file. Accepted: the example and prose carry `first_login_source`,
  `providers_filter`, `identities_source` and `identities_source_observed_at`, held by a contract test.
- **Cursor N2, `config.users` placement** — it had landed inside the `userActivity` comment block.
  Accepted; it now follows `unmanagedAudit`.
- **Cursor N3, nil-safe `join`** — rejected as before: consistent with `loginCapture.htpasswdProviders`
  and the ConfigMap's other keys; a replaced `config:` map without `users:` is a values-file error the
  chart reports loudly.

## Verdicts — Codex

Codex (gpt-5.6-sol, xhigh; read-only, on head 5e1a88e, which already carried Cursor's fixes) refuted
six claims and confirmed three; C9 stayed plausible because its sandbox could not reach the cluster.
Every refutation was re-checked here before a decision.

| Claim | Codex | Decision |
|---|---|---|
| C1 `fetch_identities` | REFUTED — an Identity's creation is not universally a login (`mappingMethod: lookup` pre-creates it); and Cursor's mixed-width premise is unsupported: apimachinery's `Time.MarshalJSON` writes fixed-width RFC3339 | **Accepted on both facts; the principal snippet rejected** — see "The Identity time is not called exact" below; the instant comparison kept, its rationale corrected in the docstring, the test and the design |
| C2 the poller's identity branch | REFUTED — a 503 while a new User appeared left `ok` over a page mixing `identity` and `user` rows | **Accepted on the fact, snippet rejected** — see "A mixed page is honest when the note is" |
| C3 store, `_user_row`, migration 9 | REFUTED on the `exact` label only; the SQL mechanics and migration measured correct (SQLite 3.53.0 locally, 3.53.4 in the image, `json_each` present) | **Accepted** as part of the relabel |
| C4 the API envelope and the tiers | CONFIRMED — measured: the predicate reaches rows and both counts, never the never-logged-in line or the detail lookup | — |
| C5 the chart | CONFIRMED — every render measured; the invalid pair exits 1 with the chart's message | — |
| C6 `_providers_setting` | REFUTED — OpenShift excludes only `.`, `..`, `/`, `%` and `:`; spaces and commas are legal names, and the comma-joined ConfigMap key cannot carry `a,b` | **Accepted on the fact, snippet rejected** — see "Every legal provider name travels" |
| C7 chips, note, export column | REFUTED — the `exact` chip and the `ok` note made the C1 assertion | **Accepted** as part of the relabel |
| C8 fidelity | REFUTED — five files outside the body's list were not named by the notes | **Accepted** — deviation (13) names them; Codex's test rejected (a test that greps a spec's prose for file names is a prose-asserting test — the standing rule) |
| C9 the reference cluster | PLAUSIBLE — `oc` denied in the sandbox | — ; measured here under Cursor's pass (above) |
| C10 what goes red | CONFIRMED | — |

## The Identity time is not called "exact" (Codex C1, C3, C7)

**Finding.** OpenShift's `mappingMethod: lookup` requires an administrator to create the Identity (and
the mapping) before the user can log in, so an Identity's `creationTimestamp` is not universally the
first login. The page labelled every Identity time "exact" and the `ok` note said "First-login times
are exact"; documenting the caveat in a design doc while the page asserted the opposite did not
resolve it. Codex proposed never promoting the Identity time at all — `first_login_at` always the
User time, the Identity column retained internally.

**Re-check.** Red Hat's authentication guide, "lookup" mapping: "does not automatically provision
users or identities"; the administrator runs `oc create identity` and `oc create useridentitymapping`.
For `claim` (the default) and `add`, OpenShift creates the Identity at the first successful login, so
there the time IS the first login — and the User's creation time is the earlier of the two for an
administrator-created User, which is the case the feature exists for.

**Decision.** Accepted on the fact, snippet rejected. Removing the promotion removes the feature issue
#62 asks for while the time is the first login for the default mapping methods; the honest fix is the
label. The chip reads `identity`, its title states both cases; the `ok` note describes the source per
row ("the Identity object's creation time where an Identity names the User … the User's creation time
otherwise") and states the lookup caveat; nothing user-facing says "exact" (CHANGELOG, chart README,
values comment, API.md, the specs index, the design). The wire (`first_login_source: identity|user`)
was already honest and is unchanged. Recorded as deviation (14). Codex's two regression tests were
taken in spirit: the UI test asserts the row and the note never say "exact" and that the chip's title
carries the lookup caveat.

**Cursor's mixed-width premise, retracted.** Cursor's C1 said the API server has marshalled both
second and microsecond precision across releases; Codex refuted it at the source, and apimachinery's
`Time.MarshalJSON` was read here: `time.RFC3339`, fixed width. The string minimum was therefore not
wrong for what the API server writes today. The instant comparison stays because it is the operation
the code means and holds at any width or offset; the docstring, the test's name and docstring, the
design and the spec's deviation (7) now say so instead of the refuted reason.

## A mixed page is honest when the note is (Codex C2)

**Finding.** After a successful read, a 503 during a cycle in which a new User appeared produced
`identities_source: ok`, known rows `identity`, the new row `user`. Codex proposed a fourth state,
`error`, with every row downgraded to the User time for that cycle.

**Re-check.** Reproduced as a test (`test_a_user_who_appears_during_a_transient_failure_carries_the_user_time`).
The status row is the last successful read's, including its `observed_at` — the poller does not
rewrite it on a transient — so the note's time is the time the Identities were actually read.

**Decision.** Accepted on the fact, snippet rejected. A mixed page is also the normal `ok` page — a
User whose Identity the read did not return carries the User time — so the defect was the note's
claim, not the mixture; with the note describing the source per row, the mixed snapshot is described
correctly. Downgrading every row on one 503 would make the tab flap on transient failures and would
still be a page the note has to describe. The test above holds the semantics.

## Every legal provider name travels (Codex C6)

**Finding.** `_PROVIDER_NAME` refused whitespace, which OpenShift accepts; the comma-joined ConfigMap
key cannot carry a provider literally named `a,b`. Codex proposed a JSON-array wire form with the
comma form kept for compatibility.

**Re-check.** `oc explain oauth.spec.identityProviders.name` (Cursor's pass) and the OpenShift API
source agree: only `.`, `..`, `/`, `%` and `:` are excluded. The whitespace refusal was mine, added
because the comma list could not carry it — the wrong layer.

**Decision.** Accepted on the fact, snippet rejected. C2 is unreleased, so there is no compatibility
to keep, and a JSON-if-it-starts-with-`[` parser would misread a provider legally named `[x`. The
chart renders `config.users.providers` with `toJson` — a YAML flow sequence, which the settings
loader already parses to a list — and the app accepts a list as it is; the comma form remains for
`GSD_USERS_PROVIDERS` and hand-written files, where a name containing a comma cannot be expressed and
the list form is the answer. The regex is exactly OpenShift's. Tests: the list form carries `a,b`,
`a b`, `LDAP` and a padded `foo_bar`; a non-string entry is a startup error; the chart test passes
`a\,b` and `a b` through `--set` and reads the list back.

## Not asked (Codex)

- **`docs/DESIGN_users_tab_logins.md`'s opening** read "The open The three open questions…" — my
  first edit landed mid-sentence. Accepted and restored; Codex's test rejected (prose-asserting).

## Outcome

Cursor refuted three claims, named one risk and volunteered three findings; six accepted on the fact,
one snippet rejected for a measured reason (the OAuth CR's actual rule), one suggestion rejected for
consistency. Codex refuted six; every fact accepted, four snippets rejected with the reason above (the
feature-removing relabel alternative, the `error` state, the dual-format parser, two prose-asserting
tests), and one of Cursor's premises retracted at the source. A second pass by both reviewers ran on
the fixed head before merge (recorded below when it lands). Re-validated after the fixes: `test_identities_read.py`, `test_config.py`,
`test_migrations.py`, `test_users_tab_logins.py`, `test_api_contract.py`, `helm lint`; CI and the full
suite re-run on the fixed head; CRC redeployed.
