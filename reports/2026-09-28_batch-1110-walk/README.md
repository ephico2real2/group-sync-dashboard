# #390, #404, #441, #447 and #435 on the lab — 2026-09-28

**Outcome.** On the CRC lab, running application 1.11.0 at `f59e0ee782` (`evidence/before-version.txt`), `developer`
walked the Cluster Configurations tab in Chromium at 1280, 768 and 375 px. `scripts/walk.py walk` finished with
`failures : []` and `walk exit=0` (`evidence/walk-output.txt`).
- #390: a draft typed into Rotate on `mock-trusted` was still in the field after the 60-second repaint had replaced
  the field's node, at all three widths. Closing and reopening the panel emptied it. Overwrite was never pressed.
- #441: no two elements on the page shared an id (134 ids; 137 after four Refresh answers). Every `cc-refresh_<id>`
  and `cc-refresh-result_<id>` sat on its own card. Refresh on `shared-rnd` answered on `shared-rnd`'s card.
- #435: the six enabled clusters polled `ok` on 1.10.0 and polled `ok` on 1.11.0. The pod log from the 1.11.0 pod's
  start at 05:39:41Z to the capture at 05:57:33Z has 0 `cluster-unreachable` lines (`evidence/deploy-podlog.txt`). The
  only ones later are the #447 follow-up's own: 6 for the throwaway `walk-447` (`evidence/447-walk-podlog447.txt`).
- #404 was not run. The lab has no ConfigMap-declared cluster, and the brief's safe shape, a stanza with no
  `saTokenLookup`, is one the code refuses; every stanza it accepts declares `saTokenLookup: true`, and an enabled one
  is handed to the fleet lookup (the section below quotes the code).
- #447, in a follow-up run on a throwaway entry, `walk-447`: its Refresh answered `auth_failed` and the card offered
  Rejoin. `developer-walk`, with a password that lies inside it, was refused with the exact sentence
  `HTTP 422 — rejoin-password-within-username: …`, in the dialog and on the card, at all three widths. The password
  field was emptied. Nothing was sent: 0 `fleet-login`, `cluster-rejoin*` and `cluster-rejoined` lines, and 0 audit
  events for `developer-walk`. `scripts/walk_447.py walk` finished with `failures : []` and `walk exit=0`
  (`evidence/447-walk-output.txt`).
- The pod log for the walk window has 6 `cluster-refreshed` lines, all `by=developer`, 0 `fleet-login` lines and 0
  `cluster-rejoin` lines.

The main walk needed one temporary change to the lab, a grant, which was removed afterwards (`can-i` `no` → `yes` →
`no`). A fresh login after the tier cache had expired got `403` on `/api/clusterconfigs` (`evidence/after-tier.txt`).
The #447 follow-up needed the same grant again, under its own label, and the throwaway Secret. Both were removed by
that label, and discovery retired `walk-447` (`evidence/447-*.txt`). There was no Helm, no `release-crc.sh` and no
Argo CD change, and no other object was created. The kept PVCs have the same UIDs before and after the walk. The fleet Lease stayed at
`resourceVersion` 5127386 with no holder, and `shared-qa`'s Secret stayed at 2981054.

## Definition of Done

