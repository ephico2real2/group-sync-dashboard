# #492 on the lab: the `verify failed` chip — 2026-09-30

**Outcome.** The lab served application 1.21.0 at commit `9843381492` before and after the walk
(`evidence/before-version.txt` at 07:06:44Z, `evidence/after-version.txt` at 07:15:50Z). That is PR #493's merge
commit `9843381492bac938d8d4145dc471696872b072c2`. The image was `quay.io/ephico2real/group-sync-dashboard:1.21.0`
in pod `group-sync-dashboard-7b8fb45dfc-r2ns8`, started at 07:00:21Z. It had 0 restarts before and after the walk
(`evidence/before-pod.txt`, `evidence/after-pod.txt`). The walker was `developer`, CRC's htpasswd account, at
1280 px and at 375 px. It held the walk's temporary `update clusterrolebindings` grant
(`evidence/walk-live.txt`: `cluster_admin: true`). All three of #492's issue-specific checks passed on the lab, and so
did the brief's rows A–F. The three `walk.py` runs each ended with `failures: []` (`evidence/walk-precheck.txt`,
`evidence/walk-live.txt`, `evidence/walk-retired.txt`), and `run.sh` recorded `walk exit=0`
(`evidence/run-exit.txt`). Nothing carrying the label `walk.gsd.lab/run=chip-492-2026-09-30` was left at the end
(`evidence/after-label-check.txt`).

## Why the grant was taken

The brief asked for the cluster-admin tier only if the Cluster Configurations page needs it to show the TLS row. It
does. The precheck ran as `developer` without the grant at 07:06:53Z, and three things answered
(`evidence/P-precheck.json`):

- `whoami` gave `cluster_admin: false`.
- The tab bar offered twelve tabs, and Cluster Configurations was not one of them.
- `GET /api/clusterconfigs` answered `403` with
  `For cluster administrators only. This view reports how this instance is wired to its clusters — …`.

The code agrees. `local-development/gsd/api.py#list_cluster_configs` calls `require_cluster_admin` before it builds
any entry, and `local-development/gsd/static/index.html#${clusterAdmin() ? tab("clusters", "Cluster Configurations") : ""}`
offers the tab only to that tier. So the TLS row itself needs the grant, not only the Add-cluster form's Test. The
brief's premise that #244's walk needed it "for the Test form only" does not hold at this commit. #244's own grant
comment names the tab, the form and the Test route together (`reports/2026-09-29_ca-244-walk/scripts/grant.yaml`).

## How each step was read

- **Driven**: the Cluster Configurations tab (`/#page=clusters`) and each card's tls and connection rows, at 1280 px
  and then at 375 px, in the same logged-in session (`reports/2026-09-30_chip-492-walk/scripts/walk.py`).
- **The page's own fetch with the session**: `GET /api/clusterconfigs`, the endpoint the tab renders from
  (`evidence/live-clusterconfigs-entries.json`, `evidence/E-w492-fail-retired.json`).
- **oc, read-only**: the Secrets, the pod log, the PVCs, the Lease and `can-i`. The only writes were the throwaway
  Secret `gsd-cluster-w492-fail` and the grant (a ClusterRole and a ClusterRoleBinding), all under the label.

## Definition of Done

