# Epic C (#383) lab walk for #432 — SPEC_S4c §3.12 as corrected by SPEC_S4e, as `developer`, application 1.4.0 (2026-09-27 UTC)

## The outcome in brief

- **What ran.** The lab ran application 1.4.0 under Argo CD: `Synced`/`Healthy` at main `6fe404c`, image
  `quay.io/ephico2real/group-sync-dashboard:1.4.0`, and `/api/version` `1.4.0` at `6a83e3edda`, the release that carries
  #432 (`evidence/start-version.txt`, `evidence/start-argo.txt`). Main moved from `6a83e3e` to `6fe404c` by reports and
  a session log only: `git diff --quiet 6a83e3e 6fe404c -- charts gitops environments local-development` holds.
  - The walk deployed 6a83e3e's own images with its values through `release-crc.sh --values`, in Helm mode.
  - It restored the lab with `release-crc.sh --argocd main` at 22:51:32Z.
- **What was walked.** SPEC_S4c §3.12 steps 0–5 and 7 ran, as `developer` only. Step 6 was not run; the reasons are
  below.
  - The lab check (SPEC_S4e §5) printed `0 0 0` before every step that placed a password. It ran 6 times, each within
    seconds of the step it guarded. The run as found printed `1 0 0`, as SPEC_S4e measured.
- **The fleet account `ocp-oauth-bind-serviceid`:**
  - 0 authorizes in the oauth-server audit log since the walk's start, 21:39:46Z, in the log as captured at its end,
    22:57:02Z;
  - 2 `openshift-challenging-client` tokens (created 2026-09-19T00:48:44Z and 00:50:11Z) at the start, at every
    capture and at the end;
  - its Lease `gsd-fleet-666f1ba7f2fdead0` byte-identical at the start, at every step and at the end: resourceVersion
    `5127386`, sha256 `96e37278…`;
  - no `fleet-*` line in the captured pod logs names it. The captures:
    - the Argo pod's, to 21:40:11Z;
    - the first walk pod's, 21:44:28Z–22:28:16Z (its first 94 s and last 31 s are in no capture);
    - the second walk pod's whole life;
    - the restored pod's, to 22:56:55Z.
  - The audit log, which is the measure, covers the whole window.
- **`developer`:** 12 authorizes in that window, each one a product login in the pod's log:
  - the lookup, and 7 successful pings;
  - 1 refused ping (step 3);
  - 2 self-login logins (steps 4 and 5a), and 1 refused self-login re-authentication (step 5b).
  - Its challenging-client tokens ended as they started: the count and the creation times match.
- **Step 3, the wrong password:**
  - one refused authorize at 22:08:00.609Z, and none across the three cadences after it (22:13, 22:18, 22:23Z);
  - the ping stood down once (`fleet-ping-failed … gave_up=true suspended=developer scope=ping`);
  - after the rotation back it confirmed once (22:28:00Z).
- **Step 5, the reactive path:**
  - a revoked session re-authenticated once, with no refusal recorded;
  - with a wrong password, the re-authentication was refused once. `fleet-credential-suspended … scope=self-login
    stopped=1` followed, and `gsd_cluster_up{cluster="walk-self-login"}` fell to `0`. No second authorize came across
    the two ping cadences after it.
- **After the restore:**
  - Argo is `Synced`/`Healthy` at `6fe404c3…`, and its `syncPolicy` is byte-identical to the one recorded before the
    pause (`automated {prune, selfHeal}`);
  - `/api/version` reads `1.4.0` (`6a83e3edda`) on the published image, at the digest the walk started with;
  - the PVC UIDs are unchanged, and no walk object remains in the cluster's API. The retired database rows and the
    registry images are noted below.
  - the dashboard ServiceAccount's `get` on `ldap-oauth-bind-secret` answered `yes` at every capture.

## Definition of Done

One row per lab item of each issue this walk can close. The items that are not lab items were closed elsewhere:
- #432's hermetic test, review and version bump: PR #438;
- #285's code items: PR #419;
- #286's documentation items and #310's Part B: their own PRs.

NOT RUN means the walk did not perform the item, and says why.

