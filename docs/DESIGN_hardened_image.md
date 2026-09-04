# The image on Red Hat Hardened Images

**Status: implemented** in application 0.11.0 (chart 0.10.0), PR #52. Everything in this record
was measured on 2026-09-04 unless it says otherwise; the scan results are in
`image-vulnerability-scan.md`, the three review rounds in `REVIEW_hardened_image.md`.

**How to read this.** Sections 1–3 say what exists and what was decided. Section 4 is the recipe.
Section 5 is the list of things that went wrong first and the rule each one left behind — read it
before changing the recipe. Sections 6–9 are the four areas checked rather than assumed: the
user, SQLite, TLS trust, and scanning. Section 10 is what an operator notices.

## 1. The files

| File | What it is | Built by |
|---|---|---|
| `local-development/Containerfile` | **The recipe.** The lean copy: every instruction with one short "why" and pointers here. About 280 lines. | the release scripts, `publish.yml`, `ci.yml` |
| `local-development/Containerfile.annotated` | **The same recipe, fully explained.** Instruction-for-instruction identical to the lean copy — `tests/test_containerfile.py` fails if they diverge, naming the line — with the full reasoning and every measurement beside each step, written for someone who has never seen a hardened image. Made with `cp` from the lean copy's ancestor, not rewritten. | nothing |
| `local-development/Containerfile.ubi` | **The previous recipe**, on `ubi9-minimal` with `microdnf`, as it was until 2026-09-04. | nothing |
| `local-development/uninstall-lists.py` | Run in the pack stage: reads, from the RPM database alone, the paths the uninstalled packages own (section 4.3). | — |
| `local-development/image-proof.py` | Run in the final stage as the runtime user: the image proves itself (section 4.4). | — |
| `local-development/tests/test_containerfile.py` | Holds the recipe's shape (section 4.5). Reads text; observes no image. | — |

To change the recipe: edit `Containerfile`, mirror the instruction in `Containerfile.annotated`
(the test says which line), and put the explanation in the annotated copy and here.

## 2. What was asked, and what was decided

**Asked.** Move the application image to Red Hat's hardened images — `hi/python:3.14` to run,
`hi/python:3.14-builder` to build — keeping the multi-stage build, and give the shell-less
runtime a shell plus `curl`, `jq`, `ls`, `cat` and `base64` the way `fluentd-hec`'s
`Dockerfile.curl` does it: a "pack" assembled with `dnf` in a builder stage and copied into the
runtime as files.

**Decided by the operator along the way.**

| Decision | Choice | Section |
|---|---|---|
| Base tags | The **floating** `3.14` and `3.14-builder`, so every build takes Red Hat's latest 3.14 | 4 |
| Declared user | The base's **65532**; first kept at UBI's 1001, then moved once the convention was checked | 6 |
| Scanning | The pack stage is scanned in CI as well as the shipped image | 9 |
| Directories | Made with `mkdir`/`chgrp`/`chmod`, the UBI recipe's own line, not through the interpreter | 5 |
| Readability | The recipe written for a junior engineer; the two Python steps as repository scripts | 1 |
| Teaching | A tested tutorial on the hashed directory and the three trust layouts, `TUTORIAL_ca_trust_hashed_directory.md`; its verification found the curl defect in 8.3 | 8 |
| Scope | Fix every HIGH in the shipped image; the pack stage's non-shipping HIGHs are not the target | 9 |

## 3. The runtime base, measured

`hi/python:3.14`, from its layers and from running it:

