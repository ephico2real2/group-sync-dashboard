# #244 on the lab: CA visibility — 2026-09-29

**Outcome.** The lab served application 1.20.0 at `d874fbc619` before, during and after the walk
(`evidence/before-version.txt`, `evidence/after-version.txt`, `evidence/end-version.txt`), image
`quay.io/ephico2real/group-sync-dashboard:1.20.0`, Deployment chart label `group-sync-dashboard-0.59.22`
(`evidence/lab-settings.txt`). The walker was `developer`, CRC's
htpasswd account, at 1280 px, holding the walk's temporary `update clusterrolebindings` grant
(`evidence/walk-output.txt`: `cluster_admin: true`). All four checks of #244's Definition of Done passed on the lab, and
so did the brief's rows A–F: `walk.py` ended with `failures: []` and exit 0 (`evidence/walk-output.txt`,
`evidence/run-exit.txt`). The log's action text and the API's `action` are the same 130 bytes; `cmp` found no difference
(`evidence/C-cmp.txt`).

The run recorded here is the second. The first run's `walk.py` stopped at A's card check on a defect in the walk
script, not in the product. It read the card's row label with `innerText`, and `.cc-kv .k` is
`text-transform: uppercase` in `local-development/gsd/static/app.css` line 1588, so the label read `TLS`, not `tls`
(`evidence/run1/walk-output.txt`). Its Secrets and grant were deleted by the label and its evidence is kept under
`evidence/run1/` (see "Run 1" below). The script now reads `textContent`.

The lab's settings (`evidence/lab-settings.txt`): `enterpriseCaSha256: ""`, `enterpriseCaSubject: ""`,
`caExpiryWarningDays: 30`, `pollIntervalSeconds: 60`, `discoveryIntervalSeconds: 300`,
`clusterSecretsWritesEnabled: true`, and `GSD_TRUSTED_CA_FILE=/etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt`.

## How each step was read

- **Driven**: the Cluster Configurations tab (`/#page=clusters`), each card's tls and connection rows, the warnings
  banner, and the Add-cluster form. E's Test connection was pressed twice. Each answer's HTTP status and JSON were read
  off the wire by Playwright's response listener.
- **The page's own fetch with the session**: `GET /api/clusterconfigs` for the entries and warnings
  (`evidence/walk-clusterconfigs-entries.json`). This is the same endpoint the tab renders from.
- **oc, read-only**: the Secrets, the pod log, the PVCs, the Lease and `can-i`. The only writes were the two throwaway
  Secrets and the grant, all under the label `walk.gsd.lab/run=ca-244-2026-09-29`.

## Definition of Done