| Issue | Definition of Done item | Result | Evidence |
|---|---|---|---|
| #432 | "SPEC_S4c §3.12 corrected, reviewed, and walked on the lab as `developer` only" — the walk | **PARTIAL.** Steps 0–5 and 7 walked, as `developer` only. Step 6 not run ("What was not run"). The correction and its review are #438's. | this README; `evidence/step*` |
| #432 | "The fleet account's token count stays 2" | **PASS.** 2 → 2; the count and the creation times match. Token names and UIDs were not captured. | `evidence/start-tokens.txt`, `evidence/end-tokens.txt` |
| #432 | "…and its audit-log authorizes stay 0" | **PASS.** 0 since 21:39:46Z, in the log as captured at 22:57:02Z. | `evidence/end-walk-window-audit.txt` |
| #383 | "On the lab, #285's walk step 3 (as `developer`) counts one authorize on the oauth-server across three cadences." | **PASS.** 1 since 22:03:41Z, in the log as captured at 22:24:05Z: the deny at 22:08:00.609Z. None at the 22:13, 22:18 and 22:23Z cadences. | `evidence/step3-three-cadences-audit.txt`, `evidence/step3-podlog.txt` |
| #383 | "`… select(.userName=="ocp-oauth-bind-serviceid") …` still returns 2" | **PASS.** | `evidence/end-tokens.txt` |
| #383 | "Deployed to CRC through `release-crc.sh --argocd`, walked, PVC UIDs unchanged." | **Deployed: PASS**, by the restore's `release-crc.sh --argocd main`. **Walked: PARTIAL** (step 6). **PVC UIDs: PASS.** | `evidence/step7-release-crc-argocd-main.log`, `evidence/end-argo.txt`, `evidence/start-pvcs.txt`, `evidence/end-pvcs.txt` |
| #285 | "Deployed to CRC through `release-crc.sh --argocd`" | **PASS.** | same |
| #285 | "…and walked per SPEC_S4c §3.12, as `developer` only" | **PARTIAL.** Steps 0–5 and 7; step 6 not run. | this README |
| #285 | "Step 3, the deliberately wrong password, counts exactly one authorize across three cadences." | **PASS.** | `evidence/step3-three-cadences-audit.txt` |
| #285 | "The `developer` `OAuthAccessToken` count ends where it started" | **PASS.** 3 → 3; the count and the creation times match: 2026-09-23T07:34:50Z, 2026-09-26T04:25:57Z and 2026-09-26T14:35:41Z. | `evidence/start-tokens.txt`, `evidence/end-tokens.txt` |
| #285 | "…and the fleet account's count is still 2." | **PASS.** | same |
| #285 | "The Secret `gsd-cluster-shared-rnd`'s `resourceVersion` is unchanged across a ping." | **PASS**, across `developer`'s pings. `2835139` at all 12 Secret captures, across 7 successful pings, 1 refused ping (22:08:00Z) and the lookup. The pings' own target, `gsd-cluster-walk-lookup`, kept `5504203` from its creation through every ping. The fleet account's own ping was not due during the walk: its last was 10:27:05Z, its interval 86400 s. | `evidence/*-secrets.txt`; the pings: `evidence/step2-podlog.txt`, `evidence/step3-podlog.txt`, `evidence/step3-rotate-back-podlog.txt`, `evidence/step4-5-pod-podlog.txt` |
| #285 | "PVC UIDs are recorded before and after and unchanged." | **PASS.** `f065b7a4-…` and `08c7d45c-…`. | `evidence/start-pvcs.txt`, `evidence/end-pvcs.txt` |
| #285 | "Screenshots of the tab's two rows." | **NOT RUN.** The tab needs the dashboard's cluster-admin tier (`update clusterrolebindings`), and `developer` does not hold it (`can-i`: `no`). The brief grants no tier and rules out `kubeadmin`. No script here logs in or calls the dashboard's route: they read `/api/version` and `/metrics` on the pod's loopback. The artefacts do not record which identity the lab's kubeconfig carries. The rows' data was read from the Leases and `/metrics` instead. | `evidence/start-cani.txt`, `evidence/*-leases.txt`, `evidence/*-metrics.txt` |
| #285 | "Evidence committed under `reports/<date>_<slug>/` and posted here, pinned to the full merge sha." | **PARTIAL.** Committed in this folder, not pushed, per the brief. Posting on the issue is the orchestrator's. | this folder |
| #286 | "After #285's deploy: the counts table above re-measured" | **PASS.** The table below. | `evidence/start-tokens.txt`, `evidence/end-tokens.txt` |
| #286 | "…and the ping's account's challenging-client count unchanged across ≥ 3 cadences" — `developer`, per §3.12 | **PASS.** 3 before the first ping, 3 after four cadences (21:47:59–22:03:00Z), 3 after the confirming ping (22:28:00Z), and 3 at the end. Each of the 7 successful pings logged `fleet-logout … outcome=revoked`. | `evidence/start-tokens.txt`, `evidence/step2-end-tokens.txt`, `evidence/step3-end-tokens.txt`, `evidence/end-tokens.txt`, `evidence/step2-podlog.txt`, `evidence/step3-rotate-back-podlog.txt`, `evidence/step4-5-pod-podlog.txt` |
| #286 | "The fleet account `ocp-oauth-bind-serviceid` is still at 2." | **PASS.** | `evidence/end-tokens.txt` |
| #310 | "Part A, after #285: a renewal **observed**…" | **NOT RUN.** It is not part of §3.12. It needs `oauth/cluster`'s `accessTokenMaxAgeSeconds` lowered to 600: a cluster-wide change that restarts the oauth-openshift pods, and this walk's brief does not name it. The walk shows the schedule and the reactive path only. `self-login-renewed … renew_at=2027-09-27T20:33:28Z` is two hours before `expires_at` (22:33:28Z). | `evidence/step4-5-pod-podlog.txt` |
| #310 | "Part A: `accessTokenMaxAgeSeconds` is restored to `31536000`. The lab is left as found…" | **NOT RUN.** Nothing was lowered, so there was nothing to restore. `{"accessTokenMaxAgeSeconds":31536000}` at the start and at the end. Entries, Secrets and PVC UIDs are recorded at both ends. | `evidence/start-oauth.txt`, `evidence/end-oauth.txt`, `evidence/start-secrets.txt`, `evidence/end-secrets.txt` |

