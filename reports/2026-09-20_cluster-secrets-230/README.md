# Clusters as labelled Secrets on CRC — S1's validation (#230)

Two scripts, both run against the deployed head `5513242` (`feat/230-cluster-secrets`; the code of
`d84ab3f` + the TLS-mode ruling `d001982`; through the Argo Application, `running : 5513242772 —
verified in-pod`, both Deployments 1/1, the report service `{"status":"ready","schema":19}`) through
`oc` and the dashboard pod's loopback as `kubeadmin`. No page: S1 has no page; the tab is S2. Every
line below is a script's own output, cut only for width.

## 1. The lifecycle — `validate.sh` (the lab's mock cluster as a labelled Secret)

Before: the mock is a **values** entry the Argo-managed Deployment cannot read (the #119 gap, measured):

```
{"id":"mock","source":"values","credential":"","status":"auth_failed",
 "error":"cluster 'mock': cannot read tokenFile '/etc/gsd/mock/token': [Errno 2] No such file or directory"}
```

The same cluster as `gsd-cluster-mock` (its token and CA from `mock-cluster-creds`) beside a deliberately
broken Secret (`config: '{not json'`). The next discovery cycle (the binding cadence, 300 s):

```
2026-09-20 13:18:42,166 WARNING gsd.clusterconfig.reader cluster Secret gsd-cluster-broken refused: config-not-json (Expecting property name enclosed in double quotes: line 1 column 2)
2026-09-20 13:18:42,169 INFO    gsd.poller cluster mock: polling started (secret:gsd-cluster-mock)
```

`GET /api/clusterconfigs` at `last_discovery 2026-09-20T17:18:42Z` — the Secret wins over the values entry
(`shadows-values-entry` is the informational finding for it), the broken one is a finding, not a crash:

```
{"id":"mock","source":"secret:gsd-cluster-mock","credential":"bearer","labels":{"environment":"lab"},
 "visibility":"inherit","identity":"same-as-host","status":"ok"}
"findings":[{"secret":"gsd-cluster-broken","code":"config-not-json","detail":"Expecting property name enclosed in double quotes: line 1 column 2"}]
```

Polled like a values cluster (`GET /api/clusters`): `{"id":"mock","status":"ok","last_poll":"2026-09-20T17:18:42Z","group_count":7,"groupsync_count":1}`
— the fixture's seven groups and one GroupSync.

The token in nothing (a grep for the Secret's bearer token): `/api/clusterconfigs: 0 · /api/clusters: 0 ·
/metrics: 0 · /readyz: 0 · the pod's log: 0`.

Both Secrets deleted → the finding gone, the cluster retired with its rows:

```
2026-09-20 13:23:42,206 INFO    gsd.poller mock: its Secret is gone; the poll thread stops (history kept)
{"id":"mock","source":"secret:gsd-cluster-mock","enabled":false,"retired":true}
```

## 2. The three TLS trust modes — `local-development/mock-app/deploy/tls-modes/deploy-tls-modes.sh`

The operator's ruling (2026-09-20): each mode is proven against a copy of the mock API whose serving
certificate is signed differently (the rig's README says what each copy is). The lab's trusted bundle
carries exactly one non-system root, `CN=LDAP Enterprise Root CA` (the ClusterIssuer `ldap-enterprise-ca`),
and not `CN=mock-privateca-root`:


### A. mock-trusted — DEFAULT (no caData): the enterprise-signed leaf verifies against the trusted bundle
{"id":"mock-trusted","source":"secret:gsd-cluster-mock-trusted","credential":"bearer","tls":{"insecure":false,"ca":"trusted-bundle"},"status":"ok","last_poll":"2026-09-20T16:58:42Z","error":null}


### B1. mock-privateca — DEFAULT (no caData): the x509 error, as a poll outcome
{"id":"mock-privateca","source":"secret:gsd-cluster-mock-privateca","credential":"bearer","tls":{"insecure":false,"ca":"trusted-bundle"},"status":"unreachable","last_poll":"2026-09-20T16:58:42Z","error":"ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1082)
2026-09-20 12:58:42,137-0400 WARNING gsd.poller binding refresh for mock-privateca failed: ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1082) (unreachable) — group data is unaffected


### B2. mock-privateca — OVERRIDE: the same Secret with tlsClientConfig.caData = the private CA's PEM
secret/gsd-cluster-mock-privateca configured
{"id":"mock-privateca","source":"secret:gsd-cluster-mock-privateca","credential":"bearer","tls":{"insecure":false,"ca":"caData"},"status":"ok","last_poll":"2026-09-20T17:04:42Z","error":null}


### C. mock-selfsigned — INSECURE: insecure: true polls the bare self-signed leaf
{"id":"mock-selfsigned","source":"secret:gsd-cluster-mock-selfsigned","credential":"bearer","tls":{"insecure":true,"ca":null},"status":"ok","last_poll":"2026-09-20T17:04:42Z","error":null}


### D. the refusal — caData AND insecure on one Secret: a finding naming both fields, no cluster, the pod alive
{"findings":[{"secret":"gsd-cluster-mock-refusal","code":"insecure-with-ca","detail":"tlsClientConfig.caData and tlsClientConfig.insecure=true are both set: choose one"}],"listed":[]}
group-sync-dashboard-6f6f9cf84-xhpkf   true   0


### E. the three beside crc-local, with the fixture's counts (GET /api/clusters)
{"id":"crc-local","status":"ok","groupsync_count":3,"group_count":62}
{"id":"mock-privateca","status":"ok","groupsync_count":1,"group_count":7}
{"id":"mock-selfsigned","status":"ok","groupsync_count":1,"group_count":7}
{"id":"mock-trusted","status":"ok","groupsync_count":1,"group_count":7}


### F. the token in no response and no log line
/api/clusterconfigs: 0
/api/clusters: 0
/metrics: 0
log: 0


### TLS MODES DONE

The rig stays deployed: S2's walk uses it. The four Secrets from an earlier CRC-API probe of the same
modes (`crc-tls-*`, since deleted) show as retired rows — the "history kept" rule, visible.