| | |
|---|---|
| OS | Hummingbird OS 20251124 (`ID_LIKE="fedora rhel"`) |
| User | 65532, gid 0, `HOME=/tmp`; no passwd entry, no group 65532 |
| Entrypoint | none; `CMD python3` |
| Shell | **none of any kind** — no `/bin/sh`, no bash, no coreutils |
| Python | `/usr/bin/python3.14` 3.14.7; site-packages split across `/usr/lib` and `/usr/lib64` exactly as UBI's, so the `--prefix=/install` tree, `PYTHONPATH` and the chart's `command:` are unchanged |
| SQLite | 3.53.4 (UBI: 3.34.1) |
| Zoneinfo | `/usr/share/zoneinfo` present (the UBI recipe had to reinstall tzdata) |
| Libraries | `libtinfo.so.6`, `libsystemd.so.0` present; no libcurl, krb5, jq, onig |
| Packages | an RPM database at `/usr/lib/sysimage/rpm/rpmdb.sqlite` (13 MB, 49 packages) with **no `rpm` binary to read it**; no `dnf`; a working `python3.14 -m pip` (pip 26.2) but no `pip` executable |
| Paths | `/bin` is a symlink to `/usr/bin` |

The builder (`hi/python:3.14-builder`) adds `sh`, `bash`, `dnf`, `rpm`, `pip3.14`, `ldd`,
coreutils, a full `curl`, and a `hummingbird.repo` pointing at
`packages.redhat.com/api/pulp-content/public-hummingbird/`. No `gcc`, no `make` — fine, the
application's wheel is pure Python and every compiled dependency ships a prebuilt cp314 wheel.

## 4. The recipe, stage by stage

Four stages. Only files cross between them: by `COPY --from`, which writes a layer of the image,
or by `RUN --mount=type=bind`, which lends a file to one step and leaves nothing in any layer.

### 4.1 `build` — the application and its dependencies, into `/install`

`pip install --prefix=/install` of the wheel, proven to import under the builder's interpreter.
No `dnf update`: only `/install` leaves this stage, so updating its RPMs would change nothing that
ships. The final stage's proof script is staged here too (`COPY --chmod=0644`), because the final
stage bind-mounts it from this stage (section 5, "bind mounts").

### 4.2 `runner` — the runtime base, named once

The pack stage reads its RPM database and the final stage is built on it; naming it makes both
refer to one pull of the floating tag within a build.

### 4.3 `pack` — what the runtime cannot install for itself

The same builder as 4.1, built from the same repository as the runtime, so every library copied
out matches the runtime's glibc. Here `dnf update` *does* earn its place: what this stage packs
ships, so it must carry Red Hat's current fixes. Three products leave it.

**The tools.** `dnf swap libcurl libcurl-minimal` (full libcurl drags eleven more packages —
LDAP, libssh, HTTP/3, brotli, sasl, fido2 …), `dnf install jq` (bash, curl and coreutils are
already on the builder), then `cp -L` of `jq`, `bash`, `curl` and the `coreutils` multicall binary;
the shims `cat`, `ls`, `base64`, `mkdir`, `chgrp`, `chmod`, `rm`, `rmdir` copied *without* `-L`
so they stay the one-line scripts that call the multicall binary; `ln -s bash sh`; and **exactly
the twelve libraries the runtime lacks**. `ldd` of the four binaries gives 26 shared objects;
diffed against the runtime's `/usr/lib64`, twelve are absent — `libjq`, `libonig`, `libcurl`,
`libnghttp2`, `libidn2`, `libunistring`, `libgssapi_krb5`, `libkrb5`, `libk5crypto`,
`libcom_err`, `libkrb5support`, `libkeyutils` — and those twelve are packed, none more.
`libtinfo` and `libsystemd`, which fluentd-hec's pack carries, are left out: the runtime has
them, and copying them would overwrite the base's own files.

