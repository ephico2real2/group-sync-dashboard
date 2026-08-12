"""The table in `environments/README.md` must still describe the real files.

WHY A TEST FOR A TABLE. It documents chart defaults next to what `crc.yaml` overrides, and that is
the shape of documentation that rots without anyone noticing: every value in it is plausible
forever. `config.unmanagedAudit.mode` has already moved once — the chart default became `log`, which
turned a `crc.yaml` override into a redundant line — and the only reason the table says so is that
somebody checked by hand on 2026-08-12. Nothing would have caught the next such move.

The failure mode is worse than a stale number. A reader consults this table to answer "will a plain
`helm install` enable login capture?", and the answer is a security property. A table that says
`false` while the chart ships `true` is not vague, it is wrong in the direction that matters.

So this reads BOTH SIDES from their real sources — the defaults out of the chart's `values.yaml`, the
overrides out of `environments/crc.yaml`, and the claims out of the README's own markdown — and
compares them. It also holds the table's HEADLINE claim, that `crc.yaml` introduces no key the chart
does not declare, because that sentence is the reason the table is only five rows long.
"""

from __future__ import annotations

import pathlib
import re

import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
README = REPO / "environments" / "README.md"
VALUES = REPO / "charts" / "group-sync-dashboard" / "values.yaml"
CRC = REPO / "environments" / "crc.yaml"


def flatten(data: dict, prefix: str = "") -> dict:
    """Dotted-path leaves, the way the README writes its keys."""
    out: dict = {}
    for key, value in (data or {}).items():
        if isinstance(value, dict):
            out.update(flatten(value, f"{prefix}{key}."))
        else:
            out[f"{prefix}{key}"] = value
    return out


def as_written(value: object) -> str:
    """Render a YAML value the way the README's backticks show it."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def table_rows() -> list[tuple[str, str, str]]:
    """(key, claimed default, claimed crc value) for every row of the README's table.

    Parses the real markdown rather than restating it. One row deliberately pairs two keys —
    `authLogLevel.manage` / `.enabled` — because they are one decision to a reader; the shorthand
    second half is expanded back to a full path here so the comparison stays mechanical.
    """
    rows: list[tuple[str, str, str]] = []
    for line in README.read_text().splitlines():
        if not line.startswith("| `"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 4:
            continue
        keys = [k.strip().strip("`") for k in cells[0].split("/")]
        defaults = [d.strip().strip("`") for d in cells[1].split("/")]
        actuals = [a.strip().strip("`") for a in cells[2].split("/")]
        assert len(keys) == len(defaults) == len(actuals), f"ragged row: {line}"
        parent = keys[0].rsplit(".", 1)[0]
        for key, default, actual in zip(keys, defaults, actuals):
            full = key if not key.startswith(".") else f"{parent}{key}"
            rows.append((full, default, actual))
    assert rows, f"no table rows found in {README}; did the section move?"
    return rows


def test_every_claimed_chart_default_is_the_real_chart_default() -> None:
    """The left-hand column against `values.yaml`.

    This is the column a reader trusts to answer "what does a plain `helm install` do?", and for
    four of these keys the honest answer is a security property — whether the chart writes a
    cluster-scoped CR, reads logs naming every person who authenticates, or accepts bearer tokens
    on /api.
    """
    defaults = flatten(yaml.safe_load(VALUES.read_text()))
    wrong = [
        f"{key}: README says default {claimed!r}, values.yaml says {as_written(defaults[key])!r}"
        for key, claimed, _ in table_rows()
        if key in defaults and as_written(defaults[key]) != claimed
    ]
    assert not wrong, "environments/README.md misstates a chart default:\n  " + "\n  ".join(wrong)


def test_every_key_in_the_table_still_exists_in_the_chart() -> None:
    """A renamed value must not leave a row describing a key nobody can set."""
    defaults = flatten(yaml.safe_load(VALUES.read_text()))
    missing = [key for key, _, _ in table_rows() if key not in defaults]
    assert not missing, (
        "environments/README.md documents keys the chart no longer declares:\n  "
        + "\n  ".join(missing)
    )


def test_every_claimed_crc_value_is_what_crc_actually_sets() -> None:
    """The right-hand column against `crc.yaml`.

    Catches the drift that turns the table's verdicts into fiction: a lab file that stopped
    overriding something the table still calls a "lab override".
    """
    actual = flatten(yaml.safe_load(CRC.read_text()))
    wrong = [
        f"{key}: README says crc.yaml sets {claimed!r}, it sets {as_written(actual[key])!r}"
        for key, _, claimed in table_rows()
        if key in actual and as_written(actual[key]) != claimed
    ]
    assert not wrong, "environments/README.md misstates crc.yaml:\n  " + "\n  ".join(wrong)


def test_the_table_covers_every_key_crc_overrides() -> None:
    """A row per key, so a NEW override cannot arrive undocumented.

    The direction that matters: somebody enabling another privileged feature for the lab and not
    saying so here leaves a table that reads complete and is not.
    """
    documented = {key for key, _, _ in table_rows()}
    actual = set(flatten(yaml.safe_load(CRC.read_text())))
    assert not actual - documented, (
        "crc.yaml sets keys the README's table does not list:\n  "
        + "\n  ".join(sorted(actual - documented))
    )
    assert not documented - actual, (
        "the README's table lists keys crc.yaml no longer sets:\n  "
        + "\n  ".join(sorted(documented - actual))
    )


def test_crc_introduces_no_key_the_chart_does_not_declare() -> None:
    """THE TABLE'S HEADLINE CLAIM, and the reason it is only five rows long.

    "Every key `crc.yaml` sets already has a chart default." If that stops being true, a release
    file is carrying configuration the chart knows nothing about — which templates to nothing and
    fails silently, since Helm does not reject unknown values.
    """
    defaults = set(flatten(yaml.safe_load(VALUES.read_text())))
    orphans = sorted(set(flatten(yaml.safe_load(CRC.read_text()))) - defaults)
    assert not orphans, (
        "crc.yaml sets keys with no chart default, so the README's headline claim is false and "
        "these values template to nothing:\n  " + "\n  ".join(orphans)
    )


def test_the_redundant_row_is_still_redundant() -> None:
    """The one row whose verdict is a MEASUREMENT, not a policy.

    `config.unmanagedAudit.mode` is called redundant because the chart default already equals it.
    That is true today and was not always: the default moved to `log` after crc.yaml was written.
    If it moves again the row becomes a real override and the word "redundant" becomes a lie — so
    this asserts the equality the word rests on, rather than the word.
    """
    key = "config.unmanagedAudit.mode"
    default = flatten(yaml.safe_load(VALUES.read_text()))[key]
    crc = flatten(yaml.safe_load(CRC.read_text()))[key]
    assert default == crc, (
        f"{key} is no longer redundant: the chart defaults to {default!r} while crc.yaml sets "
        f"{crc!r}. Update the README's verdict from 'redundant' to 'lab override'."
    )
