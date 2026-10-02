"""Recovery mode in the chart (#303): `recovery.enabled` swaps the dashboard's command for the
chart's recovery script on the same pod and volume, drops the liveness probe, keeps the pod out of
the Service, and refuses what cannot be safe. Everything else renders as it did.

These shell out to `helm template` because the switch and its guards ARE Helm templating. The
script itself is tested in tests/test_recovery_mode.py.
"""

from __future__ import annotations

import importlib.util
import pathlib
import re
import shutil
import subprocess

import pytest
import yaml

REPO = pathlib.Path(__file__).resolve().parents[2]
CHART = REPO / "charts" / "group-sync-dashboard"
SCRIPT = CHART / "scripts" / "recovery_mode.py"
ON = {"recovery__enabled": "true"}
OFFSITE = {"backup__offsite__enabled": "true"}

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def render(*flags: str, **values):
    """Render the chart. Returns (ok, combined output). `__` in a key is `.`."""
    args = ["helm", "template", "t", str(CHART), "--set", "ingress.host=t.example.com", *flags]
    for key, value in values.items():
        args += ["--set", f"{key.replace('__', '.')}={value}"]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


def _docs(**values) -> list[dict]:
    ok, out = render(**values)
    assert ok, out
    return [d for d in yaml.safe_load_all(out) if d]


def _deployment(docs: list[dict]) -> dict:
    return next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == "t-group-sync-dashboard")


def _container(docs: list[dict], name: str = "dashboard") -> dict:
    return next(c for c in _deployment(docs)["spec"]["template"]["spec"]["containers"] if c["name"] == name)


def _env(container: dict) -> dict:
    return {e["name"]: e.get("value") for e in container["env"]}


def _key(doc: dict) -> tuple[str, str]:
    return doc["kind"], doc["metadata"]["name"]


def test_t303_1_recovery_runs_the_chart_script_on_the_same_volume_with_the_env():
    docs = _docs(**ON)
    dashboard = _container(docs)
    assert dashboard["command"] == ["python3.14", "/scripts/recovery_mode.py", "--release", "t"]
    assert "gsd.api:create_app" not in " ".join(dashboard["command"])
    env = _env(dashboard)
    assert env["GSD_RECOVERY_MODE"] == "true" and env["GSD_RECOVERY_MODE_TTL"] == "2h"
    assert env["GSD_DB_PATH"] == "/data/gsd.db"
    assert _deployment(docs)["spec"]["replicas"] == 1
    data = [m for m in dashboard["volumeMounts"] if m["name"] == "data"]
    assert data == [m for m in _container(_docs())["volumeMounts"] if m["name"] == "data"] == [{"name": "data", "mountPath": "/data"}]
    assert {"name": "recovery-script", "mountPath": "/scripts", "readOnly": True} in dashboard["volumeMounts"]
    assert _env(_container(_docs(recovery__ttl="90m", **ON)))["GSD_RECOVERY_MODE_TTL"] == "90m"


def test_t303_2_recovery_overrides_the_image_cmd_with_the_proxy_off_too():
    docs = _docs(oauthProxy__enabled="false", visibility__enabled="false", reporting__enabled="false", **ON)
    assert _container(docs)["command"][:2] == ["python3.14", "/scripts/recovery_mode.py"]
    off = _container(_docs(oauthProxy__enabled="false", visibility__enabled="false", reporting__enabled="false"))
    assert "command" not in off, "with the proxy off the default render leaves the image's CMD, uvicorn"


def test_t303_3_no_liveness_probe_in_recovery_mode():
    assert "livenessProbe" not in _container(_docs(**ON))
    assert "livenessProbe" in _container(_docs())


@pytest.mark.parametrize("readiness", ["true", "false"])
def test_t303_4_a_readiness_probe_that_cannot_pass_keeps_the_pod_out_of_the_service(readiness):
    dashboard = _container(_docs(probes__readiness__enabled=readiness, **ON))
    assert dashboard["readinessProbe"] == {"tcpSocket": {"port": "http"}, "periodSeconds": 30, "timeoutSeconds": 5,
                                           "failureThreshold": 1}
    # `http` names the dashboard container's own 8080, where nothing listens while the app is stopped.
    assert {"name": "http", "containerPort": 8080} in dashboard["ports"]


