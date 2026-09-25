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


@pytest.fixture(scope="module")
def labelled(tmp_path_factory):
    """The module seed with namespace labels (it carries none): prod-ns pins team-a through the group label,
    dev-ns carries the mnemonic only, alpha-prod pins a group nothing binds, gamma-dev pins nothing
    (review of #222, OB3)."""
    tmp = tmp_path_factory.mktemp("labelled")
    store = seed_store(str(tmp / "writer.db"))
    store.replace_namespaces(CLUSTER, [
        {"name": "prod-ns", "phase": "Active", "metadata": {"company.net/mnemonic": "beta", "company.net/app-environment": "prod", "company.net/oud-group": "team-a"}},
        {"name": "dev-ns", "phase": "Active", "metadata": {"company.net/mnemonic": "beta", "company.net/app-environment": "dev"}},
        {"name": "alpha-prod", "phase": "Active", "metadata": {"company.net/mnemonic": "alpha", "company.net/app-environment": "prod", "company.net/oud-group": "bda-rbac-trino-alpha-users"}},
        {"name": "gamma-dev", "phase": "Active", "metadata": {"company.net/mnemonic": "gamma", "company.net/app-environment": "dev"}},
    ], NOW.strftime("%Y-%m-%dT%H:%M:%SZ"))
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


