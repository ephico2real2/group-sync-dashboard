# #481 on the lab: a `crc start` deletes the fleet Lease and the dashboard puts it back — 2026-09-29

**Outcome.** On the CRC lab at application 1.18.0 (`4e19d976a2`, `evidence/before-version.txt`; chart 0.59.20 at that
commit (the #481 release commit's `Chart.yaml`), synced from `main` by Argo CD,
`gitops/argocd-application-dashboard.yaml#targetRevision: main`), the dashboard kept a copy of the fleet Lease's
annotations in `/data/fleet-gate.json` on its data volume, equal to the Lease (`evidence/before-file.txt`:
`equal_to_lease {'gsd-fleet-666f1ba7f2fdead0': True}`). The orchestrator then ran `crc stop` and `crc start`, on the
operator's instruction (`evidence/crc-restart.txt`). `crc start` deleted every Lease on the cluster, as it does on every
cold start (crc's own `oc delete -A lease --all`, read in
`docs/specs/SPEC_S4f_fleet_gate_backstop.md#2.1 Who deletes the fleet Lease`): after it, all 58 Leases were created at
or after 12:02:20Z (`evidence/after-lease.txt`: `count=58 oldest=2026-09-29T12:02:20Z`).
- **The dashboard put the fleet Lease back from its copy.** At 12:03:43Z it logged `fleet-lease-absent … lease=gsd-fleet-666f1ba7f2fdead0 kept=true last_attempt=2026-09-28T17:57:01Z`
  (`evidence/after-podlog.txt`). The Lease was re-created at 12:03:43Z with a new uid (`e6e2daed-…`, where it was
  `b20785d0-…` before). Its five annotations were identical to the ones before the start, and the copy still equals the
  Lease (`evidence/after-lease.txt`, `evidence/after-file.txt`). The copy's content is unchanged; its mode is `0o664`
  where it was `0o644` before the start (`evidence/before-file.txt`, `evidence/after-file.txt`). The dashboard does not
  set that group-write bit — its writer creates the file with `open(tmp, "w")` and skips an entry equal to the file's
  (`gsd/fleetstate.py#FileBackstop.save`) — so something outside the dashboard added it between the two captures. A
  kubelet fsGroup ownership pass on the volume's remount after the reboot would; it was not measured here.
- **No second fleet bind and no second ping.** Over the restarted container's whole log — `oc logs` without
  `--previous`, so from its start (its leader election at 12:03:41Z) to the capture at 12:10:55Z, 503 lines:
  `fleet-login lines: 0`, `fleet-ping lines: 0`, `fleet-lookup lines: 0`, `fleet-state-unavailable lines: 0`, 0
  Traceback, 0 ERROR (`evidence/after-podlog.txt`). The container that ran from 11:38:20Z until the stop is not in
  that log. That it pinged nothing is shown by the Lease itself: a ping stamps `ping-last-attempt` with its claim
  before it binds (`gsd/poller.py#Poller._ping_accounts`), and the stamp reads `2026-09-28T17:57:01Z` before and after
  (`evidence/before-lease.txt`, `evidence/after-lease.txt`). The day's ping is not due until 2026-09-29T17:57:01Z, one
  interval after `ping-last-attempt` with the same password digest (`gsd/poller.py#Poller._ping_accounts`; the interval
  is `charts/group-sync-dashboard/values.yaml#intervalSeconds: 86400`, not overridden on the lab).
- **Without the fix,** the same kind of restart on 2026-09-28 lost the Lease's ping record, and the dashboard pinged a
  second time that day: `fleet-login cluster=shared-rnd` at 17:57:02Z, then `fleet-ping … last_ok=2026-09-28T17:57:01Z`
  (#481, "Where this stands").

The walk changed nothing but the CRC restart itself and, after it, one restart of Argo CD's application controller pod
(`oc delete pod` at 12:11:16Z, `evidence/argo-after-restart.txt`; see "Argo CD after a `crc start`"). The PVC UIDs and
`shared-qa`'s `resourceVersion` 2981054 are the same before and after (`evidence/before-state.txt`,
`evidence/after-state.txt`). Nobody logged in as the fleet account in the restarted container's log, the captures are
read-only (`scripts/capture.sh`), and no password was placed or changed by the walk. The dashboard container restarted
in place: the same pod, `restarts` 0 → 1 (`evidence/before-version.txt`, `evidence/after-version.txt`).

## Definition of Done

| Row | Verdict | Evidence |
|---|---|---|
| Before: 1.18.0 deployed, and the copy beside the database equals the fleet Lease | PASS | `/api/version` `"version":"1.18.0","commit":"4e19d976a2"` at 11:39:17Z; the dashboard and report pods started at 11:38:20Z and 11:38:21Z (`evidence/before-version.txt`). `/data/fleet-gate.json` exists, mode `0o644`, and holds `ping-digest`, `ping-last-attempt` `2026-09-28T17:57:01Z`, `ping-last-ok`, `ping-last-outcome` `ok` and `ping-last-target` `shared-rnd` for `gsd-fleet-666f1ba7f2fdead0`; `equal_to_lease` `True` (`evidence/before-file.txt`). The Lease had uid `b20785d0-a5b2-42aa-a46a-a27e6344250d`, `resourceVersion` 6171122, created 2026-09-28T17:57:01Z, no holder; the cluster had 58 Leases, none older than 2026-09-28T17:55:17Z (`evidence/before-lease.txt`). |
| The restart deletes every Lease | PASS | `crc stop` at 12:01:35Z, `crc start` at 12:01:41Z, returning at 12:04:45Z (`evidence/crc-restart.txt`). The watcher saw the API go down at 12:01:48Z, and the API up with the dashboard ready at 12:03:53Z (`evidence/restart-observed.txt`). After: `count=58 oldest=2026-09-29T12:02:20Z` (`evidence/after-lease.txt`). |
| The dashboard puts the fleet Lease back from the copy, and says so once | PASS | One `fleet-lease-absent` line, at 12:03:43Z: `account=<fleet account> lease=gsd-fleet-666f1ba7f2fdead0 kept=true last_attempt=2026-09-28T17:57:01Z`, with the action "the Lease was deleted — by hand, or by `crc start`, which deletes every Lease on the cluster — and is put back from the copy kept beside the database, as this dashboard last read it; if an entry was removed by hand while no pod read the Lease, it is back: remove it again and restart the pod" (`evidence/after-podlog.txt`). The Lease after: uid `e6e2daed-495c-411b-8a99-657e15a81eac`, created 2026-09-29T12:03:43Z, `resourceVersion` 6761163, no holder, and the same five annotations with the same values (`evidence/after-lease.txt`). The copy's content is unchanged and `equal_to_lease` `True`; its mode is `0o664` where it was `0o644` (`evidence/after-file.txt`; the Outcome says why). |
| No second fleet bind and no second ping that day | PASS | Over the restarted container's whole log (503 lines from its leader election at 12:03:41Z, captured 12:10:55Z): `fleet-login lines: 0`, `fleet-logout lines: 0`, `fleet-ping lines: 0`, `fleet-lookup lines: 0`, `fleet-state-unavailable lines: 0`, `cluster-rejoin lines: 0`, `Traceback lines: 0`, `ERROR lines: 0` (`evidence/after-podlog.txt`). The container before the stop is not in that log; that it pinged nothing is the unchanged `ping-last-attempt` `2026-09-28T17:57:01Z` (`evidence/before-lease.txt`, `evidence/after-lease.txt`). The 2026-09-28 restart without the fix pinged again at 17:57:02Z (#481). |
| The lab left as found | PASS | Version 1.18.0 at `4e19d976a2` after (`evidence/after-version.txt`). PVC UIDs `f065b7a4-535c-4ef1-868c-58f5afee4953` (data) and `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` (report-artifacts), and `shared-qa` `resourceVersion=2981054`, before and after (`evidence/before-state.txt`, `evidence/after-state.txt`). Argo CD: three Applications (`16-keycloak`, `20-shop-envoy`, `group-sync-dashboard`) came back `Unknown`/`ComparisonError` after the start and the other six `Synced/Healthy`; a restart of its application controller at 12:11:16Z — the one change the walk made beyond the CRC restart — brought every Application back to `Synced/Healthy` by 12:13:48Z (`evidence/after-argo.txt`, `evidence/argo-after-restart.txt`). |

## What the lab did not show

- **A refused password staying refused.** Showing it would need a wrong fleet password placed on the lab, which is not
  done. The PR's `local-development/tests/test_fleet_gate_backstop.py` measures it: a refused (401) or locked (500)
  password on the lookup, the ping and self-login binds +0 after a `crc start`, where it bound +1 before
  (`test_a_refused_password_stays_refused_across_crc_starts`). The lab walk shows the same mechanism, the Lease put back
  from the copy with its annotations, for the ping record it carries today.
- **The warning's `kept=false` form** (an account with retrieved clusters and nothing kept): the copy existed here.
- **More than one replica, persistence off, an etcd restore:** out of scope, as SPEC_S4f §1.3 states.
- **A fleet bind in the container that ran before the stop** (11:38:20Z to 12:01:48Z): its log was not captured, so
  nothing captured shows a lookup or a self-login bind absent for that window; a ping is shown absent by the Lease's
  unchanged `ping-last-attempt`.

## Argo CD after a `crc start`

The same `crc start` left `16-keycloak`, `20-shop-envoy` and `group-sync-dashboard` at `Unknown` with `ComparisonError`,
as on 2026-09-28; the other six Applications were `Synced/Healthy`, `grafana` among them, whose chart also renders a
Route (`charts/openshift-grafana/values.yaml#route:` `enabled: true`, and the Route is named in
`gitops/argocd-application-grafana.yaml#name: grafana-openshift-grafana`), so which resource each of the three failed
to compare is not shown by `evidence/after-argo.txt` — the ComparisonError's text was not captured. The application
controller started at 12:02:40Z, 12 seconds before the `v1.route.openshift.io` APIService became Available at 12:02:52Z
(`evidence/argo-after-restart.txt`); on 2026-09-28 that was read as the Route missing from its schema cache. Restarting
the controller pod at 12:11:16Z brought all nine Applications to `Synced/Healthy` by 12:13:48Z
(`evidence/argo-after-restart.txt`). This is the lab's GitOps, not the dashboard. It did not delay the dashboard,
because 1.18.0 was already deployed.

## Files

- `scripts/capture.sh`: the read-only `before` and `after` captures of the version and pods, the PVCs and `shared-qa`,
  the fleet Lease and the copy. It drops the Lease's `account` annotation from the Lease capture, and pipes the copy's
  capture through a filter that replaces the fleet account's name with `<fleet account>` and any `sha256~` value with
  `sha256~<redacted>`.
- `evidence/`: every capture, its command or source first and the instant it ran. `crc-restart.txt`,
  `restart-observed.txt`, `after-podlog.txt`, `after-argo.txt` and `argo-after-restart.txt` come from the commands their
  first lines name, not from the script; the per-event counts in `after-podlog.txt` are recorded without the command
  that produced them, and its one data line carries the same `<fleet account>` replacement.

## The walk document, removed from git (2026-10-05)

The operator, 2026-10-05: walk documents are kept locally for review and not in git. The text above is left as
recorded. `walk.html` is no longer in the tree; it remains in history, at [this folder at `6862ba8161`](https://github.com/ephico2real2/group-sync-dashboard/tree/6862ba8161253261d59f0b1afda209ad47117b8a/reports/2026-09-29_fleet-gate-481-walk).
