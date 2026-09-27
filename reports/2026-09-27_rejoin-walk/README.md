# #316 Rejoin on the lab, SPEC_D4 Appendix D — 2026-09-27 — STOPPED after step 4

**Outcome.** The lab served application 1.5.0 at `9d78afde52` before and after the walk (`evidence/step0-version.txt`,
`evidence/end-version.txt`). The walker was `developer`, an htpasswd account.

Steps 0 to 4 ran as Appendix D prescribes, at 1280, 768 and 375 px:

- The Add form wrote `rejoin-walk` with a random wrong token, and the first poll answered `auth_failed`.
- Refresh answered `auth_failed` and the card offered **Rejoin…**.
- Rejoin as `developer` answered `rejoined` at `2026-09-27T23:44:09Z`, and Refresh then answered `connected`.
- The Secret carries the Rejoin provenance and no `lookup-account`.
- The pod log has one `fleet-login` line, one `cluster-rejoin-review … allowed=true` line naming
  `rejoin-walk-cluster-admin`, and one `cluster-rejoined … revoked=true` line.
- The walker's `cli` login is a row on the host's Logins tab.

**Steps 5 and 6 did not run.** The walk script stopped on its own defect while capturing the Logins screenshot
(`evidence/walk-output.txt`, the last three lines: a Playwright locator that could not match). The step-4 capture
was then taken on its own (`scripts/walk.py logins`). The evidence also showed a surprise, described under "What
came back that the appendix does not say". The brief says to stop and report on a surprise, so the walk stopped
there.

**The cleanup ran.** The entry and the binding were deleted, and discovery retired `rejoin-walk` at 23:49:09Z.
`shared-qa`, the fleet account's Lease and the PVC UIDs are unchanged.

## Definition of Done (#316)

