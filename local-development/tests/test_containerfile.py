"""The Containerfile's load-bearing shape, held so a well-meant edit cannot undo it silently.

WHY THIS EXISTS. The image moved from ubi9-minimal to the Red Hat Hardened Images
(`hi/python:3.14`) in application 0.11.0, and the runtime base has no shell of any kind. Most of
what makes the recipe work is ORDER: a shell-form `RUN` in the runtime stage executes only after the
pack stage's `COPY` has put `/bin/sh` there; the directories and the two package removals depend on
that; the proofs must run as the user the container runs as. None of that is checked by the builder
beyond "the step ran", and a reordering that breaks it fails only at build time in CI — or worse,
builds and ships something that no longer proves itself.

WHAT IS HELD, and why each line matters:

* The three bases are the hardened images on their FLOATING minor tags (`3.14`, `3.14-builder`),
  which is an operator decision: every build takes the latest 3.14 rather than a pinned snapshot.
* In the runtime stage, no `RUN` of any form appears before the pack `COPY` — there is nothing to
  run a shell-form one with, and nothing needs an exec-form one there.
* The pack copies exactly the twelve libraries the runtime lacks, measured, and no other.
* The runtime creates its writable directories with the UBI recipe's own line (mkdir/chgrp/chmod),
  uninstalls libuuid and pip from the database's own file list (files here, records in the pack
  stage, database replaced not merged), and drops to `USER 1001` before the proofs and `CMD`.
* The proofs cover every module the build stage proved, the two removals as observed absences,
  the loader's own resolution of every packed binary, and real work from every pack tool.
* `CMD` is exec form (uvicorn is PID 1, so SIGTERM reaches it) and unchanged in substance.
* `Containerfile.ubi` is kept beside it for reference and is built by nothing in the repository.

WHAT THIS DOES NOT CHECK: that the image builds, or that the pack is complete — those are the
build-time proofs in the Containerfile itself (`RUN ["/bin/sh", "-c", "curl --version ..."]`),
which fail the build rather than a unit test.
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
LOCAL = REPO / "local-development"
CONTAINERFILE = LOCAL / "Containerfile"
BACKUP = LOCAL / "Containerfile.ubi"

RUNNER = "registry.access.redhat.com/hi/python:3.14"
BUILDER = "registry.access.redhat.com/hi/python:3.14-builder"


def _logical_lines(text: str) -> list[str]:
    """Instruction lines with continuations joined and comments dropped."""
    joined = re.sub(r"\\\n", " ", text)
    return [line.strip() for line in joined.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def _stages(lines: list[str]) -> list[tuple[str, list[str]]]:
    """(FROM line, instructions) per stage, in order."""
    stages: list[tuple[str, list[str]]] = []
    for line in lines:
        if line.startswith("FROM "):
            stages.append((line, []))
        elif stages:
            stages[-1][1].append(line)
    return stages


LINES = _logical_lines(CONTAINERFILE.read_text())
STAGES = _stages(LINES)
BY_NAME = {re.search(r"\bAS\s+(\S+)", f).group(1): body for f, body in STAGES if " AS " in f}
RUNTIME = STAGES[-1][1]


class TestBases:
    def test_the_bases_are_the_hardened_images_on_floating_minor_tags(self) -> None:
        froms = [f for f, _ in STAGES]
        assert froms == [
            f"FROM {BUILDER} AS build",
            f"FROM {RUNNER} AS runner",
            f"FROM {BUILDER} AS pack",
            "FROM runner",
        ]

    def test_no_digest_or_patch_pin_on_a_base(self) -> None:
        """A `3.14.7` or `@sha256:` pin would quietly stop the image tracking Red Hat's fixes."""
        for f, _ in STAGES:
            assert "@sha256" not in f
            assert not re.search(r":3\.14\.\d", f)


