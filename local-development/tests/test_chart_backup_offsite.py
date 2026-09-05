"""The off-volume backup CronJob renders only when asked, and refuses the combinations that
could never work.

These shell out to `helm template` because the guards ARE Helm templating; the rendered
objects are what ships. The script the ConfigMap carries is tested on its own in
tests/test_offsite_backup_script.py.
"""

from __future__ import annotations

import pathlib
import shutil
import subprocess

import pytest
import yaml

CHART = pathlib.Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard"
SCRIPT = CHART / "scripts" / "offsite_backup.py"

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not installed")

ON = {"backup__offsite__enabled": "true"}
S3 = {
    **ON,
    "backup__offsite__destination__type": "s3",
    "backup__offsite__destination__s3__existingSecret": "backup-creds",
    "backup__offsite__destination__s3__image__repository": "public.ecr.aws/aws-cli/aws-cli",
    "backup__offsite__destination__s3__image__tag": "2.17.0",
}


def render(**values):
    """Render the chart. Returns (ok, combined output). `__` in a key is `.`."""
    args = ["helm", "template", "t", str(CHART), "--set", "ingress.host=t.example.com"]
    for key, value in values.items():
        args += ["--set", f"{key.replace('__', '.')}={value}"]
    done = subprocess.run(args, capture_output=True, text=True)
    return done.returncode == 0, done.stdout + done.stderr


def _docs(out):
    return [d for d in yaml.safe_load_all(out) if d]


def _one(docs, kind, suffix="-backup-offsite"):
    found = [d for d in docs if d.get("kind") == kind and d["metadata"]["name"].endswith(suffix)]
    assert len(found) == 1, f"expected one {kind} named *{suffix}, found {len(found)}"
    return found[0]


def _pod(cronjob):
    return cronjob["spec"]["jobTemplate"]["spec"]["template"]


class TestSwitch:
    def test_nothing_renders_by_default(self):
        ok, out = render()
        assert ok, out
        assert "backup-offsite" not in out
        assert not [d for d in _docs(out) if d.get("kind") == "CronJob"]

    def test_enabled_renders_the_four_objects(self):
        ok, out = render(**ON)
        assert ok, out
        docs = _docs(out)
        for kind in ("CronJob", "ConfigMap", "ServiceAccount", "PersistentVolumeClaim"):
            _one(docs, kind)

    def test_the_configmap_carries_the_script_verbatim(self):
        ok, out = render(**ON)
        assert ok, out
        cm = _one(_docs(out), "ConfigMap")
        assert cm["data"]["offsite_backup.py"].strip() == SCRIPT.read_text().strip()

    def test_the_serviceaccount_has_no_token_and_no_grant(self):
        ok, out = render(**ON)
        assert ok, out
        docs = _docs(out)
        sa = _one(docs, "ServiceAccount")
        assert sa.get("automountServiceAccountToken") is False
        for d in docs:
            if d.get("kind") in ("RoleBinding", "ClusterRoleBinding"):
                for s in d.get("subjects") or []:
                    assert s.get("name") != sa["metadata"]["name"], "the backup account was granted something"

    def test_backup_enabled_is_refused_as_the_wrong_key(self):
        ok, out = render(backup__enabled="true")
        assert not ok and "config.backup.enabled" in out and "backup.offsite.enabled" in out


