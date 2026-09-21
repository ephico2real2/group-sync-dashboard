# #253 on the deployed dashboard — the tab bar on one row, and the heading ladder

Walked 2026-09-21 against the CRC lab at `https://group-sync-dashboard.apps-crc.testing`, deployed
through `local-development/release-crc.sh --argocd` (Argo CD, Application `group-sync-dashboard`,
`targetRevision=76d4e1e970`, Synced/Healthy, image `0.30.0-76d4e1e970`). Every number below is a line
`walk.py` printed; the script asserts each one, so a regression fails the walk rather than the reader.

## The tab bar

Fourteen tabs. Before this change they wanted 1234 px against the 1140 px the bar has inside
`.wrap`'s 1180 px cap, so the row wrapped at **every** desktop width and left `Cluster Configurations`
alone on a second line above the fold of every page.

| viewport | tabs | rows | content width | bar width | sideways scroll |
|---|---|---|---|---|---|
| 1440 | 14 | **1** | 1122 | 1122 | none |
| 1280 | 14 | **1** | 1122 | 1122 | none |
| 1180 | 14 | **1** | 1122 | 1122 | none |
| 768 | 14 | 2 | 1122 | 728 | none |
| 375 | 14 | 4 | 1122 | 335 | none |

`content width` and `bar width` agree from 1180 up because `.tabs` is `inline-flex` and shrinks to its
content once it fits — that is "1122 px of tabs inside the 1180 px cap", not a coincidence. The spare
room is 1140 − 1122 = 18 px.

The wrap at 768 and 375 is the **designed** behaviour (#152/#166): it is what keeps every tab inside a
phone viewport. The walk asserts it is still there, and that neither width scrolls sideways — the half
of the trade that had to survive.

## The heading ladder

Measured on three pages, all identical:

```
h1  18px w700 ls-0.36px
h2  15px w700 ls-0.225px
h3  13px w700 ls-0.13px
```

against the `w600` with no tracking that shipped. `.home .answer h1` has carried w700/−0.02em since
#158; this extends that treatment to the ladder rather than inventing one, and the `.card >`-scoped
tracking that made the same `h2` look different in different places is gone.

## Files

| file | what |
|---|---|
| `walk.py` | the walk, with its assertions — re-runnable |
| `01-access-granted-1440.png`, `02-namespace-audit-1440.png`, `03-overview-1440.png` | the three pages at 1440 |
| `04-access-granted-{1280,1180,768,375}.png` | the bar across widths |