| Row | Verdict | Evidence |
|---|---|---|
| **A.** `mock-privateca`'s card lists its CA's subject and expiry | **PASS** | The API's `trust`: `{"store": "secret:gsd-cluster-mock-privateca/tlsClientConfig.caData", "sourceKind": "secret", "count": 1, "enterpriseRoot": null, "certificates": [{"subject": "CN=mock-privateca-root", "issuer": "CN=mock-privateca-root", "notBefore": "2026-09-20T16:54:01Z", "notAfter": "2031-09-19T16:54:01Z", "sha256": "cdf9fb279a8795542554eb3fa0b26faa454c95430b67c1dff527adeda977fc66", "enterpriseRoot": null, "validity": "valid"}]}` (`evidence/A-mock-privateca-trust.json`). The card's tls row reads `verified ca: caData`, then `store secret:gsd-cluster-mock-privateca/tlsClientConfig.caData · 1 certificate`, then `CN=mock-privateca-root · issuer CN=mock-privateca-root · 2031-09-19T16:54:01Z` (`evidence/A-mock-privateca-card.json`). `openssl` on the Secret's decoded caData (1 PEM block, `CA:TRUE`) gives `subject=CN=mock-privateca-root`, `issuer=CN=mock-privateca-root`, `notBefore=Sep 20 16:54:01 2026 GMT`, `notAfter=Sep 19 16:54:01 2031 GMT` and `sha256 Fingerprint=CD:F9:FB:27:…:77:FC:66`. These are the API's values, and the fingerprint is the API's `sha256` in upper case with colons (`evidence/A-openssl.txt`, read at 04:56:28Z, before run 1; the Secret's resourceVersion 995049 is the same in `evidence/before-secrets.txt` and `evidence/end-secrets.txt`, so run 2 read the same caData). The temp file was deleted. The card prints no validity word for this certificate; see "Where the page and the brief or spec differ", item 1. Screenshot `01-1280-A-mock-privateca-card.png` |
| **B.** The other modes, as they are | **PASS** | `mock-trusted` (no tlsClientConfig): `tls.ca` `trusted-bundle`, trust `{"store": "/etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt", "sourceKind": "configmap", "count": 152, "enterpriseRoot": null, "certificates": []}`. The card reads `verified ca: trusted-bundle` and `store /etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt · 152 certificates`, with no enterprise chip. `mock-selfsigned` (`insecure: true`): trust `{"store": "insecure", "sourceKind": "none", "count": 0, "enterpriseRoot": null, "certificates": []}`; the card's tls row reads `insecure` and nothing else. `shared-rnd`: `tls` `{"insecure": false, "ca": "trusted-bundle"}`, with the same trust object and card text as `mock-trusted` (152 certificates, no chip) (`evidence/B-other-modes.json`). The warning codes served were `ca-expiring` and `shared-api-url`, with **0 `ca-not-enterprise`** (`evidence/B-other-modes.json`, `warning_codes`). The pin is empty (`evidence/lab-settings.txt`). The code decides it in two places. `local-development/gsd/clusterconfig/ca.py` lines 301–302 are `pinned = bool(settings.enterprise_ca_sha256 or settings.enterprise_ca_subject)` and `enterprise = any(c["enterpriseRoot"] for c in shown) if pinned else None`. `local-development/gsd/clusterconfig/warnings.py` line 38 is `if trust["enterpriseRoot"] is False:`. With no pin, `enterpriseRoot` is `None`, which is not `False`, so no `ca-not-enterprise` is raised. Screenshot `02-1280-B-mock-trusted-card.png` |
| **C.** A cluster made to fail verification shows the fix sentence; the action text is identical in the log and the API | **PASS** | Throwaway `gsd-cluster-w244-fail`: mock-privateca's server `https://mock-privateca:6443` and the caData `CN=walk-244 wrong CA`, 365 days, sha256 `7C:30:82:F1:…:45:4C:1D` (`evidence/generated-cas.txt`, `evidence/during-walksecrets.txt`). The first poll at 05:08:53Z logged `cluster-unreachable phase=tls outcome=cert-verify-failed cluster=w244-fail … store=secret:gsd-cluster-w244-fail/tlsClientConfig.caData action="this cluster pins its own CA: replace tlsClientConfig.caData in Secret gsd-cluster-w244-fail with the CA that signs its API server" detail="ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1082)"` (`evidence/C-log-line.txt`). The API entry keeps that raw `error` and adds `action` and `store` (`evidence/C-w244-fail-entry.json`). The card shows the raw error in red, the action under it, then `store secret:gsd-cluster-w244-fail/tlsClientConfig.caData` (`evidence/C-w244-fail-card.json`). **Byte for byte**: `cmp evidence/C-action-api.txt evidence/C-action-log.txt` printed nothing, "identical: 130 bytes each". The store strings are also identical, 51 bytes each (`evidence/C-cmp.txt`). Screenshot `03-1280-C-w244-fail-card.png` |
| **D.** A CA inside 30 days raises `ca-expiring` | **PASS** | Throwaway `gsd-cluster-w244-exp`: the same server and the caData `CN=walk-244 expiring CA`, `notAfter=Oct 10 05:04:45 2026 GMT`, 10 days (`evidence/generated-cas.txt`). The API's warning: `{"code": "ca-expiring", "clusters": ["w244-exp"], "detail": "w244-exp's CA CN=walk-244 expiring CA is expiring (2026-10-10T05:04:45Z). The cluster is still polled."}`. The banner shows it under its own title, `CA expiring.` (`evidence/D-w244-exp.json`, `api_ca_expiring` and `banner`). The card prints `… · 2026-10-10T05:04:45Z · expiring` (`evidence/D-w244-exp.json`, `card.tls_row`). The pod log announced it at 05:08:53Z as `ca-expiring clusters=w244-exp state=appeared … cycle=6` (`evidence/D-log-announcement.txt`), and cleared it at 05:13:53Z as `state=cleared … cycle=7`, after the delete (`evidence/end-podlog.txt`). The entry also failed verification, since this CA did not sign the server, so both appear on its card: the `expiring` word in the tls row, and the raw error with the action and the store in the connection row (screenshot `05-1280-D-w244-exp-card.png`). The lab shows only the fired case. The boundary (fires at 30 days, not at 31; 30 days + 1 s is `valid`) is proven by the unit tests `test_ca_visibility.py::test_expiring_at_the_threshold_and_not_the_day_before` and `::test_warning_does_not_start_a_fractional_day_early`. Both passed at `d874fbc6` (`evidence/unit-threshold-tests.txt`). Screenshot `04-1280-D-warnings-banner.png` |
| **E.** The Test response carries the certificate summary | **PASS** | The Add-cluster form was driven: name `w244-test`, the server above, a random bogus bearer token (not recorded), CA `paste PEM` holding C's wrong CA, then Test connection pressed. **E1** `POST /api/clusterconfigs/test` answered `200` `{"reachable":false,"server_version":null,"identity":null,"error":"unreachable: ConnectError: [SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: unable to get local issuer certificate (_ssl.c:1082)","certificates":[{"subject":"CN=walk-244 wrong CA","issuer":"CN=walk-244 wrong CA","notBefore":"2026-09-30T05:04:45Z","notAfter":"2027-09-30T05:04:45Z","sha256":"7c3082f15c68864f06a173a2f78cc36b8edc25e7aebb45aac7f0e2bb05454c1d"}]}`. The Test panel painted `CN=walk-244 wrong CA · issuer CN=walk-244 wrong CA · 2027-09-30T05:04:45Z` (`evidence/E-test-answers.json`). **E2**, PEM field `not a certificate`: `422` `{"detail":"ca-data-invalid: tlsClientConfig.caData does not decode to a PEM bundle that loads: SSLError"}`. The form printed that sentence and **no summary**. This is what the code says: `local-development/gsd/api.py` line 1219 (`if exc.certificates:`) answers the `{code, message, certificates}` object only when a block decoded, and otherwise keeps the string (SPEC D5 §3.6). **Nothing saved**: the cluster Secrets were the same eight names before and after E, with no `gsd-cluster-w244-test` (`evidence/E-test-answers.json`). The pod logged one `connection-tested cluster=w244-test … by=developer outcome=unreachable` (`evidence/end-podlog.txt`). Screenshots `06-1280-E1-test-result.png`, `07-1280-E2-refusal.png` |
| **F.** The pod log for the walk's window | **PASS** | `oc logs --since-time=2026-09-30T05:04:43Z`, 413 lines, captured at 05:14:00Z (the last line is 05:13:54Z): 0 `fleet-login`, 0 `fleet-login-refused`, 0 `fleet-lookup`, 0 `fleet-ping`, 0 Traceback, 0 `ERROR`, 0 lines naming the fleet account. The three bearer tokens (two Secrets, E's Test) were found in 0 lines each (`evidence/end-podlog.txt`). Every poll and the Test failed in the TLS handshake (`CERTIFICATE_VERIFY_FAILED`), which comes before any HTTP request, so no token was sent. |
| **End state** | **PASS** | The grant and both Secrets were deleted explicitly at 05:09:12Z (`evidence/delete.txt`). The exit trap at 05:14:00Z found nothing left (`evidence/trap-delete.txt`). `oc get secret,clusterrole,clusterrolebinding -A -l walk.gsd.lab/run=ca-244-2026-09-29` answered `No resources found` at 05:15:00Z (`evidence/final-label-check.txt`). Discovery cycle 7 logged `removed=w244-exp,w244-fail` at 05:13:53Z (`evidence/wait-discovery-removed.txt`). The grant stood for 267 s, from `oc create` at 05:04:45Z (`evidence/grant-create.txt`) to the delete at 05:09:12Z (`evidence/delete.txt`); `walk.py` used it for 9 s of that (05:09:03Z–05:09:12Z). `can-i update clusterrolebindings --as=developer` answered `no` at 05:04:45Z, `yes` at 05:08:58Z and `no` at 05:09:13Z and 05:13:59Z (`evidence/before-cani.txt`, `evidence/during-cani.txt`, `evidence/after-cani.txt`, `evidence/end-cani.txt`). The PVC UIDs were the same before, after and at the end: data `f065b7a4-535c-4ef1-868c-58f5afee4953`, report-artifacts `08c7d45c-a3eb-47be-8506-f24ea7a3e0e3` (`evidence/before-pvcs.txt`, `evidence/end-pvcs.txt`). `shared-qa` stayed at resourceVersion 2981054, and so did the rest of the cluster Secrets (`evidence/before-secrets.txt`, `evidence/end-secrets.txt`). The fleet Lease stayed at resourceVersion 7043788 with holder `""` (`evidence/before-lease.txt`, `evidence/end-lease.txt`). |

