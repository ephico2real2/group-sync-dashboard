# End-to-end walk — 2026-09-14, CRC, a NON-ADMINISTRATOR member of the biggest group

The companion to `../2026-09-14_e2e-walk/` (that one is kubeadmin, a wide-tier administrator). This
walk logs in as **jane.smith**, an LDAP user who is a member of `app-ssb-autobahnusers` — the largest
group on the reference cluster (8 members) — and who is **self-tier** in the dashboard: she cannot
`list clusterrolebindings` even with her 17 groups, which is the administrator gate
(`visibilityAdminSarResource: clusterrolebindings`, `visibilityAdminSarVerb: list`). So the dashboard
shows her only her own access, and refuses the administrator-only views.

Playwright through the real route, provider `ldap-local`. Run 2026-09-14T12:03:04Z → 12:03:51Z.

**Outcome: PASS.** 19 of 19 scripted steps in the main walk, 13 of 13 in the second pass. No report is
generated: reporting is an administrator-only feature and the Reports tab shows the refusal card, which
is the correct behaviour for this reader.

## What a self-tier member sees, versus the administrator walk

| Tab | jane.smith (self) | kubeadmin (admin) |
|---|---|---|
| Header pill | "Your view — jane.smith" | "Full view — you are seeing everything" |
| Cluster selector | "crc-local — your view" | "crc-local" |
| Users | **1 shown** (herself; "the cluster-wide user list is the administrator tier") | 62 shown |
| Groups | **17 shown** (only the groups she belongs to) | 66 shown |
| Access granted / RBAC policy / Namespace audit | narrowed to her own access path | the whole cluster |
| Reports | **refused**: "Withheld, not empty … For administrators only" | the catalogue, 11 reports |

Key screenshots: `screenshots/06-tab-users.png` (her single row), `screenshots/12-reports-refused.png`
(the refusal), `screenshots/04-tab-overview.png` (the "Your view" pill).

## What is here

| Path | What |
|---|---|
| `screenshots/NN-*.png` | the main walk: login, API probes, every tab, the Reports refusal |
| `screenshots/extra-*.png` | the second pass: the cluster selector, the light theme |
| `e2e-walk-nonadmin.pdf` | the walk document, self-tier view, with the pictures embedded |
| `results.json`, `results_extra.json`, `env.json`, `findings.json` | every step and its measurement |

## Findings (same two the administrator walk recorded)

- **#96** — selecting `prod-east` (a cluster removed from the configuration) renders a 404. Seen here too.
- **#97** — the report pod returned a 502 to an administrator-tier walk mid-session (preemption on the
  saturated node); it does not affect a self-tier reader, who never calls the report service.

## To repeat it

```sh
GSD_UI_PASSWORD='Ldap123!' KUBECONFIG=<cluster kubeconfig> \
  local-development/e2e-walk/run_walk.sh \
    --base https://group-sync-dashboard.apps-crc.testing \
    --login-user jane.smith --provider ldap-local --out /tmp/e2e/nonadmin
```

jane.smith's password is the repository's documented LDAP test credential
(`docs/LOGIN_CAPTURE_QUICKCHECK.md`). She is self-tier; kubeadmin and john.doe are wide-tier.
