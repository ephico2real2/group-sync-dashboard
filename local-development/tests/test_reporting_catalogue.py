"""The eleven reports (docs/specs/SPEC_C3_reporting_microservice.md §9.5): the registry, the parameter grammar,
every report built over the seeded snapshot and rendered both ways, and what must never appear."""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from gsd.reporting.catalogue import REGISTRY, RunContext, ValidationError, validate_params
from gsd.reporting.catalogue.common import assemble, parse_namespaces
from gsd.reporting.config import REPORT_NAMES, ReportSettings
from gsd.reporting.model import DIRECT_BINDINGS_CAVEAT, WITHHELD
from gsd.reporting.render_html import render_html
from gsd.reporting.snapshot import CLUSTER_SCOPE, Snapshot
from reporting_seed import CLUSTER, NOW, RAW_ERROR, seed_store, write_snapshot

HELPERS = Path(__file__).resolve().parents[2] / "charts" / "group-sync-dashboard" / "templates" / "_helpers.tpl"
VENDOR = Path(__file__).resolve().parents[1] / "gsd" / "static" / "vendor"
FONTS = (str(VENDOR / "DejaVuSans.ttf"), str(VENDOR / "DejaVuSans-Bold.ttf"))


@pytest.fixture(scope="module")
def snapshot(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("catalogue")
    store = seed_store(str(tmp / "writer.db"))
    d = tmp / "snapshots"; d.mkdir()
    path = write_snapshot(store, d)
    store.close()
    snap = Snapshot(path)
    yield snap
    snap.close()


def _ctx(snap, **over) -> RunContext:
    settings = ReportSettings(pdf_enabled=True, pdf_variant="pdf/a-2b", font_regular=FONTS[0], font_bold=FONTS[1],
                              login_capture_enabled=over.pop("login_capture_enabled", True), namespaces_read_enabled=over.pop("namespaces_read_enabled", False),
                              **over)
    info = snap.info()
    return RunContext(settings=settings, cluster=snap.cluster(CLUSTER), now=NOW, run_id="20260906T120000.000000Z-ab12",
                      generated_by="root", generated_by_note="proxy-verified", snapshot_stamp=info.stamp,
                      snapshot_age_seconds=info.age_seconds(NOW), schema_version=info.schema_version)


DEFAULT_PARAMS = {
    "namespace-access": {"namespaces": "prod-ns,dev-ns,ghost-ns,(cluster-scoped)"},
    "access-certification": {"campaign": "Q3 2026", "due": "2026-10-01", "reviewer": "Jane Reviewer"},
}


def _build(snap, name, params=None, **ctx_over):
    spec, build = REGISTRY[name]
    ctx = _ctx(snap, **ctx_over)
    p = validate_params(spec, {**DEFAULT_PARAMS.get(name, {}), **(params or {})})
    return assemble(spec, snap, ctx, p, build(snap, ctx, p))


class TestTheRegistry:
    def test_the_registry_is_the_config_order_and_the_chart_names_the_same_switches(self):
        assert tuple(REGISTRY) == REPORT_NAMES
        helpers = HELPERS.read_text()
        for spec, _ in REGISTRY.values():
            if spec.name == "login-activity":
                assert '"loginActivity"' in helpers
            else:
                assert f'"{spec.values_key}" "{spec.name}"' in helpers, spec.name


class TestParameters:
    def test_unknown_keys_and_each_type(self):
        spec, _ = REGISTRY["groups"]
        with pytest.raises(ValidationError, match="unknown parameter"):
            validate_params(spec, {"window": 3})
        assert validate_params(spec, {})["window_days"] == 30
        assert validate_params(spec, {"window_days": "7", "include_members": "true"}) == {"groups": [], "window_days": 7, "include_members": True}   # #149 R7: the groups dimension
        with pytest.raises(ValidationError, match="between"):
            validate_params(spec, {"window_days": 0})
        with pytest.raises(ValidationError, match="true or false"):
            validate_params(spec, {"include_members": "maybe"})
        cert, _ = REGISTRY["access-certification"]
        with pytest.raises(ValidationError, match="required"):
            validate_params(cert, {"campaign": "x", "due": "2026-10-01"})
        with pytest.raises(ValidationError, match="YYYY-MM-DD"):
            validate_params(cert, {"campaign": "x", "due": "next week", "reviewer": "r"})
        with pytest.raises(ValidationError, match="unknown parameter"):      # #149 R7: the kind toggle is gone — the Subject scope subsumes it
            validate_params(cert, {"campaign": "x", "due": "2026-10-01", "reviewer": "r", "scope": "everything"})
        ok = validate_params(cert, {"campaign": "x", "due": "2026-10-01", "reviewer": "r", "users": "alice, bob", "group_mnemonic": ["beta"]})
        assert ok["users"] == ["alice", "bob"] and ok["groups"] == [] and ok["group_mnemonic"] == ["beta"]
        ns, _ = REGISTRY["namespace-access"]
        with pytest.raises(ValidationError, match="one of"):
            validate_params(ns, {"namespaces": "prod-ns", "group_by": "owner"})
        assert validate_params(ns, {"namespaces": "prod-ns"})["group_by"] == "mnemonic"

    def test_wrong_shapes_are_422s_not_500s_and_dates_are_real(self):
        """Codex, review C3: an integer where a list of names was expected raised TypeError — a 500 —
        and 2026-99-99 passed the date regex."""
        spec, _ = REGISTRY["namespace-access"]
        for bad in (7, ["prod-ns", 7], {"prod-ns": 1}, True):
            with pytest.raises(ValidationError, match="namespaces"):
                validate_params(spec, {"namespaces": bad})
        priv, _ = REGISTRY["privileged-access"]
        with pytest.raises(ValidationError, match="roles"):
            validate_params(priv, {"roles": [1, 2]})
        groups, _ = REGISTRY["groups"]
        # Cursor, second pass: int() itself accepts " 1", "1_000" and "\t1\n", so a padded or
        # underscored string was an integer while every other wrong shape was a 422.
        for bad in (True, 1.5, [30], " 1", "1_000", "\t1\n", "1.0"):
            with pytest.raises(ValidationError, match="integer"):
                validate_params(groups, {"window_days": bad})
        assert validate_params(groups, {"window_days": "7"})["window_days"] == 7
        assert validate_params(groups, {"window_days": 7})["window_days"] == 7
        assert validate_params(groups, {"window_days": ""})["window_days"] == 30   # "" is not provided: the default
        cert, _ = REGISTRY["access-certification"]
        with pytest.raises(ValidationError, match="real date"):
            validate_params(cert, {"campaign": "x", "due": "2026-99-99", "reviewer": "r"})
        for bad in (["x"], 1, 1.5, {"x": 1}):      # a string is a string; a number was stringified before
            with pytest.raises(ValidationError, match="must be a string"):
                validate_params(cert, {"campaign": bad, "due": "2026-10-01", "reviewer": "r"})
        assert validate_params(cert, {"campaign": "x", "due": "2026-10-01", "reviewer": "r"})["due"] == "2026-10-01"

    @pytest.mark.parametrize("kind,default,choices,bad", [
        ("namespaces", ["prod-ns"], (), (1, 1.5, True, {}, [], [["prod-ns"]], [1])),
        ("bool", False, (), (1, 1.0, [], {}, [["true"]], [1], "yes")),
        ("int", 30, (), (True, 1.0, [], {}, [[1]], [1], "1.0", " 1", "1_000")),
        ("enum", "all", ("all", "groups", "users"), (1, 1.0, True, [], {}, [["all"]], [1])),
        ("date", "2026-10-01", (), (1, 1.0, True, [], {}, [["2026-10-01"]], [1], "2026-02-30", "2026-13-01")),
        ("csv", ["admin"], (), (1, 1.0, True, {}, [["admin"]], [1])),
        ("str", "default", (), (1, 1.0, True, [], {}, [["x"]], [1])),
    ])
    def test_every_parameter_type_refuses_every_wrong_json_shape(self, kind, default, choices, bad):
        """Codex, review C3 second pass: the matrix, one probe spec per type, so a new arm cannot
        quietly accept a shape the others refuse. Not in the lists on purpose: None and "" are "not
        provided" and take the default; an empty list is a legitimate empty csv."""
        from gsd.reporting.catalogue.common import ParamSpec, ReportSpec
        spec = ReportSpec(name="probe", title="Probe", summary="Probe", values_key="probe",
                          params=(ParamSpec("value", kind, default, "probe", choices=choices),))
        for value in bad:
            with pytest.raises(ValidationError):
                validate_params(spec, {"value": value})
        assert validate_params(spec, {"value": None})["value"] == default
        assert validate_params(spec, {})["value"] == default

    def test_namespaces_share_the_parser_rules(self):
        assert parse_namespaces("prod-ns, prod-ns,(cluster-scoped)") == ["prod-ns", CLUSTER_SCOPE]
        with pytest.raises(ValidationError, match="not a namespace name"):
            parse_namespaces("Prod_NS")
        with pytest.raises(ValidationError, match="at least one"):
            parse_namespaces(" , ")
        with pytest.raises(ValidationError, match="at most 50"):
            parse_namespaces(",".join(f"ns{i}" for i in range(51)))

    def test_login_activity_refuses_to_build_without_capture(self, snapshot):
        with pytest.raises(ValidationError, match="loginCapture.enabled"):
            _build(snapshot, "login-activity", login_capture_enabled=False)


class TestEveryReportBuildsAndRenders:
    @pytest.mark.parametrize("name", REPORT_NAMES)
    def test_builds_seals_and_renders_both_ways(self, snapshot, name):
        from gsd.reporting.render_pdf import render_pdf
        report = _build(snapshot, name)
        assert report.sections[0].title == "Provenance and coverage"
        text = json.dumps(report.canonical(), default=str, ensure_ascii=False)
        assert DIRECT_BINDINGS_CAVEAT in text
        assert len(report.sha256) == 64
        html = render_html(report, "GSD")
        assert report.sha256 in html and RAW_ERROR not in html
        pdf = render_pdf(report, "GSD", "pdf/a-2b", *FONTS)
        assert pdf.startswith(b"%PDF") and RAW_ERROR.encode() not in pdf

    def test_namespace_access_attests_absence_only_under_ok_coverage(self, tmp_path):
        store = seed_store(str(tmp_path / "w.db"))
        store.replace_namespaces(CLUSTER, [{"name": "prod-ns", "created_at": None, "phase": "Active"}, {"name": "dev-ns", "created_at": None, "phase": "Active"}], "2026-09-06T11:00:00Z")
        d = tmp_path / "s"; d.mkdir(); path = write_snapshot(store, d); store.close()
        with Snapshot(path) as snap:
            report = _build(snap, "namespace-access", namespaces_read_enabled=True)
        text = json.dumps(report.canonical(), default=str, ensure_ascii=False)
        assert "does NOT exist on the cluster" in text and report.coverage["attests_absence"] is True
        # the module fixture's snapshot has no namespace read: existence is not attested
        return

    def test_without_the_namespace_read_existence_is_not_attested(self, snapshot):
        report = _build(snapshot, "namespace-access")
        text = json.dumps(report.canonical(), default=str, ensure_ascii=False)
        assert "does NOT exist" not in text and "existence not attested" in text
        assert report.coverage["attests_absence"] is False and report.totals["namespaces"] == 4

    def test_privileged_includes_rosters_by_default_and_groups_does_not(self, snapshot):
        priv = _build(snapshot, "privileged-access")
        assert priv.include_members is True and any("Members of team-b" in b.title for s in priv.sections for b in s.blocks if hasattr(b, "title"))
        assert priv.totals["direct_grants"] == 1, "frank's cluster-admin; the platform SA is excluded"
        groups = _build(snapshot, "groups")
        assert groups.include_members is False and not any(s.title == "Rosters" for s in groups.sections)

    def test_the_compliance_snapshot_agrees_with_the_findings(self, snapshot):
        report = _build(snapshot, "compliance-snapshot")
        counts = snapshot.findings_counts(CLUSTER)
        for k, v in counts.items():
            assert report.totals[f"finding_{k}"] == v, k
        assert report.totals["privileged_group_grants"] == 1 and report.totals["privileged_direct_grants"] == 1

    def test_the_certification_pack_has_decision_columns_and_ends_with_the_sign_off(self, snapshot):
        report = _build(snapshot, "access-certification")
        tables = [b for s in report.sections for b in s.blocks if getattr(b, "kind", "") == "table" and "indings of" in b.title]
        assert tables and all(t.columns[-3:] == ["Approve", "Revoke", "Comment"] for t in tables)
        assert report.sections[-1].title == "Sign-off"
        # four groups carry a binding in the seed after #147 omits system:authenticated
        # (team-a, team-b, gone-group, teem-a); two people are bound directly
        assert report.totals == {"groups": 4, "users": 2}

    def test_system_subjects_are_absent_from_binding_reports_and_are_not_unmanaged(self, snapshot):
        """#147: system:authenticated (GROUP, built_in) and the seed SA (is_platform=1)
        must not appear in any report that lists bindings, and must not produce an
        unmanaged/handmade finding. A real group/person stays classified as before.
        The seed already carries both platform rows (reporting_seed.replace_bindings /
        replace_user_bindings)."""
        absent = ("system:authenticated", "authenticated-basic",
                  "system:serviceaccount:openshift-x:y", "sa-admin")
        emitters = ("namespace-access", "access-matrix", "privileged-access",
                    "binding-findings", "access-certification", "compliance-snapshot")
        for name in emitters:
            text = json.dumps(_build(snapshot, name).canonical(), default=str, ensure_ascii=False)
            for needle in absent:
                assert needle not in text, (name, needle)

        am = _build(snapshot, "access-matrix")
        matrix = next(b for s in am.sections for b in s.blocks if getattr(b, "title", "") == "Matrix")
        by_binding = {r[4]: r for r in matrix.rows}
        assert "authenticated-basic" not in by_binding and "sa-admin" not in by_binding
        assert by_binding["team-a-edit"][1] == "team-a" and by_binding["team-a-edit"][6] == "ok"
        assert by_binding["handmade-edit"][1] == "team-b"
        assert by_binding["handmade-edit"][5] == "hand-made"
        assert by_binding["handmade-edit"][6] == "unmanaged"
        assert by_binding["frank-admin"][0] == "user" and by_binding["frank-admin"][1] == "frank"
        assert by_binding["erin-view"][0] == "user" and by_binding["erin-view"][1] == "erin"
        assert all(not str(r[1]).startswith("system:") for r in matrix.rows)
        assert all(r[6] != "unmanaged" or r[1] == "team-b" for r in matrix.rows)

        bf = _build(snapshot, "binding-findings")
        assert bf.totals.get("built_in", 0) == 0
        assert bf.totals["unmanaged"] == 1
        assert bf.totals["direct_user"] == 2
        unmanaged_tbl = next(b for s in bf.sections for b in s.blocks
                             if getattr(b, "title", "") == "unmanaged")
        assert [r[0] for r in unmanaged_tbl.rows] == ["team-b"]
        assert all(not str(c).startswith("system:") for r in unmanaged_tbl.rows for c in r)

        # SA is stored, just not listed (is_platform). Store path is the include_platform read.
        sa = snapshot.user_bindings(CLUSTER, include_platform=True)
        assert any(u["user_name"].startswith("system:serviceaccount:") and u["is_platform"] for u in sa)
        assert all(not u["user_name"].startswith("system:") for u in snapshot.user_bindings(CLUSTER))

    def test_a_system_only_namespace_is_not_observed_and_the_builtin_tier_is_gone(self, snapshot, tmp_path):
        """#147 review F1a: the system: omit applied only to the listing left binding_namespaces and
        counts()["namespaces_with_bindings"] still counting a namespace whose ONLY binding is a
        system: group. Every real cluster has image-puller system:serviceaccounts:<ns> bindings, so
        namespace-access would print "Observed: yes" over an empty table and the namespace count would
        be inflated. Those surfaces now omit system: too, and binding-findings drops the built_in tier
        (it would otherwise be a permanent, misleading 0)."""
        base_observed = {r["namespace"] for r in snapshot.binding_namespaces(CLUSTER)}
        base_nwb = snapshot.counts(CLUSTER)["namespaces_with_bindings"]

        store = seed_store(str(tmp_path / "w.db"))
        keep = ("binding_kind", "binding_namespace", "binding_name", "role_kind",
                "role_name", "group_name", "managed_source", "exception")
        existing = [{k: b.get(k) for k in keep} for b in store.all_bindings(CLUSTER)]
        image_puller = {"binding_kind": "RoleBinding", "binding_namespace": "only-sys",
                        "binding_name": "system:image-pullers", "role_kind": "ClusterRole",
                        "role_name": "system:image-puller",
                        "group_name": "system:serviceaccounts:only-sys"}
        store.replace_bindings(CLUSTER, existing + [image_puller], "2026-09-06T12:00:00Z")
        d = tmp_path / "s"; d.mkdir(); path = write_snapshot(store, d); store.close()
        with Snapshot(path) as snap:
            observed = {r["namespace"] for r in snap.binding_namespaces(CLUSTER)}
            assert "only-sys" not in observed          # fail-before: image-puller made it observed
            assert observed == base_observed           # adding a system:-only namespace changes nothing
            assert snap.counts(CLUSTER)["namespaces_with_bindings"] == base_nwb

            bf = _build(snap, "binding-findings")
            assert "built_in" not in bf.totals         # fail-before: the permanent-0 built_in tier
            text = json.dumps(bf.canonical(), default=str, ensure_ascii=False)
            assert "system:serviceaccounts:only-sys" not in text
            assert "RBAC policy tab" not in text       # summary no longer claims tab parity

    def test_groupsync_health_withholds_the_error_text(self, snapshot):
        report = _build(snapshot, "groupsync-health")
        text = json.dumps(report.canonical(), default=str, ensure_ascii=False)
        assert WITHHELD in text and RAW_ERROR not in text
        assert "TrustedApplications" not in text

    def test_dormant_access_uses_capture_when_told_it_is_on(self, snapshot):
        with_capture = _build(snapshot, "dormant-access", {"dormant_days": 90})
        assert with_capture.totals["dormant"] == 1, "bob's last success is 120 days old; alice's is yesterday"
        without = _build(snapshot, "dormant-access", login_capture_enabled=False)
        assert without.totals["dormant"] is None


class TestSubjectScopeAndLookups:
    """#149 R7: the Subject scope replaces the kind toggle; a mnemonic resolves to the exact group its
    namespaces pin; login-activity takes groups; the discovered lookups; namespace-access groups its output."""

    LABELS = dict(namespace_selector_labels=("company.net/mnemonic", "company.net/app-environment"), namespace_group_label="company.net/oud-group")

    def _built(self, snap, name, **params):
        spec, build = REGISTRY[name]
        return build(snap, _ctx(snap, **self.LABELS), validate_params(spec, {**DEFAULT_PARAMS.get(name, {}), **params}))

    def _names(self, built, prefix):
        return [s.title for s in built.sections if s.title.startswith(prefix)]

    def test_access_matrix_subject_scope(self, snapshot):
        everything = self._built(snapshot, "access-matrix")
        assert everything.totals["subjects"] >= 3
        users_only = self._built(snapshot, "access-matrix", users="frank")
        assert users_only.totals["subjects"] == 1 and users_only.totals["rows"] >= 1     # groups are out: the reader asked for a user
        groups_only = self._built(snapshot, "access-matrix", groups="team-a")
        assert groups_only.totals["subjects"] == 1
        both = self._built(snapshot, "access-matrix", users="frank", groups="team-a")
        assert both.totals["subjects"] == 2

    def test_access_certification_subject_scope_and_mnemonic(self, snapshot):
        everything = self._built(snapshot, "access-certification")
        assert everything.totals["groups"] >= 2 and everything.totals["users"] >= 1
        one = self._built(snapshot, "access-certification", groups="team-a")
        assert one.totals == {"groups": 1, "users": 0}
        assert self._names(one, "Group:") == ["Group: team-a"]
        # the provenance names the scope in words
        assert "groups: team-a" in str(one.sections[0].blocks[0].items)
        # a mnemonic with no exact-group label captured names no group: nothing certified, not everything
        none = self._built(snapshot, "access-certification", group_mnemonic="beta")
        assert none.totals == {"groups": 0, "users": 0}

    def test_login_activity_users_and_groups(self, snapshot):
        spec, build = REGISTRY["login-activity"]
        assert [p.name for p in spec.params if p.group == "subject"] == ["users", "groups"]
        by_group = self._built(snapshot, "login-activity", groups="team-a")      # alice, bob
        by_user = self._built(snapshot, "login-activity", users="alice")
        everyone = self._built(snapshot, "login-activity")
        table = lambda b: next(t for s in b.sections if s.title == "Per user" for t in s.blocks)
        assert {r[0] for r in table(by_group).rows} <= {"alice", "bob"} and len(table(by_group).rows) >= 1
        assert {r[0] for r in table(by_user).rows} == {"alice"}
        assert len(table(everyone).rows) >= len(table(by_group).rows)

    def test_the_specs_carry_what_the_shell_renders(self):
        access, _ = REGISTRY["access-matrix"]
        j = {p["name"]: p for p in access.as_json(True)["params"]}
        assert j["users"]["source"] == "users" and j["users"]["group"] == "subject" and j["groups"]["source"] == "groups"
        assert j["namespace_prefix"]["advanced"] is True
        assert {p["name"]: p["unit"] for p in REGISTRY["groups"][0].as_json(True)["params"]}["window_days"] == "days"
        assert {p["name"]: p["source"] for p in REGISTRY["users"][0].as_json(True)["params"]} == {"users": "users", "providers": "providers"}
        assert {p["name"]: p["source"] for p in REGISTRY["privileged-access"][0].as_json(True)["params"]}["roles"] == "roles"
        assert "subject_kind" not in {p.name for p in access.params} and "scope" not in {p.name for p in REGISTRY["access-certification"][0].params}

    def test_the_snapshot_lists_the_discovered_lookups(self, snapshot):
        d = snapshot.discovered(CLUSTER, "company.net/mnemonic", "company.net/oud-group")
        assert d["providers"]["values"] == ["corp_ldap"]
        assert "edit" in d["roles"]["values"] and "cluster-admin" in d["roles"]["values"]
        assert d["users"]["values"] == ["alice", "bob", "erin"]
        assert "team-a" in d["groups"]["values"] and d["groups"]["truncated"] is False
        assert snapshot.members_of_groups(CLUSTER, ["team-a", "hand-made"]) == {"alice", "bob", "erin"}
        assert snapshot.members_of_groups(CLUSTER, []) == set()

    def test_namespace_access_groups_its_sections_by_a_label(self, snapshot):
        spec, build = REGISTRY["namespace-access"]
        built = build(snapshot, _ctx(snapshot, **self.LABELS), validate_params(spec, {"namespaces": "prod-ns,dev-ns,(cluster-scoped)", "group_by": "oud-group"}))
        titles = [s.title for s in built.sections if "Namespace:" in s.title or s.title == "Cluster-scoped bindings"]
        # no exact-group label captured in the seed: every namespace falls under the same bucket, cluster scope last
        assert titles[-1] == "Cluster-scoped bindings"
        assert all(t.startswith("(no oud-group) · Namespace: ") for t in titles[:-1]), titles
