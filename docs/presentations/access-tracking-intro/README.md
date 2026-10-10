# OpenShift Access Tracking & Reporting — the introduction deck

A 19-slide deck that introduces the OCP Access Tracking Dashboard in two parts: **why** (for leadership and audit:
silent access failures, self-service, quarterly access-review evidence) and **how** (for the platform team: tiers,
architecture, reporting, credentials, operations, rollout). Made on 2026-10-08 against application 5.8.0, chart
0.70.12.

| File | What it is |
|---|---|
| `deck.pdf` | the deck to present or send: 19 pages, 1920 × 1080 |
| `deck.html` | the same slides as one page, which opens in any browser; the slide markup is the source |
| `images/` | the screen-sized light screenshots the slides show, cropped from the walk below at full resolution |

The architecture slides show figures 1, 3, 5 and 6 of [architecture-overview.md](../../guides/architecture-overview.md),
from `docs/diagrams/architecture/`; they are not copied here.

## Where every claim comes from

- **Screenshots:** the light-theme walk of the lab at 5.8.0,
  [reports/2026-10-08_light-walk-5.8.0](../../../reports/2026-10-08_light-walk-5.8.0/README.md). Each crop is the top
  1440 × 900 of one page (the certification pack's two crops are 750 px wide), never a full-page capture.
- **Numbers:** each slide's footer names its source in the repository: the README (the reference cluster's 9
  bindings), `environments/crc.yaml` (the quarterly schedule), the chart's values and PrometheusRule (retention, 20
  alerts), and the reports catalogue.
- **Speaker notes:** one per slide, in `deck.html` (hidden when presenting or printing).

## Rebuilding the PDF

`deck.pdf` is `deck.html` printed by Chromium (Playwright, from the repository's venv):

```sh
local-development/.venv/bin/python - <<'PY'
from pathlib import Path
from playwright.sync_api import sync_playwright
deck = Path("docs/presentations/access-tracking-intro/deck.html").resolve()
with sync_playwright() as p:
    page = p.chromium.launch().new_page(viewport={"width": 1920, "height": 1080})
    page.goto(deck.as_uri(), wait_until="networkidle")
    page.pdf(path=str(deck.with_name("deck.pdf")), width="1920px", height="1080px", print_background=True)
PY
```

Change a slide in `deck.html`, rebuild the PDF, and commit both together.
