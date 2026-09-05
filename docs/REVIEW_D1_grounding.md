# Review — PR #77, D1 grounded in the reference cluster's OAuth audit log

Adversarial second-opinion pass, 2026-09-05, on the six-claim brief for #77: one orchestrator's note
added to `docs/specs/SPEC_D1_audit_log_login_capture.md`, recording measurements of the reference
cluster's `oauth-server/audit.log` and the parser rules the D1 implementation must follow. The
operator revised the rules mid-review (every attempt is a row, the error captured is what the record
carries, session re-authorisations through the dashboard's own client are kept as their own kind), so
Cursor reviewed the first version of the note and Codex the revised one. Cursor (Grok 4.6 high fast,
ask mode) re-derived the counts from the saved copy of the log; Codex (gpt-5.6-sol, xhigh) is recorded
below when its pass lands. Every verdict was re-checked against the log and the spec before a decision.

## Verdicts — Cursor

| Claim | Cursor | Decision |
|---|---|---|
| C1 the counts | REFUTED | **Accepted** — the 23,220 path-`/` requests are 23,218 `HEAD` and 2 browser `GET`; the 587 username-less denies are 583 authorize and 4 consent requests; every login-shape count reproduced |
| C2 browser-client authorize records are re-authorisations | REFUTED on the justification | **Accepted on the fact, wording changed** — no browser authorize-allow lacks an earlier credential login (0 of 133), but the brief's cookie-expiry explanation was wrong: the pairs arrive 0–4 s after the `POST /login`, the volume matches browser logins, and `values.yaml` says cookie expiry forces a new credential login; the note never cited cookie expiry and now names the measured gaps. The operator's revision keeps these records as kind `session` rather than dropping them |
| C3 CLI logins are the challenging client's authorize | CONFIRMED | — ; `oc login --token` leaves no username record (117 challenge denies without a username) |
| C4 the identity classification | CONFIRMED | — ; every allow resolves to a configured provider; the failed-only unknown names have no User; the mixed-case CLI failure is the same person, so the join is case-insensitive |
| C5 the DN pattern | CONFIRMED | — ; the service identity's name decodes under `ou=TrustedApplications`; the seven LDAP people decode under `ou=People`; HTPasswd names cannot match |
| C6 the D1 body against the note | REFUTED | **Accepted** — see below |

## C6 — the body still says the opposite about CLI providers

**Finding (Cursor).** The note resolves a CLI login's provider from the Identity object, but D1.3's
"WHAT IT CANNOT SAY", D1.7's `/logins` note, D1.9's values comment, the chart README row and the
changelog all say a CLI `kubeadmin` row has no provider and cannot be labelled break-glass, and
D1.10's `test_the_provider_is_read_from_the_browser_path_only` asserts exactly that. The body's
`_coalesce` window is 1 s (`ATTEMPT_WINDOW`), not the 2 s the note named, and would not have hidden
the measured pairs anyway.

**Re-check.** All passages present as cited; `ATTEMPT_WINDOW = 1` in `gsd/loginlog.py`.

**Decision.** Accepted. The note now names every body passage it supersedes with the replacement
sentence, replaces the D1.10 test with one that resolves the CLI provider from the Identity, and
replaces coalescing with the `kind` classification. Cursor's tests are the right R5 tests and are
described in the note; its spec-text tests rejected (prose).

## Not asked, and what happened to it

- **Cursor N1, the pattern field.** The note said the DN pattern matches "the decoded LDAP DN in the
  Identity's `providerUserName`"; for the LDAP provider that field is the raw DN and decoding it fails.
  Accepted: the pattern matches the raw `providerUserName` and the decoded Identity-name suffix.
- **Cursor N2, the service identity's failure.** It had 4 allows and 1 deny; the note said "logged in
  4 times". Accepted: the exclusion drops all of a service identity's records, failures included.
- **Cursor N3, the window.** 1 s, not 2 s. Accepted; the note now says so and that it is irrelevant.
- **Cursor N4/N5.** No `error` decision in this log (the `provider_error` mapping stays unexercised);
  Cursor could not run `oc` and worked from the saved copy — the counts it refuted were in that copy.

## Verdicts — Codex

Codex re-derived every count from the saved log (SHA-256 recorded), cited OpenShift's library-go and
`oc` sources for the challenging-client flow, and reviewed the note after the operator's revision.

| Claim | Codex | Decision |
|---|---|---|
| C1 the counts | CONFIRMED by re-derivation | — |
| C2 browser re-authorisations | REFUTED on the timing | **Accepted** — the note said the pairs arrive 0–4 s apart with one at 18 s; measured: 77 within 1 s, 119 within 2 s, 125 within 4 s, max 20.97 s; every one has an earlier credential allow; the note now carries those numbers and says a 1 s window would have hidden 77 and left 56 as spurious logins |
| C3 CLI logins are the challenging client | CONFIRMED from source | — ; `oc login --token` sets the bearer and calls `whoAmI`, leaving no annotated record |
| C4 the identity classification | REFUTED on one sentence | **Accepted** — the note said the LDAP provider "accepted" the mixed-case login; it was a deny. Case-insensitive attribution is still required, for the failed attempt's row; reworded |
| C5 the DN pattern | PLAUSIBLE (no live oc) | — ; the decode holds on the saved objects |
| C6 the D1 body against the note | REFUTED | **Accepted** — see below |

### C6 — the body still discarded the discriminator and counted two families

**Finding (Codex).** D1.3 keeps the request path without its query and says `client_id` is not stored,
which the `session` kind needs; the body still documents browser-pair coalescing; D1.8 says "two
families" while the note adds a third. Volunteered: the 21 username-bearing consent records
(`/oauth/authorize/approve`) made "every annotated record is a row" contradict "consent is not a login".

**Decision.** Accepted. The note now states the rule as the three admitted shapes, ignores consent
records explicitly, persists only `client_id` from the query for `cli` and `session` rows, names three
families, and carries Codex's four tests in the body's vocabulary for R5. Codex's scope remark (the
branch changes three files, not one: the spec, this record, and the citation test's list) is correct.

## Outcome

Cursor refuted three claims and volunteered three defects; Codex refuted three and volunteered one; all
accepted on the fact and applied in the note, with the operator's mid-review revision (rows for every
attempt, session kind kept, the error as the record carries it) folded in. Re-validated: `test_docs_citations.py`, `test_specs_index.py`; CI
green on every commit of the branch.
