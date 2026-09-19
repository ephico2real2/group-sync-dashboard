"""The Prometheus renderer: definitions → metric families for a collector to yield.

REFUSES an `internal` definition. /metrics is unauthenticated, and the privacy class is enforced
here — at the one place a definition becomes a series — rather than by every caller remembering
which tuple to pass. A family is DECLARED (HELP/TYPE) even when its collector returns None, the
gsd/metrics.py rule: the alert-rule tests resolve every PrometheusRule reference against a HELP
line on a bare store, so a family that only exists once its source is readable would make a rule on
it unverifiable. Samples are added only for what was measured.
"""

from __future__ import annotations

import logging

from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

from . import COUNTER, PUBLIC, Context, Kpi

log = logging.getLogger(__name__)


class PrivacyViolation(ValueError):
    """An internal-class KPI was offered to the public renderer."""


def render(kpis: tuple[Kpi, ...], ctx: Context):
    """Yield one family per definition, in order. Raises PrivacyViolation before any family is
    built if a definition is not `public` — the whole exposition is refused, not one series."""
    offenders = [k.name for k in kpis if k.privacy != PUBLIC]
    if offenders:
        raise PrivacyViolation(f"internal KPI(s) offered to /metrics: {', '.join(offenders)}")
    for kpi in kpis:
        family_cls = CounterMetricFamily if kpi.kind == COUNTER else GaugeMetricFamily
        family = family_cls(kpi.name, kpi.help, labels=list(kpi.labels))
        try:
            samples = kpi.collect(ctx)
        except Exception:  # noqa: BLE001 — one unreadable source must not fail the whole scrape
            log.exception("KPI %s could not be collected; omitted from this scrape", kpi.name)
            samples = None
        for sample in samples or ():
            family.add_metric(list(sample.labels), sample.value)
        yield family