class TestRuntimeStageOrder:
    def _index(self, predicate) -> int:
        for i, line in enumerate(RUNTIME):
            if predicate(line):
                return i
        raise AssertionError(f"no runtime line matches {predicate.__name__}")

    def test_no_run_of_any_form_before_the_pack_lands(self) -> None:
        """Stricter than "no shell-form RUN": an exec-form RUN of python3.14 would work before
        the pack, but nothing in the recipe needs one there, and forbidding all of them keeps the
        rule simple enough to hold."""
        pack_copy = self._index(lambda l: l.startswith("COPY --from=pack /jqpack/bin/"))
        for line in RUNTIME[:pack_copy]:
            assert not line.startswith("RUN"), f"RUN before the pack lands: {line}"

    def test_the_pack_copies_both_binaries_and_libraries(self) -> None:
        assert "COPY --from=pack /jqpack/bin/ /usr/bin/" in RUNTIME
        assert "COPY --from=pack /jqpack/lib64/ /usr/lib64/" in RUNTIME

    def test_directories_are_made_the_way_the_ubi_recipe_made_them(self) -> None:
        line = next(l for l in RUNTIME if "mkdir -p /data /etc/gsd" in l)
        assert "chgrp -R 0 /data /etc/gsd" in line
        assert "chmod -R g=u /data /etc/gsd" in line
        assert line.startswith('RUN ["/bin/sh", "-c",'), "must be exec form through the pack's shell"

    def test_the_uninstall_removes_the_files_the_database_listed_then_replaces_the_database(self) -> None:
        """Files and records together, in this order: the pack stage lists the packages' paths
        out of the database BEFORE erasing them; the runtime stage consumes that list, removes
        the paths, fails if one survives, empties the database directory, and only then copies
        the edited database in. A merge-copy or a hand-written path list is what the review
        caught (a 1.3 MB pip wheel left on disk with its record gone)."""
        pack = BY_NAME["pack"]
        listing = next(l for l in pack if "-ql" in l and "/rpmdb-erased-paths" in l)
        erase = listing  # same logical RUN: the listing precedes the erase inside it
        assert listing.index("-ql") < erase.index("-e --justdb --nodeps")
        for pkg in ("libuuid", "python3-pip", "python-pip-wheel"):
            assert pkg in listing
        assert "wal_checkpoint(TRUNCATE)" in erase
        assert erase.index("wal_checkpoint") < erase.index("rm -f /rpmdb/rpmdb.sqlite-shm")
        assert "COPY --from=runner /usr/lib/sysimage/rpm /rpmdb" in pack

        list_copy = self._index(lambda l: l == "COPY --from=pack /rpmdb-erased-paths /rpmdb-erased-paths-deepest-first /")
        removal = self._index(lambda l: l.startswith('RUN ["/bin/sh", "-c", "set -e; while read -r f;'))
        db_copy = self._index(lambda l: l == "COPY --from=pack /rpmdb/ /usr/lib/sysimage/rpm/")
        assert list_copy < removal < db_copy
        run = RUNTIME[removal]
        assert 'echo \\"still present: $f\\"' in run and "exit 1" in run
        assert "rm -rf /rpmdb-erased-paths" in run
        assert "/usr/share/python-wheels" in run
        assert "/usr/lib/sysimage/rpm/*" in run, "the database directory must be emptied, not merged into"
        assert "sort" not in run, "sort is not among the packed tools; the deepest-first order comes from the pack stage"
        assert "sort -ur /rpmdb-erased-paths > /rpmdb-erased-paths-deepest-first" in listing
        assert run.startswith('RUN ["/bin/sh", "-c", "set -e;'), "an error inside the loops must fail the build"

    def test_root_is_dropped_before_the_proofs_and_the_cmd(self) -> None:
        user_lines = [i for i, l in enumerate(RUNTIME) if l.startswith("USER ")]
        assert RUNTIME[user_lines[-1]] == "USER 1001"
        last_user = user_lines[-1]
        proofs = [i for i, l in enumerate(RUNTIME) if l.startswith('RUN ["python3.14"') or "pack OK" in l or "--list" in l]
        assert len(proofs) == 3 and all(i > last_user for i in proofs)
        cmd = self._index(lambda l: l.startswith("CMD "))
        assert cmd > last_user
        assert "USER 0" in RUNTIME  # root exists only between the pack COPY and USER 1001
        assert RUNTIME.index("USER 0") > self._index(lambda l: l.startswith("COPY --from=pack /jqpack/bin/"))

    def test_the_proofs_cover_what_the_base_change_could_break(self) -> None:
        py = next(l for l in RUNTIME if l.startswith('RUN ["python3.14"'))
        build_proof = next(l for l in BY_NAME["build"] if "python3.14 -c" in l and "import gsd" in l)
        build_imports = re.search(r"import (gsd[\w, ]+?);", build_proof).group(1).replace(" ", "").split(",")
        for mod in build_imports:
            assert re.search(rf"\b{mod}\b", py), f"the build stage proves {mod} imports; the runtime proof must too"
        for needle in (
            "zoneinfo.ZoneInfo('America/New_York')",
            "uuid.uuid4()",
            "import _uuid; raise SystemExit",           # libuuid removal, observed
            "import pip; raise SystemExit",             # pip removal, observed
            "/usr/share/python-wheels",                 # the wheel the first cut left behind
            "['.rpm.lock', 'rpmdb.sqlite']",            # the database directory, exactly
            "pragma journal_mode=wal",                  # the store's mode, on /data
        ):
            assert needle in py, needle
        loader = next(l for l in RUNTIME if "ld-linux-x86-64.so.2 --list" in l)
        for b in ("jq", "bash", "curl", "coreutils"):
            assert b in loader
        assert "not found" in loader
        sh = next(l for l in RUNTIME if "pack OK" in l)
        for work in ("jq -r '.a[1]'", "base64 -d", "curl --version", "ls /", "cat /etc/os-release"):
            assert work in sh, work

    def test_cmd_is_exec_form_and_unchanged(self) -> None:
        """Exact equality with the UBI recipe's CMD, whitespace aside — a changed flag or an
        extra argument is a behaviour change nothing else would notice."""
        cmd = next(l for l in RUNTIME if l.startswith("CMD "))
        assert cmd.startswith("CMD [")
        ubi_cmd = next(l for l in _logical_lines(BACKUP.read_text()) if l.startswith("CMD "))
        assert re.sub(r"\s+", " ", cmd) == re.sub(r"\s+", " ", ubi_cmd)

    def test_no_healthcheck(self) -> None:
        """OCI builds discard it and kubelet never reads it; the chart's probes are the health check."""
        assert not any(l.startswith("HEALTHCHECK") for l in LINES)


