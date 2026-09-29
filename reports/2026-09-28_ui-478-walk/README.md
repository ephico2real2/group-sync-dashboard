# #478 on the lab: own-key reads at application 1.17.0 — 2026-09-28

**Outcome.** On the CRC lab, running application 1.17.0 at `84b1e46b6f` (`evidence/before-version.txt`), `developer`
walked #478's three surfaces at 1280 and 375 px, with and without a temporary cluster-admin grant. The instants below
are UTC as the files record them: 2026-09-29T01:47Z to 02:08Z, which is the evening of 2026-09-28 in the lab's
`America/New_York` zone (`evidence/before-version.txt`, `"abbrev":"EDT"`).
- **The stale link (C5):** `zzz-unknown`, `constructor` and `toString` read the same as each other on a fresh load
  and after a hash edit, at both widths. With the grant, all three read `Full view — you are seeing everything`,
  class `scope-pill full`, "No cluster by that id is configured", `narrowedReader()` `false` and `scopeFor` `"all"`.
  Without it, all three read `Your view — developer`, class `scope-pill self`, the Overview's refusal,
  `narrowedReader()` `true` and `scopeFor` `"self"`. There were no page errors (`evidence/r2-walk-granted.txt`,
  `evidence/r2-walk-ungranted.txt`).
- **The Add-cluster form:** the form showed both chips, `constructor=c` and `__proto__=p`. `Object.getPrototypeOf(view.clusterForm.labels) === null`
  read `true`, and the YAML twin listed both keys. Create, pressed once at 01:54:36Z, answered `422` with
  `label-invalid: label key '__proto__': …`. The form showed that sentence, and `gsd-cluster-walk-478` was `NotFound`
  at 01:54:38Z and at every later check (`evidence/walk-granted.txt`, `evidence/aftercreate-secret.txt`).
- **The namespace pages:** `label_keys` is `["company.net/mnemonic", "company.net/app-environment",
  "company.net/oud-group"]`. On the list, a labelled namespace's page, an unlabelled one's page and the lookup for
  `beta`, every label cell matched the API's own value where the namespace has the key and `—` (`— none —` on a
  namespace's page) where it does not. There were no page errors (`evidence/walk-granted.txt`,
  `evidence/r2-walk-granted.txt`).
- **The pod log**, from the first grant (01:52:54Z) to 02:05:48Z: 0 `fleet-login`, 0 `cluster-rejoin`, 0 Traceback,
  0 ERROR. The Create's refusal is not logged: the dashboard container logged no line between 01:54:30Z and
  01:54:45Z (`evidence/final-podlog.txt`, `evidence/create-window-podlog.txt`).