## Timeline (run 2, UTC)

| Instant | What | Evidence |
|---|---|---|
| 05:04:43Z | window start; before-captures | `evidence/start-instant.txt` |
| 05:04:45Z | CAs generated; `gsd-cluster-w244-fail`, `gsd-cluster-w244-exp` and the grant created | `evidence/secret-create.txt`, `evidence/grant-create.txt` |
| 05:08:53Z | discovery cycle 6 `added=w244-exp,w244-fail`; `shared-api-url … state=appeared`; `ca-expiring … state=appeared`; the first polls of both logged `cert-verify-failed` | `evidence/wait-discovery-added.txt`, `evidence/wait-first-polls.txt`, `evidence/end-podlog.txt` |
| 05:09:03Z–05:09:12Z | `walk.py`: A–E | `evidence/walk-output.txt` |
| 05:09:12Z | explicit delete (Secrets, grant) | `evidence/delete.txt` |
| 05:13:53Z | discovery cycle 7 `removed=w244-exp,w244-fail`; `shared-api-url` and `ca-expiring … state=cleared` | `evidence/end-podlog.txt` |
| 05:14:00Z | exit trap: nothing left to delete | `evidence/trap-delete.txt` |

## Where the page and the brief or spec differ

1. **The card prints the validity word only when it is not `valid`.** `local-development/gsd/static/index.html` line
   6218 reads `const extra = cert.validity && cert.validity !== "valid" ? … : "";`. So `mock-privateca`'s line ends at
   its `notAfter` (`evidence/A-mock-privateca-card.json`), while `w244-exp`'s ends `· expiring`
   (`evidence/D-w244-exp.json`). The brief expected a word on every certificate. SPEC D5 §5 asks only for "each listed
   certificate", and the API carries `validity: "valid"` (`evidence/A-mock-privateca-trust.json`).
