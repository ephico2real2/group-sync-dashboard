"""The Containerfile's load-bearing shape, held so a well-meant edit cannot undo it silently.

WHY THIS EXISTS. The image moved from ubi9-minimal to the Red Hat Hardened Images
(`hi/python:3.14`) in application 0.11.0, and the runtime base has no shell of any kind. Most of
what makes the recipe work is ORDER: a shell-form `RUN` in the final stage executes only after the
pack stage's `COPY` has put `/bin/sh` there; the directories, the uninstall and the database
replacement depend on that; the proofs must run as the user the container runs as. None of that
is checked by the builder beyond "the step ran", and a reordering that breaks it fails only at
build time in CI — or worse, builds and ships something that no longer proves itself.

WHAT IS HELD, and why each line matters:

* The bases are the hardened images on their FLOATING minor tags (`3.14`, `3.14-builder`) — an
  operator decision: every build takes the latest 3.14 rather than a pinned snapshot.
* The pack copies exactly the twelve libraries the runtime lacks, measured, and every shim the
  final stage's own commands use.
* In the final stage no `RUN` of any form appears before the pack `COPY` — there is nothing to
  run a shell-form one with, and nothing needs an exec-form one there.
* The uninstall: `uninstall-lists.py` runs against the copied database BEFORE the records are
  erased; the final stage consumes its two lists, removes files and only EMPTY directories,
  fails on a survivor, removes the database directory whole, and only then copies the edited
  database in. The order of those lines is the whole guarantee.
* Root is dropped to `USER 65532` before the proofs and `CMD`; the proofs cover every module the
  build stage proved (the two lists are held equal), the removals as observed absences, the
  loader's own resolution of every packed binary, and real work from every pack tool.
* `CMD` is exec form and equal to the UBI recipe's; `Containerfile.ubi` is kept beside it and
  referenced by nothing that builds.

WHAT THIS DOES NOT CHECK: that the image builds, or that the pack is complete, or what the base
contains — those are the build-time proofs in the Containerfile and the scripts it runs, which
fail the build rather than a unit test. This file reads text; it observes no image.
"""

from __future__ import annotations

import pathlib
import re

REPO = pathlib.Path(__file__).resolve().parents[2]
LOCAL = REPO / "local-development"
CONTAINERFILE = LOCAL / "Containerfile"
BACKUP = LOCAL / "Containerfile.ubi"
LISTS = LOCAL / "uninstall-lists.py"
PROOF = LOCAL / "image-proof.py"

RUNNER = "registry.access.redhat.com/hi/python:3.14"
BUILDER = "registry.access.redhat.com/hi/python:3.14-builder"


