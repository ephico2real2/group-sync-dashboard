# Docs content audit, batch 6 of 6: the two tutorials

Phase 2 of the documents pass, sixth and last batch. `docs/guides/TUTORIAL_ca_trust_hashed_directory.md`
(949 lines) and `docs/guides/TUTORIAL_mermaid_diagrams.md` (410 lines) were read in full, and every checkable
claim was measured against main at bb400c0d (application 5.5.0, chart 0.70.8). A tutorial's commands are
claims, so every command that can run without a cluster write was run. The evidence comes from:

- **Part 2 of the CA tutorial, run as written** in a scratch directory with Homebrew OpenSSL 3.6.4 (and
  macOS's LibreSSL 3.3.6 for comparison), plus local reproductions of the curl, Python and Go claims against
  a local copy of the tutorial's TLS server: macOS curl 8.7.1, Python 3.14 `urllib`, `requests` 2.34.2 and
  `httpx` 0.28.1 from the repository's venv, and a Go 1.27.1 client.
- **The images, read without a container runtime.** No runtime was running, and none was started.
  `oc image extract` copied files out of `registry.access.redhat.com/hi/python:3.14` (built 2026-10-03),
  `hi/python:3.14-builder` and `ubi9/python-312:latest` into the scratch directory.
- **Upstream source and documentation.** OpenSSL `crypto/x509/x509_cmp.c` and `by_dir.c` (master), curl
  `src/tool_operate.c` (master) and `lib/vtls/openssl.c` at several tags, Kubernetes
  `pkg/volume/configmap/configmap.go` (master), Go's `crypto/x509/root.go` and `root_linux.go` (1.27.1),
  and the Mermaid, OpenSSL, OpenShift, cert-manager, Kyverno and Hummingbird pages the tutorials cite.
- **mermaid-cli 11.17.0** (`npx @mermaid-js/mermaid-cli@11`, the CI `diagrams` job's tool, cached in the
  scratch directory). It rendered every block in the repository, and one probe diagram per construct in
  Part 4 of the mermaid tutorial.
- **The chart**, rendered with `helm template` three ways: the defaults, `existingConfigMap` with
  `subjectHash=7886c608`, and with `subjectHash=7886c608.1`.
- **The lab** (CRC, OpenShift 4.22.7), read-only. The checks were the injected ConfigMap's certificate
  count, the tutorial's namespaces and policy, the Kyverno and cert-manager versions, and the PodSecurity
  admission defaults in `openshift-kube-apiserver/config`. No Secret was read.

Line numbers are those of bb400c0d. They are given outside backticks.

Verdicts:

- **CORRECT**: the claim matches the evidence.
- **FIXED**: the claim was wrong or stale, and the page now says what the evidence shows.
- **NOT MEASURED**: a step that needs a cluster write, or a dated measurement that could not be repeated
  here. It was left unchanged.
- **CODE-SUSPECT**: the page describes the intended behaviour and the code does not do it.

## Totals

| document | claims checked | fixed | not measured | code-suspect |
|---|---|---|---|---|
| `docs/guides/TUTORIAL_ca_trust_hashed_directory.md` | 67 | 23 | 6 | 0 |
| `docs/guides/TUTORIAL_mermaid_diagrams.md` | 38 | 10 | 1 | 0 |

One row per claim; a row whose verdict reads "FIXED / NOT MEASURED" counts as fixed.

## `docs/guides/TUTORIAL_ca_trust_hashed_directory.md`

### Preamble

| claim | verdict | evidence |
|---|---|---|
| run on CRC "OpenShift 4.x with cert-manager 1.19" on 2026-09-04 | NOT MEASURED | historical. The lab today runs OpenShift 4.22.7 and cert-manager v1.20.3 (`app.kubernetes.io/version` on the `cert-manager` Deployment) |
| "`openssl` on your machine" is enough for the local parts | FIXED | `/usr/bin/openssl rehash` on macOS fails with "'rehash' is an invalid command" (LibreSSL 3.3.6). Homebrew OpenSSL 3.6.4 runs Part 2 as written. The page now asks for OpenSSL 1.1 or later and says why |
| Kyverno CRD check; "this run used Kyverno 1.16.1" | FIXED | dated and correct. The lab now runs v1.19.1 (`reg.kyverno.io/kyverno/kyverno:v1.19.1`), where `oc get clusterpolicy` warns "kyverno.io/v1 ClusterPolicy is deprecated", and four ClusterPolicies are READY. Added that 1.19 still runs the kind and warns |
| heredoc convention (unquoted `EOF` substitutes, `'EOF'` is literal) | CORRECT | the 3.2 and 3.3 client blocks use `<<EOF` with `$HASH`/`$CM_HASH`; every other block uses `<<'EOF'` |

### Part 1: the theory

| claim | verdict | evidence |
|---|---|---|
| bundle locations in the 1.1 table | CORRECT | in `hi/python:3.14`, `/etc/ssl/certs/ca-bundle.crt` and `/etc/ssl/cert.pem` link to `tls-ca-bundle.pem`. `/etc/pki/tls/cert.pem` is absent there; the column says "usually" |
| the hash is SHA-1 of the canonical subject, first four bytes little-endian, eight hex digits | CORRECT | OpenSSL `x509_cmp.c` `X509_NAME_hash_ex`, lines 338-339: `EVP_Digest(x->canon_enc …)`, then `md[0] \| md[1]<<8 \| md[2]<<16 \| md[3]<<24` |
| the Part 2 CA hashes to `7886c608` on macOS OpenSSL 3.6 | CORRECT | run: OpenSSL 3.6.4 prints `7886c608` for a freshly generated key (the hash depends only on the subject); LibreSSL 3.3.6 prints the same |
| the container's OpenSSL is 3.5 | CORRECT | `hi/python:3.14` ships `libcrypto.so.3.5.9` |
| `-subject_hash_old` prints `bac1f22a` | CORRECT | run: OpenSSL 3.6.4 and LibreSSL 3.3.6 both print `bac1f22a` |
| "old distributions kept both links per certificate" | FIXED | the current hardened image still does: every one of the 121 PEM files in `directory-hash/` has a link under its hash and one under its old hash (`GlobalSign_Root_R46.pem`: `002c0b4f.0` and `1b0f7e5c.0`); 242 links in all. The text now says so |
| the lookup "loads every certificate in that file … checks whether one has the subject it wants. If not, it opens `<hash>.1`" | FIXED | OpenSSL `by_dir.c` lines 291-353: the loop loads `<hash>.0`, `.1` … until `lstat` fails (line 328, "file does not exist"), without checking subjects. Lines 355-373 then retrieve the subject from the store cache. Order of events corrected; the stop rule is unchanged |
| "Four consequences follow, and each one was demonstrated in Part 3" | FIXED | Part 3.2 demonstrates only rows 1 (step 5) and 3 (step 7). Now says so. Rows 2 and 4 were measured here, below |
| row 1: `.1` with no `.0` is never opened | CORRECT | run: `openssl verify -CApath` with only `7886c608.1`: "error server.crt: verification failed" |
| row 2: on a collision yours is `.1` | CORRECT | run: another CA saved as `7886c608.0` and the tutorial CA as `7886c608.1`: "server.crt: OK" |
| row 3: right CA, wrong hash, is never opened | CORRECT | run: the CA saved as `deadbeef.0`: "verification failed" |
| row 4: a bundle named `<hash>.0` "serves exactly one CA" | FIXED | run: two CAs bundled under CA A's hash. `openssl verify` passes A's server and fails B's. Measured in one Python `SSLContext` with that capath: B fails first, A passes, then B **passes**, because A's lookup loaded the whole file into the store. Qualified |
| `openssl rehash`, older name `c_rehash` | CORRECT | the man page's NAME line reads "openssl-rehash, c_rehash" |
| `update-ca-trust extract` through p11-kit builds the bundles and the hashed directory | NOT MEASURED | not run. The extracted image shows the result (below) |
| the 1.4 layout and its counts: `directory-hash/` 438 entries, `tls-ca-bundle.pem` 223752 bytes, `/etc/pki/tls/certs` 292 symlinks | FIXED | `oc image extract` of today's `hi/python:3.14` (sha256:8b4e6bb4…, created 2026-10-03T19:25:19Z). `directory-hash/` has 363 entries: 121 PEM files and 242 hash links. `tls-ca-bundle.pem` is 185311 bytes with 121 certificates. `/etc/pki/tls/certs/` has 242 entries, all symlinks into `directory-hash/`. The file set and the `/etc/ssl` links match. Numbers updated with the build date; the 292 in 1.4 and in 3.1 now read 242 |
| Python's default context reads the directory: `capath=/etc/pki/tls/certs`, `cafile=/etc/pki/tls/cert.pem` compiled in | CORRECT | `libcrypto.so.3.5.9` in the image contains `OPENSSLDIR: "/etc/pki/tls"`, `/etc/pki/tls/certs` and `/etc/pki/tls/cert.pem`. Locally, `urllib` fails with no variable and verifies with `SSL_CERT_DIR` pointing at a rehashed directory |
| curl reads the directory only when told | CORRECT | macOS curl 8.7.1 against the local server: no variable gives exit 60; `SSL_CERT_DIR` gives the body. `curl -v` reports `CApath: none` without one |
| `httpx` / `requests` "with defaults": hashed directory "no"; bundle "their own certifi; requests also reads REQUESTS_CA_BUNDLE" | FIXED | measured with the venv's `requests` 2.34.2 and `httpx` 0.28.1. `requests` ignores `SSL_CERT_FILE` and `SSL_CERT_DIR` but honours `CURL_CA_BUNDLE`: requests' sessions.py lines 857-858 read `REQUESTS_CA_BUNDLE` or `CURL_CA_BUNDLE`. `httpx` honours `SSL_CERT_FILE` and `SSL_CERT_DIR` (httpx's _config.py lines 34-37) and not `CURL_CA_BUNDLE`. Row corrected |
| Go programs: hashed directory "no" | FIXED | Go 1.27.1 `crypto/x509/root.go` `loadOnDiskRoots` (lines 153-204) reads the first bundle in `certFiles`, then every file in `certDirectories`, which on Linux are `/etc/ssl/certs` and `/etc/pki/tls/certs` (`root_linux.go` lines 20-23), or in `SSL_CERT_DIR`. Run: a Go client with `SSL_CERT_DIR` holding the CA as `deadbeef.0` verifies (OpenSSL's `verify` refuses the same directory). Row corrected: it reads the directory, by content, not by hash |
| `SSL_CERT_DIR` set to the default "changes nothing for Python" | FIXED | true of Python's default context; for `httpx` it replaces certifi with the directory (row above). Qualified |
| `SSL_CERT_FILE` "is read by everyone" | FIXED | `requests` ignores it (measured above). Now "nearly everyone (`requests` is the exception)" |
| curl reads `SSL_CERT_DIR`/`SSL_CERT_FILE` only when `CURL_CA_BUNDLE` is unset; measured on 7.76 and 8.22 | CORRECT | curl `src/tool_operate.c` `cacertpaths` (master, lines 2266-2291): the variables are consulted only when no `cacert`/`capath` is configured; `CURL_CA_BUNDLE` wins and the `else` branch reads the other two. Run on curl 8.7.1: both set gives exit 60 and `curl -v` prints `CApath: none`. The images: UBI 9 ships `libcurl/7.76.1`; the hardened builder, from which the shipped curl is copied, ships `curl 8.22.0` |
| a `.curlrc` found through `CURL_HOME` names both stores and `curl -v` shows both | CORRECT | run: `.curlrc` with `cacert` = another CA and `capath` = the rehashed directory. The request verifies, and `curl -v` prints both `CAfile:` and `CApath:` |
| nothing but the curl tool reads `.curlrc` | CORRECT | the config-file parser is the tool's (`src/tool_parsecfg.c` in curl), not libcurl's. Read, not run against another client |
| "Parts 3.5 and 3.6 use it" | FIXED | 3.6 is the clean-up; the `.curlrc` is used by the chart (3.4) and by the Kyverno policy (3.5). Now "3.4 and 3.5" |

### Part 2: hands on, locally

| claim | verdict | evidence |
|---|---|---|
| the two config files and the `openssl req` / `x509 -req` commands; `openssl verify -CAfile ca.crt server.crt` prints `server.crt: OK` | CORRECT | run as written; rc 0 and `server.crt: OK` |
| `-subject` prints `subject=C=NG, O=Example Corp, CN=Example Corp Internal Root CA` | CORRECT | run: identical |
| the `$HASH.0` copy verifies; renamed to `.1` it fails | CORRECT | run: `server.crt: OK`; then "error server.crt: verification failed", preceded by "error 20 at 0 depth lookup: unable to get local issuer certificate" (the page shows the last line) |
| `openssl rehash` scans `.pem`, `.crt`, `.cer`, `.crl` and links `HHHHHHHH.D` / `HHHHHHHH.rD` from `.0` | CORRECT | `openssl-rehash` man page (master): "The links created are of the form HHHHHHHH.D"; the extension list. Run: `ls -l capath` shows `7886c608.0 -> example-corp-ca.pem` and `example-corp-ca.pem` |
| a file without one of those extensions is ignored, so the `$HASH.0` copy would not have been linked | CORRECT | run: `openssl rehash -v` on a directory holding only a regular `7886c608.0` makes no link |
| `openssl rehash -v` prints `link example-corp-ca.pem -> 7886c608.0`; `-old` adds the MD5-era names | CORRECT | run: identical output; man page "-old Use old-style hashing (MD5 …)" |

### Part 3: on OpenShift

| claim | verdict | evidence |
|---|---|---|
| the tiny HTTPS server answers `hello over TLS from <name>` | CORRECT | run locally from the ConfigMap's script. `server_name` is the bound host's FQDN, which in a pod is the pod name, hence `server` and `server-cm` |
| the `securityContext` block is what `restricted` asks for; without it `oc apply` warns | CORRECT | lab PodSecurity defaults (`openshift-kube-apiserver/config`): `warn: restricted`, `audit: restricted`, `enforce: privileged` |
| the labelled ConfigMap is filled with the cluster trust store under the key `ca-bundle.crt`; 149 certificates on CRC | CORRECT | dated. The lab's `group-sync-dashboard-trusted-ca` today carries `ca-bundle.crt` with 152 certificates; the count moves with the cluster. Left as the run's figure |
| Layout A is "what the dashboard chart does", and curl learns of the bundle through `CURL_CA_BUNDLE`, "which no other program reads" | FIXED | the chart mounts the same way, but names the bundle to curl in a `.curlrc` (render: no `CURL_CA_BUNDLE`; `CURL_HOME=/etc/curl`). `requests` reads `CURL_CA_BUNDLE` (above). Both qualified |
| the Layout A, Layout B and 3.2-3.5 outputs (`http 404`, `hello over TLS from server`, `exit 60` …) | NOT MEASURED | they need the tutorial's pods on a cluster, which is a cluster write. The local reproductions above match each mechanism they show |
| "`optional: true` … a required volume would block the first rollout of every install until the operator has filled the ConfigMap" | FIXED | Kubernetes `pkg/volume/configmap/configmap.go`: a missing ConfigMap fails the mount unless optional (lines 191-197). A ConfigMap with no `items` projects whatever keys exist, so an existing, empty one mounts as an empty directory (lines 273-289). Read from source, not run (no cluster write). The sentence now gives that reason. The chart's own comment repeats the old reason (findings) |
| Layout B per the OpenShift 4.21 custom-PKI guide: mount over `/etc/pki/ca-trust/extracted/pem`, key renamed `tls-ca-bundle.pem` | CORRECT | the guide's example: `mountPath: /etc/pki/ca-trust/extracted/pem`, `items: key: ca-bundle.crt, path: tls-ca-bundle.pem` |
| on UBI 9 `/etc/pki/tls/certs` holds two bundle symlinks and nothing else | CORRECT | `oc image extract` of `ubi9/python-312:latest`: `ca-bundle.crt` and `ca-bundle.trust.crt`, both symlinks |
| on the hardened image the mount hides 292 links; Python fails and curl works | FIXED / NOT MEASURED | the count is 242 today (above), fixed. The Python-fails behaviour needs a pod and was not re-run |
| "While the ConfigMap is still empty, `tls-ca-bundle.pem` is an empty file and every client fails" | FIXED | Layout B maps the key through `items` and is not optional. Until the operator fills the ConfigMap the key does not exist, and the kubelet refuses the mount: "configmap references non-existent config key" (`configmap.go` lines 291-300). The pod waits; no client runs. Read from source, not run. Now says so, and that with `optional: true` the pod starts without the file and every bundle reader fails |
| 3.2: one key mounted as a single file with `subPath`; `SSL_CERT_DIR` so curl reads the directory | CORRECT | mechanism reproduced locally (rows above) |
| exit 60 is curl's "peer certificate cannot be authenticated" case | CORRECT | run: `curl: (60) SSL certificate problem: unable to get local issuer certificate` |
| 3.3 cert-manager chain, `ca.crt` in every Secret it writes | NOT MEASURED | cluster write. Consistent with cert-manager's CA issuer page |
| cert-manager 1.18+ warns that `rotationPolicy` defaults to `Always` | CORRECT | cert-manager 1.18 release notes: the default moved to `Always`, feature-gated, GA in 1.19 |
| `items` on the Secret volume exposes `ca.crt` alone | CORRECT | Kubernetes `pkg/volume/secret/secret.go` `MakePayload` (lines 261-285) projects only the listed keys when `items` is set. The `subPath` mount already shows the container one file; `items` keeps `tls.key` out of the volume |
| 3.4 table, injected row: "to curl in `CURL_CA_BUNDLE`" | FIXED | default render: the dashboard container's CA env is `GSD_TRUSTED_CA_FILE` and `CURL_HOME` only; the `.curlrc` holds `cacert = /etc/pki/ca-trust/extracted/pem/injected/ca-bundle.crt`. Now "as the `.curlrc`'s `cacert`" |
| existingConfigMap row: mounted beside the system store and named to the application | CORRECT | render: `/etc/pki/ca-trust/extracted/pem/enterprise`, and `GSD_TRUSTED_CA_FILE` lists `…/injected/ca-bundle.crt:…/enterprise/ca-bundle.crt` |
| subjectHash row: mounted again as `<hash>.0` (or `<hash>.N`), "so curl and every OpenSSL client in the pod trust it" | FIXED | render: `/etc/pki/tls/certs/7886c608.0` (and `7886c608.1` for `subjectHash=7886c608.1`), `subPath: ca-bundle.crt`, on the `dashboard` container only. The `oauth-proxy` container mounts the injected and enterprise directories but not the hashed file. Now "in the dashboard container" |
| the `.curlrc` ConfigMap is `<release>-curlrc` | FIXED | `templates/configmap-curlrc.yaml` names it `{{ include "gsd.fullname" . }}-curlrc`; with release `gsd` it renders `gsd-group-sync-dashboard-curlrc`. Now `<fullname>-curlrc`, the convention the CHANGELOG uses |
| "The first version of the chart used `CURL_CA_BUNDLE` and `SSL_CERT_DIR`" | CORRECT | `git log -S CURL_CA_BUNDLE -- charts/group-sync-dashboard/templates/`: added in 14e255bf, removed in 4bf77ef7 ("curl in the pod is configured by a .curlrc"), both 2026-09-04 |
| `charts/group-sync-dashboard/values.yaml#trustedCA`; `DESIGN_hardened_image.md` section 8 | CORRECT | `trustedCA:` at `values.yaml` line 926; `docs/design/DESIGN_hardened_image.md` section 8 is "TLS trust, for the application and for curl in the pod" |
| 3.5 policy and its outputs; generate on existing namespaces needs a touch; the opt-out | NOT MEASURED | cluster write. The lab has the background controller's ServiceAccount `kyverno/kyverno-background-controller` |
| `oc auth can-i create configmaps --as=system:serviceaccount:kyverno:kyverno-background-controller` | CORRECT | lab: `yes` for `ca-tutorial-app` (see the record's housekeeping note: this asks a SubjectAccessReview as that identity) |
| 3.6: the namespaces and the policy "were left in place on CRC so the pods above can be inspected" | FIXED | lab: `ca-tutorial` and `ca-tutorial-app` exist (created 2026-09-19T15:12Z, after the run) and hold only `kube-root-ca.crt` and `openshift-service-ca.crt`, with no pods. `ca-tutorial-app` lacks the opt-in label, and `clusterpolicies.kyverno.io "enterprise-ca-trust" not found`. Now says what is left |

### Part 4 and Sources

| claim | verdict | evidence |
|---|---|---|
| `curl: (60) … unable to get local issuer certificate` | CORRECT | run (curl 8.7.1) |
| `curl: (77) error adding trust anchors from file` | FIXED | curl `lib/vtls/openssl.c`: the text first appears in curl-8_17_0 (absent in 8_9_1 through 8_16_0). Before that, OpenSSL 3 builds print `error setting certificate file` (curl-7_76_1 line 3033), and UBI 9's `libcurl/7.76.1` contains only that string. The hardened builder's curl 8.22.0 contains the new one. Version qualifier added |
| Python verifies, curl does not; neither verifies; one CA per file; `subPath` does not follow updates | CORRECT | the runs above. Kubernetes ConfigMap docs: "A container using a ConfigMap as a subPath volume mount will not receive ConfigMap updates" |
| hardened image: mounting over `extracted/pem` broke Python, not curl | NOT MEASURED | needs a pod. The layout that explains it was measured (1.4) |
| PodSecurity row: "required for the pod to run under the restricted profile on OpenShift 4.11+" | FIXED | lab defaults: `enforce: privileged`, `warn`/`audit: restricted`. The `ca-tutorial` namespaces carry warn/audit labels only. So the pod is warned about and still runs. Now says it is refused only where a namespace enforces `restricted`. 4.11 itself not measured |
| `SSL_CERT_FILE` row: "a bundle every OpenSSL client reads" | FIXED | `requests` does not (measured). Now "nearly every client" |
| last row: both variables set, curl ignores `SSL_CERT_DIR` | CORRECT | measured (above) |
| the nine Sources links and the inline custom-PKI link | CORRECT | `curl -L` gives HTTP 200 for each |

## `docs/guides/TUTORIAL_mermaid_diagrams.md`

| claim | verdict | evidence |
|---|---|---|
| "the ten diagrams in `reference-architecture.md`" | CORRECT | `grep -c '^```mermaid'`: 10 |
| every diagram in the tutorial was rendered with CI's tool | CORRECT | the tutorial's six blocks render with mermaid-cli 11.17.0 (`ok` for each), as do all 31 blocks in the repository |
| GitHub renders mermaid natively | NOT MEASURED | not rendered on GitHub here; the cited GitHub post returns 200 |
| markdown mode writes SVGs beside the output and rewrites the blocks into image links | CORRECT | run on `docs/guides/reference-architecture.md`: ten `rendered-N.svg` files, zero mermaid fences left, `![diagram](./rendered-1.svg)` |
| the repository commits text only | CORRECT | `git ls-files '*.svg'`: only `local-development/gsd/static/favicon.svg` |
| step 3's symbols: `is_leader` in `gsd/leader.py`, `record_sync_event` and `poll_snapshot` in `gsd/store.py`, called from `poll_once` in `gsd/poller.py`; the comment above the line | CORRECT | `leader.py` line 91; `store.py` lines 1514, 2171; `poller.py` line 330 (`poll_once`), 463 (the call), 488-491 (the comment above `with store.poll_snapshot()`) |
| 3.1's flowchart is section 7.2's | CORRECT | identical to the block under "7.2 Authentication is the sidecar's job" |
| `-->\|":8443"\|`: "quote the label because it contains a colon" | FIXED | probe: `a["x"] -->\|:8443\| b["y"]` renders with the label `:8443`. Now: quoted, which is always safe; a bare colon also renders |
| `<br/>` is "the one piece of HTML the renderer keeps" | FIXED | probe: `a["<b>bold</b> and <i>it</i> and <why> x"]` renders `<b>bold</b> and <i>it</i> and  x`. `<b>`/`<i>` are kept, `<why>` dropped. Now "the one piece of HTML these diagrams use", with that note |
| the shape list | CORRECT | Mermaid flowchart syntax page |
| section 8 "uses one [subgraph] per Kubernetes object … the pod, the namespace and the cluster" | FIXED | the section 8 block has one subgraph, `ns["namespace: group-sync-dashboard"]`. Now says so, and that the sketch draws a pod the same way |
| `direction LR` inside a subgraph | CORRECT | the sketch renders |
| 3.2 "The first lines of the poll-flow diagram" | FIXED | the excerpt drops `T->>K: list groups (paged)` and four calls inside the `rect`. Now "Lines from …, shortened" |
| "stand by — re-check in 5s, not one poll interval" | CORRECT | `gsd/poller.py` line 264 (`STANDBY_RECHECK_SECONDS = 5`), line 1288 |
| the sequence constructs table | CORRECT | Mermaid sequence-diagram page; the excerpt renders |
| 3.3 ER block from section 5, reduced; labels | CORRECT | every line of the excerpt is in section 5's `erDiagram` |
| the cardinality table; `--` identifying, `..` non-identifying; attributes block | CORRECT | Mermaid ER page: the symbol table (lines 175-177 of its source), "identifying … solid … non-identifying … dashed" |
| Part 4 intro: the fast test "checks for them" (all five) | FIXED | `local-development/tests/test_docs_diagrams.py` tests `;` outside quotes, HTML-looking tags, unbalanced quotes, `style` on a subgraph and unclosed fences. It has no test for lowercase `end` or unquoted punctuation. Now "the first three" |
| row 1: a bare `;` in a note is a parse error; harmless inside a quoted flowchart label | CORRECT | probes: `Note over T: stand by; re-check in 5s` gives "Parse error on line 3". `a["stand by; re-check"]` renders the text. Mermaid's sequence page: "semicolons can be used instead of line breaks" |
| row 2: `<why>` vanishes without an error | CORRECT | probe: the label renders as `token  here` |
| row 3: an unclosed quote makes "the rest of the diagram … one label" | FIXED | probe: `ext["anything on the pod network] --> b["next"]` gives "Parse error on line 2 … got 'STR'": the label runs to the next `"` and the parse fails. Now says so |
| row 4: lowercase `end` "inside a flowchart node label … closes a subgraph" | FIXED | probes: `a[end]`, `a[the end]`, `a["the end"]` and `e[end]` inside a subgraph all render; `a["x"] --> end` is a parse error. The Mermaid page warns about "end" in a node. Now names the node form, and says a bracketed label renders on mermaid 11 |
| row 5: a label with `:`, `(`, `)` or `\|` unquoted is read as syntax | FIXED | probes: `a[a: b]` renders; `a[a (c)]` and `a[a \| c]` are parse errors. The colon is dropped from the row, with a note |
| 5.1: the test checks "the constructs from Part 4" | FIXED | as the Part 4 intro row. Now lists what it checks |
| about half a second; at least nine blocks; the command | CORRECT | `PYTHONPATH=. <venv>/python -m pytest tests/test_docs_diagrams.py -q`: "460 passed in 0.35s"; `assert len(BLOCKS) >= 9` (line 71) |
| 5.2: the job extracts every block and renders each with mermaid-cli; the sandbox reason; the zero-render guard; at least nine | CORRECT | `.github/workflows/ci.yml` lines 364-409: the extractor, the Ubuntu 23.10+/AppArmor comment, `rendered -eq 0` → `exit 1`, `assert n >= 9` |
| "two layers of automation" | CORRECT | the job's third step, the mermaid-ascii preview (lines 411-436), is display-only and never fails the job, as the `mermaid-ascii` skill says |
| 5.3: the one-diagram render | CORRECT | run: 12348-byte SVG in 17 s, first run included |
| "the extractor is the same code" | CORRECT | identical to `ci.yml` lines 368-378 except the output directory |
| the puppeteer config is "the same `--no-sandbox` config CI uses" | FIXED | `ci.yml` line 389: `{ "args": ["--no-sandbox", "--disable-setuid-sandbox"] }`; the page had `--no-sandbox` alone. Now identical |
| markdown-mode command | CORRECT | run (row above) |
| 6.1: "After chart 0.10.0" | CORRECT | `docs/CHANGELOG.md`, "Application 0.11.0 — chart 0.10.0": "Chart 0.10.0: curl in the pod trusts what the dashboard trusts" |
| 6.1: `deployment.yaml` mounts three things and sets two variables; `configmap-curlrc.yaml` names two stores; `GSD_TRUSTED_CA_FILE` in `gsd/config.py` | CORRECT | render with `subjectHash`: three ConfigMap volumes (curlrc, injected, enterprise; enterprise mounted twice); env `GSD_TRUSTED_CA_FILE`, `CURL_HOME`; `.curlrc` has `capath` and `cacert`; `config.py` line 109 |
| 6.1 diagram paths (`…/enterprise/ca-bundle.crt`, `/etc/pki/tls/certs/<hash>.0`, `CURL_HOME=/etc/curl`) | CORRECT | render (above) |
| `&lt;hash&gt;` because `<hash>` would be dropped | CORRECT | probe row 2 |
| 6.2: four rules; mutation adds three mounts and `CURL_HOME` | CORRECT | the 3.5 policy in the CA tutorial |
| exercises: `gsd/api.py`, section 4, section 8c | CORRECT | all exist |
| Sources links | CORRECT | HTTP 200 each |

## Findings for the orchestrator (no change made)

1. **The chart's stated reason for `optional: true` on the injected volume is not what the kubelet does.**
   `charts/group-sync-dashboard/templates/deployment.yaml` lines 598-599: "a pod that refused to start until then
   would fail the first rollout of every install". The chart creates the ConfigMap in the same release
   (`templates/trusted-ca.yaml`), and the volume has no `items`. So a required volume would mount it as an empty
   directory before the operator fills it (`pkg/volume/configmap/configmap.go` lines 191-197, 273-289). Comment
   only; the setting is harmless and keeps the pod starting if the ConfigMap is ever missing. Read from source,
   not run.
2. **Stale counts in chart comments.** `values.yaml` line 958 ("The image already holds ~290 entries for the
   public CAs") and `templates/configmap-curlrc.yaml` line 5 ("its ~290 public CAs"): today's `hi/python:3.14`
   has 242 entries in `/etc/pki/tls/certs` for 121 CAs (each linked twice). `values.yaml` line 957 says a bundle
   under one hash "is only ever looked up by the first subject". It is looked up by the subject that matches
   the file name, and the other certificates are served from the cache once the file is loaded (row 4 above).
   Comments only. A change would touch `charts/` and need a chart version bump, so it is not made here.
3. **`docs/design/DESIGN_hardened_image.md` line 275** names the ConfigMap `<release>-curlrc` (the template uses
   the fullname), and line 276 repeats "~290 hashed links". Outside this batch.

## Housekeeping

- No cluster write. `oc auth can-i … --as=system:serviceaccount:kyverno:kyverno-background-controller` was run
  once. It is read-only, but it asks the API server a SubjectAccessReview as that identity (no object
  persists).
- No container runtime was started. Image files were read with `oc image extract` into the scratch directory.
- mermaid-cli and its Chromium were cached in the scratch directory (`npm_config_cache`,
  `PUPPETEER_CACHE_DIR`) and deleted afterwards with the rest of the scratch files.