2. **The Test answer's certificates carry no `validity` and no `enterpriseRoot`.** E1's dicts hold subject, issuer,
   notBefore, notAfter and sha256 only (`evidence/E-test-answers.json`). `local-development/gsd/clusterconfig/writer.py`
   line 533 is `out["certificates"] = summarise_pem(parsed.ca_data or "")`, the summary without `annotate`. SPEC D5
   §3.6 says the Test answer gains `certificates` as "the same dicts, without requiring a pin". The walk records this
   difference and does not rule on it. #244's check, "the Test response carries the certificate summary", is met.
3. **A card that fails verification still says `verified`.** `w244-fail`'s tls row reads `verified ca: caData` above
   a `CERTIFICATE_VERIFY_FAILED` connection row (`evidence/C-w244-fail-card.json`, screenshot
   `03-1280-C-w244-fail-card.png`). `index.html` line 6210 prints `verified` whenever the mode is not insecure, so the
   badge names the mode (verification on), not the outcome. This wording predates #244.
4. **C and D also raise `shared-api-url`.** Both throwaways reuse mock-privateca's server, so the banner carried
   `mock-privateca, w244-exp, w244-fail declare the same API URL: https://mock-privateca:6443` from 05:08:53Z to
   05:13:53Z (`evidence/D-w244-exp.json`, `evidence/end-podlog.txt`). This is #314's warning working as designed.