## The lab check, every run (SPEC_S4e §5)

`scripts/labcheck.sh` runs the spec's three commands verbatim. It exits `0` only on `0 0 0`, and a failed read never
counts as `0`. Each file names the objects it counted over.

| Run | At (UTC) | Counts | What it guarded | Evidence |
|---|---|---|---|---|
| as found, before any deploy (informational) | 21:40:34Z | `1 0 0` | nothing: the Argo configuration names the fleet account, as SPEC_S4e §5 measured | `evidence/as-found-informational-labcheck.txt` |
| step 2, before the walk Secret | 21:44:28Z | `0 0 0` | the Secret, created 21:44:28Z | `evidence/step2-before-walk-secret-labcheck.txt` |
| step 3, before the wrong password | 22:03:41Z | `0 0 0` | the rotation, 22:03:41Z | `evidence/step3-before-wrong-password-labcheck.txt` |
| step 3, before the rotation back | 22:24:49Z | `0 0 0` | the rotation, 22:24:49Z | `evidence/step3-before-rotate-back-labcheck.txt` |
| step 4, before the self-login deploy | 22:28:39Z | `0 0 0` | the deploy, 22:28:46Z | `evidence/step4-before-deploy-labcheck.txt` |
| step 4, after it | 22:29:23Z | `0 0 0` | the session's first login, 22:29:29Z | `evidence/step4-after-deploy-labcheck.txt` |
| step 5, before the wrong password | 22:39:18Z | `0 0 0` | the rotation and the session's deletion, 22:39:18Z | `evidence/step5b-before-wrong-password-labcheck.txt` |

## The fleet account's evidence, before and after

| Measure | Start (captures 21:39:46Z–21:40:09Z) | End (captures 22:56:55Z–22:57:02Z) |
|---|---|---|
| `openshift-challenging-client` `OAuthAccessToken`s for `ocp-oauth-bind-serviceid` | 2 (2026-09-19T00:48:44Z, 00:50:11Z) | 2; the count and the creation times match |
| Its Lease `gsd-fleet-666f1ba7f2fdead0` | resourceVersion `5127386`, sha256 `96e3727807355ca16f9299e067bada4e3a1e83f3a335410ac432f78f85ea9d45`, `ping-last-ok` 2026-09-27T10:27:05Z | the same, at every capture between |
| Its view in `/api/clusterconfigs` `.fleet` | not read: the route needs the cluster-admin tier (above) | not read |
| `gsd_fleet_account_last_ok_timestamp_seconds`, the oldest `last_ok` across the served accounts | `1.790504825e+09` = 10:27:05Z | the same. It held at every capture while `developer`'s Lease recorded newer successes, so the fleet account's row stayed served, as history (SPEC_S4e §3.5 item 5) |
| Audit-log authorizes | today before the walk: 1 allow at 10:27:06.048Z, the product's daily ping | **0** since 21:39:46Z, in the log as captured at 22:57:02Z |
| `developer`'s challenging-client tokens | 3 | 3; the count and the creation times match |

## The walk, step by step

The pods: `…-c9664c7c4-2lv9v` (Argo, before), `…-6dc7997df8-snrqn` (steps 2–3), `…-79944d6c8f-8vzjm` (steps 4–5),
and `…-c9664c7c4-cxs9b` (Argo, restored).

**Step 0 — two checks before anything is deployed.**
- `/api/version` through the pod's loopback read `1.4.0` at `6a83e3edda`: the release whose commit `efb2f40` sets
  application 1.4.0 for #432, and whose CHANGELOG entry cites #432 (`evidence/start-version.txt`).
