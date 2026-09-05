"""The shipped Grafana dashboard: parses, references only metrics the collector declares,
carries the shipped alert thresholds, and reaches the cluster byte-identical.

Why byte-identity is asserted against a real `helm template` rather than assumed: the JSON
contains `$cluster`, `${DS_PROMETHEUS}`, `$__rate_interval` and `{{cluster}}` legend
formats — everything Helm would mangle if the file were inlined into a template. It is
loaded with .Files.Get, which Helm never templates; this file is what proves that stays true.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess
from datetime import timedelta

import pytest
import yaml
from prometheus_client import CollectorRegistry, generate_latest

from gsd.metrics import DashboardCollector
from gsd.store import Store

REPO = pathlib.Path(__file__).resolve().parents[2]
CHART = REPO / "charts" / "group-sync-dashboard"
DASHBOARD = CHART / "dashboards" / "group-sync-dashboard.json"
VALUES = CHART / "values.yaml"

needs_helm = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")


def _render(*sets: str) -> list[dict]:
    args = ["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h"]
    for s in sets:
        args += ["--set", s]
    done = subprocess.run(args, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    return [d for d in yaml.safe_load_all(done.stdout) if d]


def _dashboard_configmaps(docs: list[dict]) -> list[dict]:
    return [d for d in docs
            if d.get("kind") == "ConfigMap" and d["metadata"]["name"].endswith("-grafana-dashboard")]


def _walk_panels(panels: list[dict]):
    for p in panels:
        yield p
        yield from _walk_panels(p.get("panels", []))


def _exprs(board: dict) -> list[str]:
    out = []
    for p in _walk_panels(board["panels"]):
        for t in p.get("targets", []):
            if t.get("expr"):
                out.append(t["expr"])
    for v in board["templating"]["list"]:
        q = v.get("query")
        if isinstance(q, dict):
            q = q.get("query")
        if isinstance(q, str) and "gsd_" in q:
            out.append(q)
    return out


class TestTheFile:
    def test_parses_and_is_canonically_formatted(self):
        text = DASHBOARD.read_text()
        board = json.loads(text)
        assert board["uid"] == "gsd-group-sync-dashboard", "the uid is what makes re-imports update in place"
        assert board["schemaVersion"] >= 39
        assert "\t" not in text
        assert not [ln for ln in text.splitlines() if ln != ln.rstrip()], "trailing whitespace would survive `indent` and break byte-identity"
        assert text.endswith("}\n") and not text.endswith("\n\n")

    def test_every_metric_referenced_is_declared_by_the_collector(self):
        """The rule tests' guard, applied to panels: a panel over a metric nobody emits is
        a permanent 'No data' that reads as an outage."""
        referenced = set()
        for expr in _exprs(json.loads(DASHBOARD.read_text())):
            referenced |= set(re.findall(r"\bgsd_[a-z0-9_]+", expr))
        assert referenced, "no gsd_ metrics found in any expr; the probe itself is broken"

        store = Store(":memory:")
        try:
            registry = CollectorRegistry()
            registry.register(DashboardCollector(store, timedelta(seconds=120), None))
            text = generate_latest(registry).decode()
        finally:
            store.close()
        declared = {line.split()[2] for line in text.splitlines() if line.startswith("# HELP")}
        assert not (referenced - declared), f"dashboard references undeclared metrics: {referenced - declared}"

    def test_panel_thresholds_equal_the_shipped_alert_thresholds(self):
        """The board hard-codes values.yaml's prometheusRule defaults; this holds them together."""
        rule = yaml.safe_load(VALUES.read_text())["monitoring"]["prometheusRule"]
        board = json.loads(DASHBOARD.read_text())
        by_title = {p["title"]: p for p in _walk_panels(board["panels"])}

        def red_step(title: str) -> float:
            steps = by_title[title]["fieldConfig"]["defaults"]["thresholds"]["steps"]
            return next(s["value"] for s in steps if s["color"] == "red")

        assert red_step("Last poll age") == rule["notPollingSeconds"]
        assert red_step("GroupSync last-sync age per CR") == rule["overdueSeconds"]
        assert red_step("SQLite WAL size") == rule["walMiB"] * 1024 * 1024
        assert red_step("Login capture: last successful read age") == rule["captureStalledSeconds"]
        assert red_step("Backup age") == rule["backupStaleSeconds"]

    def test_the_text_panel_names_every_shipped_alert(self):
        monitoring = (CHART / "templates" / "monitoring.yaml").read_text()
        shipped = set(re.findall(r"- alert: (\w+)", monitoring))
        board = json.loads(DASHBOARD.read_text())
        text_panel = next(p for p in _walk_panels(board["panels"]) if p["type"] == "text")
        missing = {a for a in shipped if f"`{a}`" not in text_panel["options"]["content"]}
        assert not missing, f"text panel does not name: {missing}"

    def test_nodata_does_not_use_a_verdict_colour_as_the_base_step(self):
        """No series is not DOWN, WAL-off, split-brain, "just polled" or "zero empty groups". The
        reference screenshot is the scar twice over: three stats painted No data red, and after that
        fix six more still painted it green (review, PR #74, both passes). Every coloured stat and
        bar-gauge panel's base step is neutral; a real zero earns its green from the next step."""
        board = json.loads(DASHBOARD.read_text())
        seen = set()
        for p in _walk_panels(board["panels"]):
            if p["type"] not in ("stat", "bargauge") or (p.get("options") or {}).get("colorMode") == "none":
                continue
            defaults = (p.get("fieldConfig") or {}).get("defaults") or {}
            steps = (defaults.get("thresholds") or {}).get("steps") or []
            if not steps:
                continue
            seen.add(p["title"])
            for step_list in [steps] + [pr["value"]["steps"] for ov in (p["fieldConfig"].get("overrides") or [])
                                         for pr in ov.get("properties", []) if pr.get("id") == "thresholds"]:
                base = step_list[0]
                assert base.get("value") is None
                assert base["color"] not in ("red", "green"), f"{p['title']} paints No data as {base['color']}"
        for title in ("Cluster up", "WAL mode", "Leader replicas", "Last poll age", "Poll duration", "Empty groups",
                      "Unattributed groups", "Backup age", "Login capture: last successful read age",
                      "Alerts by kind and severity"):
            assert title in seen, f"{title} was not checked; the probe missed it"

    def test_readme_does_not_treat_folder_as_a_namespace_fix(self):
        """B3.9: folder/labels cannot fix sidecar namespace scope, and the operator recipe that worked
        on the reference cluster needed allowCrossNamespaceImport (review, PR #74)."""
        text = (CHART / "README.md").read_text()
        start = text.index("#### The Grafana dashboard")
        section = text[start:text.index("### ArgoCD", start)]
        assert "set a folder and label your sidecar recognises" not in section
        assert "cannot widen that" in section
        assert "grafana:\n  sidecar:\n    dashboards:\n      searchNamespace: ALL" in section
        assert "allowCrossNamespaceImport: true" in section and "configMapRef:" in section
        # the operator recipe binds the datasource input; otherwise Grafana picks the first Prometheus
        assert "inputName: DS_PROMETHEUS" in section and "datasourceName:" in section

    def test_every_panel_promql_expression_parses_with_promtool(self):
        """Grafana macros expanded to representative values, then Prometheus's own parser. Locally
        the test skips without promtool; CI installs it and must run it (review, PR #74)."""
        import os
        promtool = shutil.which("promtool")
        if promtool is None:
            if os.environ.get("CI"):
                pytest.fail("CI must install promtool; PromQL syntax validation must not skip there")
            pytest.skip("promtool not installed")
        board = json.loads(DASHBOARD.read_text())
        exprs = [t["expr"] for p in _walk_panels(board["panels"]) for t in p.get("targets", []) if t.get("expr")]
        rules = {"groups": [{"name": "grafana-dashboard-promql", "rules": [
            {"record": f"gsd_dashboard_expr_{i:03d}",
             "expr": e.replace("$__rate_interval", "5m").replace("$cluster", ".*")}
            for i, e in enumerate(exprs, start=1)]}]}
        done = subprocess.run([promtool, "check", "rules", "/dev/stdin"], input=yaml.safe_dump(rules),
                              capture_output=True, text=True, timeout=120)
        assert done.returncode == 0, done.stdout + done.stderr

    def test_a_cluster_variable_scopes_the_per_cluster_panels(self):
        board = json.loads(DASHBOARD.read_text())
        names = {v["name"] for v in board["templating"]["list"]}
        assert {"DS_PROMETHEUS", "cluster"} <= names
        cluster_var = next(v for v in board["templating"]["list"] if v["name"] == "cluster")
        assert "label_values(gsd_cluster_up, cluster)" in json.dumps(cluster_var)
        assert cluster_var["includeAll"] and cluster_var["multi"]


