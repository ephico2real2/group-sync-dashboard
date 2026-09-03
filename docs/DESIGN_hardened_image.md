# The image on Red Hat Hardened Images

**Status: implemented** in application 0.11.0 (chart 0.10.0). The recipe is
`local-development/Containerfile`; the recipe it replaced is kept beside it as
`local-development/Containerfile.ubi`, built by nothing. The scan results are in
`image-vulnerability-scan.md`. Everything below is measured on 2026-09-04 unless it says otherwise.

## What was asked

Move the application image to Red Hat's hardened images — `registry.access.redhat.com/hi/python:3.14`
to run, `hi/python:3.14-builder` to build — keeping the multi-stage build, and give the shell-less
runtime a shell plus `curl`, `jq`, `ls`, `cat` and `base64` the way `fluentd-hec`'s
`Dockerfile.curl` does it: a "pack" assembled with `dnf` in a builder stage and copied into the
runtime as files. Operator decisions on the way: the **floating** `3.14` tags, so every build takes
Red Hat's latest 3.14; the declared user stays **1001**; the pack stage is scanned in CI as well as
the shipped image; directories are made with `mkdir`/`chgrp`/`chmod`, not through the interpreter.

## What the runtime base is

`hi/python:3.14`, from its layers and from running it:

* Hummingbird OS 20251124 (`ID_LIKE="fedora rhel"`). User 65532, gid 0, `HOME=/tmp`, no
  entrypoint, `CMD python3`. **No shell of any kind.**
* `/usr/bin/python3.14` 3.14.7, site-packages split across `/usr/lib/python3.14` and
  `/usr/lib64/python3.14` exactly as UBI's — so the `--prefix=/install` wheel tree, the
  `PYTHONPATH` and the chart's `command: python3.14 -m uvicorn …` are unchanged.
* SQLite 3.53.4. `/usr/share/zoneinfo` present. `libtinfo.so.6` and `libsystemd.so.0` present.
* An RPM database at `/usr/lib/sysimage/rpm/rpmdb.sqlite` (13 MB, 49 packages) and **no `rpm`
  binary to read it**. No `dnf`. A working `python3.14 -m pip` (pip 26.2) but no `pip` executable.
* No coreutils, no bash, no curl, no libcurl, no krb5, no jq. `/bin` is a symlink to `/usr/bin`.

The builder adds `sh`, `bash`, `dnf`, `rpm`, `pip3.14`, `ldd`, coreutils, a full `curl`, and a
`hummingbird.repo` pointing at `packages.redhat.com/api/pulp-content/public-hummingbird/`. No
`gcc`, no `make` — fine, the application's wheel is pure Python and every compiled dependency ships
a prebuilt cp314 wheel.

## The recipe, stage by stage

**`build`** — the wheel and its dependency tree, `pip install --prefix=/install`, proven to
import under the builder. No `dnf update`: nothing a builder RPM touches reaches the runtime; only
`/install` crosses.

**`runner`** — the runtime base named once, so the pack stage and the final stage resolve the
floating tag to the same pull within a build.

**`pack`** — the builder after `dnf update`, which here *does* earn its place because everything
copied out ships. `dnf swap libcurl libcurl-minimal` (full libcurl drags eleven more packages —
LDAP, libssh, HTTP/3, brotli, sasl, fido2 …), `dnf install jq`, then `cp -L` of `jq`, `bash`,
`curl`, the `coreutils` multicall binary, and the shims `cat`, `ls`, `base64`, `mkdir`, `chgrp`,
`chmod`, `rm` (copied *without* `-L`, so they stay the one-line scripts that call the multicall
binary), `ln -s bash sh`, and **exactly the twelve libraries the runtime lacks**: `ldd` of the four
binaries gives 26 shared objects; diffed against the runtime's `/usr/lib64`, twelve are absent
(`libjq`, `libonig`, `libcurl`, `libnghttp2`, `libidn2`, `libunistring`, `libgssapi_krb5`,
`libkrb5`, `libk5crypto`, `libcom_err`, `libkrb5support`, `libkeyutils`); those twelve are packed,
none more. `libtinfo` and `libsystemd`, which fluentd-hec's pack carries, are left out on purpose:
the runtime has them, and copying them would overwrite the base's own files.

