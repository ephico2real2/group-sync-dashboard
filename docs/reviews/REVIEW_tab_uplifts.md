# Review record — the trailing tabs at the Namespace-audit bar (#153, PR #225)

Branch `feat/153-tab-uplifts`, base `main` (`af5c269`). Three seats on head `43f1ee2`: Cursor Grok 4.6 (ask
mode, from source), Codex GPT-5.6 xhigh (a `git archive` of the head with the venv; the guards run; Chromium
could not launch in its sandbox) and OB3 (Opus 5, pinned clones of the head and the base; 346k tokens, 35 min;
deep on M2 with four seeded servers including a never-polled cluster, M3 with call counts at every chokepoint for
four drill paths, M4+M7 with chip line boxes at six widths and contrast read from pixels on composited rows in two
modes and five palettes). Eight claims (M1–M8) plus "not asked". CI on `06ef60e` found
what the reviewers could not run: an existing test read the row's LAST chip for the identity caveat's title,
and the new provider chip was last — the assertion reads the status cell now, and the provider chip carries
a title of its own.

## Claims × decision

| # | Claim | Grok | Codex | OB3 | Decision |
|---|---|---|---|---|---|
| M1 | Behaviour preservation; every contract item still rendered | CONFIRMED | CONFIRMED (hunks in four renderers only; no request added or removed) | CONFIRMED (requests, controls and `innerText` diffed base vs head per page: four `BUTTON.drill` and two Groups insertions, nothing else) | Holds. |
| M2 | The Groups KPIs: the cluster's counts, constant under the filter, hidden at self and when never polled | REFUTED — the never-polled hide did not exist: `/api/clusters` sends integer zeros for a cluster with `status` null, and the tiles painted 0 / 0 / 0 | REFUTED, the same (measured `{'status': None, 'group_count': 0, …}`) | REFUTED on the never-polled part, measured on a seeded never-polled cluster (`status None … group_count 0` → tiles 0/0/0 beside an Overview tile saying "not the same as zero"); the other four parts held, including the state fetch HELD mid-flight | **Accepted** — hidden while `status` is null (the three-valued contract `reachable` uses) and unless all three counts are numbers; the test forces the state and asserts the tiles gone, then back. |
| M3 | The keyboard drill: one bubbling click path, no double navigation | CONFIRMED | CONFIRMED (`stopPropagation()` at the row handler) | CONFIRMED (Enter, Space, button click, row click: `navigate 1 / refresh 1 / push 1`, the same five fetches; keyboard reach 0 → 4 focusables per row) | Holds. |
| M4 | The rails only when non-zero, on the named tiles; the chips | CONFIRMED | CONFIRMED | PLAUSIBLE — the rails exact; the chip: `ldap-local` was a TWO-LINE pill at every width (the base's text broke at the hyphen too; the chip made the break a control) | **OB3's chip finding accepted**: `.chip { white-space: nowrap }` — measured safe on every chip site (Logins' sixteen, Users, the KPI page) at 375 and 1280. |
| M5 | The Usage footnote byte-for-byte, split with three leads | PLAUSIBLE (no base to diff against in ask mode) | REFUTED — the word diff shows `These are not logins either: the` → `<strong>Not logins.</strong> The` | REFUTED — five words gone, the split inside a sentence, and the leads were the sentences' own first words | First pass: accepted on the fact, the snippet rejected (the lead carried the clause). **On OB3's row, reversed**: the contract's "keep the words" is the later operator ruling, and the split sat inside a sentence — the base's words restored with the sentence's own first words as the lead (`These are not logins either:`); the test holds the footnote to the base's words exactly. |
| M6 | The tests pin what they claim | REFUTED — the overflow line never set 375 px (the phone-width sweep already holds it); unpinned: the never-polled and self-tier hides, the rails at zero, the Groups table inside `.scroll-x` at 375, the footnote | REFUTED, the same four gaps | REFUTED — mutants: unconditional rails passed all four; Empty counted from rows passed the filter test; no self-tier / never-polled test; overflow at 1280; and the head broke `TestIdentityFirstLogin` (`.last` chip) | **Accepted** — five tests added on the Grok/Codex pass, three more on OB3's (the Users and Access-granted rails at zero, every Groups tile under each state, the one-line chip at 1280 and 375); the chips asserted by name. OB3's mutants named exactly what the first four missed. |
| M7 | The guards; no new class | PLAUSIBLE (could not run) | CONFIRMED (526 passed) | CONFIRMED (526; chip text ≥ 13.2:1 on every composited row; the rail 3.0019:1 light/default, the graphical bar) | Holds. |
| M8 | RBAC policy, Logins, the Overview cards need nothing | CONFIRMED, two leftovers: the Logins provider cell is a mono dump where Users now has chips; the Overview `.tk` figures twin the Groups tiles in another visual language (out of scope by the keep-as-is ruling) | CONFIRMED | PLAUSIBLE — the Logins provider cell; and a severity disagreement: the Overview tile paints "Bindings to review" critical while the new rail was warning for the same sum | **Accepted** the Logins chip (in this PR's inventory); the Overview figures stay by the ruling (noted). "Gated, no access" keeps no rail — the page's own note says it is not automatically a problem. **OB3's severity disagreement accepted**: the rail carries the worst finding present — critical with a dangling binding (the dangling badge's and the Overview tile's severity), warning with unresolved only. |
| N1 | (both) the owner-dot sentence: `crSlot()` indexes the provider label in the sorted, flattened provider list, not the CR's position | REFUTED | REFUTED | true in substance (the slot is the provider KEY's position in the cluster's sorted, flattened list, measured under every filter and at self) | **Accepted**: the sentence says what the code does; a test holds it. |
| N2 | (both) the mock's uppercase heads, `.note`/`.foot` bands and `.b` badges not taken | optional — #152 forbade uppercase KPI labels; the bar uses `.kpi`/`.filterbar-note`/`.chip`/`.badge` | optional — the contract requires the meaning, not the class names | none required by the issue's text; the `.b` provider badge on Logins the one whose absence left an inconsistency | Holds; recorded. |

## Re-validation

- The three review tests (the never-polled hide, the owner note, the Logins chip) fail on the page without
  the fixes and pass with them; `TestTabUplifts` 9 passed; the full UI file 466 passed after CI's catch.
- OB3's three tests (the base's words, the rails at zero with the severity, the one-line chip) fail on the head
  without the fixes and pass with them; `TestTabUplifts` 12 + `TestIdentityFirstLogin` 3 passed; guards 526.
- The full suite and the CRC walk after the pass: the PR's comment.
