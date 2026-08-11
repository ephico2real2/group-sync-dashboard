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

So the list is held against the Containerfile's own `COPY` lines. Adding an input to the image
without extending the filter fails here, at the point the input is added.

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
    """Every host path the Containerfile copies into the image.

    `COPY --from=build …` is excluded: it copies from an earlier STAGE, not from the repository,
    so it is not an input a push could change.
    """
    sources: list[str] = []
    for line in CONTAINERFILE.read_text().splitlines():
        stripped = line.strip()
        if not stripped.upper().startswith("COPY "):
            continue
        if "--from=" in stripped:
            continue
        parts = stripped.split()[1:]
        sources.extend(parts[:-1])          # the last token is the destination
    assert sources, "no COPY lines parsed; the Containerfile format has changed"
    return sources


def _covers(pattern: str, path: str) -> bool:
    """Does one `paths` entry match this repo-relative path?

    Only the two forms this workflow uses: an exact file, or a directory glob ending `/**`.
    Deliberately not a general fnmatch — a filter that needs cleverer globs than these should be
    read by a human, not matched by a helper that quietly says yes.
    """
    if pattern.endswith("/**"):
        return path == pattern[:-3] or path.startswith(pattern[:-3] + "/")
    return pattern == path


def test_every_image_input_is_in_the_paths_filter() -> None:
    """The defect this file exists for: an input added to the image but not to the filter."""
    paths = _publish_paths()
    missing = []
    for source in _copied_sources():
        target = f"{CONTEXT}/{source}"
        if not any(_covers(p, target) for p in paths):
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
    assert any(_covers(p, "local-development/README.md") for p in _publish_paths()), (
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
        assert any(_covers(p, required) for p in paths), f"{required} is not in publish.yml's paths"


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
