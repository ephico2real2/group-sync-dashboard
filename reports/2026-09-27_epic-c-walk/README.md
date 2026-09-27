# Epic C (#383) lab walk — application 1.0.0, chart 0.59.2 (2026-09-27 UTC): measured read-only, live steps not run

## The outcome in brief

- **What runs** (`evidence/start-deployment.txt`, `evidence/start-api-version.txt`, `evidence/start-argo-application.txt`,
  `evidence/end-chart-and-cluster-version.txt`):
  - OpenShift 4.22.7.
  - The Argo CD Application `group-sync-dashboard` is `Synced`/`Healthy` at main `22a485c`, with auto-sync
    `{prune, selfHeal}`.
  - Chart `group-sync-dashboard-0.59.2`, image `quay.io/ephico2real/group-sync-dashboard:1.0.0`.
  - `/api/version` read through the pod's loopback: `"version":"1.0.0","commit":"05e32c8394"`.
- **The live steps did not run, because the walk's password was never provided.** The `developer` password was to come
  from `~/.config/gsd/walk.env`. That file was absent for the whole wait: checked every 60 s from 12:43Z to 13:19:37Z
  (`WALK_ENV_ABSENT after 36 minutes`), and still absent at 13:19:45Z. Every step that needs no password was done.
- **A safety finding stops SPEC_S4c §3.12 steps 2 and 3 as written on this lab**, whether or not the password
  arrives:
  - The fleet password Secret is process-wide, and the daily ping pings every account that a retrieved cluster's
    Secret records.
  - `gsd-cluster-shared-rnd` records the fleet account.
  - So the arrangement in those steps would send `developer`'s password, and then a wrong one, **as
    `ocp-oauth-bind-serviceid`**. Measured on the deployed code: 2 such authorizes, or 3 after a restart ("The
    finding", below).
- **The walk changed nothing on the lab.** Every command was a read, apart from one server-side dry run, which
  persists nothing:
  - The invariants at the end equal the start (the table below).
  - The oauth-server's audit log records **0** authorizes for the fleet account and 0 for `developer` from the walk's
    start to its end.
  - No walk object exists (`evidence/end-walk-objects.txt`: 0).
- **After the end snapshot, Argo's auto-sync was found paused by another actor, and was left as found**
  (`evidence/after-argo-application.txt`):
  - At 13:30:43Z the Application's `spec.syncPolicy` no longer carried `automated`; at 13:20:51Z it did.
  - It stayed `Synced`/`Healthy` at `22a485c`.
  - This walk wrote nothing to the Application, and no release-crc.sh, argocd-wait, helm or podman process ran on
    this workstation at 13:31:31Z.
  - A pause someone else made is theirs to end: re-enabling `selfHeal` under a deliberate pause would undo their
    work.
  - **Identified afterwards:** the pause was the orchestrator's, for #431's release (application 1.1.0). It was
    lifted by that release's `release-crc.sh --argocd main`, which re-applies the Application with `automated`.

## Definition of Done, lab items

NOT RUN means the walk did not perform the step, and says why. It is not a FAIL: nothing the product did failed.

| Issue | Definition of Done lab item | Result | Evidence |
|---|---|---|---|
| #383 | "On the lab, #285's walk step 3 (as `developer`) counts one authorize on the oauth-server across three cadences." | **NOT RUN.** Unsafe on this lab as specified: the finding. Hermetic stand-in: R2 counts 1 authorize across two processes, three targets, a restart and an edit, for a 401 and for a 500. | `evidence/hermetic-password-scope.txt`, `evidence/hermetic-substitutes.txt` |
| #383 | The fleet account still holds 2 `OAuthAccessToken`s at the end of the epic. | **PASS.** 2 at the start, 2 at the end, created 2026-09-19T00:48:44Z and 00:50:11Z. | `evidence/start-oauth-tokens.txt`, `evidence/end-oauth-tokens.txt` |
| #383 | "Deployed to CRC through `release-crc.sh --argocd`, walked, PVC UIDs unchanged." | **Deployed: PASS**, by Argo at main with the 1.0.0 image. **Walked: NOT RUN**, except the read-only rows here. **PVCs: PASS**, same UIDs at the start and the end. | `evidence/start-argo-application.txt`, `evidence/start-pvcs.txt`, `evidence/end-pvcs.txt` |
| #285 | Walked per SPEC_S4c §3.12, as `developer` only. | **NOT RUN.** Steps 2–3 are unsafe as written (the finding). Steps 4–5 were prepared but need the password. Step 6: see "What could not be done". Step 7's counts: rows below. | this README; `prepared/` |
| #285 | "Step 3, the deliberately wrong password, counts exactly one authorize across three cadences." | **NOT RUN.** As specified it would send the wrong password to the fleet account. Hermetic stand-ins: R4 (a gated account is not pinged, and is said once) and R2. | `evidence/hermetic-password-scope.txt`, `evidence/hermetic-substitutes.txt` |
| #285 | "The `developer` `OAuthAccessToken` count ends where it started." | **PASS, but no `developer` login was made.** 3 at the start (created 2026-09-23T07:34:50Z, 2026-09-26T04:25:57Z, 2026-09-26T14:35:41Z) and the same 3 at the end. | `evidence/start-oauth-tokens.txt`, `evidence/end-oauth-tokens.txt` |
| #285 | "…and the fleet account's count is still 2." | **PASS.** | same |
| #285 | "The Secret `gsd-cluster-shared-rnd`'s `resourceVersion` is unchanged across a ping." | **PASS**, across the product's own ping of the fleet account at 10:27:05Z. `2835139` is the value SPEC_S4c's notes recorded on 2026-09-26. It is also the value measured after the ping, at 12:50:05Z and 13:20:50Z. The Lease's `ping-last-ok` is `2026-09-27T10:27:05Z`. | `evidence/start-shared-rnd-secret.txt`, `evidence/end-shared-rnd-secret.txt`, `evidence/start-leases.txt` |
| #285 | "PVC UIDs are recorded before and after and unchanged." | **PASS.** | `evidence/start-pvcs.txt`, `evidence/end-pvcs.txt` |
| #285 | "Screenshots of the tab's two rows." | **NOT DONE.** `developer` cannot open the Cluster Configurations tab, which needs the cluster-admin tier, and the brief allows no other login. The fleet-account row's data is captured from `/api/clusterconfigs` instead. No self-login cluster exists, so there is no expiry row. | `evidence/pre-api.txt`, `evidence/end-api.txt` |
| #291 | "The live proof is re-run as `developer` … count before, during and after = n, n+1, n." | **NOT RUN**: no password. The hermetic run skips it by design ("1 skipped"). | `evidence/hermetic-fleet-suites.txt` |
| #291 | "Deployed to CRC and walked." | **PARTIAL.** The release commit `05e32c8394` contains #291's merge (PR #411, `cbe828b`), and #285's (PR #419, `602a1c4`) and #315's (PR #416, `ed3edda`): `git merge-base --is-ancestor`. The module's one use on the lab is the product's ping login at 10:27:06Z: `fleet-login`, then `fleet-logout … outcome=revoked`, with the fleet account's count at 2 before and after. That is the product's own login, not a walk step. | `evidence/315-pre-walk-pod-log.txt` |
| #315 | "Deployed to CRC and walked: `shared-rnd` keeps polling and no `fleet-login` line appears." | **PASS.** Over the pod's life, 10:21:54Z to 13:20:53Z: 179 `shared-rnd poll cycle` lines, and exactly one `fleet-login` line naming `shared-rnd`, the daily ping's own at 10:27:06Z. `shared-rnd` reads `"status": "ok"`, and `gsd_cluster_up{cluster="shared-rnd"}` is 1.0. | `evidence/end-podlog.txt`, `evidence/end-api.txt`, `evidence/end-metrics.txt` |
| #286 | "The counts table re-measured." | **PASS.** Table below. | `evidence/start-oauth-tokens.txt`, `evidence/end-oauth-tokens.txt` |
| #286 | "…the ping's account's challenging-client count unchanged across ≥ 3 cadences." | **PARTIAL.** The lab's ping account is the fleet account. One daily cadence has run since the deploy, at 10:27:05Z, and its count was 2 before it and 2 after it: 1 cadence, not 3. The low-interval `developer` ping is unsafe on this lab (the finding). | `evidence/start-leases.txt`, `evidence/end-oauth-tokens.txt` |
| #286 | "The fleet account `ocp-oauth-bind-serviceid` is still at 2." | **PASS.** | `evidence/end-oauth-tokens.txt` |
| #310 | "Part A: a renewal observed …" | **NOT RUN**: no password. The lifetime was never lowered. | `evidence/start-oauth-lifetime.txt` |
| #310 | "`accessTokenMaxAgeSeconds` is restored to `31536000`. The lab is left as found: entries, Secrets, and PVC UIDs recorded before and after." | **PASS** as "left as found": `{"accessTokenMaxAgeSeconds":31536000}` at the start and the end, never patched. Entries, Secrets and PVC UIDs were recorded at both ends. | `evidence/start-oauth-lifetime.txt`, `evidence/end-oauth-lifetime.txt`, `evidence/start-cluster-secrets.txt`, `evidence/end-cluster-secrets.txt` |

## The measured numbers

| Invariant | Start (12:50Z) | End (13:20Z) |
|---|---|---|
| The fleet account's `OAuthAccessToken`s (all are `openshift-challenging-client`) | 2 | 2 |
| `developer`'s `openshift-challenging-client` tokens | 3 | 3 |
| PVC `group-sync-dashboard-data` | `f065b7a4-535c-4ef1-868c-58f5afee4953` | same |
| PVC `group-sync-dashboard-report-artifacts` | `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` | same |
| `gsd-cluster-shared-rnd` `resourceVersion` | 2835139 | 2835139 |
| `oauths.config.openshift.io/cluster` `spec.tokenConfig` | `{"accessTokenMaxAgeSeconds":31536000}` | same |
| Argo `spec.syncPolicy` | `automated {prune, selfHeal}`, retry 3 (30 s × 2, 5 m max), `CreateNamespace`, `RespectIgnoreDifferences`, `ServerSideApply` | same at 13:20:51Z; `Synced`/`Healthy` at `22a485c`. By 13:30:43Z `automated` had been removed by another actor (above) |
| `/api/version`, through the pod's loopback | `1.0.0`, `05e32c8394`, `"leader":true` | same |
| The ServiceAccount's `get` on `openshift-config/ldap-oauth-bind-secret` (`oc auth can-i`; start = the 13:08Z `pre` capture) | yes | yes |
| Audit-log authorizes for the fleet account and `developer` | since 00:00Z (the 13:06Z `pre` capture): 1 `allow` for the fleet account at 10:27:06Z (the product's ping), 0 for `developer` | since 12:43:00Z: 0 and 0 |

#286's counts table, from the same two captures. The 2026-09-26 column is the issue's.

| `OAuthAccessToken` objects | 2026-09-26 (#286) | start | end |
|---|---|---|---|
| all objects | 189 | 189 | 189 |
| the dashboard's oauth-proxy (`system:serviceaccount:group-sync-dashboard:group-sync-dashboard`) | 131 | 131 | 131 |
| `openshift-challenging-client` | 30 | 30 | 30 |
| `console` | 16 | 16 | 16 |
| grafana's ServiceAccount client | 10 | 10 | 10 |
| Argo CD dex | 2 | 2 | 2 |
| the fleet account | 2 | 2 | 2 |

The product's daily ping of the fleet account ran once in this pod's life:
- the Lease `gsd-fleet-666f1ba7f2fdead0` holds `ping-last-attempt` and `ping-last-ok` `2026-09-27T10:27:05Z`, outcome
  `ok`, target `shared-rnd`;
- `/metrics` reads `gsd_fleet_account_last_ok_timestamp_seconds 1.790504825e+09`, which is 2026-09-27T10:27:05Z;
- the oauth-server audit log records one `allow 302` for the fleet account, at 10:27:06.048Z
  (`evidence/pre-audit.txt`).

The next ping is due 24 h after that attempt, and this walk did not move it (`evidence/end-leases.txt`).

## The finding: §3.12 steps 2–3 would send wrong passwords as the fleet account on this lab

**What the code does:**
- `local-development/gsd/fleetlookup.py#fleet_account` takes the username from the stanza's `ldapConnectionBootstrap`,
  or else from the chart.
- `local-development/gsd/fleetlookup.py#fleet_password` reads **one** Secret, `settings.fleet_password_secret_*`, for
  every account.
- `local-development/gsd/poller.py#Poller._ping_accounts` builds its accounts from every retrieved cluster's
  `lookup_account`. It pings each of them with that one password, and it is due whenever the password's digest
  differs from the Lease's `ping-digest`.
- So `ldapConnectionBootstrap` changes the username, but never the password.
- Filed as #432 under Epic C. It is a product defect as well as a walk hazard: any estate using two accounts with
  different passwords gets a wrong-password bind on each extra account per password change.

**What the lab holds:**
- `gsd-cluster-shared-rnd` carries `groupsync-dashboard.io/lookup-account: ocp-oauth-bind-serviceid`
  (`evidence/start-shared-rnd-secret.txt`).
- The ping is on, with an interval of 86400 (`evidence/start-config-fleet-keys.txt`).

**What §3.12 asks:**
- Step 2: "the password Secret holding developer's password".
- Step 3: "rotate the Secret to a wrong password", then back.

Each change of that Secret makes the fleet account's ping due within one discovery cadence (300 s), with the new
content as its password.

**Measured on the deployed code.** `gsd/` in this tree is byte-identical to `05e32c8394`. The test file is
`reports/2026-09-27_epic-c-walk/hermetic/test_walk_password_scope.py`, a fake target counting authorize requests by
their Basic header, with placeholder accounts. It measures what the fleet account is sent:

- **Steps 2 and 3 in one process: 2 authorizes** — the walk password, then the wrong one. The rotation back is
  held by the in-memory gate.
- **The same with a restart before the rotation back: 3.** The Lease keeps one entry per account, so the restart
  forgets the first pair.
- Setting the chart-level username to `developer` does not change either number. The fleet account is still in use
  through `shared-rnd`'s Secret.

To run it:

    cd local-development && PYTHONPATH=.:tests python -m pytest -p no:cacheprovider -v \
      ../reports/2026-09-27_epic-c-walk/hermetic/test_walk_password_scope.py

**The safe arrangement, for steps 4–5 and #310 Part A.** The second test in the file drives this arrangement:
- the ping off;
- the chart-level username `developer`;
- the password Secret a walk-only Secret;
- one `userSelfLogin` stanza on `developer`;
- `shared-rnd` retrieved by the fleet account, as on the lab.

It runs acquisition, a revoked session's re-authentication, a wrong password's suspension, three sweeps, the rotation
back and a 600 s session's renewal. **Every authorize is `developer`'s, and the fleet account's Lease is never
written**, including when that Lease carries a refusal.

The neighbour measurement changes only the ping flag, to on. The first cadence then presents the walk password as the
fleet account's (`[('fleet-bind-account', 'walk password')]`), and the test fails (2 failed). So the ping flag is the
switch the whole arrangement rests on.

**Beyond the walk. This is not measured separately:** it is the same code path with other account names. Consider an
estate that uses two accounts with different passwords, through `ldapConnectionBootstrap` or two `lookup-account`
values:
- The ping sends the one configured password as every account's.
- The directory sees one failed bind per other account per password change, before the Lease gates it.
- `docs/CLUSTER_STANZA.md#ldapConnectionBootstrap` describes the key as "the username that performs the login". It
  does not say the password is shared.

**Options.** None of these is implemented here; each is the orchestrator's decision:
- **Walk:** run steps 2–3 in a release or lab where no retrieved Secret records the fleet account.
- **Product:** a password Secret per account beside `ldapConnectionBootstrap`.
- **Product:** or ping only the accounts whose password the configured Secret holds.

## What could not be done, and why

- **#291's live test, #285 steps 4–5 and #310 Part A.** Each logs in as `developer`, and the password was not
  provided (above). Everything they need is prepared under `prepared/` and was checked:
  - the values file parses and differs from `environments/crc.yaml` only in `clusters` and
    `clusterConfig.fleetAccount.{username, passwordSecret, ping.enabled}`;
  - the RBAC manifest passed `oc apply --dry-run=server`;
  - the CA bundle the live test needs verified TLS to both `api.crc.testing:6443` and
    `oauth-openshift.apps-crc.testing`.
- **#285 steps 2–3, and #286's "`developer` flat across three ping cadences".** Unsafe on this lab as written (the
  finding). The hermetic R3 and R4 cover the ping's own behaviour: 20 clusters make 1 ping per cadence, and a gated
  account is not pinged and is said once.
- **#285 step 6, a second copy of the app out of cluster: not safely possible.** Two reasons:
  - Its discovery would see `shared-rnd`'s retrieved Secret, so the fleet account would be in use and pingable from a
    workstation process, with whatever password that process was configured with.
  - It needs the pod's ServiceAccount token copied out of the cluster.

  The stand-in is hermetic, labelled as such: R1 (two processes cannot both win one claim, and no claim is no bind)
  and R2 (1 authorize across two processes and three targets), both passing (`evidence/hermetic-substitutes.txt`).
- **Screenshots.** `developer` has no access to the tab, and no self-login row exists. `/api/clusterconfigs` is
  captured instead.
- **`release-crc.sh --argocd main` was not run.** Argo was never paused or changed, so there was nothing to restore.
  Running it would only re-apply an identical Application.

## Every write this walk made on the lab

None. The commands run were:
- `oc get` on Secrets, Leases, PVCs, OAuthAccessTokens, the Application, the Deployment, the ConfigMap, RBAC objects
  and the OAuth CR;
- `oc logs`;
- `oc adm node-logs --path=oauth-server/audit.log`, of which only derived counts are kept;
- `oc auth can-i`;
- `oc exec … urlopen` GETs of `/api/version` and `/metrics` on the pod's loopback;
- a GET of `/api/clusterconfigs` through the route, with the kubeconfig's existing kubeadmin session;
- unauthenticated GETs of `/version`, the OAuth discovery document and the OAuth route's `/healthz`;
- `oc apply --dry-run=server -f prepared/walk-rbac.yaml`, which persists nothing.

Proof: `evidence/end-walk-objects.txt` finds 0 objects with the walk's label and no walk Secret. The oauth-server's
audit log has no authorize for either account from 12:43:00Z to 13:20:55Z (`evidence/end-audit.txt`).

## How to resume: the prepared walk, in order

Once `~/.config/gsd/walk.env` exists, every command that needs the password starts with `. ~/.config/gsd/walk.env &&`.
Commit this folder first: `release-crc.sh` refuses a tree with anything untracked except its `--values` file.

1. **Baseline:**
   `reports/2026-09-27_epic-c-walk/scripts/snapshot.sh <label>`, then
   `reports/2026-09-27_epic-c-walk/scripts/capture.sh audit <label> <the start instant>`.
2. **#291** (about 3 min, including the token cache's 121 s):
   `GSD_LIVE_LOGIN_API=https://api.crc.testing:6443 GSD_LIVE_LOGIN_USER=developer
   GSD_LIVE_LOGIN_PASSWORD="$GSD_WALK_DEVELOPER_PASSWORD" GSD_LIVE_LOGIN_CA=<a temp file of
   openshift-config/enterprise-and-cluster-ca-bundle> KUBECONFIG=<the lab's> pytest -v -s
   tests/test_live_fleet_login.py`. It asserts n, n+1, n itself. Redact `token_name=` before keeping the output.
3. **The walk's grants and Secret:**
   - `oc apply -f reports/2026-09-27_epic-c-walk/prepared/walk-rbac.yaml`.
   - Create `gsd-walk-developer-password` in `group-sync-dashboard` from the variable, with `oc create secret
     generic … --dry-run=client -o yaml`, labelled `walk.gsd.lab/run=epic-c-2026-09-27`.
   - For a rotation, use `oc replace`, never `oc apply`: apply would copy the value into the last-applied annotation.
4. **Pause Argo:** record `.spec.syncPolicy`, remove `automated` with `oc patch`, then run `release-crc.sh --values
   reports/2026-09-27_epic-c-walk/prepared/walk-values-selflogin.yaml`. Its Helm mode deletes the Application
   (`local-development/release-crc.sh#Helm mode deletes the Argo Application first`). The PVCs carry `keep` and
   `Delete=false`, as measured.
5. **Steps 4, 5a and 5b**, capturing each with `scripts/capture.sh`:
   - 5a: delete the session's own token, then expect a 401, one re-login and no refusal.
   - 5b: set a wrong password in the walk Secret and delete the token, then expect one `deny` for `developer` and
     `fleet-credential-suspended … stopped=1`.
   - Add a pod restart while the account is gated: a lab proof that the gate survives a restart.
   - Hold for three discovery cadences, then rotate back.
6. **#310 Part A:**
   - Patch `accessTokenMaxAgeSeconds` to 600 and wait for the oauth-openshift pods.
   - Deploy `prepared/walk-values-310a.yaml`, a new entry `walk-renewal`.
   - Observe two renewals, at about 450 s each.
   - Restore `31536000` and wait for the pods again.
7. **End:**
   - `release-crc.sh --argocd main`.
   - Delete the walk Secret and `prepared/walk-rbac.yaml`'s objects, after `can-i` shows the chart's grant is back.
   - Delete the Lease `developer` got, `gsd-fleet-88fa0d759f845b47`.
   - Take the end snapshot, and the audit counts since the start: the fleet account must read 0.

## Files

- `evidence/`: every capture, named `<when>-<what>.txt`, with its command and instant as the header.
  - `start-*` (12:50Z) and `end-*` (13:20Z) come from `scripts/snapshot.sh`.
  - `pre-*` (13:06–13:08Z) and the matching `end-*` come from `scripts/capture.sh`.
  - `hermetic-*.txt` are the three test runs.
  - `rbac-diff-walk-selflogin.txt` is the rendered RBAC diff of the walk values against the Argo shape: REMOVED 1,
    the fleet-account Role's `get` on `ldap-oauth-bind-secret`, which `prepared/walk-rbac.yaml` keeps; ADDED 1.
- `hermetic/test_walk_password_scope.py`: the finding's measurement.
- `scripts/snapshot.sh`, `scripts/capture.sh` and `scripts/rbac_rules.py`: all read-only. Temporary files are
  `mktemp` files, removed on exit. The raw audit log, which holds every user's name, is never kept.
- `prepared/`: the walk values for steps 4–5 and for #310 Part A, the two temporary grants, and the Argo
  `valuesObject` used to render the Argo shape. **None was applied.**
