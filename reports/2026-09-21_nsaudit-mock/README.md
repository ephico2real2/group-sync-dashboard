# Namespace audit — the capture, the mock and the render check

Two scripts, both of which print every number quoted anywhere in this folder.

## `capture.py` — what the live page holds (step 1)

Drives the deployed dashboard at `https://group-sync-dashboard.apps-crc.testing` through the
oauth-proxy as `kubeadmin` and reads the page's features off the rendered DOM together with the
payloads behind them. Output: the `live-*.png` captures and `capture.json`, which
`docs/design/nsaudit-feature-capture.md` quotes.

```sh
GSD_UI_USER=kubeadmin GSD_UI_PASSWORD="$(cat ~/.crc/machines/crc/kubeadmin-password)" \
  local-development/.venv/bin/python reports/2026-09-21_nsaudit-mock/capture.py
```

Measured on `v0.30.0 · a90f1b277b`, cluster `dashboard-rnd`, poll `2026-09-21T05:06:29Z`:
`total 11` direct grants over 5 rollup entries, `excluded_platform 24`, 106 namespaces,
13 groups and 3 grants bound cluster-wide, `errors: []`.

The narrowed tiers are not in the walk — the self tier is cookie-only, so a browser signed in as an
administrator cannot reach them. They were read through the pod's loopback, which believes
`X-Forwarded-User` exactly as the app believes the proxy:

```sh
oc --context=crc-admin -n group-sync-dashboard exec <pod> -c dashboard -- \
  curl -s -H 'X-Forwarded-User: jdoe' localhost:8080/api/clusters/dashboard-rnd/user-bindings
```

## `render-check.py` — the mock (step 4)

Renders `docs/design/nsaudit-mock.html` headlessly, drives every control and asserts the resulting
state, re-renders at 375 / 393 / 768 / 1280, and measures contrast from the painted pixels — the body
wash is `background-attachment: fixed`, so the accent bloom is placed against the viewport and cannot
be derived from the token values. Output: the `mock-*.png` captures and `render-check.json`. Captures are cropped to the first 2,400 px
— a full-page shot of this page is 21,354 px tall at 375 — and nothing measured depends on the image:
every geometry assertion is computed over the whole document in the browser.

```sh
local-development/.venv/bin/python reports/2026-09-21_nsaudit-mock/render-check.py
```

107 checks, all passing. The last of them is the one that matters most: **every one of the 40 caveats
the live page carries is reachable in the mock**, asserted across nine driven states (the four tiers,
the filtered and unfiltered flat list, a search that matches nothing, and two namespace pages) plus the
`title` attributes, because the export buttons carry their honesty sentence as a tooltip. A caveat
behind a disclosure counts — the disclosures are opened — and one that renders in no state at all does
not. That check found two caveats whose branch the lab never produces (a refused namespace read, a
namespace with no recorded change); both are drawn as labelled shapes rather than left in the code
where no reader would meet them.

It also found a bug in itself: the sweep first reported two caveats missing because it *toggled* the
disclosures that the drive step had already opened, closing them. It sets the state explicitly now.

What it caught while the mock was being built, none of which `node --check` can see:

| found | fix |
|---|---|
| the 6-column namespace index laid out 541 px wide inside a 375 px viewport — reachable only by scrolling the card sideways | the index stacks compactly below 620 px; document height at 375 fell from 41,078 px to 21,354 px |
| five KPI tiles in a 2-column grid painted the empty sixth slot as a sixth, empty, grey tile | the gridlines are each tile's own shadow, clipped at the container's edge, instead of a 1 px gap over a coloured background |
| the cluster-scope marker in the tier partition rendered nothing — a `clip-path` clips the element's outline with everything else it paints | the shape moved inside an unclipped box, which carries the ring |

## Contrast, measured rather than modelled

Painted ground at the top of the viewport, x=640, with every child of `<body>` hidden so the wash
paints alone:

| | y=0 | y=120 | y=300 | y=420+ |
|---|---|---|---|---|
| live page (`--page-2: #eef0f4`) | `#e9e0e9` | `#eeeaee` | `#f6f6f6` | `#f9f9f7` |
| mock (`--page-2: #e3e6ef`, proposed) | `#dfd7e4` | `#e6e3eb` | `#f2f3f4` | `#f9f9f7` |

The tightest text in that band is the active tab label. On the live page the tightest element is the
version line — `--text-muted` at 12 px, **4.57:1**, 0.07 above the bar — which is why the mock's
version line is `--text-secondary`. In the mock every top-band element clears AA in both themes, the
tightest being the active tab at **4.76:1** (light) and **5.09:1** (dark).
