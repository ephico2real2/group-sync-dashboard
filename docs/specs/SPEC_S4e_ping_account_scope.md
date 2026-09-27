# SPEC S4e — the fleet password is presented only as an account the configuration names: the daily ping stops taking its account from a retrieved Secret's history (#432)

| | |
|---|---|
| Programme | Epic C (#383), keep the shared fleet login account safe. A correction to SPEC_S4c's daily ping (§3.4) and its lab walk (§3.12), found while preparing the Epic C lab walk (PR #433) |
| Batch | S — cluster configuration |
| Release | — (post-programme; S4's fifth step, a correction to S4c) |
| Version on release | the next application MINOR at merge and the chart PATCH its appVersion move takes; the orchestrator sets both |
| Issue | [#432](https://github.com/ephico2real2/group-sync-dashboard/issues/432) |
| Status | specified |
| Source | OB3's specification of 2026-09-27 (implementer, phase 1: research and the spec, no production code), written from issue #432, PR #433's walk report and its hermetic test, Grok's review of PR #433, OB1-lite's finding N1 on PR #433 (relayed by the orchestrator), SPEC_S4c, SPEC_S4d and main `6740e1e` (application 1.1.0, chart 0.59.3). Measured on this machine, and read-only on the reference cluster. §6's blocks were cut from a copy of `6740e1e` with the design implemented, and applied back to a clean clone for the proof in §4 |

## How to read this spec

Each section opens with its point in one bold line; the rest is the evidence. §1 is the whole change in one table.
§2 is what was read and measured, each with its source. §3 is the design: the rule, the budget over the system, the
change, what must not change, and what is left. §4 maps every test to its result before and after, measured. §5 is
the corrected lab walk. §6 is the change as implementation blocks (`docs/specs/README.md`, "Implementation blocks"),
in apply order:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_S4e_ping_account_scope.md . --apply

Line citations into the code at `6740e1e` are plain text, file:line, to keep them apart from the maintained
`path#anchor` citations. Upstream sources are cited with the commit they were read at, from the raw file with line
numbers (`curl` of the raw bytes, `nl -ba`). "Before" and "after" in §3 and §4 are `6740e1e` without and with §6's
code blocks, with the same test blocks in both.

**The constraint that overrides everything here** is SPEC_S4c's: nothing in this spec, its tests or its walk logs in
as the fleet account, with a right password or a wrong one. The tests use placeholder names against a fake target;
the walk logs in as the htpasswd `developer` only.

## Orchestrator's notes

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
  operator on 2026-09-25 ("Do not start either without the operator picking it up"). This spec does not build it, and
  nothing here is in its way (§2.5).

## 1. The point, in one table

**The daily ping sent today's password as yesterday's account; now every path presents the password only as an
account the configuration names.**

| | |
|---|---|
| **What goes wrong** | The ping logs in as the account a retrieved cluster's Secret *recorded* when its token was fetched (`groupsync-dashboard.io/lookup-account`). Its password is the one Secret the configuration names *today*. When the account changes, the ping sends today's password as yesterday's account: a refused login, counted against that account's directory entry. |
| **Where it was found** | Preparing the Epic C lab walk (PR #433): SPEC_S4c §3.12 steps 2–3 would have sent the fleet account `developer`'s password, then a wrong one. Measured hermetically: 2 refused logins, 3 with a restart. Not run on the lab. |
| **The rule** | A password is presented only as an account the configuration names for it now: the chart's `fleetAccount.username`, or an enabled mode stanza's `ldapConnectionBootstrap` — on every path: the lookup, self-login and the ping. |
| **The change** | One filter in `gsd/poller.py#Poller._ping_accounts`: a retrieved cluster is a ping target, and its account is read and listed, only while the configuration names that account (`gsd/poller.py#Poller._declared_accounts`). |
| **What does not change** | The ping's budget (once per account per interval) and its stand-down; #283's login rules; the lookup; self-login; RBAC; every chart value and template. |
| **What it costs** | An account that only a Secret-declared stanza named is no longer pinged once its cluster is retrieved, because retrieval removes that declaration (§3.5). |

## 2. Read and measured

### 2.1 The code at `6740e1e`: three paths, one password, one path with the wrong account

**The lookup and self-login take their account from the configuration as it is; the ping takes it from an
annotation written at retrieval.**

| path | where | the account it presents | the password |
|---|---|---|---|
| the lookup | fleetlookup.py:417-418, called by `_retrieve_pending` (poller.py:1629-1633) | `fleet_account(settings, cluster)`: the stanza's `ldapConnectionBootstrap`, else the chart's username (fleetlookup.py:235-242) — the pending declaration, now | `fleet_password` (fleetlookup.py:245-269): ONE Secret, for every account |
| self-login | selflogin.py:131-132 | the same function, on the self-login stanza | the same |
| the ping | poller.py:1711-1717, :1801 | `c.lookup_account`: the annotation the lookup wrote when it stored the token (fleetlookup.py:365-366; writer.py:157 for a values stanza's new Secret, :364 for a declaring Secret), read back by the reader (reader.py:94-95), never revised | the same |

Re-verified against the raw file, not taken on trust:

- **The ping set** is `targets`: enabled clusters with `token_source == "remote-lookup"` and a `lookup_account`
  (poller.py:1713-1715). `members` adds the enabled mode stanzas' accounts (poller.py:1716-1717).
- **Due** when there is no attempt yet, when the interval has elapsed, or when `ping-digest` differs from this
  password's digest (poller.py:1786-1788) — so every change of the password Secret makes it due within one discovery
  cadence.
- **The one override** from `lookup_account` is poller.py:1801, `dataclasses.replace(target,
  ldap_connection_bootstrap=account, …)`. The other four `ldap_connection_bootstrap=` sites in `gsd/` set `None` (for a
  poll or a read as a session) or parse a declaration (config.py:1571, parser.py:275).
- **Retrieval removes a Secret's declaration.** `store_lookup` pops every `CONNECTION_KEYS` key,
  `ldapConnectionBootstrap` included, from a declaring Secret (writer.py:353-354). After that, the annotation is the
  only record of which account that stanza named.
- **A values stanza survives beside its Secret.** It stays in `Settings.clusters`, but `ClusterRegistry.merge` serves
  the Secret in its place (registry.py:99-102), so `effective_clusters()` shows the retrieved cluster without the
  stanza's `ldapConnectionBootstrap`.
- **A ConfigMap onboarding's owner digest includes the account** (onboarding.py:59-60:
  `cluster.ldap_connection_bootstrap or settings.fleet_account_username`). Its owned Secret matches, and stays in the
  effective set, only while the declaration names the account it was fetched with.

The reference cluster, read-only (`oc get`, full resource names, the handed kubeconfig), 2026-09-27T13:54:37Z:

| object | value |
|---|---|
| the Deployment | 1 replica, `Recreate`, `quay.io/ephico2real/group-sync-dashboard:1.1.0` |
| `gsd-cluster-shared-rnd` | `resourceVersion` 2835139; `token-source: remote-lookup`; `lookup-account: ocp-oauth-bind-serviceid`; `managed-by: sa-token-lookup` |
| the other cluster Secrets | `gsd-cluster-mock-*` (four) and `gsd-cluster-shared-qa`: no `token-source`, no `lookup-account` |
| the fleet account's Lease, `gsd-fleet-666f1ba7f2fdead0` | `ping-last-attempt` = `ping-last-ok` = `2026-09-27T10:27:05Z`, outcome `ok`, target `shared-rnd`, `ping-digest` `e23c0ea210579dde`, holder `""`: unchanged by #431's release, whose restart did not ping again (B3) |
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
  refuted by the directory once per (account, password), estate-wide, and then every path stands down (SPEC_S4c's B2:
  the entry on the account's Lease). That is the same cost as a wrong password typed into the Secret, which the
  dashboard cannot tell apart without the same login. It is the residual in §3.5, pinned by a test.
- **The ping is different in kind.** Its account is not a declaration at all. `lookup-account` records who fetched a
  token, under the configuration of that day, and nothing revises it (writer.py:157 and :364; reader.py:95). So the ping is the
  only path that presents the password as an account no current declaration names.

### 2.5 The options, measured against the rule

**The smallest rule that holds is a filter in the ping; every other option is larger, breaks a shipped
configuration, or belongs to parked work.**

| option | holds the rule? | what it costs | decision |
|---|---|---|---|
| (a) ping only the chart's `fleetAccount.username` | yes, for the ping | stops the ping for every account a stanza names (`docs/CLUSTER_STANZA.md` §4, row 8: a per-cluster bootstrap account) and for a release with no chart username (`values.yaml`: "Empty = every mode stanza must name its own ldapConnectionBootstrap"); narrows a shipped feature (#291's rule) | rejected |
| (b) a password Secret per account | yes | #369's end state, parked by the operator; a new stanza key in three places; a `get` grant per Secret, so the dashboard ServiceAccount's permissions change; and the ping would still need (d), since an account nothing names has no Secret either | not built |
| (c1) record the account on the password Secret | yes | the Secret is not the release's (`values.yaml`: "The chart does not CREATE it"); on the reference cluster it is the identity provider's `bindPassword` Secret, which the dashboard may only `get`; requiring a new key breaks every install | rejected |
| (c2) record on the Lease which account a password last worked as, and ping only that | yes | the ping could never confirm a rotated password (a new password has no success yet), which is exactly what B3's "a rotated password is pinged once within one discovery cadence" is for | rejected |
| (d) present the password only as an account the configuration names now | yes, on every path | one filter in the ping; an account that only a consumed Secret declaration named loses its ping (§3.5) | **chosen** |

## 3. Design

### 3.1 The rule

**The fleet password is presented only as an account the configuration names for it now.**

The configuration names an account for the password in exactly these places, which
`gsd/poller.py#Poller._declared_accounts` collects:

| where | why it counts |
|---|---|
| `clusterConfig.fleetAccount.username` | the chart pairs it with `passwordSecret` |
| `ldapConnectionBootstrap` on an enabled stanza that declares a mode — values, Secret or ConfigMap; for a values stanza, also after its cluster is retrieved | the stanza names the username; the password stays the chart's |
| a ConfigMap-onboarded cluster's `lookup-account` | SPEC_S5's owner digest includes the account (onboarding.py:59-60), so it always equals what the declaration names now |

Not a place: any other `lookup-account`. It is provenance — who fetched a token, under the configuration of that day.

How each path holds the rule:

| path | how |
|---|---|
| the lookup | unchanged: `fleet_account(settings, cluster)` of the pending declaration, which is one of the places above |
| self-login | unchanged: the same, on the self-login stanza |
| the ping | new: a retrieved cluster is a ping target, and its account a member, only while its `lookup_account` is in `_declared_accounts()` |

An account the configuration stops naming leaves the ping, the tab and `/metrics` at the next discovery cadence.
Its Lease is left as it is — never deleted (SPEC_S4c §5, question 5) — so naming it again brings it back with its gate
and its ping instants.

### 3.2 The budget over the system

**Measured: an account the configuration no longer names is sent nothing, on every event in scope; the one
remaining wrong login is a false declaration's, once, as before.**

The property, with its scope: *a login presents the fleet password only as an account the configuration names for it
now — per process, per replica, across a restart, a Secret rotation, a username change, and a stanza added, removed,
renamed or disabled.* The unit is SPEC_S4c's: an authorize request on the wire, counted by a fake target. Here the
target sits in front of a fake directory that accepts an account's own password and refuses any other, and records
its verdict when the request arrives (§4, `test_the_pairing_budget_over_the_system`).

Each row starts from the lab as found: the chart names FLEET, the Secret holds FLEET's password, and shared-rnd was
retrieved as FLEET and pinged once. Each cell is (sent to an account the configuration no longer names, sent to a
named account with a password that is not its own), before → after:

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

And the Definition of Done's own shape — the corrected §3.12 walk, two accounts and one password Secret: the fleet
account is sent the walk's passwords 2 times in one process and 3 times with a restart before; **0** after
(`test_the_walk_presents_nothing_as_the_fleet_account`). The walk account is sent exactly its budget both times: the
confirming ping, the one deliberate wrong password, and the confirming ping after the rotation back.

The same budget, by path — all three, as the orchestrator asked:

| path | presents the password as | measured by |
|---|---|---|
| the lookup | the account its pending declaration names — unchanged | the "stanza added" row (1 → 1, then gated); `test_the_lookup_and_self_login_present_the_account_their_stanza_names` |
| self-login | the account its stanza names — unchanged | the self-login walk test with the ping on (every authorize is the walk account's, 5 of 5); the pin above (gated after the lookup's refusal: 0 more, a restart included) |
| the ping | an account the configuration names — **new** | every other row, and the walk test (2 and 3 → 0) |

### 3.3 The change, file by file

**One method and one condition in the poller; the rest is tests and the documents that describe the ping.**

| file | change |
|---|---|
| `local-development/gsd/poller.py` | `_declared_accounts`, and `_ping_accounts` keys its targets and members on it; its docstring says so |
| `local-development/tests/test_fleet_lifecycle.py` | the harness's `process()` names USER on the chart, as a configured release names its account. Before #432 nothing in the harness named it, and five tests pinged it only through `lookup-account` |
| `local-development/tests/test_ping_account_scope.py` | new: the Definition of Done, the budget table, the guards against narrowing, the residual's pin |
| `docs/specs/SPEC_S4c_credential_lifecycle.md` | §3.4's "Which target" names the rule; §3.12 rewritten (§5); a note records both |
| `docs/CLUSTER_STANZA.md` | the `ldapConnectionBootstrap` row says the password is still the chart's Secret |
| `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md` | the ping logs in only as an account the configuration names |
| `local-development/API.md` | the `fleet` block lists the accounts the configuration names |
| `docs/CHANGELOG.md` | the `## Unreleased` entry |

Lines added and removed, measured on the applied tree:

| file | added | removed |
|---|---|---|
| `local-development/gsd/poller.py` | +20 | −3 |
| `local-development/tests/test_fleet_lifecycle.py` | +5 | −2 |
| `local-development/tests/test_ping_account_scope.py` | +325 | −0 |
| `docs/specs/SPEC_S4c_credential_lifecycle.md` | +67 | −24 |
| `docs/CLUSTER_STANZA.md` | +1 | −1 |
| `charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md` | +5 | −1 |
| `local-development/API.md` | +2 | −2 |
| `docs/CHANGELOG.md` | +18 | −0 |

### 3.4 What must not change, and what holds each

**Everything the brief lists is untouched by the code, and each has a test or a render that says so.**

| must not change | held by |
|---|---|
| the ping's once-per-account-per-interval budget | the due test (poller.py:1786-1788) is untouched; `test_r3_twenty_clusters_on_one_account_are_one_ping_a_cadence_rotating_by_name` passes with its assertions unchanged |
| the ping's stand-down on a refusal | poller.py:1753-1782 untouched; `test_r4_a_gated_account_is_not_pinged_and_is_said_once` passes with its assertions unchanged |
| #283's login rules | `local-development/gsd/fleetlogin.py` is untouched; `test_fleet_login.py` and `test_fleet_login_basic_scrub.py` pass unchanged |
| the dashboard ServiceAccount's permissions | no chart template or value changes. Rendered RBAC atoms, before and after, for the default values, `environments/crc.yaml`, `environments/example-production.yaml` and `charts/group-sync-dashboard/example-production.yaml`, each with election on and off: REMOVED 0, ADDED 0 in all eight (60 to 70 atoms each) |
| no test or walk logs in as `ocp-oauth-bind-serviceid` | the tests use placeholder accounts against a fake target; the walk names `developer` only, and its step 0 refuses values that name the fleet account (§5) |
| the lookup and self-login | untouched; `test_the_lookup_and_self_login_present_the_account_their_stanza_names` passes before and after |
| every account the configuration names keeps its ping | `test_every_account_the_configuration_names_keeps_its_ping` passes before and after, for the chart's account, a values stanza's and a ConfigMap onboarding's |

### 3.5 What is left, stated

**Four residuals, each bounded, and none that sends a password as an account the configuration does not name.**

1. **A false declaration.** When the chart or a stanza names an account whose directory password is not the Secret's,
   that account is refused once per (account, password), on whichever path presents it first (B2). The dashboard
   cannot tell this from a wrong password in the Secret without that login. Only a credential per account closes
   it: #369, parked. Pinned by `test_the_lookup_and_self_login_present_the_account_their_stanza_names`.
2. **A Secret-declared stanza's own account.** Retrieval removes a Secret's `ldapConnectionBootstrap` along with its
   mode (writer.py:353-354). After that nothing names that account, unless the chart or another stanza does. The
   annotation cannot say whether the stanza named the account or took the default of that day — a default the chart
   may since have changed, which is the username-change row of §3.2. So that account is no longer pinged once its
   cluster is retrieved. Its cluster keeps polling on its retrieved token. To keep the daily confirmation, name the
   account on the chart, in a values stanza, or through a ConfigMap onboarding.
3. **An account the configuration stops naming leaves the tab and `/metrics`.** Its Lease stays untouched, and its
   row returns when it is named again. This is on purpose: `gsd_fleet_account_last_ok_timestamp_seconds` is the oldest
   success among the listed accounts (metrics.py:853-856), so an account nothing will ping again would freeze it and hold
   the documented alert on.
4. **One directory entry under two login names.** Each identity provider matches a login against its own attribute
   (about-ldap.adoc lines 41-45), so one entry can have two login names on two clusters: one password, one counter,
   two names. Named in two stanzas, the password is presented under each name. This is SPEC_S4d's "account is the
   exact username string" residual, unchanged.

### 3.6 The issue's Definition of Done, line by line

**Each line of #432's Definition of Done has its place here, and two of them are finished only after this spec.**

| the issue's line | where it is met |
|---|---|
| *A hermetic test: two accounts, one password Secret. The ping never authorizes as an account whose password the Secret does not hold. It fails before, passes after, and counts the wire.* | `test_the_walk_presents_nothing_as_the_fleet_account` (both cases), with §3.2's table as `test_the_pairing_budget_over_the_system`: each counts authorize requests by their Basic header (§4) |
| *SPEC_S4c §3.12 corrected, reviewed, and walked on the lab as `developer` only. The fleet account's token count stays 2, and its audit-log authorizes stay 0.* | corrected by §6's block 8 (§5 says what changed). Reviewed with this spec. The walk runs after the release that carries §6, and its step 7 records both numbers |
| *Reviewed by two seats other than the implementer, Grok one of them. The minor version bump.* | the orchestrator's: this spec goes to Grok and Codex Astra before any code, and the release commit takes the bump (Orchestrator's notes) |

## 4. Tests, before and after

**Six new test cases fail before and pass after; four pass both ways on purpose; the existing suite is unchanged but
for one harness line.**

"Before" is `6740e1e` plus §6's test blocks only (the harness line and the new file); "after" is `6740e1e` with every
block applied. Run from `local-development/` with `PYTHONPATH=.:tests`, `-p no:cacheprovider`, and `gsd` imported from
the tree under test (printed with each measurement).

| what it proves | test (`local-development/tests/…`) | before | after |
|---|---|---|---|
| the Definition of Done: two accounts, one password Secret — the corrected walk's steps 2–3, the rotation back in the same process | `test_ping_account_scope.py::test_the_walk_presents_nothing_as_the_fleet_account[same-process]` | FAILED `a walk password was presented as FLEET`: `['walk-pw-2', 'wrong-pw-4']` | passed |
| the same, the rotation back after a restart | `…[after-a-restart]` | FAILED: `['walk-pw-2', 'wrong-pw-4', 'walk-pw-2']` | passed |
| Grok's note on PR #433: the walk's self-login arrangement with the ping on | `…::test_the_self_login_walk_arrangement_with_the_ping_on_presents_nothing_as_the_fleet_account[as-found]`, `[carrying-a-refusal]` | FAILED `the first cadence presented a password`: `['fleet-bind-account']` | passed |
| §3.2's budget over the system | `…::test_the_pairing_budget_over_the_system` | FAILED: the measured dict is §3.2's before column | passed |
| an account no longer named leaves the tab and `/metrics` | `…::test_an_account_no_longer_named_leaves_the_served_view` | FAILED: the view serves both accounts, the fleet account's `last_outcome` `login-refused` | passed |
| no narrowing: the chart's account, a values stanza's and a ConfigMap onboarding's keep their ping | `…::test_every_account_the_configuration_names_keeps_its_ping[chart-username]`, `[values-stanza]`, `[configmap-onboarded]` | passed | passed — guards; each fails under its mutant (below) |
| §3.5's first residual, pinned: the lookup and self-login present the account their stanza names, once, then both stand down | `…::test_the_lookup_and_self_login_present_the_account_their_stanza_names` | passed | passed — a pin |
| harness only: the account the ping reads is named on the chart | `test_fleet_lifecycle.py::test_r3_…`, `test_r4_…[login-refused]`, `[login-failed]`, `test_r9_…`, `test_ping_ignores_onboarding_spent_mark_in_same_process` | passed, with or without the harness line | passed; without the harness line, FAILED — the account they ping is named nowhere |
| the walk report's own test (PR #433, not in this tree): reports/2026-09-27_epic-c-walk/hermetic/test_walk_password_scope.py | its four cases | 4 passed | the first test's 2 cases FAILED (`assert [] == ['walk-placeholder-2', 'walk-wrong-3']`), by design — it pins 1.0.0's defect (Orchestrator's notes); the 2 self-login cases passed |

**The whole suite**, `pytest tests/ -q --deselect tests/test_live_smoke.py`, browser tests included, run from
`local-development/` with `PYTHONPATH=.` on each proof tree (a clone of `6740e1e` with this spec's commit):

| tree | result |
|---|---|
| before | `6 failed, 6076 passed, 20 skipped, 4 deselected, 2 warnings in 483.06s` — the six are the new cases above |
| after | `6084 passed, 19 skipped, 4 deselected, 2 warnings in 481.18s` |

The two extra passes after are named, not assumed. One is a citation this change adds, `CLUSTER_CREDENTIALS.md` →
`gsd/poller.py#Poller._declared_accounts` (`test_docs_citations.py`: 1159 passed before, 1160 after, 15 skipped in
both). The other is `test_kyverno.py::test_f3_unreleased_cites_the_current_chart_version_when_it_moved_since_the_last_release`,
which skips while the CHANGELOG has no `## Unreleased` section ("no Unreleased section") and runs, and passes,
once §6's entry adds one.

**The fleet files alone** (`test_fleet_lifecycle.py`, `test_fleet_lifecycle_round3.py`, `test_self_login_url_moved.py`,
`test_fleet_lookup.py`, `test_fleet_login.py`, `test_configmap_onboarding.py`, the three `test_credential_gate_*.py`,
`test_lookup_owned_secret.py`, `test_connection_modes.py`, `test_fleet_login_basic_scrub.py`): `338 passed` on
`6740e1e`; with §6's code but without the harness line, `5 failed, 333 passed` — the five named in the table; with
both, `338 passed`.

**The blocks**, on a clean clone: `python3 local-development/apply-spec-blocks.py
docs/specs/SPEC_S4e_ping_account_scope.md . --apply` reports "12 blocks check out across 8 files", and the applied tree
equals the implemented copy byte for byte in all eight files.

**Every design decision is held by a test.** Each was reverted in the implemented copy and the tests run against the
mutant; all six were caught:

| reverted decision | caught by |
|---|---|
| any `lookup-account` pingable again (`6740e1e`'s rule) | 6 tests: the walk (both cases), the self-login walk with the ping on (both), the budget table, the served view |
| a retrieved values stanza left out (the merge hides it) | `test_every_account_the_configuration_names_keeps_its_ping[values-stanza]` |
| the ConfigMap onboarding clause left out | `test_every_account_the_configuration_names_keeps_its_ping[configmap-onboarded]` |
| the chart's username left out | 9 tests, among them the chart-username guard, R3, R4 and R9 |
| targets filtered but members not (an unnamed account stays listed) | `test_an_account_no_longer_named_leaves_the_served_view` |
| a disabled stanza still naming its account | `test_the_pairing_budget_over_the_system` (the "stanza disabled" row) |

## 5. The corrected walk (SPEC_S4c §3.12)

**Nothing the walk deploys names the fleet account, and the release it runs on presents the password only as an
account the configuration names — so no path can send a walk password as the fleet account.**

§6 rewrites SPEC_S4c §3.12 in place; the whole text is the New side of that block. What changed, and why:

| | as first written | corrected |
|---|---|---|
| the chart's username during the walk | not changed: still the fleet account | `developer` |
| the password Secret | "holding `developer`'s password" — which Secret was not said | a walk-only Secret in the release namespace; never `ldap-oauth-bind-secret` |
| what `gsd-cluster-shared-rnd` recording the fleet account meant | the ping would present the walk's passwords as the fleet account (2, or 3 with a restart) | nothing: the configuration no longer names that account, so it is neither pinged nor read |
| a guard before deploying | none | step 0: the release must carry this spec, and the rendered walk values must name only `developer` |
| `self-login`, steps 4–5 | ping state unstated | the ping stays on; `test_the_self_login_walk_arrangement_with_the_ping_on_presents_nothing_as_the_fleet_account` is its hermetic proof (Grok's note on PR #433) |
| the end | token counts | token counts, 0 audit-log authorizes for the fleet account, and its Lease byte-identical to the baseline |

Step 0's render check, measured with `helm template` on `6740e1e`: PR #433's prepared walk values
(prepared/walk-values-selflogin.yaml at `6545292`) render `fleetAccountUsername: "developer"`, one
`ldapConnectionBootstrap: developer`, and 0 mentions of `ocp-oauth-bind-serviceid`; the reference cluster's own
`environments/crc.yaml` renders 1. The check tells the two apart.

On a release without this spec the ping still reads `lookup-account`, so step 0 keeps PR #433's arrangement there: the
ping off, and steps 2–3 skipped.

## 6. Implementation blocks

**Twelve blocks over eight files, in apply order.** This spec's Status, and its row in `docs/specs/README.md`, move to
`merged` by hand in the implementing commit, beside the applied blocks — a block cannot, because its Old text would
also match inside its own fence — so that `local-development/prepare-release.py` promotes them.

<!-- block: local-development/gsd/poller.py | edit -->
```python
        return ClusterClient(host, timeout=self.settings.request_timeout_seconds), namespace

    def _ping_accounts(self) -> None:
```

```python
        return ClusterClient(host, timeout=self.settings.request_timeout_seconds), namespace

    def _declared_accounts(self, effective: list[ClusterConfig]) -> set[str]:
        """The accounts the configuration names for the ONE fleet password now (#432, SPEC_S4e §3.1): the chart's
        `fleetAccount.username`, whose password `passwordSecret` is; the `ldapConnectionBootstrap` of every enabled
        stanza that declares a mode — a stanza names the username while the password stays the chart's — including
        the values stanza of a retrieved cluster, which the merge hides behind its Secret; and a ConfigMap-onboarded
        cluster's `lookup-account`, which SPEC_S5's connection digest keeps equal to its declaration's account. Any
        other `lookup-account` is provenance: who retrieved a token under an earlier configuration, never revised."""
        s = self.settings
        accounts = {s.fleet_account_username}
        accounts.update(c.ldap_connection_bootstrap for c in (*s.clusters, *effective) if c.enabled and c.connection_mode)
        accounts.update(c.lookup_account for c in effective if c.enabled and c.onboarding)
        return accounts - {"", None}

    def _ping_accounts(self) -> None:
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
        `lookup-account` their Secrets record, in rotation by name — through `lookup(write=False)` under the account
        Lease's claim."""
```

```python
        `lookup-account` their Secrets record, in rotation by name — through `lookup(write=False)` under the account
        Lease's claim. An account is in use only while the configuration names it (`_declared_accounts`, #432): a
        `lookup-account` alone records who retrieved a token under an earlier configuration, and on its word alone
        the password is never presented, nor the account served."""
```

<!-- block: local-development/gsd/poller.py | edit -->
```python
        for c in self.settings.effective_clusters():
            named = c.ldap_connection_bootstrap or self.settings.fleet_account_username
            if c.enabled and c.token_source == CREDENTIAL_LOOKUP and c.lookup_account:
```

```python
        effective = self.settings.effective_clusters()
        declared = self._declared_accounts(effective)      # the only accounts the password is presented as (#432)
        for c in effective:
            named = c.ldap_connection_bootstrap or self.settings.fleet_account_username
            if c.enabled and c.token_source == CREDENTIAL_LOOKUP and c.lookup_account in declared:
```

<!-- block: local-development/tests/test_fleet_lifecycle.py | edit -->
```python
def process(tmp_path, monkeypatch, host: LeaseHost, *clusters: ClusterConfig, discovered=(), name="p", **kw) -> Poller:
    """One dashboard process over `host`: its own store and its own in-memory gate."""
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **k: host)
    s = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"), *clusters],
                 db_path=str(tmp_path / f"{name}.db"), cluster_secrets_writes_enabled=True, **kw)
```

```python
def process(tmp_path, monkeypatch, host: LeaseHost, *clusters: ClusterConfig, discovered=(), name="p", **kw) -> Poller:
    """One dashboard process over `host`: its own store and its own in-memory gate. USER is the chart's fleet
    account, as a configured release names one: the ping presents the password only as an account the
    configuration names (#432, SPEC_S4e), so a `lookup-account` alone no longer makes an account pingable."""
    monkeypatch.setattr("gsd.poller.own_namespace", lambda: "ns")
    monkeypatch.setattr("gsd.poller.ClusterClient", lambda *a, **k: host)
    s = Settings(clusters=[ClusterConfig("host", "https://kubernetes.default.svc", token_env="X"), *clusters],
                 db_path=str(tmp_path / f"{name}.db"), cluster_secrets_writes_enabled=True,
                 **{"fleet_account_username": USER, **kw})
```

<!-- block: local-development/tests/test_ping_account_scope.py | create -->
```python
"""#432 (SPEC_S4e): the fleet password is presented only as an account the configuration names for it now — the
chart's `fleetAccount.username`, or the `ldapConnectionBootstrap` of an enabled stanza that declares a mode — on every
path: the lookup, self-login and the daily ping. Before #432 the ping took its account from a retrieved Secret's
`lookup-account` annotation, which records who retrieved a token under an earlier configuration, and presented
today's password as that account (the Epic C walk, reports/2026-09-27_epic-c-walk: 2 authorizes, 3 after a restart).

The fake target is S4a's, answered by a fake DIRECTORY: an authorize carrying the account's own password gets a
session, any other password a 401 — the directory evaluates the presented password against the entry the login
name resolves to (openshift/oauth-server, pkg/authenticator/password/ldappassword/ldap.go: `l.Bind(entry.DN,
password)`). `presented` decodes each authorize's Basic header, so every assertion counts the wire. No real account
or password appears here: FLEET stands for the lab's fleet account and WALK for the htpasswd `developer`."""

from __future__ import annotations

import base64
import copy
import dataclasses
from datetime import timedelta

import httpx
import pytest

from gsd.config import ClusterConfig
from gsd.fleetstate import FleetLease, lease_digest, lease_name
from gsd.kube import OK
from test_fleet_lifecycle import LeaseHost, process, retrieved, sessions
from test_fleet_login import T0, login_302, refused_401
from test_fleet_lookup import UID, wire  # noqa: F401  (the fixture)

FLEET, WALK, OTHER, STANZA = "fleet-bind-account", "walk-developer", "other-account", "stanza-account"
FLEET_PASSWORD, WALK_PASSWORD, OTHER_PASSWORD, WRONG = "fleet-pw-1", "walk-pw-2", "other-pw-3", "wrong-pw-4"
TOKENS = [f"sha256~V2Fsa1Nlc3Npb25Ub2tlbk51bWJlcj{n:02d}" for n in range(8)]


def credentials(request: httpx.Request) -> tuple[str, str]:
    user, _, password = base64.b64decode(request.headers["authorization"].split(" ", 1)[1]).decode().partition(":")
    return user, password


def presented(target) -> list[tuple[str, str]]:
    """(username, password) of every authorize request, in the order it reached the target."""
    return [credentials(request) for request in target.authorize]


def directory(passwords: dict[str, str], verdicts: list | None = None) -> list:
    """The directory behind the fake OAuth server: an account's own password gets a session, any other a 401.
    `passwords` is read on every request, so a test changes an account's password by assigning into it; `verdicts`
    records (username, accepted) per authorize, judged at the moment it arrived."""
    def answer(request):
        user, password = credentials(request)
        accepted = passwords.get(user) == password
        if verdicts is not None:
            verdicts.append((user, accepted))
        return login_302() if accepted else refused_401()
    return [answer] * 64


def at(name: str, account: str, **kw) -> ClusterConfig:
    """A cluster the lookup retrieved as `account`: its Secret records the account in `lookup-account`."""
    return dataclasses.replace(retrieved(name), lookup_account=account, **kw)


def lab_as_found(tmp_path, monkeypatch, host: LeaseHost) -> None:
    """The lab on 2026-09-27: the chart names FLEET, whose password the Secret holds, shared-rnd was retrieved as FLEET,
    and the product's own daily ping confirmed it once (`gsd-fleet-666f1ba7f2fdead0`, ping-last-ok 10:27:05Z)."""
    host.rotate(FLEET_PASSWORD)
    lab = process(tmp_path, monkeypatch, host, discovered=[at("shared-rnd", FLEET)], name="lab", fleet_account_username=FLEET)
    lab._ping_accounts()
    lab._ping_accounts()                                # inside the interval: not due


# ── the Definition of Done: the corrected §3.12 walk ────────────────────────────────────────────────

@pytest.mark.parametrize("rotation_back", ["same-process", "after-a-restart"])
def test_the_walk_presents_nothing_as_the_fleet_account(tmp_path, monkeypatch, wire, rotation_back):
    """Two accounts, one password Secret (#432's Definition of Done), on the corrected SPEC_S4c §3.12 arrangement:
    the chart names WALK and the Secret holds WALK's password, while shared-rnd's Secret still records FLEET. Step 2
    (the ping as WALK) and step 3 (a wrong password for three cadences, then back), the rotation back in the same
    process and after a restart. FLEET is presented nothing and its Lease is not written; WALK is presented exactly its
    budget: the confirming ping, the one wrong password, the confirming ping after the rotation back. Before #432 FLEET
    was sent WALK's password and the wrong one, and WALK's again after the restart."""
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
    """Grok's note on PR #433: the walk's self-login arrangement (#285 steps 4-5, #310 Part A) with the ping ON — the
    chart names WALK, the Secret holds WALK's password, one self-login stanza on WALK, and shared-rnd retrieved as
    FLEET. Acquisition, a revoked session's re-authentication, a wrong password's suspension, three sweeps, the
    rotation back and a 600 s session's renewal: every authorize is WALK's and the fleet account's Lease is never
    written. Before #432 the first cadence presented WALK's password as FLEET."""
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
    """The chart's username moves from FLEET to OTHER and the Secret to OTHER's password; `then` adds a restart, a
    second process over the same Lease, or a rotation of OTHER's password."""
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
    """A values stanza names STANZA (east, retrieved as STANZA, pinged once; west, a Secret-declared cluster, was
    retrieved as STANZA too). Then the stanza is removed, names another account, or is disabled, and the fleet password
    rotates — STANZA keeps its own."""
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
    """A stanza naming OTHER is added while the Secret holds FLEET's password: the lookup presents it as OTHER, the
    stanza's declaration — refused once, then gated on the Lease, a restart included (B2)."""
    start = len(wire.authorize)
    north = ClusterConfig("north", "https://api.north.example.com:6443", sa_token_lookup=True, ldap_connection_bootstrap=OTHER)
    for name in ("added", "restarted"):
        p = process(tmp_path, monkeypatch, host, north, discovered=[at("shared-rnd", FLEET)], name=name,
                    fleet_account_username=FLEET)
        p._retrieve_pending(); p._ping_accounts()
    return start


def _rotation(tmp_path, monkeypatch, host, passwords, wire):
    """The named account's own password rotates: the ping confirms it once (B3), a restart included."""
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
    """SPEC_S4e §3.2's table, measured: from the lab as found, each event's authorizes as (sent to an account the
    configuration no longer names, sent to a named account with a password that is not its own). The first number is
    #432's property and is 0 everywhere; the second is B2's price for a false declaration, which #432 does not change:
    one per (account, password), whatever the paths, restarts and processes."""
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


# ── what #432 must not narrow ───────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("shape", ["chart-username", "values-stanza", "configmap-onboarded"])
def test_every_account_the_configuration_names_keeps_its_ping(tmp_path, monkeypatch, wire, shape):
    """No narrowing (#291's rule, applied by the orchestrator): an account a current declaration names is still pinged
    once — the chart's; a values stanza's, which the merge hides behind the Secret its lookup wrote; and a ConfigMap
    onboarding's, whose `lookup-account` SPEC_S5's connection digest keeps equal to its declaration's account
    (gsd/clusterconfig/onboarding.py#_connection). Passes before #432 and after."""
    host = LeaseHost()
    host.rotate(FLEET_PASSWORD)
    wire.answers = directory({FLEET: FLEET_PASSWORD, STANZA: FLEET_PASSWORD})
    stanzas, found = (), [at("east", FLEET if shape == "chart-username" else STANZA)]
    if shape == "values-stanza":
        stanzas = (ClusterConfig("east", "https://api.east.example.com:6443", sa_token_lookup=True,
                                 ldap_connection_bootstrap=STANZA),)
    if shape == "configmap-onboarded":
        found = [at("east", STANZA, onboarding=("fleet", "cm-uid-1", "east"))]
    process(tmp_path, monkeypatch, host, *stanzas, discovered=found, fleet_account_username=FLEET)._ping_accounts()
    assert presented(wire) == [(FLEET if shape == "chart-username" else STANZA, FLEET_PASSWORD)]


def test_an_account_no_longer_named_leaves_the_served_view(tmp_path, monkeypatch, wire):
    """The tab and /metrics serve the accounts the configuration names: after the chart's username moves, FLEET's
    Lease is neither read nor served, so `gsd_fleet_account_last_ok_timestamp_seconds` (the OLDEST last success,
    gsd/metrics.py) does not freeze on an account nothing will ping again, and a refusal on it does not hold
    `gsd_fleet_account_suspended` at 1. Before #432 FLEET stayed in the view — refused, after its wrong-password ping."""
    host = LeaseHost()
    wire.answers = directory({FLEET: FLEET_PASSWORD, OTHER: OTHER_PASSWORD})
    lab_as_found(tmp_path, monkeypatch, host)
    host.rotate(OTHER_PASSWORD)
    p = process(tmp_path, monkeypatch, host, discovered=[at("shared-rnd", FLEET), at("north", OTHER)], name="moved",
                fleet_account_username=OTHER)
    p._ping_accounts()
    views = p.signals.fleet_accounts()
    assert set(views) == {OTHER} and not views[OTHER]["suspended"], views


def test_the_lookup_and_self_login_present_the_account_their_stanza_names(tmp_path, monkeypatch, wire):
    """PINS THE STATED RESIDUAL (SPEC_S4e §2.4 and §3.5; OB1-lite's N1 on PR #433). A stanza's
    `ldapConnectionBootstrap` names the username while the password stays the chart's Secret (docs/CHANGELOG.md, chart
    0.49.0), so the lookup and self-login present the one password as the account the stanza names — the operator's
    declaration, which nothing but a bind can check. A declaration the directory refutes costs ONE answered failure
    per (account, password), across both paths and a restart: B2's entry on the account's Lease. The same before #432
    and after."""
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
  - Measured by the orchestrator on the branch: the four tests (N1, N3, and N2's new and amended UI tests) fail without
    the code changes and pass with them; main plus this spec's 102 blocks equals the branch but for the index row.
```

```markdown
  - Measured by the orchestrator on the branch: the four tests (N1, N3, and N2's new and amended UI tests) fail without
    the code changes and pass with them; main plus this spec's 102 blocks equals the branch but for the index row.
- **#432 (`docs/specs/SPEC_S4e_ping_account_scope.md`, 2026-09-27): §3.4's ping and §3.12's walk, corrected in place.**
  The deviation "The ping's targets and accounts" above keyed the ping on the `lookup-account` annotation. That
  annotation records who retrieved a token under the configuration of that day and is never revised, while the
  password is the one Secret the configuration names today. So after a username change, a removed stanza or a
  repointed Secret, the ping presented today's password as yesterday's account. §3.12's steps 2–3 as written would
  have done exactly that on the reference cluster: `developer`'s password, then a wrong one, sent as the fleet account
  (the Epic C walk, PR #433: 2 authorizes, 3 with a restart, measured hermetically; not run). The ping now presents the
  password only as an account the configuration names; SPEC_S4e §3.2 states the budget over the system, and §3.12 is
  rewritten so that nothing the walk deploys names the fleet account.
```

<!-- block: docs/specs/SPEC_S4c_credential_lifecycle.md | edit -->
```markdown
  target 3 within N days and the account's `last_ok` still moves on the days the others answer.
  Decided, not measured; §5.1 says what would change it.
```

```markdown
  target 3 within N days and the account's `last_ok` still moves on the days the others answer.
  Decided, not measured; §5.1 says what would change it. **Only an account the configuration names now is
  pinged** (#432, `docs/specs/SPEC_S4e_ping_account_scope.md` §3.1): the chart's `fleetAccount.username`, or an
  enabled mode stanza's `ldapConnectionBootstrap`. The annotation records who retrieved a token under the
  configuration of that day; on its word alone the password is never presented, nor the account served.
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
   walk-only Secret in the release namespace that holds `developer`'s password — never `ldap-oauth-bind-secret`. A
   `saTokenLookup` stanza, `walk-lookup`, points at `https://api.crc.testing:6443` with `ldapConnectionBootstrap:
   developer`. For the walk, `developer` is bound to the estate's `group-sync-dashboard-cluster-poller-token-reader`
   Role in `group-sync-operator` (S4b's rehearsal, `docs/VALIDATION_satokenlookup.md`). The ping runs at most once per
   discovery cadence, so set `intervalSeconds` to 300. Expect:
   - `fleet-lookup cluster=walk-lookup`, then `fleet-ping target=walk-lookup last_ok=<ISO>`, both as `developer`. If
     `developer`'s password is `developer` (CRC's default), these lines read `account=<redacted>`: that is the
     redactor working, not a failure.
   - `developer`'s Lease, `gsd-fleet-88fa0d759f845b47`, with its annotations, and
     `gsd_fleet_account_last_ok_timestamp_seconds` present.
   - No `fleet-ping` line for the fleet account, and the fleet account's Lease byte-identical to step 1's. While the
     configuration names only `developer`, the fleet account's tab row is absent; it returns when the configuration
     names the account again.
   - `gsd-cluster-shared-rnd`'s `resourceVersion` unchanged, and the `developer` token count back to its start.
3. **The stand-down.** Rotate the walk Secret to a wrong password with `oc replace` (never `oc apply`, which would
   copy the value into an annotation). Expect exactly **one** authorize for `developer` in the oauth-server audit log
   (the log D1 already parses), `login-refused` on `developer`'s Lease, `fleet-ping-failed … gave_up=true
   scope=ping`, and *no further authorize across three cadences*. Rotate back: one confirming ping within a cadence.
4. **`self-login`, as `developer`, with the ping still on.** A `userSelfLogin` stanza with `ldapConnectionBootstrap:
   developer` against `https://api.crc.testing:6443`; `developer` is bound to the `group-sync-dashboard-cluster-poller`
   ClusterRole for the walk. Expect the cluster to poll (`gsd_cluster_up 1`), the tab's `expires <ISO>` a year out,
   and `renew_at` two hours before it.
5. **The reactive path the lab *can* drive.** `oc delete oauthaccesstoken <the session's object>` as
   cluster-admin. Expect: the next poll's 401, `reauth`, one new login on the following cycle, the
   poll green again — and no refusal recorded. Then a wrong password + the same deletion: the
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
can present one during the walk: step 0 refuses values that name that account, and nothing presents the password as
an account the configuration does not name.

```

<!-- block: docs/CLUSTER_STANZA.md | edit -->
```markdown
| `ldapConnectionBootstrap` | string | the username that performs the login; overrides `clusterConfig.fleetAccount.username` for this cluster |
```

```markdown
| `ldapConnectionBootstrap` | string | the username that performs the login; overrides `clusterConfig.fleetAccount.username` for this cluster. The password is still the chart's one `passwordSecret`, so name only an account whose password that Secret holds: nothing but a login can check the pairing, and a wrong one costs that account one refused login per password (#432) |
```

<!-- block: charts/group-sync-dashboard/CLUSTER_CREDENTIALS.md | edit -->
```markdown
account is the daily ping (`gsd/poller.py#Poller._ping_accounts`, `clusterConfig.fleetAccount.ping`): once
per account per interval it logs in on ONE retrieved cluster, reads the token Secret there to confirm the
account still works, and stores nothing — confirming is not renewing.
```

```markdown
account is the daily ping (`gsd/poller.py#Poller._ping_accounts`, `clusterConfig.fleetAccount.ping`): once
per account per interval it logs in on ONE retrieved cluster, reads the token Secret there to confirm the
account still works, and stores nothing — confirming is not renewing. It logs in only as an account the
configuration names now — `clusterConfig.fleetAccount.username`, or a mode stanza's `ldapConnectionBootstrap`
(`gsd/poller.py#Poller._declared_accounts`, #432). A retrieved Secret's `lookup-account` says who fetched its
token; once the configuration stops naming that account, the one password Secret may hold another account's
password, so the ping neither logs in as it nor lists it.
```

<!-- block: local-development/API.md | edit -->
```markdown
`{"ping": {"enabled": true, "interval_seconds": 86400}}`, and one entry per fleet account as its Lease
holds it: `username`, `lease` (`gsd-fleet-<sha256(username)[:16]>`), `last_attempt`, `last_ok` (null before
```

```markdown
`{"ping": {"enabled": true, "interval_seconds": 86400}}`, and one entry per fleet account the configuration names
(#432: an account only a retrieved Secret's `lookup-account` records is not listed), as its Lease holds it: `username`, `lease` (`gsd-fleet-<sha256(username)[:16]>`), `last_attempt`, `last_ok` (null before
```

<!-- block: docs/CHANGELOG.md | edit -->
```markdown
## Application 1.1.0 — chart 0.59.3 — 2026-09-27
```

```markdown
## Unreleased

- **The daily ping presents the fleet password only as an account the configuration names (#432,
  `docs/specs/SPEC_S4e_ping_account_scope.md`).** The ping took its account from a retrieved cluster's
  `lookup-account` annotation — who fetched that cluster's token, under the configuration of that day — and its
  password from the one Secret the configuration names today. After a username change, a removed stanza or a
  repointed Secret, it sent one account's password as another's: a refused login counted against that account's
  directory entry, once per password change. On the reference cluster's arrangement, SPEC_S4c §3.12's walk would have
  sent the fleet account `developer`'s password and then a wrong one — 2 refused logins, 3 with a restart (the Epic C
  walk, PR #433; measured hermetically, not run); now 0. An account the configuration names — the chart's
  `fleetAccount.username`, a stanza's `ldapConnectionBootstrap`, a ConfigMap onboarding's — is pinged as before. One
  that only a `lookup-account` records is no longer pinged, nor listed on the tab or in `/metrics`, so the staleness
  gauge cannot freeze on it; that includes a Secret-declared stanza's own account once its cluster is retrieved,
  because retrieval removes the declaration. The lookup and self-login already used the account the configuration
  names and are unchanged: a stanza naming an account whose password the Secret does not hold still costs that account
  one refused login per password. SPEC_S4c §3.12's walk is rewritten so that nothing it deploys names the fleet
  account.

## Application 1.1.0 — chart 0.59.3 — 2026-09-27
```
