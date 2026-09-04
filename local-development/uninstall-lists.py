#!/usr/bin/python3.14
"""Which paths to remove from the runtime image for the packages its RPM database will no longer
record — written by the pack stage of the Containerfile, consumed by its runtime stage.

WHY A SCRIPT, AND WHY FROM THE DATABASE. The runtime base has an RPM database and no rpm binary,
so the pack stage edits a COPY of that database and the runtime stage removes the packages'
files. Files and records must move together, or the inventory lies in one of two directions: a
record erased with its files left (the first cut of this recipe shipped pip's 1.3 MB wheel that
way), or a file removed with its record left. Both answers — which paths, and which of them are
directories nothing else owns — come from the database alone. The pack stage's OWN filesystem is
the wrong witness: it holds a different build of the same packages (its libuuid's build-id
directory is not the runtime's), so `test -d` there classified a runtime directory as a file, and
`rpm -qf` there could not answer for a path it did not have. `rpm --dump` records every path's
mode; the owner table (`rpm -qa --qf '[%{=NAME}\\t%{FILENAMES}\\n]'`) records every path's owners.

Two lists come out:

* files — every non-directory path the packages owned (regular files, symlinks, %ghost, %config);
* dirs  — every directory no OTHER package owns, deepest first. A directory another package also
  owns (/usr/lib/.build-id, the bash-completion directory) is never listed and stays, even empty,
  so the packages still recorded as owning it stay true.

Anything unexpected — a --dump line that does not parse, a package that is recorded but yields
no paths — is an exit code, not a shorter list.
"""

from __future__ import annotations

import argparse
import subprocess
import sys


def rpm(dbpath: str, *args: str) -> str:
    return subprocess.run(["rpm", "--dbpath", dbpath, *args], capture_output=True, text=True, check=True).stdout


def recorded(dbpath: str, package: str) -> bool:
    return subprocess.run(["rpm", "--dbpath", dbpath, "-q", package], capture_output=True).returncode == 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dbpath", required=True)
    ap.add_argument("--files", required=True, help="output: non-directory paths, one per line")
    ap.add_argument("--dirs", required=True, help="output: exclusively owned directories, deepest first")
    ap.add_argument("packages", nargs="+")
    args = ap.parse_args()

    # `=` makes the scalar NAME repeat beside every element of the FILENAMES array; without it rpm
    # reports "array iterator used with different sized arrays" for every package and prints
    # nothing — an empty table that would make every directory look exclusive, so it is refused.
    owners: dict[str, set[str]] = {}
    for line in rpm(args.dbpath, "-qa", "--qf", "[%{=NAME}\t%{FILENAMES}\n]").splitlines():
        name, _, path = line.partition("\t")
        owners.setdefault(path, set()).add(name)
    if not owners:
        sys.exit("the owner table came back empty; the query is wrong or the database is")

    ours = set(args.packages)
    files: set[str] = set()
    dirs: set[str] = set()
    for package in args.packages:
        if not recorded(args.dbpath, package):
            print(f"{package}: not in the base, nothing to list")
            continue
        dump = rpm(args.dbpath, "-q", "--dump", package).splitlines()
        if not dump:
            sys.exit(f"{package} is recorded but --dump listed nothing")
        if package not in {o for owners_of in owners.values() for o in owners_of}:
            sys.exit(f"{package} is recorded but owns nothing in the owner table")
        for line in dump:
            fields = line.split()
            if len(fields) != 11:
                sys.exit(f"unexpected --dump line for {package}: {line!r}")
            path, mode = fields[0], int(fields[4], 8)
            if mode & 0o170000 != 0o040000:
                files.add(path)
            elif owners.get(path, set()) <= ours:
                dirs.add(path)
            # else: a directory another package owns — stays

    with open(args.files, "w") as out:
        out.writelines(p + "\n" for p in sorted(files))
    with open(args.dirs, "w") as out:
        out.writelines(p + "\n" for p in sorted(dirs, reverse=True))
    print(f"uninstall lists: {len(files)} files, {len(dirs)} directories owned by nothing else")
    return 0


if __name__ == "__main__":
    sys.exit(main())