def test_t303_5_more_than_one_replica_is_refused():
    ok, out = render(replicaCount="2", leaderElection__enabled="false", reporting__enabled="false", **ON)
    assert not ok and "recovery.enabled=true requires replicaCount: 1 (it is 2)" in out
    ok, out = render(replicaCount="0", **ON)
    assert not ok and "requires replicaCount: 1 (it is 0)" in out
    # Codex F3: `int true` is 1, so a YAML boolean passed and rendered `replicas: true`
    ok, out = render(replicaCount="true", **ON)
    assert not ok and "requires replicaCount: 1 (it is true)" in out


@pytest.mark.parametrize("ttl,why", [("abc", "is not a duration"), ("-5m", "is not a duration"),
                                     ("7200", "is not a duration"), ("0", "is zero"), ("0s", "is zero")])
def test_t303_6_a_ttl_that_is_not_a_positive_duration_is_refused(ttl, why):
    ok, out = render(recovery__ttl=ttl, **ON)
    assert not ok and f'recovery.ttl "{ttl}" {why}' in out


def test_t303_7_recovery_without_a_volume_is_refused():
    ok, out = render(persistence__enabled="false", reporting__enabled="false", **ON)
    assert not ok and "recovery.enabled=true requires persistence.enabled=true" in out


def test_the_switch_is_read_as_a_word():
    ok, out = render("--set-string", "recovery.enabled=yes")
    assert not ok and 'recovery.enabled "yes" is not true or false' in out
    ok, quoted_false = render("--set-string", "recovery.enabled=false")
    assert ok and quoted_false == render()[1]


def test_t303_14_off_renders_exactly_the_default_and_the_dashboard_as_today():
    ok, default = render()
    assert ok, default
    assert render(recovery__enabled="false")[1] == default
    # `helm upgrade --reuse-values` from a chart without the block renders with no `recovery` key.
    assert render(recovery="null")[1] == default
    dashboard = _container(_docs())
    assert "gsd.api:create_app" in dashboard["command"]
    assert "livenessProbe" in dashboard and dashboard["readinessProbe"]["httpGet"]["path"] == "/readyz"
    assert not [k for k in _env(dashboard) if k.startswith("GSD_RECOVERY")]
    assert not [d for d in _docs() if d["metadata"]["name"].endswith("-recovery")]


@pytest.mark.parametrize("extra", [{}, OFFSITE], ids=["default", "offsite"])
def test_t303_15_nothing_but_the_dashboard_container_and_its_volumes_changes(extra):
    off = {_key(d): d for d in _docs(**extra)}
    on = {_key(d): d for d in _docs(**extra, **ON)}
    assert set(on) - set(off) == {("ConfigMap", "t-group-sync-dashboard-recovery")}
    assert set(off) <= set(on)
    changed = [k for k in off if off[k] != on[k]]
    assert changed == [("Deployment", "t-group-sync-dashboard")], changed
    before, after = off[changed[0]], on[changed[0]]
    assert before["metadata"] == after["metadata"]
    spec_before, spec_after = before["spec"]["template"]["spec"], after["spec"]["template"]["spec"]
    assert before["spec"]["template"]["metadata"] == after["spec"]["template"]["metadata"]
    assert [c for c in spec_before["containers"] if c["name"] != "dashboard"] == \
           [c for c in spec_after["containers"] if c["name"] != "dashboard"], "the oauth-proxy sidecar changed"
    assert [v for v in spec_after["volumes"] if v not in spec_before["volumes"]] == \
           [v for v in spec_after["volumes"] if v["name"] in ("recovery-script", "offsite")]
    assert all(v in spec_after["volumes"] for v in spec_before["volumes"])
    for key in ("replicas", "strategy", "selector"):
        assert before["spec"][key] == after["spec"][key]


