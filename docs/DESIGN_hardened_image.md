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
`chmod`, `rm`, `rmdir` (copied *without* `-L`, so they stay the one-line scripts that call the multicall
binary), `ln -s bash sh`, and **exactly the twelve libraries the runtime lacks**: `ldd` of the four
binaries gives 26 shared objects; diffed against the runtime's `/usr/lib64`, twelve are absent
(`libjq`, `libonig`, `libcurl`, `libnghttp2`, `libidn2`, `libunistring`, `libgssapi_krb5`,
`libkrb5`, `libk5crypto`, `libcom_err`, `libkrb5support`, `libkeyutils`); those twelve are packed,
none more. `libtinfo` and `libsystemd`, which fluentd-hec's pack carries, are left out on purpose:
the runtime has them, and copying them would overwrite the base's own files.

This stage also edits **a copy of the runtime's RPM database** (`COPY --from=runner
/usr/lib/sysimage/rpm`), because the runtime cannot. In order: `uninstall-lists.py` reads, out of
that database and before anything is erased, every path that `libuuid`, `python3-pip` and
`python-pip-wheel` own, into two lists — every path that is not a directory, and every directory
that no other package records. It uses the database alone (`rpm --dump` for each path's mode,
the owner table from `rpm -qa --qf '[%{=NAME}\t%{FILENAMES}\n]'`), never the pack stage's own
filesystem, which holds a different build of the same packages: its libuuid's build-id directory
is not the runtime's, so a `test -d` there misclassified a runtime directory as a file and
`rpm -qf` there could not answer for a path it did not have. Then each package is erased with
`rpm -e --justdb --nodeps`, **per package and only if it is recorded**, because the base floats
and erasing a package that is no longer there would fail the build for the wrong reason; a check
fails the build if any of the three is still recorded; the database is checkpointed explicitly
(rpm 6 keeps it in SQLite WAL mode) and the shm/wal files SQLite creates on every open are removed
last. The reasons for the three are in `image-vulnerability-scan.md`; the short form is that
`libuuid` is the one HIGH-rated package in the base and nothing needs it, and pip — installed once
as a package and once more as the wheel under `/usr/share/python-wheels` that seeds virtual
environments — is an installer nothing needs. `--justdb` touches the database only; the pack
stage's own files are not what is being uninstalled. The database that ships records, on purpose,
one dependency it cannot satisfy: `python3-libs` on `libuuid`.

**runtime** — `FROM runner`. Order is the whole point, because nothing below the base line can
run a command until the pack has landed: `ARG`s, the `ENV` block verbatim (its `GSD_LOG_LEVEL`
commentary is pinned by `tests/test_log_levels.py`), `LABEL`s, `COPY --from=build /install`,
`COPY --from=pack` of the binaries into `/usr/bin` and the libraries into `/usr/lib64`. Then, as
root for three steps, in shell form under the pack's own `sh`, one command per line: the UBI
recipe's own directory line (`mkdir -p /data /etc/gsd && chgrp -R 0 … && chmod -R g=u …`); the
uninstall from the two lists, bind-mounted from the pack stage for that one step so they enter no
layer — every listed file removed, every listed directory removed with
`rmdir`, which removes only an *empty* directory, and that is the point, because a directory no
other package records can still hold another package's file (`/usr/lib/.build-id/2d` held one,
measured, and an earlier cut's `rm -rf` took it) — then a check that fails the build if a listed
file survives or a listed directory survives empty, and the RPM database directory removed whole
(a glob would skip the dotfile lock) to be recreated by the copy of the edited database. The
first line of that step proves `rm`, `rmdir` and `ls` exist before anything is deleted, and
nothing in it hides an error: twice in this recipe's history a tool the pack did not carry failed
with "command not found" behind a `2>/dev/null || true`, and the step silently did nothing. Then
`USER 1001`, and three proofs *as that user* on the finished filesystem: `image-proof.py`, a
script staged in the build stage and bind-mounted under `/tmp` for its one step (never copied
into this image, so it is in no layer of it) that
imports every module the build stage proved (the test holds the runtime list as a superset),
requires `_uuid` and `pip` to fail to import (the removals, observed), checks the removed paths
and that the database directory holds exactly the base's two files, exercises WAL mode on
`/data`, and cleans `/data`; the dynamic loader itself listing every
library of every packed binary with none "not found" (`ld.so --list`, not `--version`, which
exercises only what a binary loads on the way to printing it); and each pack tool doing a real
unit of work — jq evaluates JSON, base64 round-trips, sh, ls, cat and curl run. `EXPOSE`,
`VOLUME`, and the `CMD` unchanged. `HEALTHCHECK` is gone: the UBI recipe documented that OCI
builds discard it and kubelet never reads it.

`tests/test_containerfile.py` holds the shape: the three bases on floating tags, no `RUN` of any
form before the pack `COPY`, the exact twelve packed libraries and every tool the final stage
names, the directory line, the lists read before the erase and consumed before the database is
replaced with `rmdir` and no hidden error, root dropped before the proofs and the `CMD`, the
proof script's imports equal to the build stage's, the exact `CMD`, the backup referenced by
nothing. It reads text and observes no image; the proofs in the image are what observe.

## Two things the interpreter could not be trusted to do

**Directory modes.** The first cut pre-created `/data` and `/etc/gsd` in the pack stage and copied
them across. They arrived as `0755` whatever the source's mode and whatever `--chmod` said:
measured, `COPY --chmod=0775` of an empty directory lands `0755`, and of a directory with a file in
it the *file* gets `0775` and the directory still `0755`. So the directories are made in the
runtime stage, after the pack has provided `mkdir`, `chgrp` and `chmod`, with the UBI recipe's own
line. Result: `drwxrwxr-x root root`, and an arbitrary UID in gid 0 creates a SQLite file under
`/data` (measured with `--user 1000:0`). That governs a bare `podman run` and an emptyDir. Under
the chart, `/data` is a PersistentVolumeClaim and `/etc/gsd` a Secret mount, and a mount's
ownership comes from the volume and the pod's supplemental groups, not from the image — on CRC the
mounted `/data` is `root:1000670000`, the project's assigned group. The image's mode is not what
makes the PVC writable; OpenShift's security context constraints are.

**The RPM database.** SQLite creates `-shm`/`-wal` files whenever `rpm` opens it. The erase step
checkpoints the database through the interpreter (`PRAGMA wal_checkpoint(TRUNCATE)`) and ends with
their removal, *after* the last command that opens it, so the copy that ships is the two files the
base shipped, `rpmdb.sqlite` and its `.rpm.lock` — and the runtime proof asserts exactly that
listing. The runtime removes its database directory whole before the copy lands; a glob such as
`rpm/*` skips dotfiles, and the review's second pass caught that the base's lock file would have
survived a merge beside a database it no longer belonged to.

**Which directories are ours to remove.** A directory that only our packages *record* can still
hold another package's *file* (`/usr/lib/.build-id/2d`: recorded by libuuid alone in the runtime
database, holding one file of another package's). `rm -rf` on such a directory took that file,
measured. So directories are removed with `rmdir`, which refuses anything but an empty directory;
a listed directory with content left is kept and the build log says so; a listed directory that
survives empty fails the build.

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
* An in-pod curl to the in-cluster API address still takes
  `--cacert /var/run/secrets/kubernetes.io/serviceaccount/ca.crt`: that CA is the cluster's own,
  present in the ServiceAccount token's `ca.crt` and not in the injected bundle (measured on CRC:
  exit 60 through the injected bundle, 200 with the ServiceAccount CA). The dashboard names that
  file explicitly for the local cluster, so nothing changes for it.
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
