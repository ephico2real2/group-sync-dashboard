# SPEC_S4b §5 — the live check of the ServiceAccount token lookup (#284)

Head `3b15ee0ac8` (`feat/s4b-sa-token-lookup`, rebased as `cd00f2f` onto the merged spec), app 0.31.0,
chart 0.50.0, deployed to the reference cluster (OpenShift 4.22.7) with **plain Helm** —
`release-crc.sh --values environments/crc-lookup.yaml` — because this lab's Argo Application pins
`clusters` in `helm.valuesObject` by design and would not read a values stanza. The account was the
htpasswd `developer`, never the fleet account (SPEC_S4a's rule), granted the estate's own
token-reader Role on `group-sync-operator` for the duration; the password sat in
`group-sync-dashboard/gsd-fleet-account` under the chart's one-Secret grant. Every object the check
created was removed afterwards and the release was put back on `environments/crc.yaml`.

`account=<redacted>` on the log lines is the redactor, not a gap: CRC's `developer` password is the
word `developer`, so the emit helper strips the account name too. The Secrets' `lookup-account`
annotation shows it.

## Every write this check made on the lab, and its removal

Declared here first, as the business owner's standing rule requires: read-only `oc get` is not
listed; everything that created, patched or deleted an object is.

| object | why | scope | removed by (proof: `08-removal-proof.txt`) |
|---|---|---|---|
| RoleBinding `group-sync-operator/group-sync-dashboard-cluster-poller-token-reader-0` → User `developer` | the read the estate grants the fleet account, so the check logs in as `developer` and never the fleet account | the estate's own Role: `get` on **one** named Secret, no `list` | `oc adm policy remove-role-from-user … developer`; `oc get rolebinding` → none |
| Secret `group-sync-dashboard/gsd-fleet-account` (`password`) | the fleet password the pod reads through the chart's one-Secret grant | one Secret, one key | `oc delete secret` → NotFound |
| Role + RoleBinding `group-sync-dashboard/gsd-s4b-tab-view` → User `developer` | the tab's view review is `get` on Secrets in the release namespace; `developer` needed it for the screenshots only | **`get` on every Secret in the release namespace — broader than it should have been.** The tab's review asks about `secrets` generally, but a test grant must be scoped exactly as tightly as a shipped one: `resourceNames` naming the Secrets the check reads, or a screenshot taken as an identity that already holds the tier. It existed about fourteen minutes; recorded here as the lesson, not excused by the duration | `oc delete rolebinding`, `oc delete role` → NotFound |
| Secret `gsd-cluster-rnd-lookup` (written by the lookup) and `gsd-cluster-rnd-lookup2` (the probe, then rewritten in place) | the two paths under test | labelled cluster Secrets in the release namespace | `oc delete secret` → NotFound; the clusters retired, rows kept |
| PVCs `group-sync-dashboard-data`, `group-sync-dashboard-report-artifacts`: `managedFields` cleared, then labelled `app.kubernetes.io/version=0.31.0`, `helm.sh/chart=group-sync-dashboard-0.50.0` | the Argo → Helm handover: `helm install` server-side-applied the kept PVCs and hit field-manager conflicts with `argocd-controller`, then with `before-first-apply`, on those two labels | metadata only; the volumes, their binding and their data untouched (`Bound`, the same `volumeName` before and after) | not reverted — they are the labels the release now owns; managers `helm,before-first-apply` |
| The Helm release itself: the Argo Application deleted, `helm install` from this worktree (rev 1 failed on the PVC conflict, rev 2 failed on the same, rev 3 deployed with `crc-lookup.yaml`, rev 4 deployed with `environments/crc.yaml`) | the plain-Helm loop the spec prescribes for this lab | the lab's dashboard release, as every `release-crc.sh` run does | left on Helm at rev 4, head `a7fafaa`, plain values, the fleet-account Role pruned (0 objects); the Argo handback is `release-crc.sh --argocd main` after the merge |

The values file used (`environments/crc.yaml` plus the stanza and the `passwordSecret` block) was
not committed and was moved out of the tree before the final redeploy.

## The values path — a stanza in, a Secret out, the cluster polling

The values file (not committed — `environments/crc.yaml` plus the stanza) added `{name: rnd-lookup, apiUrl: https://api.crc.testing:6443,
saTokenLookup: true, ldapConnectionBootstrap: developer, caBundleFile: <the pod's SA ca.crt>}`.

- `03-pod-log.txt` — `fleet-login … tls=serviceAccount`, `fleet-logout … outcome=revoked`, then
  `fleet-lookup cluster=rnd-lookup … secret=gsd-cluster-rnd-lookup written=created
  source=group-sync-operator/group-sync-dashboard-cluster-poller last_used=2026-09-22 attempt=1/5`,
  and in the same second `discovery cycle=4 … added=rnd-lookup` — the write woke discovery.
- `04-secrets.txt` — the written Secret against the hand-made `gsd-cluster-shared-rnd`: the same six
  `data` keys, the same two `config` keys, `caData` of the same 9612 bytes (the declared bundle);
  labels `secret-type: cluster` only; annotations `managed-by: sa-token-lookup`,
  `token-source: remote-lookup`, `source-namespace`, `source-service-account`,
  `lookup-account: developer`. The hand-made one carries the pre-#282 word `lookup`.
- `05-api-clusterconfigs.txt` — `/api/clusterconfigs` through the route as a bearer-token reader:
  `rnd-lookup` `source: secret:gsd-cluster-rnd-lookup`, `credential: bearer`, `tls.ca: caData`,
  `status: ok`, `last_poll` set, no finding for it.
- `06-token-count-after.txt` — `developer`'s `openshift-challenging-client` tokens on the target:
  0 before, 0 after two successful logins. The session revokes its own token.
- `01-card-rnd-lookup.png` — the Cluster Configurations tab's card: `bearerToken`, `verified ca:
  caData`, `ok reachable`.

One timing fact worth knowing: the pod became leader 20 s after start, and the first lookup ran at
the next cadence tick (300 s) — the wake-up at start fires the discovery thread, but the lookup is
leader-only and the pod was not yet leader on that tick. Five minutes, once, at boot.

## The Secret-declared path — and the two-host contract failing legibly first

`probe-secret.yaml` declared `gsd-cluster-rnd-lookup2` with `config.saTokenLookup: true`,
`ldapConnectionBootstrap: developer` and `tlsClientConfig: {insecure: false}` — the pod's trusted
bundle, which on this lab **does not verify the API host**.

- `07a-secret-declared-trust-failure.txt` and `03-findings-login-failed-names-the-host.png` — the
  login failed at `phase=tls host=api.crc.testing:6443`, retried 1/2/4/8 s to `gave_up=true`, and the
  lookup recorded `fleet-lookup-failed phase=credential outcome=login-failed … attempt=1/5
  retry_in=300`; the tab's finding reads *phase=tls against api.crc.testing:6443 … the stanza's CA
  must verify BOTH the API host and the OAuth route*. The Secret was left untouched
  (`02-card-rnd-lookup2-pending.png`: `remote-lookup`, never polled). This is the refusal the spec
  exists to make legible, on the real cluster, and it names the host.
- `07b-secret-declared-updated.txt` and `04-card-rnd-lookup2-updated-in-place.png` — the probe
  re-applied with the CA it should have declared: the shape change re-armed the schedule
  (`discovery cycle=6 … changed=rnd-lookup2`), the next tick logged in, and `fleet-lookup …
  written=updated` rewrote the Secret in place: `config` is now `{bearerToken, tlsClientConfig}` with
  the declared `caData` kept (9612 bytes), the label `environment=rnd` kept, the four annotations
  set; `cluster-resolved … credential=bearer` in the same second; `/api/clusterconfigs` shows
  `status: ok` and no finding (`05-findings-after.png`).

## How it was captured

`capture.sh` (the text evidence), `shot.py` (the tab, through the proxy, as a viewer holding `get`
on Secrets in the release namespace — the tab's own view review), `probe-secret.yaml` (the declaring
Secret as first applied). The release commands are in the spec's §5.