5. **The two entries poll on until the next discovery.** After the 05:09:12Z delete, `w244-fail` and `w244-exp` kept
   polling until cycle 7 at 05:13:53Z: the window holds 12 `cert-verify-failed` lines (`evidence/end-podlog.txt`).
   They now remain as retired rows with their history (#96). The tab's header counted `37 clusters` (screenshot
   `04-1280-D-warnings-banner.png`, 05:09:09Z) while both were still live: the API served 37 rows at 05:09:07Z, 29
   of them retired rows from earlier walks (`tls: null`) and 8 live, the two throwaways among the live ones
   (`evidence/walk-clusterconfigs-entries.json`). The header counts every row, retired included, so the count is
   the same after cycle 7.

## Run 1

At 04:56:37Z, `gsd-cluster-w244-fail`, `gsd-cluster-w244-exp` and the grant were created with other throwaway CAs
(`evidence/run1/secret-create.txt`, `evidence/run1/generated-cas.txt`). Cycle 4 added both entries at 04:58:53Z
(`evidence/run1/wait-discovery-added.txt`). `walk.py` passed the tier check, the tab and A's API check. It stopped at
04:59:07Z on A's card check, which read `null` for every row (`evidence/run1/walk-output.txt`,
`evidence/run1/A-mock-privateca-card.json`), and took no screenshot. The cause was the `innerText` defect described
above. `run.sh` then deleted both Secrets and the grant at 04:59:07Z (`evidence/run1/delete.txt`). Cycle 5 removed
both entries at 05:03:53Z (`evidence/run1/wait-discovery-removed.txt`). `can-i` answered `no`, `yes`, `no`
(`evidence/run1/before-cani.txt`, `evidence/run1/during-cani.txt`, `evidence/run1/end-cani.txt`). The pod log in that
window held 0 `fleet-login`, 0 Traceback, 0 `ERROR`, and each of the two tokens in 0 lines
(`evidence/run1/end-podlog.txt`). `evidence/run1/C-cmp.txt` holds `cmp` errors, because C never ran.

## Redaction in this folder

- The bearer tokens (two per run in the Secrets, one for E's Test) were random `sha256~` values. They were never
  printed and were kept only in a mode-0600 file outside the repository, for the pod-log search, now deleted. The pod
  log holds each of run 2's three in 0 lines (`evidence/end-podlog.txt`) and run 1's two in 0 lines
  (`evidence/run1/end-podlog.txt`). Everything `walk.py`, `capture.sh` and `run.sh`'s waits write passes a filter that
  rewrites any `sha256~` value as `sha256~<redacted>`; the four files `run.sh` writes straight from `oc create` and
  `oc delete` (`secret-create.txt`, `grant-create.txt`, `delete.txt`, `trap-delete.txt`) carry resource names only.
  A search of the whole folder, `run1/` and the screenshots included, for `sha256~` followed by a letter or digit
  finds 0 files (`evidence/end-redaction.txt`; from this walk on `run.sh` writes it, see `capture.sh redaction`).
  No screenshot includes the form's token field: `06` is the Test panel and `07` the form message; the mask on
  `#cc-token` is configured for every capture all the same.
- The fleet account's name was replaced with `<fleet account>` in every capture, and screenshot `04` masks the fleet
  row. A case-insensitive search of this folder for the name, screenshots included, finds 0 files
  (`evidence/end-redaction.txt`).
- CA subjects, issuers, dates and fingerprints are public PKI and are written as they are.

## How to run it again

```sh
export KUBECONFIG=<the lab kubeconfig> GSD_WALK_TMP=<an empty directory outside the repo>
reports/2026-09-29_ca-244-walk/scripts/run.sh   # before, trap, CAs, Secrets, grant, waits, walk.py, cmp, delete, after, end
reports/2026-09-29_ca-244-walk/scripts/capture.sh openssl A    # A's cross-check (read-only)
```

`scripts/run.sh` fills `developer`'s password from `crc console --credentials` into `walk.py`'s environment only.
The run takes about ten minutes, most of it the two 300 s discovery waits.