**The edited RPM database.** A copy of the runtime's (`COPY --from=runner
/usr/lib/sysimage/rpm`), because the runtime has no `rpm`. Three packages are uninstalled from
the shipped image:

| Package | Why it goes |
|---|---|
| `libuuid` | The base's one HIGH-rated package: four util-linux advisories of 2026-09-02, all in `libmount`, `mount(8)` and `nsenter`, none of which the base ships; flagged by source package. Red Hat lists Hardened Images as *Affected* with no fixed build in the repository. Nothing needs it: only Python's `_uuid` module links it, and `uuid` falls back to pure Python without it. |
| `python3-pip` | pip. Nothing needs it — the application arrives installed from 4.1 — and an installer in production is surface for nothing. Also the base's only Python findings: pip's vendored msgpack 1.1.2 and setuptools 70.3.0. |
| `python-pip-wheel` | The same pip again, as a wheel under `/usr/share/python-wheels` that seeds `python -m venv`. Nothing here makes a venv. |

An uninstall is files *and* record, or the inventory lies. In order: `uninstall-lists.py` reads,
out of the copied database and before anything is erased, every path the three own, into two
lists — every path that is not a directory, and every directory that no other package records.
It uses the database alone: `rpm --dump` for each path's mode, and the owner table from
`rpm -qa --qf '[%{=NAME}\t%{FILENAMES}\n]'`; never the pack stage's own filesystem (section 5).
Then each package is erased with `rpm -e --justdb --nodeps` — `--justdb` edits the database
only, `--nodeps` because `python3-libs` names `libuuid` and the fallback makes that optional —
**per package and only if it is recorded**, because the base floats. A check fails the build if
any of the three is still recorded; the database is checkpointed explicitly (rpm 6 keeps it in
SQLite WAL mode) and the `-shm`/`-wal` side files are removed last, so what ships is the two
files the base shipped: `rpmdb.sqlite` and its `.rpm.lock`. The shipped database records, on
purpose, one dependency it cannot satisfy: `python3-libs` on `libuuid`.

### 4.4 `final` — the image that ships

`FROM runner`. Order is the whole point, in four movements:

1. **Metadata and copies only — no shell exists yet.** `ARG`s, the `ENV` block verbatim (its
   `GSD_LOG_LEVEL` commentary is pinned by `tests/test_log_levels.py`), `LABEL`s,
   `COPY --from=build /install`, then the pack's binaries into `/usr/bin` and libraries into
   `/usr/lib64`. From that line on, a shell exists.
2. **As root, under the pack's `sh`, one command per line.** The UBI recipe's own directory line
   (`mkdir -p /data /etc/gsd && chgrp -R 0 … && chmod -R g=u …`). Then the uninstall, from the
   two lists bind-mounted from the pack stage: every listed file removed; every listed directory
   removed with `rmdir`, which removes only an *empty* directory; a listed file that survives, or
   a listed directory that survives empty, fails the build; a listed directory with content is
   kept and named in the log. The first line of that step proves `rm`, `rmdir` and `ls` exist,
   and nothing in it hides an error. Then the RPM database directory removed whole and recreated
   by the copy of the edited database.
3. **Drop to `USER 65532`** (section 6).
4. **Prove the image, as that user, on the finished filesystem.**

| Proof | What it establishes |
|---|---|
| `image-proof.py`, bind-mounted from the build stage under `/tmp` | Every module the build stage proved imports under the runtime's interpreter; SQLite works in WAL mode on `/data`; zoneinfo resolves; `uuid` works while `_uuid` must *fail* to import (the libuuid removal, observed); `pip` is not importable; the paths the uninstall once missed are gone; the database directory holds exactly the base's two files. It cleans `/data` after itself and is in no layer. |
| `ld.so --list` of every packed binary | Every library resolves, asked of the dynamic loader itself; a missing one reads "not found". `--version` only exercises what a binary loads on the way to printing a string. x86-64 loader path: the image is built for linux/amd64 only. |
| One unit of work per tool | jq evaluates JSON, base64 round-trips, sh, ls, cat and curl run. |

Then `EXPOSE`, `VOLUME`, and the `CMD` unchanged from the UBI recipe. `HEALTHCHECK` is gone: OCI
builds discard it and kubelet reads the chart's probes, never the image's.

### 4.5 What the unit test holds

`tests/test_containerfile.py`: the three bases on floating tags; no `RUN` of any form before the
pack `COPY`; the exact twelve packed libraries and every program the final stage names, parsed
out of its `RUN` lines; the directory line; the lists read before the erase and consumed before
the database is replaced, `rmdir` only, no glob, no hidden error, `IFS=` on every read; root
dropped before the proofs and the `CMD`; the proof script's imports a superset of the build
stage's (parsed with `ast`); the list script's decisions; the exact `CMD`; the annotated copy
identical instruction for instruction; the two backups built by nothing. It reads text and
observes no image — the proofs in the image are what observe.

## 5. What went wrong first, and the rule each one left

Every row was a real failure on 2026-09-04, found by a rebuild, a probe, or a reviewer, and
verified before the rule was written. Read this before changing the recipe.

| Symptom | Cause | Rule now in the recipe |
|---|---|---|
| `/data` arrived `0755`, unwritable by an arbitrary UID | A `COPY` of an empty directory lands `0755` whatever the source's mode and whatever `--chmod` says (`--chmod` reaches a directory's contents, never the directory) | Directories are made in the final stage with `mkdir`/`chgrp 0`/`chmod g=u`, after the pack provides the tools |
| pip's 1.3 MB wheel shipped with its record erased | The removal list was written by hand and missed `python-pip-wheel`'s files | The lists come from the RPM database (`uninstall-lists.py`), before the erase; a listed file that survives fails the build |
| The directory cleanup silently did nothing, twice | `sort`, then `rmdir`, were not among the packed tools; "command not found" was hidden behind `2>/dev/null \|\| true` | The step proves its tools exist before deleting; nothing in it hides an error; the deepest-first order is computed in the pack stage |
| A runtime directory was listed as a file; the step failed | Paths were classified with `test -d` on the pack stage's own filesystem, which holds a *different build* of the same packages (its libuuid's build-id directory is not the runtime's) | Classification comes from `rpm --dump`'s mode field, never from the filesystem |
| `rpm -qf` could not answer for a runtime path | Same cause: the path did not exist on the pack stage's disk | Ownership comes from the database's owner table |
| Every directory looked exclusively ours | The owner query's format string lacked `=`; rpm printed errors and returned an empty table, and the empty set is a subset of anything | `[%{=NAME}\t%{FILENAMES}\n]`; an empty table, or a path the table does not know, is an exit code |
| Another package's file was deleted from `/usr/lib/.build-id/2d` | `rm -rf` on a directory only our packages *record* — such a directory can still hold another package's *file* | Directories go only with `rmdir`, which refuses anything but an empty directory; a listed directory with content is kept |
| The base's `.rpm.lock` survived beside a replaced database | `rm -rf …/rpm/*` skips dotfiles; the copy was a merge | The database directory is removed whole and recreated by the copy |
| The lists and the proof script sat in a lower layer of the image | `COPY` then delete in a later step leaves the file in the earlier layer | Both are `RUN --mount=type=bind` for their one step; the saved image's layers were listed to confirm |
| The mounted proof script was unreadable by the runtime user | A context file bind-mounted directly arrives with the host's ownership | The script is staged in the build stage with mode 0644 and mounted from there |
| The proof failed on its own path | It asserted `/tmp/image-proof.py` was absent while running from it | Absence from layers is checked from outside, on the saved image, not from inside the step |

## 6. The declared user: 65532, the base's own

The UBI recipe declared `USER 1001`, and the first cut kept it so that nothing about the image's
declared identity moved with the base. The operator then asked what the number costs on OpenShift
and what others do with the hardened images. Measured and read:

* **On OpenShift the declared user is never the UID the process runs as.** The default
  `restricted-v2` SCC replaces it with an arbitrary UID from the project's range and puts that UID
  in the root group — on CRC the container declaring `1001` ran as `1000670000`, gid 0, and so does
  the one declaring `65532`. The number matters only for the `runAsNonRoot` check, which needs it
  numeric and non-zero (both pass), and outside OpenShift, where it is the real UID.
* **65532 is the convention**: the hardened base's own default, the `nonroot` user of Google's
  distroless images and Chainguard's, and what Red Hat's Hummingbird examples declare
  (`USER ${CONTAINER_DEFAULT_USER}`, defined as 65532 in the builder; `COPY --chown=65532`). There
  is no passwd entry and no group 65532 in the runtime base; the UID stands alone, which is fine
  because only the number is ever read.
* **Group 65532 ownership helps nobody on OpenShift**, as Docker's guide for its hardened images
  says: the arbitrary UID is not in it. This recipe never relied on it; writable directories are
  root-group and group-writable.

So the declared user moved to 65532, stated explicitly in the Containerfile rather than inherited,
so that a base that changed its default would not change ours silently. Nothing else moved: the
chart sets no `runAsUser`, the directories are group-owned by root, the proofs run as the
declared user and pass, and the pod on CRC runs as the same arbitrary UID as before.

## 7. SQLite, checked rather than assumed

The application's store is the part of the image most sensitive to a base change, so it was
probed in the built image, as the declared user and again under a read-only root filesystem with
`/data` and `/tmp` mounted, the way the chart runs it.

| Checked | Result |
|---|---|
| `sqlite3.sqlite_version` / `threadsafety` | 3.53.4 / 3 |
| `enable_load_extension` (the store calls it) | present |
| `PRAGMA journal_mode=WAL` on `/data` | `wal`; `-wal` and `-shm` files created |
| `busy_timeout` | takes |
| JSON functions, `->>`, FTS5, R-tree, math and window functions, `STRICT` tables | all present |
| Temp store | on disk, `/tmp` writable |
| `SQLITE_MAX_VARIABLE_NUMBER` | 32766, unchanged from UBI — the store's chunking is still exercised |
| Compile options | Red Hat's: `gcc 16.1.1`, `SECURE_DELETE`, `ENABLE_FTS5`, `ENABLE_RTREE`, `ENABLE_MATH_FUNCTIONS`, `THREADSAFE=1` |

## 8. TLS trust, for the application and for curl in the pod

### 8.1 What the application does

It uses httpx with an `ssl.SSLContext` it builds itself (`gsd/config.py#ClusterConfig.verify`): a
cluster's own `caBundleFile` if it names one, else the bundles named in `GSD_TRUSTED_CA_FILE`
loaded onto a default context (`gsd/config.py#_trusted_ca_context`), else httpx's default, which
is certifi. The chart supplies the bundles: `trustedCA.injected` creates the ConfigMap labelled
`config.openshift.io/inject-trusted-cabundle: "true"` that OpenShift fills with the cluster's
trust store, `trustedCA.existingConfigMap` adds a bundle the cluster has never been told about,
and both are named in `GSD_TRUSTED_CA_FILE` (`charts/group-sync-dashboard/values.yaml#trustedCA`).

Measured in the built image against a public host, all verifying and identical to the UBI image:
OpenSSL's default context (the runtime has no `/etc/pki/tls/cert.pem`, but `/etc/pki/tls/certs/`
is the hashed directory OpenSSL's `capath` reads); the fallback context with the injected bundle
loaded, including one absent path in the colon-separated list; the explicit `caBundleFile` path;
httpx's certifi default; and `_trusted_ca_context()` end to end through httpx.

Hummingbird's page on custom CAs with Python
([docs/using/custom-ca-python](https://hummingbird-project.io/docs/using/custom-ca-python/))
describes `urllib` and `requests`. This application uses neither; `requests` is not installed
because nothing imports it, and a dependency nothing uses is only surface.

### 8.2 What curl in the pod does, and which variable reaches whom

curl reads none of the application's settings; it trusts the image's own bundle,
`/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem`, so a public URL verifies and a
corporate-signed one does not, even though the application verifies it. Which variable reaches
which client was measured by pointing each at a missing file:

| Variable | curl | httpx (the application) | urllib |
|---|---|---|---|
| `REQUESTS_CA_BUNDLE` | ignored | ignored | ignored |
| `CURL_CA_BUNDLE` | read | ignored | ignored |
| `SSL_CERT_FILE` | read | read | read |
| `SSL_CERT_DIR` | read | read | read |

`REQUESTS_CA_BUNDLE` is the `requests` library's alone. `SSL_CERT_FILE` would reach everything at
once, which is why it is not used: curl fails outright (exit 77) on an empty or missing file, the
injected ConfigMap is empty for the moments before OpenShift fills it, and a variable that breaks
the application's own polling in that window is the wrong trade for an interactive curl.

### 8.3 What chart 0.10.0 does

| Setting | When | Effect |
|---|---|---|
| a `.curlrc` ConfigMap (`<release>-curlrc`) mounted at `/etc/curl`, `CURL_HOME=/etc/curl` | always | curl's own configuration, read by the curl tool alone. `capath = /etc/pki/tls/certs` always — OpenSSL's hashed directory, which every OpenSSL client already reads by default and curl consults only when told. `cacert = <injected bundle>` when `trustedCA.injected` is on — the cluster's trust store, the system CAs merged with the cluster's CA, so curl loses nothing. The manual ConfigMap never becomes `cacert`: it carries only the extra CA, and one `cacert` replaces the default bundle. |
| `trustedCA.existingConfigMap.subjectHash` | when set | Hummingbird's "Approach 2": the manual CA mounted a second time as `/etc/pki/tls/certs/<hash>.0` (or `<hash>.N` on a collision), a subPath mount of one file — never the directory, which would hide the base's ~290 hashed links. Measured with a self-signed host's CA mounted that way: curl (through the `.curlrc`'s `capath`), urllib and the application's fallback context all verify it. The injected bundle cannot take this route: one file with 149 certificates, and a hashed entry is looked up by one subject. |

**Why a file and not two variables.** The first version set `CURL_CA_BUNDLE` for the injected
bundle and `SSL_CERT_DIR` for the hashed directory. Writing the tutorial
(`TUTORIAL_ca_trust_hashed_directory.md`) and verifying it in a pod that carried both showed
that **curl reads `SSL_CERT_DIR` only when `CURL_CA_BUNDLE` is unset** — `curl -v` named only the
`CAfile`, and the hashed CA that Python verified was invisible to curl. Measured on curl 7.76
(UBI 9) and 8.22 (the hardened image). Environment variables can therefore give curl one store
or the other, never both. `.curlrc` names both, `curl -v` reports `CAfile` and `CApath`, and the
mechanism has one more property the variables lacked: nothing but the curl tool reads it, so the
application's TLS, Python's default context and libcurl users cannot be affected by it. That is
also the answer to which variable is safe for the Python application — none is needed; the
application is configured by `GSD_TRUSTED_CA_FILE` and its own `caBundleFile`, OpenSSL's default
`capath` serves its fallback context unchanged, and curl is now configured by a file the
application never opens.

**Proven on the deployed chart, from the dashboard pod.** With default values: `curl -v` reports
`CAfile` (the injected bundle) and `CApath` (`/etc/pki/tls/certs`), a public host verifies, and a
server signed by a CA the cluster does not know is refused (exit 60). With
`trustedCA.existingConfigMap` naming that CA and `subjectHash=7886c608`: the hashed file is
mounted, and the enterprise server is verified by curl, by the application's own
`_trusted_ca_context()` through httpx, and by urllib's default context — while public hosts still
verify and the application keeps polling. Measured 2026-09-04 against the tutorial's TLS server
(`TUTORIAL_ca_trust_hashed_directory.md`, Part 3.2).

One address stays outside both: the in-cluster API (`https://kubernetes.default.svc`) is signed
by the cluster's own CA, present in the ServiceAccount's `ca.crt` and not in the injected bundle
(measured on CRC: exit 60 through the injected bundle, 200 with the ServiceAccount CA). An
in-pod curl to it takes `--cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt`, as it
always did; the dashboard names that file explicitly for the local cluster.

## 9. Scanning and the CI gate

The full analysis is `image-vulnerability-scan.md`. The facts that shaped the workflow:

* **Trivy does not recognise Hummingbird OS.** It reports no OS, reads no RPM database, and scans
  the Python packages alone; told `--distro redhat/10` it reads the database and matches nothing.
  A green Trivy gate on this image assesses nothing.
* **Grype does**, from v0.113 on, and it is the scanner Red Hat's own documentation names. The
  action's default Grype (v0.110.0 on 2026-09-04) predates that support and reported zero matches
  across 84 packages; the workflow pins `grype-version: v0.118.0` and ends with a step that fails
  the job if Grype did not name the distribution.
* The gate runs on the shipped image and on the pack stage, fails only on fixable findings at
  HIGH and above, and a separate non-blocking step shows the full inventory.
* Result on the shipped image: 0 CRITICAL, 0 HIGH, 12 Medium, 2 Low, 0 fixable (glibc, the
  interpreter, openssl — Red Hat's to move). The pack stage's 26 HIGHs are in rpm and util-linux
  libraries that never leave the builder.

## 10. What it changed for operators

* The image is 186 MB (UBI: 227 MB) and scans at zero CRITICAL, zero HIGH, zero fixable.
* `oc exec … -- sh -c '…'`, `curl`, `jq`, `ls`, `cat`, `base64` all work in the pod, so every
  in-pod command in the docs still holds and the release scripts' stamp check still runs. `head`,
  `wc`, `grep`, `id` are **not** packed; an `oc exec` that needs them fails with "command not
  found" rather than something subtler.
* No `pip` and no package manager in the runtime: nothing can be installed into a running pod.
* Timezone needs nothing installed; the base ships zoneinfo and the build proves it.
* An in-pod curl to a corporate-signed URL verifies; to the in-cluster API it takes the
  ServiceAccount CA (section 8.3).
* `Chart.yaml` `appVersion` 0.11.0; chart 0.10.0 adds curl's `.curlrc` ConfigMap with
  `CURL_HOME`, and `trustedCA.existingConfigMap.subjectHash` for the hashed mount.

## Sources

* Red Hat Hardened Images and Project Hummingbird —
  [hummingbird-project.io/docs/using](https://hummingbird-project.io/docs/using/overview/) (the
  builder/runtime pattern, "Use Syft and Grype to locally inspect and scan images", UID 65532),
  [security labels and metadata](https://hummingbird-project.io/docs/background/containers/security-labels-and-metadata/)
  (per-architecture SPDX SBOM as an OCI artifact, VEX by CPE), and
  [custom CA certificates with Python](https://hummingbird-project.io/docs/using/custom-ca-python/).
* Red Hat Developer, the Hummingbird Python articles that declare `USER ${CONTAINER_DEFAULT_USER}`:
  [Build trusted Python containers with Project Hummingbird and Calunga](https://developers.redhat.com/articles/2026/05/05/build-trusted-python-containers-project-hummingbird-and-calunga)
  and [Fun in the RUN instruction](https://developers.redhat.com/articles/2026/05/14/understanding-distroless-images-red-hat-hardened-images).
* Docker, [Use Docker Hardened Images with Red Hat OpenShift](https://docs.docker.com/guides/dhi-openshift/):
  the SCC overrides the image's user; group 65532 helps nobody on OpenShift.
* Red Hat security data API for the util-linux advisories, e.g.
  [CVE-2026-76642](https://access.redhat.com/security/cve/CVE-2026-76642): "Fixed in v2.41.6 and
  v2.42.3"; Red Hat Hardened Images `fix_state: Affected`.
* Trivy's supported operating systems — [trivy.dev/docs/latest/coverage/os](https://trivy.dev/docs/latest/coverage/os/):
  no Hummingbird.
* The pack pattern — `fluentd-hec/docker/Dockerfile.curl`, the operator's reference build.
