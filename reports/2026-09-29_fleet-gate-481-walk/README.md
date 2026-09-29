# #481 on the lab: a `crc start` deletes the fleet Lease and the dashboard puts it back — 2026-09-29

**Outcome.** On the CRC lab at application 1.18.0 (`4e19d976a2`, `evidence/before-version.txt`), the dashboard kept a
copy of the fleet Lease's annotations in `/data/fleet-gate.json` on its data volume, equal to the Lease
(`evidence/before-file.txt`: `equal_to_lease {'gsd-fleet-666f1ba7f2fdead0': True}`). The orchestrator then ran
`crc stop` and `crc start`, on the operator's instruction (`evidence/crc-restart.txt`). `crc start` deleted every Lease
on the cluster, as it does on every cold start: after it, all 58 Leases were created at or after 12:02:20Z
(`evidence/after-lease.txt`).
- **The dashboard put the fleet Lease back from its copy.** At 12:03:43Z it logged `fleet-lease-absent … lease=gsd-fleet-666f1ba7f2fdead0 kept=true last_attempt=2026-09-28T17:57:01Z`
  (`evidence/after-podlog.txt`). The Lease was re-created at 12:03:43Z with a new uid (`e6e2daed-…`, where it was
  `b20785d0-…` before). Its five annotations were identical to the ones before the start, and the copy still equals the
  Lease (`evidence/after-lease.txt`, `evidence/after-file.txt`).
- **No second fleet bind and no second ping.** Over the dashboard container's whole log, captured at 12:10:55Z:
  `fleet-login lines: 0`, `fleet-ping lines: 0`, `fleet-lookup lines: 0`, `fleet-state-unavailable lines: 0`, 0
  Traceback, 0 ERROR (`evidence/after-podlog.txt`). The day's ping is not due until 2026-09-29T17:57:01Z, one interval
  after `ping-last-attempt`.
