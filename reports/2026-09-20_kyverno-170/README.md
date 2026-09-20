# The Kyverno module on CRC — the walk behind #170 (steps 1–4, 6–8, the page)

Deployed head `0989e4b` (`feat/170-kyverno-module`, through the Argo Application; `running : 0989e4b66b —
verified in-pod`), walked with `walk.py` through the OAuth proxy as kubeadmin, Chromium 1280×900 then
375×740, ninety seconds after the roll so the first binding refresh had read the reports. Every line
below is the script's own output; the numbers are the lab's real reports (the 09-19 and 09-20 discovery
records: 115 reports, 667 legacy results, 9 CEL results, three breaker circuits).

| claim | measured |
|---|---|
| the API's payload | `{"present": true, "api_group": "wgpolicyk8s.io/v1alpha2", "policy_kinds": [the five CEL kinds], "reports": 115, "legacy_results": 667, "other_results": 0, "breaker_total": 12505, "breaker_drops": null, "results": {"pass": 9, "fail": 0, …}, "policies": 1, "total": 0}` |
| the tiles, the deprecated family flagged | `[['CEL policies', '1', ''], ['Failing', '0', ''], ['Warnings', '0', ''], ['Passing', '9', ''], ['Skipped', '0', ''], ['Not shown (deprecated family)', '667', 'flag-warning']]` |
| the deprecated-family note | `667 results on this cluster come from the deprecated ClusterPolicy/Policy family and are not shown. The API says that family will be removed …` |
| the breaker: three circuits summed, no drop observed | `No report has been dropped by the breaker (kyverno_breaker_total 12505, no kyverno_breaker_drops exported — a counter appears on its first increment) …` |
| the policy and its report counts | `[['ValidatingPolicy', 'restrict-nco-config-writers', 'on', 'off', 'Audit', 'Fail', 'yes ·', '9', '0', '0', '0', '0']]` |
| the findings behind the controlled-kind switch, on the wire | `Findings · 0 \| rows 0` after `?controlled=true` (every CEL result on the lab is a pass) |
| the history | `Changes · 0` (the first read is a baseline) |
| 375 px | `no-x-overflow True`; `errors : []` |

Captures: `01-kyverno-state.png`, `02-policies-and-findings.png`, `03-375.png`.
