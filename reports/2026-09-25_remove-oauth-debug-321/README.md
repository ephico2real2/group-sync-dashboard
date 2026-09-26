# #321 on the lab — the OAuth Debug path removed, a real login captured from the audit log, 2026-09-25

This folder is the lab proof for issue #321. The issue removes the pod-log login-capture source and the
`authLogLevel` Jobs that set the OAuth server to Debug.
- **Where:** the CRC lab (OpenShift 4.22.7), at commit `1178e03eb4`, the reviewed head of PR #373. Image
  `0.36.0-1178e03eb4`, chart 0.58.0.
- **How deployed:** `local-development/release-crc.sh --argocd`. Argo CD Synced/Healthy, and `1178e03eb4` verified
  in-pod (`walk/release-tail.log`).
- **PVCs:** the kept PVCs have the same UIDs before and after (`walk/pvc-before.txt`, `walk/pvc-after.txt`).

#373 merged as `667b3c4`. After `1178e03` it adds review round 2 (`b0c7fd3`): a restored test, reworded comments, and
a dead branch removed from `metrics.py`. It also merges main's #322 evidence folder. None of that changes what this
walk checked.

The merge was then deployed the same way:
- `walk/release-tail-merge.log` ends `running : 667b3c4a62 — verified in-pod`.
- `walk/pvc-after-merge.txt` has the same UIDs as before.
- `walk/pods-after-merge.txt`: both pods ready, 0 restarts, image `0.36.0-667b3c4a62`, 0 ERROR or Traceback lines. The
  audit reader goes on reading from its saved offset (`audit.log read 1084 byte(s) from offset 23856426`).

## 1. Nothing of the Debug path is left on the cluster

`walk/state-after-deploy.txt`, read after the deploy:

| Check | Result |
|---|---|
| `authLogLevel` Jobs, Roles or RoleBindings in any namespace | `(none)` |
| `authLogLevel` ClusterRoles or ClusterRoleBindings | `(none)` |
| a dashboard Role or RoleBinding in `openshift-authentication` (the old pod-log grant) | `(none)` |
| `authentications.operator.openshift.io/cluster` `spec.logLevel` | `Normal` |
| the ConfigMap's login-capture keys | `loginCaptureSource: "audit-log"`, and no `loginCaptureNamespace` key |

## 2. A real `oc login` is captured from the audit log

1. **The login:** `oc login -u developer https://api.crc.testing:6443`, into a throwaway kubeconfig, with the password
   from the environment. `walk/oc-login.txt` records `login ok at 2026-09-26T04:25:57Z`, and `oc whoami` answers
   `developer`.
2. **The pod log** (`walk/capture.txt`), 23 seconds later:
   `00:26:20 … gsd.auditlog dashboard: recorded 1 login attempt(s) from the audit log on crc (audit.log)`.
   It logs the same line for `shared-qa` and `shared-rnd`. They are the same CRC cluster under three entries, which
   is the lab's deliberate duplication.
3. **The stored row** (`walk/stored-rows.txt`, a read-only query of the pod's database):

   | cluster | user | outcome | at | source | kind | status | client |
   |---|---|---|---|---|---|---|---|
   | `dashboard` | `developer` | `success` | `2026-09-26T04:25:57.319611Z` | `audit-log` | `cli` | `302` | `openshift-challenging-client` |

   The same row is stored for `shared-qa` and `shared-rnd`.

`walk/capture.txt` also holds a call to `/api/clusters/dashboard/logins` through the pod's loopback. It was refused,
*"there is no authenticated identity to scope it to"*: the route reads the reader's identity from the oauth-proxy,
which a loopback call does not pass through. That is why the row was read from the database instead.

## 3. What this lab could not show

The spec's decision 3 is that **stored pod-log history stays readable**. This lab's database holds only `audit-log`
rows (`walk/stored-rows.txt`: `('audit-log', 3797)`), so there is no pod-log history here to read. The guarantee is
pinned by the test `test_audit_default_reads_stored_pod_history_over_api_and_metrics_after_reopen` in
`local-development/tests/test_remove_oauth_debug.py`, which OB1-lite ran on the rebased head.
