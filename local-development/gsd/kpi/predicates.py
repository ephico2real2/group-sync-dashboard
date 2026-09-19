"""The SQL predicates behind the access-posture KPIs, in ONE place.

`Store.groups()` (the list), `Store.group_counts()` (the headline and `gsd_groups_*_total`) and the
report service's `Snapshot.counts()` (the compliance snapshot's signed figures) all count the same
things, and they used to spell the predicate three times. A count that disagrees with its own list is
the defect class this project keeps rediscovering, and a KPI band that disagrees with the signed PDF
would be the same defect across two surfaces — so each spells it ONCE, from here, and
tests/test_kpi.py drives the store and a snapshot from one seeded database and holds their numbers
equal (#156).

`empty` and `unattributed` OVERLAP on purpose: "which groups grant nobody?" and "which groups is no
CR managing?" are two questions, not a partition (Store._group_state_predicate says why).
"""

from __future__ import annotations

#: A group with no members, whatever created it.
GROUP_EMPTY = "member_count = 0"
#: A group no GroupSync CR manages.
GROUP_UNATTRIBUTED = "sync_provider IS NULL"


def qualified(predicate: str, alias: str = "") -> str:
    """The predicate with its column qualified by a table alias (`g.member_count = 0`)."""
    return f"{alias}.{predicate}" if alias else predicate