- **Without the fix,** the same kind of restart on 2026-09-28 lost the Lease's ping record, and the dashboard pinged a
  second time that day: `fleet-login cluster=shared-rnd` at 17:57:02Z, then `fleet-ping … last_ok=2026-09-28T17:57:01Z`
  (#481, "Where this stands").

The walk changed nothing but the CRC restart itself. The PVC UIDs and `shared-qa`'s `resourceVersion` 2981054 are the
same before and after (`evidence/before-state.txt`, `evidence/after-state.txt`). Nobody logged in as the fleet account,
and no password was placed or changed. The dashboard container restarted in place: the same pod, `restarts` 0 → 1
(`evidence/before-version.txt`, `evidence/after-version.txt`).

## Definition of Done

| Row | Verdict | Evidence |
|---|---|---|
| Before: 1.18.0 deployed, and the copy beside the database equals the fleet Lease | PASS | `/api/version` `"version":"1.18.0","commit":"4e19d976a2"` at 11:39:17Z; the 1.18.0 pods started at 11:38:20Z and 11:38:21Z (`evidence/before-version.txt`). `/data/fleet-gate.json` exists, mode `0o644`, and holds `ping-digest`, `ping-last-attempt` `2026-09-28T17:57:01Z`, `ping-last-ok`, `ping-last-outcome` `ok` and `ping-last-target` `shared-rnd` for `gsd-fleet-666f1ba7f2fdead0`; `equal_to_lease` `True` (`evidence/before-file.txt`). The Lease had uid `b20785d0-a5b2-42aa-a46a-a27e6344250d`, `resourceVersion` 6171122, created 2026-09-28T17:57:01Z, no holder; the cluster's 58 Leases were all from the previous start, the oldest at 2026-09-28T17:55:17Z (`evidence/before-lease.txt`). |
| The restart deletes every Lease | PASS | `crc stop` at 12:01:35Z, `crc start` at 12:01:41Z, returning at 12:04:45Z (`evidence/crc-restart.txt`). The watcher saw the API go down at 12:01:48Z, and the API up with the dashboard ready at 12:03:53Z (`evidence/restart-observed.txt`). After: `count=58 oldest=2026-09-29T12:02:20Z` (`evidence/after-lease.txt`). |
| The dashboard puts the fleet Lease back from the copy, and says so once | PASS | One `fleet-lease-absent` line, at 12:03:43Z: `account=<fleet account> lease=gsd-fleet-666f1ba7f2fdead0 kept=true last_attempt=2026-09-28T17:57:01Z`, with the action "the Lease was deleted — by hand, or by `crc start`, which deletes every Lease on the cluster — and is put back from the copy kept beside the database, as this dashboard last read it; if an entry was removed by hand while no pod read the Lease, it is back: remove it again and restart the pod" (`evidence/after-podlog.txt`). The Lease after: uid `e6e2daed-495c-411b-8a99-657e15a81eac`, created 2026-09-29T12:03:43Z, `resourceVersion` 6761163, no holder, and the same five annotations with the same values (`evidence/after-lease.txt`). The copy is unchanged and `equal_to_lease` `True` (`evidence/after-file.txt`). |
| No second fleet bind and no second ping that day | PASS | Over the dashboard container's whole log (503 lines, captured 12:10:55Z): `fleet-login lines: 0`, `fleet-logout lines: 0`, `fleet-ping lines: 0`, `fleet-lookup lines: 0`, `fleet-state-unavailable lines: 0`, `cluster-rejoin lines: 0`, `Traceback lines: 0`, `ERROR lines: 0` (`evidence/after-podlog.txt`). The 2026-09-28 restart without the fix pinged again at 17:57:02Z (#481). |
| The lab left as found | PASS | Version 1.18.0 at `4e19d976a2` after (`evidence/after-version.txt`). PVC UIDs `f065b7a4-535c-4ef1-868c-58f5afee4953` (data) and `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` (report-artifacts), and `shared-qa` `resourceVersion=2981054`, before and after (`evidence/before-state.txt`, `evidence/after-state.txt`). Argo CD: the three Applications that hold a Route came back `Unknown`/`ComparisonError` after the start, and a restart of its application controller at 12:11:16Z brought every Application back to `Synced/Healthy` by 12:13:48Z (`evidence/after-argo.txt`, `evidence/argo-after-restart.txt`). |

## What the lab did not show

- **A refused password staying refused.** Showing it would need a wrong fleet password placed on the lab, which is not
  done. The PR's `local-development/tests/test_fleet_gate_backstop.py` measures it: a refused (401) or locked (500)
  password on the lookup, the ping and self-login binds +0 after a `crc start`, where it bound +1 before
  (`test_a_refused_password_stays_refused_across_crc_starts`). The lab walk shows the same mechanism, the Lease put back
  from the copy with its annotations, for the ping record it carries today.
- **The warning's `kept=false` form** (an account with retrieved clusters and nothing kept): the copy existed here.
- **More than one replica, persistence off, an etcd restore:** out of scope, as SPEC_S4f §1.3 states.

## Argo CD after a `crc start`

The same `crc start` left `16-keycloak`, `20-shop-envoy` and `group-sync-dashboard` at `Unknown` with `ComparisonError`,
as on 2026-09-28. The application controller started at 12:02:40Z, 12 seconds before the `v1.route.openshift.io`
APIService became Available at 12:02:52Z, so its schema cache has no Route. Restarting the controller pod rebuilt it
(`evidence/argo-after-restart.txt`). This is the lab's GitOps, not the dashboard. It did not delay the dashboard,
because 1.18.0 was already deployed.

## Files

- `scripts/capture.sh`: the read-only captures (`before`, `after`). It drops the Lease's `account` annotation, and
  replaces the fleet account's name with `<fleet account>` and any `sha256~` value with `sha256~<redacted>`.
- `evidence/`: every capture, its command or source first and the instant it ran.
