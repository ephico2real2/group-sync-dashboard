# SPEC S4e — the fleet password is presented only as an account the configuration names: the daily ping stops taking its account from a retrieved Secret's history (#432)

| | |
|---|---|
| Programme | Epic C (#383), keep the shared fleet login account safe. A correction to SPEC_S4c's daily ping (§3.4) and its lab walk (§3.12), found while preparing the Epic C lab walk (PR #433) |
| Batch | S — cluster configuration |
| Release | — (post-programme; S4's fifth step, a correction to S4c) |
| Version on release | app 1.4.0, chart 0.59.6 |
| Issue | [#432](https://github.com/ephico2real2/group-sync-dashboard/issues/432) |
| Status | merged |
| Source | OB3's specification of 2026-09-27 (implementer, phase 1: research and the spec, no production code), written from issue #432, PR #433's walk report and its hermetic test, Grok's review of PR #433, OB1-lite's finding N1 on PR #433 (relayed by the orchestrator), SPEC_S4c, SPEC_S4d and main `6740e1e` (application 1.1.0, chart 0.59.3). Revised on round 1 of the spec review (Grok and Codex Astra on `b341697`) with the orchestrator's decisions (Orchestrator's notes). Measured on this machine, and read-only on the reference cluster. §6's blocks were cut from a copy of `6740e1e` with the design implemented, and applied back to a clean clone for the proof in §4 |

## How to read this spec

Each section opens with its point in one bold line; the rest is the evidence. §1 is the whole change in one table.
§2 is what was read and measured. §3 is the design: the rule, the budget over the system, the change, what must not
change, and what is left. §4 maps every test to its result before and after, measured. §5 is the corrected lab walk.
§6 is the change as implementation blocks (`docs/specs/README.md`, "Implementation blocks"), in apply order:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_S4e_ping_account_scope.md . --apply

Line citations into the code at `6740e1e` are plain text, file:line, apart from the maintained `path#anchor`
citations. Upstream sources are cited with the commit they were read at, from the raw file with line numbers.
"Before" and "after" in §3 and §4 are `6740e1e` without and with §6's code blocks, with the same test blocks in both.

**The constraint that overrides everything here** is SPEC_S4c's: nothing in this spec, its tests or its walk logs in
as the fleet account, with a right password or a wrong one. The tests use placeholder names against a fake target;
the walk logs in as the htpasswd `developer` only.

## Orchestrator's notes

- **Phase 2, rebased onto main `b18e62d` (the orchestrator, 2026-09-27).** #434 (#311) changed the import lines
  around writer.py's `from ..config import CONNECTION_KEYS, …` (it added `OK`, `now_iso` and `is_verify_failure`), so
  that block's seven-line Old text no longer matched. It is narrowed to the one line it changes, `CONNECTION_KEYS`
  → `CONNECTION_MODE_KEYS`, with the same meaning. Main also already has a `## Unreleased` section (#311's and
  #314's entries), so the CHANGELOG block is now an insert after that heading, with the bullet's text unchanged.
  Nothing else in the blocks moved.

- **The id, and why a file of its own.** S4's steps take the next letter in the order they are specified (S4a #283 …
  S4d #315), and this corrects S4c's ping, so it is S4e. It is a spec of its own, not a section of SPEC_S4c, because
  `local-development/apply-spec-blocks.py` checks and applies every block in a spec file: S4c's 102 blocks are on main
  already, so their Old texts no longer occur, and a block added to S4c could never be applied by the tool. S4d set
  the precedent.
- **The versions are the orchestrator's.** The brief: "the fix takes the next free MINOR at merge; the orchestrator
  sets the number". As for 1.1.0 (`c867bc6`), the release commit beside the implementing commit moves `pyproject.toml`,
  `gsd/__init__.py` and `appVersion` to the next MINOR, and the chart by the PATCH that move takes; no block here
  touches them. The PR needs that commit: `local-development/check-app-version-bump.py` requires the next MINOR for a
  change under `gsd/` (#427), and CI's `version-bump` job (`.github/workflows/ci.yml`) refuses a change under `charts/`
  — `CLUSTER_CREDENTIALS.md` here — without a new `Chart.yaml` version.
- **A citation in the brief, corrected.** "The only username override from `lookup_account` is the ping (poller.py:1794
  at main 6740e1e)": at `6740e1e` the override is poller.py:1801; poller.py:1794 is its line at 1.0.0 (`05e32c8394`),
  the tree PR #433's reviewers read. The claim holds: `grep -rn 'ldap_connection_bootstrap=' local-development/gsd/`
  finds it and four sites that set `None` or parse a declaration.
- **The walk report's own test pins the defect.** reports/2026-09-27_epic-c-walk/hermetic/test_walk_password_scope.py
  (PR #433, at `6545292`) asserts 1.0.0's behaviour: its first test expects the fleet account to be sent the walk's
  passwords. Measured: on `6740e1e` its 4 tests pass; with §6's code, the first test's two cases fail
  (`assert [] == ['walk-placeholder-2', 'walk-wrong-3']`) and the self-login cases pass. It measures 1.0.0 and says
  so; whether the report keeps it as history or marks it is PR #433's decision.
- **The scope input from OB1-lite's N1 on PR #433 (the orchestrator, 2026-09-27).** The lookup and self-login pair a
  stanza's `ldapConnectionBootstrap` with the one password too: say whether that is covered by the rule, how the
  dashboard can know, and name all three paths in the budget. Answered in §2.4 and §3.5, and pinned by
  `test_the_lookup_and_self_login_present_the_account_their_stanza_names`. The feature that lets a stanza name its own
  account is kept whole (#291's rule, "No feature … is removed, renamed, narrowed or deprecated", applied by the
  orchestrator).
- **#369 stays parked.** A credential per account — the issue's option (b) — is #369's agreed end state, parked by the
  operator on 2026-09-25 ("Do not start either without the operator picking it up"). This spec does not build it.
- **Round 1 of the spec review, on `b341697` (Grok and Codex Astra; the orchestrator's decisions).** Each accepted fix
  was traced against the raw code before it was taken, and where the two reviewers offered different fixes the smaller
  one that closes the finding was taken.
  1. **Codex C2, accepted: a hole in the filter.** `b341697` trusted a ConfigMap output's `lookup-account` because the
     owner digest names the declaration's account — but nothing compares that account with the annotation, so an
     output whose annotation alone was edited to the fleet account passed discovery and was pinged as it (reproduced
     by Codex through real onboarding discovery, and here: §4). Now discovery carries the accepted declaration's own
     `ldapConnectionBootstrap` onto the output, and the allowed set reads that field, never the annotation (§3.1).
     Codex's block also carried the chart default; the explicit value alone is taken, since the chart's username is
     already allowed and a default must never become a field. `test_configmap_digest_does_not_authorize_a_changed_lookup_annotation`.
  2. **C4 (i), both reviewers, accepted: a Secret-declared stanza keeps its account.** Retrieval kept the mode keys'
     removal but now keeps an explicit `ldapConnectionBootstrap`, and the parser accepts it beside the token on a
     retrieved Secret only; a Secret that named no account gains none (§3.1). Codex's shape (the key stays in
     `config`) is taken over Grok's (a new `declared-account` annotation): fewer lines, no new annotation, and one
     field — `ldap_connection_bootstrap` — carries every declaration. `test_secret_retrieval_preserves_only_explicit_intent[True|False]`.
  3. **C4 (ii), both reviewers, accepted: an account no longer named stays on the tab and in `/metrics`.** Members are
     kept: an undeclared account's Lease is read and served, and the sweep returns before it reads a password or takes
     any authentication action (§3.1). That return is also the whole ping filter (the trace findings below). Its
     staleness can keep the documented alert on — shipped behaviour kept; changing the alert is a separate decision
     (§3.5). Grok's alternative, a `named` flag that keeps the gauge off such accounts, changes the metric and is not
     taken. `test_historical_refusal_stays_visible_without_reading_password`, and
     `test_an_account_no_longer_named_remains_visible_without_a_login` replaces `b341697`'s served-view test.
  4. **Codex C3, accepted: a wording correction.** The Lease holds one `refused` record, not a history: the bound is
     the latest refused digest (§3.5). The lifetime wording is removed from this spec, the stanza documentation and the
     CHANGELOG block. No durable history is built. `test_rotation_replay_contract_matches_the_lease` and
     `test_secret_recreation_rearms_a_fresh_process`.
  5. **The §3.2 table, both reviewers, accepted:** a leader change between the Lease read and the claim; an undeclared
     account with an existing ping digest; one with a saved refusal; case variants (exact-string scope); and the old
     replica's snapshot (a stated deployment requirement, not a fence). One test each (§4).
  6. **Codex, accepted: a trailing newline.** `user\n` passed the username rule through `.match()`, whose `$` matches
     before a final newline; the rule now uses `.fullmatch()`. `test_account_spelling_contract`.
  7. **§2.5 (Grok, Codex C5), accepted:** (a) is rejected because it narrows shipped pings (#291), not because (d) is
     smaller — (d) is larger in code.
  8. **Codex C7, accepted in part:** the corrected walk re-checks the live lab, read-only, immediately before every
     step that places a password, and stops unless nothing else names the fleet account (§5). Codex's offline helper,
     `check-ping-walk.py`, and its test are **not taken**: they read saved inventories ("not live rollout completion",
     Codex's own words), where three read-only `oc … | jq` counts in the walk check the live lab with no new file.
  9. **C8, both reviewers, accepted:** each new method's docstring is one short line of why; each section leads with its
     plain point; §2.1's second list of line numbers is cut to what the design rests on.
  - **Declined, with the reason:** Codex's `test_spec_states_exported_suite_limits_and_compatibility` asserts that
    reviewer's sandbox numbers (`3 failed, 5473 passed`, from an export with no `.git` and no loopback sockets), and
    §4's suite runs in real clones where those tests run; `test_new_declaration_helper_has_one_line_why` tests a
    docstring's length, and the rule is applied directly; `test_continuous_false_password_is_shared_by_all_paths`
    was not among the accepted tests — the shared-refusal statement rests on SPEC_S4c's B2 and on this spec's pin;
    Grok's leader-change and case-variant tests duplicate Codex's, which are taken.
  - **A trace finding on a taken test:** the three contract tests (4 and 5) searched the whole spec file for their
    phrases, but §6 quotes the test file, so the phrases were always present and the check was vacuous. They now read
    only the prose before §6's heading, and fail if that heading is missing. Against `b341697`'s prose all three fail
    (`3 failed`, each on its phrase); against this spec's, they pass.
  - **Two trace findings on taken code; both leave the code smaller.** (i) Codex's poller block filtered `targets` on
    the declared set *and* returned early for an undeclared account (Grok's block had the filter alone). `targets` is
    read only after that return, so the filter could not change an outcome, and it is not taken: one check, in one
    place. (ii) Codex's parser exemption carried `and oauth is None`. A Secret with both a token and `oauth` is refused
    by the very next check (`credential-ambiguous`, the accurate reason), so the clause changed only which refusal is
    reported, and it is not taken. Measured: putting either back fails none of the 386 fleet tests, while each of the
    twelve reverted decisions fails at least one (§4).
  - **Migration, measured (Codex C4's limit).** Secrets retrieved before this change lost the difference between an
    explicit and an inherited account. Measured read-only on the reference cluster, 2026-09-27T15:48:02Z: of six
    cluster Secrets one is retrieved, `gsd-cluster-shared-rnd`, created by the lookup for a values stanza
    (`managed-by: sa-token-lookup`), whose `lookup-account` equals the chart's username; no retrieved Secret came from
    a Secret-declared stanza, no Secret's `config` carries `ldapConnectionBootstrap`, and there is no onboarding
    ConfigMap. No case exists on this lab (§3.5).

## 1. The point, in one table

**The daily ping sent today's password as yesterday's account; now the password is presented only as an account the
configuration names, and an account it no longer names is still shown but never pinged.**

| | |
|---|---|
| **What goes wrong** | The ping logs in as the account a retrieved cluster's Secret *recorded* when its token was fetched (`groupsync-dashboard.io/lookup-account`). Its password is the one Secret the configuration names *today*. When the account changes, the ping sends today's password as yesterday's account: a refused login, counted against that account's directory entry. |
| **Where it was found** | Preparing the Epic C lab walk (PR #433): SPEC_S4c §3.12 steps 2–3 would have sent the fleet account `developer`'s password, then a wrong one. Measured hermetically: 2 refused logins, 3 with a restart. Not run on the lab. |
| **The rule** | A password is presented only as an account the configuration names for it now: the chart's `fleetAccount.username`, or a declaration's `ldapConnectionBootstrap` — on every path: the lookup, self-login and the ping. |
| **The change** | The ping reads the password, and logs in, only for an account a declaration names (`gsd/poller.py#Poller._declared_accounts`); every other account is still listed from its Lease, with no password read. A Secret-declared stanza's explicit account survives retrieval; a ConfigMap output's account comes from its declaration; a username with a trailing newline is refused. |
| **What does not change** | The ping's budget (once per account per interval) and its stand-down; #283's login rules; the lookup; self-login; the tab's rows and the metrics; RBAC; every chart value and template. |
| **What it costs** | Nothing on the reference cluster (§2.1). A Secret-declared stanza retrieved *before* this change has lost whether it named its account; if one exists elsewhere, its account is no longer pinged until it is declared again (§3.5). |

## 2. Read and measured

### 2.1 The code at `6740e1e`: three paths, one password, one path with the wrong account

**The lookup and self-login take their account from the configuration as it is; the ping takes it from an
annotation written at retrieval.**

| path | where | the account it presents | the password |
|---|---|---|---|
| the lookup | fleetlookup.py:417-418, called by `_retrieve_pending` (poller.py:1629-1633) | `fleet_account(settings, cluster)`: the stanza's `ldapConnectionBootstrap`, else the chart's username (fleetlookup.py:235-242) — the pending declaration, now | `fleet_password` (fleetlookup.py:245-269): ONE Secret, for every account |
| self-login | selflogin.py:131-132 | the same function, on the self-login stanza | the same |
| the ping | poller.py:1711-1717, :1801 | `c.lookup_account`: the annotation the lookup wrote when it stored the token (fleetlookup.py:365-366; writer.py:157 for a values stanza's new Secret, :364 for a declaring Secret), read back by the reader (reader.py:94-95), never revised | the same |

Three facts the design rests on, each read from the raw file:

- **Retrieval removes a Secret's declaration.** `store_lookup` pops every `CONNECTION_KEYS` key,
  `ldapConnectionBootstrap` included (writer.py:353-354). The annotation is then the only record of the account.
- **A values stanza survives beside its Secret.** It stays in `Settings.clusters`, but `ClusterRegistry.merge` serves
  the Secret in its place (registry.py:99-102), without the stanza's `ldapConnectionBootstrap`.
- **A ConfigMap output's owner digest includes the account, but not the annotation.** The digest carries
  `cluster.ldap_connection_bootstrap or settings.fleet_account_username` (onboarding.py:59-60); the output matches on
  owner, URL, token kind and TLS (onboarding.py:156-162), and nothing compares its `lookup-account` with the account.

The reference cluster, read-only (`oc get`, the handed kubeconfig), 2026-09-27T13:54:37Z and 15:48:02Z:

| object | value |
|---|---|
| the Deployment | 1 replica, `Recreate`, `quay.io/ephico2real/group-sync-dashboard:1.1.0` |
| `gsd-cluster-shared-rnd` | `resourceVersion` 2835139; `token-source: remote-lookup`; `lookup-account: ocp-oauth-bind-serviceid`; `managed-by: sa-token-lookup`; `config` keys `bearerToken`, `tlsClientConfig` |
| the other cluster Secrets | `gsd-cluster-mock-*` (four) and `gsd-cluster-shared-qa`: no `token-source`, no `lookup-account`, no `ldapConnectionBootstrap` |
| onboarding ConfigMaps | none |
| the fleet account's Lease, `gsd-fleet-666f1ba7f2fdead0` | `ping-last-attempt` = `ping-last-ok` = `2026-09-27T10:27:05Z`, outcome `ok`, target `shared-rnd`, holder `""`: unchanged by #431's release, whose restart did not ping again (B3) |
| the ConfigMap | `fleetAccountUsername: "ocp-oauth-bind-serviceid"`, the password Secret `openshift-config/ldap-oauth-bind-secret` key `bindPassword`, `fleetPingEnabled: true`, `fleetPingIntervalSeconds: 86400`, `discoveryIntervalSeconds: 300` |

### 2.2 Who counts a refused login, and against what

**The directory counts a refused login on the entry the LOGIN NAME resolves to, so another account's password sent
as the fleet account is a failure on the fleet account's own counter.**

| source | what it says |
|---|---|
| openshift/oauth-server, pkg/authenticator/password/ldappassword/ldap.go at `0a5bbfd` | lines 98-105 bind as the identity provider's `bindDN` to search, and line 100 says what a failure there means: "If the configured bindDN/bindPassword encounters errors, that blocks all logins". Lines 108-112 build the filter `(&<filter>(<attribute>=<login name>))`. Line 151, `l.Bind(entry.DN, password)`: the presented password is bound **as the entry the login name found**. Lines 154-167: codes 48 and 49 become a 401, anything else an error (a 500) |
| OpenShift docs, modules/identity-provider-about-ldap.adoc at `270ee60` | lines 12-13: "a simple bind is attempted using the distinguished name (DN) of the entry plus the provided password". Lines 41-45: the `attribute` a login name is matched against is each identity provider's own `url` setting |
| OpenLDAP, `slapo-ppolicy(5)` | `pwdFailureTime` "contains the timestamps of each of the consecutive authentication failures made upon attempted authentication to this DN (i.e. account)"; at `pwdMaxFailure` failures, with `pwdLockout` set, "the account may be locked" |
| Red Hat Directory Server 12, *Managing access control*, ch. 4 | "Directory Server maintains the lockout information in the following attributes of the user entries: `passwordRetryCount`: Stores the number of failed bind attempts" |
| this repository | the lab's directory is OpenLDAP (`docs/ACCESS_CONTROL.md`); a locked 389-ds account answers code 19, which the oauth-server turns into a 500 (SPEC_S4a §3.1, `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md`) |

**Decides:** sending account A's password as account B adds one failure to B's counter, whatever cluster it is sent
to. On the reference cluster the fleet account is the identity provider's own bind account (SPEC_S3 §3.1; its
password Secret is `ldap-oauth-bind-secret`, key `bindPassword`), and ldap.go line 100 says what its lockout is:
every login blocked.

### 2.3 What the conventions say about a credential's subject

**Everywhere, one password belongs to one principal, and the pairing is written down — beside the reference, or in
the Secret.**

| source | what it says |
|---|---|
| Kubernetes, content/en/docs/concepts/configuration/secret.md at `ce7891d`, lines 314-319 and 333-337 | the `kubernetes.io/basic-auth` type is "for storing credentials needed for basic authentication": `username`, "the user name for authentication", beside `password`; the type "sets a convention for what key names to expect" (it requires one of the two keys, not both) |
| OpenShift, modules/identity-provider-ldap-CR.adoc lines 50-52 and modules/identity-provider-ldap-secret.adoc line 23, at `270ee60` | `bindDN` "Must be set if `bindPassword` is defined", and the reverse: one DN, one password reference, paired in configuration; the Secret holds only the key `bindPassword` |
| External Secrets Operator, docs/guides/common-k8s-secret-types.md at `e95365a`, lines 51-55 | an `ExternalSecret` renders the Secret type its template names; its registry example composes `username` and `password` into one credential |
| this chart: `values.yaml` (`clusterConfig.fleetAccount`) and `docs/CHANGELOG.md` (chart 0.49.0) | `fleetAccount.username` with `passwordSecret`, "Its password" — OpenShift's pairing; a stanza's `ldapConnectionBootstrap` "names the username while the password stays this one" |
| the operator's end state, #369 (parked 2026-09-25) | a stanza may name a DEDICATED credential Secret (`username` + `password`) for a cluster with a different account; a missing one is a finding and never falls back to the global one |

**Decides:** no convention lets one password stand for several principals. So the dashboard can know whose password
it holds from exactly two sources: the configuration's pairing, or a login. A login is the act this spec rations, so
the rule is stated over the configuration.

### 2.4 The scope question: is a stanza's own account covered? (OB1-lite's N1)

**Yes, as a declaration. The lookup and self-login already obey the rule; the ping is the only path that breaks it.**

- **Covered.** A stanza's `ldapConnectionBootstrap` is one of the two places the configuration pairs an account with
  the password Secret: the chart documents that the stanza "names the username while the password stays this one".
  The lookup and self-login present the password only as the account the cluster's declaration names now
  (fleetlookup.py:417; selflogin.py:131).
- **How the dashboard knows.** Only from that declaration. The other source is the directory's answer to a login
  (ldap.go line 151). OB1-lite measured the lookup and self-login each presenting the one password as a stanza's
  account — the declaration honoured, as documented.
- **What a false declaration costs.** A stanza that names an account whose directory password is not the Secret's is
  refused by the directory, and then every path stands down while that password is the latest one refused on the
  account's Lease (SPEC_S4c's B2). That is the same cost as a wrong password typed into the Secret, which the dashboard
  cannot tell apart without the same login. The exact bound is in §3.5.
- **The ping is different in kind.** Its account is not a declaration at all. `lookup-account` records who fetched a
  token, under the configuration of that day, and nothing revises it (writer.py:157 and :364; reader.py:95). So the
  ping is the only path that presents the password as an account no current declaration names.

### 2.5 The options, measured against the rule

**(d) is chosen because it keeps every shipped ping, not because it is small: (a) is fewer lines, and is rejected
because it drops pings the chart ships (#291).**

| option | holds the rule? | what it costs | decision |
|---|---|---|---|
| (a) ping only the chart's `fleetAccount.username` | yes, for the ping | one comparison — fewer lines than (d). It stops the ping for every account a stanza names that differs from the chart's (`docs/CLUSTER_STANZA.md` §4, row 8: a per-cluster bootstrap account) and for a release with no chart username (`values.yaml`: "Empty = every mode stanza must name its own ldapConnectionBootstrap"); measured on a mutant, the values-stanza and ConfigMap guards fail. It narrows a shipped feature (#291) | rejected |
| (b) a password Secret per account | yes | #369's end state, parked by the operator; a new stanza key in three places; a `get` grant per Secret, so the dashboard ServiceAccount's permissions change | not built |
| (c1) record the account on the password Secret | yes | the Secret is not the release's (`values.yaml`: "The chart does not CREATE it"); on the reference cluster it is the identity provider's `bindPassword` Secret, which the dashboard may only `get`. A required new key needs a migration and each owner's agreement | rejected |
| (c2) ping only when the same account and password digest has succeeded before | yes | a newly rotated password has no success yet, so the ping could never confirm a rotation — B3's point. Remembering an account's older success would not vouch for today's password either | rejected |
| (d) present the password only as an account the configuration names now | yes, on every path | more code than (a): the allowed set, a retained Secret key, a carried ConfigMap field, and history kept on the tab | **chosen** |

## 3. Design

### 3.1 The rule

**The fleet password is presented only as an account the configuration names for it now. An account the
configuration no longer names is still shown, from its Lease, and never pinged.**

The configuration names an account for the password in exactly these places, which
`gsd/poller.py#Poller._declared_accounts` collects:

| where | why it counts |
|---|---|
| `clusterConfig.fleetAccount.username` | the chart pairs it with `passwordSecret` |
| `ldapConnectionBootstrap` on an enabled stanza that declares a mode — values, Secret or ConfigMap; for a values stanza, also after its cluster is retrieved | the stanza names the username; the password stays the chart's |
| `ldapConnectionBootstrap` a retrieved Secret kept | retrieval now keeps an explicit one (it used to strip it); a Secret that named no account gains none, so a chart default never becomes a field |
| `ldapConnectionBootstrap` discovery copies from an accepted ConfigMap declaration onto its output | the output's own annotation can be edited without touching the owner digest, so the declaration is read, never the annotation |

Not a place: any `lookup-account` annotation. It is provenance — who fetched a token, under the configuration of that
day.

**Monitoring is not authentication.** The sweep still reads the Lease of every account a retrieved Secret records,
and serves its view on the tab and in `/metrics`. For an account the configuration does not name, it stops there:
it does not read the password, seed the gate, stop sessions or claim the Lease.

How each path holds the rule:

| path | how |
|---|---|
| the lookup | unchanged: `fleet_account(settings, cluster)` of the pending declaration, which is one of the places above |
| self-login | unchanged: the same, on the self-login stanza |
| the ping | new: the sweep reads the password and pings only for an account in `_declared_accounts()`; for any other it serves the Lease's view and stops there |

### 3.2 The budget over the system

**Measured: an account the configuration no longer names is sent nothing, on every event in scope; the one
remaining wrong login is a false declaration's, as before.**

*Now* means the configuration the process loaded: its values and the Secrets and ConfigMaps its last discovery read.
It is not a transaction across replicas or with an operator's edit. The property, with its scope: *a login presents
the fleet password only as an account the process's configuration names for it — per process, per replica, across a
restart, a Secret rotation, a username change, and a stanza added, removed, renamed or disabled.* The unit is SPEC_S4c's:
an authorize request on the wire, counted by a fake target in front of a fake directory that accepts an account's own
password, refuses any other, and records its verdict when the request arrives.

Each row starts from the lab as found: the chart names FLEET, the Secret holds FLEET's password, and shared-rnd was
retrieved as FLEET and pinged once. Each cell is (sent to an account the configuration no longer names, sent to a
named account with a password that is not its own), before → after (`test_the_pairing_budget_over_the_system`):

| event | before | after |
|---|---|---|
| a username change: the chart names OTHER, the Secret holds OTHER's password | (1, 0) | **(0, 0)** |
| … then a restart | (1, 0) | **(0, 0)** |
| … then a second process on the same Lease | (1, 0) | **(0, 0)** |
| … then OTHER's password rotated | (2, 0) | **(0, 0)** |
| a stanza that named STANZA removed, then the fleet password rotated | (1, 0) | **(0, 0)** |
| that stanza's `ldapConnectionBootstrap` changed, then a rotation | (1, 0) | **(0, 0)** |
| that stanza disabled, then a rotation | (1, 0) | **(0, 0)** |
| a stanza added that names an account whose password the Secret does not hold (a false declaration) | (0, 1) | (0, 1): the lookup presents it once, then every path stands down (B2); unchanged |
| the named account's own password rotated | (0, 0) | (0, 0): one confirming ping (B3); unchanged |

The events the review added, one test each:

| event | before → after | test |
|---|---|---|
| leadership moves between the Lease read and the claim | FLEET sent OTHER's password once → only OTHER, once: the stale read's claim meets the 409 | `test_leadership_changes_between_read_and_claim` |
| the undeclared account's Lease already holds a ping digest, and the interval has passed | FLEET pinged → not pinged | `test_lease_already_records_ping_digest_for_undeclared_account` |
| the undeclared account's Lease holds a refusal | the password read for it → not read; the row and `gsd_fleet_account_suspended 1` served, the Lease unchanged | `test_historical_refusal_stays_visible_without_reading_password` |
| an account's `lookup-account` edited on a ConfigMap output | the edited account pinged → not pinged | `test_configmap_digest_does_not_authorize_a_changed_lookup_annotation` |
| two spellings of one name, `user` and `User` | two accounts, two Leases, each refused once → the same: exact-string scope, stated | `test_account_spelling_contract[User]` |
| a username with surrounding whitespace, or a trailing newline | `user\n` accepted → refused; spaces and tabs refused both ways | `test_account_spelling_contract` |
| an old replica still names FLEET while a shared password Secret is repurposed for OTHER | it sends OTHER's password as FLEET, before and after: the filter cannot revoke another process's loaded configuration. Drain old processes before repurposing a shared password Secret, or give the new account its own Secret reference — a deployment requirement, not a fence | `test_old_replica_still_uses_its_loaded_declaration` |

And the Definition of Done's own shape — the corrected §3.12 walk, two accounts and one password Secret: the fleet
account is sent the walk's passwords 2 times in one process and 3 times with a restart before; **0** after
(`test_the_walk_presents_nothing_as_the_fleet_account`).

The same budget, by path — all three, as the orchestrator asked:

| path | presents the password as | measured by |
|---|---|---|
| the lookup | the account its pending declaration names — unchanged | the "stanza added" row (1 → 1, then gated); `test_the_lookup_and_self_login_present_the_account_their_stanza_names` |
| self-login | the account its stanza names — unchanged | the self-login walk test with the ping on (every authorize is the walk account's, 5 of 5); the pin above (gated after the lookup's refusal: 0 more, a restart included) |
| the ping | an account the configuration names — **new** | every other row, and the walk test (2 and 3 → 0) |

### 3.3 The change, file by file

**Five small code changes and the documents that describe them.**

| file | change |
|---|---|
| `local-development/gsd/poller.py` | `_declared_accounts`; `_ping_accounts` keeps every account on the tab and, for one the helper does not hold, stops before it reads the password |
| `local-development/gsd/clusterconfig/onboarding.py` | an accepted declaration's `ldapConnectionBootstrap` is copied onto its output |
| `local-development/gsd/clusterconfig/writer.py` | `store_lookup` pops the mode keys only, so an explicit `ldapConnectionBootstrap` stays |
| `local-development/gsd/clusterconfig/parser.py` | the key is accepted beside a `bearerToken` only on a Secret annotated `token-source: remote-lookup`; everywhere else it is refused as before |
| `local-development/gsd/config.py` | `valid_bootstrap_username` uses `.fullmatch()` |
| `local-development/tests/test_fleet_lifecycle.py` | the harness names USER on the chart, since only declared accounts are pinged |
| `local-development/tests/test_fleet_lookup.py` | the declaring Secret's retrieval now keeps its explicit account |
| `local-development/tests/test_ping_account_scope.py` | new |
| `docs/specs/SPEC_S4c_credential_lifecycle.md` | §3.4's "Which target", §3.12 rewritten (§5), a note |
| `docs/CLUSTER_STANZA.md` | the `ldapConnectionBootstrap` row; §6 names the retained key |
| `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md` | the ping's account rule, and that history stays shown |
| `local-development/API.md` | the `fleet` block lists history too |
| `docs/CHANGELOG.md` | the `## Unreleased` entry |

Lines added and removed, measured on the applied tree:

| file | added | removed |
|---|---|---|
| `local-development/gsd/config.py` | +1 | −1 |
| `local-development/gsd/poller.py` | +14 | −2 |
| `local-development/gsd/clusterconfig/onboarding.py` | +3 | −1 |
| `local-development/gsd/clusterconfig/parser.py` | +5 | −2 |
| `local-development/gsd/clusterconfig/writer.py` | +5 | −4 |
| `local-development/tests/test_fleet_lifecycle.py` | +3 | −2 |
| `local-development/tests/test_fleet_lookup.py` | +2 | −1 |
| `local-development/tests/test_ping_account_scope.py` | +487 | −0 |
| `docs/specs/SPEC_S4c_credential_lifecycle.md` | +83 | −25 |
| `docs/CLUSTER_STANZA.md` | +4 | −1 |
| `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md` | +5 | −1 |
| `local-development/API.md` | +2 | −2 |
| `docs/CHANGELOG.md` | +18 | −0 |

### 3.4 What must not change, and what holds each

**Everything the brief lists is untouched, and each has a test or a render that says so.**

| must not change | held by |
|---|---|
| the ping's once-per-account-per-interval budget | the due test (poller.py:1786-1788) is untouched; `test_r3_twenty_clusters_on_one_account_are_one_ping_a_cadence_rotating_by_name` passes with its assertions unchanged |
| the ping's stand-down on a refusal | poller.py:1753-1782 untouched for a declared account; `test_r4_a_gated_account_is_not_pinged_and_is_said_once` passes with its assertions unchanged |
| #283's login rules | `local-development/gsd/fleetlogin.py` is untouched; `test_fleet_login.py` and `test_fleet_login_basic_scrub.py` pass unchanged |
| the dashboard ServiceAccount's permissions | no chart template or value changes. Rendered RBAC atoms, before and after, for the default values, `environments/crc.yaml`, `environments/example-production.yaml` and `charts/group-sync-dashboard/example-production.yaml`, each with election on and off: REMOVED 0, ADDED 0 in all eight (§4) |
| no test or walk logs in as `ocp-oauth-bind-serviceid` | the tests use placeholder accounts against a fake target; the walk names `developer` only, and stops if anything else names the fleet account (§5) |
| the lookup and self-login | untouched; `test_the_lookup_and_self_login_present_the_account_their_stanza_names` passes before and after |
| every account the configuration names keeps its ping | `test_every_account_the_configuration_names_keeps_its_ping` passes before and after, for the chart's account, a values stanza's and a ConfigMap onboarding's |
| the tab's rows and the metrics | an account the configuration no longer names is still served (`test_an_account_no_longer_named_remains_visible_without_a_login`, `test_historical_refusal_stays_visible_without_reading_password`) |

### 3.5 What is left, stated

**Five residuals, each bounded; none sends the password as an account the loaded configuration does not name.**

1. **The refusal record's bound.** The Lease remembers only the latest refusal: one `refused` entry per account, which
   a new attempt's reservation replaces and a success clears. While the Secret's uid, the password and that entry are
   unchanged, every path — lookup, self-login, ping — and every restart and replica stand down on it. But A → B → A
   across fresh processes sends A twice: B's refusal replaced A's entry, and a fresh process's gate is empty.
   A new Secret UID (a Secret deleted and recreated) re-arms a fresh process the same way, and so does an entry
   removed by hand. A process's own in-memory gate keeps every refusal it met, until it restarts. This is SPEC_S4c's B2 and D2
   as shipped; #432 documents it and builds no refusal history (`test_rotation_replay_contract_matches_the_lease`,
   `test_secret_recreation_rearms_a_fresh_process`).
2. **A false declaration.** When the chart or a stanza names an account whose directory password is not the Secret's,
   that account is refused, within the bound above. The dashboard cannot tell this from a wrong password in the
   Secret without that login. Only a credential per account closes it: #369, parked. Pinned by
   `test_the_lookup_and_self_login_present_the_account_their_stanza_names`.
3. **The snapshot boundary.** Each process decides on the configuration it loaded. A replica still running the old
   values presents a repurposed shared Secret as the old account. Drain old processes before repurposing a shared
   password Secret, or give the new account its own Secret reference (`test_old_replica_still_uses_its_loaded_declaration`).
4. **Secrets retrieved before this change.** They lost whether the stanza named its account. An account that only such
   a Secret named is no longer pinged, since guessing from `lookup-account` would reopen the username-change hole.
   Recovery is to declare the account again — on the chart, in a values stanza, in a ConfigMap onboarding, or as
   `ldapConnectionBootstrap` in the Secret's `config`, which the parser now accepts. Measured on the reference cluster:
   no such Secret exists (Orchestrator's notes).
5. **History stays shown, and so does its staleness.** An account the configuration no longer names keeps its row and
   its share of `gsd_fleet_account_last_ok_timestamp_seconds` (the oldest success, metrics.py:853-856) and of
   `gsd_fleet_account_suspended`. Since nothing pings it again, its staleness can keep the documented alert on: that
   is shipped behaviour kept, and changing the alert is a separate decision. One directory entry under two login
   names (each identity provider matches its own attribute, about-ldap.adoc lines 41-45) stays two accounts to the
   dashboard: SPEC_S4d's exact-string scope.

### 3.6 The issue's Definition of Done, line by line

**Each line of #432's Definition of Done has its place here, and two of them are finished only after this spec.**

| the issue's line | where it is met |
|---|---|
| *A hermetic test: two accounts, one password Secret. The ping never authorizes as an account whose password the Secret does not hold. It fails before, passes after, and counts the wire.* | `test_the_walk_presents_nothing_as_the_fleet_account` (both cases), with §3.2's tables: each counts authorize requests by their Basic header (§4) |
| *SPEC_S4c §3.12 corrected, reviewed, and walked on the lab as `developer` only. The fleet account's token count stays 2, and its audit-log authorizes stay 0.* | corrected by §6's §3.12 block (§5 says what changed). Reviewed with this spec. The walk runs after the release that carries §6, and its step 7 records both numbers |
| *Reviewed by two seats other than the implementer, Grok one of them. The minor version bump.* | the orchestrator's: Grok and Codex Astra reviewed `b341697` (round 1, Orchestrator's notes); the release commit takes the bump |

## 4. Tests, before and after

**The new failing cases fail before and pass after; the pins pass both ways on purpose; the existing suite changes
only where a test pinned what this change deliberately changes.**

"Before" is `6740e1e` plus §6's test blocks only (the harness line, the updated `test_fleet_lookup.py` assertion and
the new file); "after" is `6740e1e` with every block applied. Run from `local-development/` with `PYTHONPATH=.:tests`,
`-p no:cacheprovider`, and `gsd` imported from the tree under test (printed with each measurement).

| what it proves | test (`local-development/tests/…`) | before | after |
|---|---|---|---|
| the Definition of Done: two accounts, one password Secret — the corrected walk's steps 2–3, the rotation back in the same process | `test_ping_account_scope.py::test_the_walk_presents_nothing_as_the_fleet_account[same-process]` | FAILED `a walk password was presented as FLEET`: `['walk-pw-2', 'wrong-pw-4']` | passed |
| the same, the rotation back after a restart | `…[after-a-restart]` | FAILED: `['walk-pw-2', 'wrong-pw-4', 'walk-pw-2']` | passed |
| Grok's note on PR #433: the walk's self-login arrangement with the ping on | `…::test_the_self_login_walk_arrangement_with_the_ping_on_presents_nothing_as_the_fleet_account[as-found]`, `[carrying-a-refusal]` | FAILED `the first cadence presented a password`: `['fleet-bind-account']` | passed |
| §3.2's budget over the system | `…::test_the_pairing_budget_over_the_system` | FAILED: the measured dict is §3.2's before column | passed |
| a leader change between the Lease read and the claim (Codex) | `…::test_leadership_changes_between_read_and_claim` | FAILED: `[('fleet-bind-account', 'other-pw-3'), ('other-account', 'other-pw-3')]` — FLEET was sent OTHER's password | passed |
| an undeclared account whose Lease already holds a ping digest (Grok) | `…::test_lease_already_records_ping_digest_for_undeclared_account` | FAILED: `[('fleet-bind-account', 'fleet-pw-1'), ('other-account', 'fleet-pw-1')]` — FLEET was pinged again after the chart moved to OTHER | passed |
| a ConfigMap output whose `lookup-account` alone was edited (Codex C2) | `…::test_configmap_digest_does_not_authorize_a_changed_lookup_annotation` | FAILED `owner digest must not make an edited annotation a declaration`: `[('fleet-bind-account', 'c0rrect-horse-battery-staple')]` | passed |
| a Secret-declared stanza keeps its explicit account through retrieval (C4 (i)) | `…::test_secret_retrieval_preserves_only_explicit_intent[True]` | FAILED `assert None == 'other-account'`: retrieval dropped the account | passed |
| … and a Secret that named none gains none: with the chart naming FLEET, the account its retrieval recorded is not pinged | `…[False]` | FAILED `assert [('other-account', 'other-pw-3')] == []` | passed |
| an account no longer named stays on the tab, and is not logged in as (C4 (ii)) | `…::test_an_account_no_longer_named_remains_visible_without_a_login` | FAILED: `[('fleet-bind-account', 'other-pw-3'), ('other-account', 'other-pw-3')]` — FLEET was sent OTHER's password | passed |
| its saved refusal stays visible, and its password is not read (C4 (ii)) | `…::test_historical_refusal_stays_visible_without_reading_password` | FAILED `historical row read the fleet password` | passed |
| a trailing newline in a username (Codex) | `…::test_account_spelling_contract[user\n]` | FAILED `assert not True`: `user\n` passed the username rule | passed |
| exact-string scope: `User`, and a surrounding space or tab | `…[User]`, `[ user]`, `[user ]`, `[user\t]` | passed | passed — the contract, stated (§3.2) |
| retrieval's stored `config` keeps the explicit account | `test_fleet_lookup.py::TestADeclaringSecretIsUpdatedInPlace::test_the_mode_leaves_config_the_credential_arrives_and_the_annotations_remember` | FAILED `the mode leaves; the explicit account stays (#432)`: the stored `config` has no `ldapConnectionBootstrap` | passed — its assertion changes with this spec (C4 (i)) |
| no narrowing: the chart's account, a values stanza's and a ConfigMap onboarding's keep their ping | `…::test_every_account_the_configuration_names_keeps_its_ping[chart-username]`, `[values-stanza]`, `[configmap-onboarded]` | passed | passed — guards; each fails under its mutant (below) |
| §3.5's contracts: the latest-refusal bound, a recreated Secret, the old replica's snapshot | `…::test_rotation_replay_contract_matches_the_lease`, `…::test_secret_recreation_rearms_a_fresh_process`, `…::test_old_replica_still_uses_its_loaded_declaration` | passed | passed — pins of shipped behaviour and of this spec's words for it; against `b341697`'s prose all three fail, each on its phrase |
| §3.5's false declaration, pinned: the lookup and self-login present the account their stanza names, once, then both stand down | `…::test_the_lookup_and_self_login_present_the_account_their_stanza_names` | passed | passed — a pin |
| harness only: the account the ping reads is named on the chart | `test_fleet_lifecycle.py::test_r3_…`, `test_r4_…[login-refused]`, `[login-failed]`, `test_r9_…`, `test_ping_ignores_onboarding_spent_mark_in_same_process`, `test_293s_success_mark_stays_per_target_and_off_the_lease` | passed, with or without the harness line (the file: 52 passed both ways) | passed; without the harness line these six FAILED — the account they ping is named nowhere |
| the walk report's own test (PR #433, not in this tree): reports/2026-09-27_epic-c-walk/hermetic/test_walk_password_scope.py | its four cases | 4 passed | the first test's 2 cases FAILED (`assert [] == ['walk-placeholder-2', 'walk-wrong-3']`), by design — it pins 1.0.0's defect (Orchestrator's notes); the 2 self-login cases passed |

**The whole suite**, `pytest tests/ -q --deselect tests/test_live_smoke.py`, browser tests included, run from
`local-development/` with `PYTHONPATH=.` on each proof tree (a clone of `b341697` carrying this spec, with the test
blocks, or with every block):

| tree | result |
|---|---|
| before | `14 failed, 6080 passed, 20 skipped, 4 deselected, 2 warnings in 485.13s` — the fourteen are the failing cases above |
| after | `6096 passed, 19 skipped, 4 deselected, 2 warnings in 482.50s` |

The difference is named, not assumed: the fourteen cases above pass after; `test_docs_citations.py` counts one
test per anchored citation, and this change adds one, in `CLUSTER_CREDENTIALS.md`, to `_declared_accounts` (1157
passed before, 1158 after, 15 skipped in both); and
`test_kyverno.py::test_f3_unreleased_cites_the_current_chart_version_when_it_moved_since_the_last_release` skips
while the CHANGELOG has no `## Unreleased` section ("no Unreleased section") and runs, and passes, once §6's entry
adds one.

**The fleet set** — the fleet files (`test_fleet_lifecycle.py`, `test_fleet_lifecycle_round3.py`,
`test_self_login_url_moved.py`, `test_fleet_lookup.py`, `test_fleet_login.py`, `test_configmap_onboarding.py`, the
three `test_credential_gate_*.py`, `test_lookup_owned_secret.py`, `test_connection_modes.py`,
`test_fleet_login_basic_scrub.py`), `test_chart_connection_modes.py` and the new file: before, `14 failed, 372
passed`, the fourteen above; after, `386 passed`; after without the harness line, `6 failed, 380 passed`, the six
named in the table.

**§3.2's budget table**, re-measured on these two trees with each tree's own `gsd`: every cell as printed, before and
after.

**RBAC**, rendered with `helm template` (v4.3.0) from `b341697` and from the applied tree, for the default values,
`environments/crc.yaml`, `environments/example-production.yaml` and `charts/group-sync-dashboard/example-production.yaml`,
each with `leaderElection.enabled` true and false: 63, 60, 70, 70, 63, 60, 68 and 68 atoms; REMOVED 0 and ADDED 0 in
all eight. The only file under `charts/` that changes is `CLUSTER_CREDENTIALS.md`.

**The blocks**, on a clean clone of `b341697`: `python3 local-development/apply-spec-blocks.py
docs/specs/SPEC_S4e_ping_account_scope.md . --apply` reports "21 blocks check out across 13 files", and the
applied tree equals the implemented copy byte for byte in all thirteen files.

**Every design decision is held by a test.** Each was reverted in the implemented copy and the fleet set (386 tests)
run against the mutant; all twelve were caught:

| reverted decision | caught by |
|---|---|
| M0 the early return removed: any `lookup-account` pingable, and its password read (`6740e1e`'s rule) | 11 tests: the walk (both cases), the self-login walk with the ping on (both), the budget table, the leader change, the stale digest, the edited ConfigMap annotation, `[False]` retrieval, the account no longer named, the historical refusal |
| M1 a retrieved values stanza left out (the merge hides it) | `test_every_account_the_configuration_names_keeps_its_ping[values-stanza]`, `test_account_spelling_contract[User]` |
| M2 the ConfigMap declaration's account not carried onto its output | `test_configmap_digest_does_not_authorize_a_changed_lookup_annotation`, which runs real onboarding discovery |
| M3 the chart's username left out | 15 tests, among them the chart-username guard, R3, R4, R9 and the three contract tests |
| M4 members filtered too (`b341697`'s rule: the account leaves the tab) | `test_an_account_no_longer_named_remains_visible_without_a_login`, `test_historical_refusal_stays_visible_without_reading_password` |
| M5 a disabled stanza still naming its account | `test_the_pairing_budget_over_the_system` (the "stanza disabled" row) |
| M6 retrieval strips the explicit account again | `test_secret_retrieval_preserves_only_explicit_intent[True]`, and the declaring-Secret test in `test_fleet_lookup.py` |
| M7 the parser refuses the account a retrieved Secret kept | `test_secret_retrieval_preserves_only_explicit_intent[True]` |
| M8 the parser accepts the account beside any bearer token, retrieved or not | `TestTheParser::test_the_refusals_are_findings_naming_the_key[config4-…]` in `test_connection_modes.py`: a hand-written bearer Secret carrying the key is still refused |
| M9 `.match()` again | `test_account_spelling_contract[user\n]` |
| M10 a ConfigMap output's `lookup-account` trusted (`b341697`'s clause) | `test_configmap_digest_does_not_authorize_a_changed_lookup_annotation` |
| M11 option (a): only the chart's username pinged (§2.5) | 4 tests: the values-stanza and ConfigMap guards, `[True]` retrieval, `[User]` |

The two pieces round 1 did not take, put back one at a time, fail nothing: the target filter beside the early return,
`386 passed`; `and oauth is None` in the parser's exemption, `386 passed` (Orchestrator's notes).

## 5. The corrected walk (SPEC_S4c §3.12)

**Nothing the walk deploys names the fleet account; the lab is re-checked, read-only, before every password it
places; and the release it runs on presents the password only as an account the configuration names.**

§6 rewrites SPEC_S4c §3.12 in place; the whole text is the New side of that block. What changed, and why:

| | as first written | corrected |
|---|---|---|
| the chart's username during the walk | not changed: still the fleet account | `developer` |
| the password Secret | "holding `developer`'s password" — which Secret was not said | a walk-only Secret in the release namespace; never `ldap-oauth-bind-secret` |
| what `gsd-cluster-shared-rnd` recording the fleet account meant | the ping would present the walk's passwords as the fleet account (2, or 3 with a restart) | history: its Lease is read and shown, no password is read for it, and it is never pinged |
| a guard before deploying | none | step 0: the release must carry this spec, and the rendered walk values must name only `developer` |
| a guard before each password | none | the lab check (Codex C7): three read-only counts — the deployed configuration, every cluster Secret's `ldapConnectionBootstrap`, every onboarding ConfigMap — must all be `0`, immediately before the walk Secret is created and before steps 3 and 5 place a wrong password |
| `self-login`, steps 4–5 | ping state unstated | the ping stays on; `test_the_self_login_walk_arrangement_with_the_ping_on_presents_nothing_as_the_fleet_account` is its hermetic proof (Grok's note on PR #433) |
| the end | token counts | token counts, 0 audit-log authorizes for the fleet account, and its Lease byte-identical to the baseline |

Both guards, measured:

- **Step 0's render check**, with `helm template` on `6740e1e`: PR #433's prepared walk values
  (prepared/walk-values-selflogin.yaml at `6545292`) render `fleetAccountUsername: "developer"`, one
  `ldapConnectionBootstrap: developer`, and 0 mentions of `ocp-oauth-bind-serviceid`; `environments/crc.yaml` renders 1.
- **The lab check**, read-only on the reference cluster as found (2026-09-27T15:49:38Z): `1`, `0`, `0` — the deployed
  configuration still names the fleet account, so the walk stops there, as it must until the walk's values are
  deployed. On synthetic lists the second and third counts each find a Secret and a ConfigMap that name it: `1`, `1`.

On a release without this spec the ping still reads `lookup-account`, so step 0 keeps PR #433's arrangement there: the
ping off, and steps 2–3 skipped.

## 6. Implementation blocks

**Twenty-one blocks over thirteen files, in apply order.** This spec's Status, and its row in `docs/specs/README.md`, move to `merged` by hand
in the implementing commit, beside the applied blocks — a block cannot, because its Old text would also match inside
its own fence — so that `local-development/prepare-release.py` promotes them.

<!-- block: local-development/gsd/config.py | edit -->
```python


def valid_bootstrap_username(value: object) -> bool:
    return isinstance(value, str) and bool(_BOOTSTRAP_USERNAME.match(value))


@dataclass(frozen=True)
```

```python


def valid_bootstrap_username(value: object) -> bool:
    return isinstance(value, str) and bool(_BOOTSTRAP_USERNAME.fullmatch(value))


@dataclass(frozen=True)
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
            return None
        return ClusterClient(host, timeout=self.settings.request_timeout_seconds), namespace

    def _ping_accounts(self) -> None:
        """One real read per fleet account per cadence (SPEC_S4c §3.4) — the daily ping, on the discovery thread,
        after the lookups. Every account in use has its Lease read each cadence, on every replica, so the tab and
        /metrics serve the same instants and the same gate on a standby. On the leader, an entry for the configured
        password — whichever path or replica wrote it — seeds the gate and stops the account's self-login clusters
        (#419, D3), and an account whose clusters the lookup retrieved is pinged against ONE of them — the
        `lookup-account` their Secrets record, in rotation by name — through `lookup(write=False)` under the account
        Lease's claim."""
        from .clusterconfig.events import event, failure
        from .clusterconfig.parser import Finding
        from .clusterconfig.writer import secret_name_for
```

```python
            return None
        return ClusterClient(host, timeout=self.settings.request_timeout_seconds), namespace

    def _declared_accounts(self, effective: list[ClusterConfig]) -> set[str]:
        """Only declarations authorize an account: retrieval history cannot vouch for today's password (#432)."""
        s = self.settings
        accounts = {s.fleet_account_username}
        accounts.update(c.ldap_connection_bootstrap for c in (*s.clusters, *effective)
                        if c.enabled and (c.connection_mode or c.token_source == CREDENTIAL_LOOKUP))
        return accounts - {"", None}

    def _ping_accounts(self) -> None:
        """One real read per fleet account per cadence (SPEC_S4c §3.4) — the daily ping, on the discovery thread,
        after the lookups. Every account in use has its Lease read each cadence, on every replica, so the tab and
        /metrics serve the same instants and the same gate on a standby. On the leader, an entry for the configured
        password — whichever path or replica wrote it — seeds the gate and stops the account's self-login clusters
        (#419, D3), and an account whose clusters the lookup retrieved is pinged against ONE of them — the
        `lookup-account` their Secrets record, in rotation by name — through `lookup(write=False)` under the account
        Lease's claim. Historical accounts remain visible, but only declared accounts may authenticate (#432)."""
        from .clusterconfig.events import event, failure
        from .clusterconfig.parser import Finding
        from .clusterconfig.writer import secret_name_for
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
            return
        targets: dict[str, list[ClusterConfig]] = {}       # account -> the retrieved clusters its ping may read
        members: dict[str, list[str]] = {}                 # account -> every enabled cluster in use on it (#419, F3)
        for c in self.settings.effective_clusters():
            named = c.ldap_connection_bootstrap or self.settings.fleet_account_username
            if c.enabled and c.token_source == CREDENTIAL_LOOKUP and c.lookup_account:
                targets.setdefault(c.lookup_account, []).append(c)
```

```python
            return
        targets: dict[str, list[ClusterConfig]] = {}       # account -> the retrieved clusters its ping may read
        members: dict[str, list[str]] = {}                 # account -> every enabled cluster in use on it (#419, F3)
        effective = self.settings.effective_clusters()
        declared = self._declared_accounts(effective)      # the only accounts the password is presented as (#432)
        for c in effective:
            named = c.ldap_connection_bootstrap or self.settings.fleet_account_username
            if c.enabled and c.token_source == CREDENTIAL_LOOKUP and c.lookup_account:
                targets.setdefault(c.lookup_account, []).append(c)
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
            if record.reservation_pending(datetime.now(UTC), lease.claim_seconds):
                continue    # an attempt under way: its reservation is not yet an answer (#419, round 2)
            views[account] = record.view()
            # ROTATION BY NAME (§3.4): the first after the last target, wrapping — over N cadences every target is
            # read once, so a grant revoked on one is found naming it.
            clusters, last = sorted(targets.get(account, []), key=lambda c: c.name), record.ping_last_target
```

```python
            if record.reservation_pending(datetime.now(UTC), lease.claim_seconds):
                continue    # an attempt under way: its reservation is not yet an answer (#419, round 2)
            views[account] = record.view()
            if account not in declared:
                continue    # history stays visible without reading or presenting a password (#432)
            # ROTATION BY NAME (§3.4): the first after the last target, wrapping — over N cadences every target is
            # read once, so a grant revoked on one is found naming it.
            clusters, last = sorted(targets.get(account, []), key=lambda c: c.name), record.ping_last_target
```

<!-- block: local-development/gsd/clusterconfig/onboarding.py | edit -->
```python
    for i, cluster in enumerate(clusters):
        declaration = desired.get(cluster.name)
        if declaration is not None and cluster.source.split(":", 1)[-1] in outputs:
            clusters[i] = dataclasses.replace(cluster, enabled=declaration.enabled,
                                              visibility=declaration.visibility, identity=declaration.identity,
                                              onboarding=declaration.onboarding)
    # Detect a physical-name collision, including an unlabelled Secret, before spending a login.
    for name, cluster in list(pending.items()):
        with host_client._client() as client:
```

```python
    for i, cluster in enumerate(clusters):
        declaration = desired.get(cluster.name)
        if declaration is not None and cluster.source.split(":", 1)[-1] in outputs:
            # The account comes from the accepted declaration, never from the output's annotation (#432).
            clusters[i] = dataclasses.replace(cluster, enabled=declaration.enabled,
                                              visibility=declaration.visibility, identity=declaration.identity,
                                              onboarding=declaration.onboarding,
                                              ldap_connection_bootstrap=declaration.ldap_connection_bootstrap)
    # Detect a physical-name collision, including an unlabelled Secret, before spending a login.
    for name, cluster in list(pending.items()):
        with host_client._client() as client:
```

<!-- block: local-development/gsd/clusterconfig/parser.py | edit -->
```python
from dataclasses import dataclass

from ..config import (
    BOOTSTRAP_KEY, CLUSTER_IDENTITIES, CLUSTER_VISIBILITIES, CONNECTION_KEYS, CONNECTION_MODE_KEYS,
    IDENTITY_NONE, VISIBILITY_REMOTE_SAR, ClusterConfig, valid_bootstrap_username,
)

```

```python
from dataclasses import dataclass

from ..config import (
    BOOTSTRAP_KEY, CLUSTER_IDENTITIES, CLUSTER_VISIBILITIES, CONNECTION_KEYS, CONNECTION_MODE_KEYS, CREDENTIAL_LOOKUP,
    IDENTITY_NONE, VISIBILITY_REMOTE_SAR, ClusterConfig, valid_bootstrap_username,
)

```

<!-- block: local-development/gsd/clusterconfig/parser.py | edit -->
```python
        if not valid_bootstrap_username(bootstrap):
            return finding("unsupported-config-key",
                           f"config.{BOOTSTRAP_KEY}: must be a username (letters, digits, '.', '_', '@', '-')")
        if mode is None:
            return finding("unsupported-config-key",
                           f"config.{BOOTSTRAP_KEY} without saTokenLookup or userSelfLogin configures a login that would never happen")
    if token is not None and oauth is not None:
```

```python
        if not valid_bootstrap_username(bootstrap):
            return finding("unsupported-config-key",
                           f"config.{BOOTSTRAP_KEY}: must be a username (letters, digits, '.', '_', '@', '-')")
        # A retrieved bearer Secret keeps its explicit account: the daily ping's declaration (#432).
        from .writer import TOKEN_SOURCE_ANNOTATION   # local: the writer imports this module
        retrieved = (meta.get("annotations") or {}).get(TOKEN_SOURCE_ANNOTATION) == CREDENTIAL_LOOKUP
        if mode is None and not (retrieved and token is not None):
            return finding("unsupported-config-key",
                           f"config.{BOOTSTRAP_KEY} without saTokenLookup or userSelfLogin configures a login that would never happen")
    if token is not None and oauth is not None:
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
from ..config import CONNECTION_KEYS, CREDENTIAL_LOOKUP, CREDENTIAL_SELF_LOGIN
```

```python
from ..config import CONNECTION_MODE_KEYS, CREDENTIAL_LOOKUP, CREDENTIAL_SELF_LOGIN
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
    Why in place and not a second Secret (SPEC_S4 §1): a Secret is named for its cluster and the
    reader fails closed on two Secrets for one cluster, so a `create` beside the declaring Secret is
    `secret-exists` and any other name is `duplicate-cluster-name` — neither loads. `config` becomes
    `{bearerToken, tlsClientConfig}`: the mode and bootstrap keys leave (the parser refuses them
    beside a credential) and the annotations keep the memory of the mode. `tlsClientConfig` is kept
    as declared — it is the trust that just verified both hosts. Labels and `managed-by` are kept:
    the lookup did not create this Secret. The decode refusal and the 409 are `rotate`'s, for the
    reasons stated there.
```

```python
    Why in place and not a second Secret (SPEC_S4 §1): a Secret is named for its cluster and the
    reader fails closed on two Secrets for one cluster, so a `create` beside the declaring Secret is
    `secret-exists` and any other name is `duplicate-cluster-name` — neither loads. `config` becomes
    `{bearerToken, tlsClientConfig}`: the mode keys leave (the parser refuses them beside a credential)
    and the annotations keep the memory of the mode. An explicit `ldapConnectionBootstrap` stays: it is
    the declaration the daily ping may present the password as (#432). `tlsClientConfig` is kept
    as declared — it is the trust that just verified both hosts. Labels and `managed-by` are kept:
    the lookup did not create this Secret. The decode refusal and the 409 are `rotate`'s, for the
    reasons stated there.
```

<!-- block: local-development/gsd/clusterconfig/writer.py | edit -->
```python
                                                  "fix the Secret where it is written") from None
        if not isinstance(config, dict):
            raise WriteRefused("config-not-json", f"Secret {name}: data.config is not a JSON object; fix the Secret where it is written")
        for key in (*CONNECTION_KEYS, "oauth"):
            config.pop(key, None)
        config["bearerToken"] = token.strip()
        data["config"] = base64.b64encode(json.dumps(config, separators=(",", ":")).encode("utf-8")).decode("ascii")
```

```python
                                                  "fix the Secret where it is written") from None
        if not isinstance(config, dict):
            raise WriteRefused("config-not-json", f"Secret {name}: data.config is not a JSON object; fix the Secret where it is written")
        for key in (*CONNECTION_MODE_KEYS, "oauth"):
            config.pop(key, None)
        config["bearerToken"] = token.strip()
        data["config"] = base64.b64encode(json.dumps(config, separators=(",", ":")).encode("utf-8")).decode("ascii")
```

<!-- block: local-development/tests/test_fleet_lifecycle.py | edit -->
```python


def process(tmp_path, monkeypatch, host: LeaseHost, *clusters: ClusterConfig, discovered=(), name="p", **kw) -> Poller:
    """One dashboard process over `host`: its own store and its own in-memory gate."""
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **k: host)
    s = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"), *clusters],
                 db_path=str(tmp_path / f"{name}.db"), cluster_secrets_writes_enabled=True, **kw)
    s.cluster_registry.replace(list(discovered), [], at="2026-09-26T00:00:00Z")
    return Poller(Store(str(tmp_path / f"{name}.db")), s, signals=RuntimeSignals())

```

```python


def process(tmp_path, monkeypatch, host: LeaseHost, *clusters: ClusterConfig, discovered=(), name="p", **kw) -> Poller:
    """One process over `host`; USER is named on the chart, since only declared accounts are pinged (#432)."""
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **k: host)
    s = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"), *clusters],
                 db_path=str(tmp_path / f"{name}.db"), cluster_secrets_writes_enabled=True,
                 **{"fleet_account_username": USER, **kw})
    s.cluster_registry.replace(list(discovered), [], at="2026-09-26T00:00:00Z")
    return Poller(Store(str(tmp_path / f"{name}.db")), s, signals=RuntimeSignals())

```

<!-- block: local-development/tests/test_fleet_lookup.py | edit -->
```python
        (method, path, obj), = host.writes
        assert (method, path, result.written) == ("PUT", "/api/v1/namespaces/ns/secrets/gsd-cluster-rnd", "updated")
        config = json.loads(base64.b64decode(obj["data"]["config"]))
        assert config == {"tlsClientConfig": {"insecure": False, "caData": "Y2E="}, "bearerToken": SA_TOKEN}
        assert obj["metadata"]["resourceVersion"] == "7", "PUT as read: a rewrite underneath is a 409, not a silent overwrite"
        assert obj["metadata"]["labels"]["environment"] == "rnd"
        assert obj["metadata"]["annotations"] == {MANAGED_BY_ANNOTATION: "ui", TOKEN_SOURCE_ANNOTATION: "remote-lookup",
```

```python
        (method, path, obj), = host.writes
        assert (method, path, result.written) == ("PUT", "/api/v1/namespaces/ns/secrets/gsd-cluster-rnd", "updated")
        config = json.loads(base64.b64decode(obj["data"]["config"]))
        assert config == {"tlsClientConfig": {"insecure": False, "caData": "Y2E="}, "bearerToken": SA_TOKEN,
                          "ldapConnectionBootstrap": USER}, "the mode leaves; the explicit account stays (#432)"
        assert obj["metadata"]["resourceVersion"] == "7", "PUT as read: a rewrite underneath is a 409, not a silent overwrite"
        assert obj["metadata"]["labels"]["environment"] == "rnd"
        assert obj["metadata"]["annotations"] == {MANAGED_BY_ANNOTATION: "ui", TOKEN_SOURCE_ANNOTATION: "remote-lookup",
```

<!-- block: local-development/tests/test_ping_account_scope.py | create -->
```python
"""#432: the fleet password is presented only as an account the configuration names now."""

from __future__ import annotations

import base64
import copy
import dataclasses
import json
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from gsd.clusterconfig.parser import Finding, parse_secret
from gsd.clusterconfig.reader import discover
from gsd.clusterconfig.writer import LOOKUP_ACCOUNT_ANNOTATION, store_lookup
from gsd.config import ClusterConfig, valid_bootstrap_username
from gsd.fleetstate import FleetLease, lease_digest, lease_name
from gsd.kube import OK
from test_configmap_onboarding import Host, cycle, generated
from test_fleet_lifecycle import LeaseHost, process, retrieved, sessions
from test_fleet_login import T0, login_302, refused_401
from test_fleet_lookup import API, PASSWORD, SA_TOKEN, UID, USER, wire  # noqa: F401  (the fixture)

FLEET, WALK, OTHER, STANZA = "fleet-bind-account", "walk-developer", "other-account", "stanza-account"
FLEET_PASSWORD, WALK_PASSWORD, OTHER_PASSWORD, WRONG = "fleet-pw-1", "walk-pw-2", "other-pw-3", "wrong-pw-4"
TOKENS = [f"sha256~V2Fsa1Nlc3Npb25Ub2tlbk51bWJlcj{n:02d}" for n in range(8)]
SPEC = Path(__file__).parents[2] / "docs/specs/SPEC_S4e_ping_account_scope.md"


def credentials(request: httpx.Request) -> tuple[str, str]:
    user, _, password = base64.b64decode(request.headers["authorization"].split(" ", 1)[1]).decode().partition(":")
    return user, password


def presented(target) -> list[tuple[str, str]]:
    """(username, password) of every authorize, in the order it reached the target."""
    return [credentials(request) for request in target.authorize]


def directory(passwords: dict[str, str], verdicts: list | None = None) -> list:
    """A directory: an account's own password gets a session, any other a 401, judged when it arrives."""
    def answer(request):
        user, password = credentials(request)
        accepted = passwords.get(user) == password
        if verdicts is not None:
            verdicts.append((user, accepted))
        return login_302() if accepted else refused_401()
    return [answer] * 64


def at(name: str, account: str, **kw) -> ClusterConfig:
    """A cluster the lookup retrieved as `account`, recorded in its Secret's `lookup-account`."""
    return dataclasses.replace(retrieved(name), lookup_account=account, **kw)


def lab_as_found(tmp_path, monkeypatch, host: LeaseHost) -> None:
    """The lab on 2026-09-27: the chart names FLEET, shared-rnd was retrieved as FLEET and pinged once."""
    host.rotate(FLEET_PASSWORD)
    lab = process(tmp_path, monkeypatch, host, discovered=[at("shared-rnd", FLEET)], name="lab", fleet_account_username=FLEET)
    lab._ping_accounts()
    lab._ping_accounts()                                # inside the interval: not due


def spec_prose() -> str:
    """The spec before its blocks: the blocks quote this file, so its own assertions would always match."""
    prose, found, _ = SPEC.read_text().partition("\n## 6. Implementation blocks\n")
    assert found, "SPEC_S4e has no implementation-blocks heading to stop at"
    return prose


def declared_secret(explicit: bool) -> dict:
    """A Secret that declares saTokenLookup, with or without its own ldapConnectionBootstrap."""
    config = {"saTokenLookup": True}
    if explicit:
        config["ldapConnectionBootstrap"] = OTHER
    return {"metadata": {"name": "gsd-cluster-east", "resourceVersion": "1",
                         "labels": {"groupsync-dashboard.io/secret-type": "cluster"}},
            "data": {k: base64.b64encode(v.encode()).decode() for k, v in
                     {"name": "east", "server": API, "config": json.dumps(config)}.items()}}


# ── the Definition of Done: the corrected §3.12 walk ────────────────────────────────────────────────

@pytest.mark.parametrize("rotation_back", ["same-process", "after-a-restart"])
def test_the_walk_presents_nothing_as_the_fleet_account(tmp_path, monkeypatch, wire, rotation_back):
    """Two accounts, one password Secret: the walk's steps 2-3 send FLEET nothing and WALK exactly its budget."""
    host = LeaseHost()
    wire.answers = directory({FLEET: FLEET_PASSWORD, WALK: WALK_PASSWORD})
    lab_as_found(tmp_path, monkeypatch, host)
    assert presented(wire) == [(FLEET, FLEET_PASSWORD)], "the product's own daily ping, as at 10:27:05Z"
    fleet_lease = copy.deepcopy(host.leases.objects[lease_name(FLEET)])

    def walk(name: str):
        return process(tmp_path, monkeypatch, host, discovered=[at("shared-rnd", FLEET), at("walk-lookup", WALK)],
                       name=name, fleet_account_username=WALK, fleet_ping_interval_seconds=60)
    host.rotate(WALK_PASSWORD)
    p = walk("walk")
    p._ping_accounts()                                  # step 2: the ping, as WALK
    host.rotate(WRONG)
    for _ in range(3):
        p._ping_accounts()                              # step 3: refused once, then three cadences of nothing
    host.rotate(WALK_PASSWORD)
    if rotation_back == "after-a-restart":
        p = walk("restarted")
    p._ping_accounts()                                  # rotated back: one confirming ping
    after = presented(wire)[1:]
    assert [password for user, password in after if user == FLEET] == [], "a walk password was presented as FLEET"
    assert after == [(WALK, WALK_PASSWORD), (WALK, WRONG), (WALK, WALK_PASSWORD)], after
    assert host.leases.objects[lease_name(FLEET)] == fleet_lease, "the fleet account's Lease was written"


@pytest.mark.parametrize("fleet_lease", ["as-found", "carrying-a-refusal"])
def test_the_self_login_walk_arrangement_with_the_ping_on_presents_nothing_as_the_fleet_account(
        tmp_path, monkeypatch, wire, fleet_lease):
    """Grok's note on PR #433: the walk's self-login arrangement with the ping on never presents as FLEET."""
    host = LeaseHost()
    wire.answers = [login_302()]
    lab_as_found(tmp_path, monkeypatch, host)
    if fleet_lease == "carrying-a-refusal":            # the branch that reads the password Secret for the account
        holder = FleetLease(host, "ns", FLEET, claim_seconds=195, identity="elsewhere")
        holder.claim()
        holder.refuse("https://api.crc.testing:6443", lease_digest(FLEET, "another-password", UID), "login-refused")
        holder.release()
    fleet_writes = len([w for w in host.leases.writes if w[1] == lease_name(FLEET)])
    authorizes = len(wire.authorize)

    host.rotate(WALK_PASSWORD)
    stanza = ClusterConfig("walk-self", "https://api.crc.testing:6443", user_self_login=True, ldap_connection_bootstrap=WALK)
    p = process(tmp_path, monkeypatch, host, stanza, discovered=[at("shared-rnd", FLEET)], name="walk",
                fleet_account_username=WALK, fleet_ping_enabled=True)
    p.store.upsert_cluster("walk-self", stanza.api_url, True, source="values", credential="self-login")
    now = [T0]
    s = sessions(p, now)
    cluster = p.settings.cluster("walk-self")
    wire.answers = [login_302(token=TOKENS[0]), login_302(token=TOKENS[1]), refused_401(),
                    login_302(expires_in="600", token=TOKENS[2]), login_302(expires_in="600", token=TOKENS[3])]
    p._ping_accounts(); p._retrieve_pending()
    assert [user for user, _ in presented(wire)[authorizes:]] == [], "the first cadence presented a password"
    assert s.credential_for(cluster).token_value == TOKENS[0]            # step 4: acquisition
    now[0] += timedelta(seconds=60)
    s.poll_answered(cluster, "auth_failed")                             # step 5: the session deleted from outside
    assert s.credential_for(cluster).token_value == TOKENS[1]            # one re-authentication
    s.poll_answered(cluster, OK)                                        # the poll green again: the episode ends
    host.rotate(WRONG)                                                  # step 5b: a wrong password + the deletion
    now[0] += timedelta(seconds=60)
    s.poll_answered(cluster, "auth_failed")
    assert s.credential_for(cluster) is None                            # refused once: suspended
    for _ in range(3):
        now[0] += timedelta(seconds=60)
        p._ping_accounts(); p._retrieve_pending()
        assert s.credential_for(cluster) is None                        # parked: no second authorize
    host.rotate(WALK_PASSWORD)                                          # the rotation back re-arms it
    now[0] += timedelta(seconds=60)
    assert s.credential_for(cluster).token_value == TOKENS[2]            # #310 Part A: a 600 s session
    now[0] += timedelta(seconds=450)                                    # renew_at = expires_at - 150 s
    assert s.credential_for(cluster).token_value == TOKENS[3]            # renewed
    p._ping_accounts()

    walk_presented = presented(wire)[authorizes:]
    assert [user for user, _ in walk_presented] == [WALK] * 5, walk_presented
    assert [password for _, password in walk_presented] == [WALK_PASSWORD, WALK_PASSWORD, WRONG, WALK_PASSWORD,
                                                            WALK_PASSWORD]
    assert len([w for w in host.leases.writes if w[1] == lease_name(FLEET)]) == fleet_writes, "the fleet Lease written"


# ── the budget over the system: every event in scope ────────────────────────────────────────────────
# Each scenario starts from the lab as found, sets up what it needs, and returns where its EVENT begins on the wire.

def _username_change(tmp_path, monkeypatch, host, passwords, wire, *, then=()):
    """The chart moves from FLEET to OTHER and the Secret to OTHER's password; then a restart, a process, a rotation."""
    start = len(wire.authorize)
    host.rotate(OTHER_PASSWORD)
    config = dict(discovered=[at("shared-rnd", FLEET), at("north", OTHER)], fleet_account_username=OTHER)
    process(tmp_path, monkeypatch, host, name="moved", **config)._ping_accounts()
    for step in then:
        if step == "rotation":
            passwords[OTHER] = "other-pw-rotated"
            host.rotate("other-pw-rotated")
        process(tmp_path, monkeypatch, host, name=step, **config)._ping_accounts()
    return start


def _stanza_moved(tmp_path, monkeypatch, host, passwords, wire, *, change):
    """A values stanza names STANZA, then is removed, renamed or disabled, and the fleet password rotates."""
    east = ClusterConfig("east", "https://api.east.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=STANZA)
    found = [at("shared-rnd", FLEET), at("east", STANZA), at("west", STANZA)]
    process(tmp_path, monkeypatch, host, east, discovered=found, name="declared", fleet_account_username=FLEET)._ping_accounts()
    start = len(wire.authorize)
    passwords[FLEET] = "fleet-pw-rotated"
    host.rotate("fleet-pw-rotated")
    moved = {"removed": (), "renamed": (dataclasses.replace(east, ldap_connection_bootstrap="renamed-account"),),
             "disabled": (dataclasses.replace(east, enabled=False),)}[change]
    process(tmp_path, monkeypatch, host, *moved, discovered=found, name="moved", fleet_account_username=FLEET)._ping_accounts()
    return start


def _stanza_added(tmp_path, monkeypatch, host, passwords, wire):
    """A stanza naming OTHER while the Secret holds FLEET's password: refused once, then gated (B2)."""
    start = len(wire.authorize)
    north = ClusterConfig("north", "https://api.north.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=OTHER)
    for name in ("added", "restarted"):
        p = process(tmp_path, monkeypatch, host, north, discovered=[at("shared-rnd", FLEET)], name=name,
                    fleet_account_username=FLEET)
        p._retrieve_pending(); p._ping_accounts()
    return start


def _rotation(tmp_path, monkeypatch, host, passwords, wire):
    """The named account's own password rotates: one confirming ping (B3), a restart included."""
    start = len(wire.authorize)
    passwords[FLEET] = "fleet-pw-rotated"
    host.rotate("fleet-pw-rotated")
    for name in ("rotated", "restarted"):
        process(tmp_path, monkeypatch, host, discovered=[at("shared-rnd", FLEET)], name=name,
                fleet_account_username=FLEET)._ping_accounts()
    return start


#: event -> (the scenario, the accounts the configuration names once the event has happened)
EVENTS = {
    "a username change": (_username_change, {OTHER}),
    "+ a restart": (lambda *a: _username_change(*a, then=("restart",)), {OTHER}),
    "+ a second process": (lambda *a: _username_change(*a, then=("replica",)), {OTHER}),
    "+ a rotation of the new account's password": (lambda *a: _username_change(*a, then=("rotation",)), {OTHER}),
    "a stanza removed, then a rotation": (lambda *a: _stanza_moved(*a, change="removed"), {FLEET}),
    "a stanza's account changed, then a rotation": (lambda *a: _stanza_moved(*a, change="renamed"),
                                                    {FLEET, "renamed-account"}),
    "a stanza disabled, then a rotation": (lambda *a: _stanza_moved(*a, change="disabled"), {FLEET}),
    "a stanza added (a false declaration)": (_stanza_added, {FLEET, OTHER}),
    "the named account's own rotation": (_rotation, {FLEET}),
}


def test_the_pairing_budget_over_the_system(tmp_path, monkeypatch, wire):
    """SPEC_S4e §3.2: per event, (sent to an account no longer named, sent to a named account wrongly)."""
    measured = {}
    for n, (event, (scenario, named)) in enumerate(EVENTS.items()):
        run = tmp_path / f"event-{n}"
        run.mkdir()
        host = LeaseHost()
        passwords = {FLEET: FLEET_PASSWORD, OTHER: OTHER_PASSWORD, STANZA: FLEET_PASSWORD}
        verdicts: list[tuple[str, bool]] = []
        wire.requests.clear()
        wire.answers = directory(passwords, verdicts)
        lab_as_found(run, monkeypatch, host)
        start = scenario(run, monkeypatch, host, passwords, wire)
        assert [u for u, _ in verdicts] == [u for u, _ in presented(wire)], "one verdict per authorize"
        measured[event] = (len([u for u, _ in verdicts[start:] if u not in named]),
                           len([u for u, accepted in verdicts[start:] if u in named and not accepted]))
    assert measured == {
        "a username change": (0, 0),
        "+ a restart": (0, 0),
        "+ a second process": (0, 0),
        "+ a rotation of the new account's password": (0, 0),
        "a stanza removed, then a rotation": (0, 0),
        "a stanza's account changed, then a rotation": (0, 0),
        "a stanza disabled, then a rotation": (0, 0),
        "a stanza added (a false declaration)": (0, 1),
        "the named account's own rotation": (0, 0),
    }, measured


def test_leadership_changes_between_read_and_claim(tmp_path, monkeypatch, wire):
    """A leader change between the Lease read and the claim sends only the declared account (Codex)."""
    host = LeaseHost()
    host.rotate(OTHER_PASSWORD)
    wire.answers = directory({OTHER: OTHER_PASSWORD})
    args = dict(discovered=[at("old", FLEET), at("current", OTHER)], fleet_account_username=OTHER)
    first = process(tmp_path, monkeypatch, host, name="first", **args)
    second = process(tmp_path, monkeypatch, host, name="second", **args)
    first.elector = SimpleNamespace(is_leader=True)
    second.elector = SimpleNamespace(is_leader=False)
    original = first._fleet_lease
    switched = False

    def lease_for(*args):
        lease = original(*args)
        claim = lease.claim

        def switch(*a, **kw):
            nonlocal switched
            if not switched:
                switched = True
                first.elector.is_leader = False
                second.elector.is_leader = True
                second._ping_accounts()
            return claim(*a, **kw)
        lease.claim = switch
        return lease
    monkeypatch.setattr(first, "_fleet_lease", lease_for)
    first._ping_accounts()
    assert switched and presented(wire) == [(OTHER, OTHER_PASSWORD)]


def test_lease_already_records_ping_digest_for_undeclared_account(tmp_path, monkeypatch, wire):
    """A digest the old account's Lease already holds does not license a ping as it (Grok)."""
    host = LeaseHost()
    wire.answers = directory({FLEET: FLEET_PASSWORD, OTHER: OTHER_PASSWORD})
    lab_as_found(tmp_path, monkeypatch, host)
    assert host.leases.objects[lease_name(FLEET)]["metadata"]["annotations"]["groupsync-dashboard.io/ping-digest"]
    host.leases.backdate(FLEET, "groupsync-dashboard.io/ping-last-attempt", 86400)
    start = len(wire.authorize)
    process(tmp_path, monkeypatch, host, discovered=[at("shared-rnd", FLEET), at("north", OTHER)],
            name="stale-digest", fleet_account_username=OTHER)._ping_accounts()
    after = presented(wire)[start:]
    assert [user for user, _ in after if user == FLEET] == [], after


@pytest.mark.parametrize("spelling", ["User", " user", "user ", "user\t", "user\n"])
def test_account_spelling_contract(tmp_path, monkeypatch, wire, spelling):
    """Usernames are exact strings: whitespace and a trailing newline are refused, case variants are two accounts."""
    if any(c.isspace() for c in spelling):
        assert not valid_bootstrap_username(spelling)
        obj = declared_secret(True)
        obj["data"]["config"] = base64.b64encode(json.dumps(
            {"saTokenLookup": True, "ldapConnectionBootstrap": spelling}).encode()).decode()
        assert isinstance(parse_secret(obj, host_name="host"), Finding)
        return
    host = LeaseHost()
    host.rotate("wrong")
    wire.answers = directory({})
    declarations = [ClusterConfig(n, API, sa_token_lookup=True, ldap_connection_bootstrap=u)
                    for n, u in [("lower", "user"), ("upper", spelling)]]
    p = process(tmp_path, monkeypatch, host, *declarations,
                discovered=[at("lower", "user"), at("upper", spelling)], fleet_account_username="")
    p._ping_accounts()
    assert sorted(presented(wire)) == sorted([("user", "wrong"), (spelling, "wrong")])
    assert lease_name("user") != lease_name(spelling)


def test_old_replica_still_uses_its_loaded_declaration(tmp_path, monkeypatch, wire):
    """A process that still names FLEET presents a repurposed Secret as FLEET: drain it first (the stated boundary)."""
    host = LeaseHost()
    old = process(tmp_path, monkeypatch, host, name="old-values",
                  discovered=[at("old", FLEET)], fleet_account_username=FLEET)
    host.rotate(OTHER_PASSWORD)
    wire.answers = directory({OTHER: OTHER_PASSWORD})
    old._ping_accounts()
    assert presented(wire) == [(FLEET, OTHER_PASSWORD)]
    assert "Drain old processes" in spec_prose()


# ── where the account comes from: declarations, never the annotation ────────────────────────────────

def test_configmap_digest_does_not_authorize_a_changed_lookup_annotation(tmp_path, monkeypatch, wire):
    """An owned output whose lookup-account alone was edited does not authorize that account (Codex C2)."""
    host = Host()
    wire.answers = directory({USER: PASSWORD})
    settings = generated(host)
    host.secrets["gsd-cluster-rnd"]["metadata"]["annotations"][LOOKUP_ACCOUNT_ANNOTATION] = FLEET
    _, clusters, findings, _ = cycle(host, settings)
    assert not findings and len(clusters) == 1
    lease_host = LeaseHost()
    lease_host.rotate(PASSWORD)
    p = process(tmp_path, monkeypatch, lease_host, discovered=clusters, fleet_account_username=USER)
    wire.requests.clear()
    p._ping_accounts()
    assert presented(wire) == [], "owner digest must not make an edited annotation a declaration"
    assert clusters[0].ldap_connection_bootstrap == USER


@pytest.mark.parametrize("explicit", [True, False])
def test_secret_retrieval_preserves_only_explicit_intent(tmp_path, monkeypatch, wire, explicit):
    """Retrieval keeps a Secret's own ldapConnectionBootstrap, and never makes a chart default one (C4 i)."""
    path = "/api/v1/namespaces/ns/secrets/gsd-cluster-east"
    host = LeaseHost(secrets={path: declared_secret(explicit)})
    store_lookup(host, "ns", "gsd-cluster-east", token=SA_TOKEN, cluster="east",
                 source_namespace="group-sync-operator", source_service_account="reader", lookup_account=OTHER)
    stored = host.writes[-1][2]
    parsed = parse_secret(stored, host_name="host")
    assert not isinstance(parsed, Finding)
    assert parsed.ldap_connection_bootstrap == (OTHER if explicit else None)
    found, findings = discover(host, "ns", host_name="host", values_names=("host",), items=[stored])
    assert not findings
    host.rotate(OTHER_PASSWORD)
    wire.answers = directory({OTHER: OTHER_PASSWORD})
    p = process(tmp_path, monkeypatch, host, discovered=found, fleet_account_username=FLEET)
    p._ping_accounts()
    assert presented(wire) == ([(OTHER, OTHER_PASSWORD)] if explicit else [])


# ── what #432 keeps ─────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("shape", ["chart-username", "values-stanza", "configmap-onboarded"])
def test_every_account_the_configuration_names_keeps_its_ping(tmp_path, monkeypatch, wire, shape):
    """No narrowing: the chart's account, a values stanza's and a ConfigMap onboarding's are still pinged."""
    host = LeaseHost()
    host.rotate(FLEET_PASSWORD)
    wire.answers = directory({FLEET: FLEET_PASSWORD, STANZA: FLEET_PASSWORD})
    stanzas, found = (), [at("east", FLEET if shape == "chart-username" else STANZA)]
    if shape == "values-stanza":
        stanzas = (ClusterConfig("east", "https://api.east.example.com:6443", sa_token_lookup=True,
                                 ldap_connection_bootstrap=STANZA),)
    if shape == "configmap-onboarded":
        found = [at("east", STANZA, onboarding=("fleet", "cm-uid-1", "east"), ldap_connection_bootstrap=STANZA)]
    process(tmp_path, monkeypatch, host, *stanzas, discovered=found, fleet_account_username=FLEET)._ping_accounts()
    assert presented(wire) == [(FLEET if shape == "chart-username" else STANZA, FLEET_PASSWORD)]


def test_an_account_no_longer_named_remains_visible_without_a_login(tmp_path, monkeypatch, wire):
    """After a username change the old account keeps its row, is not pinged, and its Lease is untouched."""
    host = LeaseHost()
    wire.answers = directory({FLEET: FLEET_PASSWORD, OTHER: OTHER_PASSWORD})
    lab_as_found(tmp_path, monkeypatch, host)
    original = copy.deepcopy(host.leases.objects[lease_name(FLEET)])
    host.rotate(OTHER_PASSWORD)
    p = process(tmp_path, monkeypatch, host, discovered=[at("shared-rnd", FLEET), at("north", OTHER)],
                name="moved", fleet_account_username=OTHER)
    p._ping_accounts()
    assert set(p.signals.fleet_accounts()) == {FLEET, OTHER}
    assert presented(wire)[1:] == [(OTHER, OTHER_PASSWORD)]
    assert host.leases.objects[lease_name(FLEET)] == original


def test_historical_refusal_stays_visible_without_reading_password(tmp_path, monkeypatch, wire):
    """An undeclared account's saved refusal is served, suspended included, with no password read (C4 ii)."""
    host = LeaseHost()
    lease = FleetLease(host, "ns", FLEET, claim_seconds=195)
    lease.claim()
    lease.refuse(API, "historic-digest", "login-refused")
    lease.release()
    snapshot = copy.deepcopy(host.leases.objects)
    p = process(tmp_path, monkeypatch, host, discovered=[at("east", FLEET)], fleet_account_username=OTHER)

    def no_password(*a, **kw):
        pytest.fail("historical row read the fleet password")
    monkeypatch.setattr("gsd.fleetlookup.fleet_password", no_password)
    p._ping_accounts()
    assert FLEET in p.signals.fleet_accounts(), "historical account disappeared"
    assert p.signals.fleet_accounts()[FLEET]["suspended"]
    from prometheus_client import generate_latest
    from gsd.metrics import build_registry
    metrics = generate_latest(build_registry(p.store, timedelta(0), signals=p.signals, settings=p.settings)).decode()
    assert "gsd_fleet_account_suspended 1.0" in metrics
    assert host.leases.objects == snapshot
    assert not wire.authorize


# ── the refusal record's real bound (Codex C3) and the residual of a false declaration ─────────────

def test_rotation_replay_contract_matches_the_lease(tmp_path, monkeypatch, wire):
    """The Lease keeps the latest refusal only: A, B, A across fresh processes sends A twice, as the spec states."""
    host = LeaseHost()
    wire.answers = directory({})
    for i, password in enumerate(["wrong-A", "wrong-B", "wrong-A"]):
        host.rotate(password)
        p = process(tmp_path, monkeypatch, host, discovered=[at("retrieved", OTHER)],
                    name=f"restart-{i}", fleet_account_username=OTHER)
        p._ping_accounts()
    assert presented(wire) == [(OTHER, "wrong-A"), (OTHER, "wrong-B"), (OTHER, "wrong-A")]
    text = spec_prose()
    assert "The Lease remembers only the latest refusal" in text
    assert "A → B → A" in text


def test_secret_recreation_rearms_a_fresh_process(tmp_path, monkeypatch, wire):
    """A recreated password Secret (a new uid) re-arms a fresh process once, as the spec states."""
    host = LeaseHost()
    host.rotate("wrong")
    wire.answers = directory({})
    for i in range(2):
        if i:
            host.secrets["/api/v1/namespaces/ns/secrets/gsd-fleet-account"]["metadata"]["uid"] = "replacement-uid"
        process(tmp_path, monkeypatch, host, name=f"process-{i}",
                discovered=[at("target", OTHER)], fleet_account_username=OTHER)._ping_accounts()
    assert presented(wire) == [(OTHER, "wrong"), (OTHER, "wrong")]
    assert "A new Secret UID" in spec_prose()


def test_the_lookup_and_self_login_present_the_account_their_stanza_names(tmp_path, monkeypatch, wire):
    """PINS THE RESIDUAL: a stanza's account is a declaration; a false one is refused once, then gated (B2)."""
    host = LeaseHost()
    host.rotate(FLEET_PASSWORD)
    wire.answers = directory({FLEET: FLEET_PASSWORD, OTHER: OTHER_PASSWORD})
    looked_up = ClusterConfig("other", "https://api.other.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=OTHER)
    self_login = ClusterConfig("other-self", "https://api.other-self.example.com:6443", user_self_login=True,
                               ldap_connection_bootstrap=OTHER)
    for name in ("first", "restarted"):
        p = process(tmp_path, monkeypatch, host, looked_up, self_login, name=name, fleet_account_username=FLEET,
                    fleet_ping_enabled=False)
        p.store.upsert_cluster("other-self", self_login.api_url, True, source="values", credential="self-login")
        p._retrieve_pending()                           # the lookup: the Secret's password, as the stanza's OTHER
        assert sessions(p, [T0]).credential_for(p.settings.cluster("other-self")) is None   # gated: not sent
    assert presented(wire) == [(OTHER, FLEET_PASSWORD)]
```

<!-- block: docs/specs/SPEC_S4c_credential_lifecycle.md | edit -->
```markdown
    and the last attempt apart; `API.md` and §3.10 say what `last_target` is.
  - Measured by the orchestrator on the branch: the four tests (N1, N3, and N2's new and amended UI tests) fail without
    the code changes and pass with them; main plus this spec's 102 blocks equals the branch but for the index row.

## 0. The requirement, in business terms

```

```markdown
    and the last attempt apart; `API.md` and §3.10 say what `last_target` is.
  - Measured by the orchestrator on the branch: the four tests (N1, N3, and N2's new and amended UI tests) fail without
    the code changes and pass with them; main plus this spec's 102 blocks equals the branch but for the index row.
- **#432 (`docs/specs/SPEC_S4e_ping_account_scope.md`, 2026-09-27): §3.4's ping and §3.12's walk, corrected in place.**
  The deviation "The ping's targets and accounts" above keyed the ping on the `lookup-account` annotation. That
  annotation records who retrieved a token under the configuration of that day and is never revised, while the
  password is the one Secret the configuration names today. So after a username change, a removed stanza or a
  repointed Secret, the ping presented today's password as yesterday's account. §3.12's steps 2–3 as written would
  have done exactly that on the reference cluster: `developer`'s password, then a wrong one, sent as the fleet account
  (the Epic C walk, PR #433: 2 authorizes, 3 with a restart, measured hermetically; not run). The ping now presents the
  password only as an account the configuration names, and still lists an account it no longer pings; SPEC_S4e §3.2
  states the budget over the system. §3.12 is rewritten: nothing the walk deploys names the fleet account, and the
  lab is re-checked read-only before any password is placed.

## 0. The requirement, in business terms

```

<!-- block: docs/specs/SPEC_S4c_credential_lifecycle.md | edit -->
```markdown
  `ping-last-target` rotation: the cluster that was not the last target and comes first by name.
  Over N cadences every target is read once, so a grant revoked on target 3 is a finding naming
  target 3 within N days and the account's `last_ok` still moves on the days the others answer.
  Decided, not measured; §5.1 says what would change it.
- **Due when** `now − ping_last_attempt ≥ fleet_ping_interval_seconds`, **or** the password digest
  differs from `ping-digest` (a rotation is confirmed once, within one cadence). Both read from the
  Lease inside the claim, so a restart at 23:59 does not ping again at 00:00 and a second replica
```

```markdown
  `ping-last-target` rotation: the cluster that was not the last target and comes first by name.
  Over N cadences every target is read once, so a grant revoked on target 3 is a finding naming
  target 3 within N days and the account's `last_ok` still moves on the days the others answer.
  Decided, not measured; §5.1 says what would change it. **Only an account the configuration names now is
  pinged** (#432, `docs/specs/SPEC_S4e_ping_account_scope.md` §3.1): the chart's `fleetAccount.username`, or a
  declaration's `ldapConnectionBootstrap` — a stanza's, a retrieved Secret's own, an accepted ConfigMap
  declaration's. The annotation records who retrieved a token under the configuration of that day; on its word
  alone the password is never presented. The account's Lease is still read and served, so its row stays.
- **Due when** `now − ping_last_attempt ≥ fleet_ping_interval_seconds`, **or** the password digest
  differs from `ping-digest` (a rotation is confirmed once, within one cadence). Both read from the
  Lease inside the claim, so a restart at 23:59 does not ping again at 00:00 and a second replica
```

<!-- block: docs/specs/SPEC_S4c_credential_lifecycle.md | edit -->
```markdown

### 3.12 Verification on the reference cluster — read-only where it matters

The lab cannot fire the normal renewal (§2.3) and **must not** log in as the fleet account. The walk:

1. Deploy the PR head with `release-crc.sh` (the operator's rule: the deployed page, not the
   harness). Before anything: `oc get secret gsd-cluster-shared-rnd -o jsonpath='{.metadata.resourceVersion}'`
   and `oc get oauthaccesstokens -o json | jq '[.items[] | select(.userName=="developer" and .clientName=="openshift-challenging-client")] | length'`.
2. **The ping, as `developer`.** A `saTokenLookup` stanza with `ldapConnectionBootstrap: developer`
   and the password Secret holding `developer`'s password (S4b's live-check arrangement; the
   token-reader Role granted to `developer` on the lab). Set `intervalSeconds` low for the walk.
   Expect: `fleet-ping account=developer target=… last_ok=<ISO>`; the Lease `gsd-fleet-<sha(developer)>`
   with its annotations; `gsd_fleet_account_last_ok_timestamp_seconds` present; the tab's row; the
   Secret's `resourceVersion` **unchanged**; the `developer` token count back to its starting number.
3. **The stand-down.** Rotate the Secret to a wrong password. Expect exactly **one** authorize on the
   oauth-server (its pod log, or the audit log D1 already parses), `login-refused` on the object,
   `fleet-ping-failed … gave_up=true suspended=developer scope=ping`, and *no further authorize
   across three cadences*. Rotate back: one confirming ping within a cadence.
4. **`self-login`, as `developer`.** A `userSelfLogin` stanza with `ldapConnectionBootstrap: developer`
   against `https://api.crc.testing:6443`. Expect the cluster to poll (`gsd_cluster_up 1`), the tab's
   `expires <ISO>` a year out, `renew_at` two hours before it.
5. **The reactive path the lab *can* drive.** `oc delete oauthaccesstoken <the session's object>` as
   cluster-admin. Expect: the next poll's 401, `reauth`, one new login on the following cycle, the
   poll green again — and no refusal recorded. Then a wrong password + the same deletion: the
   re-authentication is refused once, `fleet-credential-suspended … scope=self-login stopped=1`, the
   card critical, and no second authorize.
6. **Two processes.** With the pod running, run a second copy of the app out of cluster against the
   same namespace (`GSD_NAMESPACE`, the pod's ServiceAccount token): the second `claim()` on a held
   Lease is `ClaimHeld`; the authorize count moves by the leader's binds only.
7. `oc get oauthaccesstokens` count for `developer` at the end equals the start; the fleet account's
   count is **untouched at 2** (the pre-existing pair, #286's).

Steps 3 and 5 are the "deliberately wrong password" the Definition of Done asks for. **Both use
`developer`.** A wrong password for `ocp-oauth-bind-serviceid` is never tried, on this lab or any.

### 3.13 Documents

```

```markdown

### 3.12 Verification on the reference cluster — read-only where it matters

The lab cannot fire the normal renewal (§2.3) and **must not** log in as the fleet account. Corrected by #432
(`docs/specs/SPEC_S4e_ping_account_scope.md` §5): as first written, steps 2–3 put `developer`'s password in the
password Secret while the chart still named the fleet account and `gsd-cluster-shared-rnd` recorded it as its
`lookup-account`, so the ping would have presented that password, and then a wrong one, as the fleet account. What
keeps this walk safe is now a rule the code enforces, not care: **nothing the walk deploys names the fleet account**,
and the release presents the password only as an account the configuration names (SPEC_S4e §3.1). The walk:

0. **Two checks before anything is deployed. The walk stops if either fails.**
   - The deployed release carries SPEC_S4e: `/api/version`, read through the pod's loopback, names the release whose
     CHANGELOG entry cites #432, or a later one. On an older release the ping presents the password as every account a
     retrieved Secret records: run with `clusterConfig.fleetAccount.ping.enabled: false` and skip steps 2–3.
   - The walk's values name only `developer`. Render them with `helm template`; in the rendered ConfigMap's
     `clusters.yaml`, `fleetAccountUsername` is `"developer"`, every `ldapConnectionBootstrap` is `developer`, and
     `grep -c ocp-oauth-bind-serviceid` is `0`. (The reference cluster's own values render `1`, so the check tells
     the two apart.)
1. **Baseline, read-only.** `oc get secret gsd-cluster-shared-rnd -o jsonpath='{.metadata.resourceVersion}'`; the
   `openshift-challenging-client` `OAuthAccessToken` counts for `developer` and for the fleet account; the fleet
   account's Lease as JSON (`gsd-fleet-666f1ba7f2fdead0` on the reference cluster), its `resourceVersion` and
   annotations; and the start instant for the oauth-server audit log. Then pause Argo CD's auto-sync and deploy the
   walk's values with `release-crc.sh --values` (the operator's rule: the deployed page, not the harness).
2. **The ping, as `developer`.** The chart's `fleetAccount.username` is `developer`. Its `passwordSecret` names a
   walk-only Secret in the release namespace — never `ldap-oauth-bind-secret`. A `saTokenLookup` stanza,
   `walk-lookup`, points at `https://api.crc.testing:6443` with `ldapConnectionBootstrap: developer`. For the walk,
   `developer` is bound to the estate's `group-sync-dashboard-cluster-poller-token-reader` Role in
   `group-sync-operator` (S4b's rehearsal, `docs/VALIDATION_satokenlookup.md`). The ping runs at most once per
   discovery cadence, so set `intervalSeconds` to 300.

   **The lab check, read-only: run it now, before the walk Secret exists, and again immediately before steps 3 and
   5 place a wrong password. Stop unless all three print `0`.** The deployed configuration, every cluster Secret's
   `ldapConnectionBootstrap`, and every onboarding ConfigMap must name no account but `developer`. A
   `lookup-account` annotation is history and is allowed.

       F=ocp-oauth-bind-serviceid
       oc get configmaps -n group-sync-dashboard group-sync-dashboard-config -o json | jq -r '.data["clusters.yaml"]' | grep -c "${F}"
       oc get secrets -n group-sync-dashboard -l groupsync-dashboard.io/secret-type=cluster -o json \
         | jq --arg f "${F}" '[.items[] | (.data.config // "" | @base64d | fromjson? // {}) | select(.ldapConnectionBootstrap == $f)] | length'
       oc get configmaps -n group-sync-dashboard -l groupsync-dashboard.io/config-type -o json \
         | jq --arg f "${F}" '[.items[] | .data // {} | to_entries[] | select(.value | contains($f))] | length'

   Then create the walk Secret with `developer`'s password. Expect:
   - `fleet-lookup cluster=walk-lookup`, then `fleet-ping target=walk-lookup last_ok=<ISO>`, both as `developer`. If
     `developer`'s password is `developer` (CRC's default), these lines read `account=<redacted>`: that is the
     redactor working, not a failure.
   - `developer`'s Lease, `gsd-fleet-88fa0d759f845b47`, with its annotations, and
     `gsd_fleet_account_last_ok_timestamp_seconds` present.
   - No `fleet-ping` line for the fleet account, and the fleet account's Lease byte-identical to step 1's. Its tab row
     stays, as history: the dashboard reads and serves that Lease, and never reads a password for it.
   - `gsd-cluster-shared-rnd`'s `resourceVersion` unchanged, and the `developer` token count back to its start.
3. **The stand-down.** Run the lab check, then rotate the walk Secret to a wrong password with `oc replace` (never `oc apply`, which would
   copy the value into an annotation). Expect exactly **one** authorize for `developer` in the oauth-server audit log
   (the log D1 already parses), `login-refused` on `developer`'s Lease, `fleet-ping-failed … gave_up=true
   scope=ping`, and *no further authorize across three cadences*. Rotate back: one confirming ping within a cadence.
4. **`self-login`, as `developer`, with the ping still on.** A `userSelfLogin` stanza with `ldapConnectionBootstrap:
   developer` against `https://api.crc.testing:6443`; `developer` is bound to the `group-sync-dashboard-cluster-poller`
   ClusterRole for the walk. Expect the cluster to poll (`gsd_cluster_up 1`), the tab's `expires <ISO>` a year out,
   and `renew_at` two hours before it.
5. **The reactive path the lab *can* drive.** `oc delete oauthaccesstoken <the session's object>` as
   cluster-admin. Expect: the next poll's 401, `reauth`, one new login on the following cycle, the
   poll green again — and no refusal recorded. Then, after the lab check, a wrong password + the same deletion: the
   re-authentication is refused once, `fleet-credential-suspended … scope=self-login stopped=1`, the
   card critical, and no second authorize.
6. **Two processes.** With the pod running, run a second copy of the app out of cluster against the
   same namespace (`GSD_NAMESPACE`, the pod's ServiceAccount token), started from the same walk values:
   the second `claim()` on a held Lease is `ClaimHeld`; the authorize count moves by the leader's binds only.
7. **The end.** The `developer` token count equals the start. The fleet account's is **untouched at 2** (the
   pre-existing pair, #286's). The audit log holds **0** authorizes for the fleet account since step 1's instant, and
   its Lease is byte-identical to step 1's. Remove what the walk created — the walk Secret, its three grants (the two
   above, and the Role that keeps the dashboard ServiceAccount's `get` on `ldap-oauth-bind-secret` while the chart's
   grant points at the walk Secret), `developer`'s Lease and `gsd-cluster-walk-lookup` — and restore with
   `release-crc.sh --argocd main`.

Steps 3 and 5 are the "deliberately wrong password" the Definition of Done asks for. **Both use
`developer`.** A wrong password for `ocp-oauth-bind-serviceid` is never tried, on this lab or any. Since #432 no path
can present one during the walk: step 0 refuses values that name that account, the lab check refuses a lab where
anything else names it, and nothing presents the password as an account the configuration does not name.

### 3.13 Documents

```

<!-- block: docs/CLUSTER_STANZA.md | edit -->
```markdown
| `dashboardController` | bool | this pod's own cluster. Exactly one enabled entry |
| `saTokenLookup` | bool | connection mode: log in as the fleet account, read the poller SA's token |
| `userSelfLogin` | bool | connection mode: poll as the fleet account itself |
| `ldapConnectionBootstrap` | string | the username that performs the login; overrides `clusterConfig.fleetAccount.username` for this cluster |

## 2. The credential — exactly one source

```

```markdown
| `dashboardController` | bool | this pod's own cluster. Exactly one enabled entry |
| `saTokenLookup` | bool | connection mode: log in as the fleet account, read the poller SA's token |
| `userSelfLogin` | bool | connection mode: poll as the fleet account itself |
| `ldapConnectionBootstrap` | string | the username that performs the login; overrides `clusterConfig.fleetAccount.username` for this cluster. The password is still the chart's one `passwordSecret`, so name only an account whose password that Secret holds: nothing but a login can check the pairing. A wrong one is refused, and every path stands down while that password is the latest one refused; the Lease keeps one refusal, so rotating away and back can send it again (SPEC_S4e §3.5, #432) |

## 2. The credential — exactly one source

```

<!-- block: docs/CLUSTER_STANZA.md | edit -->
```markdown
  `execProviderConfig`, `awsAuthConfig`, `proxyUrl`, `disableCompression`, `certData`, `keyData`,
  `serverName`), so a Secret copied from an Argo cluster entry says what is not supported.
- A refused Secret is a **finding on the tab**, never a crashed pod.

A key name is a place a credential can land, so a refusal repeats a key only when it is one this
contract already knows; anything else is described by its length.
```

```markdown
  `execProviderConfig`, `awsAuthConfig`, `proxyUrl`, `disableCompression`, `certData`, `keyData`,
  `serverName`), so a Secret copied from an Argo cluster entry says what is not supported.
- A refused Secret is a **finding on the tab**, never a crashed pod.
- Once the lookup retrieves a Secret-declared cluster, its `config` keeps an explicit `ldapConnectionBootstrap` beside
  the `bearerToken`: it is the account the daily ping may use (#432). The mode keys leave, and a Secret that named no
  account gains none.

A key name is a place a credential can land, so a refusal repeats a key only when it is one this
contract already knows; anything else is described by its length.
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
token is written, the cluster leaves that set and is not retrieved again. The one later use of the LDAP
account is the daily ping (`gsd/poller.py#Poller._ping_accounts`, `clusterConfig.fleetAccount.ping`): once
per account per interval it logs in on ONE retrieved cluster, reads the token Secret there to confirm the
account still works, and stores nothing — confirming is not renewing.

**Why the polling token carries no expiry.** A token that expires needs something to renew it, and
renewal means re-authenticating — which would turn a once-per-onboarding bind into a recurring one
```

```markdown
token is written, the cluster leaves that set and is not retrieved again. The one later use of the LDAP
account is the daily ping (`gsd/poller.py#Poller._ping_accounts`, `clusterConfig.fleetAccount.ping`): once
per account per interval it logs in on ONE retrieved cluster, reads the token Secret there to confirm the
account still works, and stores nothing — confirming is not renewing. It logs in only as an account the
configuration names now — `clusterConfig.fleetAccount.username`, or a declaration's `ldapConnectionBootstrap`
(`gsd/poller.py#Poller._declared_accounts`, #432). A retrieved Secret's `lookup-account` says who fetched its
token; once the configuration stops naming that account, the one password Secret may hold another account's
password, so the ping does not log in as it. Its row and its share of the metrics stay, read from its Lease.

**Why the polling token carries no expiry.** A token that expires needs something to renew it, and
renewal means re-authenticating — which would turn a once-per-onboarding bind into a recurring one
```

<!-- block: local-development/API.md | edit -->
```markdown
answers the values list alone with `last_discovery: null`.

**`fleet`** (#285, `docs/specs/SPEC_S4c_credential_lifecycle.md` §3.10) is the daily ping's setting,
`{"ping": {"enabled": true, "interval_seconds": 86400}}`, and one entry per fleet account as its Lease
holds it: `username`, `lease` (`gsd-fleet-<sha256(username)[:16]>`), `last_attempt`, `last_ok` (null before
the first success), `last_outcome` (`ok` or the finding code the last ping met), `last_target` (the cluster
the last ping attempted, whatever its outcome — `last_ok` may be older), and `suspended` — `[{"target", "since", "code"}]` while a refused entry stands, `[]`
otherwise. A `self-login` cluster's entry carries `session`: `{"state": "current|renewing|suspended|none",
```

```markdown
answers the values list alone with `last_discovery: null`.

**`fleet`** (#285, `docs/specs/SPEC_S4c_credential_lifecycle.md` §3.10) is the daily ping's setting,
`{"ping": {"enabled": true, "interval_seconds": 86400}}`, and one entry per fleet account in use, as its Lease holds
it — including one that only a retrieved Secret's `lookup-account` still records, listed but never pinged (#432): `username`, `lease` (`gsd-fleet-<sha256(username)[:16]>`), `last_attempt`, `last_ok` (null before
the first success), `last_outcome` (`ok` or the finding code the last ping met), `last_target` (the cluster
the last ping attempted, whatever its outcome — `last_ok` may be older), and `suspended` — `[{"target", "since", "code"}]` while a refused entry stands, `[]`
otherwise. A `self-login` cluster's entry carries `session`: `{"state": "current|renewing|suspended|none",
```

<!-- block: docs/CHANGELOG.md | after: ## Unreleased -->
```markdown

- **The daily ping presents the fleet password only as an account the configuration names (#432,
  `docs/specs/SPEC_S4e_ping_account_scope.md`).** The ping took its account from a retrieved cluster's
  `lookup-account` annotation — who fetched that cluster's token, under the configuration of that day — and its
  password from the one Secret the configuration names today. After a username change, a removed stanza or a
  repointed Secret, it sent one account's password as another's: a refused login counted against that account's
  directory entry. On the reference cluster's arrangement, SPEC_S4c §3.12's walk would have sent the fleet account
  `developer`'s password and then a wrong one — 2 refused logins, 3 with a restart (the Epic C walk, PR #433;
  measured hermetically, not run); now 0. The ping's account now comes only from a declaration: the chart's
  `fleetAccount.username`, or an `ldapConnectionBootstrap` — a stanza's, a retrieved Secret's own (retrieval now keeps
  an explicit one), or an accepted ConfigMap declaration's, never its output's annotation. An account nothing names
  any more is still listed on the tab and counted in `/metrics`, from its Lease, and no password is read for it. A
  username with a trailing newline is now refused. The lookup and self-login are unchanged: a stanza naming an
  account whose password the Secret does not hold is refused, and every path stands down while that password is the
  latest one refused. SPEC_S4c §3.12's walk now names only `developer` and re-checks the lab, read-only, before it
  places any password.
```
