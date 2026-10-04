# Epic F's seal check on the lab, as its Definition of Done words it, 2026-10-04

**Outcome.** The check passed on application 5.0.0 at `704943a11c` (`walk.log`). It is the check #386's Definition of
Done names: two `compliance-snapshot` runs for one cluster, requested one after the other over the same snapshot,
return the same `sha256` from `GET /report/api/runs/{id}`, and a run over a newer snapshot with changed data returns a
different one. The earlier walks had proved the seal on `groups` (#270) and `access-certification` (the 4.7.0 walk);
this one runs the report the epic names.

- **One snapshot, one sha256.** Two runs on `dashboard` by `dana.lee`, `…133340.586020Z-09c0` and
  `…133342.786159Z-f863`. Both were built from snapshot `2026-10-04T13:33:32.084162Z`, and both returned
  `161cba2fdc8ec166c3e7bfa4003f6f026672939bcd366684c6c8e278fd778767`.
- **An older snapshot with changed data, another sha256.** The scheduled run `…020102.809069Z-3804`
  (`schedule:quarterly-compliance`, snapshot `01:59:23Z`) returned `61b5b1c86bf9…`. A `report-diff` from it to the
  first new run, `…133345.124705Z-dd3e`, reported `blocks_changed: 3`, with 4 rows added and 4 removed:
  - Key figures, RBAC: bindings 110 → 107, unmanaged 61 → 58, the data's change;
  - Key figures, Sync pipeline: "Last poll" `01:59:22Z` → `13:33:31Z`;
  - What this evidence attests, Coverage: the login capture's "last read" instant.
- **The PVC UIDs** were the same before and after.

## Found by this check
The second and third changes are instants, not data. A second probe on the static mock cluster `mock-trusted` showed
it plainly: a new run diffed against the scheduled `…-55bd` reported only those 2 blocks
(`…133421.885158Z-97dd`). So a `compliance-snapshot` diff across snapshots never reads "No change". This is filed as
#607 (Tech debt), the class #589 fixed for access-certification. That probe ran from a scratch script, not from
`scripts/`; its measurements are on #607.

| Path | Contents |
|---|---|
| `walk.log` | each command and its output |
| `scripts/` | `run.sh`, and `in_pod.py`, which runs in the report pod (the ticket reaches it on stdin only) |

To repeat: `KUBECONFIG=<the lab kubeconfig> scripts/run.sh`. It makes three runs, the product's own.