| Row | Verdict | Evidence |
|---|---|---|
| **#492 check 1.** A throwaway cluster with a wrong CA shows `verify failed` (not `verified`) on its TLS row | **PASS** | `w492-fail`'s tls row reads `verify failed ca: caData`. Its only chip is `{"text": "verify failed", "class": "badge warning"}`, and `.badge.ok` in the row counts 0 (`evidence/A-w492-fail-1280.json`). Row A below has the detail. Screenshot `screenshots/01-1280-A-w492-fail-card.png` |
| **#492 check 2.** `mock-privateca` (verifies) still shows the green `verified` | **PASS** | Chips `[{"text": "verified", "class": "badge ok"}]`, tls row `verified ca: caData …`, status `ok` (`evidence/B-mock-privateca-1280.json`). Row B below has the detail. Screenshot `screenshots/02-1280-B-mock-privateca-card.png` |
| **#492 check 3.** `mock-selfsigned` still shows `insecure` | **PASS** | Chips `[{"text": "insecure", "class": "badge warning"}]`, tls row `insecure` (`evidence/C-mock-selfsigned-1280.json`). Row C below has the detail. Screenshot `screenshots/03-1280-C-mock-selfsigned-card.png` |
| **A.** `w492-fail` after its first poll: `verify failed` (warning), `ca: caData` beside it, no `.badge.ok` in the TLS row; the connection row keeps the raw error and the fix sentence; the API entry carries `action`; 1280 and 375 px, `scrollWidth <= innerWidth` | **PASS** | The Secret `gsd-cluster-w492-fail` was created at 07:06:54Z. It has name `w492-fail`, server `https://mock-privateca:6443` copied from `gsd-cluster-mock-privateca`, config keys `bearerToken` and `tlsClientConfig`, and tls keys `caData` only. The token is 51 characters and was never printed (`evidence/secret-create.txt`, `evidence/during-walksecrets.txt`). Its caData is `CN=walk-492 wrong CA`, self-signed, `CA:TRUE`, `notAfter=Sep 30 07:06:54 2027 GMT`, sha256 `21:E9:8F:C4:…:7D:15:84:BD` (`evidence/generated-ca.txt`). Discovery cycle 4 logged `added=w492-fail` at 07:10:35.852Z. The first poll at 07:10:35.891Z logged `cluster-unreachable phase=tls outcome=cert-verify-failed cluster=w492-fail … action="this cluster pins its own CA: replace tlsClientConfig.caData in Secret gsd-cluster-w492-fail with the CA that signs its API server"` (`evidence/wait-discovery-added.txt`, `evidence/wait-first-poll.txt`). **API** (read at 07:10:45Z): `tls` is `{"insecure": false, "ca": "caData"}`, `status` is `unreachable`, `error` is `ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1082)`, and `action` is the sentence above (`evidence/A-w492-fail-1280.json`). **Card, 1280 px**: the tls row reads `verify failed ca: caData store secret:gsd-cluster-w492-fail/tlsClientConfig.caData · 1 certificate CN=walk-492 wrong CA · issuer CN=walk-492 wrong CA · 2027-09-30T07:06:54Z`. Its chips are `[{"text": "verify failed", "class": "badge warning"}]` and `ok_badges_in_tls_row` is 0. The connection row shows the raw error, then the action (equal to the API's), then `store secret:gsd-cluster-w492-fail/tlsClientConfig.caData`. The page measured `innerWidth 1280`, `scrollWidth 1280` (`evidence/A-w492-fail-1280.json`). **Card, 375 px**: the same chip and 0 `.badge.ok` (`evidence/A-w492-fail-375.json`). The page measured `innerWidth 375`, `scrollWidth 375`. The card was 20–355 and its chip 149–252 (card `scrollWidth 333 = clientWidth 333`), so the chip sits inside the card (`evidence/A-w492-fail-375.json`, `page` and `card.geometry`). Screenshots `screenshots/01-1280-A-w492-fail-card.png`, `screenshots/04-375-A-w492-fail-card.png` |
| **B.** `mock-privateca`: green `verified`, `ca: caData`, no `action` in its API entry | **PASS** | The entry has `tls` `{"insecure": false, "ca": "caData"}`, `status` `ok`, `last_poll` `2026-09-30T07:09:53Z`, `error` `null`, and no `action` key. The card's chips are `[{"text": "verified", "class": "badge ok"}]`, and its tls row reads `verified ca: caData store secret:gsd-cluster-mock-privateca/tlsClientConfig.caData · 1 certificate CN=mock-privateca-root · issuer CN=mock-privateca-root · 2031-09-19T16:54:01Z` (`evidence/B-mock-privateca-1280.json`). At 375 px the chips are the same (`evidence/A-w492-fail-375.json`, `mock-privateca`). During the walk its header also carried `shared API URL`, because the throwaway used the same server. That warning appeared at cycle 4 and cleared at cycle 5 (`evidence/after-podlog.txt`). Screenshots `screenshots/02-1280-B-mock-privateca-card.png`, `screenshots/05-375-B-mock-privateca-card.png` |
| **C.** `mock-selfsigned`: `insecure`, no `verified`, no `verify failed` | **PASS** | The entry has `tls` `{"insecure": true, "ca": null}` and `status` `ok`. The card's chips are exactly `[{"text": "insecure", "class": "badge warning"}]`, and its tls row reads `insecure` (`evidence/C-mock-selfsigned-1280.json`). At 375 px the chips are the same (`evidence/A-w492-fail-375.json`, `mock-selfsigned`). Screenshots `screenshots/03-1280-C-mock-selfsigned-card.png`, `screenshots/06-375-C-mock-selfsigned-card.png` |
| **D.** `mock-trusted` / `shared-rnd` (trusted bundle, reachable): green `verified` — recorded only | **Recorded** | Both entries have `tls` `{"insecure": false, "ca": "trusted-bundle"}`, `status` `ok` and no `action`. Both cards' chips are `[{"text": "verified", "class": "badge ok"}]`, and both tls rows read `verified ca: trusted-bundle store /etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt · 152 certificates` (`evidence/D-trusted-bundle-1280.json`, `evidence/walk-live.txt`) |
| **E.** After the throwaway is deleted and discovery removes it: its retired row paints no chip | **PASS** | The Secret was deleted at 07:10:48Z (`evidence/delete-secret.txt`). Discovery cycle 5 logged `removed=w492-fail` at 07:15:36.032Z, 293 s of waiting later (`evidence/wait-discovery-removed.txt`). At 07:15:36.974Z the poller logged `w492-fail: its Secret is gone; the poll thread stops (history kept)` (`evidence/after-podlog.txt`). The API at 07:15:49Z gave `retired: true`, `enabled: false`, `tls: null` and no `action`. The last poll was `2026-09-30T07:15:35Z`, one second before cycle 5, and its `error` is still the raw `CERTIFICATE_VERIFY_FAILED` (`evidence/E-w492-fail-retired.json`). The card's tls row reads `unknown its source no longer describes it`, with chips `[]`, `.badge.ok` 0, no action and no store. The connection row keeps the raw error (`evidence/E-w492-fail-retired.json`). This is the retired branch of `ccTls` (`local-development/gsd/static/index.html#function ccTls`): when `c.tls` is null the function returns before any chip is built. The API's retired rows carry `"tls": None` and are appended without `action` (`local-development/gsd/api.py#list_cluster_configs`). The #244 walk's retired rows `w244-fail` and `w244-exp` read the same way at this version: `tls` null, `action` null, chips `[]` (`evidence/E-w492-fail-retired.json`, `w244_rows_recorded_only`). Screenshot `screenshots/07-1280-E-w492-fail-retired-card.png` |
| **F.** The pod log for the walk's window: 0 `fleet-login`, 0 Traceback, 0 ERROR; the throwaway token in 0 lines | **PASS** | The window runs from 07:06:44Z, captured at 07:15:52Z, and holds 391 lines. It has 0 lines each of `fleet-lookup`, `fleet-ping`, `fleet-login`, `fleet-login-refused`, `fleet-login-failed` and `fleet-logout`. It has 0 lines naming the fleet account, 0 Traceback lines, 0 lines containing `ERROR`, and 0 lines with the walk's bearer token. `cert-verify-failed` appears on 6 lines, one per poll of `w492-fail` from 07:10:35Z to 07:15:35Z (`evidence/after-podlog.txt`) |
| **End state** | **PASS** | The Secret was deleted explicitly at 07:10:48Z (`evidence/delete-secret.txt`) and the grant at 07:15:49Z (`evidence/delete-grant.txt`). The exit trap at 07:15:52Z found nothing left (`evidence/trap-delete.txt`: `No resources found` twice). `oc get secret,clusterrole,clusterrolebinding -A -l walk.gsd.lab/run=chip-492-2026-09-30` answered `No resources found` at 07:06:46Z and at 07:15:52Z (`evidence/before-label-check.txt`, `evidence/after-label-check.txt`). The grant stood for 535 s, from `oc create` at 07:06:54Z (`evidence/grant-create.txt`) to the delete at 07:15:49Z. Its ClusterRole and ClusterRoleBinding were absent at 07:06:46Z, present at 07:06:54Z and absent at 07:15:50Z (`evidence/before-grant.txt`, `evidence/during-grant.txt`, `evidence/after-grant.txt`). Most of that was the wait for discovery, whose cycles are 300 s apart (`evidence/wait-discovery-added.txt`, `evidence/wait-discovery-removed.txt`). `can-i update clusterrolebindings --as=developer` answered `no` at 07:06:46Z, `yes` at 07:10:36Z and `no` at 07:15:50Z (`evidence/before-cani.txt`, `evidence/during-cani.txt`, `evidence/after-cani.txt`). The PVC UIDs were the same before and after: data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` (`evidence/before-pvcs.txt`, `evidence/after-pvcs.txt`). `shared-qa` stayed at resourceVersion 2981054, and every other cluster Secret kept its resourceVersion (`evidence/before-sharedqa.txt`, `evidence/after-sharedqa.txt`, `evidence/before-secrets.txt`, `evidence/after-secrets.txt`). The fleet Lease stayed at resourceVersion 7043788 with holder `""` (`evidence/before-lease.txt`, `evidence/after-lease.txt`). The folder holds 0 files with a `sha256~` value, 0 files naming the fleet account and 0 files with the walk's token (`evidence/end-redaction.txt`) |

## Timeline (UTC, as the files record it)

| Instant | Event | Evidence |
|---|---|---|
| 07:00:21Z | the 1.21.0 dashboard pod starts, before the walk | `evidence/before-pod.txt` |
| 07:06:44Z | walk start; before-captures | `evidence/start-instant.txt`, `evidence/before-version.txt` |
| 07:06:53Z | precheck as `developer` without the grant: no tab, `403` | `evidence/P-precheck.json` |
| 07:06:54Z | CA generated; `gsd-cluster-w492-fail` and the grant created | `evidence/generated-ca.txt`, `evidence/secret-create.txt`, `evidence/grant-create.txt` |
| 07:10:35Z | discovery cycle 4 `added=w492-fail`; first poll `cert-verify-failed` | `evidence/wait-discovery-added.txt`, `evidence/wait-first-poll.txt` |
| 07:10:41Z–07:10:48Z | `walk.py live`: A–D at 1280 px, then A–C at 375 px | `evidence/walk-live.txt` |
| 07:10:48Z | the Secret deleted | `evidence/delete-secret.txt` |
| 07:15:36Z | discovery cycle 5 `removed=w492-fail` | `evidence/wait-discovery-removed.txt` |
| 07:15:45Z–07:15:49Z | `walk.py retired`: E | `evidence/walk-retired.txt` |
| 07:15:49Z | the grant deleted | `evidence/delete-grant.txt` |
| 07:15:50Z–07:15:52Z | after-captures, pod log, label check, exit trap | `evidence/after-version.txt`, `evidence/after-podlog.txt`, `evidence/after-label-check.txt`, `evidence/trap-delete.txt` |

## Observed, outside #492's checks

1. **`/#page=clusters` without the tier read as Home, dimmed: the precheck read the page before its refresh
   painted. Not the product.** The precheck navigated to `/#page=clusters` in the logged-in session, waited 2 s, and
   read `cc_head: false` and `cards: 0`, the page text beginning with Home's `Signed in as developer · developer You
   reach 1 namespace on dashboard …` (`evidence/P-precheck.json`, screenshot
   `screenshots/00-1280-precheck-clusters-without-grant.png`). That screenshot is dimmed: its darkest pixel is
   110 where `screenshots/01-1280-A-w492-fail-card.png` and `screenshots/07-1280-E-w492-fail-retired-card.png` reach
   11 (`evidence/P-precheck-dim.txt`; `--text-primary` is `#0b0b0b`), which is `#main` carrying `stale` (`opacity: 0.55`, `local-development/gsd/static/app.css`), the
   class `refresh()` sets while a reader-initiated fetch is in flight and `render()` removes. A hash change is a
   same-document navigation, so Playwright's `goto(..., wait_until="networkidle")` returns without waiting for the
   refresh it starts, and the 2 s wait was shorter than the lab's refresh of that page: the live pass, which waited
   for `#cc-head` instead, took about 3 s from `whoami` to the tab (`evidence/walk-live.txt`, 07:10:41Z–07:10:45Z).
   On the seeded test rig the same hash change for a reader without the tier paints the refusal card (`Withheld,
   not empty`) once the refresh lands, and so does a cold load, which is what the comment above the
   `view.page === "clusters"` branch says (`local-development/gsd/static/index.html#Reached by URL without the level`);
   `test_a_hash_change_to_the_page_without_the_tier_paints_the_refusal_card_not_home` in
   `local-development/tests/test_ui.py` waits for the paint and pins it. It changes nothing for #492, because the
   tab and the API refused either way. Recorded here, not filed: the reading is the walk's 2 s wait, not the router.
2. **Discovery refused one Secret in both cycles** (`seen=7 accepted=6 refused=1` at cycle 4, and
   `seen=6 accepted=5 refused=1` at cycle 5, `evidence/after-podlog.txt`). The refused one is not the walk's Secret,
   since the count did not change when `w492-fail` came and went. The walk did not look further.

## What is here

- `scripts/`: `run.sh` (before-captures, the exit trap, the precheck, the CA, the Secret and the grant, the waits,
  `walk.py live`, the Secret's delete, the wait for its removal, `walk.py retired`, the grant's delete, the
  after-captures), `walk.py` (the three modes), `capture.sh` (read-only captures, including `redaction`),
  `secrets.sh` (the CA and the Secret) and `grant.yaml`. They were cut down from the #244 walk's scripts
  (`reports/2026-09-29_ca-244-walk/README.md`).
- `evidence/`: 45 files, every one named in the tables above.
- `screenshots/`: 8 PNGs. The fleet row is masked in every capture (`walk.py`, `FLEET_NAME`), as in the earlier walks.

Tokens, passwords and the fleet account's name are not in this folder, and any `sha256~` value is written as
`sha256~<redacted>` (`evidence/end-redaction.txt`). CA subjects, dates and fingerprints are public PKI and are kept.

## How to repeat

```sh
GSD_WALK_TMP=<a directory outside the repo> KUBECONFIG=<the lab kubeconfig> \
  reports/2026-09-30_chip-492-walk/scripts/run.sh
GSD_WALK_TMP=<the same directory> KUBECONFIG=<the lab kubeconfig> \
  reports/2026-09-30_chip-492-walk/scripts/capture.sh redaction end   # after the README is written
```