| Issue | Row | Verdict | Evidence |
|---|---|---|---|
| #390 | A half-typed Rotate token survives the minute's repaint, and a close and reopen empties it | PASS | `evidence/walk-output.txt`, per width: typed `{"equals_draft": true, "length": 22, "type": "password"}`. After 65 s: one `GET /api/clusterconfigs` `[200]`, and the marker set on the field's node was gone, so the node had been replaced. The new node read `{"repainted": true, "equals_draft": true, "length": 22, "type": "password"}`. Closed: `null`, meaning no field. Reopened: `{"length": 0}`. Screenshots `02`–`04`, `10`–`12`, `15`–`17-*-rotate-*.png`. The field is `type=password` in every capture. The value was read through the DOM, as a comparison and a length, and was never printed. Overwrite was never pressed: `no write request was attempted (the route guard blocked none): []`, and the `gsd-cluster-mock-trusted` Secret's `resourceVersion` read 993483 after the walk (`evidence/after-secret-rvs.txt`), the value every read of the 2026-09-27 walk recorded (`../2026-09-27_epic-c-walk-432/evidence/end-secrets.txt`, `rv=993483`); this walk took no read of it before the grant. |
| #404 | The header counts a ConfigMap-declared (GitOps) cluster under ConfigMap, with its chip `ConfigMap <name> → Secret <name>` and the discovery line | NOT RUN | The lab has no ConfigMap-declared cluster: `oc get configmaps -l 'groupsync-dashboard.io/config-type in (onboard,sideload)'` answered `No resources found` before and after (`evidence/*-onboarding.txt`). The header reads `in-cluster 1 values 4 Secret 23 ConfigMap 0`, with no ConfigMap chip on any card (`"configmap_cards": []`) (`01`, `09`, `14-*-header.png`). No throwaway ConfigMap was created, because the code allows no stanza that avoids a fleet login: see "Why #404 has no throwaway ConfigMap". |
| #441 | Refresh ids are unique, and Refresh on `shared-rnd` lands on its own card | PASS | `id check` at each width: `"duplicates": []` over 134 ids. Buttons: `cc-refresh_dashboard`, `…_mock-privateca`, `…_mock-selfsigned`, `…_mock-trusted`, `…_shared-qa`, `…_shared-rnd`, each on the card of the same name. Result: `cc-refresh-result_shared-rnd` on `shared-rnd`, reading `Refresh: connected · 2026-09-28T05:54:55Z — authenticated as system:serviceaccount:group-sync-operator:group-sync-dashboard-cluster-poller, server v1.35.6`. At 1280, after four answers: 137 ids, `"duplicates": []`, `"mismatched": []`, 4 results. Screenshots `05`, `13`, `18-*-refresh-shared-rnd.png`. |
| #447 | The refused admin reads why: `HTTP 422 — rejoin-password-within-username: …` | PASS | The follow-up run on the throwaway `walk-447` (`evidence/447-walk-output.txt`, at 1280, 768 and 375 px):<br>• Refresh answered `Refresh: auth_failed · 2026-09-28T06:10:29Z — 401 Unauthorized — token invalid or expired`, and the card offered `Rejoin…` (`19`, `22`, `25-*-447-refused-rejoin-offered.png`).<br>• With `developer-walk` and a password inside it typed, the dialog read exactly `HTTP 422 — rejoin-password-within-username: the password must not be the username or a part of it, ignoring case and surrounding spaces; it was not sent`. The password field was then empty (`"password_length": 0`), and the username stayed (`20`, `23`, `26-*-447-dialog-422.png`).<br>• The card's line read `Rejoin: HTTP 422 — ` followed by the same sentence (`21`, `24`, `27-*-447-card-rejoin-line.png`).<br>• The three POSTs to `/rejoin` answered `[422, 422, 422]`.<br>Nothing was sent. From 06:08:28Z the pod log has 0 `fleet-login`, 0 `cluster-rejoin-review`, 0 `cluster-rejoined`, 0 `cluster-rejoin-failed` and 0 `fleet-lookup` lines, 0 lines naming the fleet account, and 3 `cluster-refreshed cluster=walk-447 … by=developer outcome=auth_failed` (`evidence/447-walk-podlog447.txt`). The OAuth audit log since 06:08:28Z has `developer-walk, all: 0; authorize: 0` and `fleet account, all: 0`; `developer` has 1 authorize, the walk's own login at 06:10:25Z (`evidence/447-after-audit.txt`). The same read over the main walk's window found its two `developer` logins, so the read works (`evidence/447-sanity-audit.txt`). The main walk found no card that offered Rejoin, with `shared-qa` left alone: `cards offering Rejoin (#447 needs one): []`. |
| #435 | The lab's clusters still poll as before the deploy | PASS | On 1.10.0, all six enabled clusters were `ok` at `2026-09-28T04:54:01Z` (`evidence/before-1.10.0-polls.txt`). On 1.11.0 they were `ok` at the first poll, `05:40:13Z`–`05:40:14Z` (`evidence/before-1.11.0-first-polls.txt`), and `ok` as served at `05:54:12Z`–`05:54:13Z` (`evidence/walk-api-polls.json`). The six are `dashboard`, `mock-privateca`, `mock-selfsigned`, `mock-trusted`, `shared-qa` and `shared-rnd`. The pod log from the 1.11.0 pod's creation at 05:39:41Z to the capture at 05:57:33Z has 894 lines, with 0 `cluster-unreachable`, 0 `fleet-login` and 0 `ERROR or Traceback` lines (`evidence/deploy-podlog.txt`); the 6 `cluster-unreachable` lines after 06:09:55Z are the #447 follow-up's throwaway `walk-447` (`evidence/447-walk-podlog447.txt`). The six were `ok` in each of these three snapshots, so there is no finding; the store keeps no poll between them (see below). See "Where the 1.10.0 status comes from" for what the store keeps. |
| walk | The pod log: `cluster-refreshed` lines `by=developer`, and no `fleet-login` | PASS | `evidence/walk-podlog.txt`, from 05:52:01Z: `cluster-refreshed lines: 6, of them by=developer: 6` (3 × `shared-rnd outcome=ok`, 3 × mock `outcome=unreachable`); `fleet-login lines: 0`; `cluster-rejoin / cluster-rejoined lines: 0`; `ERROR or Traceback lines: 0` |
| walk | No page error, no sideways scroll | PASS | `no uncaught page errors: []` and `no 'Dashboard API error'` at each width; `scrollWidth, innerWidth` `[1280, 1280]`, `[768, 768]`, `[375, 375]` |

