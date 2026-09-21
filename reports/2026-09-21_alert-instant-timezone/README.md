# An alert's instant renders in the configured timezone — #271 / PR #279

Captured from the hermetic harness (`tests/test_ui.py`'s `dash` fixture, the seeded store), so the
same seeded overdue CR is shown in every frame and the only variable is the display zone.

## The change

`#271` put the **absolute instant** into an alert's `detail`, because a relative age recomputed per
request is a different string on every poll and defeats the unchanged-poll repaint skip. The
operator's requirement on top of that: *"it must match the Timezone set"*.

So the division is: **the server states the instant, the page presents it.** The payload keeps the
raw UTC stamp — which is what keeps the fingerprint stable — and the alert row localises it at render
time, exactly as every other timestamp on the page does.

## Before (`01-before-chicago.png`)

```
last sync at 2026-09-21T11:47:21Z, schedule '0 * * * *' (> 2 intervals) — the schedule has stopped firing
```

The wire format, shown to the reader, ignoring the deployment's zone.

## After — the same instant, three zones

| file | display zone | the row |
|---|---|---|
| `02-after-chicago.png` | `America/Chicago` | `last sync at 2026-09-21 06:47:06 CDT, …` |
| `03-after-utc.png` | none (UTC) | `last sync at 2026-09-21 11:47:06Z, …` |
| `04-after-tokyo.png` | `Asia/Tokyo` | `last sync at 2026-09-21 20:47:06 GMT+9, …` |

`02-after-chicago.png` also shows the whole alerts card, so the other seven alerts are visibly
unchanged — only the two kinds that carry an instant were touched.

## Why the browser does the formatting, not the server

`fmtTime`'s own comment states the reason, and it is a correctness point rather than a style one:

> The abbreviation depends on the instant: 2026-01-15 in America/New_York is EST and 2026-07-15 is
> EDT. The server can only report the zone as it stands right now, so stamping that on every row
> would mislabel every timestamp on the other side of a DST boundary.

The browser ships the full IANA database, so asking it per-timestamp is both correct and free.

## Two things the substitution is careful about

- It runs **after `esc()`**. The pattern is digits, `-`, `:`, `T` and `Z` — none of which escaping
  alters — so escaping stays intact and no unescaped server text is ever substituted back in.
- A **run id** (`20260921T171114.745714Z-058e`) carries no dashes or colons in its stamp and cannot
  match. There is a test pinning that, because converting one would corrupt a filename.

## Reproducing

The captures were taken by a temporary class in `tests/test_ui.py` that drives `setDisplayZone` and
screenshots the alerts card; it was removed after the PNGs were committed. The behaviour itself is
held by `TestAnAlertsInstantRendersInTheConfiguredZone`, which fails on the unpatched page with

```
AssertionError: an alert row shows the raw wire stamp instead of the configured zone:
  ["last sync at 2026-09-21T11:44:46Z, schedule '0 * * * *' (> 2 intervals) — …"]
```
