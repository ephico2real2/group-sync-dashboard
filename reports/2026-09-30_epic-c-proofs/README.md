# Epic C's two outstanding proofs on the lab: #291's live login and #285's fleet row — 2026-09-30

**Outcome.** The lab served application 2.0.0 at commit `b40b5cf82a` before and after the walk
(`evidence/start-version.txt` at 15:14:33Z, `evidence/end-version.txt` at 15:21:45Z), in pod
`group-sync-dashboard-7b9485f499-66q2z` with 0 restarts (`evidence/start-pod.txt`, `evidence/end-pod.txt`). Both
proofs were run as `developer`, CRC's htpasswd account. Nothing logged in as the fleet account.

- **#291 (PROOF 1).** `local-development/tests/test_live_fleet_login.py` passed against `https://api.crc.testing:6443`
  as `developer`: `1 passed in 121.12s`. The test read `developer`'s `openshift-challenging-client` OAuthAccessToken
  count as **6 before, 7 during, 6 after** (`evidence/p1-pytest.txt`). The separate `oc` counts around it were
  6 and 6 for `developer` and **2 and 2** for the fleet account (`evidence/p1-before-tokens.txt`,
  `evidence/p1-after-tokens.txt`).
- **#285 (PROOF 2).** The Cluster Configurations tab's `#cc-head` card shows one fleet-account row:
  `fleet account <fleet account> · last confirmed 2026-09-29 17:57 · last ping shared-rnd: ok`, with no `suspended`
  badge because the Lease holds no suspended entry. It is captured at 1280 px and 375 px, and the page does not scroll
  sideways at either width (`evidence/fleet-rows-1280.json`, `evidence/fleet-rows-375.json`). `GET
  /api/clusterconfigs` answered 200 with the `fleet` object that the row is painted from
  (`evidence/api-clusterconfigs-fleet.json`). The fleet account's name is masked in every screenshot. OCR finds it
  0 times in the 8 committed PNGs and once in each of the 2 unmasked controls (`evidence/ocr-redaction.txt`).
- **The self-login row** cannot be shown on the lab, because the lab has no `userSelfLogin` cluster
  (`evidence/selflogin-absent.txt`). The hermetic test
  that covers it passed: `1 passed, 2 warnings in 3.76s` (`evidence/self-login-hermetic-test.txt`).

The grant stood twice, for 84 s and then 83 s. The first run's mask also covered the row's instant (see "Run 1").
`can-i update clusterrolebindings --as=developer` answered `no`, `yes`, `no` in each run. Nothing carries the label
`walk.gsd.lab/run=epic-c-proofs-2026-09-30` at the end (`evidence/end-label-check.txt`: `No resources found`).

## PROOF 1 — #291's live proof as `developer`

#291's Definition of Done: *"The live proof is re-run as `developer`, never the fleet account:
`tests/test_live_fleet_login.py`, with `OAuthAccessToken` count before, during and after = n, n+1, n."*

`reports/2026-09-30_epic-c-proofs/scripts/proof1.sh` ran it. The command line is the first lines of
`evidence/p1-pytest.txt`, and it is the one the module docstring gives:

- `GSD_LIVE_LOGIN_API=https://api.crc.testing:6443` and `GSD_LIVE_LOGIN_USER=developer`.
- `GSD_LIVE_LOGIN_PASSWORD` came from `crc console --credentials` into the test's environment only.
- `GSD_LIVE_LOGIN_CA` was a temporary file outside the repo holding `openshift-config/enterprise-and-cluster-ca-bundle`,
  as `reports/2026-09-27_epic-c-walk/README.md` ("How to resume", step 2) names it. The bundle holds 6
  certificates. `openssl s_client` verified both `api.crc.testing:6443` and `oauth-openshift.apps-crc.testing:443`
  against it with `Verify return code: 0 (ok)` (`evidence/p1-ca-check.txt`).
- `KUBECONFIG` was the lab's cluster-admin kubeconfig, so the test's `oauth_token_count` read the token objects itself.

