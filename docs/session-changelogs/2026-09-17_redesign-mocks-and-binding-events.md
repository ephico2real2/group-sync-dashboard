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
