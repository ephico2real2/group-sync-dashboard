# The namespace picker, the reviewer prefill and the totals preview on CRC — the walk behind #143 phases 2–3

Deployed head `6c8b960` (`feat/143-picker-preview` after its three review passes, through the Argo Application;
`running : 6c8b96016f — verified in-pod`; the walk at `ef91c74` read the same lines; the first walk at `44587ce` read the same lines with "1 namespaces" and no
`(cluster-scoped)` option — the review changed both), walked with `walk.py` through the OAuth proxy as kubeadmin, Chromium 1280×900 then
375×740. Every line below is the script's own output.

| #143 claim | measured |
|---|---|
| the totals preview refuses an unscoped form before Generate does | `totals  : unscoped → preview: select at least one namespace, by selector, mnemonic or explicit name` |
| the explicit names are a picker over the poll's namespaces, `(cluster-scoped)` first | `picker  : 107 namespaces discovered on crc-local, first ['(cluster-scoped)', 'beta-prod', 'beta-rnd', 'beta-uat', 'ca-tutorial']` |
| type-ahead narrows it | `typeahead: 'group-sync' → ['group-sync-dashboard', 'group-sync-operator']` |
| a pick gives the totals of that run | `totals  : group-sync-dashboard → 1 namespace · 0 group bindings · 0 user bindings` |
| the POST and the answer | `POST {"report":"namespace-access","cluster":"crc-local","params":{"namespaces":["group-sync-dashboard"]}} → 200 {"totals":{"namespaces":1,"group_bindings":0,"user_bindings":0},"truncated":false,"snapshot":"2026-09-20T08:39…"}` |
| Generate never disabled by it | `generate: enabled True` |
| the reviewer prefilled from the signed-in name | `reviewer: prefilled 'kubeadmin' | signed in as kubeadmin` |
| a required field's refusal shown as the preview | `totals  : certification, unscoped → preview: campaign is required` |
| 375 px | `no-x-overflow, picker options [True, 107]`; `Advanced open True | picker input top 120` |
| no uncaught error | `errors  : []` |

Captures: `01-namespace-picker.png`, `02-totals-beside-generate.png`, `03-reviewer-prefilled.png`,
`04-375-picker.png`.