def test_t303_16_no_rbac_rule_is_added_or_removed():
    kinds = ("Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding", "ServiceAccount")
    for extra in ({}, OFFSITE):
        off = sorted((yaml.safe_dump(d) for d in _docs(**extra) if d["kind"] in kinds))
        on = sorted((yaml.safe_dump(d) for d in _docs(**extra, **ON) if d["kind"] in kinds))
        assert off == on


def test_the_configmap_carries_the_script_verbatim():
    cm = next(d for d in _docs(**ON) if _key(d) == ("ConfigMap", "t-group-sync-dashboard-recovery"))
    assert cm["data"]["recovery_mode.py"].strip() == SCRIPT.read_text().strip()
    assert cm["metadata"]["labels"]["app.kubernetes.io/component"] == "recovery"
    volume = next(v for v in _deployment(_docs(**ON))["spec"]["template"]["spec"]["volumes"] if v["name"] == "recovery-script")
    assert volume == {"name": "recovery-script", "configMap": {"name": "t-group-sync-dashboard-recovery", "defaultMode": 0o444}}


@pytest.mark.parametrize("claim,expected", [("", "t-group-sync-dashboard-backup-offsite"), ("my-offsite", "my-offsite")])
def test_the_offsite_claim_is_mounted_read_only_as_the_cronjob_names_it(claim, expected):
    docs = _docs(backup__offsite__destination__pvc__existingClaim=claim, **OFFSITE, **ON)
    pod = _deployment(docs)["spec"]["template"]["spec"]
    assert {"name": "offsite", "persistentVolumeClaim": {"claimName": expected, "readOnly": True}} in pod["volumes"]
    assert {"name": "offsite", "mountPath": "/offsite", "readOnly": True} in _container(docs)["volumeMounts"]
    cronjob = next(d for d in docs if d["kind"] == "CronJob")
    shipped = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
    assert {"name": "offsite", "persistentVolumeClaim": {"claimName": expected}} in shipped


S3 = {"backup__offsite__destination__type": "s3", "backup__offsite__destination__s3__existingSecret": "creds",
      "backup__offsite__destination__s3__image__repository": "public.ecr.aws/aws-cli/aws-cli"}


@pytest.mark.parametrize("extra", [{}, {"backup__offsite__enabled": "false"}, OFFSITE,
                                   {**OFFSITE, "backup__offsite__destination__pvc__existingClaim": "my-offsite"},
                                   {**OFFSITE, **S3}], ids=["default", "off", "pvc", "existing-claim", "s3"])
