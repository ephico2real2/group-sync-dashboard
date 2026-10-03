"""Recovery mode in the chart (#303), its own workload since #532: a second Deployment renders the app's pod
spec with the chart's recovery script on the same volume, no liveness or readiness probe and labels no Service
selects, at 0 replicas; `recovery.enabled` scales the app's Deployment to 0 and it to 1, and refuses what cannot
be safe. Everything else renders as it did.

These shell out to `helm template` because the switch and its guards ARE Helm templating. The
script itself is tested in tests/test_recovery_mode.py.
"""

from __future__ import annotations

import importlib.util
import json
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
APP, REC = "t-group-sync-dashboard", "t-group-sync-dashboard-recovery"
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


def _deployment(docs: list[dict], name: str = APP) -> dict:
    return next(d for d in docs if d["kind"] == "Deployment" and d["metadata"]["name"] == name)


def _container(docs: list[dict], name: str = "dashboard", workload: str = APP) -> dict:
    return next(c for c in _deployment(docs, workload)["spec"]["template"]["spec"]["containers"] if c["name"] == name)


def _env(container: dict) -> dict:
    return {e["name"]: e.get("value") for e in container["env"]}


def _key(doc: dict) -> tuple[str, str]:
    return doc["kind"], doc["metadata"]["name"]


def test_t303_1_recovery_runs_the_chart_script_on_the_same_volume_with_the_env():
    docs = _docs(**ON)
    dashboard = _container(docs, workload=REC)
    assert dashboard["command"] == ["python3.14", "/scripts/recovery_mode.py", "--release", "t"]
    assert "gsd.api:create_app" not in " ".join(dashboard["command"])
    env = _env(dashboard)
    assert env["GSD_RECOVERY_MODE"] == "true" and env["GSD_RECOVERY_MODE_TTL"] == "2h"
    assert env["GSD_DB_PATH"] == "/data/gsd.db"
    assert _deployment(docs, REC)["spec"]["replicas"] == 1
    data = [m for m in dashboard["volumeMounts"] if m["name"] == "data"]
    assert data == [m for m in _container(_docs())["volumeMounts"] if m["name"] == "data"] == [{"name": "data", "mountPath": "/data"}]
    assert {"name": "recovery-script", "mountPath": "/scripts", "readOnly": True} in dashboard["volumeMounts"]
    assert _env(_container(_docs(recovery__ttl="90m", **ON), workload=REC))["GSD_RECOVERY_MODE_TTL"] == "90m"


def test_t303_2_recovery_overrides_the_image_cmd_with_the_proxy_off_too():
    docs = _docs(oauthProxy__enabled="false", visibility__enabled="false", reporting__enabled="false", **ON)
    assert _container(docs, workload=REC)["command"][:2] == ["python3.14", "/scripts/recovery_mode.py"]
    off = _container(_docs(oauthProxy__enabled="false", visibility__enabled="false", reporting__enabled="false"))
    assert "command" not in off, "with the proxy off the default render leaves the image's CMD, uvicorn"


def test_t303_3_no_liveness_probe_in_recovery_mode():
    assert "livenessProbe" not in _container(_docs(**ON), workload=REC)
    assert "livenessProbe" in _container(_docs())


@pytest.mark.parametrize("readiness", ["true", "false"])
def test_t532_6_the_recovery_pod_has_no_readiness_probe_and_no_selector_picks_it(readiness):
    """#532 replaced T303-4's readiness probe that could not pass: the recovery pod is kept out of the Service by
    its labels, so it is ready once it runs and its Deployment reports available."""
    docs = _docs(probes__readiness__enabled=readiness, **ON)
    assert "readinessProbe" not in _container(docs, workload=REC)
    assert ("readinessProbe" in _container(docs)) == (readiness == "true"), "the app's probe is as before"


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
    # #532: the recovery workload and its script are rendered on every release, the workload at 0 replicas
    assert sorted(_key(d) for d in _docs() if d["metadata"]["name"].endswith("-recovery")) == \
        [("ConfigMap", REC), ("Deployment", REC)]
    assert _deployment(_docs(), REC)["spec"]["replicas"] == 0


@pytest.mark.parametrize("extra", [{}, OFFSITE], ids=["default", "offsite"])
def test_t532_1_the_switch_changes_only_the_two_deployments_replicas(extra):
    """On and off render the same objects and differ in two fields: the app's replicas (1 -> 0) and the recovery
    workload's (0 -> 1). So both report available, and turning it off needs no pruning (#532)."""
    off = {_key(d): d for d in _docs(**extra)}
    on = {_key(d): d for d in _docs(**extra, **ON)}
    assert set(on) == set(off)
    changed = sorted(k for k in off if off[k] != on[k])
    assert changed == [("Deployment", APP), ("Deployment", REC)], changed
    assert (off[("Deployment", APP)]["spec"]["replicas"], on[("Deployment", APP)]["spec"]["replicas"]) == (1, 0)
    assert (off[("Deployment", REC)]["spec"]["replicas"], on[("Deployment", REC)]["spec"]["replicas"]) == (0, 1)
    for key in changed:
        before, after = off[key], on[key]
        before["spec"].pop("replicas"), after["spec"].pop("replicas")
        assert before == after, key


