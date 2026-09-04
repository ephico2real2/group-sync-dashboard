"""The publish workflow's `paths` filter must cover everything that goes into the image.

WHY THIS EXISTS. `publish.yml` used to run on every push to main, so a documentation-only merge
built an image, pushed it to the registry and committed a `pin image tag` on main. Measured over
five consecutive merges, two were documentation-only and each did all three. It now has a `paths`
allowlist.

WHY THE ALLOWLIST NEEDS A TEST, and this is the whole point: its failure mode is silent and
inverted. Forget to list a new input and nothing goes red — the workflow simply stops firing, the
last-published image keeps being the pinned one, and main's chart deploys code that no longer
matches the source. A green run every time. The only way to notice by hand is to wonder why a
change never reached the cluster.

So the list is held against the Containerfile's own `COPY` and `ADD` lines, plus the two inputs it
does not name — `.containerignore`, which the builder finds by convention at the context root, and
`build-and-push-external.sh`, which decides the tag and the build args. Adding an input to the image
without extending the filter fails here, at the point the input is added.

WHAT THIS STILL DOES NOT COVER, so the docstring does not overclaim: an input reached some way other
than a `COPY`/`ADD` source, a `RUN --mount=type=bind` of a context file, or those two named files —
a `RUN` that reads the context directly, a base image whose floating tag moves underneath us. The
floating base image is deliberately out of band; `workflow_dispatch` is how a rebuild is forced for
that.

THE TRAP THIS ALSO GUARDS. `COPY pyproject.toml README.md ./` puts `local-development/README.md`
inside the image, so the tempting `paths-ignore: ['**/*.md']` would skip a rebuild that is
genuinely needed. A markdown file being image content is exactly the sort of thing a filter
written from intuition gets wrong.
"""

from __future__ import annotations

import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
WORKFLOW = REPO / ".github" / "workflows" / "publish.yml"
CONTAINERFILE = REPO / "local-development" / "Containerfile"

#: The Containerfile's build context, as the build script invokes it: `podman build … .` from
#: local-development/. So a COPY source is relative to that directory.
CONTEXT = "local-development"


def _publish_paths() -> list[str]:
    workflow = yaml.safe_load(WORKFLOW.read_text())
    # `on` is the YAML 1.1 boolean `True` after parsing — the classic GitHub-Actions gotcha, and
    # the reason this reads the key defensively rather than assuming either spelling.
    triggers = workflow.get("on") or workflow.get(True)
    assert triggers, f"no trigger block found in {WORKFLOW}"
    return list(triggers["push"]["paths"])


def _copied_sources() -> list[str]:
    """Every host path the Containerfile brings into the image.

    `ADD` counts as well as `COPY`, and that is not hypothetical tidiness: the first version of
    this helper matched `COPY ` alone, so switching a line to `ADD` would have removed an input
    from this test's view while leaving it in the image.

    `COPY --from=build …` is excluded: it copies from an earlier STAGE, not from the repository,
    so it is not an input a push could change.
    """
    sources: list[str] = []
    text = re.sub(r"\\\n", " ", CONTAINERFILE.read_text())   # join continued lines first
    for line in text.splitlines():
        stripped = line.strip()
        verb = stripped.split(" ", 1)[0].upper() if " " in stripped else ""
        if verb in {"COPY", "ADD"} and "--from=" not in stripped:
            parts = [p for p in stripped.split()[1:] if not p.startswith("--")]
            sources.extend(parts[:-1])      # the last token is the destination
        # A bind mount of a context file into a RUN step is an input too — the one way in that
        # the first version of this helper could not see (its docstring said so). A mount with
        # `from=` lends a file from another STAGE and is not a repository input.
        if verb == "RUN":
            for mount in re.findall(r"--mount=(\S+)", stripped):
                opts = dict(kv.split("=", 1) for kv in mount.split(",") if "=" in kv)
                if opts.get("type") == "bind" and "from" not in opts and "source" in opts:
                    sources.append(opts["source"])
    assert sources, "no COPY/ADD lines parsed; the Containerfile format has changed"
    return sources


def _covers(pattern: str, path: str, *, is_dir: bool) -> bool:
    """Does one `paths` entry match this repo-relative path, the way GitHub would?

    A DIRECTORY SOURCE NEEDS A RECURSIVE PATTERN, and getting this wrong is how the check passes
    while the filter never fires. `paths: ['local-development/gsd']` matches a FILE at exactly
    that path; it does NOT match `local-development/gsd/api.py`. The first version of this helper
    compared `pattern == path` for every source, so an exact directory entry satisfied the test
    and the workflow would then have ignored every edit inside that directory — the silent skip
    this whole file exists to prevent, waved through by the thing meant to catch it.

    Only the two forms this workflow uses: an exact file, or a directory glob ending `/**`.
    Deliberately not a general fnmatch — a filter needing cleverer globs than these should be read
    by a human, not matched by a helper that quietly says yes.
    """
    if is_dir:
        return pattern.endswith("/**") and (
            path == pattern[:-3] or path.startswith(pattern[:-3] + "/")
        )
    if pattern.endswith("/**"):
        return path == pattern[:-3] or path.startswith(pattern[:-3] + "/")
    return pattern == path