- `scripts/render_check.sh` rendered both walk files with `helm template` from 6a83e3e's chart:
  - each renders `fleetAccountUsername: "developer"`, every `ldapConnectionBootstrap` is `developer`, and `grep -c
    ocp-oauth-bind-serviceid` is `0`;
  - the Argo shape renders `1` (`evidence/step0-render-check.txt`).
- Both walk files equal `environments/crc.yaml` outside their two marked blocks, parsed
  (`evidence/step0-values-compare.txt`).

**Step 1 — baseline, grants, pause, deploy.**
- The baseline is `evidence/start-*.txt` and `evidence/start-audit-*`.
- The three grants of `prepared/walk-rbac.yaml` were applied after a server-side dry run
  (`evidence/step1-walk-rbac-apply.txt`).
- Rendered RBAC, as effective grants per subject (`evidence/step0-rbac-diff.txt`):
  - without the grants, the walk values REMOVE one ServiceAccount grant, `get` on `ldap-oauth-bind-secret`;
  - with them, REMOVED is `0` for both walk files.
- Argo's `syncPolicy` was recorded, and `automated` removed (`evidence/step1-argo-pause.txt`).
- `release-crc.sh --values` built `1.4.0-6a83e3edda` and installed Helm revision 1 at 21:42:50Z
  (`evidence/step1-release-crc-values-ping.log`).
- The new pod stood by until the old pod's leader Lease expired, and led from 21:43:19Z. That was read from its log at
  21:44:17Z; the pod is gone.
- The audit log holds no `developer` authorize before 21:47:59Z.

**Step 2 — the ping, as `developer`.**
- The walk Secret was created at 21:44:28Z (`evidence/step2-walk-secret-create.txt`: name, resourceVersion and uid
  only).
- At the next cadence, 21:47:59Z, the lookup logged in as `developer`:
  - `fleet-login cluster=walk-lookup account=<redacted>`, `fleet-logout … outcome=revoked`, then
    `cluster-secret-created secret=gsd-cluster-walk-lookup` and `fleet-lookup cluster=walk-lookup account=<redacted>`;
  - `account=<redacted>` is the redactor at work, as §3.12 step 2 says it would be.
- The immediate re-discovery pinged: `fleet-ping account=<redacted> target=walk-lookup last_ok=2026-09-27T21:47:59Z`.
- `developer`'s Lease `gsd-fleet-88fa0d759f845b47` appeared: `ping-last-ok` 21:47:59Z, outcome `ok`, target
  `walk-lookup`, `leaseDurationSeconds` 195.
- Three more cadences each pinged once: 21:53:00, 21:58:00 and 22:03:00Z.
- No `fleet-*` line named the fleet account, and its Lease stayed byte-identical (`evidence/step2-*`).

**Step 3 — the stand-down.**
- The walk Secret was rotated in place to a random wrong password at 22:03:41Z. It was done with `oc replace`, and the
  uid was unchanged (`evidence/step3-walk-secret-wrong.txt`).
- 22:08:00Z, the refusal:
  - `fleet-login-refused … cluster=walk-lookup account=developer … 401 Unauthorized … no second attempt is made`;
  - then `fleet-ping-failed … outcome=login-refused … attempt=1/1`;
  - the Lease recorded `refused` `{at: 22:08:00Z, code: login-refused, target: https://api.crc.testing:6443}`, and
    `gsd_fleet_account_suspended` read `1`.
- 22:13:00Z, the stand-down, said once: `fleet-ping-failed … gave_up=true suspended=developer scope=ping`. Nothing
  followed at 22:18 or 22:23Z. The audit log holds one authorize in the window, the deny.
- The rotation back at 22:24:49Z gave one confirming ping at 22:28:00Z, one allow. That success cleared the `refused`
  entry, and `gsd_fleet_account_suspended` read `0` again.

**Step 4 — `self-login`, as `developer`, with the ping still on.**
- `release-crc.sh --values` reused the image and upgraded to Helm revision 2 at 22:28:46Z
  (`evidence/step4-release-crc-values-selflogin.log`).
- The new pod led from 22:29:23Z.
- At 22:29:29Z, `fleet-login cluster=walk-self-login account=<redacted> … expires_at=2027-09-27T22:29:29Z`: a year
  out.
- `polled walk-self-login: 3 CRs, 66 groups`, and `gsd_cluster_up{cluster="walk-self-login"} 1`.
- `renew_at` is two hours before `expires_at`:
  - by the rule, 2027-09-27T20:29:29Z for this session;
  - the product logs it on renewal — `renew_at=2027-09-27T20:33:28Z` for the 5a session below.
- The tab, which shows both, was not read (above).