| What | Value | Evidence |
|---|---|---|
| The test's result | `tests/test_live_fleet_login.py::test_the_session_is_obtained_and_revoked PASSED`, `1 passed in 121.12s (0:02:01)`, from 15:14:43Z to 15:16:44Z | `evidence/p1-pytest.txt` |
| The session | `account=developer issuer=https://oauth-openshift.apps-crc.testing expires_in=31536000 expires_at=2027-09-30T15:14:43Z`. The token's name is redacted to `sha256~<redacted>` | `evidence/p1-pytest.txt` |
| n, n+1, n (the test's own counts, `developer`, `openshift-challenging-client`) | `count_before=6 count_during=7`, then `count_after=6 (before=6)`. The test also asserts that the session's own token name is in the during-set and absent after | `evidence/p1-pytest.txt`; the asserts are in `local-development/tests/test_live_fleet_login.py#test_the_session_is_obtained_and_revoked` |
| The token's death | `the revoked token stopped authenticating after 121 s (the API server's token cache)` | `evidence/p1-pytest.txt` |
| `developer`, `openshift-challenging-client`, read with `oc` before and after | 6 at 15:14:43Z, 6 at 15:16:45Z after the test | `evidence/p1-before-tokens.txt`, `evidence/p1-after-tokens.txt` |
| The fleet account, read with `oc` before and after (name in a shell variable, counts only) | `openshift-challenging-client` 2 → 2, any client 2 → 2 | `evidence/p1-before-tokens.txt`, `evidence/p1-after-tokens.txt` |

The fleet account's count is also 2 at the walk's start and end (`evidence/start-tokens.txt`,
`evidence/end-tokens.txt`). The dashboard's log for the whole window has 0 `fleet-login`, 0 `fleet-ping` and 0
`fleet-lookup` lines (`evidence/end-podlog.txt`).

## PROOF 2 — #285's fleet-account row

SPEC_S4c §3.10 defines the row (`docs/specs/SPEC_S4c_credential_lifecycle.md`): *"one row per account —
`fleet account <username> · last confirmed <instant> · last ping <target>: <outcome>`, `not yet confirmed by the
daily ping` before the first success, and a `suspended` badge while the account's Lease holds an entry"*. The page
builds it in `local-development/gsd/static/index.html#function ccFleetRows`.

The tab needs the cluster-admin tier (`require_cluster_admin` in `local-development/gsd/api.py`), which `developer`
does not hold. `evidence/p2-before-cani.txt` shows `no`. So `reports/2026-09-30_epic-c-proofs/scripts/proof2.sh`
worked in this order:

1. It set the exit trap that deletes by label.
2. It created the temporary grant `reports/2026-09-30_epic-c-proofs/scripts/grant.yaml`: a ClusterRole with `update` on
   `clusterrolebindings`, bound to `developer`, both labelled `walk.gsd.lab/run=epic-c-proofs-2026-09-30`.
3. It waited 70 s for the tier's cache, then ran `reports/2026-09-30_epic-c-proofs/scripts/rows.py`.
4. It deleted the grant.

A route guard in `rows.py` aborted any request to `/api/` that was not a GET, and none was attempted
(`evidence/p2-rows.txt`: `PASS no write was attempted`).

