# #316 Rejoin on the lab, SPEC_D4 Appendix D — 2026-09-27

**Outcome.** The lab served application 1.5.0 at `9d78afde52` throughout (`evidence/step0-version.txt`,
`evidence/r2-end-version.txt`). The walker was `developer`, CRC's htpasswd account. There were two runs.

- **Run 1**, on the throwaway entry `rejoin-walk`, passed steps 0 to 4 and then stopped. The walk script had a
  defect: its Logins locator could not match. The evidence also held the surprise under "What came back that the
  appendix does not say", item 1. Run 1 was cleaned up.
- **Run 2**, on a fresh throwaway entry `rejoin-walk-2`, passed steps 0 to 7. Its step 2 ran in a first invocation
  that stopped on another script defect after the Add form had written the entry: a hard-coded name in an
  expectation (`evidence/r2-walk-output.txt`). A second invocation resumed at the poll and ran steps 3 to 6 in one
  browser session (`evidence/r2-walk-output-resumed.txt`, `failures : []`, no page errors).

In run 2:

- Rejoin answered `rejoined`, and Refresh then answered `connected`.
- The same random wrong password, pressed twice on one pod, answered `login-refused` and then `login-refused` "so it
  was not sent". The audit log shows exactly **1** `deny`, then **0** new authorizes.
- With the binding removed, the right password answered `not-cluster-admin`. The log reads `allowed=false`, the
  Secret's resourceVersion stayed at 5580537, and the walker's token count stayed at 3.
- The fleet account made **0** authorizes across both runs. It kept 2 tokens, and its Lease is byte-identical.
  `shared-qa` stayed at resourceVersion 2981054, and the PVC UIDs are unchanged.

## Definition of Done (#316)

