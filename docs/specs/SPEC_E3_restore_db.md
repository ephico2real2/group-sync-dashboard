# SPEC E3 — `restore-db.sh`: list the database copies the recovery pod can restore, and restore one (#302)

| | |
|---|---|
| Programme | Epic E (#385), restore tools and release safety; build-order step 2 of 9. It runs inside #303's recovery pod (SPEC_E2), which merges first |
| Batch | E — restore tools and release safety |
| Release | — (post-programme; Epic E's release, milestone 3.0.0) |
| Version on release | app 2.1.0, chart 0.60.1 |
| Version note | The helper and the wrapper live outside the image (`local-development/restore-db.py`, `local-development/restore-db.sh`), but two of the blocks touch image content: the `_MIGRATIONS` comment (T302-21) in `local-development/gsd/store.py` and one row of `local-development/README.md`, both under `publish.yml`'s paths, so `local-development/check-app-version-bump.py` requires the next application MINOR. The implementing pull request runs `local-development/prepare-release.py --app <the next free MINOR> --no-commit "…"`, which also moves `appVersion` and therefore the chart PATCH. Against `21132a25` that is app 2.1.0 and chart 0.59.26; if SPEC_E2 (chart 0.60.0) lands first, the chart becomes 0.60.1. No block carries a version field: the script writes them (Orchestrator's notes, 10) |
| Issue | [#302](https://github.com/ephico2real2/group-sync-dashboard/issues/302) |
| Status | merged |
| Source | OB1-lite's research and specification of 2026-10-01, written before any code from the issue (its "Decisions and corrections (2026-10-01)"), the epic's "Decisions settled (2026-10-01)", the operator's rules of 2026-10-01 on values files and Argo CD, and SPEC_E2 as it stands at `465411cd` (in review); revised the same day on the reviews of `167ecb9b` by OB3 (in Grok's seat) and Codex (Orchestrator's notes, 17). Measured on main `afa01bb8` (application 2.0.0, chart 0.59.25) with Python 3.14.7 and SQLite 3.53.4 on this machine, and read-only on the CRC lab (OpenShift 4.22.7, image 2.0.0). §7's blocks were cut from a copy of `21132a25` with the design implemented, and proved against a clean tree of it (§4.3) |

## How to read this spec

**The point in one sentence: `restore-db.sh` runs on your laptop, checks from the pod spec that the release's one
pod is in recovery mode with time left, and streams a small Python helper into that pod, which lists every copy of
the database by an ID and, for the ID you pick, checks it, shows what you lose, asks, keeps what is there now, and
swaps the copy in so that a failure at any moment leaves either the old database or the new one, and restores
only the copy and the live set the question was about.**

§1 is the mandate. §2 is the research: each finding names its source, the sentence relied on, and what it settles;
lab reads carry the command and its output. §2a lists the alternatives the research turned up and maps each external
claim to the line of this repository that behaves accordingly. §3 is the design, one decision per subsection, with
the safety budgets. §4 maps every test case of the issue (T302-1 to T302-21) to a test and shows each failing on a
tree without the change. §5 is the walk the implementing pull request runs on the lab. §6 is what an operator sees
and what it costs. §7 is the whole change as implementation blocks (`docs/specs/README.md`, "Implementation
blocks"), applied to a clean tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E3_restore_db.md . --apply
    chmod +x local-development/restore-db.sh

Citations into the code use `path#anchor`; upstream sources are named with their URL and the date they were read,
and the sentence relied on is quoted. This spec's own row in the index moves through the lifecycle by the
orchestrator's hand; no block touches it. A block found wrong during implementation is corrected here, with the
reason under the orchestrator's notes, before it is applied again.

**Words used below.** The *live set* is `/data/gsd.db` with whichever of `gsd.db-wal`, `gsd.db-shm` and
`gsd.db-journal` exist beside it. A *copy* is a file the script can restore: a scheduled backup
(`/data/backup/gsd-<stamp>.db`), a pre-upgrade copy (`/data/pre-upgrade/pre-upgrade-<stamp>-schema-<from>-to-<to>-<pod>.db`)
or a copy on the offsite claim (`/offsite/…`). The *ID* of a copy is `<user_version>-<the stamp in its name>`,
for example `20-20261001T051103.798578Z`.

## Orchestrator's notes

Decisions taken while specifying, on "easy to manage, best practice", the corrections the research made to the
issue, what this spec takes from SPEC_E2, and the decisions on the reviews of 2026-10-01 (note 17). Each is applied in
§3 and §7 and held by a test in §4.

1. **What this spec takes from SPEC_E2 (`465411cd`; merged as a spec on main at `1e4558ad`, same interface), every name, so a review change to E2 can be carried
   here mechanically.** Merge order: E2 before E3. E3's blocks apply to `b5463d45` without E2's blocks and on top of
   them, and E2's on top of E3's, giving the same tree (measured, §4.3); E3 adds no chart change.

   | from E2 | where E3 uses it |
   |---|---|
   | `GSD_RECOVERY_MODE` = `"true"` in the dashboard container's `env` (E2 §3.3, block 5) | `preflight` reads it from the pod spec; `in_recovery` reads it from the process environment in the pod |
   | `GSD_RECOVERY_MODE_TTL`, a Go duration in the grammar of `gsd.durationSeconds` (E2 §3.5) | `preflight` parses it with the same regular expressions (`ttl_seconds`); a test compares the two parsers once E2's script is on the branch |
   | the TTL is per pod, counted from its first container start and kept across container restarts (E2 §3.6) | `preflight` bounds it with the pod's `status.startTime` (note 2) |
   | `$TMPDIR/gsd-recovery.json` (`/tmp/gsd-recovery.json`) and its fields `ttl`, `deadline_monotonic` and `boot_id`; the time left is `deadline_monotonic - time.monotonic()` while `boot_id` matches the node's (`/proc/sys/kernel/random/boot_id`, empty off Linux), 0 when it does not, never more than the TTL (E2 §3.5, note 15) | `recovery_left` computes exactly that in the pod when a restore starts (note 2); `started`, `started_epoch`, `deadline` and `deadline_epoch` (display only) are not read |
   | the container name `dashboard` and the interpreter `python3.14` (E2 §3.2) | `oc exec … -c dashboard -- python3.14 /dev/stdin` |
   | PID 1 is `python3.14 /scripts/recovery_mode.py --release …`, no uvicorn (E2 §3.2) | `in_recovery` refuses when any process's argv names uvicorn; E2's removal of `--namespace` touches nothing here |
   | the offsite claim mounted read-only at `/offsite` when `backup.offsite.enabled` and `destination.type: pvc` (E2 §3.8) | `--offsite /offsite`, scanned only when it is a directory; otherwise `--list` says it is not mounted |
   | the pod's `/tmp` is the chart's `tmp` emptyDir (E2 §2.3) | the operation lock `/tmp/gsd-restore.lock` |
   | `replicaCount` 1 is required in recovery mode, strategy Recreate (E2 §3.7) | `preflight` also requires exactly one pod matching `app=<release>` |
   | the values `recovery.enabled` and `recovery.ttl` (E2 §3.1) | named in every refusal: "set … in this release's values file and roll it out" |

   E3 takes no printed command from E2: every message here names the values file and the release's pipeline (note 11).
2. **The TTL is checked twice: from the pod spec before each session, and as SPEC_E2 counts it when a restore
   starts.** The issue's correction 3 reads "the container's `startedAt` and `GSD_RECOVERY_MODE_TTL` with `oc get pod
   -o jsonpath`, no exec". SPEC_E2 keeps the TTL from the pod's first container start across restarts, so after a
   restart `startedAt` is later than that start and the time left it gives is too long. `preflight` uses the pod's
   `status.startTime` instead, "before the Kubelet pulled the container image(s)" (§2.9): `startTime + TTL` is never
   after E2's deadline, so it is a lower bound read with no exec, within the skew between the laptop's clock and the
   node's. E2's revision (`465411cd`) counts its deadline on the node's monotonic clock and ends the TTL at once when
   the node's boot ID changes; neither is visible in the pod spec. So `restore`, under its lock and before anything
   is written, also reads `/tmp/gsd-recovery.json` and computes E2's own answer (`recovery_left`, measured equal to
   E2's `remaining` on the same record, §2.13); less than the margin, or a record it cannot read (not JSON, a field
   missing or of the wrong type, or a deadline that is not a finite number, which E2's own read refuses too),
   refuses with exit 2. The TTL's end kills the container's processes, a restore among them (E2 §2.4), so the in-pod count is the one
   that decides; the laptop's is the early, cheap refusal T302-17 asks for.
3. **Correction: the confirmation is asked on the laptop, between two exec sessions, and `restore` is bound to what
   `check` showed.** `python3.14 /dev/stdin` reads the whole stream as the program before it runs, so the program finds
   its stdin at end of file (measured in the lab pod, §2.7): a question asked inside the pod can never be answered. The
   wrapper runs `check <ID>`, which prints the plan and one machine line, `confirmation sha256=<the copy's sha256>
   size=<its bytes> live-sha256=<the live set's fingerprint>`; it asks; it runs `preflight` again; then `restore <ID>
   --expected-sha256 … --expected-size … --expected-live-sha256 …`, which refuses with exit 3, writing nothing, when
   the copy under that ID or the live set is not the one the answer was given for. Both reviews measured the gap this
   closes: with only the ID, a copy replaced under the same ID, or a live set another restore changed, was restored on
   a plan made for other bytes. The fingerprint covers `gsd.db`, `-wal` and `-journal` by name, size and bytes, not
   `-shm`, the index SQLite rewrites on any open (§2.2). T302-10 and T302-11 are therefore wrapper tests; T302-10's
   printed facts are the helper's `check`.
4. **The ID's schema is read from the copy's header, not through SQLite.** `PRAGMA user_version` could not be read
   from a copy truncated by half (measured: the first run of T302-8 listed it under no schema at all), so its ID
   changed and `--from-version` answered "no copy has the ID" instead of the integrity failure T302-8 asks for. The
   helper reads the four bytes at offset 60 that the pragma itself reads (§2.5); a damaged copy keeps its ID and is
   refused by `integrity_check` by name. A file without the SQLite header lists as `?-<stamp>`, "no (not a database)".
5. **The group and mode are set on the temporary file, before the rename.** The issue orders "renames it onto
   `gsd.db`, then applies `chgrp 0` and `chmod g=u`". Done first, the live name never carries the wrong group, and a
   refused `chgrp` (EPERM) stops the restore while the old database is still in place.
6. **The old file is made whole before its journals go (beyond the issue).** After the live set is kept, the helper
   opens and closes `gsd.db` once, which is SQLite's own way to fold a `-wal` into the file and remove it ("The only
   safe way to remove a WAL file", §2.1) and to roll back a hot `-journal`; neither reads the schema, so a file a
   newer image wrote folds too. SQLite folds nothing, and raises nothing, while another process has the file open
   or when it cannot write it (measured, §2.1), so the helper removes a `-wal` or `-journal` only when the close
   left it absent or empty; otherwise the restore stops at the fold with nothing removed. A file SQLite cannot open
   as a database (`DatabaseError`: not a database, or corrupt) is removed around, the set kept first: replacing such a
   file is what a restore is for. A damaged file whose `-wal` holds page 1 is not such a file: SQLite opens it through
   the `-wal`, raises nothing, and its close cannot write the `-wal` back (an explicit checkpoint says `database disk
   image is malformed`; measured on a file overwritten and on one cut short by half, §2.1). The fold stops there as it
   does for a held file, and its message names that cause as well and §4a, which restores over such a file by hand.
   From that moment `/data/gsd.db` alone is the whole old database, so a kill before
   the rename loses nothing (T302-13, after-fold; measured, §4). `-journal` joins the live set because the store falls
   back to rollback mode on storage without shared memory (`local-development/gsd/store.py#stays in rollback-journal mode`),
   and a hot journal left beside another file corrupts it (§2.3).
7. **The sidecar parser is the offsite script's, held equal by a test, not shared by import.** The helper is one
   file streamed over stdin; `offsite_backup.py` runs its own `main` when executed as `__main__`, and streaming two
   files would need a loader. So `SIDECAR_LINE` and `sidecar_expected` are copied line for line
   (`charts/group-sync-dashboard/scripts/offsite_backup.py#sidecar_expected`), and
   `test_the_sidecar_parser_is_the_offsite_scripts` asserts the same pattern and the same verdict on ten sidecar
   texts, including the two the offsite review found (a digest and a name on separate lines; a name with a
   space). The walk script `pre-verify.py`'s `.split()` is not used (the issue's correction 5).
8. **The offsite source is scanned recursively for both name patterns.** #304 will ship the newest pre-upgrade copy
   off the volume and has not specified where in the claim; scanning `/offsite` for `gsd-<stamp>….db` and
   `pre-upgrade-<stamp>-schema-…` at any depth lists it without a change here. #304's spec must keep those names.
   On the lab offsite is off (§2.10), so `--list` says `/offsite is not mounted`.
9. **The runbook gets a pointer, the way back, and the keep step corrected in both manual paths, not the §4
   rewrite.** The rewrite is #300's (the issue's correction 1). But the DoD asks for the fallback's keep step to keep
   the `-wal`, and leaving it would keep a measured loss (0 of 500 rows) in the procedure this script falls back to;
   the block is a few lines inside §4a's command, which SPEC_E2 does not touch. The same block removes the
   `-journal` it now keeps: left beside the copy, an old hot journal is rolled back into it, and the restored file
   reads `database disk image is malformed` (measured, §2.3). §4b's off-volume path kept nothing before it
   overwrote `gsd.db`, and #300's issue does not list it (its T300-11 checks a keep step §4b does not have), so
   blocks 7 and 8 give §4b and its S3 note the same keep, the same removal and §4a's order (note 20). And the kept set is the way back
   from a wrong restore, but its `gsd.db` copied alone can lack every row its `-wal` held: §4's "Undo a restore"
   (block 4) says to stay in recovery mode, fold the kept set first and restore its `gsd.db` with §4a, and the
   script's last lines point there. Because the Undo runs §4a, §4a writes the copy under a temporary name before it
   removes anything and renames it after (note 20).
10. **Versions.** The `_MIGRATIONS` comment and the README row are image content
    (`.github/workflows/publish.yml#'local-development/gsd/**'`, read by
    `local-development/check-app-version-bump.py#image_content_changes`), so the pull request takes the next
    application MINOR through `prepare-release.py --app … --no-commit`, as the issue's DoD allows. The version fields,
    the Chart.yaml history line and the CHANGELOG heading are that script's output, not blocks: their numbers depend
    on what merges first.
11. **The operator's rules of 2026-10-01 on values files and Argo CD.** Every message the wrapper or the helper prints
    about recovery mode says "Set `recovery.enabled: true` and `recovery.ttl: 2h` (or a longer `recovery.ttl`, or
    `recovery.enabled: false`) in this release's values file and roll it out through the release's deployment
    pipeline". Nothing prints an Argo CD patch, an `argocd` command, `helm upgrade` or `--set`; T302-4 asserts the
    first and the third are absent. Nothing offers `oc delete pod` either: SPEC_E2 (notes 5 and 16, on main) reads
    the rule as covering any message a program prints, with the values file the only way to extend
    (`test_no_refusal_offers_a_way_but_the_values_file`; note 20). The lab walk (§5) is development and uses the lab's values file with
    `release-crc.sh`. The mock's block 3 printed an Argo CD patch; PR #505 corrects the mock.
12. **A backup name with a pod in it still lists.** #391 will put the pod into the scheduled backup's name; the
    pattern accepts anything between the stamp and `.db`, so the ID (the stamp) is unchanged by it.
13. **The executable bit.** A block cannot carry a file mode. The implementing pull request runs
    `chmod +x local-development/restore-db.sh` after `--apply` (git records `100755`);
    `test_the_wrapper_is_executable` fails until it does.
14. **The index.** This spec adds the forty-second row against `f1423143`, after E5's (#304), at the end like D5's
    (#244), and `local-development/tests/test_specs_index.py` excludes E3 from the rising-issue check by its id and pins
    it to #302 (`assert ROWS["E3"]["issue"] == "302"`), as it does D5, G1, E2, G2, E4, G3 and E5: excluded by the
    number, a row and header that both named another issue above #481 passed (note 20). Measured: with E3's row and
    header both set to #999 the test fails with `AssertionError: ('E3 is #302', '999')`. A spec merged after this one
    changes the same count sentence, heading and test, and rebases them.
15. **The margin is ten minutes.** The whole restore at the lab's size is seconds (§2.11): about 10 s under the lab's
    emulation, extrapolated from the measured parts; ten minutes covers a database a hundred times the lab's
    (extrapolated, not measured) and refuses only in the last twelfth of the default 2h TTL. A constant, not a
    setting: nothing asks to tune it. Both counts of note 2 use it.
16. **The loss plan counts the store's five history tables and names the rest (the reviews of 2026-10-01).** The
    issue names three; the store keeps five AUTOINCREMENT event tables: its own list adds `kyverno_result_event`
    (`local-development/gsd/store.py#_HISTORY_TABLES`), and `login_event`, the login audit, is pruned on its own
    (`local-development/gsd/store.py#DELETE FROM login_event WHERE id IN`). `check` counts all five, calls the count
    an estimate (after an earlier restore two branches of history can reuse ids, which no id count tells apart,
    §2.6), and names what else rolls back without a count: the current users, groups and bindings, the poll and login
    capture state, `dashboard_user_activity`, `kpi_daily`, `report_run` and the current Kyverno results.
    `test_check_counts_every_history_table_the_store_keeps` holds `HISTORY` against the store's list.
17. **The reviews of 2026-10-01: OB3 (in Grok's seat) and Codex (gpt-5.6-sol, xhigh), both "revise", decided here.**
    Both measured that the budget of §3.6 did not hold at `167ecb9b`. The design below takes one fix per finding:
    - **Taken from OB3:** the fold's check (note 6, its F1), with its exception split, so a corrupt live file is still
      replaced, which Codex's "propagate every fold error" would refuse; the way back in the runbook and the script's
      last line (F2); §4b's keep and the S3 note (F5, blocks 7 and 8); `SOURCE` 20 wide (F6); the citations of the
      margin (F7) and the counts (F8); its tests, adapted where noted below.
    - **Taken from Codex:** the binding of `restore` to the copy's sha256 and size and to the live set's fingerprint
      (its F1), over OB3's sha256 alone (F4), because only the fingerprint closes a live set that changed during the
      question; the snapshot written beside the live file first and checked there (schema and `integrity_check`)
      before the live set is kept or touched, so a copy replaced between its header read and its hash cannot take
      the live name; one lock for `list`, `check` and `restore` (note 18); the "estimate" wording and the named
      rolled-back state (F3); one action per call (F4); its eight probes, as `tests/test_restore_db_safety.py`.
    - **Rejected, with the reason:** Codex's "an SQLite open error propagates" (a live file SQLite cannot read at all
      could then never be restored over; OB3's split keeps the safety: an open that fails for a reason outside the
      file (locked, read-only, I/O) removes nothing that holds bytes, and a file SQLite cannot read is removed around
      only after the keep; its limit, a damaged file whose `-wal` holds page 1, is note 6's and note 20's); Codex's prose procedure to undo a restore by copying four names and renaming them one by one (OB3's
      is shorter and uses commands the runbook already has: fold the kept set, then §4a); the `-shm` in the live-set
      fingerprint (a `--list` between the two sessions rewrites it, §2.2, and would refuse every such restore); OB3's
      single `sha256` line (replaced by the confirmation line).
    - **Codex's tests adapted, each kept as a failing-before case:** the messages they match follow this design's
      words; `test_fold_failure_preserves_the_live_journal` holds as written (an `OperationalError` with a `-wal` that
      holds bytes refuses); the undo test reads this runbook's "Undo a restore" paragraph; the two-action test runs
      both orders (one order alone missed a mutation, §4.2).
18. **One helper operation in the pod at a time.** `list` and `check` open the live database read-only, and a
    connection open while a restore folds and renames it is the case of §2.1 (SQLite folds nothing) and howtocorrupt
    §2.5. So all three take the same `flock` for their whole run (Codex's F2), and the fold's check (note 6) still
    covers what the lock cannot see: a hand-made `oc exec` session holding the file.
19. **The snapshot comes first.** `restore` writes the copy to `gsd.db.restore.tmp` and checks it there before it keeps
    the live set: a refusal at that point leaves nothing changed and nothing kept. The keep then happens after the
    last check and before the first change, so every completed keep is a set as it was immediately before a change.

20. **The confirmation pass of 2026-10-01 (OB3, in Grok's seat) on `159deef8`.** It killed the helper at every
    traced line of a restore (3,134 SIGKILLs over seven live sets: the killed-writer `-wal`, another process holding
    the file, a `gsd.db` the pod cannot write, three not-a-database shapes, a hot `-journal`) and 27 times inside
    SQLite's close-time checkpoint: every state read as the old database or the copy, and every finished keep was the
    live set byte for byte. Four changes followed:
    - **The Undo, through §4a (blocks 4 to 6).** With `gsd.db` unwritable, "Undo a restore" as printed removed the
      live `-wal` and then could not write the copy: `gsd.db` read 40 of 540 rows (all 58 states that had a keep).
      §4a now writes the copy under a temporary name, removes, then renames (`os.replace` in the image's Python), so
      a write that fails stops before anything is removed; measured again, all 58 end on the old database whole.
      `test_the_runbooks_undo_leaves_the_old_database_whole_when_gsd_db_cannot_be_written`.
    - **A damaged file whose `-wal` holds page 1 (note 6).** Its fold refused on every attempt naming only a session
      or a permission; the message now names damage and §4a. The test meant to guard the `DatabaseError` branch never
      reached it (with the branch deleted, all 71 passed): its file now has a `-wal` without page 1, which the open
      cannot read, and a second test holds the damaged shape.
    - **No `oc delete pod` in any refusal (note 11),** as SPEC_E2 on main decided for the same rule.
    - **A TTL record whose deadline is not a finite number** is refused with exit 2 as unreadable, as E2's own read
      refuses it, instead of ending in a traceback (nothing was written either way).
    - **§4b and the S3 note in §4a's order (beyond the pass, which left them unmeasured).** They removed the side
      files and then wrote the copy onto `gsd.db`, the order F1 corrected in §4a. Both now write the copy under the
      temporary name, then remove, then rename (blocks 7 and 8). §4b, run as printed against a `gsd.db` of mode 0444
      beside a killed writer's `-wal` (500 rows), exits 0, keeps the set and leaves the copy alone (40 rows).
      `test_no_manual_path_writes_the_copy_onto_gsd_db_before_its_journals_go` holds all three paths (MF1 and MB, §4.2).
    The index pin (note 14) follows D5's, G1's, E2's, G2's, E4's and G3's. Measured and left as scope (§3.6): a writer that opens the live file
    and commits inside the few statements between the fold's check and the rename leaves its `-wal` beside the copy;
    a session open before the restore cannot (its writes go to the `-wal` the fold unlinked, or SQLite refuses them
    after the rename).

21. **The implementing pull request's versions (2026-10-01, on origin/main `64d52877`, SPEC_E2 merged at chart
    0.60.0, application 2.0.0).** The 13 blocks checked out unchanged (`13 blocks check out across 9 files`), so none
    was corrected. The Version note's derivation is taken as written: `prepare-release.py --app 2.1.0 --no-commit`
    moves the chart a PATCH, 0.60.0 to 0.60.1, so the header and the index row read chart 0.60.1, not the 0.60.5
    PR #518 assigned when it moved this spec's 0.59.26 (taking 0.60.5 with `--chart` would have put SPEC_G3's
    0.60.1, SPEC_E4's 0.60.2 and SPEC_G4's 0.60.3 at or below `Chart.yaml`). Under SPEC_E5's rule the same pull
    request moves the `specified` specs the tree now reaches, keeping each MINOR or PATCH: SPEC_G3's chart 0.60.1 to
    0.60.5 (0.60.2 to 0.60.4 are SPEC_E4's and SPEC_G4's), and the application 2.1.0 of SPEC_G2, SPEC_E4 and SPEC_E6
    to 2.4.0 (2.2.0 is SPEC_G3's, 2.3.0 SPEC_E9's), their chart cells unchanged.

**Open questions for the operator.** None.

## 1. The mandate, and what is out of scope

The issue (#302, "What must be accomplished"): `restore-db.sh --list`, run from a laptop with `oc`, lists every
restorable copy (the on-volume backups, the pre-upgrade copies, and the offsite claim's copies when the recovery pod
mounts it), one row per copy with an ID that picks out exactly one copy, its `user_version`, UTC stamp, size, source,
sidecar verdict and whether the pod's image understands it; it refuses unless the release's single pod is in recovery
mode (#303: the env is set and no uvicorn runs) and prints how to turn it on; `--from-version <id>` refuses before it
touches the live file an unknown or ambiguous ID, a copy newer than the image (both numbers named), a failed
`integrity_check` and a sidecar mismatch; it prints the loss window and the row counts it discards, asks (`--yes`
for scripts), keeps the live set under `/data/pre-restore/<stamp>/`, removes `-wal` and `-shm`, writes the copy under
a temporary name, renames it onto `gsd.db`, applies `chgrp 0` and `chmod g=u`, and prints the from and to
`user_version`, so that a failure at any step leaves neither a truncated `gsd.db` nor the restored file beside a
`-wal` it did not write; it only reads backups, runs at most one restore at a time, and starts none with less than a
margin of the recovery TTL left; it prints runbook §6's move-aside instruction when `pre-upgrade/` holds a copy for a
schema the image does not understand; it adds no RBAC and keeps runbook §4 as the fallback; it is walked on the lab as
a real rollback; and `_MIGRATIONS` says migrations are one-way.

Out of scope, each owned elsewhere: recovery mode itself (#303, SPEC_E2); the runbook's §0 and the §4 rewrite (#300);
offsite on by default and shipping pre-upgrade copies off the volume (#304); restoring from S3 (the epic keeps §4b's
S3 path manual); a backup button in the GUI (dropped on #300). The script does not move the `-to-<N>-` copy runbook §6
asks to move aside; it says so (T302-15, T302-18).

## 2. Research, measured

Every web source was fetched on 2026-10-01 with `curl` and read as text; the sentence relied on is quoted. The
lab reads ran against the release's running pod `group-sync-dashboard-7b9485f499-jspfl` (image 2.0.0) and wrote
nothing: each was a Python program streamed over `oc exec -i … python3.14 /dev/stdin` that only reads, or an
`oc get`/`oc explain`.

### 2.1 What a `-wal` holds, and how to remove one safely

**Source.** SQLite, "Write-Ahead Logging" (sqlite.org/wal.html, last updated 2026-08-25), §2: "The WAL approach
inverts this. The original content is preserved in the database file and the changes are appended into a separate WAL
file. A COMMIT occurs when a special record indicating a commit is appended to the WAL." §3.1: "SQLite will
automatically checkpoint whenever a COMMIT occurs that causes the WAL file to be 1000 pages or more in size, or when
the last database connection on a database file closes." §4: "if the last process to have the database open exits
without cleanly shutting down the database connection … then the WAL file might be retained on disk after all
connections to the database have been closed. The WAL file is part of the persistent state of the database and should
be kept with the database if the database is copied or moved. If a database file is separated from its WAL file, then
transactions that were previously committed to the database might be lost, or the database file might become
corrupted. The only safe way to remove a WAL file is to open the database file using one of the sqlite3_open()
interfaces then immediately close the database using sqlite3_close()."

**Measured** (probe P1, P4, Python 3.14.7, SQLite 3.53.4): a WAL database whose writer committed 500 rows with
`wal_autocheckpoint=0` and was killed with SIGKILL leaves `gsd.db` 12,288 bytes, `gsd.db-wal` 20,632 and `gsd.db-shm`
32,768.

    P1 kept gsd.db alone counts 0 ; the kept set counts 500
    P4 new gsd.db beside the old -wal reads 500 rows (the new file has 3); integrity ok

P4 is the failure the order of the swap exists to prevent: a new file renamed onto `gsd.db` with the old `-wal` still
beside it is silently read as the old database, and `integrity_check` says `ok`. The helper's `fold` (open, read the
header, close) leaves `gsd.db` alone holding all 540 rows of the test fixture and no `-wal` or `-shm`
(`test_the_fold_removes_the_wal_only_after_sqlite_has_written_it_back`).

**The close folds only as the last connection** (measured by the review of 2026-10-01, the same killed-writer set;
`probe_fold.py`, `probe_fold3.py`): with nothing else open, open-and-close leaves `gsd.db` alone with 540 rows. With
another process holding the file (a `mode=ro` reader after one read, as a concurrent `--list` or `check` is; or a
reader inside a transaction), or with `gsd.db` mode 0444, the same open-and-close raises nothing, the 20,632-byte
`-wal` is still there, and `gsd.db` alone holds 40 rows. Removing that `-wal` takes the 500 rows out of the live file:
with a reader holding it, a rename that then fails left `/data/gsd.db` at 40 rows under a message saying it was
whole. A newer image's last transaction, carrying a schema entry this SQLite cannot parse, still folds (540 rows):
neither `PRAGMA user_version` nor the close reads the schema, while `PRAGMA wal_checkpoint` does and raises
`malformed database schema`.

**A damaged file whose `-wal` holds page 1** (the confirmation pass of 2026-10-01, `c1_extra.py`, `corrupt-mech3`):
a `gsd.db` overwritten with 15,000 bytes that are not a database, or cut to half of its 1,662,976 bytes, beside the
1,046,512-byte `-wal` its writer left, which holds page 1 and a database of 657 pages. SQLite reads page 1 from the
`-wal`, so `PRAGMA user_version` answers and nothing is raised; the close-time checkpoint does not happen (both files
keep their sizes), and an explicit `PRAGMA wal_checkpoint(PASSIVE)` on a copy raises `database disk image is
malformed`. The fold then stops as for a held file, every attempt. With a `-wal` that covers the whole database the same open folds it
over the garbage; with no page 1 beside the file the open raises `file is not a database`, the `DatabaseError` the
fold takes as "not a database".

**What it settles.** The live set is kept whole, the old file is folded by SQLite before its journals are removed,
and both happen before the rename (§3.6); a `-wal` or `-journal` SQLite did not empty is never removed.

### 2.2 A read-only open of the live set changes only its `-shm`

**Measured** (probe P2): the same killed-writer set opened with `file:…?mode=ro`, counted, closed:

    P2 mode=ro count (500, 500) user_version 0
    P2 unchanged after a mode=ro open and close: {'gsd.db': True, 'gsd.db-wal': True, 'gsd.db-shm': False}

**What it settles.** `--list` and `check` may read the live database's `user_version` and counts through SQLite (so
the `-wal`'s rows count) without changing the database or its `-wal`; the `-shm` is the wal-index SQLite rebuilds on
any open. T302-10 asserts `gsd.db` and `gsd.db-wal` byte-identical after `check`.

### 2.3 What corrupts a database when files are moved

**Source.** SQLite, "How To Corrupt An SQLite Database File" (sqlite.org/howtocorrupt.html, last updated
2026-04-13), §1.3: "If the hot journal files are moved, deleted, or renamed after a crash or power failure, then
automatic recovery will not work and the database may go corrupt." The journal files are named "with the addition of
-journal or -wal suffix". §1.4: "The following actions are all likely to lead to corruption: … Copying a database file
without also copying its journal. Overwriting a database file with another without also deleting any hot journal
associated with the original database." §2.5: "unlinking or renaming an open database file results in behavior that
is undefined and probably undesirable."

**Measured** (the review of 2026-10-01, `runbook_4a_drive.py`): runbook §4a's command run as printed, against a
rollback-journal database whose writer died mid-transaction (a hot `gsd.db-journal`), with a copy older than it:
`rm -f /data/gsd.db-wal /data/gsd.db-shm` leaves the journal, `cat … > /data/gsd.db` writes the copy, and the next
open rolls the old journal back into the copy: `database disk image is malformed`. With the `-journal` removed too,
the copy reads whole. The helper's fold rolls the same journal back before anything is removed, and its restore
reads `ok` and 40 rows.

**What it settles.** Keep the set, not the file (T302-12); remove the old journals before the copy takes the name
(T302-13), in the script and in the runbook's manual paths alike; and rename only while no process holds the file,
which is what recovery mode, the uvicorn check and the fold's check give (T302-5).

### 2.4 `integrity_check` and `quick_check`

**Source.** SQLite, "Pragma statements" (sqlite.org/pragma.html, last updated 2026-06-04), `integrity_check`: "This
pragma does a low-level formatting and consistency check of the database … If the integrity_check pragma finds
problems, strings are returned … If pragma integrity_check finds no errors, a single row with the value 'ok' is
returned." `quick_check`: "like integrity_check except that it does not verify UNIQUE constraints and does not verify
that index content matches table content … PRAGMA quick_check runs in O(N) time whereas PRAGMA integrity_check
requires O(NlogN) time".

**Measured on the lab** (the newest backup, 14,221,312 bytes, opened `immutable=1&mode=ro` in the pod):
`integrity_check ok 0.994 s`, `quick_check ok 0.126 s`, `sha256 … 0.101 s`. On this machine a 14,938,112-byte copy of
the same shape took 0.032 s for `integrity_check`: the lab's emulated amd64 image (§2.10) runs it about 31 times
slower.

**What it settles.** The issue's `integrity_check` costs about a second at the lab's size; it is kept, run once in
`check` and once in `restore`.

### 2.5 `user_version`, and opening a copy

**Source.** pragma.html, `user_version`: "The user_version pragma will get or set the value of the user-version
integer at offset 60 in the database header." SQLite, "Database File Format" (sqlite.org/fileformat2.html, last
updated 2025-12-25): the header string is "SQLite format 3\000", and "The 4-byte big-endian integer at offset 60 is
the user version which is set and queried by the user_version pragma." SQLite, "Uniform Resource Identifiers"
(sqlite.org/uri.html): `immutable=1` "signals to SQLite that the underlying database file is held on read-only media
and cannot be modified … SQLite always opens immutable database files read-only and it skips all file locking and
change detection on immutable database files."

**Measured.** In the lab pod the newest backup's header bytes 18 and 19 are `b'\x01\x01'` (a rollback-journal
file, as `VACUUM INTO` writes it; SPEC_M1 §2.1 measured the same) and its `user_version` is 20. On this machine
`PRAGMA user_version` could not be read from a copy truncated by half (the first run of T302-8, Orchestrator's
notes, 4).

**What it settles.** A copy's schema is read from its header (`schema_of`), so a damaged copy keeps its ID; a copy is
opened `immutable=1&mode=ro` for `integrity_check` and the counts, because no `-wal` belongs to one; and because a
copy is a path another process could replace, `restore` checks the snapshot it wrote again (note 19). The live database is the exception: its `-wal` may hold a newer page 1, so its `user_version` is read
through SQLite (`live_version`, §2.2).

### 2.6 AUTOINCREMENT: the rows inserted after a copy

**Source.** SQLite, "SQLite Autoincrement" (sqlite.org/autoinc.html, last updated 2024-02-22): without the keyword,
"If you ever delete rows … then ROWIDs from previously deleted rows might be reused"; with it, "The ROWID chosen for
the new row is at least one larger than the largest ROWID that has ever before existed in that same table." The five
history tables (note 16) are declared so (`local-development/gsd/store.py#INTEGER PRIMARY KEY AUTOINCREMENT`).

**Measured on the lab** (the newest backup, read in the pod):

    membership_event count,max(id) (1843, 1843) seq (1843,)
    sync_event count,max(id) (2590, 168252) seq (168375,)
    binding_event count,max(id) (4328, 4328) seq (4328,)

`sync_event`'s rows are deleted as well as inserted: 2,590 rows remain of 168,375 ever inserted, and the 123 newest ids
are gone too. So "live minus copy" is no measure of what a restore discards, as the issue says.

**What it settles.** The rows a restore discards are the live rows with an id above the copy's highest. An id above
the copy's `MAX(id)` and at most its `sqlite_sequence` value was used and deleted before the copy was taken and is
never used again, so counting above `MAX(id)` gives the same number as counting above `sequence`, without depending
on `sqlite_sequence`. The count assumes the live database descends from the copy; after an earlier restore to an older copy, ids may
repeat on another branch of history, which no id count tells apart, so `check` calls the number an estimate (note 16). Measured in the lab pod with the probe copy of §2.10: `sync_event` live 2,611, in copy
2,590, discarded 21.

### 2.7 `oc exec -i … python3.14 /dev/stdin`: stdin, exit status, a dropped session

**Measured in the lab pod.** The probe streamed with `oc exec -i -n group-sync-dashboard <pod> -c dashboard --
python3.14 /dev/stdin one two < probe_lab.py`:

    sys.path[0] '/proc/self/fd' argv ['/dev/stdin', 'one', 'two'] python 3.14.7 sqlite 3.53.4
    stdin after the source was read: ''
    import gsd.store 1.379 s; KNOWN_SCHEMA_VERSION 20

`oc exec -n … -- python3.14 -c 'import sys; …; sys.exit(3)'` prints `command terminated with exit code 3` and `oc`
itself exits 3: the helper's exit status reaches the wrapper.

A dropped session (the `oc` client killed with SIGKILL five or six seconds into a session): a program that printed a
line every second was gone three seconds after the kill (its stdout had gone); a program that printed nothing was still
running four seconds after the kill (`proc 114 [… '/dev/stdin', 'probe-silent']`) and ended by itself at its thirty
seconds. On this lab, a dropped `oc exec` does not stop the program in the pod; a write to its closed stdout does.

**Source.** Kubernetes, kubelet configuration (v1beta1) reference, kubernetes/website `ffdd94e6`,
`content/en/docs/reference/config-api/kubelet-config.v1beta1.md` lines 830-833: "streamingConnectionIdleTimeout is
the maximum time a streaming connection can be idle before the connection is automatically closed. Deprecated: no
longer has any effect. Default: "4h"". The lab's kubelet reports `'streamingConnectionIdleTimeout': '4h0m0s'`
(`oc get --raw /api/v1/nodes/crc/proxy/configz`). The search for a primary source on what a container runtime does
to an exec'd process when its client disconnects found none; a GitLab Runner merge request says "If the connection is
cut off for some reason the process is also killed", which the measurement above contradicts for this lab.

**What it settles.** The confirmation cannot travel through the helper's stdin (Orchestrator's notes, 3). A restore
whose session drops goes on: the helper prints nothing between its steps and ignores a failed print (`say`), so it
finishes; the operation lock (§3.7) is held until it ends, so a second run is refused meanwhile. A container that ends
(at the TTL, or a deleted pod) kills it at any step; §3.6 makes every such moment safe.

### 2.8 `os.replace`, the rename, and fsync

**Source.** Python 3.14 `Doc/library/os.rst` (cpython `v3.14.0`, lines 2799-2805): `os.replace` "If successful, the
renaming will be an atomic operation (this is a POSIX requirement)" and "The operation may fail if src and dst are on
different filesystems." rename(2), Linux man-pages 6.19: "If newpath already exists, it will be atomically replaced,
so that there is no point at which another process attempting to access newpath will find it missing"; `EXDEV`
"oldpath and newpath are not on the same mounted filesystem". fsync(2), Linux man-pages 6.19: "Calling fsync() does not
necessarily ensure that the entry in the directory containing the file has also reached disk. For that an explicit
fsync() on a file descriptor for the directory is also needed." flock(2), Linux man-pages 6.19: "the lock is released
either by an explicit LOCK_UN operation on any of these duplicate file descriptors, or when all such file descriptors
have been closed."

**What it settles.** The copy is written beside `gsd.db` (same directory, same filesystem), fsynced, renamed, and the
directory fsynced; the kept set is written as `<stamp>.tmp/` and renamed when complete. The image's SQLite has
`DISABLE_DIRSYNC` (SPEC_M1 §2.1), so nothing else syncs the directory. The operation lock is an `flock`, which the
kernel releases when the process ends however it ends.

### 2.9 When the TTL ends: the pod's `startTime`

**Source.** `oc explain pod.status.startTime` on the lab: "RFC 3339 date and time at which the object was
acknowledged by the Kubelet. This is before the Kubelet pulled the container image(s) for the pod."
`oc explain pod.status.containerStatuses.state.running.startedAt`: "Time at which the container was last
(re-)started".

**Measured on the lab:** `startTime 2026-09-30T23:09:43Z`, the dashboard container's `startedAt
2026-09-30T23:09:45Z`.

**What it settles.** Orchestrator's notes, 2: `startTime + recovery.ttl` is a lower bound on SPEC_E2's deadline,
read from the pod spec with no exec, within the laptop's clock skew; the count that decides is E2's own (§2.13).

### 2.10 The lab, read-only, 2026-10-01

The probe in the pod (`probe_lab.py`, reads only):

    proc 1 ['/usr/bin/qemu-x86_64-static', '/usr/sbin/python3.14', '-m', 'uvicorn', 'gsd.api:create_app', '--factory', '--host', '127.0.0.1']
    proc 106 ['/usr/sbin/python3.14', '/dev/stdin', 'one', 'two']
    uid 1000790000 gid 0 groups [0, 1000790000] umask 0o22
    data gsd.db 15794176 0o100664 uid 1000790000 gid 1000790000
    data gsd.db-shm 32768 0o100664 uid 1000790000 gid 1000790000
    data gsd.db-wal 4511432 0o100664 uid 1000790000 gid 1000790000
    backup [('gsd-20260930T230906.692903Z.db', 14184448), ('gsd-20260930T231004.994977Z.db', 14188544), ('gsd-20261001T051103.798578Z.db', 14204928), ('gsd-20261001T111104.000930Z.db', 14221312)]
    env {'GSD_DB_PATH': '/data/gsd.db', 'GSD_CONFIG': '/etc/gsd/clusters.yaml', 'GSD_RECOVERY_MODE': None, …}
    config backupDir line ['backupDir: "/data/backup"', 'backupIntervalHours: 6', 'backupKeep: 4']

There is no `/data/pre-upgrade` and no `/data/pre-restore`, and no offsite CronJob (`oc get cronjob`: the three report
schedules). The running dashboard holds a 4.5 MB `-wal`. The pod's process holds group 0, so `chgrp 0` is allowed
for a file it owns.

**The helper itself under image 2.0.0.** Streamed unmodified into the running (not recovery) pod:

    $ oc exec -i -n group-sync-dashboard <pod> -c dashboard -- python3.14 /dev/stdin list < local-development/restore-db.py
    refused: GSD_RECOVERY_MODE is not true in this container, so it is not the recovery pod (#303)
    command terminated with exit code 2

and a probe copy of it with `GSD_RECOVERY_MODE` set inside the program and `--proc /etc` (so the running uvicorn does
not refuse it; both are for this read-only measurement only), `list` and then `check` on the newest backup:

    image    understands schema 20 and older
    live     /data/gsd.db · user_version 20
    ID                          SCHEMA  STAMP (UTC)                  SIZE  SOURCE         SIDECAR   THIS IMAGE
    20-20261001T111104.000930Z  20      2026-10-01T11:11:04Z    13.56 MiB  backup         none      yes
    20-20261001T051103.798578Z  20      2026-10-01T05:11:03Z    13.55 MiB  backup         none      yes
    20-20260930T231004.994977Z  20      2026-09-30T23:10:04Z    13.53 MiB  backup         none      yes
    20-20260930T230906.692903Z  20      2026-09-30T23:09:06Z    13.53 MiB  backup         none      yes
    # offsite: /offsite is not mounted (recovery mode mounts the offsite claim only when backup.offsite uses its pvc destination)
    real 3.12

    loss window  2026-10-01T11:11:04Z -> 2026-10-01T13:24:17Z (2h13m13s): what the dashboard recorded since is discarded
                 table                 live   in copy   discarded
                 membership_event      1843      1843           0
                 sync_event            2611      2590          21
                 binding_event         4328      4328           0
    real 4.19

The wrapper against the lab as it is (`bash local-development/restore-db.sh --list`, from the implemented copy):

    refused: pod group-sync-dashboard-7b9485f499-jspfl is not in recovery mode: its dashboard container has no GSD_RECOVERY_MODE=true, so the dashboard may be writing the database.
      Set recovery.enabled: true and recovery.ttl: 2h in this release's values file and roll it out through the release's deployment pipeline (docs/RUNBOOK_backup_restore.md, section 4). Not with oc set env: recovery mode is the chart's recovery.enabled, and a hand edit of the Deployment is not it.
    exit 2

It issued `oc get pods` and no exec.

### 2.11 How long a restore takes, for the TTL margin

**Measured on this machine** (`probe_time.py`: a database of the lab's shape, three history tables with an index,
restored through the helper as the tests run it):

| copy | `integrity_check` alone | `check` | `restore` |
|---|---|---|---|
| 14,938,112 bytes (the lab's size) | 0.032 s | 0.15 s | 0.17 s |
| 153,276,416 bytes (ten times) | 0.335 s | 0.53 s | 0.66 s |

On the lab, `check` took 4.19 s end to end through `oc exec` (§2.10), of which 1.38 s is importing `gsd.store` and
about a second `integrity_check`. With the 31-fold emulation factor of §2.4, `restore` at the lab's size is about
5 s of work plus the same 3 s of `oc exec` and import: about ten seconds. #301's lab copy was 8,876,032 bytes in
0.40 s (#301's closing comment). At a hundred times the lab's size `integrity_check` grows faster than the file
(SPEC_M1 §2.1: 218 times longer at 92 times the size), which puts a restore at a few minutes: extrapolated, not
measured.

### 2.12 The image's tools, and the interpreter

`local-development/Containerfile` ships coreutils as one binary acting as `cat`, `ls`, `base64`, `mkdir`, `chgrp`,
`chmod`, `rm` and `rmdir` ("ONE binary that acts as cat, ls, base64, mkdir, chgrp, chmod, rm or rmdir by the name it
is called"), plus `bash`, `curl` and `jq`: no `cp`, `mv`, `sleep`, `tar` or `sha256sum`. The image puts `gsd` on
`PYTHONPATH` (`/install/lib/python3.14/site-packages`), so a program streamed to `/dev/stdin` imports it (measured,
§2.7). `KNOWN_SCHEMA_VERSION` exists from application 0.37.0 (#305, `fde24c5`); `_MIGRATIONS` as `(target, title,
statements)` tuples from `fb1c8bd` (2026-08-02); `python3.14` is the image's interpreter from `7f0e3a6` (2026-08-02).

### 2.13 SPEC_E2's own count of the TTL

**Source.** SPEC_E2 at `465411cd`, §3.5 and note 15: the record `$TMPDIR/gsd-recovery.json` carries `deadline_monotonic`
("the node's `CLOCK_MONOTONIC` at the deadline") and `boot_id` ("the node's, from `/proc/sys/kernel/random/boot_id`;
empty off Linux"); "The time left is `deadline_monotonic - time.monotonic()` while `boot_id` matches, never more than
the TTL, and 0 when it does not"; its script's `remaining(record, ttl, monotonic, boot)` computes it. E2 note 3: "at
the TTL the kernel ends every process in the container with it, an `oc exec` restore still running included".

**Measured** (an export of `21132a25` with E2's blocks and then E3's applied; E2's `deadline` writes the record,
E3's `recovery_left` reads it):

    state file E2 writes: gsd-recovery.json == E3 reads: gsd-recovery.json True
    E2 remaining: 7200.0  E3 recovery_left: 7200.0
    other boot: E2 0.0  E3 0.0

**What it settles.** Note 2: `restore` refuses, before writing, on E2's own count, which a node restart or a clock
step cannot lengthen; the pod spec's bound stays as the earlier refusal from the laptop.

## 2a. Alternatives considered

| option | source | cost here | decision |
|---|---|---|---|
| Ship the helper in the image (`gsd/restore.py`) | the issue's first draft | the image a rollback targets predates it; a rollback is exactly when the older image runs | rejected (the issue's decision) |
| Ship it in the chart as a ConfigMap, as SPEC_E2 ships the recovery script | SPEC_E2 §3.2 | a chart change, a mount in recovery mode, and the restore logic tied to chart releases; E2 needs it because PID 1 must exist before any exec, a restore does not | rejected: streaming needs no chart or image change |
| `python3.14 -c "<source>"`, keeping stdin free for the answer | execve(2), Linux man-pages 6.19: "the limit per string is 32 pages (the kernel constant MAX_ARG_STRLEN)", 128 KiB with 4 KiB pages; the helper is 42,720 bytes | the human's wait would sit inside an open exec session, which the TTL and a dropped connection end; the two-session design keeps the writing session seconds long | rejected; `/dev/stdin` as the issue decided, the question on the laptop (note 3) |
| Re-run every check in `restore`, bound to nothing but the ID | this spec at `167ecb9b` | a copy replaced under the same ID, or a live set changed by another restore, is restored on the plan shown for other bytes (both reviews measured it) | replaced: the confirmation line, the copy's sha256 and size and the live set's fingerprint (note 3) |
| Bind only the copy's sha256 | OB3's review (F4) | a live set changed while the question was open still makes the loss shown wrong | rejected; the live fingerprint as well (Codex's F1) |
| Hold the in-pod lock while the laptop asks | — | an abandoned terminal holds the pod's one lock until its exec dies, and the human's wait sits in an exec session (above) | rejected; the lock is released after `check`, and the content binding covers the gap |
| Write the copy onto the live file with SQLite's backup API or `VACUUM INTO` | sqlite.org/lang_vacuum.html (VACUUM INTO "must not previously exist"), the backup API | the restored file would not be the verified bytes (its sha256 differs from the sidecar's), and it needs the live file opened read-write | rejected: copy, check the snapshot, rename |
| Check the copy where it lies and swap in the bytes read | this spec at `167ecb9b` | the copy is a path another process can replace between the header read and the hash (Codex measured `user_version 20 -> 21` under an image that understands 20) | replaced: the snapshot beside the live file is checked again (schema and integrity) before anything else happens (note 19) |
| Delete the old `-wal` and `-shm` (the runbook) | runbook §4a | between the delete and the rename `/data/gsd.db` alone lacks the `-wal`'s rows (0 of 500, §2.1) | replaced by open-and-close first (wal.html §4), then delete (note 6) |
| Delete whatever is left after the open and close | this spec at `167ecb9b` | another process holding the file, or a file the pod cannot write, leaves the `-wal` unfolded with no error, so the delete takes its rows out of the live file (§2.1) | replaced: delete only an absent or empty `-wal`/`-journal`, else stop at the fold (note 6) |
| Propagate every error of the open, and refuse any `-wal` left | Codex's review (F2) | safe, but a live file SQLite cannot read at all could never be restored over (measured: a file of garbage with no `-wal`, and with a `-wal` without page 1); a damaged file whose `-wal` holds page 1 is refused by both designs (§2.1) | rejected; OB3's split (note 17), its limit named in the refusal (note 6) |
| `PRAGMA wal_checkpoint(TRUNCATE)` instead of the open and close | pragma.html | reads the schema, and raises `malformed database schema` on a database a newer image wrote, the very file a rollback restores over (§2.1) | rejected |
| Lock `restore` only | this spec at `167ecb9b` | a `--list` or `check` in a second terminal holds the live file open while a restore folds and renames it | replaced: one lock for all three (note 18) |
| Bound the TTL with the container's `startedAt` | the issue's correction 3 | wrong after a container restart (E2 keeps the TTL) | rejected; the pod's `startTime` (note 2) |
| Bound the TTL from the pod spec alone | this spec at `167ecb9b` | blind to E2's monotonic clock and boot ID (`465411cd`), and the TTL's end kills a restore in flight | kept as the early refusal; the decision is E2's own count, read in the pod (note 2, §2.13) |
| A lock file created with `O_EXCL` | — | a killed operation leaves it held forever | rejected; `flock`, released by the kernel (§2.8) |
| A Kubernetes Lease as the lock | — | RBAC for the operator's identity and a cluster write | rejected: one pod, one kernel, and the content binding across the sessions |
| `quick_check` instead of `integrity_check` | pragma.html | eight times faster on the lab (0.126 s against 0.994 s), but skips UNIQUE and index content | rejected: a second matters less than a missed index fault before a restore |
| Discarded rows as live minus copy | the mock's first draft | retention deletes rows (2,590 of 168,375 remain, §2.6), so the difference undercounts or goes negative | rejected; ids above the copy's highest, called an estimate |
| Discarded rows above `sqlite_sequence` | autoinc.html | equal to the `MAX(id)` count on one line of history, and depends on a table SQLite lets anyone edit | rejected; `MAX(id)`, an estimate |
| Count the issue's three tables only | the issue | the store keeps five event tables, `login_event` and `kyverno_result_event` among them, and other state rolls back too (note 16) | rejected; the five, and the rest named |
| The ID's schema through `PRAGMA user_version` | — | unreadable on a damaged copy, so the ID changes (note 4) | rejected; the header's offset 60 |
| Import `offsite_backup.py` by streaming it with the helper | the issue ("reuse its checker") | a loader in the stream, and the script runs its `main` as `__main__` | rejected; copied and held equal by a test (note 7) |
| The walk script `pre-verify.py`'s sidecar check | `reports/2026-09-26_epic-b-release/walk/pre-verify.py` | `.split()` accepts what `sha256sum -c` rejects; reads each copy whole; skips copies without a sidecar | rejected (the issue's correction 5) |
| Print the Argo CD patch or `helm upgrade --set` to turn recovery on | SPEC_E2 at `b7b8e993`, the mock | an ApplicationSet may fix parameters; the operator's rule: values file, then the pipeline | rejected (note 11) |

**Reconciliation: each external claim, and the code that behaves accordingly.**

- wal.html §2, §4 (committed rows live in the `-wal`; separating it loses them): the store runs in WAL mode
  (`local-development/gsd/store.py#PRAGMA journal_mode=WAL`); `Layout.live_set` names `gsd.db`, `-wal`, `-shm` and
  `-journal`, and `keep` copies, fsyncs and renames the whole set into place before `fold` changes anything.
- wal.html §4 ("open … then immediately close"): `fold` opens `gsd.db` with `sqlite3.connect`, reads one pragma, and
  closes it, and removes a `-wal` or `-journal` only when SQLite left it absent or empty, so the only removal of a
  `-wal` with content is SQLite's own; `test_the_fold_removes_the_wal_only_after_sqlite_has_written_it_back`
  measures the 540 rows in `gsd.db` alone afterwards, `test_the_fold_removes_nothing_sqlite_did_not_fold` the stop
  when another process holds the file, and `test_fold_failure_preserves_the_live_journal` the stop when the open fails.
- howtocorrupt §1.4 (a hot journal of the original beside another file): `fold` removes `-wal`, `-shm` and `-journal`
  before `os.replace`; T302-13 kills the process before and after the rename and finds no journal beside the copy.
- howtocorrupt §2.5 (renaming a file another process has open): `in_recovery` refuses when any process's argv names
  uvicorn; the wrapper refuses when the pod spec lacks `GSD_RECOVERY_MODE`; `operation_lock` keeps the helper's own
  readers out of a restore (`test_check_cannot_open_the_live_database_during_a_restore`).
- pragma.html and fileformat2 (user_version at offset 60): `schema_of` reads `header[60:64]` big-endian; the store's
  own refusal reads the same number through `PRAGMA user_version` (`local-development/gsd/store.py#_schema_state`),
  and T302-7 matches its wording (`database schema N is newer than this dashboard understands (M)`).
- uri.html (`immutable=1` skips locking and change detection; a file that changes anyway may give wrong results):
  `integrity` and the copy's counts open `file:…?immutable=1&mode=ro`, as the offsite script does
  (`charts/group-sync-dashboard/scripts/offsite_backup.py#integrity`), and `write` checks the snapshot it wrote, a
  file only this process has written, again before it is used (`test_written_snapshot_schema_is_checked_before_the_live_set_changes`).
- autoinc.html (an AUTOINCREMENT id is never reused): the five event tables are AUTOINCREMENT
  (`local-development/gsd/store.py#INTEGER PRIMARY KEY AUTOINCREMENT`); `cmd_check` counts live rows `WHERE id > ?`
  with the copy's `MAX(id)` and calls it an estimate, because a restore earlier in the database's life starts the
  ids again from an older copy's.
- os.rst, rename(2) (atomic, same filesystem): `Layout.tmp` is `gsd.db.restore.tmp` in the database's own directory;
  the store's own copy follows the same pattern (`local-development/gsd/store.py#_pre_upgrade_copy`: temporary name,
  fsync, `os.replace`, directory fsync).
- fsync(2) (the directory entry needs its own fsync): `copy_file` fsyncs each file; `fsync_directory` follows the
  keep's rename and the swap.
- flock(2) (released when the descriptors close): `operation_lock` holds an `flock` for the whole of a `list`,
  `check` or `restore` and writes no marker a later run must clear; T302-16 shows a second restore refused and a third,
  after the holder closed, succeed.
- `oc explain pod.status.startTime` (before the image pull): `preflight` adds the TTL to `status.startTime`.
- SPEC_E2 §3.5 (the time left from `deadline_monotonic` and `boot_id`): `recovery_left` computes it the same way,
  measured equal to E2's `remaining` (§2.13).
- The offsite script's sidecar grammar: `SIDECAR_LINE` and `sidecar_expected` in the helper equal
  `charts/group-sync-dashboard/scripts/offsite_backup.py#SIDECAR_LINE` and `#sidecar_expected` on ten texts
  (`test_the_sidecar_parser_is_the_offsite_scripts`).
- `config.backup.dir` as the app reads it: `GSD_BACKUP_DIR`, else `backupDir` (`local-development/gsd/config.py#GSD_BACKUP_DIR`);
  `config_backup_dir` reads the same two in the same order.
- The operator's rule on switches: every recovery-mode instruction the programs print names `recovery.enabled` or
  `recovery.ttl` in the release's values file and its deployment pipeline (`_values_hint`); T302-4 asserts no
  Argo CD or Helm command.

## 3. The design

### 3.1 Two programs, one file each

`local-development/restore-db.sh` (bash, 104 lines) runs on the laptop. `local-development/restore-db.py` (Python,
792 lines with its docstrings) has four commands: `preflight` runs on the laptop's `python3` and reads the pod
list; `list`, `check <ID>` and `restore <ID>` run in the pod, one at a time (§3.7), streamed as `oc exec -i -n <ns>
<pod> -c dashboard -- python3.14 /dev/stdin <command>` with the file on stdin. The helper imports only the standard
library on the laptop, and in the pod `gsd.store` (for the schema the image understands) and `yaml` (to read
`backupDir`), both the image's. Its syntax is Python 3.9's (`test_the_helper_parses_on_the_oldest_python_it_meets`),
for an older laptop `python3`; it was run on 3.14.7 here and in the lab pod, and CI runs it on 3.11 and 3.14.

### 3.2 The wrapper's order

1. `oc get pods -n <ns> -l app=<release> -o json | python3 restore-db.py preflight`: exactly one pod; its dashboard
   container's spec has `GSD_RECOVERY_MODE=true`; the container is running; `startTime + GSD_RECOVERY_MODE_TTL - now`
   is at least `MARGIN_SECONDS` (600). Any failure: exit 2 with the reason and what to set, and no exec. It prints
   `pod <name> · recovery mode, at least <time> of its TTL left` and `image <image>`.
2. `--list`: `list` in the pod; done.
3. `--from-version <ID>`: `check <ID>` in the pod (every check, the plan, and the confirmation line; it writes
   nothing). Without `--yes`, the question `Restore <ID> over the live database? [y/N]` on the laptop; any answer but
   `y`/`yes` exits 4 with nothing changed. Then `preflight` again (the answer may have taken minutes): the same pod and
   enough TTL, or exit 2. Then `restore <ID> --expected-sha256 <sha256> --expected-size <size>
   --expected-live-sha256 <fingerprint>` with the confirmation line's three values (note 3).

`--list` and `--from-version` exclude each other: both in one call is a usage error, exit 64, in either order.
`--namespace` and `--release` default to `group-sync-dashboard`, the runbook's `$NS` and `$REL`; the pods are found by
`app=<release>`, the chart's selector label (`charts/group-sync-dashboard/templates/_helpers.tpl#app: {{ include "gsd.fullname" . }}`),
which on the lab selects the dashboard pod and not the report pod (`oc get pods -l app=group-sync-dashboard -o name`:
one pod).

### 3.3 The copies, and their IDs

| source | where | name |
|---|---|---|
| `backup` | `GSD_BACKUP_DIR`, else `backupDir` in `GSD_CONFIG` (`/data/backup` by default); none when backups are off | `gsd-<stamp>.db`, or `gsd-<stamp>-<anything>.db` (note 12) |
| `pre-upgrade` | `pre-upgrade/` beside `GSD_DB_PATH` (SPEC_M1 §3.1) | `pre-upgrade-<stamp>-schema-<from>-to-<to>-<pod>.db` |
| `offsite` | `/offsite`, at any depth, when it is mounted (SPEC_E2 §3.8) | either of the two |

The ID is `<user_version>-<stamp>`, the stamp exactly as the name carries it, microseconds included (the epic's decision;
two copies can share a second). `user_version` is read from the header (§2.5). Two files with one ID are the same name
in two sources, which the offsite job makes (it keeps a backup's name). Byte-identical (equal sha256), they are one row
whose source names both (`backup+offsite`) and whose sidecar verdict is the strongest of theirs (a matching sidecar on
one verifies the bytes of both); the restore reads the on-volume one. Differing, they are one row, a note line naming
both files and both digests, and `--from-version` refuses the ID. So no two rows share an ID and every ID names one set
of bytes (T302-2).

`--list` prints the image's schema, the live file's `user_version`, then one row per ID, newest first:
`ID`, `SCHEMA`, `STAMP (UTC)`, `SIZE` (MiB), `SOURCE` (20 wide: `pre-upgrade+offsite` is 19), `SIDECAR` (`ok`,
`mismatch`, `none`) and `THIS IMAGE` (`yes`; `yes, migrates N -> K on start`; `no (N > K)`; `no (not a database)`).
Notes follow: what `none` means, that backups are off, that `/offsite` is not mounted, any differing twins, and §3.9's
move-aside note.

### 3.4 The checks, before anything is written

In the pod, before anything else, exit 2: `GSD_RECOVERY_MODE` not `true`; any process whose argv has `uvicorn` (read
from every `/proc/<pid>/cmdline`, because PID 1 may be `qemu-x86_64-static`, §2.10); another helper operation holding
the lock (§3.7); and, in `restore`, less than ten minutes of the TTL as SPEC_E2 counts it, or no record to count it
from (note 2). Then, each a refusal with exit 3 that names the copy: an ID no copy has; an ID whose files differ; a
file that is not a database; a schema above the image's `KNOWN_SCHEMA_VERSION`, in the store's own words, with the
newest copy the image does understand; a sidecar that does not match (both digests) or is malformed;
`integrity_check` other than `ok`; and, in `restore`, a copy or a live set other than the ones on the confirmation
line (note 3), and a snapshot that, once written beside the live file, reads another schema or fails
`integrity_check` (note 19). The schema the image understands is `gsd.store.KNOWN_SCHEMA_VERSION`, or, in an image
older than #305, the highest target in `gsd.store._MIGRATIONS`, which is the same definition
(`local-development/gsd/store.py#KNOWN_SCHEMA_VERSION`).

### 3.5 What a restore discards, shown before the question

`check` prints the candidate, its integrity, its sidecar, the schemas (copy, live, image), the loss window from the
copy's stamp to now, and per history table (`membership_event`, `sync_event`, `binding_event`,
`kyverno_result_event`, `login_event`: note 16) the live rows, the copy's rows, and the live rows with an id above the
copy's highest (§2.6). One line calls that last column an estimate and says why it is not the difference; one names
the state that rolls back without a count. A table the copy lacks counts every live row; a table the live file lacks
prints `-`. The live database is read through SQLite read-only (§2.2). The last line is the confirmation line.

### 3.6 The swap, and what a failure leaves

`restore` takes the lock (§3.7), counts the TTL (note 2), repeats §3.4 and compares the confirmation, prints one line
saying so, and then prints nothing until the swap is done. In order:

1. **Tidy.** Remove what a killed restore left: `gsd.db.restore.tmp`, and any `pre-restore/<stamp>.tmp/`.
2. **Space.** The live set's size plus the copy's must fit in the free space of the database's directory, or exit 1
   with both numbers and nothing written.
3. **Write.** Copy the candidate to `gsd.db.restore.tmp` beside `gsd.db`, hashing what it writes and fsyncing it; a
   digest other than the one checked is a failure (the copy changed while it was read). Read the snapshot's schema
   from its header and run `integrity_check` on it: another schema than the checks saw, or a schema the image does not
   understand, or a failed check, is exit 3 with the snapshot removed (note 19). `chgrp 0`, `chmod g=u` (note 5).
4. **Keep.** Copy the live set into `pre-restore/<stamp>.tmp/`, each file fsynced, `chgrp 0` and `chmod g=u` on each
   (and on directories it creates), the directory fsynced, then renamed to `pre-restore/<stamp>/`.
5. **Fold.** Open and close `gsd.db` once with SQLite (note 6). If a `gsd.db-wal` or `gsd.db-journal` still holds
   bytes and the file is one SQLite can open as a database, SQLite did not fold it (another process holds it, the
   pod cannot write it, or it is damaged so that its close cannot write the `-wal` back, §2.1): exit 1 at the step
   `fold`, nothing beside `gsd.db` removed, the message naming the three and §4a. Otherwise remove `gsd.db-wal`,
   `gsd.db-shm` and `gsd.db-journal`.
6. **Swap.** `os.replace(gsd.db.restore.tmp, gsd.db)`, then fsync the directory.
7. Print the kept set, what was removed, what was written and its sha256, `user_version <from> -> <to>`, the line
   saying to set `recovery.enabled: false` in the values file and roll it out, the way back (the kept set, and runbook
   §4's "Undo a restore"), and §3.9's note.

**Budget, per release: at every instant, `/data/gsd.db` and what sits beside it read as either the old database
whole or the checked copy with no journal of the old one; and a `pre-restore/<stamp>/` directory, once it has that
name, holds the whole live set as it was just before the first change.** Its scope: a restore run by this helper in
the release's one recovery pod, on a filesystem that renames atomically within a directory (POSIX), with the process
killed at any moment (SIGKILL, the container's end at the TTL, a deleted pod) or a step failing with an error, and
with any other process in the pod holding the live file open (a reader, or a session open before the restore:
measured). Not a process that writes: one that opens the live file and commits inside the few statements between the
fold's check and the rename leaves its `-wal` beside the copy (measured, note 20); nothing in recovery mode writes the
database. Kill points measured (T302-13): after the write, in the
middle of the keep, after the keep, after the fold, just before the rename, just after it. Each leaves the old
database whole (540 rows) or the copy alone, and a later run completes the restore. A failure with an error removes
the temporary copy and says what is on disk, by step (`test_a_failed_rename_names_the_state_and_leaves_the_old_database_whole`).
Another process holding the file (an `oc exec` session) or a file the pod cannot write makes SQLite fold nothing;
the fold then stops with nothing removed (`test_the_fold_removes_nothing_sqlite_did_not_fold`), where removing the
`-wal` would have left `/data/gsd.db` at 40 of 540 rows (§2.1). Not in scope: a power cut on storage that loses
fsynced data, and the runbook's manual paths.

### 3.7 One helper operation at a time

**Budget: at most one of `list`, `check` and `restore` runs in the release's recovery pod at any time.** The release
has one pod in recovery mode (SPEC_E2 refuses `replicaCount` other than 1, and `preflight` refuses any count but
one), and in that pod each of the three holds `flock(LOCK_EX | LOCK_NB)` on `$TMPDIR/gsd-restore.lock` (`/tmp`, the
pod's emptyDir) for its whole run (note 18). A second is refused with exit 2, naming the holder's start instant, pid
and operation, which the holder writes into the file. The kernel drops the lock when the holder ends, however it ends
(§2.8), so a dropped session's restore holds it until it finishes and a killed one holds nothing. The lock is released
between `check` and `restore`, while the laptop asks; the confirmation line (note 3) carries what the answer was
given for across that gap. Scope: the helper's own operations; an `oc debug` pod, a hand-typed runbook block or a
hand-made `oc exec` session is outside the lock, and the fold's check is what stands against the last when it holds
the file as the fold runs (§3.6 for one that opens it later).

### 3.8 The TTL margin

**Budget: no `check` or `restore` session starts with less than ten minutes (`MARGIN_SECONDS`) of the recovery TTL
left by the pod spec's bound, and no restore writes anything with less than ten minutes left as SPEC_E2 counts
it.** `preflight` computes `startTime + TTL - now` from the pod spec (note 2) before each session; `restore` computes
E2's own `deadline_monotonic - monotonic` with the boot-ID check under its lock (§2.13). Each refuses naming the time
left, and what to set: a longer `recovery.ttl` in the values file (a new pod, a new TTL), the only way to extend
(note 11). Scope: restores started by the helper; `preflight` uses the laptop's clock, so a skew between it
and the node's moves only the early refusal. Ten minutes is note 15's number.

### 3.9 The move-aside note (runbook §6)

When `pre-upgrade/` holds a copy whose `-to-<N>-` is above the image's schema, `list`, `check` and `restore` print:
the file, that the image does not understand N, that it and its `.sha256` must be moved out of `pre-upgrade/` before
that upgrade is tried again or the new attempt takes no copy (`local-development/gsd/store.py#_pre_upgrade_copy`
skips when a copy for its target exists), the runbook section, and "This script moves nothing."

### 3.10 Only reads the copies

**Budget: the script never deletes, moves, renames, rotates or writes a copy.** It opens copies only to read them
(`immutable=1&mode=ro` or a byte stream), and it writes only in the database's own directory (`gsd.db`,
`gsd.db.restore.tmp`, the removal of `gsd.db-wal`, `-shm`, `-journal`, and `pre-restore/`) and `$TMPDIR/gsd-restore.lock`.
The offsite claim is mounted read-only by SPEC_E2 as well. T302-15 hashes the three sources before and after a
`list` and a `restore`.

### 3.11 Permissions and the runbook

No RBAC is added anywhere: the script runs as the operator, who needs `get` on pods and `create` on `pods/exec` in the
namespace, which the runbook's procedure already needs. No file under `charts/` changes, so the rendered chart and
its RBAC are byte-identical (T302-19). The runbook's §4 opens with a paragraph that points at the script and keeps the
commands below it as the fallback, and a second, "Undo a restore": stay in recovery mode, take a finished keep (never
a `.tmp` one), fold it, and restore its `gsd.db` with §4a. §4a's and §4b's keep steps keep the live set, and both
remove the `-journal` with the `-wal` and `-shm` (note 9); §4a, §4b and the S3 note write the copy under a temporary name
before they remove anything and rename it after; the Undo depends on §4a's (note 20).

### 3.12 The CHANGELOG and the one-way comment

One entry first under `## Unreleased`. Above `_MIGRATIONS`, four comment lines: migrations are one-way, #305 refuses
the database after one, and the way back is the pre-upgrade copy restored with this script in recovery mode, or the
runbook's §4 (T302-21). No code changes in `store.py`.

## 4. Tests

### 4.1 One test per issue test case

`local-development/tests/test_restore_db.py` (block 11) runs the helper as the pod does, `python /dev/stdin <command>`
with the file on stdin, against a temporary `/data`, `/offsite`, `/proc` and `$TMPDIR` holding SPEC_E2's TTL record;
the fixture's live database holds 40 rows a table and 500 more `sync_event` rows committed only to its `-wal` by a
writer killed before a checkpoint. `local-development/tests/test_restore_db_wrapper.py` (block 12) runs `bash
restore-db.sh` with `oc` stubbed on PATH, as `local-development/tests/test_release_crc.py#STUB` does; the stub answers
`oc get pods` from a JSON file and runs `oc exec … python3.14 /dev/stdin <args>` here with the streamed helper.
`local-development/tests/test_restore_db_safety.py` (block 13) is Codex's review probes (note 17).

| ID | test | fails without the change because |
|---|---|---|
| T302-1 | `test_t302_1_list_shows_every_copy_with_its_id_schema_source_sidecar_and_verdict` | no `restore-db.py`: the stream it is read from does not exist (§4.2) |
| T302-2 | `test_t302_2_a_byte_identical_offsite_twin_is_one_row_and_a_differing_one_is_refused` | as T302-1 |
| T302-3 | `test_t302_3_a_copy_newer_than_this_image_is_listed_as_not_understood` | as T302-1 |
| T302-4 | `test_t302_4_outside_recovery_mode_it_refuses_names_the_value_and_never_execs` | no `restore-db.sh` |
| T302-5 | `test_t302_5_none_or_two_pods_are_refused_before_any_exec[0, 2]`, `test_t302_5_uvicorn_in_the_pod_is_refused_by_the_helper_and_nothing_is_written`, `test_t302_5_a_uvicorn_process_or_a_missing_env_is_refused_in_the_pod` | as T302-1 and T302-4 |
| T302-6 | `test_t302_6_an_unknown_id_is_refused_and_nothing_is_touched` | as T302-1 |
| T302-7 | `test_t302_7_a_copy_newer_than_this_image_is_refused_with_both_numbers` | as T302-1 |
| T302-8 | `test_t302_8_a_truncated_copy_is_refused_by_integrity_check` (and a file that is not a database) | as T302-1 |
| T302-9 | `test_t302_9_a_sidecar_naming_another_digest_is_refused_with_both` | as T302-1 |
| T302-10 | `test_t302_10_check_prints_the_loss_window_and_the_rows_inserted_after_the_copy` (25 pruned rows: live 15, copy 40, discarded 0; `sync_event` 540, 40, 500) and `test_t302_10_answering_no_writes_nothing_after_the_loss_window_is_shown` | as T302-1 and T302-4 |
| T302-11 | `test_t302_11_yes_restores_without_asking` | as T302-4 |
| T302-12 | `test_t302_12_the_live_set_is_kept_whole_with_its_wal` | as T302-1; and the runbook's keep, followed by hand, keeps `gsd.db` alone (0 of 500, §2.1) |
| T302-13 | `test_t302_13_a_kill_after_any_step_leaves_the_old_database_or_the_new_one[after-write, mid-keep, after-keep, after-fold, before-rename, after-rename]` | as T302-1 |
| T302-14 | `test_t302_14_the_copy_replaces_the_database_with_no_journal_and_the_group_set` | as T302-1 |
| T302-15 | `test_t302_15_the_sources_are_only_read` | as T302-1 |
| T302-16 | `test_t302_16_a_second_restore_is_refused_while_one_runs` | as T302-1 |
| T302-17 | `test_t302_17_too_little_ttl_left_is_refused_from_the_pod_spec_alone` | as T302-4 |
| T302-18 | `test_t302_18_a_copy_for_a_schema_this_image_lacks_gets_the_move_aside_note` | as T302-1 |
| T302-19 | no file under `charts/` changes (`git diff --stat` on the applied tree, §4.3), so every render, its RBAC included, is byte-identical: REMOVED 0, ADDED 0 | a regression guard; it holds at the merge base too |
| T302-20 | the lab walk, §5 | — |
| T302-21 | `test_t302_21_migrations_say_they_are_one_way_and_name_the_way_back` | the lines above `_MIGRATIONS` are blank |

T302-14 checks the group with `--group <the test's own gid>`: a CI runner is not in group 0, so the default (0) cannot
be shown there; the lab walk (§5, step 6) reads `gid 0` on the restored file.

Added by the research and the design:

| test | holds |
|---|---|
| `test_a_failed_rename_names_the_state_and_leaves_the_old_database_whole` | §3.6: an error at the rename leaves the folded old database, no temporary copy, and a message naming the step |
| `test_a_copy_that_changed_after_its_check_is_not_swapped_in` | §3.6 step 3: bytes other than the checked ones never take the live name |
| `test_the_sidecar_parser_is_the_offsite_scripts[case0 … case9]` | note 7 |
| `test_preflight_bounds_the_ttl_by_the_pods_start_not_the_containers_restart` | note 2, §3.8 |
| `test_the_go_durations_recovery_ttl_takes` | the TTL grammar; equal to SPEC_E2's parser once its script exists |
| `test_an_image_older_than_known_schema_version_reads_it_from_the_migrations` | §3.4 |
| `test_the_backup_directory_is_read_from_the_config_when_the_env_does_not_set_it` | §3.3, and the "backups are off" note |
| `test_the_fold_removes_the_wal_only_after_sqlite_has_written_it_back` | §2.1, note 6 |
| `test_the_helper_parses_on_the_oldest_python_it_meets` | §3.1 |
| `test_the_wrapper_is_executable` | note 13 |
| `test_list_prints_the_pod_the_image_and_the_rows`, `test_usage_errors_exit_64` | §3.2 |

Added by the reviews of 2026-10-01 (note 17; each fails on the blocks of `167ecb9b`, except the two guards):

| test | holds |
|---|---|
| `test_the_fold_removes_nothing_sqlite_did_not_fold` (OB3) | note 6, §3.6 step 5: another process holds the live file; the fold stops with nothing removed and the old database whole |
| `test_the_fold_folds_a_database_a_newer_image_wrote` (OB3) | §2.1: the rollback shape still folds (a guard: passes before and after) |
| `test_a_live_file_that_is_not_a_database_is_replaced_around` (OB3; its file reshaped by note 20) | note 6: the fold's check never blocks a file SQLite cannot open: its `-wal` holds no page 1, so the open raises `DatabaseError` (a guard; red with that branch removed) |
| `test_check_counts_every_history_table_the_store_keeps` (OB3) | note 16 |
| `test_restore_refuses_a_copy_or_a_live_set_other_than_the_ones_check_showed` | note 3, the helper's half: a wrong sha256, size or fingerprint, and a partial confirmation, each exit 3 with nothing written |
| `test_the_live_fingerprint_ignores_the_shm_a_reader_rewrites` | note 3, note 17: a rewritten `-shm` is no change |
| `test_the_restore_reads_the_ttl_left_as_recovery_mode_counts_it[too-little-left, the-node-restarted, no-record, not-a-finite-number]` | note 2, §2.13 |
| `test_the_restore_is_bound_to_what_check_showed` (wrapper) | note 3, the wrapper's half |
| `test_list_keeps_a_long_source_apart_from_its_sidecar` (OB3) | §3.3 |
| `test_the_runbooks_undo_folds_the_kept_set_into_one_whole_file` (OB3) | note 9, block 4 |
| `test_the_runbook_removes_every_journal_it_keeps` (OB3) | note 9, §2.3, blocks 5, 7 and 8 |
| `tests/test_restore_db_safety.py`: `test_confirmed_candidate_bytes_are_bound_to_the_restore`, `test_confirmed_live_set_is_bound_to_the_loss_plan`, `test_written_snapshot_schema_is_checked_before_the_live_set_changes`, `test_fold_failure_preserves_the_live_journal`, `test_loss_plan_names_all_append_only_history_and_other_rolled_back_state`, `test_wrapper_rejects_two_actions[list-first, restore-first]`, `test_check_cannot_open_the_live_database_during_a_restore`, `test_runbook_explains_how_to_recover_a_kept_live_set` (Codex) | notes 3, 6, 16, 17, 18, 19; §3.2 |

Added by the confirmation pass of 2026-10-01 (note 20; each fails on the blocks of `159deef8`):

| test | holds |
|---|---|
| `test_the_runbooks_undo_leaves_the_old_database_whole_when_gsd_db_cannot_be_written` | note 20, blocks 4 to 6: "Undo a restore" as printed, after a restore that stopped at the fold |
| `test_a_damaged_live_file_whose_wal_holds_page_1_stops_at_the_fold_and_says_so` | note 6, §2.1, §3.6 step 5 |
| `test_no_refusal_offers_a_way_but_the_values_file`, and T302-17's last assertion | note 11 |
| `test_no_manual_path_writes_the_copy_onto_gsd_db_before_its_journals_go` | note 20: §4a, §4b and the S3 note write under the temporary name, never onto `gsd.db` |
| `test_the_restore_reads_the_ttl_left_as_recovery_mode_counts_it[not-a-finite-number]` | note 2 |

### 4.2 Each test fails without the change

**On a clean tree of origin/main `b5463d45`, before the blocks**, with the three new test modules copied in and run
with `PYTHONPATH` at that tree's `local-development`: `76 failed in 2.69s`, none passing (`75 failed` on `73cc7d08` in
the confirmation pass; `71 failed` on `21132a25` with the 71 tests of `159deef8`). The helper's tests fail on
`FileNotFoundError: … 'restore-db.py'` (opening it as the stream, or loading it; the kill drivers report it from their
own process); the wrapper's on `bash` exiting 127, `restore-db.sh: No such file or directory`; T302-21 on
`assert ('ONE-WAY' in '')`; the runbook tests on the two-name `rm` lines and the missing paragraphs;
`test_the_wrapper_is_executable` on `assert False`. **After `--apply` and `chmod +x`:** `76 passed in 12.55s`.

**Against the blocks of `167ecb9b`** the reviews measured their own probes failing: OB3's seven (`7 failed, 51
passed` with its tests) and Codex's eight (`8 failed`); each is in the table above and passes here. **Against the
blocks of `159deef8`** the confirmation pass's tests give `5 failed, 70 passed`, each on its own defect (note 20).

**Mutations of the implemented tree**, each in a scratch copy of the applied tree, the three modules run against it
(`mutate2.py`, §4.3). Each mutation turns red the tests named:

| run | the change | result | tests that go red |
|---|---|---|---|
| M0 | none | 76 passed | — |
| M1 | the old -wal removed without opening the file first (the runbook's order) | 9 failed, 67 passed | test_a_damaged_live_file_whose_wal_holds_page_1_stops_at_the_fold_and_says_so, test_a_failed_rename_names_the_state_and_leaves_the_old_database_whole, test_fold_failure_preserves_the_live_journal, test_t302_13_a_kill_after_any_step_leaves_the_old_database_or_the_new_one, test_the_fold_folds_a_database_a_newer_image_wrote, test_the_fold_removes_nothing_sqlite_did_not_fold, test_the_fold_removes_the_wal_only_after_sqlite_has_written_it_back, test_the_runbooks_undo_leaves_the_old_database_whole_when_gsd_db_cannot_be_written |
| M2 | the live set kept as gsd.db alone | 8 failed, 68 passed | test_t302_11_yes_restores_without_asking, test_t302_12_the_live_set_is_kept_whole_with_its_wal, test_t302_13_a_kill_after_any_step_leaves_the_old_database_or_the_new_one, test_the_runbooks_undo_folds_the_kept_set_into_one_whole_file, test_the_runbooks_undo_leaves_the_old_database_whole_when_gsd_db_cannot_be_written |
| M3 | the journals removed after the rename, not before | 10 failed, 66 passed | test_a_failed_rename_names_the_state_and_leaves_the_old_database_whole, test_a_live_file_that_is_not_a_database_is_replaced_around, test_t302_11_yes_restores_without_asking, test_t302_13_a_kill_after_any_step_leaves_the_old_database_or_the_new_one, test_t302_14_the_copy_replaces_the_database_with_no_journal_and_the_group_set, test_the_runbooks_undo_leaves_the_old_database_whole_when_gsd_db_cannot_be_written |
| M4 | no lock | 2 failed, 74 passed | test_check_cannot_open_the_live_database_during_a_restore, test_t302_16_a_second_restore_is_refused_while_one_runs |
| M5 | the schema read through PRAGMA user_version | 1 failed, 75 passed | test_t302_8_a_truncated_copy_is_refused_by_integrity_check |
| M6 | discarded as live minus copy | 1 failed, 75 passed | test_t302_10_check_prints_the_loss_window_and_the_rows_inserted_after_the_copy |
| M7 | no uvicorn check | 2 failed, 74 passed | test_t302_5_a_uvicorn_process_or_a_missing_env_is_refused_in_the_pod, test_t302_5_uvicorn_in_the_pod_is_refused_by_the_helper_and_nothing_is_written |
| M8 | the twins not compared | 1 failed, 75 passed | test_t302_2_a_byte_identical_offsite_twin_is_one_row_and_a_differing_one_is_refused |
| M9 | no TTL margin in preflight | 3 failed, 73 passed | test_no_refusal_offers_a_way_but_the_values_file, test_preflight_bounds_the_ttl_by_the_pods_start_not_the_containers_restart, test_t302_17_too_little_ttl_left_is_refused_from_the_pod_spec_alone |
| M10 | the written bytes not compared with the checked digest | 1 failed, 75 passed | test_a_copy_that_changed_after_its_check_is_not_swapped_in |
| M11 | a copy newer than the image accepted | 1 failed, 75 passed | test_t302_7_a_copy_newer_than_this_image_is_refused_with_both_numbers |
| M12 | the fold's check: a -wal SQLite did not fold is removed | 4 failed, 72 passed | test_a_damaged_live_file_whose_wal_holds_page_1_stops_at_the_fold_and_says_so, test_fold_failure_preserves_the_live_journal, test_the_fold_removes_nothing_sqlite_did_not_fold, test_the_runbooks_undo_leaves_the_old_database_whole_when_gsd_db_cannot_be_written |
| M13 | restore ignores the confirmation | 3 failed, 73 passed | test_confirmed_candidate_bytes_are_bound_to_the_restore, test_confirmed_live_set_is_bound_to_the_loss_plan, test_restore_refuses_a_copy_or_a_live_set_other_than_the_ones_check_showed |
| M14 | HISTORY back to the issue's three | 2 failed, 74 passed | test_check_counts_every_history_table_the_store_keeps, test_loss_plan_names_all_append_only_history_and_other_rolled_back_state |
| M15 | SOURCE back to 15 wide | 1 failed, 75 passed | test_list_keeps_a_long_source_apart_from_its_sidecar |
| M16 | the wrapper drops the confirmation | 3 failed, 73 passed | test_confirmed_candidate_bytes_are_bound_to_the_restore, test_confirmed_live_set_is_bound_to_the_loss_plan, test_the_restore_is_bound_to_what_check_showed |
| M17 | runbook §4a leaves the -journal | 2 failed, 74 passed | test_runbook_explains_how_to_recover_a_kept_live_set, test_the_runbook_removes_every_journal_it_keeps |
| M18 | no in-pod TTL check | 3 failed, 73 passed | test_no_refusal_offers_a_way_but_the_values_file, test_the_restore_reads_the_ttl_left_as_recovery_mode_counts_it |
| M19 | the snapshot's schema not checked again | 1 failed, 75 passed | test_written_snapshot_schema_is_checked_before_the_live_set_changes |
| M20 | two actions accepted by the wrapper | 1 failed, 75 passed | test_wrapper_rejects_two_actions |
| M21 | the live fingerprint includes the -shm | 1 failed, 75 passed | test_the_live_fingerprint_ignores_the_shm_a_reader_rewrites |
| M22 | check opens the live database without the lock | 1 failed, 75 passed | test_check_cannot_open_the_live_database_during_a_restore |
| MF1 | runbook §4a back to removing, then cat onto gsd.db | 2 failed, 74 passed | test_no_manual_path_writes_the_copy_onto_gsd_db_before_its_journals_go, test_the_runbooks_undo_leaves_the_old_database_whole_when_gsd_db_cannot_be_written |
| MB | runbook §4b back to removing, then cat onto gsd.db | 1 failed, 75 passed | test_no_manual_path_writes_the_copy_onto_gsd_db_before_its_journals_go |
| MF2 | the fold's refusal without §4a's way for a damaged file | 1 failed, 75 passed | test_a_damaged_live_file_whose_wal_holds_page_1_stops_at_the_fold_and_says_so |
| MN1 | a TTL refusal offers oc delete pod again | 1 failed, 75 passed | test_no_refusal_offers_a_way_but_the_values_file |
| MN2 | a deadline that is not a finite number accepted | 1 failed, 75 passed | test_the_restore_reads_the_ttl_left_as_recovery_mode_counts_it |
| MD | the open's DatabaseError branch deleted (it propagates) | 1 failed, 75 passed | test_a_live_file_that_is_not_a_database_is_replaced_around |

All measured on the 76 tests of this revision on `b5463d45` (`mutate3.py`; a parametrized test counts once per case,
its name once). MD deletes the branch, so the open's `DatabaseError` propagates, as the confirmation pass measured it;
taking it as an `OperationalError` instead (`pass`) leaves all 76 green, because on that shape SQLite's failed open
still folds and removes the `-wal`, so the fold has nothing to refuse either way.

M1 is the runbook's own order (remove the `-wal` without opening the file): a kill after the removal, or a failed
rename, leaves `/data/gsd.db` without the `-wal`'s 500 rows. M3 (the journals removed after the rename) leaves the
restored file beside the old `-wal` at a kill between the two, which P4 (§2.1) reads as the old database. M12 is the
defect both reviews measured at `167ecb9b`; M13 and M16 the unbound confirmation; M18 the TTL counted from the pod spec
alone.

### 4.3 The proof

§7 was not written by hand. The design was implemented in a detached worktree of `b5463d45` (OB3's corrected blocks
applied, then Codex's design merged in as note 17 says, then the confirmation pass); a generator cut each block's Old text from `b5463d45` and its
New text from the implemented copy, at whole lines, joining hunks fewer than ten lines apart unless that would enclose
a fence line, with the fewest context lines that make the Old text unique, and checked that each file's blocks,
applied in order, give the implemented file byte for byte: `13 blocks across 9 files reproduce the implemented copy`.
Then, on a fresh detached worktree of `b5463d45`:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E3_restore_db.md <tree>
    13 blocks check out across 9 files
    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E3_restore_db.md <tree> --apply
    chmod +x <tree>/local-development/restore-db.sh

After `--apply` every changed and created file is identical (`cmp`) to the implemented copy. On that tree, with
`PYTHONPATH` at its `local-development` and the venv's Python 3.14.7:

| check | command | result |
|---|---|---|
| the new tests, before the blocks | the three new modules copied into a clean tree of `b5463d45` | `76 failed in 2.69s` (§4.2) |
| the new tests, after | `pytest tests/test_restore_db.py tests/test_restore_db_wrapper.py tests/test_restore_db_safety.py -q -p no:cacheprovider` | `76 passed in 12.55s` |
| the blocks, on origin/main | `apply-spec-blocks.py` on an export of `b5463d45`, then `cmp` against the implemented copy; and on `f1423143` (SPEC_E5 merged; it changed only `docs/specs/` and `test_specs_index.py`) | `13 blocks check out across 9 files` on both; identical |
| hermetic suite | `pytest tests/ -q -p no:cacheprovider --deselect tests/test_ui.py --deselect tests/test_live_smoke.py` | `6348 passed, 26 skipped, 655 deselected, 5 xfailed in 330.23s` on `b5463d45` (`6265` on `73cc7d08` in the confirmation pass; `6228` at `159deef8` on `21132a25`; `6175` at `167ecb9b`, on `afa01bb8`) |
| hermetic suite, this spec's commit alone | the same, in the spec's worktree before any block | `6293 passed, 26 skipped, 655 deselected, 5 xfailed in 303.99s`; it carries none of the new tests, and its count includes `test_docs_citations.py`'s checks of this spec's anchored citations |
| browser suite | not run: no page, script or style of the application changes | — |
| the chart | `git diff --stat b5463d45 -- charts/` on the applied tree | empty: no render and no RBAC rule can change (T302-19) |
| with SPEC_E2 | E2's blocks as merged on main (`b5463d45`, SPEC_E2 at `1e4558ad`) then E3's, and E3's then E2's, each on an export of `b5463d45` | `21 blocks check out across 12 files` and `13 blocks check out across 9 files` in both orders; `diff -r` of the two trees: identical. On the E2-first tree the three new modules and E2's `tests/test_recovery_mode.py` and `tests/test_chart_recovery_mode.py` (56 tests) give `132 passed`, the TTL parity check included; E3's `recovery_left` equals E2's `remaining` on every record E2 writes (§2.13) |
| shell | `shellcheck` 0.11.0 on `restore-db.sh`; `bash -n` under macOS's `/bin/bash` 3.2.57 | clean; parses |
| Python 3.9 | `ast.parse(source, feature_version=(3, 9))` on the helper (inside the tests) | parses |
| markdown | `markdownlint-cli2` on the runbook, the CHANGELOG and `local-development/README.md`, and on the specs index | the same findings before and after (CHANGELOG MD012 ×1; runbook MD004 ×3, MD040 ×3), all on main already; the index: 0 |
| the reviews' drives | OB3's `test_ob3_drive.py` and `test_ob3_drive_wrapper.py` against the implemented copy | `7 passed, 1 failed`: the one matches the old lock message's words (`pid N, <ID>`; now `pid N, restore <ID>`); the behaviour it drives, a second restore refused and a third done, holds |

The cut, the mutation harness and the probes ran from this spec's scratch directory and are not committed; the probes
that decided the design are described in §2 well enough to repeat.

## 5. On the lab (the implementing pull request)

Not run in this phase: the lab is read-only here, and recovery mode (SPEC_E2) is not merged. This section is
development work on the lab, so it uses the lab's values file and `local-development/release-crc.sh` (with
`--values`), as every lab deploy does. The walk is recorded under `reports/<date>_restore-db-302/` with terminal
captures as PNG, and pinned to the merge sha on the issue.

1. **Before.** Record the UIDs of `group-sync-dashboard-data` and `group-sync-dashboard-report-artifacts` (on
   2026-10-01 `f065b7a4-535c-4ef1-868c-58f5afee4953` and `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`) and the five history
   counts (runbook §4c's query, with `kyverno_result_event` and `login_event` added).
2. **An upgrade to a walk-only schema 21.** Build a lab-only image of the branch with one no-op migration,
   `(21, "no-op for the #302 lab walk", ["SELECT 1"])`, deploy it, and read its log: `pre-upgrade copy written before
   migrating schema 20 -> 21: /data/pre-upgrade/pre-upgrade-<stamp>-schema-20-to-21-<pod>.db`. The image is never
   pushed to quay or set as the Application's image.
3. **Recovery mode under the previous image.** In the lab's values file set `image.tag: 2.0.0` (or the branch's real
   image, which understands 20), `recovery.enabled: true` and `recovery.ttl: 2h`, and roll it out. The pod reads
   `1/2 Running` and its log begins `RECOVERY MODE` (SPEC_E2).
4. **`--list`.** `local-development/restore-db.sh --list` shows the pre-upgrade copy as `20-<stamp>`, `pre-upgrade`,
   `ok`, `yes`; every backup the schema-21 image wrote as `no (21 > 20)`; and the move-aside note for the `-to-21-`
   copy.
5. **The refusals.** `--from-version` with a `21-…` backup's ID exits 3 naming 21 and 20 and the pre-upgrade copy's
   ID; a run with the release's values off (before step 3, or after step 8) exits 2 naming `recovery.enabled`.
6. **The restore.** `--from-version 20-<stamp>`; answer `y`. The output ends `check` with its confirmation line,
   says how much of the TTL is left as SPEC_E2 counts it, keeps the live set under
   `/data/pre-restore/<stamp>/`, prints `user_version 21 -> 20`, and `oc exec … -- ls -ln /data` shows `gsd.db` with
   gid 0 and mode `-rw-rw-r--`, no `gsd.db-wal`, no `gsd.db-shm`.
7. **Move the `-to-21-` copy aside, as runbook §6 says** (the walker does it; the script does not): with `oc exec … --
   python3.14 -c` and `os.replace`, move it and its `.sha256` into `/data/pre-restore/`. `ls /data/pre-upgrade` then
   shows no `-to-21-` copy (T302-20).
8. **Recovery off.** Set `recovery.enabled: false` in the values file and roll it out. The 2.0.0 dashboard starts
   and serves. Per history table, the rows with an id at or below the copy's highest equal the copy's count
   (`check`'s `in copy` column of step 6; counted so because the first poll adds rows at once). The UIDs of step 1
   are unchanged.
9. **No chart change.** `git diff --stat <merge base> -- charts/` is empty (T302-19).

## 6. What an operator sees, and what it costs

- **`--list`:** three header lines and one row per copy, in about 3 s on the lab (§2.10).
- **Outside recovery mode:** a refusal naming `recovery.enabled` and `recovery.ttl` and the values file, exit 2, and
  nothing run in the pod.
- **`--from-version`:** the plan (candidate, integrity, sidecar, schemas, loss window, the five tables and what else
  rolls back, the confirmation line), the question, then about ten seconds on the lab and the lines that say what was
  kept, removed and written, the `user_version` move and the way back. A refusal says which check failed and changes
  nothing; a copy or a live set that changed while the question was open is such a refusal.
- **Another `--list`, check or restore already running in the pod:** a refusal naming it, exit 2.
- **Disk:** each restore keeps the live set under `/data/pre-restore/<stamp>/` (on the lab about 20 MB with the
  `-wal`), on the data claim, and nothing prunes it: it is the way back from a wrong restore. The operator removes old
  ones by hand.
- **Cost:** no new object, permission, value or image content beyond a comment and a README row; two files in
  `local-development/`.
- **Code:** the table below, from `git diff --numstat` on the applied copy (§4.3).

| file | added | removed |
|---|---|---|
| `local-development/restore-db.py` (new) | 792 | 0 |
| `local-development/restore-db.sh` (new) | 104 | 0 |
| `local-development/gsd/store.py` | 4 | 0 |
| `docs/RUNBOOK_backup_restore.md` | 57 | 19 |
| `local-development/README.md` | 1 | 0 |
| `docs/CHANGELOG.md` | 18 | 0 |
| `local-development/tests/test_restore_db.py` (new) | 799 | 0 |
| `local-development/tests/test_restore_db_wrapper.py` (new) | 166 | 0 |
| `local-development/tests/test_restore_db_safety.py` (new) | 172 | 0 |
| total | 2113 | 19 |

The version fields `prepare-release.py` moves (Orchestrator's notes, 10) are not counted.

## 7. Implementation blocks

Applied in this order. Blocks 1 and 2 create the helper and the wrapper; block 3 is the comment in `store.py`; blocks
4 to 8 are the runbook (§4's pointer and undo, §4a's keep and removal and its sentence, §4b's keep and removal and its
S3 note); blocks 9 and 10 are the README row and the CHANGELOG; blocks 11 to 13 are the tests. After `--apply`,
`chmod +x local-development/restore-db.sh` (Orchestrator's notes, 13), then `prepare-release.py --app <next MINOR>
--no-commit "…"` (notes, 10).

### Block 1 — local-development/restore-db.py: the helper, streamed into the recovery pod

Standard library only (gsd.store and yaml imported in the pod only): `preflight` on the laptop; `list`, `check` and `restore` in the pod, one at a time under one lock (§3.1 to §3.10).

<!-- block: local-development/restore-db.py | create -->

```python
#!/usr/bin/env python3
"""The helper restore-db.sh runs (#302): list the database copies the recovery pod can restore, and restore one.

Not shipped in the image. restore-db.sh streams this file into the release's recovery pod (#303) over
`oc exec -i ... python3.14 /dev/stdin`, so it runs under whatever image that pod runs, the older one a rollback
targets included, and that image's own gsd.store says which schema it understands. Standard library only, apart
from gsd.store (KNOWN_SCHEMA_VERSION) and the yaml the image reads its configuration with, both imported in the
pod only. Every file operation happens here, in Python: the image has no cp, mv or sha256sum.

    preflight     on the laptop, from `oc get pods -o json` on stdin: the release's one pod, in recovery mode,
                  with at least MARGIN_SECONDS of its TTL left. Prints "<pod>\\t<image>\\t<time left>".
    list          in the pod: one row per restorable copy (backup, pre-upgrade, offsite) and its ID.
    check ID      in the pod: every check on one copy, what restoring it would discard, and a confirmation line
                  (the copy's sha256 and size, the live set's fingerprint). Writes nothing.
    restore ID    in the pod: the TTL left as SPEC_E2 counts it; the checks again, and with --expected-* the very
                  copy and live set the check showed; the copy written beside the live file under a temporary
                  name and checked there; the live set kept under pre-restore/<stamp>/; the old file made whole
                  and its -wal, -shm and -journal removed; the copy renamed onto it.

One helper operation runs in the pod at a time (list, check and restore all take the same lock).

Exit status: 0 done; 1 failed (the message says what was and was not changed); 2 refused because the pod is
not ready for a restore (not in recovery mode, uvicorn running, another operation running, too little TTL left);
3 refused because of the copy (an unknown ID, twins that differ, a schema newer than this image, a sidecar that
does not match, integrity_check, a copy or a live set other than the ones the check showed). Nothing is written before every
check has passed.

docs/specs/SPEC_E3_restore_db.md is the design; docs/RUNBOOK_backup_restore.md, section 4, the manual fallback.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import math
import os
import re
import shutil
import sqlite3
import sys
import time
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

#: Refuse a restore with less than this much of the recovery TTL left. At the TTL the recovery container exits
#: and ends every `oc exec` session in it, a restore's included. The whole restore of the lab's 14 MB database
#: is seconds under the lab's emulation; ten minutes covers a database about a hundred times larger (SPEC_E3 §2.11).
MARGIN_SECONDS = 600.0
#: The history tables a restore can lose rows from: the store's own Store._HISTORY_TABLES and login_event, which
#: it prunes on its own. Every id is AUTOINCREMENT, so an id above the copy's highest is a row inserted after the
#: copy was taken (tests/test_restore_db.py holds this list against the store's).
HISTORY = ("membership_event", "sync_event", "binding_event", "kyverno_result_event", "login_event")
#: One `sha256sum -c` line, parsed exactly as charts/group-sync-dashboard/scripts/offsite_backup.py parses it
#: (tests/test_restore_db.py holds the two equal).
SIDECAR_LINE = re.compile(r"([0-9A-Fa-f]{64})[ \t]+(.+?)\r?\n?")
SUM_SUFFIX = ".sha256"
#: Store._vacuum_into's gsd-<stamp>.db. Anything after the stamp is accepted, so a name that also carries a pod
#: still lists; the stamp is the copy's own, microseconds included, because two copies can share a second.
BACKUP_NAME = re.compile(r"gsd-(\d{8}T\d{6}\.\d{6}Z)(?:-[^/]+)?\.db")
#: _pre_upgrade_copy's pre-upgrade-<stamp>-schema-<from>-to-<to>-<pod>.db.
PRE_UPGRADE_NAME = re.compile(r"pre-upgrade-(\d{8}T\d{6}\.\d{6}Z)-schema-\d+-to-(\d+)-.+\.db")
#: The files SQLite keeps beside a database. A -wal or a hot -journal holds committed rows of the file it
#: belongs to, and one left beside another file is replayed into that file.
SIDE_FILES = ("-wal", "-shm", "-journal")
#: Where copies come from, in the order a byte-identical twin is read from.
SOURCES = ("backup", "pre-upgrade", "offsite")
#: SPEC_E2's record of this pod's TTL, in the pod's /tmp, and where the node's boot ID it is counted on is read.
RECOVERY_STATE = "gsd-recovery.json"
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
CHUNK = 1 << 20
MIB = 1048576
EXIT_FAILED, EXIT_POD, EXIT_COPY = 1, 2, 3
#: The Go duration grammar of the chart's gsd.durationSeconds helper, which recovery.ttl is written in.
_DURATION = re.compile("(?:[0-9]+(?:\\.[0-9]+)?(?:ns|us|µs|ms|s|m|h))+")
_TOKEN = re.compile("([0-9]+(?:\\.[0-9]+)?)(ns|us|µs|ms|s|m|h)")
_UNIT = {"ns": 1e-9, "us": 1e-6, "µs": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0}


class Refused(Exception):
    """A refusal or a failure the operator must read, with its exit status."""

    def __init__(self, code: int, message: str) -> None:
        super().__init__(message)
        self.code = code


def say(line: str = "", stream=None) -> None:
    """Print, and never let a closed stream stop the work. When the oc session drops, the process in the pod
    goes on (measured on the lab), and a failed print must not abort a restore between two of its steps."""
    try:
        print(line, file=stream or sys.stdout, flush=True)
    except OSError:
        pass


def ttl_seconds(text: str) -> float | None:
    """A Go duration as seconds (`2h`, `90m`, `1h30m`), or None when the text is not one."""
    if not _DURATION.fullmatch(text):
        return None
    return sum(float(number) * _UNIT[unit] for number, unit in _TOKEN.findall(text))


def span(seconds: float) -> str:
    """Whole seconds as a compact Go duration (`2h`, `1h30m`, `45s`)."""
    total = max(0, int(seconds))
    hours, rest = divmod(total, 3600)
    minutes, secs = divmod(rest, 60)
    return ((f"{hours}h" if hours else "") + (f"{minutes}m" if minutes else "") + (f"{secs}s" if secs else "")) or "0s"


def utc(epoch: float) -> str:
    return datetime.fromtimestamp(epoch, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def stamp_epoch(stamp: str) -> float:
    return datetime.strptime(stamp, "%Y%m%dT%H%M%S.%fZ").replace(tzinfo=timezone.utc).timestamp()


# ---------------------------------------------------------------------------------------------------------------
# preflight: on the laptop, from the pod spec alone (no exec)
# ---------------------------------------------------------------------------------------------------------------

def _values_hint(change: str) -> str:
    return (f"  Set {change} in this release's values file and roll it out through the release's deployment "
            "pipeline (docs/RUNBOOK_backup_restore.md, section 4). Not with oc set env: recovery mode is the chart's "
            "recovery.enabled, and a hand edit of the Deployment is not it.")


def preflight(doc: dict, release: str, namespace: str, now: float, margin: float = MARGIN_SECONDS) -> tuple[str, str, float]:
    """The release's one pod, its image, and how much of its recovery TTL is left at least; or a refusal.

    The TTL is counted from the pod's first container start and kept across container restarts (#303), so
    the deadline is bounded with the pod's status.startTime, which the kubelet sets before it pulls the image
    and therefore never after that first start: the time left printed is never more than the pod has."""
    pods = doc.get("items") or []
    names = [p["metadata"]["name"] for p in pods]
    if len(pods) != 1:
        raise Refused(EXIT_POD, f"{len(pods)} pods match app={release} in {namespace} ({', '.join(names) or 'none'}); "
                                "a restore needs exactly one, the release's recovery pod. Wait until one is left "
                                "(a terminating pod still counts), then run this again")
    pod, name = pods[0], names[0]
    spec = next((c for c in pod["spec"]["containers"] if c["name"] == "dashboard"), {})
    env = {e["name"]: e.get("value") for e in spec.get("env") or []}
    if env.get("GSD_RECOVERY_MODE") != "true":
        raise Refused(EXIT_POD, f"pod {name} is not in recovery mode: its dashboard container has no "
                                "GSD_RECOVERY_MODE=true, so the dashboard may be writing the database.\n"
                                + _values_hint("recovery.enabled: true and recovery.ttl: 2h"))
    status = pod.get("status") or {}
    state = next((s.get("state") or {} for s in status.get("containerStatuses") or [] if s["name"] == "dashboard"), {})
    longer = "a longer recovery.ttl (a new pod, with a new TTL)"
    if "running" not in state:
        raise Refused(EXIT_POD, f"pod {name}: the dashboard container is not running ({', '.join(state) or 'no status yet'}). "
                                "At the TTL recovery mode exits and the pod reads CrashLoopBackOff.\n"
                                + _values_hint(longer))
    ttl_text = env.get("GSD_RECOVERY_MODE_TTL") or ""
    ttl = ttl_seconds(ttl_text)
    started = status.get("startTime")
    if not ttl or not started:
        raise Refused(EXIT_POD, f"pod {name}: its recovery TTL ({ttl_text!r}) or its start time ({started!r}) cannot be "
                                "read, so the time left cannot be known")
    left = datetime.strptime(started, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc).timestamp() + ttl - now
    if left < margin:
        raise Refused(EXIT_POD, f"pod {name}: at most {span(left)} of recovery.ttl {ttl_text} is left, less than the "
                                f"{span(margin)} a restore keeps in hand: at the TTL the container exits and ends every "
                                "oc exec in it.\n" + _values_hint(longer))
    return name, spec.get("image") or "unknown", left


# ---------------------------------------------------------------------------------------------------------------
# in the pod
# ---------------------------------------------------------------------------------------------------------------

def in_recovery(proc: Path) -> None:
    """This container is the recovery pod's and nothing in it serves: GSD_RECOVERY_MODE (#303) and no uvicorn.
    Every process's argv is read, because PID 1 is not always the program: on the lab's arm64 node it is
    qemu-x86_64-static running python3.14."""
    if os.environ.get("GSD_RECOVERY_MODE") != "true":
        raise Refused(EXIT_POD, "GSD_RECOVERY_MODE is not true in this container, so it is not the recovery pod (#303)")
    if not proc.is_dir():
        raise Refused(EXIT_POD, f"{proc} cannot be read, so whether uvicorn runs here cannot be told")
    for cmdline in sorted(proc.glob("[0-9]*/cmdline")):
        try:
            argv = cmdline.read_bytes().split(b"\0")
        except OSError:
            continue                                # a process that ended while the list was read
        if any(arg == b"uvicorn" or arg.endswith(b"/uvicorn") for arg in argv):
            raise Refused(EXIT_POD, f"uvicorn is running here (pid {cmdline.parent.name}): the dashboard may be "
                                    "writing the database")


def known_schema() -> int:
    """The schema this pod's image understands: KNOWN_SCHEMA_VERSION (#305), or, in an image older than it,
    the same maximum read from _MIGRATIONS."""
    try:
        import gsd.store as store
    except ImportError as exc:
        raise Refused(EXIT_POD, f"gsd.store cannot be imported here ({exc}): this is not a dashboard image") from exc
    known = getattr(store, "KNOWN_SCHEMA_VERSION", None)
    return int(known if known is not None else max(migration[0] for migration in store._MIGRATIONS))


def config_backup_dir() -> str:
    """config.backup.dir as the app reads it (gsd/config.py): GSD_BACKUP_DIR, else backupDir in GSD_CONFIG."""
    if os.environ.get("GSD_BACKUP_DIR"):
        return os.environ["GSD_BACKUP_DIR"]
    path = Path(os.environ.get("GSD_CONFIG") or "/etc/gsd/clusters.yaml")
    if not path.is_file():
        return ""
    import yaml                                     # the image's: gsd reads its configuration with it
    raw = yaml.safe_load(path.read_text()) or {}
    return str(raw.get("backupDir") or "") if isinstance(raw, dict) else ""


class Layout:
    """Where the live database and every source of copies are, in this pod."""

    def __init__(self, offsite: Path) -> None:
        self.db = Path(os.environ.get("GSD_DB_PATH") or "/data/gsd.db")
        backup = config_backup_dir()
        self.backup = Path(backup) if backup else None
        self.pre_upgrade = self.db.parent / "pre-upgrade"
        self.pre_restore = self.db.parent / "pre-restore"
        self.offsite = offsite
        self.lock = Path(os.environ.get("TMPDIR") or "/tmp") / "gsd-restore.lock"
        self.state = Path(os.environ.get("TMPDIR") or "/tmp") / RECOVERY_STATE
        self.tmp = self.db.with_name(self.db.name + ".restore.tmp")

    def live_set(self) -> list[Path]:
        return [p for p in (self.db, *(Path(f"{self.db}{s}") for s in SIDE_FILES)) if p.is_file()]


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        while chunk := fh.read(CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def live_fingerprint(lay: Layout) -> str:
    """The live set's content: each of gsd.db, -wal and -journal that exists, by name, size and bytes. Not -shm,
    the index SQLite rewrites on any open, even a read-only one (§2.2)."""
    digest = hashlib.sha256()
    for path in lay.live_set():
        if path.name.endswith("-shm"):
            continue
        digest.update(f"{path.name}\0{path.stat().st_size}\0".encode())
        with path.open("rb") as fh:
            while chunk := fh.read(CHUNK):
                digest.update(chunk)
    return digest.hexdigest()


def sidecar_expected(sidecar: Path, name: str) -> str | None:
    """The digest a `sha256sum -c` sidecar records for `name`, or None when it is empty, unreadable, malformed
    or names another file: offsite_backup.py's sidecar_expected, line for line, apart from an unreadable file."""
    try:
        text = sidecar.read_text()
    except OSError:
        return None
    match = SIDECAR_LINE.fullmatch(text)
    if match is None or match.group(2) != name:
        return None
    return match.group(1).lower()


def schema_of(path: Path) -> int | None:
    """A copy's user_version, read from its header: the 4-byte big-endian integer at offset 60 that PRAGMA
    user_version reads and sets (sqlite.org/fileformat2.html). From the header, so a damaged copy still gets its
    ID and is refused by integrity_check by name; None when the file does not start with the SQLite header.
    Right for a copy only: no -wal belongs to a copy, while a live file's -wal may hold a newer page 1."""
    try:
        with path.open("rb") as fh:
            header = fh.read(64)
    except OSError:
        return None
    if len(header) < 64 or not header.startswith(b"SQLite format 3\x00"):
        return None
    return int.from_bytes(header[60:64], "big")


def integrity(path: Path) -> str:
    """'ok', or what PRAGMA integrity_check (or the open) said instead."""
    try:
        conn = sqlite3.connect(f"file:{path.as_posix()}?immutable=1&mode=ro", uri=True)
        try:
            return str(conn.execute("PRAGMA integrity_check").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.Error as exc:
        return f"cannot be checked: {exc}"


def history(conn: sqlite3.Connection) -> dict[str, tuple[int, int] | None]:
    """(rows, highest id) per history table; None for a table this database does not have."""
    out: dict[str, tuple[int, int] | None] = {}
    for table in HISTORY:
        try:
            count, highest = conn.execute(f"SELECT COUNT(*), COALESCE(MAX(id), 0) FROM {table}").fetchone()
            out[table] = (int(count), int(highest))
        except sqlite3.Error:
            out[table] = None
    return out


class Row:
    """One ID: one copy, or the same name under two sources (the offsite job keeps a backup's name)."""

    def __init__(self, rid: str, entries: list[tuple[str, Path]]) -> None:
        self.id = rid
        self.entries = sorted(entries, key=lambda e: (SOURCES.index(e[0]), str(e[1])))
        head, self.stamp = rid.split("-", 1)
        self.schema = None if head == "?" else int(head)
        self.path = self.entries[0][1]
        self._digests: dict[Path, str] = {}

    @property
    def sources(self) -> str:
        return "+".join(dict.fromkeys(source for source, _ in self.entries))

    def digest(self, path: Path) -> str:
        if path not in self._digests:
            self._digests[path] = sha256_of(path)
        return self._digests[path]

    def differ(self) -> bool:
        return len({self.digest(path) for _, path in self.entries}) > 1

    def sidecar(self) -> tuple[str, str]:
        """ok / mismatch / none, and why. Twins are byte-identical, so one matching sidecar verifies both."""
        verdicts = []
        for _, path in self.entries:
            side = path.with_name(path.name + SUM_SUFFIX)
            if not side.exists():
                continue
            expected = sidecar_expected(side, path.name)
            if expected is None:
                verdicts.append(("mismatch", f"{side} is empty, malformed or names another file"))
            elif expected != self.digest(path):
                verdicts.append(("mismatch", f"{path} has sha256 {self.digest(path)}; its sidecar says {expected}"))
            else:
                verdicts.append(("ok", f"{side} matches"))
        for word in ("mismatch", "ok"):
            for verdict in verdicts:
                if verdict[0] == word:
                    return verdict
        return "none", "no .sha256 beside it (scheduled backups write none), so integrity_check is its only check"


def catalogue(lay: Layout) -> dict[str, Row]:
    """Every restorable copy, by ID: <user_version>-<the copy's own stamp>. Copies are only ever read here."""
    found: dict[str, list[tuple[str, Path]]] = {}

    def scan(source: str, paths) -> None:
        for path in sorted(paths):
            match = BACKUP_NAME.fullmatch(path.name) or PRE_UPGRADE_NAME.fullmatch(path.name)
            if match and path.is_file():
                schema = schema_of(path)
                found.setdefault(f"{'?' if schema is None else schema}-{match.group(1)}", []).append((source, path))

    if lay.backup is not None and lay.backup.is_dir():
        scan("backup", lay.backup.glob("gsd-*.db"))
    if lay.pre_upgrade.is_dir():
        scan("pre-upgrade", lay.pre_upgrade.glob("pre-upgrade-*.db"))
    if lay.offsite.is_dir():
        scan("offsite", lay.offsite.rglob("*.db"))
    return {rid: Row(rid, entries) for rid, entries in found.items()}


def understood(schema: int | None, known: int) -> str:
    if schema is None:
        return "no (not a database)"
    if schema > known:
        return f"no ({schema} > {known})"
    return "yes" if schema == known else f"yes, migrates {schema} -> {known} on start"


def live_version(db: Path) -> int | None:
    """The live database's user_version, read through SQLite so a -wal is seen; it changes nothing but the
    -shm index SQLite rebuilds on any open (measured, SPEC_E3 §2.2)."""
    if not db.is_file():
        return None
    try:
        conn = sqlite3.connect(f"file:{db.as_posix()}?mode=ro", uri=True)
        try:
            return int(conn.execute("PRAGMA user_version").fetchone()[0])
        finally:
            conn.close()
    except sqlite3.Error:
        return None


def aside_notes(lay: Layout, known: int) -> list[str]:
    """Runbook §6: a pre-upgrade copy taken for a schema this image does not understand makes a retried upgrade
    take no copy of what this image writes from now on. Said, never done: this script moves nothing."""
    notes = []
    for path in sorted(lay.pre_upgrade.glob("pre-upgrade-*.db")) if lay.pre_upgrade.is_dir() else []:
        match = PRE_UPGRADE_NAME.fullmatch(path.name)
        if match and int(match.group(2)) > known:
            notes.append(f"note: {path} was taken before an upgrade to schema {match.group(2)}, which this image does "
                         f"not understand. Before that upgrade is tried again, move it and its {SUM_SUFFIX} out of "
                         f"{lay.pre_upgrade} (to {lay.pre_restore}/, for example), or the new attempt finds it and takes "
                         "no copy of what this image writes from now on (docs/RUNBOOK_backup_restore.md, section 6). "
                         "This script moves nothing.")
    return notes


def cmd_list(lay: Layout, known: int) -> int:
    rows = sorted(catalogue(lay).values(), key=lambda r: (r.stamp, r.id), reverse=True)
    live = live_version(lay.db)
    say(f"image    understands schema {known} and older")
    say(f"live     {lay.db} · " + ("absent" if not lay.db.is_file() else
                                   "unreadable" if live is None else f"user_version {live}"))
    say(f"{'ID':<28}{'SCHEMA':<8}{'STAMP (UTC)':<22}{'SIZE':>11}  {'SOURCE':<20}{'SIDECAR':<10}THIS IMAGE")
    notes = []
    for row in rows:
        size = row.path.stat().st_size / MIB
        sidecar = row.sidecar()[0]
        if row.differ():
            notes.append(f"# {row.id}: " + " and ".join(f"{p} (sha256 {row.digest(p)})" for _, p in row.entries)
                         + " differ; --from-version refuses this ID")
        schema = "?" if row.schema is None else str(row.schema)
        # SOURCE is 20 wide: "pre-upgrade+offsite", a pre-upgrade copy #304 has shipped, is 19.
        say(f"{row.id:<28}{schema:<8}{utc(stamp_epoch(row.stamp)):<22}{size:>7.2f} MiB  {row.sources:<20}"
            f"{sidecar:<10}{understood(row.schema, known)}")
    say(f"# {len(rows)} candidates. none: no .sha256 beside it (scheduled backups write none), so integrity_check is "
        "its only check. mismatch: --from-version refuses it.")
    if lay.backup is None:
        say("# backup: config.backup is off (no backupDir), so there are no scheduled backups to list")
    if not lay.offsite.is_dir():
        say(f"# offsite: {lay.offsite} is not mounted (recovery mode mounts the offsite claim only when backup.offsite "
            "uses its pvc destination)")
    for line in notes + aside_notes(lay, known):
        say(line)
    return 0


def checked(lay: Layout, rid: str, known: int) -> tuple[Row, str]:
    """The copy an ID names, and its sha256, once every check has passed; a refusal otherwise. Reads only."""
    rows = catalogue(lay)
    if rid not in rows:
        raise Refused(EXIT_COPY, f"no copy has the ID {rid}; run --list for the IDs")
    row = rows[rid]
    if row.differ():
        raise Refused(EXIT_COPY, f"{rid} names copies that differ: "
                                 + "; ".join(f"{p} (sha256 {row.digest(p)})" for _, p in row.entries)
                                 + ". Decide which one is right and restore it by hand (docs/RUNBOOK_backup_restore.md, "
                                 "section 4)")
    if row.schema is None:
        raise Refused(EXIT_COPY, f"{row.path} is not a database SQLite can open")
    if row.schema > known:
        better = sorted((r for r in rows.values() if r.schema is not None and r.schema <= known),
                        key=lambda r: r.stamp)
        hint = (f" The newest copy this image understands: --from-version {better[-1].id} (source {better[-1].sources})."
                if better else "")
        raise Refused(EXIT_COPY, f"{rid}: database schema {row.schema} is newer than this dashboard understands ({known}); "
                                 f"restore a copy at or below schema {known}, or run the image that understands "
                                 f"{row.schema}.{hint}")
    verdict, detail = row.sidecar()
    if verdict == "mismatch":
        raise Refused(EXIT_COPY, f"{rid}: {detail}")
    result = integrity(row.path)
    if result != "ok":
        raise Refused(EXIT_COPY, f"{rid}: {row.path}: integrity_check said {result!r}")
    return row, row.digest(row.path)


def cmd_check(lay: Layout, rid: str, known: int) -> int:
    row, digest = checked(lay, rid, known)
    now = time.time()
    copy = sqlite3.connect(f"file:{row.path.as_posix()}?immutable=1&mode=ro", uri=True)
    try:
        copied = history(copy)
    finally:
        copy.close()
    live_rows: dict[str, tuple[int, int] | None] = {table: None for table in HISTORY}
    live = live_version(lay.db)
    if live is not None:
        conn = sqlite3.connect(f"file:{lay.db.as_posix()}?mode=ro", uri=True)
        try:
            for table in HISTORY:
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    after = conn.execute(f"SELECT COUNT(*) FROM {table} WHERE id > ?",
                                         ((copied[table] or (0, 0))[1],)).fetchone()[0]
                    live_rows[table] = (int(count), int(after))
                except sqlite3.Error:
                    live_rows[table] = None
        finally:
            conn.close()
    live_word = "absent" if not lay.db.is_file() else "unreadable" if live is None else str(live)
    say(f"candidate    {row.path} · {row.path.stat().st_size / MIB:.2f} MiB · {row.sources}")
    say("integrity    ok  (PRAGMA integrity_check on the copy, opened immutable)")
    say(f"sidecar      {row.sidecar()[0]}: {row.sidecar()[1]}")
    say(f"schema       copy {row.schema} · live {live_word} · this image understands {known} and older")
    say(f"loss window  {utc(stamp_epoch(row.stamp))} -> {utc(now)} ({span(now - stamp_epoch(row.stamp))}): what the "
        "dashboard recorded since is discarded")
    say(f"             {'table':<22}{'live':>7}{'in copy':>10}{'discarded':>12}")
    for table in HISTORY:
        mine, theirs = live_rows[table], copied[table]
        say(f"             {table:<22}{'-' if mine is None else mine[0]:>7}{'-' if theirs is None else theirs[0]:>10}"
            f"{'-' if mine is None else mine[1]:>12}")
    say("             discarded is an estimate: the live rows with an id above the copy's highest. Not live minus "
        "copy (retention may have pruned rows the copy still has); after an earlier restore two branches of history "
        "can reuse ids, which no id count can tell apart.")
    say("             also rolled back, not counted: the current users, groups and bindings, the poll and login "
        "capture state, dashboard_user_activity, kpi_daily, report_run and the current Kyverno results. The first "
        "poll reads the clusters again; the activity, KPI and report records do not come back.")
    # restore-db.sh hands these to `restore`, which refuses a copy or a live set that changed in between.
    say(f"confirmation sha256={digest} size={row.path.stat().st_size} live-sha256={live_fingerprint(lay)}")
    for line in aside_notes(lay, known):
        say(line)
    return 0


@contextmanager
def operation_lock(lay: Layout, operation: str):
    """One helper operation in this pod at a time: a restore, and every --list or check, which open the live
    database read-only, a connection that must not be open while a restore folds and renames it. flock, so the
    kernel releases it when the process ends, however it ends: a restore whose oc session dropped holds it until it
    finishes, and a killed one leaves nothing held."""
    fd = os.open(lay.lock, os.O_RDWR | os.O_CREAT, 0o664)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            holder = os.read(fd, 512).decode(errors="replace").strip() or "its start was not recorded yet"
            raise Refused(EXIT_POD, f"another restore or database inspection is running in this pod ({holder}). One "
                                    "runs at a time; a restore whose oc session dropped goes on until it ends. Run this "
                                    "again after it has")
        os.ftruncate(fd, 0)
        os.write(fd, f"started {utc(time.time())}, pid {os.getpid()}, {operation}\n".encode())
        yield
    finally:
        os.close(fd)


def recovery_left(lay: Layout) -> float:
    """Seconds of the recovery TTL left, counted as SPEC_E2's own script counts them: its deadline on the node's
    monotonic clock minus the clock now, while the node's boot ID is the one it recorded; 0 when it is not (the node
    restarted under the pod); never more than the TTL. A record that cannot be read leaves the time unknown."""
    try:
        record = json.loads(lay.state.read_text())
        deadline, recorded = float(record["deadline_monotonic"]), str(record["boot_id"])
        ttl = ttl_seconds(str(record["ttl"]))
        if not math.isfinite(deadline):             # SPEC_E2's deadline() refuses the same record
            raise ValueError(f"deadline_monotonic {deadline} is not a finite number")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise Refused(EXIT_POD, f"the recovery TTL cannot be read from {lay.state} ({type(exc).__name__}: {exc}), so "
                                "how long this container has before it exits is unknown; nothing was written")
    try:
        boot = BOOT_ID.read_text().strip()
    except OSError:
        boot = ""                                   # not Linux: E2 records an empty boot ID there too
    if recorded != boot:
        return 0.0
    left = deadline - time.monotonic()
    return min(left, ttl) if ttl else left


def share(path: Path, group: int) -> None:
    """chgrp 0 and chmod g=u, OpenShift's arbitrary-UID rule: the next pod may run as another UID in group 0."""
    os.chown(path, -1, group)
    mode = path.stat().st_mode & 0o7777
    os.chmod(path, (mode & ~0o070) | ((mode & 0o700) >> 3))


def fsync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def copy_file(source: Path, target: Path) -> str:
    """Stream source to a new target, fsynced; the sha256 of the bytes written."""
    digest = hashlib.sha256()
    with source.open("rb") as reader, target.open("xb") as writer:
        while chunk := reader.read(CHUNK):
            writer.write(chunk)
            digest.update(chunk)
        writer.flush()
        os.fsync(writer.fileno())
    return digest.hexdigest()


def keep(lay: Layout, live_set: list[Path], group: int) -> Path:
    """The live set as found, under pre-restore/<stamp>/: written as <stamp>.tmp/ and renamed when complete."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    final, partial = lay.pre_restore / stamp, lay.pre_restore / f"{stamp}.tmp"
    if not lay.pre_restore.is_dir():
        lay.pre_restore.mkdir()
        share(lay.pre_restore, group)
    partial.mkdir()
    share(partial, group)
    for path in live_set:
        copy_file(path, partial / path.name)
        share(partial / path.name, group)
    fsync_directory(partial)
    os.replace(partial, final)
    fsync_directory(lay.pre_restore)
    return final


def write(lay: Layout, row: Row, digest: str, known: int, group: int) -> None:
    """The copy beside the live file under a temporary name (a rename needs one filesystem), checked again there:
    the bytes written are the ones checked, and the snapshot itself has the schema and the integrity the checks
    saw, so a copy replaced between its header read and its hash never takes the live name. Its group and mode
    are set before it does."""
    written = copy_file(row.path, lay.tmp)
    if written != digest:
        raise OSError(f"{lay.tmp} holds sha256 {written}, but the copy checked had {digest}: it changed while it was read")
    schema = schema_of(lay.tmp)
    if schema is None or schema != row.schema or schema > known:
        raise Refused(EXIT_COPY, f"the copy written for {row.id} reads schema {schema}, but the checks saw "
                                 f"{row.schema} and this image understands {known}: it changed while it was read. "
                                 "Nothing in the live set changed")
    result = integrity(lay.tmp)
    if result != "ok":
        raise Refused(EXIT_COPY, f"the copy written for {row.id} failed integrity_check ({result!r}). Nothing in the "
                                 "live set changed")
    share(lay.tmp, group)


def fold(lay: Layout) -> list[str]:
    """Make the old file whole, then remove what SQLite keeps beside it. Opening and closing it is SQLite's own
    way to fold a -wal into the file and remove it, and to roll back a hot -journal; neither reads the schema, so
    a file a newer image wrote folds too. SQLite does neither, silently, while another process has the file open
    or when it cannot write it (measured, SPEC_E3 §2.1): a -wal or -journal that still holds bytes after the
    close was not folded, and removing it would take committed rows out of the live file, so the restore stops
    here with nothing removed. A file SQLite cannot open as a database is removed around: the set was kept first.
    A damaged file whose -wal holds page 1 is not that file: SQLite opens it through the -wal, and its close cannot
    write the -wal back (an explicit checkpoint says `database disk image is malformed`, SPEC_E3 §2.1), so it stops
    here as a held file does, and the message names that cause too."""
    if lay.db.is_file():
        unreadable = False
        try:
            conn = sqlite3.connect(lay.db)
            try:
                conn.execute("PRAGMA user_version").fetchone()
            finally:
                conn.close()
        except sqlite3.OperationalError:
            pass                                    # locked, read-only, I/O: what is left beside it decides
        except sqlite3.DatabaseError:
            unreadable = True                       # not a database SQLite can open, or a corrupt one
        held = [side.name for side in (Path(f"{lay.db}-wal"), Path(f"{lay.db}-journal"))
                if side.is_file() and side.stat().st_size]
        if held and not unreadable:
            raise sqlite3.OperationalError(
                f"SQLite did not fold {' and '.join(held)} into {lay.db} when it closed it: another process has the "
                "database open (an oc exec session), the file cannot be written, or it is damaged so that SQLite cannot "
                "write the -wal back into it. Nothing beside it was removed. If nothing holds it and it can be written, "
                "it is damaged: restore over it by hand (docs/RUNBOOK_backup_restore.md, section 4a)")
    removed = []
    for suffix in SIDE_FILES:
        side = Path(f"{lay.db}{suffix}")
        if side.exists():
            side.unlink()
            removed.append(side.name)
    return removed


def cmd_restore(lay: Layout, rid: str, known: int, group: int, confirmed: tuple | None = None) -> int:
    with operation_lock(lay, f"restore {rid}"):
        left = recovery_left(lay)
        if left < MARGIN_SECONDS:
            raise Refused(EXIT_POD, f"{span(left)} of the recovery TTL is left in this pod, as SPEC_E2's script counts "
                                    f"it, less than the {span(MARGIN_SECONDS)} a restore keeps in hand: at the TTL the "
                                    "container exits and ends this session. Nothing was written.\n"
                                    + _values_hint("a longer recovery.ttl (a new pod, with a new TTL)"))
        row, digest = checked(lay, rid, known)
        if confirmed is not None:
            sha256, size, live_sha256 = confirmed
            if (digest, row.path.stat().st_size) != (sha256.lower(), size):
                raise Refused(EXIT_COPY, f"{rid} changed after the check you answered: it is now sha256 {digest}, "
                                         f"{row.path.stat().st_size} bytes; the check showed sha256 {sha256}, {size} "
                                         "bytes. Nothing was written; run this again to see the plan for it now")
            now = live_fingerprint(lay)
            if now != live_sha256.lower():
                raise Refused(EXIT_COPY, f"the live database set changed after the check you answered (live-sha256 "
                                         f"{now}, the check showed {live_sha256}), so what it said a restore discards "
                                         "no longer holds. Nothing was written; run this again to see the plan now")
        say(f"checked again  {rid}: schema {row.schema} (this image understands {known}), sidecar {row.sidecar()[0]}, "
            f"integrity_check ok; {span(left)} of the recovery TTL left")
        # No output from here to the swap: a closed stream must not stop the work between two steps.
        stage, kept, before, removed, live_set = "tidy", None, None, [], []
        try:
            # What a killed restore left: the temporary copy, and a keep that never finished. Neither is a copy.
            lay.tmp.unlink(missing_ok=True)
            for partial in lay.pre_restore.glob("*.tmp") if lay.pre_restore.is_dir() else []:
                shutil.rmtree(partial)
            live_set = lay.live_set()
            need = sum(p.stat().st_size for p in live_set) + row.path.stat().st_size
            free = shutil.disk_usage(lay.db.parent).free
            if free < need:
                raise Refused(EXIT_FAILED, f"free space {free / MIB:.1f} MiB on {lay.db.parent}, {need / MIB:.1f} MiB "
                                           "needed (the live set kept, and the copy written beside it); nothing was written")
            stage = "write"
            write(lay, row, digest, known, group)
            stage = "keep"
            kept = keep(lay, live_set, group) if live_set else None
            before = live_version(lay.db)
            stage = "fold"
            removed = fold(lay)
            stage = "swap"
            os.replace(lay.tmp, lay.db)
            stage = "sync"
            fsync_directory(lay.db.parent)
        except Refused:
            lay.tmp.unlink(missing_ok=True)
            raise
        except (OSError, sqlite3.Error) as exc:
            lay.tmp.unlink(missing_ok=True)
            state = {"tidy": "nothing in the live set changed",
                     "write": "nothing in the live set changed",
                     "keep": "nothing in the live set changed",
                     "fold": f"{lay.db} is the database it was, whole: its -wal folded into it, or still beside it",
                     "swap": f"{lay.db} is the database it was, whole, without its -wal",
                     "sync": f"{lay.db} is the copy, but the directory sync failed: check the volume"}[stage]
            message = f"the restore failed at the step {stage}: {exc}. {state}"
            raise Refused(EXIT_FAILED, message + (f"; the live set as found is kept under {kept}" if kept else "")) from exc
    after = schema_of(lay.db)
    say(f"kept         {kept}/  {', '.join(p.name for p in live_set)} (the live set, as found)" if kept else
        f"kept         nothing: there was no {lay.db}")
    say(f"removed      {', '.join(removed) or 'nothing'} (after opening and closing the old file, which folds its "
        "-wal into it)")
    say(f"written      {lay.db} <- {row.path} · sha256 {digest} · chgrp {group} · chmod g=u")
    say(f"user_version {'absent' if before is None else before} -> {after}")
    say("restored. Set recovery.enabled: false in this release's values file and roll it out through the release's "
        "deployment pipeline: the app starts on the restored file.")
    if kept:
        say(f"way back     {kept}/ is the database as it was; docs/RUNBOOK_backup_restore.md section 4, \"Undo a "
            "restore\", puts it back (fold it first: its rows may be only in its -wal)")
    for line in aside_notes(lay, known):
        say(line)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="restore-db.py", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    pre = sub.add_parser("preflight", help="on the laptop: the pod list on stdin")
    pre.add_argument("--release", required=True)
    pre.add_argument("--namespace", required=True)
    for name in ("list", "check", "restore"):
        command = sub.add_parser(name)
        if name != "list":
            command.add_argument("id", help="an ID as --list prints it: <user_version>-<the copy's stamp>")
        command.add_argument("--offsite", type=Path, default=Path("/offsite"),
                             help="where recovery mode mounts the offsite claim, read-only")
        command.add_argument("--proc", type=Path, default=Path("/proc"), help=argparse.SUPPRESS)
        command.add_argument("--group", type=int, default=0, help=argparse.SUPPRESS)
        if name == "restore":
            command.add_argument("--expected-sha256", help="the copy's sha256 on check's confirmation line")
            command.add_argument("--expected-size", type=int, help="the copy's size on that line")
            command.add_argument("--expected-live-sha256", help="the live set's fingerprint on that line")
    args = parser.parse_args(argv)
    try:
        if args.command == "preflight":
            try:
                doc = json.load(sys.stdin)
            except ValueError as exc:
                raise Refused(EXIT_POD, f"the pod list is not JSON ({exc}): did oc get pods fail?") from exc
            name, image, left = preflight(doc, args.release, args.namespace, time.time())
            say(f"{name}\t{image}\t{span(left)}")
            return 0
        in_recovery(args.proc)
        lay = Layout(args.offsite)
        known = known_schema()
        if args.command == "list":
            with operation_lock(lay, "list"):
                return cmd_list(lay, known)
        if args.command == "check":
            with operation_lock(lay, f"check {args.id}"):
                return cmd_check(lay, args.id, known)
        confirmed = (args.expected_sha256, args.expected_size, args.expected_live_sha256)
        if any(value is None for value in confirmed) and any(value is not None for value in confirmed):
            raise Refused(EXIT_COPY, "restore takes all three of --expected-sha256, --expected-size and "
                                     "--expected-live-sha256 (check's confirmation line), or none")
        return cmd_restore(lay, args.id, known, args.group, None if confirmed[0] is None else confirmed)
    except Refused as exc:
        say(("failed: " if exc.code == EXIT_FAILED else "refused: ") + str(exc), sys.stderr)
        return exc.code


if __name__ == "__main__":
    sys.exit(main())
```

### Block 2 — local-development/restore-db.sh: the wrapper, run from the laptop with oc

Finds the release's one pod, refuses outside recovery mode or with too little TTL left from the pod spec alone, streams the helper, asks between `check` and `restore`, and binds `restore` to check's confirmation line (§3.1, §3.2). The implementing pull request sets its executable bit (Orchestrator's notes, 13).

<!-- block: local-development/restore-db.sh | create -->

```bash
#!/usr/bin/env bash
# restore-db.sh — list the database copies the recovery pod can restore, and restore one (#302).
#
#   local-development/restore-db.sh --list
#   local-development/restore-db.sh --from-version <ID> [--yes]
#   options: --namespace <ns> (default group-sync-dashboard)
#            --release <name> (default group-sync-dashboard: the pods are found by app=<name>, as in the runbook)
#
# Runs on your laptop with oc, as you: nothing is added to any ServiceAccount; you need get on pods and
# create on pods/exec in the namespace. It refuses unless the release's one pod is in recovery mode (#303:
# recovery.enabled: true in the release's values file) with at least ten minutes of recovery.ttl left, then
# streams restore-db.py into that pod's dashboard container (oc exec -i ... python3.14 /dev/stdin): the work
# runs under the image the pod runs, the older one a rollback targets included, and nothing has to be shipped
# in it. --from-version shows what the restore discards and asks before it writes (--yes does not ask).
# docs/RUNBOOK_backup_restore.md, section 4, is the manual fallback; docs/specs/SPEC_E3_restore_db.md the design.
#
# Exit status: 0 done; 1 failed (the output says what changed); 2 refused, the pod is not ready for a
# restore; 3 refused, the copy; 4 not confirmed; 64 usage.
set -euo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
HELPER="${HERE}/restore-db.py"
NS=group-sync-dashboard
REL=group-sync-dashboard
MODE=""
ID=""
YES=0

usage() {
  sed -n '4,7p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --list)
      if [ -n "${MODE}" ]; then usage >&2; exit 64; fi          # one action per call
      MODE=list ;;
    --from-version|--namespace|--release)
      if [ "$#" -lt 2 ] || [ -z "$2" ]; then usage >&2; exit 64; fi
      case "$1" in
        --from-version)
          if [ -n "${MODE}" ]; then usage >&2; exit 64; fi
          MODE=restore; ID="$2" ;;
        --namespace) NS="$2" ;;
        --release) REL="$2" ;;
      esac
      shift ;;
    --yes) YES=1 ;;
    -h|--help) usage; exit 0 ;;
    *) usage >&2; exit 64 ;;
  esac
  shift
done
if [ -z "${MODE}" ]; then usage >&2; exit 64; fi

# The release's one pod, in recovery mode, with enough of its TTL left: read from the pod spec, no exec.
# Prints "<pod>\t<image>\t<time left>", or refuses (exit 2) with the reason and what to set.
preflight() {
  local pods
  pods=$(oc get pods -n "${NS}" -l "app=${REL}" -o json) || return
  printf '%s' "${pods}" | python3 "${HELPER}" preflight --release "${REL}" --namespace "${NS}"
}

# The helper, streamed into the pod's dashboard container: it runs under that pod's image.
in_pod() {
  oc exec -i -n "${NS}" "${POD}" -c dashboard -- python3.14 /dev/stdin "$@" < "${HELPER}"
}

FOUND=$(preflight) || exit $?
IFS=$'\t' read -r POD IMAGE LEFT <<< "${FOUND}"
printf 'pod      %s · recovery mode, at least %s of its TTL left\nimage    %s\n' "${POD}" "${LEFT}" "${IMAGE}"

if [ "${MODE}" = list ]; then
  in_pod list
  exit 0
fi

# The plan. Its confirmation line binds the restore below to the copy's bytes and to the live set the plan
# describes: `restore` refuses either if it changed while the question was open.
CHECKED=$(in_pod check "${ID}") || exit $?
printf '%s\n' "${CHECKED}"
CONFIRMED=$(printf '%s\n' "${CHECKED}" | sed -n 's/^confirmation sha256=\([0-9a-f]\{64\}\) size=\([0-9][0-9]*\) live-sha256=\([0-9a-f]\{64\}\)$/\1 \2 \3/p')
if [ -z "${CONFIRMED}" ] || [ "$(printf '%s\n' "${CONFIRMED}" | wc -l | tr -d ' ')" -ne 1 ]; then
  echo "failed: the check printed no single confirmation line; nothing changed" >&2
  exit 1
fi
read -r SHA256 SIZE LIVE_SHA256 <<< "${CONFIRMED}"
if [ "${YES}" -ne 1 ]; then
  printf 'Restore %s over the live database? [y/N] ' "${ID}"
  answer=""
  read -r answer || true
  case "${answer}" in
    y|Y|yes|YES) ;;
    *) echo "not restored: not confirmed; nothing changed" >&2; exit 4 ;;
  esac
fi

# The answer may have taken a while: the pod and its TTL again, just before the session that writes.
AGAIN=$(preflight) || exit $?
if [ "${AGAIN%%$'\t'*}" != "${POD}" ]; then
  echo "refused: the recovery pod changed from ${POD} to ${AGAIN%%$'\t'*} since the check; run this again" >&2
  exit 2
fi
in_pod restore "${ID}" --expected-sha256 "${SHA256}" --expected-size "${SIZE}" --expected-live-sha256 "${LIVE_SHA256}"
```

### Block 3 — local-development/gsd/store.py: migrations are one-way (T302-21)

A comment above `_MIGRATIONS` naming the pre-upgrade copy and this script as the way back. No code changes.

<!-- block: local-development/gsd/store.py | edit -->

Old text:

```python

_MIGRATIONS: list[tuple[int, str, list[str]]] = [
```

New text:

```python

# Migrations are ONE-WAY: nothing undoes one, and once one has run an image older than it refuses the database
# (#305). The way back is the copy taken before it ran, pre-upgrade/pre-upgrade-<stamp>-schema-<from>-to-<to>-<pod>.db
# beside the database (_pre_upgrade_copy, #301), restored under the older image with local-development/restore-db.sh
# in recovery mode (#302, #303), or by hand with docs/RUNBOOK_backup_restore.md section 4.
_MIGRATIONS: list[tuple[int, str, list[str]]] = [
```

### Block 4 — docs/RUNBOOK_backup_restore.md: §4 points at the script, and says how to undo a restore

Two paragraphs under the heading; the manual commands below them stay as the fallback (§3.11).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text

The dashboard is the only writer and must be **stopped** first: two processes on one SQLite
```

New text:

```text

**The script, in recovery mode (#302).** With the release's pod in recovery mode (#303: `recovery.enabled: true`
in the release's values file), run `local-development/restore-db.sh --list` from your laptop, then
`local-development/restore-db.sh --from-version <ID>` with an ID it printed. It does what §4a and §4b do by hand,
for a scheduled backup, a pre-upgrade copy (§6) or a copy on the offsite claim when recovery mode mounts it: it
refuses a copy newer than the image, a sidecar that does not match and a failed `integrity_check`; it shows what the
restore discards and asks; it keeps the live set (`gsd.db` with its `-wal` and `-shm`) under
`/data/pre-restore/<stamp>/`; and it writes the copy under a temporary name, with `chgrp 0` and `chmod g=u`,
before it renames it onto `gsd.db`. It refuses unless the release's one pod is in recovery mode with at least ten
minutes of `recovery.ttl` left. The commands below stay as the fallback, and as the specification the script
implements (`docs/specs/SPEC_E3_restore_db.md`).

**Undo a restore.** The live set the script replaced is kept under `/data/pre-restore/<stamp>/`, and it is the way
back; a directory whose name ends in `.tmp` is a keep that never finished, not a set. Stay in recovery mode. The
kept set's committed rows may sit only in its `gsd.db-wal`, so fold it before anything copies it: in the recovery pod,
`oc exec -n $NS <pod> -c dashboard -- python3.14 -c 'import sqlite3, sys; c = sqlite3.connect(sys.argv[1]); c.execute("PRAGMA user_version"); c.close()' /data/pre-restore/<stamp>/gsd.db`
leaves that `gsd.db` whole and alone: SQLite folds the `-wal` into it and removes it with the `-shm`, and rolls a hot
`-journal` back. If a `-wal` or `-journal` with bytes is still beside it afterwards, something else has it open or
it is damaged; do not go on. Then restore it with §4a's commands, the kept `gsd.db` in place of the `gsd-….db` copy:
they run `integrity_check` on it, keep the current live set first, write it beside `gsd.db` under a temporary name,
and remove the current `-wal`, `-shm` and `-journal` before it takes the name. A kept `gsd.db` copied without the
fold can lack every row its `-wal` held.

The dashboard is the only writer and must be **stopped** first: two processes on one SQLite
```

### Block 5 — docs/RUNBOOK_backup_restore.md: §4a keeps the live set, not `gsd.db` alone, and removes all of it

The fallback's keep step, corrected (T302-12's finding; §2.1), and its removal of every side file it keeps: a hot `-journal` left beside the copy is rolled back into it (measured, §2.3). The copy is written under a temporary name before anything is removed and renamed after: removed first and written after, a write that failed left `gsd.db` without its `-wal`'s rows, and "Undo a restore" runs these commands (note 20).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
import pathlib, time
live = pathlib.Path(\"/data/gsd.db\")
if live.is_file():
    keep = pathlib.Path(\"/data/pre-restore\"); keep.mkdir(parents=True, exist_ok=True)
    (keep / (\"gsd.db.\" + str(int(time.time())))).write_bytes(live.read_bytes())
    print(\"kept the live file under /data/pre-restore\")
"
rm -f /data/gsd.db-wal /data/gsd.db-shm
cat /data/backup/gsd-….db > /data/gsd.db
chgrp 0 /data/gsd.db && chmod g=u /data/gsd.db
ls -l /data
```

New text:

```text
import pathlib, time
keep = pathlib.Path(\"/data/pre-restore\") / time.strftime(\"%Y%m%dT%H%M%SZ\", time.gmtime())
for name in (\"gsd.db\", \"gsd.db-wal\", \"gsd.db-shm\", \"gsd.db-journal\"):
    live = pathlib.Path(\"/data\") / name
    if live.is_file():
        keep.mkdir(parents=True, exist_ok=True)
        (keep / name).write_bytes(live.read_bytes())
        print(\"kept\", live, \"under\", keep)
"
cat /data/backup/gsd-….db > /data/gsd.db.restore.tmp
chgrp 0 /data/gsd.db.restore.tmp && chmod g=u /data/gsd.db.restore.tmp
rm -f /data/gsd.db-wal /data/gsd.db-shm /data/gsd.db-journal
python3.14 -c "import os; os.replace(\"/data/gsd.db.restore.tmp\", \"/data/gsd.db\")"
ls -l /data
```

### Block 6 — docs/RUNBOOK_backup_restore.md: §4a says why the set is kept, and that all of it goes

One sentence before the side-file paragraph, which names the `-journal` too.

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text

`-wal`/`-shm` **must** go: they belong to the file that was there before, and SQLite would
replay a foreign WAL into the restored database. `chgrp 0` + `g=u` is the arbitrary-UID rule
OpenShift runs under: the next pod may get a different UID and reads through the root group
```

New text:

```text

The live **set** is kept, not `gsd.db` alone: a writer killed before a checkpoint leaves committed rows only in
`gsd.db-wal`, and a kept `gsd.db` without it counted 0 of 500 such rows where the kept set counted 500 (#302).
The copy is written under a temporary name and renamed onto `gsd.db` once the old side files are gone, so a write
that fails (a full volume, a `gsd.db` the pod cannot write) stops before anything is removed.
`-wal`, `-shm` and `-journal` **must** go: they belong to the file that was there before, and SQLite would
replay a foreign WAL, or roll a foreign hot journal back, into the restored database. `chgrp 0` + `g=u` is the arbitrary-UID rule
OpenShift runs under: the next pod may get a different UID and reads through the root group
```

### Block 7 — docs/RUNBOOK_backup_restore.md: §4b keeps the live set, writes the copy beside gsd.db, then removes and renames

The off-volume fallback kept nothing before `cat … > /data/gsd.db` and left a `-journal` beside the copy (the reviews of 2026-10-01; §3.11). The same keep as §4a, inside the pod's existing Python, and §4a's order: the copy written under a temporary name before the side files go, then renamed (note 20).

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
python3.14 /dev/stdin <<EOF
import hashlib, pathlib, sqlite3
p = pathlib.Path("/offsite/gsd-….db")
h = hashlib.sha256(p.read_bytes()).hexdigest()
assert h == p.with_name(p.name + ".sha256").read_text().split()[0], "sidecar mismatch"
c = sqlite3.connect(f"file:{p}?immutable=1", uri=True)
assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
print("copy verified", h)
EOF
rm -f /data/gsd.db-wal /data/gsd.db-shm
cat /offsite/gsd-….db > /data/gsd.db
chgrp 0 /data/gsd.db && chmod g=u /data/gsd.db
'
```

New text:

```text
python3.14 /dev/stdin <<EOF
import hashlib, pathlib, sqlite3, time
p = pathlib.Path("/offsite/gsd-….db")
h = hashlib.sha256(p.read_bytes()).hexdigest()
assert h == p.with_name(p.name + ".sha256").read_text().split()[0], "sidecar mismatch"
c = sqlite3.connect(f"file:{p}?immutable=1", uri=True)
assert c.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
print("copy verified", h)
keep = pathlib.Path("/data/pre-restore") / time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
for name in ("gsd.db", "gsd.db-wal", "gsd.db-shm", "gsd.db-journal"):
    live = pathlib.Path("/data") / name
    if live.is_file():
        keep.mkdir(parents=True, exist_ok=True)
        (keep / name).write_bytes(live.read_bytes())
        print("kept", live, "under", keep)
EOF
cat /offsite/gsd-….db > /data/gsd.db.restore.tmp
chgrp 0 /data/gsd.db.restore.tmp && chmod g=u /data/gsd.db.restore.tmp
rm -f /data/gsd.db-wal /data/gsd.db-shm /data/gsd.db-journal
python3.14 -c "import os; os.replace(\"/data/gsd.db.restore.tmp\", \"/data/gsd.db\")"
'
```

### Block 8 — docs/RUNBOOK_backup_restore.md: the S3 path keeps, writes under the temporary name, then removes and renames

A separate block because a bare fence line sits between §4b's command and this note. The same order as §4a and §4b.

<!-- block: docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text

For an S3 copy: download it (§3), then, in the helper pod, run the `rm -f /data/gsd.db-wal
/data/gsd.db-shm` line FIRST, stream the copy in —
`cat gsd-….db | oc exec -i -n $NS gsd-restore -- sh -c 'cat > /data/gsd.db'` — and finish with
the ownership lines. The order matters: a `-wal` that outlives the file it belonged to would be
replayed into the restored database.

```

New text:

```text

For an S3 copy: download it (§3), then, in the helper pod, run the keep lines above, stream the copy in under the
temporary name — `cat gsd-….db | oc exec -i -n $NS gsd-restore -- sh -c 'cat > /data/gsd.db.restore.tmp'` — and
finish with the last four lines above: the ownership lines, the `rm -f /data/gsd.db-wal
/data/gsd.db-shm /data/gsd.db-journal` line, and the rename. The order matters: the copy is whole beside `gsd.db`
before anything of the old file is removed, and a `-wal` that outlives the file it belonged to would be replayed
into the restored database.

```

### Block 9 — local-development/README.md: the tools table names the script

One row.

<!-- block: local-development/README.md | edit -->

Old text:

```text
| `prepare-release.py` | the four version fields, the Chart.yaml history line, the changelog heading, the branch and the commit, from `--app`/`--chart` and a reason; runs the version test first (`../docs/RELEASING.md`) |
| `clusters.example.yaml` | template for `clusters.yaml`, the local poller config |
```

New text:

```text
| `prepare-release.py` | the four version fields, the Chart.yaml history line, the changelog heading, the branch and the commit, from `--app`/`--chart` and a reason; runs the version test first (`../docs/RELEASING.md`) |
| `restore-db.sh` | list the database copies the recovery pod can restore, and restore one (#302); it streams `restore-db.py` into the pod. `../docs/RUNBOOK_backup_restore.md` section 4 |
| `clusters.example.yaml` | template for `clusters.yaml`, the local poller config |
```

### Block 10 — docs/CHANGELOG.md: the CHANGELOG entry

First under `## Unreleased` (§3.12).

<!-- block: docs/CHANGELOG.md | edit -->

Old text:

```text
## Unreleased

```

New text:

```text
## Unreleased

- **`restore-db.sh`: list the database copies the recovery pod can restore, and restore one (#302, Epic E #385,
  `docs/specs/SPEC_E3_restore_db.md`).** `local-development/restore-db.sh --list` runs from the laptop with `oc` and
  prints one row per copy (a scheduled backup, a pre-upgrade copy, a copy on the offsite claim): its ID
  (`<user_version>-<the copy's own stamp>`), schema, stamp, size, source, sidecar verdict and whether the pod's
  image understands it. `--from-version <ID>` refuses a copy newer than the image, a sidecar that does not match and
  a failed `integrity_check`; prints the loss window, an estimate of the rows of the five history tables inserted
  after the copy and the other state that rolls back; asks (`--yes` does not), and restores only the copy and the
  live set the question was about. It writes the copy under a temporary name and checks it there, keeps the live set
  under `/data/pre-restore/<stamp>/`, opens and closes the old file so SQLite folds its `-wal` in (and stops, removing
  nothing, when SQLite did not), removes `-wal`, `-shm` and `-journal`, and renames the copy onto `gsd.db` with
  `chgrp 0` and `chmod g=u`. It refuses unless the release's one pod is in recovery mode (#303) with ten minutes of
  `recovery.ttl` left, and while another `--list`, check or restore runs in the pod; it never deletes, moves or
  rotates a copy. The helper, `local-development/restore-db.py`, is streamed into the pod over `oc exec -i`, so it
  runs under the image a rollback targets; nothing is added to the image or to any ServiceAccount. The runbook's §4
  points at it, says how to undo a restore from the kept set, and keeps the manual paths as the fallback: §4a and
  §4b now keep the live set and remove its `-journal` as well. `_MIGRATIONS` says that migrations are one-way and
  names the way back.

```

### Block 11 — local-development/tests/test_restore_db.py: the helper's tests

T302-1 to T302-3, T302-5 (in the pod), T302-6 to T302-9, T302-10 (the plan), T302-12 to T302-16, T302-18, T302-21, and the tests the research and OB3's review added (§4.1).

<!-- block: local-development/tests/test_restore_db.py | create -->

```python
"""restore-db.py (#302), driven as the recovery pod runs it: `python /dev/stdin <command>` with the helper on stdin,
against a temporary /data, /offsite and /proc. docs/specs/SPEC_E3_restore_db.md §4 maps each test to its case."""
from __future__ import annotations

import ast
import fcntl
import hashlib
import importlib.util
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import pytest

from gsd.store import KNOWN_SCHEMA_VERSION as KNOWN

LOCAL_DEV = Path(__file__).resolve().parents[1]
HELPER = LOCAL_DEV / "restore-db.py"
OFFSITE_SCRIPT = LOCAL_DEV.parent / "charts" / "group-sync-dashboard" / "scripts" / "offsite_backup.py"
RECOVERY_SCRIPT = LOCAL_DEV.parent / "charts" / "group-sync-dashboard" / "scripts" / "recovery_mode.py"
TABLES = ("membership_event", "sync_event", "binding_event")
STAMPS = ("20261001T051103.798578Z", "20261001T111104.000930Z", "20260925T064601.385120Z", "20260930T180002.104233Z")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def make_db(path: Path, rows: int, version: int) -> None:
    """A database with the three history tables (ids AUTOINCREMENT, as in gsd/store.py's SCHEMA)."""
    conn = sqlite3.connect(path)
    for table in TABLES:
        conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)")
        conn.executemany(f"INSERT INTO {table}(v) VALUES (?)", [(str(i),) for i in range(rows)])
    conn.execute(f"PRAGMA user_version = {version}")
    conn.commit()
    conn.close()


def vacuum_copy(source: Path, target: Path) -> None:
    """A copy the way Store._vacuum_into and _pre_upgrade_copy take one."""
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(source)
    conn.execute(f"VACUUM INTO '{target}'")
    conn.close()


def sidecar(path: Path, digest: str | None = None) -> None:
    path.with_name(path.name + ".sha256").write_text(f"{digest or sha(path)}  {path.name}\n")


def kill_writer_after(db: Path, rows: int) -> None:
    """Commit `rows` sync_event rows into the -wal and die before any checkpoint, as a killed pod does."""
    code = ("import os, sqlite3, sys\n"
            "c = sqlite3.connect(sys.argv[1], isolation_level=None)\n"
            "c.execute('PRAGMA journal_mode=WAL'); c.execute('PRAGMA wal_autocheckpoint=0')\n"
            "c.execute('BEGIN')\n"
            f"[c.execute('INSERT INTO sync_event(v) VALUES (?)', ('wal',)) for _ in range({rows})]\n"
            "c.execute('COMMIT'); os.kill(os.getpid(), 9)\n")
    subprocess.run([sys.executable, "-c", code, str(db)], check=False)


def count(db: Path, table: str = "sync_event") -> int:
    """Rows as SQLite reads the file with whatever sits beside it, from a scratch copy so nothing here folds it."""
    scratch = Path(tempfile.mkdtemp())
    for side in ("", "-wal", "-shm", "-journal"):
        if Path(f"{db}{side}").exists():
            shutil.copy2(f"{db}{side}", scratch / f"gsd.db{side}")
    conn = sqlite3.connect(scratch / "gsd.db")
    try:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    finally:
        conn.close()
        shutil.rmtree(scratch)


class Pod:
    """A temporary recovery pod: /data, /offsite, /proc and $TMPDIR, and the helper run as `oc exec` runs it."""

    def __init__(self, root: Path, uvicorn: bool = False) -> None:
        self.root = root
        self.data, self.offsite, self.proc, self.tmp = (root / n for n in ("data", "offsite", "proc", "tmp"))
        self.backup, self.pre_upgrade, self.pre_restore = (self.data / n for n in ("backup", "pre-upgrade", "pre-restore"))
        for d in (self.backup, self.pre_upgrade, self.offsite, self.proc / "1", self.tmp):
            d.mkdir(parents=True)
        argv = (["/usr/bin/qemu-x86_64-static", "/usr/sbin/python3.14", "-m", "uvicorn", "gsd.api:create_app"] if uvicorn
                else ["python3.14", "/scripts/recovery_mode.py", "--release", "group-sync-dashboard"])
        (self.proc / "1" / "cmdline").write_bytes(b"\0".join(a.encode() for a in argv) + b"\0")
        self.db = self.data / "gsd.db"
        self.ttl_left(7200.0)

    def ttl_left(self, seconds: float, boot: str | None = None) -> None:
        """SPEC_E2's record of the TTL in the pod's /tmp, `seconds` from now on the node's monotonic clock."""
        if boot is None:
            boot_file = Path("/proc/sys/kernel/random/boot_id")
            boot = boot_file.read_text().strip() if boot_file.exists() else ""
        now, mono = time.time(), time.monotonic()
        record = {"ttl": "2h", "started": "", "started_epoch": now, "deadline": "", "deadline_epoch": now + seconds,
                  "deadline_monotonic": mono + seconds, "boot_id": boot}
        (self.tmp / "gsd-recovery.json").write_text(json.dumps(record))

    def run(self, *args: str, env: dict | None = None) -> subprocess.CompletedProcess:
        environment = {**os.environ, "PYTHONPATH": str(LOCAL_DEV), "GSD_RECOVERY_MODE": "true",
                       "GSD_DB_PATH": str(self.db), "GSD_BACKUP_DIR": str(self.backup), "TMPDIR": str(self.tmp),
                       **(env or {})}
        with HELPER.open("rb") as source:
            return subprocess.run([sys.executable, "/dev/stdin", *args, "--offsite", str(self.offsite),
                                   "--proc", str(self.proc), "--group", str(os.getgid())],
                                  stdin=source, capture_output=True, text=True, env=environment, timeout=120)


@pytest.fixture
def pod(tmp_path: Path) -> Pod:
    """Live: 40 rows a table at KNOWN, then 500 sync_event rows only in its -wal. Copies: two backups at KNOWN
    (taken before the -wal rows), a pre-upgrade copy at KNOWN - 1 with its sidecar, an offsite copy with its."""
    p = Pod(tmp_path)
    make_db(p.db, 40, KNOWN)
    vacuum_copy(p.db, p.backup / f"gsd-{STAMPS[0]}.db")
    vacuum_copy(p.db, p.backup / f"gsd-{STAMPS[1]}.db")
    older = tmp_path / "older.db"
    make_db(older, 30, KNOWN - 1)
    pre = p.pre_upgrade / f"pre-upgrade-{STAMPS[2]}-schema-{KNOWN - 1}-to-{KNOWN}-group-sync-dashboard-abc12-xyz34.db"
    vacuum_copy(older, pre)
    sidecar(pre)
    off = p.offsite / f"gsd-{STAMPS[3]}.db"
    vacuum_copy(p.db, off)
    sidecar(off)
    kill_writer_after(p.db, 500)
    return p


def ids(result: subprocess.CompletedProcess) -> list[str]:
    return re.findall(r"^(\S+-\d{8}T\d{6}\.\d{6}Z)\s", result.stdout, re.M)


def row(result: subprocess.CompletedProcess, rid: str) -> str:
    return next(line for line in result.stdout.splitlines() if line.startswith(rid + " "))


def tree(*dirs: Path) -> dict[str, tuple[int, str, int]]:
    return {str(p): (p.stat().st_size, sha(p), p.stat().st_mtime_ns)
            for d in dirs for p in sorted(d.rglob("*")) if p.is_file()}


def test_t302_1_list_shows_every_copy_with_its_id_schema_source_sidecar_and_verdict(pod: Pod) -> None:
    result = pod.run("list")
    assert result.returncode == 0, result.stderr
    assert sorted(ids(result)) == sorted([f"{KNOWN}-{STAMPS[0]}", f"{KNOWN}-{STAMPS[1]}", f"{KNOWN - 1}-{STAMPS[2]}",
                                         f"{KNOWN}-{STAMPS[3]}"])
    assert re.search(rf"^{KNOWN}-{STAMPS[0]}\s+{KNOWN}\s+2026-10-01T05:11:03Z\s+[\d.]+ MiB\s+backup\s+none\s+yes$",
                     result.stdout, re.M), result.stdout
    assert re.search(rf"\s+pre-upgrade\s+ok\s+yes, migrates {KNOWN - 1} -> {KNOWN} on start$",
                     row(result, f"{KNOWN - 1}-{STAMPS[2]}"))
    assert re.search(r"\s+offsite\s+ok\s+yes$", row(result, f"{KNOWN}-{STAMPS[3]}"))
    assert f"live     {pod.db} · user_version {KNOWN}" in result.stdout
    assert f"image    understands schema {KNOWN} and older" in result.stdout


def test_t302_2_a_byte_identical_offsite_twin_is_one_row_and_a_differing_one_is_refused(pod: Pod) -> None:
    twin = pod.offsite / f"gsd-{STAMPS[0]}.db"
    shutil.copy2(pod.backup / twin.name, twin)
    sidecar(twin)
    result = pod.run("list")
    assert ids(result).count(f"{KNOWN}-{STAMPS[0]}") == 1 and len(ids(result)) == len(set(ids(result)))
    assert re.search(r"\s+backup\+offsite\s+ok\s+yes$", row(result, f"{KNOWN}-{STAMPS[0]}"))

    other = pod.root / "other.db"
    make_db(other, 7, KNOWN)
    twin.unlink()
    vacuum_copy(other, twin)
    result = pod.run("list")
    assert ids(result).count(f"{KNOWN}-{STAMPS[0]}") == 1
    assert f"# {KNOWN}-{STAMPS[0]}: " in result.stdout and "differ; --from-version refuses this ID" in result.stdout
    before = tree(pod.data)
    refused = pod.run("restore", f"{KNOWN}-{STAMPS[0]}")
    assert refused.returncode == 3
    assert str(pod.backup / twin.name) in refused.stderr and str(twin) in refused.stderr
    assert sha(pod.backup / twin.name) in refused.stderr and sha(twin) in refused.stderr
    assert tree(pod.data) == before


def test_t302_3_a_copy_newer_than_this_image_is_listed_as_not_understood(pod: Pod) -> None:
    newer = pod.root / "newer.db"
    make_db(newer, 5, KNOWN + 1)
    vacuum_copy(newer, pod.backup / "gsd-20261003T150002.513647Z.db")
    result = pod.run("list")
    assert row(result, f"{KNOWN + 1}-20261003T150002.513647Z").endswith(f"no ({KNOWN + 1} > {KNOWN})")


def test_t302_5_a_uvicorn_process_or_a_missing_env_is_refused_in_the_pod(tmp_path: Path) -> None:
    serving = Pod(tmp_path / "a", uvicorn=True)
    make_db(serving.db, 3, KNOWN)
    before = tree(serving.data)
    result = serving.run("restore", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 2 and "uvicorn is running here (pid 1)" in result.stderr
    assert tree(serving.data) == before
    plain = Pod(tmp_path / "b")
    result = plain.run("list", env={"GSD_RECOVERY_MODE": ""})
    assert result.returncode == 2 and "GSD_RECOVERY_MODE is not true" in result.stderr


def test_t302_6_an_unknown_id_is_refused_and_nothing_is_touched(pod: Pod) -> None:
    before = tree(pod.data)
    result = pod.run("restore", f"{KNOWN}-20200101T000000.000000Z")
    assert result.returncode == 3 and "no copy has the ID" in result.stderr
    assert tree(pod.data) == before


def test_t302_7_a_copy_newer_than_this_image_is_refused_with_both_numbers(pod: Pod) -> None:
    newer = pod.root / "newer.db"
    make_db(newer, 5, KNOWN + 1)
    vacuum_copy(newer, pod.backup / "gsd-20261003T150002.513647Z.db")
    before = tree(pod.data)
    result = pod.run("restore", f"{KNOWN + 1}-20261003T150002.513647Z")
    assert result.returncode == 3
    assert f"database schema {KNOWN + 1} is newer than this dashboard understands ({KNOWN})" in result.stderr
    assert f"--from-version {KNOWN}-{STAMPS[1]}" in result.stderr          # the newest copy it does understand
    assert tree(pod.data) == before


def test_t302_8_a_truncated_copy_is_refused_by_integrity_check(pod: Pod) -> None:
    big = pod.root / "big.db"
    make_db(big, 5000, KNOWN)
    bad = pod.backup / "gsd-20261001T171103.000001Z.db"
    vacuum_copy(big, bad)
    bad.write_bytes(bad.read_bytes()[: bad.stat().st_size // 2])
    garbage = pod.backup / "gsd-20261001T171104.000002Z.db"
    garbage.write_bytes(b"not a database " * 300)
    listed = pod.run("list")
    assert row(listed, "?-20261001T171104.000002Z").endswith("no (not a database)")
    before = tree(pod.data)
    result = pod.run("restore", f"{KNOWN}-20261001T171103.000001Z")
    assert result.returncode == 3 and "integrity_check said" in result.stderr, result.stderr
    result = pod.run("restore", "?-20261001T171104.000002Z")
    assert result.returncode == 3 and "is not a database SQLite can open" in result.stderr, result.stderr
    assert tree(pod.data) == before


def test_t302_9_a_sidecar_naming_another_digest_is_refused_with_both(pod: Pod) -> None:
    pre = next(pod.pre_upgrade.glob("pre-upgrade-*.db"))
    sidecar(pre, "0" * 64)
    before = tree(pod.data)
    result = pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}")
    assert result.returncode == 3 and sha(pre) in result.stderr and "0" * 64 in result.stderr
    assert tree(pod.data) == before


def test_t302_10_check_prints_the_loss_window_and_the_rows_inserted_after_the_copy(pod: Pod) -> None:
    # Retention pruned 25 of the rows the copy still has; the copy's highest id is 40.
    conn = sqlite3.connect(pod.db)
    conn.execute("DELETE FROM membership_event WHERE id <= 25")
    conn.commit()
    conn.close()
    files = [n for n in ("gsd.db", "gsd.db-wal") if (pod.data / n).exists()]
    before = {n: sha(pod.data / n) for n in files}
    result = pod.run("check", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 0, result.stderr
    assert "loss window  2026-10-01T05:11:03Z -> " in result.stdout
    assert re.search(r"membership_event\s+15\s+40\s+0$", result.stdout, re.M), result.stdout
    assert re.search(r"sync_event\s+540\s+40\s+500$", result.stdout, re.M)
    assert re.search(r"binding_event\s+40\s+40\s+0$", result.stdout, re.M)
    # check writes nothing: the database and its -wal are byte-identical (-shm is the index SQLite rebuilds on any open)
    assert {n: sha(pod.data / n) for n in files} == before
    assert not pod.pre_restore.exists()


def test_t302_12_the_live_set_is_kept_whole_with_its_wal(pod: Pod) -> None:
    assert count(pod.db) == 540                                    # 40, and 500 committed only to the -wal
    result = pod.run("restore", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 0, result.stderr
    (kept,) = [d for d in pod.pre_restore.iterdir() if d.is_dir()]
    assert {"gsd.db", "gsd.db-wal"} <= {p.name for p in kept.iterdir()}
    assert count(kept / "gsd.db") == 540


def test_t302_14_the_copy_replaces_the_database_with_no_journal_and_the_group_set(pod: Pod) -> None:
    pre = next(pod.pre_upgrade.glob("pre-upgrade-*.db"))
    result = pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}")
    assert result.returncode == 0, result.stderr
    assert sha(pod.db) == sha(pre)
    assert sorted(p.name for p in pod.data.iterdir() if p.is_file()) == ["gsd.db"]
    mode = pod.db.stat().st_mode
    assert pod.db.stat().st_gid == os.getgid() and (mode & 0o070) == (mode & 0o700) >> 3    # chgrp, chmod g=u
    assert f"user_version {KNOWN} -> {KNOWN - 1}" in result.stdout


def test_t302_15_the_sources_are_only_read(pod: Pod) -> None:
    before = tree(pod.backup, pod.pre_upgrade, pod.offsite)
    assert pod.run("list").returncode == 0
    assert pod.run("restore", f"{KNOWN}-{STAMPS[3]}").returncode == 0
    after = tree(pod.backup, pod.pre_upgrade, pod.offsite)
    assert {k: v[:2] for k, v in after.items()} == {k: v[:2] for k, v in before.items()}


def test_t302_16_a_second_restore_is_refused_while_one_runs(pod: Pod) -> None:
    lock = pod.tmp / "gsd-restore.lock"
    with lock.open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        fh.write("started 2026-10-01T09:48:17Z, pid 4242, 20-x\n")
        fh.flush()
        before = tree(pod.data)
        result = pod.run("restore", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 2 and "started 2026-10-01T09:48:17Z" in result.stderr
    assert tree(pod.data) == before
    assert pod.run("restore", f"{KNOWN}-{STAMPS[0]}").returncode == 0     # released with its holder


def test_t302_18_a_copy_for_a_schema_this_image_lacks_gets_the_move_aside_note(pod: Pod) -> None:
    stuck = pod.pre_upgrade / f"pre-upgrade-20261003T090002.208311Z-schema-{KNOWN}-to-{KNOWN + 1}-pod-new.db"
    vacuum_copy(pod.backup / f"gsd-{STAMPS[1]}.db", stuck)
    sidecar(stuck)
    result = pod.run("restore", f"{KNOWN}-20261003T090002.208311Z")
    assert result.returncode == 0, result.stderr
    assert f"note: {stuck} was taken before an upgrade to schema {KNOWN + 1}" in result.stdout
    assert "This script moves nothing." in result.stdout and stuck.exists()


def test_t302_21_migrations_say_they_are_one_way_and_name_the_way_back() -> None:
    source = (LOCAL_DEV / "gsd" / "store.py").read_text()
    above = source.split("\n_MIGRATIONS: list[", 1)[0].rsplit("\n\n", 1)[-1]
    assert "ONE-WAY" in above and "pre-upgrade" in above and "restore-db.sh" in above


# --- T302-13: a kill after each step, as SIGKILL leaves it (no cleanup runs) -------------------------------------

DRIVER = r'''
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("restore_db", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
step, when = sys.argv[2], sys.argv[3]       # when: before/after (the rename), or the call to kill after
if step == "rename":                       # the rename onto gsd.db: killed just before it, or just after it
    real = os.replace
    def rename(src, dst):
        if str(dst).endswith("gsd.db"):
            if when == "after":
                real(src, dst)
            os._exit(9)
        return real(src, dst)
    os.replace = rename
else:                                      # killed as soon as that call to the step returns
    real, calls = getattr(m, step), []
    def killed(*args, **kwargs):
        result = real(*args, **kwargs)
        calls.append(1)
        if len(calls) == (1 if when == "after" else int(when)):
            os._exit(9)
        return result
    setattr(m, step, killed)
sys.exit(m.main(sys.argv[4:]))
'''


def _driven(pod: Pod, *argv: str) -> subprocess.CompletedProcess:
    """The helper in a process of its own, with one of its steps replaced as DRIVER-like code says."""
    env = {**os.environ, "PYTHONPATH": str(LOCAL_DEV), "GSD_RECOVERY_MODE": "true", "GSD_DB_PATH": str(pod.db),
           "GSD_BACKUP_DIR": str(pod.backup), "TMPDIR": str(pod.tmp)}
    return subprocess.run([sys.executable, "-c", *argv[:1], str(HELPER), *argv[1:], "--offsite", str(pod.offsite),
                           "--proc", str(pod.proc), "--group", str(os.getgid())],
                          env=env, capture_output=True, text=True, timeout=120)


@pytest.mark.parametrize("step, when", [("write", "after"), ("copy_file", "2"), ("keep", "after"),
                                        ("fold", "after"), ("rename", "before"), ("rename", "after")],
                         ids=["after-write", "mid-keep", "after-keep", "after-fold", "before-rename", "after-rename"])
def test_t302_13_a_kill_after_any_step_leaves_the_old_database_or_the_new_one(pod: Pod, step: str, when: str) -> None:
    rid = f"{KNOWN - 1}-{STAMPS[2]}"
    copy = next(pod.pre_upgrade.glob("pre-upgrade-*.db"))
    killed = _driven(pod, DRIVER, step, when, "restore", rid)
    assert killed.returncode == 9, killed.stderr
    side = [n for n in ("gsd.db-wal", "gsd.db-journal") if (pod.data / n).exists()]
    if sha(pod.db) == sha(copy):
        assert not side, "the restored file sits beside a journal it did not write"
    else:
        assert count(pod.db) == 540                                  # the old database, whole
    for kept in [d for d in pod.pre_restore.glob("*") if d.is_dir() and not d.name.endswith(".tmp")]:
        assert count(kept / "gsd.db") == 540                         # a finished keep is the whole live set
    rerun = pod.run("restore", rid)                                  # and the next run finishes the job
    assert rerun.returncode == 0, rerun.stderr
    assert sha(pod.db) == sha(copy) and not list(pod.data.glob("*.tmp")) and not list(pod.pre_restore.glob("*.tmp"))


FAILING_RENAME = r'''
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("restore_db", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
real = os.replace
def rename(src, dst):
    if str(dst).endswith("gsd.db"):
        raise OSError(28, "No space left on device")
    return real(src, dst)
os.replace = rename
sys.exit(m.main(sys.argv[2:]))
'''


def test_a_failed_rename_names_the_state_and_leaves_the_old_database_whole(pod: Pod) -> None:
    result = _driven(pod, FAILING_RENAME, "restore", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 1
    assert "the restore failed at the step swap" in result.stderr and "whole, without its -wal" in result.stderr
    assert count(pod.db) == 540 and not (pod.data / "gsd.db-wal").exists()
    assert not (pod.data / "gsd.db.restore.tmp").exists()


CHANGED_SOURCE = r'''
import importlib.util, os, sys
spec = importlib.util.spec_from_file_location("restore_db", sys.argv[1])
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
real = m.copy_file
def copy_file(source, target):
    if str(target).endswith(".restore.tmp"):                 # the copy changed after it was checked
        source = next(m.Path(os.environ["GSD_BACKUP_DIR"]).glob("gsd-*.db"))
    return real(source, target)
m.copy_file = copy_file
sys.exit(m.main(sys.argv[2:]))
'''


def test_a_copy_that_changed_after_its_check_is_not_swapped_in(pod: Pod) -> None:
    before = sha(pod.db)
    result = _driven(pod, CHANGED_SOURCE, "restore", f"{KNOWN - 1}-{STAMPS[2]}")
    assert result.returncode == 1 and "the restore failed at the step write" in result.stderr, result.stderr
    assert "it changed while it was read" in result.stderr and sha(pod.db) == before
    assert not (pod.data / "gsd.db.restore.tmp").exists() and count(pod.db) == 540


# --- added by the research and the design ---------------------------------------------------------------------

SIDECARS = [
    ("{d}  {n}\n", True), ("{d}  {n}", True), ("{d}\t{n}\r\n", True), ("{D}  {n}\n", True),
    ("{d}\n{n}\n", False), ("{d}  other.db\n", False), ("", False), ("{d}  {n}\n{d}  {n}\n", False),
    ("not-a-digest  {n}\n", False), ("{d}  {n} \n", False),
]


@pytest.mark.parametrize("text, valid", SIDECARS, ids=[f"case{i}" for i in range(len(SIDECARS))])
def test_the_sidecar_parser_is_the_offsite_scripts(tmp_path: Path, text: str, valid: bool) -> None:
    helper, offsite = _load(HELPER, "restore_db"), _load(OFFSITE_SCRIPT, "offsite_backup")
    assert helper.SIDECAR_LINE.pattern == offsite.SIDECAR_LINE.pattern
    name, digest = "gsd-20261001T051103.798578Z.db", "ab" * 32
    side = tmp_path / (name + ".sha256")
    side.write_text(text.format(d=digest, D=digest.upper(), n=name), newline="")
    assert helper.sidecar_expected(side, name) == offsite.sidecar_expected(side, name)
    assert (helper.sidecar_expected(side, name) == digest) is valid


def _pods(env: dict, *, start: str, running: bool = True, count: int = 1, image: str = "q/gsd:2.0.0") -> dict:
    pod = {"metadata": {"name": "group-sync-dashboard-6c5d8f7b9d-q2x7m"},
           "spec": {"containers": [{"name": "dashboard", "image": image,
                                    "env": [{"name": k, "value": v} for k, v in env.items()]},
                                   {"name": "oauth-proxy", "image": "proxy"}]},
           "status": {"startTime": start,
                      "containerStatuses": [{"name": "dashboard", "state": {"running": {}} if running else
                                             {"waiting": {"reason": "CrashLoopBackOff"}}}]}}
    return {"items": [pod] * count}


def test_preflight_bounds_the_ttl_by_the_pods_start_not_the_containers_restart() -> None:
    helper = _load(HELPER, "restore_db")
    now = 1_790_000_000.0
    start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 3600))
    env = {"GSD_RECOVERY_MODE": "true", "GSD_RECOVERY_MODE_TTL": "2h"}
    name, image, left = helper.preflight(_pods(env, start=start), "r", "n", now)
    assert (name, image, left) == ("group-sync-dashboard-6c5d8f7b9d-q2x7m", "q/gsd:2.0.0", 3600)
    with pytest.raises(helper.Refused) as late:
        helper.preflight(_pods({**env, "GSD_RECOVERY_MODE_TTL": "1h5m"}, start=start), "r", "n", now)
    assert late.value.code == 2 and "at most 5m of recovery.ttl 1h5m is left" in str(late.value)
    with pytest.raises(helper.Refused, match="not running"):
        helper.preflight(_pods(env, start=start, running=False), "r", "n", now)


def test_the_go_durations_recovery_ttl_takes() -> None:
    helper = _load(HELPER, "restore_db")
    assert [helper.ttl_seconds(t) for t in ("2h", "90m", "1h30m", "1.5h", "abc", "7200", "0s")] == \
        [7200.0, 5400.0, 5400.0, 5400.0, None, None, 0.0]
    assert [helper.span(s) for s in (7200, 5400, 45, 0, -3)] == ["2h", "1h30m", "45s", "0s", "0s"]
    if RECOVERY_SCRIPT.is_file():                                   # #303's script, once it is on the branch
        recovery = _load(RECOVERY_SCRIPT, "recovery_mode")
        for text in ("2h", "90m", "1h30m", "1.5h", "500ms", "abc", "7200", "-5m", "0s"):
            assert helper.ttl_seconds(text) == recovery.ttl_seconds(text), text


def test_an_image_older_than_known_schema_version_reads_it_from_the_migrations(tmp_path: Path) -> None:
    package = tmp_path / "old" / "gsd"
    package.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    (package / "store.py").write_text("_MIGRATIONS = [(1, 'a', []), (17, 'b', []), (9, 'c', [])]\n")
    p = Pod(tmp_path / "pod")
    make_db(p.db, 1, 17)
    result = p.run("list", env={"PYTHONPATH": str(tmp_path / "old")})
    assert result.returncode == 0, result.stderr
    assert "image    understands schema 17 and older" in result.stdout


def test_the_backup_directory_is_read_from_the_config_when_the_env_does_not_set_it(pod: Pod) -> None:
    config = pod.root / "clusters.yaml"
    config.write_text(f'backupDir: "{pod.backup}"\nbackupKeep: 4\n')
    result = pod.run("list", env={"GSD_BACKUP_DIR": "", "GSD_CONFIG": str(config)})
    assert f"{KNOWN}-{STAMPS[0]}" in ids(result)
    off = pod.run("list", env={"GSD_BACKUP_DIR": "", "GSD_CONFIG": str(pod.root / "absent.yaml")})
    assert f"{KNOWN}-{STAMPS[0]}" not in ids(off) and "# backup: config.backup is off" in off.stdout


def test_the_fold_removes_the_wal_only_after_sqlite_has_written_it_back(pod: Pod, monkeypatch) -> None:
    """wal.html §4: open and close is the safe way to remove a -wal. After it the old file alone holds the
    500 rows, so a kill between the removal and the rename loses nothing (T302-13 after-fold)."""
    helper = _load(HELPER, "restore_db")
    monkeypatch.setenv("GSD_DB_PATH", str(pod.db))
    monkeypatch.setenv("GSD_BACKUP_DIR", str(pod.backup))
    removed = helper.fold(helper.Layout(pod.offsite))
    assert not (pod.data / "gsd.db-wal").exists() and not (pod.data / "gsd.db-shm").exists()
    assert removed == [] and count(pod.db) == 540


def test_the_helper_parses_on_the_oldest_python_it_meets() -> None:
    """The laptop's python3 runs preflight; the pod's python3.14 runs the rest."""
    ast.parse(HELPER.read_text(), feature_version=(3, 9))


def test_the_wrapper_is_executable() -> None:
    assert os.access(LOCAL_DEV / "restore-db.sh", os.X_OK)


# --- added by the review (2026-10-01) ------------------------------------------------------------------------------

HOLDER = r'''
import sqlite3, sys, time
c = sqlite3.connect(f"file:{sys.argv[1]}?mode=ro", uri=True)
c.execute("PRAGMA user_version").fetchone()
print("ready", flush=True)
time.sleep(60)
'''


def test_the_fold_removes_nothing_sqlite_did_not_fold(pod: Pod) -> None:
    """Another process with the live file open (a --list or check in a second session): SQLite's close then folds
    nothing and says nothing. The restore must stop at the fold with the old database whole, not remove the -wal
    and leave /data/gsd.db without its 500 rows (§3.6; measured in §2.1)."""
    holder = subprocess.Popen([sys.executable, "-c", HOLDER, str(pod.db)], stdout=subprocess.PIPE, text=True)
    try:
        assert holder.stdout.readline().strip() == "ready"
        result = pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}")
    finally:
        holder.kill()
        holder.wait()
    assert result.returncode == 1, result.stderr
    assert "the restore failed at the step fold" in result.stderr and "SQLite did not fold gsd.db-wal" in result.stderr
    assert (pod.data / "gsd.db-wal").exists() and count(pod.db) == 540
    assert not (pod.data / "gsd.db.restore.tmp").exists()


def test_the_fold_folds_a_database_a_newer_image_wrote(pod: Pod, monkeypatch) -> None:
    """The rollback case: the newer image's last transaction put rows and a schema entry this SQLite cannot parse
    into the -wal. Opening and closing reads no schema, so the fold still writes the -wal back (§2.1)."""
    code = ("import os, sqlite3, sys\n"
            "c = sqlite3.connect(sys.argv[1], isolation_level=None)\n"
            "c.execute('PRAGMA wal_autocheckpoint=0'); c.execute('PRAGMA writable_schema=ON'); c.execute('BEGIN')\n"
            "[c.execute('INSERT INTO sync_event(v) VALUES (?)', ('newer',)) for _ in range(100)]\n"
            "c.execute(\"INSERT INTO sqlite_schema(type, name, tbl_name, rootpage, sql) VALUES "
            "('table', 'future', 'future', 0, 'CREATE TABLE future(a FUTURE_SYNTAX(')\")\n"
            "c.execute('COMMIT'); os.kill(os.getpid(), 9)\n")
    subprocess.run([sys.executable, "-c", code, str(pod.db)], check=False)
    helper = _load(HELPER, "restore_db")
    monkeypatch.setenv("GSD_DB_PATH", str(pod.db))
    monkeypatch.setenv("GSD_BACKUP_DIR", str(pod.backup))
    assert helper.fold(helper.Layout(pod.offsite)) == [] and not (pod.data / "gsd.db-wal").exists()
    conn = sqlite3.connect(pod.db)
    conn.execute("PRAGMA writable_schema=ON")
    try:
        assert conn.execute("SELECT COUNT(*) FROM sync_event").fetchone()[0] == 640
    finally:
        conn.close()


def test_a_live_file_that_is_not_a_database_is_replaced_around(pod: Pod) -> None:
    """A live gsd.db SQLite cannot open at all is no reason to refuse: the set was kept first (fold's docstring).
    SQLite cannot open it when nothing beside it holds page 1: here its -wal holds rows rewritten in place only, so
    the open raises DatabaseError, which the fold takes as "not a database" (a fold that let it through refuses).
    Over a -wal that holds page 1, SQLite opens such a file through the -wal instead (the next test)."""
    code = ("import os, sqlite3, sys\n"
            "c = sqlite3.connect(sys.argv[1], isolation_level=None)\n"
            "c.execute('PRAGMA wal_checkpoint(TRUNCATE)'); c.execute('PRAGMA wal_autocheckpoint=0'); c.execute('BEGIN')\n"
            "c.execute(\"UPDATE sync_event SET v = 'Z' || substr(v, 2) WHERE id <= 40\")\n"
            "c.execute('COMMIT'); os.kill(os.getpid(), 9)\n")
    subprocess.run([sys.executable, "-c", code, str(pod.db)], check=False)
    assert (pod.data / "gsd.db-wal").stat().st_size                # bytes no file but the lost one can take
    pod.db.write_bytes(b"not a database " * 1000)
    result = pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}")
    assert result.returncode == 0, result.stderr
    assert sha(pod.db) == sha(next(pod.pre_upgrade.glob("pre-upgrade-*.db")))
    assert sorted(p.name for p in pod.data.iterdir() if p.is_file()) == ["gsd.db"]


def test_a_damaged_live_file_whose_wal_holds_page_1_stops_at_the_fold_and_says_so(tmp_path: Path) -> None:
    """A gsd.db cut short beside the -wal its writer left, page 1 among its frames: SQLite opens it through the -wal
    and raises nothing, and its close cannot write the -wal back (an explicit checkpoint says `database disk image is
    malformed`). The fold stops with nothing removed, and its message names damage and the manual path, not only a
    session or a permission (review of the spec, 2026-10-01; SPEC_E3 §2.1)."""
    p = Pod(tmp_path)
    make_db(p.db, 40, KNOWN)
    conn = sqlite3.connect(p.db)
    conn.execute("CREATE TABLE pad (v BLOB)")
    conn.executemany("INSERT INTO pad VALUES (?)", [(os.urandom(4000),) for _ in range(400)])
    conn.commit()
    conn.close()
    older = tmp_path / "older.db"
    make_db(older, 30, KNOWN - 1)
    vacuum_copy(older, p.pre_upgrade / f"pre-upgrade-{STAMPS[2]}-schema-{KNOWN - 1}-to-{KNOWN}-pod-a.db")
    kill_writer_after(p.db, 500)
    p.db.write_bytes(p.db.read_bytes()[: p.db.stat().st_size // 2])
    wal = (p.data / "gsd.db-wal").read_bytes()
    result = p.run("restore", f"{KNOWN - 1}-{STAMPS[2]}")
    assert result.returncode == 1 and "the restore failed at the step fold" in result.stderr, result.stderr
    assert "damaged" in result.stderr and "section 4a" in result.stderr, result.stderr
    assert (p.data / "gsd.db-wal").read_bytes() == wal and not (p.data / "gsd.db.restore.tmp").exists()


def test_check_counts_every_history_table_the_store_keeps(tmp_path: Path) -> None:
    """The store keeps five AUTOINCREMENT event tables (Store._HISTORY_TABLES, and login_event, pruned on its own);
    a restore discards the rows added to each after the copy, so `check` counts each."""
    from gsd import store
    helper = _load(HELPER, "restore_db")
    assert set(store.Store._HISTORY_TABLES) | {"login_event"} <= set(helper.HISTORY)
    p = Pod(tmp_path)
    conn = sqlite3.connect(p.db)
    conn.executescript(store.SCHEMA)
    conn.execute(f"PRAGMA user_version = {KNOWN}")
    conn.commit()
    conn.close()
    vacuum_copy(p.db, p.backup / f"gsd-{STAMPS[0]}.db")
    conn = sqlite3.connect(p.db)
    conn.executemany("INSERT INTO login_event(cluster_id, pod_name, user_name, outcome, at, observed_at) "
                     "VALUES ('c', 'n', ?, 'success', '2026-10-01T12:00:00Z', '2026-10-01T12:00:01Z')",
                     [(f"u{i}",) for i in range(7)])
    conn.executemany("INSERT INTO kyverno_result_event(cluster_id, policy_kind, policy, resource_kind, resource_name, "
                     "change, result, observed_at) VALUES ('c', 'ValidatingPolicy', 'p', 'Pod', ?, 'appeared', 'fail', "
                     "'2026-10-01T12:00:00Z')", [(f"r{i}",) for i in range(3)])
    conn.commit()
    conn.close()
    result = p.run("check", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 0, result.stderr
    assert re.search(r"login_event\s+7\s+0\s+7$", result.stdout, re.M), result.stdout
    assert re.search(r"kyverno_result_event\s+3\s+0\s+3$", result.stdout, re.M), result.stdout


def confirmation(result: subprocess.CompletedProcess) -> tuple[str, str, str]:
    (line,) = re.findall(r"^confirmation sha256=([0-9a-f]{64}) size=(\d+) live-sha256=([0-9a-f]{64})$", result.stdout, re.M)
    return line


def test_restore_refuses_a_copy_or_a_live_set_other_than_the_ones_check_showed(pod: Pod) -> None:
    """restore-db.sh asks between two sessions: `check` prints the copy's sha256 and size and the live set's
    fingerprint, and `restore` refuses either changed before anything is written (review of the spec, F1/F4)."""
    rid = f"{KNOWN - 1}-{STAMPS[2]}"
    copy = next(pod.pre_upgrade.glob("pre-upgrade-*.db"))
    digest, size, live = confirmation(pod.run("check", rid))
    assert (digest, int(size)) == (sha(copy), copy.stat().st_size)
    before = tree(pod.data)
    for wrong in (("0" * 64, size, live), (digest, str(int(size) + 1), live), (digest, size, "0" * 64)):
        refused = pod.run("restore", rid, "--expected-sha256", wrong[0], "--expected-size", wrong[1],
                          "--expected-live-sha256", wrong[2])
        assert refused.returncode == 3 and "after the check you answered" in refused.stderr, refused.stderr
    partial = pod.run("restore", rid, "--expected-sha256", digest)
    assert partial.returncode == 3 and "all three" in partial.stderr
    assert tree(pod.data) == before
    assert pod.run("restore", rid, "--expected-sha256", digest, "--expected-size", size,
                   "--expected-live-sha256", live).returncode == 0


def test_the_live_fingerprint_ignores_the_shm_a_reader_rewrites(pod: Pod) -> None:
    """Any open between `check` and `restore`, a --list among them, may rewrite the -shm index (§2.2): not a change."""
    rid = f"{KNOWN - 1}-{STAMPS[2]}"
    digest, size, live = confirmation(pod.run("check", rid))
    shm = Path(f"{pod.db}-shm")
    before = shm.read_bytes()
    shm.write_bytes(b"\0" * len(before))
    assert shm.read_bytes() != before
    assert pod.run("restore", rid, "--expected-sha256", digest, "--expected-size", size,
                   "--expected-live-sha256", live).returncode == 0


@pytest.mark.parametrize("left, boot", [(300.0, None), (7200.0, "a-boot-that-is-not-this-one"), (None, None),
                                        (float("nan"), None)],
                         ids=["too-little-left", "the-node-restarted", "no-record", "not-a-finite-number"])
def test_the_restore_reads_the_ttl_left_as_recovery_mode_counts_it(pod: Pod, left, boot) -> None:
    """SPEC_E2's own answer, read in the pod as the restore starts: deadline_monotonic minus the clock, 0 on another
    boot, unknown without the record; each refuses with exit 2 and writes nothing (review of the spec, E2 rework)."""
    if left is None:
        (pod.tmp / "gsd-recovery.json").unlink()
    else:
        pod.ttl_left(left, boot)
    before = tree(pod.data)
    result = pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}")
    assert result.returncode == 2, result.stderr
    assert ("cannot be read" if left is None or left != left else "of the recovery TTL is left in this pod") in result.stderr
    assert tree(pod.data) == before and not pod.pre_restore.exists()


def test_list_keeps_a_long_source_apart_from_its_sidecar(pod: Pod) -> None:
    """A pre-upgrade copy #304 has shipped offsite lists as `pre-upgrade+offsite`, 19 characters."""
    pre = next(pod.pre_upgrade.glob("pre-upgrade-*.db"))
    (pod.offsite / pre.name).write_bytes(pre.read_bytes())
    result = pod.run("list")
    assert re.search(rf"\s+pre-upgrade\+offsite\s+ok\s+yes, migrates {KNOWN - 1} -> {KNOWN} on start$",
                     row(result, f"{KNOWN - 1}-{STAMPS[2]}")), result.stdout


def test_the_runbooks_undo_folds_the_kept_set_into_one_whole_file(pod: Pod) -> None:
    """The way back is the kept set; its gsd.db copied alone counts 40 of 540. Runbook §4's "Undo a restore" folds
    it first: run as the runbook prints it, the kept gsd.db alone holds all 540."""
    assert pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}").returncode == 0
    (kept,) = [d for d in pod.pre_restore.iterdir() if d.is_dir()]
    runbook = (LOCAL_DEV.parent / "docs" / "RUNBOOK_backup_restore.md").read_text()
    match = re.search(r"python3\.14 -c '([^']+)' /data/pre-restore/<stamp>/gsd\.db", runbook)
    assert match, "runbook §4 has no command that folds the kept set"
    subprocess.run([sys.executable, "-c", match.group(1), str(kept / "gsd.db")], check=True)
    alone = pod.root / "alone"
    alone.mkdir()
    shutil.copy2(kept / "gsd.db", alone / "gsd.db")
    assert count(alone / "gsd.db") == 540 and not (kept / "gsd.db-wal").exists()


def test_the_runbooks_undo_leaves_the_old_database_whole_when_gsd_db_cannot_be_written(pod: Pod) -> None:
    """Runbook §4's "Undo a restore", run as printed after a restore that stopped at the fold (a gsd.db the pod
    cannot write): §4a's commands keep the live set and remove its -wal, so the copy they put in its place must
    already sit beside gsd.db under a temporary name. Removed first and written after, gsd.db read 40 of 540 rows
    when the write was refused (the blocks of 159deef8; review of the spec, 2026-10-01)."""
    if os.geteuid() == 0:
        pytest.skip("root writes a 0444 file")
    pod.db.chmod(0o444)
    stopped = pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}")
    assert stopped.returncode == 1 and "the restore failed at the step fold" in stopped.stderr, stopped.stderr
    (kept,) = [d for d in pod.pre_restore.iterdir() if d.is_dir()]
    runbook = (LOCAL_DEV.parent / "docs" / "RUNBOOK_backup_restore.md").read_text()
    fold = re.search(r"python3\.14 -c '([^']+)' /data/pre-restore/<stamp>/gsd\.db", runbook).group(1)
    subprocess.run([sys.executable, "-c", fold, str(kept / "gsd.db")], check=True)
    lines = runbook.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("oc debug -n $NS deploy/$REL -c dashboard -- sh -c '"))
    body = "\n".join(lines[start + 1:lines.index("'", start + 1)])
    script = (body.replace("/data/backup/gsd-….db", f"/data/pre-restore/{kept.name}/gsd.db").replace("/data", str(pod.data))
              .replace("python3.14", sys.executable).replace("chgrp 0 ", f"chgrp {os.getgid()} "))
    subprocess.run(["sh", "-c", script], capture_output=True, text=True, check=False)
    assert count(pod.db) == 540                                      # the old database whole, put back from the keep


def test_no_refusal_offers_a_way_but_the_values_file(pod: Pod) -> None:
    """The operator's rule as SPEC_E2 applies it (its notes 5 and 16): every message a program prints names the
    release's values file as the way to extend or leave recovery mode, and a pod's deletion is not offered as one.
    The three TTL refusals: the container not running, too little left by the pod spec, and as SPEC_E2 counts it."""
    helper = _load(HELPER, "restore_db")
    now = 1_790_000_000.0
    env = {"GSD_RECOVERY_MODE": "true", "GSD_RECOVERY_MODE_TTL": "2h"}
    start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now - 7000))
    said = []
    for doc in (_pods(env, start=start), _pods(env, start=start, running=False)):
        with pytest.raises(helper.Refused) as refused:
            helper.preflight(doc, "r", "n", now)
        said.append(str(refused.value))
    pod.ttl_left(100.0)
    said.append(pod.run("restore", f"{KNOWN - 1}-{STAMPS[2]}").stderr)
    for text in said:
        assert "values file" in text and "oc delete" not in text, text


def test_no_manual_path_writes_the_copy_onto_gsd_db_before_its_journals_go() -> None:
    """Runbook §4a, §4b and the S3 note write the copy beside gsd.db under a temporary name and rename it after the
    old side files are removed, so a write that fails (a full volume, a gsd.db the pod cannot write) stops before
    anything is removed (confirmation pass of the spec, F1: removed first and written after, gsd.db read 40 of 540)."""
    runbook = (LOCAL_DEV.parent / "docs" / "RUNBOOK_backup_restore.md").read_text()
    section = runbook.split("\n## 4.", 1)[1].split("\n## 5.", 1)[0]
    assert not re.search(r"> /data/gsd\.db['\s]", section), "a manual path writes the copy onto /data/gsd.db itself"
    assert section.count("> /data/gsd.db.restore.tmp") == 3            # §4a, §4b and the S3 note


def test_the_runbook_removes_every_journal_it_keeps() -> None:
    """Runbook §4's manual paths keep the live set, -journal included, and must remove all three side files before
    a copy takes the name: a hot -journal left beside it is rolled back into the copy (howtocorrupt §1.4)."""
    runbook = (LOCAL_DEV.parent / "docs" / "RUNBOOK_backup_restore.md").read_text()
    section = runbook.split("\n## 4.", 1)[1].split("\n## 5.", 1)[0]
    removes = re.findall(r"rm -f /data/gsd\.db-wal\s+/data/gsd\.db-shm[^\n`]*", section)
    assert len(removes) == 3 and all("/data/gsd.db-journal" in line for line in removes), removes
    assert section.count("for name in (") == 2                       # §4a and §4b keep the set first
```

### Block 12 — local-development/tests/test_restore_db_wrapper.py: the wrapper's tests

T302-4, T302-5 (the pod count and uvicorn), T302-10 (the answer), T302-11, T302-17, with `oc` stubbed on PATH, and the binding of `restore` to check's confirmation line (§4.1).

<!-- block: local-development/tests/test_restore_db_wrapper.py | create -->

```python
"""restore-db.sh (#302), driven end to end with `oc` stubbed on PATH, as tests/test_release_crc.py drives its
script. The stub answers `oc get pods` from a file and runs `oc exec ... python3.14 /dev/stdin <args>` here, with
the streamed helper on stdin, against a temporary pod (tests/test_restore_db.py's). docs/specs/SPEC_E3_restore_db.md
§4 maps each test to its case."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from gsd.store import KNOWN_SCHEMA_VERSION as KNOWN
from test_restore_db import STAMPS, Pod, count, kill_writer_after, make_db, sidecar, vacuum_copy

LOCAL_DEV = Path(__file__).resolve().parents[1]
WRAPPER = LOCAL_DEV / "restore-db.sh"

STUB = r'''#!/usr/bin/env bash
# Every call is logged as one line. `oc get pods` answers from STUB_PODS; `oc exec` runs the streamed helper here.
printf '%s\n' "$*" >> "$STUB_LOG"
case "$1" in
  get) cat "$STUB_PODS" ;;
  exec)
    while [ "$#" -gt 0 ] && [ "$1" != /dev/stdin ]; do shift; done
    shift
    exec "$STUB_PYTHON" /dev/stdin "$@" --offsite "$STUB_OFFSITE" --proc "$STUB_PROC" --group "$STUB_GROUP" ;;
esac
'''


def pods(pod_env: dict, *, started_ago: float = 600, n: int = 1) -> dict:
    start = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - started_ago))
    item = {"metadata": {"name": "group-sync-dashboard-6c5d8f7b9d-q2x7m"},
            "spec": {"containers": [{"name": "dashboard", "image": "quay.io/ephico2real/group-sync-dashboard:2.0.0",
                                     "env": [{"name": k, "value": v} for k, v in pod_env.items()]}]},
            "status": {"startTime": start, "containerStatuses": [{"name": "dashboard", "state": {"running": {}}}]}}
    return {"items": [item] * n}


RECOVERY = {"GSD_DB_PATH": "/data/gsd.db", "GSD_RECOVERY_MODE": "true", "GSD_RECOVERY_MODE_TTL": "2h"}


@pytest.fixture
def lab(tmp_path: Path):
    """A temporary pod with copies (as tests/test_restore_db.py's), the stub on PATH, and a runner."""
    p = Pod(tmp_path / "pod")
    make_db(p.db, 40, KNOWN)
    vacuum_copy(p.db, p.backup / f"gsd-{STAMPS[0]}.db")
    older = tmp_path / "older.db"
    make_db(older, 30, KNOWN - 1)
    pre = p.pre_upgrade / f"pre-upgrade-{STAMPS[2]}-schema-{KNOWN - 1}-to-{KNOWN}-pod-a.db"
    vacuum_copy(older, pre)
    sidecar(pre)
    kill_writer_after(p.db, 500)
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "oc").write_text(STUB)
    (bin_dir / "oc").chmod(0o755)
    (bin_dir / "python3").symlink_to(sys.executable)
    log, pods_file = tmp_path / "oc.log", tmp_path / "pods.json"

    def run(*args: str, pod_list: dict, answer: str = "") -> subprocess.CompletedProcess:
        pods_file.write_text(json.dumps(pod_list))
        env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "STUB_LOG": str(log),
               "STUB_PODS": str(pods_file), "STUB_PYTHON": sys.executable, "STUB_OFFSITE": str(p.offsite),
               "STUB_PROC": str(p.proc), "STUB_GROUP": str(os.getgid()), "PYTHONPATH": str(LOCAL_DEV),
               "GSD_RECOVERY_MODE": "true", "GSD_DB_PATH": str(p.db), "GSD_BACKUP_DIR": str(p.backup),
               "TMPDIR": str(p.tmp)}
        return subprocess.run(["bash", str(WRAPPER), *args], input=answer, capture_output=True, text=True,
                              env=env, timeout=120)

    run.pod, run.log, run.pre = p, log, pre
    return run


def calls(lab) -> list[str]:
    return lab.log.read_text().splitlines() if lab.log.exists() else []


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_t302_4_outside_recovery_mode_it_refuses_names_the_value_and_never_execs(lab) -> None:
    result = lab("--list", pod_list=pods({"GSD_DB_PATH": "/data/gsd.db"}))
    assert result.returncode == 2
    assert "is not in recovery mode" in result.stderr
    assert "Set recovery.enabled: true and recovery.ttl: 2h in this release's values file" in result.stderr
    assert "applications.argoproj.io" not in result.stderr and "helm upgrade" not in result.stderr
    assert [c for c in calls(lab) if c.startswith("exec")] == []


@pytest.mark.parametrize("n", [0, 2])
def test_t302_5_none_or_two_pods_are_refused_before_any_exec(lab, n: int) -> None:
    result = lab("--from-version", f"{KNOWN}-{STAMPS[0]}", "--yes", pod_list=pods(RECOVERY, n=n))
    assert result.returncode == 2 and f"{n} pods match app=group-sync-dashboard" in result.stderr
    assert [c for c in calls(lab) if c.startswith("exec")] == []


def test_t302_5_uvicorn_in_the_pod_is_refused_by_the_helper_and_nothing_is_written(lab) -> None:
    (lab.pod.proc / "1" / "cmdline").write_bytes(b"python3.14\0-m\0uvicorn\0gsd.api:create_app\0")
    before = digest(lab.pod.db)
    result = lab("--from-version", f"{KNOWN}-{STAMPS[0]}", "--yes", pod_list=pods(RECOVERY))
    assert result.returncode == 2 and "uvicorn is running here" in result.stderr
    assert digest(lab.pod.db) == before and not lab.pod.pre_restore.exists()


def test_t302_10_answering_no_writes_nothing_after_the_loss_window_is_shown(lab) -> None:
    before = {n: digest(lab.pod.data / n) for n in ("gsd.db", "gsd.db-wal")}
    result = lab("--from-version", f"{KNOWN}-{STAMPS[0]}", pod_list=pods(RECOVERY), answer="n\n")
    assert result.returncode == 4 and "not confirmed" in result.stderr
    assert "loss window  2026-10-01T05:11:03Z -> " in result.stdout and "[y/N]" in result.stdout
    assert "sync_event" in result.stdout and result.stdout.count("discarded") >= 1
    assert [c.split(" -- ")[1] for c in calls(lab) if c.startswith("exec")] == [
        f"python3.14 /dev/stdin check {KNOWN}-{STAMPS[0]}"]
    assert {n: digest(lab.pod.data / n) for n in ("gsd.db", "gsd.db-wal")} == before
    assert not lab.pod.pre_restore.exists()


def test_t302_11_yes_restores_without_asking(lab) -> None:
    result = lab("--from-version", f"{KNOWN - 1}-{STAMPS[2]}", "--yes", pod_list=pods(RECOVERY))
    assert result.returncode == 0, result.stderr
    assert "[y/N]" not in result.stdout
    assert f"user_version {KNOWN} -> {KNOWN - 1}" in result.stdout
    assert digest(lab.pod.db) == digest(lab.pre)
    (kept,) = [d for d in lab.pod.pre_restore.iterdir() if d.is_dir()]
    assert count(kept / "gsd.db") == 540
    assert [c.split(" -- ")[1].split()[2] for c in calls(lab) if c.startswith("exec")] == ["check", "restore"]


def test_t302_17_too_little_ttl_left_is_refused_from_the_pod_spec_alone(lab) -> None:
    result = lab("--from-version", f"{KNOWN}-{STAMPS[0]}", "--yes",
                 pod_list=pods(RECOVERY, started_ago=2 * 3600 - 300))
    assert result.returncode == 2
    assert "of recovery.ttl 2h is left, less than the 10m a restore keeps in hand" in result.stderr
    assert "a longer recovery.ttl" in result.stderr and "oc delete" not in result.stderr
    assert [c for c in calls(lab) if c.startswith("exec")] == []


def test_list_prints_the_pod_the_image_and_the_rows(lab) -> None:
    result = lab("--list", pod_list=pods(RECOVERY))
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith("pod      group-sync-dashboard-6c5d8f7b9d-q2x7m · recovery mode, at least 1h49m")
    assert "image    quay.io/ephico2real/group-sync-dashboard:2.0.0" in result.stdout
    assert f"{KNOWN - 1}-{STAMPS[2]}" in result.stdout


def test_usage_errors_exit_64(lab) -> None:
    for args in ((), ("--from-version",), ("--bogus",), ("--namespace", "")):
        assert lab(*args, pod_list=pods(RECOVERY)).returncode == 64, args


def test_the_restore_is_bound_to_what_check_showed(lab) -> None:
    """The question sits between two sessions; `restore` gets check's confirmation line and refuses anything else."""
    result = lab("--from-version", f"{KNOWN - 1}-{STAMPS[2]}", "--yes", pod_list=pods(RECOVERY))
    assert result.returncode == 0, result.stderr
    assert f"confirmation sha256={digest(lab.pre)} size={lab.pre.stat().st_size} live-sha256=" in result.stdout
    restore = [c.split(" -- ")[1] for c in calls(lab) if c.startswith("exec")][-1].split()
    assert restore[:4] == ["python3.14", "/dev/stdin", "restore", f"{KNOWN - 1}-{STAMPS[2]}"]
    assert restore[4:8] == ["--expected-sha256", digest(lab.pre), "--expected-size", str(lab.pre.stat().st_size)]
    assert restore[8] == "--expected-live-sha256" and len(restore[9]) == 64
```

### Block 13 — local-development/tests/test_restore_db_safety.py: Codex's review regressions

The eight probes of Codex's review, adapted to this design where it differs from Codex's blocks (Orchestrator's notes, 17) (§4.1).

<!-- block: local-development/tests/test_restore_db_safety.py | create -->

```python
"""Safety regressions found by Codex's review of SPEC E3 (#302, 2026-10-01): the confirmed plan bound to the bytes,
the snapshot checked before the live set changes, a failed fold that removes nothing, one helper operation at a
time, the whole loss plan, one action per call, and a way back from the kept set. Each failed on the spec's first
blocks (docs/specs/SPEC_E3_restore_db.md §4.2)."""
from __future__ import annotations

import fcntl
import importlib.util
import os
import shlex
import sqlite3
from pathlib import Path

import pytest

from gsd.store import KNOWN_SCHEMA_VERSION as KNOWN
from test_restore_db import STAMPS, Pod, make_db, sha, vacuum_copy
from test_restore_db_wrapper import RECOVERY, lab, pods  # noqa: F401 (lab is a fixture)

LOCAL_DEV = Path(__file__).resolve().parents[1]
HELPER = LOCAL_DEV / "restore-db.py"


def load_helper():
    spec = importlib.util.spec_from_file_location("review_restore_db", HELPER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def stub_that_moves_after_check(lab, source: Path, target: Path) -> None:
    """`oc` as the wrapper tests stub it, which also replaces `target` with `source` once `check` has returned."""
    stub = lab.log.parent / "bin" / "oc"
    stub.write_text(f'''#!/usr/bin/env bash
printf '%s\\n' "$*" >> "$STUB_LOG"
case "$1" in
  get) cat "$STUB_PODS" ;;
  exec)
    while [ "$#" -gt 0 ] && [ "$1" != /dev/stdin ]; do shift; done
    shift
    "$STUB_PYTHON" /dev/stdin "$@" --offsite "$STUB_OFFSITE" --proc "$STUB_PROC" --group "$STUB_GROUP"
    rc=$?
    if [ "${{1:-}}" = check ]; then mv {shlex.quote(str(source))} {shlex.quote(str(target))}; fi
    exit "$rc" ;;
esac
''')
    stub.chmod(0o755)


def test_confirmed_candidate_bytes_are_bound_to_the_restore(lab, tmp_path: Path) -> None:
    """Replace the copy under the same ID after the wrapper's check returns and before its restore."""
    candidate = lab.pod.backup / f"gsd-{STAMPS[0]}.db"
    replacement = tmp_path / "replacement.db"
    make_db(replacement, 1, KNOWN)
    stub_that_moves_after_check(lab, replacement, candidate)
    before = sha(lab.pod.db)
    restored = lab("--from-version", f"{KNOWN}-{STAMPS[0]}", "--yes", pod_list=pods(RECOVERY))
    assert restored.returncode == 3, "same ID but unconfirmed bytes were restored"
    assert "changed after the check you answered" in restored.stderr
    assert sha(lab.pod.db) == before and not lab.pod.pre_restore.exists()


def test_confirmed_live_set_is_bound_to_the_loss_plan(lab, tmp_path: Path) -> None:
    """A second restore or a hand change between the question and the restore makes the plan shown wrong."""
    changed_live = tmp_path / "changed-live.db"
    make_db(changed_live, 99, KNOWN)
    stub_that_moves_after_check(lab, changed_live, lab.pod.db)
    changed_sha = sha(changed_live)
    restored = lab("--from-version", f"{KNOWN}-{STAMPS[0]}", "--yes", pod_list=pods(RECOVERY))
    assert restored.returncode == 3
    assert "live database set changed after the check you answered" in restored.stderr
    assert sha(lab.pod.db) == changed_sha and not lab.pod.pre_restore.exists()


def test_written_snapshot_schema_is_checked_before_the_live_set_changes(tmp_path: Path, monkeypatch) -> None:
    """Replace the copy after its header was read but before it is hashed: the snapshot's own schema refuses."""
    helper = load_helper()
    pod = Pod(tmp_path / "pod")
    make_db(pod.db, 20, KNOWN)
    candidate = pod.backup / f"gsd-{STAMPS[0]}.db"
    vacuum_copy(pod.db, candidate)
    newer = tmp_path / "newer.db"
    make_db(newer, 1, KNOWN + 1)
    before = sha(pod.db)
    real_schema = helper.schema_of
    replaced = False

    def replace_after_header(path: Path):
        nonlocal replaced
        result = real_schema(path)
        if Path(path) == candidate and not replaced:
            replaced = True
            os.replace(newer, candidate)
        return result

    monkeypatch.setattr(helper, "schema_of", replace_after_header)
    monkeypatch.setenv("GSD_RECOVERY_MODE", "true")
    monkeypatch.setenv("GSD_DB_PATH", str(pod.db))
    monkeypatch.setenv("GSD_BACKUP_DIR", str(pod.backup))
    monkeypatch.setenv("TMPDIR", str(pod.tmp))
    rc = helper.main(["restore", f"{KNOWN}-{STAMPS[0]}", "--offsite", str(pod.offsite),
                      "--proc", str(pod.proc), "--group", str(os.getgid())])
    assert rc == 3
    assert sha(pod.db) == before and not pod.pre_restore.exists()
    assert not (pod.data / "gsd.db.restore.tmp").exists()


def test_fold_failure_preserves_the_live_journal(tmp_path: Path, monkeypatch) -> None:
    """SQLite cannot open the old file at all (OperationalError) and a -wal with bytes is beside it: nothing goes."""
    helper = load_helper()
    pod = Pod(tmp_path / "pod")
    pod.db.write_bytes(b"not a sqlite database")
    wal = Path(f"{pod.db}-wal")
    wal.write_bytes(b"committed bytes that must not be unlinked")
    monkeypatch.setenv("GSD_DB_PATH", str(pod.db))
    monkeypatch.setenv("GSD_BACKUP_DIR", str(pod.backup))
    monkeypatch.setattr(helper.sqlite3, "connect",
                        lambda *args, **kwargs: (_ for _ in ()).throw(sqlite3.OperationalError("cannot open")))
    with pytest.raises(sqlite3.Error):
        helper.fold(helper.Layout(pod.offsite))
    assert wal.read_bytes() == b"committed bytes that must not be unlinked"


def test_loss_plan_names_all_append_only_history_and_other_rolled_back_state(tmp_path: Path) -> None:
    pod = Pod(tmp_path / "pod")
    make_db(pod.db, 2, KNOWN)
    conn = sqlite3.connect(pod.db)
    for table in ("login_event", "kyverno_result_event"):
        conn.execute(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY AUTOINCREMENT, v TEXT)")
        conn.executemany(f"INSERT INTO {table}(v) VALUES (?)", [("copy",), ("copy",)])
    conn.execute("CREATE TABLE kpi_daily(day TEXT PRIMARY KEY, v TEXT)")
    conn.execute("INSERT INTO kpi_daily VALUES ('2026-10-01', 'copy')")
    conn.commit()
    conn.close()
    vacuum_copy(pod.db, pod.backup / f"gsd-{STAMPS[0]}.db")
    conn = sqlite3.connect(pod.db)
    for table in ("login_event", "kyverno_result_event"):
        conn.execute(f"INSERT INTO {table}(v) VALUES ('live')")
    conn.execute("UPDATE kpi_daily SET v='live'")
    conn.commit()
    conn.close()
    result = pod.run("check", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 0, result.stderr
    assert "login_event" in result.stdout and "kyverno_result_event" in result.stdout
    assert "kpi_daily" in result.stdout and "report_run" in result.stdout
    assert "estimate" in result.stdout.lower()


@pytest.mark.parametrize("order", ["list-first", "restore-first"])
def test_wrapper_rejects_two_actions(lab, order: str) -> None:
    actions = [["--list"], ["--from-version", f"{KNOWN}-{STAMPS[0]}"]]
    args = actions[0] + actions[1] if order == "list-first" else actions[1] + actions[0]
    result = lab(*args, "--yes", pod_list=pods(RECOVERY))
    assert result.returncode == 64
    assert not lab.pod.pre_restore.exists() and not lab.log.exists()


def test_check_cannot_open_the_live_database_during_a_restore(tmp_path: Path) -> None:
    pod = Pod(tmp_path / "pod")
    make_db(pod.db, 2, KNOWN)
    vacuum_copy(pod.db, pod.backup / f"gsd-{STAMPS[0]}.db")
    with (pod.tmp / "gsd-restore.lock").open("w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        result = pod.run("check", f"{KNOWN}-{STAMPS[0]}")
    assert result.returncode == 2 and "another restore or database inspection" in result.stderr


def test_runbook_explains_how_to_recover_a_kept_live_set() -> None:
    runbook = (LOCAL_DEV.parent / "docs" / "RUNBOOK_backup_restore.md").read_text()
    section = runbook.split("**Undo a restore.**", 1)[1].split("\n\n", 1)[0]
    assert all(word in section for word in ("gsd.db", "-wal", "-shm", "-journal", "integrity_check", ".tmp"))
    assert runbook.count("rm -f /data/gsd.db-wal /data/gsd.db-shm /data/gsd.db-journal") >= 2
```