def test_t532_1_the_recovery_pod_is_the_app_pod_with_the_recovery_branches():
    """The recovery workload's pod spec is the app's except for the dashboard container's command, env, mounts and
    probes, the recovery volumes and the anti-affinity: the oauth-proxy sidecar and everything else are the same."""
    docs = _docs(**OFFSITE)
    app, rec = (_deployment(docs, n)["spec"]["template"]["spec"] for n in (APP, REC))
    assert [c for c in app["containers"] if c["name"] != "dashboard"] == \
           [c for c in rec["containers"] if c["name"] != "dashboard"], "the oauth-proxy sidecar differs"
    assert [v for v in rec["volumes"] if v not in app["volumes"]] == \
           [v for v in rec["volumes"] if v["name"] in ("recovery-script", "offsite")]
    assert all(v in rec["volumes"] for v in app["volumes"])
    rest = lambda pod: {k: v for k, v in pod.items() if k not in ("containers", "volumes", "affinity")}
    assert rest(app) == rest(rec)
    assert _deployment(docs, REC)["spec"]["strategy"] == _deployment(docs)["spec"]["strategy"] == {"type": "Recreate"}


def test_t532_2_no_selector_of_the_app_picks_the_recovery_pod_and_back():
    """The Service, the PodDisruptionBudget, the ServiceMonitor's Service and the app's Deployment select the app's
    pod only; the recovery Deployment selects its own pod only; the report service's NetworkPolicy admits the
    app's pod only (#532)."""
    docs = _docs(**ON)
    pod_labels = {n: _deployment(docs, n)["spec"]["template"]["metadata"]["labels"] for n in (APP, REC)}
    picks = lambda selector, labels: all(labels.get(k) == v for k, v in selector.items())
    service = next(d for d in docs if _key(d) == ("Service", APP))["spec"]["selector"]
    pdb = next(d for d in docs if d["kind"] == "PodDisruptionBudget" and d["metadata"]["name"] == APP)
    selectors = {"Service": service, "PodDisruptionBudget": pdb["spec"]["selector"]["matchLabels"],
                 "app Deployment": _deployment(docs)["spec"]["selector"]["matchLabels"]}
    netpol = next(d for d in docs if d["kind"] == "NetworkPolicy")
    selectors["report NetworkPolicy"] = next(p["podSelector"]["matchLabels"] for rule in netpol["spec"]["ingress"]
                                            for p in rule.get("from", []) if "podSelector" in p
                                            and p["podSelector"].get("matchLabels", {}).get("app") == APP)
    for name, selector in selectors.items():
        assert picks(selector, pod_labels[APP]) and not picks(selector, pod_labels[REC]), name
    recovery = _deployment(docs, REC)["spec"]["selector"]["matchLabels"]
    assert picks(recovery, pod_labels[REC]) and not picks(recovery, pod_labels[APP])
    assert pod_labels[REC]["app"] == REC, "restore-db.sh finds the recovery pod by app=<release>-recovery"


def test_t532_3_each_pod_names_the_other_in_its_own_required_anti_affinity_cluster_wide():
    """Each workload's pod carries one required anti-affinity term against the other's pods, on any node of the
    same OS (every node this image runs on), appended to the values' affinity, in both switch states. Each names
    the other in its OWN terms because the scheduler re-queues a waiting pod on a delete only when the deleted pod
    matches the waiting pod's own anti-affinity (SPEC_E11 note 8): with the term on the recovery pod alone, the app
    pod waited for the 5-minute unschedulable flush (303 s on the lab)."""
    labels = {"app.kubernetes.io/instance": "t", "app.kubernetes.io/name": "group-sync-dashboard"}
    term = {"labelSelector": {"matchLabels": {"app": APP, **labels}}, "topologyKey": "kubernetes.io/os"}
    mirror = {"labelSelector": {"matchLabels": {"app": REC, "app.kubernetes.io/component": "recovery", **labels}},
              "topologyKey": "kubernetes.io/os"}
    for values in ({}, ON):
        docs = _docs(**values)
        assert _deployment(docs, REC)["spec"]["template"]["spec"]["affinity"] == \
            {"podAntiAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": [term]}}
        assert _deployment(docs)["spec"]["template"]["spec"]["affinity"] == \
            {"podAntiAffinity": {"requiredDuringSchedulingIgnoredDuringExecution": [mirror]}}
    zone = {"key": "topology.kubernetes.io/zone", "operator": "In", "values": ["a"]}
    mine = {"labelSelector": {"matchLabels": {"x": "y"}}, "topologyKey": "kubernetes.io/hostname"}
    ok, out = render("--set-json", 'affinity={"nodeAffinity":{"requiredDuringSchedulingIgnoredDuringExecution":'
                     '{"nodeSelectorTerms":[{"matchExpressions":[' + json.dumps(zone) + ']}]}},'
                     '"podAntiAffinity":{"requiredDuringSchedulingIgnoredDuringExecution":[' + json.dumps(mine) + ']}}',
                     **ON)
    assert ok, out
    docs = [d for d in yaml.safe_load_all(out) if d]
    app, rec = (_deployment(docs, n)["spec"]["template"]["spec"]["affinity"] for n in (APP, REC))
    assert app["podAntiAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"] == [mine, mirror]
    assert rec["podAntiAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"] == [mine, term]
    assert rec["nodeAffinity"] == app["nodeAffinity"]


