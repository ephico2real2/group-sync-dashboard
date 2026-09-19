# Changelog

What each release changed, newest first. Two artefacts, two version lines (`docs/RELEASING.md`):
the application (`pyproject.toml`, deployed as `quay.io/ephico2real/group-sync-dashboard:<version>`)
and the chart (`Chart.yaml`, published to the Helm repository). A chart release that only moves
`appVersion` is listed under the application release it carries. The reasoning behind each change
lives next to the code and in the design and review records linked here. Changes merged since the
last release sit under `## Unreleased` until the release that carries them replaces that heading —
which `local-development/prepare-release.py` does when the release is cut.

## Unreleased

- **Artefact retention ages a run from its completion, not its request (#163).** `prune` keyed both of its time-sensitive decisions on the run id, which is minted at request time: a manual run that waited in the queue or rendered slowly arrived `done` with an id already older than `manual.days` and was deleted by the next prune, and "newest" for the caps ranked a fast late request above a slow early one. Both tiers now use one stamp, `retention_stamp` — `finished_at`, persisted to whole seconds by the worker, aged from the END of its second so rounding can only keep an artefact a moment longer; a run that never completed (refused by a full queue, or the pod died under it — `finished_at` has been in every manifest since the first release, so there is no legacy manifest) falls back to the id. Four tests fail on the old prune and pass on this one: a run requested five days ago but finished ten seconds ago survives; the manual cap keeps the most recently completed runs; scheduled keep-K holds the most recently completed report, not the latest request; a run finished on the cutoff second survives until the next second and one finished a second earlier goes at once. A fifth pins the fallback on the two runs that take it. Two more guard the way retention could stop silently — `_maybe_prune` swallows every exception, so one bad input would have switched it off for the whole store: a hand-edited `finished_at` of the wrong type is skipped like a malformed one, and a naive `now` from an injected clock is read as UTC. A queue refusal now stamps `finished_at` like every other terminal transition. `values.yaml` and the chart README state the semantic. Chart 0.34.1.

- **Home, the page every reader lands on (#158).** `#page=home` is the default route on every tier and the first tab; the Overview keeps its administrator-tier role, one click away (#169). Home answers one question — *what can I reach, and how?* — for the person asking and nobody else, so it is **self-scoped by definition**: an administrator sees their own access here, never everyone's, and the payload for a name is the same whichever tier resolves it apart from the `scope` field naming the tier. That dissolves the tier problem the Overview's refusal card left open rather than special-casing it: a narrowed reader's first impression of the product is no longer a refusal. One new endpoint, `GET /api/clusters/{cluster_id}/home`, composed from the reads the drill-downs already serve (the viewer's groups, the bindings those groups reach, the bindings naming them directly, their membership history) plus one new store method (`memberships_by_cluster`); the arithmetic behind every sentence is derived once server-side in `gsd/home.py`, so a number and its label change together. The page follows `docs/design/landing-access-mock.html`: the answer first (one sentence, its figures, its tags, and the cross-cluster line), then **What changed** — the reader's own membership history over 30 days, folded the way a person reads it (a group that changed five times in half an hour is one *flapping* line; a sync that added eleven groups at once is one line) — **Cluster-wide**, naming the roles a stronger one already covers ("three groups grant `edit` cluster-wide, and `admin` includes it by default — worth confirming before anyone relies on them"), **Namespaces you can reach**, **Direct grants** (the governance exception, shown to the person who holds it), and **Your groups**, the one that gives the top role first and the long tail folded. Every row is a whole-row button that drills into the page that already exists, so the keyboard reaches all of them. A cluster that does not treat your identity as its own says so in its own words rather than as an API error. Holds at 375 px.
  - **Review, pass 1 (Grok — `docs/REVIEW_home.md`).** A cluster whose policy is `hidden` is polled but never served, and the cross-cluster line walked the store's clusters rather than the served ones — so it named a cluster whose own endpoint 404s, counted its memberships and folded its history into what changed; the serving rule is one predicate now (`is_served`), with `require_cluster` its other caller, and the "does this cluster vouch for me" question is answered from configuration instead of a tier resolver, which on a `remote-sar` cluster was an HTTP SubjectAccessReview per cluster inside the read snapshot. Only a **ClusterRole** named `admin`, `edit` or `view` is ranked: a namespaced Role of that name is a different object, and ranking it let the page say "removing this would not change what you can do" about access nothing else grants. The cluster-wide foot speaks only of groups that exist (a role held by a direct grant read "0 groups grant edit cluster-wide"). "N more changes in the window" counts changes, not the cards they were folded into, and reads as one change at one. The 30-day window arrives with the payload instead of being a second constant in the page.
  - **Review, pass 2 (Codex, over the committed tree).** The sub-line called a count of namespaces "namespace grants" — the committed evidence capture reads it back — and the tag said "1 / 1 groups grant" at one; each cluster's history is read up to a cap, so the card now names the clusters whose counts are lower bounds instead of presenting them as complete; Home's own contrast is fixed where it is Home's (the rows carry secondary text, the hover wash drops to 6 %, and the amber pills sit on the card's surface rather than `--page-2`), with a guard over all ten theme × palette variants, while the shared tokens' own headroom stays #184's; and the policy sweep that proves every cluster endpoint answers `hidden` exactly as `unknown` now covers `home` and `namespaces`.
  - **Review, pass 1 (Codex, over the fixed tree).** The card no longer concludes that removing a covered role is safe: a role's name is not proof of its live rules, so it says the stronger one *includes it by default — worth confirming*. The cross-cluster pill was called `.stale`, which is the shell's refetch class (`opacity: 0.55` on whatever carries it), so it rendered at 2.27:1; renamed. A retention window of "forever" no longer claims older changes were pruned, and "two paths to the same grant" compares the role's kind as well as its name.
- **One lookup over the three kinds (#174).** `#page=lookup` — at rest, three doors (Groups, Users, Namespaces) carrying the lists' own counts and one line of state each, and a door opens its list; with text, the matches by kind as *N of M*, twelve per kind with "open the full list to see them", every hit a drill to its page and the matched substring marked. A **Find** box sits in the bar wherever no list has its own (the Overview, the RBAC policy, Logins, Usage and Reports tabs, a user's page): typing there opens the lookup once — one history entry, not one per keystroke — with the text carried, and typing on the lookup is a repaint. The AND contract of the list boxes holds across the three kinds (`alice zzz` finds nothing, `demo` finds a namespace by its label value). On a list page a line carries what was typed to the lookup — "search everything for demo" — and counts the other kinds only when this session already holds them (typing is a filter and issues no request; the users list is fetched only on its own tab); inside a group's member search, *search everything instead* does the same. The search is an extra door beside the lists and the tabs, never a replacement for them. The one data addition: `binding_count` on every `/groups` row (the Grants column), the same number the group's own detail lists, on every tier and under every state filter (`tests/test_groups_binding_count.py`). Holds at 375 px.
  - **Review, pass 1 (Grok, Codex, OB1 — `docs/REVIEW_lookup.md`).** A committed IME composition opens the lookup and a query of spaces is not a position change; the matched substring is marked on the raw text (a name with `&` painted as its entity, and the second word of a query marked inside the first's mark); the Users door counts logins as the Users tab does (a manual account is a row, not a login) and both doors name the one refusal, a missing identity; the lookup says when its counts are the reader's own; the empty state does not claim data an empty cluster does not have; the groups rows carry the state they were fetched under, so the lookup's whole list never paints under the Groups tab's filter nor counts in the also-line; every drill and door answers Enter and Space; the mark is bold, not a wash (the accent wash had put the link text at 3.4:1, under the sheet's 4.5:1 bar); "open the full list to see them" carries the query to that list's box; the doors' double chevron.
  - **Review, pass 2 (Grok, Codex — `docs/REVIEW_lookup.md`).** Overlapping terms mark the union ("ab bc" on "abc" had marked "ab" only): every match of every term is collected as a range, merged, and emitted once, so every occurrence is marked and marks never nest; the e2e walk visits the lookup (a page, not a tab, so `walk_tabs` never opened it); the drill's link colour on a zebra row measures 4.305:1 (light) / 4.375:1 (dark), lower on hover — the foundation's zebra and hover tokens on every table, routed to #184.
- **Namespaces are entities, not a filter (#167).** `GET /api/clusters/{cluster_id}/namespaces` — every namespace the poller sees, with its configured labels (`namespaceMetadataLabels`) and two counts (distinct groups bound in it, non-platform grants naming a person there; cluster-wide bindings counted once on the envelope), and `source` saying whether the namespace read was permitted, since a refused read cannot attest absence. `GET …/namespaces/{name}` — who reaches it and through which group, the grants naming a person, the cluster-wide grants that reach it too, its siblings under the first configured label, how many distinct people the paths add up to, and its history from `binding_event`. Self tier: the viewer's own paths only, refused before any lookup so the 403 for a namespace outside their view and for one that does not exist are byte-identical, `people` withheld. On the Namespace audit tab a **Namespaces** card lists every namespace (measured on CRC before: a 5-option select over the four that already carried a grant, out of 110) with a pattern box over the name **and the label values** — `demo` finds every demo namespace, `demo qa` narrows it, the AND contract of the other three boxes — and a row opens the namespace page: `#page=nsaudit&…&ns=<name>`, the third drill-down peer of a group and a user, `← all namespaces` and the one history stack; its group and person rows drill on. The Exposure ranking and the flat list's own filter stay as they were.
  - **Review, pass 1 (Grok, OB1, Codex — `docs/REVIEW_namespaces.md`).** A ClusterRoleBinding naming a person is on the namespace page and in `people` (`cluster_wide_grants` on the detail; the list's envelope already counted it and the page said nobody); the envelope's `cluster_wide_groups` counts distinct groups, as the column it twins does; a self-tier viewer whose own path is cluster-wide sees every namespace, the line saying the path is theirs — the reach rule the detail already applied — and the card's copy speaks of the viewer's own grants, never "every namespace the poller sees" or "no namespaces recorded"; a baseline history row reads "first observed", never "+ granted"; the namespace payloads are in the auto-refresh fingerprint; the list is not fetched on the namespace page; the cluster selector and the keyboard user-drill drop `ns` as they drop `group` and `user`; the namespace page offers no export of the audit table it does not show; the three store methods are declared on `StorageBackend` (the CI failure); and a tree-wide guard against merge markers, after the merge of #177 into this branch left a pair in this file.
  - **Review, pass 2 (Grok, OB1, Codex).** The list's switch is the reach itself (`cluster_wide_path`, a platform identity's binding included — the counts still leave platform identities out, and the card says which case it is); a baseline history row wears its own muted class, never the added colour; every drill activates from the keyboard through the click's own path (Enter on a group's name went nowhere). **From the deployed walk (CRC, 76ebaff21e):** the namespace page's cluster-wide line listed 54 bindings, 41 of them to virtual `system:` groups — every `via_groups` / `cluster_wide_groups` row now carries `is_platform`, virtual groups are badged in the table and folded on the line ("and 41 platform bindings to virtual groups (system:authenticated, system:nodes, …)"), and the list's cluster-wide group count leaves them out.
  - **Review, pass 3 (OB1's confirmation on the merged head).** The self-tier list follows the reach inside a namespace too (a platform identity's RoleBinding in a namespace lists that namespace, with the review's counts); the Via groups column and the page's count are groups of people — a virtual `system:` group is on the page, badged, never counted, so a namespace with zero in both can be a result again (on OpenShift every namespace carries `system:image-pullers`); a virtual group's default binding wears no hand-made badge (the findings tier it built-in); the cluster-wide fold names the most-bound virtual groups first and counts them; a group drill inside a group row on a user's page navigates once. The muted colour on a zebra row measures 4.45:1 — a token question on the foundation, #184.
- **Design-system foundation (#152) and the phone-width tab bar (#166).** Spacing (`--space-1…11`, the 2 px grid the sheet already sat on) and radius (`--radius-xs/sm/md/lg/pill/round`) scales join the type scale, every literal swept onto them at its current value — nothing moves; the nineteen off-ladder values (a control height, a glyph's asymmetry, 7-above/9-below the tab bar) stay literals with an `optical:` note the guard test requires. The three tokens the Users tab's chips had referenced through hard-coded fallbacks (`--line`, `--accent-soft`, `--warn`) exist now, in both themes, `--warn` held to the 4.5:1 text bar. The 92 inline `style=` attributes the page carried are classes on the token system (the one that stays is the render-time series colour). **Appearance (Auto / Light / Dark) and Colours (Default · Deuteranopia-safe · Protanopia-safe · Tritanopia-safe · High contrast)** are global shell state on `<html>` — set from `?mode=` / `?theme=` first (a shared link opens as the sender saw it), then the reader's stored choice, applied before the first paint; the controls sit in the static header where the 60 s filter repaint cannot reach them, and a change is never a navigation. The palettes are Okabe–Ito hues solved to the same contrast bars as the default tokens (every theme × palette pair is measured by `tests/test_accessibility.py`); they override only the status hues, never a page's own colour. Measured at 375 px on the live cluster before: the tab bar 676 px wide, the page 696, five of nine tabs unreachable; after: the bar wraps, every tab inside the viewport, `scrollWidth` 375 on every tab — the alerts card's rows, which pushed Overview to 477, wrap their detail too. Guards: inline styles may carry no literal, spacing and radius come from the ladders or carry their note, no raw colour outside the token blocks, the OS-dark palette twins match, `test_ui.py` sweeps every tab at 375 px. Dark is a screen theme — a print is light whatever the screen theme; the URL keeps `?mode` / `?theme` across Back, a hashless link and a reload; a junk URL value defers to the stored choice; below 520 px each header label sits above its select, on screen.
- **`binding_event`: the bindings' membership history (#167, #175 — `docs/DESIGN_binding_events.md`).** `rbac_group_binding` and `user_binding` are still replaced every refresh, but the refresh now first appends every (binding, subject) row that appeared or disappeared — a role change is one `removed` and one `added` — so a namespace has a history, the landing page's "what changed" can see the grant that changed what a person reaches, and #156 has an in-app bindings series. `GET /api/clusters/{cluster_id}/binding-changes` (self-scoped to the viewer and their groups), `gsd_binding_changes_total{cluster,change,subject_kind}` (counts only, pre-seeded), retention on `membershipEventsDays`, migration 13.
  - **The first-observation rule, for both tables.** Measured on CRC: `membership_event` held 76 / 87 / 5 `added` rows in one instant per cluster — each cluster's first observation, one of which the landing-page notes had read as "a bulk onboarding". A first observation is now written with `baseline = 1` on both `membership_event` and `binding_event` (rows kept, so `first_seen_at`, `original_first_seen_at` and the cliff window are unchanged); a consumer renders it as "first observed", never "added". Existing rows on an upgraded store keep `baseline = 0`. Whether a refresh is the first observation is decided by a per-(cluster, stream) marker, `observation_state` (migration 14; the same idempotent seed also runs at every open, so a store a marker-less build wrote to is marked at the next start), consumed once — empty or not — inside the refresh's transaction, not inferred from the rows: the inference was an off-by-one (an empty first poll made the next poll's real additions read as the baseline) and retention could reopen it (found in the review, Codex; `docs/REVIEW_binding_events.md`). The self-scoped `binding-changes` query binds the viewer's groups as one `json_each` parameter, so a viewer in more groups than SQLite's variable limit no longer gets a 500, and reads its two halves through the subject index (`UNION ALL`, not `OR`: measured 306 ms → 1.8 ms at 300k rows, OB1).
- **Cluster Overview relayout (#172).** The page follows the fleet, not the viewport: `data-density` on `<html>` from the served cluster count — ≤ 3 full (a tile per cluster with the seven figures, the API URL and the poll age), ≤ 8 medium, ≤ 24 compact, more a table row each — and past three the tiles sort worst-first, past eight the alerts card leads. A tile opens its cluster: `#page=overview&cluster=<id>` was already a position, so it needed a renderer, not a model — the scoped view carries that cluster's figures in full, its alerts only, its GroupSync CRs and its policy configs, with `← all clusters`; the bar's selector offers "all clusters" on the Overview and is the same position, so select and tile agree, and Back and Forward walk the one stack (the Overview tab opens the fleet). Alerts are paged eight at a time, worst-first — critical, warning, silenced last and dimmed naming what silenced them — with a kinds summary and page numbers that are view state, never a position. Status carries its consequence under the badge: an unreachable tile says every count is the last one observed; a `late` CR says one interval has passed and the next missed fire makes it overdue; `overdue` says every group it owns is frozen; a failing policy config says RBAC has quietly stopped reconciling. The three cards and every caveat of the contract survive in both views — asserted by a test over a seeded fleet of 2, 6, 14 and 40 clusters, not judged by eye. No new endpoint: the fleet's two tables are the per-cluster payloads fetched in parallel up to eight clusters; past that they live in the scoped view. The Policy tab's strip is the same card.
  - **Review, pass 1 (Grok, OB1, Codex — `docs/REVIEW_overview_relayout.md`).** A link to a retired cluster is the page's own detour, bar intact, not the generic error card (#96); the dense table's unreachable rows say `auth_failed`, not `unknown`; `unknown` on a CR names its cause (never synced, or an unusable schedule) and no longer blames the cluster; the fleet's absent-CRDs note needs a successful poll behind it; the opened cluster is a plain block with the tile's typography and no dead button; a cluster change from the fleet drops the previous cluster's payloads, so a tile paints first — its alerts and "Loading…" — and fetches after; the fleet tables repaint on the timer, name a cluster whose fetch failed, are not fetched behind a refusal card, and are not written by a superseded refresh; the alert kinds are chips; the RBAC policy tab's card is the pre-#172 card plus the consequence line. The self-tier Overview is #182.
  - **Review, pass 2 (Grok, OB1, Codex).** The opened cluster keeps its rail; a heading beside its count keeps the card's accent rail and the Policy tab's heading is the old markup exactly; an unusable schedule is named with or without a last sync; the selector names a retired id beside its detour. The compact tiles follow the mock (the operator's ruling: the mock's visuals) — the CR and policy figures return at full density and on the scoped view. The self-tier Overview stays as ruled in #169 (an open Overview is a server-side public projection, a separate change); the landing page every reader gets is #158.
  - **Review, pass 3 (OB1's confirmation on the merged head).** A tile's name carries no accent rail — the tile has its own status rail and its opened form has none (pass 2's wider selector had reached it); the e2e walk's cluster switch is a valid call again (Playwright's `arg` is keyword-only) and waits for the opened cluster to paint, not for the position to change — a guard binds every call in the walk scripts against the installed signature, since the walk only ever runs against a deployed cluster.
- **Two-tier report retention — a manual burst no longer evicts a scheduled report (R2, #149).** The artefact prune ran a single run-count cap that sliced **all** finished runs by id, so a burst of on-demand (manual) runs pushed a still-valid scheduled report past the cap and deleted it (`artifacts.py` `prune`). Retention is now two tiers, split by origin (`Run.schedule`): a **scheduled** run is kept while within the newest `keepPerSchedule` (default 2) per (schedule, cluster) **OR** younger than `days` (default 90), and is **exempt from the manual run-count cap**; a **manual** run is kept `days` (default 3) and at most `maxRuns` (default 500), whichever prunes first. A per-schedule `(keep, days)` override beats the globals. Queued/running runs are still never pruned. Fail-before/pass-after tests: 600 manual runs + one scheduled run → the scheduled run survives; newest-K-per-(schedule, cluster) survives past `days`; the per-schedule override is honoured.
  - **UPGRADE NOTE:** `reporting.retention.days` / `.maxRuns` become `reporting.retention.scheduled.{keepPerSchedule,days}` and `reporting.retention.manual.{days,maxRuns}` (env `GSD_REPORT_SCHEDULED_KEEP_PER_SCHEDULE`, `GSD_REPORT_SCHEDULED_RETENTION_DAYS`, `GSD_REPORT_MANUAL_RETENTION_DAYS`, `GSD_REPORT_MANUAL_RETENTION_MAX_RUNS`). Defaults keep the old 90-day scheduled window while giving manual runs a short 3-day life so on-demand runs cannot overfill the PVC.
## Application 0.24.0 — chart 0.33.0 — 2026-09-16

- **`priorityClassName` on both Deployments (#97).** The chart renders a pod `priorityClassName` when `priorityClassName` (dashboard) or `reporting.priorityClassName` (report) is set; both default empty, so nothing renders by default — and `priorityClassName` is omitted from the report pod's config checksum, so introducing the key does not roll that pod on upgrade. Measured on CRC (2026-09-14): the report pod was **Preempted 29x** in ~3h at **99% node CPU requests**, evicted by OLM `collect-profiles` (`openshift-user-critical`) and a marketplace catalog pod (`system-cluster-critical`); a PDB does not stop preemption, a priority does. Rendered only when set, mirroring the chart's existing `nodeSelector`/`tolerations`/`affinity` guards.

## Application 0.24.0 — chart 0.32.0 — 2026-09-16

- **Global reporting window (P4, `docs/DESIGN_reporting_selectors_snapshots_and_windows.md` §5; issue #131).** A new `reporting.window` block gates **automated** report runs — schedules, and any service-token caller — to a time-of-day range on chosen weekdays, in a chosen timezone. A human's manual run from the Reports tab is **never** gated (an operational rail, not access control). Off by default.
  - **Enforcement** is authoritative in the report service's `create_run`: an automated run outside the window is refused with **409 + `Retry-After`** before any Run is stored; `trigger.py` maps that 409 to **exit 0** (a *skip*, so the CronJob is not marked failed and does not retry into the window). The one worker rechecks against the run's `requested_at` before rendering — a run admitted just before the close still completes (end-of-window schedules are not flaky), but a run that never was in-window is failed.
  - **Origin is persisted** on each run — `viewer` (ticket), `schedule` (service token + a named schedule) or `service` (service token, no schedule) — and the gate keys on the origin, so a bare service `curl` with no `--schedule` is still treated as automated. The run manifest loader now defaults a missing `origin` to `viewer` and **tolerates unknown keys**, so a rollback that reads a newer manifest never drops the run from the index.
  - **The predicate** is half-open `[start, end)`, wrap-aware (a night window like `22:00–06:00` splits at midnight; the post-midnight part belongs to the previous day), timezone-localized, and validated **fail-closed** at both render (chart guard) and report-service startup — an enabled-but-malformed window never silently disables gating. The schedule CronJob's `spec.timeZone` is set to the window's zone so the cron and the window agree (GA on Kubernetes 1.27 / OpenShift ~4.14; pruned on older).
  - **Metrics:** `gsd_report_runs_outside_window_total{origin}` counts refusals (no names), and `gsd_report_schedule_last_success_timestamp{schedule}` (schedule names are operator config, not people) is the signal a monitor turns into "no success within its period" — so a wrong timezone cannot silently stop nightly evidence.
  - **Not in this PR (named follow-ups):** splitting the ticket-signing secret from the service bearer (the window is non-adversarial to a token holder, per §8); the snapshot manual/automatic mode + PVC sentinel (P3).

## Application 0.23.0 — chart 0.31.0 — 2026-09-16

- **Reporting-review fixes (Fable-high 24h review, Codex-verified — `docs/REVIEW_reporting_review_24h.md`).** Three defects the P1/P2 passes missed, each with a fail-before/pass-after test:
  - **F1 — the namespace-count preview no longer 500s on a pathologically nested `selectors`.** `json.loads` answers a deeply nested payload (`[[[…`, which fits inside h11's 16 KiB request line) with `RecursionError`, which is *not* a `ValueError` subclass, so it escaped `GET /report/api/namespace-count`'s catch and became a 500 — against the endpoint's "bad input shows nothing" contract. `RecursionError` now joins the caught set and the preview returns a null count.
  - **N3 — a pre-capture snapshot no longer reports an attested `0`.** A copy written before the label capture existed (schema < 12, still inside the rolling snapshot window) has no `cluster_namespace_label` table, so a selector or mnemonic selection expanded to the empty set and was reported as "0 namespaces match" — indistinguishable from a real empty match. The preview now returns null and a report run refuses with *"this snapshot carries no namespace-label capture (it predates the capture)"* for **both** the `selectors` and the deprecated `mnemonics` paths, via a new `Snapshot.selector_capture_present()`.
  - **F2 — a stale singular `reporting.namespaceSelector.label` is now refused at render.** The key was removed in 0.22.0, but Helm ignores unknown keys, so a value left behind in a 0.21 values file rendered cleanly while the selector silently vanished. The chart now fails the render for a *materially-set* `.label` (an empty/absent value stays an allowed no-op, since 0.21 shipped `label: ""` as its default) — the same fail-fast the chart applies to every other removed or misconfigured key.

## Application 0.22.0 — chart 0.30.0 — 2026-09-15

- **Remove the deprecated single-dimension `reporting.namespaceSelector.label`.** P2 (0.21.0) replaced the single selector key with the list `reporting.namespaceSelector.labels`, keeping the singular for one release. It is now gone: the `.label` values key, the `GSD_REPORT_NS_SELECTOR_LABEL` env, the report-service config field and its fallback, and the singular render guard are all removed — only `.labels` remains. The `values.yaml` comments now spell out that the selector keys are enterprise-specific (set them to your cluster's real namespace-metadata label keys, not the `company.net/*` examples) and that the dropdown VALUES are auto-discovered from the namespaces.
  - **UPGRADE NOTE (0.21.0 → 0.22.0):** a deployment that still set `reporting.namespaceSelector.label` must switch to `reporting.namespaceSelector.labels: [<key>]` — otherwise the namespace-access selector shows no dimensions (explicit names still work). `reporting.namespaceMetadata.labels` is unchanged.

## Application 0.21.0 — chart 0.29.0 — 2026-09-15

- **Multi-dimension namespace selector (P2).** The namespace-access report now selects on more than one captured metadata dimension at once — `company.net/mnemonic` **and** `company.net/app-environment` — combined AND across dimensions, OR within a dimension. `reporting.namespaceSelector.label` (a single key) becomes `reporting.namespaceSelector.labels` (an ordered list, each of which must be one of `reporting.namespaceMetadata.labels`); the singular is still honoured for one release when the list is empty. The Reports form renders one multi-select per dimension, and a debounced **preview count (#107)** shows how many namespaces the current selection expands to before a heavy run. Scheduled-report params now ride as one `--params-json` JSON object (Helm's `%v` cannot express a nested map), and the report service gains a read-only `GET /report/api/namespace-count` for the preview.
  - **UPGRADE NOTE:** no behaviour change for an existing single-label deployment — `reporting.namespaceSelector.label` keeps working. To select on two dimensions, set `reporting.namespaceSelector.labels: [company.net/mnemonic, company.net/app-environment]` (both must be in `reporting.namespaceMetadata.labels`). The deprecated `mnemonics` report parameter still works one release; prefer `selectors`.

## Application 0.20.0 — chart 0.28.0 — 2026-09-15

- **Docs: correct the chart README rbacAuditors default.** The README still listed `rbacAuditors.enabled` default as `false` / opt-in after 0.27.0 flipped it on; it now states the on-by-default behaviour, that the binding is inert until the named group has members, and that a populated group then reaches the wide report tier. Values behaviour is unchanged from 0.27.0 (review #121 follow-up, Cursor F1).

## Application 0.20.0 — chart 0.27.0 — 2026-09-15

- **Reporting auditors ON by default (chart).** `rbacAuditors.enabled` now defaults to `true`, per the chart's on-by-default rule: a default install binds the named auditor group (`app-ocp-rbac-groupsync-ns-auditor`, `createLocal: false` — bind-only) to a read-only audit ClusterRole, so an environment values file that does not mention it keeps the auditor gate rather than silently dropping it. The binding is inert where that group does not exist. Set `rbacAuditors.enabled: false` in an environment file to render nothing. Fixes the recurrence where a `helm upgrade -f <env>.yaml` dropped the auditor RBAC because the default was opt-in.
  - **UPGRADE NOTE (0.26.0 → 0.27.0):** on a cluster where the named group `app-ocp-rbac-groupsync-ns-auditor` already exists (an LDAP sync, say), this upgrade GRANTS its members cluster-wide read on users/groups/RBAC objects AND the dashboard's wide report tier — read-only and installer-conferred, but a new grant relative to 0.26.0. On any cluster where you do not want that, set `rbacAuditors.enabled: false` before upgrading. Where the group has no members (or does not exist) the binding is inert.

## Application 0.20.0 — chart 0.26.0 — 2026-09-14

- **Retire clusters removed from the configuration (#96).** A cluster dropped from `clusters:` (or one
  with `enabled: false`) no longer lingers in the UI as `ok` with frozen data and stale "overdue" alerts.
  The poller marks its stored row `enabled = 0` at the start of every cycle (a config change rolls the
  pod, so add/remove takes effect on the next start), and `/api/clusters`, `/api/whoami`, `/api/alerts`,
  `/metrics` and a direct `/api/clusters/{id}/…` (which 404s like an unknown id) all skip it (with no
  served cluster at all, `/api/alerts` fails closed to `scope: self` like `/api/whoami`). Its history and snapshot rows
  stay, so an already-generated report still reads them (docs/ACCESS_CONTROL.md §11). Supersedes the D2
  behaviour where a removed cluster resolved to `inherit` and stayed in the list.
- **Reporting: a mnemonic multi-select on the namespace-access form (#103, B3).** The report catalogue
  (`/report/api/reports`) now returns per-cluster `namespaceSelectors` — the configured selector label and
  its captured values, opened best-effort from the snapshot (a missing, unreadable or corrupt snapshot
  returns an empty map, never a 500 — the catalogue degrades, the Reports tab does not fault). The Reports
  form renders a checkable multi-select of those values ahead of the advanced
  explicit-names field, and a `readParamEl` helper serialises a `<select multiple>` as the full array (its
  `value` is only the first option). Completes Extension B: capture (0.22.0) → API (0.24.0) → GUI here.

## Application 0.19.0 — chart 0.25.0 — 2026-09-14

- **Reporting auditors: default the auditor group and guard the `createLocal` collision.** `values.yaml`
  now ships `rbacAuditors.groups` defaulting to `app-ocp-rbac-groupsync-ns-auditor` with
  `createLocal: false` (opt-in via `rbacAuditors.enabled`, still off). A render-time guard refuses
  `createLocal: true` for a group name that already exists under another owner (e.g. an LDAP sync),
  failing the install with the one-line remedy instead of Helm's ownership error and preventing the
  group-family sync from wedging (docs/TROUBLESHOOTING_auditor_groups.md,
  docs/FINDINGS_auditor_group_ldap_sync_interaction.md).

## Application 0.19.0 — chart 0.24.0 — 2026-09-14

- **Reporting: select a report's namespaces by the estate's grouping label.** The namespace-access
  report gains a `mnemonics` parameter that expands the configured `reporting.namespaceSelector.label`
  values (captured in 0.22.0) to their namespaces; the explicit-names path stays as the advanced
  fallback, and choosing both is refused. The report pod reads the selector key from
  `GSD_REPORT_NS_SELECTOR_LABEL`. No default-install change (docs/DESIGN_reporting_auditors_and_ns_selector.md §3).

## Application 0.19.0 — chart 0.23.0 — 2026-09-14

- **Reporting: opt-in auditor groups (chart).** A new `rbacAuditors` stanza binds a chosen group
  to a least-privilege, read-only ClusterRole (get/list on users, groups and the RBAC objects) so a
  non-developer can run reports and review identities and RBAC in OpenShift directly — no workload
  access, no Usage tab. Render guards ensure the role covers the report gate and refuse an unsafe
  configuration; the ClusterRoleBinding name hashes the group and the role (LDAP DNs are not DNS-1123,
  and roleRef is immutable). Off by default (docs/DESIGN_reporting_auditors_and_ns_selector.md §2).

## Application 0.19.0 — chart 0.22.0 — 2026-09-14

- **Reporting: namespace-metadata capture (chart + poller).** The poller now captures a bounded,
  configured set of Namespace labels (`reporting.namespaceMetadata.labels`, default off, needs
  `rbac.namespaces`) into a child table — the foundation for selecting a report's namespaces by the
  estate's grouping label. Default off; a default install renders and behaves exactly as before
  (docs/DESIGN_reporting_auditors_and_ns_selector.md §3).

## Application 0.19.0 — chart 0.21.0 — 2026-09-13

- **Per-cluster authorization for the multi-cluster case.** A reader is authenticated by the
  hosting cluster only, and the tier that cluster decided used to gate every cluster's rows. Two
  keys per `clusters[]` entry now say what a reader may see about each other cluster:
  `visibility` — `inherit` (the host decides), `self-only` (nobody is wide there), `hidden`
  (polled, never served through `/api`; 404 like an unknown id), `remote-sar` (that cluster's own
  RBAC decides through the same SubjectAccessReview on its own API with its own Group objects,
  cached per reader and cluster, every failure self) — and `identity` — `none` (the host's
  username is nobody there; person-scoped views answer 403, health still shows) or
  `same-as-host`. Defaults are the safe direction: the first enabled entry `inherit`/`same-as-host`,
  every other `self-only`/`none`. `/api/whoami` gains `visibility.clusters`, `/api/clusters` rows gain
  `visibility`, `/api/alerts` filters per cluster in that cluster's tier and reports the narrowest
  scope served; the cluster selector marks a narrowed cluster and the header pill follows the
  selected one. (`ACCESS_CONTROL.md` §11)
- **Upgrade note for multi-cluster installs:** remotes become `self-only` on chart 0.21.0. Set
  `clusters[].visibility: inherit` to keep the old view, deliberately. Helm never merges lists: when
  adding an entry with `--set`, pass every entry, `clusters[0]` included, or the render refuses the
  padded `null` by name.
- **Chart 0.21.0:** the two values, a render guard on their vocabulary (unknown policy,
  `hidden`/`remote-sar` on the host entry, `remote-sar` without `identity: same-as-host`), NOTES
  naming every cluster's effective policy, and the stale `docs/PLAN_oauth_proxy.md` reference in
  the `clusters` comment replaced.

- **Per-cluster authorization for the multi-cluster case: clusters[].visibility and clusters[].identity (D2).**

## Application 0.18.0 — chart 0.20.0 — 2026-09-06

- **Reporting, as a separate service.** A second pod on its own image (`group-sync-dashboard-report`,
  same appVersion) renders eleven evidence reports — the namespace access report, an access matrix,
  privileged access, binding findings, groups, users, login activity, dormant access, GroupSync
  health, a compliance snapshot and an access-certification pack — as self-contained HTML and
  PDF/A-2b (fpdf2, pure Python: the hardened base has no pango) from a read-only `VACUUM INTO` copy
  the dashboard's leader writes every 300 s under `/data/report`; never the live database. Reached
  through the oauth-proxy's path-routed `/report/` upstream; the dashboard decides the wide tier and
  mints a signed ticket (`GET /api/report/ticket`), the report service verifies it against a shared
  token and binds it to the proxy's identity. The dashboard's API stays GET-only: it PULLS
  `/report/api/usage` on the poll thread into `report_run` (migration 11, with `cluster_namespace`
  for `rbac.namespaces`) and serves it at the usage tier (`GET /api/dashboard/reports`, Usage tab).
  New Reports tab (wide tier; a named refusal below it). Chart `reporting.*` — **on by default**,
  refused where it cannot work (proxy off, emptyDir, replicas > 1, RWOP, no bindings grant); TLS via
  service-ca, a NetworkPolicy, an artefact PVC, optional schedules as CronJobs, two new alerts.
  `gsd_report_*` on the report service, `gsd_report_usage_pulls_total` on the dashboard.
  Also `rbac.namespaces` (off), so the namespace report can attest absence. The report image is
  published by the same run as the dashboard's and catalogued, signed and attested the same way
  (`DESIGN_supply_chain.md` D10; its SBOM is the artifact `sbom-report-<commit>`). The spec's body was applied with nineteen recorded deviations, chiefly fpdf2 2.8.8's required table heading style and the npm package version that carries DejaVu Sans. (spec `docs/specs/SPEC_C3_reporting_microservice.md`, design `DESIGN_reporting_service.md`; supersedes the parked namespace-report design)

## Application 0.17.0 — chart 0.19.0 — 2026-09-06

- **Login capture from the oauth-server audit log, as a second source.** `loginCapture.source:
  audit-log` reads `/var/log/oauth-server/audit.log` on the control-plane nodes through the API
  server's node proxy — what `oc adm node-logs --path=oauth-server/audit.log` does — at the
  default audit verbosity, so the `authLogLevel` Jobs and the OAuth roll they cause can be
  retired, and a first read backfills as far as the rotated files reach (bounded by
  `loginCapture.retentionDays`, drained at 8 MiB per node per cycle). Every attempt is a row of
  its kind: `credential` (the login form), `cli` (`oc login`'s challenging client) and, on
  request (`?kind=`), `session` (an existing session re-authorising to a client). Each row
  carries its `auditID`, so de-duplication is exact; an event that corresponds to a pod-log row
  already stored is linked to it rather than recorded beside it, and that row keeps its LDAP
  cause. The typed name is classified, not filtered: `identity_match` is the configured provider
  it resolves to through the User's Identity, or null — an unmatched failure stays a row and is
  counted on `/metrics` by outcome. Identities that are not people
  (`loginCapture.auditLog.ignoreIdentityPatterns`, default an LDAP bind service account's OU)
  are dropped on every decision. The audit log records no cause for a refusal beyond the HTTP
  status and, for CLI failures, "Authentication failed"; the Logins tab and the `/logins`
  envelope say so, and the envelope names its `source`. A resume is safe against rotation by a
  head fingerprint per cursor — measured on the reference cluster, a Range exactly at the file's
  size answers 416 like a Range past it, so the size alone cannot tell "nothing new" from
  "rotated". New outcome `provider_error`. Schema migration 10 (`login_event.source`, `audit_id`,
  `kind`, `client_id`, `identity_match`, `status_code`, `error_message`, `user_agent`;
  `login_audit_cursor`; `ocp_user.identities`). Metric families
  `gsd_login_capture_source_info{cluster,source}`,
  `gsd_login_capture_audit_settled_timestamp_seconds{cluster,node}` and
  `gsd_login_capture_unmatched_total{cluster,outcome}`; the stalled alert and its gauge are
  untouched. (spec `specs/SPEC_D1_audit_log_login_capture.md`, design `DESIGN_login_capture.md`)
- **Chart 0.19.0:** `loginCapture.source` and `loginCapture.auditLog.{nodeSelector,nodeNames,
  providers,ignoreIdentityPatterns}`. With `audit-log` a ClusterRole on `get nodes/proxy` (+
  `list nodes`, or `resourceNames`) renders instead of the namespaced pod-log Role — read-only,
  cluster-wide, off by default for its breadth, which the values comment states.
  `source=audit-log` with `authLogLevel.enabled=true` is refused: the chart will not roll the
  OAuth server as a side effect of a read setting. Default renders are unchanged.

## Application 0.16.0 — chart 0.18.0 — 2026-09-06

- **Idle timeout with a countdown, as an off-by-default module.** After `session.idleTimeout.minutes`
  of no pointer, keyboard or tab-visibility activity the session is signed out; the last
  `warningSeconds` of that window are a `role=dialog` countdown (focus trapped
  with `inert`, Escape or Enter to stay, forced-colors border), and at zero the page removes its data
  and sends the browser to the proxy's `sign_out`, which clears the cookie. Enforced by the proxy,
  modelled by the page: nothing is persisted, activity in one tab defers every tab of that browser,
  and the 60 s poll is suspended while the countdown is up so an unattended tab cannot keep a
  session alive. The absolute cap stays the guarantee for a tab that never gets there. `/api/whoami`
  `session` gains `idle_timeout`. (design `DESIGN_session_and_signout.md`, spec
  `docs/specs/SPEC_C4_idle_timeout.md`)
- **Chart 0.18.0:** `session.idleTimeout.{enabled,minutes,warningSeconds}`; refused without the proxy,
  and refused when the window is not shorter than `oauthProxy.cookie.expire`.

## Chart 0.17.0 — application 0.15.0 — 2026-09-05

- **Off-volume backup CronJob, `backup.offsite` (chart, off by default).** The other half of
  `config.backup`: a CronJob mounts the data claim read-only, picks the newest `gsd-*.db`,
  streams it to a second claim (`destination.type: pvc`, no credentials) or stages it for an
  operator-supplied S3 CLI image (`destination.type: s3`, credentials only from a Secret you
  create), writes a `.sha256` sidecar, runs `PRAGMA integrity_check` on the copy, prunes the
  destination to `keep`, and fails loudly otherwise. Under `ReadWriteOnce` the Job is pinned to
  the dashboard's node; `ReadWriteOncePod` is refused at render. Two alerts on
  `kube_cronjob_status_last_successful_time` when `monitoring.prometheusRule` is on. Restore and
  verify: `docs/RUNBOOK_backup_restore.md`. (spec `docs/specs/SPEC_B1_offsite_backup.md`)

- **Every pushed image is signed and attested, and every published chart package is attested.**
  The build script records the digest the registry acknowledged and makes the release aliases as
  server-side copies of that manifest, read back and compared, so one digest is every tag. Two new
  jobs follow the push: an SBOM (Syft 1.51.1, SPDX JSON, a workflow artifact) and a keyless cosign
  signature under GitHub's OIDC identity with the SBOM attached and SLSA provenance in the
  repository's attestation store — each read back before the run is green. `helm.yaml` attests the
  `.tgz` chart-releaser uploaded, for new versions only. No key anywhere; `helm verify` is
  deliberately not supported. `helm/chart-releaser-action` is pinned by commit like every other
  action, and a test now holds that rule. Variables `SUPPLY_CHAIN_SBOM` and `SUPPLY_CHAIN_SIGNING`
  turn the modules off. (design `DESIGN_supply_chain.md`)


## Application 0.15.0 — chart 0.16.0 — 2026-09-05

- **Users tab: provider allow-list and first login from Identity objects.** `config.users.providers` (empty = all)
  lists only people who logged in through the named identity providers, applied when the tab is read;
  the API carries `providers_filter` and the page says "Showing providers: …"; the never-logged-in line
  is not narrowed. `rbac.identities` (default false — a grant, so off under the 0.14.0 rule) lets the
  poller read Identity objects, and each row's `first_login_at` becomes the Identity's creation
  time with `first_login_source: identity` (the first login for `mappingMethod: claim`/`add`; an
  administrator's create for `lookup`, which the page states rather than calling the time "exact");
  without the grant it stays the User's creation time,
  labelled `user` on the wire and "approx." on the page; `identities_source` (`ok`, `forbidden`,
  `off`, `pending`) says why. Schema migration 9 (`ocp_user.identity_created_at`,
  `ocp_identity_status`). The export's users projection gains `first_login_source`. (spec
  `docs/specs/SPEC_C2_users_tab_providers_identities.md`)
- **Chart:** `rbac.identities` (false) renders `get,list` on `identities.user.openshift.io` and refuses
  without `rbac.users`; `config.users.providers` → `usersProviders`, `rbac.identities` →
  `identitiesReadEnabled`.

## Application 0.14.0 — chart 0.15.0 — 2026-09-05

- **CSV and JSON export on every table.** Users, Groups, Access granted, Namespace audit and
  Logins gain Export buttons in the filter bar. The file is built in the browser from the rows the
  server served this reader — after the page's own filter and sort, at the reader's own tier — so it
  can never hold a row the tier withheld. RFC 4180 with a UTF-8 BOM (spreadsheets), JSON without one
  (RFC 8259), a formula-looking cell prefixed with an apostrophe, the file named for the cluster, tab,
  tier and UTC time, and `_partial` in the name plus `truncated` in the JSON when the page was a cut
  of a larger set. Not recorded in Usage: an export makes no request, and the activity table counts
  interactions per day, not actions. `/api/version` gains `features`. (design `DESIGN_export.md`,
  spec `docs/specs/SPEC_C1_table_export.md`)
- **Chart:** `ui.export.enabled` (default true) → `uiExportEnabled`.

## Chart 0.14.0 — application 0.13.0 — 2026-09-05

- **Every switch is on by default unless it costs something the chart cannot grant.** The
  operator's rule for the chart: a boolean defaults to `true` unless the switch needs RBAC beyond a
  namespaced read, a credential, a second image or a cluster-wide write. Flipped: `podDisruptionBudget.enabled`
  (harmless with `maxUnavailable: 1`), `loginCapture.enabled` (inert until the login lines exist),
  and `oauthProxy.apiTokenAccess.enabled` (the proxy's SubjectAccessReview still gates every
  token). Kept off, each with its reason in `values.yaml`: `securityContext.allowPrivilegeEscalation`,
  `trustedCA.existingConfigMap.enabled`, `ingress.enabled`, `authLogLevel.manage`/`.enabled` — the
  OAuth Debug level is being retired in favour of the oauth-server audit log as the source of login
  lines — `oauthProxy.skipProviderButton`, an operator's product choice (people log in from the
  OpenShift login screen, which the explicit button gives them), `monitoring.serviceMonitor.enabled`
  / `monitoring.prometheusRule.enabled`, because the reference cluster runs no Prometheus (rendering
  with both on was verified — lint, template, server-side dry run against the CRDs, a live deploy —
  before the default went back, so enabling them is a values change and nothing else), and
  `oauthProxy.requestLogging`, which the second review pass showed writes the complete request URI,
  the OAuth callback's authorization code included, to the pod log. The Grafana dashboard keeps
  following the ServiceMonitor; the reference values no longer force it on. An upgrade that relied on a `false` default now needs the value set explicitly.
- **The hook Job pods no longer carry the workload's selector labels.** Found while validating the
  on-by-default budget on the reference cluster: the `authLogLevel` Job pods matched the
  PodDisruptionBudget's selector, the disruption controller failed the budget (`SyncFailed: jobs.batch
  does not implement the scale subresource`, `DisruptionAllowed=False`) and every drain would have
  been blocked; the same labels made the Service match a running hook pod. The hook pods keep
  `app.kubernetes.io/name`, `instance` and `component` and drop the `app` label;
  `tests/test_chart_pdb.py` holds both selectors to the Deployment's pod template alone.

## Chart 0.13.0 — application 0.13.0 — 2026-09-05

- **A Grafana dashboard ships with the chart.** `monitoring.grafanaDashboard` renders
  `dashboards/group-sync-dashboard.json` as a ConfigMap labelled `grafana_dashboard: "1"` — the
  sidecar convention; grafana-operator v5 reads it through `configMapRef` (recipe in the chart
  README). Default `""` follows `monitoring.serviceMonitor.enabled`. Every panel expression is held
  to the collector's declared families, the thresholds to `values.yaml`'s defaults, and the rendered
  JSON to the file byte-for-byte, all by `tests/test_chart_grafana_dashboard.py`.
  (spec `docs/specs/SPEC_B3_grafana_dashboard.md`)

## Application 0.13.0 — chart 0.12.0 — 2026-09-05

- **Retention for the accumulated history, `config.retention`.** `membershipEventsDays: 0`
  (forever) and `syncEventsDays: 730` by default; the leader prunes after the cycle's backup, never
  before one has succeeded in this process's life and never at all while `config.backup` is off,
  5,000 rows per table per cycle, counted into `gsd_retention_rows_deleted_total{table}`. Four
  history responses gain `retention: {window_days, retained_since}` and the page says "history
  retained since …" where a timeline begins at the cut. First start after upgrade builds the
  `sync_event_by_time` index. **Restoring an old backup to read its history: set both windows to
  `0` first** — the first successful backup in the new process's life releases the prune.
  (spec `docs/specs/SPEC_B2_history_retention.md`)

## Application 0.12.0 — chart 0.11.0 — 2026-09-05

- **Group-count cliff alert, with read-only silencing.** A group whose membership fell by
  `config.alerts.groupCountCliff.dropRatio` (0.5) from at least `minMembers` (10) within
  `windowHours` (24) is alert kind `group_count_cliff`, severity warning — reconstructed from the
  membership events the poll already records, so no new table. Silence it read-only with the Group
  annotation `groupsync-dashboard.io/silence-group-count-cliff` (`true` or `until=YYYY-MM-DD`) or the
  chart's `silence` globs; a silenced cliff is still reported as `group_count_cliff_silenced`, dimmed
  on the Overview, counted under its own kind on `/metrics`, and never pages. New
  `GroupSyncGroupCountCliff` rule (the twelfth). `/api/alerts` rows gain `silenced` and
  `silenced_by`; group rows gain `cliff_silence`; schema migration 8. Both cliff kinds are withheld
  at the self tier. Default on, and the README's "needs a floor as well as a ratio" is answered by
  the floor. (spec `docs/specs/SPEC_B4_group_count_cliff.md`)

- **The browser tests run in CI.** `tests/test_ui.py` — the real app on a free port, a seeded store,
  Playwright against it — now runs in a `ui` job of its own on every pull request and push, on the
  interpreter the image ships, with the Playwright package pinned so the Chromium build is too.
  Screenshots and traces are kept as a workflow artifact only when a test fails. Repository
  variable `CI_UI_TESTS=false` turns the job off and leaves the interpreter matrix exactly as it
  was; `test_live_smoke.py` still runs nowhere but against a cluster you name.
- **A release is one command.** `local-development/prepare-release.py --app X.Y.Z "reason"` (or
  `--chart A.B.C`) moves the four version fields together, writes the `Chart.yaml` history line and
  the application paragraph, turns this `## Unreleased` heading into the release heading, runs
  `tests/test_chart_versions.py`, and commits to `release/…` with the operator as sole author;
  `--pr` opens the pull request. It refuses a dirty tree, a version that does not advance, and a
  branch that exists. Nothing writes to `main`, as before.

## Application 0.11.0 — chart 0.10.0 — 2026-09-04

- **The image runs on Red Hat Hardened Images.** `hi/python:3.14` to run and `hi/python:3.14-builder`
  to build, on the floating `3.14` tags so every build takes Red Hat's latest 3.14. The runtime base
  has no shell, so a third stage assembles one — bash (and `sh`), `curl` on `libcurl-minimal`, `jq`,
  and the coreutils shims `cat`, `ls`, `base64`, `mkdir`, `chgrp`, `chmod`, `rm` — with exactly the
  twelve libraries the runtime lacks, measured by `ldd`, and copies it in. Every in-pod command in
  the docs and the release scripts' stamp check still work. SQLite is 3.53.4 (UBI: 3.34.1); zoneinfo
  ships, so the tzdata reinstall is gone; 186 MB against 227. The declared user is the base's
  65532 rather than UBI's 1001 — the distroless convention, numeric, and on OpenShift never the
  UID the process runs as anyway. The recipe is written to be read, with its two Python steps
  as repository scripts; `Containerfile.annotated` is the same instructions with the full
  reasoning beside each step, held identical by a test, and `Containerfile.ubi` is the previous
  recipe — both built by nothing. (#52; design `DESIGN_hardened_image.md`)
- **Three packages uninstalled from the base, files and RPM records together.** `libuuid`, the one
  HIGH-rated package in the base (four util-linux advisories of 2026-09-02, all in mount code the
  image does not ship, no fixed build from Red Hat yet) — nothing needs it, and `uuid` falls back to
  pure Python, proven on every build. And pip, twice (`python3-pip` and the `python-pip-wheel`
  seed), an installer nothing needs, whose vendored msgpack and setuptools were the only Python
  findings. The file list comes from the RPM database itself, so files and records cannot diverge.
  The shipped image scans at zero CRITICAL, zero HIGH, zero fixable at any severity. (#52;
  `image-vulnerability-scan.md`)
- **CI scans with Grype, not Trivy.** Measured: Trivy does not recognise Hummingbird OS and scans
  no OS package; Grype reads the RPM database and Red Hat's advisories for it. The gate runs on the
  shipped image and on the pack stage, fails only on fixable HIGH, and a separate step shows the
  full inventory. (#52)
- **Chart 0.10.0: curl in the pod trusts what the dashboard trusts.** curl reads the image's own
  system bundle and none of the application's settings, so an `oc exec … curl` against a
  corporate-signed URL failed where the application verified it. Now a `.curlrc` ConfigMap,
  mounted at `/etc/curl` and found through `CURL_HOME`, names the injected bundle as `cacert`
  (when `trustedCA.injected` is on) and OpenSSL's hashed directory as `capath`; and a new
  `trustedCA.existingConfigMap.subjectHash` mounts the manual CA into that directory as
  `<hash>.0`, Hummingbird's "Approach 2", so curl, urllib and the dashboard's fallback context all
  trust it. A file rather than `CURL_CA_BUNDLE` and `SSL_CERT_DIR`, because curl ignores the
  second whenever the first is set (measured on curl 7.76 and 8.22), and only the curl tool reads
  the file, so the dashboard's own TLS cannot be touched by it. Every claim measured in a pod;
  `TUTORIAL_ca_trust_hashed_directory.md` teaches the mechanism. Also `appVersion`, and the
  `timezone` and SQLite comments now say what the hardened base ships. (#52)

## Application 0.10.2 — chart 0.9.4 — 2026-09-04

- **Access granted, from the second-pass review:** when the reader's tier is indeterminate (a
  whoami that fails on a later cycle) the tab fails closed to Loading, as the Overview does, instead
  of painting a cached payload of either tier; the Reaches column's logged-in count is null until
  the User objects have been read at least once, rather than a confident zero on a fresh install or
  the cycle after migration 7; a row that carries no tier renders its group name as plain text,
  closing the last way into the 404 that #49 removed. (review record `REVIEW_second_pass_2026-09-04.md`)
- **Chart 0.9.3:** the chart README's values table only — the row for a `redirectMode` key that no
  longer exists. Docs for the whole day's state, and this changelog, landed with it. (#50)

## Application 0.10.1 — chart 0.9.2 — 2026-09-04

- **Access granted:** a group name is a drill only where a group page can answer. Built-in
  virtual groups never have a Group object and unresolved bindings name groups that never existed,
  so those names drilled to a 404 that blamed a deletion which never happened. They render as plain
  text now; dangling and granted groups keep the drill. (#49)

## Application 0.10.0 — chart 0.9.1 — 2026-09-03

- **Access granted opens on what was granted.** The faults (dangling, unresolved, unmanaged) stay on
  top because nothing on the cluster reports them; the Granted section follows; the built-in
  majority stays one filter away. It used to open on the faults alone. (#48)
- **Every row says who it reaches.** `member_count` — the named Group's own count — and
  `logged_in_count` — members with a `User` that has an identity, the 0.9.0 definition of a login.
  Both null when no Group object exists, so 0 means the group exists and grants nobody today, and is
  highlighted. Opt-in on the store query and pre-grouped, so the metrics scrape, the poller and
  `/api/clusters` pay nothing for it; `/api/clusters` also stops materialising every binding row to
  count them. (#48)
- **Filter and sort.** A type-to-match box like the Groups and Users tabs, over group, role,
  namespace and binding name, narrowing every section with the cluster-wide counts untouched; sortable
  column headers on the shared table; truncation disclosed when the page is cut. (#48)
- **A narrowed reader sees their own grants.** The findings endpoint still refuses them; the tab reads
  their own `/users/{name}` and shows the bindings that reach them through their groups, with the
  group named. The tab re-decides its tier from the whoami that just arrived, so a tier change
  mid-session paints the right view on the next cycle. (#48; review record
  `REVIEW_access_granted_reach.md`)

## Application 0.9.0 — chart 0.9.0 — 2026-09-03

- **The Users tab counts the people who have logged in.** Rows are OpenShift `User` objects, which
  the cluster creates at first login and never before; group membership is an attribute of a row
  and may be zero. Synced members who have never logged in are one line, by count, with the names a
  click away. Per row: first login, identity provider(s), last captured login, display name.
  Headline KPIs, chips by membership and provider, a banner naming `rbac.users` when the read is
  refused, and the age of the last successful read. `/users` pages properly (`total`, `offset`) and
  carries `logged_in_total` beside `total` so a manual account with no identity is listed but not
  counted as a login. Schema migration 7 rebuilds `ocp_user`. (#47; design
  `DESIGN_users_tab_logins.md`, review record `REVIEW_users_tab_logins.md`)
- **Fix:** `Store.login_without_access` was defined twice and only the undocumented copy ran; an
  AST guard test now fails the build on any repeated method name in the package. (#46)
- **Chart 0.9.0:** `appVersion` moves; the `rbac.users` grant is now the Users tab's source rather
  than a decoration of it, so turning it off costs that tab's rows (the tab says so by name) instead
  of display names. No template output changes.

## Chart 0.8.0 — application 0.8.1 — 2026-09-03

- **A Route the router names, by default.** `route.enabled` (default true) emits an OpenShift Route
  with `spec.subdomain: <fullname>`, so the hostname is `<fullname>.<apps domain>` — the release name,
  never the namespace — with no cluster lookup at render time. The ServiceAccount's OAuth callback
  becomes a reference to that Route by name. That is what lets ArgoCD, Flux and any `helm template`
  renderer deploy the chart with no per-cluster value: the Ingress path's apps-domain lookup could
  never succeed there and the render was refused. `ingress.enabled` (default false) keeps the
  Ingress for plain Kubernetes, unchanged. A host set deliberately (`route.host`, or a carried-over
  `ingress.host`) is used as given. (#45; design `DESIGN_route_exposure.md`, review record
  `REVIEW_route_exposure.md`)
- **`argocd.enabled` defaults to true.** It adds `argocd.argoproj.io/sync-options` annotations and
  nothing else, which Kubernetes ignores outside Argo, so an Application needs no chart value at
  all. (#45)
- On upgrade from 0.7.1 the Ingress and its generated Route are replaced by the chart's Route on the
  same hostname; sessions, data and RBAC are untouched. Measured on the reference cluster.
