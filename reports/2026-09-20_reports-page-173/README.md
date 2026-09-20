# The Reports page on CRC — the walk behind #173's Definition of Done

Deployed head `7748b69` (the PR branch `feat/173-reports-page` at `36883bb` merged with `main` at
`88e6ea5`, through the Argo Application; `running : 7748b69e21 — verified in-pod`), walked with
`reports_walk.py` through the OAuth proxy as kubeadmin, Chromium 1280×800 then 375×740. Every line
below is the script's own output.

| DoD item | measured |
|---|---|
| the catalogue: 11 reports, category colour, 700-weight names, the key under each, the count | `rows : 11`, `count chip: 11 available`, `weight : 700`, `keys : [namespace-access … access-certification]`; `form open on arrival: False` |
| a click opens the form with the panel's top visible, no manual scrolling | `landed : form top/bottom/viewport [100, 462, 800]` after clicking the last row |
| `report` as a position: deep link, Back, Forward, the label from `from` | `hash: #page=reports&cluster=crc-local&report=access-certification`, `back: ← all reports`; after a second pick `← Access certification pack`; the control returns to `access-certification`; the browser's Back leaves `form present: 0`; Forward reopens it |
| a pasted link lands too (found by the first walk: top 849 on an 800 px viewport before `36883bb`) | `deep : back control: ← all reports | form top: 12` |
| 375 px: zero overflow, the catalogue scrolls in its own container | `375px : form top/viewport/no-x-overflow/wrap [12, 740, True, 'auto']` |
| no uncaught error on any step | `errors : []` |

Captures: `01-catalogue.png`, `02-click-lands-in-view.png`, `03-back-control-names-previous.png`,
`04-deep-link.png`, `05-375-form.png`, `06-375-catalogue.png`.