def _logical_lines(text: str) -> list[str]:
    """Instruction lines with continuations joined, runs of blanks collapsed, comments dropped.

    Collapsing blanks lets the Containerfile align its columns for the reader without the
    assertions here caring; nothing asserted below depends on more than one space anywhere."""
    joined = re.sub(r"\\\n", " ", text)
    return [re.sub(r"[ \t]+", " ", line).strip() for line in joined.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]


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
        assert line == "RUN mkdir -p /data /etc/gsd && chgrp -R 0 /data /etc/gsd && chmod -R g=u /data /etc/gsd"
        assert RUNTIME.index(line) > self._index(lambda l: l.startswith("COPY --from=pack /jqpack/bin/")), (
            "a shell-form RUN needs the pack's sh, which does not exist before that COPY"
        )

    def test_the_uninstall_lists_before_erasing_removes_only_what_is_listed_then_replaces_the_database(self) -> None:
        """Files and records together, in this order: the pack stage runs uninstall-lists.py
        against the copied database BEFORE erasing the records; the final stage consumes the two
        lists, removes the files and only EMPTY listed directories, fails if anything listed
        survives, removes the database directory whole, and only then copies the edited database
        in. Each of those was a real failure once: a hand-written path list left pip's wheel; a
        merge-copy would keep the base's lock file; `rm -rf` on a listed directory took another
        package's file; an unpacked tool with its error hidden removed nothing at all."""
        pack = BY_NAME["pack"]
        assert "COPY --from=runner /usr/lib/sysimage/rpm /rpmdb" in pack
        assert "COPY uninstall-lists.py /uninstall-lists.py" in pack
        erase = next(l for l in pack if l.startswith("RUN python3.14 /uninstall-lists.py"))
        assert erase.index("/uninstall-lists.py") < erase.index("-e --justdb --nodeps"), "list before erase"
        for pkg in ("libuuid", "python3-pip", "python-pip-wheel"):
            assert erase.count(pkg) >= 3, f"{pkg} must be listed, erased and checked"
        assert 'if rpm --dbpath /rpmdb -q "$p" >/dev/null 2>&1; then' in erase, "erase only what is recorded"
        assert "still recorded: $p" in erase
        assert erase.index("wal_checkpoint(TRUNCATE)") < erase.index("rm -f /rpmdb/rpmdb.sqlite-shm")

        removal = self._index(lambda l: l.startswith("RUN --mount=type=bind,from=pack,source=/rpmdb-erased-files"))
        db_copy = self._index(lambda l: l == "COPY --from=pack /rpmdb/ /usr/lib/sysimage/rpm/")
        assert removal < db_copy
        run = RUNTIME[removal]
        assert "--mount=type=bind,from=pack,source=/rpmdb-erased-dirs,target=/rpmdb-erased-dirs" in run
        assert not any(l.startswith("COPY --from=pack /rpmdb-erased") for l in RUNTIME), (
            "the lists must be mounted, not copied: a COPY writes a layer a later rm cannot undo"
        )
        assert "for t in rm rmdir ls; do" in run
        assert "command -v" in run and "not packed" in run, "the tools must be proven present first"
        assert 'rm -f "$f"' in run and "< /rpmdb-erased-files" in run
        assert 'rmdir "$d"' in run and "rm -rf \"$d\"" not in run, "only rmdir: never delete another package's content"
        assert "still present: $f" in run and "empty directory survived: $d" in run
        assert "rm -rf /usr/lib/sysimage/rpm " in run + " ", "the database directory goes whole, not by glob"
        assert "/usr/lib/sysimage/rpm/*" not in run
        assert "2>/dev/null || true" not in run, "nothing in this step may hide an error"
        assert run.count("IFS= read -r") == 4, "every read loop keeps whitespace intact"

    def test_the_list_script_classifies_from_the_database_alone(self) -> None:
        """The load-bearing decisions in uninstall-lists.py, held as text: the owner table's
        format string (the `=` is what makes it work), the refusal of an empty table and of a path
        the table does not know, the mode test that tells a directory from everything else, the
        exclusive-ownership test, and the deepest-first order the runtime's rmdir loop relies on."""
        text = LISTS.read_text()
        for needle in (
            '"[%{=NAME}\\t%{FILENAMES}\\n]"',
            "if not owners:",
            "if path not in owners:",
            "if len(fields) != 11:",
            "int(fields[4], 8)",
            "mode & 0o170000 != 0o040000",
            "owners[path] <= ours",
            "sorted(dirs, reverse=True)",
            'if not recorded(args.dbpath, package):',
        ):
            assert needle in text, needle
        assert 'rpm(args.dbpath, "-q", "--dump", package)' in text

    def test_root_is_dropped_before_the_proofs_and_the_cmd(self) -> None:
        user_lines = [i for i, l in enumerate(RUNTIME) if l.startswith("USER ")]
        assert RUNTIME[user_lines[-1]] == "USER 65532", (
            "the hardened base's own default and the distroless convention; numeric, so "
            "runAsNonRoot can verify it without a passwd entry"
        )
        last_user = user_lines[-1]
        proofs = [i for i, l in enumerate(RUNTIME) if "python3.14 /tmp/image-proof.py" in l or "pack OK" in l or "--list" in l]
        assert len(proofs) == 3 and all(i > last_user for i in proofs)
        cmd = self._index(lambda l: l.startswith("CMD "))
        assert cmd > last_user
        assert "USER 0" in RUNTIME  # root exists only between the pack COPY and USER 65532
        assert RUNTIME.index("USER 0") > self._index(lambda l: l.startswith("COPY --from=pack /jqpack/bin/"))

    def test_the_proofs_cover_what_the_base_change_could_break(self) -> None:
        """The runtime proof script imports every module the build stage proved (parsed from
        both with `ast`, not by eye; the proof may import more, for its own checks), names the
        removals it observes, exercises WAL on /data and cleans up; the loader proof asks ld.so
        itself; the tool proof makes each tool work. This reads the script's text — that the
        named checks are reachable is the build's business, since the build runs it."""
        import ast
        build_proof = next(l for l in BY_NAME["build"] if "python3.14 -c" in l and "import gsd" in l)
        code = re.search(r'python3\.14 -c "(.*)"', build_proof).group(1)
        build_mods = {a.name for n in ast.walk(ast.parse(code)) if isinstance(n, ast.Import) for a in n.names}
        proof_tree = ast.parse(PROOF.read_text())
        proof_mods = {a.name for n in ast.walk(proof_tree) if isinstance(n, ast.Import) for a in n.names}
        assert build_mods <= proof_mods, f"proved by the build stage but not the runtime: {build_mods - proof_mods}"
        # The proof imports MORE than the build stage proves (sqlite3, zoneinfo, uuid, os, sys —
        # its own checks); the guarantee held here is the superset, and the docstring says so.
        text = PROOF.read_text()
        for needle in (
            'must_not_import("_uuid"',              # libuuid removal, observed
            'must_not_import("pip"',                # pip removal, observed
            '"/usr/share/python-wheels"',           # the wheel the first cut left behind
            '[".rpm.lock", "rpmdb.sqlite"]',        # the database directory, exactly
            'pragma journal_mode=wal',              # the store's mode, on /data
            'os.remove(os.path.join("/data", name))',  # nothing of the proof ships
        ):
            assert needle in text, needle
        proof = next(l for l in RUNTIME if "python3.14 /tmp/image-proof.py" in l)
        assert proof.startswith("RUN --mount=type=bind,from=build,source=/image-proof.py,target=/tmp/image-proof.py"), (
            "the proof script must be mounted for its step, never copied into a layer of this image"
        )
        assert not any("COPY" in l and "image-proof.py" in l for l in RUNTIME)
        assert "COPY --chmod=0644 image-proof.py /image-proof.py" in BY_NAME["build"], (
            "staged in the build stage with a mode the runtime user can read"
        )
        loader = next(l for l in RUNTIME if "ld-linux-x86-64.so.2 --list" in l)
        for b in ("jq", "bash", "curl", "coreutils"):
            assert b in loader
        assert "not found" in loader and "2>&1" in loader
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
        dnf = next(l for l in BY_NAME["pack"] if "dnf update -y" in l)
        assert "dnf swap -y libcurl libcurl-minimal" in dnf
        assert "dnf install -y jq" in dnf
        assert "dnf clean all" in dnf
        tools = next(l for l in BY_NAME["pack"] if "/jqpack/bin/" in l and "cp " in l)
        assert "ln -s bash /jqpack/bin/sh" in tools, "sh must resolve to bash"
        assert "cp -L /usr/bin/jq /usr/bin/bash /usr/bin/curl /usr/bin/coreutils /jqpack/bin/" in tools

    # Words that may appear in command position in the final stage's RUN lines without being a
    # program the pack must ship: shell keywords and builtins (bash provides them), the
    # interpreter the base provides, and variable assignments.
    SHELL_WORDS = {
        "for", "do", "done", "if", "then", "else", "fi", "while", "case", "esac", "in",
        "command", "test", "echo", "exit", "printf", "read", "python3.14",
    }

    def test_every_program_the_final_stage_runs_is_packed(self) -> None:
        """Derived from the RUN lines, not from a hand-kept list: every word in command position
        — at the start, or after &&, ||, ;, |, {, then, do, else, or $( — must be a shell word, the
        interpreter, an assignment, or a program the pack copies. A tool the final stage names
        but the pack does not ship fails with "command not found", and the history of this file
        is that such a failure was hidden twice."""
        run = next(l for l in BY_NAME["pack"] if "/jqpack/bin/" in l and "cp " in l)
        packed = set(re.findall(r"/usr/bin/([\w-]+)", run)) | {"sh"}      # sh is the symlink
        pattern = re.compile(r"(?:^|&&|\|\||;|\||\{|\bthen\b|\bdo\b|\belse\b|\$\()\s*(?:!\s*)?([A-Za-z0-9_./-]+=?)")
        seen: set[str] = set()
        for line in RUNTIME:
            if not line.startswith("RUN"):
                continue
            body = re.sub(r"^RUN(?:\s+--mount=\S+)*\s+", "", line)
            for word in pattern.findall(body):
                if word.endswith("=") or word.startswith("/lib64/ld-linux"):
                    continue                 # an assignment; the loader is the base's
                seen.add(word)
        programs = seen - self.SHELL_WORDS
        assert programs, "no programs parsed from the final stage; the parser is broken"
        assert programs <= packed, f"named by the final stage, not packed: {sorted(programs - packed)}"

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
