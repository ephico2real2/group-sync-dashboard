# #310 Part A — a `userSelfLogin` session renewing on the CRC lab, as `developer`, application 2.0.0 (prepared 2026-09-30)

**Status: PREPARED, NOT RUN.** This folder is phase 1 of 2. It holds the plan, the walk's values and grants, the
scripts phase 2 will run, the offline proofs, and the lab's state as found, read with `oc get` only. Nothing in this
folder has written to the cluster. Phase 2 runs `scripts/run.sh` once the orchestrator has checked this plan.

## What the walk proves

Issue #310's Definition of Done, Part A:

- a renewal **observed**: the margin fires, the new session is entered before the old one exits, and polling continues
  across the boundary, all captured with timestamps, on a lab entry that is not `shared-qa`;
- `accessTokenMaxAgeSeconds` restored to `31536000`, and the lab left as found: entries, Secrets, and PVC UIDs
  recorded before and after.

The lab cannot fire a renewal as it stands. `oauth/cluster` states a one-year session lifetime, so `renew_at` is 364 days
22 hours after a login (SPEC_S4c §2.3; `evidence/phase1-as-found-baseline.txt`: `{"accessTokenMaxAgeSeconds":31536000}`).
The walk lowers it to 600 s for the observation and puts it back. The operator gave the go-ahead for that cluster-wide
change on 2026-09-30.

## Scope: the walk proves the ¼ branch of the margin; the 2 h branch is proven hermetically

The margin is one line of code, `local-development/gsd/selflogin.py#renew_at`, lines 56 and 69–71 at `708e6be1`
(`git show 708e6be1:local-development/gsd/selflogin.py | nl -ba`):

```text
    56	MARGIN = timedelta(hours=2)
    69	def renew_at(session: FleetSession) -> datetime:
    70	    """`expires_at − min(2 h, ¼ × expires_in)` (SPEC_S4 §3.1): a fixed margin, a retry budget, not a fraction."""
    71	    return session.expires_at - min(MARGIN, timedelta(seconds=session.expires_in / 4))
```

`min()` has two branches, and the lifetime decides which one applies. Computed by that function, with an injected
`obtained_at` (`evidence/offline-timing.txt`):

| `accessTokenMaxAgeSeconds` | where | margin | renews after login | branch |
|---|---|---|---|---|
| 31 536 000 (365 d) | CRC as found: crc-org/snc `oauth_cr.yaml` lines 7–8 at `b30cd1f`, `# token max age set to 365 days` / `accessTokenMaxAgeSeconds: 31536000` | 7 200 s | 31 528 800 s (364 d 22 h) | 2 h cap |
| 86 400 (24 h) | OpenShift's documented default (SPEC_S4 §3.1's reading of the OpenShift docs; not re-fetched here) — **the production path** | 7 200 s (¼ would be 6 h) | 79 200 s (22 h) | 2 h cap |
| 28 800 (8 h) | where the branches meet | 7 200 s | 21 600 s | both |
| 3 600 (1 h) | an estate that tightens it | 900 s | 2 700 s | ¼ |
| **600** | **this walk** | **150 s** | **450 s** | **¼** |

So, stated plainly:

- **The lab walk observes a real renewal end to end on the ¼ branch.** That covers the login, `renew_at`, the renewal
  firing on the poll cycle, the new session before the old one's revoke, and polling across the boundary. It uses
  the target's own `expires_in` (600) on the wire.
- **The 2 h branch, which covers any lifetime of 8 h or more and so the production default, is proven only by the
  hermetic injected-clock tests.** The branch difference lives entirely in the `min()` on line 71. The firing path
  (`SelfLoginSessions.credential_for`: `now < held.renew_at`) and the renewal order (`_acquire`) are the same code
  whichever branch computed `renew_at`. The tests, run in phase 1 (`evidence/offline-hermetic.txt`):
  - `tests/test_fleet_lifecycle.py::test_r5_renewal_is_a_fixed_margin_before_expiry[86400-79200]` PASSED;
  - `[31536000-31528800]` PASSED;
  - `[3600-2700]` PASSED, which is the ¼ branch;
  - `test_r6_renewal_answers_the_new_login_before_the_old_token_is_revoked` PASSED, the renewal order, on a 3600 s
    session: the ¼ branch.

  No hermetic test fires a renewal end to end on a ≥ 8 h session. R5 proves the computed instant, and R6 proves the
  firing and the order on the ¼ branch. The 2 h cap's computed instant was also seen live on 2026-09-27. There,
  `self-login-renewed … renew_at=2027-09-27T20:33:28Z` is 2 h before `expires_at=2027-09-27T22:33:28Z`
  (`reports/2026-09-27_epic-c-walk-432/evidence/step4-5-pod-podlog.txt`). That renewal was a re-authentication
  (`reauth=true`), not a scheduled one.
