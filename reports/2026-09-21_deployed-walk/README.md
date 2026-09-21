# The deployed head, walked — main @ `19ffb25b4a`

Walked 2026-09-21 against the CRC lab, deployed through `local-development/release-crc.sh --argocd`
(Argo CD Application `group-sync-dashboard`, `targetRevision=19ffb25b4a`, Synced/Healthy, image
`0.30.0-19ffb25b4a`, commit verified in-pod rather than only in the Application spec).

Nine pull requests merged into this head today. `walk.py` asserts every figure below, so a regression
fails the walk rather than the reader; each line it prints is a measurement.

## The tab bar (#253 → #256)

Fourteen tabs. Before this they wanted 1234 px against the 1140 px the bar has inside `.wrap`'s
1180 px cap, so the row wrapped at **every** desktop width and left `Cluster Configurations` alone on
a second line above the fold of every page.

| viewport | tabs | rows | sideways scroll |
|---|---|---|---|
| 1440 | 14 | **1** | none |
| 1280 | 14 | **1** | none |
| 1180 | 14 | **1** | none |
| 768 | 14 | 2 | none |
| 375 | 14 | 4 | none |

The wrap at 768 and 375 is the designed behaviour (#152/#166) — it is what keeps every tab inside a
phone viewport — and the walk asserts it is still there.

## The heading ladder (#253 → #256)

```
h1  18px w700 ls-0.36px
h2  15px w700 ls-0.225px
```

against the `w600` with no tracking that shipped before. `.home .answer h1` had carried w700/−0.02em
since #158; this extends that treatment to the ladder rather than inventing one.

## Platform namespaces in the Namespace audit index (#257 → #258)

```
67 platform namespaces hidden — 1 of them has a direct grant. Show them ·
openshift-*, kube-*, and five named ones — the rule the Home page uses.
```

**39 rows** listed instead of 106; **Show them** restores all 106 and focus stays on the control.

The classification is the rule `gsd/home.py` has always shipped, applied to this index for the first
time — it had exactly one caller, the Home page.

### What the walk surfaced

The one hidden namespace **with** a finding is `openshift-console-user-settings`: two `view` grants,
to `developer` and `jane.smith`. It is ranked in the worklist **above** while hidden from the index
**below**, and no sentence on the page reconciles the two. The count clause exists precisely so a
reader is told hiding cost them something — the sentence that explains it is the first item of
#261's remaining tranche.

## Files

| file | what |
|---|---|
| `walk.py` | the walk and its assertions — re-runnable |
| `01-tabbar-{1440,1280,1180,768,375}.png` | the bar across widths |
| `02-nsaudit-filtered.png` | the index with platform namespaces hidden |
| `03-nsaudit-platform-shown.png` | after **Show them** |