class TestTheStrTrimmerAndTheNamespacesHelp:
    """Review of #224 (OB3)."""

    def test_a_padded_namespace_prefix_is_the_trimmed_prefix(self):
        # The trim changes what an existing schedule selects: " prod" matched nothing before (no namespace
        # name starts with a space) and matches prod* now; spaces only meant nothing and mean everything.
        # Pinned so the change is deliberate and the CHANGELOG's sentence stays true.
        spec = REGISTRY["access-matrix"][0]
        assert validate_params(spec, {"namespace_prefix": " prod"})["namespace_prefix"] == "prod"
        assert validate_params(spec, {"namespace_prefix": "prod "})["namespace_prefix"] == "prod"
        assert validate_params(spec, {"namespace_prefix": "   "})["namespace_prefix"] == ""

    def test_the_namespaces_help_does_not_promise_an_override(self):
        # The validator refuses explicit names beside a Scope; the help must not say they override it.
        spec = REGISTRY["namespace-access"][0]
        p = next(x for x in spec.params if x.name == "namespaces")
        assert "override" not in p.help.lower(), p.help
        assert "not both" in p.help, p.help
        with pytest.raises(ValidationError, match="not more than one"):
            validate_params(spec, {"namespaces": ["prod-ns"], "selectors": {"company.net/mnemonic": ["demo"]}})


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

    def test_the_provenance_rows_say_what_happened_not_the_pollers_state_word(self, snapshot):
        # Operator, 2026-09-21: "Namespaces ok — attests absence" is misleading. It put the poller's own
        # state token beside a term of art whose meaning (SPEC_C3: "this namespace exists and has no
        # grants", as against "none observed") appeared nowhere on the row — and which reads on its face
        # as the report asserting that access IS absent. Nothing pinned these rows before this test.
        report = _build(snapshot, "groups")
        rows = {k: v for b in report.sections[0].blocks if getattr(b, "items", None) for k, v in b.items}
        for label in ("Namespaces", "User objects", "Login capture"):
            assert label in rows, rows
            # no bare state token is offered to a reader as the whole value
            assert rows[label] not in ("ok", "off", "forbidden", "pending"), (label, rows[label])
        assert not rows["Namespaces"].startswith(("ok ", "off ", "forbidden ", "pending ")), rows["Namespaces"]
        # the claim is spelled out, in either direction, and never as the bare term of art
        absence = "a namespace with no grants is reported as having none"
        cannot = "\u2018no grants\u2019 cannot be told from \u2018never read\u2019"
        assert (absence in rows["Namespaces"]) is report.coverage["attests_absence"], rows["Namespaces"]
        assert (cannot in rows["Namespaces"]) is not report.coverage["attests_absence"], rows["Namespaces"]
        assert "attests absence" not in rows["Namespaces"] and "does not attest absence" not in rows["Namespaces"]
        # every state has words, so a new one cannot render a KeyError or a raw token
        from gsd.reporting.catalogue.common import _CAPTURE, _NS_READ, _USERS_READ
        assert set(_NS_READ) == {"ok", "off", "forbidden", "pending"}
        assert set(_USERS_READ) == {"ok", "forbidden", "pending"} and set(_CAPTURE) == {"ok", "off", "pending"}
        # the JSON field consumers read is untouched
        assert isinstance(report.coverage["attests_absence"], bool)

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
        assert [r[0] for r in unmanaged_tbl.rows] == ["group team-b"]
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
        # a mnemonic with no exact-group label captured is a failed run with a reason, never a clean empty
        # pack a reviewer could sign (review of #222, OB3; the first cut pinned totals 0/0 here)
        with pytest.raises(ValidationError, match="no namespace-label capture|no namespace carries"):
            self._built(snapshot, "access-certification", group_mnemonic="beta")

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

    def test_a_scoped_login_pack_counts_the_scope_in_its_summary_too(self, snapshot):
        # Review of #222 (Codex M1): the summary by outcome and provider — and the `attempts` total it feeds —
        # counted the whole cluster's attempts on a pack whose users were narrowed (measured: users=alice gave
        # attempts=3, users=1). Every figure on a scoped pack is the scope's.
        scoped = self._built(snapshot, "login-activity", users="alice")
        summary = next(b for s in scoped.sections if s.title == "Summary" for b in s.blocks if getattr(b, "title", "") == "Attempts by outcome and provider")
        assert sum(int(r[2]) for r in summary.rows) == 1 and scoped.totals == {"attempts": 1, "users": 1, "rejected": 0}
        everyone = self._built(snapshot, "login-activity")
        assert everyone.totals["attempts"] == 3                       # alice, mallory, carol in the 30-day window; bob is 120 days out
        empty = self._built(snapshot, "login-activity", groups="empty-group")   # a group with no members counts nothing
        assert empty.totals == {"attempts": 0, "users": 0, "rejected": 0}

    def test_a_damaged_table_read_degrades_the_lookups_not_500s(self, snapshot, monkeypatch):
        # Review of #222 (Codex M4): a copy that opened cleanly can still raise sqlite3.Error from a later
        # read; discovered() wraps it as SnapshotError like the other seam methods, so the route answers
        # empty menus instead of a 500.
        import sqlite3
        from gsd.reporting.snapshot import Snapshot, SnapshotError
        real = Snapshot._rows
        def broken(self, sql, params=()):
            if "FROM group_state" in sql:
                raise sqlite3.OperationalError("simulated post-open damage")
            return real(self, sql, params)
        monkeypatch.setattr(Snapshot, "_rows", broken)
        with pytest.raises(SnapshotError):
            snapshot.discovered("crc-local", "company.net/mnemonic", "company.net/oud-group")

    def test_a_mnemonic_that_resolves_to_nothing_is_a_failed_run_not_an_empty_pack(self, labelled):
        # Review of #222 (OB3): measured on 7fa4a6e, an unconfigured deployment, a pre-capture copy and a value
        # no namespace carries each built a pack with totals 0/0 and nothing said — where namespace-access
        # refuses the same selection with a reason. The resolved case, for contrast: beta → prod-ns → team-a,
        # and the pack's Scope line names the resolved group.
        beta = self._built(labelled, "access-certification", group_mnemonic="beta")
        assert beta.totals == {"groups": 1, "users": 0}
        assert ("Scope", "mnemonics: beta (team-a)") in beta.sections[0].blocks[0].items
        # resolved to a group nothing binds: the header names it, so its absence below is readable
        alpha = self._built(labelled, "access-certification", group_mnemonic="alpha")
        assert alpha.totals == {"groups": 0, "users": 0}
        assert ("Scope", "mnemonics: alpha (bda-rbac-trino-alpha-users)") in alpha.sections[0].blocks[0].items
        with pytest.raises(ValidationError, match="no namespace carries company.net/mnemonic"):
            self._built(labelled, "access-certification", group_mnemonic="nope")
        with pytest.raises(ValidationError, match="pin no group through company.net/oud-group"):
            self._built(labelled, "access-certification", group_mnemonic="gamma")
        spec, build = REGISTRY["access-certification"]
        params = validate_params(spec, {**DEFAULT_PARAMS["access-certification"], "group_mnemonic": "beta"})
        with pytest.raises(ValidationError, match="not configured on this deployment"):
            build(labelled, _ctx(labelled, namespace_selector_labels=(), namespace_group_label="company.net/oud-group"), params)
        with pytest.raises(ValidationError, match="not configured on this deployment"):
            build(labelled, _ctx(labelled, namespace_selector_labels=("company.net/mnemonic",), namespace_group_label=""), params)
        # a copy from before the capture attests nothing, not zero (the same refusal as namespace-access)
        import shutil, sqlite3
        old = Path(labelled.path).parent.parent / "pre-capture"; old.mkdir()
        copy = old / Path(labelled.path).name; shutil.copy(labelled.path, copy)
        with sqlite3.connect(copy) as db:
            db.execute("DROP TABLE cluster_namespace_label")
            db.execute("PRAGMA user_version = 11")
        with Snapshot(copy) as pre:
            with pytest.raises(ValidationError, match="no namespace-label capture"):
                build(pre, _ctx(pre, **self.LABELS), params)

    def test_an_ungrouped_namespace_report_keeps_the_readers_order(self, snapshot, labelled):
        # Review of #222 (OB3): on the base branch explicit names came out in the order the reader gave them;
        # 7fa4a6e sorted them by name and forced (cluster-scoped) last even when no label grouped anything.
        spec, build = REGISTRY["namespace-access"]
        plain = dict(namespace_selector_labels=(), namespace_group_label="")
        built = build(snapshot, _ctx(snapshot, **plain), validate_params(spec, {"namespaces": "(cluster-scoped),prod-ns,dev-ns"}))
        titles = [s.title for s in built.sections if "Namespace:" in s.title or s.title == "Cluster-scoped bindings"]
        assert titles == ["Cluster-scoped bindings", "Namespace: prod-ns", "Namespace: dev-ns"], titles
        # with a grouping label captured the sections ARE sorted: bucket, then name, cluster scope last
        grouped = build(labelled, _ctx(labelled, **self.LABELS), validate_params(spec, {"namespaces": "(cluster-scoped),prod-ns,dev-ns", "group_by": "mnemonic"}))
        assert [s.title for s in grouped.sections if "Namespace:" in s.title or s.title == "Cluster-scoped bindings"][-1] == "Cluster-scoped bindings"

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

    def test_the_member_counts_are_cut_where_the_names_are(self, snapshot):
        # the cap bounds both projections of the same read: never a count for a name the menu does not offer
        snapshot.DISCOVERED_CAP = 2
        d = snapshot.discovered(CLUSTER, "company.net/mnemonic", "company.net/oud-group")
        assert d["groups"]["truncated"] is True and d["groups"]["values"] == ["empty-group", "hand-made"]
        assert d["groups"]["members"] == {"empty-group": 0, "hand-made": 1}

    def test_namespace_access_groups_its_sections_by_a_label(self, snapshot, tmp_path):
        spec, build = REGISTRY["namespace-access"]
        # nothing captured for this cluster (the seed carries no namespace labels): the headings stay as
        # they were, in the reader's order — the default group_by must not rewrite every heading on a
        # deployment without labels (review of #222, Grok), nor re-sort them (OB3)
        built = build(snapshot, _ctx(snapshot, **self.LABELS), validate_params(spec, {"namespaces": "prod-ns,dev-ns,(cluster-scoped)", "group_by": "oud-group"}))
        titles = [s.title for s in built.sections if "Namespace:" in s.title or s.title == "Cluster-scoped bindings"]
        assert titles == ["Namespace: prod-ns", "Namespace: dev-ns", "Cluster-scoped bindings"]
        # with the label captured on one namespace: that one bucketed first, the rest under "(no oud-group)"
        from reporting_seed import seed_store, write_snapshot
        store = seed_store(str(tmp_path / "w.db"))
        store.replace_namespaces(CLUSTER, [
            {"name": "prod-ns", "created_at": None, "phase": "Active", "metadata": {"company.net/oud-group": "app-ocp-rbac-prod-ns-admin"}},
            {"name": "dev-ns", "created_at": None, "phase": "Active", "metadata": {}}], "2026-09-14T00:00:00Z")
        d = tmp_path / "snap"; d.mkdir(); path = write_snapshot(store, d); store.close()
        with Snapshot(path) as snap:
            built = build(snap, _ctx(snap, **self.LABELS), validate_params(spec, {"namespaces": "prod-ns,dev-ns,(cluster-scoped)", "group_by": "oud-group"}))
        titles = [s.title for s in built.sections if "Namespace:" in s.title or s.title == "Cluster-scoped bindings"]
        assert titles == ["app-ocp-rbac-prod-ns-admin · Namespace: prod-ns", "(no oud-group) · Namespace: dev-ns", "Cluster-scoped bindings"], titles

    def test_a_named_subject_with_no_binding_is_said_and_dormant_access_is_scoped_throughout(self, snapshot):
        # Review of #222 (Grok): a named group with no binding vanished; dormant-access narrowed only its
        # last table; the groups report's scope did not narrow the membership changes.
        matrix = self._built(snapshot, "access-matrix", groups="team-a,no-such-group")
        assert any(s.title == "Named but not bound" and "no-such-group" in str(s.blocks[0].text) for s in matrix.sections)
        cert = self._built(snapshot, "access-certification", users="nobody")
        assert cert.totals == {"groups": 0, "users": 0} and any(s.title == "Named but not bound" for s in cert.sections)
        everyone = self._built(snapshot, "dormant-access")
        one = self._built(snapshot, "dormant-access", users="erin")
        assert everyone.totals["never_logged_in"] >= 1 and one.totals["never_logged_in"] <= everyone.totals["never_logged_in"]
        counts = lambda b: dict(b.sections[0].blocks[0].items)
        assert counts(one)["Members who have never logged in"] == one.totals["never_logged_in"]
        grp = self._built(snapshot, "groups", groups="team-b")
        assert grp.totals["groups"] == 1 and grp.totals["changes"] <= self._built(snapshot, "groups").totals["changes"]