- **The restore target is `31536000`, the lab as found. It is not `86400`.** The walk leaves CRC where it was, even
  though real clusters default to 86400.

## The plan in brief

Phase 2 is one script, `scripts/run.sh`, run in the background with one waiter on its exit. In order:

| # | Step | Writes | Guard |
|---|---|---|---|
| 0 | Preflight, all reads: `kubeadmin`, podman up, `oauth/cluster` reads `31536000`, no run-labelled object, no `developer` Lease, GitHub's `main` is `708e6be1`. Clone `708e6be1` into the scratch directory for `release-crc.sh`. Start baseline. | none | aborts before the trap on any mismatch |
| — | **The EXIT trap is set** (`scripts/sweep.sh`) | — | runs on every exit before the hand-back ends |
| 1 | The walk's two grants, `prepared/walk-rbac.yaml`, with `oc create` after a server dry run | 3 RBAC objects | REMOVED 0 (below) |
| 2 | `release-crc.sh --values <the walk values>` from the clean clone, in Helm mode | builds `2.0.0-708e6be104` and deletes the Argo CD Application | exit 0 or abort |
| 3 | Follow the new pod's log (one `oc logs -f`) and sample `/metrics` every 15 s, into the scratch directory | none | the pod must take the leader Lease in 180 s |
| 4 | Lab check, then `oauth/cluster` to 600 by a JSON merge patch of that one field; wait for the rollout and the operator | `oauth/cluster` | lab check `0 0 0`; settled in 900 s |
| 5 | Lab check again, then create the walk Secret with `developer`'s password | 1 Secret | lab check `0 0 0` |
| 6 | Observe: the first login (lifetime must read 600 s ± 10 s), two scheduled renewals, then two more poll cycles | none | aborts on a refusal, a suspension, a failed poll or a timeout |
| 7 | Hand back: delete the walk Secret, restore `31536000` and wait, `release-crc.sh --argocd main`, sweep | the reverse of 1–5 | the sweep never drops a ServiceAccount permission |
| 8 | Evidence: the derived audit rows, the end baseline, the start/end comparison | none | — |

## Order: three places where this plan differs from the brief

The brief ordered the steps: grants and Secret, then the `oauth/cluster` patch, then the deploy. At the end it ran
`--argocd main` and then the trap's restore. This plan changes three things, each for a measured reason. The
orchestrator decides.

