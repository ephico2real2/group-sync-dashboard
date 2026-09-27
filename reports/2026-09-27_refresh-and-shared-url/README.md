# #311 Refresh and #314 the shared API URL warning, on the lab — 2026-09-27

**Outcome.** On the CRC lab, running application 1.4.0 at `6a83e3edda` (`evidence/before-version.txt`), `developer`
walked the Cluster Configurations tab in Chromium at 1280, 768 and 375 px. `scripts/walk.py` finished with
`failures : []` and `walk exit=0` (`evidence/walk-output.txt`).
- #314: the ⚠️ banner named `shared-qa`, `shared-rnd` and `https://api.crc.testing:6443`. Both of those cards
  carried the `shared API URL` chip and a hint naming the other card. None of the 10 disabled entries at the same URL
  carried the chip.
- #311: Refresh on `shared-rnd` went from idle, to in flight, to `connected · <ISO-8601 UTC>`. The answer was still
  shown after the 60-second repaint had redrawn the card.
- The three enabled mock entries each answered `unreachable`: the mock has no `/version`. That was the only failed
  Refresh outcome observed in this walk.
- The pod log for the walk window has 12 `cluster-refreshed` lines, all `by=developer`, and 0 `fleet-login` lines.

The walk needed one temporary change to the lab, a grant, which was removed afterwards. A fresh login after the
tier cache had expired got `403` on `/api/clusterconfigs` (`evidence/after-tier.txt`). Nothing else changed: no Helm,
no `release-crc.sh`, no Argo CD change, and no edit to any Secret or value. The kept PVCs have the same UIDs before
and after the walk.

## Definition of Done

| Issue | Row | Verdict | Evidence |
|---|---|---|---|
| #314 | The ⚠️ banner on the tab names `shared-qa`, `shared-rnd` and `https://api.crc.testing:6443` | PASS | `walk-output.txt`, `banner text` at each width: `"⚠️ Shared API URL. shared-qa, shared-rnd declare the same API URL: https://api.crc.testing:6443. Each entry is still polled and counted on its own."`; the API's `warnings` in `evidence/api-clusterconfigs.json`; `01-1280-banner.png`, `14-768-banner.png`, `27-375-banner.png` |
| #314 | Both cards carry the `shared API URL` chip and hint | PASS | `shared-qa card` / `shared-rnd card`: `"chip": true` and `"Also declared by shared-rnd — …"` / `"Also declared by shared-qa — …"` at each width; `02/03`, `15/16`, `28/29-*-chip.png` |
| #314 | No chip on the disabled entries at the same URL | PASS | `disabled entries at the shared URL (10), chip shown`: all 10 `false`, at each width (`cm-demo-a`, `crc-tls-cadata`, `crc-tls-default`, `crc-tls-insecure`, `d2b-no-groups`, `d2b-no-sar`, `gitops-example-389`, `rnd-lookup`, `rnd-lookup2`, `verify-lookup`, all retired rows); three by name in `04–06`, `17–19`, `30–32-*-disabled-*.png` |
| #311 | Refresh idle | PASS | `idle button reads Refresh, enabled, no result line` at each width; `07`, `20`, `33-*-refresh-idle.png` |
| #311 | Refresh in flight, labelled | PASS | `"button": {"text": "Refreshing…", "disabled": true, "aria_busy": "true"}`, with the line `Refresh: probing /version and users/~ with the stored credential…`; `08`, `21`, `34-*-refresh-in-flight.png` |
| #311 | Refresh succeeded: `connected · <ISO-8601 UTC>` | PASS | `Refresh: connected · 2026-09-27T20:20:24Z — authenticated as system:serviceaccount:group-sync-operator:group-sync-dashboard-cluster-poller, server v1.35.6` (then `…20:21:38Z`, `…20:22:52Z`); `09`, `22`, `35-*-refresh-succeeded.png` |
| #311 | The same state after the 60-second repaint | PASS | after 65 s at each width: one `GET /api/clusterconfigs` (`[200]`), the result line's node replaced (`marker … null`), the text unchanged (`"same": true, "repainted": true, "polls": 1`); `10`, `23`, `36-*-refresh-after-repaint.png` |
| #311 | A failed Refresh on each of the three enabled mocks | PASS | `mock-privateca`, `mock-selfsigned`, `mock-trusted` each: `Refresh: unreachable · … — HTTP 404 on /version: {"detail":"Not Found"}`, with the red badge; `11–13`, `24–26`, `37–39-*-refresh-mock-*.png`. The `auth_failed` branch, which adds the Rejoin hint, was not exercised in this walk: Refresh was pressed on `shared-rnd` and the three mocks only, so the walk does not establish that no lab entry could return it. |
| #311 | The pod log: `cluster-refreshed` lines `by=developer`, no `fleet-login` | PASS | `evidence/walk-podlog.txt`: `cluster-refreshed lines: 12, of them by=developer: 12` (3 × `shared-rnd outcome=ok`, 9 × mock `outcome=unreachable`); `fleet-login lines: 0`; `ERROR or Traceback lines: 0` |
| both | No page error, no sideways scroll | PASS | `no uncaught page errors: []`, `no 'Dashboard API error'` and `scrollWidth / innerWidth` `[1280, 1280]`, `[768, 768]`, `[375, 375]` |