| What | Value | Evidence |
|---|---|---|
| `developer`'s tier with the grant | `{"user": "developer", "cluster_admin": true}` | `evidence/p2-rows.txt` |
| `GET /api/clusterconfigs` → `fleet` (username replaced by `<fleet account>`) | `http 200`; `ping` `{"enabled": true, "interval_seconds": 86400}`; one account with `lease` `gsd-fleet-666f1ba7f2fdead0`, `last_attempt` and `last_ok` both `2026-09-29T17:57:32Z`, `last_outcome` `ok`, `last_target` `shared-rnd`, `suspended` `[]` | `evidence/api-clusterconfigs-fleet.json` |
| The row at 1280 px | `fleet account <fleet account> · last confirmed 2026-09-29 17:57 · last ping shared-rnd: ok`, badges `[]`, `innerWidth 1280`, `scrollWidth 1280` | `evidence/fleet-rows-1280.json`; `screenshots/01-1280-cc-head.png`, `screenshots/02-1280-fleet-row.png` |
| The row at 375 px | The same text and badges `[]`, `innerWidth 375`, `scrollWidth 375` | `evidence/fleet-rows-375.json`; `screenshots/03-375-cc-head.png`, `screenshots/04-375-fleet-row.png` |
| The walker's checks at each width | One row per API account, SPEC_S4c §3.10's shape, `last confirmed` equal to the API's `last_ok` to the minute, `last ping shared-rnd: ok` equal to the API's `last_target` and `last_outcome`, `suspended` painted exactly when the Lease holds an entry, no sideways scroll, no page error, no `Dashboard API error`: every line `PASS`, `failures: []` | `evidence/p2-rows.txt`, `evidence/p2-exit.txt` (`rows.py exit=0`) |
| `not yet confirmed by the daily ping` and the `suspended` badge | Not on the lab. The lab's account was confirmed on 2026-09-29 and its Lease has no suspended entry. Both branches are asserted by the hermetic test named below, which is fed one confirmed and suspended account and one account never confirmed | `evidence/api-clusterconfigs-fleet.json`; `evidence/self-login-hermetic-test.txt` |

The API and the row agree with the fleet Lease. The ping last ran at 2026-09-29T17:57:32Z, and with
`interval_seconds 86400` it was not due again during the walk. The pod log's window has 0 `fleet-ping` lines
(`evidence/end-podlog.txt`), and the Lease stayed at resourceVersion 7043788 with holder `""`
(`evidence/start-lease.txt`, `evidence/end-lease.txt`).

### The masking, and the OCR check that proves it

The row prints the fleet account's name, so every capture masks it at the moment it is taken. Three masks are used
together:

- the name's own span, `[data-cc-fleet] .v > .mono:first-child`;
- every element whose text names the account;
- an opaque box over each rendered occurrence of the name, from `Range.getClientRects()` over the matched substring
  (`TEXT_BOXES_JS` in `rows.py`, copied from `reports/2026-09-30_release-2.0.0-walk/scripts/e2e_masked.py`).

`evidence/mask-log.jsonl` records the counts per screenshot: 1 row span, 1 element naming the account and 1 text box
in each.

`reports/2026-09-30_epic-c-proofs/scripts/ocr-redaction.sh` then ran macOS Vision OCR over every PNG in this folder.
It counted the recognised lines that name the account, matching the full name or its middle fragment (`cut -d-
-f2-3`), case-insensitively (`evidence/ocr-redaction.txt`):

| Image | Lines naming the account |
|---|---|
| positive control: the fleet row, 1280 px, UNMASKED (outside the repo, deleted after the check) | 1 |
| positive control: the `#cc-head` card, 1280 px, UNMASKED (outside the repo, deleted after the check) | 1 |
| each of the 8 committed PNGs (`screenshots/0[1-4]-*.png`, `screenshots/run1/0[1-4]-*.png`) | 0 |

### Run 1, and why the grant was taken twice

The first run, from 15:17:32Z to 15:18:56Z (84 s), is kept in `evidence/run1/` and `screenshots/run1/`. The walker
had two defects there, and both are fixed in the committed `rows.py`:

- **The mask selector matched the instant.** The run used `[data-cc-fleet] .v > .mono`, the selector the earlier walks
  masked with. In this row it also matches the `last confirmed` instant's `<span class="mono">`. The mask log shows
  `fleet_row_elements: 2` (`evidence/run1/mask-log.jsonl`), and the screenshots show the instant under a magenta box
  (`screenshots/run1/02-1280-fleet-row.png`). Since the row's instant is what #285 asks to see, the captures were
  retaken with `:first-child`, which matches the name's span only (`fleet_row_elements: 1` in
  `evidence/mask-log.jsonl`).