1. **The walk Secret comes after the deploy, not before it.** SPEC_S4c §3.12 step 2 (corrected by SPEC_S4e §5) says
   the lab check must print `0 0 0` before the walk Secret exists. On the lab as found it prints `1 0 0`, because the
   Argo CD configuration names the fleet account
   (`evidence/phase1-as-found-informational-labcheck.txt`, 16:25:08Z). It reaches `0 0 0` only once the walk values are
   deployed. The 2026-09-27 walk used the same order (`reports/2026-09-27_epic-c-walk-432/README.md`, "The lab check,
   every run").
2. **The deploy comes before the `oauth/cluster` patch.** Nothing logs in until the Secret exists. So patching after
   the deploy proves the same thing, and it keeps the image build and the Helm handover out of the window in which
   every new OAuth token on the cluster lives 600 s. No `2.0.0-*` image is in the internal registry today, so
   `release-crc.sh` will build both images (`evidence/phase1-risk-reads.txt`: 0 of 197 image stream tags match
   `:2.0.0-`).
3. **`oauth/cluster` is restored before `--argocd main`, not after it.** The restored Argo CD pod pings the fleet account
   on its first discovery cadence when the ping is due. The fleet account's Lease records the last ping at
   `2026-09-29T17:57:32Z`, and the interval is 86400 s (`evidence/phase1-as-found-baseline.txt`). So from 17:57:32Z
   today, the ping is due the moment an Argo CD pod starts. Restoring first means that login meets a settled
   oauth-openshift, and gets a normal one-year session that its own logout then revokes. Restoring after would send the
   fleet account's password to an OAuth server that may be mid-rollout. The walk pod names no fleet account
   (`evidence/offline-render.txt`: 0), so the restore's rollout meets only `developer`. By then the walk Secret is gone,
   so no password is presented at all.

## The walk values, rebased on today's `environments/crc.yaml`

`prepared/walk-values-selflogin.yaml` is `environments/crc.yaml` at `708e6be1`, with its comments kept, except for two
fenced blocks and one comment. `environments/crc.yaml` has not changed since the 2026-09-27 file was prepared:
`git diff --stat 6a83e3e 708e6be1 -- environments/ gitops/` prints nothing. The chart moved from 0.59.6 to 0.59.25
in that time. It added three `trustedCA` keys to the ConfigMap (#244), and the walk does not set them. Parsed with
`yq`, the file equals `environments/crc.yaml` once `.clusters` and `.clusterConfig.fleetAccount` are removed from both
(`evidence/offline-values.txt`, PASS).

The line diff, explained (`evidence/offline-values.txt` holds the whole diff; there, the fleet account's username is
shown as `<the fleet account>`):

| Lines (diff) | What changed | Why |
|---|---|---|
| `0a1,19` | a header | says what the file is, what it deploys, and that it names no fleet account |
| `116a136`, `147,157c152` | `# WALK 1 of 2` … `# END WALK 1` around `clusters` | the fence |
| `118,121d137` | crc.yaml's "HELM REPLACES LISTS" comment removed | it sat inside the replaced list; the `dashboard` stanza it explains is kept as is |
| `128,131c144,147` | the `shared-rnd` stanza's first comment and name → the `walk-self-login` comment and name | the Argo CD Application's `valuesObject` declares `dashboard` alone (`gitops/argocd-application-dashboard.yaml`), so `shared-rnd` and `mock` are not values stanzas on the lab: `shared-rnd` is discovered from its Secret, and the mock clusters come from their own Secrets. The walk renders what Argo renders, plus one stanza |
| `133,145c149,150` | `saTokenLookup: true` and its comments → `userSelfLogin: true`, `ldapConnectionBootstrap: developer` | the one walk stanza: a self-login session as `developer` against `https://api.crc.testing:6443` |
| `147,157c152` | the `mock` stanza removed | as above: not a values stanza under Argo CD |
| `169,172c164,166` | crc.yaml's comment above `fleetAccount` → the `# WALK 2 of 2` fence comment | that comment names the fleet account; the walk values must name it nowhere (SPEC_S4c §3.12 step 0) |
| `174c168` | `username:` → `developer` | the password is presented only as an account the configuration names (SPEC_S4e §3.1). If the chart's username stayed the fleet account, the configuration would name it (lab check `1`), and the one password Secret — now holding `developer`'s password — would be the fleet account's |
| `176,178c170,173` | `passwordSecret` → `group-sync-dashboard/gsd-walk-developer-password`, key `password`, then `# END WALK 2` | `developer`'s password, in a walk-only Secret; `ldap-oauth-bind-secret` is never touched |

The render: `fleetAccountUsername: "developer"`, one `ldapConnectionBootstrap: developer`, one `userSelfLogin: true`,
no `saTokenLookup: true`, `pollIntervalSeconds: 60`, `fleetPingEnabled: true`, `fleetPingIntervalSeconds: 86400`. The
fleet account's username appears 0 times in the walk values file, in the rendered `clusters.yaml`, and in the whole
render. It appears once in the Argo CD shape's `clusters.yaml`, so the check can tell the two apart
(`evidence/offline-render.txt`). The username is read from `environments/crc.yaml` into a variable and never printed.

### The ping: on (the chart default), and it cannot bind

The walk values do not write a `ping` block, so the chart default stands: on, daily. That is the simplest
arrangement, and it is the one SPEC_S4e's hermetic test proves: "with the ping on". It presents nothing, for two
reasons read in `local-development/gsd/poller.py#Poller._ping_accounts`:

- the ping reads a password only against a *target*, and a target is a cluster the lookup retrieved as that account
  (`c.token_source == CREDENTIAL_LOOKUP and c.lookup_account`). `developer` has none: the walk has no `saTokenLookup`
  stanza, and `gsd-cluster-walk-lookup` was deleted on 2026-09-27. The cluster Secrets as found are the four mock
  Secrets, `shared-qa` and `shared-rnd` (`evidence/phase1-as-found-baseline.txt`). So `ping = leader and target is not
  None and …` is False;
- the fleet account, which `gsd-cluster-shared-rnd` records, is not a *declared* account under the walk values, so its
  Lease is read and served as history (`if account not in declared: continue`), and no password is read for it.

Turning the ping off would add a line to the values and change nothing on the wire. The orchestrator may prefer it
as belt and braces; it is listed under "Open questions".

## The grants: REMOVED 0

`prepared/walk-rbac.yaml` holds the two of the 2026-09-27 walk's three grants that a self-login-only walk needs,
relabelled `walk.gsd.lab/run=selflogin-310-2026-09-30`:

1. **the keep-grant**: a Role and RoleBinding in `openshift-config` that keep the dashboard ServiceAccount's `get` on
   `ldap-oauth-bind-secret`. The walk values move the chart's fleet-account grant to the walk Secret, and without this
   grant the walk would remove that one permission;
2. `developer` bound to the existing `group-sync-dashboard-cluster-poller` ClusterRole. A self-login cluster polls as
   `developer`'s own session.

The third 2026-09-27 grant, `developer` on the token-reader Role, served the lookup, and this walk looks nothing up.

Rendered with `helm template` (v4.3.0) and expanded per subject by
`reports/2026-09-27_epic-c-walk-432/scripts/rbac_grants.py`, the Argo CD shape compared with the walk
(`evidence/offline-rbac-diff.txt`; renders of 3318 and 3323 lines, and the grants file of 62 lines):

```text
without the walk grants: grants 66 -> 66, REMOVED 1
  - ServiceAccount:group-sync-dashboard:group-sync-dashboard | openshift-config | secrets | get | ldap-oauth-bind-secret
with prepared/walk-rbac.yaml:  grants 66 -> 68, REMOVED 0, REMOVED for the dashboard ServiceAccount: 0
  + ServiceAccount:group-sync-dashboard:group-sync-dashboard | group-sync-dashboard | secrets | get | gsd-walk-developer-password
  + User::developer | (cluster) | roleRef ClusterRole/group-sync-dashboard-cluster-poller
```

The keep-grant is removed only after `--argocd main`. `scripts/sweep.sh` first reads the chart's own
`group-sync-dashboard-fleet-account` Role and its binding in `openshift-config`. They must grant the ServiceAccount
`get` on `ldap-oauth-bind-secret`; until they do, the keep-grant stays, and the sweep says so.

## What the product writes, and the lines phase 2 waits for

The rule, from `local-development/gsd/selflogin.py#renew_at`:

```text
def renew_at(session: FleetSession) -> datetime:
    """`expires_at − min(2 h, ¼ × expires_in)` (SPEC_S4 §3.1): a fixed margin, a retry budget, not a fraction."""
    return session.expires_at - min(MARGIN, timedelta(seconds=session.expires_in / 4))
```

It is checked at the top of each poll cycle, before the poll, in
`local-development/gsd/selflogin.py#SelfLoginSessions.credential_for`:
`if held is not None and now < held.renew_at and not held.reauth: return self._as(cluster, held)`. At or after
`renew_at` the cycle logs in again (`_acquire`). A renewal then does this, in order
(`local-development/gsd/selflogin.py#SelfLoginSessions._acquire`):

```text
acquired = login, login.__enter__()          # the NEW session: FleetLogin writes `fleet-login … expires_at=<new>`
...
if old is not None:
    self._exit(old.login)                    # the OLD session revoked: `fleet-logout … outcome=revoked`
    event(log, logging.INFO, "self-login-renewed", cluster=cluster.name, account=account,
          expires_at=session.expires_at_iso, renew_at=stamp(fresh.renew_at), ...)
```

The event names, as `local-development/gsd/fleetlogin.py#FleetLogin` and `local-development/gsd/selflogin.py` spell
them: `fleet-login`, `fleet-logout`, `self-login-renewed`. The failures phase 2 aborts on are `fleet-login-refused`,
`fleet-login-failed`, `fleet-credential-suspended`, `self-login-failed`, and `cluster-unreachable` for the walk
cluster. The first login writes `fleet-login` only; `self-login-renewed` is written on renewals. Their shapes, as the
2026-09-27 walk captured them (`reports/2026-09-27_epic-c-walk-432/evidence/step4-5-pod-podlog.txt`):

```text
<instant> … INFO    gsd.fleetlogin fleet-login cluster=walk-self-login account=<redacted> tls=trusted-bundle oauth=https://oauth-openshift.apps-crc.testing expires_at=2027-09-27T22:29:29Z
<instant> … INFO    gsd.selflogin self-login-renewed cluster=walk-self-login account=<redacted> expires_at=2027-09-27T22:33:28Z renew_at=2027-09-27T20:33:28Z reauth=true
```

`account=<redacted>` is the redactor at work: CRC's `developer` password is the word `developer` (SPEC_S4c §3.12
step 2). The successful poll line is `polled walk-self-login: <n> CRs, <n> groups, …`
(`local-development/gsd/poller.py#poll_once`'s `log.info`), and the gauges are
`gsd_cluster_up{cluster="walk-self-login"}` and `gsd_cluster_last_poll_timestamp_seconds{cluster="walk-self-login"}`.

## Timings

Measured offline against the shipped code (`evidence/offline-timing.txt`):

- a 600 s session: `renew_at = expires_at − 150 s`, because `min(2 h, 600 / 4) = 150 s`;
- the floor: `expires_in` must exceed `4 × pollIntervalSeconds = 240 s` (`local-development/gsd/selflogin.py#SelfLoginSessions._acquire`); 600 > 240;
- on a 60 s cycle, `renew_at` falls 450 s after a login, and the first cycle at or after it is at 480 s. So:
  - renewal 1 comes 480 s after the first login, 30 s after `renew_at` and 120 s before the old session ends;
  - renewal 2 comes at 960 s, and renewal 3 would come at 1440 s.

Phase 2 waits for two renewals: 16 minutes after the first login on this model, with a timeout of `2 × 540 + 300 s`.
It then waits 130 s more, so the evidence shows polls after the last renewal. The first login comes within one cycle of
the Secret (`wait_for`, 240 s bound). The oauth-openshift rollout time, the image build time and the Argo CD sync time
were **not measured** here. Their bounds in the scripts: the rollout must start within 600 s and settle within
900 s (`scripts/oauth_lifetime.sh`), and `argocd-wait.sh` waits at most 900 s.

The model assumes a cycle starts every 60 s (`local-development/gsd/poller.py#Poller._wait_cycle` waits out the
interval minus the cycle's own work). A slow poll moves the renewal later within its 150 s margin; `analyse.py` checks
what the log shows, not the model.

## What phase 2 captures as evidence

All under `evidence/`, each file with its command and instant. `sha256~` token-object names are redacted. No
password or token is captured, and the fleet account is counted, never named.

| File | What |
|---|---|
| `phase2-start-baseline.txt`, `phase2-observed-baseline.txt`, `phase2-end-baseline.txt` | `scripts/baseline.sh`: `oauth/cluster` `.spec.tokenConfig`, and the sha256 of the rest of `.spec`; the challenging client's overrides; the authentication ClusterOperator and the oauth-openshift rollout; the dashboard Deployment, pod and `/api/version`; Argo CD and the report Jobs; PVC UIDs; cluster Secrets by name, resourceVersion and creation time; the fleet Lease's resourceVersion, holder and ping instants, and its sha256; `developer`'s Lease; OAuthAccessToken counts and creation instants for `developer` and the fleet account, and how many carry `expiresIn <= 600`; the `can-i` grants; the run-labelled objects; the cluster gauges |
| `phase2-*-labcheck.txt` | the three lab-check counts, as found (`1 0 0` expected), after the deploy, and before the Secret |
| `phase2-set-600-oauth-lifetime.txt`, `trap-oauth-lifetime.txt` / `handback-*-oauth-lifetime.txt` | each patch, the Deployment generation it moved, every state transition to SETTLED |
| `phase2-deploy-release-crc.log`, `phase2-handback-release-crc-argocd-main.log` | the two `release-crc.sh` runs |
| `phase2-walk-rbac-create.txt`, `phase2-walk-secret.txt` | what was created: names, resourceVersion, uid, never data |
| `phase2-podlog.txt` | every `fleet-login`, `fleet-logout`, `self-login-*` and `fleet-credential-*` line about `walk-self-login`, every `polled walk-self-login:` line, failed polls, ERROR/Traceback, with counts, and how many `fleet-*` lines name the fleet account (a count) |
| `phase2-metrics.txt` | the 15-second `/metrics` samples of the walk cluster's and the host's gauges |
| `phase2-analysis.txt` | `scripts/analyse.py`'s verdict: each session's lifetime is 600 s; the scheduled renewals; for each one, the new login at or after `renew_at` and before the old `expires_at`, then `fleet-login` (new) ≤ `fleet-logout outcome=revoked` (old) ≤ `self-login-renewed`, with `renew_at = expires_at − 150 s` and a poll on both sides within one cycle; the longest gap between polls ≤ 75 s; no failure line; the gauge at 1 and the last-poll stamp advancing by ≤ 75 s |
| `phase2-window-audit.txt`, `phase2-since-secret-audit.txt` | derived oauth-server audit rows: `developer`'s challenging-client authorizes (expected: 1 + the renewals, all allow), the fleet account's count, and the records with no username |
| `phase2-*-sweep.txt`, `phase2-compare.txt` | what the restore did, and the start/end comparison line by line (`scripts/compare_baselines.sh`) |
| `phase2-run.txt` | the whole run's log |

## Risks

- **The oauth-openshift pods restart twice**: once for the patch and once for the restore. During each rollout, logins
  to the console, `oc login`, and Argo CD's and Grafana's OAuth logins may fail briefly. Existing tokens keep their
  expiry. The rollout duration on this CRC was not measured.
- **Every OAuth token minted while the value is 600 lives 600 s**, not just the walk's. That covers `developer`'s and
  anyone else's console sessions, `oc login` tokens, and the oauth-proxy sessions of the dashboard and Grafana. The
  lab's kubeconfig carries a token minted before the window, so its expiry does not change; its creation time was not
  read. Nobody should `oc login` to a kubeconfig the walk depends on during the window. The end baseline counts the
  tokens with `expiresIn <= 600` by client, so what was minted in the window is on record.
- **Helm mode deletes the Argo CD Application with its cascade.** The Application carries
  `resources-finalizer.argocd.argoproj.io`, and no parent Application or ApplicationSet recreates it: no
  ownerReferences, no tracking annotation, no ApplicationSet (`evidence/phase1-risk-reads.txt`). The cascade deletes the report CronJob's Jobs, and with them today's failed run. That Job,
  `group-sync-dashboard-report-nightly-namespace-access-29845560`, started 2026-09-30T02:00:00Z and ended `Failed:
  DeadlineExceeded`, "Job was active longer than specified deadline", at 02:15:01Z. It has no pod or event left. Its
  status is in `evidence/phase1-risk-reads.txt`, recorded and not fixed. That failure is why Argo CD reads
  `Degraded` today. After the handover the CronJob is new, so `--argocd main` may reach `Healthy`, or it may stop at the
  900 s gate: the result is recorded either way.
- **`--argocd main` deploys whatever `main` is on GitHub.** The preflight aborts unless it is `708e6be1`. A merge to
  `main` during the walk would change what the hand-back deploys.
- **PVCs**: both carry `helm.sh/resource-policy: keep`, which keeps them through `helm uninstall` (the hand-back), and
  `argocd.argoproj.io/sync-options: Prune=false,Delete=false,PruneLast=true`, which keeps them through the Application's
  cascade (the deploy; `charts/group-sync-dashboard/templates/pvc.yaml`): data `f065b7a4-535c-4ef1-868c-58f5afee4953`,
  report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, as found. The preflight aborts unless the live objects carry
  both. Nothing in the scripts touches a PVC. The UIDs are compared start to end.
- **The walk cluster stays in the database as a retired row**, `walk-self-login`, and the product keeps its history
  (#96), as the 2026-09-27 walk's did. `developer`'s entry also stays in `fleet-gate.json`, the copy of the fleet Leases
  that #481 keeps beside the database on the data PVC. The restored configuration names no `developer` account, so
  the copy is only ever read back when a later configuration names `developer` again
  (`local-development/gsd/poller.py#Poller._ping_accounts` restores a Lease only for an account in use). The walk
  deletes no database rows.
- **The last `developer` session's end**: the walk Secret is deleted first. The session is then either revoked when
  `--argocd main` stops the walk pod (the poll thread's exit calls `SelfLoginSessions.stop`, then
  `local-development/gsd/api.py#build_app`'s lifespan calls `poller.stop()`), or it expires first. In that case one
  expired OAuthAccessToken object may remain until the API server removes it; that removal was not measured. The end
  comparison shows `developer`'s challenging-client count and creation instants, as a MUST line.
- **The fleet account's daily ping** moves its Lease's resourceVersion whenever an Argo CD pod pings it. That happens
  before the handover if phase 2 starts after 17:57:32Z, and again after the restore. That is the product, not the
  walk. The comparison reports the Lease as INFO, with its `ping-last-attempt`, and requires only an empty holder.
- **The keep-grant and `developer`'s Lease outlive a failed run.** The trap leaves them on purpose until the chart's
  grant is back or the configuration stops naming `developer`. It prints the `--argocd main` command to finish.

## Open questions for the orchestrator

1. **The order** (above): the Secret after the deploy, the patch after the deploy, the restore before `--argocd main`.
2. **The ping**: the chart default (on), which cannot bind here, or an explicit `ping.enabled: false`?
3. **The observation length**: two renewals (16 min on the model) or three (24 min)? `RENEWALS=3` makes it three.
4. **The trap does not run `--argocd main`.** A failed run leaves the lab on the walk's Helm release, with
   `oauth/cluster` restored and the password Secret gone. The trap prints the command only once its sweep restored
   `31536000` and saw the operator settle; otherwise it prints the restore and says not to hand back. Should the trap
   run it itself?
5. **The build**: `release-crc.sh` builds `2.0.0-708e6be104` into the internal registry, because none exists. Per the
   operator's rule the images stay (published images are never deleted).
6. **SPEC_S4c §3.12 step 4 and #310's "ping stays on"**: §3.12 walks self-login "with the ping still on" beside a lookup
   stanza. This walk has no lookup stanza, so "on" is on in name only (above). That is consistent with the spec, not a
   disagreement. Nothing in SPEC_S4c §3.1/§3.6 or SPEC_S4e §5 disagrees with `local-development/gsd/selflogin.py` on the
   margin, the order, or the floor (`evidence/offline-timing.txt`, and `tests/test_fleet_lifecycle.py` R5/R6 passing).

## The offline proofs (phase 1)

`PY=<the repo's venv python> bash scripts/offline_proofs.sh` runs all eight groups. It reads no cluster.

| Proof | Result | Evidence |
|---|---|---|
| the walk values equal `environments/crc.yaml` outside the two blocks (parsed) | PASS | `evidence/offline-values.txt` |
| the fleet account's username in the walk values file, its rendered `clusters.yaml`, its whole render | 0, 0, 0 (the Argo CD shape: 1) | `evidence/offline-render.txt` |
| rendered RBAC, the Argo CD shape → the walk | line counts 3318 / 3323 / 62; REMOVED 1 without the grants, **REMOVED 0** with them | `evidence/offline-rbac-diff.txt` |
| SPEC_S4e's `test_the_self_login_walk_arrangement_with_the_ping_on_presents_nothing_as_the_fleet_account` | **2 passed** | `evidence/offline-hermetic.txt` |
| `tests/test_ping_account_scope.py`, whole | 24 passed | same |
| `tests/test_fleet_lifecycle.py` + `tests/test_fleet_lifecycle_round3.py` | 54 passed | same |
| the 2 h branch, by injected clock: `test_r5_renewal_is_a_fixed_margin_before_expiry` `[3600-2700]`, `[86400-79200]`, `[31536000-31528800]`; the order: `test_r6_renewal_answers_the_new_login_before_the_old_token_is_revoked` | 4 passed, each named PASSED | same |
| the margin by lifetime, and the 600 s schedule, from `renew_at` | 31536000 and 86400: 7200 s (the 2 h cap); 600: 150 s; renewals at +480 s, +960 s, +1440 s | `evidence/offline-timing.txt` |
| `scripts/analyse.py` on synthetic logs in the real lines' shapes | a good run 14 passed / 0 failed; a run with the old session revoked first and one missed poll fails exactly those two checks (12 / 2) | `evidence/offline-analyse.txt` |
| `scripts/sweep.sh` three times against a stub `oc` | 1 patch in three runs; the keep-grant and `developer`'s Lease left in run 1 (exit 5), removed in run 2, nothing in run 3 | `evidence/offline-restore.txt` |
| `scripts/capture.sh` stream-start, then stream-stop, against a stub `oc` | both exit 0; no stream loop left (not yet run: added by the review of phase 1) | `evidence/offline-streams.txt` |

Every script passes `bash -n` and `shellcheck -x`.

## The lab as found (phase 1, `oc get` only, 2026-09-30T16:35Z)

`evidence/phase1-as-found-baseline.txt`, `scripts/baseline.sh phase1-as-found --get-only`. It skips `/api/version`,
which needs `oc exec`, and `oc auth can-i`, which POSTs a review. Phase 1 was held to `oc get`.

- `oauth/cluster`: `{"accessTokenMaxAgeSeconds":31536000}`; `.spec` keys `identityProviders`, `tokenConfig`; the
  challenging client overrides nothing (`null`, `null`).
- The authentication operator: `Available=True Degraded=False Progressing=False`; oauth-openshift at generation 15, 1/1
  ready, its pod started 2026-09-22T15:34:16Z.
- The dashboard: `quay.io/ephico2real/group-sync-dashboard:2.0.0`, chart `group-sync-dashboard-0.59.25`, no Helm
  release record, so Argo CD owns it. Argo CD is `Synced` at `708e6be1046ca302ffbef6ba1f17fe811295462f` and reads
  `Degraded` because of the CronJob (above).
- PVCs: data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, both
  `resource-policy=keep`.
- Cluster Secrets: `gsd-cluster-shared-qa` rv `2981054`, `gsd-cluster-shared-rnd` rv `2835139`, and the four mock
  Secrets.
- The fleet account's Lease `gsd-fleet-666f1ba7f2fdead0`: rv `7043788`, no holder, last ping ok at
  2026-09-29T17:57:32Z, no refusal. `developer`'s Lease `gsd-fleet-88fa0d759f845b47`: not found.
- OAuthAccessTokens: 254 in all. `developer`'s challenging-client tokens: 6. The fleet account's: 2, created
  2026-09-19T00:48:44Z and 00:50:11Z. Tokens with `expiresIn <= 600`: 0.
- No object carries the run label; the walk Secret does not exist.
- The lab check: `1 0 0`, expected on the Argo CD configuration (`evidence/phase1-as-found-informational-labcheck.txt`).
- The risk reads (`evidence/phase1-risk-reads.txt`, 16:41:42Z): 0 of 197 image stream tags match `:2.0.0-`; the
  Application's finalizer, with no owner, tracking annotation or ApplicationSet; the failed nightly Job's two
  conditions, and 0 pods left.

## Files

- `prepared/walk-values-selflogin.yaml`: the walk's values (above).
- `prepared/walk-rbac.yaml`: the two grants.
- `prepared/argo-clusters-override.yaml`: the Application's `valuesObject`, for rendering the Argo CD shape (a copy of
  the 2026-09-27 file).
- `scripts/lib.sh`: shared names and helpers. The fleet account's username is read from its Lease, into a variable.
- `scripts/run.sh`: phase 2, with the trap.
- `scripts/sweep.sh`: the restore, safe to run any number of times.
- `scripts/oauth_lifetime.sh`: the one `oauth/cluster` merge patch, and the wait for the operator.
- `scripts/walk_secret.sh`: the walk Secret. The password reaches `oc` on stdin, never on a command line. That is the
  one change from the 2026-09-27 script, whose `--from-literal` put it in `oc`'s argv.
- `scripts/labcheck.sh`: SPEC_S4e §5's three counts.
- `scripts/baseline.sh`, `scripts/compare_baselines.sh`: the lab's invariants, and their comparison.
- `scripts/capture.sh`: the log follow, the metrics sampler, the derived captures, and the audit rows.
- `scripts/analyse.py`: the verdict, from the committed evidence.
- `scripts/offline_proofs.sh`, `scripts/stub/`: the phase-1 proofs, and the stand-in `oc` and `sleep` they use.

## How to run phase 2

With the plan accepted, from this worktree's copy of the folder:

```sh
WALK_TMP=<a scratch directory outside the repository> \
KUBECONFIG=/Users/olasumbo/.claude/gsd-session-2026-09-28/kc-crc \
  bash reports/2026-09-30_selflogin-renewal-310/scripts/run.sh     # in the background, one waiter on its exit
```

It exits 0 only if all three hold: the analysis passed, the final sweep removed everything, and the start/end
comparison is equal on every MUST line. If it stops early, the trap restores `oauth/cluster` and removes what is safe
to remove. `evidence/phase2-run.txt` then ends with what is left, and the command that finishes it.

The background task needs its own timeout, set to the harness's maximum (`timeout: 7200000`). The run's length was
not measured. Its bounded waits add up to 8 235 s before the image build: `release-crc.sh --values` 1 205 s, the
leader 180 s, the 600 patch 1 500 s, the first login 240 s, the renewals 1 380 s, 130 s, the restore 1 500 s,
`--argocd main` 1 200 s, and the second sweep's settle check 900 s. That is more than the maximum. A stop that sends
SIGTERM or SIGHUP to the process group runs the trap; SIGKILL runs nothing (below).

### If the run is killed

SIGKILL, or any stop that gives the trap no time, leaves whatever the run had reached. `run.sh` prints the restore
before it patches `oauth/cluster`; it is also here. In this order, from this worktree:

```sh
KUBECONFIG=/Users/olasumbo/.claude/gsd-session-2026-09-28/kc-crc bash reports/2026-09-30_selflogin-renewal-310/scripts/sweep.sh manual
# the same first step by hand, if the scripts cannot run:
oc patch oauths.config.openshift.io cluster --type=merge -p '{"spec":{"tokenConfig":{"accessTokenMaxAgeSeconds":31536000}}}'
```

Only once `oc get oauths.config.openshift.io cluster -o jsonpath='{.spec.tokenConfig}'` reads
`{"accessTokenMaxAgeSeconds":31536000}` and the authentication operator reads `Available=True Degraded=False
Progressing=False`, run `release-crc.sh --argocd main` from the deploy clone, then `sweep.sh` once more: the restored
configuration pings the fleet account on its first discovery cadence.
