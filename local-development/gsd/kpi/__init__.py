"""The dashboard's KPIs, computed once from one set of definitions and rendered to two surfaces (#156).

A KPI is a `Kpi`: a name, a kind, a bounded label set, a PRIVACY CLASS and a collector. Collectors
read the store, the process's own cgroup, or the process-event seam; two renderers emit what they
return — `render_prom` as Prometheus families for `/metrics`, `render_json` as the tier-gated payload
the pages read. The number a page shows and the number Prometheus scrapes therefore come from the
same collector, and cannot drift.

THE PRIVACY CLASS IS A FIELD, NOT A CONVENTION. `/metrics` is unauthenticated by design, so a
`public` KPI carries aggregates under bounded labels only — never a person's or a group's name, and
never a distinct-user count: `gsd_dashboard_active_users` was exposed and deliberately removed because
an unlabelled count of people is still personnel information on an open endpoint
(docs/SPEC_per_user_visibility.md). Anything counting people is `internal`, and `render_prom`
REFUSES an internal definition rather than trusting every caller to remember — tests/test_kpi.py
holds the two renderers to the class.

UNAVAILABLE IS NOT ZERO. A collector that cannot measure returns None and the KPI is OMITTED from
both surfaces — the `gsd_sqlite_wal_bytes` precedent: a failure to measure must never read as a
measurement of zero (a cgroup v1 node, a `cpu.max` of `max`, a report service of an older build).

SCALAR QUERIES ONLY. Every store-backed KPI is one aggregate query; none is derived from a capped
page — the Usage tab once reported 167 days / 5,000 interactions when the truth was 364 / 10,920.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

PUBLIC = "public"
INTERNAL = "internal"
PRIVACY_CLASSES = (PUBLIC, INTERNAL)

GAUGE = "gauge"
COUNTER = "counter"
KINDS = (GAUGE, COUNTER)

#: The two processes that self-report system usage. Bounded at two: a `component` label value is one
#: of these and nothing else, which tests/test_kpi.py pins.
COMPONENT_DASHBOARD = "dashboard"
COMPONENT_REPORT = "report"
COMPONENTS = (COMPONENT_DASHBOARD, COMPONENT_REPORT)


@dataclass(frozen=True)
class Sample:
    """One measurement: the label values, in the definition's label order, and the value."""

    labels: tuple[str, ...]
    value: float


@dataclass(frozen=True)
class Kpi:
    """One definition. `collect(ctx)` returns the samples, or None when the source cannot be measured
    (omitted, never zeroed). `public` definitions are the ones `/metrics` may carry; their `name` is
    the Prometheus family name and every label is bounded. `internal` definitions reach the JSON
    surface only, behind the tier rules."""

    name: str
    help: str
    kind: str
    labels: tuple[str, ...]
    privacy: str
    collect: Callable[["Context"], Iterable[Sample] | None]

    def __post_init__(self) -> None:
        if self.privacy not in PRIVACY_CLASSES:
            raise ValueError(f"{self.name}: privacy must be one of {PRIVACY_CLASSES}, not {self.privacy!r}")
        if self.kind not in KINDS:
            raise ValueError(f"{self.name}: kind must be one of {KINDS}, not {self.kind!r}")


@dataclass
class Context:
    """What collectors may read. Every field is optional so a definition can be exercised without a
    cluster, a cgroup or a store: a collector whose source is absent returns None and is omitted.

    `component` names the process the collectors run in (`dashboard` | `report`); `system` is that
    process's own cgroup sampler; `volume` the path whose filesystem the process's data lives on;
    `store` the dashboard's store and `cluster_ids` the clusters it serves; `signals` the dashboard's
    RuntimeSignals (the event-watermark counters and the report service's last system sample).
    """

    component: str
    system: object | None = None
    volume: str | None = None
    store: object | None = None
    cluster_ids: tuple[str, ...] = ()
    signals: object | None = None
