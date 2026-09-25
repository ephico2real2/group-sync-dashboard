# #312 closed out on the lab: #354 deployed, the checks re-run — 2026-09-24

Captured on the CRC lab (OpenShift 4.22.7) against main `244d4ab` — #355 (docs and reports) on top of #354, which
stops the chart's own `rbac.ocp.io/config-source` label from counting as "a policy operator is in use" — application
0.32.0 and chart 0.53.1. It was deployed with `local-development/release-crc.sh --argocd` from a detached worktree at
that commit: both images built and stamp-verified, the Application Synced/Healthy at 01:20:51Z, `244d4ab9c0` verified
in-pod, and the two kept PVCs identical before and after (`walk/pvc-before.txt`, `walk/pvc-after.txt`: UIDs
`f065b7a4-535c-4ef1-868c-58f5afee4953` and `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, both created 2026-09-19T00:56:50Z).
The lab ran `4f4c070b08` before.

The scripts in `walk/` are copies of `reports/2026-09-24_rbac-provenance-and-review-counts/walk/` with their `source`
and `SHOTS` lines (and `WALK` in `lib.sh`) pointed at the scratch folder this session ran them from, plus one change:
the planted-grant script reads the refresh count it waits for from the pod's log instead of carrying 206 and 205
(`diff` the two folders to see exactly that). Two scripts are new: `config-source.sh`, the label census #354's premise
rests on, and `pod-log-excerpt.sh`, the pod's own refresh and finding lines, read once while the pod still lived.
Every number and time below is quoted from the `.out` files, and the wait budget from `evidence-347.sh`; the pictures
are the same captures the previous folder made, taken again on this deploy. The Logins capture the verification script
also takes belongs to #346, which is closed, and is not committed here.

**Times.** Every pod time below is the pod's own, UTC−4: its `TZ` is `America/New_York` (`walk/pod-log-excerpt.out`,
line 1), its log lines carry `-0400`, and the pages print EDT (`screenshots/347-access-granted.png`, "updated 21:24:49
EDT"). The lab host's clock, and the session log, are CDT, one hour behind; the Argo CD and PVC stamps are UTC.

| File | What it shows |
|---|---|
| `walk/release-244d4ab.log` | the deploy: build, push, the Argo CD sync to `244d4ab9c0`, the in-pod check (the image layer lines removed) |
| `walk/pvc-before.txt`, `walk/pvc-after.txt` | the two PVCs' UID, volume and creation time before and after the deploy — identical |
| `walk/verify-fixes.sh`, `.out` | #312's binding, the auditor tier with its negative control, the three pages as deployed |
| `walk/evidence-347.sh`, `.out` | a planted hand-made grant on a synced group: before, with it, after removing it |
| `walk/after-shared-rnd.out` | every cluster re-read once `shared-rnd`'s own refresh had run |
| `walk/config-source.sh`, `.out` | which bindings carry `rbac.ocp.io/config-source`, by value, and how many name a Group |
| `walk/pod-log-excerpt.sh`, `.out` | the pod's log: every binding refresh of the three CRC entries and every line naming the planted grant |
| `screenshots/347-access-granted.png` | the Access granted tiles with no unmanaged grant: 205 = 38 + 6 + 161 |
| `screenshots/347-access-granted-with-unmanaged.png` | the same tiles with the planted grant: 207 = 38 + 7 + 162 |
| `screenshots/347-unmanaged-section.png` | the planted grant in the page's Unmanaged section |
| `screenshots/347-overview-tile.png` | the Overview's `dashboard` tile: 7 bindings to review |
| `screenshots/347-kpi.png` | the KPI page as deployed, before the grant; the capture's 700-pixel clip ends at the Access posture labels, so its To review 18 is quoted from `walk/verify-fixes.out`, not read off the picture |
| `screenshots/347-kpi-posture-with-unmanaged.png` | the KPI page's Access posture with the grant: To review 21 = 18 unresolved · 0 dangling · 3 unmanaged |

## The chart's own auditor binding (the first three lines of #312's Definition of Done)

From `walk/verify-fixes.out`:

- `group-sync-dashboard-ra-b78c05817c9d` carries `config-source=group-sync-dashboard` (#350's label, chart 0.53.1).
- `oc auth can-i list clusterrolebindings` answers **yes** as a member of `app-ocp-rbac-groupsync-ns-auditor` and
  **no** without that group — the negative control. That is the question `visibility.adminSar` asks, so the auditor
  tier still passes it after the label.
- The new pod's first binding refresh, `refreshed 205 group bindings for dashboard` at 21:20:50 −0400 (01:20:50Z,
  one second before Argo CD reported Synced/Healthy), logged 0 `UNMANAGED GRANT DISCOVERED` lines for the `-ra-`
  binding.
- `/api/clusters` reports 0 unmanaged grants on every cluster; the Access granted tiles read 205 = 38 + 6 + 161, and
  the KPI page's To review 18 = 18 unresolved · 0 dangling · 0 unmanaged.

## #354 on a lab that uses the policy operator

#354 changes one thing: the chart's own label value no longer opens the `unmanaged` finding on a host with no policy
operator. The gate reads Group-subject bindings only. On this lab, 51 bindings carry `rbac.ocp.io/config-source` and 44
of them name a Group (`walk/config-source.out`). 43 of those belong to the policy operator — `baseline-nonprod-rbac` 26,
`baseline-cluster-rbac` 11, `baseline-prod-rbac` 3, and one each of `custom-cluster-rbac`, `bdp-oud-group-rbac` and
`trino-oud-group-rbac` — and the 44th is the chart's auditor binding, the only one of the chart's 8 labelled bindings
with a Group subject. So the gate is open with or without the chart's label, and #354 must change nothing here. It did
not: a hand-made grant is still reported, and every count is the one the previous folder measured on `4f4c070`.

| | Before | With the grant | After removing it |
|---|---|---|---|
| `dashboard` findings (API) | 205: ok 38, unresolved 6, unmanaged 0, built-in 161 | 207: ok 38, unresolved 6, **unmanaged 1**, built-in 162 | 205: ok 38, unresolved 6, unmanaged 0, built-in 161 |
| Access granted tiles | 205 = 38 + 6 + 161 | **207 = 38 + 7 + 162** | — |
| Overview, bindings to review | — | **7** on `dashboard`, `shared-qa` and `shared-rnd` | — |
| KPI, To review | 18 = 18 unresolved · 0 dangling · 0 unmanaged | **21 = 18 unresolved · 0 dangling · 3 unmanaged** | — |
| `/api/clusters`, unmanaged | 0 / 0 / 0 | 1 / 1 / 1 | 0 / 0 / 1, then 0 / 0 / 0 (`walk/after-shared-rnd.out`) |

The before figures are `walk/verify-fixes.out`'s; the rest are `walk/evidence-347.out`'s and `walk/after-shared-rnd.out`'s.

- The grant was a RoleBinding granting `view` to the synced group `app-ocp-rbac-groupsync-ns-auditor` in a namespace
  of its own, with no labels. The poller first logged it at 21:26:49 −0400 for `shared-rnd` and `shared-qa`, and at
  21:26:50 for `dashboard`, and re-announced it every refresh while it stood — seven `UNMANAGED GRANT DISCOVERED`
  lines in all (`walk/pod-log-excerpt.out`); the line `walk/evidence-347.out` quotes, at 21:36:49, is the last of
  them when the script read the log (`UNMANAGED GRANT DISCOVERED — … RoleBinding gsd-evidence-347/evidence-347-hand-made
  grants view to group …`).
- The tiles sum to the total in both states; the new namespace also adds one built-in binding, so the total rose by 2
  and the refresh after the grant read 207, not 206 (`refreshed 207 group bindings for dashboard` at 21:26:50,
  `walk/pod-log-excerpt.out`). The copied script's wait for 206 therefore matched nothing and ran its budget of 48 ×
  15 s (`walk/evidence-347.sh`); no number depends on it — the counts were read afterwards.
- `dashboard`, `shared-qa` and `shared-rnd` are the same CRC by design, so the one grant counts three times on the KPI
  page. After the namespace was deleted, the `dashboard` refresh at 21:37:49 −0400 read 205 while `shared-rnd` still
  showed 1; `shared-rnd`'s first refresh after the deletion, at 21:42:49, read 205 (`walk/pod-log-excerpt.out`), and
  the re-read at 01:49:23Z (21:49:23 −0400), after its 21:47:50 refresh, shows all three back at 0.

## What this closes

#312's Definition of Done, line by line: the label is on every RBAC object the chart renders (#350, chart 0.53.1,
held by `local-development/tests/test_chart_rbac_provenance.py`); the live cluster no longer reports the auditor
binding, with the auditor tier passing its `can-i` and its negative control (above); and the ServiceAccount-subject
asymmetry is decided as not intended. The decision is the operator's, recorded on #353 ("Exclusion is a decision, never
inferred") and in `docs/HANDOVER_2026-09-20.md`: the finding extends to ServiceAccount and User subjects, and a grant is
silenced only by the operator's `rbac.ocp.io/config-source` label or the exception annotation on its binding, never by
inference. Its specification, SPEC_U1, is pull request #357.
