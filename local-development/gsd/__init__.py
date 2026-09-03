"""GroupSync dashboard — read-only multi-cluster observability for the group-sync-operator."""

# Must equal pyproject.toml's `version`, which is the source of truth the build script reads.
# This copy is what /api/version and gsd_build_info report, so drift here tells an operator the
# pod is running a version it is not — the same failure appVersion had, and quieter, because the
# endpoint answers confidently either way. tests/test_chart_versions.py holds the two together;
# before that test existed nothing did.
__version__ = "0.8.0"