- **The shape check read the uppercased label.** The run read the row with `innerText`, and `.cc-kv .k` is
  `text-transform: uppercase` in `local-development/gsd/static/app.css`, so the text began `FLEET ACCOUNT`. The shape
  check failed on that alone (`evidence/run1/p2-rows.txt`: two `FAIL … shape` lines, and every other check `PASS`).
  The committed walker reads the label with `textContent`. It keeps the `innerText` form as `inner_text`
  (`evidence/fleet-rows-1280.json`).

The same defect is on record from the #244 walk, which named it (`reports/2026-09-29_ca-244-walk/README.md`).

Run 2 stood from 15:19:53Z to 15:21:16Z, 83 s (`evidence/grant-window.txt`). Its 70 s are the tier cache's wait.
The two windows total 167 s.

## The self-login row

SPEC_S4c §3.10 also defines `self-login · expires <instant>` on a `userSelfLogin` cluster's credential row. The lab
has no `userSelfLogin` cluster (`evidence/selflogin-absent.txt`, read at 15:23:55Z):

- 0 of the 6 cluster Secrets declare `userSelfLogin: true`, and all 6 configs parse as JSON objects, so the 0 is not
  a parse failure;
- 0 of the release's 163 non-empty `clusters.yaml` lines name it;
- there are 0 onboarding ConfigMaps.

Creating one is #310 Part A's job, which waits on the operator, so this walk did not create one.

The row is covered hermetically by
`local-development/tests/test_ui.py#TestClusterConfigPage.test_the_fleet_account_rows_and_a_self_login_expiry_are_instants`.
The test parses a `userSelfLogin` Secret, feeds the page a session expiring `2026-09-23T06:00:05Z`, and asserts the
following at 375 px:

- the credential row reads `self-login` and `expires 2026-09-23 06:00`;
- the fleet rows read `last confirmed 2026-09-22 06:00 · last ping shared-rnd: ok` with `suspended`, and
  `not yet confirmed by the daily ping`;
- the page does not scroll sideways.

It passed on this worktree's head `b7d120ca9b`: `…[chromium] PASSED`, `1 passed, 2 warnings in 3.76s`
(`evidence/self-login-hermetic-test.txt`).

## Before and after

