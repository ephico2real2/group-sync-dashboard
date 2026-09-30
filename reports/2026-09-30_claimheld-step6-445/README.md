# #445 — SPEC_S4c §3.12 step 6 walked on the CRC lab: `ClaimHeld` on `developer`'s Lease, application 2.0.0 (prepared 2026-09-30)

**Status: PREPARED, NOT RUN.** This is phase 1: the plan, the scripts, the offline proofs and a read-only baseline of
the lab. Phase 1 wrote nothing to the cluster; its only cluster commands were `oc get` and `oc whoami`. Phase 2 runs
`scripts/run.sh` once OB3 and Grok have reviewed this plan.

#445's Definition of Done: "§3.12 step 6 rewritten, reviewed by two seats (Grok one), and walked on the lab, with
evidence under `reports/`." PR #461 did the rewrite and its review (merged 2026-09-28). What is still owed is the walk.

## What step 6 proves, and what it does not

SPEC_S4c §3.12 step 6 runs one coordinator inside the dashboard pod, through one `oc exec -i … python3.14 -`. The
coordinator starts two claim-only processes, `walk-step6-a` and `walk-step6-b`. Neither has a `LeaderElector`, and
neither reads a password. A claims `developer`'s Lease and holds it. Then B tries to claim it. Once B is done, A
releases the Lease.

**It proves:** two independent OS processes see the same Lease through the real API server. While A's claim is live,
B's `FleetLease.claim()` raises `ClaimHeld`, and B writes nothing. When A lets go, the holder is cleared. Nothing goes
to the OAuth server while this happens: the 6.4 audit counts 0 authorizes for `developer` and 0 for the fleet
account.

**It does not prove:**

- **The CAS race.** B's `ClaimHeld` comes from the READ path. B's claim reads the Lease, finds a live holder
  (`gsd/fleetstate.py#FleetRecord.in_flight`, lines 194–196), and raises before it writes. In the rehearsal below, B
  sends one GET and no write. The other path is the API server answering 409 when two claims race on one
  resourceVersion: a POST of a name that exists, or a PUT with a stale resourceVersion. The lab walk never exercises
  it. `tests/test_fleet_lifecycle.py::test_r1_two_processes_cannot_both_win_one_claim_and_no_claim_is_no_bind`
  proves both 409s hermetically: `evidence/offline-hermetic.txt`, PASSED.
- **Leadership plus the Lease.** A standby never reaches `claim()`. That was the #444 stop, and PR #461 chose the
  durable Lease on purpose.
- **A bind path under the claim.** A lookup, a ping or a self-login is not exercised. Those are R2/D1 hermetically
  (below), and steps 2–5 on the lab (`reports/2026-09-27_epic-c-walk-432/`).
- **The #481 backstop.** The coordinator's `FleetLease` has no backstop, so the data volume's `fleet-gate.json` is
  neither read nor written.

## Where the merged step 6 does not match the code or the lab today

These are for the orchestrator to settle before phase 2 runs.

1. **The Lease name holds.** `gsd-fleet-88fa0d759f845b47` is `lease_name("developer")`, which is
   `"gsd-fleet-" + sha256(username)[:16]` (`gsd/fleetstate.py:109`). It depends on the username only. The password
   Secret's `metadata.uid` salts the **digest** that a Lease records (`lease_digest(account, password, salt)`, line
   114), never the name. So any walk Secret gives the same Lease name, and so does no Secret at all. Checked against
   the code in `evidence/offline-lease-name.txt` (PASS).
2. **The spec assumes the Lease exists. On today's lab it is absent.** Step 6 is written to follow step 5 ("After
   step 5 …"), and by then the walk's own ping and self-login would have created the Lease. On the lab as found,
   `developer`'s Lease is **absent**: the #310 walk's sweep removed it
   (`evidence/phase1-as-found-baseline.txt`: `developer's Lease gsd-fleet-88fa0d759f845b47: absent`). Two things
   follow:
   - The spec's 6.0 read, `oc get leases.coordination.k8s.io gsd-fleet-88fa0d759f845b47 … -o jsonpath=…`, answers
     NotFound.
   - By the code, an absent Lease is not in flight: `read()` returns an empty record, whose holder is `""`. A's
     `claim()` then creates the Lease with a POST (`gsd/fleetstate.py:340`,
     `self._call("POST" if record.raw is None else "PUT", obj)`).

   `scripts/run.sh` handles this in 6.0. It treats NotFound as free, with the same rule as `in_flight`
   (`scripts/lib.sh#dev_lease_free`). It also runs the spec's own read verbatim and records its output, NotFound
   included. The rehearsal ran both shapes, and both print the expected three lines:
   - `absent`: GET 404, then POST 201;
   - `free`: GET, then PUT.

   **Decide:** accept "absent" as "not in flight", or have phase 2 first create the Lease through a product claim.
   The second option needs a stanza for `developer`, a password, and a real bind; see "The arrangement".
