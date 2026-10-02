# SPEC E7 — the schema line in the release note, and the runbook's standard before every upgrade (#300)

| | |
|---|---|
| Programme | Epic E (#385), restore tools and release safety; build-order step 6 of 9, the last of the restore rows. It describes the tools of SPEC_E2 (#303, recovery mode) and SPEC_E3 (#302, `restore-db.sh`), which merge before it, and rewrites three passages of SPEC_E2's runbook text (Orchestrator's notes, 2) |
| Batch | E — restore tools and release safety |
| Release | — (post-programme; Epic E's release, milestone 3.0.0) |
| Version on release | no version change (a repository tool, tests and docs) |
| Version note | `local-development/prepare-release.py`, `local-development/tests/`, `docs/` and `.claude/` are outside `publish.yml`'s image paths (`.github/workflows/publish.yml#ONLY WHEN SOMETHING THAT GOES INTO THE IMAGE CHANGED`), and no block touches `charts/**`, so neither the application nor the chart version moves: the issue's "Target version: none" |
| Issue | [#300](https://github.com/ephico2real2/group-sync-dashboard/issues/300) |
| Status | merged |
| Source | OB1-lite's research and specification of 2026-10-01, written before any code from the issue's "Decisions and corrections (2026-10-01)" and its comment of the same day (the reason stays the first bullet). Measured on origin/main `b5463d45` (application 2.0.0, chart 0.59.25, schema 20) with Python 3.14.7, SQLite 3.53.4, git 2.55.0 and helm v4.3.0, and read-only on the CRC lab (OpenShift 4.22.7, image 2.0.0). §7's blocks were cut from a throwaway tree of `b5463d45` with SPEC_E2, SPEC_E3 (at `159deef8`), SPEC_E4 and SPEC_E5 (at `a5103cd6`) applied first, the epic's build order, and proved there and on three narrower bases. Revised the same day on OB2's review (Orchestrator's notes, 9) and rebased onto origin/main `eade4c2a` (SPEC_E3 and SPEC_E6 merged as specs); §4.2 and §4.3 re-measured on `eade4c2a` with SPEC_E2's and SPEC_E3's blocks applied |

## How to read this spec

**The point in one sentence: when an application release's image will migrate the database, `prepare-release.py`
now says so in the changelog, directly under the release's reason, with the schema it leaves and the schema it
reaches; and the backup runbook gains a three-step check to run before every upgrade (§0), while its §4 opens with
the order recovery mode, `restore-db.sh`, recovery mode off, and stops and starts the app only through the release's
values file.**

§1 is the mandate. §2 is the research: each finding names its source, the sentence relied on, and what it settles;
lab reads carry the command and its output. §2a lists the alternatives the research turned up and maps each external
claim to the line of this repository that behaves accordingly. §3 is the design, one decision per subsection, with
the safety budgets. §4 maps every test case of the issue (T300-1 to T300-13) to a test and shows each new one failing
on a tree without the change. §5 is the walk the implementing pull request runs on the lab. §6 is what an operator
sees and what it costs. §7 is the whole change as implementation blocks (`docs/specs/README.md`, "Implementation
blocks"), applied after SPEC_E2's and SPEC_E3's with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E7_schema_line_and_runbook.md . --apply

Citations into the code use `path#anchor`; a line number, where one helps, is written as plain text against
`b5463d45`. Upstream sources are named with their URL and the date they were read, and the sentence relied on is
quoted; line numbers of upstream code come from `curl -s <raw-url> | nl -ba`. This spec's own row in the index moves
through the lifecycle by the orchestrator's hand; no block touches it.

**Words used below.** The *schema* of a tree is the highest target in `local-development/gsd/store.py#_MIGRATIONS`;
the running database carries it as `PRAGMA user_version`, and the image as `KNOWN_SCHEMA_VERSION`. The *release
commit* is the first-parent commit at which `pyproject.toml`'s version became HEAD's
(`local-development/prepare-release.py#schema_since_app_release`, #298). The *schema line* is the changelog bullet
this spec adds. The *stack* is main with the blocks of SPEC_E2 and SPEC_E3 applied, the tree #300's pull request will
meet: first measured on `b5463d45` with SPEC_E4 and SPEC_E5 as well, re-measured on `eade4c2a` with E2 and E3.

## Orchestrator's notes

Decisions taken while specifying, on "easy to manage, best practice", the corrections the research made to the
issue, and what this spec shares with the other Epic E specs. Each is applied in §3 and §7 and held by a test in §4.

1. **The issue's six decisions are followed; two are refined, with evidence.**
   - *1, where the line lands:* under the issue's MINOR heading, the version whose image first migrates. Measured
     on main: `schema_since_app_release` returns `('b40b5cf82a07255d80011676e072daf38ed5c734', 20, 20)` in 0.232 s,
     14 first-parent commits after "Merge pull request #495 … release/app-2.0.0", so the next MAJOR cut on main sees
     no move and writes no line. The epic skill's §6 step 2 lists the children's lines in the epic's GitHub release
     (block 12, §3.4).
   - *2, the shallow refusal:* raised before any edit and recorded in the docstring's "WHAT IT REFUSES" (block 2).
     **Refinement:** only an application release reads the history. A chart-only release builds no image, so it
     migrates nothing (`docs/RELEASING.md#A chart-only release`), and refusing it on a shallow clone would add a
     refusal with nothing to protect; `test_t300_6_a_chart_only_release_reads_no_history` holds that.
   - *3, the sandbox:* `FILES` gains `local-development/gsd/store.py` (block 8). Measured with the change applied
     and that one line removed: 14 of the file's 32 tests fail, 7 of them existing ones, every `--app` run refused
     with `git show <sha>:local-development/gsd/store.py failed: fatal: path … does not exist` (§4.2); with it, 32 of
     32 pass. The issue measured 8 of 22 with its own wiring of the call; this spec's reads the schema after the
     existing refusals, so the existing-branch test still meets its own refusal first.
   - *4, the two off-volume paths:* §0 step 2 reads whether the offsite CronJob exists and branches (§3.5).
   - *5, the from-schema:* the image's `KNOWN_SCHEMA_VERSION`, imported in the running pod, measured on the lab
     (`20`, §2.10). §1's snippet stays the check of the copy itself (step 2), not the source of the number: the
     newest backup can predate the last migration, and it is absent when `config.backup.enabled` is false. Reading
     the live file's header instead is refuted in §2.5.
   - *6, the free space:* **correction.** `/metrics`' `gsd_volume_disk_total_bytes − gsd_volume_disk_used_bytes` is
     the filesystem's free blocks including those reserved for root (`local-development/gsd/kpi/system.py#disk`
     computes used from `f_bfree`), while the store compares `shutil.disk_usage(directory).free`, which is
     `f_bavail` (`local-development/gsd/store.py#_pre_upgrade_copy`; CPython, §2.6). On ext4 the default reserve is
     5% (§2.6), so `/metrics` is an upper bound. §0 gives the exact number from the pod, the same call the store
     makes, and keeps `/metrics` as the `oc`-free bound. On the lab the two agree (xfs: `f_bfree == f_bavail`,
     measured).
2. **What this spec shares with SPEC_E2, SPEC_E3, SPEC_E4 and SPEC_E5, so the later one rebases mechanically.**

   | passage of `docs/RUNBOOK_backup_restore.md` | other spec's block | this spec's block | how they meet |
   |---|---|---|---|
   | §4's opening, between the heading and "The dashboard is the only writer" | SPEC_E3 block 4 inserts **The script, in recovery mode (#302)** and **Undo a restore** | 15 inserts **In order.** after the heading line | disjoint: block 15's Old text is the heading line alone, so either order applies (measured on `b5463d45`+E2 and on the stack). Block 15 and block 16 name E3's paragraph by its bold title; a rename there must be carried here |
   | §4, recovery mode's step 3 | SPEC_E2 block 14 writes it | 16 rewrites its first two lines | depends on E2 (merged as a spec on main) |
   | §4, **Without recovery mode** and its `oc scale` line | SPEC_E2 block 14 writes the sentence; `b5463d45` has the `oc scale` | 17 rewrites both | depends on E2 |
   | §4a's keep step and side-file paragraph, §4b's Python and S3 note | SPEC_E3 blocks 5 to 8 | none | untouched; T300-11 reads E3's keep step as written there |
   | §4b's helper pod `image:` line | none | 18 | on `b5463d45` and after E2 alike |
   | §4c's first sentence and `oc scale --replicas=1` | SPEC_E2 block 17 writes the sentence | 19 rewrites both | depends on E2 |
   | §4c's expected `/api/version`, and "Scale to 0" after #305's refusal | none | 20, 21 | on `b5463d45` and after E2 alike |
   | the opening list's on-volume and off-volume bullets, §2's expected log, §6 | SPEC_E4 block 24, SPEC_E5 blocks 14 to 17 | none | untouched |
   | §0 (new), before "What a successful backup looks like" | none | 14 | on any base |
   | `docs/CHANGELOG.md`, first under `## Unreleased` | SPEC_E2 block 18, SPEC_E3 block 10, SPEC_E4, SPEC_E5 | 13 | each Old text stays unique; the later-applied entry is first |

   So 19 of the 22 blocks apply to `b5463d45` itself, and all 22 to `b5463d45` with SPEC_E2's blocks, with or
   without E3, E4 and E5; re-measured the same on `eade4c2a`, with SPEC_E3 as merged (§4.3). Blocks 15 and 16 name `restore-db.sh` and E3's paragraph, so #300 is implemented
   after #302 as the epic orders it. SPEC_E2's own runbook tests (`test_t303_19_the_docs_name_the_switch_and_say_what_alerts`,
   `test_the_only_documented_path_is_the_values_file`) and SPEC_E3's (`test_the_runbook_removes_every_journal_it_keeps`,
   `test_runbook_explains_how_to_recover_a_kept_live_set`, `test_the_runbooks_undo_folds_the_kept_set_into_one_whole_file`)
   pass on the stack with this spec applied (§4.3).
3. **Correction to the issue: most of the §4 rewrite already exists in SPEC_E2 and SPEC_E3.** The issue (2026-09-30)
   predates both: SPEC_E2's block 14 makes recovery mode the primary path through the values file, its blocks 15 to
   17 move §4a, §4b and §4c into the recovery pod, and SPEC_E3's blocks 4 to 8 add the script, the way to undo a
   restore and the corrected keep steps. Replacing §4 wholesale would undo SPEC_E3's text, which the mandate
   forbids. What #300 still owns in §4, and does: the order at the top (block 15); step 3 pointing at the script
   (16); the fallback's writer stopped and started through the values file instead of `oc scale` (17, 19, 21); the
   two stale `0.15.0` lines (18, 20). The issue's third stale item, the keep step that kept `gsd.db` without its
   `-wal`, is SPEC_E3's block 5; T300-11 asserts it.
4. **Correction to SPEC_E2's fallback: `oc scale` becomes `replicaCount: 0` in the values file.** SPEC_E2 kept
   `oc scale -n $NS deploy/$REL --replicas=0` for "Without recovery mode"; the issue's item 6 and the operator's
   rule of 2026-10-01 say never `oc scale`, and the lab's Application tracks `main` with `selfHeal: true` (§2.8), so
   a hand scale is reverted mid-restore. Measured: `helm template` with `replicaCount=0` differs from the default
   render in three lines only, `replicas: 0`, the configuration's `replicaCount: 0` and the pod's
   `checksum/config`; the claim and its access mode do not move (`charts/group-sync-dashboard/templates/_helpers.tpl#gsd.accessMode`
   derives ReadWriteOncePod for both 0 and 1). `oc debug deploy/<name>` debugs a Deployment's pod template whatever
   its replicas (`oc debug --help`: "any controller resource that creates a pod (like a deployment …)").
5. **Correction to §4c's expected output.** `/api/version` prints compact JSON, measured on the lab:
   `{"leader":true,"version":"2.0.0","commit":"b40b5cf82a",…}`, not the spaced `{"leader": true, "version":
   "0.15.0", …}` the runbook shows. Block 20 writes the shape it prints and the version as "the application version
   the release now runs", which a pinned number would make stale again.
6. **The new code blocks in §0 use four backticks.** `local-development/apply-spec-blocks.py#FENCE` ends a block's
   fence at the first line of exactly three backticks, so no block can carry one. CommonMark closes a fence at "at
   least as many backticks or tildes as the opening code fence" (§2.9), so a block opened and closed with four
   renders as any other; measured with the `markdown-it` 14.3.0 bundled in `markdownlint-cli2`: §0's five fences
   parse as five `sh` code blocks. Tildes would read the same but add a `MD048` (code-fence style) warning to a file
   that uses backticks; four backticks add none (measured: `markdownlint-cli2` reports 6 issues in the runbook on the
   stack before and after, all pre-existing).
7. **Found while stacking, not this spec's, for the orchestrator.** SPEC_E4's block 24 and SPEC_E5's block 14 both
   edit the runbook's on-volume bullet; on `b5463d45`+E2+E3+E4, E5's block 14 fails ("Old text occurs 0 times"), so
   whichever is implemented second re-cuts its Old text. On the same stack two tests fail before and after this
   spec, as their own notes say they will until handled: `test_the_offsite_claim_is_mounted_exactly_when_the_cronjob_writes_one[default]`
   (SPEC_E5's note 1: SPEC_E2's block 3 must take `gsd.offsiteOn`) and `test_the_wrapper_is_executable` (SPEC_E3's
   note 13: `chmod +x` after `--apply`).
8. **The index.** Rebased onto `eade4c2a`, this spec adds the forty-fourth row, after E6's, and
   `local-development/tests/test_specs_index.py` excludes E7 from the rising-issue check by its id and pins it to
   #300 (`assert ROWS["E7"]["issue"] == "300"`), as it does E3, E5 and E6.
9. **OB2's review of 2026-10-01, decided by the orchestrator (all accepted; finder: OB2).**
   - **F1 (required): T300-1/2 seeded its changelog from the repository's.** On a release pull request's head the
     repository's `docs/CHANGELOG.md` has no `## Unreleased` (the release consumed it), and the test's
     `lines[5]` raised `IndexError` on `b40b5cf8`'s changelog (OB2 measured). The test now writes its own changelog
     with one collected bullet and asserts the whole entry: reason, the line, the collected bullet. The test without
     an `## Unreleased` heading stays.
   - **F2: what the helper cannot read is refused with the script's message.** `highest_migration` parses the
     store with `ast`, so a store that does not parse, or a `_MIGRATIONS` entry that is not a literal tuple, raised
     `SyntaxError`, `ValueError` or `AttributeError` past `run()` as a traceback. Block 4 catches those three
     beside `ReleaseError` and refuses ("so nothing was changed"), before any edit;
     `test_t300_6_an_unreadable_migrations_list_is_refused_before_anything_is_edited`.
   - **F3: a schema that fell is refused.** HEAD's highest target below the release commit's means the image
     would refuse (`StoreSchemaTooNew`) every database the released image migrated; the first version printed "no
     schema line" and cut the release. Block 4 refuses it before any edit, block 2's docstring says so;
     `test_t300_6_a_schema_that_fell_is_refused_before_anything_is_edited`.
   - **Prose:** §3.3 names the three refusals; §4.1's T300-6 row names the two tests; §4.2's counts are
     re-measured (11 failing before, 43 passing after); §2.3's GitLab quote follows upstream's "rolling back to".
10. **The review of PR #528 (2026-10-02), by OB2 in Codex's seat, decided by the orchestrator: F1 and F2 accepted,
    F3 not applied.**
    - **F1: an empty `_MIGRATIONS` entry was a traceback.** `highest_migration` reads `entry.elts[0]`
      (`local-development/prepare-release.py#highest_migration`), so `(),` raised `IndexError`, which block 4 did not
      catch. OB2 measured it on the head `2f643921`: `IndexError: list index out of range` from `entry.elts[0]`,
      exit 1. Block 4 now catches `IndexError` too, with a comment that names the empty entry. Block 9 runs
      `test_t300_6_an_unreadable_migrations_list_is_refused_before_anything_is_edited` twice, once with `*EXTRA,` and
      once with `(),`. Measured on `2f643921` with only the test change: the `[empty-tuple]` case fails ("so nothing
      was changed" is not in the Traceback) and `[starred]` passes. With block 4 changed, both pass.
    - **F2: §4 step 3 did not name the script's target.** `local-development/restore-db.sh` defaults `--namespace`
      and `--release` to `group-sync-dashboard` (lines 6, 7, 23 and 24), but the runbook's opening sets
      `NS=group-sync`. Block 16's step 3 now says "each with `--namespace $NS --release $REL` unless both are the
      script's defaults (`group-sync-dashboard`)", and block 22's `test_t300_10` asserts that phrase. Measured on
      `2f643921` with only the test change: `test_t300_10` fails on the new assert, and passes once block 16 is
      changed. SPEC_E3's own paragraph ("The script, in recovery mode (#302)") has the same omission. It is SPEC_E3's
      text and is not changed here.
    - **F3, not applied: the operator's open question (below).** OB2 measured that this programme's MINOR flow drops
      the schema line. The three MINORs since 2.0.0 (`2205888f` 2.1.0, `d3aa900a` 2.2.0, `91c5c0f1` 2.3.0) ran
      `prepare-release.py --app … --no-commit` on their branches and kept only Chart.yaml, `pyproject.toml` and
      `__init__.py` (SPEC_E6's note 14: "Epic E's release cuts the heading"). A line written on such a branch is
      therefore lost with the changelog edit, and the MAJOR cut later on `main` finds `then == now` and writes none.
      In OB2's clone, a migration 21 committed with version 2.4.0 and the changelog untouched gave this on
      `--app 3.0.0`: `schema  : 21 at 9b5385762f (application 2.4.0), 21 at HEAD; no schema line`. OB2 offered a
      guard in `tests/test_migration_needs_app_release.py`: when the commit that released HEAD's version carries a
      higher schema than the commit that released the version before it, `docs/CHANGELOG.md` must contain the exact
      `SCHEMA_LINE`. OB2 measured it passing on this history (2.3.0 at `c57f2927` and 2.2.0 at `721a78db` are both
      schema 20) and failing on the clone until the bullet is kept. OB2 also offered a matching sentence for block 11.
      None of this is built. It waits on the operator's answer to the open question below.
    - **Counts after the review.** With only the test blocks applied on a tree without the change, §4.2's run fails
      12, not 11: the parametrized T300-6 case adds one. With every block applied, the three files pass 44, not 43.

**Open question for the operator (not decided, not built).** Should CI also hold the schema line for a release
whose version is bumped by hand, without `prepare-release.py`? One way is a test that every changelog heading whose
image raised the schema carries the line. Today nothing else writes the line: the "App image changes bump the app
version" job checks the version fields (`local-development/check-app-version-bump.py`), not the changelog, and
`docs/RELEASING.md` (block 11) says a hand bump gets no line. This spec builds without it.

## 1. The mandate, and what is out of scope

The issue (#300, "What must be accomplished"):

1. When the highest `_MIGRATIONS` entry at HEAD is above the one at the previous application release,
   `prepare-release.py --app` writes one fixed line into the release's changelog entry, directly under the reason
   bullet: "**Schema N → M.** The first start on this image migrates the database one way; the pre-upgrade copy
   (#301) and `restore-db.sh` (#302) are the way back.", with the right numbers, a jump of more than one included.
2. No line when the schema did not move, and none on a chart-only release.
3. The script keeps its refusals and its all-or-nothing behaviour: the schema is read before anything is edited, and
   a failure to read it edits nothing; the existing release tests still pass.
4. `docs/RELEASING.md` says what the line means and when it appears.
5. Runbook §0 "Before every upgrade": take the off-volume copy and confirm it landed (§2 with the offsite CronJob,
   §3 without); note the `user_version` you upgrade from without opening the live file; know where #301's
   pre-upgrade copy will be written and that it needs free space of at least the database's size.
6. Runbook §4 around #303 and #302, the `oc debug` procedure kept as the fallback, set in the release's values file
   and rolled out through the pipeline, never `oc scale`, no Argo CD Application or ApplicationSet patch; the stale
   lines fixed (the `:0.15.0` image, the `"version": "0.15.0"`, the keep step without `-wal`).
7. §4 is still "Restore" and §6 still "Pre-upgrade copies": the store's refusals and `tests/test_migrations.py`
   cite them.
8. Every command in §0 and §4 is run once on the lab, its output in the evidence (§5).

And from the Decisions and corrections: the line follows the reason, reuses `schema_since_app_release`, lands under
the issue's MINOR, the epic skill's §6 step 2 lists the children's lines; the shallow refusal is new and raised
before any edit; the test sandbox copies `store.py`.

**Out of scope**, each owned elsewhere: recovery mode itself (#303, SPEC_E2) and the restore script (#302, SPEC_E3);
offsite on by default (#304, SPEC_E5); a GUI backup button (dropped on this issue, 2026-09-22: it would need `create`
on `batch/jobs`); restoring from S3 inside a script (the epic keeps §4b's S3 path manual); §5 of the runbook (moving
the data to a new claim), which still says "scale to zero" in prose and is not named by the issue; a CI check of the
line for hand-bumped releases (the open question above). No GUI, chart, RBAC or application change.

## 2. Research, measured

Every web source was fetched on 2026-10-01 with `curl` and read as text; the sentence relied on is quoted. Lab reads
ran against the release's pod `group-sync-dashboard-7b9485f499-jspfl` (image `quay.io/ephico2real/group-sync-dashboard:2.0.0`)
between 16:49Z and 17:07Z and wrote nothing on the cluster: each was an `oc get`, an `oc exec … ls`, `cat` of a
backup file, `curl` of `/api/version`, or a `python3.14 -c` that imports a constant, stats files or opens a backup
with `immutable=1`.

### 2.1 What a changelog owes an upgrader

**Source.** Keep a Changelog 1.1.0 (keepachangelog.com/en/1.1.0/), "Ignoring Deprecations": "When people upgrade
from one version to another, it should be painfully clear when something will break. … If you do nothing else, list
deprecations, removals, and any breaking changes in your changelog." "Inconsistent Changes": "By inconsistently
applying changes, your users may mistakenly think that the changelog is the single source of truth. It ought to be."
On yanked releases: "The [YANKED] tag is loud for a reason. It's important for people to notice it."

**Settles.** A one-way migration is the change an upgrader must not miss, so it belongs in the changelog entry of
the version that performs it, written every time (by the tool, not by memory), and visibly (bold, its own bullet).
Today's entries name migrations in prose when the author remembers ("schema migration 20", the issue's history).

### 2.2 Why the version number cannot carry it here

**Source.** Semantic Versioning 2.0.0 (semver.org): "MAJOR version when you make incompatible API changes"; "Major
version X (X.y.z | X > 0) MUST be incremented if any backward incompatible changes are introduced to the public API."

**Settles.** This repository versions the application MINOR per merged issue and MAJOR per closed epic
(`docs/RELEASING.md#Releasing`), and a migration ships with the next MINOR in its own pull request (#298's guard,
`local-development/tests/test_migration_needs_app_release.py#assert_schema_released`). So a one-way schema move rides a
MINOR; nothing in the number says it. The line is that signal.

### 2.3 How other projects flag an irreversible migration

- **Django** (docs.djangoproject.com/en/5.2/topics/migrations/): "A migration is irreversible if it contains any
  irreversible operations. Attempting to reverse such migrations will raise IrreversibleError". `RunPython`: "If
  reverse_code is None (the default), the RunPython operation is irreversible."
- **Rails** (guides.rubyonrails.org/active_record_migrations.html, 3.13): "Sometimes your migration will do something
  which is just plain irreversible; for example, it might destroy some data. In such cases, you can raise
  ActiveRecord::IrreversibleMigration in your down block."
- **GitLab** (`doc/update/plan_your_upgrade.md` on gitlab.com master): "Something might go wrong during an upgrade,
  so it's critical that you have a rollback plan. A proper rollback plan creates a clear path to bring a GitLab
  instance back to its last working state and comprises: The process to back up the instance. The process to
  restore the instance." `doc/update/package/downgrade.md` (re-read 2026-10-01 for the review): "At least a database
  backup created under the exact same version and edition you are rolling back to." and "The backup is required to
  revert the schema changes (migrations) made during the upgrade."
- **Argo CD** (argo-cd.readthedocs.io/en/stable/operator-manual/upgrading/overview/): "If you are upgrading from
  v1.3.0 to v1.5.2 please make sure to check upgrading details in both v1.3 to v1.4 and v1.4 to v1.5 upgrading
  instructions." "The major release introduces backward incompatible behavior changes. It is recommended to take a
  backup of Argo CD settings using the disaster recovery guide."

**Settles.** Django and Rails mark irreversibility in the migration code, for a developer running `migrate`
backwards; here no migration has a down path at all (`local-development/gsd/store.py#_migrate` applies forward only),
so every migration is one-way and SPEC_E3's `_MIGRATIONS` comment already says so. GitLab and Argo CD speak to the
operator, as this issue must: a backup taken before, at the version left (GitLab's "exact same version" is our "the
schema you leave"), and every intermediate note read (Argo CD's v1.3 → v1.4 → v1.5 is §0 step 1's "every entry
after the version you run, up to and including the one you deploy").

### 2.4 git: the release commit, and a shallow clone

**Source.** git-scm.com/docs/git-rev-list: "--first-parent: When finding commits to include, follow only the first
parent commit upon seeing a merge commit." git-scm.com/docs/git-rev-parse: "--is-shallow-repository: When the
repository is shallow print "true", otherwise "false"." git-scm.com/docs/git-clone: "--depth <depth>: Create a
shallow clone with a history truncated to the specified number of commits."

**Settles.** `schema_since_app_release` walks `rev-list --first-parent HEAD` to the commit whose first parent has
another version, and when the walk ends without one it asks `rev-parse --is-shallow-repository` and refuses on
`true` (lines 171-182 on `b5463d45`). A depth-1 clone is shallow even of a single commit (measured with git 2.55.0:
`git clone --depth 1 file://<a one-commit repository>`, then `rev-parse --is-shallow-repository` prints `true`), so
the sandbox's one commit is enough for T300-6.

### 2.5 SQLite: what `user_version` is, and why §0 does not read the live file

**Source.** sqlite.org/pragma.html: "The user_version pragma will get or set the value of the user-version integer
at offset 60 in the database header. The user-version is an integer that is available to applications to use however
they want. SQLite makes no use of the user-version itself." sqlite.org/fileformat.html, 1.3.14: "The 4-byte
big-endian integer at offset 60 is the user version … The user version is not used by SQLite." sqlite.org/uri.html:
"SQLite always opens immutable database files read-only and it skips all file locking and change detection on
immutable database files. If this query parameter … asserts that a database file is immutable and that file changes
anyway, then SQLite might return incorrect query results and/or SQLITE_CORRUPT errors." sqlite.org/wal.html, §2 (as
SPEC_E3 §2.1 quotes it): "The original content is preserved in the database file and the changes are appended into
a separate WAL file."

**Settles.** The number is the application's own cursor (`_migrate` reads and sets it), so the authority on what
the running database holds is the code that set it: while the pod runs, `user_version == KNOWN_SCHEMA_VERSION`,
because a newer database is refused at open (`local-development/gsd/store.py#StoreSchemaTooNew`) and an older one is
migrated up to it. Two shortcuts are refuted: §1's `immutable=1` snippet on the *live* file can read a changing file
wrongly by SQLite's own words, and reading the four header bytes of `gsd.db` can return the pre-migration number while
the changed page 1 still sits in `gsd.db-wal`. On the lab the live set had a 4,511,432-byte `-wal` at 16:49Z.

### 2.6 Free space: the number the store compares, and the one `/metrics` exports

**Source.** CPython `Lib/shutil.py` at tag v3.14.0 (`curl -s https://raw.githubusercontent.com/python/cpython/v3.14.0/Lib/shutil.py | nl -ba`),
lines 1449-1453:

    st = os.statvfs(path)
    free = st.f_bavail * st.f_frsize
    total = st.f_blocks * st.f_frsize
    used = (st.f_blocks - st.f_bfree) * st.f_frsize

man7.org mke2fs(8), `-m reserved-blocks-percentage`: "Specify the percentage of the file system blocks reserved for
the super-user. … The default percentage is 5%."

**This repository.** The store refuses the start when `shutil.disk_usage(directory).free` is below `PRAGMA
page_count × page_size` (`local-development/gsd/store.py#_pre_upgrade_copy`, "free space … MiB, database … MiB").
`/metrics`' `gsd_volume_disk_used_bytes` is `total − f_frsize × f_bfree` (`local-development/gsd/kpi/system.py#disk`).
The logical size SQLite reports is at most the main file plus the `-wal` (every page a WAL frame adds is one frame of
the `-wal`), so `os.stat` of the two bounds it without opening the database.

**Measured on the lab** (16:49Z to 16:55Z):

    $ oc exec … -- python3.14 -c '… shutil.disk_usage("/data") … os.statvfs("/data") …'
    disk_usage.free 25941950464 statvfs bfree*frsize 25941950464 bavail*frsize 25941950464 total 160456224768
    $ curl -sk https://group-sync-dashboard.apps-crc.testing/metrics | grep -E '^gsd_(volume_disk|build_info|sqlite_wal_bytes|backup_last)'
    gsd_build_info{branch="main",commit="b40b5cf82a",version="2.0.0"} 1.0
    gsd_sqlite_wal_bytes 4.511432e+06
    gsd_backup_last_success_timestamp_seconds 1.7908530643803718e+09
    gsd_volume_disk_used_bytes{component="dashboard"} 1.34517866496e+11
    gsd_volume_disk_total_bytes{component="dashboard"} 1.60456224768e+11
    $ oc exec … -- python3.14 -c 'import glob, os, shutil; print("free", …); print("databases", …)'
    free 25883918336
    databases 20317896

**Settles.** §0 step 3 prints the store's own number, `free`, and an upper bound of the store's `need`, `databases`;
on the lab `free` is about 1,274 times `databases`. `/metrics` gives the same free space (total − used =
25,938,358,272, 15 s after the pod's 25,941,950,464) on a filesystem without a root reserve, which is why it is the
`oc`-free bound and not the check.

### 2.7 The offsite Job, run by hand and read

**Source.** kubernetes.io, `kubectl create job`: "kubectl create job test-job --from=cronjob/a-cronjob"; "--from
string The name of the resource to create a Job from (only CronJob is supported)." kubectl
`pkg/polymorphichelpers/logsforobject.go` at `d1f17c3a` (`curl -s https://raw.githubusercontent.com/kubernetes/kubectl/master/pkg/polymorphichelpers/logsforobject.go | nl -ba`),
lines 131-142: with `--all-containers` the loop reads `t.Spec.InitContainers` first, then `t.Spec.Containers`.

**This repository.** The offsite Job's pod has the init container `stage` for the `s3` destination and the
container `ship` for `pvc` (`charts/group-sync-dashboard/templates/backup-offsite.yaml#initContainers`); the script
prints `copied … -> …` and `integrity_check ok; user_version N; …` after a copy, or `already shipped: … matches its
sidecar; nothing to copy` alone when the newest backup is already there
(`charts/group-sync-dashboard/scripts/offsite_backup.py#ship`). `activeDeadlineSeconds: 1800` bounds the Job
(`charts/group-sync-dashboard/values.yaml#activeDeadlineSeconds`).

**Settles.** §0 step 2 reads every container's log, so the confirming lines are found for either destination, and
waits as long as the Job may run. An "already shipped" run prints no `user_version`, so §0 accepts it as the
confirmation it is (the copy matched its sidecar).

### 2.8 Why a hand edit does not hold

**Source.** argo-cd.readthedocs.io/en/stable/user-guide/auto_sync/, "Automatic Self-Healing": "By default, changes
that are made to the live cluster will not trigger automated sync. To enable automatic sync when the live cluster's
state deviates from the state defined in Git, … setting the self-heal option to true in the automated sync policy".
The same page: "For an ApplicationSet managed application, changing the application's spec.syncPolicy.automated field
will, however, have no effect."

**Measured on the lab:** `oc get applications.argoproj.io -A` shows `group-sync-dashboard` tracking `main` with
`selfHeal: true` and the value file `../../environments/crc.yaml`.

**Settles.** An `oc scale` of the Deployment is a deviation from Git that self-heal reverts, and under an
ApplicationSet the Application's sync policy cannot be toggled to hold it. A value in the release's values file,
rolled out through the pipeline, is the one change that holds. Argo CD is cited for that reason only.

### 2.9 Code fences inside an implementation block

**Source.** spec.commonmark.org/0.31.2/, 4.5: "A code fence is a sequence of at least three consecutive backtick
characters (`) or tildes (~)." "The content of the code block consists of all subsequent lines, until a closing code
fence of the same type as the code block began with (backticks or tildes), and with at least as many backticks or
tildes as the opening code fence."

**Settles.** Orchestrator's notes, 6.

### 2.10 This repository and the lab, measured

- **Who calls the helper today:** `git grep -n schema_since_app_release` on `b5463d45` finds its definition (line
  156 of `local-development/prepare-release.py`) and three calls in `local-development/tests/test_migration_needs_app_release.py`;
  `run()` does not call it.
- **What the script writes today:** the heading and the reason bullet (`local-development/prepare-release.py#the reason goes first and the collected bullets follow it`),
  nothing about the schema; the issue measured a scratch clone with a no-op migration 21: `grep -c "Schema 20"` = 0.
- **The sandbox:** one commit, "baseline" (`local-development/tests/test_prepare_release.py#sandbox`), and `FILES`
  without `store.py`.
- **The changelog's shape:** one heading per version, bullets one blank line apart (the 2.0.0 entry has the epic
  first); `## Unreleased` holds the bullets merged since.
- **The runbook:** on `b5463d45`, `## 1.` to `## 6.` and no `## 0.`; `:0.15.0` pinned in §4b's helper pod;
  `"version": "0.15.0"` expected in §4c; `oc scale` to stop and start. On the stack, §4 already carries SPEC_E2's
  recovery mode and SPEC_E3's script (Orchestrator's notes, 3).
- **What cites the runbook's numbers:** the store's refusals "(docs/RUNBOOK_backup_restore.md §4; after an upgrade,
  the pre-upgrade copy in §6)" and "§6", pinned by `local-development/tests/test_migrations.py`; a chart refusal "§5"
  (`charts/group-sync-dashboard/templates/_helpers.tpl#§5 covers moving the data`); links to `#6-pre-upgrade-copies`
  from the chart README and the changelog, and to `#4c-bring-it-back-and-verify` from the changelog.
- **The lab, §0's commands** (16:49Z to 16:56Z):

      $ oc exec -n group-sync-dashboard deploy/group-sync-dashboard -c dashboard -- python3.14 -c 'from gsd.store import KNOWN_SCHEMA_VERSION; print(KNOWN_SCHEMA_VERSION)'
      20
      $ oc get cronjob -n group-sync-dashboard group-sync-dashboard-backup-offsite
      Error from server (NotFound): cronjobs.batch "group-sync-dashboard-backup-offsite" not found
      $ B=$(oc exec … python3.14 -c 'import glob; print(sorted(glob.glob("/data/backup/gsd-*.db"))[-1])'); echo $B
      /data/backup/gsd-20261001T111104.000930Z.db
      $ oc exec … -- cat "$B" > "$(basename "$B")"; sha256sum "$(basename "$B")"
      55ac0b743f7d39f3c1de6a0a5f6791fd20dd8ec15bd7c32b0b4293bf834e1397  gsd-20261001T111104.000930Z.db
      $ python3 -c '<§1 snippet>' gsd-20261001T111104.000930Z.db
      integrity_check: ok
      user_version: 20
      membership_event 1843
      sync_event 2590
      login_event 7950
      $ oc exec … -- curl -s http://127.0.0.1:8080/api/version
      {"leader":true,"version":"2.0.0","commit":"b40b5cf82a","branch":"main","dirty":false,…}

  The copy is 14,221,312 bytes on the workstation (macOS's `/sbin/sha256sum`), the same as the pod's listing. The
  pod also holds `curl` 8.22.0, which the runbook's opening list of the image's tools omits (out of scope here).
- **The lab's claims** (17:06Z), unchanged by anything this spec measured: `group-sync-dashboard-data`
  `f065b7a4-535c-4ef1-868c-58f5afee4953` (ReadWriteMany), `group-sync-dashboard-report-artifacts`
  `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`.

## 2a. Alternatives considered

| # | Option | Source | What it would cost here | Decision |
|---|---|---|---|---|
| A1 | `prepare-release.py --app` writes the line, reusing #298's helper | the issue; §2.1 | 13 lines in the script; the sandbox carries `store.py` | **chosen**: the tool every release already runs, at the moment the version moves, with the comparison CI already trusts |
| A2 | CI writes the line into the GitHub release body after the merge (`helm.yaml`) | Keep a Changelog, "What about GitHub Releases?": "GitHub Releases create a non-portable changelog" | a workflow that writes after merge, and a second place to read | rejected: the changelog is the source of truth (§2.1), and a release body is written after the image is already published |
| A3 | A CI test that every heading whose image raised the schema carries the line | the issue's open question | a parser over changelog history and the store at every release commit | not built: the operator's question (Orchestrator's notes) |
| A4 | Mark each migration reversible or irreversible in code (Django's `IrreversibleError`, Rails' `IrreversibleMigration`) | §2.3 | a field per migration, always "irreversible" | rejected: `_migrate` has no down path, so the mark would never vary; SPEC_E3 already states it once on `_MIGRATIONS` |
| A5 | A loud tag in the heading, Keep a Changelog's `[YANKED]` style (`## Application 2.1.0 — chart … — date — SCHEMA 20 → 21`) | §2.1 | the heading is matched by the script's own regexes and read by people and tests as `## Application X — chart Y — date` | rejected: a bullet adds the fact without changing a format other code reads |
| A6 | The line first, above the reason | the mock's first draft | — | rejected by the issue's comment of 2026-10-01: the reason goes first (`prepare-release.py`, the epic skill) |
| A7 | Per-version upgrade pages (GitLab "required upgrade stops", Argo CD "v1.3 to v1.4") | §2.3 | a page per release | rejected: one standing checklist (§0) plus one line per release carries the same facts at this repository's size |
| A8 | On a shallow clone: refuse (decision 2), warn and write no line, or `git fetch --unshallow` | §2.4 | — | **refuse**: no line would be a release cut blind, the failure this issue exists to prevent; fetching would make a release tool touch the network and the repository's refs, which the script never does ("never tags, never talks to a registry") |
| A9 | From-schema: the image's `KNOWN_SCHEMA_VERSION`; §1's snippet on the newest backup; the live file with `immutable=1` or `mode=ro`; the four header bytes | §2.5 | — | **the import**: exact while the pod runs and opens nothing; the backup can predate the last migration or be absent; the live file is what the issue says not to open and `immutable=1` can misread it; the header bytes can lag the `-wal` |
| A10 | Free space: the pod's `shutil.disk_usage`; `/metrics` total − used; `df` | §2.6 | — | **the pod's call**, the store's own; `/metrics` kept as the `oc`-free upper bound; `df` is not in the image |
| A11 | The fallback's stop: `replicaCount: 0` in the values file; `oc scale`; pausing Argo CD | §2.8 | — | **the values file**: the only change that holds under self-heal and an ApplicationSet; `oc scale` is reverted; an Argo CD step is outside the operator's rule |
| A12 | Fences in a block: four backticks; tildes; indented code | §2.9 | — | **four backticks**: no lint finding, same rendering (Orchestrator's notes, 6) |

**Reconciliation: research says X, the code does X at.**

| External claim | This repository |
|---|---|
| `--first-parent` follows only the first parent (§2.4) | `local-development/prepare-release.py#schema_since_app_release` runs `rev-list --first-parent HEAD`, the push order `publish.yml` compares (`test_the_release_is_the_merge_that_moved_the_version`) |
| `--is-shallow-repository` prints `true` on a shallow clone (§2.4) | the helper raises `ReleaseError(… fetch-depth: 0)` on `true`; block 4 wraps it as "so nothing was changed" before any edit; `test_t300_6_a_shallow_history_is_refused_before_anything_is_edited` |
| `user_version` is the application's integer; SQLite makes no use of it (§2.5) | `local-development/gsd/store.py#_migrate` walks `_MIGRATIONS` with it as the cursor; `local-development/prepare-release.py#highest_migration` parses the same list, held equal to `KNOWN_SCHEMA_VERSION` by `test_the_parse_reads_what_the_store_declares` |
| `immutable=1` on a changing file may read wrongly (§2.5) | §0 never opens the live file (T300-9 asserts no `sqlite3` in §0's code); §1's snippet stays for copies |
| `shutil.disk_usage().free` is `f_bavail`; `/metrics`' used is from `f_bfree` (§2.6) | `local-development/gsd/store.py#_pre_upgrade_copy` compares `shutil.disk_usage(directory).free`; `local-development/gsd/kpi/system.py#disk` exports `total − f_bfree`; §0 step 3 prints the first and names the second a bound |
| `--all-containers` reads init containers first (§2.7) | the `s3` destination's copy line is printed by the init container `stage` (`charts/group-sync-dashboard/templates/backup-offsite.yaml#initContainers`); §0's `oc logs … --all-containers` reads it |
| self-heal reverts live changes; an ApplicationSet's Application cannot toggle it (§2.8) | §4's fallback stops the writer with `replicaCount` in the values file (block 17); the rendered difference is three lines (Orchestrator's notes, 4) |
| a fence closes at as many backticks as it opened with (§2.9) | `local-development/apply-spec-blocks.py#FENCE` ends at exactly three; §0's fences use four |
| "painfully clear when something will break" (§2.1) | `local-development/prepare-release.py#SCHEMA_LINE`, bold, its own bullet, written by the tool on every release that moves the schema |

## 3. The design

### 3.1 When the line is written

An application release (`--app`) reads, after every existing refusal and before the first edit,
`schema_since_app_release(REPO)`: the release commit, its schema (`then`) and HEAD's (`now`). When `now > then`, the
entry carries the line; otherwise it does not, and the script prints which:

    schema  : 20 at b40b5cf82a (application 2.0.0), 21 at HEAD; the changelog entry says so
    schema  : 20 at b40b5cf82a (application 2.0.0), 20 at HEAD; no schema line

A chart-only release (`--chart` alone) builds no image, migrates nothing and reads no history. Under "minor per
issue" a migration's pull request runs `prepare-release.py --app <next MINOR> … --no-commit` on its branch, where HEAD
carries the migration and the version is still the last release's, so the line lands under that MINOR's heading; the
epic's MAJOR, cut later on `main`, finds HEAD's version already released with that schema and writes none (§3.4).
HEAD is the committed tree: the script has already refused a dirty one.

### 3.2 What the line says, and where

One constant, `SCHEMA_LINE`, the issue's words as one bullet line:

    - **Schema 20 → 21.** The first start on this image migrates the database one way; the pre-upgrade copy (#301) and `restore-db.sh` (#302) are the way back.

It goes directly under the reason bullet, one blank line apart like every bullet in the file, and the bullets
`## Unreleased` collected follow it; the same holds when there is no `## Unreleased` heading. One line, not wrapped,
so `grep '^- \*\*Schema '` finds every one (§3.4); the reason bullet is not wrapped either.

### 3.3 The new refusals

Three refusals, each raised after every existing one and before the first write, so `git status --porcelain` stays
empty and the exit is 1 (T300-6):

- **A history too shallow** to reach the release commit. The helper raises; `run()` re-raises it as

      ERROR: cannot tell whether application 2.1.0 migrates the database, so nothing was changed: history ends at <sha> before application 2.0.0 began; this needs the full history (actions/checkout fetch-depth: 0)

  CI's `tests` job already checks out with `fetch-depth: 0` for #298's guard, and a release is cut from a checkout
  of `main`.
- **A `store.py` the helper cannot read**, at HEAD or at the release commit: a `git show` that fails, a file that
  does not parse, a `_MIGRATIONS` entry that is not a literal tuple, a non-integer target. The same "cannot tell
  whether … so nothing was changed" message, with the helper's error after it, never a traceback. A release commit
  whose `store.py` has no `_MIGRATIONS` assignment reads as schema 0 (`highest_migration` returns 0); unreachable on
  this history, where every release commit carries the list.
- **A schema that fell:** HEAD's highest target below the release commit's. That image would refuse every database
  the released one migrated (`local-development/gsd/store.py#StoreSchemaTooNew`):

      ERROR: _MIGRATIONS reaches 20 at HEAD but 21 at <sha> (application 2.1.0), so this image would refuse every database that release migrated; nothing was changed

All three are recorded in "WHAT IT REFUSES" (block 2).

**Budget (B1), the script, scope: one run of `prepare-release.py` on the operator's checkout.**

| | before | after |
|---|---|---|
| files edited | Chart.yaml, CHANGELOG, and with `--app` pyproject and `__init__`, plus promoted specs | the same set |
| lines added to the CHANGELOG | heading + reason (+ blank) | the same, plus exactly one bullet and one blank line when `now > then` on `--app`; none otherwise |
| git calls before the first edit | `status`, `rev-parse --abbrev-ref`, `rev-parse --verify` | plus, on `--app` only: one `rev-list --first-parent`, one `git show` of `pyproject.toml` for HEAD and one per first-parent commit until the version changes, at most one `rev-parse --is-shallow-repository`, and two `git show` of `store.py`; all reads. Measured on `b5463d45` by counting the helper's calls: 16, 0, 2 and the one `rev-list`, in 0.232 s |
| refusals | the docstring's list | the same list, in the same order, plus three on `--app` only, before any edit: the shallow history, an unreadable `store.py`, a schema that fell |
| network, refs, tags | none | none |

### 3.4 The epic's release note

`.claude/skills/epic/SKILL.md` §6 step 2 gains: list every schema line the epic's children released, with

    awk '/^## Application [0-9]+\.0\.0 / && ++n == 2 {exit} /^## / {h = $0} /^- \*\*Schema / {print h; print $0}' docs/CHANGELOG.md

run on `main` after the release merged: it prints each heading with its line, from the top of the changelog to the
previous epic's MAJOR heading, and nothing when no child moved the schema ("No schema change"). Measured with macOS
`/usr/bin/awk` on a synthetic changelog of headings 3.0.0, 2.2.0 (Schema 21 → 22), Chart 0.61.0, 2.1.0 (Schema 20 →
21) and 2.0.0 (Schema 19 → 20): it printed the 2.2.0 and 2.1.0 pairs and stopped at 2.0.0; on today's changelog it
prints nothing.

### 3.5 Runbook §0, before every upgrade

A new section after the opening (where `NS` and `REL` are set) and before the pictures, three numbered steps, each
command in its own block, none stopping the dashboard:

1. **Whether the upgrade migrates, and the schema you leave.** Every changelog entry after the running version
   (`gsd_build_info`'s `version` on `/metrics`) up to the target that carries the schema line migrates on its first
   start. The schema you leave is `KNOWN_SCHEMA_VERSION`, imported in the running pod (A9); it is the `<from>` of
   the pre-upgrade copy's name.
2. **An off-volume copy, confirmed.** `oc get cronjob … $REL-backup-offsite` decides: with it, a Job from the
   CronJob (§2's run), waited for up to its `activeDeadlineSeconds`, its logs read across containers, confirmed by
   `copied …` with `integrity_check ok; user_version` equal to step 1's number, or `already shipped …`; without `oc`,
   §2's Prometheus query and the stale alert bound the scheduled copy's age. Without the CronJob, §3's `cat` of the
   newest on-volume backup to the workstation, `sha256sum`, and §1's snippet run locally. Either copy is the newest
   six-hourly backup; what changed later is in the live database and, when the schema moves, in the pre-upgrade copy.
3. **Where the pre-upgrade copy goes, and that it fits.** `/data/pre-upgrade/` (`/data/<pod-name>/pre-upgrade/`
   above one replica); `free` from `shutil.disk_usage("/data")` must be above `databases`, the summed size of every
   pod's `gsd.db` and `gsd.db-wal` (one level under `/data` covers the per-pod layout); `/metrics` total − used is the
   `oc`-free upper bound (A10).

**Budget (B2), §0, scope: one operator following §0 against one release.** Cluster writes: at most one Job, created
from the release's own CronJob and only when it exists; it runs under the CronJob's ServiceAccount and mounts what
the CronJob mounts. Everything else is a read: `oc get`, `oc exec` of `python3.14 -c` that imports a constant or
stats files, `cat` of a backup file, `curl` of the public `/metrics`. The live database is never opened (T300-9). No
RBAC, no ServiceAccount change, no chart value.

### 3.6 Runbook §4 opens with the order, and step 3 restores with the script

A paragraph, **In order.**, directly under `## 4. Restore`: recovery mode on through the values file with the image
you will restore under; `restore-db.sh` (SPEC_E3's paragraph, named by its bold title, which follows); recovery mode
off and §4c; §4a and §4b as the manual fallback; **Without recovery mode** for a chart that has none; and the rule:
every change through the values file and the pipeline, never `oc scale` or `oc set env`, because a self-healing GitOps
controller reverts a hand edit. SPEC_E2's step 3 then restores with `restore-db.sh --list` and `--from-version <ID>`
(it refuses with less than ten minutes of `recovery.ttl` left, SPEC_E3) and keeps §4a and §4b, through `oc exec` into
the recovery pod, as the fallback, with E2's "Check the time left first" sentence as it is.

### 3.7 The fallback stops and starts the writer through the values file

**Without recovery mode** (the fallback, and any chart before 0.60.0) sets `replicaCount: 0` in the values file and
rolls it out, then `oc wait --for=delete` and the `oc debug` pod of §4a or the helper pod of §4b; §4c sets it back
(`1`) the same way, or turns recovery mode off. The paragraph after #305's refusal says "Turn recovery mode on (§4)"
where it said "Scale to 0 (§4)", and "deploy the image that understands the first, by its `image.tag` in the values
file". §4b's helper pod takes "the Deployment's image" with the `oc get deploy … jsonpath` that prints it, and §4c
expects `/api/version`'s compact JSON with "the application version the release now runs".

**Budget (B3), §4, scope: one restore by one operator.** No new write path: the change replaces a hand write
(`oc scale`) that the GitOps controller undoes with a values change it keeps. No new grant, no RBAC change (the
dashboard ServiceAccount is untouched), no GUI action.

### 3.8 What does not change

- Section numbers: `## 4. Restore`, `## 5. Moving the data to a new claim (access mode change)` and `## 6.
  Pre-upgrade copies` keep their titles, so `§4`, `§5`, `§6` in the store, the chart and the tests, and the links to
  `#6-pre-upgrade-copies`, `#4-restore` and `#4c-bring-it-back-and-verify`, still resolve (T300-12).
- SPEC_E3's paragraphs, keep steps and removals, and SPEC_E2's recovery-mode steps 1, 2, 4 and 5, its alerts
  paragraph and its development line.
- `prepare-release.py`'s existing refusals and messages, their order, and its all-or-nothing commit; the helper
  itself is not edited.
- The manual restore commands of §4a and §4b (the fallback the issue keeps).

## 4. Tests

### 4.1 The issue's test cases

| ID | Test | Fails without the change because |
|---|---|---|
| T300-1 | `test_t300_1_2_a_release_after_a_migration_carries_the_schema_line_under_its_reason[1]`, on a changelog it seeds with one collected bullet; `test_t300_1_the_line_is_written_without_an_unreleased_heading_too` | `run()` writes no schema line: the entry's lines are the reason and the collected bullet only |
| T300-2 | `test_t300_1_2_…[2]`: two migrations, `Schema N → N+2` | as T300-1 |
| T300-3 | `test_t300_3_no_line_when_the_schema_did_not_move` | regression guard; it also asserts the new `; no schema line` print, which today's script lacks |
| T300-4 | `test_t300_4_no_line_on_a_chart_only_release` | regression guard: after a migration, `--chart` writes no line and prints no `schema  :` |
| T300-5 | block 8 (`FILES` gains `store.py`); no test removed or weakened | not a failing test: with the change and without that line, 14 of 32 fail, 7 of the 22 existing (§4.2) |
| T300-6 | `test_t300_6_a_shallow_history_is_refused_before_anything_is_edited`; `test_t300_6_an_unreadable_migrations_list_is_refused_before_anything_is_edited`; `test_t300_6_a_schema_that_fell_is_refused_before_anything_is_edited`; `test_t300_6_a_chart_only_release_reads_no_history` | today a shallow clone and a fallen schema release with no check (exit 0), and an unreadable entry is never read; the last is a guard of the refusals' scope |
| T300-7 | the file's existing 22 tests, unchanged, and `tests/test_migration_needs_app_release.py`'s 7 | regression guard |
| T300-8 | `test_t300_8_releasing_md_states_the_line_and_when_it_appears` | `docs/RELEASING.md` has no such text, and `prep.SCHEMA_LINE` does not exist |
| T300-9 | `test_t300_9_section_0_comes_first_and_covers_the_three_steps` | no `## 0.` heading |
| T300-10 | `test_t300_10_section_4_is_recovery_mode_and_the_script_with_oc_debug_as_the_fallback` | no **In order.** paragraph; an `oc scale` command line in §4; no `replicaCount: 0` |
| T300-11 | `test_t300_11_no_stale_version_and_the_fallback_keeps_the_wal` | `group-sync-dashboard:0.15.0` and `"version": "0.15.0"` are in the runbook; "Scale to 0" is in §4 |
| T300-12 | `test_t300_12_the_sections_the_code_cites_keep_their_numbers` | regression guard: fails on a renumbered §4, §5 or §6, a section the code cites that the runbook lacks, or a link to an anchor no heading makes |
| T300-13 | the lab walk, §5 | §0 does not exist and §4 has no scripted path |

### 4.2 Measured: each new test fails without the change, and passes with it

Re-measured after OB2's review on a throwaway worktree of `eade4c2a` with SPEC_E2's and SPEC_E3's blocks applied
(and `chmod +x local-development/restore-db.sh`, SPEC_E3's note 13), with only this spec's test blocks (6 to 9 and
22) applied, `PYTHONPATH=<tree>/local-development`:

    $ python -m pytest -q tests/test_prepare_release.py tests/test_runbook_backup_restore.py
    FAILED tests/test_prepare_release.py::test_t300_1_2_a_release_after_a_migration_carries_the_schema_line_under_its_reason[1]
    FAILED tests/test_prepare_release.py::test_t300_1_2_a_release_after_a_migration_carries_the_schema_line_under_its_reason[2]
    FAILED tests/test_prepare_release.py::test_t300_1_the_line_is_written_without_an_unreleased_heading_too
    FAILED tests/test_prepare_release.py::test_t300_3_no_line_when_the_schema_did_not_move
    FAILED tests/test_prepare_release.py::test_t300_6_a_shallow_history_is_refused_before_anything_is_edited
    FAILED tests/test_prepare_release.py::test_t300_6_an_unreadable_migrations_list_is_refused_before_anything_is_edited
    FAILED tests/test_prepare_release.py::test_t300_6_a_schema_that_fell_is_refused_before_anything_is_edited
    FAILED tests/test_prepare_release.py::test_t300_8_releasing_md_states_the_line_and_when_it_appears
    FAILED tests/test_runbook_backup_restore.py::test_t300_9_section_0_comes_first_and_covers_the_three_steps
    FAILED tests/test_runbook_backup_restore.py::test_t300_10_section_4_is_recovery_mode_and_the_script_with_oc_debug_as_the_fallback
    FAILED tests/test_runbook_backup_restore.py::test_t300_11_no_stale_version_and_the_fallback_keeps_the_wal
    11 failed, 25 passed in 15.42s

Each fails for the reason §4.1 gives: T300-1/2 on the entry (`reason, the line, then the collected bullets`), the
no-Unreleased case on its entry, T300-3 on the missing `; no schema line` print, the three T300-6 refusals on an exit
of 0 (`derived : chart …`, the release went through), T300-8 on `prep.SCHEMA_LINE` (`AttributeError`), and T300-9
to T300-11 on the runbook.

With all 22 blocks applied:

    $ python -m pytest -q tests/test_prepare_release.py tests/test_runbook_backup_restore.py tests/test_migration_needs_app_release.py
    43 passed in 14.74s

T300-5, measured with all blocks applied and block 8's `store.py` line removed from `FILES`:

    14 failed, 18 passed
    FAILED: the 7 existing --app tests (test_an_application_release_moves_all_four_fields_together,
      test_an_explicit_chart_version_wins_over_the_derived_patch,
      test_an_unreleased_heading_becomes_the_release_heading_and_keeps_its_bullets,
      test_a_failing_version_test_leaves_the_edits_and_commits_nothing, test_no_commit_edits_the_tree_and_stops,
      test_missing_gh_leaves_the_branch_and_says_so, test_a_release_promotes_merged_status_cells), each refused
      with "ERROR: cannot tell whether application 9.0.0 migrates the database, so nothing was changed: git show
      <sha>:local-development/gsd/store.py failed: fatal: path 'local-development/gsd/store.py' does not exist in
      '<sha>'"; and the 7 new tests that read or edit the sandbox's store

### 4.3 Measured: where the blocks apply, and what else runs

    $ python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E7_schema_line_and_runbook.md <tree>
    eade4c2a (main)                                FAIL block 16 (docs/RUNBOOK_backup_restore.md | edit): Old text occurs 0 times
    eade4c2a without blocks 16, 17 and 19          19 blocks check out across 7 files
    eade4c2a + SPEC_E2                             22 blocks check out across 7 files
    eade4c2a + SPEC_E2 + SPEC_E3 (as merged)       22 blocks check out across 7 files

The first version measured the same on `b5463d45`, `b5463d45` + E2, + E3, and with E4 and E5 (SPEC_E5 without its
version and index blocks and its block 14, Orchestrator's notes, 7). The applied tree equals, byte for byte, the tree
the blocks were cut from (`cmp` of the seven files: none differ).

On `eade4c2a` + E2 + E3 with every block applied, the other test files that read the runbook or call the helper:

    $ python -m pytest -q tests/test_docs_citations.py tests/test_migrations.py tests/test_chart_recovery_mode.py \
        tests/test_recovery_mode.py tests/test_restore_db.py tests/test_restore_db_wrapper.py \
        tests/test_restore_db_safety.py tests/test_chart_versions.py
    1739 passed, 19 skipped in 41.03s

The full hermetic suite was run on the first version's stack (`b5463d45` + E2 to E5): `3 failed, 7131 passed, 27
skipped, 5 xfailed`, the three failures the predecessors' and identical without this spec (E2's offsite-mount test,
E3's `chmod`, and G2's version cell once E5's renumbering blocks were left out). The review's fixes change only
blocks 2, 4 and 9 (`prepare-release.py` and its test file), whose files ran above, so the suite was not rerun.

In the spec worktree, `tests/test_specs_index.py` and `tests/test_docs_citations.py` pass with this spec and its index
row: `1700 passed, 22 skipped`. The pin holds: with E7's row and header mistyped as #301, the index test
fails on `('E7 is #300', '301')` (`1 failed, 93 passed` on a copy of the index and the spec).

## 5. On the lab

The walk the implementing pull request runs (T300-13), after SPEC_E2 and SPEC_E3 are merged and deployed, with
`release-crc.sh` (development): every command of §0 and §4 once, as the merged runbook prints it, each output saved
as text under `reports/<date>_runbook-schema-line-300/`, the restore's terminal as PNG.

1. **Before.** `oc get pvc -n group-sync-dashboard -o custom-columns=NAME:.metadata.name,UID:.metadata.uid` must read
   `f065b7a4-535c-4ef1-868c-58f5afee4953` and `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` (measured 17:06Z today).
2. **§0, step 1.** The `KNOWN_SCHEMA_VERSION` import (measured today: `20`), and `gsd_build_info` from `/metrics`
   (`version="2.0.0"` today).
3. **§0, step 2.** `oc get cronjob … $REL-backup-offsite`. Today it is `NotFound`, so the walk runs the copy-out
   (measured today, §2.10: the newest backup, its `sha256sum`, §1's snippet locally: `integrity_check: ok`,
   `user_version: 20`). Once SPEC_E5 has turned offsite on, the same walk runs the Job branch instead: the four
   commands, `Complete`, the `copied`/`integrity_check` lines.
4. **§0, step 3.** The free-space command (measured today: `free 25883918336`, `databases 20317896`) and the two
   `/metrics` gauges.
5. **§4, the scripted path.** In the lab's values file, `recovery.enabled: true` (and the image to restore under),
   rolled out by `release-crc.sh` (the lab's development path); `restore-db.sh --list`; `--from-version <ID>` of the
   newest backup; `recovery.enabled: false` rolled out; §4c's `oc rollout status` and `curl … /api/version`, whose
   output must match the shape §4c now shows; the row counts against §1's.
6. **§4, the fallback.** `replicaCount: 0` in the lab's values file, rolled out; `oc wait --for=delete`; §4a's
   `oc debug` body with the copy the walk restored in step 5 (it sets the database back to that copy and discards what
   the app wrote since step 5: the #300 walk's F4 measured `sync_event` 2776 → 2770 and `login_event` 7992 → 7968;
   corrected by SPEC_E10); `replicaCount: 1`,
   rolled out; §4c. Measured today, read-only: `helm template … --set replicaCount=0` renders and differs from the
   default render in `replicas`, the configuration's `replicaCount` and `checksum/config` only.
7. **After.** The PVC UIDs again, unchanged; `prepare-release.py --app <next> "…" --no-commit` on a scratch clone with
   a no-op migration writes the line, and without it does not (the issue's DoD check, T300-1 and T300-3).

The demo-guide structure does not apply: this is a runbook (the issue).

## 6. What an operator sees, and what it costs

- **A release engineer** running `prepare-release.py --app` sees one more line of output, `schema  : N at <sha>
  (application X), M at HEAD; …`, and, when the schema moved, one more bullet in the entry, under the reason. On a
  shallow clone the application release is refused with nothing edited and the message names `fetch-depth: 0`. A
  chart-only release behaves exactly as today. Cost: about a quarter of a second of `git show` (§3.3).
- **An operator planning an upgrade** reads, in each changelog entry between the running and the target version,
  whether its image migrates and from which schema to which; across an epic, the epic's GitHub release lists them.
  Before the upgrade, §0's three steps take a few minutes: three reads, and either one Job from the offsite CronJob
  or one download the size of the newest backup (14.2 MB on the lab).
- **An operator restoring** finds §4 starting with the order, the script as step 3, the manual paths as the
  fallback, and no instruction a GitOps controller would undo; §4c's expected output matches what `/api/version`
  prints.
- **Auditor and self tier:** nothing changes. No GUI, chart, RBAC, ServiceAccount or application change; no new
  image content.

## 7. Implementation blocks

Twenty-two blocks, in order. Blocks 16, 17 and 19 rewrite SPEC_E2's runbook text and apply once SPEC_E2's runbook
blocks are on the tree; the other nineteen apply to `eade4c2a` as well (Orchestrator's notes, 2). After `--apply`
nothing else is run by hand: no file mode, no version.

### Block 1 — local-development/prepare-release.py: the docstring says what the script derives: the schema line

WHAT IT DERIVES gains the line (§3.1).

<!-- block: local-development/prepare-release.py | edit -->

Old text:

```text
0.9.4. An explicit --chart wins. KIND (MAJOR, MINOR, PATCH) is the semver component that moved.
```

New text:

```text
0.9.4. An explicit --chart wins. KIND (MAJOR, MINOR, PATCH) is the semver component that moved.
An application release whose HEAD carries a higher `_MIGRATIONS` target than the commit that
released the current version gets the schema line under its reason in the changelog (SCHEMA_LINE,
#300): the first start on its image migrates the database one way.
```

### Block 2 — local-development/prepare-release.py: the docstring records the new refusals

WHAT IT REFUSES gains the shallow history (the issue's decision 2), an unreadable store and a schema that fell (§3.3).

<!-- block: local-development/prepare-release.py | edit -->

Old text:

```text
close), or with no letter or digit in it, or spanning any line boundary (\r and U+2028 included).
```

New text:

```text
close), or with no letter or digit in it, or spanning any line boundary (\r and U+2028 included).
An application release on a history too shallow to reach the commit that released the current
version, or whose store.py there or at HEAD cannot be read (checked before anything is edited):
without it the schema line cannot be decided. An application release whose HEAD carries a lower
highest `_MIGRATIONS` target than that commit (also before any edit): its image would refuse every
database that release migrated.
```

### Block 3 — local-development/prepare-release.py: the line's fixed words, one constant

The issue's wording, as one bullet line (§3.2).

<!-- block: local-development/prepare-release.py | edit -->

Old text:

```python
COMMENT_WIDTH = 100
```

New text:

```python
COMMENT_WIDTH = 100
# The changelog bullet an application release carries when its image migrates the database (#300). One
# line, so an epic's release note collects its children's with one grep (.claude/skills/epic/SKILL.md §6).
SCHEMA_LINE = ("- **Schema {then} → {now}.** The first start on this image migrates the database one way; "
               "the pre-upgrade copy (#301) and `restore-db.sh` (#302) are the way back.")
```

### Block 4 — local-development/prepare-release.py: the schema is read after the refusals and before the first edit

#298's helper, called for an application release only; what it cannot read, and a schema that fell, are refused (§3.1, §3.3).

<!-- block: local-development/prepare-release.py | edit -->

Old text:

```python
        raise ReleaseError(f"branch {branch} already exists; nothing was changed. Delete or rename it.")

```

New text:

```python
        raise ReleaseError(f"branch {branch} already exists; nothing was changed. Delete or rename it.")

    # ── The schema this release moves (#300) ──────────────────────────────────────────────────
    # Read before any edit, so a history that cannot answer refuses with nothing changed. A chart-only
    # release builds no image, so it migrates nothing and reads no history.
    schema_line = ""
    if args.app:
        try:
            released_at, then, now = schema_since_app_release(REPO)
        except (ReleaseError, SyntaxError, ValueError, AttributeError, IndexError) as err:
            # ReleaseError: a shallow history, a `git show` that fails, a non-integer target. The rest: a
            # store.py that does not parse, or a `_MIGRATIONS` entry that is not the literal tuple the helper
            # reads (an empty one included).
            raise ReleaseError(f"cannot tell whether application {app_new} migrates the database, so nothing "
                               f"was changed: {err}") from None
        if now < then:
            raise ReleaseError(f"_MIGRATIONS reaches {now} at HEAD but {then} at {released_at[:10]} (application "
                               f"{app_old}), so this image would refuse every database that release migrated; "
                               "nothing was changed")
        if now > then:
            schema_line = SCHEMA_LINE.format(then=then, now=now)
        print(f"schema  : {then} at {released_at[:10]} (application {app_old}), {now} at HEAD; "
              + ("the changelog entry says so" if schema_line else "no schema line"))

```

### Block 5 — local-development/prepare-release.py: the line goes under the reason, before the collected bullets

The reason stays first (§3.2).

<!-- block: local-development/prepare-release.py | edit -->

Old text:

```python
    bullet = f"- **{reason}.**\n"
    log = CHANGELOG.read_text()
    if re.search(r"^## Unreleased[ \t]*$", log, re.M):
        # The heading that has been collecting bullets since the last release becomes this one;
        # the reason goes first and the collected bullets follow it.
```

New text:

```python
    bullet = f"- **{reason}.**\n"
    if schema_line:
        bullet += f"\n{schema_line}\n"
    log = CHANGELOG.read_text()
    if re.search(r"^## Unreleased[ \t]*$", log, re.M):
        # The heading that has been collecting bullets since the last release becomes this one;
        # the reason goes first, the schema line under it, and the collected bullets follow.
```

### Block 6 — local-development/tests/test_prepare_release.py: the tests import the script

To read `SCHEMA_LINE` and `highest_migration` from the script itself.

<!-- block: local-development/tests/test_prepare_release.py | edit -->

Old text:

```python
import os
import pathlib
```

New text:

```python
import importlib.util
import os
import pathlib
```

### Block 7 — local-development/tests/test_prepare_release.py: the tests load the script as a module

As `tests/test_migration_needs_app_release.py` does.

<!-- block: local-development/tests/test_prepare_release.py | edit -->

Old text:

```python
REPO = pathlib.Path(__file__).resolve().parents[2]
```

New text:

```python
REPO = pathlib.Path(__file__).resolve().parents[2]

# The script's own constants and parser, so a test of the schema line reads the words the script writes.
_spec = importlib.util.spec_from_file_location("prepare_release", REPO / "local-development" / "prepare-release.py")
prep = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prep)
```

### Block 8 — local-development/tests/test_prepare_release.py: the sandbox carries the store

T300-5: the issue's decision 3.

<!-- block: local-development/tests/test_prepare_release.py | edit -->

Old text:

```python
    "local-development/prepare-release.py",
    "docs/CHANGELOG.md",
```

New text:

```python
    "local-development/prepare-release.py",
    # An application release reads the schema at HEAD and at the commit that released the current version
    # with `git show <rev>:local-development/gsd/store.py` (#300); without it every --app case fails.
    "local-development/gsd/store.py",
    "docs/CHANGELOG.md",
```

### Block 9 — local-development/tests/test_prepare_release.py: the schema line's tests

T300-1 to T300-4, T300-6 (with the unreadable store and the schema that fell) and T300-8 (§4).

<!-- block: local-development/tests/test_prepare_release.py | edit -->

Old text:

```python
    assert git(sandbox, "status", "--porcelain").strip() == "", "the spec edits must be in the release commit"

```

New text:

```python
    assert git(sandbox, "status", "--porcelain").strip() == "", "the spec edits must be in the release commit"


# ── The schema line (#300) ──────────────────────────────────────────────────────────────────────────

# The sentence the issue fixed, written here as text so a change to the script's constant fails a test.
SCHEMA_SENTENCE = ("The first start on this image migrates the database one way; the pre-upgrade copy (#301) and "
                   "`restore-db.sh` (#302) are the way back.")
STORE = "local-development/gsd/store.py"
MIGRATIONS_OPEN = "_MIGRATIONS: list[tuple[int, str, list[str]]] = ["


def _next_app_minor(sandbox: pathlib.Path) -> str:
    """The next application MINOR — the version an issue that adds a migration takes."""
    major, minor, _ = current(sandbox)["app"].split(".")
    return f"{major}.{int(minor) + 1}.0"


def add_migrations(sandbox: pathlib.Path, count: int) -> tuple[int, int]:
    """Commit `count` no-op migrations above the sandbox's highest, as an issue branch would before its release
    edits, and return the highest target before and after."""
    store = sandbox / STORE
    text = store.read_text()
    before = prep.highest_migration(text)
    entries = "".join(f'\n    ({before + n}, "a test-only migration", []),' for n in range(1, count + 1))
    assert text.count(MIGRATIONS_OPEN) == 1, "the store's _MIGRATIONS opening line moved; update MIGRATIONS_OPEN"
    store.write_text(text.replace(MIGRATIONS_OPEN, MIGRATIONS_OPEN + entries))
    git(sandbox, "commit", "-qam", f"{count} migration(s)")
    assert prep.highest_migration(store.read_text()) == before + count
    return before, before + count


def entry(sandbox: pathlib.Path, heading: str) -> list[str]:
    """The lines of one changelog entry, from below its heading to the next heading."""
    lines = (sandbox / "docs/CHANGELOG.md").read_text().splitlines()
    start = lines.index(heading)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("## ")), len(lines))
    return lines[start + 1:end]


@pytest.mark.parametrize("count", [1, 2])
def test_t300_1_2_a_release_after_a_migration_carries_the_schema_line_under_its_reason(
        sandbox: pathlib.Path, count: int) -> None:
    """T300-1 and T300-2: the numbers are the release's and HEAD's highest targets, a jump of two included, and
    the line sits directly under the reason, before the bullets Unreleased collected. The changelog is seeded:
    the repository's own has no `## Unreleased` heading on a release PR's head (the release consumed it), and
    the collected bullets must be known to be asserted."""
    log = sandbox / "docs/CHANGELOG.md"
    log.write_text("# Changelog\n\nIntro.\n\n## Unreleased\n\n- **Something merged earlier.**\n\n"
                   "## Application 0.1.0 — chart 0.1.0 — 2026-01-01\n\n- old\n")
    git(sandbox, "commit", "-qam", "seed an Unreleased section")
    then, now = add_migrations(sandbox, count)
    target = _next_app_minor(sandbox)
    done = run(sandbox, "--app", target, "The migration's release", "--no-commit")
    assert done.returncode == 0, done.stdout + done.stderr
    lines = entry(sandbox, f"## Application {target} — chart {current(sandbox)['chart']} — {DATE}")
    assert lines == ["", "- **The migration's release.**", "", f"- **Schema {then} → {now}.** {SCHEMA_SENTENCE}",
                     "", "- **Something merged earlier.**", ""], "reason, the line, then the collected bullets"
    assert f"schema  : {then} at " in done.stdout and f"{now} at HEAD; the changelog entry says so" in done.stdout


def test_t300_1_the_line_is_written_without_an_unreleased_heading_too(sandbox: pathlib.Path) -> None:
    """The other branch of the changelog edit: no Unreleased heading, so the entry goes above the first release."""
    log = sandbox / "docs/CHANGELOG.md"
    log.write_text("# Changelog\n\nIntro.\n\n## Application 0.1.0 — chart 0.1.0 — 2026-01-01\n\n- old\n")
    git(sandbox, "commit", "-qam", "a changelog with no Unreleased heading")
    then, now = add_migrations(sandbox, 1)
    target = _next_app_minor(sandbox)
    done = run(sandbox, "--app", target, "Released", "--no-commit")
    assert done.returncode == 0, done.stdout + done.stderr
    assert entry(sandbox, f"## Application {target} — chart {current(sandbox)['chart']} — {DATE}") == [
        "", "- **Released.**", "", f"- **Schema {then} → {now}.** {SCHEMA_SENTENCE}", ""]


def test_t300_3_no_line_when_the_schema_did_not_move(sandbox: pathlib.Path) -> None:
    target = _next_app_minor(sandbox)
    done = run(sandbox, "--app", target, "No migration here", "--no-commit")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "; no schema line" in done.stdout
    lines = entry(sandbox, f"## Application {target} — chart {current(sandbox)['chart']} — {DATE}")
    assert lines[1] == "- **No migration here.**"
    assert not [line for line in lines if line.startswith("- **Schema ")]


def test_t300_4_no_line_on_a_chart_only_release(sandbox: pathlib.Path) -> None:
    """A chart-only release builds no image (docs/RELEASING.md, the chart-only flow), so it migrates nothing."""
    add_migrations(sandbox, 1)
    target = _next_chart_patch(sandbox)
    done = run(sandbox, "--chart", target, "A template change", "--no-commit")
    assert done.returncode == 0, done.stdout + done.stderr
    assert "schema  :" not in done.stdout
    lines = entry(sandbox, f"## Chart {target} — application {current(sandbox)['app']} — {DATE}")
    assert not [line for line in lines if line.startswith("- **Schema ")]


def _shallow_clone(sandbox: pathlib.Path, tmp_path_factory) -> pathlib.Path:
    """A depth-1 clone of the sandbox. git marks it shallow (it does even for a single commit), so the walk to the
    release commit ends at a boundary that is not where the version began."""
    clone = tmp_path_factory.mktemp("shallow") / "repo"
    git(sandbox, "clone", "-q", "--depth", "1", f"file://{sandbox}", str(clone))
    assert git(clone, "rev-parse", "--is-shallow-repository").strip() == "true"
    return clone


def test_t300_6_a_shallow_history_is_refused_before_anything_is_edited(sandbox: pathlib.Path,
                                                                        tmp_path_factory) -> None:
    """Decision 2 of the issue: a release that cannot read the schema at the last release is refused, not cut
    blind, and the refusal comes before the first edit."""
    clone = _shallow_clone(sandbox, tmp_path_factory)
    before = current(clone)
    done = run(clone, "--app", _next_app_minor(clone), "Blind", "--no-commit")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "so nothing was changed" in done.stderr and "fetch-depth: 0" in done.stderr
    assert "Traceback" not in done.stderr
    assert current(clone) == before
    assert git(clone, "status", "--porcelain").strip() == ""


@pytest.mark.parametrize("broken", ["\n    *EXTRA,", "\n    (),"], ids=["starred", "empty-tuple"])
def test_t300_6_an_unreadable_migrations_list_is_refused_before_anything_is_edited(sandbox: pathlib.Path,
                                                                                     broken: str) -> None:
    """A store.py the helper cannot read (an entry that is not a literal tuple, and an empty tuple whose first
    element the helper indexes) is a refusal with the script's message, not a traceback, and nothing is edited."""
    store = sandbox / STORE
    store.write_text(store.read_text().replace(MIGRATIONS_OPEN, MIGRATIONS_OPEN + broken))
    git(sandbox, "commit", "-qam", "a _MIGRATIONS entry the parser cannot read")
    before = current(sandbox)
    done = run(sandbox, "--app", _next_app_minor(sandbox), "Unreadable", "--no-commit")
    assert done.returncode == 1, done.stdout + done.stderr
    assert "so nothing was changed" in done.stderr and "Traceback" not in done.stderr
    assert current(sandbox) == before and git(sandbox, "status", "--porcelain").strip() == ""


def test_t300_6_a_schema_that_fell_is_refused_before_anything_is_edited(sandbox: pathlib.Path) -> None:
    """HEAD's highest target below the released one: that image would refuse (StoreSchemaTooNew) every database
    the released image migrated, so the release is refused before any edit, not cut with no line."""
    then, now = add_migrations(sandbox, 1)
    released = _next_app_minor(sandbox)
    done = run(sandbox, "--app", released, "Released with the migration")
    assert done.returncode == 0, done.stdout + done.stderr
    (sandbox / STORE).write_text((REPO / STORE).read_text())
    git(sandbox, "commit", "-qam", "the migration reverted, the version kept")
    before = current(sandbox)
    done = run(sandbox, "--app", _next_app_minor(sandbox), "Fell", "--no-commit")
    assert done.returncode == 1, done.stdout + done.stderr
    assert f"reaches {then} at HEAD but {now} at" in done.stderr and "nothing was changed" in done.stderr
    assert "Traceback" not in done.stderr
    assert current(sandbox) == before and git(sandbox, "status", "--porcelain").strip() == ""


def test_t300_6_a_chart_only_release_reads_no_history(sandbox: pathlib.Path, tmp_path_factory) -> None:
    """The new refusal is the application release's alone: a chart-only release on the same clone is cut."""
    clone = _shallow_clone(sandbox, tmp_path_factory)
    done = run(clone, "--chart", _next_chart_patch(clone), "A template change", "--no-commit")
    assert done.returncode == 0, done.stdout + done.stderr


def test_t300_8_releasing_md_states_the_line_and_when_it_appears() -> None:
    text = (REPO / "docs" / "RELEASING.md").read_text()
    section = text.split("### An application release", 1)[1].split("### A chart-only release", 1)[0]
    assert prep.SCHEMA_LINE.format(then="N", now="M") in section, "the exact line, as the script writes it"
    assert f"- **Schema N → M.** {SCHEMA_SENTENCE}" in section
    for words in ("`_MIGRATIONS`", "schema_since_app_release", "chart-only", "fetch-depth: 0", "MINOR"):
        assert words in section, words
```

### Block 10 — docs/RELEASING.md: step 6 names the line

T300-8.

<!-- block: docs/RELEASING.md | edit -->

Old text:

```text
6. Turn `## Unreleased` in `docs/CHANGELOG.md` into `## Application X — chart Y — date`, with the
   reason as its first bullet and everything merged since the last release beneath it.
```

New text:

```text
6. Turn `## Unreleased` in `docs/CHANGELOG.md` into `## Application X — chart Y — date`, with the
   reason as its first bullet, the schema line under it when the release moves the schema (below), and
   everything merged since the last release beneath it.
```

### Block 11 — docs/RELEASING.md: what the line means and when it appears

T300-8.

<!-- block: docs/RELEASING.md | edit -->

Old text:

```text
All the edits land in one PR, or CI is red. That is the coupling working, not friction.
```

New text:

```text
All the edits land in one PR, or CI is red. That is the coupling working, not friction.

**The schema line (#300).** An application release whose image migrates the database says so, directly under
the reason:

> - **Schema N → M.** The first start on this image migrates the database one way; the pre-upgrade copy (#301) and `restore-db.sh` (#302) are the way back.

`N` is the highest `_MIGRATIONS` target at the commit that released the current application version, and `M`
the highest at HEAD, both read with `git show` before anything is edited
(`local-development/prepare-release.py#schema_since_app_release`, the helper #298's CI guard uses). The line
appears only when `M` is above `N`, and a jump of more than one says so (`Schema 20 → 22`). A chart-only release
builds no image and gets no line. A migration ships with the next MINOR in its own PR (below), so the line lands
under that issue's `## Application X.Y.0` heading, the version whose image first migrates; an epic's MAJOR then
carries none of its own, and the epic's GitHub release note lists its children's lines
(`.claude/skills/epic/SKILL.md`, section 6). Finding that commit needs the full history: on a shallow clone an
application release is refused before any edit, and the message names `actions/checkout`'s `fetch-depth: 0`
(`git fetch --unshallow` on a laptop). A version bumped by hand, without the script, gets no line: nothing else
writes it.
```

### Block 12 — .claude/skills/epic/SKILL.md: §6 step 2: the epic's release note lists its children's schema lines

The issue's decision 1 (§3.4).

<!-- block: .claude/skills/epic/SKILL.md | edit -->

Old text:

```text
2. **Release note.** Once `helm.yaml` has created the GitHub release, write the epic's summary (the children, their
   merge shas, the lab evidence) into that release's body. The tag is the **chart** version just cut, not the
```

New text:

```text
2. **Release note.** Once `helm.yaml` has created the GitHub release, write the epic's summary (the children, their
   merge shas, the lab evidence) into that release's body. List in it every schema line the epic's children released
   (#300): a child that added a migration carries `**Schema N → M.**` under its own MINOR heading in
   `docs/CHANGELOG.md`, and the epic's MAJOR carries none, so an operator upgrading across the epic learns of each
   move only here. On `main` after the release merged,
   `awk '/^## Application [0-9]+\.0\.0 / && ++n == 2 {exit} /^## / {h = $0} /^- \*\*Schema / {print h; print $0}' docs/CHANGELOG.md`
   prints each such heading and its line, up to the previous epic's MAJOR; when it prints nothing, write "No schema
   change". The tag is the **chart** version just cut, not the
```

### Block 13 — docs/CHANGELOG.md: the entry

First under `## Unreleased`.

<!-- block: docs/CHANGELOG.md | edit -->

Old text:

```text
## Unreleased

```

New text:

```text
## Unreleased

- **The release note says when the schema moves, and the runbook says what to do before every upgrade (#300, Epic E
  #385, `docs/specs/SPEC_E7_schema_line_and_runbook.md`).** `prepare-release.py --app` compares the highest
  `_MIGRATIONS` target at the commit that released the current application version with HEAD's, before it edits
  anything, and when HEAD's is higher writes a bullet under the release's reason: `Schema N → M.`, the first start
  on the image migrates the database one way, and the pre-upgrade copy (#301) and `restore-db.sh` (#302) are the way
  back. A chart-only release reads nothing and gets no line; an application release on a shallow clone is refused
  with nothing edited. `docs/RELEASING.md` says what the line means and when it appears, and the epic skill's
  release note lists the children's lines. `docs/RUNBOOK_backup_restore.md` gains §0, "Before every upgrade": read
  the schema lines and the schema you leave (the running image's `KNOWN_SCHEMA_VERSION`, no live file opened), take
  an off-volume copy and confirm it (§2 with the offsite CronJob, §3 without), and check the free space the
  pre-upgrade copy needs. §4 opens with the order (recovery mode, `restore-db.sh`, recovery mode off), points its
  steps at the script, stops the writer of the manual fallback with `replicaCount: 0` in the values file instead of
  `oc scale`, and drops two stale lines: the `0.15.0` image pinned in §4b's helper pod and the `0.15.0` expected from
  `/api/version` in §4c. No application or chart change.

```

### Block 14 — docs/RUNBOOK_backup_restore.md: §0, before every upgrade

T300-9 (§3.5): a new section after the opening, before the pictures.

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
## What a successful backup looks like
```

New text:

```text
## 0. Before every upgrade

The first start of an image that moves the schema upgrades the database one way (§6), and the copy it takes first
stays on the volume it protects. Before you change the image a release runs (a new chart version, or `image.tag` in
its values file), do these three things. None of them stops the dashboard.

1. **Read whether the upgrade migrates the database, and note the schema you leave.** In `docs/CHANGELOG.md`,
   every entry after the version you run (`gsd_build_info`'s `version` label on `/metrics`), up to and including
   the one you deploy, that carries a `**Schema N → M.**` line migrates the database on its first start
   (`local-development/prepare-release.py#SCHEMA_LINE`); an epic's GitHub release lists its children's lines. The
   schema you leave is the one the running image understands, read without opening the live file:

   ````sh
   oc exec -n $NS deploy/$REL -c dashboard -- python3.14 -c 'from gsd.store import KNOWN_SCHEMA_VERSION; print(KNOWN_SCHEMA_VERSION)'
   ````

   While the dashboard runs, its database is at exactly this number: a newer one is refused at startup
   (`gsd/store.py#StoreSchemaTooNew`) and an older one is migrated up to it (`gsd/store.py#_migrate`). Note it: it is
   the `<from>` in the pre-upgrade copy's name (§6), and a copy at this schema restores under the image you run now
   (§4).
2. **Take a copy off the volume, and confirm it landed.** Whether the release has the offsite CronJob decides how:

   ````sh
   oc get cronjob -n $NS $REL-backup-offsite
   ````

   * **It exists** (`backup.offsite` on): run it now (§2). The copy landed when the Job is `Complete` and its log
     says `copied … -> …` followed by `integrity_check ok; user_version` with step 1's number, or `already shipped:
     … matches its sidecar` (a scheduled run shipped the same backup and verified it then):

     ````sh
     J=manual-$(date +%s)
     oc create job -n $NS --from=cronjob/$REL-backup-offsite $J
     oc wait -n $NS --for=condition=complete job/$J --timeout=1800s
     oc logs -n $NS job/$J --all-containers | grep -E '^(copied|already shipped|integrity_check)'
     ````

     Without `oc`, where Prometheus reads kube-state-metrics, §2's query gives the last scheduled success, and
     `GroupSyncDashboardOffsiteBackupStale` not firing says it is recent: that copy is at most one
     `backup.offsite.schedule` old.
   * **It does not** (`NotFound`): copy the newest on-volume backup to your workstation (§3), and check it there
     with §1's snippet run with `python3`: `integrity_check: ok`, and a `user_version` equal to step 1's number.

     ````sh
     B=$(oc exec -n $NS deploy/$REL -c dashboard -- python3.14 -c 'import glob; print(sorted(glob.glob("/data/backup/gsd-*.db"))[-1])')
     oc exec -n $NS deploy/$REL -c dashboard -- cat "$B" > "$(basename "$B")"
     sha256sum "$(basename "$B")"
     ````

   Either way the copy is the newest six-hourly backup (`config.backup.intervalHours`); what changed after it is in
   the live database and, when the schema moves, in the pre-upgrade copy the new image takes on the volume.
3. **Know where the pre-upgrade copy goes, and that it fits.** When step 1 found a schema line, the new image's
   first start writes the database as it is to `/data/pre-upgrade/` (`/data/<pod-name>/pre-upgrade/` above one
   replica) before it migrates, and refuses to start, changing nothing, while the free space there is below the
   database's size (§6). Compare the two:

   ````sh
   oc exec -n $NS deploy/$REL -c dashboard -- python3.14 -c 'import glob, os, shutil; print("free", shutil.disk_usage("/data").free); print("databases", sum(os.stat(p).st_size for p in glob.glob("/data/gsd.db") + glob.glob("/data/gsd.db-wal") + glob.glob("/data/*/gsd.db") + glob.glob("/data/*/gsd.db-wal")))'
   ````

   `free` must be above `databases`. A copy needs at most its database's file and `-wal` together, and above one
   replica every pod copies its own at the same start, so the sum counts them all; `os.stat` opens no database.
   Without `oc`, `/metrics` carries the volume's numbers: `gsd_volume_disk_total_bytes{component="dashboard"}` minus
   `gsd_volume_disk_used_bytes{component="dashboard"}` is the free space, or more than the copy may use where the
   filesystem keeps blocks for root (`mke2fs` reserves 5% by default).

## What a successful backup looks like
```

### Block 15 — docs/RUNBOOK_backup_restore.md: §4 opens with the order and the rule

T300-10 (§3.6).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
## 4. Restore
```

New text:

```text
## 4. Restore

**In order.** Turn recovery mode on through the release's values file, with the image you will restore under (steps
1 and 2 below); list the copies and restore one with `restore-db.sh` (**The script, in recovery mode**, next); turn
recovery mode off and verify (step 5 and §4c). §4a and §4b are the same restore by hand, the fallback when the script
cannot be used, and **Without recovery mode** below is the fallback for a chart that has none. Every change to the
release goes through its values file and its deployment pipeline, never `oc scale` or `oc set env`: a GitOps
controller that self-heals, Argo CD's for one, reverts a hand edit to an object it renders.
```

### Block 16 — docs/RUNBOOK_backup_restore.md: §4, step 3 restores with the script, the manual paths as its fallback

T300-10 (§3.6); SPEC_E2's text. Applies after SPEC_E2's runbook blocks (its text).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
3. **Restore** with §4a or §4b, running their commands with `oc exec -n $NS deploy/$REL -c dashboard -- sh -c '…'`
   instead of `oc debug` or a helper pod. **Check the time left first** (the last `left` line of `oc logs`):
```

New text:

```text
3. **Restore** with `local-development/restore-db.sh --list`, then `--from-version <ID>` (**The script, in recovery
   mode**, above), each with `--namespace $NS --release $REL` unless both are the script's defaults
   (`group-sync-dashboard`); it refuses with less than ten minutes of `recovery.ttl` left. By hand, the fallback, use
   §4a or §4b, running their commands with `oc exec -n $NS deploy/$REL -c dashboard -- sh -c '…'` instead of `oc debug`
   or a helper pod. **Check the time left first** (the last `left` line of `oc logs`):
```

### Block 17 — docs/RUNBOOK_backup_restore.md: §4, without recovery mode: the writer stops through the values file, not `oc scale`

T300-10 (§3.7); SPEC_E2's text. Applies after SPEC_E2's runbook blocks (its text).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
**Without recovery mode** (the fallback, and any chart before 0.60.0), scale the writer to zero and use the
`oc debug` pod of §4a or the helper pod of §4b:

```sh
oc scale -n $NS deploy/$REL --replicas=0
```

New text:

```text
**Without recovery mode** (the fallback, and any chart before 0.60.0), stop the writer the same way: set
`replicaCount: 0` in this release's values file and roll it out through its deployment pipeline (it changes the
Deployment's `replicas` and the configuration's copy of the number, not the claim or its access mode), then use the
`oc debug` pod of §4a or the helper pod of §4b. Wait until the pod is gone:

```sh
```

### Block 18 — docs/RUNBOOK_backup_restore.md: §4b's helper pod runs the Deployment's image, not 0.15.0

T300-11.

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
      image: quay.io/ephico2real/group-sync-dashboard:0.15.0   # the running tag
```

New text:

```text
      image: <the Deployment's image>   # oc get deploy -n $NS $REL -o jsonpath='{.spec.template.spec.containers[0].image}'
```

### Block 19 — docs/RUNBOOK_backup_restore.md: §4c brings the app back through the values file

T300-10 (§3.7); SPEC_E2's text. Applies after SPEC_E2's runbook blocks (its text).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
In recovery mode, turn it off (§4, step 5) instead of the `oc scale` below: the app starts on the restored
file. The rest of this section is the same.

```sh
oc scale -n $NS deploy/$REL --replicas=1
```

New text:

```text
Turn recovery mode off (§4, step 5); on the fallback, set `replicaCount` back to its value (1) in the values file
and roll it out. The app starts on the restored file:

```sh
```

### Block 20 — docs/RUNBOOK_backup_restore.md: §4c expects the version the release runs, in the shape `/api/version` prints

T300-11 (§2.9).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
Expected: `{"leader": true, "version": "0.15.0", …}` (with `oauthProxy.enabled` the app binds
loopback; `curl` from inside the pod is the honest check).
```

New text:

```text
Expected: `{"leader":true,"version":"<the application version the release now runs>",…}`, the older one after a
rollback, as `gsd_build_info` on `/metrics` says too (with `oauthProxy.enabled` the app binds loopback; `curl` from
inside the pod is the honest check).
```

### Block 21 — docs/RUNBOOK_backup_restore.md: §4c, after a refusal: recovery mode, not a scale to 0

T300-10 (§3.7).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
changes the file's bytes, not its contents. Scale to 0
(§4) and either restore a copy whose `user_version` is at or below the second number, or deploy the
image that understands the first. A rollback to an older image without restoring the database first
stops the same way.
```

New text:

```text
changes the file's bytes, not its contents. Turn recovery mode on
(§4) and either restore a copy whose `user_version` is at or below the second number, or deploy the
image that understands the first, by its `image.tag` in the values file. A rollback to an older image without
restoring the database first stops the same way.
```

### Block 22 — local-development/tests/test_runbook_backup_restore.py: the runbook's tests

T300-9 to T300-12 (§4).

<!-- block: local-development/tests/test_runbook_backup_restore.py | create -->

```python
"""docs/RUNBOOK_backup_restore.md, as #300 left it: §0 before every upgrade, §4 around recovery mode (#303) and
restore-db.sh (#302) with the manual paths as the fallback, and the section numbers the code cites.

The runbook is the procedure an operator follows at 03:00, so these read it as text: a heading renumbered or a
stale command left in place is a wrong instruction no other test sees. The store's refusals cite "§4" and "§6"
(gsd/store.py), a chart refusal cites "§5", and the chart README links "#6-pre-upgrade-copies".
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
RUNBOOK = REPO / "docs" / "RUNBOOK_backup_restore.md"
TEXT = RUNBOOK.read_text()
HEADINGS = re.findall(r"^## (\d+)\. (.+)$", TEXT, re.M)


def section(number: str) -> str:
    """The body of `## <number>. …`, up to the next level-2 heading."""
    start = re.search(rf"^## {number}\. .+$", TEXT, re.M)
    assert start, f"no section {number}"
    end = re.search(r"^## ", TEXT[start.end():], re.M)
    return TEXT[start.end():start.end() + end.start()] if end else TEXT[start.end():]


def code_lines(text: str) -> list[str]:
    """Every line inside a fenced block, three backticks or four, stripped of its indentation."""
    lines, fence = [], None
    for line in text.splitlines():
        stripped = line.strip()
        marker = re.match(r"^(`{3,})", stripped)
        if fence is None and marker:
            fence = marker.group(1)
        elif fence is not None and stripped == fence:
            fence = None
        elif fence is not None:
            lines.append(stripped)
    return lines


def slug(title: str) -> str:
    """GitHub's heading anchor: lower case, punctuation other than '-' dropped, spaces to '-'."""
    return re.sub(r"[^\w\- ]", "", title.lower()).replace(" ", "-")


def test_t300_9_section_0_comes_first_and_covers_the_three_steps() -> None:
    assert [number for number, _ in HEADINGS] == ["0", "1", "2", "3", "4", "5", "6"], HEADINGS
    assert HEADINGS[0] == ("0", "Before every upgrade")
    body = section("0")
    code = code_lines(body)
    # the schema lines tell whether the upgrade migrates; the running image's number is the one you leave
    assert "**Schema N → M.**" in body and "prepare-release.py#SCHEMA_LINE" in body
    assert any("from gsd.store import KNOWN_SCHEMA_VERSION" in line for line in code)
    assert not [line for line in code if "sqlite3" in line or "gsd.db?" in line], "§0 opens no database"
    # the off-volume copy: §2 when the offsite CronJob exists, §3 when it does not, and how to see it landed
    assert "§2" in body and "§3" in body
    assert any(line.startswith("oc get cronjob -n $NS $REL-backup-offsite") for line in code)
    assert any("--from=cronjob/$REL-backup-offsite" in line for line in code)
    assert any("oc wait" in line and "condition=complete" in line for line in code)
    assert "integrity_check" in body and "already shipped" in body
    assert any('cat "$B" > "$(basename "$B")"' in line for line in code)
    # where the pre-upgrade copy goes, and the free space it needs, with and without oc
    assert "/data/pre-upgrade/" in body and "/data/<pod-name>/pre-upgrade/" in body
    assert any("shutil.disk_usage" in line and "os.stat" in line for line in code)
    assert "gsd_volume_disk_total_bytes" in body and "gsd_volume_disk_used_bytes" in body


def test_t300_10_section_4_is_recovery_mode_and_the_script_with_oc_debug_as_the_fallback() -> None:
    body = section("4")
    order = body.split("\n\n", 2)[1]
    assert order.startswith("**In order.**"), "§4 opens with the order"
    for words in ("recovery mode", "values file", "deployment pipeline", "restore-db.sh", "never `oc scale`"):
        assert words in order, words
    assert "recovery.enabled: true" in body and "local-development/restore-db.sh --list" in body
    assert "--from-version <ID>" in body
    assert "--namespace $NS --release $REL" in body, "the script defaults to group-sync-dashboard for both; the runbook's NS is not it"
    code = code_lines(body)
    assert any(line.startswith("oc debug -n $NS deploy/$REL") for line in code), "the fallback keeps oc debug"
    assert not [line for line in code if line.startswith("oc scale")], "no oc scale in §4's commands"
    assert "`replicaCount: 0` in this release's values file" in body
    # the only Helm command line is the one labelled for development and troubleshooting
    operator = re.sub(r"\*\*Development and troubleshooting only:\*\*.*?\n\n", "", body, flags=re.S)
    for word in ("helm upgrade", "--set", "argocd", "applications.argoproj.io", "oc patch", "oc set env deploy"):
        assert word not in operator.lower(), word
    for sentence in re.split(r"(?<=[.;:])\s+", operator):
        assert "Argo CD" not in sentence or "revert" in sentence, sentence


def test_t300_11_no_stale_version_and_the_fallback_keeps_the_wal() -> None:
    body = section("4")
    assert "group-sync-dashboard:0.15.0" not in TEXT
    assert '"version": "0.15.0"' not in TEXT and '"version":"0.15.0"' not in TEXT
    assert '"version":"<the application version the release now runs>"' in body, "the shape /api/version prints"
    keep = body.split("### 4a.", 1)[1].split("### 4b.", 1)[0]
    assert re.search(r'for name in \(\\"gsd\.db\\", \\"gsd\.db-wal\\"', keep), "§4a keeps gsd.db with its -wal"
    assert "Scale to 0" not in body


def test_t300_12_the_sections_the_code_cites_keep_their_numbers() -> None:
    titles = dict(HEADINGS)
    assert titles["4"] == "Restore"
    assert titles["5"] == "Moving the data to a new claim (access mode change)"
    assert titles["6"] == "Pre-upgrade copies"
    cited = set()
    for path in [*(REPO / "local-development" / "gsd").rglob("*.py"), *(REPO / "charts").rglob("*.*")]:
        if path.is_file() and path.suffix in (".py", ".tpl", ".yaml", ".md"):
            cited.update(re.findall(r"RUNBOOK_backup_restore\.md §(\d)", path.read_text(errors="replace")))
    assert {"4", "5", "6"} <= cited, cited
    assert cited <= set(titles), f"the code cites a section the runbook does not have: {cited - set(titles)}"
    # the links other documents make into the runbook, as GitHub resolves them: a heading's anchor
    anchors = {slug(title) for title in re.findall(r"^#{2,3} (.+)$", TEXT, re.M)}
    linked = set()
    for path in REPO.rglob("*.md"):
        if not {".git", ".venv", "node_modules"} & set(path.parts):
            linked.update(re.findall(r"\]\([^)\s]*RUNBOOK_backup_restore\.md#([\w-]+)\)", path.read_text(errors="replace")))
    assert "6-pre-upgrade-copies" in linked
    assert linked <= anchors, f"links to anchors the runbook does not have: {linked - anchors}"
```
