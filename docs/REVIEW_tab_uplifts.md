# Review record — the trailing tabs at the Namespace-audit bar (#153, PR #225)

Branch `feat/153-tab-uplifts`, base `main` (`af5c269`). Three seats on head `43f1ee2`: Cursor Grok 4.6 (ask
mode, from source), Codex GPT-5.6 xhigh (a `git archive` of the head with the venv; the guards run; Chromium
could not launch in its sandbox) and OB3 (Opus 5, a pinned clone — report pending at this record's first
commit; its column is added when it lands). Eight claims (M1–M8) plus "not asked". CI on `06ef60e` found
what the reviewers could not run: an existing test read the row's LAST chip for the identity caveat's title,
and the new provider chip was last — the assertion reads the status cell now, and the provider chip carries
a title of its own.

## Claims × decision

| # | Claim | Grok | Codex | Decision |
|---|---|---|---|---|
| M1 | Behaviour preservation; every contract item still rendered | CONFIRMED | CONFIRMED (hunks in four renderers only; no request added or removed) | Holds. |
| M2 | The Groups KPIs: the cluster's counts, constant under the filter, hidden at self and when never polled | REFUTED — the never-polled hide did not exist: `/api/clusters` sends integer zeros for a cluster with `status` null, and the tiles painted 0 / 0 / 0 | REFUTED, the same (measured `{'status': None, 'group_count': 0, …}`) | **Accepted** — hidden while `status` is null (the three-valued contract `reachable` uses) and unless all three counts are numbers; the test forces the state and asserts the tiles gone, then back. |
| M3 | The keyboard drill: one bubbling click path, no double navigation | CONFIRMED | CONFIRMED (`stopPropagation()` at the row handler) | Holds. |
| M4 | The rails only when non-zero, on the named tiles; the chips | CONFIRMED | CONFIRMED | Holds. |
| M5 | The Usage footnote byte-for-byte, split with three leads | PLAUSIBLE (no base to diff against in ask mode) | REFUTED — the word diff shows `These are not logins either: the` → `<strong>Not logins.</strong> The` | **Accepted on the fact, snippet rejected**: the lead carries the clause's whole meaning; Codex's "Not logins. These are not logins either" says it twice. The test pins the three thoughts and the sentences that carry the contract's content (the UTC bucket, "not one HTTP request", the oauth-server's log). |
| M6 | The tests pin what they claim | REFUTED — the overflow line never set 375 px (the phone-width sweep already holds it); unpinned: the never-polled and self-tier hides, the rails at zero, the Groups table inside `.scroll-x` at 375, the footnote | REFUTED, the same four gaps | **Accepted** — five tests added: the never-polled and self-tier hides with the rails at zero, the Groups table inside its container at 375 px, the footnote's three thoughts (on the fixture that records usage — the plain one runs without the proxy), the owner note, the Logins chip; the chips asserted by name (`ldap-local`, `developer`). |
| M7 | The guards; no new class | PLAUSIBLE (could not run) | CONFIRMED (526 passed) | Holds. |
| M8 | RBAC policy, Logins, the Overview cards need nothing | CONFIRMED, two leftovers: the Logins provider cell is a mono dump where Users now has chips; the Overview `.tk` figures twin the Groups tiles in another visual language (out of scope by the keep-as-is ruling) | CONFIRMED | **Accepted** the Logins chip (in this PR's inventory); the Overview figures stay by the ruling (noted). "Gated, no access" keeps no rail — the page's own note says it is not automatically a problem. |
| N1 | (both) the owner-dot sentence: `crSlot()` indexes the provider label in the sorted, flattened provider list, not the CR's position | REFUTED | REFUTED | **Accepted**: the sentence says what the code does; a test holds it. |
| N2 | (both) the mock's uppercase heads, `.note`/`.foot` bands and `.b` badges not taken | optional — #152 forbade uppercase KPI labels; the bar uses `.kpi`/`.filterbar-note`/`.chip`/`.badge` | optional — the contract requires the meaning, not the class names | Holds; recorded. |

## Re-validation

- The three review tests (the never-polled hide, the owner note, the Logins chip) fail on the page without
  the fixes and pass with them; `TestTabUplifts` 9 passed; the full UI file 466 passed after CI's catch.
- The full suite and the CRC walk after the pass: the PR's comment.