def test_the_offsite_claim_is_mounted_exactly_when_the_cronjob_writes_one(extra):
    """The mount and the CronJob are decided by one switch today and by #304's helper next; whatever decides
    them, the recovery pod mounts the claim the CronJob writes, and nothing when it writes none. A default
    that turns offsite on (#304) must turn the mount on with it, or this test fails."""
    docs = _docs(**extra, **ON)
    mounted = [v["persistentVolumeClaim"]["claimName"] for v in _deployment(docs)["spec"]["template"]["spec"]["volumes"]
               if v["name"] == "offsite"]
    written = [v["persistentVolumeClaim"]["claimName"] for d in docs if d["kind"] == "CronJob"
               for v in d["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
               if v["name"] == "offsite" and "persistentVolumeClaim" in v]
    assert mounted == written, (mounted, written)


@pytest.mark.parametrize("ttl", ["2h", "90m", "1h30m", "1.5s", "250ms", "abc", "0", "0s", "-5m", "7200", "2H"])
def test_the_chart_and_the_script_accept_the_same_ttls(ttl):
    spec = importlib.util.spec_from_file_location("recovery_mode", SCRIPT)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    ok, out = render(recovery__ttl=ttl, **ON)
    assert ok == bool(script.ttl_seconds(ttl)), (ttl, out[-400:])


def _values_comment() -> str:
    lines = (CHART / "values.yaml").read_text().splitlines()
    end = lines.index("recovery:")
    start = max(i for i in range(end) if lines[i].startswith("# ---"))
    return "\n".join(lines[start:end])


def _between(text: str, start: str, end: str) -> str:
    begin = text.index(start)
    return text[begin:text.index(end, begin + len(start))]


def test_t303_19_the_docs_name_the_switch_and_say_what_alerts():
    for doc in (CHART / "values.yaml", CHART / "README.md", REPO / "docs" / "RUNBOOK_backup_restore.md"):
        text = doc.read_text()
        assert "recovery.enabled" in text and "recovery.ttl" in text, doc
    comment = re.sub(r"\s*\n#\s*", " ", _values_comment())
    assert "values file" in comment and "deployment pipeline" in comment and "never with `oc set env`" in comment.lower()
    assert "GroupSyncDashboardNotPolling does not fire" in comment
    assert "GroupSyncDashboardReportSnapshotStale" in comment and "The TTL is the bound" in comment
    # what the TTL ends (measured: an exec'd process is killed when PID 1 exits) and what restarts it
    assert "every process in the container stops" in comment and "evicted" in comment and "0/1" in comment
    runbook = (REPO / "docs" / "RUNBOOK_backup_restore.md").read_text()
    assert "Check the time left first" in runbook and "every process in the container stops" in runbook
    for doc in (CHART / "README.md", REPO / "docs" / "RUNBOOK_backup_restore.md", CHART / "values.yaml"):
        assert not re.search(r"NotPolling[^.]*(fires|covers)[^.]*recovery", doc.read_text()), doc


def test_the_only_documented_path_is_the_values_file():
    """The operator's rule (2026-10-01): recovery mode is set in the release's values file and rolled out through
    the release's deployment pipeline. No Argo CD Application patch or parameter, no argocd or Helm command line
    in the operator's path; Argo CD is named only to say why a hand edit is reverted, and a plain `helm upgrade
    -f` only on the runbook's line for development and troubleshooting."""
    readme = (CHART / "README.md").read_text()
    runbook = _between((REPO / "docs" / "RUNBOOK_backup_restore.md").read_text(),
                       "**Recovery mode is the primary path", "**Without recovery mode**")
    assert runbook.count("**Development and troubleshooting only:**") == 1, "the plain Helm form has one labelled line"
    operator_path, development = runbook.split("**Development and troubleshooting only:**")
    texts = {
        "values comment": re.sub(r"\s*\n#\s*", " ", _values_comment()),
        "README section": _between(readme, "### Recovery mode", "\n#"),
        "README upgrading": _between(readme, "**To restore the database, before or after an upgrade", "## Uninstall"),
        "runbook": operator_path,
        "CHANGELOG": _between((REPO / "docs" / "CHANGELOG.md").read_text(), "- **Recovery mode:", "\n- **"),
    }
    for name, text in texts.items():
        assert "values file" in text, name
        assert not [word for word in ("helm upgrade", "--set", "--reset-then-reuse-values", "--reuse-values", "argocd",
                                      "applications.argoproj.io", "oc patch", "oc delete", "parameters") if word in text.lower()], name
        for sentence in re.split(r"(?<=[.;])\s+", text):
            assert "Argo CD" not in sentence or "revert" in sentence, (name, sentence)
    assert "helm upgrade $REL <chart> -n $NS -f <values-file>" in development and "--set" not in development


def test_the_docs_warn_against_a_pipeline_that_rolls_a_failed_rollout_back():
    """The recovery rollout never becomes ready, so a pipeline that remediates a failed rollout by rolling it
    back (Helm 4's --rollback-on-failure, Helm 3's --atomic: the release goes back to the revision before, in
    which the app runs with its liveness probe) turns recovery mode off on its own and starts the app on a
    file that may be half restored. The three operator texts say so, in words that keep the operator path
    free of a command line."""
    runbook = _between((REPO / "docs" / "RUNBOOK_backup_restore.md").read_text(),
                       "**Recovery mode is the primary path", "**Development and troubleshooting only:**")
    texts = {"values comment": re.sub(r"\s*\n#\s*", " ", _values_comment()),
             "README section": _between((CHART / "README.md").read_text(), "### Recovery mode", "\n#"),
             "runbook": runbook}
    for name, text in texts.items():
        text = re.sub(r"\s+", " ", text)                    # the README and the runbook wrap at 110 columns
        assert "--rollback-on-failure" in text and "--atomic" in text and "half restored" in text, name
        assert "helm upgrade" not in text.lower(), name