| #316 row | Verdict | Evidence |
|---|---|---|
| A test for each behaviour; the hermetic and browser suites green; CI green | not this walk | the implementing PR (#446) |
| (chart changes) a version bump; rendered RBAC, REMOVED 0 | not this walk | the implementing PR |
| Docs updated | not this walk | the implementing PR |
| Reviewed by two seats other than the implementer | not this walk | the implementing PR |
| Deployed to CRC and walked; evidence committed under `reports/<date>_<slug>/` | **PASS** | 1.5.0 at `9d78afde52`; Appendix D steps 0–7 in run 2, steps 0–4 in run 1; this folder |
| The walk breaks a throwaway entry's token, and Refresh reads `auth_failed` | **PASS** | run 2: the Add form wrote `rejoin-walk-2` with a random wrong token (`r2-01-1280-step2-add-form.png`). The row read `status: auth_failed`, `401 Unauthorized — token invalid or expired`. Refresh answered `auth_failed · 2026-09-27T23:57:18Z` with "use Rejoin" (`r2-02`–`04-*-step3-card-offers-rejoin.png`). Run 1 the same at 23:44:04Z (`02`–`04`) |
| Rejoin as a cluster administrator; polling resumes | **PASS** | run 2: `rejoined · 2026-09-27T23:57:27Z`, the dialog closed with both fields empty (`r2-12`–`14`). The row read `status: ok` at 23:58:30Z, and Refresh answered `connected · 2026-09-27T23:58:30Z — authenticated as system:serviceaccount:group-sync-operator:group-sync-dashboard-cluster-poller` (`r2-15`–`17`) |
| The Secret carries the rejoin provenance and the admin's name | **PASS** | `evidence/r2-step4-secret.txt`: `token-source: rejoin`, `rejoined-by: developer`, `rejoin-account: developer`, `rejoined-at: 2026-09-27T23:57:27Z`, source namespace and ServiceAccount, `managed-by: ui` kept, no `lookup-account`; uid `9e721557-…` unchanged since step 2, resourceVersion 5580014 → 5580537 |
| The admin's login appears in the Logins history for that remote | **PASS on the host's entry; not on `rejoin-walk-2`'s** | `GET /api/clusters/dashboard/logins` at 23:59:21Z: `2026-09-27T23:57:27.363969Z`, `success`, provider `developer`, `audit: cli allow via openshift-challenging-client` (`r2-21`/`r2-22-1280-step4-logins-*.png`). `dashboard` and `rejoin-walk-2` are the same CRC. `GET /api/clusters/rejoin-walk-2/logins` answered 200 with 0 such rows, in both runs. Run 1 recorded why: the entry's first audit read is a backfill of 8388608 bytes from offset 0 |
| A second Rejoin with the same wrong password makes zero authorize requests, counted | **PASS** | since 23:59:28Z: after the first press, 1 `cli` authorize, `deny`, `401`, at 23:59:29Z (`evidence/r2-step5-after-first-audit.txt`). After the second press at 23:59:43Z, still 1 (`evidence/r2-step5-after-second-audit.txt`). The pod log has one `fleet-login-refused`, and for the second press only `cluster-rejoin-failed … already refused this password for developer, so it was not sent` |

## Run 2, step by step

| Step | When (UTC) | What came back | Evidence |
|---|---|---|---|
| 0 | 23:54:46 | `shared-qa` at resourceVersion 2981054. The Lease at resourceVersion 5127386, sha256 `96e37278…`, as at run 1's step 0. Tokens (`openshift-challenging-client`): `developer` 3, the fleet account 2. `can-i`: `no`. No binding and no entry. 0 audit events since the start instant. | `evidence/r2-step0-*.txt` |
| 1 | 23:54:56 | The binding `oc create clusterrolebinding rejoin-walk-cluster-admin --clusterrole=cluster-admin --user=developer` and the label `walk.gsd.lab/run=rejoin-2026-09-27`; `can-i`: `yes`. The walk began 82 s later. The command log was overwritten by the grant capture of the same file name (see "The scripts' own defects"). | `evidence/r2-step1-grant.txt`, `evidence/r2-step1-cani.txt` |
| 2 | 23:56:26 | The Add form: `https://api.crc.testing:6443`, **use the trusted bundle** (`tlsClientConfig {"insecure":false}`), a random `sha256~` token of 51 characters, and the walk's label. It answered `Secret gsd-cluster-rejoin-walk-2 created — discovery requested`. | `r2-01-1280-step2-add-form.png`, `evidence/r2-walk-output.txt`, `evidence/r2-step2-secret.txt` |
| 3 | 23:57:17 – 23:58:30 | The row read `auth_failed`, and Refresh answered `auth_failed` and offered **Rejoin…**. The dialog opened with both fields empty. Rejoin answered `rejoined · 23:57:27Z` (the answer reads `as <redacted>`, item 1 below), and Refresh then answered `connected`. | `r2-02`–`r2-17`, `evidence/r2-walk-output-resumed.txt` |
| 4 | 23:59:21 | The Secret's annotations (in the table above). The walker's challenging-client tokens were 3. The Logins row is on the host's tab. The log lines are below. | `evidence/r2-step4-*.txt`, `r2-21`/`r2-22` |
| 5 | 23:59:29, 23:59:43 | First press: `login-refused — rejoin-walk-2 refused the password for developer: check the username and password; it is not sent again by this pod while it is the same password (401 Unauthorized from oauth-openshift.apps-crc.testing; Www-Authenticate: Basic realm="openshift"; body: <empty>)`. Second press, the same password retyped: `login-refused — https://api.crc.testing:6443 already refused this password for developer, so it was not sent: type the right password (this pod holds a refused password back until it restarts)`. The dialog stayed open with the password field empty each time. Audit: 1 `deny`, then 0 new. | `r2-23`–`r2-34`, `evidence/r2-step5-*-audit.txt` |
| 6 | 00:00:44 – 00:01:02 | A fresh cluster-admin tier check was seen at 00:00:44Z on the pod's `/metrics` (`allowed` 8 → 9 around one `/api/whoami`). The binding was deleted at 00:00:50, and the press came 16.6 s after the fresh check. It answered `not-cluster-admin — rejoin-walk-2 says <redacted> may not update clusterrolebindings there, so nothing was read or written: Rejoin needs a cluster administrator of rejoin-walk-2; the login was signed out`. The log reads `cluster-rejoin-review … allowed=false`, then `fleet-logout … outcome=revoked`. The Secret's resourceVersion was 5580537 before and after. The walker's tokens were 3 before and after. | `r2-35`–`r2-40`, `evidence/r2-step6-*.txt`, `evidence/r2-step6-grant-delete.txt` |
| 7 | 00:01:26 – 00:02:54 | `rejoin-walk-2`'s Secret was deleted; the binding was already gone, and `--ignore-not-found` printed nothing. Discovery cycle 11 at 00:02:27 logged `removed=rejoin-walk-2`, then `rejoin-walk-2: its Secret is gone; the poll thread stops (history kept)`. The label and the name select nothing, and `can-i` answers `no`. A fresh login as `developer` at 00:02:54 answered `cluster_admin: false` and `/api/clusterconfigs` `403`. The end checks are in the budget table below. | `evidence/r2-step7-delete.txt`, `evidence/r2-end-*.txt` |

**Step 4's and step 6's log lines**, from `evidence/r2-step6-podlog.txt`. The `sha256~` names are redacted by the
capture; every other `<redacted>` is the application's own.

```text
19:57:27,368 fleet-login cluster=rejoin-walk-2 account=<redacted> tls=trusted-bundle rejoin_by=<redacted> oauth=https://oauth-openshift.apps-crc.testing expires_at=2027-09-27T23:57:27Z
19:57:27,385 cluster-rejoin-review cluster=rejoin-walk-2 by=<redacted> account=<redacted> question="update clusterrolebindings" allowed=true reason="RBAC: allowed by ClusterRoleBinding 'rejoin-walk-cluster-admin' of ClusterRole 'cluster-admin' to User '<redacted>'"
19:57:27,406 fleet-logout cluster=rejoin-walk-2 account=<redacted> tls=trusted-bundle rejoin_by=<redacted> token=sha256~<redacted> outcome=revoked
19:57:27,429 cluster-secret-rotated secret=gsd-cluster-rejoin-walk-2 namespace=group-sync-dashboard cluster=rejoin-walk-2 by=developer
19:57:27,430 cluster-rejoined cluster=rejoin-walk-2 by=<redacted> account=<redacted> secret=gsd-cluster-rejoin-walk-2 written=updated revoked=true
19:59:29,325 fleet-login-refused phase=credential outcome=login-refused cluster=rejoin-walk-2 account=developer tls=trusted-bundle rejoin_by=developer …
19:59:29,327 cluster-rejoin-failed phase=credential outcome=login-refused cluster=rejoin-walk-2 by=developer account=developer …
19:59:44,010 cluster-rejoin-failed phase=credential outcome=login-refused … "https://api.crc.testing:6443 already refused this password for developer, so it was not sent …"
20:01:01,691 fleet-login cluster=rejoin-walk-2 account=<redacted> tls=trusted-bundle rejoin_by=<redacted> …
20:01:01,712 cluster-rejoin-review cluster=rejoin-walk-2 by=<redacted> account=<redacted> question="update clusterrolebindings" allowed=false
20:01:01,719 fleet-logout cluster=rejoin-walk-2 account=<redacted> … outcome=revoked
20:01:01,720 cluster-rejoin-failed phase=credential outcome=not-cluster-admin cluster=rejoin-walk-2 by=<redacted> account=<redacted> …
```

The times are the pod's local zone (EDT, UTC−4). The run-2 window counts: `fleet-login` 2, `fleet-login-refused` 1,
`fleet-logout` 2, `cluster-rejoin-review` 2, `cluster-rejoined` 1, `cluster-rejoin-failed` 3, lines naming the fleet
account 0, `ERROR`/`Traceback` 0.

## The budget, from the audit log and the token list

These are counts from the oauth-server audit log, read through a pipe and never written. `r2-end-audit.txt` covers
run 2 from 23:54:46Z; `r2-end-since-run1-audit.txt` covers both runs from 23:42:28Z.

| Count | Run 2 | Both runs | Appendix D expects |
|---|---|---|---|
| Rejoin presses | 4 (step 3, step 5 ×2, step 6) | 5 | — |
| `developer` `cli` authorizes (`client_id=openshift-challenging-client`) | **3**: `allow` 23:57:27, `deny` 23:59:29, `allow` 00:01:01 | 4 (run 1's `allow` 23:44:09) | one per press that sends; the gated press sends nothing |
| `deny` | **1** | 1 | step 5's single `deny` |
| authorizes after step 5's second press, before step 6 | **0** | — | 0 |
| the fleet account's annotated events, and its authorizes | **0** and **0** | 0 and 0 | 0 |
| the fleet account's tokens (`openshift-challenging-client`) | 2 at step 0 and at the end | 2 throughout | 2 |
| `developer`'s `openshift-challenging-client` tokens | 3 at steps 0, 4, 5, 6 (before and after) and at the end | 3 throughout | unchanged: each Rejoin login revoked |
| the fleet account's Lease | resourceVersion 5127386, sha256 `96e37278…`: `diff` of run 1's step 0 against run 2's end, without their instants, is empty | | unchanged |
| `gsd-cluster-shared-qa` resourceVersion | 2981054 at run 1's step 0, run 2's step 0 and run 2's end | | equal |
| PVC UIDs | data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, identical at both ends | | unchanged |

The other `developer` events are `credential` + `session` pairs: the walk's own browser logins through the
dashboard's proxy.

## What came back that the appendix does not say

1. **The account's name is `<redacted>` wherever the right password is in play.** This happens in the Rejoin answer
   (`Signed in to rejoin-walk-2 as <redacted>`, `says <redacted> may not …`), in `fleet-login`/`fleet-logout`
   (`account=<redacted> rejoin_by=<redacted>`), in `cluster-rejoin-review` (`to User '<redacted>'`) and in
   `cluster-rejoined`. The lines of step 5, where a random wrong password is in play, name `developer`. **CRC's
   `developer` password is the same as its username, CRC's publicly documented default. §3.7's scrub therefore also
   blanks the username wherever it removes that password, and this evidence carries that inference, as measured.**
   The value is written nowhere here. The same scrub-by-value in run 1's walk script withheld `developer` from the
   first lines of `evidence/walk-output.txt`, and it was then narrowed to the two random values (`SCRUB_ENV`). The
   Secret's `rejoined-by` / `rejoin-account`, the `cluster-secret-rotated … by=developer` line and the Logins row name
   `developer` as written.
2. **Observation (a), measured in run 2: at 375 px the dialog's Cancel and Rejoin buttons are reachable by
   scrolling the dialog.** `observe_dialog_reach` in `scripts/walk.py`; the lines `obs (a)` in
   `evidence/r2-walk-output-resumed.txt`.

   | viewport | dialog | buttons before | after one wheel scroll over the dialog | reachable |
   |---|---|---|---|---|
   | 375 × 812 | `overflow-y: auto`, `max-height: calc(100% - 34px)`, scrollHeight 833 / clientHeight 776 | top 801, bottom 833: off screen, a tap at the centre misses | scrollTop 57, top 744, bottom 776: in the viewport, a tap lands on each | **yes** |
   | 375 × 667 | the same, clientHeight 631 | top 801: off screen | scrollTop 202, top 599, bottom 631: a tap lands on each | **yes** |

   The screenshots are `r2-08`/`r2-09` (812) and `r2-10`/`r2-11` (667), each before and after the scroll. Not a
   defect: the buttons start below the fold and one scroll inside the dialog reaches them. Run 1's
   `07-375-step3-dialog-empty.png` ended above them because an element capture shows only the dialog's visible box.
3. **Observation (b), measured in run 2: the card's CONNECTION row leaves `auth_failed` on the page's next poll
   after the server's own poll.** `observe_connection_redraw`; the lines `obs (b)`.
   - At 23:58:32, after the Rejoin answer at 23:57:27Z and after Refresh had answered `connected`, the row still read
     `auth_failed 2026-09-27 23:57 401 Unauthorized — token invalid or expired`.
   - The page's own `GET /api/clusterconfigs` came at 23:59:12, the only one while watching. The walk's reads carry
     `?walk=1` and are excluded.
   - By 23:59:17, 110.1 s after the answer, the row read `ok reachable 2026-09-27 23:58`
     (`r2-18`–`r2-20-*-obs-b-connection-after-poll.png`). That is within two of the page's 60 s intervals
     (`POLL_INTERVAL_MS`).
   - For up to one page interval after the server polls, the card shows `Refresh: connected` beside a CONNECTION row
     reading `auth_failed` (`r2-15`–`r2-17`). The Rejoin answer's own `refresh()` ran before the server's poll had
     turned the row to `ok` (23:58:30 in the API).

## The scripts' own defects, and what was changed

- **Run 1:**
  - The Logins locator (`page.locator("table", has=…)` matched a nested table that does not exist). Fixed as
    `logins_shot`.
  - The scrub-by-value (item 1).
  - `lab.sh grant` and `capture.sh grant` both wrote `step1-grant.txt`. The capture overwrote the create command's
    log in both runs; the binding itself is in the captures. `lab.sh` now writes `step1-binding-create.txt`.
- **Run 2:**
  - An expectation hard-coded `gsd-cluster-rejoin-walk` (fixed: `add_entry` uses the entry's name).
  - Step 6's `can-i` wait read the last line of stdout + stderr, which is the API's warning. It therefore waited its
    full 10 × 1 s without seeing `no`. The press still came 16.6 s after the fresh tier check, and the remote answered
    `allowed=false`. The wait now looks for `no` on any line.
- The resumed invocation (`GSD_STEP2_DONE=1`) skipped the Add form the first invocation had already run, and
  continued at the poll.

## Run 1, for the record (stopped after step 4)

| Step | When (UTC) | What came back | Evidence |
|---|---|---|---|
| 0–1 | 23:42:28 – 23:42:40 | The same baseline as run 2's; the binding; `can-i` `yes` | `evidence/step0-*.txt`, `evidence/step1-*.txt` |
| 2 | 23:44:01 | The Add form wrote `rejoin-walk`; discovery cycle 5 `added=rejoin-walk`; the first poll `auth_failed` | `01-1280-step2-add-form.png`, `evidence/step2-secret.txt` |
| 3 | 23:44:04 – 23:45:03 | Refresh `auth_failed` offering Rejoin; `rejoined · 23:44:09Z`; Refresh `connected` | `02`–`13-*.png` |
| 4 | 23:45:05 – 23:47:59 | The provenance on the Secret (resourceVersion 5573221 → 5573284); one `fleet-login`, `cluster-rejoin-review … allowed=true` naming `rejoin-walk-cluster-admin`, `cluster-rejoined … revoked=true`; the host's Logins row | `evidence/step4-*.txt`, `14`/`15-1280-step4-logins-*.png` |
| cleanup | 23:48:06 – 23:49:28 | The Secret and the binding deleted; discovery cycle 7 `removed=rejoin-walk`; a fresh login `cluster_admin: false`, `403`. A try at 23:48:41, inside the 60 s tier cache, still answered `true` / `200` | `evidence/step7-delete.txt`, `evidence/cleanup-*.txt`, `evidence/end-*.txt` |

## How to run it again

```sh
export KUBECONFIG=<the lab kubeconfig> GSD_WALK_ENTRY=<a fresh throwaway name> GSD_RUN=<a file prefix>
F=reports/2026-09-27_rejoin-walk
T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)
for k in version pvcs sharedqa lease tokens cani grant secret tiers; do "$F/scripts/capture.sh" "$k" "${GSD_RUN}step0"; done
"$F/scripts/capture.sh" audit "${GSD_RUN}step0" "$T0"
"$F/scripts/lab.sh" grant                     # then wait more than 60 s: the tier cache
GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
GSD_WRONG_PASSWORD="$(openssl rand -hex 12)" GSD_WALK_TOKEN="sha256~$(openssl rand -hex 22)" \
  local-development/.venv/bin/python "$F/scripts/walk.py" walk
"$F/scripts/lab.sh" delete                    # always: the entry and the binding, --ignore-not-found
# once the pod logs `discovery … removed=<the entry>` and 60 s have passed:
GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
  local-development/.venv/bin/python "$F/scripts/walk.py" after
for k in version pvcs sharedqa lease tokens tiers grant cani secret; do "$F/scripts/capture.sh" "$k" "${GSD_RUN}end"; done
"$F/scripts/capture.sh" audit "${GSD_RUN}end" "$T0"; "$F/scripts/capture.sh" podlog "${GSD_RUN}end" "$T0"
```

`walk.py walk` runs steps 2–6 in one browser session, observations (a) and (b) included. `GSD_STEP2_DONE=1` with
`GSD_SHOT_FROM=<n>` resumes after an Add form that already ran. `walk.py logins <the row's instant>` captures step
4's Logins row on its own.
