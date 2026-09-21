# The Cluster Configurations tab on CRC — the walk behind #230 S2 (PR #237), item 6 of #230's plan

Deployed head `aa5f832` (`feat/230-cluster-configurations-tab` with main at `20101e9` merged in, through the Argo
Application, history entry 31; `running : aa5f832155 — verified in-pod`), walked with `walk.py` through the OAuth
proxy as kubeadmin, Chromium 1280×900 then 375×740, then as `developer` for the refusal. Every line below is the
script's own output; the fleet is the lab's real rig at walk time (01:18–01:19Z, 2026-09-21): the in-cluster host
`crc-local`, four Secret-sourced clusters, one malformed Secret, four retired rows. Argo's history shows no other
deploy between #247's (`20101e93a9`, entry 30) and this one, so nothing else was on the lab during the walk.

| claim | measured |
|---|---|
| the tab exists for a reader with the tier | fourteen tab buttons, the last `Cluster Configurations`; `whoami.clusterconfig {view: true, manage: true}` for kubeadmin |
| the lead and the head | `Cluster Configurations 9 clusters`; `namespace group-sync-dashboard`; `selector groupsync-dashboard.io/secret-type=cluster`; `by source in-cluster 1 values 0 Secret 8`; `discovery 8 Secrets carry the discovery label · last read 2026-09-21 01:17` (`last_discovery 2026-09-21T01:17:38Z` — the pod's start-up discovery, two seconds after the roll) |
| the host: source chip, credential kind, TLS, connection | `crc-local in-cluster enabled` — `server https://kubernetes.default.svc`; `credential serviceAccount set read-only — the pod's own ServiceAccount`; `tls verified ca: serviceAccount`; `connection ok reachable 2026-09-21 01:18`; foot `the pod's own in-cluster ServiceAccount — not a Secret` |
| `mock-trusted` (Secret, no `tlsClientConfig`) | chip `Secret gsd-cluster-mock-trusted`; `bearerToken set`; `tls verified ca: trusted-bundle`; labels `environment=lab`, `groupsync-dashboard.io/tls-mode=trusted`; `ok reachable 2026-09-21 01:18` |
| `mock-privateca` (Secret, `caData` 780 chars) | chip `Secret gsd-cluster-mock-privateca`; `bearerToken set`; `tls verified ca: caData`; labels `environment=lab`, `…/tls-mode=privateca`; `ok reachable 2026-09-21 01:18` |
| `mock-selfsigned` (Secret, `insecure: true`) | chip `Secret gsd-cluster-mock-selfsigned`; `bearerToken set`; `tls insecure` (the warning badge); labels `environment=lab`, `…/tls-mode=selfsigned`; `ok reachable 2026-09-21 01:18` |
| `shared-rnd` — this CRC through its public endpoint, the SA-token shape | chip `Secret gsd-cluster-shared-rnd`; `server https://api.crc.testing:6443`; `bearerToken set` (the Secret's token is 1 377 chars, its `caData` 9 612 — measured with `oc get secret … -o json`, never shown by the page); `tls verified ca: caData`; labels `environment=rnd`; `visibility inherit`, `identity same-as-host`; `ok reachable 2026-09-21 01:18` |
| the credential never leaves the API | every live row's credential reads `bearerToken set` or `serviceAccount set`; the API rows carry `credential: "bearer"` / `"in-cluster"` and no token field |
| the retired rows say why, not a dash | `crc-tls-cadata`, `crc-tls-default`, `crc-tls-insecure` (all `https://api.crc.testing:6443`) and `mock` (`https://mock-openshift:6443`): each `disabled`, `tls unknown its source no longer describes it`, `visibility —`, `identity —`, `labels none`, foot `its Secret is gone — the history is kept, the cluster is disabled`; the API rows carry `retired: true, enabled: false, tls: null`; `crc-tls-default` keeps its last outcome verbatim — `unreachable 2026-09-20 16:53 ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: self-signed certificate in certificate chain (_ssl.c:1082)` — the others `ok reachable` at `2026-09-20 16:53` / `17:23`, their `last_poll` frozen where their Secret vanished |
| the findings card | one finding: `gsd-cluster-mock-refusal` · `insecure-with-ca` · `tlsClientConfig.caData and tlsClientConfig.insecure=true are both set: choose one` (that Secret carries `caData` 780 chars **and** `insecure: true`, measured) |
| the Add-cluster form and its YAML twin | typed `walk-demo`, `https://api.walk.example:6443`, a token, `use the trusted bundle`, `self-only`, `same-as-host`, label `environment=walk`; the pane: `name: "gsd-cluster-walk-demo"`, `namespace: "group-sync-dashboard"`, both labels quoted (`"environment": "walk"`), `config: \|-` with `{"tlsClientConfig":{"insecure":false},"bearerToken":"<redacted>"}`, `visibility: "self-only"`, `identity: "same-as-host"`, `enabled: "true"`; `twin {name_quoted, label_quoted, token_absent, redacted, insecure_false, enabled_string}` all true |
| this deployment's writes are off (the chart default; `environments/crc.yaml` sets no `clusterConfig`) | `create_button 0`, `test_button 0`; the note `This deployment does not write Secrets — the dashboard is a reader by design, and clusterConfig.secrets.writes.enabled is off (the default). Copy the YAML beside the form and apply it the way your other Secrets arrive; the next discovery picks it up. …`; the head's `Describes a labelled Secret in group-sync-dashboard.`; every live Secret row's credential adds `rotate it where the Secret is written — this deployment's writes are off` and its foot `declared by its Secret — delete it there; this deployment's writes are off` |
| 375 px | `no-x-overflow True`, the widest of `#cc-head`, the cards, `#cc-findings`, `#cc-add`, `#cc-yaml` at 333 px inside `innerWidth 375` |
| a reader without the tier (`developer`: `oc auth can-i get secrets -n group-sync-dashboard --as=developer` → `no`, `create secrets` → `no`) | thirteen tab buttons, no `Cluster Configurations`; the cold URL `#page=clusters` paints the refusal card — `Withheld, not empty. This page lists every cluster this dashboard reads … How the fleet is wired is not a self reader's business. For administrators only. …` — with `whoami.clusterconfig {view: false, manage: false}`, `data.clusterconfigs.forbidden true`, and **no request** to `/api/clusterconfigs` (`performance.getEntriesByType('resource')` → `api-requested False`) |
| errors | `[]` on both sessions — `walk exit=0` |

Captures: `01-tab-1280.png` (1280×4894, full page), `02-add-form-1280.png` (the `#cc-add` section, 1140×1065),
`03-tab-375.png` (375×7883, full page), `04-add-form-375.png` (335×2003), `05-refusal-denied-1280.png` (1280×900).

## A measured fact about discovery, and a UX follow-up

A Secret written **by GitOps** is discovered on the binding cadence — `bindingIntervalSeconds`, 300 s on the lab — and
`last_discovery` advances on that tick, not on the write (measured tonight on `gsd-cluster-shared-rnd`, written
13 minutes before this walk's deploy and discovered by the pod's start-up cycle). A Secret written **by the tab** wakes
the discovery thread (`Poller.request_discovery()`, the `"discovery": "requested"` in the write's response), so it
lands within seconds. The form's note says only "the next discovery picks it up" — it does not say how long that is
for the GitOps path. Left as a UX follow-up for #244 / #230 rather than a behaviour change here: the sentence should
name the cadence (or the `last read` stamp in the head should say when the next read is due).
