# SPEC E5 — the off-volume backup on by default: three states, a yield where it cannot work, and the newest pre-upgrade copy shipped too (#304)

| | |
|---|---|
| Programme | Epic E (#385), restore tools and release safety; the child that turns `backup.offsite` on by default. SPEC_E2 (#303) mounts the claim this CronJob writes and calls the helper this spec adds (Orchestrator's notes, 1) |
| Batch | E — restore tools and release safety |
| Release | — (post-programme; Epic E's release, milestone 3.0.0) |
| Version on release | chart 0.61.0 (chart only) |
| Version note | No application version: `charts/**` is outside `publish.yml`'s image paths (`.github/workflows/publish.yml#NOTE charts/** is deliberately ABSENT`), and nothing else changes in the image. The chart takes a MINOR, 0.59.25 to 0.60.0, because a default changes and a value's grammar widens (`charts/group-sync-dashboard/Chart.yaml#MAJOR and MINOR for behaviour`). **When specs claim the same numbers, the rule is:** a spec still `specified` must name a version above `Chart.yaml` (`local-development/tests/test_specs_index.py#test_a_spec_the_changelog_has_not_begun_names_versions_the_tree_has_not_reached`), so whichever implementation merges first takes its number and, in the same pull request, moves every other `specified` spec whose chart version is not above the new `Chart.yaml` to the next free version above it, in its header and its index row, keeping its MINOR or PATCH and its application version. On origin/main `b5463d45` those are SPEC_E2 (chart 0.60.0), SPEC_G2 (app 2.1.0, chart 0.60.0) and SPEC_E4 (app 2.1.0, chart 0.59.26): blocks 36 to 39 move them to chart 0.61.0, 0.61.0 and 0.60.2, 0.60.1 being SPEC_G3's (this spec changes no application version, so their app cells stay). SPEC_G3 (app 2.2.0, chart 0.60.1) is already above 0.60.0 and is left alone. Measured: §7 without blocks 36 to 39 fails that test with `AssertionError: ('E2', 'chart 0.60.0 (chart only)', 'Chart.yaml is already 0.60.0')`; with them the full hermetic suite passes (§4.3). If another of them is implemented first, its pull request moves this spec's two cells instead, and this spec's implementing pull request re-derives blocks 36 to 41 before applying: it drops the cells that no longer collide and corrects the version in blocks 40 (the CHANGELOG entry) and 41 (`Chart.yaml`), with the reason under these notes (`docs/specs/README.md`, "Implementation blocks"). SPEC_E3 (#302, app 2.1.0, chart 0.59.26) is not on main; when it is, the same rule applies to it. The epic's build order puts #303 first, so the expected case is SPEC_E2's implementing pull request moving this spec to chart 0.61.0 |
| Issue | [#304](https://github.com/ephico2real2/group-sync-dashboard/issues/304) |
| Status | released |
| Source | OB1-lite's research and specification of 2026-10-01, written before any code, from the issue's "Decisions and corrections (2026-10-01)", the epic's decisions of 2026-09-26, SPEC_M1 §3.8 and SPEC_E2 at `465411cd`. Measured on origin/main `21132a25` (application 2.0.0, chart 0.59.25) with helm v4.3.0 and the repository's Python 3.14.7 (SQLite 3.53.4), and read-only on the CRC lab (OpenShift 4.22.7, Kubernetes v1.35.6). §7's blocks were cut from a copy of `21132a25` with the design implemented, and proved against a clean tree (§4.3). Revised the same day on the reviews of `4dfde5e6` (OB3 in Grok's seat, OB2 in Codex's), after merging origin/main `3b3d0010` (SPEC G1, E2, G2 and E4); §7 re-cut from that merge and proved again (§4.3; Orchestrator's notes, 10) |

## How to read this spec

**The point in one sentence: `backup.offsite.enabled` becomes a word with three values — empty (the new
default) puts the off-volume copy on wherever it can work and renders nothing where it cannot, `true` keeps
today's refusals, `false` is off — one helper decides for the CronJob, its two alerts and anything else that
must follow them, and the same run also ships the newest pre-upgrade copy.**

Today the copy the dashboard takes every six hours lands on the volume it protects, unless someone opts into
`backup.offsite`. Turning that on by default is one line in `values.yaml`, but measured alone it turns five
configurations that render today into render errors, and breaks 18 chart tests. This spec makes the default
step aside in exactly those five, keeps an explicit `true` strict, reads the switch as a word so a quoted
`"false"` means off, and fixes the tests' expectations one by one.

§1 is the mandate. §2 is the research: each finding names its primary source, the exact sentence relied on,
and what it settles; lab reads carry the command and its output. §2a weighs the alternatives and reconciles
each external claim with the line of code that relies on it. §3 is the design, one decision per subsection,
with the safety budget. §4 maps every test case of the issue (T304-1 to T304-19) to a test and shows each
failing on a tree without the change. §5 is the walk the implementing pull request runs on the lab. §6 is
what an operator sees and what it costs. §7 is the whole change as implementation blocks
(`docs/specs/README.md`, "Implementation blocks"), applied to a clean tree with

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E5_offsite_on_by_default.md . --apply

Citations into the code use `path#anchor`; a line number, where one helps, is written as plain text against
`21132a25`. Upstream sources are named with their URL and the commit or tag they were read at; their line
numbers come from `curl -s <raw-url> | nl -ba`.

## Orchestrator's notes

1. **The interlock with SPEC_E2 (#303), whichever merges first.** SPEC_E2's recovery pod mounts the offsite
   claim read-only "exactly when the CronJob renders with a `pvc` destination" (SPEC_E2, Orchestrator's
   notes 7 and 8), and its block 3 reads the switch by truthiness:

       {{- if and .Values.backup.offsite.enabled (eq .Values.backup.offsite.destination.type "pvc") }}

   After this spec the default is `""`, which a template `if` takes as false (§2.1), so that line would stop
   mounting a claim the CronJob writes. The one helper this spec adds is the contract:
   **`include "gsd.offsiteOn" .` returns the string `"true"` exactly when the offsite CronJob renders, and
   `"false"` otherwise; it refuses the render on a word other than `true`, `false` or empty.** The line
   E2's block must carry is:

       {{- if and (eq (include "gsd.offsiteOn" .) "true") (eq .Values.backup.offsite.destination.type "pvc") }}

   - **This spec merges first:** E2's implementing pull request changes that one line in its block 3 before
     applying, and records it under its notes. E2's own
     `test_the_offsite_claim_is_mounted_exactly_when_the_cronjob_writes_one[default]` fails without it (OB3
     measured that on E2's review, SPEC_E2 §4.2), so the omission cannot ship.
   - **SPEC_E2 merges first:** this spec's implementing pull request adds one edit block for
     `charts/group-sync-dashboard/templates/deployment.yaml`, Old the first line above, New the second,
     after block 9 here, and records it under these notes; the same E2 test is then the guard.
   - Both orders were applied and tested on copies of this branch's merge of origin/main `3b3d0010`, with SPEC_E2
     as merged on main (§4.3, "Composition with SPEC_E2"): each passes both specs' chart tests with the one line
     changed (`391 passed`), and fails E2's `[default]` case without it. OB3 also found that without the line a
     quoted `"false"` makes the recovery pod mount a claim that is never rendered, which E2's test does not cover;
     the one line closes both. Blocks 36 and 39 move SPEC_E2's version cells, which E2's own blocks never touch.
   SPEC_E3 (#302) lists `/offsite` at any depth for `gsd-<stamp>….db` and `pre-upgrade-<stamp>-schema-…`
   names and asked that #304 keep them (SPEC_E3, Orchestrator's notes 8): the second pass ships each copy
   under the store's own name into `/offsite/pre-upgrade/` (§3.6).
2. **A correction to the issue: the default in `values.yaml` is `""`, not `true`.** "The change" opens with
   "`backup.offsite.enabled: true`", but the same section and the epic's decision of 2026-09-26 make empty
   the default and `true` the strict form. A `true` default would be strict, and strict is what fails the
   five renders (§2.6). T304-15 says the key "joins `FLIPPED`"; `FLIPPED` asserts `is True`, so the policy test
   gains a named set, `ON_WHERE_IT_CAN_WORK`, whose members must default to `""` (blocks 26 to 29).
3. **A deviation from the letter of the issue's decision 1, made on "easy to manage, best practice".** The
   decision says the default "must never turn a render that passes today into an error", and its scope is
   the five guards. Four more refusals in `backup-offsite.yaml` are about the offsite stanza's own values: a
   `destination.type` that is not `pvc` or `s3`, a destination claim that is the data claim, a `keep` that is
   not a count, and an `s3` destination without its Secret or image. Today each of those renders cleanly while
   offsite is off; with the default on they fail (measured, §2.6). They stay refusals in every state: a value
   set by hand under `backup.offsite.destination` says offsite is wanted, and yielding there would be a
   configured backup that silently never runs, which is the mistake the template's first guard exists for
   (`charts/group-sync-dashboard/templates/backup-offsite.yaml#the mistake it catches is`). The CHANGELOG's
   upgrade note names the case and the way out. The same exception applies to the epic's acceptance check E4
   ("Every configuration that renders today still renders"), which is read with it. Who it breaks, measured on
   the merge of origin/main `3b3d0010` with §7 applied: none of the seventeen values files the repository ships
   for this chart (`environments/crc.yaml`, both `example-production.yaml`, the fourteen under
   `reports/*/prepared/`) sets a `backup.offsite` value, and all seventeen render; the lab's Application adds only
   a `clusters` override (OB3's read). A release that does break fails its whole render, not only the offsite
   objects, with that value's message. The review kept the refusals (OB3: a typo'd destination would otherwise
   yield silently while the estate believes the new default turned offsite on); the alternative is one more
   condition in the helper (§2a, A9).
4. **The pre-upgrade pass runs on the `pvc` destination at one replica only.** SPEC_M1 §3.8 recommends "one
   replica only": above one each pod has its own `/data/<pod>/pre-upgrade/` (SPEC_M1 §2.5). The `s3` destination is
   left as it is: its upload container and any operator-written `command` are documented to find "the
   verified copy and its `.sha256` sidecar" under `/stage` (`charts/group-sync-dashboard/values.yaml#The verified copy and its .sha256`),
   so a subdirectory there could break a custom command, and S3 has no `keep` to bound a second set of keys.
   The values comment says so.
5. **The pass checks the copy against the sidecar the store wrote.** A pre-upgrade copy whose bytes no longer
   match the `.sha256` beside it on the volume is refused, not shipped under a fresh sidecar that would vouch
   for it. The six-hourly pass is unchanged: the app writes no sidecar for its `gsd-*.db` backups, and the
   check is a keyword argument only the second pass sets (§3.6).
6. **A cluster with no default StorageClass.** The claim omits `storageClassName` when
   `destination.pvc.storageClass` is empty, so it takes the cluster's default class; with none, it stays
   unbound until one exists (§2.3), and the bind Job fails after its 600 s deadline. That is the operator's
   ruling of 2026-09-22 ("If there is no default storage class or storage available, how is that our problem?
   That is a prerequisite"), and the data claim has the same prerequisite unless `persistence.storageClass`
   names a class. The one release shape that gains a failure is one that names `persistence.storageClass` on
   a cluster with no default class; the CHANGELOG's upgrade note says to name
   `backup.offsite.destination.pvc.storageClass` too. Not measured on a cluster without a default class.
7. **The Grafana board's text panel** (`charts/group-sync-dashboard/dashboards/group-sync-dashboard.json#nineteen with backup.offsite`)
   says "seventeen, nineteen with backup.offsite"; that is still true, so the board is left as it is. The
   chart README's heading keeps the words "The seventeen alerts",
   which two specs cite (`charts/group-sync-dashboard/README.md#The seventeen alerts`).
8. **The index.** This spec's row follows SPEC_G3's in `docs/specs/README.md`, and
   `local-development/tests/test_specs_index.py`'s count moves from 40 to 41. Like E2, G2, E4 and G3, E5 is excluded
   from the rising issue numbers by its id and pinned to its issue, `assert ROWS["E5"]["issue"] == "304"`, not by
   the number: excluded by the number alone, E5 mistyped as #504 in its row and its header passed every index
   check (OB3's mutant). Measured on the merge: with the pin, that mutant fails `AssertionError: ('E5 is #304',
   '504')`; with the pin removed, it passes `88 passed` (measured on the merge of origin/main `b5463d45`).
9. **The stale alert after the second pass** (the review's N1). A run fails when either pass fails, so
   `GroupSyncDashboardOffsiteBackupStale` can fire while the six-hourly copies still leave the volume: a refused
   pre-upgrade copy fails every run until a newer upgrade replaces it or it is moved aside. The alert's
   description, the chart README's row and runbook §2 say so, and runbook §2 says how to clear it (blocks 9, 13
   and 16, held by `test_a_refused_pre_upgrade_copy_is_named_by_the_alert_and_the_runbook`).
10. **The reviews of `4dfde5e6`, decided by the orchestrator on 2026-10-01.** OB3 (in Grok's seat) and OB2 (in
    Codex's seat, Codex being out of usage) confirmed the switch over 43 input forms, the nine yield shapes, the
    script's 13 edge cases, both composition orders with SPEC_E2 as merged, and RBAC REMOVED 0 ADDED 0.
    - **Accepted, required:** F1, the version rule above and blocks 36 to 39 (OB3 measured §7 on main failing the
      ladder test on SPEC_E2); F2, the index pin (note 8; OB2 found it too); F4, A8's Bitnami ref (`17930f7` is
      ambiguous in bitnami/charts and its raw URL answers 404; `17930f75cdbc` resolves to the quoted lines).
    - **Accepted, recommended:** N1 (note 9); F5 (note 3); F6, the chart README says what a cluster with no
      default StorageClass does (block 11); OB2's F2, the CHANGELOG's upgrade note adds that a valid destination
      filled in while `enabled` was left unset is now used (block 40).
    - **Not taken:** OB3's alternative to F1, naming 0.61.0 here now: block 41 would then check out only after
      SPEC_E2 is applied. OB3's N2, the root README's monitoring sentence ("twelve alerting rules … both off by
      default"), was wrong before this spec and is not in a block this spec touches; it is left for its own
      change.
11. **For the operator:** none. The three-state switch was settled on 2026-09-26, the pre-upgrade pass on SPEC_M1
   §3.8, and the rest above on "easy to manage, best practice".
12. **Re-cut at implementation, 2026-10-01, on origin/main `721a78db`** (application 2.2.0, chart 0.60.2: SPEC_E2,
    SPEC_E3 and SPEC_E4 merged after §7 was cut). `apply-spec-blocks.py` stopped at `FAIL block 14
    (charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md | edit): Old text occurs 0 times`; checked block by block past that, blocks 37,
    38, 39 and 41 failed the same way, and block 36 checked out against a spec that is no longer `specified`. Each
    correction is mechanical; no design changed:
    - **Block 9a, added** (note 1, "SPEC_E2 merges first"): `charts/group-sync-dashboard/templates/deployment.yaml`
      line 60 still read the switch by truthiness. Old the first line of note 1, New the second.
    - **Block 14**: its Old text led with the on-volume bullet's last line, which SPEC_E4's block 24 rewrote (#521;
      SPEC_E7's note 7 found it). Re-cut as the off-volume bullet alone; the New text is unchanged.
    - **Block 36, dropped**: SPEC_E2 is `merged` at chart 0.60.0, and the version rule reads `specified` specs only.
    - **Blocks 37 to 39, re-derived** from `docs/specs/README.md` on `721a78db` under the Version note's rule. This
      spec takes chart 0.61.0, the MINOR above 0.60.2 that its header already named (SPEC_E2's pull request moved
      it). The `specified` specs whose chart cell 0.61.0 reaches move to the next version no spec claims, keeping
      their MINOR or PATCH, their app cell and their order: SPEC_G2 0.61.0 → 0.63.0 (0.62.0 is SPEC_W1's, which
      stays); SPEC_G4 0.60.3 and 0.60.4 → 0.61.1 and 0.61.2; SPEC_G3 0.60.5 → 0.61.3; SPEC_E6 0.60.6 → 0.61.4.
      SPEC_E4 is `merged` and its cell stays; SPEC_E9 names no chart version. Blocks 37, 38, 38a, 38b (headers) and
      39 to 39c (index rows).
    - **Block 40**: first under `## Unreleased`, above SPEC_E4's entry rather than above K5's (three Epic E entries
      now sit between them), and naming chart 0.61.0, the version `Chart.yaml` reaches
      (`local-development/tests/test_kyverno.py#test_f3_unreleased_cites_the_current_chart_version_when_it_moved_since_the_last_release`).
    - **Block 41**: Old is the tail SPEC_E4 left (`version: 0.60.2`), New 0.61.0 with the same history line.
    - **`environments/crc.yaml` and PR #522** (open at implementation, head `68cfd97d`): it adds
      `backup.offsite.enabled: true` with `destination.type: pvc` to the lab's values file, so §2.7's and §5's "sets
      nothing under `backup`" and note 3's "none … sets a `backup.offsite` value" hold for `721a78db` only. Measured
      with that file on the applied chart (helm v4.3.0): it renders, since `true` is strict and no blocker holds, with
      the five objects, the two alerts and `--pre-upgrade-source /data/pre-upgrade` (one replica); RBAC against
      `721a78db`'s chart with the same file `rules: before 65, after 65`, `REMOVED 0`, `ADDED 0`, bindings 8 and 8.
      The lab walk (§5) then takes the `true` path rather than the default, and observes the same objects.

13. **The lab's values table, after PR #522 (`7c9ba624`), 2026-10-01.** #522 set `backup.offsite.enabled: true` with
    the `pvc` destination in `environments/crc.yaml` and added its row to `environments/README.md`'s key table with
    the chart default `false`. After this spec the chart default is the empty word, so on the merge of origin/main
    `local-development/tests/test_environments_readme.py#test_every_claimed_chart_default_is_the_real_chart_default`
    failed: `backup.offsite.enabled: README says default 'false', values.yaml says '""'`. Block 19a corrects the cell
    to `""` and says what the lab's `true` now means: the strict form, not the switch that turns the copy on. The
    `destination.type` row (`pvc`, redundant) is unchanged. Re-rendered with `environments/crc.yaml` from
    `7c9ba624` on the applied chart: renders, the five offsite objects, the two alerts and
    `--pre-upgrade-source /data/pre-upgrade`; RBAC against `7c9ba624`'s chart `rules: before 65, after 65`,
    `REMOVED 0`, `ADDED 0`, bindings 8 and 8.

14. **The review of PR #524, 2026-10-02 (OB2, Fable, in Codex's seat), F1, accepted (required).** A values file that
    leaves `config.backup:` `dir:` blank gives a null, which removes the key (§2.2). Version 0.60.2 rendered it, and the
    ConfigMap hands the app `backupDir: ""`, backups disabled. On head `3763be41` the default render failed:
    `executing "gsd.offsiteBlocker" at <.Values.config.backup.dir>: wrong type for value; expected string; got
    interface {}`, because `hasPrefix` cannot read a nil. `gsd.offsiteBlocker` now reads the dir as a word, with the
    idiom `gsd.offsiteOn` uses for its own nil (block 6), so that release yields by default and `true` refuses it
    with the existing empty-dir message. `TestYield::test_a_null_backup_dir_is_the_empty_dir` holds it (block 22):
    on `3763be41` it fails with that type error, and it passes with the fix.

## 1. The mandate, and what is out of scope

The issue (#304, "What must be accomplished"): a default install ships its backups off the data volume (the
CronJob, its ConfigMap, the grant-less ServiceAccount, the 5Gi claim with `helm.sh/resource-policy: keep`, the
bind Job); the default steps aside, with no error, where any of the five guards would fail; an explicit `true`
keeps today's refusals; the switch is read as a word; the two offsite alerts follow the CronJob exactly; the
newest pre-upgrade copy leaves the volume in a second pass, to its own directory, at one replica; the policy
test agrees; nothing else moves (the PDB, the dashboard's RBAC, the offsite account's lack of any grant, the
data and report-artifacts claims); and it works on the lab. Its Definition of Done asks for T304-1 to T304-18
failing on main where marked and passing on the head, a chart bump with RBAC REMOVED 0, the values comment,
the chart README row, the runbook and the CHANGELOG with the upgrade note, two reviewer seats, and the lab walk
with the PVC UIDs unchanged.

Out of scope, each owned elsewhere: recovery mode and its mount (#303, SPEC_E2; this spec only gives it the
helper), the restore script and its `offsite` source (#302, SPEC_E3), per-pod backup rotation above one replica
(#391, SPEC_E4), choosing a different StorageClass for the destination claim (advice in the values comment, as
before), and S3 for the pre-upgrade copy (Orchestrator's notes, 4).

## 2. Research, measured

### 2.1 How a template reads `false`, `"false"` and `""`

**Go's `if`.** `text/template` (go1.27.1, the toolchain helm v4.3.0 reports; `src/text/template/doc.go`
lines 88-92 at tag `go1.27.1`): "If the value of the pipeline is empty, no output is generated; otherwise, T1
is executed. The empty values are false, 0, any nil pointer or interface value, and any array, slice, map, or
string of length zero." So `"false"` (a five-letter string) is true and `""` is false.

**Sprig's `default`.** Helm's function list (helm/helm-www at `5d30947`, `docs/chart_template_guide/function_list.mdx`
lines 145-155): "if `.Bar` evaluates to a non-empty value, it will be used. But if it is empty, `foo` will be
returned instead. The definition of "empty" depends on type: … Boolean: `false` … And always `nil` (aka
null)". The code, Masterminds/sprig v3.3.0 (the version helm v4.3.0's `go.mod` pins, line 10),
`defaults.go` lines 26-31 and 47-48: `func dfault(d interface{}, given ...interface{}) interface{} { if
empty(given) || empty(given[0]) { return d } …` and `case reflect.Bool: return !g.Bool()`. So `false |
default true` is `true`: an explicit off turns on. The chart already records this trap
(`charts/group-sync-dashboard/templates/fleet-account-rbac.yaml#A WORD, NOT TRUTHINESS`).

**`kindOf`, `kindIs`, `toString`.** Function list lines 2273-2286: "`kindOf` returns the kind of an object …
the `kindIs` function will let you verify that a value is a particular kind"; line 716: "`toString`: Convert
to a string." Code: sprig `reflect.go` lines 22-28, `kindOf` is `reflect.ValueOf(src).Kind().String()`, so a
nil value's kind is `invalid`; `strings.go` lines 174-186, `strval` returns a string as itself and anything
else through `fmt.Sprintf("%v", v)`, so a boolean prints `true` or `false` and nil prints `<nil>`.

**Measured** with helm v4.3.0 on a probe chart in scratch (`o.x: ""` in its values; one line per form):

```text
<defaults>                         hasKey=true  kindOf=string  toString=""       truthy=no  defaultTrue=true
--set o.x=false                    hasKey=true  kindOf=bool    toString="false"  truthy=no  defaultTrue=true
--set o.x=true                     hasKey=true  kindOf=bool    toString="true"   truthy=yes defaultTrue=true
--set-string o.x=false             hasKey=true  kindOf=string  toString="false"  truthy=yes defaultTrue=false
--set-string o.x=yes               hasKey=true  kindOf=string  toString="yes"    truthy=yes defaultTrue=yes
--set o.x=                         hasKey=true  kindOf=string  toString=""       truthy=no  defaultTrue=true
--set o.x=null                     hasKey=false kindOf=invalid toString="<nil>"  truthy=no  defaultTrue=true
--set o.x=0                        hasKey=true  kindOf=int64   toString="0"      truthy=no  defaultTrue=true
file x: yes | on | True | TRUE     hasKey=true  kindOf=bool    toString="true"   truthy=yes defaultTrue=true
file x: no | off                   hasKey=true  kindOf=bool    toString="false"  truthy=no  defaultTrue=true
file x: ~  and  file x: (empty)    hasKey=false kindOf=invalid toString="<nil>"  truthy=no  defaultTrue=true
file x: "false"                    hasKey=true  kindOf=string  toString="false"  truthy=yes defaultTrue=false
```

What this settles: truthiness is wrong twice (a quoted `"false"` is on, the default `""` is off), `default`
is wrong once (a boolean `false` is on), and `toString` of the value, with nil taken as empty, gives exactly
three words to compare.

### 2.2 How Helm parses a values file, and what a null does

**YAML 1.1 booleans.** Helm v4.3.0 pins `sigs.k8s.io/yaml v1.6.0` (`go.mod` line 52), whose `yaml.go` line 52
says: "As per the YAML 1.1 specification, which yaml.v2 used underneath implements, literal 'yes' and 'no'
strings without quotation marks will be converted to true/false implicitly." The resolver,
yaml/go-yaml `v2.4.4` `resolve.go` lines 37-42, lists `y Y yes Yes YES`, `on On ON` as true and `n N no No NO`,
`off Off OFF` as false. Measured above: `yes`, `on`, `True` arrive as the boolean `true`, `no` and `off` as
`false`. So a values file's unquoted `yes`/`no` is read as the boolean, and only a quoted `"yes"` (or
`--set-string`) is a word to refuse.

**A null.** Helm's values guide (`docs/chart_template_guide/values_files.mdx` lines 149-151 at `5d30947`): "If
you need to delete a key from the default values, you may override the value of the key to be `null`, in which
case Helm will remove the key from the overridden values merge." Measured above: `x: ~` and an empty `x:`
leave no key (`kindOf=invalid`). A release that writes `enabled:` with no value therefore gets the chart's
default, which is the empty word.

**`--set-string`.** `docs/helm/helm_install.md` lines 15-17: "use either the '--values' flag and pass in a file
or use the '--set' flag … to force a string value use '--set-string'." The tests use it to reproduce a values
file's quoted string.

### 2.3 What the new claim needs from the cluster

**Default class.** Kubernetes, "Storage Classes" (kubernetes/website at `980792f`,
`content/en/docs/concepts/storage/storage-classes.md` lines 56-57): "When a PVC does not specify a
`storageClassName`, the default StorageClass is used." Lines 71-74: a PVC created "even when no default
StorageClass exists … creates as you defined it, and the `storageClassName` of that PVC remains unset until a
default becomes available." The template omits the field when the value is empty
(`charts/group-sync-dashboard/templates/backup-offsite.yaml#{{- with $o.destination.pvc.storageClass }}`).

**Binding mode.** The same page, lines 183-184: "`WaitForFirstConsumer` mode … will delay the binding and
provisioning of a PersistentVolume until a Pod using the PersistentVolumeClaim is created." That is why the
bind Job exists (`charts/group-sync-dashboard/templates/backup-offsite.yaml#THE BIND JOB`): without a pod the
claim stays Pending until the first scheduled run, up to six hours.

**On the lab** (read-only, 2026-10-01):

```text
$ oc get storageclass
NAME                                     PROVISIONER                        RECLAIMPOLICY   VOLUMEBINDINGMODE      ALLOWVOLUMEEXPANSION   AGE
crc-csi-hostpath-provisioner (default)   kubevirt.io.hostpath-provisioner   Retain          WaitForFirstConsumer   false                  63d
nfs-csi                                  nfs.csi.k8s.io                     Retain          Immediate              true                   4d23h
$ oc get pvc -n group-sync-dashboard -o custom-columns=…
NAME                                    UID                                    CLASS                          MODES             STATUS   SIZE
group-sync-dashboard-data               f065b7a4-535c-4ef1-868c-58f5afee4953   crc-csi-hostpath-provisioner   [ReadWriteMany]   Bound    1Gi
group-sync-dashboard-report-artifacts   08c7d45c-a3eb-47be-8506-f24ea7a3e0e3   crc-csi-hostpath-provisioner   [ReadWriteOnce]   Bound    2Gi
```

So on CRC the new claim lands on `crc-csi-hostpath-provisioner`, the data claim's own class and node disk: off
the volume, not off the storage, as the issue's Capabilities table says. The UIDs are the issue's.

**Survival annotations.** Helm, "Chart Development Tips and Tricks" (`docs/howto/charts_tips_and_tricks.md`
lines 253-256 at `5d30947`): "The annotation `helm.sh/resource-policy: keep` instructs Helm to skip deleting
this resource when a helm operation (such as `helm uninstall`, `helm upgrade` or `helm rollback`) would result
in its deletion. _However_, this resource becomes orphaned." Argo CD v3.4.7, `docs/user-guide/sync-options.md`
lines 7-14 ("No Prune Resources … `argocd.argoproj.io/sync-options: Prune=false`") and 113-121 ("No Resource
Deletion … you might want to retain them even after your application is deleted, e.g. for Persistent Volume
Claims … `Delete=false`"). Both are object annotations the template already renders on the claim
(`charts/group-sync-dashboard/templates/backup-offsite.yaml#argocd.argoproj.io/sync-options: Prune=false,Delete=false,PruneLast=true`);
nothing here changes them, and T304-1 asserts them on the default render.

### 2.4 How the CronJob runs, and what counts as a success

Kubernetes, "CronJob" (`content/en/docs/concepts/workloads/controllers/cron-jobs.md` at `980792f`):

- lines 135-138: "`Forbid`: The CronJob does not allow concurrent runs; if it is time for a new Job run and the
  previous Job run hasn't finished yet, the CronJob skips the new Job run";
- lines 110-113: `startingDeadlineSeconds` "defines a deadline (in whole seconds) for starting the Job, if that
  Job misses its scheduled time for any reason. After missing the deadline, the CronJob skips that instance of
  the Job";
- lines 210-214: "A CronJob creates a Job object approximately once per execution time of its schedule … there
  are certain circumstances where two Jobs might be created, or no Job might be created … Therefore, the Jobs
  that you define should be _idempotent_."

The controller (kubernetes `v1.35.6`, `pkg/controller/cronjob/cronjob_controllerv2.go`): the Forbid check is
`len(cronJob.Status.Active) > 0` (line 573), with the upstream comment "it is theoretically possible to have
concurrency with Forbid" (lines 574-577); and a finished, succeeded child Job sets `LastSuccessfulTime` whether
or not it is in the active list, "a job does not have to be in active list, as long as it has completed
successfully, we will process the timestamp" (lines 459-468). `kubectl create job --from=cronjob/…`
(`staging/src/k8s.io/kubectl/pkg/cmd/create/create_job.go` lines 254-277 at `v1.35.6`) sets the CronJob as the
Job's controller owner. So a manual run (runbook §2) that succeeds moves
`kube_cronjob_status_last_successful_time` and clears `GroupSyncDashboardOffsiteBackupUnobserved` (T304-19),
while Forbid does not count it: a manual run and a scheduled one can overlap.

### 2.5 Monitoring on the lab

```text
$ oc get pods -n openshift-monitoring | grep -E 'kube-state|prometheus-k8s|thanos'
kube-state-metrics-5845dfd6df-b2lrq   3/3   Running   15   15d
prometheus-k8s-0                      6/6   Running   30   15d
thanos-querier-7b8dd7c9d8-7279p       6/6   Running   24   11d
$ oc get configmap cluster-monitoring-config -n openshift-monitoring -o jsonpath='{.data.config\.yaml}'
enableUserWorkload: true
$ oc get prometheusrules.monitoring.coreos.com -n group-sync-dashboard
NAME                   AGE
group-sync-dashboard   15h
```

kube-state-metrics is scraped, so `GroupSyncDashboardOffsiteBackupUnobserved` fires from the deploy until the
first success and clears after it (§5).

### 2.6 This repository, measured on `21132a25`

**The switch today.** `charts/group-sync-dashboard/values.yaml` line 1020 is `enabled: false`; the template
tests it by truthiness at `backup-offsite.yaml` line 13 (`{{- if .Values.backup.offsite.enabled }}`) and the
alerts at `monitoring.yaml` line 298 (the same test). The five guards are lines 29-43 of `backup-offsite.yaml`;
four more refusals (lines 44-63) check the destination stanza.

**The render matrix.** A script in scratch renders the chart under each state with
`helm template t <chart> --set ingress.host=h <flags>` and prints the return code, the kinds labelled
`app.kubernetes.io/component: backup-offsite`, the number of offsite alerts, and whether the CronJob carries
the pre-upgrade argument. On `21132a25`:

```text
defaults                               rc=0 offsite=[] alerts=0
enabled=true                           rc=0 offsite=['ConfigMap', 'CronJob', 'Job', 'PersistentVolumeClaim', 'ServiceAccount'] alerts=2
enabled=false                          rc=0 offsite=[] alerts=0
set-string enabled=false               rc=0 offsite=['ConfigMap', 'CronJob', 'Job', 'PersistentVolumeClaim', 'ServiceAccount'] alerts=2
set-string enabled=yes                 rc=0 offsite=['ConfigMap', 'CronJob', 'Job', 'PersistentVolumeClaim', 'ServiceAccount'] alerts=2
enabled=null                           rc=0 offsite=[] alerts=0
config.backup.enabled=false            rc=0 offsite=[] alerts=0
RWOP derived                           rc=0 offsite=[] alerts=0
persistence off                        rc=0 offsite=[] alerts=0
config.backup.dir=                     rc=0 offsite=[] alerts=0
config.backup.dir=/backup              rc=0 offsite=[] alerts=0
config.backup.dir=/data/../etc         rc=0 offsite=[] alerts=0
existingClaim, no accessMode           rc=0 offsite=[] alerts=0
true + config.backup.enabled=false     rc=1 backup.offsite.enabled=true requires config.backup.enabled=true. …
true + RWOP derived                    rc=1 backup.offsite.enabled=true cannot work with a ReadWriteOncePod data volume: …
true + persistence off                 rc=1 backup.offsite.enabled=true requires persistence.enabled=true. …
true + dir=                            rc=1 backup.offsite.enabled=true requires config.backup.dir under /data/ with no '..' (it is ""). …
true + existingClaim                   rc=1 backup.offsite.enabled=true with persistence.existingClaim requires persistence.accessMode …
dest type=s3 (no secret)               rc=0 offsite=[] alerts=0
dest type=nfs                          rc=0 offsite=[] alerts=0
dest keep=abc                          rc=0 offsite=[] alerts=0
dest existingClaim=data claim          rc=0 offsite=[] alerts=0
replicaCount=2                         rc=0 offsite=[] alerts=0
```

The quoted-`"false"` defect and the any-word defect are the two `set-string` rows. The five `true + …` rows
are the five renders that fail when only the default is flipped.

**The test impact of flipping only the default.** A copy of `21132a25` with line 1020 alone set to `true`,
running the chart, values, script and pre-upgrade test files (`tests/test_chart_*.py
tests/test_values_defaults.py tests/test_offsite_backup_script.py tests/test_pre_upgrade_copy.py
tests/test_kyverno.py tests/test_ci_charts.py`): main `497 passed, 3 skipped`; flipped `18 failed, 479 passed,
3 skipped`. The 18, the issue's T304-18 list re-measured:

```text
test_chart_backup_offsite.py  TestSwitch::test_nothing_renders_by_default
test_chart_backup_offsite.py  TestAlerts::test_the_two_rules_render_only_with_the_cronjob
test_chart_pdb.py             TestThePdbSelectsTheDeploymentOnly::test_the_selector_matches_the_dashboard_pod_and_no_hook_pod
test_chart_reporting.py       test_default_reporting_render_is_yaml_and_all_selectors_match_only_their_workloads
test_chart_reporting.py       test_report_manifests_have_unique_labels_and_the_service_monitor_selector_matches
test_chart_reporting.py       TestDerivations::test_a_quoted_false_pauses_the_cronjob_and_the_status_page_alike
test_chart_route.py           (nine tests: `one()` expects one dashboard ServiceAccount and finds two, and
                              test_no_service_account_means_no_reference_and_the_route_still_renders lists the offsite one)
test_chart_strategy.py        TestStillRenders::test_rollingupdate_at_one_replica_without_persistence
test_values_defaults.py       test_the_only_false_defaults_are_the_stated_exceptions
test_values_defaults.py       test_every_kept_off_boolean_has_a_reason_comment_above_it
```

Their causes, read from the failures: a second ServiceAccount (route, 9), a second CronJob picked by `next()` or
counted (reporting, 3: `assert 2 == 1`, `'backup-offsite' == 'report-schedule'`, `KeyError: 'suspend'`), the
bind Job counted beside the secrets mint (pdb, 1), the strict `true` failing an emptyDir render (strategy, 1),
the policy lists (values, 2), and the two tests that encode "off by default" (offsite, 2).

**The pre-upgrade copies.** The store writes them beside the database, `Path(db_path).parent / "pre-upgrade"`
(`local-development/gsd/store.py#PRE_UPGRADE_DIR`), named `pre-upgrade-<stamp>-schema-<from>-to-<to>-<pod>.db`
with a `sha256sum -c` sidecar, keeping three (`local-development/gsd/store.py#PRE_UPGRADE_KEEP`). The offsite
script has one pattern, `charts/group-sync-dashboard/scripts/offsite_backup.py#PATTERN = "gsd-*.db"`, and no
option for another (`charts/group-sync-dashboard/scripts/offsite_backup.py#main`).

**RBAC.** `reports/2026-09-27_epic-c-walk/scripts/rbac_rules.py` (one line per kind, namespace, role, group,
resource, verb and name) on `21132a25`'s render and the implemented one: by default `rules: before 59, after
59`, `REMOVED 0`, `ADDED 0`; with `environments/crc.yaml` `rules: before 65, after 65`, `REMOVED 0`, `ADDED 0`.
Bindings and their subjects: by default 7 and 7, with `environments/crc.yaml` 8 and 8, none added or removed.
The only new ServiceAccount is `group-sync-dashboard-backup-offsite`, bound to nothing.

### 2.7 The lab today

```text
$ oc get cronjobs.batch -n group-sync-dashboard
NAME                                                   SCHEDULE           TIMEZONE           SUSPEND   ACTIVE   LAST SCHEDULE   AGE
group-sync-dashboard-report-biweekly-groups            0 6 1,16 * *       America/New_York   True      0        <none>          15h
group-sync-dashboard-report-nightly-namespace-access   0 22 * * *         America/New_York   False     0        12h             15h
group-sync-dashboard-report-quarterly-compliance       0 6 1 1,4,7,10 *   America/New_York   False     0        4h45m           15h
$ oc exec -n group-sync-dashboard group-sync-dashboard-7b9485f499-jspfl -c dashboard -- ls -la /data /data/backup
/data:          backup/  fleet-gate.json  gsd.db (15802368)  gsd.db-shm  gsd.db-wal (4511432)  report/
/data/backup:   gsd-20260930T230906.692903Z.db (14184448)  gsd-20260930T231004.994977Z.db (14188544)
                gsd-20261001T051103.798578Z.db (14204928)  gsd-20261001T111104.000930Z.db (14221312)
```

(The listing is abridged to names and sizes.) No offsite CronJob, no `/data/pre-upgrade`, and four six-hourly
copies of about 14 MB. `environments/crc.yaml` sets nothing under `backup` or `persistence`, so the lab gets the
default, at one replica.

## 2a. Alternatives considered

| # | Option | Source | Cost here | Decision |
|---|---|---|---|---|
| A1 | Flip `enabled` to `true` and nothing else (the issue as filed) | the issue's original description | five renders that pass today fail (§2.6), 18 tests fail | rejected |
| A2 | `true` by default, and yield on every contradiction, with no strict form | the issue's first refinement | loses the operator's ruling that an explicit contradiction still fails (2026-09-22, the epic's decision of 2026-09-26); a `true` someone wrote would be silently ignored | rejected |
| A3 | Two keys: `enabled: true` and `strict: false` | — | a second key, a second README row, and a fourth combination (`enabled: false, strict: true`) to define | rejected; the chart already has a tri-state with empty meaning derived: `monitoring.grafanaDashboard.enabled` (`charts/group-sync-dashboard/templates/_helpers.tpl#gsd.grafanaDashboardEnabled`) |
| A4 | Three words: `""` on where it can work, `true` strict, `false` off | the epic's decision of 2026-09-26; the chart's precedent above | one helper and one word-reader | **chosen** |
| A5 | Read the switch with `default` (`enabled \| default true`) | Sprig `dfault` (§2.1) | an explicit `false` turns offsite on (measured `defaultTrue=true` for `--set o.x=false`) | rejected |
| A6 | Keep truthiness (`if .Values.backup.offsite.enabled`) and add a guard | Go `text/template` (§2.1) | `""` is false, so the default would turn nothing on, and `"false"` stays on | rejected |
| A7 | Decide "can it work" with `lookup` (the StorageClass, the live claim) | Helm, "Using the `lookup` function", `functions_and_pipelines.mdx` lines 271-274: "Helm is not supposed to contact the Kubernetes API Server during a `helm template\|install\|upgrade\|delete\|rollback --dry-run` operation" | Argo CD renders with `helm template` and no cluster, so every `lookup` is empty there and the decision would differ between Helm and Argo | rejected; the five conditions are all decidable from values |
| A8 | Keep the copy opt-in, as other charts do | Bitnami `postgresql` `values.yaml` lines 1327-1329 at `17930f75cdbc` (`backup.enabled: false`); CloudNativePG `charts/cluster/values.yaml` lines 496-498 at `60fda25` ("You need to configure backups manually, so backups are disabled by default"); Velero `charts/velero/values.yaml` line 798 at `6b21973` (`schedules: {}`) | the industry default is off because a backup's destination is the installer's to choose; here the operator ruled the opposite (2026-09-22: "We need to enable offsite backup immediately"; the chart's 0.14.0 rule, booleans on), and a second claim on the default class is a destination the chart can choose | rejected by the operator's ruling; the trade (not off the storage) is stated in the values comment |
| A9 | Yield also on the stanza's own refusals (type, claim, keep, S3) | — | a configured destination that silently never runs | rejected (Orchestrator's notes, 3) |
| A10 | Ship the pre-upgrade copy from a second container, or a second CronJob | SPEC_M1 §3.8 ("a second pass") | a second container runs concurrently with the first and needs its own mounts; a second CronJob needs its own alerts, account and claim | rejected; one run, two passes of the same script (§3.6) |
| A11 | Ship the pre-upgrade copy to S3 too | — | a subdirectory under `/stage` that an operator's custom `command` may not expect, a re-upload every run, no `keep` | rejected (Orchestrator's notes, 4) |

**Reconciliation: each external claim, and the line of this repository that behaves accordingly.**

- Go's `if` treats `""` as false and `"false"` as true → the helper compares words, and both callers test the
  helper's word: `charts/group-sync-dashboard/templates/backup-offsite.yaml#if eq (include "gsd.offsiteOn" .) "true"`
  and the same expression in `charts/group-sync-dashboard/templates/monitoring.yaml#Rendered exactly when the offsite CronJob is`.
- Sprig's `default` treats `false` as empty → `gsd.offsiteOn` never calls `default`; it reads
  `ternary "" (toString $raw) (kindIs "invalid" $raw)` (block 6).
- `kindOf` of nil is `invalid`, `toString` prints a boolean as its word → the same expression; the matrix row
  `enabled=null` renders the default and `set-string enabled=false` renders nothing (§4.3).
- go-yaml v2 resolves `yes`/`no`/`on`/`off` as booleans → `test_a_values_file_reads_the_same[no]`, `[off]`,
  `[yes]` (block 22).
- Helm removes a key set to null → the helper takes an absent key as the empty word;
  `test_a_values_file_reads_the_same[]` (an empty value) renders the CronJob.
- An omitted `storageClassName` takes the default class → `backup-offsite.yaml#{{- with $o.destination.pvc.storageClass }}`
  (unchanged); `test_the_default_ships_the_copy_off_the_volume` asserts the field is absent.
- `WaitForFirstConsumer` binds on the first pod → the bind Job (unchanged), asserted on the default render.
- `Forbid` skips a run while the previous one is active → `charts/group-sync-dashboard/values.yaml#concurrencyPolicy: Forbid`,
  rendered at `backup-offsite.yaml#concurrencyPolicy: {{ $o.concurrencyPolicy }}` (unchanged).
- Jobs "should be idempotent" → the script's "already shipped" skip
  (`charts/group-sync-dashboard/scripts/offsite_backup.py#already shipped`), which the second pass uses
  unchanged; `test_the_newest_copy_ships_verified_and_three_are_kept` runs it five times.
- A succeeded child Job sets `LastSuccessfulTime` → the two rules read `kube_cronjob_status_last_successful_time`
  (`charts/group-sync-dashboard/templates/monitoring.yaml#GroupSyncDashboardOffsiteBackupUnobserved`); §5 step 6
  checks it after a manual run.
- `helm.sh/resource-policy: keep` and Argo's `Prune=false,Delete=false` → rendered on the claim
  (`backup-offsite.yaml#helm.sh/resource-policy: keep`), asserted on the default render.

## 3. The design

### 3.1 Three words, one helper

`gsd.offsiteOn` (block 6) reads `backup.offsite.enabled` and returns `"true"` or `"false"`:

| the value, as Helm hands it to the template | the word | `gsd.offsiteOn` |
|---|---|---|
| absent, null, `""` | `""` | `"true"` unless `gsd.offsiteBlocker` names a condition, then `"false"` |
| boolean `true` (also YAML 1.1 `yes`, `on`, `True`), string `"true"` | `true` | `"true"` |
| boolean `false` (also `no`, `off`), string `"false"` | `false` | `"false"` |
| anything else: `"yes"`, `"ture"`, `0`, `"False"` | that word | the render is refused, naming the three values |

The word is `toString` of the value, or `""` when its kind is `invalid` (nil). Reason: §2.1 measured that
both truthiness and `default` misread one of the three states, and that `toString` prints exactly the words a
values file or `--set` produces. Refusing anything else follows the chart's precedent for a misspelt switch
(`charts/group-sync-dashboard/templates/_helpers.tpl#gsd.grafanaDashboardEnabled`): a word that silently meant
on or off would decide whether the history leaves the volume.

Every template that must agree with the CronJob calls the helper and compares with `"true"`: the CronJob's file
(block 7), the two alerts (block 9), and SPEC_E2's recovery mount (Orchestrator's notes, 1). Reason: the
issue's decision 2; a second, hand-copied condition is how the alerts and the CronJob would drift apart, since
`""` is false to an `if` (T304-12 holds it).

### 3.2 The five conditions, written once

`gsd.offsiteBlocker` (block 6) returns the message of the first of the five conditions that holds, or `""`:
persistence off; `config.backup.enabled` off; `config.backup.dir` not under `/data/` or containing `..` (an
empty dir is not under `/data/`, and the app reads it as "backups disabled", `local-development/gsd/config.py#Empty disables`);
`persistence.existingClaim` without `persistence.accessMode`; and a `ReadWriteOncePod` data volume, derived or
explicit. The messages are today's, moved verbatim from `backup-offsite.yaml` lines 29-43, in today's order.

- With `""`, a non-empty blocker makes `gsd.offsiteOn` `"false"`: nothing renders and nothing fails.
- With `true`, `backup-offsite.yaml` fails with the blocker's message (`{{- with include "gsd.offsiteBlocker" . }}{{- fail . }}`).
  T304-8 compares the messages.

Reason for one helper rather than the guards duplicated as a condition: the yield and the refusal then cannot
disagree about what "cannot work" means.

### 3.3 What stays a refusal in every state

The four refusals about the offsite stanza itself (destination type, the data claim as destination, `keep`,
the S3 Secret and image) are unchanged and apply whenever offsite is on, the default included (Orchestrator's
notes, 3). So does the existing refusal of the non-key `backup.enabled`.

### 3.4 The default value and its comment

`values.yaml` carries `enabled: ""`. The comment above `backup:` states the three words, the five conditions,
that the value is set in the release's values file and rolled out through the release's deployment pipeline,
that the default claim lands on the cluster's default StorageClass (off the volume, not necessarily off the
storage), what happens without a default class, and the pre-upgrade pass (block 10). No `helm upgrade`, `--set`
or Argo CD step appears in it.

### 3.5 The policy test

`backup.offsite.enabled` leaves `KEPT_OFF` and joins `FLIPPED`; a new tuple, `ON_WHERE_IT_CAN_WORK`, names the
flipped keys whose default is `""`, and the check asserts `== ""` for those and `is True` for the rest (blocks 26
to 29). The chart README row no longer says `false` (block 11), which
`local-development/tests/test_values_defaults.py#test_no_current_doc_tells_the_operator_to_enable_a_default` enforces for every
`FLIPPED` key.

### 3.6 The second pass: the newest pre-upgrade copy

The script gains `--pre-upgrade-source DIR` (blocks 1 to 5). After the six-hourly pass, unchanged, it runs
`ship_pre_upgrade(DIR, <dest>/pre-upgrade)`:

- no `DIR`, or no `pre-upgrade-*.db` in it: print "nothing to ship" and succeed. The store writes a copy only
  when an image upgrades the schema, and the lab has none today (§2.7);
- otherwise the existing `ship()` with `pattern="pre-upgrade-*.db"`, `keep=PRE_UPGRADE_KEEP` (3, equal to the
  store's, held by a test), and `require_source_sidecar=True`: newest by name (the stamp leads the name, so name
  order is time order, SPEC_M1 §3.2); copied through `.part`, re-hashed at the destination, `integrity_check` on
  the copy, sidecar written and both renamed into place, then pruned to three; and before publishing, the bytes
  read must match the sidecar the store wrote beside the copy (Orchestrator's notes, 5).

`newest_backup`, `prune` and `ship` take the pattern as a parameter whose default is today's `PATTERN`, so the
six-hourly pass calls them exactly as before. The two passes are independent: each runs, a `BackupError` in one
is printed and does not stop the other, and the process exits 1 if either failed, so the CronJob's status and
both alerts still see any failure. The stale alert therefore fires when either pass keeps failing, and its
description says so (Orchestrator's notes, 9).

The CronJob passes `--pre-upgrade-source /data/pre-upgrade` to the `pvc` container only, and only when
`replicaCount` is not above 1: the same test `deployment.yaml` uses for `GSD_DB_PATH`
(`charts/group-sync-dashboard/templates/deployment.yaml#value: /data/gsd.db`), whose directory's
`pre-upgrade/` is where the store writes. The copies land in `/offsite/pre-upgrade/` under the store's names,
which keeps SPEC_E3's listing working (Orchestrator's notes, 1) and keeps them out of the six-hourly
destination's `gsd-*.db` glob and its `keep` (T304-14).

### 3.7 The budget

Per release, over every replica and restart, with the default or `true`:

| what | bound | scope and source |
|---|---|---|
| CronJobs | 1 | the template renders one, `<fullname>-backup-offsite` |
| scheduled Jobs running at once | 1, best-effort | `Forbid` counts the controller's active list; upstream says concurrency is "theoretically possible" (§2.4). A manual Job (runbook §2) is not counted and can overlap a scheduled one: both write `<name>.part` under the same name, and an overlap ends in a failed hash or integrity check and a failed Job, never a published copy that was not verified (`charts/group-sync-dashboard/scripts/offsite_backup.py#the destination holds sha256`). Not measured |
| claims created | 1, 5Gi, kept on uninstall | `helm.sh/resource-policy: keep`, Argo's `Prune=false,Delete=false` (§2.3); none with `destination.pvc.existingClaim` or `s3` |
| bind Jobs | 1 per pod-spec hash, `backoffLimit: 0`, 600 s | unchanged |
| writes to the data claim | 0 | mounted `readOnly` in the CronJob pod (`backup-offsite.yaml#readOnly: true`); the bind Job does not mount it |
| deletions | only names matching the pass's own pattern in the pass's own directory: `gsd-*.db` (and sidecars, `.part`) in `/offsite`, `pre-upgrade-*.db` (and sidecars, `.part`) in `/offsite/pre-upgrade` | `prune()`'s globs are non-recursive (`Path.glob` without `**`) |
| copies kept | ≤ `keep` (14) six-hourly and ≤ 3 pre-upgrade at rest, one more of each while a run publishes | `prune()` after each publish |
| space at the lab's sizes | about 264 MiB of 5Gi, an estimate | (14 + 1) × 14,221,312 bytes (the newest backup, §2.7) plus (3 + 1) × 15,802,368 bytes (the database file; a pre-upgrade copy is about the database's size, SPEC_M1 §3.5): 276,529,152 bytes. Not measured on a claim |
| grants to the offsite account | 0, and no token | §2.6, RBAC REMOVED 0 ADDED 0; `automountServiceAccountToken: false` |

### 3.8 What does not change

The six-hourly pass's selection, verification, sidecar, prune and messages; `--check`; every refusal message;
the claim's annotations and size; the bind Job; the CronJob's schedule, policy and deadlines; the PDB, which
still selects only the dashboard's pods (T304-16); the dashboard's RBAC (T304-17); the data and
report-artifacts claims; the application image.

## 4. Tests

### 4.1 One test per test case of the issue

"Before" is the new and changed test files run against the chart and script of this branch's merge of origin/main
`3b3d0010` (`547a68ad`; a copy of the tree with only the six test files of §7 replaced); "after" is the tree with §7 applied (§4.3). The quoted failure is the
line pytest printed before.

| ID | test (in `local-development/tests/`) | before | after |
|---|---|---|---|
| T304-1 | `test_chart_backup_offsite.py::TestSwitch::test_the_default_ships_the_copy_off_the_volume` (replaces `test_nothing_renders_by_default`): the CronJob, the ConfigMap carrying the script, the account without a token, the 5Gi claim with `helm.sh/resource-policy: keep`, Argo's `Prune=false,Delete=false,PruneLast=true` and no `storageClassName`, and one bind Job | fails: `assert False == ''` (the default is `false`) | passes |
| T304-2 to T304-7 | `TestYield::test_the_default_steps_aside[…]`, seven cases: on-volume backup off; derived `ReadWriteOncePod`; persistence off; empty backup dir; dir outside `/data/`; dir walking out of `/data/` (`/data/../etc`); existing data claim without an access mode. Each: render succeeds, no object labelled `backup-offsite`, no offsite alert | passes (offsite is off by default): regression guards. With only the default flipped, each of these renders fails (§2.6, the five `true + …` rows) | passes |
| T304-8 | `TestYield::test_true_still_refuses_with_the_reason[…]`, the same seven, each with its message; the existing `TestPrerequisites` and `TestAccessModes` refusals are kept with `true` | passes (`true` is strict on main): regression guard. The six messages compared byte for byte between `547a68ad` and the applied tree are the same (§4.3) | passes |
| T304-9 | `TestTheSwitchIsAWord::test_false_is_off`; `TestAlerts::test_the_two_rules_render_exactly_when_the_cronjob_does[false]` | passes: regression guard. Mutation M2 (the word read through `default`) fails it (§4.2) | passes |
| T304-10 | `test_a_quoted_word_means_what_it_says[false-False]`, `test_a_values_file_reads_the_same["false"-False]` | fails: `assert (True is False)`, the CronJob renders | passes |
| T304-11 | `test_any_other_word_is_refused_naming_the_three[yes, ture, 0, False]` | fails: `assert not True`, the render succeeds | passes |
| T304-12 | `TestAlerts::test_the_two_rules_render_exactly_when_the_cronjob_does[…]`, eleven states (default, `true`, `false`, quoted `"false"`, the seven yield cases) (replaces `test_the_two_rules_render_only_with_the_cronjob`); `test_the_two_rules_watch_the_cronjob` keeps the expressions | `[default]` fails: `assert False is ('default' in ('default', 'true'))`; `[quoted false]` fails: `assert True is …`; `test_the_two_rules_watch_the_cronjob` fails: `KeyError: 'GroupSyncDashboardOffsiteBackupStale'` | passes |
| T304-13 | `test_offsite_backup_script.py::TestPreUpgradePass::test_the_newest_copy_ships_verified_and_three_are_kept` (five copies over five runs; the newest of each run shipped, its sidecar equal to the store's, three kept); `test_a_copy_the_store_wrote_ships_and_checks` (a copy written by `gsd.store._pre_upgrade_copy` itself, shipped, then `--check`: "sidecar matches"); `test_chart_backup_offsite.py::TestPvcDestination::test_the_newest_pre_upgrade_copy_ships_too_at_one_replica` | the script tests fail: `SystemExit: 2` (argparse: the option does not exist); the chart test fails: `expected one CronJob named *-backup-offsite, found 0` | passes |
| T304-14 | `TestPreUpgradePass::test_the_six_hourly_pass_is_unchanged_beside_it` (the same files in `/offsite` with and without the second pass, `--keep 2`, and no `pre-upgrade-*` among them); and the existing `test_pre_upgrade_copy.py::test_the_six_hourly_backups_do_not_see_the_copy` (SPEC_M1 §3.2: `newest_backup` unchanged) | the new test fails only because the option is new (`SystemExit: 2`); the existing test passes before and after | passes |
| T304-15 | `test_values_defaults.py::test_the_only_false_defaults_are_the_stated_exceptions`, `::test_no_current_doc_tells_the_operator_to_enable_a_default` | fails: `unexpected false defaults: ['backup.offsite.enabled']`; `('charts/group-sync-dashboard/README.md', 'backup.offsite.enabled')` (the row says `false`) | passes |
| T304-16 | `test_chart_pdb.py::TestThePdbSelectsTheDeploymentOnly::test_the_selector_matches_the_dashboard_pod_and_no_hook_pod`, widened from the Jobs to every Job and CronJob pod template | fails: `['t-group-sync-dashboard-secrets-mint']` (the offsite bind Job and CronJob are not there to check) | passes: the components are `backup-offsite`, `backup-offsite`, `secrets-mint`, none matched by the budget |
| T304-17 | `TestSwitch::test_the_serviceaccount_has_no_token_and_no_grant`, now on the default render; and the RBAC diff of §2.6 | fails: `expected one ServiceAccount named *-backup-offsite, found 0`; the diff is a measurement | passes; `REMOVED 0`, `ADDED 0` by default and with `environments/crc.yaml` |
| T304-18 | the 18 of §2.6, each an expectation update: the two offsite tests are replaced by T304-1 and T304-12; `test_chart_route.py` sets the offsite account aside (blocks 34, 35; nine tests); `test_chart_reporting.py` names the report CronJob and checks both CronJobs against both budgets (blocks 31-33; three tests); `test_chart_pdb.py` is T304-16; `test_values_defaults.py` is T304-15 (two tests); `test_chart_strategy.py::TestStillRenders::test_rollingupdate_at_one_replica_without_persistence` is unchanged and passes because the default yields with persistence off | on a copy with only the default flipped to `true`: 18 failed (§2.6) | all pass |
| T304-19 | the lab walk, §5 | the lab has no offsite CronJob (§2.7) | the implementing pull request |

**Added by the research and the review** (all in the same two files):

| test | what it holds | before | after |
|---|---|---|---|
| `TestYield::test_the_offsite_stanzas_own_mistakes_are_refused_in_the_default_too` | Orchestrator's notes, 3: a destination value set by hand is refused, not yielded | fails: `assert (not True)`, offsite is off and the render succeeds | passes |
| `TestTheSwitchIsAWord::test_a_quoted_word_means_what_it_says[true-True]`, `[-True]` | `"true"` is on; an empty string is the default | `[-True]` fails: `assert (False is True)` | passes |
| `TestTheSwitchIsAWord::test_a_values_file_reads_the_same[no, off, yes, (empty)]` | §2.2: YAML 1.1 booleans and a null, through a values file (`-f`) | `[-True]` (an empty value, the null) fails: `assert False is True` | passes |
| `TestS3Destination::test_verify_then_upload_in_two_containers` (one line added) | the `s3` stage carries no pre-upgrade argument (Orchestrator's notes, 4) | passes | passes |
| `TestPreUpgradePass::test_no_copy_yet_is_not_a_failure[absent, empty]` | a new install, and an emptied directory, ship nothing and succeed | `SystemExit: 2` | passes |
| `TestPreUpgradePass::test_a_copy_that_no_longer_matches_its_sidecar_is_refused` | Orchestrator's notes, 5; and the six-hourly pass still ships | `SystemExit: 2` | passes |
| `TestPreUpgradePass::test_a_failing_six_hourly_pass_does_not_stop_the_pre_upgrade_pass` | §3.6: independent passes, exit 1 | `SystemExit: 2` | passes |
| `TestPreUpgradePass::test_the_names_and_the_count_are_the_stores` | `PRE_UPGRADE_KEEP`, `PRE_UPGRADE_DIR` and the pattern equal to the store's | `AttributeError: module 'offsite_backup' has no attribute 'PRE_UPGRADE_KEEP'` | passes |
| `TestAlerts::test_a_refused_pre_upgrade_copy_is_named_by_the_alert_and_the_runbook` | Orchestrator's notes, 9 (the review's N1): the stale alert's description names a refused pre-upgrade copy and no longer says "nothing newer is off it."; runbook §2 says how to clear it | fails: `KeyError: 'GroupSyncDashboardOffsiteBackupStale'`; against the first cut of §7 (`4dfde5e6`): `assert ('pre-upgrade copy is refused' in "t-group-sync-dashboard-backup-offsite last succeeded …")` | passes |

Counts, the seven touched chart and script files (`tests/test_offsite_backup_script.py tests/test_chart_backup_offsite.py
tests/test_values_defaults.py tests/test_chart_pdb.py tests/test_chart_reporting.py tests/test_chart_route.py
tests/test_chart_strategy.py`): before `28 failed, 307 passed`; after `335 passed`.

### 4.2 Each new behaviour fails without its line

Ten mutations of the implemented tree, each a copy with one change, running `tests/test_chart_backup_offsite.py` and
`tests/test_offsite_backup_script.py` (105 tests). Measured on the first cut (`4dfde5e6`); the review changed none of
the lines they mutate, and OB3 re-ran M1, M2, M5, M6 and M8 with the same results:

| run | the change | result | tests that go red |
|---|---|---|---|
| M1 | the two alerts back on truthiness (`if .Values.backup.offsite.enabled` in `monitoring.yaml`) | 5 failed | `test_a_quoted_word_means_what_it_says[false-False]` and `[-True]`, T304-12 `[default]` and `[quoted false]`, `test_the_two_rules_watch_the_cronjob` |
| M2 | the word read through `default` (`toString ($raw \| default "")`) | 4 failed | `test_false_is_off`, `test_a_values_file_reads_the_same[no-False]` and `[off-False]`, T304-12 `[false]` |
| M3 | no `ReadWriteOncePod` condition in the blocker | 4 failed | `TestYield` `[derived ReadWriteOncePod]` both ways, `test_rwop_is_refused`, T304-12 `[derived ReadWriteOncePod]` |
| M4 | the CronJob's file back on truthiness | 10 failed | T304-1, T304-17's account test, the stanza test, the quoted and values-file `"false"`/empty cases, the pre-upgrade argument, T304-12 `[default]` and `[quoted false]` |
| M5 | any other word taken as on | 4 failed | `test_any_other_word_is_refused_naming_the_three[yes, ture, 0, False]` |
| M6 | no check against the store's sidecar | 1 failed | `test_a_copy_that_no_longer_matches_its_sidecar_is_refused` |
| M7 | the second pass skipped when the first fails | 1 failed | `test_a_failing_six_hourly_pass_does_not_stop_the_pre_upgrade_pass` |
| M8 | the pre-upgrade copies shipped into `/offsite` itself | 5 failed | the five `TestPreUpgradePass` tests that read `/offsite/pre-upgrade` |
| M9 | no `--pre-upgrade-source` argument in the CronJob | 1 failed | `test_the_newest_pre_upgrade_copy_ships_too_at_one_replica` |
| M10 | `PRE_UPGRADE_KEEP = 14` | 2 failed | `test_the_newest_copy_ships_verified_and_three_are_kept`, `test_the_names_and_the_count_are_the_stores` |

### 4.3 The proof

§7 was not written by hand. The design was implemented in a detached worktree of this branch's merge of origin/main
`3b3d0010` (`547a68ad`: SPEC G1, E2, G2 and E4 merged, and this spec's first cut); a generator cut each block's Old
text from that merge and its New text from the implemented copy, at whole lines, with no code fence inside a block,
each Old unique in its file as the earlier blocks leave it and preferring leading context, and checked that each
file's blocks, applied in order, give the implemented file byte for byte: `41 blocks across 20 files reproduce the
implemented files byte for byte`. Then, on a fresh detached worktree of `547a68ad`:

    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E5_offsite_on_by_default.md .
    41 blocks check out across 20 files
    python3 local-development/apply-spec-blocks.py docs/specs/SPEC_E5_offsite_on_by_default.md . --apply

After `--apply` every changed file is identical (`cmp`) to the implemented copy. On that tree, with `PYTHONPATH`
at its `local-development` (the imported `gsd` printed as that tree's):

| check | command | result |
|---|---|---|
| the issue's six chart test files and the script and copy tests | `pytest -q -p no:cacheprovider tests/test_chart_*.py tests/test_values_defaults.py tests/test_offsite_backup_script.py tests/test_pre_upgrade_copy.py tests/test_kyverno.py tests/test_ci_charts.py` | `547a68ad`: `497 passed, 3 skipped`; applied: `546 passed, 3 skipped` |
| hermetic suite | `pytest tests/ -q -p no:cacheprovider --deselect tests/test_ui.py --deselect tests/test_live_smoke.py` | applied on `547a68ad` (main `3b3d0010` with this spec): `6346 passed, 26 skipped, 655 deselected, 5 xfailed`, no failure; the version ladder test included |
| the version ladder (Orchestrator's notes, Version note) | `pytest tests/test_specs_index.py` on a copy with every block but 36 to 39 applied | `1 failed, 85 passed`: `AssertionError: ('E2', 'chart 0.60.0 (chart only)', 'Chart.yaml is already 0.60.0')`; with them, passes in the hermetic suite above |
| this spec's index row and citations | `pytest -q tests/test_specs_index.py tests/test_docs_citations.py`, in the spec's branch | `1612 passed, 22 skipped`; 37 of the citation checks are this spec's, none skipped |
| chart | `helm lint`; the render matrix of §2.6 | lint clean; the matrix on the applied chart equals the first cut's and reads as §3.1 and §3.2 say: the default renders the five objects and two alerts with the pre-upgrade argument; `false`, `"false"` and the seven yield cases render nothing of offsite; `"yes"` is refused naming the three values; `true` keeps the five refusals; the four stanza refusals apply by default too; at `replicaCount` 2 the CronJob renders without the pre-upgrade argument |
| the strict messages | the six `true + …` renders on `547a68ad` and on the applied chart, the error line compared as a string | the same message in all six |
| RBAC | `reports/2026-09-27_epic-c-walk/scripts/rbac_rules.py`, default values and `environments/crc.yaml` | `rules: before 59, after 59`, `REMOVED 0`, `ADDED 0`; `rules: before 65, after 65`, `REMOVED 0`, `ADDED 0`; bindings 7 and 7, 8 and 8, none added or removed |
| markdown | `markdownlint-cli2` on the runbook, the CHANGELOG, the reference architecture and the chart README | 30 findings before and after, the same per file and rule (MD004, MD012, MD014, MD040), all on main already |
| Python 3.11 | `ast.parse(source, feature_version=(3, 11))` on the script and the six test files | all parse; CI's 3.11 job was not run here |

**Composition with SPEC_E2** (Orchestrator's notes, 1). SPEC_E2 as merged on main, with its `Chart.yaml` block left
out (that block is the version collision of the header, settled at implementation), applied in both orders on
copies of `547a68ad`, then both specs' chart and script tests (`tests/test_chart_recovery_mode.py
tests/test_recovery_mode.py` and the seven files of §4.1):

| order | E2's line | result |
|---|---|---|
| this spec, then E2 | changed to call `gsd.offsiteOn` | `391 passed` |
| this spec, then E2 | as E2 writes it | `1 failed, 390 passed`: `test_the_offsite_claim_is_mounted_exactly_when_the_cronjob_writes_one[default]` |
| E2, then this spec plus the interlock block | changed by the interlock block | `391 passed` |
| E2, then this spec | as E2 writes it | `1 failed, 390 passed`: the same test |

Every block of both specs applied cleanly in both orders.

## 5. On the lab (the implementing pull request)

Not run in this phase: the lab is read-only here. The implementing pull request deploys the reviewed head with
`local-development/release-crc.sh --argocd` (development: the lab's own release path) and walks it. The
release's values (`environments/crc.yaml`) set nothing under `backup`, so the lab gets the default; after PR
#522 they set `enabled: true` with the `pvc` destination, which renders the same objects (Orchestrator's notes, 12).

1. **Before.** Record the UIDs: `oc get pvc -n group-sync-dashboard -o custom-columns=NAME:.metadata.name,UID:.metadata.uid`
   must show `group-sync-dashboard-data` `f065b7a4-535c-4ef1-868c-58f5afee4953` and
   `group-sync-dashboard-report-artifacts` `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` (§2.3).
2. **Deploy**, then read the objects: `oc get cronjobs.batch,configmap,serviceaccount -n group-sync-dashboard -l app.kubernetes.io/component=backup-offsite`
   lists one of each; `oc get pvc group-sync-dashboard-backup-offsite -n group-sync-dashboard` is `Bound` on
   `crc-csi-hostpath-provisioner`, 5Gi, with `helm.sh/resource-policy: keep` and the Argo sync options. Under Argo
   CD the bind Job is a Sync hook deleted on success, so its evidence is the claim `Bound` and the Application
   `Synced Healthy` (`oc get applications.argoproj.io -A`). Record the new claim's UID.
3. **The alert before the first run.** In the Thanos querier,
   `absent(kube_cronjob_status_last_successful_time{namespace="group-sync-dashboard",cronjob="group-sync-dashboard-backup-offsite"})`
   returns 1 (the rule's expression), and `GroupSyncDashboardOffsiteBackupUnobserved` is pending or firing.
4. **A manual run.** `oc create job -n group-sync-dashboard --from=cronjob/group-sync-dashboard-backup-offsite manual-<stamp>`,
   then `oc logs -n group-sync-dashboard -l job-name=manual-<stamp>`: `copied /data/backup/gsd-….db ->
   /offsite/gsd-….db`, `integrity_check ok; user_version <the database schema>; …`, `pruned 0 older copies (keep=14)`, and
   `no pre-upgrade-*.db under /data/pre-upgrade: nothing to ship …` (the lab has no pre-upgrade copy, §2.7).
   The Job completes.
5. **The copy verifies.** Runbook §1's `--check` on `/offsite/gsd-….db` (the CronJob's pod spec with the
   command replaced): `integrity_check ok`, `sidecar matches`.
6. **The alert clears.** `kube_cronjob_status_last_successful_time{…}` has a series (the manual Job is owned by
   the CronJob and succeeded, §2.4) and `GroupSyncDashboardOffsiteBackupUnobserved` is no longer firing.
7. **After.** The two UIDs of step 1, unchanged.

The pre-upgrade copy's shipping is held by the tests of §4.1 (T304-13 runs the store's own copy through the
pass); on the lab it ships after the first application release that migrates the schema, and the implementing
pull request records whether one exists at walk time. Creating one on the lab (a lab-only image with a no-op
migration, as SPEC_M1 §5 describes) is not part of this walk.

## 6. What an operator sees, and what it costs

- **A release that sets nothing**, on its next rollout through its pipeline: a 5Gi claim
  `<fullname>-backup-offsite` on the cluster's default class, a bind Job for a few seconds, a CronJob at
  `15 */6 * * *`, its ConfigMap and grant-less account, and two alerts; `…Unobserved` fires until the first
  successful run and clears after it. Every six hours the newest six-hourly copy, and at one replica the newest
  pre-upgrade copy, leave the volume, verified, with the newest 14 and 3 kept.
- **A release where the copy cannot work** (persistence off, backups off, a dir outside `/data/`, an existing
  claim without its mode, `ReadWriteOncePod`): nothing new, and no error.
- **A release that set `true`:** the same as before, refusals and messages included, plus the pre-upgrade copy.
- **A release that set `false`, or `"false"`:** nothing. Before this change a quoted `"false"` rendered the
  CronJob.
- **A release with an invalid `backup.offsite.destination.*` value left over while offsite was off:** the render
  now fails with that value's message; set `backup.offsite.enabled: false` in the values file, or fix the value.
- **Space:** about 264 MiB of the 5Gi claim at the lab's sizes (§3.7).
- **Code:** lines added and removed by §7, from `git diff --numstat` on the applied tree:

| file | added | removed |
|---|---|---|
| `charts/group-sync-dashboard/scripts/offsite_backup.py` | 56 | 17 |
| `charts/group-sync-dashboard/templates/_helpers.tpl` | 42 | 0 |
| `charts/group-sync-dashboard/templates/backup-offsite.yaml` | 15 | 19 |
| `charts/group-sync-dashboard/templates/monitoring.yaml` | 5 | 3 |
| `charts/group-sync-dashboard/values.yaml` | 25 | 8 |
| `charts/group-sync-dashboard/README.md` | 19 | 9 |
| `charts/group-sync-dashboard/Chart.yaml` | 4 | 1 |
| `charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md` | 20 | 5 |
| `docs/guides/reference-architecture.md` | 10 | 4 |
| `docs/CHANGELOG.md` | 24 | 0 |
| `docs/specs/README.md`, `SPEC_E2_recovery_mode.md`, `SPEC_G2_platform_users.md`, `SPEC_E4_per_pod_backup_rotation.md` (version cells) | 6 | 6 |
| `local-development/tests/test_chart_backup_offsite.py` | 138 | 16 |
| `local-development/tests/test_offsite_backup_script.py` | 106 | 1 |
| `local-development/tests/test_values_defaults.py` | 10 | 2 |
| `local-development/tests/test_chart_pdb.py` | 9 | 6 |
| `local-development/tests/test_chart_reporting.py` | 8 | 5 |
| `local-development/tests/test_chart_route.py` | 4 | 4 |

## 7. Implementation blocks

Applied in this order: the script (1-5), the templates (6-9a), `values.yaml` (10), the documents (11-19a), the tests (20-35), the version cells of the four other specs this chart version reaches (37-39c), the CHANGELOG (40) and the chart version (41). Every block is an edit; no file is created. Blocks 9a, 14 and 36 to 41 were re-cut at implementation (Orchestrator's notes, 12).

### Block 1 — charts/group-sync-dashboard/scripts/offsite_backup.py

The docstring names the second pass (§3.6).

<!-- block: charts/group-sync-dashboard/scripts/offsite_backup.py | edit -->

Old text:

```python
  5. prune --dest to --keep copies (0 keeps everything), sidecars with their copies.
```

New text:

```python
  5. prune --dest to --keep copies (0 keeps everything), sidecars with their copies.

With --pre-upgrade-source, a second pass does the same for the newest pre-upgrade-*.db the store
writes beside the database before a migration (#301), into <dest>/pre-upgrade, keeping
PRE_UPGRADE_KEEP, and refuses a copy whose bytes no longer match the sidecar the store wrote. The two
passes are independent: a failure in one does not stop the other, and either fails the run (#304).
```

### Block 2 — charts/group-sync-dashboard/scripts/offsite_backup.py

The pre-upgrade constants, equal to the store's, and `newest_backup` takes the pattern (default: today's).

<!-- block: charts/group-sync-dashboard/scripts/offsite_backup.py | edit -->

Old text:

```python
PATTERN = "gsd-*.db"
SIDECAR_LINE = re.compile(r"([0-9A-Fa-f]{64})[ \t]+(.+?)\r?\n?")
PART_SUFFIX = ".part"
SUM_SUFFIX = ".sha256"
HISTORY_TABLES = ("membership_event", "sync_event")


class BackupError(Exception):
    """A failure the operator must see. Every one exits non-zero with its message."""


def newest_backup(source: Path) -> Path:
    if not source.is_dir():
        raise BackupError(
            f"source {source} is not a directory — is config.backup.dir mounted here, "
            f"and is config.backup.enabled on?"
        )
    candidates = sorted(p for p in source.glob(PATTERN) if p.is_file())
    if not candidates:
        raise BackupError(
            f"no {PATTERN} under {source}: the dashboard has not written a backup yet "
```

New text:

```python
PATTERN = "gsd-*.db"
#: The pre-upgrade copies (#301): beside the database, outside PATTERN, the newest by name. Kept to the
#: count the store keeps on the volume (gsd/store.py PRE_UPGRADE_KEEP; a test holds the two equal).
PRE_UPGRADE_PATTERN = "pre-upgrade-*.db"
PRE_UPGRADE_DIR = "pre-upgrade"
PRE_UPGRADE_KEEP = 3
SIDECAR_LINE = re.compile(r"([0-9A-Fa-f]{64})[ \t]+(.+?)\r?\n?")
PART_SUFFIX = ".part"
SUM_SUFFIX = ".sha256"
HISTORY_TABLES = ("membership_event", "sync_event")


class BackupError(Exception):
    """A failure the operator must see. Every one exits non-zero with its message."""


def newest_backup(source: Path, pattern: str = PATTERN) -> Path:
    if not source.is_dir():
        raise BackupError(
            f"source {source} is not a directory — is config.backup.dir mounted here, "
            f"and is config.backup.enabled on?"
        )
    candidates = sorted(p for p in source.glob(pattern) if p.is_file())
    if not candidates:
        raise BackupError(
            f"no {pattern} under {source}: the dashboard has not written a backup yet "
```

### Block 3 — charts/group-sync-dashboard/scripts/offsite_backup.py

`prune` and `ship` take the pattern; `ship` checks the store's sidecar when the second pass asks it to (Orchestrator's notes, 5).

<!-- block: charts/group-sync-dashboard/scripts/offsite_backup.py | edit -->

Old text:

```python

def prune(dest: Path, keep: int) -> int:
    """Store.backup's rule: sorted(glob)[:-keep] goes. 0 keeps everything. Sidecars follow their
    copies; a sidecar whose copy is gone, and any .part a killed run left, go too (review of B1)."""
    for transient in (*dest.glob(PATTERN + PART_SUFFIX), *dest.glob(PATTERN + SUM_SUFFIX + PART_SUFFIX)):
        transient.unlink(missing_ok=True)
    copies = sorted(p for p in dest.glob(PATTERN) if p.is_file())
    victims = copies[:-keep] if keep > 0 else []
    for stale in victims:
        stale.unlink()
        stale.with_name(stale.name + SUM_SUFFIX).unlink(missing_ok=True)
    for orphan in dest.glob(PATTERN + SUM_SUFFIX):
        if not orphan.with_name(orphan.name[: -len(SUM_SUFFIX)]).is_file():
            orphan.unlink(missing_ok=True)
    return len(victims)


REPICK_ATTEMPTS = 3


def ship(source: Path, dest: Path, keep: int) -> int:
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError(f"destination {dest} is not writable: {exc}") from exc
    if dest.resolve() == source.resolve():
        raise BackupError(f"destination {dest} IS the source directory — that is not off the volume")
    # A SIGKILL mid-copy skips `finally`; whatever .part a killed run left is not a copy and goes now.
    prune(dest, 0)

    # The app writes backups on its own timer (Store.backup), so the newest file can change while
    # this one is being copied — the picked file stays readable through its open descriptor, and
    # the copy is still a verified backup, one interval old. Re-pick a bounded number of times so
    # the destination ends the run holding the newest; past that, keep the verified copy and say so
    # in the log rather than chase a source that keeps moving (review of B1, both passes).
    for attempt in range(1, REPICK_ATTEMPTS + 1):
        newest = newest_backup(source)
        target = dest / newest.name
        sidecar = dest / (newest.name + SUM_SUFFIX)
        if target.exists() and sidecar.exists():
            expected = sidecar_expected(sidecar, newest.name)
            if expected is not None and sha256_of(target) == expected:
                print(f"already shipped: {target} matches its sidecar; nothing to copy")
                break
            print(f"{target} exists but does not match its sidecar; copying again", file=sys.stderr)

        part = dest / (newest.name + PART_SUFFIX)
        sidecar_part = dest / (newest.name + SUM_SUFFIX + PART_SUFFIX)
        published = False
        try:
            source_digest, size = copy_hashed(newest, part)
```

New text:

```python

def prune(dest: Path, keep: int, pattern: str = PATTERN) -> int:
    """Store.backup's rule: sorted(glob)[:-keep] goes. 0 keeps everything. Sidecars follow their
    copies; a sidecar whose copy is gone, and any .part a killed run left, go too (review of B1)."""
    for transient in (*dest.glob(pattern + PART_SUFFIX), *dest.glob(pattern + SUM_SUFFIX + PART_SUFFIX)):
        transient.unlink(missing_ok=True)
    copies = sorted(p for p in dest.glob(pattern) if p.is_file())
    victims = copies[:-keep] if keep > 0 else []
    for stale in victims:
        stale.unlink()
        stale.with_name(stale.name + SUM_SUFFIX).unlink(missing_ok=True)
    for orphan in dest.glob(pattern + SUM_SUFFIX):
        if not orphan.with_name(orphan.name[: -len(SUM_SUFFIX)]).is_file():
            orphan.unlink(missing_ok=True)
    return len(victims)


REPICK_ATTEMPTS = 3


def ship(source: Path, dest: Path, keep: int, pattern: str = PATTERN, *, require_source_sidecar: bool = False) -> int:
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise BackupError(f"destination {dest} is not writable: {exc}") from exc
    if dest.resolve() == source.resolve():
        raise BackupError(f"destination {dest} IS the source directory — that is not off the volume")
    # A SIGKILL mid-copy skips `finally`; whatever .part a killed run left is not a copy and goes now.
    prune(dest, 0, pattern)

    # The app writes backups on its own timer (Store.backup), so the newest file can change while
    # this one is being copied — the picked file stays readable through its open descriptor, and
    # the copy is still a verified backup, one interval old. Re-pick a bounded number of times so
    # the destination ends the run holding the newest; past that, keep the verified copy and say so
    # in the log rather than chase a source that keeps moving (review of B1, both passes).
    for attempt in range(1, REPICK_ATTEMPTS + 1):
        newest = newest_backup(source, pattern)
        target = dest / newest.name
        sidecar = dest / (newest.name + SUM_SUFFIX)
        if target.exists() and sidecar.exists():
            expected = sidecar_expected(sidecar, newest.name)
            if expected is not None and sha256_of(target) == expected:
                print(f"already shipped: {target} matches its sidecar; nothing to copy")
                break
            print(f"{target} exists but does not match its sidecar; copying again", file=sys.stderr)

        part = dest / (newest.name + PART_SUFFIX)
        sidecar_part = dest / (newest.name + SUM_SUFFIX + PART_SUFFIX)
        published = False
        try:
            source_digest, size = copy_hashed(newest, part)
            if require_source_sidecar:
                # The store writes this sidecar before the copy takes its name (#301): bytes that no longer
                # match it changed on the volume, and a fresh sidecar here would vouch for them.
                recorded = sidecar_expected(newest.with_name(newest.name + SUM_SUFFIX), newest.name)
                if recorded != source_digest:
                    raise BackupError(f"{newest}: the bytes read hash to {source_digest}, but its sidecar on the "
                                      f"volume records {recorded or 'no digest'}; it is not the copy the store verified")
```

### Block 4 — charts/group-sync-dashboard/scripts/offsite_backup.py

The re-pick and the prune use the pass's pattern; `ship_pre_upgrade`, the second pass, succeeds with nothing to ship when no copy exists yet.

<!-- block: charts/group-sync-dashboard/scripts/offsite_backup.py | edit -->

Old text:

```python
        try:
            later = newest_backup(source)
        except BackupError:
            later = newest
        # Re-pick only when the name moved FORWARD: if the picked file vanished and an older one
        # is now the newest, the copy just published is the most recent this run saw.
        if later.name <= newest.name:
            break
        if attempt < REPICK_ATTEMPTS:
            print(f"note: {later.name} landed during the copy; shipping it too (attempt {attempt + 1})")
        else:
            print(f"note: {later.name} landed during the copy; it ships on the next run")

    removed = prune(dest, keep)
    print(f"pruned {removed} older cop{'y' if removed == 1 else 'ies'} (keep={keep})")
    return 0
```

New text:

```python
        try:
            later = newest_backup(source, pattern)
        except BackupError:
            later = newest
        # Re-pick only when the name moved FORWARD: if the picked file vanished and an older one
        # is now the newest, the copy just published is the most recent this run saw.
        if later.name <= newest.name:
            break
        if attempt < REPICK_ATTEMPTS:
            print(f"note: {later.name} landed during the copy; shipping it too (attempt {attempt + 1})")
        else:
            print(f"note: {later.name} landed during the copy; it ships on the next run")

    removed = prune(dest, keep, pattern)
    print(f"pruned {removed} older cop{'y' if removed == 1 else 'ies'} (keep={keep})")
    return 0


def ship_pre_upgrade(source: Path, dest: Path) -> int:
    """The second pass (#304; SPEC_M1 §3.8): the newest pre-upgrade copy, checked against the sidecar the
    store wrote, into its own directory. No copy is not a failure: the store takes one only when an image
    upgrades the schema, so a new install has none."""
    if not source.is_dir() or not any(p.is_file() for p in source.glob(PRE_UPGRADE_PATTERN)):
        print(f"no {PRE_UPGRADE_PATTERN} under {source}: nothing to ship (one is written only when an image "
              f"upgrades the schema)")
        return 0
    return ship(source, dest, PRE_UPGRADE_KEEP, PRE_UPGRADE_PATTERN, require_source_sidecar=True)
```

### Block 5 — charts/group-sync-dashboard/scripts/offsite_backup.py

`--pre-upgrade-source`; the two passes run independently and either fails the run; `run_pass` prints the reason.

<!-- block: charts/group-sync-dashboard/scripts/offsite_backup.py | edit -->

Old text:

```python
    parser.add_argument("--check", type=Path, metavar="FILE", help="verify one copy and exit")
    args = parser.parse_args(argv)
    try:
        if args.check is not None:
            return check(args.check)
        if args.source is None or args.dest is None:
            parser.error("--source and --dest are required unless --check is given")
        return ship(args.source, args.dest, args.keep)
```

New text:

```python
    parser.add_argument("--check", type=Path, metavar="FILE", help="verify one copy and exit")
    parser.add_argument("--pre-upgrade-source", type=Path, metavar="DIR",
                        help=f"also ship the newest {PRE_UPGRADE_PATTERN} under DIR to <dest>/{PRE_UPGRADE_DIR}, "
                             f"keeping {PRE_UPGRADE_KEEP}")
    args = parser.parse_args(argv)
    if args.check is not None:
        return run_pass(lambda: check(args.check))
    if args.source is None or args.dest is None:
        parser.error("--source and --dest are required unless --check is given")
    status = run_pass(lambda: ship(args.source, args.dest, args.keep))
    if args.pre_upgrade_source is not None:
        status |= run_pass(lambda: ship_pre_upgrade(args.pre_upgrade_source, args.dest / PRE_UPGRADE_DIR))
    return status


def run_pass(step) -> int:
    """One pass: its return code, or 1 with the reason on stderr."""
    try:
        return step()
```

### Block 6 — charts/group-sync-dashboard/templates/_helpers.tpl

`gsd.offsiteBlocker` (the five conditions, today's messages) and `gsd.offsiteOn` (the word, the yield), after `gsd.accessMode`, which the blocker calls (§3.1, §3.2).

<!-- block: charts/group-sync-dashboard/templates/_helpers.tpl | edit -->

Old text:

```text
{{- define "gsd.accessMode" -}}
{{- if .Values.persistence.accessMode -}}
{{- .Values.persistence.accessMode -}}
{{- else if gt (int .Values.replicaCount) 1 -}}
ReadWriteMany
{{- else -}}
ReadWriteOncePod
{{- end -}}
{{- end -}}
```

New text:

```text
{{- define "gsd.accessMode" -}}
{{- if .Values.persistence.accessMode -}}
{{- .Values.persistence.accessMode -}}
{{- else if gt (int .Values.replicaCount) 1 -}}
ReadWriteMany
{{- else -}}
ReadWriteOncePod
{{- end -}}
{{- end -}}

# ── Off-volume backup ─────────────────────────────────────────────────────────────────────
# gsd.offsiteBlocker: the first of the five conditions under which the offsite CronJob cannot work,
# as the message an explicit `backup.offsite.enabled: true` refuses the render with; empty when none
# holds. The default ("") yields on exactly these five. The offsite stanza's own values (destination
# type, claim, keep, S3 Secret and image) are refused in backup-offsite.yaml in every state.
# config.backup.dir is read as a word: a values file's `dir:` with no value is a null (the key removed),
# which the ConfigMap already hands the app as "" (backups disabled) but `hasPrefix` cannot read. Nil
# becomes "", so that release yields by default and `true` refuses it as the empty dir, never with a
# type error (review of E5, OB2).
{{- define "gsd.offsiteBlocker" -}}
{{- $dir := ternary "" (toString .Values.config.backup.dir) (kindIs "invalid" .Values.config.backup.dir) -}}
{{- if not .Values.persistence.enabled -}}
backup.offsite.enabled=true requires persistence.enabled=true. With an emptyDir there is no volume to ship a backup off, and the history it would protect resets on every restart anyway.
{{- else if not .Values.config.backup.enabled -}}
backup.offsite.enabled=true requires config.backup.enabled=true. The CronJob ships the VACUUM INTO files the dashboard writes under config.backup.dir; with that off there is nothing to ship, and copying the live gsd.db with its WAL would produce a torn file that opens and restores — the worst kind of backup.
{{- else if or (not (hasPrefix "/data/" $dir)) (contains ".." $dir) -}}
{{- printf "backup.offsite.enabled=true requires config.backup.dir under /data/ with no '..' (it is %q). The CronJob mounts the data claim at /data, read-only, and reads the backups from there." $dir -}}
{{- else if and .Values.persistence.existingClaim (not .Values.persistence.accessMode) -}}
backup.offsite.enabled=true with persistence.existingClaim requires persistence.accessMode set to that claim's access mode: helm cannot read the live claim, and an emptied accessMode derives ReadWriteOncePod or ReadWriteMany from replicaCount, which may not be what the claim was created with. ReadWriteOncePod is refused either way.
{{- else if eq (include "gsd.accessMode" .) "ReadWriteOncePod" -}}
backup.offsite.enabled=true cannot work with a ReadWriteOncePod data volume: that mode lets exactly ONE pod mount the claim, so the CronJob pod would stay Pending forever. Set persistence.accessMode to ReadWriteOnce (the CronJob is then pinned to the dashboard's node by podAffinity) or ReadWriteMany. accessModes are immutable on an existing claim — charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md covers moving the data to a new one.
{{- end -}}
{{- end -}}

# gsd.offsiteOn: backup.offsite.enabled read as a WORD, never by truthiness. "true" or "false":
#   ""     (the default) on wherever the copy can work, off with no error where it cannot;
#   true   on, and backup-offsite.yaml refuses each blocker by name;
#   false  off.
# A template `if` takes the string "false" as true and "" as false, and Sprig's `default` takes an
# explicit false as empty, so the value is printed and compared. A boolean prints as its word; YAML
# 1.1's yes/no/on/off arrive as booleans; a null removes the key, which is the default. Any other
# word refuses the render. Everything that must follow the CronJob calls this one helper: the
# CronJob's objects, its two alerts (monitoring.yaml), the recovery pod's offsite mount (SPEC_E2).
{{- define "gsd.offsiteOn" -}}
{{- $raw := .Values.backup.offsite.enabled -}}
{{- $word := ternary "" (toString $raw) (kindIs "invalid" $raw) -}}
{{- if eq $word "true" -}}
true
{{- else if eq $word "false" -}}
false
{{- else if eq $word "" -}}
{{- ternary "true" "false" (eq (include "gsd.offsiteBlocker" .) "") -}}
{{- else -}}
{{- fail (printf "backup.offsite.enabled is %q, which is not one of its three values: empty (\"\", the default: on wherever the off-volume copy can work, and nothing where it cannot), true (on, and the render refuses a combination that cannot work) or false (off). Set one of them in this release's values file and roll it out through the release's deployment pipeline." $word) -}}
{{- end -}}
{{- end -}}
```

### Block 7 — charts/group-sync-dashboard/templates/backup-offsite.yaml

The header names the three states; the file renders when `gsd.offsiteOn` says so, and refuses the blocker under `true`; the five inline guards move to the helper (§3.2).

<!-- block: charts/group-sync-dashboard/templates/backup-offsite.yaml | edit -->

Old text:

```yaml
Off-volume backup: the other half of config.backup. See values.yaml under `backup:` for the
decisions; this file models the interactions and renders, when enabled, a ServiceAccount, a
ConfigMap and a CronJob — plus the destination claim and its one-shot bind Job when the chart
creates that claim (five objects), none of those two for an existing claim or S3 (three).

The `backup.enabled` guard is OUTSIDE the enabled block on purpose: the mistake it catches is
setting the wrong key and seeing nothing render.
*/}}
{{- if hasKey .Values.backup "enabled" }}
{{- fail "backup.enabled is not a value. The on-volume backup the dashboard takes is config.backup.enabled (on by default); the off-volume CronJob is backup.offsite.enabled. A key that silently did nothing here would look like a backup that was configured." }}
{{- end }}
{{- if .Values.backup.offsite.enabled }}
{{- $o := .Values.backup.offsite }}
{{- $mode := include "gsd.accessMode" . }}
{{- $type := $o.destination.type }}
{{- $fullname := include "gsd.fullname" . }}
{{- $dataClaim := .Values.persistence.existingClaim | default (printf "%s-data" $fullname) }}
{{- $createsClaim := and (eq $type "pvc") (not $o.destination.pvc.existingClaim) }}
{{- /* The bind Job's name carries a hash of what its pod runs with, because a Job's pod template is
immutable: an image or resources change must produce a NEW Job (Helm and Argo then create it and
remove the old one) rather than a patch the API server refuses. */}}
{{- /* Every field that lands in the pod template is hashed — pullPolicy, pullSecrets, the pod and
container security contexts, nodeSelector, tolerations — because a change to any of them with a
stable name is a refused patch, not a no-op; and the chart version, so a change to the template's
fixed content (the command, the mounts) in a new chart also renames the Job (review of B1, second
pass, both reviewers). */}}
{{- $bindHash := printf "%s|%s|%s|%s|%s|%s|%s|%s|%s" .Chart.Version (include "gsd.image" .) .Values.image.pullPolicy (toYaml .Values.image.pullSecrets) (toYaml $o.resources) (toYaml .Values.securityContext) (toYaml .Values.podSecurityContext) (toYaml .Values.nodeSelector) (toYaml .Values.tolerations) | sha256sum | trunc 8 }}
{{- if not .Values.persistence.enabled }}
{{- fail "backup.offsite.enabled=true requires persistence.enabled=true. With an emptyDir there is no volume to ship a backup off, and the history it would protect resets on every restart anyway." }}
{{- end }}
{{- if not .Values.config.backup.enabled }}
{{- fail "backup.offsite.enabled=true requires config.backup.enabled=true. The CronJob ships the VACUUM INTO files the dashboard writes under config.backup.dir; with that off there is nothing to ship, and copying the live gsd.db with its WAL would produce a torn file that opens and restores — the worst kind of backup." }}
{{- end }}
{{- if or (not (hasPrefix "/data/" .Values.config.backup.dir)) (contains ".." .Values.config.backup.dir) }}
{{- fail (printf "backup.offsite.enabled=true requires config.backup.dir under /data/ with no '..' (it is %q). The CronJob mounts the data claim at /data, read-only, and reads the backups from there." .Values.config.backup.dir) }}
{{- end }}
{{- if and .Values.persistence.existingClaim (not .Values.persistence.accessMode) }}
{{- fail "backup.offsite.enabled=true with persistence.existingClaim requires persistence.accessMode set to that claim's access mode: helm cannot read the live claim, and an emptied accessMode derives ReadWriteOncePod or ReadWriteMany from replicaCount, which may not be what the claim was created with. ReadWriteOncePod is refused either way." }}
{{- end }}
{{- if eq $mode "ReadWriteOncePod" }}
{{- fail "backup.offsite.enabled=true cannot work with a ReadWriteOncePod data volume: that mode lets exactly ONE pod mount the claim, so the CronJob pod would stay Pending forever. Set persistence.accessMode to ReadWriteOnce (the CronJob is then pinned to the dashboard's node by podAffinity) or ReadWriteMany. accessModes are immutable on an existing claim — charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md covers moving the data to a new one." }}
{{- end }}
```

New text:

```yaml
Off-volume backup: the other half of config.backup. See values.yaml under `backup:` for the
decisions; this file models the interactions and renders, when on (gsd.offsiteOn: by default
wherever it can work), a ServiceAccount, a ConfigMap and a CronJob — plus the destination claim
and its one-shot bind Job when the chart creates that claim (five objects), none of those two for
an existing claim or S3 (three).

The `backup.enabled` guard is OUTSIDE the enabled block on purpose: the mistake it catches is
setting the wrong key and seeing nothing render.
*/}}
{{- if hasKey .Values.backup "enabled" }}
{{- fail "backup.enabled is not a value. The on-volume backup the dashboard takes is config.backup.enabled (on by default); the off-volume CronJob is backup.offsite.enabled. A key that silently did nothing here would look like a backup that was configured." }}
{{- end }}
{{- if eq (include "gsd.offsiteOn" .) "true" }}
# Only an explicit `true` reaches here with a blocker: the default has already yielded.
{{- with include "gsd.offsiteBlocker" . }}
{{- fail . }}
{{- end }}
{{- $o := .Values.backup.offsite }}
{{- $mode := include "gsd.accessMode" . }}
{{- $type := $o.destination.type }}
{{- $fullname := include "gsd.fullname" . }}
{{- $dataClaim := .Values.persistence.existingClaim | default (printf "%s-data" $fullname) }}
{{- $createsClaim := and (eq $type "pvc") (not $o.destination.pvc.existingClaim) }}
{{- /* The bind Job's name carries a hash of what its pod runs with, because a Job's pod template is
immutable: an image or resources change must produce a NEW Job (Helm and Argo then create it and
remove the old one) rather than a patch the API server refuses. */}}
{{- /* Every field that lands in the pod template is hashed — pullPolicy, pullSecrets, the pod and
container security contexts, nodeSelector, tolerations — because a change to any of them with a
stable name is a refused patch, not a no-op; and the chart version, so a change to the template's
fixed content (the command, the mounts) in a new chart also renames the Job (review of B1, second
pass, both reviewers). */}}
{{- $bindHash := printf "%s|%s|%s|%s|%s|%s|%s|%s|%s" .Chart.Version (include "gsd.image" .) .Values.image.pullPolicy (toYaml .Values.image.pullSecrets) (toYaml $o.resources) (toYaml .Values.securityContext) (toYaml .Values.podSecurityContext) (toYaml .Values.nodeSelector) (toYaml .Values.tolerations) | sha256sum | trunc 8 }}
```

### Block 8 — charts/group-sync-dashboard/templates/backup-offsite.yaml

The `pvc` container ships the newest pre-upgrade copy too, at one replica (§3.6).

<!-- block: charts/group-sync-dashboard/templates/backup-offsite.yaml | edit -->

Old text:

```yaml
                - {{ $o.destination.pvc.keep | quote }}
```

New text:

```yaml
                - {{ $o.destination.pvc.keep | quote }}
                {{- if not (gt (int .Values.replicaCount) 1) }}
                # The newest pre-upgrade copy too, into /offsite/pre-upgrade. At one replica the database
                # is /data/gsd.db and its copies are in /data/pre-upgrade; above one each pod has its own.
                - --pre-upgrade-source
                - /data/pre-upgrade
                {{- end }}
```

### Block 9 — charts/group-sync-dashboard/templates/monitoring.yaml

The two alerts follow the same helper (§3.1, T304-12), and the stale alert's description names both passes: a run fails when either fails (§3.6; the review's N1).

<!-- block: charts/group-sync-dashboard/templates/monitoring.yaml | edit -->

Old text:

```yaml
              pod log for the cause.
        {{- if .Values.backup.offsite.enabled }}

        # The app cannot see its own CronJob, so these two read kube-state-metrics. On
        # OpenShift the platform stack scrapes it for every namespace and user-workload rules
        # are evaluated against the Thanos querier that federates it, so the series is
        # normally visible here. Where kube-state-metrics is absent the second rule fires and
        # stays firing — an alert that could never fire would be indistinguishable from
        # healthy, which is the GroupSyncDashboardNotPolling lesson applied to a Job.
        - alert: GroupSyncDashboardOffsiteBackupStale
          expr: >-
            (time() - max(kube_cronjob_status_last_successful_time{namespace="{{ .Release.Namespace }}",cronjob="{{ include "gsd.fullname" . }}-backup-offsite"}))
              > {{ .Values.monitoring.prometheusRule.offsiteBackupStaleSeconds }}
          for: {{ .Values.monitoring.prometheusRule.for.offsiteBackupStale }}
          labels: {severity: critical}
          annotations:
            summary: "The off-volume backup CronJob has not succeeded within the expected window"
            description: >-
              {{ include "gsd.fullname" . }}-backup-offsite last succeeded
              {{ `{{ $value | humanizeDuration }}` }} ago — at least two schedule slots. The
              on-volume copies still land on the claim they protect; nothing newer is off it.
```

New text:

```yaml
              pod log for the cause.
        {{- if eq (include "gsd.offsiteOn" .) "true" }}

        # Rendered exactly when the offsite CronJob is: one helper decides both.
        # The app cannot see its own CronJob, so these two read kube-state-metrics. On
        # OpenShift the platform stack scrapes it for every namespace and user-workload rules
        # are evaluated against the Thanos querier that federates it, so the series is
        # normally visible here. Where kube-state-metrics is absent the second rule fires and
        # stays firing — an alert that could never fire would be indistinguishable from
        # healthy, which is the GroupSyncDashboardNotPolling lesson applied to a Job.
        - alert: GroupSyncDashboardOffsiteBackupStale
          expr: >-
            (time() - max(kube_cronjob_status_last_successful_time{namespace="{{ .Release.Namespace }}",cronjob="{{ include "gsd.fullname" . }}-backup-offsite"}))
              > {{ .Values.monitoring.prometheusRule.offsiteBackupStaleSeconds }}
          for: {{ .Values.monitoring.prometheusRule.for.offsiteBackupStale }}
          labels: {severity: critical}
          annotations:
            summary: "The off-volume backup CronJob has not succeeded within the expected window"
            description: >-
              {{ include "gsd.fullname" . }}-backup-offsite last succeeded
              {{ `{{ $value | humanizeDuration }}` }} ago — at least two schedule slots. A run
              fails when either of its passes fails: nothing newer is off the volume, or, at one
              replica, the newest pre-upgrade copy is refused while the six-hourly copies still ship.
```

### Block 9a — charts/group-sync-dashboard/templates/deployment.yaml

SPEC_E2 is merged (#518), so its recovery pod's offsite mount takes the same helper as the CronJob (Orchestrator's notes, 1 and 12).

<!-- block: charts/group-sync-dashboard/templates/deployment.yaml | edit -->

Old text:

```yaml
{{- if and .Values.backup.offsite.enabled (eq .Values.backup.offsite.destination.type "pvc") }}
```

New text:

```yaml
{{- if and (eq (include "gsd.offsiteOn" .) "true") (eq .Values.backup.offsite.destination.type "pvc") }}
```

### Block 10 — charts/group-sync-dashboard/values.yaml

The comment states the three words, the default destination's class, and the pre-upgrade pass; the default becomes `""` (§3.4).

<!-- block: charts/group-sync-dashboard/values.yaml | edit -->

Old text:

```yaml
#
# OFF BY DEFAULT because it needs a destination the chart cannot choose for you — a second
# claim on a DIFFERENT StorageClass, or a bucket and a credential — and a CronJob rendered with
# nowhere to write is a red Job on every schedule. Nothing else about it is optional once on:
# the copy is hashed, opened and integrity-checked BEFORE it counts, and the Job exits
# non-zero on any of those.
#
# WHO RUNS IT. The dashboard image, with a Python-stdlib script the chart ships as a
# ConfigMap (scripts/offsite_backup.py, mounted at /scripts). The image has no tar, rsync or
# aws on purpose (docs/design/DESIGN_hardened_image.md §10), and a shell copy could not verify what
# it copied; the sqlite3 module is exactly what PRAGMA integrity_check needs.
#
# MOUNTING THE DATA CLAIM TWICE. The dashboard pod holds it.
#   ReadWriteMany     the CronJob pod mounts it anywhere; no affinity.
#   ReadWriteOnce     the claim binds to one NODE, so the chart pins the CronJob pod to the
#                     dashboard's node with a required podAffinity. A dashboard scaled to zero
#                     then leaves the Job Pending until activeDeadlineSeconds fails it — the
#                     honest outcome: no dashboard, no new copy to ship.
#   ReadWriteOncePod  exactly one pod, ever. The chart REFUSES to render rather than ship a
#                     Job that can never schedule.
#
# ALERTING. The app cannot see this Job. With monitoring.prometheusRule.enabled the chart adds
# two rules on kube_cronjob_status_last_successful_time (kube-state-metrics): stale, and
# never-observed. Where kube-state-metrics is not scraped the second one fires and stays
# firing — an alert that can never fire would be indistinguishable from healthy.
#
# NOT `backup.enabled`. That key does not exist and the chart refuses it: the on-volume
# switch is config.backup.enabled, this one is backup.offsite.enabled.
#
# THE CLAIM BINDS AT ONCE, BY A THROWAWAY POD. On a StorageClass with volumeBindingMode
# WaitForFirstConsumer (the common default) a claim stays Pending until a pod mounts it, and the
# CronJob may not run for six hours — `helm upgrade --wait` timed out on exactly that (measured on
# the reference cluster, 2026-09-05), and a timed-out upgrade is a FAILED revision whose objects
# Helm does not own. So, when the chart creates the claim, it also renders a one-shot bind Job
# that mounts it and exits: --wait succeeds in seconds. Under Argo CD the bind Job is a Sync hook
# in the claim's wave (0), deleted once it succeeds, so the wave turns healthy as soon as the claim
# binds and the CronJob follows in wave 1. With destination.pvc.existingClaim the claim is yours
# and no bind Job renders.
backup:
  offsite:
    enabled: false
```

New text:

```yaml
#
# ON WHEREVER IT CAN WORK. `enabled` is read as a word, one of three:
#   ""     (the default) on, unless the copy cannot work here; then nothing renders and nothing
#          fails. It cannot work with: persistence off; config.backup off, or an empty
#          config.backup.dir (the app reads that as backups disabled); a config.backup.dir outside
#          /data/; persistence.existingClaim without persistence.accessMode; a ReadWriteOncePod
#          data volume (below).
#   true   on, and the render REFUSES each of those with the reason.
#   false  off. A quoted "false" is off too; any other word refuses the render.
# Set it in this release's values file and roll it out through the release's deployment pipeline.
# The CronJob and its two alerts follow the same decision.
#
# The default destination is a second claim on the cluster's DEFAULT StorageClass: off the volume,
# not necessarily off the storage (on CRC the default class is the data claim's own). Name a
# different class in destination.pvc.storageClass for that. A cluster with no default class leaves
# the claim Pending, and the bind Job below fails after its 600 s deadline, until one is named.
# Once on, nothing is optional: the copy is hashed, opened and integrity-checked BEFORE it counts,
# and the Job exits non-zero on any of those.
#
# THE PRE-UPGRADE COPY TOO. At replicaCount 1, with the pvc destination, the same run also ships the
# newest copy the dashboard takes before a schema upgrade (/data/pre-upgrade; see config.backup
# above) to /offsite/pre-upgrade, checked against its .sha256, keeping three. No such copy yet is
# not a failure. The s3 destination ships the six-hourly copy only.
#
# WHO RUNS IT. The dashboard image, with a Python-stdlib script the chart ships as a
# ConfigMap (scripts/offsite_backup.py, mounted at /scripts). The image has no tar, rsync or
# aws on purpose (docs/design/DESIGN_hardened_image.md §10), and a shell copy could not verify what
# it copied; the sqlite3 module is exactly what PRAGMA integrity_check needs.
#
# MOUNTING THE DATA CLAIM TWICE. The dashboard pod holds it.
#   ReadWriteMany     the CronJob pod mounts it anywhere; no affinity.
#   ReadWriteOnce     the claim binds to one NODE, so the chart pins the CronJob pod to the
#                     dashboard's node with a required podAffinity. A dashboard scaled to zero
#                     then leaves the Job Pending until activeDeadlineSeconds fails it — the
#                     honest outcome: no dashboard, no new copy to ship.
#   ReadWriteOncePod  exactly one pod, ever. The default renders no CronJob; `true` REFUSES to
#                     render rather than ship a Job that can never schedule.
#
# ALERTING. The app cannot see this Job. With monitoring.prometheusRule.enabled the chart adds
# two rules on kube_cronjob_status_last_successful_time (kube-state-metrics): stale, and
# never-observed. Where kube-state-metrics is not scraped the second one fires and stays
# firing — an alert that can never fire would be indistinguishable from healthy.
#
# NOT `backup.enabled`. That key does not exist and the chart refuses it: the on-volume
# switch is config.backup.enabled, this one is backup.offsite.enabled.
#
# THE CLAIM BINDS AT ONCE, BY A THROWAWAY POD. On a StorageClass with volumeBindingMode
# WaitForFirstConsumer (the common default) a claim stays Pending until a pod mounts it, and the
# CronJob may not run for six hours — `helm upgrade --wait` timed out on exactly that (measured on
# the reference cluster, 2026-09-05), and a timed-out upgrade is a FAILED revision whose objects
# Helm does not own. So, when the chart creates the claim, it also renders a one-shot bind Job
# that mounts it and exits: --wait succeeds in seconds. Under Argo CD the bind Job is a Sync hook
# in the claim's wave (0), deleted once it succeeds, so the wave turns healthy as soon as the claim
# binds and the CronJob follows in wave 1. With destination.pvc.existingClaim the claim is yours
# and no bind Job renders.
backup:
  offsite:
    enabled: ""    # "" on wherever it can work | true on, refusing what cannot work | false off
```

### Block 11 — charts/group-sync-dashboard/README.md

The section's opening paragraph, with what a cluster without a default StorageClass does (the review's F6), and the `enabled` row.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text

**Off by default** — it needs a destination the chart cannot choose for you. Once on, the copy is
hashed, opened and integrity-checked before it counts, and the Job fails loudly otherwise.
Restore and verification: [`charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md`](../../charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md).

| Key | Default | Notes |
|---|---|---|
| `backup.offsite.enabled` | `false` | renders a CronJob, a ConfigMap with `scripts/offsite_backup.py`, a grant-less ServiceAccount, and (type `pvc`, no `existingClaim`) a second PVC. **Refused** with `persistence.enabled=false`, `config.backup.enabled=false`, a `config.backup.dir` outside `/data/`, or a `ReadWriteOncePod` data volume |
```

New text:

```text

**On wherever it can work.** `backup.offsite.enabled` is read as a word: empty (the default) renders
the CronJob unless the copy cannot work in this release, and then renders nothing and fails nothing;
`true` renders it and refuses those combinations with the reason; `false` turns it off (a quoted
`"false"` too); any other word refuses the render. Set it in the release's values file and roll it out
through the release's deployment pipeline. The default destination is a 5Gi claim on the cluster's
default StorageClass, which is off the volume but not necessarily off the storage: name a different
class in `destination.pvc.storageClass` for that. A cluster with no default StorageClass leaves the claim
Pending, and its bind Job fails after 600 s, so the rollout reports a failure until
`destination.pvc.storageClass` names a class. The copy is hashed, opened and integrity-checked before it
counts, and the Job fails loudly otherwise. At one replica with the `pvc` destination the
same run also ships the newest pre-upgrade copy ([runbook §6](../../charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md#6-pre-upgrade-copies))
to `/offsite/pre-upgrade`, keeping three. Restore and verification:
[`charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md`](../../charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md).

| Key | Default | Notes |
|---|---|---|
| `backup.offsite.enabled` | `""` | renders a CronJob, a ConfigMap with `scripts/offsite_backup.py`, a grant-less ServiceAccount, and (type `pvc`, no `existingClaim`) a second PVC with its bind Job. Empty: **nothing renders**, and nothing fails, with `persistence.enabled=false`, `config.backup.enabled=false`, a `config.backup.dir` that is empty or outside `/data/`, `persistence.existingClaim` without `persistence.accessMode`, or a `ReadWriteOncePod` data volume. `true`: each of those is **refused**. `false`: off. Any other word is refused |
```

### Block 12 — charts/group-sync-dashboard/README.md

The alert count in the `monitoring.prometheusRule.enabled` row and the stale-threshold row.

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text
| `monitoring.serviceMonitor.labels` | `{}` | extra metadata labels. Usually how a cluster's Prometheus selects which ServiceMonitors it owns |
| `monitoring.prometheusRule.enabled` | `true` | **seventeen** alerts — two of them render only with `reporting.enabled` (the default) — nineteen with `backup.offsite.enabled`; see below |
| `monitoring.prometheusRule.labels` | `{}` | as above, for rule selection |
| `monitoring.prometheusRule.overdueSeconds` | `7200` | a GroupSync has not synced for this long |
| `monitoring.prometheusRule.notPollingSeconds` | `600` | catches a dead poll loop, which the health endpoints cannot. **Must stay above ~2× `config.pollIntervalSeconds`** or it fires continuously on a healthy deployment |
| `monitoring.prometheusRule.walMiB` | `256` | MiB. 25% of the default 1Gi PVC. Raise it with `persistence.size` |
| `monitoring.prometheusRule.captureStalledSeconds` | `1800` | seconds without a successful oauth-log read before login capture counts as stalled. Capture rides the poll thread, so this **must stay well above `config.pollIntervalSeconds`** — same reasoning as `notPollingSeconds` |
| `monitoring.prometheusRule.backupStaleSeconds` | `43200` | seconds since the newest backup file before the copy counts as stale. Keep at ~2× `config.backupIntervalHours` × 3600 — one missed backup is a blip, two is a broken mechanism |
| `monitoring.prometheusRule.offsiteBackupStaleSeconds` | `43200` | seconds since the off-volume CronJob last succeeded (`kube_cronjob_status_last_successful_time`, kube-state-metrics). Two slots of `backup.offsite.schedule`. Rendered only with `backup.offsite.enabled` |
```

New text:

```text
| `monitoring.serviceMonitor.labels` | `{}` | extra metadata labels. Usually how a cluster's Prometheus selects which ServiceMonitors it owns |
| `monitoring.prometheusRule.enabled` | `true` | **nineteen** alerts — two of them render only with `reporting.enabled` (the default), two only where the offsite CronJob renders (the default, which steps aside where it cannot work); see below |
| `monitoring.prometheusRule.labels` | `{}` | as above, for rule selection |
| `monitoring.prometheusRule.overdueSeconds` | `7200` | a GroupSync has not synced for this long |
| `monitoring.prometheusRule.notPollingSeconds` | `600` | catches a dead poll loop, which the health endpoints cannot. **Must stay above ~2× `config.pollIntervalSeconds`** or it fires continuously on a healthy deployment |
| `monitoring.prometheusRule.walMiB` | `256` | MiB. 25% of the default 1Gi PVC. Raise it with `persistence.size` |
| `monitoring.prometheusRule.captureStalledSeconds` | `1800` | seconds without a successful oauth-log read before login capture counts as stalled. Capture rides the poll thread, so this **must stay well above `config.pollIntervalSeconds`** — same reasoning as `notPollingSeconds` |
| `monitoring.prometheusRule.backupStaleSeconds` | `43200` | seconds since the newest backup file before the copy counts as stale. Keep at ~2× `config.backupIntervalHours` × 3600 — one missed backup is a blip, two is a broken mechanism |
| `monitoring.prometheusRule.offsiteBackupStaleSeconds` | `43200` | seconds since the off-volume CronJob last succeeded (`kube_cronjob_status_last_successful_time`, kube-state-metrics). Two slots of `backup.offsite.schedule`. Rendered only where the offsite CronJob renders |
```

### Block 13 — charts/group-sync-dashboard/README.md

The alerts heading keeps the cited words "The seventeen alerts"; the two offsite rows say when they render, and the stale row names both passes (the review's N1).

<!-- block: charts/group-sync-dashboard/README.md | edit -->

Old text:

```text

#### The seventeen alerts (nineteen with `backup.offsite`)

| Alert | Fires on | `for` |
|---|---|---|
| `GroupSyncOverdue` | a CR has not synced for `overdueSeconds` | `for.overdue`, `10m` |
| `DanglingRoleBinding` | a binding grants a group that was operator-managed and has vanished | `for.dangling`, `15m` |
| `GroupSyncDashboardNotPolling` | the dashboard's own poll loop has stopped. `/healthz` is unconditional and `/readyz` only reads the store, so neither probe can see this | `for.notPolling`, `5m` |
| `GroupSyncClusterUnreachable` | `gsd_cluster_up == 0` | `for.unreachable`, `15m` |
| `GroupSyncDashboardDirectUserGrants` | bindings still name people rather than LDAP groups | `for.directUserGrants`, `1h` — long, because this is a migration backlog, not an incident |
| `GroupSyncDashboardConfigReconcileError` | a `NamespaceConfig`/`GroupConfig` is failing, so RBAC has silently stopped reconciling | `for.configError`, `10m` |
| `GroupSyncGroupCountCliff` | `gsd_alerts_total{kind="group_count_cliff"} > 0` — a group lost `dropRatio` of at least `minMembers` members within `windowHours`. Rendered only while `config.alerts.groupCountCliff.enabled`; silenced cliffs count under `group_count_cliff_silenced` and never fire | `for.groupCountCliff`, `15m` |
| `GroupSyncDashboardWalGrowing` | `gsd_sqlite_wal_bytes` above `walMiB` — checkpoint starvation | `for.walGrowing`, `30m` |
| `GroupSyncDashboardWalDisabled` | `gsd_sqlite_wal_enabled == 0` — the filesystem refused WAL | `for.walDisabled`, `10m` |
| `GroupSyncDashboardVisibilityChecksFailing` | the SubjectAccessReview behind per-user visibility is erroring, so readers are silently served the self view fail-closed | `for.visibilityFailing`, `15m` |
| `GroupSyncDashboardLoginCaptureStalled` | no successful oauth-log read for `captureStalledSeconds` while capture is enabled — the Logins page silently freezes | `for.captureStalled`, `15m` |
| `GroupSyncDashboardBackupStale` | the newest file in `backupDir` is older than `backupStaleSeconds` — the only copy of the un-refetchable history has stopped being taken | `for.backupStale`, `30m` |
| `GroupSyncDashboardReportUsagePullFailing` | the dashboard's poller could not pull the report service's usage feed (token mismatch, Service/TLS, or a shape change) and has not succeeded in the window — runs are not lost, the Usage tab's Reports table stops advancing. Rendered only with `reporting.enabled` | `for.reportPull`, `30m` |
| `GroupSyncDashboardReportSnapshotStale` | `gsd_report_snapshot_age_seconds` above four snapshot intervals — the dashboard's leader is not writing copies, so a report would print stale data with an honest "data as of" line. Rendered only with `reporting.enabled` | `for.reportSnapshot`, `30m` |
| `GroupSyncDashboardOffsiteBackupStale` | *(`backup.offsite.enabled` only)* the CronJob last succeeded more than `offsiteBackupStaleSeconds` ago — nothing newer is off the volume | `for.offsiteBackupStale`, `30m` |
| `GroupSyncDashboardOffsiteBackupUnobserved` | *(`backup.offsite.enabled` only)* `kube_cronjob_status_last_successful_time` has no series for the CronJob: it has never succeeded, or kube-state-metrics is not scraped here — in which case the stale alert can never fire and this is the only signal | `for.offsiteBackupUnobserved`, `1h` |
```

New text:

```text

#### The seventeen alerts, and two more wherever the offsite CronJob renders (the default)

| Alert | Fires on | `for` |
|---|---|---|
| `GroupSyncOverdue` | a CR has not synced for `overdueSeconds` | `for.overdue`, `10m` |
| `DanglingRoleBinding` | a binding grants a group that was operator-managed and has vanished | `for.dangling`, `15m` |
| `GroupSyncDashboardNotPolling` | the dashboard's own poll loop has stopped. `/healthz` is unconditional and `/readyz` only reads the store, so neither probe can see this | `for.notPolling`, `5m` |
| `GroupSyncClusterUnreachable` | `gsd_cluster_up == 0` | `for.unreachable`, `15m` |
| `GroupSyncDashboardDirectUserGrants` | bindings still name people rather than LDAP groups | `for.directUserGrants`, `1h` — long, because this is a migration backlog, not an incident |
| `GroupSyncDashboardConfigReconcileError` | a `NamespaceConfig`/`GroupConfig` is failing, so RBAC has silently stopped reconciling | `for.configError`, `10m` |
| `GroupSyncGroupCountCliff` | `gsd_alerts_total{kind="group_count_cliff"} > 0` — a group lost `dropRatio` of at least `minMembers` members within `windowHours`. Rendered only while `config.alerts.groupCountCliff.enabled`; silenced cliffs count under `group_count_cliff_silenced` and never fire | `for.groupCountCliff`, `15m` |
| `GroupSyncDashboardWalGrowing` | `gsd_sqlite_wal_bytes` above `walMiB` — checkpoint starvation | `for.walGrowing`, `30m` |
| `GroupSyncDashboardWalDisabled` | `gsd_sqlite_wal_enabled == 0` — the filesystem refused WAL | `for.walDisabled`, `10m` |
| `GroupSyncDashboardVisibilityChecksFailing` | the SubjectAccessReview behind per-user visibility is erroring, so readers are silently served the self view fail-closed | `for.visibilityFailing`, `15m` |
| `GroupSyncDashboardLoginCaptureStalled` | no successful oauth-log read for `captureStalledSeconds` while capture is enabled — the Logins page silently freezes | `for.captureStalled`, `15m` |
| `GroupSyncDashboardBackupStale` | the newest file in `backupDir` is older than `backupStaleSeconds` — the only copy of the un-refetchable history has stopped being taken | `for.backupStale`, `30m` |
| `GroupSyncDashboardReportUsagePullFailing` | the dashboard's poller could not pull the report service's usage feed (token mismatch, Service/TLS, or a shape change) and has not succeeded in the window — runs are not lost, the Usage tab's Reports table stops advancing. Rendered only with `reporting.enabled` | `for.reportPull`, `30m` |
| `GroupSyncDashboardReportSnapshotStale` | `gsd_report_snapshot_age_seconds` above four snapshot intervals — the dashboard's leader is not writing copies, so a report would print stale data with an honest "data as of" line. Rendered only with `reporting.enabled` | `for.reportSnapshot`, `30m` |
| `GroupSyncDashboardOffsiteBackupStale` | *(only where the offsite CronJob renders)* the CronJob last succeeded more than `offsiteBackupStaleSeconds` ago — nothing newer is off the volume, or the newest pre-upgrade copy is refused (a run fails when either pass fails; the pod's log says which) | `for.offsiteBackupStale`, `30m` |
| `GroupSyncDashboardOffsiteBackupUnobserved` | *(only where the offsite CronJob renders)* `kube_cronjob_status_last_successful_time` has no series for the CronJob: it has never succeeded, or kube-state-metrics is not scraped here — in which case the stale alert can never fire and this is the only signal | `for.offsiteBackupUnobserved`, `1h` |
```

### Block 14 — charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md

The opening list: on by default, and the pre-upgrade copy. Re-cut at implementation without SPEC_E4's on-volume line (Orchestrator's notes, 12).

<!-- block: charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
* **off-volume** — `backup.offsite` (off by default) copies the newest of those to a second
  claim or to object storage, with a `.sha256` sidecar, after an integrity check
  (`charts/group-sync-dashboard/scripts/offsite_backup.py#ship`);
```

New text:

```text
* **off-volume** — `backup.offsite` (on by default wherever it can work) copies the newest of those to a
  second claim or to object storage, with a `.sha256` sidecar, after an integrity check
  (`charts/group-sync-dashboard/scripts/offsite_backup.py#ship`), and, at one replica with the second
  claim, the newest pre-upgrade copy as well (§6);
```

### Block 15 — charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md

§2's expected log gains the second pass's line.

<!-- block: charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
pruned 0 older copies (keep=14)
```

New text:

```text
pruned 0 older copies (keep=14)
no pre-upgrade-*.db under /data/pre-upgrade: nothing to ship (one is written only when an image upgrades the schema)
```

### Block 16 — charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md

§2 explains the second pass, and how a refused pre-upgrade copy stops failing every run (the review's N1).

<!-- block: charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text

A second run straight after says `already shipped: … matches its sidecar; nothing to copy`.
```

New text:

```text

The last line is the second pass, which runs at one replica with the `pvc` destination. Once an upgrade
has written a pre-upgrade copy (§6), that line is replaced by the pass's own three lines, which name
`/data/pre-upgrade/pre-upgrade-….db -> /offsite/pre-upgrade/pre-upgrade-….db`, its `integrity_check ok`
and `pruned 0 older copies (keep=3)`. The pass checks the copy against the `.sha256` beside it first and
keeps the newest three. The two passes are independent: a failure in one does not stop the other, and
either fails the Job. A pass that prints `ERROR: … it is not the copy the store verified` has found a copy whose
bytes no longer match the checksum the dashboard wrote when it took it: do not restore from it. Every run fails on
it, and `GroupSyncDashboardOffsiteBackupStale` fires while the six-hourly copies still ship, until a newer upgrade
writes a newer copy or that copy and its `.sha256` are moved out of `pre-upgrade/` (to `/data/pre-restore/`, as §6
does); the next run then ships the newest copy that verifies.

A second run straight after says `already shipped: … matches its sidecar; nothing to copy`.
```

### Block 17 — charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md

§6 says where the pre-upgrade copy goes off the volume.

<!-- block: charts/group-sync-dashboard/docs/RUNBOOK_backup_restore.md | edit -->

Old text:

```text
  `/data/<pod-name>/pre-upgrade/` when `replicaCount` is greater than 1. It is written even when scheduled
  backups are disabled, and the six-hourly rotation, the offsite CronJob, the backup metric and the KPI size
  line never include it.
```

New text:

```text
  `/data/<pod-name>/pre-upgrade/` when `replicaCount` is greater than 1. It is written even when scheduled
  backups are disabled, and the six-hourly rotation, the backup metric and the KPI size line never include it.
* **Off the volume.** At one replica, the offsite CronJob's `pvc` destination also receives the newest copy,
  in `/offsite/pre-upgrade/` under the same name, checked against its `.sha256` first; the newest three are
  kept there (§2). The copies of the six-hourly backups in `/offsite` never include it.
```

### Block 18 — docs/guides/reference-architecture.md

The backup paragraph names the second pass.

<!-- block: docs/guides/reference-architecture.md | edit -->

Old text:

```text
directory while hashing it, opens the *copy* with `immutable=1` and runs `PRAGMA
integrity_check`, then writes a `.sha256` sidecar and prunes to `keep`. Object storage goes
```

New text:

```text
directory while hashing it, opens the *copy* with `immutable=1` and runs `PRAGMA
integrity_check`, then writes a `.sha256` sidecar and prunes to `keep`. At one replica a second pass
does the same for the newest pre-upgrade copy, into its own directory
(`charts/group-sync-dashboard/scripts/offsite_backup.py#ship_pre_upgrade`). Object storage goes
```

### Block 19 — docs/guides/reference-architecture.md

The refusal table: what refuses only under `true`, the access-mode row split, the word row.

<!-- block: docs/guides/reference-architecture.md | edit -->

Old text:

```text
`templates/backup-offsite.yaml` adds its own, all about mounting one claim twice and about where
the copy goes (`charts/group-sync-dashboard/templates/backup-offsite.yaml#backup.enabled is not a value`):

| Combination | Refused because |
|---|---|
| `backup.enabled` set at all | the on-volume switch is `config.backup.enabled`; a key that silently did nothing would look like a backup that was configured |
| `backup.offsite.enabled` with `persistence.enabled=false`, `config.backup.enabled=false`, or `config.backup.dir` outside `/data/` | nothing to ship, a torn copy of the live file, or a directory the CronJob cannot see |
| `backup.offsite.enabled` with a `ReadWriteOncePod` data volume | one pod may ever mount it, so the Job could never schedule; `ReadWriteOnce` is derived into a required `podAffinity` instead |
```

New text:

```text
`templates/backup-offsite.yaml` adds its own, all about mounting one claim twice and about where
the copy goes (`charts/group-sync-dashboard/templates/backup-offsite.yaml#backup.enabled is not a value`).
The second to fourth rows refuse only an explicit `true`: the default, an empty `backup.offsite.enabled`, renders
no CronJob in those combinations instead (`charts/group-sync-dashboard/templates/_helpers.tpl#gsd.offsiteBlocker`):

| Combination | Refused because |
|---|---|
| `backup.enabled` set at all | the on-volume switch is `config.backup.enabled`; a key that silently did nothing would look like a backup that was configured |
| `backup.offsite.enabled: true` with `persistence.enabled=false`, `config.backup.enabled=false`, or `config.backup.dir` empty or outside `/data/` | nothing to ship, a torn copy of the live file, or a directory the CronJob cannot see |
| `backup.offsite.enabled: true` with a `ReadWriteOncePod` data volume | one pod may ever mount it, so the Job could never schedule; `ReadWriteOnce` is derived into a required `podAffinity` instead |
| `backup.offsite.enabled: true` with `persistence.existingClaim` and no `persistence.accessMode` | the chart cannot read the live claim's mode, and one derived from `replicaCount` may not be the claim's |
| `backup.offsite.enabled` set to a word other than `true`, `false` or empty | the switch is compared as a word, so a quoted `"false"` is off; a misspelt word must not decide whether the copy leaves the volume |
```

### Block 19a — environments/README.md

The lab table's chart-default cell for `backup.offsite.enabled`, which PR #522 added while the default was `false` (Orchestrator's notes, 13).

<!-- block: environments/README.md | edit -->

Old text:

```text
| `backup.offsite.enabled` | `false` | `true` | lab override — the off-volume backup on (the operator, 2026-10-02): a CronJob copies the newest scheduled backup to its own claim every six hours, so a lost or corrupted data volume is not the only copy. Its ServiceAccount has no token and no grant (rendered RBAC unchanged, 65 rules) |
```

New text:

```text
| `backup.offsite.enabled` | `""` | `true` | lab override — the off-volume backup on (the operator, 2026-10-02). Since #304 the empty default turns it on here too; `true` is the strict form, which refuses a combination where the copy cannot work rather than rendering nothing: a CronJob copies the newest scheduled backup to its own claim every six hours, so a lost or corrupted data volume is not the only copy. Its ServiceAccount has no token and no grant (rendered RBAC unchanged, 65 rules) |
```

### Block 20 — local-development/tests/test_offsite_backup_script.py

Imports for the pre-upgrade tests.

<!-- block: local-development/tests/test_offsite_backup_script.py | edit -->

Old text:

```python

from gsd.store import Store
```

New text:

```python

import gsd.store as store_module
from gsd.store import KNOWN_SCHEMA_VERSION, Store
```

### Block 21 — local-development/tests/test_offsite_backup_script.py

`TestPreUpgradePass`: T304-13, T304-14, the store's own copy, nothing to ship, the sidecar check, independent passes, the names held equal.

<!-- block: local-development/tests/test_offsite_backup_script.py | edit -->

Old text:

```python
        assert "empty or malformed" in capsys.readouterr().err
```

New text:

```python
        assert "empty or malformed" in capsys.readouterr().err


def _pre_upgrade_copy(directory: pathlib.Path, stamp: str, rows: int = 1) -> pathlib.Path:
    """A pre-upgrade copy as the store names it, with the store's sidecar (#301)."""
    directory.mkdir(parents=True, exist_ok=True)
    copy = directory / f"pre-upgrade-{stamp}-schema-19-to-20-pod-a.db"
    conn = sqlite3.connect(copy)
    conn.execute("CREATE TABLE sync_event (id INTEGER)")
    conn.executemany("INSERT INTO sync_event VALUES (?)", [(i,) for i in range(rows)])
    conn.execute("PRAGMA user_version = 19")
    conn.commit()
    conn.close()
    (directory / (copy.name + ".sha256")).write_text(f"{_sha(copy)}  {copy.name}\n")
    return copy


class TestPreUpgradePass:
    """The second pass (#304; SPEC_M1 §3.8): the newest pre-upgrade copy, into its own directory."""

    def test_the_newest_copy_ships_verified_and_three_are_kept(self, script, source, tmp_path, capsys):
        """T304-13."""
        backups, _ = source
        pre, dest = tmp_path / "pre-upgrade", tmp_path / "offsite"
        args = ["--source", str(backups), "--dest", str(dest), "--keep", "14", "--pre-upgrade-source", str(pre)]
        for day in range(1, 6):
            newest = _pre_upgrade_copy(pre, f"2026100{day}T000000.000000Z", rows=day)
            assert script.main(args) == 0
            shipped = dest / "pre-upgrade" / newest.name
            assert _sha(shipped) == _sha(newest)
            assert (dest / "pre-upgrade" / (newest.name + ".sha256")).read_text() == f"{_sha(newest)}  {newest.name}\n"
        assert sorted(p.name for p in (dest / "pre-upgrade").glob("pre-upgrade-*.db")) == \
            sorted(p.name for p in pre.glob("pre-upgrade-*.db"))[-script.PRE_UPGRADE_KEEP:]
        assert len(list((dest / "pre-upgrade").glob("*.sha256"))) == script.PRE_UPGRADE_KEEP
        out = capsys.readouterr().out
        assert "integrity_check ok; user_version 19" in out and f"(keep={script.PRE_UPGRADE_KEEP})" in out

    def test_a_copy_the_store_wrote_ships_and_checks(self, script, source, tmp_path, capsys):
        """The store's own copy, name and sidecar, through the pass and then `--check` (the runbook's)."""
        backups, _ = source
        db = tmp_path / "data" / "gsd.db"
        db.parent.mkdir()
        Store(str(db)).close()
        conn = sqlite3.connect(db)
        conn.execute(f"PRAGMA user_version = {KNOWN_SCHEMA_VERSION - 1}")
        conn.commit()
        store_module._pre_upgrade_copy(conn, str(db), KNOWN_SCHEMA_VERSION - 1)
        conn.close()
        (copy,) = (db.parent / store_module.PRE_UPGRADE_DIR).glob("pre-upgrade-*.db")
        dest = tmp_path / "offsite"
        assert script.main(["--source", str(backups), "--dest", str(dest),
                            "--pre-upgrade-source", str(db.parent / store_module.PRE_UPGRADE_DIR)]) == 0
        assert script.main(["--check", str(dest / "pre-upgrade" / copy.name)]) == 0
        assert "sidecar matches" in capsys.readouterr().out

    def test_the_six_hourly_pass_is_unchanged_beside_it(self, script, source, tmp_path):
        """T304-14: the same gsd-*.db is picked, and no pre-upgrade copy enters its destination or rotation."""
        backups, store = source
        alone, both = tmp_path / "alone", tmp_path / "both"
        pre = tmp_path / "pre-upgrade"
        for day in range(1, 5):
            _pre_upgrade_copy(pre, f"2026100{day}T000000.000000Z")
        for _ in range(3):
            store.backup(str(backups), keep=10)
            assert script.main(["--source", str(backups), "--dest", str(alone), "--keep", "2"]) == 0
            assert script.main(["--source", str(backups), "--dest", str(both), "--keep", "2",
                                "--pre-upgrade-source", str(pre)]) == 0
        assert sorted(p.name for p in both.iterdir() if p.is_file()) == sorted(p.name for p in alone.iterdir())
        assert not list(both.glob("pre-upgrade-*"))
        assert len(list((both / "pre-upgrade").glob("pre-upgrade-*.db"))) == 1, "one per run, the newest"

    @pytest.mark.parametrize("layout", ["absent", "empty"])
    def test_no_copy_yet_is_not_a_failure(self, script, source, tmp_path, capsys, layout):
        backups, _ = source
        pre = tmp_path / "pre-upgrade"
        if layout == "empty":
            pre.mkdir()
        assert script.main(["--source", str(backups), "--dest", str(tmp_path / "o"), "--pre-upgrade-source", str(pre)]) == 0
        assert "nothing to ship" in capsys.readouterr().out

    def test_a_copy_that_no_longer_matches_its_sidecar_is_refused(self, script, source, tmp_path, capsys):
        """A copy changed on the volume would otherwise leave with a fresh sidecar vouching for it."""
        backups, _ = source
        pre, dest = tmp_path / "pre-upgrade", tmp_path / "offsite"
        copy = _pre_upgrade_copy(pre, "20261001T000000.000000Z")
        (pre / (copy.name + ".sha256")).write_text("0" * 64 + f"  {copy.name}\n")
        assert script.main(["--source", str(backups), "--dest", str(dest), "--pre-upgrade-source", str(pre)]) == 1
        assert "it is not the copy the store verified" in capsys.readouterr().err
        assert not list((dest / "pre-upgrade").iterdir())
        assert len(list(dest.glob("gsd-*.db"))) == 1, "the six-hourly pass still shipped"

    def test_a_failing_six_hourly_pass_does_not_stop_the_pre_upgrade_pass(self, script, tmp_path, capsys):
        empty, pre, dest = tmp_path / "backup", tmp_path / "pre-upgrade", tmp_path / "offsite"
        empty.mkdir()
        copy = _pre_upgrade_copy(pre, "20261001T000000.000000Z")
        assert script.main(["--source", str(empty), "--dest", str(dest), "--pre-upgrade-source", str(pre)]) == 1
        assert "has not written a backup yet" in capsys.readouterr().err
        assert (dest / "pre-upgrade" / copy.name).is_file()

    def test_the_names_and_the_count_are_the_stores(self, script):
        """The script cannot import the store (it ships alone in a ConfigMap), so the two are held equal here."""
        assert script.PRE_UPGRADE_KEEP == store_module.PRE_UPGRADE_KEEP
        assert script.PRE_UPGRADE_DIR == store_module.PRE_UPGRADE_DIR
        assert pathlib.Path("pre-upgrade-20261001T000000.000000Z-schema-19-to-20-pod-a.db").match(script.PRE_UPGRADE_PATTERN)
        assert not pathlib.Path("gsd-20261001T000000.000000Z.db").match(script.PRE_UPGRADE_PATTERN)
```

### Block 22 — local-development/tests/test_chart_backup_offsite.py

The module docstring; the five conditions as data; `render` takes flags; T304-1 replaces `test_nothing_renders_by_default`; the account test reads the default; `TestYield` (T304-2 to T304-8) and `TestTheSwitchIsAWord` (T304-9 to T304-11).

<!-- block: local-development/tests/test_chart_backup_offsite.py | edit -->

Old text:

```python
"""The off-volume backup CronJob renders only when asked, and refuses the combinations that
could never work.

These shell out to `helm template` because the guards ARE Helm templating; the rendered
objects are what ships. The script the ConfigMap carries is tested on its own in
tests/test_offsite_backup_script.py.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest
import yaml

CHART = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"
SCRIPT = CHART / "scripts" / "offsite_backup.py"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")

ON = {"backup__offsite__enabled": "true"}
S3 = {
    **ON,
    "backup__offsite__destination__type": "s3",
    "backup__offsite__destination__s3__existingSecret": "backup-creds",
    "backup__offsite__destination__s3__image__repository": "public.ecr.aws/aws-cli/aws-cli",
    "backup__offsite__destination__s3__image__tag": "2.17.0",
}


def render(**values):
    """Render the chart. Returns (ok, combined output). `__` in a key is `.`."""
    args = ["helm", "template", "t", str(CHART), "--set", "ingress.host=t.example.com"]
    for key, value in values.items():
        args += ["--set", f"{key.replace('__', '.')}={value}"]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


def _docs(out):
    return [d for d in yaml.safe_load_all(out) if d]


def _one(docs, kind, suffix="-backup-offsite"):
    found = [d for d in docs if d.get("kind") == kind and d["metadata"]["name"].endswith(suffix)]
    assert len(found) == 1, f"expected one {kind} named *{suffix}, found {len(found)}"
    return found[0]


def _pod(cronjob):
    return cronjob["spec"]["jobTemplate"]["spec"]["template"]


class TestSwitch:
    def test_nothing_renders_by_default(self):
        ok, out = render()
        assert ok, out
        docs = _docs(out)
        assert not [d for d in docs if d.get("kind") == "CronJob"]
        assert not [d for d in docs if d.get("metadata", {}).get("name", "").endswith("-backup-offsite")]
        # the rules render by default since 0.36.0: the two offsite alerts stay behind the switch (the
        # shipped Grafana board's text panel names them as "backup.offsite.enabled only", which is fine)
        alerts = [r["alert"] for d in docs if d.get("kind") == "PrometheusRule" for g in d["spec"]["groups"] for r in g["rules"] if "alert" in r]
        assert not [a for a in alerts if "Offsite" in a], alerts

    def test_enabled_renders_the_four_objects(self):
        ok, out = render(**ON)
        assert ok, out
        docs = _docs(out)
        for kind in ("CronJob", "ConfigMap", "ServiceAccount", "PersistentVolumeClaim"):
            _one(docs, kind)
        assert len([d for d in docs if d.get("kind") == "Job" and "backup" in d["metadata"]["name"]]) == 1, "plus the one-shot bind Job"

    def test_the_configmap_carries_the_script_verbatim(self):
        ok, out = render(**ON)
        assert ok, out
        cm = _one(_docs(out), "ConfigMap")
        assert cm["data"]["offsite_backup.py"].strip() == SCRIPT.read_text().strip()

    def test_the_serviceaccount_has_no_token_and_no_grant(self):
        ok, out = render(**ON)
        assert ok, out
        docs = _docs(out)
        sa = _one(docs, "ServiceAccount")
        assert sa.get("automountServiceAccountToken") is False
        for d in docs:
            if d.get("kind") in ("RoleBinding", "ClusterRoleBinding"):
                for s in d.get("subjects") or []:
                    assert s.get("name") != sa["metadata"]["name"], "the backup account was granted something"

    def test_backup_enabled_is_refused_as_the_wrong_key(self):
        ok, out = render(backup__enabled="true")
        assert not ok and "config.backup.enabled" in out and "backup.offsite.enabled" in out

```

New text:

```python
"""The off-volume backup CronJob renders wherever it can work, steps aside where it cannot, and,
asked for explicitly with `true`, refuses the combinations that could never work (#304).

These shell out to `helm template` because the guards ARE Helm templating; the rendered
objects are what ships. The script the ConfigMap carries is tested on its own in
tests/test_offsite_backup_script.py.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest
import yaml

CHART = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"
SCRIPT = CHART / "scripts" / "offsite_backup.py"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")

ON = {"backup__offsite__enabled": "true"}          # the strict form
# The five conditions the default steps aside from, each as (values, the message `true` refuses it with).
CANNOT_WORK = {
    "on-volume backup off": ({"config__backup__enabled": "false"}, "config.backup.enabled=true"),
    "derived ReadWriteOncePod": ({"reporting__enabled": "false", "persistence__accessMode": ""}, "Pending forever"),
    "persistence off": ({"persistence__enabled": "false", "reporting__enabled": "false"}, "persistence.enabled=true"),
    "empty backup dir": ({"config__backup__dir": ""}, "under /data/"),
    "backup dir outside /data/": ({"config__backup__dir": "/backup"}, "under /data/"),
    "backup dir walking out of /data/": ({"config__backup__dir": "/data/../etc"}, "under /data/"),
    "existing data claim, no access mode": ({"persistence__existingClaim": "mine", "persistence__accessMode": "",
                                             "reporting__enabled": "false"}, "cannot read the live claim"),
}
S3 = {
    **ON,
    "backup__offsite__destination__type": "s3",
    "backup__offsite__destination__s3__existingSecret": "backup-creds",
    "backup__offsite__destination__s3__image__repository": "public.ecr.aws/aws-cli/aws-cli",
    "backup__offsite__destination__s3__image__tag": "2.17.0",
}


def render(*flags, **values):
    """Render the chart. Returns (ok, combined output). `__` in a key is `.`."""
    args = ["helm", "template", "t", str(CHART), "--set", "ingress.host=t.example.com", *flags]
    for key, value in values.items():
        args += ["--set", f"{key.replace('__', '.')}={value}"]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


def _offsite_objects(out):
    return [d for d in _docs(out) if (d.get("metadata", {}).get("labels") or {}).get("app.kubernetes.io/component") == "backup-offsite"]


def _offsite_alerts(out):
    return [r["alert"] for d in _docs(out) if d.get("kind") == "PrometheusRule"
            for g in d["spec"]["groups"] for r in g["rules"] if "Offsite" in r.get("alert", "")]


def _docs(out):
    return [d for d in yaml.safe_load_all(out) if d]


def _one(docs, kind, suffix="-backup-offsite"):
    found = [d for d in docs if d.get("kind") == kind and d["metadata"]["name"].endswith(suffix)]
    assert len(found) == 1, f"expected one {kind} named *{suffix}, found {len(found)}"
    return found[0]


def _pod(cronjob):
    return cronjob["spec"]["jobTemplate"]["spec"]["template"]


class TestSwitch:
    def test_the_default_ships_the_copy_off_the_volume(self):
        """T304-1: with no value set, the CronJob and everything it needs render: the script, an
        account with no token, the 5Gi claim that survives an uninstall, and the bind Job."""
        values = yaml.safe_load((CHART / "values.yaml").read_text())
        assert values["backup"]["offsite"]["enabled"] == ""
        ok, out = render()
        assert ok, out
        docs = _docs(out)
        _one(docs, "CronJob")
        assert _one(docs, "ConfigMap")["data"]["offsite_backup.py"].strip() == SCRIPT.read_text().strip()
        assert _one(docs, "ServiceAccount")["automountServiceAccountToken"] is False
        pvc = _one(docs, "PersistentVolumeClaim")
        assert pvc["spec"]["resources"]["requests"]["storage"] == "5Gi"
        assert pvc["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
        assert pvc["metadata"]["annotations"]["argocd.argoproj.io/sync-options"] == "Prune=false,Delete=false,PruneLast=true"
        assert "storageClassName" not in pvc["spec"], "the cluster's default class, unless one is named"
        assert len([d for d in docs if d.get("kind") == "Job" and "-backup-offsite-bind-" in d["metadata"]["name"]]) == 1

    def test_enabled_renders_the_four_objects(self):
        ok, out = render(**ON)
        assert ok, out
        docs = _docs(out)
        for kind in ("CronJob", "ConfigMap", "ServiceAccount", "PersistentVolumeClaim"):
            _one(docs, kind)
        assert len([d for d in docs if d.get("kind") == "Job" and "backup" in d["metadata"]["name"]]) == 1, "plus the one-shot bind Job"

    def test_the_configmap_carries_the_script_verbatim(self):
        ok, out = render(**ON)
        assert ok, out
        cm = _one(_docs(out), "ConfigMap")
        assert cm["data"]["offsite_backup.py"].strip() == SCRIPT.read_text().strip()

    def test_the_serviceaccount_has_no_token_and_no_grant(self):
        ok, out = render()
        assert ok, out
        docs = _docs(out)
        sa = _one(docs, "ServiceAccount")
        assert sa.get("automountServiceAccountToken") is False
        for d in docs:
            if d.get("kind") in ("RoleBinding", "ClusterRoleBinding"):
                for s in d.get("subjects") or []:
                    assert s.get("name") != sa["metadata"]["name"], "the backup account was granted something"

    def test_backup_enabled_is_refused_as_the_wrong_key(self):
        ok, out = render(backup__enabled="true")
        assert not ok and "config.backup.enabled" in out and "backup.offsite.enabled" in out


class TestYield:
    """T304-2 to T304-7: where the copy cannot work, the default renders nothing of offsite and fails
    nothing; with only the default flipped to `true` each of these renders failed."""

    @pytest.mark.parametrize("case", sorted(CANNOT_WORK))
    def test_the_default_steps_aside(self, case):
        ok, out = render(**CANNOT_WORK[case][0])
        assert ok, out
        assert not _offsite_objects(out) and not _offsite_alerts(out)

    @pytest.mark.parametrize("case", sorted(CANNOT_WORK))
    def test_true_still_refuses_with_the_reason(self, case):
        """T304-8: anyone who set `true` keeps the refusal, message and all."""
        values, message = CANNOT_WORK[case]
        ok, out = render(**values, **ON)
        assert not ok and "backup.offsite.enabled=true" in out and message in out, out[-600:]

    def test_a_null_backup_dir_is_the_empty_dir(self, tmp_path):
        """`config.backup.dir:` with no value is a null that removes the key (§2.2): the ConfigMap already
        hands the app `backupDir: ""` for it, so the default steps aside and `true` refuses it as the empty
        dir — never with Go's "wrong type for value" on a nil, which rendered on 0.60.2 and failed on 0.61.0."""
        values = tmp_path / "values.yaml"
        values.write_text("config:\n  backup:\n    dir:\n")
        ok, out = render("-f", str(values))
        assert ok, out
        assert not _offsite_objects(out) and not _offsite_alerts(out)
        ok, out = render("-f", str(values), **ON)
        assert not ok and "config.backup.dir under /data/ with no '..' (it is \"\")" in out, out[-600:]

    def test_the_offsite_stanzas_own_mistakes_are_refused_in_the_default_too(self):
        """A destination value set by hand says offsite is wanted; stepping aside would hide that it
        never runs."""
        ok, out = render(backup__offsite__destination__type="nfs")
        assert not ok and "is not a destination" in out


class TestTheSwitchIsAWord:
    """T304-9 to T304-11: true, false or empty, read as words; anything else refused by name."""

    def test_false_is_off(self):
        ok, out = render(backup__offsite__enabled="false")
        assert ok, out
        assert not _offsite_objects(out) and not _offsite_alerts(out)

    @pytest.mark.parametrize("word,on", [("false", False), ("true", True), ("", True)])
    def test_a_quoted_word_means_what_it_says(self, word, on):
        ok, out = render("--set-string", f"backup.offsite.enabled={word}")
        assert ok, out
        assert bool(_offsite_objects(out)) is on and bool(_offsite_alerts(out)) is on

    @pytest.mark.parametrize("word", ["yes", "ture", "0", "False"])
    def test_any_other_word_is_refused_naming_the_three(self, word):
        ok, out = render("--set-string", f"backup.offsite.enabled={word}")
        assert not ok
        assert f'backup.offsite.enabled is "{word}"' in out
        assert 'empty ("", the default' in out and "true (on" in out and "false (off)" in out

    @pytest.mark.parametrize("text,on", [('"false"', False), ("no", False), ("off", False), ("yes", True), ("", True)])
    def test_a_values_file_reads_the_same(self, tmp_path, text, on):
        """The release's values file is the path. YAML 1.1's no/off/yes arrive as booleans, and an empty
        value is a null that removes the key, which is the default."""
        values = tmp_path / "values.yaml"
        values.write_text(f"backup:\n  offsite:\n    enabled: {text}\n")
        ok, out = render("-f", str(values))
        assert ok, out
        assert bool(_offsite_objects(out)) is on

```

### Block 23 — local-development/tests/test_chart_backup_offsite.py

The CronJob's pre-upgrade argument at one replica and not above (T304-13, the chart half).

<!-- block: local-development/tests/test_chart_backup_offsite.py | edit -->

Old text:

```python
        assert ship["securityContext"]["readOnlyRootFilesystem"] is True
```

New text:

```python
        assert ship["securityContext"]["readOnlyRootFilesystem"] is True

    def test_the_newest_pre_upgrade_copy_ships_too_at_one_replica(self):
        """T304-13 (the chart half): at one replica the copies are in /data/pre-upgrade, beside
        /data/gsd.db; above one each pod has its own directory, and none is named."""
        ok, out = render()
        assert ok, out
        (ship,) = _pod(_one(_docs(out), "CronJob"))["spec"]["containers"]
        assert ship["command"][ship["command"].index("--pre-upgrade-source") + 1] == "/data/pre-upgrade"
        ok, out = render(replicaCount="2", leaderElection__enabled="false", reporting__enabled="false")
        assert ok, out
        (ship,) = _pod(_one(_docs(out), "CronJob"))["spec"]["containers"]
        assert "--pre-upgrade-source" not in ship["command"]
```

### Block 24 — local-development/tests/test_chart_backup_offsite.py

The `s3` stage ships the six-hourly copy only (Orchestrator's notes, 4).

<!-- block: local-development/tests/test_chart_backup_offsite.py | edit -->

Old text:

```python
        assert stage["command"][stage["command"].index("--keep") + 1] == "0"
```

New text:

```python
        assert stage["command"][stage["command"].index("--keep") + 1] == "0"
        assert "--pre-upgrade-source" not in stage["command"], "the s3 destination ships the six-hourly copy only"
```

### Block 25 — local-development/tests/test_chart_backup_offsite.py

T304-12 replaces `test_the_two_rules_render_only_with_the_cronjob`: the rules render exactly when the CronJob does, in every state; and the stale alert and the runbook name a refused pre-upgrade copy (the review's N1).

<!-- block: local-development/tests/test_chart_backup_offsite.py | edit -->

Old text:

```python

    def test_the_two_rules_render_only_with_the_cronjob(self):
        assert "GroupSyncDashboardOffsiteBackupStale" not in self._rules()
        rules = self._rules(**ON)
```

New text:

```python

    @pytest.mark.parametrize("case", ["default", "true", "false", "quoted false", *sorted(CANNOT_WORK)])
    def test_the_two_rules_render_exactly_when_the_cronjob_does(self, case):
        """T304-12: one helper decides both, so they cannot drift apart in any state."""
        flags, values = (), {}
        if case == "true":
            values = ON
        elif case == "false":
            values = {"backup__offsite__enabled": "false"}
        elif case == "quoted false":
            flags = ("--set-string", "backup.offsite.enabled=false")
        elif case in CANNOT_WORK:
            values = CANNOT_WORK[case][0]
        ok, out = render(*flags, monitoring__prometheusRule__enabled="true", **values)
        assert ok, out
        cronjob = [d for d in _docs(out) if d.get("kind") == "CronJob" and d["metadata"]["name"].endswith("-backup-offsite")]
        expected = ["GroupSyncDashboardOffsiteBackupStale", "GroupSyncDashboardOffsiteBackupUnobserved"] if cronjob else []
        assert sorted(_offsite_alerts(out)) == expected
        assert bool(cronjob) is (case in ("default", "true"))

    def test_a_refused_pre_upgrade_copy_is_named_by_the_alert_and_the_runbook(self):
        """A run fails when either pass fails (§3.6): the stale alert must not say that nothing newer left the
        volume, and the runbook must say how a refused pre-upgrade copy stops failing every run."""
        description = self._rules()["GroupSyncDashboardOffsiteBackupStale"]["annotations"]["description"]
        assert "pre-upgrade copy is refused" in description and "nothing newer is off it." not in description
        runbook = (CHART.parents[1] / "charts" / "group-sync-dashboard" / "docs" / "RUNBOOK_backup_restore.md").read_text().split("## 3.", 1)[0]
        assert "it is not the copy the store verified" in runbook and "/data/pre-restore/" in runbook

    def test_the_two_rules_watch_the_cronjob(self):
        rules = self._rules()
```

### Block 26 — local-development/tests/test_values_defaults.py

`backup.offsite.enabled` leaves `KEPT_OFF` (T304-15).

<!-- block: local-development/tests/test_values_defaults.py | edit -->

Old text:

```python
    "rbac.identities": "C2: a grant (get/list identities.user.openshift.io) the chart does not otherwise need, so off under the 0.14.0 rule",
    "backup.offsite.enabled": "B1: needs a destination the chart cannot choose (a second claim or a bucket and a credential); a CronJob with nowhere to write is a red Job every six hours",
```

New text:

```python
    "rbac.identities": "C2: a grant (get/list identities.user.openshift.io) the chart does not otherwise need, so off under the 0.14.0 rule",
```

### Block 27 — local-development/tests/test_values_defaults.py

And joins `FLIPPED`.

<!-- block: local-development/tests/test_values_defaults.py | edit -->

Old text:

```python
    "monitoring.grafanaDashboard.cr.enabled",
```

New text:

```python
    "monitoring.grafanaDashboard.cr.enabled",
    # #304: on wherever it can work. Its default is the empty word, not `true`: `true` is the strict
    # form that refuses a combination the default steps aside from.
    "backup.offsite.enabled",
```

### Block 28 — local-development/tests/test_values_defaults.py

`ON_WHERE_IT_CAN_WORK`, the flipped keys whose default is `""`.

<!-- block: local-development/tests/test_values_defaults.py | edit -->

Old text:

```python

# Documents an operator follows. Records (reviews, the changelog's history, superseded designs and
```

New text:

```python

# Flipped switches whose default is "" (on wherever it can work) rather than true.
ON_WHERE_IT_CAN_WORK = ("backup.offsite.enabled",)

# Documents an operator follows. Records (reviews, the changelog's history, superseded designs and
```

### Block 29 — local-development/tests/test_values_defaults.py

The check reads `ON_WHERE_IT_CAN_WORK`.

<!-- block: local-development/tests/test_values_defaults.py | edit -->

Old text:

```python
    for key in FLIPPED:
        assert values[key] is True, key
```

New text:

```python
    for key in FLIPPED:
        if key in ON_WHERE_IT_CAN_WORK:
            assert values[key] == "", key
        else:
            assert values[key] is True, key
```

### Block 30 — local-development/tests/test_chart_pdb.py

T304-16: every Job and CronJob pod template stays outside the budget, the offsite ones included.

<!-- block: local-development/tests/test_chart_pdb.py | edit -->

Old text:

```python
        assert _matches(selector, deployment["spec"]["template"]["metadata"]["labels"])
        jobs = [d for d in docs if d.get("kind") == "Job"]
        assert len(jobs) == 1, [d["metadata"]["name"] for d in jobs]   # secrets mint only
        for job in jobs:
            labels = job["spec"]["template"]["metadata"]["labels"]
            assert not _matches(selector, labels), (
                f"{job['metadata']['name']}: a Job-owned pod in the budget fails it "
                f"(jobs.batch has no scale subresource) and blocks every drain"
            )
            # Still identifiable as this release's pod, just not as the workload.
            assert labels["app.kubernetes.io/instance"] == "t"
            assert labels["app.kubernetes.io/component"] == "secrets-mint", labels
```

New text:

```python
        assert _matches(selector, deployment["spec"]["template"]["metadata"]["labels"])
        # Every Job-owned pod template in the default render: the secrets mint, and the offsite
        # claim's bind Job and CronJob, which render by default since #304.
        pods = {d["metadata"]["name"]: d["spec"]["template"]["metadata"]["labels"] for d in docs if d.get("kind") == "Job"}
        pods.update({d["metadata"]["name"]: d["spec"]["jobTemplate"]["spec"]["template"]["metadata"]["labels"]
                     for d in docs if d.get("kind") == "CronJob"})
        assert sorted(labels["app.kubernetes.io/component"] for labels in pods.values()) == \
            ["backup-offsite", "backup-offsite", "secrets-mint"], sorted(pods)
        for name, labels in pods.items():
            assert not _matches(selector, labels), (
                f"{name}: a Job-owned pod in the budget fails it "
                f"(jobs.batch has no scale subresource) and blocks every drain"
            )
            # Still identifiable as this release's pod, just not as the workload.
            assert labels["app.kubernetes.io/instance"] == "t"
```

### Block 31 — local-development/tests/test_chart_reporting.py

Both CronJobs, the report schedule's and the offsite one, stay outside both budgets.

<!-- block: local-development/tests/test_chart_reporting.py | edit -->

Old text:

```python
    assert _matches(monitor["spec"]["selector"]["matchLabels"], service["metadata"]["labels"])
    cronjobs = [d for d in docs if d.get("kind") == "CronJob"]
    assert len(cronjobs) == 1
    cl = cronjobs[0]["spec"]["jobTemplate"]["spec"]["template"]["metadata"]["labels"]
    assert not _matches(ds, cl) and not _matches(rs, cl)
```

New text:

```python
    assert _matches(monitor["spec"]["selector"]["matchLabels"], service["metadata"]["labels"])
    # The report schedule's CronJob, and the offsite CronJob that renders by default (#304): neither
    # pod is selected by either budget.
    cronjobs = [d for d in docs if d.get("kind") == "CronJob"]
    assert sorted(d["metadata"]["name"] for d in cronjobs) == [f"{dashboard_name}-backup-offsite", f"{report_name}-weekly"]
    for cronjob in cronjobs:
        cl = cronjob["spec"]["jobTemplate"]["spec"]["template"]["metadata"]["labels"]
        assert not _matches(ds, cl) and not _matches(rs, cl)
```

### Block 32 — local-development/tests/test_chart_reporting.py

The report CronJob by name.

<!-- block: local-development/tests/test_chart_reporting.py | edit -->

Old text:

```python
    assert labels["app.kubernetes.io/name"].endswith("-report") and "app" not in labels
    cron = next(d for d in docs if d.get("kind") == "CronJob")
```

New text:

```python
    assert labels["app.kubernetes.io/name"].endswith("-report") and "app" not in labels
    cron = next(d for d in docs if d.get("kind") == "CronJob" and d["metadata"]["name"] == "t-group-sync-dashboard-report-weekly")
```

### Block 33 — local-development/tests/test_chart_reporting.py

The report CronJob by name, in the quoted-false test.

<!-- block: local-development/tests/test_chart_reporting.py | edit -->

Old text:

```python
        docs = [d for d in _yaml.safe_load_all(done.stdout) if d]
        cron = next(d for d in docs if d.get("kind") == "CronJob")
```

New text:

```python
        docs = [d for d in _yaml.safe_load_all(done.stdout) if d]
        cron = next(d for d in docs if d.get("kind") == "CronJob" and d["metadata"]["name"] == "t-group-sync-dashboard-report-a")
```

### Block 34 — local-development/tests/test_chart_route.py

`one()` sets the offsite account aside, as it does the report's and the mint's (nine tests).

<!-- block: local-development/tests/test_chart_route.py | edit -->

Old text:

```python
    Service, ServiceAccount, Deployment and PDB, all named `…-report`; these tests are about the
    dashboard's, so the report service's are set aside first (C3), and so is the secrets-mint
    hook's identity (0.37.0)."""
    found = [o for o in objects(out) if o["kind"] == kind and not o["metadata"]["name"].endswith(("-report", "-secrets-mint"))]
```

New text:

```python
    Service, ServiceAccount, Deployment and PDB, all named `…-report`; these tests are about the
    dashboard's, so the report service's are set aside first (C3), and so are the secrets-mint
    hook's identity (0.37.0) and the offsite CronJob's, which renders by default (#304)."""
    found = [o for o in objects(out) if o["kind"] == kind and not o["metadata"]["name"].endswith(("-report", "-secrets-mint", "-backup-offsite"))]
```

### Block 35 — local-development/tests/test_chart_route.py

The same in the no-ServiceAccount test.

<!-- block: local-development/tests/test_chart_route.py | edit -->

Old text:

```python
        # mounted — templates/report-serviceaccount.yaml), which this switch does not govern (C3).
        dashboard_sas = [o for o in objects(out) if o["kind"] == "ServiceAccount" and not o["metadata"]["name"].endswith(("-report", "-secrets-mint"))]
```

New text:

```python
        # mounted — templates/report-serviceaccount.yaml), which this switch does not govern (C3).
        dashboard_sas = [o for o in objects(out) if o["kind"] == "ServiceAccount" and not o["metadata"]["name"].endswith(("-report", "-secrets-mint", "-backup-offsite"))]
```

### Block 36 — dropped at implementation

SPEC_E2 is `merged` at chart 0.60.0 (#518); the version rule reads `specified` specs only, so its cell stays (Orchestrator's notes, 12).

### Block 37 — docs/specs/SPEC_G2_platform_users.md

SPEC_G2's MINOR: chart 0.63.0 (0.61.0 is this spec's, 0.62.0 SPEC_W1's); app 2.4.0 kept.

<!-- block: docs/specs/SPEC_G2_platform_users.md | edit -->

Old text:

```text
| Version on release | app 2.4.0, chart 0.61.0 |
```

New text:

```text
| Version on release | app 2.4.0, chart 0.63.0 |
```

### Block 38 — docs/specs/SPEC_G4_namespaced_lease_grant.md

SPEC_G4's two PATCHes: chart 0.61.1 and 0.61.2, the first free above 0.61.0, keeping their order before SPEC_G3 and SPEC_E6.

<!-- block: docs/specs/SPEC_G4_namespaced_lease_grant.md | edit -->

Old text:

```text
| Version on release | chart 0.60.3 (step 1, adds the Role) and 0.60.4 (step 2, removes the ClusterRole rule), chart only |
```

New text:

```text
| Version on release | chart 0.61.1 (step 1, adds the Role) and 0.61.2 (step 2, removes the ClusterRole rule), chart only |
```

### Block 38a — docs/specs/SPEC_G3_acknowledged_direct_grants.md

SPEC_G3's PATCH: chart 0.61.3; app 2.5.0 kept.

<!-- block: docs/specs/SPEC_G3_acknowledged_direct_grants.md | edit -->

Old text:

```text
| Version on release | app 2.5.0, chart 0.60.5 |
```

New text:

```text
| Version on release | app 2.5.0, chart 0.61.3 |
```

### Block 38b — docs/specs/SPEC_E6_kpi_backups_card.md

SPEC_E6's PATCH: chart 0.61.4; app 2.4.0 kept.

<!-- block: docs/specs/SPEC_E6_kpi_backups_card.md | edit -->

Old text:

```text
| Version on release | app 2.4.0, chart 0.60.6 |
```

New text:

```text
| Version on release | app 2.4.0, chart 0.61.4 |
```

### Block 39 — docs/specs/README.md

SPEC_G2's index row, held equal to its header by `local-development/tests/test_specs_index.py#test_the_index_row_matches_the_spec_header`.

<!-- block: docs/specs/README.md | edit -->

Old text:

```text
| G2 | [`SPEC_G2_platform_users.md`](SPEC_G2_platform_users.md) — platform users in the values file (`platformUsers`), classified in the poller so one list feeds the direct-user view, its alert and the unmanaged finding; either platform list from an existing ConfigMap, mounted as a file, refused beside an inline list | G — access declared | — | app 2.4.0, chart 0.61.0 | [#255](https://github.com/ephico2real2/group-sync-dashboard/issues/255) | specified |
```

New text:

```text
| G2 | [`SPEC_G2_platform_users.md`](SPEC_G2_platform_users.md) — platform users in the values file (`platformUsers`), classified in the poller so one list feeds the direct-user view, its alert and the unmanaged finding; either platform list from an existing ConfigMap, mounted as a file, refused beside an inline list | G — access declared | — | app 2.4.0, chart 0.63.0 | [#255](https://github.com/ephico2real2/group-sync-dashboard/issues/255) | specified |
```

### Block 39a — docs/specs/README.md

SPEC_G4's index row, held equal to its header by `local-development/tests/test_specs_index.py#test_the_index_row_matches_the_spec_header`.

<!-- block: docs/specs/README.md | edit -->

Old text:

```text
| G4 | [`SPEC_G4_namespaced_lease_grant.md`](SPEC_G4_namespaced_lease_grant.md) — the Lease grant namespaced: the dashboard's Leases granted by a Role and RoleBinding in the release namespace (`<fullname>-leases`), shipped in a chart release before the one that removes the ClusterRole's Lease rule, so an upgrade through both refuses the running pod no Lease call; the removal waits on the operator's agreement on #420 | G — access declared | — | chart 0.60.3 (step 1, adds the Role) and 0.60.4 (step 2, removes the ClusterRole rule), chart only | [#420](https://github.com/ephico2real2/group-sync-dashboard/issues/420) | specified |
```

New text:

```text
| G4 | [`SPEC_G4_namespaced_lease_grant.md`](SPEC_G4_namespaced_lease_grant.md) — the Lease grant namespaced: the dashboard's Leases granted by a Role and RoleBinding in the release namespace (`<fullname>-leases`), shipped in a chart release before the one that removes the ClusterRole's Lease rule, so an upgrade through both refuses the running pod no Lease call; the removal waits on the operator's agreement on #420 | G — access declared | — | chart 0.61.1 (step 1, adds the Role) and 0.61.2 (step 2, removes the ClusterRole rule), chart only | [#420](https://github.com/ephico2real2/group-sync-dashboard/issues/420) | specified |
```

### Block 39b — docs/specs/README.md

SPEC_G3's index row, held equal to its header by `local-development/tests/test_specs_index.py#test_the_index_row_matches_the_spec_header`.

<!-- block: docs/specs/README.md | edit -->

Old text:

```text
| G3 | [`SPEC_G3_acknowledged_direct_grants.md`](SPEC_G3_acknowledged_direct_grants.md) — acknowledged direct grants: a direct user grant whose binding carries the operator's `rbac.ocp.io/config-source` label or exception annotation leaves the worklist, its counts, the alert and the reports' review figures, counted and listed; `group-sync-operator-helm` is a chart's provenance in the Group gate; no migration | G — access declared | — | app 2.5.0, chart 0.60.5 | [#503](https://github.com/ephico2real2/group-sync-dashboard/issues/503) | specified |
```

New text:

```text
| G3 | [`SPEC_G3_acknowledged_direct_grants.md`](SPEC_G3_acknowledged_direct_grants.md) — acknowledged direct grants: a direct user grant whose binding carries the operator's `rbac.ocp.io/config-source` label or exception annotation leaves the worklist, its counts, the alert and the reports' review figures, counted and listed; `group-sync-operator-helm` is a chart's provenance in the Group gate; no migration | G — access declared | — | app 2.5.0, chart 0.61.3 | [#503](https://github.com/ephico2real2/group-sync-dashboard/issues/503) | specified |
```

### Block 39c — docs/specs/README.md

SPEC_E6's index row, held equal to its header by `local-development/tests/test_specs_index.py#test_the_index_row_matches_the_spec_header`.

<!-- block: docs/specs/README.md | edit -->

Old text:

```text
| E6 | [`SPEC_E6_kpi_backups_card.md`](SPEC_E6_kpi_backups_card.md) — the KPI page's Backups card: the last copy as an instant and when the next is due, the copies kept against `keep`, the failures since start, the newest copy's schema against the build's and the newest pre-upgrade copy, in one of five states said in words (disabled, never "0 backups"), from what the dashboard process already has; no Prometheus, no new metric, no new permission; composes with SPEC_E4 | E — restore tools and release safety | — | app 2.4.0, chart 0.60.6 | [#306](https://github.com/ephico2real2/group-sync-dashboard/issues/306) | specified |
```

New text:

```text
| E6 | [`SPEC_E6_kpi_backups_card.md`](SPEC_E6_kpi_backups_card.md) — the KPI page's Backups card: the last copy as an instant and when the next is due, the copies kept against `keep`, the failures since start, the newest copy's schema against the build's and the newest pre-upgrade copy, in one of five states said in words (disabled, never "0 backups"), from what the dashboard process already has; no Prometheus, no new metric, no new permission; composes with SPEC_E4 | E — restore tools and release safety | — | app 2.4.0, chart 0.61.4 | [#306](https://github.com/ephico2real2/group-sync-dashboard/issues/306) | specified |
```

### Block 40 — docs/CHANGELOG.md

The CHANGELOG entry with the upgrade note, first under `## Unreleased` (re-cut at implementation above SPEC_E4's entry, chart 0.61.0: Orchestrator's notes, 12) (`local-development/tests/test_kyverno.py#test_f3_unreleased_cites_the_current_chart_version_when_it_moved_since_the_last_release` holds the chart version to it); a configured destination is used (OB2's F2).

<!-- block: docs/CHANGELOG.md | edit -->

Old text:

```text
- **Above one replica, every pod keeps its own scheduled backups (#391, Epic E #385,
```

New text:

```text
- **The off-volume backup is on wherever it can work, and it ships the newest pre-upgrade copy too (#304,
  `docs/specs/SPEC_E5_offsite_on_by_default.md`; chart 0.61.0, no application change).**
  `backup.offsite.enabled` is read as a word with three values. Empty, the new default, renders the
  offsite CronJob unless the copy cannot work in the release (persistence off; `config.backup` off or an
  empty `config.backup.dir`; a `config.backup.dir` outside `/data/`; `persistence.existingClaim` without
  `persistence.accessMode`; a `ReadWriteOncePod` data volume), and then renders nothing and fails
  nothing. `true` keeps the refusal of each of those, message for message. `false` is off, and a quoted
  `"false"` is now off too: it used to render the CronJob. Any other word refuses the render. The two
  offsite alerts render exactly when the CronJob does. At `replicaCount` 1 with the `pvc` destination
  the same run also ships the newest `pre-upgrade-*.db` from `/data/pre-upgrade` to
  `/offsite/pre-upgrade`, after checking it against its `.sha256`, and keeps three there; no such copy
  yet is not a failure. **Upgrade note:** a release that sets nothing gains, on the next rollout, a 5Gi
  claim `<fullname>-backup-offsite` on the cluster's default StorageClass (`helm.sh/resource-policy:
  keep`, and Argo CD's `Prune=false,Delete=false`), a one-shot bind Job, a CronJob, a ConfigMap, a
  ServiceAccount with no grant and no token, and the alerts `GroupSyncDashboardOffsiteBackupStale` and
  `GroupSyncDashboardOffsiteBackupUnobserved`; the second fires where kube-state-metrics is not scraped.
  On a cluster with no default StorageClass the claim stays Pending until
  `backup.offsite.destination.pvc.storageClass` names one. A values file that set an invalid
  `backup.offsite.destination.*` value while offsite was off now fails the render with that value's
  existing message, and a values file that filled in a valid destination (an `s3` stanza with its Secret
  and image, or a `pvc` existing claim) while `enabled` was left unset now renders that CronJob on the
  next rollout: a destination that is configured is used. To keep offsite off, set
  `backup.offsite.enabled: false` in the release's values file and roll it out through the release's
  deployment pipeline.
- **Above one replica, every pod keeps its own scheduled backups (#391, Epic E #385,
```

### Block 41 — charts/group-sync-dashboard/Chart.yaml

The MINOR and its history line; `appVersion` unchanged.

<!-- block: charts/group-sync-dashboard/Chart.yaml | edit -->

Old text:

```yaml
# rotation above one replica (#391, SPEC_E4).
version: 0.60.2
```

New text:

```yaml
# rotation above one replica (#391, SPEC_E4).
# CHART 0.61.0 (2026-10-01), MINOR: backup.offsite.enabled defaults to "" (on wherever it can work),
# read as true, false or empty; the offsite CronJob also ships the newest pre-upgrade copy (#304,
# SPEC_E5). appVersion unchanged.
version: 0.61.0
```