**Step 5 — the reactive path.**
- **5a.** `scripts/delete_session_token.sh` deleted exactly one object, as cluster-admin, at 22:30:17Z. It is the
  `developer` challenging-client token whose creation plus `expiresIn` equals the logged `expires_at`.
  - The session's polls at 22:30:28 and 22:31:28Z still succeeded.
  - The 401 came at 22:32:28Z: `cluster-unreachable … outcome=auth_failed`, then `self-login-failed … reauth=next-cycle
    … nothing is recorded as a refusal`.
  - 22:33:28Z, one login:
    - `fleet-login cluster=walk-self-login`;
    - `fleet-logout-failed … outcome=auth_failed`, the revoke of the token the walk had deleted — #283's reading of a
      401 on a revoke, "may still exist". The object was gone.
    - `self-login-renewed … reauth=true`, and the poll was green again.
  - No refusal: no `refused` entry, and `gsd_fleet_account_suspended 0` (`evidence/step5a-*`).
- **5b.** Right after the 22:38:53Z ping, the lab check printed `0 0 0` at 22:39:18Z. Then the password was rotated to
  a wrong one, and the new session's token deleted.
  - 22:39:28Z, the 401, then `self-login-failed … reauth=next-cycle`.
  - 22:40:29Z, the refusal:
    - the re-authentication was refused once: `fleet-login-refused … cluster=walk-self-login account=developer`;
    - `fleet-credential-suspended … account=developer suspended=developer scope=self-login stopped=1
      clusters=walk-self-login`;
    - `gsd_cluster_up{cluster="walk-self-login"} 0`, the card critical.
  - At the next cadence, 22:43:53Z, the ping stood down once (`… scope=ping`), and `gsd_fleet_account_suspended`
    read `1`.
  - The audit log, as captured at 22:49:36Z, holds one authorize since 22:39:18Z: the deny. The parked cluster made
    no further login
    (`evidence/step5b-*`).

**Step 6 — two processes.** Not run. See "What was not run".

**Step 7 — the end.**
- Before removal, at 22:49:58Z, the counts equalled the start:
  - `developer` 3, the fleet account 2, 194 objects in all;
  - the fleet Lease byte-identical;
  - `shared-qa` (rv `2981054`) and `shared-rnd` (rv `2835139`) unchanged (`evidence/step7-before-removal-*`).
- The removal ran in an order that keeps every password off the wire and never drops a ServiceAccount permission
  (`evidence/step7-removal-before-restore.txt`):
  - 22:50:17Z: the walk Secret (by label), `gsd-cluster-walk-lookup` (by name: the product made it, unlabelled) and
    `developer`'s two grants (by label).
  - 22:50:28Z–22:51:32Z: the restore, `release-crc.sh --argocd main` from a clean checkout of main `6fe404c`. Helm
    uninstalled, keeping both PVCs by their resource policy, and Argo synced (`evidence/step7-release-crc-argocd-main.log`).
  - 22:52:05Z, with the chart's `group-sync-dashboard-fleet-account` Role back in openshift-config and `can-i`
    answering `yes`: the keep-grant, by label. `can-i` still answered `yes` (`evidence/step7-keep-grant-removal.txt`).
  - 22:52:19Z: `developer`'s Lease, by name, once the restored configuration named no `developer` account
    (`evidence/step7-developer-lease-removal.txt`). Its resourceVersion was still `5534296`, the refusal's: nothing
    wrote it after the walk Secret went.
- The restored pod led from 22:50:54Z. It logged `retired 2 cluster(s) no longer in the configuration`, and no
  `fleet-*` line, through 22:56:55Z (`evidence/end-restored-pod-podlog.txt`).

## Every `developer` authorize in the window

The audit rows are derived: `ResponseComplete` records of `GET /oauth/authorize?client_id=openshift-challenging-client`
for `developer` and the fleet account only (`evidence/end-walk-window-audit.txt`).

| Audit record (UTC) | Decision | The pod's line | Step |
|---|---|---|---|
| 21:47:59.773507Z | allow 302 | `fleet-login cluster=walk-lookup` → `fleet-lookup` | 2, the lookup |
| 21:47:59.897630Z | allow 302 | `fleet-ping … last_ok=21:47:59Z` | 2 |
| 21:53:00.057731Z | allow 302 | `fleet-ping … last_ok=21:52:59Z` | 2 |
| 21:58:00.194953Z | allow 302 | `fleet-ping … last_ok=21:58:00Z` | 2 |
| 22:03:00.315588Z | allow 302 | `fleet-ping … last_ok=22:03:00Z` | 2 |
| 22:08:00.609105Z | **deny 401** | `fleet-login-refused cluster=walk-lookup` → `fleet-ping-failed … attempt=1/1` | 3 |
| 22:28:00.813810Z | allow 302 | `fleet-ping … last_ok=22:28:00Z` | 3, the rotation back |
| 22:29:29.359422Z | allow 302 | `fleet-login cluster=walk-self-login` | 4 |
| 22:33:28.677799Z | allow 302 | `fleet-login cluster=walk-self-login` → `self-login-renewed … reauth=true` | 5a |
| 22:33:53.776069Z | allow 302 | `fleet-ping … last_ok=22:33:53Z` | 5a, the ping still on |
| 22:38:53.897915Z | allow 302 | `fleet-ping … last_ok=22:38:53Z` | 5b, before the rotation |
| 22:40:29.079091Z | **deny 401** | `fleet-login-refused cluster=walk-self-login` → `fleet-credential-suspended … stopped=1` | 5b |

