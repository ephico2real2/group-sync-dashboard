# Review record — the image on Red Hat Hardened Images (PR #52)

Two adversarial reviews of branch `feat/hardened-image` at `6b09e89`, 2026-09-04, from one brief
of sixteen numbered claims (A1–A7 the Containerfile, B1–B4 the chart, C1–C2 CI, D1–D3 docs and
tests), each to be confirmed or refuted with a line. Codex (thread `01a069b6-fe38-7b61-b140-ccc4321367ed`)
and Cursor (`cursor agent --mode ask`). Neither could run podman or the suite; both judged the
files. Every finding below was re-checked against the built image before it was accepted or
declined; the verdict column is mine, not theirs.

## Findings and what happened to them

| # | Raised by | Finding | Verified how | Outcome |
|---|---|---|---|---|
| 1 | Codex (blocker) | `python-pip-wheel`'s record was erased but its files were not listed for removal; the 1.3 MB wheel under `/usr/share/python-wheels` would ship with its record gone — an inventory that lies. | `rpm -ql python-pip-wheel` in the pack stage; `ls /usr/share/python-wheels` in the shipped image: the wheel was there. | **Fixed.** The pack stage now reads the three packages' file lists out of the runtime's database before the erase; the runtime stage removes every listed file and symlink, then empty directories, fails the build if a listed path survives, and the proof asserts the wheel directory is gone. Rebuilt and re-probed: 5 of 5 paths absent, Syft inventory carries neither pip nor libuuid. |
| 2 | Codex, Cursor | The database directory was copied by merge; a sidecar the base might one day ship would survive beside a database that no longer matches. `.rpm.lock` unaddressed. | `ls /usr/lib/sysimage/rpm` in the pristine runner: `.rpm.lock` and `rpmdb.sqlite` — the lock is the base's own. | **Fixed.** The runtime empties the directory before the copy; the proof asserts the listing is exactly those two files. |
| 3 | Cursor (note) | shm/wal removed without an explicit checkpoint; the erase sticking was evidence, not a contract. | The wal was 0 bytes after `rpm -e` (measured); still, the interpreter now runs `PRAGMA wal_checkpoint(TRUNCATE)` before the removal. | **Fixed.** |
| 4 | Codex, Cursor | The build-time proofs omitted modules the build stage proved (`yaml`, `croniter`, `prometheus_client`), did not observe the removals, and `--version` does not exercise a binary's full library set. | Read the two RUN lines. | **Fixed.** The proof imports every module the build stage does (the test derives the list from the build stage's own line), asserts `_uuid` and `pip` fail to import, checks the removed paths and the database listing, exercises WAL on `/data`; a second proof runs `ld.so --list` on every packed binary and fails on "not found"; the third does real work with jq and base64. |
| 5 | Codex, Cursor | The changelog heading said chart 0.9.5; the chart is 0.10.0. | Read. | **Fixed.** |
| 6 | Codex, Cursor | The design and scan docs described one unconditional erase; the Containerfile had become conditional. | Read. | **Fixed.** Both describe the conditional, per-package erase, the file lists, the checkpoint and the replacement. |
| 7 | Codex, Cursor | The chart README did not disclose curl's exit 77 while the injected ConfigMap is still empty, and said `--cacert` for the manual CA right before documenting the mechanism that makes curl trust it. | Measured earlier: exit 77 on an empty or missing bundle. | **Fixed.** One paragraph says both, and qualifies `--cacert` as the route without `subjectHash`. |
| 8 | Codex, Cursor | `subjectHash` accepted only a bare hash and always mounted `.0`; OpenSSL's `.1` collision suffix is legitimate, and a base entry of the same name would be shadowed. | Read; the base holds ~290 hashed entries. | **Fixed.** The value may carry `.N`; the mount honours it verbatim; `.0` is assumed only when absent; the values comment says when to use it. |
| 9 | Codex, Cursor | The curl chart tests: the "mounted" check was prefix-satisfiable by a parent mount; nothing asserted the injected volume is optional, the ConfigMap carries the label, or the proxy is left alone; one malformed case only. | Read. | **Fixed.** Exact parent mount with volume identity and `optional: true`; label asserted; proxy asserted clean; six malformed hashes parametrised; `.1` honoured. |
| 10 | Cursor | A duplicate curl test class, easy to fix one and leave the other. | `grep class` — two classes. | **Fixed.** The older one removed. |
| 11 | Codex, Cursor | `test_containerfile.py` passed broken recipes: it did not assert the twelve libraries, the erase mechanism, the proof coverage, ordering, or the exact `CMD`. | Read. | **Fixed.** Exact twelve; listing before erase; list copy → removal → database copy ordering; the proof imports derived from the build stage; loader proof present; `CMD` equal to the UBI recipe's. |
| 12 | Codex, Cursor | The `/data` mode in the image does not govern a PVC; the chart sets no `fsGroup`. | Measured on CRC: the mounted `/data` is `root:1000670000`, from OpenShift's assigned group. | **Accepted, documented.** Containerfile comment and design doc say the mode governs `podman run` and emptyDir, and that on the cluster the volume and the SCC decide. No chart change: OpenShift's restricted SCC supplies the group; `fsGroup` would be a non-OpenShift concern the chart already scopes out. |
| 13 | Codex (note), Cursor (note) | Pin `anchore/scan-action` by commit for a security gate. | `gh api` for the `v7` tag: `e1165082…`, release v7.4.2. | **Fixed.** |
| 14 | Codex (should-fix) | Floating tags: pin digests and automate digest-update PRs instead. | — | **Declined, by the operator's decision** to take Red Hat's latest 3.14 on every build. The failure modes both reviewers enumerated are recorded in the design doc; the ones that would be silent (a renamed package, a base that gains a packed library) are covered by the proofs that observe the removals and by the exact-list test. |
| 15 | Codex | Verify `python3-libs`' dependency on `libuuid` is knowingly broken in the shipped database. | — | **Accepted as is.** It is deliberate, `--nodeps`, and now named in the Containerfile and the design doc. |
| 16 | Cursor (note) | `Chart.yaml` had no history comment for 0.10.0. | Read. | **Fixed.** |
| 17 | Cursor (A2 residual) | A future base that gains one of the twelve packed libraries would be silently overwritten by the pack copy. | — | **Accepted.** The exact-list test forces a re-measurement whenever the list moves; a base that gains one of these libraries would be overwritten with the pack stage's build of the same library from the same repository, which is the pack's premise. Recorded in the design doc. |

Confirmed without change: A1 (no `RUN` before the pack), A6 (ENV/LABEL/CMD verbatim), B1
(`SSL_CERT_DIR` is OpenSSL's default; not for the proxy, which takes `-openshift-ca`), C1 (the
action's v7 inputs; no buildx or load step needed), C2 (chart 0.10.0; the 0.11.0 triple agrees).

## What the second build proved

After the fixes: `./release-crc.sh --build-only` passes all three proofs; in the image the five
removed paths are absent, `/data` is empty after the WAL exercise, `/usr/lib/sysimage/rpm` holds
exactly `.rpm.lock` and `rpmdb.sqlite`; Syft lists 57 RPMs and 27 Python packages with neither pip
nor libuuid; Grype (0.118.0) reports 0 CRITICAL, 0 HIGH, 12 Medium, 2 Low, 0 fixable; 186 MB. CI
with the pinned Grype identifies `hummingbird 20251124` and reports 14 matches across 84 packages
on the shipped image and 43 across 96 on the pack stage, and the distribution check passes.