**The walk ran in two passes.** The first pass (01:52:54Z–01:57:03Z) read each hash-edit case 1.5 s after setting
`location.hash`, before the refresh that the edit starts had repainted. `#main` still showed Home ("What changed last
30 days"). The check that compared those readings with the fresh loads failed, and the pass stopped before the granted
phase at 375 px (`evidence/walk-granted.txt`). A probe, `scripts/probe_hash.py`, shows the same thing for real
positions. One second after the edit, `#main` still showed Home with `stale` set, for `#page=groups` and
`#page=overview&cluster=dashboard` as well as for `zzz-unknown`. By three seconds each new page had painted and the
`updated` stamp had moved (`evidence/probe-hash-repaint.txt`). The failure came from the walk's timing, not from the
product. The second pass (02:00:30Z–02:05:23Z) marks Home's first card and waits until a paint replaces it and
`#main` is no longer `stale`. It did not press Create again. The first pass's fresh-load readings, the form with its one Create, and the namespace
pages at 1280 px stand; its hash-edit readings are superseded.

The walk made one kind of temporary change to the lab: the grant, created and removed twice. It ran no Helm,
`release-crc.sh` or Argo CD command, and it changed no chart values. Nobody logged in as the fleet account, no fleet
password was placed, and no Rejoin was submitted. The route guard blocked no request in any phase. `/api/version`
read 1.17.0 at `84b1e46b6f` before and after, and the kept PVCs had the same UIDs. The fleet Lease stayed at
`resourceVersion` 6171122 with no holder, and `shared-qa`'s Secret stayed at 2981054.

## Definition of Done

| # | Row | Verdict | Evidence |
|---|---|---|---|
| 1 | The stale link (C5): as `developer` with the grant, then without it, `#page=overview&cluster=` `zzz-unknown`, `constructor`, `toString`, each on a fresh load and by editing `location.hash` after a good Home load, at 1280 and 375 px; the three ids read the same | PASS (second pass) | **With the grant** (02:01:46Z–02:02:47Z): whoami `"scope": "all", "cluster_admin": true`, `/api/clusterconfigs` `200`. At 1280 and at 375, fresh and by hash, each of the three ids read `pill_text` `Full view — you are seeing everything`, `pill_class` `scope-pill full`, `no_cluster_note` `true` with the `h2` naming the id, `narrowedReader` `false`, `scopeFor` `"all"`, `own_key_in_whoami_clusters` `false` and `page_errors` `[]`. Four `C5 (<how>): the three ids read the same … "differs": {}` lines, and `a fresh load and a hash edit read the same: true` at each width (`evidence/r2-walk-granted.txt`, `screenshots/61`–`72`). **Without it** (02:04:21Z–02:05:20Z, after `can-i` `no` at 02:03:06Z and the wait from 02:03:06Z to 02:04:16Z): whoami `"scope": "self", "cluster_admin": false`, `/api/clusterconfigs` `403`. Every case read `Your view — developer`, `scope-pill self`, `no_cluster_note` `false` with the `h2` `Overview` (the Overview's "Withheld, not empty" refusal), `narrowedReader` `true`, `scopeFor` `"self"` and no page error. Again `"differs": {}` four times (`evidence/r2-walk-ungranted.txt`, `screenshots/101`–`112`). The first pass's fresh loads read the same values (`evidence/walk-granted.txt`, `evidence/walk-ungranted.txt`, `screenshots/01`–`03`, `41`–`43`, `47`–`49`). |
| 2 | The Add-cluster form with `__proto__`: name `walk-478`, server `https://api.crc.testing:6443`, a throwaway token string, labels `constructor=c` and `__proto__=p`; both chips, a null prototype, the YAML twin; Create ONCE → the server's `label-invalid` naming `__proto__`, `422`; no Secret written | PASS | At 1280 (01:54:36Z): `"chips": ["constructor=c", "__proto__=p"], "proto_is_null": true, "keys": ["constructor", "__proto__"], "own___proto__": true`, and the twin's label lines are `"constructor": "c"`, `"__proto__": "p"` and `"groupsync-dashboard.io/secret-type": "cluster"`. The route guard saw the one POST with label keys `["constructor", "__proto__"]`. The response listener read `{"status": 422, "detail": "label-invalid: label key '__proto__': an optional DNS prefix and a slash, then ≤ 63 characters of letters, digits, '-', '_' or '.', starting and ending alphanumeric"}`, and `#cc-form-msg` showed the same sentence, with both chips still there. `Create POSTs sent in this phase: 1` (`evidence/walk-granted.txt`, `screenshots/07-granted-1280-form-two-labels.png`, `screenshots/08-granted-1280-form-create-refused.png`). `oc get secrets.v1. gsd-cluster-walk-478` answered `NotFound` at 01:47:06Z, 01:54:38Z, 01:57:02Z, 02:05:22Z and 02:05:48Z (`evidence/before-secret.txt`, `aftercreate-secret.txt`, `after-secret.txt`, `r2-after-secret.txt`, `final-secret.txt`). At 375 px (02:02:51Z) the same facts were read and Create was not pressed: `Create POSTs sent in this phase: 0` (`evidence/r2-walk-granted.txt`, `screenshots/73-granted-rerun-375-form-two-labels.png`). |
| 3 | The namespace pages with the lab's real keys: the list, one namespace's page, the lookup by a real label value; the value where the namespace has the key, `—` where it does not; the search finds its namespace; no page error; `label_keys` recorded | PASS | `label_keys`: `["company.net/mnemonic", "company.net/app-environment", "company.net/oud-group"]`, over 118 namespaces, 27 with a value for one of the keys and 91 with none. On the list, 25 rows on page one (17 with a value, 8 all `—`) had `"mismatches": []`, for example `["beta-prod", ["beta", "prod", "—"]]` and `["ca-tutorial", ["—", "—", "—"]]`. `beta-prod`'s page showed KPIs `[["mnemonic", "beta"], ["app-environment", "prod"], ["oud-group", "— none —"]]` and "Labelled company.net/mnemonic=beta and company.net/app-environment=prod." `ca-tutorial`'s page showed all three `— none —` and "Carries none of the captured labels". The lookup `beta` found `Namespaces · 4 of 118`, `beta-prod`, `beta-rnd`, `beta-uat` and `oud-poc-crossfamily`, with `"mismatches": []`. `function_or_native_on_page` was `false` everywhere, with no page error, at 1280 (01:54:42Z–01:54:51Z) and 375 (02:02:55Z–02:03:06Z) (`evidence/walk-granted.txt`, `evidence/r2-walk-granted.txt`, `screenshots/10`–`12`, `75`–`77`; the list itself has no screenshot, see "What the lab did not do"). The query was typed into the lookup box: `q` is not one of `POSITION_KEYS` in `local-development/gsd/static/index.html`, so `#page=lookup&q=…` would not carry it. **No label key named `constructor` (or `toString`) is configured on the lab**, so the own-key case itself is not exercised here. It is covered by #478's browser test (PR #482) `TestALabelKeyNamedLikeAnObjectMember` in `local-development/tests/test_ui.py`. |
| 4 | The pod log for the window: the create refusal line if one is logged; 0 `fleet-login`, 0 `cluster-rejoin`, 0 Traceback, 0 ERROR | PASS | From 01:52:54Z, 543 lines: `lines naming walk-478, label-invalid, __proto__ or a POST to /api/clusterconfigs:` none; `cluster-secret-created lines: 0`; `lines matching 'fleet-login': 0`; `lines matching 'cluster-rejoin': 0`; `lines naming /rejoin: 0`; `lines naming the fleet account: 0`; `Traceback lines: 0`; `ERROR lines: 0` (`evidence/final-podlog.txt`). No refusal line is logged: between 01:54:30Z and 01:54:45Z the container wrote `# lines: 0` (`evidence/create-window-podlog.txt`). The API turns the writer's refusal into the `422` without an event line (`_write_error` in `local-development/gsd/api.py`). |
| end | End state: `can-i` no → yes → no; no grant, no `gsd-cluster-walk-478`; `/api/version`, PVC UIDs, `shared-qa`, the fleet Lease unchanged | PASS | `can-i`: `no` at 01:47:05Z; `yes` at 01:52:54Z; `no` at 01:54:55Z and 01:57:02Z; `yes` at 02:00:30Z; `no` at 02:03:06Z, 02:05:22Z and 02:05:48Z (`evidence/before-cani.txt`, `granted-cani.txt`, `removed-cani.txt`, `after-cani.txt`, `r2-granted-cani.txt`, `r2-removed-cani.txt`, `r2-after-cani.txt`, `final-cani.txt`). The grant by the run label: `No resources found` before and at 02:05:48Z (`evidence/before-grant.txt`, `final-grant.txt`). The explicit deletes were at 01:54:55Z and 02:03:06Z, and each trap delete afterwards found `No resources found` (`evidence/grant-delete.txt`, `r2-grant-delete.txt`). `/api/version` read `"version":"1.17.0","commit":"84b1e46b6f"` before and after (`evidence/before-version.txt`, `r2-after-version.txt`). PVC UIDs `f065b7a4-535c-4ef1-868c-58f5afee4953` (data) and `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` (report-artifacts) before and after (`evidence/before-pvcs.txt`, `r2-after-pvcs.txt`). `shared-qa` `resourceVersion=2981054` before and after (`evidence/before-sharedqa.txt`, `r2-after-sharedqa.txt`). The fleet Lease `name=gsd-fleet-666f1ba7f2fdead0 resourceVersion=6171122 holderIdentity=""` before and after (`evidence/before-lease.txt`, `r2-after-lease.txt`). |

## How the walk ran

| When (UTC) | Step | File |
|---|---|---|
| 01:47:04–06 | Before: version, PVC UIDs, `can-i` `no`, no labelled grant, `gsd-cluster-walk-478` `NotFound`, the Lease, `shared-qa` | `evidence/before-*.txt` |
| 01:52:54 | First pass: the trap armed, then the grant created; `can-i` `yes`; 70 s waited, to 01:54:04 | `evidence/t0.txt`, `grant-create.txt`, `granted-cani.txt`, `wait-granted.txt` |
| 01:54:08–01:54:31 | C5 with the grant at 1280. The fresh loads were as in row 1. The hash edits were read before the repaint (`main_h2` `What changed last 30 days`), and the check failed | `evidence/walk-granted.txt` |
| 01:54:36–01:54:38 | The form at 1280, Create pressed once: `422` `label-invalid` naming `'__proto__'`; the Secret `NotFound` | `evidence/walk-granted.txt`, `aftercreate-secret.txt` |
| 01:54:42–01:54:51 | The namespace pages at 1280 | `evidence/walk-granted.txt` |
| 01:54:55 | The walk stopped after the 375 px tier check (a failure was already recorded), `walk exit=1`; the grant deleted explicitly; `can-i` `no`; 70 s waited, to 01:56:05 | `evidence/walk-granted.txt`, `grant-delete.txt`, `removed-cani.txt`, `wait-ungranted.txt` |
| 01:56:09–01:57:00 | C5 without the grant at 1280 and 375. Its hash edits were read before the repaint too; the check passed only because it compared the ids with one another across the two modes and all of them read `self` | `evidence/walk-ungranted.txt` |
| 01:57:00–03 | After captures; the trap's delete found nothing | `evidence/after-*.txt`, `grant-delete.txt` |
| 02:00:30 | Second pass (`scripts/walk.sh rerun`): the trap armed, the grant created, `can-i` `yes`, 70 s waited to 02:01:41 | `evidence/r2-t0.txt`, `r2-grant-create.txt`, `r2-granted-cani.txt`, `r2-wait-granted.txt` |
| 02:01:46–02:03:06 | C5 with the grant at 1280 and 375, waiting for the repaint; the form (no Create) and the namespace pages at 375; `failures : []`, `walk exit=0` | `evidence/r2-walk-granted.txt` |
| 02:03:06 | The grant deleted explicitly; `can-i` `no`; 70 s waited, to 02:04:16 | `evidence/r2-grant-delete.txt`, `r2-removed-cani.txt`, `r2-wait-ungranted.txt` |
| 02:04:21–02:05:21 | C5 without the grant at 1280 and 375; `failures : []`, `walk exit=0` | `evidence/r2-walk-ungranted.txt` |
| 02:05:21–02:05:59 | After captures; the trap's delete found nothing; the final `can-i`, grant, Secret and pod-log captures | `evidence/r2-after-*.txt`, `final-*.txt`, `create-window-podlog.txt` |
| 02:07:58–02:08:24 | The repaint probe, without the grant: at +1 s `#main` still showed Home with `stale` `true`; at +3 s the new page was painted and `stale` `false`, for all three targets; no page error, nothing blocked | `evidence/probe-hash-repaint.txt` |

## Why the CA mode is "use the trusted bundle"

The form opens on "paste PEM". With no PEM, the server refuses `ca-data-invalid` before it reads a label: `validate()`
in `local-development/gsd/clusterconfig/writer.py` checks the token, then the TLS mode, then the labels. The walk
chose the trusted bundle so the only thing Create could be refused for was a label. The token string
`walk-478-not-a-token` is 20 characters, above the writer's floor of 8 (`MIN_TOKEN_LENGTH`). No server issued it,
and the refusal came before any request to a cluster.

## What the lab did not do

- The route guard on the dashboard's `/api/` let through GETs and exactly one `POST /api/clusterconfigs`, and only
  when that POST's body carried `__proto__`, so a build that dropped the key could not have written the Secret. It
  blocked nothing in any phase: four `the route guard blocked no request : []` lines (`evidence/walk-granted.txt`,
  `walk-ungranted.txt`, `r2-walk-granted.txt`, `r2-walk-ungranted.txt`).
- No chip was removed and Create was not pressed again.
- The first pass's hash-edit screenshots (`screenshots/04`–`06`, `44`–`46`, `50`–`52`) show Home, not the case in
  their names. They are kept as the record of that pass; the second pass's `64`–`66`, `70`–`72`, `104`–`106` and
  `110`–`112` show the repainted pages.
- `screenshots/77-granted-rerun-375-lookup.png` was taken 1.2 s after typing, while the lookup's Groups door still
  read "loading…". The namespace section it measures had painted.
- The two `ns-list` captures the walk took (steps 09 and 74) are not in this folder. `walk.py` photographed the
  first `table` in `#main`, which on the Namespace audit page is the "Cluster-wide direct grants" card's table,
  not the namespace list, and that table names the fleet account in its "Who is exposed" column. The list's
  values are the JSON `ns list` lines in `evidence/walk-granted.txt` and `evidence/r2-walk-granted.txt`; there is
  no picture of it.

## Files

- `scripts/walk.sh`: the whole walk in order (`walk.sh` for the first pass, `walk.sh rerun` for the second). It arms
  a shell `trap … EXIT` that deletes the grant by the run label before it creates the grant, and deletes it again
  explicitly when the granted phase ends.
- `scripts/walk.py`: the Playwright walk (`granted`, `ungranted`, `granted-rerun`, `ungranted-rerun`).
- `scripts/probe_hash.py`: the repaint probe (run with `PYTHONPATH=scripts`; it uses `walk.py`'s login and guard).
- `scripts/capture.sh`: the read-only captures. It redacts any `sha256~` value and replaces the fleet account's name,
  read from its Lease, with `<fleet account>`. Neither appears in any text file in this folder: a search for the
  account's name and for `sha256~` found 0 files. `walk.py` masks the name only where its selector matches (the
  fleet card on the Cluster Configurations page); the two captures that rendered it elsewhere were removed (above).
- `scripts/grant.yaml`: the temporary grant, labelled `walk.gsd.lab/run=ui-478-2026-09-28`.
- `evidence/`: every capture, its command line first and the instant it ran. Files prefixed `r2-` are the second
  pass's; `final-` files were captured after it.
- `screenshots/`: 51 PNGs. The number is the step (09 and 74 were removed, above), and the name gives the phase, the
  width, and the case.