This stage also edits **a copy of the runtime's RPM database** (`COPY --from=runner
/usr/lib/sysimage/rpm`), because the runtime cannot: `rpm -e --justdb --nodeps libuuid
python3-pip python-pip-wheel`. The reasons are in `image-vulnerability-scan.md`; the short form is
that `libuuid` is the one HIGH-rated package in the base and nothing needs it, and pip is an
installer nothing needs. `--justdb` touches the database only; the pack stage's own files are not
what is being uninstalled.

**runtime** — `FROM runner`. Order is the whole point, because nothing below the base line can be
a shell-form `RUN` until the pack has landed: `ARG`s, the `ENV` block verbatim (its `GSD_LOG_LEVEL`
commentary is pinned by `tests/test_log_levels.py`), `LABEL`s, `COPY --from=build /install`,
`COPY --from=pack` of the binaries into `/usr/bin` and the libraries into `/usr/lib64`. Then, as
root for three steps: the UBI recipe's own directory line (`mkdir -p /data /etc/gsd && chgrp -R 0
… && chmod -R g=u …`), the file removals for `libuuid` and pip, and the edited RPM database copied
over the base's. Then `USER 1001`, and two exec-form proofs *as that user*: the wheel tree imports
under the runtime's interpreter with `sqlite3`, `zoneinfo` and `uuid` working; and `curl`, `jq`,
`ls`, `cat`, `base64` all run under the pack's own shell, which is the same as saying every library
they need is present. `EXPOSE`, `VOLUME`, and the `CMD` unchanged. `HEALTHCHECK` is gone: the UBI
recipe documented that OCI builds discard it and kubelet never reads it.

`tests/test_containerfile.py` holds the shape: the three bases on floating tags, no shell-form
`RUN` before the pack `COPY`, the directory line, the two uninstalls, root dropped before the
proofs and the `CMD`, exec-form `CMD`, the backup referenced by nothing.

## Two things the interpreter could not be trusted to do

**Directory modes.** The first cut pre-created `/data` and `/etc/gsd` in the pack stage and copied
them across. They arrived as `0755` whatever the source's mode and whatever `--chmod` said:
measured, `COPY --chmod=0775` of an empty directory lands `0755`, and of a directory with a file in
it the *file* gets `0775` and the directory still `0755`. So the directories are made in the
runtime stage, after the pack has provided `mkdir`, `chgrp` and `chmod`, with the UBI recipe's own
line. Result: `drwxrwxr-x root root`, and an arbitrary UID in gid 0 creates a SQLite file under
`/data` (measured with `--user 1000:0`).

**The RPM database.** SQLite creates `-shm`/`-wal` files whenever `rpm` opens it. The erase step
ends with their removal, *after* the last `rpm` command, so the copy that ships is the one file the
base shipped.

## SQLite, checked rather than assumed

The application's store is the part of the image most sensitive to a base change, so it was probed
in the built image, as user 1001 and again under a read-only root filesystem with `/data` and
`/tmp` mounted, the way the chart runs it: `sqlite3.sqlite_version` 3.53.4, `threadsafety` 3,
`enable_load_extension` present (the store calls it), `PRAGMA journal_mode=WAL` on `/data` returns
`wal` and creates the `-wal`/`-shm` files, `busy_timeout` takes, JSON functions and `->>`, FTS5,
R-tree, math and window functions, `STRICT` tables, temp store on disk with `/tmp` writable, and
`SQLITE_MAX_VARIABLE_NUMBER` still 32766. The compile options are Red Hat's (`gcc 16.1.1`,
`SECURE_DELETE`, `ENABLE_FTS5`, `ENABLE_RTREE`, `ENABLE_MATH_FUNCTIONS`, `THREADSAFE=1`).

## Trust store, checked against the Hummingbird guidance

Hummingbird's page on custom CAs with Python
([docs/using/custom-ca-python](https://hummingbird-project.io/docs/using/custom-ca-python/)) makes
two points: `urllib` reads `/etc/pki/tls/cert.pem` and `/etc/pki/tls/certs/`, while `requests`
ignores `/etc/pki` and needs `REQUESTS_CA_BUNDLE`; and on OpenShift the cluster-wide bundle can be
had from a ConfigMap labelled `config.openshift.io/inject-trusted-cabundle: "true"`, which the
page mounts over `/etc/pki/tls/cert.pem` with `subPath: ca-bundle.crt`.

This application uses neither `urllib` nor `requests` for the API servers it polls. It uses httpx
with an `ssl.SSLContext` it builds itself (`gsd/config.py#ClusterConfig.verify`): a cluster's own
`caBundleFile` if it names one, else the bundles named in `GSD_TRUSTED_CA_FILE` loaded onto a
default context (`gsd/config.py#_trusted_ca_context`), else httpx's default, which is certifi. The
chart already does what the page describes and more: `trustedCA.injected` creates the labelled
ConfigMap and mounts its `ca-bundle.crt`, `trustedCA.existingConfigMap` adds a bundle the cluster
has never been told about, and both paths are named in `GSD_TRUSTED_CA_FILE`
(`charts/group-sync-dashboard/values.yaml#trustedCA`). The bundle is mounted under the chart's
`mountPath`, not over `/etc/pki/tls/cert.pem`, because the app is told where it is.

**curl in the pod is the exception**, and it is what the operator's question was about. curl
reads none of the application's settings; it trusts the image's own bundle,
`/etc/pki/ca-trust/extracted/pem/tls-ca-bundle.pem` (its `-v` output names it), so a public URL
verifies and a corporate-signed one does not, even though the application verifies it. Which
variable reaches which client was measured by pointing each at a missing file:

