# Session change log — group-sync-dashboard, 2026-09-17 → 2026-09-17

What one working session did, in the order it did it, with the time of each commit taken from
`git log` (author time, America/Chicago) and the review, deployment and test facts from the commands
the session ran. Every "measured" claim is one the session ran a command for; nothing below is
recalled from memory alone.

Outcome in one line: **…**

| | Before the session | After |
|---|---|---|
| Application / chart | 0.24.0 / 0.33.0 (`docs/CHANGELOG.md`, 2026-09-16) | … |
| main | `54ecde7` (2026-09-16 20:05, PR #150 merged) | … |
| `docs/design/` | 2 files: the README and the reporting-status mock (`git ls-tree 54ecde7`) | … |
| PRs opened today (gh) | — | #154, #164, #168, #176, #177 |
| Issues filed today (gh) | — | #152–#175 |

---

## Part 1 — the redesign, driven from the live dashboard first (2026-09-17, 14:31 → 22:04)

### Mocks and records — branch `docs/landing-access-mock` (PR #164), `docs/drilldown-mock` (PR #168)

- The operator's mandate: drive the live app with Playwright before designing. The drill-down mock
  (drilldown-mock.html, on PR #168's branch) adopts the measured navigation model — hash positions, one history
  stack, contextual back labels, multi-word AND search proven by `alice zzz` → 0 results — and the
  Cluster Overview relayout (cluster-overview-mock.html, same branch) uses the real four-state status
  vocabulary traced through `local-development/gsd/state.py`, with density tiers by fleet size and paged alerts.
- **Found by the render check**: the KPI mock invented CPU motion with `Math.random` on a "live values"
  page and showed the mock cluster's sync as ok while the live store said overdue 3d — both corrected
  (`ec6532c`). The Reports-page mock had a stray `<style>` pair from the grafted form mock that put its
  CSS outside the stylesheet — removed (`77f381a`).
- Records committed on that branch: data-requirements.md, inventory-2026-09-17.md and
  kyverno-research-2026-09-17.md under the design directory; the feature contract gained the Cluster Overview and the
  persistent shell (Refresh, Sign out, settings, Appearance and Colour) as must-not-remove (`a719aba`).
- Issues #156–#175 filed from the audit; #171 is the tracking issue with the implementation order.

## Part 2 — binding_event: the bindings' membership history (2026-09-17, 21:40 → )

### Implementation — commit `1f55cb1`, PR #177

- Two rulings from the data audit implemented on the backend: namespace history (#167) and "who else
  is in my groups" (#158 G). `rbac_group_binding` / `user_binding` are still replaced each refresh, but
  the refresh first appends a `binding_event` per (binding, subject) that appeared or disappeared;
  `membership_event` and `binding_event` both carry a first-observation `baseline` flag (#175).
  `GET /api/clusters/{cluster_id}/binding-changes` (self-scoped), `gsd_binding_changes_total` pre-seeded
  with nameless labels, migration 13, retention shared with `membershipEventsDays`.
- Deployed to CRC as `0.24.0-1f55cb14ad` after a first attempt exited 125 (`oc whoami -t` has no token
  under the client-certificate kubeconfig — recorded in memory). **Measured live**: two RoleBindings created at
  02:52:06Z → three `added` rows at 02:57:18Z (the platform's `system:image-pullers` included), namespace
  deleted → three matching `removed` rows at 03:03:18Z; counters symmetric.

### Review pass 1 applied — commit `c59fddd` (2026-09-17 23:0x), PR #177

- **Found by Codex (gpt-5.6-sol, xhigh), C4 REFUTED, accepted and fixed**: an empty first poll left no rows, so the
  second poll's real additions were flagged `baseline = 1` (`first_empty=0 event_rows=0 second_nonempty=1
  second_baseline=1`). The first observation is now a consumed marker — `observation_state(cluster_id, stream)`,
  **migration 14** rather than Codex's rewrite of 13, because CRC already carried `user_version 13`.
- **Found by Codex, volunteered, accepted**: one SQL placeholder per viewer group → "too many SQL variables" past
  `SQLITE_LIMIT_VARIABLE_NUMBER`; one `json_each(?)` parameter now; the test forces the limit to 16.
- **Found by Cursor (Grok 4.6)**: two stale "two tables" comments and four preservation tests — **applied**; its
  accepted debt on the empty first observation is superseded by the marker.
- Measured: touched files 193 passed; full suite **3073 passed, 17 skipped** (`--ignore=tests/test_ui.py`); citations
  test 891 passed; CRC upgrade 13→14 wrote **0** baseline rows over 407 / 95 / 184 current rows; nine markers seeded;
  the route answers `count: 6, baseline_rows: 0`. Record: `docs/REVIEW_binding_events.md`.
- Process: Codex's own "leave the scratch directory empty" step deleted the launcher's `tee` target it shared —
  recovered byte-identical (25,265 bytes) from the harness capture; the second pass gives each reviewer its own
  directory and forbids deleting files it did not create.

### The OB1 skill (PR #176, branch `skill-ob1-reviewer`) — commits `c31e6a9`, `dff6d4c`, `30dc24e`

- The operator's branch conflicted with main (cut before `a3b4b07`); resolved keeping OB1, main's background-wakeup
  paragraph, Grok's ZDR tag and the demand-the-snippet sentence — PR #176 reads MERGEABLE (blocked only on approval).
- **The operator**: "It shouldn't be review only. It also produces the code fix for any suggestions" → OB1 hands back
  the full fix and its failing/passing test in its report; "Dont drop the cursor fable role" → the Cursor Fable rows
  stay; OB1 fills the role while Cursor's usage limit is hit (measured: `ActionRequiredError: You've hit your usage
  limit`), and Cursor Fable resumes when the quota resets.