3. **"The ping and self-login have stood down" has nothing to refer to here.** This walk runs step 6 on its own, and
   its configuration gives `developer` no stanza. The running pod never reads or claims `developer`'s Lease at all.
   That is stronger than a stood-down path (see "The arrangement").
4. **The image does have a shell.** The spec says "The image has no shell". `release-crc.sh` checks the build inside
   the pod with `oc exec … -- sh -c 'echo "$GSD_GIT_COMMIT"'`, and on 2026-09-30 that check printed
   `running : 708e6be104 — verified in-pod`
   (`reports/2026-09-30_selflogin-renewal-310/evidence/phase2-deploy-release-crc.log`). This changes nothing: step 6
   runs `python3.14` either way. It is a factual slip in the prose.
5. **When the Lease is already held, the abort prints two lines.** The rehearsal `held` scenario printed
   `ABORT: process A did not hold` and then `ABORT: process A did not release`. The second line is misleading: A
   never held the Lease, and the coordinator's `finally` reports the release regardless. The exit code (2) and the
   absence of writes are correct: 1 GET, 0 POST/PUT. This is cosmetic, and no fix is proposed here.
6. **6.5's "does not import `fleet_password`, `FleetLogin` or `lookup`" is true by name only.** It is true of the
   names: `tests/test_s4c_step6_walk.py::test_step6_script_claims_and_never_reads_a_password` PASSED. But
   `gsd.fleetstate` imports the `gsd.fleetlogin` module (`from .fleetlogin import RETRY_POLICY`,
   `gsd/fleetstate.py:58`), so that module is loaded. It is never *called*: in the rehearsal, the only requests the
   coordinator sends are Lease GET/POST/PUT (`evidence/offline-coordinator.txt`).
