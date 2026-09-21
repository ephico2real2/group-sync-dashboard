# The report form names its cluster, walked — `feat/267-cluster-in-report-forms` @ `97462a1824`

Walked 2026-09-21 against the CRC lab, deployed through `local-development/release-crc.sh --argocd`
(Argo CD Application `group-sync-dashboard`, `targetRevision=97462a1824`, Synced/Healthy, image
`0.30.0-97462a1824`, commit verified in-pod rather than only in the Application spec). Before this
run the lab held `0.30.0-977365e25f` — main at the merge-base — so nothing of #267 had run here.

This is the evidence the hermetic tests cannot be: the control against a **real estate of five
configured clusters** rather than a two-cluster fixture. `walk.py` asserts every figure below, so a
regression fails the walk rather than the reader.

## The control, on five clusters (`01-control-default.png`, `02-all-five.png`)

```
clusters: ['dashboard', 'mock-privateca', 'mock-selfsigned', 'mock-trusted', 'shared-rnd']
nav     : dashboard | count: 1 of 5 clusters
```

The chips are the nav's list in the nav's order; `dashboard` is the primary and carries
`LOOKUPS · TOTALS`; it is the only checked chip and it is `aria-disabled` — the last cluster cannot
be unchecked. `all 5` takes the count to `5 of 5 clusters` and **no** chip is disabled then, because
none of them is the last one.

## The fan-out: five runs, five seals, one action (`03-fan-out.png`)

```
batch   : 5 clusters requested — 5 done
  dashboard       done  sha256 cc21609f5543…
  mock-privateca  done  sha256 1c979ab7e083…
  mock-selfsigned done  sha256 b97f7246e087…
  mock-trusted    done  sha256 508ce2642320…
  shared-rnd      done  sha256 6ee03f5a610e…
```

One run per cluster, in the order asked, each sealed on its own with its own download buttons. The
page says `5 clusters, one run each`, and the totals line beside it (`62 groups · 85 changes`) is the
**primary's**, which the control states in words: *lookups and the totals preview are dashboard's*.

**What this run does NOT prove.** The walk was written expecting `shared-rnd` — the credential-less
cluster of SPEC_S3 — to fail its own run and leave the others sealed, which would have exercised
partial failure on real data. It did not: `shared-rnd` has a snapshot on this lab and sealed like the
rest. So partial failure remains covered **only** by the API test
(`test_one_cluster_the_snapshot_lacks_fails_its_own_run_and_no_other`), and the browser test's
`ghost` is still an injected id rather than a configured cluster. That gap is stated rather than
papered over.

**A pre-existing observation, corroborated.** The walk was run twice against the same head with the
same parameters, and every sha256 changed between the two runs (`97edc4b0806d` → `cc21609f5543` for
`dashboard`). That is not this PR: the run facts — "Generated at" and "Run id" — sit inside
`sections`, so they are inside the hash. OB1-lite reached the same conclusion independently in the
review by diffing the canonical documents, where base-vs-head and head-vs-head differed on exactly
those two lines. Worth an issue; it is not a #267 regression.

## The fleet-path note (#269 V1) (`04-fleet-note.png`, `05-dismissed.png`)

Pick a user on `dashboard`, visit Overview (the fleet leaves the cluster null, #172), come back to
Reports:

```
note    : Cluster changed from dashboard to the fleet view — users picked on dashboard was cleared;
          the lookups now offered are dashboard's. dismiss
```

On the head before the fix this read *"changed from dashboard to — … the lookups now offered are 's"*,
because the change recorded `to: null` and the boot cycle then stamped the first cluster outside
`navigate()`, so no chokepoint pass ever rewrote it. The walk asserts both that the fleet is named
and that the old garbled forms (`" to — "`, `"are 's"`) are absent, and that the lookup really went
(`.rp-tag` count 0) — the note must not be the only thing that changed.

`dismiss` then clears it, and the walk confirms the note is gone.

V2 (a poll failure after 202 worded as a refusal) is not walked: it needs an aborted request, which
the browser test does with `page.route(...).abort()`.

## Reproducing

```
GSD_UI_USER=<user> GSD_UI_PASSWORD=<pw> local-development/.venv/bin/python walk.py
```
