# Home — the page every reader lands on (#158)

Evidence for issue #158, captured 2026-09-18 at commit `c5cd511` on branch `feat/home` (PR #186).
Application `0.24.0-c5cd5112ec`, chart `0.33.0`, on CRC (`crc-local`) with the mock cluster beside it.

This folder is what the page DID on that day, at that commit, for those readers — not what it is meant to
do. Every claim in the Definition of Done below names the picture that shows it.

| File | What it shows | Captured against |
|---|---|---|
| `01-home-crc-1440.png` | Home as `kubeadmin` on the live cluster: cluster-wide `cluster-admin`, 13 namespaces with 12 already covered by it, 14 direct grants, no synced groups, and the cross-cluster line naming the mock cluster | CRC, the deployed image |
| `02-home-crc-375.png` | The same page at 375 px, top to bottom, with no sideways scroll (halved from the 8910 px original so it opens in a browser) | CRC, the deployed image |
| `03-tier-self-home.png` | A **narrowed** reader (`alice`, pill "Your view — alice") landing on Home and seeing her own access — no refusal | the seeded app, restrictions on |
| `04-tier-self-overview-refusal.png` | The same reader one click away on the Overview: the administrator-tier refusal, unchanged by this issue | the seeded app, restrictions on |
| `05-tier-admin-home.png` | An **administrator** (`root`, pill "Full view — you are seeing everything") landing on Home and seeing **their own** access — "Nothing on crc-local names you", because root is in no synced group | the seeded app, restrictions on |
| `06-tier-admin-overview.png` | The same administrator on the Overview, with the cluster hero: what they see about the cluster is still there, one click away | the seeded app, restrictions on |
| `07-home-dark.png` | Home in the dark theme | the seeded app |

The tier pair (03–06) is captured against the seeded application rather than CRC because a narrowed reader
on the lab needs the pod's own loopback (a bearer token always lands on the wide view), and the seeded app
carries both personas with the same code the cluster is running.

## Definition of done, against the evidence

- [x] **Renders for every tier, showing only the viewer's own access; an administrator sees their own
      access here, not everyone's.** `03` and `05`: the narrowed reader and the administrator land on the
      same page shape, each showing themselves. The administrator's Home says *"Nothing on crc-local names
      you"* while their Overview (`06`) shows the whole cluster — which is the claim, in one pair of
      pictures. Pinned by `test_an_administrator_sees_their_own_access_here_not_everyones`, which diffs the
      two tier bodies, and `test_an_administrator_sees_their_own_access_here_not_the_clusters`.
- [x] **Cluster switching re-scopes correctly, with labels and values changing together.** Every number is
      derived once, server-side, in `local-development/gsd/home.py`, so a figure and the sentence around it
      come from one payload. `test_the_cluster_selector_rescopes_and_a_cluster_that_vouches_for_nobody_says_so`.
- [x] **Drill-through to Groups / Access-granted / Namespace views works and preserves scope.**
      `test_a_group_row_drills_to_that_group_and_back_returns_to_home`; every row is a whole-row `<button>`,
      so the keyboard reaches it (`test_every_row_is_a_button_the_keyboard_reaches`).
- [x] **Direct grants are distinguished from group-derived access.** `01`: the *Direct grants* card, and
      every namespace row reached that way reads "granted to you directly".
- [x] **No cross-user or cross-cluster aggregate is reachable — asserted by a test, not by inspection.**
      `test_direct_grants_are_the_viewers_own_and_nobody_elses` (another person is seeded and asserted
      absent), `test_a_hidden_cluster_is_not_elsewhere` and
      `test_the_cross_cluster_loop_consults_no_tier_resolver`.
- [x] **Accessibility and type-scale tests green; `prefers-reduced-motion` honoured.** The CSS guards pass;
      the page adds no motion. Contrast findings on shared tokens are routed to #184, which is where that
      fix belongs.
- [x] **Adversarial review.** Grok 4.6 and Codex (GPT-5.6, xhigh): seven findings, all applied with
      fail-before/pass-after tests. Record: `../../docs/REVIEW_home.md`.
- [x] **CRC verification as an administrator** — `01`, `02`. As a narrowed persona: the seeded pair `03`/`04`
      stands in, per the note above.

Measured on this commit: browser suite **372 passed**, non-browser **3420 passed, 13 skipped**, Home API
tests **16 passed**; CI green on every job.
