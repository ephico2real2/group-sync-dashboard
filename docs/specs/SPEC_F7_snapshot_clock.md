# SPEC F7 — the reports' clock is the snapshot's: windows end at the snapshot's stamp, sealed sections hold no poll or read instant, and the form starts with HTML ticked (#592, #607, #593)

| | |
|---|---|
| Programme | After Epic F (#386, released as application 5.0.0): the two decisions it left open, #592 (SPEC_F1's open question 1) and #593 (SPEC_F2's), both decided by the operator on 2026-10-04, and #607, the same class of defect found on the lab the same day. One spec, one application MINOR |
| Batch | F — reports |
| Release | — (post-programme; its own PR and its own review) |
| Version on release | app 5.1.0, chart 0.70.2 |
| Version note | Image content (`local-development/gsd/reporting/**` and `local-development/gsd/static/index.html`, both under `publish.yml`'s `local-development/gsd/**`), so the next application MINOR after main's 5.0.0, 5.1.0 (`docs/RELEASING.md`: "MINOR per merged issue changing the image"). The chart moves only because `appVersion` moves: no template, default, value or RBAC change, so a PATCH, 0.70.1 to 0.70.2, as 0.70.1 was for 5.0.0 and 0.66.5 to 0.66.7 were for 4.1.0 to 4.3.0 (`charts/group-sync-dashboard/Chart.yaml#MAJOR and MINOR for behaviour`). W1 stays `specified` at chart 0.71.0, above both 0.70.1 and 0.70.2, so it does not move. Read on `4e5a708d` (application 5.0.0, chart 0.70.1). A release that lands first makes the version blocks (36 to 40) fail their check; the implementing pull request corrects them here first |
| Issue | [#592](https://github.com/ephico2real2/group-sync-dashboard/issues/592) |
| Status | specified |
| Source | OB1-lite's research and specification of 2026-10-04 (implementer seat), from the three issues and their decision comments (`gh issue view 592`, `607`, `593` with `--comments`), the code read on `4e5a708d`, and the repository's venv (Python 3.14). No cluster was touched: the operator held the lab. §7's 40 blocks were generated from a working copy and proved against a copy of `4e5a708d` with this spec in it (§4.3) |

## How to read this spec

The plain point first. A report is read from a **snapshot**: a copy of the dashboard's database, taken every five
minutes by default and named by the instant it was taken (its **stamp**). Five reports also look at a clock: "attempts in the
last 30 days", "members with no login in 90 days", "is this GroupSync overdue". Today that clock is the moment the
report is *generated*, which can be minutes or hours after the snapshot. So a report can say "to 14:00" about data
that stops at 13:55, and two runs over one snapshot can disagree. The operator decided (#592): the clock is the
snapshot's stamp. Page one's "Generated at" still says when the report was generated, because that describes the run.

Two smaller changes ride with it. #607: `compliance-snapshot` puts the last poll's instant and the login-capture read's
instant inside its sealed sections, so a diff of two snapshots always shows a change even when nothing changed; those
instants stay on page one and leave the sealed sections (`login-activity`'s "Last log read" is the same class). #593:
the Reports form starts with only HTML ticked.

§1 is the mandate. §2 is the research: the sources, the code, the measurements. §2a lists the alternatives. §3 is the
design, one rule per subsection. §4 maps each Definition-of-Done item to a test and records the proof. §5 is the lab
check. §6 is what a reader sees. §7 is the change as implementation blocks (`docs/specs/README.md`, "Implementation
blocks"), applied with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_F7_snapshot_clock.md . --apply

Line citations into the code at `4e5a708d` are file:line in plain text inside tables and quoted output; prose cites
`path#anchor`.

## Orchestrator's notes

1. **Three issues, one index row.** The index has one issue column; this row names #592, the decision that sets the
   design. #607 and #593 are named in the title, the CHANGELOG entry and every block that implements them. #592 is
   above every issue in the rows before it (H1 is #542), so the row needs no exclusion in
   `local-development/tests/test_specs_index.py`'s rising-number assert; the index count moves from 58 to 59.
2. **Correction to the brief: not every one of the five reports' sha256 changes.** The brief and #592's "cost of yes"
   say the five reports' hashes change once. Measured over one snapshot, main against this spec (§2.3, table 3):
   `compliance-snapshot` and `login-activity` change at every clock (their sealed rows change); `groupsync-health`
   changes at every clock too, because its caveat's words change ("at generation time" becomes "at the snapshot's
   stamp"); `groups` and `dormant-access` keep their hash unless a membership change or a last login falls between
   the snapshot's stamp and the generation time. The CHANGELOG entry (Block 40) says exactly that. The other six
   reports' hashes are unchanged at every clock measured.
3. **The test seed's snapshot is stamped at the seed's `NOW`.** `Store.snapshot` names the copy by the wall clock
   (local-development/gsd/store.py:1778), while the seed's rows are dated from a fixed `NOW` of 2026-09-06 12:00 UTC
   (local-development/tests/reporting_seed.py:17). Once the windows end at the stamp, the seed's rows would slide out
   of them as the calendar moves. Measured (§2.3, the time experiment): with the stamp 40 days later, two catalogue
   tests fail (`login-activity`'s window no longer holds the seeded attempts); 400 days later, a third. Block 20
   renames the seed's copy to `NOW` (or to an instant the test names), so the suite reads the same data on any day.
   The two tests that write two copies from one store give the second one its own instant (Blocks 25 and 29).
4. **`login-activity` across two snapshots cannot read "No change", and that is correct.** #607 keeps the window's
   rows out of its scope ("Must not change: `login-activity`'s window ('To', #592)"). With #592 the window's `From`
   and `To` are the snapshot's stamp minus N days and the stamp itself, so two snapshots five minutes apart count
   attempts over two different periods, and the diff says so: the Window block shows `From` and `To` moved and nothing
   else (T607-2). "Last log read" leaves the sealed Window because it is the read cycle's instant, the #607 class
   (measured on main: it is the only row a diff of two snapshots shows for `login-activity`, §2.3).
5. **The hash still covers both instants.** "Last poll" is in `sealed_provenance`
   (local-development/gsd/reporting/model.py:77) and the read instant is in the coverage's `login_capture_note`
   (local-development/gsd/reporting/catalogue/common.py:291), both inside the hash, for every report. A diff compares
   neither (local-development/gsd/reporting/diff.py:31-32, :75-88). This spec moves the instants out of the sealed
   *sections*, which a diff compares, as #589 did for access-certification's "Data as of"; it does not change what the
   hash covers. A new snapshot is still new evidence and hashes differently (T270-6 unchanged in substance).
6. **The form's default is fixed, not configured (#593).** The operator's decision is "Start tick with html", with
   fixed defaults: the form does not follow `reporting.formats.manual`. No value key, no chart change.
7. **The browser tests that assumed PDF ticked.** The whole browser suite passed with the new default and only two
   existing tests changed for it (§2.3): `test_generate_label_follows_the_format_boxes`, which asserted the old default
   (measured failing on main's page, §4.3), and `test_the_administrator_generates_a_report_and_downloads_the_pdf`,
   which clicks a PDF artefact the new default does not ask for (read in the code; not run without its block). Three other tests untick PDF before generating (test_ui.py:11781, :11844, :11893);
   they still pass and still say what they mean (no PDF), so they are left alone.
   `test_a_ticked_csv_box_survives_a_repaint_of_the_form` passed either way, but its "an unticked PDF survives a
   repaint" became the default and proved nothing; it now flips every box from its default (Block 34).
8. **Dates.** Blocks 36 and 37 date the chart's history lines 2026-10-04; the implementing pull request writes its
   own date.

Open questions: none. The three issues are decided; §2a records the choices this spec made inside them.

## 1. The mandate, and what is out of scope

**#592 (decided yes, 2026-10-04).** "Report windows and clock-based checks end at the snapshot's stamp, not the
generation time." The operator's reason: *"I dont wanna users to think that the data is not accurate."* Scope: the
five builders that read `ctx.now` for data (`login-activity`, `groups`, `dormant-access`, `groupsync-health`,
`compliance-snapshot`). "Generated at" on page one stays the generation time.

**#607.** `compliance-snapshot` seals the "Last poll" instant (Key figures, Sync pipeline) and the login-capture note's
"last read" instant (the Coverage table), so a diff across snapshots never reads "No change". Keep the instants on
page one; keep in the sealed sections only what does not change with the snapshot clock: the poll's status, the
capture's state and its `started_at`. Check `login-activity`'s "Last log read" (said in the issue to be read from the
code only, not measured). Must not change: page one's rows; what the diff compares, other than these instants; the
other reports' seals; `login-activity`'s window (#592's).

**#593 (decided 2026-10-04: "Start tick with html").** The Reports form starts with only HTML ticked; PDF and CSV start
unticked; JSON is always written; the reader's choices still survive a repaint; fixed defaults, not
`reporting.formats.manual`. A browser test that the form opens reading "Generate HTML · JSON".

**Out of scope:** the page one rows and words; what the diff compares (`COVERAGE_FIELDS` and the sealed sections);
`sealed_provenance` and the coverage dict (both still sealed, for every report); the other six reports' seals; the
PDF, HTML and CSV renderers; the stored runs (never rewritten); `reporting.formats.*` and every other value; the
snapshot's cadence.

## 2. Research, measured

### 2.1 Primary sources

| Source | What it says | What this spec takes |
|---|---|---|
| #592, the operator's decision comment (2026-10-04) | yes; the five builders; "Generated at" stays; ships with #607 and #593 as one spec and one MINOR | §3.1 to §3.3 |
| #592's body | five builders read `ctx.now`; measured: `login-activity` differs at +2 min, `groupsync-health` and `compliance-snapshot` at +2 h, `dormant-access` at a cutoff edge; cost: a one-time hash change and the seed's `NOW` | re-measured in §2.3 (table 1); the hash cost corrected (Orchestrator's notes 2) |
| #607's body | the two sealed instants, measured on `mock-trusted` (`blocks_changed: 2`); "Last log read" read from the code only; the change; Must not change; the DoD | §3.4; "Last log read" measured in §2.3 (table 2) |
| #593, the operator's decision comment (2026-10-04) | `reportWant: { pdf: true, ... }` becomes `{ pdf: false, html: true, csv: false }`; the form opens reading "Generate HTML · JSON"; fixed defaults | §3.5 |
| SPEC_F1, Orchestrator's notes 1 and open question 1 | the windows were left on the generation clock on purpose, pending this decision | §3.1 |
| #589 (commit `f34658fe`, `access_certification.py`) | the precedent: the duplicate "Data as of" row left the sealed Campaign list; the stamp stayed on page one and in `sealed_provenance`; one hash change, named in the CHANGELOG | §3.4 follows it |

### 2.2 The code, read on `4e5a708d`

| Fact | Where |
|---|---|
| The run context carries `now` (a datetime) and `snapshot_stamp` (a string) | local-development/gsd/reporting/catalogue/common.py:100, :104 |
| The stamp is ISO-8601 UTC with microseconds, from the snapshot's file name; the age parses it with `%Y-%m-%dT%H:%M:%S.%fZ` | local-development/gsd/reporting/snapshot.py:65, :69-70, :98 |
| A run and a preview build the context with `now` from the service's clock and `snapshot_stamp=info.stamp` | local-development/gsd/reporting/runs.py:180-185; local-development/gsd/reporting/server.py:535-539 |
| `window_start(now, days)` is `iso(now - timedelta(days=days))` | local-development/gsd/reporting/catalogue/common.py:255-256 |
| `compute_state(last_sync, schedule, now, grace, ...)` | local-development/gsd/state.py:78 |
| The five builders read `ctx.now` for data | login_activity.py:37, :56; groups.py:24; dormant_access.py:52; groupsync_health.py:24, :32; compliance_snapshot.py:31, :32 (all under local-development/gsd/reporting/catalogue/) |
| groupsync-health's caveat says "at generation time" | local-development/gsd/reporting/catalogue/groupsync_health.py:51 |
| Every window query has a lower bound only (`>= since`): nothing in a snapshot is later than its stamp, so a window that ends at the stamp counts everything the snapshot holds | local-development/gsd/reporting/snapshot.py:494, :500, :583, :597, :641 |
| Page one: "Generated at" from `ctx.now`; "Last poll" with its instant; the login-capture note with "(last read …)" | local-development/gsd/reporting/catalogue/common.py:353, :358, :291, :375 |
| compliance-snapshot's sealed "Last poll" row and its WHEN answer built from the capture note | local-development/gsd/reporting/catalogue/compliance_snapshot.py:52, :62 |
| login-activity's sealed Window: From, To (`ctx.now`), Watching since, Last log read, Login gate | local-development/gsd/reporting/catalogue/login_activity.py:56-58 |
| The diff compares four coverage conclusions (not the notes) and every block of the sealed sections | local-development/gsd/reporting/diff.py:31-32, :70-88 |
| `sealed_provenance` holds the stamp, the schema and the last poll (instant, status, message); the coverage is sealed | local-development/gsd/reporting/model.py:77, :136-138 |
| The snapshot copy is named by the wall clock | local-development/gsd/store.py:1778 |
| The test seed's rows are dated from `NOW = 2026-09-06 12:00 UTC`; `write_snapshot` returns the wall-clock copy | local-development/tests/reporting_seed.py:17, :85-88 |
| The form's default boxes; the label; the boxes; the POST's formats | local-development/gsd/static/index.html:192, :2937-2938, :2951-2953, :4270-4273 |
| The tests that pin today's behaviour: `CLOCK_ANCHORED`, `CLOCK_DERIVED`, `_other_run`, T270-1, T270-2, T270-6, T270-10; `CLOCK_MOVED`, T108-2, #589's test, T108-3; the label test and the PDF download walk | local-development/tests/test_report_seal.py:34-39, :74-79, :86-112, :166-183, :247-259; local-development/tests/test_report_diff.py:24-31, :94-99, :102-119, :121-127; local-development/tests/test_ui.py:11856-11880, :8774-8803 |

### 2.3 The measurements

Every command ran on 2026-10-04 with the repository's venv (`PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD` from
`local-development`), on copies of `4e5a708d` ("main") and of main with this spec's blocks applied ("new"). The
scripts are the seal suite's own `_run` over the seed's snapshot.

**Table 1 — #592 on main: two runs over ONE snapshot, generated apart** (`m592.py`; the parameters are the narrowest
that put a seeded row on a window's edge):

    gap=        0:02:00 login-activity       params={}                     same_sha=False differs_in=['Summary/Window']
    gap=        0:02:00 groups               params={'window_days': 1}     same_sha=True differs_in=[]
    gap=        0:02:00 dormant-access       params={'dormant_days': 1}    same_sha=False differs_in=['Dormant: no successful login in 1 days/Members who have logged in before, not recently']
    gap=        0:02:00 groupsync-health     params={}                     same_sha=True differs_in=[]
    gap=        0:02:00 compliance-snapshot  params={}                     same_sha=True differs_in=[]
    gap=        2:00:00 login-activity       params={}                     same_sha=False differs_in=['Summary/Window']
    gap=        2:00:00 groups               params={'window_days': 1}     same_sha=True differs_in=[]
    gap=        2:00:00 dormant-access       params={'dormant_days': 1}    same_sha=False differs_in=['Dormant: no successful login in 1 days/Members who have logged in before, not recently']
    gap=        2:00:00 groupsync-health     params={}                     same_sha=False differs_in=['Summary/Pipeline', 'GroupSync CRs/CRs']
    gap=        2:00:00 compliance-snapshot  params={}                     same_sha=False differs_in=['Key figures/Sync pipeline']
    gap=2 days, 0:00:00 login-activity       params={}                     same_sha=False differs_in=['Summary/Window']
    gap=2 days, 0:00:00 groups               params={'window_days': 1}     same_sha=False differs_in=['Summary/Groups', 'Membership changes, last 1 days/Changes']
    gap=2 days, 0:00:00 dormant-access       params={'dormant_days': 1}    same_sha=False differs_in=['Dormant: no successful login in 1 days/Members who have logged in before, not recently']
    gap=2 days, 0:00:00 groupsync-health     params={}                     same_sha=False differs_in=['Summary/Pipeline', 'GroupSync CRs/CRs']
    gap=2 days, 0:00:00 compliance-snapshot  params={}                     same_sha=False differs_in=['Key figures/Sync pipeline']

At two days all five differ on main, each in the block the issue names; that gap is T592-1's. With this spec all five
hash the same at every gap (T592-1 on the applied tree, §4.3).

**Table 2 — #607 on main: two snapshots of one store, the second after one more poll and one more read**
(`m607.py`, the diff's own `build_diff`):

    compliance-snapshot wall-clock stamps blocks_changed: 2
        Key figures — Sync pipeline | removed: [['Last poll', '2026-10-04T14:20:17Z — ok']] | added: [['Last poll', '2026-09-06T12:05:00Z — ok']]
        What this evidence attests — Coverage | removed: [['Can it say WHEN somebody last logged in?', 'yes — Login attempts are recorded since 2026-09-06T12:00:00Z (last read 2026-09-06T12:00:00Z); nothing before that was ever observed.']] | added: [['Can it say WHEN somebody last logged in?', 'yes — Login attempts are recorded since 2026-09-06T12:00:00Z (last read 2026-09-06T12:05:00Z); nothing before that was ever observed.']]
    login-activity wall-clock stamps blocks_changed: 1
        Summary — Window | removed: [['Last log read', '2026-09-06T12:00:00Z']] | added: [['Last log read', '2026-09-06T12:05:00Z']]

The two `compliance-snapshot` blocks are #607's lab finding reproduced. `login-activity`'s "Last log read" is
measured here: the same class, and on main the only row its cross-snapshot diff shows (its `To` is the generation
time, the same in both runs). (The first "Last poll" is the wall clock because the seed's `record_poll` reads it; T607's
fixture pins it to `NOW`.)

**Table 3 — the hash, main against new, over one snapshot file** (`hashes.py`; the first twelve hex digits; the
generation time 0, 2 minutes and 2 hours after the stamp):

| report | main, +0 / +2 m / +2 h | new, +0 / +2 m / +2 h |
|---|---|---|
| compliance-snapshot | 2654866b3b59 / 2654866b3b59 / 1afecb8d92b3 | 05bd49ee47ae, all three |
| login-activity | a383226c4572 / f5fcf4e70240 / b53408ae4476 | 04c0a495e1bf, all three |
| groupsync-health | a93522b953fc / a93522b953fc / 5b302a5d2c4c | 4c47283d6506, all three |
| groups | 493bdd93d72a, all three | 493bdd93d72a, all three (unchanged) |
| dormant-access | a68bbffb3c7e, all three | a68bbffb3c7e, all three (unchanged) |
| access-certification, access-matrix, binding-findings, namespace-access, privileged-access, users | one value each, all three | the same value as main, all three |

So: three hashes change once (Orchestrator's notes 2), `groups` and `dormant-access` change only where the window
edge moves a row, the other six never change, and on the new tree no report's hash depends on the generation time.

**The time experiment (why the seed's stamp is pinned).** With the clock change applied but the seed's copy left on the
wall clock, the stamp was shifted forward by an environment variable in a throwaway copy of `Store._vacuum_into`
(not part of this spec):

    shift 40 days:  FAILED test_reporting_catalogue.py::TestSubjectScopeAndLookups::test_login_activity_users_and_groups
                    FAILED test_reporting_catalogue.py::TestSubjectScopeAndLookups::test_a_scoped_login_pack_counts_the_scope_in_its_summary_too
    shift 400 days: the two above, and
                    FAILED test_reporting_catalogue.py::TestEveryReportBuildsAndRenders::test_dormant_access_uses_capture_when_told_it_is_on

(Besides the tests this spec rewrites, and `test_the_stamp_is_the_filename_in_iso_form`, which the shift itself broke.)
The seeded success of `alice` is at `NOW` − 1 day (2026-09-05 12:00 UTC), so a 30-day window from the wall clock loses
it from 2026-10-05 12:00 UTC: the day after this spec was written. Block 20 pins the stamp; with it, the reporting
suites pass on any date.

**The browser suite with the new default** (the working copy, every browser test, before Block 34 was written):
`694 passed, 2 warnings in 250.41s`. No test other than the two in Orchestrator's notes 7 depended on PDF being ticked.

## 2a. Alternatives considered

| | Option | Taken? | Why |
|---|---|---|---|
| A1 | A read-only property on the run context, `snapshot_at`, parsed from `snapshot_stamp` by one helper that the snapshot's age also uses | **yes** | no constructor changes: the two places that build a context (runs.py:181, server.py:536) and the seven test sites that do are untouched; one reader of the stamp's format |
| A2 | A new `RunContext` field filled by each caller | no | every caller and every test that builds a context changes, for a value already in the context as a string |
| A3 | Overwrite `ctx.now` with the stamp | no | page one's "Generated at" and the snapshot's age read `ctx.now`; the operator kept "Generated at" as the generation time |
| B1 | `login-activity`'s `From` and `To` stay in the sealed Window, valued at the stamp | **yes** | they say which period the counts cover, which is data; #607 lists the window under "Must not change"; a diff that shows the window moved is telling the truth (Orchestrator's notes 4) |
| B2 | Move `From` and `To` out of the sealed Window | no | page one is shared by eleven reports and has no window row; the reader would lose the period the counts cover |
| C1 | compliance-snapshot reads `started_at` from the snapshot for its WHEN answer | **yes** | the coverage dict is sealed for all eleven reports; adding a field to it would change every report's hash |
| C2 | Drop "(last read …)" from the coverage note in `common.coverage` | no | page one prints that note for every report (the DoD keeps "last read" on page one), and the note is inside every report's hash |
| D1 | Stamp the seed's copy at `NOW` in the test helper | **yes** | one helper; the seed's rows and its snapshot agree, as they do in production |
| D2 | Date the seed's rows from the wall clock | no | dozens of assertions pin the seed's instants (`2026-09-06T12:00:00Z`, run ids) |
| E1 | The form's default from `reporting.formats.manual` | no | the operator decided fixed defaults (#593) |

## 3. The design

### 3.1 One instant for the data: `RunContext.snapshot_at`

`local-development/gsd/reporting/snapshot.py` gains `stamp_instant(stamp)`, the one reader of the stamp's format; the
snapshot's age now calls it (no behaviour change). `RunContext` gains a read-only property, `snapshot_at`, the stamp as
an aware datetime. Its docstring says why it exists. The `now` field gets a one-line comment: it is the generation
time, for page one and the age, never a report's data.

Why the stamp is the right end: every window query reads `>= since` with no upper bound (§2.2), and a snapshot holds
nothing later than its stamp. A window that ends at the stamp therefore counts exactly what the snapshot holds, and its
`To` says so. A window that ends at the generation time claims minutes or hours the snapshot never saw, which is the
operator's "not accurate".

### 3.2 The five builders

Each `ctx.now` that feeds data becomes `ctx.snapshot_at`:

| Report | What moves to the stamp | Where |
|---|---|---|
| login-activity | the window's start, and its `To` row | Blocks 6, 7 |
| groups | the change window's start | Block 8 |
| dormant-access | the dormancy cutoff | Block 9 |
| groupsync-health | the sync window's start; each CR's state; the caveat's words ("at the snapshot's stamp") | Blocks 10, 11, 12 |
| compliance-snapshot | the Overdue count; the 30-day change window | Block 13 |

Page one is not touched: "Generated at" (`iso(ctx.now)`) and "Data as of … taken N min before generation" stay.

### 3.3 What a reader sees

`login-activity`'s Window reads `From` = stamp − N days and `To` = the stamp, to the second, the same instant page one
prints under "Data as of". A run generated two hours after the snapshot no longer says its data runs to the
generation time. Every run over one snapshot, with the same parameters, hashes the same, whenever it runs.

### 3.4 #607: no poll or read instant in a sealed section

- `compliance-snapshot`, Key figures, Sync pipeline: `("Last poll", "<instant> — <status>")` becomes
  `("Last poll status", "<status>")`. The instant stays on page one's "Last poll" row.
- `compliance-snapshot`, What this evidence attests, Coverage, "Can it say WHEN somebody last logged in?": when capture
  is ok, the answer is built from the capture's `started_at` without the last read: "yes — Login attempts are recorded
  since <started_at>; nothing before that was ever observed." The other answers (capture off or pending) are unchanged:
  those notes carry no instant (common.py:286, :288).
- `login-activity`, Summary, Window: the "Last log read" row leaves. "Watching since" (the capture's `started_at`)
  stays. Page one's login-capture note still prints "(last read …)".

The hash still covers both instants (Orchestrator's notes 5); a diff no longer shows them.

### 3.5 #593: the form starts with HTML ticked

`view.reportWant` starts as `{ pdf: false, html: true, csv: false }`. Nothing else in the page changes: the label, the
boxes and the POST already read `view.reportWant` and the boxes (index.html:2937-2953, :4270-4273), so the form opens
reading "Generate HTML · JSON" and posts `["html"]`. A reader who ticks PDF gets PDF; the choice survives a repaint as
before (#575).

### 3.6 The test seed

`write_snapshot(store, directory, at=NOW)` renames the copy the store wrote to the stamp of `at`, and refuses a second
copy at the same instant in one directory (a test that writes two must name the second's instant). Production code is
not touched.

### 3.7 What does not change, and the test that holds it

| Must not change | Held by |
|---|---|
| Page one's rows and words, "Generated at" the generation time | T270-1 (Generated at differs between two runs, now for every report), T592-1 (the two instants exact), T607-1 (page one's Last poll and last read), `test_t270_3_…` unchanged |
| What the diff compares, other than these instants | no block touches `diff.py`'s code (Block 18 is its docstring); T108-1, `test_diff_reports_stable_coverage_conclusions_without_read_cycle_noise`, #589's test unchanged in substance |
| `sealed_provenance` and the coverage, sealed for every report | no block touches `model.py`'s code (Blocks 16 and 17 are docstrings) or `common.coverage`; T270-5, T270-6 |
| The other six reports' seals | §2.3 table 3 (the same hash on main and new); T108-2 over all eleven |
| The PDF, HTML and CSV renderers | no block touches `render_pdf.py`, `render_html.py` or `render_csv.py` |
| The stored runs | nothing rewrites an artefact; `recompute_sha256` unchanged |
| Values, RBAC, templates | no block touches `charts/` except Chart.yaml's version lines |

## 4. Tests

### 4.1 One test per Definition-of-Done item

| DoD item | Test |
|---|---|
| #592: two runs over one snapshot, generated apart, hash the same, for each of the five | T592-1 `test_report_seal.py::test_t592_1_two_runs_two_days_apart_over_one_snapshot_hash_the_same` (five cases, two days apart, each with the parameters that put a seeded row on its edge); T108-2 now over all eleven reports |
| #592: no report reads the generation clock; the docs say where the windows end | T592-2 `test_report_seal.py::test_t592_2_no_report_reads_the_generation_clock_into_its_data` (replaces T270-10) |
| #607: a diff of two runs over snapshots that differ only in the poll and read instants reads "No change"; page one still shows both | T607-1 `test_report_diff.py::test_t607_1_compliance_snapshot_diffs_to_no_change_across_a_new_poll_and_read` |
| #607: `login-activity`'s "Last log read" (measured, the same class) | T607-2 `test_report_diff.py::test_t607_2_login_activity_shows_only_its_window_moving_across_a_new_poll_and_read` |
| #593: the form opens reading "Generate HTML · JSON" and posts HTML alone | T593-1 `test_ui.py::TestReportClusterControl::test_the_form_opens_with_html_only_ticked`; the label test updated (Block 32) |
| the full hermetic and browser suites | §4.3 |

### 4.2 Each test fails without the change, and why

With only the test blocks (20 to 34) applied to `4e5a708d` (§4.3, the "tests only" run):

- T270-1 [login-activity]: `To` is the generation time, two minutes apart.
- T592-1, all five: the hashes differ (the blocks in §2.3 table 1, at two days).
- T592-2: `assert not ['groups', 'login-activity', 'dormant-access', 'groupsync-health', 'compliance-snapshot']`.
- T108-2 [login-activity]: `{('Summary', 'Window')} == set()`.
- T607-1: `('Key figures', 'Sync pipeline')` and `('What this evidence attests', 'Coverage')` changed.
- T607-2: the Window's changed rows are `['From', 'Last log read', 'To']`, not `['From', 'To']`.
- T593-1: `'Generate PDF · HTML · JSON' == 'Generate HTML · JSON'`.
- The label test: `assert (True and not True)` (PDF is ticked).

T270-6 and #589's test pass on main with Blocks 25 and 29 too: those blocks only give the second copy its own instant.

### 4.3 The proof

Every command below ran on 2026-10-04 with the repository's venv, `PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=$PWD` from
`local-development`, Playwright's chromium for the browser suite, and no cluster. "main" is a clone of `4e5a708d`;
"applied" is an `rsync` copy (no `.git`) of this spec's worktree, `4e5a708d` plus this spec, its index row and the
index test's count, with the blocks applied. Three hermetic tests read git (`git ls-files`, `git show HEAD:…`) and
fail in a copy with no `.git`, so the suites below ran in a second applied copy: a clone of the worktree's `4e5a708d`
with the applied files copied over it (22 paths changed or added, nothing committed). Every copy was deleted
afterwards.

**The blocks.**

    $ python3 local-development/apply-spec-blocks.py docs/specs/SPEC_F7_snapshot_clock.md .
    40 blocks check out across 19 files
    $ python3 local-development/apply-spec-blocks.py docs/specs/SPEC_F7_snapshot_clock.md . --apply
    40 blocks check out across 19 files
    applied to …/f7-proof

The applied tree is byte-equal, file by file (`cmp`, 19 files), to the working copy the blocks were generated from,
and differs from main in exactly those 19 files plus this spec, the index row and the index test.

**Lines added and removed** (`git diff --no-index --numstat`, main against applied):

| File | + | − |
|---|---|---|
| local-development/gsd/reporting/snapshot.py | 6 | 1 |
| local-development/gsd/reporting/catalogue/common.py | 8 | 1 |
| local-development/gsd/reporting/catalogue/login_activity.py | 5 | 3 |
| local-development/gsd/reporting/catalogue/groups.py | 1 | 1 |
| local-development/gsd/reporting/catalogue/dormant_access.py | 1 | 1 |
| local-development/gsd/reporting/catalogue/groupsync_health.py | 3 | 3 |
| local-development/gsd/reporting/catalogue/compliance_snapshot.py | 9 | 4 |
| local-development/gsd/reporting/model.py (docstrings) | 4 | 4 |
| local-development/gsd/reporting/diff.py (docstring) | 1 | 1 |
| local-development/gsd/static/index.html | 1 | 1 |
| local-development/tests/reporting_seed.py | 7 | 2 |
| local-development/tests/test_report_seal.py | 36 | 42 |
| local-development/tests/test_report_diff.py | 61 | 20 |
| local-development/tests/test_ui.py | 29 | 5 |
| docs/DESIGN_reporting_service.md | 7 | 5 |
| charts/group-sync-dashboard/Chart.yaml | 5 | 2 |
| local-development/pyproject.toml | 1 | 1 |
| local-development/gsd/__init__.py | 1 | 1 |
| docs/CHANGELOG.md | 20 | 0 |
| **total** | **206** | **98** |

The product code is 39 lines added and 20 removed; of the 39, 14 are comments or docstrings and 3 are blank.

**The new tests fail on main** (main with only the test blocks, 20 to 34, applied):

    $ pytest -q tests/test_report_seal.py tests/test_report_diff.py
    FAILED tests/test_report_seal.py::test_t270_1_two_runs_over_one_snapshot_hash_the_same[login-activity]
    FAILED tests/test_report_seal.py::test_t592_1_two_runs_two_days_apart_over_one_snapshot_hash_the_same[compliance-snapshot]
    FAILED tests/test_report_seal.py::test_t592_1_two_runs_two_days_apart_over_one_snapshot_hash_the_same[dormant-access]
    FAILED tests/test_report_seal.py::test_t592_1_two_runs_two_days_apart_over_one_snapshot_hash_the_same[groups]
    FAILED tests/test_report_seal.py::test_t592_1_two_runs_two_days_apart_over_one_snapshot_hash_the_same[groupsync-health]
    FAILED tests/test_report_seal.py::test_t592_1_two_runs_two_days_apart_over_one_snapshot_hash_the_same[login-activity]
    FAILED tests/test_report_seal.py::test_t592_2_no_report_reads_the_generation_clock_into_its_data
    FAILED tests/test_report_diff.py::test_t108_2_two_runs_over_one_snapshot_diff_to_no_change[login-activity]
    FAILED tests/test_report_diff.py::test_t607_1_compliance_snapshot_diffs_to_no_change_across_a_new_poll_and_read
    FAILED tests/test_report_diff.py::test_t607_2_login_activity_shows_only_its_window_moving_across_a_new_poll_and_read
    10 failed, 39 passed, 2 warnings in 5.19s

    $ pytest -q tests/test_ui.py --browser chromium -k '<the five format-box tests>'
    test_ui.py:11865: AssertionError: assert (True and not True)
    test_ui.py:11895: AssertionError: assert 'Generate PDF · HTML · JSON' == 'Generate HTML · JSON'
    FAILED tests/test_ui.py::TestReportClusterControl::test_generate_label_follows_the_format_boxes[chromium]
    FAILED tests/test_ui.py::TestReportClusterControl::test_the_form_opens_with_html_only_ticked[chromium]
    2 failed, 3 passed, 689 deselected in 6.65s

Each failure's reason is in §4.2. The three that pass on main (the PDF download walk, the CSV box, the repaint test)
pass after too: their blocks make them independent of the default.

**The affected suites on the applied tree:**

    $ pytest -q tests/test_reporting_catalogue.py tests/test_report_seal.py tests/test_report_diff.py \
        tests/test_report_csv.py tests/test_namespace_selector.py tests/test_unmanaged_subjects.py \
        tests/test_reporting_server.py tests/test_reporting_snapshot.py tests/test_reporting_render.py \
        tests/test_backup.py tests/test_kpi.py tests/test_chart_versions.py tests/test_kyverno.py \
        tests/test_specs_index.py tests/test_docs_citations.py tests/test_prepare_release.py
    2511 passed, 18 skipped, 2 warnings in 81.95s (0:01:21)

**The full hermetic suite** (CI's selection, `.github/workflows/ci.yml`):

    $ pytest tests/ -q --deselect tests/test_ui.py --deselect tests/test_live_smoke.py
    7623 passed, 23 skipped, 698 deselected, 5 xfailed, 2 warnings in 365.22s (0:06:05)

On main the same command: `7612 passed, 24 skipped, 697 deselected, 5 xfailed, 2 warnings in 362.73s (0:06:02)`.
The difference, from `--collect-only` on both: seven ids gone (T108-3 ×5, T270-2, T270-10), seventeen new (T108-2 ×5
for the five reports it now covers, T607-1, T607-2, T592-1 ×5, T592-2, the index's two F7 cases, this spec's one
citation and its fence check), and `test_kyverno.py::test_f3_unreleased_cites_the_current_chart_version_when_it_moved_since_the_last_release`
runs instead of skipping, because the CHANGELOG has an Unreleased section again and it names chart 0.70.2:
+11 passed, −1 skipped.

**The browser suite:**

    $ pytest tests/test_ui.py -q --browser chromium
    694 passed, 2 warnings in 250.71s (0:04:10)

On main the same command: `693 passed, 2 warnings in 254.87s (0:04:14)`; the one more is T593-1.

**Markdown lint** (`markdownlint-cli2`, the repository's config): `docs/specs/README.md` 0 issues;
`docs/CHANGELOG.md` and `docs/DESIGN_reporting_service.md` report the same three issues on main and on the applied
tree (MD038, MD012, MD040, at lines this spec does not touch, moved by 20 in the CHANGELOG).

**Not measured:** the lab (§5); `helm template` (no template or value changes; Chart.yaml's version fields are
held by `tests/test_chart_versions.py`, in the affected run above).

## 5. On the lab (the implementing pull request)

After the release is deployed with `release-crc.sh --argocd` (the data and report-artifacts PVC UIDs recorded before
and after), in namespace `group-sync-dashboard`, as a wide-tier viewer. The snapshot interval is
`reporting.snapshot.intervalSeconds` (300 s by default): two runs read one snapshot only if no new copy lands between
them, so each pair below is checked by its `snapshot_stamp`, and a pair that straddles a new copy is run again.

1. **One snapshot, two clocks, one hash.** Generate `compliance-snapshot` on `crc-local`, then again three minutes
   later; the same for `login-activity` (login capture is on in `environments/crc.yaml`). From
   `GET /report/api/runs`, read each run's `snapshot_stamp` and `sha256`. Pass: for each report, equal stamps and
   equal sha256s. Open both `login-activity` HTML files: the Window's `To` equals page one's "Data as of" stamp to the
   second, and the two pages' "Generated at" differ by about three minutes.
2. **#607 on `mock-trusted`.** Generate `compliance-snapshot` on `mock-trusted`; after the next snapshot (more than
   300 s later, a newer `snapshot_stamp`) generate it again, and request a `report-diff` of the two (the Report history
   row's "Diff vs…" action). Pass: the diff's Summary reads "No change" (`blocks_changed: 0`) unless the cluster's data
   changed between the snapshots, in which case every changed row is a data row (none is "Last poll" or "last read").
   Page one of each run still shows its "Last poll" instant and the capture note's "(last read …)".
3. **The form.** Open the Reports tab, pick any report. Pass: only HTML is ticked and the button reads
   "Generate HTML · JSON"; tick PDF and the label reads "PDF · HTML · JSON".

The evidence (the run records, the diff, the screenshots) goes under `reports/<date>_<slug>/` and on #592, #607 and
#593, pinned to the full merge sha. This spec makes no lab write beyond the report runs.

## 6. What a reader sees, and what it costs

A report's windows end where its data ends: `login-activity`'s `To` is the snapshot's stamp, the same instant page one
prints as "Data as of". Two runs over one snapshot are one sha256 whoever runs them and whenever. A diff of
`compliance-snapshot` across snapshots shows only data. The Reports form starts with HTML only, which also makes a
manual run lighter by default ("PDF is heavy"). Cost: the three hash changes of Orchestrator's notes 2, once; no new
permission, value, migration, route or image.

## 7. Implementation blocks

Forty blocks, in this order: the code (1 to 19), the tests (20 to 34), the design doc (35), the versions and the
CHANGELOG (36 to 40). Each edit's Old text occurs once in its file on `4e5a708d`, after the earlier blocks for that
file.

### Block 1 — `local-development/gsd/reporting/snapshot.py` (1 of 2): one reader of the stamp's format, `stamp_instant`

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->

```python


@dataclass(frozen=True)
class SnapshotInfo:
```

```python


def stamp_instant(stamp: str) -> datetime:
    """A snapshot stamp (ISO-8601 UTC with microseconds, from the filename) as an aware datetime."""
    return datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


@dataclass(frozen=True)
class SnapshotInfo:
```

### Block 2 — `local-development/gsd/reporting/snapshot.py` (2 of 2): the snapshot's age reads it (no behaviour change)

<!-- block: local-development/gsd/reporting/snapshot.py | edit -->

```python

    def age_seconds(self, now: datetime) -> float:
        return (now - datetime.strptime(self.stamp, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)).total_seconds()


```

```python

    def age_seconds(self, now: datetime) -> float:
        return (now - stamp_instant(self.stamp)).total_seconds()


```

### Block 3 — `local-development/gsd/reporting/catalogue/common.py` (1 of 3): the run context imports it

<!-- block: local-development/gsd/reporting/catalogue/common.py | edit -->

```python
from ..config import ReportSettings
from ..model import DIRECT_BINDINGS_CAVEAT, KeyValues, Note, Report, Section, Table, iso
from ..snapshot import CLUSTER_SCOPE, Snapshot

MAX_NAMESPACES = 50
```

```python
from ..config import ReportSettings
from ..model import DIRECT_BINDINGS_CAVEAT, KeyValues, Note, Report, Section, Table, iso
from ..snapshot import CLUSTER_SCOPE, Snapshot, stamp_instant

MAX_NAMESPACES = 50
```

### Block 4 — `local-development/gsd/reporting/catalogue/common.py` (2 of 3): `now` is the generation time, and says so

<!-- block: local-development/gsd/reporting/catalogue/common.py | edit -->

```python
    settings: ReportSettings
    cluster: dict                   # Snapshot.cluster row
    now: datetime
    run_id: str
```

```python
    settings: ReportSettings
    cluster: dict                   # Snapshot.cluster row
    #: The generation time: page one's "Generated at" and the snapshot's age. Never a report's data (#592).
    now: datetime
    run_id: str
```

### Block 5 — `local-development/gsd/reporting/catalogue/common.py` (3 of 3): `RunContext.snapshot_at`: the instant the data ends

<!-- block: local-development/gsd/reporting/catalogue/common.py | edit -->

```python
    #: company.net/app-environment. Empty = no selector.
    namespace_selector_labels: tuple[str, ...] = ()


```

```python
    #: company.net/app-environment. Empty = no selector.
    namespace_selector_labels: tuple[str, ...] = ()

    @property
    def snapshot_at(self) -> datetime:
        """The instant the data ends: the snapshot's stamp. Windows, cutoffs and overdue states end here, not at
        the generation time, so every run over one snapshot states the same data (#592)."""
        return stamp_instant(self.snapshot_stamp)


```

### Block 6 — `local-development/gsd/reporting/catalogue/login_activity.py` (1 of 2): the window starts N days before the snapshot's stamp

<!-- block: local-development/gsd/reporting/catalogue/login_activity.py | edit -->

```python
        raise ValidationError("login-activity needs login capture (loginCapture.enabled); nothing writes login_event without it")
    cid = ctx.cluster["id"]
    since = window_start(ctx.now, params["window_days"])
    # The subject scope: named users, and the members of named groups (#149 R7). The summary by outcome
    # and provider is the scope's too — a scoped pack whose totals counted the whole cluster's attempts
```

```python
        raise ValidationError("login-activity needs login capture (loginCapture.enabled); nothing writes login_event without it")
    cid = ctx.cluster["id"]
    since = window_start(ctx.snapshot_at, params["window_days"])
    # The subject scope: named users, and the members of named groups (#149 R7). The summary by outcome
    # and provider is the scope's too — a scoped pack whose totals counted the whole cluster's attempts
```

### Block 7 — `local-development/gsd/reporting/catalogue/login_activity.py` (2 of 2): `To` is the stamp; "Last log read" leaves the sealed Window (#607)

<!-- block: local-development/gsd/reporting/catalogue/login_activity.py | edit -->

```python
    sections = scope_note + [
        Section("Summary", [
            KeyValues("Window", [("From", since), ("To", ctx.now.strftime("%Y-%m-%dT%H:%M:%SZ")),
                                 ("Watching since", status["started_at"] if status else "not yet"), ("Last log read", status["last_read_at"] if status else "never"),
                                 ("Login gate", f"{gate['group_name']} ({gate['source']})" if gate and gate["group_name"] else "none known")]),
            Table("Attempts by outcome and provider", ["outcome", "provider", "attempts"], [[s["outcome"], s["provider"], s["n"]] for s in summary], empty_text="no attempts in the window"),
```

```python
    sections = scope_note + [
        Section("Summary", [
            # The window ends at the snapshot's stamp (#592). The last log read moves with every read, so it is on
            # page one's login-capture note and not here: a diff of two snapshots must not show it (#607).
            KeyValues("Window", [("From", since), ("To", ctx.snapshot_at.strftime("%Y-%m-%dT%H:%M:%SZ")),
                                 ("Watching since", status["started_at"] if status else "not yet"),
                                 ("Login gate", f"{gate['group_name']} ({gate['source']})" if gate and gate["group_name"] else "none known")]),
            Table("Attempts by outcome and provider", ["outcome", "provider", "attempts"], [[s["outcome"], s["provider"], s["n"]] for s in summary], empty_text="no attempts in the window"),
```

### Block 8 — `local-development/gsd/reporting/catalogue/groups.py`: the change window ends at the stamp

<!-- block: local-development/gsd/reporting/catalogue/groups.py | edit -->

```python
def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    since = window_start(ctx.now, params["window_days"])
    groups = snap.groups(cid)
    if params["groups"]:
```

```python
def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    since = window_start(ctx.snapshot_at, params["window_days"])
    groups = snap.groups(cid)
    if params["groups"]:
```

### Block 9 — `local-development/gsd/reporting/catalogue/dormant_access.py`: the dormancy cutoff is set from the stamp

<!-- block: local-development/gsd/reporting/catalogue/dormant_access.py | edit -->

```python
    if ctx.settings.login_capture_enabled:
        last = snap.last_successful_login(cid)
        cutoff = window_start(ctx.now, params["dormant_days"])
        capture = snap.login_capture_status(cid)
        rosters = snap.group_rosters(cid, [g["name"] for g in snap.groups(cid)])
```

```python
    if ctx.settings.login_capture_enabled:
        last = snap.last_successful_login(cid)
        cutoff = window_start(ctx.snapshot_at, params["dormant_days"])
        capture = snap.login_capture_status(cid)
        rosters = snap.group_rosters(cid, [g["name"] for g in snap.groups(cid)])
```

### Block 10 — `local-development/gsd/reporting/catalogue/groupsync_health.py` (1 of 3): the sync window ends at the stamp

<!-- block: local-development/gsd/reporting/catalogue/groupsync_health.py | edit -->

```python
def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    since = window_start(ctx.now, params["window_days"])
    crs = snap.groupsyncs(cid)
    presence = snap.groupsync_presence(cid)
```

```python
def build(snap: Snapshot, ctx: RunContext, params: dict) -> Built:
    cid = ctx.cluster["id"]
    since = window_start(ctx.snapshot_at, params["window_days"])
    crs = snap.groupsyncs(cid)
    presence = snap.groupsync_presence(cid)
```

### Block 11 — `local-development/gsd/reporting/catalogue/groupsync_health.py` (2 of 3): each CR's state is computed at the stamp

<!-- block: local-development/gsd/reporting/catalogue/groupsync_health.py | edit -->

```python
    for cr in crs:
        last = st.parse_time(cr["last_sync_at"])
        state = st.compute_state(last, cr["schedule"], ctx.now, GRACE)
        current = st.reconcile_error_is_current(st.parse_time(cr["error_at"]), last)
        s = syncs.get(cr["name"], {})
```

```python
    for cr in crs:
        last = st.parse_time(cr["last_sync_at"])
        state = st.compute_state(last, cr["schedule"], ctx.snapshot_at, GRACE)
        current = st.reconcile_error_is_current(st.parse_time(cr["error_at"]), last)
        s = syncs.get(cr["name"], {})
```

### Block 12 — `local-development/gsd/reporting/catalogue/groupsync_health.py` (3 of 3): the caveat says so

<!-- block: local-development/gsd/reporting/catalogue/groupsync_health.py | edit -->

```python
        Section("GroupSync CRs", [
            Table("CRs", ["cr", "schedule", "state", "last sync", "groups", f"syncs in {params['window_days']} d", "last sync in window", "reconcile error"], rows, empty_text="no GroupSync CR"),
            Note("State is computed from the schedule and the last sync at generation time, with a 120 s grace — the Overview's rule (gsd/state.py compute_state). Error text is withheld: it can carry the directory bind DN.", "caveat"),
        ], page_break=True),
        Section("Policy operator", [Table("NamespaceConfig and GroupConfig", ["kind", "name", "last success", "last error", "status", "message"], cfg_rows,
```

```python
        Section("GroupSync CRs", [
            Table("CRs", ["cr", "schedule", "state", "last sync", "groups", f"syncs in {params['window_days']} d", "last sync in window", "reconcile error"], rows, empty_text="no GroupSync CR"),
            Note("State is computed from the schedule and the last sync at the snapshot's stamp, with a 120 s grace — the Overview's rule (gsd/state.py compute_state). Error text is withheld: it can carry the directory bind DN.", "caveat"),
        ], page_break=True),
        Section("Policy operator", [Table("NamespaceConfig and GroupConfig", ["kind", "name", "last success", "last error", "status", "message"], cfg_rows,
```

### Block 13 — `local-development/gsd/reporting/catalogue/compliance_snapshot.py` (1 of 3): the Overdue count and the 30-day window at the stamp; the capture's start is read

<!-- block: local-development/gsd/reporting/catalogue/compliance_snapshot.py | edit -->

```python
    gate = snap.access_group(cid)
    crs = snap.groupsyncs(cid)
    overdue = sum(1 for cr in crs if st.compute_state(st.parse_time(cr["last_sync_at"]), cr["schedule"], ctx.now, GRACE) == st.OVERDUE)
    changes = snap.membership_change_counts(cid, window_start(ctx.now, 30))
    cov = coverage(snap, ctx)
    sections = [
        Section("Key figures", [
```

```python
    gate = snap.access_group(cid)
    crs = snap.groupsyncs(cid)
    overdue = sum(1 for cr in crs if st.compute_state(st.parse_time(cr["last_sync_at"]), cr["schedule"], ctx.snapshot_at, GRACE) == st.OVERDUE)
    changes = snap.membership_change_counts(cid, window_start(ctx.snapshot_at, 30))
    cov = coverage(snap, ctx)
    capture = snap.login_capture_status(cid)
    sections = [
        Section("Key figures", [
```

### Block 14 — `local-development/gsd/reporting/catalogue/compliance_snapshot.py` (2 of 3): Sync pipeline keeps the poll's status, not its instant (#607)

<!-- block: local-development/gsd/reporting/catalogue/compliance_snapshot.py | edit -->

```python
                                         ("Access outside the login gate", len(awl) if gate and gate["group_name"] else "no gate known"),
                                         ("Login gate", f"{gate['group_name']}" if gate and gate["group_name"] else "none")]),
            KeyValues("Sync pipeline", [("GroupSync CRs", c["groupsyncs"]), ("Overdue", overdue), ("Last poll", f"{ctx.cluster.get('last_poll')} — {ctx.cluster.get('status')}")]),
        ]),
        Section("Privileged grants", [Table("cluster-admin anywhere; admin/edit cluster-wide", ["kind", "subject", "role", "scope", "binding"],
```

```python
                                         ("Access outside the login gate", len(awl) if gate and gate["group_name"] else "no gate known"),
                                         ("Login gate", f"{gate['group_name']}" if gate and gate["group_name"] else "none")]),
            # The poll's instant is on page one; only its outcome is data here, so a diff of two snapshots
            # does not show a new poll as a change (#607).
            KeyValues("Sync pipeline", [("GroupSync CRs", c["groupsyncs"]), ("Overdue", overdue), ("Last poll status", str(ctx.cluster.get("status")))]),
        ]),
        Section("Privileged grants", [Table("cluster-admin anywhere; admin/edit cluster-wide", ["kind", "subject", "role", "scope", "binding"],
```

### Block 15 — `local-development/gsd/reporting/catalogue/compliance_snapshot.py` (3 of 3): the WHEN answer says since when, without the last read (#607)

<!-- block: local-development/gsd/reporting/catalogue/compliance_snapshot.py | edit -->

```python
                ["Can it attest that a namespace has NO grants?", "yes" if cov["attests_absence"] else "no — " + cov["namespaces_note"]],
                ["Can it say who has logged in?", "yes (User objects with identities)" if cov["users_read"] == "ok" else "no — " + cov["users_note"]],
                ["Can it say WHEN somebody last logged in?", "yes — " + cov["login_capture_note"] if cov["login_capture"] == "ok" else "no — " + cov["login_capture_note"]],
                ["Does it evaluate effective permissions?", "no — " + cov["direct_bindings_caveat"]],
                ["How far back does membership history go?", cov["history_retained_since"]["membership_event"] or "no rows"],
```

```python
                ["Can it attest that a namespace has NO grants?", "yes" if cov["attests_absence"] else "no — " + cov["namespaces_note"]],
                ["Can it say who has logged in?", "yes (User objects with identities)" if cov["users_read"] == "ok" else "no — " + cov["users_note"]],
                # Since when, without the last read: that instant moves with every read and is on page one (#607).
                ["Can it say WHEN somebody last logged in?", f"yes — Login attempts are recorded since {capture['started_at']}; nothing before that was ever observed."
                 if cov["login_capture"] == "ok" else "no — " + cov["login_capture_note"]],
                ["Does it evaluate effective permissions?", "no — " + cov["direct_bindings_caveat"]],
                ["How far back does membership history go?", cov["history_retained_since"]["membership_event"] or "no rows"],
```

### Block 16 — `local-development/gsd/reporting/model.py` (1 of 2): the module docstring

<!-- block: local-development/gsd/reporting/model.py | edit -->

```python
cluster's last poll before it ended). Page one's facts of the run — when, by whom, under which run
id or release, how old the snapshot was, the chart's marking or binding interval — are outside it,
so two runs over one snapshot with the same parameters hash the same whoever runs them, except where
a report's own data is computed against the generation clock (a window, a cutoff, an overdue state:
SPEC_F1, Orchestrator's notes 1): those agree only while the clock-derived values coincide. The
coverage can also reflect two report-service settings (`login_capture_enabled`,
`namespaces_read_enabled`), so a run under other settings is other evidence. A PDF can be tied back
```

```python
cluster's last poll before it ended). Page one's facts of the run — when, by whom, under which run
id or release, how old the snapshot was, the chart's marking or binding interval — are outside it,
so two runs over one snapshot with the same parameters hash the same whoever runs them and whenever:
a window, a cutoff or an overdue state ends at the snapshot's stamp, not at the generation time
(#592, docs/specs/SPEC_F7_snapshot_clock.md), so it is the same at every run over one snapshot. The
coverage can also reflect two report-service settings (`login_capture_enabled`,
`namespaces_read_enabled`), so a run under other settings is other evidence. A PDF can be tied back
```

### Block 17 — `local-development/gsd/reporting/model.py` (2 of 2): `Report.canonical`'s docstring

<!-- block: local-development/gsd/reporting/model.py | edit -->

```python
    def canonical(self) -> dict:
        """The DATA, and only the data: what two runs over one snapshot with the same parameters agree
        on while the values a report computes against the generation clock coincide (the module
        docstring). A section marked `sealed=False` (page one, the run's facts) is left out; what page
        one shows that is data is here through its own key: the cluster and its API URL, the snapshot facts, the
```

```python
    def canonical(self) -> dict:
        """The DATA, and only the data: what two runs over one snapshot with the same parameters agree
        on at any generation time, because their data ends at the snapshot's stamp (the module
        docstring). A section marked `sealed=False` (page one, the run's facts) is left out; what page
        one shows that is data is here through its own key: the cluster and its API URL, the snapshot facts, the
```

### Block 18 — `local-development/gsd/reporting/diff.py`: the module docstring

<!-- block: local-development/gsd/reporting/diff.py | edit -->

```python
A diff reads two stored `.json` artefacts, never the snapshot, and compares their SEALED data only
(SPEC_F1): page one states the run, so it is left out, and two runs over one snapshot diff to
"No change" unless the report's own data reads the generation clock. Stable coverage conclusions,
every table, key-value list and the notes of each sealed section are compared as a multiset of whole
rows: a row present in the head and not the base is added, the reverse is removed, and a changed cell
```

```python
A diff reads two stored `.json` artefacts, never the snapshot, and compares their SEALED data only
(SPEC_F1): page one states the run, so it is left out, and two runs over one snapshot diff to
"No change": a report's data ends at the snapshot's stamp (#592). Stable coverage conclusions,
every table, key-value list and the notes of each sealed section are compared as a multiset of whole
rows: a row present in the head and not the base is added, the reverse is removed, and a changed cell
```

### Block 19 — `local-development/gsd/static/index.html`: the form starts with HTML ticked (#593)

<!-- block: local-development/gsd/static/index.html | edit -->

```html
const view = { page: "home", homeShow: {}, cluster: null, groupsync: null, groupFilter: "all", bindingFilter: "review",
                report: null, reportLanded: null, reportFocusRow: null, reportForm: {},
                reportWant: { pdf: true, html: true, csv: false },   // #106: the format boxes, kept across the form's repaints
                kyvernoControlled: false, kyvernoPolicy: null, kyvernoKind: null,   // #170: the Kyverno page's filters (filters, not positions)
                /* #230 S2: the Cluster Configurations form's state, so a poll's repaint never destroys what the
```

```html
const view = { page: "home", homeShow: {}, cluster: null, groupsync: null, groupFilter: "all", bindingFilter: "review",
                report: null, reportLanded: null, reportFocusRow: null, reportForm: {},
                reportWant: { pdf: false, html: true, csv: false },  // #106: the format boxes, kept across the form's repaints; #593: HTML only at first, PDF is heavy
                kyvernoControlled: false, kyvernoPolicy: null, kyvernoKind: null,   // #170: the Kyverno page's filters (filters, not positions)
                /* #230 S2: the Cluster Configurations form's state, so a poll's repaint never destroys what the
```

### Block 20 — `local-development/tests/reporting_seed.py`: `write_snapshot` stamps the copy at the seed's NOW

<!-- block: local-development/tests/reporting_seed.py | edit -->

```python


def write_snapshot(store: Store, directory: Path) -> Path:
    path = store.snapshot(str(directory), keep=2)
    assert path, "snapshot was not written"
    return Path(path)


```

```python


def write_snapshot(store: Store, directory: Path, at: datetime = NOW) -> Path:
    """A copy of `store`, stamped `at` (the seed's NOW unless a test says otherwise). A report's data ends at the
    snapshot's stamp (#592), so a copy stamped by the wall clock would slide every window as the calendar moves and
    drop the seed's rows out of them."""
    path = store.snapshot(str(directory), keep=2)
    assert path, "snapshot was not written"
    pinned = Path(path).with_name(f"gsd-{at.strftime('%Y%m%dT%H%M%S.%f')}Z.db")
    assert not pinned.exists(), f"{pinned.name} exists: give the second copy its own instant"
    return Path(path).rename(pinned)


```

### Block 21 — `local-development/tests/test_report_seal.py` (1 of 6): the module docstring

<!-- block: local-development/tests/test_report_seal.py | edit -->

```python
"""The seal covers the data only (docs/specs/SPEC_F1_data_only_seal.md, #270): two runs over one snapshot
with the same parameters hash the same whoever runs them, while the values a report computes against the
generation clock coincide; the snapshot, the parameters and the coverage are sealed; page one still shows the
run; the .json alone reproduces the hash."""
from __future__ import annotations

```

```python
"""The seal covers the data only (docs/specs/SPEC_F1_data_only_seal.md, #270): two runs over one snapshot
with the same parameters hash the same whoever runs them and whenever, because a report's data ends at the
snapshot's stamp (docs/specs/SPEC_F7_snapshot_clock.md, #592); the snapshot, the parameters and the coverage are
sealed; page one still shows the run; the .json alone reproduces the hash."""
from __future__ import annotations

```

### Block 22 — `local-development/tests/test_report_seal.py` (2 of 6): `SNAPSHOT_CLOCK` replaces `CLOCK_ANCHORED` and `CLOCK_DERIVED`

<!-- block: local-development/tests/test_report_seal.py | edit -->

```python
    "access-certification": {"campaign": "Q3 2026", "due": "2026-10-01", "reviewer": "Jane Reviewer"},
}
#: login-activity's Window prints the generation clock as its `To`: data anchored to the run (SPEC_F1,
#: Orchestrator's notes 1), so two of its runs agree only at one clock.
CLOCK_ANCHORED = {"login-activity"}
#: Every report whose builder reads the generation clock (`ctx.now`) into sealed data: a window, a cutoff, an
#: overdue state. Two of its runs over one snapshot agree only while those values coincide (SPEC_F1, note 1).
CLOCK_DERIVED = {"login-activity", "groups", "dormant-access", "groupsync-health", "compliance-snapshot"}
#: The .json keys before SPEC_F1; none is removed or renamed.
JSON_KEYS = {"name", "cluster", "params", "coverage", "totals", "truncated", "include_members", "sections", "title",
```

```python
    "access-certification": {"campaign": "Q3 2026", "due": "2026-10-01", "reviewer": "Jane Reviewer"},
}
#: The five reports whose window, cutoff or overdue state ends at the snapshot's stamp (#592), each with the
#: parameters that put a seeded row on that edge: on main, a run two days later moved each of them (SPEC_F7 §2.3).
SNAPSHOT_CLOCK = {"login-activity": {}, "groups": {"window_days": 1}, "dormant-access": {"dormant_days": 1},
                  "groupsync-health": {}, "compliance-snapshot": {}}
#: The .json keys before SPEC_F1; none is removed or renamed.
JSON_KEYS = {"name", "cluster", "params", "coverage", "totals", "truncated", "include_members", "sections", "title",
```

### Block 23 — `local-development/tests/test_report_seal.py` (3 of 6): `_other_run` is two minutes later for every report

<!-- block: local-development/tests/test_report_seal.py | edit -->

```python

def _other_run(snapshot: Snapshot, name: str, **over) -> Report:
    """The same report over the same snapshot by another viewer, under another run id, two minutes later
    (at the same clock for a clock-anchored report)."""
    later = NOW if name in CLOCK_ANCHORED else NOW + timedelta(minutes=2)
    return _run(snapshot, name, now=later, run_id="20260906T120200.000000Z-cd34", viewer="bob",
                note="schedule:nightly", **over)

```

```python

def _other_run(snapshot: Snapshot, name: str, **over) -> Report:
    """The same report over the same snapshot by another viewer, under another run id, two minutes later."""
    return _run(snapshot, name, now=NOW + timedelta(minutes=2), run_id="20260906T120200.000000Z-cd34", viewer="bob",
                note="schedule:nightly", **over)

```

### Block 24 — `local-development/tests/test_report_seal.py` (4 of 6): T270-1 checks Generated at for every report; T592-1 replaces T270-2

<!-- block: local-development/tests/test_report_seal.py | edit -->

```python
    one, two = _page_one(first), _page_one(second)
    assert one["Run id"] != two["Run id"] and one["Generated by"] != two["Generated by"], "page one still shows the run"
    if name not in CLOCK_ANCHORED:
        assert one["Generated at (UTC)"] != two["Generated at (UTC)"]


def test_t270_2_login_activity_differs_only_in_its_window_when_the_clock_moves(snap):
    """The measured limit (SPEC_F1, Orchestrator's notes 1): at another clock, login-activity's sealed data
    differs in its Window block and nowhere else. Without SPEC_F1 page one differs too."""
    first = _run(snap, "login-activity")
    second = _run(snap, "login-activity", now=NOW + timedelta(minutes=2), run_id="20260906T120200.000000Z-cd34",
                  viewer="bob")
    assert first.sha256 != second.sha256

    def without_window(report: Report) -> dict:
        doc = report.canonical()
        for section in doc["sections"]:
            section["blocks"] = [b for b in section["blocks"] if not (b["kind"] == "kv" and b["title"] == "Window")]
        return doc

    assert without_window(first) == without_window(second)


```

```python
    one, two = _page_one(first), _page_one(second)
    assert one["Run id"] != two["Run id"] and one["Generated by"] != two["Generated by"], "page one still shows the run"
    assert one["Generated at (UTC)"] != two["Generated at (UTC)"]


@pytest.mark.parametrize("name", sorted(SNAPSHOT_CLOCK))
def test_t592_1_two_runs_two_days_apart_over_one_snapshot_hash_the_same(snap, name):
    """#592: a report's window, cutoff or overdue state ends at the snapshot's stamp, so a run two days later over
    the same snapshot states the same data; page one's Generated at still says when each ran. Without the change
    each of the five differs (SPEC_F7 §2.3): login-activity's Window `To`, the one-day change window of groups, the
    one-day dormancy cutoff, groupsync-health's overdue state and compliance-snapshot's Overdue count."""
    params = SNAPSHOT_CLOCK[name]
    first = _run(snap, name, params=params)
    later = _run(snap, name, now=NOW + timedelta(days=2), run_id="20260908T120000.000000Z-cd34", viewer="bob",
                 params=params)
    assert first.sha256 == later.sha256, name
    assert _page_one(first)["Generated at (UTC)"] == "2026-09-06T12:00:00Z"
    assert _page_one(later)["Generated at (UTC)"] == "2026-09-08T12:00:00Z"


```

### Block 25 — `local-development/tests/test_report_seal.py` (5 of 6): T270-6's second copy has its own instant

<!-- block: local-development/tests/test_report_seal.py | edit -->

```python
    directory.mkdir()
    try:
        first, second = Snapshot(write_snapshot(store, directory)), Snapshot(write_snapshot(store, directory))
    finally:
        store.close()
```

```python
    directory.mkdir()
    try:
        first = Snapshot(write_snapshot(store, directory))
        second = Snapshot(write_snapshot(store, directory, at=NOW + timedelta(minutes=5)))
    finally:
        store.close()
```

### Block 26 — `local-development/tests/test_report_seal.py` (6 of 6): T592-2 replaces T270-10

<!-- block: local-development/tests/test_report_seal.py | edit -->

```python


def test_t270_10_the_docs_name_every_report_whose_data_reads_the_clock():
    """Two runs over one snapshot hash the same whoever runs them; the docs that say so name the reports whose
    sealed data reads the generation clock (T270-2 measures one; a dormant cutoff or a change window moves too)."""
    reads = {name for name, (_, build) in REGISTRY.items() if "ctx.now" in inspect.getsource(inspect.getmodule(build))}
    assert reads == CLOCK_DERIVED, reads ^ CLOCK_DERIVED
    changelog = (DOCS / "CHANGELOG.md").read_text()
    bullet = changelog[changelog.index("- **A report's sha256 covers its data only (#270"):]
    design = (DOCS / "DESIGN_reporting_service.md").read_text()
    paragraph = design[design.index("**What the sha256 covers (SPEC_F1, #270).**"):]
    for where, text in (("CHANGELOG.md", bullet[:bullet.index("\n\n")]),
                        ("DESIGN", paragraph[:paragraph.index("\n\n")])):
        assert not [n for n in sorted(CLOCK_DERIVED) if f"`{n}`" not in text], where
    assert "generation clock" in model.__doc__ and "generation clock" in model.Report.canonical.__doc__


```

```python


def test_t592_2_no_report_reads_the_generation_clock_into_its_data():
    """#592: no builder reads `ctx.now` (page one, in common.py, does: Generated at and the snapshot's age); the five
    that end a window, a cutoff or an overdue state at the snapshot's stamp are named where the seal is described.
    Without the change those five read `ctx.now`, and the model's docstrings promise less."""
    sources = {name: inspect.getsource(inspect.getmodule(build)) for name, (_, build) in REGISTRY.items()}
    assert not [name for name, source in sources.items() if "ctx.now" in source]
    assert {name for name, source in sources.items() if "ctx.snapshot_at" in source} == set(SNAPSHOT_CLOCK)
    design = (DOCS / "DESIGN_reporting_service.md").read_text()
    paragraph = design[design.index("**What the sha256 covers (SPEC_F1, #270).**"):]
    paragraph = paragraph[:paragraph.index("\n\n")]
    assert "end at the\nsnapshot's stamp, not at the generation time" in paragraph and "generation clock" not in paragraph
    assert not [n for n in sorted(SNAPSHOT_CLOCK) if f"`{n}`" not in paragraph]
    assert "generation clock" not in model.__doc__ and "generation clock" not in model.Report.canonical.__doc__


```

### Block 27 — `local-development/tests/test_report_diff.py` (1 of 4): the imports; `CLOCK_MOVED` goes

<!-- block: local-development/tests/test_report_diff.py | edit -->

```python
from gsd.reporting.snapshot import Snapshot
from reporting_seed import CLUSTER, NOW, seed_store, write_snapshot
from test_report_seal import CLOCK_DERIVED, _other_run, _run, snap  # noqa: F401 — `snap` is a fixture
from test_reporting_server import SERVICE, _viewer, _wait_done, service  # noqa: F401 — `service` is a fixture

DIFF = "report-diff"
#: What the five clock-reading reports show when the clock moves two hours over one snapshot (measured, §2.3).
CLOCK_MOVED = {
    "login-activity": {("Summary", "Window")},
    "groups": set(),
    "dormant-access": set(),
    "groupsync-health": {("GroupSync CRs", "CRs"), ("Summary", "Pipeline")},
    "compliance-snapshot": {("Key figures", "Sync pipeline")},
}


```

```python
from gsd.reporting.snapshot import Snapshot
from reporting_seed import CLUSTER, NOW, seed_store, write_snapshot
from test_report_seal import _other_run, _run, _page_one, snap  # noqa: F401 — `snap` is a fixture
from test_reporting_server import SERVICE, _viewer, _wait_done, service  # noqa: F401 — `service` is a fixture

DIFF = "report-diff"


```

### Block 28 — `local-development/tests/test_report_diff.py` (2 of 4): T108-2 covers all eleven reports

<!-- block: local-development/tests/test_report_diff.py | edit -->

```python


@pytest.mark.parametrize("name", sorted(set(REGISTRY) - CLOCK_DERIVED))
def test_t108_2_two_runs_over_one_snapshot_diff_to_no_change(snap, name):  # noqa: F811
    """The six clock-free reports: another viewer, run id and minute, one snapshot: nothing changed, because page
    one (who and when) is not sealed data. Without SPEC_F3: ModuleNotFoundError."""
    diff = _build(_doc(_run(snap, name)), _doc(_other_run(snap, name)))
    assert _changed(diff) == set(), name
```

```python


@pytest.mark.parametrize("name", sorted(REGISTRY))
def test_t108_2_two_runs_over_one_snapshot_diff_to_no_change(snap, name):  # noqa: F811
    """Every report: another viewer, run id and minute, one snapshot: nothing changed, because page one (who and
    when) is not sealed data and a report's data ends at the snapshot's stamp (#592). Without SPEC_F3:
    ModuleNotFoundError; without #592, login-activity's Window `To` moves with the minute."""
    diff = _build(_doc(_run(snap, name)), _doc(_other_run(snap, name)))
    assert _changed(diff) == set(), name
```

### Block 29 — `local-development/tests/test_report_diff.py` (3 of 4): #589's test: the second copy has its own instant

<!-- block: local-development/tests/test_report_diff.py | edit -->

```python
    directory.mkdir()
    try:
        first, second = Snapshot(write_snapshot(store, directory)), Snapshot(write_snapshot(store, directory))
    finally:
        store.close()
```

```python
    directory.mkdir()
    try:
        first = Snapshot(write_snapshot(store, directory))
        second = Snapshot(write_snapshot(store, directory, at=NOW + timedelta(minutes=5)))
    finally:
        store.close()
```

### Block 30 — `local-development/tests/test_report_diff.py` (4 of 4): T607-1 and T607-2 replace T108-3

<!-- block: local-development/tests/test_report_diff.py | edit -->

```python


@pytest.mark.parametrize("name", sorted(CLOCK_DERIVED))
def test_t108_3_a_clock_reading_report_shows_what_the_clock_moved(snap, name):  # noqa: F811
    """The five reports that read the generation clock: two hours apart over one snapshot, the diff shows exactly
    the blocks computed against the clock (CLOCK_MOVED, measured), and nothing else. Without SPEC_F3:
    ModuleNotFoundError."""
    later = _run(snap, name, now=NOW + timedelta(hours=2), run_id="20260906T140000.000000Z-cd34")
    assert _changed(_build(_doc(_run(snap, name)), _doc(later))) == CLOCK_MOVED[name], name


```

```python


def _a_later_poll_and_read(tmp_path: Path, monkeypatch) -> tuple[Snapshot, Snapshot, str]:
    """Two snapshots of one seeded database that differ only in the poll and login-capture read instants (#607):
    the first polled and stamped at the seed's NOW, the second five minutes later after one more successful poll
    and one more read."""
    import gsd.store
    monkeypatch.setattr(gsd.store, "now_iso", lambda: NOW.strftime("%Y-%m-%dT%H:%M:%SZ"))
    store = seed_store(str(tmp_path / "writer.db"))
    directory = tmp_path / "snapshots"
    directory.mkdir()
    later = (NOW + timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        first = Snapshot(write_snapshot(store, directory))
        monkeypatch.setattr(gsd.store, "now_iso", lambda: later)
        store.record_poll(CLUSTER, "ok", None)
        store.record_login_read(CLUSTER, later)
        second = Snapshot(write_snapshot(store, directory, at=NOW + timedelta(minutes=5)))
    finally:
        store.close()
    return first, second, later


def test_t607_1_compliance_snapshot_diffs_to_no_change_across_a_new_poll_and_read(tmp_path, monkeypatch):
    """#607: the poll's and the read's instants are on page one, not in a sealed section, so two snapshots of the
    same data diff to "No change"; page one still shows both instants. Without the change the diff shows
    `Key figures — Sync pipeline` (Last poll) and `What this evidence attests — Coverage` (last read)."""
    first, second, later = _a_later_poll_and_read(tmp_path, monkeypatch)
    try:
        base, head = _run(first, "compliance-snapshot"), _other_run(second, "compliance-snapshot")
    finally:
        first.close()
        second.close()
    assert (base.provenance["last_poll"], head.provenance["last_poll"]) == ("2026-09-06T12:00:00Z", later)
    assert _changed(_build(_doc(base), _doc(head))) == set()
    page_one = head.sections[0]
    assert _page_one(head)["Last poll"] == f"{later} — ok"
    assert any(b.kind == "note" and f"(last read {later})" in b.text for b in page_one.blocks)


def test_t607_2_login_activity_shows_only_its_window_moving_across_a_new_poll_and_read(tmp_path, monkeypatch):
    """#607 and #592 together: login-activity's window ends at each snapshot's stamp, so two snapshots five minutes
    apart change its From and To and nothing else; the last log read is on page one only. Without the change the
    Window block also removes and adds `Last log read`."""
    first, second, later = _a_later_poll_and_read(tmp_path, monkeypatch)
    try:
        base, head = _run(first, "login-activity"), _other_run(second, "login-activity")
    finally:
        first.close()
        second.close()
    diff = _build(_doc(base), _doc(head))
    assert _changed(diff) == {("Summary", "Window")}
    removed, added = next(s for s in diff.sections if s.title == "Summary — Window").blocks
    assert [row[0] for row in removed.rows] == [row[0] for row in added.rows] == ["From", "To"]
    assert ["To", "2026-09-06T12:05:00Z"] in added.rows
    assert any(b.kind == "note" and f"(last read {later})" in b.text for b in head.sections[0].blocks)


```

### Block 31 — `local-development/tests/test_ui.py` (1 of 4): the PDF download walk ticks PDF

<!-- block: local-development/tests/test_ui.py | edit -->

```python
            page.fill("#report-lookup-namespace-access-namespaces", "prod-ns"); page.press("#report-lookup-namespace-access-namespaces", "Enter")
            page.wait_for_selector('.rp-tag[data-name="prod-ns"]')
            gen = page.locator("#report-generate")
            gen.focus()
```

```python
            page.fill("#report-lookup-namespace-access-namespaces", "prod-ns"); page.press("#report-lookup-namespace-access-namespaces", "Enter")
            page.wait_for_selector('.rp-tag[data-name="prod-ns"]')
            page.check("#report-want-pdf")              # #593: the form starts with HTML only; this walk downloads the PDF
            gen = page.locator("#report-generate")
            gen.focus()
```

### Block 32 — `local-development/tests/test_ui.py` (2 of 4): the Generate label starts at "HTML · JSON"

<!-- block: local-development/tests/test_ui.py | edit -->

```python

    def test_generate_label_follows_the_format_boxes(self, browser, reporting_server):
        # #577: defaults, each change, and a repaint all name the selected formats in box order.
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.goto(base + "#page=reports&cluster=crc-local&report=groups")
            page.wait_for_selector("#report-want-csv")
            label = page.locator("#report-generate span")
            assert page.is_checked("#report-want-pdf") and page.is_checked("#report-want-html")
            assert not page.is_checked("#report-want-csv")
            assert label.inner_text() == "PDF · HTML · JSON"
            page.uncheck("#report-want-pdf")
```

```python

    def test_generate_label_follows_the_format_boxes(self, browser, reporting_server):
        # #577: defaults, each change, and a repaint all name the selected formats in box order; #593: HTML only at first.
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.goto(base + "#page=reports&cluster=crc-local&report=groups")
            page.wait_for_selector("#report-want-csv")
            label = page.locator("#report-generate span")
            assert page.is_checked("#report-want-html") and not page.is_checked("#report-want-pdf")
            assert not page.is_checked("#report-want-csv")
            assert label.inner_text() == "HTML · JSON"
            page.check("#report-want-pdf")
            assert label.inner_text() == "PDF · HTML · JSON"
            page.uncheck("#report-want-pdf")
```

### Block 33 — `local-development/tests/test_ui.py` (3 of 4): T593-1: the form opens reading "Generate HTML · JSON"

<!-- block: local-development/tests/test_ui.py | edit -->

```python
            assert label.inner_text() == "JSON"
            assert "json is always written" in page.locator(".report-actions").inner_text()
            assert not errors, errors
        finally:
```

```python
            assert label.inner_text() == "JSON"
            assert "json is always written" in page.locator(".report-actions").inner_text()
            assert not errors, errors
        finally:
            ctx.close()

    def test_the_form_opens_with_html_only_ticked(self, browser, reporting_server):
        # #593, the operator's decision: the Reports form starts with only HTML ticked, so it opens reading
        # "Generate HTML · JSON" and a Generate untouched asks for HTML alone (JSON is always written). Without the
        # change it opens reading "Generate PDF · HTML · JSON" and posts ["html", "pdf"].
        import json as _json
        base, _, _ = reporting_server
        ctx, page, errors = _reports_page(browser, base, "root")
        try:
            page.goto(base + "#page=reports&cluster=crc-local&report=groups")
            page.wait_for_selector("#report-want-pdf")
            assert " ".join(page.locator("#report-generate").inner_text().split()) == "Generate HTML · JSON"
            assert [page.is_checked(f"#report-want-{f}") for f in ("pdf", "html", "csv")] == [False, True, False]
            with page.expect_request(lambda r: r.url.endswith("/api/runs") and r.method == "POST") as info:
                page.click("#report-generate")
            assert _json.loads(info.value.post_data)["formats"] == ["html"]
            assert not errors, errors
        finally:
```

### Block 34 — `local-development/tests/test_ui.py` (4 of 4): the repaint test flips every box from its default

<!-- block: local-development/tests/test_ui.py | edit -->

```python
            page.wait_for_selector("#report-want-csv")
            page.check("#report-want-csv")
            page.uncheck("#report-want-pdf")
            page.click('[data-switch="include_members"]')
            page.wait_for_selector('[data-switch="include_members"][aria-checked="true"]')
            assert page.is_checked("#report-want-csv") and not page.is_checked("#report-want-pdf"), "the repaint undid the reader's boxes"
            with page.expect_request(lambda r: r.url.endswith("/api/runs") and r.method == "POST") as info:
                page.click("#report-generate")
            assert _json.loads(info.value.post_data)["formats"] == ["html", "csv"]
            assert not errors, errors
        finally:
```

```python
            page.wait_for_selector("#report-want-csv")
            page.check("#report-want-csv")
            page.check("#report-want-pdf")              # #593: the reader flips every box from its default
            page.uncheck("#report-want-html")
            page.click('[data-switch="include_members"]')
            page.wait_for_selector('[data-switch="include_members"][aria-checked="true"]')
            assert [page.is_checked(f"#report-want-{f}") for f in ("pdf", "html", "csv")] == [True, False, True], \
                "the repaint undid the reader's boxes"
            with page.expect_request(lambda r: r.url.endswith("/api/runs") and r.method == "POST") as info:
                page.click("#report-generate")
            assert _json.loads(info.value.post_data)["formats"] == ["pdf", "csv"]
            assert not errors, errors
        finally:
```

### Block 35 — `docs/DESIGN_reporting_service.md`: what the sha256 covers

<!-- block: docs/DESIGN_reporting_service.md | edit -->

```markdown
generated by, the run id, the snapshot's age, the report service's version and commit, the marking, the binding
interval and the PDF variant and font are run facts, outside the hash. So two runs over one snapshot with the same
parameters hash the same, whoever runs them, while the values a report computes against the generation clock
coincide: `login-activity`'s window ends at the generation instant, so two of its runs agree only at one clock;
`groupsync-health` and `compliance-snapshot` compute the overdue state against it, `groups`, `groupsync-health` and
`compliance-snapshot` count changes in a window that ends at it, and `dormant-access` sets its cutoff from it
(SPEC_F1, Orchestrator's notes 1). The coverage can also reflect two report-service settings
(`login_capture_enabled`, `namespaces_read_enabled`), so a run under other settings is other evidence. A new
snapshot is new evidence and hashes differently. The `.json` carries every section, page one with `"sealed": false`,
```

```markdown
generated by, the run id, the snapshot's age, the report service's version and commit, the marking, the binding
interval and the PDF variant and font are run facts, outside the hash. So two runs over one snapshot with the same
parameters hash the same, whoever runs them and whenever: a report's windows, cutoffs and overdue states end at the
snapshot's stamp, not at the generation time (#592, SPEC_F7). `login-activity`'s window ends at the stamp,
`groupsync-health` and `compliance-snapshot` compute the overdue state at it, `groups`, `groupsync-health` and
`compliance-snapshot` count changes in a window that ends at it, and `dormant-access` sets its cutoff from it. Page
one's "Generated at" stays the generation time: it describes the run. The instants of the last poll and of the
login-capture read are on page one, not in a sealed section, so a diff never shows them as a change (#607). The
coverage can also reflect two report-service settings
(`login_capture_enabled`, `namespaces_read_enabled`), so a run under other settings is other evidence. A new
snapshot is new evidence and hashes differently. The `.json` carries every section, page one with `"sealed": false`,
```

### Block 36 — `charts/group-sync-dashboard/Chart.yaml` (1 of 2): chart 0.70.2 and its history line

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```yaml
# CHART 0.70.1 (2026-10-04), PATCH: appVersion moves to application 5.0.0 (below); Epic F: reports,
# honest seals, more formats, diffs and delivery (#386).
version: 0.70.1
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
# id or display name — and a Find member box on the group page. /users rows gain `full_name`,
```

```yaml
# CHART 0.70.1 (2026-10-04), PATCH: appVersion moves to application 5.0.0 (below); Epic F: reports,
# honest seals, more formats, diffs and delivery (#386).
# CHART 0.70.2 (2026-10-04), PATCH: appVersion moves to application 5.1.0 (below); the reports' clock is the
# snapshot's (#592, #607, #593; SPEC_F7). No template, default or RBAC change.
version: 0.70.2
# 0.8.0 (2026-09-03). A Users tab — every user with a synced membership, filtered as you type on
# id or display name — and a Find member box on the group page. /users rows gain `full_name`,
```

### Block 37 — `charts/group-sync-dashboard/Chart.yaml` (2 of 2): application 5.1.0's history line

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

```yaml
# 4.7.0 (2026-10-04). The Tech debt sweep: the Generate label, the KPI cards on a phone, no PDF on schedules, the recovery script's SIGTERM, the Reports description, report-diff order, access-certification's sealed stamp, two stale names, cron day and month names, the release note's schema line, the walk's interpreter, the README and the cosign version (#577 #546 #548 #594 #555 #587 #588 #589 #590 #585 #543 #591 #545 #535). MINOR.
# 5.0.0 (2026-10-04). Epic F: reports, honest seals, more formats, diffs and delivery (#386). MAJOR.
appVersion: "5.0.0"

keywords: [openshift, ldap, rbac, groupsync, observability]
```

```yaml
# 4.7.0 (2026-10-04). The Tech debt sweep: the Generate label, the KPI cards on a phone, no PDF on schedules, the recovery script's SIGTERM, the Reports description, report-diff order, access-certification's sealed stamp, two stale names, cron day and month names, the release note's schema line, the walk's interpreter, the README and the cosign version (#577 #546 #548 #594 #555 #587 #588 #589 #590 #585 #543 #591 #545 #535). MINOR.
# 5.0.0 (2026-10-04). Epic F: reports, honest seals, more formats, diffs and delivery (#386). MAJOR.
# 5.1.0 (2026-10-04). A report's windows, cutoffs and overdue states end at the snapshot's stamp, not the generation time (#592); compliance-snapshot and login-activity keep the last poll's and the last read's instants out of their sealed sections (#607); the Reports form starts with only HTML ticked (#593). MINOR.
appVersion: "5.1.0"

keywords: [openshift, ldap, rbac, groupsync, observability]
```

### Block 38 — `local-development/pyproject.toml`: application 5.1.0

<!-- block: local-development/pyproject.toml | edit -->

```toml
# gets a KeyError after this upgrade, which is a contract change and not a patch — administrators
# are unaffected, byte-for-byte.
version = "5.0.0"
description = "Read-only multi-cluster dashboard for the redhat-cop group-sync-operator"
requires-python = ">=3.11"
```

```toml
# gets a KeyError after this upgrade, which is a contract change and not a patch — administrators
# are unaffected, byte-for-byte.
version = "5.1.0"
description = "Read-only multi-cluster dashboard for the redhat-cop group-sync-operator"
requires-python = ">=3.11"
```

### Block 39 — `local-development/gsd/__init__.py`: application 5.1.0

<!-- block: local-development/gsd/__init__.py | edit -->

```python
# endpoint answers confidently either way. tests/test_chart_versions.py holds the two together;
# before that test existed nothing did.
__version__ = "5.0.0"

# THE ONE PLACE THE DASHBOARD IS NAMED. The page title, the header, the signed-out page and
```

```python
# endpoint answers confidently either way. tests/test_chart_versions.py holds the two together;
# before that test existed nothing did.
__version__ = "5.1.0"

# THE ONE PLACE THE DASHBOARD IS NAMED. The page title, the header, the signed-out page and
```

### Block 40 — `docs/CHANGELOG.md`: the Unreleased entry

<!-- block: docs/CHANGELOG.md | edit -->

```markdown
last release sit under `## Unreleased` until the release that carries them replaces that heading —
which `local-development/prepare-release.py` does when the release is cut.

## Application 5.0.0 — chart 0.70.1 — 2026-10-04
```

```markdown
last release sit under `## Unreleased` until the release that carries them replaces that heading —
which `local-development/prepare-release.py` does when the release is cut.

## Unreleased

- **The reports' clock is the snapshot's (#592, #607, #593, `docs/specs/SPEC_F7_snapshot_clock.md`; application 5.1.0,
  chart 0.70.2).** A report's windows, cutoffs and overdue states now end at the snapshot's stamp, not at the
  generation time: `login-activity`'s window (its `To` is the stamp), the change windows of `groups`,
  `groupsync-health` and `compliance-snapshot`, the overdue state of `groupsync-health` and `compliance-snapshot`, and
  the dormancy cutoff of `dormant-access`. Two runs over one snapshot now hash the same at any generation time. Page
  one's "Generated at" is still the generation time. `compliance-snapshot`'s sealed sections no longer carry the last
  poll's instant (Key figures, Sync pipeline: "Last poll status" now) or the login-capture read's instant (the
  Coverage table's WHEN answer), and `login-activity`'s Window no longer carries "Last log read". Page one still shows
  both instants, and the hash still covers them through `sealed_provenance` and the coverage, which a diff does not
  compare. So a diff of two `compliance-snapshot` runs over snapshots that differ only in those instants reads "No
  change". **The sha256 of `compliance-snapshot`, `login-activity` and `groupsync-health` changes once** over the same
  data, because their sealed rows or words changed (`groupsync-health`'s caveat now says the state is computed at the
  snapshot's stamp). `groups` and `dormant-access` hash as before unless a membership change or a last login falls
  between the snapshot's stamp and the generation time, which the earlier window counted differently. The other six
  reports' hashes do not change, and stored runs are not rewritten. The Reports form now starts with only HTML ticked
  ("Generate HTML · JSON"); PDF and CSV start unticked, and the reader's choices still survive a repaint. No
  permission, value or migration.

## Application 5.0.0 — chart 0.70.1 — 2026-10-04
```
