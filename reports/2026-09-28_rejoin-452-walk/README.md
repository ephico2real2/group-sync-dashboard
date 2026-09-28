# #452 on the lab: a Rejoin over a Secret that names its own account — 2026-09-28

**Outcome.** The lab served application 1.6.0 at `268ea63935` throughout (`evidence/step1-version.txt`,
`evidence/end-version.txt`). The walker was `developer`, CRC's htpasswd account, with a disposable `cluster-admin`
binding (SPEC_D4 D4-18).

- The throwaway Secret `gsd-cluster-walk-452` carried its own `ldapConnectionBootstrap` under
  `token-source: remote-lookup`. Discovery accepted it and it polled `auth_failed`.
- Rejoin as `developer` answered `rejoined`. The Secret it wrote has config keys `bearerToken` and `tlsClientConfig`
  only, and `token-source: rejoin`.
- Discovery logged `changed=walk-452` with no new refusal. The row polled `ok`, Refresh answered `connected`, and the
  card stayed on the tab until the walk deleted the Secret.
- Before 1.6.0 the same Rejoin wrote a Secret the parser refuses (`unsupported-config-key`), and the cluster left the
  served set. Step 3 reproduces that hermetically at `0683da6` and shows the pass at `268ea63`.
- Budget: `developer` made **1** `cli` authorize (the Rejoin, `allow`). The fleet account made **0**, kept **2**
  tokens, and its Lease kept resourceVersion 5127386 with the same sha256 of its canonical object excluding
  `managedFields`. `shared-qa` stayed at resourceVersion 2981054, and the PVC UIDs are unchanged.

## Definition of Done (#452)

