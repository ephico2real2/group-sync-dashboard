"""The eleven reports, registered once, in the order the Reports tab lists them."""

from __future__ import annotations

from ..config import REPORT_NAMES
from . import (access_certification, access_matrix, binding_findings, compliance_snapshot,
               dormant_access, groups, groupsync_health, login_activity, namespace_access,
               privileged_access, users)
from .common import Built, ParamSpec, ReportSpec, RunContext, ValidationError, validate_params

_MODULES = (namespace_access, access_matrix, privileged_access, binding_findings, groups, users,
            login_activity, dormant_access, groupsync_health, compliance_snapshot, access_certification)

#: name -> (spec, build). Held to config.REPORT_NAMES by tests/test_reporting_catalogue.py.
REGISTRY: dict[str, tuple[ReportSpec, object]] = {m.SPEC.name: (m.SPEC, m.build) for m in _MODULES}

assert tuple(REGISTRY) == REPORT_NAMES, "catalogue order must match config.REPORT_NAMES"

__all__ = ["REGISTRY", "Built", "ParamSpec", "ReportSpec", "RunContext", "ValidationError", "validate_params"]
