# Addendum — #311's `auth_failed` branch, on a throwaway entry — 2026-09-27

**Outcome.** This addendum ran on the same lab as the parent walk: application 1.4.0 at `6a83e3edda`
(`evidence/before-version.txt`). The throwaway entry was `walk-authfail`. It is a cluster Secret whose bearer token
is a random `sha256~` string that no server issued.

Pressing Refresh on it as `developer` answered `auth_failed` with the Rejoin hint at 1280, 768 and 375 px.
`scripts/walk_authfail.py walk` ended with `failures : []` and exit 0 (`evidence/walk-output.txt`). The answer was:

> `Refresh: auth_failed · 2026-09-27T20:50:25Z — 401 Unauthorized — token invalid or expired` / `The stored
> credential was refused. Next step: Rejoin (#316), not built yet — until then, replace the credential where it is
> written.`

The pod log has three `cluster-refreshed cluster=walk-authfail credential=bearer by=developer outcome=auth_failed`
lines and 0 `fleet-login` lines (`evidence/walk-podlog.txt`).

## Definition of Done

| Issue | Row | Verdict | Evidence |
|---|---|---|---|
| #311 | On an entry with a refused token (a throwaway, never `shared-qa`), Refresh reads `auth_failed` and offers Rejoin | PASS | `walk-output.txt`, `[1280]`, `[768]` and `[375]`: `auth_failed with the Rejoin hint`; `42-1280-`, `43-768-`, `44-375-walk-authfail-refused.png`; the pod log's three `outcome=auth_failed` lines, `by=developer`; `fleet-login lines: 0` |

## The Secret and the grant, in order

| When (UTC) | Step | File |
|---|---|---|
| 20:48:11–14 | 1.4.0 at `6a83e3edda`; PVC UIDs; `can-i update clusterrolebindings --as=developer`: `no`; no grant and no Secret carrying `walk.gsd.lab/run=authfail-2026-09-27` | `evidence/before-*.txt` |
| 20:48:14 | The grant created (`scripts/grant.yaml`, the parent's with the new label); `can-i`: `yes` | `evidence/grant-create.txt`, `evidence/granted-*.txt` |
| 20:48:22–23 | `scripts/secret.sh apply` created `gsd-cluster-walk-authfail` (uid `a060ccc6-d1e3-4565-b9b1-878ac21b8f68`). It carries the discovery label and the walk's label; `name: walk-authfail`; `server: https://api.crc.testing:6443`; `config` keys `bearerToken` and `tlsClientConfig`. The TLS block is copied from `gsd-cluster-shared-qa` (`{"insecure":false}`, the trusted bundle), so TLS verifies and only the token is wrong. The manifest was a mktemp file, removed on exit. | `evidence/secret-apply.txt`, `evidence/applied-secret.txt` |
| 20:49:59 | Discovery cycle 46: `added=walk-authfail`. `shared-api-url … clusters=shared-qa,shared-rnd,walk-authfail state=appeared`. The first poll answered `auth_failed` (`401 Unauthorized`). | `evidence/walk-podlog.txt` |
| 20:50:23 | The banner named three entries: `shared-qa, shared-rnd, walk-authfail declare the same API URL: https://api.crc.testing:6443.` | `40-1280-banner-three.png`, `41-1280-walk-authfail-before.png` |
| 20:50:25 / 27 / 28 | Refresh pressed at 1280 / 768 / 375 px: `auth_failed` with the Rejoin hint each time | `42`–`44-*-walk-authfail-refused.png` |
| 20:50:37 | `scripts/secret.sh delete`, by label; the label query then returned `[]` | `evidence/secret-delete.txt`, `evidence/deleted-secret.txt` |
| 20:54:59 | Discovery cycle 47: `removed=walk-authfail`. `shared-api-url … clusters=shared-qa,shared-rnd state=appeared`. At 20:55:00: `walk-authfail: its Secret is gone; the poll thread stops (history kept)` | `evidence/walk-podlog.txt` |
| 20:55:21 | The banner named `shared-qa` and `shared-rnd` only. `walk-authfail` was retired: `"enabled": false, "retired": true`, no chip, no Refresh button. | `45-1280-banner-two.png`, `46-1280-walk-authfail-retired.png`, `evidence/gone-output.txt` |
| 20:55:31 | The grant removed by its label. `can-i`: `no`; the grant and the Secret, by label, both empty. PVC UIDs as before; 1.4.0 still serving. | `evidence/grant-delete.txt`, `evidence/after-*.txt` |
| 20:56:56 | A fresh login as `developer`, after the tier cache: `"cluster_admin": false`, `/api/clusterconfigs` `403`, no tab | `evidence/after-tier.txt` |

**The kept PVCs.** `group-sync-dashboard-data` is `f065b7a4-535c-4ef1-868c-58f5afee4953` and
`group-sync-dashboard-report-artifacts` is `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3`, both before and after
(`evidence/before-pvcs.txt`, `evidence/after-pvcs.txt`).

## What the measurements add

- **Which request refuses.** `evidence/probe-status-codes.txt` records three requests to the same API, with a random
  `sha256~` token and TLS verification off (`curl -k`); it measures status codes only. The token gets `401` from
  `/version` and `401` from `users/~`; `/version` with no token at all gets `200`. The API refuses a presented
  invalid token even on `/version`, so the probe stops at its first request. `/version` answers anonymously only when
  no token is sent.
- **The retired row stays.** Like the parent walk's 10 disabled entries at this URL, `walk-authfail` remains on the
  tab as a retired, disabled card: the history is kept, by design. It joins no shared-URL group
  (`45-1280-banner-two.png`).
- **The shared-URL log line** reports a group changing size as the old group `cleared` and the new one `appeared`.
  At cycle 47 that includes a `WARNING … clusters=shared-qa,shared-rnd state=appeared` for a pair that already
  shared the URL before the walk.
- **The pod log names the entry beyond Refresh.**
  - Each poll: a `cluster-unreachable … outcome=auth_failed` line, with the action "rotate it in this cluster's
    Secret".
  - An audit-log capture warning.
  - One binding-refresh warning.
  - At 20:50:18, `visibility tier for 'developer' is indeterminate (auth_failed …) — failing closed to the self view
    for this request`. That is `walk-authfail`'s `remote-sar` visibility, which Secret-sourced entries get by default
    on this lab.

  None of these is a login: `fleet-login lines: 0`.

## How to run it again

```sh
export KUBECONFIG=<the lab kubeconfig>
F=reports/2026-09-27_refresh-and-shared-url/authfail
for k in version pvcs cani grant secret; do "$F/scripts/capture.sh" "$k" before; done
oc create -f "$F/scripts/grant.yaml"
"$F/scripts/secret.sh" apply              # then wait for `discovery … added=walk-authfail` (up to discoveryIntervalSeconds, 300)
GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
  local-development/.venv/bin/python "$F/scripts/walk_authfail.py" walk
"$F/scripts/secret.sh" delete             # then wait for `discovery … removed=walk-authfail`
GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
  local-development/.venv/bin/python "$F/scripts/walk_authfail.py" gone
"$F/scripts/capture.sh" podlog walk <the instant before the grant, RFC 3339>
oc delete clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io \
  -l walk.gsd.lab/run=authfail-2026-09-27
for k in cani grant secret pvcs version; do "$F/scripts/capture.sh" "$k" after; done
```

Wait more than 60 s after creating the grant before the first login (the tier cache). The parent's
`../scripts/walk.py after` is the fresh-login check once the grant is gone.