@needs_helm
class TestTheConfigMap:
    def test_off_by_default_because_the_servicemonitor_is(self):
        assert not _dashboard_configmaps(_render())

    def test_follows_the_servicemonitor_when_left_empty(self):
        docs = _render("monitoring.serviceMonitor.enabled=true")
        cms = _dashboard_configmaps(docs)
        assert len(cms) == 1
        assert cms[0]["metadata"]["labels"]["grafana_dashboard"] == "1"
        assert "grafana_folder" not in (cms[0]["metadata"].get("annotations") or {})

    def test_explicit_true_ships_it_without_the_servicemonitor(self):
        docs = _render("monitoring.grafanaDashboard.enabled=true")
        assert _dashboard_configmaps(docs)
        assert not [d for d in docs if d.get("kind") == "ServiceMonitor"]

    def test_explicit_false_withholds_it_with_the_servicemonitor_on(self):
        docs = _render("monitoring.serviceMonitor.enabled=true",
                       "monitoring.grafanaDashboard.enabled=false")
        assert not _dashboard_configmaps(docs)

    def test_a_typo_refuses_the_render(self):
        args = ["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h",
                "--set-string", "monitoring.grafanaDashboard.enabled=ture"]
        done = subprocess.run(args, capture_output=True, text=True, timeout=120)
        assert done.returncode != 0
        assert "monitoring.grafanaDashboard.enabled" in done.stderr

    def test_folder_and_extra_labels_land(self):
        docs = _render("monitoring.grafanaDashboard.enabled=true",
                       "monitoring.grafanaDashboard.folder=Access",
                       "monitoring.grafanaDashboard.labels.team=platform")
        cm = _dashboard_configmaps(docs)[0]
        assert cm["metadata"]["annotations"]["grafana_folder"] == "Access"
        assert cm["metadata"]["labels"]["team"] == "platform"

    def test_a_missing_dashboard_map_follows_the_servicemonitor(self):
        """`--set monitoring.grafanaDashboard=null` died on `.labels` of nil (review, PR #74)."""
        assert not _dashboard_configmaps(_render("monitoring.grafanaDashboard=null"))
        docs = _render("monitoring.serviceMonitor.enabled=true", "monitoring.grafanaDashboard=null")
        cms = _dashboard_configmaps(docs)
        assert len(cms) == 1 and cms[0]["metadata"]["labels"]["grafana_dashboard"] == "1"

    def test_a_colliding_sidecar_label_refuses_the_render(self):
        """Extra labels are for a different key; overwriting grafana_dashboard would drop the
        convention value and the sidecar would ignore the ConfigMap (review, PR #74)."""
        args = ["helm", "template", "t", str(CHART), "-n", "x", "--set", "ingress.host=h",
                "--set", "monitoring.grafanaDashboard.enabled=true",
                "--set", "monitoring.grafanaDashboard.labels.grafana_dashboard=0"]
        done = subprocess.run(args, capture_output=True, text=True, timeout=120)
        assert done.returncode != 0, done.stdout
        assert "grafana_dashboard" in done.stderr

    def test_rendered_configmap_json_is_byte_identical_to_the_file(self):
        """No Helm mangling: the `$cluster` / `{{cluster}}` strings survive, and the block
        scalar's chomping reproduces the file's single trailing newline exactly. If this
        ever fails on the final newline alone, switch the template to `| quote` — Go %q
        into a YAML double-quoted scalar is also lossless for this file."""
        cm = _dashboard_configmaps(_render("monitoring.grafanaDashboard.enabled=true"))[0]
        rendered = cm["data"]["group-sync-dashboard.json"]
        assert rendered == DASHBOARD.read_text()
        assert json.loads(rendered)["uid"] == "gsd-group-sync-dashboard"