7. **These match today's lab:**
   - the fleet account's challenging-client token count is **2** (6.4 expects 2; phase 1 baseline: `2 created
     2026-09-19T00:48:44Z, 2026-09-19T00:50:11Z`);
   - `claim_seconds` is **195**: the deployed `requestTimeoutSeconds: 15`, and the rehearsal's `until` is 195 s after
     the claim;
   - the lab check prints `1 0 0` on the Argo CD configuration
     (`evidence/phase1-as-found-informational-labcheck.txt`), so step 6.0's `0 0 0` needs the walk values deployed.

## The arrangement: what phase 2 deploys, derived from the code

The brief asked for three things:

- `developer` as the chart's fleet username;
- a walk-only password Secret;
- a stanza that gives `developer` a Lease.

From the code, step 6 needs the first. It needs neither the Secret nor the stanza.

- **Why deploy at all.** Step 6.0 aborts unless the lab check prints `0 0 0`. The Argo CD configuration names the
  fleet account (`1 0 0`). So `clusterConfig.fleetAccount.username` must name someone else: `developer`.
- **No stanza.** A's claim creates an absent Lease (item 2 above), so nothing has to create it first. With no stanza
  naming `developer`, the running pod never touches that Lease. The reason is in
  `gsd/poller.py#Poller._ping_accounts`, which reads, restores and claims only the Leases of `members`: accounts with
  a cluster in use (lines 1741–1747, loop at 1756). Under the walk values, `members` holds one account, the fleet
  account's (for `gsd-cluster-shared-rnd`, which the lookup retrieved as it). The fleet account is not declared, so
  the pod only reads its Lease and serves it as history. Nothing is pending a lookup (`_retrieve_pending`, line 1610:
  no cluster's credential kind is `remote-lookup`. Phase 1 read every cluster Secret's declared modes, and none
  declares `saTokenLookup` or `userSelfLogin` (`evidence/phase1-risk-reads.txt`).
  - A stanza would change that. It would put `developer` in `members`, and the leader would then create and claim
    `developer`'s Lease itself. The control test measures exactly this: the Lease is restored by
    `lease.restore(record)` at line 1766. The pod would then race A for the claim.
- **The password Secret is named but never created.** `gsd-walk-developer-password` is the name in the values, and
  the walk never creates it. Step 6 places no password. With the Secret absent, every bind path refuses before the
  wire: `gsd/fleetlookup.py#fleet_password` raises `fleet-credential-missing` on the GET (line 258). There are three
  such paths: the lookup, the ping and self-login, and they are its only callers.
  - This walk never holds or handles `developer`'s password at all. The #310 walk read it from `crc console
    --credentials`.
  - The chart still needs a name, and refuses a blank one (`templates/fleet-account-rbac.yaml`: "passwordSecret.name
    is empty, but a connection mode is in use").
- **The ping stays at the chart default (on).** It has nothing to ping as `developer`: there are no targets.
  `ping.enabled: false` would change nothing on the wire; it is an open question below.

Hermetic proof of this arrangement: `scripts/test_step6_arrangement.py`, on the repository's own harness
(`tests/test_fleet_lifecycle.py#LeaseHost`: one fake API server, CAS enforced, every write counted). Both tests
PASSED:

- `test_step6_the_walk_pod_never_touches_developers_lease_and_the_claim_is_held` — the pod leads for three cadences
  and again while A holds the claim. Across all of them it never reads `developer`'s Lease, never reads the password
  Secret, and sends nothing to the target. On the same fake API, A POSTs the Lease and B raises `ClaimHeld` with the
  exact text the coordinator checks. The only writes to `developer`'s Lease are A's POST and A's release PUT. The
  fleet Lease is unchanged.
- `test_step6_control_a_stanza_naming_developer_makes_the_pod_read_its_lease` — the control. It shows the probe is
  not vacuous.

Two mutations were measured by hand on a copy (in the scratch directory, not committed), and each failed where it
should:

- adding a `developer` retrieved cluster fails with `the pod created developer's Lease`;
- skipping B's claim fails with `DID NOT RAISE ClaimHeld`.

`prepared/walk-values-claimheld.yaml` is `environments/crc.yaml`, verbatim outside two fenced blocks:

- `clusters` is the Argo CD Application's override, `dashboard` alone;
- `fleetAccount` is `developer` plus the never-created walk Secret.

It is derived from #310's reviewed walk values by removing the `walk-self-login` stanza and rewriting the header
(`evidence/offline-values.txt`: equal to `environments/crc.yaml` outside those blocks, parsed with `yq`; `.clusters`
equal to `prepared/argo-clusters-override.yaml`; the fleet account named 0 times). No file in `environments/`,
`gitops/`, `charts/` or `local-development/` changed between `708e6be1` and `57735e9e`: `git diff --stat` prints
nothing.

## The grants: REMOVED 0

`prepared/walk-rbac.yaml` holds one grant: the keep-grant, a Role and a RoleBinding in `openshift-config`. It keeps
the dashboard ServiceAccount's `get` on `ldap-oauth-bind-secret` while the walk values point the chart's
fleet-account grant at the walk Secret. It is grant 1 of #310, relabelled `walk.gsd.lab/run=claimheld-445-2026-09-30`.
There is no `developer` binding: step 6's processes act as the ServiceAccount, and the chart renders its `leases` rule
(`get`, `create`, `update`) identically in both shapes (`evidence/offline-render.txt`).

Rendered with `helm template` (v4.3.0) and expanded per subject by
`reports/2026-09-27_epic-c-walk-432/scripts/rbac_grants.py` (`evidence/offline-rbac-diff.txt`). The renders are 3318
lines each; the grants file is 45 lines.

```text
without the walk grant:        grants 66 -> 66, REMOVED 1
  - ServiceAccount:group-sync-dashboard:group-sync-dashboard | openshift-config | secrets | get | ldap-oauth-bind-secret
with prepared/walk-rbac.yaml:  grants 66 -> 67, REMOVED 0, REMOVED for the dashboard ServiceAccount: 0
  + ServiceAccount:group-sync-dashboard:group-sync-dashboard | group-sync-dashboard | secrets | get | gsd-walk-developer-password
```

The one ADDED atom is `get` on a Secret that will not exist. `scripts/sweep.sh` removes the keep-grant only once the
chart's own `group-sync-dashboard-fleet-account` Role and binding grant that `get` again, after `--argocd main`.

## The plan in brief

Phase 2 is one script, `scripts/run.sh`, run in the background with one waiter on its exit.

| # | Step | Writes | Guard |
|---|---|---|---|
| 0 | Preflight, all reads: `kubeadmin`; podman up; `PY` has pytest and PyYAML; no run-labelled object; `developer`'s Lease **absent** (the sweep may only delete what this walk created); the walk Secret absent; Argo CD `main Synced 57735e9e…`; both PVCs `Delete=false` and `keep`; GitHub's `main` is `57735e9e…`. Clone `57735e9e` into `WALK_TMP`. **Extract the coordinator from the clone's SPEC_S4c** with `scripts/extract_step6.py`, check its sha256 against the pin, compile it. Start baseline (full), informational lab check. | none | aborts before the trap on any mismatch |
| — | **The EXIT trap is set** (`scripts/sweep.sh`); the kill -9 recovery is printed | — | runs on every exit before the hand-back ends |
| 1 | The keep-grant, `oc create` after a server dry run | 2 RBAC objects | REMOVED 0 |
| 2 | `release-crc.sh --values prepared/walk-values-claimheld.yaml` from the clone (Helm mode): builds `2.0.0-57735e9ee8`, deletes the Argo CD Application, installs | images, the release | exit 0 or abort |
| 3 | The walk pod takes the leader Lease | none | 180 s |
| 6.0 | Lab check `0 0 0`; `developer`'s Lease free (absent, no holder, or past renew + duration); the spec's read, verbatim; `STEP6_SINCE`, both challenging-client counts, the fleet Lease's sha256 | none | abort unless `0 0 0`; abort if still held after 180 s |
| 6.1–6.3 | `oc exec -i -n group-sync-dashboard deploy/group-sync-dashboard -c dashboard -- python3.14 - < <the extracted program>` | `developer`'s Lease: A's POST (or PUT) and A's release | exactly `HELD …`, `ClaimHeld … until …`, `RELEASED`, exit 0, and the Lease's holder empty after; otherwise abort (no automatic retry) |
| 6.4 | The derived audit in `[STEP6_SINCE, now)`; the counts again; the fleet Lease's sha256 again | none | `developer` 0 and the fleet account 0 authorizes, counts equal, fleet count 2, sha equal; else "ABORT: an authorize ran in the window" |
| — | The pod's log, read once, derived | none | — |
| 7 | `release-crc.sh --argocd main`, then `sweep.sh handback` | the reverse of 1–2, and `developer`'s Lease | the sweep never drops a ServiceAccount permission, never deletes a held Lease |
| 8 | Audits for three windows (before the walk pod leads: INFO; its tenure: MUST 0/0; after the hand-back: INFO), the end baseline, the comparison, and a count of the fleet account's name in `evidence/` (MUST 0) | none | exit 0 only if all hold |

### The coordinator comes from the spec, never from a copy

`scripts/extract_step6.py` does no parsing of its own. It imports the repository's
`local-development/tests/test_s4c_step6_walk.py` and uses:

- `live_step6()`: the live §3.12 walk, step 6 up to step 7;
- `_HEREDOC`: the body of the `<<'PY' … PY` heredoc;

and dedents the result exactly as that test does. It also checks that step 6 holds exactly one heredoc, and that
its command line is `oc exec -i -n group-sync-dashboard deploy/group-sync-dashboard -c dashboard -- python3.14 -`,
the one `run.sh` runs. The program is 82 lines, sha256 `2b5e210329a66ce6dc3387470ade604bb835028e36dc00e04a28298dca5be9c2`
(`evidence/offline-coordinator.txt`). `run.sh` pins that sha256 and re-extracts from the spec at `57735e9e` in its
preflight. If the spec's program differs from the one rehearsed here, phase 2 aborts before any write.

### The expected output, quoted from the spec

> Expect `HELD walk-step6-a gsd-fleet-88fa0d759f845b47`, then one line
> `ClaimHeld walk-step6-a holds gsd-fleet-88fa0d759f845b47 until …`, then `RELEASED`, and exit 0.

and for 6.4 (the spec's second line names the fleet account; it is shown here as `<the fleet account>`):

```text
#   developer authorize records, any decision: 0
#   <the fleet account> authorize records, any decision: 0
```

Two differences in this walk's evidence. The fleet account's line reads `the fleet account's authorize records, any
decision: 0`, because its name is never printed. And the token line reads `the fleet account,
openshift-challenging-client: 2`.

### The rehearsal: the verbatim program, in the image, against a fake API server

`scripts/stub/rehearse_step6.py` runs inside `localhost/group-sync-dashboard:2.0.0-708e6be104` with `podman run -i
--network none`. The program goes in on stdin, exactly as `oc exec -i … python3.14 -` delivers it. It runs under the
image's own `python3.14` and its own `gsd`. That image's 68 `gsd` modules are byte-identical to this tree's (sha256,
module by module, in `evidence/offline-coordinator.txt`). The host cluster is a fake Lease API on 127.0.0.1, with CAS
enforced and every request logged. The pod's namespace file and `GSD_CONFIG` are mounted.

| The Lease before | Output | Requests | Exit |
|---|---|---|---|
| absent (the lab today) | `HELD walk-step6-a gsd-fleet-88fa0d759f845b47` / `ClaimHeld walk-step6-a holds gsd-fleet-88fa0d759f845b47 until <instant>` / `RELEASED` | GET 404, POST 201 (A); GET 200 (B, no write); PUT 200 (A's release); GET 200 | 0 |
| free (the spec's premise) | the same three lines | GET, PUT (A); GET (B); PUT; GET | 0 |
| held by another (6.0 skipped) | A's traceback `ClaimHeld: group-sync-dashboard-pod holds …`, `ABORT: process A did not hold`, `ABORT: process A did not release` | one GET, **no write** | 2 |

## What phase 2 captures as evidence

All of it goes under `evidence/`. No password or token is captured: none is placed. The fleet account is counted,
never named, and `run.sh` counts its name across `evidence/` at the end (MUST 0).

| File | What |
|---|---|
| `phase2-start-baseline.txt`, `phase2-end-baseline.txt` | `scripts/baseline.sh`: `oauth/cluster`'s spec by sha256 (never written); the dashboard Deployment, pod and `/api/version`; Argo CD, with a derived `argo:` line; PVC UIDs and annotations; cluster Secrets by name, resourceVersion and creation; the fleet Lease's resourceVersion, holder, ping instants and sha256; `developer`'s Lease; OAuthAccessToken counts and creation instants; the `can-i` grants (the ServiceAccount's `get` on `ldap-oauth-bind-secret` and on the walk Secret, and `create`/`update` on leases); the run-labelled objects |
| `phase2-*-labcheck.txt` | the three counts: as found (`1 0 0` expected), and at 6.0 (`0 0 0` required) |
| `phase2-walk-rbac-create.txt`, `phase2-deploy-release-crc.log`, `phase2-handback-release-crc-argocd-main.log` | what was created, and the two `release-crc.sh` runs |
| `phase2-step6.0.txt` | the spec's Lease read verbatim, the state, `STEP6_SINCE`, the counts, the fleet Lease's sha256 |
| `phase2-step6.1-6.3.txt` | the command, the program's sha256, its stdout, its stderr, its exit code, and the Lease after it |
| `phase2-step6.4.txt`, `phase2-step6.4-audit.txt` | the derived audit in `[STEP6_SINCE, now)`, and the counts before and after |
| `phase2-podlog.txt` | the walk pod's log, read once: the leader lines, any line naming `developer`'s Lease (0 expected: the pod never touches it, and step 6's processes write to the exec stream), fleet-* and self-login-* lines, errors |
| `phase2-{before-walk-pod,walk-pod,after-handback}-audit.txt` | the three windows' derived audits |
| `handback-sweep.txt` (or `trap-sweep.txt`), `phase2-compare.txt`, `phase2-run.txt` | the restore, the start/end comparison line by line, the whole run's log |

`scripts/capture.sh audit` is #310's, with one addition: a read that returns no records exits 2, and a log whose
earliest record is later than the window's start exits 3. Neither can be read as "0 authorizes"
(`evidence/offline-audit.txt`).

## Timings

These were measured by the #310 walk on this lab and this workstation on 2026-09-30
(`reports/2026-09-30_selflogin-renewal-310/evidence/phase2-run.txt`):

- `release-crc.sh --values` took 99 s, 20:17:47Z to 20:19:26Z, and that included building both images;
- the walk pod led within 5 s of it (20:19:31Z);
- `release-crc.sh --argocd main` took 64 s, 20:44:27Z to 20:45:31Z.

Step 6's own duration was not measured, in the rehearsal or on the lab. Its bounds are A's 30 s wait, B's 15 s
timeout and the 10 s release. This script's waits are 180 s for the leader and 180 s for 6.0. `release-crc.sh` bounds its rollout at 300 s
and `argocd-wait.sh` bounds the sync at 900 s. The run's total length on the lab was **not measured**. From #310's
figures it is on the order of minutes.

## Risks

- **Helm mode deletes the Argo CD Application with its cascade**, as on 2026-09-27 and 2026-09-30. The PVCs survive by
  their live `Delete=false`, and the preflight aborts without it. As found: data
  `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`. The UIDs are a
  MUST line at the end.
- **The build.** `release-crc.sh` at `57735e9e` builds `2.0.0-57735e9ee8`: the phase 1 read found only
  `2.0.0-708e6be104` in the internal registry (`evidence/phase1-risk-reads.txt`). The images stay, per the operator's rule. There is an alternative
  (open question 3).
- **`--argocd main` deploys whatever `main` is on GitHub.** The preflight aborts unless it is `57735e9e`.
- **The fleet account's daily ping.** It last ran at 2026-09-30T17:58:43Z (the fleet Lease, phase 1), so it is next
  due at 2026-10-01T17:58:43Z. If phase 2 starts after that, the Argo CD pod pings the fleet account before the
  deploy and again after the hand-back. That is the product, not the walk, and the audit windows keep it apart: the
  walk pod's tenure is a MUST 0/0, before and after are INFO. The fleet Lease's resourceVersion and sha256 are INFO
  lines start to end. Within 6.0–6.4 its sha256 is a MUST: the walk pod does not declare the fleet account, so it
  never writes that Lease.
- **A coordinator cut off mid-claim.** A network drop during `oc exec` could leave A's claim live for up to 195 s.
  The spec says to wait, never to delete it. `run.sh` aborts with no retry. `sweep.sh` leaves a held Lease in place
  (exit 5) and deletes it only once it is free and the configuration no longer names `developer`. The `oc exec`
  itself has no timeout of its own: macOS has no `timeout(1)` by default. A hung exec would need the operator to
  stop the run, and the trap then sweeps.
- **`developer`'s Lease outlives a failed run**, as do the keep-grant and the walk release. The trap leaves them on
  purpose until the hand-back, and prints the command that finishes it.
- **The walk cluster rows.** None: this walk adds no cluster, so no retired row is left in the database.

## Open questions for the orchestrator

1. **The Lease absent at 6.0** (item 2 in the list of mismatches above): accept "absent is not in flight" as the
   code defines it? Or should phase 2 first make the product create the Lease? That second option needs a
   `developer` stanza, `developer`'s password, a real bind, and the token-reader grant.
2. **The arrangement:** no stanza and no password Secret (this plan), rather than the brief's "walk-only password
   Secret" and "a stanza that gives `developer` a Lease".
3. **The build:** build `2.0.0-57735e9ee8`, or deploy from a `708e6be1` clone and reuse `2.0.0-708e6be104` (no build;
   the same code, per the `git diff` and the 68-module sha256 match)? The plan builds, so the tag names the commit
   the brief names.
4. **The ping:** leave the chart default (on), which has no `developer` target, or set `ping.enabled: false`?
5. **The trap does not run `--argocd main`**, as in #310. Should it here? Unlike #310, there is no cluster-wide state
   to settle first.
6. **The two prose slips in step 6** (items 4 and 5): fix them in the spec after the walk, or leave them?

## The offline proofs (phase 1)

`PY=<the repo's venv python> bash scripts/offline_proofs.sh` runs all nine groups. It reads no cluster.
`REHEARSAL_IMAGE` defaults to `localhost/group-sync-dashboard:2.0.0-708e6be104`. The last run printed `ALL OFFLINE
PROOFS PASS`.

| Proof | Result | Evidence |
|---|---|---|
| the walk values equal `environments/crc.yaml` outside the two blocks; `.clusters` is the Argo override; the fleet account named 0 times | PASS ×3 | `evidence/offline-values.txt` |
| the render: the fleet account in the walk's `clusters.yaml`, in its whole render, and in the Argo shape's `clusters.yaml` | 0, 0, 1; `fleetAccountUsername: "developer"`; 0 `ldapConnectionBootstrap` / `saTokenLookup` / `userSelfLogin`; the same `leases` rule bound to the ServiceAccount in both | `evidence/offline-render.txt` |
| rendered RBAC, the Argo shape → the walk (3318 / 3318 / 45 lines) | REMOVED 1 without the keep-grant, **REMOVED 0** with it | `evidence/offline-rbac-diff.txt` |
| `lease_name("developer")` from the code = `lib.sh`'s = the spec's | PASS | `evidence/offline-lease-name.txt` |
| this walk's arrangement, `scripts/test_step6_arrangement.py` | 2 passed | `evidence/offline-hermetic.txt` |
| the spec's own step-6 pins, `tests/test_s4c_step6_walk.py` | 7 passed | same |
| ClaimHeld across processes, the tests SPEC_S4c §3.11 names: R1 `test_r1_two_processes_cannot_both_win_one_claim_and_no_claim_is_no_bind`; R2 `test_r2_the_budget_over_the_system_one_authorize_across_two_processes_three_targets_a_restart_and_an_edit[401\|500]`; D1 `test_d1_clock_skew_does_not_admit_a_second_bind`, `test_d1_skew_takeover_at_each_point_of_the_attempt[reservation\|authorize\|refusal]`, `test_d1_a_paused_winner_resumes_after_the_takeover_and_does_not_bind`; C5 `test_d1_paused_winner_success_clears_its_own_reservation_on_409`, `test_d1_paused_winner_complete_does_not_erase_a_foreign_refusal` | 10 passed, each named PASSED | same |
| `tests/test_fleet_lifecycle.py` + `test_fleet_lifecycle_round3.py` + `test_fleet_gate_backstop.py`; `tests/test_ping_account_scope.py` | 90 passed; 24 passed | same |
| the coordinator: extracted, compiled, pinned; the image's `gsd` = this tree's; rehearsed absent / free / held | PASS, PASS (68 modules); exit 0 / 0 / 2 with the lines above | `evidence/offline-coordinator.txt` |
| `scripts/sweep.sh` five times against a stub `oc` | exit 5, 5, 5, 0, 0: the keep-grant kept while a cut-short cascade is deleting the Application and until the chart's grant is back on Argo CD; the Lease kept while the configuration names `developer` and while a claim is live; everything removed at the end; 0 unexpected calls | `evidence/offline-restore.txt` |
| `scripts/capture.sh audit` against a stub `oc`, on 8 synthetic records | the window's counts (developer 2, the fleet account 1, another user never printed); an empty read exits 2, a late log exits 3 | `evidence/offline-audit.txt` |
| `bash -n`, `shellcheck -x` (0.11.0) on every script | PASS | `evidence/offline-lint.txt` |

### The stub harness

- `scripts/stub/oc` answers exactly the calls `sweep.sh` and `capture.sh audit` make, from state files in a temporary
  directory, and logs every call. It fails (exit 97) on any call it does not know, so a changed script cannot pass by
  meeting a silent stub.
- The stub runs use `env -i` with the stub first on `PATH`, under `bash`, with `KUBECONFIG=/dev/null`. A mistaken
  call can reach no cluster.
- `scripts/stub/rehearse_step6.py` is the fake API server and launcher for the in-image rehearsal. It uses the
  standard library only.
- All proofs run with `PYTHONDONTWRITEBYTECODE=1` and `-p no:cacheprovider`, and leave nothing in the tree.

## The lab as found (phase 1, read-only, 2026-09-30T21:50Z)

From `evidence/phase1-as-found-baseline.txt` (`scripts/baseline.sh phase1-as-found --get-only`: `oc get` only, so no
`/api/version` and no `can-i`):

- **The dashboard.** `quay.io/ephico2real/group-sync-dashboard:2.0.0`, chart `group-sync-dashboard-0.59.25`, pod
  started 2026-09-30T20:44:45Z. There is no Helm release record. Argo CD is `Synced` at
  `57735e9ee8fe4a8bf7cf6df97b0ebde50ca21a61` and `Healthy`.
- **PVCs.** Data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`,
  both `resource-policy=keep` and `Prune=false,Delete=false,PruneLast=true`.
- **Cluster Secrets.** `gsd-cluster-shared-qa` rv `2981054`, `gsd-cluster-shared-rnd` rv `2835139`, and the four mock
  Secrets. By a read of their declared modes, booleans only, none declares `saTokenLookup` or `userSelfLogin`, and
  none carries `ldapConnectionBootstrap`. `shared-rnd` alone carries `token-source=remote-lookup` and a
  `lookup-account`. There are 0 onboarding ConfigMaps (`evidence/phase1-risk-reads.txt`).
- **The fleet Lease.** `gsd-fleet-666f1ba7f2fdead0` is at rv `7468503`, with no holder. Its last ping was ok at
  2026-09-30T17:58:43Z, and it has no refusal. Its sha256 is `fb7092eedd5bb05cc1ab02d4bac3b1509c0439247e33f254b5d0a86d8c98a302`.
  `developer`'s Lease `gsd-fleet-88fa0d759f845b47` is **absent**.
- **OAuthAccessTokens.** 256 in all. `developer`'s challenging-client tokens: 6. The fleet account's: 2, created
  2026-09-19T00:48:44Z and 00:50:11Z.
- **The walk's objects.** Nothing carries the run label, and the walk Secret does not exist.
- **The lab check.** `1 0 0`, as expected on the Argo CD configuration.
- **`oauth/cluster`.** Its `.spec` sha256 is `305a2986…`, and the authentication operator reads `Available=True
  Degraded=False Progressing=False`.

## Files

- `prepared/walk-values-claimheld.yaml`: the walk's values (above).
- `prepared/walk-rbac.yaml`: the keep-grant.
- `prepared/argo-clusters-override.yaml`: the Application's `valuesObject`, for rendering the Argo CD shape (#310's copy).
- `scripts/lib.sh`: names and helpers, including `developer`'s Lease state and the in-flight rule. The fleet account's
  username is read from its Lease, into a variable.
- `scripts/run.sh`: phase 2, with the trap.
- `scripts/extract_step6.py`: the coordinator, from the spec, through the repository's own test module.
- `scripts/sweep.sh`: the restore, safe to run any number of times.
- `scripts/labcheck.sh`: the spec's three counts (#310's, unchanged below its header).
- `scripts/baseline.sh`, `scripts/compare_baselines.sh`: the lab's invariants, and their comparison.
- `scripts/capture.sh`: the pod log (read once) and the derived audit.
- `scripts/test_step6_arrangement.py`: the arrangement, hermetically.
- `scripts/offline_proofs.sh`, `scripts/stub/`: the phase 1 proofs, the stand-in `oc`, and the in-image rehearsal.

## How to run phase 2

With the plan accepted, from this worktree's copy of the folder:

```sh
WALK_TMP=<a scratch directory outside the repository> \
KUBECONFIG=/Users/olasumbo/.claude/gsd-session-2026-09-28/kc-crc \
PY=/Users/olasumbo/gitRepos/group-sync-dashboard/local-development/.venv/bin/python \
  bash reports/2026-09-30_claimheld-step6-445/scripts/run.sh     # in the background, one waiter on its exit
```

`PY` must have pytest and PyYAML: the extraction imports the repository's step-6 test module, and the venv above has
both. `run.sh` exits 0 only if all of these hold:

- step 6 printed its three lines and 6.4's counts held;
- the hand-back's `release-crc.sh --argocd main` exited 0 (Synced and Healthy at `main`);
- the hand-back's sweep removed everything;
- the walk pod's tenure audit is 0 authorizes for `developer` and 0 for the fleet account;
- the start/end comparison is equal on every MUST line;
- the fleet account is named 0 times in `evidence/`.

If it stops early, the trap sweeps what is safe to remove, and `evidence/phase2-run.txt` ends with what is left and
the command that finishes it. Give the background task the harness's maximum timeout. The run's length was not
measured; see "Timings".

### If the run is killed

SIGKILL, or any stop that gives the trap no time, leaves whatever the run had reached. No password was ever placed,
and no cluster-wide object was ever written. In this order, from this worktree:

```sh
(cd <WALK_TMP>/deploy-57735e9e/local-development && ./release-crc.sh --argocd main)
KUBECONFIG=/Users/olasumbo/.claude/gsd-session-2026-09-28/kc-crc bash reports/2026-09-30_claimheld-step6-445/scripts/sweep.sh manual
```

If `sweep.sh` reports `developer`'s Lease as held, wait until its renew time plus 195 s has passed, then run it again.
Never delete a held Lease.
