"""Read-only multi-cluster observability for the group-sync-operator. Named by TITLE below."""

# Must equal pyproject.toml's `version`, which is the source of truth the build script reads.
# This copy is what /api/version and gsd_build_info report, so drift here tells an operator the
# pod is running a version it is not — the same failure appVersion had, and quieter, because the
# endpoint answers confidently either way. tests/test_chart_versions.py holds the two together;
# before that test existed nothing did.
__version__ = "0.12.0"

# THE ONE PLACE THE DASHBOARD IS NAMED. The page title, the header, the signed-out page and
# the API docs all read this; the README heading is held to it by tests/test_title.py. It used
# to be a literal in five files, and the last rename changed one of them and left the rest to
# be found by hand. Renaming is one edit here, plus recapturing the screenshots.
TITLE = "OCP Access Tracking Dashboard"
