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

Pending; the section is completed when the pass lands.

## Outcome

Cursor refuted three claims, named one risk and volunteered three findings; six accepted on the fact,
one snippet rejected for a measured reason (the OAuth CR's actual rule), one suggestion rejected for
consistency. Re-validated after the fixes: `test_identities_read.py`, `test_config.py`,
`test_migrations.py`, `test_users_tab_logins.py`, `test_api_contract.py`, `helm lint`; CI and the full
suite re-run on the fixed head; CRC redeployed.