| What | Start | End | Evidence |
|---|---|---|---|
| `/api/version` (pod loopback) | `2.0.0`, `b40b5cf82a`, leader | the same | `evidence/start-version.txt`, `evidence/end-version.txt` |
| Chart and images | `group-sync-dashboard-0.59.25`, both images `2.0.0` | the same | `evidence/start-chart.txt`, `evidence/end-chart.txt` |
| PVC UIDs | data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` | the same | `evidence/start-pvcs.txt`, `evidence/end-pvcs.txt` |
| `gsd-cluster-shared-qa` | resourceVersion 2981054 | 2981054 | `evidence/start-sharedqa.txt`, `evidence/end-sharedqa.txt` |
| Every cluster Secret's resourceVersion | six Secrets | all six unchanged | `evidence/start-secrets.txt`, `evidence/end-secrets.txt` |
| The fleet Lease | 1 Lease, resourceVersion 7043788, holder `""` | the same | `evidence/start-lease.txt`, `evidence/end-lease.txt` |
| The fleet account's tokens | `openshift-challenging-client` 2, any client 2 | 2, 2 | `evidence/start-tokens.txt`, `evidence/end-tokens.txt` |
| `developer`'s tokens | `openshift-challenging-client` 6, any client 71 | 6, 73 | `evidence/start-tokens.txt`, `evidence/end-tokens.txt` |
| Argo CD | `Synced`, `Degraded`, revision `b7d120ca9b…`. The only resource not Healthy is the CronJob `group-sync-dashboard-report-nightly-namespace-access` (*"CronJob has not completed its last execution successfully"*) | the same | `evidence/start-argo.txt`, `evidence/end-argo.txt` |
| The nightly CronJob | last schedule `2026-09-30T02:00:00Z`, last success `2026-09-29T02:00:11Z` | the same. Recorded, not fixed | `evidence/start-cronjob.txt`, `evidence/end-cronjob.txt` |
| `can-i update clusterrolebindings --as=developer` | `no` | `no` | `evidence/start-cani.txt`, `evidence/end-cani.txt` |
| Anything carrying the walk's label | none | `No resources found` | `evidence/start-grant.txt`, `evidence/end-label-check.txt` |

`developer`'s any-client count rose by 2. Those are the two UI logins of PROOF 2, one per run. They are
`system:serviceaccount:group-sync-dashboard:group-sync-dashboard` tokens created at 15:18:44Z and 15:21:06Z, and no
other `developer` token was created during the walk (`evidence/end-developer-tokens-since-start.txt`). PROOF 1's
`openshift-challenging-client` token is not among them: its session revoked it.

The dashboard's log from 15:14:32Z to 15:21:48Z has 283 lines. It has 0 `fleet-lookup`, `fleet-ping`,
`fleet-login`, `fleet-login-refused`, `fleet-login-failed` and `fleet-logout` lines, and 0 lines naming the fleet
account. It also has 0 Traceback lines and 0 lines containing `ERROR` (`evidence/end-podlog.txt`).

## Timeline (UTC)

| Instant | Event | Evidence |
|---|---|---|
| 15:14:32Z | walk start; start captures follow | `evidence/start-instant.txt` |
| 15:14:43Z → 15:16:44Z | PROOF 1: the live test, `1 passed in 121.12s`; the revoked token answered for 121 s of it (the token cache) | `evidence/p1-pytest.txt` |
| 15:17:32Z → 15:18:56Z | PROOF 2 run 1: grant, `can-i` `no`/`yes`/`no`, UI login at 15:18:44Z, captures | `evidence/run1/p2-timeline.txt`, `evidence/run1/grant-window.txt` |
| 15:19:53Z → 15:21:16Z | PROOF 2 run 2: grant, `can-i` `no` (15:19:53Z) / `yes` (15:21:03Z) / `no` (15:21:16Z), UI login at 15:21:06Z, captures | `evidence/p2-timeline.txt`, `evidence/p2-before-cani.txt`, `evidence/p2-during-cani.txt`, `evidence/p2-after-cani.txt` |
| 15:21:16Z | the exit trap finds nothing left (`No resources found` twice) | `evidence/p2-trap-delete.txt` |
| 15:21:31Z | the OCR check; the unmasked controls deleted after it | `evidence/ocr-redaction.txt` |
| 15:21:45Z → 15:22:07Z | end captures | `evidence/end-*.txt` |
| 15:23:55Z | no `userSelfLogin` cluster on the lab, measured | `evidence/selflogin-absent.txt` |

## Redaction

The folder holds no token, no password, no `sha256~` value and no occurrence of the fleet account's name.

- The name was read from the fleet Lease's annotation into a shell variable and never printed.
- Every script replaces it with `<fleet account>` in what it writes, and replaces any `sha256~` value with
  `sha256~<redacted>`.
- `developer`'s password went from `crc console --credentials` straight into the environment of the process that used
  it (`GSD_LIVE_LOGIN_PASSWORD` in `proof1.sh`, `GSD_UI_PASSWORD` in `proof2.sh`). No script prints or writes it, and
  `rows.py` runs `oc` without it.
- The text search of the whole folder is `evidence/end-redaction.txt`: 0 files with a `sha256~` value and 0 files
  naming the fleet account, in any case. The pixel search is `evidence/ocr-redaction.txt`.

## How to repeat

```sh
export KUBECONFIG=<the lab's cluster-admin kubeconfig> GSD_WALK_TMP=<a directory outside the repo>
R=reports/2026-09-30_epic-c-proofs/scripts
for k in version pod chart argo cronjob pvcs sharedqa lease tokens cani grant secrets; do "${R}/capture.sh" "${k}" start; done
"${R}/proof1.sh"
"${R}/proof2.sh"
OCR=<a macOS Vision OCR binary> "${R}/ocr-redaction.sh" <unmasked control PNGs written by rows.py into GSD_WALK_TMP>
for k in version pod chart argo cronjob pvcs sharedqa lease tokens cani grant secrets; do "${R}/capture.sh" "${k}" end; done
"${R}/capture.sh" podlog end <the start instant>; "${R}/capture.sh" redaction end
```
