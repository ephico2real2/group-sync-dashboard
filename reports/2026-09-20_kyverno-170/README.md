# The Kyverno module on CRC — the walk behind #170 (steps 1–4, 6–8, the page)

Deployed head `9e8ef02` (`feat/170-kyverno-module` after the three-seat pass — the grants `list` only, every served report
group read, the breaker the host cluster's, readiness from `conditionStatus` — through the Argo Application;
`running : 9e8ef02fe1 — verified in-pod`; the walks at `0989e4b` and `da46d4e` read the same lines but the policy row's), walked with `walk.py` through the OAuth proxy as kubeadmin, Chromium 1280×900 then
375×740, ninety seconds after the roll so the first binding refresh had read the reports. Every line
below is the script's own output; the numbers are the lab's real reports (the 09-19 and 09-20 discovery
records: 115 reports, 667 legacy results, 9 CEL results, three breaker circuits).

| claim | measured |
|---|---|
| the API's payload | `{"present": true, "api_group": "wgpolicyk8s.io/v1alpha2", "policy_kinds": [the five CEL kinds], "reports": 115, "legacy_results": 667, "other_results": 0, "breaker_total": 12839, "breaker_drops": null, "results": {"pass": 9, "fail": 0, …}, "policies": 1, "total": 0}` |
| the tiles, the deprecated family flagged | `[['CEL policies', '1', ''], ['Failing', '0', ''], ['Warnings', '0', ''], ['Passing', '9', ''], ['Skipped', '0', ''], ['Not shown (deprecated family)', '667', 'flag-warning']]` |
| the deprecated-family note | `667 results on this cluster come from the deprecated ClusterPolicy/Policy family and are not shown. The API says that family will be removed …` |
| the breaker: three circuits summed, no drop observed | `No report has been dropped by the breaker (kyverno_breaker_total 12839, no kyverno_breaker_drops exported — a counter appears on its first increment) …`; the payload's `"breaker_configured": true` (the pod's loopback) is what lets the page tell a failed scrape from an unset URL |
| the policy and its report counts | `[['ValidatingPolicy', 'restrict-nco-config-writers', 'on', 'off', 'Audit', 'Fail', 'yes', '9', '0', '0', '0', '0']]` — Ready alone: the earlier walks printed `conditionStatus.message` (`skip generating ValidatingAdmissionPolicy: not enabled.`) beside it, which the CRD defines as the VAP-generation note, not a readiness note (OB3); the payload's `"ready": true, "note": ""` for this policy; a condition that is not True would print as error text |
| the findings behind the controlled-kind switch, on the wire | `Findings · 0 \| rows 0` after `?controlled=true` (every CEL result on the lab is a pass) |
| the history | `Changes · 0` (the first read is a baseline) |
| 375 px | `no-x-overflow True`; `errors : []` |

Captures: `01-kyverno-state.png`, `02-policies-and-findings.png`, `03-375.png`.