No record carried no username in the window.

## #286's counts table

| `OAuthAccessToken` objects | 2026-09-26 (#286) | start (21:39:46Z) | end (22:56:55Z) |
|---|---|---|---|
| all objects | 189 | 194 | 194 |
| the dashboard's oauth-proxy (`system:serviceaccount:group-sync-dashboard:group-sync-dashboard`) | 131 | 136 | 136 |
| `openshift-challenging-client` | 30 | 30 | 30 |
| `console` | 16 | 16 | 16 |
| grafana's ServiceAccount client | 10 | 10 | 10 |
| Argo CD dex | 2 | 2 | 2 |
| the fleet account | 2 | 2 | 2 |
| `developer`, `openshift-challenging-client` | 3 | 3 | 3 |

## Where the lab differed from the spec's words

- **Step 5's "the next poll's 401".**
  - In 5a, the deleted token was still accepted by two polls, at 22:30:28 and 22:31:28Z. The poll at 22:32:28Z, 131 s
    after the deletion, was refused.
  - In 5b, the poll 10 s after the deletion was refused.
  - This is consistent with the API server caching a token's authentication; the cause was not measured. The product's
    behaviour after the 401 was as specified both times.
- **`gsd_fleet_account_suspended` follows the Lease a cadence late.** It is refreshed by the discovery sweep's read of
  the Lease.
  - It read `0` at 22:41:17Z, after the 22:40:29Z refusal.
  - It read `1` after the 22:43:53Z sweep (read at 22:49:37Z).
  - In step 3 it was first read at 22:13:34Z, after the next sweep, so its delay there was not measured.
- **A revoke of a token the walk had deleted is logged `fleet-logout-failed … outcome=auth_failed`.** It happened in
  5a and in 5b. It is #283's deliberate reading of a 401 on a revoke. The counts show the objects were gone.
- **Each deploy's new pod stood by until the previous pod's leader Lease expired:** 25 s (21:42:54→21:43:19Z), 31 s
  (22:28:52→22:29:23Z) and 8 s (22:50:46→22:50:54Z).
  - The leadership instants are in `evidence/step4-5-pod-podlog.txt` and `evidence/end-restored-pod-standby.txt`. The
    first pod's was read from its log at 21:44:17Z; that pod is gone.
  - The walk pods' "not leader, skipping poll" lines were read, not kept.
  - The audit log holds no `developer` authorize inside either walk pod's standby.

## What was not run, and why

- **§3.12 step 6, a second copy of the app out of cluster.** Stopped as ambiguous, per the brief. Four reasons,
  the first three read in the code and the fourth in `prepared/walk-rbac.yaml`:
  1. **A process that remains a leader-election standby cannot demonstrate `ClaimHeld`.** It skips self-login
     acquisition, pending lookups and pings before any fleet-account claim.
     - `local-development/gsd/poller.py#Poller._run_cluster`'s standby branch skips the poll: "not leader, skipping
       poll". The line was read in both walk pods' logs after their deploys (not kept; the pods are gone).
     - `local-development/gsd/poller.py#Poller._retrieve_pending` returns before any lookup.
     - `local-development/gsd/poller.py#Poller._ping_accounts` pings only as leader.
  2. **An out-of-cluster copy is not a standby by default.**
     - A process without the standard ServiceAccount token file assumes leadership, even when `leaderElection` is
       `true`: `local-development/gsd/leader.py#LeaderElector.start`, and `local-development/gsd/leader.py#_in_cluster`.
     - The spec does not define the external token and election setup.
     - Nor does it say how an overlapping claim on a held account Lease is made.
  3. **A second active process may bind.** It may acquire a session, or a due ping, subject to the shared claim and to
     the refusal and cadence gates: `local-development/gsd/selflogin.py#SelfLoginSessions._acquire` and
     `local-development/gsd/poller.py#Poller._ping_accounts`.
  4. **The pod's ServiceAccount token, copied out of the cluster, could read the fleet account's password** through
     the keep-grant, from a workstation process. Neither the brief nor the spec says how that token is to be held.
  - Step 6 remains NOT RUN, pending a clarified procedure and acceptance criterion.
  - Stand-ins, re-run on 1.4.0's code:
    - R1, two processes cannot both win one claim, and no claim is no bind;
    - R2, 1 authorize across two processes, three targets, a restart and an edit;
    - with R3–R7: 16 passed;
    - SPEC_S4e's suite, the walk tests included: 24 passed (`evidence/hermetic-stand-ins.txt`).
- **The tab's rows, as screenshots, and the `/api/clusterconfigs` `.fleet` view.**
  - Both need the dashboard's cluster-admin tier. `developer` does not hold it, the brief rules out `kubeadmin`, and no
    script here calls the dashboard's route.
  - The tier grant a walk could use is PR #442's temporary `update clusterrolebindings` for `developer` (its
    `scripts/grant.yaml`). This brief does not list it, so it was not applied.
