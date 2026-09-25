"""Every Role, ClusterRole and binding this chart ships carries the policy system's provenance label (#312).

The dashboard reports a Group-subject binding with no `rbac.ocp.io/config-source` label (and no
`rbac.ocp.io/unmanaged-exception` annotation) as a grant made by hand, outside the policy system — and
the chart set that label on no template, so the dashboard flagged the chart's own auditor binding on its
own RBAC policy tab (measured on the reference cluster: `group-sync-dashboard-ra-b78c05817c9d`, logged as
UNMANAGED GRANT DISCOVERED every poll). The chart renders these objects from values on every install, so
the chart is their config source; the exception annotation stays a person's acknowledgement.

The template set is derived from the files, not listed here: a new template that ships an RBAC kind the
renders below do not reach fails `test_every_rbac_template_is_rendered`, so it cannot ship unlabelled.
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

from gsd.kube import CHART_CONFIG_SOURCE, CONFIG_SOURCE_LABEL

REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "charts" / "group-sync-dashboard"
CRC_VALUES = REPO / "environments" / "crc.yaml"
LABEL = CONFIG_SOURCE_LABEL  # the key and value the dashboard reads, not copies of them
RBAC_KINDS = ("Role", "ClusterRole", "RoleBinding", "ClusterRoleBinding")

pytestmark = pytest.mark.skipif(shutil.which("helm") is None, reason="helm not on PATH")

# Two renders reach every RBAC template: the lab's values (audit-log login capture, the fleet account, the
# cluster-Secret writes, the auditor binding) and the pod-log source with the authLogLevel Job, whose
# Role and ClusterRole only exist on that path.
RENDERS = {
    "crc": [],
    "pod-log": ["--set", "loginCapture.source=pod-log", "--set", "authLogLevel.manage=true"],
}


def _rbac_objects(extra: list[str]) -> list[tuple[str, dict]]:
    """(source template, document) for every RBAC-kind document the chart renders with these values."""
    done = subprocess.run(["helm", "template", "t", str(CHART), "-n", "x", "-f", str(CRC_VALUES), *extra],
                          capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    out = []
    for chunk in re.split(r"^---\s*$", done.stdout, flags=re.M):
        source = re.search(r"^# Source: group-sync-dashboard/templates/(\S+)$", chunk, re.M)
        doc = yaml.safe_load(chunk)
        if source and doc and doc.get("kind") in RBAC_KINDS:
            out.append((source.group(1), doc))
    return out


@pytest.fixture(scope="module")
def rendered() -> dict[str, list[tuple[str, dict]]]:
    return {name: _rbac_objects(extra) for name, extra in RENDERS.items()}


@pytest.mark.parametrize("render", list(RENDERS))
def test_every_rbac_object_names_the_chart_as_its_config_source(rendered, render):
    objects = rendered[render]
    assert objects, f"{render}: no RBAC object rendered"
    missing = [f"{src}: {d['kind']}/{d['metadata']['name']}" for src, d in objects
               if (d["metadata"].get("labels") or {}).get(LABEL) != CHART_CONFIG_SOURCE]
    assert not missing, f"{render}: RBAC objects without {LABEL}={CHART_CONFIG_SOURCE}: {missing}"


def test_the_auditor_binding_is_no_longer_unmanaged(rendered):
    """The binding #312 names: the ClusterRoleBinding the chart renders for its default auditor group."""
    auditor = [d for src, d in rendered["crc"] if src == "rbac-auditors.yaml" and d["kind"] == "ClusterRoleBinding"]
    assert auditor and all(d["metadata"]["labels"][LABEL] == CHART_CONFIG_SOURCE for d in auditor)
    assert all(s.get("kind") == "Group" for d in auditor for s in d["subjects"]), "the finding is about Group subjects"


def test_every_rbac_template_is_rendered(rendered):
    """Each template file that ships an RBAC kind is reached by one of the renders, so the label check covers it."""
    shipping = {p.name for p in (CHART / "templates").glob("*.yaml")
                if re.search(rf"^kind: ({'|'.join(RBAC_KINDS)})\s*$", p.read_text(), re.M)}
    reached = {src for objects in rendered.values() for src, _ in objects}
    assert shipping <= reached, f"RBAC templates no render reaches (add a value set to RENDERS): {sorted(shipping - reached)}"