| #316 row | Verdict | Evidence |
|---|---|---|
| A test for each behaviour; the hermetic and browser suites green; CI green | not this walk | the implementing PR (#446) |
| (chart changes) a version bump; rendered RBAC, REMOVED 0 | not this walk | the implementing PR |
| Docs updated | not this walk | the implementing PR |
| Reviewed by two seats other than the implementer | not this walk | the implementing PR |
| Deployed to CRC and walked; evidence committed under `reports/<date>_<slug>/` | **partial** | 1.5.0 at `9d78afde52` deployed; steps 0–4 and the cleanup here; steps 5–6 not run |
| The walk breaks a throwaway entry's token, and Refresh reads `auth_failed` | **PASS** | `walk-output.txt`: the row `status: auth_failed`, `401 Unauthorized — token invalid or expired`; Refresh `auth_failed · 2026-09-27T23:44:04Z` with "use Rejoin"; `02`–`04-*-step3-card-offers-rejoin.png`; pod log `cluster-refreshed cluster=rejoin-walk credential=bearer by=developer outcome=auth_failed` |
| Rejoin as a cluster administrator; polling resumes | **PASS** | `rejoined · 2026-09-27T23:44:09Z`, the dialog closed with both fields empty (`08`–`10-*-step3-rejoined.png`). The row read `status: ok` at 23:45:02Z. Refresh answered `connected · 2026-09-27T23:45:03Z — authenticated as system:serviceaccount:group-sync-operator:group-sync-dashboard-cluster-poller, server v1.35.6` (`11`–`13-*-step3-refresh-connected.png`). Pod log at 23:45:02: `polled rejoin-walk: 3 CRs, 66 groups, 3 new sync event(s), 95 membership change(s)` |
| The Secret carries the rejoin provenance and the admin's name | **PASS** | `evidence/step4-secret.txt`: `token-source: rejoin`, `rejoined-by: developer`, `rejoin-account: developer`, `rejoined-at: 2026-09-27T23:44:09Z`, `source-namespace: group-sync-operator`, `source-service-account: group-sync-dashboard-cluster-poller`, `managed-by: ui` kept, no `lookup-account`; the same uid `2f66c2a9-…` as step 2, resourceVersion 5573221 → 5573284 |
| The admin's login appears in the Logins history for that remote | **PASS on the host's entry; not measured on `rejoin-walk`'s** | `GET /api/clusters/dashboard/logins` at 23:45:06Z: one row, `2026-09-27T23:44:09.516138Z`, `success`, `audit: cli allow via openshift-challenging-client`. `14`/`15-1280-step4-logins-*.png`. `dashboard` and `rejoin-walk` are the same CRC. `GET /api/clusters/rejoin-walk/logins` returned 200 with 0 such rows at 23:45:06Z: its first audit read at 23:45:03Z was a backfill of 8388608 bytes from offset 0, and the walk did not wait for a later read |
| A second Rejoin with the same wrong password makes zero authorize requests, counted | **NOT RUN** | step 5 did not run |

## The steps, as they came back

| Step | When (UTC) | What came back | Evidence |
|---|---|---|---|
| 0 | 23:42:28 | The start instant for the audit log. `gsd-cluster-shared-qa` at resourceVersion 2981054. The fleet account's Lease at resourceVersion 5127386, `ping-last-ok 2026-09-27T10:27:05Z`, sha256 `96e37278…`. Tokens: `developer`'s `openshift-challenging-client` 3; the fleet account's `openshift-challenging-client` 2. `can-i`: `no`. No binding and no `rejoin-walk` Secret. Audit events since the start instant: 0. | `evidence/step0-*.txt` |
| 1 | 23:42:40 | `oc create clusterrolebinding rejoin-walk-cluster-admin --clusterrole=cluster-admin --user=developer`, then the label `walk.gsd.lab/run=rejoin-2026-09-27`; `can-i`: `yes`. The walk started 73 s later, after the 60 s tier cache. | `evidence/step1-*.txt` |
| 2 | 23:44:01 | The Add form's YAML twin showed `tlsClientConfig {"insecure":false}` (the trusted bundle), `visibility remote-sar`, `identity same-as-host` and the walk's label. **Create Secret** answered `Secret gsd-cluster-rejoin-walk created — discovery requested`. Discovery cycle 5 at 23:44:02 logged `added=rejoin-walk`, and the first poll answered `auth_failed`. | `01-1280-step2-add-form.png`, `evidence/step2-secret.txt`, `evidence/step4-podlog.txt` |
| 3 | 23:44:04 – 23:45:03 | Refresh answered `auth_failed` and offered **Rejoin…**. The dialog opened with both fields empty, the password field `type=password`. The press at 23:44:09 answered `rejoined`, and at 23:45:03 Refresh answered `connected`. | `02`–`13-*.png`, `evidence/walk-output.txt` |
| 4 | 23:45:05 – 23:47:59 | The Secret's annotations and the pod log's lines (below). The walker's `openshift-challenging-client` tokens were 3, as at step 0. The Logins row is on the host's tab. | `evidence/step4-*.txt`, `14`/`15-1280-step4-logins-*.png` |
| 5, 6 | — | Not run. | — |
| cleanup | 23:48:06 – 23:49:28 | The Secret was deleted by name at 23:48:06 and the binding at 23:48:07. `can-i`: `no`; the label and the name each select nothing. Discovery cycle 7 at 23:49:09 logged `removed=rejoin-walk`, and at 23:49:10 `rejoin-walk: its Secret is gone; the poll thread stops (history kept)`. A fresh login as `developer` at 23:49:28 answered `cluster_admin: false` and `/api/clusterconfigs` `403`. A first try at 23:48:41, 34 s after the removal and inside the 60 s tier cache, still answered `true` and `200`. | `evidence/step7-delete.txt` (the cleanup, by `scripts/lab.sh delete`), `evidence/cleanup-*.txt`, `evidence/end-podlog.txt` |

**Step 4's log lines**, from `evidence/step4-podlog.txt`:

```text
23:44:09.522 gsd.fleetlogin fleet-login cluster=rejoin-walk account=<redacted> tls=trusted-bundle rejoin_by=<redacted> oauth=https://oauth-openshift.apps-crc.testing expires_at=2027-09-27T23:44:09Z
23:44:09.539 gsd.rejoin cluster-rejoin-review cluster=rejoin-walk by=<redacted> account=<redacted> question="update clusterrolebindings" allowed=true reason="RBAC: allowed by ClusterRoleBinding 'rejoin-walk-cluster-admin' of ClusterRole 'cluster-admin' to User '<redacted>'"
23:44:09.560 gsd.fleetlogin fleet-logout cluster=rejoin-walk account=<redacted> tls=trusted-bundle rejoin_by=<redacted> token=sha256~<redacted> outcome=revoked
23:44:09.583 gsd.clusterconfig.writer cluster-secret-rotated secret=gsd-cluster-rejoin-walk namespace=group-sync-dashboard cluster=rejoin-walk by=developer
23:44:09.594 gsd.rejoin cluster-rejoined cluster=rejoin-walk by=<redacted> account=<redacted> secret=gsd-cluster-rejoin-walk written=updated revoked=true
```

The `sha256~` token name is redacted by `scripts/capture.sh`. Every other `<redacted>` is the application's own.

## The budget, from the audit log and the token list

These are counts from the oauth-server audit log, read through a pipe and never written. The window runs from the
start instant 23:42:28Z to 23:49:19Z (`evidence/end-audit.txt`).

| Count | Value | Appendix D expects |
|---|---|---|
| `developer` `cli` authorizes (`client_id=openshift-challenging-client`) | **1**: `allow`, `302`, at 23:44:09Z, the Rejoin | one per press |
| `developer` `deny` | 0 | step 5's single `deny`: **not run** |
| the fleet account's annotated events, and its authorizes | **0** and **0** | 0 |
| the fleet account's tokens (`openshift-challenging-client`) | 2 at step 0, 2 at step 4, 2 at the end | 2 |
| `developer`'s `openshift-challenging-client` tokens | 3 at step 0, 3 at step 4, 3 at the end: the Rejoin login was revoked | back to step 0's |
| the fleet account's Lease | resourceVersion 5127386 and sha256 `96e37278…` at both ends; `diff` of the two captures without their instants is empty | unchanged |
| `gsd-cluster-shared-qa` resourceVersion | 2981054 at step 0 and at the end | equal |
| pod log `fleet-login` / `fleet-logout` / `cluster-rejoin-review` / `cluster-rejoined` / `cluster-rejoin-failed` / lines naming the fleet account / `ERROR` or `Traceback` | 1 / 1 / 1 / 1 / 0 / 0 / 0 | — |

The other ten `developer` events in the window are five `credential` + `session` pairs. They are the walk's own
browser logins through the dashboard's proxy, not Rejoin.

## What came back that the appendix does not say

1. **The account's name is `<redacted>` in the Rejoin answer and in the pod's Rejoin lines.** The answer reads
   `Signed in to rejoin-walk as <redacted>, who may update clusterrolebindings there`. The lines read
   `account=<redacted> rejoin_by=<redacted>`, and the review's reason ends `to User '<redacted>'`. SPEC_D4 §3.7
   scrubs every answer and line of the password in play. On this lab that scrub also matches the account's name, so
   the lines Appendix D step 4 names carry no readable `rejoin_by=` value. The Secret's `rejoined-by` and
   `rejoin-account` annotations, the `cluster-secret-rotated … by=developer` line and the Logins row name
   `developer` as written. The walk script's own scrub, which withheld its secret values by value, did the same to
   the first lines of `evidence/walk-output.txt` (`"user": "<withheld>"`). It has since been narrowed to the two
   random values (`scripts/walk.py`, `SCRUB_ENV`).
2. **The card's CONNECTION row lags its Refresh line.** At 23:45:03 the card read `Refresh: connected`, while the
   CONNECTION row still showed `auth_failed 2026-09-27 23:44` (`11`–`13-*-step3-refresh-connected.png`). The API
   had answered `status: ok` at 23:45:02. The card is drawn from the page's last `/api/clusterconfigs` read, taken
   after the Rejoin answer at 23:44:10. This was observed; whether the next 60 s poll redraws it was not measured.
3. **The dialog at 375 px.** The element capture (`07-375-step3-dialog-empty.png`) ends at the one-try warning;
   **Cancel** and **Rejoin** are below it. Whether the dialog scrolls to them at 375 px was not measured.

## What is not done

- Step 5 (one wrong password, twice: `login-refused`, then `login-refused` "so it was not sent", one `deny`, zero
  new authorizes) and step 6 (the binding removed, the right password: `not-cluster-admin`, the Secret's
  resourceVersion and the walker's token count unchanged). Their screenshots do not exist.
- **Why they cannot simply be resumed.** The card offers **Rejoin…** only after Refresh answers `auth_failed` or
  `pending`, or while the page still holds its own Rejoin answer (`ccRejoinButton`). A fresh page on a repaired
  entry does not offer it. A re-run needs the entry broken again, by a new Add or by Rotate. That is the
  orchestrator's decision.
- **The binding is removed.** Step 6 on this lab needs the host's cached tier to outlive the removal of the binding,
  because the host and the remote are one CRC. `scripts/walk.py` presses inside that window only after
  `gsd_visibility_tier_checks_total{outcome="allowed",threshold="cluster_admin"}` shows a fresh check, and it stops
  if more than 40 s have passed.

## How to run it again

```sh
export KUBECONFIG=<the lab kubeconfig>
F=reports/2026-09-27_rejoin-walk
T0=$(date -u +%Y-%m-%dT%H:%M:%SZ)
for k in version pvcs sharedqa lease tokens cani grant secret tiers; do "$F/scripts/capture.sh" "$k" step0; done
"$F/scripts/capture.sh" audit step0 "$T0"
"$F/scripts/lab.sh" grant                     # then wait more than 60 s: the tier cache
GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
GSD_WRONG_PASSWORD="$(openssl rand -hex 12)" GSD_WALK_TOKEN="sha256~$(openssl rand -hex 22)" \
  local-development/.venv/bin/python "$F/scripts/walk.py" walk
"$F/scripts/lab.sh" delete                    # always: the entry and the binding, --ignore-not-found
# once the pod logs `discovery … removed=rejoin-walk` and 60 s have passed:
GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
  local-development/.venv/bin/python "$F/scripts/walk.py" after
for k in version pvcs sharedqa lease tokens tiers; do "$F/scripts/capture.sh" "$k" end; done
"$F/scripts/capture.sh" audit end "$T0"; "$F/scripts/capture.sh" podlog end "$T0"
```

`scripts/walk.py logins <the row's instant>` captures step 4's Logins row on its own. The run above used it after
the walk stopped (`evidence/step4-logins-output.txt`).