## How the walk ran

| When (UTC) | Step | File |
|---|---|---|
| 20:18:53–55 | 1.4.0, commit `6a83e3edda`; PVC UIDs; `can-i update clusterrolebindings --as=developer`: `no`; no object with the walk's label | `evidence/before-*.txt` |
| 20:19:01 | The grant created: ClusterRole `gsd-walk-crb-update` (`update` on `clusterrolebindings`) and ClusterRoleBinding `gsd-walk-crb-update-developer`, both labelled `walk.gsd.lab/run=refresh-shared-url-2026-09-27`; `can-i`: `yes` | `scripts/grant.yaml`, `evidence/grant-create.txt`, `evidence/granted-*.txt` |
| 20:19:01 → 20:20:06 | A 65 s wait before the login. The dashboard caches each tier decision for `visibilityTierTtlSeconds: 60`, so an earlier `no` for `developer` could otherwise still be served. | — |
| 20:20:18 → 20:24:00 | The walk: `whoami` `"cluster_admin": true`, `/api/clusterconfigs` `200`, then the three widths | `evidence/walk-output.txt`, `screenshots/` |
| 20:24:28 | The grant removed by its label; `can-i`: `no`; `oc get … -l walk.gsd.lab/run=…`: `No resources found`; PVC UIDs; 1.4.0 still serving | `evidence/grant-delete.txt`, `evidence/after-*.txt` |
| 20:24:30 | The pod log from 20:18:52 | `evidence/walk-podlog.txt` |
| 20:25:52 | A fresh login as `developer`, after the tier cache has expired: `"cluster_admin": false`, `/api/clusterconfigs` `403`, no Cluster Configurations tab | `evidence/after-tier.txt` |

**The in-flight state.** The probe is fast. At 1280 px the click was at `20:20:24Z`, and the pod logged
`cluster-refreshed … outcome=ok` at `20:20:24.707`. To photograph the in-flight state, `walk.py` turns on Chromium's
own network emulation (`Network.emulateNetworkConditions`, 4000 ms latency) before the click, then lifts it after
the capture. The pod log's instant shows the server received and answered the request at once; the emulation delays
the answer's arrival in the page, so the page stays in flight until it lands. Nothing on the lab was slowed or
changed.

**The repaint.** Before the 65 s wait, the walk sets a data attribute on the result line's node. The page's
60-second timer re-fetched `/api/clusterconfigs` and replaced `#main`, so the node carrying the attribute was gone.
The line drawn in its place read the same, because the answer is kept in the page's state (`view.clusterRefresh`),
not in the DOM.

## A note, not a defect

The three mock entries poll `ok`: their card's connection row reads `ok reachable` beside the refused Refresh in
`11-1280-refresh-mock-privateca.png`. Refresh answers `unreachable` for them because it probes `/version` first, and
the mock app has no such route: `local-development/mock-app/mock_app/app.py` registers the group, user, identity,
namespace, binding, config, node and OAuth APIs, and `/healthz`, but no `/version`. The word `unreachable` for an
HTTP 404 from a server that did answer is the poller's own: `local-development/gsd/kube.py` maps every status
`>= 400` other than 401 and 403 to `UNREACHABLE`. Refresh reuses the poller's words by design. A real OpenShift API
serves `/version`, so this appears only on the mocks.

## Screenshots

39 files, each cropped to its element (the header section or one cluster card). They are numbered in the order the
walk took them, at 1280 (`01–13`), 768 (`14–26`) and 375 (`27–39`) px:

| Per width | What it shows |
|---|---|
| `…-banner.png` | the tab's header section with the ⚠️ Shared API URL banner |
| `…-shared-qa-chip.png`, `…-shared-rnd-chip.png` | the chip in the heading and the hint under the server row |
| `…-disabled-cm-demo-a.png`, `…-disabled-crc-tls-cadata.png`, `…-disabled-crc-tls-default.png` | three disabled entries at the same URL, with no chip |
| `…-refresh-idle.png`, `…-refresh-in-flight.png`, `…-refresh-succeeded.png`, `…-refresh-after-repaint.png` | Refresh on `shared-rnd`, in order |
| `…-refresh-mock-privateca.png`, `…-refresh-mock-selfsigned.png`, `…-refresh-mock-trusted.png` | the refused Refresh on each mock |

## How to run it again

The password is read from `crc` into the environment of the one command that uses it. It is never printed or
written to a file, and no script here contains it:

```sh
export KUBECONFIG=<the lab kubeconfig>
F=reports/2026-09-27_refresh-and-shared-url
for k in version pvcs cani grant; do "$F/scripts/capture.sh" "$k" before; done
oc create -f "$F/scripts/grant.yaml"                       # then wait more than 60 s (the tier cache)
GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
  local-development/.venv/bin/python "$F/scripts/walk.py" walk
oc delete clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io \
  -l walk.gsd.lab/run=refresh-shared-url-2026-09-27
for k in cani grant pvcs version; do "$F/scripts/capture.sh" "$k" after; done
"$F/scripts/capture.sh" podlog walk <the instant before the grant, RFC 3339>
GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
  local-development/.venv/bin/python "$F/scripts/walk.py" after   # more than 60 s after the removal
```

`walk.py` exits non-zero on an uncaught page error, a visible "Dashboard API error" or any failed expectation.