## How the walk ran

| When (UTC) | Step | File |
|---|---|---|
| 05:49:37–39 | 1.11.0, commit `f59e0ee782`; PVC UIDs; `can-i`: `no`; no object with the walk's label; the fleet Lease; `shared-qa`'s `resourceVersion`; no onboarding ConfigMap; the poll status in two store backups | `evidence/before-*.txt` |
| 05:52:24 | The grant: ClusterRole `gsd-walk-crb-update` (`update` on `clusterrolebindings`) and ClusterRoleBinding `gsd-walk-crb-update-developer`, both labelled `walk.gsd.lab/run=batch-1110-2026-09-28`. `can-i`: `yes` | `scripts/grant.yaml`, `evidence/grant-create.txt`, `evidence/granted-*.txt` |
| 05:52:42 | The rollouts: the 1.10.0 ReplicaSet at 04:53:38Z, the 1.11.0 one at 05:39:41Z, `strategy=Recreate`, and the four backups | `evidence/before-rollouts.txt` |
| 05:52:24 → 05:53:45 | A 70 s wait before the login. The dashboard caches each tier decision for `visibilityTierTtlSeconds: 60`. | — |
| 05:53:45 → 05:57:18 | The walk: `whoami` `"cluster_admin": true`, `/api/clusterconfigs` `200`, then the three widths | `evidence/walk-output.txt`, `screenshots/` |
| 05:57:31 | The grant removed by its label. Then: `can-i` `no`; `oc get … -l walk.gsd.lab/run=batch-1110-2026-09-28` `No resources found`; PVC UIDs; the Lease; `shared-qa`; no onboarding ConfigMap; 1.11.0 still serving | `evidence/grant-delete.txt`, `evidence/after-*.txt` |
| 05:57:33 | The pod log for the walk window (from 05:52:01Z) and since the pod's creation (from 05:39:41Z) | `evidence/walk-podlog.txt`, `evidence/deploy-podlog.txt` |
| 05:58:49 | The cluster Secrets' `resourceVersion`s after the walk. This folder holds no pre-flight read of them; the comparison is with the 2026-09-27 walk's `end-secrets.txt` (`mock-trusted` `rv=993483`, `shared-qa` `rv=2981054`) | `evidence/after-secret-rvs.txt` |
| 05:58:57 | A fresh login as `developer` after the tier cache had expired: `"cluster_admin": false`, `/api/clusterconfigs` `403`, no Cluster Configurations tab | `evidence/after-tier.txt` |
| 06:01:49–50 | The end state, once more: `can-i` `no`; no object with the walk's label; the same PVC UIDs; the Lease at 5127386 with no holder; `shared-qa` at 2981054; no onboarding ConfigMap; the pod log from 05:52:01Z still 6 `cluster-refreshed` (all `by=developer`), 0 `fleet-login`, 0 `cluster-rejoin` | `evidence/final-*.txt` |
| 06:08:28 | #447 follow-up, before: `can-i` `no`; no object with `walk.gsd.lab/run=batch-1110-447-2026-09-28`; the same PVC UIDs; the Lease at 5127386 with no holder; `shared-qa` at 2981054; 0 audit events | `evidence/447-before-*.txt` |
| 06:09:37 | The grant again (`scripts/grant-447.yaml`, the new label); `can-i`: `yes`. `scripts/secret-447.sh apply` created `gsd-cluster-walk-447` (uid `c5f436d0-b5b7-4f22-b89e-a6c5e06935f9`) from a mode-600 manifest: config keys `bearerToken` and `tlsClientConfig` (`{"insecure":false}`) | `evidence/447-grant-create.txt`, `evidence/447-granted-*.txt`, `evidence/447-secret-apply.txt`, `evidence/447-applied-secret.txt` |
| 06:09:55 | Discovery cycle 8: `added=walk-447`, `credential=bearer`. The first poll answered `auth_failed` (401) | `evidence/447-walk-podlog447.txt` |
| 06:10:27 → 06:10:39 | The #447 walk at the three widths | `evidence/447-walk-output.txt`, `screenshots/19`–`27` |
| 06:10:56–57 | The Secret, then the grant, deleted by the label. `can-i` `no`; both label queries empty; the same PVC UIDs, Lease and `shared-qa` | `evidence/447-secret-delete.txt`, `evidence/447-grant-delete.txt`, `evidence/447-after-*.txt` |
| 06:14:55–56 | Discovery cycle 9: `removed=walk-447`; `walk-447: its Secret is gone; the poll thread stops (history kept)` | `evidence/447-walk-podlog447.txt` |
| 06:15:09 | The pod log and the OAuth audit log from 06:08:28Z | `evidence/447-walk-podlog447.txt`, `evidence/447-after-audit.txt` |
| 06:15:26 | A fresh login as `developer`: `"cluster_admin": false`, `/api/clusterconfigs` `403` | `evidence/447-after-tier.txt` |