class TestPvcDestination:
    def test_data_claim_is_mounted_read_only_twice(self):
        ok, out = render(**ON)
        assert ok, out
        pod = _pod(_one(_docs(out), "CronJob"))
        data = [v for v in pod["spec"]["volumes"] if v["name"] == "data"][0]
        assert data["persistentVolumeClaim"]["readOnly"] is True
        assert data["persistentVolumeClaim"]["claimName"].endswith("-data")
        (ship,) = pod["spec"]["containers"]
        mount = [m for m in ship["volumeMounts"] if m["name"] == "data"][0]
        assert mount["readOnly"] is True and mount["mountPath"] == "/data"

    def test_it_runs_the_dashboard_image_with_the_script(self):
        ok, out = render(**ON)
        assert ok, out
        docs = _docs(out)
        dashboard = [d for d in docs if d.get("kind") == "Deployment"][0]
        image = [c for c in dashboard["spec"]["template"]["spec"]["containers"]
                 if c["name"] == "dashboard"][0]["image"]
        (ship,) = _pod(_one(docs, "CronJob"))["spec"]["containers"]
        assert ship["image"] == image
        assert ship["command"][:2] == ["python3.14", "/scripts/offsite_backup.py"]
        assert ship["command"][ship["command"].index("--source") + 1] == "/data/backup"
        assert ship["command"][ship["command"].index("--keep") + 1] == "14"
        assert ship["securityContext"]["readOnlyRootFilesystem"] is True

    def test_the_pod_does_not_match_the_service_selector(self):
        """A Job pod with no readiness probe is Ready as soon as it runs; carrying the
        selector labels would put it behind the Service for the length of the copy."""
        ok, out = render(**ON)
        assert ok, out
        docs = _docs(out)
        selector = [d for d in docs if d.get("kind") == "Service"][0]["spec"]["selector"]
        labels = _pod(_one(docs, "CronJob"))["metadata"]["labels"]
        assert any(labels.get(k) != v for k, v in selector.items())
        # Stronger than "one label differs": the two keys that would route traffic are absent or
        # different, so adding `app:` by mistake would fail here (review of B1).
        assert "app" not in labels
        assert labels["app.kubernetes.io/name"] != selector["app.kubernetes.io/name"]

    def test_the_destination_claim_survives_uninstall(self):
        ok, out = render(**ON)
        assert ok, out
        pvc = _one(_docs(out), "PersistentVolumeClaim")
        assert pvc["metadata"]["annotations"]["helm.sh/resource-policy"] == "keep"
        assert pvc["spec"]["accessModes"] == ["ReadWriteOnce"]

    def test_an_existing_claim_is_referenced_not_created(self):
        ok, out = render(**ON, backup__offsite__destination__pvc__existingClaim="mine")
        assert ok, out
        docs = _docs(out)
        assert not [d for d in docs if d.get("kind") == "PersistentVolumeClaim"
                    and d["metadata"]["name"].endswith("-backup-offsite")]
        pod = _pod(_one(docs, "CronJob"))
        offsite = [v for v in pod["spec"]["volumes"] if v["name"] == "offsite"][0]
        assert offsite["persistentVolumeClaim"]["claimName"] == "mine"

    def test_the_data_claim_as_destination_is_refused(self):
        ok, out = render(**ON, backup__offsite__destination__pvc__existingClaim="t-group-sync-dashboard-data")
        assert not ok and "is the data claim itself" in out

    def test_negative_keep_is_refused(self):
        ok, out = render(**ON, backup__offsite__destination__pvc__keep="-1")
        assert not ok and "keep" in out

    def test_non_numeric_keep_is_refused(self):
        """Review of B1 (Cursor): Sprig's `int "abc"` is 0, so the old `lt … 0` guard let it render
        and the Job died in argparse."""
        ok, out = render(**ON, backup__offsite__destination__pvc__keep="abc")
        assert not ok and "keep" in out


class TestAccessModes:
    def test_rwx_needs_no_affinity(self):
        ok, out = render(**ON)              # the shipped default is ReadWriteMany
        assert ok, out
        assert "affinity" not in _pod(_one(_docs(out), "CronJob"))["spec"]

    def test_rwo_pins_the_job_to_the_dashboards_node(self):
        ok, out = render(**ON, persistence__accessMode="ReadWriteOnce")
        assert ok, out
        docs = _docs(out)
        pod = _pod(_one(docs, "CronJob"))
        (term,) = pod["spec"]["affinity"]["podAffinity"]["requiredDuringSchedulingIgnoredDuringExecution"]
        assert term["topologyKey"] == "kubernetes.io/hostname"
        selector = [d for d in docs if d.get("kind") == "Service"][0]["spec"]["selector"]
        assert term["labelSelector"]["matchLabels"] == selector

    def test_rwop_is_refused(self):
        ok, out = render(**ON, persistence__accessMode="ReadWriteOncePod")
        assert not ok and "ReadWriteOncePod" in out and "Pending forever" in out

    def test_derived_rwop_at_one_replica_is_refused_too(self):
        ok, out = render(**ON, persistence__accessMode="")
        assert not ok and "ReadWriteOncePod" in out


