from __future__ import annotations

import subprocess

import pytest
import yaml

from test_chart_pdb import CHART, _matches, _render


def _exact(docs: list[dict], kind: str, name: str) -> dict:
    hits = [d for d in docs if d.get("kind") == kind and d.get("metadata", {}).get("name") == name]
    assert len(hits) == 1, (kind, name, [d.get("metadata", {}).get("name") for d in docs if d.get("kind") == kind])
    return hits[0]


@pytest.mark.parametrize("mode", ["ReadWriteOnce", "ReadWriteOncePod"])
def test_reporting_refuses_data_claim_modes_that_do_not_survive_independent_rescheduling(mode):
    done = subprocess.run(["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h",
                           "--set", "reporting.enabled=true", "--set", f"persistence.accessMode={mode}"],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode != 0
    assert "reporting.enabled=true requires persistence.accessMode=ReadWriteMany" in done.stderr and mode in done.stderr


def test_default_reporting_render_is_yaml_and_all_selectors_match_only_their_workloads():
    docs = _render("reporting.enabled=true", "monitoring.serviceMonitor.enabled=true",
                   "reporting.schedules[0].name=weekly", "reporting.schedules[0].schedule=0 6 * * 1",
                   "reporting.schedules[0].report=access-matrix")
    dashboard_name = "t-group-sync-dashboard"; report_name = f"{dashboard_name}-report"
    dashboard = _exact(docs, "Deployment", dashboard_name); report = _exact(docs, "Deployment", report_name)
    service = _exact(docs, "Service", report_name); monitor = _exact(docs, "ServiceMonitor", report_name)
    dashboard_pdb = _exact(docs, "PodDisruptionBudget", dashboard_name); report_pdb = _exact(docs, "PodDisruptionBudget", report_name)
    dl = dashboard["spec"]["template"]["metadata"]["labels"]; rl = report["spec"]["template"]["metadata"]["labels"]
    ds = dashboard_pdb["spec"]["selector"]["matchLabels"]; rs = report_pdb["spec"]["selector"]["matchLabels"]
    assert _matches(ds, dl) and not _matches(ds, rl)
    assert _matches(rs, rl) and not _matches(rs, dl)
    assert _matches(service["spec"]["selector"], rl)
    assert _matches(monitor["spec"]["selector"]["matchLabels"], service["metadata"]["labels"])
    cronjobs = [d for d in docs if d.get("kind") == "CronJob"]
    assert len(cronjobs) == 1
    cl = cronjobs[0]["spec"]["jobTemplate"]["spec"]["template"]["metadata"]["labels"]
    assert not _matches(ds, cl) and not _matches(rs, cl)


def test_the_report_deployment_carries_the_two_tier_retention_env():
    """R2 (#149): these four env vars are the ONLY wiring between values.reporting.retention and the
    service's prune, and nothing else asserted them — a reverted template would have stayed green
    (raised by the adversarial review, Cursor). The removed single-tier names must not come back."""
    docs = _render("reporting.enabled=true")
    report = _exact(docs, "Deployment", "t-group-sync-dashboard-report")
    env = {e["name"]: e.get("value")
           for c in report["spec"]["template"]["spec"]["containers"] for e in c.get("env", [])}
    assert env["GSD_REPORT_SCHEDULED_KEEP_PER_SCHEDULE"] == "2"
    assert env["GSD_REPORT_SCHEDULED_RETENTION_DAYS"] == "90"
    assert env["GSD_REPORT_MANUAL_RETENTION_DAYS"] == "3"
    assert env["GSD_REPORT_MANUAL_RETENTION_MAX_RUNS"] == "500"
    assert "GSD_REPORT_RETENTION_DAYS" not in env, "the single-tier env was replaced, not kept"
    assert "GSD_REPORT_RETENTION_MAX_RUNS" not in env


class UniqueKeyLoader(yaml.SafeLoader):
    """Reject duplicate mapping keys instead of silently taking the last value."""


def _construct_unique_mapping(loader, node, deep=False):
    loader.flatten_mapping(node); result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in result:
            raise yaml.constructor.ConstructorError("while constructing a mapping", node.start_mark,
                                                    f"duplicate YAML key {key!r}", key_node.start_mark)
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping)