**The repaint (#390).** The walk sets a data attribute on the Rotate field's node before leaving the page alone. The
page's 60-second timer re-fetched `/api/clusterconfigs` and replaced `#main`, so the node that carried the attribute
was gone after 65 s at each width. The field drawn in its place held the 22 typed characters. They are kept in
`view.clusterRotateDraft`, in JavaScript memory: `local-development/gsd/static/index.html#function ccCredential`
draws the field from it, and `local-development/gsd/static/index.html#function wireClusterConfig` writes it on
every keystroke and deletes it when the panel closes. The walk would have waited up to three timer ticks, because the timer
skips the repaint when the payload has not changed. One tick sufficed at every width.

**The guard.** A Playwright route over `/api/clusterconfigs*` let reads and Refresh through and aborted anything
else, so pressing Overwrite, Delete or Rejoin could not have reached the dashboard. It blocked nothing.

## Why #404 has no throwaway ConfigMap

The brief allowed one throwaway onboarding ConfigMap, but only in a shape that causes no login of any kind and no
fleet-password read: no `saTokenLookup` and no `ldapConnectionBootstrap`. The code refuses every such stanza. Every
stanza it accepts declares `saTokenLookup: true`; an enabled one is handed to the fleet lookup. A disabled one
(`enabled: false`) is accepted and never looked up, but it never gets the generated Secret either, and the row's chip
`ConfigMap <name> → Secret <name>` names that Secret, which only the lookup writes:
- A ConfigMap stanza must declare `saTokenLookup: true` and may carry no credential
  (`local-development/gsd/config.py#parse_cluster_entries`):
  ```python
  if "tokenEnv" in entry or "tokenFile" in entry:
      raise ConfigError(f"{where}: a ConfigMap may not carry a credential reference")
  ...
  if entry.get("saTokenLookup") is not True:
      raise ConfigError(f"{where}: a ConfigMap needs saTokenLookup: true")
  ```
  Onboarding parses both config types, `onboard` and `sideload`, with this rule: `parse_cluster_entries([entry],
  source, remote_host=host)` (`local-development/gsd/clusterconfig/onboarding.py#discover_onboarding`). A refused stanza becomes the
  finding "use saTokenLookup: true, no credential or token reference", in the same function.
- An accepted stanza with no generated Secret yet is handed to the lookup scheduler:
  `# A current declaration whose output is missing is handed to the EXISTING lookup scheduler.`
  then `clusters.extend(pending.values())`, both in `discover_onboarding`.
- The scheduler retrieves every enabled lookup cluster: `pending = {c.name: c for c in
  self.settings.effective_clusters() if c.enabled and c.credential_kind == CREDENTIAL_LOOKUP}`
  (`local-development/gsd/poller.py#Poller._retrieve_pending`). It takes the fleet account's Lease,
  `self._fleet_lease(client, namespace, fleet_account(self.settings, cluster))`, and runs `lookup(...)`, in the
  same method. `lookup` is "the whole retrieval for one cluster: password, login, read, revoke"
  (`local-development/gsd/fleetlookup.py#lookup`).

So the safe shape does not exist, and the one shape that avoids a login, `enabled: false`, could never show the row's
`→ Secret <name>`; the row is NOT RUN. The header still shows the #404 layout on this lab:
`by source` `in-cluster 1 values 4 Secret 23 ConfigMap 0`, and the discovery line
`5 Secrets carry the discovery label · last read …`.

## #447: the throwaway entry, and why it cannot reach the fleet password

The follow-up run needed a card whose Refresh answers `auth_failed`. It uses one throwaway cluster Secret,
`gsd-cluster-walk-447`, built by `scripts/secret-447.sh` in the shape of the 2026-09-27 `walk-authfail` entry
([its README](../2026-09-27_refresh-and-shared-url/authfail/README.md)). Its data is `name: walk-447` and
`server: https://api.crc.testing:6443`. Its `config` holds a random `sha256~` bearer token that no server issued, and
the `tlsClientConfig` copied read-only from `gsd-cluster-shared-qa` (`{"insecure":false}`). Its `config` carries no
`saTokenLookup`, `userSelfLogin` or `ldapConnectionBootstrap`. Its only annotation is
`kubectl.kubernetes.io/last-applied-configuration`, which `oc apply` wrote. That annotation holds the manifest,
the bogus token included; the capture redacts it (`evidence/447-applied-secret.txt`). `oc create` would not have
written it. The Secret has no `token-source` or `lookup-account` annotation. It carries the discovery label and the run label
`walk.gsd.lab/run=batch-1110-447-2026-09-28`. The token is generated inside the script and never printed. It is
written only to a mode-0600 `mktemp` manifest, which the exit trap removes.

The code shows that nothing in this shape can reach the fleet password. The password is read in three places only,
and each is gated on something this Secret does not declare:
- **The lookup** (`local-development/gsd/fleetlookup.py#lookup`) runs from `Poller._retrieve_pending` for
  `c.enabled and c.credential_kind == CREDENTIAL_LOOKUP` (`local-development/gsd/poller.py#Poller._retrieve_pending`).
  For this Secret `credential_kind` is `bearer`: `if self.token_value is not None: return "bearer"` is tested before
  `if self.sa_token_lookup: return CREDENTIAL_LOOKUP` (`local-development/gsd/config.py#ClusterConfig.credential_kind`).
  The parser sets `sa_token_lookup=mode == "saTokenLookup"`, where `mode` comes only from `config` keys this Secret
  does not carry (`local-development/gsd/clusterconfig/parser.py#parse_secret`).
- **The daily ping** (`local-development/gsd/poller.py#Poller._ping_accounts`) counts a cluster toward an account only
  when `c.enabled and c.token_source == CREDENTIAL_LOOKUP and c.lookup_account`, or
  `c.enabled and c.connection_mode is not None and named`. `token_source` and `lookup_account` come only from the
  Secret's `token-source` and `lookup-account` annotations (`local-development/gsd/clusterconfig/reader.py#discover`),
  and this Secret has neither. `connection_mode` is `None` without `saTokenLookup` or `userSelfLogin`.
- **Self-login** (`local-development/gsd/selflogin.py`) takes only
  `c.enabled and c.credential_kind == CREDENTIAL_SELF_LOGIN` clusters.

The two presses cannot reach it either:
- **Refresh** "NEVER LOGS IN. No FleetLogin, no lookup, no self-login session, no CredentialGate"
  (`local-development/gsd/clusterconfig/writer.py#refresh`). It probes with the stored bogus token, and the API
  server answers an unknown token with 401.
- **Rejoin** runs `rejoin.check(cluster, settings, username, password)` before it looks up the gate, takes the
  one-at-a-time lock or calls `rejoin.rejoin`, which is the only step that logs in (`local-development/gsd/api.py`,
  the `/api/clusterconfigs/{name}/rejoin` route). `check` refuses a password inside the username, ignoring case and
  surrounding spaces (`local-development/gsd/rejoin.py#check`):
  ```python
  folded = password.strip().casefold()
  if folded and folded in username.casefold():
      raise WriteRefused("rejoin-password-within-username", "the password must not be the username or a part of it, "
                                                           "ignoring case and surrounding spaces; it was not sent")
  ```
  A `WriteRefused` that is not a conflict answers 422 with `f"{exc.code}: {exc.detail}"`.

## Where the 1.10.0 status comes from (#435)

The store keeps one poll outcome per cluster, overwritten by each poll: `poll_outcome` has `cluster_id` as its
primary key, and `record_poll` is an upsert (the `CREATE TABLE IF NOT EXISTS poll_outcome` schema and `local-development/gsd/store.py#Store.record_poll`). The Deployment
is `Recreate`, so the 1.10.0 pod's log went with the pod. The history that remains is the backup files, which the walk
opened read-only (`mode=ro&immutable=1`):
- `gsd-20260928T045402.100313Z.db`: 1.10.0's pod started at 04:53:38Z, and all six clusters were `ok` at
  04:54:01Z. This is 1.10.0's first poll. Its later polls, until 05:39:41Z, are not kept anywhere the walk could read.
- `gsd-20260928T054014.212287Z.db`: 1.11.0's pod started at 05:39:41Z, and all six were `ok` at 05:40:13Z–05:40:14Z.

## A note, not a defect

The discovery line reads `5 Secrets carry the discovery label`, but six Secrets carry it
(`evidence/labelled-secrets.txt`). The sixth, `gsd-cluster-mock-refusal`, is refused as a configuration finding. The
page counts the live clusters that come from a Secret: `clusters.filter((c) => !c.retired && !c.host &&
String(c.source || "").startsWith("secret:")).length` (`local-development/gsd/static/index.html#function clusterConfigPage`). It does not
count the Secrets that carry the label. The number matches #404's comment there, "Discovery counts live Secret
storage"; the sentence says more than that. So the line reads `5 Secrets carry the discovery label` while 6 do,
because the sixth, `gsd-cluster-mock-refusal`, is refused as a finding; the wording goes on an issue of its own.

## What is redacted

The header screenshots (`01`, `09`, `14`) show the `fleet account` row. The account's name is covered with a grey
box after capture, and the rest of the row is unchanged. `capture.sh` replaces any `sha256~` token with
`sha256~<redacted>`; the only one that reached a capture was `walk-447`'s bogus token, inside the `last-applied`
annotation, and it is redacted. The Lease capture reads its `resourceVersion`, holder and renew time only, and
the Secret captures read metadata only.

## Screenshots

27 files, each cropped to its element (the header section, one cluster card, or the Rejoin dialog). They are numbered
in the order they were taken. The main walk is at 1280 (`01–08`), 768 (`09–13`) and 375 (`14–18`) px, and the #447
follow-up at 1280 (`19–21`), 768 (`22–24`) and 375 (`25–27`) px:

| Per width | What it shows |
|---|---|
| `…-header.png` | the tab's header: `by source`, the ConfigMap selector and the discovery line (#404) |
| `…-rotate-typed.png`, `…-rotate-after-repaint.png`, `…-rotate-reopened-empty.png` | Rotate on `mock-trusted`, masked (#390) |
| `…-refresh-shared-rnd.png` | Refresh's answer on `shared-rnd`'s own card (#441) |
| `06`–`08-1280-refresh-mock-*.png` | the three mocks' Refresh answers, none of which offers Rejoin (#447's precondition) |
| `…-447-refused-rejoin-offered.png` | `walk-447`'s Refresh `auth_failed` and the `Rejoin…` button (#447) |
| `…-447-dialog-422.png` | the Rejoin dialog after the press: the username kept, the password field empty, the 422 sentence (#447) |
| `…-447-card-rejoin-line.png` | the card after Cancel: the `Rejoin: HTTP 422 — …` line under the Refresh line (#447) |

At 375 px the dialog is taller than the viewport, so `26-375-447-dialog-422.png` shows its visible part. That
cuts the heading and the sentence's last words ("it was not sent"); the full sentence is the DOM read in
`evidence/447-walk-output.txt`. The card captures (`21`, `24`, `27`) were taken 300 ms after Cancel, while the dialog's
backdrop was still fading, so they look paler than the others.

## How to run it again

The password is read from `crc` into the environment of the one command that uses it. It is never printed or
written to a file, and no script here contains it:

```sh
export KUBECONFIG=<the lab kubeconfig>
F=reports/2026-09-28_batch-1110-walk
for k in version pvcs cani grant lease sharedqa onboarding rollouts; do "$F/scripts/capture.sh" "$k" before; done
"$F/scripts/capture.sh" polls before-1.10.0 /data/backup/<a backup taken on the old version>
oc create -f "$F/scripts/grant.yaml"                       # then wait more than 60 s (the tier cache)
GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
  local-development/.venv/bin/python "$F/scripts/walk.py" walk
oc delete clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io \
  -l walk.gsd.lab/run=batch-1110-2026-09-28
for k in cani grant pvcs lease sharedqa onboarding version; do "$F/scripts/capture.sh" "$k" after; done
"$F/scripts/capture.sh" podlog walk <the instant before the grant, RFC 3339>
GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
  local-development/.venv/bin/python "$F/scripts/walk.py" after   # more than 60 s after the removal
```

The #447 follow-up:

```sh
export GSD_WALK_RUN=walk.gsd.lab/run=batch-1110-447-2026-09-28
for k in version pvcs cani grant lease sharedqa secret; do "$F/scripts/capture.sh" "$k" 447-before; done
"$F/scripts/capture.sh" audit 447-before "${T0}"                  # T0: the instant before the grant, RFC 3339
oc create -f "$F/scripts/grant-447.yaml"
"$F/scripts/secret-447.sh" apply                # then wait for `discovery … added=walk-447` (up to 300 s)
GSD_WALK_REJOIN_PASSWORD=walk \
  GSD_UI_PASSWORD="$(crc console --credentials -o json | jq -r .clusterConfig.developerCredentials.password)" \
  local-development/.venv/bin/python "$F/scripts/walk_447.py" walk   # the Rejoin password: any part of developer-walk
"$F/scripts/secret-447.sh" delete
oc delete clusterroles.rbac.authorization.k8s.io,clusterrolebindings.rbac.authorization.k8s.io \
  -l walk.gsd.lab/run=batch-1110-447-2026-09-28
for k in cani grant secret pvcs lease sharedqa version; do "$F/scripts/capture.sh" "$k" 447-after; done
"$F/scripts/capture.sh" podlog447 447-walk "${T0}"; "$F/scripts/capture.sh" audit 447-after "${T0}"
```

`walk_447.py` as committed has one change from the run: its unused `gone` mode was removed. The `walk` path that ran
is unchanged.

`walk.py` exits non-zero on an uncaught page error, a visible "Dashboard API error", a blocked write request, or any
failed expectation. The header screenshots need the fleet account's name masked before they are committed.