class TestPrerequisites:
    def test_no_persistence_is_refused(self):
        ok, out = render(**ON, persistence__enabled="false")
        assert not ok and "persistence.enabled=true" in out

    def test_no_on_volume_backup_is_refused(self):
        ok, out = render(**ON, config__backup__enabled="false")
        assert not ok and "config.backup.enabled=true" in out

    def test_a_backup_dir_outside_data_is_refused(self):
        ok, out = render(**ON, config__backup__dir="/backup")
        assert not ok and "under /data/" in out

    def test_a_backup_dir_that_walks_out_of_data_is_refused(self):
        """Review of B1 (Cursor): hasPrefix alone accepted /data/backup/../.., which is / in the pod."""
        ok, out = render(**ON, config__backup__dir="/data/backup/../..")
        assert not ok and "under /data/" in out

    def test_an_existing_data_claim_without_an_explicit_access_mode_is_refused(self):
        """Review of B1 (Cursor): the chart cannot read a live claim's mode, and an emptied
        accessMode derives one from replicaCount, which may not be the claim's."""
        ok, out = render(**ON, persistence__existingClaim="already-there", persistence__accessMode="")
        assert not ok and "cannot read the live claim" in out
        ok, out = render(**ON, persistence__existingClaim="already-there", persistence__accessMode="ReadWriteOnce")
        assert ok, out

    def test_an_unknown_destination_is_refused(self):
        ok, out = render(**ON, backup__offsite__destination__type="nfs")
        assert not ok and "is not a destination" in out


class TestS3Destination:
    def test_secret_is_required(self):
        values = {k: v for k, v in S3.items() if not k.endswith("existingSecret")}
        ok, out = render(**values)
        assert not ok and "existingSecret" in out and "never embeds" in out

    def test_image_is_required(self):
        values = {k: v for k, v in S3.items() if "image__repository" not in k}
        ok, out = render(**values)
        assert not ok and "S3 CLI" in out

    def test_verify_then_upload_in_two_containers(self):
        ok, out = render(**S3)
        assert ok, out
        docs = _docs(out)
        pod = _pod(_one(docs, "CronJob"))
        (stage,) = pod["spec"]["initContainers"]
        (upload,) = pod["spec"]["containers"]
        assert stage["command"][:2] == ["python3.14", "/scripts/offsite_backup.py"]
        assert stage["command"][stage["command"].index("--dest") + 1] == "/stage"
        assert stage["command"][stage["command"].index("--keep") + 1] == "0"
        assert upload["image"] == "public.ecr.aws/aws-cli/aws-cli:2.17.0"
        assert upload["envFrom"] == [{"secretRef": {"name": "backup-creds"}}]
        assert [m["name"] for m in upload["volumeMounts"] if m["name"] == "data"] == [], \
            "the upload container must never see the data claim"
        assert "aws s3 cp /stage/" in upload["command"][-1]
        assert not [d for d in docs if d.get("kind") == "PersistentVolumeClaim"
                    and d["metadata"]["name"].endswith("-backup-offsite")]

    def test_no_credential_is_rendered(self):
        ok, out = render(**S3)
        assert ok, out
        assert "AWS_SECRET_ACCESS_KEY:" not in out and "aws_secret" not in out.lower()

    def test_a_custom_command_replaces_the_default(self):
        ok, out = render(**S3, **{"backup__offsite__destination__s3__command[0]": "rclone"})
        assert ok, out
        (upload,) = _pod(_one(_docs(out), "CronJob"))["spec"]["containers"]
        assert upload["command"] == ["rclone"]


class TestAlerts:
    def _rules(self, **values):
        ok, out = render(monitoring__prometheusRule__enabled="true", **values)
        assert ok, out
        for d in _docs(out):
            if d.get("kind") == "PrometheusRule":
                return {r["alert"]: r for g in d["spec"]["groups"] for r in g["rules"]}
        raise AssertionError("no PrometheusRule rendered")

    def test_the_two_rules_render_only_with_the_cronjob(self):
        assert "GroupSyncDashboardOffsiteBackupStale" not in self._rules()
        rules = self._rules(**ON)
        stale = rules["GroupSyncDashboardOffsiteBackupStale"]
        absent = rules["GroupSyncDashboardOffsiteBackupUnobserved"]
        for rule in (stale, absent):
            assert 'cronjob="t-group-sync-dashboard-backup-offsite"' in rule["expr"]
            assert "kube_cronjob_status_last_successful_time" in rule["expr"]
        assert "> 43200" in stale["expr"] and stale["labels"]["severity"] == "critical"
        assert absent["expr"].startswith("absent(") and absent["labels"]["severity"] == "warning"