def _matches(paths: list[str], target: str) -> bool:
    """Is this repo-relative path covered, judging directory-ness from the filesystem?"""
    is_dir = (REPO / target).is_dir()
    return any(_covers(p, target, is_dir=is_dir) for p in paths)


def test_every_image_input_is_in_the_paths_filter() -> None:
    """The defect this file exists for: an input added to the image but not to the filter."""
    paths = _publish_paths()
    missing = []
    for source in _copied_sources():
        target = f"{CONTEXT}/{source}"
        if not _matches(paths, target):
            missing.append(f"{source} (as {target})")
    assert not missing, (
        "these Containerfile COPY sources are not covered by publish.yml's `paths`, so changing "
        "them would NOT rebuild the image — and nothing would report it:\n  "
        + "\n  ".join(missing)
        + "\n\nfilter is:\n  " + "\n  ".join(paths)
    )


def test_the_readme_is_covered_because_it_is_image_content() -> None:
    """Named explicitly, because `paths-ignore: ['**/*.md']` is the tempting wrong answer.

    `COPY pyproject.toml README.md ./` puts it in the image. A filter that treats markdown as
    documentation would stop rebuilding when it changes.
    """
    assert "README.md" in _copied_sources(), (
        "the Containerfile no longer copies README.md; if that is deliberate, drop it from "
        "publish.yml's paths too and delete this test"
    )
    assert _matches(_publish_paths(), "local-development/README.md"), (
        "local-development/README.md is inside the image but is not in publish.yml's paths"
    )


def test_the_recipe_and_the_build_script_are_covered() -> None:
    """Neither is COPY'd, and both change the image.

    The Containerfile is the recipe. build-and-push-external.sh decides the tag scheme, passes the
    GIT_COMMIT/GIT_BRANCH/BUILD_VERSION build args that become `gsd_build_info`, and performs the
    stamp verification — so editing it changes what gets published even with no other change.
    """
    paths = _publish_paths()
    for required in (
        "local-development/Containerfile",
        "local-development/build-and-push-external.sh",
    ):
        assert _matches(paths, required), f"{required} is not in publish.yml's paths"


def test_a_manual_run_is_still_possible() -> None:
    """The escape hatch the filter makes necessary.

    A rebuild is occasionally wanted for a reason the paths cannot see — a base-image CVE, a
    registry that lost a tag. Without `workflow_dispatch` the only way to force one would be an
    empty commit touching a listed path, which is a worse thing to have to invent under pressure.
    """
    workflow = yaml.safe_load(WORKFLOW.read_text())
    triggers = workflow.get("on") or workflow.get(True)
    assert "workflow_dispatch" in triggers, (
        "publish.yml has a paths filter but no workflow_dispatch, so a needed rebuild cannot be "
        "triggered by hand"
    )


def test_the_containerignore_is_in_the_paths_filter() -> None:
    """It is an image input, and it was missing from the first version of this filter.

    Podman applies `.containerignore` to the build context BEFORE any COPY runs, so editing it
    changes what lands in the image with no change to any other listed path. Verified rather than
    argued: a probe build of `COPY pkg /pkg` shipped both files, and the same build with
    `pkg/drop.txt` in `.containerignore` shipped only one.

    It currently excludes `tests/`, `docs/`, `*.db` and the local cluster config, so an edit there
    can add or remove whole trees from the image while the workflow stays silent.

    Not derived from the Containerfile like the COPY sources, because it is not named there — the
    builder finds it by convention at the context root. So it is asserted by name.
    """
    ignore = REPO / CONTEXT / ".containerignore"
    if not ignore.exists():
        # Listing a path that does not exist is harmless, and it is what makes CREATING the file
        # trigger a build. So the assertion below stands either way; this only skips the
        # existence half.
        pass
    assert _matches(_publish_paths(), f"{CONTEXT}/.containerignore"), (
        "local-development/.containerignore decides what every COPY may see, so editing it changes "
        "the image — but it is not in publish.yml's paths, so such an edit would not rebuild"
    )


def test_a_directory_source_is_matched_recursively_or_not_at_all() -> None:
    """The helper must judge patterns the way GitHub does, or it waves the bug through.

    `paths: ['local-development/gsd']` matches a FILE at that exact path and does NOT match
    `local-development/gsd/api.py`. An earlier version of `_covers` compared `pattern == path` for
    every source, so an exact directory entry passed the check while the workflow ignored every
    edit inside that directory.
    """
    assert _covers("local-development/gsd/**", "local-development/gsd", is_dir=True)
    assert not _covers("local-development/gsd", "local-development/gsd", is_dir=True), (
        "a non-recursive pattern was accepted for a directory source; GitHub would not fire on "
        "files inside it, so the filter would silently stop rebuilding"
    )
    # A file source is the other way round: exact is correct and sufficient.
    assert _covers("local-development/pyproject.toml", "local-development/pyproject.toml",
                   is_dir=False)