def test_report_manifests_have_unique_labels_and_the_service_monitor_selector_matches():
    done = subprocess.run(["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h",
                           "--set", "reporting.enabled=true", "--set", "monitoring.serviceMonitor.enabled=true",
                           "--set", "reporting.schedules[0].name=weekly", "--set", "reporting.schedules[0].schedule=0 6 * * 1",
                           "--set", "reporting.schedules[0].report=access-matrix"], capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    docs = [d for d in yaml.load_all(done.stdout, Loader=UniqueKeyLoader) if d]  # raises on any duplicate key
    service = next(d for d in docs if d.get("kind") == "Service" and d["metadata"]["name"].endswith("-report"))
    labels = service["metadata"]["labels"]
    assert all(labels.get(k) == v for k, v in service["spec"]["selector"].items())
    assert labels["app.kubernetes.io/name"].endswith("-report") and "app" not in labels
    cron = next(d for d in docs if d.get("kind") == "CronJob")
    assert cron["metadata"]["labels"]["app.kubernetes.io/component"] == "report-schedule"


def test_monitoring_ingress_admits_only_prometheus_pods_in_the_configured_namespaces():
    docs = _render("reporting.enabled=true", "monitoring.serviceMonitor.enabled=true")
    policy = _exact(docs, "NetworkPolicy", "t-group-sync-dashboard-report")
    assert policy["spec"]["policyTypes"] == ["Ingress"] and "egress" not in policy["spec"]
    rules = policy["spec"]["ingress"]; assert len(rules) == 2
    peers = rules[1]["from"]
    assert {p["namespaceSelector"]["matchLabels"]["kubernetes.io/metadata.name"] for p in peers} == {"openshift-monitoring", "openshift-user-workload-monitoring"}
    for p in peers:
        assert p["podSelector"] == {"matchLabels": {"app.kubernetes.io/name": "prometheus"}}


def test_report_deployment_does_not_derive_affinity_from_the_data_access_mode():
    template = (CHART / "templates" / "report-deployment.yaml").read_text()
    assert "$mode" not in template and "ReadWriteOnce" not in template
    report = _exact(_render("reporting.enabled=true"), "Deployment", "t-group-sync-dashboard-report")
    assert "affinity" not in report["spec"]["template"]["spec"]


# ----------------------------------------------------------------------------------------------
# The prose list of §9.9, as tests: the default render, every refusal by name, the derivations,
# a schedule, and the namespaces grant.
# ----------------------------------------------------------------------------------------------
from test_chart_strategy import render as _render_text   # (ok, text): for the ConfigMap body and refusals


def _config_data(out: str) -> dict:
    for d in yaml.safe_load_all(out):
        if d and d.get("kind") == "ConfigMap":
            for value in (d.get("data") or {}).values():
                if "loginCaptureSource" in value:
                    return yaml.safe_load(value)
    raise AssertionError("no ConfigMap carries the settings file")


def _container(deployment: dict, name: str) -> dict:
    return next(c for c in deployment["spec"]["template"]["spec"]["containers"] if c["name"] == name)


def _env(container: dict, name: str) -> str | None:
    return next((e.get("value") for e in container.get("env", []) if e["name"] == name), None)


class TestTheDefaultRender:
    def test_every_report_object_renders_and_the_proxy_carries_the_second_upstream(self):
        docs = _render()
        kinds = {(d["kind"], d["metadata"]["name"]) for d in docs}
        for kind in ("Deployment", "Service", "NetworkPolicy", "ServiceAccount", "PodDisruptionBudget"):
            assert (kind, "t-group-sync-dashboard-report") in kinds, kind
        assert ("Secret", "t-group-sync-dashboard-report-token") not in kinds, "0.37.0: minted on the cluster, never rendered (test_chart_secrets_mint.py)"
        # 0.36.1: protected like the data claim — a scheduled report is generated once from its day's
        # snapshot (two-tier retention, #154/#163), so the store is history, not a cache
        pvc = _exact(docs, "PersistentVolumeClaim", "t-group-sync-dashboard-report-artifacts")
        data = _exact(docs, "PersistentVolumeClaim", "t-group-sync-dashboard-data")
        for claim in (pvc, data):
            ann = claim["metadata"]["annotations"]
            assert ann["helm.sh/resource-policy"] == "keep"
            assert ann["argocd.argoproj.io/sync-options"] == "Prune=false,Delete=false,PruneLast=true"
        off = _exact(_render("argocd.preservePVC=false"), "PersistentVolumeClaim", "t-group-sync-dashboard-report-artifacts")
        assert "argocd.argoproj.io/sync-options" not in off["metadata"]["annotations"] and off["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
        service = _exact(docs, "Service", "t-group-sync-dashboard-report")
        assert _matches({"app.kubernetes.io/component": "report"}, service["metadata"]["labels"])
        proxy = _container(_exact(docs, "Deployment", "t-group-sync-dashboard"), "oauth-proxy")
        assert "-upstream=https://t-group-sync-dashboard-report.x.svc:8443/report/" in proxy["args"]
        assert "-upstream-ca=/etc/gsd/service-ca/service-ca.crt" in proxy["args"]
        assert any(m["mountPath"] == "/etc/gsd/service-ca" for m in proxy["volumeMounts"])
        dashboard = _container(_exact(docs, "Deployment", "t-group-sync-dashboard"), "dashboard")
        assert any(m["mountPath"] == "/etc/gsd/report" and m["readOnly"] for m in dashboard["volumeMounts"])

    def test_the_configmap_and_the_report_container_agree(self):
        ok, out = _render_text()
        assert ok, out
        cfg = _config_data(out)
        assert cfg["reportingUrl"] == "https://t-group-sync-dashboard-report.ca-tutorial.svc:8443" or cfg["reportingUrl"].startswith("https://t-group-sync-dashboard-report.")
        assert cfg["reportingSnapshotIntervalSeconds"] == 300 and cfg["reportingCaFile"] == "/etc/gsd/service-ca/service-ca.crt"
        assert cfg["namespacesReadEnabled"] is False
        report = _container(_exact(_render(), "Deployment", "t-group-sync-dashboard-report"), "report")
        enabled = _env(report, "GSD_REPORT_ENABLED_REPORTS").split(",")
        assert len(enabled) == 11 and "login-activity" in enabled, "loginCapture.enabled defaults true since 0.14.0"
        off = _container(_exact(_render("loginCapture.enabled=false"), "Deployment", "t-group-sync-dashboard-report"), "report")
        assert "login-activity" not in _env(off, "GSD_REPORT_ENABLED_REPORTS") and len(_env(off, "GSD_REPORT_ENABLED_REPORTS").split(",")) == 10

    def test_the_data_claim_is_read_only_in_the_report_pod_at_both_levels(self):
        report = _exact(_render(), "Deployment", "t-group-sync-dashboard-report")
        spec = report["spec"]["template"]["spec"]
        data_volume = next(v for v in spec["volumes"] if v["name"] == "data")
        assert data_volume["persistentVolumeClaim"]["readOnly"] is True
        container = _container(report, "report")
        mount = next(m for m in container["volumeMounts"] if m["name"] == "data")
        assert mount["readOnly"] is True
        assert not _matches({"app.kubernetes.io/name": "group-sync-dashboard"}, report["spec"]["template"]["metadata"]["labels"])


class TestRefusals:
    @pytest.mark.parametrize("sets,needle", [
        (("oauthProxy.enabled=false", "visibility.enabled=false"), "requires oauthProxy.enabled=true"),
        (("persistence.enabled=false",), "requires persistence.enabled=true"),
        (("replicaCount=2", "leaderElection.enabled=false"), "requires replicaCount 1"),
        (("rbac.bindings=false",), "requires rbac.bindings=true"),
        (("reporting.snapshot.intervalSeconds=30",), "intervalSeconds must be at least 60"),
        (("reporting.ticket.ttlSeconds=10",), "ttlSeconds must be between 30 and 3600"),
        (("reporting.pdf.variant=pdf/x-1a",), "is not a PDF variant"),
        (("reporting.reports.loginActivity.enabled=true", "loginCapture.enabled=false"), "requires loginCapture.enabled=true"),
        (("reporting.reports.groups.enabled=maybe",), "must be true or false"),
        (("reporting.schedules[0].name=w", "reporting.schedules[0].schedule=0 6 * * 1", "reporting.schedules[0].report=nope"), "is not an enabled catalogue name"),
        (("reporting.image.digest=abc",), "is not a digest"),
        (("rbac.namespaces=true", "reporting.namespaceMetadata.labels[0]=company.net/mnemonic",
          "reporting.namespaceSelector.labels[0]=company.net/nope"), "is not in reporting.namespaceMetadata.labels"),
        (("reporting.namespaceSelector.label=company.net/mnemonic",), "was removed"),
        (("reporting.window.enabled=true", "reporting.window.timezone=UTC", "reporting.window.start=9am"), "is not HH:MM"),
        (("reporting.window.enabled=true", "reporting.window.timezone=UTC", "reporting.window.start=12:00", "reporting.window.end=12:00"), "start and end are equal"),
        (("reporting.window.enabled=true", "reporting.window.timezone=UTC", "reporting.window.days={Funday}"), "is not one of Mon..Sun"),
        (("reporting.window.enabled=true", "reporting.window.timezone=UTC", "reporting.window.days={Mon,Mon}"), "duplicate"),
        (("reporting.window.enabled=true", "reporting.window.timezone=", "timezone="), "needs a timezone"),
    ])
    def test_each_guard_names_its_key(self, sets, needle):
        done = subprocess.run(["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h",
                               *sum((["--set", s] for s in sets), [])], capture_output=True, text=True, timeout=120)
        assert done.returncode != 0, sets
        assert needle in done.stderr, done.stderr[-400:]

    def test_the_removed_singular_label_refuses_only_a_material_value(self):
        # Helm ignores an unknown key, so a stale non-empty reporting.namespaceSelector.label left in a
        # 0.21 values file would render cleanly while the selector silently vanished. The chart refuses a
        # materially-set .label (review 2026-09-16, Fable F2) — but 0.21 shipped `label: ""` as its
        # default, so an empty value stays an allowed no-op, and the removed key is refused even when the
        # new .labels is also present (Codex: refuse only a material value, and refuse first).
        def _run(*sets):
            return subprocess.run(["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h",
                                   *sum((["--set", s] for s in sets), [])], capture_output=True, text=True, timeout=120)
        assert _run("reporting.namespaceSelector.label=").returncode == 0            # the 0.21 no-op default
        material = _run("reporting.namespaceSelector.label=company.net/mnemonic")
        assert material.returncode != 0 and "was removed" in material.stderr, material.stderr[-400:]
        both = _run("rbac.namespaces=true", "reporting.namespaceMetadata.labels[0]=company.net/mnemonic",
                    "reporting.namespaceSelector.labels[0]=company.net/mnemonic",
                    "reporting.namespaceSelector.label=company.net/mnemonic")
        assert both.returncode != 0 and "was removed" in both.stderr, both.stderr[-400:]


class TestDerivations:
    def test_tls_off_drops_the_ca_and_the_certificate_and_speaks_http(self):
        docs = _render("reporting.tls.enabled=false")
        proxy = _container(_exact(docs, "Deployment", "t-group-sync-dashboard"), "oauth-proxy")
        assert not any(a.startswith("-upstream-ca") for a in proxy["args"])
        assert any(a.startswith("-upstream=http://t-group-sync-dashboard-report.") for a in proxy["args"])
        report = _exact(docs, "Deployment", "t-group-sync-dashboard-report")
        assert not any(v["name"] == "tls" for v in report["spec"]["template"]["spec"]["volumes"])
        ok, out = _render_text(reporting__tls__enabled="false")
        cfg = _config_data(out)
        assert cfg["reportingUrl"].startswith("http://") and cfg["reportingCaFile"] == ""

    def test_monitoring_adds_the_ingress_rule_the_second_monitor_and_two_rules(self):
        docs = _render("monitoring.serviceMonitor.enabled=true", "monitoring.prometheusRule.enabled=true")
        monitors = [d["metadata"]["name"] for d in docs if d.get("kind") == "ServiceMonitor"]
        assert sorted(monitors) == ["t-group-sync-dashboard", "t-group-sync-dashboard-report"]
        rules = [r["alert"] for d in docs if d.get("kind") == "PrometheusRule" for g in d["spec"]["groups"] for r in g["rules"] if "alert" in r]
        assert {"GroupSyncDashboardReportUsagePullFailing", "GroupSyncDashboardReportSnapshotStale"} <= set(rules)
        policy = _exact(docs, "NetworkPolicy", "t-group-sync-dashboard-report")
        assert len(policy["spec"]["ingress"]) == 2
        without = _exact(_render("monitoring.serviceMonitor.enabled=false"), "NetworkPolicy", "t-group-sync-dashboard-report")
        assert len(without["spec"]["ingress"]) == 1

    def test_off_renders_none_of_it(self):
        docs = _render("reporting.enabled=false", "monitoring.prometheusRule.enabled=true", "monitoring.serviceMonitor.enabled=true")
        # `report-auditor` is the rbacAuditors ClusterRole (on by default), gated by rbacAuditors.enabled
        # not reporting.enabled — it shares the "report" prefix but is not a reporting object.
        assert not [d for d in docs if d["metadata"]["name"].startswith("t-group-sync-dashboard-report")
                    and "report-auditor" not in d["metadata"]["name"]]
        proxy = _container(_exact(docs, "Deployment", "t-group-sync-dashboard"), "oauth-proxy")
        assert not any("report" in a for a in proxy["args"])
        rules = [r["alert"] for d in docs if d.get("kind") == "PrometheusRule" for g in d["spec"]["groups"] for r in g["rules"] if "alert" in r]
        assert not any("Report" in r for r in rules)
        ok, out = _render_text(reporting__enabled="false")
        assert "reportingUrl" not in out

    def test_the_window_renders_env_and_the_cronjob_timezone(self):
        docs = _render("reporting.window.enabled=true", "reporting.window.timezone=America/New_York",
                       "reporting.schedules[0].name=nightly", "reporting.schedules[0].schedule=0 22 * * *",
                       "reporting.schedules[0].report=groups", "reporting.schedules[0].cluster=crc-local")
        report = _container(_exact(docs, "Deployment", "t-group-sync-dashboard-report"), "report")
        assert _env(report, "GSD_REPORT_WINDOW_ENABLED") == "true"
        assert _env(report, "GSD_REPORT_WINDOW_TIMEZONE") == "America/New_York"     # window.timezone wins
        cron = _exact(docs, "CronJob", "t-group-sync-dashboard-report-nightly")
        assert cron["spec"]["timeZone"] == "America/New_York"                       # cron and window agree
        docs_off = _render("reporting.schedules[0].name=nightly", "reporting.schedules[0].schedule=0 22 * * *",
                           "reporting.schedules[0].report=groups", "reporting.schedules[0].cluster=crc-local")
        report_off = _container(_exact(docs_off, "Deployment", "t-group-sync-dashboard-report"), "report")
        assert _env(report_off, "GSD_REPORT_WINDOW_ENABLED") == "false"
        assert "timeZone" not in _exact(docs_off, "CronJob", "t-group-sync-dashboard-report-nightly")["spec"]

    def test_the_window_timezone_falls_back_to_values_timezone(self):
        docs = _render("reporting.window.enabled=true", "timezone=Europe/Paris", "reporting.window.days={Mon}")
        report = _container(_exact(docs, "Deployment", "t-group-sync-dashboard-report"), "report")
        assert _env(report, "GSD_REPORT_WINDOW_TIMEZONE") == "Europe/Paris"          # empty window.timezone -> .Values.timezone

    def test_a_schedule_renders_one_cronjob_with_the_trigger_command(self):
        docs = _render("reporting.schedules[0].name=weekly", "reporting.schedules[0].schedule=0 6 * * 1",
                       "reporting.schedules[0].report=access-matrix", "reporting.schedules[0].cluster=crc-local",
                       "reporting.schedules[0].params.subject_kind=groups", "reporting.schedules[0].formats[0]=html")
        cron = _exact(docs, "CronJob", "t-group-sync-dashboard-report-weekly")
        pod = cron["spec"]["jobTemplate"]["spec"]["template"]
        assert pod["metadata"]["labels"]["app.kubernetes.io/component"] == "report-schedule"
        command = " ".join(pod["spec"]["containers"][0]["command"] + pod["spec"]["containers"][0].get("args", []))
        # P2: params ride as one --params-json JSON object, not repeated --param k=v (Helm %v is not JSON).
        # A pinned cluster and an explicit format still pass through (#149 R1/R3).
        for piece in ("--report access-matrix", "--cluster crc-local", "--schedule weekly", "--wait",
                      "--params-json", '"subject_kind":"groups"', "--format html"):
            assert piece in command, (piece, command)
        assert "suspend" not in cron["spec"]
        # never retried by Kubernetes (review of PR #220, OB3): a retry re-POSTs the whole fan-out
        assert cron["spec"]["jobTemplate"]["spec"]["backoffLimit"] == 0
        assert "--timeout" in command and "840" in command

    def test_a_schedule_is_cluster_agnostic_by_default_and_names_no_format(self):
        # #149 R1/R3: no `cluster`, no `formats` — the service fans out over its snapshot's clusters and
        # defaults the formats by origin; the trigger receives neither flag.
        docs = _render("reporting.schedules[0].name=nightly", "reporting.schedules[0].schedule=0 2 * * *",
                       "reporting.schedules[0].report=namespace-access")
        cron = _exact(docs, "CronJob", "t-group-sync-dashboard-report-nightly")
        command = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["command"]
        assert "--cluster" not in command and "--format" not in command, command
        assert "suspend" not in cron["spec"]

    def test_a_disabled_schedule_is_suspended_not_removed(self):
        # #149 R4: enabled: false keeps the CronJob (definition, history, audit) and sets spec.suspend.
        docs = _render("reporting.schedules[0].name=paused", "reporting.schedules[0].schedule=0 2 * * *",
                       "reporting.schedules[0].report=groups", "reporting.schedules[0].enabled=false")
        cron = _exact(docs, "CronJob", "t-group-sync-dashboard-report-paused")
        assert cron["spec"]["suspend"] is True
        docs = _render("reporting.schedules[0].name=live", "reporting.schedules[0].schedule=0 2 * * *",
                       "reporting.schedules[0].report=groups", "reporting.schedules[0].enabled=true")
        assert "suspend" not in _exact(docs, "CronJob", "t-group-sync-dashboard-report-live")["spec"]

    def test_a_quoted_false_suspends_too_and_json_never_reaches_the_trigger(self):
        # Review of PR #220 (Codex, Grok): `--set-string enabled=false` is a non-empty string, truthy to
        # Go templates — `not` left the paused schedule firing (the window's own scar). The word false
        # suspends whatever its type. And a `formats: [json]` entry is not a --format the trigger takes.
        done = subprocess.run(["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h",
                               "--set", "reporting.enabled=true", "--set", "reporting.schedules[0].name=paused",
                               "--set", "reporting.schedules[0].schedule=0 2 * * *",
                               "--set", "reporting.schedules[0].report=groups",
                               "--set", "reporting.schedules[0].formats[0]=json", "--set", "reporting.schedules[0].formats[1]=html",
                               "--set-string", "reporting.schedules[0].enabled=false"],
                              capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stderr
        docs = [d for d in yaml.safe_load_all(done.stdout) if d]
        cron = _exact(docs, "CronJob", "t-group-sync-dashboard-report-paused")
        assert cron["spec"]["suspend"] is True
        command = cron["spec"]["jobTemplate"]["spec"]["template"]["spec"]["containers"][0]["command"]
        assert command.count("--format") == 1 and "json" not in command and "html" in command
    def test_the_schedules_reach_the_report_pod_as_json(self):
        # #149 R6: the status page reads cadence, enabled and retention from the chart's own values.
        import json as _json
        env = {e["name"]: e.get("value") for d in _render(
            "reporting.schedules[0].name=quarterly", r"reporting.schedules[0].schedule=0 6 1 1\,4\,7\,10 *",
            "reporting.schedules[0].report=compliance-snapshot", "reporting.schedules[0].retention.keepPerSchedule=12",
            "reporting.schedules[1].name=paused", r"reporting.schedules[1].schedule=0 6 1\,16 * *",
            "reporting.schedules[1].report=namespace-access", "reporting.schedules[1].enabled=false",
            "reporting.schedules[1].params.foo=bar")
            if d.get("kind") == "Deployment" and d["metadata"]["name"].endswith("-report")
            for e in d["spec"]["template"]["spec"]["containers"][0]["env"]}
        got = _json.loads(env["GSD_REPORT_SCHEDULES"])
        assert got == [
            {"name": "quarterly", "schedule": "0 6 1 1,4,7,10 *", "report": "compliance-snapshot", "retention": {"keepPerSchedule": 12}},
            {"name": "paused", "schedule": "0 6 1,16 * *", "report": "namespace-access", "enabled": False},
        ], got                                                    # params stay out; enabled only when set
        assert _json.loads({e["name"]: e.get("value") for d in _render() if d.get("kind") == "Deployment" and d["metadata"]["name"].endswith("-report")
                            for e in d["spec"]["template"]["spec"]["containers"][0]["env"]}["GSD_REPORT_SCHEDULES"]) == []

    def test_the_exact_group_label_reaches_both_pods_and_needs_the_namespaces_grant(self):
        # #149 R7: the report pod resolves mnemonics through it; the poller captures it as a third label
        # whether or not the operator listed it; without the Namespace grant it is refused like the labels.
        docs = _render("rbac.namespaces=true", "reporting.namespaceGroupLabel=company.net/oud-group",
                       "reporting.namespaceMetadata.labels[0]=company.net/mnemonic")
        report = {e["name"]: e.get("value") for d in docs if d.get("kind") == "Deployment" and d["metadata"]["name"].endswith("-report")
                  for e in d["spec"]["template"]["spec"]["containers"][0]["env"]}
        assert report["GSD_REPORT_NAMESPACE_GROUP_LABEL"] == "company.net/oud-group"
        ok, out = _render_text(rbac__namespaces="true", reporting__namespaceGroupLabel="company.net/oud-group",
                               **{"reporting.namespaceMetadata.labels[0]": "company.net/mnemonic"})
        assert ok, out
        assert _config_data(out)["namespaceMetadataLabels"] == ["company.net/mnemonic", "company.net/oud-group"]
        ok, out = _render_text(rbac__namespaces="true", reporting__namespaceGroupLabel="company.net/mnemonic",
                               **{"reporting.namespaceMetadata.labels[0]": "company.net/mnemonic"})
        assert _config_data(out)["namespaceMetadataLabels"] == ["company.net/mnemonic"], "already listed: not appended twice"
        ok, out = _render_text(reporting__namespaceGroupLabel="company.net/oud-group")
        assert not ok and "namespaceGroupLabel is set but rbac.namespaces is false" in out
    def test_a_quoted_false_pauses_the_cronjob_and_the_status_page_alike(self):
        # Review of #221 (OB3): report-cronjob.yaml suspends on the literal word false (a quoted "false" or a
        # --set-string is a non-empty string), and the service reads `enabled` as a boolean. Rendered as the
        # value itself, "false" reached the pod as the string "false", which `is not False` — the page said On
        # with a next fire, above a CronJob that would never fire. The helper now emits the CronJob's decision.
        import json as _json, subprocess as _sp
        done = _sp.run(["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h", "--set", "reporting.enabled=true",
                        "--set", "persistence.accessMode=ReadWriteMany",
                        "--set", "reporting.schedules[0].name=a", "--set", "reporting.schedules[0].schedule=0 6 * * *",
                        "--set", "reporting.schedules[0].report=groups", "--set-string", "reporting.schedules[0].enabled=false"],
                       capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stderr
        import yaml as _yaml
        docs = [d for d in _yaml.safe_load_all(done.stdout) if d]
        cron = next(d for d in docs if d.get("kind") == "CronJob")
        env = {e["name"]: e.get("value") for d in docs if d.get("kind") == "Deployment" and d["metadata"]["name"].endswith("-report")
               for e in d["spec"]["template"]["spec"]["containers"][0]["env"]}
        assert cron["spec"]["suspend"] is True
        assert _json.loads(env["GSD_REPORT_SCHEDULES"]) == [{"name": "a", "schedule": "0 6 * * *", "report": "groups", "enabled": False}]

    def test_the_origin_formats_reach_the_report_pod(self):
        env = {e["name"]: e.get("value") for d in _render() if d.get("kind") == "Deployment" and d["metadata"]["name"].endswith("-report")
               for e in d["spec"]["template"]["spec"]["containers"][0]["env"]}
        assert env["GSD_REPORT_FORMATS_SCHEDULED"] == "html,json" and env["GSD_REPORT_FORMATS_MANUAL"] == "html,json,pdf"
        env = {e["name"]: e.get("value") for d in _render("reporting.formats.scheduled[0]=html", "reporting.formats.scheduled[1]=pdf")
               if d.get("kind") == "Deployment" and d["metadata"]["name"].endswith("-report")
               for e in d["spec"]["template"]["spec"]["containers"][0]["env"]}
        assert env["GSD_REPORT_FORMATS_SCHEDULED"] == "html,pdf"

    def test_the_namespaces_grant_follows_its_switch(self):
        rules = [r for d in _render("rbac.namespaces=true") if d.get("kind") == "ClusterRole" and d["metadata"]["name"] == "t-group-sync-dashboard-reader" for r in d["rules"]]
        assert any(r.get("resources") == ["namespaces"] and r.get("verbs") == ["get", "list"] and r.get("apiGroups") == [""] for r in rules)
        rules = [r for d in _render() if d.get("kind") == "ClusterRole" and d["metadata"]["name"] == "t-group-sync-dashboard-reader" for r in d["rules"]]
        assert not any(r.get("resources") == ["namespaces"] for r in rules)
        ok, out = _render_text(rbac__namespaces="true")
        assert _config_data(out)["namespacesReadEnabled"] is True


def test_a_quoted_false_window_neither_gates_nor_sets_the_cron_timezone():
    """A quoted "false" (or --set-string) is a non-empty, truthy string, which Go-template truthiness
    read as ON: spec.timeZone appeared on the CronJob and the guard validated a window the app treats
    as DISABLED (review of P4, C6/F3). gsd.reportWindowEnabled accepts exactly the report service's
    _bool_env spellings and refuses the rest, so the three call sites cannot disagree."""
    done = subprocess.run(["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h",
                           "--set", "reporting.enabled=true", "--set", "reporting.schedules[0].name=nightly",
                           "--set", "reporting.schedules[0].schedule=30 22 * * *",
                           "--set", "reporting.schedules[0].report=access-matrix",
                           "--set-string", "reporting.window.enabled=false"],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    docs = [d for d in yaml.safe_load_all(done.stdout) if d]
    assert "timeZone" not in _exact(docs, "CronJob", "t-group-sync-dashboard-report-nightly")["spec"]
    report = _container(_exact(docs, "Deployment", "t-group-sync-dashboard-report"), "report")
    assert _env(report, "GSD_REPORT_WINDOW_ENABLED") == "false"


def test_a_misspelt_window_enabled_refuses_the_render():
    done = subprocess.run(["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h",
                           "--set", "reporting.enabled=true", "--set-string", "reporting.window.enabled=flase"],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode != 0
    assert "is not a boolean" in done.stderr