def test_t532_4_same_serviceaccount_and_security_context_and_no_uid_of_its_own():
    """The operator's decision on #532: the same namespace, ServiceAccount and SCC, and no runAsUser, so OpenShift
    assigns the recovery pod the UID it assigns the app's (restricted-v2's range)."""
    docs = _docs(**ON)
    app, rec = (_deployment(docs, n) for n in (APP, REC))
    assert rec["metadata"]["namespace"] == app["metadata"]["namespace"]
    pa, pr = app["spec"]["template"]["spec"], rec["spec"]["template"]["spec"]
    assert pr["serviceAccountName"] == pa["serviceAccountName"] == APP
    assert pr["securityContext"] == pa["securityContext"] and "runAsUser" not in pr["securityContext"]
    for container in pr["containers"]:
        assert "runAsUser" not in (container.get("securityContext") or {}), container["name"]
    assert _container(docs, workload=REC)["securityContext"] == _container(docs)["securityContext"]


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
    volume = next(v for v in _deployment(_docs(**ON), REC)["spec"]["template"]["spec"]["volumes"] if v["name"] == "recovery-script")
    assert volume == {"name": "recovery-script", "configMap": {"name": "t-group-sync-dashboard-recovery", "defaultMode": 0o444}}


@pytest.mark.parametrize("claim,expected", [("", "t-group-sync-dashboard-backup-offsite"), ("my-offsite", "my-offsite")])
def test_the_offsite_claim_is_mounted_read_only_as_the_cronjob_names_it(claim, expected):
    docs = _docs(backup__offsite__destination__pvc__existingClaim=claim, **OFFSITE, **ON)
    pod = _deployment(docs, REC)["spec"]["template"]["spec"]
    assert {"name": "offsite", "persistentVolumeClaim": {"claimName": expected, "readOnly": True}} in pod["volumes"]
    assert {"name": "offsite", "mountPath": "/offsite", "readOnly": True} in _container(docs, workload=REC)["volumeMounts"]
    cronjob = next(d for d in docs if d["kind"] == "CronJob")
    shipped = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]["volumes"]
    assert {"name": "offsite", "persistentVolumeClaim": {"claimName": expected}} in shipped


def test_t532_5_on_a_single_node_claim_the_offsite_copy_runs_beside_either_workloads_pod():
    """On ReadWriteOnce the offsite Job must run on the node that holds the data claim: beside the app's pod, or in
    recovery mode the recovery pod's, as it did when the recovery pod carried the app's labels (#532)."""
    docs = _docs(persistence__accessMode="ReadWriteOnce", reporting__enabled="false", **OFFSITE, **ON)
    cronjob = next(d for d in docs if d["kind"] == "CronJob" and d["metadata"]["name"].endswith("-backup-offsite"))
    (term,) = cronjob["spec"]["jobTemplate"]["spec"]["template"]["spec"]["affinity"]["podAffinity"][
        "requiredDuringSchedulingIgnoredDuringExecution"]
    assert term["topologyKey"] == "kubernetes.io/hostname"
    selector = term["labelSelector"]

    def picks(labels: dict) -> bool:
        return (all(labels.get(k) == v for k, v in selector["matchLabels"].items())
                and all(labels.get(e["key"]) in e["values"] for e in selector["matchExpressions"]))

    for name in (APP, REC):
        assert picks(_deployment(docs, name)["spec"]["template"]["metadata"]["labels"]), name
    job_labels = cronjob["spec"]["jobTemplate"]["spec"]["template"]["metadata"]["labels"]
    assert not picks(job_labels)


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
    mounted = [v["persistentVolumeClaim"]["claimName"] for v in _deployment(docs, REC)["spec"]["template"]["spec"]["volumes"]
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
    assert "every process in the container stops" in comment and "evicted" in comment and "1/1" in comment
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
