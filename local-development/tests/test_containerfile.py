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
* In the runtime stage, no shell-form `RUN` appears before the pack `COPY` — there is nothing to
  run it with.
* The runtime creates its writable directories with the UBI recipe's own line (mkdir/chgrp/chmod),
  uninstalls libuuid and pip (files here, records in the pack stage), and drops to `USER 1001`
  before the proofs and before `CMD`.
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

    def test_no_shell_form_run_before_the_pack_lands(self) -> None:
        pack_copy = self._index(lambda l: l.startswith("COPY --from=pack /jqpack/bin/"))
        for line in RUNTIME[:pack_copy]:
            assert not line.startswith("RUN "), f"shell-form RUN before /bin/sh exists: {line}"

    def test_the_pack_copies_both_binaries_and_libraries(self) -> None:
        assert "COPY --from=pack /jqpack/bin/ /usr/bin/" in RUNTIME
        assert "COPY --from=pack /jqpack/lib64/ /usr/lib64/" in RUNTIME

    def test_directories_are_made_the_way_the_ubi_recipe_made_them(self) -> None:
        line = next(l for l in RUNTIME if "mkdir -p /data /etc/gsd" in l)
        assert "chgrp -R 0 /data /etc/gsd" in line
        assert "chmod -R g=u /data /etc/gsd" in line
        assert line.startswith('RUN ["/bin/sh", "-c",'), "must be exec form through the pack's shell"

    def test_libuuid_and_pip_are_uninstalled_files_and_records(self) -> None:
        removal = next(l for l in RUNTIME if "rm -rf /usr/lib/python3.14/site-packages/pip" in l)
        assert "/usr/lib64/libuuid.so.1" in removal
        assert "COPY --from=pack /rpmdb/ /usr/lib/sysimage/rpm/" in RUNTIME
        erase = next(l for l in BY_NAME["pack"] if "-e --justdb --nodeps" in l)
        for pkg in ("libuuid", "python3-pip", "python-pip-wheel"):
            assert pkg in erase
        assert "COPY --from=runner /usr/lib/sysimage/rpm /rpmdb" in BY_NAME["pack"]

    def test_root_is_dropped_before_the_proofs_and_the_cmd(self) -> None:
        user_lines = [i for i, l in enumerate(RUNTIME) if l.startswith("USER ")]
        assert RUNTIME[user_lines[-1]] == "USER 1001"
        last_user = user_lines[-1]
        proofs = [i for i, l in enumerate(RUNTIME) if l.startswith('RUN ["python3.14"') or "pack OK" in l]
        assert len(proofs) == 2 and all(i > last_user for i in proofs)
        cmd = self._index(lambda l: l.startswith("CMD "))
        assert cmd > last_user
        assert "USER 0" in RUNTIME  # root exists only between the pack COPY and USER 1001
        assert RUNTIME.index("USER 0") > self._index(lambda l: l.startswith("COPY --from=pack /jqpack/bin/"))

    def test_the_proofs_cover_what_the_base_change_could_break(self) -> None:
        py = next(l for l in RUNTIME if l.startswith('RUN ["python3.14"'))
        for name in ("import gsd", "sqlite3", "zoneinfo", "uuid.uuid4()"):
            assert name in py
        sh = next(l for l in RUNTIME if "pack OK" in l)
        for tool in ("curl --version", "jq --version", "ls /", "cat /etc/os-release", "base64 --version"):
            assert tool in sh

    def test_cmd_is_exec_form_and_unchanged(self) -> None:
        cmd = next(l for l in RUNTIME if l.startswith("CMD "))
        assert cmd.startswith("CMD [")
        for part in ('"python3.14"', '"-m"', '"uvicorn"', '"gsd.api:create_app"', '"--factory"', '"--workers", "1"'):
            assert part in cmd

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

    def test_libraries_the_runner_already_has_are_not_overwritten(self) -> None:
        """libtinfo and libsystemd are in the runner base; packing them would replace its files."""
        run = next(l for l in BY_NAME["pack"] if "libjq.so.1" in l)
        assert "libtinfo" not in run
        assert "libsystemd" not in run


class TestBackup:
    def test_the_ubi_recipe_is_kept_and_built_by_nothing(self) -> None:
        assert BACKUP.is_file()
        assert "ubi9-minimal" in BACKUP.read_text()
        for path in [*LOCAL.glob("*.sh"), *(REPO / ".github" / "workflows").glob("*.yml")]:
            assert "Containerfile.ubi" not in path.read_text(), f"{path.name} references the backup"