| #452 row | Verdict | Evidence |
|---|---|---|
| OB2's test fails before and passes after | **PASS** (re-run for this walk) | `evidence/step3-hermetic-0683da6.txt`: `1 failed`, `AssertionError: the rejoined Secret does not load: Finding(… code='unsupported-config-key', detail='config.ldapConnectionBootstrap without saTokenLookup or userSelfLogin configures a login that would never happen')`, gsd 1.5.0 imported from the copy. `evidence/step3-hermetic-268ea63.txt`: `1 passed`, gsd 1.6.0 |
| The full suite is green | not this walk | the implementing PR (#453) |
| Reviewed by two seats other than the author: Grok and Codex | not this walk | the implementing PR (#453) |
| Deployed; the next Rejoin walk shows a rejoined declaring Secret still served | **PASS** | 1.6.0 at `268ea63935`. Before: `config_keys` `bearerToken`, `ldapConnectionBootstrap`, `tlsClientConfig`, and `token-source: remote-lookup` (`evidence/step2-secret.txt`). Rejoin `rejoined · 2026-09-28T02:16:58Z`. After: `config_keys` `bearerToken`, `tlsClientConfig`, and `token-source: rejoin`, with no `lookup-account` (`evidence/step5-end-secret.txt`). `discovery cycle=8 … refused=1 changed=walk-452` (a global count: cycles 7, 8 and 9 each report `refused=1` and no `refused_now`; this walk's captures do not name that refusal). Row `status: ok`, `retired: false`, `findings: []`. Refresh `connected`, CONNECTION `ok` (`evidence/walk-output.txt`, `16`–`18-*-step5-card-served.png`) |

**Must not change** (#452): the Rejoin provenance annotations are all present on the rewritten Secret
(`rejoined-by`, `rejoin-account`, `rejoined-at`, source namespace and ServiceAccount). The lookup's own write keeping
an explicit account was **not exercised on the lab**. That would take a lookup with the fleet password, which this
walk's design rules out. It is covered by the hermetic tests in #453.

## The throwaway Secret's shape, and why it cannot present the fleet password

The Secret is S4e's post-retrieval shape. It has a bearer token (random, bogus, generated inside `scripts/lab.sh`,
never printed, never on a command line), a made-up `ldapConnectionBootstrap: walk-bootstrap-452` that exists in no
directory, `token-source: remote-lookup`, no `lookup-account`, and shared-qa's `tlsClientConfig`
(`{"insecure": false}`, read-only). It was written with `oc create` from a 0600 `mktemp` manifest that the script's
exit trap removes. The file was confirmed gone after the run. `oc create` writes no last-applied annotation, so the
token is not copied into the metadata.

Before the Secret was applied, the code at `268ea63` was read for every caller of `fleet_password`. There are three
call sites, and `lookup()` has two callers:

| Where the password is read | Its gate | This Secret |
|---|---|---|
| `local-development/gsd/fleetlookup.py#lookup`, called by `local-development/gsd/poller.py#Poller._retrieve_pending` | the pending set holds only clusters whose `credential_kind` is `CREDENTIAL_LOOKUP` | `credential_kind` is `bearer`: a `token_value` wins in `local-development/gsd/config.py#ClusterConfig.credential_kind` |
| `local-development/gsd/fleetlookup.py#lookup` again, called by `local-development/gsd/poller.py#Poller._ping_accounts` on a target | a target needs `token_source == remote-lookup` **and** a `lookup_account` | `lookup_account` is `None`: `local-development/gsd/clusterconfig/reader.py#discover` takes it only from the `lookup-account` annotation |
| `local-development/gsd/poller.py#Poller._ping_accounts`'s own read, in its loop over `members` | a member is a target, or has `connection_mode is not None` | neither: `connection_mode` is `None` |
| `local-development/gsd/selflogin.py#SelfLoginSessions.credential_for` | `local-development/gsd/poller.py#Poller._run_cluster` calls it only when `credential_kind == CREDENTIAL_SELF_LOGIN` | not self-login |

The made-up account does enter two sets that only filter:

- `local-development/gsd/poller.py#Poller._declared_accounts`. The ping loop only reads it for accounts in `members`.
- `local-development/gsd/rejoin.py#fleet_accounts`. It is Rejoin's refusal list for usernames.

Neither starts a login. `evidence/step3-shape-parse.txt` runs the shape through the application's own parser:
`credential_kind='bearer' connection_mode=None credential_pending=None lookup_account=None`. The same shape under
`token-source: rejoin`, which is what a pre-fix Rejoin wrote, is `unsupported-config-key`.

On the lab this held for the whole walk (`evidence/end-podlog.txt`, from 02:13:57Z): `fleet-lookup` 0,
`fleet-lookup-failed` 0, `fleet-ping` 0, `fleet-ping-failed` 0, lines naming the fleet account 0. There was still one
fleet-account Lease (`evidence/*-leases.txt`), and the API's fleet view never named `walk-bootstrap-452`
(`fleet_names_walk_account: false` at every read in `evidence/walk-output.txt`).

## Step by step

| Step | When (UTC) | What came back | Evidence |
|---|---|---|---|
| 1 | 02:13:57 | `shared-qa` at resourceVersion 2981054. The Lease at resourceVersion 5127386, sha256 `96e37278…`. One fleet-account Lease. Tokens (`openshift-challenging-client`): `developer` 3, the fleet account 2. `can-i`: `no`. No binding and no entry. 0 audit events since the start instant. PVC UIDs: data `f065b7a4-…`, report-artifacts `08c7d45c-…` | `evidence/step1-*.txt` |
| 2 | 02:14:25 – 02:14:55 | `secret/gsd-cluster-walk-452 created` (uid `b5fbb006-…`, resourceVersion 5653358). Discovery `cycle=7 … added=walk-452` and `cluster-resolved … credential=bearer tls=trusted-bundle`. The first poll: `cluster-unreachable … outcome=auth_failed … 401 Unauthorized — token invalid or expired`. The `shared-api-url` warning appeared for `shared-qa,shared-rnd,walk-452` (the card's **shared API URL** chip) | `evidence/step2-apply.txt`, `step2-secret.txt`, `step2-podlog.txt` |
| 3 | 02:13:14 (hermetic) | The #452 test at `0683da6`: `1 failed` on `unsupported-config-key`. At `268ea63`: `1 passed`. The shape parse above. No lab write | `evidence/step3-*.txt`, `scripts/shape.py` |
| 4 | 02:15:18 – 02:16:59 | The binding `walk-452-cluster-admin` and the walk's label; `can-i`: `yes`. A 75 s wait for the tier cache, then the walk as `developer`: `cluster_admin: true`. The row read `auth_failed`, `rejoinable: true`, `findings: []`. Refresh answered `auth_failed · 2026-09-28T02:16:52Z` with "use Rejoin". The dialog opened with both fields empty. Rejoin answered `rejoined · 2026-09-28T02:16:58Z` and the dialog closed | `evidence/step4-*.txt`, `evidence/walk-output.txt`, `01`–`12-*.png` |
| 5 | 02:16:58 – 02:18:52 | The Secret (resourceVersion 5655629, uid unchanged): config keys `bearerToken`, `tlsClientConfig`; `token-source: rejoin`, `rejoined-by: developer`, `rejoin-account: developer`, `rejoined-at: 2026-09-28T02:16:58Z`, `source-namespace: group-sync-operator`, `source-service-account: group-sync-dashboard-cluster-poller`, no `lookup-account`. Discovery `cycle=8 … changed=walk-452`, no `refused_now`. At 02:17:55 the poll read 61 users and 66 groups. The row read `status: ok`, `retired: false`, `findings: []`. Refresh answered `connected · 2026-09-28T02:17:57Z — authenticated as system:serviceaccount:group-sync-operator:group-sync-dashboard-cluster-poller`. The CONNECTION row read `ok reachable 2026-09-28 02:17` at 02:18:49 | `evidence/step5-*.txt`, `13`–`18-*.png` |
| 6 | 02:19 | Audit since 02:13:57Z: `developer` 1 `cli` authorize (`allow`, 02:16:58Z), 0 `deny`. The fleet account 0 events, 0 authorizes. Its tokens 2. The Lease resourceVersion 5127386 with the same sha256 | `evidence/step6-*.txt` |
| 7 | 02:19:21 – 02:23:30 | The Secret and the binding deleted **by the walk's label**. Discovery `cycle=9 … removed=walk-452` at 02:21:59, then `walk-452: its Secret is gone; the poll thread stops (history kept)`, and the `shared-api-url` warning `state=cleared`. The walk's label selects no binding, the Secret is gone, and `can-i` answers `no`. After 70 s, a fresh login as `developer` answered `cluster_admin: false` and `/api/clusterconfigs` `403`. The end checks are in the budget table | `evidence/step7-delete.txt`, `evidence/end-*.txt` |

**Step 4's and step 5's log lines**, from `evidence/step5-podlog.txt`. The `sha256~` names are redacted by the
capture. Every other `<redacted>` is the application's own (see "What came back").

```text
22:16:52,923 cluster-refreshed cluster=walk-452 credential=bearer by=developer outcome=auth_failed
22:16:58,291 fleet-login cluster=walk-452 account=<redacted> tls=trusted-bundle rejoin_by=<redacted> oauth=https://oauth-openshift.apps-crc.testing expires_at=2027-09-28T02:16:58Z
22:16:58,318 cluster-rejoin-review cluster=walk-452 by=<redacted> account=<redacted> question="update clusterrolebindings" allowed=true reason="RBAC: allowed by ClusterRoleBinding 'walk-452-cluster-admin' of ClusterRole 'cluster-admin' to User '<redacted>'"
22:16:58,374 fleet-logout cluster=walk-452 account=<redacted> tls=trusted-bundle rejoin_by=<redacted> token=sha256~<redacted> outcome=revoked
22:16:58,498 cluster-secret-rotated secret=gsd-cluster-walk-452 namespace=group-sync-dashboard cluster=walk-452 by=developer
22:16:58,499 cluster-rejoined cluster=walk-452 by=<redacted> account=<redacted> secret=gsd-cluster-walk-452 written=updated revoked=true
22:16:58,709 discovery cycle=8 namespace=group-sync-dashboard seen=7 accepted=6 refused=1 changed=walk-452
22:17:57,132 cluster-refreshed cluster=walk-452 credential=bearer by=developer outcome=ok
```

The times are the pod's local zone (EDT, UTC−4). The `fleet-login`/`fleet-logout` event names belong to the login
module, which Rejoin shares. These two lines carry `rejoin_by` and are `developer`'s own login and revoke: the audit
log's one `cli` authorize at 02:16:58Z is `developer`'s, and the fleet account has 0.

## The budget, from the audit log and the token list

These are counts from the oauth-server audit log, read through a pipe and never written (`evidence/end-audit.txt`,
from 02:13:57Z).

| Count | This walk | The brief expects |
|---|---|---|
| Rejoin presses | 1 | — |
| `developer` `cli` authorizes (`client_id=openshift-challenging-client`) | **1**: `allow` 02:16:58Z | one, for the Rejoin |
| the other `developer` events | 2 `credential` + `session` pairs: the walk's browser login (02:16:44Z) and the `after` login (02:23:22Z), both through the dashboard's proxy | — |
| the fleet account's annotated events, and its authorizes | **0** and **0** | 0 |
| the fleet account's tokens (`openshift-challenging-client`) | 2 at step 1, step 6 and the end | 2 |
| `developer`'s `openshift-challenging-client` tokens | 3 at step 1, step 5 and the end: the Rejoin login was revoked | unchanged |
| the fleet account's Lease | resourceVersion 5127386, sha256 `96e3727807355ca1…` of the canonical object excluding `managedFields`, equal at step 1, step 6 and the end | unchanged |
| fleet-account Leases | 1 at step 1, step 6 and the end | no Lease for the made-up account |
| `gsd-cluster-shared-qa` resourceVersion | 2981054 at step 1 and at the end | equal |
| PVC UIDs | data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, identical at both ends | unchanged |

## What came back that the brief does not say

1. **The account name is redacted in the Rejoin answer and in the login, review and logout lines**
   (`Signed in to walk-452 as <redacted>`, `account=<redacted> rejoin_by=<redacted>`). This is #316's item 1, seen
   again: CRC's `developer` password is the same as its username, and the application scrubs the password by value
   (`reports/2026-09-27_rejoin-walk/README.md`). The Secret's `rejoined-by`/`rejoin-account` and the
   `cluster-secret-rotated … by=developer` line name `developer` as written. Password fields are empty in every
   captured dialog, and no live bearer-token value or unredacted `sha256~` token appears in this report. The scripts
   read the password from `crc console` into the walk's environment only. The literal string `developer` is
   retained as a username in scripts, evidence and screenshot text; because it also equals this lab account's
   reported CRC-default password, the password value is not absent from the report. Two synthetic tokens are: the
   test fixture quoted in `evidence/step3-hermetic-0683da6.txt`, and the all-zero dummy `scripts/shape.py` builds.
   The fleet account's login name is not in this folder.
2. **After `rejoined`, the closed dialog's message element still read `Signing in once…`**
   (`dialog after the answer` in `evidence/walk-output.txt`). The dialog was closed with both fields empty. Whether
   the next open clears it was not measured in this walk.

## How to run it again

```sh
export KUBECONFIG=<the lab kubeconfig>
F=reports/2026-09-28_rejoin-452-walk
T0=$(date -u +%Y-%m-%dT%H:%M:%SZ); echo "${T0}" > "$F/evidence/step1-start-instant.txt"
for k in version pvcs sharedqa lease leases tokens cani grant secret tiers; do "$F/scripts/capture.sh" "$k" step1; done
"$F/scripts/capture.sh" audit step1 "${T0}"
"$F/scripts/lab.sh" apply                     # then wait for `discovery … added=walk-452` and an auth_failed poll
"$F/scripts/lab.sh" grant                     # then wait more than 60 s: the tier cache
GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
  local-development/.venv/bin/python "$F/scripts/walk.py" walk
"$F/scripts/capture.sh" audit step6 "${T0}"; for k in lease leases tokens; do "$F/scripts/capture.sh" "$k" step6; done
"$F/scripts/lab.sh" delete                    # always: the Secret and the binding by the walk's label
# once the pod logs `discovery … removed=walk-452` and 60 s have passed:
GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
  local-development/.venv/bin/python "$F/scripts/walk.py" after
for k in version pvcs sharedqa lease leases tokens tiers grant cani secret; do "$F/scripts/capture.sh" "$k" end; done
"$F/scripts/capture.sh" audit end "${T0}"; "$F/scripts/capture.sh" podlog end "${T0}"
```

Step 3 runs outside the worktree, on `git archive` copies of `0683da6` and `268ea63`, with the test file copied from
`268ea63` into the older copy and `PYTHONPATH=<copy>/local-development`.