- **#310 Part A**, above.

## Procedure notes

- **Step 3's first check was gated through a pipe.** The command was `if labcheck.sh … | tail -1; then`, which tests
  `tail`'s status, not the check's.
  - The check itself printed `0 0 0` at 22:03:41Z: `evidence/step3-before-wrong-password-labcheck.txt` ends
    `0 0 0`.
  - The script prints its counts only after every read has succeeded, and exits `0` on exactly these counts. That exit
    code was not captured.
  - A failing check would not have blocked that rotation, though.
  - Every later gate tested `labcheck.sh`'s own exit code.
- **The pod-log filter was narrowed after step 3,** to the fleet, self-login and discovery loggers plus failed polls;
  steps 2 and 3 were re-captured with it. `evidence/step2-podlog.txt` runs from 21:44:28Z to its capture at 22:24:33Z,
  so it holds step 3's lines too.
- **The removal order differs from the brief's bullet order.**
  - The keep-grant came off after the restore, once `can-i` showed the chart's grant back: removing it earlier would
    have dropped the ServiceAccount's `get` for the length of the handover.
  - `developer`'s Lease came off after the restore: a pending lookup under the walk values claims, and so recreates,
    it.
  - Everything else was removed before the restore.
- **The walk's two clusters remain as retired rows** in the dashboard's database: `walk-lookup` and `walk-self-login`,
  "retired 2 cluster(s)" at 22:50:54Z. The product keeps a cluster's history when it leaves the configuration (#96),
  and the walk deletes no database rows.
- **The product's own unmanaged-grant audit reported the walk's grant.** `UNMANAGED GRANT DISCOVERED — …:
  ClusterRoleBinding gsd-walk-developer-poller … grants group-sync-dashboard-cluster-poller to user developer`.
  - It was reported on `dashboard`, `shared-qa` and `shared-rnd` from 21:43:24Z, then on `walk-lookup` and
    `walk-self-login` when they first polled.
  - These lines were read from the walk pods' logs during steps 1, 2 and 4, and not kept; the pods are gone.

## Every write this walk made on the lab

In order:
- 21:41:09Z: the three grants of `prepared/walk-rbac.yaml`.
- 21:41:28Z: `automated` removed from the Application's `syncPolicy`.
- 21:41:45–21:43:35Z: `release-crc.sh --values prepared/walk-values-ping.yaml`. It built and pushed `1.4.0-6a83e3edda`
  to the internal registry, deleted the Application (cascade) and installed Helm revision 1.
- 21:44:28Z: the walk Secret, created.
- 22:03:41Z, 22:24:49Z and 22:39:18Z: the walk Secret, replaced in place.
- 22:28:46Z: Helm revision 2 (`prepared/walk-values-selflogin.yaml`).
- 22:30:17Z and 22:39:18Z: one `developer` `OAuthAccessToken` each, deleted: the walk's own session.
- 22:50:17Z: the walk Secret, `gsd-cluster-walk-lookup` and `developer`'s two grants, deleted.
- 22:50:28–22:51:32Z: `release-crc.sh --argocd main`, which uninstalled Helm and re-applied the Application.
- 22:52:05Z: the keep-grant, deleted.
- 22:52:19Z: `developer`'s Lease, deleted.

The product itself wrote:
- `gsd-cluster-walk-lookup`;
- `developer`'s Lease;
- its logins' own tokens, each revoked;
- its database rows.

The images `1.4.0-6a83e3edda` (both) stay in the internal registry: published images are never deleted.

Proof of the end state:
- `evidence/end-walkobjects.txt`: 0 labelled objects, and `gsd-cluster-walk-lookup`, `gsd-fleet-88fa0d759f845b47` and
  the walk Secret all `not found`;