| Variable | curl | httpx (the application) | urllib |
|---|---|---|---|
| `REQUESTS_CA_BUNDLE` | ignored | ignored | ignored |
| `CURL_CA_BUNDLE` | read | ignored | ignored |
| `SSL_CERT_FILE` | read | read | read |
| `SSL_CERT_DIR` | read | read | read |

`REQUESTS_CA_BUNDLE` is the `requests` library's alone, and nothing in the image imports it.
`SSL_CERT_FILE` would reach everything at once, which is why it is not used: curl fails outright
(exit 77) on an empty or missing file, the injected ConfigMap is empty for the moments before
OpenShift fills it, and a variable that breaks the application's own polling in that window is
the wrong trade for an interactive curl. So chart 0.10.0 does two things:

* `CURL_CA_BUNDLE` names the injected bundle when `trustedCA.injected` is on. It is curl's
  variable alone, and the injected bundle is the system store merged with the cluster's trusted
  CA, so curl loses nothing. The manual ConfigMap never goes there: it carries only the extra CA
  and curl reads one file.
* `SSL_CERT_DIR=/etc/pki/tls/certs`, always. That is OpenSSL's compiled default in this image
  (`ssl.get_default_verify_paths()` reports it), so the application and httpx see no change —
  measured: public hosts verify, a self-signed host is still refused, the fallback context is
  unchanged. curl, which ignores the directory unless told, now reads it. And that is what makes
  Hummingbird's "Approach 2" work for the manual CA: `trustedCA.existingConfigMap.subjectHash`,
  the eight hex digits of `openssl x509 -noout -subject_hash`, mounts the same ConfigMap a second
  time as `/etc/pki/tls/certs/<hash>.0` (a subPath mount of one file, never the directory, which
  would hide the base's ~290 hashed links). Measured with a self-signed host's CA mounted that
  way: curl with the directory, urllib and the application's fallback context all verify it;
  httpx's certifi default and an explicit `caBundleFile` do not, by design. The injected bundle
  cannot take this route: it is one file with 149 certificates, and a hashed entry is looked up
  by one subject.

Measured in the built image, against a public host, all of it verifying and identical to the UBI
image: OpenSSL's default context (the runtime has no `/etc/pki/tls/cert.pem`, but its
`/etc/pki/tls/certs/` is the hashed directory, and that is what OpenSSL's `capath` is); the app's
fallback path with the injected bundle loaded onto it, including one absent path in the
colon-separated list; the explicit `caBundleFile` path; httpx's certifi default; and
`_trusted_ca_context()` itself, end to end through httpx. No `requests` is installed because
nothing imports it, and installing a dependency nothing uses is only surface.

## What it changed for operators

* The image is 186 MB (UBI: 227 MB) and scans at zero CRITICAL, zero HIGH, zero fixable.
* `oc exec … -- sh -c '…'`, `curl`, `jq`, `ls`, `cat`, `base64` all work in the pod, so every
  in-pod command in the docs still holds and the release scripts' stamp check still runs. `head`,
  `wc`, `grep`, `id` are **not** packed; an `oc exec` that needs them fails with "command not
  found" rather than something subtler.
* No `pip` and no package manager in the runtime: nothing can be installed into a running pod.
* Timezone needs nothing installed; the base ships zoneinfo and the build proves it.
* CI scans with Grype, on the shipped image and on the pack stage, gating on fixable HIGH.
* `Chart.yaml` `appVersion` 0.11.0; chart 0.10.0 adds `SSL_CERT_DIR`, `CURL_CA_BUNDLE` for the
  injected bundle, and `trustedCA.existingConfigMap.subjectHash` for the hashed mount.

## Sources

* Red Hat Hardened Images and Project Hummingbird —
  [hummingbird-project.io/docs/using](https://hummingbird-project.io/docs/using/overview/) (the
  builder/runtime pattern, "Use Syft and Grype to locally inspect and scan images", UID 65532),
  [security labels and metadata](https://hummingbird-project.io/docs/background/containers/security-labels-and-metadata/)
  (per-architecture SPDX SBOM as an OCI artifact, VEX by CPE), and
  [custom CA certificates with Python](https://hummingbird-project.io/docs/using/custom-ca-python/).
* Red Hat security data API for the util-linux advisories, e.g.
  [CVE-2026-76642](https://access.redhat.com/security/cve/CVE-2026-76642): "Fixed in v2.41.6 and
  v2.42.3"; Red Hat Hardened Images `fix_state: Affected`.
* Trivy's supported operating systems — [trivy.dev/docs/latest/coverage/os](https://trivy.dev/docs/latest/coverage/os/):
  no Hummingbird.
* The pack pattern — `fluentd-hec/docker/Dockerfile.curl`, the operator's reference build.
