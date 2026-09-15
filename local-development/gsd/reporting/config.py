"""The report service's settings — environment only, no ConfigMap.

Env rather than a YAML file because every value is a path, a number or a short enum that the
chart writes onto the Deployment (charts/group-sync-dashboard/templates/report-deployment.yaml),
where an auditor reads `oc describe deploy`. Names start GSD_REPORT_ so `oc set env --list` groups
them. Every wrong value fails at startup with the variable named: this process is one uvicorn
worker with nothing to degrade to.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

#: The PDF/A variants fpdf2 enforces (measured against fpdf2 2.8.8: DocumentCompliance has exactly
#: these plus PDFA_4E/PDFA_4F, which need an engineering/attachment intent this catalogue has no use
#: for). "" is a plain PDF. The chart validates the same list at render (gsd.reportPdfVariant).
PDF_VARIANTS = ("", "pdf/a-1b", "pdf/a-2b", "pdf/a-2u", "pdf/a-3b", "pdf/a-3u", "pdf/a-4")

#: The catalogue's names, in the order the Reports tab lists them. The chart's per-report switches
#: use the camelCase forms of these (values.yaml reporting.reports.*); gsd.reporting.catalogue's
#: REGISTRY is held to this tuple by tests/test_reporting_catalogue.py.
REPORT_NAMES = (
    "namespace-access", "access-matrix", "privileged-access", "binding-findings", "groups",
    "users", "login-activity", "dormant-access", "groupsync-health", "compliance-snapshot",
    "access-certification",
)


class ReportConfigError(Exception):
    pass


def _int_env(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ReportConfigError(f"{name}={raw!r} is not an integer") from exc
    if not lo <= value <= hi:
        raise ReportConfigError(f"{name}={value} is outside [{lo}, {hi}]")
    return value


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    word = raw.strip().lower()
    if word in ("true", "1", "yes"):
        return True
    if word in ("false", "0", "no"):
        return False
    raise ReportConfigError(f"{name}={raw!r} is not a boolean (true/false)")


@dataclass(frozen=True)
class ReportSettings:
    snapshot_dir: str = "/data/report"
    artifact_dir: str = "/artifacts"
    token_file: str = "/etc/gsd/report/token"
    #: TLS for uvicorn. Both empty = plain HTTP (reporting.tls.enabled=false).
    tls_cert_file: str = ""
    tls_key_file: str = ""
    pdf_enabled: bool = True
    pdf_variant: str = "pdf/a-2b"
    #: The embedded font for the PDF (regular, bold), vendored under gsd/static/vendor.
    font_regular: str = ""
    font_bold: str = ""
    retention_days: int = 90
    retention_max_runs: int = 500
    marking: str = "Handling: internal — access review evidence"
    #: Which catalogue entries this deployment switched on (the chart derives loginActivity).
    enabled_reports: tuple[str, ...] = REPORT_NAMES
    #: Facts about the dashboard's configuration the report service cannot read from a snapshot
    #: and must be told, so the coverage block is truthful: whether login capture and the
    #: namespaces read are on, and the binding cadence for the freshness line.
    login_capture_enabled: bool = False
    namespaces_read_enabled: bool = False
    binding_interval_seconds: int = 300
    namespace_selector_label: str = ""   # the captured key the namespace-access report selects on (B2)
    #: One worker renders at a time; the queue is bounded so a burst answers 429 rather than
    #: piling up renders the pod's memory limit then ends.
    max_queued_runs: int = 8
    log_level: str = "INFO"
    git_commit: str = field(default_factory=lambda: os.environ.get("GSD_GIT_COMMIT", "unknown"))


def load_report_settings() -> ReportSettings:
    variant = os.environ.get("GSD_REPORT_PDF_VARIANT", "pdf/a-2b")
    if variant not in PDF_VARIANTS:
        raise ReportConfigError(f"GSD_REPORT_PDF_VARIANT={variant!r} must be one of {PDF_VARIANTS}")
    enabled_raw = os.environ.get("GSD_REPORT_ENABLED_REPORTS", ",".join(REPORT_NAMES))
    enabled = tuple(n.strip() for n in enabled_raw.split(",") if n.strip())
    unknown = sorted(set(enabled) - set(REPORT_NAMES))
    if unknown:
        raise ReportConfigError(f"GSD_REPORT_ENABLED_REPORTS names reports that do not exist: {unknown}")
    cert, key = os.environ.get("GSD_REPORT_TLS_CERT", ""), os.environ.get("GSD_REPORT_TLS_KEY", "")
    if bool(cert) != bool(key):
        raise ReportConfigError("GSD_REPORT_TLS_CERT and GSD_REPORT_TLS_KEY must be set together or not at all")
    pdf_enabled = _bool_env("GSD_REPORT_PDF_ENABLED", True)
    font_regular = os.environ.get("GSD_REPORT_FONT_REGULAR", "")
    font_bold = os.environ.get("GSD_REPORT_FONT_BOLD", "")
    if pdf_enabled and variant and (not font_regular or not font_bold):
        # PDF/A demands embedded fonts (measured: fpdf2 refuses base fonts under every PDF/A
        # profile), so a PDF/A variant with no font file is a configuration that cannot render.
        raise ReportConfigError("a PDF/A variant needs GSD_REPORT_FONT_REGULAR and GSD_REPORT_FONT_BOLD (TrueType files)")
    return ReportSettings(
        snapshot_dir=os.environ.get("GSD_REPORT_SNAPSHOT_DIR", "/data/report"),
        artifact_dir=os.environ.get("GSD_REPORT_ARTIFACT_DIR", "/artifacts"),
        token_file=os.environ.get("GSD_REPORT_TOKEN_FILE", "/etc/gsd/report/token"),
        tls_cert_file=cert, tls_key_file=key,
        pdf_enabled=pdf_enabled, pdf_variant=variant,
        font_regular=font_regular, font_bold=font_bold,
        retention_days=_int_env("GSD_REPORT_RETENTION_DAYS", 90, lo=0, hi=3650),
        retention_max_runs=_int_env("GSD_REPORT_RETENTION_MAX_RUNS", 500, lo=0, hi=100000),
        marking=os.environ.get("GSD_REPORT_MARKING", ReportSettings.marking),
        enabled_reports=enabled,
        login_capture_enabled=_bool_env("GSD_REPORT_LOGIN_CAPTURE_ENABLED", False),
        namespaces_read_enabled=_bool_env("GSD_REPORT_NAMESPACES_READ_ENABLED", False),
        binding_interval_seconds=_int_env("GSD_REPORT_BINDING_INTERVAL_SECONDS", 300, lo=1, hi=86400),
        namespace_selector_label=os.environ.get("GSD_REPORT_NS_SELECTOR_LABEL", "").strip(),
        max_queued_runs=_int_env("GSD_REPORT_MAX_QUEUED_RUNS", 8, lo=1, hi=100),
        log_level=os.environ.get("GSD_LOG_LEVEL", "INFO"),
    )