class TestPackStage:
    def test_the_pack_installs_with_dnf_update_and_libcurl_minimal(self) -> None:
        run = next(l for l in BY_NAME["pack"] if "dnf update -y" in l)
        assert "dnf swap -y libcurl libcurl-minimal" in run
        assert "dnf install -y jq" in run
        assert "ln -s bash /jqpack/bin/sh" in run

    def test_the_shims_the_runtime_stage_relies_on_are_packed(self) -> None:
        run = next(l for l in BY_NAME["pack"] if "/jqpack/bin/" in l and "cp " in l)
        for tool in ("cat", "ls", "base64", "mkdir", "chgrp", "chmod", "rm"):
            assert f"/usr/bin/{tool} " in run or f"/usr/bin/{tool}\t" in run, f"{tool} shim not packed"

    PACKED = {
        "libjq.so.1", "libonig.so.5", "libcurl.so.4", "libnghttp2.so.14", "libidn2.so.0",
        "libunistring.so.5", "libgssapi_krb5.so.2", "libkrb5.so.3", "libk5crypto.so.3",
        "libcom_err.so.2", "libkrb5support.so.0", "libkeyutils.so.1",
    }

    def test_exactly_the_twelve_libraries_the_runtime_lacks_are_packed(self) -> None:
        """Measured on 2026-09-04: ldd of jq/bash/curl/coreutils names 26 shared objects, of
        which the runtime base lacks these twelve and no other. One more would overwrite a file of
        the base's (libtinfo, libsystemd); one fewer is a loader error the build-time proof turns
        into a failed build. If the base or the pack's dependency closure moves, this list moves
        with a new measurement, not by intuition."""
        run = next(l for l in BY_NAME["pack"] if "libjq.so.1" in l)
        packed = set(re.findall(r"/usr/lib64/(lib[\w.+-]+\.so\.\d+)", run))
        assert packed == self.PACKED, packed ^ self.PACKED


class TestBackup:
    def test_the_ubi_recipe_is_kept_and_built_by_nothing(self) -> None:
        assert BACKUP.is_file()
        assert "ubi9-minimal" in BACKUP.read_text()
        for path in [*LOCAL.glob("*.sh"), *(REPO / ".github" / "workflows").glob("*.yml")]:
            assert "Containerfile.ubi" not in path.read_text(), f"{path.name} references the backup"