- `evidence/end-cani.txt`: `developer` holds none of the walk's grants.

## Files

- `README.md`: this document.
- `prepared/`, read before use and applied as they are:
  - the two walk values files (each `environments/crc.yaml` at 6a83e3e with two marked blocks);
  - the three grants;
  - the Argo `valuesObject`, for rendering the Argo shape.
- `scripts/`: no password or token in any of them. What each one does:
  - `labcheck.sh` runs SPEC_S4e §5's three `oc … | jq` counts. It prints them only after every read has succeeded,
    and exits `0` only on `0 0 0`, `1` on any other counts, and `2` on a failed read.
  - `snapshot.sh` makes ten read-only captures:
    - `OAuthAccessToken` counts and creation times, never names;
    - the PVCs and the Argo Application;
    - `/api/version` on the pod's loopback, with the Deployment's images and the pod's image digests;
    - the fleet-account Leases, with digests shown as `<redacted>` beside a sha256 of each whole unredacted object;
    - the cluster Secrets' metadata, and the ConfigMap's fleet keys and clusters list;
    - `oc auth can-i`, with the names of the openshift-config Roles and RoleBindings;
    - `oauth/cluster`'s token config, and the walk's objects.
  - `capture.sh` makes three captures:
    - `podlog`: `oc logs`, filtered, with `sha256~` names redacted;
    - `metrics`: `/metrics` on the pod's loopback;
    - `audit`: every `oauth-server/audit*.log` read with `oc adm node-logs` into a `mktemp -d` directory that a trap
      removes on exit. It keeps only the derived rows for `developer` and the fleet account, and a count of the
      records that carry no username.
  - `render_check.sh` runs `helm template`, offline, on each walk file and on the Argo shape:
    - for each walk file, it reads the rendered ConfigMap's `fleetAccountUsername`, every `ldapConnectionBootstrap`,
      and the count of the fleet account's name;
    - for the Argo shape, it reads `fleetAccountUsername` and that count.
  - `rbac_grants.py` expands the bindings and rules of rendered manifests into per-subject grants, and prints REMOVED
    and ADDED. It runs offline.
  - `walk_secret.sh` creates or rotates the walk Secret:
    - `create` and `right` read `developer`'s password with `crc console --credentials -o json | jq -r
      '.clusterConfig.developerCredentials.password'`; `wrong` generates one with `openssl rand -hex 16`;
    - the value is held in a shell variable inside the script's own process;
    - it reaches `oc` as `--from-literal=password=…` on the command line of `oc create secret generic
      … --dry-run=client -o json`, whose output is piped through `jq`, which adds the walk label, into `oc create -f -`
      or `oc replace -f -`;
    - the script prints only the Secret's name, resourceVersion, uid and last-applied annotation, which is empty,
      then unsets the variable.
  - `delete_session_token.sh` finds the session to delete and deletes it only if exactly one token matches:
    - it takes `expires_at` from the pod log's last `fleet-login cluster=walk-self-login` line;
    - it keeps `developer`'s `openshift-challenging-client` tokens created since the walk's start whose
      `creationTimestamp + expiresIn` is within 3 s of that instant;
    - it deletes the match only when exactly one matches, by a name it never prints, and otherwise refuses.
  - `wait_for_log.sh` reads the dashboard container's log every 20 s until a pattern has matched `n` times, or its
    timeout passes.
- `evidence/`: every capture, named `<when>-<what>.txt`, with its command and instant as the header.
  - `sha256~` names are redacted.
  - Lease digests are `<redacted>`; their byte-identity is the sha256 of the whole unredacted object.
  - No raw audit log is in this folder, only the derived rows (`capture.sh audit`, above).

## How to re-run

From a checkout of this repository, with the lab's kubeconfig in `KUBECONFIG`, in this order:
1. `scripts/snapshot.sh start`.
2. `scripts/render_check.sh step0 <repo> prepared/walk-values-*.yaml`.
3. `oc apply -f prepared/walk-rbac.yaml`.
4. Pause Argo.
5. `release-crc.sh --values <the ping file>`, from a clean checkout of the release commit.
6. `scripts/labcheck.sh <label>`, and then, only on exit 0, `scripts/walk_secret.sh create`.
7. The same pair, with `wrong` and then `right`.
8. `release-crc.sh --values <the self-login file>`, with the lab check before and after it.
9. `scripts/delete_session_token.sh <start>` for 5a. For 5b, `scripts/labcheck.sh`, then `walk_secret.sh wrong` and
   `delete_session_token.sh` right after a ping cadence.
10. The removal and the restore, in the order under "Step 7".

Keep `scripts/capture.sh audit <label> <start>` running beside every step.
